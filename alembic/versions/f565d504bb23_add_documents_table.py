"""add documents table

Revision ID: f565d504bb23
Revises: dc01bac4eb77
Create Date: 2026-02-19 17:32:06.449681

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f565d504bb23'
down_revision: Union[str, Sequence[str], None] = 'dc01bac4eb77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('documents',
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('conversation_id', sa.String(length=36), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('file_type', sa.String(length=10), nullable=False),
    sa.Column('file_size_bytes', sa.Integer(), nullable=False),
    sa.Column('char_count', sa.Integer(), nullable=False),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('entities_detected', sa.Integer(), nullable=False),
    sa.Column('was_truncated', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documents_organization_id'), ['organization_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documents_organization_id'))

    op.drop_table('documents')
