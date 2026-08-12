"""#969 -- le garde offline MORD-il ? Chaque mutation doit faire ROUGIR le fichier de test.

Un fichier de test vert au PREMIER passage ne prouve rien -- et celui de #969 l'a ete, 30/30, du
premier coup. #957 en a livre deux qui etaient MUETS (temoins degeneres) et quatre contre-epreuves
qui n'avaient pas mordu ; #967 a livre cette sonde-ci pour la meme raison. Le seul controle qui
tranche est la MUTATION : on casse volontairement UN terme du port, on rejoue le garde, et on
exige `rc != 0`. Une mutation qui laisse VERT designe un terme que rien ne tient.

Les mutations sont textuelles, appliquees EN PLACE, avec restauration systematique (`finally`) ET
verification que le fichier est bien revenu a son octet d'origine. Elles portent une par une sur
les termes que le decompile impose :

    1049 : MIN_UTILITY 1 -> 2               le seuil du `.cctor`
    1049 : rayon lu -> constante 1          `GetNumberConstant(0x16)` cesse d'etre LU
    1049 : includeCenter 0 -> 1             la tuile centrale entre dans le compte
    1049 : gate `maxBuffed > 0` -> True     le ZERO deterministe de GetUseProbability disparait
    1049 : cible CASTER -> 1re du selecteur le self-cast devient un cast sur autrui
    1228 : bonus 10 -> 0                    le seul terme qui departage les positions disparait
    1228 : faction DarkAngels -> tout ami   `HasFaction(u, 10)` cesse d'etre lu
    1228 : ordre du selecteur -> trie       l'argmax redevient decide par la VALEUR de l'id
    1228 : gate slot 4 ajoute               la symetrie fautive (1228 n'a PAS de zero)
    1003 : utilite -> constante 1           le compte de tuiles cesse de classer les cibles
    1003 : tuiles occupees ignorees         `CanAddUnit` cesse de retirer l'occupation
    1003 : gate slot 4 -> True              `GetBestTarget`/`GetNumSummons` cessent de refuser
    1203 : gate WillNormalAttackKill retire le SEUL discriminant de 1203 disparait
    1203 : PV -> constante                  l'utilite cesse de classer par les PV
    1106 : gate -> True                     le ZERO deterministe (aucune cible) disparait
    1106 : union `targets` -> `fromHere`    le slot 69 confondu avec la vue par position
    registre : 1049 retiree de PLAYBOOKS    l'ability redevient invisible du moteur

Usage : `python probe_969_morsure.py` (rc 0 = toutes les mutations mordent).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
NC = RACINE / "engine" / "playbook" / "noncomparable"
TEST = "tests/engine/playbook/test_969_effect_buff_decision_faces_offline.py"

COW = NC / "crusade_of_wrath.py"
STERN = NC / "sternguard_focus.py"
DFA = NC / "death_from_above.py"
PATRONS = NC / "daemonic_patrons.py"
HOWL = NC / "war_howl.py"
INIT = NC / "__init__.py"

#: (libelle, fichier, texte AVANT, texte APRES)
MUTATIONS = [
    # ---------------------------------------------------------------- 1049 CrusadeOfWrath
    # ⚠ AUCUN `\n` dans les ancrages : la lecture est BRUTE, donc un fichier a fins de ligne
    # CRLF ne contient PAS `...1.0\n`. Un ancrage qui ne matche plus rend la mutation NON JOUEE
    # -- une sonde qui ne mord pas parce qu'elle a rate sa cible est pire qu'une sonde absente.
    ("1049 : MIN_UTILITY 1 -> 2", COW,
     "    MIN_UTILITY = 1.0",
     "    MIN_UTILITY = 2.0"),
    ("1049 : rayon LU -> constante 1", COW,
     "    consts = ((_gc.ability(_ABILITY_NAME) or {}).get(\"constants\") or {})",
     "    return 1   # MUTATION\n"
     "    consts = ((_gc.ability(_ABILITY_NAME) or {}).get(\"constants\") or {})"),
    ("1049 : includeCenter 0 -> 1", COW,
     "            if 1 <= d <= radius:                     # includeCenter = 0 -> `d >= 1`",
     "            if 0 <= d <= radius:                     # MUTATION"),
    ("1049 : gate `maxBuffed > 0` -> True", COW,
     "        return self._max_friendly_units_buffed(ctx) > 0",
     "        return True   # MUTATION"),
    ("1049 : cible CASTER -> constante etrangere", COW,
     "        return [{\"target\": ctx.uid, \"ability\": self.ABILITY_ID,",
     "        return [{\"target\": -1, \"ability\": self.ABILITY_ID,   # MUTATION"),
    # ---------------------------------------------------------------- 1228 SternguardFocus
    ("1228 : bonus 10 -> 0", STERN,
     "    _ADJACENT_DARK_ANGEL_BONUS = 10.0",
     "    _ADJACENT_DARK_ANGEL_BONUS = 0.0   # MUTATION"),
    ("1228 : faction DarkAngels -> tout ami", STERN,
     "            if AUP._unit_faction({\"vis\": vis}) == UnitFaction.DarkAngels.name:",
     "            if True:   # MUTATION"),
    ("1228 : ordre du selecteur -> trie par id", STERN,
     "        premiere = cibles[0][0]                        # keep-first a utilite egale",
     "        premiere = sorted(c[0] for c in cibles)[-1]    # MUTATION"),
    ("1228 : gate slot 4 ajoute (symetrie fautive)", STERN,
     "    def _visual_by_pos(ctx: NCContext) -> dict:",
     "    def should_evaluate(self, ctx) -> bool:   # MUTATION\n"
     "        return bool(ctx.fpos)\n"
     "\n"
     "    @staticmethod\n"
     "    def _visual_by_pos(ctx: NCContext) -> dict:"),
    # ---------------------------------------------------------------- 1003 DeathFromAbove
    ("1003 : utilite -> constante 1", DFA,
     "            util = float(self._spawn_tiles(ctx, tuple(pos)))",
     "            util = 1.0   # MUTATION"),
    ("1003 : tuiles occupees ignorees", DFA,
     "        occupied = set(ctx.epos or ()) | set(ctx.fpos or ())",
     "        occupied = set()   # MUTATION"),
    ("1003 : gate slot 4 -> True", DFA,
     "        if best is not None and best < 1:",
     "        if False:   # MUTATION"),
    # ---------------------------------------------------------------- 1203 DaemonicPatrons
    ("1203 : gate WillNormalAttackKill retire", PATRONS,
     "        if _will_normal_attack_kill(ctx, target, tile):",
     "        if False:   # MUTATION"),
    ("1203 : PV -> constante", PATRONS,
     "        return float(hp) if hp and hp > 0 else None",
     "        return 1.0 if hp and hp > 0 else None   # MUTATION"),
    # ---------------------------------------------------------------- 1106 WarHowl
    ("1106 : gate `aucune cible` -> True", HOWL,
     "        return True if v is None else v",
     "        return True   # MUTATION"),
    ("1106 : union `targets` -> `fromHere`", HOWL,
     "                    if a.get(\"abilityId\") == na and (a.get(\"targets\") or []):",
     "                    if a.get(\"abilityId\") == na and (a.get(\"fromHere\") or []):"),
    # ---------------------------------------------------------------- le REGISTRE
    ("registre : 1049 retiree de PLAYBOOKS", INIT,
     "        CrusadeOfWrathPlaybook(),       # 1049",
     "        # MUTATION -- CrusadeOfWrathPlaybook(),       # 1049"),
]


def _lire(chemin: Path) -> str:
    """Lecture SANS traduction de fin de ligne (`newline=""`).

    ⚠ `Path.read_text` / `Path.write_text` traduisent : sous Windows, `write_text` convertit
    chaque `\\n` en `\\r\\n`. Une sonde qui lit puis reecrit le MEME texte laisse donc le fichier
    CONVERTI EN CRLF -- l'arbre est sali, `git status` le voit, et l'assertion de restauration ne
    l'attrape PAS (la relecture retraduit dans l'autre sens, donc les deux chaines sont egales).
    Mesure : les deux premiers fichiers mutes par cette sonde sont ressortis modifies. On lit et on
    ecrit donc en mode BRUT, des deux cotes."""
    with open(chemin, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _ecrire(chemin: Path, texte: str) -> None:
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write(texte)


def _eol(texte: str) -> str:
    """Le separateur de ligne REELLEMENT present dans le fichier, DERIVE et non presume.

    Les ancrages ci-dessus sont ecrits en `\\n` ; l'arbre, lui, peut etre en CRLF (c'est le cas
    sous Windows, `core.autocrlf`) ou en LF (une CI Linux). Coder l'un des deux en dur ferait
    manquer la cible sur l'autre -- et une mutation NON JOUEE se lit comme un terme << tenu >>."""
    return "\r\n" if "\r\n" in texte else "\n"


