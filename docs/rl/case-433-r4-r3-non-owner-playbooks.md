# case-433-r4-r3 — les deux `*NonOwnerPlaybook` absents du registre, et le pré-gate `<slot 4>`

**Verdict : les deux sont PORTÉS. `PsychicFortress` (1000) est CONFRONTÉ LIVE et l'écart est un
CHANGEMENT DE TUILE** — le natif joue la tuile que le port ne retenait pas. `EcogSupport` (1487) est
porté et son atteignabilité est **mesurée** (le summon apparaît réellement), mais l'argmax natif
reste **NON CONFRONTÉ**, pour une raison structurelle nommée au §5.

L'argument d'absence qui couvrait le registre — « `LoadPlaybookNonOwner` rend null == MÊME
dégradation que le natif » — était **faux ici** : il ne vaut que pour un type d'ability **sans**
classe native. Les deux classes existent, et leur `CalculateMovementUtilityInSteps` yielde un poids
non nul.

## 1. Ce que les deux corps font, au décompilé

`IdunBattle.AI.Playbook.Loki.PsychicFortressNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
— le corps le plus court de la famille, **aucun gate** hors l'adjacence :

    ITile ownerTile = EntityExtensions.GetMainTile(owner, State);
    if (ownerTile == null) yield break;
    if (!TileExtensions.IsAdjacentTo(case.MovementTile, ownerTile)) yield break;
    yield return GetUtilityValue("PSYCHICFORTRESS_AdjacentFriendly");        // 20

`IdunBattle.AI.Playbook.Loki.ECogSupportPlaybookNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
— **trois** gates, et le premier porte sur le MOVER :

    if (case.unit == null)     { yield return Fix64.Zero; yield break; }
    ITile ownerTile = EntityExtensions.GetMainTile(owner, State);
    if (ownerTile == null)     { yield return Fix64.Zero; yield break; }
    if (!UnitExtensions.HasTrait(case.unit, 2)) yield break;                 // UnitTrait.Summon
    if (UnitExtensions.GetParent(case.unit, State, false) != owner) yield break;
    if (!TileExtensions.IsAdjacentTo(case.MovementTile, ownerTile)) yield break;
    yield return GetUtilityValue("EcogSupport_EcogAdjacentToParent");        // 10

Quatre lectures qui ne se devinent pas :

* **La disposition des champs de la SM DIFFÈRE entre les deux classes** et se lit dans la
  méthode-usine, jamais par transposition : `ECogSupport…$$CalculateMovementUtilityInSteps` écrit
  `case @+0x20, owner @+0x28, playbook @+0x30` ; `PsychicFortress…` écrit
  `owner @+0x20, playbook @+0x28, case @+0x30`.
* **`2` est `UnitTrait`.Summon** (enum qualifié). Le terme d'`EcogSupport` ne peut donc mordre que
  pendant le sweep d'un SUMMON du porteur — jamais pour un allié ordinaire.
* **`GetParent` passe `root = false`** (littéral `0`) : parent DIRECT, pas la racine de chaîne.
* **`IsAdjacentTo` = `MovementUtil$$AreTilesAdjacent`** (vérifié : `TileExtensions$$IsAdjacentTo`
  n'a pas d'autre corps), donc le foyer `battle_query.are_entities_adjacent` — celui qui porte le
  court-circuit d'identité `t1 == t2` de #433-r1, **pas** `is_adjacent`.

Clés BC résolues au littéral (`probe_212_bc_key_literals.py`, slot → token → `global-metadata.dat`),
jamais devinées par préfixe. **Pas de piège #271** : `20` et `10` dans la capture `data/seed-bc.json`
**comme** au gameconfig vivant — le terme mordait donc déjà côté natif pendant que le port rendait 0.

## 2. Le pré-gate `<slot 4>` : LU, et il vaut `false`

C'est le verrou que le module `playbook/non_owner.py` s'était nommé à lui-même (« le jour où un
playbook NonOwner sans auto-gate entre au registre, il faudra lire ce slot »). Les deux entrants
sont exactement ce cas : ni l'un ni l'autre ne re-teste `IsFriend`, alors que
`KustomForceFieldReworkedNonOwnerPlaybook` le faisait — c'est ce qui rendait le gate transparent
jusqu'ici. Trois sources indépendantes le tranchent :

