# #287-r11-r2 — l'étage EXISTAIT, c'est l'AIGUILLAGE qui manquait (1076), et trois ids qui restent

Dettes réelles **4 → 3**, re-dérivé des deux côtés par `probe_287r5_etages_bloquants.py` (le
recensement est la vérité courante, pas cette page — le re-jouer).

| id | ability | porteur | étage demandé | état |
|---|---|---|---|---|
| 1076 | `MV71SniperDroneSquadAttack` | `tauMarksman` (pool) | `IsMeleeAttack` + `PickTile` | **déjà porté** — c'est le DISPATCH qui manquait |
| 1164 | `MindControl` | `genesMagus` (pool) | slot `0x7c` + prédicat statique | slot **RÉSOLU**, prédicat **ILLISIBLE** |
| 1101 | `AttemptedPossession` | `thousSorcerer` (pool) | `GetChildren` + `GetPreferredAttackTarget` | corps **LU**, étage de SIMULATION non porté |
| 1213 | `DeathOnTheWind` | `darkaStormSpeeder` (**hors pool MoW**) | `GetNumAttacksReceivedThisTurn` | étage porté, **SEEDING** absent |

Cinquième tranche de suite où l'étage préexiste — et cette fois la nuance est ailleurs : pour
`1076`, ce n'était même pas le call-site, c'était **le porteur qui appelait le mauvais corps**.

## 1. Le trou : `1076` EST une attaque normale, et le port n'a qu'UNE règle d'attaque normale

