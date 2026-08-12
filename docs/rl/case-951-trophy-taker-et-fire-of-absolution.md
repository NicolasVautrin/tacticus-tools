# #951 — `TrophyTaker` (port NEUF) et `FireOfAbsolution` (audit d'un port EXISTANT)

Deux passifs, `worldExecutions` « Tarvakh » et `adeptRetributor` « Vindicta », donnés comme « le
dernier item manquant de leur kit ». **Un seul des deux l'était.**

## 1. Recensement — par le bloc `methodPointers`, et le compte de CORPS PROPRES

| classe native | base (lue dans `frida/classes.tsv`) | corps PROPRES déclarés |
|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TrophyTakerAbility` | `IdunBattle.Entities.Abilities.BaseTriggeredAbility` | `CreateTrigger` · `CreateBehaviour` · `GetCritChanceMultiplier` · `GetLocalizationData` — **4/4** |
| `IdunBattle.Entities.Effects.Loki.TrophyTaker_ExtraCritDamageEffect` | `IdunBattle.Entities.Effects.BaseEffect` | `.ctor` · `HealthLowerThanPct` · `CreateCritDamageBonus` · `CreateEffectDamageBonusForAttack` — **4/4** |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility` | **`IdunBattle.Entities.Abilities.BaseTriggeredAbility`** | `CreateTrigger` · `CreateBehaviour` · `u003CCreateBehaviouru003Eb__3_0` — **3/3** |

**Proportion de corps propres : 11/11 (100 %) sur les trois classes de logique.** Aucune
déduplication ICF dans ce lot — contrairement à #947/#948, où les deux `.ctor` étaient absents des
tables. Le seul mislabel rencontré est ailleurs, et il est instructif : `CenterSpace.Free.
MersenneTwister$$get_Count`, appelé par `FireOfAbsolutionAbility$$CreateBehaviour`, est un
`mov eax,[rcx+0x10] ; ret` — le getter d'`AbilityType` de l'ability elle-même, pas un compteur.

⚠ **La BASE de `FireOfAbsolutionAbility` est `BaseTriggeredAbility` malgré son namespace `Active`.**
Le namespace n'est pas la hiérarchie ; `classes.tsv` l'est.

**Ce qui N'EXISTE PAS, et c'est un résultat** : aucune `CreateActiveCondition`, aucune
`CreateTargetSelector`, aucun `ApplyInternal`/`RevertInternal` dans tout le lot. Les deux passifs
sont donc SELF, sans condition d'activation — d'où, pour `TrophyTaker`, l'absence d'entrée
`ABILITY_INIT_OWNER_EFFECTS` (§4).

## 2. Les arbres (mirror 1:1, surcharges tranchées à l'ENCODAGE)

