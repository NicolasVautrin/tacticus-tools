"""#112 DarkAngels lot 1 — FACE COMBAT des 3 actives portees, confront LIVE + discriminants offline.

Portees (arbres DSL, `engine/runner/abilities/darkangels.py`) :
  * `SuperchargeAbility$$ExecuteBehaviour`          (1103, darkaHellblaster « Sarquael »)
  * `ExemplarOfHateAbility$$ExecuteBehaviour`       (1140, darkaAsmodai « Asmodai »)
  * `CalibaniteGreatswordAbility$$ExecuteBehaviour` (1189, darkaCompanion « Forcas »)

Les batailles sont montees par `probe_112_darkangels.build` : le camp joueur est DEPLACE AU CONTACT du
camp adverse (les 9-11 hexes entre les deux coins de MC1_67 rendraient la branche Chaos d'ExemplarOfHate
et le volet SPLASH de Supercharge intestables -- « bloque par la geometrie de spawn » n'est pas une
reponse).

Ce que ces tests PROUVENT :
  (1) Supercharge, cible SANS unite derriere : degat LIVE == degat PORT **BIT-EXACT** (aucun tirage
      `PickRandomly` ne s'interpose) -> la chaine bornes/profil/percage/mods/effet est exacte.
  (2) Supercharge, cible AVEC unites derriere : les 3 `Supercharge_ExtraPiercing` (cible + les <=2
      unites derriere) sont poses AVANT les deux volets de degat, et le SPLASH frappe EXACTEMENT ces
      unites-la. RESIDU MESURE (non asserte) : le degat n'est PAS bit-exact des qu'il y a >=1 unite
      derriere -- le natif consomme des tirages supplementaires (cf. §RESIDU en bas de fichier).
  (3) Supercharge : l'effet de percage BONIFIE SES PROPRES COUPS (A/B offline) -> l'`AddEffect` est bien
      le PREMIER volet du `&`, pas le dernier.
  (4) ExemplarOfHate : `ExemplarOfHate_Target`(1293) + `Pinned`(1065) poses, ATTAQUANT elu identique au
      live, et montant d'override `PercentageOfAttackCappedAtMax` **EXACT vs `UnitStats_Attack_Override`**.
  (5) ExemplarOfHate : cible NON-Chaos -> SEUL le debuff 1293 (ni Pinned, ni attaque libre) ; l'election
      d'attaquant ignore les allies NON-DarkAngels et hors portee.
  (6) CalibaniteGreatsword : toggle Strike->Sweep puis Sweep->Strike, port == live sur les effets de
      POSTURE (1404/1405), sans degat ni fin de tour.

RESIDUS NOMMES (mesures, non assertes) :
  * RNG : avec 2 unites derriere, le degat live s'aligne sur le port decale de +2 tirages pour le volet
    MAIN et +5 pour le volet SPLASH (mesure #112, seed 112112, MC1_67 au contact) -> le natif consomme
    2 tirages au `PickRandomly(UnitsDirectlyBehind, 2)` **meme quand le pool tient dans n** (ce que
    `_pick_randomly_n` ne fait PAS : « le natif ne roll pas quand le set tient ») + 1 tirage
    supplementaire avant le splash. C'est le GAP #215 (cout/ordre du PickRandomly non cale), desormais
    CHIFFRE. Non corrige ici : `_pick_randomly_n` est PARTAGE (PlasmaCannon/Fragstorm/BringerOfDespair).
  * ExemplarOfHate : le degat de l'attaque libre est CONFONDU par le passif non porte
    `FearedInterrogator` de darkaAsmodai (live 6 coups vs 4 = `weapons[0].hits` de la config ; effets
    `FearedInterrogator_Owner`/`_Target` presents des le spawn). On asserte donc l'override et le
    ciblage, PAS le per-coup de l'attaque libre.
  * Immunite d'effet : `BaseEffect.EntityIsImmuneToEffect` (+ surcharges) n'est pas portee ->
    `Pinned` est pose par le port sur une cible a trait `TerminatorArmour` alors que le natif le refuse
    (i2 « This unit cannot be Suppressed » ; MESURE #112 sur blackAbaddon). Les tests evitent donc les
    cibles TerminatorArmour pour la branche Chaos.

ASCII-only. Dispose SES runners.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
import probe_112_darkangels as PR
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.dsl.effects import ExecutionContext
from engine.entities.behaviours import AtomicGroup, op_and
from engine.entities.selectors import Target, UnitSet
from engine.runner.abilities.behaviours import AttackWithAttackDamage, entities_from_state
from engine.runner.abilities.darkangels import (SuperchargeAbility, ExemplarOfHateAbility,
                                                CalibaniteGreatswordAbility, supercharge_tree,
                                                _supercharge_behind, _exemplar_of_hate_attackers,
                                                _exemplar_capped_attack_vars)

SUPERCHARGE, EXEMPLAR, CALIBANITE = 1103, 1140, 1189
EXTRA_PIERCING, EOH_TARGET, PINNED = 1208, 1293, 1065
CG_STRIKE, CG_SWEEP = 1404, 1405


# ------------------------------------------------------------------ helpers

def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _dmg_by_target(action: dict) -> dict:
    """`Amount` par cible dans la cascade d'une action live."""
    out = {}
    for e in (action.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td:
            out.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return out


def _tag_value(action: dict, key: str):
    for e in (action.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if key in td:
            return td[key], e.get("entity")
    return None, None


def _effect_groups(action: dict) -> list:
    return [e.get("source") for e in (action.get("events") or [])
            if e.get("kind") == "group" and e.get("group") == 22]


def _behind(dv, pos, caster, target):
    """`UnitsDirectlyBehind(caster, target)` : ennemis du caster sur l'anneau R1 de la cible, du cote
    OPPOSE au caster (`MinDistance(caster,cand) > MinDistance(caster,target)`, STRICT)."""
    dt = hexgeo.distance(pos[caster], pos[target])
    return sorted(e["id"] for e in dv["units"]
                  if (not e.get("ctrl")) and e["id"] != target
                  and hexgeo.distance(pos[e["id"]], pos[target]) == 1
                  and hexgeo.distance(pos[caster], pos[e["id"]]) > dt)


@pytest.fixture(scope="module")
def da_runner(live_session):
    """Runner DarkAngels-vs-BlackLegion AU CONTACT (module-scope : 1 build pour tous les tests LIVE
    lecture-seule + les replays offline ; les tests qui CASTENT live prennent `da_fresh`)."""
    sid = live_session
    rid = PR.build(sid)
    try:
        yield sid, rid
    finally:
        PR.dispose(sid, rid)


@pytest.fixture
def da_fresh(live_session):
    """Runner FRAIS par test (un cast live mute l'etat -> pas de partage)."""
    sid = live_session
    rid = PR.build(sid)
    try:
        yield sid, rid
    finally:
        PR.dispose(sid, rid)


def _snapshot(sid, rid):
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    rng = PR.rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng, dict) and rng.get("mt")):
        pytest.skip("dumpRng KO")
    return board, dv, ob, cs, rng


