"""Pydantic schemas for card API."""

from pydantic import BaseModel, Field


class CardMappingCreate(BaseModel):
    card_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    content_type: str = Field(pattern=r"^(folder|stream|podcast|command)$")
    content_path: str = Field(min_length=1)
    cover_path: str | None = None


class CardMappingUpdate(BaseModel):
    name: str | None = None
    content_type: str | None = Field(default=None, pattern=r"^(folder|stream|podcast|command)$")
    content_path: str | None = None
    cover_path: str | None = None


class CardMappingResponse(BaseModel):
    card_id: str
    name: str
    content_type: str
    content_path: str
    cover_path: str | None
    resume_position: float
