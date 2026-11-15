import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.candidate import Candidate
from app.models.user import User, UserRole
from app.schemas.candidate import CandidateCreate, CandidateOut

router = APIRouter(prefix="/candidates", tags=["candidates"])

RECRUITING_ROLES = (UserRole.ADMIN, UserRole.RECRUITER, UserRole.HIRING_MANAGER)


@router.get("", response_model=list[CandidateOut])
async def list_candidates(
    db: AsyncSession = Depends(get_db), _: User = Depends(require_roles(*RECRUITING_ROLES))
) -> list[Candidate]:
    result = await db.execute(select(Candidate).order_by(Candidate.created_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    payload: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(*RECRUITING_ROLES)),
) -> Candidate:
    existing = await db.execute(select(Candidate).where(Candidate.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Candidate with this email already exists")

    candidate = Candidate(**payload.model_dump())
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(*RECRUITING_ROLES)),
) -> Candidate:
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate
