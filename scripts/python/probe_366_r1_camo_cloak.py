"""case-366-r1 -- MONTAGE LIVE de `1014 CamoCloak_DmgReduction` (porteur `ultraEliminatorSgt`
<<Certus>>, owner-effect PERMANENT pose par son passif `CamoCloak` 1003).

CRITERE BINAIRE : << le port retire du degat RANGED recu par Certus exactement ce que le natif
retire, et se TAIT exactement quand le natif se tait ? >>

Le natif a DEUX faces, et un montage qui n'en exerce qu'une ne prouve rien :

  * `...CamoCloak_DmgReductionEffect$$CreateActiveCondition` = `HasValidEffectTrigger(Owner@0x148)`
    = `HasEffect(sel, 1013 LightCover, onlyActive=0, 6) | IsEffectTarget(sel, 1026
    BigTarget_Adjacent)`. C'est un gate de COUVERT, et il est MESURABLE DIRECTEMENT cote natif :
    `EffectComponent.IsActive` est publie en `decisionView.effects[].active`, et le canal PAR DEFAUT
    DROPPE les inactifs.
  * `...$$CreateDamageModifier` = `ForAddition(OwnerIsTarget & HasValidEffectTrigger(Target@0x178)
    & IsRangedAttack, Multiply(ConfigVar(0x12 = dmgReduction), Direct(-1)))` -> slot +0x10 cote
    DEFENSEUR = `flat_reductions`, additif PLAT **PRE-percage**.

Les trois regimes de COUVERT (`--cover`), qui sont le coeur du cas :

  bigtarget  -- un ami portant le trait `BigTarget` (`astraBullgryn`) est place RING-1 de Certus.
                Son aura `1026 BigTarget_AdjacentEffect` fait de Certus une CIBLE -> 2e membre du
                `op_BitwiseOr`. Ne demande AUCUN terrain particulier.
  lightcover -- Certus est DEPLACE sur une tuile `DryBush`, qui HEBERGE `LightCoverAbility` : celle-ci
                pose `1013 LightCover` sur les unites qui s'y tiennent -> 1er membre du `op_BitwiseOr`.
  none       -- ni l'un ni l'autre : le natif doit ETEINDRE l'effet (absent du canal actif) et ne
                retirer AUCUN degat.

Etages mesures (chacun separement, jamais un scalaire fitte) :

  E1 -- GATE DE COUVERT, cote NATIF. Presence de `1014` dans `decisionView.effects` (canal actif)
        + son flag `active` dans le canal `includeInactive: true`. Aucune deduction du port.
  E2 -- DEGAT RANGED. Le meme coup joue LIVE et rejoue OFFLINE sur la MEME capture et le MEME flux
        MT. Trois valeurs : `live`, `port`, et la CONTRE-EPREUVE `port_sans_effet` (instance 1014
        retiree du monde offline). Sans la 3e, << port == live >> ne prouverait pas que la
        reduction change quoi que ce soit dans ce montage.
  E3 -- CONTREFACTUEL DE COUVERT (offline, regime `bigtarget`). MEME capture, MEME flux : on RETIRE
        l'aura 1026 du monde offline. Le port doit alors rendre EXACTEMENT `port_sans_effet` --
        c'est ce qui prouve que sa `CreateActiveCondition` est PORTEUSE et pas decorative.
  E4 -- AXE MELEE (`--axis melee`) : meme effet ACTIF, coup de MELEE. Le gate `IsRangedAttack` doit
        fermer -- natif ET port -- donc `live == port == port_sans_effet`.

L'armure de Certus est mise a 0 (`--hp-player`) : la reduction PLATE est PRE-percage, donc a armure
nulle elle se lit 1 pour 1 sur le degat. `--dmg-target` remonte la frappe ennemie au-dessus de la
reduction (sinon le degat plancherait et la mesure serait aveugle).

Usage :
    python probe_366_r1_camo_cloak.py --cover bigtarget  --axis ranged --board MC1_67 --seed 31337
    python probe_366_r1_camo_cloak.py --cover lightcover --axis ranged --board C4_09  --seed 4242
    python probe_366_r1_camo_cloak.py --cover none       --axis ranged --board MC1_67 --seed 31337

Consommateur pytest : `tests/engine/runner/test_camo_cloak_dmg_reduction_live.py`.
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parent.parent

CARRIER = "ultraEliminatorSgt"   # <<Certus>> -- HERO, dans le pool spawnable du rank courant
BIG = "astraBullgryn"            # <<Kut>> -- HERO au pool, porte le trait `BigTarget` (aura 1026)
FOE = "necroWarden"              # <<Makhotep>> -- UNE arme melee ET une arme ranged r3 : le MEME
#                                  ennemi sert les deux axes, une variable de moins
ABILITY = "CamoCloak"
ABILITY_ID = 1003                # 0x3eb -- TriggeredAbilityType (le `.ctor` de l'effet l'ecrit en edx)
EFFECT = 1014                    # 0x3f6 -- EffectType CamoCloak_DmgReduction
LIGHT_COVER = 1013               # 0x3f5 -- EffectType LightCover
BIG_TARGET_ADJ = 1026            # 0x402 -- EffectType BigTarget_AdjacentEffect
COVER_TILE = "DryBush"           # le TileId qui HEBERGE `LightCoverAbility` (cf. `utilities/tile.py`)

DMG_TARGET = 20000               # frappe ennemie >> reduction (sinon plancher, mesure aveugle)
HP_PLAYER = 400000               # Certus encaisse plusieurs echanges ; met AUSSI son armure a 0
HP_TARGET = 300000               # l'ennemi SURVIT a l'overwatch de Certus pendant l'approche
BOARD = "MC1_67"
SEED = "31337"


# --------------------------------------------------------------------------- build
def build_args(board: str, cover: str, passive_level: "int | None" = None) -> list:
    """`--hp-player` met l'armure de Certus a 0 (lecture 1:1 de la reduction PRE-percage).
    `--unit-stat PassiveAbilityLevel=N` DISSOCIE le niveau PASSIF du niveau ACTIF, que la
    normalisation met tous deux a 50 : c'est le SEUL regime qui discrimine lequel des deux indexe
    `variables["dmgReduction"]`, donc le seul qui puisse REFUTER la lecture << `GetAbilityState
    (effet)` = l'AbilityState d'une TRIGGERED >> tiree du `.ctor` (`mov edx, 0x3eb` puis la
    surcharge `AbilityOrEffect$$op_Implicit` qui appelle `set_TriggeredAbility`)."""
    p_units = CARRIER if cover != "bigtarget" else "%s,%s" % (CARRIER, BIG)
    out = ["--p-units", p_units, "--a-units", FOE,
           "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0",
           "--hp-player", str(HP_PLAYER), "--hp-target", str(HP_TARGET),
           "--dmg-target", str(DMG_TARGET),
           "--board", board]
    if passive_level is not None:
        out += ["--unit-stat", "%s:PassiveAbilityLevel=%d" % (CARRIER, int(passive_level))]
    return out


def _build_subprocess(seed: str, tag: str, board: str, cover: str,
                      passive_level: "int | None" = None) -> int:
    state = _ROOT / "logs" / ("_probe366r1camo-%s-%d.json" % (tag, os.getpid()))
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), *build_args(board, cover, passive_level)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return int(json.loads(state.read_text())["runnerId"])


# --------------------------------------------------------------------------- lecture live
def _unit(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _by_vis(dec, vis):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def _eff(u, etype):
    return next((e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype), None)


def live_amounts(res, target_id):
    """Per-coup LIVE attribues a `target_id`, dans l'ordre des events + flag de salete (crit /
    block / evade rendraient le coup non comparable a un rejeu deterministe)."""
    out, dirty = [], False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") == target_id and "Amount" in td:
                out.append(int(td.get("Amount")))
                dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock")) \
                    or bool(td.get("Attack_DidEvade"))
    return out, dirty


# --------------------------------------------------------------------------- pilotage
def _endturn(rpc, rid):
    return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                               "captureEvents": False}, 90)


def _movable(rpc, rid, uid):
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def _place_at_distance(rpc, rid, mover_vis, anchor_vis, want, tries=25):
    """DEPLACE `mover_vis` jusqu'a la distance hex `want` d'`anchor_vis`. On FABRIQUE la geometrie,
    on ne la subit pas -- le meme ennemi sert l'axe ranged (3) et l'axe melee (1), et le meme
    levier place l'ami `BigTarget` en ring-1 (1)."""
    import hexgeo
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        mv, an = _by_vis(dv, mover_vis), _by_vis(dv, anchor_vis)
        if mv is None or an is None:
            return None
        mpos = (mv["pos"]["col"], mv["pos"]["row"])
        apos = (an["pos"]["col"], an["pos"]["row"])
        if hexgeo.distance(mpos, apos) == want:
            return want
        if dv.get("currentPlayer") != mv.get("owner"):
            _endturn(rpc, rid)
            continue
        tiles = _movable(rpc, rid, mv["id"])
        if not tiles:
            _endturn(rpc, rid)
            continue
        best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, apos) - want),
                                         hexgeo.distance(t, apos)))
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": best[0], "row": best[1]}},
            "captureEvents": False}, 90)
        if hexgeo.distance(best, apos) == want:
            return want
        _endturn(rpc, rid)
    return None


