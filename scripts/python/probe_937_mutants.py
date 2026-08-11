"""#937 -- HARNAIS ADVERSARIAL de `tests/engine/runner/test_synaptic_linchpin_live.py` : chaque
alteration du port doit faire ROUGIR au moins un cas. Un mutant qui reste VERT designe une
assertion manquante -- ou un etage reellement INERTE, qu'il faut alors NOMMER.

⚠ **UN MUTANT NE << MORD >> PAS PARCE QUE `rc != 0`** -- et ce probe existe sous cette forme parce
que la confusion a ete FAITE. Lors du 1er passage, une fenetre de maintenance (drain) a tue la
session Frida au milieu de la serie : les six derniers mutants ont rendu `2 deselected, 9 errors`,
c'est-a-dire **zero assertion evaluee**, et un lecteur qui ne regarde que le code retour les compte
tous comme des morsures. Le verdict est donc lu dans le BILAN pytest :

    N failed, M passed      -> MORD          (des assertions ont ete evaluees, certaines ont cede)
    0 failed, M passed      -> INERTE        (le mutant ne change aucun observable garde)
    E errors / 0 passed     -> INDISPONIBLE  (montage casse : session morte, runner refuse, ...)

`INDISPONIBLE` n'est **ni** un vert **ni** un rouge : le probe le dit et sort en `rc=99`, comme
`host_inputs.py` distingue « pas mesure » de « mesure et vide ».

Chaque mutant est un couple (motif EXACT, remplacement) applique au fichier PORTE puis restaure
dans un `finally`. Le motif absent -> `MUTANT INVALIDE` (le port a bouge sous le harnais), jamais
un silence.

Usage (depuis scripts/python) :
    python probe_937_mutants.py [--only M4] [--keep-going]
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LINCH = ROOT / "engine/runner/operations/triggers/loki/synaptic_linchpin.py"
GEOM = ROOT / "engine/entities/selectors/geometry.py"
BEH = ROOT / "engine/entities/behaviours.py"
TEST = "tests/engine/runner/test_synaptic_linchpin_live.py"

#: (nom, fichier, motif EXACT, remplacement). Le nom porte le conjoint natif vise.
MUTANTS = [
    ("M1 HasTrait(actor, Synapse) retire", LINCH,
     "        if not _ACTOR_HAS_SYNAPSE.should_trigger(entities):          # HasTrait(actor, Synapse)\n"
     "            return False\n",
     "        if False:\n            return False\n"),
    ("M2 AreFriends(owner, actor) retire", LINCH,
     "        if not _OWNER_ACTOR_FRIENDS.should_trigger(entities):        # AreFriends(owner, actor)\n"
     "            return False\n",
     "        if False:\n            return False\n"),
    ("M3 IsAlive(target) retire", LINCH,
     "        return bool(_TARGET_IS_ALIVE.should_trigger(entities))",
     "        return True"),
    ("M4 cap sur l'accumulateur du CAST au lieu de Children(owner)", LINCH,
     "    live_summons = UnitsWithId(ChildrenOf(Owner()), unit_id,\n"
     "                               int(UnitSelectionType.OnlyAliveAndTargetable))",
     "    from .....entities.selectors.tiles import Children as _CastChildren\n"
     "    live_summons = UnitsWithId(_CastChildren(), unit_id,\n"
     "                               int(UnitSelectionType.OnlyAliveAndTargetable))"),
    ("M5 UnitsWithId n'applique plus son UnitSelectionType", GEOM,
     "                if u.get(\"visualId\") == uid and selection_ok_from_ctx(u, self.mode, ctx)]",
     "                if u.get(\"visualId\") == uid]"),
    ("M6 on_appearance retire (le summon n'attaque plus)", LINCH,
     "        on_appearance=UseNormalAttackIfAble(ActiveTarget(), Target()),",
     "        on_appearance=None,"),
    ("M7 Spawn ancre sur l'ACTEUR au lieu du PORTEUR", LINCH,
     "        entities = entities_from_state(state, self.owner_id, ev.target_id, ev.actor_id)\n"
     "        synaptic_linchpin_spawn_tree(",
     "        entities = entities_from_state(state, ev.actor_id, ev.target_id, ev.actor_id)\n"
     "        synaptic_linchpin_spawn_tree("),
    ("M8 AdjacentTiles(Target) -> AdjacentTiles(Owner)", LINCH,
     "        First(SortTilesByUtility(CanAddUnit(AdjacentTiles(Target())),",
     "        First(SortTilesByUtility(CanAddUnit(AdjacentTiles(Owner())),"),
    ("M9 ability_state retire (stats du summon a l'index par defaut)", LINCH,
     "        ability_state=ability_state)",
     "        ability_state=None)"),
    ("M10 Repeat: UNE iteration quel que soit `times`", BEH,
     "        for _ in range(max(0, int(n))):\n"
     "            res = res.combine(self.body.execute(entities, ectx))   # PAS de court-circuit (natif)",
     "        for _ in range(1):\n"
     "            res = res.combine(self.body.execute(entities, ectx))   # PAS de court-circuit (natif)"),
]

_BILAN = re.compile(r"(?:(\d+) failed)?[, ]*(?:(\d+) passed)?[, ]*(?:(\d+) errors?)?")


#: Le test du noeud `Repeat` vit HORS du fichier d'ability : le mutant M10 y est INOBSERVABLE
#: (`nrOfSummons == 1`), donc il est garde la ou il mord. Les deux fichiers sont joues ENSEMBLE,
#: sinon M10 rendrait INERTE alors qu'il MORD.
TEST_REPEAT = "tests/engine/test_937_repeat_node_offline.py"


def _run():
    out = subprocess.run([sys.executable, "-m", "pytest", TEST, TEST_REPEAT, "-q", "-k", "offline",
                          "--no-header", "-p", "no:cacheprovider"],
                         cwd=str(ROOT), capture_output=True, text=True)
    lines = [x for x in (out.stdout or "").strip().split("\n") if x.strip()]
    return out.returncode, (lines[-1] if lines else "(aucune sortie)")


def _verdict(tail: str) -> str:
    """MORD / INERTE / INDISPONIBLE -- lu dans le BILAN pytest, jamais dans le code retour."""
    failed = int((re.search(r"(\d+) failed", tail) or [0, 0])[1] or 0) if "failed" in tail else 0
    passed = int((re.search(r"(\d+) passed", tail) or [0, 0])[1] or 0) if "passed" in tail else 0
    errors = int((re.search(r"(\d+) errors?", tail) or [0, 0])[1] or 0) if "error" in tail else 0
    if errors and passed == 0:
        return "INDISPONIBLE"          # montage casse : AUCUNE assertion evaluee
    if failed:
        return "MORD"
    return "INERTE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="prefixe du mutant (ex. M4)")
    ap.add_argument("--keep-going", action="store_true",
                    help="poursuit meme apres un INDISPONIBLE (par defaut on s'arrete)")
    a = ap.parse_args()

    rc0, t0 = _run()
    v0 = _verdict(t0)
    print("[937m] BASELINE : %s  (%s)" % (v0, t0))
    if v0 == "INDISPONIBLE":
        print("[937m] VERDICT: INDISPONIBLE -- le montage ne tourne pas, aucun mutant n'est jugeable")
        return 99
    if rc0 != 0:
        print("[937m] VERDICT: BASELINE ROUGE -- inutile de muter")
        return 1

    inertes, invalides, indispo = [], [], []
    for name, path, old, new in MUTANTS:
        if a.only and not name.startswith(a.only):
            continue
        src = io.open(path, encoding="utf-8").read()
        if old not in src:
            print("%-58s : MUTANT INVALIDE (motif absent -- le port a bouge)" % name)
            invalides.append(name)
            continue
        io.open(path, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
        try:
            _rc, tail = _run()
        finally:
            io.open(path, "w", encoding="utf-8", newline="\n").write(src)
        v = _verdict(tail)
        print("%-58s : %-13s (%s)" % (name, v, tail))
        if v == "INERTE":
            inertes.append(name)
        elif v == "INDISPONIBLE":
            indispo.append(name)
            if not a.keep_going:
                print("[937m] ARRET : montage indisponible -- les mutants suivants ne seraient pas "
                      "jugeables (c'est EXACTEMENT le faux positif que ce probe existe pour eviter)")
                break

    rc1, t1 = _run()
    print("[937m] RESTAURE : %s  (%s)" % (_verdict(t1), t1))
    if indispo or _verdict(t1) == "INDISPONIBLE":
        print("[937m] VERDICT: INDISPONIBLE -- %d mutant(s) non jugeable(s) : %s"
              % (len(indispo), ", ".join(indispo) or "(restauration)"))
        return 99
    if invalides:
        print("[937m] VERDICT: FAIL -- %d mutant(s) INVALIDE(s) : %s"
              % (len(invalides), ", ".join(invalides)))
        return 1
    if inertes:
        print("[937m] VERDICT: FAIL -- %d mutant(s) INERTE(s), a couvrir ou a NOMMER : %s"
              % (len(inertes), ", ".join(inertes)))
        return 1
    print("[937m] VERDICT: PASS -- tous les mutants joues MORDENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
