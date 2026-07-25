# Tâche #95 — Contributions des buffs Waaagh (effets 1100 `+extraDmg` / 1101 `+extraHit`)

Build `gqfc5mff6c`. Résidu n°1 de [`case-94-summon-consumers.md`](case-94-summon-consumers.md) §9 :
les marqueurs 1100/1101 étaient **posés** mais leurs contributions **jamais lues**. Elles le sont
maintenant, et **confrontées au live** (`test_waaagh_buff_contrib_live.py`, 6 tests).

Convention de citation : symbole Ghidra verbatim (aucune VA nue).

---

## 1. Les deux canaux natifs (mirror 1:1)

```
IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack
    EffectBonus.ForAddition( IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster,
                             ConfigVar(8 = extraDmg, GetAbilityState(effet), effet+0x60) )

IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack
    EffectBonus.ForAddition( MÊME condition,
                             ConfigConst(0x2b = extraHit, effet+0x60) )
```

JUMEAUX EXACTS : même chaîne `IsNormalAttack` → `op_BitwiseAnd(IsMeleeAttack)` →
`op_BitwiseAnd(get_OwnerIsCaster)` → `ForAddition(cond, <amount>)`. Seule la magnitude diffère
(variable per-niveau vs constante). `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$.ctor`
= `BaseEffect(AbilityOrEffect(0x422 = 1058 Waaagh), 1)` → la config lue est celle de l'ability **Waaagh**.

`OwnerIsCaster` est vrai **par construction** sur ces deux canaux : ils ne sont invoqués que pour les
attaques du PORTEUR (`_attacker_effect_bonuses` / `hits_bonus_from_effects`).

**Port** : `engine/entities/effects/loki/status.py` — `WaaaghExtraDamageEffect
.create_effect_damage_bonus_for_attack` (canal additif `DamageModifiers.Add`, même que SmashaEad /
DecoysAndMisdirection / LordOfTempests) et `WaaaghExtraHitsEffect.create_effect_hits_bonus_for_attack`
(axe COUPS, même que `PowerTrip_FullHealthEffect` — dont le gate n'a PAS le `IsMeleeAttack` d'ici).
La nature du coup arrive par `att_ctx["is_melee"]` (= le `board` de
`IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`, peuplé par les DEUX façades).

## 2. La magnitude : niveau du POSEUR, multiplier RÉSOLU = 100

Chaîne native : `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` →
`IdunBattle.Entities.Formulas.ConfigAmount$$GetAbilityState` (branche « sélecteur
`AbilityStateFromEffect` », `IdunBattle.DSL.AbilityStateFromEffectSelector$$Select` →
`EffectComponent.AbilityState @0x18`) → slot 0xd4 du `BattleQuery` →
`IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` →
`IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`.

Ce dernier applique **`Round(v × AbilityState.VariableMultiplierPercentage / 100)`** — mais UNIQUEMENT
si la clé appartient à `config+0x28` (= `variablesAffectedByRarityBonus`). `extraDmg` EN FAIT PARTIE →
le multiplier est bien appliqué ; c'est donc le **multiplier résolu** qui vaut 100.

**MESURE LIVE** (`probe_95_waaagh_contrib.py`, MC1_67 seed 31337) :

| grandeur | valeur |
|---|---|
| `effectAbilityStates(1100)` → `stateRaw` | `[81, 1, 1058, 0,0,0,0,0,0,0]` = `Owner=81 (Warboss)`, `Ability=1058`, **`Nullable<AbilityState>` VIDE** |
| Warboss `unitConfig` / `abilityStates[1058]` | `level 50`, `multiplier 200` |
| bénéficiaire (`orksNob`) `unitConfig` | `level 50`, `multiplier 180` |
| preview NATIVE, par coup, avant → après | **min 965 → 1408**, **max 1447 → 1890** ⇒ **+443 constant** |
| `extraDmg[L50]` brut | **443** ✔ (×200 % = 886 ✘, ×180 % = 797 ✘) |

Le facteur 200 est en plus **arithmétiquement réfuté** : 443 est impair, aucun `extraDmg[L] × 2` ne le
produit. Le port lit donc `ability_var("Waaagh", "extraDmg", <niveau ACTIF du poseur>)` **sans
`multiplier_pct`**. (Même famille que le gap #68/#75 « multiplier COMBAT d'un additif d'effet » —
ici **mesuré**, pas supposé.)