# ------------------------------------------------------------------ (1) Supercharge bit-exact

def test_supercharge_live_bitexact_without_units_behind(da_fresh):
    """Cible SANS unite derriere -> AUCUN tirage `PickRandomly` ne s'interpose : le degat du volet MAIN
    est BIT-EXACT vs live, et `Supercharge_ExtraPiercing` (1208) est pose sur la cible.

    C'est LE datapoint qui prouve la chaine complete (bornes minDmg/maxDmg config-scalees, profil Plasma
    pierce 65, armure de la cible, %-list attaquant, ET le +extraPierceRatio de l'effet pose par l'ability
    elle-meme) -- independamment du residu RNG du `PickRandomly` (cf. en-tete)."""
    sid, rid = da_fresh
    board, dv, ob, cs, rng = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "darkaHellblaster" not in bv:
        pytest.skip("darkaHellblaster absent")
    caster = bv["darkaHellblaster"]["id"]
    pos = PR.positions(dv)
    legal = PR.legal_from_here(sid, rid, caster, SUPERCHARGE)   # `fromHere` (JAMAIS `targets`), cf. #111
    cands = [t for t in legal if not _behind(dv, pos, caster, t)]
    if not cands:
        pytest.skip("aucune cible legale sans unite derriere")
    tgt = cands[0]

    st = load_state(dv, ob, cs, board=board)
    st.rng = _seed_rng(rng)
    off = SuperchargeAbility().execute_behaviour(st, caster, tgt)
    assert off is not None and off.get("dsl") is True
    off_main = (off.get("main_attack") or {}).get("per_hit") or []

    res = PR.cast(sid, rid, caster, tgt, SUPERCHARGE)
    assert res.get("ok"), f"cast live KO: {str(res)[:200]}"
    live = _dmg_by_target(res)
    print(f"\n[SC bitexact] caster u{caster} -> u{tgt} (behind=[]) "
          f"off={off_main} live={live.get(tgt)}")
    assert tgt in (off.get("pierce_effect") or []), \
        f"Supercharge_ExtraPiercing non pose sur la cible u{tgt} ({off.get('pierce_effect')})"
    assert "Supercharge_ExtraPiercing" in _effect_groups(res), \
        f"live ne pose pas Supercharge_ExtraPiercing: {_effect_groups(res)}"
    assert set(live) == {tgt}, f"live frappe {set(live)} != {{u{tgt}}} (aucune unite derriere)"
    assert off_main == live[tgt], \
        f"degat MAIN port {off_main} != live {live[tgt]} (chaine bornes/percage/mods/effet)"


