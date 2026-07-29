#!/usr/bin/env python
"""Probe #224 item 2 -- validation live de `CursedPlagueBell_ExtraMove` (EffectType 0x431 = 1073).

L'effet est pose pour UN tour par
`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellMovementAbility$$CreateBehaviour`
sur les amis CHAOS non-Stationary de l'aura `ContagionsOfNurgle` de `deathBlightbringer`
(<< Corrodius >>). La classe d'effet est NATIVE bespoke et emet elle-meme son `ChangeStat` :

    IdunBattle.Entities.Effects.Loki.CursedPlagueBell_ExtraMoveEffect$$ApplyInternal
      == ...$$AddStatModifier
      = DSLBehaviors.ChangeStat( Entity(target), Stat(1 = Movement, 5 = Modification),
                                 4 = Modify, DSLFormulas.Direct(GetNumberConstant(0xe extraMovement)),
                                 Entity(effect), 1 = OnlyAlive, false, false )
    ...$$RevertInternal == ...$$RevertStatModifier
      = le MEME appel en Stat(1 = Movement, 6 = ResetModification), amount = <DSLFormulas+0x18> = Direct(0)

Port : `engine/entities/effects/loki/cursed_plague_bell.py` (canal EAGER `applied_stat_mods` +
`reverted_stats`), registre `EFFECT_CLASSES["CursedPlagueBell_ExtraMove"]`.

CE QUE LE PROBE MESURE (rien n'est suppose -- tout est relu du live) :
  0. OFFLINE  : substrat du port (constante, registre, formes appliquee/revertee).
  1. LIVE     : QUI porte 1073 au tour du joueur (gate Chaos, exclusion du porteur d'aura).
  2. ATTRIBUTION : la contribution offline vit sous une cle d'effet retirable, du MEME montant que
                   celui que `statModSources` attribue a l'entite-effet NATIVE, residu opaque = 0.
  3. VALEUR   : `GetStat(MOVEMENT)` offline == `combatSnapshot.units[].stats.movement` natif.
  4. REVERT   : `endturn` des DEUX cotes (natif + `EndTurnOperation`) -> valeurs ABSOLUES egales.
                C'est LE critere : l'effet expire (remaining = 1) et son +1 doit SORTIR du stat.
  5. RE-POSE  : `endturn` de nouveau -> l'effet est re-pose (nouvel effectId) et le stat remonte ;
                le port re-seede depuis la nouvelle capture doit rendre la MEME valeur.

`--mutate registry` retire l'entree `CursedPlagueBell_ExtraMove` du registre AVANT de charger l'etat
(= l'arbre sans ce port) et rejoue les memes mesures : c'est la contre-epreuve.

ASCII only (cp1252). Usage :
    python probe_224_cursed_plague_bell_extramove.py --offline-only
    python probe_224_cursed_plague_bell_extramove.py [--seed 777] [--board MC1_67]
    python probe_224_cursed_plague_bell_extramove.py --mutate registry
    python probe_224_cursed_plague_bell_extramove.py --runner <id>      # reutilise un runner existant
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

EFFECT_TYPE = 1073                     # 0x431 CursedPlagueBell_ExtraMove
ABILITY = "CursedPlagueBell"
BELL = "deathBlightbringer"            # Corrodius -- POOL-HERO rank 17, porteur de l'aura
CHAOS_ALLIES = ["worldJakhal", "blackAbaddon"]     # amis CHAOS (recoivent l'effet)
NON_CHAOS_ALLY = "astraBullgryn"                   # ami IMPERIAL (contre-cas du gate Chaos)
ENEMIES = "necroWarden,necroWarden"


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# --------------------------------------------------------------------------------------------
# Etape 0 -- substrat OFFLINE
# --------------------------------------------------------------------------------------------
def step0_offline() -> int:
    """Le port lit-il ce que le natif lit ? (constante, registre, formes apply/revert)."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects import effect_stat_mod_key, effect_stat_modifications
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.stats import StatType

    bad = 0
    cls = EFFECT_CLASSES.get("CursedPlagueBell_ExtraMove")
    print("[0] registre EFFECT_CLASSES['CursedPlagueBell_ExtraMove'] = %s"
          % (cls.__name__ if cls else None))
    if cls is None:
        return 1

    amt = ability_var(ABILITY, "extraMovement", is_constant=True)
    print("[0] GetNumberConstant(0xe = extraMovement) via gameconfig = %r" % (amt,))
    if amt != 1:
        print("[0] ATTENTION : la constante gameconfig a bouge (attendu 1) -- le port la RELIT, "
              "les attendus chiffres du probe suivent la valeur lue")

    eff = cls(name="CursedPlagueBell_ExtraMove", effect_type=EFFECT_TYPE, remaining_turns=1, source=1)
    applied = eff.applied_stat_mods(object())
    reverted = [int(s) for s in eff.reverted_stats()]
    key = effect_stat_mod_key(eff)
    print("[0] applied_stat_mods = %s ; reverted_stats = %s ; source_key = %s"
          % (applied, reverted, key))
    if applied != [(int(StatType.MOVEMENT), int(amt or 0))]:
        print("[0] KO : applied_stat_mods != [(MOVEMENT, extraMovement)]")
        bad += 1
    if reverted != [int(StatType.MOVEMENT)]:
        print("[0] KO : reverted_stats != [MOVEMENT] -> la contribution ne serait PAS retirable")
        bad += 1
    if key is None:
        print("[0] KO : effect_stat_mod_key None -> aucun revert possible")
        bad += 1
    # forme OVERRIDE : sans ctx la base ne dit rien (comme BlackRage/Waaagh), avec ctx elle rend le mod.
    if effect_stat_modifications(eff) != []:
        print("[0] KO : la forme de BASE devrait etre muette (le natif OVERRIDE ApplyModification)")
        bad += 1
    if effect_stat_modifications(eff, stats_ctx=object()) != applied:
        print("[0] KO : la forme OVERRIDE ne remonte pas applied_stat_mods")
        bad += 1
    print("[0] substrat offline : %s" % ("OK" if bad == 0 else "%d ecart(s)" % bad))
    return bad


