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

### Le volet **AoE** de `1148` — le SET, pas seulement le gate (#359-r1)

Le gate ci-dessus ne couvrait que la cible **PRINCIPALE**. La boucle native, elle, est celle du
sélecteur : `MakeDamagePredictions` évalue `GetEntitiesFromSelector(GetAllDamageableTargets, caster,
casterPosition, target)` et, **par entité rendue**, `AddRange(GenerateMultiHitAttackPredictions(…, e,
DSLSelectors$$Entity(e), damage, hits, 0, Nullable<DamageProfile>(null), 0))`. `hits`
(`AActiveAbility$$GetHits`) est hoisté ; `damage` est évalué DANS la boucle, mais
`DaemonicOrdnanceAbility$$GetDamage(target, state, isPrediction)` **ignore son argument `target`**
(son corps est `AActiveAbility$$MinMaxDamage(state, isPrediction)` seul) — la base est donc la même
pour toutes les entités, et il n'y a rien à surcharger.

Le port n'avait **aucun** mirror de ce sélecteur : `AActiveAbility.get_aoe_targets` rendait `[]`.
La zone étant ancrée sur la CIBLE, elle la contient toujours — d'où l'exactitude du gate — mais elle
contient **aussi les deux voisines du triangle**, et c'est là que l'écart vivait.

**Trois pièces**, comme pour `1147`, mais la troisième est différente : le sélecteur est
TILE-DOMAIN, donc il exige des canaux que le `DslContext` de la prédiction n'avait pas.

1. `DaemonicOrdnanceAbility` (`entities/abilities/active_ability.py`) porte le sélecteur en
   `get_aoe_targets`. `Tiles(Subject@0x68)` est collapsé en `Subject()` — le sujet lié par le
   `Filter` est déjà une entité-TUILE, `UnitsMainTilesSelector` y est l'identité (même collapse que
   la face COMBAT) ;
