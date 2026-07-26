"""#125 -- REPORT de coups d'une chaine `ChainLeftOverHitsAttackDamage` apres un KILL, et flux
`state.rng` des coups GASPILLES sur le cadavre.

RE (decompile = verite).

  * `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` est une boucle `while (i < hits)` SANS
    aucune sortie anticipee sur la mort de la cible, et les tirages d'un coup
    (`IdunBattle.Core.HitDamage$$GetDamage`, `IdunBattle.Core.Services.DamagePrediction$$RollCritical`,
    `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`) sont consommes dans
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` AVANT la sous-operation 0x42
    (`IdunBattle.Operations.ApplyDamageOperation$$Execute`) : le natif ROULE donc bien TOUS ses coups,
    y compris ceux qui tombent sur un cadavre. Le port aussi (`_run_hits` boucle sur `hits`).
  * `IdunBattle.Operations.ApplyDamageOperation$$Execute` retourne des l'entree quand la cible porte
    `UnitFlag.Overkilled` (8) — apres avoir pose une entree `LeftOverDamages` de flag LITTERAL 1. C'est
    pour cela qu'un coup gaspille N'EMET PLUS d'event des que le cumul depasse le seuil d'overkill :
    **compter les events sous-estime les coups**, et c'est ce qui avait fait lire un report constant.
  * `IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits` compte les
    entrees de flag vrai portant NOTRE `AbilityOrEffect`, et ajoute `extraHits` des que la liste est
    non vide.

CE QUE CE TEST GARDE (oracle = le LIVE, une seule variable = la formule de report) :
  (1) le maillon dont la cible SURVIT au live — le seul dont le per-coup live n'est ni clampe par les
      PV ni tronque par la suppression d'event — est **bit-exact** entre port et natif ;
  (2) CONTRE-CAS integre : la formule d'AVANT #125 (`1 + extraHit` des qu'il y a kill, calibree #116 sur
      le seul regime PV 8000) rend un per-coup DIFFERENT et CONTREDIT le live -> le test est
      discriminant et le fix est bien la variable causale.

Regime choisi : `--hp-target 3000` sur MC1_67 — la 1re cible meurt au coup 2 (k=2, H=6) donc le report
vaut `max(0, 6-2-1) + extraHit = 4` la ou l'ancienne formule rendait 2 ; le 2e maillon meurt a son tour
et le 3e SURVIT (cible discriminante). ASCII only.
"""
from __future__ import annotations

import json

import pytest

import gameconfig as GC
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.behaviours.combat import ChainLeftOverHitsAttackDamage
from engine.runner.abilities.handler import AbilityHandler
from engine.runner.components import HealthComponent
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

ABILITY = 1006                       # MultiThreatEliminator
CASTER_VIS = "necroDestroyer"
A_UNITS = "eldarRanger,astraBullgryn,tauMarksman"
HP_TARGET = 3000


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _live_per_hit(cast):
    """{target -> [Amount par event]}. 1 event de degat portant `Active_Ability_Type == ABILITY` == 1
    coup dont `ApplyDamageOperation` n'a PAS court-circuite (oracle #61) ; les coups tombes sur une
    cible deja `Overkilled` n'apparaissent pas -- d'ou la lecture UNIQUEMENT sur le maillon survivant."""
    out: dict = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                out.setdefault(int(td.get("Target_Id")), []).append(int(td.get("Amount") or 0))
    return out


def _legacy_left_over_hits(atk: dict, extra: int) -> int:
    """Formule d'AVANT #125 (#116) : UNE entree des que l'attaque tue, quel que soit le nombre de coups
    tombes sur le cadavre. Sert de CONTRE-CAS -- si elle donnait le meme resultat que la formule
    portee, la mesure ne serait pas discriminante et le test le dit."""
    per_hit = list(atk.get("per_hit_health") or [])
    hp = int(atk.get("hp_before") or 0)
    if hp <= 0:
        entries = len(per_hit)
    else:
        entries = 0
        for h in per_hit:
            hp -= int(h)
            if hp <= 0:
                entries = 1
                break
    return entries + (int(extra) if entries else 0)


def _capture(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def mkstate():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
            st.rng = rng
        return st
    return mkstate, dec


def _cast_offline(st, cid, tid):
    h = AbilityHandler(st)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(caster_id=int(cid), target_id=int(tid),
                                                      ability_type=ABILITY))
    return (h.last or {}).get("chain") or []


