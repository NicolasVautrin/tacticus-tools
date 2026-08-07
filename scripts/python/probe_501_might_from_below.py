#!/usr/bin/env python
"""Probe #501 -- validation live de la face COMBAT de `MightFromBelow` (active 1165, The Patermine
`genesPatriarch`).

Port : `engine/runner/abilities/loki/might_from_below.py` (mirror de
`IdunBattleLogic.Entities.Abilities.Active.Loki.MightFromBelowAbility$$ExecuteBehaviour`).

CE QUE CE PROBE MESURE, ET POURQUOI CETTE FORME
-----------------------------------------------
L'arbre natif a TROIS phases (`AActiveAbility$$Execute` x3) : attaque 5 coups, `KillDeadUnits`,
puis `IfAlive(Spawn(<tuiles des decoys AMIS ADJACENTS>))`. Un total de degat juste ne prouverait
rien -- il faut confronter (a) la SEQUENCE coup par coup, (b) le SUMMON, et (c) le fait que les
tuiles de summon soient evaluees APRES l'attaque.

  A -- SEQUENCE. Replay-diff bit-exact : meme etat pre-cast (`decisionView` / `observeBattle` /
       `combatSnapshot` / `dumpRng`), cast live PUIS cast offline sur cet etat, et diff des
       montants COUP PAR COUP -- live via les events `Amount` portant
       `Active_Ability_Type == 1165` (meme oracle que #61/#116), offline via `attack["per_hit"]`.
       Un total peut coincider par compensation ; une LISTE de 5 montants, non.

  B -- CHAINAGE kill -> decoy -> summon (LE regime discriminant). Cible a BAS PV : l'attaque la
       TUE, `CosmicHorror_OnKillAbility` pose un `genesSmnDecoy` sur sa tuile -- qui est ADJACENTE
       au Patermine, puisque le masque impose une cible adjacente -- et la 3e phase summone un
       `genesSmnGenestealer` DESSUS. Un port qui figerait les tuiles AVANT l'attaque rendrait 0
       summon ici, sans erreur : c'est exactement le no-op silencieux que ce volet attrape.

  C -- GATE DE CIBLE (non-regression de la MIGRATION du masque,
       `TARGETING_OPTIONS_UNPORTED` -> classe). `rules = 0x4000 = TargetIsEnemy` +
       `range = RANGE_ADJACENT` : on confronte l'ensemble des cibles que le PORT juge legales a
       celui que le NATIF rend (`abilityTargets`). Une divergence serait la degradation
       PERMISSIVE que le contrat de disjonction protege.

ASCII only (cp1252).
Usage: python probe_501_might_from_below.py [--volet A|B|C|tous] [--seed 50101] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

PATERMINE_VIS = "genesPatriarch"          # SEUL porteur lineup de 1165 (3 autres = npc)
ABILITY = 1165
ABILITY_ID = "MightFromBelow"
DECOY_VIS = "genesSmnDecoy"               # `CosmicHorror.constants.unitToSpawn`
SUMMON_VIS = "genesSmnGenestealer"        # `MightFromBelow.constants.unitId`
VICTIME_VIS = "necroWarden"               # volet B : la cible du CAST, celle qu'on descend en PV


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _hp(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _units_of_vis(dec, vis, alive_only=True):
    """⚠ `alive_only=False` est le defaut a utiliser pour un SUMMON : mesure du 2026-08-07, le
    Genestealer pose par la 3e phase attaque immediatement, se fait tuer par la riposte adverse
    dans la MEME cascade, et disparait donc d'une vue filtree `alive`. Une comparaison sur les
    seules unites VIVANTES avait conclu << le natif ne summone pas >>, ce qui est FAUX (les steps
    du cast montrent `AddUnit(entity=108, Unit_Foot_Tile_Id_1=73)` sous le groupe
    `Ability_Summon`)."""
    return [u for u in (dec.get("units") or [])
            if u.get("visualId") == vis and (u.get("alive") or not alive_only)]


def _live_added_units(res):
    """Les unites CREEES par le cast, dans l'ordre natif : chaque `step 9` (`AddUnitOperation`)
    porte `Unit_Parent_Id` et `Unit_Foot_Tile_Id_1` (la tuile d'ancrage). C'est la mesure qui
    tranche le SUMMON independamment de ce que la cascade aval fait ensuite de l'unite posee."""
    out = []
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            if (e.get("step") or e.get("type")) != 9:
                continue
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            out.append({"entity": e.get("entity"), "parent": td.get("Unit_Parent_Id"),
                        "tile": td.get("Unit_Foot_Tile_Id_1")})
    return out


def _live_amounts_after(res, index, target_id):
    """Les `Amount` portes sur `target_id` APRES le step `index` -- c.-a-d. apres l'ouverture du
    groupe `Ability_Summon`. C'est la SEQUENCE de coups de l'attaque IA du summon, mesuree hors
    de tout delta HP (qu'un heal/revive adverse peut masquer)."""
    out = []
    if index is None:
        return out
    for act in (res.get("actions") or []):
        for i, e in enumerate(act.get("events") or []):
            if i <= index:
                continue
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" in td and int(td.get("Target_Id") or -1) == int(target_id):
                out.append(td["Amount"])
    return out


def _live_group_order(res, groups):
    """L'ORDRE des groupes `groups` dans les steps du cast -- la DECOMPOSITION PAR ETAGE de
    l'arbre : `Ability_Attack` (0x20) puis `Ability_Summon` (0x22), et entre les deux le
    `AddUnit` du decoy pose par `CosmicHorror`."""
    out = []
    for act in (res.get("actions") or []):
        for i, e in enumerate(act.get("events") or []):
            if e.get("kind") == "group" and int(e.get("group") or -1) in groups:
                out.append((i, int(e["group"]), e.get("source")))
            elif (e.get("step") or e.get("type")) == 9:
                out.append((i, "AddUnit", e.get("entity")))
    return out


def build(seed: int, board: str, tag: str, hp_target: int, extra=()) -> int:
    """Runner ISOLE. `--state-file` sous `logs/` (SORTIE de run, #349) et NOM UNIQUE par volet :
    deux volets lances ensemble ne doivent pas se marcher dessus."""
    state = ROOT / "logs" / "runners" / f"_a501_mfb_{tag}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state), "--board", board,
         "--p-units", f"{PATERMINE_VIS},genesPrimus",
         "--a-units", "ultraTitus,necroWarden",
         "--hp-target", str(hp_target), "--hp-player", "400000"] + list(extra),
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[501] build {tag} KO: {(proc.stderr or proc.stdout or '')[-500:]}", file=sys.stderr)
        return 0
    return json.loads(state.read_text())["runnerId"]


