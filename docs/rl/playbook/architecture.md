# Architecture de l'IA playbook (vue d'ensemble + spine décisionnel)

> But : carte fidèle de l'IA native de Tacticus (build gqfc5mff6c) — comment une équipe
> choisit *quelle unité* active *quelle action*, et comment cette architecture se réimplémente
> de façon **modifiable** en Python. Le détail du calcul de score est dans `scoring.md`, les
> prédictions dans `prediction.md`, le déplacement dans `pathfinding.md`, les feuilles par-ability
> dans `playbooks.md`, l'état d'avancement dans `status.md`.

## 1. Les deux étages

L'IA = **maximisation d'utilité par buckets**, PAS 200 algorithmes indépendants. Deux étages :

1. **Étage scorer — `Utilities`** (somme pondérée). Au-dessus : une devise unifiée. Chaque action
   candidate reçoit une utilité Fix64 = somme pondérée de prédictions (dégât/soin/effet/repair) +
   utilités de position/tuile, poids tirés de `BattleConfiguration.Utilities`. **Il n'y a que 2
   profils dans le BC** : `Default` (54 groupes — TOUT le scoring IA) et `MovementSuggestion`
   (**1 seul** groupe `RangedAdjacentEnemy` = overlay de la feature UI swipe `MovementSuggestionState`,
   PAS le scoring de mouvement de l'IA). ⇒ **l'IA lit toujours `Default`** ; il n'y a pas de bascule
   Default↔MovementSuggestion selon action/mouvement. Cœur =
   `ComparablePlaybook.CalculateActionUtility`. Détail des termes et poids → `scoring.md`.
2. **Étage playbooks par-ability** (1 classe/ability, registre ~351 entrées). En dessous : chaque
   ability possède sa `Playbook` qui (a) énumère ses candidats (cibles/tuiles éligibles) et
   (b) leur attribue un score. La majorité héritent du comportement de base ; seuls quelques deltas
   par feuille. Détail des feuilles → `playbooks.md`.

## 2. Le spine décisionnel (complet)

```
while valid_units:                              # PickNextUnit — ordonnancement des unités
    unit = next ordered valid unit
    cands = []
    for ability in unit.abilities:              # 1 playbook / ability
        cands += playbook_for(ability).evaluate(unit, pos)   # remplit un BUCKET de candidats
    action = choose_action(cands, ctx)          # argmax-utilité parmi les actions LÉGALES
    apply(action)
```

### 2.1 `PickNextUnit` — choix de l'unité à activer

`OperationalDeciders.DefaultGroupOperator` itère les unités valides (vivantes + contrôlées + action
restante, `GetValidUnits`) selon une `order_strategy` (vtable idx 1 sur `operator.0x28`).

L'ordonnancement authoritative est un **décideur à 8 buckets à seuils**, construit EN ORDRE par
`DefaultGroupOperator..ctor` (@181183dc0) via le ctor `UtilityBucket(UtilityType, Nullable<Fix64>
minUtilityDifference)` (@180e432b0) :

| # | UtilityType | MinUtilityDifference | flag |
|---|---|---|---|
| 1 | PreferSummons(74) | **1** | |
| 2 | PreferNonBoss(68) | **1** | |
| 3 | PreferFreshlySpawned(69) | **1** | |
| 4 | UnitOrder(76) | — | **RejectAllNoneBestCases=true** |
| 5 | LastAbilities(75) | — | |
| 6 | PreferAbilities(73) | — | |
| 7 | UnitWithShortestPathToEnemy(71) | — | |
| 8 | Remaining(72) | — | |

Priorité : summons → non-boss → fraîchement-spawn (chacun gate `util≥1`) → UnitOrder (garde le
meilleur) → … → reste. Le seuil `minUtilityDifference` est porté par la config
`IdunBattleLogic.AI.Utilities` (`UtilityDefinition{ UtilityBucket[] }`,
`UtilityBucket{ WeightedUtility[] Utilities, bool RejectAllNoneBestCases, Fix64 MinUtilityDifference@0x20 }`).

### 2.2 Évaluation par-ability — remplissage du bucket

Pour chaque ability, sa `Playbook` énumère ses candidats et émet une action scorée. Squelette uniforme
(`BasePlaybook.Evaluate`, déterministe : `SetDisallowRandom` autour) :

```
evaluate(unit, pos) -> Bucket:
    bucket = Bucket()
    for cand in enumerate_candidates(unit):     # GenerateBucketWithActionForEveryEligibleTarget
        u = score(cand)                          # ← seul delta par-playbook
        bucket.AddAction(GenerateAction(unit, pos, cand, u))
    return bucket
```

Deux **régimes de score** (juste nommés ici, détail → `scoring.md`) :
- **Comparable** (`ComparablePlaybook<T>`) — attaques, soins : somme pondérée sur prédictions partagée
  (`CalculateActionUtility`).
- **NonComparable** (`NonComparablePlaybook<T>`) — summons, buffs, mouvement : heuristique entière
  écrite DANS la feuille (ex. `MasterOfTheTutelaries`, `FightingRetreat`).

`DefaultActiveAbilityPlaybook` (la majorité des abilities) est trivial : énumère les cibles, priorité
constante `Fix64(3/2)=1.5`, aucune heuristique.

### 2.3 Sélection de l'action — générateurs ordonnés, PREMIER NON-NULL (RE confirmé, modèle corrigé)

> ⚠ **Correction** : l'ancienne section affirmait un « argmax sur une devise unifiée » entre
> attaque/heal/move. **C'est FAUX** (vérifié dans le code, build gqfc5mff6c). Le vrai mécanisme est
> une **liste ordonnée de générateurs, premier-non-null**, mouvement en dernier (fallback).

`DefaultAiUnitTactic..ctor` (@1810eebc0) construit une LISTE ORDONNÉE de générateurs (@tactic+0x60) :

```
[ Gen(pref=1000), Gen(100), Gen(0), Gen(-100), Gen(-1000), Gen(final), MovementActionGenerator ]
  \________ 6 ActiveAbilityActionGenerator, un par TIER de préférence ________/   \_ move EN DERNIER _/
```

`CalculateNextActionForUnit.MoveNext` (@1810f54e0) itère la liste et renvoie la **PREMIÈRE action
NON-NULL** (`if (action != 0) break`). Pas d'argmax inter-générateurs — **premier-non-null par tier**.

**Tier de préférence par ability = sa PLAYBOOK.** `InitAbilityTypeLists` (@1810ed540) range chaque
ability dans la liste de son `playbook.Preference` (1000/100/0/-100/-1000 ; sans préférence → liste
« final »). Dict tier→abilities @tactic+0x40. `GetDefaultActiveAbilityActionGenerators` (@1810ed0c0)
crée un `ActiveAbilityActionGenerator` par tier dans cet ordre.

**Un générateur de tier** — `ActiveAbilityActionGenerator.GenerateActions` (@18119a3f0) :
1. énumère les abilities du tier que possède l'unité (`GetUnitAbilitiesInOrder` @181182a40, ordre
   déclaré, shuffle optionnel selon `ShouldRandomizeOrder`) ;
