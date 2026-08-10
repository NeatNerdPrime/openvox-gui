"""cluster_secrets table for shared clustered GUI credentials

Revision ID: 004_cluster_secrets
Revises: 003_add_role_to_api_tokens
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa

revision = "004_cluster_secrets"
down_revision = "003_add_role_to_api_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cluster_secrets",
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column("value_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
    )


def downgrade():
    op.drop_table("cluster_secrets")
