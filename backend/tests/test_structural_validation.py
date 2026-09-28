from app.analysis.structural_validator import validate_structure
from app.config import Limits
from app.models.analysis import IssueType
from app.models.circuit import Circuit
from tests.helpers import and_or_circuit, circuit, make_circuit

LIMITS = Limits()


def issues(c, severity=None):
    report = validate_structure(c, LIMITS)
    return [(i.type, i.component) for i in report.issues if severity is None or i.severity == severity]


def test_valid_circuit_has_no_issues():
    report = validate_structure(and_or_circuit(), LIMITS)
    assert report.issues == []
    assert report.order is not None


def test_missing_input_connection():
    c = circuit(["A"], {"gate_2": "AND"}, ["Y"], [("A", "gate_2", 0), ("gate_2", "Y")])
    report = validate_structure(c, LIMITS)
    [err] = report.errors
    assert (err.type, err.component) == (IssueType.MISSING_INPUT, "gate_2")
    assert "input 2" in err.message


def test_missing_input_on_dangling_gate_is_only_a_warning():
    c = circuit(["A", "B"], {"g": "AND", "stray": "OR"}, ["Y"], [("A", "g", 0), ("B", "g", 1), ("g", "Y")])
    assert issues(c, "error") == []
    assert (IssueType.MISSING_INPUT, "stray") in issues(c, "warning")
    assert (IssueType.DANGLING_GATE, "stray") in issues(c, "warning")


def test_missing_output():
    c = circuit(["A", "B"], {"g": "AND"}, [], [("A", "g", 0), ("B", "g", 1)])
    assert (IssueType.MISSING_OUTPUT, None) in issues(c, "error")


def test_undriven_output():
    c = circuit(["A"], {}, ["Y"], [])
    assert (IssueType.UNDRIVEN_OUTPUT, "out_Y") in issues(c, "error")
    assert (IssueType.UNCONNECTED_INPUT, "in_A") in issues(c, "warning")


def test_multiple_drivers_on_gate_pin_and_output():
    c = circuit(["A", "B"], {"g": "NOT"}, ["Y"], [("A", "g"), ("B", "g"), ("g", "Y"), ("A", "Y")])
    errs = issues(c, "error")
    assert (IssueType.MULTIPLE_DRIVER, "g") in errs
    assert (IssueType.MULTIPLE_DRIVER, "out_Y") in errs


def test_unknown_gate():
    c = circuit(["A", "B"], {"g": ("FLUX", 2)}, ["Y"], [("A", "g", 0), ("B", "g", 1), ("g", "Y")])
    assert (IssueType.UNKNOWN_GATE, "g") in issues(c, "error")


def test_gate_aliases_are_accepted():
    c = circuit(["A"], {"g": "inv"}, ["Y"], [("A", "g"), ("g", "Y")])
    assert issues(c) == []


def test_invalid_gate_arity():
    c1 = circuit(["A"], {"g": ("AND", 1)}, ["Y"], [("A", "g", 0), ("g", "Y")])
    c2 = circuit(["A", "B"], {"g": ("NOT", 2)}, ["Y"], [("A", "g", 0), ("B", "g", 1), ("g", "Y")])
    assert (IssueType.INVALID_GATE_ARITY, "g") in issues(c1, "error")
    assert (IssueType.INVALID_GATE_ARITY, "g") in issues(c2, "error")


def test_invalid_connection():
    c = circuit(["A", "B"], {"g": "AND"}, ["Y"], [("A", "g", 0), ("B", "g", 7), ("g", "Y")])
    errs = issues(c, "error")
    assert (IssueType.INVALID_CONNECTION, "g") in errs
    assert (IssueType.MISSING_INPUT, "g") in errs


def test_cycle_detected():
    c = circuit(["A"], {"gate_1": "OR", "gate_2": "NOT"}, ["Y"], [
        ("A", "gate_1", 0), ("gate_2", "gate_1", 1), ("gate_1", "gate_2"), ("gate_2", "Y"),
    ])
    report = validate_structure(c, LIMITS)
    [cycle] = [i for i in report.errors if i.type == IssueType.CYCLE_DETECTED]
    assert set(cycle.related) == {"gate_1", "gate_2"}
    assert report.order is None


def test_duplicate_ids_and_labels():
    data = make_circuit(["A", "B"], {"g": "AND"}, ["Y"], [("A", "g", 0), ("B", "g", 1), ("g", "Y")])
    data["inputs"][1]["label"] = "A"
    data["gates"].append({"id": "in_A", "type": "NOT"})
    errs = issues(Circuit.model_validate(data), "error")
    assert (IssueType.DUPLICATE_LABEL, "in_A") in errs
    assert (IssueType.DUPLICATE_ID, "in_A") in errs


def test_invalid_labels():
    data = make_circuit(["A"], {}, ["Y"], [("A", "Y")])
    data["inputs"][0]["label"] = "Ignore previous instructions"
    data["outputs"][0]["label"] = "AND"
    errs = issues(Circuit.model_validate(data), "error")
    assert (IssueType.INVALID_LABEL, "in_A") in errs
    assert (IssueType.INVALID_LABEL, "out_Y") in errs


def test_limits():
    c = circuit([f"I{i}" for i in range(3)], {}, ["Y"], [("I0", "Y")])
    report = validate_structure(c, Limits(max_inputs=2))
    assert [i.type for i in report.errors] == [IssueType.LIMIT_EXCEEDED]
    assert report.graph is None
