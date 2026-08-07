# -*- coding: utf-8 -*-
"""#526 -- INVENTAIRE CLASSE des residus du backlog : l'ETAGE MECANIQUE, re-derivable.

Ce qu'il fait, et ce qu'il ne fait pas
--------------------------------------
Il reproduit la partie MECANIQUE du classement de
`docs/rl/case-526-inventaire-classe-des-residus-moteur.md` : parse du backlog,
extraction des ANCRES de chaque entree, puis quatre axes -- PERIMETRE (moteur /
harnais), FRAICHEUR, NATURE, CONFRONTABILITE -- et un ordre de priorite.

Il ne rend JAMAIS un verdict par defaut. Chaque axe a une valeur d'ignorance
explicite, et c'est elle qui sort quand aucune epreuve ne mord. Un signal qui
rendrait `VIVANT` faute de mesure serait un mensonge.

Trois principes, tous payes par une faute deja commise
------------------------------------------------------
1. On interroge l'artefact qui DEFINIT le fait (`ABILITY_CLASSES` pour
   << portee ? >>, les PR mergees pour << livre ? >>, l'arbre pour
   << ce fichier existe ? >>), jamais un document qui le RESUME.
2. Tout grep dans un document a SECTIONS est BORNE a sa section. `backlog.md`
   porte sept sections, dont une nommee << Fiches PERIMEES -- NE PAS
   re-dispatcher >> : un match non borne melangerait les deux statuts.
3. Un capteur muet rend `None` (NON MESURE), jamais un zero. `gh` absent ne
   veut pas dire << aucune PR ne ferme ce residu >>.

Une mesure ECARTEE, et pourquoi elle l'est
------------------------------------------
<< Le symbole natif cite est-il present dans `engine/**` ? >> a ete mesuree puis
RETIREE du verdict : sur le nom COURT elle rend 159 presents sur 161 (aucun
pouvoir discriminant), et sur le symbole COMPLET 135/161 -- mais nos ports
CITENT verbatim le symbole qu'ils declarent NON porte (`CLAUDE.md`, regle
d'ecriture), donc la presence ne dit rien du portage. `--mesures-ecartees`
la re-joue et imprime les deux chiffres : c'est un resultat, pas un oubli.

Usage
-----
    python probe_526_inventaire_residus.py                  # resume ASCII
    python probe_526_inventaire_residus.py --tsv <chemin>   # table complete
    python probe_526_inventaire_residus.py --detail <id>    # une entree
    python probe_526_inventaire_residus.py --top 20         # classement priorise
    python probe_526_inventaire_residus.py --portee         # ce que la mesure NE voit pas
    python probe_526_inventaire_residus.py --mesures-ecartees
"""
from __future__ import annotations

import argparse
import ast
import collections
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / "scripts" / "python"
BACKLOG = ROOT / "docs" / "rl" / "backlog.md"
ENGINE = PY / "engine"
HANDLER = ENGINE / "runner" / "abilities" / "handler.py"

# La SEULE section qui porte des taches dispatchables. Les six autres
# ("Residus documentes", "Fiches PERIMEES -- NE PAS re-dispatcher", les blocs
# #321 / #289, les cliquets) portent un autre statut.
SECTION_TACHES = "## Taches ouvertes"

RE_ROW = re.compile(r"^\|\s*(#[A-Za-z0-9\-]+)\s*\|")
RE_SECTION = re.compile(r"^## ")

# ---------------------------------------------------------------- etage 0
_ACCENTS = {"à": "a", "â": "a", "é": "e", "è": "e", "ê": "e", "ë": "e",
            "î": "i", "ï": "i", "ô": "o", "ù": "u", "û": "u", "ü": "u",
            "ç": "c", "É": "E", "È": "E", "Ê": "E", "À": "A", "Î": "I"}


def sans_accents(s: str) -> str:
    return "".join(_ACCENTS.get(c, c) for c in s)


