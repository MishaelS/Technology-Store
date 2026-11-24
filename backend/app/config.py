from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# <repo>/resources/locales locally, /resources/locales in Docker
DEFAULT_LOCALES_DIR = Path(__file__).resolve().parents[2] / "resources" / "locales"


class Settings(BaseSettings):
    """App settings, read from environment variables (or the .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url:     str = "postgresql+psycopg://store:store@localhost:5432/store"
    jwt_secret:       str = "dev-secret-change-me"
    jwt_expire_hours: int = 24
    cors_origins:     str = "http://localhost:5173"
    locales_dir:      str = str(DEFAULT_LOCALES_DIR)
    seed_password:    str = ""   # password for seeded accounts; empty = random, printed to the log

    # Bonus system
    welcome_bonus:     int = 500   # bonus points for signing up
    cashback_percent:  int = 5     # % of the order total, credited when status becomes done
    max_bonus_percent: int = 30    # max % of an order that can be paid with bonus points

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