# ------------------------------------------------------------------ (2) Supercharge ciblage + effets

def test_supercharge_live_pierce_effect_on_target_and_behind(da_fresh):
    """Cible AVEC unites derriere : l'`AddEffect(1208)` couvre `op_Addition(target, PickRandomly(
    UnitsDirectlyBehind, 2))` = la cible ET les unites derriere, et le volet SPLASH frappe EXACTEMENT
    ces memes unites. (Degat non asserte -- residu RNG documente en en-tete.)"""
    sid, rid = da_fresh
    board, dv, ob, cs, rng = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "darkaHellblaster" not in bv:
        pytest.skip("darkaHellblaster absent")
    caster = bv["darkaHellblaster"]["id"]
    pos = PR.positions(dv)
    legal = PR.legal_from_here(sid, rid, caster, SUPERCHARGE)
    ranked = sorted(legal, key=lambda t: -len(_behind(dv, pos, caster, t)))
    if not ranked or not _behind(dv, pos, caster, ranked[0]):
        pytest.skip("aucune cible legale avec unite derriere")
    tgt = ranked[0]
    bh = _behind(dv, pos, caster, tgt)

    st = load_state(dv, ob, cs, board=board)
    st.rng = _seed_rng(rng)
    off = SuperchargeAbility().execute_behaviour(st, caster, tgt)
    res = PR.cast(sid, rid, caster, tgt, SUPERCHARGE)
    assert res.get("ok"), f"cast live KO: {str(res)[:200]}"
    live = _dmg_by_target(res)
    groups = _effect_groups(res)
    print(f"\n[SC targets] u{caster} -> u{tgt} behind={bh} "
          f"port_eff={off.get('pierce_effect')} port_splash={[p['target'] for p in off.get('splash') or []]} "
          f"live_dmg={sorted(live)} live_groups={groups}")

    # (a) l'effet couvre cible + derriere, cote PORT comme cote LIVE (1 groupe 1208 par unite)
    assert sorted(off.get("pierce_effect") or []) == sorted([tgt] + bh), \
        f"effet porte sur {off.get('pierce_effect')} != cible+derriere {[tgt] + bh}"
    assert groups.count("Supercharge_ExtraPiercing") == 1 + len(bh), \
        f"live pose {groups.count('Supercharge_ExtraPiercing')} effets != {1 + len(bh)}"
    # (b) le SPLASH frappe exactement les unites derriere (ni la cible, ni d'autres)
    assert sorted(p["target"] for p in (off.get("splash") or [])) == bh, \
        f"splash port {[p['target'] for p in off.get('splash') or []]} != derriere {bh}"
    assert set(live) == set([tgt] + bh), f"live frappe {set(live)} != {set([tgt] + bh)}"
    # (c) ORDRE : les 3 poses d'effet precedent le 1er degat (l'AddEffect est le 1er volet du `&`)
    kinds = [(e.get("group"), e.get("source")) for e in (res.get("events") or [])
             if e.get("kind") == "group"]
    first_dmg = next((i for i, (g, _s) in enumerate(kinds) if g == 26), None)
    last_eff = max((i for i, (g, s) in enumerate(kinds)
                    if g == 22 and s == "Supercharge_ExtraPiercing"), default=None)
    assert first_dmg is not None and last_eff is not None and last_eff < first_dmg, \
        f"les effets de percage ne precedent pas le degat (eff@{last_eff}, dmg@{first_dmg})"


