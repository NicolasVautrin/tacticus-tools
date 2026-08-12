"""Contre-epreuve du garde `tests/engine/test_964r1_ecog_support_offline.py` (#964-r1).

Un test vert ne prouve rien tant qu'on n'a pas montre qu'il ROUGIT sur la faute qu'il pretend
garder. Ce probe MUTE l'arbre dans une COPIE de l'arbre de travail (jamais en place), rejoue le
garde, et verifie que chaque mutation fait tomber le test ATTENDU -- ni plus, ni moins.

Quatre mutations, choisies parce qu'elles sont les modes de panne SILENCIEUX du port :

  A. `get_ability_type` retire de `PerformAIAbility`  -> l'E-Cog ATTAQUE au lieu de REPARER
  B. le sens de l'`If` inverse                        -> spawn et reparation echanges
  C. `override_movement` passe a `None`               -> l'E-Cog se DEPLACE avant de reparer
  D. l'appel a `unit_repaired_triggers` retire        -> registered-but-dead

Aucun runner, aucun RPC : purement offline. ASCII only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

_ICI = os.path.dirname(os.path.abspath(__file__))
_TEST = os.path.join("tests", "engine", "test_964r1_ecog_support_offline.py")

#: (nom, fichier relatif, ancien, nouveau, test qui DOIT rougir)
_MUTATIONS = [
    ("A get_ability_type retire",
     os.path.join("engine", "runner", "operations", "triggers", "loki", "ecog_support.py"),
     "        get_ability_type=_repair_type_of)",
     "        )",
     "test_perform_ai_ability_joue_le_REPAIR_pas_l_attaque_normale"),
    ("B sens de l'If inverse",
     os.path.join("engine", "runner", "operations", "triggers", "loki", "ecog_support.py"),
     "    cap_libre = AmountIsGreater(Const(int(max_summons)), Count(already_summoned_units()))",
     "    cap_libre = AmountIsGreater(Count(already_summoned_units()), Const(int(max_summons)))",
     "test_arbre_forme_et_sens_du_if"),
    ("C override_movement a None",
     os.path.join("engine", "runner", "operations", "triggers", "loki", "ecog_support.py"),
     "        override_movement=Const(0),",
     "        override_movement=None,",
     "test_override_movement_est_direct_zero_pas_none"),
    ("D emetteur UnitRepaired retire",
     os.path.join("engine", "runner", "operations", "repair.py"),
     "        _repair_dispatch.unit_repaired_triggers(state, caster_id, int(target_id))",
     "        pass",
     "test_repair_operation_appelle_l_emetteur"),
]


def _copie_arbre(dst: str) -> None:
    """Copie l'arbre `scripts/python` (sources + tests + entrees), sans les caches."""
    shutil.copytree(_ICI, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "logs"))


def _joue(racine: str, nodeid: str | None = None) -> tuple[int, str]:
    cible = _TEST if nodeid is None else f"{_TEST}::{nodeid}"
    p = subprocess.run([sys.executable, "-m", "pytest", cible, "-q", "--no-header"],
                       cwd=racine, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    echecs = []
    with tempfile.TemporaryDirectory(prefix="probe964r1_") as tmp:
        racine = os.path.join(tmp, "python")
        _copie_arbre(racine)

        rc, out = _joue(racine)
        print("TEMOIN (arbre non mute) : rc=%d" % rc)
        if rc != 0:
            print(out[-2000:])
            print("ECHEC : le temoin doit etre VERT avant toute mutation.")
            return 1

        for nom, rel, avant, apres, attendu in _MUTATIONS:
            chemin = os.path.join(racine, rel)
            with open(chemin, encoding="utf-8") as fh:
                src = fh.read()
            if src.count(avant) != 1:
                print("  %-32s NON APPLIQUEE (motif absent ou ambigu : %d)"
                      % (nom, src.count(avant)))
                echecs.append(nom + " (motif introuvable)")
                continue
            with open(chemin, "w", encoding="utf-8") as fh:
                fh.write(src.replace(avant, apres))
            rc_m, out_m = _joue(racine, attendu)
            with open(chemin, "w", encoding="utf-8") as fh:      # restauration immediate
                fh.write(src)
            verdict = "MORD" if rc_m != 0 else "INERTE"
            print("  %-32s -> %-6s  (%s)" % (nom, verdict, attendu))
            if rc_m == 0:
                echecs.append(nom)

    print()
    if echecs:
        print("ECHEC : %d mutation(s) INERTE(S) -- le garde ne les voit pas : %s"
              % (len(echecs), ", ".join(echecs)))
        return 1
    print("OK -- les %d mutations mordent toutes." % len(_MUTATIONS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
