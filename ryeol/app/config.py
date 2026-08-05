from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm_mode: str = os.getenv("LLM_MODE", "qwen").lower()
    ollama_url: str = os.getenv("OLLAMA_URL", "http://ollama:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    search_rerank: bool = os.getenv("SEARCH_RERANK", "true").lower() in {"1", "true", "yes"}
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "180"))
    session_db_path: str = os.getenv("SESSION_DB_PATH", "ryeol/runtime/sessions.sqlite3")


settings = Settings()
