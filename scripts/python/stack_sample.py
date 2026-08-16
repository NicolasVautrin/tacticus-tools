"""Nommer une boucle native : echantillonne les piles du jeu et RESOUT les adresses.

    python scripts/python/stack_sample.py --session 20
    python scripts/python/stack_sample.py --session 20 --echantillons 10 --tous

A QUOI CA SERT
--------------
Un jeu qui ne repond plus se separe en deux par le CPU : delta NUL = thread BLOQUE, delta
PLEIN = thread qui TOURNE EN ROND. Le second cas ne se diagnostique pas a l'oeil -- il faut
savoir OU il tourne. Ce script echantillonne les piles et nomme les adresses recurrentes.

LE PARTAGE DU TRAVAIL, ET POURQUOI IL EST LA
---------------------------------------------
Le hook rend des ADRESSES BRUTES ; c'est ICI qu'on les nomme, contre
`data/symbols/<build>/ghidra/functions.tsv`. `DebugSymbol.fromAddress` cote Frida ne connait
pas les methodes IL2CPP : il rendrait `GameAssembly.dll+0x53cf70`, ce qui n'apprend rien.

(!) LE HASH DU BUILD EST VERIFIE. Une adresse resolue contre le mauvais dump donne un nom
COHERENT et FAUX -- c'est le mode de panne le plus couteux du depot. On compare donc le build
installe a `data/symbols/CURRENT` et on REFUSE si ca diverge.

(!) LE RPC N'EST PAS QUEUED, et c'est voulu : il mesure un thread principal qui ne rend pas la
main. Un RPC queued n'arriverait jamais.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import bisect
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
VA_BASE = 0x180000000


def charger_table(build):
    """(adresses triees, symboles) depuis functions.tsv. Rend (None, None) si absente."""
    p = RACINE / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    if not p.exists():
        return None, None, p
    adrs, noms = [], []
    for ligne in p.read_text(encoding="utf-8", errors="replace").split("\n"):
        c = ligne.split("\t")
        if len(c) < 2:
            continue
        try:
            adrs.append(int(c[0], 16))
        except ValueError:
            continue
        noms.append(c[1].strip())
    couples = sorted(zip(adrs, noms))
    return [a for a, _ in couples], [n for _, n in couples], p


def resoudre(va, adrs, noms):
    """Le symbole qui CONTIENT `va`, avec son decalage. `None` si hors table."""
    if not adrs:
        return None
    i = bisect.bisect_right(adrs, va) - 1
    if i < 0:
        return None
    return "%s+0x%x" % (noms[i], va - adrs[i]) if va != adrs[i] else noms[i]


def build_courant():
    """Le build INSTALLE, lu sur disque -- jamais recopie.

    (!) Un repertoire de build est celui qui PORTE L'EXE. Le dossier contient aussi un `.temp`
    (mesure le 2026-08-16), et prendre << le premier sous-dossier >> le designait, ce qui
    declenchait un faux refus de divergence de build. Le critere est l'exe, pas le rang."""
    d = Path.home() / "AppData" / "Local" / "tacticus" / "games"
    if not d.exists():
        return None
    builds = [x.name for x in d.iterdir()
              if x.is_dir() and not x.name.startswith(".") and (x / "Tacticus.exe").exists()]
    if len(builds) == 1:
        return builds[0]
    # zero ou plusieurs : on ne DEVINE pas, on rend None et l'appelant le dit
    return None


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--echantillons", type=int, default=6)
    ap.add_argument("--profondeur", type=int, default=24)
    # (!) DEFAUT = TOUS LES THREADS. Filtrer sur l'etat `running` PERD le signal : mesure du
    # 2026-08-16, avec le filtre 0 trame GameAssembly sur 4 echantillons, sans lui 182 sur 2.
    # L'etat rapporte par l'OS a l'instant de l'echantillon ne dit pas qui fait le travail.
    ap.add_argument("--actifs-seuls", action="store_true",
                    help="ne garder que les threads en etat `running` (PERD du signal)")
    ap.add_argument("--build", default=None, help="force le build (sinon : data/symbols/CURRENT)")
    a = ap.parse_args(argv)

    # --- le build : on REFUSE de resoudre contre le mauvais dump ---
    fichier_courant = RACINE / "data" / "symbols" / "CURRENT"
    build_table = a.build or (fichier_courant.read_text(encoding="utf-8").strip()
                              if fichier_courant.exists() else None)
    installe = build_courant()
    print("build installe = %s ; table = %s" % (installe, build_table))
    if build_table is None:
        print("REFUS : aucun build de table (data/symbols/CURRENT absent). "
              "Rien n'est resolu -- une adresse nue ne vaut rien.")
        return 2
    if installe and installe != build_table and not a.build:
        print("REFUS : le build INSTALLE (%s) et celui de la TABLE (%s) divergent."
              % (installe, build_table))
        print("  Resoudre contre le mauvais dump donne des noms COHERENTS et FAUX.")
        print("  Re-dumper, ou forcer avec --build en sachant ce qu'on fait.")
        return 2

    adrs, noms, chemin = charger_table(build_table)
    if adrs is None:
        print("REFUS : table absente -- %s" % chemin)
        return 2
    print("table : %d symboles (%s)" % (len(adrs), chemin.name))
    print()

    corps = json.dumps({"method": "stackSample",
                        "args": [{"echantillons": a.echantillons,
                                  "profondeur": a.profondeur,
                                  "seulementActifs": a.actifs_seuls}],
                        "timeout": 60000}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%d/rpc" % (a.hote, a.session),
                                 data=corps, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode("utf-8")).get("result")
    except urllib.error.HTTPError as e:
        print("NON MESURE : HTTP %s -- %s" % (e.code, e.read().decode("utf-8", "replace")[:250]))
        return 2
    except Exception as e:
        print("NON MESURE : %s: %s" % (type(e).__name__, e))
        return 2

    if not (isinstance(d, dict) and d.get("ok")):
        print("NON MESURE : %s" % json.dumps(d, ensure_ascii=False)[:400])
        return 2

    base = int(d["base"], 16) if d.get("base") else None
    if base is None:
        print("REFUS : base de GameAssembly.dll NON MESUREE -- aucune adresse n'est resoluble.")
        return 2
    print("GameAssembly.dll base=0x%x taille=%s ; %d thread(s) vus sur %d echantillon(s)"
          % (base, d.get("taille"), d.get("threadsVus"), d.get("echantillons")))
    print()

    def nommer(adr_hex):
        adr = int(adr_hex, 16)
        if d.get("taille") and not (base <= adr < base + d["taille"]):
            return None          # hors GameAssembly : pas notre table
        return resoudre(VA_BASE + (adr - base), adrs, noms)

    # On RECALCULE la recurrence ici, en ne gardant que ce qui touche le MOTEUR : sur 140+
    # threads, la quasi-totalite dort dans ntdll/UnityPlayer et noie le signal.
    from collections import Counter
    par_thread = {}
    for lot in (d.get("lots") or []):
        for e in lot:
            p = par_thread.setdefault(e["thread"], {"vu": 0, "etats": set(),
                                                    "ga": Counter(), "trames": 0})
            p["vu"] += 1
            p["etats"].add(e.get("etat"))
            for f in (e.get("trames") or []):
                p["trames"] += 1
                if nommer(f["adresse"]):
                    p["ga"][f["adresse"]] += 1

    moteur = [(tid, p) for tid, p in par_thread.items() if p["ga"]]
    moteur.sort(key=lambda kv: -sum(kv[1]["ga"].values()))
    print("=== les threads qui touchent GameAssembly (%d sur %d) ==="
          % (len(moteur), len(par_thread)))
    if not moteur:
        print("  AUCUN -- soit le jeu est au repos, soit l'unwind n'atteint pas le moteur.")
        print("  Ce n'est PAS une preuve que rien ne tourne.")
        return 0
    print("  (une boucle se reconnait a une adresse presente dans TOUS les echantillons)")
    for tid, p in moteur[:6]:
        total = sum(p["ga"].values())
        print()
        print("  thread %-8s vu %d fois, etats=%s -- %d trame(s) GameAssembly"
              % (tid, p["vu"], ",".join(sorted(x for x in p["etats"] if x)), total))
        for adr, fois in p["ga"].most_common(14):
            marque = "  <<< dans TOUS les echantillons" if fois >= p["vu"] else ""
            print("      x%-3d %s%s" % (fois, nommer(adr), marque))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
