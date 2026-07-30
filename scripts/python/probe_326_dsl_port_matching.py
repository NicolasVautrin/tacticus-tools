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

  -> `PORTE`                : homonyme ET artefact homonyme cite (les deux signaux concordent).
  -> `PORTE_ALIAS_FACADE`   : pas d'homonyme, mais un export de FACADE cite la CLASSE DE NOEUD de
     la primitive -> port sous un AUTRE NOM Python (`PushUnit`/`MoveUnit` portent
     `DisplaceUnitBehaviour`). Chercher par homonymie seule l'aurait declare absent.
  -> `PORTE_HORS_FACADE`    : porte inline dans une ability / une operation, avec un porteur
     plausible (le nom de la primitive est dans le fichier ou la classe englobante).
  -> `PORTE_ARTEFACT_AUTRE` : homonyme MAIS le port ne cite QUE d'autres artefacts. C'est le piege
     `Heal`/`Repair` (un nom Python qui dit `Heal` alors qu'il construit un `Repair`) : a relire
     a la main, jamais compte comme porte sur la foi du nom.
  -> `PORTE_SANS_CITATION`  : homonyme et AUCUN symbole natif cite -> port non ATTESTE.
  -> `CITE_A_QUALIFIER`     : l'artefact apparait dans `engine/**` sans porteur plausible. NI porte
     NI absent -- non tranche (mention documentaire, ou port sous un nom trop eloigne).
  -> `NON_PORTE`            : aucune trace de l'artefact dans `engine/**`.

Le tableau de sortie ECHOUE si un verdict produit n'y figure pas : un total ampute se lirait
comme une couverture.

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
# Classe de NOEUD citee SANS `$$` (le port nomme souvent le TYPE construit, pas une de ses
# methodes) : `IdunBattle.Entities.Formulas.CurrentStatModifierAmountFormula`,
# `Idun.Source.IdunBattle.Logic.Entities.Behaviours.RefreshDynamicStatModifierValueBehaviour`.
# Sans ce canal, ces ports sortaient en `PORTE_ARTEFACT_AUTRE` -- un faux positif du piege
# Heal/Repair, qui aurait envoye relire a la main des ports parfaitement attestes.
NODECLS_RE = re.compile(
    r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)*(?:Entities\.(?:Selectors|Formulas|Behaviours|Triggers)|DSL)\."
    r"([A-Za-z_][A-Za-z0-9_]*)")


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
            # Les facades font `from ... import *` : elles re-exportent aussi ce qu'elles ont
            # elles-memes importe de la stdlib (`dataclass`, `field`, `replace`). Ce ne sont pas
            # des noeuds -- les compter comme « exports sans artefact natif » serait un faux.
            if not (getattr(obj, "__module__", "") or "").startswith("engine"):
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
    """Artefacts natifs cites dans un bloc de source, par TROIS canaux :
      * `pairs`   -- (classe, methode) d'un symbole `X$$Y` ;
      * `dotted`  -- methode d'une forme pointee `DSL*.Meth` ;
      * `nodecls` -- nom court d'une CLASSE DE NOEUD citee sans `$$`."""
    pairs, dotted, nodecls = set(), set(), set()
    for m in SYMBOL_RE.finditer(src):
        pairs.add((m.group(1), m.group(2)))
        nodecls.add(m.group(1).rsplit(".", 1)[-1])
    for m in DOTTED_RE.finditer(src):
        dotted.add(m.group(1))
    for m in NODECLS_RE.finditer(src):
        nodecls.add(m.group(1))
    return pairs, dotted, nodecls


NODE_SUFFIXES = ("Selector", "Behaviour", "Formula", "Trigger", "Node", "Ability")


def _matches_node_class(name, nodecls):
    """Une classe de noeud citee correspond-elle a la primitive `name` ? Le natif nomme le type
    `<Primitive><Suffixe>` (`FilterSelector`, `AddEffectBehaviour`, `SumFormula`). Egalite stricte
    sur le prefixe + suffixe connu : `Heal` ne doit pas capturer `HealingBalmsBehaviour`."""
    for c in nodecls:
        if c == name:
            return c
        if c.startswith(name):
            rest = c[len(name):]
            if rest in NODE_SUFFIXES or rest.rstrip("0123456789") in NODE_SUFFIXES:
                return c
    return None


