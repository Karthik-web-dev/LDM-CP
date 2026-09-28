"""Central orchestration: circuit -> structural checks -> graph -> AST -> truth tables -> equivalence -> AI."""

import json
import logging
import time
from typing import Any

from app.ai.client import AIValidator
from app.ai.validator import AIValidationError, reconcile
from app.analysis.boolean_ast import render_expression, rendered_length
from app.analysis.equivalence import compare_columns, map_outputs
from app.analysis.expected_function import build_expected, expected_truth_table
from app.analysis.expression_generator import generate_expressions
from app.analysis.kmap import KMapError, build_kmap
from app.analysis.minimize import minimize_sop
from app.analysis.graph import NodeKind
from app.analysis.structural_validator import validate_structure
from app.analysis.truth_table import generate_truth_table
from app.config import Settings
from app.models.ai import AIFeedback
from app.models.analysis import DeterministicResult, IssueType, OutputComparison, StructuralIssue
from app.models.api import KMapResponse, TaskPreview, ValidateResponse
from app.models.circuit import Circuit
from app.models.task import Task

logger = logging.getLogger("ldm.validation")

# Truth tables up to this many rows are sent to the AI tutor.
AI_TRUTH_TABLE_MAX_ROWS = 64


def _issue(type_: IssueType, severity: str, message: str, component: str | None = None) -> StructuralIssue:
    return StructuralIssue(type=type_, severity=severity, message=message, component=component)  # type: ignore[arg-type]


