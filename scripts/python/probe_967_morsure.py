"""#967 -- le garde offline MORD-il ? Chaque mutation doit faire ROUGIR le fichier de test.

Un fichier de test vert au PREMIER passage ne prouve rien : #957 en a livre deux qui etaient
MUETS (temoins degeneres), et quatre contre-epreuves qui n'avaient pas mordu. Le seul controle qui
tranche est la MUTATION : on casse volontairement un terme du port, on rejoue le garde, et on
exige `rc != 0`. Une mutation qui laisse VERT designe un terme que rien ne tient.

Les mutations sont textuelles et appliquees EN PLACE, avec restauration systematique (`finally`).
Elles portent une par une sur les termes que le decompile impose :

    MIN_UTILITY de 1213 (2 -> 1)              le seul seuil des six qui ne vaut pas 1
    FilterContinuous fantome sur la ligne     1213 n'en a PAS (contraste 1187)
    plancher de 1143 (1 -> 0)                 ce qui separe ForwardSpotter d'AlphaWarrior
    penalite amie de 1142 (-1 -> +1)          le tir fratricide cesse d'etre penalise
    occupant de 1142 (+3/-3 -> 0)             le terme d'occupant disparait
    percage de 1214 (100 - r -> r)            l'utilite croit avec le percage au lieu de decroitre
    bonus de 1214 (500 -> 0)                  la classe de bonus disparait
    priorite de 1223 (-1000 -> 0)             le tier `Last` remonte au tier `Normal`
    ordre du selecteur (liste -> triee)       l'argmax redevient decide par la VALEUR de l'id
    gate de 1213 (`should_evaluate` -> True)  le pre-filtre de grappe disparait
    stat de 1224 (ATTACK -> constante)        l'utilite cesse de classer par l'attaque

Usage : `python probe_967_morsure.py` (rc 0 = toutes les mutations mordent).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
NC = RACINE / "engine" / "playbook" / "noncomparable"
TEST = "tests/engine/playbook/test_967_mow_decision_faces_offline.py"

#: (libelle, fichier, texte AVANT, texte APRES)
MUTATIONS = [
    ("1213 : MIN_UTILITY 2 -> 1", NC / "storm_speeder.py",
     "    MIN_UTILITY = 2.0     # `DeathOnTheWindPlaybook$$.cctor`",
     "    MIN_UTILITY = 1.0     # `DeathOnTheWindPlaybook$$.cctor`"),
    ("1213 : FilterContinuous fantome sur la ligne", NC / "storm_speeder.py",
     "    return sum(1 for tile in line if tile in enemy_set)   # PAS de `break`",
     "    return len([1 for i, t in enumerate(line) if all(x in enemy_set for x in line[:i + 1])])"
     "   # MUTATION"),
    ("1213 : gate `should_evaluate` toujours vrai", NC / "storm_speeder.py",
     "        epos = [p for p in (ctx.epos or []) if p and p[0] is not None]\n"
     "        if not epos:\n"
     "            return True                                   # canal muet",
     "        return True\n"
     "        epos = [p for p in (ctx.epos or []) if p and p[0] is not None]\n"
     "        if not epos:\n"
     "            return True                                   # canal muet"),
    ("1214 : percage 100 - r -> r", NC / "storm_speeder.py",
     "        return self.PIERCE_BASE - float(ratio)",
     "        return float(ratio)"),
    ("1214 : bonus 500 -> 0", NC / "storm_speeder.py",
     "    RANGED_BONUS = 500.0",
     "    RANGED_BONUS = 0.0"),
    ("1143 : plancher 1 -> 0", NC / "ordnance_battery.py",
     "    BASE_UTILITY = 1.0",
     "    BASE_UTILITY = 0.0"),
    ("1142 : penalite amie -1 -> +1", NC / "ordnance_battery.py",
     "    ADJACENT_ENEMY, ADJACENT_FRIEND = 1, -1",
     "    ADJACENT_ENEMY, ADJACENT_FRIEND = 1, 1"),
    ("1142 : terme d'occupant +3/-3 -> 0", NC / "ordnance_battery.py",
     "    OCCUPANT_ENEMY, OCCUPANT_FRIEND = 3, -3",
     "    OCCUPANT_ENEMY, OCCUPANT_FRIEND = 0, 0"),
    ("1223 : PRIORITY -1000 -> 0", NC / "necro_reanimator.py",
     "    PRIORITY = native_priority(int(ActiveAbilityType.ReanimationBeam))   # -1000",
     "    PRIORITY = 0   # MUTATION -- #"),
    ("1224 : utilite ATTACK -> constante", NC / "necro_reanimator.py",
     "            atk = float(ctx.scene.attack_current(tid))",
     "            atk = 1.0"),
    ("selecteur : l'ordre natif remplace par un tri", NC / "_targets.py",
     "        out.append((tid, p if (p and p[0] is not None) else None))\n"
     "    return out",
     "        out.append((tid, p if (p and p[0] is not None) else None))\n"
     "    return sorted(out, key=lambda x: x[0])"),
]


def _jouer() -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header", "-x"],
                       cwd=str(RACINE), capture_output=True, text=True)
    return r.returncode


def main() -> int:
    print("[967] controle de MORSURE du garde offline")
    base = _jouer()
    if base != 0:
        print("  ARRET : le garde est DEJA rouge sans mutation (rc=%d) -- rien de mesurable" % base)
        return 2
    print("  temoin non mute : rc=0 (vert)")
    muets = []
    for libelle, chemin, avant, apres in MUTATIONS:
        src = chemin.read_text(encoding="utf-8")
        if avant not in src:
            print("  ANCRE INTROUVABLE : %-46s -> mutation NON APPLIQUEE" % libelle)
            muets.append(libelle + " (ancre introuvable)")
            continue
        chemin.write_text(src.replace(avant, apres, 1), encoding="utf-8")
        try:
            rc = _jouer()
        finally:
            chemin.write_text(src, encoding="utf-8")
        etat = "MORD" if rc != 0 else "MUET"
        print("  %-46s -> rc=%d  %s" % (libelle, rc, etat))
        if rc == 0:
            muets.append(libelle)
    apres_tout = _jouer()
    if apres_tout != 0:
        print("  ARRET : restauration incomplete -- le garde est rouge apres coup (rc=%d)"
              % apres_tout)
        return 2
    print("  restauration verifiee : rc=0")
    if muets:
        print("  %d mutation(s) MUETTE(S) : %s" % (len(muets), ", ".join(muets)))
        return 1
    print("  les %d mutations MORDENT toutes" % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