2. pour chaque ability UTILISABLE (`!IsAbilityBlocked`, `CanCurrentlyBeUsed`, playbook can-evaluate),
   exécute sa playbook → actions scorées → `Bucket.Merge` ;
3. termine par **`Bucket.ChooseAction`** (argmax-faisable, cf. ci-dessous) → renvoie l'action, ou
   **null si le bucket est VIDE** (aucune ability du tier n'a produit d'action LÉGALE).

**`ChooseAction` (argmax DANS un bucket)** :
```
ChooseAction(bucket)        @1813fc0d0:  feasible(default) ? default : ChooseActionFromBuckets(children)
ChooseActionFromBuckets     @1813fbe00:  itère la SortedList par clé, 1ʳᵉ action faisable (récursif)
Bucket.AddAction            @1813fbcc0:  default = action de plus haute utilité (op_GreaterThan) ⇒ argmax
Bucket.AddActionToBucket    @1813fbb60:  sous-bucket par catégorie (SortedList, SANS seuil ⇒ feasible)
gate FUN_18004cc80       :  action != null && (minUtilityDifference absent OU U >= minUtilityDifference)
```

**Conséquences (modèle corrigé) :**
- Ordre inter-catégorie = **tiers de préférence par-ability** (hard priority), PAS un ordre figé
  attack>heal>summon, PAS un argmax sur devise commune.
