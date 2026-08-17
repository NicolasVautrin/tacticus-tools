"""DEATH-NOVA (traits `Explodes` 1008 -> triggered 1021, `PutridExplosion` 2028 -> 1074) —
CONFRONT LIVE du vecteur `On(PreUnitDeath_2 = 2)` et des deux arbres DSL de nova.

Ce que le test confronte au LIVE (aucune fixture gelee, aucun scalaire fitte) :
  A. `test_explodes_nova_live` — porteur `necroSpyder` au centre, un ALLIE et un ENNEMI adjacents,
     un ennemi CONTROLE hors du ring. Le porteur est tue par une attaque normale ennemie ; on
     compare, PAR CIBLE, le delta de PV LIVE au delta produit OFFLINE par `pre_unit_death_2_triggers`
     rejoue depuis la MEME capture d'etat. Verifie du meme coup :
       * FRIENDLY-FIRE : l'allie (meme equipe que le porteur) encaisse -- le selecteur natif
         `Units(AdjacentTiles(Self),0,3)` n'a AUCUN filtre d'equipe ;
       * GATE DE ZONE : l'unite hors ring 1 encaisse 0 ;
       * MAGNITUDE : `explodesDmg`% du **maxPV** (pas des PV courants), profil `DirectDamage`
         (PiercingRatio 100 -> l'armure de la cible est integralement percee).
  B. `test_putrid_explosion_faction_exclusion_live` — porteur `deathPutrifier`, avec un ennemi
     **DeathGuard** ET un allie **non-DeathGuard** adjacents : l'exclusion `UnitsFromFaction` est
     par **FACTION**, pas par equipe -> l'ENNEMI DeathGuard est EPARGNE, l'ALLIE Aeldari encaisse.
     Profil `Toxic` (PiercingRatio 70) -> le net n'est PAS 25% du maxPV : decomposition d'etage
     verifiee (base -> percage -> armure).
  C. `test_explodes_fires_on_overkill_live` — LE PIEGE. Les deux `CreateTrigger` passent `a=1` a
     `OnPreDeath2` => `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent` n'ajoute PAS le `NOT HasFlag(dying, Overkilled=8)`.
     Un port copie sur `FinalJustice` (dont le gate overkill vit dans son BEHAVIOUR) serait FAUX.
     On monte une mort **OVERKILL CERTAINE** (degat BRUT de la prediction >= 2 x PV) et on exige que
     la nova parte quand meme.
  D. `test_putrid_steppable_gate_offline` / `test_no_overkill_gate_offline` — les deux gates du
     `OnDeathEvent(2, a, b)` mirrores, verifies OFFLINE (aucun porteur `Steppable` de `PutridExplosion`
     n'existe en gameconfig -> gate non confrontable live : mirror + toggle offline).

Artefacts natifs (build gqfc5mff6c) : `ExplodesAbility` IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$CreateBehaviour ; `PutridExplosion_Ability` IdunBattleLogic.Entities.Abilities.Active.Loki.PutridExplosion_Ability$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Active.Loki.PutridExplosion_Ability$$CreateBehaviour ; `IdunBattleLogic.Entities.DSLTriggers$$OnPreDeath2`
-> `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent` ; emetteur de la sequence de mort `KillUnitOperation$$IdunBattle.Operations.KillUnitOperation$$Execute`
(ordre d'instruction LU : On(1) -> On(2) -> On(0) -> On(54 = UnitDefeated) -> On(53 = PostUnitKill)).

⚠ `--block-target 0,0` : le block EST tire dans la famille ABILITY (prouve live), mais le rejeu
offline part d'un RNG cale AVANT le coup letal alors que le natif a deja consomme des tirages ->
l'issue du tirage de block n'est pas comparable dans ce protocole. On NEUTRALISE le block pour
mesurer l'etage DEGAT (le modele de block reste couvert par les tests block dedies).

ASCII only (cp1252) ; adjacence evenq.
"""
from __future__ import annotations

import pytest

from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import UnitComponent, HealthComponent, StatsComponent
from engine.runner.operations.triggers.dispatch.move_death import pre_unit_death_2_triggers
from engine.runner.operations.triggers.loki.death_nova import (
    ExplodesAbility, PutridExplosionAbility, EXPLODES_PROFILE)
