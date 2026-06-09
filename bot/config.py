"""Configuration centrale : secrets (.env) + taux (pricing.yaml) + table `config`.

Deux niveaux :
- `Settings` (pydantic-settings) : secrets et chemins, chargés depuis `.env`. Immuable.
- `PricingConfig` : taux/frais chargés depuis `pricing.yaml`, surchargeables à chaud
  par la table `config` (réglage en jeu via /calc rates, /config set).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Secrets et paramètres d'environnement (lecture seule)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Discord
    discord_token: str = Field(default="", alias="DISCORD_TOKEN")
    discord_app_id: str = Field(default="", alias="DISCORD_APP_ID")
    discord_client_secret: str = Field(default="", alias="DISCORD_CLIENT_SECRET")
    discord_guild_id: int | None = Field(default=None, alias="DISCORD_GUILD_ID")
    default_track_channel_id: int | None = Field(default=None, alias="DEFAULT_TRACK_CHANNEL_ID")
    daily_digest_channel_id: int | None = Field(default=None, alias="DAILY_DIGEST_CHANNEL_ID")

    # eBay
    ebay_app_id: str = Field(default="", alias="EBAY_APP_ID")
    ebay_dev_id: str = Field(default="", alias="EBAY_DEV_ID")
    ebay_cert_id: str = Field(default="", alias="EBAY_CERT_ID")
    ebay_marketplace_id: str = Field(default="EBAY_FR", alias="EBAY_MARKETPLACE_ID")
    ebay_env: str = Field(default="PRODUCTION", alias="EBAY_ENV")

    # Vinted
    vinted_domain: str = Field(default="www.vinted.fr", alias="VINTED_DOMAIN")
    vinted_session_cookie: str = Field(default="", alias="VINTED_SESSION_COOKIE")

    # Divers
    timezone: str = Field(default="Europe/Paris", alias="TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    db_path: str = Field(default="data/bot.db", alias="DB_PATH")
    knowledge_dir: str = Field(default="knowledge", alias="KNOWLEDGE_DIR")
    pricing_config: str = Field(default="pricing.yaml", alias="PRICING_CONFIG")

    @field_validator(
        "discord_guild_id",
        "default_track_channel_id",
        "daily_digest_channel_id",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v):
        """Une variable .env vide ('') doit valoir None, pas planter le parsing int."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @property
    def ebay_oauth_base(self) -> str:
        if self.ebay_env.upper() == "SANDBOX":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()


class PricingConfig:
    """Taux/frais éditables. Lit pricing.yaml ; les overrides DB sont fusionnés à chaud."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    @classmethod
    def load(cls, path: str | Path) -> "PricingConfig":
        p = Path(path)
        if not p.exists():
            return cls({})
        with p.open("r", encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    def apply_overrides(self, overrides: dict[str, Any]) -> None:
        """Fusion récursive d'overrides (issus de la table config) sur les taux YAML."""
        _deep_merge(self._data, overrides)

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self._data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    # Raccourcis courants -----------------------------------------------------
    @property
    def charges(self) -> dict[str, float]:
        return self.get("charges", default={}) or {}

    @property
    def platforms(self) -> dict[str, dict]:
        return self.get("platforms", default={}) or {}

    @property
    def sourcing(self) -> dict[str, float]:
        return self.get("sourcing", default={}) or {}

    @property
    def thresholds(self) -> dict[str, float]:
        return self.get("thresholds", default={}) or {}

    @property
    def grading(self) -> dict[str, dict]:
        return self.get("grading", default={}) or {}

    def as_dict(self) -> dict[str, Any]:
        return self._data


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
