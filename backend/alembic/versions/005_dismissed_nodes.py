"""dismissed_nodes — operator-hidden ghost certnames

Revision ID: 005_dismissed_nodes
Revises: 004_cluster_secrets
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa

revision = "005_dismissed_nodes"
down_revision = "004_cluster_secrets"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "dismissed_nodes" in insp.get_table_names():
        return
    op.create_table(
        "dismissed_nodes",
        sa.Column("certname", sa.String(255), primary_key=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("reason", sa.String(255), nullable=False, server_default="ghost"),
    )


def downgrade():
    op.drop_table("dismissed_nodes")
