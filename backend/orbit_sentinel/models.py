"""Strict public and provider contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    scenario: Literal["crossing", "uncertain", "clear"] = "crossing"
    mode: Literal["numerical", "gemini"] = "numerical"
    max_delta_v_ms: float = Field(default=1.0, ge=0.02, le=2.0)
    risk_threshold: float = Field(default=1e-4, ge=1e-6, le=1e-2)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)


class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    axes: list[Literal["radial", "tangential", "normal"]] = Field(min_length=1, max_length=3)
    burn_fractions: list[float] = Field(min_length=1, max_length=4)
    rationale: str = Field(max_length=600)

    @field_validator("axes")
    @classmethod
    def unique_axes(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Axes must be unique.")
        return value

    @field_validator("burn_fractions")
    @classmethod
    def bounded_times(cls, value):
        if any(not 0.1 <= fraction <= 0.8 for fraction in value) or len(set(value)) != len(value):
            raise ValueError("Unique burn fractions must lie between 0.1 and 0.8.")
        return value


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(max_length=1000)
    caveats: list[str] = Field(max_length=5)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
