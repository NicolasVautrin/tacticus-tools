# #997 — Six no-op silencieuses : la catégorie annoncée MENT quatre fois sur six

**Build** `rnca9r7q6c`. **Numéro** `#997` (réservé par `probe_468_collision_numeros.py --suggere`).
Tranche = six `ActiveAbilityType` absents d'`ABILITY_CLASSES`, donc routés vers un NO-OP :
`ported: False`, 0 dégât, 0 effet, **aucune erreur**.

## 0. Le résultat en une ligne

L'audit annonce **DAMAGE pour les six**. Le décompilé de leur `ExecuteBehaviour` dit **DAMAGE
pour deux**. Les quatre autres ne frappent **rien** au cast : elles posent des effets
`*_PendingAttack` / `*_PendingTarget`, et le dégât appartient à une **TRIGGERED** d'un tour
ultérieur.

| id | ability | annoncé | ce que le cast fait RÉELLEMENT | verdict |
|---|---|---|---|---|
| **1176** | `BlightGrenades` | DAMAGE(Toxic) | 2× `AttackWithAbilityDamage` (cible + 2 tirées derrière) | **CONFIRMÉE** |
| **1170** | `ExplosivePresents` | DAMAGE(Blast) | 1× `AttackWithAbilityDamage` (cible + adjacents − caster) | **CONFIRMÉE** |
| **1215** | `InstrumentsOfVengeance` | DAMAGE(HeavyRound) | `If(Maybe(50))` sur 4 `GetEffectBehavior` + `AddBondEffect(1519)` + `If(!HasAdjacentEnemies) ActivateEffect(1009)` | **FAUSSE** — 2-phases |
| **1174** | `SolarAtomizer` | DAMAGE(Melta) | persistent-data + `AddEffectOrIncreaseLevel(1365)` + `AddEffect(1371)` + `AddEffect(1372)` | **FAUSSE** — 2-phases |
| **1094** | `TheLantern` | DAMAGE(Energy) | `AddEffect(1195)` + `AddEffect(1065)` + `AddEffect(1194)` | **FAUSSE** — 2-phases |
| **1193** | `NovaCharge` | DAMAGE(Particle) | `AddBondEffect(1411)` + `AddEffect(1412)` + `AddEffect(1413)` | **FAUSSE** — 2-phases |

La colonne « catégorie » de l'audit dérive du `damageProfile` de **l'arme du porteur**, jamais du
behaviour de l'ability (résidu `#491-r2`). Elle ne peut donc **rien** dire d'une ability non
portée. Ici elle se trompe **4 fois sur 6** — et l'avertissement de l'audit sur `1192-1194`
(`Nova*` = buffs NonComparable) est **confirmé** : `1193 NovaCharge` ne frappe pas.

## 1. Ce que dit chaque `ExecuteBehaviour` (décompilé = vérité)

Le contexte DSL est `<ability>+0x30` ; ses champs, lus par recoupement des six corps :
`+0x78` Behaviors · `+0x80` Formulas · `+0x88` Triggers · `+0x90` Selectors, et dans les
Selectors `+0x48` = **Caster**, `+0x60` = **Target**, `+0x30`/`+0x58` = autres accesseurs.

### 1176 `BlightGrenades` — DAMAGE, CONFIRMÉE

`IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$ExecuteBehaviour` :

```
behind = PickRandomly( UnitsDirectlyBehind(caster@0x48, target@0x60), 2, allowRepeat=0, 0x7fffffff, false )
ExecuteAtomic(
      AttackWithAbilityDamage(caster, target, MinMaxDamage(state), GetDamageProfile(), GetHits(), this, 2)
    & AttackWithAbilityDamage(caster, behind, MinMaxDamage(state), GetDamageProfile(), GetHits(), this, 2)
  , 0x2a )
```

