from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "k8989785")
    NEO4J_DB: str = os.getenv("NEO4J_DB", "neo4j")

    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma:2b")
    OLLAMA_MODELS_RAW: str = os.getenv("OLLAMA_MODELS", "")

    INPUT_DIR: str = os.getenv("INPUT_DIR", "inputs")
    PROCESSED_DIR: str = os.getenv("PROCESSED_DIR", "processed")
    OUTPUT_JSON_DIR: str = os.getenv("OUTPUT_JSON_DIR", "output/json")

    def get_models(self) -> list[str]:
        models = [m.strip() for m in self.OLLAMA_MODELS_RAW.split(",") if m.strip()]
        return models or [self.OLLAMA_MODEL]

settings = Settings()

# 確保資料夾存在
for p in [settings.INPUT_DIR, settings.PROCESSED_DIR, settings.OUTPUT_JSON_DIR]:
    os.makedirs(p, exist_ok=True)