from engine.runner.operations.triggers.base import TriggerEvent
from engine.dsl.event_trigger_type import EventTriggerType

CENTER = (3, 4)

# Rosters CHOISIS (jamais subis) :
#  * allie et controle-eloigne SANS `Overwatch` (un tir gratuit pendant le placement entamerait les
#    PV et fausserait la mesure -- vecu) ; `eldarAutarch` = allie Aeldari, donc non-DeathGuard ;
#  * tueur = `ultraInceptorSgt` et NON `ultraTitus` : Titus porte le trait `BeastSlayer` qui pose
#    l'effet `BeastSlayer_ExtraBlock` -> une SOURCE DE BLOCK que `--block-target 0,0` (stat de base)
#    ne neutralise pas. Le block est un TIRAGE : le rejeu offline part d'un RNG cale AVANT le coup
#    letal alors que le natif a deja consomme des tirages -> issue non comparable. Titus porte AUSSI
#    `FinalJustice` (autre death-trigger) -> double raison de l'ecarter du ring.
EXPLODES_BUILD = ["--p-units", "necroSpyder,eldarAutarch",
                  "--a-units", "ultraInceptorSgt,ultraTitus,astraBullgryn",
                  "--block-target", "0,0"]
PUTRID_BUILD = ["--p-units", "deathPutrifier,eldarAutarch",
                "--a-units", "ultraInceptorSgt,deathBlightbringer,astraBullgryn",
                "--block-target", "0,0"]


def _units(rpc, rid):
    """Indexe `observeBattle` par **squadId** = l'id de `applyAction`, de `decisionView.units[].id`
    et des entites du `State` offline (`entityId` n'est PAS accepte par `applyAction`)."""
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    return {int(u["squadId"]): u for u in (ob.get("units") or [])}


def _hp(rpc, rid):
    return {k: (int(v.get("hp") or 0), int(v.get("hpMax") or 0)) for k, v in _units(rpc, rid).items()}


