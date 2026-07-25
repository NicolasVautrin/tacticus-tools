"""Tache #95 -- CONTRIBUTIONS des buffs Waaagh : 1100 (+extraDmg) et 1101 (+extraHit).

Canaux natifs portes (mirror 1:1) :
  `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`
      = ForAddition(IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster,
                    ConfigVar(8=extraDmg, GetAbilityState(effet)))
  `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`
      = ForAddition(MEME condition, ConfigConst(0x2b=extraHit))
Resolution de la magnitude : `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` ->
  `IdunBattle.Entities.Formulas.ConfigAmount$$GetAbilityState` (selecteur AbilityStateFromEffect) ->
  `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` /
  `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`
  (ce dernier applique `Round(v x AbilityState.VariableMultiplierPercentage/100)` pour les cles de
   `variablesAffectedByRarityBonus`).

SCENARIO -- DEUX THEATRES SEPARES (voir `probe_95_waaagh_contrib.py` pour le detail des pieges) :
  * theatre B : la cible du Waaagh est AMENEE sur le Warboss (qui caste depuis son spawn).
  * theatre A, LOIN : `orksNob` au contact d'un ennemi SANS `Overwatch` (sinon il meurt a l'approche
    -- `decisionView` GARDE les cadavres) et SANS effet de reduction de degat (qui polluerait le
    delta par-coup). C'est l'unite de MESURE : preview NATIVE (`aiPredict` -> `GetAllPredictions`)
    avant / apres le cast, a position ET cible INCHANGEES.
  * une 4e unite de mon camp n'est JAMAIS activee : elle garde le tour OUVERT apres le cast, sinon
    le tour bascule, le TICK de fin de tour passe et les 3 buffs (`Direct(1)` = 1 TOUR) ont deja
    expire quand on les lit.

ASCII only. Skip propre si pas de session / geometrie non cooperative.
"""
from __future__ import annotations

import os

import pytest

import hexgeo

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.effects.magnitude import ability_var

CASTER = "orksWarboss"
ALLY = "orksNob"                  # ORK de mesure (melee), buffe par UnitsFromFaction(Orks) board-wide
MID = "orksRuntherd"              # ORK a distance intermediaire : discriminant du selecteur
SPARE = "spaceHound"              # non-Ork jamais activee : garde le tour ouvert
FOE_ALLY = "necroWarden"          # cible du Nob : ni Overwatch ni effet de reduction de degat
FOE_CASTER = "tyranTyrantGuard"   # cible du Waaagh, ramenee sur le Warboss
# Board/seed OVERRIDABLES : le critere pass/fail ne depend ni de l'un ni de l'autre (on confronte des
# DELTAS avant/apres a geometrie figee) -> `WAAAGH95_BOARD` / `WAAAGH95_SEED` rejouent le meme scenario
# ailleurs pour chasser le sur-ajustement.
BOARD = os.environ.get("WAAAGH95_BOARD", "MC1_67")
SEED = os.environ.get("WAAAGH95_SEED", "31337")


def _upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


