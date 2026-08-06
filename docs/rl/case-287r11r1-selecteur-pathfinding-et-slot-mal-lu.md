# #287-r11-r1 — trois règles de plus, et le « slot non résolu » qui n'en était pas un

Dettes réelles **7 → 4**, re-dérivé des deux côtés par `probe_287r5_etages_bloquants.py` (le
recensement est la vérité courante, pas cette page — le re-jouer).

| id | ability | porteur | canal | étage demandé | état de l'étage |
|---|---|---|---|---|---|
| 1016 | `SendInTheNextWave` | `astraYarrick` (pool) | surcharge | `GetSurroundingTiles` + `GetUnitMaxRange` | **partiellement** porté |
| 1180 | `HeroicFusillade` | `genesKelermorph` (pool) | surcharge | `GetMinDistance` + `IsInMovementRange` | **déjà porté** |
| 1197 | `ExcruciatingFrequencies` | `emperNoiseMarine` (pool) | table | sélecteur DSL (`TilesBehindInLine`) | **déjà porté** |

Quatrième tranche de suite où l'étage préexiste : pour `1180` et `1197`, **seul le call-site
manquait**. `1016` est la nuance — son étage manquait d'un BRAS (`onlyEmptyOrSteppable`) et d'un
mirror (`GetUnitMaxRange`), qui ferme au passage un hardcode.

## 1. Ce qui bloquait vraiment `1016` : un SLOT MAL LU, pas un étage manquant

Le port portait cette note, et elle est **fausse dans sa conclusion comme dans sa méthode** :

> `SendInTheNextWaveAbility$$GetDynamicInvalidTargetReason` … appelle le slot 0x66 de `IBattleQuery`
> … Le slot 0x66 n'est pas résolu (aucune lambda du décorateur
> `RecordedSimulationRequestsBattleQuery` ne l'a donné), donc la méthode n'est PAS surchargée.

