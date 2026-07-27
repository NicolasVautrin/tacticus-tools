# case #154 — DoomSiren (1199) et FearOfTheUnseen (1115), canal DirectDamage

> **Verdict** : les DEUX abilities sont **portées et confrontées au live**. Elles étaient NO-OP
> (aucun handler enregistré). Build `gqfc5mff6c`. Mesures du 2026-07-28, session Frida 5.

---

## 1. DoomSiren (1199) — `emperKakophonist` « Adamatar », EmperorsChildren

### 1.1 Artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour` — arbre DSL,
mirror 1:1 dans `engine/runner/abilities/emperorschildren.py` :

```
pool  = Damageable( AdjacentEnemies(Self@0x148, TargetTiles@0x190, unique=1) )
sel   = Cache( op_Addition( Target@0x178,
                            PickRandomly(pool, GetNumberConstant(0x78 = nrOfUnits)) ), 1 )
atk   = AttackWithAttackDamage(caster@0x160, sel, MinMaxDamage(0xc, 0xd),
                               Nullable(GetDamageProfile(config, 0)),
                               GetHits() = GetNumberConstant(0x2f), AbilityOrEffect(1199), default)
ovk   = Foreach( UnitsDamagedThisPhase(caster@0x160),
                 If( IsDead(It@0x180) & HasFlag(It@0x180, 8 = Overkilled),
                     AddStaticStatModifierEffect(Self@0x148, 0x597 = DoomSiren_ExtraHit,
                                                 0x11 = ExtraHits, dsl@0xc0 = Direct(1),
                                                 turns = null, isHidden = false) ) )
ExecuteAtomic( op_Addition(atk, ovk), entities, 0x2a )
```

Deux points de lecture qui auraient pu être devinés faux :

- **`AdjacentEnemies` est l'overload 3 arguments** (`unit`, `unitTile`, `unique`), qui décompile en
  `Enemies(unit, Units(AdjacentTiles(unitTile), unique, 3) − unitTile)` : le pool est ancré sur les
  **tuiles de la CIBLE** (`TargetTiles@0x190`), pas sur le caster. Le contraste avec
  `BringerOfDespair` / `HarbingerOfDestruction` (caster-ancrés) est testé (`test_doom_siren_live.py::
  test_doom_siren_splash_anchored_on_target_not_caster`).
- **Le montant du stat-mod est le littéral 1 du `DSLFactory`**, pas la constante config `extraHit` :
  `IdunBattleLogic.Entities.DSLFactory$$.ctor` alloue les formules littérales
  `+0xb8 = 0 · +0xc0 = 1 · +0xc8 = 2 · +0xd0 = 100 · +0xd8 = −1`, et le behaviour passe `dsl@0xc0`.
  Les deux valent 1 ici — le port mirror le natif, pas la coïncidence.

### 1.2 Plomberie partagée qu'il a fallu poser

| pièce | mirror natif | fichier |
|---|---|---|
| `UnitFlag.Overkilled` (8) matérialisé | posé par `IdunBattle.Operations.ApplyDamageOperation$$Execute+0x17d5` (`mov edx,8` juste avant `UnitFlagsComponent$$Add`, lu au désassemblage) ; retiré par `IdunBattle.Operations.ReviveUnitOperation$$Execute+0x7e0` | `runner/components.py`, `runner/operations/damage.py`, `runner/operations/revive.py` |
| `UnitComponent.damaged_units_this_phase` | `List<BEntityId>` @`ActorStatisticsComponent + 0x48`, vidée par `IdunBattle.Operations.EndPhaseOperation$$ResetEntityPhase` **dans la même boucle** que `TriggeredAbilityComponent$$ResetPhase` | `runner/components.py`, `runner/state.py` |
| sélecteur `UnitsDamagedThisPhase` | `IdunBattle.Entities.Formulas.UnitsDamagedThisPhaseSelector$$Select` | `entities/selectors/units.py` |
| prédicat `HasUnitFlag(unit, flag)` | `IdunBattleLogic.Entities.DSLFactory$$HasFlag(unit, flag)` → `HasFlagAbilityTrigger` — jumeau UNIT-DOMAIN du `HasFlag` scalaire existant | `entities/triggers.py` |

