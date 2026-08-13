# #947 / #948 — deux passifs de kit de la famille `_ExtraDamageEffect`

`HeadClaimer` (`blackHaarken` « Haarken Worldclaimer ») et `EnmityForTheUnworthy`
(`darkaCompanion` « Forcas »). Les deux étaient le dernier item manquant de leur kit.

## 1. Recensement — par le bloc `methodPointers`, jamais par grep de nom

| famille | classe native | ce qu'elle DÉCLARE |
|---|---|---|
| #947 | `IdunBattle.Entities.Effects.Loki.HeadClaimer_ExtraDamageEffect` (`EffectType 0x404 = 1028`) | `CreateEffectDamageBonusForAttack` · `GetLocalizationDataInternal` |
| #947 | `IdunBattle.Entities.Effects.Loki.HeadClaimer_ExtraHitsEffect` (`0x405 = 1029`) | `.ctor` · `CreateEffectHitsBonusForAttack` · `GetHits` · `GetLocalizationDataInternal` |
| #947 | `IdunBattleLogic.Entities.Abilities.Active.Loki.HeadClaimerAbility` | `CreateBehaviour` · `CreateTrigger` |
| #947 | `IdunBattle.View.AbilityConfigs.Loki.HeadClaimerVisuals` | vue seule — aucune logique de combat |
| #948 | `IdunBattle.Entities.Effects.Loki.EnmityForTheUnworthy_ExtraDamageEffect` (`0x578 = 1400`) | `AdjacentFriendlyDarkaUnitsAmount` · `CurrentDamage` · `CreateActiveCondition` · `CreateEffectDamageBonusForAttack` · `GetLocalizationDataInternal` |
| #948 | `IdunBattle.Entities.Effects.Loki.EnmityForTheUnworthy_ExtraDamagePctEffect` (`0x577 = 1399`) | `.ctor` · `AdjacentUnitsAmount` · `CurrentDamagePct` · `CreateActiveCondition` · `CreateEffectDamageBonusForAttack` · `GetLocalizationDataInternal` |
| #948 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnmityForTheUnworthyAbility` | `CreateBehaviour` **seul** |

**Ce qui N'EXISTE PAS, et c'est un résultat** :

* `EnmityForTheUnworthyAbility` n'a **pas** de `CreateTrigger` propre → elle prend celui de sa base
  (`On(AbilityInit) & get_OwnerIsActor`), donc pose à l'INIT → `ABILITY_INIT_OWNER_EFFECTS`, jamais
  `ABILITY_TRIGGERS`.
* Aucune `CreateActiveCondition` chez `HeadClaimer` (flag capté souverain) ; les deux effets
  d'Enmity en ont une, portée (`active_condition_ported = True`).
* Aucune `CreateTargetSelector` nulle part → quatre SELF-effects, aucune aura.
* Les `.ctor` de `HeadClaimer_ExtraDamageEffect` et d'`EnmityForTheUnworthy_ExtraDamageEffect` sont
  **absents des tables** : IL2CPP les a DÉDUPLIQUÉS avec ceux de leurs jumeaux — corps
  byte-identiques, lus dans les OCTETS (`mov edx, 0x407` / `mov edx, 0x522`). Conséquence portée :
  les deux effets d'une famille indexent la **même** entrée gameconfig, celle du PASSIF.
* `HeadClaimer_ExtraDamageEffect` n'a pas de `GetCurrentBonus` propre : le corps qu'il appelle est
  celui que ghidra étiquette `TerrifyingCrescendo_ExtraDmgEffect$$GetCurrentBonus` (dédup ICF).

## 2. Les arbres (mirror 1:1)

```
HeadClaimer_ExtraDamageEffect$$CreateEffectDamageBonusForAttack
    ForAddition( get_OwnerIsCaster,
                 Multiply(ConfigVar(extraDmg = 8, GetAbilityState(this)), EffectLevel) )

HeadClaimer_ExtraHitsEffect$$GetHits
    Multiply( Get(GetNumberConstant(extraHit = 0x2b)), EffectLevel )
HeadClaimer_ExtraHitsEffect$$CreateEffectHitsBonusForAttack
    ForAddition( get_OwnerIsCaster, GetHits() )

HeadClaimerAbility$$CreateTrigger
    ( OnPreDeath2(overkill: true, steppable: false) | On(0x34 = UnitFled, ownerAlive: true) )
    & get_OwnerIsActor
    & NOT AreFriends(Owner@+0x30, Target@+0x60, 0, false)
    & NOT TriggeringAbilityIs(AbilityOrEffect(TriggeredAbilityType.ItsGonnaBlow = 1080))
HeadClaimerAbility$$CreateBehaviour
    op_BitwiseAnd( AddEffectOrIncreaseLevel(0x404, ..., amount = Const(1), max = NULL),
                   If( IsHero(Target@+0x60),
                       AddEffectOrIncreaseLevel(0x405, ..., amount = Const(1), max = NULL) ) )

EnmityForTheUnworthy_ExtraDamageEffect$$AdjacentFriendlyDarkaUnitsAmount
    Count( NonSteppableOrObjectUnits(
               UnitsFromFaction(AdjacentFriends(Owner@+0x30, unique: true, 3), DarkAngels, 3), 3) )
EnmityForTheUnworthy_ExtraDamagePctEffect$$AdjacentUnitsAmount
    Count( NonSteppableOrObjectUnits( AdjacentUnits(Owner@+0x30, unique: true, 3), 3) )
```