Le décompilé du build courant écrit `+ 0x67`, et la table de MÉTADONNÉE
(`data/symbols/<build>/metadata/interface_slots.tsv`, lue dans le champ `slot`
d'`Il2CppMethodDefinition`) donne directement :

    IBattleQuery   103  GetSurroundingTiles   6
    IBattleQuery   111  GetMinDistance        2
    IBattleQuery   171  GetUnitMaxRange       1
    IMovementQuery  13  IsInMovementRange     4
    ITargetsSelector 2  Count                 1

Chercher une lambda de proxy n'était pas la bonne voie : elle ne rend un nom que si le décorateur
`RecordedSimulationRequestsBattleQuery` a un site pour ce slot, et son absence se lit à tort comme
« non résoluble ». La table, elle, répond toujours — **et départage les homonymes** : le slot 111
est `GetMinDistance`, PAS `GetDistance` (qui occupe 108/109/110). Les confondre aurait donné une
distance entre deux TUILES là où le natif prend le MIN sur deux EMPREINTES, et surtout aurait perdu
le sentinel **-1** qui désarme la règle sur substrat vide.

## 2. Les trois corps, verbatim

`SendInTheNextWaveAbility$$GetDynamicInvalidTargetReason` :

    range = GetSpawnedUnitRange();                       // = GetUnitMaxRange(GetStringConstant(0x0 unitId))
    tiles = battleQuery.GetSurroundingTiles(targetTiles, range,
                                            onlyEmptyOrSteppable: 1, onlyWalkable: 1,
                                            onlyMovable: 0, includeCenter: 1);      // slot 103
    return tiles.Count() < 1 ? 2 : 0;                    // ICollection<ITile>.get_Count (slot 0)

`HeroicFusilladeAbility$$GetDynamicInvalidTargetReason` :

    dc.range = GetNumberConstant(0x16 range);                                       // = 2
    tiles = battleQuery.GetSurroundingTiles(targetTiles, 1, 0, 1, 0, 1);            // slot 103
    list  = tiles.Where(t => movementQuery.IsInMovementRange(dc.caster, t, ignoreUnitFlags: 1,
                                                             { overrideRange = dc.range })).ToList();
    if (battleQuery.GetMinDistance(targetTiles, casterTiles) < 2) return 0;         // slot 111
    return list.Count == 0 ? 2 : 0;

`ExcruciatingFrequenciesAbility$$GetDynamicInvalidTargetReason` :

    entities = default(AbilityEntities);                 // memset 0x128
    entities.caster = caster; entities.target = target; entities.targetTiles = targetTiles;
    return GetAttackTargets().<vslot 24 = ITargetsSelector.Count>(entities) > 0 ? 0 : 2;

    GetAttackTargets = Enemies(Caster@0x48, Units(GetAffectedTiles(), unique: 1, type: 3), type: 3)
    GetAffectedTiles = SortReverse( TilesBehindInLine(CasterTile@0x50, TargetTile@0x78,
                                                     settings{+0x10 = 1, +0x11 = 1},
                                                     Direct(GetNumberConstant(0x17 nrOfTiles))) )

`2` = `TargetingRule.TargetMatchesDynamicRule`.

### Les offsets de `DSLSelectors` sont LUS, pas déduits

`DSLSelectors$$InitializeShared` alloue les sélecteurs partagés, et Ghidra mislabelle **tous** leurs
ctors (`Mono.Btls.MonoBtlsX509VerifyParam$$.ctor`, corps dédupliqué `(this, state)`) : le nom ne dit
rien. Ce qui les identifie, ce sont deux getters de `DSLTriggers` dont le corps entier est un
`AreEqual` :

    get_CasterIsCasterTile = AreEqual(DSLSelectors+0x48, DSLSelectors+0x50)   -> +0x48 = Caster (ENTITE)
    get_OwnerIsTargetTile  = AreEqual(DSLSelectors+0x78, AbilityEntities+0x30) -> +0x78 = TargetTile

Les prendre pour des offsets de `DSLFactory` (`0x160 Caster`, `0x178 Target`) aurait interverti deux
rôles sans rien casser visiblement.

### Le vslot 24 est `Count`, et c'est sa SIGNATURE qui le dit

Ghidra rend l'appel comme un dispatch virtuel anonyme sur `klass->vtable[0x18]`. Ce qui l'établit :
les **six** call-sites de ce slot dans le binaire passent tous un `AbilityEntities` **par valeur** et
comparent le retour à `0`/`1` — dont `DoomboltAbility$$GetDynamicInvalidCasterReason`, dont le corps
entier est `Count(GetTargets(), entities) < 1 ? TargetIsInRange : 0`. Et `ITargetsSelector` n'expose
qu'**une** méthode à 1 paramètre rendant un `int` : `Count`.

## 3. `1016` — `includeCenter = 1` et `onlyEmptyOrSteppable = 1` vont ENSEMBLE

C'est le second est ce qui rend le premier inoffensif : le centre est la tuile de la CIBLE, donc
occupée, donc rejetée par `IsEmptyOrSteppable` — **sauf si la cible porte le trait `Steppable`
(0x1b)**, auquel cas le natif la compte vraiment. Retirer le centre « parce qu'il est occupé » aurait
été une simplification fausse, invisible partout sauf sur ce régime.

⚠ **Ce n'est PAS le même ensemble que `GetSpawnTilesSelector`** (l'`ExecuteBehaviour`), et les
confondre aurait produit un SUR-refus. Le sélecteur de spawn passe par
`CanAddUnit(SurroundingTiles(target, includeCenter: 0, r))` : `CanAddUnit` ajoute trois rejets
(blocker, `NotWalkable`, tuile RÉSERVÉE) et EXCLUT le centre. Le gate de ciblage est donc
strictement **plus permissif** que ce que l'ability saura utiliser — il existe une configuration où
le cast est légal et ne pose rien. Le natif l'assume ; le port aussi.

### Le hardcode qui tombe, et pourquoi il tenait

`SITNW_SPAWNED_UNIT_RANGE = 2` était justifié par « le service de config d'unités n'est pas exposé
offline ». C'était vrai du **service** et faux de la **source** : `GetUnitMaxRange` passe par
`BattleQuery$$GetUnitConfig`, donc par le CATALOGUE, que `gameconfig` porte. Le mirror
`services/battle_query.get_unit_max_range` le lit ; il n'y a plus qu'un foyer, partagé par la règle
de ciblage et par `GetSpawnTilesSelector`.

Trois lectures que la conversion oblige à faire, et qui ne se devinent pas :

* une arme **sans** `Range` vaut **1** (`HasValue ? Value : 1`), pas 0 ni « ignorée » ;
* une unité **inconnue** rend **0** — les deux `return 0` du haut de corps sont distincts de la
  boucle, et le port garde la distinction ;
* sur le gameconfig courant, `astraSmnGuardsman` = `[Physical(sans portée), Las(Range 2)]` →
  `max(1, 2)` = **2**, exactement la valeur que la constante portait. La conversion est donc
  value-preserving, et l'étage 2 de la garde le **FIGE** : `probe_313` compare des *mirrors*, jamais
  une valeur écrite au site.

