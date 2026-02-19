from pathlib import Path
from pydantic_settings import BaseSettings


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "VeilChat"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = f"sqlite+aiosqlite:///{_PROJECT_ROOT / 'data' / 'veilchat.db'}"

    # Auth
    secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # LLM Provider defaults
    default_provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    ollama_base_url: str = "http://localhost:11434/v1"

    # Sanitization
    sanitization_enabled: bool = True
    min_confidence_threshold: float = 0.7

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Licensing
    license_public_key_path: str = ""

    # Data directory
    data_dir: Path = _PROJECT_ROOT / "data"

    model_config = {"env_prefix": "VEILCHAT_", "env_file": str(_PROJECT_ROOT / ".env")}


settings = Settings()
