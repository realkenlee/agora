"""Database connection pool and query helpers using asyncpg."""

from __future__ import annotations
import json
import os
import ssl
from typing import Any, Optional
import asyncpg

_pool: Optional[asyncpg.Pool] = None


async def _init_conn(conn):
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def init_pool():
    global _pool
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    _pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
        command_timeout=30,
        statement_cache_size=0,  # required for Supabase PgBouncer pooler
        ssl=ssl_ctx,
        init=_init_conn,
    )


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_pool() on startup")
    return _pool


async def fetch(query: str, *args) -> list[asyncpg.Record]:
    async with pool().acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args) -> Optional[asyncpg.Record]:
    async with pool().acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args) -> Any:
    async with pool().acquire() as conn:
        return await conn.fetchval(query, *args)


async def execute(query: str, *args) -> str:
    async with pool().acquire() as conn:
        return await conn.execute(query, *args)


async def executemany(query: str, args: list) -> None:
    async with pool().acquire() as conn:
        await conn.executemany(query, args)
