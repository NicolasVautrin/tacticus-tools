"""PASSE DE MUTANTS du port `1210 ExemplarOfTheMontka` -- chaque mutation doit MORDRE.

Un cliquet qui ne rougit sur AUCUNE deformation du port ne garde rien. Ce probe applique une a une
DIX mutations au code REEL (edition en place, restauration en `finally`), rejoue
`tests/engine/runner/test_1210_exemplar_of_the_montka_offline.py`, et exige que la passe DEVIENNE
ROUGE. Un mutant qui reste VERT est imprime comme `INERTE` -- c'est une QUESTION, pas un succes.

Chaque mutation est une deformation PLAUSIBLE : soit la recopie du voisin de forme
(`WarHowl` 1106, dont 1210 differe sur quatre points), soit l'oubli d'un litteral natif.

    python probe_1210_mutants.py            # les dix
    python probe_1210_mutants.py --only M4  # un seul

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
TAU = PYDIR / "engine" / "runner" / "abilities" / "tau.py"
EFF = PYDIR / "engine" / "entities" / "effects" / "loki" / "exemplar_of_the_montka.py"
TEST = "tests/engine/runner/test_1210_exemplar_of_the_montka_offline.py"

#: (id, fichier, ancien, nouveau, ce que la mutation SIMULE)
MUTANTS = [
    ("M1", TAU,
     "    return UnitsWithRangedWeapons(\n        UnitsWithTrait(friends, _MONTKA_TRAIT,"
     "                    # 0x10 = Hero\n                       selection_type=_MONTKA_SELECTION))"
     "         # 4e argument natif : 3",
     "    return UnitsWithTrait(friends, _MONTKA_TRAIT,\n"
     "                          selection_type=_MONTKA_SELECTION)",
     "filtre UnitsWithRangedWeapons OUBLIE (le buff partirait aux amis melee)"),
    ("M2", TAU,
     "        UnitsWithTrait(friends, _MONTKA_TRAIT,                    # 0x10 = Hero\n"
     "                       selection_type=_MONTKA_SELECTION))         # 4e argument natif : 3",
     "        friends)",
     "filtre UnitsWithTrait(Hero) OUBLIE (le buff partirait aux summons ranged)"),
    ("M3", EFF, "        return [(UnitTrait.Unstoppable, True)]",
     "        return []",
     "`applied_traits` VIDE -- le no-op SILENCIEUX que le canal de pose ne signale pas"),
    ("M4", EFF, '    key = "extraDmg_2" if big else "extraDmg"',
     '    key = "extraDmg" if big else "extraDmg_2"',
     "branches du `If` INVERSEES (value-preserving en structure, FAUX en valeur)"),
    ("M5", EFF, "        if is_normal_attack is not True:                   # IsNormalAttack",
     "        if is_ranged is not False:                         # IsMeleeAttack (RECOPIE de 1222)\n"
     "            return None\n"
     "        if is_normal_attack is not True:                   # IsNormalAttack",
     "gate `IsMeleeAttack` AJOUTE par recopie de 1222 (tue le buff des attaques distantes)"),
    ("M6", TAU, "    friends = Friends(AllAliveUnits(), reference=Caster(),"
                "        # Friends(of = Caster@+0x48, ...)\n"
                "                      selection_type=_MONTKA_SELECTION)           "
                "# 4e argument natif : 3",
     "    friends = Friends(AllAliveUnits(), reference=Caster())",
     "`selectionType = 3` OUBLIE (sur-buffe une unite en DEEP STRIKE, mesure #585)"),
    ("M7", TAU, "        rules=TR.CasterIsPossibleTarget | TR.CasterMatchesDynamicRule,",
     "        rules=TR.CasterIsPossibleTarget | TR.CasterMatchesDynamicRule "
     "| TR.CasterHasNotMoved,",
     "masque RECOPIE de 1216/1192 (`| 0x10`) -- 1210 n'a PAS `CasterHasNotMoved`"),
    ("M8", TAU, "                     duration_turns=1,               "
                "# `<DSLFormulas+0x20>` = 1 -> 1 TOUR, PAS 1 round",
     "                     duration_rounds=1,",
     "duree lue en ROUNDS au lieu de TOURS (`TurnsFromRounds` invente)"),
    ("M9", TAU, "                     scale_from_source=True,         "
                "# `get_AbilityStateReference` = l'etat du CASTER",
     "                     scale_from_source=False,",
     "`AbilityStateReference` ignore -- le scaling lu sur le BUFFE, ecart SILENCIEUX"),
    # M10 est ecrit pour rester SYNTAXIQUEMENT VALIDE : un mutant qui ne fait que casser le parse
    # rougirait sans rien dire des assertions -- ce serait un faux MORD.
    ("M10", TAU,
     "    return UnitsWithRangedWeapons(\n"
     "        UnitsWithTrait(friends, _MONTKA_TRAIT,                    # 0x10 = Hero\n"
     "                       selection_type=_MONTKA_SELECTION))         # 4e argument natif : 3",
     "    inner = UnitsWithRangedWeapons(\n"
     "        UnitsWithTrait(friends, _MONTKA_TRAIT,\n"
     "                       selection_type=_MONTKA_SELECTION))\n"
     "    return Union(Caster(), inner)",
     "`op_Addition(Caster, ...)` RECOPIE de WarHowl -- 1210 n'en a pas"),
]


def _run_tests():
    p = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q"], cwd=str(PYDIR),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "")[-400:]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    a = ap.parse_args(argv)

    rc0, out0 = _run_tests()
    print("[1210-mut] REFERENCE (port intact) : rc=%d" % rc0)
    if rc0 != 0:
        print("[1210-mut] KO -- la reference est deja ROUGE, la passe ne prouverait rien :\n%s" % out0)
        return 2

    bad = []
    for mid, path, old, new, why in MUTANTS:
        if a.only and mid != a.only:
            continue
        src = path.read_text(encoding="utf-8")
        if old not in src:
            # Un mutant qui ne s'applique PAS est un FAUX VERT : on le dit, on ne le tait pas.
            print("[1210-mut] %-4s NON APPLIQUE (motif absent) -- %s" % (mid, why))
            bad.append(mid)
            continue
        try:
            path.write_text(src.replace(old, new, 1), encoding="utf-8")
            rc, out = _run_tests()
        finally:
            path.write_text(src, encoding="utf-8")
        verdict = "MORD" if rc != 0 else "INERTE"
        print("[1210-mut] %-4s %-7s rc=%d -- %s" % (mid, verdict, rc, why))
        if rc == 0:
            print("           sortie: %s" % out.replace("\n", " | ")[-220:])
            bad.append(mid)

    rc_final, _ = _run_tests()
    print("[1210-mut] RESTAURATION verifiee : rc=%d" % rc_final)
    if rc_final != 0:
        print("[1210-mut] KO -- l'arbre n'est PAS revenu a son etat initial")
        return 2
    if bad:
        print("[1210-mut] MUTANTS INERTES ou NON APPLIQUES : %s" % bad)
        return 1
    print("[1210-mut] OK -- les %d mutants MORDENT"
          % len([m for m in MUTANTS if not a.only or m[0] == a.only]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
