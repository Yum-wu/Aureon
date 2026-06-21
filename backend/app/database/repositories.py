"""Database repositories using asyncpg."""

import structlog
from app.database.connection import get_db_pool

logger = structlog.get_logger()


class MessageRepository:
    @staticmethod
    async def create(session_id: str, role: str, content: str,
                     tokens: int = 0, tool_name: str = None,
                     tool_args: str = None, tenant_id: str = "default") -> int:
        pool = get_db_pool()
        if not pool:
            raise RuntimeError("Database not initialized")
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO messages (session_id, role, content, tokens, tool_name, tool_args, tenant_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                session_id, role, content, tokens, tool_name, tool_args, tenant_id
            )
            return row["id"]

    @staticmethod
    async def get_conversation(session_id: str, limit: int = 50, tenant_id: str = "default") -> list[dict]:
        pool = get_db_pool()
        if not pool:
            return []
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, session_id, role, content, tokens, tool_name, tool_args, created_at
                   FROM messages WHERE session_id = $1 AND tenant_id = $2
                   ORDER BY created_at DESC LIMIT $3""",
                session_id, tenant_id, limit
            )
            return [dict(r) for r in reversed(rows)]

    @staticmethod
    async def cleanup_oldest(session_id: str, max_messages: int = 500, tenant_id: str = "default") -> int:
        pool = get_db_pool()
        if not pool:
            return 0
        async with pool.acquire() as conn:
            result = await conn.execute(
                """DELETE FROM messages WHERE id IN (
                     SELECT id FROM messages WHERE session_id = $1 AND tenant_id = $2
                     ORDER BY created_at ASC OFFSET $3
                   )""",
                session_id, tenant_id, max_messages
            )
            return int(result.split()[-1])


class AtomRepository:
    @staticmethod
    async def create(session_id: str, subject: str, predicate: str, obj: str,
                     message_id: int = None, confidence: float = 0.5,
                     tenant_id: str = "default") -> int:
        pool = get_db_pool()
        if not pool:
            raise RuntimeError("Database not initialized")
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO atoms (session_id, subject, predicate, object, message_id, confidence, tenant_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                session_id, subject, predicate, obj, message_id, confidence, tenant_id
            )
            return row["id"]

    @staticmethod
    async def get_by_session(session_id: str, limit: int = 50, tenant_id: str = "default") -> list[dict]:
        pool = get_db_pool()
        if not pool:
            return []
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM atoms WHERE session_id = $1 AND tenant_id = $2
                   ORDER BY created_at DESC LIMIT $3""",
                session_id, tenant_id, limit
            )
            return [dict(r) for r in rows]


_ALLOWED_UPDATE_FIELDS = frozenset({"name", "email", "role", "is_active", "password_hash"})


class UserRepository:
    @staticmethod
    async def create(email: str, name: str, password_hash: str,
                     role: str = "viewer", tenant_id: str = "default") -> int:
        pool = get_db_pool()
        if not pool:
            raise RuntimeError("Database not initialized")
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO users (email, name, password_hash, role, tenant_id)
                   VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                email, name, password_hash, role, tenant_id
            )
            return row["id"]

    @staticmethod
    async def get_by_email(email: str) -> dict | None:
        pool = get_db_pool()
        if not pool:
            return None
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
            return dict(row) if row else None

    @staticmethod
    async def list_users(role: str = None, tenant_id: str = "default") -> list[dict]:
        pool = get_db_pool()
        if not pool:
            return []
        async with pool.acquire() as conn:
            if role:
                rows = await conn.fetch(
                    "SELECT * FROM users WHERE role = $1 AND tenant_id = $2 ORDER BY created_at DESC",
                    role, tenant_id
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM users WHERE tenant_id = $1 ORDER BY created_at DESC", tenant_id
                )
            return [dict(r) for r in rows]

    @staticmethod
    async def update(user_id: int, **fields) -> bool:
        """Update user fields �� only whitelisted column names allowed."""
        pool = get_db_pool()
        if not pool:
            return False
        safe_fields = {k: v for k, v in fields.items() if k in _ALLOWED_UPDATE_FIELDS}
        if not safe_fields:
            logger.warning("user_update_no_safe_fields", user_id=user_id, requested=list(fields.keys()))
            return False
        set_parts = []
        values = []
        for i, (k, v) in enumerate(safe_fields.items(), 1):
            set_parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(user_id)
        async with pool.acquire() as conn:
            result = await conn.execute(
                f"UPDATE users SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = ${len(values)}",
                *values
            )
            return result != "UPDATE 0"

    @staticmethod
    async def delete(user_id: int) -> bool:
        pool = get_db_pool()
        if not pool:
            return False
        async with pool.acquire() as conn:
            result = await conn.execute("UPDATE users SET is_active = FALSE WHERE id = $1", user_id)
            return result != "UPDATE 0"


class AuditLogRepository:
    @staticmethod
    async def create(action: str, resource: str = None, detail: str = None,
                     user_id: str = None, ip_address: str = None,
                     tenant_id: str = "default") -> int:
        pool = get_db_pool()
        if not pool:
            raise RuntimeError("Database not initialized")
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO audit_logs (user_id, action, resource, detail, ip_address, tenant_id)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                user_id, action, resource, detail, ip_address, tenant_id
            )
            return row["id"]

    @staticmethod
    async def list_logs(tenant_id: str = "default", limit: int = 100, offset: int = 0) -> list[dict]:
        pool = get_db_pool()
        if not pool:
            return []
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM audit_logs WHERE tenant_id = $1
                   ORDER BY created_at DESC LIMIT $2 OFFSET $3""",
                tenant_id, limit, offset
            )
            return [dict(r) for r in rows]
