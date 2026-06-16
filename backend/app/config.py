from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class ComputerUseMode(str, Enum):
    OFF = "off"
    READONLY = "readonly"
    CONFIRM = "confirm"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PET_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM (openai-compatible)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # DashScope 百炼
    dashscope_api_key: str = ""
    tts_model: str = "cosyvoice-v2"
    tts_voice: str = "longxiaochun_v2"
    tts_enabled: bool = True

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000

    # Agent computer use 安全模式
    computer_use_mode: ComputerUseMode = ComputerUseMode.CONFIRM

    # Memory (Phase 5)
    memory_db_path: str = "data/memory.db"
    memory_llm_model: str = ""          # 空 = 使用主 llm_model
    memory_extraction_enabled: bool = True
    memory_compression_threshold: int = 10   # 多少轮后开始触发压缩
    memory_compression_batch: int = 6        # 每次压缩多少轮
    memory_recall_max_events: int = 10
    memory_recall_token_budget: int = 1000


settings = Settings()
