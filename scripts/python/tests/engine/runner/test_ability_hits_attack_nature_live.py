"""#122 -- canal de COUPS d'une attaque d'ABILITY : la nature du coup est DECLAREE, pas positionnelle.

RE (decompile = verite). `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` delegue au slot
d'interface 0xb5 -> `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`, qui ouvre par

    IsMeleeAttack = IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack(<tranche AttackData>, ...)

et cette facade ne calcule RIEN : elle resout le slot d'interface 2 de la `BattleQuery` et delegue a
`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, qui part de
`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType(<AbilityOrEffect du coup>)` :

    rangeType 0 (absent) -> melee FALSE et ranged FALSE      2 (Ranged) -> ranged TRUE
    rangeType 1 (Melee)  -> melee TRUE                       3 (Normal) -> AreUnitsInMelee (POSITIONNEL)

=> pour une ability qui declare `attackRangeType = Ranged`, `IsRangedAttack` est VRAI **meme au
contact**. Le trigger `OwnerIsTarget & IsRangedAttack` de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack`
mord donc sur une cible ADJACENTE au caster.

CE QUE CE TEST PROUVE (une seule variable : le predicat de nature ; meme etat, meme RNG) :
  (1) le nb de coups REELLEMENT applique par le natif == celui du port (oracle = le LIVE) ;
  (2) le modele POSITIONNEL (l'ancien calcul, `_is_ranged_position` = adjacence) rend un nombre
      DIFFERENT et CONTREDIT le live -> le test est discriminant et le fix est la variable causale.

GEOMETRIE DRIVEE : la cible Camouflage est posee sur un VOISIN du caster (dist 1) -- c'est la seule
configuration ou les deux modeles divergent. Les autres ennemis sont parques loin (pas d'aura, pas de
maillon suivant). `--hp-target` haut -> aucun kill -> chaine d'UN maillon.

Lit l'etat LIVE (aucune tuile/RVA/valeur hardcodee) ; les magnitudes viennent du gameconfig. ASCII only.
"""
from __future__ import annotations

import json

import pytest

import gameconfig as GC
import hexgeo
from engine.entities.effects.magnitude import trait_var
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.necrons import MultiThreatEliminatorAbility
from engine.runner.components import PositionComponent
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

ABILITY = 1006                       # MultiThreatEliminator
CASTER_VIS = "necroDestroyer"
CAMO_VIS = "tauMarksman"             # porteur du trait Camouflage (effet 1134)
CAMO_EFFECT = 1134


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _find(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _effect_types(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return {int(e.get("effectType") or -1) for e in ((u or {}).get("effects") or [])}


def _live_per_hit(cast, tid):
    """1 event de degat portant `Active_Ability_Type == ABILITY` == 1 coup APPLIQUE (oracle #61)."""
    out = []
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY \
                    and td.get("Target_Id") == tid:
                out.append(td.get("Amount"))
    return out


def _place(rpc, rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 60)


def _drive(rpc, rid, board):
    """Amene le tour du caster, parque les ennemis LOIN, colle la cible Camouflage sur un VOISIN du
    caster. Rend (cid, tid) ou None."""
    def dview():
        return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

    myp = None
    for _ in range(20):
        dv = dview()
        c = _find(dv, CASTER_VIS)
        if c is None:
            return None
        myp = c.get("owner")
        if dv.get("currentPlayer") == myp:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    else:
        return None

    dv = dview()
    c, tgt = _find(dv, CASTER_VIS), _find(dv, CAMO_VIS)
    if c is None or tgt is None:
        return None
    cpos = (c["pos"]["col"], c["pos"]["row"])
    ctile = board.id_at(*cpos)
    # les AUTRES ennemis loin : pas d'aura de coups, pas de maillon suivant possible
    far = [t for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), cpos) > 6]
    it = iter(far)
    for e in (dv.get("units") or []):
        if e.get("owner") == myp or not e.get("alive") or e["id"] == tgt["id"]:
            continue
        ft = next(it, None)
        if ft is None:
            break
        _place(rpc, rid, e["id"], *board.coord(ft))
    nbrs = [n for n in board.neighbours(ctile) if board.walkable(n)]
    if not nbrs:
        return None
    _place(rpc, rid, tgt["id"], *board.coord(nbrs[0]))
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": c["id"], "abilityType": ABILITY}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == ABILITY), {})
    fh = [x.get("targetId") for x in (ab.get("fromHere") or [])]
    if tgt["id"] not in fh:
        return None
    return c["id"], tgt["id"]


