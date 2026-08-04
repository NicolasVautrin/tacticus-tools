# case-589-r1-r1-r2 — le PRODUIT « compteur rebranché × seuil franchi », confronté

`#589-r1-r1-r2`. Les deux moitiés existaient, leur produit non : #589-r1 mesure le **compteur**
rebranché sur le `ConnectivityComponent` (17/17 accord CANAL, deux boards à `Bridge`), #589-r1-r1
mesure le **seuil** d'`EmpyricAmbush` (7 mesures, 7 accords) — mais sur `MC1_67`, un board **sans
pont**, donc dégénéré pour le compteur. Aucune mesure ne jouait les deux à la fois.

## 1. La question binaire, et sa réponse mesurée

> « Existe-t-il un trajet où le compteur rebranché fait FRANCHIR le seuil d'`EmpyricAmbush`, et le
> port s'accorde-t-il au natif sur ce trajet ? »

**OUI, et il s'accorde — 3 trajets, 2 boards, 2 régimes, 3 accords.** Sur chacun, la GÉOMÉTRIE dit
« sous le seuil » et le substrat STOCKÉ dit « au-dessus » :

| board | régime | trajet | `n_G` | `n_C` | **NATIF** | LIVE | port CANAL | port GÉOMÉTRIE (avant #589) |
|---|---|---|---|---|---|---|---|---|
| `C1_74` | `Fly` (`blackHaarken`) | `(1,5) -> (4,4)` | 3 | 4 | **4** | `[3087, 2591, 2338, 2459]` | == | `[1590, 1707, 2129, 1454]` |
| `C1_74` | `TeleportStrike(+Fly)` (`bloodIntercessor`) | `(1,5) -> (4,4)` | 3 | 4 | **4** | `[8338]` | == | `[6836]` |
| `C3_14` | `Fly` | `(3,2) -> (4,3)` | 2 | 5 | **5** | `[2367, 3355, 3247, 2841]` | == | `[1802, 1940, 2066, 1694]` |

⇒ **le rebranchement change la DÉCISION, pas seulement un nombre.** Sans lui, le port aurait lu
`n_G = 3` (ou 2), refusé le gate, et rendu ~46 % de dégât en moins sur la salve de `C1_74`.

**Recoupement croisé, non cherché** : la ligne `C3_14` rend **exactement** les deux vecteurs du
tableau de `case-589-r1-r1` mesurés sur `MC1_67` — `[2367,3355,3247,2841]` avec buff,
`[1802,1940,2066,1694]` sans. Le buff produit le même delta sur deux boards et deux géométries : le
seuil ne dépend pas du board, c'est bien le COMPTEUR qui en dépend.

## 2. Les quatre bras — et trois sont des contre-épreuves

1. **LIVE** — le natif, l'oracle ;
2. **port CANAL** (état livré) — doit égaler le live. *Il l'égale, et son compteur égale le natif.*
3. **port GÉOMÉTRIE** — `Board.base_add_neighbours` → `neighbours_geometric`, l'état d'**AVANT**
   #589. Doit diverger, **et son compteur doit valoir `n_G`** : c'est ce second point qui prouve
   que la MUTATION A MORDU (mesuré : 3 / 3, 2 / 2, 5 / 2) ;
4. **port NOCHANNEL** — l'effet retiré d'`EFFECT_CLASSES` (retombe sur `BaseEffect`, deux canaux
   `None`). Doit égaler le bras 3. *Il l'égale, aux trois trajets*, ce qui **identifie la cause** :
   c'est le buff qui manque en géométrie, pas un effet de bord du changement de substrat.

**Le bras 3 interdit l'accord dégénéré ; le bras 4 interdit la mauvaise attribution.** Et le
**TÉMOIN** (`--temoin`) ferme la dernière porte : sur un trajet où `n_G == n_C = 8 >= 4`, la
mutation de substrat rend **exactement** le live (`[3087, 2591, 2338, 2459]`, compteur 8 des deux
côtés) tandis que `NOCHANNEL`, lui, mord. La mutation n'est donc pas un marteau qui casserait tout
rejeu — elle ne déplace le résultat que là où les deux substrats divergent.

## 3. Le GISEMENT, chiffré — combien de trajets basculent, sur combien examinés

`--only SCAN`, critère `n_G < movement <= n_C` (seuil **relu du gameconfig**, jamais codé en dur) :

| board | `Bridge` | couples marchables | `Fly` | `TeleportStrike(+Fly)` | formes d'écart |
|---|---|---|---|---|---|
| `C1_74` | 2 | 3540 | **20** (0,56 %) | **20** | `3 -> 4` × 20 |
| `C3_14` | 15 | 870 | **68** (7,8 %) | **68** | `2->4`×12, `2->5`×8, `2->6`×2, `3->4`×28, `3->5`×16, `3->6`×2 |

Le second board n'est pas une redite : il multiplie la **densité** par 14 et ouvre **six** formes
d'écart au lieu d'une. `Walk` est absent des deux colonnes **par mesure** (0 basculement sur
3906 couples × 2 boards, `case-589-r1` §3) — il ne discrimine rien et n'est pas joué.

## 4. Ce que le montage a coûté, et qui resservira

* **Le trajet ne se choisit pas à la distance hex — il se CALCULE.** Le montage de #589-r1-r1
  visait `hexgeo.distance(start, step_to) == dist` ; ici le critère est `n_G < K <= n_C`, deux
  appels de `MovementQuery$$GetConnectedPathTo` sous substrat imposé. Sur `C1_74`, **20 couples sur
  3540** le satisfont : le tirer à la distance revient à ne jamais tomber dessus.
* **Il faut le RE-CALCULER après le cast.** Le `FlyUnit` de
  `EmpyricAmbushAbility$$ExecuteBehaviour` téléporte Lhykhis sur une adjacente de la cible —
  potentiellement la tuile visée. Le plan choisit donc l'ancre qui laisse le PLUS de `step_to`
  discriminants, puis re-balaie depuis la position réelle de l'attaquant.
* **L'ancre se choisit en adjacence NATIVE**, jamais `hexgeo.distance <= 1` :
  `MovementUtil$$AreTilesAdjacent` vaut `(|Δelev| < 2) & ConnectivityComponent$$IsNeighbour`. Une
  ancre géométrique fait rendre au natif une attaque hors de portée (`case-589-r1` §6).
* **`eldarLhykhis` n'est pas au pool** → `catalog_inject.write_augmented_seed_bc`, et elle est
  posée à distance 2 de l'ancre **avant** le cycle de tour pour que le cast passe.
* **`--crit 100,700`** : tous les coups critent des deux côtés, donc ce qui bouge est
  `extraCritDmg` — écart déterministe, aucun tirage.

## 5. Les gardes

* `tests/engine/runner/test_empyric_ambush_threshold_live.py` — **9 passed** (5 de #589-r1-r1 + 4).
  `test_le_compteur_rebranche_fait_franchir_le_seuil` est **paramétré sur les 3 trajets** ;
  `test_hors_trajet_discriminant_le_substrat_ne_change_rien` est le témoin. Le montage est
  **importé** du probe, pas retranscrit.
* `scripts/python/probe_589r1r1r2_produit_canal_seuil_live.py` — deux crans : `SCAN` (le gisement
  chiffré, aucun montage) et `DUEL` (le carré à quatre bras, avec ses gardes de régime — un trajet
  non discriminant est REFUSÉ, jamais rendu vert).

## 6. Reproduction

    python probe_589r1r1r2_produit_canal_seuil_live.py --only SCAN --boards C1_74,C3_14
    python probe_589r1r1r2_produit_canal_seuil_live.py --only DUEL --board C1_74
    python probe_589r1r1r2_produit_canal_seuil_live.py --only DUEL --board C1_74 --attacker bloodIntercessor
    python probe_589r1r1r2_produit_canal_seuil_live.py --only DUEL --board C3_14
    python probe_589r1r1r2_produit_canal_seuil_live.py --only DUEL --board C1_74 --temoin
    python -m pytest tests/engine/runner/test_empyric_ambush_threshold_live.py

## 7. Ce qui n'est PAS couvert

* **Deux boards à `Bridge` sur les ~287 estimés.** Les 285 autres ne sont pas balayés — et le
  contraste 0,56 % / 7,8 % dit que la densité n'est **pas** estimable depuis un board.
* **`TeleportStrike(Walk)` (ptype 6) n'est pas joué en DUEL.** Le SCAN le donne identique au
  ptype 7 sur les deux boards, mais aucune salve n'a été mesurée dans ce régime.
* **`extraCritChance` reste saturé** par `--crit 100,700` : seul `extraCritDmg` est discriminé.
  C'est le régime le plus fort (déterministe), pas le plus complet — le canal CHANCE de 1578 n'est
  confronté par aucune mesure de cette famille.
* **La POSE (`EmpyricAmbushAbility` 1232) reste non portée** (`#589-r1-r1-r1`) : l'effet arrive
  dans l'état du port par la capture live, jamais par le moteur.
* **`AmuletOfTheVoidwyrm_CritDamageReduction` reste NON PORTÉ** (`#589-r1-r1-r2-r1`) —
  `ForSubtraction(get_OwnerIsTarget, …)`, l'axe RÉDUCTION du canal crit-dégât, rendu **atteignable**
  par l'élargissement du balayage de #589-r1-r1 sans être porté.
* **La face PRÉDICTION n'est pas touchée** : `services/damage_prediction.py` n'appelle pas
  `crit_chance_bonus_from_effects` (gap préexistant, `case-366-r1` §6.4).
