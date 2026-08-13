"""add role column to api_tokens for service token scoping

Revision ID: 003
Revises: 002
Create Date: 2026-06-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_add_role_to_api_tokens'
down_revision = '002_add_api_tokens'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "api_tokens" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("api_tokens")}
    if "role" in cols:
        return
    op.add_column('api_tokens', sa.Column('role', sa.String(50), nullable=False, server_default='operator'))


def downgrade():
    op.drop_column('api_tokens', 'role')
