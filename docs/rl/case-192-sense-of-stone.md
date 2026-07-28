# case-192 — `SereneUnifierSenseOfStone` (effet 1169) : le facteur 2,000 de tout banc embarquant Aun'Shi

## Symptôme

Tout banc de mesure qui embarquait `tauAunShi` rendait un dégât OFFLINE **exactement double** du
dégât LIVE — facteur **2,000** reproductible, identique sur deux cibles d'armures différentes à la
fois (donc pas un accident du nœud de dégât : un rapport constant sur deux régimes de réduction ne
peut venir que d'un modificateur multiplicatif non porté).

## L'artefact natif

`IdunBattle.Entities.Effects.Loki.SereneUnifierSenseOfStoneEffect$$CreateEffectDamageMalusForDefense` :

```
EffectBonus.ForPercentDecrease( DSLFactory.get_OwnerIsTarget,
                                DSLFactory.ConfigVar(0x46, GetAbilityState(effet), mult@+0x60),
                                Nullable<AbilityOrEffect>(0x479 = 1145 SereneUnifier) )
```

`get_OwnerIsTarget` **SEUL** : aucun gate mêlée/ranged, aucun gate de profil de dégât, aucun gate
normal-vs-ability, aucune `ActiveCondition`. `ConfigVar(0x46)` = `dmgReductionPct` de la config
`SereneUnifier` (25 → 50, plateau à 50 dès L50 ; **hors** `variablesAffectedByRarityBonus =
['extraDmg']` ⇒ le multiplier de rareté est inerte). C'est le jumeau structurel exact de
`VexillaMagnifica_DmgReduction`.

`...SenseOfStoneEffect$$.ctor` = `BaseEffect..ctor(this, AbilityOrEffect(0x479), 1, 0)` ; la classe
n'a **que** ces deux méthodes (table de symboles du build : aucun `CreateTargetSelector`, aucun
`CreateActiveCondition`).

## Le piège de classification, et ce qui le tranche

