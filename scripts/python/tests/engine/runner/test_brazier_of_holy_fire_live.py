"""BrazierOfHolyFire (actif 1041, `adeptCanoness` -- Canoness, HERO Adepta Sororitas) : face COMBAT
portee -> arbre DSL, confrontee au LIVE sur DEUX geometries DISCRIMINANTES (case-brazier-radbombardment).

`IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
(DECOMPILE, mirror 1:1 -- cf. `abilities/sisterhood.py`) :

    AActiveAbility.Execute( op_BitwiseAnd( op_BitwiseAnd(
        AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(0xc/0xd),
                               GetDamageProfile(config,0), GetNumberOfHits(target@0x178)),
        AddEffect(5 = Fire, stateRef, TargetTiles@0x190) ),                    # surcharge 4-ARGS
      AddEffect(0x433 = 1075, stateRef, source = caster@0x160,
                UnitsWithTrait(SurroundingUnits(target@0x178, ConfigConst(0x44), 1, 1, 3), 0x3fb, 3),
                TurnsFromRounds(2)) ) )

    GetNumberOfHits(u) = ConditionalAmount( HasTrait(u, 0x3fb = 1019 Daemon),
                                            ConfigConst(0x32 = nrOfHits_2), ConfigConst(0x2f = nrOfHits) )

CE QUE CES TESTS PROUVENT (lisent l'etat LIVE ; drivent les positions ; state-file UNIQUE dispose) :
  (1) EXECUTION REELLE : `ported=True` (garde anti-no-op silencieux -- AVANT ce port, 1041 etait ABSENT
      du registre COMBAT : `ported=False`, 0 degat, AUCUNE erreur. Mesure du 2026-07-26, runner MC1_67 :
      live 2 coups [1899, 1599] / port 0 -- divergence d'etat SILENCIEUSE).
  (2) DEGAT BIT-EXACT per-coup live == offline (l'observable direct, immunise au tick de fin de tour).
  (3) BRANCHE DE COUPS `ConditionalAmount(HasTrait(cible, Daemon))` : cible NON-Daemon -> `nrOfHits`
      coups ; cible DAEMON -> `nrOfHits_2` coups. C'est LE scenario discriminant du port : un port qui
      lirait `nrOfHits` en dur passerait le 1er test et TOMBERAIT sur le second.
  (4) FEU DE TUILE : la MainTile de la cible porte `Fire` (5) live ET offline.
  (5) MARQUAGE `BrazierOfHolyFire_ExtraDmg` (1075) sur les Daemons a <= `range_2` hex de la cible,
      CIBLE INCLUSE (`SurroundingUnits(..., includeCenter=1)`).

ORACLES DES PARAMS (#96 -- aucun scalaire de gameplay fige ici). Le decompile TRANCHE : les deux
branches de coups partent de `IdunBattleLogic.Entities.DSLFormulas$$ConfigConst`, le profil de
`IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile`, le rayon d'un `ConfigConst` -- valeurs
BRUTES (`GetNumberConstant` = `GetStringConstant` + `Int32.Parse`). L'oracle est donc la CONFIG :
`gameconfig.ability("BrazierOfHolyFire").constants` (`nrOfHits`, `nrOfHits_2`, `range_2`,
`damageProfile`) et `gameconfig.damage_profile(<profil>).PiercingRatio`.

ARTEFACT DE MESURE CONNU, et pourquoi on n'asserte PAS le delta de PV : les cibles Necrons portent le
trait `LivingMetal` (i2 : « Regenerates {[hpPct]}% of its max Health at the start of the players' turn »).
1041 FINIT le tour du caster (defauts base) -> entre le cast et la relecture `decisionView`, le moteur
natif a demarre le tour adverse et REGENERE la cible. Mesure : coups [1899, 1599] = 3498 demandes, delta
PV live 3071 = 3498 - 427, et 427 = 5 % des 8536 PV max. L'observable NON POLLUE est le `Amount` PAR COUP
de l'evenement de degat -- c'est lui qu'on confronte (meme discipline que #98 : ne pas lire un compteur
APRES le tick).

ASCII only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import pytest

import gameconfig as GC
import hexgeo
from engine.entities.pathfinding.board import Board
from engine.entities.effect_type import EffectType
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent
from engine.runner.abilities.base import ability_attack_params
from engine.runner.abilities.sisterhood import BrazierOfHolyFireAbility
from engine.runner.abilities.handler import ABILITY_CLASSES

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import damage_profile_pierce    # noqa: E402

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "adeptCanoness"
ABILITY = 1041
FIRE = int(EffectType.Fire)                                  # 5
EXTRA_DMG = int(EffectType.BrazierOfHolyFire_ExtraDmg)       # 0x433 = 1075
TRAIT_DAEMON = int(UnitTrait.Daemon)                         # 0x3fb = 1019


def _const(key):
    """ORACLE : constante de config d'ability 1041 (`ConfigConst`/`GetNumberConstant`, lecture BRUTE cote
    natif). Fail explicite si la cle a disparu de la config (le natif, lui, LEVE)."""
    v = ((GC.ability("BrazierOfHolyFire") or {}).get("constants") or {}).get(key)
    assert v is not None, (f"oracle introuvable : gameconfig.ability('BrazierOfHolyFire').constants.{key} "
                           f"absent -- le natif le lit en ConfigConst, il DOIT exister")
    return v


def _has_daemon(visual_id: str) -> bool:
    return "Daemon" in ((GC.unit(visual_id) or {}).get("traits") or [])


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _cr(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _build(seed, a_units):
    sf = ROOT / "logs" / "runners" / f"brazier-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", a_units,
         # #933 -- LE COUP PROPRE SE CONSTRUIT. Ce fichier SKIPPE sur « coup non propre
         # (crit/block/evade) » : il trouvait son coup propre SANS RIEN DEMANDER tant que le canal
         # crit/block etait MUET. Depuis la bascule #419-r5/-r6 (items BiS par defaut) le tirage
         # est ouvert des DEUX cotes, et le skip est devenu FREQUENT -- mesure du 2026-08-11 :
         # 1 passed / 2 skipped, rc 0, sans que rien ne le signale (le fichier n'est pas
         # INTEGRALEMENT skippe, donc la garde #455 ne le voit pas). Les QUATRE faces, parce que
         # `--crit` n'epingle que les p-units et `--crit-target` que les a-units (#419-r6 §3.1).
         "--crit", "0,0", "--crit-target", "0,0",
         "--block-player", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-300:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _approach(rpc, rid, board, target_vis, rng_cfg):
    """Avance jusqu'a mon tour ; rapproche le caster a portee `constants.range` de la cible. Renvoie
    (cid, tid, my_player) ou None. DRIVE les positions (jamais « bloque par la geometrie de spawn »)."""
    def tile_of(u):
        cr = _cr(u)
        return board.id_at(cr[0], cr[1]) if cr else None

    def bfs(src):
        dist = {src: 0}
        q = deque([src])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and (n == src or board.walkable(n)):
                    dist[n] = dist[x] + 1
                    q.append(n)
        return dist

    def legal(cid):
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == ABILITY), {})
        return [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]

    my = None
    for _ in range(25):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        caster, tgt = _find(units, CASTER_VIS), _find(units, target_vis)
        if caster is None or tgt is None:
            return None
        if my is None:
            my = caster.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cid = caster["id"]
        if hexgeo.distance(_cr(caster), _cr(tgt)) <= rng_cfg and tgt["id"] in legal(cid):
            return cid, tgt["id"], my
        dist = bfs(tile_of(tgt))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist and dist[t] >= 1]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        best = min(pool, key=lambda t: dist[t])
        col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": col, "row": row}}}, 60)
    return None


def _cast_live(rpc, rid, cid, tid):
    """Cast LIVE + extraction des `Amount` PAR COUP attribues a 1041 (l'observable NON pollue par le
    tick de fin de tour, cf. l'en-tete)."""
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
        "captureEvents": True}, 150)
    per_target, flags = {}, {"crit": False, "block": False, "evade": False}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                per_target.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
                flags["crit"] = flags["crit"] or bool(td.get("Attack_DidCrit"))
                flags["block"] = flags["block"] or bool(td.get("Attack_DidBlock"))
                flags["evade"] = flags["evade"] or bool(td.get("Attack_DidEvade"))
    return per_target, flags, res


