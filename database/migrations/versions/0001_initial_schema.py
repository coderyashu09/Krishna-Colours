"""Initial database schema for Krishna Colour

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from database.models import Base
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from database.models import Base
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
