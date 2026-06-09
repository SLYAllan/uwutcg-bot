import pathlib

import pytest

from bot.config import PricingConfig

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def pricing() -> PricingConfig:
    return PricingConfig.load(ROOT / "pricing.yaml")
