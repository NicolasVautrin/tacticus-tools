#!/usr/bin/env python
"""#448-r3-r1-r1 -- un montage qui GREFFE doit ALIMENTER le canal `unitAbilityStates`.

POURQUOI CE PROBE EXISTE (mesure du 2026-08-05, pas une precaution). `probe_448_r2b_stormboyz_
teleporting_in.py` rendait 0 echec en CLI contre 3 sous pytest, MEME code / MEME seed / MEME board.
Cause : `engine.runner.snapshot.load_state` ne seede `UnitContext.passive_abilities` (et trois
autres champs du meme payload) que si le canal `unitAbilityStates` a parle -- soit par le TRANSPORT
AMBIANT (`snapshot.bind_live_rpc`, que `tests/conftest.py::live_session` lie), soit par l'argument
`ability_states=<payload>`. Sans canal, `collect_triggered_abilities` retombe sur
`gameconfig.unit(<greffon>)`, qui ne porte evidemment PAS l'ability GREFFEE : aucune classe greffee
n'est montee cote port, et toutes les assertions NEGATIVES du probe (« l'effet n'est plus la »,
« aucun marqueur ») passent A VIDE, EN VERT.

CE QUE LE PROBE MESURE -- et pourquoi le critere n'est PAS « le fichier appelle `bind_live_rpc` ».
La fiche parente (`case-448-r3-r1` §9) recensait par ce critere-la et rendait SEPT fichiers. Il est
FAUX PAR EXCES : il ne voit qu'UNE des deux voies d'alimentation. Quatre des sept passent
`ability_states=<payload>` explicitement -- leur canal parle, `source == "given"`. Le critere
correct est le CANAL, pas la VOIE : un site `load_state` est couvert s'il recoit le payload, OU si
son fichier lie l'ambiant, OU s'il herite l'ambiant du harnais (`tests/conftest.py`).

LES CINQ ETAGES (chacun DERIVE, aucun ne part d'une liste de noms) :

  1. PRIMITIVES  -- les fonctions de `catalog_inject.py` qui ecrivent une ability CHOISIE PAR
                    L'APPELANT dans une unite du BC. Derivees par data-flow intra-fonction : la
                    valeur ecrite dans `u["PassiveAbilities"|"ActiveAbilities"|"TertiaryAbility"|
                    "Traits"]` depend-elle d'un PARAMETRE ? Si oui la greffe DIVERGE du gameconfig
                    (c'est le vice) ; si elle depend de l'`unit_id` seul, c'est une TRANSCRIPTION
                    du gameconfig (`augment`), et le port qui derive du gameconfig tombe juste.
  2. GREFFEURS   -- fermeture transitive des appelants des primitives, sur tout le corpus.
  3. LECTEURS    -- fermeture transitive des fichiers qui atteignent `load_state`, et la LISTE DE
                    SES SITES d'appel.
  4. COUVERTURE  -- par SITE (pas par fichier) : `ability_states=` non-`None`, ou ambiant lie dans
                    le fichier, ou ambiant herite (fichier de `tests/`).
  5. PORTEE      -- ce que la mesure NE VOIT PAS, imprime a chaque run.

Le probe est OFFLINE et PUR (aucun runner, aucune session). Usage, depuis `scripts/python` :

    python probe_448_r3_r1_r1_greffe_sans_canal.py
    python probe_448_r3_r1_r1_greffe_sans_canal.py --mutate       # contre-epreuve synthetique
    python probe_448_r3_r1_r1_greffe_sans_canal.py --details      # tous les sites, couverts inclus
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
CATALOG = PYDIR / "catalog_inject.py"

#: Cles de `BC.Units[]` dont le port ne peut lire l'ecart QUE par le canal `unitAbilityStates`.
#: Ce sont exactement les trois que monte `IdunBattle.Entities.Factories.UnitFactory$$
#: AddConfiguredAbilities` : `PassiveAbilities` (hierarchie 2), `ActiveAbilities` et
#: `TertiaryAbility` (hierarchie 3).
#:
#: ⚠ `Traits` EN EST ABSENT, et ce n'est pas un oubli : un trait greffe (`add_unit_trait`) est lu
#: par le port sur `combatSnapshot.units[].traits` (`snapshot._load_unit_traits` -> `ctx.traits`,
#: que `collect_triggered_abilities` itere en PREMIER). Substrat UNIQUE avec le natif, donc aucune
#: dependance au canal -- c'est le constat deja ecrit dans `catalog_inject.add_unit_trait`.
UNIT_ABILITY_KEYS = ("PassiveAbilities", "ActiveAbilities", "TertiaryAbility")

#: Le consommateur garde. Un seul foyer : `engine/runner/snapshot.py`.
CONSUMER = "load_state"

#: Les deux voies d'alimentation du canal ambiant.
BINDERS = ("bind_live_rpc", "live_rpc")

#: Fichiers dont le harnais lie l'ambiant pour eux (`tests/conftest.py::live_session`, #363).
INHERITED_AMBIENT_DIR = "tests"


# ─────────────────────────────────────────────────────────────────── outillage AST

def parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return None


def called_names(node) -> set:
    """Noms TERMINAUX appeles sous `node` : `f(...)` -> `f`, `M.f(...)` -> `f`.

    ⚠ NON QUALIFIE -- ne sert qu'aux deux usages ou l'homonymie est sans consequence : detecter un
    `bind_live_rpc` dans un fichier, et propager un wrapper A L'INTERIEUR de `catalog_inject.py`.
    Le graphe d'appels du corpus, lui, est QUALIFIE PAR MODULE (`resolve_calls`) : un graphe par nom
    terminal rendait `main` greffeur, donc 1842 fichiers sur 1842 -- mesure du 2026-08-05."""
    out: set = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def _param_names(fn) -> set:
    a = fn.args
    out = {p.arg for p in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)}
    if a.vararg:
        out.add(a.vararg.arg)
    if a.kwarg:
        out.add(a.kwarg.arg)
    return out


def _tainted_locals(fn, seeds: set) -> set:
    """Fermeture (naive, 3 passes -- suffit pour des corps lineaires) des noms locaux dont la
    valeur DERIVE d'un des `seeds`. Sert a trancher « ability choisie par l'appelant » contre
    « ability derivee de l'unite »."""
    taint = set(seeds)
    for _ in range(3):
        for n in ast.walk(fn):
            if not isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                continue
            val = n.value
            if val is None:
                continue
            used = {x.id for x in ast.walk(val) if isinstance(x, ast.Name)}
            if not (used & taint):
                continue
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                for x in ast.walk(t):
                    if isinstance(x, ast.Name):
                        taint.add(x.id)
        # boucles `for a, b in <expr tainte>`
        for n in ast.walk(fn):
            if isinstance(n, ast.For):
                used = {x.id for x in ast.walk(n.iter) if isinstance(x, ast.Name)}
                if used & taint:
                    for x in ast.walk(n.target):
                        if isinstance(x, ast.Name):
                            taint.add(x.id)
    return taint


