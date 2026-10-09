"""Application configuration classes."""
import os
from datetime import timedelta


class BaseConfig:
    """Shared config across all environments."""

    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-key-change-this")
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "dev-jwt-key-change-this")
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES: timedelta = timedelta(days=30)

    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        "mysql+mysqlconnector://root:@localhost/homespace",
    )

    SQLALCHEMY_ENGINE_OPTIONS: dict = {
    "pool_recycle": 280,
    "pool_pre_ping": True,
}

    PAYSTACK_SECRET_KEY: str = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY: str = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    MAIL_SERVER: str = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT: int = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS: bool = os.environ.get("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
    MAIL_USERNAME: str = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD: str = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER: str = os.environ.get("MAIL_DEFAULT_SENDER", "")
    PUBLIC_BASE_URL: str = os.environ.get("PUBLIC_BASE_URL", "https://www.homespace.ng")
    EMAIL_VERIFICATION_MAX_AGE: int = 24 * 60 * 60


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)


class ProductionConfig(BaseConfig):
    DEBUG = False


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}