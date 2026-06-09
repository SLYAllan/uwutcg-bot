"""Actions rapides sur les embeds d'alerte (§3.10).

- Bouton LIEN DIRECT (`ButtonStyle.link`) : ouvre la vraie page web (panier eBay, article
  Vinted, page Cardmarket) — simple navigation, aucune automatisation, aucun risque compte.
- Boutons CÔTÉ BOT : persistants via `discord.ui.DynamicItem` (le custom_id encode l'action
  + l'id seen_listings + le prix en centimes) → survivent à un redémarrage du bot.

PAS de bouton « payer direct » : SCA/PSD2 l'interdit côté loi, et automatiser le checkout
Vinted ferait courir un risque de bannissement. Conforme au brief.
"""
from __future__ import annotations

import logging
import re

import discord

log = logging.getLogger(__name__)

# action -> (label, style, emoji)
ACTIONS = {
    "margin": ("Calcule ma marge", discord.ButtonStyle.primary, "💶"),
    "bought": ("Acheté", discord.ButtonStyle.success, "✅"),
    "ignore": ("Ignorer", discord.ButtonStyle.secondary, "🚫"),
    "mute": ("Mute la recherche", discord.ButtonStyle.secondary, "🔕"),
    "save": ("Sauvegarder", discord.ButtonStyle.secondary, "📌"),
    "ebaywl": ("Watchlist eBay", discord.ButtonStyle.secondary, "➕"),
}


class AlertActionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"alert:(?P<action>\w+):(?P<seen>\d+):(?P<cents>\d+)",
):
    """Bouton persistant. custom_id : alert:<action>:<seen_id>:<price_cents>."""

    def __init__(self, action: str, seen_id: int, price_cents: int):
        self.action = action
        self.seen_id = seen_id
        self.price_cents = price_cents
        label, style, emoji = ACTIONS[action]
        super().__init__(
            discord.ui.Button(
                label=label,
                style=style,
                emoji=emoji,
                custom_id=f"alert:{action}:{seen_id}:{price_cents}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):  # type: ignore[override]
        return cls(match["action"], int(match["seen"]), int(match["cents"]))

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        bot = interaction.client
        price = self.price_cents / 100.0
        if self.action == "margin":
            await self._do_margin(interaction, bot, price)
        elif self.action == "bought":
            await bot.db.set_seen_status_by_id(self.seen_id, "bought")  # type: ignore[attr-defined]
            await interaction.response.send_message("✅ Marqué **acheté**.", ephemeral=True)
        elif self.action == "ignore":
            await bot.db.set_seen_status_by_id(self.seen_id, "ignored")  # type: ignore[attr-defined]
            await interaction.response.send_message("🚫 Deal **ignoré**.", ephemeral=True)
        elif self.action == "save":
            await bot.db.set_seen_status_by_id(self.seen_id, "saved")  # type: ignore[attr-defined]
            await interaction.response.send_message("📌 **Sauvegardé** dans la watchlist.", ephemeral=True)
        elif self.action == "mute":
            await self._do_mute(interaction, bot)
        elif self.action == "ebaywl":
            await interaction.response.send_message(
                "➕ La watchlist eBay nécessite une autorisation utilisateur (OAuth "
                "*Authorization Code*) en plus de la clé application. À configurer "
                "(consentement eBay) — voir README §eBay watchlist.",
                ephemeral=True,
            )

    async def _do_margin(self, interaction: discord.Interaction, bot, price: float) -> None:
        from bot.services.pricing import CostBreakdown, cheapest_break_even, compute_all
        from bot.ui import embeds

        cost = CostBreakdown(purchase=price)
        results = compute_all(cost, bot.pricing)  # type: ignore[attr-defined]
        cheapest = cheapest_break_even(results)
        embed = embeds.calc_embed(
            results,
            cheapest.platform if cheapest else None,
            header=f"Sur la base d'un achat à **{price:.2f} €**",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _do_mute(self, interaction: discord.Interaction, bot) -> None:
        row = await bot.db.get_seen(self.seen_id)  # type: ignore[attr-defined]
        if row is None:
            await interaction.response.send_message("Introuvable.", ephemeral=True)
            return
        await bot.db.execute(  # type: ignore[attr-defined]
            "UPDATE tracked_searches SET muted = 1 WHERE id = ?", (row["search_id"],)
        )
        await interaction.response.send_message("🔕 Recherche **mutée**.", ephemeral=True)


def build_alert_view(
    *, link_url: str | None, seen_id: int, price: float | None, is_ebay: bool = False
) -> discord.ui.View:
    """Construit la vue d'alerte : bouton lien (si dispo) + boutons d'action persistants."""
    view = discord.ui.View(timeout=None)
    if link_url:
        view.add_item(
            discord.ui.Button(label="Ouvrir 🔗", style=discord.ButtonStyle.link, url=link_url)
        )
    cents = int(round((price or 0.0) * 100))
    for action in ("margin", "bought", "ignore", "mute", "save"):
        view.add_item(AlertActionButton(action, seen_id, cents))
    if is_ebay:
        view.add_item(AlertActionButton("ebaywl", seen_id, cents))
    return view