`1076 MV71SniperDroneSquadAttack` est l'attaque **NORMALE** de `tauMarksman` (posée par
`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` depuis le passif
`MV71SniperDroneSquad`). Le porteur que la cascade du port consulte pour une attaque normale est
donc `targeting._NormalAttackTargeting`, dont la règle-délégué appelait **toujours**
`normal_attack_dynamic_invalid_target_reason`, mirror de la BASE
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`
(« une arme existe »).

Or le natif lie `options+0x38` au slot de vtable `+0x480` de **l'INSTANCE**, et
`MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason` **surcharge** ce slot sans jamais
rappeler la base. `tauMarksman` a des armes ⇒ le port rendait `0` **partout**. Dégradation
PERMISSIVE, sans erreur ni crash.

⚠ **Ce n'est pas un oubli de table, c'est un axe manquant.** Le port avait déjà la table
`NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE` (#419-r1-tr14-r5-r2-r1-r2) : les *options* dépendent du
type concret depuis longtemps. La *règle-délégué*, elle, n'en dépendait pas — alors que le natif
les tient toutes deux du même objet.

L'aiguillage posé est **DÉRIVÉ**, pas une table à tenir : `"get_dynamic_invalid_target_reason" in
klass.__dict__` — le mirror exact de « l'instance a-t-elle surchargé le slot ? ».
`getattr` aurait remonté la MRO et vu le défaut d'`ActiveAbility`, donc aiguillé **tout le monde**
vers un `return 0` permissif. Mesure qui rend l'aiguillage sûr plutôt que supposé : sur les
**18** types de la table, **1076 et lui seul** déclare le corps (étage 1 de la garde, qui rougit le
jour où un autre entre — pour qu'on le CONFRONTE au lieu de le câbler en silence).

## 2. Le corps natif, verbatim

`MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason(caster, casterTiles, target, targetTiles)` :

    entities = default(AbilityEntities);          // memset 0x128
    entities.<+0x08> = caster; entities.<+0x10> = target;
    entities.<+0x18> = caster; entities.<+0x48> = casterTiles;
    if (!IsMeleeAttack(entities) && target != null
        && PickTile(entities, pickFirst: true) == null)
        return 1;                                 // = TargetingRule.ValidRequest
    return 0;

`MV71SniperDroneSquadAttackAbility$$PickTile(entities, pickFirst)`, dont les trois slots
d'interface sont lus dans `data/symbols/<build>/metadata/interface_slots.tsv` (jamais devinés — la
leçon de #287-r11-r1) :

    IBattleQuery   103  GetSurroundingTiles            6
    IBattleQuery   171  GetUnitMaxRange                1
    IBattleQuery   196  IsTargetInAttackRangeForSummon 4

    unitId = GetStringConstant(cfg@0x60, 0)                       // tauSmnDroneSniper
    range  = battleQuery.GetUnitMaxRange(unitId)                  // slot 171 -> 4
    list   = new List<ITile>()
    tiles  = battleQuery.GetSurroundingTiles(GetTiles(entities.target), range,
                                             onlyEmptyOrSteppable: 0, onlyWalkable: 1,
                                             onlyMovable: 0, includeCenter: 1)      // slot 103
    foreach (t in tiles)
        if (!list.Contains(t) && t.IsFreeTile(state, true, null, false)
            && !t.IsTilePendingDrafting(state, null)
            && battleQuery.IsTargetInAttackRangeForSummon(entities.caster, unitId, t,
                                                          entities.target))          // slot 196
        { if (pickFirst) return t; list.Add(t); }
    // enumeration terminee : SortTilesByUtility(...) -> First -> SelectTile ; si null, le REPLI
    // `HasTooManySummons` (tuile du drone le plus faible, filtree par
    // `DSLSelectors$$FilterTilesIfCanAttackTargetTileFrom`).

### Deux lectures que la conversion oblige à faire

* **Le code rendu est le littéral `1 = TargetingRule.ValidRequest`**, PAS `2
  TargetMatchesDynamicRule` comme toutes les autres règles dynamiques portées. C'est le même
  emploi « code de refus » que la tête de domaine TUILE du filtre statique
  (`targeting_rule_inventory`, rôle `REASON`). Recopier `2` par analogie aurait écrit un code FAUX
  que la cascade propage tel quel — et **l'oracle live l'a confirmé** : `0x1 [ValidRequest]`.
* **`PickTile(pickFirst: true)` n'est PAS « la première tuile de l'anneau »** : c'est le MÊME corps
  que l'exécution, **REPLI COMPRIS**. Quand aucune tuile candidate ne passe le filtre, le natif
  poursuit sur le bloc `HasTooManySummons`. Un port qui aurait court-circuité à « anneau vide ⇒
  refus » aurait SUR-refusé au cap. `_pick_tile` faisait déjà passer les deux modes par ce repli —
  la conversion n'a eu à ajouter aucune branche.

L'ORDRE d'énumération de `GetSurroundingTiles` (non RE'd) n'a **aucune** incidence : le gate ne
teste que la NULLITÉ du retour, jamais QUELLE tuile est rendue.

### `IsMeleeAttack` est un FOYER, pas deux prédicats

`DSLTriggers$$IsMeleeAttack` (surcharge 4 arguments) construit un
`IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger` — le nom porte l'axe INVERSE, et c'est
le natif qui l'écrit : `MV71SniperDroneSquadAttackAbility$$HasAttackType` en tire les deux sens
(`type == 1` ⇒ `AbilityTrigger$$op_LogicalNot(IsMeleeAttack(...))`).

Le natif appelle la **MÊME méthode** dans `ExecuteBehaviour` (dispatch mêlée) et dans son gate. Le
port l'a donc extraite en un foyer `_is_melee_attack`, que `execute_behaviour` consomme désormais :
sans lui, le dispatch d'exécution et le gate de ciblage pouvaient diverger. Un étage de la garde
lit le source d'`execute_behaviour` pour le tenir.

## 3. Confrontation LIVE, avec attribution

`probe_287r11r2_mv71_gate_live.py` — géométrie **PLACÉE**, board **CHOISI** pour elle, attribution
par **désarmement** (jamais par le code rendu : `ValidRequest` sert aussi ailleurs).

`GetUnitMaxRange(tauSmnDroneSniper)` = **4** : saturer un disque r=4 demande 60 unités sur un board
ordinaire. Le balayage des **779** boards de `data/boards/` donne `MC1_01` (5×7, 25 tuiles
marchables), dont la tuile `(4,6)` n'a que **8** tuiles marchables dans son disque r=4 —
`(0,4) (1,5) (1,6) (2,6) (3,3) (3,6) (4,3) (4,4)`. Huit occupants suffisent, et le caster en est un.

| montage | cibles | verdicts natifs | refus attribués à la règle | sur-refus | SOUS-refus | vue rouge (témoin) |
|---|---|---|---|---|---|---|
| `sature` | 6 | `{0x1: 1, 0x0: 3, 0x8000000: 2}` | **2** (les deux porteurs) | **0** | **0** | **2 SOUS-refus** |
| `une-tuile` | 6 | `{0x0: 4, 0x8000000: 2}` | 0 | **0** | **0** | 0 |

**12 cibles, 0 sur-refus, 0 sous-refus.** Non-dégénérescence : `{0x1: 1, 0x0: 7, 0x8000000: 4}` —
les deux verdicts sont exercés.

⚠ **DEUX porteurs sont confrontés au MÊME oracle, et c'est le point** : `classe`
(`ABILITY_CLASSES[1076]()`, voie de `turnflow.can_use_ability`) et `normale`
(`_NormalAttackTargeting`, voie de `valid_normal_attack_targets`). Mesurer un seul des deux aurait
laissé l'autre en dette — et c'est la seconde qui était fausse.

### La bascule ne déplace QU'UNE unité

`sature` → `une-tuile` : l'allié de `(3,6)` part en `(2,2)`, hors du disque. MÊME caster, MÊME
cible, MÊME distance (2), MÊME ligne de vue ; le disque passe de **0** à **exactement 1** tuile
libre et le natif bascule `0x1` → `0x0`. Le décideur est le **COMPTE**, pas la distance.

`(3,6)` est la tuile libérée, et le choix n'est pas indifférent : elle est **adjacente à la cible**,
donc le volet LIGNE DE VUE d'`IsTargetInAttackRangeForSummon` (que le port COLLAPSE) n'a aucune
tuile intermédiaire à examiner. Libérer une tuile lointaine aurait exposé le collapse et mélangé
deux causes.

### Aucun ennemi adjacent au caster, et c'est délibéré

Le masque de 1076 porte `forceMeleeTarget = RangedBool.IfRangedCaster` : un ennemi au contact ferait
clamper la portée à 1 par `ShouldApplyRangedInMelee`, et la cible à d=2 serait refusée par
`TargetIsInRange` — un AUTRE bit, qui masquerait la règle. Les quatre bloqueurs adjacents au caster
sont donc des **alliés**. Le board impose d'ailleurs le partage : `MC1_01` n'a que **3** spawns
côté joueur (12 côté adverse).

## 4. La garde

`tests/engine/test_287r11r2_mv71_gate_offline.py`, **14 tests / sept étages** : recensement (dont
« 1076 est le SEUL type d'attaque normale à déclarer le corps ») ; le code `ValidRequest` figé ; la
bascule offline avec distance invariante ; le **bras MÊLÉE** qu'aucun montage live ne produit ;
l'aiguillage (et sa non-régression sur un caster générique, confrontée au foyer de la base) ; le
rayon dérivé du catalogue sous mutant de `GC.unit` ; les mutants en DELTA.

Vue rouge sur l'arbre témoin (`git archive` de `af7c0f5a`, arbre **complet** — les caches lazy du
gameconfig doivent voir les mêmes entrées) : **8 failed / 6 passed** ; **14 passed** après.

⚠ Les deux symboles NEUFS (`_is_melee_attack`, `mv71_dynamic_invalid_target_reason`) sont importés
**DANS** leurs tests, pas en tête — sinon la COLLECTE échoue sur le témoin et la vue rouge se réduit
à une ligne.

Les 6 verts du témoin sont nommés : la géométrie du substrat, les deux étages du RAYON (acquis
antérieurs), le bras `target == null`, et deux étages qui attendent `0` — **structurel**, le témoin
étant PERMISSIF.

## 5. Ce qui n'est PAS couvert

* **Le bras MÊLÉE n'est pas exercé live** : il faudrait saturer le disque d'une cible AU CONTACT du
  caster, et `MC1_01` ne l'autorise pas (les deux voisines marchables du caster sont dans le disque
  de la cible). Couvert **offline**, avec la vérification que le disque EST bien saturé — sinon le
  `0` viendrait de `PickTile` et non du court-circuit.
* **Le régime `GetUnitMaxRange` = 0 ou 1** n'est pas exercé live (le drone a une arme de portée 4).
  Couvert offline sous substrat fabriqué, qui **assertionne d'abord que le catalogue ne l'exerce
  pas**.
* **Le repli `HasTooManySummons`** (au cap de 3 drones) n'est exercé ni live ni offline dans cette
  tranche : le gate ne l'atteint que si l'anneau est vide ET que trois drones sont déjà posés.
  C'est le même corps que l'exécution, déjà confronté par `#61bis`.