def _move(rpc, rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _normal_attack_id(dec, uid):
    for u in (dec.get("units") or []):
        if int(u.get("id") or -1) == int(uid):
            for a in (u.get("abilities") or []):
                if a.get("kind") == "normal":
                    return int(a.get("id"))
    return None


def _offline(rpc, rid):
    """Capture S + `State` offline seede sur le MT19937 de combat."""
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 120)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    st = load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="evenq"))
    if isinstance(rng0, dict) and rng0.get("ok"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
    return dec, st


def _setup(rpc, build_runner, seed, build_args, carrier_vis, hp_player, ring_roles=("ally", "killer")):
    """Monte la geometrie : porteur au centre, `ring_roles` sur le ring 1, TOUT LE RESTE hors ring
    (controles du gate de zone). Renvoie (rid, ids, board) ou skip si le placement a entame des PV."""
    rid = build_runner(seed, extra=build_args + ["--hp-player", str(hp_player)])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    ring = [board.coord(t) for t in board.neighbours(board.id_at(*CENTER))]
    if len(ring) < 3:
        pytest.skip("centre trop pauvre en voisins")

    ob = _units(rpc, rid)
    by_vis = {}
    for uid, u in ob.items():
        by_vis.setdefault(u.get("visualId"), []).append(uid)
    need = [carrier_vis, "eldarAutarch", "ultraInceptorSgt", "astraBullgryn"]
    if any(v not in by_vis for v in need):
        pytest.skip("roster incomplet dans l'etat capture")
    ids = {
        "carrier": by_vis[carrier_vis][0],
        "ally": by_vis["eldarAutarch"][0],
        "killer": by_vis["ultraInceptorSgt"][0],
        "far": by_vis["astraBullgryn"][0],
    }
    ids["adj"] = next(uid for uid, u in ob.items()
                      if uid not in ids.values() and u.get("teamId") != ob[ids["carrier"]].get("teamId"))

    off_ring = [(6, 0), (6, 8), (0, 8)]                    # controles du GATE DE ZONE (hors ring 1)
    outside = [ids[r] for r in ("far", "adj", "ally", "killer") if r not in ring_roles]
    for uid, (c, r) in zip(outside, off_ring):
        _move(rpc, rid, uid, c, r)
    _move(rpc, rid, ids["carrier"], *CENTER)
    for role, (c, r) in zip(ring_roles, ring):
        _move(rpc, rid, ids[role], c, r)

    ob = _units(rpc, rid)
    if any(u not in ob for u in ids.values()):
        pytest.skip("etat live incomplet apres placement (RPC partiel)")
    if any(int(ob[u].get("hp") or 0) != int(ob[u].get("hpMax") or 0) for u in ids.values()):
        pytest.skip("placement pollue (PV entames : overwatch/reaction) -> mesure non fiable")
    return rid, ids, board


def _kill_and_compare(rpc, rid, ids, require_overkill=None):
    """Coup letal LIVE puis comparaison PAR CIBLE (live vs port rejoue depuis la capture S).
    Renvoie (live_nova, port_nova, hp_before, raw_dmg, maxhp_carrier)."""
    dec, st = _offline(rpc, rid)
    na = _normal_attack_id(dec, ids["killer"])
    if na is None:
        pytest.skip("id d'attaque normale du tueur introuvable")
    hp_before = _hp(rpc, rid)
    if any(u not in hp_before for u in ids.values()):
        pytest.skip("etat live incomplet (observeBattle partiel) -> mesure non fiable")

    # OVERKILL observable : `healthDmg*` est CAPE a `hpBefore` ; `totalDmg*` est le degat BRUT et
    # EGALE le degat sante brut quand la cible n'a ni armure-pool ni bouclier (`is_overkill
    # IdunBattle.Core.Services.DamagePrediction$$IsOverkill` : overkill ssi dmg >= 2 x PV, `overkillDmgPctOfHealth`=100).
    pred = ((rpc("aiPredict", {"runnerId": rid, "unitId": ids["killer"],
                               "targetId": ids["carrier"], "abilityType": na}, 90) or {})
            .get("pred") or {})
    raw = None
    if int(pred.get("armorBefore") or 0) == 0 and int(pred.get("shieldBefore") or 0) == 0 \
            and pred.get("totalDmgMin") is not None:
        raw = (int(pred["totalDmgMin"]), int(pred["totalDmgMax"]))
    hpc = hp_before[ids["carrier"]][0]
    if require_overkill is True:
        if raw is None or raw[0] < 2 * hpc:
            pytest.skip("coup letal non OVERKILL-certain sur ce build (raw=%s, PV=%d)" % (raw, hpc))
    if require_overkill is False:
        if raw is None or raw[1] >= 2 * hpc or raw[0] < hpc:
            pytest.skip("coup letal non NON-OVERKILL-certain sur ce build (raw=%s, PV=%d)" % (raw, hpc))

    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ids["killer"], "targetId": ids["carrier"],
        "abilityType": na}}, 120)
    hp_after = _hp(rpc, rid)
    if hp_after[ids["carrier"]][0] > 0:
        pytest.skip("le porteur n'est pas mort du coup (degat insuffisant)")
    live = {u: hp_before[u][0] - hp_after[u][0] for u in hp_before if u != ids["carrier"]}

    ce = st.get_entity(ids["carrier"])
    if ce is None:
        pytest.skip("porteur absent de l'etat offline")
    maxhp = int((ce.get_component(HealthComponent)).hp_max or 0)
    ce.get_component(UnitComponent).alive = False           # fire-on-death : owner deja mort
    before = {e: int(x.get_component(HealthComponent).hp or 0) for e, x in st.entities.items()
              if x.get_component(HealthComponent) is not None}
    pre_unit_death_2_triggers(st, ids["carrier"], ids["killer"],
                              overkill=bool(require_overkill))
    after = {e: int(x.get_component(HealthComponent).hp or 0) for e, x in st.entities.items()
             if x.get_component(HealthComponent) is not None}
    port = {e: before[e] - after[e] for e in before if e != ids["carrier"]}
    return live, port, hp_before, raw, maxhp


