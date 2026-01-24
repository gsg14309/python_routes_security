from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.hr import PerformanceReview
from app.schemas.hr import PerformanceReviewOut

router = APIRouter(tags=["performance_reviews"])


@router.get("/performance-reviews", response_model=list[PerformanceReviewOut])
def list_performance_reviews(db: Session = Depends(get_db)) -> list[PerformanceReview]:
    return list(db.scalars(select(PerformanceReview).order_by(PerformanceReview.id)).all())

