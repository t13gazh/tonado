"""Card management API routes."""

from fastapi import APIRouter, Depends, HTTPException

from core.dependencies import get_card_service
from core.schemas.card import CardMappingCreate, CardMappingResponse, CardMappingUpdate
from core.services.card_service import CardMapping, CardService

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.get("/", response_model=list[CardMappingResponse])
async def list_cards(svc: CardService = Depends(get_card_service)) -> list[dict]:
    mappings = await svc.list_mappings()
    return [m.to_dict() for m in mappings]


@router.get("/{card_id}", response_model=CardMappingResponse)
async def get_card(card_id: str, svc: CardService = Depends(get_card_service)) -> dict:
    mapping = await svc.get_mapping(card_id)
    if mapping is None:
        raise HTTPException(404, "Card not found")
    return mapping.to_dict()


@router.post("/", response_model=CardMappingResponse, status_code=201)
async def create_card(req: CardMappingCreate, svc: CardService = Depends(get_card_service)) -> dict:
    mapping = CardMapping(
        card_id=req.card_id,
        name=req.name,
        content_type=req.content_type,
        content_path=req.content_path,
        cover_path=req.cover_path,
    )
    await svc.set_mapping(mapping)
    return mapping.to_dict()


@router.put("/{card_id}", response_model=CardMappingResponse)
async def update_card(card_id: str, req: CardMappingUpdate, svc: CardService = Depends(get_card_service)) -> dict:
    existing = await svc.get_mapping(card_id)
    if existing is None:
        raise HTTPException(404, "Card not found")

    if req.name is not None:
        existing.name = req.name
    if req.content_type is not None:
        existing.content_type = req.content_type
    if req.content_path is not None:
        existing.content_path = req.content_path
    if req.cover_path is not None:
        existing.cover_path = req.cover_path

    await svc.set_mapping(existing)
    return existing.to_dict()


@router.delete("/{card_id}")
async def delete_card(card_id: str, svc: CardService = Depends(get_card_service)) -> dict:
    deleted = await svc.delete_mapping(card_id)
    if not deleted:
        raise HTTPException(404, "Card not found")
    return {"status": "ok"}


@router.get("/scan/wait")
async def wait_for_scan(
    timeout: float = 30.0,
    new_only: bool = False,
    svc: CardService = Depends(get_card_service),
) -> dict:
    """Wait for a card to be scanned. Used by the card wizard.

    Long-polls until a card is detected or timeout is reached.
    new_only=true: ignore card already on reader, wait for a new placement.
    """
    timeout = min(timeout, 60.0)  # Cap at 60s
    card_id = await svc.wait_for_scan(
        timeout=timeout, new_only=new_only,
    )
    if card_id is None:
        return {"scanned": False, "card_id": None}

    # Check if card already has a mapping
    existing = await svc.get_mapping(card_id)
    return {
        "scanned": True,
        "card_id": card_id,
        "has_mapping": existing is not None,
        "mapping": existing.to_dict() if existing else None,
    }