@pytest.fixture(scope="session")
def waaagh_buff(rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.orks import WaaaghAbility

    rid = build_runner(SEED, extra=["--p-units", f"{CASTER},{ALLY},{MID},{SPARE}",
                                    "--a-units", f"{FOE_CASTER},{FOE_ALLY}",
                                    "--board", BOARD])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    def dv():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    def find(d, vis):
        return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)

    def endturn():
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    def movable(uid):
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == uid), None)
        return [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or []
                if t.get("col") is not None]

    def drive(vis, goal_fn, want_dist, stop_fn=None, iters=14):
        for _ in range(iters):
            d = dv()
            u = find(d, vis)
            if u is None:
                pytest.skip(f"{vis} absent")
            if stop_fn is not None and stop_fn(d):
                return
            goal = goal_fn(d)
            dist = hexgeo.distance(_upos(u), goal)
            if dist <= want_dist:
                return
            tiles = [t for t in movable(u["id"]) if hexgeo.distance(t, goal) >= want_dist]
            best = min(tiles, key=lambda t: (hexgeo.distance(t, goal), t)) if tiles else None
            if best is None or hexgeo.distance(best, goal) >= dist:
                endturn()
                continue
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": u["id"], "to": {"col": best[0], "row": best[1]}}}, 60)

    d = dv()
    wb_spawn = _upos(find(d, CASTER))
    drive(FOE_CASTER, lambda _d: wb_spawn, 2)                                   # theatre B
    drive(ALLY, lambda dd: _upos(find(dd, FOE_ALLY)), 1, iters=16)              # theatre A
    drive(MID, lambda dd: _upos(find(dd, FOE_ALLY)), 1, iters=8,
          stop_fn=lambda dd: hexgeo.distance(_upos(find(dd, MID)), wb_spawn) >= 3)

    d = dv()
    ally, foe = find(d, ALLY), find(d, FOE_ALLY)
    if hexgeo.distance(_upos(ally), _upos(foe)) != 1:
        pytest.skip("Nob pas au contact de sa cible -> mesure melee impossible")

    # Cible LEGALE de Waaagh, publiee par le natif (`GetDynamicInvalidTargetReason` =
    # `Count(GetPossibleMovementTiles(target)) > 0`). #111 : on lit `fromHere` -- « legalite EXACTE
    # du cast immediat » -- et NON `targets`, qui est le superset « ce tour, MOVE inclus » : une cible
    # de `targets \ fromHere` n'est castable qu'APRES un deplacement, donc `applyAction` (qui ne bouge
    # pas) y rendrait un NO-OP moteur (`mutated=false`) -> ce fixture skiperait en vert sans avoir
    # rien valide. `targets` reste en repli (fromHere indispo = degradation documentee du RPC).
    wb_target = None
    for _ in range(6):
        d = dv()
        c = find(d, CASTER)
        if d.get("currentPlayer") != c.get("owner"):
            endturn(); continue
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": c["id"], "allAbilities": True}, 90)
        abils = [a for u in (at.get("units") or []) if u.get("unitId") == c["id"]
                 for a in (u.get("abilities") or []) if a.get("abilityId") == 1058]
        tg = [t["targetId"] for a in abils for t in (a.get("fromHere") or [])
              if t.get("targetId") is not None] \
            or [t["targetId"] for a in abils for t in (a.get("targets") or [])
                if t.get("targetId") is not None]
        if tg:
            e = find(d, FOE_CASTER)
            wb_target = e["id"] if (e and e["id"] in tg) else tg[0]
            break
        endturn()
    if wb_target is None:
        pytest.skip("Waaagh jamais castable (geometrie)")

    # --- etat AVANT (pour le replay du port) + mesure NATIVE de reference -----------------------
    dv0 = dv()
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    ally, foe, c = _f(dv0, ALLY), _f(dv0, FOE_ALLY), _f(dv0, CASTER)
    dead0 = {u.get("squadId") for u in (ob0.get("units") or []) if u.get("isDead")}
    if ally["id"] in dead0 or foe["id"] in dead0:
        pytest.skip("Nob ou cible deja mort (decisionView garde les cadavres)")
    pre = rpc("aiPredict", {"runnerId": rid, "unitId": ally["id"], "targetId": foe["id"]}, 90)

    act = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": c["id"], "targetId": wb_target, "abilityType": 1058}}, 150)
    a0 = ((act or {}).get("actions") or [{}])[0]
    if not a0.get("mutated"):
        pytest.skip(f"cast Waaagh non mute : {a0.get('error')}")

    dv1 = dv()
    ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
    ally1 = next((u for u in (dv1.get("units") or []) if u["id"] == ally["id"]), None)
    foe1 = next((u for u in (dv1.get("units") or []) if u["id"] == foe["id"]), None)
    if ally1 is None or foe1 is None:
        pytest.skip("Nob/cible disparus apres le cast")
    post = rpc("aiPredict", {"runnerId": rid, "unitId": ally["id"], "targetId": foe["id"]}, 90)

    def adj(d, tid):
        t = next((u for u in (d.get("units") or []) if u["id"] == tid), None)
        tp = _upos(t)
        return sorted(u["id"] for u in (d.get("units") or [])
                      if u["id"] != tid and _upos(u)[0] is not None
                      and hexgeo.distance(_upos(u), tp) == 1)

    invariants = {
        "ally_pos": (_upos(ally), _upos(ally1)),
        "foe_pos": (_upos(foe), _upos(foe1)),
        "foe_hp": (foe.get("hp"), foe1.get("hp")),
        "foe_adj": (adj(dv0, foe["id"]), adj(dv1, foe["id"])),
        "pred_tile": (pre.get("tile"), post.get("tile")),
        "ally_dead": (ally["id"] in dead0,
                      ally["id"] in {u.get("squadId") for u in (ob1.get("units") or [])
                                     if u.get("isDead")}),
    }

    # --- REPLAY du PORT sur le MEME etat-avant (rng cale) ---------------------------------------
    def replay(with_buff: bool = True):
        """Etat-avant FRAIS (rng cale) + rejeu du MEME cast Waaagh. `with_buff=False` = contre-cas :
        on CONSOMME les deux effets 1100/1101 juste apres la pose (tout le reste du cast identique)."""
        st = load_state(dv0, ob0, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"])
            rng.mti = s0["mti"]
            st.rng = rng
        r = WaaaghAbility().execute_behaviour(st, c["id"], wb_target)
        if not with_buff and st.effects is not None:
            for lst in st.effects.by_unit.values():
                for e in lst:
                    if (getattr(e, "name", "") or "") in ("Waaagh_ExtraDamage", "Waaagh_ExtraHits"):
                        e.consumed = True
        return st, r

    state, res = replay()

    # niveau d'ability ACTIVE du POSEUR (ce que `GetAbilityState(effet)` resout)
    caster_cfg = next((u.get("unitConfig") or {} for u in (snap.get("units") or [])
                       if u.get("entityId") == c["id"]), {})
    return {"rid": rid, "pre": pre.get("pred") or {}, "post": post.get("pred") or {},
            "invariants": invariants, "state": state, "res": res, "replay": replay,
            "ally_id": ally["id"], "caster_id": c["id"], "mid_id": _f(dv1, MID)["id"],
            "spare_id": _f(dv1, SPARE)["id"], "caster_cfg": caster_cfg, "foe_id": foe["id"],
            "ally_effects_live": {e.get("name") for e in (ally1.get("effects") or [])},
            "dv1": dv1}


def _f(d, vis):
    return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)