```
TrophyTakerAbility$$CreateTrigger
    <DSLTriggers+0x30>                                   # = On(AbilityInit) & <+0x70> & OwnerIsActor
    | ( On(EventTriggerType.UnitDefeated = 0x36, ownerNeedsToBeAlive: true) & get_OwnerIsActor )

TrophyTakerAbility$$GetCritChanceMultiplier
    Count( NormalUnits( UnitsDefeatedBy(Owner@+0x30), UnitSelectionType.Any = 0 ) )

TrophyTakerAbility$$CreateBehaviour(abilityState, triggerType)
    triggerType == UnitDefeated
      -> AddOrUpdateStaticStatModifierEffect(Owner@+0x30, EffectType.TrophyTaker_ExtraCritChance
             = 0x508, StatType.CriticalChance = 9,
             Multiply(ConfigVar(extraCritChance = 0x41, abilityState, config),
                      GetCritChanceMultiplier()),
             turns: null, isHidden: false)
    sinon
      -> AddEffect(EffectType.TrophyTaker_ExtraCritDamage = 0x509, AbilityStateReference,
                   targets: Owner@+0x30, turns: Nullable<int> VIDE)

TrophyTaker_ExtraCritDamageEffect$$.ctor
    BaseEffect..ctor(AbilityOrEffect(TriggeredAbilityType.TrophyTaker = 0x4cd),
                     hasAutomaticActivation: true)
TrophyTaker_ExtraCritDamageEffect$$HealthLowerThanPct
    NOT AmountIsEqualOrGreater(
            StatAmount(Target@+0x60, Health = 5, StatPart.CurrentPct = 1, null, Any),
            Direct(GetNumberConstant(hpPct = 0x12)) )
TrophyTaker_ExtraCritDamageEffect$$CreateEffectDamageBonusForAttack
    ForAddition(get_OwnerIsCaster & HealthLowerThanPct(), ConfigVar(extraDmg = 0x8, ...))
TrophyTaker_ExtraCritDamageEffect$$CreateCritDamageBonus
    ForAddition(get_OwnerIsCaster & HealthLowerThanPct(), ConfigVar(extraCritDmg = 0x42, ...))

FireOfAbsolutionAbility$$CreateTrigger
    On(EventTriggerType.AttackInAtomicGroup = 0x4a, ownerNeedsToBeAlive: true)
    & get_OwnerIsActor & IsRangedAttack()                 # surcharge à 0 ARGUMENT
FireOfAbsolutionAbility$$CreateBehaviour
    ( Inform(TagKey.Target_Id = 0xb3, EntityId(Target@+0x60))
      & AttackWithAttackDamage(Caster@+0x48,
            (AdjacentUnits(Target@+0x60, unique: false, OnlyAliveAndTargetable = 3)
             - Caster@+0x48) - Target@+0x60,
            Direct(GetVariableForLevel(dmg = 0xb, ., fallbackToDefault: false)),
            GetDamageProfile(), hits: GetNumberConstant(nrOfHits = 0x2f),
            AbilityOrEffect(this.AbilityType), options: VIDE, OnlyTargetable = 2) )
    & Maybe(behaviourFactory: b__3_0, entities: AdjacentTiles(Target@+0x60),
            probability: GetNumberConstant(chance = 0x2a))
FireOfAbsolutionAbility$$<CreateBehaviour>b__3_0(tile)
    AddEffect(EffectType.Fire = 5, AbilityStateReference, targets: tile, turns: VIDE)
```

### Ce que la lecture des OCTETS a tranché, et que le pseudo-C ne disait pas

1. **`AmountIsEqualOrGreater`, pas `AmountIsGreater`** — deux classes distinctes. Le gate est
   `pct < hpPct` **STRICT** : une cible à EXACTEMENT 50 % ne donne rien.
2. **La surcharge d'`AmountIsEqualOrGreater` est `(amount, minAmount)`**, pas `(selector, …)`.
3. **`StatPart.CurrentPct` (1)** n'est PAS traité par `StatComponent$$GetStatPart` (pas de `case 1`
   — il lèverait `ArgumentOutOfRangeException`). Sa formule vit dans
   `FillUpStatComponent$$GetStatPart` case 1 :
   `Fix64.Round(Max(0, current / CurrentMaximumValue) * 100, mode 0)` — arrondi demi-vers-le-PAIR,
   pas une troncature.
4. **`ConfigVar` a DEUX surcharges dans le même passif** : `abilityState: AbilityState` (struct) sur
   la face STAT-MOD, `abilityState: IAbilityStateSelector` sur les deux `EffectBonus`.
5. **`turns = null` et `isHidden = false`** : `xor ebx,ebx` puis `[rsp+0x28] = rbx` / `[rsp+0x30] = bl`.
   Le stat-mod est PERMANENT et VISIBLE.
6. **`Maybe(behaviourFactory, entities, probability)` fait UN TIRAGE PAR ENTITÉ** —
   `MaybeBehaviour$$Execute` boucle sur `entities.Select(...)` et appelle `random.slot5(prob)` DANS
   la boucle ; la variante à behaviour simple, elle, ne tire qu'une fois. Le port
   (`Foreach(AdjacentTiles, Maybe(chance, SetOnFire))`) était donc déjà fidèle.
