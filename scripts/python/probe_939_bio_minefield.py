"""#939 -- MESURE live de `1144 BioMinefield` (`tyranBiovore`, MoW du pool).

Ce probe REJOUE le montage qui a servi a confronter le port, et imprime ce que le NATIF fait. Il
ne garde rien (c'est le role de `tests/engine/runner/test_939_bio_minefield_offline.py`).

MONTAGE (celui de la mesure du 2026-08-11, board MC1_67, seed 777) :

    python rl_duel.py build --seed 777 --board MC1_67 --p-mow tyranBiovore \
        --p-units tyranParasite --a-units tyranParasite,tyranNeurothrope --state-file <ABSOLU>
    # 1144 sort en `[cd2 munitions1!MANQUE]` -> 3 x (act endturn + aiturn) fait tomber le cooldown
    python rl_duel.py act ability --caster <mow> --target <ennemi> --ability 1144 --state-file <...>

⚠ **LE MANQUE DE MUNITIONS N'EMPECHE PAS LE CAST, ET C'EST LU** : le terme munitions de
`ActiveAbility$$get_CanCurrentlyBeUsed` est DECISION-ONLY (`engine/runner/components.py` :
`SpendAmmoOperation$$Execute` echoue silencieusement a stock nul, et `MachineOfWarAmmo` vaut 0 dans
le seed BC). Un `act ability` force s'execute donc et pose tous ses effets. Sans cette lecture, le
montage paraitrait impossible.

MESURE OBTENUE (branche `else`, la seule que ce montage atteint -- cf. plus bas) :
  * **3 mines** `tyranSmnSporeMine` posees (`nrOfSummons_2 = 3`), `Unit_Parent_Id = <la MoW>`,
    `Unit_IsSummoned = 1`, `Unit_SpawnSource = 2`, `UnitStats_Movement = 1`, `Attack = 0` ;
  * leurs tuiles sont **adjacentes a la CIBLE**, pas au caster (une MoW n'a aucune tuile) --
    cible en (1,1), mines en (2,0), (0,0), (2,1) ;
  * **`BioMinefield_Target` sur la CIBLE**, `Effect_SourceId = <la MoW>`, `Effect_RemainingTurns = 1`
    -> l'`AddEffect(source = Owner, targets = Target, turns = <DSLFormulas+0x20> = Direct(1))` ;
  * les mines montent leur propre kit sous `Level = 50` / `VariableMultiplierPercentage = 150`,
    c'est-a-dire l'`AbilityState` du cast -- ce que le port rend par le DEFAUT de `Spawn`.

⚠ **LA BRANCHE `then` N'EST PAS ATTEIGNABLE PAR DEUX CASTS SUCCESSIFS, ET LA RAISON EST MESUREE.**
Un second cast au tour suivant a RE-SPAWNE (branche `else`) au lieu de deplacer/faire exploser. Ce
n'est PAS une divergence : entre les deux casts, les 3 mines avaient DISPARU. Elles jouent au
turn-start suivant par `PlayAutomaticUnitsOperation` (trait `Summon`, cf. #291) et, etant posees
ADJACENTES a la cible, elles explosent immediatement -- la cible est passee de 9927 a 6419 PV
(-3508) dans l'intervalle. Au moment du 2e cast, `Count(Alive(ChildrenOf(Owner)))` valait donc **0**,
et `0 >= nrOfSummons(3)` est FAUX. Le natif a pris la bonne branche.

Corollaire : **toute mine posee par 1144 est adjacente a un ennemi par construction**, donc meurt au
tour suivant. Le SEUL chemin vers la branche `then` est d'accumuler des mines qui SURVIVENT, via
`1145 SporeMineLauncher` (qui, elle, cible une TUILE libre quelconque) : **3 casts** de 1145 sur des
tuiles ELOIGNEES de tout ennemi -- elle n'en pose qu'UNE par cast (mesure) -- puis un cast de 1144.
Ce montage prend 4 tours de MoW ; la partie s'est terminee avant dans la session de mesure. Residu
`#939-r1`.

ASCII only. Ne prend AUCUN argument autre que `--state-file` (chemin ABSOLU, hors `data/`).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
ABILITY = 1144
SPORE_MINE = "tyranSmnSporeMine"


def _ascii(s: str) -> str:
    """Tout ce que ce probe RELAIE vient de `rl_duel view`, qui imprime des accents et des fleches.
    La console Windows est en cp1252 : un caractere non-ASCII y leve `UnicodeEncodeError` et fait
    CRASHER le probe -- un faux negatif qui masquerait la mesure. On translittere donc a la sortie,
    jamais a la lecture."""
    return s.encode("ascii", "replace").decode("ascii")


def _rl(args, state_file):
    cmd = [sys.executable, str(ICI / "rl_duel.py")] + args + ["--state-file", str(state_file)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(ICI), timeout=600)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU, hors data/ (cf. invariant 3 du CLAUDE.md)")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--tours", type=int, default=3,
                    help="cycles endturn+aiturn avant le cast (cooldown initial = 2)")
    ns = ap.parse_args()
    sf = Path(ns.state_file).resolve()
    if "data" in sf.parts[:-1] and sf.parts[-2] == "data":
        print("[939] REFUS : le state-file ne doit pas vivre sous data/")
        return 2

    r = _rl(["build", "--seed", ns.seed, "--board", ns.board,
             "--p-mow", "tyranBiovore", "--p-units", "tyranParasite",
             "--a-units", "tyranParasite,tyranNeurothrope"], sf)
    if r.returncode != 0:
        print("[939] build KO rc=%d" % r.returncode)
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        return 1
    etat = json.loads(sf.read_text(encoding="utf-8"))
    print("[939] runner %s seed %s board %s" % (etat.get("runnerId"), ns.seed, ns.board))

    for _ in range(ns.tours):                     # `initialCooldownTurns = 2`
        _rl(["act", "endturn"], sf)
        _rl(["aiturn"], sf)

    vue = _rl(["view"], sf).stdout
    mow = [l for l in vue.splitlines() if "tyranBiovore" in l]
    print(_ascii("[939] MoW avant cast : %s" % (mow[0].strip()[:160] if mow else "<absente>")))
    cible = None
    for ligne in vue.splitlines():
        if "ENNEMI" in ligne and "] u" not in ligne:
            for tok in ligne.split():
                if tok.startswith("u") and tok[1:].isdigit():
                    cible = tok[1:]
                    break
        if cible:
            break
    caster = None
    for ligne in vue.splitlines():
        if "tyranBiovore" in ligne:
            for tok in ligne.split():
                if tok.startswith("u") and tok[1:].isdigit():
                    caster = tok[1:]
                    break
    if caster is None or cible is None:
        print("[939] montage INCOMPLET (caster=%r cible=%r) -- rien mesure" % (caster, cible))
        _rl(["dispose"], sf)
        return 1

    r = _rl(["act", "ability", "--caster", caster, "--target", cible,
             "--ability", str(ABILITY)], sf)
    cascade = r.stdout
    spawns = cascade.count("Unit_IsSummoned=1")
    parents = set()
    for ligne in cascade.splitlines():
        if "Unit_Parent_Id=" in ligne:
            parents.add(ligne.split("Unit_Parent_Id=")[1].split()[0])
    print("[939] CAST %s u%s -> u%s" % (ABILITY, caster, cible))
    print("[939]   unites posees (Unit_IsSummoned=1) : %d   parents : %s"
          % (spawns, sorted(parents)))
    print("[939]   effet BioMinefield_Target dans la cascade : %s"
          % ("BioMinefield_Target" in cascade))
    for ligne in cascade.splitlines():
        if "Effect_RemainingTurns" in ligne and "Effect_SourceId" in ligne:
            print(_ascii("[939]   %s" % ligne.strip()[:150]))

    vue = _rl(["view"], sf).stdout
    mines = [l.strip() for l in vue.splitlines() if SPORE_MINE in l and "=" in l]
    print("[939] mines vivantes apres cast : %d" % len(mines))
    for m in mines[:6]:
        print(_ascii("[939]   %s" % m[:130]))
    for ligne in vue.splitlines():
        if "BioMinefield_Target" in ligne:
            print(_ascii("[939] effet sur la cible : %s" % ligne.strip()[:150]))

    _rl(["dispose"], sf)
    print("[939] runner dispose")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