Le boundary de phase du port (`State.reset_trigger_phases`, appelé en tête de `Runner.apply`) est
**exactement** le site natif : `ResetEntityPhase` fait les deux resets côte à côte.

### 1.3 Masque de ciblage

`DoomSirenAbility$$.ctor` **n'appelle aucun `TargetingOptions$$.ctor`** : il copie les 0x40 octets du
preset statique `IdunBattle.Core.Services.TargetingOptions` **statics `+0x40`** (le même que
`CrushingClawsAbility$$.ctor`). Valeurs lues dans `TargetingOptions$$.cctor` :

```
statics+0x40 (preset+0x00) = 0        -> isSelfCasting = False
statics+0x48 (preset+0x08) = TargetingRange statics+0x30 -> RANGE_ADJACENT (onlyAdjacent, range 1)
statics+0x60 (preset+0x20) = 1        -> forceMeleeTarget = RangedBool.False
statics+0x68 (preset+0x28) = 0x4000   -> Rules = TargetIsEnemy
```

`ABILITY_ATTACK_TYPE[1199] = 0` (`DirectTargetAttack`) — 3ᵉ argument de
`AActiveAbility..ctor(this, &opts, 0, 0)`.

### 1.4 Validation live — `test_doom_siren_live.py` (4 tests, verts)

| cas | montage | verdict |
|---|---|---|
| **A** cible SEULE | aucun ennemi adjacent à la cible | **1 unité frappée, per-coup LIVE == OFFLINE bit-exact** |
| **B** cible + 2 adjacents-cible | `len(pool) == nrOfUnits` → le pick prend tout le pool | 3 unités frappées ; **cible principale bit-exacte** ; préfixe commun ≥ `nrOfHits + 1` |
| ancrage | ennemi adjacent au CASTER, à distance ≥ 2 de la cible | **non frappé** (réfute un pool caster-ancré) |
| overkill | cible à 1 PV vs cible qui survit | `DoomSiren_ExtraHit` posé **seulement** en overkill, `EXTRA_HITS +1` |

Les cas A et B ne rendent ni le même cardinal ni le même total : un scalaire fitté ne passe pas les
deux.

### 1.5 Résidu NOMMÉ — confond `ThrillSeekers`, mesuré, EXTÉRIEUR à DoomSiren

Sur le cas B, le per-coup des cibles **additionnelles** diverge à partir du 2ᵉ coup de la 2ᵉ cible.
`probe_154_doom_siren_live.py` décompose :

```
live  u77 [931, 1036, 893]   ==  offline u77   -> cible principale BIT-EXACTE
live  u79 [1367, 1284, 1245]  vs  offline [1367, 1379, 1553]  -> 1er coup exact, puis décalage
live  u81 coup 0 : Attack_DidCrit = 1
CritChance(Adamatar) après cast = 15  DES DEUX CÔTÉS
```

Adamatar porte le trait `ThrillSeekers`
(`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility`), qui pose l'effet
`Thrilled` (1434, `+thrillSeekersExtraCritChance`) **dès qu'elle cible un ennemi à pleine vie** —
c'est-à-dire pendant ce cast. L'effet est **porté et appliqué offline** (CritChance = 15 des deux
côtés) ; ce qui diffère est le **RANG** auquel la modification devient effective à l'intérieur d'une
attaque MULTI-CIBLES : live, le crit-roll supplémentaire est consommé dès le 2ᵉ coup de la 2ᵉ cible ;
offline, plus tard.

⇒ **étage PARTAGÉ** (pose + refresh de stat-mod intra-attaque), pas DoomSiren. Le test fige donc la
**longueur du préfixe commun** au lieu de valeurs : un vrai bug de ciblage / bornes / profil / nombre
de coups casserait le préfixe dès le 1ᵉʳ coup. Ne pas « corriger » DoomSiren pour absorber cet écart —
ce serait une compensation.

