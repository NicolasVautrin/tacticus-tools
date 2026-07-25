#!/usr/bin/env python3
"""Migration des citations natives : adresse VA -> SYMBOLE Ghidra verbatim.

POURQUOI. Churn inter-build MESURE (build de mai -> gqfc5mff6c) : les NOMS sont stables a
97,5 %, les ADRESSES changent a 100 %. Une citation par ADRESSE est donc fausse des la
mise a jour suivante, silencieusement — alors que le symbole, lui, survit et se re-resout
d'un grep dans `data/symbols/<build>/ghidra/functions.tsv`.

FORME CIBLE = EXACTEMENT la sortie de l'outil d'extraction (`ghidra_symbols.py dump`), pour
que le grep code <-> table soit immediat :
    IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage
Un point INTERNE se cite `<symbole>+0x<offset>` : l'offset est RELATIF, il ne perime pas.
Les offsets relatifs deja presents dans le code (champs de struct `+0xa8`, slots de vtable)
ne sont PAS concernes — seules les VA absolues le sont.

TROIS CAS DE REECRITURE (le 3e est le repli, toujours sur) :
  1. `Nom @VA` / `Type.Nom(args) @VA`  -> `<symbole>` (ou `<symbole>(args)`)
     Le symbole SE TERMINE par le nom court : rien n'est perdu, le type possesseur est gagne.
  2. `Nom(@VA)`                        -> `<symbole>`
  3. tout le reste                     -> substitution SUR PLACE de la seule VA.

GARDE-FOU CAPITAL : sur un fichier Python on TOKENISE, et on ne reecrit QUE dans les
COMMENT / STRING / FSTRING. Un litteral `NUMBER` n'est JAMAIS touche -- il est EXECUTABLE.
Mesure du 2026-07-25 : 17 VA vivent dans du code reel -- la constante d'image base, les cles
de dict `<adresse>: "Nom"` de probe_38b_vtable.py et probe_79_revive_vtable.py, et une
comparaison `if g == <adresse>:`. Une migration purement textuelle les aurait transformees en
SyntaxError. Les `.md` sont integralement de la prose. Les `.ts` sont HORS PERIMETRE : les
hooks portent de vraies RVA en dur dans du code (chantier distinct).

NB : ce fichier et les probes VA documentent des adresses A TITRE D'EXEMPLE. Elles sont
volontairement ecrites SANS le prefixe `0x`/`@` reconnu par VA_RE, pour que l'outil ne
reecrive pas sa propre documentation.

NON MIGRE, et c'est VOULU : les VA qui resolvent sur un placeholder `FUN_<addr>` (le
"symbole" n'y est que l'adresse deguisee, migrer n'apporterait RIEN) et celles situees avant
le premier symbole. Elles sont LISTEES dans le rapport pour rester visibles.

Sortie ASCII pure (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import bisect
import io
import re
import sys
import token as T
import tokenize
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SYMBOLS_DIR = REPO / "data" / "symbols"

VA_RE = re.compile(r"(?<![0-9a-fA-Fx])(?:0x|@)(18[0-9a-fA-F]{7})(?![0-9a-fA-F])")
# Identifiant .NET tel qu'il apparait dans nos citations : `Type.Sous.Methode`,
# `IterateAdjacentTiles.<>d__8.MoveNext`, `d__6.MoveNext`, ...
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.(?:<>)?[A-Za-z_][A-Za-z0-9_]*)*$")


class Table:
    """Table de symboles du build : adresse -> symbole englobant."""

    def __init__(self, build: str):
        path = SYMBOLS_DIR / build / "ghidra" / "functions.tsv"
        if not path.exists():
            raise SystemExit("table absente : %s\n  -> lancer `ghidra_symbols.py dump`" % path)
        pairs = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                addr, _, name = line.rstrip("\n").partition("\t")
                if name:
                    pairs.append((int(addr, 16), name))
        pairs.sort()
        self.build = build
        self.addrs = [a for a, _ in pairs]
        self.names = [n for _, n in pairs]

    def resolve(self, va: int):
        """-> (symbole, offset) ou (None, None) si la VA precede le 1er symbole."""
        i = bisect.bisect_right(self.addrs, va) - 1
        if i < 0:
            return None, None
        return self.names[i], va - self.addrs[i]

    def citation(self, va: int):
        """-> texte de citation, ou None si la VA n'est pas migrable."""
        sym, off = self.resolve(va)
        if sym is None or sym.startswith("FUN_"):
            return None
        return sym if off == 0 else "%s+0x%x" % (sym, off)


def tail(sym: str) -> str:
    """`Namespace.Type$$Methode` -> `methode` (minuscules, pour comparaison)."""
    seg = sym.split("+0x")[0]
    seg = seg.split("$$")[-1] if "$$" in seg else seg
    return seg.split(".")[-1].lower()


def _match_open_paren(text: str, close: int) -> int:
    """Index du '(' appariant le ')' en `close`, ou -1."""
    depth = 0
    for i in range(close, -1, -1):
        if text[i] == ")":
            depth += 1
        elif text[i] == "(":
            depth -= 1
            if depth == 0:
                return i
    return -1