def _advance_to_my_turn(rpc, rid, vis, max_iter=10):
    """Amene le tour a la team du porteur SANS faire jouer l'IA adverse (`endturn` sec) : on garde
    la main totale sur la geometrie (doctrine drive-positions)."""
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _drive_adjacent(rpc, rid, max_turns=8, vis_cible=None):
    """DEPLACE le Patermine jusqu'a etre ADJACENT (dist 1) d'un ennemi -- `RANGE_ADJACENT`. On
    DEPLACE, on ne se plaint pas de la geometrie de spawn.

    `vis_cible` = on VISE cet ennemi-la, et pas simplement le plus proche : le volet B a besoin que
    la cible du CAST soit celle dont on a baisse les PV, sinon le kill (donc le chainage) n'a pas
    lieu."""
    for _ in range(max_turns):
        dec, me = _advance_to_my_turn(rpc, rid, PATERMINE_VIS)
        if me is None:
            return None, None, None
        enemies = [u for u in (dec.get("units") or [])
                   if u.get("alive") and u.get("owner") != me.get("owner")]
        if not enemies:
            return None, None, None
        if vis_cible is not None:
            vises = [e for e in enemies if e.get("visualId") == vis_cible]
            if vises:
                enemies = vises
        tgt = min(enemies, key=lambda e: hexgeo.distance(_pos(me), _pos(e)))
        if hexgeo.distance(_pos(me), _pos(tgt)) == 1:
            return dec, me, tgt
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            tp = _pos(tgt)
            best = min(tiles, key=lambda p: hexgeo.distance(p, tp))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            me2 = _find(dec2, PATERMINE_VIS)
            if me2 is not None:
                en2 = [u for u in (dec2.get("units") or [])
                       if u.get("alive") and u.get("owner") != me2.get("owner")]
                if vis_cible is not None:
                    en2 = [e for e in en2 if e.get("visualId") == vis_cible] or en2
                t2 = min(en2, key=lambda e: hexgeo.distance(_pos(me2), _pos(e))) if en2 else None
                if t2 is not None and hexgeo.distance(_pos(me2), _pos(t2)) == 1:
                    return dec2, me2, t2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _capture(rpc, rid):
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    return dec, ob, snap, s