2. `_MAKE_DMG_TARGET_GATE[1148]` : **inchangé**, il datait de #350-r3 ;
3. la levée du court-circuit (#359) : **inchangée**, et c'est le régime R\_B ci-dessous qui l'exerce
   — la cible principale y est refusée par le gate alors que le natif émet.

**Le câblage, et ses TROIS dégradations silencieuses.** Aucune n'aurait levé d'erreur :

| canal | sans lui | conséquence |
|---|---|---|
| `board` | `TilesInTriangleShape` / `TilesOnSameElevation` / `Units(<tuiles>)` rendent `[]` | volet muet |
| `tile_has_effect` | branche TUILE de `HasEffect` sans accesseur → `False` | volet muet |
| `Scene.machine_of_war_position` | `IsPositionMachineForCurrentPlayer(2)` FAUX d'office → `dir = 4` | **mauvais triangle**, en silence |

Les deux premiers viennent de la `Scene` (le second par `_tile_has_effect_from_scene`, qui traduit
l'id d'entité-tuile en position — **même substrat que le gate**, foyer unique). Le troisième est
neuf : `Scene` porte désormais `machine_of_war_position`, posé par `engine.ai.context` via
`_machine_of_war_position` (la cascade de `AiDecisionContext.machine_of_war_position`, extraite en
fonction module pour que les deux consommateurs ne divergent pas). `make_damage_predictions` ne
reçoit que la `Scene` — c'est la raison d'être du champ.

⚠ **Piège d'OUTILLAGE, et il a coûté une passe de mesure** : `probe_344._ctx` n'appelle pas
`AICTX.build(..., spawn_groups=…)`. Sans les groupes, la cascade retombe sur le slot d'une MoW
**déployée** (`decisionView.mows`) — et un montage GREFFÉ n'en a aucune → `None` → `dir = 4`. Le
probe lit donc les `SpawnPointGroups` dans le state-file du build (`_ctx_with_groups`), résidu
d'outillage déjà nommé par `case-302` (aucun RPC ne les expose par runner).

Mesures (`probe_350r3_mow_caster.py --step 6|7`), natif / port AVANT / port APRÈS. Montage :
1148 greffée sur `deathBlightbringer`, deux ennemis d'armures **pilotées** (0 et 500) et niveau 50 —
au niveau 2 les quatre bornes saturent au plancher `(3, 3, 3)` sur les deux, et l'accord ne dirait
plus rien des VALEURS.

| régime | natif | port AVANT | port APRÈS |
|---|---|---|---|
| R\_A cible sur tuile EN FEU | `(2793, 4191, 3)` | = natif | = natif |
| R\_B **cible sur tuile FROIDE**, un autre ennemi brûlant dans SON triangle | **1** event, sur l'AUTRE | **∅** | 1, = natif |
| R\_C deux ennemis sur tuiles en feu | **2** events, `(2793,4191,3)` et `(1941,4038,3)` | **1** | 2, mêmes valeurs |
| généralisation `C1_15` (`dir` BASCULE à 4) | idem, `(4191,6288,3)` / `(1941,4038,3)` | idem | = natif |

R\_B est le régime du cas : la cible demandée n'a **aucun** event natif, et le natif émet quand
même. R\_C sépare les VALEURS — sans les armures distinctes, un port qui recopierait la prédiction
principale sur chaque membre du set passerait.

**La généralisation borne la SECONDE branche du `If`.** `MC1_67` déclare
`MachineOfWarPosition(team 1) = 2` → `dir = 1` (triangle `{S, SE}`) ; `C1_15` déclare `0` → `dir = 4`
(`{NW, N}`). Balayage du dépôt : **502** boards résolvent sur `0`, **173** sur `2`. La mutation
« canal MoW débranché » est **rouge sur `MC1_67` et VERTE sur `C1_15`** — une seule des deux gardes
ne prouverait donc rien.

⚠ **Résidu NOMMÉ, découvert par cette généralisation** : sur `C1_15` le natif n'allume que
`{(3,3), (3,4)}` du triangle `{(2,3), (3,3), (3,4)}`, et la seule covariable relevée était
`walkable = False`. D'où une garde par **inclusion** (les tuiles allumées sont dans le triangle
attendu, centre compris), pas par égalité.

> **TRANCHÉ par #368** — `docs/rl/case-368-pose-daemonic-ordnance.md`. Deux choses distinctes
> étaient confondues. **(a)** L'amputation « 3 nominales → 2 réelles » qui a coûté une passe de
> montage est **l'ÉLÉVATION** (`TilesOnSameElevation(…, maxDiff = 1)`), déjà portée : le
> « nominal » comparé était la géométrie calculée à la main par `probe_302_3._burn_stage`, sans ce
> filtre. Mesuré, natif == port sur les **deux** branches du `If` — et sur `MC1_67` la tuile amputée
> est **MARCHABLE**, ce qui retourne la covariable. **(b)** Un écart RÉEL subsiste, plus étroit :
> une tuile de la zone **non marchable** n'est pas embrasée par le natif (3 mesures, 2 boards,
> 2 terrains, dont une où les trois élévations sont identiques). Sa cause native n'est **pas
> tranchée** — aucun étage de la chaîne de pose ne lit la marchabilité, et `tileMeta` filtre les
> effets inactifs sans exposer le drapeau, donc « non posé » et « posé-inactif » restent
> indiscernables. Capteur nommé et livré (non activé). L'écart reste **inerte** pour ce sélecteur,
> pour la raison ci-dessous.

Il est **inerte pour ce sélecteur** : une unité ne se tient pas sur une tuile non marchable, donc
`Units(<tuile non marchable>)` rend vide de toute façon.

### Le **BRANCHEMENT** de cette prédiction sur la route de DÉCISION (#359-r3)

