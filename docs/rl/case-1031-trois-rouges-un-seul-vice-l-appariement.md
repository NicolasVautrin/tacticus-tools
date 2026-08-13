# #1031 — Trois rouges de `master`, un seul vice : l'APPARIEMENT de sonde

Trois cliquets rouges depuis plusieurs tours — `test_enum_ordinal_ratchet` (via `probe_283`,
`FAIL (5)`) et les deux `test_etage3_aucune_citation_fausse` de `test_477r24r1` et
`test_477r25`. **Aucun des trois n'accusait une faute du dépôt.** Les cinq sites signalés se
répartissent en **quatre faux positifs d'appariement** et **un seul vrai** défaut.

Un appariement de sonde rapproche deux choses écrites **près** l'une de l'autre et conclut
qu'elles se rapportent l'une à l'autre. `probe_283` s'en défend explicitement — « un gate ne se
fonde pas sur ce qu'un texte porte PRÈS, mais sur ce qu'un auteur a DÉCLARÉ » — et c'est
pourtant par là que les trois sont tombés.

## 1. `probe_283` étape 2 — le figeage CONFRONTÉ dans le code

Quatre sites réclamés, `0 FAUX aujourd'hui, 4 a lire`. **Trois sont le cliquet que la doctrine
exige** :

    assert BOF.BookOfFateAbility.event_id == 38 == int(EventTriggerType.NormalAttack)

`_membre_vise` ne lit que la **prose** (tokens `COMMENT`/`STRING`), et c'est volontaire — une
*annotation* est du commentaire. Mais le dépôt écrit aussi le motif **inverse** : le membre en
égalité avec le littéral, **dans le code**. C'est exactement ce que le `CLAUDE.md` prescrit
(« le registre ne suffit pas — il faut aussi FIGER l'ordinal ÉCRIT AU SITE », le cran que
`probe_313` ne peut pas voir puisqu'il redevient vert dès qu'on régénère le mirror). Le
convertir le rendrait **tautologique** — `int(E.X) == int(E.X)` — donc **inerte** : on
détruirait le cliquet en croyant l'appliquer.

Cran posé (`_membre_enum_du_code`) : le membre est cherché sur la **chaîne entière** du
`Compare` — `a == 38 == int(E.X)` a trois opérandes et `visit_Compare` s'arrête au premier
couple qui mord. **Le vert est VÉRIFIÉ, jamais supposé** : le membre doit valoir exactement le
littéral sur le build courant. Sinon c'est un `FAIL`, et le plus grave des trois — le site se
croit gardé et ne l'est pas.

**Le quatrième site était un vrai** : `test_1023_omnissiahs_blessing_offline.py:86` écrivait
`== 48` **nu**. Le fichier fige bien `UnitRepaired == 48` — **quatre lignes plus haut**. Un
renumérotage aurait laissé ce site-ci pointer ailleurs pendant que l'autre ligne rougissait.
Corrigé au patron canonique du dépôt.

Effet : `4 a lire` → **0**, `+4 CONFRONTES` comptés et imprimés.

## 2. `probe_283` étape 5 — l'annotation n'annote que les QUOTES

Le `FAIL` accusait `test_981_vecteurs_de_fuite_offline.py:136`, qui écrit :

> `On(PreUnitFled)` passe la fuyarde TROIS FOIS (…) ; `On(0x34)` et `On(0x36)` passent …

Une annotation, deux ancres nues — **et la phrase les OPPOSE**. `0x34` est `UnitFled`, `0x36`
est `UnitDefeated`, tous deux **figés quatre lignes plus haut dans le même fichier** ; ni l'un
ni l'autre n'est `PreUnitFled`.

Premier cran essayé — *plus d'ancres que d'annotations ⇒ ambigu* — **ne mord pas** : `On(0x36)`
est sur la ligne 137. Il est conservé (il garde une autre forme, sur les quotes) mais ce n'est
pas le discriminant.

Le discriminant est le **TYPE d'ancre**, et il tient à la raison d'être de l'annotation.
#420-r5 l'a créée pour un manque précis : *une quote verbatim ne peut pas porter son membre
dedans sans cesser d'être verbatim*. Une ancre `On(<n>)` n'a pas ce manque — sa voie propre est
la forme nommée `On(<n> = <Membre>)`, que l'étape 4 confronte, et que #420 a posée sur 220 sites.