class Entree:
    def __init__(self, ident, ligne, cells, brut):
        self.ident = ident
        self.ligne = ligne
        self.brut = brut
        # Les cellules d'une ligne '| a | b | c | d |' sortent avec un vide en
        # tete ET en queue : le titre est en position 2, pas 1.
        self.titre = cells[2] if len(cells) > 2 else ""
        self.tag = cells[3] if len(cells) > 3 else ""
        self.point_entree = cells[4] if len(cells) > 4 else ""
        self.symboles: list[str] = []
        self.ids: list[int] = []
        self.noms_ability: list[str] = []
        self.chemins: list[str] = []
        self.probes: list[str] = []
        self.perimetre = self.perim_raison = ""
        self.fraicheur = self.frai_raison = ""
        self.nature = self.nat_raison = ""
        self.confront = self.conf_raison = ""
        self.affirme_absence = False
        self.ecart_chiffre = False
        self.bloque_reinject = False
        self.score = 0.0


def parser_backlog(chemin: Path = BACKLOG) -> list[Entree]:
    lignes = chemin.read_text(encoding="utf-8").splitlines()
    debut = fin = None
    for i, l in enumerate(lignes):
        if RE_SECTION.match(l):
            if debut is None and sans_accents(l).strip().startswith(SECTION_TACHES):
                debut = i
            elif debut is not None and i > debut:
                fin = i
                break
    if debut is None:
        raise SystemExit("section '%s' introuvable dans %s" % (SECTION_TACHES, chemin))
    if fin is None:
        fin = len(lignes)
    out = []
    for i in range(debut, fin):
        m = RE_ROW.match(lignes[i])
        if m:
            cells = [c.strip() for c in lignes[i].split("|")]
            out.append(Entree(m.group(1), i + 1, cells, lignes[i]))
    return out


# ---------------------------------------------------------------- etage 1
RE_SYMBOLE = re.compile(r"\b([A-Za-z_][\w.<>]*\$\$[A-Za-z_][\w.<>]*)")
RE_ID_NOM = re.compile(r"\b(1[0-9]{3})\s+`?([A-Z][A-Za-z0-9_]{3,})")
RE_CHEMIN = re.compile(r"`([^`]*?\.(?:py|ts|md|json|tsv))`")
RE_PROBE = re.compile(r"\b((?:probe|test|migrate|audit|prototype)_[A-Za-z0-9_]+)")


def extraire_ancres(e: Entree) -> None:
    t = e.brut
    e.symboles = sorted(set(RE_SYMBOLE.findall(t)))
    couples = RE_ID_NOM.findall(t)
    e.ids = sorted({int(a) for a, _ in couples})
    e.noms_ability = sorted({n for _, n in couples})
    e.chemins = sorted({c.strip() for c in RE_CHEMIN.findall(t)})
    e.probes = sorted(set(RE_PROBE.findall(t)))


# ---------------------------------------------------------------- etage 2
# Discriminant : l'OBJET de la divergence. MOTEUR si le reparer change le
# comportement du moteur EN BATAILLE. Approxime par une ancre forte (symbole
# natif, id d'ability, chemin engine/) ; a defaut par un lexique, et le lexique
# HARNAIS l'emporte sur le lexique moteur FAIBLE (un residu qui parle d'un
# cliquet et emploie le mot << degat >> reste un residu de cliquet).
MOTS_HARNAIS = (
    "cliquet", "empreinte", "cache de verdict", "worktree", "banque",
    "pytest", "collecte", "declencheur", "xdist", "gh pr", "pull request",
    "frida/hooks", "reinject", "dispatch", "orchestrateur", "ledger",
    "numero", "collision", "loop_status", "ghidra-projects", "rebase",
    "case-doc", "backlog", "hook stop", "seuil", "balayage", "recenseur",
    "import differe", "differes", "baril", "sondes", "nommage", "renommer",
    "registre host", "state-file", "harnais", "montage", "citation",
)
MOTS_MOTEUR_FAIBLES = (
    "natif", "decompile", "degat", "attaque", "caster", "cible", "tuile",
    "trait ", "effet", "playbook", "dsl", "ability", "bataille", "board",
    "unite", "pathfind", "porteur", "cast", "spawn", "armure", "crit",
)