# ─────────────────────────────────────────────────────── etage 1 : primitives derivees

#: Parametres qui ne CHOISISSENT rien : le SUPPORT (le BC, le chemin de sortie) et la CIBLE
#: (l'unite). Une valeur qui n'en derive QUE est une TRANSCRIPTION du gameconfig de l'unite --
#: exactement ce que `augment` fait --, et le port qui derive du gameconfig tombe alors juste.
SUPPORT_PARAMS = frozenset(("bc", "seed_bc", "out_path", "unit_id", "unit_ids", "rank", "replace"))


def derive_primitives(path: Path) -> tuple[dict, list]:
    """Rend `({nom: 'divergente' | 'divergente-si:<param>' | 'transcription'}, indetermines)`.

    Une fonction est PRIMITIVE si elle affecte l'une des `UNIT_ABILITY_KEYS` sur un subscript.
    Elle est DIVERGENTE si la valeur affectee derive d'un de ses PARAMETRES hors `SUPPORT_PARAMS`
    -- c'est-a-dire si l'APPELANT choisit ce qui est monte, donc si le BC peut s'ecarter du
    gameconfig. Si ce parametre est OPTIONNEL (il a un defaut), la divergence est CONDITIONNELLE :
    seul un SITE qui passe l'argument greffe (`write_augmented_seed_bc(restrict_abilities=…)`,
    qui RETIRE des abilities -- divergence en sens INVERSE de la greffe, tout aussi muette)."""
    tree = parse(path)
    if tree is None:
        return ({}, ["%s : non parsable" % path.name])
    prims: dict = {}
    indet: list = []
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        writes = []
        for n in ast.walk(fn):
            if not isinstance(n, ast.Assign):
                continue
            for t in n.targets:
                if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) \
                        and t.slice.value in UNIT_ABILITY_KEYS:
                    writes.append((t.slice.value, n.value))
        if not writes:
            continue
        params = _param_names(fn)
        chooser = params - SUPPORT_PARAMS
        optionnels = _optional_params(fn)
        coupables = set()
        for _key, val in writes:
            used = {x.id for x in ast.walk(val) if isinstance(x, ast.Name)}
            for c in chooser:
                if used & _tainted_locals(fn, {c}):
                    coupables.add(c)
        if not coupables:
            prims[fn.name] = "transcription"
        elif coupables - optionnels:
            prims[fn.name] = "divergente"
        else:
            prims[fn.name] = "divergente-si:%s" % sorted(coupables)[0]
    # WRAPPERS du meme module. On suit les APPELS **et les REFERENCES DE NOM** : mesure du
    # 2026-08-05 -- `write_grafted_seed_bc` fait `graft = graft_active_ability if … else
    # graft_passive_ability` puis `graft(...)`, donc un critere par APPEL seul le rate, et avec lui
    # le montage le plus utilise du depot.
    for _ in range(4):
        for fn in tree.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if str(prims.get(fn.name, "")).startswith("divergente"):
                continue
            refs = called_names(fn) | referenced_names(fn)
            if any(str(prims.get(c, "")).startswith("divergente") for c in refs):
                prims[fn.name] = "divergente"
    return (prims, indet)


