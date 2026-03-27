"""Pydantic schemas for config API."""

from typing import Any

from pydantic import BaseModel, Field


class ConfigValueResponse(BaseModel):
    key: str
    value: Any


class ConfigSetRequest(BaseModel):
    key: str = Field(min_length=1)
    value: Any