* **Le volet CASTER** (`options+0x30`) : inchangé, 1076 ne pose pas `CasterMatchesDynamicRule`.
* **Deux rouges PRÉ-EXISTANTS**, reproduits à l'identique sur `af7c0f5a`, donc hors de cette
  tranche : `test_loki_solo_targeting_live.py::test_1151_the_quickening_targeting` (1 failed) et
  `test_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule_live.py` (6 errors — montage
  « aucun `genesSmnDecoy` vivant ADJACENT a un ennemi »).

## 6. Les trois ids qui restent, et COMMENT leur étage a été lu

### 6.1 `1164 MindControl` — le slot est RÉSOLU, le prédicat reste ILLISIBLE

    tiles = battleQuery.<slot 0x7c>(targetTiles, friendsOf: caster, enemiesOf: null,
                                    ignoreSteppables: false)
    ListExtensions.FilterInPlace(tiles, <Func<T,bool> statique de `MindControlAbility.<>c`>)
    return tiles.Count != 0 ? 0 : 2

Le slot `0x7c` = **`IBattleQuery 124 GetAdjacentUnits/4`**, lu dans
`data/symbols/<build>/metadata/interface_slots.tsv` — la case-doc `#287-r4-r1` le laissait en
« slot 0x7c », non résolu. Le port a déjà le mirror (`targeting.get_adjacent_units`).

