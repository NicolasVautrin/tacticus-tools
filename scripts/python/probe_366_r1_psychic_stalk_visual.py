"""case-366-r1 -- MONTAGE LIVE de `1216 PsychicStalk_VisualEffect` (porteur `thousAhriman`
<<Ahriman>>, passif `PsychicStalk` / TriggeredAbilityType 1179).

CRITERE BINAIRE : << la classe native n'a AUCUN canal de gameplay -- est-ce MESURE, ou seulement
supposé ? -- et le seul predicat qu'elle porte (`CreateActiveCondition`) rend-il, cote port,
exactement ce que rend le natif ? >>

Le natif `IdunBattle.Entities.Effects.Loki.PsychicStalk_VisualEffectEffect` surcharge EXACTEMENT
quatre methodes, dont AUCUNE n'est un slot de sortie gameplay :

    CreateActiveCondition = op_LogicalNot( IsDead(Owner@DSLSelectors+0x30) )   == IsAlive(Owner)
    CreateTargetSelector  = Units( EntitiesWithAnyEffect(
                                       Tiles( Enemies(of = Owner@0x30,
                                                      entities = AllUnits@0x20, onlyAlive = 1) ),
                                       Fire = 5, effectTarget = 6 ), unique = 1, selectionType = 3 )
    GetRefreshTriggers    = int[3]  (non portable : le port n'a pas de `RefreshEffectTrigger`)
    .ctor

⚠ POURQUOI CE PROBE NE PEUT PAS SE CONTENTER D'UNE ABSENCE D'OBSERVABLE : un effet INERTE n'emet
rien, et un effet ABSENT non plus. Les epreuves ci-dessous mesurent donc des VALEURS DE RETOUR,
jamais un silence :

  E1 -- POSE + FLAG, cote NATIF. `1216` est-il sur Ahriman, et que vaut son `EffectComponent.IsActive
        @+0x5c` ? Lu sur le canal `includeInactive` de `decisionView` (le canal par defaut DROPPE
        les inactifs -- un zero lu la ne serait PAS une mesure). C'est la VALEUR DE RETOUR
        materialisee de `CreateActiveCondition`.
  E2 -- SELECTEUR, confronte sur ses ENTREES. Ahriman tire -> `PsychicStalk_ApplyFireTile` allume
        l'hex de la cible. L'ORACLE est INDEPENDANT du port : « ennemis VIVANTS d'Ahriman dont la
        main tile porte `Fire` », derive de `tileMeta` + `decisionView`. On compare l'ensemble
        designe par `target_selector_covers` a cet oracle, unite par unite.
        ⚠ La sortie MATERIALISEE du selecteur natif (`EffectComponent$$AddTargetId`, champ
        `EffectComponent+0x48`) n'est lue par AUCUN capteur : `readEffectsByUnit` ne publie que
        l'`EffectsOwnedComponent.ActiveEffectIds` du PORTEUR. C'est un residu NOMME, pas un trou
        ignore -- cf. la case-doc.
  E3 -- CONTRIBUTION AU DEGAT, MESUREE A ZERO. Le meme coup est rejoue offline AVEC et SANS `1216`
        dans le monde, sur la MEME capture et le MEME flux MT, avec la cible SUR un hex en feu
        (donc tous les gates du kit OUVERTS -- le regime le plus favorable a une contribution).
        Les deux per-coup doivent etre EGAUX AU BIT, et les DEUX etages (`attacker_modifiers` /
        `defender_modifiers`) identiques. C'est ce qui transforme « pas de canal » en MESURE.
  E4 -- LA BRANCHE FAUSSE de la condition (bras `--kill-carrier`). Le foe tue Ahriman ; on relit le
        flag `active` de `1216` cote NATIF, et on le compare a ce que rend le port. C'est le seul
        regime ou `IsAlive(Owner)` vaut FAUX.
  E5 -- DISCRIMINANCE OFFLINE du predicat porte. Sur la capture, on force `hp` du porteur a 0 dans
        le monde offline : le port doit ETEINDRE `1216` (`is_active` False, et
        `refresh_stat_modifier_effects` doit ECRIRE le flag puisque la condition est PORTEE), alors
        que le defaut `BaseEffect.is_active` -- celui qu'on aurait sans le port -- rend True.
        Sans ce temoin, l'accord d'E1 ne prouverait rien (tout rend True sur un porteur vivant).

Usage :
    python probe_366_r1_psychic_stalk_visual.py --board MC1_67 --seed 31337
    python probe_366_r1_psychic_stalk_visual.py --board C4_09  --seed 4242
    python probe_366_r1_psychic_stalk_visual.py --kill-carrier

Consommateur pytest : `tests/engine/runner/test_psychic_stalk_visual_effect_live.py`.
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

CARRIER = "thousAhriman"        # <<Ahriman>> -- HERO, dans le pool spawnable du rank courant
ALLY = "astraPrimarisPsy"       # Imperial, arme PSYCHIC r2 (1 coup) -> `1435` MUET (cf. #366-r1)
FOE = "necroWarden"             # encaisseur ATTAQUE ; ses passifs sont retires -> il porte le feu
FOE2 = "necroDestroyer"         # SECOND ennemi, JAMAIS attaque -> JAMAIS sur un hex en feu. C'est
#                                 lui qui rend l'exclusion du selecteur ANCREE LIVE : sans lui,
#                                 l'unique ennemi etant sur le feu, un port qui aurait OUBLIE le
#                                 gate `EntitiesWithAnyEffect(..., Fire)` rendrait le MEME ensemble.
EFFECT_EXTRA = 1215             # 0x4bf -- PsychicStalk_ExtraAttackDamage
EFFECT_VISUAL = 1216            # 0x4c0 -- PsychicStalk_VisualEffect  <-- LE SUJET
EFFECT_CHAOS = 1435             # 0x59b -- PsychicStalk_FriendlyChaosExtraDamage
FIRE = 5                        # EffectType.Fire -- ce que `PsychicStalk_ApplyFireTile` pose
HP_TARGET = 400000
HP_PLAYER = 300000
HP_PLAYER_FRAGILE = 1200        # bras `--kill-carrier` : le foe tue Ahriman en un ou deux coups
BOARD = "MC1_67"
SEED = "31337"


# --------------------------------------------------------------------------- build
def build_args(board: str, hp_player: int) -> list:
    """`PassiveAbilities=[]` sur l'ALLIE et la CIBLE : retire `Nightshroud` / `RelentlessMarch`, qui
    consomment du flux MT ou deplacent le defenseur. On ne touche PAS aux passifs d'Ahriman --
    `PsychicStalk` EST le sujet."""
    return ["--p-units", "%s,%s" % (CARRIER, ALLY), "--a-units", "%s,%s" % (FOE, FOE2),
            "--crit", "0,0", "--crit-target", "0,0",
            "--block-target", "0,0", "--block-player", "0,0",
            "--hp-target", str(HP_TARGET), "--hp-player", str(hp_player),
            "--board", board,
            "--unit-stat", "%s:PassiveAbilities=[]" % ALLY,
            "--unit-stat", "%s:PassiveAbilities=[]" % FOE,
            "--unit-stat", "%s:PassiveAbilities=[]" % FOE2]


def _build_subprocess(seed: str, board: str, tag: str, hp_player: int) -> int:
    state = _ROOT / "logs" / ("_probe366r1psv-%s-%d.json" % (tag, os.getpid()))
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), *build_args(board, hp_player)]
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


def _normal(u):
    return next((a for a in ((u or {}).get("abilities") or []) if a.get("kind") == "normal"), None)


def weapon_profile(vis: str, ranged: bool) -> "str | None":
    import gameconfig as GC
    ws = (GC.unit(vis) or {}).get("weapons") or []
    for w in ws:
        if bool(w.get("Range")) == bool(ranged):
            return w.get("DamageProfile")
    return (ws[0].get("DamageProfile") if ws else None)


def fire_tiles(tm) -> list:
    """Positions (col,row) portant l'effet `Fire` d'apres `tileMeta` -- l'ORACLE NATIF du gate,
    independant du port."""
    return [(t["col"], t["row"]) for t in ((tm or {}).get("tiles") or [])
            if any(e.get("effectType") == FIRE for e in (t.get("effects") or []))]


def live_amounts(res, target_id):
    """Per-coup LIVE attribues a `target_id`. `Effect_Type` SEPARE le coup d'attaque du DoT de l'hex
    en feu (`Effect_Type = 5`) -- les melanger comparerait une somme a un coup."""
    hits, other, dirty = [], [], False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") != target_id or "Amount" not in td:
                continue
            if td.get("Effect_Type") in (None, 0, 1009):
                hits.append(int(td.get("Amount")))
                dirty = dirty or bool(td.get("Attack_DidCrit")) \
                    or bool(td.get("Attack_DidBlock")) or bool(td.get("Attack_DidEvade"))
            else:
                other.append((int(td.get("Amount")), td.get("Effect_Type")))
    return hits, dirty, other


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
    """DEPLACE `mover_vis` jusqu'a la distance hex `want` d'`anchor_vis` -- on FABRIQUE la
    geometrie, on ne la subit pas."""
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


def _ensure_turn(rpc, rid, owner, tries=8):
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if dv.get("currentPlayer") == owner:
            return dv
        _endturn(rpc, rid)
    return None


def _attack(rpc, rid, caster, target):
    norm = _normal(caster)
    if norm is None:
        raise RuntimeError("aucune attaque normale exposee sur %s" % (caster.get("visualId"),))
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster["id"], "targetId": target["id"],
        "abilityType": norm["id"]}}, 150)
    if not (isinstance(res, dict) and res.get("ok")):
        raise RuntimeError("coup live KO: %s" % (str(res)[:200],))
    return res


# --------------------------------------------------------------------------- offline
def _capture(rpc, rid):
    return {
        "dv": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "dv_inactive": rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                            "includeInactive": True}, 150),
        "ob": rpc("observeBattle", {"runnerId": rid}, 90),
        "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
        "tm": rpc("tileMeta", {"runnerId": rid}, 90),
        "rng": rpc("dumpRng", {"runnerId": rid}, 40),
    }


def _load(cap, board):
    """`tiles=` INDISPENSABLE : sans le seed des effets de tuile l'etat offline repartirait d'un
    plateau VIERGE et le selecteur serait faux pour une raison de HARNAIS."""
    from engine.runner.snapshot import load_state
    return load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"])


def _strip_effect(st, carrier_id, etype):
    for e in (st.effects.by_unit.get(int(carrier_id)) or []):
        if e.effect_type == etype:
            e.consumed = True


def offline_hits(cap, board, caster_id, target_id, strip_effect_on=None, strip_etype=None):
    """Rejoue le MEME coup OFFLINE sur la MEME capture et le MEME flux MT."""
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    st = _load(cap, board)
    if strip_effect_on is not None and strip_etype is not None:
        _strip_effect(st, strip_effect_on, strip_etype)
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(caster_id, target_id))
    last = getattr(getattr(runner, "damage_handler", None), "last", None)
    return list((last or {}).get("per_hit") or [])


def offline_stages(cap, board, tgt_id, att_id, profile, strip_effect_on=None, strip_etype=None):
    """DECOMPOSITION PAR ETAGE, LES DEUX FACES. Un effet qui n'ecrit dans AUCUN slot doit laisser
    `attacker_modifiers` ET `defender_modifiers` bit-identiques quand on le retire."""
    from engine.runner.damage_model import attacker_modifiers, defender_modifiers
    st = _load(cap, board)
    if strip_effect_on is not None and strip_etype is not None:
        _strip_effect(st, strip_effect_on, strip_etype)
    dmods = defender_modifiers(st, tgt_id, None, is_melee=False, damage_profile=profile,
                               attacker_id=att_id, is_normal_attack=True)
    dmods = dmods[0] if isinstance(dmods, tuple) else dmods
    amods = attacker_modifiers(st, att_id, None, is_ranged=True, target_id=tgt_id,
                               is_normal_attack=True, damage_profile=profile)
    amods = amods[0] if isinstance(amods, tuple) else amods
    return {
        "def_pct": [[float(m), c] for m, c in (dmods.pct_list or [])],
        "def_additive": int(dmods.additive),
        "def_flat": list(dmods.flat_reductions or []),
        "att_pct": [[float(m), c] for m, c in (amods.pct_list or [])],
        "att_additive": int(amods.additive),
        "att_flat": list(amods.flat_reductions or []),
    }


def offline_selector_view(cap, board, carrier_id):
    """E2 -- le mirror de `CreateTargetSelector`, evalue PAR CANDIDAT sur l'etat charge, et
    l'ORACLE independant derive du live. Rend les DEUX ensembles pour comparaison."""
    from engine.runner.components import (OwnerComponent, PositionComponent, UnitComponent,
                                           unit_is_alive)
    from engine.runner.damage_model import tile_status_effects_by_pos
    st = _load(cap, board)
    inst = next((e for e in (st.effects.by_unit.get(int(carrier_id)) or [])
                 if e.effect_type == EFFECT_VISUAL), None)
    if inst is None:
        return {"present": False,
                "effects_on_carrier": sorted(e.effect_type for e in
                                             (st.effects.by_unit.get(int(carrier_id)) or []))}
    ent = st.get_entity(int(carrier_id))
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    owner_team = oc.team if oc is not None else None
    # Candidats = TOUTES les unites du plateau (le selecteur natif part d'`AllUnits@0x20`), et le
    # canal de tuile est demande sur LEURS positions (`tile_status_effects_by_pos(state, positions)`).
    cands = []
    for e, _uc in st.with_component(UnitComponent):
        pc, oc2 = e.get_component(PositionComponent), e.get_component(OwnerComponent)
        if pc is None or oc2 is None:
            continue
        cands.append((e.id, (pc.col, pc.row), oc2.team, unit_is_alive(e)))
    tfx = tile_status_effects_by_pos(st, [p for _i, p, _t, _a in cands]) or {}

    def _cov(**over):
        """Ensemble designe, avec UN conjoint du selecteur neutralise -- decomposition par ETAGE :
        chaque gate est eprouve SEPAREMENT sur l'etat live reel, pas sur un cas fabrique."""
        out = []
        for uid, pos, team, alive in cands:
            ctx = {"owner_team": owner_team, "tgt_team": team, "tgt_alive": alive,
                   "t_pos": pos, "tile_effects_by_pos": tfx}
            ctx.update(over)
            if inst.target_selector_covers(ctx):
                out.append(uid)
        return sorted(out)

    return {
        "present": True, "cls": type(inst).__name__, "owner_team": owner_team,
        "candidates": sorted(i for i, _p, _t, _a in cands),
        "covered": _cov(),
        # -- contrefactuels PAR CONJOINT (chacun doit VIDER l'ensemble) --
        "cov_no_fire": _cov(tile_effects_by_pos={}),        # EntitiesWithAnyEffect(Fire) ferme
        "cov_no_tile_channel": _cov(tile_effects_by_pos=None),   # canal absent -> restrictif
        # `AreEnemies` : on donne au PORTEUR l'equipe des foes -> ils deviennent ses ALLIES et
        # doivent sortir de l'ensemble, alors qu'ils sont TOUJOURS sur l'hex en feu. C'est le gate
        # d'equipe eprouve SEUL, sans toucher au feu.
        "cov_owner_team_swapped": _cov(owner_team=next(
            (t for _i, _p, t, _a in cands if t != owner_team), owner_team)),
        "cov_team_unknown": _cov(owner_team=None),          # cle absente -> degradation RESTRICTIVE
        "cov_all_dead": _cov(tgt_alive=False),              # onlyAlive = 1
        "fire_positions": sorted(str(k) for k, v in tfx.items() if "Fire" in set(v or ())),
    }


def offline_active_view(cap, board, carrier_id):
    """E5 -- DISCRIMINANCE du predicat porte. Trois lectures sur la MEME capture :
      * `nominal`   : `is_active` du port avec le porteur tel qu'il est ;
      * `hp_zero`   : le meme apres avoir mis `hp = 0` -- la seule branche ou `IsAlive(Owner)`
                      est FAUX ;
      * `base_default` : ce que rendrait `BaseEffect.is_active` (le defaut qu'on aurait SANS le
                      port) dans ce meme regime -- il rend True, d'ou la discriminance.
    Et `flag_after_refresh` : `refresh_stat_modifier_effects` doit ECRIRE le flag, puisque la
    condition est PORTEE (`_active_condition_is_ported`)."""
    from engine.entities.effects.base import BaseEffect
    from engine.runner.components import HealthComponent, unit_state_for_effects
    from engine.runner.operations.refresh_effects import (_active_condition_is_ported,
                                                          refresh_stat_modifier_effects)
    out = {}
    for tag, kill in (("nominal", False), ("hp_zero", True)):
        st = _load(cap, board)
        inst = next((e for e in (st.effects.by_unit.get(int(carrier_id)) or [])
                     if e.effect_type == EFFECT_VISUAL), None)
        if inst is None:
            out[tag] = None
            continue
        ent = st.get_entity(int(carrier_id))
        hc = ent.get_component(HealthComponent) if ent is not None else None
        if kill and hc is not None:
            hc.hp = 0
        us = unit_state_for_effects(st, int(carrier_id))
        out[tag] = {
            "hp": (hc.hp if hc is not None else None),
            "is_active": bool(inst.is_active(us)),
            "base_default": bool(BaseEffect.is_active(inst, us)),
            "condition_ported": bool(_active_condition_is_ported(inst)),
            "flag_before": bool(inst.active),
        }
        refresh_stat_modifier_effects(st, int(carrier_id))
        out[tag]["flag_after_refresh"] = bool(inst.active)
    return out


