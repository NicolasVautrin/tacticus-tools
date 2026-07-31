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

### Le mur RESTANT n'est pas le déploiement — ⚠ ni le jeu (tranché par #360)

La MoW se déploie, `aiPlaybookPredict` résout ses playbooks (`HadesAutocannonsPlaybook`,
`DaemonicOrdnancePlaybook`) et `--unit-stat blackForgefiend:ActiveAbilityLevel=4` **pilote** le
niveau (`abilityState.level = 4`, `source: capteur`). Et pourtant, avec la MoW **comme caster** :

| mesure | résultat | verdict #360 |
|---|---|---|
| `aiPlaybookPredict(1147)` sans summon en jeu | `count = 0`, `listNull = false` | régime du sélecteur, correct |
| idem avec un summon en jeu | **`count = -1`, `listNull = true`** | **artefact du harnais** — il substituait la `UnitPosition` de la CIBLE ; le natif passe `UnitPosition$$NullPosition()` |
| `engine.ai.context.build(…, casterId de la MoW)` | **`ctx.me is None`** | **correct, et pas un verrou** — `build` est la fonction des UNITÉS ; `build_machine` rend le contexte |

Les deux lignes basses ont été **retournées par #360** : le même `MakeDamagePredictions`, invoqué
avec la position du CASTER, rend `(324, 492, 6)`. Détail, correctif et gardes :
**`docs/rl/case-360-porteur-mow-oracle-direct.md`**.

La **greffe** (`case-92` §5bis) reste légitime — le natif charge le playbook **par ability**, et la
formule de 1147 ne lit ni stat ni trait du caster — et elle est désormais **validée par mesure** :
les deux bras rejoués avec le porteur MoW réel rendent les mêmes couples.

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

### Le volet **AoE** de `1147` — ce n'est pas un second batch, c'est LA boucle (#359)

`HadesAutocannonsPlaybook$$MakeDamagePredictions` ne prédit pas « la cible » : il évalue
`GetEntitiesFromSelector(HadesAutocannonsAbility$$GetAllTargets, caster, casterPosition, target)`
et, **par entité rendue**, `AddRange(GenerateMultiHitAttackPredictions(…, e, DSLSelectors$$Entity(e),
damage, hits, 0, Nullable<DamageProfile>(null), 0))`. `damage` (`StaffOfStarsAbility$$GetDamage`,
`isPrediction = 1`) et `hits` (`AActiveAbility$$GetHits`) sont évalués **une seule fois, hors
boucle** : seule la cible change d'un event à l'autre.

Le port n'avait aucun mirror de ce sélecteur — `AActiveAbility.get_aoe_targets` rendait `[]` — donc
**un** event là où le natif en émet un par summon retenu.

    UnitsWithTrait( Friends( of: Target@0x60,
                             SurroundingUnits(Target@0x60, ConfigConst(0x16 = range),
                                              unique: 1, includeCenter: 1, sel: 3) ),
                    2 = Summon, 3 )                          # puis SortByRow / SortReverse (ordre)

`+0x60 = Target` n'est pas déduit du comportement : la carte des slots de `DSLSelectors` de ce build
était déjà établie par recoupement (`runner/abilities/deathguard.py`, en-tête de
`CursedPlagueBellAttackAbility$$CreateTrigger` : `+0x30 Owner · +0x40 Actor · +0x48 Caster ·
+0x60 Target · +0x68 ActiveTarget/Subject`), et un second consommateur la NOMME —
`DaemonicOrdnanceAbility$$GetTargetAreaTiles` = `TilesOnSameElevation(+0x60,
TilesInTriangleShape(+0x60, dir), 1)`. Contraste lisible sur `HadesAutocannonsAbility$$
ExecuteBehaviour`, qui attaque DEPUIS `+0x30`.

**Trois pièces au port**, et la troisième ne se devine pas :

1. `HadesAutocannonsAbility` (face prédiction, `entities/abilities/active_ability.py`) porte le
   sélecteur en `get_aoe_targets` ;
2. `_MAKE_DMG_TARGET_GATE[1147]` : l'appartenance de la CIBLE à son propre sélecteur se réduit
   EXACTEMENT à « vivante ET trait `Summon` » (distance 0 ≤ range avec `includeCenter`, et une
   entité est toujours de son propre camp) ;
3. `make_damage_predictions` ne court-circuite plus la boucle AoE quand la cible principale est
   refusée par un gate de sélecteur. **Mesuré** : cible = le summoner (non-summon) entouré de trois
   `deathPoxwalker` → le natif rend **3** events, aucun sur la cible demandée. Le court-circuit
   rendait 0. Inerte pour `1148`, dont le set AoE est vide.