def classer_perimetre(e: Entree) -> None:
    """Precedence par SCORE, pas par ancre forte.

    La regle << une ancre forte l'emporte >> a ete mesuree FAUSSE : #486-r21
    (empreinte des declencheurs) et #485-r1-r1-r2 (contre-epreuve morte d'un
    probe) citent `engine/...` et remontaient en tete du classement MOTEUR. Un
    residu d'outillage qui NOMME un fichier moteur reste un residu d'outillage.
    Quand les deux camps s'equilibrent, on rend MIXTE et on appelle la lecture
    humaine -- on ne tranche pas au hasard.
    """
    bas = sans_accents(e.brut).lower()
    pe = sans_accents(e.point_entree).lower()
    harnais = [m for m in MOTS_HARNAIS if m in bas]
    faibles = [m for m in MOTS_MOTEUR_FAIBLES if m in bas]

    sm = 0
    detail_m = []
    if e.symboles:
        sm += 3
        detail_m.append("symbole natif x%d" % len(e.symboles))
    if e.ids:
        sm += 3
        detail_m.append("id d'ability %s" % ",".join(str(i) for i in e.ids))
    if re.search(r"\bengine/", e.brut):
        sm += 2
        detail_m.append("chemin engine/")
    if faibles:
        sm += min(len(faibles), 3)
        detail_m.append("lexique moteur %s" % ",".join(faibles[:3]))

    sh = 0
    detail_h = []
    if harnais:
        sh += 2 * min(len(harnais), 4)
        detail_h.append("lexique harnais %s" % ",".join(harnais[:4]))
    # Le POINT D'ENTREE dit le sujet mieux que le corps : une case-doc de
    # cliquet / d'echafaudage ne devient pas moteur parce qu'elle cite un module.
    if re.search(r"cliquet|empreinte|declencheur|echafaudage|cache-de-verdict|"
                 r"collision|numeros|ledger|banque|rouges|worktree|hooks-audit", pe):
        sh += 4
        detail_h.append("point d'entree d'outillage")

    if sm == 0 and sh == 0:
        e.perimetre, e.perim_raison = "PERIMETRE-INDETERMINE", "aucun signal"
    elif sm > sh:
        e.perimetre = "MOTEUR" if sm >= 3 else "MOTEUR-FAIBLE"
        e.perim_raison = "moteur %d > harnais %d : %s" % (sm, sh, " + ".join(detail_m))
    elif sh > sm:
        e.perimetre = "HARNAIS"
        e.perim_raison = "harnais %d > moteur %d : %s" % (sh, sm, " + ".join(detail_h))
    else:
        e.perimetre = "MIXTE"
        e.perim_raison = "egalite %d/%d -- lecture humaine requise : %s || %s" % (
            sm, sh, " + ".join(detail_m), " + ".join(detail_h))


# ---------------------------------------------------------------- etage 3
RE_ABSENCE = re.compile(
    r"non port|pas port|n'est pas port|ne sont ni port|aucune entr[ée]e|"
    r"n'a aucun|sans substrat|n'existe pas|pas de r[èe]gle port|"
    r"jamais confront|non confront|LUE? mais NON|reste morte|n'est pas outill|"
    r"NON LU|non lu|NON port|NON fait|non cabl|pas cabl",
    re.IGNORECASE,
)


def _rx_id(x: str) -> re.Pattern:
    """'#287-r11' matche '#287-r11' et '#287r11', jamais '#287-r11-r1'."""
    return re.compile(r"#" + re.escape(x.lstrip("#")).replace(r"\-", "[-]?")
                      + r"(?![0-9A-Za-z-])")


RE_PREFIXE = re.compile(r"^[a-z]+(?:\(([^)]*)\))?\s*[:!]")


def position_sujet(msg: str) -> str:
    """Fragment d'un sujet de commit / titre de PR ou un id vaut CETTE tranche.

    Sans cette borne, `docs(#486-r15) : ... et le residu #486-r16` compterait
    comme une livraison de #486-r16 alors qu'il l'OUVRE.
    """
    m = RE_PREFIXE.match(msg)
    if m and m.group(1):
        return m.group(1)
    m2 = re.match(r"^(?:Merge pull request #\d+\s*--\s*)?(#[\w-]+)\s*[ :,]", msg)
    if m2:
        return m2.group(1)
    return ""


