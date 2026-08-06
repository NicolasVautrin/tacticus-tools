#!/usr/bin/env python
"""#419-r6 -- le PERIMETRE de la bascule du defaut a « equiper », DERIVE et non herite.

POURQUOI CE PROBE EXISTE
------------------------
#419-r5 a mesure 8 fichiers, tous des fichiers de DEGAT. Mais la bascule change l'etat de TOUT
runner construit, donc de tout test live qui en monte un : prendre 8 pour le perimetre serait
exactement le vice qu'un recenseur commet quand il ne visite qu'une famille (cf. CLAUDE.md,
« un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas »).

CE QU'IL VISITE, ET CE QU'IL NE VISITE PAS
-------------------------------------------
Il visite les FICHIERS DE TEST de `scripts/python/tests/`, et n'en classe comme LIVE que ceux
qui touchent le harnais (`build_runner`, `live_session`, `rpc`, ou un `rl_duel build`). Il ne
visite PAS :
  * les PROBES (`scripts/python/probe_*.py`) -- ils mesurent, ils ne gardent rien ;
  * ce qu'un test live atteint INDIRECTEMENT via une fixture d'un autre paquet ;
  * la face DECISION hors tests (`engine_validate.py`, `predict_sweep.py`), qui monte pourtant
    des runners.
Chacune de ces trois portees est IMPRIMEE, pas tue -- un perimetre qui ne dit pas ses bords se
lit comme complet.

LES TROIS CANAUX D'EXPOSITION, ET POURQUOI ILS SONT DISTINCTS
--------------------------------------------------------------
La bascule ne fait pas qu'ouvrir le crit. Mesure #419-r5 etape 3 : equiper fait aussi entrer
l'unite dans ses AUTRES slots -- 49 unites sur 106 changent de `FixedArmor`, 4 de `Health`.

  (A) COUP PROPRE EXIGE  -- le fichier filtre/skippe sur `did_crit`/`DidCrit`/`mightCrit`. Il
      trouvait son coup propre SANS RIEN DEMANDER quand le canal etait muet. Risque : le
      fichier devient INERTE (`passed == 0 and skipped > 0`, garde #455).
  (B) NEUTRALISATION DEJA EXPLICITE -- le fichier pose deja `--crit`/`--block-*` au build. Il
      est IMMUNISE par construction, et c'est le remede-type.
  (C) VALEUR EN DUR      -- le fichier compare a un scalaire ecrit dans le source (PV, armure,
      degat). Un changement de `FixedArmor`/`Health` le fait rougir, et ce canal-la n'a RIEN a
      voir avec le crit : c'est celui qu'un balayage « cherche le mot crit » raterait.

Aucune assertion : c'est un probe, il MESURE.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TESTS = _HERE / "tests"

# Un fichier est LIVE s'il touche le harnais. Les trois premieres sont les fixtures de
# `conftest.py` ; la ddessous, un test qui fait son propre `rl_duel build`.
_MARQUEURS_LIVE = ("build_runner", "live_session", '"rl_duel.py", "build"',
                   "'rl_duel.py', 'build'")
# (A) le fichier EXIGE un coup propre -- il skippe/filtre des que le live crite ou bloque.
_MARQUEURS_PROPRE = ("did_crit", "DidCrit", "mightCrit", "did_block", "DidBlock",
                     "didEvade", "DidEvade", "coup non propre", "sample_is_clean")
# (B) le fichier a DEJA neutralise au build.
_MARQUEURS_NEUTRALISE = ("--crit", "--block-target", "--block-player", "--crit-target",
                         "NO_NOISE")


def _classe(src: str) -> dict:
    return {
        "live": any(m in src for m in _MARQUEURS_LIVE),
        "propre": any(m in src for m in _MARQUEURS_PROPRE),
        "neutralise": any(m in src for m in _MARQUEURS_NEUTRALISE),
    }


def _valeurs_en_dur(path: Path, src: str) -> list[tuple[int, str]]:
    """(C) -- comparaisons d'egalite a un ENTIER > 100 dans un `assert`.

    Le seuil ecarte les indices, les compteurs et les petits ordinaux ; il est IMPRIME comme
    filtre, jamais tu. Un `assert x == 8536` est le profil recherche : un PV, une armure ou un
    degat fige dans le source, que le changement de `FixedArmor`/`Health` fait rougir sans que
    le mot « crit » apparaisse nulle part.
    """
    out = []
    try:
        arbre = ast.parse(src)
    except SyntaxError:
        return out
    lignes = src.splitlines()
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Assert):
            continue
        for c in ast.walk(n.test):
            if not isinstance(c, ast.Compare):
                continue
            for op, comp in zip(c.ops, c.comparators):
                if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) \
                        and isinstance(comp.value, int) and not isinstance(comp.value, bool) \
                        and abs(comp.value) > _SEUIL_ENTIER:
                    ligne = lignes[c.lineno - 1].strip() if c.lineno <= len(lignes) else ""
                    out.append((c.lineno, ligne[:110]))
    return out


_SEUIL_ENTIER = 100


_BILAN = re.compile(r"(\d+) (passed|failed|skipped|error)")


def _jouer_un(rel: str, regime: str | None) -> dict:
    """Joue UN fichier et rend son bilan. `regime` = valeur de `TACTICUS_BIS_ITEMS` (None = defaut).

    Un fichier dont le bilan est `passed == 0 and skipped > 0` est INERTE (garde #455) : il rend
    `rc = 0` et ressemble a du vert alors qu'aucune assertion n'a ete evaluee. C'est l'etat que
    cette mesure cherche, donc on le NOMME au lieu de le lire dans un `rc`.
    """
    import os
    import subprocess

    env = dict(os.environ)
    if regime is None:
        env.pop("TACTICUS_BIS_ITEMS", None)
    else:
        env["TACTICUS_BIS_ITEMS"] = regime
    p = subprocess.run([sys.executable, "-m", "pytest", "tests/" + rel,
                        "-q", "--tb=no", "-p", "no:randomly"],
                       cwd=str(_HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    compte = {k: 0 for k in ("passed", "failed", "skipped", "error")}
    for n, k in _BILAN.findall(p.stdout or ""):
        compte[k] = int(n)
    compte["rc"] = p.returncode
    compte["inerte"] = bool(compte["passed"] == 0 and compte["skipped"] > 0)
    compte["fichier"] = rel
    compte["regime"] = "defaut" if regime is None else regime
    return compte


def _jouer(rels: list[str], regime: str | None, workers: int) -> list[dict]:
    """4 au plus : le pump est PARTAGE avec les autres agents (cf. CLAUDE.md)."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as ex:
        return list(ex.map(lambda r: _jouer_un(r, regime), rels))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lister", choices=["propre", "neutralise", "dur", "live", "indifferent",
                                         "indifferent_non_joue"],
                    help="imprime la liste des fichiers d'une categorie")
    ap.add_argument("--jouer", choices=["propre", "neutralise", "dur", "indifferent",
                                        "indifferent_non_joue"],
                    help="JOUE la categorie et rend son bilan par fichier")
    ap.add_argument("--fichiers", default=None,
                    help="JOUE une liste EXPLICITE (chemins relatifs a tests/, separes par des "
                         "virgules) -- sert au TEMOIN : rejouer les seuls degrades dans l'autre "
                         "regime est ce qui etablit la CAUSALITE, un rouge pouvant preexister")
    ap.add_argument("--regime", choices=["0", "1", "defaut"], default="defaut",
                    help="TACTICUS_BIS_ITEMS impose ; `defaut` = ce que le code porte")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--depuis", type=int, default=0, help="borner : index de depart")
    ap.add_argument("--jusqu-a", type=int, default=0, help="borner : index de fin (0 = tout)")
    a = ap.parse_args(argv)

    if not _TESTS.exists():
        print("[419-r6] ARBRE DE TESTS INTROUVABLE : %s -- aucune mesure" % _TESTS)
        return 2

    fichiers = sorted(_TESTS.rglob("test_*.py"))
    cats: Counter = Counter()
    par_cat: dict[str, list] = {"live": [], "propre": [], "neutralise": [], "dur": [],
                                "indifferent": [], "indifferent_non_joue": []}
    durs: dict[str, list] = {}

    for p in fichiers:
        src = p.read_text(encoding="utf-8", errors="replace")
        c = _classe(src)
        rel = str(p.relative_to(_TESTS)).replace("\\", "/")
        cats["fichiers"] += 1
        if not c["live"]:
            cats["offline"] += 1
            continue
        cats["live"] += 1
        par_cat["live"].append(rel)
        if c["neutralise"]:
            cats["neutralise"] += 1
            par_cat["neutralise"].append(rel)
        elif c["propre"]:
            cats["expose_propre"] += 1
            par_cat["propre"].append(rel)
        else:
            cats["live_indifferent"] += 1
            par_cat["indifferent"].append(rel)
        d = _valeurs_en_dur(p, src)
        if d:
            cats["expose_valeur_dure"] += 1
            par_cat["dur"].append(rel)
            durs[rel] = d

    # `indifferent` et `dur` ne sont PAS disjoints : le canal (C) est evalue sur TOUS les live.
    # #419-r6 a joue (A) et (C) integralement dans les deux regimes ; le reste a jouer est donc
    # exactement `indifferent \ dur`. Le nommer evite de re-payer ce qui l'a deja ete.
    _durs = set(par_cat["dur"])
    par_cat["indifferent_non_joue"] = [r for r in par_cat["indifferent"] if r not in _durs]
    cats["indifferent_non_joue"] = len(par_cat["indifferent_non_joue"])
    cats["indifferent_deja_joue_par_C"] = (cats["live_indifferent"]
                                           - cats["indifferent_non_joue"])

    print("=== PERIMETRE DERIVE de la bascule #419-r6 ===")
    print("  fichiers de test visites            : %d" % cats["fichiers"])
    print("    dont OFFLINE (hors perimetre)     : %d" % cats["offline"])
    print("    dont LIVE (montent un runner)     : %d" % cats["live"])
    print("  --- ventilation des LIVE, par canal d'exposition ---")
    print("   (B) deja NEUTRALISES au build      : %d" % cats["neutralise"])
    print("   (A) EXIGENT un coup propre, nus    : %d" % cats["expose_propre"])
    print("       indifferents aux deux          : %d" % cats["live_indifferent"])
    print("   (C) portent une VALEUR EN DUR      : %d  (assert == entier > %d)"
          % (cats["expose_valeur_dure"], _SEUIL_ENTIER))
    print("       ECARTES PAR CE SEUIL : les egalites a un entier <= %d (indices, compteurs,"
          % _SEUIL_ENTIER)
    print("       petits ordinaux), et toute comparaison qui n'est pas `==` dans un `assert`.")
    print("  --- ce qui reste A JOUER (#419-r6-r1) ---")
    print("   indifferents DEJA joues par le canal (C) : %d"
          % cats["indifferent_deja_joue_par_C"])
    print("   indifferents JAMAIS joues                : %d" % cats["indifferent_non_joue"])
    print("  --- CE QUE CE BALAYAGE NE VISITE PAS ---")
    print("   * les probes `scripts/python/probe_*.py` (ils mesurent, ils ne gardent rien) ;")
    print("   * ce qu'un test atteint via une fixture d'un AUTRE paquet ;")
    print("   * la face DECISION hors tests (`engine_validate.py`, `predict_sweep.py`), qui")
    print("     monte pourtant des runners -- non couverte par cette tranche.")

    if a.lister:
        print("=== liste : %s (%d) ===" % (a.lister, len(par_cat[a.lister])))
        for rel in par_cat[a.lister]:
            if a.lister == "dur":
                print("  %s" % rel)
                for ln, txt in durs[rel][:4]:
                    print("      L%-5d %s" % (ln, txt))
            else:
                print("  %s" % rel)

    if a.jouer or a.fichiers:
        rels = ([s.strip() for s in a.fichiers.split(",") if s.strip()]
                if a.fichiers else par_cat[a.jouer])
        fin = a.jusqu_a or len(rels)
        rels = rels[a.depuis:fin]
        regime = None if a.regime == "defaut" else a.regime
        print("=== JEU : %d fichier(s) (%s), regime TACTICUS_BIS_ITEMS=%s ==="
              % (len(rels), a.jouer or "liste explicite", a.regime))
        res = _jouer(rels, regime, a.workers)
        n_inerte = n_rouge = n_vert = 0
        for r in sorted(res, key=lambda x: x["fichier"]):
            if r["failed"] or r["error"] or r["rc"] not in (0, 1):
                etat, n_rouge = "ROUGE ", n_rouge + 1
            elif r["inerte"]:
                etat, n_inerte = "INERTE", n_inerte + 1
            else:
                etat, n_vert = "vert  ", n_vert + 1
            print("  %s %-58s p=%-3d s=%-3d f=%-3d e=%-3d rc=%d"
                  % (etat, r["fichier"], r["passed"], r["skipped"], r["failed"],
                     r["error"], r["rc"]))
        print("  BILAN : %d vert, %d INERTE (garde #455), %d ROUGE"
              % (n_vert, n_inerte, n_rouge))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
