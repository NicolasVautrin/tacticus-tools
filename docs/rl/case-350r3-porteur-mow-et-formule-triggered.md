# case-350-r3 — le porteur MoW (b) et le porteur de la formule de `1160` (c)

Deux verrous sans rapport, laissés ouverts par `#350` §5. Tranchés séparément.

---

## (b) `--p-units` refuse une MoW — garde EXPLICITE, chemin DÉJÀ câblé

`rl_duel.cmd_build::pick()` teste `u not in pool`, et `pool` est le **complémentaire** de `pool_mow`
(`_normalize_and_extract_pool` : `pool_regular = normalized - mow`). Les deux pools sont disjoints
**par construction** : toute MoW est refusée par `--p-units`, et c'est voulu — `--p-mow` / `--a-mow`
la poussent par `BC.PredefinedMachines` (`_patch_predefined_machines`), voie déjà validée.

Mesuré (rank 17, `MC1_67`) : `blackForgefiend` ∈ `pool_mow` (8 MoW), ∉ pool régulier (97 unités),
entrée `BC.Units` présente (donc `--unit-stat` a prise), board MoW-capable. **Rien à assouplir.**

### Le mur RESTANT n'est pas le déploiement

La MoW se déploie, `aiPlaybookPredict` résout ses playbooks (`HadesAutocannonsPlaybook`,
`DaemonicOrdnancePlaybook`) et `--unit-stat blackForgefiend:ActiveAbilityLevel=4` **pilote** le
niveau (`abilityState.level = 4`, `source: capteur`). Et pourtant, avec la MoW **comme caster** :

| mesure | résultat |
|---|---|
| `aiPlaybookPredict(1147)` sans summon en jeu | `count = 0`, `listNull = false` |
| idem avec un summon en jeu | **`count = -1`, `listNull = true`** — le natif rend `null` |
| `engine.ai.context.build(…, casterId de la MoW)` | **`ctx.me is None`** |