**La mesure tombe des deux côtés, et c'est elle qui tranche.** Le dépôt ne portait que **deux**
ancres `On(<n>)` appariées à un `On(<Membre>)` de la même ligne, **toutes deux en prose
narrative** :

| site | verdict rendu | réalité |
|---|---|---|
| `martial_apotheosis.py:34` | `ancree` (vert) | juste **par accident** |
| `test_981_vecteurs_de_fuite_offline.py:136` | `perimee` (rouge) | faux **par accident** |

Un mécanisme dont la moitié des verdicts est un accident ne garde rien. Les **23** autres
ancrées sont toutes des quotes `FUN_`, où l'annotation est bien ce que l'auteur a posé *pour*
elles.

Effet : `24 ancrées → 23` (toutes `FUN`), `1 FAIL → 0`, `1473 stables → 1474`. Le gate #420-r5
mord **toujours** sur une quote (contre-épreuve jouée).

## 3. `477-r24-r1` — l'élision PARTIELLE

    transfer_damage.py:11   -> Core.Services.OperationProcessor$$TransferDamage(..., hitIndex)

lu « 2 arguments », confronté aux 6 de la signature. Le cran d'élision **existait** — pour
`(...)` **total**. L'élision **partielle** — élider le début, nommer ce qui intéresse — est la
forme réellement écrite, et elle DÉCLARE ne rien énumérer. Même lecture que
`probe_283._FUN_PUB`, qui accepte déjà `FUN_...(0x50, …, 0x3d)`.

**Aucun trou ouvert** : un site qui écrit tous ses arguments reste confronté ; seul celui qui
déclare une élision sort du gate — il ne peut pas mentir sur ce qu'il n'affirme pas.

⚠ **Le helper était RECOPIÉ dans les deux probes**, et c'est précisément pourquoi son cran n'a
été corrigé qu'à moitié. Il est désormais **importé du foyer**, comme `_appel`, `_entre` et
`_regex_noms` l'étaient déjà. Un cran dupliqué se corrige à moitié.

## 4. `477-r25` — deux référentiels de slots sur une ligne

`case-978-faces-decision-thousandsons-eldar.md:37` :

> **slot 23 = `Select`**, **slot 24 = `Count`**, recoupés par `ITargetsSelector` (slots 0 et 2)

**Les deux référentiels sont EXACTS**, lus au `global-metadata.dat` de `rnca9r7q6c` :

| type | `Select` | `Count` | `SelectTile` | `SelectFirst` |
|---|---|---|---|---|
| classe `IdunBattle.DSL.TargetsSelector` | 23 | 24 | 16 | 5 |
| interface `IdunBattle.DSL.ITargetsSelector` | 0 | 2 | 12 | 1 |

Le probe rattachait 23/24 à la seule interface **nommée sur la ligne** — le vice déjà mesuré
pour `AActiveAbility`, dont le commentaire du probe dit mot pour mot : « il RATTACHAIT ces
slots à l'interface voisine citée sur la même ligne, et rendait FAUSSES deux citations JUSTES ».

⚠ **L'énoncé du backlog est donc RÉFUTÉ** : `#934-r2` décrit ce rouge comme « citation fausse
dans `case-978:37` ». La citation est juste ; c'est l'appariement qui ne l'était pas.

⚠ **Et le remède d'`AActiveAbility` — un alias de récepteur — est REFUSÉ, mesure à l'appui.**
Le dépôt qualifie **majoritairement par le nom de CLASSE** une méthode dont il cite le slot
d'**INTERFACE** : `backlog.md:438` (« le slot de vtable 12 du sélecteur EST
`IdunBattle.DSL.TargetsSelector$$SelectTile` » — 12 = interface, la classe dit 16) et
`backlog.md:690` (« `slot 1` = `…TargetsSelector$$SelectFirst` » — 1 = interface, la classe dit
5). L'alias aurait retourné ces **deux citations JUSTES** en rouge : on aurait déplacé la faute,
pas fermé le gisement.

