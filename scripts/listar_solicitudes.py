"""Lista las solicitudes de contacto pendientes (estado contacto_solicitado).

Útil mientras la notificación interna por SMTP no esté implementada (plan 14).
Corre dentro de Docker:

    docker compose run --rm app python3 scripts/listar_solicitudes.py
"""

import asyncio
from datetime import timezone

from sqlalchemy import select

from src.db.models import Lead, LeadStatus
from src.db.session import async_session


async def main() -> None:
    async with async_session() as session:
        result = await session.execute(
            select(Lead)
            .where(Lead.estado == LeadStatus.contacto_solicitado)
            .order_by(Lead.updated_at.desc())
        )
        leads = list(result.scalars().all())

    if not leads:
        print("No hay solicitudes pendientes.")
        return

    print(f"{len(leads)} solicitud(es) pendiente(s):\n")
    for lead in leads:
        extra = lead.extra_data or {}
        solicitud = extra.get("ultima_solicitud") or {}
        tipo = solicitud.get("tipo", "contacto")
        fecha = lead.updated_at
        if fecha is None:
            fecha = lead.created_at
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)

        print("─" * 60)
        print(f"Tipo:       {tipo}")
        print(f"Email:      {lead.email or 'N/A'}")
        print(f"Nombre:     {lead.nombre or 'N/A'}")
        print(f"Empresa:    {lead.empresa or 'N/A'}")
        print(f"Cargo:      {lead.cargo or 'N/A'}")
        print(f"Fecha:      {fecha.astimezone(timezone.utc).isoformat(timespec='minutes')}")
        print(f"Lead ID:    {lead.id}")
        print("─" * 60)
        print()


if __name__ == "__main__":
    asyncio.run(main())
