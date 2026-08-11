"""`HeavyGravCannon` (EffectType **1291**, passif d'`admecDestroyer` <<Sy-Gex>>) confronte au LIVE --
les DEUX canaux, et les DEUX faces de chaque gate.

`IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect` (DECOMPILE, mirror 1:1 -- cf.
`engine/entities/effects/loki/extra_damage.py::HeavyGravCannonEffect`) :

    DamageCondition() = ( get_OwnerIsActor & IsRangedAttack )
                        & ( HasTrait(target,5=Mechanical) | HasTrait(target,0x3f5=1013 MkXGravis)
                          | HasTrait(target,0x40f=1039 TerminatorArmour) )
    CreateEffectDamageBonusForAttack = EffectBonus.ForAddition( DamageCondition, ConfigVar(8=extraDmg) )
    CreatePiercingBonusForAttack     = EffectBonus.ForPiercing( DamageCondition, ConfigVar(0x3f=extraPierceRatio) )

Les DEUX canaux appellent LA MEME `...$$DamageCondition` (ce n'est pas un etage distinct par canal) ;
le ctor `BaseEffect(AbilityOrEffect.op_Implicit(0x4d1 = 1233), 1)` fait lire la config de l'ABILITY
`HeavyGravCannon` (TriggeredAbilityType 1233 -- homonyme de l'EffectType 1291, et sans rapport avec
TriggeredAbilityType 1291 = SelfRepairMechanism).

POURQUOI CE FICHIER EN PLUS de `test_sentinel_directives_live` : la-bas la cible `necroOverlord`
(armure 1909) laisse le canal PERCAGE **INERTE**, car le percage natif est un PLANCHER
(`StaticBattleRules.Damage$$GetDamageWithPiercing` = `max(0, d - armure, d x pierce%)`) et la branche
armure domine. Le flat seul y est donc mesure. ICI la cible est `adeptMorvenn` (Mechanical, armure
mesuree 2411) : le seuil `armure / (1 - pierce_eff)` = 2411 / 0.39 = 6182 depasse la borne HAUTE du
coup (maxDmg + extraDmg = 5761) => la branche PERCAGE gagne POUR TOUT TIRAGE, et les deux canaux
deviennent simultanement observables (probe `probe_hgc_1291.py --case band`).

CE QUE CE FICHIER PROUVE :
  (1) DETERMINISTE (offline sur l'etat CAPTE live) : l'effet 1291 seede sur Sy-Gex rend
      +extraDmg[passiveLvl] x mult ET +extraPierceRatio[passiveLvl] pour une cible Mechanical en
      RANGED, et RIEN en melee / cible non qualifiante / nature de coup inconnue (tri-etat #106).
  (2) REPLAY-DIFF a QUATRE hypotheses : le cast LIVE est confronte a l'offline sous
      {les deux canaux, flat SEUL, percage SEUL, aucun canal}. La bit-exactitude ne vaut que si
      les trois hypotheses degradees DIVERGENT -- c'est ce qui separe « le port est juste » de
      « le scenario ne discrimine rien ».
  (3) MATERIALISATION finale du vecteur (garde heritee de la campagne que ce montage a permis de
      faire) : ce regime est le SEUL, sur l'ability bounds-mode famille ATTACK, ou la valeur finale
      est FRACTIONNAIRE -- elle ne peut l'etre que si les DEUX %-list sont vides ET que la branche
      PERCAGE du plancher l'emporte. On force les deux materialisations (`round_materialize`) et on
      verrouille : ARRONDI == live, TRONCATURE != live (cf.
      `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` slot 0x10,
      `Fix64.Round(·, AwayFromZero)`). Meme forme que la garde #131 de l'attaque normale.

⚠ Le test (3) n'est discriminant que si le tirage tombe a partie fractionnaire >= .5 (~50 % des
tirages du regime) ; sinon il se SKIPPE explicitement plutot que de rendre un vert vide.

Drive les positions, lit l'etat LIVE, aucune tuile/valeur de gameplay figee (tout oracle vient de
gameconfig). State-file UNIQUE en chemin ABSOLU sous logs/, runner dispose au teardown. ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import pytest

import gameconfig as GC
import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, set_moved_flag
from engine.runner.damage_model import defender_fixed_armor, target_trait_names
from engine.entities.effects.magnitude import ability_var

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]
CASTER_VIS = "admecDestroyer"        # Sy-Gex : porteur UNIQUE du passif HeavyGravCannon (1291)
TARGET_VIS = "adeptMorvenn"          # Mechanical + armure HAUTE -> la branche PERCAGE gagne toujours
FILLER_VIS = "necroWarden"           # 2e a-unit (le build veut plus d'une unite adverse)
ABILITY = 1139                       # SentinelDirectives : RANGED, 1 coup, famille ATTACK
EFFECT_NAME = "HeavyGravCannon"      # nom d'EffectType capte live (effectType 1291)
ABILITY_CFG = "HeavyGravCannon"      # config lue par le ConfigVar (AbilityOrEffect 0x4d1 = 1233)


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


def _const(key):
    v = ((GC.ability("SentinelDirectives") or {}).get("constants") or {}).get(key)
    assert v is not None, f"oracle absent : ability('SentinelDirectives').constants.{key}"
    return v


def _build(seed):
    """Runner isole. SURTOUT PAS `--hp-target` : ce knob remet a **0** le `FixedArmor` des a-units
    (MESURE probe_hgc_1291 --case band : adeptMorvenn 2411 -> 0, necroWarden 2008 -> 0, seule
    difference entre les deux runs) -- or c'est precisement l'armure qui fait gagner la branche
    PERCAGE du plancher `max(0, d - armure, d x pierce%)`. Sans armure, le canal percage redevient
    inerte et le scenario ne discrimine plus rien. La survie de la cible est assuree autrement :
    `adeptMorvenn` a ~9500 PV pour un coup de ~3500 (mesure), donc pas de cap overkill."""
    sf = ROOT / "logs" / "runners" / f"hgc-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS,
         "--a-units", f"{TARGET_VIS},{FILLER_VIS}",
         # #933 -- LE COUP PROPRE SE CONSTRUIT (cf. le skip « coup non propre (crit/block/evade) »
         # plus bas), au lieu d'etre trouve par chance : depuis la bascule #419-r5/-r6 le tirage
         # crit/block est ouvert des DEUX cotes. Les QUATRE faces (#419-r6 §3.1).
         # ⚠ PREVENTIF ICI, et c'est MESURE : ce fichier rend 1 passed / 1 skipped AVANT comme
         # APRES, et son skip restant est celui du tirage a partie fractionnaire < .5 (L401) --
         # identique sous `TACTICUS_BIS_ITEMS=0`. Ce montage ne repare donc AUCUN ecart observe ;
         # il ferme un skip PROBABILISTE qui, lui, depend du tirage du jour.
         # Ces leviers n'ecrivent QUE `CritChance`/`CritDamage` (resp. `BlockChance`/
         # `BlockDamage`) : le `FixedArmor` dont depend la branche PERCAGE, et que la docstring
         # ci-dessus protege de `--hp-target`, n'est PAS touche.
         "--crit", "0,0", "--crit-target", "0,0",
         "--block-player", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-300:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _approach(rpc, rid, board):
    """Avance jusqu'a mon tour et rapproche le caster a portee `constants.range` de la cible, jusqu'a
    ce que le cast soit LEGAL depuis sa position. Renvoie (cid, tid, moves) ou None."""
    def tile_of(u):
        cr = _cr(u)
        return board.id_at(cr[0], cr[1]) if cr else None

    def bfs(src):
        dist = {src: 0}; q = deque([src])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and (n == src or board.walkable(n)):
                    dist[n] = dist[x] + 1; q.append(n)
        return dist

    def legal(cid):
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == ABILITY), {})
        return [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]

    my, moves = None, 0
    rng_cfg = int(_const("range"))
    for _ in range(25):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        caster, tgt = _find(units, CASTER_VIS), _find(units, TARGET_VIS)
        if caster is None or tgt is None:
            return None
        if my is None:
            my = caster.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60); continue
        cid = caster["id"]
        if hexgeo.distance(_cr(caster), _cr(tgt)) <= rng_cfg and tgt["id"] in legal(cid):
            return cid, tgt["id"], moves
        dist = bfs(tile_of(tgt))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist and dist[t] >= 2]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": col, "row": row}}}, 60)
        moves += 1
    return None


def _cast_live(rpc, rid, cid, tid):
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


# --- hypotheses offline : on NEUTRALISE un canal en shadowant la methode SUR L'INSTANCE captee -----
#     (l'effet reste present et actif : seule sa contribution a l'axe vise disparait -> l'ecart
#      mesure isole CE canal, pas la presence de l'effet).
_HYPOTHESES = ("full", "flat_only", "pierce_only", "none")


def _hgc_of(state, cid):
    return [e for e in state.effects.by_unit.get(int(cid), []) if e.name == EFFECT_NAME]


def _apply_hypothesis(state, cid, hyp: str) -> bool:
    """Rend False si l'effet n'est pas seede (rien a neutraliser -> le test le signale)."""
    effs = _hgc_of(state, cid)
    if not effs:
        return False
    for e in effs:
        if hyp == "none":
            state.effects.by_unit[int(cid)] = [
                x for x in state.effects.by_unit[int(cid)] if x is not e]
        elif hyp == "flat_only":
            e.create_effect_piercing_bonus_for_attack = lambda *a, **k: None
        elif hyp == "pierce_only":
            e.create_effect_damage_bonus_for_attack = lambda *a, **k: None
    return True


def _offline(dv, ob, snap, board, s0, cid, tid, moves, hyp: str, force_round=None):
    """Rejoue le cast OFFLINE sur le MEME etat et le MEME flux RNG. `force_round` (None = defaut du
    port) force la materialisation finale de `apply_all_modifiers` -> garde (3)."""
    # #169 : `damage_ops` est un PACKAGE ; ce cast passe par le vecteur d'ABILITY bounds-mode
    # (`execute_ability_attack`), qui resout `apply_all_modifiers` dans les globals de
    # `damage_ops.ability`. Patcher le `__init__` du package serait un NO-OP SILENCIEUX -- la
    # garde (3) ne verrait plus AUCUN ecart entre ARRONDI et TRONCATURE et se skipperait
    # (`force_round` inerte), c.-a-d. un vert qui ne mesure plus rien.
    from engine.runner.operations.damage_ops import ability as damage_ops_ability
    from engine.services.damage_modifiers import apply_all_modifiers as _aam
    st = load_state(dv, ob, snap, board=board)
    if moves > 0:
        set_moved_flag(st, cid)          # fait DRIVE que `load_state` ne peut pas relire (#101)
    assert _apply_hypothesis(st, cid, hyp), (
        f"effet {EFFECT_NAME} absent du seed offline (effets captes = "
        f"{[e.name for e in st.effects.by_unit.get(int(cid), [])]}) -- rien a confronter")
    st.rng = _seed_rng(s0)
    runner = Runner(st).install_default_handlers(20)
    if force_round is not None:
        damage_ops_ability.apply_all_modifiers = (
            lambda v, m, round_materialize=False, _f=force_round: _aam(v, m, round_materialize=_f))
    try:
        runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=ABILITY))
    finally:
        damage_ops_ability.apply_all_modifiers = _aam
    last = runner.ability_handler.last or {}
    return ((last.get("attack") or {}).get("per_hit") or []), last


# ==================================================================== (1) gates + magnitude, offline

def test_heavy_grav_cannon_gates_and_magnitude_live(live_session, rpc):
    """DETERMINISTE, sur l'etat CAPTE live : l'effet 1291 seede sur Sy-Gex contribue aux DEUX canaux
    contre une cible Mechanical en RANGED, et a AUCUN dans les cas ou la `DamageCondition` est fausse
    (melee, nature inconnue, cible sans les 3 traits, attaquant != porteur)."""
    rid, sf, err = _build("777")
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv, ob, snap)
        caster = _find(dv.get("units") or [], CASTER_VIS)
        tgt = _find(dv.get("units") or [], TARGET_VIS)
        if caster is None or tgt is None:
            pytest.skip("caster/cible absents du build")
        cid, tid = caster["id"], tgt["id"]
        effs = _hgc_of(st, cid)
        assert effs, (f"{EFFECT_NAME} non seede sur {CASTER_VIS} : effets captes = "
                      f"{[e.get('name') for e in (caster.get('effects') or [])]}")
        eff = effs[0]
        assert eff.effect_type == 1291, f"effectType {eff.effect_type} != 1291 (homonymie d'ids ?)"
        # ORACLE = gameconfig, indexe par le niveau/mult LUS de l'etat live (jamais un scalaire fige).
        want_flat = ability_var(ABILITY_CFG, "extraDmg", eff.ability_level,
                                multiplier_pct=eff.ability_variables_multiplier)
        want_pierce = ability_var(ABILITY_CFG, "extraPierceRatio", eff.ability_level,
                                  multiplier_pct=eff.ability_variables_multiplier)
        assert want_flat and want_pierce, (
            f"oracle gameconfig vide : ability('{ABILITY_CFG}').variables extraDmg/extraPierceRatio "
            f"@lvl={eff.ability_level}")
        tt = target_trait_names(st, tid)
        assert "Mechanical" in tt, f"{TARGET_VIS} n'est plus Mechanical (traits={sorted(tt)})"

        # -- canal DEGAT ------------------------------------------------------------------------
        got = eff.create_effect_damage_bonus_for_attack(is_ranged=True, target_traits=tt)
        assert got is not None and got.kind == "Addition" and got.value == want_flat, (
            f"canal degat : {got!r} != ForAddition({want_flat}) -- `ForAddition(cond, ConfigVar(8="
            f"extraDmg))` indexe par passiveAbilityLevel={eff.ability_level} x mult="
            f"{eff.ability_variables_multiplier}%")
        assert eff.create_effect_damage_bonus_for_attack(is_ranged=False, target_traits=tt) is None, \
            "gate IsRangedAttack : le bonus ne doit PAS s'appliquer en melee"
        assert eff.create_effect_damage_bonus_for_attack(is_ranged=None, target_traits=tt) is None, \
            "tri-etat #106 : nature de coup INCONNUE -> IsRangedAttack faux -> pas de bonus"
        assert eff.create_effect_damage_bonus_for_attack(
            is_ranged=True, target_traits=frozenset({"Hero", "Unstoppable"})) is None, \
            "gate HasTrait(target, Mechanical|MkXGravis|TerminatorArmour) : cible non qualifiante"
        assert eff.create_effect_damage_bonus_for_attack(is_ranged=True, target_traits=None) is None, \
            "cible INCONNUE -> pas de bonus (« present != applique »)"

        # -- canal PERCAGE ----------------------------------------------------------------------
        base_ctx = {"owner_id": cid, "att_id": cid, "is_ranged": True, "target_traits": tt}
        assert eff.create_effect_piercing_bonus_for_attack(base_ctx) == want_pierce, \
            f"canal percage != ConfigVar(0x3f=extraPierceRatio)={want_pierce}"
        assert eff.create_effect_piercing_bonus_for_attack({**base_ctx, "att_id": tid}) is None, \
            "gate get_OwnerIsActor : un AUTRE attaquant ne beneficie pas du percage du porteur"
        assert eff.create_effect_piercing_bonus_for_attack({**base_ctx, "is_ranged": False}) is None, \
            "gate IsRangedAttack (percage) : pas de bonus en melee"
        assert eff.create_effect_piercing_bonus_for_attack(
            {**base_ctx, "target_traits": frozenset({"Hero"})}) is None, \
            "gate HasTrait (percage) : cible non qualifiante"
        print(f"\n[HGC] lvl={eff.ability_level} mult={eff.ability_variables_multiplier} "
              f"extraDmg={want_flat} extraPierceRatio={want_pierce} armor({TARGET_VIS})="
              f"{defender_fixed_armor(st, tid)}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


# ==================================================================== (2) replay-diff 4 hypotheses

def test_heavy_grav_cannon_flat_and_pierce_replay_live(live_session, rpc):
    """REPLAY-DIFF : cast LIVE de SentinelDirectives sur une cible Mechanical a ARMURE HAUTE ->
    le per-coup live est BIT-EXACT avec l'offline portant les DEUX canaux, et DIFFERE des trois
    hypotheses degradees (flat seul / percage seul / aucun) -- preuve que chaque canal est bien
    LA (et pas compense par l'autre)."""
    rid, sf, err = _build("777")
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = _approach(rpc, rid, board)
        if placed is None:
            pytest.skip("caster n'a pas atteint la portee de la cible (LOS)")
        cid, tid, moves = placed

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("combatSnapshot/dumpRng indispo")
        st0 = load_state(dv, ob, snap, board=board)
        if st0.get_entity(cid) is None or st0.get_entity(cid).get_component(StatsComponent) is None:
            pytest.skip("caster sans StatsComponent")
        armor = defender_fixed_armor(st0, tid)

        live, dirty = _cast_live(rpc, rid, cid, tid)
        if not live:
            pytest.skip("aucun degat live (LOS/cast no-op)")
        if dirty:
            pytest.skip("coup non propre (crit/block/evade)")

        off = {}
        for hyp in _HYPOTHESES:
            off[hyp], last = _offline(dv, ob, snap, board, s0, cid, tid, moves, hyp)
            assert last.get("ported") is True, f"cast offline non execute (hyp={hyp}) : {last}"
        print(f"\n[HGC-REPLAY] armor({TARGET_VIS})={armor} moved={moves > 0} live={live}")
        for hyp in _HYPOTHESES:
            print(f"[HGC-REPLAY]   off[{hyp:11s}] = {off[hyp]}")

        assert live == off["full"], (
            f"live {live} != offline {off['full']} avec les DEUX canaux HeavyGravCannon actifs -- "
            f"le port diverge du natif (autres hypotheses: {off})")
        # DISCRIMINANCE : sans elle, l'egalite ci-dessus ne prouverait rien (un canal peut etre
        # inerte dans ce scenario -- c'est exactement le cas du percage face a necroOverlord).
        assert off["flat_only"] != off["full"], (
            f"le canal PERCAGE est INERTE ici ({off['flat_only']} == {off['full']}) : le scenario ne "
            f"discrimine pas -- il faut une cible a armure plus haute (cf. probe_hgc_1291 --case band)")
        assert off["pierce_only"] != off["full"], (
            f"le canal DEGAT est inerte ici ({off['pierce_only']} == {off['full']}) : scenario non "
            f"discriminant")
        assert off["none"] != off["full"], "aucun canal ne contribue : scenario non discriminant"
        assert live != off["flat_only"] and live != off["pierce_only"] and live != off["none"], (
            f"le natif matche une hypothese DEGRADEE (live={live}, off={off}) -- un canal du port "
            f"n'existe pas cote natif, ou ne devrait pas s'appliquer sur ce vecteur")

        # (3) MATERIALISATION finale : ARRONDI == live, TRONCATURE != live. Regime FRACTIONNAIRE
        # obtenu uniquement parce que le canal PERCAGE fait gagner la branche `d x pierce%` du
        # plancher (les deux %-list etant vides ici, rien n'a arrondi en amont).
        trunc, _ = _offline(dv, ob, snap, board, s0, cid, tid, moves, "full", force_round=False)
        rnd, _ = _offline(dv, ob, snap, board, s0, cid, tid, moves, "full", force_round=True)
        print(f"[HGC-REPLAY]   materialisation: troncature={trunc} arrondi={rnd}")
        if trunc == rnd:
            pytest.skip(f"tirage a partie fractionnaire < .5 (troncature == arrondi == {rnd}) : "
                        f"la garde de materialisation n'est pas discriminante sur ce tirage")
        assert live == rnd, (
            f"live {live} != ARRONDI {rnd} : l'etage `Fix64.Round(Mul(v, multiplier), AwayFromZero)` de "
            f"`CalculateBaseDamageWithModifiers` (slot 0x10) n'est pas celui du natif sur ce vecteur")
        assert live != trunc, (
            f"live {live} == TRONCATURE {trunc} : le vecteur ability bounds-mode famille ATTACK "
            f"materialiserait par `op_Explicit` -- la campagne HeavyGravCannon (14 casts, "
            f"probe_hgc_1291 --case round) dit l'inverse")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass
