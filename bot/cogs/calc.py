"""Calculateur d'achat & seuil de rentabilité (§3.5) + /convert (§4).

- /calc compute : point mort + paliers par plateforme (one-shot).
- /calc bind|unbind : marque un salon "calculateur" → on y écrit juste une valeur
  ("12000 jpy ebay", "35€ cm", "5000¥") et le bot répond automatiquement.
- /calc rates : affiche les taux courants.
- /convert : JPY <-> EUR via le taux Wise en cache.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.services.pricing import (
    CostBreakdown,
    cheapest_break_even,
    compute_all,
    parse_calc_message,
)
from bot.ui import embeds

log = logging.getLogger(__name__)

CURRENCY_CHOICES = [
    app_commands.Choice(name="JPY (yen)", value="jpy"),
    app_commands.Choice(name="EUR (euro)", value="eur"),
]
PLATFORM_CHOICES = [
    app_commands.Choice(name="eBay", value="ebay"),
    app_commands.Choice(name="Cardmarket", value="cardmarket"),
    app_commands.Choice(name="TikTok Shop", value="tiktok"),
    app_commands.Choice(name="Toutes", value="all"),
]


class CalcCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="calc", description="Calculateur de rentabilité")

    # --- /calc compute -------------------------------------------------------
    @group.command(name="compute", description="Seuil de rentabilité pour un achat")
    @app_commands.choices(currency=CURRENCY_CHOICES, platform=PLATFORM_CHOICES)
    @app_commands.describe(
        value="Montant d'achat",
        currency="Devise du montant",
        platform="Plateforme de revente (toutes par défaut)",
        shipping_in="Port entrant (€)",
        import_fees="Frais d'import / TVA non récupérable (€)",
        shipping_out="Port sortant (€)",
    )
    async def compute(
        self,
        interaction: discord.Interaction,
        value: float,
        currency: app_commands.Choice[str] | None = None,
        platform: app_commands.Choice[str] | None = None,
        shipping_in: float = 0.0,
        import_fees: float = 0.0,
        shipping_out: float = 0.0,
    ):
        await interaction.response.defer(thinking=True)
        cur = currency.value if currency else "eur"
        plat = platform.value if platform else "all"
        embed = await self._build(value, cur, plat, shipping_in, import_fees, shipping_out)
        await interaction.followup.send(embed=embed)

    async def _build(
        self,
        value: float,
        currency: str,
        platform: str,
        shipping_in: float = 0.0,
        import_fees: float = 0.0,
        shipping_out: float = 0.0,
    ) -> discord.Embed:
        purchase_eur = value
        header_cur = "€"
        if currency == "jpy":
            rate = await self.bot.fx.get_rate()
            purchase_eur = rate.jpy_to_eur(value)
            header_cur = f"≈ {purchase_eur:.2f} € ({value:.0f} JPY @ {rate.rate:.5f})"
        cost = CostBreakdown(
            purchase=purchase_eur,
            import_fees=import_fees,
            shipping_in=shipping_in,
            shipping_out=shipping_out,
        )
        platforms = None if platform == "all" else [platform]
        results = compute_all(cost, self.bot.pricing, platforms=platforms)
        cheapest = cheapest_break_even(results)
        header = (
            f"Achat **{value:.2f} {currency.upper()}** {header_cur if currency=='jpy' else ''} · "
            f"coût de revient **{cost.total:.2f} €**"
        )
        return embeds.calc_embed(results, cheapest.platform if cheapest else None, header=header)

    # --- /calc bind / unbind -------------------------------------------------
    @group.command(name="bind", description="Fait de ce salon un salon calculateur")
    async def bind(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        default_import: float = 0.0,
        default_ship_in: float = 0.0,
        default_ship_out: float = 0.0,
    ):
        cid = (channel or interaction.channel).id
        await self.bot.db.execute(
            "INSERT INTO calc_channels(channel_id, default_import, default_ship_in, default_ship_out) "
            "VALUES(?, ?, ?, ?) ON CONFLICT(channel_id) DO UPDATE SET "
            "default_import=excluded.default_import, default_ship_in=excluded.default_ship_in, "
            "default_ship_out=excluded.default_ship_out",
            (cid, default_import, default_ship_in, default_ship_out),
        )
        await interaction.response.send_message(
            f"🧮 <#{cid}> est maintenant un salon calculateur. Écris-y une valeur "
            "(`12000 jpy ebay`, `35€ cm`, `5000¥`).",
            ephemeral=True,
        )

    @group.command(name="unbind", description="Retire le statut calculateur du salon")
    async def unbind(
        self, interaction: discord.Interaction, channel: discord.TextChannel | None = None
    ):
        cid = (channel or interaction.channel).id
        await self.bot.db.execute("DELETE FROM calc_channels WHERE channel_id = ?", (cid,))
        await interaction.response.send_message(f"<#{cid}> n'est plus un salon calculateur.", ephemeral=True)

    @group.command(name="rates", description="Affiche les taux/frais du calculateur")
    async def rates(self, interaction: discord.Interaction):
        charges = self.bot.pricing.charges
        e = discord.Embed(title="📊 Taux du calculateur", color=0x5865F2)
        e.add_field(
            name="Charges micro-entreprise (% CA brut)",
            value=(
                f"URSSAF {charges.get('urssaf_pct', 0):.1%} · "
                f"IR {charges.get('income_tax_pct', 0):.1%} · "
                f"CFP {charges.get('cfp_pct', 0):.1%}"
            ),
            inline=False,
        )
        for key, p in self.bot.pricing.platforms.items():
            e.add_field(
                name=p.get("label", key),
                value=(
                    f"commission {p.get('commission_pct', 0):.1%} · "
                    f"paiement {p.get('payment_pct', 0):.1%} · "
                    f"fixe {p.get('fixed_fee_eur', 0):.2f} €"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=e, ephemeral=True)

    # --- /convert ------------------------------------------------------------
    @app_commands.command(name="convert", description="Convertit JPY <-> EUR (taux Wise)")
    @app_commands.choices(currency=CURRENCY_CHOICES)
    async def convert(
        self,
        interaction: discord.Interaction,
        amount: float,
        currency: app_commands.Choice[str],
    ):
        await interaction.response.defer(thinking=True)
        rate = await self.bot.fx.get_rate()
        if currency.value == "jpy":
            out = rate.jpy_to_eur(amount)
            msg = f"{amount:.0f} JPY = **{out:.2f} €**"
        else:
            out = rate.eur_to_jpy(amount)
            msg = f"{amount:.2f} € = **{out:.0f} JPY**"
        tag = " _(fallback)_" if rate.is_fallback else ""
        await interaction.followup.send(f"{msg}  · taux {rate.rate:.5f} ({rate.source}){tag}")

    # --- auto-réponse dans les salons calculateur ----------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        bound = await self.bot.db.fetchone(
            "SELECT default_import, default_ship_in, default_ship_out FROM calc_channels "
            "WHERE channel_id = ?",
            (message.channel.id,),
        )
        if bound is None:
            return
        parsed = parse_calc_message(message.content)
        if parsed is None:
            return
        embed = await self._build(
            parsed.value,
            parsed.currency,
            parsed.platform or "all",
            shipping_in=bound["default_ship_in"] or 0.0,
            import_fees=bound["default_import"] or 0.0,
            shipping_out=bound["default_ship_out"] or 0.0,
        )
        await message.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(CalcCog(bot))