def _cover_positions(rpc, rid) -> set:
    """Positions dont le terrain BC est `DryBush` -- les tuiles qui HEBERGENT `LightCoverAbility`
    (`IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$CreateBehaviour` =
    `AddEffect(0x3f5, state, UnitsThatNeedEffect())`, l'effet est pose sur les UNITES qui s'y
    tiennent)."""
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    out = set()
    for t in (bg.get("tiles") or []):
        tid = t.get("tileDefId") or t.get("terrain") or t.get("tileId")
        if tid == COVER_TILE:
            out.add((t.get("col"), t.get("row")))
    return out


def _move_onto_cover(rpc, rid, vis, cover_pos, tries=20):
    """DEPLACE `vis` sur une tuile de couvert. Sweep multi-tours : la portee d'un pas ne suffit pas
    toujours -- on avance vers la plus proche a chaque tour du porteur."""
    import hexgeo
    if not cover_pos:
        return None
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        mv = _by_vis(dv, vis)
        if mv is None:
            return None
        here = (mv["pos"]["col"], mv["pos"]["row"])
        if here in cover_pos:
            return here
        if dv.get("currentPlayer") != mv.get("owner"):
            _endturn(rpc, rid)
            continue
        tiles = _movable(rpc, rid, mv["id"])
        onto = [t for t in tiles if t in cover_pos]
        if onto:
            tgt = onto[0]
        elif tiles:
            goal = min(cover_pos, key=lambda c: hexgeo.distance(here, c))
            tgt = min(tiles, key=lambda t: hexgeo.distance(t, goal))
            if tgt == here:
                _endturn(rpc, rid)
                continue
        else:
            _endturn(rpc, rid)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": tgt[0], "row": tgt[1]}},
            "captureEvents": False}, 90)
        if tgt in cover_pos:
            return tgt
        _endturn(rpc, rid)
    return None


