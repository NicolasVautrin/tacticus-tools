"""#893 -- BANC DE MUTANTS de `1049 CrusadeOfWrath` : est-ce que le confront MORD ?

Un jeu de tests devient INERTE en silence (un selecteur renomme, une assertion qui ne porte plus
sur ce qu'elle croit). Ce banc l'etablit MECANIQUEMENT : pour chaque mutation du PORT, il exige
`rc != 0`, et il exige `rc == 0` sur l'arbre RESTAURE -- avant ET apres, parce qu'un banc qui ne
verifie pas sa restauration peut rendre tous ses mutants << mordants >> sur un arbre casse.

Chaque mutant nomme la FAUTE qu'il simule, pas le texte qu'il remplace.

Usage :
    python probe_893_mutants.py --volet offline      # rapide, aucun runner
    python probe_893_mutants.py --volet live         # monte 2 runners par mutant
    python probe_893_mutants.py --volet live --mutants STAT_INVERSE,PORTEE_1
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CIBLE = HERE / "engine" / "runner" / "abilities" / "blacktemplars.py"
HANDLER = HERE / "engine" / "runner" / "abilities" / "handler.py"
TEST = "tests/engine/runner/test_893_crusade_of_wrath_live.py"

#: L'ancre des trois mutants de `_params`. Elle est prise sur DEUX lignes parce que chacune, prise
#: seule, matche AUSSI le `_params` du voisin `UnbreakableDutyAbility` (meme module, meme forme) --
#: mesure du banc a sa premiere passe : trois mutants INERTES, signales comme tels plutot que
#: comptes verts. C'est exactement le vice que ce banc existe pour montrer.
ANCRE_PARAMS = ('        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1\n'
                '        extra_dmg = ability_var(self.ABILITY_ID, "extraDmg", level, '
                'multiplier_pct=mult) or 0')

#: `(nom, volets, fichier, ancien, nouveau, faute simulee)`. `ancien` doit etre UNIQUE dans le
#: fichier -- le banc le verifie et refuse sinon (une mutation qui ne matche pas est un mutant
#: INERTE, donc un faux vert du banc lui-meme). `volets` = la ou le mutant DOIT mordre : les trois
#: mutants de `_params` ne sont visibles QUE live (les bras offline derivent leurs valeurs du
#: gameconfig nu, pas de `_params`).
MUTANTS = [
    ("STAT_INVERSE", ("offline", "live"), CIBLE,
     "dmg = AddStaticStatModifierEffect(buffed, CRUSADE_OF_WRATH_EXTRA_DAMAGE, int(StatType.ATTACK),",
     "dmg = AddStaticStatModifierEffect(buffed, CRUSADE_OF_WRATH_EXTRA_DAMAGE, int(StatType.EXTRA_PIERCE_MELEE),",
     "[A] ecrit sur ExtraPierceMelee au lieu d'Attack (statType 0 -> 0x15)"),
    ("CLES_INVERSEES", ("live",), CIBLE, ANCRE_PARAMS,
     ANCRE_PARAMS.replace('"extraDmg", level, multiplier_pct=mult',
                          '"extraPierceRatio", level, multiplier_pct=mult'),
     "GetVariableForLevel(8) lu comme (0x3f) -- la confusion SILENCIEUSE en ordinal"),
    ("MULTIPLIER_OUBLIE", ("live",), CIBLE, ANCRE_PARAMS,
     ANCRE_PARAMS.replace(', multiplier_pct=mult) or 0', ') or 0'),
     "AbilityVariablesMultiplierPercentage ignore -> 277 au lieu de 499"),
    ("DUREE_1_ROUND", ("offline", "live"), CIBLE,
     "CRUSADE_OF_WRATH_BUFF_ROUNDS = 2",
     "CRUSADE_OF_WRATH_BUFF_ROUNDS = 1",
     "TurnsFromRounds(2) lu comme (1) -- << this round >> au lieu de << and the next >>"),
    ("CASTER_INCLUS", ("offline", "live"), CIBLE,
     "    autour = SurroundingUnits(CasterTile(), Const(int(range_val)), selection_type=SELECTION)\n"
     "    return Friends(Sub(autour, Caster()), reference=Owner(), selection_type=SELECTION)",
     "    autour = SurroundingUnits(CasterTile(), Const(int(range_val)), include_center=True,\n"
     "                              selection_type=SELECTION)\n"
     "    return Friends(autour, reference=Owner(), selection_type=SELECTION)",
     "les DEUX exclusions du caster retirees (includeCenter=1 ET op_Subtraction absent)"),
    ("EQUIPE_IGNOREE", ("offline", "live"), CIBLE,
     "    return Friends(Sub(autour, Caster()), reference=Owner(), selection_type=SELECTION)",
     "    return Sub(autour, Caster())",
     "le `Friends(of = Owner)` retire -> les ENNEMIS a portee sont buffes aussi"),
    ("ATTAQUE_ABSENTE", ("offline", "live"), CIBLE,
     "    return op_and(dmg, op_add(pierce, free))",
     "    return op_and(dmg, pierce)",
     "le volet [C] (attaque normale gratuite) tombe de l'arbre"),
    ("PORTEE_1", ("live",), CIBLE, ANCRE_PARAMS,
     ANCRE_PARAMS.replace('rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1',
                          "rng_range = 1"),
     "GetNumberConstant(0x16 range) = 2 lu comme 1 -> l'allie a distance 2 n'est plus buffe"),
    ("REGISTRE_ABSENT", ("offline", "live"), HANDLER,
     "    CrusadeOfWrathAbility.ABILITY_TYPE: CrusadeOfWrathAbility,",
     "    # MUTANT : CrusadeOfWrathAbility.ABILITY_TYPE: CrusadeOfWrathAbility,",
     "1049 hors d'ABILITY_CLASSES -- le NO-OP SILENCIEUX que la tranche ferme"),
]


def _pytest(volet: str) -> int:
    cmd = [sys.executable, "-m", "pytest", TEST, "-q", "-x"]
    if volet != "tout":
        cmd += ["-k", volet]
    return subprocess.run(cmd, cwd=str(HERE), check=False,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="#893 : banc de mutants")
    ap.add_argument("--volet", default="offline", choices=("offline", "live", "tout"))
    ap.add_argument("--mutants", default=None, help="liste separee par des virgules")
    a = ap.parse_args()
    voulus = set(a.mutants.split(",")) if a.mutants else None

    print("[893] RESTAURATION AVANT -- volet=%s" % a.volet)
    rc = _pytest(a.volet)
    if rc != 0:
        print("[893] PAS MESURE : l'arbre RESTAURE est deja ROUGE (rc=%d)" % rc)
        return 2
    print("[893] arbre restaure : rc=0 OK")

    echecs = []
    for nom, volets, fichier, ancien, nouveau, faute in MUTANTS:
        if voulus is not None and nom not in voulus:
            continue
        if a.volet != "tout" and a.volet not in volets:
            print("[893] %-18s HORS VOLET (mord en %r) | %s" % (nom, list(volets), faute))
            continue
        src = fichier.read_text(encoding="utf-8")
        if src.count(ancien) != 1:
            print("[893] %-18s MUTANT INERTE : le motif matche %d fois dans %s"
                  % (nom, src.count(ancien), fichier.name))
            echecs.append(nom)
            continue
        fichier.write_text(src.replace(ancien, nouveau), encoding="utf-8")
        try:
            rc = _pytest(a.volet)
        finally:
            fichier.write_text(src, encoding="utf-8")
        mord = rc != 0
        print("[893] %-18s rc=%-3d %s | %s" % (nom, rc, "MORD" if mord else "N'A PAS MORDU", faute))
        if not mord:
            echecs.append(nom)

    print("[893] RESTAURATION APRES")
    rc = _pytest(a.volet)
    if rc != 0:
        print("[893] ECHEC : l'arbre n'est pas revenu vert (rc=%d)" % rc)
        return 2
    if echecs:
        print("[893] MUTANTS QUI N'ONT PAS MORDU : %r" % (echecs,))
        return 1
    print("[893] OK -- tous les mutants joues ont mordu, et l'arbre restaure est vert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
