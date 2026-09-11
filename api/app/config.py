from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    admin_api_key: str = "change-me"
    app_secret: str = "change-me-too"
    database_url: str = "sqlite:////data/baltigo_live.db"
    media_dir: Path = Path("/data/media")
    log_dir: Path = Path("/data/logs")
    cors_origins: str = "http://localhost:8080"

    worker_id: str = "worker-1"
    worker_poll_seconds: float = 2.0
    restart_base_seconds: int = 3
    restart_max_seconds: int = 60

    stream_transcode: bool = False
    video_bitrate: str = "4500k"
    audio_bitrate: str = "128k"
    output_fps: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
settings.media_dir.mkdir(parents=True, exist_ok=True)
settings.log_dir.mkdir(parents=True, exist_ok=True)