Reste **le prédicat**, et il est vraiment illisible : `MindControlAbility.<>c` cache un
`Func<T,bool>` **sans capture** dont le corps est **DÉDUPLIQUÉ**. Il n'apparaît ni dans
`ghidra/functions.tsv` (indexée par adresse) ni dans `frida/methods.tsv` (0 RVA répétée) — alors
que **7** autres lambdas `<GetDynamicInvalidTargetReason>b__0` y figurent.
`MindControlAbility$$ExecuteBehaviour` fait deviner (`Attackable(Friends(Self, AdjacentUnits(Target)))`,
et `DSLSelectors$$Attackable` = `UnitsWithoutTrait(0x1b Steppable)`) — mais **deviner n'est pas
lire**, et un prédicat faux ici refuserait des casts que le natif accepte.

**Point d'ancrage à ouvrir** : le bundle n'expose aucun moyen de nommer les méthodes d'une classe
IMBRIQUÉE. `resolveMethodPtr` prend `(ns, cls)` et `findClassAnywhere` rend le **premier** `<>c` du
namespace — donc une réponse fausse sans le dire. Il faut un RPC qui énumère par **type
déclarant** (ou qui accepte un `Il2CppClass*` obtenu par `class_get_nested_types`). C'est un
capteur, donc une fenêtre de reinject. NON PORTÉ, et le `0` du port reste permissif.

### 6.2 `1101 AttemptedPossession` — corps LU, étage de SIMULATION non porté

`AttemptedPossessionAbility$$GetDynamicInvalidTargetReason` (mirror du décompilé) :

    unit = UnitExtensions.GetUnit(target, state);   if (unit == null) return 2;
    vivants = UnitExtensions.GetChildren(unit, state, e => UnitExtensions.IsAlive(e, state));
    if (vivants.Count == 0 && UnitExtensions.HasTrait(target, 0x19)) return 2;
    tous = UnitExtensions.GetChildren(unit, state, null);
    if (tous.Count < 1 && GetPreferredAttackTarget(caster, unit) == null) return 2;
    return 0;

(le prédicat `e => IsAlive(e, state)` est ici une méthode d'INSTANCE de l'ability —
`AttemptedPossessionAbility$$<GetDynamicInvalidTargetReason>b__3_0` — donc nommée dans les deux
tables, contrairement à celui de `1164`.)

