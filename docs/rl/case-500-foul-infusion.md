# #500 — `FoulInfusion` (1038) : le buff est posé AVANT l'attaque, et c'est la SÉQUENCE qui se mesure

`FoulInfusion` était un **no-op silencieux** : absente d'`ABILITY_CLASSES`, la décision la
choisissait et l'exécution l'ignorait — 0 effet, 0 dégât, aucune erreur. Porteur lineup :
`deathPutrifier` « Pestillian » (Death Guard, dans le pool rank 17) ; les trois autres porteurs
(`deathBossPutrifier`, `deathBossPutrifierLHE`, `deathNpcPutrifier`) sont npc.

Le port vit dans
[`engine/runner/abilities/loki/foul_infusion.py`](../../scripts/python/engine/runner/abilities/loki/foul_infusion.py).

## 1. Ce que fait le natif — `FoulInfusionAbility$$ExecuteBehaviour`

Mirror 1:1 (build `rnca9r7q6c`), slots `IdunBattleLogic.Entities.DSLSelectors` :
`+0x30 Owner`, `+0x48 Caster` :

```
range   = DSLFormulas.ContagionsOfNurgleRange( Owner@+0x30, unitSelectionType = 1, isNextTurn = 0 )
friends = DSLSelectors.SurroundingFriends( Caster@+0x48, range, unique = 1, unitSelectionType = 3 )
chaos   = DSLSelectors.UnitsWithTrait( friends, 0x7ea = 2026 Chaos, 3 )
targets = TargetsSelector.op_Addition( chaos, Caster@+0x48 )
buff    = DSLBehaviors.AddEffect( 0x432 = 1074 FoulInfusion_ExtraHits, GetAbilityStateReference(this),
                                  source = Caster@+0x48, targets, turns = TurnsFromRounds(2) )
foes    = DSLSelectors.Attackable( DSLSelectors.AdjacentEnemies(Caster@+0x48, 1, 3), 3 )
pick    = DSLSelectors.PickRandomly( foes, 1, allowDuplicates = 0, maxDuplicates = 0x7fffffff,
                                     ignoreForcedTargets = false )
atk     = DSLBehaviors.UseNormalAttack( Caster@+0x48, pick, ... )
AActiveAbility.Execute( this, AbilityBehaviour.op_Addition(buff, atk), entities )
```

Quatre lectures que le décompilé impose :

* **un seul `Execute`, aucun `ExecuteAtomic`** — l'`op_Addition` part directement dans
  `AActiveAbility$$Execute` (contraste `RevitalizingMalignancy`, qui emballe le sien) ⇒ `Seq` nu ;
* **le buff est posé AVANT l'attaque** — l'attaque libre du cast bénéficie *déjà* du coup
  additionnel `Toxic` que l'effet 1074 ajoute (`IsMeleeAttack & OwnerIsCaster`, et l'arme de
  `deathPutrifier` n'a pas de `Range` ⇒ melee) ;
* **le rayon vient de l'AURA, pas d'une constante d'ability** —
  `AuraEffectRangeFormula$$Calculate` exige `HasTrait(unit, 0x7eb ContagionsOfNurgle)` (que
  Pestillian porte au gameconfig) puis évalue `GetRangeOnOwnerTurn(StatAmount(Owner, 0xc
  TurnsStarted))` : **1** aux tours 1-2, **2** aux tours 3-4, **3** ensuite ;
* **le caster est ajouté par l'ARBRE, pas par le masque** — `SurroundingFriends` retire les tuiles
  du centre, donc l'`op_Addition(chaos, Caster)` final est le seul chemin par lequel Pestillian se
  buffe, et il le fait **sans passer par le filtre `UnitsWithTrait(Chaos)`**.

`Attackable(entities, selType)` = `UnitsWithoutTrait(entities, 0x1b Steppable, selType)` — le natif
n'alloue aucun sélecteur dédié, il compose textuellement.

Faces déjà portées avant cette tranche, inchangées : l'effet 1074
(`entities/effects/loki/hits.py::FoulInfusionExtraHitsEffect`) et le playbook
(`playbook/noncomparable/foul_infusion.py`).

## 2. Ciblage — `.ctor` et règle dynamique

`FoulInfusionAbility$$.ctor`, forme **flags directs** (surcharge A, 7 arguments) :

```
range = TargetingRange.CustomRange(<GetRange délégué>)
TargetingOptions..ctor(&opts, isSelfCasting = 1, &range, forceMeleeTarget = 1, rules = 0x482, null, null)
AActiveAbility..ctor(this, &opts, 2)          # 3e arg = 2 = AbilityAttackType.Others
```

`0x482 = 0x2 + 0x80 + 0x400`, exhaustif :
`TargetMatchesDynamicRule | AddCaster | TargetIsFriendly`. Le `range` est la surcharge **délégué**
⇒ `custom_range_func()`, aucun gate de distance dérivable.

⚠ `AbilityAttackType` = **`Others`**, relu au décompilé — l'ability *émet pourtant une attaque* et
sa catégorie d'audit est `DAMAGE(Toxic)` : deux raisons de croire à `DirectTargetAttack`. Le natif
écrit `2`.