def _optional_params(fn) -> set:
    a = fn.args
    out = set()
    pos = list(a.posonlyargs) + list(a.args)
    for p, _d in zip(pos[len(pos) - len(a.defaults):], a.defaults):
        out.add(p.arg)
    for p, d in zip(a.kwonlyargs, a.kw_defaults):
        if d is not None:
            out.add(p.arg)
    return out


def referenced_names(node) -> set:
    """Noms mentionnes en LECTURE, appel ou non : `graft = graft_passive_ability` compte."""
    out: set = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add(n.id)
        elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
            out.add(n.attr)
    return out


# ──────────────────────────────────────────── etages 2-3 : fermeture transitive du corpus

def corpus(root: Path) -> list:
    """Tout `.py` sous `scripts/python`, hors caches. On balaie AUSSI `tests/` : un test qui
    greffe est soumis au meme critere (il herite juste l'ambiant du conftest)."""
    out = []
    for p in sorted(root.rglob("*.py")):
        parts = set(p.parts)
        if "__pycache__" in parts or ".venv" in parts or "node_modules" in parts:
            continue
        out.append(p)
    return out


def module_name(path: Path, root: Path) -> str:
    r = path.relative_to(root)
    parts = list(r.parts)
    parts[-1] = parts[-1][:-3]                                  # strip .py
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_relative(mod: str, level: int, base_pkg: str) -> str:
    """`from ..services import x` dans `engine.runner.snapshot` -> `engine.services`."""
    parts = base_pkg.split(".") if base_pkg else []
    if level > 0:
        parts = parts[:len(parts) - (level - 1)] if level - 1 <= len(parts) else []
    return ".".join([p for p in parts + ([mod] if mod else []) if p])


