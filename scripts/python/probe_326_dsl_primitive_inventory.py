"""#326 phase 2 -- ETAGE A : inventaire du VOCABULAIRE DSL natif et de sa couverture PORT.

Ce probe MESURE, il ne conclut pas. Il produit deux tables machine dans `logs/` (chemins RELATIFS
au checkout, cf. `tests/test_314_absolute_repo_path_offline.py`) :

  * `logs/326_dsl_primitives_native.tsv`  -- une ligne par PRIMITIVE native (famille, nom, overloads,
    symbole ghidra VERBATIM d'un representant, presence dans les deux tables de symboles).
  * `logs/326_dsl_port_citations.tsv`     -- une ligne par CITATION d'un symbole natif dans le port
    Python (`scripts/python/engine/**`), avec fichier + ligne + porteur (classe/fonction englobante).

SOURCE DE VERITE = les tables de symboles VERSIONNEES du build courant
(`data/symbols/<CURRENT>/frida/methods.tsv` + `ghidra/functions.tsv`). Aucune VA absolue n'est
ecrite dans le rapport : on cite le symbole.

TRI-ETAT, pas binaire. Une primitive absente des tables n'est PAS « inexistante » :
IL2CPP deduplique les corps triviaux et, depuis le build `rnca9r7q6c`, les corps PLEINEMENT
PARTAGES (`u003C__Il2CppFullySharedGenericTypeu003E`) ne sont plus nommes du tout
(4882 -> 0, cf. `docs/rl/case-259-couverture-gshared.md`). Toute famille dont le compte tombe a 0
est donc rapportee `NON_MESURABLE`, jamais `0`.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Les 4 classes-factory du vocabulaire DSL dans le build courant. Le build `gqfc5mff6c` n'en
# exposait qu'UNE (`IdunBattleLogic.Entities.DSLFactory`) : l'eclatement en 4 est un fait de build,
# pas une reorganisation de notre part -- les deux orthographes sont donc acceptees au matching.
DSL_FACTORY_CLASSES = [
    "IdunBattleLogic.Entities.DSLBehaviors",
    "IdunBattleLogic.Entities.DSLSelectors",
    "IdunBattleLogic.Entities.DSLFormulas",
    "IdunBattleLogic.Entities.DSLTriggers",
    "IdunBattleLogic.Entities.DSLFactory",
]

# Les COMBINATEURS du DSL ne sont pas des methodes de factory : ce sont les OPERATEURS surcharges
# des 4 bases (`a & b`, `a | b`, `!a`, `a + b`, `a - b`). Les omettre a coute une erreur MESUREE :
# mon premier inventaire, restreint aux classes-factory, ratait
# `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd` -- **540 composeurs**, la primitive la PLUS
# utilisee du binaire selon la table de xrefs de la phase 1 (#325). Un vocabulaire dont il manque
# le point de composition le plus frequent n'est pas un vocabulaire.
# On ne prend QUE les `op_*` : les autres methodes de ces bases (`Select*`, `Calculate`,
# `ShouldTrigger`, `ctor`) sont l'EVALUATION du noeud, pas du vocabulaire de composition.
DSL_BASE_CLASSES = [
    "IdunBattle.DSL.AbilityTrigger",
    "IdunBattle.DSL.AbilityBehaviour",
    "IdunBattle.DSL.TargetsSelector",
    "IdunBattle.DSL.AAmountFormula",
]

# Namespaces des CLASSES DE NOEUD (le type construit par la factory). Le port cite tantot la
# factory (`DSLFactory$$Filter`), tantot la classe de noeud (`...Selectors.XSelector$$Select`).
NODE_NAMESPACES = (
    "IdunBattle.Entities.Selectors.",
    "IdunBattle.Entities.Formulas.",
    "IdunBattle.Entities.Behaviours.",
    "IdunBattle.Entities.Triggers.",
    "IdunBattleLogic.Entities.Selectors.",
    "IdunBattleLogic.Entities.Formulas.",
    "IdunBattleLogic.Entities.Behaviours.",
    "IdunBattleLogic.Entities.Triggers.",
    "IdunBattle.DSL.",
)


def _current_build() -> str:
    with io.open(os.path.join(REPO, "data", "symbols", "CURRENT"), encoding="utf-8") as fh:
        return fh.read().strip()


def load_methods(build: str):
    """`frida/methods.tsv` : <rva>\t<fullname>\t<declaring>\t<static?>\t<ret>\t<params...>.
    Source PRIMAIRE du vocabulaire (dump IL2CPP complet, pas la vue Ghidra)."""
    path = os.path.join(REPO, "data", "symbols", build, "frida", "methods.tsv")
    rows = []
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 3:
                continue
            rows.append(p)
    return rows


def load_functions(build: str):
    """`ghidra/functions.tsv` : <VA>\t<symbole ghidra verbatim>. Vue Ghidra (aval)."""
    path = os.path.join(REPO, "data", "symbols", build, "ghidra", "functions.tsv")
    syms = []
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 2:
                continue
            syms.append(p[1])
    return syms


_CACHE_INV = None


def _cache_inv():
    """Cache de verdict de l'inventaire natif (#1029), monte a la demande.

    ⚠ L'ENCODEUR EST OBLIGATOIRE ICI : les cles de `native_primitives` sont des TUPLES
    `(famille, nom)`, que JSON ne sait pas ecrire. On serialise la LISTE des entrees -- chacune
    porte deja `family` et `name`, donc la cle se reconstruit sans rien deviner. Une serialisation
    qui aplatirait la cle en chaine aurait introduit une ambiguite sur un nom contenant le
    separateur.
    """
    global _CACHE_INV
    if _CACHE_INV is None:
        from pathlib import Path                          # ce module ne l'importe pas en tete
        import verdict_cache
        ici = Path(__file__).resolve().parent
        _CACHE_INV = verdict_cache.CacheCliquet(
            "probe_326_inventaire_natif",
            contexte=verdict_cache.sha_fichiers_texte(ici / "probe_326_dsl_primitive_inventory.py"),
            encoder=lambda v, _a: [v[k] for k in sorted(v)],
            decoder=lambda v, _a: {(e["family"], e["name"]): e for e in v},
            notes=("# Cle de validation = sha256 des DEUX tables du build (`frida/methods.tsv`,",
                   "# `ghidra/functions.tsv`), toutes deux VERSIONNEES sous `data/symbols/<build>/`.",
                   "# L'inventaire ne depend que d'elles : il ne peut bouger qu'a un re-dump."))
    return _CACHE_INV


def native_primitives(build: str):
    """{(famille, nom) -> dict} depuis les DEUX tables. `famille` = suffixe de la classe-factory
    (`Behaviors`/`Selectors`/`Formulas`/`Triggers`/`Factory`).

    MESURE (#1029) : 6,1 s a froid pour balayer `frida/methods.tsv` (22,9 Mo), a chaque passe, pour
    un resultat qui ne depend QUE de deux tables versionnees. Cache par leur sha -- invalidation
    EXACTE, pas heuristique. Run a froid : `TACTICUS_SANS_CACHE_CLIQUET=1`.
    """
    import verdict_cache
    from symbols_layout import build_dir
    d = build_dir(build)
    sha = verdict_cache.sha_gros_fichiers(d / "frida" / "methods.tsv",
                                          d / "ghidra" / "functions.tsv")
    if sha is not None:
        cache = _cache_inv()
        vu = cache.obtenir("data/symbols/%s" % build, "native_primitives", sha)
        if vu is not verdict_cache.MANQUE:
            return vu
    prim = _native_primitives_brut(build)
    # On n'ecrit RIEN si l'inventaire est vide : ce serait figer un << tables absentes >> jusqu'au
    # prochain re-dump, et l'appelant se tairait ensuite sur une vraie disparition.
    if sha is not None and prim:
        cache.poser("data/symbols/%s" % build, "native_primitives", sha, prim)
        cache.enregistrer()
    return prim


def _native_primitives_brut(build: str):
    prim = {}

    for p in load_methods(build):
        full = p[1]
        decl = p[2]
        meth = full.rsplit(".", 1)[-1]
        if decl in DSL_FACTORY_CLASSES:
            pass
        elif decl in DSL_BASE_CLASSES and meth.startswith("op_"):
            pass
        else:
            continue
        fam = decl.rsplit(".", 1)[-1]
        name = full[len(decl) + 1:] if full.startswith(decl + ".") else meth
        key = (fam, name)
        e = prim.setdefault(key, {
            "family": fam, "name": name, "overloads_frida": 0, "overloads_ghidra": 0,
            "symbol": "%s$$%s" % (decl, name), "sigs": [], "decl": decl,
        })
        e["overloads_frida"] += 1
        if len(p) > 5:
            e["sigs"].append(p[5])
        elif len(p) > 4:
            e["sigs"].append("")

    ghidra_seen = defaultdict(int)
    ghidra_decl = {}
    for sym in load_functions(build):
        if "$$" not in sym:
            continue
        cls, meth = sym.split("$$", 1)
        if cls in DSL_FACTORY_CLASSES:
            pass
        elif cls in DSL_BASE_CLASSES and meth.startswith("op_"):
            pass
        else:
            continue
        fam = cls.rsplit(".", 1)[-1]
        ghidra_seen[(fam, meth)] += 1
        ghidra_decl[(fam, meth)] = cls

    for key, n in ghidra_seen.items():
        e = prim.setdefault(key, {
            "family": key[0], "name": key[1], "overloads_frida": 0, "overloads_ghidra": 0,
            "symbol": "%s$$%s" % (ghidra_decl[key], key[1]), "sigs": [],
            "decl": ghidra_decl[key],
        })
        e["overloads_ghidra"] = n
    for key, e in prim.items():
        e.setdefault("overloads_ghidra", 0)
        if key in ghidra_seen:
            e["overloads_ghidra"] = ghidra_seen[key]
    return prim


def node_classes(build: str):
    """Classes de NOEUD natives (le type que la factory construit), depuis methods.tsv."""
    out = defaultdict(set)
    for p in load_methods(build):
        decl = p[2]
        for ns in NODE_NAMESPACES:
            if decl.startswith(ns):
                short = decl[len(ns):]
                meth = p[1].rsplit(".", 1)[-1]
                out[decl].add(meth)
                out["#short#" + short].add(decl)
                break
    return out


# --- Cote PORT ---------------------------------------------------------------------------------

SYMBOL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.<>]*?)\$\$([A-Za-z_][A-Za-z0-9_]*)")
# Citation "pointee" : `DSLFactory.Filter`, `DSLSelectors.Filter`, `TargetsSelector.Select`.
DOTTED_RE = re.compile(r"\bDSL(?:Factory|Behaviors|Selectors|Formulas|Triggers)\.([A-Za-z_][A-Za-z0-9_]*)")

PY_DEF_RE = re.compile(r"^(\s*)(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)")


def scan_port(root):
    """Toutes les citations de symbole natif dans le port Python, avec leur PORTEUR (la derniere
    `class`/`def` de niveau <= courant). On classe par ARTEFACT (le symbole cite), jamais par
    ressemblance de nom."""
    cites = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, REPO).replace("\\", "/")
            stack = []          # [(indent, kind, name)]
            with io.open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    m = PY_DEF_RE.match(line)
                    if m:
                        indent = len(m.group(1))
                        while stack and stack[-1][0] >= indent:
                            stack.pop()
                        stack.append((indent, m.group(2), m.group(3)))
                    holder = ".".join(s[2] for s in stack) or "<module>"
                    for cm in SYMBOL_RE.finditer(line):
                        cites.append({
                            "file": rel, "line": lineno, "holder": holder,
                            "kind": "symbol", "cls": cm.group(1), "meth": cm.group(2),
                        })
                    for dm in DOTTED_RE.finditer(line):
                        cites.append({
                            "file": rel, "line": lineno, "holder": holder,
                            "kind": "dotted", "cls": "DSL*", "meth": dm.group(1),
                        })
    return cites


MARQUEUR_GSHARED = "__Il2CppFullySharedGeneric"     # meme marqueur que probe_259

# Le compte gshared depend du MOTIF, et deux lectures honnetes peuvent differer d'un facteur 1,7
# sans se contredire : les motifs sont EMBOITES. Mesure sur `rnca9r7q6c`, colonne SYMBOLE de
# `ghidra/functions.tsv`, test `in` (sous-chaine, pas regex) -- 4874 / 4011 / 912 / 2830. On les
# publie tous les quatre plutot que d'en imposer un : un chiffre gshared sans son motif n'est pas
# une mesure, c'est une opinion.
MOTIFS_GSHARED = (
    "__Il2CppFullySharedGeneric",                    # prefixe -- celui de probe_259
    "FullySharedGenericType",
    "FullySharedGenericStructType",
    "u003C__Il2CppFullySharedGenericTypeu003E",      # forme delimitee complete
)


def gshared_axis_check(build):
    """L'axe VOCABULAIRE est-il MESURABLE sur ce build, ou aveugle comme l'axe UTILITY ?

    Rendre `0` primitives portees sur un axe INVISIBLE se lirait « rien a signaler » (defaut
    #273) : on MESURE au lieu de supposer, ET on mesure DANS LA BONNE TABLE.

    Point de methode qui a failli me faire ecrire un faux : les corps pleinement partages
    (`u003C__Il2CppFullySharedGenericTypeu003E`) n'apparaissent JAMAIS dans `frida/methods.tsv`
    -- ni avant ni apres la MAJ (0 des deux cotes) : le `methodPointer` d'une DEFINITION
    generique est un thunk d'invocation, pas le corps. Les compter la rendrait donc « 0 » sur
    tous les builds, ce qui ressemble a l'effondrement decrit par #259 sans en etre un. La table
    qui les porte est `ghidra/functions.tsv`.
    """
    rows = load_methods(build)
    n_voc = sum(1 for p in rows if p[2] in DSL_FACTORY_CLASSES)
    n_pb = sum(1 for p in rows
               if p[2].startswith("IdunBattle.AI.Playbook") or "BucketSystem" in p[2])
    n_full_frida = sum(1 for p in rows if MARQUEUR_GSHARED in "\t".join(p))
    n_full_ghidra = sum(1 for s in load_functions(build) if MARQUEUR_GSHARED in s)
    return {
        "vocabulaire DSL (methodes de factory)": (n_voc, n_voc > 0),
        "utility (Playbook/BucketSystem), table frida": (n_pb, n_pb > 0),
        "corps pleinement partages, table frida": (n_full_frida, None),
        "corps pleinement partages, table ghidra (#259)": (n_full_ghidra, n_full_ghidra > 0),
    }


def compare_builds(build_a, build_b):
    """Noms de primitive gagnes/perdus entre deux builds VERSIONNES. Sert a distinguer
    « la primitive a disparu du jeu » de « la table ne la nomme plus »."""
    a = {name for (_f, name) in native_primitives(build_a)}
    b = {name for (_f, name) in native_primitives(build_b)}
    return sorted(a - b), sorted(b - a), len(a), len(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="logs")
    ap.add_argument("--compare", default=None,
                    help="hash d'un build VERSIONNE a comparer (ex. gqfc5mff6c)")
    args = ap.parse_args()

    build = _current_build()
    out_dir = os.path.join(REPO, args.out_dir)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    prim = native_primitives(build)
    fam_counts = defaultdict(int)
    for (fam, _name) in prim:
        fam_counts[fam] += 1

    p_native = os.path.join(out_dir, "326_dsl_primitives_native.tsv")
    with io.open(p_native, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.native.v1\tbuild=%s\n" % build)
        fh.write("family\tname\tsymbol\toverloads_frida\toverloads_ghidra\n")
        for (fam, name) in sorted(prim):
            e = prim[(fam, name)]
            fh.write("%s\t%s\t%s\t%d\t%d\n" % (
                fam, name, e["symbol"], e["overloads_frida"], e["overloads_ghidra"]))

    cites = scan_port(os.path.join(REPO, "scripts", "python", "engine"))
    p_cites = os.path.join(out_dir, "326_dsl_port_citations.tsv")
    with io.open(p_cites, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.citations.v1\tbuild=%s\n" % build)
        fh.write("file\tline\tholder\tkind\tcls\tmeth\n")
        for c in cites:
            fh.write("%s\t%d\t%s\t%s\t%s\t%s\n" % (
                c["file"], c["line"], c["holder"], c["kind"], c["cls"], c["meth"]))

    nodes = node_classes(build)
    n_node_cls = len([k for k in nodes if not k.startswith("#short#")])

    print("build=%s" % build)
    print("primitives DSL natives par famille :")
    for fam in sorted(fam_counts):
        print("  %-22s %4d" % (fam, fam_counts[fam]))
    print("  %-22s %4d" % ("TOTAL", len(prim)))
    print("classes de NOEUD natives (namespaces Selectors/Formulas/Behaviours/Triggers/DSL) : %d" % n_node_cls)
    print("citations de symbole natif dans scripts/python/engine/** : %d" % len(cites))

    print("MESURABILITE des axes (methodes NOMMEES dans la table du build) :")
    for b in ([build] + ([args.compare] if args.compare else [])):
        print("  -- build %s" % b)
        for label, (n, ok) in gshared_axis_check(b).items():
            state = ("attendu -- cette table ne porte JAMAIS ces corps" if ok is None
                     else ("MESURABLE" if ok else "NON MESURABLE (aucun corps nomme)"))
            print("     %-48s %5d  %s" % (label, n, state))
        syms = load_functions(b)
        meths = ["\t".join(p) for p in load_methods(b)]
        print("     -- decomposition par MOTIF (un chiffre gshared sans son motif n'est pas une mesure)")
        for m in MOTIFS_GSHARED:
            print("        %-44s ghidra=%5d  frida=%5d"
                  % (m, sum(1 for s in syms if m in s), sum(1 for s in meths if m in s)))

    if args.compare:
        lost, gained, na, nb = compare_builds(args.compare, build)
        print("comparaison %s -> %s : %d -> %d noms de primitive" % (args.compare, build, na, nb))
        print("  disparus : %s" % (", ".join(lost) or "(aucun)"))
        print("  apparus  : %s" % (", ".join(gained) or "(aucun)"))
    print("ecrit : %s" % os.path.relpath(p_native, REPO).replace("\\", "/"))
    print("ecrit : %s" % os.path.relpath(p_cites, REPO).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