def prose_spans(path: Path, text: str):
    """Intervalles [debut, fin) OU une reecriture est SANS RISQUE.

    Python -> uniquement COMMENT / STRING / FSTRING (jamais un NUMBER, qui est EXECUTABLE).
    Autre  -> tout le fichier (prose integrale).
    Retourne None si le fichier est integralement autorise.
    """
    if path.suffix != ".py":
        return None
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))

    def off(rc):
        row, col = rc
        return starts[row - 1] + col if row - 1 < len(starts) else len(text)

    ok = []
    prose = {T.COMMENT, T.STRING}
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        if hasattr(T, name):
            prose.add(getattr(T, name))
    try:
        for tk in tokenize.generate_tokens(io.StringIO(text).readline):
            if tk.type in prose:
                ok.append((off(tk.start), off(tk.end)))
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        raise SystemExit("REFUS : %s ne tokenise pas (%s) -- aucun fichier ecrit." % (path, exc))
    return ok


def plan_file(text: str, table: Table, allowed):
    """-> (nouveau texte, compteur de cas, VA non migrees, echantillons)."""
    out = []
    cases = Counter()
    skipped = []
    shown = []
    pos = 0

    def in_prose(a: int, b: int) -> bool:
        if allowed is None:
            return True
        return any(s <= a and b <= e for s, e in allowed)

    for m in VA_RE.finditer(text):
        if not in_prose(m.start(), m.end()):
            cases["CODE EXECUTABLE (intouche)"] += 1
            continue
        cit = table.citation(int(m.group(1), 16))
        if cit is None:
            skipped.append(m.group(1))
            cases["non-migrable (FUN_ / hors table)"] += 1
            continue

        start, end = m.start(), m.end()
        base = tail(cit)

        # --- cas 2 : `Nom(@VA)` -- la VA est le SEUL contenu des parentheses.
        if start > 0 and text[start - 1] == "(" and end < len(text) and text[end] == ")":
            head = text[: start - 1]
            im = IDENT_RE.search(head)
            if im and im.group(0).split(".")[-1].lower() == base:
                out.append(text[pos:im.start()])
                out.append(cit)
                shown.append((text[im.start():end + 1], cit))
                pos = end + 1
                cases["2. Nom(@VA) -> symbole"] += 1
                continue

        # --- cas 1 : `Nom @VA` ou `Type.Nom(args) @VA` (separateur = blancs, saut de ligne
        #     et backticks/ponctuation de wrap inclus).
        head = text[:start].rstrip(" \t\r\n`")
        args = ""
        if head.endswith(")"):
            op = _match_open_paren(head, len(head) - 1)
            if op > 0:
                args = head[op:]
                head = head[:op]
        im = IDENT_RE.search(head)
        if im and im.group(0).split(".")[-1].lower() == base:
            out.append(text[pos:im.start()])
            out.append(cit + args)
            shown.append((text[im.start():end], cit + args))
            wrapped = "\n" in text[im.start():end]
            cases["1. Nom @VA -> symbole" + (" (citation wrappee)" if wrapped else "")] += 1
            pos = end
            continue

        # --- cas 3 : repli sur place.
        out.append(text[pos:start])
        out.append(cit)
        shown.append((m.group(0), cit))
        pos = end
        cases["3. substitution sur place"] += 1

    out.append(text[pos:])
    return "".join(out), cases, skipped, shown


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--build", default="gqfc5mff6c")
    ap.add_argument("--ext", default=".py,.md,.ts")
    ap.add_argument("--exclude", default=".claude/worktrees,docs/rl/solving-playbook.md",
                    help="fragments de chemin a ignorer (virgules)")
    ap.add_argument("--apply", action="store_true", help="ecrit (defaut : simulation)")
    ap.add_argument("--sample", type=int, default=0, help="affiche N reecritures d'exemple")
    args = ap.parse_args()

    table = Table(args.build)
    exts = tuple(args.ext.split(","))
    excl = [e.replace("/", "\\") for e in args.exclude.split(",") if e]

    files = []
    for root in args.roots:
        p = REPO / root
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += [f for f in p.rglob("*") if f.is_file() and f.suffix in exts]
    files = [f for f in files if not any(e in str(f) for e in excl)]

    total = Counter()
    all_skipped = []
    touched = 0
    samples = []
    for f in sorted(files):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not VA_RE.search(text):
            continue
        new, cases, skipped, shown = plan_file(text, table, prose_spans(f, text))
        total.update(cases)
        all_skipped += [(str(f.relative_to(REPO)), s) for s in skipped]
        if new == text:
            continue
        touched += 1
        for old, rep in shown:
            if len(samples) < args.sample:
                samples.append((str(f.relative_to(REPO)), old, rep))
        if args.apply:
            f.write_text(new, encoding="utf-8", newline="\n")

    print("build       : %s (%d symboles)" % (table.build, len(table.addrs)))
    print("mode        : %s" % ("APPLIQUE" if args.apply else "SIMULATION (--apply pour ecrire)"))
    print("fichiers    : %d scannes, %d modifies" % (len(files), touched))
    print("")
    for case, n in sorted(total.items()):
        print("  %-34s %d" % (case, n))
    print("  %-34s %d" % ("TOTAL", sum(total.values())))

    if all_skipped:
        print("")
        print("--- NON MIGRE (reste en VA, par conception) ---")
        by_va = Counter(va for _, va in all_skipped)
        for va, n in by_va.most_common():
            where = sorted({p for p, v in all_skipped if v == va})
            print("  @%s  x%-3d %s" % (va, n, ", ".join(where[:3])
                                       + (" ..." if len(where) > 3 else "")))

    if samples:
        print("")
        print("--- ECHANTILLON DE REECRITURES ---")
        for path, a, b in samples:
            print("  %s" % path)
            print("    - %s" % a.replace("\n", " <NL> ")[:160])
            print("    + %s" % b.replace("\n", " <NL> ")[:160])
    return 0


if __name__ == "__main__":
    sys.exit(main())
