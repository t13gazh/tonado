"""Card management API routes."""

from fastapi import APIRouter, HTTPException

from core.schemas.card import CardMappingCreate, CardMappingResponse, CardMappingUpdate
from core.services.card_service import CardMapping, CardService

router = APIRouter(prefix="/api/cards", tags=["cards"])

_card_service: CardService | None = None


def init(card_service: CardService) -> None:
    global _card_service
    _card_service = card_service


def _get_service() -> CardService:
    if _card_service is None:
        raise HTTPException(503, "Card service not available")
    return _card_service


@router.get("/", response_model=list[CardMappingResponse])
async def list_cards() -> list[dict]:
    mappings = await _get_service().list_mappings()
    return [m.to_dict() for m in mappings]


@router.get("/{card_id}", response_model=CardMappingResponse)
async def get_card(card_id: str) -> dict:
    mapping = await _get_service().get_mapping(card_id)
    if mapping is None:
        raise HTTPException(404, "Karte nicht gefunden")
    return mapping.to_dict()


@router.post("/", response_model=CardMappingResponse, status_code=201)
async def create_card(req: CardMappingCreate) -> dict:
    mapping = CardMapping(
        card_id=req.card_id,
        name=req.name,
        content_type=req.content_type,
        content_path=req.content_path,
        cover_path=req.cover_path,
    )
    await _get_service().set_mapping(mapping)
    return mapping.to_dict()


@router.put("/{card_id}", response_model=CardMappingResponse)
async def update_card(card_id: str, req: CardMappingUpdate) -> dict:
    existing = await _get_service().get_mapping(card_id)
    if existing is None:
        raise HTTPException(404, "Karte nicht gefunden")

    if req.name is not None:
        existing.name = req.name
    if req.content_type is not None:
        existing.content_type = req.content_type
    if req.content_path is not None:
        existing.content_path = req.content_path
    if req.cover_path is not None:
        existing.cover_path = req.cover_path

    await _get_service().set_mapping(existing)
    return existing.to_dict()


@router.delete("/{card_id}")
async def delete_card(card_id: str) -> dict:
    deleted = await _get_service().delete_mapping(card_id)
    if not deleted:
        raise HTTPException(404, "Karte nicht gefunden")
    return {"status": "ok"}