def test_supercharge_pierce_effect_boosts_its_own_hits(da_runner):
    """A/B OFFLINE : l'arbre complet (AddEffect PUIS attaques) fait PLUS de degat que le meme arbre SANS
    l'`AddEffect` -> le +extraPierceRatio s'applique aux coups de Supercharge EUX-MEMES. Discriminant de
    l'ORDRE du `&` : un arbre qui poserait l'effet APRES les attaques donnerait les MEMES degats."""
    sid, rid = da_runner
    board, dv, ob, cs, rng = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "darkaHellblaster" not in bv:
        pytest.skip("darkaHellblaster absent")
    caster = bv["darkaHellblaster"]["id"]
    legal = PR.legal_from_here(sid, rid, caster, SUPERCHARGE)
    if not legal:
        pytest.skip("aucune cible legale")
    tgt = legal[0]

    def run(with_effect: bool):
        st = load_state(dv, ob, cs, board=board)
        st.rng = _seed_rng(rng)
        bh = _supercharge_behind(st, caster, tgt)
        ectx = ExecutionContext(state=st, rng=st.rng)
        if with_effect:
            tree = supercharge_tree(bh)
        else:                                   # MEME arbre, `AddEffect` retire (control)
            bs = UnitSet(bh)
            tree = AtomicGroup(op_and(
                AttackWithAttackDamage(Target(), "Supercharge", "Plasma", is_melee=False,
                                       native_factory="attack"),
                AttackWithAttackDamage(bs, "Supercharge", "Plasma", is_melee=False,
                                       min_key="minDmg_2", max_key="maxDmg_2",
                                       hits_key="nrOfHits_2", multi=True, native_factory="attack")))
        tree.execute(entities_from_state(st, caster, tgt), ectx)
        return {p.get("target"): p["attack"]["total"] for n, p in ectx.emitted
                if n == "AttackWithAttackDamage"}

    with_eff, without = run(True), run(False)
    print(f"\n[SC pierce A/B] u{caster}->u{tgt} avec={with_eff} sans={without}")
    assert set(with_eff) == set(without) and with_eff, "A/B : cibles differentes (test invalide)"
    assert all(with_eff[t] > without[t] for t in with_eff), \
        f"le +percage ne bonifie pas ses propres coups : avec={with_eff} sans={without}"