def file_symbols(path: Path, root: Path) -> dict:
    """Table de resolution du fichier : `{nom local: ('mod', <module>) | ('fn', <module>, <nom>)}`.

    C'est ce qui QUALIFIE les appels. Les imports relatifs sont resolus contre le package du
    fichier ; les imports hors corpus restent dans la table et ne matchent simplement jamais."""
    tree = parse(path)
    if tree is None:
        return {}
    mod = module_name(path, root)
    pkg = mod.rsplit(".", 1)[0] if "." in mod else ""
    if (path.name == "__init__.py"):
        pkg = mod
    syms: dict = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                syms[(a.asname or a.name).split(".")[0]] = ("mod", a.name)
        elif isinstance(n, ast.ImportFrom):
            src = _resolve_relative(n.module or "", n.level, pkg) if n.level else (n.module or "")
            for a in n.names:
                syms[a.asname or a.name] = ("fn", src, a.name)
    return syms


def resolve_calls(path: Path, root: Path, own_fns: set, conditional: dict | None = None) -> dict:
    """`{fonction du fichier (ou '<module>'): {(module, nom) appeles ou REFERENCES}}` -- QUALIFIE.

    Trois formes resolues : `M.f` via l'alias de module, `f` importe via `from X import f`, et `f`
    defini dans le fichier lui-meme. On compte l'APPEL **et la simple REFERENCE** (cf.
    `referenced_names`). Une forme non resolue (`obj.methode()`, callable stocke dans un dict) est
    IGNOREE ici et comptee a l'etage 5.

    `conditional = {(module, nom): <parametre>}` : arete posee SEULEMENT si le site passe ce
    keyword -- c'est la primitive dont la divergence depend de l'argument."""
    tree = parse(path)
    if tree is None:
        return {}
    conditional = conditional or {}
    mod = module_name(path, root)
    syms = file_symbols(path, root)
    out: dict = {}
    unresolved = 0

    def _qualify(node, compte=False):
        """`(module, nom)` d'un `Attribute`/`Name` en position LECTURE, ou None.

        `compte=True` incremente le compteur des APPELS non resolus (etage 5). On ne compte que
        les APPELS : compter toute reference non resolue noierait le chiffre (232 314 contre 3 968
        appels, mesure du 2026-08-05)."""
        nonlocal unresolved
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            ent = syms.get(node.value.id)
            if ent and ent[0] == "mod":
                return (ent[1], node.attr)
            if compte:
                unresolved += 1
            return None
        if isinstance(node, ast.Name):
            ent = syms.get(node.id)
            if ent and ent[0] == "fn":
                return (ent[1], ent[2])
            if node.id in own_fns:
                return (mod, node.id)
            return None
        if compte:
            unresolved += 1
        return None

    def _scan(node):
        acc = set()
        gated = set()               # cibles conditionnelles vues APPELEES avec leur keyword
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                t = _qualify(n.func, compte=True)
                if t is not None and t in conditional:
                    if any(kw.arg == conditional[t] for kw in n.keywords):
                        gated.add(t)
                    continue                     # sans le keyword : pas d'arete
        for n in ast.walk(node):
            if isinstance(n, (ast.Name, ast.Attribute)) and isinstance(n.ctx, ast.Load):
                t = _qualify(n)
                if t is None:
                    continue
                if t in conditional and t not in gated:
                    continue
                acc.add(t)
        return acc

    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[n.name] = _scan(n)
    top = ast.Module(body=[b for b in tree.body
                           if not isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                 ast.ClassDef))],
                     type_ignores=[])
    out["<module>"] = _scan(top)
    for n in ast.walk(tree):                                    # corps de classe (methodes)
        if isinstance(n, ast.ClassDef):
            for b in n.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.setdefault("%s.%s" % (n.name, b.name), _scan(b))
    out["<unresolved>"] = unresolved
    return out