`GetDynamicInvalidTargetReason` = `HasTrait(target, 0x7ea Chaos) ? 0 : 2` — corps inchangé dans
`targeting.py::_dynamic_rule_foul_infusion`, la classe le **surcharge** (même forme que #488).

**Contrat de disjonction payé aux quatre endroits, dans le même commit** : sortie de
`TARGETING_OPTIONS_UNPORTED` (+ recompte du bloc « surcharge A » : `14` → **12**, il était déjà
faux d'une unité depuis #488), sortie de `DYNAMIC_TARGET_RULE_UNPORTED`, retrait de
`SNAP_TARGETING_UNPORTED` + cardinalités (`40` → **39**, total `124` → **123**), retrait de
`POOL_ABILITIES_WITHOUT_COMBAT_CLASS` (et de la liste `attendues` du court-circuit friendly-only,
dont les deux propriétés restent asserties hors périmètre).

## 3. Ce que la mesure a tranché — `scale_from_source`

L'`AbilityStateReference` du `AddEffect` natif n'est pas décoratif :
`FoulInfusion_ExtraHitsEffect$$CreateAdditionalHits` lit son montant par
`ConfigVar(0xb = dmg, BaseEffect.GetAbilityState(effect), config)`. Sans `scale_from_source=True`,
l'effet matérialisé résout `dmg` contre son propre niveau de *stack* : le coup additionnel tombe à
**42** au lieu de **4188** (mesure ci-dessous). C'est un étage, pas un scalaire à caler.

Résidu nommé : le foyer partagé `_source_scaling` préfère `passive_ability_level` à
`active_ability_level`, alors que `GetAbilityState` d'une ability **active** rend le niveau actif ;
sur un BC normalisé les deux valent `targetAbilityLevel`, donc l'écart est nul ici.

## 4. Validation live — quatre étages, cinq contre-épreuves

Montage `probe_500_foul_infusion.py` (board `MC1_67`, seed 500, `--hp-target 400000`) — chaque
unité discrimine **une** lecture :

| unité | tuile | rôle |
|---|---|---|
| `deathPutrifier` | (5,5) | caster |
| `deathBlightlord` | (5,6) | allié Chaos **dist 1** → buffé |
| `deathRotbone` | (5,7) | allié Chaos **dist 2** → hors aura (rayon 1 au tour 1) |
| `ultraApothecary` | (6,5) | allié **non-Chaos** dist 1 → filtré par `UnitsWithTrait` |
| `necroWarden` | (4,5) | ennemi adjacent |
| `orksNob` | (5,4) | ennemi adjacent → pool de **deux**, le tirage discrimine |

Accord port / natif, sur la même capture (`dumpRng` calé) :

| étage | port | natif |
|---|---|---|
| E1 porteurs de 1074 | `{u77, u79}` | `{u77, u79}` |
| E2 cible frappée | `u85` | `u85` |
| E3 delta PV | `{85: 13847}` | `{85: 13847}` |
| `last['ported']` | `True` | — |

13847 = **9659** (arme) + **4188** (le coup additionnel du buff posé juste avant).

Cinq contre-épreuves hors-ligne, sur la même capture — **toutes discriminantes** :

| variante | porteurs | cible | total |
|---|---|---|---|
| REF (mirror) | `{77,79}` | 85 | **13847** = natif |
| AB1 sans `scale_from_source` | `{77,79}` | 85 | 9701 |
| AB2 **ordre inversé** (attaque puis buff) | `{77,79}` | 85 | 9659 |
| AB3 sans `UnitsWithTrait(Chaos)` | `{77,79,**83**}` | 85 | 13847 |
| AB4 rayon **constant 2** | `{77,79,**81**}` | 85 | 13847 |
| AB5 sans le tirage `PickRandomly` | `{77,79}` | **87** | 6782 |

⚠ **AB2 est celle qui compte** : le nombre de coups d'arme y est *identique*, seule la séquence
change. Un critère sur le compte de coups serait resté **vert**.

Garde committé : `tests/engine/runner/test_500_foul_infusion_live.py` (5 tests, `DECLENCHEUR` au
niveau module). Le premier test asserte que le montage est **discriminant** avant de juger le port.

## 5. Ce qui n'est PAS couvert

* `Attackable` = `UnitsWithoutTrait(0x1b Steppable)` — **aucune unité `Steppable`** dans le montage,
  donc le filtre n'est pas confronté (il ne retire rien ici). Résidu.
* `unitSelectionType = 3 OnlyAliveAndTargetable` — seul le volet ALIVE est porté ; le volet
  TARGETABLE (deep-strike en cours) n'est matérialisé nulle part côté port (résidu partagé par tous
  les sélecteurs d'occupation).
* Le **rayon d'aura 2 et 3** (`TurnsStarted > 2`, `> 4`) n'est pas confronté live : la mesure a été
  prise au tour 1 (rayon 1). La table elle-même est déjà gardée ailleurs
  (`contagions_of_nurgle_range_for_turns`, #224) ; ce qui reste non confronté ici, c'est le
  **couplage** rayon-d'aura → ensemble buffé à rayon > 1.
* `unique`, `parentAbility` / `triggerAbilityOrEffect` / `options` de `UseNormalAttack` : inertes,
  documentés au module.