def _offline_state(dec, ob, snap, s, board):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    state = load_state(dec, ob, snap, board=board)
    if _ok(s):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"])
        rng.mti = s["mti"]
        state.rng = rng
    return state


def _live_per_hit(res, ability):
    """{target_id -> [degat par COUP]} depuis les events d'`applyAction(captureEvents)`. Un event
    portant `Amount` et `Active_Ability_Type == ability` == UN coup APPLIQUE (oracle #61/#116)."""
    out: dict = {}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == int(ability):
                out.setdefault(int(td.get("Target_Id")), []).append(td.get("Amount"))
    return out


def _offline_apply(state, caster_id, target_id):
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id, target_id, ABILITY))
    return runner.ability_handler.last or {}


def _offline_units_of_vis(state, vis, alive_only=False):
    """Cf. `_units_of_vis` : par DEFAUT on ne filtre PAS sur `alive` -- un summon peut mourir dans
    la cascade aval du meme cast."""
    from engine.runner.components import UnitComponent, PositionComponent
    out = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if uc is not None and uc.visual_id == vis and (uc.alive or not alive_only):
            out.append((eid, (pc.col, pc.row) if pc is not None else None, bool(uc.alive)))
    return sorted(out)


# ------------------------------------------------------------------ volet A : SEQUENCE ----------

def volet_a(rpc, board_cls, seed, board_id, casts):
    """Replay-diff bit-exact de la SEQUENCE coup par coup, cible a HAUT PV (aucun kill : le volet
    isole l'ATTAQUE de la phase de summon)."""
    rid = build(seed, board_id, "a", 400000)
    if not rid:
        return ["A:build"]
    fails: list = []
    seqs: list = []
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return ["A:boardGraph"]
        board = board_cls(bg["tiles"], adjacency="evenq")
        for n in range(casts):
            dec, me, tgt = _drive_adjacent(rpc, rid)
            if me is None or tgt is None:
                print(f"[501-A] cast#{n}: drive KO -> datapoint NON MESURE")
                break
            caster_id, target_id = me["id"], tgt["id"]
            dec0, ob0, snap0, s0 = _capture(rpc, rid)
            hp0 = _hp(ob0, target_id)
            state = _offline_state(dec0, ob0, snap0, s0, board)
            if state.get_entity(caster_id) is None or state.rng is None:
                fails.append(f"A/cast{n}:etat-offline")
                break
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": caster_id, "targetId": target_id,
                "abilityType": ABILITY}, "captureEvents": True}, 240)
            a0 = ((res or {}).get("actions") or [{}])[0]
            if not (a0.get("ok") and a0.get("mutated")):
                print(f"[501-A] cast#{n} live KO/illegal: {str(res)[:240]}")
                fails.append(f"A/cast{n}:cast-live")
                break
            live_seq = (_live_per_hit(res, ABILITY) or {}).get(int(target_id)) or []
            diag = _offline_apply(state, caster_id, target_id)
            if diag.get("ported") is not True:
                print(f"[501-A] cast#{n}: 1165 NON portee (no-op silencieux): {diag}")
                fails.append(f"A/cast{n}:ported")
                break
            atk = ((diag.get("attacks") or [{}])[0] or {})
            off_seq = list(((atk.get("attack") or {}).get("per_hit")) or [])
            same = live_seq == off_seq
            seqs.append(off_seq)
            print(f"[501-A] cast#{n} cible={tgt.get('visualId')} hp0={hp0} "
                  f"live={live_seq} offline={off_seq} : {'OK' if same else 'X'}")
            if not same:
                fails.append(f"A/cast{n}:sequence")
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)
    # TEMOIN NON DEGENERE : une sequence VIDE des deux cotes serait un accord sans contenu.
    nonvide = [s for s in seqs if s]
    if not nonvide:
        print("[501-A] TEMOIN DEGENERE : aucune sequence non vide mesuree.")
        fails.append("A:temoin-degenere")
    else:
        longueurs = sorted(set(len(s) for s in nonvide))
        print(f"[501-A] longueurs de sequence observees = {longueurs} "
              f"(nrOfHits attendu = 5)")
        if longueurs != [5]:
            print("[501-A] ATTENTION : longueur != 5 -- coups refuses (cadavre) ou config autre.")
    return fails


