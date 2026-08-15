#!/usr/bin/env python3
"""#927-r4 -- MESURE : quel litteral `matchAbilityEntities` chaque call-site natif de
`IdunBattleLogic.Entities.DSLSelectors$$Cache` pousse-t-il, et le PORT le transcrit-il ?

LA QUESTION, ET POURQUOI ELLE SE POSE
-------------------------------------
Le noeud porte `engine/entities/selectors/geometry.py::Cache` accepte
`match_ability_entities` en argument OPTIONNEL, de defaut `True`. Un defaut est un litteral
qu'on ne relit pas : si le natif n'en a AUCUN -- c'est-a-dire si chaque call-site pousse le
sien -- alors le port fabrique une valeur la ou le natif en LIT une, et un futur `Cache` pose
sans y penser prendra le mode majoritaire.

CE QUE CE PROBE MESURE, EN DEUX VOLETS INDEPENDANTS
--------------------------------------------------
  [PE]  Census NATIF. Scan du binaire pour tous les `E8 <rel32>` visant
        `IdunBattleLogic.Entities.DSLSelectors$$Cache`, puis desassemblage AVANT de la fonction
        appelante (depuis son symbole, jamais depuis une fenetre desalignee) pour suivre R8 --
        le 3e argument de l'ABI x64 Windows, donc `matchAbilityEntities`. Sortie : par symbole
        appelant, la liste des litteraux pousses.
  [PY]  Census PORTE. Balayage AST de `scripts/python/engine/**` : chaque appel au noeud DSL
        `Cache` (import resolu, pas un homonyme), et s'il ECRIT `match_ability_entities`.

TRI-ETAT. Une table de symboles absente, un binaire introuvable ou capstone manquant rendent
rc=2 et le DISENT. Aucun chemin ne fabrique un zero.

Usage:
    python probe_927r4_cache_census.py            # les deux volets
    python probe_927r4_cache_census.py --pe       # volet natif seul
    python probe_927r4_cache_census.py --py       # volet porte seul

ASCII strict (console cp1252).
"""
from __future__ import annotations

import argparse
import ast
import bisect
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from symbols_layout import build_dir, current_build  # noqa: E402

#: Ce qui doit changer pour que cette mesure change d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/**/*.py",),
    "build": True,
    "toujours": False,
    "raison": "Il croise le DECOMPILE du build courant (call-sites natifs de "
              "`DSLSelectors$$Cache`) avec les call-sites PYTHON du noeud `Cache`. Les deux "
              "bougent : un changement de build deplace les adresses, un port neuf ajoute un "
              "call-site Python.",
}

SYMBOLE_CACHE = "IdunBattleLogic.Entities.DSLSelectors$$Cache"
#: Le noeud DSL, par son module de definition -- surtout pas par son nom nu (`Cache` est un
#: identifiant courant ; on ne veut QUE celui-la).
MODULE_NOEUD = "engine.entities.selectors.geometry"


# ==============================================================================================
# VOLET PE -- le census NATIF
# ==============================================================================================