Le niveau du poseur arrive côté port par `AddEffect(..., scale_from_source=True)` (le port de
l'`AbilityStateReference` que les TROIS nœuds natifs passent en 2ᵉ argument) →
`runner/abilities/behaviours/effects.py::_source_scaling` → `active_ability_level` de la SOURCE.
No-op sur 1099/1101 (magnitudes constantes), REQUIS par 1100.

`extraHit` est une **constante** (`GetNumberConstant`, branche ConfigConst de `ConfigAmount.Calculate`)
→ jamais scalée. Mesure : **+1 coup** (3 → 4), == `constants.extraHit` = 1.

## 3. Le sélecteur de buff est bien BOARD-WIDE — enfin prouvé live

`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` :

```
Unique( caster@0x160
        + AdjacentFriends(caster@0x160, 1, 3)
        + UnitsFromFaction(Friends(caster@0x160, allUnits@0x80, 3), 5 = Orks, 3) )
```

Lectures qui verrouillent le 3ᵉ terme :
- `IdunBattleLogic.Entities.DSLFactory$$Friends(factory, référence, source, mode)` →
  `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$.ctor` stocke **`+0x18 = référence`** (le caster)
  et **`+0x20 = source`** ; `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd` résout
  `+0x18` en UNE entité (slot 8) et **itère `+0x20`** (slot 5) en filtrant `IsFriend(référence, u)`.
  Aucun rayon.
- `factory+0x80` est construit par `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` avec le
  **même ctor et les mêmes arguments** que `IdunBattleLogic.Entities.DSLFactory$$AllUnits` ⇒ c'est
  bien « toutes les unités vivantes » (le label ghidra `AllAliveMachinesSelector$$.ctor`, refcount 94,
  est un ctor gshared PARTAGÉ — on lit la STRUCTURE, jamais le nom).

**Confirmation live** (dump des effets de TOUTES les unités après le cast) :

| unité | dist. au Warboss (au moment du buff) | Ork ? | buffée ? |
|---|---|---|---|
| `orksWarboss` (caster) | 0 | oui | **oui** |
| `orksNpc2OrkBoy` ×2 (summons) | 1 | oui | **oui** |
| `orksRuntherd` | 4 puis 9 (2 runs) | oui | **oui** |
| `orksNob` | 9 | oui | **oui** |
| `spaceHound` | 2 | **non** | **non** |

⇒ 3ᵉ terme board-wide CONFIRMÉ (Ork à 9 hex buffé) et faction-gaté (non-Ork à 2 hex non buffé, donc
hors ring-1 ⇒ `AdjacentFriends` est bien un rayon 1). Le port était CORRECT ; c'est la **validation
live** qui manquait (cf. §4, piège n°2).

## 4. Trois pièges de mesure — payés, à ne pas repayer

1. **Les buffs `Direct(1)` ont DÉJÀ expiré si le cast épuise le camp.** Le cast termine l'activation
   du Warboss ; si plus aucune unité alliée n'a d'activation, le tour bascule, le TICK de fin de tour
   passe et les 3 effets (durée = 1 TOUR) sont retirés **avant** toute relecture. Première mesure :
   `effects []` sur **TOUTES** les unités, caster compris — on croit à un no-op de pose.
   **Parade** : une unité de mon camp **jamais activée** (ici `spaceHound`) garde le tour OUVERT.
   ⇒ c'est aussi pourquoi le volet live de `test_summon_consumers_live.py
   ::test_waaagh_buff_effects_posed_live_and_port` est conditionnel : il était **vide**, donc vacuum.
2. **`decisionView` GARDE les cadavres.** L'unité de mesure (`orksNob`) mourait à l'approche sous
   l'`Overwatch` de `necroDestroyer` : `decisionView` la publiait toujours (position, PV), `aiPredict`
   rendait une preview figée, et elle n'était (légitimement) jamais buffée — `AllAliveUnits`.
   Symptôme : « le sélecteur n'est pas board-wide ». **Parade** : contrôler `observeBattle.isDead`
   AVANT de mesurer, et choisir une cible **sans trait `Overwatch`**.
3. **Cible avec réduction de dégât ⇒ delta par-coup pollué.** `tyranTyrantGuard` porte
   `GuardianOrganism_DamageReduction` = `ForSubtraction(Min(PercentageOf(CurrentDamage, pct), cap))`,
   **recalculée sur le dégât courant** : le delta par coup mesuré devenait ~+531 au lieu de +443.
   **Parade** : cible sans effet défensif (`necroWarden` : liste d'effets vide).

Piège de scénario (déjà connu, re-vécu) : sans **deux théâtres séparés**, la charge du Warboss + les
Ork Boyz du `PerformAIAction` arrivent au contact de la cible de mesure → elle meurt et
`GetStuckIn.GetBonusHitChance` bascule à 100 % (2 Orks adjacents à la cible) → le `+1` coup serait
noyé sous `+floor(hits/2)`.

## 5. Validation

`scripts/python/tests/engine/runner/test_waaagh_buff_contrib_live.py` (6 tests, tous PASS) :

| test | ce qu'il confronte |
|---|---|
| `test_live_extra_hit_adds_exactly_extra_hit` | preview NATIVE : coups **+`extraHit`** (3 → 4) |
| `test_live_extra_damage_adds_extra_dmg_per_hit_unscaled` | preview NATIVE : **+`extraDmg[L poseur]` BRUT** par coup, sur les DEUX bornes |
| `test_port_posts_both_buffs_on_the_far_ork_ally` | sélecteur board-wide : allié Ork à 9 hex buffé, live **et** port |
| `test_port_hits_and_damage_contributions_match_live` | les canaux PORTÉS, sur les effets que le PORT a posés, rendent **exactement** le delta live |
| `test_port_gates_ranged_and_ability_attacks` | contre-cas gates : RANGED → 0, ABILITY (`is_normal_attack=False`) → 0, sur les DEUX canaux |
| `test_port_counter_case_unbuffed_unit_gets_nothing` | contre-cas sélecteur : la 4ᵉ unité (non-Ork, hors ring-1) ne reçoit rien, live **et** port |

Zéro régression : `test_summon_consumers_live.py` (23) ✔, `test_cultdemagogue_migration_live.py` (6) ✔,
`test_runner_attack_live.py` (2, garde du pipeline dégât/coups partagé) ✔.

**Non couvert** :
- la dépendance au NIVEAU du poseur n'est exercée qu'à **un** point (L50) — le seed BC donne le même
  niveau 50 à tout rank testé ; le multiplier, lui, est discriminé (200 et 180 tous deux réfutés) ;
- effets 1100/1101 **SEEDÉS** depuis une capture live (`EffectFactory.create_many`) : le niveau porté
  est celui de l'unité PORTEUSE, pas du poseur (le canal de capture n'expose pas la source) —
  approximation pré-existante et commune à tous les buffs cross-unité du port ;
- la face COMBAT réelle (dégât appliqué) n'est confrontée qu'indirectement : les deux canaux sont
  partagés combat/prédiction (`attack_hits_with_modifiers`, `build_attacker_modifiers_from_effects`),
  et la mesure porte sur la façade PRÉDICTION native.

## 6. Résidu NON traité (priorité 2 de la tâche) — ordre intra-groupe

`PerformAIAction(asGroup=1)` : le port garde **l'ordre du sélecteur**, le natif fait un **argmax
d'utilité**. RE avancée cette passe (pas de port : le faire sans la sémantique des buckets serait
inventer) :

```
IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$PickNextUnit
  -> IdunBattle.AI.OperationalDeciders.AnAiGroupOperator$$GetValidUnits
       = HasActionLeft(u) && !IsDead(u) && BaseUnitComponent.aiActions@+0x60 < 0x3e9
  -> slot 1 de operator+0x28 (fabrique de tactique), avec le PICKER operator+0x30
IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$.ctor : le picker est un tableau de 8
  `IdunBattleLogic.AI.Utilities.UtilityBucket` construits dans CET ordre —
     0x4a (poids Fix64 1) · 0x44 (poids 1) · 0x45 (poids 1) · 0x4c (poids NUL, flag +0x18 = 1)
     · 0x4b (nul) · 0x49 (nul) · 0x47 (nul) · 0x48 (nul)
```

Ce qui manque pour porter : la sémantique des 8 ids de bucket (aucun dump d'enum `UtilityBucket`
disponible) + le scoreur par-unité derrière le slot 1. Sans incidence tant que les unités du groupe
sont interchangeables (cas des Ork Boyz clones et des gardes de SupremeCommander).