# --------------------------------------------------------------------------- montage
def run(rpc, seed: str = SEED, board_id: str = BOARD, keep: bool = False,
        kill_carrier: bool = False) -> dict:
    r = {"seed": seed, "board": board_id, "rid": None, "arm": "kill" if kill_carrier else "nominal"}
    try:
        _run(rpc, r, seed, board_id, kill_carrier)
    except Exception as exc:                              # montage KO -> ERREUR, jamais un vert
        r["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if not keep and r.get("rid") is not None:
            try:
                rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
            except Exception:
                pass
    return r


def _run(rpc, r: dict, seed: str, board_id: str, kill_carrier: bool) -> None:
    import hexgeo
    from engine.entities.pathfinding.board import Board

    hp_player = HP_PLAYER_FRAGILE if kill_carrier else HP_PLAYER
    rid = _build_subprocess(seed, board_id, r["arm"], hp_player)
    r["rid"] = rid
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    dv0i = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": True}, 150)
    car, ally, foe = _by_vis(dv0, CARRIER), _by_vis(dv0, ALLY), _by_vis(dv0, FOE)
    if car is None or ally is None or foe is None:
        raise RuntimeError("deploiement incomplet")
    r["carrier_id"], r["ally_id"], r["foe_id"] = car["id"], ally["id"], foe["id"]

    # -- E1 : POSE + FLAG (la VALEUR DE RETOUR materialisee de `CreateActiveCondition`) ---------
    r["e1_effects_on_carrier"] = [(e.get("effectType"), e.get("name"), e.get("active"))
                                  for e in ((_unit(dv0i, car["id"]) or {}).get("effects") or [])]
    ev = _eff(_unit(dv0i, car["id"]), EFFECT_VISUAL)
    r["e1_visual_present"] = ev is not None
    r["e1_visual_active"] = (ev or {}).get("active")
    r["e1_visual_name"] = (ev or {}).get("name")
    r["e1_visual_default_channel"] = _eff(_unit(dv0, car["id"]), EFFECT_VISUAL) is not None

    if kill_carrier:
        _run_kill_arm(rpc, r, rid, board, car, foe)
        r["ok"] = True
        return

    # -- E2/E3 : le feu est pose par le NATIF, puis on mesure ------------------------------------
    # ⚠ ORDRE CRITIQUE. Le `Fire` pose par `PsychicStalk_ApplyFireTile` a une DUREE : si on place
    # l'allie APRES le tir d'Ahriman, les fins de tour consommees par le deplacement l'ETEIGNENT
    # (mesure du 1er run : `fire_tiles = []`, cible a (6,8)). On place donc les DEUX unites
    # D'ABORD, puis, dans UN SEUL tour joueur : Ahriman tire (pose le feu sous la position
    # COURANTE de la cible) -> capture -> l'allie frappe.
    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du joueur non atteint")
    # Le tir d'Ahriman SPLASHE le feu (`TargetTiles@0x78` = plusieurs tuiles -- mesure : (6,7) ET
    # (6,8)). On ECARTE donc le second ennemi, sinon il se retrouve lui aussi sur le feu et
    # l'EXCLUSION du selecteur n'est plus ancree live. On DEPLACE la configuration voulue.
    _place_at_distance(rpc, rid, FOE2, FOE, 4)
    if _place_at_distance(rpc, rid, ALLY, FOE, 2) != 2:
        raise RuntimeError("allie non place a d=2")
    if _place_at_distance(rpc, rid, CARRIER, FOE, 2) != 2:
        raise RuntimeError("Ahriman non place a d=2 pour poser le feu")
    if _ensure_turn(rpc, rid, car["owner"]) is None:
        raise RuntimeError("tour du joueur non retabli")
    dv1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    car1, foe1 = _unit(dv1, car["id"]), _unit(dv1, foe["id"])
    if car1 is None or foe1 is None:
        raise RuntimeError("porteur ou cible absent avant la pose du feu")
    r["pose_dist"] = hexgeo.distance((car1["pos"]["col"], car1["pos"]["row"]),
                                     (foe1["pos"]["col"], foe1["pos"]["row"]))
    if r["pose_dist"] < 2:
        raise RuntimeError("Ahriman a d=%s : le tir serait MELEE, or `PsychicStalk_ApplyFireTile` "
                           "exige `IsRangedAttack`" % (r["pose_dist"],))
    _attack(rpc, rid, car1, foe1)                       # -> PsychicStalk_ApplyFireTile
    r["fire_after_carrier_shot"] = fire_tiles(rpc("tileMeta", {"runnerId": rid}, 90))

    cap = _capture(rpc, rid)
    attU, foeU = _unit(cap["dv"], ally["id"]), _unit(cap["dv"], foe["id"])
    if attU is None or foeU is None:
        raise RuntimeError("attaquant ou cible absent de la capture")
    fpos = (foeU["pos"]["col"], foeU["pos"]["row"])
    r["fire_tiles"] = fire_tiles(cap["tm"])
    r["target_on_fire"] = fpos in r["fire_tiles"]
    if not r["target_on_fire"]:
        raise RuntimeError("la cible n'est PAS sur un hex en feu (feu=%s cible=%s)"
                           % (r["fire_tiles"], fpos))
    dist = hexgeo.distance((attU["pos"]["col"], attU["pos"]["row"]), fpos)
    profile = weapon_profile(ALLY, ranged=(dist > 1))
    r["dist"], r["profile"] = dist, profile

    # E2 -- le selecteur, contre un ORACLE independant (tileMeta + decisionView)
    sel = offline_selector_view(cap, board, car["id"])
    r["e2_selector"] = sel
    enemies = [u for u in (cap["dv"].get("units") or [])
               if u.get("alive") and u.get("owner") != car.get("owner")]
    oracle = sorted(u["id"] for u in enemies
                    if (u["pos"]["col"], u["pos"]["row"]) in r["fire_tiles"])
    off = sorted(u["id"] for u in enemies
                 if (u["pos"]["col"], u["pos"]["row"]) not in r["fire_tiles"])
    r["e2_oracle_enemies_on_fire"] = oracle
    r["e2_enemies_off_fire"] = off
    r["e2_match"] = (sel.get("covered") == oracle)
    # GARDE DE MONTAGE : sans un ennemi HORS feu, l'ensemble « ennemis » et l'ensemble « ennemis sur
    # le feu » coincident -> un port qui aurait OUBLIE le gate `Fire` passerait quand meme. Un
    # montage non discriminant doit ECHOUER, pas rendre un vert.
    if not off:
        raise RuntimeError("montage NON DISCRIMINANT : tous les ennemis vivants sont sur le feu "
                           "(feu=%s) -- le gate Fire ne serait pas eprouve" % (r["fire_tiles"],))
    if not oracle:
        raise RuntimeError("montage NON DISCRIMINANT : aucun ennemi sur le feu")

    # E3 -- contribution au degat, MESUREE a zero (les gates du kit sont OUVERTS ici)
    res = _attack(rpc, rid, attU, foeU)
    hits, dirty, other = live_amounts(res, foe["id"])
    if not hits:
        raise RuntimeError("coup joue mais aucun degat attribue a la cible")
    r["e3_live_hits"], r["e3_dirty"], r["e3_live_other"] = hits, dirty, other
    r["e3_port_hits"] = offline_hits(cap, board, ally["id"], foe["id"])
    r["e3_port_hits_without_visual"] = offline_hits(cap, board, ally["id"], foe["id"],
                                                    strip_effect_on=car["id"],
                                                    strip_etype=EFFECT_VISUAL)
    # TEMOIN de SENSIBILITE : retirer `1215` (qui, LUI, a un canal) DOIT changer le degat -- sinon
    # l'egalite ci-dessus ne dirait rien (un montage aveugle rend tout egal).
    r["e3_port_hits_without_extra"] = offline_hits(cap, board, ally["id"], foe["id"],
                                                   strip_effect_on=car["id"],
                                                   strip_etype=EFFECT_EXTRA)
    r["e3_stage_with"] = offline_stages(cap, board, foe["id"], ally["id"], profile)
    r["e3_stage_without_visual"] = offline_stages(cap, board, foe["id"], ally["id"], profile,
                                                  strip_effect_on=car["id"],
                                                  strip_etype=EFFECT_VISUAL)

    # E5 -- discriminance offline du predicat porte
    r["e5_active_view"] = offline_active_view(cap, board, car["id"])
    r["ok"] = True


def _run_kill_arm(rpc, r, rid, board, car, foe) -> None:
    """E4 -- LA BRANCHE FAUSSE : le foe tue Ahriman, on relit le flag `active` de `1216`."""
    import hexgeo
    for _ in range(14):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        c, f = _unit(dv, car["id"]), _unit(dv, foe["id"])
        if c is None or f is None:
            break
        if not c.get("alive"):
            break
        if dv.get("currentPlayer") != foe.get("owner"):
            _endturn(rpc, rid)
            continue
        d = hexgeo.distance((c["pos"]["col"], c["pos"]["row"]), (f["pos"]["col"], f["pos"]["row"]))
        if d > 1:
            if _place_at_distance(rpc, rid, FOE, CARRIER, 1) != 1:
                _endturn(rpc, rid)
                continue
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            c, f = _unit(dv, car["id"]), _unit(dv, foe["id"])
            if c is None or f is None or dv.get("currentPlayer") != foe.get("owner"):
                continue
        try:
            _attack(rpc, rid, f, c)
        except RuntimeError:
            _endturn(rpc, rid)

    cap = _capture(rpc, rid)
    ob = cap["ob"]
    # `observeBattle` indexe par `squadId` (PAS `id`) -- cf. probe_17/probe_112 ; `isDead` y est LA
    # verite live de la mort (`project_decisionview_keeps_dead` : decisionView garde les cadavres).
    obu = next((u for u in (ob.get("units") or []) if u.get("squadId") == car["id"]), {})
    r["e4_carrier_isdead_observe"] = obu.get("isDead")
    r["e4_carrier_hp"] = obu.get("hp")
    cu = _unit(cap["dv_inactive"], car["id"])
    r["e4_carrier_alive_dv"] = (cu or {}).get("alive")
    r["e4_effects_on_carrier"] = [(e.get("effectType"), e.get("name"), e.get("active"))
                                  for e in ((cu or {}).get("effects") or [])]
    ev = _eff(cu, EFFECT_VISUAL)
    r["e4_visual_present"] = ev is not None
    r["e4_visual_active_live"] = (ev or {}).get("active")
    # ce que le PORT rend sur EXACTEMENT cette capture
    r["e4_port_active_view"] = offline_active_view(cap, board, car["id"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--kill-carrier", action="store_true",
                    help="E4 -- le foe tue Ahriman : seule branche ou IsAlive(Owner) est FAUX")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    def rpc(method, body=None, timeout=120):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, seed=a.seed, board_id=a.board, keep=a.keep, kill_carrier=a.kill_carrier)
    print(json.dumps(r, indent=1, default=str))
    if r.get("error"):
        return 1
    print("")
    print("[366-r1/1216] runner=%s board=%s seed=%s bras=%s"
          % (r["rid"], a.board, a.seed, r["arm"]))
    print("  E1 pose    : present=%s active=%s name=%s (canal defaut: %s)"
          % (r.get("e1_visual_present"), r.get("e1_visual_active"), r.get("e1_visual_name"),
             r.get("e1_visual_default_channel")))
    if r["arm"] == "kill":
        print("  E4 mort    : isDead=%s hp=%s | 1216 present=%s active_live=%s"
              % (r.get("e4_carrier_isdead_observe"), r.get("e4_carrier_hp"),
                 r.get("e4_visual_present"), r.get("e4_visual_active_live")))
        print("     port     : %s" % (json.dumps(r.get("e4_port_active_view"), default=str),))
        return 0
    print("  E2 selecteur: port=%s oracle=%s match=%s"
          % ((r.get("e2_selector") or {}).get("covered"), r.get("e2_oracle_enemies_on_fire"),
             r.get("e2_match")))
    print("  E3 degat   : live=%s port=%s | sans 1216=%s | sans 1215=%s"
          % (r.get("e3_live_hits"), r.get("e3_port_hits"),
             r.get("e3_port_hits_without_visual"), r.get("e3_port_hits_without_extra")))
    print("  E5 predicat: %s" % (json.dumps(r.get("e5_active_view"), default=str),))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