Deux volets, `op_BitwiseAnd`. Les **deux** appellent `AActiveAbility$$MinMaxDamage` et
`AActiveAbility$$GetHits` — donc **même plage et même nombre de coups** des deux côtés (pas de
`nrOfHits_2` ici, contrairement au patron splash habituel). La factory est
`DSLBehaviors$$AttackWithAbilityDamage` → `AbilityDamageOperation` (1 tirage/coup).

### 1170 `ExplosivePresents` — DAMAGE, CONFIRMÉE

`IdunBattleLogic.Entities.Abilities.Active.Loki.ExplosivePresentsAbility$$ExecuteBehaviour` :

```
targets = ( target@0x60 + AdjacentUnits(target@0x60, unique:1, 3) ) - caster@0x48
ExecuteAtomic(
    AttackWithAbilityDamage(caster, targets, MinMaxDamage(state), GetDamageProfile(), GetHits(), this, 2)
  , 0x2a )
```

**Un seul** `AttackWithAbilityDamage`, sur un sélecteur MULTI (cible + ses adjacents, moins le
caster). Pas de bande secondaire, donc **un seul** `nrOfHits`. Le `- caster` est explicite dans le
natif : friendly-fire sur les **alliés** du caster, mais jamais sur le caster lui-même — même
forme que `Stikkbomb` (`AdjacentUnits` brut, aucun wrapper `Enemies`).

### 1215 `InstrumentsOfVengeance` — 2-PHASES, catégorie FAUSSE

`IdunBattleLogic.Entities.Abilities.Active.Loki.InstrumentsOfVengeanceAbility$$ExecuteBehaviour` :

```
A = GetEffectBehavior(1, true)  + GetEffectBehavior(5, false)
B = GetEffectBehavior(2, true)  + GetEffectBehavior(4, false)
Execute(
      If( Maybe(0x32 = 50), A, B )
    + AddBondEffect( 1519 InstrumentsOfVengeance_PendingAttack, stateRef, sel@0x30, sel@0x30, sel@0x30 )
    + If( !HasAdjacentEnemies(sel@0x30), ActivateEffect(sel@0x30, 1009 Overwatch_AutoAttack), null ) )
```

Aucun `AttackWith*` dans le corps. Le dégât vit dans la triggered
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InstrumentsOfVengeance_AttackAbility` (`$$AttackLine`,
`$$AttackTileBehavior`) et dans l'effet `InstrumentsOfVengeance_PendingAttackEffect`. Le cast est un
**armement** : il tire à pile ou face (`Maybe(50)`) entre deux paires de behaviours d'effet, pose le
bond de pending-attack, et **allume l'overwatch** si personne n'est au contact.

### 1174 `SolarAtomizer` — 2-PHASES, catégorie FAUSSE

`IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$ExecuteBehaviour` — accumulateur de
charge, aucun `AttackWith*` :

```
tiles   = GetTargetTiles()
charged = Cache( EntitiesWithAnyEffect( Friends(caster, AllUnits − caster, 3), 1365 MachineVengeance, 6 ), true )
Execute(
      AddPersistentData( this, caster, <clé>, EffectLevel(EffectFromOwner(charged, 1365)) )
    & RemoveEffect( charged, Nullable(1365), 0 )
    & If( AmountIsGreater( GetPersistentData(this, caster, <clé>), Zero ),
          AddEffectOrIncreaseLevel( 1365 MachineVengeance, stateRef, caster, caster, <niveau lu> ), null )
    & SetPersistentData( this, caster, <clé>, Zero )
    & AddEffect( 1371 SolarAtomizer_PendingAttack,  stateRef, caster, caster )
    & AddEffect( 1372 SolarAtomizer_PendingTarget,  stateRef, caster, tiles ) )
```

Le cast **siphonne** les stacks `MachineVengeance` de tous les alliés, les re-concentre sur le
caster, puis arme la pending-attack sur les tuiles visées.

### 1094 `TheLantern` — 2-PHASES, catégorie FAUSSE

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheLanternAbility$$ExecuteBehaviour` :

