"""Find the stored circuit that a short request ("half adder", "full adder using 74153") asks for.

This is plain, deterministic text matching, never AI: the same words always give the same circuit.
The text is normalised, then compared with each exercise's aliases (see ``app.generator.aliases``).

A circuit matches when every word of one of its aliases appears in the request. The best match is the
alias with the most weight (so "full adder using mux" prefers the multiplexer circuit over the plain
full adder, and "half adder using logic gates" prefers the half adder over "logic gates").

Two strictness levels:

* lenient (demo mode, where the person is choosing a circuit to open): any alias contained in the
  request opens that circuit, and partial matches are offered as suggestions;
* strict (deciding whether live AI text *names* a circuit): the alias must be a distinctive name (at
  least two real words) and cover most of what was typed. "use only NAND gates" and "use a 7476" are
  instructions, not requests for the NAND-gate or counter exercise, so they match nothing.

"X to Y" is kept as one direction-aware word, so "excess-3 to BCD" and "BCD to excess-3" stay different.
"""

import re
from dataclasses import dataclass

from app.generator.aliases import ALIASES
from app.services.golden_repository import GoldenRepository
from app.services.task_repository import TaskRepository

# Filler words that never help identify a circuit. ("and" is NOT filler: "and gate", "and into or".)
STOPWORDS = frozenset(
    "a an the of me please i want need my can you could do how is it build make create design circuit circuits "
    "implement draw generate show give using use with for from in on by bit only".split()
)
# Words that describe the kind of part, not which circuit: they count for little.
WEAK_WORDS = frozenset({"logic", "gate"})

SYNONYMS = {
    "multiplexer": "mux", "multiplexers": "mux", "multiplexor": "mux", "muxes": "mux",
    "demultiplexer": "demux", "adders": "adder", "counters": "counter", "registers": "register",
    "ff": "flipflop", "asynchronous": "async", "synchronous": "sync", "comparators": "comparator",
    "decoders": "decoder", "gates": "gate", "xs3": "excess3", "latches": "latch",
    "converter": "converter", "conversion": "converter", "convert": "converter",
}
STRICT_MIN_WEIGHT = 2.0  # a distinctive name: at least two real words
STRICT_MIN_COVERAGE = 0.6  # ...and most of what was typed
PARTIAL_MIN_FRACTION = 0.6
TITLE_SCORE = 10.0


def normalize(text: str) -> list[str]:
    """Lower-case words with punctuation removed, synonyms unified, "X to Y" merged and filler dropped."""
    text = text.lower()
    text = re.sub(r"flip[\s-]*flops?", "flipflop", text)
    text = re.sub(r"excess[\s-]*3", "excess3", text)  # "excess-3", "excess 3"
    text = re.sub(r"(\d)\s*[:x/]\s*(\d)", r"\1 \2", text)  # 8:1, 4x1, 2/1 -> "8 1"
    text = re.sub(r"(\d)\s+to\s+(\d)", r"\1 \2", text)  # "2 to 1" -> "2 1"
    words = [SYNONYMS.get(w, w) for w in re.findall(r"[a-z]+\d*|\d+", text)]
    merged: list[str] = []
    i = 0
    while i < len(words):
        if i + 2 < len(words) and words[i + 1] == "to":
            merged.append(f"{words[i]}_to_{words[i + 2]}")
            i += 3
        else:
            merged.append(words[i])
            i += 1
    return [w for w in merged if w not in STOPWORDS and w != "to"]


def _weight(words: set[str]) -> float:
    return sum(0.25 if w in WEAK_WORDS else 1.0 for w in words)


@dataclass
class DemoEntry:
    task_id: str
    title: str
    style: str  # "ic" if the stored circuit uses an IC or block, else "gates"
    parts: list[str]


@dataclass
class DemoMatch:
    task_id: str
    title: str
    style: str
    score: float
    phrase: str  # the stored phrase your words matched
    full: bool  # a whole phrase was matched (False: only a suggestion)


BASIC_GATES = {"AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR", "BUFFER", "VCC", "GND"}


class DemoMatcher:
    def __init__(self, tasks: TaskRepository, golden: GoldenRepository):
        self.entries: dict[str, DemoEntry] = {}
        self.phrases: dict[str, list[tuple[str, list[str]]]] = {}
        self.titles: dict[str, list[str]] = {}
        for task in tasks.list():
            stored = golden.get(task.id)
            if stored is None:
                continue  # no stored circuit: nothing to open
            types = sorted({g["type"].upper() for g in stored["circuit"]["gates"]})
            self.entries[task.id] = DemoEntry(task.id, task.title, "gates" if set(types) <= BASIC_GATES else "ic", types)
            self.titles[task.id] = normalize(task.title)
            prepared: list[tuple[str, list[str]]] = []
            seen: set[tuple[str, ...]] = set()
            for text in ALIASES.get(task.id, []):
                words = normalize(text)
                if words and tuple(words) not in seen:
                    seen.add(tuple(words))
                    prepared.append((text, words))
            self.phrases[task.id] = prepared

    def catalog(self) -> list[DemoEntry]:
        return list(self.entries.values())

    def match(self, request: str, limit: int = 4, strict: bool = False) -> list[DemoMatch]:
        """Circuits that fit the request, best first. Whole-phrase matches come before suggestions."""
        words = normalize(request)
        wanted = set(words)
        if not wanted:
            return []
        total = _weight(wanted)
        found: list[DemoMatch] = []
        for task_id, phrases in self.phrases.items():
            best: DemoMatch | None = None

            def consider(score: float, phrase: str, full: bool) -> None:
                nonlocal best
                if best is None or (full, score) > (best.full, best.score):
                    entry = self.entries[task_id]
                    best = DemoMatch(task_id, entry.title, entry.style, round(score, 3), phrase, full)

            if words == self.titles[task_id]:  # the exercise's own title, word for word
                consider(TITLE_SCORE, self.entries[task_id].title, True)
            for text, phrase_words in phrases:
                phrase_set = set(phrase_words)
                if phrase_set <= wanted:
                    weight = _weight(phrase_set)
                    if strict and (weight < STRICT_MIN_WEIGHT or weight / total < STRICT_MIN_COVERAGE):
                        continue
                    consider(weight, text, True)
                elif not strict and len(phrase_set & wanted) >= 2 and len(phrase_set & wanted) / len(phrase_set) >= PARTIAL_MIN_FRACTION:
                    consider(0.8 * len(phrase_set & wanted) / len(phrase_set), text, False)
            if best is not None:
                found.append(best)
        found.sort(key=lambda m: (not m.full, -m.score, m.task_id))
        return found[:limit]

    def best(self, request: str, strict: bool = False) -> DemoMatch | None:
        """The circuit to open for this request, or None when nothing matches a whole phrase."""
        matches = self.match(request, limit=1, strict=strict)
        return matches[0] if matches and matches[0].full else None
