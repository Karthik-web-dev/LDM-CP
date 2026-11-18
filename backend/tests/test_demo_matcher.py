"""Demo mode: free-text requests open the right stored circuit, deterministically."""

from collections import defaultdict

import pytest
from fastapi.testclient import TestClient

from app.generator.aliases import ALIASES
from app.main import app
from app.services.demo_matcher import DemoMatcher, normalize
from app.services.golden_repository import GoldenRepository
from app.services.task_repository import TaskRepository


@pytest.fixture(scope="module")
def matcher() -> DemoMatcher:
    return DemoMatcher(TaskRepository(), GoldenRepository())


@pytest.mark.parametrize(
    "request_text,expected",
    [
        ("half adder", "half_adder"),
        ("Half Adder", "half_adder"),
        ("build me a half adder", "half_adder"),
        ("please design a half-adder circuit", "half_adder"),
        ("full adder", "full_adder"),
        ("full adder using mux", "full_adder_mux_74153"),
        ("full adder using 8:1 multiplexer", "full_adder_mux_74153"),
        ("full adder with 74153", "full_adder_mux_74153"),
        ("2:1 mux", "mux_2to1"),
        ("2 to 1 multiplexer", "mux_2to1"),
        ("excess-3 to BCD", "excess3_to_bcd"),
        ("convert excess 3 to bcd", "excess3_to_bcd"),
        ("bcd to excess-3 code converter", "bcd_to_excess3"),
        ("2 bit comparator using decoder", "comparator_2bit_74138"),
        ("comparator using 74138", "comparator_2bit_74138"),
        ("asynchronous up counter", "async_up_counter_2bit"),
        ("ripple counter using jk flip flop", "async_up_counter_2bit"),
        ("asynchronous down counter", "async_down_counter_2bit"),
        ("synchronous up/down counter", "sync_updown_counter_2bit"),
        ("4 bit shift register", "shift_register_4bit"),
        ("shift register using d flip-flops", "shift_register_4bit"),
        ("verify the logic gates", "gates_verification"),
        ("simplify using boolean algebra", "boolean_simplification"),
        ("majority of three", "majority_3"),
        ("nand using and and not", "nand_from_basics"),
    ],
)
def test_natural_requests_open_the_expected_circuit(matcher, request_text, expected):
    best = matcher.best(request_text)
    assert best is not None and best.task_id == expected, (request_text, best)


def test_direction_matters_for_code_converters(matcher):
    assert matcher.best("excess 3 to bcd").task_id == "excess3_to_bcd"
    assert matcher.best("bcd to excess 3").task_id == "bcd_to_excess3"
    assert normalize("bcd to excess-3") != normalize("excess-3 to bcd")


def test_every_exercise_is_found_by_its_title_and_every_alias(matcher):
    for task in TaskRepository().list():
        for text in [task.title, *ALIASES.get(task.id, [])]:
            best = matcher.best(text)
            assert best is not None and best.task_id == task.id, f"{text!r} should open {task.id}, got {best}"


def test_no_phrase_belongs_to_two_exercises():
    owners = defaultdict(set)
    for task_id, phrases in ALIASES.items():
        for phrase in phrases:
            owners[tuple(normalize(phrase))].add(task_id)
    clashes = {k: v for k, v in owners.items() if len(v) > 1}
    assert not clashes, clashes


def test_the_prompt_that_showed_the_wrong_circuit(matcher):
    """"sr flip flop using nand gates" once opened the NAND-gate exercise because of the words "nand gate"."""
    request = "sr flip flop using nand gates"
    for strict in (False, True):
        best = matcher.best(request, strict=strict)
        assert best is not None and best.task_id == "sr_flipflop_nand", (strict, best)
    assert matcher.best("sr latch using nand gates", strict=True).task_id == "sr_latch_nand"


@pytest.mark.parametrize(
    "instruction",
    ["use only NAND gates", "use a 7476 and tie the unused pins to VCC", "use as few gates as possible", "use a mux", "add the carry output", "fix the wiring"],
)
def test_instructions_are_not_mistaken_for_circuit_names(matcher, instruction):
    """In strict mode (deciding whether live AI text names a circuit) a part or number alone is not a name."""
    assert matcher.best(instruction, strict=True) is None


@pytest.mark.parametrize(
    "request_text,expected",
    [
        ("build half adder using logic gates", "half_adder"),
        ("full adder using 74153", "full_adder_mux_74153"),
        ("a 4 bit shift register", "shift_register_4bit"),
        ("2 bit comparator using decoder", "comparator_2bit_74138"),
    ],
)
def test_strict_mode_still_accepts_clear_circuit_names(matcher, request_text, expected):
    assert matcher.best(request_text, strict=True).task_id == expected


def test_unknown_requests_open_nothing_but_may_suggest(matcher):
    assert matcher.best("quantum teleporter") is None
    assert matcher.best("") is None
    assert matcher.best("the") is None


def test_matching_is_deterministic(matcher):
    first = [m.task_id for m in matcher.match("adder")]
    assert first == [m.task_id for m in matcher.match("adder")]


def test_catalog_says_whether_a_circuit_uses_an_ic(matcher):
    styles = {e.task_id: e.style for e in matcher.catalog()}
    assert styles["half_adder"] == "gates"
    assert styles["full_adder_mux_74153"] == "ic"
    assert styles["shift_register_4bit"] == "ic"
    assert set(styles) == {t.id for t in TaskRepository().list()}


def test_endpoints():
    client = TestClient(app)
    hit = client.post("/api/v1/demo/match", json={"prompt": "half adder"}).json()
    assert hit["best"]["task_id"] == "half_adder" and hit["best"]["style"] == "gates"
    miss = client.post("/api/v1/demo/match", json={"prompt": "quantum teleporter"}).json()
    assert miss["best"] is None
    instruction = client.post("/api/v1/demo/match", json={"prompt": "use only NAND gates", "strict": True}).json()
    assert instruction["best"] is None
    assert client.post("/api/v1/demo/match", json={"prompt": "use only NAND gates"}).json()["best"]["task_id"] == "nand_from_basics"
    catalog = client.get("/api/v1/demo/catalog").json()
    assert {"task_id", "title", "style", "parts"} <= set(catalog[0])
    assert client.post("/api/v1/demo/match", json={"prompt": "x" * 400}).status_code == 422
