"""Agrega el estado contacto_solicitado a los leads.

Revision ID: 003
Revises: 002
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE lead_status ADD VALUE IF NOT EXISTS 'contacto_solicitado'"
    )


def downgrade() -> None:
    # PostgreSQL no permite eliminar un valor de un enum de forma directa.
    # El estado queda disponible también al volver a una revisión anterior.
    pass
