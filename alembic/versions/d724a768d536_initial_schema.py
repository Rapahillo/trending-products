"""initial schema

Revision ID: d724a768d536
Revises:
Create Date: 2026-05-16 17:53:44.637601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY


# revision identifiers, used by Alembic.
revision: str = 'd724a768d536'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(320), unique=True, index=True, nullable=False),
        sa.Column('hashed_password', sa.String(200), nullable=False),
        sa.Column('subscription_tier', sa.Enum('free', 'basic', 'pro', 'enterprise', name='subscriptiontier'), nullable=False),
        sa.Column('region_preference', sa.String(10), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'product_cards',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('category', sa.String(200), nullable=True),
        sa.Column('image_urls', ARRAY(sa.String), nullable=False),
        sa.Column('trend_score', sa.Integer, default=0, index=True, nullable=False),
        sa.Column('trend_velocity', sa.Enum('accelerating', 'stable', 'decelerating', name='trendvelocity'), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('regions', ARRAY(sa.String), index=True, nullable=False),
        sa.Column('status', sa.Enum('trending', 'declining', 'expired', name='productstatus'), nullable=False),
        sa.Column('tiktok_data', JSONB, nullable=False),
        sa.Column('supplier_data', JSONB, nullable=False),
        sa.Column('competition', JSONB, nullable=False),
        sa.Column('pricing', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'collection_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Enum('success', 'partial', 'failed', name='collectionstatus'), nullable=False),
        sa.Column('items_collected', sa.Integer, default=0, nullable=False),
        sa.Column('errors', JSONB, nullable=False),
    )

    op.create_table(
        'score_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('product_card_id', UUID(as_uuid=True), sa.ForeignKey('product_cards.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('trend_score', sa.Integer, nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'api_keys',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('key_hash', sa.String(200), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('rate_limit', sa.Integer, default=1000, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('api_keys')
    op.drop_table('score_history')
    op.drop_table('collection_runs')
    op.drop_table('product_cards')
    op.drop_table('users')
    op.execute('DROP TYPE IF EXISTS subscriptiontier')
    op.execute('DROP TYPE IF EXISTS trendvelocity')
    op.execute('DROP TYPE IF EXISTS productstatus')
    op.execute('DROP TYPE IF EXISTS collectionstatus')