class ValidationService:
    def __init__(self, ai_validator: AIValidator, settings: Settings):
        self.ai_validator = ai_validator
        self.settings = settings
        self.limits = settings.limits

    # ---- deterministic analysis -------------------------------------------------------------

    def preview_task(self, task: Task) -> TaskPreview:
        """Describe a target both as equations and as a truth table (used by the target editor)."""
        outputs, problems = build_expected(task)
        if problems:
            return TaskPreview(valid=False, errors=problems)
        variables = list(dict.fromkeys(list(task.inputs) + sorted(set().union(*(o.variables for o in outputs)))))
        if len(variables) > self.limits.max_truth_table_variables:
            return TaskPreview(valid=False, errors=[f"The target uses {len(variables)} inputs; at most {self.limits.max_truth_table_variables} are supported."])
        table = expected_truth_table(outputs, variables, self.limits.max_truth_table_variables)
        simplified = {}
        for col, o in enumerate(outputs):
            ones = {i for i, r in enumerate(table.rows) if r.outputs[col] == 1}
            dont_cares = {i for i, r in enumerate(table.rows) if r.outputs[col] is None}
            simplified[o.label] = render_expression(minimize_sop(variables, ones, dont_cares))
        return TaskPreview(
            valid=True,
            inputs=variables,
            outputs=[o.label for o in outputs],
            # Rendered from the parse, so the user sees exactly how their equation was understood.
            expressions={o.label: render_expression(o.expression) for o in outputs},
            simplified=simplified,
            truth_table=table,
        )

    def analyze(self, task: Task, circuit: Circuit) -> DeterministicResult:
        report = validate_structure(circuit, self.limits)
        logger.info(
            "structural_validation_completed errors=%d warnings=%d",
            len(report.errors), len(report.warnings),
        )
        expected, task_problems = build_expected(task)
        errors = report.errors + [_issue(IssueType.INVALID_TASK, "error", p) for p in task_problems]
        warnings = list(report.warnings)

        if errors or report.graph is None or report.order is None:
            return DeterministicResult(structurally_valid=not report.has_errors(), errors=errors, warnings=warnings)

        graph = report.graph
        by_output_id = generate_expressions(graph, report.order)
        output_label = {n.id: n.label or n.id for n in graph.nodes_of_kind(NodeKind.OUTPUT)}
        circuit_exprs = {output_label[oid]: expr for oid, expr in by_output_id.items()}

        output_expressions: dict[str, str | None] = {}
        for label, expr in circuit_exprs.items():
            if rendered_length(expr) > self.limits.max_expression_length:
                output_expressions[label] = None
                warnings.append(_issue(IssueType.EXPRESSION_TOO_LARGE, "warning", f"The expression for output {label} is too long to display; it was still checked with a truth table."))
            else:
                output_expressions[label] = render_expression(expr)
        logger.info("boolean_expression_generated outputs=%d", len(output_expressions))

        # Variables: task-declared order first, then any other circuit or expected variables.
        circuit_vars = [i.label for i in circuit.inputs]
        expected_vars: set[str] = set().union(*(o.variables for o in expected)) if expected else set()
        variables = list(dict.fromkeys([v for v in task.inputs if v in set(circuit_vars) | expected_vars]))
        variables += sorted((set(circuit_vars) | expected_vars) - set(variables))

        for v in sorted(expected_vars - set(circuit_vars)):
            warnings.append(_issue(IssueType.MISSING_TASK_INPUT, "warning", f"The task uses input {v}, but the circuit has no input labelled {v}."))
        task_vars = expected_vars | set(task.inputs)
        for inp in circuit.inputs:
            if inp.label not in task_vars:
                warnings.append(_issue(IssueType.EXTRA_INPUT, "warning", f"Input {inp.label} is not part of the task.", inp.id))

        result = DeterministicResult(
            structurally_valid=True,
            expression=next(iter(output_expressions.values()), None),
            output_expressions=output_expressions,
            variables=variables,
            evaluation_order=report.order,
            errors=[],
            warnings=warnings,
        )

        if len(variables) > self.limits.max_truth_table_variables:
            result.errors.append(_issue(IssueType.LIMIT_EXCEEDED, "error", f"The circuit and task use {len(variables)} input variables; at most {self.limits.max_truth_table_variables} can be checked."))
            return result

        student_table = generate_truth_table(circuit_exprs, variables, self.limits.max_truth_table_variables)
        target_table = expected_truth_table(expected, variables, self.limits.max_truth_table_variables)
        result.truth_table = student_table
        result.expected_truth_table = target_table

        by_label = {o.label: o for o in expected}
        mappings, extra_outputs = map_outputs(list(by_label), list(circuit_exprs))
        for m in mappings:
            target = by_label[m.expected_output]
            if m.circuit_output is None:
                warnings.append(_issue(IssueType.MISSING_EXPECTED_OUTPUT, "warning", f"The task expects an output labelled {m.expected_output}, but the circuit has none."))
                result.comparisons.append(OutputComparison(
                    expected_output=m.expected_output, circuit_output=None,
                    expected_expression=target.display, expected_defined_by=target.defined_by,
                    circuit_expression=None, equivalent=False,
                ))
                continue
            if m.label_mismatch:
                warnings.append(_issue(IssueType.OUTPUT_LABEL_MISMATCH, "warning", f"Your output is labelled {m.circuit_output}; the task calls it {m.expected_output}. It was compared anyway."))
            cmp = compare_columns(student_table, m.circuit_output, target_table, m.expected_output)
            result.comparisons.append(OutputComparison(
                expected_output=m.expected_output,
                circuit_output=m.circuit_output,
                expected_expression=target.display,
                expected_defined_by=target.defined_by,
                circuit_expression=output_expressions.get(m.circuit_output),
                equivalent=cmp.equivalent,
                counterexamples=cmp.counterexamples,
                mismatch_count=cmp.mismatch_count,
            ))
        for extra in extra_outputs:
            warnings.append(_issue(IssueType.EXTRA_OUTPUT, "warning", f"Output {extra} is not part of the task and was not checked."))

        result.warnings = warnings  # the model holds a copy; publish warnings added above
        result.equivalent_to_expected = bool(result.comparisons) and all(c.equivalent for c in result.comparisons)
        logger.info("equivalence_checked equivalent=%s", result.equivalent_to_expected)
        return result

    # ---- AI tutor ---------------------------------------------------------------------------

    def build_ai_payload(self, task: Task, circuit: Circuit, det: DeterministicResult) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task": {
                "title": task.title,
                "description": task.description,
                "expected_outputs": self._describe_targets(task),
            },
            "student_circuit": circuit.model_dump(by_alias=True, exclude_none=True, exclude={
                "inputs": {"__all__": {"position"}}, "gates": {"__all__": {"position"}}, "outputs": {"__all__": {"position"}},
            }),
            "deterministic_analysis": {
                "output_expressions": det.output_expressions,
                "equivalent_to_expected": det.equivalent_to_expected,
                "comparisons": [c.model_dump() for c in det.comparisons],
                "errors": [{"type": e.type.value, "component": e.component, "message": e.message} for e in det.errors],
                "warnings": [{"type": w.type.value, "component": w.component, "message": w.message} for w in det.warnings],
            },
        }
        if det.truth_table and det.expected_truth_table and len(det.truth_table.rows) <= AI_TRUTH_TABLE_MAX_ROWS:
            payload["deterministic_analysis"]["truth_table"] = [
                {
                    "inputs": dict(zip(det.variables, s.inputs)),
                    "circuit": dict(zip(det.truth_table.outputs, s.outputs)),
                    # "X" = don't care: any value is acceptable on that row.
                    "expected": {k: ("X" if v is None else v) for k, v in zip(det.expected_truth_table.outputs, e.outputs)},
                }
                for s, e in zip(det.truth_table.rows, det.expected_truth_table.rows)
            ]
        return payload

    @staticmethod
    def _describe_targets(task: Task) -> dict[str, Any]:
        expected, _ = build_expected(task)
        if task.expected_truth_table is not None:
            return {
                o.label: {"defined_by": "truth_table", "equivalent_expression": o.display, "inputs": o.variables,
                          "column": ["X" if v is None else int(v) for v in (o.table or [])]}
                for o in expected
            }
        return {o.label: {"defined_by": "expression", "expression": o.display} for o in expected}

    async def run_ai(
        self, task: Task, circuit: Circuit, det: DeterministicResult, is_correct: bool, include_ai: bool, mode: str = "feedback",
    ) -> AIFeedback:
        if not include_ai:
            return AIFeedback(available=False, skipped_reason="AI feedback was not requested.")
        # Hints are explicitly requested and useful at any stage; feedback waits for a complete circuit.
        if mode == "feedback" and (not det.structurally_valid or det.errors):
            return AIFeedback(available=False, skipped_reason="Fix the circuit problems listed in the analysis first, or ask for a hint.")
        if mode == "feedback" and is_correct and not self.settings.ai_on_correct:
            return AIFeedback(available=False, skipped_reason="The circuit is correct.")

        payload = self.build_ai_payload(task, circuit, det)
        if len(json.dumps(payload)) > self.limits.max_ai_prompt_chars:
            return AIFeedback(available=False, error="This circuit is too large for AI feedback.", error_kind="prompt_too_large")

        started = time.perf_counter()
        logger.info("ai_validation_started model=%s", self.ai_validator.model_name)
        try:
            response = await self.ai_validator.validate(payload, mode)
        except AIValidationError as exc:
            level = logging.INFO if exc.kind == "disabled" else logging.WARNING
            logger.log(level, "ai_validation_failed kind=%s", exc.kind)
            return AIFeedback(available=False, error=exc.message, error_kind=exc.kind)
        except Exception:  # never let the AI layer break deterministic results
            logger.exception("ai_validation_failed kind=unknown")
            return AIFeedback(available=False, error="AI validation service temporarily unavailable.", error_kind="unknown")

        component_ids = {c.id for c in circuit.inputs} | {g.id for g in circuit.gates} | {o.id for o in circuit.outputs}
        feedback = reconcile(response, is_correct, component_ids, self.ai_validator.model_name)
        logger.info(
            "ai_validation_completed ms=%d agrees=%s",
            (time.perf_counter() - started) * 1000, feedback.agrees_with_analysis,
        )
        return feedback

    # ---- entry point ------------------------------------------------------------------------

    def kmaps(self, task: Task, circuit: Circuit | None, source: str) -> KMapResponse:
        """K-maps of the target or of the circuit's function, one per output. No AI involved."""
        if source == "target":
            preview = self.preview_task(task)
            if not preview.valid or preview.truth_table is None:
                return KMapResponse(source="target", errors=preview.errors)
            table = preview.truth_table
        else:
            det = self.analyze(task, circuit)  # type: ignore[arg-type]
            if det.errors or det.truth_table is None:
                return KMapResponse(source="circuit", errors=["Complete the circuit first: " + "; ".join(e.message for e in det.errors[:3])])
            table = det.truth_table
        try:
            return KMapResponse(source=source, kmaps=[build_kmap(table, o) for o in table.outputs])  # type: ignore[arg-type]
        except KMapError as exc:
            return KMapResponse(source=source, errors=[str(exc)])  # type: ignore[arg-type]

    async def validate(self, task: Task, circuit: Circuit, include_ai: bool = True, ai_mode: str = "feedback") -> ValidateResponse:
        logger.info(
            "validation_started task=%s inputs=%d gates=%d outputs=%d connections=%d",
            task.id, len(circuit.inputs), len(circuit.gates), len(circuit.outputs), len(circuit.connections),
        )
        det = self.analyze(task, circuit)
        is_correct = det.structurally_valid and not det.errors and det.equivalent_to_expected
        ai = await self.run_ai(task, circuit, det, is_correct, include_ai, ai_mode)
        return ValidateResponse(success=True, is_correct=is_correct, task=task, deterministic=det, ai=ai)