def test_supercharge_pierce_effect_persists_and_is_plasma_gated(da_runner):
    """GENERALISATION : l'effet 1208 SURVIT au cast et bonifie les coups PLASMA **suivants** contre les
    unites marquees (i2 : « Until the beginning of Sarquael's next turn, any further hits that deal
    Plasma Damage against these units also have +extraPierceRatio% pierce ratio »), et SEULEMENT eux
    (gate `DamageProfileIs(GetDamageProfile(config)=Plasma)`).

    Exerce le canal NEUF `create_piercing_bonus_for_attack` -> `build_defender_modifiers_from_effects`
    -> `AttackDamageOperation._apply_defender_flat_reductions` (fusion defenseur->attaquant de
    `extra_pierce`), sur un vecteur qui n'est PAS Supercharge."""
    sid, rid = da_runner
    board, dv, ob, cs, rng = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "darkaHellblaster" not in bv:
        pytest.skip("darkaHellblaster absent")
    caster = bv["darkaHellblaster"]["id"]
    legal = PR.legal_from_here(sid, rid, caster, SUPERCHARGE)
    if not legal:
        pytest.skip("aucune cible legale")
    tgt = legal[0]
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.abilities.base import ability_attack_params

    def probe(profile, with_supercharge):
        """1 coup d'ability `profile` sur `tgt`, avec ou sans l'effet de percage prealable."""
        st = load_state(dv, ob, cs, board=board)
        st.rng = _seed_rng(rng)
        if with_supercharge:
            SuperchargeAbility().execute_behaviour(st, caster, tgt)
        st.rng = _seed_rng(rng)                       # MEME flux pour les deux branches
        bmin, bmax, pierce, _h = ability_attack_params(st, caster, "PlasmaCannon", profile, ranged=True)
        r = AttackDamageOperation.execute_ability_attack(
            st, caster, tgt, bmin, bmax, pierce, 1, damage_profile=profile, is_melee=False)
        return (r or {}).get("total")

    plasma_off, plasma_on = probe("Plasma", False), probe("Plasma", True)
    power_off, power_on = probe("Power", False), probe("Power", True)
    print(f"\n[SC persist] u{caster}->u{tgt} Plasma sans={plasma_off} avec={plasma_on} | "
          f"Power sans={power_off} avec={power_on}")
    assert plasma_on is not None and plasma_off is not None
    assert plasma_on > plasma_off, \
        f"le +percage ne survit pas au cast pour un coup PLASMA suivant ({plasma_off} -> {plasma_on})"
    assert power_on == power_off, \
        f"gate DamageProfileIs viole : un coup NON-Plasma est bonifie ({power_off} -> {power_on})"


# ------------------------------------------------------------------ (4) ExemplarOfHate LIVE

