#!/usr/bin/env python3
"""#287-r13-r1 -- le RAYON DE SOUFFLE d'un refus dur sur le deficit de roster, MESURE.

LE RESIDU, ET CE QUI LE BLOQUAIT
---------------------------------
`rl_duel._verify_roster` (#287-r13) confronte le roster DEMANDE au roster MONTE et NOMME chaque
exemplaire absent -- mais laisse le `rc` inchange, la ou le deficit de PLACEMENT rend `3`. Le
refus dur n'a pas ete pose << faute de mesure : le rayon de souffle n'est pas derivable de la
config, il faudrait REJOUER chaque montage >>.

C'est vrai de la FREQUENCE du deficit. Ce n'est PAS vrai du rayon, qui se derive exactement --
et il se derive parce qu'un `rc` ne casse que ce qui le LIT.

LES DEUX ETAGES, ET POURQUOI L'ORDRE COMPTE
---------------------------------------------
  * **etage 1 -- QUI LIT le rc** (statique, exact). Un appelant qui ne lie meme pas le resultat
    de `subprocess.run` ne peut pas etre casse : le `return 3` de `cmd_build` arrive APRES
    `_save_state`, donc le runner existe, le state-file est ecrit, et l'appelant qui ignore le
    `rc` poursuit exactement comme avant. Le rayon, c'est `check=True` + `.returncode` teste.
  * **etage 2 -- COMBIEN de montages DECLENCHENT** le deficit (live, echantillon). Le produit
    des deux est le risque reel ; l'etage 1 seul le SUR-estime, et c'est le bon sens pour une
    mesure de risque.

⚠ **Un `--list-pool` ne monte AUCUNE bataille** -- il n'atteint jamais `_verify_roster`. Le
compter dans le rayon gonflerait le chiffre d'appelants structurellement hors de portee : la
ventilation les SEPARE.

⚠ **L'etage 1 penche du cote BRUYANT, et c'est declare** : `.returncode` est cherche dans tout
le FICHIER, pas dans la seule fonction appelante. Un fichier qui lie le resultat sous un nom
reutilise ailleurs est donc compte a risque. Sur-estimer un rayon fait renoncer a un refus
qu'on aurait pu poser ; sous-estimer le fait poser un refus qui casse. La dissymetrie est
voulue.

    python probe_287r13r1_rayon_refus_roster.py               # etage 1 seul (offline)
    python probe_287r13r1_rayon_refus_roster.py --live        # + etage 2 (monte des runners)

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYDIR = REPO / "scripts" / "python"

#: Ce qui doit changer pour que cette mesure puisse changer de valeur.
DECLENCHEUR = {
    "chemins": ("scripts/python/rl_duel.py", "scripts/python/probe_*.py",
                "scripts/python/tests/**/*.py"),
    "build": False,
    "toujours": False,
    "raison": "Le rayon se derive des APPELANTS de `rl_duel build` -- ils vivent dans les probes "
              "et les tests -- et du point ou `cmd_build` rend son `rc`, dans `rl_duel.py`.",
}

#: Les montages de l'etage 2. Choisis pour COUVRIR les formes reellement ecrites par les
#: appelants a risque (rosters courts et nommes), et non pour maximiser le taux de deficit :
#: mesurer la frequence sur des montages tordus repondrait a une autre question.
#: Les quatre premiers sont ceux deja mesures par #287-r13 ; les suivants reproduisent la forme
#: des appelants que l'etage 1 designe.
MONTAGES = (
    ("roster aleatoire",      ["--roster", "5", "--board", "MC1_67"]),
    ("MoW",                   ["--board", "C1_02", "--p-mow", "deathCrawler",
                               "--p-units", "necroWarden", "--a-units", "orksNob"]),
    ("multiplicite x4",       ["--board", "C1_09", "--a-units",
                               "necroWarden,necroWarden,necroWarden,necroWarden",
                               "--p-units", "orksNob"]),
    ("deux camps nommes",     ["--board", "MC1_67", "--p-units", "orksBigMek,orksNob",
                               "--a-units", "worldKharn,templChampion"]),
    ("cinq contre cinq",      ["--board", "MC1_67", "--p-units",
                               "orksBigMek,orksNob,orksWarboss,astraBullgryn,necroWarden",
                               "--a-units",
                               "worldKharn,templChampion,eldarJainZar,tauMarksman,darkaHellblaster"]),
    ("un contre un",          ["--board", "C1_02", "--p-units", "orksNob",
                               "--a-units", "necroWarden"]),
    ("board etroit x5",       ["--board", "C1_01", "--p-units",
                               "orksBigMek,orksNob,orksWarboss,astraBullgryn,necroWarden",
                               "--a-units", "worldKharn"]),
    ("multiplicite x6",       ["--board", "MC1_31", "--p-units",
                               "necroWarden,necroWarden,necroWarden,necroWarden,"
                               "necroWarden,necroWarden", "--a-units", "orksNob"]),
)


# --------------------------------------------------------------- ETAGE 1 : QUI LIT le rc
def tracked_py() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO),
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit("git ls-files a echoue : %s" % (r.stderr or "").strip())
    return [p for p in r.stdout.split("\0") if p.endswith(".py")]


#: MEMO DE RESULTAT (#941), meme forme que les quatre balayages de #486-r5 -- jamais un cache
#: d'AST. Ce qui est retenu est minuscule (un tuple de quadruplets) ; ce qui est evite est le
#: balayage de tout `git ls-files`, `ast.unparse` compris.
_INVOCATIONS_CACHE: tuple | None = None


def _balayer_invocations() -> list[tuple[str, int, str, bool]]:
    """LE BALAYAGE. Separe de `invocations()` pour qu'un cliquet puisse le SUBSTITUER et mesurer
    que le memo mord (garde : `test_486r5_balayages_memoises_offline.py`)."""
    out = []
    for rel in tracked_py():
        if rel.endswith("rl_duel.py"):
            continue
        try:
            src = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "rl_duel" not in src:
            continue
        try:
            arbre = ast.parse(src, filename=rel)
        except SyntaxError:
            continue
        parent: dict[int, ast.AST] = {}
        for n in ast.walk(arbre):
            for c in ast.iter_child_nodes(n):
                parent[id(c)] = n
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            try:
                txt = ast.unparse(n)
            except Exception:                                   # noqa: BLE001
                continue
            if "rl_duel" not in txt:
                continue
            if "'build'" not in txt and '"build"' not in txt:
                continue
            monte = "list-pool" not in txt
            if "check=True" in txt:
                out.append((rel, n.lineno, "check=True", monte))
                continue
            p = parent.get(id(n))
            cible = None
            if isinstance(p, ast.Assign) and p.targets and isinstance(p.targets[0], ast.Name):
                cible = p.targets[0].id
            if cible is None:
                out.append((rel, n.lineno, "resultat non lie", monte))
                continue
            lit = any(isinstance(m, ast.Attribute) and m.attr == "returncode"
                      and isinstance(m.value, ast.Name) and m.value.id == cible
                      for m in ast.walk(arbre))
            out.append((rel, n.lineno, "rc teste" if lit else "rc IGNORE", monte))
    return out


def invocations() -> tuple[tuple[str, int, str, bool], ...]:
    """[(rel, ligne, garde, monte_une_bataille)] pour chaque `rl_duel ... build`.

    `garde` in {'check=True', 'rc teste', 'rc IGNORE', 'resultat non lie'}.
    `monte_une_bataille` est False pour `--list-pool`, qui n'atteint jamais `_verify_roster`.

    MEMOISE (#941). Le balayage visite TOUT `.py` versionne, `ast.unparse` a chaque `Call` des
    fichiers qui citent `rl_duel` -- mesure du 2026-08-11 : **38 s**, et les TROIS tests du
    cliquet le refaisaient chacun pour son compte (114 s pour un seul releve). La valeur rendue
    est un TUPLE, donc aucun appelant ne peut modifier ce que verra le suivant."""
    global _INVOCATIONS_CACHE
    if _INVOCATIONS_CACHE is None:
        _INVOCATIONS_CACHE = tuple(_balayer_invocations())
    return _INVOCATIONS_CACHE


# ------------------------------------------------------- ETAGE 2 : COMBIEN DECLENCHENT
#: LE montage a DEFICIT, re-derive de la mesure de #287-r13 (board `C1_02`, seed 4242) :
#: quatre `necroWarden` demandes, TROIS `--a-place` -> le quatrieme n'arrive jamais. C'est la
#: contre-epreuve de l'etage 3 : sans un montage qui DECLENCHE, un `rc == 3` observe ne
#: distinguerait pas << le refus mord >> de << rien n'a ete demande >>.
MONTAGE_A_DEFICIT = ["--board", "C1_02", "--p-units", "orksNob",
                     "--a-units", "necroWarden,necroWarden,necroWarden,necroWarden",
                     "--a-place", "necroWarden:2,6", "--a-place", "necroWarden:3,6",
                     "--a-place", "necroWarden:4,6"]


def joue(nom: str, args: list[str], seed: str, env_extra: dict | None = None
         ) -> tuple[bool, str, int]:
    """(deficit ?, extrait, rc). Le state-file est UNIQUE et ABSOLU, et le runner est DISPOSE."""
    fd, chemin = tempfile.mkstemp(prefix="p287r13r1_", suffix=".json")
    os.close(fd)
    env = dict(os.environ)
    env.update(env_extra or {})
    try:
        cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed,
               "--state-file", chemin] + args
        r = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300, env=env)
        blob = (r.stdout or "") + (r.stderr or "")
        deficit = "roster NON MONTE" in blob
        extrait = ""
        for ligne in blob.splitlines():
            if "roster NON MONTE" in ligne:
                extrait = ligne.strip()
                break
        if not deficit and r.returncode != 0:
            queue = (r.stderr or "").strip().splitlines()
            extrait = "rc=%d (AUTRE cause) : %s" % (r.returncode, queue[-1] if queue else "")
        return deficit, extrait, r.returncode
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT -- non mesure, pas 'propre'", -1
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", chemin],
                       cwd=str(PYDIR), capture_output=True, text=True, timeout=120)
        Path(chemin).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true",
                    help="joue l'etage 2 (monte des runners, un a la fois)")
    ap.add_argument("--seed", default="777")
    args = ap.parse_args()

    inv = invocations()
    montent = [i for i in inv if i[3]]
    listpool = [i for i in inv if not i[3]]
    risque = [i for i in montent if i[2] in ("check=True", "rc teste")]

    print("=== (1) LE RAYON : qui LIT le `rc` de `rl_duel build` ? ===")
    print("invocations `rl_duel ... build` : %d" % len(inv))
    print("  dont `--list-pool` (ne monte AUCUNE bataille, hors de portee) : %d" % len(listpool))
    print("  dont MONTENT une bataille                                    : %d" % len(montent))
    print("")
    for k, n in Counter(g for _r, _l, g, m in inv if m).most_common():
        print("    %-20s %d" % (k, n))
    print("")
    print("  RAYON DE SOUFFLE d'un refus dur : %d site(s) sur %d qui montent (%.1f %%)"
          % (len(risque), len(montent), 100.0 * len(risque) / max(1, len(montent))))
    for rel, ln, g, _m in sorted(risque):
        print("     %s:%d  [%s]" % (rel, ln, g))
    print("")
    print("  NB : le `return 3` de `cmd_build` arrive APRES `_save_state` -- le runner existe et")
    print("  le state-file est ecrit. Un appelant qui n'inspecte pas le `rc` poursuit a")
    print("  l'identique ; c'est pourquoi le rayon se derive au lieu de se supposer.")
    print("")

    if not args.live:
        print("=== (2) LA FREQUENCE : non mesuree (passer --live) ===")
        print("  Un rayon SEUL ne dit pas le risque : il faut savoir combien de montages")
        print("  DECLENCHENT le deficit. Ne pas confondre << pas mesure >> et << zero >>.")
        return 0

    print("=== (2) LA FREQUENCE : combien de montages DECLENCHENT le deficit ? ===")
    deficits, joues = [], 0
    for nom, extra in MONTAGES:
        d, ex, _rc = joue(nom, extra, args.seed)
        joues += 1
        etat = "DEFICIT" if d else "ok"
        print("  %-22s %-8s %s" % (nom, etat, ex[:90]))
        if d:
            deficits.append((nom, ex))
    print("")
    print("  montages joues : %d ; DEFICITS : %d" % (joues, len(deficits)))
    print("")

    # ----------------------------------------------------- (3) LE REFUS MORD-IL, ET SE LEVE-T-IL ?
    print("=== (3) CONTRE-EPREUVE : le refus dur mord, et l'echappatoire le leve ===")
    d_dur, ex_dur, rc_dur = joue("deficit / refus", MONTAGE_A_DEFICIT, "4242")
    d_lev, ex_lev, rc_lev = joue("deficit / echappatoire", MONTAGE_A_DEFICIT, "4242",
                                 env_extra={"TACTICUS_ALLOW_ROSTER_DEFICIT": "1"})
    print("  refus par defaut          : deficit=%s rc=%d   %s" % (d_dur, rc_dur, ex_dur[:70]))
    print("  TACTICUS_ALLOW_ROSTER_DEFICIT=1 : deficit=%s rc=%d" % (d_lev, rc_lev))
    ok3 = (d_dur and rc_dur == 3 and d_lev and rc_lev == 0)
    print("  VERDICT : %s" % ("les DEUX faces mordent" if ok3 else
                              "!! le refus ou son echappatoire ne se comporte pas comme attendu"))
    print("  Les deux bras jouent le MEME montage : sans le bras leve, un `rc == 3` ne")
    print("  distinguerait pas un refus d'un echec de montage ; sans le bras dur, un")
    print("  `rc == 0` ne distinguerait pas l'echappatoire d'une absence de deficit.")
    print("")

    print("=== VERDICT ===")
    print("  rayon    : %d site(s) qui liraient un `rc` change" % len(risque))
    print("  frequence: %d / %d montages representatifs declenchent le deficit"
          % (len(deficits), joues))
    print("  refus    : %s" % ("mord ET se leve" if ok3 else "COMPORTEMENT INATTENDU"))
    print("  Le risque reel est le PRODUIT des deux premiers, jamais l'un des deux seul.")
    return 0 if ok3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
