# #477-r15 — Combien de `StreamCache` / `StreamDispatcher` est porté ? Mesure et chiffrage

**Build** `rnca9r7q6c`. Mesure offline (`probe_477r15_stream_emitter_coverage.py`) + confrontation
live session Frida **7** (`probe_477r15_identite_par_kit.py`, 5 runners montés et disposés).

## Verdict en une ligne

**Rien de l'émetteur n'est porté** — et ce n'est pas « 0 % d'une table à remplir », c'est une couche
**absente**. Le bus d'événements du moteur est un **stub mort** (0 appel, 0 sous-classe d'événement
sur 116 421 lignes). En revanche le **risque n° 1 identifié par #477-r11 n'existe pas** : le flux
**porte bien** un identifiant d'unité, et la stratégie de comparaison n'a besoin d'aucun canal
supplémentaire. Le vrai point dur est ailleurs, et il est mesuré : l'**ordre d'allocation des
entités ECS**.

## 1. La migration 014 : ce qu'elle fait vraiment

`scripts/sql/014_stream_group.sql` — « matérialise l'arbre des groupes du StreamDispatcher ». C'est
**exact et hors sujet** : elle crée une table PostgreSQL `tacticus.stream_group` (self-FK
`parent_group_id`, `depth`, `group_code`) alimentée **à l'ingest de ce que le NATIF a émis**, capté
par `frida/hooks/game/apply-stack.ts`.

⇒ **C'est un CONSOMMATEUR.** Elle ne fait rien émettre au port Python. La question « combien de la
couche est déjà portée » ne peut pas s'appuyer dessus. Même chose pour `scripts/python/stream_events.py`
(décodeur : `step_name`, `group_name`, `decode_lines`, `analyze`).

**L'asymétrie est totale** : le dépôt sait **lire** le flux natif (décodage + matérialisation SQL) et
ne sait **rien en produire**.

## 2. L'état mesuré du port, ventilé par RÔLE

| rôle | état | mesure |
|---|---|---|
| **vocabulaire** (GroupType/StepType/TagKey) | **dérivable, non mirroré** | `enums.tsv` versionné : **104 / 62 / 244** membres. Aucun mirror Python de `TagKey` — 7 mentions, toutes en commentaire |
| **résolution ordinal ↔ nom** | **PORTÉ et gardé** | `stream_events.step_id` / `group_id`, résolus **par NOM** contre la table versionnée, lèvent si le membre disparaît |
| **transport d'événements** | **STUB MORT** | `EventBus` : 3 méthodes définies, **0 appel** ; `BattleEvent` : **0 sous-classe**. Instancié **6 fois** — uniquement pour remplir le paramètre `execute(state, bus)` |
| **structure de groupes** (open/close, profondeur) | **absente à l'émission** | existe en **lecture** (`decode_lines` suit une pile ; le SQL 014 la matérialise) |
| **formatage texte** (les 4 formes) | **absent** | aucun writer |
| **résultats d'opération** | **dicts ad hoc** | **99** `execute()` répartis sur **11** formes de retour, dont **74 sans annotation** ; 7 `dict`, 6 `Optional[dict]`, 1 `list[dict]`… Aucune forme commune d'où dériver un flux |

Le point le plus trompeur est le bus : il **paraît** exister — il est importé dans 25 modules
d'opération, instancié, passé partout. Mais `EventBus()` y est un **objet jetable** que la signature
exige ; rien ne s'y abonne et rien n'y publie. Une lecture par `grep` conclurait « couche présente » ;
la visite AST dit **0 appel**.

⚠ **Ces chiffres se re-dérivent, ils ne se citent pas** — et le rebase de cette PR l'a démontré sur
sa propre mesure : `execute()` est passé de **97 à 99** (non annotés 72 → 74) entre le commit de
lancement et `origin/master`, sans que rien ne touche à la couche stream. C'est précisément pourquoi
la tranche livre un **probe** et pas un tableau figé.

## 3. La couverture face à la grammaire réelle

**Non mesurable, et c'est le résultat** — pas un zéro. Il n'existe aucun registre d'émission à
interroger (`engine/streams/`, `engine/runner/streams/`, `engine/battlestream/` : aucun). Le probe
rend donc `PAS MESURE` sur les trois axes, jamais `0 / 104`.

La différence porte tout le chiffrage : « 0 couvert » suggère un émetteur présent et vide (coût =
remplir une table) ; « registre absent » dit qu'il faut **construire la couche** (autre ordre de
grandeur).

⚠ Le périmètre se dérive des **enums** (104 / 62 / 244), jamais de l'observé — le recensement live de
#477-r11 (16 / 21 / 83) est un **plancher**, cf. `#477-r13`.

