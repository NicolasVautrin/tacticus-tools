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

MESURE DE SEPARATION (etape 0b, rejouee a chaque run) : sur `docs/rl/**`, 6546 occurrences `#<n>`
pour 831 DEFINITIONS -- 12,7 %. Un critere par simple presence rougirait sur la quasi-totalite du
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
  * << un `<n>` a la fois dans une ligne OUVERTE et dans une case-doc >> -> **7** cohabitations,
    dont **6 legitimes** (tache-parapluie qui livre ses items, ou dossier RE-OUVERT sur le meme
    sujet). Quatre criteres derives ont ete essayes pour separer les 6 du vrai positif -- << la
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

ASCII only (console Windows cp1252).
Usage:
    python probe_468_collision_numeros.py [-v]
    python probe_468_collision_numeros.py --report
    python probe_468_collision_numeros.py --self-test
    python probe_468_collision_numeros.py --attester "<ident>|<fichier>=<raison>"
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
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("   ATTENTION ledger illisible (%s) -- traite comme VIDE, donc BLOQUANT" % exc)
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
    try:
        return BACKLOG.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


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
    if not lignes:
        print("   FAIL backlog.md illisible ou vide -- le cliquet ne peut RIEN mesurer")
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
