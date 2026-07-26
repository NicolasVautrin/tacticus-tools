#!/usr/bin/env python
"""gameconfig_diff -- comparer deux instantanes du gameconfig (17 Mo chacun).

POURQUOI PAS UN DIFF TEXTUEL : `diff` sur 17 Mo de JSON rend des dizaines de
milliers de lignes ou une accolade deplacee pese autant qu'un degat divise par
deux. Et un diff textuel ne repond PAS a la seule question qui compte (tache
#105) : est-ce un REEQUILIBRAGE (des nombres bougent sur des chemins existants)
ou un changement de MECANIQUE (des chemins apparaissent / disparaissent) ?

CE QUE FAIT CET OUTIL : il aplatit chaque config en `chemin -> valeur feuille`,
puis range les differences en TROIS familles, qui sont le critere de #105 :

    AJOUT    chemin present seulement dans B  -- MECANIQUE (capacite/champ neuf)
    RETRAIT  chemin present seulement dans A  -- MECANIQUE (capacite retiree)
    VALEUR   meme chemin, valeur differente   -- REEQUILIBRAGE si les deux
                                                 valeurs sont numeriques,
                                                 MECANIQUE sinon (bool, enum,
                                                 nom de type...)

LES LISTES DE SCALAIRES SONT COMPAREES COMME DES ENSEMBLES, pas par index :
`boardsToInclude` porte 676 entrees, et une simple permutation cote serveur
produirait 676 fausses differences par index. On rapporte les membres ajoutes /
retires. Les listes d'objets, elles, restent indexees (l'ordre y porte du sens).

Usage :
    python scripts/python/gameconfig_diff.py --list
    python scripts/python/gameconfig_diff.py <A.json> <B.json>
    python scripts/python/gameconfig_diff.py <A> <B> --section units
    python scripts/python/gameconfig_diff.py <A> <B> --limit 200
    python scripts/python/gameconfig_diff.py --live      # instantane versionne vs live

Sorties ASCII uniquement (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONED = ROOT / "data" / "gameconfig"


# --- localisation des instantanes ---------------------------------------------------------------

def live_dir() -> Path:
    base = Path.home() / "AppData" / "LocalLow" / "Snowprint"
    cands = [p for p in base.glob("*/gameconfig") if p.is_dir()]
    if not cands:
        raise RuntimeError("repertoire gameconfig live introuvable sous %s" % base)
    return cands[0]


def identify(path: Path) -> dict:
    """Identite d'un instantane SANS le parser entierement (17 Mo).

    `clientGameConfigVersion` et `fullConfigHash` sont a la RACINE du document,
    donc dans les premiers octets : on lit une tete de fichier et on extrait les
    deux champs au lieu de payer un json.loads complet juste pour un listing.
    """
    head = path.read_text(encoding="utf-8")[:4096]
    out = {"file": path.name, "bytes": path.stat().st_size, "mtime": path.stat().st_mtime}
    for key in ("clientGameConfigVersion", "fullConfigHash"):
        marker = '"%s"' % key
        i = head.find(marker)
        if i < 0:
            continue
        j = head.find(":", i + len(marker))
        k = head.find(",", j)
        if j > 0 and k > j:
            out[key] = head[j + 1:k].strip().strip('"')
    return out


# --- aplatissement -------------------------------------------------------------------------------

def _is_scalar(v) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def flatten(obj, prefix: str, out: dict, sets: dict) -> None:
    """Aplatit `obj` en {chemin: valeur feuille}. Les listes de scalaires vont
    dans `sets` (compare comme ensembles), les listes d'objets sont indexees."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, "%s.%s" % (prefix, k) if prefix else str(k), out, sets)
    elif isinstance(obj, list):
        if obj and all(_is_scalar(x) for x in obj):
            sets[prefix] = obj
        elif not obj:
            out[prefix] = "[]"
        else:
            for i, v in enumerate(obj):
                flatten(v, "%s[%d]" % (prefix, i), out, sets)
    else:
        out[prefix] = obj


