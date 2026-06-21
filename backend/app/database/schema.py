"""Database schema versioning -- applies pending migrations on startup.

Provides a simple migration framework: each migration is a numbered SQL file.
The current version is tracked in a `schema_version` table. On startup,
pending migrations are applied in order within transactions.
"""
import structlog
from pathlib import Path

logger = structlog.get_logger()

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def ensure_schema_version_table(pool) -> None:
    """Create schema_version table if not exists."""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT NOW(),
                description TEXT
            )
        """)


async def get_current_version(pool) -> int:
    """Return the latest applied migration version, or 0 if none."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COALESCE(MAX(version), 0) AS v FROM schema_version"
        )
        return row["v"]


async def get_pending_migrations(current_version: int) -> list[tuple[int, Path]]:
    """Return list of (version, path) for unapplied migrations."""
    pending = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        try:
            version = int(f.stem.split("_")[0])
            if version > current_version:
                pending.append((version, f))
        except ValueError:
            logger.warning("migration_invalid_filename", file=f.name)
    return pending


async def apply_migrations(pool) -> None:
    """Apply all pending migrations in order."""
    await ensure_schema_version_table(pool)
    current = await get_current_version(pool)
    pending = await get_pending_migrations(current)

    if not pending:
        logger.info("schema_up_to_date", version=current)
        return

    for version, path in pending:
        sql = path.read_text(encoding="utf-8")
        logger.info("migration_applying", version=version, file=path.name)
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES ($1, $2)",
                    version, path.name,
                )
        logger.info("migration_applied", version=version)