def _ensure_turn(rpc, rid, owner, tries=8):
    """Fait tourner les fins de tour jusqu'a ce que `owner` soit le joueur courant. La CAPTURE doit
    etre prise dans le MEME etat de tour que le coup mesure."""
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if dv.get("currentPlayer") == owner:
            return dv
        _endturn(rpc, rid)
    return None


# --------------------------------------------------------------------------- offline
def _capture(rpc, rid):
    return {
        "dv": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "dv_inactive": rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                            "includeInactive": True}, 150),
        "ob": rpc("observeBattle", {"runnerId": rid}, 90),
        "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
        "rng": rpc("dumpRng", {"runnerId": rid}, 40),
    }


def _load(cap, board):
    from engine.runner.snapshot import load_state
    return load_state(cap["dv"], cap["ob"], cap["snap"], board=board)


def _strip_effect(st, carrier_id, etype=EFFECT):
    """CONTRE-EPREUVE : retire une instance du monde offline (marquee consommee)."""
    for e in (st.effects.by_unit.get(carrier_id) or []):
        if e.effect_type == etype:
            e.consumed = True


def _strip_cover(st, carrier_id):
    """CONTREFACTUEL DE COUVERT : retire des SUPPORTS du gate `HasValidEffectTrigger`, sans toucher
    a l'instance 1014 elle-meme -- donc c'est bien la `CreateActiveCondition` PORTEE qui doit
    fermer, pas l'absence de l'effet :
      * `1013 LightCover` porte par Certus         -> 1er membre du `op_BitwiseOr` ;
      * `1026 BigTarget_Adjacent` porte par un ami -> 2e membre.
    """
    _strip_effect(st, carrier_id, LIGHT_COVER)
    for uid in list(st.effects.by_unit.keys()):
        _strip_effect(st, uid, BIG_TARGET_ADJ)