1. **Le slot 4 est bien celui du prédicat, et les slots 0/1/2 sont les trois `Calculate*`.**
   `FUN_180002590(slot, <Il2CppClass*>, obj)` indexe `klass->interfaceOffsets` (+0xb0, compte
   +0x12e) puis la vtable (+0x138, entrées de 0x10) ; le `DAT_` passé porte un token de
   metadata-usage `kind == 1` (`kIl2CppMetadataUsageTypeInfo`) — c'est le TYPE de l'interface.
   `<EvaluateMovementInSteps>d__0$$MoveNext` invoque le slot **0** avec `(case, owner)`,
   `<EvaluateAttackInSteps>d__1` le **1**, `<EvaluateRepairInSteps>d__2` le **2** ;
   `IsInvalidEntityForPlaybook` et `<IterateAbilities>d__3` le **4**.
2. **Aucune classe concrète ne le surcharge.** Le bloc `methodPointers` du PE
   (`probe_8889_methodptr_vtable.py`) donne pour les trois classes concernées **exactement deux
   entrées** — `.ctor` puis `CalculateMovementUtilityInSteps` — suivies des six corps de leur SM
   `d__2`. C'est la lecture qui remplace « absent des tables donc pas d'override », que le
   `CLAUDE.md` interdit à bon droit.
3. **Dans le bloc de la base, un seul corps rend un booléen.** `TriggeredAbilityNonOwnerPlaybook<T>`
   compte **21** entrées ; **19** portent un symbole propre et rendent toutes un objet, `Fix64` ou
   `void`. Des deux corps fondus restants, l'un lit un champ objet (8 octets), l'autre est
   `return 0` sur **UN** octet — la seule signature possible.

⇒ le gate se réduit à `IsFriend(case.unit ?? case.parent, owner)`, et il est mirroré **là où le
natif le met** : dans le dispatcher (`utilities/tile.py::TriggeredAbilitiesNonOwnerUtility.evaluate`,
mirror d'`IterateAbilities`), pas dans les corps. `KustomForceFieldReworked` garde son propre test —
son corps natif le porte vraiment.

**Ce que ce gate évitait, mesuré offline** : sans lui, `PsychicFortress` verse **+20** sur les tuiles
adjacentes à un Tigurius **ADVERSE**. Aucune assertion antérieure ne voyait ce régime.

## 3. Confront live — `PsychicFortress`, un CHANGEMENT DE TUILE

Montage (`probe_433_r4_r3_non_owner_playbooks.py::run_psychic_fortress`) : on classe les tuiles
candidates d'un allié SANS le terme, puis on DÉPLACE le porteur sur une tuile voisine **native** de
la deuxième (et pas de la première). Le couple n'est retenu que si l'écart sans terme est **inférieur
au poids** — sinon le terme ne pourrait rien renverser et la mesure ne prouverait rien.

| board  | seed  | mover           | argmax SANS | argmax AVEC | NATIF   |
|--------|-------|-----------------|-------------|-------------|---------|
| MC1_67 | 777   | `astraBullgryn` | (0, 4)      | (1, 4)      | (1, 4)  |
| MC1_67 | 31337 | `astraBullgryn` | (0, 4)      | (1, 4)      | (1, 4)  |
| MC1_67 | 4321  | `astraBullgryn` | (0, 4)      | (1, 4)      | (1, 4)  |
| C4_09  | 777   | `astraBullgryn` | (3, 5)      | (4, 4)      | (4, 4)  |
| C1_25  | 777   | `necroWarden`   | (1, 3)      | (2, 2)      | (2, 2)  |

**5 montages, 3 boards, 2 movers, 5/5 le natif suit le terme.** Le kit du porteur porte `1000` sur
les DEUX substrats (le `triggered` du voisin côté port, l'`AbilitiesComponent` côté
`unitAbilityStates`). La proposition native est vérifiée MOVE PUR (aucun `ActiveAbilityMessage`),
sans quoi la tuile viendrait du sweep d'ATTAQUE, hors du modèle `UnitMovement(6)`.

## 4. `EcogSupport` — atteignabilité MESURÉE

Le porteur `votanIronmaster` (Vynn) est HERO **hors pool** → injection catalogue
(`catalog_inject.write_augmented_seed_bc`, `case-92` §6). Le summon n'apparaît **pas** au début de
bataille : `ECogSupport_InitAbility$$CreateTrigger` = `OnOwnerSpecificAbilityInit(0x5cf)` ne fait
qu'un `AddFlag(0x18)`. Le vrai déclencheur est
`ECogSupportAbility$$CreateTrigger` = **`On(0x30) & OwnerIsCaster`**, et `0x30` = `48` =
`IdunBattle.DSL.EventTriggerType.UnitRepaired` — c'est la **réparation** par le porteur (ability
dérivée du trait `Mechanic`) qui invoque l'E-Cog :

    If( AmountIsGreater(ConfigConst(maxSummons = 3), Count(AlreadySummonedUnits)),
        Spawn(Owner, PickRandomly(CanAddUnit(AdjacentTiles(Caster)), 1), "votanSmnEcog", opts),
        PerformAIAbility(<un E-Cog déjà invoqué, ami adjacent, avec cible de repair valide>) )

