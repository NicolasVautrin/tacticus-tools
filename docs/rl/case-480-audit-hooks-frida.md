# #480 — Audit de `frida/hooks/` à la lumière du flux de replay : rôles, redondance, angles morts

**Build** `rnca9r7q6c`, session Frida **7**, runner **226** (MC1_67, seed 777, `--record-replay`).
Probe : `scripts/python/probe_480_hooks_audit.py`. Tranche de **décision**, pas de refactoring.

## Verdict en une ligne

**Presque rien n'est redondant avec le flux, et c'est mesuré, pas concédé** : le flux est le canal
COMBAT/ÉTAT, et même sur ce terrain il **omet la topologie du plateau** — une troisième face
d'omissions que #477-r11 ne publiait pas. Le gisement réel de cet audit est ailleurs, et il est
double : **un angle mort de tri-état sur le capteur d'état le plus consommé** (`observeBattle`
rendait `ok:true` sur « pas de bataille »), et **une qualification périmée qui écarte 69 fichiers
versionnés et bundlés du périmètre d'audit** depuis quatre jours.

---

## 1. Le périmètre était FAUX — deux fois, et par deux causes différentes

### 1a. `hooks/scratch/` n'est plus gitignoré depuis #365 (2026-07-31, `774df416`)

`.gitignore` le dit littéralement : *« frida/hooks/scratch/ N'EST PLUS IGNORE — il est ENTREE DE
BUILD »*. Mesuré : **69 fichiers `.ts` versionnés**, et `controller.ts` en fait **67 imports
statiques** — ils sont donc **dans le bundle** (témoins vérifiés dans `dist/hooks.js` reconstruit :
`dumpComponentFields`, `dslNodeProbe`, `searchAllClasses`).

⇒ Conséquence directe et non triviale : les **142 erreurs TypeScript** de `hooks/scratch/` que
`case-477` (§8, §10.5) et `case-475` (§7) écartent en les disant *« dans `hooks/scratch/`,
gitignoré »* portent sur du **code versionné, importé statiquement et livré dans le bundle**. Le
compte total est inchangé (**146** erreurs, re-mesuré : 142 scratch + 3 `normalize-bc/debug-rpcs.ts`
+ 1 `rl/tensorizer.ts`) ; c'est sa **qualification** qui est périmée, et c'est elle qui fait passer
le lot pour hors périmètre.

### 1b. « 41 214 lignes » est un compte de lignes NON VIDES

Le chiffre vient de `Get-Content | Measure-Object -Line`, qui **ne compte pas les lignes vides**.
Mesuré : hors scratch, **43 523** lignes dont **2 307** vides ⇒ `43 523 − 2 307 = 41 216`, à 2 près
du chiffre cité (deux fichiers sans saut de ligne final).

| périmètre | fichiers | lignes |
|---|---:|---:|
| `frida/hooks/**` total | **194** | **45 805** |
| hors `scratch/` | 125 | 43 523 |
| `scratch/` | 69 | 2 282 |

⚠ **Ma première mesure a « confirmé le chiffre au chiffre près »** — parce qu'elle employait le
**même outil biaisé**. C'est `feedback_agreement_worthless_on_shared_stale_input` en miniature :
deux mesures qui partagent leur instrument s'accordent sans rien prouver. Le désaccord n'est apparu
qu'en changeant d'instrument (Python `splitlines()`), et le diagnostic n'a tenu qu'une fois la
**cause** de l'écart reproduite (le compte des lignes vides).

---

## 2. Ventilation par RÔLE — table ÉCRITE, jamais un critère par nom

**54 modules** exportent `register()`. La table vit dans le probe (`ROLES`) et **rougit sur tout
module non classé** : une entrée neuve force une décision au lieu de tomber dans un lot par défaut.

