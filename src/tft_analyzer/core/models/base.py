from pydantic import BaseModel, ConfigDict, Field


class SchemaModel(BaseModel):
    """Base class for versioned immutable domain contracts."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: int = Field(default=1, ge=1)
