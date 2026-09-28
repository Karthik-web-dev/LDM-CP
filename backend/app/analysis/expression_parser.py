"""Parser for task expressions such as ``(A AND B) OR NOT C`` or ``A & B | !C``.

Only task definitions go through this parser; circuit expressions are generated from the graph.

Precedence, highest first: NOT / postfix ``'``, AND / NAND, XOR / XNOR, OR / NOR.
AND, OR, and XOR chains are flattened (``A AND B AND C`` -> one 3-input AND). NAND, NOR, and
XNOR are not associative, so their chains are left-nested.

Accepted spellings (keywords are case-insensitive):
    AND: AND & && * · ∧     OR: OR | || + ∨     XOR: XOR ^ ⊕
    NOT: NOT ! ~ ¬ (prefix) or ' (postfix, e.g. A')
    NAND, NOR, XNOR: keywords only.  Constants: 0 1
    Implicit AND: adjacent terms, e.g. ``A'B + AB'`` or ``A(B + C)``.

Textbook juxtaposition: a word made only of capital letters is a product of single-letter
variables, so ``A'BC`` is ``A' AND B AND C``. Names containing lowercase letters, digits or ``_``
stay whole (``Cin``, ``S1``, ``B_2``). Names listed in ``known_variables`` are never split.
"""

import re
from dataclasses import dataclass

from app.analysis.boolean_ast import And, BooleanExpression, Const, Nand, NaryOp, Nor, Not, Or, Variable, Xnor, Xor

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
KEYWORDS = {"AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"}

_SYMBOLS = {
    "&&": "AND", "&": "AND", "*": "AND", "·": "AND", "∧": "AND",
    "||": "OR", "|": "OR", "+": "OR", "∨": "OR",
    "^": "XOR", "⊕": "XOR",
    "!": "NOT", "~": "NOT", "¬": "NOT",
    "(": "(", ")": ")", "'": "'",
}
_TOKEN_RE = re.compile(r"\s*(?:(?P<ident>[A-Za-z_][A-Za-z0-9_]*)|(?P<const>[01])(?![0-9])|(?P<sym>&&|\|\||[&*·∧|+∨^⊕!~¬()']))")

_OPS: dict[str, type[NaryOp]] = {"AND": And, "OR": Or, "XOR": Xor, "NAND": Nand, "NOR": Nor, "XNOR": Xnor}
_ASSOCIATIVE = {"AND", "OR", "XOR"}
_TERM_START = {"IDENT", "CONST", "(", "NOT"}
_LETTER_RUN_RE = re.compile(r"^[A-Z]{2,}$")


class ExpressionParseError(ValueError):
    def __init__(self, message: str, position: int):
        self.position = position
        super().__init__(f"{message} (at position {position})")


def is_valid_identifier(name: str) -> bool:
    return bool(IDENTIFIER_RE.match(name)) and name.upper() not in KEYWORDS


@dataclass
class _Token:
    kind: str  # IDENT, CONST, AND, OR, XOR, NAND, NOR, XNOR, NOT, (, ), ', END
    text: str
    pos: int


def _tokenize(source: str, known_variables: frozenset[str] = frozenset()) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(source):
        if source[pos:].strip() == "":
            break
        m = _TOKEN_RE.match(source, pos)
        if not m:
            start = pos + (len(source[pos:]) - len(source[pos:].lstrip()))
            raise ExpressionParseError(f"Unexpected character {source[start]!r}", start)
        start = m.start(m.lastgroup)
        text = m.group(m.lastgroup)
        if m.lastgroup == "ident":
            upper = text.upper()
            if upper in KEYWORDS:
                tokens.append(_Token(upper, text, start))
            elif _LETTER_RUN_RE.match(text) and text not in known_variables:
                # "BC" -> B, C; the parser ANDs adjacent terms.
                tokens.extend(_Token("IDENT", ch, start + i) for i, ch in enumerate(text))
            else:
                tokens.append(_Token("IDENT", text, start))
        elif m.lastgroup == "const":
            tokens.append(_Token("CONST", text, start))
        else:
            tokens.append(_Token(_SYMBOLS[text], text, start))
        pos = m.end()
    tokens.append(_Token("END", "", len(source)))
    return tokens


class _Parser:
    def __init__(self, source: str, known_variables: frozenset[str] = frozenset()):
        self.tokens = _tokenize(source, known_variables)
        self.i = 0

    def peek(self) -> _Token:
        return self.tokens[self.i]

    def take(self) -> _Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def parse(self) -> BooleanExpression:
        if self.peek().kind == "END":
            raise ExpressionParseError("Expression is empty", 0)
        expr = self.binary_level(0)
        tok = self.peek()
        if tok.kind != "END":
            raise ExpressionParseError(f"Unexpected {tok.text!r}", tok.pos)
        return expr

    _LEVELS = [("OR", "NOR"), ("XOR", "XNOR"), ("AND", "NAND")]

    def binary_level(self, level: int) -> BooleanExpression:
        if level == len(self._LEVELS):
            return self.unary()
        ops = self._LEVELS[level]
        left = self.binary_level(level + 1)
        # Collect operands of a flattened associative chain.
        chain_op: str | None = None
        chain: list[BooleanExpression] = [left]
        while self.peek().kind in ops or (ops[0] == "AND" and self.peek().kind in _TERM_START):
            # Adjacent terms ("A B", "A'B", "A(B+C)") are an implicit AND.
            op = self.take().kind if self.peek().kind in ops else "AND"
            right = self.binary_level(level + 1)
            if op in _ASSOCIATIVE and chain_op in (None, op):
                chain_op = op
                chain.append(right)
                continue
            current = self._close(chain_op, chain)
            if op in _ASSOCIATIVE:
                chain_op, chain = op, [current, right]
            else:
                chain_op, chain = None, [_OPS[op]((current, right))]
        return self._close(chain_op, chain)

    @staticmethod
    def _close(op: str | None, chain: list[BooleanExpression]) -> BooleanExpression:
        if op is None:
            return chain[0]
        return _OPS[op](tuple(chain))

    def unary(self) -> BooleanExpression:
        if self.peek().kind == "NOT":
            self.take()
            return Not(self.unary())
        expr = self.primary()
        while self.peek().kind == "'":
            self.take()
            expr = Not(expr)
        return expr

    def primary(self) -> BooleanExpression:
        tok = self.take()
        if tok.kind == "IDENT":
            return Variable(tok.text)
        if tok.kind == "CONST":
            return Const(tok.text == "1")
        if tok.kind == "(":
            expr = self.binary_level(0)
            close = self.take()
            if close.kind != ")":
                raise ExpressionParseError("Expected ')'", close.pos)
            return expr
        if tok.kind == "END":
            raise ExpressionParseError("Unexpected end of expression", tok.pos)
        raise ExpressionParseError(f"Unexpected {tok.text!r}", tok.pos)


def parse_expression(source: str, known_variables: set[str] | list[str] | None = None) -> BooleanExpression:
    """Parse ``source``. ``known_variables`` (e.g. a task's declared inputs) are never split into letters."""
    return _Parser(source, frozenset(known_variables or ())).parse()