Le résidu était libellé « **aura d'équipe** ». Une aura se porte côté SOURCE
(`create_aura_defense_damage_malus_for_ally`, l'effet vit sur le porteur et se projette par un
`CreateTargetSelector`). **Ce n'est pas le cas ici**, et c'est le décompilé qui tranche :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour` pose la
phase 1 par

```
AddEffect(0x491, AbilityStateReference, source = owner@0x160, targets = <sélecteur>, TurnsFromRounds(1))
```

— un `AddEffect` **sur un sélecteur**. L'effet est donc **matérialisé sur chaque bénéficiaire** :
il apparaît dans `decisionView.units[].effects` de CHACUN (`source` = Aun'Shi), et son unique nœud
de déclenchement est `get_OwnerIsTarget`. ⇒ canal **DÉFENSEUR standard**
(`create_effect_damage_malus_for_defense`), pas un canal aura. La mesure le confirme : sur le banc,
les trois bénéficiaires attendus portent bien 1169.

Le sélecteur (qui appartient à la POSE, pas à l'effet) :
`(AdjacentFriends(owner, 1) + owner) + UnitsFromFaction(SurroundingFriends(owner, ConfigConst(0x16) =
range = 2) − AdjacentFriends(owner, 1), UnitFaction.Tau = 9)` = Aun'Shi **lui-même** + ses amis
adjacents (toute faction) + ses amis T'au à distance 2.

## Le cycle complet (contexte, hors périmètre du port)

Trigger `On(0x13 = TurnStarted) & <cond@0xa0> & get_OwnerIsCaster`, puis
`Modulo(PlayerTurnsStarted(owner), 3)` :

| modulo | effet posé | nature |
|---|---|---|
| **1** | `0x491` = 1169 `SenseOfStone` | `AddEffect` → classe d'effet dédiée (**ce port**) |
| **2** | `0x492` = 1170 `ZephyrsGrace` | `AddStaticStatModifierEffect` stat 1 = MOVEMENT, `ConfigConst(0xe)` = `extraMovement` = 1 |
| **0** | `0x493` = 1171 `StormOfFire` | `AddStaticStatModifierEffect` stat 0 = ATTACK, `ConfigVar(8)` = `extraDmg` |

(+ les trois jumeaux `_Visual` 0x498/0x499/0x49a, posés sur Aun'Shi **seul**, cosmétiques.)
1170/1171 sont des stat-mods **génériques** : ils n'ont aucune classe d'effet native et suivront le
port de la POSE, pas un port d'effet.

## Isolation — trois bancs, une seule variable

Le constat de départ (« tout banc embarquant `tauAunShi` ») est un constat de BANC : il fallait
prouver que 1169 en est bien la cause, et pas une autre unité / un autre étage.
Véhicule : cast 1137 `MurderousSwing` de `worldExecutions` sur 2 cibles adjacentes
(`probe_192_sense_of_stone.py`, MC1_67 seed 20137).

| banc | 1169 présent ? | rapport offline/live |
|---|---|---|
| roster AVEC Aun'Shi, **avant** le turn-start adverse | non | **1,0000** |
| roster AVEC Aun'Shi, après 2 `endturn` | oui (rem=1, src=Aun'Shi) | **2,0000** sur les DEUX cibles |
| roster TÉMOIN (porteur → vanille), **mêmes** 2 `endturn` | non | **1,0000** |

Le premier banc élimine « c'est l'unité » ; le troisième élimine « ce sont les `endturn` ». Il ne
reste que la présence de l'effet. 2,0000 = 1/(1 − 50/100), avec `dmgReductionPct[L50] = 50`.

> **Pourquoi le banc d'origine ne montrait rien sans `endturn`** : le trigger est `On(TurnStarted)`.
> Tant que l'équipe d'Aun'Shi n'a pas DÉMARRÉ un tour, 1169 **n'existe pas**. Un montage qui cast
> sans jamais rendre la main (c'est le cas de `probe_murderous_swing_1137`, par conception) est muet
> sur cette mécanique — ni faux ni juste : hors phase.

## Le port

`SereneUnifierSenseOfStoneEffect` (`scripts/python/engine/entities/effects/loki/damage_reduction.py`),
enregistrée `"SereneUnifierSenseOfStone"` dans `EFFECT_CLASSES` (routage par NOM d'`EffectType`).
`ability_level` (passif) indexe `dmgReductionPct`, `for_percent_decrease(owner_is_caster=False, …)`.

**Résidu assumé** (identique à `FightingRetreat_DamageReduction`) : le natif indexe `ConfigVar` sur
l'`AbilityState` de la **SOURCE** (Aun'Shi — c'est SON `AbilityStateReference` que l'`AddEffect`
passe) ; l'effet seedé depuis `decisionView.effects` porte, lui, le niveau du **PORTEUR**. Les deux
coïncident sur un roster homogène (cas des runners) et divergeraient sur un banc à paliers mélangés.
La **POSE** (behaviour turn-start + cycle Modulo) n'est pas portée : l'effet est consommé tel qu'il
est capté, comme `VexillaMagnifica_DmgReduction` / `PrioritisedEfficiency_DmgReduction`.

## Validation

**Face COMBAT** — `probe_192_sense_of_stone.py`, rapport 2,000 → **1,000** ; bit-exact sur deux
couples (board, seed) : MC1_67/20137 (2457 / 3374) et C3_01/31337 (2694 / 4266).

**Face DÉCISION** — `probe_192_sense_of_stone.py --decision` confronte l'oracle natif
(`decisionView.attackPlans[].ranked[0].dmgMin/dmgMax`) à la prédiction offline, sur un plan dont la
CIBLE porte 1169 : **oracle (2892, 4338) == offline (2892, 4338)**. Sans le port :
offline (5784, 8676) = exactement le double.

> **Ce résultat RÉFUTE une hypothèse inscrite dans le harnais.** `frida/hooks/features/ai-step/projection.ts`
> affirme en commentaire que « `CalculateDamagePredictionScenario` models only armor + stat caps » et
> que les réducteurs défensifs trigger-based ne tirent qu'à la résolution réelle — en citant **Aun'Shi**
> en exemple (`predOptimistic`, seed 80072). C'est **faux pour 1169** : la prédiction NATIVE applique
> bien la réduction. Le flag n'est d'ailleurs pas levé ici (son regex
> `/Reduce(Dmg|Damage|Hits)|HitReduction/i` ne matche pas « SereneUnifierSenseOfStone »), donc ces
> échantillons comptent comme *clean* dans `test_predict_live` — le trou y était pleinement exposé.

**Garde** — `tests/engine/runner/test_sense_of_stone_live.py` : dégât reçu par une cible portant 1169,
bit-exact **en mêlée ET en ranged** (le natif n'a aucun gate ; un gate ajouté par erreur casserait
exactement une des deux paramétrisations). Discriminance vérifiée en retirant l'entrée du registre :
les deux paramétrisations ÉCHOUENT sans le port, passent avec.

**Non-régression** — rejoués verts : `test_dakka_dakka_dakka_live`, `test_tau_lot1_live`,
`test_tau_lot1_residues_live` (12 tests — les trois familles qui embarquent `tauAunShi`),
`test_damage_normal_armored_live`, `test_damage_roll_live`, `test_runner_attack_live` (7 tests).

**NON couvert** : (a) la courbe `dmgReductionPct[level < 50]` — `rl_duel build --rank` ne fait PAS
varier `passiveAbilityLevel` (mesuré : 50 à rank 5 comme à rank 17), seule l'entrée L50 = 50 est
confrontée live ; le port lit néanmoins la courbe entière via `ability_var`. (b) la POSE et le cycle
Modulo (hors périmètre). (c) le résidu niveau-SOURCE ci-dessus, non exercé faute de banc à paliers
mélangés.