def _agree(live, port):
    keys = sorted(set(live) | set(port))
    bad = [(k, live.get(k, 0), port.get(k, 0)) for k in keys if live.get(k, 0) != port.get(k, 0)]
    assert not bad, "nova live != port par cible : %s" % bad


def test_explodes_nova_live(live_session, rpc, build_runner):
    """`Explodes` : friendly-fire + gate de zone + magnitude (25% du maxPV, DirectDamage p100)."""
    rid, ids, _ = _setup(rpc, build_runner, "90310", EXPLODES_BUILD, "necroSpyder", 804)
    live, port, hp_before, raw, maxhp = _kill_and_compare(rpc, rid, ids)
    _agree(live, port)
    # FRIENDLY-FIRE : l'allie (MEME equipe que le porteur) encaisse -- pas de wrapper `Enemies`.
    assert live[ids["ally"]] > 0, "friendly-fire absent : l'allie adjacent n'a rien encaisse"
    # GATE DE ZONE : l'unite hors ring 1 est intacte.
    assert live[ids["far"]] == 0, "une unite HORS du ring 1 a encaisse la nova"
    # MAGNITUDE : DirectDamage a PiercingRatio 100 -> l'armure est integralement percee, donc le net
    # sur une cible SANS bouclier == la base = round(explodesDmg% x maxPV).
    import gameconfig as GC
    pct = int((GC.trait("Explodes").get("variables") or {})["explodesDmg"])
    assert live[ids["ally"]] == round(pct * maxhp / 100), \
        "base attendue = %d%% du maxPV(%d) ; observe %d" % (pct, maxhp, live[ids["ally"]])
    assert EXPLODES_PROFILE == "DirectDamage"


def test_explodes_fires_on_overkill_live(live_session, rpc, build_runner):
    """LE PIEGE : `OnPreDeath2(a=1)` => AUCUN gate `NOT HasFlag(Overkilled)`. Mort OVERKILL-certaine
    (degat BRUT >= 2 x PV) -> la nova part QUAND MEME (un port copie sur FinalJustice l'annulerait)."""
    rid, ids, _ = _setup(rpc, build_runner, "90311", EXPLODES_BUILD, "necroSpyder", 300)
    live, port, hp_before, raw, maxhp = _kill_and_compare(rpc, rid, ids, require_overkill=True)
    _agree(live, port)
    assert live[ids["ally"]] > 0 and live[ids["killer"]] > 0, \
        "nova SUPPRIMEE en overkill (raw=%s, PV=%d) : gate parasite" % (raw, hp_before[ids["carrier"]][0])


def test_putrid_explosion_faction_exclusion_live(live_session, rpc, build_runner):
    """`PutridExplosion` : exclusion `UnitsFromFaction(<adjacents>, putridExplosionFactionId)` par
    **FACTION** et non par equipe -> l'ENNEMI DeathGuard est EPARGNE, l'ALLIE Aeldari encaisse.
    Le porteur est `Resilient` : mourir d'UN coup implique structurellement un OVERKILL
    (`IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` : hors overkill le degat est cape a curHP-1)."""
    rid, ids, _ = _setup(rpc, build_runner, "90312", PUTRID_BUILD, "deathPutrifier", 300,
                         ring_roles=("ally", "killer", "adj"))   # `adj` = deathBlightbringer (DeathGuard)
    live, port, hp_before, raw, maxhp = _kill_and_compare(rpc, rid, ids, require_overkill=True)
    _agree(live, port)
    import gameconfig as GC
    v = GC.trait("PutridExplosion").get("variables") or {}
    excluded = v["putridExplosionFactionId"]
    ob = _units(rpc, rid)
    dg = [u for u in live if (GC.unit(ob[u].get("visualId")) or {}).get("FactionId") == excluded]
    assert dg, "aucun adjacent de la faction exclue (%s) : scenario non discriminant" % excluded
    for u in dg:
        assert live[u] == 0, "un adjacent %s (ENNEMI) a encaisse : exclusion faite par EQUIPE ?" % excluded
    assert live[ids["ally"]] > 0, "l'allie non-%s n'a rien encaisse (friendly-fire absent)" % excluded
    # ETAGE : profil Toxic (PiercingRatio 70) -> le net d'une cible ARMOREE n'est PAS la base.
    base = round(int(v["putridExplosionDmgPct"]) * maxhp / 100)
    assert live[ids["ally"]] == base, "allie sans armure : net attendu = base %d, observe %d" % (
        base, live[ids["ally"]])
    armored = [u for u in live if u not in dg and u != ids["ally"] and live[u] > 0]
    for u in armored:
        assert live[u] <= base, "net %d > base %d sur u%d (percage Toxic 70%%)" % (live[u], base, u)