Mesuré (`run_ecog_support`, `MC1_67`/777) : Vynn répare `admecRuststalker` blessé →
**`squadId 112` apparaît en (2, 0)**, sous le `visualId` **`votanNpc1Ecog`** (piège de nommage
`case-92` §5). Sur le `ctx` LIVE de ce summon, les deux gates non triviaux passent :
`unit_traits` porte `UnitTrait.Summon`, `unit_parent_id` = **81** = le porteur. Le terme du port
vaut le poids **exactement** sur les tuiles que `AreTilesAdjacent` déclare adjacentes au porteur et
0 partout ailleurs — balayé sur les **63** tuiles du plateau, **0 divergence**.

## 5. NON CONFRONTÉ — l'argmax natif du summon, et pourquoi c'est structurel

Un summon n'entre **jamais** dans `decisionView.toActivate` (#291) : `aiMovableTiles` lui rend zéro
tuile et `aiDryRunAllUnits` un `FinishUnitTurnMessage`. Son mouvement est joué par
`PlayAutomaticUnits` au **turn-start suivant** de sa team ⇒ l'oracle est **destructif** (un point de
mesure par bataille, pas de dry-run) et la géométrie du spawn est **tirée au sort** par le natif
(`PickRandomly(CanAddUnit(AdjacentTiles(Caster)), 1)`), donc non pilotable pour fabriquer la fenêtre
où le terme renverse l'argmax. Le montage exact à jouer si on le rouvre : capturer l'état à la fin du
tour adverse, calculer l'argmax du port avec/sans terme pour le summon, puis lire sa position au
tout début du tour suivant (recette E4 de `probe_291_summon_activation.py`).

## 6. Validation

* **12 tests** (`tests/engine/test_433_r4_r3_non_owner_playbooks_live.py`) : 8 offline + 2 live
  `PsychicFortress` + 2 live `EcogSupport`.
* **4 mutations, 4 rouges**, arbre restauré bit-exact à chaque fois :
  retrait de `1000` du registre → 7 rouges dont le confront live ; retrait du pré-gate `IsFriend`
  de la feuille → `test_the_pre_gate_excludes_an_ENEMY_carrier` (20.0 versés sur un porteur adverse) ;
  neutralisation du gate `Summon` d'`EcogSupport` → gardes offline ; neutralisation de son gate
  d'adjacence → **59 tuiles divergentes sur 63** au live.
* **Tests de garde re-joués verts** (foyer partagé `non_owner.py` + feuille 4) :
  `test_kustom_force_field_reworked_live.py` (9), `test_419_playbook_wiring_ratchet_offline.py` (3),
  `test_443r1a_triggered_move_anchor_offline.py` (26),
  `test_tile_term_triggered_playbooks_live.py` (12),
  `test_tile_term_unit_gated_playbooks_live.py` (30), `test_playbook_live.py` (3).

## 7. Résidus

* ~~**`#433-r4-r3-r1` — 19 faces MOVE `*NonOwnerPlaybook` restent non portées.**~~ **FERMÉ pour les
  10 du corps partagé — §8.** Le compte cité ici (25 / 22 / 19) était un compte **par NOM** et il
  est FAUX : rectifié au §8.
* **`#433-r4-r3-r2` — les faces OWNER de 1000 et 1487 ne sont pas portées non plus** :
  `PsychicFortressPlaybook$$GetAdjacentFriendUtility` et
  `ECogSupportPlaybook$$CalculateMovementUtilityInStepsInternal`. Elles ne pèsent que le sweep du
  PORTEUR lui-même, donc hors du montage de ce cas — mais elles sont vivantes.
