"""#326 phase 2 -- ETAGE A (2/2) : APPARIEMENT primitive native <-> port Python, PAR ARTEFACT.

Consomme `logs/326_dsl_primitives_native.tsv` (produit par `probe_326_dsl_primitive_inventory.py`)
et introspecte les DEUX facades du port :

  * `engine.dsl.nodes`                      -- mirror de la classe-factory native (kinds T/S/V + les
    COMBINATEURS E purs) ; c'est le point de construction unique cote Python.
  * `engine.runner.abilities.behaviours`    -- les feuilles E RUNNER-COUPLEES (meme namespace natif
    `IdunBattle.Entities.Behaviours`, separees par LAYERING, pas par artefact).

METHODE -- on classe par ARTEFACT, jamais par nom. Pour chaque export Python on lit son SOURCE
(`inspect.getsource`) et on en extrait les symboles natifs cites (`X$$Y`, `DSL*.Y`). Le verdict
croise alors DEUX signaux independants :

  1. existe-t-il un export Python HOMONYME de la primitive native ?
  2. cet export CITE-T-IL la primitive homonyme (ou une classe de noeud du meme nom) ?

  -> `PORTE`             : homonyme ET artefact homonyme cite (les deux signaux concordent).
  -> `PORTE_ARTEFACT_AUTRE` : homonyme MAIS le port ne cite QUE d'autres artefacts. C'est le piege
     `Heal`/`Repair` (un nom Python qui dit `Heal` alors qu'il construit un `Repair`) : a relire
     a la main, jamais compte comme porte sur la foi du nom.
  -> `PORTE_SANS_CITATION` : homonyme et AUCUN symbole natif cite -> port non ATTESTE.
  -> `PORTE_HORS_FACADE` : pas d'homonyme en facade, mais la primitive est citee ailleurs dans
     `scripts/python/engine/**` (port inline dans une ability / une operation).
  -> `NON_PORTE`         : aucun des deux.

Sortie : `logs/326_dsl_primitive_coverage.tsv` (chemin RELATIF au checkout) + un resume ASCII.
"""
from __future__ import annotations

import argparse
import inspect
import io
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "scripts", "python"))

SYMBOL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.<>]*?)\$\$([A-Za-z_][A-Za-z0-9_]*)")
DOTTED_RE = re.compile(r"\bDSL(?:Factory|Behaviors|Selectors|Formulas|Triggers)\.([A-Za-z_][A-Za-z0-9_]*)")