Une MoW est off-board : le harnais lui substitue la `UnitPosition` de la **cible**
(`rpc-predict.ts`, RE #172), et elle n'est pas dans `decisionView.units`, d'où l'absence de contexte
côté port. La confrontation d'arrondi passe donc par la **greffe** (`case-92` §5bis) : le natif
charge le playbook **par ability**, et la formule de 1147 ne lit ni stat ni trait du caster.

### `1147 HadesAutocannons` — CONFRONTÉE

Son sélecteur `HadesAutocannonsAbility$$GetAllTargets` ne retient que des **summons du camp de la
cible** (i2 : « a targeted enemy summon and all other enemy summons within 2 hexes »). Sans summon,
le natif rend 0 event **quel que soit le caster** — mesuré 16 fois (8 cibles × 2 abilities ×
{MoW, unité greffée}, ring serré compris). Le montage en pose : `deathBlightbringer` (pool)
auto-cast `1040 SpawnPoxwalkers` → deux `deathPoxwalker`.

Gabarit #344 par ailleurs inchangé, `1147` greffée sur `necroWarden` :

| bras | niveau | (minDmg, maxDmg) | somme | natif | `to_even` | `trunc` | `half_up`/`ceil` |
|---|---|---|---|---|---|---|---|
| A (`3 mod 4`) | 4 | (58, 77) | 135 | **(324, 492, 6)** | = natif | (324, **480**, 6) | = natif |
| B (`1 mod 4`) | 2 | (43, 58) | 101 | **(240, 360, 6)** | = natif | = natif | (**246**, **366**, 6) |

`to_even` est la **seule** variante nulle sur les deux bras, et le code **livré** égale le natif sur
les deux — exactement ce que prévoit son inscription en **(a2)**
(`StaffOfStarsAbility$$GetDamage`, `isPrediction = 1`).

### `1148 DaemonicOrdnance` — CONFRONTÉE, et un **bug de port** trouvé au passage

`DaemonicOrdnancePlaybook$$MakeDamagePredictions` ne boucle pas sur `<Target>` mais sur
`GetEntitiesFromSelector(DaemonicOrdnanceAbility$$GetAllDamageableTargets, …)` =

    Enemies( caster@0x160,
             Units( Filter( GetTargetAreaTiles(), HasEffect(Tiles(Subject@0x180), 5 = Fire) ), 1 ),
             3 )

soit **les ennemis debout sur une tuile qui porte DÉJÀ le feu** — que ce même cast pose en dernier
étage de son behaviour. Le port n'avait pas ce sélecteur et émettait un event générique par cible :

| régime | natif | port AVANT | port APRÈS |
|---|---|---|---|
| zone froide (board frais) | ∅ (0 event) | **(81, 123, 3)** | ∅ |
| zone en feu (après un premier cast) | (3, 3, 3) | — | **(3, 3, 3)** |

Sur-prédiction **muette** — ni erreur ni crash — qui gonflait l'utilité de 1148 dans toute décision
portée. Fermée par `_MAKE_DMG_TARGET_GATE` (`engine/playbook/prediction/abilities.py`), registre
distinct de `_MAKE_DMG_INPUT_OVERRIDES` : celui-ci ne change que les **entrées** d'un event déjà
acquis, celui-là décide s'il **existe**.

`tile_effects_by_pos = None` (chemins sans `tileMeta`) est traité comme « feu inconnu » → aucun
event, c.-à-d. le régime du natif sur tout board frais. Faux négatif possible et **borné** si une
zone brûle réellement sans que la carte d'effets soit chargée ; l'ancien comportement, lui, était
faux sur **tout** board.

---

## (c) `1160 HeavyRailRifle` — l'objet évalué est la TriggeredAbility `1260`

`HeavyRailRiflePlaybook$$EvaluateNonComparable` appelle

    Playbook<T>$$GetAbility<T>(this, 0x4ec, &slot, …)          // 0x4ec = 1260

puis, **sur cet objet** : `BaseTriggeredAbility$$GetDamageProfileOrDefault(., 0x12)`,
`VisionsOfHeresy_AttackAbility$$GetAttackHits` (= `ConfigConst(0x2f = nrOfHits)`) et
`MassiveScythingTalonsAbility$$GetDamage` → `BaseTriggeredAbility$$MinMaxDamage` =
`RandomAmount( cfg@0x20[0xc = minDmg], cfg@0x20[0xd = maxDmg] )`, pris au **slot 4** de
`IAmountFormula` (= `AAmountFormula$$CalculateAverage`, troncature) → **forme (b)**.

`0x4ec` est la même valeur que rend `HeavyRailRifle_PendingAttackEffect$$GetTriggeredAbilityType`,
et le port la nomme déjà : `TriggeredAbilityType.HeavyRailRifle_Attack = 1260`.

L'ability **active** 1160, elle, ne fait que poser deux effets —
`HeavyRailRifleAbility$$ExecuteBehaviour` = `AddEffect(0x536 = 1334 PendingTarget) &
AddEffect(0x535 = 1333 PendingAttack)`. **Aucun dégât.** `engine/runner/abilities/tau.py` le disait
déjà : la phase 2 est hors de ce port.

**Verdict : l'inscription ne manque pas — l'y poser serait faux sur deux axes** (mauvais enum,
`ActiveAbilityType` au lieu de `TriggeredAbilityType` ; mauvais objet, une `BaseTriggeredAbility`
dont la config est à `+0x20` et non `+0x60`). Les registres `_PREDICTION_MINMAX_*` ne sont lus que
par `AActiveAbility.get_damage`, chemin que cet objet n'emprunte pas. Le fait est conservé dans
`_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY` (table **documentaire**, disjonction gardée).

Rien à poser côté `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE` : `ABILITY_CLASSES` est inchangé
(1160 y était déjà, avec ses deux données).

### Gisement ouvert par cette lecture (non porté, nommé)

La couche **TRIGGERED** a ses propres deux formes, symétriques de celles de #350 sur la couche
ACTIVE, et leurs xrefs sont énumérables :

| corps | forme | playbooks appelants |
|---|---|---|
| `MassiveScythingTalonsAbility$$GetDamage` → `BaseTriggeredAbility$$MinMaxDamage` | (b) troncature | `HeavyRailRiflePlaybook$$EvaluateNonComparable`, `FuryOfTheAncientsPlaybook$$GetDamagePrediction` |
| `MassiveScythingTalonsAbility$$GetAverageDamage` → `BaseTriggeredAbility$$MinMaxDamageAverage` | (a) demi-vers-le-pair | `LightImUpPlaybook$$CalculateAttackUtilityForMainTarget` / `…ForSecondaryTarget` / `…InStepsInternal>d__2$$MoveNext`, `MassiveScythingTalonsPlaybook…InStepsInternal>d__2$$MoveNext` |

Ces quatre-là alimentent des **utilités** (`CalculateAttackUtility…`), pas des
`ProbableDamageEvent` : leur confrontation demande un oracle d'utilité, pas `aiPlaybookPredict`.
Hors périmètre `#350-r3`.

---

## Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `tests/engine/test_350_prediction_average_forms_offline.py` — **F** | 1160 dans **aucun** des trois registres, `1260 = 0x4ec = TriggeredAbilityType.HeavyRailRifle_Attack`, et la table documentaire disjointe des registres |
| idem — **G** | le gate de sélecteur de 1148 sur scène synthétique : ami refusé, tuile froide refusée, tuile en feu acceptée, `tileMeta` absent = feu **inconnu** (pas supposé) |
| `tests/engine/test_350r3_mow_carrier_live.py` (4) | pools disjoints + chemin MoW câblé ; le mur restant est l'oracle/le port, **pas** le déploiement ; 1147 `to_even` seule nulle sur deux bras ; 1148 en accord dans les **deux** régimes de feu |
| `probe_350r3_mow_caster.py` | le montage (`--only-scan`, `--step 1|2|3`) |

**Mutation jouée, rouge** : retirer `1148` de `_MAKE_DMG_TARGET_GATE` → la garde live rougit sur le
régime froid avec `(81, 123, 3)` contre `∅`.

## Ce qui n'est PAS couvert

- **1147/1148 avec la MoW pour caster** : le montage GREFFE remplace le porteur, donc l'étage AVAL
  (profil d'arme, perçage) est celui du greffon. L'arrondi de la **base**, lui, est bien celui de
  1147 — le bras A discrimine (492 contre 480). La voie directe reste fermée par les deux mesures du
  tableau ci-dessus ; la rouvrir demande soit que `rpc-predict.ts` sache calculer une
  `UnitPosition` pour une MoW, soit que `ai/context.py` construise un contexte pour une entité
  `Machine`.
- **Le volet AoE de 1147** : le natif émet un event par summon retenu (2 sur le bras A), le port un
  seul. Le gabarit #344 isole la cible principale ; ce compte est affiché, pas gardé.
- **La couche TRIGGERED** (tableau ci-dessus) : lue, non portée, non confrontée.