def offline_hits(cap, board, caster_id, target_id, strip=False, strip_cover=False):
    """Rejoue le MEME coup OFFLINE sur la MEME capture et le MEME flux MT -> per-coup du port.
      * `strip`       : sans l'instance 1014 (contre-epreuve de discriminance) ;
      * `strip_cover` : avec 1014 mais SANS son support de couvert (contrefactuel de la
        `CreateActiveCondition`)."""
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    st = _load(cap, board)
    if strip:
        _strip_effect(st, target_id)
    if strip_cover:
        _strip_cover(st, target_id)
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(caster_id, target_id))
    last = getattr(getattr(runner, "damage_handler", None), "last", None)
    return list((last or {}).get("per_hit") or [])


def offline_effect_view(cap, board, carrier_id):
    """Ce que le PORT materialise pour 1014 sur cette capture : presence, classe, niveau lu, et le
    bonus rendu dans les 4 regimes de gate. Etage SEPARE du degat -- un port qui n'aurait PAS
    l'effet et un port dont le gate ferme rendent le meme degat."""
    from engine.runner.components import unit_state_for_effects
    st = _load(cap, board)
    inst = next((e for e in (st.effects.by_unit.get(carrier_id) or [])
                 if e.effect_type == EFFECT), None)
    us = unit_state_for_effects(st, carrier_id)
    view = {"present": inst is not None,
            "us_light_cover": us.get("has_effect_light_cover"),
            "us_big_target": us.get("is_target_of_big_target_adjacent"),
            "port_has_1013": bool(st.effects.has_effect(carrier_id, LIGHT_COVER)),
            "in_active_effects": any(
                e.effect_type == EFFECT for e in st.effects.active_effects(carrier_id, us))}
    if inst is None:
        return view
    def _b(is_melee):
        eb = inst.create_effect_damage_malus_for_defense(is_melee, None, None)
        return None if eb is None else [eb.kind, eb.value]
    view.update({"cls": type(inst).__name__,
                 "ability_level": inst.ability_level,
                 "active_ability_level": inst.active_ability_level,
                 "multiplier": inst.ability_variables_multiplier,
                 "is_active": bool(inst.is_active(us)),
                 "ranged": _b(False),          # le seul regime ou le natif soustrait
                 "melee": _b(True),
                 "unknown_nature": _b(None)})
    return view


def decision_effect_view(cap, board, carrier_id):
    """Face DECISION du MEME gate : `Scene.unit_state` / `Scene.effects` (pendant PREDICTION de
    `runner.components.unit_state_for_effects` / `EffectsState.active_effects`). Un fork
    << moteur != prediction >> se verrait ICI : memes cles, meme verdict d'activite, ou pas."""
    from engine.playbook.scene import Scene
    st = _load(cap, board)
    sc = Scene.from_state(st)
    us = sc.unit_state(carrier_id)
    return {"us_light_cover": us.get("has_effect_light_cover"),
            "us_big_target": us.get("is_target_of_big_target_adjacent"),
            "in_scene_effects": any(e.effect_type == EFFECT for e in sc.effects(carrier_id))}