`OnPreDeath2(a, b)` = `OnDeathEvent(2, a, b)`, dont le corps a été relu : `a = true` **désarme** le
gate d'overkill (`<DSLTriggers+0x70> = Yes`) et `b = false` **arme**
`NOT HasTrait(Target, 0x1b = Steppable)`. Les deux littéraux sont décodés aux octets
(`mov dl, 1` / `xor r8d, r8d`), pas lus dans le pseudo-C.

### Surcharges tranchées par l'ADRESSE RÉELLE de la cible du `call` (`E8 rel32`)

Depuis `EnmityForTheUnworthy_ExtraDamageEffect$$AdjacentFriendlyDarkaUnitsAmount` :
`AdjacentFriends` = la variante `(this, unit, unique, selectionType)`, PAS `(this, unit, unitTile,
unique)` ; `UnitsFromFaction` = l'overload **ENUM**, pas celui à `factionId` string. Depuis
`HeadClaimerAbility$$CreateTrigger+0x130` : l'`AbilityOrEffect$$op_Implicit` visé est celui qui pose
`set_TriggeredAbility` — d'où `TriggeredAbilityType.ItsGonnaBlow`, et non l'`ActiveAbilityType` ni
l'`EffectType` d'ordinal 1080. Même id, même qualification que `BarbedOvipositorAbility`.

## 3. Les écarts que la recopie d'un jumeau aurait effacés

1. **`HeadClaimer_ExtraDmg` n'a AUCUN gate de nature de coup.** Il PARTAGE son corps de magnitude
   avec `TerrifyingCrescendo_ExtraDmg`, qui porte en plus un `IsRangedAttack`. Recopier le jumeau
   aurait tué le bonus sur toutes les attaques MÊLÉE de Haarken — dont son attaque normale.
2. **Aucun cap de niveau** : le `max` d'`AddEffectOrIncreaseLevel` est `NULL`, là où
   TerrifyingCrescendo passe `Direct(buffMaxLevel = 6)`. C'est le « for the rest of the battle ».
