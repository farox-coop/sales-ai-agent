import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, Enum, ForeignKey, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


class LeadStatus(str, enum.Enum):
    activo = "activo"
    completado = "completado"
    abandonado = "abandonado"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    tool_call = "tool_call"


class DocumentType(str, enum.Enum):
    propuesta = "propuesta"
    cv = "cv"
    presupuesto = "presupuesto"
    otro = "otro"


class DocumentStatus(str, enum.Enum):
    activo = "activo"
    archivado = "archivado"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    empresa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estado: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus, name="lead_status"), default=LeadStatus.activo)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nivel_madurez: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resumen_diagnostico: Mapped[str | None] = mapped_column(Text, nullable=True)
    recordatorio_enviado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    interacciones: Mapped[list["Interaction"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class Interaction(Base):
    __tablename__ = "interacciones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=True)
    rol: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"))
    contenido: Mapped[str] = mapped_column(Text)
    pregunta_numero: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["Lead"] = relationship(back_populates="interacciones")


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drive_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="document_type"), default=DocumentType.otro)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    ultima_sincro: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status"), default=DocumentStatus.activo)
