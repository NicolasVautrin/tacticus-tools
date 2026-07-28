# Case #217 — face COMBAT de BlackRage (ActiveAbilityType 1163, « Lucien »)

**Porteur** : `bloodDeathCompany` (« Lucien », Blood Angels Death Company) — unité UNIQUE,
active `BlackRage` (id 1163) + passif `VisionsOfHeresy`, traits Hero/RapidAssault/Resilient/Unstoppable.
**Statut** : PORTÉ + VALIDÉ LIVE (probe `probe_217_blackrage.py` VERDICT PASS + guard 31337 100%).

La face DÉCISION (`engine/playbook/noncomparable/black_rage.py`) était déjà portée ; la face COMBAT
était un NO-OP silencieux (1163 absent de `ABILITY_CLASSES`). L'ability est castée au walk de garde 31337
(step 12, u91 ab=1163 tgt=85) → divergence d'état invisible (doctrine « DÉCIDER ≠ EXÉCUTER »).

## 1. RE (décompilé = vérité, VAs citées, build gqfc5mff6c)

`BlackRageAbility.ExecuteBehaviour @1811b9c20` = arbre DSL en **3 phases** (mesure GROUND TRUTH live
confirme chaque étage) :

- **Phase A** `Execute(SetHealth)` — `GetSetHealthBehaviour @1811ba690` =
  `ChangeStat(Health(5), mode 0 = SetAbsolute, PercentageOf(StatAmount(Health, MAXIMUM=2), ConfigVar(hpPct)))`.
  - Mode = 0 (SetAbsolute) : lu dans `ChangeStatBehaviour.Execute @180fbfb10` (champ +0x68, case 0 = la
    modification impose `GetStat == amount`) ; l'arg mode = `param_4` du call `DSLFactory.ChangeStat
    @180debdc0` (confirmé par contre-exemple `CursedPlagueBell_ExtraMoveEffect.AddStatModifier @180f3b080`
    = mode 4 source-scaled en `param_4`).
  - `PercentageOf @...` mode 0 = **Round half-to-even** (`_round_fix64` mode 0), PAS floor.
  - `hpPct` = ability var **PER-LEVEL** `[30, 30, ..., 50]` (L1→30%, L65→50%), HORS variablesAffectedByRarityBonus.
  - **Health = stat FILL-UP** (`HealthComponent`) → SetAbsolute = SET du current HP. C'est le COÛT self.
  - **MESURE live** (31337, Lucien MaxHealth ~15059) : hp 9035 → **4518** = round(15059×30/100=4517.7).

- **Phase B** `ExecuteAtomic(tag 0x2a)` — **3 self-buffs** sur `ctx160` (= le CASTER), durée node ZÉRO
  (remaining=0 live = permanent) :
  - `AddStaticStatModifierEffect(caster, 1342, stat=MOVEMENT(1), ConfigConst(0xe=extraMovement))` →
    **BlackRage_ExtraMove** (0x53e), +1 MOVEMENT. `DefaultAmountOfRounds(1342)=null @181559ff0`.
  - `AddEffect(0x53f=1343, caster)` → **BlackRage_ExtraDamage**. `CreateEffectDamageBonusForAttack @180f340e0`
    = `ForAddition((OwnerIsCaster & IsCharging(caster,target) & IsNormalAttack), ConfigVar(8=extraDmg))`
    (extraDmg `[10,12,14,...]` — bonus dégât sur l'attaque de CHARGE).
  - `AddEffect(0x540=1344, caster)` → **BlackRage_AutomaticUnit** (ctor @180f34090 = `BaseEffect(
    AbilityOrEffect(0x48b=1163), 1)`). Marqueur pur : arme la triggered `BlackRage_ActivationAbility`
    (`CreateTrigger @180e19f30` = `On(0x16) & HasEffect(self, 0x540)` → `CreateBehaviour @180e19ef0` =
    `PerformAIAction(self)` = « acts again » berserk Death Company).

- **Phase C** `Execute(MoveUnit & UseActiveAbility)` — la CHARGE + l'attaque :
  - `MoveUnit(caster, First(SortTilesByUtility(GetPossibleMovementTiles, 0x20)))` où
    `GetPossibleMovementTiles @1811ba5f0` = `TilesUnitCanMoveToChargeTarget(caster@0x160, ?, target@0x178,
    UnitMovementRangeWithBonus(0x53e, ConfigConst 0xe))` = tuiles adjacentes à la cible atteignables.
  - `UseActiveAbility(Alive, target@0x178, UnitNormalAttackType(caster))` = **attaque NORMALE au contact**
    (MELEE après la charge — profil 0, 4 coups mesurés live).

**Sélecteurs** : caster = `factory+0x160`, target = `factory+0x178` (l'**ENNEMI** chargé — tgt 85 du walk
est un ennemi, PAS un allié : le SetHealth/effets ciblent le self, l'attaque frappe la cible). GAP décision
`GetUseProbability @181121740` (porte RNG 0.4 hors-bucket) déjà documenté côté playbook.

## 2. Port (mirror 1:1, doctrine DSL-vs-impératif #149)

| Fichier | Ajout |
|---|---|
| `engine/runner/abilities/behaviours.py` | Feuille `SetHealth` (mirror GetSetHealthBehaviour, fill-up HP, round mode-0) ; `UseActiveAbility` rendu **défensif** sur `state.rng is None` (mirror `execute_ability_attack` : replay effet-seul sans crash) |
| `engine/entities/effects/loki/status.py` | `BlackRageExtraMoveEffect` (applied_stat_mods=[(MOVEMENT,1)] / reverted_stats=[MOVEMENT]) ; `BlackRageExtraDamageEffect` + `BlackRageAutomaticUnitEffect` (marqueurs) |
| `engine/entities/effects/loki/__init__.py`, `factory.py` | Exports + `EFFECT_CLASSES` (noms `BlackRage_ExtraMove/ExtraDamage/AutomaticUnit`) |
| `engine/runner/abilities/loki/strike.py` | `black_rage_tree` (3 phases) + `_black_rage_charge_positions` (collapse SortTilesByUtility→First via `FixedTiles`) + classe `BlackRageAbility` |
| `engine/runner/abilities/loki/__init__.py`, `handler.py` | Exports + `ABILITY_CLASSES[1163] = BlackRageAbility` |

L'arbre : `op_add( op_add( SetHealth(Caster), AtomicGroup(AddEffect×3(Caster, durée 0)) ),
op_and( MoveUnit(Caster, FixedTiles(charge)), UseActiveAbility(Caster, Target) ) )`. Les feuilles émettent
les MÊMES Operations que les vecteurs déjà portés (AddEffectOperation, MoveUnitOperation, AttackDamage
Operation) → même mutation, même ordre setHealth→buffs→charge→attaque (les buffs AVANT l'attaque comme
l'exige le natif). `AddStaticStatModifierEffect(1342)` est FOLDÉ dans `AddEffect(1342)` + la classe
`BlackRageExtraMoveEffect` (qui DÉCLARE le stat-mod MOVEMENT) — même Operation `AddEffectOperation` en aval.

## 3. Validation adversariale (probe `probe_217_blackrage.py`)

Build LIVE Lucien vs `tyranTyrantGuard` (MC1_67, hp-target 500k), drive à portée de charge, CAPTURE
pré-cast (decisionView/observe/combatSnapshot/dumpRng → `load_state` + rng calé), CAST 1163 LIVE (parse
cascade brute), APPLIQUE le MÊME `ActiveAbilityMessage` OFFLINE (`Runner.apply`) et CONFRONTE. **VERDICT PASS** :

- **A. SetHealth** : offline **4518 == live 4518** (DÉTERMINISTE bit-exact ; le round mode-0 est load-bearing —
  floor donnait 4517).
- **B. Effets** : offline pose {1342, 1343, 1344} == live, remaining live 0 → offline None (permanent).
- **C. Movement** : offline 4 → 5 (+1 ExtraMove ; live statModSources = movement total 1, source=l'effet).
- **D. Charge** : Lucien offline (5,8) ADJACENT à l'ennemi (6,8) après le MoveUnit (dist hex 1).
- **E. Attaque normale** (SOFT) : dispatchée, ennemi touché (500000→490911 offline). Le total offline (9089)
  diverge du total cascade live (rng désaligné pour une ability MULTI-étage : le move/passifs live consomment
  du rng entre le dumpRng et l'attaque ; + VisionsOfHeresy/RapidAssault non re-tirés offline) → SOFT.

**Zéro-régression** : `engine_agreement_stages.py --build --seeds 31337` = **100%** (ability 13/13, move 18/18,
prédiction 10/10, utilité 10/10 ; step 12 u91 ab=1163 MATCH). Tests ciblés : `test_effect_stun_live` PASS,
`test_finaljustice_live` PASS (garde `UseActiveAbility` défensif).

## 4. Résidus documentés (présent ≠ appliqué)

1. **BlackRage_ExtraDamage (1343) — contribution +extraDmg-on-charge non modélisée.** Magnitude négligeable
   (extraDmg `[10,12,14]` vs ~3000/coup = <0.5%) ; le gate `IsCharging` n'est pas exprimable dans le canal
   modifier eager sans SUR-APPLIQUER aux attaques hors-charge (l'effet persiste remaining=0). L'effet est
   posé (présent/diffable). Branchement futur : `create_effect_damage_bonus_for_attack` gated charge
   (cf. FeederTendrils).
2. **BlackRage_AutomaticUnit (1344) — mécanisme act-again non modélisé.** L'effet est posé ; la triggered
   `BlackRage_ActivationAbility` (`PerformAIAction` sur event 0x16) = tranche triggered dédiée (nécessite le
   vecteur On(0x16) + un re-tour d'action offline).
3. **Attaque normale offline non bit-exacte dans la probe** — artefact de désalignement rng multi-étage (cf.
   E) ; le dispatch réel (`UseActiveAbility → AttackDamageOperation.execute`) est le pipeline d'attaque normale
   déjà validé bit-exact ailleurs.
4. **`UseActiveAbility` — sujet natif `Alive(caster@0x160)`, port `Caster()` nu.** Sans effet sur ce chemin
   (les 5 sélecteurs d'options du `MoveUnit` sont NULS, donc aucun after-move ne peut tuer le caster entre
   la charge et l'attaque), mais l'écart structurel est noté.

*(Le résidu « tuile de charge — `SortTilesByUtility` collapsé » a été LEVÉ par #206 :
`black_rage_possible_movement_tiles_selector` + `first_tile_by_utility(MovementSuggestion)` sont des
mirrors 1:1 — cf. `case-206-black-rage-waaagh-movement-suggestion.md`.)*

## 5. Gate de cible — masque + règle dynamique (#210)

BlackRage entrait dans `ABILITY_CLASSES` **sans `TARGETING_OPTIONS`**. Or
`get_invalid_target_reason` / `get_invalid_caster_reason` commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` ; `None` ⇒ retour 0 immédiat, **aucun gate**.
Le moteur acceptait donc des casts que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`
REFUSE — dégradation permissive, ni erreur ni crash, invisible en self-play.

### 5.1 Le masque, relu sur BlackRage (jamais hérité de Waaagh)

`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$.ctor` :

```
lVar1 = <bloc de statiques de IdunBattle.Core.Services.TargetingRange>
<copie des 0x18 octets de lVar1+0x48>                       # preset useWholeBoard
TargetingOptions..ctor(&opts, 0, &<copie>, 1, 0x106004012, 0, 0, 0)
AActiveAbility..ctor(this, &opts, 2, 0)
```

C'est l'overload **FLAGS DIRECTS** (8 arguments), **pas** l'overload « preset + flags » : le littéral
`0x106004012` **EST** le masque effectif, et le `TargetingRange` n'est pas un champ statique recopié en
bloc mais l'argument `range` du ctor. Les deux pièges connus sont donc écartés par lecture, pas par
présomption. Le ctor se trouve être **byte-identique** à
`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$.ctor` (même bloc de statiques, même
offset `+0x48`, même littéral) — constat *a posteriori*, pas la source du port.

| bit | nom `IdunBattle.Core.Services.TargetingRule` | effet porté |
|---|---|---|
| `0x2` | `TargetMatchesDynamicRule` | consulte `get_dynamic_invalid_target_reason` (§5.2) |
| `0x10` | `CasterHasNotMoved` | volet CASTER — Lucien ne peut pas caster après s'être déplacé |
| `0x4000` | `TargetIsEnemy` | refus sur soi-même / un allié |
| `0x6000000` | `AllowObscuredTarget…` | permissif (aucune contrainte de ligne de vue) |
| `0x100000000` | `TargetIsNotAdjacent` | refus d'une cible DÉJÀ au contact, **avant** la règle dynamique |

`range` = le `TargetingRange` statique `+0x48` = `useWholeBoard` ⇒ le volet PORTÉE générique **ne teste
rien** ; toute la contrainte de distance vit dans la règle dynamique, qui rend le même code
`TargetIsInRange`.

### 5.2 La règle dynamique

`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$GetDynamicInvalidTargetReason` :

```
tiles = BlackRageAbility.GetPossibleMovementTiles()
ents  = AbilityEntities(caster, caster, target, 0, 0, 0, casterTiles, ...)
return Count( tiles.Evaluate(ents) ) > 0 ? 0 : 0x8000000        # TargetingRule.TargetIsInRange
```

Jumeau structurel de `WaaaghAbility$$GetDynamicInvalidTargetReason`, à une différence de FORME près :
le natif appelle ici `GetPossibleMovementTiles()` **sans argument** (la cible vient du sélecteur
`factory+0x178` de l'arbre), là où Waaagh lui passe `Get(target)`. Les deux voient la même cible.

Le prédicat **n'est pas une distance** : « il existe au moins une tuile LIBRE et marchable hex-adjacente
à la cible, ATTEIGNABLE par le caster en `MOVEMENT + extraMovement` pas ». Le sélecteur consommé est
`black_rage_possible_movement_tiles_selector` (le mirror 1:1 livré par #206), et la portée
`_black_rage_move_range` — au moment du gate l'effet 1342 n'est pas encore posé, donc la branche
`MOVEMENT + bonus` du `If` natif, exactement comme le natif qui évalue la formule avant toute exécution.

### 5.3 Mesure (probe `probe_210_blackrage_targeting.py`)

Oracle = `abilityReason` (masque `TargetingRule` NATIF) ; port rejoué sur le MÊME état figé en DEUX
versions : **APRÈS** (le registre) et **AVANT** (`TARGETING_OPTIONS = None` + règle dynamique du défaut
d'`ActiveAbility` = l'état de `master`). Quatre états figés, chacun avec sa capture.

| cas | natif | port APRÈS | port AVANT (`master`) |
|---|---|---|---|
| S1 ennemi loin (d=11) — règle DYNAMIQUE | `0x8000000 TargetIsInRange` | `0x8000000` | **`0x0`** |
| S1 cible AMIE | `0x4000 TargetIsEnemy` | `0x4000` | **`0x0`** |
| S1 cible = LE CASTER | `0x4000 TargetIsEnemy` | `0x4000` | **`0x0`** |
| S2 ennemi chargeable (d=2) | `0x0` | `0x0` | `0x0` |
| S3 ennemi AU CONTACT (d=1) | `0x100000000 TargetIsNotAdjacent` | `0x100000000` | **`0x0`** |
| S4a caster ayant bougé (état chargé) | `0x10 CasterHasNotMoved` | `0x10` | **`0x0`** |
| S4b idem + `set_moved_flag` (chemin replay) | `0x10 CasterHasNotMoved` | `0x10` | **`0x0`** |

**7/7 d'accord, et 6 cas où le natif REFUSE alors que `master` rendait 0** — c'est-à-dire six casts
illégaux que le moteur acceptait.

`S4a`/`S4b` couvrent les **deux chemins de pose** du flag `UnitFlag.Moved` : le snapshot
(`snapshot._load_unit_flags` ← `combatSnapshot.units[].unitFlags`) et le replay offline
(`set_moved_flag`, mirror d'`IdunBattle.Entities.UnitExtensions$$SetMovedFlag` qu'appelle
`MoveUnitOperation`).

> **Deux fiches corrigées au passage.** Les docstrings de `components.unit_has_moved` et de
> `get_invalid_caster_reason` affirmaient que `load_state` ne seede PAS le `UnitFlagsComponent`, donc
> que la règle `CasterHasNotMoved` est **inerte sur un état chargé**. C'est **périmé** depuis
> `f02e30f` (`_load_unit_flags`), et `S4a` le mesure : sans aucune pose manuelle, le port rend `0x10`
> en accord avec l'oracle. Trouvé **au re-jeu après rebase** — `f02e30f` n'était pas dans le commit de
> base de cette tranche.

### 5.4 Généralisation — le prédicat n'est pas monotone en distance

`probe_210_blackrage_targeting.py --sweep 8` déplace Lucien de proche en proche et confronte natif/port
sur chaque ennemi vivant, à chaque position. **48 points sur deux montages, 0 désaccord** :

| montage | verdicts natifs par distance |
|---|---|
| `MC1_67` / seed 777 | d=1 `0x100000000` · **d=2 `0x0` ET `0x8000000`** · d=3 `0x8000000` · **d=6 `0x0`** · d=7/10/11 `0x8000000` |
| `C1_74` / seed 31337 | d=1 `0x100000000` · **d=2 `0x0` ET `0x8000000`** · d=3 `0x0` · **d=5 `0x0`** · **d=6 `0x8000000`** |

Deux signatures qu'un collapse « `hexDistance <= portée` » ne peut pas produire : à **distance égale**
(d=2) le natif accepte une cible et en refuse une autre, et le verdict **n'est pas monotone** (d=3
refusé mais d=6 accepté sur `MC1_67` ; d=5 accepté mais d=6 refusé sur `C1_74`). Le port suit sur les
48 points.

## 6. Finding annexe (candidat, HORS scope combat — non modifié)

Le playbook DÉCISION porté (`should_evaluate`) gate sur `hp <= hpmax*0.5` et sa docstring dit « 50% ». La RE
combat montre que **hpPct est PER-LEVEL (30%→50%)** : `GetHealthPercentageAfterUse @1811ba570 = ConfigVar(
hpPct)`, `GetSetHealthBehaviour = SetAbsolute(PercentageOf(MaxHealth, hpPct))`. Le seuil 0.5 n'est correct
qu'au niveau max. **N'affecte PAS le guard 31337** (Lucien y caste à hp=1, sous tout seuil) → laissé
INCHANGÉ (face décision hors scope). À corriger si un walk à niveau intermédiaire l'exerce (candidat).