* **`#433-r4-r3-r3` — `scene_tile_leaf_ctx` ne produit pas `unit_parent_id`.** Le terme
  `EcogSupport` (et le bonus PARENT de `SaviorProtocolsPlaybook`, même dégradation nommée là-bas)
  rend donc 0 sur la face PRÉDICTION. Le canal existe des deux côtés depuis #378 (`Scene.parent`) :
  fermable en une ligne, non fait ici (hors périmètre, et rayon de souffle non mesuré).
* **Le régime SPAWN de la feuille 4** (`case.unit == null`, `case.parent != null`) reste muet — le
  `ctx` de spawn ne porte aucune clé de sujet. Résidu préexistant, inchangé.

---

# case-433-r4-r3-r1 — les DIX `AdjacentToOwnerNonOwnerPlaybook<T>`, fermees d'un seul geste

**Verdict : 10 classes portees, 9 au registre, et DEUX confronts LIVE qui sont des CHANGEMENTS DE
TUILE.** Le corps est PARTAGE (un unique iterateur gshared) : le confronter une fois vaut pour les
dix, et le second montage prouve en plus la face variable `GetAdjacencyUtility` ET la cle de
registre de la classe que son propre `.ctor` designe faux.

## 8. Le compte, RE-DERIVE — et il etait faux

| | herite | mesure #433-r4-r3-r1 | ecart |
|---|---|---|---|
| concrets derivant de `TriggeredAbilityNonOwnerPlaybook<T>` | 25 | **28** | +3 |
| dont derivees DIRECTES | 15 | **18** | +3 |
| dont via `AdjacentToOwnerNonOwnerPlaybook<T>` | 10 | **10** | = |
| faces MOVE | 22 | **24** | +2 |
| faces ATTACK | 3 | **3** | = |
| faces REPAIR | (non compte) | **1** | +1 |

**La cause de l'ecart** : le compte herite filtrait sur le NOM (`*NonOwnerPlaybook`). Trois concrets
ne portent pas ce suffixe alors que leur PARENT est bien `TriggeredAbilityNonOwnerPlaybook`1` dans
`data/symbols/<build>/frida/classes.tsv` :

* `IdunBattle.AI.Playbook.Loki.CabalOfSorcerersPlaybook` — **a une face MOVE**
  (`…CabalOfSorcerersPlaybook$$CalculateMovementUtilityInSteps` + sa SM `d__2`) ;
* `IdunBattle.AI.Playbook.Loki.WisdomOfTheAncientsPlaybook` — **a une face MOVE** ;
* `IdunBattle.AI.Playbook.Loki.VoltagheistFieldPlaybook` — face **REPAIR**
  (`…$$CalculateRepairUtilityInSteps`), une 4e face que le compte herite ne mentionnait pas.

Leurs SM nichees (`CabalOfSorcerersPlaybook.<CalculateMovementUtilityInSteps>d__2`) ne contiennent pas
non plus la chaine `NonOwnerPlaybook` : le grep les ratait **deux fois**. Filtrer sur le PARENT, jamais
sur le nom.

## 9. Le corps PARTAGE, et les trois pieges qu'il tend

`IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` :

    if (case.unit == null) yield break;
    if (!Query.AreEntitiesAdjacent(case.Position.Tiles, owner)) yield break;
    yield return GetAdjacencyUtility(case.unit, owner);

1. **La disposition de la state machine est une TROISIEME**, distincte des deux deja mesurees par
   #433-r4-r3 : `case@+0x20, playbook@+0x28, owner@+0x30` ici, contre `case/owner/playbook` pour
   `ECogSupport` et `owner/playbook/case` pour `PsychicFortress`. Trois classes, trois ordres — la
   transposition est morte a chaque fois.
2. **Le gate d'adjacence n'est PAS celui des voisins nommes.** Eux font `GetMainTile(owner)` puis
   `TileExtensions$$IsAdjacentTo` (UNE tuile contre UNE). Ici le corps lit le champ `Query` du
   playbook — **`+0x60`** dans le bloc de champs, confirme par
   `IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$get_Query`
   qui lit le MEME offset (et `get_State` lit `+0x40`, ce qui ecarte la confusion) — et invoque
   `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` sur **des LISTES de tuiles**.
   ⚠ L'overload se fixe par les TYPES des arguments (liste de tuiles, puis ENTITE), **pas** par un
   indice de slot : les indices cites ailleurs dans le port pour cette methode ont bouge de +1 a ce
   build (residu `#433-r3-r3`) et auraient designe une autre surcharge. De toute facon les TROIS
   convergent vers `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` et ne different que par
   les `GetTiles` interposes : pour des entites d'UNE tuile le port est insensible a la question.
