# Grading — sociétés et échelles

Le grading consiste à faire évaluer et encapsuler une carte par une société tierce.
Le grade (note) atteste de l'état et authentifie la carte, ce qui peut multiplier sa
valeur — surtout aux notes hautes (9.5, 10). L'écart de prix raw → gradé est le cœur
du calcul de ROI (voir /grading-roi). Attention : seules les cartes en très bon état
brut valent le coût/risque du grading.

## PSA (Professional Sports Authenticator)
Référence mondiale, surtout US, très liquide à la revente.
Échelle entière de 1 à 10 :
- PSA 10 « Gem Mint » : quasi parfaite. C'est la note qui fait exploser la valeur.
- PSA 9 « Mint » : excellent, mais décote nette vs 10.
- PSA 8 « NM-MT », 7 « NM », … jusqu'à 1 « Poor ».
Pas de demi-points (sauf très anciennes exceptions). La population PSA 10 d'une carte
influe fortement sur sa cote. Sous-grades non publiés.

## BGS / Beckett (Beckett Grading Services)
Échelle 1 à 10 AVEC demi-points (8.5, 9.5…).
Quatre sous-notes : centrage (centering), coins (corners), bords (edges), surface.
La note globale n'est pas la moyenne mais dépend de la plus basse + arrondi.
- BGS 9.5 « Gem Mint » : très recherché.
- BGS 10 « Pristine » : rare ; les quatre sous-notes ≥ 9.5.
- « Black Label » : BGS 10 avec les quatre sous-notes à 10 pile — extrêmement rare,
  prime de prix énorme.

## CGC (Certified Guaranty Company)
Issu du comics, monté en puissance sur les cartes (notamment Pokémon).
Échelle 1 à 10 avec demi-points.
- CGC 10 « Gem Mint » et CGC 10 « Pristine » (le Pristine est au-dessus du Gem Mint).
- Souvent moins cher et plus rapide que PSA ; cote en dessous de PSA à note égale sur
  beaucoup de cartes, mais l'écart se réduit.

## PCA (Professional Card Authentication)
Société FRANÇAISE, populaire sur le marché FR/UE (délais et port plus avantageux depuis la France).
Échelle 1 à 10 (PCA 10 en haut). Bon compromis coût/rapidité pour le marché européen,
mais reconnaissance/liquidité moindre à l'international que PSA.

## Autres sociétés
- SGC : réputée (cartes vintage US), coque noire caractéristique.
- AFG, GMA, MGC… : sociétés à bas coût, peu reconnues, faible prime de valeur.
- En Europe/Asie émergent aussi d'autres acteurs ; vérifier la liquidité avant de grader.

## Impact du grade sur la valeur (logique de ROI)
- L'écart raw → gradé n'est rentable que si : (prix gradé attendu − prix raw − coût grading) > 0.
- Le coût grading = tarif société + port aller-retour + assurance (table éditable dans pricing.yaml).
- Le « point mort » est la note la plus basse où la plus-value devient positive.
- Risque : une note inférieure à l'espérée (ex. 9 au lieu de 10) peut annuler le gain.
- Privilégier le grading des cartes brutes proches du Mint, à forte cote en note haute.