@pytest.mark.parametrize("seed,board_id", [("4242", "MC1_67"), ("777", "C3_01")])
def test_ability_hits_channel_uses_declared_attack_nature_live(live_session, rpc, build_runner,
                                                               seed, board_id):
    """Cible `Camouflage_HitReduction` ADJACENTE au caster, ability declaree `Ranged` : le natif
    SOUSTRAIT le malus (nature DECLAREE) ; le modele positionnel ne le soustrait pas et contredit le
    live. Deux couples (seed, board) : l'invariant ne depend ni du tirage ni de la geometrie du
    plateau, seulement du couple (nature declaree, effet porte)."""
    cfg = GC.ability("MultiThreatEliminator") or {}
    if cfg.get("attackRangeType") != "Ranged":
        pytest.skip(f"premisse changee : attackRangeType={cfg.get('attackRangeType')!r} != 'Ranged'")
    reduction = trait_var("Camouflage", "camouflageHitReduction_1")
    assert reduction, "oracle absent : traitVariables.camouflageHitReduction_1 introuvable"

    rid = build_runner(seed, board=board_id,
                       extra=["--p-units", CASTER_VIS,
                              "--a-units", f"{CAMO_VIS},eldarRanger",
                              "--hp-target", "90000", "--crit", "0,0", "--no-ai"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    placed = _drive(rpc, rid, board)
    if placed is None:
        pytest.skip("geometrie (cible Camouflage adjacente + cast legal) non atteinte")
    cid, tid = placed

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if CAMO_EFFECT not in _effect_types(dv, tid):
        pytest.skip(f"la cible u{tid} ne porte pas l'effet {CAMO_EFFECT} (Camouflage_HitReduction)")
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    st_probe = load_state(dv, ob, snap, board=board)
    cp = st_probe.get_entity(cid).get_component(PositionComponent)
    tp = st_probe.get_entity(tid).get_component(PositionComponent)
    dist = hexgeo.distance((cp.col, cp.row), (tp.col, tp.row))
    assert dist == 1, f"setup NON discriminant : cible a dist={dist} (attendu 1, le seul cas ou les " \
                      f"deux modeles de nature divergent)"

    # --- LIVE ---
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
        "captureEvents": True}, 120)
    live_ph = _live_per_hit(cast, tid) if _ok(cast) else []
    if not live_ph:
        pytest.skip(f"aucun degat live (cast={str(cast)[:160]})")

    # --- PORT (nature DECLAREE) ---
    st = load_state(dv, ob, snap, board=board); st.rng = _seed_rng(s0)
    chain = (MultiThreatEliminatorAbility().execute_behaviour(st, cid, tid) or {}).get("chain") or []
    assert chain, "le port n'a produit aucun maillon"
    applied = chain[0]["applied_hits"]

    # --- CONTRE-CAS (ancien predicat POSITIONNEL) : meme etat, meme RNG ---
    # #169 : `damage_ops` est un PACKAGE ; le SEUL consommateur de `hits_channel_is_melee` est
    # `execute_ability_attack`, qui le resout dans les globals de `damage_ops.ability`. Patcher le
    # `__init__` du package (ou `_channel`, deja importe par valeur) serait un NO-OP SILENCIEUX --
    # le contre-cas rendrait la MEME chaine que le port et l'assertion `legacy != applied`
    # ci-dessous (garde de discrimination) l'attraperait.
    import engine.runner.operations.damage_ops.ability as dops
    from engine.runner.operations.triggers.base import _is_ranged_position
    keep = dops.hits_channel_is_melee
    dops.hits_channel_is_melee = lambda state, a, t, is_melee: not _is_ranged_position(state, a, t)
    try:
        st_leg = load_state(dv, ob, snap, board=board); st_leg.rng = _seed_rng(s0)
        leg_chain = (MultiThreatEliminatorAbility().execute_behaviour(st_leg, cid, tid)
                     or {}).get("chain") or []
    finally:
        dops.hits_channel_is_melee = keep
    legacy = (leg_chain[0] if leg_chain else {}).get("applied_hits")

    print(f"\n[#122] dist={dist} live={len(live_ph)} coups {live_ph} | port(declare)={applied} "
          f"{chain[0].get('per_hit')} | legacy(positionnel)={legacy} "
          f"| camouflageHitReduction_1={reduction}")

    assert legacy != applied, (
        f"setup NON discriminant : les deux modeles de nature rendent {applied} coups -- ce test ne "
        f"peut pas rougir (verifier que la cible porte bien Camouflage et qu'elle est adjacente)")
    assert len(live_ph) == applied, (
        f"le port applique {applied} coups, le natif {len(live_ph)} -- la nature du coup du canal de "
        f"coups ne suit pas `BattleQuery$$IsMeleeAttack` (attackRangeType declare)")
    assert len(live_ph) != legacy, (
        f"le natif applique {len(live_ph)} coups == le modele POSITIONNEL ({legacy}) : la mesure ne "
        f"soutient plus le verdict #122, RE a refaire avant de toucher au port")
    assert applied < legacy, (
        f"la nature declaree devrait RETIRER des coups (Camouflage ranged) : {applied} >= {legacy}")
