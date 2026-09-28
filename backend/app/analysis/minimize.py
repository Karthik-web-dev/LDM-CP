"""Truth table -> simplified sum-of-products, via Quine-McCluskey.

Used to show a truth-table target as a readable equation. Prime implicants are exact; the cover
takes essential primes first and then picks greedily, so the result is always correct but not
guaranteed to be the absolute minimum for every function.
"""

from app.analysis.boolean_ast import And, BooleanExpression, Const, Not, Or, Variable

# An implicant is (bits, mask): mask bits set to 1 are "don't care" positions (a dash).
Implicant = tuple[int, int]


def _covers(imp: Implicant, row: int) -> bool:
    bits, mask = imp
    return (row & ~mask) == (bits & ~mask)


def prime_implicants(n_vars: int, terms: set[int]) -> list[Implicant]:
    current = {(t, 0) for t in terms}
    primes: set[Implicant] = set()
    while current:
        merged: set[Implicant] = set()
        used: set[Implicant] = set()
        items = sorted(current)
        for i, (b1, m1) in enumerate(items):
            for b2, m2 in items[i + 1:]:
                if m1 != m2:
                    continue
                diff = (b1 ^ b2) & ~m1
                if diff and diff & (diff - 1) == 0:  # exactly one differing bit
                    merged.add((b1 & ~diff, m1 | diff))
                    used.add((b1, m1))
                    used.add((b2, m2))
        primes |= current - used
        current = merged
    full = (1 << n_vars) - 1
    return sorted(primes, key=lambda p: (-bin(p[1] & full).count("1"), p))


def implicant_rows(n_vars: int, imp: Implicant) -> list[int]:
    """All truth-table rows covered by an implicant."""
    return [r for r in range(1 << n_vars) if _covers(imp, r)]


def minimal_cover(n_vars: int, ones: set[int], dont_cares: set[int] = frozenset()) -> list[Implicant]:
    """Implicants whose OR is 1 on ``ones`` and 0 off ``ones | dont_cares``.

    Empty list = constant 0; ``[(0, full_mask)]`` = constant 1. Order is deterministic.
    """
    if not ones:
        return []
    if len(ones | dont_cares) == 1 << n_vars:
        return [(0, (1 << n_vars) - 1)]
    n = n_vars

    primes = prime_implicants(n, ones | set(dont_cares))
    uncovered = set(ones)
    chosen: list[Implicant] = []

    # Essential primes: the only prime covering some required row.
    for row in sorted(ones):
        covering = [p for p in primes if _covers(p, row)]
        if len(covering) == 1 and covering[0] not in chosen:
            chosen.append(covering[0])
    for p in chosen:
        uncovered -= {r for r in uncovered if _covers(p, r)}

    # Greedy cover for the rest: most new rows, then fewest literals (primes are pre-sorted).
    while uncovered:
        best = max(primes, key=lambda p: sum(_covers(p, r) for r in uncovered))
        chosen.append(best)
        uncovered -= {r for r in uncovered if _covers(best, r)}

    # Deterministic order: by the row pattern, so output is stable.
    return sorted(chosen, key=lambda p: (p[0] & ~p[1], p[1]))


def implicant_expression(variables: list[str], imp: Implicant) -> BooleanExpression:
    n = len(variables)
    bits, mask = imp
    literals: list[BooleanExpression] = []
    for j, name in enumerate(variables):
        bit = 1 << (n - 1 - j)
        if mask & bit:
            continue
        literals.append(Variable(name) if bits & bit else Not(Variable(name)))
    if not literals:
        return Const(True)
    return literals[0] if len(literals) == 1 else And(tuple(literals))


def minimize_sop(variables: list[str], ones: set[int], dont_cares: set[int] = frozenset()) -> BooleanExpression:
    """Simplified SOP for the function that is 1 on ``ones`` and free on ``dont_cares``.

    Row index ``r`` uses the truth-table convention: the first variable is the most significant bit.
    """
    cover = minimal_cover(len(variables), ones, dont_cares)
    if not cover:
        return Const(False)
    terms = [implicant_expression(variables, p) for p in cover]
    return terms[0] if len(terms) == 1 else Or(tuple(terms))