⚠ **Le catalogue n'exerce PAS le bras « toutes les armes sans portée »** — mesuré, **aucune** unité
n'est dans ce cas. Un test dérivé du catalogue partait donc en `skip`, c'est-à-dire en invisibilité
(#455) : le substrat est FABRIQUÉ, et le test **assertionne d'abord que le catalogue ne l'exerce
pas**, pour se retourner le jour où il l'exercerait.

## 4. `1180` — le COURT-CIRCUIT, et ce qu'il faut ne PAS réutiliser

`GetMinDistance(targetTiles, casterTiles) < 2` rend `0` **avant tout test de chargeabilité** : une
cible déjà au contact est valide sans que rien d'autre ne soit évalué. Et le sentinel `-1` de
`GetMinDistance` (contre `int.MaxValue` de `MovementQuery$$GetDistance`) fait que **le vide DÉSARME**
la règle — la convention permissive du module y est obtenue par le mirror lui-même, pas par une garde
ajoutée.

⚠ **`_charge_candidate_tiles` n'est pas réutilisable ici**, malgré la ressemblance :

| | gate de CIBLAGE | pool de CHARGE (`ExecuteBehaviour`) |
|---|---|---|
| contenu | `onlyEmptyOrSteppable = 0` — les tuiles OCCUPÉES entrent | `CanAddUnit` — blocker / `NotWalkable` / RÉSERVÉE |
| centre | `includeCenter = 1` | exclu |
| filtre | `IsInMovementRange` seul | intersection avec le stop-set |

L'ordre du décompilé est de plus **inversé** : le `Where`/`ToList` est calculé AVANT le
court-circuit, qui ne le lit pas. Sans conséquence sur le verdict (le natif jette la liste), mais le
port ne doit pas en tirer que la distance filtre le pool.

## 5. `1197` — la cible est une TUILE, et le contexte natif est volontairement pauvre

Le natif ne remplit que **trois** champs de l'`AbilityEntities` (`caster` +0x08, `target` +0x10,
`targetTiles` +0x38 — offsets lus au `.ctor`, dont les noms de paramètres viennent de la métadonnée).
`casterTiles` (+0x48) reste **NUL**, donc `CasterTileSelector$$Select` retombe sur
`GetTiles(entities.Caster)` — l'empreinte COURANTE, ce que `CasterTile()` rend déjà côté port hors
balayage IA. Aucun écart.

