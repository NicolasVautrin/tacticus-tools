"""GATE NO-MOVE de `HeavyWeapon_ExtraDmg` (effet 1008, trait HeavyWeapon) confronte au LIVE, DANS LES
DEUX SENS -- test de GENERALISATION du fix #101 (le fait « a bouge ce tour » vit dans le flag natif).

`IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` (DECOMPILE) =
    EffectBonus.ForPercentIncrease(
        OwnerIsCaster & IsRangedAttack
        & ((F@0xa0 & !HasFlag(TurnFinished=3)) | !F@0xa0)
        & (!HasFlag(Moved=0) | HasFlag(Teleported=0xc)),
        ConditionalAmount(TriggeringAbilityIs(0x3ec=1004 MortisRound) ? base x2 : base))
avec `base = ConfigConst 0xf` = trait var `heavyWeaponExtraDmg` = 25 -> **+25% sur les attaques RANGED
d'une unite qui N'A PAS bouge ce tour**. Le flag `UnitFlag.Moved=0` est pose par
`IdunBattle.Entities.UnitExtensions$$SetMovedFlag`, appele par `IdunBattle.Operations.MoveUnitOperation$$Execute`,
et purge par `RemoveTurnFlags(new_activation=1)` du `IdunBattle.Operations.StartTurnOperation$$Execute`.

CE QUE CE TEST PROUVE (par cast LIVE de SentinelDirectives 1139, ranged, mono-coup, famille ATTACK) :
  (A) caster N'A PAS bouge (on DEPLACE LA CIBLE vers lui -- le move d'une AUTRE unite ne pose pas SON
      flag) -> le natif applique +25% : live == offline BIT-EXACT avec le flag ABSENT, et l'hypothese
      inverse (flag pose) DIVERGE.
  (B) caster A bouge (un seul deplacement, en restant a portee) -> le natif N'applique PAS +25% :
      live == offline BIT-EXACT avec le flag POSE (`set_moved_flag`), et l'hypothese inverse DIVERGE.
La double assertion « == l'hypothese vraie » ET « != l'hypothese fausse » est le coeur adversarial :
un port qui aurait simplement SUPPRIME le bonus passerait (B) et ECHOUERAIT (A), et reciproquement.

CIBLE = `orksNob` : traits ['Hero','GetStuckIn','BeastSlayer','Unstoppable'] -- ni Mechanical(5), ni
MkXGravis(0x3f5=1013), ni TerminatorArmour(0x40f=1039) -> la `DamageCondition` de l'autre passif du
caster, `HeavyGravCannon` (`IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect$$DamageCondition` =
OwnerIsActor & IsRangedAttack & (HasTrait(target,5)|HasTrait(target,0x3f5)|HasTrait(target,0x40f))),
est FALSE -> ce passif NON PORTE est INERTE ici, ce qui rend le bit-exact atteignable (contrairement au
test_sentinel_directives_live, dont la cible necroOverlord EST Mechanical -> residu +extraDmg).

Drive les positions (memoire « drive positions »), lit l'etat LIVE, aucune tuile/RVA hardcodee.
State-file UNIQUE en chemin ABSOLU, runner dispose au teardown. ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import set_moved_flag, UnitFlagsComponent
from engine.runner.abilities.base import ability_attack_params
from engine.runner.operations.damage import AttackDamageOperation

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]
CASTER_VIS = "admecDestroyer"      # Sy-Gex : trait HeavyWeapon (+25% ranged not-moved)
TARGET_VIS = "orksNob"             # NI Mechanical NI MkXGravis NI TerminatorArmour -> HeavyGravCannon inerte
ABILITY = 1139                     # SentinelDirectives : ranged, 1 coup, famille ATTACK
RANGE = 3


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _cr(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _build(seed):
    sf = ROOT / "logs" / "runners" / f"hwgate-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS,
         "--a-units", f"{TARGET_VIS},necroWarden", "--hp-target", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-300:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _mv(rpc, rid, uid, c):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)


def _legal_from_here(rpc, rid, cid):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == ABILITY), {})
    return set(x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or []))


def _my_turn(rpc, rid):
    """Avance jusqu'au tour du proprietaire du caster. Renvoie (dv, caster, my) ou (None, None, None).
    Chaque `endturn` -> `StartTurnOperation` -> `RemoveTurnFlags` : au retour, AUCUNE unite du joueur
    entrant ne porte `UnitFlag.Moved` (etat de depart propre pour le cas A)."""
    for _ in range(12):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        caster = _find(dv.get("units") or [], CASTER_VIS)
        if caster is None:
            return None, None, None
        my = caster.get("owner")
        if dv.get("currentPlayer") == my:
            return dv, caster, my
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _occupied(dv, exclude=()):
    out = set()
    for u in (dv.get("units") or []):
        if not u.get("alive") or u.get("id") in exclude:
            continue
        c = _cr(u)
        if c is not None:
            out.add(c)
    return out


def _place(rpc, rid, board, move_caster: bool):
    """Drive : place la CIBLE a portee du caster, et (si `move_caster`) DEPLACE le caster d'une tuile en
    restant a portee. Renvoie (cid, tid, moved) ou (None, None, None) si infaisable."""
    dv, caster, my = _my_turn(rpc, rid)
    if caster is None:
        return None, None, None
    cid = caster["id"]
    tgt = _find(dv.get("units") or [], TARGET_VIS)
    if tgt is None:
        return None, None, None
    tid = tgt["id"]
    # autres unites parquees LOIN (aucune interference LOS/overwatch)
    ccur = _cr(caster)
    far = [board.coord(t) for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), ccur) > 7]
    others = [u for u in (dv.get("units") or [])
              if u.get("alive") and u.get("id") not in (cid, tid)]
    for i, u in enumerate(others):
        if i < len(far):
            _mv(rpc, rid, u["id"], far[i])

    # ETAPE 1 (commune aux deux cas) : placer la CIBLE a portee du caster IMMOBILE, jusqu'a ce que le
    # cast soit LEGAL depuis sa position actuelle (le move d'une AUTRE unite ne pose pas SON flag).
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    occ = _occupied(dv2, exclude=(cid, tid))
    spots = [board.coord(t) for t in sorted(board.by_id)
             if board.walkable(t) and board.coord(t) not in occ
             and 2 <= hexgeo.distance(board.coord(t), ccur) <= RANGE]
    tspot = None
    for s in spots[:12]:
        _mv(rpc, rid, tid, s)
        if tid in _legal_from_here(rpc, rid, cid):
            tspot = s
            break
    if tspot is None:
        return None, None, None
    if not move_caster:
        return cid, tid, False

    # ETAPE 2 (cas B seulement) : DEPLACER le caster sur une tuile REELLEMENT atteignable
    # (`aiMovableTiles` = ce que le moteur accepte -> le move est APPLIQUE, donc `SetMovedFlag` pose
    # cote natif) en gardant la cible a portee ET le cast legal.
    mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
    cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
    cand = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
            if (t["col"], t["row"]) != ccur
            and 2 <= hexgeo.distance((t["col"], t["row"]), tspot) <= RANGE]
    cand.sort(key=lambda c: hexgeo.distance(c, ccur))
    for c in cand[:8]:
        _mv(rpc, rid, cid, c)
        dvc = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        if _cr(_find(dvc.get("units") or [], CASTER_VIS)) != c:
            continue                                            # move refuse -> tuile suivante
        if tid in _legal_from_here(rpc, rid, cid):
            return cid, tid, True
    return None, None, None


def _cast(rpc, rid, cid, tid):
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
        "captureEvents": True}, 120)
    ph, dirty = [], False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                ph.append(td.get("Amount"))
                dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock")) \
                    or bool(td.get("Attack_DidEvade"))
    return ph, dirty


def _offline(dv, ob, snap, board, s0, cid, tid, moved_flag: bool):
    st = load_state(dv, ob, snap, board=board)
    # LES DEUX HYPOTHESES SONT POSEES EXPLICITEMENT. Depuis `snapshot._load_unit_flags` (case-o10 SS 6),
    # `load_state` SEEDE `UnitFlag.Moved` depuis `combatSnapshot.units[].unitFlags` : l'etat recharge
    # porte donc deja le flag REEL. Ne rien faire ne construit plus l'hypothese « n'a pas bouge » -- il
    # faut RETIRER le flag, sinon les deux branches rendent la meme valeur et le contrefactuel (donc
    # tout le pouvoir discriminant du test) s'evapore EN SILENCE. C'est ce qu'a montre le premier
    # re-jeu apres le fix : `live == off_true` passait, `off_false != off_true` tombait.
    if moved_flag is None:
        pass                             # SEED BRUT : l'etat tel que `load_state` le rend, rien de pose
    elif moved_flag:
        set_moved_flag(st, cid)          # `SetMovedFlag` : le caster porte `UnitFlag.Moved`
    else:
        fl = st.get_entity(cid).get_component(UnitFlagsComponent)
        if fl is not None:               # `RemoveTurnFlags(new_activation=1)` retire Moved+Teleported
            fl.remove(UnitFlagsComponent.MOVED)
            fl.remove(UnitFlagsComponent.TELEPORTED)
    st.rng = _seed_rng(s0)
    bmin, bmax, pierce, hits = ability_attack_params(st, cid, "SentinelDirectives", "Physical",
                                                     ranged=True)
    out = AttackDamageOperation.execute_ability_attack(
        st, cid, tid, bmin, bmax, pierce, hits, damage_profile="Physical", is_melee=False,
        is_attack_damage_op=True)
    return (out or {}).get("per_hit") or []


def _run_case(rpc, seed, move_caster: bool):
    rid, sf, err = _build(seed)
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        cid, tid, moved = _place(rpc, rid, board, move_caster)
        if cid is None:
            pytest.skip(f"drive/legalite infaisable (move_caster={move_caster})")

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("combatSnapshot/dumpRng indispo")

        live, dirty = _cast(rpc, rid, cid, tid)
        if not live:
            pytest.skip("aucun degat live (cast no-op / LOS)")
        if dirty:
            pytest.skip("coup non propre (crit/block/evade)")

        off_true = _offline(dv, ob, snap, board, s0, cid, tid, moved_flag=moved)
        off_false = _offline(dv, ob, snap, board, s0, cid, tid, moved_flag=not moved)
        print(f"\n[HWGATE moved={moved}] live={live} off(flag={moved})={off_true} "
              f"off(flag={not moved})={off_false}")
        assert live == off_true, (
            f"live {live} != offline {off_true} avec le flag Moved={moved} (fait DRIVE) : le gate "
            f"no-move de HeavyWeapon_ExtraDmg diverge du natif")
        assert off_false != off_true, (
            f"les deux hypotheses de flag donnent {off_true} : le gate n'est PAS discriminant sur ce "
            f"scenario (bonus nul ?) -> l'egalite ci-dessus ne prouve rien")
        assert live != off_false, (
            f"live {live} == offline {off_false} avec le flag INVERSE : le natif ne suit pas le gate")
        # magnitude : le bonus est bien +25% (trait var heavyWeaponExtraDmg), pas un scalaire fitte
        # sans mouvement, c'est l'hypothese VRAIE (flag absent) qui porte le bonus ; avec mouvement,
        # c'est l'hypothese FAUSSE.
        hi, lo = (off_true, off_false) if not moved else (off_false, off_true)
        assert lo[0] < hi[0] and abs(hi[0] / lo[0] - 1.25) < 0.01, (
            f"ratio bonus {hi[0]}/{lo[0]} != 1.25 (+heavyWeaponExtraDmg=25%)")
        # LE FLAG VIENT DU SEED, PAS DE LA FIXTURE (case-o10 SS 6). `load_state` SEUL -- sans aucune
        # pose ni retrait manuel -- doit deja reproduire le live, dans les DEUX regimes. Sans cette
        # assertion, les deux cas ci-dessus continueraient de passer si
        # `snapshot._load_unit_flags` etait supprime (ils posent le flag eux-memes) : c'est
        # exactement le trou par lequel un replay-diff a sur-evalue le degat de `blackObliterator`
        # de +25% (live 5868 / offline 7096) sans qu'aucun test ne bronche.
        off_seed = _offline(dv, ob, snap, board, s0, cid, tid, moved_flag=None)
        print(f"[HWGATE moved={moved}] off(seed brut, aucune pose)={off_seed}")
        assert off_seed == live, (
            f"seed brut {off_seed} != live {live} (moved={moved}) : `load_state` ne reconstruit pas "
            f"`UnitFlag.Moved` depuis `combatSnapshot.units[].unitFlags` -- tout replay-diff d'une "
            f"attaque suivant un deplacement re-diverge de +25% en silence")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def test_heavy_weapon_gate_not_moved_applies_bonus(live_session, rpc):
    """(A) Le caster N'A PAS bouge (c'est la CIBLE qu'on deplace) -> +25% applique par le natif ;
    l'offline sans flag est BIT-EXACT, l'offline avec flag DIVERGE."""
    _run_case(rpc, "777", move_caster=False)


def test_heavy_weapon_gate_moved_cancels_bonus(live_session, rpc):
    """(B) Le caster A bouge (1 deplacement, toujours a portee) -> le natif N'applique PAS +25% ;
    l'offline AVEC flag est BIT-EXACT, l'offline sans flag DIVERGE."""
    _run_case(rpc, "777", move_caster=True)