def _require_clean(d):
    """La mesure n'a de sens que si RIEN d'autre n'a bouge entre les deux previews."""
    for k, (x, y) in d["invariants"].items():
        if x != y:
            pytest.skip(f"invariant {k} rompu ({x} -> {y}) : mesure non exploitable")
    if not d["pre"] or not d["post"]:
        pytest.skip("preview native indisponible")
    # La preview ECRETE `healthDmg*` aux PV de la cible : si meme la borne BASSE tue, `appliedHits`
    # est tronque et les deux axes deviennent inexploitables (mesure C3_01/777 : la borne HAUTE
    # post-buff tombait pile sur hpBefore = 8536).
    for lbl in ("pre", "post"):
        if d[lbl]["healthDmgMin"] >= d[lbl]["hpBefore"]:
            pytest.skip(f"{lbl} : kill garanti -> appliedHits tronque, mesure non exploitable")


def _unclamped(d, key):
    """La borne `key` est-elle exploitable dans les DEUX previews (non ecretee par les PV cible) ?"""
    return all(d[lbl][key] < d[lbl]["hpBefore"] for lbl in ("pre", "post"))


def _expected_extra_dmg(d):
    """`ConfigVar(8=extraDmg, GetAbilityState(effet))` = extraDmg[niveau ACTIF du POSEUR], multiplier
    RESOLU = 100 (cf. `WaaaghExtraDamageEffect`, mesure live)."""
    return int(ability_var("Waaagh", "extraDmg", d["caster_cfg"].get("activeAbilityLevel")) or 0)


# ================================================================================================ #
# FACE NATIVE (ground truth) -- ce que la preview du jeu fait vraiment
# ================================================================================================ #

def test_live_extra_hit_adds_exactly_extra_hit(waaagh_buff):
    """`Waaagh_ExtraHitsEffect.CreateEffectHitsBonusForAttack` = `ForAddition(..., ConfigConst(0x2b))` :
    l'allie ORK buffe marque **+extraHit** coup avec son attaque normale MELEE (preview NATIVE)."""
    d = waaagh_buff
    _require_clean(d)
    n = int(ability_var("Waaagh", "extraHit", is_constant=True) or 0)
    assert n > 0, "config Waaagh sans extraHit"
    assert d["post"]["appliedHits"] - d["pre"]["appliedHits"] == n, (
        f"coups live {d['pre']['appliedHits']} -> {d['post']['appliedHits']} "
        f"(attendu +{n} = extraHit)")