| rôle | modules | le flux le concurrence-t-il ? |
|---|---:|---|
| **ÉTAT** | 12 | oui, partiellement — c'est le seul terrain commun |
| **DÉCISION** | 12 | **non, par construction** (playbook/utilité/prédiction absents du flux) |
| **MONTAGE** | 14 | non — construit/pilote un runner, ne l'observe pas |
| **INFRA** | 12 | non — pump, IL2CPP, nav, rendu, crash |
| **SONDE** | 4 | non — exploration one-shot |

Le critère par nom est proscrit ici pour la raison mesurée en #477-r11 §5a (appariement par
sous-chaîne : **6 verdicts faux sur 8**) : `hit-trace`, `effect-bonus-trace`, `triggered-move-trace`
portent « trace » comme `dsl-trace`, mais les trois premiers observent l'**état** et le dernier la
**décision**.

**Enregistrement** : un seul module importé n'est **pas** enregistré — `features/movement-trace.ts`,
volontairement (commenté dans `controller.ts`, 39 `Interceptor.attach` sur
`EvaluateMovementInSteps`, lag de navigation visible). Son code reste dans le bundle : poids mort,
aucun hook posé.

---

## 3. REDONDANCE vs le flux — trois états, et la frontière est DÉRIVÉE

Le périmètre du flux est dérivé des **trois enums** (`GroupType` 104, `StepType` 62, `TagKey` 244),
jamais de l'observé — l'observé n'est qu'un plancher (#477-r13 ; mon flux : 25 actions, 83 tags).

| capteur | appels Python | verdict | ce qui le tranche |
|---|---:|---|---|
| `decisionView` | 2 707 | **NÉCESSAIRE** | face DÉCISION — **absente du flux par construction** |
| `combatSnapshot` | 1 198 | **NÉCESSAIRE** | `Defense`, `EvasionChance` : **0 TagKey** ; les 7 `Extra*` n'existent qu'en `_Modification*` (le delta, jamais la valeur courante) |
| `boardGraph` | 1 364 | **NÉCESSAIRE** | topologie franchissable : **0 TagKey** (cf. §3a) |
| `observeBattle` | 975 | **NÉCESSAIRE** | `visualId` (nom du kit) et `rank` sans porteur. ⚠ **PAS `squadId`** : #477-r15 §4 l'a réfuté — il est porté par le `Entity=` de **chaque ligne**, donc absent des `Tag=` mais bien présent (cf. §3b) |
| `dumpRng` | 677 | **NÉCESSAIRE (aujourd'hui)** | le flux dit *« a crité : non »*, jamais le tirage. Le canal PRNG existe mais son lecteur **n'est pas déployé** (§5) |
| `tileMeta` | 334 | **NÉCESSAIRE** | `elevation`/`isWall`/`isTemporary` : **0 TagKey** (§3a) |
| `aiPlaybookPredict`, `pairUtility`, `abilityTargets`, `aiMovableTiles` | 275 / 374 / 490 / 637 | **NÉCESSAIRE** | face DÉCISION |
| `hit-trace`, `scorer-damage-trace`, `effect-bonus-trace` | on-demand | **INDÉCIDABLE** | le flux donne le **`Amount` final par hit** ; ces capteurs décomposent **par étage** (canal du bonus, face attaquant/défenseur). Tant que « jamais fitter un scalaire, décomposer par étage » est la doctrine, le flux ne les remplace pas — mais il **borne** leur usage : le résultat final n'a plus à être tracé pour être vérifié |
| `winner-capture` | — | **INDÉCIDABLE** | `Action=FinishMatch` existe ; le vainqueur y est-il porté ? non mesuré |
| — | — | **REDONDANT : aucun capteur en entier** | — |

**Aucun capteur n'est intégralement redondant.** Le flux ne supprime pas de capteur ; il **change
la nature de la preuve** — il devient l'oracle de conformité, et les capteurs redeviennent des
instruments de *diagnostic* (répondre « pourquoi ça diverge ») au lieu d'instruments de *constat*
(« quelle valeur »).

### 3a. Une TROISIÈME face d'omissions, non publiée jusqu'ici : la TOPOLOGIE

#477-r11 §5 publie les omissions vis-à-vis de `StatType` (5a) et d'`observeBattle` (5b). **Rien
n'était écrit sur la face TUILE.** Mesuré des deux côtés :

- **dérivation, sur les QUATRE positions de la grammaire** (leçon du §3b — un porteur peut vivre
  hors des `Tag=`) : sur les 244 `TagKey`, `Elevation|Wall|Height|Temporary` rend **uniquement**
  `Tile_IsTerritory` (plus deux tags de score) ; sur les 62 `StepType`, les seuls membres liés au
  terrain sont `AddTile`, `AttackTile`, `RemoveUnitFromTiles`, `TerritoryCapture`,
  `TerritoryScoreModifierChange`, `HideDoorActivationTile` ; sur les 104 `GroupType`, `TileDamage`,
  `VolatileRockets`, `TerritoryCapture`. **Aucun** ne porte le relief, les murs ou le caractère
  temporaire — et l'`Entity=` d'un `AddTile` est l'**id de la tuile**, pas son relief ;
- **observation** sur le flux réel (123 022 car., 2 931 lignes) : chaque `Action=AddTile` porte
  exactement **trois** tags — `Tile_Column`, `Tile_Row`, `Tile_IsTerritory`.

⇒ Un comparateur de flux est **structurellement aveugle au relief, aux murs et aux tuiles
temporaires**. `tileMeta` / `boardGraph` sont donc nécessaires, et cette omission doit rejoindre la
liste publiée du §5 — sans quoi elle deviendrait une **projection implicite**, exactement ce que
#477-r11 met en garde de ne pas laisser s'installer.

### 3b. Note de rebase — la liste d'omissions de #477-r11 a bougé pendant cet audit

Cette tranche a été rebasée sur 27 commits, dont **#477-r15**, qui **réfute** un point que la
première version de cette fiche reprenait : *« le flux ne nomme jamais l'unité »*. Mesuré là-bas sur
un roster à **kit dupliqué** et deux boards de tailles différentes : `squadId` **a** un porteur —
le `Entity=` que porte **chaque ligne**. Il n'est pas absent, il n'est simplement **pas un `Tag=`**,
et un recenseur qui ne cherche un porteur que parmi les `Tag=` le manque.

⇒ Deux conséquences pour cet audit, et **aucune** n'annule le §3a :
- le verdict `observeBattle` **NÉCESSAIRE** tient, mais sur `visualId` et `rank` seulement ;
- la leçon se **généralise à ma propre mesure** : j'ai cherché les porteurs de `elevation` / `isWall`
  / `isTemporary` parmi les 244 `TagKey`. C'est le bon espace **pour ces trois champs-là** — je l'ai
  recoupé sur le flux réel, où chaque `Action=AddTile` porte exactement trois tags et où `Entity=`
  est l'**id de tuile**, pas son relief. Mais la règle à retenir est celle de #477-r15 : **un porteur
  peut vivre hors des `Tag=`**, et le recensement doit balayer les quatre positions de la grammaire
  (`Group=`, `Action=`, `Entity=`, `Tag=`), jamais la seule dernière.

---

## 4. ANGLE MORT TROUVÉ — `observeBattle` rendait `ok:true` sur « pas de bataille »

C'est le patron nommé par le brief (« un objet sans champ se lit *vide* au lieu de *pas mesuré* »),
sur le capteur d'état le plus consommé après `decisionView`/`combatSnapshot`.

**Mesure** (session 7, même minute, deux bras) :

| bras | `ok` | `counts.total` | `counts.tiles` | `err` |
|---|---|---:|---:|---|
| témoin — `runnerId: 226` (bataille réelle) | `true` | 158 | 63 | — |
| **`observeBattle({})`** — live, aucune bataille | **`true`** | **0** | **0** | **vide** |
| `runnerId: 999999` (inexistant) | `false` | 0 | 0 | `runner … not found` |

Le troisième bras est correct — c'est le **deuxième** qui ment : un consommateur qui vérifie
consciencieusement `ok` lit *« la bataille existe et elle est vide »*.

**Cause, lue dans le code** (`features/observe.ts`) : `obs.ok = true` est posé **inconditionnellement**
dès que le pointeur d'état est non nul. Les deux gardes en amont (`!runner`, `statePtr.isNull()`)
couvrent l'absence de runner, **pas** un `MatchState` sans entité.

**Corrigé ici** — critère `counts.total === 0`, le plus conservateur possible : une `MatchState`
réelle porte toujours ses tuiles (mesuré 63), donc ce cas ne peut désigner qu'un état non mesurable.
**Aucun changement** pour un appel portant un `runnerId` de runner monté — c'est-à-dire pour la
quasi-totalité des 975 sites appelants.
⛔ **INACTIF jusqu'à la prochaine fenêtre de reinject** (`frida/hooks/*`).

### 4a. Ce que le balayage du même patron a rendu ailleurs

Sondage **non destructif** (allowlist de lecteurs purs, `runnerId` inexistant — jamais les 321 RPC
en aveugle : `renderBudget` a déjà tué le process par `SetResolution`) :

- **8 lecteurs sur 9 rendent une erreur NOMMÉE** — `combatSnapshot`, `tileMeta`, `boardGraph`,
  `decisionView`, `unitAbilityStates`, `dumpRng`, `abilityTargets`, et `observeBattle` sur ce
  chemin-là. Le patron est donc **globalement bien tenu** ; le trou du §4 est une exception, pas une
  épidémie.
- `replayOutputStream` **lève** au lieu de rendre (`HTTP 500`) : pas un zéro rassurant — une panne
  opaque, moins grave mais moins diagnostique.
- **Angle mort assumé, à connaître** : la projection lourde de `combatSnapshot` reste **alive-only**
  par conception. Depuis #429-r1-r3-r1 les unités non vivantes sortent dans un bloc `unitsNotAlive`
  **minimal** (id + type + flags) — une unité **enfuie** a donc ses flags mais **aucune stat**.
  C'est écrit dans le code, ce n'est pas caché ; ça reste une frontière à ne pas oublier.

---

## 5. Ce qui est ÉCRIT mais INERTE — mesuré en live, pas déduit

| symbole | source | session 7 | verdict |
|---|---|---|---|
| `replayOutputStream` / `…Status` | présent | **répond** (`recorderArmed`, 123 022 car. lus) | déployé, opérationnel |
| `replaySteps` | présent | **HTTP 500 — absent** | #477-r12 **confirmé en live** |
| `replayRngEvents` | présent | **HTTP 500 — absent** | #477-r12 **confirmé en live** |

Le contenu des événements PRNG reste donc **réduit à un compte** (24 sur mon runner), et la découpe
en pas reste un delta au lieu d'être **nommée par son message**.

⚠ **Distinction que cet audit a dû établir pour ne pas conclure faux** : `replaySteps` **est** dans
le bundle qu'on **reconstruit** (vérifié, `dist/hooks.js` rc 0, 1 145 414 o) et **absent** de la
session **injectée**. « Dans le bundle » et « dans la session » sont deux mesures différentes ;
seule la seconde dit si un capteur existe pour un appelant. **Rien aujourd'hui ne rend cette
seconde mesure** autrement qu'en appelant le RPC et en lisant un `500` — cf. §8, recommandation R3.

---

## 6. Adresses épinglées — VERT, avec une nuance que le cliquet ne rend pas

`probe_475_pinned_addresses.py` **re-joué** : **rc 0**, 194 fichiers balayés, **0** site
d'arithmétique d'adresse hors du foyer, **14 pins** cohérents avec la table versionnée de leur
build. L'affirmation du `CLAUDE.md` tient ; les 6 adresses périmées de #475 sont résorbées.

**La nuance** : le cliquet valide le pin contre son build **DÉCLARÉ** — c'est son contrat, et il est
juste. Il ne dit pas combien de pins sont **utilisables aujourd'hui**. Mesuré :

| build déclaré | pins | état sur `rnca9r7q6c` |
|---|---:|---|
| `rnca9r7q6c` | 13 (`scorer-damage-trace.ts`) | **ACTIFS** |
| `gqfc5mff6c` | 1 (`modifier-observe.ts`) | **REFUSÉ** — ce chemin est désarmé, et c'est le comportement voulu |

C'est le résidu **#475-r2** déjà nommé (re-mesurer `FUN_1800267c0` en session ghidra). Rien de neuf
à ouvrir : la mine est désarmée proprement, elle attend juste sa re-dérivation.

---

## 7. Tables de noms — VERT, mais le cliquet ne pèse qu'un sens sur deux

`probe_252_hook_name_tables.py` : **rc 0**, les **6** tables collent au build courant, et mieux que
« collent » — elles sont en **bijection exacte** (table = jeu, `faux = 0`, `hors-enum = 0`,
`absents-de-la-table = 0` pour les six). Le gisement « 66 noms faux sur 102 » n'a **aucun
équivalent** ici.

**Ce que le cliquet contrôle réellement** (la question posée) : `derive = True` si `faux or absents`
— c'est-à-dire **table → enum** (les noms qu'elle porte sont-ils justes) et les entrées disparues.
La troisième quantité, `manquants` (**enum → table**), est **calculée, affichée, et n'entre pas dans
le verdict**.

⇒ Aujourd'hui `manquants = 0` partout, donc le trou est **théorique**. Mais c'est la forme exacte
d'une garde qui se dégrade en silence (`feedback_threshold_guard_decays`) : un build qui **ajoute**
des membres laisserait le cliquet **vert** avec des tables incomplètes. Les six tables étant déjà en
bijection, faire peser `manquants` **ne produirait aucun faux positif** — c'est un cliquet qui
verrouille un acquis, pas une exigence neuve. **Recommandation R4**, non appliquée ici : elle touche
le verdict d'un garde partagé, et ce n'est pas une tranche de refactoring.

Le consommateur, lui, dégrade proprement : `abilityName` / `triggeredAbilityName` rendent
`id:<n>` sur un id inconnu — l'ordinal reste lisible, rien ne se tait.

---

## 8. Code mort — une hypothèse RÉFUTÉE, un vrai candidat trouvé

**`features/sim-engine.ts` (1 594 lignes) est PLEINEMENT ATTEIGNABLE — hypothèse réfutée.** Ses
**15 RPC ont tous des appelants**, et pas des appelants décoratifs : `frida/host/router.ts` (routes
HTTP), le front `frida/public/`, et surtout **`frida/host/drain.ts`** — `simBuildPreview` /
`simDisposePreview` servent le mécanisme **DRAIN** lui-même. La mémoire du projet range
« replay/inner-sim » en historique ; elle ne désigne pas ce module.

**Le vrai candidat est `features/sim.ts`** (200 lignes, 1 `Interceptor`) : ses trois RPC — `sim`,
`commit`, `simAndCommit` — n'ont **aucun appelant**, nulle part (host, front, Python, docs, tests).
C'est l'inner-sim historique, celui qui applique sur le runner **live**.
⚠ Verdict borné : ses noms sont **génériques** (`commit` matche 137 fois côté Python, tous faux
positifs) — le compte n'est concluant qu'avec un critère par forme d'appel RPC, ce qui a été fait.

**121 RPC sur 321 (38 %) n'ont aucune mention hors `frida/hooks/`** — 122 avant le rebase, 121 après :
ces chiffres se **re-dérivent**, ils ne se citent pas. C'est un **axe de tri, pas un
verdict** : ~45 sont les enveloppes `dump*` de `controller.ts` autour de `scratch/`, sondes
one-shot appelées à la main — leur absence d'appelant est leur nature, pas leur mort.

---

## 9. Liste priorisée — par valeur au regard de l'OBJECTIF (comparateur de flux)

### Sans fenêtre de reinject (Python / docs / outillage)

| # | action | valeur |
|---|---|---|
| **R1** | **Porter l'ÉMISSION du flux côté Python.** ⚠ **Question tranchée pendant cette tranche par #477-r15** : **rien n'est porté** — la mig 014 est un *consommateur*, et le bus d'événements est un **stub mort** (0 appel). Ce n'est donc pas « remplir une table » mais **construire la couche**, chiffrée là-bas en 5 tranches (A : mirror des enums + writer ; B : socle d'émission ; **C : ordre d'allocation des entités ECS — le point dur** ; D : 10 `StreamHelper$$Get*Tags` ; E : cliquet). Ne pas re-poser la question ici. | **la plus haute** — tout le reste en dépend |
| **R2** | **Publier l'omission TOPOLOGIE** (§3a) dans la liste du §5 de `case-477r11`, et l'ajouter à la table d'appariement du probe, qui rougit sur un champ non apparié. Sans ça, un futur comparateur la traite en silence comme « comparée ». | haute — évite une projection implicite |
| **R4** | Faire **peser `manquants`** dans le verdict de `probe_252` (§7). Zéro faux positif attendu. | moyenne — verrouille un acquis |
| **R5** | Corriger la **qualification périmée** « `hooks/scratch/` gitignoré » dans `case-477` et `case-475`, et décider du sort des **142 erreurs tsc** d'un répertoire versionné et bundlé. | moyenne — le périmètre d'audit est faux tant qu'elle traîne |
| **R6** | `features/sim.ts` : 3 RPC sans appelant (§8). Retrait ou justification écrite. | basse |

### Exigeant une fenêtre de reinject (`frida/hooks/*`)

| # | action | valeur |
|---|---|---|
| **F1** | **Activer le correctif `observeBattle`** de cette PR (§4) et **re-jouer** les trois bras du tableau : le bras `observeBattle({})` doit rendre `ok:false` + `err` nommée, le témoin `runnerId: 226` rester `ok:true` / 158 entités. | haute — corrige un zéro rassurant sur 975 sites |
| **F2** | **Confronter `replaySteps` / `replayRngEvents`** (#477-r12, §5). Condition de retournement déjà écrite : `messageCls` non nul par pas et `recordedPlayerIds == [11]`. Donne le **contenu** PRNG et la découpe nommée. | haute — c'est le canal §6 de #477-r11, aujourd'hui réduit à un compte |
| **F3** | `#475-r3` — confronter `bucket-audit` (corps gshared via instance inflatée), et `#475-r2` — re-dériver le pin `gqfc5mff6c` de `modifier-observe` (§6). | moyenne |
| **R3** | **Capteur MANQUANT, nommé ici** : rien ne dit **quels RPC sont réellement exposés par la session**. Un appelant n'obtient qu'un `HTTP 500` opaque, indiscernable d'une erreur d'exécution (§5). Le remède est un endpoint host rendant `Object.keys(script.exports)` — **côté host, donc pas de reinject**, mais un redémarrage du host, qui est le même geste réservé. | moyenne — supprime une classe entière d'opacité |

### Capteurs manquants du backlog, reclassés au regard de l'objectif

⚠ **Deux de ces lignes de backlog ont été CONFRONTÉES au code avant d'être rangées** — une ligne de
backlog affirme des faits, et ils sont parfois faux (`feedback_verify_task_freshness_before_dispatch`).
Résultat : **une confirmée, une déjà résolue**.

| item | rang | pourquoi |
|---|---|---|
| `readEffectsByTile` jette `removed` inconditionnellement (#425-r2) | **1er** | **CONFIRMÉ au code** — `game/effects.ts:562` : `if (info && info.removed) continue;`, **sans échappatoire**, alors que la ligne suivante conditionne `!active` à `includeInactive`. Or le flux porte `LoseEffect` / `DeactivateEffect` / `UpdateEffectTurns` : la **fin de vie** d'un effet est exactement ce qu'un comparateur confrontera en premier, et ce capteur-là la jette |
| ~~`EffectComponent+0x48` — cibles d'une entité-effet (#366-r1)~~ | **RÉSOLU — à retirer du backlog** | le capteur **existe** : `readEffectTargetIds` (`game/effects.ts`), publié en `targetIds`, et avec un **tri-état correct** (`null` = illisible / `[]` = mesuré et vide / taille aberrante ⇒ `null`) |
| `decodeRule` publiant `hex: "0x0"` (#444-r1) | 2e | face DÉCISION — hors flux, donc **jamais** couvert par le comparateur ; reste un zéro rassurant à corriger, et le flux ne le fera pas à notre place |
| `aiPlaybookPredict` ne prend pas une MoW pour caster (#350-r3c) | 3e | face DÉCISION, hors flux |
| canal d'ENTITÉ pour les armes / stats résolues des MoW | 4e | recoupe partiellement les `UnitStats_*` du flux — **à re-qualifier après R1**, pas avant |

---

## 10. Ce que je n'ai PAS fait

- **Aucun refactoring.** Les six (huit, re-mesuré) modules au-dessus du seuil de ~1 000 lignes sont
  **laissés tels quels** : la doctrine dit de scindre *quand ça passe le seuil*, et aucun d'eux n'a
  montré de défaut **imputable à sa taille** dans cet audit. Les scinder maintenant serait du
  pré-scindage.
- **Les 121 RPC sans appelant ne sont pas tranchés un par un** — seul `sim.ts` l'a été.
- **`winner-capture` vs `Action=FinishMatch`** : laissé INDÉCIDABLE, non mesuré.
- **Le flux n'a pas été confronté à un flux Python** — il n'y en a pas encore (R1).
- **Aucun reinject, aucun redémarrage du host.** Le correctif du §4 est livré **inactif**.

## Résidus

- **#480-r1** — **Le périmètre `hooks/scratch/`** : 69 fichiers versionnés et bundlés portant
  **142** erreurs tsc, qualifiés « gitignoré » par trois case-docs. Trancher : soit ils rentrent
  dans le contrat de typage, soit leur exclusion est **écrite et motivée** au lieu d'être héritée
  d'une propriété git qui a changé. *Condition de retournement* : `npx tsc -p tsconfig.hooks.json
  --noEmit` rend un compte **stable et assumé**, et plus aucune case-doc ne les dit gitignorés.
- **#480-r2** — **`probe_252` ne pèse qu'un sens de la bijection** (§7). *Condition de
  retournement* : ajouter un membre d'enum absent des tables fait **rougir** le cliquet.
- **#480-r3** — **Aucune mesure de « quels RPC la session expose »** (§5, R3). *Condition de
  retournement* : un appel à un RPC absent se distingue d'une erreur d'exécution **sans lire le
  code du bundle**.
- **#480-r4** — **Friction de worktree** : `npm run build:hooks` échoue (`ENOENT`) sur un worktree
  frais tant que `frida/dist/` n'existe pas. Bénin, mais il contredit « un worktree frais est
  RUNNABLE par son seul checkout » pour la voie bundle. *Condition de retournement* : `npm ci` puis
  `npm run build:hooks` rc 0 sans `mkdir` manuel.
- **#468-r10** (ouvert par cette tranche, hors périmètre d'audit) — **l'allocateur de numéros est
  aveugle aux réservations des agents EN VOL**. Cette tranche en est la mesure : elle a été écrite
  entière sous `#479`, numéro que `probe_468 --suggere` lui a donné **et** a donné au ménage des
  branches orphelines (PR #659, mergée pendant). Collision **double** — la racine **et** le résidu
  `r1`. Renumérotée en `#480` avant merge. Détail, parades évaluées et condition de retournement :
  au backlog.

## Note de renumérotation

Cette fiche a été écrite sous `#479` et renumérotée en **`#480`** avant merge : `#479` était pris
par `case-479-branches-orphelines.md` (PR #659), mergé pendant la tranche. Les artefacts `#479`
du dépôt appartiennent donc **au ménage des branches**, pas à cet audit — et le résidu `#479-r1`
du backlog n'est **pas** l'un des miens.