def test_exemplar_live_effects_attacker_and_override(da_fresh):
    """Cible CHAOS a portee d'un allie DarkAngels : port == live sur (a) les DEUX effets poses
    (`ExemplarOfHate_Target` 1293 + `Pinned` 1065), (b) l'ATTAQUANT elu, (c) le MONTANT d'override
    `PercentageOfAttackCappedAtMax` (`UnitStats_Attack_Override` de la cascade).

    Le degat de l'attaque libre n'est PAS asserte : il est confondu par le passif non porte
    `FearedInterrogator` d'Asmodai (cf. en-tete). On evite les cibles a trait `TerminatorArmour`
    (immunite Suppressed non portee)."""
    sid, rid = da_fresh
    board, dv, ob, cs, rng = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "darkaAsmodai" not in bv:
        pytest.skip("darkaAsmodai absent")
    caster = bv["darkaAsmodai"]["id"]
    pos = PR.positions(dv)
    legal = PR.legal_from_here(sid, rid, caster, EXEMPLAR)
    if not legal:
        pytest.skip("aucune cible legale")
    import gameconfig as GC
    vis = {u["id"]: u.get("visualId") for u in dv["units"]}

    def has_termi(uid):
        return "TerminatorArmour" in ((GC.unit(vis.get(uid)) or {}).get("traits") or [])
    cands = [t for t in legal if not has_termi(t)]
    if not cands:
        pytest.skip("toutes les cibles legales sont TerminatorArmour (immunite Pinned non portee)")
    tgt = min(cands, key=lambda e: hexgeo.distance(pos[caster], pos[e]))

    st = load_state(dv, ob, cs, board=board)
    st.rng = _seed_rng(rng)
    off = ExemplarOfHateAbility().execute_behaviour(st, caster, tgt)
    assert off is not None and off.get("dsl") is True

    res = PR.cast(sid, rid, caster, tgt, EXEMPLAR)
    assert res.get("ok"), f"cast live KO: {str(res)[:200]}"
    groups = _effect_groups(res)
    live_ov, live_ov_owner = _tag_value(res, "UnitStats_Attack_Override")
    print(f"\n[EOH live] u{caster}->u{tgt} port_eff={off.get('effects')} port_att=u{off.get('attacker')} "
          f"port_ov={off.get('attack_override')} | live_groups={groups} live_ov={live_ov}@u{live_ov_owner}")

    assert EOH_TARGET in (off.get("effects") or []), f"debuff 1293 non pose ({off.get('effects')})"
    assert "ExemplarOfHate_Target" in groups, f"live ne pose pas le debuff ({groups})"
    assert PINNED in (off.get("effects") or []), f"Pinned non pose sur cible Chaos ({off.get('effects')})"
    assert "Pinned" in groups, f"live ne pose pas Pinned sur cible Chaos ({groups})"
    if live_ov is None:
        pytest.skip("aucun allie DarkAngels a portee live (branche attaque libre non exercee)")
    assert off.get("attacker") == live_ov_owner, \
        f"attaquant elu port u{off.get('attacker')} != live u{live_ov_owner}"
    assert off.get("attack_override") == live_ov, \
        f"override port {off.get('attack_override')} != live {live_ov} (PercentageOfAttackCappedAtMax)"


# ------------------------------------------------------------------ (5) discriminants OFFLINE

def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def test_exemplar_non_chaos_target_gets_only_the_debuff(da_runner):
    """DISCRIMINANT `If(HasTrait(target, 0x7ea=Chaos))` : contre une cible NON-Chaos, SEUL le debuff
    1293 est pose -- ni `Pinned`, ni override, ni attaque libre. Refute un port qui executerait la
    branche inconditionnellement (et refute aussi un `HasTrait(Target(), 2026)` naif, qui serait
    TOUJOURS faux -> Chaos jamais declenche : le test (4) prouve l'autre sens)."""
    sid, rid = da_runner
    board, dv, ob, cs, rng = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "darkaAsmodai" not in bv:
        pytest.skip("darkaAsmodai absent")
    caster = bv["darkaAsmodai"]["id"]
    # On RETIRE la grande-alliance Chaos de la cible en la faisant passer pour une unite Imperiale :
    # `HasGrandAlliance` lit `ctx.faction_of(unit)` = FactionId gameconfig du `visualId`.
    st = load_state(dv, ob, cs, board=board)
    st.rng = _seed_rng(rng)
    from engine.runner.components import OwnerComponent, UnitComponent
    coc = st.get_entity(caster).get_component(OwnerComponent)
    tgt = next(uid for uid, e in sorted(st.entities.items())
               if e.get_component(OwnerComponent) is not None
               and e.get_component(OwnerComponent).team != coc.team
               and e.get_component(UnitComponent) is not None
               and e.get_component(UnitComponent).alive)
    st.get_entity(tgt).get_component(UnitComponent).visual_id = "ultraTitus"   # Imperial, non-Chaos
    off = ExemplarOfHateAbility().execute_behaviour(st, caster, tgt)
    print(f"\n[EOH non-chaos] u{caster}->u{tgt}(ultraTitus/Imperial) effets={off.get('effects')} "
          f"attaquant={off.get('attacker')} attaque={off.get('attack') is not None}")
    assert off.get("effects") == [EOH_TARGET], \
        f"cible non-Chaos : effets {off.get('effects')} != [{EOH_TARGET}] (branche Chaos executee a tort)"
    assert off.get("attack") is None, "cible non-Chaos : aucune attaque libre ne doit partir"
    assert off.get("attack_override") is None, "cible non-Chaos : aucun override ne doit etre pose"