7. **`UnitsDefeatedBy` prend l'UNION** de `ActorStatisticsComponent` `+0xa8` (mêlée) et `+0xb0`
   (le reste) — `UnitsDefeatedBySelector$$Select` appelle `AddUnits` sur les DEUX.
8. **`RegisterDefeatedUnit` est appelé à `KillUnitOperation$$Execute+0x8b9`, sous DEUX gates**
   (`IsActor(killer)`, `!IsSteppable(killed)`), donc **AVANT** `On(UnitDefeated)` @+0xeac. Le
   consommateur compte la victime COURANTE : `n+1`, jamais `n`.

## 3. L'ÉTAGE NATIF QUI MANQUAIT — et il manquait dans DEUX foyers

`UnitsDefeatedBy` n'était porté nulle part (deux approximations impératives existaient côté
décision et côté combat, aucune n'était le nœud). Trois pièces ajoutées :

* `UnitComponent.defeated_units` — mirror des deux listes natives, **fusionnées**, avec la mesure
  qui l'autorise : le seul lecteur porté prend l'union. Résidu **#951-r1** pour la scission.
* `components.register_defeated_unit(state, killer, killed)` — appelée depuis `damage.py` à
  l'emplacement natif exact, gates compris.
* `selectors.units.UnitsDefeatedBy` — nœud DSL.

