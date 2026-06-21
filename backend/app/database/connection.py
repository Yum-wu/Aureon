"""asyncpg connection pool management."""
import asyncpg
import structlog
from app.config import settings

logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Initialize the connection pool. Call during lifespan startup."""
    global _pool
    db_url = settings.database.database_url
    if not db_url:
        logger.info("DATABASE_URL not set, skipping PostgreSQL initialization")
        return
    try:
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=2,
            max_size=20,
            command_timeout=60,
        )
        logger.info("PostgreSQL connected (pool min=2, max=20)")

        # Run schema migration
        await _run_schema()
    except Exception as e:
        logger.error("PostgreSQL connection failed: %s", e)
        _pool = None


async def _run_schema() -> None:
    """Execute schema.sql to create tables if not exist."""
    if _pool is None:
        return
    import os
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if os.path.exists(schema_path):
        sql = open(schema_path, "r", encoding="utf-8").read()
        async with _pool.acquire() as conn:
            await conn.execute(sql)
        logger.info("Database schema applied")


def get_db_pool() -> asyncpg.Pool | None:
    """Return the connection pool, or None if not initialized."""
    return _pool


def get_pool_stats() -> dict | None:
    """Return asyncpg pool statistics for monitoring."""
    pool = get_db_pool()
    if not pool:
        return None
    return {
        "size": pool.get_size(),
        "idle_size": pool.get_idle_size(),
        "min_size": pool.get_min_size(),
        "max_size": pool.get_max_size(),
    }


def update_prometheus_pool_stats() -> None:
    """Push DB pool stats to Prometheus gauges."""
    stats = get_pool_stats()
    if stats:
        try:
            from app.observability.custom_metrics import db_pool_size, db_pool_idle
            db_pool_size.set(stats["size"])
            db_pool_idle.set(stats["idle_size"])
        except Exception:
            pass


async def close_db_pool() -> None:
    """Close the connection pool. Call during lifespan shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")
