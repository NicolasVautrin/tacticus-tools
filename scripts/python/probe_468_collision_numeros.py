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

ASCII only (console Windows cp1252).
Usage:
    python probe_468_collision_numeros.py [-v]
    python probe_468_collision_numeros.py --report
    python probe_468_collision_numeros.py --self-test
    python probe_468_collision_numeros.py --attester "<ident>|<fichier>=<raison>"
    python probe_468_collision_numeros.py --suggere            # une RACINE libre
    python probe_468_collision_numeros.py --suggere 420        # un RESIDU libre sous #420
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
DOCS_RL = REPO / "docs" / "rl"
BACKLOG = DOCS_RL / "backlog.md"
LEDGER = REPO / "scripts" / "ratchets-468-numeros-attestes.json"

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

#: (a) PREMIERE cellule d'une ligne de tableau. Le `~~` de part et d'autre = entree BARREE.
RE_LIGNE_TABLEAU = re.compile(r"^\|\s*(~~)?\s*[`*]*\s*#(" + ID + r")\s*[`*]*\s*(~~)?\s*\|")
#: (b) TETE d'une puce de premier niveau (`- `, `* `), gras et backticks tolerés.
#:     ⚠ ANCREE en debut de ligne SANS espace de tete : une puce INDENTEE est une continuation
#:     ou une sous-puce, jamais l'ouverture d'un dossier.
RE_TETE_DE_PUCE = re.compile(r"^[-*]\s+(?:~~)?\s*(?:\*\*)?\s*(?:~~)?\s*[`]?#(" + ID + r")[`]?")
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

    Toute panne de `git` leve `Indisponible` -- jamais un ensemble VIDE, qui ferait suggerer un
    numero deja pris. C'est la meme frontiere que `host_inputs.py` : `null` n'est pas `0`.
    """
    out = {}
    for m in re.finditer(RE_TOKEN_LARGE, _git(["log", "--format=%s%n%b", "--no-merges"],
                                              "`git log`")):
        out.setdefault(normaliser(m.group(0)[1:]), set()).add("git log")
    return out


#: Libelles de PROVENANCE des deux sources EN VOL (niveaux N1 et N2 du docstring). Ils sont
#: le discriminant de `_imprimer_portee` : un identifiant dont TOUTES les sources sont en vol
#: n'est PAS encore fusionne, et c'est exactement ce qu'un `--suggere` d'hier aurait propose.
SRC_REF_EN_VOL = "ref non fusionnee"
SRC_WORKTREE = "worktree "


def _identifiants_des_refs_hors_head() -> dict:
    """{cle: {SRC_REF_EN_VOL}} -- N1 : les commits que `HEAD` n'atteint PAS.

    `--not HEAD` est ce qui rend la provenance gratuite ET la mesure bon marche : sur 363 refs,
    ce qui reste hors de la lignee courante est une poignee de commits. Un `--all` nu couterait
    autant mais melangerait les deux origines, et on ne pourrait plus DIRE ce qui est en vol.
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


def employes(ids_worktrees=None) -> dict:
    """{cle normalisee: {sources}} -- l'UNION, toutes positions confondues.

    Depuis #468-r10 l'union couvre AUSSI les deux sources en vol (N1 et N2) : sans elles,
    `--suggere 425` et `--suggere 448` rendaient, le jour de la mesure, deux numeros que des
    dossiers en vol portaient deja. Le parametre evite de globber deux fois quand l'appelant
    a deja mesure la concurrence pour l'imprimer."""
    if ids_worktrees is None:
        ids_worktrees, _illisibles = _identifiants_des_worktrees(_autres_worktrees())
    union = {}
    for part in (_identifiants_du_contenu(), _identifiants_des_noms(),
                 _identifiants_des_commits(), _identifiants_des_refs_hors_head(),
                 ids_worktrees):
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