def test_live_extra_damage_adds_extra_dmg_per_hit_unscaled(waaagh_buff):
    """`Waaagh_ExtraDamageEffect.CreateEffectDamageBonusForAttack` = `ForAddition(..., ConfigVar(8))` :
    le degat PAR COUP monte de `extraDmg[niveau du POSEUR]` **BRUT** (multiplier resolu = 100 -- ni le
    200 % du Warboss ni le 180 % du porteur). Confronte les bornes NON ECRETEES par les PV cible."""
    d = waaagh_buff
    _require_clean(d)
    want = _expected_extra_dmg(d)
    assert want > 0, "config Waaagh sans extraDmg au niveau du poseur"
    h0, h1 = d["pre"]["appliedHits"], d["post"]["appliedHits"]
    assert h0 and h1
    checked = 0
    for k in ("healthDmgMin", "healthDmgMax"):
        if not _unclamped(d, k):
            continue                     # borne ecretee aux PV de la cible -> non exploitable
        per0, per1 = d["pre"][k] / h0, d["post"][k] / h1
        assert round(per1 - per0) == want, (
            f"{k} par coup {per0:.1f} -> {per1:.1f} (delta {per1 - per0:.1f}) != extraDmg {want}")
        checked += 1
    assert checked, "les deux bornes sont ecretees par les PV cible -> aucune mesure de degat"


# ================================================================================================ #
# FACE PORT -- le replay offline du MEME cast doit produire les MEMES contributions
# ================================================================================================ #

def test_port_posts_both_buffs_on_the_far_ork_ally(waaagh_buff):
    """Le selecteur `UnitsFromFaction(Friends(caster, allUnits@0x80), 5=Orks)` est BOARD-WIDE : l'allie
    ORK est buffe MEME a 9 hex du Warboss (confirme LIVE) -- et le port fait pareil."""
    d = waaagh_buff
    want = {"Waaagh_ExtraDamage", "Waaagh_ExtraHits"}
    st = d["state"]
    port = {getattr(e, "name", None) or "" for e in (st.effects.by_unit.get(d["ally_id"]) or [])}
    assert want <= port, f"port : l'allie Ork loin n'a pas {sorted(want)} (a : {sorted(port)})"
    assert want <= d["ally_effects_live"], (
        f"live : l'allie Ork loin n'a pas {sorted(want)} (a : {sorted(d['ally_effects_live'])})")


def test_port_hits_and_damage_contributions_match_live(waaagh_buff):
    """Les DEUX canaux portes rendent EXACTEMENT le delta mesure live : +extraHit coup et +extraDmg
    par coup. Mesure en **A/B** (etat rejoue AVEC vs SANS les effets 1100/1101) et non en absolu :
    le porteur peut avoir d'AUTRES contributions au meme canal (mesure C3_01/777 : SmashaEad +599 sur
    le meme additif) -- comparer l'additif TOTAL au delta live serait un faux echec."""
    from engine.entities.effects import hits_bonus_from_effects
    from engine.entities.effects import build_attacker_modifiers_from_effects
    d = waaagh_buff
    _require_clean(d)

    def channels(st):
        effs = [e for e in (st.effects.by_unit.get(d["ally_id"]) or []) if not e.consumed]
        return (hits_bonus_from_effects(effs, att_ctx={"is_melee": True}),
                build_attacker_modifiers_from_effects(effs, is_ranged=False,
                                                      is_normal_attack=True).additive)

    on_hits, on_add = channels(d["state"])
    off_hits, off_add = channels(d["replay"](with_buff=False)[0])
    live_hits = d["post"]["appliedHits"] - d["pre"]["appliedHits"]
    assert on_hits - off_hits == live_hits, (
        f"port +{on_hits - off_hits} coups != live +{live_hits}")
    h0, h1 = d["pre"]["appliedHits"], d["post"]["appliedHits"]
    live_dmg = round(d["post"]["healthDmgMin"] / h1 - d["pre"]["healthDmgMin"] / h0)
    assert round(on_add - off_add) == live_dmg, (
        f"port additif Waaagh {on_add - off_add} != live +{live_dmg} par coup")


