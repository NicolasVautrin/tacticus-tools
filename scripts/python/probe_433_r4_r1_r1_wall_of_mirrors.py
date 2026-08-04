"""probe #433-r4-r1-r1 -- ORACLE 1 BIT du gate de ciblage de `WallOfMirrors` (1186), LIVE.

CE QUI EST MESURE
-----------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.WallOfMirrorsAbility$$GetDynamicInvalidTargetReason`
n'a que DEUX conjoints, et il rend un BIT :

    valide(cible)  <=>  cible porte Markerlight (0x462)  ET  GetPossibleTiles() est non vide

Le RPC `abilityTargets` expose exactement cette reponse pour (unite, ability) -- sans dependre
d'aucune prediction de degat. On confronte donc la face DECISION seule, `cible par cible`, contre
`engine.runner.abilities.loki.WallOfMirrorsAbility.get_dynamic_invalid_target_reason`.

MONTAGE (board MC1_67) -- calque sur `probe_27_4c_forwardobservers_ab.py`, meme verrou et meme parade
--------------------------------------------------------------------------------------------------
PORTEUR. Les deux porteurs de 1186 sont `tauSmnStealthSuit` (summon SANS invocateur : il n'est cite
que par `units.abilities.ATemptingTrap.constants.unitId`, et AUCUNE unite du gameconfig ne porte
`ATemptingTrap`) et `tauNpc5StealthSuit` (npc) ; `buildNormalizedBC` les REFUSE tous les deux. On
GREFFE donc 1186 sur `tauCrisis` (T'au, pool, arme Pulse portee 2). C'est licite ici parce que le
natif charge le playbook PAR ABILITY (`WallOfMirrorsPlaybook$$.ctor` = `ComparablePlaybook(0x4a2)`),
que `GetUseProbability` est la CONSTANTE `Fix64(75/100)`, et que ni le gate ni `GetPossibleTiles` ne
lisent une stat ou un trait du caster.

MARKERLIGHT par voie NATURELLE : `tauDarkstrider` porte le passif `StructuralAnalyser`, dont
`...StructuralAnalyser_AddMarkerlightAbility$$CreateTrigger` = `On(0xa) & IsRangedAttack &
OwnerIsCaster` -> son tir RANGED pose 0x462 sur SA cible. Une seule des deux cibles est marquee : le
bit doit donc DIFFERER entre les deux, dans le MEME etat. C'est ce qui rend la mesure discriminante
(un accord sur deux « non » ne prouverait rien).

Usage (depuis scripts/python, ASCII only) :
    python probe_433_r4_r1_r1_wall_of_mirrors.py --build
    python probe_433_r4_r1_r1_wall_of_mirrors.py            # re-joue sur le runner du state-file
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_wom_graft.json"
STATE = LOGS / "rs_wom_433r4r1r1.json"
BOARD = "MC1_67"
SEED = 909

WALL_OF_MIRRORS = int(ActiveAbilityType.WallOfMirrors)      # 1186
MARKERLIGHT = int(EffectType.Markerlight)                   # 0x462 = 1122

GRAFT_ON = "tauCrisis"                 # porteur GREFFE de 1186
P_UNITS = "tauCrisis,tauMarksman"
A_UNITS = "orksWarboss,necroWarden"

CASTER_VID = "tauCrisis"               # porte 1186 apres greffe
MARKER_VID = "tauMarksman"             # son attaque NORMALE (1076) pose Markerlight sur SA cible
TGT_MARK_VID = "orksWarboss"           # sera MARQUE
TGT_PLAIN_VID = "necroWarden"          # restera NON marque

CASTER_TILE = "2,6"
MARKER_TILE = "5,2"                    # portee du drone MV71 = 4 -> atteint TGT_MARK
TGT_MARK_TILE = "2,4"
TGT_PLAIN_TILE = "2,8"
NORMAL_ATTACK = 1076                   # `MV71SniperDroneSquadAttack` = l'attaque NORMALE de Sho'syl


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row), hp, [effectType...])} -- aucun id hardcode."""
    out = {}
    for u in (_dv(rid).get("units") or []):
        p = u.get("pos") or {}
        effs = [e.get("effectType") for e in (u.get("effects") or []) if isinstance(e, dict)]
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")), u.get("hp"), effs)
    return out