def _jouer() -> int:
    return subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-x"],
                          cwd=RACINE, capture_output=True, text=True).returncode


def main() -> int:
    # 0. le garde doit etre VERT avant toute mutation, sinon la sonde ne mesure rien.
    if _jouer() != 0:
        print("[969] ECHEC : le garde est DEJA rouge sans mutation -- rien n'est mesurable")
        return 2

    muettes = []
    for libelle, chemin, avant_lf, apres_lf in MUTATIONS:
        origine = _lire(chemin)
        eol = _eol(origine)
        avant = avant_lf.replace("\n", eol)
        apres = apres_lf.replace("\n", eol)
        if avant not in origine:
            print(f"[969] ANCRAGE PERDU : {libelle}")
            print(f"       le texte attendu n'est plus dans {chemin.name} -- mutation NON JOUEE")
            muettes.append(libelle + " (ancrage perdu)")
            continue
        try:
            _ecrire(chemin, origine.replace(avant, apres, 1))
            rc = _jouer()
        finally:
            _ecrire(chemin, origine)
            # La restauration est VERIFIEE, et en mode BRUT : une sonde qui laisse le port mute
            # -- ou seulement re-encode ses fins de ligne -- empoisonne tout ce qui suit, y
            # compris les mesures des autres agents.
            assert _lire(chemin) == origine, f"RESTAURATION RATEE {chemin}"
        etat = "MORD" if rc != 0 else "MUETTE"
        print(f"[969] {etat:7s} {libelle}")
        if rc == 0:
            muettes.append(libelle)

    print(f"[969] {len(MUTATIONS) - len(muettes)}/{len(MUTATIONS)} mutations mordent")
    if muettes:
        print("[969] MUTATIONS MUETTES -- ces termes ne sont tenus par RIEN :")
        for m in muettes:
            print(f"       - {m}")
        return 1
    # Controle final : apres restauration, le garde doit etre VERT a nouveau.
    if _jouer() != 0:
        print("[969] ECHEC : le garde est rouge APRES restauration -- un fichier est reste mute")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