3. **`GetAdjacencyUtility(movingUnit, owner)` est le SEUL point de variation**, et les dix corps lus
   un par un ne lisent QUE `movingUnit`. Aucun ne lit `owner`, ni l'etat, ni une stat. C'est ce qui
   rend ces termes **greffables** (regle « npc GREFFABLE » du `CLAUDE.md`) — et c'est ce qui a rendu
   la confrontation possible du tout.

## 10. `PrimarchOfTheFirstLegion` — le `.ctor` designe la MAUVAISE ability

`IdunBattle.AI.Playbook.Loki.PrimarchOfTheFirstLegionNonOwnerPlaybook$$.ctor` passe `0x5b6` =
**1462** = `NetherRealmCasket` a sa base, alors que l'enum la numerote **1511**. Ce n'est pas une
mauvaise lecture : les octets sont `ba b6 05 00 00` dans les DEUX `.ctor`, et les deux passent aussi
le MEME `MethodInfo*` de base inflate — la classe derive donc litteralement
d'`AdjacentToOwnerNonOwnerPlaybook<NetherRealmCasketAbility>`, ce qui explique que `classes.tsv`
n'ait AUCUNE instanciation `AdjacentToOwnerNonOwnerPlaybook<PrimarchOfTheFirstLegion…>`.

**Ce n'est pas le `.ctor` qui indexe le registre.** `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner`
fait `TryGetValue(<factories @+0x98>, abilityType)` ; la cle est posee au SITE D'ENREGISTREMENT
(`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`). Tranche **deux fois, independamment** :

* **offline** — `probe_433_r4_r3_r1_non_owner_registry.py` balaie les `mov edx, imm32` du corps
  d'enregistrement (0xfcb0 octets) : les dix ids d'enum y figurent, **1511 present**, **1462 une
  seule fois** (donc aucune des deux entrees n'ecrase l'autre) ;
* **en vivant** — §11 etape B : on greffe l'ability **1511** et le natif SUIT le terme. S'il n'avait
  pas d'entree sous 1511, `LoadPlaybookNonOwner` rendrait null et il ne la suivrait pas.

Suivre le `.ctor` aurait, au choix, **tue l'entree 1462** de `NetherRealmCasket` (dont les porteurs
`necroDestroyer`/`necroSpyder` sont au pool par la voie relique) en lui substituant un gate de
FACTION la ou le natif teste un TRAIT, ou pose une entree morte sous 1511. Aucune erreur, aucun
crash : les deux sont des regressions silencieuses.

## 11. Confront LIVE — deux CHANGEMENTS DE TUILE

**Montage : la GREFFE.** Aucun des dix porteurs n'arrive en bataille par la voie ordinaire. Le seul
hero du pool qui porte un de ces passifs nativement, `necroOverlord` (`MyWillBeDoneOverlord`), a une
entree `BC.Units` **PERIMEE** (`catalog_inject.STALE_UNIT_ENTRIES`, #254-bc/#392-r1) : tout runner
bati sur ce seed le deploie avec le kit de `gqfc5mff6c`, donc SANS l'ability — le terme y serait
inerte des DEUX cotes. On greffe donc (`catalog_inject.graft_passive_ability`, `replace=True`) sur
`astraBullgryn`, unite DU POOL. La greffe est legitime ici parce que les dix
`GetAdjacencyUtility` ne lisent rien du caster (§9.3), condition explicitement exigee par le
`CLAUDE.md` avant toute greffe.

| etape | ability | poids | mover | argmax SANS | argmax AVEC | NATIF |
|---|---|---|---|---|---|---|
| A | `WatchedOver` 1524 (aucun gate) | 20 | `darkaAzrael` | (0, 4) | **(1, 4)** | **(1, 4)** |
| B | `PrimarchOfTheFirstLegion` 1511 (gate DarkAngels) | 20 | `darkaAzrael` | (0, 4) | **(1, 4)** | **(1, 4)** |

Board `MC1_67`, seed 777. Le couple n'est retenu que si l'ecart sans terme est INFERIEUR au poids —
sinon le terme ne pourrait rien renverser. La proposition native est verifiee **MOVE PUR** (aucun
`ActiveAbilityMessage`), sans quoi la tuile viendrait du sweep d'ATTAQUE, hors du modele
`UnitMovement(6)`. Le kit du greffon porte l'id sur les DEUX substrats (`triggered` cote port,
`unitAbilityStates` cote natif).

