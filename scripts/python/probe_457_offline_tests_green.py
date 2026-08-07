"""#457 -- CLIQUET : TOUT fichier de test qui n'est pas `_live.py` doit etre VERT.

CE QU'IL EST AUJOURD'HUI : lancable a la demande, **pas** une etape de PR obligatoire. Aucun
fichier de `.claude/` ni `CLAUDE.md` ne le prescrit, et la banque de fond ne tourne plus. Ce qui
suit dit ce qu'il COUTE et ce qu'il VOIT -- pas quand le jouer.

⛔ NE LANCE PAS LE RUN COMPLET PAR REFLEXE : **297,8 s de mur mesure a 8 shards**, ~1 425 s en
serie. Le geste courant, quand on veut s'en servir, est une SELECTION -- `--since <base>` ou
`--depuis-ledger` (cf. plus bas). Sans diff impactant, il ne joue rien et rend la main tout de
suite.

⚠ LE `0,21 %` QUI L'AVAIT DE-OBLIGE NE DIT PAS CE QU'ON LUI A FAIT DIRE (#486-r23). L'argument du
2026-08-05 (`d82ec527`) etait : sur 67 runs de `logs/ratchets-bg`, 2 437 lignes de cliquet, **5
non nulles**, donc << des prises de FONDATION, pas de GARDE >>. C'est un **biais du survivant
applique a un garde-fou** : un taux de declenchement bas est compatible avec << inutile >> ET avec
<< efficace >>, donc il ne separe pas les deux hypotheses. La contre-epreuve est arrivee seule --
de-oblige le 05, l'arbre offline portait **14-15 rouges le 07**. Un taux de declenchement ne
re-de-obligera donc plus rien ici ; le critere est le COUT, confronte au cout de la derive.
Detail et chiffres : `docs/rl/case-486r23-ledger-du-vert-offline.md`.

⚠ ET CETTE REFUTATION NE VAUT QUE POUR LUI. Il pese 67 % de la banque et n'est pas un cliquet de
GISEMENT mais un **lanceur de suite de tests** -- c'est pourquoi lui seul pouvait attraper ces 14
rouges. Les 32 cliquets de gisement n'ont pas tire une seule fois en 67 runs, et rien de ce qui
precede ne dit ce que vaut LEUR de-obligation.

⚠ Le cout ne se << regle >> pas en retrecissant le perimetre (faute que #457-r5 repare) : il se
regle par la SELECTION, qui est mesuree et se justifie fichier par fichier.

CE QU'IL EST SEUL A VOIR
------------------------
Un fichier de test 100 % OFFLINE, ROUGE EN PERMANENCE sur `master`, que rien ne signale.

Mesure du 2026-08-02, sur `master` propre : `tests/engine/runner/test_multihex_substrate.py`
rendait `3 failed, 15 passed` -- et le rouge datait du 2026-08-01. Trois raisons CUMULEES le
rendaient invisible, et aucune n'est un oubli individuel :

  1. `CLAUDE.md` PROSCRIT la suite complete -- a raison : 410 des 519 fichiers de test sont
     `_live.py`, la suite entiere sature la session Frida partagee. (Comptes RE-DERIVES le
     2026-08-02 apres #457-r5 ; les precedents -- 489 et 405 -- etaient eux-memes fausses par
     le glob corrige ci-dessous, qui masquait 23 fichiers.)
  2. Un agent ne rejoue que les tests de SA tranche, et ce fichier n'etait la tranche de personne.
  3. Les trois entrees pytest de la banque (`pytest_signatures`, `pytest_attestations`,
     `pytest_adjacency`) nomment leurs fichiers A LA MAIN. C'est une ALLOWLIST : un fichier n'y
     entre que si quelqu'un pense a l'y mettre. Personne n'y a pense pour celui-la.

C'est la forme deja trouvee par #435 et #455, et la correction durable a chaque fois ete d'entrer
le garde dans la banque. Ce cliquet la generalise : son perimetre se DERIVE (tout ce qui n'est pas
`_live.py`), donc un fichier offline neuf y entre TOUT SEUL, sans que personne ait a y penser.

Il voit aussi la SECONDE moitie du meme vice, plus couteuse : le VERT VACUEUX. Dans le fichier
mesure, un quatrieme test passait au vert avec zero assertion utile -- son anneau de voisins etait
vide, donc `set([centre]) == {centre} | set([])` etait trivialement vraie. Un fichier rouge se
repare ; un fichier vert-a-vide s'accumule.

CE QU'IL COUTE -- ET POURQUOI CE N'EST PLUS << presque rien >>
--------------------------------------------------------------
La proscription de la suite complete vise le cout des tests LIVE : les OFFLINE ne montent aucun
runner. Mais le cout a CHANGE D'ORDRE avec #457-r5, et l'ancienne redaction (<< 84 fichiers,
896 tests, 116 s d'un bloc ; 86 s pour le plus long des trois shards >>) mesurait un perimetre
AMPUTE de 23 fichiers.

Mesure du 2026-08-02, perimetre COMPLET, 109 fichiers / 1195 tests, trois shards joues en
parallele SOUS CHARGE (5 agents actifs) : **602 / 770 / 431 s**. Les 24 fichiers entrants pesent a
eux seuls plus de 600 s en serie -- ce sont pour l'essentiel des BALAYAGES (tables de symboles,
669 kits, arbre `scripts/**`), lourds mais legitimement offline.

Consequence assumee : a trois shards ce cliquet DEVIENT le mur de la banque, d'ou le passage a
HUIT dans `scripts/ratchets.ps1`.

ATTENTION -- NE PAS CONFONDRE LES DEUX CHIFFRES. La simulation sur les durees par fichier (mesurees SOUS
CHARGE) annoncait un mur de 629 s a 8 shards ; le mur REEL, mesure ISOLE le 2026-08-02
(`ratchets.ps1 -Only probe_439,probe_440,probe_457`), est **297,8 s** -- shard le plus long 295,7 s,
le plus court 48,3 s. La simulation surestime parce qu'elle additionne des durees deja gonflees par
la contention. Le mur d'une banque ne se SIMULE pas, il se MESURE isole (cf. les 4 releves du meme
jour, 126,6 / 136,2 / 159,1 / 319,8 s, sur des compositions quasi identiques).

Sharder plus ne rachete pas son cout : le md5 regroupe les lourds, et le plancher irreductible
reste le fichier le plus lourd, insecable (268 s en serie sous charge). Le vrai levier est
d'alleger les balayages eux-memes (residu #457-r6).

NE PAS << regler >> ce cout en retrecissant le perimetre : c'est exactement la faute que #457-r5
repare. Chiffres a RE-DERIVER, jamais a citer.

LE PERIMETRE, ET POURQUOI CE CRITERE-LA
---------------------------------------
Le critere retenu est `not name.endswith("_live.py")`. Un critere plus fin a ete essaye puis
REFUTE PAR MESURE : classer par la CLOTURE DE FIXTURES (`"host" not in item.fixturenames`) rendait
153 fichiers << offline >>, dont des DIZAINES de `*_live.py` -- ils montent leur runner a la main,
sans passer par les fixtures `host`/`live_session`/`build_runner`. Joue tel quel, ce critere partait
monter des runners et depassait 600 s. Le suffixe, lui, est DECLARATIF et tenu par le depot.

La cloture de fixtures reste utilisee, mais comme FILET et non comme critere : un item d'un fichier
non-`_live.py` qui reclame quand meme une fixture live est DESELECTIONNE et RAPPORTE. On ne rougit
pas dessus -- ce cliquet garde << les tests offline sont verts >>, pas << le nommage est parfait >>.

Le filet a pris EXACTEMENT UN poisson, et il a fallu 231/232 pour le voir. `mesure` mesurait
1 item, dans `test_act_of_faith_crit_resets_both_paths.py` : une seule fonction de test, prenant
`live_session`/`rpc`/`build_runner`, dans un fichier que le suffixe declarait offline. Sa docstring
disait << contrepartie OFFLINE >> -- l'intention l'etait, l'implementation non.

CE QUI L'A REVELE N'EST PAS LE FILET, C'EST L'EMPREINTE. Le filet le deselectionnait en silence
depuis toujours : sans report, pas de chronometrage, pas d'entree -- le fichier restait donc
eternellement a << jamais mesure >> et se rejouait sous `--since`. C'est cet ecart 231/232, et lui
seul, qui a nomme le fichier. Un item deselectionne ne coute rien et ne se voit pas ; c'est son
ABSENCE DE POIDS qui parle. Renomme en `_live.py` le 2026-08-07 : il sort du perimetre offline et
rejoint la banque ou il peut reellement tourner.

PERIMETRE (#434) : la liste vient de `git ls-files` lance dans CE checkout, donc elle ne peut pas
lire l'arbre d'un autre agent. ECRITURE (#455) : aucune -- `-p no:cacheprovider` empeche pytest de
deposer `.pytest_cache` sous `scripts/python/`, que la banque enumere en parallele.

CE PROBE EXIGE SON CWD, ET LE VERIFIE (#464)
--------------------------------------------
Les chemins passes a `pytest.main` sont relatifs au ROOTDIR (`scripts/python/pytest.ini`). Lance
d'ailleurs, pytest ne trouve aucun de ses arguments et rend `rc=4` -- une erreur d'USAGE, pas un
verdict. Mesure du 2026-08-04, depuis la racine du depot : `--measure` chronometrait 127 fichiers a
**0,0 s**, ecrivait une empreinte a **0 fichier de test**, soit **632 lignes supprimees** du fichier
VERSIONNE `scripts/ratchets-457-footprints.json` -- et annoncait << poids ecrits, mais l'arbre est
ROUGE >>, c'est-a-dire un rc de gisement pour un echec de MONTAGE. C'est le patron << un echec RENDU
se lit comme une mesure >>, en pire : il PERSISTE, et une empreinte videe ne selectionne pas TROP
(ce que la peremption normale fait, cf. `_footprints_path`) mais TROP PEU -- `impacted_files`
interprete << absent de `par_test` >> comme << aucune dependance hors-.py >>, donc un FAUX VERT.

Deux verrous, dans cet ordre :
  1. `_exiger_cwd()` REFUSE avant de jouer quoi que ce soit (rc `EX_NON_MESURE`) ;
  2. `_ecrire_mesure()` est le FOYER UNIQUE d'ecriture et refuse encore si pytest a rendu un rc
     d'usage/interruption, ou si AUCUN fichier n'a produit de report -- le filet couvre ce que le
     CWD ne cause pas (un fichier disparu entre `git ls-files` et l'execution, un `-x` interrompu).

`EX_NON_MESURE = 99` est la convention deja tenue par `scripts/ratchets-bg.ps1` : << aucun verdict
sur le depot >>, a ne JAMAIS lire comme un rouge de gisement (ni comme un vert).

LE TRI-ETAT S'ARRETAIT AU SEUIL DU MONTAGE (#471)
--------------------------------------------------
Ces deux verrous couvraient le CWD et l'ecriture -- pas la panne de l'OUTIL. `candidate_files`
portait un `check=True` nu : `git ls-files` en echec levait `CalledProcessError`, donc rc=1, donc
un ROUGE de gisement pour une panne d'outil. Mesure du 2026-08-04 sur `d2ede23d` :
`BANQUE ROUGE -- 1/40 : probe_457:s3` alors que ce shard avait crashe en 4,5 s SANS JOUER UN SEUL
TEST (rc 128), les 7 autres etant VERTS et la commande rejouee a la main rendant rc=0.

Trois consequences, toutes portees par `MontageImpossible` et son foyer `_git` :
  * la panne d'outil rend desormais `EX_NON_MESURE`, et `ratchets.ps1` la classe `INDISPONIBLE` ;
  * `_modules_du_graphe` ne rend plus `{}` EN SILENCE sur un git en echec -- ce repli-la etait pire
    qu'un crash : `mods` vide vide la cloture du graphe, donc `impacted_files` SOUS-selectionne,
    c'est-a-dire un FAUX VERT ;
  * l'attrape est ETROITE (type dedie, sites nommes) : un `except Exception` avalerait un bug du
    probe lui-meme et le ferait passer pour une indisponibilite.

Le CRITERE qui separe montage et mesure -- et sa borne, un `git ls-files` a rc=0 et liste VIDE qui
reste un ROUGE -- vit dans `scripts/ratchets-verdict.ps1`. Contre-epreuve : `probe_471`.

L'EMPREINTE NE DOIT RIEN AU `__pycache__` DE LA MACHINE (#464-r2)
-----------------------------------------------------------------
Le hook d'audit compte comme lecture GLOBALE tout `open` fait hors d'un test. Or, SANS bytecode,
l'import ouvre la SOURCE `.py` -- et la mesure devenait donc une fonction de l'etat du cache de la
machine. Mesure du 2026-08-04, MEME arbre, MEME probe :

| regime | `_globales` ecrites | dont `.py` | dont NON-`.py` | `par_test` |
| --- | --- | --- | --- | --- |
| worktree FROID (0 `__pycache__`) | **552** | 549 | 3 | 52 |
| arbre CHAUD | **3** | 0 | 3 | 47 |

Les 3 NON-`.py` sont les MEMES des deux cotes (`data/seed-bc.json`, `data/symbols/CURRENT`,
`scripts/python/pytest.ini`) : le noyau utile etait stable, tout le reste etait du bytecode.

ATTENTION -- l'effet REEL de ce bruit n'est PAS celui qu'on croit, et la mesure le tranche : un
`.py` du domaine place dans `_globales` **n'a AUCUN effet quand LUI-MEME change** --
`impacted_files` construit `hors_py = [c for c in changes if c not in mods]`, donc un module de
`scripts/python` n'est JAMAIS confronte a `_globales`. Son seul effet residuel passait par
`dirs_glob` : un fichier NON-`.py` du meme REPERTOIRE forcait le rejeu total. Un diff purement
Python ne declenchait donc jamais << TOUT rejoue >> par cette voie -- mesure sur 40 commits reels :
**0** TOUT-rejeu dans les DEUX regimes.

**RIEN N'EST FILTRE** -- la CAUSE est traitee. `--measure` PRECHAUFFE le bytecode
(`_prechauffer_bytecode`) avant d'installer le hook, et un GARDE DE REGIME refuse d'ecrire
l'empreinte si un module du domaine est quand meme lu en global (signe que le prechauffage n'a pas
pris). Mesure sur echantillon : **355** lectures brutes sans prechauffage, **2** avec, et
froid == chaud.

ATTENTION -- **la piste << filtrer les `.py` des globales >> a ete essayee, puis ECARTEE par
mesure.** Elle ferme `_globales` mais pas `par_test`, ou un import LAZY execute pendant un test
attribue au test une source `.py` (47 entrees a chaud contre 52 a froid). Et la, le filtre ne PEUT
pas etre etendu :
`par_test` porte **420** couples (test, repertoire-de-code) meme a chaud, parce que ce depot est
plein de tests-BALAYAGE qui OUVRENT le code source pour l'analyser. Ces lectures ne sont couvertes
par aucun import, donc par aucune preuve -- les retirer serait le faux vert de #464.

Fermer la cause a tout de meme exige de fermer un trou du graphe, decouvert en cherchant la preuve
de couverture : cf. `_conftest_edges`.

MESURE INCREMENTALE (#463)
--------------------------
`--measure` rejoue TOUT le perimetre : mesure du 2026-08-04, **976,9 s pour 1471 tests**. Un fichier
de test offline NEUF n'a pas de poids, prend le poids MAXIMUM connu dans `bins_of`, et desequilibre
la partition -- ce qui faisait de cette passe complete le seul remede a une garde d'equilibrage,
soit ~12 min BLOQUANTES par PR pour une OPTIMISATION de mur.

`--measure-missing` ne chronometre que les fichiers SANS poids et FUSIONNE dans le JSON existant.
C'est le cas nominal (mediane 0-1 fichier offline neuf par PR) : quelques secondes au lieu de 12 min.

⚠ POIDS ABSENTS N'EST PAS SANS POIDS (#463-r1). `logs/` est GITIGNORE, donc un worktree d'agent
n'a JAMAIS de poids -- et le critere << sans poids >> y valait pour TOUT LE MONDE : mesure du
2026-08-07 depuis un worktree, ce mode retenait **235 fichiers sur 235**, soit un `--measure`
complet (~976 s), c'est-a-dire l'exact contraire de sa raison d'etre. C'est le tri-etat que ce
depot tient partout ailleurs (`null` = pas mesure, jamais un zero), applique aux poids : quand le
FICHIER de poids est absent, le seul critere applicable est l'ENTREE D'EMPREINTE, et le mode le
DIT. Mesure apres correction : **1 fichier sur 235, 15 s de mur**.
Corollaire : dans ce regime, AUCUN fichier de poids n'est ecrit -- une entree unique fixerait
`defaut = max(weights.values())` de `bins_of` sur une valeur non representative, ce qui est PIRE
que le repli md5, lequel repartit par nombre et reste honnete.

Il ECRIT desormais l'empreinte des seuls fichiers qu'il a joues (#486-r15). Ce refus etait
structurel TANT QUE l'empreinte portait UN SEUL tampon de fraicheur pour l'ensemble ; avec un
tampon PAR ENTREE, une passe partielle rafraichit exactement ce qu'elle a mesure et ne pretend
RIEN sur le reste. Cf. la section suivante.

LE TAMPON DE FRAICHEUR DESCEND A L'ENTREE (#486-r15)
-----------------------------------------------------
L'empreinte portait un `_commit` GLOBAL, et `impacted_files` s'en servait pour unir << tout ce qui
a change depuis la mesure >> au diff de la PR. Ce sha etait ECRIT DANS LE WORKTREE D'UN AGENT,
donc sur SA branche -- que le squash-merge remplace par un commit neuf avant de la supprimer. Le
sha inscrit etait donc MORT-NE : mesure du 2026-08-07, `57bb2a7c` est inconnu de `git cat-file`,
et `--since` rendait **220/220 fichiers sur chacune des 8 dernieres bases de PR** -- la selection
ne selectionnait plus rien depuis 3 jours et ~40 commits. Auto-destructeur A CHAQUE LIVRAISON PAR
PR, pas un oubli.

La forme retenue est celle que ce depot tient DEJA sur l'autre versant, le ledger LIVE
`scripts/ratchets-462-live-attestations.json` (#462, repare par #465) : un tampon PAR ENTREE, cle
sur le CONTENU. Une entree perimee MANQUE au lieu de mentir, et un sha mort n'invalide que
lui-meme.

CE QUI REMPLACE LE TAMPON GLOBAL : RIEN. C'EST LE `git diff` QUI FAIT FOI
--------------------------------------------------------------------------
La question a laquelle l'empreinte repond est << ce diff touche-t-il ce test ? >>. Git rend deja
la liste des chemins modifies ; on l'apparie aux deps mesurees et aux globs declares. Appariement
de CHAINES, zero lecture, zero sha. Une cle de contenu par entree a ete ESSAYEE puis ECARTEE :
elle repond a une autre question (<< ce contenu a-t-il change ? >>), que le diff a deja tranchee,
et elle coute -- 4 001 ms pour hacher `scripts/python`, 2 643 ms pour un simple `stat()`, quand le
plus petit test offline pese 80 ms.

ET LA FRAICHEUR SE REPARE TOUTE SEULE, DES QUE LA MISE A JOUR PARTIELLE EXISTE. Le fichier de
test change ? il est dans le diff, donc selectionne, donc joue, donc son entree est REECRITE. Un
module de sa fermeture change ? le graphe d'imports le retient, meme chaine. Le seul cas
reellement dangereux -- un module qui se met a LIRE une donnee que l'empreinte du test ignore --
est donc couvert AU MOMENT MEME ou ce module change. C'est pour cela que la mise a jour partielle
est le coeur de cette tranche, et que le `_commit` GLOBAL qui l'interdisait etait le vrai defaut.

`_commit` et `_at` RESTENT dans chaque entree, en CONTEXTE INFORMATIF -- jamais comme critere.

L'ABSENCE D'UNE ENTREE VEUT DIRE << PAS MESURE >>, ET ELLE REJOUE
------------------------------------------------------------------
Avant #486-r15, un fichier absent de `par_test` etait lu << il n'ouvre aucun fichier du depot >>
et SAUTE. C'est une AFFIRMATION qui n'a jamais ete gagnee : elle ne vaut que si le test a tourne
au moins une fois sous le hook d'audit. Mesure sur `master` le 2026-08-07 : **88 entrees pour 220
fichiers offline** -- 132 fichiers passaient par cette affirmation. C'est le faux vert que
`_footprints_path` decrit : une empreinte videe ne sur-selectionne pas, elle SOUS-selectionne.
L'empreinte porte desormais une entree pour CHAQUE fichier joue, `dirs` VIDE compris ; MESURE-ET-
VIDE et JAMAIS-MESURE cessent donc de se confondre, et le second rejoue.

LA MOITIE DECLAREE : `DECLENCHEUR` (#486-r15, forme partagee avec #486-r12)
----------------------------------------------------------------------------
Chaque FICHIER de test declare, au niveau module, ce qui doit changer pour qu'il puisse changer de
verdict -- memes quatre cles et meme semantique de glob que les cliquets de la banque
(`declencheur_cliquet.py`). La declaration est BON MARCHE (regex contre les chemins du diff, ni
lecture ni AST pour les fichiers qui ne declarent pas) et elle exprime ce qu'aucune mesure ne
voit : l'INTENTION. Elle ne vaut que parce qu'un cliquet la CONFRONTE a la mesure --
`probe_486r15_declencheurs_tests.py`, qui verifie que rien de ce que le fichier IMPORTE ou OUVRE
ne sort de son perimetre declare.

Le grain est le FICHIER, pas le test, et c'est mesure : sur `test_477r24r1_slots_interface_offline`,
UN test coute 15,0 s quand les 59 du fichier en coutent 49,7 -- le cout FIXE des fixtures est ~15 s
et ne se divise pas. Et surtout, une selection INTRA-FICHIER casserait `probe_455` : un fichier
dont tous les tests sont deselectionnes n'emet AUCUN report, donc devient structurellement
invisible.

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_PYDIR_POUR_IMPORT = Path(__file__).resolve().parent
if str(_PYDIR_POUR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_PYDIR_POUR_IMPORT))

import declencheur_cliquet                                                  # noqa: E402
# LEDGER VERSIONNE DU VERT OFFLINE (#486-r23). Arete a SENS UNIQUE : ce module-la n'importe RIEN
# d'ici (l'impact lui est INJECTE), donc pas de cycle. Forme B non requise -- on lie des noms de
# module, pas des fonctions patchables. Il est LEGER (`json`/`subprocess`/`pathlib`).
import ledger_vert_offline as ledger                                        # noqa: E402
# LE FOYER DU RECENSEMENT OFFLINE (#463-r1) : `TESTS_DIR`, la convention de collecte et le filtre
# `_live.py` y vivent, parce que TROIS outils les derivaient separement. Le module est LEGER
# (`json`/`ast`/`tokenize`) et n'importe RIEN d'ici -- l'arete est a sens unique, donc pas de
# cycle. Forme B (liaison de module) : cf. la regle d'import du depot.
import probe_463r1_ecart_empreinte_offline as ecart_empreinte               # noqa: E402
import repo_read                                                            # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: `toujours: True`, et pour une raison qui lui est PROPRE : sa selection existe DEJA, elle est
#: INTERNE, et elle est MESUREE. `--since <ref>` restreint le perimetre aux fichiers impactes,
#: deduits de l'EMPREINTE (`scripts/ratchets-457-footprints.json` : les fichiers reellement
#: OUVERTS par chaque test) et du graphe d'imports, tout doute rejouant TOUT et le DISANT.
#: Le borner en PLUS par une liste de chemins ecrite ici, ce serait poser une seconde selection
#: DEDUITE au-dessus d'une selection MESUREE -- et c'est la moins fidele des deux qui
#: trancherait. Ce que ce cliquet lit, ce sont ses 109 fichiers de test ET tout ce que ces tests
#: lisent : `engine/**`, les ~830 probes, `data/symbols`, `data/seed-bc.json`, `data/boards`,
#: `scripts/**` (~24 d'entre eux sont des BALAYAGES d'arbre) -- soit le depot, moins rien de
#: nommable.
#:
#: Corollaire pour l'appelant : passer `--since` est ce qui rend son cout supportable, pas le
#: sauter. Sans diff impactant, il ne joue aucun test et rend la main tout de suite.
DECLENCHEUR = {
    "chemins": ("*", "**"),
    "build": True,
    "toujours": True,
    "raison": "Il joue tout `scripts/python/tests/**` non-`_live.py` : son verdict depend de "
              "tout ce que ces tests LISENT, y compris les balayages d'arbre et les tables de "
              "symboles. Sa selection est INTERNE (`--since`, empreinte MESUREE) et doit rester "
              "la seule -- une borne par chemins posee au-dessus la contredirait.",
}

#: Fixture RACINE du monde live. La cloture calculee par pytest (`item.fixturenames`) est
#: TRANSITIVE : un item qui reclame `live_runner` -> `build_runner` -> `host` porte les trois.
#: Verifie le 2026-08-02 sur les 512 fichiers collectes -- `host` et `live_session` couvrent
#: EXACTEMENT les memes 359 fichiers, et `rpc`/`build_runner`/`live_runner` en sont des
#: sous-ensembles stricts (294 / 248 / 2). Une seule racine suffit donc a tous les reconnaitre.
LIVE_FIXTURE_ROOT = "host"

#: Repertoire des tests (`testpaths = tests` dans `pytest.ini`). C'est un PATHSPEC DE REPERTOIRE,
#: pas un glob : `git ls-files <dir>` descend recursivement, sans semantique `**` a deviner.
#:
#: ATTENTION #457-r5 : la forme precedente etait `scripts/python/tests/**/test_*.py`, et `**/` EXIGE un
#: niveau intermediaire -- les fichiers poses DIRECTEMENT dans `tests/` en etaient exclus.
#: Mesure du 2026-08-02 : 496 fichiers avec `**`, 519 sans, soit 23 invisibles, dont 21 que AUCUNE
#: entree de la banque ne jouait (les 2 autres etant nommes a la main par `pytest_signatures` et
#: `pytest_attestations`). C'est le vice de #458 (`Path.match` n'etend pas `**`) sur un autre outil.
#:
#: DEPUIS #463-r1, LE CRITERE VIT DANS `probe_463r1_ecart_empreinte_offline` -- pas ici. Il etait
#: DERIVE trois fois separement (ici, dans `loop_status.mesurer_empreinte`, et le cliquet d'ecart
#: en aurait fait une quatrieme), et deux derivations d'un meme critere ouvrent un ecart
#: SILENCIEUX : le capteur mesurerait alors un autre perimetre que celui que `--measure-missing`
#: joue. Meme arbitrage que `_modules_du_graphe`, qui est le foyer unique du domaine du graphe.
#: Les NOMS restent ici (`TESTS_DIR`, `_is_test_file`) : ce sont eux que lisent les tests de #457.
TESTS_DIR = ecart_empreinte.TESTS_DIR

#: La convention de collecte de pytest. Alias du foyer -- cf. `TESTS_DIR` ci-dessus.
_is_test_file = ecart_empreinte.est_fichier_de_test

_PYDIR = Path(__file__).resolve().parent

#: rc << RIEN N'A ETE MESURE >>. Convention deja tenue par `scripts/ratchets-bg.ps1` (`rc=99` =
#: MONTAGE EN ECHEC, aucun verdict sur le depot). Un appelant DOIT le traiter comme
#: << non mesure >>, jamais comme un rouge de gisement -- ni comme un vert.
EX_NON_MESURE = 99

#: Codes pytest sous lesquels la mesure n'est PAS exploitable : 2 interrompu, 3 erreur interne,
#: 4 erreur d'USAGE, 5 aucun test collecte. `0` et `1` le sont -- des tests ROUGES n'invalident ni
#: les durees ni l'empreinte, les fichiers ont bien ete joues.
RC_PYTEST_SANS_MESURE = (2, 3, 4, 5)

#: VERSION DU FORMAT DE L'EMPREINTE (#486-r15). `1` = un `_commit` GLOBAL comme critere de
#: fraicheur, et `par_test[rel]` = simple liste de repertoires, ecrite SEULEMENT si non vide.
#: `2` = une entree DICT par fichier MESURE (`dirs` VIDE compris, ce qui rend l'absence lisible
#: comme << jamais mesure >>), un `_at`/`_commit` par entree en contexte INFORMATIF, et des
#: `temoins` (chemins reels) pour la confrontation des `DECLENCHEUR`.
#:
#: Une empreinte d'un AUTRE format ne se devine pas : `impacted_files` refuse de s'en servir et
#: rejoue TOUT en le disant. C'est le seul traitement sur -- lire une empreinte de format 1 avec
#: les regles du 2 conclurait << jamais mesure >> partout (sur-selection, benin) ; l'inverse
#: conclurait << aucune dependance hors-.py >> partout, soit exactement le FAUX VERT de #464.
FORMAT_EMPREINTE = 2


class MontageImpossible(RuntimeError):
    """Le probe n'a pas pu CONSTITUER l'objet de sa mesure. Rend `EX_NON_MESURE`, JAMAIS 1 (#471).

    LE CRITERE, ET POURQUOI IL EST ETROIT
    -------------------------------------
    Cette exception ne se leve que sur une panne de ce dont le probe DEPEND et qui n'est PAS le
    depot : le CWD que l'appelant lui donne, les outils externes qu'il invoque (`git`, `pytest` en
    tant que programme), le systeme de fichiers. Le test operationnel tient en une question --
    << un depot PARFAIT, a cet instant, sur cette machine, aurait-il produit ce meme echec ? >>.

    Ce qu'elle NE couvre PAS, et qui reste un ROUGE : un `git ls-files` qui repond rc=0 avec une
    liste VIDE (reponse VALIDE de l'outil = fait sur le depot -> perimetre effondre), un test
    offline qui echoue, un shard vide hors selection. C'est la frontiere a ne pas laisser glisser :
    sans elle, << je n'ai rien trouve >> deviendrait << je n'ai pas pu regarder >>.

    LE GISEMENT MESURE (2026-08-04, banque sur `d2ede23d`)
    ------------------------------------------------------
    `[ratchets] BANQUE ROUGE -- 1/40 cliquet(s) : probe_457:s3`. Or cette tranche n'a joue AUCUN
    test : elle a crashe en 4,5 s dans son propre montage, sur
    `subprocess.CalledProcessError: Command '['git', 'ls-files', 'scripts/python/tests']' returned
    non-zero exit status 128` (`candidate_files`, appele depuis `main`). Les 7 autres shards
    etaient VERTS (s5 : 412,7 s, rc=0) et la commande rejouee a la main dans le meme worktree
    rendait rc=0 immediatement -- donc TRANSITOIRE, pas un etat casse.

    Une exception non rattrapee rend `1` en Python : le crash sortait donc EXACTEMENT comme
    << un test offline est rouge >>. Le tri-etat de `probe_457` existait deja (garde de CWD,
    refus d'ecrire, rc pytest d'usage) mais s'ARRETAIT AU SEUIL DU MONTAGE.

    ⚠ AUCUNE PARADE N'EST CODEE SUR LA CAUSE de ce 128. L'hypothese << contention git >> (les
    worktrees partagent `.git/`, la banque tournait pendant un `git merge --no-ff` dans l'arbre
    principal) est PLAUSIBLE et NON ETABLIE -- la trancher demanderait de rejouer une passe AVEC
    et SANS operation git concurrente. Le defaut ferme ici est le TRI-ETAT, qui vaut quelle que
    soit la cause. Aucun rejeu automatique non plus : << un rejeu qui passe ne prouve rien >>.
    """


def repo_root() -> Path:
    """Racine du checkout COURANT. Depuis un worktree, c'est le worktree -- jamais l'arbre
    principal (#434 : un cliquet ne balaie QUE son propre checkout)."""
    return _PYDIR.parents[1]


def _git(args: list, quoi: str, tolere_rc: bool = False, racine=None):
    """FOYER UNIQUE des appels a `git` (#471). Rend le `CompletedProcess`.

    `tolere_rc=True` : le rc non nul est une INFORMATION que l'appelant sait interpreter (une ref
    inconnue de `git diff` fait rejouer TOUT, et c'est le comportement voulu). Sinon, un rc non nul
    est une panne d'outil -> `MontageImpossible`.

    Une `OSError` (git absent du PATH, process non lancable) leve TOUJOURS : aucun appelant ne peut
    en tirer une information sur le depot.

    Pourquoi un foyer : le crash mesure venait d'un `check=True` isole. Disperser la traduction
    << panne d'outil -> non mesure >> sur chaque site rouvrirait le trou au premier appel ajoute --
    c'est la meme raison qui fait de `_ecrire_mesure` le foyer unique des ECRITURES.
    """
    cmd = ["git", "-C", str(racine or repo_root()), *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as exc:
        raise MontageImpossible(
            "`git %s` n'a pas pu etre lance (%s: %s) -- %s"
            % (" ".join(args), type(exc).__name__, exc, quoi)) from exc
    if proc.returncode != 0 and not tolere_rc:
        raise MontageImpossible(
            "`git %s` a rendu rc=%d -- %s. stderr: %s"
            % (" ".join(args), proc.returncode, quoi, (proc.stderr or "").strip()[:300]))
    return proc


def _exiger_cwd() -> str:
    """`""` si le CWD permet de jouer, sinon le message de REFUS (#464).

    Les chemins passes a `pytest.main` sont relatifs au ROOTDIR, que `pytest.ini` fixe a
    `scripts/python`. Lance d'ailleurs, pytest rend `rc=4` (usage) et le probe ecrivait quand meme
    -- 632 lignes retirees d'un fichier VERSIONNE. On VERIFIE et on REFUSE plutot que de produire
    du garbage : c'est le geste que l'echec de montage exige, pas un repli silencieux.

    Pourquoi refuser au lieu de `chdir` : un `chdir` implicite masquerait un appelant mal cable
    (`ratchets.ps1` fait `Set-Location scripts\\python`, c'est SA responsabilite) et rendrait le
    diagnostic invisible la prochaine fois. `--list` n'invoque pas pytest et n'est donc pas garde.
    """
    ici = Path.cwd().resolve()
    if ici == _PYDIR:
        return ""
    return ("[457] REFUS : ce probe doit etre lance depuis `%s` (les chemins passes a pytest sont\n"
            "[457] relatifs au rootdir de `pytest.ini`). CWD courant : `%s`.\n"
            "[457] rc=%d -- RIEN n'a ete joue, RIEN n'a ete ecrit. Ce n'est PAS un verdict sur le "
            "depot." % (_PYDIR, ici, EX_NON_MESURE))


def candidate_files() -> list[str]:
    """Les fichiers de test NON `_live.py`, en chemins relatifs a `scripts/python`.

    Passe par `git ls-files` : seul l'index de CE checkout est consulte, donc ni les worktrees
    voisins ni les fichiers non suivis n'y entrent. Tri stable -- le shard doit etre reproductible.

    Le REPERTOIRE est passe a git (qui descend seul), et la selection des fichiers se fait ICI, en
    Python : c'est ce qui rend le perimetre relisable et testable, au lieu de dependre de la
    semantique d'un glob (#457-r5).

    #471 : un `git ls-files` en echec leve `MontageImpossible` (-> rc 99) au lieu du
    `CalledProcessError` du `check=True` d'origine, qui sortait en rc=1 -- indistinguable d'un test
    offline rouge. C'est le crash EXACT mesure le 2026-08-04 sur `probe_457:s3` (rc 128).
    Une liste VIDE, elle, n'est PAS une panne : c'est une reponse valide, donc un fait sur le
    depot, et le garde anti-effondrement de `main` la traite en ROUGE."""
    #463-r1 : le FILTRE est delegue au foyer (`ecart_empreinte.perimetre_offline`), qui est une
    # fonction PURE sur la sortie de git. L'APPEL a git reste ici, avec son `MontageImpossible` --
    # c'est exactement ce partage qui permet a `loop_status` de partager le critere sans partager
    # la facon d'interroger git (il a son propre cache TTL et son propre tri-etat).
    out = _git(["ls-files", TESTS_DIR],
               "impossible d'enumerer le perimetre des tests -- RIEN n'a ete mesure")
    return ecart_empreinte.perimetre_offline(out.stdout)


def shard_of(rel: str, total: int) -> int:
    """Shard STABLE d'un fichier : md5 du chemin relatif, modulo `total`.

    Stable = independant de l'ordre et du nombre de fichiers, donc l'ajout d'un fichier ne
    redistribue pas les autres (un modulo sur l'INDEX du tri, lui, decale tout le monde).

    C'est le REPLI, utilise quand aucun poids n'est disponible. Il repartit par NOMBRE, pas par
    COUT -- mesure du 2026-08-02 : il avait concentre 4 fichiers lourds dans le seul `s7`
    (106 s isole, contre 4,8 s pour `s3`), et ce shard-la faisait A LUI SEUL tout le mur de la
    banque (234,7 s sur 234,8). D'ou `bins_of` ci-dessous."""
    digest = hashlib.md5(rel.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % total


#: Poids MESURES (secondes par fichier), regeneres par `--measure`. VERSIONNE a dessein : sans
#: lui, un checkout frais retomberait sur le repli md5 et paierait le mur que #457-r6 corrige.
#:
#: Ces poids ne conditionnent QUE la repartition. Perimes, ils coutent du MUR -- jamais un faux
#: vert, jamais un trou : `bins_of` partitionne l'ENSEMBLE des fichiers quels que soient les
#: poids, et la garde `test_457_r5_perimetre_offline.py` verifie l'union stricte des bins.
#:
#: SOUS `logs/`, JAMAIS sous `scripts/python/` (#455). Premiere version de ce mode : les poids
#: etaient ecrits a cote du probe -- `probe_440` a ROUGI, a raison. La banque tourne en PARALLELE
#: et plusieurs cliquets ENUMERENT `scripts/python/**` : y creer un fichier le fait apparaitre
#: puis disparaitre sous les pieds d'un voisin. Le prix a payer est que `logs/` est gitignore,
#: donc un checkout frais (un worktree d'agent) retombe sur le repli md5 : mur sous-optimal,
#: verdict INCHANGE. C'est le bon arbitrage -- la correction prime sur le mur.
def _weights_path():
    return repo_root() / "logs" / "ratchets" / "457-durations.json"


def _weights() -> dict:
    """Les poids mesures, ou `{}` s'ils sont absents/illisibles (-> repli md5)."""
    path = _weights_path()
    if not path.exists():
        return {}
    try:
        import json
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in raw.items()}
    except Exception:
        return {}


def bins_of(files: list, total: int, weights: dict) -> list:
    """Partitionne `files` en `total` paquets EQUILIBRES PAR COUT (LPT).

    LPT (longest processing time first) : on place le plus lourd d'abord, toujours dans le paquet
    le moins charge. Heuristique classique, bornee a 4/3 de l'optimal -- amplement suffisant ici.

    DETERMINISTE : le tri porte sur `(-poids, chemin)`, donc deux shards du MEME run calculent
    exactement la meme partition. C'est ce qui interdit qu'un fichier tombe dans zero paquet --
    le mode de defaillance a eviter, puisqu'il serait SILENCIEUX (un fichier jamais joue, sous un
    verdict vert). Un fichier sans poids prend le poids MAXIMUM connu : on ignore son cout, on le
    suppose donc le pire (le choix sur, symetrique de l'ordonnancement de la banque)."""
    if total < 1:
        raise ValueError("total doit etre >= 1")
    defaut = max(weights.values()) if weights else 1.0
    charge = [0.0] * total
    paquets = [[] for _ in range(total)]
    for rel in sorted(files, key=lambda r: (-weights.get(r, defaut), r)):
        i = min(range(total), key=lambda j: (charge[j], j))
        paquets[i].append(rel)
        charge[i] += weights.get(rel, defaut)
    return [sorted(p) for p in paquets]


def equilibre_des_bins(files: list, total: int, weights: dict) -> dict:
    """Diagnostic de l'equilibre de la partition, SUR LES SEULS FICHIERS PESES (#463).

    Un fichier SANS poids prend le maximum connu dans `bins_of` (choix sur), donc il DEPLACE les
    vrais lourds et fait monter la charge maximale -- sans qu'aucun poids ne soit faux. Mesurer
    l'equilibre sur l'ensemble complet melangeait donc deux choses : la qualite de l'heuristique
    (ce qu'on veut garder) et l'absence de donnees (ce qu'on veut seulement RAPPORTER).

    `ratio = max(charges) / max(plancher, moyenne)` : le plancher est le fichier le PLUS LOURD,
    insecable -- on ne peut pas exiger mieux que lui.
    """
    peses = [rel for rel in files if rel in weights]
    inconnus = [rel for rel in files if rel not in weights]
    charges = [sum(weights[r] for r in b) for b in bins_of(peses, total, weights)] if peses else []
    plancher = max((weights[r] for r in peses), default=0.0)
    moyenne = (sum(charges) / len(charges)) if charges else 0.0
    reference = max(plancher, moyenne)
    return {
        "peses": peses,
        "inconnus": inconnus,
        "charges": charges,
        "plancher": plancher,
        "moyenne": moyenne,
        "ratio": (max(charges) / reference) if charges and reference > 0 else 0.0,
    }


class _DeselectLiveItems:
    """Retire les items dont la cloture de fixtures touche le monde live, et les RAPPORTE."""

    def __init__(self) -> None:
        self.kept = 0
        self.dropped_items = 0
        self.dropped_files: set[str] = set()

    def pytest_collection_modifyitems(self, session, config, items):   # noqa: D102
        keep = []
        for item in items:
            if LIVE_FIXTURE_ROOT in set(getattr(item, "fixturenames", ())):
                self.dropped_items += 1
                self.dropped_files.add(str(item.path))
            else:
                keep.append(item)
        self.kept = len(keep)
        items[:] = keep


class _TimePerFile:
    """Accumule setup+call+teardown PAR FICHIER, pour regenerer les poids en UN SEUL passage.

    Mesurer fichier par fichier couterait 110 demarrages de process (3,1 s piece, soit ~340 s de
    pur demarrage) et surestimerait chaque fichier de ce meme cout fixe -- deux fois faux."""

    def __init__(self) -> None:
        self.sec: dict = {}
        self.n: dict = {}

    def pytest_runtest_logreport(self, report):                       # noqa: D102
        # Le NODEID, pas `fspath` : mesure du 2026-08-02, `fspath` ne correspondait pas aux cles
        # pour 13 des 111 fichiers (sous-repertoires a conftest imbrique) -- ils ressortaient a
        # 0 s alors qu'ils collectaient et passaient leurs tests. Le nodeid, lui, commence
        # TOUJOURS par le chemin relatif au rootdir, separateurs `/`.
        nodeid = str(getattr(report, "nodeid", "") or "")
        rel = nodeid.split("::")[0].replace("\\", "/")
        if not rel:
            rel = str(getattr(report, "fspath", "")).replace("\\", "/")
        if rel:
            self.sec[rel] = self.sec.get(rel, 0.0) + float(getattr(report, "duration", 0.0) or 0.0)
            self.n[rel] = self.n.get(rel, 0) + 1


class _BilanParFichier:
    """Le BILAN VENTILE de pytest, par FICHIER -- la moitie que `_TimePerFile` ne porte pas.

    Il alimente le ledger versionne du vert offline (`ledger_vert_offline`). Ventile, et pas
    seulement `rc`, parce que c'est la ventilation qui rend possible le garde `#455` :
    `passed == 0 and skipped > 0` est un VERT QUI MENT -- zero assertion evaluee, `rc 0`. Un champ
    `verdict` seul ne saurait pas le voir, et c'est exactement ainsi que
    `test_summon_trait_effects_live.py` a tenu sur `master` en 8 skipped / 0 passed.

    La SEMANTIQUE DES PHASES est celle de `probe_462`, et elle n'est pas cosmetique : un echec en
    `setup`/`teardown` est une panne de MONTAGE (`error`), pas un echec d'assertion (`failed`).
    Confondre les deux fait accuser le depot pour une panne de harnais.
    """

    def __init__(self) -> None:
        self.par_fichier: dict = {}

    def _seau(self, rel: str) -> dict:
        return self.par_fichier.setdefault(
            rel, {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "xfailed": 0})

    def pytest_runtest_logreport(self, report):                       # noqa: D102
        rel = str(getattr(report, "nodeid", "") or "").split("::")[0].replace("\\", "/")
        if not rel:
            return
        seau = self._seau(rel)
        if getattr(report, "when", None) in ("setup", "teardown"):
            if report.failed:
                seau["error"] += 1
            return
        if getattr(report, "wasxfail", None) is not None and report.skipped:
            seau["xfailed"] += 1
        elif report.passed:
            seau["passed"] += 1
        elif report.failed:
            seau["failed"] += 1
        elif report.skipped:
            seau["skipped"] += 1


class _FilesPerTest:
    """EMPREINTE MESUREE : quels fichiers du depot chaque fichier de test ouvre REELLEMENT.

    C'est la piece qui permet une selection par diff SANS table ecrite a la main. Le graphe
    d'imports ne voit que les dependances `import` ; un test qui lit `data/...` ou `docs/...` en
    est invisible, et c'est exactement la ou une selection naive produirait un FAUX VERT.

    Deux seaux, et la distinction est ce qui rend l'empreinte SURE :
      * `par_test`  -- lectures faites PENDANT un test (on sait a qui les attribuer) ;
      * `globales`  -- lectures faites hors de tout test (collecte, import de module, conftest).
        Elles ne sont attribuables a personne, donc tout changement les touchant impacte TOUS les
        fichiers. Conservateur par construction -- jamais l'inverse.
    """

    def __init__(self, root) -> None:
        self.root = str(root).replace("\\", "/").rstrip("/") + "/"
        self._prefixe = self.root.lower()
        self._n = len(self.root)
        self.par_test: dict = {}
        self.globales: set = set()
        self.courant = None
        sys.addaudithook(self._hook)

    def _hook(self, event, args):
        # Chemin CHAUD : appele a chaque `open` du process. Sortir au plus vite.
        if event != "open":
            return
        p = args[0]
        if type(p) is not str or len(p) <= self._n:
            return
        q = p.replace("\\", "/")
        if not q.lower().startswith(self._prefixe):
            return
        rel = q[self._n:]
        if self.courant is None:
            self.globales.add(rel)
        else:
            self.par_test.setdefault(self.courant, set()).add(rel)

    def pytest_runtest_logstart(self, nodeid, location):               # noqa: D102
        self.courant = str(nodeid).split("::")[0].replace("\\", "/")

    def pytest_runtest_logfinish(self, nodeid, location):              # noqa: D102
        self.courant = None


def _temoins(chemins, versionnable) -> list:
    """DEUX chemins REELS par groupe (repertoire, extension) : le plus petit et le plus grand.

    A QUOI CA SERT, ET POURQUOI PAS `dirs` (#486-r15). `dirs` sert la SELECTION, a la granularite
    repertoire -- c'est le bon grain pour << un fichier NEUF de ce repertoire doit rejouer >>. La
    CONFRONTATION d'un `DECLENCHEUR`, elle, apparie des GLOBS a des chemins : `docs/rl/*.md` ne
    s'evalue pas contre le repertoire `docs/rl`, il s'evalue contre un fichier. Il faut donc des
    chemins reels.

    L'AGREGATION est une APPROXIMATION ASSUMEE, et elle borne PAR LE BAS : un glob discriminant
    sur le nom de base peut couvrir les deux temoins d'un groupe sans couvrir un troisieme fichier
    du meme groupe. Elle est reprise telle quelle de `probe_486r12_declencheurs.py`, qui la
    documente pour les cliquets -- meme arbitrage, meme raison : garder le fichier versionne
    lisible (l'empreinte a chemins COMPLETS pesait 961 Ko).
    """
    seaux: dict = {}
    for c in chemins:
        if not versionnable(c) or "/" not in c:
            continue
        base = c.rsplit("/", 1)
        ext = base[1].rsplit(".", 1)[-1] if "." in base[1] else ""
        cle = (base[0], ext)
        mn, mx = seaux.get(cle, (c, c))
        seaux[cle] = (min(mn, c), max(mx, c))
    out: set = set()
    for mn, mx in seaux.values():
        out.add(mn)
        out.add(mx)
    return sorted(out)


def _empreinte_fusionnee(mesures: list, lus_par_test: dict, dossiers, temoins, globales: list,
                         commit, complete: bool, mods: dict) -> dict:
    """L'empreinte a ECRIRE : les entrees de CETTE passe, fusionnees dans celle du disque (#486-r15).

    LA REGLE, ET ELLE TIENT EN UNE LIGNE : cette passe n'ecrit QUE ce qu'elle a mesure, et ne
    touche a RIEN d'autre. C'est ce que le tampon par entree rend possible -- avec un `_commit`
    global, rafraichir apres 2 fichiers pretendait une fraicheur qu'on n'avait pas.

    UNE ENTREE PAR FICHIER JOUE, `dirs` VIDE COMPRIS. Avant #486-r15, seules les entrees NON VIDES
    etaient ecrites, et `impacted_files` lisait l'absence comme << aucune dependance hors-.py >> :
    une empreinte videe faisait alors SAUTER des tests (faux vert, #464). Desormais l'absence se
    lit << jamais mesure >> -> rejoue, et cela n'est VRAI que si les entrees vides sont ecrites.

    `_globales` : REMPLACE par une passe complete (elle a tout vu), UNI par une passe partielle
    (elle n'a vu que la collecte de ses propres fichiers). L'union ne peut que SUR-selectionner --
    `_globales` ne sert qu'a declencher un rejeu total ; la retrecir serait le seul sens dangereux.

    `_commit` et `_at` sont du CONTEXTE : ils disent OU et QUAND, jamais si l'entree est valide.
    Le sha inscrit peut etre mort-ne (branche d'agent squash-mergee, cf. l'en-tete) sans que cela
    invalide quoi que ce soit -- c'est tout l'objet de #486-r15.
    """
    ancien = _footprints()
    ancien_pt = ancien.get("par_test") if ancien.get("_format") == FORMAT_EMPREINTE else {}
    garde = {} if complete else {r: e for r, e in (ancien_pt or {}).items()
                                 if isinstance(e, dict) and r not in mesures}

    maintenant = int(time.time())
    neuves = {}
    for rel in sorted(mesures):
        lus = lus_par_test.get(rel, ())
        neuves[rel] = {
            "_at": maintenant,
            "_commit": commit,
            # LES DEPS SONT DES REPERTOIRES, et le diff fait foi : on les APPARIE aux chemins que
            # `git diff --name-only` rend. Aucun hash, aucune lecture. Le repertoire s'apparie
            # meme MIEUX qu'un fichier -- un fichier NEUF qui y apparait est couvert sans que
            # l'empreinte bouge, et c'est exactement ce qu'un test-balayage exige.
            "dirs": dossiers(lus),
            "temoins": temoins(lus),
        }

    anciennes_glob = ancien.get("_globales") or []
    return {
        "_format": FORMAT_EMPREINTE,
        "_regime": REGIME_MESURE,
        "_globales": sorted(globales if complete else set(globales) | set(anciennes_glob)),
        "par_test": dict(sorted({**garde, **neuves}.items())),
    }


def _ecrire_ledger(perimetre: list, joues: list, bilan, horloge, rc: int, n_shards: int) -> None:
    """Inscrit au LEDGER VERSIONNE le verdict de CHAQUE fichier que CETTE passe a joue (#486-r23).

    DECIDE D'ABORD, ECRIT ENSUITE -- meme discipline que `_ecrire_mesure`, et pour la meme raison :
    ce fichier est VERSIONNE, donc une ecriture fausse se propage a tout le monde.

    TROIS REFUS, et chacun ferme un chemin par lequel un FAUX VERT entrerait :

      1. `rc` d'USAGE / d'interruption (2, 3, 4, 5) -- rien n'a ete joue, donc rien n'est atteste.
         C'est le patron << un echec RENDU se lit comme une mesure >>, deja paye deux fois ici.
      2. `n_shards > 1` -- LA CONCURRENCE INTRA-RUN. Les 8 shards sont 8 PROCESSUS : ils
         ecriraient le meme fichier en meme temps, et le dernier ecraserait les autres (chaque
         shard ne connait QUE ses fichiers, donc il ecrirait un ledger ampute des 7/8 restants).
         Refuser et le DIRE ; consolider entre processus est un residu, pas une devinette.
      3. AUCUNE base de fraicheur (`git` muet) -- une attestation sans `_depuis` n'est pas
         verifiable, donc `raison_de_rejeu` la rejetterait de toute facon. Autant ne pas l'ecrire.

    Ce qui n'est PAS un refus : des tests ROUGES. Un rouge est un FAIT sur cet arbre et il
    s'inscrit -- c'est meme la seule facon qu'un rouge cesse d'etre invisible entre deux passes.
    """
    if rc in RC_PYTEST_SANS_MESURE:
        print("[457] ledger NON ECRIT : pytest rc=%d -- rien n'a ete joue, rien n'est atteste."
              % rc)
        return
    if n_shards > 1:
        print("[457] ledger NON ECRIT : %d shards = autant de processus concurrents sur un "
              "fichier VERSIONNE ; chacun n'a joue que sa part et ecraserait celle des autres."
              % n_shards)
        print("[457] Rejouer en MONO-SHARD pour attester (residu : consolidation inter-shards).")
        return
    base, comment = ledger.base_de_fraicheur(repo_root())
    tete = _git(["rev-parse", "HEAD"], "horodatage du ledger", tolere_rc=True)
    head = (tete.stdout or "").strip() or None
    # DEUX ANCRES : `_depuis` = HEAD (PRECIS, mortel au squash), `_base` = merge-base
    # (SURVIVANTE, grossiere). Mesure du 2026-08-07 : avec la base SEULE, `--depuis-ledger` rend
    # EXACTEMENT la selection de `--since <base>` (33 fichiers, 494 s) -- zero economie.
    if not head and not base:
        print("[457] ledger NON ECRIT : %s" % comment)
        return
    depuis = head
    blobs = ledger.blobs_courants(repo_root(), list(joues))

    neuves = {}
    for rel in joues:
        b = bilan.par_fichier.get(rel)
        if b is None:
            # AUCUN report pour ce fichier : il n'a rien collecte (ou a disparu). Ne RIEN ecrire
            # est le seul traitement sur -- une entree fabriquee a 0 partout serait lue `VIDE`,
            # ce qui est un FAIT que cette passe n'a pas etabli.
            continue
        neuves[rel] = ledger.entree_neuve(
            b, horloge.sec.get(rel, 0.0), blobs.get(rel), depuis, head, base=base)

    if not neuves:
        print("[457] ledger NON ECRIT : aucun des %d fichier(s) joue(s) n'a produit de report."
              % len(joues))
        return
    anciennes, anomalies = ledger.lire(repo_root())
    for a in anomalies:
        print("[457] ledger : %s" % a)
    fusion = ledger.fusionner(anciennes, neuves, perimetre=perimetre)
    p = ledger.ecrire(repo_root(), fusion)
    verts = sum(1 for e in neuves.values() if e["verdict"] == ledger.VERT)
    print("[457] ledger -> %s : %d entree(s) inscrite(s) (%d VERT, %d non-VERT), %d au total ; "
          "ancres _depuis=%s (precise) / _base=%s [%s]"
          % (p, len(neuves), verts, len(neuves) - verts, len(fusion),
             (depuis or "(aucune)")[:8], (base or "(aucune)")[:8], comment))


def _ecrire_mesure(perimetre: list, joues: list, horloge, empreinte, rc: int,
                   elapsed: float, poids_connus: dict, complete: bool = True,
                   ecrire_poids: bool = True) -> int:
    """FOYER UNIQUE d'ecriture de ce probe (#464). DECIDE d'abord, ecrit ensuite -- jamais l'inverse.

    Le vice repare : `--measure` ecrivait, PUIS annoncait << poids ecrits, mais l'arbre est ROUGE >>
    sur un `pytest rc=4` qui n'est pas un rouge du tout mais une erreur d'USAGE. Un echec de montage
    RENDU se lit comme une mesure ; ici il se PERSISTAIT, dans un fichier versionne.

    Le critere du refus est le NOMBRE DE REPORTS, jamais la duree : un fichier offline pur peut
    passer ses 4 tests en moins de 5 ms (mesure du 2026-08-02 -- l'arrondi a 2 decimales rendait 13
    puis 15 fichiers << sans mesure >>, signature d'un seuil, pas d'un fichier muet). Ce qui ne peut
    PAS arriver en regime normal, c'est que le perimetre ENTIER soit muet.

    `empreinte is None` = aucune empreinte n'a ete instrumentee : on ne touche pas au fichier
    versionne. Depuis #486-r15 une mesure PARTIELLE en instrumente une, et n'ecrit alors QUE les
    entrees des fichiers qu'elle a joues -- le tampon vit dans l'entree, donc rien n'est pretendu
    sur les autres.
    """
    import json

    mesures = [rel for rel in joues if horloge.n.get(rel, 0) > 0]
    if rc in RC_PYTEST_SANS_MESURE or not mesures:
        cause = ("pytest rc=%d (%s)" % (rc, {2: "interrompu", 3: "erreur interne",
                                             4: "erreur d'USAGE -- rien n'a ete joue",
                                             5: "aucun test collecte"}.get(rc, "non exploitable"))
                 if rc in RC_PYTEST_SANS_MESURE
                 else "aucun des %d fichier(s) joue(s) n'a produit le moindre report" % len(joues))
        print("[457] REFUS D'ECRIRE : %s." % cause)
        print("[457] Les poids ET l'empreinte sont INCHANGES -- une mesure vide ecrite serait pire")
        print("[457] que pas de mesure : elle effacerait des entrees VALIDES et ferait payer un")
        print("[457] rejeu total a tout le monde sous `--since`.")
        print("[457] Cause la plus frequente : lancement hors `%s`." % _PYDIR)
        print("[457] rc=%d -- aucun verdict sur le depot." % EX_NON_MESURE)
        return EX_NON_MESURE

    # FUSION (mode incremental) puis RESTRICTION au perimetre : un fichier de test supprime ne
    # doit pas laisser son poids derriere lui -- il gonflerait le `defaut` de `bins_of` pour rien.
    poids = {rel: poids_connus[rel] for rel in perimetre if rel in poids_connus}
    poids.update({rel: round(horloge.sec.get(rel, 0.0), 3) for rel in joues})
    manquants = [rel for rel in joues if horloge.n.get(rel, 0) == 0]

    path = _weights_path()
    if ecrire_poids:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(poids, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    else:
        # POIDS ABSENTS (#463-r1) : ecrire ce que cette passe a mesure fabriquerait un fichier de
        # poids a UNE entree, et ce serait PIRE que pas de poids du tout -- `bins_of` prend
        # `defaut = max(weights.values())`, donc le poids d'un seul fichier deviendrait la valeur
        # supposee de TOUS les autres. Le repli md5, lui, repartit par nombre et reste honnete.
        print("[457] POIDS NON ECRITS : ce checkout n'en avait aucun, et un fichier de poids a "
              "%d entree(s) fixerait le `defaut` de `bins_of` sur une valeur non representative."
              % len(joues))
        print("[457] Le repli md5 reste en place (mur sous-optimal, verdict INCHANGE). "
              "L'EMPREINTE, elle, est ecrite ci-dessous -- c'est elle qui est VERSIONNEE.")

    empreinte_refusee = False
    if empreinte is not None:
        # Empreinte MESUREE -- VERSIONNEE, avec le commit qui l'horodate (cf. `_footprints_path`).
        # Sans `_commit`, la selection ne peut pas mesurer son age et refuse de s'appliquer.
        # `tolere_rc` : un rc non nul laisse `_commit` a None, et `impacted_files` REFUSE alors de
        # s'appliquer (TOUT rejoue) -- degradation SURE, deja ecrite ; pas de quoi lever.
        tete = _git(["rev-parse", "HEAD"], "horodatage de l'empreinte", tolere_rc=True)

        def _versionnable(r: str) -> bool:
            # Bruit MACHINE, jamais dans un diff : bytecode et sorties de run. Les garder gonflerait
            # un fichier versionne de 521 lignes illisibles (mesure) sans rien apporter -- ils sont
            # deja ignores a la lecture.
            return not (r.endswith(".pyc") or "__pycache__" in r or r.startswith("logs/"))

        def _dossiers(chemins) -> list:
            # On stocke les REPERTOIRES, pas les fichiers -- c'est exactement la granularite a
            # laquelle `impacted_files` compare (un test qui lit `docs/rl/x.md` doit rejouer si
            # `docs/rl/y.md` change, sinon un fichier NEUF passerait entre les mailles). Stocker
            # chaque fichier ne rendrait AUCUNE precision, et pesait 961 Ko versionnes.
            return sorted({c.rsplit("/", 1)[0] for c in chemins if _versionnable(c) and "/" in c})

        # GARDE DE REGIME (#464-r2). Un module du domaine lu GLOBALEMENT signe un bytecode qui
        # n'etait pas a jour : `import` a ouvert la SOURCE. L'empreinte decrirait alors le
        # `__pycache__` de la machine (mesure : 552 globales a froid contre 3 a chaud) -- et elle
        # est VERSIONNEE, donc le defaut serait propage. On REFUSE de l'ecrire.
        modules = _modules_du_graphe()
        brutes = [g for g in empreinte.globales if _versionnable(g)]
        modules_globaux = sorted(g for g in brutes if _est_module_du_domaine(g, modules))
        if modules_globaux and not _echappatoire_regime():
            print("[457] REFUS D'ECRIRE L'EMPREINTE : %d module(s) du domaine lu(s) en GLOBAL, "
                  "donc le bytecode n'etait pas a jour au moment de la mesure."
                  % len(modules_globaux))
            for rel in modules_globaux[:5]:
                print("        %s" % rel)
            print("[457] Une empreinte mesuree dans ce regime decrit le __pycache__ de la machine,")
            print("[457] pas le depot -- et elle est VERSIONNEE. Les POIDS, eux, sont ecrits.")
            print("[457] Causes usuelles : PYTHONDONTWRITEBYTECODE=1, `logs/` non ecrivable, ou un")
            print("[457] module non compilable. Remede : relancer `--measure` (le prechauffage a")
            print("[457] deja tourne). Echappatoire CONSCIENTE si la lecture est APPLICATIVE")
            print("[457] (un conftest qui lit un .py comme DONNEE) : %s=1" % _ENV_ECHAPPATOIRE)
            empreinte_refusee = True
        else:
            emp_path = _footprints_path()
            emp = _empreinte_fusionnee(
                mesures=mesures,
                lus_par_test=empreinte.par_test,
                dossiers=_dossiers,
                temoins=lambda c: _temoins(c, _versionnable),
                globales=sorted(brutes),
                commit=(tete.stdout or "").strip() or None,
                complete=complete,
                mods=modules)
            emp_path.write_text(json.dumps(emp, indent=1, sort_keys=True) + "\n",
                                encoding="utf-8")

            hors_py = sorted({r for r in emp["_globales"] if not r.endswith(".py")})
            hors_py_test = sorted({r for v in empreinte.par_test.values() for r in v
                                   if not r.endswith(".py")})
            print("[457] empreinte -> %s : %d entree(s) de test (%s ; %d rafraichie(s) par cette "
                  "passe), %d lecture(s) GLOBALE(s) (non attribuables -> impactent TOUT), dont %d "
                  "hors .py ; %d fichier(s) hors .py lus pendant les tests"
                  % (emp_path, len(emp["par_test"]),
                     "REECRITE en entier" if complete else "FUSION partielle",
                     len(mesures), len(emp["_globales"]), len(hors_py), len(hors_py_test)))
    else:
        print("[457] empreinte NON INSTRUMENTEE par cette passe -- fichier versionne INCHANGE.")

    joue = sum(round(horloge.sec.get(rel, 0.0), 3) for rel in joues)
    print("[457] %d fichier(s) joue(s), %.1f s de tests mesures en %.1f s de mur ; %s"
          % (len(joues), joue, elapsed,
             ("%d poids -> %s" % (len(poids), path)) if ecrire_poids
             else "poids NON ecrits (aucun n'existait dans ce checkout)"))
    for rel in sorted(joues, key=lambda r: -horloge.sec.get(r, 0.0))[:5]:
        print("    %7.1f s  %s" % (horloge.sec.get(rel, 0.0), rel))
    if manquants:
        # Un fichier a 0 s n'est pas anodin : il n'a produit AUCUN report (collecte vide, items
        # tous deselectionnes). Le dire -- il garde un poids nul, jamais le maximum.
        print("[457] %d fichier(s) sans mesure (0 report) : %s"
              % (len(manquants), ", ".join(manquants[:5])))
    if rc != 0:
        print("[457] pytest rc=%d -- mesure %s (les fichiers ONT ete joues), mais l'arbre est "
              "ROUGE" % (rc, "ecrite" if ecrire_poids else "ecrite (empreinte seule)"))
        return 1
    if empreinte_refusee:
        # Le GISEMENT est vert, mais le LIVRABLE << empreinte >> n'a pas ete produit. Ne pas rendre
        # 0 : un `--measure` qui n'ecrit pas l'empreinte et se tait passerait pour une maintenance
        # faite. `EX_NON_MESURE` est deja la convention << ce run n'a pas produit sa mesure >>.
        print("[457] rc=%d -- l'arbre est VERT, mais l'EMPREINTE n'a pas ete produite "
              "(cf. ci-dessus)" % EX_NON_MESURE)
        return EX_NON_MESURE
    return 0


def _pycache_prefix():
    """Ou le bytecode de la MESURE est ecrit -- surtout PAS `scripts/python/**/__pycache__`.

    `sys.pycache_prefix` (CPython >= 3.8) redirige tout le bytecode vers une arborescence miroir.
    Deux raisons, dans cet ordre :

      1. #455 -- un cliquet n'ECRIT JAMAIS dans `scripts/python` : la banque tourne en parallele et
         plusieurs cliquets ENUMERENT cet arbre. Faire apparaitre des dizaines de `__pycache__`
         pendant qu'un voisin le parcourt est exactement la course mesuree entre `probe_455` et
         `probe_391`.
      2. #464-r2 -- le prechauffage doit etre REPRODUCTIBLE. Sous `logs/` (gitignore, deja le foyer
         des poids), il survit d'une mesure a l'autre sans jamais entrer dans un diff.
    """
    return repo_root() / "logs" / "ratchets" / "457-pycache"


def _prechauffer_cache_pytest(perimetre: list, prefixe: str) -> int:
    """Fait fabriquer a PYTEST son propre bytecode, dans un SOUS-PROCESS. Rend le rc.

    `compileall` ne suffit PAS, et la mesure l'a tranche : pytest REECRIT les assertions des
    fichiers de test et des `conftest.py`, et son chargeur REJETTE un `.pyc` qui ne porte pas sa
    marque -- il relit donc la SOURCE. Mesure du 2026-08-04, prechauffage `compileall` seul :
    REFUS du garde de regime sur **136** modules, soit exactement les **132** fichiers du perimetre
    + les **3** `conftest.py` + 1.

    Ces lectures-la ne sont pas du bruit inevitable : elles dependent de la presence du cache
    PYTEST, donc de l'etat de la machine -- exactement le defaut de #464-r2, deplace d'un cran.
    Une passe `--collect-only` les fabrique une bonne fois.

    SOUS-PROCESS, et c'est le point : collecter dans le process courant laisserait les modules de
    test dans `sys.modules`, si bien que le vrai run ne re-executerait PAS leur code de niveau
    module -- on PERDRAIT les lectures globales legitimes d'un test-BALAYAGE qui ouvre
    `data/symbols/**` a l'import. Le cache se partage par le disque ; l'etat du process, non.
    """
    import subprocess as _sp

    env = dict(os.environ)
    env["PYTHONPYCACHEPREFIX"] = prefixe
    r = _sp.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
                 *perimetre],
                cwd=str(_PYDIR), env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace")
    return int(r.returncode)


def _prechauffer_bytecode(perimetre=None) -> tuple:
    """Compile `scripts/python/**` AVANT de poser le hook. Rend `(prefixe, secondes)`.

    LA CAUSE de #464-r2, traitee a sa racine. Sans bytecode a jour, `import` ouvre la SOURCE `.py`
    -- et le hook d'audit `open` compte cette ouverture comme une lecture du depot. Mesure du
    2026-08-04, MEME arbre MEME probe : `_globales` = 552 a froid contre 3 a chaud, et `par_test`
    = 52 entrees contre 47. L'empreinte decrivait donc l'etat du `__pycache__` de la machine.

    Le prechauffage RETIRE la cause au lieu de filtrer le symptome -- il ne fait disparaitre AUCUNE
    information : une lecture applicative de `.py` (un test-BALAYAGE qui ouvre le code source pour
    l'analyser -- ils sont nombreux ici) reste un `open` bien reel, vu et attribue. C'est ce qui
    interdisait de simplement retirer les `.py` de `par_test` : ces lectures-la ne sont couvertes
    par AUCUN import, donc par aucune preuve.

    Best-effort assume : un echec de compilation n'interrompt pas la mesure -- c'est le GARDE DE
    REGIME de `_ecrire_mesure` qui la sanctionne, en refusant d'ecrire une empreinte qui decrirait
    le `__pycache__` plutot que le depot. Ce partage est deliberatif : ici on AGIT, la-bas on
    VERIFIE le resultat, jamais l'inverse.
    """
    import compileall

    prefixe = str(_pycache_prefix())
    sys.pycache_prefix = prefixe
    # `PYTHONPYCACHEPREFIX` EN PLUS, et c'est INDISPENSABLE : `workers != 1` fait compiler
    # `compile_dir` dans des SOUS-PROCESS, qui n'heritent PAS d'une affectation a
    # `sys.pycache_prefix` -- elle ne vit que dans l'interpreteur courant. Mesure du 2026-08-04 avec
    # `workers=0` seul : **1691** `.pyc` deposes dans `scripts/python/**/__pycache__` (violation
    # #455) contre 1030 dans le prefixe, et le GARDE DE REGIME a refuse l'empreinte sur **548**
    # modules lus en source. La variable d'environnement, elle, traverse le fork.
    os.environ["PYTHONPYCACHEPREFIX"] = prefixe

    avant = _pyc_dans_l_arbre()
    started = time.time()
    try:
        compileall.compile_dir(str(_PYDIR), quiet=2, workers=0, force=False)
    except Exception as exc:                                   # pragma: no cover - best effort
        print("[457] prechauffage bytecode INTERROMPU (%s) -- le garde de regime tranchera"
              % type(exc).__name__)
    if perimetre:
        # Le SECOND etage, indispensable : le bytecode que PYTEST fabrique pour lui-meme.
        rc = _prechauffer_cache_pytest(perimetre, prefixe)
        if rc != 0:
            print("[457] prechauffage du cache pytest : rc=%d (collecte non nominale) -- le garde "
                  "de regime tranchera" % rc)
    fuite = _pyc_dans_l_arbre() - avant
    if fuite > 0:
        # Le DIRE tout de suite : sans cela, la cause ne se lit qu'a la fin, apres ~20 min.
        print("[457] ATTENTION -- %d fichier(s) .pyc ecrit(s) DANS scripts/python malgre le "
              "prefixe : la redirection n'a pas pris (#455 + #464-r2)" % fuite)
    return prefixe, time.time() - started


def _pyc_dans_l_arbre() -> int:
    """Combien de `.pyc` vivent sous `scripts/python` -- le temoin DIRECT que le prefixe a pris."""
    return sum(1 for _ in _PYDIR.rglob("*.pyc"))


def _measure(perimetre: list, seulement_manquants: bool = False) -> int:
    """Chronometre le perimetre (ou ses seuls fichiers SANS poids) et reecrit les poids. ASCII only."""
    if not perimetre:
        # Un perimetre vide n'est pas une mesure a zero : c'est un effondrement de perimetre
        # (`git ls-files` muet, checkout partiel). Le DIRE, et n'ecrire RIEN.
        print("[457] --measure : perimetre VIDE, rien a mesurer")
        print("[457] rc=%d -- aucun verdict sur le depot." % EX_NON_MESURE)
        return EX_NON_MESURE

    poids_connus = _weights() if seulement_manquants else {}
    # LES POIDS SONT-ILS ABSENTS, OU LES FICHIERS SONT-ILS SANS POIDS ? (#463-r1). Deux etats que
    # `poids_connus == {}` confondait, et c'est le tri-etat que ce depot tient partout ailleurs :
    # `logs/` est GITIGNORE, donc un worktree d'agent n'a JAMAIS de poids -- pas << 235 fichiers
    # neufs >>, mais << je n'ai pas mesure les poids >>.
    poids_absents = seulement_manquants and not _weights_path().exists()
    if seulement_manquants:
        # DEUX criteres, et c'est le sens du mode : un fichier neuf n'a NI poids NI entree
        # d'empreinte. L'ABSENCE d'entree est detectable sans le graphe ; la PEREMPTION d'une
        # entree, elle, n'est PAS chassee ici -- une entree perimee fait simplement rejouer son
        # test sous `--since`, ce qui est deja le comportement voulu, et la poursuivre ferait
        # degenerer ce mode en `--measure` complet des qu'un module partage change (#486-r15).
        emp = _footprints()
        deja = set((emp.get("par_test") or {}) if emp.get("_format") == FORMAT_EMPREINTE else {})
        if poids_absents:
            # LE CRITERE << sans poids >> N'EST PAS APPLICABLE : il vaudrait pour TOUT LE MONDE.
            # Mesure du 2026-08-07 depuis un worktree d'agent : `--measure-missing` retenait
            # **235 fichiers sur 235**, soit un `--measure` complet (~976 s) -- c'est-a-dire que
            # le geste que `loop_status` et `probe_463r1` recommandent etait IMPRATICABLE dans le
            # seul regime ou leurs lecteurs le lisent. On retient donc le SEUL critere
            # applicable, l'EMPREINTE, et on le DIT.
            joues = [rel for rel in perimetre if rel not in deja]
        else:
            joues = [rel for rel in perimetre if rel not in poids_connus or rel not in deja]
        if not joues:
            print("[457] --measure-missing : les %d fichier(s) du perimetre ont deja %s, rien a "
                  "mesurer" % (len(perimetre),
                               "une entree d'empreinte" if poids_absents
                               else "un poids ET une entree d'empreinte"))
            return 0
        if poids_absents:
            print("[457] --measure-missing : POIDS ABSENTS de ce checkout (%s est gitignore, donc"
                  " un worktree n'en a jamais). Ce n'est PAS << aucun fichier n'a de poids >> :"
                  % _weights_path())
            print("[457] le critere retenu est le SEUL applicable, l'ENTREE D'EMPREINTE.")
        print("[457] --measure-missing : %d fichier(s) %s sur %d ; les %d autres gardent leur "
              "mesure" % (len(joues),
                          "SANS entree d'empreinte" if poids_absents
                          else "SANS poids ou SANS entree d'empreinte",
                          len(perimetre), len(perimetre) - len(joues)))
    else:
        joues = list(perimetre)

    horloge = _TimePerFile()
    filet = _DeselectLiveItems()
    # AVANT le hook : le bytecode a jour, sinon `import` ouvre les SOURCES et l'empreinte mesure le
    # `__pycache__` de la machine (#464-r2). NECESSAIRE AUSSI EN PARTIEL depuis #486-r15, qui ecrit
    # l'empreinte des fichiers joues : sans lui, le GARDE DE REGIME refuserait l'ecriture. Le cout
    # reste borne -- `compileall(force=False)` ne recompile que ce qui a bouge, et le second etage
    # ne collecte que `joues`.
    ou, secs = _prechauffer_bytecode(joues)
    print("[457] bytecode prechauffe en %.1f s -> %s (hors scripts/python, cf. #455)" % (secs, ou))
    # L'empreinte pose un audit hook GLOBAL et IRREVERSIBLE sur `open`. Elle est installee dans les
    # DEUX modes : le tampon vit dans l'ENTREE, donc une passe partielle rafraichit exactement ce
    # qu'elle a joue sans rien pretendre du reste (#486-r15).
    empreinte = _FilesPerTest(repo_root())
    started = time.time()
    rc = pytest.main(["-q", "-p", "no:cacheprovider", *joues],
                     plugins=[horloge, filet, empreinte])
    elapsed = time.time() - started

    return _ecrire_mesure(perimetre, joues, horloge, empreinte, int(rc), elapsed, poids_connus,
                          complete=not seulement_manquants, ecrire_poids=not poids_absents)


#: ---------------------------------------------------------------------------------------------
#: SELECTION PAR DIFF (`--since`). DEUX mecanismes COMPLEMENTAIRES, et le partage des roles est
#: STRICT : le graphe d'imports couvre l'axe `import` (tout `.py` du domaine), l'empreinte couvre
#: ce qu'aucun import ne revele -- un test qui lit `data/symbols/...`, `docs/...` ou
#: `frida/hooks/*.ts`.
#:
#: Le hook d'audit, lui, voyait AUSSI ce que la MACHINE fait faire a l'import : des `.pyc` quand le
#: cache est chaud, les SOURCES `.py` quand il est froid. Ni l'un ni l'autre n'est une information
#: sur le DEPOT -- d'ou le prechauffage et son garde de regime (#464-r2), qui suppriment la cause
#: au lieu de filtrer la trace.
#:
#: TOUT CE QUI N'EST PAS PROUVE IMPACTE. Un test sans empreinte, un module illisible, un import
#: dynamique, une empreinte absente : impacte. La selection ne peut que RETIRER des tests dont on
#: a montre l'independance -- jamais en retirer par defaut. C'est ce qui la separe d'une table
#: ecrite a la main, qui est le vice recurrent de ce depot (5 occurrences).
#: ---------------------------------------------------------------------------------------------

def _module_name(rel: str) -> str:
    nom = rel[len(TESTS_DIR.rsplit("/", 1)[0]) + 1:-3].replace("/", ".")
    return nom[:-len(".__init__")] if nom.endswith(".__init__") else nom


#: Ce que l'empreinte ATTESTE d'elle-meme, en clair dans le fichier versionne : elle a ete mesuree
#: bytecode a jour, donc aucune de ses lectures ne vient de la compilation d'un import. Chaine
#: CONSTANTE -- identique a froid et a chaud, donc aucun bruit de diff (#464-r2).
REGIME_MESURE = ("bytecode PRECHAUFFE avant la mesure -- aucune lecture GLOBALE ne provient d'un "
                 "import (garde de regime #464-r2)")

#: Echappatoire CONSCIENTE au garde de regime, sur le patron de `TACTICUS_ALLOW_GREEN_SKIP` (#455).
#: A n'employer que si la lecture globale d'un module est APPLICATIVE (un `conftest.py` qui ouvre
#: un `.py` comme DONNEE) -- pas pour faire taire un prechauffage en echec.
_ENV_ECHAPPATOIRE = "TACTICUS_457_ACCEPTE_PY_GLOBAUX"


def _echappatoire_regime() -> bool:
    return bool(os.environ.get(_ENV_ECHAPPATOIRE))


def _modules_du_graphe(racine=None) -> dict:
    """`{chemin relatif au depot -> nom de module}` pour tout `.py` VERSIONNE de `scripts/python`.

    FOYER UNIQUE du domaine (#464-r2). C'est A LA FOIS le domaine sur lequel `_import_graph`
    resout les imports, et l'ensemble que le filtre de `_couverte_par_le_graphe` consulte pour
    decider qu'une lecture globale est deja couverte. Les deriver separement -- une fois a
    l'ecriture de l'empreinte, une fois a sa lecture -- ouvrirait un ecart SILENCIEUX : une
    lecture retiree d'un cote sans etre couverte de l'autre est exactement le faux vert de #464.

    #471 : `git` en echec levait un `{}` SILENCIEUX. C'etait pire qu'un crash -- avec `mods` vide,
    la cloture du graphe d'imports est vide, donc `impacted_files` SOUS-selectionne : un faux VERT,
    exactement le mode de defaillance que `_footprints_path` decrit pour une empreinte videe.
    Desormais la panne d'outil leve, et le probe rend << non mesure >>.
    """
    r = _git(["ls-files", "scripts/python"],
             "impossible de deriver le domaine du graphe d'imports", racine=racine)
    return {l.strip(): _module_name(l.strip())
            for l in r.stdout.splitlines() if l.strip().endswith(".py")}


def _est_module_du_domaine(rel: str, modules) -> bool:
    """`True` si `rel` est un module du domaine du graphe (`_modules_du_graphe`).

    Sert au GARDE DE REGIME, PAS a filtrer (#464-r2). La nuance est le coeur de l'arbitrage :

    Un module du domaine lu PENDANT un import est couvert par le graphe -- mais le hook d'audit ne
    sait pas dire d'ou vient un `open`. Ce depot est plein de tests-BALAYAGE qui OUVRENT le code
    source pour l'analyser, et un `conftest.py` pourrait faire de meme A LA COLLECTE : cette
    lecture-la n'est couverte par AUCUN import, donc par aucune preuve. Retirer les modules des
    globales << parce qu'ils sont bruyants >> retirerait donc, un jour, un vrai signal -- exactement
    le faux vert de #464.

    D'ou le choix : on ne FILTRE pas, on traite la CAUSE (`_prechauffer_bytecode`) et on VERIFIE
    qu'elle a bien ete traitee. En regime nominal ce predicat ne designe plus rien.
    """
    return rel in modules


def _conftest_edges(mods: dict) -> dict:
    """Aretes de la semantique PYTEST, qu'aucune instruction `import` ne rend visibles.

    Un `conftest.py` s'applique a TOUT fichier de test de son repertoire et de ses
    sous-repertoires -- fixtures, hooks, `autouse`. Aucun test ne l'IMPORTE, donc le graphe
    purement syntaxique s'arretait sur lui, et tout ce qu'il importe lui-meme s'arretait la aussi.

    Mesure du 2026-08-04 sur `origin/master`, AVANT cette arete : changer n'importe lequel des 4
    `conftest.py` ne retenait que **2 fichiers de test sur 132** -- alors que
    `scripts/python/tests/conftest.py` porte `green_skip_guard` (le garde de #455),
    `pytest_runtest_makereport` et trois fixtures `autouse`. Le meme trou frappait donc, par
    transitivite, tout module importe par un conftest.

    Ce trou est INDEPENDANT du regime chaud/froid (un `conftest.py` est dans `mods`, donc il n'a
    jamais ete confronte a `_globales`). Il est ferme ICI parce que la couverture par le graphe
    est ce sur quoi #464-r2 s'appuie pour cesser de compter les modules : la preuve devait etre
    VRAIE, pas postulee.
    """
    conftests = [rel for rel in mods if rel.rsplit("/", 1)[-1] == "conftest.py"]
    tests = [rel for rel in mods if _is_test_file(rel.rsplit("/", 1)[-1])]
    aretes = {}
    for c in conftests:
        base = c.rsplit("/", 1)[0] + "/"
        cibles = {t for t in tests if t.startswith(base)}
        if cibles:
            aretes[c] = cibles
    return aretes


#: `{(empreinte des sources, modules): (inverse, incertains, direct, shas)}` -- memoise pour la
#: duree du process (#486-r5, elargi par #486-r15).
#:
#: POURQUOI. `_import_graph` lit et `ast.parse` tout `scripts/python/**`. `tests/
#: test_457_r8_selection_par_diff_offline.py` l'exerce sur l'arbre REEL dans TROIS tests
#: differents, et `--since` l'appelle une fois de plus.
#:
#: SUR A PARTAGER : la valeur rendue est FIGEE (`dict` de `frozenset`, `frozenset`), donc aucun
#: appelant ne peut modifier ce que verra le suivant -- le `defaultdict(set)` d'origine, lui,
#: aurait laisse fuiter une mutation. Et la cle porte l'EMPREINTE (mtime, taille) des sources :
#: un fichier modifie entre deux appels invalide le cache au lieu de rendre un graphe perime.
_GRAPHE_CACHE: dict = {}


def _empreinte_sources(mods: dict, racine) -> tuple:
    """`(chemin, mtime_ns, taille)` de chaque source du domaine. Cle du cache du graphe."""
    out = []
    for rel in sorted(mods):
        try:
            st = (racine / rel).stat()
            out.append((rel, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((rel, None, None))
    return tuple(out)


def _import_graph(mods: dict) -> tuple:
    """(qui-importe-qui inverse, modules a resolution INCERTAINE). Purement statique.

    Le resultat est FIGE et memoise -- cf. `_GRAPHE_CACHE`."""
    racine = repo_root()
    cle = (_empreinte_sources(mods, racine), tuple(sorted(mods.items())))
    if cle not in _GRAPHE_CACHE:
        _GRAPHE_CACHE[cle] = _calculer_import_graph(mods, racine)
    return _GRAPHE_CACHE[cle]


def _calculer_import_graph(mods: dict, racine) -> tuple:
    """LE calcul, sans cache -- meme critere qu'avant #486-r5.

    Lecture PARALLELE (`repo_read`, 16 threads) : l'ouverture d'un fichier sous `scripts/` pese
    ~7 ms (filtre systeme sur les extensions executables). Les octets sont passes tels quels a
    `ast.parse`, comme le faisait `read_bytes()` -- l'echec de lecture (`None`) rejoint la meme
    branche `incertains` que l'`OSError` d'origine.

    """
    import ast as _ast
    from collections import defaultdict

    par_nom = defaultdict(set)
    for rel, m in mods.items():
        par_nom[m].add(rel)

    inverse = defaultdict(set)
    incertains = set()
    ordre = list(mods)
    octets = repo_read.read_bytes_many([str(racine / rel) for rel in ordre])
    for rel, data in zip(ordre, octets):
        try:
            if data is None:
                raise OSError(rel)
            arbre = _ast.parse(data)
        except (OSError, SyntaxError, ValueError):
            incertains.add(rel)          # illisible : on ne PRETEND pas savoir
            continue
        noms, dyn = set(), False
        for n in _ast.walk(arbre):
            if isinstance(n, _ast.Import):
                noms.update(a.name for a in n.names)
            elif isinstance(n, _ast.ImportFrom):
                if n.level:
                    dyn = True           # import relatif : non resolu ici
                if n.module:
                    noms.add(n.module)
                    noms.update(n.module + "." + a.name for a in n.names)
            elif isinstance(n, _ast.Call):
                f = n.func
                if (getattr(f, "attr", None) or getattr(f, "id", None)) in (
                        "import_module", "__import__", "load_module", "exec_module"):
                    dyn = True
        if dyn:
            incertains.add(rel)
        for nom in noms:
            morceaux = nom.split(".")
            for i in range(len(morceaux), 0, -1):
                cle = ".".join(morceaux[:i])
                if cle in par_nom:
                    for cible in par_nom[cle]:
                        inverse[cible].add(rel)
                    break

    # La semantique pytest, que l'AST ne peut PAS voir (aucun test n'importe son conftest).
    for conf, cibles in _conftest_edges(mods).items():
        inverse[conf].update(cibles)
    # FIGE avant de sortir : la valeur est memoisee et partagee entre appels (#486-r5).
    # `impacted_files` ne fait que `inverse.get(...)` et `rel in incertains` -- les deux formes
    # marchent a l'identique sur un `dict` de `frozenset` et un `frozenset`.
    return {k: frozenset(v) for k, v in inverse.items()}, frozenset(incertains)


#: LE HASH PAR DEP A ETE ESSAYE PUIS ECARTE, et la mesure qui l'a tue vaut d'etre gardee.
#:
#: L'idee etait de faire porter a chaque dep son propre hash de contenu, pour decider par
#: comparaison de hashes plutot que par un diff. Trois mesures du 2026-08-07 la refutent :
#:
#:   * les deps SONT des repertoires (1 226 sur 1 227) ; descendre au FICHIER pour les hacher
#:     fait passer les 88 entrees de 1 227 a **59 592** couples -- x48,6, plusieurs Mo VERSIONNES ;
#:   * hacher en LISANT coute 680 ms pour `engine/` et **4 001 ms** pour `scripts/python/`, quand
#:     le plus petit test offline pese **80 ms** et les 165 plus legers **13,1 s a eux tous** ;
#:   * `stat()` seul n'est pas un refuge (2 643 ms) : sous Windows c'est le NOMBRE d'appels
#:     systeme qui coute, pas le volume lu.
#:
#: Et surtout, un hash repond a une question que le DIFF a deja tranchee. `git diff --name-only`
#: rend la liste des chemins modifies ; on l'apparie aux globs declares et aux deps mesurees --
#: appariement de CHAINES, zero lecture, zero sha. Un repertoire s'apparie meme MIEUX qu'un
#: fichier : un fichier NEUF dans ce repertoire est couvert sans que rien ne bouge.
#:
#: LA FRAICHEUR SE REPARE ALORS TOUTE SEULE, a condition que la mise a jour PARTIELLE existe --
#: c'est le coeur de #486-r15. Le fichier de test change ? il est dans le diff, donc selectionne,
#: donc joue, donc son entree est REECRITE. Un module de ses deps change ? meme chaine. Le seul
#: cas dangereux -- un module qui se met a lire une donnee que l'empreinte du test ignore -- est
#: donc couvert AU MOMENT MEME ou ce module change.


#: L'empreinte est VERSIONNEE, contrairement aux poids -- et l'asymetrie est le point.
#: Des POIDS perimes coutent du MUR, jamais un faux vert : ils ne font que deplacer des fichiers
#: entre shards. Une EMPREINTE perimee, elle, ferait SAUTER des tests. La versionner telle quelle
#: convertirait donc un defaut local en faux vert PARTAGE.
#: Ce qui la rend versionnable : CHAQUE ENTREE porte sa propre cle de validite, calculee sur le
#: CONTENU de la fermeture d'imports du test (#486-r15). Une entree dont la fermeture a bouge
#: MANQUE -- elle ne ment pas -- et son test est rejoue. Perimee, l'empreinte selectionne donc
#: TROP, entree par entree, et retombe continument sur le rejeu total a mesure qu'elle vieillit.
#: Meme classe de surete que les poids, sans en partager la fragilite.
#:
#: CE QU'ELLE NE PORTE PLUS : un `_commit` GLOBAL comme critere. Il etait ecrit dans le worktree
#: d'un AGENT, donc sur une branche que le squash-merge remplace par un commit neuf avant de la
#: supprimer -- le sha naissait MORT, et l'empreinte entiere devenait inverifiable A CHAQUE
#: LIVRAISON PAR PR. Mesure du 2026-08-07 : `57bb2a7c` inconnu de git, `--since` a 220/220 sur les
#: 8 dernieres bases. `_commit` reste ECRIT dans chaque entree, en contexte informatif.
#: Placee sous `scripts/`, PAS sous `scripts/python/` (#455 : la banque y enumere en parallele) et
#: PAS sous `data/`, qui est reserve aux ENTREES du jeu et dont un cliquet garde la composition.
def _footprints_path():
    return repo_root() / "scripts" / "ratchets-457-footprints.json"


def _footprints() -> dict:
    import json
    for p in (_footprints_path(), _weights_path().parent / "457-footprints.json"):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
    return {}


def _changed(ref: str) -> list:
    """Les fichiers changes entre `ref` et HEAD, ou `None` si la ref est inconnue de git.

    `tolere_rc=True` a dessein : un rc non nul dit ici << cette ref n'existe pas >>, ce que
    `impacted_files` traduit deja en << TOUT rejoue >>. C'est une INFORMATION exploitable, pas une
    panne d'outil -- la seule panne (git non lancable) leve depuis `_git` (#471)."""
    r = _git(["diff", "--name-only", ref, "HEAD"],
             "diff de selection `--since`", tolere_rc=True)
    if r.returncode != 0:
        return None
    return sorted({l.strip() for l in r.stdout.splitlines() if l.strip()})


#: Marqueur cherche en SOUS-CHAINE avant tout `ast.parse` : un fichier qui ne l'ecrit pas ne
#: declare rien, et n'est donc jamais parse. C'est ce qui rend l'evaluation bon marche.
_MARQUEUR_DECL = declencheur_cliquet.NOM


def declencheurs_du_perimetre(perimetre: list, racine=None) -> tuple:
    """`({rel: globs effectifs}, {rel: pourquoi la declaration n'est PAS servie})`.

    L'EVALUATION DOIT COUTER MOINS QUE LE TEST (#486-r15). Mesure du 2026-08-07 sur ce depot :
    165 des 220 fichiers offline pesent **13,1 s A EUX TOUS** (moyenne 0,08 s). Un selecteur qui,
    pour decider de les jouer, balaierait le corpus ou calculerait une fermeture d'imports
    (32,7 s d'`ast.parse`) serait PERDANT par construction. D'ou les trois crans, dans cet ordre :

      1. on ne lit QUE les fichiers du perimetre (220 petits fichiers, en parallele) ;
      2. un PRE-FILTRE par SOUS-CHAINE ecarte tout fichier qui n'ecrit pas le mot `DECLENCHEUR` --
         aucun AST pour lui ;
      3. `ast.literal_eval` sur la seule affectation trouvee, jamais un `import` du module (le
         patron de `declencheur_cliquet.lire` : un fichier dont l'import PLANTE doit pouvoir
         declarer quand meme).

    UNE DECLARATION MAL FORMEE N'EST PAS SERVIE, et la raison est rendue : le fichier retombe sur
    le mecanisme MESURE. Servir une declaration douteuse serait le seul sens dangereux.
    """
    racine = racine or repo_root()
    chemins = ["scripts/python/" + rel for rel in perimetre]
    textes = repo_read.read_texts([str(racine / c) for c in chemins], errors="replace")
    servis: dict = {}
    ecartes: dict = {}
    for rel, source_rel, texte in zip(perimetre, chemins, textes):
        if texte is None:
            ecartes[rel] = "fichier illisible"
            continue
        if _MARQUEUR_DECL not in texte:
            ecartes[rel] = "aucune declaration"
            continue
        try:
            # `lire` RE-OUVRE le fichier. C'est deliberé : on ne touche pas au foyer partage
            # `declencheur_cliquet` (vendore a l'IDENTIQUE de #486-r12, pour qu'un conflit
            # add/add se resolve trivialement), et le surcout ne porte que sur les fichiers qui
            # ont DEJA passe le pre-filtre par sous-chaine -- c'est-a-dire ceux qui declarent.
            d = declencheur_cliquet.lire(racine / source_rel)
        except (declencheur_cliquet.DeclencheurAbsent, OSError, SyntaxError) as exc:
            ecartes[rel] = str(exc)
            continue
        fautes = declencheur_cliquet.valider(d)
        if fautes:
            ecartes[rel] = "declaration MAL FORMEE : %s" % fautes[0]
            continue
        if d.get("toujours"):
            ecartes[rel] = "`toujours: True` -- rien ne le borne"
            continue
        # `racine` EXPLICITE : le perimetre effectif inclut desormais la CASCADE DE HARNAIS,
        # que le foyer DERIVE du disque (#531). La laisser retomber sur `declencheur_cliquet.
        # RACINE` marcherait ici -- les deux racines coincident -- mais elle ferait dependre la
        # selection d'une racine calculee AILLEURS, sur un critere different (`repo_root` remonte
        # depuis le cwd, `RACINE` depuis le module). Deux derivations d'une meme racine sont
        # exactement la forme d'ecart silencieux que #463-r1 a ferme.
        servis[rel] = declencheur_cliquet.perimetre(d, source_rel, racine)
    return servis, ecartes


def impacted_files(perimetre: list, ref: str) -> tuple:
    """(sous-ensemble du perimetre a rejouer, raison). Retourne le perimetre ENTIER si un doute
    subsiste -- et la raison le DIT, pour qu'un rejeu total ne se lise jamais comme une mesure.

    DEUX MOITIES, ET IL FAUT LES DEUX (#486-r15) :

      * DECLAREE  -- le `DECLENCHEUR` du fichier de test, apparie au diff par simple regex. Bon
        marche, lisible, et il exprime ce qu'aucune mesure ne voit : l'INTENTION. Il ne vaut que
        parce qu'un cliquet le CONFRONTE a la mesure (`probe_486r15_declencheurs_tests.py`) ;
      * MESUREE   -- graphe d'imports + empreinte des fichiers reellement ouverts. Elle voit ce
        que la declaration oublie, et c'est elle qui decide pour tout fichier NON declare.

    Le graphe est PARESSEUX : il n'est calcule que s'il reste au moins un fichier non declare.
    C'est la ou passe le cout (32,7 s d'`ast.parse` sur 2 096 modules), et c'est ce que la
    generalisation des declarations doit faire disparaitre."""
    changes = _changed(ref)
    if changes is None:
        return perimetre, "ref `%s` inconnue de git -- TOUT rejoue" % ref
    if not changes:
        return [], "aucun fichier change entre %s et HEAD" % ref

    emp = _footprints()
    if not emp:
        return perimetre, "AUCUNE empreinte mesuree (`--measure`) -- TOUT rejoue"

    # INVALIDATION PAR ENTREE (#486-r15), et non plus par un `_commit` GLOBAL. Le sha global etait
    # ecrit dans le worktree d'un agent, donc sur une branche que le squash-merge remplace puis
    # supprime : il naissait MORT, et l'empreinte entiere devenait inverifiable d'un coup. La
    # fraicheur se lit desormais entree par entree, sur le CONTENU -- rien ne depend d'une ref git.
    if emp.get("_format") != FORMAT_EMPREINTE:
        return perimetre, ("empreinte de format %s (attendu %d) -- illisible sans risque, "
                           "TOUT rejoue" % (emp.get("_format"), FORMAT_EMPREINTE))

    racine = repo_root()
    mods = _modules_du_graphe(racine)

    # Les GLOBALES ne sont attribuables a personne -> tout changement les touchant impacte TOUT.
    # `.pyc` exclus : bytecode non versionne, jamais dans un diff.
    #
    # ATTENTION -- AUCUN autre retrait ici (#464-r2). Filtrer les modules du domaine a la LECTURE
    # a ete essaye puis ECARTE : rien ne distingue, dans une empreinte deja ecrite, la lecture
    # d'IMPORT (couverte par le graphe) de la lecture APPLICATIVE d'un `.py` par un
    # conftest-balayage (qui n'est couverte par rien). Le regime est garanti a l'ECRITURE, ou
    # l'information existe encore. Une empreinte ANCIENNE, mesuree avant ce correctif, garde donc
    # ses `.py` : elle SUR-selectionne -- le sens sur, et elle se regenere.
    globales = {g for g in emp.get("_globales", ()) if not g.endswith(".pyc")}
    dirs_glob = {g.rsplit("/", 1)[0] for g in globales if "/" in g}
    hors_py = [c for c in changes if c not in mods]
    for c in hors_py:
        d = c.rsplit("/", 1)[0] if "/" in c else ""
        if c in globales or d in dirs_glob:
            return perimetre, "changement dans une lecture GLOBALE (%s) -- TOUT rejoue" % c

    # Un fichier hors-.py impacte les tests dont l'empreinte lit son REPERTOIRE (granularite
    # repertoire : un test qui lit `docs/rl/x.md` doit rejouer si `docs/rl/y.md` change).
    # `par_test[rel]["dirs"]` stocke des REPERTOIRES (cf. `_dossiers` a l'ecriture).
    par_test = emp.get("par_test", {})
    dirs_par_test = {}
    for t, entree in par_test.items():
        lus = (entree.get("dirs") or ()) if isinstance(entree, dict) else ()
        dirs_par_test[t] = {x.rsplit("/", 1)[0] if "." in x.rsplit("/", 1)[-1] else x
                            for x in lus} | set(lus)

    dirs_changes = {c.rsplit("/", 1)[0] for c in hors_py if "/" in c} | set(hors_py)

    # NORMALISATION : `perimetre` et les cles de `par_test` sont relatifs a `scripts/python`
    # (nodeid pytest), `changes`/`touches`/`mods` sont relatifs au DEPOT. Comparer les deux formes
    # sans les ramener l'une a l'autre ne matcherait JAMAIS -- selection vide, donc faux vert.
    prefixe = "scripts/python/"
    changes_s = set(changes)

    # ---------------------------------------------------------------- MOITIE DECLAREE
    declares, _ecartes = declencheurs_du_perimetre(perimetre, racine)
    retenus = []
    causes = {"declare": 0, "diff": 0, "graphe": 0, "jamais mesure": 0,
              "empreinte perimee": 0, "hors .py": 0}
    a_mesurer = []
    for rel in perimetre:
        globs = declares.get(rel)
        if globs is None:
            a_mesurer.append(rel)
            continue
        if any(declencheur_cliquet.couvre(globs, c) for c in changes):
            retenus.append(rel)
            causes["declare"] += 1

    # ---------------------------------------------------------------- MOITIE MESUREE
    # PARESSEUX : le graphe (32,7 s d'`ast.parse`) n'est calcule que s'il reste un fichier a
    # decider. C'est ce que la generalisation des declarations fait disparaitre.
    if a_mesurer:
        inverse, incertains = _import_graph(mods)
        # Cloture arriere du graphe d'imports sur les .py changes.
        touches, pile = set(), [c for c in changes if c in mods]
        while pile:
            x = pile.pop()
            if x in touches:
                continue
            touches.add(x)
            pile.extend(inverse.get(x, ()))
        for rel in a_mesurer:
            abs_rel = prefixe + rel
            if abs_rel in changes_s:
                retenus.append(rel)
                causes["diff"] += 1
                continue
            if abs_rel in touches or abs_rel in incertains:
                retenus.append(rel)
                causes["graphe"] += 1
                continue
            entree = par_test.get(rel)
            if not isinstance(entree, dict):
                # TRI-ETAT : JAMAIS MESURE n'est PAS << mesure et vide >>. Avant #486-r15 les deux
                # se confondaient dans une absence, lue << aucune dependance hors-.py >> -- une
                # AFFIRMATION qui n'a jamais ete gagnee, puisqu'elle ne vaut que si le test a
                # tourne au moins une fois sous le hook d'audit. Mesure sur `master` le
                # 2026-08-07 : 88 entrees pour 220 fichiers, donc 132 fichiers passaient par cette
                # affirmation-la. Une entree est desormais ecrite pour CHAQUE fichier joue, `dirs`
                # VIDE compris -- une absence veut donc dire << pas de mesure >>, et cela rejoue.
                retenus.append(rel)
                causes["jamais mesure"] += 1
                continue
            if dirs_par_test[rel] & dirs_changes:
                retenus.append(rel)
                causes["hors .py"] += 1

    # L'ordre du perimetre est CONSERVE : la partition en shards est deterministe, et deux shards
    # d'un meme run doivent voir exactement la meme liste.
    rang = {rel: i for i, rel in enumerate(perimetre)}
    retenus.sort(key=lambda r: rang[r])
    raison = ("%d/%d fichier(s) impactes par %d changement(s) depuis %s "
              "[%d declare(s), %d mesure(s) ; %s]"
              % (len(retenus), len(perimetre), len(changes), ref, len(declares), len(a_mesurer),
                 ", ".join("%s %d" % (k, v) for k, v in causes.items() if v) or "aucun"))
    return retenus, raison


def main(argv=None) -> int:
    """Point d'entree. TROIS issues, jamais deux (#471) : 0 = mesure VERTE, 1 = mesure ROUGE,
    `EX_NON_MESURE` = RIEN n'a pu etre mesure (montage). Le tri est porte par `_run`, ce corps-ci
    n'est que la TRADUCTION d'un echec de montage en code de sortie."""
    try:
        return _run(argv)
    except MontageImpossible as exc:
        # ATTRAPE ETROITE, et c'est le point : seuls les sites de MONTAGE levent ce type (cf.
        # `_git`). Un `except Exception` ici avalerait un bug du probe lui-meme et le ferait
        # passer pour une indisponibilite -- l'echappatoire exacte que ce tri-etat doit eviter.
        print("[457] MONTAGE EN ECHEC : %s" % exc)
        print("[457] RIEN n'a ete mesure, RIEN n'a ete ecrit. Ce n'est PAS un verdict sur le")
        print("[457] depot -- ni un rouge de gisement, ni un vert.")
        print("[457] rc=%d" % EX_NON_MESURE)
        return EX_NON_MESURE


def _run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default=None,
                    help="Ne joue que les fichiers IMPACTES par le diff <ref>..HEAD (empreinte "
                         "mesuree + graphe d'imports). Tout doute rejoue TOUT, et le dit.")
    ap.add_argument("--depuis-ledger", action="store_true", dest="depuis_ledger",
                    help="Ne joue que les fichiers dont le VERT n'est plus atteste par le ledger "
                         "VERSIONNE (`scripts/ratchets-457-vert-offline.json`), compose avec "
                         "l'empreinte. Se cumule avec `--since` : l'intersection est jouee.")
    ap.add_argument("--shard", default="0/1",
                    help="k/N -- ne joue que le shard k parmi N (defaut 0/1 = tout).")
    ap.add_argument("--list", action="store_true",
                    help="Imprime les fichiers du shard et sort, sans rien jouer.")
    ap.add_argument("--measure", action="store_true",
                    help="Joue TOUT le perimetre d'un bloc en chronometrant chaque fichier, puis "
                         "reecrit les poids ET l'empreinte versionnee. Rejeu COMPLET (mesure du "
                         "2026-08-04 : 976,9 s / 1471 tests) -- de la maintenance, pas une etape "
                         "de PR. A rejouer quand le mur derive ou que l'empreinte vieillit.")
    ap.add_argument("--measure-missing", action="store_true", dest="measure_missing",
                    help="Ne chronometre que les fichiers SANS poids ou SANS entree d'empreinte, "
                         "et FUSIONNE dans les poids ET l'empreinte existants (cas nominal : "
                         "mediane 0-1 fichier offline neuf par PR). Depuis #486-r15 le tampon de "
                         "fraicheur vit dans l'ENTREE : cette passe rafraichit exactement ce "
                         "qu'elle a joue et ne pretend RIEN sur le reste.")
    args = ap.parse_args(argv)

    if args.measure and args.measure_missing:
        print("[457] --measure et --measure-missing s'excluent : le premier rejoue TOUT, le "
              "second complete.")
        return 2

    # ======================================================================================
    #  GARDE DE RETRAIT -- MIROIR EXACT de celle de `scripts/ratchets.ps1` (2026-08-05,
    #  d82ec527). Ce probe EST dans cette banque et en pese 67 % : sa de-obligation est la
    #  sienne. La banque REFUSE deja de se lancer sans `TACTICUS_ALLOW_RATCHETS` -- mais ce
    #  fichier appele DIRECTEMENT (`python probe_457_offline_tests_green.py ...`) contournait
    #  ce refus entierement. C'est par ce trou-la qu'on continuait de payer.
    #
    #  MESURE DU 2026-08-06 : un agent en vol l'a joue PAR REFLEXE, apres la de-obligation, sur
    #  une tranche qui ne le concernait pas. Le bandeau de l'en-tete ne l'a pas arrete -- il est
    #  lu APRES la decision de lancer, exactement le constat qui a impose la garde de la banque.
    #  Une consigne en PROSE n'arrete pas un comportement ; il faut un REFUS EXECUTABLE.
    #
    #  MEME ECHAPPATOIRE, pas une seconde : `TACTICUS_ALLOW_RATCHETS`. La banque l'exporte deja,
    #  donc ses huit shards continuent de tourner SANS RIEN CHANGER a `ratchets.ps1` (l'env est
    #  herite par le sous-processus). Inventer une variable propre aurait fragmente le contrat.
    #
    #  `--list` sort AVANT cette garde, comme `-List` cote banque : lister n'execute rien, et
    #  c'est le contrat de derivation que lit `probe_439`.
    #
    #  Pourquoi `EX_NON_MESURE` (99) et pas 1 : `1` se lit « un fichier de test est ROUGE »,
    #  soit un verdict sur le depot. Un refus n'en est pas un. C'est la meme regle que le `64`
    #  de la banque, et la table que lisent `probe_471` / `loop_status` la porte deja.
    # ======================================================================================
    if not args.list and not os.environ.get("TACTICUS_ALLOW_RATCHETS"):
        print("")
        print("  ===================================================================")
        print("   REFUS -- CE CLIQUET N EST PAS UNE ETAPE DE PR OBLIGATOIRE")
        print("  ===================================================================")
        print("")
        print("  Il n est prescrit par aucun fichier de .claude/ ni par CLAUDE.md, et la")
        print("  banque de fond ne tourne plus. Le lancer reste un choix DELIBERE, jamais")
        print("  un reflexe -- d ou ce refus, pose apres qu un agent l a joue par reflexe")
        print("  sur une tranche qui ne le concernait pas (2026-08-06).")
        print("")
        print("  CE QU IL COUTE, et c est la seule raison du refus :")
        print("    run COMPLET  ~1 425 s en serie, 297,8 s de mur a 8 shards ;")
        print("    meme une PR PUREMENT DOCUMENTAIRE selectionne 10 fichiers et")
        print("    paie 550,8 s en mono-shard (mesure du 2026-08-07).")
        print("")
        print("  CE QUE TU FAIS NORMALEMENT A LA PLACE :")
        print("    - les tests CIBLES de ta tranche, et tu les montres dans ton rapport ;")
        print("    - la relecture du diff de tout test EXISTANT que tu modifies.")
        print("")
        print("  SI TU LE JOUES, JOUE UNE SELECTION -- jamais le run complet :")
        print("    $env:TACTICUS_ALLOW_RATCHETS=1")
        print("    python probe_457_offline_tests_green.py --since origin/master")
        print("    python probe_457_offline_tests_green.py --depuis-ledger")
        print("    `--list` n execute rien et reste jouable sans la variable.")
        print("")
        print("[457] rc=%d -- RIEN n a ete joue, ce n est PAS un verdict sur le depot."
              % EX_NON_MESURE)
        return EX_NON_MESURE

    # GARDE DE CWD (#464), en tete : il couvre TOUT mode qui invoque pytest -- la mesure comme le
    # shard. `--list` n'invoque rien (l'enumeration passe par `git -C <racine>`, donc elle est
    # CWD-independante) et reste jouable de partout.
    # Sans lui, le shard lance hors `scripts/python` rendait `VERDICT: FAIL` sur un `rc=4` d'usage
    # (residu #457-r7), et `--measure` ecrivait du garbage PERSISTANT (#464).
    if not args.list:
        refus = _exiger_cwd()
        if refus:
            print(refus)
            return EX_NON_MESURE

    if args.measure or args.measure_missing:
        return _measure(candidate_files(), seulement_manquants=args.measure_missing)

    try:
        k_txt, n_txt = args.shard.split("/", 1)
        k, n = int(k_txt), int(n_txt)
    except ValueError:
        print("[457] --shard attend la forme k/N (ex. 0/3)")
        return 2
    if n < 1 or not (0 <= k < n):
        print("[457] --shard hors bornes : %s" % args.shard)
        return 2

    every = candidate_files()
    # LE PERIMETRE COMPLET, CAPTURE AVANT TOUTE SELECTION. `every` est reduit par `--since` et
    # `--depuis-ledger` ; passer ce reduit a `ledger.fusionner` EFFACERAIT les entrees de tous les
    # fichiers non selectionnes -- une passe de 10 fichiers detruirait 226 attestations valides.
    perimetre_complet = list(every)
    if args.since:
        # La selection s'applique AVANT le partitionnement : les shards se repartissent alors les
        # seuls fichiers impactes, donc N shards restent equilibres sur un perimetre reduit.
        every, raison = impacted_files(every, args.since)
        print("[457] --since %s : %s" % (args.since, raison))
        if not every:
            print("[457] aucun fichier impacte -- rien a jouer, VERDICT: PASS")
            return 0
    if args.depuis_ledger:
        # COMPOSITION empreinte x ledger (#486-r23). L'impact est INJECTE : `ledger_vert_offline`
        # n'importe rien d'ici. Le graphe d'imports est memoise (`_GRAPHE_CACHE`), donc N bases
        # distinctes ne le recalculent pas N fois.
        avant = len(every)
        garde = set(every)
        every, raisons, anomalies = ledger.a_rejouer(
            every, repo_root(),
            lambda sha: [r for r in impacted_files(candidate_files(), sha)[0] if r in garde])
        for a in anomalies:
            print("[457] ledger : %s" % a)
        causes = {}
        for motif in raisons.values():
            causes[motif.split(" (")[0].split(" --")[0]] = \
                causes.get(motif.split(" (")[0].split(" --")[0], 0) + 1
        print("[457] --depuis-ledger : %d/%d fichier(s) SANS vert atteste valable [%s]"
              % (len(every), avant,
                 ", ".join("%s %d" % (k, v) for k, v in sorted(causes.items(),
                                                               key=lambda kv: -kv[1])[:4])
                 or "aucun"))
        if not every:
            print("[457] tout le perimetre est ATTESTE VERT et valable -- rien a jouer, "
                  "VERDICT: PASS")
            return 0
    poids = _weights()
    if poids:
        mine = bins_of(every, n, poids)[k]
        mode = "cout mesure"
        charge = sum(poids.get(rel, 0.0) for rel in mine)
        # Un fichier de test offline NEUF n'a pas de poids : `bins_of` lui donne le MAXIMUM connu
        # (choix sur), donc il deplace les vrais lourds et degrade le mur -- sans qu'aucun poids ne
        # soit faux et sans le moindre risque de faux vert. Le DIRE ici, et nommer le remede a
        # quelques secondes ; c'est ce rapport qui remplace la passe complete de 976,9 s que la
        # garde d'equilibrage exigeait (#463).
        sans = [rel for rel in every if rel not in poids]
        if sans:
            print("[457] %d fichier(s) SANS poids (mur sous-optimal, verdict INCHANGE) : %s"
                  % (len(sans), ", ".join(sans[:3])))
            print("[457] les mesurer : cd scripts/python ; python %s --measure-missing"
                  % Path(__file__).name)
    else:
        # Repli : aucun poids disponible (checkout partiel, fichier supprime). Le cliquet reste
        # CORRECT -- il est seulement moins bien equilibre. Le dire, plutot que le taire.
        mine = [rel for rel in every if shard_of(rel, n) == k]
        mode = "REPLI md5 (poids absents -> mur sous-optimal)"
        charge = 0.0
    print("[457] %d fichier(s) de test non-`_live.py` ; shard %d/%d -> %d fichier(s) [%s%s]"
          % (len(every), k, n, len(mine), mode,
             ("", " ~%.0f s" % charge)[bool(charge)]))

    if args.list:
        for rel in mine:
            print("   ", rel)
        return 0

    if not mine and args.since:
        # SOUS `--since` un shard vide est LEGITIME : la selection a reduit le perimetre en dessous
        # du nombre de shards (mesure : un diff docs-only retient 4 fichiers pour 8 shards). Le
        # garde anti-effondrement reste ARME pour le cas normal ci-dessous -- le desarmer pour tout
        # le monde rouvrirait exactement le trou que la section 3 de la case-doc a ferme.
        print("[457] shard vide SOUS SELECTION (%d fichier(s) retenus pour %d shards) -- rien a "
              "jouer ici, ce n'est PAS un effondrement de perimetre" % (len(every), n))
        return 0

    if not mine:
        # Un shard vide n'est pas un succes : c'est le signe que le perimetre s'est effondre
        # (glob devenu faux, `git ls-files` muet). Le dire, plutot que rendre un vert.
        print("[457] FAIL shard VIDE -- le perimetre ne designe aucun fichier")
        return 1

    plugin = _DeselectLiveItems()
    bilan = _BilanParFichier()
    horloge = _TimePerFile()
    started = time.time()
    # `-p no:cacheprovider` : aucune ecriture sous `scripts/python/` (#455 -- la banque enumere
    # cet arbre en parallele). `--import-mode=importlib` est deja dans `pytest.ini` ; on ne le
    # repete pas, pour que ce cliquet joue EXACTEMENT la configuration de production.
    rc = pytest.main(["-q", "-p", "no:cacheprovider", *mine],
                     plugins=[plugin, bilan, horloge])
    elapsed = time.time() - started
    # LE LEDGER S'ECRIT ICI, ET PAS DANS `_ecrire_mesure` : celui-ci n'est atteint que par
    # `--measure`, qui rejoue TOUT (976,9 s). Un ledger qui ne se remplirait qu'a la maintenance
    # serait vide en pratique -- c'est la passe ORDINAIRE qui prouve le vert, donc c'est elle qui
    # doit l'inscrire.
    _ecrire_ledger(perimetre_complet, mine, bilan, horloge, int(rc), n)

    print("[457] %d test(s) joue(s) en %.1f s -- pytest rc=%d" % (plugin.kept, elapsed, int(rc)))
    if plugin.dropped_items:
        print("[457] %d item(s) DESELECTIONNE(S) (fixture live dans un fichier non-`_live.py`) :"
              % plugin.dropped_items)
        for path in sorted(plugin.dropped_files):
            try:
                shown = str(Path(path).relative_to(_PYDIR))
            except ValueError:
                shown = path
            print("    ", shown.replace("\\", "/"))
        print("[457] (rapporte, non bloquant : ce cliquet garde le VERT des offline, pas le nommage)")

    # #457-r7 : un rc d'USAGE / d'interruption ne dit RIEN sur le depot. Le traduire en
    # `VERDICT: FAIL` faisait lire << un test offline est rouge >> la ou RIEN n'avait tourne. Le
    # garde de CWD ci-dessus en couvre la cause de loin la plus frequente ; ceci est le filet
    # (fichier disparu entre `git ls-files` et l'execution, `-x` interrompu, erreur interne).
    # `rc=5` (aucun test collecte) reste un ROUGE : le shard a des fichiers, n'en collecter aucun
    # est anormal -- c'est le gisement de `probe_455` r3.
    if int(rc) in (2, 3, 4):
        print("[457] pytest rc=%d -- erreur d'USAGE ou interruption, AUCUN verdict sur le depot."
              % int(rc))
        print("[457] rc=%d : ne PAS le lire comme un rouge de gisement (ni comme un vert)."
              % EX_NON_MESURE)
        return EX_NON_MESURE
    if int(rc) != 0:
        print("[457] VERDICT: FAIL -- au moins un test offline est ROUGE (pytest rc=%d)" % int(rc))
        return 1
    print("[457] VERDICT: PASS -- tous les tests offline du shard sont verts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