def test_exemplar_attacker_selection_is_dark_angels_in_range_best_first(da_runner):
    """DISCRIMINANT du collapse `GetAttacker` : le vivier est `UnitsWhoCanAttack(UnitsFromFaction(
    Friends(caster), DarkAngels), target)` trie par `SortAttackersByDamagePrediction`.
      (a) un allie NON-DarkAngels a portee n'est JAMAIS elu ;
      (b) un allie DarkAngels HORS portee d'arme n'est jamais elu ;
      (c) l'elu est celui de plus haute cle de prediction (ici : le plus gros `override x coups`)."""
    sid, rid = da_runner
    board, dv, ob, cs, rng = _snapshot(sid, rid)
    st = load_state(dv, ob, cs, board=board)
    st.rng = _seed_rng(rng)
    from engine.runner.components import OwnerComponent, UnitComponent
    from engine.ai.action_generators import _faction

    def vis(uid):
        return st.get_entity(uid).get_component(UnitComponent).visual_id
    caster = next(uid for uid, e in sorted(st.entities.items())
                  if e.get_component(UnitComponent) is not None
                  and e.get_component(UnitComponent).visual_id == "darkaAsmodai")
    cteam = st.get_entity(caster).get_component(OwnerComponent).team
    allies = [uid for uid, e in sorted(st.entities.items())
              if e.get_component(OwnerComponent) is not None
              and e.get_component(OwnerComponent).team == cteam
              and e.get_component(UnitComponent) is not None
              and e.get_component(UnitComponent).alive]
    tgt = next(uid for uid, e in sorted(st.entities.items())
               if e.get_component(OwnerComponent) is not None
               and e.get_component(OwnerComponent).team != cteam
               and e.get_component(UnitComponent) is not None
               and e.get_component(UnitComponent).alive)
    if len(allies) < 3:
        pytest.skip("au moins 3 allies requis")

    # geometrie DRIVEE : cible en (c,r) ; on colle 2 allies DarkAngels a cote, on eloigne les autres.
    from engine.runner.components import PositionComponent
    tp = st.get_entity(tgt).get_component(PositionComponent)
    tpos = (tp.col, tp.row)
    ring = [board.coord(t) for t in sorted(board.by_id)
            if board.walkable(t) and hexgeo.distance(board.coord(t), tpos) == 1]
    far = [board.coord(t) for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), tpos) > 6]
    if len(ring) < 2 or not far:
        pytest.skip("geometrie insuffisante (anneau R1 / tuiles lointaines)")
    near_ids = allies[:2]
    for i, uid in enumerate(near_ids):
        _set_pos(st, uid, *ring[i])
    for j, uid in enumerate(allies[2:]):
        _set_pos(st, uid, *far[j % len(far)])
    # un allie NON-DarkAngels COLLE a la cible (leurre) : on maquille le 2e voisin en ultraTitus.
    lure = near_ids[1]
    st.get_entity(lure).get_component(UnitComponent).visual_id = "ultraTitus"

    cap, pct = _exemplar_capped_attack_vars(st, caster)
    ranked = _exemplar_of_hate_attackers(st, caster, tgt, cap, pct)
    print(f"\n[EOH attacker] cible=u{tgt}@{tpos} adj={[(u, vis(u)) for u in near_ids]} "
          f"loin={allies[2:]} -> ranked={ranked} (factions={[_faction(vis(u)) for u in ranked]})")
    assert lure not in ranked, \
        f"un allie NON-DarkAngels (u{lure}, {vis(lure)}) est dans le vivier {ranked}"
    assert all(_faction(vis(u)) == "DarkAngels" for u in ranked), \
        f"vivier non filtre par faction : {[(u, vis(u)) for u in ranked]}"
    assert set(ranked) <= set(near_ids), \
        f"un allie HORS portee est dans le vivier : {ranked} (a portee : {near_ids})"
    off = ExemplarOfHateAbility().execute_behaviour(st, caster, tgt)
    assert off.get("attacker") == (ranked[0] if ranked else None), \
        f"l'elu {off.get('attacker')} != tete du classement {ranked}"


