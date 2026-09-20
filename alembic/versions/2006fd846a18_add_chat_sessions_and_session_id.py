"""add_chat_sessions_and_session_id

Revision ID: 2006fd846a18
Revises: 066b6cae91da
Create Date: 2026-09-19 19:49:50.683920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2006fd846a18'
down_revision: Union[str, Sequence[str], None] = '066b6cae91da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('chat_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_sessions_id'), 'chat_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_chat_sessions_session_id'), 'chat_sessions', ['session_id'], unique=True)
    op.add_column('messages', sa.Column('session_id', sa.String(), nullable=True))
    op.create_foreign_key(None, 'messages', 'chat_sessions', ['session_id'], ['session_id'], ondelete='CASCADE')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, 'messages', type_='foreignkey')
    op.drop_column('messages', 'session_id')
    op.drop_index(op.f('ix_chat_sessions_session_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_id'), table_name='chat_sessions')
    op.drop_table('chat_sessions')