# ------------------------------------------- volet B : chainage kill -> decoy -> summon ---------

def _dump_events(res):
    """DECOMPOSITION PAR ETAGE : l'ORDRE brut des steps du cast. C'est ce qui tranche << le decoy
    de `CosmicHorror` est-il pose AVANT ou APRES la phase de summon ? >> -- une question qu'aucun
    total ni aucun compte ne peut trancher."""
    print("[501-B] --- steps du cast (ordre natif) ---")
    for act in (res.get("actions") or []):
        for i, e in enumerate(act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            kind = e.get("type") or e.get("step") or e.get("kind")
            reste = {k: v for k, v in e.items() if k not in ("tags",)}
            print(f"  [{i:3d}] {kind} {reste} {td}")


def volet_b(rpc, board_cls, seed, board_id, hp_target, dump_events=False):
    """LE regime discriminant : l'attaque TUE, `CosmicHorror` pose un decoy adjacent, la 3e phase
    summone dessus. Les tuiles de summon sont donc evaluees APRES l'attaque."""
    # `--hp-target` force UNE valeur sur TOUT le camp adverse. On la remonte PER-UNIT sur
    # `ultraTitus` pour que la cible du summon SURVIVE a son attaque : sinon elle meurt, son
    # `FuelledByFury_CanRevive` la ramene a plein PV et le delta HP retombe a 0 des DEUX cotes --
    # un accord en REGIME DEGENERE, qui ne prouve rien sur l'attaque IA du summon.
    # `--hp-target` force UNE valeur sur TOUT le camp adverse ; on la laisse HAUTE et on descend
    # PER-UNIT la seule cible du cast. Sinon l'autre ennemi -- celui que le SUMMON attaque -- meurt
    # aussi, son `FuelledByFury_CanRevive` le ramene a plein PV, et le delta HP retombe a 0 des DEUX
    # cotes : un accord en REGIME DEGENERE, qui ne prouve rien sur l'attaque IA du summon.
    rid = build(seed, board_id, "b", 400000,
                extra=["--unit-stat", f"{VICTIME_VIS}:Health={hp_target},"
                                      f"RemainingHealth={hp_target}"])
    if not rid:
        return ["B:build"]
    fails: list = []
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return ["B:boardGraph"]
        board = board_cls(bg["tiles"], adjacency="evenq")
        dec, me, tgt = _drive_adjacent(rpc, rid, vis_cible=VICTIME_VIS)
        if me is None or tgt is None:
            print("[501-B] drive KO -> NON MESURE")
            return ["B:drive"]
        caster_id, target_id = me["id"], tgt["id"]
        dec0, ob0, snap0, s0 = _capture(rpc, rid)
        hp0 = _hp(ob0, target_id)
        state = _offline_state(dec0, ob0, snap0, s0, board)
        if state.get_entity(caster_id) is None or state.rng is None:
            return ["B:etat-offline"]
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster_id, "targetId": target_id,
            "abilityType": ABILITY}, "captureEvents": True}, 240)
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not (a0.get("ok") and a0.get("mutated")):
            print(f"[501-B] cast live KO: {str(res)[:240]}")
            return ["B:cast-live"]
        live_seq = (_live_per_hit(res, ABILITY) or {}).get(int(target_id)) or []
        if dump_events:
            _dump_events(res)
        # L'ETAGE QUI TRANCHE LE CHAINAGE : l'ORDRE des steps du cast. On le lit AVANT toute
        # comparaison d'etat, parce qu'une vue d'etat POST-cast ne distingue pas << pas summone >>
        # de << summone puis tue par la riposte >>.
        ordre = _live_group_order(res, {0x20, 0x22})
        added = _live_added_units(res)
        i_attack = next((i for i, g, _s in ordre if g == 0x20), None)
        i_summon = next((i for i, g, _s in ordre if g == 0x22), None)
        tile_cible = None
        for a in added:
            if tile_cible is None and a.get("parent") == caster_id:
                tile_cible = a.get("tile")
        print(f"[501-B] groupes du cast : Ability_Attack@{i_attack} Ability_Summon@{i_summon}")
        print(f"[501-B] AddUnit natifs  : {added}")
        dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        live_dead = _find(dec2, tgt.get("visualId")) is None
        # ⚠ alive_only=False : le summon MEURT dans la cascade aval du meme cast (riposte).
        live_summons = [(u["id"], _pos(u), bool(u.get("alive")))
                        for u in _units_of_vis(dec2, SUMMON_VIS, alive_only=False)]
        live_decoys = [(u["id"], _pos(u), bool(u.get("alive")))
                       for u in _units_of_vis(dec2, DECOY_VIS, alive_only=False)]

        diag = _offline_apply(state, caster_id, target_id)
        if diag.get("ported") is not True:
            print(f"[501-B] 1165 NON portee : {diag}")
            return ["B:ported"]
        atk = ((diag.get("attacks") or [{}])[0] or {})
        off_seq = list(((atk.get("attack") or {}).get("per_hit")) or [])
        off_summons = _offline_units_of_vis(state, SUMMON_VIS)
        off_decoys = _offline_units_of_vis(state, DECOY_VIS)
        from engine.runner.components import UnitComponent
        te = state.get_entity(target_id)
        tuc = te.get_component(UnitComponent) if te is not None else None
        off_dead = bool(tuc is not None and not tuc.alive)

        print(f"[501-B] hp0={hp0} live_seq={live_seq} off_seq={off_seq}")
        print(f"[501-B] cible morte : live={live_dead} offline={off_dead}")
        print(f"[501-B] decoys   : live={[(p, a) for _i, p, a in live_decoys]} "
              f"offline={[(p, a) for _i, p, a in off_decoys]}")
        print(f"[501-B] summons  : live={[(p, a) for _i, p, a in live_summons]} "
              f"offline={[(p, a) for _i, p, a in off_summons]}")
        print(f"[501-B] diag.summons={diag.get('summons')} "
              f"summon_attacks={diag.get('summon_attacks')} downed={diag.get('downed')}")
        # L'ATTAQUE IA DU SUMMON (`on_appearance` = `PerformAIAttackFromCurrentPosition`) : on
        # confronte le delta HP de SA cible, unite par unite. C'est le dernier etage de l'arbre
        # #501 ; ce qui vient APRES (riposte adverse, mort du summon, decoy du trait `Ambush`)
        # appartient a d'autres mecaniques et est RAPPORTE, pas assertionne.
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        from engine.runner.components import HealthComponent
        deltas_live, deltas_off = {}, {}
        for u in (dec0.get("units") or []):
            uid = u["id"]
            h0 = _hp(ob0, uid)
            if h0 is None:
                continue
            h2 = _hp(ob2, uid)
            deltas_live[uid] = (h0 - h2) if h2 is not None else "mort"
            e = state.get_entity(uid)
            hc = e.get_component(HealthComponent) if e is not None else None
            ec = e.get_component(UnitComponent) if e is not None else None
            deltas_off[uid] = ("mort" if (ec is not None and not ec.alive)
                               else ((h0 - hc.hp) if hc is not None else None))
        print(f"[501-B] deltas HP live   = {deltas_live}")
        print(f"[501-B] deltas HP offline= {deltas_off}")
        sa = (diag.get("summon_attacks") or [])
        cible_summon = sa[0]["target"] if sa else None
        if cible_summon is not None:
            dl, do = deltas_live.get(cible_summon), deltas_off.get(cible_summon)
            print(f"[501-B] cible de l'attaque du summon = u{cible_summon} : "
                  f"live={dl} offline={do}")
            if dl != do:
                fails.append("B:delta-cible-summon")
                print("[501-B] ECART sur la cible du summon -- decomposer : coups du summon, ou "
                      "cascade AVAL (riposte a la mort, FinalJustice) hors perimetre #501 ?")
            # Le delta HP peut etre masque par un heal/revive adverse : on confronte AUSSI la
            # SEQUENCE brute des coups portes APRES l'ouverture du groupe `Ability_Summon`, qui
            # est l'attaque IA du summon (`on_appearance`). Somme comparee au `total` du port.
            live_apres = _live_amounts_after(res, i_summon, int(cible_summon))
            print(f"[501-B] coups du summon (live, apres Ability_Summon) = {live_apres} "
                  f"somme={sum(live_apres)} ; total offline={sa[0].get('total')}")
            if sum(live_apres) != sa[0].get("total"):
                fails.append("B:total-attaque-summon")
            if not live_apres:
                print("[501-B] TEMOIN DEGENERE : le summon n'a porte aucun coup mesurable.")
                fails.append("B:temoin-summon-inerte")
        if live_seq != off_seq:
            fails.append("B:sequence")
        if live_dead != off_dead:
            fails.append("B:mort")
        # CE QUE CE VOLET GARDE : le NOMBRE et les TUILES des summons poses par la 3e phase --
        # PAS ce que la cascade aval en fait (riposte, mort, decoy d'Ambush), qui appartient a
        # d'autres mecaniques.
        pos_live = sorted(p for _i, p, _a in live_summons)
        pos_off = sorted(p for _i, p, _a in off_summons if p)
        if pos_live != pos_off:
            fails.append("B:summons")
        # ET l'ETAT du decoy sur lequel le summon est pose : `AddUnitOperation$$KillSteppableUnits`
        # le DETRUIT. Sans ce crush le port laissait un decoy VIVANT en trop -- un fantome qui
        # resservirait de tuile de summon au cast suivant.
        if (sorted((p, a) for _i, p, a in live_decoys)
                != sorted((p, a) for _i, p, a in off_decoys if p)):
            fails.append("B:decoys")
        # TEMOIN NON DEGENERE : ce volet ne vaut que si le chainage a REELLEMENT eu lieu.
        if not live_dead:
            print("[501-B] TEMOIN DEGENERE : la cible n'est pas morte, le chainage n'est pas "
                  "exerce. Baisser --hp-target.")
            fails.append("B:temoin-pas-de-kill")
        if i_summon is None or not live_summons:
            print("[501-B] TEMOIN DEGENERE : aucun groupe Ability_Summon / aucun summon natif -- "
                  "le regime discriminant n'est pas exerce.")
            fails.append("B:temoin-pas-de-summon")
        elif i_attack is not None and not (i_attack < i_summon):
            fails.append("B:ordre-des-phases")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)
    return fails