def _git(args: list[str]) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT)] + args, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def lire_commits() -> list[tuple[int, str]] | None:
    out = _git(["log", "--format=%ct%x09%s", "--all"])
    if out is None:
        return None
    res = []
    for l in out.splitlines():
        p = l.split("\t", 1)
        if len(p) == 2:
            res.append((int(p[0]), p[1]))
    return res


def lire_blame() -> dict[int, int] | None:
    out = _git(["blame", "--line-porcelain", "-w", "--", str(BACKLOG)])
    if out is None:
        return None
    res, lineno = {}, None
    t = 0
    for l in out.splitlines():
        m = re.match(r"^[0-9a-f]{40} (\d+) (\d+)", l)
        if m:
            lineno = int(m.group(2))
        elif l.startswith("author-time "):
            t = int(l.split()[1])
        elif l.startswith("\t") and lineno is not None:
            res[lineno] = t
    return res


def lire_pr_mergees(limite: int = 600):
    """Tri-etat : None = capteur muet (gh absent / delai / auth), jamais un zero."""
    try:
        r = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--limit", str(limite),
             "--json", "number,title,mergedAt"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT), timeout=90)
    except FileNotFoundError:
        return None, "gh ABSENT du PATH"
    except subprocess.TimeoutExpired:
        return None, "gh : delai de 90 s depasse"
    except OSError as exc:
        return None, "gh : erreur systeme (%s)" % exc.__class__.__name__
    if r.returncode != 0:
        return None, "gh rc=%d : %s" % (r.returncode, (r.stderr or "").strip()[:120])
    try:
        return json.loads(r.stdout), "gh OK"
    except json.JSONDecodeError:
        return None, "gh : sortie JSON illisible"


