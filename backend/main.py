# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.db_mongo import MongoDB
from app.database.db_neo4j import Neo4jDB

from app.routes.conversation_router import router as conversation_router
from app.routes.file_router import router as file_router
from app.routes.chat_router import router as chat_router
from app.routes.health_router import router as health_router
from app.routes.law_router import router as law_router
from app.routes.nlu_router import router as nlu_router
from app.routes.rag_router import router as rag_router
from app.routes.ethics_router import router as ethics_router

MONGODB_URL = "mongodb://mongo:27017/chatdb"
MONGODB_DB = "chatdb"
NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"

def create_app() -> FastAPI:
    app = FastAPI(title="CAPA_DOC API", version="1.0.0")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # DB instances on app.state
    app.state.mongo = MongoDB(MONGODB_URL, MONGODB_DB)
    app.state.neo4j = Neo4jDB(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    @app.on_event("startup")
    async def _startup():
        await app.state.mongo.connect()
        await app.state.neo4j.connect()
        if hasattr(app.state.neo4j, "ensure_constraints"):
            await app.state.neo4j.ensure_constraints()

    @app.on_event("shutdown")
    async def _shutdown():
        await app.state.mongo.close()
        await app.state.neo4j.close()

    # Register blueprints (routers)
    app.include_router(conversation_router, prefix="/api/conversations", tags=["conversations"])
    app.include_router(file_router,         prefix="/api/file_uploads", tags=["files"])
    app.include_router(chat_router,         prefix="/api/chat", tags=["chat"])
    app.include_router(health_router,       prefix="/api/health", tags=["health"])
    app.include_router(law_router,          prefix="/api/law_advice", tags=["law"])
    app.include_router(nlu_router,          prefix="/api/nlu", tags=["nlu"])
    app.include_router(rag_router,          prefix="/api/rag", tags=["rag"])
    app.include_router(ethics_router,       prefix="/api/ethics", tags=["ethics"])

    @app.get("/")
    async def root():
        return {"message": "CAPA_DOC backend is running"}

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