## 4. L'identité des unités — l'affirmation de #477-r11 est RÉFUTÉE

`case-477r11` § 5b écrit : *« Sans aucun porteur : `visualId`, `squadId`, `rank` [...] le flux ne
nomme jamais l'unité [...] l'appariement repose sur l'ordre d'apparition ou sur la signature du kit,
jamais sur un identifiant. »*

**Montage** — le régime que personne n'avait joué : un roster à **kit dupliqué**
(`--p-units "adeptCanoness,adeptCanoness,adeptRetributor"`, accepté sans réserve), sur deux boards de
**tailles différentes**.

| board | tuiles | `Entity=` du flux | `squadId` d'`observeBattle` | concordance |
|---|---:|---|---|---|
| MC1_67 | 63 | 77, 79, 81, 83, 85 | 77, 79, 81, 83, 85 | **OUI** |
| C1_02 | 35 | 49, 51, 53, 55, 57 | 49, 51, 53, 55, 57 | **OUI** |

**Trois résultats, tous mesurés :**

1. **`squadId` A un porteur** — c'est le `Entity=` porté par **chaque ligne** du flux. Il n'est pas
   absent : il n'est simplement pas un `Tag=`. Un recenseur qui ne cherche un porteur que parmi les
   `Tag=` le manque — **même vice** que l'appariement par sous-chaîne déjà corrigé au § 5a de la même
   fiche. C'est `visualId` (le **nom du kit**, `adeptCanoness`) qui n'a effectivement aucun porteur.
