"""Karnaugh maps, computed deterministically from a truth-table column.

Layout: the first half of the variables (rounded down) index rows, the rest index columns, each
in Gray-code order so adjacent cells differ in one variable. Groups are the implicants chosen by
the Quine-McCluskey cover in ``minimize``, so the map and the simplified equation always agree.
"""

from app.analysis.boolean_ast import render_expression
from app.analysis.minimize import Implicant, implicant_expression, implicant_rows, minimal_cover
from app.models.analysis import KMap, KMapCell, KMapGroup, TruthTable

MAX_KMAP_VARIABLES = 4


class KMapError(ValueError):
    pass


def gray_code(bits: int) -> list[int]:
    return [i ^ (i >> 1) for i in range(1 << bits)]


def _bits_label(value: int, width: int) -> str:
    return format(value, f"0{width}b") if width else ""


def term_text(variables: list[str], imp: Implicant) -> str:
    """Textbook product notation: A'B, or Cin'·A when any name is longer than one letter."""
    n = len(variables)
    bits, mask = imp
    literals = []
    for j, name in enumerate(variables):
        bit = 1 << (n - 1 - j)
        if not mask & bit:
            literals.append(name if bits & bit else name + "'")
    if not literals:
        return "1"
    sep = "" if all(len(v) == 1 for v in variables) else "·"
    return sep.join(literals)


def build_kmap(table: TruthTable, output: str) -> KMap:
    variables = table.variables
    n = len(variables)
    if n == 0 or n > MAX_KMAP_VARIABLES:
        raise KMapError(f"K-maps are shown for 1 to {MAX_KMAP_VARIABLES} inputs; this function has {n}.")
    col = table.outputs.index(output)
    values = [row.outputs[col] for row in table.rows]  # index = truth-table row (first variable is MSB)
    ones = {i for i, v in enumerate(values) if v == 1}
    dont_cares = {i for i, v in enumerate(values) if v is None}

    row_bits = n // 2
    col_bits = n - row_bits
    row_order, col_order = gray_code(row_bits), gray_code(col_bits)
    position: dict[int, tuple[int, int]] = {}
    cells: list[list[KMapCell]] = []
    for r, rv in enumerate(row_order):
        line = []
        for c, cv in enumerate(col_order):
            minterm = (rv << col_bits) | cv
            position[minterm] = (r, c)
            line.append(KMapCell(row=r, col=c, minterm=minterm, value=values[minterm]))
        cells.append(line)

    cover = minimal_cover(n, ones, dont_cares)
    groups = [
        KMapGroup(
            term=term_text(variables, imp),
            expression=render_expression(implicant_expression(variables, imp)),
            minterms=implicant_rows(n, imp),
            cells=[list(position[m]) for m in implicant_rows(n, imp)],
        )
        for imp in cover
    ]
    return KMap(
        output=output,
        variables=variables,
        row_variables=variables[:row_bits],
        col_variables=variables[row_bits:],
        row_labels=[_bits_label(v, row_bits) for v in row_order],
        col_labels=[_bits_label(v, col_bits) for v in col_order],
        cells=cells,
        groups=groups,
        minimal_sop=" + ".join(g.term for g in groups) if groups else "0",
        minterms=sorted(ones),
        dont_cares=sorted(dont_cares),
    )
