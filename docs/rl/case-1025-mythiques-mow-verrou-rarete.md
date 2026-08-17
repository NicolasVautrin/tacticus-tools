# #1025 — `MoreGitzOverEre` + `ElectrochaffBackups` : la POSE est portée, le BONUS bute sur un capteur

Deux abilities **mythiques** de Machine of War. Les deux ont la **même structure** : une face POSE
sans aucun gate, et une face DÉGÂT dont le **premier conjoint utile** est `HasRarity(…, 5 = Mythic)`.
La première est portée et confrontée live ; la seconde ne l'est pas, et l'inscrire sans son gate
serait un terme **permissif**.

## 1. Ce qui est LU au décompilé

### `ElectrochaffBackups` — `TriggeredAbilityType` 0x5ae = 1454 (`tauBroadside`, `tauNpcMoWBroadside`)

`classes.tsv` : parent `IdunBattle.Entities.Abilities.BaseTriggeredAbility`, deux méthodes propres.

```
$$CreateTrigger  =  op_BitwiseOr(
     On(0x3e = EffectAdded, alive) & <commun> & TriggeringEffectIs(0x462 = Markerlight),
     On(0x0f = DamageTaken, alive) & <commun> & IsRangedAttack() )
   avec <commun> = AreEnemies(Owner@<DSLSelectors+0x30>, Target@<+0x60>, 0)
                 & IsNormalUnit(Target@<+0x60>)

$$CreateBehaviour =
   turns = TurnsFromRounds( GetNumberConstant(config@<this+0x20>, 0x45 = nrOfRounds) )
   If( HasEffect(Target@<+0x60>, 0x5a6, onlyActive: 0, effectTarget: 6),
       ChangeEffectTurns(Target@<+0x60>, 0x5a6, turns, changeType: 1 = ChangeType.Set),
       AddEffect(0x5a6, get_AbilityStateReference(this), source = Owner@<+0x30>,
                 targets = Target@<+0x60>, turns) )
```