def load_flat(path: Path) -> tuple[dict, dict, dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    root = doc.get("clientGameConfig") or doc
    leaves: dict = {}
    sets: dict = {}
    flatten(root, "", leaves, sets)
    meta = {"clientGameConfigVersion": doc.get("clientGameConfigVersion"),
            "fullConfigHash": doc.get("fullConfigHash")}
    return leaves, sets, meta


# --- comparaison ---------------------------------------------------------------------------------

def _numeric(v) -> bool:
    # bool est un int en Python : un True->False n'est PAS un reequilibrage.
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def section_of(path: str) -> str:
    return path.split(".", 1)[0] if path else "(racine)"


def compare(a_path: Path, b_path: Path) -> dict:
    la, sa, ma = load_flat(a_path)
    lb, sb, mb = load_flat(b_path)

    ka, kb = set(la), set(lb)
    added = sorted(kb - ka)
    removed = sorted(ka - kb)

    rebalance, mechanic = [], []
    for k in sorted(ka & kb):
        va, vb = la[k], lb[k]
        if va == vb:
            continue
        (rebalance if _numeric(va) and _numeric(vb) else mechanic).append((k, va, vb))

    # listes de scalaires : difference ENSEMBLISTE (l'ordre n'y porte pas de sens)
    set_changes = []
    for k in sorted(set(sa) | set(sb)):
        xa, xb = sa.get(k), sb.get(k)
        if xa is None or xb is None:
            (added if xa is None else removed).append(k + "[]")
            continue
        sxa, sxb = set(map(repr, xa)), set(map(repr, xb))
        if sxa != sxb:
            set_changes.append((k, sorted(sxb - sxa), sorted(sxa - sxb)))

    return {"meta_a": ma, "meta_b": mb, "added": added, "removed": removed,
            "rebalance": rebalance, "mechanic": mechanic, "sets": set_changes,
            "n_leaves_a": len(la), "n_leaves_b": len(lb)}


# --- rapport -------------------------------------------------------------------------------------

def _fmt(v) -> str:
    s = repr(v)
    return s if len(s) <= 60 else s[:57] + "..."


def report(d: dict, section: str | None, limit: int) -> None:
    def keep(path: str) -> bool:
        return section is None or section_of(path) == section

    added = [p for p in d["added"] if keep(p)]
    removed = [p for p in d["removed"] if keep(p)]
    reb = [t for t in d["rebalance"] if keep(t[0])]
    mec = [t for t in d["mechanic"] if keep(t[0])]
    sets = [t for t in d["sets"] if keep(t[0])]

    print("A: ver=%s hash=%s  (%d feuilles)" % (
        d["meta_a"].get("clientGameConfigVersion"),
        str(d["meta_a"].get("fullConfigHash"))[:16], d["n_leaves_a"]))
    print("B: ver=%s hash=%s  (%d feuilles)" % (
        d["meta_b"].get("clientGameConfigVersion"),
        str(d["meta_b"].get("fullConfigHash"))[:16], d["n_leaves_b"]))
    if section:
        print("section: %s" % section)
    print("")
    print("MECANIQUE  ajouts=%d  retraits=%d  valeurs non-numeriques=%d  listes=%d"
          % (len(added), len(removed), len(mec), len(sets)))
    print("REEQUILIBRAGE  valeurs numeriques=%d" % len(reb))
    print("")

    # ventilation par section : ou la mise a jour a-t-elle porte ?
    per: dict = {}
    for p in added:
        per.setdefault(section_of(p), [0, 0, 0, 0])[0] += 1
    for p in removed:
        per.setdefault(section_of(p), [0, 0, 0, 0])[1] += 1
    for t in mec:
        per.setdefault(section_of(t[0]), [0, 0, 0, 0])[2] += 1
    for t in reb:
        per.setdefault(section_of(t[0]), [0, 0, 0, 0])[3] += 1
    if per:
        print("%-24s %8s %8s %8s %8s" % ("section", "ajout", "retrait", "type", "nombre"))
        for k in sorted(per, key=lambda x: -sum(per[x])):
            a, r, m, n = per[k]
            print("%-24s %8d %8d %8d %8d" % (k, a, r, m, n))
        print("")

    def dump(title: str, rows: list, fmt) -> None:
        if not rows:
            return
        print("--- %s (%d) ---" % (title, len(rows)))
        for row in rows[:limit]:
            print("  " + fmt(row))
        if len(rows) > limit:
            print("  ... %d de plus (--limit)" % (len(rows) - limit))
        print("")

    dump("AJOUTS", added, lambda p: p)
    dump("RETRAITS", removed, lambda p: p)
    dump("MECANIQUE (valeur non numerique)", mec,
         lambda t: "%s : %s -> %s" % (t[0], _fmt(t[1]), _fmt(t[2])))
    dump("REEQUILIBRAGE (valeur numerique)", reb,
         lambda t: "%s : %s -> %s" % (t[0], _fmt(t[1]), _fmt(t[2])))
    dump("LISTES (difference ensembliste)", sets,
         lambda t: "%s : +%s -%s" % (t[0], _fmt(t[1]), _fmt(t[2])))


def cmd_list() -> None:
    rows = []
    if VERSIONED.is_dir():
        rows += [("versionne", p) for p in sorted(VERSIONED.glob("*.json"))]
    try:
        rows += [("live", p) for p in sorted(live_dir().glob("*.json"))]
    except RuntimeError as e:
        print("(live indisponible : %s)" % e)
    if not rows:
        print("aucun instantane trouve")
        return
    print("%-10s %-36s %12s %-18s %s" % ("origine", "fichier", "octets", "mtime", "fullConfigHash"))
    import datetime
    for origin, p in rows:
        info = identify(p)
        mt = datetime.datetime.fromtimestamp(info["mtime"]).strftime("%Y-%m-%d %H:%M")
        print("%-10s %-36s %12d %-18s %s" % (
            origin, info["file"], info["bytes"], mt,
            str(info.get("fullConfigHash"))[:32]))


def main() -> int:
    ap = argparse.ArgumentParser(description="diff par chemin de feuille de deux gameconfig")
    ap.add_argument("a", nargs="?", help="instantane A (ancien)")
    ap.add_argument("b", nargs="?", help="instantane B (nouveau)")
    ap.add_argument("--list", action="store_true", help="lister les instantanes connus")
    ap.add_argument("--section", default=None,
                    help="ne rapporter qu'une section de tete (units, globalValues, ...)")
    ap.add_argument("--limit", type=int, default=40, help="lignes par famille (defaut 40)")
    a = ap.parse_args()

    if a.list or not (a.a and a.b):
        cmd_list()
        return 0

    pa, pb = Path(a.a), Path(a.b)
    for p in (pa, pb):
        if not p.is_file():
            print("introuvable : %s" % p)
            return 2
    report(compare(pa, pb), a.section, a.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
