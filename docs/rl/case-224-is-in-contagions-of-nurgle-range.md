# case-224 item 4 — `IsInContagionsOfNurgleRange` : un nœud DSL, et le canal d'aura qu'il ouvre

Le prédicat de `CursedPlagueBellAttackAbility` (Corrodius, `deathBlightbringer`). Le case-211 §5 le
citait comme non porté : ce cas le porte, et avec lui le **canal d'aura** dont il dépend — qui était
un résidu nommé deux fois dans `runner/abilities/deathguard.py`.

---

## 1. Les deux questions qui décidaient de la forme du port

**a) Nœud DSL ou helper impératif ?** — **NŒUD DSL** (kind T).
`...CursedPlagueBellAttackAbility$$IsInContagionsOfNurgleRange` est une *propriété* dont le corps
compilé est exactement `DSLTriggers.IsInUnitContagionsOfNurgleAura(Actor, Owner)`. Le compilateur
l'**inline** dans `...CursedPlagueBellAttackAbility$$CreateTrigger` — les deux xrefs de la propriété
ne sont que des entrées de table de méthodes. Rien à recâbler à la main : le prédicat *est* une
branche de l'arbre `CreateTrigger`.

**b) Sur quoi porte la « range » ?** — sur **l'unité OWNER**, pas sur une entité-effet posée ni sur
un ensemble de tuiles. `IdunBattle.Entities.Triggers.AuraEffectRangeFormula$$Calculate` lit la
**définition** de l'effet 1071 dans la base d'effets (`GetEffect(effectType)`), la caste en
`IAuraEffect`, exige `HasTrait(owner, ContagionsOfNurgle)` et évalue `GetCurrentRange()` **sur
l'owner**. Aucune instance d'effet n'est requise sur le porteur : seul son **trait** compte.

⚠ `0x42f = 1071` est ici un **`EffectType`** (`ContagionsOfNurgle_ArmorReduction1`), pas le
`TriggeredAbilityType.CursedPlagueBell` qui vaut le même 1071 (case-211).

---

## 2. Le décompilé

```csharp
// IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$CreateTrigger
On(9)
& ( OwnerIsTarget | <DSLTriggers+0x20> )
& !CasterIsTarget
& CurrentAttackDamageProfilesContain(0xd = Psychic)
& AreEnemies(Actor@0x40, Owner@0x30)
& HasTrait(Actor@0x40, 0x3ea = UnitTrait.Psyker)
& IsInContagionsOfNurgleRange                       // <- l'item
& !CurrentAbilityIs(this)
```

Slots de `IdunBattleLogic.Entities.DSLSelectors` (build `rnca9r7q6c`, le `DSLFactory` monolithique
a été scindé) : `+0x20 AllUnits · +0x30 Owner · +0x40 Actor · +0x48 Caster · +0x60 Target ·
+0x68 ActiveTarget/Subject`. Mapping **établi par recoupement**, pas deviné :
`...Lakrimae_SummonPoxwalker_Ability$$CreateTrigger` lit
`Filter(+0x20, AreFriends(+0x30, +0x68) & IsUnitWithVisualId(+0x68, poxwalker))`,
`AreEnemies(+0x30, +0x60)`, `IsDead(+0x60)`, `!HasTrait(+0x60, Mechanical)` — seule l'affectation
ci-dessus rend ce trigger cohérent avec Lakrimae.

```csharp
// IdunBattleLogic.Entities.DSLTriggers$$IsInUnitContagionsOfNurgleAura(target, unit)
var range = DSLFormulas.ContagionsOfNurgleRange(unit, unitSelectionType: 0, isNextTurn: false);
var dist  = DSLFormulas.MinDistance(target, unit);
// ⚠ la classe se lit sur le POINTEUR chargé avant `il2cpp_object_new`, PAS sur le nom du `.ctor`
// (corps trivial dédupliqué, cf. §2.1) — c'est le même global que `DSLTriggers$$AmountIsEqualOrGreater`
return new AmountIsEqualOrGreaterAbilityTrigger(amount: range, minAmount: dist);  // dist <= range
```

```csharp
// IdunBattle.Entities.Triggers.AuraEffectRangeFormula$$Calculate
unit = <selecteur>.SelectSingle(entities);            if (unit == null) return 0;
aura = <effets>.GetEffect(effectType) as IAuraEffect; if (aura == null) return 0;
if (!UnitExtensions.HasTrait(unit, aura.GetTrait())) return 0;
entities.<Owner @+0x18> = unit;
return (isNextTurn ? aura.GetNextTurnRange() : aura.GetCurrentRange()).Calculate(entities);
```