def scan_whole_port():
    """Deux index des citations d'artefact DSL dans TOUT `scripts/python/engine/**` :
      * `hits`      {methode de factory -> [(fichier, ligne, porteur)]}
      * `node_hits` {nom court de classe de NOEUD -> [(fichier, ligne, porteur)]}
    Le second existe parce qu'un port peut nommer le TYPE construit sans jamais nommer la factory
    -- l'ignorer produirait un faux `NON_PORTE`."""
    hits, node_hits = defaultdict(list), defaultdict(list)
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
                        node_hits[cm.group(1).rsplit(".", 1)[-1]].append((rel, lineno, holder))
                    for dm in DOTTED_RE.finditer(line):
                        hits[dm.group(1)].append((rel, lineno, holder))
                    for nm in NODECLS_RE.finditer(line):
                        node_hits[nm.group(1)].append((rel, lineno, holder))
    return hits, node_hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--native", default="logs/326_dsl_primitives_native.tsv")
    ap.add_argument("--out", default="logs/326_dsl_primitive_coverage.tsv")
    args = ap.parse_args()

    native = read_native(os.path.join(REPO, args.native))
    exports = facade_exports()
    port_hits, node_hits = scan_whole_port()

    # Pre-calcul des artefacts cites par export, + index inverse classe-de-noeud -> exports.
    # Cet index est ce qui permet de reconnaitre un port sous un NOM PYTHON DIFFERENT : le port
    # `PushUnit`/`MoveUnit` mirrore `DisplaceUnitBehaviour`, donc la primitive `DisplaceUnit` EST
    # portee -- la chercher par homonymie seule la declarerait absente.
    cited, facade_by_nodecls = {}, defaultdict(list)
    for name, e in exports.items():
        cited[name] = cited_symbols(e["source"])
        for nc in cited[name][2]:
            facade_by_nodecls[nc].append(name)

    rows = []
    for prim in native:
        name, fam = prim["name"], prim["family"]
        exp = exports.get(name)
        verdict, evidence, where = "NON_PORTE", "", ""
        if exp is not None:
            pairs, dotted, nodecls = cited[name]
            homonym = [c for (c, m) in pairs if m == name]
            node_cls = _matches_node_class(name, nodecls)
            if homonym or name in dotted:
                verdict = "PORTE"
                evidence = (homonym[0] + "$$" + name) if homonym else ("DSL*." + name)
            elif node_cls:
                verdict = "PORTE"
                evidence = "noeud:" + node_cls
            elif pairs or dotted:
                verdict = "PORTE_ARTEFACT_AUTRE"
                evidence = ";".join(sorted({"%s$$%s" % p for p in pairs})[:3])
            else:
                verdict = "PORTE_SANS_CITATION"
            where = "%s:%d" % (exp["file"], exp["line"])
        else:
            # Pas d'export homonyme. Trois canaux, du plus fort au plus faible :
            #  (a) un export de FACADE cite la classe de noeud -> port sous un AUTRE NOM Python ;
            #  (b) la primitive est citee ailleurs dans `engine/**` avec un porteur PLAUSIBLE
            #      (son nom apparait dans le fichier ou la classe englobante) -> port inline ;
            #  (c) citee sans porteur plausible -> A QUALIFIER (mention documentaire ou port sous
            #      un nom trop eloigne). Ce n'est PAS « non porte » : c'est non tranche.
            alias_nc = _matches_node_class(name, set(facade_by_nodecls))
            cites = list(port_hits.get(name, ()))
            nc = _matches_node_class(name, set(node_hits))
            if nc:
                cites += list(node_hits[nc])
            if alias_nc:
                alias = sorted(facade_by_nodecls[alias_nc])[0]
                verdict = "PORTE_ALIAS_FACADE"
                evidence = "noeud:%s porte par `%s`" % (alias_nc, alias)
                ex = exports[alias]
                where = "%s:%d" % (ex["file"], ex["line"])
            elif cites:
                low = name.lower()
                owned = [c for c in cites
                         if low in c[2].lower() or low in os.path.basename(c[0]).lower()]
                f, l, h = (owned or cites)[0]
                verdict = "PORTE_HORS_FACADE" if owned else "CITE_A_QUALIFIER"
                evidence = "%d citation(s)%s" % (len(cites), (" noeud:" + nc) if nc else "")
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

    # AXE SYMETRIQUE : les exports Python SANS primitive native homonyme. Un nom Python qui ne
    # correspond a aucune primitive n'est pas forcement faux -- il peut porter la CLASSE DE NOEUD
    # (alias) ou n'etre qu'une piece d'infrastructure du port. Mais il peut aussi etre un nom
    # INVENTE, et c'est precisement ce qu'il faut pouvoir nommer.
    native_names = {p["name"] for p in native}
    orphans = sorted(n for n in exports if n not in native_names)
    orphan_rows = []
    for name in orphans:
        pairs, dotted, nodecls = cited[name]
        if pairs or dotted:
            state = "ALIAS_ARTEFACT"
            ev = ";".join(sorted({"%s$$%s" % p for p in pairs})[:2]) or ("DSL*." + sorted(dotted)[0])
        elif nodecls:
            state = "ALIAS_ARTEFACT"
            ev = "noeud:" + sorted(nodecls)[0]
        else:
            state = "SANS_ARTEFACT_CITE"
            ev = "-"
        # La 1re ligne de docstring est ce qui permet de trancher A LA LECTURE entre un slot de
        # factory (`caster@+0x168`), un operateur (`op_BitwiseAnd`), une piece d'infrastructure du
        # port et un nom reellement invente. On la rend au lieu de laisser deviner.
        doc = (exports[name]["source"] or "").split('"""')
        first = doc[1].strip().split("\n")[0][:140].replace("\t", " ") if len(doc) > 1 else "-"
        orphan_rows.append((name, state, ev,
                            "%s:%d" % (exports[name]["file"], exports[name]["line"]), first))
    orph_path = os.path.join(os.path.dirname(out_path), "326_dsl_port_orphans.tsv")
    with io.open(orph_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.orphans.v2\n")
        fh.write("export\tstate\tevidence\tsite\tdoc\n")
        for row in orphan_rows:
            fh.write("\t".join(row) + "\n")

    counts = defaultdict(lambda: defaultdict(int))
    for r in rows:
        counts[r["family"]][r["verdict"]] += 1
    verdicts = ["PORTE", "PORTE_ALIAS_FACADE", "PORTE_HORS_FACADE", "PORTE_ARTEFACT_AUTRE",
                "PORTE_SANS_CITATION", "CITE_A_QUALIFIER", "NON_PORTE"]
    # Garde : aucun verdict produit ne doit manquer au tableau -- une colonne oubliee ferait
    # DISPARAITRE des primitives du total, et un total ampute se lit comme une couverture.
    unknown = {r["verdict"] for r in rows} - set(verdicts)
    if unknown:
        raise SystemExit("verdicts non listes dans le tableau : %s" % ", ".join(sorted(unknown)))
    print("primitives natives : %d" % len(rows))
    print("%-12s %s" % ("famille", " ".join("%-20s" % v for v in verdicts)))
    tot = defaultdict(int)
    for fam in sorted(counts):
        print("%-12s %s" % ("DSL" + fam, " ".join("%-20d" % counts[fam][v] for v in verdicts)))
        for v in verdicts:
            tot[v] += counts[fam][v]
    print("%-12s %s" % ("TOTAL", " ".join("%-20d" % tot[v] for v in verdicts)))
    assert sum(tot.values()) == len(rows), "total != nombre de primitives"
    n_sans = sum(1 for r in orphan_rows if r[1] == "SANS_ARTEFACT_CITE")
    print("exports Python sans primitive native homonyme : %d "
          "(%d citent un artefact = ALIAS, %d n'en citent AUCUN)"
          % (len(orphans), len(orphans) - n_sans, n_sans))
    print("  sans artefact cite : %s"
          % ", ".join(r[0] for r in orphan_rows if r[1] == "SANS_ARTEFACT_CITE"))
    print("ecrit : %s" % args.out)
    print("ecrit : %s" % os.path.relpath(orph_path, REPO).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
