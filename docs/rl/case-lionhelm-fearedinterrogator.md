# LionHelm (darkaAzrael) + FearedInterrogator (darkaAsmodai) — RE + port

> Etat : **RE TERMINEE ET CONFIRMEE EN GHIDRA + VTABLE RUNTIME**, port non encore ecrit
> (mise en veille reseau 2026-07-27). Les deux passifs etaient classes GAP-ABSENT par
> `docs/rl/passive-ability-coverage.md` (items #23 et #10 de la file dispatchable).

## 0. Confirmation d'existence (l'avertissement de l'audit)

Les deux symboles annonces par la file existent bien en ghidra et portent la mecanique que
leur nom suggere :

- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LionHelmAbility$$CreateBehaviour`
- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FearedInterrogatorAbility$$CreateBehaviour`

Les deux sont des **arbres DSL** (`DSLFactory.AddEffect` / `AddDynamicStatModifierEffect`) :
aucune logique imperative dans l'ability, tout vit dans les classes d'EFFET.

### Piege de methode rencontre — `data/symbols/<build>/frida/methods.tsv` est DEDUPE PAR ADRESSE

Mesure : 121 501 lignes, **121 501 adresses distinctes, 0 doublon**. Or le binaire fait de
l'**identical code folding** : plusieurs methodes au corps identique partagent une adresse et
**une seule survit** dans la table. Consequence directe et verifiee ici :

- `LionHelm_ExtraDmgEffect.CreateTargetSelector` est **ABSENT** de `methods.tsv` ;
- `LionHelm_ExtraBlockDamageEffect.CreateTargetSelector` y est a la RVA `f4bf30`, que
  **ghidra nomme `PathOfCommandExtraDmgEffect$$CreateTargetSelector`** — les deux tables
  ne survivent pas sur le meme nom, ce qui PROUVE le partage de corps.

=> **L'absence d'un symbole dans `methods.tsv` n'est PAS une preuve d'absence de la methode.**
Le depart se fait par la **VTABLE RUNTIME** (`resolveVtableSlot`, read-only, RPC `introspect.ts`),
slot `+0x538` = `CreateTargetSelector` (lu depuis
`IdunBattle.Entities.Effects.BaseEffect$$CreateTargetSelectorAndCache`, qui fait
`(**(vtable+0x538))(this, *(vtable+0x540))`).

Releve vtable (build `gqfc5mff6c`) :

| classe d'effet | slot 0x538 -> VA | selecteur effectif |
|---|---|---|
| `LionHelm_ExtraDmgEffect` | `180f4bf30` | `SurroundingFriends(owner, ConfigConst(range))` |
| `LionHelm_ExtraBlockDamageEffect` | `180f4bf30` | idem (MEME corps) |
| `LionHelm_ExtraBlockChanceEffect` | `180f55cf0` | idem + `UnitsFromFaction(DarkAngels)` |
| `FearedInterrogator_OwnerEffect` | `180e03180` | **defaut** (= le porteur seul) |
| `FearedInterrogator_TargetEffect` | `180f48cb0` | selecteur dedie (cf. §2) |
| `SmashaEadEffect` (temoin SELF) | `180e03180` | **defaut** |

`180e03180` = corps par defaut partage par tous les effets SELF -> il discrimine proprement
AURA vs SELF.

## 1. LionHelm — `TriggeredAbilityType` **1163** (0x48b), porteur `darkaAzrael` (HERO, pool)

Config gameconfig : `variables = {extraDmg[65]=437, blockDmg[65]=582, blockChance[65]=20}`,
`constants = {range: 2}`, `variablesAffectedByRarityBonus = [extraDmg, blockDmg]`
(**blockChance N'EST PAS scale par la rarete**).

i2 : « Friendly units within 2 hexes block an additional 582 Damage when they Block and deal
+437 Damage with attacks triggered by Overwatch. Other friendly Dark Angels within 2 hexes also
have their Block chance increased by +20% »

### `LionHelmAbility$$CreateBehaviour` (mirror 1:1)

```
AddEffect( EffectType.LionHelm_ExtraDmg = 1193 (0x4a9),
           abilityState = AbilityStateReference,
           targets      = Owner@0x148,
           turns        = null )
+ AddDynamicStatModifierEffect( targets   = Owner@0x148,
                                effectType= EffectType.LionHelm_ExtraBlockChance = 1232 (0x4d0),
                                statType  = StatType.BlockChance = 7,
                                turns = null, isHidden = false )
+ AddDynamicStatModifierEffect( targets   = Owner@0x148,
                                effectType= EffectType.LionHelm_ExtraBlockDamage = 1214 (0x4be),
                                statType  = StatType.BlockDamage = 8,
                                turns = null, isHidden = false )
```

(les trois combines par `AbilityBehaviour.op_Addition`). **Les trois effets-entites vivent sur
AZRAEL** ; la projection se fait par le `CreateTargetSelector` de chaque effet (mold AURA cote
SOURCE, identique a SpotterReworked / LordOfTheHost / DefenderOfTheGreaterGood).

⚠ Qualification d'enum obligatoire ici — les memes ids nomment autre chose ailleurs :
`EffectType 1214 = LionHelm_ExtraBlockDamage` mais `ActiveAbilityType 1214 = Hailstrike` ;
`EffectType 1193 = LionHelm_ExtraDmg` mais `TriggeredAbilityType 1193 = SynapticInsight` ;
`EffectType 1232 = LionHelm_ExtraBlockChance` mais `TriggeredAbilityType 1232 = EnvDefenderHealthBuff`.

### Volet 1 — `LionHelm_ExtraDmgEffect` (EffectType 1193)

`.ctor` = `BaseEffect(AbilityOrEffect(TriggeredAbilityType.LionHelm = 1163), hasAutomaticActivation = true)`.

Selecteur (vtable, corps `180f4bf30`) :
`SurroundingFriends(unit = Owner@0x148, range = AbilityConfiguration.GetNumberConstant(0x16 = range) = 2,
unique = true, unitSelectionType = OnlyAliveAndTargetable(3))` — **self EXCLU**.

`IdunBattle.Entities.Effects.Loki.LionHelm_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` :

```
amount = ConfigVar( AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@0x60 )
A      = HasEffect( Caster@0x160, EffectType.Overwatch_AutoAttack = 1009 (0x3f1),
                    onlyActive = false, targetType = EffectTargetType.Both = 6 )
         & IsOverwatchAttack()
B      = HasEffect( Caster@0x160, EffectType.GrimRetribution_CounterAttack = 1213 (0x4bd),
                    onlyActive = false, targetType = Both )
         & CurrentAbilityIs( AbilityOrEffect(TriggeredAbilityType.GrimRetribution = 1177) )
gate   = get_OwnerIsCaster & (A | B)
return   EffectBonus.ForAddition( gate, amount, source = AbilityOrEffect(LionHelm 1163) )
```

Canal = ADDITIF PRE-PERCAGE PAR COUP (`DamageModifiers.additive`), comme LordOfTheHost /
SpotterReworked. Cote port : `create_aura_attack_damage_bonus_for_ally`.

**Le gate `IsOverwatchAttack` n'est pas encore threade dans le ctx de l'agregateur AURA**
(`engine/runner/damage_model.py::_apply_ally_attack_damage_auras` -> `ctx`) : il faut y ajouter
`is_overwatch`, deja disponible en amont dans
`engine/runner/operations/damage_ops.py::_DamageOpsMixin.execute(..., is_overwatch=...)`
(le meme flag alimente deja `ability_pierce_effect_bonus`). Chaine a etendre :
`damage_ops.execute` -> `damage_model.attacker_modifiers` -> `_apply_ally_attack_damage_auras`.

i2 ne mentionne QUE l'Overwatch ; le decompile porte AUSSI la branche B (contre-attaque
`GrimRetribution` de `darkaHellblaster`, passif lui-meme non porte -> branche B inerte
aujourd'hui, mais elle se porte quand meme, gate `CurrentAbilityIs(1177)` + presence de
l'effet 1213).

### Volet 2 — `LionHelm_ExtraBlockDamageEffect` (EffectType 1214)

`.ctor` = `ADynamicStatModifierEffect( sourceAbility = AbilityOrEffect(LionHelm 1163),
unitEffectType = null, canBeImmuneTo = false, keepOnRevive = true, isMultiply = false )`.

Selecteur = `SurroundingFriends(Owner, range = 2, unique, OnlyAliveAndTargetable)` (self exclu).

`IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockDamageEffect$$GetDynamicStatModificationAmount(owner, target, effect)` :

```
ConfigVar( abilityType = TriggeredAbilityType.LionHelm = 1163,
           unit        = EffectSource( Get(effect) ),        // = AZRAEL, jamais le buffe
           variableType= AbilityVariableType.blockDmg = 20 (0x14) )
```

Stat modifie : `StatType.BlockDamage = 8`. Montant scale par le multiplicateur de rarete
d'AZRAEL (`blockDmg` est dans `variablesAffectedByRarityBonus`).

### Volet 3 — `LionHelm_ExtraBlockChanceEffect` (EffectType 1232)

`.ctor` identique (meme `ADynamicStatModifierEffect(...)`).

`IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockChanceEffect$$CreateTargetSelector` :
```
UnitsFromFaction( SurroundingFriends(Owner@0x148, GetNumberConstant(0x16 = range), true, OnlyAliveAndTargetable),
                  faction = UnitFaction.DarkAngels = 10,
                  unitSelectionType = OnlyAliveAndTargetable )
```
`IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockChanceEffect$$GetDynamicStatModificationAmount` :
`ConfigVar(LionHelm 1163, EffectSource(effect), AbilityVariableType.blockChance = 21 (0x15))`.
Stat modifie : `StatType.BlockChance = 7`. **PAS de scaling rarete** (blockChance hors
`variablesAffectedByRarityBonus`).

### Question OUVERTE a trancher live (avant d'ecrire les volets 2/3)

Les volets 2/3 sont des `AStatModifierEffect` : le natif MATERIALISE une `ValueModification`
sur le `UnitStats` de chaque cible-selecteur. Or le seed offline lit `combatSnapshot`
(`GetStat` deja resolu) -> si un allie est a portee au moment du build, sa `blockChance` /
`blockDamage` seedee **contient deja** la contribution LionHelm. Ajouter naivement un canal
aura de block DOUBLE-COMPTERAIT.

Mesure a faire (2 builds, board `MC1_67`) : `combatSnapshot` de l'allie
(a) a distance <= 2 d'Azrael, (b) a distance 3 — comparer `blockChance` / `blockDamage`.
Puis DEPLACER l'allie in/out de portee et re-lire `combatSnapshot` pour voir si le natif
re-evalue (RefreshEffects) ou fige.

## 2. FearedInterrogator — `TriggeredAbilityType` **1235** (0x4d3), porteur `darkaAsmodai` (HERO, pool)

Config gameconfig : `variables = {extraDmg[65]=728, extraHits[65]=2}`,
`variablesAffectedByRarityBonus = [extraDmg]` (**extraHits non scale**), pas de constants.

i2 : « Deals +728 Damage against enemies that are Suppressed, Stunned, or that are adjacent to
another friendly Dark Angel. Scores 2 additional hits if the enemy is also Chaos. »

### `FearedInterrogatorAbility$$CreateBehaviour` (mirror 1:1)

```
AddEffect( EffectType.FearedInterrogator_Owner  = 1294 (0x50e), AbilityStateReference,
           source = Owner@0x148, targets = Owner@0x148, options = default )
&
AddEffect( EffectType.FearedInterrogator_Target = 1295 (0x50f), AbilityStateReference,
           source = Owner@0x148, targets = Owner@0x148, options = default )
```
(combines par `AbilityBehaviour.op_BitwiseAnd`). Les deux effets-entites vivent sur ASMODAI ;
`_Target` se projette sur les ENNEMIS via son selecteur, `_Owner` reste sur Asmodai (selecteur
DEFAUT `180e03180`).

`.ctor` (corps partage par les deux classes) =
`BaseEffect(AbilityOrEffect(TriggeredAbilityType.FearedInterrogator = 1235), hasAutomaticActivation = true)`.

### `FearedInterrogator_TargetEffect$$CreateTargetSelector` — le MARQUEUR

```
A       = ValidNormalAttackTargets( unit = Owner@0x148, unitTile = Tiles(Owner@0x148),
                                    range = null, ignoreRule = null, additionalRule = null )
friends = UnitsFromFaction( Friends(of = Owner@0x148, entities = <all>@0x80,
                                    selectionType = OnlyAliveAndTargetable),
                            UnitFaction.DarkAngels = 10, OnlyAliveAndTargetable )
          - Owner@0x148                                  // « ANOTHER friendly Dark Angel »
E       = EntitiesWithAnyEffect( A, [ EffectType.Stunned = 1162 (0x48a),
                                      EffectType.Pinned  = 1065 (0x429) ] )
B       = AdjacentUnits( friends, unique = true, OnlyAliveAndTargetable )
return    Unique( E + (A & B) )
```

- « Suppressed » de l'i2 = `EffectType.Pinned` (1065) — meme effet que pose SuppressiveFire (#74).
- Le marqueur ne se pose QUE sur des cibles d'attaque normale LEGALES d'Asmodai
  (`ValidNormalAttackTargets`) : c'est un gate de PORTEE reel, absent du texte i2.

### `FearedInterrogator_OwnerEffect` — les deux bonus (selecteur DEFAUT = Asmodai seul)

`IdunBattle.Entities.Effects.Loki.FearedInterrogator_OwnerEffect$$CreateEffectDamageBonusForAttack` :
```
amount = ConfigVar( AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@0x60 )
gate   = get_OwnerIsCaster
       & HasEffect( Target@0x178, EffectType.FearedInterrogator_Target = 1295,
                    onlyActive = false, targetType = Both )
return   EffectBonus.ForAddition( gate, amount )
```

`IdunBattle.Entities.Effects.Loki.FearedInterrogator_OwnerEffect$$CreateEffectHitsBonusForAttack` :
```
amount = ConfigVar( AbilityVariableType.extraHits = 19 (0x13), GetAbilityState(this), config@0x60 )
gate   = get_OwnerIsCaster
       & HasEffect( Target@0x178, FearedInterrogator_Target 1295, false, Both )
       & HasTrait( Target@0x178, UnitTrait 0x7ea = 2026 = grande-alliance Chaos )
return   EffectBonus.ForAddition( gate, amount )
```

=> cote port : **SELF** effect sur Asmodai, canaux
`create_effect_damage_bonus_for_attack` + `create_effect_hits_bonus_for_attack`, dont le gate
est un PREDICAT sur la CIBLE (« la cible satisfait le selecteur de `_Target` »). Le gate trait
2026 = grande-alliance Chaos, deja derive de `GrandAllianceId` ailleurs dans le moteur
(RitesOfBattle / BeaconOfRage).

## 3. Plan de validation (2 cas discriminants par passif, dont UN NEGATIF)

| passif | cas POSITIF | cas NEGATIF (le passif ne mord PAS) |
|---|---|---|
| LionHelm ExtraDmg | `darkaHellblaster` (trait Overwatch) a <= 2 hexes d'Azrael, overwatch declenche par un mover ennemi -> +extraDmg/coup | (a) meme overwatch avec Azrael a distance 3 ; (b) attaque NORMALE du meme allie a <= 2 hexes (gate `IsOverwatchAttack` faux) ; (c) overwatch d'AZRAEL lui-meme (self exclu du selecteur) |
| LionHelm block | allie a <= 2 (blockDmg) / allie Dark Angels a <= 2 (blockChance) | allie a distance 3 ; allie NON-DarkAngels a <= 2 (blockDmg oui, blockChance non) |
| FearedInterrogator | Asmodai attaque un ennemi Pinned/Stunned -> +extraDmg ; ennemi Pinned ET Chaos -> +extraDmg ET +extraHits | ennemi ni Pinned/Stunned ni adjacent a un autre Dark Angel ami -> AUCUN bonus ; ennemi Pinned NON-Chaos -> +extraDmg mais PAS +extraHits |

Patron de test = `tests/engine/runner/test_psychic_fortress_aura_live.py` (replay-diff
`off_ph == live_ph` au coup pres + assertion sur la presence/absence du modifier) et
`tests/engine/runner/test_overwatch_live.py` (declenchement de l'overwatch par un move drive).