def index(files: list, root: Path, conditional: dict | None = None) -> dict:
    """`{graph, mods, bad, unresolved, per_file}` -- graphe d'appels QUALIFIE du corpus."""
    graph: dict = {}
    mods: dict = {}
    bad: list = []
    unresolved = 0
    per_file: dict = {}
    for p in files:
        tree = parse(p)
        if tree is None:
            bad.append(p)
            continue
        own = {n.name for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        res = resolve_calls(p, root, own, conditional)
        unresolved += res.pop("<unresolved>", 0)
        mod = module_name(p, root)
        mods[p] = mod
        per_file[p] = res
        for fn, calls in res.items():
            graph[(mod, fn)] = graph.get((mod, fn), set()) | calls
    return {"graph": graph, "mods": mods, "bad": bad, "unresolved": unresolved,
            "per_file": per_file}


def reaching(graph: dict, seeds: set) -> set:
    """Fermeture transitive ARRIERE : les `(module, fn)` qui atteignent l'un des `seeds`."""
    reach = set(seeds)
    changed, rounds = True, 0
    while changed and rounds < 60:
        changed, rounds = False, rounds + 1
        for node, calls in graph.items():
            if node in reach:
                continue
            if calls & reach:
                reach.add(node)
                changed = True
    return reach


# ────────────────────────────────────────────────── etage 4 : couverture par SITE

def consumer_sites(path: Path) -> list:
    """Les sites d'appel `load_state(...)` du fichier, avec leur regime de canal.

    Regimes : `given` (payload fourni), `refused` (`ability_states=False` -- contre-epreuve
    EXPLICITE, assumee), `auto` (rien de passe -> depend de l'ambiant)."""
    tree = parse(path)
    if tree is None:
        return []
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        if name != CONSUMER:
            continue
        regime = "auto"
        for kw in n.keywords:
            if kw.arg != "ability_states":
                continue
            v = kw.value
            if isinstance(v, ast.Constant) and v.value is False:
                regime = "refused"
            elif isinstance(v, ast.Constant) and v.value is None:
                regime = "auto"
            else:
                regime = "given"
        if len(n.args) >= 7:                      # 7e positionnel = `ability_states`
            regime = "given"
        out.append((n.lineno, regime))
    return out


def binds_ambient(path: Path) -> bool:
    """Le fichier lie-t-il le transport ambiant lui-meme ? (nom terminal : l'homonymie de
    `bind_live_rpc`/`live_rpc` n'existe pas dans le corpus, verifie)."""
    tree = parse(path)
    return bool(tree is not None and (called_names(tree) & set(BINDERS)))


def inherits_ambient(path: Path) -> bool:
    """Le harnais le lie pour lui : tout fichier sous `tests/` (fixture `live_session`, #363)."""
    return INHERITED_AMBIENT_DIR in path.parts


# ─────────────────────────────────────────────────────────────────────── mesure

def measure(root: Path) -> dict:
    prims, prim_indet = derive_primitives(CATALOG)
    cat_mod = module_name(CATALOG, root)
    divergentes = {(cat_mod, k) for k, v in prims.items()
                   if str(v).startswith("divergente")}
    conditional = {(cat_mod, k): str(v).split(":", 1)[1] for k, v in prims.items()
                   if str(v).startswith("divergente-si:")}
    files = corpus(root)
    idx = index(files, root, conditional)
    graph, mods = idx["graph"], idx["mods"]
    reach_graft = reaching(graph, divergentes)
    reach_read = reaching(graph, {("engine.runner.snapshot", CONSUMER)})
    greffeurs = {p for p, m in mods.items()
                 if any((m, fn) in reach_graft for fn in idx["per_file"].get(p, {}))}
    lecteurs = {p for p, m in mods.items()
                if any((m, fn) in reach_read for fn in idx["per_file"].get(p, {}))}
    greffeurs.discard(CATALOG)                      # le module des primitives n'est pas un montage
    suspects = sorted(greffeurs & lecteurs)
    rows = []
    for p in suspects:
        sites = consumer_sites(p)
        amb = binds_ambient(p) or inherits_ambient(p)
        for lineno, regime in sites:
            couvert = regime == "given" or amb
            rows.append({"file": p, "line": lineno, "regime": regime, "ambient": amb,
                         "couvert": couvert})
        if not sites:
            # Le fichier atteint `load_state` par une fonction d'un AUTRE module : le site n'est
            # pas ici. TRI-ETAT -- ni accuse ni blanchi. `ambiant=False` = a verifier a la main
            # (le module appele peut fournir le payload, ou pas) ; `ambiant=True` = couvert.
            rows.append({"file": p, "line": None, "regime": "indirect", "ambient": amb,
                         "couvert": bool(amb), "indirect": True})
    return {"primitives": prims, "divergentes": sorted(n[1] for n in divergentes),
            "prim_indet": prim_indet, "greffeurs": sorted(greffeurs), "lecteurs": sorted(lecteurs),
            "suspects": suspects, "rows": rows, "illisibles": idx["bad"],
            "unresolved": idx["unresolved"], "n_files": len(files)}


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(PYDIR)).replace("\\", "/")
    except ValueError:
        return str(p)


