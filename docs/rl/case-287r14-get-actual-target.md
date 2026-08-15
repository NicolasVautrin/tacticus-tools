# #287-r14 — `TargetingQuery$$GetActualTarget` : le port avait **deux régimes de cible**, le natif n'en a **qu'un**

Le port recevait tantôt une **UNITÉ** (tous les tests live : `_ringed_cast.cast_and_confront` envoie
`targetId: <unité>`), tantôt une **TUILE** (la face DÉCISION portée : `abilityTargets` rend
`kind: "tile"`, l'action porte le `tileEntityId`). Le natif accepte les deux **parce qu'il transforme
lui-même**. Le port, lui, propageait l'argument tel quel.

## 1. La chaîne native — relue, pas héritée

`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` transforme sa cible **AVANT ses deux
gates**, et l'ordre est celui-là (lu au décompilé, build `rnca9r7q6c`) :

    ability     = AbilitiesDatabase.Get(abilityType);
    casterTiles = EntityExtensions.GetTiles(caster, state);
    finalTarget = IActiveAbility.GetActualTarget(ability, caster, target);   // slot IActiveAbility 16
    if (finalTarget == null) return;
    if (IsDeadUnitAndNotAllowedByAbility(abilityType, finalTarget)) return;
    if (IsInvalidTarget(caster, casterTiles, finalTarget, ...)) return;
    ... GetAbilityEntities(this, caster, casterTiles, finalTarget, abilityType);   // +0x10 <- finalTarget

`IdunBattle.Entities.Abilities.AActiveAbility$$GetActualTarget` recopie les 0x40 octets de **ses**
`TargetingOptions` (`this+0xb0`) et délègue au slot `ITargetingQuery` 6 =
`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` :

    if (options.isSelfCasting == 0) {                      // byte @options+0x00
        if (options.rules & 0x40)          return EntityExtensions.GetMainTile(target, state);
        if (options.rules & (1<<44))       return UnitExtensions.GetMachine(target, state);
        if (options.rules & (1<<46)) { u = UnitExtensions.GetUnit(target, state);
                                       return u != null ? u : GetMachine(target, state); }
        return UnitExtensions.GetUnit(target, state);
    }
    return caster;

Les deux numéros de slot sont **lus** dans `data/symbols/<build>/metadata/interface_slots.tsv`
(`ITargetingQuery 6 GetActualTarget`, `IActiveAbility 16 GetActualTarget`).

⚠ **La branche MACHINE n'essaie PAS `GetUnit` d'abord** — seule la branche ACTOR enchaîne les deux.
Écrire « unit puis machine » partout serait un masque faux.

⚠ **La surcharge de `GetUnit` se tranche par les XREFS, pas par le nom** : le binaire en porte
**trois** (tuile→unité, pied→unité, et le dispatch domaine mixte). Les deux call-sites de
`GetActualTarget` visent la troisième, dont le corps teste `Unit` → l'entité elle-même, `Tile` →
l'occupant via `TileContentComponent` **avec récursion**, `UnitFoot` → son unité, sinon `null`.

## 2. Le rayon — mesuré dans DEUX voies, parce qu'elles ne couvrent pas le même ensemble

`probe_287r14_get_actual_target.py` joue **tout** `ABILITY_CLASSES` dans les deux régimes sur un
substrat identique et compare une **empreinte d'ÉTAT** (effets posés + PV + positions + morts), pas
le diagnostic rendu.

⚠ **Le critère par le RETOUR aurait rendu « rayon 0 »** : `1018` rend `deferred_effect: 1022` dans
les deux régimes — c'est le **porteur** de l'effet qui diffère, pas le diagnostic.

| voie | avant | après |
|---|---|---|
| `execute_behaviour` en direct — `TargetIsTile` | **14 divergentes** sur 23 | **0** |
| `AbilityHandler.visit_ActiveAbilityMessage` — **toutes** | **0** (la mesure n'existait pas ; le trou était en amont) | **0**, 44 témoins non nuls |

Le témoin non nul est obligatoire : **85 des 129** casts sont inertes sur le montage générique (les
gates de ciblage refusent la cible), et un accord entre deux no-op ne prouve rien.

## 3. Les deux branchements, et pourquoi le second n'est pas un fork

* **`AbilityHandler._active_ability_operation`** — la place NATIVE : la résolution y précède
  `IsDeadUnitAndNotAllowedByAbility`, `IsInvalidTarget`, le snapshot `GetTiles(finalTarget)`, la
  re-résolution `ExecuteForReplacedTarget` et `execute_behaviour`. C'est ce branchement-là qui couvre
  le moteur (`applyAction`, RL, tests live).
* **La tête des 23 `execute_behaviour` `TargetIsTile`** — le port **fusionne** dans
  `execute_behaviour` deux étages natifs (`GetAbilityEntities` + `AActiveAbility$$ExecuteBehaviour`) ;
  la résolution est l'étage immédiatement amont du premier, donc son ancrage le plus proche côté
  port. Elle y est **inerte** quand le handler a déjà résolu.

**L'idempotence est ce qui autorise les deux** : chaque branche est un projecteur
(`GetMainTile(<tuile>)` rend la tuile, `GetUnit(<unité>)` l'unité, `GetMachine(<MoW>)` la MoW,
self-cast rend `caster`). Elle est gardée (étage [2] du cliquet), pas supposée.

## 4. Les deux non-mesures qui ne doivent PAS devenir des refus

* **`TARGETING_OPTIONS is None`** (masque non RE-lu) → `target_id` rendu tel quel. Même doctrine que
  le gate de cible : sans masque le port ne devine pas.
* **`state.board is None`** (boardGraph non chargé — `load_state(dv, ob, snap)` sans `board=`) →
  `target_id` rendu tel quel. Ce n'est pas « la cible n'a pas de tuile ».
  **MESURE** : sans ce repli, `test_valkyrie_strike_migration_live` passait de « l'arbre DSL pose
  1022 » à `execute_behaviour -> None`, un no-op complet — une non-mesure rabattue en REFUS.

⚠ **Une MoW n'est pas une `Unit`.** Le natif la classe `Machine` ; le port lui pose un
`UnitComponent` pour la rendre exerçable (`snapshot._load_machines`). Le discriminant retenu est le
`MachineComponent` : sans lui, `GetUnit(<MoW>)` rendrait la MoW là où le natif rend `null`.

## 5. La confrontation LIVE — `probe_287r14_confront_live.py` (`MC1_67`, seed 777)

Cast de `1018 ValkyrieStrike` avec `targetId` = **l'id d'UNITÉ** (le régime que le port empruntait) :

| | porteur de l'effet `1022` |
|---|---|
| **NATIF** | **TUILE 74** (`tileMeta.tiles[].effects`) ; `decisionView.units[].effects` **inchangé** |
| **PORT** après la tranche | **74** — accord |
| **TÉMOIN** (résolution neutralisée) | **77**, l'unité — la divergence que la tranche ferme |

Le témoin est obligatoire : sans lui, un accord natif/port ne distingue pas « la résolution porte le
résultat » de « il vient d'ailleurs ».

**Généralisation — `1026 BasiliskBarrage`, un patron TOUT AUTRE** (`--volet 1026`) : pas de `Target()`
dans l'arbre, mais un collapse impératif qui **tire ses tuiles au PRNG**. C'est le scénario le plus à
risque (une cible déplacée d'un cran ferait diverger la suite de tirages). Cast en régime UNITÉ :
natif et port rendent les **6 mêmes coups**, `(81,462) (81,493) (79,460) (79,521) (77,449) (77,525)`,
et le **témoin est identique** — la résolution y est **inerte**, son collapse passait déjà par
`main_tile_id`. C'est un résultat de **non-régression**, pas de réparation : il établit que la
tranche ne perturbe aucun tirage.

## 5bis. La régression que la tranche a d'abord INTRODUITE — et qui l'a trouvée

Brancher la résolution **en amont** du gate cible-morte (l'ordre natif) l'a **désarmé** : pour une
ability tile-target visant un **cadavre**, `main_tile_id` rendait encore sa dernière tuile (le
`PositionComponent` survit à la mort côté port), donc `IsUnit(<tuile>)` était faux et le cast
s'exécutait sur un mort. **Écart PERMISSIF, silencieux.**

Ce n'est pas la relecture qui l'a vu, c'est le **harnais** : `test_429r1r3_dead_target_message_gate_live`
est parti en `ERROR` (`state.rng non calé`, levé depuis `damage_ops/normal.py` — donc la behaviour
s'exécutait). Le décompilé tranche : `GetMainTileId` cherche le composant de **pied**, puis
l'`OrderedSet` de pieds @+0x78 dont il sort par `return 0` quand il est **vide** ; le natif retire du
board l'unité tuée, donc `GetMainTile(<cadavre>)` rend `state.GetEntity(0)` = **null**. Le filtre
d'occupation est posé dans `main_tile_id`, par `UnitExtensions$$IsAlive` — le prédicat **large** (flag
`Dead`, pool `AliveUnits`, PV), choisi plutôt que les seuls PV parce qu'une unité **retirée** à PV
pleins n'a pas de pied non plus, et parce que c'est **exactement** celui du gate cible-morte : la
résolution et le gate ne peuvent plus diverger sur le même cadavre. Étage [12] de la garde.

### Ce que cela a changé dans `#429-r1-r3`, et pourquoi c'est une fidélité

Deux corrections dans `probe_429r1r3_dead_target_message_gate.py` et son test :

1. **`_refuse` ignorait une QUATRIÈME porte.** `no_actual_target` est native
   (`if (finalTarget == null) return 0;`, avant les deux gates) et mord sur les 23 tile-target dont
   la cible cadavre ne résout plus. L'omettre comptait ces **refus** comme des **passages** : le bras
   muté rendait **86/129** au lieu de **109/129**, et l'écart accusait le mauvais mécanisme.
2. **L'ensemble des « rescapées sans le gate de message » n'est plus `{1089}`.** Une ability
   **self-castée** voit sa cible remplacée par le **caster** (court-circuit `isSelfCasting`, en tête
   de `GetActualTarget`) : le gate cible-morte ne peut pas la fermer, puisqu'il ne voit plus le
   cadavre — et **le natif fait exactement cela**. Mesuré : **20 rescapées = 19 self-cast + `1089`**
   (`1045`, self-cast, est fermée par `invalid_target`). L'attendu du test se **dérive** désormais
   (`self_cast | {1089}`, `self_cast` lu du registre) au lieu d'être saisi, et ce qui reste
   discriminant — le cœur du cas #429-r1-r3 — est intact : **aucune** ability à cible **externe**
   n'échappe, hormis le porteur du bit 38. Le test principal (`refusees == registre`) reste
   **129/129**.

⚠ **Le montage du probe LEVAIT** au lieu de mesurer (`state.rng` non calé) : un scénario qui ne
confronte aucun tirage mais dont le bras muté exécute des behaviours doit quand même seeder son PRNG,
sinon la levée remonte dans la **fixture** et les deux tests sortent en `ERROR` — sans aucune mesure.

⚠ Le champ du canal est `effectType`, **pas** `type`, et `tileMeta.tiles[]` n'a **pas** de champ
`id` (indexé par `(col,row)`) : les confondre rend deux dicts vides, donc « le natif ne pose RIEN »
— la conclusion inverse de la vérité (faute commise et corrigée dans #287-r12 ; ce probe réutilise
ses deux lecteurs plutôt que d'en écrire de nouveaux).

## 6. La garde

`tests/engine/runner/test_287r14_get_actual_target_offline.py`, **11 étages** : les quatre branches +
self-cast ; la contre-épreuve d'ordre (MACHINE ne passe pas par `GetUnit`) ; l'idempotence ; les deux
non-mesures ; le **cliquet de registre voie behaviour** (le critère de la tranche) ; le **cliquet de
registre voie handler** (toutes les abilities) ; le **témoin non nul** ; le **balayage STATIQUE** du
geste au registre ; la MoW ; le porteur TUILE de `1022` (valeur mesurée live) ; et l'**atteignabilité
du gate `finalTarget == null`**.

Vue rouge sur l'arbre témoin (`git archive` du commit d'avant la tranche) : **11 failed / 1 passed**.
Le seul vert est `etage8b`, qui assertionne le **non-vide** du balayage statique — un invariant que la
tranche ne change pas, et sans lequel l'étage [8] serait vert sur un ensemble vide.

⚠ **L'import des trois symboles NEUFS est LOCAL** (`_foyer()`), et la raison n'est pas un cycle : au
niveau module ils feraient échouer la **collecte** sur l'arbre témoin, et un fichier non collecté ne
montre **aucun** de ses autres étages. Même parade que `test_287r12_role_target_tuile_offline` pour
`main_tile_id`.

⚠ **L'étage [11] existe parce que le gate `finalTarget == null` n'est exercé par AUCUN des 258 casts
du balayage** (mesuré) : ce sont ces branches-là qui dérivent en silence. Il l'exerce explicitement
— une ability UNIT-TARGET dont la cible est une **tuile vide**.

## 7. Ce qui n'est PAS couvert

* **`#287-r14-r1` — la voie `execute_behaviour` ne résout que les `TargetIsTile`.** Mesuré après la
  tranche : **73** abilities divergent encore entre les deux régimes par appel DIRECT (72
  `GetUnit (défaut)` + 1 `TargetIsActor`), parce que la ligne de résolution n'est posée que sur les
  23 tile-target. Ce régime — passer un id de TUILE en direct à une ability unit-target — n'est
  emprunté par **aucun appelant réel** (la face décision n'émet un `tileEntityId` que pour les
  tile-target, et le moteur passe par le handler, qui résout), mais un futur probe pourrait
  l'emprunter, exactement comme `test_valkyrie_strike_migration_live` a gravé le régime U.
* **`#287-r14-r2` — `TileExtensions$$GetMachinePlatformContent` n'est pas porté** : c'est la branche
  TUILE de `UnitExtensions$$GetMachine`. Le port ne modélise pas les plateformes de MoW comme contenu
  de tuile (une MoW n'a ni `PositionComponent` ni tuile — `snapshot._load_machines`, « hors-plateau »),
  donc il n'existe aucun substrat d'où la tirer. `machine_id` rend `None` sur une tuile, ce qui est la
  dégradation fidèle à ce que le port sait — mais une ability `TargetIsMachine` ciblant la
  **plateforme** plutôt que la machine résoudrait `None` là où le natif rend la MoW.
* **La branche `UnitFoot` de `GetUnit`** n'a pas de contrepartie : les pieds n'ont pas d'entité propre
  côté port (`get_unit_feet` rend des **positions**). Aucun appelant du port ne tient d'id de pied.
* **`test_valkyrie_strike_migration_live` grave toujours le régime U** — et c'est correct : il charge
  `load_state(dv, ob, snap)` **sans board**, donc la résolution y est inerte par le repli du §4. Il
  reste juste **en tant que test de migration** (il confronte DSL vs impératif, pas le porteur au
  natif) ; c'est `probe_287r14_confront_live.py` qui confronte le porteur.
* **L'espace d'ids partagé tuile/entité** reste le résidu déjà nommé dans
  `operations/active_ability.py` : un id ambigu est tranché par l'ordre de `main_tile_id` (unité
  d'abord, tuile en repli — l'ordre natif), ce n'est pas une séparation des espaces.

## 8. `#287-r14-r1` : le regime est MORT -- les 73 tetes ne seront PAS portees

**Tranche le 2026-08-08.** Le residu proposait de porter la resolution sur la tete des **73**
abilities qui divergent entre regime UNITE et regime TUILE par appel direct, en notant que ce
regime n'est << emprunte par aucun appelant reel >>. La consigne etait de le VERIFIER d'abord.

### Ce que la mesure rend

| mesure | valeur |
|---|---|
| appels DIRECTS a `execute_behaviour` (hors `AbilityHandler`, 3+ args) | **181** |
| dont l'expression de cible NOMME une tuile | **10** |
| dont la classe est ecrite au site (attribution EXACTE) | **3** -- `DaemonicOrdnance` 1148, `DutyEternal` 1158, `SporeMineLauncher` 1145 |
| ... et toutes trois sont `TargetIsTile` | **3 / 3** |
| non attribuables (`cls().execute_behaviour(...)`) | **7**, tous dans les probes #287-r12 |
| appelants qui passent une tuile a une ability **unit-target** | **0** |

Les 7 non attribuables sont `probe_287r12_confront_live.py`, `probe_287r12_role_target_tuile.py`
et son test : ils balaient **tout** le registre avec une tuile parce que **mesurer ce regime est
leur objet**. Les compter en faute ferait rougir la mesure du regime sur la mesure elle-meme.

**Verdict : branche morte.** Porter 73 tetes reviendrait a recopier 73 fois une ligne inerte et
a s'en donner la maintenance -- une dette, pas un port.

### Le cran qui manquait vraiment, et qui n'etait garde par rien

Les 23 tetes existantes ne sont pas une couverture partielle arbitraire : elles couvrent le
regime **symetrique**, celui qui EST emprunte -- passer une **UNITE** a une ability tile-target,
ce que `test_valkyrie_strike_migration_live` grave. La ventilation, **derivee du registre** :

| versant | entrees | resolvent en tete |
|---|---|---|
| `TargetIsTile` | 23 | **23** (0 manquante) |
| non-tile | 106 | **0** (0 surplus) |
| `TARGETING_OPTIONS` non RE-lu -- *pas mesure* | 0 | -- |

Ce **23/23** n'etait garde par rien. C'est exactement la forme de `TARGETING_OPTIONS` et
`ABILITY_ATTACK_TYPE` : **un zero que notre propre cadence de portage rouvre**, une ability
tile-target neuve entrant au registre sans sa ligne. La degradation serait **PERMISSIVE et
muette** -- l'ability opererait sur l'unite la ou le natif lui donne sa tuile, sans erreur.

Livre : `probe_287r14r1_resolution_tile_target.py` (`--cliquet`) et
`tests/engine/runner/test_287r14r1_resolution_tile_target_offline.py` (8 tests).

Trois choix de conception, tous **derives** :

* le versant `TARGETING_OPTIONS is None` a **son propre seau** -- le rabattre sur << non-tile >>
  fabriquerait un zero (regle tri-etat de `host_inputs.py`). Il est vide aujourd'hui ; il est
  quand meme imprime, et un test verifie que les trois seaux **partitionnent** le registre ;
* le lecteur de la ligne est un **AST sur la source de la methode**, jamais un grep du fichier :
  un module d'abilities en porte jusqu'a 40, un grep attribuerait a une classe la ligne de sa
  voisine ;
* l'attribution d'un appel est **exacte ou absente** : `XAbility().execute_behaviour(...)`
  s'attribue, `cls().execute_behaviour(...)` non -- et les seconds sont **imprimes**, jamais
  devines ni comptes propres.

Le cliquet **assertionne son propre non-vide** (`0 tile-target` fait rougir), et l'etage 2
verifie que le releve de sites-a-tuile n'est pas vide **avant** de conclure qu'il est conforme :
un `hors_contrat == []` obtenu sur un releve vide ne prouverait rien.

## 9. `#287-r14-r2` : la branche `MachinePlatform` NE SERA PAS PORTEE -- et la raison ecrite etait fausse

`IdunBattle.Entities.UnitExtensions$$GetMachine` a trois branches, relues sur le build COURANT
`t6dpr4k06g` (la fiche notait « Ghidra sert encore l'ANCIEN build » : c'est perime) :

    if (entity == null)          return null;
    if (EntityType(entity) == 6) return entity;                            # Machine
    if (EntityType(entity) == 7) return TileExtensions
                                        .GetMachinePlatformContent(entity, state);
    return null;

et `GetMachinePlatformContent` lit `MachinePlatformComponent.MachineId` (`Nullable`, `@+0x14`
hasValue / `@+0x18` value) puis **rend `null` si `HasValue` est faux** (`if (*pcVar4 == 0) return 0`).

### La raison de ne pas porter a CHANGE, parce que l'ancienne est tombee

L'ancienne : « le substrat est publie A MOITIE -- une MoW porte DEUX plateformes, le canal n'en
publie qu'UNE -- donc porter le mapping ferait reussir la resolution sur l'une et echouer sur
l'autre, en silence ». **Elle est fausse.** `frida/hooks/game/match-state.ts::readMachinePlatformLink`
ne retient que les plateformes dont `MachineId.HasValue` est vrai -- **la meme condition** que le
natif. Une plateforme absente de `decisionView.mows[].platformIds` est donc une plateforme sur
laquelle `GetMachinePlatformContent` rendrait `null` lui aussi : le mapping publie est **COMPLET
pour tout ce qui est LIABLE**. Le « deux plateformes, une publiee » est un FAIT NATIF.

### Ce qui interdit reellement le port : la REACHABILITE, et elle est MESUREE

Deux portes seulement mènent a `machine_id()` avec autre chose qu'une Machine :

| voie | bit | porteurs au registre (182 entrees) |
|---|---|---|
| `TargetIsMachine` -- appelle `machine_id()` SANS essayer `unit_id()` d'abord | 44 | **0** |
| `TargetIsActor` -- `unit_id() ?? machine_id()` | 46 | **1** : `1160 HeavyRailRifle` |

Et le canal de ciblage natif ne remet jamais une plateforme. Mesure du 2026-08-15
(`--p-mow tauBroadside --a-mow orksRukkatrukk`, board `MC1_67`, seed 777) :

    decisionView.mows -> id=75 machineId=80 (tauBroadside)   platformIds=[75]
                         id=76 machineId=79 (orksRukkatrukk) platformIds=[76]
    abilityTargets(caster=80, ability=1160).fromHere -> [77, 79]
        INTERSECTION avec les PLATEFORMES {75, 76} = {}       <- VIDE
        INTERSECTION avec les MACHINES    {79, 80} = {79}     <- la MACHINE, pas sa plateforme
    port, MEME etat charge : machine_id(79) = 79, machine_id(80) = 80   <- ACCORD

Porter la branche ajouterait donc du code qu'aucun vecteur n'exerce, et son premier test devrait
FABRIQUER une cible que le natif ne produit jamais -- « pas de porteur = speculatif ».

### Le verdict est sous CLIQUET, pas en prose

`tests/engine/test_287r14r2_reachability_plateforme_offline.py`, 4 tests. Le premier est un
**temoin de non-degenerescence** : les deux comptes gardes valent `0` et `1`, donc un registre
vide, un `TargetingRule` renomme ou un `TARGETING_OPTIONS` introuvable les rendraient verts en
n'ayant rien regarde -- on exige d'abord que le gisement existe. Le fichier ROUGIT le jour ou une
ability entre au registre avec `TargetIsMachine`, ou ou `1160` change de masque : le port devient
alors exigible **avec** son vecteur de confrontation, qui est exactement ce qui manquait.