**Le GATE, mesure et non deduit** (etape B, greffon a la MEME position) : sur `necroWarden`
(faction 7), le terme vaut **exactement 0 sur ses 12 tuiles candidates** — `max_delta = 0.0`.

## 12. `RedemptionOfTheRisen` (1522) — PORTEE, mais DEAD CODE nomme

La 10e classe est portee et son corps est exact (identique a celui de `PrimarchOfTheFirstLegion`,
cle et poids compris), mais elle est **volontairement HORS du registre** : l'ability n'est attribuee
a AUCUNE unite sur `rnca9r7q6c`. Deux sources independantes :

* `unit_map.py find --ability RedemptionOfTheRisen` -> 0 unite sur les 5 voies derivables ;
* balayage TEXTUEL du gameconfig entier : ses **4** occurrences sont sa definition
  (`variables.hp`), son `baseMultiplier` et ses DEUX cles d'utilite. Aucune liste de passifs d'unite
  ne la cite.

C'est le cliquet **#419** qui l'a trouve, et il avait raison : l'enregistrer aurait ajoute du code
que le dispatcher n'itere jamais. **La banque a rougi sur mon propre port avant que je ne le livre**
— la classe reste, l'entree de registre part, et la reactiver tient en UNE ligne au build ou une
unite portera 1522.

## 13. Validation

* **38 tests** (`tests/engine/test_433_r4_r3_r1_adjacent_to_owner_live.py`) : 34 offline (dont 26
  cas parametres de gate) + 4 live.
* **5 mutations, 5 rouges**, arbre restaure BIT-EXACT a chaque fois (verifie par comparaison
  binaire, pas par relecture) : `Primarch` indexee sur le litteral du `.ctor` -> **6** rouges ;
  `IsMechanical` rabattu sur `HasTrait(Mechanical)` nu -> 2 ; gate d'adjacence retire du corps
  partage -> 1 ; `PropheticSentinel` rendu exclusif au lieu de cumulatif -> 1 ; porteur sans
  position accepte -> 1. **6e contre-epreuve, involontaire et la meilleure** : re-enregistrer 1522
  fait rougir `probe_457:s2` de la banque (§12).
* **Banque de cliquets VERTE** — 35/35, mur 389,9 s (apres avoir ete ROUGE 1/35 sur mon port).
* **Gardes re-jouees vertes** (foyer partage `non_owner.py` + feuille 4) :
  `test_kustom_force_field_reworked_live.py` (9), `test_433_r4_r3_non_owner_playbooks_live.py` (12),
  `test_419_playbook_wiring_ratchet_offline.py` (3), `test_443r1a_triggered_move_anchor_offline.py`
  (26), `test_tile_term_triggered_playbooks_live.py` (12),
  `test_tile_term_unit_gated_playbooks_live.py` (30), `test_playbook_live.py` (3).
