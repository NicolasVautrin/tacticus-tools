"""GARDE case-cvc — le CYCLE DE VIE du debuff d'armure de l'aura `ContagionsOfNurgle` (1071/1072).

Ce que la garde PROUVE (et pas « le code est atteint ») :

  1. **les DEUX instances coexistent** sur chaque ennemi du porteur, posees par
     `ContagionsOfNurgle_AddEffectInitially_Ability` -- y compris HORS du disque, ou elles sont
     toutes deux `active: false`. C'est la refutation directe du collapse « le port ne pose que
     l'instance active » : le canal `decisionView { includeInactive: true }` les montre, et le port
     les materialise a l'identique.
  2. **l'instance ACTIVE suit la geometrie** : promenee autour des porteurs, la victime voit
     l'ensemble actif LIVE et l'ensemble actif PORT coincider, et `FixedArmor` avec.
  3. **l'aura qui GRANDIT allume l'effet sans que personne ne bouge** : a distance 2 d'un porteur
     isole, `TurnsStarted` 0-2 (rayon 1) -> INERTE ; 3+ (rayon 2) -> ACTIF. Les deux faces derivent
     par LEUR propre vecteur (live `endturn`, port `StartTurnOperation.execute`), sans re-seed.
  4. **sortir de l'aura retire la contribution** : le port joue le pas par son propre
     `MoveUnitOperation` (qui declenche le driver `RefreshEffectsOperation` porte) et rend la MEME
     armure que le natif -- c'est le volet qui distingue « le port LIT juste » de « le port EVOLUE
     juste ».
  5. **les fenetres sont DISJOINTES** (offline) : aucun nombre d'auras n'active 1071 ET 1072, sinon
     -20 % et -40 % se cumuleraient.

Chaines natives portees (symboles) :
  `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CreateActiveCondition`
  `IdunBattle.Entities.Triggers.ContagionsOfNurgleAmountFormula$$Calculate`
  `IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount`
  `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` / `$$ShouldBeActive` /
  `$$ActivateEffect` / `$$DeactivateEffect` / `$$UpdateEffectTargets`
  `IdunBattle.Entities.Components.EffectComponent$$.ctor` (le flag `+0x5c` naît FAUX)
Cf. `docs/rl/case-cvc-contagions-lifecycle.md`.

ASCII-only. Skip si pas de session live.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
import probe_cvc_contagions_lifecycle as P                          # noqa: E402

RED1, RED2 = P.RED1, P.RED2
CARRIERS = "deathTyphus,deathBlightlord,deathPutrifier"
VICTIMS = "ultraTitus,necroWarden,adeptMorvenn"


# --------------------------------------------------------------------------- offline (sans live)

def test_active_condition_windows_are_disjoint_offline():
    """`CreateActiveCondition` = `min <= ContagionsOfNurgleAmount <= max`, avec les fenetres du ctor
    (`EffectsDatabase` b__14_93/94) : `[1,1]` et `[2,+inf[`. DISJOINTES -> jamais -20 % ET -40 %."""
    from engine.entities.effects.loki.status import ContagionsOfNurgleArmorReductionEffect as E
    e1 = E(name="ContagionsOfNurgle_ArmorReduction1", effect_type=RED1, value=-299, source=7)
    e2 = E(name="ContagionsOfNurgle_ArmorReduction2", effect_type=RED2, value=-598, source=7)
    assert e1.aura_amount_window() == (1, 1)
    assert e2.aura_amount_window() == (2, 0x7FFFFFFF)
    for n in range(0, 6):
        us = {"contagions_of_nurgle_amount": (lambda _s, k=n: k)}
        a1, a2 = e1.is_active(us), e2.is_active(us)
        assert (a1, a2) == (n == 1, n >= 2), f"amount={n} -> ({a1},{a2})"
        assert not (a1 and a2), f"les DEUX instances actives a amount={n} : -20 % ET -40 % cumules"


def test_inert_instance_declares_no_stat_modification_offline():
    """Le gate `self.active` d'`applied_stat_mods` est LOAD-BEARING : les deux instances coexistent,
    une seule porte une `ValueModification` cote natif. Sans lui la passe 2 du seed attribuerait les
    DEUX magnitudes alors que le `statDelta` capte n'en porte qu'une."""
    from engine.entities.effects.loki.status import ContagionsOfNurgleArmorReductionEffect as E
    act = E(name="ContagionsOfNurgle_ArmorReduction1", effect_type=RED1, value=-299, source=7)
    inert = E(name="ContagionsOfNurgle_ArmorReduction1", effect_type=RED1, value=-299, source=7,
              active=False)
    assert act.applied_stat_mods(None) == [(16, -299)]
    assert inert.applied_stat_mods(None) == []
    # ...et AUCUNE cle de POSE eager : sinon `refresh_stat_modifier_effects` skipperait l'instance
    # et le cycle de vie ne pourrait plus ni l'allumer ni l'eteindre.
    assert act.stat_mod_source is None


def test_poser_lays_both_instances_offline(contagions_stage):
    """Le vecteur `On(UnitAdded)` pose la PAIRE `AddEffect(1071) & AddEffect(1072)` -- garde
    anti-collapse. On simule une unite qui APPARAIT dans l'aura : sur un state RECHARGE (jamais
    celui de la fixture, que ce test mute), on retire ses instances, on la place au contact d'un
    porteur ISOLE, et on rejoue `apply_on_unit_added`."""
    import hexgeo
    from engine.runner.operations.triggers.loki.contagions_of_nurgle import (
        apply_on_unit_added, aura_carriers)
    from engine.runner.components import PositionComponent
    st = contagions_stage
    _dec, ob, _snap, state = P._load(st["rid"], st["tiles"])         # copie FRAICHE, isolee
    victim, carrier = st["victim"], st["carrier"]
    state.effects.by_unit[victim] = [e for e in state.effects.by_unit.get(victim, [])
                                     if int(getattr(e, "effect_type", 0) or 0) not in (RED1, RED2)]
    cpos = state.get_entity(carrier).get_component(PositionComponent)
    anchor = (cpos.col, cpos.row)
    # Un SEUL porteur a portee : les autres sont ECARTES offline (le compte doit valoir 1, sinon
    # c'est 1072 qui s'active et l'assertion sur l'instance active ne dirait rien de la fenetre).
    for c in st["carriers"][1:]:
        pc = state.get_entity(c["squadId"]).get_component(PositionComponent)
        pc.col, pc.row = anchor[0], anchor[1] + 9
    vpc = state.get_entity(victim).get_component(PositionComponent)
    occ = {(p.col, p.row) for e, p in state.with_component(PositionComponent) if e.id != victim}
    free = [(t["col"], t["row"]) for t in st["tiles"] if t.get("walkable", True)
            and (t["col"], t["row"]) not in occ
            and hexgeo.distance((t["col"], t["row"]), anchor) == 1]
    if not free:
        pytest.skip("aucune tuile libre au contact du porteur")
    vpc.col, vpc.row = free[0]
    assert aura_carriers(state, victim), "montage KO : la victime n'est dans aucune aura"
    res = apply_on_unit_added(state, victim)
    posed = sorted(int(e.effect_type) for e in state.effects.by_unit.get(victim, [])
                   if int(getattr(e, "effect_type", 0) or 0) in (RED1, RED2))
    print(f"\n[cvc] pose -> {res} | instances={posed}")
    assert posed == [RED1, RED2], (
        f"le vecteur n'a pose que {posed} : le collapse « une seule instance » est de retour "
        "(le natif pose `AddEffect(1071) & AddEffect(1072)`, la fenetre tranche ensuite)")
    assert res and res["effect"] == "ContagionsOfNurgle_ArmorReduction1", (
        f"une seule aura -> 1071 doit etre l'instance ACTIVE ({res})")


# --------------------------------------------------------------------------- montage live

@pytest.fixture(scope="module")
def contagions_stage(live_session, rpc, build_runner):
    """Runner 3 porteurs Contagion (camp adverse) vs 3 victimes, board MC1_67. Un SEUL build pour
    tout le module (discipline runner)."""
    b = build_runner(seed="4242", extra=["--p-units", VICTIMS, "--a-units", CARRIERS, "--no-ai"])
    rid = b["rid"]
    P.rpc = lambda m, a=None, t=90: rpc(m, a, timeout=t)             # le probe parle par la fixture
    tiles = rpc("boardGraph", {"runnerId": rid}, timeout=60)["tiles"]
    dec, ob, snap, state = P._load(rid, tiles)
    alive = [u for u in ob["units"] if not u.get("isDead")]
    carriers = [u for u in alive if u["visualId"].startswith("death")]
    victims = [u for u in alive if u not in carriers]
    if len(carriers) < 2 or not victims:
        pytest.skip("montage Contagion non monte (porteurs/victimes absents)")
    return {"rid": rid, "tiles": tiles, "dec": dec, "ob": ob, "snap": snap, "state": state,
            "carriers": carriers, "victims": victims,
            "carrier": carriers[0]["squadId"], "victim": victims[0]["squadId"]}


def test_both_instances_are_laid_on_every_enemy_live(contagions_stage):
    """`AddEffectInitially` pose 1071 ET 1072 sur CHAQUE ennemi du porteur, inertes hors du disque.
    Le canal LARGE les publie ; le port les materialise a l'identique."""
    st = contagions_stage
    dec, _ob, _snap, state = P._load(st["rid"], st["tiles"])         # scene FRAICHE (le module bouge)
    for v in st["victims"]:
        live = P._live_effects(dec, v["squadId"])
        port, _armor = P._port_state(state, v["squadId"])
        print(f"\n[cvc] {v['visualId']:<14} live={live} port={port}")
        assert set(live) == {RED1, RED2}, (
            f"{v['visualId']} : le canal LARGE ne publie pas les DEUX instances ({live}) -- "
            "montage KO ou canal `includeInactive` non demande")
        assert set(port) == set(live), (
            f"{v['visualId']} : le port materialise {sorted(port)} pour {sorted(live)}")