def write_graft_seed_bc() -> None:
    """Copie du seed BC PARTAGE avec `ActiveAbilities` de `GRAFT_ON` remplace par `[1186]`.
    N'ECRIT JAMAIS le seed BC partage (meme discipline que `catalog_inject --out`)."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [WALL_OF_MIRRORS]
            n += 1
    if n != 1:
        raise SystemExit("greffe impossible : %d entree(s) %r dans BC.Units" % (n, GRAFT_ON))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")
    print("[graft] %s.ActiveAbilities = [%d] -> %s" % (GRAFT_ON, WALL_OF_MIRRORS, SEED_BC))


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien -- sans cette garde les deux bras degenerent en UN seul
    etat et l'accord devient trivial."""
    pos = {i: p for _v, (i, p, _h, _e) in _units(rid).items()}
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def build(hp_target: int = 0, armor_target: int = 0) -> int:
    """`hp_target > 0` gonfle les PV des cibles : indispensable pour SORTIR du regime degenere ou
    les deux moteurs tuent la cible et ou l'accord `hp == 0` ne discrimine RIEN sur le montant.
    `armor_target > 0` donne de l'ARMURE a la cible -- sans elle, le canal PERCAGE de l'effet 0x576
    est INERTE (mesure : delta identique avec et sans le bonus), donc l'accord ne le testerait pas."""
    write_graft_seed_bc()
    extra = ["--hp-target", str(hp_target)] if hp_target else []
    if armor_target:
        extra += ["--armor-target", str(armor_target)]
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
          "--state-file", str(STATE)] + extra)
    rid = _runner_id()
    ids = {v: i for v, (i, _p, _h, _e) in _units(rid).items()}
    want = ((ids[CASTER_VID], CASTER_TILE), (ids[MARKER_VID], MARKER_TILE),
            (ids[TGT_MARK_VID], TGT_MARK_TILE), (ids[TGT_PLAIN_VID], TGT_PLAIN_TILE))
    for unit, to in want:
        _move(rid, unit, to)
    _assert_placed(rid, want)
    return rid


def ensure_my_turn(rid: int) -> None:
    """Le seed peut ouvrir sur le tour ADVERSE : `aiturn` le joue jusqu'a ce que le controle
    revienne. Sans ca, l'`act ability` du marqueur part sur la mauvaise equipe et rend un no-op."""
    for _ in range(3):
        dv = _dv(rid)
        act = dv.get("toActivate") or []
        mine = {u.get("id") for u in (dv.get("units") or []) if u.get("ctrl")}
        if act and set(act) & mine and {v[0] for k, v in _units(rid).items()
                                        if k in (CASTER_VID, MARKER_VID)} & mine:
            return
        _run(["aiturn", "--state-file", str(STATE), "--runner", str(rid)])


def mark(rid: int) -> list:
    """`tauMarksman` lance son attaque NORMALE (1076) sur `TGT_MARK` : le bloc (e) de
    `MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` pose `Markerlight` (0x462) sur la CIBLE.
    Rend la liste des (id, visualId) qui portent Markerlight APRES le tir."""
    ids = {v: i for v, (i, _p, _h, _e) in _units(rid).items()}
    _run(["act", "ability", "--caster", str(ids[MARKER_VID]), "--ability", str(NORMAL_ATTACK),
          "--target", str(ids[TGT_MARK_VID]), "--state-file", str(STATE), "--runner", str(rid)])
    return [(i, v) for v, (i, _p, _h, effs) in _units(rid).items() if MARKERLIGHT in effs]


def native_reason(rid: int, caster_id: int, target_id: int) -> int:
    """ORACLE 1 BIT — `abilityReason` traverse la cascade de ciblage NATIVE pour (caster, 1186,
    cible) et rend le masque `TargetingRule` ROMPU. Le `targetReason` vaut donc `0x0` quand la cible
    est legale, et `0x2 TargetMatchesDynamicRule` quand seul le predicat DYNAMIQUE la refuse.

    ⚠ `abilityTargets` ne convient PAS ici : il n'enumere que les unites ACTIVABLES du tour courant
    (mesure : `unitCount = 0` pour un caster hors `toActivate`), donc son zero serait un zero de
    HARNAIS, pas une mesure du gate."""
    r = L._rpc("abilityReason", [{"runnerId": rid, "casterId": caster_id,
                                 "abilityType": WALL_OF_MIRRORS, "targetId": target_id}])
    return int((r.get("targetReason") or {}).get("hex") or "0x0", 16)


def main() -> int:
    if "--build" in sys.argv:
        rid = build()
        ensure_my_turn(rid)
        holders = mark(rid)
        print("[markerlight] porteurs apres le tir : %s" % holders)
    else:
        rid = _runner_id()
    units = _units(rid)
    caster_id = units[CASTER_VID][0]
    marked = {v for v, (_i, _p, _h, effs) in units.items() if MARKERLIGHT in effs}
    print("[etat] runner=%d caster=%s marquees=%s" % (rid, caster_id, sorted(marked)))
    for vid in (TGT_MARK_VID, TGT_PLAIN_VID):
        tid = units[vid][0]
        print("  %-16s id=%-4s markerlight=%-5s natif_targetReason=0x%x"
              % (vid, tid, vid in marked, native_reason(rid, caster_id, tid)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