```csharp
// IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect
GetTrait()         => 0x7eb = 2027 = UnitTrait.ContagionsOfNurgle      // corps constant
GetMaxRange()      => Direct(3)
GetCurrentRange()  => GetRangeOnOwnerTurn( StatAmount(Owner, 0xc = TurnsStarted) )
GetNextTurnRange() => GetRangeOnOwnerTurn( Sum(StatAmount(Owner, 0xc), Direct(1)) )
GetRangeOnOwnerTurn(n) => n <= 2 ? 1 : (n <= 4 ? 2 : 3)
```

`GetRangeOnOwnerTurn` est l'arbre `ConditionalAmount` équivalent de la surcharge compilée
`$$CalculateRange(roundsInGame)` (`if (2 < n) return (4 < n) + 2 ; return 1`) — même table, deux
formes natives. Le port n'en a **qu'une**, et le foyer existant
`deathguard.contagions_of_nurgle_range` (mirror de `$$CalculateRange(unit)`, SpawnPoxwalkers) lui
reste value-identique.

### 2.1 Les deux comparateurs sont INCLUSIFS — même rayon effectif

| prédicat natif | classe de condition réellement instanciée | comparateur | rayon effectif (`TurnsStarted` 1 / 3 / 5) |
|---|---|---|---|
| `IsInUnitContagionsOfNurgleAura` (par UNITÉ) | `AmountIsEqualOrGreaterAbilityTrigger` | `dist <= range` **INCLUSIF** | 1 / 2 / 3 |
| `BattleQuery$$GetInRangeAuraAmount` (par ÉQUIPE) | — (boucle en dur) | `dist <= range` **INCLUSIF** | 1 / 2 / 3 |

`IsInUnitContagionsOfNurgleAura` charge, juste avant son `il2cpp_object_new`, **le même pointeur de
classe** que `IdunBattleLogic.Entities.DSLTriggers$$AmountIsEqualOrGreater` — et pas celui de
`IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreater`. Or
`IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` finit par
`return minAmount.Calculate(entities) <= amount.Calculate(entities)`.

> ⚠ **CE POINT A ÉTÉ LU FAUX DEUX FOIS, ET C'EST LE MÊME PIÈGE (#293).** Le `.ctor` appelé porte le
> nom `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$.ctor`, dont le `ShouldTrigger`
> est bien `<` STRICT. **Ce nom ne désigne pas la classe instanciée** : le ctor est un corps trivial
> (`base..ctor` + `[this+0x18] = amount` + `[this+0x20] = minAmount`) que IL2CPP **déduplique** entre
> toutes les conditions de même layout, et la table des symboles ne lui donne **qu'un** propriétaire.
> Le même piège s'était présenté **dans l'autre sens** sur `MurderousSwing` (#108, ctor étiqueté
> `AmountIsEqualOrGreater...` pour une classe `AmountIsGreater...`) et sur `UnitsDirectlyBehind`
> (#48, résolu par le singleton de classe). **La seule ancre est le pointeur de classe**, jamais le
> nom du ctor — et il change de propriétaire d'un build à l'autre.
>
> Re-dérivation mécanique, offline, sans runner :
> `python scripts/python/probe_293_aura_predicate_comparator.py --inventory` — il lit le pointeur de
> classe dans les octets de `GameAssembly.dll`, corrobore par l'encodage `setg`/`setge` des deux
> `ShouldTrigger`, et rend l'inventaire des **22** sites d'instanciation par famille.

Les deux autres modèles qui pouvaient expliquer l'écart d'une unité sont **réfutés étage par étage** :

* `MinDistance` natif = `hexdist − 1` ? **Non.**
  `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate` accumule
  `Math.Min(min, PositionComponent.Distance(b, a))` ;
  `IdunBattle.Entities.Components.PositionComponent$$Distance` =
  `IdunBattle.Utils.Hex.CubeCoordinate$$Distance(this.ToCube(), other.ToCube())` =
  `Max(Max(|dx|, |dy|), |dz|)`. Aucun offset sur le chemin.
* `GetCurrentRange` natif = table + 1 ? **Non.** `GetRangeOnOwnerTurn` est lu en entier (§2 ci-dessus)
  et le port en est le mirror exact. Ce modèle était déjà réfuté indépendamment par le probe
  d'ÉQUIPE — mais sur `EntropyCannons`, donc sur une **autre** définition d'effet ; il l'est
  maintenant sur 1071 lui-même, par lecture.

Confirmation live : `case-224-cursed-plague-bell-attack.md` §3.2 — seuil natif =
`GetCurrentRange(TurnsStarted)` exactement, à deux paliers (range 2 → d=1 **et d=2**, pas d=3 ;
range 3 → d=2 **et d=3**, pas d=4), attribution par le tag natif `Passive_Ability_Type = 1071`.

---

## 3. Ce qui est porté

| Fichier | Contenu |
|---|---|
| `engine/entities/effects/aura.py` (**neuf**) | registre `IAuraEffect` : `aura_trait` / `aura_max_range` / `aura_range_on_owner_turn` / `aura_current_range` / `aura_next_turn_range` / `is_aura_effect`. C'est l'étage de portée **partagé** par les deux consommateurs. |
| `engine/entities/formulas.py` | `MinDistance` (mirror `MinDistanceFormula$$Calculate`, `int.MaxValue` sur enumération vide) ; `AuraEffectRange` (mirror `AuraEffectRangeFormula$$Calculate`) |
| `engine/entities/triggers.py` | `IsInUnitAura` = `AmountIsEqualOrGreater(AuraEffectRange, MinDistance)` ; docstring de `IsInTeamAura` remise à l'état final (le résidu est levé) |
| `engine/runner/abilities/deathguard.py` | `is_in_contagions_of_nurgle_range()` = `IsInUnitAura(Actor(), 1071, Caster())` + le bloc RE de `CreateTrigger` |
| `engine/battle_query.py` | `get_in_range_aura_amount` / `is_in_team_aura_range` (mirror complet des deux slots `IBattleQuery`) |
| `engine/runner/abilities/behaviours/context.py` | câblage `ctx.is_in_team_aura` |
| `engine/dsl/base.py` | commentaire du champ `is_in_team_aura` |

`Owner@0x30` est rendu par `Caster()` : le port ne matérialise pas de sélecteur `Owner` distinct
(`ctx.owner` retombe sur `ctx.caster`, hypothèse Owner==Caster déjà actée pour les *triggered*).

Le gate `HasTrait(owner, ContagionsOfNurgle)` lit `ctx.has_trait`, dont le substrat est l'ensemble
**effectif** des traits runtime depuis #264/#270 (`combatSnapshot.units[].traits`, avec repli
gameconfig + alliance) : la mesure live prime sur la reconstruction. Les gardes de ce cas ont été
re-jouées **après** ce rebase, sans écart.

