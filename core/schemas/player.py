"""Pydantic schemas for player API."""

from pydantic import BaseModel, Field


class PlayerStateResponse(BaseModel):
    state: str
    volume: int
    current_track: str
    current_album: str
    elapsed: float
    duration: float
    playlist_length: int
    playlist_position: int


class VolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=100)


class SeekRequest(BaseModel):
    position: float = Field(ge=0)
