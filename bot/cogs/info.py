"""Commande d'aide : /info — tutoriel complet d'utilisation du bot."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

INTRO = (
    "Bot de veille marché **UwUTCG** : tracking d'annonces, ventes, prix, arbitrage Japon "
    "et calculateur de rentabilité. Les alertes arrivent en **quasi temps réel** (le bot "
    "interroge les plateformes en boucle : eBay ~60 s, Vinted ~90 s, Cardmarket ~5 min)."
)


def build_info_embeds() -> list[discord.Embed]:
    e1 = discord.Embed(
        title="📖 Guide du bot UwUTCG — 1/2", description=INTRO, color=0x5865F2
    )
    e1.add_field(
        name="① À configurer en premier",
        value=(
            "`/config set-default-channel` — salon où arrivent les alertes de tracking\n"
            "`/config set-digest-channel` — salon du résumé quotidien (taux JPY→EUR + cotes)\n"
            "`/config show` — voir la config courante"
        ),
        inline=False,
    )
    e1.add_field(
        name="② Tracking d'annonces — `/track`",
        value=(
            "Reçois une alerte par **nouvelle annonce** sur tes recherches.\n"
            "`/track add platform:vinted query:\"dracaufeu 151\" max_price:50`\n"
            "`/track add platform:ebay query:\"pikachu psa 10\"`\n"
            "• **Cardmarket** = deal sniper sur UNE carte : `query` = **nom exact ou URL** de la "
            "carte, et mets un `max_price` pour ne cibler que les bons plans.\n"
            "`/track list` · `/track remove id:<n>`"
        ),
        inline=False,
    )
    e1.add_field(
        name="③ Boutons sous chaque alerte",
        value=(
            "🔗 **Ouvrir** : va direct sur la page d'achat (panier eBay / article Vinted / page CM)\n"
            "💶 **Marge** : break-even + marge par plateforme sur ce prix\n"
            "✅ **Acheté** : marque le deal (compté au digest)\n"
            "🔕 **Mute** : coupe cette recherche"
        ),
        inline=False,
    )
    e1.add_field(
        name="④ Ventes réussies — `/sold`",
        value="`/sold platform:ebay query:\"charizard 151\"` → prix min / médian / max + dernières ventes.",
        inline=False,
    )
    e1.add_field(
        name="⑤ Suivi de prix d'une carte — `/monitor`",
        value=(
            "Publie le suivi dans le salon courant (ou `salon:` au choix) : prix mini, **vrai total "
            "d'offres**, tendance & moyennes 7j/30j Cardmarket, graphique.\n"
            "`/monitor create card:<nom ou URL Cardmarket> [salon:#salon]` · `/monitor list` · `/monitor remove`"
        ),
        inline=False,
    )

    e2 = discord.Embed(title="📖 Guide du bot UwUTCG — 2/2", color=0x5865F2)
    e2.add_field(
        name="⑥ Rentabilité — `/calc` & `/convert`",
        value=(
            "`/calc compute value:5000 currency:jpy` → point mort + paliers (eBay/CM/TikTok)\n"
            "`/calc bind` → fais de ce salon un **salon calculateur** : écris juste `12000 jpy ebay`, "
            "`35€ cm` ou `5000¥` et le bot répond\n"
            "`/calc rates` (taux) · `/convert amount:5000 currency:jpy`"
        ),
        inline=False,
    )
    e2.add_field(
        name="⑦ Arbitrage Japon→France — `/arbitrage`",
        value=(
            "Scanne **Mercari JP** et alerte si la revente FR dégage une marge ≥ seuil. "
            "Bouton **Commander sur FromJapan** sur l'alerte.\n"
            "`/arbitrage watch query:\"pikachu psa 10\" min_margin:30` · `list` · `remove`"
        ),
        inline=False,
    )
    e2.add_field(
        name="⑧ Grading & scellé",
        value=(
            "`/grading-roi card:\"<nom>\" company:psa` → plus-value nette + point mort par note\n"
            "`/sealed watch product:\"display SV ...\" buy_below:90` → alerte sous seuil · `list` · `remove`"
        ),
        inline=False,
    )
    e2.add_field(
        name="⑨ Cartes & connaissances",
        value=(
            "`/carte nom:jinx [prix:true]` → fiche carte Riftbound (+ prix Cardmarket)\n"
            "`/riftbound`, `/pokemon`, `/condition`, `/grading` → base de connaissances"
        ),
        inline=False,
    )
    e2.add_field(
        name="⑩ Notifications (ping) & réglages",
        value=(
            "`/notify on` → être pingué sur les alertes (tracking, monitoring, digest)\n"
            "`/notify add user:@X` → pinguer quelqu'un d'autre · `/notify list` · `/notify off`\n"
            "_(le créateur d'un /track ou /monitor est ajouté automatiquement)_\n"
            "`/config poll-intervals` · `/config set-poll-interval platform:vinted seconds:90`"
        ),
        inline=False,
    )
    e2.add_field(
        name="💡 Astuces",
        value=(
            "• Quand tu ajoutes une recherche, le bot **n'alerte pas** sur les annonces déjà en "
            "ligne (pas de flood) — seulement les nouvelles.\n"
            "• Le paiement final reste toujours de ton côté (les boutons t'amènent juste à la page)."
        ),
        inline=False,
    )
    return [e1, e2]


class InfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="info", description="Comment utiliser le bot (guide complet)")
    async def info(self, interaction: discord.Interaction):
        await interaction.response.send_message(embeds=build_info_embeds(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCog(bot))