def report(m: dict, details: bool) -> int:
    print("== etage 1. PRIMITIVES de greffe, derivees de catalog_inject.py ==")
    for name in sorted(m["primitives"]):
        print("   %-32s %s" % (name, m["primitives"][name]))
    print("   -> DIVERGENTES (l'appelant CHOISIT l'ability) : %d" % len(m["divergentes"]))
    for x in m["prim_indet"]:
        print("   INDETERMINE : %s" % x)

    print("")
    print("== etages 2-3. fermeture transitive (graphe QUALIFIE par module) ==")
    print("   fichiers balayes                      : %d" % m["n_files"])
    print("   fichiers GREFFEURS (transitif)        : %d" % len(m["greffeurs"]))
    print("   fichiers LECTEURS de load_state       : %d" % len(m["lecteurs"]))
    print("   SUSPECTS (greffent ET chargent)       : %d" % len(m["suspects"]))

    print("")
    print("== etage 4. couverture du canal, par SITE ==")
    mauvais = [r for r in m["rows"] if not r["couvert"] and r["regime"] not in ("refused", "indirect")]
    refuses = [r for r in m["rows"] if r["regime"] == "refused"]
    indirects = [r for r in m["rows"] if r.get("indirect")]
    indet = [r for r in indirects if not r["couvert"]]
    for r in sorted(m["rows"], key=lambda r: (rel(r["file"]), r["line"] or 0)):
        if r["couvert"] and not details:
            continue
        etat = "OK" if r["couvert"] else ("INDETERMINE" if r["regime"] == "indirect" else "AMPUTE")
        print("   %-58s %-6s %-9s ambiant=%-5s %s"
              % (rel(r["file"]), r["line"] if r["line"] else "-", r["regime"],
                 r["ambient"], etat))
    print("   sites totaux %d | AMPUTES %d | refus explicite %d | indirects %d (dont %d INDETERMINES)"
          % (len(m["rows"]), len(mauvais), len(refuses), len(indirects), len(indet)))

    print("")
    print("== etage 5. PORTEE DE LA MESURE (ce que ce probe NE VOIT PAS) ==")
    print("   - une greffe faite par un AUTRE PROCESSUS : un probe qui recoit un seed BC deja")
    print("     greffe (`--seed-bc <chemin>`) ne porte aucun appel de primitive, donc n'entre pas")
    print("     dans les SUSPECTS. Le garde EXECUTABLE de `load_state` (registre de greffes du")
    print("     processus) ne le voit pas non plus -- c'est l'angle mort NOMME de la tranche.")
    print("   - les appels DYNAMIQUES (`getattr(CI, nom)`, table de callables) : le graphe est")
    print("     syntaxique.")
    print("   - appels NON RESOLUS par le graphe qualifie (`obj.methode()`, callable stocke) : %d"
          % m["unresolved"])
    print("   - fichiers ILLISIBLES (SyntaxError) : %d%s"
          % (len(m["illisibles"]), (" -- " + ", ".join(rel(p) for p in m["illisibles"]))
             if m["illisibles"] else ""))
    print("   - un site couvert par `ability_states=<expr>` n'est pas verifie NON VIDE ici : un")
    print("     payload en erreur passerait pour une mesure (cf. `probe_478`, qui l'assertionne).")

    print("")
    if mauvais:
        print("VERDICT : %d site(s) AMPUTE(S) -- greffe montee, canal muet, port ampute." % len(mauvais))
        return 1
    print("VERDICT : 0 site ampute sur %d suspect(s)." % len(m["suspects"]))
    return 0