```
zone = Unique( target@0x60
             + SurroundingTiles(target@0x60, 0, r=1)
             + ( SurroundingTiles(target@0x60, 0, r=2) & SurroundingTiles(sel@0x58, 0, r=1) ) )
hit  = Enemies( caster@0x48, zone, 3 )
Execute(
      AddEffect( 1195 TheLantern_PendingTarget, stateRef, caster, zone )
    & AddEffect( 1065 Pinned,                   stateRef, caster, hit )
    & AddEffect( 1194 TheLantern_PendingAttack, stateRef, caster, caster ) )
```

Le seul effet **immédiat et observable** du cast est le `Pinned` (1065) sur les ennemis de la zone —
un stat-mod de Movement, **déjà porté** ailleurs (cf. `splash.py`). Le dégât est différé.

### 1193 `NovaCharge` — 2-PHASES, catégorie FAUSSE (l'audit avait raison)

`IdunBattleLogic.Entities.Abilities.Active.Loki.NovaChargeAbility$$ExecuteBehaviour` :

```
line = Cache( GetLineTiles(), true )
more = GetAdditionalMarkedTiles( line )
Execute(
      AddBondEffect( 1411 NovaCharge_PendingAttack,       stateRef, caster, caster, sel@0x30 )
    & AddEffect(     1412 NovaCharge_PendingTarget_Line,   stateRef, caster, line )
    & AddEffect(     1413 NovaCharge_PendingTarget_Single, stateRef, caster, more ) )
```

Le `damageProfile: Particle` du kit est celui de **l'arme de `tauBossRiptide`** ; il ne dit rien du
cast. `NovaChargePlaybook$$EvaluateNonComparable` (et non `MakeDamagePredictions`) le corrobore côté
DÉCISION : c'est un playbook NonComparable, comme `NovaShield`/`NovaBoost`.

**Contre-épreuve côté playbook** — l'artefact natif de décision sépare les deux familles sans
ambiguïté, et il concorde 6/6 avec la lecture des `ExecuteBehaviour` :

| ability | méthode du playbook natif | famille |
|---|---|---|
| `BlightGrenadesPlaybook` | `$$MakeDamagePredictions` | DAMAGE |
| `ExplosivePresentsPlaybook` | `$$MakeDamagePredictions` | DAMAGE |
| `InstrumentsOfVengeancePlaybook` | `$$CalculateCustomUtility` | non-DAMAGE |
| `SolarAtomizerPlaybook` | `$$EvaluateNonComparable` | non-DAMAGE |
| `TheLanternPlaybook` | `$$EvaluateNonComparable` | non-DAMAGE |
| `NovaChargePlaybook` | `$$EvaluateNonComparable` | non-DAMAGE |

C'est un **second canal indépendant** du décompilé de l'ability, et il faut le dire :
`MakeDamagePredictions` / `EvaluateNonComparable` se lit d'un `grep` dans
`data/symbols/<build>/ghidra/functions.tsv`, **sans décompiler quoi que ce soit**. Une colonne
« catégorie » dérivée de là, plutôt que du `damageProfile` de l'arme, aurait rendu 6/6 juste au lieu
de 2/6.

## 2. Qui les porte, et par quel chemin

Les six porteurs sont **npc** (`unit_map.py find --ability`), dont **quatre boss**. « npc-only »
n'implique pas « non confrontable » : un boss se monte via `--explicit-stats` (mesure live du
2026-08-11, `reference_boss_montable_par_explicit_stats`).

