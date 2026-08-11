#!/usr/bin/env python
"""Probe #931 (volet ADVERSARIAL) -- chaque mutation du port doit FAIRE ROUGIR au moins une phase
de `probe_931_twisted_science.py`. Un mutant qui passe VERT est soit un temoin aveugle, soit une
lecture native que rien n'exerce : il faut alors le NOMMER avec sa cause MESUREE, jamais le taire.

Le mutant est applique par REECRITURE TEMPORAIRE du fichier source (restaure dans un `finally`),
puis la phase visee est rejouee dans un SOUS-PROCESSUS -- sans quoi le module deja importe dans CE
processus resterait celui d'avant la mutation, et le mutant passerait VERT sans avoir mordu.

ASCII only (cp1252). Usage :
    python probe_931_mutants.py                 # tous
    python probe_931_mutants.py --only M3
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
GENE = PYDIR / "engine" / "runner" / "abilities" / "genestealer.py"
EFF = PYDIR / "engine" / "entities" / "effects" / "loki" / "twisted_science.py"

#: Les mutants dont on ATTEND qu'ils restent INERTES, avec la cause MESUREE. Un mutant inscrit ici
#: qui se met a MORDRE est signale aussi fort qu'un mutant attendu-mordant qui devient inerte : les
#: deux disent que la cause ecrite n'est plus vraie.
INERTES_ATTENDUS = {
    "M4": ("l'ORDRE des deux volets est ALGEBRIQUEMENT inobservable sur cet arbre. Le `ChangeStat` "
           "du port ne clampe PAS (branche HEALTH de la feuille) et le stat-mod 1355 est un pur "
           "DECALAGE ADDITIF du plafond, donc "
           "`min(hp + heal, old_max) + extra == min(hp + heal + extra, old_max + extra)` pour "
           "TOUT (hp, heal, extra, old_max) -- verifie exhaustivement par `_demo_m4()` ci-dessous. "
           "Ce n'est pas un trou de temoin : aucun montage ne peut les separer tant que ces deux "
           "faits tiennent, et le controle ci-dessous ROUGIT le jour ou l'un des deux change."),
    "M8": ("le refus des ENNEMIS est REDONDANT avec le bit `TargetIsFriendly` (0x400) du masque "
           "STATIQUE, evalue AVANT la regle dynamique par `targeting.get_invalid_target_reason`. "
           "La redondance est NATIVE, pas une scorie du port : le masque de "
           "`...TwistedScience_HealAbility$$.ctor` porte 0x400 ET son "
           "`$$GetDynamicInvalidTargetReason` refait `IsEnemy -> 0x400`. La sortie du mutant le "
           "MONTRE (les deux ennemis restent hors de l'ensemble du port)."),
}

#: `(id, fichier, ancien, nouveau, phase visee, ce que le mutant CASSE)`
MUTANTS = [
    ("M1", GENE,
     "cond = TriggerAnd(Not(HasEffect(Target(), TWISTED_SCIENCE_EXTRA_HP, active_only=False)),",
     "cond = TriggerAnd(HasEffect(Target(), TWISTED_SCIENCE_EXTRA_HP, active_only=False),",
     "cast", "gate de non-repose INVERSE -> plus aucun buff sur une cible vierge"),
    ("M2", GENE,
     "    is_gs = HasFaction(Target(), int(UnitFaction.Genestealers))",
     "    is_gs = HasFaction(Target(), int(UnitFaction.Ultramarines))",
     "cast", "gate de FACTION deplace -> 1356 sur la mauvaise cible"),
    ("M3", GENE,
     "    add_hp = ChangeStat(Target(), int(StatType.HEALTH), \"add\", _TS_HEAL_SOURCE, extra_hp)",
     "    add_hp = ChangeStat(Target(), int(StatType.HEALTH), \"add\", _TS_HEAL_SOURCE, 0)",
     "pauvre", "montant du ChangeStat a ZERO -> +hp de PV COURANTS perdus"),
    ("M4", GENE,
     "    return op_add(If(cond, buffs), heal)",
     "    return op_add(heal, If(cond, buffs))",
     "blesse", "ORDRE INVERSE (soin AVANT le releve de plafond) -> soin tronque"),
    ("M5", EFF,
     "        amt = self.get_stat_modification_amount()\n        return [(int(StatType.HEALTH), int(amt))] if amt else []",
     "        return []",
     "blesse", "stat-mod HEALTH non applique a la pose -> plafond fige"),
    ("M6", GENE,
     "            if not has_effect_of_type(state, tid, TWISTED_SCIENCE_EXTRA_HP):\n                return 0                                       # non marquee -> valide MEME a PV pleins",
     "            pass                                           # clause 'full HP' RETIREE",
     "gates", "clause 'allie non marque = legal meme a PV pleins' retiree -> plus aucune cible"),
    ("M7", GENE,
     "        if not is_affected_by_heal_type(state, tid, 0):        # HealType.NonMechanical\n            return int(TR.TargetIsHealable)",
     "        if False:\n            return int(TR.TargetIsHealable)",
     "meca", "premier gate (IsAffectedByHealType) retire -> le port accepte une MACHINE"),
    ("M8", GENE,
     "                return int(TR.TargetIsFriendly)\n            if not has_effect_of_type",
     "                return 0\n            if not has_effect_of_type",
     "gates", "refus des ENNEMIS retire de la regle DYNAMIQUE"),
    ("M9", GENE,
     "    add_dmg = AddEffect(TWISTED_SCIENCE_EXTRA_DMG, EffectType.TwistedScience_ExtraDmg.name,\n                        Target(), duration_rounds=None, scale_from_source=True)",
     "    add_dmg = AddEffect(TWISTED_SCIENCE_EXTRA_DMG, EffectType.TwistedScience_ExtraDmg.name,\n                        Target(), duration_rounds=None, scale_from_source=False)",
     "dmg", "AbilityStateReference non propage -> magnitude lue sur le BUFFE"),
    ("M10", GENE,
     "    cond = TriggerAnd(Not(HasEffect(Target(), TWISTED_SCIENCE_EXTRA_HP, active_only=False)),\n                      Not(OwnerIsTarget()))",
     "    cond = Not(HasEffect(Target(), TWISTED_SCIENCE_EXTRA_HP, active_only=False))",
     "self", "terme `!OwnerIsTarget` retire -> Hollan se buffe lui-meme"),
    ("M11", GENE,
     "        return 0 if ok else int(TR.TargetIsHealable)",
     "        return 0",
     "gates", "verdict `EntityCanBeHealed` ignore -> le port n'exclut plus la cible deja marquee"),
    ("M12", GENE,
     "        self_cast=False, range=RANGE_ADJACENT_IF_MELEE_CASTER,\n        force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)",
     "        self_cast=False, range=RANGE_WHOLE_BOARD,\n        force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)",
     "meca", "portee elargie au plateau entier -> le port accepte des allies non adjacents"),
]


def _demo_m4() -> bool:
    """La DEMONSTRATION EXECUTABLE de l'inertie de M4 -- et son CLIQUET.

    Les deux ordres calculent, pour le port :
      * ordre NATIF  : `hp' = hp + extra` (ChangeStat, non clampe) puis `min(hp' + heal, new_max)` ;
      * ordre INVERSE: `hp' = min(hp + heal, old_max)` (Heal, clampe sur l'ANCIEN plafond, le
                       stat-mod n'ayant pas encore ete pose) puis `hp' + extra`.
    avec `new_max = old_max + extra`. Balaye exhaustivement une grille et rend False des qu'un
    couple les separe -- ce qui arriverait si `ChangeStat` se mettait a clamper, ou si le stat-mod
    cessait d'etre un decalage additif. Le jour ou ca arrive, M4 devient un mutant EXERCABLE et
    cette entree doit sortir d'`INERTES_ATTENDUS`."""
    for old_max in (1000, 6023, 10038):
        for extra in (0, 1, 2992, 20000):
            new_max = old_max + extra
            for heal in (0, 1, 100, 3614, 99999):
                for hp in range(0, old_max + 1, max(1, old_max // 17)):
                    a = min(hp + extra + heal, new_max)
                    b = min(hp + heal, old_max) + extra
                    if a != b:
                        print("[931][M4-demo] SEPARES : old_max=%d extra=%d heal=%d hp=%d -> %d vs %d"
                              % (old_max, extra, heal, hp, a, b))
                        return False
    print("[931][M4-demo] les deux ordres coincident sur TOUTE la grille balayee "
          "(3 plafonds x 4 magnitudes x 5 soins x 18 niveaux de PV)")
    return True


def _run_phase(phase: str) -> int:
    p = subprocess.run([sys.executable, "probe_931_twisted_science.py", "--phase", phase],
                       cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    tail = [l for l in (p.stdout or "").splitlines() if l.startswith("[931]")]
    for l in tail[-4:]:
        print("      | " + l)
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    anomalies = []
    for mid, path, old, new, phase, quoi in MUTANTS:
        if a.only and mid != a.only:
            continue
        # `newline=""` DES DEUX COTES : sans lui, la lecture traduit les fins de ligne en `\n` et
        # la reecriture les rend en `\r\n` (Windows) -- le fichier RESTAURE differerait alors de
        # l'original sur TOUTES ses lignes, et `git status` sortirait sale apres chaque passe.
        src = path.read_text(encoding="utf-8", newline="")
        # ... et l'ANCRE doit alors parler la meme langue que le fichier, sinon elle devient
        # INTROUVABLE sur un checkout en CRLF -- un mutant non applique, donc un temoin muet.
        if "\r\n" in src:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        if old not in src:
            print("[931][%s] ANCRE INTROUVABLE dans %s -- mutant NON APPLIQUE (le temoin serait un "
                  "faux vert)" % (mid, path.name))
            anomalies.append((mid, "ancre introuvable"))
            continue
        attendu_inerte = mid in INERTES_ATTENDUS
        print("[931][%s] %s -> phase %s%s"
              % (mid, quoi, phase, "   [INERTE ATTENDU]" if attendu_inerte else ""))
        try:
            path.write_text(src.replace(old, new, 1), encoding="utf-8", newline="")
            rc = _run_phase(phase)
        finally:
            path.write_text(src, encoding="utf-8", newline="")
        mord = rc != 0
        print("[931][%s] rc=%d -> %s" % (mid, rc, "MORD" if mord else "INERTE"))
        if attendu_inerte:
            print("[931][%s]   CAUSE MESUREE : %s" % (mid, INERTES_ATTENDUS[mid]))
            if mord:
                anomalies.append((mid, "attendu INERTE mais il MORD -- la cause ecrite est perimee"))
        elif not mord:
            anomalies.append((mid, "phase %s reste verte" % phase))
    print()
    if not a.only or a.only == "M4":
        if not _demo_m4():
            anomalies.append(("M4-demo", "les deux ordres ne coincident plus -- M4 doit sortir "
                                         "d'INERTES_ATTENDUS et devenir exercable"))
    if anomalies:
        print("[931] ANOMALIES : %s" % ", ".join("%s (%s)" % (m, c) for m, c in anomalies))
    else:
        print("[931] OK -- chaque mutant MORD, sauf les %d INERTES ATTENDUS dont la cause est "
              "mesuree et re-verifiee." % len(INERTES_ATTENDUS))
    sys.exit(1 if anomalies else 0)


if __name__ == "__main__":
    main()