# --------------------------------------------------------------------------- montage
def run(rpc, cover: str = "bigtarget", axis: str = "ranged", seed: str = SEED,
        board_id: str = BOARD, keep: bool = False,
        passive_level: "int | None" = None) -> dict:
    r = {"cover": cover, "axis": axis, "seed": seed, "board": board_id, "rid": None,
         "passive_level_forced": passive_level}
    try:
        _run(rpc, r, cover, axis, seed, board_id, passive_level)
    except Exception as exc:                              # montage KO -> ERREUR, jamais un vert
        r["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if not keep and r.get("rid") is not None:
            try:
                rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
            except Exception:                             # nettoyage best-effort
                pass
    return r


def _run(rpc, r: dict, cover: str, axis: str, seed: str, board_id: str,
         passive_level: "int | None" = None) -> None:
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board

    want_dist = 1 if axis == "melee" else 3
    r["want_dist"] = want_dist

    rid = _build_subprocess(seed, "%s-%s" % (cover, axis), board_id, cover, passive_level)
    r["rid"] = rid
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    car, foe = _by_vis(dv0, CARRIER), _by_vis(dv0, FOE)
    if car is None or foe is None:
        raise RuntimeError("porteur/cible absents du deploiement")
    r["carrier_id"], r["foe_id"] = car["id"], foe["id"]
    r["carrier_owner"], r["foe_owner"] = car.get("owner"), foe.get("owner")

    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 120)
    _uc0 = next((u.get("unitConfig") or {} for u in (snap0.get("units") or [])
                 if u.get("entityId") == car["id"]), {})
    r["passive_level"] = _uc0.get("passiveAbilityLevel")
    r["active_level"] = _uc0.get("activeAbilityLevel")
    r["multiplier"] = _uc0.get("abilityVariablesMultiplier")
    mult = r["multiplier"] or 100
    r["dmg_reduction_config"] = ability_var(ABILITY, "dmgReduction", r["passive_level"],
                                            multiplier_pct=mult)
    # Ce que la MEME formule donnerait si le niveau lu etait l'ACTIF : discriminant SEULEMENT quand
    # les deux sont dissocies (`--unit-stat PassiveAbilityLevel=N`).
    r["dmg_reduction_if_active"] = ability_var(ABILITY, "dmgReduction", r["active_level"],
                                               multiplier_pct=mult)

    # -- geometrie de COUVERT, FABRIQUEE ------------------------------------------------------
    if cover == "bigtarget":
        big = _by_vis(dv0, BIG)
        if big is None:
            raise RuntimeError("l'ami BigTarget (%s) est absent du deploiement" % BIG)
        r["big_id"] = big["id"]
        if _place_at_distance(rpc, rid, BIG, CARRIER, 1) != 1:
            raise RuntimeError("ami BigTarget non amene en ring-1 de Certus")
    elif cover == "lightcover":
        cpos = _cover_positions(rpc, rid)
        r["cover_tiles"] = len(cpos)
        if not cpos:
            raise RuntimeError("board %s sans tuile %s" % (board_id, COVER_TILE))
        landed = _move_onto_cover(rpc, rid, CARRIER, cpos)
        if landed is None:
            raise RuntimeError("Certus n'a pas atteint une tuile %s" % COVER_TILE)
        r["carrier_pos"] = list(landed)

    # -- E1 : GATE DE COUVERT, cote NATIF -----------------------------------------------------
    dva = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    dvi = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                               "includeInactive": True}, 150)
    ea, ei = _eff(_unit(dva, car["id"]), EFFECT), _eff(_unit(dvi, car["id"]), EFFECT)
    r["nat_in_active_channel"] = ea is not None
    r["nat_active_flag"] = None if ei is None else ei.get("active")
    r["nat_effects_inactive_channel"] = [(e.get("effectType"), e.get("name"), e.get("active"))
                                         for e in ((_unit(dvi, car["id"]) or {}).get("effects")
                                                   or [])]
    r["nat_has_1013"] = _eff(_unit(dvi, car["id"]), LIGHT_COVER) is not None
    if cover == "bigtarget":
        r["nat_big_has_1026"] = _eff(_unit(dvi, r.get("big_id")), BIG_TARGET_ADJ) is not None

    # -- geometrie d'ATTAQUE : l'ennemi a `want_dist` de Certus --------------------------------
    if _place_at_distance(rpc, rid, FOE, CARRIER, want_dist) != want_dist:
        raise RuntimeError("distance %s non atteinte (axe %s)" % (want_dist, axis))
    if _ensure_turn(rpc, rid, foe["owner"]) is None:
        raise RuntimeError("tour ennemi non atteint")
    # les fins de tour ont pu casser la geometrie -> on la REFABRIQUE
    if _place_at_distance(rpc, rid, FOE, CARRIER, want_dist) != want_dist:
        raise RuntimeError("distance %s non retablie avant le coup" % want_dist)
    if _ensure_turn(rpc, rid, foe["owner"]) is None:
        raise RuntimeError("tour ennemi non retabli")

    # -- E2/E3/E4 : le COUP -------------------------------------------------------------------
    cap = _capture(rpc, rid)
    r["capture_current_player"] = cap["dv"].get("currentPlayer")
    r["port_effect_view"] = offline_effect_view(cap, board, car["id"])
    r["decision_effect_view"] = decision_effect_view(cap, board, car["id"])

    foe_row = _unit(cap["dv"], foe["id"])
    norm = next((a for a in ((foe_row or {}).get("abilities") or [])
                 if a.get("kind") == "normal"), None)
    if norm is None:
        raise RuntimeError("aucune attaque normale exposee sur l'ennemi")
    resA = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": foe["id"], "targetId": car["id"],
        "abilityType": norm["id"]}}, 150)
    if not (isinstance(resA, dict) and resA.get("ok")):
        raise RuntimeError("coup live KO: %s" % (str(resA)[:200],))
    hits, dirty = live_amounts(resA, car["id"])
    if not hits:
        raise RuntimeError("coup joue mais aucun degat attribue au porteur")
    r["live_hits"], r["dirty"] = hits, dirty

    r["port_hits"] = offline_hits(cap, board, foe["id"], car["id"])
    r["port_hits_no_effect"] = offline_hits(cap, board, foe["id"], car["id"], strip=True)
    r["port_hits_no_cover"] = offline_hits(cap, board, foe["id"], car["id"], strip_cover=True)
    r["agree"] = (r["live_hits"] == r["port_hits"])
    r["discriminant"] = (r["port_hits"] != r["port_hits_no_effect"])
    # ⚠ Le contrefactuel de couvert se compare COUP A COUP, jamais liste a liste : retirer le
    # support (`1013` ou `1026`) retire du MEME geste sa reduction de COUPS (LightCover -2 ranged,
    # BigTarget_Adjacent -1 ranged) -- c'est litteralement ce que dit l'i2 (<< whenever an incoming
    # ranged attack has its NUMBER OF HITS reduced >>). Le nombre de coups change donc, et c'est la
    # consequence NATIVE attendue, pas un artefact. Ce qu'on teste ici est que le PREMIER coup
    # retombe sur la valeur SANS reduction.
    r["cover_gate_bites"] = (r["port_hits_no_cover"][:1] == r["port_hits_no_effect"][:1]
                             and r["port_hits_no_cover"][:1] != r["port_hits"][:1])
    if r["live_hits"] and r["port_hits_no_effect"]:
        n = min(len(r["live_hits"]), len(r["port_hits_no_effect"]))
        r["delta_per_hit"] = sorted({r["port_hits_no_effect"][i] - r["live_hits"][i]
                                     for i in range(n)})