3. **Les DEUX effets d'Enmity comptent des populations DIFFÉRENTES** : `AdjacentFriends` +
   `UnitsFromFaction(DarkAngels)` pour la face additive, `AdjacentUnits` **nu** (amis ET ennemis,
   aucun filtre d'équipe) pour la face pourcentage.
4. **Canaux `EffectBonus` différents** : `+0x10` Addition contre `+0x08` PercentIncrease.
5. **Un seul des deux est rarity-scalé** : `variablesAffectedByRarityBonus == ["extraDmg"]` —
   `extraDmgPct` ne l'est pas. Ce fait ne se lit QUE dans le gameconfig.
6. **`NonSteppableOrObjectUnits` est PROPRE à Enmity** : le compteur voisin déjà porté
   (`adjacent_dark_angels_friends`, #932, Deathwing) s'arrête à `UnitsFromFaction`. Les deux arbres
   ne sont pas interchangeables — d'où deux clés de contexte distinctes
   (`adjacent_units_no_steppable`, `adjacent_dark_angels_friends_no_steppable`).

## 4. Validation

**Offline** — `tests/engine/test_947_948_extra_damage_passives_offline.py`, 29 tests dont **6
contre-épreuves par MUTATION** (chacune fait rougir un garde ; un garde vert sous mutation est
inerte). Elles couvrent : le gate `IsRangedAttack` recopié du jumeau, le canal pourcentage devenu
additif, la face additive branchée sur la mauvaise clé, `extraDmgPct` scalé à tort, `extraHit`
traité comme une variable, et le sélecteur d'Enmity privé de son étage `NonSteppableOrObjectUnits`.

**Live** — `probe_947_948_extra_damage_passives.py` + `tests/engine/runner/…_live.py`, board
`MC1_67` / seed `4321`, rejeu offline depuis capture avec le MÊME flux RNG :

| bras | régime | natif | port | écart |
|---|---|---|---|---|
| `enmity` | Forcas adjacent à SA SEULE cible (units=1, DA=0) | 3567 | 3567 | 0 |
| `enmity` | + 2 amis Dark Angels + 1 ami hors-DA (units=4, DA=2) | 8721 | 8721 | 0 |
| `headclaimer` | après 2 kills de HÉROS, 6 coups | 9924 | 9924 | 0 |

La géométrie est **calculée** (tuile la plus centrale à 6 voisins JOUABLES, dérivée du
`boardGraph`) puis **assertionnée** contre les positions réelles, jamais espérée ; le probe REFUSE
de conclure si les deux régimes rendent le même total natif. Les niveaux des deux stacks
(`1028 = 1029 = 1` après le premier kill, `= 2` après le second) coïncident des deux côtés.

**Les cinq mutants LIVE mordent** :

| mutant | effet mesuré |
|---|---|
| `en_da` | régime `entoure` : −3066 (la face ADDITIVE disparaît) |
| `en_units` | `solo` −496, `entoure` −3946 (la face POURCENTAGE disparaît) |
| `hc_effet` | −3588 sur 6 coups (l'additif `extraDmg × 2`) |
| `hc_hits` | **6 coups → 4** : preuve directe que le port applique bien `extraHit × level = +2` |
| `hc_trigger` | niveaux port `None` : l'accumulation ne se fait plus |

## 5. Résidus

* **#947-r1 — la branche `On(UnitFled)` est portée mais INERTE** : aucun vecteur de fuite n'existe
  côté port. Sous-compte possible, jamais de sur-compte.
* **#948-r1 — les deux compteurs d'Enmity sont évalués à la position COURANTE en PRÉDICTION**, pas à
  la tuile candidate (même contraste assumé que `adjacent_taunted_enemies` #911 et
  `adjacent_dark_angels_friends` #932).
* **`NOT TriggeringAbilityIs(ItsGonnaBlow)` : gate INERTE**, même constat que
  `loki/barbed_ovipositor.py` — aucun poseur d'`ItsGonnaBlow` n'est porté et le canal n'est pas
  threadé sur `On(2)`.
* **Le CAS NÉGATIF du `If(IsHero(Target))` n'est pas confronté live**, et la raison est MESURÉE :
  toutes les unités `lineup` plaçables portent `Hero`, que le natif REPOSE indépendamment de
  `BC.Units[].Traits` (`--unit-stat "<vis>:Traits=[]"` laisse `combatSnapshot.traits == [16]`), et
  les MoW — seules unités confrontables sans `Hero` (`traits == [1006, 1049]`) — ne sont pas posées
  sur le plateau, donc inattaquables en mêlée. Même population que #942-r1. Le cas est gardé
  OFFLINE, en exécutant le nœud contre un `AbilityEntities` fabriqué.

## 6. Observation HORS PÉRIMÈTRE — #949 — **RÉSOLUE, et l'écart était dans le LECTEUR**

> ⚠ Cette section annonçait : « le ledger natif porte **8 coups** —
> `[1779, 1539, 1713, 1688, 1520, 1885, 1704, 66723]` — là où le rejeu offline en rend **6** pour
> 10 124 pts […] un coup SUPPLÉMENTAIRE que le port ne matérialise pas ». **Les trois affirmations
> sont fausses**, et la re-mesure (#949) les défait une par une. Le texte d'origine est conservé
> ci-dessus en citation parce qu'il est la prémisse du résidu — pas parce qu'il tient.

Re-mesuré par `scripts/python/probe_949_ltgb_coup_manquant.py` (board `MC1_67` / seed 4321, même
montage, `blackHaarken` avec ses traits NATIFS) :

1. **Le `66723` n'est pas un coup.** Son tag natif porte `Effect_Type = 1476` = `DespoiledGround`
   — le DoT de tuile que `LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` pose à la clôture de
   l'attaque, dont la non-portée est un résidu **déjà nommé** dans
   `engine/runner/operations/triggers/loki/let_the_galaxy_burn.py`. Le ledger de COUPS natif en
   compte donc **7**, pas 8. L'ancienne mesure additionnait deux populations d'events : les coups
   de l'attaque et un canal qui lui est étranger.
2. **Le port matérialise bien le 7ᵉ coup**, et le gate se comporte comme le décompilé le dit.
   Trace par étage : le trigger de pose `matches` rend `true`, le `Maybe(33 %)` rend `true`, et
   `LetTheGalaxyBurnEffect.additional_hit_groups` rend `{count: 1, min: 1106, max: 1106,
   profile: null}` — que `execute_additional_hits` exécute pour **1704**, la valeur native EXACTE.
3. **Le « 6 coups » venait du lecteur.** `damage_ops/normal.py::execute` publie la phase d'arme
   dans `per_hit` et le canal #179 **à côté**, dans `additional_hits` (deux sous-opérations natives
   distinctes). Le `_replay` de `probe_947_948` ne lisait que le premier. Arbitre décisif :
   `hp_delta = 11828` = la somme EXACTE des 7 coups natifs. Le bras `Traits=[]` restait bit-exact
   simplement parce que, sans `LetTheGalaxyBurn`, aucun groupe #179 n'existe.

**Lequel des deux disjoints du gate tenait** (la question ouverte du résidu) : `IsPersistentData`.
La tuile de la cible ne portait **aucun** status-effect (`TargetHasTileEffect` FAUX, lu live) ;
c'est le `Maybe(LetTheGalaxyBurnChancePct = 33)` du trigger de pose qui avait armé le flag.

Ce qui restait, **et qui était un vrai bug** : un écart de **1 point** sur ce coup, réparé par
#949 dans `apply_pierce_and_modifiers` (les quatre appels de modificateurs sont désormais groupés
PAR FACE). Détail : `docs/rl/case-949-ltgb-coup-manquant.md`.

## #948-r1 — FERMÉ : le natif DÉPLACE réellement l'unité, et ce n'est pas `RefreshSimulatedEffects`

**L'énoncé était juste, sa citation ne l'était pas.** Le résidu attribuait la ré-évaluation par
tuile à `IdunBattle.Operations.SimulateEffectsOperation$$RefreshSimulatedEffects`. Relu verbatim
sur `rnca9r7q6c`, ce corps-là ne fait que re-poser les effets entité par entité — il ne
repositionne rien. Le déplacement est **dans son appelant**,
`IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` :

```
if (!UnitExtensions.IsDead(unit, state)) {
    originalTiles = EntityExtensions.GetTiles(unit, state)      // sauvegarde
    flags.Add(1) ; SetMovedFlag(unit, state)
    processor->slot(+0x65)(processor, unit, tile, &out)         // L'UNITE EST POSEE SUR `tile`
    added = SimulateMoveUnitTriggers(this, unit, node, tile)
    RefreshSimulatedEffects(this)                               // les effets sont re-poses
    action.Invoke(...)                                          // LA PREDICTION S'EXECUTE ICI
    ResetAddedEffects(this, added) ; <restauration complete>
}
```

L'entité est donc **physiquement** sur la tuile candidate pendant l'action, et `AdjacentUnits(Owner)`
descend sur `EntityExtensions$$IterateTiles(owner)` : il lit la tuile **candidate**. La distinction
compte — citer `RefreshSimulatedEffects` aurait fait chercher la ré-évaluation dans l'étage des
effets, où elle n'est pas.

**Fix** : `playbook/adjacency.py::subject_tiles_at` substitue les pieds du sujet ;
`Scene._enmity_adjacent` accepte `at_pos` ; **les deux** vecteurs de prédiction (attaque normale et
ability) le threadent — n'en câbler qu'un déplacerait le fork au lieu de le supprimer.

**Garde** — `tests/engine/test_948r1_tuile_candidate_offline.py`, 5 étages, deux géométries
(contact **rompu** par le déplacement, contact **créé**), témoin non nul exigé sur chacune. Vue
ROUGE par deux mutations :

| mutation | rouge |
|---|---|
| C — le compteur ignore `at_pos` | `A : le compteur ne bouge PAS (courant=2 candidat=2)` |
| D — le vecteur NORMALE ne threade plus | `enmity_adjacent_units(att_id) ne threade pas la tuile candidate` |

**Non-régression** : 107 tests offline (faces jumelles d'adjacence #943-r7, adjacence câblée
#943-r4, Deathwing #932, foyer d'adjacence #433-r4-r2, élévation #515, deux formes de pieds
#419-r1-tr10-r2, et les passifs #947/#948 eux-mêmes).

**Ce qui n'est PAS couvert** : `#948-r3` (un porteur MULTI-TUILES garde ses pieds réels) et les
**deux voisins de forme**, `Scene.adjacent_taunted_enemies` (#911) et
`Scene.adjacent_dark_angels_friends` (#932), qui relèvent du même gisement et restent à la position
courante. La lecture ci-dessus vaut pour eux — leur câblage est mécaniquement identique — mais ils
ont leur propre porteur à confronter, donc leur propre tranche.
