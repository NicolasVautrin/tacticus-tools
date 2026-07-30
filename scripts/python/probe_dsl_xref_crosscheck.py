#!/usr/bin/env python3
"""CONTRE-EPREUVE de la carte DSL : les xrefs disent-elles la meme chose que le TEXTE
du decompile ?

POURQUOI ce probe existe
    `dsl_xref_map.py` derive tout le graphe d'usage d'UNE source : les xrefs Ghidra.
    Une source unique qui se valide elle-meme ne prouve rien -- si le filtre de type,
    la normalisation des closures ou le batch avaient un biais, la carte serait fausse
    ET coherente. On recoupe donc par une source INDEPENDANTE : le pseudo-C rendu par
    `decompile_function`, ou les appels apparaissent en clair.

    Ce n'est pas un doublon : les xrefs viennent de l'analyse de flot de Ghidra, le
    texte du decompile de son moteur de rendu. Un desaccord localise l'erreur.

CE QUE LE PROBE MESURE, par site de composition tire au sort :
    * primitives citees dans le TEXTE mais ABSENTES des aretes -> la carte en rate ;
    * primitives dans les aretes mais ABSENTES du texte -> sur-comptage (ou appel
      resolu par flot que le rendu n'ecrit pas tel quel).

CE QU'IL NE PEUT PAS TRANCHER
    Un appel INLINE par le compilateur n'apparait ni en xref ni comme appel nomme
    dans le texte : les deux sources sont aveugles ensemble. Un accord parfait ne
    prouve donc pas l'exhaustivite -- il prouve l'absence de biais ENTRE les deux
    lectures. C'est exactement la limite que `feedback_agreement_worthless_on_shared
    _stale_input` decrit : deux lecteurs d'une meme entree morte s'accordent.

Usage :
    python scripts/python/probe_dsl_xref_crosscheck.py [--sample 12] [--seed 0]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from ghidra_symbols import BINARY, GhidraMCP, loaded_build      # noqa: E402
from dsl_xref_map import (REPO, TABLES, call_batch, is_primitive,  # noqa: E402
                          load_functions, owner_of, split_symbol)


def load_edges() -> dict:
    """(owner, site_method) -> {primitive}. Depuis le CONTRAT machine, pas le brut."""
    p = TABLES / "dsl-usage-edges.tsv"
    if not p.exists():
        raise SystemExit("carte absente (%s) : lancer `dsl_xref_map.py all` d'abord"
                         % p.relative_to(REPO).as_posix())
    out = defaultdict(set)
    hdr = None
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            f = line.rstrip("\n").split("\t")
            if hdr is None:
                hdr = f
                continue
            out[(f[3], f[6])].add(f[0])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    g = GhidraMCP(timeout=240).connect()
    build = loaded_build(g)
    current = (REPO / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    if build != current:
        print("STOP  ghidra-mcp sert %s, CURRENT dit %s" % (build, current))
        return 2

    funcs = load_functions(build)
    prim_names = sorted({s for _a, s in funcs if is_primitive(s)})
    # index nom court -> symbole complet, pour reconnaitre les appels dans le texte
    short2full = defaultdict(set)
    for s in prim_names:
        cls, meth = split_symbol(s)
        short2full["%s$$%s" % (cls.rsplit(".", 1)[-1], meth)].add(s)

    edges = load_edges()
    # sites candidats : fonctions qui portent au moins une arete (donc comparables)
    sites = sorted({(o, m) for (o, m) in edges})
    rnd = random.Random(args.seed)
    picked = rnd.sample(sites, min(args.sample, len(sites)))

    # Retrouver l'ADRESSE de chaque site. `decompile_function` ne resout PAS un
    # symbole IL2CPP passe par nom (`... not found` sur un nom pourtant present dans
    # la table) : on l'interroge par adresse, seule forme fiable ici.
    by_owner_meth = defaultdict(list)
    addr_of = {}
    for a, s in funcs:
        o, m = owner_of(s)
        by_owner_meth[(o, m)].append(s)
        addr_of[s] = a

    targets, addr2site = [], {}
    for o, m in picked:
        for full in by_owner_meth.get((o, m), []):
            a = addr_of[full]
            targets.append(a)
            addr2site[a.lower()] = (o, m)
    if not targets:
        print("aucun site resolvable -- rien a recouper")
        return 1

    print("build=%s  sites tires=%d  fonctions a decompiler=%d"
          % (build, len(picked), len(targets)))

    text_by_site = defaultdict(str)
    step = 4
    for i in range(0, len(targets), step):
        chunk = targets[i:i + step]
        try:
            res = call_batch(g, "decompile_function",
                             {"binary_name": BINARY, "name_or_address": chunk,
                              "include_callees": True, "timeout_sec": 90})
        except Exception as exc:                              # noqa: BLE001
            print("  WARN  decompile %d-%d : %s" % (i, i + len(chunk), str(exc)[:100]))
            continue
        for j, ent in enumerate(res):
            if ent.get("error"):
                print("  WARN  %s : %s" % (chunk[j] if j < len(chunk) else "?",
                                           str(ent["error"])[:90]))
                continue
            code = ent.get("code") or ""
            # `callees` est une seconde lecture, plus directe que le texte : on
            # concatene les deux, une primitive citee par l'une ou l'autre compte.
            callees = ent.get("callees") or []
            if isinstance(callees, list):
                code += "\n" + "\n".join(
                    c if isinstance(c, str) else str(c.get("name", "")) for c in callees)
            name = ent.get("name") or ""
            key = addr2site.get((chunk[j] if j < len(chunk) else "").lower())
            if key is None and name:
                key = owner_of(name)
            if key is None or not code.strip():
                continue
            text_by_site[key] += code

    n_ok = n_miss = n_extra = 0
    print("")
    for o, m in picked:
        code = text_by_site.get((o, m), "")
        if not code:
            print("  SKIP  %s$$%s -- pas de decompile rendu" % (o.rsplit(".", 1)[-1], m))
            continue
        cited = set()
        for short, fulls in short2full.items():
            # Le rendu ecrit le symbole COMPLET ; on cherche la forme courte comme
            # ancre. La FRONTIERE DE FIN est obligatoire : sans elle, `AmountIsGreater`
            # matche `AmountIsGreaterThanZero` et le probe accuse la carte de rater
            # une primitive qui n'a jamais ete appelee. Mesure au premier jet : 6
            # « manques » sur 12 sites, tous des prefixes -- le test etait rouge a
            # cause du MONTAGE, pas de la carte.
            if short.split("$$")[1] and re.search(
                    re.escape(short) + r"(?![A-Za-z0-9_])", code):
                cited |= fulls
        mapped = edges.get((o, m), set())
        miss = sorted(cited - mapped)
        extra = sorted(mapped - cited)
        n_miss += len(miss)
        n_extra += len(extra)
        if not miss and not extra:
            n_ok += 1
            print("  OK    %-46s %d primitives, accord total"
                  % (o.rsplit(".", 1)[-1] + "$$" + m, len(mapped)))
        else:
            print("  DIFF  %-46s carte=%d texte=%d"
                  % (o.rsplit(".", 1)[-1] + "$$" + m, len(mapped), len(cited)))
            for s in miss[:6]:
                print("          texte seulement : %s" % s.split("$$")[-1])
            for s in extra[:6]:
                print("          carte seulement : %s" % s.split("$$")[-1])

    print("")
    print("RESULTAT  %d/%d sites en accord total ; %d citations texte non mappees ; "
          "%d aretes non retrouvees dans le texte"
          % (n_ok, len(picked), n_miss, n_extra))
    print("NB  un appel INLINE est invisible des DEUX cotes : l'accord borne le biais "
          "entre lectures, il ne prouve pas l'exhaustivite.")
    out = REPO / "logs" / "dsl_crosscheck.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"build": build, "sites": len(picked),
                               "agree": n_ok, "text_only": n_miss,
                               "map_only": n_extra}, indent=2), encoding="utf-8")
    return 0 if n_miss == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