def _imprimer_portee(pris, autres, illisibles) -> None:
    """Dit ce que le numero rendu NE garantit PAS. Voir le commentaire de bloc ci-dessus."""
    print("[468] PORTEE DE LA MESURE -- ce que ce numero ne garantit PAS")
    print("   %s : un agent qui vient de recevoir un numero et n'a RIEN encore ecrit est"
          % MARQUEUR_ANGLE_MORT)
    print("   invisible de toute lecture de l'arbre. Deux `--suggere` lances au meme instant")
    print("   depuis deux worktrees rendent le MEME numero. Reserver le supprimerait, mais")
    print("   exigerait commit+push -- ce qui serialiserait l'allocation entre agents.")
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
                    if src and all(s == SRC_REF_EN_VOL or s.startswith(SRC_WORKTREE)
                                   for s in src))
    print("   deja EN VOL et donc ecartes (hors de ce qui est fusionne) : %d%s"
          % (len(en_vol), " -> " + ", ".join("#%s (%s)" % (k, "/".join(sorted(pris[k])))
                                             for k in en_vol[:6]) if en_vol else ""))
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


def suggerer(parent: str) -> int:
    """Imprime un identifiant LIBRE. `parent` vide -> une racine ; sinon un `r<k>` sous `parent`.

    On ne recycle JAMAIS un trou sous la borne, meme libre : un trou peut etre un numero pris
    par un agent EN VOL dont la PR n'est pas encore fusionnee -- l'arbre ne peut pas le voir.
    La suggestion est donc MONOTONE, et les trous sont seulement LISTES.

    La PORTEE est imprimee dans les deux modes, et apres le numero : c'est ce qui empeche de
    lire une suggestion comme une garantie (#468-r10).
    """
    autres = _autres_worktrees()
    ids_wt, illisibles = _identifiants_des_worktrees(autres)
    pris = employes(ids_wt)
    if parent:
        base = normaliser(parent.lstrip("#"))
        k = 1
        while "%sr%d" % (base, k) in pris:
            k += 1
        print("[468] LIBRE : #%s-r%d" % (parent.lstrip("#"), k))
        occupes = [i for i in range(1, k) if "%sr%d" % (base, i) in pris]
        print("   pris sous #%s : %s" % (parent.lstrip("#"),
                                         ", ".join("r%d" % i for i in occupes) or "(aucun)"))
        _imprimer_portee(pris, autres, illisibles)
        return 0

    borne = borne_des_taches()
    n = borne + 1
    while str(n) in pris:
        n += 1
    print("[468] LIBRE : #%d" % n)
    print("   borne des taches = %d (plus grande racine DEFINIE que backlog.md connait) ; "
          "%d..%d etaient pris" % (borne, borne + 1, n - 1) if n > borne + 1 else
          "   borne des taches = %d (plus grande racine DEFINIE que backlog.md connait)" % borne)
    trous = [i for i in range(1, borne) if str(i) not in pris]
    print("   %d trou(s) libre(s) SOUS la borne, NON proposes (un trou peut etre reserve par une "
          "PR en vol) : %s" % (len(trous), ", ".join(str(i) for i in trous[:12]) or "(aucun)"))
    print("   corpus : docs/rl + scripts/python + messages de commit + refs hors HEAD + noms "
          "des autres worktrees -- l'UNION, mentions comprises (%d identifiants)" % len(pris))
    _imprimer_portee(pris, autres, illisibles)
    return 0


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
    total, nb, fich = ventiler_occurrences()
    print("  SEPARATION -- %d occurrences `#<n>` dans docs/rl (%d fichiers), %d definitions "
          "(%.1f %%) : le reste est MENTION" % (total, fich, nb, 100.0 * nb / max(total, 1)))


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
                    help="DONNE un identifiant libre : sans argument une racine, avec un parent "
                         "(ex. 420) le plus petit `r<k>` libre sous lui")
    ap.add_argument("--racine", metavar="CHEMIN",
                    help="vise un AUTRE arbre (contre-epreuve bout-en-bout sur depot jetable)")
    args = ap.parse_args(argv)

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

    if args.suggere is not None:
        return suggerer(args.suggere)

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
