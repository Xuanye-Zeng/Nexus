"""change resume_sections.embedding to 768-dim

Revision ID: ccda0b64e306
Revises: 86c3bb0cf61a
Create Date: 2026-05-29 22:25:10.473775

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ccda0b64e306'
down_revision: Union[str, Sequence[str], None] = '86c3bb0cf61a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Switch embedding column from vector(1536) to vector(768) by drop+add.
    Safe because the table has no production data yet."""
    op.drop_column('resume_sections', 'embedding')
    op.add_column(
        'resume_sections',
        sa.Column('embedding', pgvector.sqlalchemy.Vector(768), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('resume_sections', 'embedding')
    op.add_column(
        'resume_sections',
        sa.Column('embedding', pgvector.sqlalchemy.Vector(1536), nullable=True),
    )