def test_no_overkill_gate_offline():
    """Les DEUX `CreateTrigger` passent `a=1` a `OnPreDeath2` -> `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent` n'ajoute
    PAS `NOT HasFlag(dying, UnitFlag.Overkilled=8)`. Le port ne doit donc lire `ev.overkill` NULLE PART."""
    for cls in (ExplodesAbility, PutridExplosionAbility):
        ab = cls(7)
        assert ab.event_id == EventTriggerType.PreUnitDeath_2, "event != 2 (PreUnitDeath_2)"
        assert ab.fire_on_death is True, "l'owner EST le mourant -> fire_on_death requis"
        ev_ovk = TriggerEvent(EventTriggerType.PreUnitDeath_2, 9, 7, ranged=False, profile=None,
                              killer_id=9, dying_id=7, overkill=True)
        ev_no = TriggerEvent(EventTriggerType.PreUnitDeath_2, 9, 7, ranged=False, profile=None,
                             killer_id=9, dying_id=7, overkill=False)

        class _S:                                   # etat minimal : `matches` d'Explodes ne le lit pas
            def get_entity(self, _):
                return None
        st = _S()
        if cls is ExplodesAbility:                  # b=1 : aucun gate du tout
            assert ab.matches(st, ev_ovk) and ab.matches(st, ev_no), \
                "%s doit matcher AVEC et SANS overkill" % cls.__name__
        # OwnerIsTarget : un autre mourant ne matche pas
        ev_other = TriggerEvent(EventTriggerType.PreUnitDeath_2, 9, 8, ranged=False, profile=None,
                                killer_id=9, dying_id=8, overkill=False)
        assert not ab.matches(st, ev_other), "%s a matche sur la mort d'une AUTRE unite" % cls.__name__


def test_putrid_steppable_gate_offline():
    """`PutridExplosion` passe `b=0` a `OnPreDeath2` -> `OnDeathEvent` ajoute
    `NOT HasTrait(dying, UnitTrait.Steppable=0x1b)` (Explodes passe `b=1` : pas de gate).
    Aucun porteur `Steppable` de PutridExplosion n'existe en gameconfig -> gate NON confrontable
    live : on le verifie par TOGGLE offline du set de traits."""
    from engine.entities.traits.unit_trait import UnitTrait

    class _Ctx:
        def __init__(self, traits):
            self.traits = traits

    class _SC:
        def __init__(self, traits):
            self.ctx = _Ctx(traits)

    class _E:
        def __init__(self, traits):
            self._sc = _SC(traits)

        def get_component(self, cls):
            return self._sc if cls.__name__ == "StatsComponent" else None

    class _S:
        def __init__(self, traits):
            self._e = _E(traits)

        def get_entity(self, _):
            return self._e

    ev = TriggerEvent(EventTriggerType.PreUnitDeath_2, 9, 7, ranged=False, profile=None,
                      killer_id=9, dying_id=7, overkill=False)
    assert PutridExplosionAbility(7).matches(_S(["PutridExplosion"]), ev), \
        "porteur non-Steppable : la nova doit partir"
    assert not PutridExplosionAbility(7).matches(
        _S(["PutridExplosion", UnitTrait.Steppable.name]), ev), \
        "porteur Steppable : `NOT HasTrait(dying, Steppable)` doit SUPPRIMER la nova (b=0)"
    # Explodes (b=1) : AUCUN gate Steppable.
    assert ExplodesAbility(7).matches(_S(["Explodes", UnitTrait.Steppable.name]), ev), \
        "Explodes (b=1) ne doit PAS etre gate par Steppable"