S'y ajoute un câblage : le `DslContext` de `make_damage_predictions` fournit désormais `has_trait`
(substrat `_entity_traits`, #267-r1). Sans lui `UnitsWithTrait` rend VIDE par dégradation — le volet
AoE aurait été muet sans la moindre erreur. Inerte pour les autres sets AoE portés (aucun ne lit de
trait).

Mesures (`probe_350r3_mow_caster.py --step 4|5`), natif / port AVANT / port APRÈS :

| régime | natif | port AVANT | port APRÈS |
|---|---|---|---|
| R0 aucun summon en jeu | ∅ | **(6, 6, 6)** sur la cible | ∅ |
| R1 cible summon, 2 autres summons dans son disque | 3 events | **1** | 3 |
| R2 porteur (camp du caster) amené AU CONTACT | 3 events | 1 | 3 |
| R3 cible NON-summon (le summoner) | 3 events, **aucun sur elle** | 1 sur la cible | 3 |
| généralisation `MC1_15`, caster **allié** des summons | 3 events, dégâts ventilés (486/738 ×2, 324/492 ×1) | 1 | 3, même ventilation |

Le montage R1 discrimine à lui seul le référent d'équipe : le caster y est du camp OPPOSÉ aux
summons, donc un `Friends(of: Caster)` aurait rendu **zéro**. La généralisation borne l'autre côté
(caster ALLIÉ : un filtre `Enemies` — le réflexe pour une ability offensive, et ce que disent ses
`TargetingOptions` — rendrait zéro alors que le natif émet).

Le compte de summons est un tirage natif (`Divide(RandomAmount(cnt × chance, cnt × chance_2), 100,
Ceiling)`, `cnt` = tuiles libres du disque `CalculateRange(TurnsStarted)`) : le montage isole donc le
summoner au centre pour que `cnt = 6` et que la borne BASSE elle-même — `ceil(6 × 20 / 100) = 2` —
garantisse le régime multi-cible.

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
| idem — **H** (#359) | le SET AoE de 1147, conjonction par conjonction : rayon (témoin à `range+1`), trait, camp de la CIBLE, centre inclus ; + le gate réduit au trait `Summon` (mort refusé, scène vide refusée). `range` **relu du gameconfig**, pas écrit en dur |
| `tests/engine/test_350r3_mow_carrier_live.py` (6) | pools disjoints + chemin MoW câblé ; la MoW-caster est MESURABLE par l'oracle qui passe la position du CASTER (#360) ; 1147 `to_even` seule nulle sur deux bras ; 1148 en accord dans les **deux** régimes de feu ; **(#359)** le volet AoE sur 4 régimes + sa généralisation (autre board, caster allié) |
| `probe_350r3_mow_caster.py` | le montage (`--only-scan`, `--step 1|2|3|4|5`) |

**Mutations jouées, toutes rouges** :

| mutation | garde qui l'attrape |
|---|---|
| retirer `1148` de `_MAKE_DMG_TARGET_GATE` | live, régime froid : `(81, 123, 3)` contre `∅` |
| retirer `1147` du registre de classes **et** du gate (= le port d'AVANT #359) | live, les 4 régimes — c'est le `port_before` que le probe reconstitue, et la garde EXIGE qu'il diffère |
| ré-armer le court-circuit `if main is None: return events` | live R3 : port `∅` contre 3 events natifs |
| remplacer `ConfigConst("range")` par une constante large | offline **H** : `{10, 11, 12}` au lieu de `{10, 11}` |
| retirer `has_trait` du `DslContext` de `make_damage_predictions` | live R1 : le set AoE devient vide (la garde offline, qui construit son propre contexte, ne le voit PAS) |

## Ce qui n'est PAS couvert

- ~~**1147/1148 avec la MoW pour caster**~~ — **COUVERT depuis #360**
  (`case-360-porteur-mow-oracle-direct.md`). Les deux bras de 1147 et les deux régimes de feu de
  1148 ont été rejoués avec `blackForgefiend` POUR CASTER : 1147 rend **les mêmes couples** que la
  greffe (`(324, 492, 6)` / `(240, 360, 6)`), et 1148 a révélé un **bug que la greffe cachait**
  (`scene.team(<MoW>) is None` faisait taire son gate de sélecteur — natif `(3, 3, 3)`, port ∅).
- ~~**Le volet AoE de 1147**~~ — **COUVERT depuis #359** (section dédiée ci-dessus). ⚠ Le volet AoE
  n'a PAS été rejoué avec la MoW pour caster : les quatre régimes et la généralisation passent par
  la GREFFE. Le sélecteur ne lit rien du caster (il est ancré sur la CIBLE), mais le pont ouvert par
  #360 permettrait de le confronter directement — non fait.
- **L'ORDRE des events de 1147** : le natif ordonne son ensemble (`SortByRow` / `SortReverse` sous
  `If(AreEqual(CurrentPlayer, Player(1)))`), le port émet la cible principale en tête. **Mesuré**
  (`--step 5`) : natif `[113, 110, 116]`, port `[110, 113, 116]` — même ensemble, même valeurs.
  Sans effet sur l'utilité (`CalculateUtilityFromPredictions` **somme**), d'où une garde qui porte
  sur l'ENSEMBLE ; le jour où un consommateur lira le premier event, il faudra porter le tri.
- **Le pendant du volet AoE pour 1148** : son playbook boucle lui aussi sur un sélecteur, mais le
  port n'a **pas** de set AoE pour elle (`AActiveAbility.get_aoe_targets` → `[]`). Une cible hors
  zone-de-feu alors qu'un AUTRE ennemi y est debout donne donc `∅` côté port et un event côté natif.
  Le mécanisme est en place (la levée du court-circuit vaut pour tout `_MAKE_DMG_TARGET_GATE`) : il
  ne manque que le mirror de `GetAllDamageableTargets` en `get_aoe_targets`. Non porté, non mesuré.
- **La couche TRIGGERED** (tableau ci-dessus) : lue, non portée, non confrontée.