def _charger_fonctions(build: str):
    """`ghidra/functions.tsv` -> (liste triee de VAs, dict VA -> symbole)."""
    f = build_dir(build) / "ghidra" / "functions.tsv"
    if not f.is_file():
        raise RuntimeError("table ghidra/functions.tsv absente pour le build %s" % build)
    vas, noms = [], {}
    with f.open("r", encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            if ligne.startswith("#"):
                continue
            bout = ligne.rstrip("\n").split("\t")
            if len(bout) < 2:
                continue
            try:
                va = int(bout[0], 16)
            except ValueError:
                continue
            vas.append(va)
            noms[va] = bout[1]
    vas.sort()
    return vas, noms


def _chemin_binaire(build: str) -> Path:
    p = Path.home() / "AppData" / "Local" / "tacticus" / "games" / build / "GameAssembly.dll"
    if not p.is_file():
        raise RuntimeError(
            "GameAssembly.dll du build %s introuvable (%s) -- volet PE NON MESURE" % (build, p))
    return p


def _sections(pe):
    """[(va_debut, va_fin, data)] des sections EXECUTABLES."""
    base = pe.OPTIONAL_HEADER.ImageBase
    out = []
    for s in pe.sections:
        # IMAGE_SCN_MEM_EXECUTE
        if not (s.Characteristics & 0x20000000):
            continue
        deb = base + s.VirtualAddress
        data = s.get_data()
        out.append((deb, deb + len(data), data))
    return out


def _lire(sections, va, n):
    for deb, fin, data in sections:
        if deb <= va and va + n <= fin:
            return data[va - deb:va - deb + n]
    return None


def _call_sites(sections, cible: int):
    """Toutes les VAs d'un `E8 <rel32>` (call) OU d'un `E9 <rel32>` / `EB <rel8>` (JMP) dont la
    cible vaut `cible`. Rend [(va, opcode)].

    ⚠ **LE JMP EST UN CALL-SITE, ET L'OUBLIER SOUS-COMPTE LE CENSUS.** Un appel en position de
    QUEUE est compile en tail call : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    FuryOfTheAncientsAbility$$GetTarget` finit par `mov r8b, 1 ; jmp <Cache>`, et un scan qui ne
    cherche que `E8` ne le voit PAS. C'est ce qui manquait au census de #927-r3, qui annoncait
    119 call-sites -- exactement le compte `E8` seul.

    On ne se contente pas de chercher l'octet : on VERIFIE que la cible calculee tombe pile sur
    le symbole. Un faux octet interne a une instruction ne peut donc pas passer sauf coincidence
    exacte sur le deplacement -- et celui-ci est unique par site.
    """
    trouves = []
    for deb, fin, data in sections:
        n = len(data)
        for opcode, taille in ((b"\xe8", 5), (b"\xe9", 5), (b"\xeb", 2)):
            i = 0
            while True:
                i = data.find(opcode, i)
                if i < 0 or i + taille > n:
                    break
                rel = int.from_bytes(data[i + 1:i + taille], "little", signed=True)
                if deb + i + taille + rel == cible:
                    trouves.append((deb + i, opcode[0]))
                i += 1
    return sorted(trouves)


_R8 = {"r8", "r8d", "r8w", "r8b"}


def _valeur_r8_au_call(md, sections, debut_fn: int, va_call: int):
    """Desassemble [debut_fn, va_call] et rend la derniere valeur ECRITE dans R8.

    Rend un `int` si le dernier ecrivain est un immediat ou un `xor r8*, r8*` (donc 0), et
    `None` si R8 vient d'ailleurs (registre, memoire) ou n'a pas ete ecrit dans la fenetre.
    """
    taille = va_call - debut_fn
    if taille <= 0 or taille > 0x20000:
        return "HORS-FENETRE"
    octets = _lire(sections, debut_fn, taille)
    if octets is None:
        return "HORS-SECTION"
    val = None
    vu_call = False
    for ins in md.disasm(octets, debut_fn):
        if ins.address >= va_call:
            break
        m = ins.mnemonic
        ops = ins.op_str
        # Un appel intermediaire detruit R8 (volatile dans l'ABI x64 Windows).
        if m == "call":
            val, vu_call = None, True
        try:
            _lus, ecrits = ins.regs_access()
        except Exception:
            _lus, ecrits = (), ()
        noms = {md.reg_name(r) for r in ecrits}
        if not (noms & _R8):
            continue
        cible, _, source = ops.partition(", ")
        cible, source = cible.strip(), source.strip()
        if m == "xor" and cible in _R8 and source == cible:
            val = 0
        elif m == "mov" and cible in _R8:
            try:
                val = int(source, 0)
            except ValueError:
                val = None
        else:
            val = None
    if val is None:
        return "INDETERMINE(apres-call)" if vu_call else "INDETERMINE"
    return val


def volet_pe(build: str):
    try:
        import capstone
        import pefile
    except ImportError as e:
        print("[PE] NON MESURE -- module manquant : %s" % e)
        return None

    vas, noms = _charger_fonctions(build)
    cible = None
    for va, nom in noms.items():
        if nom == SYMBOLE_CACHE:
            cible = va
            break
    if cible is None:
        print("[PE] NON MESURE -- symbole %s absent de la table du build %s"
              % (SYMBOLE_CACHE, build))
        return None

    pe = pefile.PE(str(_chemin_binaire(build)), fast_load=True)
    secs = _sections(pe)
    sites = _call_sites(secs, cible)

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    par_appelant = defaultdict(list)
    valeurs = Counter()
    formes = Counter()
    for va, opc in sites:
        i = bisect.bisect_right(vas, va) - 1
        debut = vas[i] if i >= 0 else None
        nom = noms.get(debut, "?")
        v = _valeur_r8_au_call(md, secs, debut, va) if debut is not None else "SANS-SYMBOLE"
        par_appelant[nom].append(v)
        valeurs[v if isinstance(v, int) else str(v)] += 1
        formes["call (E8)" if opc == 0xE8 else "tail call (jmp %02X)" % opc] += 1

    print("[PE] build=%s  symbole=%s" % (build, SYMBOLE_CACHE))
    print("[PE] call-sites trouves : %d" % len(sites))
    for f in sorted(formes):
        print("[PE]   forme %-24s %d" % (f, formes[f]))
    for k in sorted(valeurs, key=lambda x: (isinstance(x, str), x)):
        etiquette = {0: "SLOT (matchAbilityEntities = 0)",
                     1: "DICT (matchAbilityEntities = 1)"}.get(k, str(k))
        print("[PE]   %-40s %d" % (etiquette, valeurs[k]))

    minorite = sorted(n for n, vs in par_appelant.items() if any(v == 0 for v in vs))
    print("[PE] appelants poussant AU MOINS UN 0 (mode SLOT) : %d" % len(minorite))
    for n in minorite:
        print("[PE]   %s  ->  %s" % (n, par_appelant[n]))

    autres = sorted(n for n, vs in par_appelant.items()
                    if any(not isinstance(v, int) for v in vs))
    if autres:
        print("[PE] appelants a litteral NON CONSTANT (a lire a l'oeil) : %d" % len(autres))
        for n in autres:
            print("[PE]   %s  ->  %s" % (n, par_appelant[n]))
    return {"sites": len(sites), "valeurs": dict(valeurs),
            "par_appelant": {k: v for k, v in par_appelant.items()}}


# ==============================================================================================
# VOLET PY -- le census PORTE
# ==============================================================================================

def _alias_du_noeud(arbre: ast.AST) -> set[str]:
    """Les noms locaux qui designent le noeud DSL `Cache` dans ce module."""
    out = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.endswith(
                MODULE_NOEUD.rsplit(".", 1)[-1]):
            for a in n.names:
                if a.name == "Cache":
                    out.add(a.asname or a.name)
        elif isinstance(n, ast.ImportFrom) and n.module in (MODULE_NOEUD, "engine.dsl"):
            for a in n.names:
                if a.name == "Cache":
                    out.add(a.asname or a.name)
    return out


def volet_py():
    racine = RACINE / "scripts" / "python" / "engine"
    if not racine.is_dir():
        print("[PY] NON MESURE -- %s absent" % racine)
        return None
    ecrits, muets = [], []
    for f in sorted(racine.rglob("*.py")):
        try:
            src = f.read_text(encoding="utf-8")
            arbre = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        alias = _alias_du_noeud(arbre)
        if not alias:
            continue
        for n in ast.walk(arbre):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in alias):
                continue
            rel = f.relative_to(RACINE).as_posix()
            explicite = any(k.arg == "match_ability_entities" for k in n.keywords) \
                or len(n.args) >= 2
            (ecrits if explicite else muets).append((rel, n.lineno))
    print("[PY] call-sites du noeud DSL `Cache` : %d" % (len(ecrits) + len(muets)))
    print("[PY]   ECRIVENT le litteral        : %d" % len(ecrits))
    print("[PY]   HERITENT du defaut          : %d" % len(muets))
    par_fichier = Counter(r for r, _ in muets)
    print("[PY] fichiers concernes par le defaut : %d" % len(par_fichier))
    for r, c in sorted(par_fichier.items()):
        print("[PY]   %-70s %d" % (r, c))
    print("[PY] sites ECRIVANT :")
    for r, l in ecrits:
        print("[PY]   %s:%d" % (r, l))
    return {"ecrits": ecrits, "muets": muets}


