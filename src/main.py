from alembic.config import Config
from alembic import command

# Aplicar migraciones al startup (asegura schema actualizado)
alembic_cfg = Config("src/db/migrations/alembic.ini")
command.upgrade(alembic_cfg, "head")

# Importar hooks para que Chainlit los registre
import src.chainlit.hooks  # noqa: E402, F401