# --------------------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="case-366-r1 : montage live de 1014 CamoCloak")
    ap.add_argument("--cover", choices=("bigtarget", "lightcover", "none"), default="bigtarget")
    ap.add_argument("--axis", choices=("ranged", "melee"), default="ranged")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--passive-level", type=int, default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=120):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, a.cover, a.axis, a.seed, a.board, a.keep, a.passive_level)
    print(json.dumps(r, indent=1, default=str))
    if r.get("error"):
        return 1
    print("")
    print("[366-r1/1014/%s/%s] runner=%s board=%s seed=%s dist=%s"
          % (a.cover, a.axis, r["rid"], a.board, a.seed, r["want_dist"]))
    print("  config   : dmgReduction[PASSIF L%s] x mult %s = %s | si ACTIF L%s -> %s"
          % (r["passive_level"], r["multiplier"], r["dmg_reduction_config"],
             r["active_level"], r["dmg_reduction_if_active"]))
    print("  E1 GATE NATIF : 1014 canal actif=%s  IsActive=%s | 1013 sur Certus=%s | 1026 ami=%s"
          % (r["nat_in_active_channel"], r["nat_active_flag"], r["nat_has_1013"],
             r.get("nat_big_has_1026")))
    print("  PORT effet    : %s" % (json.dumps(r["port_effect_view"], default=str),))
    print("  E2 DEGAT      : live=%s  port=%s  (agree=%s)"
          % (r["live_hits"], r["port_hits"], r["agree"]))
    print("     CONTRE-EPREUVE (sans 1014, meme flux MT) : %s  (discriminant=%s, delta/coup=%s)"
          % (r["port_hits_no_effect"], r["discriminant"], r.get("delta_per_hit")))
    print("  E3 CONTREFACTUEL de couvert (1014 present, support retire) : %s  (gate mord=%s)"
          % (r["port_hits_no_cover"], r["cover_gate_bites"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