def read_native(path):
    rows = []
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or line.startswith("family\t"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 5:
                continue
            rows.append({"family": p[0], "name": p[1], "symbol": p[2],
                         "ov_frida": int(p[3]), "ov_ghidra": int(p[4])})
    return rows


def facade_exports():
    """{nom Python -> dict(source, file, line, facade)} des DEUX facades du port."""
    import engine.dsl.nodes as facade
    import engine.runner.abilities.behaviours as leaves

    out = {}
    for label, mod in (("dsl.nodes", facade), ("runner.behaviours", leaves)):
        names = getattr(mod, "__all__", None) or [n for n in dir(mod) if not n.startswith("_")]
        for name in names:
            obj = getattr(mod, name, None)
            if obj is None or not (inspect.isclass(obj) or inspect.isfunction(obj)):
                continue
            try:
                src = inspect.getsource(obj)
                fpath = inspect.getsourcefile(obj) or ""
                lineno = inspect.getsourcelines(obj)[1]
            except (OSError, TypeError):
                src, fpath, lineno = "", "", 0
            rel = os.path.relpath(fpath, REPO).replace("\\", "/") if fpath else ""
            prev = out.get(name)
            # Un nom expose par les DEUX facades (re-export) : on garde la 1re occurrence, on note.
            if prev is not None:
                prev["facades"].add(label)
                continue
            out[name] = {"source": src, "file": rel, "line": lineno, "facades": {label},
                         "kind": "class" if inspect.isclass(obj) else "function"}
    return out


def cited_symbols(src):
    """Symboles natifs cites dans un bloc de source : set de (classe, methode) + set de methodes
    citees en forme pointee `DSL*.Meth`."""
    pairs, dotted = set(), set()
    for m in SYMBOL_RE.finditer(src):
        pairs.add((m.group(1), m.group(2)))
    for m in DOTTED_RE.finditer(src):
        dotted.add(m.group(1))
    return pairs, dotted


def scan_whole_port():
    """{meth -> [(fichier, ligne, porteur)]} de TOUTES les citations de primitive DSL du port."""
    hits = defaultdict(list)
    root = os.path.join(REPO, "scripts", "python", "engine")
    def_re = re.compile(r"^(\s*)(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, REPO).replace("\\", "/")
            stack = []
            with io.open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    m = def_re.match(line)
                    if m:
                        indent = len(m.group(1))
                        while stack and stack[-1][0] >= indent:
                            stack.pop()
                        stack.append((indent, m.group(3)))
                    holder = ".".join(s[1] for s in stack) or "<module>"
                    for cm in SYMBOL_RE.finditer(line):
                        if cm.group(1).split(".")[-1].startswith("DSL"):
                            hits[cm.group(2)].append((rel, lineno, holder))
                    for dm in DOTTED_RE.finditer(line):
                        hits[dm.group(1)].append((rel, lineno, holder))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--native", default="logs/326_dsl_primitives_native.tsv")
    ap.add_argument("--out", default="logs/326_dsl_primitive_coverage.tsv")
    args = ap.parse_args()

    native = read_native(os.path.join(REPO, args.native))
    exports = facade_exports()
    port_hits = scan_whole_port()

    # Pre-calcul des artefacts cites par export.
    cited = {}
    for name, e in exports.items():
        cited[name] = cited_symbols(e["source"])

    rows = []
    for prim in native:
        name, fam = prim["name"], prim["family"]
        exp = exports.get(name)
        verdict, evidence, where = "NON_PORTE", "", ""
        if exp is not None:
            pairs, dotted = cited[name]
            homonym = [c for (c, m) in pairs if m == name]
            # Un port peut aussi citer la CLASSE DE NOEUD homonyme (`XSelector$$Select`,
            # `XBehaviour$$Execute`, `XFormula$$Calculate`, `XTrigger$$ShouldTrigger`).
            node_cls = [c for (c, m) in pairs
                        if c.rsplit(".", 1)[-1].rstrip("0123456789").startswith(name)
                        and c.rsplit(".", 1)[-1] != name]
            if homonym or name in dotted:
                verdict = "PORTE"
                evidence = (homonym[0] + "$$" + name) if homonym else ("DSL*." + name)
            elif node_cls:
                verdict = "PORTE"
                evidence = "noeud:" + sorted(set(node_cls))[0]
            elif pairs or dotted:
                verdict = "PORTE_ARTEFACT_AUTRE"
                evidence = ";".join(sorted({"%s$$%s" % p for p in pairs})[:3])
            else:
                verdict = "PORTE_SANS_CITATION"
            where = "%s:%d" % (exp["file"], exp["line"])
        elif name in port_hits:
            verdict = "PORTE_HORS_FACADE"
            f, l, h = port_hits[name][0]
            evidence = "%d citation(s)" % len(port_hits[name])
            where = "%s:%d (%s)" % (f, l, h)
        rows.append({
            "family": fam, "name": name, "symbol": prim["symbol"],
            "ov_frida": prim["ov_frida"], "ov_ghidra": prim["ov_ghidra"],
            "verdict": verdict, "evidence": evidence, "port_site": where,
        })

    out_path = os.path.join(REPO, args.out)
    if not os.path.isdir(os.path.dirname(out_path)):
        os.makedirs(os.path.dirname(out_path))
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.coverage.v1\n")
        fh.write("family\tname\tsymbol\toverloads_frida\toverloads_ghidra\tverdict\tevidence\tport_site\n")
        for r in sorted(rows, key=lambda r: (r["family"], r["name"])):
            fh.write("%s\t%s\t%s\t%d\t%d\t%s\t%s\t%s\n" % (
                r["family"], r["name"], r["symbol"], r["ov_frida"], r["ov_ghidra"],
                r["verdict"], r["evidence"], r["port_site"]))

    # Exports Python SANS primitive native homonyme -> a expliquer (alias de port, classe de noeud
    # portee directement, ou nom invente).
    native_names = {p["name"] for p in native}
    orphans = sorted(n for n in exports if n not in native_names)

    counts = defaultdict(lambda: defaultdict(int))
    for r in rows:
        counts[r["family"]][r["verdict"]] += 1
    verdicts = ["PORTE", "PORTE_ARTEFACT_AUTRE", "PORTE_SANS_CITATION", "PORTE_HORS_FACADE", "NON_PORTE"]
    print("primitives natives : %d" % len(rows))
    print("%-12s %s" % ("famille", " ".join("%-21s" % v for v in verdicts)))
    tot = defaultdict(int)
    for fam in sorted(counts):
        print("%-12s %s" % ("DSL" + fam, " ".join("%-21d" % counts[fam][v] for v in verdicts)))
        for v in verdicts:
            tot[v] += counts[fam][v]
    print("%-12s %s" % ("TOTAL", " ".join("%-21d" % tot[v] for v in verdicts)))
    print("exports Python sans primitive native homonyme : %d" % len(orphans))
    print("  %s" % ", ".join(orphans[:40]))
    print("ecrit : %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
