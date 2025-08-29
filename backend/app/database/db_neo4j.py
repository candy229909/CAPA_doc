# app/database/db_neo4j.py
from __future__ import annotations

# ⬇️ 保留你原本用到的 import（neo4j AsyncGraphDatabase 等）
import asyncio, socket
from urllib.parse import urlparse
from neo4j import AsyncGraphDatabase


class Neo4jDB:
    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None

    async def connect(self):
        # 先確定 DNS 能解析
        u = urlparse(self.uri)
        host = u.hostname or "neo4j"
        port = u.port or 7687
        await self._wait_dns(host, port, seconds=60)

        # 建 driver 並等服務可用
        self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))
        for _ in range(60):
            try:
                await self.driver.verify_connectivity()
                return
            except Exception:
                await asyncio.sleep(1)
        raise RuntimeError(f"Neo4j not reachable at {self.uri}")

    async def close(self):
        if self.driver:
            await self.driver.close()
    
    async def _wait_dns(self, host: str, port: int, seconds: int = 60):
        loop = asyncio.get_running_loop()
        for _ in range(seconds):
            try:
                await loop.getaddrinfo(host, port)  # 解析成功就回傳
                return
            except socket.gaierror:
                await asyncio.sleep(1)
        raise RuntimeError(f"DNS not ready for {host}:{port}")

    async def ensure_constraints(self):
        # 把你原本的唯一約束/索引建立搬過來
        cyphers = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Conversation) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Prompt) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
        ]
        async with self.driver.session() as s:
            for q in cyphers:
                await s.run(q)

    async def ping(self) -> bool:
        """檢查 Neo4j 連接狀態"""
        try:
            async with self.driver.session() as session:
                await session.run("RETURN 1")
            return True
        except Exception:
            return False

    async def save_interaction(self, conversation_id: str, user_message: str, ai_response: str):
        """儲存一次對話問答到 Neo4j 圖形資料庫"""
        """ No need to implement for now, save conversation to neo4j DB
        try:
            async with self.driver.session() as session:
                await session.run(
                    """ """
                    MERGE (c:Conversation {id: $conversation_id})
                    CREATE (u:Message {content: $user_message, role: 'user', timestamp: datetime()})
                    CREATE (a:Message {content: $ai_response, role: 'assistant', timestamp: datetime()})
                    CREATE (c)-[:CONTAINS]->(u)
                    CREATE (c)-[:CONTAINS]->(a)
                    CREATE (u)-[:FOLLOWED_BY]->(a)
                    """ """,
                    conversation_id=conversation_id, user_message=user_message, ai_response=ai_response
                )
        except Exception as e:
            print(f"Neo4j error: {e}")
        """
        return

    async def run_read_query(self, cypher: str, params: Dict[str, Any] | None = None):
        """執行讀取類型的 Cypher 查詢並返回結果資料"""
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, parameters=params or {})
                records = []
                async for r in result:
                    records.append(r.data())
                return records
        except Exception as e:
            print("[Neo4j] run_read_query error:", e)
            return []

