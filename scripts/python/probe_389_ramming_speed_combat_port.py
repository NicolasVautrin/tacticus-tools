#!/usr/bin/env python
"""Probe #389 (residu `#383-r1`) -- la face COMBAT de `RammingSpeed` (1059) : PORT contre NATIF.

CE QU'IL MESURE
---------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$ExecuteBehaviour` porte QUATRE
observables, et le probe les confronte TOUS sur le MEME etat + le MEME rng :

    ifMove = If( NOT IsAdjacent(Caster@0x48, Target@0x60, 3),
                 MoveUnit(Caster@0x48, GetTileToMoveTo(), <options ZERO>) )
    addEff = AddEffect( 0x44a = 1098 RammingSpeed_ExtraExplode, AbilityStateReference,
                        source = Owner@0x30, targets = Owner@0x30, <options ZERO> )
    atk1   = AttackWithAttackDamage( Owner@0x30, Target@0x60, RandomAmount(minDmg, maxDmg),
                                     GetDamageProfile(), hits = GetNumberConstant(0x2f), ... )
    atk2   = AttackWithAttackDamage( Owner@0x30, Owner@0x30,  <MEME amount>, <MEME profil>,
                                     hits = GetNumberConstant(0x32), ... )
    Execute( (ifMove + addEff) + If(<DSLTriggers+0x20>, atk1 + atk2) )

  1. **TUILE** -- la position d'arrivee du caster apres le cast (deja confrontee 2/2 par `#353-r1`
     cote NATIF ; ici c'est le PORT qui doit reellement deplacer l'unite).
  2. **COUPS SUR LA CIBLE** -- la liste per-hit, BIT-EXACTE (meme rng dumpe avant le cast).
  3. **COUPS SUR SOI** -- le contrecoup `nrOfHits_2` sur le CASTER lui-meme (2e attaque).
  4. **EFFET 1098** -- pose sur le caster (c'est le SEUL poseur de cet effet dans tout le jeu,
     donc c'est aussi ce qui rendra confrontable la branche VRAIE du `ConditionalAmount` de
     `ExplodesAbility$$GetDamage`, residu ouvert de `#383`).

`<DSLTriggers+0x20>` = `OwnerIsAlive` (`IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`),
nomme par #389 -- cf. le docstring de `engine/entities/triggers.py::OwnerIsAlive`. Il est VRAI sur
tout montage jouable ici (le caster ne peut mourir pendant le move que par un tir reactif) : sa
garde ROUGE est OFFLINE (`tests/engine/runner/test_389_ramming_speed_combat_offline.py`).

MONTAGE
-------
Herite de `probe_353r1` (greffe `orksKillaKan <- 1059`, board CHOISI, `drive_to` + `ensure_turn`) :
le caster doit etre NON adjacent a la cible (sinon le `If` court-circuite le move) et ne pas avoir
bouge (sinon `GetDynamicInvalidTargetReason` rend `0x10`). PV eleves des deux camps : le contrecoup
ne doit tuer personne, sinon les listes per-hit sont tronquees par la mort.

Le probe REFUSE de conclure (`BRAS NON DISCRIMINANT`) plutot que de mesurer degrade.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_389_ramming_speed_combat_port.py
    python probe_389_ramming_speed_combat_port.py --board C1_20 --seed 38901
    python probe_389_ramming_speed_combat_port.py --mutate no-self-attack     # DOIT rougir
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from probe_353_ramming_speed_prediction import build_grafted_seed_bc         # noqa: E402
from probe_353r1_ramming_speed_charge_tile import (                          # noqa: E402
    ENEMY2, FILLER_P, GRAFT, VICTIM, MOVE_RANGE, _ids, _pos, _view,
    controlled_by_current_player, drive_to, ensure_turn)

ABILITY = 1059
ABILITY_NAME = "RammingSpeed"
EXTRA_EXPLODE = 1098            # EffectType.RammingSpeed_ExtraExplode (0x44a)
BOARD = "MC1_67"
HP = 900000                     # ni la cible ni le caster ne doivent mourir : listes per-hit ENTIERES

MUTATIONS = ("none", "no-move", "no-self-attack", "no-effect", "swap-hits", "gate-closed",
             "self-attack-on-target", "keep-effect")


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed_bc: Path, seed: int, board: str, hp_player: int = HP) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17",
           "--seed-bc", str(seed_bc),
           "--p-units", "%s,%s" % (GRAFT, FILLER_P),
           "--a-units", "%s,%s" % (VICTIM, ENEMY2),
           "--hp-player", str(int(hp_player)), "--hp-target", str(HP), "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _state_builder(sid, rid, board):
    """Capture l'etat AVANT le cast (`decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng`)
    et rend une FABRIQUE d'etats rejouables -- meme recette que `probe_226r_skystrike_spread`, seul
    montage du depot qui atteint le bit-exact sur un cast d'ability."""
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    rng0 = _r(sid, "dumpRng", {"runnerId": rid}, 40)

    def build():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"])
            r.mti = rng0["mti"]
            st.rng = r
        return st
    return build, dv, bool(isinstance(rng0, dict) and rng0.get("mt"))


