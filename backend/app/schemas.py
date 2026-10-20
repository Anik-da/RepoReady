"""Request schemas kept separate from route implementation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GitScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2_048)
    ref: str | None = Field(default=None, max_length=200)