`ElectrochaffBackups_DamageReductionPctEffect` (`EffectType` 0x5a6 = 1446) dérive de
`DamageModifierAbilityEffect` (`.ctor(this, 0x5ae, 0)` — l'ability parente, LUE) :

```
$$CreateDamageModifier = EffectBonus$$ForPercentDecrease(
      get_OwnerIsCaster
    & HasRarity( Target@<+0x60>, 5 = Mythic )
    & AreFriends( Target@<+0x60>, EffectSource(Effect@<+0x38>), 0, false ),
      ConfigVar(0x46 = dmgReductionPct, GetAbilityState(effet), effet@+0x60) )
```

`DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack` délègue au slot `CreateDamageModifier`
(vtable +0x728) : la contribution part donc sur la face **ATTAQUANT**.

### `MoreGitzOverEre` — `TriggeredAbilityType` 0x5b0 = 1456 (`orksRukkatrukk`, `orksNpcMoWRukkatrukk`)

`classes.tsv` : parent `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` ; la classe
n'override **que** `$$GetEffectType`, corps entier `return 0x5a9` (= 1449). La base fournit le reste :

```
AOwnerEffectTriggeredAbility$$CreateTrigger   = OnOwnerSpecificAbilityInit(this.AbilityType)
AOwnerEffectTriggeredAbility$$CreateBehaviour = If( CreateCondition(abilityState),
    AddEffect( GetEffectType(), AbilityState(Owner@<+0x30>, AbilityType(this)),
               source = Owner, targets = Owner, options = <Nullable ZERO> ) )
```

→ owner-effect **PERMANENT** posé à l'init, patron `Vitarus` / `NornCrown` / `ToughToKill`.

`MoreGitzOverEre_ExtraDamagePctEffect` (1449) dérive de `BaseEffect` et implémente deux faces :

```
$$CreateEffectDamageBonusForAttack = EffectBonus$$ForPercentIncrease(
      get_OwnerIsTarget
    & AreFriends( Caster@<+0x48>, EffectSource(Effect@<+0x38>), 0, false )
    & HasRarity( Caster@<+0x48>, 5 = Mythic )
    & IsMeleeAttack & IsNormalAttack,
      ConfigVar(0xa = extraDmgPct, GetAbilityState(effet), effet@+0x60) )

$$CreateTargetSelector = Unique( Enemies( Owner@<+0x30>,
      AdjacentUnits( Friends(Owner, UnitsWithVisualId(
            VisualUnitIdFromUnitId(Get(GetStringConstant(0 = unitId))), 1), 3), 1, 3)
    + Filter( AllAliveUnits@<+0x20>,
              AmountIsEqualOrGreater(
                  Friends(Owner, UnitsWithRarity(AdjacentUnits(ActiveTarget@<+0x68>, 1, 3),
                                                 5 = Mythic, 3), 3),
                  Direct(2) ) ), 3) )
```

Gameconfig : `unitId = "orksSmnSquig"`, `extraDmgPct = [10, 13, 16, 20]` (4 paliers).
i2 concorde mot pour mot : « Enemies that are adjacent to a friendly **Squig** or adjacent to **two
or more** friendly **Mythic** characters take +X% Damage from **normal melee** attacks by **Mythic**
characters. »

## 2. LE VERROU — `HasRarity` n'a aucun substrat côté port

`IdunBattle.Entities.UnitExtensions$$HasRarity`, `IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger`
et `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` comparent **tous trois**
`GetBaseUnitComponent(entity) + 0x74` au littéral. Aucune autre voie native.

Côté port, **re-mesuré pour cette tranche** :

| source | porte la rareté ? |
|---|---|
| `combatSnapshot` / `decisionView` (hooks) | non |
| `UnitContext` (`engine/entities/unit_context.py`) | non |
| gameconfig | non — `BaseRarity = "Common"` pour `orksRukkatrukk` **et** `tauBroadside` |

Même verrou que `ShieldOfFaithNonOwnerPlaybook` et les trois faces MOVE de `#477-r37-r1`. Ce qu'il
faudrait : `combatSnapshot.units[].rarity` ← `IdunBattle.Entities.Components.BaseUnitComponent.Rarity`
(+0x74), donc **une fenêtre de reinject**. Le seed BC porte déjà 10 unités `Rarity == 5`, et
`--unit-stat "<vis>:Rarity=5"` l'écrit par unité : le verrou est un **capteur manquant**, pas une
limite de montage.

⇒ les **deux** effets (1446, 1449) restent **hors `EFFECT_CLASSES`**. Un `BaseEffect` générique rend
`None` sur tous les canaux : la dégradation est **restrictive**, jamais permissive. Résidu `#1025-r1`.

## 3. Ce qui EST porté, et comment il a été confronté

| face | port | confrontation |
|---|---|---|
| trigger + behaviour 1454 | `runner/operations/triggers/loki/electrochaff_backups.py`, `RELIC_ABILITY_TRIGGERS["ElectrochaffBackups"]` | live, 4 étages |
| owner-effect 1449 | `ABILITY_INIT_OWNER_EFFECTS["MoreGitzOverEre"]` | live, 3 étages |

**La voie de registration d'une mythique est celle de la RELIQUE**, et c'est lu :
`IdunMetaLogic.UserProgress.TertiaryAbilities$$GetTertiaryAbility` branche sur item-relique OU
mythique et écrit le **même** `BC.Units[].TertiaryAbility` ; `UnitFactory$$AddConfiguredAbilities`
fait l'unique `TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)`. Un registre
`MYTHIC_*` séparé serait un artefact du port. Le gameconfig, lui, les range sous `mythicAbilities` —
clé **META** que `collect_triggered_abilities` ne lit pas, exactement comme le natif.

### Mesures live (build `rnca9r7q6c`, board `MC1_67`, seed 777)

- `--equip-mythic tauBroadside` → cast `TwinSmartMissileSystem` : la cible porte
  `Markerlight(r4)` **et** `ElectrochaffBackups_DamageReductionPct(r2)`. **Sans** `--equip-mythic` :
  `Markerlight(r4)` **seul**. Le régime est SÉPARANT.
- attaque normale ranged (5 coups) : **5** blocs `[Ability_Power e=81 «ElectrochaffBackups»]`, et la
  durée observée reste **r2**. `ChangeType.Add` donnerait 10 → **`Set` est prouvé par la mesure**,
  pas déduit du littéral seul.
- `r2` = `ConvertRoundsToTurns(nrOfRounds = 1)` avec 2 joueurs : le `TurnsFromRounds` est confirmé.
- `--equip-mythic orksRukkatrukk` → la MoW porte `1449 MoreGitzOverEre_ExtraDamagePct` avec
  `remaining = 0` (permanent, mirror du `Nullable` d'options ZERO). Sans : rien.
- port sur le même état : `hp 10542 → 7777` — **identique au live** — effet 1446 posé, `turns = 2`.

⚠ **Une MoW n'est PAS dans `decisionView.units`** : elle est hors-plateau (ni PV ni tuile) et vit
dans `decisionView.mows`, clé `casterId`. La chercher dans `units` rend un `skip` silencieux.

⚠ **Granularité du vecteur `On(0x0f)`** : le natif émet par COUP (5), le port une fois par profil
d'arme (2). Sans effet observable ici — `Set` est idempotent — mais ce ne serait pas le cas d'un
behaviour accumulatif.

⚠ **Le cliquet live de `MoreGitzOverEre` passe SANS l'entrée `ABILITY_INIT_OWNER_EFFECTS`** (mesuré) :
l'effet arrive par la CAPTURE, sa `CreateActiveCondition` héritée étant la constante VRAIE. L'entrée
n'est un filet que pour les chemins **purement offline**, et seul le cliquet OFFLINE le montre.

## 4. Résidus

- **`#1025-r1`** — canal `rarity` absent : les faces DÉGÂT de 1446 et 1449 ne sont pas portées.
  `BLOCAGE: capteur`.
- **`#1025-r2` — FERMÉ (2026-08-15).** `damage_taken_triggers` threade désormais
  `source_ability` en `ability_type` (`AbilityEntities+0x60 = CurrentAbility`). Trois lectures
  l'établissent :
  1. `IdunBattle.Operations.ApplyDamageOperation$$Execute` ne construit **qu'UN SEUL**
     `AbilityEntities` (une seule invocation du ctor à 33 paramètres, après `memset(.., 0x128)`) et
     le réutilise pour ses TROIS publications `On(0x39)` / `On(0xf)` / `On(0x10)` — le `+0x60` du
     vecteur `DamageTaken` est donc celui que #1020-r3 avait déjà résolu en `source_ability`
     (`DamageAppliedResult+0x40`) ;
  2. `IdunBattleLogic.Entities.DSLTriggers$$IsRangedAttack()` (la surcharge SANS argument, celle
     d'`ElectrochaffBackups`) alloue son propre sélecteur d'ability : la classe que
     `IdunBattleLogic.Entities.DSLSelectors$$.ctor` range en **`+0x88`**, c'est-à-dire
     `AbilityTypeSelector.CurrentAbilitySelector` — donc `+0x60`, pas `+0x98` ;
  3. `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` (slot 3) rend VRAI sur `Ranged(2)`
     **sans lire aucune position** (`case 2: return true;`).

  Régime fermé, et il n'est pas théorique : une attaque d'ability déclarée `Ranged` portée **au
  contact** était refusée par le port. Garde :
  `test_1025_electrochaff_backups_offline.py::test_branche_degat_accepte_une_ability_Ranged_AU_CONTACT`
  (même montage que le bras négatif — seules les deux tuiles restent adjacentes, seul le canal
  change — avec contre-épreuve `Melee` dérivée du gameconfig).
- **`#10013`** (ouvert par la même tranche) — les DEUX frères du même `AbilityEntities`
  (`On(0x39)`, `On(0x10)`) ne portent toujours pas `ability_type`. DÉLIBÉRÉ : aucun de leurs
  consommateurs portés ne lit `ev.ability_type` (mesuré : 0 occurrence dans `fleshmetal_guns.py`,
  `fire.py`, `geminae_superia.py`, `savior_protocols.py`), donc l'y poser serait un canal sans
  lecteur. `BLOCAGE: aucun`.

  ⚠ **RE-MESURÉ le 2026-08-17. Les deux prémisses TIENNENT — mais aucune n'était établie comme
  écrit ci-dessus, et l'une des deux est fausse en tant que fait.**

  * **Le natif.** « Ne construit qu'**UN SEUL** `AbilityEntities` (une seule invocation du ctor à
    33 paramètres) » est **FAUX** : `ApplyDamageOperation$$Execute` invoque le ctor **deux** fois.
    La seconde est le ctor de **COPIE** à 2 arguments — `AbilityEntities$$.ctor(entities,
    activeTarget)`, signature LUE dans `data/symbols/<build>/frida/methods.tsv` — et elle produit
    une **autre** structure, qui reçoit ensuite deux `Nullable<int>` de dégât. Ce qui est vrai, et
    qui suffit à la conclusion : **les trois publications passent la même variable** (`On(0x39)`,
    `On(0xf)` et `On(0x10)` reçoivent toutes `local_408`). La conclusion était juste ; son
    fondement, non.
  * **La reachabilité.** La mesure par **liste blanche** de quatre fichiers ne pouvait pas montrer
    ce qu'elle avait oublié : elle ne visitait ni `lifewards.py` ni `on_toxic_damage.py`, deux
    consommateurs réels. Re-dérivée des **registres** de `dispatch/registry.py` (305 classes de
    trigger recensées) : `On(0x39)` a **trois** consommateurs portés (`GeminaeSuperiaAbility`,
    `SaviorProtocolsAbility`, `LifewardsAbility`) et `On(0x10)` **trois**
    (`FleshmetalGunsTileEffectAbility`, `OnFireDamageAbility`, `OnToxicDamageAbility`). **Aucun des
    six ne lit `ev.ability_type`** ; les deux qui lisent un canal d'ability lisent
    `ev.triggering_effect` (`+0x98`). Le seul lecteur d'`ev.ability_type` de la famille est
    `ElectrochaffBackupsOnRangedDamageAbility`, sur `On(0xf)` — déjà câblé par `#1025-r2`.

  Le canal reste donc **sans lecteur**, donc non validable (patron #419) : `BLOCAGE: porteur`, et
  non `aucun`. À fermer quand un consommateur de `On(0x39)` ou `On(0x10)` lira un gate de kind.
