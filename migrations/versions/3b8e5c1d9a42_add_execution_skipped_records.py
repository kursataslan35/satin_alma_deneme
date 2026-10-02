"""record source values that controls could not parse

Revision ID: 3b8e5c1d9a42
Revises: 86b815857fd1
"""
from alembic import op
import sqlalchemy as sa


revision = "3b8e5c1d9a42"
down_revision = "86b815857fd1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("rule_executions") as batch_op:
        batch_op.add_column(sa.Column("skipped_records", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("skipped_examples", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("rule_executions") as batch_op:
        batch_op.drop_column("skipped_examples")
        batch_op.drop_column("skipped_records")