⚠ **Et un QUATRIÈME étage, trouvé par la confrontation, dans un foyer PARTAGÉ.**
`Count(NormalUnits(UnitsDefeatedBy(Owner), Any))` rendait **0** là où le natif rend **1** : le
`Units` du port re-résolvait toute entrée par l'occupation de tuile, laquelle ne garde que les
VIVANTS — or les unités vaincues sont mortes par construction. Le natif, lui,
**court-circuite** (`TargetsSelector$$SelectUnit` : la ré-résolution est sous
`if (IsUnitFoot(entity) || IsTile(entity))`). L'écart était **écrit dans la docstring de `Units`**
depuis longtemps (« le filtre VIVANT y reste applique ») et n'avait jamais été rencontré : il
fallait une source qui rende des morts. Corrigé, avec un rayon de souffle borné par le
`selection_type` — les call-sites en `OnlyAlive`/`OnlyAliveAndTargetable` (l'écrasante majorité)
ré-excluent le mort deux lignes plus bas et ne changent pas.

## 4. `FireOfAbsolution` — l'audit, et un FAUX MANQUANT

Il **était déjà porté**, par un vecteur impératif branché sur `On(AttackInAtomicGroup)`
(`dispatch/ability.py::evaluate_abilities_for_event` + `dispatch/attack.py`). L'audit
`kit-coverage.md` le compte manquant parce qu'il lit les **REGISTRES**, et que ce passif n'y a pas
d'entrée. **Résidu #951-r2.** Trois écarts réels trouvés et corrigés :

1. **`chance` était HARDCODÉE** (`FIRE_OF_ABSOLUTION_IGNITE_CHANCE = 30`) là où le natif lit
   `GetNumberConstant(AbilityConstantType.chance)`. Valeur juste aujourd'hui, canal faux :
   un rebalancage du gameconfig serait passé inaperçu. Les deux autres grandeurs du même
   `CreateBehaviour` étaient déjà lues de la config — c'était la seule des trois.
2. **Le `selectionType = 3` d'`AdjacentUnits` était AVALÉ**, compensé par un wrapper `Alive(...)` :
   le volet ALIVE était porté, le volet **TARGETABLE** non. Une unité adjacente en deep-strike
   (`UnitFlag.Untargetable`) était touchée par le port et pas par le natif.
3. **La docstring affirmait « pas de `CreateTrigger` distinct dumpé pour ce passif ».** C'est FAUX :
   `FireOfAbsolutionAbility$$CreateTrigger` a un corps PROPRE. Une prose fausse survit à tous les
   tests fonctionnels — d'où un garde qui exige que le module CITE le symbole.

## 5. Validation

**Offline** — `tests/engine/test_951_trophy_taker_offline.py`, **25 tests** dont **6
contre-épreuves par MUTATION**, chacune vérifiée mordante : gate non strict, troncature au lieu du
demi-vers-le-pair, union réduite de moitié, `NormalUnits` absent du compteur, `get_OwnerIsCaster`
exigé des deux canaux, chance re-figée, `selectionType` ré-avalé.

**Live** — `tests/engine/runner/test_951_trophy_taker_live.py` (7 tests), board `MC1_67`, seed
`4321`, replay-diff RNG-seedé :

| régime | natif | port | écart |
|---|---|---|---|
| gate FERMÉ (cible 90 % PV), 0 victime | 4248 | 4248 | **0** |
| gate OUVERT (cible 40 % PV), 0 victime | 5445 | 5445 | **0** |
| différentiel = `ConfigVar(extraDmg)` | +1197 | +1197 | **0** |
| stat-mod 1288 après 1 victime | `StatType 9, Amount 16, IsDynamic 0, IsHidden 0, remaining 0` | idem | **0** |

`Amount = 16` est exactement `extraCritChance[niveau 50]` **non** multiplié par la rareté (180 %) —
l'asymétrie `variablesAffectedByRarityBonus == ["extraDmg", "extraCritDmg"]`, gardée.

⚠ **Le régime TÉMOIN est ce qui rend le reste interprétable.** Sans lui, l'écart mesuré avec un
kill préalable (682 à 881 points) se serait lu comme un écart de `TrophyTaker`. Il ne l'est pas :
il vient de `BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee`, un AUTRE
passif du MÊME porteur, qui indexe sa magnitude sur le compteur de victimes — que la capture ne
publie pas. Sans kill préalable, l'écart est **0**. Résidu **#951-r3**.

## 6. Résidus

* **#951-r1** — `defeated_units` fusionne les deux listes natives ; scission requise le jour où
  `DSLSelectors$$UnitsDefeatedByMeleeAttack` entre au port.
* **#951-r2** — `kit-coverage.md` compte `FireOfAbsolution` MANQUANT alors qu'il est porté : l'audit
  lit les registres, ce passif passe par un vecteur impératif.
* **#951-r3** — le compteur d'unités vaincues n'est pas publié par la capture : après un
  rechargement, un nouveau kill recompte à partir de zéro. Écart mesuré 682–881 sur
  `BlessingsOfKhorne`, PRÉEXISTANT à cette tranche.
* **#951-r4** — le `ownerNeedsToBeAlive: true` du `CreateTrigger` de `FireOfAbsolution` n'est pas
  porté (le vecteur impératif ne le modélise pas). Inobservable sur ce vecteur — l'attaquant est
  vivant par construction d'une attaque qu'il vient de porter.

## 7. Ce qui n'est PAS couvert, avec la raison MESURÉE

* **Le cas `pct` EXACTEMENT au seuil, en live.** Il est gardé OFFLINE (le gate strict), pas live :
  le forcer demanderait `RemainingHealth = Health/2` **et** qu'aucun dégât n'ait entamé la cible
  entre le seed et la mesure — or le pilotage traverse plusieurs tours et `necroWarden` régénère.
* **Les deux rouges rencontrés en cours de route sont PRÉEXISTANTS**, mesurés sur un worktree
  détaché à `origin/master` (`bbeadd28`) : `test_419_r1_fire_of_absolution_pair_term_live` (« le
  port ne produit AUCUNE action depuis (4, 4) sur 77 ») et `test_runner_attack_live`
  (`AttributeError` à `playbook/scene.py:735`). Aucun des deux n'est touché par cette tranche.
