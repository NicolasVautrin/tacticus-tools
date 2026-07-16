# Case #191 — BeaconOfRage_FriendlyExtraDamage (0x513=1299) : aura +50% du bonus rage aux amis Chaos adjacents

**Status : PORTÉ + VALIDÉ OFFLINE + RE COMPLÈTE (decompile-citée, gqfc5mff6c). LIVE CONFRONT
PENDING** (l'unique confirmation manquante : le pipeline de PRÉDICTION natif folde-t-il cette aura
PROJETÉE de type DamageBonus sur l'attaque MÊLÉE d'un ami ? — scénario stateful difficile à driver,
cf. §Validation). Variante AURA du self BeaconOfRage (0x512=1298, porté+bit-exact #189).**

## Ce que c'est (i2)
« 50% of the extra damage from Beacon of Rage is added to the damage of melee attacks of adjacent
friendly Chaos units. » Actif SSI Azkor (worldEightbound) a ≥1 kill.

## RE native (decompile-citée, build gqfc5mff6c) — INTÉGRALE

### L'effet vit sur le PORTEUR (Azkor), pas sur les amis — c'est une AURA
`ABeaconOfRageAbility.GetUpdateFriendEffectBehaviour @180e13040` :
```
level = If(UnitsDefeatedAmount(owner@0x148) > 0, GetCurrentSelfEffectLevel, 0@0xb8)   // = GetCurrentFriendEffectLevel
If(UnitsDefeatedAmount>0 & !HasEffect(owner, 0x513), AddEffect(0x513, abilityStateRef, owner@0x148, owner@0x148))
If(HasEffect(owner, 0x513), SetEffectLevel(owner@0x148, 0x513, level))
```
`AddEffect`/`SetEffectLevel`/`HasEffect` ciblent tous **owner@0x148 = Azkor** ⇒ l'effet 0x513 est
matérialisé SUR AZKOR (capté dans `decisionView.effects` d'AZKOR, JAMAIS des amis). Modèle identique à
`DaughterOfTheAbyss` (#184) : effet hosté sur le porteur + `CreateTargetSelector` projeté → canal AURA
CÔTÉ SOURCE. `GetCurrentFriendEffectLevel @180e12f10` = la même logique isolée.

### Valeur = 50% du bonus SELF
`BeaconOfRage_FriendlyExtraDamageEffect.CreateEffectDamageBonusForAttack @180f33370` :
```
trigger = get_OwnerIsCaster & IsMeleeAttack
value   = PercentageOf( Multiply( ConfigVar(8=extraDmg, GetAbilityState, config@0x60),
                                  EffectLevel(effet@0x150) ),
                        0x32=50, mode 0 )
```
= `ForAddition` (même canal additif `DamageModifiers.Add` que le self 0x512 @180f33130 = `ForAddition(
OwnerIsCaster, Multiply(ConfigVar extraDmg, EffectLevel))`). Donc **friendly = round_half_even(self_bonus
× 50/100)** avec `self_bonus = extraDmg[ablvl Azkor] × rage`. `PercentageOf` mode 0 = Fix64 round
half-to-even (`dsl/base.py::_round_fix64`). `FriendlyDamageBonus @180f33610` = même Multiply(ConfigVar,
EffectLevel) avant le PercentageOf (helper miroir).

### Sélecteur = amis Chaos adjacents
`CreateTargetSelector @180f335b0` : `UnitsWithTrait( AdjacentFriends(owner@0x148, 1, 3), 0x7ea=2026=Chaos, 3 )`
= amis d'Azkor ring-1 (hex-adjacents) de grande-alliance **Chaos**.

### Trait 2026 = grande-alliance Chaos (dérivé de GrandAllianceId, PAS gameconfig.traits)
`GrandAlliance.GetTrait @1815647a0` : Imperial→0x1a=26, Xenos→0x3ee=1006, **Chaos→0x7ea=2026**. Comme
le gate Imperial de RitesOfBattle (#49/#153), ce trait de grande-alliance est ABSENT de
`gameconfig.units.traits` → gate via `att_grand_alliance == "Chaos"` (GrandAllianceId capté).

### Magnitude/level
- `extraDmg` = `ConfigVar(8, GetAbilityState)` = ability_var BeaconOfRage indexée sur l'ablvl PASSIF
  d'AZKOR (source), scale multiplier no-op (hors variablesAffectedByRarityBonus, cf. #189).
- `rage` = `EffectLevel(0x513@Azkor)` = `GetCurrentFriendEffectLevel` = `If(kills>0, Min(TotalTimesAttacked,
  8), 0)` : ÉCRIT à SetEffectLevel, capté tel quel dans `decisionView.effects[].level`. ⇒ la PRÉSENCE de
  l'effet + son level encodent DÉJÀ le gate ≥1-kill + la rage → on lit `self.level` directement (comme le
  self, PAS de recalcul offline de UnitsDefeatedAmount).

## Port
- `entities/effects/base.py` : nouveau hook aura `create_aura_attack_damage_bonus_for_ally(ctx)`
  (symétrique ALLIÉ de `create_aura_attack_damage_malus_for_enemy` / ShadowInTheWarp). Défaut None.
- `entities/effects/loki.py::BeaconOfRageFriendlyExtraDamageEffect` : gates `is_melee` + ami-d'Azkor
  (att_team==owner_team) + exclut self + hex-adjacent (dist≤1) + `att_grand_alliance=="Chaos"` ;
  valeur `for_addition(True, round(Fraction(extraDmg[ablvl]×rage × 50, 100)))`. Gate rage≤0 / ablvl None
  → inerte.
- `entities/effects/__init__.py` : agrégateur `aura_attack_damage_bonus_from_allies(carriers, ctx)` →
  list[EffectBonus] (mirror `aura_attack_damage_malus_from_enemies`) + export.
- `entities/effects/factory.py` : registre `"BeaconOfRage_FriendlyExtraDamage"` (nom capté =
  effect-type-names.ts:422).
- `playbook/prediction.py` : après la boucle `aura_attack_damage_malus_from_enemies`, boucle
  `aura_attack_damage_bonus_from_allies` (réutilise `carriers`, ctx {att_id/att_pos/att_team,
  att_grand_alliance, is_melee}) → `add_modifier(mods, eb)` (Addition → `mods.additive`, même canal que
  le self, déjà bit-exact). Le self (Azkor attaque) et l'aura (un ami attaque) portent sur des ATTAQUANTS
  distincts → jamais cumulés.

## Validation
- **OFFLINE (probe_191_offline, 12 checks)** : `value == round_half_even(self_bonus × 0.5)` (self_bonus
  déjà bit-exact #189) ; tous les gates (is_melee, self-exclusion, team, Chaos, adjacence, rage≤0,
  ablvl None) ; agrégateur 8-tuple `carriers`. PASS.
- **LIVE CONFRONT — PENDING (l'unique confirmation manquante)** : mesurer que l'oracle
  `aiPlaybookPredict` d'une attaque MÊLÉE d'un ami Chaos adjacent à Azkor (Azkor ayant ≥1 kill + rage≥1)
  prend bien le +50% FLAT (== engine). Question de fond : le pipeline de prédiction natif folde-t-il une
  aura PROJETÉE de type **DamageBonus** (effet hosté sur X, `CreateTargetSelector` vers l'attaquant Y) ?
  - Le self flat DamageBonus EST foldé en prédiction (#189 bit-exact) ⇒ la prédiction folde bien les
    DamageBonus de `CreateEffectDamageBonusForAttack`. Reste à confirmer que les effets PROJETÉS (hostés
    sur une autre unité, target-sélectionnés) le sont aussi côté ATTAQUANT.
  - Le port a DÉJÀ ce pattern pour ShadowInTheWarp (`aura_attack_damage_malus_from_enemies`, malus ennemi)
    câblé en prédiction — MAIS lui non plus n'est pas bit-exact-confirmé en prédiction (flaggé
    runner-engine.md). Seule l'aura STAT-mod attaquant (RitesOfBattle #49) est live-bit-exact.
  - RE côté attaquant NON tranchée cheap : `CalculateAttackerModifiersForPrediction @181000590` (1395
    lignes) = stat-mods (#196, "NE PAS cabler avant") + élévation + gate interface DAT_1831b7f78 slot 3 ;
    la collecte des EFFECT-DamageBonus (dont projetés) est ailleurs (facade prédiction). Non résolu ici.
  - **Scénario de confront (à driver)** : roster Azkor (worldEightbound) + ami Chaos mêlée (worldJakhal)
    adjacents ; driver jusqu'à Azkor ≥1 kill ET attaqué ≥1 fois (rage) ; vérifier
    `decisionView.effects[Azkor]` contient "BeaconOfRage_FriendlyExtraDamage" ; confronter la mêlée de
    l'ami. Difficulté = compteurs de bataille STATEFUL (kill + attacked) non injectables, seulement
    gagnés en sim multi-tours.
  - **Risque si le natif NE folde PAS** : sur-application en prédiction (over-application) → scoper au
    combat/runner. Surface de régression PETITE (gate serré : Chaos + adjacent + mêlée + kill + rage).

## Anchors
GetUpdateFriendEffectBehaviour @180e13040 ; GetCurrentFriendEffectLevel @180e12f10 ;
CreateEffectDamageBonusForAttack @180f33370 ; CreateTargetSelector @180f335b0 (AdjacentFriends 1,3 +
UnitsWithTrait 0x7ea) ; FriendlyDamageBonus @180f33610 ; GrandAlliance.GetTrait @1815647a0 (Imperial 26 /
Xenos 0x3ee / Chaos 0x7ea) ; self BeaconOfRage @180f33130 / GetCurrentSelfEffectLevel @180e12fa0 (#189).
Port : loki.BeaconOfRageFriendlyExtraDamageEffect, effects.aura_attack_damage_bonus_from_allies,
prediction (boucle aura alliée). Probe : scratchpad probe_191_offline.py. Cf. case-185 (BoK/BeaconOfRage),
#189 (self porté bit-exact), #190 (OverwhelmingWrath RangeDmgReduction).
