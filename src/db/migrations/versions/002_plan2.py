"""Plan 2 — columnas nuevas + tabla documentos

Revision ID: 002
Revises: 001
Create Date: 2026-07-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Leads: nuevas columnas ---
    op.add_column("leads", sa.Column("nivel_madurez", sa.String(50), nullable=True))
    op.add_column("leads", sa.Column("extra_data", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("leads", sa.Column("resumen_diagnostico", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("recordatorio_enviado", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    # --- Interacciones: nuevas columnas ---
    op.add_column("interacciones", sa.Column("tool_name", sa.String(255), nullable=True))
    op.add_column("interacciones", sa.Column("tool_result", sa.Text(), nullable=True))

    # --- MessageRole: agregar tool_call al enum ---
    op.execute("ALTER TYPE message_role ADD VALUE IF NOT EXISTS 'tool_call'")

    # --- Documentos: tabla nueva ---
    op.create_table(
        "documentos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("drive_id", sa.String(255), nullable=False),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum("propuesta", "cv", "presupuesto", "otro", name="document_type"),
            nullable=False,
        ),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("ultima_sincro", sa.DateTime(), nullable=False),
        sa.Column("chunks_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("activo", "archivado", name="document_status"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("drive_id"),
    )


def downgrade() -> None:
    op.drop_table("documentos")
    op.execute("DROP TYPE IF EXISTS document_status")
    op.execute("DROP TYPE IF EXISTS document_type")

    op.drop_column("interacciones", "tool_result")
    op.drop_column("interacciones", "tool_name")

    op.drop_column("leads", "recordatorio_enviado")
    op.drop_column("leads", "resumen_diagnostico")
    op.drop_column("leads", "extra_data")
    op.drop_column("leads", "nivel_madurez")
