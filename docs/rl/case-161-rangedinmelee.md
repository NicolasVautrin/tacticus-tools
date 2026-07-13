# Case #161 — RangedInMelee sur-appliqué : le trait Ranged (0xb) n'existe sur AUCUNE unité

**Statut** : RE fait (decompile `gqfc5mff6c`) + FIX appliqué + VALIDÉ LIVE (predict_sweep, 2 rosters,
SpiritLeech bit-exact + 0 régression). #161 CLOS.

## TL;DR

Le port appliquait la réduction **RangedInMelee ×0.5** dès qu'une ability était `is_ranged` et qu'un
ennemi mêlée-able était adjacent. FAUX : le natif `ShouldApplyRangedInMelee @181005810` gate sur
**`HasTrait(ATTAQUANT, UnitTrait.Ranged=0xb=11)`** (param_4=0 dans le chemin prédiction), PAS sur
l'ability. Et ce trait 11 **n'est porté par AUCUNE unité** (0 en gameconfig, 0 dans la BC
`Units[].Traits`). => le natif n'applique **JAMAIS** RangedInMelee en prédiction. Le port sur-appliquait
la ×0.5 aux **casters HYBRIDES** (ranged weapon MAIS pas trait Ranged) tirant une ability ranged en
mêlée -> SpiritLeech (Neurothrope) = **×2 faux**.

## RE (VAs, build gqfc5mff6c)

- `DamageCalculations.CalculateRangedInMeleeReduction @181004700` appelle
  `ShouldApplyRangedInMelee(attacker, tiles, state, 0, 0)` -> **param_4 = 0**.
- `DamageCalculations.ShouldApplyRangedInMelee @181005810` :
  `if (adjacent-tiles-exist && (HasTrait(attacker, 0xb) != 0 || param_4 != 0)) { loop: ennemi mêlée-able
  adjacent (team!=att, vivant, CanMeleeAttackOverElevationDifference |Δelev|<2) -> return 1 } return 0`.
  Avec param_4=0 -> gate = **HasTrait(attacker, 0xb)** seul.
- `UnitExtensions.IsRanged @180ed8f00` = `HasTrait(0xb) OR HasRangedWeapon` : comme aucune unité n'a
  le trait 0xb, cette fonction se réduit à `HasRangedWeapon` (la branche trait est morte). Le
  Neurothrope a `HasRangedWeapon=true` mais `HasTrait(0xb)=false` -> pas RangedInMelee (confirmé oracle).
- Trait 11 = runtime-only (assigné à la création de BaseUnitComponent, hors config client) MAIS
  **jamais assigné en pratique** : 0 unité en gameconfig (`units.traits`), 0 dans la BC. Vestigial.

## Fix (offline, aucun reinject/capture)

`engine/playbook/prediction.py::_should_apply_ranged_in_melee` : ajouté le gate natif
`if UnitTrait.Ranged.name not in ctx.traits: return False` (mirror `HasTrait(attacker, 0xb)`). Comme
aucune unité ne porte "Ranged", RangedInMelee devient inerte partout -> matche le natif. Le reste du
corps (ennemi mêlée-able adjacent) est CONSERVÉ : si un jour une unité porte le trait Ranged, il
s'activera fidèlement. (Insight clé, utilisateur : « si ce trait n'existe pas, ça change quoi ? » -> il
ne FAUT PAS capturer un trait absent, il faut juste ne pas appliquer la réduction.)

## Validation live (predict_sweep)

- Roster tyranNeurothrope,tyranTyrantGuard vs orksNob,orksNob (seed 777, MC1_67) :
  SpiritLeech AVANT `[695,1043]` (MAJOR, ×0.5×0.67) -> APRÈS `[1390,2085]` = oracle **bit-exact** (OK).
  Loki_NormalAttack reste OK (aucune régression). (CrushingClaws MAJOR = gap SÉPARÉ, sur-prédiction.)
- Roster tauDarkstrider,custoTrajann vs bloodIntercessor,bloodIntercessor (seed 62062) : ranged unit
  (tauDarkstrider) Loki_NormalAttack OK, **0 régression ×2** (aucune unité ne réclame la ×0.5).
  Bonus : FightingRetreat = ORACLE_EMPTY (valide aussi le fix #110 end-to-end).

## Portée & suivi

Impacte tout caster HYBRIDE tirant une ability/arme ranged en mêlée (psykers, héros melee+ranged).
Le facteur ×2 de HarvesterOfSouls (#163) est à re-confronter : vérifier s'il relevait (partiellement)
de ce même bug ou uniquement du base-override ArcScourge.