def _from_here(rpc, rid, cid):
    """Cibles LEGALES SANS bouger (`abilityTargets(...).fromHere`) -- JAMAIS `targets` (#111)."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": int(cid), "abilityType": ABILITY}, 120)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == ABILITY), {})
    return [int(x.get("targetId")) for x in (ab.get("fromHere") or [])]


def _my_turn(rpc, rid):
    for _ in range(20):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        c = next((u for u in (dv.get("units") or [])
                  if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        if c is None:
            return None, None
        if dv.get("currentPlayer") == c.get("owner"):
            return c, dv
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _drive_chain(rpc, rid, board, c, dv):
    """DRIVE la geometrie de la CHAINE (doctrine : on deplace les unites pour realiser la condition
    testee, jamais « bloque par la geometrie de spawn »). Le selecteur de cible suivante est
    `Unobscured(Enemies(SurroundingUnits(casterTile, range))) INTER AdjacentUnits(derniere cible)` :
    il faut donc une ligne d'ennemis chacun ADJACENT au precedent ET dans le disque `range` du caster.

    ORDRE IMPOSE : `astraBullgryn` (aucun malus de coups) puis `eldarRanger` (`LightCover`, -2) puis
    `tauMarksman` (`Camouflage`, -1). C'est cet ordre qui rend le DERNIER maillon SURVIVANT (1 seul
    coup applique apres le malus) -- le seul dont le per-coup live est directement comparable."""
    import hexgeo
    order = ["astraBullgryn", "eldarRanger", "tauMarksman"]
    foes = {u.get("visualId"): int(u["id"]) for u in (dv.get("units") or [])
            if u.get("alive") and u.get("owner") != c.get("owner")}
    if any(v not in foes for v in order):
        return None
    cpos = (c["pos"]["col"], c["pos"]["row"])
    ctile = board.id_at(*cpos)
    mine = {board.id_at(u["pos"]["col"], u["pos"]["row"])
            for u in (dv.get("units") or [])
            if u.get("alive") and u.get("owner") == c.get("owner") and u.get("pos")}

    def free(t, used):
        return (board.walkable(t) and t not in used and t not in mine
                and hexgeo.distance(board.coord(t), cpos) <= 2)

    for n1 in board.neighbours(ctile):
        if not free(n1, {ctile}):
            continue
        for n2 in board.neighbours(n1):
            if not free(n2, {ctile, n1}):
                continue
            for n3 in board.neighbours(n2):
                if not free(n3, {ctile, n1, n2}):
                    continue
                for vis, t in zip(order, (n1, n2, n3)):
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": foes[vis],
                        "to": {"col": board.coord(t)[0], "row": board.coord(t)[1]}}}, 60)
                fh = _from_here(rpc, rid, int(c["id"]))
                if foes[order[0]] in fh:
                    return int(c["id"]), foes[order[0]]
                return None
    return None


@pytest.mark.parametrize("seed", ["4242", "777"])
def test_chain_leftover_hits_after_kill_live(live_session, rpc, build_runner, seed):
    extra = int(GC.ability("MultiThreatEliminator")["constants"]["extraHit"])
    rid = build_runner(seed, board="MC1_67",
                       extra=["--rank", "17", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
                              "--hp-target", str(HP_TARGET), "--hp-player", "60000",
                              "--crit", "0,0"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    c, dv = _my_turn(rpc, rid)
    if c is None:
        pytest.skip("tour du caster inatteignable")
    got_ct = _drive_chain(rpc, rid, Board(bg["tiles"], adjacency="evenq"), c, dv)
    if got_ct is None:
        pytest.skip("geometrie de chaine non realisable sur ce board")
    cid, tid = got_ct

    mkstate, _dec = _capture(rpc, rid)
    hp0 = {int(eid): (e.get_component(HealthComponent).hp
                      if e.get_component(HealthComponent) else None)
           for eid, e in mkstate().entities.items()}
    chain = _cast_offline(mkstate(), cid, tid)

    keep = ChainLeftOverHitsAttackDamage.__dict__["_left_over_hits"]
    ChainLeftOverHitsAttackDamage._left_over_hits = staticmethod(_legacy_left_over_hits)
    try:
        legacy = _cast_offline(mkstate(), cid, tid)
    finally:
        ChainLeftOverHitsAttackDamage._left_over_hits = keep

    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": tid, "abilityType": ABILITY},
        "captureEvents": True}, 120)
    assert _ok(cast), str(cast)[:200]
    live = _live_per_hit(cast)
    assert live, "aucun event de degat live"

    # Le(s) maillon(s) DISCRIMINANT(S) : cible SURVIVANTE au live (aucun event a 0 -> aucun coup
    # gaspille, et somme < PV de depart -> aucun clamp) => le per-coup live est directement comparable.
    surv = [t for t, lv in live.items()
            if all(lv) and hp0.get(t) is not None and sum(lv) < hp0[t]]
    if not surv:
        pytest.skip(f"aucun maillon a cible survivante (live={live}) -- regime non discriminant")
    got = {int(c["target"]): list(c["per_hit"]) for c in chain}
    leg = {int(c["target"]): list(c["per_hit"]) for c in legacy}
    for t in surv:
        assert got.get(t) == live[t], (f"maillon u{t} : port={got.get(t)} live={live[t]} "
                                       f"(chaine portee={chain})")
    # CONTRE-CAS : l'ancienne formule doit CONTREDIRE le live sur ce meme maillon.
    assert any(leg.get(t) != live[t] for t in surv), (
        f"mesure NON discriminante : l'ancienne formule (1+extraHit={1 + extra}) rend le meme "
        f"per-coup que la nouvelle sur {surv} -- il ne faut rien en conclure (legacy={legacy})")
