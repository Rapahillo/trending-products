import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class TrendVelocity(str, enum.Enum):
    accelerating = "accelerating"
    stable = "stable"
    decelerating = "decelerating"


class ProductStatus(str, enum.Enum):
    trending = "trending"
    declining = "declining"
    expired = "expired"


class ProductCard(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "product_cards"

    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(200))
    image_urls: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    trend_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    trend_velocity: Mapped[TrendVelocity] = mapped_column(
        Enum(TrendVelocity), default=TrendVelocity.stable
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    regions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, index=True)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus), default=ProductStatus.trending, index=True
    )
    tiktok_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    supplier_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    competition: Mapped[dict] = mapped_column(JSONB, default=dict)
    pricing: Mapped[dict] = mapped_column(JSONB, default=dict)

    score_history: Mapped[list["ScoreHistory"]] = relationship(back_populates="product_card")
