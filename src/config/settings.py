"""Application settings using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Supabase
    supabase_url: str = Field(alias="NEXT_PUBLIC_SUPABASE_URL")
    supabase_anon_key: str = Field(alias="NEXT_PUBLIC_SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")

    # Notion (optional, for task management)
    notion_api_key: str | None = Field(default=None, alias="NOTION_API_KEY")

    # Scraper settings
    scraper_user_agent: str = Field(
        default="AgendadesScraper/0.1 (+https://agendades.es)",
        alias="SCRAPER_USER_AGENT",
    )
    scraper_request_timeout: int = Field(default=30, alias="SCRAPER_REQUEST_TIMEOUT")
    scraper_max_retries: int = Field(default=3, alias="SCRAPER_MAX_RETRIES")
    scraper_retry_delay: float = Field(default=1.0, alias="SCRAPER_RETRY_DELAY")
    scraper_concurrent_requests: int = Field(default=5, alias="SCRAPER_CONCURRENT_REQUESTS")

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )
    log_format: Literal["json", "console"] = Field(default="console", alias="LOG_FORMAT")
    log_file: str | None = Field(default="logs/scraper.log", alias="LOG_FILE")

    # Environment
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )
    debug: bool = Field(default=False, alias="DEBUG")

    # LLM (Groq) - Tiered model system (all available on Groq free tier)
    # ORO:    llama-3.3-70b-versatile - Structured JSON APIs
    # PLATA:  llama-3.3-70b-versatile - Semi-structured HTML/RSS
    # BRONCE: llama-3.3-70b-versatile - Web scraping (same model, simpler)
    # FILTER: llama-3.1-8b-instant - Pre-processing, discard junk
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    llm_enabled: bool = Field(default=False, alias="LLM_ENABLED")
    llm_batch_size: int = Field(default=20, alias="LLM_BATCH_SIZE")

    # Tiered models by source quality level
    llm_model_oro: str = Field(default="openai/gpt-oss-120b", alias="LLM_MODEL_ORO")
    llm_model_plata: str = Field(default="llama-3.3-70b-versatile", alias="LLM_MODEL_PLATA")
    llm_model_bronce: str = Field(default="llama-3.3-70b-versatile", alias="LLM_MODEL_BRONCE")
    llm_model_filter: str = Field(default="llama-3.1-8b-instant", alias="LLM_MODEL_FILTER")

    # Ollama (local/self-hosted LLM - for testing, no rate limits)
    ollama_url: str | None = Field(default=None, alias="OLLAMA_URL")
    ollama_model: str = Field(default="qwen2.5:7b", alias="OLLAMA_MODEL")
    llm_provider: Literal["groq", "ollama"] = Field(default="groq", alias="LLM_PROVIDER")

    # Unsplash (for event cover images)
    unsplash_access_key: str | None = Field(default=None, alias="UNSPLASH_ACCESS_KEY")
    unsplash_enabled: bool = Field(default=False, alias="UNSPLASH_ENABLED")

    # Pexels (fallback for images)
    pexels_api_key: str | None = Field(default=None, alias="PEXELS_API_KEY")

    # Firecrawl (for HTML to Markdown conversion)
    firecrawl_url: str = Field(default="http://localhost:3002", alias="FIRECRAWL_URL")
    firecrawl_api_key: str | None = Field(default=None, alias="FIRECRAWL_API_KEY")

    # Scraper modes
    dry_run: bool = Field(default=False, alias="DRY_RUN")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
