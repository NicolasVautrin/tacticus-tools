#!/usr/bin/env python
"""Probe #468 -- un NUMERO de tache ou de residu ATTRIBUE DEUX FOIS.

POURQUOI CE CLIQUET EXISTE
--------------------------
Rien n'attribue les numeros de ce depot. Ils sont pris au vol par qui en a besoin -- un agent
qui ouvre un residu, un rapport qui en nomme un, l'orchestrateur qui dispatche -- sans registre
ni verification. Une collision ne se voit qu'A L'OEIL au merge, et seulement si quelqu'un la
remarque. Or toute la tracabilite en depend : `docs/rl/case-<n>-*.md`,
`scripts/python/probe_<n>_*.py`, `scripts/python/tests/**/test_<n>_*.py`, les lignes de
`docs/rl/backlog.md`, et les messages de commit (`git log --grep`).

DEUX occurrences INDEPENDANTES le 2026-08-04, a quelques heures d'ecart :
  * `#465` -- la tache << ledger probe_462 >> (PR #560) et la tache << etat de boucle >> (PR #562)
    ont pris le meme numero, avec DEUX `#465-r1` differents a neuf lignes d'ecart dans
    `backlog.md`. Renumerotation complete du second en `#467` : fichiers, residus, references
    internes, ET messages de commit.
  * `#448-r1-r1-r2` -- un residu de PERFORMANCE (ligne de backlog) et le << second bras
    d'`IsLikeFlying` >> (PR #571). Celle-la PRECEDAIT le dispatch. Renumerotee en
    `#448-r1-r1-r3` le 2026-08-04 ; la ligne de backlog porte encore la mention `ex-`.

Le cout est ASYMETRIQUE selon le moment ou on la trouve : avant livraison c'est un choix de nom ;
apres, c'est une REECRITURE D'HISTORIQUE. C'est ce qui justifie un garde MECANIQUE plutot qu'une
convention ecrite.

LE CRITERE : DEFINITION, JAMAIS MENTION
---------------------------------------
Un cliquet trop strict rougirait sur les renvois LEGITIMES, dont ce depot est plein -- une
case-doc qui CITE le residu d'une autre, une ligne de backlog qui pointe la case-doc voisine, un
message de commit qui reference un numero. Le critere porte donc sur la POSITION de l'occurrence,
pas sur sa presence :

  DEFINITION -- le numero est en position d'IDENTIFIANT D'ENTREE. Trois positions, et trois
  seulement :
    (a) PREMIERE CELLULE d'une ligne du tableau de `backlog.md`  -> `| #465-r1 | ... |`
    (b) TETE d'une puce de premier niveau de `backlog.md`        -> `- **#420-r1** -- ...`
    (c) PREFIXE d'un nom de fichier `docs/rl/case-<n>-*.md`

  MENTION -- tout le reste, et le cliquet ne la lit JAMAIS : un `#n` en milieu de phrase, dans
  une colonne << Point d'entree >>, dans une ligne de continuation de puce, dans une case-doc qui
  renvoie a une autre, dans un message de commit.

MESURE DE SEPARATION (etape 0b, rejouee a chaque run) : sur `docs/rl/**`, 6580 occurrences `#<n>`
pour 836 DEFINITIONS -- 12,7 %. Un critere par simple presence rougirait sur la quasi-totalite du
depot. (Chiffres a RE-DERIVER via `--report`, jamais a citer : ils bougent a chaque tranche.)

CE QUE LA CONFRONTATION AU DEPOT A CHANGE (mesures du 2026-08-04)
-----------------------------------------------------------------
Trois formes avaient ete relevees A L'OEIL. La mesure en REFUTE deux comme criteres bloquants :

  * << deux `case-<n>-*.md` pour un meme `<n>` >> -> **33 identifiants** concernes, dont `366r1`
    avec **26** fichiers. Ce sont des tranches d'une MEME tache livrees au fil de l'eau
    (`case-217-blackrage` / `-stormcaller` / `-thequickening` / `-phantom-action-routing`).
    Aucun critere textuel ne separe un multi-items d'une collision : les deux ont le meme numero
    et des sujets sans rapport. RENDU EN INVENTAIRE (`--report`), jamais bloquant.
  * meme reponse pour les artefacts de CODE : **73** ids portent >= 2 `probe_<n>_*.py` et **36**
    portent >= 2 `test_<n>_*.py` (le couple `_live` / `_offline` a lui seul).
  * << un `<n>` a la fois dans une ligne OUVERTE et dans une case-doc >> -> **8** identifiants en
    cohabitation (11 paires), dont **7 legitimes** (tache-parapluie qui livre ses items, dossier
    RE-OUVERT sur le meme sujet, ou dossier CLOS dont la ligne n'a pas ete barree).
    Quatre criteres derives ont ete essayes pour separer les legitimes du vrai positif -- << la
    ligne cite le fichier >>, << la ligne cite un prefixe `case-<n>` >>, << la colonne Modele
    porte un tag >>, << le titre H1 de la case-doc >> -- et les QUATRE echouent, la plupart en
    RATANT la vraie collision (`#420-r1` cite `case-420`, prefixe de sa propre case-doc).
    Cette forme est donc gardee par LEDGER (patron `probe_462`), pas par critere.

  Reste DECIDABLE sans jugement, et c'est l'etape 1 : **deux definitions OUVERTES du meme
  identifiant dans `backlog.md`**. Une tache = une ligne ; deux lignes ouvertes = deux taches
  sous un numero. Zero faux positif mesure. La restriction << ouvertes >> est ce qui ecarte
  `#27-r4` et `#437-r1`, ou une ligne BARREE (dossier clos) cohabite avec une ligne ouverte du
  MEME sujet -- une re-ouverture, pas deux dossiers.

CE QUE LE PROBE FAIT
--------------------
0a. AUTO-TEST des detecteurs sur des lignes SYNTHETIQUES, positives ET negatives jumelles. Un
    cliquet dont le detecteur a cesse de mordre rend VERT sur un depot fautif (#430 / #439).
0b. CONTRE-EPREUVE SUR PIECES : ventile toutes les occurrences `#<n>` de `docs/rl/**` en
    definitions / mentions et verifie les invariants de separation.
1.  DOUBLE OUVERTURE : deux definitions NON BARREES du meme identifiant dans `backlog.md`.
2.  COHABITATION ouvert-au-backlog x case-doc du meme identifiant, non ATTESTEE au ledger
    `scripts/ratchets-468-numeros-attestes.json`.

Les collisions CONNUES ET NON RESOLUES sont au ledger avec le statut `COLLISION-OUVERTE` : elles
sont RE-IMPRIMEES a chaque run (jamais silencieuses) sans faire rougir. Un cliquet fige sa ligne
de base et interdit de la depasser -- il ne renumerote pas le passe, ce qui serait une reecriture
d'historique et un arbitrage d'orchestrateur.

TRI-ETAT (contrat de banque, `scripts/ratchets-verdict.ps1`, #471) : `0` vert, `N` = N rouges de
gisement, `99` INDISPONIBLE quand le MONTAGE a echoue -- `docs/rl` introuvable, `OSError` sur le
backlog ou le ledger. Un `backlog.md` vide, un ledger au JSON invalide ou un corpus indigent sont
des FAITS SUR LE DEPOT, donc des ROUGES : c'est la frontiere a ne pas laisser glisser.

ATTRIBUER N'EST PAS DETECTER -- et le critere s'INVERSE (`--suggere`, #468-r4)
-----------------------------------------------------------------------------
Les etapes ci-dessus RATTRAPENT le geste fautif. `--suggere` le supprime : elle DONNE un
numero libre. Et son critere est l'exact oppose du leur.

  * DETECTER exige de separer definition et mention -- 87 % des occurrences sont des renvois
    legitimes, un critere par presence rougirait partout et serait desarme le jour meme.
  * ATTRIBUER n'en a pas besoin, et ne doit surtout pas s'en servir : un numero seulement
    MENTIONNE est deja PRIS. Le critere est l'UNION de toutes les positions.

C'est ce qui rend `--suggere` robuste aux trous CONNUS du detecteur (#468-r1/r2/r3, et la
puce de residu d'une case-doc, qui n'est pas une position de definition) : elle n'a pas
besoin de savoir ce qu'est une definition pour eviter un numero deja employe.

LA MONOTONIE VAUT DANS LES DEUX MODES -- elle ne valait que dans un (#468-r11)
-----------------------------------------------------------------------------
Le mode RACINE refuse de recycler un trou sous la borne (<< un trou peut etre reserve par une
PR en vol >>) ; le mode RESIDU, lui, s'arretait au PREMIER trou et le proposait. Le motif
s'applique pourtant mot pour mot aux deux, et le docstring de `suggerer` affirmait deja la
monotonie pour la fonction ENTIERE : c'etait une contradiction interne, pas un arbitrage.

MESURE de l'asymetrie (2026-08-05) : `--suggere 477` rendait `#477-r14` alors que `#477-r15`,
`-r16` et `-r17` EXISTENT -- deux case-docs, trois probes, un test, des messages de commit,
une ref non fusionnee et cinq worktrees. Le corpus les VOYAIT tous (verifie dans `employes()`,
pas deduit de la sortie) : le defaut etait dans la RESTITUTION, qui n'imprimait que le PREFIXE
CONTIGU, donc un compte filtre qui ne disait pas ce qu'il filtrait. Gisement : **11 parents sur
218** proposaient un trou avec des residus superieurs (#66, #95, #229, #437-r1, #462-r4d...).

Les deux modes sont donc alignes : on part du PLUS GRAND pris + 1, et les trous sont LISTES,
jamais proposes.

MESURE qui l'impose (2026-08-04) : 13 racines pures < 500 -- dont `#28`, `#269`, `#297`,
`#300`, `#307` -- n'existent QUE dans les messages de commit. Le corpus documentaire les
donne pour des trous LIBRES ; `git log --grep` prouve le contraire. Un balayage qui omet
l'historique fabrique donc exactement la collision qu'il pretend eviter, d'ou :

  UNE MESURE INCOMPLETE NE REND JAMAIS DE NUMERO. Si `git log` est muet, `--suggere` sort en
  INDISPONIBLE (99) et ne suggere RIEN -- suggerer sur un corpus ampute serait pire que se
  taire. Meme frontiere que le tri-etat ci-dessous : ce n'est pas une echappatoire, c'est un
  changement d'ACCUSE.

ET LE CORPUS N'EST PAS L'ARBRE COURANT -- l'angle mort des agents EN VOL (#468-r10)
------------------------------------------------------------------------------------
`--suggere` rendait `PASS` dans le SEUL regime ou nos collisions se produisent. Son corpus
etait ce qui est ECRIT ET FUSIONNE, alors qu'une allocation se fait au DEBUT d'une tranche,
avant que le moindre artefact existe. MESURE (2026-08-05) : deux agents dispatches ensemble
ont pris `#479` du meme `--suggere` -- collision DOUBLE (la racine ET le residu `r1`), pour
deux sujets sans rapport. Le cliquet rendait `PASS` pendant tout ce temps, et il avait raison
au regard de son corpus.

L'aveuglement se VENTILE en trois niveaux, et deux se ferment :

  N1 -- L'HISTORIQUE DE `HEAD` SEULEMENT. `git log` sans `--all` ne voit rien hors de la
        lignee du worktree appelant : un worktree d'agent est FIGE a son commit de lancement,
        donc aveugle a `master` qui avance et aux branches des voisins. FERME par
        `_identifiants_des_refs_hors_head()` (`git log --all --not HEAD`). Cout mesure
        +0,06 s ; il a rendu `#448-r3`, que `--suggere 448` proposait alors qu'un dossier
        le portait deja.
  N2 -- L'ARBRE DE TRAVAIL DU WORKTREE COURANT SEULEMENT. `git grep --untracked` ne lit que
        SON checkout : un `case-<n>-*.md` ecrit chez le voisin est invisible. FERME par
        `_identifiants_des_worktrees()` -- un glob des NOMS (jamais du contenu, jamais une
        commande git DANS l'arbre d'autrui : `git status` rafraichit l'index et ecrirait chez
        le voisin). Cout mesure +0,39 s pour 13 worktrees ; il a rendu `#425-r3`, meme
        symptome.
  N3 -- CE QUI N'EST ECRIT NULLE PART. Un agent qui vient de recevoir un numero et n'a rien
        ecrit est invisible de TOUTE lecture de l'arbre. **Irreductible** sans reservation, et
        reserver exigerait commit+push, ce qui serialise l'allocation entre agents paralleles.
        C'est pourquoi `--suggere` IMPRIME SA PORTEE (`_imprimer_portee`) : un allocateur
        incapable de voir les reservations concurrentes doit le NOMMER, exactement comme
        `loop_status` distingue `null` de `0`.

DEUX EXTENSIONS MESUREES PUIS REFUSEES -- le chiffre decide, pas l'intuition :

  * BALAYER LES 94 BRANCHES NON FUSIONNEES (diff + log par branche, ~30 s) : **5** identifiants
    apportes, dont **une seule racine, `#658`** -- et c'est un numero de PULL REQUEST, pas de
    tache (`#468-r8` : les deux espaces se remplissent en parallele). Effet sur le numero rendu :
    **AUCUN**. Les branches survivent au squash-merge (79 pour 1 PR ouverte, `#467-r6`), donc
    leur contenu est deja dans le corpus. `--all` en capte deja les messages pour 0,06 s.
  * `git log --all --diff-filter=A --name-only` (couvrirait les branches SANS worktree) :
    **25** identifiants pour **+2,64 s** (x1,7 le temps total), dont **24 de bruit pur** --
    `#arithmetic`, `#dispatcher`, `#selectors`... des noms de modules Python que `couper_nom`
    lit comme des identifiants. Rapport signal/bruit 1/25.

UNE TROISIEME SOURCE, MESUREE PUIS RETENUE : LE CORPS DES PULL REQUESTS (#468-r11)
---------------------------------------------------------------------------------
`#468-r10` nommait la parade `gh` sans la construire. Elle est ici, et le chiffre la justifie --
le meme protocole qui a REFUSE les deux extensions ci-dessus (0 changement de numero) la RETIENT
(2 changements de numero sur l'arbre vivant).

Le corps d'une PR N'EST PAS DANS L'ARBRE. Le squash-merge de GitHub ne le recopie pas dans le
message de commit : `git log --all --grep "479-r2"` rend **0**, `git grep "479-?r2"` rend **0**,
et pourtant la PR #663 ecrit noir sur blanc << son verdict ne pese pas `manquants` => #479-r2 >>.
`--suggere 479` rendait donc `#479-r2` -- un numero DEJA OUVERT, invisible de toute lecture de
l'arbre. C'est le meme symptome que `#425-r3` et `#448-r3` au niveau N1/N2, sur une quatrieme
source.

MESURE (2026-08-05, 670 PR, depot reel), identifiants ABSENTS du corpus des quatre autres
sources et apportes par le TITRE + le CORPS des PR :

  | PR lues        | inedits | dont residus | CHANGENT le numero rendu       | cout   |
  |----------------|---------|--------------|--------------------------------|--------|
  | 25             |    4    |      1       | 1 (`--suggere 479` r2 -> r3)   | ~1,5 s |
  | 200 (RETENU)   |   20    |      2       | 2 (+ `--suggere 449-r2-r5`)    | ~3,9 s |
  | 670 (toutes)   |   25    |      2       | 2 -- AUCUN de plus             | ~7,3 s |

Le gisement se TARIT : les 470 PR les plus anciennes n'apportent aucun changement de numero
(leur contenu a fini dans l'arbre). `GH_LIMITE_PR = 200` capture donc 100 % du signal mesure
pour 53 % du cout de la lecture integrale.

DEUX CHOIX DE FORME, tous deux dictes par la mesure :

  * ON NE LIT PAS LE NOM DE BRANCHE, et le chiffre qui le justifie a du etre RE-MESURE : la
    premiere mesure (<< 24 identifiants de bruit >>) prefixait un `#` au nom de branche, ce que
    le code ne ferait jamais -- un mutant l'a montre en RESTANT VERT. Formes reelles, sur 40 PR :
    `RE_TOKEN_LARGE` tel quel rend **0** identifiant (il exige un `#`), et `couper_nom` -- la
    voie que ce fichier emploie deja pour les NOMS de fichiers -- rend **2** identifiants,
    `worktree` et `agent`, soit **0** signal pour du bruit pur. Meme famille que le
    `--name-only` refuse ci-dessus, en plus petit.
  * ON GARDE LES NUMEROS DE PR, et c'est le cote SUR. Sur 200 PR, 18 des 20 inedits sont des
    numeros de PULL REQUEST cites en prose (`#631`, `#655`...) que rien ne distingue d'une tache
    (`#468-r8`). Les prendre fait SAUTER un entier le jour ou l'espace des taches (borne 480)
    atteindra celui des PR (~670) ; les ecarter risquerait de rater une vraie racine. Sauter
    coute un entier, reprendre coute une reecriture d'historique.

CE CAPTEUR NE LEVE PAS `Indisponible`, comme `git worktree list` et pour la meme raison : c'est
un capteur d'APPOINT. Sans lui, `--suggere` retombe sur les quatre sources d'avant, degradees
mais pas fausses ; le faire lever rendrait l'outil inutilisable hors ligne ou sans `gh` -- donc
ferait revenir au geste que ce cliquet supprime (choisir son numero au vol). La contrepartie est
stricte et c'est `_imprimer_portee` qui la tient : muet se DIT (<< NON MESUREES >>), avec le
STDERR de `gh` en clair (un `rc` ne nomme rien -- `rc=1` couvre a lui seul le token invalide, le
depot inconnu et l'erreur d'usage, cf. #467-r6), et JAMAIS rabattu sur << 0 PR >>. Aucun repli
sur cache : un cache disant << 0 PR >> ne prouverait rien.

CINQ SOURCES NE SUFFISENT PAS : ON N'OBSERVE PLUS, ON ALLOUE (#468-r14)
-----------------------------------------------------------------------
Les cinq elargissements ci-dessus repondent tous a la meme question -- << ou ce numero est-il
deja ECRIT ? >>. Aucun ne peut repondre a celle qui produit nos collisions : << qui vient de le
PRENDRE ? >>. Un agent alloue au DEBUT de sa tranche et n'ecrit qu'a la fin, des heures plus
tard ; entre les deux, il est invisible de toute lecture, par construction. Le corpus etait donc
epuise comme piste -- mesure : les branches non fusionnees apportent 0 changement de numero, le
corps des PR en apporte 2, et il ne reste rien a lire.

MESURE DU SYMPTOME (2026-08-11, trois jours) : SEPT collisions, dont quatre vues de visu -- un
agent annonce `#907`, un autre le prend PENDANT qu'il travaille (renumerotation manuelle en
`#911`) ; `--suggere` rend `#909` deja pris ; `#479` collisionne DOUBLE (racine ET `-r1`) ;
`#420-r1` QUADRUPLE. Toutes dans le meme regime : deux allocations concurrentes, aucune ecriture
entre les deux.

LE REMEDE EST UN CHANGEMENT DE NATURE, PAS UN SIXIEME CAPTEUR. `--suggere` RESERVE le numero
qu'elle rend, et la reservation EST l'allocation :

    os.open(<dossier>/<cle>.json, O_CREAT | O_EXCL)

`O_CREAT|O_EXCL` (CREATE_NEW cote Win32) est atomique : pour une cle donnee, EXACTEMENT UN
processus peut reussir. Il n'y a aucune fenetre entre << je constate que c'est libre >> et
<< je le prends >>, parce que c'est le MEME appel systeme. Deux `--suggere` simultanes ne
peuvent donc pas rendre le meme numero -- ce n'est pas improbable, c'est impossible ; celui qui
perd la course voit son `FileExistsError`, incremente et rejoue. Le refus est EXECUTABLE, pas
redige.

OU VIT LA RESERVATION, ET POURQUOI LA -- trois contraintes, un seul emplacement qui les tienne :
  (1) VISIBLE DE TOUS. Jusqu'a 6 agents tournent en parallele, chacun dans SON worktree, sur la
      meme machine. Mesure du 2026-08-11 : `git rev-parse --git-common-dir` rend le MEME chemin
      absolu (`<principal>/.git`) depuis l'arbre principal ET depuis chacun des 32 worktrees --
      c'est la definition d'un worktree lie, pas une coincidence d'installation.
  (2) SURVIT A LA DISPARITION D'UN WORKTREE. Un worktree PROPRE est auto-supprime des que son
      agent rend la main ; `.git/` du principal, lui, n'est touche ni par `git worktree remove`,
      ni par `git clean` (qui ne descend jamais dans le repertoire git).
  (3) HORS DE TOUT ARBRE DE TRAVAIL. Une reservation versionnee exigerait commit+push (donc de
      serialiser l'allocation, donc le reseau) et ferait de `backlog.md` -- deja le fichier le
      plus partage du depot, 36 des 40 dernieres PR -- le lieu d'un conflit par allocation.
      Sous `.git/`, elle n'apparait dans aucun `git status` et ne peut entrer dans aucune PR.

TROIS FORMES REFUSEES, et le motif de chacune :
  * VERROU GLOBAL + registre JSON (lire, decider, ecrire, deverrouiller) : ajoute un mode de
    panne que la creation exclusive n'a pas -- le verrou ORPHELIN, qu'un process tue laisse
    derriere lui et qu'il faut alors expirer par un DELAI, c'est-a-dire par un seuil qui se
    degrade en silence. Ici il n'y a rien a relacher : l'artefact EST le resultat.
  * COMMIT+PUSH d'une ligne de reservation : serialise l'allocation entre agents et depend du
    reseau ; c'est la parade que #468-r10 avait deja nommee puis ecartee pour cette raison.
  * UN SERVICE (le host, un daemon d'allocation) : une piece mobile de plus, qui peut etre
    eteinte -- et un allocateur indisponible fait revenir au geste qu'on supprime.

CE QUE LA RESERVATION NE COUVRE PAS, et c'est dit a chaque appel (`_imprimer_portee`) : un
numero choisi SANS passer par l'outil ; un autre clone du depot ou une autre machine (l'espace
de noms est per-depot, comme le `.git` qui le porte) ; et un numero reserve puis jamais livre --
un entier brule, exactement l'asymetrie que la monotonie assume deja (sauter coute un entier,
reprendre coute une reecriture d'historique). Il n'y a donc PAS de liberation : `--liberer`
rouvrirait une course entre le releaseur et un demandeur, pour economiser un entier.

ASCII only (console Windows cp1252).
Usage:
    python probe_468_collision_numeros.py [-v]
    python probe_468_collision_numeros.py --report
    python probe_468_collision_numeros.py --self-test
    python probe_468_collision_numeros.py --gate origin/master   # n'accuse QUE cette branche
    python probe_468_collision_numeros.py --attester "<ident>|<fichier>=<raison>"
    python probe_468_collision_numeros.py --suggere            # une RACINE libre, RESERVEE
    python probe_468_collision_numeros.py --suggere 420        # un RESIDU libre sous #420
    python probe_468_collision_numeros.py --suggere --pour "<sujet>"   # etiquette la reservation
    python probe_468_collision_numeros.py --reservations       # ce qui est alloue, par qui
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
DOCS_RL = REPO / "docs" / "rl"
BACKLOG = DOCS_RL / "backlog.md"
LEDGER = REPO / "scripts" / "ratchets-468-numeros-attestes.json"

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: ⚠ CE DECLENCHEUR NE VAUT QUE POUR L'ARGV QUE LA BANQUE JOUE (aucun mode). Il a ete MESURE
#: fonction par fonction, pas suppose : `_lignes_backlog` -> `docs/rl/backlog.md` ;
#: `_fichiers_case_docs` -> `docs/rl/case-*.md` (les NOMS) ; `ventiler_occurrences` ->
#: `docs/rl/**/*.md` ; `lire_ledger` -> le ledger ; `self_test` -> les echantillons de CE
#: fichier. `_artefacts_de_code` (qui, lui, rglob `scripts/python`) n'est atteint QUE par
#: `--report`, et `employes` / `_identifiants_des_*` (git, worktrees, `gh`) QUE par `--suggere`.
#: L'IRREDUCTIBILITE de l'unicite -- << n'importe quel numero peut heurter n'importe quel autre >>
#: -- est vraie du mode ATTRIBUER (`--suggere`), dont le corpus est l'UNION de toutes les
#: positions ; le mode DETECTER, lui, ne lit que des DEFINITIONS, et les trois positions de
#: definition vivent toutes dans `docs/rl`.
#: MESURE (audit hook sur `open`, 2026-08-07) : l'argv de banque ouvre **664** fichiers du
#: depot, et **664 sur 664** sont soit un `.md` de `docs/rl` (662), soit le ledger, soit cette
#: source. Le perimetre ci-dessous n'est donc PAS une prudence : il est mesure, et il borne.
#: `toujours: True` est neanmoins ce qui est DECLARE, et c'est un ARBITRAGE, pas un defaut
#: d'analyse : l'unicite d'un numero n'a pas de voisinage -- un `#<n>` peut etre pris par un
#: `probe_<n>_*.py`, un `test_<n>_*.py` ou un message de commit que ce mode ne lit PAS (seuls
#: `--report` et `--suggere` les voient). Borner sur `docs/rl` ferait donc coincider le
#: declencheur avec l'ANGLE MORT du detecteur, et le gain serait de 2,5 s.
DECLENCHEUR = {
    "chemins": ("docs/rl/*", "docs/rl/**", "scripts/ratchets-468-numeros-attestes.json"),
    "build": False,
    "toujours": True,
    "raison": "Mesure : les 664 lectures de l'argv de banque tiennent dans `docs/rl` + le "
              "ledger. Declare TOUJOURS quand meme -- l'unicite d'un numero n'a pas de "
              "voisinage, et les positions que ce mode ne lit pas (artefacts de code, messages "
              "de commit) sont precisement celles ou une collision naitrait sans toucher "
              "`docs/rl`. Le gain d'un bornage serait de 2,5 s.",
}

#: << RIEN N'A ETE MESURE >> -- contrat de banque, `scripts/ratchets-verdict.ps1` (#471).
#: BLOQUANT comme un rouge, mais il change l'ACCUSE : le harnais, pas le contenu du depot.
EX_INDISPONIBLE = 99


class Indisponible(Exception):
    """Le MONTAGE a echoue : un depot PARFAIT aurait subi le meme echec sur cette machine.

    C'est le test operationnel de `ratchets-verdict.ps1`, et la frontiere est etroite :
      * `docs/rl` introuvable (CWD faux impose par l'appelant, `--racine` errone) -> INDISPONIBLE ;
      * une `OSError` en lisant `backlog.md` ou le ledger (verrou, droits)         -> INDISPONIBLE ;
      * `backlog.md` ABSENT ou VIDE alors que `docs/rl` existe                     -> ROUGE ;
      * un ledger au JSON INVALIDE                                                 -> ROUGE ;
      * un corpus indigent                                                         -> ROUGE.
    Les trois derniers sont des FAITS SUR LE CONTENU du depot -- meme frontiere que
    << `git ls-files` rc=0 et liste VIDE -> ROUGE >>. Sans elle, << je n'ai rien trouve >>
    deviendrait << je n'ai pas pu regarder >>, et tout finirait INDISPONIBLE."""


def viser(racine: Path) -> None:
    """Pointe le probe sur un AUTRE arbre (`--racine`).

    C'est ce qui rend la contre-epreuve BOUT-EN-BOUT possible : fabriquer un depot jetable
    portant les collisions et verifier que le probe REND rc != 0. Un detecteur qu'on ne teste
    qu'en appelant ses fonctions pures laisse le CABLAGE (lecture, ledger, code de sortie) hors
    garde -- et c'est par la que `probe_181` rendait `0` inconditionnellement (#430)."""
    global REPO, DOCS_RL, BACKLOG, LEDGER
    REPO = racine.resolve()
    DOCS_RL = REPO / "docs" / "rl"
    BACKLOG = DOCS_RL / "backlog.md"
    LEDGER = REPO / "scripts" / "ratchets-468-numeros-attestes.json"

# ------------------------------------------------------------------------------------------
# La GRAMMAIRE d'un identifiant, DERIVEE des formes presentes dans le depot.
#
# Racine numerique (`465`, `1014`) ou alphanumerique (`r6`, `o10`, `n8b`, `49x`), suivie d'une
# chaine de suffixes de residu (`-r1`, `-tr14`, `-t6`, `-a`, `-b1`), la separation par tiret
# etant FACULTATIVE : le depot ecrit `#366-r1` et `#366r1` pour le MEME residu, et
# `case-443-r1c-*` a cote de `case-443r1a-*`. La normalisation retire donc `-` et `_`.
# ------------------------------------------------------------------------------------------
ID = r"[0-9]+[a-z]*(?:-?(?:r|tr|t)[0-9]+[a-z]?)*(?:-[a-z])?|[a-z]+[0-9]+[a-z0-9]*"

#: Un token de nom de fichier qui prolonge l'IDENTIFIANT au lieu d'ouvrir le SLUG.
#: `case-448-r1-r1-r2-second-bras-...` -> ident `448-r1-r1-r2`, slug `second-bras-...`.
#: Les tokens purement NUMERIQUES en sont exclus A DESSEIN : `case-229-1502-rites-of-morkai-*`
#: porte un id d'ABILITY (1502), pas un suffixe de residu -- et rien ne les distingue de
#: `case-302-2-*`, ou `2` EST un suffixe. Cote sur : on n'absorbe pas (residu #468-r1).
SUFFIXE_TOKEN = re.compile(r"^(?:r|tr|t)\d+[a-z]?\d*$|^[a-z]\d*$|^bis$")

#: EN POSITION DE DEFINITION, L'IDENTIFIANT SE LIT PAR SA POSITION, PAS PAR UNE GRAMMAIRE
#: (#468-r1). C'est le principe meme de ce cliquet (<< le critere porte sur la POSITION >>),
#: applique jusqu'au bout : dans une premiere cellule de tableau, ce n'est pas une grammaire qui
#: dit ou l'identifiant FINIT -- c'est le `|` fermant ; en tete de puce, c'est la ponctuation.
#:
#: ⚠ LE DEFAUT QUE CA CORRIGE N'EST PAS UN REPLIEMENT, C'EST UNE DISPARITION -- et c'est en quoi
#: l'enonce de #468-r1 (<< effet cote SUR : peut faire voir une cohabitation, jamais la
#: manquer >>) etait FAUX de ce cote. `ID` s'arrete au premier segment qu'il ne sait pas lire
#: (`-c1`, `-b-r1`, `-src`, `-1`), et comme les deux motifs exigent un `|` (resp. une fin de
#: token) JUSTE APRES, la ligne ENTIERE cessait de correspondre. MESURE le 2026-08-15 :
#: **72 lignes de tableau** de `backlog.md` n'etaient vues comme AUCUNE definition -- 7 % du
#: registre -- dont les familles `#462-r4b-...-b/-c-r<k>` (31), `#462-r4e-o-r<k>` (9),
#: `#366-r1-<mot>` (13), `#433-r4-r2-r1-r1-a/c-r<k>` (3), `#443-r2-b<k>` (2), et les
#: identifiants non numeriques `#o10-a/-c`, `#PAI-c/-k`, `#BL-*`, `#haze-ord`, `#254-bc*`.
#: L'etape 1 leur etait donc structurellement AVEUGLE : deux dossiers sous `#462-r4e-o-r2-r1`
#: n'auraient rien fait rougir.
#:
#: CE QUE CA NE RESOUT PAS, et c'est le NOYAU de #468-r1 : `normaliser` retire les tirets, donc
#: `#222-1` et un futur `#2221` restent indistinguables. Cette ambiguite-la est REELLE, elle est
#: dans la CONVENTION D'ECRITURE et pas dans le detecteur -- et `--suggere` la subit deja a
#: l'identique (`RE_TOKEN_LARGE` lit `222-1` puis normalise en `2221`). Le correctif ci-dessus
#: ALIGNE le detecteur sur l'attribueur ; il ne cree pas cette confusion, il cesse de la cacher.
ID_POSITION = r"[0-9a-zA-Z](?:[0-9a-zA-Z-]*[0-9a-zA-Z])?"

#: (a) PREMIERE cellule d'une ligne de tableau. Le `~~` de part et d'autre = entree BARREE.
RE_LIGNE_TABLEAU = re.compile(r"^\|\s*(~~)?\s*[`*]*\s*#(" + ID_POSITION + r")\s*[`*]*\s*(~~)?\s*\|")
#: (b) TETE d'une puce de premier niveau (`- `, `* `), gras et backticks tolerés.
#:     ⚠ ANCREE en debut de ligne SANS espace de tete : une puce INDENTEE est une continuation
#:     ou une sous-puce, jamais l'ouverture d'un dossier.
RE_TETE_DE_PUCE = re.compile(r"^[-*]\s+(?:~~)?\s*(?:\*\*)?\s*(?:~~)?\s*[`]?#(" + ID_POSITION + r")[`]?")
#: Toute occurrence, pour la ventilation de l'etape 0b.
RE_OCCURRENCE = re.compile(r"#(" + ID + r")\b")


def normaliser(ident: str) -> str:
    """`366-r1`, `366r1`, `366_r1` -> `366r1`. Le depot ecrit les trois."""
    return re.sub(r"[-_]", "", ident.lower())


def couper_nom(stem: str) -> tuple:
    """`case-448-r1-r1-r2-second-bras` -> ('448-r1-r1-r2', 'second-bras')."""
    toks = stem.split("-")
    if toks and toks[0] == "case":
        toks = toks[1:]
    if not toks:
        return "", ""
    ident = [toks[0]]
    i = 1
    while i < len(toks) and SUFFIXE_TOKEN.match(toks[i]):
        ident.append(toks[i])
        i += 1
    return "-".join(ident), "-".join(toks[i:])


# ------------------------------------------------------------------------------------------
# Extraction des DEFINITIONS
# ------------------------------------------------------------------------------------------

class Definition:
    """Une entree qui FAIT EXISTER un numero comme sujet."""

    __slots__ = ("ident", "cle", "source", "ou", "barre", "texte")

    def __init__(self, ident, source, ou, barre, texte=""):
        self.ident = ident
        self.cle = normaliser(ident)
        self.source = source          # 'tableau' | 'puce' | 'case-doc'
        self.ou = ou                  # 'backlog.md:342' | 'case-420-r1-....md'
        self.barre = barre
        self.texte = texte

    @property
    def ouverte(self) -> bool:
        return not self.barre

    def __repr__(self):
        return "#%s %s %s%s" % (self.ident, self.source, self.ou, "" if self.ouverte else " [barre]")


def definitions_du_backlog(lignes) -> list:
    """Les definitions portees par `backlog.md`, positions (a) et (b) SEULEMENT.

    Le BARRE se lit sur la portion de ligne QUI PRECEDE le numero, plus la fermeture de cellule :
    `~~#462~~` et `- ~~**#45x**~~` sont clos, alors qu'un `~~...~~` situe APRES le numero ne
    barre que le titre (`| #448-r1-r1-r1-r1-r1 | **...** |` reste ouvert)."""
    out = []
    for n, ligne in enumerate(lignes, 1):
        m = RE_LIGNE_TABLEAU.match(ligne)
        if m:
            barre = bool(m.group(1) or m.group(3))
            out.append(Definition(m.group(2), "tableau", "backlog.md:%d" % n, barre, ligne))
            continue
        m = RE_TETE_DE_PUCE.match(ligne)
        if m:
            avant = ligne[: ligne.index("#" + m.group(1))]
            out.append(Definition(m.group(1), "puce", "backlog.md:%d" % n, "~~" in avant, ligne))
    return out


def definitions_des_case_docs(noms) -> list:
    """Position (c) : le prefixe `case-<n>-` d'un nom de fichier. Une case-doc est le DOSSIER
    d'un numero -- son existence l'attribue, quel que soit son contenu."""
    out = []
    for nom in sorted(noms):
        ident, slug = couper_nom(Path(nom).stem)
        if ident:
            out.append(Definition(ident, "case-doc", nom, False, slug))
    return out


def _fichiers_case_docs() -> list:
    return sorted(p.name for p in DOCS_RL.glob("case-*.md"))


# ------------------------------------------------------------------------------------------
# La QUATRIEME position de definition DE FAIT : la puce de la section << Residus >> d'une
# case-doc (#468-r7). MESUREE, puis RENDUE EN INVENTAIRE -- pas en critere bloquant.
# ------------------------------------------------------------------------------------------
#
# CE QUI EST VRAI, ET QUI JUSTIFIAIT LE RESIDU : c'est bien une position de definition. 435 des
# 869 case-docs portent une section << Residus >> (520 sections), qui ouvrent **588** puces de
# tete `#<n>` -- **508** identifiants distincts, dont **143** qu'AUCUNE ligne de `backlog.md` ne
# definit et **118** qui n'ont meme pas de case-doc a leur nom. `case-467` ouvre `#472-r1/-r2/-r3`
# exactement la, et ces trois-la sont les << orphelins >> de la section 8 de la case-doc.
#
# CE QUI EST FAUX, ET QUE SEULE LA MESURE POUVAIT DIRE : le remede que le residu proposait --
# << un critere de SECTION, pas de puce >> -- NE SEPARE PAS. Applique tel quel, il rend **33**
# identifiants portes par une puce OUVERTE dans DEUX case-docs ou plus (41 avant le correctif de
# #468-r1 ci-dessus, qui a deja dissous huit ECRASEMENTS de cles). Une section << Residus >>
# RECAPITULE l'etat de sa famille : citer le residu du voisin y est la NORME.
#
# LE DISCRIMINANT QUI MARCHE, ET SA LIMITE. Une case-doc POSSEDE un identifiant quand sa propre
# cle en est un PREFIXE ; entre plusieurs pretendants, le plus LONG l'emporte (le dossier le plus
# specifique) ; et quand PERSONNE ne le possede, toutes ses puces definissent -- sans quoi le cas
# MOTIVANT (`case-467` ouvrant `#472-r1`, ou `467` n'est pas prefixe de `472r1`) serait perdu.
# Effet mesure : 501 puces ouvertes -> 465 definitions + 36 citations, et les doubles tombent de
# **33** a **6 fichiers-differents + 3 meme-fichier**.
#
# CES NEUF-LA ONT ETE LUS, UN PAR UN : **9 sur 9 sont LEGITIMES**. Six sont des RE-CITATIONS dans
# un dossier frere, et elles le DISENT (`<< reste OUVERT, cf. case-521r1 >>`, `<< inchange >>`,
# `<< (existant, non ouvert ici) >>`) ; trois sont le meme residu repris deux fois DANS UN MEME
# fichier, la seconde puce portant une mise a jour d'etat (`<< #419-r1-tr14-r5 -- FERME >>` face
# a `<< (releve d'ouverture) >>`).
#
# D'OU LE VERDICT, ET IL EST CELUI DE LA SECTION 3 : **0 collision sur 456 identifiants ouverts**,
# pour un taux de faux positifs mesure a **9/9**. Un critere qui crie au loup a chaque fois se
# fait desarmer dans la semaine -- c'est exactement le motif qui a fait REFUSER la forme
# << deux case-docs pour un meme `<n>` >>. Rendu en INVENTAIRE (`--report`), jamais bloquant.
# CE QUI LE RENDRAIT BLOQUANT : deux puces definissantes du meme identifiant dans DEUX case-docs
# dont AUCUNE ne le possede -- la seule forme ou << re-citation d'un dossier frere >> ne peut pas
# etre l'explication. Elle est a **0** aujourd'hui, sur une population de 10 : trop petite pour
# qu'on puisse en mesurer le taux de faux positifs, donc pas encore un critere.

#: Un titre markdown de niveau 2 a 6. Le niveau sert a FERMER la section : une section se termine
#: au titre suivant de niveau egal ou superieur, jamais a une sous-section.
RE_TITRE_MD = re.compile(r"^(#{2,6})\s+(.*)$")

#: Un titre qui ANNONCE des residus. Les deux graphies du depot (`## Residus`, `## 10. Resid...`,
#: `### Residus ouverts`), accentuees ou non.
RE_TITRE_RESIDUS = re.compile(r"r[eé]sidus?", re.IGNORECASE)


def sections_de_residus(lignes) -> list:
    """[(debut, fin)] -- les plages (indices 0-based, fin exclue) des sections << Residus >>."""
    plages, ouvert, niveau = [], None, 0
    for i, ligne in enumerate(lignes):
        m = RE_TITRE_MD.match(ligne)
        if not m:
            continue
        if ouvert is not None and len(m.group(1)) <= niveau:
            plages.append((ouvert, i))
            ouvert = None
        if ouvert is None and RE_TITRE_RESIDUS.search(m.group(2)):
            ouvert, niveau = i + 1, len(m.group(1))
    if ouvert is not None:
        plages.append((ouvert, len(lignes)))
    return plages


def puces_des_case_docs() -> tuple:
    """([Definition], [Definition]) -- (definitions, citations) des puces de section Residus.

    La repartition suit le discriminant du commentaire de bloc ci-dessus : proprietaire au plus
    long prefixe, et a defaut de proprietaire, toutes les puces definissent."""
    brut = {}
    for nom in _fichiers_case_docs():
        chemin = DOCS_RL / nom
        try:
            lignes = chemin.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        ident_doc, _slug = couper_nom(Path(nom).stem)
        cle_doc = normaliser(ident_doc)
        for debut, fin in sections_de_residus(lignes):
            for i in range(debut, fin):
                m = RE_TETE_DE_PUCE.match(lignes[i])
                if not m:
                    continue
                avant = lignes[i][: lignes[i].index("#" + m.group(1))]
                d = Definition(m.group(1), "puce-case-doc", "%s:%d" % (nom, i + 1),
                               "~~" in avant, lignes[i])
                brut.setdefault(d.cle, []).append((d, cle_doc))
    definitions, citations = [], []
    for cle, lot in brut.items():
        proprios = [len(cd) for _d, cd in lot if cd and cle.startswith(cd)]
        maxi = max(proprios) if proprios else None
        for d, cd in lot:
            possede = maxi is not None and cd and cle.startswith(cd) and len(cd) == maxi
            (definitions if (maxi is None or possede) else citations).append(d)
    return definitions, citations


# ------------------------------------------------------------------------------------------
# Le LEDGER : ce que le cliquet a FIGE comme ligne de base
# ------------------------------------------------------------------------------------------
#
# Chaque entree est `"<ident normalise>|<portee>": "<statut> -- <raison>"`, ou la PORTEE est soit
# le nom d'une case-doc (etape 2), soit le marqueur `@backlog` (etape 1, qui ne porte sur aucun
# fichier). Deux statuts :
#   * une raison LIBRE = cohabitation legitime (tache-parapluie, dossier re-ouvert) ;
#   * `COLLISION-OUVERTE` = collision REELLE non resolue. Re-imprimee A CHAQUE RUN, elle ne fait
#     pas rougir : renumeroter apres livraison est une reecriture d'historique, donc un arbitrage
#     d'orchestrateur -- pas une decision de cliquet.
COLLISION_OUVERTE = "COLLISION-OUVERTE"
#: Portee conventionnelle des attestations de l'etape 1 (aucun fichier n'y est en cause).
PORTEE_BACKLOG = "@backlog"


def lire_ledger() -> dict:
    if not LEDGER.exists():
        return {}
    try:
        brut = LEDGER.read_text(encoding="utf-8")
    except OSError as exc:                                # verrou, droits : pas le depot
        raise Indisponible("ledger illisible sur disque : %s" % exc) from exc
    try:
        data = json.loads(brut)
    except ValueError as exc:                             # JSON invalide : fait sur le CONTENU
        print("   ROUGE ledger au JSON invalide (%s) -- traite comme VIDE, donc BLOQUANT" % exc)
        return {}
    return {k: v for k, v in data.get("attestations", {}).items() if isinstance(v, str) and v.strip()}


def ecrire_ledger(att: dict) -> None:
    LEDGER.write_text(json.dumps(
        {"_": "Cohabitations ATTESTEES pour probe_468_collision_numeros.py. Cle = "
              "'<identifiant normalise>|<nom de la case-doc>'. Valeur = la RAISON, non vide. "
              "Le statut 'COLLISION-OUVERTE' marque une collision reelle NON resolue : elle est "
              "re-imprimee a chaque run et n'est PAS un blanc-seing.",
         "attestations": dict(sorted(att.items()))},
        indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------------------
# Etape 0a -- auto-test des detecteurs
# ------------------------------------------------------------------------------------------
#
# Chaque cas POSITIF a son jumeau NEGATIF : c'est le jumeau qui interdit d'elargir le motif pour
# << faire mordre >> le cliquet. Les negatifs sont des MENTIONS reelles, recopiees du depot.
CAS = [
    # --- POSITIFS : les trois positions de definition ---
    ("tableau, entree ouverte",
     ["| #465-r1 | **Le ledger ne dit pas si un rouge a ete mesure ICI** | `[opus]` | `case-465` |"],
     [("465r1", True)]),
    ("tableau, entree BARREE",
     ["| ~~#462~~ | ~~**Rien ne regarde l'etat des tests LIVE**~~ | **INVENTAIRE LIVRE** | x |"],
     [("462", False)]),
    ("tableau, titre barre mais numero OUVERT",
     ["| #448-r1-r1-r1-r1-r1 | ~~**a moitie**~~ **Le departage n'est pas lu** | `[opus]` | y |"],
     [("448r1r1r1r1r1", True)]),
    ("tete de puce, backtickee",
     ["- **`#420-r1` -- filtre CARRIER `UnitsWithRanged...` non porte.** Il monte un"],
     [("420r1", True)]),
    ("tete de puce, sans backtick ni tiret cadratin",
     ["- **#45d, residus** (`playbook/prediction.md` section 9bis -- tranche CLOSE"],
     [("45d", True)]),
    # --- POSITIFS de #468-r1 : les formes que `ID` rendait INVISIBLES (pas repliees) ---
    ("tableau, segment LETTRE suivi d'un residu (`-c-r3-r1-r5`)",
     ["| #462-r4b-r1-r1-r1-r1-c-r3-r1-r5 | **La POSE de la mine** | `[opus]` | `case-462` |"],
     [("462r4br1r1r1r1cr3r1r5", True)]),
    ("tableau, suffixe en MOT (`-camo-seed`)",
     ["| ~~#366-r1-camo-seed~~ | ~~**Un effet CONDITION-GATED absent**~~ | **LIVRE** | x |"],
     [("366r1camoseed", False)]),
    ("tableau, identifiant NON NUMERIQUE a suffixe (`#PAI-c`, `#BL-1029r-r1`)",
     ["| #PAI-c | **Consommateurs de `PerformAIAction` restants** | `[opus]` | y |",
      "| #BL-1029r-r1 | **Le 10e coup du cast de Drachnyen** | `[opus]` | z |"],
     [("paic", True), ("bl1029rr1", True)]),
    ("tableau, suffixe purement NUMERIQUE (`#222-1`) -- lu ENTIER, plus jamais ignore",
     ["| ~~#222-1~~ | ~~`ArmoriumCherub` (1014) : masque de ciblage~~ | **CLOS** | w |"],
     [("2221", False)]),

    # --- NEGATIFS : des MENTIONS, et c'est l'echantillon qui compte ---
    ("colonne Point d'entree : un renvoi, pas une definition",
     ["| #467-r3 | **Le rappel ne se repete pas** | `[opus]` | `case-467` section 7 ; voir #465 |"],
     [("467r3", True)]),
    ("ligne de continuation de puce (indentee) : jamais une ouverture",
     ["- **`#462-r4a-r1` -- le decompile route les deux canaux.**",
      "  `case-462-r4a-canal-du-multiplicateur.md` section 6. Voir aussi #420-r1 et #443-r2."],
     [("462r4ar1", True)]),
    ("puce dont le numero n'est PAS en tete",
     ["- **Le correctif #321 n'est PAS VERIFIE EN VOL.** `[opus]` Il vit dans `frida/host/*`,"],
     []),
    ("prose : deux renvois croises dans la meme phrase",
     ["C'est #434 dans l'autre sens (la-bas on LISAIT hors perimetre, ici on y ECRIVAIT), et le",
      "residu #439-r1 le nomme. Detail : `docs/rl/case-430-banque-de-cliquets.md`."],
     []),
    ("message de commit",
     ["chore(#462): regenerer le ledger apres #554",
      "docs(#467): l'etat de boucle, resolution de #465-r1"],
     []),
    ("blockquote qui cite une entree",
     ["> **#465-r1** est cite ici comme rappel, pas ouvert."],
     []),
    ("separateur de tableau et en-tete",
     ["| # | Tache | Modele | Point d'entree |", "|---|---|---|---|"],
     []),
    ("sous-puce indentee portant un numero en tete",
     ["  - **#468-r9** une sous-puce n'ouvre pas un dossier"],
     []),
    ("titre de section markdown",
     ["## Residus ouverts par #321 (registre host des runners)"],
     []),
]

CAS_NOMS = [
    # (nom de fichier, ident attendu, slug attendu)
    ("case-448-r1-r1-r2-second-bras-islikeflying.md", "448-r1-r1-r2", "second-bras-islikeflying"),
    ("case-1014-armorium-cherub-targeting.md", "1014", "armorium-cherub-targeting"),
    ("case-467-etat-de-boucle.md", "467", "etat-de-boucle"),
    ("case-366r1-echoes-from-the-warp-revive.md", "366r1", "echoes-from-the-warp-revive"),
    ("case-254b-a-worktree-frais-enums.md", "254b-a", "worktree-frais-enums"),
    ("case-r6bp2-after-hit-maybe-ability-vector.md", "r6bp2", "after-hit-maybe-ability-vector"),
    ("case-1203-on-toxic-damage.md", "1203", "on-toxic-damage"),
]


def self_test(verbose: bool) -> list:
    mauvais = []
    for nom, lignes, attendu in CAS:
        vus = [(d.cle, d.ouverte) for d in definitions_du_backlog(lignes)]
        ok = vus == attendu
        if verbose or not ok:
            print("   %-5s %-52s vu=%s attendu=%s"
                  % ("OK" if ok else "FAIL", nom, vus, attendu))
        if not ok:
            mauvais.append(nom)
    for nom, ident, slug in CAS_NOMS:
        vu = couper_nom(Path(nom).stem)
        ok = vu == (ident, slug)
        if verbose or not ok:
            print("   %-5s %-52s vu=%s attendu=%s"
                  % ("OK" if ok else "FAIL", "nom: " + nom, vu, (ident, slug)))
        if not ok:
            mauvais.append(nom)
    # `366-r1` et `366r1` doivent se rejoindre, sinon une collision passe entre les deux graphies.
    if normaliser("366-r1") != normaliser("366r1"):
        mauvais.append("normalisation des graphies")
    return mauvais


# ------------------------------------------------------------------------------------------
# Etape 0b -- la contre-epreuve SUR PIECES : definitions vs mentions du depot reel
# ------------------------------------------------------------------------------------------

def ventiler_occurrences() -> tuple:
    """(occurrences totales, definitions, fichiers lus) sur `docs/rl/**.md`.

    Le chiffre qui compte est le RATIO : si presque tout etait une definition, le critere ne
    separerait rien. Sur `docs/rl`, les mentions ecrasent les definitions d'un ordre de grandeur.
    """
    total, fichiers = 0, 0
    for p in sorted(DOCS_RL.rglob("*.md")):
        try:
            txt = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fichiers += 1
        total += len(RE_OCCURRENCE.findall(txt))
    defs = len(definitions_du_backlog(_lignes_backlog())) + len(
        definitions_des_case_docs(_fichiers_case_docs()))
    return total, defs, fichiers


def _lignes_backlog() -> list:
    if not DOCS_RL.is_dir():
        raise Indisponible("docs/rl introuvable sous %s -- CWD ou --racine faux" % REPO)
    if not BACKLOG.is_file():
        return []                                          # fait sur le depot -> ROUGE
    try:
        return BACKLOG.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Indisponible("backlog.md illisible sur disque : %s" % exc) from exc
    except UnicodeDecodeError:
        return []                                          # fait sur le CONTENU -> ROUGE


# ------------------------------------------------------------------------------------------
# Etapes 1 et 2
# ------------------------------------------------------------------------------------------

def etape1_double_ouverture(defs_backlog) -> list:
    """[(cle, [Definition])] -- deux definitions NON BARREES du meme identifiant."""
    par_cle = {}
    for d in defs_backlog:
        if d.ouverte:
            par_cle.setdefault(d.cle, []).append(d)
    return sorted((k, v) for k, v in par_cle.items() if len(v) > 1)


def doubles_cles(doubles) -> list:
    return [k for k, _v in doubles]


def etape2_cohabitations(defs_backlog, defs_cases) -> list:
    """[(cle, Definition backlog ouverte, [Definition case-doc])]."""
    ouverts = {}
    for d in defs_backlog:
        if d.ouverte:
            ouverts.setdefault(d.cle, d)
    par_cle = {}
    for d in defs_cases:
        par_cle.setdefault(d.cle, []).append(d)
    return sorted((k, ouverts[k], par_cle[k]) for k in set(ouverts) & set(par_cle))


# ------------------------------------------------------------------------------------------
# Inventaire (--report) : les formes REFUTEES comme criteres, rendues en chiffres
# ------------------------------------------------------------------------------------------

def _artefacts_de_code() -> tuple:
    """({cle: [probe]}, {cle: [test]}) -- balayage CONFINE a `scripts/python`."""
    probes, tests = {}, {}
    for p in sorted((REPO / "scripts" / "python").rglob("*.py")):
        m = re.match(r"^(probe|test)_(\d[\w]*)\.py$", p.name)
        if not m:
            continue
        ident, _slug = couper_nom("case-" + m.group(2).replace("_", "-"))
        (probes if m.group(1) == "probe" else tests).setdefault(normaliser(ident), []).append(p.name)
    return probes, tests


def code_seule_position(probes, tests, ailleurs) -> dict:
    """{cle: [fichiers]} -- les identifiants dont un ARTEFACT DE CODE est la SEULE position.

    C'EST LA POPULATION QUE #468-r3 DESIGNE, et le residu la donnait pour << probablement vide >>.
    MESURE (2026-08-15) : elle ne l'est PAS. Sur **928** identifiants portes par au moins un
    `probe_<n>_*.py` / `test_<n>_*.py`, **177** n'ont AUCUNE autre position -- ni ligne de
    `backlog.md`, ni `case-<n>-*.md`, ni puce de section << Residus >> -- et **40** d'entre eux
    portent **deux fichiers ou plus**. C'est exactement la forme decrite : une collision qui ne se
    manifesterait QUE par deux artefacts de code passerait, et il y a 40 endroits ou elle pourrait
    se cacher.

    MAIS ELLE RESTE INDECIDABLE, et cinq cas traces par une SECONDE SOURCE le montrent. Les plus
    ambigus par les slugs -- `#1066` (`macro-plasma-decision` + `rites-of-morkai-decision`),
    `#982-r5` (`swap-decisionview` + `can-heal-full-health`), `#494-r1` (`db4-decompose` +
    `ordre-cibles`), `#365` (`versioned-imports-gitignored` + `selector-montage`), `#421`
    (`rail-covers-registry` + `effect-active-gate`) -- ont ete confrontes a `git log --grep` :
    TROIS se resolvent en UNE SEULE tranche multi-facettes (`#1066` = << les trois dernieres faces
    DECISION d'actives de kit >>), et DEUX sont indecidables, leur dossier etant clos sans
    case-doc. Zero collision ETABLIE.

    D'OU LE MEME VERDICT QUE LES SECTIONS 3.1 ET 3.2 : aucun critere textuel ne separe une tranche
    multi-facettes d'une collision -- les deux portent le meme numero et des slugs sans rapport.
    INVENTAIRE, jamais bloquant. Ce qui change par rapport a avant : le rapport ne montrait que le
    compte BRUT (<< N ids a >= 2 probes >>), qui melange les 751 identifiants ayant un dossier
    ailleurs avec les 40 qui n'en ont pas. Seuls ces 40 sont le gisement.
    """
    tous = {}
    for source in (probes, tests):
        for cle, fichiers in source.items():
            tous.setdefault(cle, []).extend(fichiers)
    return {cle: sorted(f) for cle, f in tous.items() if cle not in ailleurs}


# ------------------------------------------------------------------------------------------
# `--suggere` -- DONNER un numero libre (residu #468-r4)
# ------------------------------------------------------------------------------------------
#
# Critere INVERSE de celui des etapes 1 et 2 : ici on prend l'UNION de toutes les positions,
# mentions comprises. Un numero seulement CITE est deja pris -- c'est litteralement l'occurrence
# `#448-r1-r1-r2`, ou le rapport employait le numero AVANT tout artefact.

#: Une racine SANS suffixe de residu (`465`), par opposition a `465r1` ou `r6`.
RACINE_PURE = re.compile(r"^\d+$")


#: Les DEUX arbres ou un numero s'emploie. Bornes en PATHSPEC, donc `git grep` ne remonte
#: jamais a la racine : `.claude/worktrees/` est hors de portee par construction (#434), et
#: depuis un worktree la commande ne voit QUE ce worktree.
PATHSPECS = ("docs/rl", "scripts/python")

#: Motif d'ATTRIBUTION, volontairement plus large que `RE_OCCURRENCE` : tout ce qui suit un
#: `#` et pourrait etre lu comme un identifiant. Un sur-ensemble est le cote SUR ici -- il fait
#: SAUTER un numero, jamais le reprendre. (Verifie : ce que `RE_OCCURRENCE` voit, il le voit.)
RE_TOKEN_LARGE = r"#[0-9a-zA-Z][0-9a-zA-Z_-]*"


def _git(args, quoi):
    """Lance git ou LEVE. Une panne d'outil n'est jamais un ensemble vide -- ce serait
    exactement la mesure amputee qui fabrique une collision."""
    import subprocess
    try:
        res = subprocess.run(["git", "-C", str(REPO)] + args, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Indisponible("%s injouable (%s) -- aucun numero ne peut etre suggere sur un "
                           "corpus ampute" % (quoi, exc)) from exc
    # `git grep` rend 1 quand il ne trouve RIEN : c'est une reponse valide, pas une panne.
    if res.returncode not in (0, 1):
        raise Indisponible("%s rc=%d -- aucun numero ne peut etre suggere sur un corpus "
                           "ampute" % (quoi, res.returncode))
    return res.stdout


def _identifiants_du_contenu() -> dict:
    """{cle: {'contenu'}} -- tout `#<n>` de `docs/rl` et `scripts/python`, par `git grep`.

    COUT, mesure le 2026-08-04 sur 535 `.md` + 1749 `.py` : `git grep` 0,6 s contre 16,7 s
    (jusqu'a 37 s sous charge) pour `rglob` + `read_text`, pour un resultat STRICTEMENT
    equivalent. La regex n'y etait pour rien -- elle coute 0,1 s sur le corpus deja en
    memoire ; c'est la LECTURE de 2 300 fichiers qui dominait. Un outil d'attribution qu'on
    attend deux minutes ne sera pas utilise, donc ne supprimera aucun geste fautif.

    `--untracked` couvre le travail NON COMMITE du worktree courant : c'est precisement la
    ou vit le numero que l'agent est en train de prendre.
    """
    out = {}
    txt = _git(["grep", "-h", "-o", "-I", "--untracked", "-E", RE_TOKEN_LARGE, "--"]
               + list(PATHSPECS), "`git grep`")
    for ligne in txt.splitlines():
        if len(ligne) > 1:
            out.setdefault(normaliser(ligne[1:]), set()).add("contenu")
    return out


def _identifiants_des_noms() -> dict:
    """{cle: {nom}} -- `case-<n>-*.md`, `probe_<n>_*.py`, `test_<n>_*.py`.

    Le nom porte l'identifiant meme quand le contenu ne le cite pas -- et le glob voit les
    fichiers non commites, comme `--untracked` ci-dessus."""
    out = {}
    fichiers = list(DOCS_RL.rglob("*.md")) + list((REPO / "scripts" / "python").rglob("*.py"))
    for p in fichiers:
        ident, _slug = couper_nom(re.sub(r"^(?:probe|test)_", "", p.stem).replace("_", "-"))
        if ident:
            out.setdefault(normaliser(ident), set()).add(p.name)
    return out


def _identifiants_des_commits() -> dict:
    """{cle: {'git log'}} -- l'historique fait partie de l'espace de noms.

    `git log --grep "#<n>"` est une voie de tracabilite de plein droit : un numero cite dans un
    message de commit est PRIS, meme si aucun fichier ne le porte plus (case-doc renommee,
    tranche abandonnee). MESURE : 13 racines pures < 500 ne vivent QUE la.

    LES COMMITS DE MERGE EN FONT PARTIE, et les EXCLURE amputait la source la plus complete
    (#468-r13). `--no-merges` etait ici un defaut jamais examine -- aucune ligne ne le motivait --
    et il jetait la SEULE trace que le squash-merge laisse dans l'arbre. Mesure du 2026-08-15 :
    698 commits de merge, dont **647 portent un `#`** en sujet (`merge(#1039) : ...`,
    `merge PR #1023 (#1027) -- ...`) ; ils apportent **96 identifiants INEDITS** que les six
    autres sources ne voient pas, et **1 numero rendu change** -- `--suggere 432` proposait
    `#432-r1`, alors que ce residu a ete LIVRE par la PR #479 et que `git grep -E '#432-?r1'`
    sur `docs/rl` + `scripts/python` rend **0** : le sujet du merge est son unique trace.
    COUT : NUL -- c'est le meme `git log`, avec un filtre en moins (1,09 s -> 0,99 s, dans le
    bruit). Aucun bruit de nom de branche non plus : `RE_TOKEN_LARGE` exige un `#`, et les
    51 merges sans `#` sont exactement les `Merge remote-tracking branch 'origin/...'`.

    Toute panne de `git` leve `Indisponible` -- jamais un ensemble VIDE, qui ferait suggerer un
    numero deja pris. C'est la meme frontiere que `host_inputs.py` : `null` n'est pas `0`.
    """
    out = {}
    for m in re.finditer(RE_TOKEN_LARGE, _git(["log", "--format=%s%n%b"], "`git log`")):
        out.setdefault(normaliser(m.group(0)[1:]), set()).add("git log")
    return out


#: Libelles de PROVENANCE des sources HORS DE CE QUI EST FUSIONNE (niveaux N1 et N2 du
#: docstring, plus le corps des PR ajoute par #468-r11). Ils sont le discriminant de
#: `_imprimer_portee` : un identifiant dont TOUTES les sources sont la n'est PAS dans l'arbre
#: fusionne, et c'est exactement ce qu'un `--suggere` d'hier aurait propose.
SRC_REF_EN_VOL = "ref non fusionnee"
SRC_WORKTREE = "worktree "


def _identifiants_des_refs_hors_head() -> dict:
    """{cle: {SRC_REF_EN_VOL}} -- N1 : les commits que `HEAD` n'atteint PAS.

    `--not HEAD` est ce qui rend la provenance gratuite ET la mesure bon marche : sur 363 refs,
    ce qui reste hors de la lignee courante est une poignee de commits. Un `--all` nu couterait
    autant mais melangerait les deux origines, et on ne pourrait plus DIRE ce qui est en vol.

    ICI `--no-merges` RESTE, et c'est une TROISIEME extension MESUREE PUIS REFUSEE (#468-r13),
    par le meme protocole que les deux de `#468-r10`. Le retirer coute **+1,0 s** (1,94 -> 2,97 s)
    et apporte **0 identifiant inedit** -- non pas parce que les merges hors `HEAD` seraient
    vides, mais parce que la correction ci-dessus (`_identifiants_des_commits` lit desormais les
    merges) les couvre deja. Mesure PRISE HORS DU REGIME DEGENERE : un worktree FRAIS ne prouve
    rien ici, puisque tout est dans sa lignee ; le balayage a donc ete rejoue en simulant un
    worktree EN RETARD de 5, 20, 40 et 80 commits (`--not HEAD~n`), et l'apport reste **0 a
    chaque palier**. Ce qui reste hors de portee est nomme : un merge vivant SEULEMENT sur une
    branche non fusionnee -- et les 51 merges sans `#` du depot sont tous des
    `Merge remote-tracking branch 'origin/...'`, qui ne portent aucun numero par construction.
    """
    out = {}
    txt = _git(["log", "--all", "--not", "HEAD", "--format=%s%n%b", "--no-merges"],
               "`git log --all --not HEAD`")
    for m in re.finditer(RE_TOKEN_LARGE, txt):
        out.setdefault(normaliser(m.group(0)[1:]), set()).add(SRC_REF_EN_VOL)
    return out


#: Les motifs qui portent un identifiant DANS UN NOM DE FICHIER. Bornes a dessein : un glob
#: non borne (ou `git log --name-only`) ramasse tous les modules du moteur et rend 24 faux
#: positifs sur 25 -- mesure, cf. docstring.
GLOBS_IDENTIFIANTS = ("docs/rl/case-*.md", "scripts/python/probe_*.py",
                      "scripts/python/test_*.py", "scripts/python/tests/test_*.py")

#: CE N'EST PAS LA FAUTE DE #434, et la distinction est le coeur du sujet. #434 punit un
#: cliquet qui ENUMERE DEPUIS LA RACINE et ramasse `.claude/worktrees/` sans le vouloir : il
#: paie la traversee x N et rapporte les fichiers du voisin COMME LES SIENS. Ici les worktrees
#: sont la CIBLE, nommes un par un par `git worktree list`, avec quatre motifs bornes et pour
#: leurs seuls NOMS -- jamais confondus avec le perimetre courant, puisqu'ils sortent sous
#: `worktree <nom>`. Verifie : `probe_440` reste PASS. Et `--suggere` n'est pas dans la banque
#: (`ratchets.ps1` l'appelle sans argument), donc ces 0,39 s ne touchent pas le mur des
#: cliquets -- c'est la meme raison qui autorisait deja le `git grep` de `--suggere`.


def _autres_worktrees():
    """[(chemin, branche ou None)] -- les worktrees du meme `.git`, SAUF celui d'ou l'on parle.
    `None` = capteur MUET, ce qui n'est pas la meme chose qu'une liste vide.

    POURQUOI CELUI-CI NE LEVE PAS `Indisponible`, alors que `git grep` et `git log` le font.
    C'est un capteur d'APPOINT : sans lui, `--suggere` retombe exactement sur le corpus
    fusionne, c'est-a-dire sur son comportement d'avant #468-r10 -- degrade, mais pas faux au
    sens ou l'etait un corpus prive de son historique. Le faire lever transformerait la panne
    d'un capteur d'appoint en REFUS TOTAL, donc une regression pour un `git` ancien ou bride.
    La contrepartie est stricte, et c'est `_imprimer_portee` qui la tient : muet se DIT
    (<< NON MESUREE >>) et ne se rabat JAMAIS sur << 0 autre worktree >>."""
    import os
    try:
        txt = _git(["worktree", "list", "--porcelain"], "`git worktree list`")
    except Indisponible:
        return None
    # TROUVE A LA RELECTURE, et c'est le vice meme que ce bloc existe pour eviter : `_git`
    # TOLERE `rc=1`, parce que `git grep` rend 1 quand il ne trouve rien -- reponse valide.
    # Pour `worktree list`, `rc=1` est une PANNE (sous-commande absente d'un git ancien), et
    # elle sortirait en stdout VIDE, donc en << 0 autre worktree MESURE >>. Le discriminant
    # est DERIVE, pas conventionnel : un `worktree list` qui reussit liste TOUJOURS au moins
    # l'arbre d'ou l'on parle. Une sortie vide ne peut donc etre qu'un capteur muet.
    if not txt.strip():
        return None
    moi = os.path.normcase(os.path.realpath(str(REPO)))
    out, courant = [], {}
    for ligne in txt.splitlines() + [""]:
        if not ligne.strip():
            if courant.get("worktree"):
                chemin = courant["worktree"]
                if os.path.normcase(os.path.realpath(chemin)) != moi:
                    out.append((Path(chemin), courant.get("branch")))
            courant = {}
            continue
        cle, _, val = ligne.partition(" ")
        courant[cle] = val or True
    return out


def _identifiants_des_worktrees(autres) -> tuple:
    """({cle: {'worktree <nom>'}}, [(chemin, raison)]) -- N2 : les NOMS ecrits chez les voisins.

    On ne lit QUE des noms de fichiers, et par le systeme de fichiers : aucune commande git
    n'est lancee DANS l'arbre d'autrui. `git status` y rafraichirait l'index -- une ECRITURE
    dans le worktree d'un agent qui travaille.

    TRI-ETAT PAR WORKTREE : un repertoire devenu illisible (un worktree jetable de pytest qui
    meurt en cours de balayage, un agent nettoye) est RENDU dans la seconde liste et NOMME par
    `_imprimer_portee`. Il n'est ni ignore en silence (ce serait un zero fabrique), ni promu en
    `Indisponible` (ce qui rendrait l'outil inutilisable des qu'une flotte tourne).

    CE QU'ON ACCEPTE, ET C'EST LE BON COTE : un worktree ABANDONNE (agent mort, nettoyage pas
    encore passe) fait reserver un numero qui ne sera peut-etre jamais livre. On saute alors un
    numero pour rien -- exactement la meme asymetrie que la monotonie de `suggerer` : on ne
    recycle pas un trou parce qu'un trou peut etre pris. Sauter coute un entier ; reprendre
    coute une reecriture d'historique."""
    out, illisibles = {}, []
    for chemin, _branche in (autres or ()):     # `None` = capteur muet, deja dit par la portee
        try:
            # UN SEUL foyer d'illisibilite, et c'est une contre-epreuve qui l'a impose :
            # `Path.glob` sur un repertoire ABSENT ne leve pas, il rend une liste VIDE. Le
            # test passait donc par un second chemin que la mutation ne visait pas, et la
            # mutation << illisible avale >> restait VERTE. Deux chemins pour un meme constat,
            # c'est un chemin non garde.
            if not chemin.is_dir():
                raise OSError("repertoire absent")
            trouves = [p for g in GLOBS_IDENTIFIANTS for p in chemin.glob(g)]
        except OSError as exc:
            illisibles.append((chemin, str(exc)))
            continue
        for p in trouves:
            ident, _slug = couper_nom(re.sub(r"^(?:probe|test)_", "", p.stem).replace("_", "-"))
            if ident:
                out.setdefault(normaliser(ident), set()).add(SRC_WORKTREE + chemin.name)
    return out, illisibles


#: Profondeur de lecture des PULL REQUESTS. DERIVEE d'une mesure, pas choisie : sur le depot
#: reel (670 PR), les 200 plus recentes apportent les **2** changements de numero mesures, et
#: la lecture integrale n'en apporte AUCUN de plus pour x1,9 le cout. Cf. docstring du module.
GH_LIMITE_PR = 200

#: Libelle de PROVENANCE de la quatrieme source en vol -- le corps d'une PR n'est PAS dans
#: l'arbre (le squash-merge ne l'y recopie pas), donc un identifiant qui n'existe que la est,
#: du point de vue de toute lecture de l'arbre, aussi invisible qu'un worktree voisin.
SRC_PR = "corps de PR"

#: Libelle de PROVENANCE du NUMERO PROPRE d'une PR -- distinct de `SRC_PR`, qui ne designe que
#: ce que le titre et le corps CITENT. La PR #1088 rend `#1088` pris sans citer quoi que ce soit :
#: dans un espace de noms partage, exister SUFFIT. Le JSON de `gh` demandait deja `number` et ne
#: s'en servait pas -- le defaut en miniature.
SRC_PR_NUMERO = "numero de PR"

#: Delai maximal accorde a `gh`. MESURE : 1,4 s (0 PR ouverte) a 3,9 s (200 PR). Un depassement
#: est une PANNE NOMMEE, pas un zero -- meme frontiere que les autres capteurs.
GH_TIMEOUT_S = 30


def _pull_requests():
    """([{title, body}], None) si MESURE | (None, raison) si NON MESURE. JAMAIS ([], raison).

    Le tri-etat est la seule chose qui compte ici : un `gh` muet doit se lire << je n'ai pas
    regarde >>, jamais << il n'y a rien >>. Et la panne doit porter son NOM -- sur `gh 2.88.1`,
    `rc=1` couvre a lui seul le token invalide (HTTP 401), le depot inconnu (GraphQL) et
    l'erreur d'usage ; `4` = non authentifie. Seul le STDERR les separe (#467-r6), donc c'est
    le stderr qu'on remonte, pas le `rc`.

    PAS DE DISCRIMINANT DERIVE ICI, contrairement a `git worktree list`. La-bas, une sortie
    vide ne PEUT PAS etre vraie (un `worktree list` qui reussit liste toujours l'arbre courant).
    Ici, un depot sans aucune PR rend legitimement `[]` : le seul discriminant disponible est
    `rc == 0` + JSON valide, et on le dit plutot que d'inventer une regle.

    AUCUN REPLI SUR CACHE. Un cache disant << 0 PR >> ne prouverait rien et ferait taire l'outil
    sur une PR ouverte depuis -- il peut SIGNALER, jamais RASSURER, donc il n'existe pas.
    """
    import subprocess
    try:
        res = subprocess.run(
            ["gh", "pr", "list", "--state", "all", "--limit", str(GH_LIMITE_PR),
             "--json", "number,title,body"],
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=GH_TIMEOUT_S)
    except FileNotFoundError:
        return None, "`gh` introuvable sur le PATH"
    except subprocess.TimeoutExpired:
        return None, "`gh` n'a pas repondu en %d s" % GH_TIMEOUT_S
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "`gh` injouable : %s" % exc
    if res.returncode != 0:
        motif = " ".join((res.stderr or "").split())[:160] or "(stderr vide)"
        return None, "`gh` rc=%d -- %s" % (res.returncode, motif)
    try:
        data = json.loads(res.stdout or "null")
    except ValueError as exc:
        return None, "`gh` rc=0 mais sortie illisible : %s" % exc
    if not isinstance(data, list):
        return None, "`gh` rc=0 mais sortie inattendue (%s)" % type(data).__name__
    return data, None


def _identifiants_des_pr(prs) -> dict:
    """{cle: {SRC_PR | SRC_PR_NUMERO}} -- ce que les PR CITENT, et ce qu'elles SONT.

    LE NOM DE BRANCHE EST EXCLU, et c'est une mesure : sur 40 PR il apporte 24 identifiants
    (`#worktree-agent-a5af8da...`, `#agent-477r16r1`) pour **0** signal -- exactement le bruit
    qui a fait refuser `git log --name-only` (#468-r10 section 3).

    LE NUMERO PROPRE DE LA PR EST INCLUS (#468-r8). Il ne l'etait pas, et c'est ce qui a laisse
    `#1084` designer a la fois le residu du foyer `damage_model.py` et la PR du foyer
    `targeting.py` : `git log --grep='#1084'` rend les deux, et rien ne dit lequel est vise. Le
    `number` etait deja demande a `gh` et jete.

    ⚠ CE N'EST PAS, A SOI SEUL, LE CORRECTIF DE LA COLLISION -- et le croire serait le piege.
    Marquer `#1088` pris fait allouer `#1089`, que GitHub donnera a la PR suivante, ouverte
    quelques minutes plus tard pour cette tranche meme : la collision serait DEPLACEE. Ce qui la
    supprime est la BANDE (`PLANCHER_RACINE`). Cette source-ci fait autre chose, qui compte
    aussi : elle rend le corpus HONNETE sur ce qui est deja pris.
    """
    out = {}
    for pr in prs or ():
        for champ in ("title", "body"):
            for m in re.finditer(RE_TOKEN_LARGE, pr.get(champ) or ""):
                out.setdefault(normaliser(m.group(0)[1:]), set()).add(SRC_PR)
        num = pr.get("number")
        if isinstance(num, int) and num > 0:
            out.setdefault(str(num), set()).add(SRC_PR_NUMERO)
    return out


# ------------------------------------------------------------------------------------------
#  LA RESERVATION -- ce qui fait passer d'OBSERVER a ALLOUER (#468-r14)
# ------------------------------------------------------------------------------------------
#
# Voir la section << CINQ SOURCES NE SUFFISENT PAS >> du docstring pour le POURQUOI et pour les
# trois formes refusees. Ici, le COMMENT, et il tient en une ligne : la creation exclusive d'un
# fichier EST l'allocation. Pas de verrou a prendre, donc pas de verrou orphelin a expirer ;
# pas d'etat a relire apres l'avoir ecrit, donc pas de fenetre entre le constat et la prise.

#: Libelle de PROVENANCE d'un numero RESERVE mais pas encore ecrit. C'est la SIXIEME source, et
#: la seule qui ne soit pas une lecture de ce qui existe : elle dit ce qui a ete PRIS.
SRC_RESERVATION = "reservation"

#: Le sous-dossier, sous le `.git` COMMUN. Prefixe explicite : ce repertoire cohabite avec les
#: donnees de git, il doit se lire comme etranger a elles au premier coup d'oeil.
NOM_DOSSIER_RESERVATIONS = "tacticus-468-reservations"

#: Garde de TERMINAISON de la boucle d'allocation -- pas un seuil de qualite. Chaque tour perdu
#: signifie qu'un AUTRE processus a pris notre candidat entre notre calcul et notre creation ;
#: avec C allocateurs concurrents, un ordonnancement equitable en produit au plus C-1. La borne
#: est large et ne se degrade PAS en silence : elle LEVE (`Indisponible`), elle ne rend jamais
#: un numero non reserve.
PLAFOND_TENTATIVES = 1000

#: Un parent acceptable APRES normalisation. Il devient un NOM DE FICHIER : tout ce qui n'est
#: pas alphanumerique est refuse ici plutot que traduit en chemin (`--suggere ../ailleurs`).
RE_PARENT_SUR = re.compile(r"^[0-9a-z]+$")


def _chemin_git_commun() -> Path:
    """Le `.git` PARTAGE par tous les worktrees de ce depot.

    MESURE (2026-08-11) : `git rev-parse --git-common-dir` rend le meme chemin absolu -- le `.git`
    de l'arbre PRINCIPAL -- depuis l'arbre principal ET depuis chacun des 32 worktrees d'agents.
    C'est ce que garantit un worktree LIE -- le `.git` d'un worktree est un fichier qui pointe vers
    le repertoire commun -- donc ce n'est pas une propriete de notre installation, c'est la
    definition. (La VALEUR de ce chemin ne s'ecrit pas ici : `probe_273` etape 0b balaie le TEXTE,
    docstrings comprises, et un chemin absolu ecrit en prose est une invitation a le recopier.)

    La forme RELATIVE (`.git`, rendue depuis l'arbre principal par les git anciens) est resolue
    contre `REPO` : on n'exige pas `--path-format=absolute`, qui daterait la compatibilite a
    git 2.31 sans rien apporter."""
    brut = _git(["rev-parse", "--git-common-dir"], "`git rev-parse --git-common-dir`").strip()
    if not brut:
        raise Indisponible("`git rev-parse --git-common-dir` muet -- sans repertoire git commun, "
                           "aucune reservation n'est visible des autres worktrees")
    chemin = Path(brut)
    if not chemin.is_absolute():
        chemin = REPO / brut
    return chemin.resolve()


def _dossier_reservations() -> Path:
    """Le dossier des reservations, CREE si besoin. LEVE si on ne peut pas y ecrire.

    Une reservation impossible ne se degrade PAS en observation : ce serait revenir exactement
    au defaut que cette tranche supprime, et en silence. `--suggere` sort alors en INDISPONIBLE
    sans imprimer de numero -- meme frontiere que << une mesure incomplete ne rend jamais de
    numero >>, transposee de la LECTURE a l'ECRITURE."""
    dossier = _chemin_git_commun() / NOM_DOSSIER_RESERVATIONS
    try:
        dossier.mkdir(parents=True, exist_ok=True)          # exist_ok : deux agents en parallele
    except OSError as exc:
        raise Indisponible("dossier de reservations inaccessible (%s) -- aucun numero ne peut "
                           "etre ALLOUE, et l'observation seule ne suffit pas" % exc) from exc
    return dossier


def _contexte_de_reservation(etiquette: str) -> dict:
    """Qui reserve, d'ou, quand. MESURE AVANT la creation exclusive, a dessein : une panne de
    capteur ici ne doit pas survenir APRES qu'on a deja pris le numero."""
    import subprocess
    branche = "?"
    try:
        res = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30)
        if res.returncode == 0 and res.stdout.strip():
            branche = res.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass                                    # informatif : jamais bloquant pour l'allocation
    return {
        "quand": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "worktree": str(REPO),
        "branche": branche,
        "pid": os.getpid(),
        "pour": etiquette or "(non dit)",
    }


def _reserver(cle: str, dossier: Path, contexte: dict) -> bool:
    """PREND `cle`. True si NOUS l'avons obtenue, False si un autre nous a devances.

    `O_CREAT|O_EXCL` est le point entier de cette tranche : c'est un appel systeme atomique
    (CREATE_NEW cote Win32), donc pour une cle donnee exactement UN processus en sort avec
    True, quels que soient l'entrelacement et le nombre de concurrents.

    LE CONTENU N'EST QU'INFORMATIF : un fichier cree puis vide (processus tue entre les deux)
    reserve tout autant, puisque c'est le NOM qui porte l'identifiant. La reservation ne peut
    donc pas etre a moitie faite."""
    chemin = dossier / (cle + ".json")
    try:
        fd = os.open(str(chemin), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except OSError as exc:
        raise Indisponible("reservation de #%s impossible (%s) -- aucun numero n'est rendu sans "
                           "avoir ete PRIS" % (cle, exc)) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as flux:
        json.dump(dict(contexte, cle=cle), flux, indent=2, ensure_ascii=True, sort_keys=True)
    return True


def _identifiants_des_reservations(dossier) -> dict:
    """{cle: {SRC_RESERVATION}} -- les numeros PRIS et pas encore ecrits.

    On lit les NOMS, jamais le contenu : un fichier tronque par un processus tue reserve quand
    meme, et c'est ce qu'on veut -- le cote SUR est de sauter un entier, pas de le reprendre."""
    out = {}
    for chemin in (dossier.glob("*.json") if dossier else ()):
        cle = normaliser(chemin.stem)
        if cle:
            out.setdefault(cle, set()).add(SRC_RESERVATION)
    return out


def lire_reservations(dossier) -> list:
    """[(cle, contexte)] -- pour `--reservations`. Un fichier illisible est RENDU quand meme,
    avec un contexte vide : il RESERVE, et le taire le ferait passer pour libre."""
    out = []
    for chemin in sorted(dossier.glob("*.json")):
        try:
            ctx = json.loads(chemin.read_text(encoding="utf-8"))
            if not isinstance(ctx, dict):
                ctx = {}
        except (OSError, ValueError):
            ctx = {}
        out.append((chemin.stem, ctx))
    return out


def employes(ids_worktrees=None, ids_pr=None, ids_reservations=None) -> dict:
    """{cle normalisee: {sources}} -- l'UNION, toutes positions confondues.

    Depuis #468-r10 l'union couvre AUSSI les deux sources en vol (N1 et N2) : sans elles,
    `--suggere 425` et `--suggere 448` rendaient, le jour de la mesure, deux numeros que des
    dossiers en vol portaient deja. Depuis #468-r11 elle couvre la QUATRIEME source hors-arbre,
    le corps des PR : sans elle, `--suggere 479` rendait `#479-r2`, ouvert par la PR #663 et
    introuvable de `git grep` comme de `git log --all`. Depuis #468-r14 elle couvre la SIXIEME,
    qui n'est pas une lecture de ce qui existe mais de ce qui a ete PRIS : les reservations.
    Les parametres evitent de mesurer deux fois quand l'appelant a deja interroge ces capteurs
    pour imprimer sa portee."""
    if ids_worktrees is None:
        ids_worktrees, _illisibles = _identifiants_des_worktrees(_autres_worktrees())
    if ids_pr is None:
        # Chemin par DEFAUT (tests, appels internes) : la panne n'a AUCUN lecteur ici, donc elle
        # n'est pas dite -- et c'est pourquoi le chemin de PRODUCTION (`suggerer`) mesure lui-meme
        # et passe le resultat : le tri-etat ne vaut que la ou quelqu'un l'imprime.
        prs, _panne = _pull_requests()
        ids_pr = _identifiants_des_pr(prs)
    if ids_reservations is None:
        ids_reservations = _identifiants_des_reservations(_dossier_reservations())
    union = {}
    for part in (_identifiants_du_contenu(), _identifiants_des_noms(),
                 _identifiants_des_commits(), _identifiants_des_refs_hors_head(),
                 ids_worktrees, ids_pr, ids_reservations):
        for k, v in part.items():
            union.setdefault(k, set()).update(v)
    return union


# ------------------------------------------------------------------------------------------
#  LA PORTEE DE LA MESURE -- niveau N3, celui qu'aucune lecture de l'arbre ne ferme
# ------------------------------------------------------------------------------------------
#
# Ce bloc est le LIVRABLE de #468-r10, pas un ornement. Un allocateur qui rend un numero d'air
# sur -- alors qu'il ne peut structurellement pas voir les reservations concurrentes -- est le
# patron qu'on traque partout ailleurs : un capteur qui repond sur ce qu'il regarde en laissant
# croire qu'il a tout regarde.
#
# Il est IMPRIME INCONDITIONNELLEMENT, y compris a zero worktree concurrent : une PR en vol,
# ou un worktree deja supprime dont la branche n'a pas encore ete poussee, porte peut-etre ce
# numero. Le rendre conditionnel reintroduirait le << PASS rassurant >> qu'il existe pour tuer.

#: Marqueur STABLE de l'avertissement -- c'est lui que la garde de retournement cherche dans
#: les deux sorties concurrentes (`test_468_..._offline.py`). Le deplacer casse la garde, et
#: c'est voulu : l'avertissement est un contrat, pas une decoration.
MARQUEUR_ANGLE_MORT = "ANGLE MORT"


def _imprimer_portee(pris, autres, illisibles, pr_lues=None,
                     pr_panne="capteur non sollicite", reserve=None, dossier=None,
                     refus=()) -> None:
    """Dit ce que le numero rendu NE garantit PAS. Voir le commentaire de bloc ci-dessus."""
    print("[468] PORTEE DE LA MESURE -- ce que ce numero ne garantit PAS")
    if reserve:
        print("   RESERVE : %s.json -- creation EXCLUSIVE dans %s" % (reserve, dossier))
        print("   Deux `--suggere` simultanes ne PEUVENT PAS rendre ce numero tous les deux :")
        print("   l'allocation EST le `O_CREAT|O_EXCL`, il n'y a pas de fenetre entre le")
        print("   constat et la prise. Ce n'est pas improbable, c'est impossible.")
        if refus:
            print("   PRIS SOUS NOS PIEDS pendant cette allocation : %s -- la course a EU LIEU"
                  % ", ".join("#" + c for c in refus))
    else:
        print("   NON RESERVE -- ce numero n'a ete qu'OBSERVE, donc un autre appel peut le")
        print("   rendre au meme instant. C'est le regime d'avant #468-r14.")
    print("   %s : la reservation ne vaut que pour CE depot sur CETTE machine (elle vit dans"
          % MARQUEUR_ANGLE_MORT)
    print("   le `.git` commun). Restent invisibles jusqu'a etre ECRITS : un numero choisi SANS")
    print("   passer par cet outil, et un numero pris depuis un autre clone du depot.")
    if pr_lues is None:
        # Tri-etat, meme regle que partout : `null` n'est pas `0`. Un << 0 PR >> fabrique ferait
        # lire << aucune PR ne porte ce numero >>, et aucun repli sur cache ne peut le dire.
        print("   PR GitHub : NON MESUREES -- %s" % pr_panne)
    else:
        print("   PR GitHub : %d lue(s) sur les %d plus recentes ; les plus ANCIENNES ne sont "
              "PAS lues" % (len(pr_lues), GH_LIMITE_PR))
    if autres is None:
        # Tri-etat : jamais rabattu sur 0. Un `0` fabrique ferait lire << personne d'autre >>.
        print("   concurrence : NON MESUREE -- `git worktree list` muet")
    elif autres:
        print("   concurrence : %d autre(s) worktree(s) sur ce depot -> %s"
              % (len(autres), ", ".join(sorted(c.name for c, _b in autres)[:6])))
    else:
        print("   concurrence : 0 autre worktree MESURE -- mais une PR en vol, ou un worktree")
        print("   deja supprime, peut porter ce numero sans que rien ici ne le montre.")
    for chemin, raison in illisibles or ():
        print("   worktree ILLISIBLE (non mesure, pas vide) : %s -- %s" % (chemin.name, raison))
    en_vol = sorted(k for k, src in pris.items()
                    if src and all(s == SRC_REF_EN_VOL or s == SRC_PR
                                   or s.startswith(SRC_WORKTREE) for s in src))
    detail = ", ".join("#%s (%s)" % (k, "/".join(sorted(pris[k]))) for k in en_vol[:6])
    if len(en_vol) > 6:                       # ne pas annoncer 7 et n'en montrer que 6
        detail += ", ... (%d de plus)" % (len(en_vol) - 6)
    print("   deja EN VOL et donc ecartes (hors de ce qui est fusionne) : %d%s"
          % (len(en_vol), " -> " + detail if en_vol else ""))
    print("   -> si d'autres agents travaillent en ce moment, ANNONCE le numero que tu prends.")


def borne_des_taches() -> int:
    """La plus grande racine DEFINIE que `backlog.md` connait -- le sommet de l'espace des taches.

    Le filtre << connue du backlog >> est ce qui ecarte les identifiants de case-doc qui ne sont
    PAS des numeros de tache : `case-1014-*`, `case-1203-*`, `case-1547-*` portent des id
    d'ability ou d'effet. Sans lui, la borne saute a 1547 et la suggestion devient absurde.

    La borne n'a pas besoin d'etre exacte, seulement d'etre <= la vraie frontiere : le balayage
    qui suit avance jusqu'au premier libre. C'est ce qui la rend robuste.
    """
    try:
        txt = BACKLOG.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        txt = ""
    connues = {normaliser(m.group(1)) for m in RE_OCCURRENCE.finditer(txt)}
    defs = definitions_du_backlog(_lignes_backlog()) + definitions_des_case_docs(
        _fichiers_case_docs())
    racines = [int(d.cle) for d in defs if RACINE_PURE.match(d.cle) and d.cle in connues]
    return max(racines) if racines else 0


def _residus_pris(base: str, pris) -> dict:
    """{k: sources} -- TOUS les `<base>r<k>` employes, pas seulement le prefixe contigu.

    C'est le correctif de #468-r11. L'ancien code s'arretait au PREMIER trou et n'imprimait que
    ce qu'il avait traverse : `--suggere 477` annoncait << pris sous #477 : r1..r13 >> alors que
    `r15`, `r16` et `r17` etaient dans `pris` -- deux case-docs, trois probes, un test, des
    messages de commit, une ref non fusionnee et cinq worktrees. Le corpus les VOYAIT ; c'est la
    restitution qui filtrait sans le dire."""
    motif = re.compile(r"^" + re.escape(base) + r"r(\d+)$")
    out = {}
    for cle, src in pris.items():
        m = motif.match(cle)
        if m:
            out[int(m.group(1))] = src
    return out


def _lister_trous(trous, libelle_element) -> str:
    """Rend la liste des trous SANS mentir sur ce qu'elle tronque (#468-r10, meme regle que
    `en_vol` : ne pas annoncer N et n'en montrer que 12)."""
    if not trous:
        return "(aucun)"
    txt = ", ".join(libelle_element(i) for i in trous[:12])
    if len(trous) > 12:
        txt += ", ... (%d de plus)" % (len(trous) - 12)
    return txt


#: PLANCHER DES RACINES NEUVES -- la bande ou une racine ne peut plus heurter un numero de PR.
#:
#: LE DEFAUT N'EST PAS QU'UN NUMERO SOIT PRIS, C'EST QUE LES DEUX COMPTEURS SE SOIENT REJOINTS.
#: `#<n>` designe a la fois une tache et une PR (#468-r8) ; tant que les racines vivaient a ~500
#: et les PR a ~1500, une collision etait accidentelle. MESURE le 2026-08-14 : racine DEFINIE max
#: **1079**, racine la plus haute EN USAGE **1084**, PR max **1088**. Les deux bandes se sont
#: croisees, donc DESORMAIS TOUTE racine neuve heurte une PR -- ce n'est plus un accident, c'est
#: le regime permanent. `#1084` designe deja les deux.
#:
#: POURQUOI UNE CONSTANTE, ET NON `maxPR + marge` : une bande derivee DERIVE, au sens propre --
#: elle monte a chaque appel, donc deux allocations du meme jour ne se comparent plus. Surtout,
#: elle rendrait l'allocation DEPENDANTE DU RESEAU : `gh` muet (mesure #467-r6 : 5 tours sur 8
#: hors budget avant correctif) et plus AUCUN numero ne pourrait etre rendu. Une constante
#: s'evalue hors ligne, se teste, et se relit. Le prix est qu'elle a une date de peremption --
#: d'ou l'alerte ci-dessous, qui la NOMME plutot que de la laisser se degrader en silence.
#:
#: LA VALEUR : au rythme MESURE de ~37 PR/jour, (10000 - 1088) / 37 = ~240 jours de marge. Elle
#: donne en prime un discriminant VISUEL immediat -- une racine neuve a 5 chiffres, une PR en a 4.
PLANCHER_RACINE = 10000

#: PLAFOND DE LA BANDE HISTORIQUE -- la racine la plus haute EN USAGE au moment de la scission
#: (mesure du 2026-08-14 : `#1084`, reserve et cite, au-dessus de la borne DEFINIE de 1079).
#: Il ne sert qu'a la RESTITUTION : sans lui, `suggerer` annoncerait ~8900 << trous libres >>
#: entre les deux bandes, alors que cet intervalle n'a jamais ete alloue et ne le sera jamais.
#: Un compte qui melange un TROU (numero saute, peut-etre pris par une PR en vol) et un
#: INTERVALLE DE BANDE (jamais ouvert) ne veut plus rien dire.
PLAFOND_BANDE_HISTORIQUE = 1084

#: Zone d'ALERTE sous le plancher : on previent quand les PR y entrent, pas quand elles l'ont
#: franchi. ~1000 PR = ~27 jours au rythme mesure -- le temps de relever la bande sans urgence.
MARGE_ALERTE_PLANCHER = 1000


def trous_des_bandes(borne: int, pris: dict) -> list:
    """Les numeros LIBRES a l'interieur des bandes REELLEMENT ouvertes, jamais entre elles.

    L'intervalle `]PLAFOND_BANDE_HISTORIQUE, PLANCHER_RACINE[` n'est pas un trou : personne ne
    l'a jamais alloue. Le compter ferait passer la scission de bande pour ~8900 numeros perdus.
    """
    bandes = [(1, min(borne, PLAFOND_BANDE_HISTORIQUE))]
    if borne > PLANCHER_RACINE:
        bandes.append((PLANCHER_RACINE, borne - 1))
    return [i for lo, hi in bandes for i in range(lo, hi + 1) if str(i) not in pris]


def candidat_observe(base: str, pris: dict, borne: int) -> tuple:
    """(cle, rang) -- le numero que l'OBSERVATION SEULE designe, et rien de plus.

    C'est EXACTEMENT ce que `--suggere` rendait avant #468-r14, extrait en fonction PURE. Deux
    raisons, et la seconde est la plus importante :
      * la boucle d'allocation la rejoue apres chaque candidat perdu, sans dupliquer la regle ;
      * la contre-epreuve peut la lancer en CONCURRENCE et MONTRER qu'elle rend N fois le meme
        numero. Un remede dont on ne peut pas exhiber le defaut qu'il corrige ne se prouve pas.
    """
    if base:
        occupes = _residus_pris(base, pris)
        k = max(occupes) + 1 if occupes else 1
        return normaliser("%sr%d" % (base, k)), k
    # La bande (#468-r8) : une racine neuve part AU-DESSUS de l'espace des numeros de PR, jamais
    # simplement au-dessus de la borne des taches. `max` et non `if` -- une fois la bande entamee,
    # `borne` la depasse et c'est elle qui commande, donc la monotonie tient dans les deux regimes.
    n = max(borne + 1, PLANCHER_RACINE)
    while str(n) in pris:
        n += 1
    return str(n), n


def allouer(base: str, pris: dict, borne: int, dossier: Path, contexte: dict) -> tuple:
    """(cle, rang, refus) -- le numero PRIS, jamais seulement observe.

    L'invariant tient en une phrase : cette fonction ne rend une cle que si `_reserver` a rendu
    True pour elle, et `_reserver` ne peut rendre True qu'a UN processus. Un candidat perdu
    entre dans `pris` comme n'importe quelle autre source occupee -- donc le tour suivant
    respecte la MONOTONIE comme le premier, et `refus` garde la trace de la course pour que le
    lecteur la voie au lieu de la supposer.
    """
    refus = []
    for _ in range(PLAFOND_TENTATIVES):
        cle, rang = candidat_observe(base, pris, borne)
        if _reserver(cle, dossier, contexte):
            return cle, rang, refus
        refus.append(cle)
        pris.setdefault(cle, set()).add(SRC_RESERVATION)
    raise Indisponible("%d candidats consecutifs pris par d'autres processus -- l'allocation "
                       "n'aboutit pas ; AUCUN numero n'est rendu (une garde de terminaison ne "
                       "se degrade pas en suggestion non reservee)" % PLAFOND_TENTATIVES)


def _alerter_plancher(prs, pr_panne) -> None:
    """Dit si la bande des PR approche `PLANCHER_RACINE` -- ou qu'on n'a PAS pu le regarder.

    Une constante de bande a une date de peremption ; un seuil qui se degrade en silence est
    pire que pas de seuil. Le tri-etat est le meme que partout ailleurs ici : `gh` muet ne rend
    PAS un << tout va bien >>, il rend << non verifie >>. L'allocation, elle, reste correcte dans
    les deux cas -- elle est au-dessus du plancher par construction, pas par mesure.
    """
    if prs is None:
        print("   MARGE NON VERIFIEE : les PR n'ont pas ete mesurees (%s). L'allocation reste "
              "au-dessus de %d par CONSTRUCTION, mais la distance a la collision n'a pas ete "
              "regardee." % (pr_panne, PLANCHER_RACINE))
        return
    max_pr = max((int(p.get("number") or 0) for p in prs), default=0)
    reste = PLANCHER_RACINE - max_pr
    if reste <= MARGE_ALERTE_PLANCHER:
        print("   /!\\ ALERTE BANDE : PR max = %d, plancher des racines = %d -- il reste %d "
              "numeros. RELEVER `PLANCHER_RACINE` MAINTENANT : quand les deux se rejoindront, "
              "toute racine neuve heurtera une PR, exactement comme en aout 2026 (#468-r8)."
              % (max_pr, PLANCHER_RACINE, reste))
    else:
        print("   marge de bande : PR max = %d, plancher = %d -> %d numeros d'avance."
              % (max_pr, PLANCHER_RACINE, reste))


def suggerer(parent: str, etiquette: str = "") -> int:
    """ALLOUE un identifiant libre. `parent` vide -> une racine ; sinon un `r<k>` sous `parent`.

    On ne recycle JAMAIS un trou, meme libre : un trou peut etre un numero pris par un agent EN
    VOL dont la PR n'est pas encore fusionnee -- l'arbre ne peut pas le voir. La suggestion est
    donc MONOTONE, et les trous sont seulement LISTES.

    LA MONOTONIE VAUT DANS LES DEUX MODES (#468-r11). Elle ne valait que dans le mode RACINE :
    le mode RESIDU s'arretait au premier trou et le PROPOSAIT, contredisant ce docstring meme.
    Le motif ecrit pour les racines s'applique mot pour mot a un residu -- `#477-r14` peut avoir
    ete alloue par un agent qui n'a encore rien ecrit (N3), ou porte par une PR ouverte dont le
    worktree est deja supprime. Mesure de l'asymetrie : **11 parents sur 218** proposaient un
    trou alors que des residus SUPERIEURS existaient.

    ELLE N'OBSERVE PLUS, ELLE ALLOUE (#468-r14) : le numero rendu est RESERVE par creation
    exclusive avant d'etre imprime, dans le `.git` commun a tous les worktrees. Deux appels
    concurrents ne peuvent donc plus rendre le meme -- ce que la version d'avant NOMMAIT comme
    son angle mort irreductible, et que sept collisions en trois jours ont paye.

    La PORTEE est imprimee dans les deux modes, et apres le numero : c'est ce qui empeche de
    lire une suggestion comme une garantie (#468-r10).
    """
    nom = parent.lstrip("#") if parent else ""
    base = normaliser(nom)
    if nom and not RE_PARENT_SUR.match(base):
        # Le parent devient un NOM DE FICHIER de reservation : ce qui n'est pas alphanumerique
        # est refuse ici, pas traduit en chemin.
        print("[468] REFUS : parent `%s` non conforme (attendu : un identifiant, ex. 420 ou "
              "448-r1). Rien n'a ete reserve." % parent)
        return 2
    dossier = _dossier_reservations()          # LEVE si on ne peut pas ALLOUER -> aucun numero
    contexte = _contexte_de_reservation(etiquette)
    autres = _autres_worktrees()
    ids_wt, illisibles = _identifiants_des_worktrees(autres)
    prs, pr_panne = _pull_requests()
    pris = employes(ids_wt, _identifiants_des_pr(prs), _identifiants_des_reservations(dossier))

    if base:
        _cle, k, refus = allouer(base, pris, 0, dossier, contexte)
        occupes = _residus_pris(base, pris)
        print("[468] LIBRE : #%s-r%d" % (nom, k))
        print("   pris sous #%s : %s"
              % (nom, ", ".join("r%d" % i for i in sorted(occupes)) or "(aucun)"))
        trous = [i for i in range(1, k) if i not in occupes]
        print("   %d trou(s) libre(s) SOUS r%d, NON proposes (un trou peut etre reserve par une "
              "PR en vol) : %s" % (len(trous), k, _lister_trous(trous, lambda i: "r%d" % i)))
        _imprimer_portee(pris, autres, illisibles, prs, pr_panne, _cle, dossier, refus)
        return 0

    borne = borne_des_taches()
    _cle, n, refus = allouer("", pris, borne, dossier, contexte)
    print("[468] LIBRE : #%d" % n)
    print("   borne des taches = %d (plus grande racine DEFINIE que backlog.md connait) ; "
          "%d..%d etaient pris" % (borne, borne + 1, n - 1) if n > borne + 1 else
          "   borne des taches = %d (plus grande racine DEFINIE que backlog.md connait)" % borne)
    trous = trous_des_bandes(borne, pris)
    print("   %d trou(s) libre(s) DANS LES BANDES OUVERTES, NON proposes (un trou peut etre "
          "reserve par une PR en vol) : %s" % (len(trous), _lister_trous(trous, str)))
    print("   bande NEUVE : racines >= %d, au-dessus de l'espace des numeros de PR (#468-r8). "
          "L'intervalle %d..%d n'est PAS un trou -- il n'a jamais ete ouvert."
          % (PLANCHER_RACINE, PLAFOND_BANDE_HISTORIQUE + 1, PLANCHER_RACINE - 1))
    _alerter_plancher(prs, pr_panne)
    print("   corpus : docs/rl + scripts/python + messages de commit + refs hors HEAD + noms "
          "des autres worktrees + corps des PR + RESERVATIONS -- l'UNION, mentions comprises "
          "(%d identifiants)" % len(pris))
    _imprimer_portee(pris, autres, illisibles, prs, pr_panne, _cle, dossier, refus)
    return 0


def lister(dossier) -> int:
    """`--reservations` : ce qui est ALLOUE et pas encore ecrit, avec qui l'a pris.

    Sans cette vue, la sixieme source serait la seule du corpus qu'aucun humain ne peut lire --
    un allocateur dont l'etat est invisible se fait contourner des la premiere surprise."""
    entrees = lire_reservations(dossier)
    print("[468] RESERVATIONS : %d -- %s" % (len(entrees), dossier))
    for cle, ctx in entrees:
        print("   #%-14s %s  %-28s %s" % (cle, ctx.get("quand", "?"),
                                          ctx.get("branche", "?"), ctx.get("pour", "?")))
    if not entrees:
        print("   (aucune) -- personne n'a d'allocation en cours sur ce depot")
    return 0


# ------------------------------------------------------------------------------------------
#  `--gate <ref>` -- NOMMER LA DEFINITION QUE CETTE PR INTRODUIT (#468-r2)
# ------------------------------------------------------------------------------------------
#
# CE QUE CA CHANGE, ET CE QUE CA NE CHANGE PAS. Les etapes 1 et 2 lisent l'ARBRE : elles disent
# << #920-r3 a deux definitions >> sans dire LAQUELLE des deux vient d'arriver. Le lecteur est
# alors l'auteur de la PR, qui doit lui-meme retrouver sa ligne parmi les 1075 du backlog, et
# decider si c'est LUI qui doit renumeroter ou l'autre. `--gate` repond a cette question-la :
# il croise le meme constat avec le diff depuis le MERGE-BASE, et n'accuse QUE ce que la branche
# a ecrit. GAIN DE PRECISION, PAS DE DETECTION -- aucune collision de plus n'est trouvee, et
# c'est voulu : le balayage complet reste le mode par defaut.
#
# LE DIFF PART DU MERGE-BASE, PAS DE `ref`, et la difference n'est pas cosmetique (meme
# raisonnement que `probe_462_live_tests_status._live_in_diff`) : `git diff origin/master`
# compare `origin/master` a mon arbre, donc il ramene EN SENS INVERSE tout ce que les autres
# agents ont pousse depuis mon point de branchement -- sur ce depot, quatre PR mergees en deux
# heures. La gate accuserait alors des lignes que la branche n'a jamais ecrites, ce qui est le
# plus sur moyen de la faire desarmer.
#
# L'ARBRE DE TRAVAIL EST INCLUS (pas de second terme `HEAD`) : un agent qui vient d'ecrire sa
# ligne et n'a pas encore commite doit voir sa propre collision. Une gate qui ne mord qu'apres le
# commit arrive apres le moment ou renommer est gratuit.
#
# L'APPARIEMENT SE FAIT PAR LE TEXTE DE LA LIGNE, PAS PAR SON NUMERO. Un numero de ligne de diff
# ne designe rien de stable : toute insertion au-dessus le decale, et `backlog.md` est le fichier
# le plus partage du depot (36 des 40 dernieres PR). Le texte, lui, identifie la ligne meme si
# elle a bouge.

def _definitions_introduites(ref: str) -> tuple:
    """(base, {textes de lignes AJOUTEES au backlog}, {noms de case-docs AJOUTEES}).

    LEVE `Indisponible` si la ref est inconnue ou le diff injouable -- une gate qui ne sait pas
    ce que la branche a ecrit ne rend PAS un vert. Meme frontiere que partout ailleurs ici."""
    try:
        base = _git(["merge-base", ref, "HEAD"], "`git merge-base %s HEAD`" % ref).strip()
    except Indisponible as exc:
        raise Indisponible("gate impossible (%s) -- une gate qui ne sait pas ce que la branche a "
                           "ecrit ne rend PAS un vert" % exc) from exc
    if not base:
        raise Indisponible("aucun merge-base entre `%s` et HEAD -- la gate ne peut pas savoir ce "
                           "que cette branche a introduit" % ref)
    diff = _git(["diff", "--unified=0", base, "--", "docs/rl/backlog.md"],
                "`git diff %s -- backlog.md`" % base[:8])
    ajoutees = set()
    for ligne in diff.splitlines():
        if ligne.startswith("+") and not ligne.startswith("+++"):
            texte = ligne[1:].strip()
            if texte:
                ajoutees.add(texte)
    statut = _git(["diff", "--name-status", base, "--", "docs/rl"],
                  "`git diff --name-status %s`" % base[:8])
    neuves = set()
    for ligne in statut.splitlines():
        champs = ligne.split("\t")
        if len(champs) >= 2 and champs[0].startswith("A"):
            nom = Path(champs[-1]).name
            if nom.startswith("case-") and nom.endswith(".md"):
                neuves.add(nom)
    return base, ajoutees, neuves


def gate(ref: str) -> int:
    """N'accuse QUE les definitions que cette branche a introduites (#468-r2)."""
    base, ajoutees, neuves = _definitions_introduites(ref)
    lignes = _lignes_backlog()
    if not any(l.strip() for l in lignes):
        print("   FAIL backlog.md absent ou vide alors que docs/rl existe")
        print("[468] VERDICT GATE: FAIL (1)")
        return 1
    defs_b = definitions_du_backlog(lignes)
    defs_c = definitions_des_case_docs(_fichiers_case_docs())
    att = lire_ledger()
    print("[468] GATE depuis le merge-base %s (avec %s)" % (base[:8], ref))
    print("   introduit par cette branche : %d ligne(s) ajoutee(s) a backlog.md, %d case-doc(s) "
          "neuve(s)" % (len(ajoutees), len(neuves)))
    if not ajoutees and not neuves:
        # DIT, jamais tu : un vert sur un diff vide est correct, mais il doit se lire comme
        # << rien a juger >> et non comme << rien a signaler >>.
        print("   cette branche n'introduit AUCUNE definition -- rien a juger ici. Le balayage "
              "complet (argv sans mode) reste le mode qui garde l'arbre.")
    ko = 0
    for cle, ds in etape1_double_ouverture(defs_b):
        if att.get("%s|%s" % (cle, PORTEE_BACKLOG), "").startswith(COLLISION_OUVERTE):
            continue
        miennes = [d for d in ds if d.texte.strip() in ajoutees]
        if not miennes:
            continue
        ko += 1
        print("   FAIL cette branche OUVRE #%s, qui l'est deja :" % ds[0].ident)
        for d in ds:
            print("        %-14s %-18s %s" % ("INTRODUITE ICI" if d in miennes else "DEJA LA",
                                              d.ou, d.texte.strip()[:100]))
        print("        -> renumerote TA ligne : "
              "`python probe_468_collision_numeros.py --suggere %s`"
              % (cle if RACINE_PURE.match(cle) else ""))
    for cle, dbl, cases in etape2_cohabitations(defs_b, defs_c):
        for c in cases:
            if att.get("%s|%s" % (cle, c.ou)):
                continue
            de_la_branche = []
            if dbl.texte.strip() in ajoutees:
                de_la_branche.append("la ligne %s" % dbl.ou)
            if c.ou in neuves:
                de_la_branche.append("la case-doc %s" % c.ou)
            if not de_la_branche:
                continue
            ko += 1
            print("   FAIL #%s : cette branche introduit %s, qui cohabite avec %s"
                  % (dbl.ident, " et ".join(de_la_branche),
                     c.ou if "la case-doc" not in " ".join(de_la_branche) else dbl.ou))
            print("        backlog : %s" % dbl.texte.strip()[:110])
            print("        Si c'est une tranche de la MEME tache : --attester \"%s|%s=<raison>\""
                  % (cle, c.ou))
    print("[468] VERDICT GATE: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


def rapport() -> None:
    defs_b = definitions_du_backlog(_lignes_backlog())
    defs_c = definitions_des_case_docs(_fichiers_case_docs())
    par_cle = {}
    for d in defs_c:
        par_cle.setdefault(d.cle, []).append(d)
    multi = {k: v for k, v in par_cle.items() if len(v) > 1}
    print("[468] INVENTAIRE")
    print("  backlog   : %d definitions (%d ouvertes) sur %d identifiants"
          % (len(defs_b), sum(1 for d in defs_b if d.ouverte),
             len({d.cle for d in defs_b})))
    print("  case-docs : %d fichiers sur %d identifiants" % (len(defs_c), len(par_cle)))
    print("  FORME REFUTEE -- %d identifiants portent >= 2 case-docs (tranches d'une meme tache) :"
          % len(multi))
    for k in sorted(multi, key=lambda x: -len(multi[x]))[:8]:
        print("     %-22s %2d fichiers  ex. %s" % (k, len(multi[k]), multi[k][0].ou))
    probes, tests = _artefacts_de_code()
    print("  FORME REFUTEE -- %d ids a >= 2 probe_<n>_*, %d ids a >= 2 test_<n>_* "
          "(couple _live/_offline)" % (sum(1 for v in probes.values() if len(v) > 1),
                                       sum(1 for v in tests.values() if len(v) > 1)))
    defs_p, _cites = puces_des_case_docs()
    ailleurs = ({d.cle for d in defs_b} | set(par_cle) | {d.cle for d in defs_p})
    seuls = code_seule_position(probes, tests, ailleurs)
    seuls_multi = {k: v for k, v in seuls.items() if len(v) > 1}
    print("     dont le CODE est la SEULE position (#468-r3) : %d identifiant(s), %d a >= 2 "
          "fichiers -- le GISEMENT, que le residu donnait pour vide : %s"
          % (len(seuls), len(seuls_multi),
             ", ".join("#" + k for k in sorted(seuls_multi)[:10]) or "(aucun)"))
    rapport_puces(defs_b, par_cle)
    total, nb, fich = ventiler_occurrences()
    print("  SEPARATION -- %d occurrences `#<n>` dans docs/rl (%d fichiers), %d definitions "
          "(%.1f %%) : le reste est MENTION" % (total, fich, nb, 100.0 * nb / max(total, 1)))


def rapport_puces(defs_b, cases_par_cle) -> None:
    """La QUATRIEME position de definition, EN INVENTAIRE (#468-r7).

    Elle n'est pas bloquante, et la raison est mesuree, pas prudente : voir le commentaire de
    bloc de `puces_des_case_docs`. Ce qui suit est ce qu'un humain doit pouvoir LIRE -- une
    collision qui ne se manifesterait que la se verrait ici, meme si aucun `rc` ne la crie."""
    defs_p, cites = puces_des_case_docs()
    ouvertes = [d for d in defs_p if d.ouverte]
    par_cle = {}
    for d in ouvertes:
        par_cle.setdefault(d.cle, []).append(d)
    ouverts_b = {d.cle for d in defs_b if d.ouverte}
    tous_b = {d.cle for d in defs_b}
    sans_ailleurs = sorted(k for k in par_cle if k not in tous_b and k not in cases_par_cle)
    doubles = {k: v for k, v in par_cle.items() if len({d.ou.split(":")[0] for d in v}) > 1}
    #: LA FORME QUI RENDRAIT LE CRITERE BLOQUANT : deux dossiers, aucun proprietaire. Elle est
    #: comptee A CHAQUE RUN pour qu'on sache le jour ou elle cesse d'etre a zero.
    orphelines = {k: v for k, v in doubles.items() if k in sans_ailleurs}
    print("  4e POSITION (non bloquante) -- %d puce(s) de section << Residus >> : %d definition(s) "
          "(%d ouverte(s)) + %d citation(s) ecartee(s) par le proprietaire"
          % (len(defs_p) + len(cites), len(defs_p), len(ouvertes), len(cites)))
    print("     %d identifiant(s) ouvert(s) ici ; %d aussi ouverts au backlog ; %d SANS aucune "
          "autre position" % (len(par_cle), len(set(par_cle) & ouverts_b), len(sans_ailleurs)))
    print("     %d identifiant(s) a >= 2 puces definissantes dans DES FICHIERS DIFFERENTS "
          "(mesure : re-citations legitimes)" % len(doubles))
    print("     dont %d SANS proprietaire -- la seule forme qui serait BLOQUANTE : %s"
          % (len(orphelines), ", ".join("#" + k for k in sorted(orphelines)) or "(aucune)"))


# ================================ l'ECHANTILLON ADVERSARIAL de sujets de commit (#486-r18)
#: Ou vit l'echantillon GELE. Il est VERSIONNE, donc declarable comme un CHEMIN -- c'est tout
#: l'objet de #486-r18.
SUJETS_GELES = REPO / "scripts" / "ratchets-468-sujets-de-commit.txt"

#: La SENTINELLE qui separe l'en-tete des donnees, et elle n'est PAS decorative.
#:
#: ⚠ LA CONVENTION HABITUELLE `#` = COMMENTAIRE AMPUTERAIT EXACTEMENT CE QUI COMPTE. Nos sujets
#: de commit COMMENCENT couramment par le numero (`#175-e / #175-r : ...`) : un lecteur qui
#: filtre les lignes commencant par `#` jette les sujets les PLUS adversariaux -- ceux dont la
#: premiere colonne ressemble le plus a une definition de backlog -- et rend un corpus ampute
#: qui se lit comme un vert. Faute commise a la premiere ecriture de ce mode, vue en RELISANT
#: l'artefact genere. Tout ce qui suit la sentinelle est DONNEE, verbatim.
SENTINELLE_SUJETS = "# --- SUJETS (tout ce qui suit est DONNEE, `#` compris) ---"


def geler_sujets_de_commit() -> int:
    """(Re)ecrit l'echantillon adversarial : tous les sujets de commit portant un `#`, dedupes.

    POURQUOI GELER, ET CE QUE CA COUTE (#486-r18)
    ----------------------------------------------
    `test_468_collision_numeros_offline.py` soumet a `definitions_du_backlog` des SUJETS DE
    COMMIT reels, qui doivent tous etre lus comme des MENTIONS. C'est la contre-epreuve la plus
    exigeante du critere -- et elle lisait `git log` EN DIRECT. Or l'historique bouge a chaque
    commit : sous toute selection par diff, l'echantillon avait change par construction, d'ou un
    `toujours: True` qui rejouait les **140,9 s** du fichier a CHAQUE passe.

    L'HISTORIQUE PASSE EST IMMUABLE : le geler ne perd rien de ce qu'il portait. Mesure du
    2026-08-08 : la fenetre vivante de 400 commits donnait **374** sujets distincts ; l'historique
    COMPLET en donne **3 034** -- l'echantillon gele est donc ~8x plus RICHE que celui qu'il
    remplace, et non pas appauvri. Ce qu'on perd est borne et nomme : les formes de sujet
    INVENTEES APRES le gel. Elles reviennent au premier `--geler-sujets`, et le fichier porte le
    commit et la date de son gel pour que sa peremption se LISE au lieu de se deviner.
    """
    sujets = _git(["log", "--format=%s", "--no-merges"], "git log (sujets)").splitlines()
    avec = sorted({s.strip() for s in sujets if "#" in s and s.strip()})
    if not avec:
        print("[468] REFUS : `git log` n'a rendu AUCUN sujet portant un `#` -- un echantillon "
              "adversarial VIDE passerait pour un vert. Rien n'est ecrit.")
        return 2
    tete = _git(["rev-parse", "HEAD"], "git rev-parse").strip()[:12]
    entete = [
        "# ECHANTILLON ADVERSARIAL de sujets de commit (#486-r18) -- GENERE, jamais fusionne a",
        "# la main : REGENERER (`python scripts/python/probe_468_collision_numeros.py",
        "# --geler-sujets`) en cas de conflit.",
        "#",
        "# A QUOI IL SERT. `definitions_du_backlog` doit lire CHACUNE de ces lignes comme une",
        "# MENTION, jamais comme une DEFINITION. C'est le corpus reel qui a le plus de chances",
        "# de faire deraper le critere de position, parce que nos sujets de commit citent des",
        "# numeros a longueur de journee et empruntent parfois la ponctuation du backlog.",
        "#",
        "# POURQUOI GELE. Lu en direct, il rendait la contre-epreuve NON BORNABLE (l'historique",
        "# bouge a chaque commit), donc `toujours: True`, donc 140,9 s rejouees a chaque passe.",
        "# L'historique PASSE est immuable : le geler ne perd que les formes INVENTEES APRES.",
        "#",
        "# gele a HEAD=%s -- %d sujet(s) distinct(s) portant un `#`" % (tete, len(avec)),
        SENTINELLE_SUJETS,
    ]
    SUJETS_GELES.write_text("\n".join(entete + avec) + "\n", encoding="utf-8")
    print("[468] echantillon gele : %d sujet(s) distinct(s) (dont %d COMMENCANT par `#`) -> %s"
          % (len(avec), sum(1 for s in avec if s.startswith("#")),
             SUJETS_GELES.relative_to(REPO).as_posix()))
    return 0


def lire_sujets_geles() -> list:
    """Les sujets de l'echantillon gele. LEVE si absent ou vide -- jamais une liste vide.

    Un echantillon adversarial vide validerait tout : c'est exactement le faux vert que la
    doctrine de ce depot nomme << un recenseur ne peut pas rendre zero sur ce qu'il ne visite
    pas >>. Le contrat est donc : present et non vide, ou `Indisponible`.

    La lecture se fait APRES la sentinelle, et verbatim : voir `SENTINELLE_SUJETS` pour la
    raison -- filtrer les `#` amputerait le corpus de ses lignes les plus adversariales.
    """
    try:
        lignes = SUJETS_GELES.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Indisponible("echantillon de sujets de commit illisible (%s) -- REGENERER : "
                           "`probe_468_collision_numeros.py --geler-sujets`" % exc) from exc
    if SENTINELLE_SUJETS not in lignes:
        raise Indisponible("echantillon de sujets de commit SANS SENTINELLE -- format perime, "
                           "REGENERER : `probe_468_collision_numeros.py --geler-sujets`")
    sujets = [l for l in lignes[lignes.index(SENTINELLE_SUJETS) + 1:] if l.strip()]
    if not sujets:
        raise Indisponible("echantillon de sujets de commit VIDE -- il validerait tout")
    return sujets


# ------------------------------------------------------------------------------------------

def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="ne joue QUE l'auto-test des detecteurs, en detail")
    ap.add_argument("--report", action="store_true",
                    help="inventaire complet, y compris les formes REFUTEES comme criteres")
    ap.add_argument("--attester", metavar="ENTREE",
                    help="ajoute au ledger : \"<ident>|<fichier>=<raison>\" (raison OBLIGATOIRE)")
    ap.add_argument("--suggere", metavar="PARENT", nargs="?", const="",
                    help="ALLOUE un identifiant libre (et le RESERVE) : sans argument une "
                         "racine, avec un parent (ex. 420) le plus petit `r<k>` libre sous lui")
    ap.add_argument("--pour", metavar="SUJET", default="",
                    help="etiquette la reservation (ce que la tranche va traiter)")
    ap.add_argument("--reservations", action="store_true",
                    help="liste les numeros ALLOUES et pas encore ecrits, avec qui les a pris")
    ap.add_argument("--gate", metavar="REF",
                    help="n'accuse QUE les definitions introduites depuis le merge-base avec REF "
                         "(ex. origin/master) -- gain de precision, pas de detection (#468-r2)")
    ap.add_argument("--racine", metavar="CHEMIN",
                    help="vise un AUTRE arbre (contre-epreuve bout-en-bout sur depot jetable)")
    ap.add_argument("--geler-sujets", action="store_true", dest="geler_sujets",
                    help="(re)ecrit l'echantillon adversarial de sujets de commit (#486-r18)")
    args = ap.parse_args(argv)

    if args.geler_sujets:
        return geler_sujets_de_commit()

    if args.racine:
        viser(Path(args.racine))

    if args.attester:
        if "=" not in args.attester:
            print("[468] USAGE : --attester \"<ident>|<fichier>=<raison>\"")
            return 2
        cle, raison = args.attester.split("=", 1)
        if not raison.strip():
            print("[468] REFUS : la raison est OBLIGATOIRE -- une attestation sans raison est un"
                  " blanc-seing, et c'est exactement ce que ce cliquet garde.")
            return 2
        att = lire_ledger()
        att[cle.strip()] = raison.strip()
        ecrire_ledger(att)
        print("[468] atteste : %s -> %s" % (cle.strip(), raison.strip()))
        return 0

    if args.gate:
        return gate(args.gate)

    if args.reservations:
        return lister(_dossier_reservations())

    if args.suggere is not None:
        return suggerer(args.suggere, args.pour)

    if args.report:
        rapport()
        return 0

    print("[468] racine : %s" % REPO)
    mauvais = self_test(args.verbose or args.self_test)
    print("[468] etape 0a : auto-test des detecteurs -- %d/%d cas, %d en echec"
          % (len(CAS) + len(CAS_NOMS) - len(mauvais), len(CAS) + len(CAS_NOMS), len(mauvais)))
    for nom in mauvais:
        print("   FAIL auto-test : %s" % nom)
    if args.self_test:
        print("[468] VERDICT: %s" % ("PASS" if not mauvais else "FAIL (%d)" % len(mauvais)))
        return 0 if not mauvais else 1

    lignes = _lignes_backlog()
    # `not lignes` NE SUFFIT PAS : `"\n".splitlines()` rend `['']`, qui est VRAI. Un backlog
    # reduit a du blanc passait donc pour mesure -- trou trouve par la contre-epreuve, pas a
    # la relecture.
    if not any(l.strip() for l in lignes):
        # `docs/rl` EXISTE (sinon `Indisponible`) mais le backlog est absent ou vide : c'est un
        # fait sur le CONTENU du depot, donc un ROUGE -- pas une panne de montage.
        print("   FAIL backlog.md absent ou vide alors que docs/rl existe -- le registre des "
              "numeros a disparu")
        print("[468] VERDICT: FAIL (1)")
        return 1
    defs_b = definitions_du_backlog(lignes)
    defs_c = definitions_des_case_docs(_fichiers_case_docs())

    total, nb_defs, fich = ventiler_occurrences()
    part = 100.0 * nb_defs / max(total, 1)
    print("[468] etape 0b : %d occurrences `#<n>` dans docs/rl (%d fichiers) ; %d DEFINITIONS "
          "(%.1f %%), le reste est MENTION" % (total, fich, nb_defs, part))
    ko0b = 0
    if args.racine:
        # Sur un arbre JETABLE, le corpus est minuscule par construction : le garde d'indigence
        # rougirait pour la MAUVAISE raison et masquerait le verdict des etapes 1 et 2.
        print("   (--racine : garde d'indigence du corpus DESACTIVE, il ne vaut que sur le depot)")
    elif total < 500 or nb_defs == 0:
        print("   FAIL corpus indigent (%d occurrences, %d definitions) -- le critere n'est pas "
              "confronte : un balayage qui rend zero se lit << rien a signaler >>" % (total, nb_defs))
        ko0b = 1
    elif part > 50.0:
        print("   FAIL %.1f %% des occurrences sont lues comme des DEFINITIONS -- le detecteur a "
              "cesse de separer definition et mention" % part)
        ko0b = 1

    att = lire_ledger()

    doubles = etape1_double_ouverture(defs_b)
    # Une attestation d'etape 1 porte la PORTEE `@backlog` : attester une COHABITATION
    # (etape 2) ne doit JAMAIS dispenser de la double ouverture -- ce sont deux constats.
    connues = {k for k in doubles_cles(doubles)
               if att.get("%s|%s" % (k, PORTEE_BACKLOG), "").startswith(COLLISION_OUVERTE)}
    neufs = [(k, v) for k, v in doubles if k not in connues]
    print("[468] etape 1 : %d identifiant(s) a >= 2 definitions OUVERTES au backlog "
          "(%d deja au ledger)" % (len(doubles), len(doubles) - len(neufs)))
    for k, v in doubles:
        marque = "FAIL" if k not in connues else "CONNU"
        print("   %s #%s : %d definitions ouvertes" % (marque, v[0].ident, len(v)))
        for d in v:
            print("        %-18s %s" % (d.ou, d.texte.strip()[:110]))
        if k in connues:
            print("        -> %s" % att["%s|%s" % (k, PORTEE_BACKLOG)])
        else:
            print("        Deux lignes OUVERTES = deux taches sous un numero. Si c'est bien une")
            print("        collision et qu'elle est DEJA LIVREE, l'arbitrage revient a")
            print("        l'orchestrateur -- fige-la : --attester \"%s|%s=%s -- <ce que porte"
                  " chaque ligne>\"" % (k, PORTEE_BACKLOG, COLLISION_OUVERTE))

    cohab = etape2_cohabitations(defs_b, defs_c)
    manquantes = []
    for k, dbl, cases in cohab:
        for c in cases:
            if not att.get("%s|%s" % (k, c.ou)):
                manquantes.append((k, dbl, c))
    print("[468] etape 2 : %d cohabitation(s) ouvert-x-case-doc, %d NON attestee(s)"
          % (sum(len(c) for _k, _d, c in cohab), len(manquantes)))
    for k, dbl, c in manquantes:
        print("   FAIL #%s : la ligne OUVERTE %s cohabite avec la case-doc %s"
              % (dbl.ident, dbl.ou, c.ou))
        print("        backlog : %s" % dbl.texte.strip()[:120])
        print("        Si c'est une tranche de la MEME tache, atteste-la :")
        print("          python probe_468_collision_numeros.py --attester \"%s|%s=<raison>\""
              % (k, c.ou))
        print("        Si c'est un AUTRE sujet, le numero est PRIS : prends-en un libre AVANT de"
              " livrer (renommer apres livraison est une reecriture d'historique).")

    # Les collisions figees se REPETENT a chaque run. Une collision qu'on cesse de voir est une
    # collision qu'on cesse de traiter : le ledger n'est pas un silencieux, c'est une ligne de base.
    ouvertes = sorted((c, v) for c, v in att.items() if v.startswith(COLLISION_OUVERTE))
    if ouvertes:
        print("[468] COLLISIONS CONNUES ET NON RESOLUES (%d) -- arbitrage d'orchestrateur, "
              "non bloquant ici :" % len(ouvertes))
        for c, v in ouvertes:
            print("   #%s  %s" % (c.split("|", 1)[0], v))

    ko = len(mauvais) + ko0b + len(neufs) + len(manquantes)
    print("[468] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


def _main_tri_etat(argv) -> int:
    """`main`, plus la traduction du MONTAGE en `99` (contrat de banque, #471).

    `INDISPONIBLE` est BLOQUANT : il ne fait rien taire, il change l'ACCUSE. Sans ce chemin, une
    panne de montage sortait en `rc=1` -- exactement le rouge de gisement pour panne d'outil que
    `#471` a mesure sur `probe_457:s3`."""
    try:
        return main(argv)
    except Indisponible as exc:
        print("[468] INDISPONIBLE -- %s" % exc)
        print("[468] rc=%d : RIEN n'a ete mesure. Ce n'est PAS un verdict sur le depot."
              % EX_INDISPONIBLE)
        return EX_INDISPONIBLE


if __name__ == "__main__":
    sys.exit(_main_tri_etat(sys.argv[1:]))