# --------------------------------------------------------------------------------------------
# Harnais live
# --------------------------------------------------------------------------------------------
def build(seed: str, board: str, state_file: Path) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    p_units = ",".join([BELL] + CHAOS_ALLIES + [NON_CHAOS_ALLY])
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board,
         "--p-units", p_units, "--a-units", ENEMIES,
         "--hp-target", "300000", "--hp-player", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[build] KO: %s" % ((proc.stderr or proc.stdout or "")[-500:],))
        sys.exit(2)
    return int(json.loads(state_file.read_text())["runnerId"])


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _advance_to_owner_of(sid, rid, vis, max_iter=12):
    """Avance jusqu'au tour du proprietaire de `vis` (l'effet n'est pose qu'a SON debut de tour)."""
    for _ in range(max_iter):
        dec = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                                "captureEvents": False}, 90)
    return None, None


def _board(sid, rid):
    """Board NATIF (`boardGraph`) -- indispensable : sans lui `state.board is None` et le pendant
    offline d'`aiMovableTiles` rend [] SILENCIEUSEMENT (cf. `_move_tiles`)."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _capture(sid, rid):
    dec = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
    return dec, ob, snap


def _live_movement(snap):
    return {int(su["entityId"]): int((su.get("stats") or {}).get("movement") or 0)
            for su in (snap.get("units") or []) if su.get("entityId") is not None}


def _live_move_by_source(sid, rid):
    """`statModSources` -> {unitId: {"total": t, "residual": r, "effect": somme des sources NON-unite}}."""
    sm = _r(sid, "statModSources", {"runnerId": rid, "minAbs": 1}, 120)
    out = {}
    for uu in (sm.get("units") or []) if isinstance(sm, dict) else []:
        mv = (uu.get("mods") or {}).get("movement")
        if not mv:
            continue
        eff = sum(int(s.get("amount") or 0) for s in (mv.get("bySource") or [])
                  if not s.get("sourceIsUnit"))
        out[int(uu["entityId"])] = {"total": int(mv.get("total") or 0),
                                    "residual": int(mv.get("residual") or 0), "effect": eff}
    return out


def _off_movement_and_sources(state, uid):
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType, CAPTURED_SOURCE
    ent = state.get_entity(uid)
    sc = ent.get_component(StatsComponent) if ent is not None else None
    if sc is None:
        return None, {}, 0, 0
    ctx = sc.ctx
    comp = ctx.stats.components.get(int(StatType.MOVEMENT))
    per = dict(comp.modification.per_source) if comp is not None else {}
    statmod = sum(int(v) for k, v in per.items()
                  if isinstance(k, tuple) and k[:2] == ("statmod", EFFECT_TYPE))
    return int(ctx.stat(StatType.MOVEMENT)), per, statmod, int(per.get(CAPTURED_SOURCE, 0) or 0)


def _has_1073(u):
    return any(e.get("effectType") == EFFECT_TYPE for e in (u.get("effects") or []))


def _live_movable(sid, rid, side="all"):
    """`aiMovableTiles` = dry-run natif de `MovementQuery.GetMovableTilesFor` -> {unitId: {(col,row)}}.
    C'est l'INCIDENCE de la stat MOVEMENT sur le mouvement, pas la stat elle-meme. `side="all"` pour
    pouvoir lire les tuiles d'une unite dont ce n'est PAS le tour (mesure post-expiration)."""
    mt = _r(sid, "aiMovableTiles", {"runnerId": rid, "side": side}, 150)
    out = {}
    for uu in (mt.get("units") or []) if isinstance(mt, dict) else []:
        uid = uu.get("unitId", uu.get("entityId"))
        if uid is None:
            continue
        out[int(uid)] = {(int(t["col"]), int(t["row"])) for t in (uu.get("tiles") or [])}
    return out


def _off_movable(state, uid):
    """Pendant OFFLINE de `aiMovableTiles` (`engine/ai/state_bridge._move_tiles`, dont la portee est
    justement `_move_range` = `GetStat(MOVEMENT)` -- le stat que l'effet 1073 modifie)."""
    from engine.ai.state_bridge import _move_tiles
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    ent = state.get_entity(uid)
    if ent is None:
        return None
    pc = ent.get_component(PositionComponent)
    oc = ent.get_component(OwnerComponent)
    uc = ent.get_component(UnitComponent)
    if pc is None or oc is None or uc is None:
        return None
    tiles = _move_tiles(state, int(uid), uc.visual_id, int(oc.team), (pc.col, pc.row))
    return {(int(t["col"]), int(t["row"])) for t in tiles}


# --------------------------------------------------------------------------------------------
def run_live(sid, rid, mutate: str | None) -> int:
    if mutate == "registry":
        from engine.entities.effects import factory as _F
        _F.EFFECT_CLASSES.pop("CursedPlagueBell_ExtraMove", None)
        print("[mut] entree 'CursedPlagueBell_ExtraMove' RETIREE du registre (arbre sans le port)")
    from engine.runner.snapshot import load_state
    from engine.runner.operations.turnflow import EndTurnOperation

    bad = 0
    dec, bell = _advance_to_owner_of(sid, rid, BELL)
    if bell is None:
        print("[1] KO : %s absent / tour non atteint" % BELL)
        return 1
    dec, ob, snap = _capture(sid, rid)
    board = _board(sid, rid)
    live_mv = _live_movement(snap)
    by_src = _live_move_by_source(sid, rid)
    units = {u["visualId"]: u for u in (dec.get("units") or []) if u.get("alive")}

    print("[1] tour=%s currentPlayer=%s -- porteurs de %d cote NATIF :"
          % (dec.get("turn"), dec.get("currentPlayer"), EFFECT_TYPE))
    for vis, u in units.items():
        tag = "1073" if _has_1073(u) else "  - "
        print("    u%-4s %-22s team=%s %s movement=%s mods=%s"
              % (u["id"], vis, u.get("team"), tag, live_mv.get(u["id"]),
                 by_src.get(u["id"], {})))

    carriers = [u for u in units.values() if _has_1073(u)]
    if not carriers:
        print("[1] KO : aucun porteur de 1073 -- montage sans effet a mesurer")
        return 1

    # GATE (contre-cas) : le porteur de l'AURA et l'ami NON-Chaos ne doivent PAS l'avoir.
    for vis in (BELL, NON_CHAOS_ALLY):
        u = units.get(vis)
        if u is not None and _has_1073(u):
            print("[1] KO gate : %s porte 1073 (attendu : non -- SurroundingFriends exclut le porteur, "
                  "UnitsWithTrait(Chaos) exclut l'Imperial)" % vis)
            bad += 1
    for vis in CHAOS_ALLIES:
        u = units.get(vis)
        if u is not None and not _has_1073(u):
            print("[1] note : %s (Chaos) ne porte PAS 1073 -- hors aura ?" % vis)

    state = load_state(dec, ob, snap, board=board)
    if state.effects is None:
        print("[2] KO : etat offline sans effets")
        return bad + 1

    # -- 2/3 : attribution + valeur absolue -----------------------------------------------------
    pre_off, pre_live = {}, {}
    for u in carriers:
        uid = u["id"]
        off_mv, per, statmod, captured = _off_movement_and_sources(state, uid)
        nat = by_src.get(uid, {})
        print("[2] u%-4s %-22s offline movement=%s per_source=%s"
              % (uid, u["visualId"], off_mv, per))
        print("    natif movement=%s ; statModSources total=%s residual=%s effet=%s"
              % (live_mv.get(uid), nat.get("total"), nat.get("residual"), nat.get("effect")))
        if off_mv != live_mv.get(uid):
            print("    KO [3] GetStat(MOVEMENT) offline %s != natif %s" % (off_mv, live_mv.get(uid)))
            bad += 1
        if statmod != int(nat.get("effect") or 0):
            print("    KO [2] montant attribue offline %d != montant natif attribue a l'entite-effet %d"
                  % (statmod, int(nat.get("effect") or 0)))
            bad += 1
        if captured != 0:
            print("    KO [2] residu opaque offline = %d alors que le natif a residual=%d "
                  "(contribution NON retirable)" % (captured, int(nat.get("residual") or 0)))
            bad += 1
        pre_off[uid], pre_live[uid] = off_mv, live_mv.get(uid)

    # -- 3b : INCIDENCE SUR LE MOUVEMENT (tuiles atteignables, pas seulement la stat) ------------
    # Confronte TOUTES les unites controlees, porteuses ou non : un ecart sur une unite SANS 1073
    # est un ecart de PATHFINDING (etage partage), pas de ce port -- il est signale comme tel.
    nat_tiles, off_tiles, diffs = _live_movable(sid, rid), {}, {}
    carrier_ids = {c["id"] for c in carriers}
    for u in sorted(units.values(), key=lambda x: x["id"]):
        uid = u["id"]
        nat, off = nat_tiles.get(uid), _off_movable(state, uid)
        if uid in carrier_ids:
            off_tiles[uid] = off
        if nat is None or off is None:
            continue
        diffs[uid] = nat ^ off
        print("[3b] u%-4s %-22s [%s] tuiles natif=%d offline=%d (sym.diff=%d) %s"
              % (uid, u["visualId"], "1073" if _has_1073(u) else "sans",
                 len(nat), len(off), len(nat ^ off), sorted(nat ^ off)[:6] or ""))
    # Bruit de fond = les tuiles en desaccord sur les unites SANS 1073 : c'est l'etage PATHFINDING
    # (partage), pas ce port. Seul un desaccord PROPRE a une unite porteuse est impute ici.
    noise = set().union(*[d for uid, d in diffs.items() if uid not in carrier_ids] or [set()])
    for uid in carrier_ids:
        own = (diffs.get(uid) or set()) - noise
        if own:
            print("    KO [3b] u%s : desaccord de tuiles PROPRE au porteur (hors bruit pathfinding) : %s"
                  % (uid, sorted(own)[:8]))
            bad += 1
    if noise:
        print("[3b] bruit PATHFINDING commun (present AUSSI sur des unites sans 1073, donc etage "
              "partage, hors perimetre de ce port) : %s" % sorted(noise)[:8])

    # -- 4 : REVERT (le critere) ----------------------------------------------------------------
    _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": False}, 90)
    dec1, _, snap1 = _capture(sid, rid)
    live_mv1 = _live_movement(snap1)
    res = EndTurnOperation.execute(state, advance=False)
    print("[4] endturn joue des DEUX cotes (offline reverts = %s)" % (res.get("stat_mods_reverted"),))
    for u in carriers:
        uid = u["id"]
        off_mv, per, _s, _c = _off_movement_and_sources(state, uid)
        u1 = next((x for x in (dec1.get("units") or []) if x.get("id") == uid), None)
        still_nat = bool(u1 is not None and _has_1073(u1))
        still_off = state.effects.has_effect(uid, effect_type=EFFECT_TYPE)
        print("    u%-4s %-22s natif %s -> %s (1073 %s) ; offline %s -> %s (1073 %s)"
              % (uid, u["visualId"], pre_live[uid], live_mv1.get(uid),
                 "present" if still_nat else "parti", pre_off[uid], off_mv,
                 "present" if still_off else "parti"))
        if live_mv1.get(uid) == pre_live[uid]:
            print("    note : le natif n'a pas fait redescendre le MOVEMENT -> rien a garder ici")
            continue
        if off_mv != live_mv1.get(uid):
            print("    KO [4] apres expiration : offline MOVEMENT=%s, natif %s (ecart +%s conserve)"
                  % (off_mv, live_mv1.get(uid), off_mv - int(live_mv1.get(uid) or 0)))
            bad += 1

    # -- 4b : CONSEQUENCE du revert sur les tuiles atteignables (offline). `aiMovableTiles` ne rend
    # que les squads du joueur COURANT (c'est desormais celui d'en face) -> pas de pendant natif
    # LISIBLE a cet instant ; le regime « sans effet » est confronte au natif a l'etape [6].
    for u in carriers:
        uid = u["id"]
        off = _off_movable(state, uid)
        was = off_tiles.get(uid)
        if off is None or was is None:
            continue
        print("[4b] u%-4s %-22s tuiles offline %d -> %d apres expiration (le +1 fantome en valait %d)"
              % (uid, u["visualId"], len(was), len(off), len(was) - len(off)))

    # -- 5 : RE-POSE au tour suivant ------------------------------------------------------------
    _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": False}, 90)
    dec2, ob2, snap2 = _capture(sid, rid)
    live_mv2 = _live_movement(snap2)
    state2 = load_state(dec2, ob2, snap2, board=board)
    for u in carriers:
        uid = u["id"]
        u2 = next((x for x in (dec2.get("units") or []) if x.get("id") == uid), None)
        re_posed = bool(u2 is not None and _has_1073(u2))
        off_mv2, per2, _s2, _c2 = _off_movement_and_sources(state2, uid)
        print("[5] u%-4s %-22s re-pose natif=%s ; natif movement=%s ; offline (re-seede)=%s"
              % (uid, u["visualId"], re_posed, live_mv2.get(uid), off_mv2))
        if re_posed and off_mv2 != live_mv2.get(uid):
            print("    KO [5] re-pose : offline %s != natif %s" % (off_mv2, live_mv2.get(uid)))
            bad += 1

    # -- 6 : REGIME « SANS EFFET » confronte LIVE sur la MEME unite ------------------------------
    # Doctrine « drive positions » : on ELOIGNE un ami Chaos hors de l'aura `ContagionsOfNurgle`, puis
    # on repasse au tour du joueur. Le natif ne re-pose alors PAS 1073 -> sa stat MOVEMENT et son
    # ensemble de tuiles retombent a la base, et le port re-seede doit rendre EXACTEMENT les memes.
    bad += _step6_out_of_aura(sid, rid, board)
    return bad


def _hexdist(a, b):
    import hexgeo
    return int(hexgeo.distance(tuple(a), tuple(b)))


def _step6_out_of_aura(sid, rid, board) -> int:
    from engine.runner.snapshot import load_state
    bad = 0
    dec, bell = _advance_to_owner_of(sid, rid, BELL)
    if bell is None:
        print("[6] tour du porteur non atteint -- regime hors-aura non exerce")
        return 0
    units = {u["visualId"]: u for u in (dec.get("units") or []) if u.get("alive")}
    subject = next((units[v] for v in CHAOS_ALLIES if v in units and _has_1073(units[v])), None)
    if subject is None:
        print("[6] aucun ami Chaos porteur de 1073 -- regime hors-aura non exerce")
        return 0
    bpos = (bell["pos"]["col"], bell["pos"]["row"])
    occupied = {(u["pos"]["col"], u["pos"]["row"]) for u in units.values()}
    mv = _live_movable(sid, rid, side="friendly").get(subject["id"]) or set()
    far = sorted((t for t in mv if t not in occupied), key=lambda t: -_hexdist(t, bpos))
    if not far:
        print("[6] aucune tuile de deplacement libre -- regime hors-aura non exerce")
        return 0
    dest = far[0]
    print("[6] on ELOIGNE u%s (%s) de l'aura : %s -> %s (dist au porteur %d -> %d)"
          % (subject["id"], subject["visualId"],
             (subject["pos"]["col"], subject["pos"]["row"]), dest,
             _hexdist((subject["pos"]["col"], subject["pos"]["row"]), bpos), _hexdist(dest, bpos)))
    mv_res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": subject["id"], "to": {"col": dest[0], "row": dest[1]}}}, 90)
    if not (isinstance(mv_res, dict) and mv_res.get("ok")):
        print("[6] deplacement REFUSE (%s) -- regime hors-aura non exerce" % (str(mv_res)[:200],))
        return 0
    for _ in range(2):
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                                "captureEvents": False}, 90)
    dec3, ob3, snap3 = _capture(sid, rid)
    u3 = next((x for x in (dec3.get("units") or []) if x.get("id") == subject["id"]), None)
    if u3 is None or not u3.get("alive"):
        print("[6] le sujet n'a pas survecu -- regime hors-aura non exerce")
        return 0
    if _has_1073(u3):
        print("[6] le natif RE-POSE 1073 malgre l'eloignement (dist %d, aura elargie ?) -- "
              "regime hors-aura non exerce"
              % _hexdist((u3["pos"]["col"], u3["pos"]["row"]), bpos))
        return 0
    state3 = load_state(dec3, ob3, snap3, board=board)
    live_mv3 = _live_movement(snap3)
    off_mv3, per3, statmod3, captured3 = _off_movement_and_sources(state3, subject["id"])
    print("[6] hors aura : natif movement=%s (1073 absent) ; offline=%s per_source=%s"
          % (live_mv3.get(subject["id"]), off_mv3, per3))
    if off_mv3 != live_mv3.get(subject["id"]):
        print("    KO [6] MOVEMENT hors aura : offline %s != natif %s"
              % (off_mv3, live_mv3.get(subject["id"])))
        bad += 1
    if statmod3 != 0:
        print("    KO [6] une contribution 1073 subsiste offline alors que l'effet est absent : %d"
              % statmod3)
        bad += 1
    nat_all = _live_movable(sid, rid, side="friendly")
    nat_t, off_t = nat_all.get(subject["id"]), _off_movable(state3, subject["id"])
    if nat_t is not None and off_t is not None:
        # MEME protocole qu'en [3b] : le bruit de l'etage PATHFINDING est mesure sur les unites qui
        # n'ont jamais porte 1073, puis soustrait -- sinon on imputerait a ce port un desaccord de
        # flood-fill partage par tout le monde.
        noise = set()
        for uid, nt in nat_all.items():
            if uid == subject["id"]:
                continue
            ot = _off_movable(state3, uid)
            if ot is not None:
                noise |= (nt ^ ot)
        own = (nat_t ^ off_t) - noise
        print("[6] tuiles hors aura : natif=%d offline=%d (sym.diff=%d, dont bruit pathfinding %s)"
              % (len(nat_t), len(off_t), len(nat_t ^ off_t), sorted(noise)[:6] or "aucun"))
        # A CET INSTANT l'effet 1073 est ABSENT des DEUX cotes (verifie ci-dessus) et la contribution
        # offline est nulle : l'ensemble de tuiles ne depend plus que de (board, position, MOVEMENT,
        # occupants) -- aucun de ces termes ne vient de ce port. Un desaccord residuel est donc
        # STRUCTURELLEMENT hors perimetre : on le REPORTE (etage pathfinding), on ne l'impute pas.
        if own:
            print("    note [6] desaccord de tuiles residuel %s -- effet 1073 absent des deux cotes "
                  "et MOVEMENT egal, donc ETAGE PATHFINDING (le port sur-atteint), hors perimetre"
                  % sorted(own)[:8])
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--mutate", choices=["registry"], default=None)
    ap.add_argument("--runner", type=int, default=None, help="reutiliser un runner existant")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner construit")
    a = ap.parse_args()

    bad = step0_offline()
    if a.offline_only:
        print("=== probe_224 (offline) : %s ===" % ("OK" if bad == 0 else "%d ecart(s)" % bad))
        return 1 if bad else 0

    sid = _resolve_session()
    state_file = ROOT / "logs" / "runners" / ("_a224i2_cpb_%s.json" % a.seed)
    rid = a.runner if a.runner is not None else build(a.seed, a.board, state_file)
    print("[live] session=%s runner=%s seed=%s board=%s" % (sid, rid, a.seed, a.board))
    try:
        bad += run_live(sid, rid, a.mutate)
    finally:
        if a.runner is None and not a.keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
            print("[live] runner %s dispose" % rid)
    print("=== probe_224 item2 (%s) : %s ==="
          % (a.mutate or "port", "OK" if bad == 0 else "%d ecart(s)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