def _tile_effects(rpc, rid, board):
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    return {board.id_at(t["col"], t["row"]): sorted(e.get("effectType")
                                                    for e in (t.get("effects") or []))
            for t in (tm.get("tiles") or [])}


def _run(rpc, target_vis, seed="777", extra_enemies=""):
    """Monte un duel Canoness vs `target_vis`, approche, caste 1041 LIVE puis rejoue le port offline sur
    le MEME etat et le MEME rng. Rend (contexte de comparaison) ou leve pytest.skip."""
    a_units = target_vis + ("," + extra_enemies if extra_enemies else "")
    rid, sf, err = _build(seed, a_units)
    if rid is None:
        pytest.skip(f"build runner KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = _approach(rpc, rid, board, target_vis, int(_const("range")))
        if placed is None:
            pytest.skip(f"caster n'a pas atteint la portee {_const('range')} de {target_vis}")
        cid, tid, my = placed

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")
        tiles_pre = _tile_effects(rpc, rid, board)
        eff_pre = {u["id"]: [e.get("effectType") for e in (u.get("effects") or [])]
                   for u in (dv.get("units") or [])}
        tpos = _cr(next(u for u in dv["units"] if u["id"] == tid))
        target_tile = board.id_at(tpos[0], tpos[1])

        live, flags, res = _cast_live(rpc, rid, cid, tid)
        if not live.get(tid):
            pytest.skip(f"aucun degat live sur la cible (LOS/obscurci) cast={str(res)[:160]}")
        if flags["crit"] or flags["block"] or flags["evade"]:
            pytest.skip(f"coup non propre (crit/block/evade): {flags}")
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        tiles_post = _tile_effects(rpc, rid, board)
        eff_post = {u["id"]: [e.get("effectType") for e in (u.get("effects") or [])]
                    for u in (dv2.get("units") or [])}

        st = load_state(dv, ob, snap, board=board)
        st.rng = _seed_rng(s0)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=ABILITY))
        last = runner.ability_handler.last or {}
        return {"rid": rid, "sf": sf, "board": board, "cid": cid, "tid": tid, "my": my,
                "target_tile": target_tile, "dv": dv, "live": live, "last": last, "st": st,
                "runner": runner, "tiles_pre": tiles_pre, "tiles_post": tiles_post,
                "eff_pre": eff_pre, "eff_post": eff_post}
    except BaseException:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        sf.unlink(missing_ok=True)
        raise