Résidu voisin déjà inventorié : **R26** (rider overkill de `ThrillSeekers`, face PRÉDICTION).

### 1.6 Autre résidu

`forceOverkill` du 2ᵉ volet n'est pas concerné ; en revanche `AddEffectOperation` a un gate
« déjà-présent » : **deux overkills dans la même phase ne posent qu'un seul `DoomSiren_ExtraHit`**
(le natif passe par `UpdateExistingEffect`). Non exercé par les tests (un seul overkill monté) —
nommé ici.

---

## 2. FearOfTheUnseen (1115) — `tyranDeathleaper` « Deathleaper », Tyranids

### 2.1 Artefact natif — LE CAST NE FAIT AUCUN DÉGÂT

`IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour` :

```
enemies = Enemies(Self@0x148,
                  NonSteppableOrObjectUnits(
                      SurroundingUnits(Self@0x148, GetNumberConstant(0x16 = range),
                                       unique=1, includeCenter=1, sel=3), 3), 3)
Execute( ( If( NOT HasFlag(Self@0x148, 0 = Moved),
               AddEffect(0x429 = Pinned, stateRef, caster@0x160, enemies, options = default)
               op_Addition TriggerAbility(enemies, 0x401 = BattleFatigue, ...) )
           op_Addition AddEffect(0x4d6 = 1238 TeleportingIn, stateRef, Self@0x148, turns) )
         op_Addition AddEffect(0x4d7 = 1239 ExtraDamage, stateRef, Self@0x148, turns) )
  avec turns = Sum(TurnsFromRounds(1), Direct(1))
```

C'est un **poseur d'effets pur**. Le DirectDamage annoncé par la config 1115 vit en **PHASE 2**, dans
l'effet 1239 : `IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_ExtraDamageEffect$$CreateAdditionalHits`
→ `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` avec
`trigger = OwnerIsCaster & IsMeleeAttack`, `damage = BaseEffect$$GetMinMaxDamage(this, 0)` =
`RandomAmount(ConfigVar(0xc minDmg), ConfigVar(0xd maxDmg))` indexé par `AbilityStateFromEffect`,
`hits = Get(GetNumberConstant(0x2f))`, `profile = GetDamageProfile(config, 0)`.
Porté comme `FearOfTheUnseenExtraDamageEffect` (canal #179, template `CordClaw`).

`Execute` **plain**, pas `ExecuteAtomic` (contraste DoomSiren `0x2a`).

### 2.2 Masque de ciblage — overload FLAGS DIRECTS

`FearOfTheUnseenAbility$$.ctor` : `TargetingOptions..ctor(&opts, 1, &range, 1, 0x18, 0, 0, 0)`
⇒ `isSelfCasting = 1`, `range` = copie de `TargetingRange` statics `+0x60` = `RANGE_SELF`
(`overrideRange = 0`), `forceMeleeTarget = RangedBool.False`,
`Rules = 0x18 = AddCasterIfMatchesDynamicRule (0x8) | CasterHasNotMoved (0x10)`.

`ABILITY_ATTACK_TYPE[1115] = 2` (`Others`).

### 2.3 Ce que la mesure a CORRIGÉ dans ma lecture

Il y a **deux** gardes « le Deathleaper n'a pas bougé », à deux étages différents :

- le **masque** porte `CasterHasNotMoved` ⇒ `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`
  **refuse le cast entier**, en amont de toute behaviour ;
- l'ExecuteBehaviour porte **en plus** un `If(NOT HasFlag(Self, Moved), ...)` autour du seul volet
  ennemis.

**Mesure** : avec le flag `Moved` posé, le port ne matérialise **aucun** effet — ni `Pinned`, ni les
deux effets self. C'est le premier gate qui parle. Le `If` interne est donc **du code défensif** sur
ce chemin. Mon test initial supposait l'inverse (« les effets self passent quand même ») et a été
réécrit d'après la mesure : `test_fear_of_the_unseen_moved_gate_refuses_the_whole_cast` fige
maintenant le **refus complet + la raison `CasterHasNotMoved`**. Un port entré au registre sans son
masque passerait le cas nominal et échouerait celui-là.

### 2.4 Validation live — `test_fear_of_the_unseen_live.py`

| cas | montage | verdict attendu |
|---|---|---|
| **A** | 2 ennemis dans le disque rayon-`range`, 1 à `range`+1 | 2 `Pinned` LIVE == OFFLINE ; aucun dégât au cast |
| **B** | 1 seul ennemi dans le disque | 1 seul `Pinned` |
| gate | flag `Moved` posé | refus complet, raison `CasterHasNotMoved` |
| **phase 2** | même attaque mêlée, même MT, avec vs sans l'effet 1239 | 1 groupe de `nrOfHits` coups au profil `constants.damageProfile`, coups d'arme INCHANGÉS |

Le volet phase-2 mesure au bon endroit : les coups du canal #179 sont des **sous-opérations**
(`IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`), donc ils ne
figurent pas dans le `per_hit` de l'arme mais dans la clé `additional_hits`. (Première rédaction du
test : fausse pour cette raison — corrigée après mesure.)