La mécanique ci-dessus était portée et confrontée ; elle n'était **branchée nulle part**.
`DaemonicOrdnancePlaybook` (port) héritait de `NonAttackComparablePlaybook.make_damage_predictions`,
qui rend `[]` — donc terme de prédiction **nul partout**, y compris là où le natif prédit.

`DaemonicOrdnancePlaybook$$MakeDamagePredictions` **relu** : liste vide, puis, pour chaque entité de
`GetEntitiesFromSelector(GetAllDamageableTargets, caster, casterPosition, target)`,
`AddRange(GenerateMultiHitAttackPredictions(caster, casterPosition, e, DSLSelectors$$Entity(e),
GetDamage(…), GetHits(), 0, Nullable<DamageProfile>(null), 0))`. **Il n'y a pas de « cible
principale »** — et ce n'est pas un détail de forme : `<Target>` est ici une entité **TUILE**
(`0x46000040`, bit 6), qui ne prend aucun dégât. La forme « main + AoE » de
`prediction.make_damage_predictions` est le mirror du régime à cible **UNITÉ** (celui de l'oracle
`aiPlaybookPredict`, #359-r1) ; sur la route de DÉCISION c'est la **BOUCLE** qui est le mirror. D'où
un override dans le playbook, exactement comme `PlagueburstMortarPlaybook.make_damage_predictions`.
`param_8 = null` est **lu** dans `_PLAYBOOK_PROFILE_OVERRIDE[1148]` (foyer unique déjà confronté),
jamais recopié en littéral.

Le sélecteur est TILE-DOMAIN : il exigeait `tile_has_effect` au `DslContext` de la route tuile
(`playbook/tile_targets.py`), par le **même** `_tile_has_effect_from_scene` que la face PRÉDICTION.
Inerte pour `1169`, dont aucun nœud ne lit d'effet de tuile.

**Montage** (`probe_302_3_daemonic_ordnance.py --burning`), et il tient à **deux** trouvailles :

1. **1148 SORT du kit après son cast** (`decisionView.abilities = [69]` seul, `allAbilities: True`
   compris) et le feu ne dure que `DefaultAmountOfRounds(5) = 2` rounds : un mono-porteur devrait
   attendre un cooldown qui **survit au feu** — régime inatteignable. On greffe donc 1148 sur
   **deux** unités : un ALLUMEUR, qui caste et part en cooldown, et le DÉCIDEUR, mesuré **dans le
   même tour**. ⚠ Lire le seul `cooldown` d'une entrée ABSENTE rend `None`, qui se lit exactement
   comme « purgé » — le probe teste désormais la PRÉSENCE.
2. **Les tuiles embrasées sont MESURÉES, pas déduites** : la zone-triangle nominale compte 3 tuiles,
   celle qui brûle en compte 2 (cast sur `(4,1)` → `{(4,1), (5,2)}`). Placer sur la géométrie
   nominale mettait un ennemi hors du feu, et le montage rendait **1** event au lieu de 2, en
   silence.

Deux ancres, l'ordre s'**inverse** selon que le terme est branché : FROIDE 3 ennemis (custom **30**,
prédiction 0) contre CHAUDE 2 ennemis brûlants (custom **20** + 2 events). L'écart de custom est
d'**un** ennemi, franchi par `AbilityVariablesMultiplierPercentage = 400` sur le décideur — levier
qui n'agit **que** sur 1148 ; baisser les PV relèverait l'attaque normale autant (mesuré : PV de
l'ennemi chaud à `8000` → `_best_attack.full = 166.98` contre `70.0` pour 1148, le natif ATTAQUE et
1148 n'est plus élue du tout — c'est pourquoi ce levier a été abandonné et n'a pas d'option CLI).

**Bras TÉMOIN, et il est indispensable** : avec **UN SEUL** ennemi brûlant, l'écart de custom vaut
DEUX ennemis (30 contre 10) et le terme (`U = 13.96`) ne suffit pas — le natif COMME le port restent
sur l'ancre FROIDE. Le terme ne renverse donc pas *par principe*, il renverse quand il PÈSE plus que
l'écart. Sans ce bras, un port qui préférerait la zone brûlante systématiquement passerait le bras
séparant.

| mesure | natif | port APRÈS | port AVANT (débranché) |
|---|---|---|---|
| tuile élue, **2** brûlants (custom 30 vs 20) | `(1148, 49)` = `(4,1)` | = natif | **`(1148, 52)` = `(4,4)`** |
| tuile élue, **1** brûlant (custom 30 vs 10) — TÉMOIN | `(1148, 52)` = `(4,4)` | = natif | = natif |
| agreement, marche entière | — | **11/11** casts, 7/7 pos, 4/4 stay | **10/11** casts |

Le désaccord du bras débranché, verbatim :
`step 0 u87: ABIL native(ab=1148,tgt=49) engine=ability(ab=1148,tgt=52) [MISS]`.

⚠ `engine_validate.run_agreement` accepte désormais `spawn_groups` (défaut `None` = inchangé) :
sans lui, `IsPositionMachineForCurrentPlayer` retombe sur son repli et 1148 marche sur le mauvais
triangle — le désaccord n'accuserait alors que le harnais.

**La garde qui semblait devoir tomber ne tombe pas.**
`test_prediction_term_is_zero_because_the_area_is_not_burning` reste **verte** : ce que le
branchement change, c'est le régime BRÛLANT, pas le régime froid, où le sélecteur reste vide **par
construction native**. Seule sa docstring encodait l'ancien comportement (« ce test DOIT tomber ») ;
l'assertion garde désormais le **gate de sélecteur**.

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
| idem — **(7)(8)** (#359-r1) | le SET AoE de 1148 sur 3 régimes, dont celui où la cible demandée n'a AUCUN event natif ; les VALEURS séparées par cible (armures pilotées) ; le port d'AVANT EXIGÉ différent ; et **(8)** le même montage sur un board où `dir` bascule — les deux ensemble bornent les deux branches du `If` |
| `probe_350r3_mow_caster.py` | le montage (`--only-scan`, `--step 1|2|3|4|5|6|7`) ; `--step 6` imprime la DÉCOMPOSITION PAR ÉTAGE du set (classe routée, board, `mow_position`, triangle brut + élévations + marchabilité, zone, tuiles en feu, AoE) — c'est elle qui a désigné le canal manquant au lieu d'un `[]` muet |
| `tests/engine/test_daemonic_ordnance_decision_live.py` — **H** (#359-r3) | le régime BRÛLANT de la route de DÉCISION : le montage brûle vraiment (2 tuiles chaudes en feu, 0 froide, 2 events contre 0) et le custom FAVORISE la froide ; 1148 bat l'attaque normale (sinon la mesure porterait sur l'arbitrage, pas le ciblage) ; accord natif/port sur la tuile élue ; et la VUE ROUGE — `make_damage_predictions` remis sur le corps de base élit l'ancre FROIDE |
| `probe_302_3_daemonic_ordnance.py --burning \| --agreement [--unbranched]` | le montage à DEUX porteurs + la marche entière (11/11 contre 10/11) |

**Mutations jouées, toutes rouges** :

| mutation | garde qui l'attrape |
|---|---|
| retirer `1148` de `_MAKE_DMG_TARGET_GATE` | live, régime froid : `(81, 123, 3)` contre `∅` |
| retirer `1147` du registre de classes **et** du gate (= le port d'AVANT #359) | live, les 4 régimes — c'est le `port_before` que le probe reconstitue, et la garde EXIGE qu'il diffère |
| ré-armer le court-circuit `if main is None: return events` | live R3 : port `∅` contre 3 events natifs |
| remplacer `ConfigConst("range")` par une constante large | offline **H** : `{10, 11, 12}` au lieu de `{10, 11}` |
| retirer `has_trait` du `DslContext` de `make_damage_predictions` | live R1 : le set AoE devient vide (la garde offline, qui construit son propre contexte, ne le voit PAS) |
| **(#359-r1)** retirer `DaemonicOrdnance` du registre de classes (= le port d'AVANT) | live R\_B : `port [] != natif [{'target': 77, 'dmg': (2793, 4191, 3)}]` |
| **(#359-r1)** ré-armer le court-circuit `if main is None: return events` | live R\_B : **même** message — c'est le seul régime qui l'exerce |
| **(#359-r1)** retirer `1148` de `_MAKE_DMG_TARGET_GATE` | live R\_B : le port ajoute un event sur la cible FROIDE — `port [{'target': 79, …}, {'target': 77, …}] != natif [{'target': 77, …}]` |
| **(#359-r1)** débrancher `current_player_machine_position` | live R\_B sur `MC1_67` : `port [] != natif […]` — et **VERT sur `C1_15`**, où la dégradation coïncide avec `dir = 4` |
| **(#359-r1)** débrancher `tile_has_effect` | live R\_B : `port [] != natif […]` |
| **(#359-r3)** remettre `make_damage_predictions` sur le corps de base (= le port d'AVANT) | live, zone en feu : `step 0 u87: ABIL native(ab=1148,tgt=49) engine=ability(ab=1148,tgt=52) [MISS]` — agreement 10/11 au lieu de 11/11 |

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
- ~~**Le pendant du volet AoE pour 1148**~~ — **COUVERT depuis #359-r1** (section dédiée ci-dessus).
  ⚠ Comme pour 1147, il n'a PAS été rejoué avec la MoW pour caster : les quatre mesures passent par
  la GREFFE. Le sélecteur ne lit du caster que son `team` (`Enemies(Caster, …)`), et le pont #360
  permettrait de le confronter directement — non fait.
- **L'ORDRE des events de 1148** : non mesuré. Le sélecteur de 1148 n'a PAS de nœud de tri (contraste
  avec 1147, qui finit par `SortByRow`/`SortReverse`), donc l'ordre natif est celui de l'itération
  des tuiles de `GetTargetAreaTiles`. Le port l'obtient par construction (`Units` itère les tuiles),
  mais la garde porte sur l'ENSEMBLE — l'ordre n'a pas été confronté.
- ~~**La tuile NON MARCHABLE du triangle**~~ — **REPRIS par #368**
  (`docs/rl/case-368-pose-daemonic-ordnance.md`). L'amputation nominal → réel est l'ÉLÉVATION, déjà
  portée (natif == port, deux branches du `If`). L'écart lié à la marchabilité existe, est mesuré
  trois fois et **borné** (l'écart `port \ natif` est exactement l'ensemble des tuiles non
  marchables de la zone), mais sa **cause native reste non tranchée** — capteur `tileMeta
  includeInactive` livré, non activé. Inerte pour la prédiction comme pour le combat.
- ~~**Le BRANCHEMENT de la prédiction de 1148 sur sa route de DÉCISION**~~ — **FERMÉ (#359-r3)**,
  section dédiée ci-dessus.
- **La généralisation du montage BRÛLANT à un board où `dir` bascule** (#359-r3) : **NON COUVERTE**.
  Le placement piloté échoue sur `C1_03` — `act move` respecte la portée de déplacement de l'unité,
  et les spawns y sont trop loin des ancres (`worldTerminator` reste à `(1,3)` au lieu de `(4,3)`) ;
  le probe le REFUSE (`placement KO (obtenu, attendu)`) au lieu de mesurer un montage dégradé.
  Portée bornée : le branchement lui-même ne lit pas `dir`, et les DEUX branches du `If` sont déjà
  gardées ailleurs — bras `--flip` (`C1_03`) côté custom, `C1_15` côté prédiction (#359-r1). Ce qui
  manque est une confrontation du branchement sous `dir = 4`, pas une lecture.
- **La couche TRIGGERED** (tableau ci-dessus) : lue, non portée, non confrontée.
