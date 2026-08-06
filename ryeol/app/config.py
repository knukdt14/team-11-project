from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm_mode: str = os.getenv("LLM_MODE", "auto").lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://ollama:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "exaone3.5:2.4b")
    search_rerank: bool = os.getenv("SEARCH_RERANK", "true").lower() in {"1", "true", "yes"}
    gemini_timeout: float = float(os.getenv("GEMINI_TIMEOUT", "20"))
    ollama_timeout: float = float(os.getenv("OLLAMA_TIMEOUT", "180"))
    session_db_path: str = os.getenv("SESSION_DB_PATH", "ryeol/runtime/sessions.sqlite3")


settings = Settings()