# ------------------------------------------------------------------ (6) CalibaniteGreatsword

def test_calibanite_toggle_live_both_directions(da_fresh):
    """TOGGLE de POSTURE : port == live dans les DEUX sens. Forcas demarre en STRIKE (1404, pose par la
    triggered `CalibaniteGreatsword_SetStartAbility`) -> cast 1 : +1405 / -1404 ; tour suivant, cast 2 :
    +1404 / -1405. Aucun degat, aucune fin de tour."""
    sid, rid = da_fresh
    board, dv, ob, cs, rng = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "darkaCompanion" not in bv:
        pytest.skip("darkaCompanion absent")
    uid = bv["darkaCompanion"]["id"]
    pre = {e[0] for e in PR.eff_names(dv, uid)}
    if CG_STRIKE not in pre:
        pytest.skip(f"Forcas ne demarre pas en posture Strike ({sorted(pre)})")

    # --- PORT (replay offline du meme etat) ---
    st = load_state(dv, ob, cs, board=board)
    st.rng = _seed_rng(rng)
    off1 = CalibaniteGreatswordAbility().execute_behaviour(st, uid, uid)
    off2 = CalibaniteGreatswordAbility().execute_behaviour(st, uid, uid)   # 2e bascule (retour Strike)

    # --- LIVE ---
    r1 = PR.cast(sid, rid, uid, uid, CALIBANITE)
    dv1 = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    post1 = {e[0] for e in PR.eff_names(dv1, uid)}
    PR.act(sid, rid, {"kind": "endturn"})
    PR.rpc(sid, "aiPlayByUnit",
           {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999, "maxPump": 400}, 300)
    r2 = PR.cast(sid, rid, uid, uid, CALIBANITE)
    dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    post2 = {e[0] for e in PR.eff_names(dv2, uid)}

    print(f"\n[CG toggle] u{uid} port1={off1.get('stance')} add={off1.get('added')} rm={off1.get('removed')}"
          f" | port2={off2.get('stance')} add={off2.get('added')} rm={off2.get('removed')}")
    print(f"[CG toggle] live1 groups={_effect_groups(r1)} post={sorted(post1)}")
    print(f"[CG toggle] live2 groups={_effect_groups(r2)} post={sorted(post2)}")

    # cast 1 : Strike -> Sweep, des DEUX cotes
    assert off1.get("stance") == "Sweep" and CG_SWEEP in (off1.get("added") or []) \
        and CG_STRIKE in (off1.get("removed") or []), f"port cast1 {off1}"
    assert "CalibaniteGreatswordSweep" in _effect_groups(r1) \
        and "CalibaniteGreatswordStrike" in _effect_groups(r1), f"live cast1 {_effect_groups(r1)}"
    assert CG_SWEEP in post1 and CG_STRIKE not in post1, f"live post1 {sorted(post1)}"
    # cast 2 : Sweep -> Strike, des DEUX cotes
    assert off2.get("stance") == "Strike" and CG_STRIKE in (off2.get("added") or []) \
        and CG_SWEEP in (off2.get("removed") or []), f"port cast2 {off2}"
    assert CG_STRIKE in post2 and CG_SWEEP not in post2, f"live post2 {sorted(post2)}"
    # aucun degat, aucune fin de tour (1189 est dans les 2 inventaires de base.py)
    assert not _dmg_by_target(r1) and not _dmg_by_target(r2), "le toggle ne doit infliger AUCUN degat"