# ------------------------------------------------------------------ volet C : gate de cible -----

def volet_c(rpc, board_cls, seed, board_id):
    """Le masque migre doit refuser exactement ce que le natif refuse : `TargetIsEnemy` +
    `RANGE_ADJACENT`. On confronte l'ENSEMBLE des cibles legales, port vs `abilityTargets`."""
    rid = build(seed, board_id, "c", 400000)
    if not rid:
        return ["C:build"]
    fails: list = []
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return ["C:boardGraph"]
        board = board_cls(bg["tiles"], adjacency="evenq")
        dec, me, _tgt = _drive_adjacent(rpc, rid)
        if me is None:
            return ["C:drive"]
        caster_id = me["id"]
        dec0, ob0, snap0, s0 = _capture(rpc, rid)
        state = _offline_state(dec0, ob0, snap0, s0, board)
        nat = rpc("abilityTargets", {"runnerId": rid, "unitId": caster_id,
                                     "abilityType": ABILITY}, 90)
        # ⚠ La reponse est `units[].abilities[]` avec `fromHere` (castable SANS bouger) et
        # `targets` (superset move inclus) -- il n'y a PAS de cle `now`. Lire la mauvaise cle rend
        # un ensemble VIDE, donc un faux « le natif ne cible rien ». On exige en plus
        # `fromHereResolved`, sans quoi `fromHere` est absent et l'ensemble est vide par DEFAUT de
        # mesure, pas par refus natif.
        if not nat.get("fromHereResolved"):
            print("[501-C] fromHere INDISPO -- gate NON MESUREE (ni vert ni rouge)")
            return ["C:fromHere-indispo"]
        natifs = set()
        for u in (nat.get("units") or []):
            if int(u.get("unitId") or -1) != int(caster_id):
                continue
            for a in (u.get("abilities") or []):
                if int(a.get("abilityId") or -1) != ABILITY:
                    continue
                for t in (a.get("fromHere") or []):
                    tid = t.get("targetId") if isinstance(t, dict) else t
                    if tid is not None:
                        natifs.add(int(tid))
        from engine.runner.abilities.targeting import get_invalid_target_reason
        from engine.runner.abilities.handler import ABILITY_CLASSES
        # ⚠ INSTANCE, pas la classe : la cascade appelle `get_dynamic_invalid_target_reason` sur
        # l'objet (une classe rendrait la methode NON LIEE). Signature LUE :
        # `get_invalid_target_reason(state, caster_id, target_id, ability)`.
        ability = ABILITY_CLASSES[ABILITY]()
        portes = set()
        for u in (dec0.get("units") or []):
            if not u.get("alive") or u["id"] == caster_id:
                continue
            if get_invalid_target_reason(state, caster_id, u["id"], ability) == 0:
                portes.add(int(u["id"]))
        print(f"[501-C] cibles natives={sorted(natifs)} portees={sorted(portes)}")
        if natifs != portes:
            print(f"[501-C] natif\\port={sorted(natifs - portes)} port\\natif={sorted(portes - natifs)}")
            fails.append("C:cibles")
        if not natifs:
            print("[501-C] TEMOIN DEGENERE : aucune cible native -- l'accord ne discrimine rien.")
            fails.append("C:temoin-degenere")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", default="tous", choices=["A", "B", "C", "tous"])
    ap.add_argument("--seed", type=int, default=50101)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--casts", type=int, default=3)
    ap.add_argument("--hp-target", type=int, default=4000)
    ap.add_argument("--dump-events", action="store_true",
                    help="volet B : imprime l'ORDRE brut des steps du cast (decomposition par etage)")
    args = ap.parse_args()

    from engine.entities.pathfinding.board import Board
    from engine.entities.effects.magnitude import ability_var

    sid = _resolve_session()

    def rpc(method, body, t=90):
        return (_rpc(sid, method, [body], timeout=t).get("result") or {})

    # `ability_var` rend des ENTIERS ; les constantes de CHAINE (`unitId`, `damageProfile`) se
    # lisent au gameconfig, comme le fait la classe portee.
    import gameconfig as GC
    consts = ((GC.ability(ABILITY_ID) or {}).get("constants") or {})
    print(f"[501] kit 1165 : nrOfHits="
          f"{int(ability_var(ABILITY_ID, 'nrOfHits', is_constant=True) or 0)} "
          f"unitId={consts.get('unitId')} profil={consts.get('damageProfile')}")

    fails: list = []
    if args.volet in ("A", "tous"):
        fails += volet_a(rpc, Board, args.seed, args.board, args.casts)
    if args.volet in ("B", "tous"):
        fails += volet_b(rpc, Board, args.seed + 1, args.board, args.hp_target,
                         dump_events=args.dump_events)
    if args.volet in ("C", "tous"):
        fails += volet_c(rpc, Board, args.seed + 2, args.board)

    if fails:
        print(f"[501] ECHECS : {fails}")
        return 1
    print("[501] PROBE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
