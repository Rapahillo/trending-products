from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://trending:trending_dev@localhost:5432/trending"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours
    pipeline_schedule_hours: int = 12
    scoring_weights_path: str = "config/scoring_weights.yml"
    tiktok_base_url: str = "https://ads.tiktok.com/creative_radar_api/v1/"
    aliexpress_api_key: str = ""
    collector_retry_attempts: int = 3
    collector_retry_backoff: float = 2.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