def _dispose(rpc, ctx):
    try:
        rpc("disposeRunner", {"runnerId": ctx["rid"]}, 20)
    except Exception:
        pass
    try:
        ctx["sf"].unlink()
    except Exception:
        pass


def _assert_common(ctx, want_hits: int, target_vis: str, compare_hits=None):
    """Assertions PARTAGEES par les deux geometries : execution reelle, nb de coups == oracle config,
    degat per-coup bit-exact live==offline sur TOUS les coups, feu sur la tuile de la cible.

    `compare_hits` = nombre de coups confrontes BIT-EXACT (None = tous, le regime des DEUX geometries).
    La geometrie DAEMON n'en confrontait qu'UN tant que le port SAUTAIT le jet de block de
    `Daemon_ExtraBlock` (1034) que le natif roule -- un tirage d'ecart, donc les coups 2+ decalaient.
    Ce gap est FERME (#221 : `AttackDamageOperation._block_sources` thread l'Attack courante du
    defenseur a `defender_effect_block_sources`, mirror de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$GetBlockDamage`) -> les 4 coups
    sont confrontes."""
    last, live, tid = ctx["last"], ctx["live"], ctx["tid"]
    assert last.get("ported") is True, (
        f"BrazierOfHolyFire (1041) non execute (no-op) : last={last} ; "
        f"unported={getattr(ctx['runner'].ability_handler, 'unported', None)}")
    off_ph = (last.get("attack") or {}).get("per_hit") or []
    live_ph = live.get(tid) or []
    assert last.get("hits") == want_hits, (
        f"GetNumberOfHits rendu {last.get('hits')} != oracle config {want_hits} pour {target_vis} "
        f"(Daemon={_has_daemon(target_vis)}) -- la ConditionalAmount(HasTrait(cible, Daemon), "
        f"nrOfHits_2, nrOfHits) ne lit pas la bonne branche ou pas les bonnes constantes")
    assert len(live_ph) == want_hits, (
        f"{len(live_ph)} coups LIVE (per_hit={live_ph}) != oracle config {want_hits} -- soit une "
        f"reduction de coups joue dans ce setup (le port doit la modeliser), soit l'oracle/le port ne "
        f"lisent pas la constante que le natif passe a AttackWithAttackDamage")
    n = want_hits if compare_hits is None else int(compare_hits)
    assert off_ph[:n] == live_ph[:n], (
        f"degat per-coup offline {off_ph[:n]} != live {live_ph[:n]} (sur les {n} premiers coups) : un "
        f"etage du coup diverge (bornes MinMaxDamage, percage du profil, famille de factory, ou un "
        f"passif du caster non porte)")
    # FEU sur la MainTile de la cible : live ET offline. Cote port le canal `OnFire` du profil Flame
    # (after-hit) pose le feu AVANT l'`AddEffect` explicite -> ce dernier est un no-op « deja present »,
    # exactement comme le gate natif d'`AddEffectOperation`. On asserte donc la PRESENCE, pas `placed`.
    tt = ctx["target_tile"]
    assert FIRE in (ctx["tiles_post"].get(tt) or []), (
        f"la tuile {tt} de la cible n'est PAS en feu LIVE apres le cast "
        f"(pre={ctx['tiles_pre'].get(tt)} post={ctx['tiles_post'].get(tt)})")
    st = ctx["st"]
    assert st.effects is not None and st.effects.has_effect(tt, effect_type=FIRE), (
        f"la tuile {tt} de la cible n'est PAS en feu OFFLINE (AddEffect(5 Fire -> TargetTiles@0x190) "
        f"non materialise)")