- DANS un tier, plusieurs abilities se départagent par **argmax d'utilité** (le bucket).
- Le **MOUVEMENT est un FALLBACK** : il ne fire QUE si AUCUN tier d'ability n'a produit d'action
  légale (= rien d'atteignable/utilisable). **Pas de seuil utilité ability-vs-move.**
- « Bouger pour mieux attaquer » N'EST PAS le MovementGen : c'est une **action d'ability avec
  composante de déplacement** (la playbook énumère les couples (tuile atteignable, cible) ; le bucket
  prend le meilleur). Le MovementGen pur (approche) ne sert que quand aucune attaque n'est possible
  depuis aucune tuile atteignable.

> **Re-validation LIVE (Rotbone, #38 option A) → VERDICT B** : Rotbone, allié adjacent **manque 2007 PV**
> (cible LÉGALE de Heal 18 ET Active 1037 via `abilityTargets`), Rotbone sans attaque → **le natif BOUGE**.
> Donc « premier-non-null PUR » est incomplet : un tier peut renvoyer null **malgré une cible ciblable**.

> **MàJ (RE ré-confirmée gqfc5mff6c) + lien avec le faux-vert ability (§1)** : `GetDefaultActiveAbilityActionGenerators
> @1810ed0c0` lu ligne-à-ligne → tiers = **littéraux `[1000, 100, 0, -100 (0xffffff9c), -1000 (0xfffffc18),
> FINAL]`** (dict `tactic+0x40`, + liste `final` `tactic+0x38`). `InitAbilityTypeLists @1810ed540` : pour
> chaque ActiveAbilityType, `pref = playbook.get_Priority()` (**interface slot 0** ; slot 1 = bool "final")
> → bucket `Dict<Preference,List>`. Le getter est **`get_Priority`** (virtuel per-playbook, pas de symbole
> statique). **EXTRAIT LIVE** via le probe `abilityPreferences` (`frida/hooks/features/ability-prefs.ts` :
> hook passif `LoadPlaybook` → capture DB, puis `LoadPlaybook(db,ability,1)` + `get_Priority` par ability).
>
> **Carte des tiers (sweep 0..1300, gqfc5mff6c)** — **seules 22 abilities / 1300 ont un tier ≠ 0** :
>
> | Priority | # | abilities |
> |---|---|---|
> | **0** (défaut) | 1278 | toutes attaques normales + la plupart des dégâts/soins (69, 1171, 1067, 1081, 1129, 1150, 1183…) |
> | **1000** | 9 | EreWeGo(1085), BreathOfSilence(1070), DeathScream(1109), ArmouredMight_Move(1127), TzeentchsFirestorm(1155), ArcScourge(1173), NovaBoost(1192), SquigLaunchas(1200), DeathOnTheWind(1213) |
> | **100** | 4 | Catalyst(1032), GunnersKillOnSight(1125), SolarAtomizer(1174), ThriceBlessedConflagration(1187) |
> | **-100** | 3 | MacroPlasmaIncinerator(1159), SquigMine(1201), InfernalCannon(1209) |
> | **-1000** | 6 | MyWillBeDone(1072), DaGreatWaaagh(1084), LivingBatteringRam(1111), InvocationOfMachineVengeance(1172), NovaShield(1194), ReanimationBeam(1223) |
>
> ⚠ **Le moteur VIOLE ce modèle** : `engine_decide` fait un **argmax plat** + tie-break codé en dur
> « **spécial>normal** » — PAS le tier-first-non-null. MAIS **les mismatches seed-777 sont TOUS tier-0**
> (69, 1171, 1067, 1081, 1129, 1150, 1183 = Priority 0) → **ce ne sont PAS des désaccords de TIER, mais de
> WITHIN-TIER** : le playbook natif de `1171` (DakkaDakka) a renvoyé NULL (gate bespoke §3.3) OU l'utilité
> within-tier diffère, alors que le moteur préfère `1171` (spécial>normal). ⇒ le fix ability = **(1)** porter
> le tier-first-non-null (**table de 22 abilities ≠ 0** ci-dessus, hardcodable — cheap, mais ne corrige QUE
> les batailles avec ces 22 abilities) **+ (2)** les **gates bespoke par-playbook (§3.3)** = le vrai levier
> des 30 % (la majorité des abilities étant tier-0). Les deux entremêlés ; (2) domine.

### 2.3bis Le GATE par-action (`ShouldExecute`) — RE complet

Chaque action *comparable* (attaque/soin/repair) s'auto-gate à l'**émission**. Flux (RE) :

```
ComparablePlaybook.EvaluateInternal   @181408980 :  pour chaque cible éligible
    util = CalculateActionUtility(...)              # Nullable<TimeSpan>
    if util.HasValue:                               # <-- GATE : sinon AUCUNE action émise
        action = GenerateAction(unit, cible, util.Value)
        if FUN_18004cc80(bucket, action): bucket.argmax(action)

CalculateActionUtility                @181406ee0 :
    u = predictionUtility(...)                      # heal: CalculateUtilityFromHealEvent (cf. §9)
    if !ShouldExecute(unit, cible, u): return null  # vtable +0x328  → Nullable.null
    u += tileUtility (CalculateUtilityFromTilePrediction) + UtilityAttackCase + ...
    return Nullable(u)                              # (sentinels TimeSpan Zero/Min/Max gérés à part)

HealPlaybook.ShouldExecute            @181184b30 :  return u > 0 && (cibleNonBoss || cible != caster)
```

⇒ **Le gate = `prédiction d'utilité > 0`.** Si l'utilité de soin (la cible) est `<= 0`, `ShouldExecute`
renvoie false → `CalculateActionUtility` renvoie `null` → `EvaluateInternal` **n'émet pas** d'action →
le tier soin renvoie null → fallback MOVE. (Légalité de ciblage `abilityTargets` ≠ utilité > 0.)

> ⇒ **Remplaçant fidèle de `ENGINE_HEAL_MIN_UTIL`** : émettre le soin **ssi `heal_utility > 0`** (seuil
> **0**, pas 50), sur l'utilité de soin déjà portée (#37, `predict.py` PARTIE 3). Idem attaque (utilité
> de prédiction > 0, + sentinels kill).
>
> **✅ RÉSOLU — « VERDICT B » était une ERREUR DE MESURE, pas un comportement natif.** Le dump de
> l'action COMPLÈTE de Rotbone (`aiDryRunAllUnits`, chunk entier, pas juste le 1er message) :
> `[ MoveUnitMessage u80→(1,2), ActiveAbilityMessage caster=80 target=80 abilityType=18 (Heal) ]`.
> **Rotbone se DÉPLACE PUIS SOIGNE.** Le helper `native_first` renvoyait `"move"` sur le premier
> message et **masquait le heal qui suit** → tout le « contradiction / gate mystère » poursuivait un
> **fantôme**. La chaîne RE était **correcte depuis le début** : `heal_utility > 0` ⟹ le soin EST émis.
> Les sous-pistes (IsFriend par-joueur `@180ed8550`, magnitude `Damage×hits`, éligibilité
> `ShouldEvaluateTarget @18111fb10` sans filtre « déjà agi », `get_CanCurrentlyBeUsed @180f8fdb0`
> cooldown/charges, abilities `18`+`1037` `usable=true`) restent des RE valides, mais elles cherchaient
> à expliquer un non-événement.
>
> **Leçon (mesurer la vérité terrain, pas un proxy)** : l'action native est souvent **COMPOSÉE**
> (`move + ability`). Toute comparaison moteur-vs-natif doit lire le **chunk entier**, pas
> `native_first[0]`. ⚠ **`ENGINE_HEAL_MIN_UTIL` est très probablement FAUX** : il fait *bouger* le moteur
> là où le natif fait *move+heal* ; la « concordance » mesurée plus tôt ne tenait qu'au 1er message
> (le move), par coïncidence.
>
> **✅ REFONTE SCORING UNIFIÉ (1ère tranche, `engine_decide` — VALIDÉE LIVE).** Modèle natif porté :
> chaque ability candidate = `(tuile atteignable, cible)` scorée `pred_util + tile_util(tuile)` ;
> gate `ShouldExecute` = `pred_util > 0` (l'ancien seuil 50 RETIRÉ — il était faux) ; argmax `full_util`
> ; le MOVE est le **fallback** (RE premier-non-null). La branche soin **balaie les tuiles** (cible
> joignable depuis T ssi `hexdist(T,cible) ≤ HEAL_RANGE`, self depuis toute tuile) → produit une action
> **composée move+heal**. **Validation Rotbone : MATCH EXACT** (moteur = natif : move→(1,2) + heal
> ability 18 sur self) après fix `is_friend` (comparer à `me.team` 1/2, pas `currentPlayer` 3/4).
> **RESTE** : (a) ~~`HEAL_RANGE=1` → portée pour soins à distance~~ **résolu (§2.3ter) : gameconfig
> confirme qu'AUCUN soin d'allié ciblé n'a de `range` → adjacent, `HEAL_RANGE=1` correct** ; (b)
> `tile_util` = `move.move_utility` **n'est PAS le terme de tuile natif** — le vrai (RE §2.3ter) =
> `CalculateUtilityFromTilePrediction` = composite **Tile(7)** (déjà porté = `tile_composite`), et
> surtout la **tuile du caster** vient du **prédicteur de position (vtable +0x398)**, PAS d'un balayage
> `move_utility` → un simple swap `move_utility`→`tile_composite` ne suffit pas (RE +0x398 = vraie
> prochaine brique) ; (c) intégrer summon/buff au pool unifié (encore en branche fallback) ; (d)
> **non-régression** : lancer les tests ciblés attaque/heal (la branche attaque passe de return-immédiat
> à candidat-poolé) avant tout commit ; (e) corriger `native_first`/le harnais d'agreement pour comparer
> le **chunk complet** (move ∧ ability).

### 2.3ter `CalculateUtilityFromTilePrediction` — RE complet (le terme de tuile d'action)

`CalculateActionUtility @181406ee0` (branche normale, RE ligne à ligne) additionne, dans l'ordre :

```
u  = predictionUtility            (vtable +0x338, +0x340)   # heal: utilité de soin (§9)
u += CalculateUtilityFromPredictions(config @…+0x48)        # utilités liées aux prédictions
if !ShouldExecute(unit, cible, u):  return null             # vtable +0x328  (GATE, cf. §2.3bis)
u += term                          (vtable +0x348, +0x350)
u += UtilityAttackCase-key0x36     (registre playbook +0x40, clé 0x36)
u += CalculateUtilityFromTilePrediction(config @…+0x60)     # <-- LE TERME DE TUILE
return Nullable(u)
```

`CalculateUtilityFromTilePrediction @181408740` (RE) :

```
if (vtable +0x318)(this, this+0x320):  return 0            # gate : pas de terme de tuile
pos  = (vtable +0x398)(this, unit, position, config+0x3a0) # <-- PREDICTEUR DE POSITION DU CASTER
if pos.MainTile == null:  return 0
case = new UtilityMovementCase(unit, pos, definition = playbook+0x10)   # ctor @181105ef0
grp  = playbookUtilities[key=7]        # registre playbook +0x40, classe dict DAT_1831eeb88
return Fix64(0) + grp.Evaluate(case)   # grp = composite Tile(7)
```

**Deux faits établis (décompilé = vérité) :**
0. **(#128) La membership du composite `Tile(7)` est LUE au décompilé, plus supposée.**
   `IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` résout un `UtilityType` via une **carte de
   composition** `db+0x58` (`Dictionary<UtilityType, UtilityType[]>`) : 1 enfant ⇒ l'utilité seule,
   `> 1` ⇒ `new ComposedUtility(children)` ; sinon `db+0x60` = fabrique de feuille.
   `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities` y écrit : **clé 7 (`Tile`) → tableau
   de 0x1d = 29** (= `engine/utilities/tile.py::TILE_LEAF_IDS`), clé 0x22 (34 `Damage`) → 13,
   clé 6 (`UnitMovement`) → `[7, 0x10 MinDistanceToClosestEnemy]`, clé 5 → `[6, 0x11]`, clé 0 → `[7, 1]`,
   clé 0x20 → `[7, 0x21]`. Et `IdunBattle.AI.Playbook.BasePlaybook$$Init` pose `playbook+0x40 = param_8`
   ⇒ **c'est LA MÊME base d'utilités que le sweep MOVE**, pas un profil par playbook (la BC n'a que
   `Utilities.Default` et `Utilities.MovementSuggestion`, ce dernier réduit à `RangedAdjacentEnemy`).
1. **Le terme = le composite `Tile(7)`** évalué sur un `UtilityMovementCase(caster, tuile-prédite)`.
   C'est EXACTEMENT ce que `engine/utilities/tile.py::tile_composite` porte déjà (sa docstring cite
   « scoré par `Weight[Tile=7]` dans `CalculateUtilityFromTilePrediction` »). Sur une carte plate,
   `Tile(7) ≈ 0` (feuilles situationnelles gatées sur métadata absente) → ce terme **ne sélectionne
   pas** la tuile ; c'est un bonus/malus additif.
2. **`+0x398` = `MakeFinalTilePrediction`, et c'est l'IDENTITÉ** (RÉSOLU par lecture de la vtable runtime
   via Frida — « voie 1 »). Son jumeau `Playbook<T>.GetMovementUtility @1814ab490` est identique à
   `CalculateUtilityFromTilePrediction` **sans** le transform `+0x398` ⇒ `+0x398` est *uniquement* le
   transform `position candidate → position prédite`. Or son corps (`HealPlaybook`, gshared `@0x1803088d0`)
   = **`49 8b c0 c3` = `mov rax, r8 ; ret`** = **retourne le 3ᵉ argument (la position d'entrée) inchangé**.
   ⇒ pour un `ComparablePlaybook`, la tuile prédite = la tuile candidate **telle quelle**, aucune
   ré-computation d'engagement.

**Résolution du slot +0x398 (vtable runtime `HealPlaybook`, klass `0x1df81f5ab20`) — validée** : le slot
+0x328 lu = `ShouldExecute` (= le modèle d'offsets est correct). Table lue :

| off | méthode (via `il2cpp_method_get_name`) |
|-----|----------------------------------------|
| +0x2f8 | `get_CanHandleNullCasterTile` |
| +0x318 | `get_IgnoreTileUtility` (le gate de `CalculateUtilityFromTilePrediction`) — **relu #128 : `Loki_NormalAttackPlaybook`, `ExcruciatingFrequenciesPlaybook` et `HealPlaybook` pointent TOUS le même stub `0x1802b15a0` = `32 c0 c3` (`xor al,al ; ret`) ⇒ FALSE, le terme de tuile s'applique toujours ; aucun symbole `*$$get_IgnoreTileUtility` n'existe = aucun override dans le build** |
| +0x328 | `ShouldExecute` *(validation)* |
| +0x338 | `CalculateCustomUtility` |
| +0x348 | `CalculateCasterPositionUtility` (base = `Fix64(0)`) |
| +0x358…+0x388 | `Make{Damage,Heal,Effect,Repair}Predictions` |
| **+0x398** | **`MakeFinalTilePrediction`** = identité (`mov rax,r8;ret`) |

**Portée / anti-généralisation** (confirmé en live) : `MightFromBelowPlaybook` **et** `RepairPlaybook`
pointent +0x398 sur le **même stub identité** `0x1803088d0` → les repositionneurs n'overrident PAS le
prédicteur de tuile ; ils overrident `CalculateCasterPositionUtility` (+0x348, un terme d'**UTILITÉ**).
`FireAndRepositionPlaybook` a +0x398 = slot garbage → c'est une `NonComparablePlaybook` (vtable + chemin
`EvaluateNonComparable` différents). ⇒ **identité = comportement de base de TOUT `ComparablePlaybook`**.

**Conséquence (H2 confirmée, H1 réfutée)** : `+0x398` **ne calcule PAS** de tuile d'engagement/mouvement.
Combiné à `Tile(7) ≈ 0` (plat) et `CalculateCasterPositionUtility = 0`, **aucun terme d'utilité de
l'action ne discrimine la tuile du caster pour un soin plat**. ⇒ le balayage `(tuile × cible)` +
`move.move_utility` du moteur (qui récompense l'engagement) **n'est PAS** le mécanisme natif ; s'il a
matché Rotbone→(1,2), c'est **par coïncidence**, pas par fidélité.

**Report du (1,2)** : puisque `MakeFinalTilePrediction` est l'identité, la tuile-caster émise = une
**position candidate énumérée en amont** — pas un choix d'utilité de `+0x398`. Le locus de cette
énumération est le **générateur** (§2.3quater ci-dessous), pas `EvaluateInternal`.

### 2.3quater L'énumération des tuiles candidates — RE (générateur + bucket-tree)

`EvaluateInternal @181408980` **n'énumère PAS les tuiles** : il énumère les **cibles éligibles**
(`GetEligibleTargetsEntities`) à **position caster FIXÉE** (param_4), calcule `CalculateActionUtility`
par cible, `GenerateAction`, et garde l'argmax dans un `Bucket` (tie-break = **premier sur égalité**,
`op_GreaterThan` STRICT). L'énumération des **tuiles** est un cran au-dessus, dans
`ActiveAbilityActionGenerator.<GenerateActions>d__7.MoveNext @18119a3f0` :

```
accumulator = new Bucket()                                  # <-- UN SEUL, AVANT la boucle d'abilities
for each ability in GetUnitAbilitiesInOrder(tier):          # gate IsAbilityBlocked + get_CanCurrentlyBeUsed
    playbook = LoadPlaybook(abilityId)
    for each TUILE in <tiles enumerator @state+0x68>:       # = GenerateActionTiles (tuiles de MOUVEMENT)
        if valid(TUILE, ability):                           # FUN_18000c1b0(0x3f, ...)
            bucket_tile = playbook.Evaluate(unit, TUILE)     # = EvaluateInternal, caster = TUILE
            accumulator.Merge(bucket_tile)                   # Bucket.Merge @1813fc790
    if count(tiles) == 0:                                   # SEULEMENT si AUCUNE tuile de mouvement
        if playbook.CanHandleNullCasterTile:
            accumulator.Merge(Evaluate(unit, NullPosition))  # evalue sur place
    playbook.ResetCaches()
action = accumulator.ChooseAction()                         # @1813fc0d0 — APRES toutes les abilities
```

> **Correction #128** : l'accumulateur est créé **UNE fois avant** la boucle d'abilities et
> `ChooseAction` n'est appelé **qu'une fois après** l'avoir épuisée (lu ligne à ligne dans
> `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` :
> le `Bucket` vit à `state+0x48`, alloué à l'état 0). ⇒ l'argmax est **INTER-ability** par utilité,
> il n'y a PAS de « première ability qui sort gagne ». Le port (`ComparableAbilityGenerator.generate`,
> bucket unique) est donc structurellement fidèle. La version précédente de ce pseudo-code (un
> accumulateur PAR ability) était fausse.
>
> **Corollaire #128, mesuré live** : la liste de tuiles vient de
> `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` = `IBattleQuery.slot+0xe` (tuiles de
> MOUVEMENT) + ajouts par playbook. `GetMovableTilesFor` **exclut la tuile courante** ; la branche
> `NullPosition` ne tire QUE si la liste est vide. ⇒ une unité qui a encore du déplacement **n'évalue
> PAS** l'action depuis sa tuile d'origine. Le port, lui, la consomme (elle est ajoutée EXPRÈS dans
> `attackPlans.ranked` par notre hook) → sur-génération de candidats. Preuve chiffrée et périmètre :
> `docs/rl/case-128-tile-elevation-utility.md` §5.

- **`Bucket.Merge`** = `AddAction(dest, src.action)` (argmax, `>` strict → premier sur égalité) + fusion
  récursive de l'arbre `SortedList<Key, sous-Bucket>`.
- **`ChooseAction`** = renvoie l'action-top **si LÉGALE** (`FUN_18004cc80`), sinon retombe sur
  `ChooseActionFromBuckets` (les sous-buckets), sinon null.
- **Tie-break global** : `>` STRICT partout ⇒ à utilité égale, **la PREMIÈRE (tuile, cible) énumérée
  gagne** (ordre de l'énumérateur de tuiles @0x68).

⇒ **Le modèle du moteur (sweep `tuile × cible` + argmax) EST structurellement le natif.** La correction
n'est donc PAS l'architecture mais le **terme de tuile** : le natif score chaque (tuile, cible) via
`CalculateActionUtility` = `predictionUtil + CalculateUtilityFromPredictions + CasterPositionUtility[=0]
+ key-0x36(UtilityAttackCase) + Tile(7)[≈0 plat]` — **PAS** `move.move_utility`.

**Les 2 termes restants — RE'd (dernière brique de (b), CLOSE) :**
- **`CalculateUtilityFromPredictions @181407890` (+0x48)** = `Σ` des utilités d'**événements prédits** au
  tile candidat : `Σ CalculateUtilityFromDamageEvent` (Weight[Damage=34]) + `Σ CalculateUtilityFromHealEvent`
  (Weight[Heal=44]) + `Σ` effet (Weight[AddedTileEffects=45] × proba) + `Σ` repair (Weight[Repair=46]).
  ⇒ **pour une ATTAQUE, ce terme VARIE par tuile** (les prédictions de dégât dépendent des cibles
  atteignables/à portée depuis chaque tuile → l'IA préfère les tuiles qui tuent/frappent plus). ⇒ **pour un
  SELF-HEAL, il est CONSTANT** (`CalculateUtilityFromHealEvent(self, montant fixe)`, indépendant de la tuile).
- **key-0x36 = UtilityType 54 = `WireweaveNet_FirstAttack`** (dump.cs gqfc5mff6c ; le label journal §13.1
  « position du caster » était une **inférence fausse**). Son `Evaluate` (`MoveNext @1810f76f0`) est gaté :
  cible **adjacente** ET cible **possédant l'effet 1111 (0x457, WireweaveNet)** → sinon **`return 0`**.
  ⇒ **= 0 pour tout ce qui n'est pas une attaque WireweaveNet** (donc 0 pour un heal).

**Conclusion du (1,2) (DÉFINITIVE)** : pour un **self-heal sur carte plate**, TOUS les termes de
`CalculateActionUtility` sont **constants/nuls par tuile** (predictions=constant, CasterPositionUtility=0,
WireweaveNet=0, Tile7≈0). ⇒ la tuile-caster est un **tie-break pur** → la **PREMIÈRE tuile de mouvement
énumérée** (ordre de l'énumérateur @0x68) gagne. Le `(1,2)` est un **artefact d'ordre d'énumération**, PAS
un choix d'engagement. ⇒ **`move.move_utility` (qui récompense l'engagement) est DÉFINITIVEMENT unfaithful**
pour la tuile d'un soin tile-indépendant.

**Implication moteur (fidélité)** :
- **Abilities tile-DÉPENDANTES (attaques)** : le terme de tuile fidèle = `CalculateUtilityFromPredictions@tuile`
  (dégât/kill prédit par tuile) `+ Tile(7)@tuile`, PAS `move.move_utility`. La tuile discriminée = celle qui
  maximise le dégât/kill prédit (déjà portable via la prédiction de dégât existante).
- **Abilities tile-INDÉPENDANTES (self-heal/self-buff)** : le natif **n'a aucune préférence de tuile** ; la
  tuile émise = première énumérée. Tenter de la matcher via `move_utility` est unfaithful ET vain (wash) ;
  pour l'agreement exact il faudrait répliquer l'ordre d'énumération des tuiles de mouvement (@0x68), sinon
  accepter que la tuile est arbitraire (seule l'ability + le fait que c'est un move+heal comptent).

### 2.4 Modèle générique des feuilles (à porter)

`score(case) = Σ_{candidat énuméré} [ gate(candidat) ? Σ weightKeys_applicables(candidat) : 0 ]`, avec
`weight = playbookWeights[key]` (int, défaut 0) → Fix64. **Par-ability = uniquement** (a) le gate
(effet/trait/faction/adjacence + ids), (b) l'énumération (quel ensemble cibles/tuiles), (c) les clés de
poids + l'arithmétique. Tout le reste (scaffolding itérateur, `GetUtilityValue`, layout source) vit dans
la base. Cf. `playbooks.md`.

## 3. Architecture d'override (la raison de réimplémenter)

L'IA native est une boîte noire **non-surchargeable** ; la réimplémentation rend chaque décision
**modifiable**. Trois granularités, séparées du base fidèle :

| portée | mécanisme | exemple |
|--------|-----------|---------|
| **par-ability** | remplacer l'entrée du registre `PLAYBOOKS[abilityType]` | réécrire le scoring de `MasterOfTheTutelaries` |
| **par-poids** (Comparable only) | patcher un poids `Utilities` (0 code) | monter `w_dmg`, baisser `w_heal` |
| **global / transverse** | un *modifier* appliqué à TOUT score | pénaliser toute tuile dans un overwatch (blindspot connu) |

```python
faithful = Engine()                                            # clone validé vs natif (agreement ~100%)
improved  = Engine(overrides=[OverwatchPenalty(), AggressiveBias()])   # déviations VOULUES, traçables
```

- Le **base** reste mesuré contre l'IA native → baseline de fidélité honnête (`status.md`).
- Les **overrides** sont des deltas **opt-in** et **traçables** (« cette décision diffère du natif
  PARCE QUE le modifier X »). Sans cette séparation, un override polluerait la métrique de fidélité :
  on ne saurait plus si un désaccord = bug de portage ou amélioration volontaire.

Débloque : corriger les faiblesses (overwatch-suicide, sur-extension), générer des variantes
(aggressive/defensive → diversité du dataset IL), faire de l'A/B natif-fidèle vs amélioré.

## 4. Ce qui RESTE / est OUVERT (spine)

- **`order_strategy` de `PickNextUnit`** : modèle posé (8 buckets §2.1). À raffiner uniquement si
  l'agreement le réclame — le harnais compare déjà la MÊME unité (`activatedUnitId`), donc
  l'ordonnancement n'est PAS la cause des misses attaque-vs-move connus. Un ordre raisonnable suffit
  tant que le scoring par-action domine.
- **OUVERT (scale, → `scoring.md`)** : homogénéité numérique `tile_util` (centaines : MaxDistEnemies,
  MinDist −100) vs `U_damage` (KillUnit 50/100 + DamageDealt brut, magnitude inconnue — config Damage
  absente du BC). SEULE inconnue numérique restante de l'argmax move-vs-attaque ; à caler par
  l'agreement une fois `tile_util(tuile d'attaque)` ajouté au moteur.