| id | porteur | catégorie | chemin de montage |
|---|---|---|---|
| 1176 | `deathNpc2PlagueMarine` | npc | `--explicit-stats` (entrée `units.npc` à table `stats[]`) |
| 1170 | `orksRedGobbo` | npc | idem |
| 1215 | `darkaBossLion` | boss | `--explicit-stats "darkaBossLion:<palier>"` |
| 1094 | `deathBossMortarion` | boss | `--explicit-stats` (monté live, mesuré) |
| 1193 | `tauBossRiptide` | boss | `--explicit-stats` (monté live, mesuré) |
| 1174 | `admecBossBelisarius` | boss | ⛔ **REFUS MESURÉ** : `--explicit-stats` lève `TriggeredAbilityType.ShroudPsalm inconnu du build courant` — l'inversion de voie `ShroudPsalm` (en `passiveAbilities` mais `ActiveAbilityType` 1181) que `catalog_inject.augment` ne gère pas |

Deux pièges de montage à retenir pour qui reprendra : le garde de roster rend un **FAUX ROUGE**
(le jeu remappe l'id — `tauBossRiptide` → `GuildBoss11Boss1TauRiptide`), à lever par
`TACTICUS_ALLOW_ROSTER_DEFICIT=1` après vérification dans la vue ; et un boss arrive `moveNone`
+ `Immune`, donc tout volet dépendant d'un déplacement du caster se déclare NON CONFRONTÉ.

## 3. Conséquence pour le portage

- **1176 / 1170** sont portables **maintenant** : ce sont des attaques pures, leurs sélecteurs
  (`AdjacentUnits`, `PickRandomly`, `UnitsDirectlyBehind`) ont déjà leur mirror, et le patron
  `AttackWithAttackDamage(..., native_factory="ability", multi=True)` est celui de `Stikkbomb` /
  `PlasmaGrenade`.
- **1215 / 1174 / 1094 / 1193** ne sont **pas** des ports d'attaque. Porter leur `ExecuteBehaviour`
  seul poserait des effets `*_Pending*` que **personne ne consomme** — le dégât resterait à zéro,
  et le port aurait l'air fait. Chacune exige sa **triggered** (`*_AttackAbility`) et ses effets
  `*_PendingAttackEffect` / `*_PendingTargetEffect` **dans la même tranche**, sinon on remplace une
  no-op silencieuse par une demi-implémentation tout aussi silencieuse.
- **`1094 TheLantern`** est le moins cher des quatre : son seul effet non différé est
  `1065 Pinned`, déjà porté.

Résidus ouverts pour les quatre : `#997-r1` (1215), `#997-r2` (1193), `#997-r3` (1094),
`#997-r4` (1174).

## 4. Ce qui est PORTÉ, et ce que le live en dit

`1170 ExplosivePresents` (`orks.py`) et `1176 BlightGrenades` (`deathguard.py`) sont au registre,
avec leur `TARGETING_OPTIONS`, leur `ABILITY_ATTACK_TYPE` et leur `GetDynamicInvalidTargetReason`
dans le même commit.

### Les deux masques, et pourquoi la lecture naïve en rate un

| | forme de ctor | masque effectif | portée |
|---|---|---|---|
| 1170 | **FLAGS DIRECTS** — un seul ctor à 7 args | `0x200000000002` = `TargetMatchesDynamicRule \| TargetIsUnit` | `RANGE_FROM_CONFIG` (2), `forceMeleeTarget = 2` = `RangedBool.IfRangedCaster` |
| 1176 | **PRESET + FLAGS** — deux ctors enchaînés | `0x4002 \| 0x2000000` = **`0x2004002`** = `TargetMatchesDynamicRule \| TargetIsEnemy \| AllowObscuredTargetByElevation` | `RANGE_FROM_CONFIG` (2), `forceMeleeTarget = 0` = `RangedBool.True` |

Sur 1176 le seul littéral visible dans le premier ctor est `0x4002` : le prendre pour le masque
perdrait `AllowObscuredTargetByElevation`. Sur 1170, `TargetIsEnemy` est **absent** — le filtrage
de camp vit dans la règle dynamique, qui **exempte** l'unité `constants.unitId` (`orksGrot`).
Rabattre 1170 sur `TargetIsEnemy` serait *plus restrictif que le natif*.

### Confrontation live — `tests/engine/runner/test_997_noop_damage_casts_live.py`

Montage : `rl_duel build --board MC1_67 --seed 777 --explicit-stats "orksRedGobbo:1"
--explicit-stats "deathNpc2PlagueMarine:1" --p-units "orksRedGobbo:1,deathNpc2PlagueMarine:1"
--a-units "orksNob,…" --hp-target 90000`, avec `TACTICUS_ALLOW_ROSTER_DEFICIT=1` (le garde de
roster compare l'id demandé à l'id **remappé** que publie le jeu — faux rouge connu). Les deux
porteurs npc montent sans injection de catalogue.

Ce que le jeu a répondu, et que le port reproduit :

- **1170, friendly-fire** — le caster placé **adjacent à sa propre cible**, un allié adjacent
  aussi : le live frappe `{cible, ennemi adjacent, ALLIÉ adjacent}` et **pas le caster**. Les deux
  faits sont contradictoires pour un port naïf (« les alliés sont touchés » *et* « le caster, qui
  est son propre allié, ne l'est pas ») — c'est ce qui rend la paire probante.
- **1170, règle dynamique** — le jeu n'offre **pas** l'allié dans `abilityTargets.fromHere`, alors
  que le masque ne porte aucun `TargetIsEnemy`. C'est la règle dynamique qui le refuse, et le port
  rend `2` sur lui / `0` sur l'ennemi.
- **1176, targeting** — le live frappe `{cible, les 2 unités directly-behind}`, avec
  `nrOfHits = 1` sur **chaque** volet.

### Quatre mutations adversariales, quatre rouges

Chaque garde a été **vue rouge** en mutant le port, message verbatim :

| mutation | message |
|---|---|
| 1170 : retirer `op_Subtraction(., caster)` | `set de cibles du PORT [77, 79, 85, 87] != set LIVE [77, 79, 87]` — `85` est le Gobbo |
| 1170 : wrapper le sélecteur dans `Enemies(...)` | `set de cibles du PORT [77, 79] != set LIVE [77, 79, 87]` — `87` est l'allié |
| 1170 : `get_dynamic_invalid_target_reason` → `0` | `le port ACCEPTE un allie comme cible d'ExplosivePresents … assert 0 == 2` |
| 1176 : `pick_n=1` au lieu de 2 | `set de cibles du PORT [77, 79] != set LIVE [77, 79, 81]` |

La borne de non-vide est **comptée**, pas supposée : chaque test assertionne `live` non vide avant
de comparer les ensembles, et le premier `assert set(live) == want` porte trois ids réels.

### Ce qui n'est PAS couvert

- **La MAGNITUDE du dégât** n'est pas confrontée — même confond que `test_plasma_cannon_live` :
  `execute_ability_attack` ne passe pas `is_ranged` à `attacker_modifiers`, donc les buffs ranged
  du caster manquent offline, et `_pick_randomly_n` peut désynchroniser le flux rng du volet
  DERRIÈRE (#215). Le targeting et le nombre de coups — c'est-à-dire exactement ce que ces deux
  ports décident — le sont.
- **L'exemption `orksGrot`** de la règle dynamique de 1170 n'est vérifiée qu'**offline** (aucun
  Grot dans le roster monté) ; c'est le seul chemin de cette règle qui n'ait pas de témoin live.
- **`Contaminated` (1244)** n'a aucun poseur porté : le gate dynamique de 1176 rend donc `0` dans
  tout montage actuel. Il est porté quand même — l'absence de règle rendrait `0` *par le chemin de
  repli*, même valeur pour une mauvaise raison, et cesserait d'être juste dès que l'effet entrera.
- **Le volet DERRIÈRE de 1176 à plus de 2 candidats** : quelles 2 unités sont piquées dépend de
  l'ordre d'énumération natif du pool (résidu #215, partagé avec Fragstorm/PlasmaCannon). Le
  montage en place deux, donc ce régime n'est pas exercé.
