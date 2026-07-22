import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Lead, Interaction, Documento, MessageRole, LeadStatus, DocumentStatus


async def get_or_create_lead(session: AsyncSession, session_id: str) -> Lead:
    result = await session.execute(select(Lead).where(Lead.session_id == session_id))
    lead = result.scalar_one_or_none()
    if lead is None:
        lead = Lead(session_id=session_id)
        session.add(lead)
        await session.commit()
        await session.refresh(lead)
    return lead


async def save_interaction(
    session: AsyncSession,
    lead_id: uuid.UUID,
    rol: MessageRole,
    contenido: str,
    tool_name: str | None = None,
    tool_result: str | None = None,
    pregunta_numero: int | None = None,
) -> Interaction:
    interaction = Interaction(
        lead_id=lead_id,
        rol=rol,
        contenido=contenido,
        tool_name=tool_name,
        tool_result=tool_result,
        pregunta_numero=pregunta_numero,
    )
    session.add(interaction)
    await session.commit()
    return interaction


async def close_lead(session: AsyncSession, lead_id: uuid.UUID, status: LeadStatus) -> None:
    lead = await session.get(Lead, lead_id)
    if lead:
        lead.estado = status
        await session.commit()


async def update_lead(session: AsyncSession, lead_id: uuid.UUID, **kwargs) -> Lead | None:
    lead = await session.get(Lead, lead_id)
    if lead:
        for key, value in kwargs.items():
            if hasattr(lead, key):
                setattr(lead, key, value)
        await session.commit()
        await session.refresh(lead)
    return lead


async def get_lead_interactions(session: AsyncSession, lead_id: uuid.UUID) -> list[Interaction]:
    result = await session.execute(
        select(Interaction)
        .where(Interaction.lead_id == lead_id)
        .order_by(Interaction.created_at)
    )
    return list(result.scalars().all())


async def count_questions(session: AsyncSession, lead_id: uuid.UUID) -> int:
    """Cuenta las interacciones del asistente como proxy de preguntas realizadas."""
    result = await session.execute(
        select(func.count()).select_from(Interaction)
        .where(
            Interaction.lead_id == lead_id,
            Interaction.rol == MessageRole.assistant,
        )
    )
    return result.scalar_one()


async def get_abandoned_leads(session: AsyncSession) -> list[Lead]:
    result = await session.execute(
        select(Lead)
        .where(
            Lead.estado == LeadStatus.abandonado,
            Lead.recordatorio_enviado == False,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def mark_reminder_sent(session: AsyncSession, lead_id: uuid.UUID) -> None:
    lead = await session.get(Lead, lead_id)
    if lead:
        lead.recordatorio_enviado = True
        await session.commit()


async def upsert_documento(session: AsyncSession, drive_id: str, **kwargs) -> Documento:
    result = await session.execute(
        select(Documento).where(Documento.drive_id == drive_id)
    )
    doc = result.scalar_one_or_none()
    if doc:
        for key, value in kwargs.items():
            if hasattr(doc, key):
                setattr(doc, key, value)
    else:
        doc = Documento(drive_id=drive_id, **kwargs)
        session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def get_active_documents(
    session: AsyncSession, tipo: str | None = None
) -> list[Documento]:
    stmt = select(Documento).where(Documento.status == DocumentStatus.activo)
    if tipo:
        stmt = stmt.where(Documento.tipo == tipo)
    result = await session.execute(stmt.order_by(Documento.nombre))
    return list(result.scalars().all())