* **Rebase sur `a060d971`** (qui active la porte d'elevation du substrat DSL, #535) puis RE-JEU
  integral : aucun ecart.

### Ce qui n'est PAS couvert

* **8 des 10 termes ne sont pas confrontes INDIVIDUELLEMENT en live.** Le corps partage l'est (A) et
  la face variable l'est (B, gate + non-gate) ; les huit autres `GetAdjacencyUtility` sont gardes
  offline, corps par corps, par les 26 cas parametres.
* **Les entites MULTI-TUILES.** Le natif compare ici deux LISTES de tuiles ; le port compare deux
  positions. Pour une Machine of War le natif est PLUS permissif. Aucun des 10 porteurs connus n'est
  multi-tuiles, mais le mover, lui, pourrait l'etre.
* **Le regime SPAWN** de la feuille 4 reste muet (le `ctx` de spawn ne porte aucune cle de sujet) —
  residu preexistant, inchange.
* **`PrimarchOfTheFirstLegion` n'a qu'un porteur npc** (`darkaBossLion`) : le confront passe par la
  greffe, qui est fidele ici (§9.3) mais ne prouve rien sur les stats/traits du vrai porteur.

## 14. `#433-r4-r3-r1-r3` — le TROISIÈME jumeau unionnait encore (RÉSOLU, 2026-08-15)

**Prémisse CONFIRMÉE par re-mesure live**, mais **son accusé était faux**.

Ce que la fiche disait : « `entity_triggered_ability_ids` FUSIONNE le kit gameconfig par
`visualId` ». C'est **inexact depuis #456-r1** — ce foyer est en tri-état et **REMPLACE**
(mesuré : `ctx` mesuré → `[1524, 1030]`, aucune union avec `[1028]`).

La cause réelle : **`engine/utilities/tile.py::_adjacent_units`**, le jumeau `AiDecisionContext`,
était le **dernier des trois producteurs** à unionner :

```python
_trig = list(triggered_ability_ids(u.get("visualId")))   # kit GAMECONFIG
for _t in (live_kits.get(u.get("id")) or ()):            # UNION avec la mesure
    if _t not in _trig:
        _trig.append(_t)
```

Le MOVER était passé au remplacement par **#304**, les deux autres jumeaux
(`runner_tile_leaf_ctx`, `scene_tile_leaf_ctx`) par **#456-r1** — tous deux sur la même mesure :
une union ne peut qu'AJOUTER, donc elle RÉINTRODUIT un passif que la bataille n'a **pas** monté.
Les VOISINS, eux, sont restés en union. L'asymétrie vivait **dans le même producteur**.

### La mesure, re-jouée LIVE le 2026-08-15 (`t6dpr4k06g`, montage §11 étape A)

```
avant   kit greffon -- port = [1028, 1524, 1030]   AbilitiesComponent NATIF = [1524, 1030]
après   kit greffon -- port = [1524, 1030]         AbilitiesComponent NATIF = [1524, 1030]
```

`1028` = `AvalancheOfMuscle`, le passif de kit que `graft_passive_ability(..., replace=True)` avait
justement remplacé dans `BC.Units[].PassiveAbilities`. Le verdict de #433-r4-r3-r1 est **intact** :
le natif SUIT toujours le terme (argmax `(1,4)` des deux côtés).

### Portée du correctif

Le repli gameconfig reste **entier** quand la mesure est vide pour cette entité (RPC indisponible,
entité absente, contexte offline sans pont) — c'est le seul régime que le motif d'union protégeait.
Consommateurs de `friend_units[].triggered` / `enemy_units[].triggered` :
`AttractToDecoysUtility` (64), `SteppableUnitUtility` (19), et les playbooks non-owner.

### Validation

* `tests/engine/test_433r4r3r1r3_kit_voisin_remplacement_offline.py` — **6 gardes**, dont le repli
  dans les trois formes de mesure vide, la lecture PAR ENTITÉ (deux voisins de même `visualId`, un
  mesuré et un non), et l'égalité de traitement MOVER/VOISINS. Contre-épreuve : remettre l'union →
  **4 rouges**, restauration → 6 verts.
* Re-jeu des consommateurs, **76 tests verts** : `test_433_r4_r3_r1_adjacent_to_owner_live.py` (38),
  `test_433_r4_r3_non_owner_playbooks_live.py` (12), `test_steppable_decoy_tile_leaves_live.py`
  (14), `test_tile_term_triggered_playbooks_live.py` (12) ; puis
  `test_kustom_force_field_reworked_live.py` (9) et `test_tile_term_unit_gated_playbooks_live.py`
  (30).
* **Deux rouges rencontrés, tous deux PRÉ-EXISTANTS** (baseline mesurée en restaurant `tile.py` à
  l'état antérieur, résultats **identiques** au bit près) : `test_477r33_non_owner_playbooks_live.py`
  12 failed / 29 passed, et `test_spiritual_leader_tile_term_live.py` 1 failed / 9 passed
  (`(1,3)` : terme 0 avec 2 decoys adjacents). **Ce ne sont pas des régressions de cette tranche.**
