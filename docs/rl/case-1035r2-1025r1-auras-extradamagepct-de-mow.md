# #1035-r2 / #1025-r1 — les deux auras `ExtraDamagePct` de MACHINE OF WAR

Port des deux owner-effects d'abilities **MYTHIQUES** que `#999-r3-r1-r1` venait de débloquer :

| EffectType | Nom | Ability (TriggeredAbilityType) | Porteuse | Résidu |
|---|---|---|---|---|
| `0x5a2` = **1442** | `BlightedLand_ExtraDamagePct` | `BlightedLand` `0x5a7` = 1447 | `deathCrawler` | `#1035-r2` |
| `0x5a9` = **1449** | `MoreGitzOverEre_ExtraDamagePct` | `MoreGitzOverEre` `0x5b0` = 1456 | `orksRukkatrukk` | `#1025-r1` (volet PORT) |

Foyer : `engine/entities/effects/loki/extra_damage_aura.py`.

---

## 1. Même slot natif, canaux de port OPPOSÉS

Les deux implémentent `$$CreateEffectDamageBonusForAttack` (slot ATTAQUANT). Ce qui les sépare est
la **population** que leur `$$CreateTargetSelector` vise :

* **1442** projette sur les **AMIS** de la MoW ⇒ le bénéficiaire est l'**ATTAQUANT** ⇒
  `create_aura_attack_damage_bonus_for_ally` ;
