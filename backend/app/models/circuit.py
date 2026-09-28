"""Normalized, versioned circuit representation (see CIRCUIT_FORMAT.md).

This schema is independent of any editor implementation. Semantics are carried only by ids,
gate types, and connections; positions are optional display metadata.
"""

from pydantic import BaseModel, ConfigDict, Field

ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class CircuitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=64)
    position: Position | None = None


class Gate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_PATTERN)
    type: str = Field(min_length=1, max_length=32)
    # Number of input pins. When omitted, the gate type's default arity is used.
    inputs: int | None = Field(default=None, ge=0, le=64)
    position: Position | None = None


class CircuitOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=64)
    position: Position | None = None


class Connection(BaseModel):
    """A directed edge from a driver (input or gate output) to a sink pin (gate input or output)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    from_: str = Field(alias="from", pattern=ID_PATTERN)
    to: str = Field(pattern=ID_PATTERN)
    # Which input pin of the target gate. May be omitted for single-input targets.
    input_index: int | None = Field(default=None, ge=0)


class Circuit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, le=1)
    inputs: list[CircuitInput] = Field(default_factory=list)
    gates: list[Gate] = Field(default_factory=list)
    outputs: list[CircuitOutput] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