def test_growing_aura_activates_without_moving_live(contagions_stage):
    """L'aura GRANDIT (`GetCurrentRange` 1 -> 2 avec `TurnsStarted` du porteur) : a distance 2 fixe,
    l'effet passe d'INERTE a ACTIF des deux cotes, chacun par SON vecteur (live `endturn`, port
    `StartTurnOperation`), sans re-seed."""
    st = contagions_stage
    bad = P._stage_c(st["rid"], st["tiles"],
                     next(c for c in st["carriers"] if c["squadId"] == st["carrier"]),
                     next(v for v in st["victims"] if v["squadId"] == st["victim"]),
                     st["carriers"])
    if bad == P.NOT_EXERCISED:                 # jamais un VERT muet (cf. `NOT_EXERCISED`)
        pytest.skip("croissance d'aura NON EXERCEE sur cette scene -- rien n'a ete valide")
    assert bad == 0, "la croissance d'aura n'est pas suivie par le port (cf. sortie du probe)"


def test_active_instance_follows_geometry_live(contagions_stage):
    """L'ensemble ACTIF et `FixedArmor` coincident live/port sur plusieurs geometries, et l'etat
    ACTIF VARIE (sinon la garde ne prouve rien)."""
    import hexgeo
    st = contagions_stage
    rid, tiles = st["rid"], st["tiles"]
    victim, carrier = st["victim"], st["carrier"]
    # ISOLER le porteur mesure : les autres a >= 9 du PORTEUR (pas de la victime) -> la victime, qui
    # tournera a <= 4 de lui, reste a >= 5 d'eux, donc hors du rayon max 3. Sans ca le compte
    # d'auras melange plusieurs porteurs et l'etat ACTIF ne varie plus avec la distance mesuree.
    ob = P.rpc("observeBattle", {"runnerId": rid}, 40)
    ck0 = P._pos_of(ob, carrier)
    for c in st["carriers"]:
        if c["squadId"] != carrier:
            P._place(rid, tiles, c["squadId"], ck0, 9)
    seen, bad = [], []
    for want in (4, 3, 2, 1):
        ob = P.rpc("observeBattle", {"runnerId": rid}, 40)
        ck = P._pos_of(ob, carrier)
        P._place(rid, tiles, victim, ck, want)
        dec, ob, snap, state = P._load(rid, tiles)
        d = hexgeo.distance(P._pos_of(ob, victim), P._pos_of(ob, carrier))
        live = sorted(t for t, a in P._live_effects(dec, victim).items() if a)
        port = sorted(t for t, a in P._port_state(state, victim)[0].items() if a)
        larm, parm = P._live_fixed_armor(snap, victim), P._port_state(state, victim)[1]
        print(f"\n[cvc] d={d} live={live} port={port} armure live={larm} port={parm}")
        seen.append(tuple(live))
        if live != port or larm != parm:
            bad.append((d, live, port, larm, parm))
    assert not bad, f"desaccords live/port sur la geometrie : {bad}"
    assert len(set(seen)) >= 2, (
        f"l'etat ACTIF n'a pas VARIE ({seen}) : la garde ne discrimine rien sur cette scene")


def test_leaving_aura_reverts_the_modification_live(contagions_stage):
    """Le port joue le pas de SORTIE par son propre `MoveUnitOperation` et rend la MEME armure que
    le natif -- `DeactivateEffect` -> `UpdateEffectTargets([])` -> `RevertModification`."""
    st = contagions_stage
    bad = P._stage_e(st["rid"], st["tiles"],
                     next(c for c in st["carriers"] if c["squadId"] == st["carrier"]),
                     st["carriers"][1],
                     next(v for v in st["victims"] if v["squadId"] == st["victim"]),
                     st["carriers"])
    if bad == P.NOT_EXERCISED:                 # jamais un VERT muet (cf. `NOT_EXERCISED`)
        pytest.skip("sortie d'aura NON EXERCEE sur cette scene -- rien n'a ete valide")
    assert bad == 0, "la sortie d'aura ne retire pas la contribution cote port (cf. sortie du probe)"
