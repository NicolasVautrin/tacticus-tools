# #463-r1 — le cliquet qui ROUGIT sur l'écart d'empreinte, et qui REFUSE de le refermer

## 1. Le fait

Rien ne mesurait automatiquement les poids d'un fichier de test **offline neuf**.
`probe_457 --measure-missing` est un geste **explicite**, et son oubli est **silencieux** : le
fichier n'entre pas dans `scripts/ratchets-457-footprints.json`, donc il se rejoue **toujours**
sous `--since` (une entrée absente se lit « jamais mesuré », #486-r15) et prend le poids
**maximum** connu dans `bins_of`, déplaçant les vrais lourds.

**Cadence mesurée le 2026-08-07 : trois réouvertures en une journée**, toutes par nos propres
livraisons — 231→232 (`d9c430cb`), 232→233 (`94fd2b72`), 233→234 (`0010d088`). Ce gisement est
donc alimenté par notre **cadence de portage**, au même titre que `TARGETING_OPTIONS` et
`ABILITY_ATTACK_TYPE` — et il était le **seul des trois sans cliquet**.

## 2. ⛔ Ce que le cliquet REFUSE de faire, et le contre-cas qui l'interdit

**Il ne mesure PAS à la place de l'humain.** Le remède évident — lancer `--measure-missing` tout
seul sur le fichier manquant — est **faux**, et le contre-cas date du **même jour** que les trois
réouvertures.

Le 2026-08-07 au matin, le **même écart `N-1 / N`** appelait la réponse **inverse** (`40917cd0`) :
`test_act_of_faith_crit_resets_both_paths.py` n'était pas offline — c'était un test **live mal
nommé**, qu'il fallait **renommer**. Sa docstring disait « contrepartie OFFLINE » ; l'intention
l'était, l'implémentation non. Le filet de `probe_457` **désélectionne** les items live avant
qu'ils s'exécutent : le mesurer aurait gravé, dans un fichier **versionné**, une empreinte dérivée
d'une sélection **étroite** — donc un **faux vert durable**, exactement ce que le silence
d'aujourd'hui évite.

Le discriminant « ce fichier est-il offline ? » porte sur l'**intention de l'auteur** : il n'est
pas mécanisable. Un cliquet qui le tranche fabriquerait le défaut qu'il surveille. Celui-ci
**rougit, nomme, donne un indice lu, et rend la main** — il énonce les deux issues et n'en choisit
aucune.

## 3. L'indice est LU, jamais COMPTÉ — et son angle mort est mesuré

Un grep `live_session|build_runner|rpc` matche **aussi la prose** : vécu sur
`test_524r1_bond_sous_effets_offline.py`, où `rpc` vivait dans une chaîne de message. Deux étages,
qui **disent tous deux sur quoi ils ont matché** :

1. la **réclamation de fixture**, lue dans la **signature** (`ast`) — pytest résout une fixture par
   le nom du paramètre, donc `def test_x(live_session)` est un fait, pas une correspondance de
   texte. `@pytest.mark.usefixtures("host")` compte pareil. L'ensemble des fixtures live est
   **dérivé des `conftest.py`** (fermeture transitive depuis `probe_457.LIVE_FIXTURE_ROOT`), jamais
   une liste écrite ;
2. les autres occurrences, classées par **type de token** (`NAME` / `STRING` / `COMMENT`) avec leur
   ligne, bornes de mot comprises (sans elles, `host` matcherait `ghost`).

⚠ **Et l'absence de réclamation n'est PAS une preuve d'offline.** Re-dérivé à chaque exécution et
**imprimé** : **90 des 513** `*_live.py` du dépôt (17,5 %) n'en réclament aucune non plus — ils
montent leur runner à la main, ou par une fixture **locale** qui appelle un probe. C'est la limite
même qui a fait **réfuter** la clôture de fixtures comme critère de périmètre pour `probe_457`.
Sans ce chiffre, « aucune réclamation » se lirait « donc offline », et le cliquet aurait tranché
**en creux** — par une absence de preuve présentée comme une preuve d'absence.

**Contre-épreuve involontaire, et c'est la meilleure** : le premier fichier sur lequel le cliquet
a rougi est **son propre test**, qui écrit `def test_ko(live_session, rpc)` **dans une chaîne**
(le dépôt jetable de sa contre-épreuve). Un grep l'aurait classé live ; le cliquet a rendu
« 24 occurrences, **24 en PROSE, 0 en NAME** ».

## 4. Les deux sens, parce qu'une intersection ne montre pas ce qui déborde

Le capteur de `loop_status` rendait `couverts = len([r for r in perimetre if r in entrees])`. Sur
un périmètre intégralement couvert, une empreinte portant en plus des entrées **mortes** affichait
`N/N` et se **taisait**. Or ce qui déborde est précisément la **trace d'un renommage** en
`_live.py` — le contre-cas ci-dessus. Le cliquet ventile donc :

| sens | nom | effet |
| --- | --- | --- |
| périmètre \ empreinte | `NON MESURE` | rejeu permanent sous `--since`, poids maximum |
| empreinte \ périmètre | `FANTOME` | bénin pour la sélection, **trace d'un renommage** ; `--measure-missing` ne le purge pas, seul `--measure` le fait |

## 5. Un foyer, trois lecteurs — le doublon supprimé plutôt qu'un quatrième ajouté

Le périmètre offline était dérivé **trois fois séparément** : `probe_457.candidate_files` (ce que
`--measure-missing` **joue**), `loop_status.mesurer_empreinte` (ce que le hook `Stop` **compte**),
et ce cliquet en aurait fait une **quatrième**. Deux dérivations d'un même critère ouvrent un écart
**silencieux** : le capteur mesurerait un périmètre pendant que l'outil en joue un autre.

`probe_463r1_ecart_empreinte_offline.perimetre_offline` est donc **le** foyer, et ses trois
lecteurs l'importent. La fonction est **pure** (elle prend le texte de `git ls-files`), ce qui
laisse à chacun **sa** façon d'interroger git — `MontageImpossible` pour `probe_457`, cache TTL et
tri-état pour `loop_status`.

Le module reste **léger** : `ast` / `tokenize` / `argparse` y sont **différés**, et il n'importe
**ni `pytest` ni `repo_read`**. Il ne va même pas jusqu'à importer `probe_457` — mesure du
2026-08-07, cet import coûte **1,53 s** en process frais, pour **deux littéraux** ; son contrat
(`FORMAT_EMPREINTE`, `LIVE_FIXTURE_ROOT`) est **lu dans son source** par `ast` (0,015 s), et un
test **importe pour de vrai** afin de confronter ce qui est extrait à ce que l'import rend — sans
ce cran, l'optimisation aurait la forme exacte d'une recopie qui dérive en silence.

## 6. Le geste recommandé était IMPRATICABLE là où il est lu

Découvert en **appliquant** le geste que le cliquet nomme. `logs/` est **gitignoré** : un worktree
d'agent n'a **jamais** de poids. Le critère « sans poids » valait donc pour **tout le monde**, et
`--measure-missing` retenait **235 fichiers sur 235** — un `--measure` complet (~976 s) là où le
mode existe pour en coûter quelques secondes. **Le cliquet aurait recommandé un geste de 16 min à
un lecteur qui en attendait 15 s** ; il se serait fait désarmer.

C'est le **tri-état** du dépôt appliqué aux poids : `{}` parce que le **fichier est absent** n'est
pas `{}` parce qu'aucun fichier n'a de poids. Depuis, `_measure` distingue les deux, **le dit**, et
retient le seul critère applicable — l'**entrée d'empreinte**.

| régime | fichiers joués | mur |
| --- | --- | --- |
| avant | 235 / 235 | ~976 s |
| après | **1 / 235** | **15 s** |

Corollaire : **aucun fichier de poids partiel n'est écrit** dans ce régime. Une entrée unique
fixerait `defaut = max(weights.values())` de `bins_of` sur une valeur non représentative — **pire**
que pas de poids du tout, où le repli md5 répartit par nombre et reste honnête.

## 7. Le câblage, et pourquoi ces deux points-là

- **Hook `Stop`, via `loop_status`** — le déclenchement **automatique**. Le signal existait déjà
  (#486-r15) ; il gagne les trois manques : il **nomme** les fichiers, voit l'**autre sens**, et ne
  **tranche plus** (il disait « regenerer : `--measure-missing` »).
- **Passe de test** — `tests/test_463r1_ecart_empreinte_offline.py`, dont l'étage 7 confronte
  l'**arbre réel** (un `git ls-files` et une lecture JSON, aucun test rejoué).
- **CLI** — `python probe_463r1_ecart_empreinte_offline.py`, jouable seul, **hors**
  `TACTICUS_ALLOW_RATCHETS` : ce refus garde `probe_457` parce qu'il coûte ~900 s ; celui-ci
  coûte 0,5 s de travail (le poste dominant est le `git ls-files`, 0,19 à 0,66 s selon la
  contention sur le `.git/` partagé).

**Aucun doublon ajouté** : la recopie du filtre de périmètre disparaît de `loop_status`.

## 8. Aucune allowlist, aucune échappatoire — et c'est une mesure

#486-r15 a dû poser une **dette versionnée** parce que l'obligation sèche rendait `master` rouge
sur 711 fichiers. Ici, l'écart mesuré sur `master` au 2026-08-07 est **0 manquant / 0 fantôme**
pour 234 fichiers : l'obligation sèche est **déjà satisfaite**, donc aucune dette n'est nécessaire,
et en inventer une fabriquerait d'avance le trou par lequel le gisement revient. Deux tests le
gardent : l'un rejoue le cas rouge sous trois variables d'environnement du dépôt, l'autre balaie le
source (`os.environ` en position exécutable = 0) — une liste de noms ne montre jamais celui qu'elle
a oublié.

## 9. Contre-épreuves

- **Le cliquet rougit pour de vrai**, sur un dépôt git **jetable** (vrai binaire, vrai git) :
  entrée retirée → `rc 1` + fichier nommé ; entrée fantôme → `rc 1` ; format inconnu → `rc 1`
  **sans accuser aucun fichier** ; git absent → `rc 99` ; empreinte absente → `rc 99`. La **borne**
  (empreinte complète → `rc 0`) est ce qui interdit à un cliquet qui rougirait toujours de passer
  tous les cas.
- **Chaque mutation a mordu** : chaque étage assertionne le **non-vide** de son propre témoin avant
  d'exiger le rouge. Un test qui rougit sur un ensemble vide passerait pour vert.
- **In vivo** : le cliquet a rougi sur **son propre fichier de test**, l'a nommé, et son indice a
  correctement classé en PROSE les occurrences que le fichier porte dans des chaînes.
- **Sortie ASCII** sous test, sur le chemin **rouge** (celui qui imprime le plus), pas sur le
  `PASS` d'une ligne.

## 10. Résidus

- **`#463-r2`** (ouvert par #463, toujours ouvert) — la marge d'équilibre `1,35` n'a pas été
  re-dérivée.
- **Rouges PRÉEXISTANTS de `master`, mesurés le 2026-08-07 sur `3a09dc1d`** — non ouverts ici,
  hors périmètre, **nommés** : `probe_486r15` rougit sur
  `tests/engine/runner/test_501_might_from_below_offline.py` (1 chemin) et
  `tests/engine/test_524r1_bond_sous_effets_offline.py` (16 chemins), tous deux **déclarés trop
  étroits**. `tests/test_486r15_empreinte_par_entree_offline.py` en faisait partie (2 chemins :
  `verdict_cache.py`, `scripts/ratchets-457-footprints.json`) et a été **réparé ici**, parce que
  cette tranche le touchait de toute façon : 3 fichiers en faute → **2**. Le mécanisme est celui
  que porte `#486-r20`.
- **`probe_486r12` rend `rc 99`** (27 entrées non mesurées) — **identique sur la référence**, donc
  préexistant et non causé par cette tranche.
