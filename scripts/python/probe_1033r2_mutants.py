"""CONTRE-EPREUVE du cliquet `#1033-r2` : chaque mutant DOIT faire rougir le test.

Un cliquet vert ne prouve rien tant qu'on n'a pas montre qu'il rougit sur la faute qu'il pretend
interdire. HUIT mutants, un par etage garde -- et chacun est la faute PLAUSIBLE, celle qu'un
relecteur presse ecrirait, pas une absurdite :

  M1  1107 sort du registre `PLAYBOOKS`                       -> etage 1 (et 3, 4, 5, 6, 7)
      (l'etat d'AVANT cette tranche : la face DECISION retombe sur le chemin generique)
  M2  l'utilite devient `float(hp)` -- le voisin de forme     -> etage 2
      (`VexillaMagnifica`/`EuphoricStrikes`/`DaemonicPatrons` ont EXACTEMENT ce squelette et
       cette `MIN_UTILITY` ; recopier leur utilite est la faute la plus tentante du lot)
  M3  `MIN_UTILITY` passe a 1.5 (borne lue en `>` strict)     -> etage 3
      (le MORT SILENCIEUX : 0 candidat, 0 erreur -- exactement `IronkinSteeljack` avant #971)
  M4  le gate `WillNormalAttackKill` est retire               -> etage 4
  M5  le gate est INVERSE (on ne garde QUE les sure-kill)     -> etage 4
      (le contresens que le nom du gate invite a commettre)
  M6  le gate cesse d'etre POSITIONNEL (teste depuis l'origine) -> etage 5
      (`tile` remplace par `ctx.origin` : plausible, et faux des que le caster bouge)
  M7  `should_evaluate` est surcharge par un gate invente     -> etage 6
      (la faute symetrique de #46 : inventer un slot 4 que la metadata dit ABSENT)
  M8  la ligne de dette 1107 revient dans `probe_1021.DETTE`  -> etage 8
      (une face portee re-protegee par sa VIEILLE ligne, donc soustraite au CRAN A)

Sortie ASCII (cp1252). Chaque fichier mute est RESTAURE dans un `finally`.

Usage:
    python probe_1033r2_mutants.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
CIBLE = os.path.join("tests", "engine", "playbook", "test_1033r2_reveal_decision_offline.py")

REVEAL = os.path.join("engine", "playbook", "noncomparable", "reveal.py")
INIT = os.path.join("engine", "playbook", "noncomparable", "__init__.py")
P1021 = "probe_1021_face_decision_au_registre.py"

MUTANTS = (
    ("M1 1107 sort du registre PLAYBOOKS", INIT,
     "        RevealPlaybook(),               # 1107",
     "        # RevealPlaybook(),             # 1107"),

    ("M2 l'utilite devient float(hp) (le voisin de forme)", REVEAL,
     "        return 1.0                         # `FixMath.NET.Fix64$$op_Implicit(1)`",
     "        return float(ctx.hp_cur_by_id.get(target) or 0)  # MUTANT"),

    ("M3 MIN_UTILITY passe a 1.5 (borne lue en > strict)", REVEAL,
     "    MIN_UTILITY = 1.0   # `...RevealPlaybook$$.cctor`",
     "    MIN_UTILITY = 1.5   # MUTANT"),

    ("M4 le gate WillNormalAttackKill est retire", REVEAL,
     "        if _will_normal_attack_kill(ctx, target, tile):\n"
     "            return None                    # `continue` natif",
     "        if False:\n"
     "            return None                    # MUTANT"),

    ("M5 le gate est INVERSE (on ne garde QUE les sure-kill)", REVEAL,
     "        if _will_normal_attack_kill(ctx, target, tile):",
     "        if not _will_normal_attack_kill(ctx, target, tile):"),

    ("M6 le gate cesse d'etre POSITIONNEL", REVEAL,
     "        if _will_normal_attack_kill(ctx, target, tile):",
     "        if _will_normal_attack_kill(ctx, target, ctx.origin):"),

    ("M7 should_evaluate est surcharge par un gate invente", REVEAL,
     "    def evaluate_non_comparable(self, tile, target, ctx: NCContext):",
     "    def should_evaluate(self, ctx: NCContext) -> bool:\n"
     "        return False        # MUTANT\n\n"
     "    def evaluate_non_comparable(self, tile, target, ctx: NCContext):"),

    ("M8 la ligne de dette 1107 revient dans probe_1021.DETTE", P1021,
     "    # 1107 `Reveal` -- TRANCHE par #1033-r2, ligne RETIREE",
     "    1107: (\"SANS_VERDICT\", \"MUTANT\"),\n"
     "    # 1107 `Reveal` -- TRANCHE par #1033-r2, ligne RETIREE"),
)


def _jouer():
    r = subprocess.run([sys.executable, "-m", "pytest", CIBLE, "-q", "-p", "no:randomly"],
                       cwd=ICI, capture_output=True, text=True)
    return r.returncode


def main():
    base = _jouer()
    print("BASE (aucun mutant) : rc=%d  %s" % (base, "OK" if base == 0 else "KO -- ARRET"))
    if base != 0:
        return 1

    inertes = []
    for libelle, rel, avant, apres in MUTANTS:
        chemin = os.path.join(ICI, rel)
        with open(chemin, "r", encoding="utf-8") as fh:
            src = fh.read()
        if avant not in src:
            print("%-58s MUTATION NON APPLIQUEE (motif absent)" % libelle)
            inertes.append(libelle + " [motif absent -- le mutant ne teste RIEN]")
            continue
        try:
            with open(chemin, "w", encoding="utf-8") as fh:
                fh.write(src.replace(avant, apres, 1))
            rc = _jouer()
        finally:
            with open(chemin, "w", encoding="utf-8") as fh:
                fh.write(src)
        print("%-58s rc=%d  %s" % (libelle, rc, "MORD" if rc != 0 else "INERTE"))
        if rc == 0:
            inertes.append(libelle)

    apres_base = _jouer()
    print("RESTAURATION : rc=%d  %s" % (apres_base, "OK" if apres_base == 0 else "KO"))
    if inertes:
        print("\nMUTANTS INERTES (%d) -- le cliquet ne garde PAS ce qu'il pretend :" % len(inertes))
        for m in inertes:
            print("  " + m)
        return 1
    if apres_base != 0:
        return 1
    print("\nOK : %d/%d mutants mordent." % (len(MUTANTS), len(MUTANTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