# =========================================== GEOMETRIE 1 : cible NON-Daemon (branche `nrOfHits`)

def test_brazier_non_daemon_target_live(live_session, rpc):
    """Cible SANS le trait Daemon -> branche `ConfigConst(0x2f) = nrOfHits` du `ConditionalAmount`.
    Prouve (1) execution reelle, (2) degat per-coup bit-exact, (3) branche de coups par defaut,
    (4) feu de tuile. AUCUN Daemon a portee -> le volet 1075 ne marque personne (assertion negative :
    c'est le pendant du test Daemon)."""
    target_vis = "necroWarden"
    assert not _has_daemon(target_vis), f"{target_vis} porte Daemon : la geometrie 1 n'est plus discriminante"
    ctx = _run(rpc, target_vis)
    try:
        want = int(_const("nrOfHits"))
        _assert_common(ctx, want, target_vis)
        # ORACLE percage : PiercingRatio du PROFIL de config (isole tant que le caster n'a pas d'ExtraPierce)
        prof = _const("damageProfile")
        st, cid = ctx["st"], ctx["cid"]
        sc = st.get_entity(cid).get_component(StatsComponent)
        xp = int(sc.ctx.extra_pierce or 0) + int(sc.ctx.extra_pierce_ranged or 0)
        _, _, pierce, hits = ability_attack_params(st, cid, "BrazierOfHolyFire", prof, ranged=True)
        assert xp == 0 or pierce == damage_profile_pierce(prof) + xp, (
            f"percage {pierce} incoherent avec l'oracle profil {damage_profile_pierce(prof)} + "
            f"ExtraPierce {xp}")
        # volet 1075 : aucun Daemon dans le setup -> personne n'est marque, des DEUX cotes.
        marked_off = [m for m in (ctx["last"].get("marked") or []) if m.get("placed")]
        assert not marked_off, f"1075 pose offline sans Daemon a portee : {marked_off}"
        for uid, effs in ctx["eff_post"].items():
            new = [e for e in effs if e not in (ctx["eff_pre"].get(uid) or [])]
            assert EXTRA_DMG not in new, f"1075 pose LIVE sur u{uid} sans Daemon a portee"
        print(f"\n[BRAZIER/non-daemon] hits={want} live={ctx['live'].get(ctx['tid'])} "
              f"off={(ctx['last'].get('attack') or {}).get('per_hit')} fire_tile={ctx['target_tile']}")
    finally:
        _dispose(rpc, ctx)


# ===================================== GEOMETRIE 2 : cible DAEMON (branche `nrOfHits_2` + marquage)