# ==============================================================================================
# VOLET APPARIEMENT -- chaque site PYTHON contre le litteral de SON call-site natif
# ==============================================================================================

RE_SYMBOLE = re.compile(r"\b([A-Za-z_][\w.]*\$\$[A-Za-z_]\w*)")


def _englobantes(arbre: ast.AST):
    """[(noeud, [ancetres def/class])] -- pour retrouver la docstring qui cite le natif."""
    pile = {}
    def marche(n, anc):
        for e in ast.iter_child_nodes(n):
            a2 = anc + [e] if isinstance(
                e, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else anc
            pile[id(e)] = a2
            marche(e, a2)
    pile[id(arbre)] = []
    marche(arbre, [])
    return pile


def apparier(natif: dict[str, list[int]]):
    """Croise chaque call-site PYTHON du noeud `Cache` avec le litteral que pousse SON
    call-site natif. FONCTION PURE (aucune sortie console) -- partagee avec le cliquet.

    L'appariement se fait par le SYMBOLE natif cite dans la docstring ou les commentaires de la
    fonction/classe englobante, de la plus PROCHE a la plus lointaine -- jamais par le nom du
    fichier ni par une heuristique de nommage. Un site dont aucun symbole connu du census
    n'apparait sort avec une liste d'appariement VIDE, jamais rabattu sur un defaut.

    Rend [(chemin_relatif, ligne, litteral_ecrit_ou_None, [symboles_courts_apparies])].
    """
    court = defaultdict(list)
    for plein, vals in natif.items():
        court[plein.rsplit(".", 1)[-1]].extend(vals)

    racine = RACINE / "scripts" / "python" / "engine"
    lignes = []
    for f in sorted(racine.rglob("*.py")):
        try:
            src = f.read_text(encoding="utf-8")
            arbre = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        alias = _alias_du_noeud(arbre)
        if not alias:
            continue
        src_lignes = src.splitlines()
        pile = _englobantes(arbre)
        for n in ast.walk(arbre):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in alias):
                continue
            explicite = any(k.arg == "match_ability_entities" for k in n.keywords) \
                or len(n.args) >= 2
            ecrit = None
            if explicite:
                for k in n.keywords:
                    if k.arg == "match_ability_entities":
                        ecrit = getattr(k.value, "value", "?")
                if ecrit is None and len(n.args) >= 2:
                    ecrit = getattr(n.args[1], "value", "?")
            # Symboles cites par les englobantes, de la plus PROCHE a la plus lointaine, puis
            # le module. On ne retient que ceux que le census natif connait.
            anc = list(reversed(pile.get(id(n), [])))
            # 1re source : le VOISINAGE IMMEDIAT du site (commentaire de fin de ligne, ligne
            # au-dessus). C'est la forme la plus PRECISE -- le symbole du call-site, pas celui
            # de la fonction, qui peut en citer plusieurs.
            textes = ["\n".join(src_lignes[max(0, n.lineno - 4):n.lineno + 1])]
            for a in anc:
                d = ast.get_docstring(a) or ""
                deb = max(0, a.lineno - 12)
                textes.append(d + "\n" + "\n".join(src_lignes[deb:a.lineno + 3]))
            textes.append(ast.get_docstring(arbre) or "")
            apparies = []
            for t in textes:
                for s in RE_SYMBOLE.findall(t):
                    c = s.rsplit(".", 1)[-1]
                    if c in court:
                        apparies.append(c)
                if apparies:
                    break
            lignes.append((f.relative_to(RACINE).as_posix(), n.lineno, ecrit,
                           sorted(set(apparies))))
    return lignes