def _ts(iso: str) -> int:
    return int(datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def classer_fraicheur(e, commits, blame, prs) -> None:
    e.affirme_absence = bool(RE_ABSENCE.search(e.brut))
    p = _rx_id(e.ident)
    t_ins = (blame or {}).get(e.ligne, 0)
    preuves = []

    # E1 -- une TRANCHE portant ce numero exact a ete commitee APRES l'inscription
    if commits is not None:
        h = [m for (t, m) in commits if t > t_ins and p.search(position_sujet(m))]
        if h:
            preuves.append("E1 commit-de-tranche posterieur : %s" % h[0][:70])

    # E2 -- une PR MERGEE dont le TITRE porte ce numero en position de sujet
    if prs is not None:
        h = [pr for pr in prs
             if p.search(position_sujet(pr["title"])) and _ts(pr["mergedAt"]) > t_ins]
        if h:
            preuves.append("E2 PR mergee #%d : %s" % (h[0]["number"], h[0]["title"][:60]))

    # E3 -- citation morte : un chemin cite qui n'existe plus
    morts = [c for c in e.chemins if "/" in c
             and not (ROOT / c).exists() and not (PY / c).exists()]

    if preuves:
        e.fraicheur = "PERIME-CANDIDAT"
        e.frai_raison = " | ".join(preuves)
    elif morts:
        e.fraicheur = "INDETERMINE"
        e.frai_raison = "E3 citation morte : %s" % ", ".join(morts[:2])
    else:
        manques = []
        if commits is None:
            manques.append("git muet")
        if prs is None:
            manques.append("gh muet")
        if blame is None:
            manques.append("blame muet")
        e.fraicheur = "INDETERMINE"
        e.frai_raison = ("aucune epreuve ne mord"
                         + (" (capteurs muets : %s)" % ",".join(manques) if manques else ""))


# ---------------------------------------------------------------- etage 4
LEXIQUE_NATURE = [
    ("BUG-SILENCIEUX", (
        r"reste VERT", r"rien ne rougit", r"aucun test ne", r"en silence",
        r"silencieu", r"invisible", r"sans signal", r"faux vert", r"sans erreur",
        r"aucune erreur", r"permissi", r"regression silencieuse",
        r"structurellement invisible", r"sans que rien", r"no-op silencieux",
    )),
    ("MIRROR-INCOMPLET", (
        r"LUE? mais NON port", r"non port[ée]", r"pas port[ée]", r"partiellement",
        r"collapse", r"diverge", r"ecart mesure", r"le port rend", r"le port ne",
        r"n'a aucun substrat", r"NON port", r"n'est pas porte", r"ni portes",
        r"la loi port[ée]e", r"rate le r[ée]gime", r"ne couvre pas", r"au lieu de",
        r"n'est c[âa]bl[ée]", r"hors du domaine du port", r"ne mat[ée]rialise pas",
        r"n'est pas outill", r"reste[nt]? non port",
    )),
    ("CONFRONTATION-MANQUANTE", (
        r"jamais confront", r"non confront", r"n'a pas ete monte", r"pas ete oppose",
        r"NON VERIFIE", r"reste a etablir", r"contre-epreuve", r"n'a jamais ete",
        r"regime discriminant",
    )),
    ("MESURE-MANQUANTE", (
        r"on ne sait pas", r"indeterminable", r"pas mesure", r"non mesure",
        r"corps natif NON LU", r"NON LU", r"a trancher", r"a classer", r"a decider",
        r"a specifier", r"reste ouvert",
    )),
    ("OUTILLAGE", (
        r"cliquet", r"empreinte", r"cache de verdict", r"pytest", r"banque",
        r"declencheur", r"collecte", r"worktree", r"ledger", r"loop_status",
    )),
    ("PROSE", (
        r"citation perim", r"commentaire date", r"docstring", r"nommage",
        r"renommer", r"la prose", r"redocumenter",
    )),
]
ORDRE_NATURE = ["BUG-SILENCIEUX", "MIRROR-INCOMPLET", "CONFRONTATION-MANQUANTE",
                "MESURE-MANQUANTE", "OUTILLAGE", "PROSE"]


# Signal de GRAVITE, orthogonal a la taxonomie : la ligne porte-t-elle un ECART
# CHIFFRE natif-vs-port deja mesure ? Un residu qui dit << natif 10073 contre
# port 9575 >> n'est plus une intention : c'est un symptome constate, et il
# passe devant un residu de meme nature qui n'en a pas. Motif volontairement
# etroit -- deux nombres d'au moins 2 chiffres separes par un comparatif.
RE_ECART_CHIFFRE = re.compile(
    r"\b\d{2,}\b[^.|]{0,60}?\b(?:contre|vs\.?|au lieu de|puis)\b[^.|]{0,60}?\b\d{2,}\b"
    r"|natif\s*[`\[]?\s*\d{2,}[^.|]{0,40}port\s*[`\[]?\s*\d{2,}"
    r"|port\s*[`\[]?\s*\d{2,}[^.|]{0,40}natif\s*[`\[]?\s*\d{2,}",
    re.IGNORECASE,
)


# Un residu qui exige un CAPTEUR NEUF (hook frida) n'est pas dispatchable seul :
# il attend une fenetre de reinject, qui appartient a l'orchestrateur. Le dire
# ici evite d'envoyer un solveur sur un mur.
RE_BLOQUE_REINJECT = re.compile(
    r"fen[êe]tre de reinject|exige une fen[êe]tre|capteur\s+`?frida|frida/hooks|"
    r"reinject pour [êe]tre active|demande d'exposer",
    re.IGNORECASE,
)


def classer_nature(e: Entree) -> None:
    e.ecart_chiffre = bool(RE_ECART_CHIFFRE.search(e.brut))
    e.bloque_reinject = bool(RE_BLOQUE_REINJECT.search(e.brut))
    trouves = []
    for etiquette, motifs in LEXIQUE_NATURE:
        for m in motifs:
            if re.search(m, e.brut, re.IGNORECASE):
                trouves.append((etiquette, m))
                break
    if not trouves:
        e.nature, e.nat_raison = "NATURE-INDETERMINEE", "aucun motif du lexique"
        return
    ordre = ORDRE_NATURE
    if e.perimetre in ("HARNAIS",):
        ordre = ["OUTILLAGE"] + [x for x in ORDRE_NATURE if x != "OUTILLAGE"]
    for etiquette in ordre:
        for t, m in trouves:
            if t == etiquette:
                autres = sorted({x for x, _ in trouves} - {t})
                e.nature = t
                e.nat_raison = "motif '%s'%s" % (m, " ; aussi " + ",".join(autres) if autres else "")
                return


# ---------------------------------------------------------------- etage 5
def charger_porteurs():
    """Index nom d'ability -> porteurs, derive du gameconfig (offline).

    Tri-etat : None si `unit_map` n'est pas chargeable.
    """
    sys.path.insert(0, str(PY))
    try:
        import unit_map  # noqa: E402
        kits = unit_map.all_kits()
    except Exception:
        return None, None
    return kits, unit_map


def classer_confrontabilite(e, kits, um) -> None:
    """Gate du CLAUDE.md. HORS POOL N'EST PAS UN REFUS.

    Le seul refus legitime serait `data/unspawnable_rank<N>.json` -- ce fichier
    n'existe pas dans l'arbre. On rend donc la VOIE d'arrivee en bataille, pas un
    oui/non : hero-ou-MoW du catalogue, npc greffable, summon a observer, ou
    << voie a etablir >> quand aucun nom d'ability n'est citable.
    """
    if re.search(r"unspawnable_rank", e.brut):
        e.confront, e.conf_raison = "REFUS-LEGITIME", "cite data/unspawnable_rank<N>.json"
        return
    if e.perimetre == "HARNAIS":
        e.confront, e.conf_raison = "SANS-OBJET", "residu d'outillage : aucune bataille a monter"
        return
    if kits is None or um is None:
        e.confront, e.conf_raison = "NON-MESURE", "unit_map non chargeable"
        return
    if not e.noms_ability:
        montage = [p for p in e.probes if p.startswith("probe_")]
        if montage:
            e.confront = "MONTAGE-ECRIT"
            e.conf_raison = "aucun nom d'ability cite, mais un montage existe : %s" % montage[0]
        else:
            e.confront, e.conf_raison = "VOIE-A-ETABLIR", "aucun nom d'ability cite"
        return
    kinds, trouves = set(), []
    for nom in e.noms_ability:
        p = [k for k in kits if um.carrier_voies(k, nom)]
        if p:
            trouves.append(nom)
            kinds |= {k.get("kind", "?") for k in p}
    if not trouves:
        e.confront = "VOIE-A-ETABLIR"
        e.conf_raison = ("nom(s) %s absent(s) des 5 voies du gameconfig -- "
                         "NE PROUVE PAS la mort (trait/summon/liveevent/tile non couverts)"
                         % ",".join(e.noms_ability[:2]))
        return
    if kinds & {"lineup", "mow"}:
        e.confront = "CONFRONTABLE-CATALOGUE"
        e.conf_raison = "porteur(s) de kind %s pour %s" % (
            ",".join(sorted(kinds)), ",".join(trouves[:2]))
    else:
        e.confront = "CONFRONTABLE-PAR-GREFFE"
        e.conf_raison = ("porteurs npc-only (%s) pour %s -- greffe sur une unite du pool "
                         "(case-92 §5bis), pas un refus"
                         % (",".join(sorted(kinds)), ",".join(trouves[:2])))


# ---------------------------------------------------------------- etage 6
POIDS_NATURE = {"BUG-SILENCIEUX": 100, "MIRROR-INCOMPLET": 60,
                "CONFRONTATION-MANQUANTE": 40, "MESURE-MANQUANTE": 25,
                "NATURE-INDETERMINEE": 10, "PROSE": 5, "OUTILLAGE": 0}
POIDS_CONFRONT = {"CONFRONTABLE-CATALOGUE": 30, "CONFRONTABLE-PAR-GREFFE": 22,
                  "MONTAGE-ECRIT": 18, "VOIE-A-ETABLIR": 8,
                  "NON-MESURE": 4, "SANS-OBJET": 0, "REFUS-LEGITIME": 0}


def scorer(e: Entree) -> None:
    """Critere de tete impose par le brief : un BUG SILENCIEUX confrontable et
    vivant passe devant tout le reste -- c'est le seul defaut qu'un entrainement
    RL irait exploiter. Un PERIME-CANDIDAT est ECARTE du classement (il doit
    d'abord etre verifie), pas rétrogradé."""
    if e.perimetre in ("HARNAIS",) or e.fraicheur == "PERIME-CANDIDAT":
        e.score = -1.0
        return
    s = POIDS_NATURE.get(e.nature, 0) + POIDS_CONFRONT.get(e.confront, 0)
    if e.perimetre == "MOTEUR":
        s += 10
    elif e.perimetre == "MOTEUR-FAIBLE":
        s += 2
    if e.ecart_chiffre:
        s += 25  # symptome deja CONSTATE, pas une intention
    e.score = float(s)


# ---------------------------------------------------------------- pilote
def mesurer(chemin: Path = BACKLOG, avec_gh: bool = True):
    entrees = parser_backlog(chemin)
    commits = lire_commits()
    blame = lire_blame()
    prs, etat_gh = (lire_pr_mergees() if avec_gh else (None, "gh non interroge (--sans-gh)"))
    kits, um = charger_porteurs()
    for e in entrees:
        extraire_ancres(e)
        classer_perimetre(e)
        classer_fraicheur(e, commits, blame, prs)
        classer_nature(e)
        classer_confrontabilite(e, kits, um)
        scorer(e)
    capteurs = {
        "git log": "%d commits" % len(commits) if commits is not None else "MUET",
        "git blame": "%d lignes" % len(blame) if blame is not None else "MUET",
        "gh pr list": ("%d PR mergees" % len(prs)) if prs is not None else "MUET -- " + etat_gh,
        "unit_map": "%d kits" % len(kits) if kits is not None else "MUET",
    }
    return entrees, capteurs


def mesures_ecartees(entrees) -> None:
    """Re-joue le signal SYMBOLE et imprime pourquoi il est ecarte du verdict."""
    src = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                    for p in sorted(ENGINE.rglob("*.py")))
    plein = court = total = 0
    for e in entrees:
        for s in e.symboles:
            total += 1
            plein += s in src
            court += s.split("$$")[-1] in src
    print("\nMESURE ECARTEE -- << le symbole cite est-il dans engine/ ? >>")
    print("  symboles cites par les entrees : %d" % total)
    print("  nom COURT present dans engine/  : %d (%.0f %%) -- ne discrimine RIEN"
          % (court, 100.0 * court / max(total, 1)))
    print("  symbole COMPLET present         : %d (%.0f %%) -- nos ports CITENT"
          % (plein, 100.0 * plein / max(total, 1)))
    print("  verbatim le symbole qu'ils declarent NON porte (regle d'ecriture du")
    print("  CLAUDE.md) : la presence ne dit donc rien du portage. ECARTEE.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv")
    ap.add_argument("--detail")
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--portee", action="store_true")
    ap.add_argument("--mesures-ecartees", action="store_true")
    ap.add_argument("--sans-gh", action="store_true", help="verdict 100 %% offline")
    a = ap.parse_args()

    entrees, capteurs = mesurer(avec_gh=not a.sans_gh)
    print("BACKLOG  : %s" % BACKLOG.relative_to(ROOT).as_posix())
    print("SECTION  : '%s' -- %d entrees" % (SECTION_TACHES, len(entrees)))
    for k, v in capteurs.items():
        print("CAPTEUR  : %-12s %s" % (k, v))

    if a.detail:
        cible = a.detail.lstrip("#").lower()
        for e in entrees:
            if e.ident.lstrip("#").lower() == cible:
                print("\n%s (L%d)  score=%.0f" % (e.ident, e.ligne, e.score))
                print("  PERIMETRE %-24s %s" % (e.perimetre, e.perim_raison))
                print("  FRAICHEUR %-24s %s" % (e.fraicheur, e.frai_raison))
                print("  NATURE    %-24s %s" % (e.nature, e.nat_raison))
                print("  CONFRONT  %-24s %s" % (e.confront, e.conf_raison))
                print("  symboles  %s" % (", ".join(e.symboles[:6]) or "-"))
                print("  abilities %s" % (", ".join("%d %s" % (i, n) for i, n in
                                                    zip(e.ids, e.noms_ability)) or "-"))
                print("  probes    %s" % (", ".join(e.probes[:6]) or "-"))
                print("  titre     %s" % e.titre[:200])
                return 0
        print("entree %s introuvable" % a.detail)
        return 2

    for axe in ("perimetre", "fraicheur", "nature", "confront"):
        print("\n%s" % axe.upper())
        c = collections.Counter(getattr(e, axe) for e in entrees)
        for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
            print("  %-26s %4d" % (k, v))

    moteur = [e for e in entrees if e.perimetre in ("MOTEUR", "MOTEUR-FAIBLE", "MIXTE")]
    print("\nCROISEMENT sur les %d entrees MOTEUR (fortes + faibles)" % len(moteur))
    croise = collections.Counter((e.nature, e.confront) for e in moteur)
    for (n, c), v in sorted(croise.items(), key=lambda kv: -kv[1])[:12]:
        print("  %-24s %-24s %3d" % (n, c, v))

    if a.top:
        print("\nCLASSEMENT PRIORISE -- %d premiers (score = nature + confrontabilite)" % a.top)
        print("  (PERIME-CANDIDAT et HARNAIS sont ECARTES : score -1)")
        for i, e in enumerate(sorted(moteur, key=lambda x: (-x.score, x.ident))[:a.top], 1):
            print("  %2d. %-30s %3.0f %s%s %-24s %-24s"
                  % (i, e.ident, e.score, "E!" if e.ecart_chiffre else "  ",
                     "R!" if e.bloque_reinject else "  ", e.nature, e.confront))

    if a.tsv:
        out = Path(a.tsv)
        cols = ["id", "ligne", "score", "perimetre", "fraicheur", "nature", "confront",
                "ecart_chiffre", "bloque_reinject",
                "symboles", "ids", "probes", "perim_raison", "frai_raison",
                "nat_raison", "conf_raison", "titre"]
        with out.open("w", encoding="utf-8", newline="") as fh:
            fh.write("\t".join(cols) + "\n")
            for e in sorted(entrees, key=lambda x: -x.score):
                fh.write("\t".join([
                    e.ident, str(e.ligne), "%.0f" % e.score, e.perimetre, e.fraicheur,
                    e.nature, e.confront,
                    "oui" if e.ecart_chiffre else "non",
                    "oui" if e.bloque_reinject else "non",
                    ";".join(e.symboles[:4]),
                    ";".join(str(i) for i in e.ids), ";".join(e.probes[:4]),
                    e.perim_raison, e.frai_raison, e.nat_raison, e.conf_raison,
                    e.titre[:300].replace("\t", " "),
                ]) + "\n")
        print("\nTSV ecrit : %s" % out)

    if a.mesures_ecartees:
        mesures_ecartees(entrees)

    if a.portee:
        print("\nPORTEE DE LA MESURE -- ce que ce probe NE voit PAS")
        print("  - il lit la SEULE section '%s' du backlog" % SECTION_TACHES)
        print("  - FRAICHEUR : un residu livre SANS que son numero soit en position de")
        print("    SUJET d'un commit ou d'un titre de PR reste INDETERMINE. C'est le cas")
        print("    dominant, et c'est le resultat principal de la tranche.")
        print("  - `gh pr list --limit 600` ne remonte pas au-dela des PR les plus")
        print("    recentes : une livraison plus ancienne est hors de portee de E2.")
        print("  - le blame date la DERNIERE reecriture de la ligne, pas son ajout :")
        print("    une ligne remaniee peut masquer une livraison anterieure.")
        print("  - CONFRONTABILITE : les voies trait / summon / liveevent / tile ne sont")
        print("    pas derivees ; un 'VOIE-A-ETABLIR' n'est PAS une preuve de mort.")
        print("  - NATURE et PERIMETRE sont LEXICAUX : ils classent ce que la ligne DIT,")
        print("    pas ce que le code fait. Un contresens de redaction se propage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
