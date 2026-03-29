"""Pydantic schemas for card API."""

from pydantic import BaseModel, Field

from core.schemas.common import ContentType


class CardMappingCreate(BaseModel):
    card_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    content_type: ContentType
    content_path: str = Field(min_length=1)
    cover_path: str | None = None


class CardMappingUpdate(BaseModel):
    name: str | None = None
    content_type: ContentType | None = None
    content_path: str | None = None
    cover_path: str | None = None


class CardMappingResponse(BaseModel):
    card_id: str
    name: str
    content_type: ContentType
    content_path: str
    cover_path: str | None
    resume_position: float