### 2.5 Résidus NOMMÉS

- **`FearOfTheUnseen_TeleportingIn` (1238) est posé mais inerte** : `BaseEffect` nu. Sa mécanique —
  untargetable + téléport libre au tour suivant — vit dans un sous-système MOUVEMENT non porté :
  base native `BlockUnitMovementEffect`, `$$GetMovingEffectType` → `0x4d9 = 1241
  FearOfTheUnseen_Moving`, `$$GetAdditionalRemoveTriggers` =
  `AmountIsEqual(EffectRemainingTurns(Effect@0x150), dsl@0xc0 = 1)`, pathfinder dédié
  `IdunBattle.Entities.Pathfinding.FearOfTheUnseenPathfinder$$IsValidTeleportTile`.
- **`$$GetDynamicInvalidCasterReason` = `IsTeleporting(caster) ? 4 : 0`** n'est pas invoquée par la
  cascade de refus (le bit `CasterMatchesDynamicRule` 0x4 n'est pas dans le masque) : elle l'est par
  le constructeur de LISTE de cibles via `AddCasterIfMatchesDynamicRule` (0x8), étage non porté
  (`get_caster_not_added_reason` rend 0). ⇒ offline, un cast depuis le Deep Strike n'est pas refusé
  alors que le natif le refuse — écart du côté **permissif**, nommé.
- **`forceOverkill = true`** (6ᵉ argument d'`EffectAdditionalHits$$Create`) n'est pas transporté par
  le canal `additional_hit_groups` : les coups bonus ne bypassent pas le cap `Resilient`. No-op sur
  toute cible non-`Resilient`.
- **`TriggerAbility(BattleFatigue)`** est porté structurellement (registre étroit
  `TRIGGERED_ABILITY_FORCE_FIRE`, gate « if they have it » = le trait sur l'unité). Le
  `Maybe(GetFleeChance)` garde son résidu **pré-existant** (chance non sourçable offline, cf.
  `runner/operations/behaviour.py`). Inerte dans un duel de héros : aucun héros ne porte le trait.

---

## 3. Leçon de harnais (réutilisable)

`_ability_cast_replay.py` (fixture nommée `ability_cast_harness`) porte la règle apprise ici :

> **Placer d'abord, atteindre son tour ensuite.** Chaque `applyAction move` consomme une activation
> et peut faire basculer le joueur courant ; un cast tenté après coup est **refusé en silence**
> (signature #111 : `ok=True`, pas de `mutated`, 2 événements, aucun dégât). Repasser par des
> `endturn` APRÈS les placements donne au caster un tour neuf, flags purgés — indispensable dès qu'un
> masque porte `CasterHasNotMoved`.

Le premier montage de ces tests est tombé exactement dans ce piège : `probe_154_doom_siren_live.py`
l'a mesuré (`abilityTargets` rendait `playerId: 4` alors que le caster appartenait au joueur 3).
