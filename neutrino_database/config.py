from pydantic_settings import BaseSettings, SettingsConfigDict
from neutrino_database.paths import ProjectPath
from pathlib import Path

class Settings(BaseSettings):

    DATABASE_URL: str

    model_config = SettingsConfigDict(
        env_file=Path(ProjectPath.ROOT / ".env") if (ProjectPath.ROOT / ".env").exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

# Instantiate only once.
settings = Settings()