# #433-r4-r1-r4-r2-r4 — l'AVAL du basculement d'adjacence

**MESURE, pas port** — aucune écriture dans `engine/`. (chiffres en cours de consolidation)

## 1. La question

#433-r4-r1-r4-r2 (PR #606) a montré que `battle_query.is_adjacent` **change de verdict** quand on le
branche sur la liste stockée du `ConnectivityComponent`, et que **le natif est d'accord** (oracle
indépendant : le splash de `FragBomb`). Solde : **4** arêtes permissives fermées sur `C1_74`, **38**
sur `C3_14`, **0** restrictive.

Non mesuré jusqu'ici : est-ce que ça change une **DÉCISION** ? L'imitation learning se moque d'un
nombre qui bouge ; il se soucie d'un **choix** qui diffère.

## 2. Le discriminant, et la SURFACE exacte de la mesure

Comparaison **DIRECTE des deux substrats du MÊME port**, sur le MÊME état live — le natif n'entre
pas dans cette mesure (un critère à trois valeurs noierait le cas utile, leçon de `#589-r1`) :

    NAT = `is_adjacent(t, p, elev, neigh)`   <- ce que le port fait DEPUIS #606
    GEO = `is_adjacent(t, p, elev, None)`    <- ce qu'il faisait AVANT

**Le patch porte sur la PRIMITIVE, jamais sur le canal.** `neigh_by_pos` a d'autres lecteurs qui le
lisent directement (l'ordre natif des voisins pour la cible exacte de `GauntletsOfUltramar`, #117) et
qui, eux, sont identiques dans les deux états du dépôt : neutraliser le canal mesurerait autre chose.

**Surface**, dérivée du code (parcours AST, pas un grep) : **65** call-sites passent le canal aux
quatre primitives d'adjacence, **15** ne le passent pas — ces derniers restent géométriques *dans
les deux substrats*, donc structurellement invisibles à cette mesure. Ce sont exactement les
résidus déjà nommés (`#433-r4-r1-r4-r2-r1` : `in_arc`, `is_charging` ; `-r2` :
`heroic_fusillade`) plus `entities/triggers.py`, `runner/abilities/targeting.py`,
`services/movement_query.py`, `utilities/ramming_speed.py`, `runner/operations/spawn.py`.

## 3. À compléter
