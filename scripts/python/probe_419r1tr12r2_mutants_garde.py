"""Contre-epreuve de la GARDE : mute le code livre, rejoue les tests, restaure.

Un remplacement qui ne MATCHE PAS produirait un vert trompeur (piege mesure par la tranche 12) :
chaque mutant LEVE si son motif est introuvable, et on verifie que le fichier a change.
"""
import subprocess
import sys
from pathlib import Path

PY = Path(__file__).resolve().parent          # scripts/python de CE checkout, jamais un chemin fige
TARGET = PY / "catalog_inject.py"
TEST = "tests/engine/test_419r1tr12r2_stats_npc_summon_offline.py"

MUTANTS = {
    # 1. ToZeroBasedIndex clampe au lieu de lever sur level <= 0
    "clamp_bas": (
        "    if level <= 0:\n"
        "        raise ValueError(\n"
        "            f\"unit level {level} <= 0 : ToZeroBasedIndex leve (InvalidOperationException)\")\n"
        "    return level - 1",
        "    return max(0, level - 1)",
    ),
    # 2. GetLevelFromUnitId : defaut = dernier palier au lieu de 1
    "defaut_dernier_palier": (
        "        except ValueError:\n            return 1\n    return 1",
        "        except ValueError:\n            return 10 ** 6\n    return 10 ** 6",
    ),
    # 3. GetStatsForLevel sans clamp HAUT
    "sans_clamp_haut": (
        "    return rows[min(_to_zero_based_index(lvl), len(rows) - 1)]",
        "    return rows[_to_zero_based_index(lvl)]",
    ),
    # 4. multiplicateur : recherche par rank (l'approximation heros) au lieu de l'indexation
    "mult_par_rank": (
        "    idx = max(0, min(int(progression_index), len(steps) - 1))\n"
        "    return steps[idx][\"abilityStatMultiplierPct\"]",
        "    return ability_multiplier_pct(17, 50, False)",
    ),
    # 5. le regime `_2` est ignore : tout passe en primary
    "toujours_primary": (
        "        key = key_primary if primary else key_secondary",
        "        key = key_primary",
    ),
    # 6. le balayage des declarants se restreint a `unitId`
    "declarants_partiels": (
        "SUMMON_ID_CONSTANTS = ((\"unitToSpawn\", 8, True), (\"unitId\", 0, True), "
        "(\"unitId_2\", 4, False))",
        "SUMMON_ID_CONSTANTS = ((\"unitId\", 0, True),)",
    ),
    # 7. l'ambiguite de declarant est tranchee en silence (premier arrive)
    "ambiguite_silencieuse": (
        "            if len(set(profils.values())) > 1:",
        "            if False:",
    ),
    # 8. `source` ne distingue plus le mirror de catalogue du montage post-spawn
    # ⚠ Motif RE-ANCRE par #419-r1-tr12-r2-r1 : le `return` porte desormais `zeroProfile`. Le probe
    # LEVE sur motif introuvable (c'est son point) -- il a donc SIGNALE sa propre peremption au
    # premier re-jeu, exactement comme il est ecrit pour le faire.
    "source_indistincte": (
        "    return {\"source\": \"summon-spawn\", \"fields\": st, \"ability\": ability,",
        "    return {\"source\": \"npc\", \"fields\": st, \"ability\": ability,",
    ),
}

# Mutants ATTENDUS INERTES, avec la raison. Les lister explicitement vaut mieux que de les
# omettre : un mutant inerte non declare se lit comme un trou de garde.
#   `summon_zero_ecrase` -- remplacer `if base == 0: continue` par `pass` ecrit `out[field] = 0`
#   la ou le champ valait deja 0. La valeur de depart d'un summon est 0 (sa config n'a pas de
#   `stats[]`), donc `if (var != 0)` et « ecraser toujours » sont ALGEBRIQUEMENT identiques dans
#   ce regime. Le garde reste ecrit parce qu'il est ce que dit le decompile.
INERTES_ATTENDUS = {
    "summon_zero_ecrase": (
        "        if base == 0:\n            continue                                    "
        "# `if (var != 0)` du decompile",
        "        pass",
    ),
}


def run_tests() -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header"],
                       cwd=PY, capture_output=True, text=True)
    return p.returncode, (p.stdout or "")[-400:]


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")
    rc_ref, out_ref = run_tests()
    print(f"[ref] code NON mute -> rc={rc_ref}  {out_ref.strip().splitlines()[-1]}")
    if rc_ref != 0:
        print("[ref] ECHEC : la garde ne passe deja pas, la contre-epreuve n'a pas de sens")
        return 1
    bilan = {}
    try:
        for name, (old, new) in {**MUTANTS, **INERTES_ATTENDUS}.items():
            if old not in src:
                raise SystemExit(f"[{name}] MOTIF INTROUVABLE -- un vert serait trompeur")
            muted = src.replace(old, new, 1)
            if muted == src:
                raise SystemExit(f"[{name}] le remplacement n'a rien change")
            TARGET.write_text(muted, encoding="utf-8")
            rc, out = run_tests()
            last = out.strip().splitlines()[-1] if out.strip() else "?"
            bilan[name] = rc
            print(f"[{name}] rc={rc}  {last}")
    finally:
        TARGET.write_text(src, encoding="utf-8")
    rc_end, out_end = run_tests()
    print(f"[restaure] rc={rc_end}  {out_end.strip().splitlines()[-1]}")
    inertes = [k for k, v in bilan.items() if v == 0 and k not in INERTES_ATTENDUS]
    mordants_surprise = [k for k in INERTES_ATTENDUS if bilan.get(k) != 0]
    if inertes:
        print(f"ECHEC : mutants INERTES non declares (la garde ne les voit pas) : {inertes}")
        return 1
    if mordants_surprise:
        # Un inerte-attendu qui se met a mordre veut dire que la demonstration d'inertie ne tient
        # plus : il faut la relire, pas la retirer.
        print(f"ECHEC : declares INERTES mais MORDANTS : {mordants_surprise} "
              f"-- la demonstration d'inertie est perimee")
        return 1
    if rc_end != 0:
        print("ECHEC : la restauration n'a pas remis le code d'aplomb")
        return 1
    print(f"OK : {len(MUTANTS)}/{len(MUTANTS)} mutants font ROUGIR la garde ; "
          f"{len(INERTES_ATTENDUS)} inerte(s) DECLARE(S) et confirme(s) ; restauration verte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