**Le canal d'aura était un résidu, et sa levée est une correction de fidélité.** `ctx.is_in_team_aura`
n'était jamais fourni, donc `IsInTeamAura` rendait toujours `False` et la branche AURA de
`...PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger` était morte : le port **refusait des
cibles que le natif accepte**. Le porter n'était pas un détour — c'est le même
`GetTrait` + `GetCurrentRange` que le prédicat de l'item, et c'est ce qui le rend confrontable live.

**Ce que ce cas ne porte PAS** : l'ability `CursedPlagueBellAttackAbility` elle-même
(`CreateBehaviour` = `AttackWithAttackDamage` Psychic), ni les autres branches de son `CreateTrigger`
(`On(9)`, `CurrentAttackDamageProfilesContain`, `CurrentAbilityIs`).

---

## 4. Validation live

**Oracle** : `abilityTargets(deathCrawler, EntropyCannons 1168)`. Son
`...EntropyCannonsAbility$$GetDynamicInvalidTargetReason` rend 0 **ssi**
`IsInTeamContagionsOfNurgleAura(target, caster)` **OU** `HasNegativeModifier(target, FixedArmor)` ;
sur un runner frais la seconde branche est muette (aucun modificateur négatif d'armure), donc la
légalité de la cible **est** le prédicat d'aura natif.

Montage (board `MC1_67` non requis — `C1_02` est MoW-capable) : `deathTyphus` (**porteur** du trait)
+ `necroWarden` (allié **sans** le trait) + MoW `deathCrawler`, face à trois ennemis tanky. Le
porteur est **déplacé** aux distances 1, 2, 3, 4 de l'ennemi ; `--advance N` fait monter
`TurnsStarted(porteur)`, seul levier qui exerce les paliers 2 et 3.

### 4.1 Le seuil natif suit `TurnsStarted` — les trois paliers

| `TurnsStarted(porteur)` | `GetCurrentRange` attendu | seuil natif MESURÉ (dernier `d` accepté) | accord port |
|---|---|---|---|
| 1 (`--advance 0`)  | 1 | **1** (d=1 oui ; d=2,3,4 non) | 4/4 |
| 3 (`--advance 4`)  | 2 | **2** (d=1,2 oui ; d=3,4 non) | 4/4 |
| 5 (`--advance 8`)  | 3 | **3** (d=1,2,3 oui ; d=4 non)  | 4/4 |

**12 confrontations distance, 0 désaccord**, et le seuil *bouge* avec la seule variable d'entrée de
la formule. C'est ce déplacement — pas un point isolé — qui distingue la table 1/2/3 d'un rayon
constant.

### 4.2 Le gate TRAIT

Porteur écarté à ≥ 6 hex, `necroWarden` (**sans** `ContagionsOfNurgle`) amené **au contact** de
l'ennemi : natif = `False`, port = `False`. Rejoué dans les trois régimes — **3/3**.

### 4.3 Mutation adversariale — trois mutations, trois signatures disjointes

| mutation | effet mesuré |
|---|---|
| gate `HasTrait` retiré de `get_in_range_aura_amount` | **étape TRAIT seule** rouge (natif `False`, port muté `True`) ; les 4 distances restent vertes |
| `aura_range_on_owner_turn` figée à `1` | **2/4 distances** rouges à `TurnsStarted=5` — exactement d=2 et d=3, celles où la table dépasse 1 |
| comparateur `<` rendu `<=` (donc STRICT) | **1/4** rouge à `TurnsStarted=1` — exactement `d == range` |

La troisième est celle qui compte le plus : elle prouve **live** que le comparateur de la version
d'ÉQUIPE est bien INCLUSIF. Par contraste, le STRICT de la version par UNITÉ est une propriété
*propre* à ce prédicat (§2.1), pas une lecture fautive répercutée des deux côtés.

### 4.4 Non-régression

`test_mow_targeting_predicate_live.py` **7/7**, `test_contagions_of_nurgle_new_unit_live.py`
**3/3**, `test_tile_term_unit_gated_playbooks_live.py -k deathBlightbringer` **10/10** (case-211
inchangé). Le nouveau `test_contagions_aura_range_live.py` fait **3/3** et **rougit** sous la
mutation du comparateur (vérifié).

---

## 5. Ce que ce cas n'établit PAS

* ~~**Le comparateur de la version par UNITÉ n'est pas mesuré live**~~ — **CLOS**. Porter
  `CursedPlagueBellAttackAbility` (1071) lui a donné son premier consommateur MOTEUR, donc son
  premier montage confrontable (`case-224-cursed-plague-bell-attack.md` §3.2 : seuil natif =
  `GetCurrentRange(TurnsStarted)` exactement, deux paliers), et #293 a **attribué** l'écart d'une
  unité au COMPARATEUR par lecture du pointeur de classe (§2.1). Le prédicat est INCLUSIF, comme
  celui de la version d'équipe. Garde re-dérivable :
  `python scripts/python/probe_293_aura_predicate_comparator.py`.
* **`GetNextTurnRange` / `isNextTurn=true`** : porté (mirror), jamais exercé. Ses consommateurs sont
  `CursedPlagueBellMovementAbility$$GetTargetsSelector` (paramètre `isDangerZone`) et
  `CursedPlagueBell_DangerZoneEffect`, hors périmètre.
* **`unitSelectionType`** (`AuraEffectRangeFormula+0x1c`) : écrit par le ctor, **lu par aucun chemin**
  de `Calculate` — non porté. Les call-sites Contagion passent 0 ; `Lakrimae_SummonPoxwalker` passe 1
  et retombe sur la même portée.
* **`SynapseEffect`** : second `IAuraEffect` (son `$$GetNextTurnRange` est nommé), **non porté** —
  aucun consommateur mirroré ne le demande. Un `EffectType` hors registre rend « cast échoué », ce
  qui est fidèle pour les deux call-sites portés et faux pour un futur consommateur Synapse.
* **Un porteur d'aura MULTI-TUILES** : `MinDistance` itère les entités et lit **une** position par
  entité (`PositionComponent.Distance`), pas l'empreinte de pieds — conforme au natif, mais non
  exercé sur une unité multi-tuiles.
* **Un trait `ContagionsOfNurgle` ACCORDÉ en bataille** (`AddTraitOperation`) : le substrat lit les
  traits du `StatsComponent` (gameconfig + alliance), même limite que case-211 §3.

---

## 6. Reproduire

```bash
cd scripts/python
python probe_224_contagions_aura_range.py --offline-only
python probe_224_contagions_aura_range.py --board C1_02 --seed 4242              # palier 1
python probe_224_contagions_aura_range.py --board C1_02 --seed 4242 --advance 4  # palier 2
python probe_224_contagions_aura_range.py --board C1_02 --seed 4242 --advance 8  # palier 3
python -m pytest tests/engine/runner/test_contagions_aura_range_live.py -q
```

Le probe n'arme **aucun hook** : il ne lit que `abilityTargets` / `decisionView` / `observeBattle` /
`combatSnapshot` / `boardGraph` et pilote par `applyAction`. Aucune réinjection.

**Piège de montage, mesuré** : avec un seul ennemi, `--advance 6` termine la bataille et la MoW
disparaît de `decisionView.mows` — l'oracle s'évapore sans erreur. D'où les trois ennemis tanky.