2. **La signature du kit ne discrimine PAS.** Entre les deux `adeptCanoness` : **41 tags de kit
   strictement égaux** (stats, ids d'ability, niveaux). Seuls diffèrent l'`Entity=` lui-même et les
   ids d'objets dérivés (`Effect_Id` 97 vs 98, `Effect_SourceId` 81 vs 83). ⇒ **l'appariement par
   signature de kit, tel que #477-r11 le proposait, est IMPOSSIBLE dès qu'un roster porte un
   doublon** — et un tel roster est parfaitement légal.
3. ⇒ **Aucun canal d'identité supplémentaire n'est nécessaire.** L'appariement se fait sur `Entity=`,
   directement. La stratégie de comparaison de flux **tient**.

### Mais le point dur se déplace : l'id d'entité est un compteur d'allocation GLOBAL

35 tuiles ⇒ unités à **49**, 63 tuiles ⇒ unités à **77** — décalage exact de 28. L'id d'entité dépend
donc du **nombre d'entités créées avant** les unités.

⇒ **Un émetteur côté port doit reproduire l'ORDRE ET LE NOMBRE d'allocations d'entités ECS, tuiles
comprises.** Une seule entité de plus ou de moins, et **toutes** les lignes divergent. C'est la
contrainte structurante de l'émetteur, et elle n'était identifiée nulle part.

⚠ **Piège de mesure rencontré** : `MC1_67` et `C1_70` font **tous deux 63 tuiles** et rendent les
**mêmes** ids — lu trop vite, cela se serait conclu « l'id ne dépend pas du board ». Le probe impose
des boards de tailles distinctes et **dit explicitement** quand le point n'est pas mesuré.

## 5. Le chiffrage

### Ce qui borne l'émetteur, re-dérivé (jamais cité)

`ABILITY_CLASSES` = **104**, `ABILITY_ATTACK_TYPE` = **105**, kits complets **46 / 127**
(`audit_kit_coverage.py` : `avec-travail=81`, `items=100`). Un émetteur ne produit que le flux des
mécaniques **effectivement portées** : une ability absente du registre n'émettra jamais son groupe.

### Tranches livrables

| # | tranche | nature | volume mesuré | dépend de |
|---|---|---|---|---|
| **A** | **Mirror des 3 enums + writer de grammaire** — les 4 formes, indentation **4 espaces**, séparateur **LF**, tags triés | **mécanique** | 104 + 62 + 244 membres, table versionnée | rien |
| **B** | **Socle d'émission** — `StartGroup` / `Action` / `FinishGroup` + pile + profondeur, en remplacement du bus mort ; flush racine à profondeur 0 | **RE légère** | 3 fonctions natives nommées + `StreamCache$$SendRootGroupIfFinished` | A |
| **C** | **Allocation d'entités ECS** — reproduire l'ordre (tuiles, puis unités par pas de 2, puis effets) | **RE — le point dur** | inconnu : la factory d'entités n'a jamais été RE'd | B |
| **D…** | **Tags par famille** — un mirror 1:1 par helper natif | **mécanique par famille, RE par tag** | **10** `StreamHelper$$Get*Tags` (`GetAddUnitTags`, `GetDamageTags`, `GetRefreshEffectTags`, `GetResurrectUnitTags`, `GetAddOrUpdateShieldTags`, `GetAddScoreTags`, `GetRemoveShieldTags`, `GetReviveUnitTags`, `GetActiveAbilityStateUpdateTags`, `GetUpdateActiveAbilityModificationTags`) | B |
| **E** | **Le cliquet 3 états** (§ 6) | mécanique | — | A + B |

**Atteignable maintenant** : A, B, E — aucune ne dépend de la couverture de portage. Elles suffisent
à produire un flux comparable **sur le seul déploiement** (`System_GameSetup` : `AddPlayer`,
`AddTile`, `AddUnit`), qui est déjà un oracle utile et **entièrement déterministe**.

**Bloqué par la couverture** : D au-delà des familles dont les mécaniques sont portées, et tout
diff couvrant le **déroulé** d'une bataille. Avec 46/127 kits complets, un diff de flux entier serait
rouge presque partout dès le premier jour — d'où le cliquet.

**Le pari de C** est ce qui décide du coût réel : si l'ordre d'allocation ECS se reproduit
simplement (tuiles dans l'ordre du board, unités dans l'ordre du roster, pas de 2), l'émetteur est
essentiellement mécanique. Sinon, tout diff de flux entier est hors d'atteinte et il faut se rabattre
sur une comparaison **par groupe apparié**, plus faible. **C'est la question à trancher avant de
chiffrer la suite** — elle n'est pas tranchée ici.

## 6. La forme du cliquet — esquissée, non construite

Une comparaison de flux entier serait rouge presque partout. Donc **jamais un pass/fail** : **trois
états**, enregistrés partout dès le premier jour.

- **conforme** — les deux flux sont égaux sur le périmètre comparé ;
- **divergent CONNU** — la divergence est déjà **inscrite** dans un registre de divergences, avec sa
  cause nommée (mécanique non portée, tag non émis) ;
- **divergent NOUVEAU** — **le seul état qui rougit**.

Forme proposée : un registre versionné `<GroupType|StepType|TagKey> -> cause`, et le comparateur
**classe** chaque ligne divergente. Deux exigences, toutes deux tirées de fautes déjà mesurées :

1. **Le registre se PURGE tout seul.** Une divergence connue qui **cesse** de se produire doit
   rougir aussi (entrée périmée) — sans quoi le registre ne fait que grossir et finit par tout
   couvrir. C'est la leçon du seuil qui se dégrade en silence.
2. **Le non-comparé est PUBLIÉ, jamais implicite.** Ce que le port n'émet pas encore n'est pas
   « égal » : c'est **non comparé**, et ça doit se lire dans le rapport (§ 5 de #477-r11).

## Résidus

- ~~**#477-r16** — l'ORDRE D'ALLOCATION DES ENTITÉS ECS n'est pas RE'd.~~ **TRANCHÉ** :
  `docs/rl/case-477r16-allocation-entites-ecs.md`. Allocateur unique
  (`MatchComponent$$NextId`, pré-incrément), 9 sites d'appel exhaustifs, ordre fixé par
  `SetupGameOperation$$Execute`. Verdict **MÉCANIQUE** — la prédiction posée avant mesure tient
  9 critères sur 9, sur trois tailles de board. Le pas de 2 est **1 + nb de pieds**, pas « deux
  entités par unité ». Deux tables **statiques** du binaire entrent dans l'offset (résidu
  `#477-r16-r1`), et la boucle sur les pieds reste non confrontée (`#477-r16-r2`).
- **#477-r17** — **`visualId` (le nom du kit) reste sans porteur, et c'est sans conséquence pour le
  DIFF mais pas pour le DIAGNOSTIC.** Comparer deux flux ne demande pas le kit ; comprendre *quelle
  unité* diverge, si. La table entité → kit s'obtient d'`observeBattle` côté natif — le port devra
  l'exposer symétriquement, sinon un rapport de divergence nommera « l'entité 83 » sans dire que
  c'est le second `adeptCanoness`.

## Ce que je n'ai PAS fait

- **Aucun émetteur écrit** — la tranche mesurait, elle n'a rien porté.
- **`replaySteps` / `replayRngEvents` non confrontés** — livrés dans le bundle mais non déployés
  (`#477-r12` intact). Ma mesure n'en dépendait pas : `replayOutputStream` suffit.
- **Le déterminisme du flux n'a pas été re-mesuré** — établi par #477-r11, non recontesté ici.
- **La couverture des `GroupType` non observés** (`#477-r13`) reste un plancher : je n'ai joué aucun
  scénario destiné à l'élargir.