* **1449** projette sur ses **ENNEMIS** ⇒ le bénéficiaire est la **CIBLE DU COUP**
  (`get_OwnerIsTarget`) ⇒ `create_aura_defense_damage_malus_for_ally` **avec
  `AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"`**, le seul agrégateur du port qui balaie les
  porteurs TIERS pour une cible donnée. C'est l'arbitrage exact de
  `DaughterOfTheAbyss_ExtraDamagePct` (#437-r1-r1-r1) : **la face vient de la CLASSE**, pas du
  canal.

Confondre les deux serait **silencieux** — l'effet se contenterait de ne jamais fire.

## 2. Ce qui a été relu au décompilé (et une correction)

`...BlightedLandEffect$$CreateTargetSelector` :

    UnitsOnTilesWithEffect(
        UnitsWithRarity( Friends(Owner@<DSLSelectors+0x30>, AllUnits@<+0x20>, 3), 5 = Mythic, 3),
        0x4dc = EffectType.Contaminated )

**AUCUN étage ne lit la position du porteur** — c'est ce qui rend cette aura évaluable depuis une
MoW, qui n'en a aucune. `Friends(Owner, AllUnits)` est board-wide, `UnitsWithRarity` lit
`GetBaseUnitComponent(e)+0x74`, et `UnitsOnTilesWithEffect` lit la tuile de l'**élément courant**
du sélecteur (donc du bénéficiaire), pas celle du porteur.

⚠ **Son `ForPercentIncrease` est INLINE** (pas d'appel à
`IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease`). C'est la **structure écrite** qui
l'établit, champ par champ contre le corps de la méthode nommée : `+0x00 <- trigger`,
`+0x08 <- formule`, `+0x10..+0x33 <- 0`, `+0x34..+0x4c <- AbilityOrEffect`. Aucun slot additif
écrit ⇒ canal POURCENT.

`...MoreGitzOverEre_ExtraDamagePctEffect$$CreateTargetSelector` (composition, pas ordre des `call`) :

    Unique( Enemies( Owner@+0x30,
        AdjacentUnits( Friends(Owner, UnitsWithVisualId(
                           VisualUnitIdFromUnitId(ConfigConstString(<config>,0)), 1), 3), 1, 3)
      + Filter( AllUnits@+0x20,
                AmountIsEqualOrGreater(
                    Friends(Owner, UnitsWithRarity(AdjacentUnits(<élément@+0x68>,1,3), 5, 3), 3),
                    Direct(2) ) ), 3 ) )

et son trigger : `get_OwnerIsTarget & (AreFriends(Caster@+0x48, EffectSource@+0x38) &
HasRarity(Caster@+0x48, Mythic)) & IsMeleeAttack & IsNormalAttack`.

⚠ `<DSLSelectors+0x68>` est l'**élément courant**, pas une unité nommée — même slot que lit
`UnitsOnTilesWithEffect`. La branche B se lit donc « l'unité évaluée a ≥ 2 amis-du-porteur
Mythiques adjacents ».

⚠ **L'ATTAQUANT compte dans ce seuil** : `AdjacentUnits(<la cible>)` ne l'exclut pas, et
`Friends`/`UnitsWithRarity` le gardent. Le `>= 2` est donc atteignable **à un seul renfort** — fait
LU, et figé par un test (une première rédaction du cliquet l'avait supposé faux).

⚠ `AreFriends(Caster, EffectSource)` est VRAI quand `Caster == EffectSource`
(`UnitExtensions$$IsFriend` n'écarte pas l'égalité) : la MoW qui attaque elle-même touche le bonus.
L'agrégateur DÉFENSE n'exclut que `uid == tgt_id` ⇒ servi **sans code spécial**, et on n'ajoute
surtout pas d'exclusion par imitation du canal ATTAQUE (qui, lui, en a une).

## 3. Câblage : quatre clés neuves au ctx d'aura DÉFENSE, sur les DEUX faces

`att_rarity`, `is_normal_attack`, `tgt_adjacent_unit_profiles`, `tertiary_ability_state_of`
(cette dernière côté COMBAT seul — la face PRÉDICTION n'a pas de foyer et retombe sur le repli
nommé, comme `NornCrown` / `HeadwoppasKillchoppa`).

Le substrat d'adjacence est un **arbre DSL dans la classe d'effet** (doctrine #149) —
`more_gitz_adjacent_units_selector()` — dont les deux faces donnent l'`AbilityEntities` :
`runner/components.py::adjacent_unit_ids` et `playbook/scene.py::Scene.adjacent_unit_ids`. Donc la
**liste STOCKÉE** avec la porte d'élévation, jamais un `hexgeo.distance == 1`.

1442, lui, n'a eu besoin d'**aucune clé neuve** : `att_rarity` et la MAIN TILE de l'attaquant dans
`tile_effects_by_pos` avaient été posées **pour lui** par #999-r3-r1.

## 4. Confrontation LIVE — régime SÉPARANT, témoin non nul

`aiPredict` (preview natif `GetAllPredictions`) contre `make_normal_attack_predictions`.

**1442** (`probe_1035r2_blighted_land_bonus_live.py`) — le terrain vient de la **porteuse
elle-même** : `deathCrawler` porte l'active `PlagueburstMortar` (1169), dont l'`ExecuteBehaviour`
finit par `AddEffect(Contaminated, <tuile ciblée> + <tirées>)`.

| bras | aura | tuile | natif | port | pct-list |
|---|---|---|---|---|---|
| `on` | posée | Contaminated | (4773, 7161) | **(4773, 7161)** | `+50 élévation`, `+10 BlightedLand` |
| `off` | absente | Contaminated | (4341, 6510) | (4341, 6510) | `+50 élévation` |
| `rarity` | posée | Contaminated | (4341, 6510) | (4341, 6510) | `+50 élévation` |

**1449** (`probe_1025r1_more_gitz_bonus_live.py`) — géométrie forcée par `--place`/`--a-place` :
(3,3) `orksNob` attaquant, (2,4) `orksWarboss` renfort, (3,4) `necroWarden` cible.

| bras | natif | port | pct-list |
|---|---|---|---|
| `on` | (3183, 4773) | **(3183, 4773)** | `+10 MoreGitzOverEre` |
| `off` (pas de mythique) | (2895, 4341) | (2895, 4341) | — |
| `caster` (Nob → Epic) | (2895, 4341) | (2895, 4341) | — |
| `count` (Warboss → Epic) | (2895, 4341) | (2895, 4341) | — |

**Accord bit-exact partout.** Le bras `off` de 1442 **tire le mortier lui aussi** : sans cela il
différerait par DEUX choses (l'aura *et* le terrain, `Contaminated_Unit` compris, qui réduit
l'armure de l'occupant).

⚠ `caster` et `count` **ne sont pas redondants** : en `caster` les deux gates tombent ENSEMBLE
(l'attaquant perd son `HasRarity` *et* sort du compte des voisins). Seul `count` isole
`AmountIsEqualOrGreater(..., Direct(2))`.

## 5. Deux pièges de MONTAGE, mesurés

1. **Une `Scene` sans `elev_by_pos` ni `tile_effects_by_pos` dégrade EN SILENCE.** Mesuré : la
   sonde 1442 rendait `4341` côté port contre `4773` côté natif — **une fausse divergence de 10 %
   imputable au seul harnais**. `engine/ai/context.py` construit toujours ces deux tables depuis
   `tileMeta` ; les omettre ferme tout gate positionnel ou de tuile.
2. **Un board synthétique doit porter `neighbours` DÉJÀ filtré par `|dElev| < 2`.** C'est
   l'identité LUE du substrat (`Board.base_add_neighbours`) : le champ est capté à travers
   `TileQuery.IterateAdjacentTiles`. Avec la couronne hex nue, un port qui lirait
   `hexgeo.distance == 1` passe tous les étages.

## 6. On ne fitte pas le scalaire

Une première rédaction du cliquet live comparait le rapport `on/off` à `1 + pct/100` et **rougissait
sur un port juste** (4773 contre 4775 attendus). Le natif accumule le pourcentage dans
`attackModifiers`, consommé AVANT perçage/armure par `DamagePrediction$$CalculateBaseDamageWith
AllModifiers`, avec un `Fix64.Round` par accumulateur non nul. Les tests comparent donc la
**décomposition par étage** (`base`/`pierce`/`armor`/`hits` identiques ; seule l'entrée
`PercentIncrease(extraDmgPct)` diffère).

## 7. Cliquets

* `tests/engine/runner/test_1035r2_1025r1_auras_mow_offline.py` — 39 cas, 6 étages ;
* `tests/engine/runner/test_1035r2_blighted_land_bonus_live.py` — 4 cas ;
* `tests/engine/runner/test_1025r1_more_gitz_bonus_live.py` — 5 cas.

Deux crans qui **figeaient l'absence** ont rougi, au moment prévu, et sont **requalifiés** :
`test_1035_mythiques_mow_offline::test_verrou_de_rarete_fige_avec_sa_raison` et son jumeau
`test_1025_electrochaff_backups_offline`. Chacun garde désormais l'**inscription** + un contre-bras
de rareté (l'inscription ne doit pas avoir coûté le gate).

## 8. Résidu

`#1035-r4` — la face **COMBAT** (`damage_model`) des deux auras n'est confrontée qu'OFFLINE ; la
face PRÉDICTION l'est live. Même forme que `#1025-r3` pour 1446.
