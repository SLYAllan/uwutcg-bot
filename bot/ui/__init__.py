"""Couche présentation Discord : embeds + vues/boutons d'action (§3.10)."""

from bot.ui import embeds
from bot.ui.alerts import AlertActionButton, build_alert_view

__all__ = ["embeds", "AlertActionButton", "build_alert_view"]