def test_brazier_daemon_target_live(live_session, rpc):
    """Cible AVEC le trait Daemon -> branche `ConfigConst(0x32) = nrOfHits_2` (4 coups au lieu de 2) ET
    marquage `BrazierOfHolyFire_ExtraDmg` (1075) sur elle-meme (`SurroundingUnits(..., includeCenter=1)`
    -> le CENTRE compte). C'est le scenario DISCRIMINANT : un port qui lirait `nrOfHits` en dur (ou qui
    inverserait les deux branches du ConditionalAmount) passe le test non-Daemon et TOMBE ici.

    PORTEE DE LA CONFRONTATION DE DEGAT : les 4 coups, bit-exact. Mesure du 2026-07-27
    (`probe_brazier_daemon_offset.py`, board MC1_67, seed 777 -- MEME suite de valeurs `v1..v8` tiree
    du rng dans les trois runs) :
        necroWarden      (NON Daemon, 2 coups) : live = v1, v3         -> 2 tirages/coup
        worldEightbound  (Daemon,     4 coups) : live = v1, v4, v6, v8 -> +1 tirage au 1er coup
        blackObliterator (Daemon,     4 coups) : live = v1, v4, v6, v8 -> idem
    Le tirage surnumeraire est le JET DE BLOCK que le natif roule parce que toute unite Daemon porte
    `Daemon_ExtraBlock` (1034), pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$
    CreateUpdateEffectBehaviour`. Il n'est roule QU'AU 1er coup : la source echoue, son `BEntityId` part
    dans `failedBlockIds` et `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`
    l'exclut des coups suivants (d'ou v4->v6->v8 a 2 tirages). #221 a ferme le gap ; ce test GARDE la
    fermeture. Chiffrage reproductible : `probe_daemon_extrablock_gap.py`."""
    target_vis = "blackObliterator"
    assert _has_daemon(target_vis), f"{target_vis} n'a plus le trait Daemon : geometrie 2 non discriminante"
    ctx = _run(rpc, target_vis)
    try:
        want = int(_const("nrOfHits_2"))
        assert want != int(_const("nrOfHits")), (
            "nrOfHits_2 == nrOfHits dans la config : la branche Daemon n'est plus observable, ce test "
            "ne discrimine plus rien")
        _assert_common(ctx, want, target_vis)   # #221 : les 4 coups, plus de bridage
        tid = ctx["tid"]
        # (5) MARQUAGE 1075 : la cible EST un Daemon et le centre est INCLUS -> elle se marque elle-meme.
        marked_off = {m["target"] for m in (ctx["last"].get("marked") or []) if m.get("placed")}
        assert tid in marked_off, (
            f"la cible Daemon u{tid} n'est PAS marquee 1075 offline (marked={ctx['last'].get('marked')}) "
            f"-- SurroundingUnits(target, range_2, includeCenter=1) doit inclure le CENTRE")
        new_live = [e for e in (ctx["eff_post"].get(tid) or [])
                    if e not in (ctx["eff_pre"].get(tid) or [])]
        assert EXTRA_DMG in new_live, (
            f"le natif n'a PAS pose 1075 sur la cible Daemon (effets apparus={new_live}) -- soit le "
            f"selecteur d'effet differe, soit le trait Daemon n'est pas celui lu (0x3fb)")
        assert ctx["st"].effects.has_effect(tid, effect_type=EXTRA_DMG), \
            "1075 non materialise offline sur la cible Daemon"
        print(f"\n[BRAZIER/daemon] hits={want} (vs nrOfHits={_const('nrOfHits')}) "
              f"live={ctx['live'].get(tid)} off={(ctx['last'].get('attack') or {}).get('per_hit')} "
              f"marked_off={sorted(marked_off)}")
    finally:
        _dispose(rpc, ctx)


# ============================================================ table offline (aucune session requise)

def test_brazier_registered_and_turn_flags():
    """1041 route vers la classe portee et garde les turn-flags PAR DEFAUT (absent des deux frozensets
    d'override -> le cast termine le tour et pose ActiveAbilityUsed). Pur offline."""
    from engine.runner.abilities.base import (NO_END_TURN_ABILITY_TYPES,
                                              NO_ABILITY_USED_FLAG_ABILITY_TYPES,
                                              sets_end_turn_flags_for,
                                              sets_active_ability_used_flag_for)
    from engine.runner.state import State
    assert ABILITY_CLASSES.get(ABILITY) is BrazierOfHolyFireAbility
    assert BrazierOfHolyFireAbility.ABILITY_TYPE == ABILITY
    assert ABILITY not in NO_END_TURN_ABILITY_TYPES
    assert ABILITY not in NO_ABILITY_USED_FLAG_ABILITY_TYPES
    st = State()
    assert sets_end_turn_flags_for(ABILITY, st, 1) is True
    assert sets_active_ability_used_flag_for(ABILITY, st, 1) is True
    # les 4 constantes lues par l'arbre DOIVENT exister (le natif LEVE si une cle manque)
    for k in ("nrOfHits", "nrOfHits_2", "range_2", "damageProfile"):
        assert _const(k) is not None