def litteraux_du_symbole(natif: dict[str, list[int]], courts) -> list[int]:
    """Les litteraux DISTINCTS que poussent les call-sites des symboles cites."""
    court = defaultdict(list)
    for plein, vals in natif.items():
        court[plein.rsplit(".", 1)[-1]].extend(vals)
    return sorted({v for c in courts for v in court.get(c, ()) if isinstance(v, int)})


def volet_appariement(pe):
    if not pe:
        print("[AP] NON MESURE -- volet PE indisponible")
        return None
    natif = pe["par_appelant"]
    lignes = apparier(natif)

    print("[AP] appariement des %d call-sites PYTHON a leur call-site NATIF" % len(lignes))
    ok = sus = orph = 0
    for rel, ln, ecrit, app in lignes:
        vals = litteraux_du_symbole(natif, app)
        effectif = True if ecrit is None else bool(ecrit)
        if not app:
            orph += 1
            print("[AP] NON APPARIE  %s:%d  (ecrit=%s)" % (rel, ln, ecrit))
        elif vals == [int(effectif)]:
            ok += 1
        elif int(effectif) in vals:
            sus += 1
            print("[AP] AMBIGU      %s:%d  effectif=%d  natif=%s  via %s"
                  % (rel, ln, int(effectif), vals, app))
        else:
            sus += 1
            print("[AP] DIVERGENT   %s:%d  effectif=%d  natif=%s  via %s"
                  % (rel, ln, int(effectif), vals, app))
    print("[AP] concordants=%d  a-lire=%d  non-apparies=%d" % (ok, sus, orph))
    return lignes