L'étage bloquant est le **troisième bras** : `GetPreferredAttackTarget` appelle une méthode
générique du service `this+0x40` avec `(possessedUnit, 0x4b9, <closure {possessedUnit, this}>,
<clé du caster>)` — la couche de SIMULATION d'effet. Ni `GetChildren` ni ce service n'ont de mirror
côté port. **NON PORTÉ** ; le porteur `thousSorcerer` est pourtant AU POOL, donc la tranche est
confrontable dès que l'étage existe.

### 6.3 `1213 DeathOnTheWind` — le SEEDING, toujours, et le porteur n'est PAS spawnable

    unit = UnitExtensions.GetUnit(target, state);  if (unit == null) return 0;
    return EntityExtensions.GetNumAttacksReceivedThisTurn(unit) != 0 ? 0 : 2;

Inchangé depuis `#287-r4-r1` §9.3 : le compteur (`UnitComponent.times_attacked_this_turn`) et son
reset sont portés, mais `load_state` ne le **seede** pas — porter la règle refuserait des cibles que
le natif ACCEPTE. Deux faits mesurés dans cette tranche s'y ajoutent :

* **aucun hook du bundle ne publie ce compteur** — `timesAttacked` / `AttacksReceived` : **0**
  occurrence dans `frida/**`. Il n'existe donc pas de capteur existant à réutiliser ; c'est bien une
  fenêtre de reinject (point d'ancrage : `EntityExtensions$$GetNumAttacksReceivedThisTurn`, à
  publier dans `combatSnapshot`) ;
* **`darkaStormSpeeder` n'est pas dans les 8 MoW spawnables** du pool rank 17 — la confrontation
  demanderait en plus une injection catalogue.

## 7. Chiffres, re-dérivés des deux côtés

| | avant #287-r11-r2 | après |
|---|---|---|
| règle ÉVALUABLE par le port (surcharge/table) | 35 | **36** |
| aucune règle (le `0` permissif) | 34 | **33** |
| dont **dette réelle** (surcharge native lisible) | **4** | **3** |
| dont `0` coïncidant avec le corps de base | 30 | 30 |

Cliquets re-joués : `probe_181` **129/129, 0 manquante** ; `probe_429` OK ;
`probe_287r5` cliquet d'appariement OK (0 orphelin, 0 fantôme). Cette tranche n'ajoute **aucune**
entrée à `ABILITY_CLASSES` (1076 y était déjà, avec son masque et son `AbilityAttackType`).

## 8. Résidu `#287-r11-r2-r1`

**Le gate de ciblage de `1076` hérite du COLLAPSE de `IsTargetInAttackRangeForSummon`, et l'écart
est RESTRICTIF côté natif — donc PERMISSIF côté port.** Le corps natif (slot 196), LU :

    if (target == null || !UnitExtensions.IsTargetable(target)) return false;
    range = max(w.Range ?? 1 for w in GetUnitConfig(unitId).Weapons);
    if (DamageCalculations.ShouldApplyRangedInMelee(parent, [tile], state, true)) {
        range = 1; if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false;
    } else if (range == 1 && !TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false;
    if (GetDistance(tile, target) > range) return false;
    foreach (t in GetTiles(target))
        if (!<slot 0x10>(tile, t, 6, 2).IsNullOrEmpty()) return false;      // LIGNE DE VUE
    if (range == 1) return DamageCalculations.CanMeleeAttackOverElevationDifference(tile, GetMainTile(target));
    return true;

Le port collapse tout cela en `1 <= distance(tile, cible) <= range` (`_pick_tile`). Tant que
`PickTile` ne servait qu'à l'EXÉCUTION, le collapse ne coûtait qu'une tuile de spawn parfois
différente ; il **décide maintenant de la légalité d'un cast**. Une tuile que le natif rejette pour
LIGNE DE VUE (ou pour `CanMeleeAttackOverElevationDifference`) est comptée valide par le port, qui
ACCEPTE alors une cible que le natif REFUSE — un **SOUS-refus**. Le montage `une-tuile` a été
conçu pour l'éviter (tuile adjacente à la cible), donc la mesure de cette tranche ne le voit pas ;
il faut un montage où la seule tuile libre du disque est **masquée** par du terrain.
Étage manquant : le mirror de `<IBattleQuery slot 0x10>(from, to, 6, 2)` (la même famille que
`GetTilesObscuringTerrain`, déjà portée pour `TargetIsUnobscured` — à confronter avant réemploi).