# ─────────────────────────────────────────────────────────────── contre-epreuve

MUTANT_GREFFE = '''
import catalog_inject as CI
from engine.runner.snapshot import load_state
def montage(bc, rid, dv, ob, snap):
    CI.graft_passive_ability(bc, "tauCrisis", "Cleave")
    return load_state(dv, ob, snap)
'''

MUTANT_COUVERT = '''
import catalog_inject as CI
from engine.runner.snapshot import load_state
def montage(bc, rid, dv, ob, snap, ast):
    CI.graft_passive_ability(bc, "tauCrisis", "Cleave")
    return load_state(dv, ob, snap, ability_states=ast)
'''


MUTANT_INDIRECT = '''
import montage_partage as MP
def scenario(dv, ob, snap):
    return MP.monter_et_charger(dv, ob, snap)
'''

MUTANT_PARTAGE = '''
import catalog_inject as CI
from engine.runner.snapshot import load_state
def monter_et_charger(dv, ob, snap):
    CI.equip_relic({}, "tauCrisis", "AmuletOfTheVoidwyrm")
    return load_state(dv, ob, snap)
'''


def mutate() -> int:
    """Le probe sait-il ECHOUER ? Quatre fichiers synthetiques : ampute / couvert / le meme vice
    reparti sur DEUX modules (transitivite) / l'appelant qui n'y touche pas."""
    import tempfile
    rc = 0
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "mutant_ampute.py").write_text(MUTANT_GREFFE, encoding="utf-8")
        (base / "mutant_couvert.py").write_text(MUTANT_COUVERT, encoding="utf-8")
        (base / "montage_partage.py").write_text(MUTANT_PARTAGE, encoding="utf-8")
        (base / "mutant_indirect.py").write_text(MUTANT_INDIRECT, encoding="utf-8")
        prims, _ = derive_primitives(CATALOG)
        divergentes = {("catalog_inject", k) for k, v in prims.items() if v == "divergente"}
        idx = index(corpus(base), base)
        reach_graft = reaching(idx["graph"], divergentes)
        reach_read = reaching(idx["graph"], {("engine.runner.snapshot", CONSUMER)})
        mods = idx["mods"]
        greffeurs = {p for p, m in mods.items()
                     if any((m, fn) in reach_graft for fn in idx["per_file"].get(p, {}))}
        lecteurs = {p for p, m in mods.items()
                    if any((m, fn) in reach_read for fn in idx["per_file"].get(p, {}))}
        suspects = sorted(greffeurs & lecteurs)
        print("== contre-epreuve : 4 fichiers synthetiques ==")
        print("   suspects detectes : %s" % ", ".join(sorted(p.name for p in suspects)))
        verdicts = {}
        for p in suspects:
            amb = binds_ambient(p)
            sites = consumer_sites(p)
            verdicts[p.name] = all((r == "given" or amb) for _l, r in sites) if sites else None
        print("   verdicts : %s" % verdicts)
        attendu = {"mutant_ampute.py": False, "mutant_couvert.py": True,
                   "montage_partage.py": False, "mutant_indirect.py": None}
        for nom, att in attendu.items():
            if nom not in verdicts:
                print("   ECHEC : %s n'est meme pas SUSPECT" % nom)
                rc = 1
            elif verdicts[nom] is not att:
                print("   ECHEC : %s -> %r, attendu %r" % (nom, verdicts[nom], att))
                rc = 1
    print("   %s" % ("OK -- le probe discrimine" if rc == 0 else "KO"))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mutate", action="store_true", help="contre-epreuve synthetique")
    ap.add_argument("--details", action="store_true", help="imprime AUSSI les sites couverts")
    a = ap.parse_args()
    if a.mutate:
        return mutate()
    return report(measure(PYDIR), a.details)


if __name__ == "__main__":
    sys.exit(main())