TABLE = "dsl_cache_call_sites.tsv"


def chemin_table(build: str | None = None) -> Path:
    """La table VERSIONNEE du census natif -- une ENTREE, au meme titre que
    `remove_on_death_step.tsv` et `non_owner_slot4.tsv` (memes moeurs : produite par un
    `--regenerer` explicite, jamais par un run ordinaire)."""
    return build_dir(build) / "metadata" / TABLE


def regenerer_table(pe, build: str) -> Path:
    """Ecrit `<symbole appelant>\\t<litteraux, separes par des virgules>`, trie."""
    dest = chemin_table(build)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "# 3e argument (`matchAbilityEntities`) de chaque call-site de",
        "# `IdunBattleLogic.Entities.DSLSelectors$$Cache` -- build %s." % build,
        "# 1 = mode DICT (`+0x30.TryGetValue(entities)`), 0 = mode SLOT (`+0x28`).",
        "# Les call-sites d'un meme appelant sont dans l'ordre des ADRESSES croissantes.",
        "# Le compte inclut les TAIL CALLS (`jmp`) : les rater sous-compte le census (#927-r4).",
        "# Regenerer : python scripts/python/probe_927r4_cache_census.py --regenerer",
    ]
    for nom in sorted(pe["par_appelant"]):
        vals = pe["par_appelant"][nom]
        lignes.append("%s\t%s" % (nom, ",".join(str(v) for v in vals)))
    dest.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return dest


def lire_table(build: str | None = None) -> dict[str, list[int]]:
    """La table versionnee -> {symbole appelant: [litteraux]}. Erreur DURE si absente."""
    f = chemin_table(build)
    if not f.is_file():
        raise RuntimeError(
            "table %s absente -- la regenerer par "
            "`python scripts/python/probe_927r4_cache_census.py --regenerer`" % f)
    out = {}
    for ligne in f.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#") or not ligne.strip():
            continue
        nom, _, vals = ligne.partition("\t")
        out[nom] = [int(v) for v in vals.split(",") if v.strip()]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerer", action="store_true",
                    help="reecrit data/symbols/<build>/metadata/" + TABLE)
    ap.add_argument("--pe", action="store_true", help="volet natif seul")
    ap.add_argument("--py", action="store_true", help="volet porte seul")
    ap.add_argument("--apparier", action="store_true",
                    help="croise chaque site PYTHON avec le litteral de SON call-site natif")
    ap.add_argument("--json", metavar="FICHIER", help="ecrire le resultat brut (sous logs/)")
    a = ap.parse_args()
    cible = a.pe or a.py or a.apparier or a.regenerer
    faire_pe = a.pe or a.apparier or a.regenerer or not cible
    faire_py = a.py or not cible

    res = {}
    rc = 0
    pe = None
    build = None
    if faire_pe:
        try:
            build = current_build()
            pe = volet_pe(build)
        except Exception as e:                                    # noqa: BLE001
            print("[PE] NON MESURE -- %s" % e)
            rc = 2
        res["pe"] = pe
        rc = rc or (2 if pe is None else 0)
    if a.regenerer:
        if pe is None:
            print("[TABLE] NON REGENEREE -- le volet PE n'a rien mesure")
            rc = rc or 2
        else:
            print("[TABLE] %s" % regenerer_table(pe, build))
    if faire_py:
        print("")
        r = volet_py()
        res["py"] = r
        rc = rc or (2 if r is None else 0)
    if a.apparier:
        print("")
        r = volet_appariement(pe)
        res["appariement"] = r
        rc = rc or (2 if r is None else 0)

    if a.json:
        dest = Path(a.json)
        if not dest.is_absolute():
            dest = RACINE / "logs" / dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        print("\n[OUT] %s" % dest)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
