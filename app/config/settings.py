"""Typed, validated application configuration.

Nothing outside this module should read os.environ directly. Every threshold that
could reasonably change (universe bounds, cooldowns, provider choice) lives here,
never hard-coded in business logic.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MarketSettings(BaseSettings):
    market: str = Field(default="INDIA", alias="MARKET")
    exchange: str = Field(default="NSE", alias="EXCHANGE")
    min_price: float = Field(default=50.0, alias="MIN_PRICE")
    max_price: float = Field(default=300.0, alias="MAX_PRICE")
    min_avg_traded_value: float = Field(default=5_000_000.0, alias="MIN_AVG_TRADED_VALUE")
    exclude_sme: bool = Field(default=True, alias="EXCLUDE_SME")
    min_history_days: int = Field(default=250, alias="MIN_HISTORY_DAYS")
    watchlist_symbols: str = Field(default="TCS,RELIANCE,INFY", alias="WATCHLIST_SYMBOLS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def watchlist(self) -> list[str]:
        return [s.strip() for s in self.watchlist_symbols.split(",") if s.strip()]


class DatabaseSettings(BaseSettings):
    database_url: str = Field(default="sqlite:///./databroker.db", alias="DATABASE_URL")
    analytical_storage_uri: str = Field(default="", alias="ANALYTICAL_STORAGE_URI")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ProviderSettings(BaseSettings):
    market_data_provider: str = Field(default="", alias="MARKET_DATA_PROVIDER")
    market_data_api_key: str = Field(default="", alias="MARKET_DATA_API_KEY")
    market_data_ws_url: str = Field(default="", alias="MARKET_DATA_WS_URL")
    news_provider: str = Field(default="", alias="NEWS_PROVIDER")
    news_api_key: str = Field(default="", alias="NEWS_API_KEY")
    company_data_provider: str = Field(default="", alias="COMPANY_DATA_PROVIDER")
    indianapi_api_key: str = Field(default="", alias="INDIANAPI_API_KEY")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class LLMSettings(BaseSettings):
    groq_api_keys: str = Field(default="", alias="GROQ_API_KEYS")
    cerebras_api_keys: str = Field(default="", alias="CEREBRAS_API_KEYS")
    default_routing_profile: str = Field(default="cost_aware", alias="LLM_DEFAULT_ROUTING_PROFILE")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def groq_keys(self) -> list[str]:
        return [k.strip() for k in self.groq_api_keys.split(",") if k.strip()]

    def cerebras_keys(self) -> list[str]:
        return [k.strip() for k in self.cerebras_api_keys.split(",") if k.strip()]


class TelegramSettings(BaseSettings):
    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AlertSettings(BaseSettings):
    cooldown_seconds: int = Field(default=900, alias="ALERT_COOLDOWN_SECONDS")
    poll_interval_seconds: int = Field(default=300, alias="POLL_INTERVAL_SECONDS")
    """How often scripts/run_service.py checks the watchlist while the market is
    open. 300s (5 min) balances timeliness against yfinance rate limits on a free
    setup — lower it for scalping, raise it for swing."""
    retrain_interval_days: int = Field(default=1, alias="RETRAIN_INTERVAL_DAYS")
    """How often scripts/run_service.py re-runs the anomaly model trainer
    automatically (ml/training/anomaly_trainer_job.py). Pure local computation
    (fits mean/std features + a baseline comparison, a couple of seconds per
    watchlist symbol) — no LLM calls, cheap enough to run daily even on a small
    burstable VM. Set to 0 to disable auto-retraining and only train by running
    scripts/train_anomaly_model.py yourself."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DeploymentSettings(BaseSettings):
    deploy_env: str = Field(default="local", alias="DEPLOY_ENV")
    azure_subscription_id: str = Field(default="", alias="AZURE_SUBSCRIPTION_ID")
    azure_resource_group: str = Field(default="", alias="AZURE_RESOURCE_GROUP")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class Settings:
    """Composition of all settings groups. Load once at process startup."""

    def __init__(self) -> None:
        self.market = MarketSettings()
        self.database = DatabaseSettings()
        self.providers = ProviderSettings()
        self.llm = LLMSettings()
        self.telegram = TelegramSettings()
        self.alerts = AlertSettings()
        self.deployment = DeploymentSettings()

        if self.market.min_price >= self.market.max_price:
            raise ValueError("MIN_PRICE must be less than MAX_PRICE")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
