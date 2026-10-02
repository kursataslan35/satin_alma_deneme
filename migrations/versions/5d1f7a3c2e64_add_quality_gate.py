"""quality check severity and pre-control quality gate results

Revision ID: 5d1f7a3c2e64
Revises: 3b8e5c1d9a42
"""
from alembic import op
import sqlalchemy as sa


revision = "5d1f7a3c2e64"
down_revision = "3b8e5c1d9a42"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("quality_checks") as batch_op:
        batch_op.add_column(sa.Column("severity", sa.String(length=16), nullable=False,
                                      server_default="warning"))
    with op.batch_alter_table("rule_executions") as batch_op:
        batch_op.add_column(sa.Column("quality_status", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("quality_summary", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("rule_executions") as batch_op:
        batch_op.drop_column("quality_summary")
        batch_op.drop_column("quality_status")
    with op.batch_alter_table("quality_checks") as batch_op:
        batch_op.drop_column("severity")