def test_port_gates_ranged_and_ability_attacks(waaagh_buff):
    """GATES `IsMeleeAttack` & `IsNormalAttack` (les DEUX canaux) : aucune contribution sur une attaque
    RANGED ni sur une attaque d'ABILITY. Contre-cas indispensable : sans lui, « +1 coup » ne prouve pas
    que la condition native est portee."""
    from engine.entities.effects import hits_bonus_from_effects
    from engine.entities.effects import build_attacker_modifiers_from_effects
    d = waaagh_buff
    effs = [e for e in (d["state"].effects.by_unit.get(d["ally_id"]) or []) if not e.consumed]
    waaagh = [e for e in effs if (getattr(e, "name", "") or "").startswith("Waaagh_Extra")]
    assert waaagh, "aucun effet Waaagh sur l'allie -> contre-cas vide"
    assert hits_bonus_from_effects(waaagh, att_ctx={"is_melee": False}) == 0, "coups: RANGED non gate"
    assert hits_bonus_from_effects(waaagh, is_normal_attack=False,
                                   att_ctx={"is_melee": True}) == 0, "coups: ABILITY non gatee"
    assert build_attacker_modifiers_from_effects(waaagh, is_ranged=True).additive == 0, \
        "degat: RANGED non gate"
    assert build_attacker_modifiers_from_effects(waaagh, is_ranged=False,
                                                 is_normal_attack=False).additive == 0, \
        "degat: ABILITY non gatee"


def test_port_combat_face_consumes_both_channels(waaagh_buff):
    """FACE COMBAT (`IdunBattle.Operations.AttackDamageOperation$$Execute` -> facade `GetAttackHits` +
    `attacker_modifiers`) : l'attaque NORMALE MELEE de l'allie buffe, rejouee OFFLINE, porte bien les
    deux contributions. A/B sur DEUX etats issus du MEME etat-avant, seuls les effets 1100/1101 varient.
    - coups : delta EXACT == extraHit (l'axe coups n'est pas scale par l'armure) ;
    - degat : borne non-crit par coup STRICTEMENT superieure (l'additif entre PRE-percage en combat,
      donc le delta y est reduit par armure/percage -- on assert la MONOTONIE, pas extraDmg brut :
      ce serait fitter un scalaire a travers un etage qu'on ne mesure pas ici)."""
    from engine.runner.operations.damage import AttackDamageOperation
    d = waaagh_buff
    n = int(ability_var("Waaagh", "extraHit", is_constant=True) or 0)
    st_on, _ = d["replay"](with_buff=True)
    st_off, _ = d["replay"](with_buff=False)
    on = AttackDamageOperation.execute(st_on, d["ally_id"], d["foe_id"])
    off = AttackDamageOperation.execute(st_off, d["ally_id"], d["foe_id"])
    if not on or not off:
        pytest.skip("attaque offline non resolue (positions/armes)")
    assert on["hits"] - off["hits"] == n, (
        f"combat : coups {off['hits']} -> {on['hits']} (attendu +{n} = extraHit)")
    per_on = on["clean_min"] / on["hits"]
    per_off = off["clean_min"] / off["hits"]
    assert per_on > per_off, (
        f"combat : borne non-crit par coup {per_off:.1f} -> {per_on:.1f} (l'additif extraDmg "
        f"n'atteint pas le chemin COMBAT)")


def test_port_counter_case_unbuffed_unit_gets_nothing(waaagh_buff):
    """CONTRE-CAS : l'unite NON-Ork jamais activee (hors `UnitsFromFaction(Orks)` ET hors ring-1 du
    Warboss) ne recoit AUCUNE contribution -- live ET port. Sans ce contraste, le +1/+extraDmg pourrait
    venir de n'importe quel effet present."""
    from engine.entities.effects import hits_bonus_from_effects
    from engine.entities.effects import build_attacker_modifiers_from_effects
    d = waaagh_buff
    spare = next((u for u in (d["dv1"].get("units") or []) if u["id"] == d["spare_id"]), None)
    live_names = {e.get("name") for e in (spare or {}).get("effects") or []}
    if any(n and n.startswith("Waaagh_") for n in live_names):
        pytest.skip("la 4e unite s'est retrouvee dans l'anneau du Warboss -> pas un contre-cas")
    effs = [e for e in (d["state"].effects.by_unit.get(d["spare_id"]) or []) if not e.consumed]
    port_names = {getattr(e, "name", None) or "" for e in effs}
    assert not any(n.startswith("Waaagh_") for n in port_names), (
        f"port : la 4e unite (non-Ork, hors ring-1) est buffee : {sorted(port_names)}")
    assert hits_bonus_from_effects(effs, att_ctx={"is_melee": True}) == 0
    assert build_attacker_modifiers_from_effects(effs, is_ranged=False).additive == 0
