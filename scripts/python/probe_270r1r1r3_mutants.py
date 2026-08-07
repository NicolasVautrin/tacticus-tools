"""#270-r1-r1-r3 -- MUTATION de la garde : chaque mutant doit la faire ROUGIR.

POURQUOI CE PROBE EXISTE. Une garde verte ne prouve rien : elle peut etre verte parce qu'elle ne
regarde rien. Le seul controle qui distingue les deux est la MUTATION -- casser exprès ce que la
garde pretend tenir, et verifier qu'elle le dit. Ce probe applique 20 mutations sur l'arbre REEL,
joue `test_270r1r1r3_role_enum_offline.py` apres chacune, puis restaure par `git checkout`.

⚠ UN MUTANT QUI RESTE VERT N'ACCUSE PAS FORCEMENT LA GARDE -- et la reponse n'est pas devinable,
elle se LIT. Mesure de la tranche : deux mutants sont d'abord restes verts, et les DEUX etaient
inoperants.
  * `W_HEAL = 100` apparait DANS LA DOCSTRING avant le code : `replace(..., 1)` mutait de la prose.
  * le mutant « mirror deplace » se contentait de renommer un titre de docstring -- il ne deplacait
    rien.
Refaits pour mordre reellement (mutation dans le CODE ; deplacement de fichier + reecriture des
imports), les deux sont detectes. D'ou la sortie : elle distingue MOTIF ABSENT (mutation non
appliquee) de VERT (mutation appliquee, garde muette) -- confondre les deux ferait accuser la
mauvaise piece.

⚠ CE PROBE ECRIT DANS L'ARBRE, puis restaure par `git checkout -- <chemin>`. Il refuse de demarrer
si l'arbre porte des modifications non commitees sur son perimetre : sinon la restauration les
DETRUIRAIT.

Usage :
    python probe_270r1r1r3_mutants.py            # les 20 mutants
    python probe_270r1r1r3_mutants.py --liste    # les enumere sans rien ecrire

Sortie ASCII stricte (console Windows cp1252). 100 % OFFLINE.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = REPO / "scripts" / "python"
ENGINE = PY / "engine"
TEST = "tests/engine/test_270r1r1r3_role_enum_offline.py"

# (libelle, chemin relatif AU DEPOT, motif, remplacement). Motif vide => APPEND.
# Le motif est choisi pour viser du CODE, jamais de la prose : c'est la faute qui a rendu deux
# mutants inoperants au premier passage.
MUTANTS: list[tuple[str, str, str, str]] = [
    ("M01 renumerotage d'un membre utilise (AbilityConstantType.range 22 -> 23)",
     "scripts/python/engine/entities/ability_constant_type.py",
     "    range = 22\n", "    range = 23\n"),
    ("M02 renumerotage d'un UnitFlag utilise (Overkilled 8 -> 10)",
     "scripts/python/engine/entities/unit_flag.py",
     "    Overkilled = 8\n", "    Overkilled = 10\n"),
    ("M03 retour a l'ordinal nu (orks.RAMMING_SPEED_CONST_RANGE)",
     "scripts/python/engine/runner/abilities/orks.py",
     "RAMMING_SPEED_CONST_RANGE = AbilityConstantType.range",
     "RAMMING_SPEED_CONST_RANGE = 0x16"),
    ("M04 retour a l'ordinal nu (components.OVERKILLED)",
     "scripts/python/engine/runner/components.py",
     "    OVERKILLED = UnitFlag.Overkilled", "    OVERKILLED = 8"),
    ("M05 confusion des deux index (AbilityConstantType.range -> AbilityVariableType.range)",
     "scripts/python/engine/runner/abilities/orks.py",
     "RAMMING_SPEED_CONST_RANGE = AbilityConstantType.range",
     "RAMMING_SPEED_CONST_RANGE = AbilityVariableType.range"),
    ("M06 membre SUPPRIME du mirror (UnitFlag.Removed)",
     "scripts/python/engine/entities/unit_flag.py", "    Removed = 26\n", ""),
    ("M07 membre RENOMME dans le mirror (EntityType.Machine -> Machin)",
     "scripts/python/engine/entities/entity_type.py",
     "    Machine = 6\n", "    Machin = 6\n"),
    ("M08 mirror RETIRE du registre probe_313 (AbilityVariableType)",
     "scripts/python/probe_313_enum_mirror_bijection.py",
     '    Mirror("AbilityVariableType", "engine/entities/ability_variable_type.py",\n'
     '           "IdunBattle.Configuration.AbilityVariableType"),\n', ""),
    ("M09 mirror mis EN DETTE au registre (garde=False)",
     "scripts/python/probe_313_enum_mirror_bijection.py",
     '    Mirror("UnitFlag", "engine/entities/unit_flag.py",\n'
     '           "IdunBattle.Entities.Enum.UnitFlag"),',
     '    Mirror("UnitFlag", "engine/entities/unit_flag.py",\n'
     '           "IdunBattle.Entities.Enum.UnitFlag", garde=False, dette=(0, 0, 0)),'),
    ("M10 cle du registre par nom COURT au lieu du nom PLEIN",
     "scripts/python/probe_313_enum_mirror_bijection.py",
     '"IdunBattle.Configuration.AbilityConstantType"),', '"AbilityConstantType"),'),
    ("M11 un SCALAIRE assume converti en membre d'enum (W_HEAL, dans le CODE)",
     "scripts/python/engine/utilities/heal.py",
     "\nW_HEAL = 100   #",
     "\nfrom ..entities.ability_constant_type import AbilityConstantType"
     "\nW_HEAL = AbilityConstantType.extraHits   #"),
    ("M12 un LECTEUR apparait pour la constante morte STAT_HEALTH",
     "scripts/python/engine/services/damage_prediction.py", "", "\n# mutant : STAT_HEALTH\n"),
    ("M13 UnitFlagsComponent.has rend toujours True",
     "scripts/python/engine/runner/components.py",
     "        return int(flag) in self.flags\n", "        return True\n"),
    ("M14 remove_turn_flags retire AUSSI Overkilled",
     "scripts/python/engine/runner/components.py",
     "        for f in (self.ACTIVE_ABILITY_USED, self.TURN_FINISHED, self.TURN_FINISHED_FORCED):",
     "        for f in (self.ACTIVE_ABILITY_USED, self.TURN_FINISHED, self.TURN_FINISHED_FORCED,\n"
     "                  self.OVERKILLED):"),
    ("M15 PERMUTATION de deux membres du mirror (minDmg <-> maxDmg)",
     "scripts/python/engine/entities/ability_variable_type.py",
     "    minDmg = 12\n    maxDmg = 13\n", "    maxDmg = 12\n    minDmg = 13\n"),
    ("M16 les deux index deviennent HOMONYMES sur un ordinal utilise (22)",
     "scripts/python/engine/entities/ability_variable_type.py",
     "    blockDmg_2 = 22\n", "    range = 22\n"),
    ("M17 le cycle d'import DISPARAIT (entities/abilities/__init__ ne tire plus active_ability)",
     "scripts/python/engine/entities/abilities/__init__.py",
     "from .active_ability import", "from .ability_configuration import"),
    ("M18 la table SITES est VIDEE (une garde qui ne garde plus rien)",
     "scripts/python/" + TEST, "\nSITES = {\n", "\nSITES = {}\n_SITES_MORT = {\n"),
    ("M19 ordinal FIGE aligne sur un mirror mute (AbilityConstantType.nrOfHits 47 -> 48)",
     "scripts/python/engine/entities/ability_constant_type.py",
     "    nrOfHits = 47\n", "    nrOfHits = 48\n"),
    # M20 n'est pas une substitution de texte : il DEPLACE le fichier et reecrit ses importateurs.
    ("M20 mirror REELLEMENT deplace sous entities/abilities/ (le cycle d'import revient)",
     "@@DEPLACEMENT@@", "", ""),
]


def _jouer() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header"],
                       cwd=str(PY), capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def _restaurer(rel: str) -> None:
    subprocess.run(["git", "-C", str(REPO), "checkout", "--", rel], check=True,
                   capture_output=True)


def _sale() -> list[str]:
    # `--no-optional-locks` (#474) : ce `status` est une LECTURE, mais git y prend quand meme
    # `.git/index.lock` de l'ARBRE PRINCIPAL a 0 octet pendant ~toute sa duree (5/5 mesures).
    # Ce module tourne sous budget, donc tuable dans cette fenetre -- un git TerminateProcess-e
    # ne nettoie rien, et c'est la commande SUIVANTE qui meurt sur le residu (20/20 mesures).
    r = subprocess.run(["git", "-C", str(REPO), "--no-optional-locks", "status", "--porcelain",
                        "scripts/python"], capture_output=True, text=True, check=True)
    return [l for l in r.stdout.splitlines() if l and not l.startswith("??")]


def _appliquer_deplacement() -> list[Path]:
    """M20 : deplace `ability_constant_type.py` sous `entities/abilities/` et reecrit les imports."""
    src = ENGINE / "entities" / "ability_constant_type.py"
    dst = ENGINE / "entities" / "abilities" / "ability_constant_type.py"
    shutil.copyfile(src, dst)
    src.unlink()
    touches = [dst]
    for f in PY.rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        if "entities.ability_constant_type" in t:
            f.write_text(t.replace("entities.ability_constant_type",
                                   "entities.abilities.ability_constant_type"), encoding="utf-8")
            touches.append(f)
    return touches


def main() -> int:
    ap = argparse.ArgumentParser(description="#270-r1-r1-r3 : mutation de la garde")
    ap.add_argument("--liste", action="store_true", help="enumere les mutants sans rien ecrire")
    a = ap.parse_args()

    if a.liste:
        for libelle, rel, _, _ in MUTANTS:
            print("  %-80s %s" % (libelle, rel))
        print("[270-r1-r1-r3] %d mutant(s)" % len(MUTANTS))
        return 0

    sale = _sale()
    if sale:
        print("[270-r1-r1-r3] REFUS : `scripts/python` porte des modifications non commitees.")
        print("   Ce probe restaure par `git checkout` -- il les DETRUIRAIT. Commite d'abord.")
        for l in sale[:10]:
            print("   " + l)
        return 2

    rc, sortie = _jouer()
    if rc != 0:
        print("[270-r1-r1-r3] BASE DEJA ROUGE -- rien de mesurable")
        print(sortie[-1500:])
        return 2
    print("[270-r1-r1-r3] BASE VERTE")
    print()

    muets: list[str] = []
    absents: list[str] = []
    for libelle, rel, avant, apres in MUTANTS:
        if rel == "@@DEPLACEMENT@@":
            touches = _appliquer_deplacement()
            try:
                rc2, out = _jouer()
            finally:
                (ENGINE / "entities" / "abilities" / "ability_constant_type.py").unlink(
                    missing_ok=True)
                _restaurer("scripts/python")
        else:
            f = REPO / rel
            src = f.read_text(encoding="utf-8")
            if avant and avant not in src:
                # MOTIF ABSENT != garde muette. Le dire separement est ce qui evite d'accuser la
                # garde pour une mutation qui n'a jamais eu lieu.
                print("  %-18s %s" % ("MOTIF ABSENT", libelle))
                absents.append(libelle)
                continue
            f.write_text(src.replace(avant, apres, 1) if avant else src + apres, encoding="utf-8")
            try:
                rc2, out = _jouer()
            finally:
                _restaurer(rel)
        echecs = [l.split("::")[-1].split(" ")[0] for l in out.splitlines()
                  if l.startswith("FAILED")]
        print("  %-18s %-78s %s" % ("ROUGE" if rc2 else "VERT (NON DETECTE)", libelle,
                                    "; ".join(echecs[:2])))
        if rc2 == 0:
            muets.append(libelle)

    print()
    if absents:
        print("[270-r1-r1-r3] %d mutation(s) NON APPLIQUEE(S) -- le motif a bouge, a re-cibler :"
              % len(absents))
        for m in absents:
            print("   " + m)
    if muets:
        print("[270-r1-r1-r3] VERDICT: FAIL -- %d mutant(s) NON DETECTE(S). Trancher : la garde "
              "est-elle trouee, ou le mutant inoperant ? (les deux sont deja arrives)" % len(muets))
        for m in muets:
            print("   " + m)
        return 1
    if absents:
        print("[270-r1-r1-r3] VERDICT: FAIL -- des mutations n'ont pas ete appliquees ; le vert "
              "des autres ne couvre pas ce qu'elles visaient.")
        return 1
    print("[270-r1-r1-r3] VERDICT: PASS -- %d/%d mutants DETECTES." % (len(MUTANTS), len(MUTANTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