D'où `REFERENTIELS` — une table **LUE**, jamais appariée à un récepteur, qui alimente le verdict
que le probe sait déjà rendre : « JUSTE, mais sur `TargetsSelector` (le site écrit
`ITargetsSelector`) », **ni vert ni rouge, et LISTÉ**. C'est le seul verdict que la mesure
autorise. Régénération de l'entrée versionnée **purement additive** : 20 lignes ajoutées, **0
modifiée** (les slots `0xffff`, non virtuels, sont écartés — ils n'indexent rien).

## 5. Ce que fermer (4) a DÉCOUVERT — deux rouges empilés derrière une assertion

`test_etage3_aucune_citation_fausse` assertionne `faux_nom` **puis** `faux_arite`. Tant que le
premier tombait, le second n'était **jamais évalué**. Deux rouges d'arité vivaient là,
invisibles, dans `heavy_rail_rifle.py`.

Convention mesurée sur les **104** citations à arité confrontable : **43/43** concordantes quand
le récepteur est collé devant, **59/61** sans récepteur — la parenthèse porte les **arguments**,
le récepteur est implicite. Ces deux lignes y mettaient le **récepteur** : `Calculate` prend
`(entities: AbilityEntities, result: OperationResult)`, et `hitsNode` est le `this`.

Récepteur remis devant, arguments **élidés** — ce corps n'a pas été relu, donc on ne les devine
pas depuis la signature. Le slot et le nom, eux, étaient justes.

## 6. Le trou de rattachement — CHIFFRÉ

`probe_283` **est** dans `scripts/ratchets.ps1`, en six entrées à déclencheurs ventilés. Ce qui
manque est en aval : il n'entre pas dans les passes de merge, et c'est par là qu'un ordinal en
dur est passé dans un fichier mergé le jour même.

Le coût annoncé (161,8 s pour `exec` + `prose` + `on`) est une mesure **à froid**. Le cache
`verdict_cache` est **versionné** (`scripts/cliquets-cache/`), donc partagé entre agents et
merges. Re-mesuré à cache chaud le 2026-08-13 :

| entrée | à froid (doc) | **à cache chaud** | ce qu'elle garde |
|---|---|---|---|
| `diff` | 1,1 s | **0,4 s** | compteur |
| `mirror` | 32,6 s | **2,6 s** | **exécutable** |
| `exec` | 80,0 s | **4,6 s** | **exécutable** ← *l'entrée qui a manqué* |
| `tables` | 12,3 s | **21,0 s** | **exécutable** |
| `prose` | 66,1 s | **127,4 s** | prose (compteur ; seul 4bis est un gate) |
| `on` | 15,7 s | **29,1 s** | prose |

**Proposition** : ajouter les **trois entrées exécutables** (`mirror`, `exec`, `tables`) à la
passe de merge — **28,2 s**, soit moins que `test_477r24r1` seul (**52,9 s** dans
`ratchets-457-durations.json`, et celui-là est déjà joué). `exec` seul — celle qui aurait
attrapé le site fautif — coûte **4,6 s**. Les deux entrées chères gardent de la prose et peuvent
rester hors passe de merge. Décision d'orchestration, non appliquée ici.

## Gardes

`scripts/python/tests/test_1031_appariements_de_sondes_offline.py` — **25 tests**, un mutant par
cran, chacun reproduisant le rouge qu'il ferme :

* figeage **menteur** (littéral ≠ ordinal du membre nommé) → `FAIL`, et non `CONF` ;
* `annotation_de_ligne` en régime `FUN` sur la ligne de `test_981:136` → `perimee` (le faux
  rouge) ; en régime `On` → `nue` ;
* `_ELISION` neutralisé → `(..., hitIndex)` recompte **2** ;
* table `TargetsSelector` retirée → `AUCUNE METHODE (hors table, 15 slots)`.

Plus les non-régressions qui auraient signé une fermeture par **désarmement** : le gate #420-r5
mord toujours sur une quote, `_compter_args` compte toujours exactement ce qui est énuméré, un
ordinal **nu** reste réclamé, et un référentiel n'est **jamais** un récepteur.

Ce fichier entre à l'`ALLOWLIST` de `probe_283`, nommément et avec sa raison : ses échantillons
**portent** une quote périmée et une ligne à deux ancres — ce sont les données qui prouvent que
le gate mord encore. Un contrôle qui rougit sur son propre artefact fait renoncer à des mesures
justes.

## Résidus

* **`#1031-r1`** — les **261** ancres `On(<n>)` nues restent indécidables (résidu `#283-r1`,
  inchangé). La voie de sortie est écrite : les réécrire en `On(<n> = <Membre>)` les fait passer
  à l'étape 4, où elles sont confrontées. `martial_apotheosis.py:34` et
  `test_981_vecteurs_de_fuite_offline.py:136` sont désormais dans ce lot.
* **`#1031-r2`** — les arguments réels des deux appels de formule de `heavy_rail_rifle.py` ne
  sont pas lus (élision assumée). Exige une relecture de
  `IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$EvaluateNonComparable`.