⚠ **Le rôle `target` d'une entité TUILE n'est pas matérialisé** par `entities_from_state` : même
verrou et même parade LOCALE que `AlphaWarriorAbility` (#287-r8), pour la même raison — élargir le
foyer changerait les arbres des 5 abilities TILE-TARGET portées qui lisent aujourd'hui un `Target()`
nul. RÉSIDU `#287-r12`, inchangé.

## 6. Confrontation LIVE, avec attribution

`probe_287r11r1_regles_ciblage_live.py` — géométrie **PLACÉE** (`--place`/`--a-place`, jamais subie),
board **CHOISI** pour elle, attribution par désarmement sur les SUR-refus seuls, SOUS-refus compté à
part (il survit au témoin par construction — leçon de `case-287r8` §5).

| montage | id | cibles | verdicts natifs | refus reproduits | sur-refus | SOUS-refus | témoin |
|---|---|---|---|---|---|---|---|
| `1016` | 1016 | 2 | `{0x2: 1, 0x0: 1}` | **1** | **0** | **0** | 0 |
| `1016-une-seule` | 1016 | 2 | `{0x0: 2}` | 0 | **0** | **0** | 0 |
| `1180` | 1180 | 4 | `{0x0: 2, 0x2: 2}` | **2** | **0** | **0** | 0 |
| `1180-bloque` | 1180 | 4 | `{0x0: 3, 0x2: 1}` | **1** | **0** | **0** | 0 |
| `1180-libre` | 1180 | 4 | `{0x2: 3, 0x0: 1}` | **3** | **0** | **0** | 0 |
| `1197` | 1197 | 6 | `{0x2: 4, 0x0: 2}` | **4** | **0** | **0** | 0 |
| `1197-hors-ligne` | 1197 | 6 | `{0x2: 5, 0x0: 1}` | **5** | **0** | **0** | 0 |

**28 cibles, 0 sur-refus, 0 sous-refus, témoin désarmé à 0 partout.** Non-dégénérescence vérifiée
PAR ID : `1016` `{0x2: 1, 0x0: 3}`, `1180` `{0x0: 6, 0x2: 6}`, `1197` `{0x2: 9, 0x0: 3}` — les deux
verdicts sont exercés pour les trois.

### Le board de `1016` a été TROUVÉ, pas choisi

Saturer un disque de rayon 2 demande 18 unités sur un board ordinaire. Le balayage des **779** boards
de `data/boards/` donne `C4_05`, dont le coin `(0,0)` n'a que **4** tuiles jouables dans son disque
r=2 (`(0,0)`, `(1,1)`, `(1,2)`, `(2,1)` — `(1,0)` et `(2,0)` sont `ForceUnplayable`, `(0,1)` et
`(0,2)` sont `Block`). Trois unités suffisent alors.

### Quatre montages SÉPARENT le port d'un modèle plausible mais FAUX

Un accord obtenu là où deux modèles coïncident ne prouve rien. Ces quatre-là sont choisis parce que
le modèle naïf y donne l'autre réponse :

* **`1180-bloque` / `1180-libre`** — MÊME cible `(2,3)`, MÊME distance `d = 3`, MÊME
  `ring1min = 2` : seule la position des trois bloqueurs change. Natif **`0x2`** puis **`0x0`**.
  Un port qui aurait collapsé `IsInMovementRange` en `distance <= range` aurait accepté les deux :
  c'est bien le **PATHFINDING** qui décide, et l'attribution du refus au blocage est MESURÉE, pas
  supposée.
* **`1016` / `1016-une-seule`** — MÊME cible `(0,0)`, MÊME caster, **une seule unité déplacée** :
  le disque passe de 0 à exactement 1 tuile libre et le verdict bascule `0x2` → `0x0`. Le décideur
  est le **COMPTE**, pas la position ni la distance.
* **`1197-hors-ligne`** — l'ennemi de `(0,4)` est ADJACENT à l'aim `(0,3)` mais n'est pas sur sa
  ligne (la marche s'arrête au bord : `[(0,3)]`). Natif **`0x2`**. Un port qui aurait lu
  `GetAttackTargets` comme « les ennemis autour de la tuile visée » aurait accepté.

## 7. La garde

`tests/engine/test_287r11r1_regles_ciblage_offline.py`, **21 tests / six étages** : recensement ;
le rayon `1016` dérivé (avec mutant de SOURCE sur `GC.unit`) ; la bascule `1016` dont le bras
`Steppable` qu'aucun montage live ne produit, et le rayon mesuré PAR LA GÉOMÉTRIE ; le court-circuit
`1180` et la portée de mouvement ; le filtre `Enemies` et la borne `nrOfTiles` de `1197` ; les
mutants en DELTA.

Vue rouge sur l'arbre témoin (`git archive` de `58a9c183`, arbre **complet** — les caches lazy du
gameconfig doivent voir les mêmes entrées) : **13 failed / 8 passed** ; **21 passed** après.

⚠ **Les deux imports NEUFS sont faits DANS leurs tests, pas en tête** — et c'est la seule raison :
en tête, ils font échouer la **COLLECTE** sur le témoin, donc un rouge d'UNE ligne au lieu d'une
ventilation. La vue rouge publiée n'aurait montré aucun bras.

Les 8 verts du témoin sont nommés, et leur structure est celle de `case-287r11` §7 :

* deux mesurent le **SUBSTRAT** (géométrie de la ligne, connexité) — ils ne jugent aucune règle ;
* un est un **acquis antérieur** (les trois ids posaient déjà le bit au masque) ;
* les cinq autres attendent **`0`**, et c'est **STRUCTUREL** : le témoin est PERMISSIF, donc aucun
  substrat ne peut distinguer « accepte parce qu'il lit la bonne chose » de « accepte parce qu'il ne
  lit rien ». Ce sont les tests de REFUS qui portent le rouge, et c'est là que la garde mord.

⚠ **La géométrie de la ligne `1197` est DÉRIVÉE, jamais posée**, et le premier jet a rougi pour
l'avoir supposée : un board LIGNE (`row = 0`) tronque le rayon à UNE tuile, parce que
`cube(2,0) = (2,-1,-1)` alors que `cube(1,0) + (cube(1,0) - cube(0,0)) = (2,0,-2)`, soit l'offset
`(2,-1)`. Tous les bras seraient passés **par vacuité**, et le refus se serait lu comme « le port ne
trouve pas l'ennemi ». Un test garde désormais que la ligne est assez longue.

## 8. Chiffres, re-dérivés des deux côtés

| | avant #287-r11-r1 | après |
|---|---|---|
| règle ÉVALUABLE par le port (surcharge/table) | 31 | **34** |
| aucune règle (le `0` permissif) | 34 | **31** |
| dont **dette réelle** (surcharge native lisible) | **7** | **4** |
| dont `0` coïncidant avec le corps de base | 27 | 27 |

Cliquets re-joués : `probe_181` **104/104, 0 manquante** ; `probe_120` étape 0 « littéral de ctor
manquant : aucun » ; `probe_313` 32 mirrors en bijection, 0 dette ; `probe_287r4r1` OK (5/5 mutants
mordent) ; `probe_273 --only-scan` OK ; `probe_287r5` cliquet d'appariement OK.
Cette tranche n'ajoute **aucune** entrée à `ABILITY_CLASSES` (1016 et 1180 y étaient déjà avec leur
masque et leur `AbilityAttackType` ; 1197 reste hors registre, sa règle vit dans la table).

