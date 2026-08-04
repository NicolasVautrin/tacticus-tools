"""Le chemin INCREMENTAL du board rend-il les memes agregats que la lecture entiere ?

⛔ CE PROBE NE RELIT JAMAIS LE CORPUS. Une reconstruction complete coute 2 616 Mo et 1 300 s
(mesure du 2026-08-04) ; la payer pour VERIFIER serait exactement la faute qu'on cherche a
supprimer. On verifie donc le MECANISME sur quelques PETITS fichiers, pas le resultat sur les
906 transcripts : si `_read_tail` + accumulation redonnent la lecture entiere sur un fichier,
ils la redonnent sur tous -- la propriete est locale au fichier.

Ce qui est mis a l'epreuve, et qui EST le risque reel :
  1. la COUPURE. `_read_tail` s'arrete au dernier saut de ligne. Une reprise au milieu d'une
     ligne perdrait ou dupliquerait un enregistrement. On coupe donc a des offsets ARBITRAIRES,
     y compris en plein JSON, et on exige le meme total qu'une lecture d'un bloc.
  2. l'ACCUMULATION. Lire en N morceaux doit donner la somme d'une lecture unique.
  3. l'IDEMPOTENCE. Relire a offset == taille ne doit RIEN ajouter (c'est le cas nominal :
     un fichier d'agent termine est revu a chaque run et ne doit plus jamais compter).

Usage : python probe_board_incremental.py [--files N]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_board as rb  # noqa: E402


def agg(lines: list) -> dict:
    """Agregat par jour d'un lot de lignes -- meme extraction que `load_tokens`."""
    out = defaultdict(lambda: [0, 0])
    for ln in lines:
        if '"usage"' not in ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        u = (rec.get("message") or {}).get("usage") or {}
        t = rb._ts(rec.get("timestamp"))
        if not u or not t:
            continue
        day = t.astimezone().strftime("%Y-%m-%d")
        out[day][0] += rb._ctx(u)
        out[day][1] += 1
    return {d: tuple(v) for d, v in out.items()}


def add(a: dict, b: dict) -> dict:
    out = dict(a)
    for d, (c, n) in b.items():
        pc, pn = out.get(d, (0, 0))
        out[d] = (pc + c, pn + n)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--files", type=int, default=6, help="nombre de petits transcripts a tester")
    args = ap.parse_args()

    pdir = rb.project_dir()
    cand = sorted(pdir.glob("*/subagents/agent-*.jsonl"), key=lambda p: p.stat().st_size)
    cand = [p for p in cand if p.stat().st_size > 20000][:args.files]
    if not cand:
        print("PAS DE TRANSCRIPT exploitable -- probe NON CONCLUANT (ce n'est pas un succes)")
        return 2

    print("%-26s %9s  %s" % ("fichier", "taille", "verdict"))
    bad = 0
    total_mo = 0.0
    for fp in cand:
        size = fp.stat().st_size
        total_mo += size / 1048576.0
        whole, off = rb._read_tail(fp, 0)
        ref = agg(whole)

        # (1)+(2) coupures ARBITRAIRES, y compris en plein milieu d'une ligne JSON.
        # On rejoue la logique de `_read_tail` bornee a la coupure : lire jusqu'au dernier
        # saut de ligne du morceau, et avancer l'offset D'AUTANT -- pas jusqu'a la coupure.
        cuts = [size // 7, size // 3, (size * 2) // 3, size]
        acc, cur = {}, 0
        for c in cuts:
            with fp.open("rb") as fh:
                fh.seek(cur)
                buf = fh.read(max(0, c - cur))
            cut = buf.rfind(b"\n")
            if cut < 0:
                continue
            usable = buf[:cut + 1]
            acc = add(acc, agg(usable.decode("utf-8", "replace").splitlines()))
            cur += len(usable)
        # la queue restante
        tail, cur = rb._read_tail(fp, cur)
        acc = add(acc, agg(tail))

        # (3) idempotence : a offset == taille, plus rien
        again, off2 = rb._read_tail(fp, size)
        idem = (again == [] and off2 == size)

        ok = (acc == ref) and idem
        bad += 0 if ok else 1
        print("%-26s %8.1fk  %s" % (fp.name[:26], size / 1024.0,
                                    "OK" if ok else "ECHEC"))
        if not ok:
            for d in sorted(set(ref) | set(acc)):
                if ref.get(d) != acc.get(d):
                    print("     %s  entier=%s  morceaux=%s" % (d, ref.get(d), acc.get(d)))
            if not idem:
                print("     NON IDEMPOTENT a offset==taille")

    print()
    print("%d fichier(s), %.1f Mo lus -- JAMAIS le corpus (2616 Mo)" % (len(cand), total_mo))
    print("resultat : %s" % ("OK -- accumulation == lecture entiere" if not bad
                             else "%d ECHEC(S)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