def _load_board(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    return Board(bg["tiles"], adjacency="evenq")


def _effects_of(dv, uid) -> list:
    for u in (dv.get("units") or []):
        if int(u.get("id")) == int(uid):
            return sorted(int(e.get("effectType") or -1) for e in (u.get("effects") or []))
    return []


def _effects_live(sid, rid, uid) -> list:
    """Effets du caster sur le canal `includeInactive` -- le SEUL comparable a `State.effects.by_unit`
    cote port (`snapshot.decision_view_seed_body` : `decisionView` par DEFAUT laisse tomber les effets
    INERTES, `includeInactive` = le canal STRUCTURE). Comparer les deux canaux croises produirait un
    faux ecart : mesure #389, `RammingSpeed_ExtraExplode` (1098) est POSE et n'apparait PAS dans le
    canal par defaut."""
    from engine.runner.snapshot import decision_view_seed_body
    dv = _r(sid, "decisionView", decision_view_seed_body(rid, allAbilities=True, maxRank=32), 180)
    return _effects_of(dv, uid)


def _scan_geometry(state, board, ids, max_targets: int = 24):
    """Cherche une geometrie ou (a) le caster est a 2..MOVE_RANGE de la cible (donc le `If` ARME le
    move), (b) la cible a au moins une tuile ring-1 libre (sinon `GetTileToMoveTo` ne designe rien et
    le gate de ciblage refuse), (c) l'allie est LOIN (il ne doit pas occuper une candidate).

    On MUTE l'etat OFFLINE pour tester, puis on restaure -- jamais de geometrie choisie sur une
    hypothese de terrain."""
    from engine.runner.abilities.orks import ramming_speed_tile_to_move_to
    from engine.runner.components import PositionComponent
    pcs = {v: state.get_entity(ids[v]).get_component(PositionComponent)
           for v in (GRAFT, FILLER_P, VICTIM, ENEMY2)}
    keep = {v: (pc.col, pc.row) for v, pc in pcs.items()}
    walk = sorted(board.coord(t) for t in board.by_id if board.walkable(t))
    six = sorted((t for t in board.by_id
                  if board.walkable(t) and len(board.neighbours(t)) == 6
                  and all(board.walkable(n) for n in board.neighbours(t))),
                 key=lambda t: (hexgeo.distance(board.coord(t), keep[VICTIM]), t))
    try:
        for tt in six[:max_targets]:
            tp = board.coord(tt)
            ring = [board.coord(n) for n in board.neighbours_native(tt)]
            if len(ring) != 6:
                continue
            ally = next((p for p in reversed(walk)
                         if all(hexgeo.distance(p, q) > 1 for q in ring + [tp])), None)
            if ally is None:
                continue
            pcs[VICTIM].col, pcs[VICTIM].row = tp
            pcs[FILLER_P].col, pcs[FILLER_P].row = ally
            casters = sorted((p for p in walk
                              if p != ally and p not in ring
                              and 2 <= hexgeo.distance(p, tp) <= MOVE_RANGE),
                             key=lambda p: (hexgeo.distance(p, keep[GRAFT]), p))
            for e2 in sorted(ring, key=lambda p: hexgeo.distance(p, keep[ENEMY2])):
                pcs[ENEMY2].col, pcs[ENEMY2].row = e2
                for cp in casters[:8]:
                    pcs[GRAFT].col, pcs[GRAFT].row = cp
                    dest = ramming_speed_tile_to_move_to(state, ids[GRAFT], ids[VICTIM], MOVE_RANGE)
                    if dest is None or tuple(dest) == tuple(cp):
                        continue
                    return tp, e2, cp, ally
    finally:
        for v, pc in pcs.items():
            pc.col, pc.row = keep[v]
    return None


class _Never:
    """Trigger MUTE : rend toujours FAUX (bras `gate-closed`)."""
    def evaluate(self, ctx):
        return False

    def should_trigger(self, ctx):
        return False


def _apply_mutation(mutate: str):
    """Pose la mutation sur le MODULE `runner.abilities.orks` et rend le restaurateur. Toutes portent
    sur des symboles resolus AU NIVEAU MODULE par `ramming_speed_tree`, donc un patch d'attribut
    suffit -- aucune copie de code moteur dans le probe."""
    from engine.runner.abilities import orks as O
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    saved = {k: getattr(O, k) for k in ("ramming_speed_tree", "MoveUnit", "AddEffect",
                                        "OwnerIsAlive", "op_add")}
    saved_reg = list(EFFECT_TRIGGERS.get(EXTRA_EXPLODE) or [])

    def _restore():
        for k, v in saved.items():
            setattr(O, k, v)
        EFFECT_TRIGGERS[EXTRA_EXPLODE] = saved_reg

    if mutate == "none":
        return _restore
    _orig = saved["ramming_speed_tree"]
    if mutate == "keep-effect":
        # `#389-r1`, CONTRE-EPREUVE DU RETRAIT : l'entree de registre est retiree, donc le
        # `On(PhaseEnd)` de `RammingSpeed_ExtraExplodeEffect` n'existe plus cote port et 1098 devient
        # PERMANENT (`AddEffect` options ZERO -> `remaining = 0`) -- l'etat d'AVANT le fix. Elle ne
        # DISCRIMINE que sur un bras ou le caster SURVIT (sinon le cliquet est desarme, cf. le
        # residu `KillUnitOperation$$RemoveEffects`).
        EFFECT_TRIGGERS[EXTRA_EXPLODE] = []
        return _restore
    if mutate == "no-move":
        # `MoveUnit` neutralise : le caster reste sur place -> la TUILE diverge.
        class _NoMove:
            def __init__(self, *a, **k):
                pass

            def execute(self, entities, ectx):
                from engine.dsl.effects import OperationResult
                return OperationResult.ok()
        O.MoveUnit = _NoMove
    elif mutate == "no-effect":
        class _NoEffect:
            def __init__(self, *a, **k):
                pass

            def execute(self, entities, ectx):
                from engine.dsl.effects import OperationResult
                return OperationResult.ok()
        O.AddEffect = _NoEffect
    elif mutate == "no-self-attack":
        # 2e `AttackWithAttackDamage` (celui dont la CIBLE est `Owner@0x30`) supprime = l'etat
        # d'AVANT #389 pour ce volet : le contrecoup n'existe pas.
        def _no_self(dest, profile):
            tree = _orig(dest, profile)
            gated = tree.right                              # If(OwnerIsAlive, atk1 + atk2)
            gated.then = gated.then.left                    # -> atk1 seul
            return tree
        O.ramming_speed_tree = _no_self
    elif mutate == "swap-hits":
        # `nrOfHits_2` (contrecoup) lu comme `nrOfHits` : 2 coups deviennent 4.
        def _swap(dest, profile):
            tree = _orig(dest, profile)
            tree.right.then.right.hits_key = "nrOfHits"
            return tree
        O.ramming_speed_tree = _swap
    elif mutate == "gate-closed":
        # `<DSLTriggers+0x20>` force a FAUX : les deux attaques disparaissent.
        def _closed(dest, profile):
            tree = _orig(dest, profile)
            tree.right.cond = _Never()
            return tree
        O.ramming_speed_tree = _closed
    elif mutate == "self-attack-on-target":
        # Le contrecoup dirige sur la CIBLE au lieu du CASTER (`Owner@0x30` lu comme `Target@0x60`).
        def _on_target(dest, profile):
            from engine.entities.selectors.accessors import Target
            tree = _orig(dest, profile)
            tree.right.then.right.target_sel = Target()
            return tree
        O.ramming_speed_tree = _on_target
    else:
        raise SystemExit("mutation inconnue : %r" % mutate)
    return _restore


def _port_cast(build, cid, tid, mutate: str) -> dict:
    """Rejoue le cast OFFLINE par le CHEMIN REEL, sur l'etat + le rng captures AVANT le cast natif.

    ⚠ `#389-r1` : le chemin est `Runner.apply(ActiveAbilityMessage)`, PAS `AbilityHandler.
    visit_ActiveAbilityMessage` appele nu. Le handler nu execute bien l'arbre (meme tuile, memes
    coups -- verifie), mais il court-circuite la BORNE DE PHASE : `Runner.apply` est le mirror de
    `IdunBattle.Messages.InputMessageProcessor$$RunPhase(..., isInternalPhase: false)`, dont la
    cloture (`Core.Services.OperationProcessor$$EndPhase` -> `IdunBattle.Operations.
    EndPhaseOperation$$Execute`) publie `EventTriggerType.PhaseEnd` -- l'evenement qui RETIRE 1098.
    Confronter le port par le handler nu rendrait donc `effect_persists_port_only` VRAI par
    construction, quel que soit l'etat du port. `AbilityHandler` est le SEUL post-handler a porter un
    `visit_ActiveAbilityMessage` (verifie) : passer par le runner n'execute pas l'arbre deux fois."""
    from engine.runner.components import PositionComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    restore = _apply_mutation(mutate)
    try:
        st = build()
        rr = Runner(st).install_default_handlers(20)
        rr.apply(ActiveAbilityMessage(
            caster_id=int(cid), target_id=int(tid), ability_type=ABILITY))
        res = rr.ability_handler.last or {}
        e = st.get_entity(int(cid))
        pc = e.get_component(PositionComponent) if e is not None else None
        eff = [int(x.effect_type) for x in (st.effects.by_unit.get(int(cid)) or [])
               if not x.consumed]
        add = res.get("add_effect") or {}
        return {"raw": res, "tile": [pc.col, pc.row] if pc is not None else None,
                "hits_target": list(((res.get("attack_target") or {}).get("attack")
                                     or {}).get("per_hit") or []),
                "hits_self": list(((res.get("attack_self") or {}).get("attack")
                                   or {}).get("per_hit") or []),
                # POSE de l'effet (le leaf `AddEffect`) -- distincte de sa PRESENCE finale, que le
                # natif ET le port (depuis `#389-r1`) ramenent tous deux a zero a la cloture de phase.
                # Les deux observables sont confrontes separement (`effect_match` / `effect_removed`).
                "effect_posed": (int(add.get("effect_type") or -1) == EXTRA_EXPLODE
                                 and int(add.get("target") or -1) == int(cid)
                                 and bool(add.get("placed"))),
                "effects_caster": sorted(eff),
                "hp": _hp_offline(st)}
    finally:
        restore()


def _hp_offline(st) -> dict:
    """{unitId: pv} depuis le `State` du port (unites MORTES incluses, a 0)."""
    from engine.runner.components import HealthComponent
    out: dict = {}
    for eid, e in st.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None:
            out[int(eid)] = int(max(0, hc.hp))
    return out


def _as_reported(rolled: list, hp: int) -> list:
    """Convertit la serie de coups ROULES du port en la serie que le NATIF RAPPORTE.

    RESIDU GENERIQUE (pas propre a 1059) mesure ici : quand un coup TUE le defenseur, le tag
    `Amount` natif porte le degat REELLEMENT applique (borne par les PV restants) et la serie
    S'ARRETE, alors que le port continue la boucle et rapporte le montant BRUT. L'ETAT est le meme
    des deux cotes (`HealthComponent.reduce` borne a 0) -- seule la TRACE differe. Cette conversion
    est une transformation DEFINIE (aucun degre de liberte), pas un ajustement : elle ne peut pas
    faire coincider deux series de tirages differentes."""
    out: list = []
    rem = int(hp)
    for v in rolled:
        if rem <= 0:
            break
        a = min(int(v), rem)
        out.append(a)
        rem -= a
    return out


def _hp_live(sid, rid) -> dict:
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    return {int(u["id"]): int(u.get("hp") or 0) for u in (dv.get("units") or [])}


def _live_cast(sid, rid, cid, tid) -> dict:
    """Cast NATIF avec `captureEvents` : coups ventiles par `Target_Id` (tags `Amount` +
    `Active_Ability_Type == 1059`), position d'arrivee du caster, effets post-cast."""
    res = _r(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": ABILITY}}, 150) or {}
    act0 = (res.get("actions") or [{}])[0]
    by_target: dict = {}
    posed = False
    for a in (res.get("actions") or []):
        for ev in (a.get("events") or []):
            td = ev.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            # POSE de l'effet : le SEUL tag qui porte l'ability SOURCE d'un effet cree.
            if (td.get("Effect_SourceActiveAbility") == ABILITY
                    and int(td.get("Effect_SourceId") or -1) == int(cid)):
                posed = True
            if "Amount" not in td or td.get("Active_Ability_Type") != ABILITY:
                continue
            by_target.setdefault(int(td.get("Target_Id")), []).append(td.get("Amount"))
    after = None
    for u in (res.get("units") or []):
        if int(u.get("squadId", -1)) == int(cid):
            p = u.get("pos") or {}
            after = [p.get("col"), p.get("row")]
            break
    return {"error": act0.get("error"), "mutated": bool(act0.get("mutated")),
            "tile": after, "by_target": by_target, "effect_posed": posed}


def run(seed: int = 38900, board: str = BOARD, mutate: str = "none", hp_player: int = HP,
        verbose: bool = True) -> dict:
    sid = _resolve_session()
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    sf = logs / ("p389-%s.json" % tag)
    bcf = logs / ("p389-seed-bc-%s.json" % tag)
    out: dict = {"seed": seed, "board": board, "mutation": mutate, "hp_player": hp_player}
    out["graft"] = build_grafted_seed_bc(bcf)
    rid = None
    try:
        rid = _build(sf, bcf, seed, board, hp_player)
        out["runner"] = rid
        board_obj = _load_board(sid, rid)
        build0, dv0, _ = _state_builder(sid, rid, board_obj)
        ids = _ids(dv0)
        geo = _scan_geometry(build0(), board_obj, ids)
        if geo is None:
            out["error"] = ("aucune geometrie (caster a 2..%d de la cible, ring-1 libre, allie "
                            "ecarte) sur %s -- rien n'est joue" % (MOVE_RANGE, board))
            return out
        tp, e2, cp, ap = geo
        out["geometry"] = {"target": list(tp), "enemy2": list(e2), "caster": list(cp),
                           "ally": list(ap)}
        wanted = {ids[VICTIM]: tp, ids[ENEMY2]: e2, ids[GRAFT]: cp, ids[FILLER_P]: ap}
        if not drive_to(sid, rid, wanted):
            dv = _view(sid, rid)
            out["error"] = "drive KO : voulu %s obtenu %s" % (
                {k: list(v) for k, v in wanted.items()}, {u: _pos(dv, u) for u in wanted})
            return out
        out["turn_given"] = ensure_turn(sid, rid, ids[GRAFT])
        cid, tid = ids[GRAFT], ids[VICTIM]
        out["caster_id"], out["target_id"] = cid, tid
        ctrl = controlled_by_current_player(sid, rid)
        out["caster_has_turn"] = (int(cid) in ctrl) if ctrl else None

        # --- etat + rng CAPTURES JUSTE AVANT le cast (c'est ce qui rend le bit-exact possible)
        build, dv, has_rng = _state_builder(sid, rid, board_obj)
        out["rng_captured"] = has_rng
        out["effects_before"] = _effects_live(sid, rid, cid)

        hp_before = _hp_live(sid, rid)
        port = _port_cast(build, cid, tid, mutate)
        out["port"] = {k: port[k] for k in ("tile", "hits_target", "hits_self", "effects_caster",
                                            "effect_posed")}

        live = _live_cast(sid, rid, cid, tid)
        out["live_error"], out["live_mutated"] = live["error"], live["mutated"]
        out["live_tile"] = live["tile"]
        out["live_hits_target"] = list(live["by_target"].get(int(tid)) or [])
        out["live_hits_self"] = list(live["by_target"].get(int(cid)) or [])
        out["live_effect_posed"] = bool(live["effect_posed"])
        out["live_effects_caster"] = _effects_live(sid, rid, cid)

        hp_live = _hp_live(sid, rid)
        ids_common = sorted(set(port["hp"]) & set(hp_live))
        out["hp_before"] = {str(u): hp_before.get(u) for u in ids_common}
        out["hp_port"] = {str(u): port["hp"][u] for u in ids_common}
        out["hp_live"] = {str(u): hp_live[u] for u in ids_common}
        out["hp_match"] = all(port["hp"][u] == hp_live[u] for u in ids_common)
        out["caster_died"] = (hp_live.get(int(cid), 1) <= 0)

        out["tile_match"] = (port["tile"] is not None and live["tile"] is not None
                             and list(port["tile"]) == list(live["tile"]))
        out["port_hits_target_reported"] = _as_reported(port["hits_target"],
                                                        hp_before.get(int(tid), 0))
        out["port_hits_self_reported"] = _as_reported(port["hits_self"], hp_before.get(int(cid), 0))
        out["hits_target_match"] = (out["port_hits_target_reported"] == out["live_hits_target"])
        out["hits_self_match"] = (out["port_hits_self_reported"] == out["live_hits_self"])
        # L'`AddEffect` se confronte sur DEUX observables DISJOINTS :
        #  (a) la POSE -- le natif CREE l'entite d'effet (tag `Effect_SourceActiveAbility = 1059`) ;
        #  (b) la PRESENCE FINALE -- le natif la RETIRE avant la fin du meme `applyAction`, par le
        #      `On(PhaseEnd)` de `RammingSpeed_ExtraExplodeEffect` (`#389-r1`, RE close). Depuis le
        #      port du retrait, les deux cotes doivent etre VIDES ; `effect_persists_port_only`
        #      est donc devenu un CLIQUET (il DOIT valoir False) et entre dans `match`.
        # ⚠ CANAL : `live_effects_caster` vient de `decisionView` **`includeInactive`** -- le seul
        # comparable a `State.effects.by_unit`. Le canal par DEFAUT laisse tomber les effets INERTES
        # et ferait confondre << retire >> avec << desactive >>.
        out["effect_match"] = (bool(port["effect_posed"]) == bool(live["effect_posed"]))
        out["effect_persists_port_only"] = (EXTRA_EXPLODE in port["effects_caster"]
                                            and EXTRA_EXPLODE not in out["live_effects_caster"])
        out["effect_removed_both"] = (EXTRA_EXPLODE not in port["effects_caster"]
                                      and EXTRA_EXPLODE not in out["live_effects_caster"])
        # `#389-r2` -- CLIQUET RE-ARME SUR BRAS LETHAL. Quand le porteur MEURT, le natif vide TOUS
        # ses effets (`IdunBattle.Operations.KillUnitOperation$$RemoveEffects` -> slot 0x5a ->
        # `IdunBattle.Operations.RemoveEffectsOperation$$Execute`, appele TROIS fois, un par
        # `KillUnitStep`). Le port ne portait que le volet ETROIT `ability_modifications` : mesure
        # sur le bras lethal MC1_67/38901, natif `[]` contre port `[1026, 1098, 1361, 1362]`.
        # Depuis le port de l'operation (`operations/remove_effects.py`), les DEUX cotes vident tout
        # -> le cliquet vaut sur TOUS les bras, lethal compris, et
        # `dead_carrier_keeps_effects_port_only` DOIT valoir False.
        out["dead_carrier_keeps_effects_port_only"] = bool(
            out["caster_died"] and port["effects_caster"] and not out["live_effects_caster"])
        out["removal_checked"] = True
        out["match"] = bool(out["tile_match"] and out["hits_target_match"]
                            and out["hits_self_match"] and out["effect_match"]
                            and out["hp_match"] and out["effect_removed_both"]
                            and not out["dead_carrier_keeps_effects_port_only"])
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)
        bcf.unlink(missing_ok=True)

    # --- VERDICT DERIVE DES CHAMPS
    if out.get("error"):
        out["ok"] = False
        out["verdict"] = "MONTAGE KO : %s" % out["error"]
    elif out.get("caster_has_turn") is not True:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : le caster n'a pas la main (caster_has_turn=%s) ; "
                          "`MovableTilesInRange` repart d'un `OrderedSet` VIDE (garde FLAG de "
                          "`MovementQuery$$FindAnyOrAllMoveableTiles`)." % out.get("caster_has_turn"))
    elif not out.get("rng_captured"):
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : `dumpRng` muet -- les listes per-hit ne sont pas "
                          "comparables BIT A BIT, on ne mesurerait qu'un ordre de grandeur.")
    elif not out.get("live_mutated"):
        out["ok"] = False
        out["verdict"] = "CAST NATIF REFUSE (%s) -- rien n'est mesure" % out.get("live_error")
    elif not out.get("live_hits_target"):
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : le natif n'emet AUCUN coup sur la cible "
                          "(tags `Amount`/`Active_Ability_Type=1059` absents).")
    elif mutate != "none":
        out["ok"] = not out["match"]
        out["verdict"] = (
            "MUTATION %r : le port MUTE %s le natif -- le bras %s ce terme. "
            "(tuile %s / cible %s / soi %s / pose effet %s / retrait %s / PV %s)"
            % (mutate, "DIVERGE de" if not out["match"] else "s'accorde AVEC",
               "DISCRIMINE" if not out["match"] else "NE DISCRIMINE PAS",
               out["tile_match"], out["hits_target_match"], out["hits_self_match"],
               out["effect_match"],
               out["effect_removed_both"] if out["removal_checked"] else "n/a",
               out["hp_match"]))
    elif out["match"]:
        out["ok"] = True
        out["verdict"] = ("PORT == NATIF sur les 7 observables : tuile %s, %d coups sur la cible %s, "
                          "%d coups sur SOI %s, effet 1098 pose (%s), retrait des DEUX cotes (%s), "
                          "aucun effet survivant au porteur MORT cote port seul (%s), PV finaux "
                          "identiques sur %d unites (caster mort=%s)"
                          % (out["live_tile"], len(out["live_hits_target"]),
                             out["live_hits_target"], len(out["live_hits_self"]),
                             out["live_hits_self"], out["live_effect_posed"],
                             out["effect_removed_both"],
                             not out["dead_carrier_keeps_effects_port_only"],
                             len(out.get("hp_live") or {}), out.get("caster_died")))
    else:
        out["ok"] = False
        out["verdict"] = (
            "PORT != NATIF : tuile port=%s natif=%s (%s) | cible port=%s natif=%s (%s) | "
            "soi port=%s natif=%s (%s) | pose 1098 port=%s natif=%s (%s) | retrait 1098 des DEUX "
            "cotes=%s (persiste cote PORT SEUL=%s) | PV port=%s natif=%s (%s)"
            % (out["port"]["tile"], out["live_tile"], out["tile_match"],
               out["port"]["hits_target"], out["live_hits_target"], out["hits_target_match"],
               out["port"]["hits_self"], out["live_hits_self"], out["hits_self_match"],
               out["port"]["effect_posed"], out["live_effect_posed"], out["effect_match"],
               out["effect_removed_both"], out["effect_persists_port_only"],
               out.get("hp_port"), out.get("hp_live"), out.get("hp_match")))

    if verbose:
        print("[389] runner=%s board=%s seed=%s mutation=%s" % (out.get("runner"), board, seed,
                                                                mutate))
        print("[389] geo=%s" % json.dumps(out.get("geometry")))
        print("[389] caster=%s cible=%s main=%s rng=%s"
              % (out.get("caster_id"), out.get("target_id"), out.get("caster_has_turn"),
                 out.get("rng_captured")))
        print("  tuile      port=%s   natif=%s" % ((out.get("port") or {}).get("tile"),
                                                   out.get("live_tile")))
        print("  cible      port=%s (rapporte %s)   natif=%s"
              % ((out.get("port") or {}).get("hits_target"), out.get("port_hits_target_reported"),
                 out.get("live_hits_target")))
        print("  soi-meme   port=%s (rapporte %s)   natif=%s"
              % ((out.get("port") or {}).get("hits_self"), out.get("port_hits_self_reported"),
                 out.get("live_hits_self")))
        print("  pose 1098  port=%s   natif=%s   (effets caster port=%s natif=%s avant=%s)"
              % ((out.get("port") or {}).get("effect_posed"), out.get("live_effect_posed"),
                 (out.get("port") or {}).get("effects_caster"), out.get("live_effects_caster"),
                 out.get("effects_before")))
        print("  retrait    1098 absent des DEUX cotes=%s   (persiste cote PORT SEUL=%s, "
              "cliquet actif=%s, porteur mort garde ses effets cote PORT SEUL=%s)"
              % (out.get("effect_removed_both"), out.get("effect_persists_port_only"),
                 out.get("removal_checked"),
                 out.get("dead_carrier_keeps_effects_port_only")))
        print("  PV         port=%s" % json.dumps(out.get("hp_port")))
        print("             natif=%s (avant=%s)"
              % (json.dumps(out.get("hp_live")), json.dumps(out.get("hp_before"))))
        print("[389] %s" % out.get("verdict"))
        print("[389] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=38900)
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--mutate", choices=MUTATIONS, default="none",
                    help="GARDE ADVERSARIALE : le port est volontairement FAUX, le probe DOIT rougir")
    ap.add_argument("--hp-player", type=int, default=HP,
                    help="PV du camp JOUEUR. Bas (~5000) = le CONTRECOUP tue le caster -> la NOVA de "
                         "son trait `Explodes` part PENDANT le cast et lit `HasEffect(Owner, 1098)` : "
                         "c'est le SEUL canal ou la pose de l'effet est OBSERVABLE en degat.")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, board=a.board, mutate=a.mutate, hp_player=a.hp_player,
              verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