## 9. Ce qui n'est PAS couvert

* **Le bras `Steppable` de `1016` n'est PAS exercé en live**, et c'est mesuré : **aucune** unité du
  catalogue ne porte le trait (il vient des summons créés en jeu — decoys, spore mines). L'amener
  demanderait de caster l'ability d'un summoner puis de re-mesurer, ce que la mesure de ciblage ne
  fait pas. Couvert **offline** (étage 3 de la garde), pas live.
* **Le régime `GetUnitMaxRange` = 0 ou 1** n'est pas exercé live : le seul summon de `1016` est
  `astraSmnGuardsman`, de portée 2. Couvert offline sous substrat fabriqué.
* **`1197` : un ennemi ALIGNÉ au-delà de `nrOfTiles`** n'est pas exercé live — `C1_02` (5×7) ne porte
  aucune ligne assez longue depuis une position adjacente au caster. Couvert offline.
* **Le volet CASTER** (`options+0x30`, `CasterMatchesDynamicRule`) : inchangé, aucune règle portée.
* **Les 4 dettes restantes** sont recensées par `probe_287r5_etages_bloquants.py` : `1076`
  (`IsMeleeAttack` + `PickTile`), `1101` (SIMULATION), `1164` (ILLISIBLE, prédicat statique
  dédupliqué), `1213` (SEEDING, `#287-r5-r2`).
* **Deux rouges PRÉ-EXISTANTS** ont été rencontrés et **reproduits à l'identique sur `58a9c183`**,
  donc hors de cette tranche : `test_381r4_imperative_collapses_offline.py` (3 tests) et
  `test_heroic_fusillade_migration_live.py::test_g5_move_splash_crit_wiring` (1 test). Les quatre
  tournent autour de la même tuile de charge `(1,2)` — même gisement, à rapprocher de `#484`.

## 10. Résidu `#287-r11-r1-r1`

**Des slots d'interface déclarés « NON RÉSOLUS » par le port le sont par
`data/symbols/<build>/metadata/interface_slots.tsv`, et deux d'entre eux laissent une règle NON
PORTÉE.** Le gisement est celui que cette tranche vient de payer sur `1016` : la voie d'attribution
employée dans les docstrings est le **PROXY** (`RecordedSimulationRequestsBattleQuery.<>c__DisplayClassNNN$$<X>b__0`),
qui ne rend un nom que si le décorateur a un site pour ce slot — son silence se lit à tort comme
« non résoluble ». Recensé, **4 sites** :

| site | slot cité | ce que la table dit | conséquence |
|---|---|---|---|
| `targeting.py` (bit 52 `CasterHas2TurnsLeft`) | `IBattleQuery` `0x1a` | `26 ShouldPlayerSkipTurn/1` — **ne colle pas** (le port lit 2 arguments) | règle NON PORTÉE, dégradation permissive |
| `astramilitarum.py` (`MalleusRocketLauncher`) | idem, redit | idem | idem |
| `targeting.py` (`CasterHasNotMoved`) | `IBattleQuery` `0x34` | `52 IsInMovementRange/2` — **cohérent** | ne peut que DÉSARMER, mesuré armé en live |
| `triggers/loki/hateful_assault.py` | `DSLSelectors+0x78` | **RÉSOLU par cette tranche** : `TargetTile` (via `DSLTriggers$$get_OwnerIsTargetTile`) | note à corriger |

⚠ **Le travail n'est pas mécanique** : sur le premier site, la table CONTREDIT la lecture du port
(1 paramètre contre 2 lus) — donc c'est le SLOT ou l'INTERFACE qui est mal lu, et il faut y retourner
au décompilé. C'est justement pour ça que le résidu vaut : une note « non résolu » cache ici une
lecture FAUSSE, pas une limite.

⚠ Et le zéro ne s'atteint pas par balayage : `movement_query.py` et `stream_cache.py` portent des
« non résolu » **structurels** (une interface IL2CPP n'a pas de corps, et `ISPSet<T>` n'est pas
nommée) — ceux-là restent, et les compter comme dette ferait rougir un garde-fou sur du définitif.
