"""#79 (retrofit case-66) -- RitesOfMorkai : self-revive ONE-SHOT de l'unite « Inspired ».

`RitesOfMorkaiEffect` (IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$.ctor / filter IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$CreateTargetFilter) = sous-classe de `ReviveEffect`
(IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger / IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour) :
  * filtre = `get_OwnerIsTarget` -> le porteur de l'effet se revive LUI-MEME (aucun AreFriends/IsAdjacent :
    la portee a deja ete appliquee a la POSE de l'effet par l'active 1211 de Baldr) ;
  * ctor `removeEffect=TRUE` (champ 0x488) -> le 2e volet du behaviour est `GetRemoveEffectBehaviour` et
    NON `DeactivateEffect` => revive **one-shot DEFINITIF** (i2 : « The **first time** each inspired unit
    would be defeated ») -- contraste Narthecium/TaintedNarthecium (0x488=0 -> once-per-TURN) ;
  * `get_ReviveOnOverkill` non surcharge -> BASE GameCamera$$ShouldBlurBackground `return 0` => « unless Overkilled » (i2 idem).

VOIE : `spaceWolfPriest` (Baldr) est absent du seed BC capture, ce qui avait ete lu comme « hors
pool donc non confrontable ». C'est FAUX -- `catalog_inject.write_augmented_seed_bc` l'injecte dans
les DEUX catalogues (`Units` + `Abilities`) et il entre au pool (97 -> 98). Deux familles de gardes
cohabitent donc ici :
  * `rom_env` / `rom_alt_env` -- etat LIVE quelconque + effet 1502 **INJECTE** dans `state.effects` :
    exercent les 3 discriminants du port (self-only, one-shot, unless-Overkilled) et le gate
    `IsActive` sur des rosters/boards varies, sans dependre du porteur ;
  * `rom_native_env` -- Baldr REELLEMENT spawne, `RitesOfMorkai` (1211) REELLEMENT caste : les
    instances 1502 viennent de la cascade native et transitent par le canal
    (`readEffectsByUnit` -> `decisionView` -> `load_state`). cf.
    `docs/rl/case-229-1502-rites-of-morkai-live-confrontation.md`.

4e discriminant depuis 2026-07-29 (residu #229) : le gate `EffectComponent.IsActive @+0x5c` que
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` applique AVANT
d'evaluer le trigger de cible. Une instance 1502 seedee INERTE (canal
`decisionView { includeInactive: true }`, seede depuis #219) ne doit RIEN declencher.
ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.triggers.dispatch.move_death import after_death_triggers
from engine.runner.operations.revive import reset_revive_gates, kill_unit_revive_gate
from engine.runner.components import (UnitComponent, HealthComponent, PositionComponent,
                                      StatsComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.pathfinding.board import Board
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.magnitude import ability_var
from engine.runner.operations.triggers.loki.rites_of_morkai import RITES_OF_MORKAI_EFFECT

# Roster quelconque du pool : le porteur reel (spaceWolfPriest) est hors pool -> on INJECTE l'effet.
BUILD = ["--p-units", "ultraTitus,bloodIntercessor", "--a-units", "worldKharn",
         "--rank", "17", "--board", "MC1_67"]
# Roster + board DIFFERENTS (autres factions, autres traits/PV, autre geometrie) : sert de
# generalisation au gate `IsActive` -- il ne doit dependre d'aucune particularite de BUILD.
# ⚠ Roster NON-MECHANICAL obligatoire : `get_HealType` de RitesOfMorkai vaut 0 (Heal), donc
# `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` REFUSE les mecaniques -> un roster
# Necron/AdMec rendrait le controle POSITIF faux-negatif (mesure : `necroOverlord` ne revive pas,
# et c'est le comportement CORRECT -- i2 : « friendly NON-MECHANICAL units »).
BUILD_ALT = ["--p-units", "eldarFarseer,astraCreed", "--a-units", "orksNob",
             "--rank", "17", "--board", "C3_01"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _first_player_unit(state):
    from engine.runner.components import OwnerComponent
    teams = {}
    for uid, e in state.entities.items():
        oc = e.get_component(OwnerComponent)
        if oc is not None:
            teams.setdefault(oc.team, []).append(uid)
    t = sorted(teams)[0]
    return teams[t][0], teams[t][1] if len(teams[t]) > 1 else None


@pytest.fixture(scope="module")
def rom_env(live_session, rpc, build_runner):
    rid = build_runner("31337", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live KO")
    st0 = load_state(dv, ob, snap, board=board)
    if getattr(st0, "effects", None) is None:
        pytest.skip("pas d'EffectsState (combatSnapshot partiel)")
    return {"dv": dv, "ob": ob, "snap": snap, "board": board}


@pytest.fixture(scope="module")
def rom_alt_env(live_session, rpc, build_runner):
    """Second etat LIVE (autre roster, autre board, autre seed) pour la generalisation du gate."""
    rid = build_runner("4242", extra=BUILD_ALT)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo (alt)")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live KO (alt)")
    st0 = load_state(dv, ob, snap, board=board)
    if getattr(st0, "effects", None) is None:
        pytest.skip("pas d'EffectsState (combatSnapshot partiel, alt)")
    return {"dv": dv, "ob": ob, "snap": snap, "board": board}


def _fresh(env, seed=777):
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"])
    st.rng = IntBasedMersenneTwister(seed)
    return st


POSER_LEVEL = 50          # niveau de l'ACTIVE RitesOfMorkai du poseur (Baldr) transporte par l'effet
POSER_MULT = 180          # AbilityVariablesMultiplierPercentage du poseur


def _inspire(st, uid, level=POSER_LEVEL, mult=POSER_MULT):
    """Pose l'effet 1502 « Inspired » sur `uid` -- mirror de ce que fait l'active 1211 de Baldr
    (`AddEffectOperation`), le porteur reel etant hors pool. L'effet TRANSPORTE le niveau/multiplicateur
    de l'ability du POSEUR (c'est l'`abilityState` que lit `GetReviveHP`)."""
    e = BaseEffect(name="RitesOfMorkai", effect_type=RITES_OF_MORKAI_EFFECT,
                   active_ability_level=level, ability_level=level,
                   ability_variables_multiplier=mult, source=uid, target=uid)
    st.effects.by_unit.setdefault(int(uid), []).append(e)
    return e


def _kill(st, uid, killer, overkill=False):
    """`On(1)` PUIS la GARDE @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e (`kill_unit_revive_gate`) qui draine la `ReviveData` posee par
    la feuille `Revive` -- mirror de `IdunBattle.Operations.KillUnitOperation$$Execute` (case-89 volet C)."""
    st.get_entity(uid).get_component(HealthComponent).hp = 0
    st.get_entity(uid).get_component(UnitComponent).alive = False
    out = after_death_triggers(st, dying_id=uid, killer_id=killer, overkill=overkill)
    kill_unit_revive_gate(st, uid)
    return out


def test_self_revive_in_place(rom_env):
    """L'unite INSPIREE qui meurt (sans overkill) est revive EN PLACE a min(reviveHP, maxPV)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    _inspire(st, uid)
    pc = st.get_entity(uid).get_component(PositionComponent)
    pos0 = (pc.col, pc.row)
    maxhp = int(st.get_entity(uid).get_component(HealthComponent).hp_max)
    # `GetReviveHP` lit l'abilityState PORTE PAR L'EFFET (niveau/mult du POSEUR), pas ceux du porteur.
    rhp = ability_var("RitesOfMorkai", "hp", POSER_LEVEL, multiplier_pct=POSER_MULT)
    res = _kill(st, uid, other)
    assert st.get_entity(uid).get_component(UnitComponent).alive, \
        "unite inspiree NON revive: %s" % res
    hp = int(st.get_entity(uid).get_component(HealthComponent).hp)
    assert hp > 0 and hp <= maxhp, "hp revive invalide: %d (maxPV=%d)" % (hp, maxhp)
    if rhp is not None:
        assert hp == min(int(rhp), maxhp), "hp %d != min(reviveHP=%s, maxPV=%d)" % (hp, rhp, maxhp)
    assert (pc.col, pc.row) == pos0, "position CHANGEE (revive doit etre EN PLACE)"
    assert any(r.get("ability") == "RitesOfMorkai" for r in res), "trigger absent: %s" % res


def test_one_shot_definitive(rom_env):
    """`removeEffect`(0x488)=TRUE -> RemoveEffect : le revive est one-shot DEFINITIF. Une 2e mort ne
    revive plus, MEME apres `reset_revive_gates` (qui ne rearme QUE le once-per-turn de Narthecium)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    _inspire(st, uid)
    _kill(st, uid, other)
    assert st.get_entity(uid).get_component(UnitComponent).alive, "revive #1 attendu"
    assert all(e.consumed for e in st.effects.by_unit[int(uid)]
               if e.effect_type == RITES_OF_MORKAI_EFFECT), "effet 1502 non RETIRE apres le revive"
    reset_revive_gates(st)                       # turn-start : ne doit PAS rearmer un RemoveEffect
    _kill(st, uid, other)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "2e revive apres reset (one-shot DEFINITIF non respecte)"


def test_unless_overkilled(rom_env):
    """`get_ReviveOnOverkill` herite de la base = 0 -> mort en OVERKILL : PAS de revive (i2 « unless
    Overkilled »)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    _inspire(st, uid)
    _kill(st, uid, other, overkill=True)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "revive malgre l'overkill (RitesOfMorkai = unless Overkilled)"
    assert all(not e.consumed for e in st.effects.by_unit[int(uid)]
               if e.effect_type == RITES_OF_MORKAI_EFFECT), \
        "effet consomme alors que le trigger n'a pas matche"


def test_owner_is_target_only(rom_env):
    """`get_OwnerIsTarget` : l'effet ne revive QUE son porteur -- la mort d'une AUTRE unite (meme
    adjacente, meme alliee) ne le declenche pas (contraste Narthecium, qui revive un ALLIE)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    if other is None:
        pytest.skip("pas de 2e unite alliee")
    _inspire(st, uid)                             # l'effet est sur `uid`, on tue `other`
    _kill(st, other, uid)
    assert not st.get_entity(other).get_component(UnitComponent).alive, \
        "une AUTRE unite a ete revive (OwnerIsTarget non respecte)"
    assert st.get_entity(uid).get_component(UnitComponent).alive, "le porteur ne devait pas mourir"


def test_no_effect_no_revive(rom_env):
    """Sans l'effet 1502 pose, aucune revive (garde anti-faux-positif du rail EFFECT_TRIGGERS)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    _kill(st, uid, other)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "revive sans effet RitesOfMorkai pose"


# --- Gate `EffectComponent.IsActive @+0x5c` (residu #229) ------------------------------------------
# `EvaluateEffectTriggerTargets` relit le flag PAR CIBLE, sur l'`EffectComponent` recharge depuis
# l'entite-effet, AVANT `ShouldTrigger` : une instance INACTIVE n'est meme pas evaluee. Le rail
# oppose (`EvaluateEffectTriggerEffectAbilities`, `ArraySet`) n'a AUCUN gate -- 1502 n'y a rien.

def test_inactive_instance_does_not_revive(rom_env):
    """CONTRE-EPREUVE du gate : instance 1502 posee mais `active=False` -> AUCUN revive, et l'effet
    n'est PAS consomme (le natif n'evalue pas le trigger, donc n'execute pas non plus le
    `RemoveEffect` du 2e volet du behaviour). Ce test ECHOUE sur le port d'avant le gate."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    e = _inspire(st, uid)
    e.active = False                       # ce que seede `decisionView { includeInactive: true }`
    res = _kill(st, uid, other)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "revive par une instance 1502 INACTIVE (gate IsActive @+0x5c absent)"
    assert not e.consumed, "effet 1502 consomme alors que le trigger n'a PAS ete evalue"
    assert not any(r.get("ability") == "RitesOfMorkai" for r in res), \
        "trigger 1502 execute malgre l'instance inactive: %s" % res


def test_reactivated_instance_revives(rom_env):
    """Face POSITIVE du meme gate : le flag remis a True (ce que fait `RefreshEffectsOperation$$
    ActivateEffect`, `+0x5c = 1`) rend le trigger evaluable -> revive normal. Prouve que le gate lit
    bien le FLAG et pas autre chose (l'etat est par ailleurs identique au test negatif)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    e = _inspire(st, uid)
    e.active = False
    e.active = True                        # re-activation avant la mort
    res = _kill(st, uid, other)
    assert st.get_entity(uid).get_component(UnitComponent).alive, \
        "instance re-activee non revive: %s" % res
    assert e.consumed, "effet 1502 non retire apres un revive reussi"


def test_gate_is_per_instance(rom_env):
    """Le flag est PORTE PAR L'INSTANCE (`EffectComponent`), pas par le type ni par l'unite : deux
    unites inspirees, l'une avec une instance active, l'autre inerte -> seule la 1re est revive."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    if other is None:
        pytest.skip("pas de 2e unite alliee")
    e_live = _inspire(st, uid)             # instance ACTIVE
    e_dead = _inspire(st, other)           # instance INERTE
    e_dead.active = False
    third = next((u for u in st.entities if u not in (uid, other)), None)
    if third is None:
        pytest.skip("pas de 3e unite pour porter le coup")
    _kill(st, uid, third)
    _kill(st, other, third)
    assert st.get_entity(uid).get_component(UnitComponent).alive, "porteur ACTIF non revive"
    assert e_live.consumed, "instance active non consommee par son revive"
    assert not st.get_entity(other).get_component(UnitComponent).alive, \
        "porteur INERTE revive (le gate a fuite d'une instance a l'autre)"
    assert not e_dead.consumed, "instance inerte consommee"


def test_inactive_instance_does_not_revive_alt_board(rom_alt_env):
    """GENERALISATION : meme verdict sur un AUTRE roster (autre faction, autres traits/PV) et un
    AUTRE board -- le gate ne depend d'aucune particularite de l'etat de `rom_env`."""
    st = _fresh(rom_alt_env)
    uid, other = _first_player_unit(st)
    e = _inspire(st, uid)
    e.active = False
    _kill(st, uid, other)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "revive par une instance 1502 INACTIVE (autre roster/board)"
    assert not e.consumed, "effet 1502 consomme alors que le trigger n'a PAS ete evalue"
    # controle positif dans le MEME etat : l'instance active revive bien.
    st2 = _fresh(rom_alt_env)
    uid2, other2 = _first_player_unit(st2)
    _inspire(st2, uid2)
    _kill(st2, uid2, other2)
    assert st2.get_entity(uid2).get_component(UnitComponent).alive, \
        "instance ACTIVE non revive sur l'autre roster/board (controle positif)"


# --- Rail NATIF : Baldr spawne, RitesOfMorkai caste, 1502 pose PAR LE JEU --------------------
# Le porteur entre au pool par `catalog_inject.write_augmented_seed_bc` (Units + Abilities). Ces
# gardes ne dependent plus d'aucune injection dans `state.effects` : l'instance 1502 vient de la
# cascade native et transite par `readEffectsByUnit` -> `decisionView` -> `EffectFactory.create`.

NATIVE_P_UNITS = "spaceWolfPriest,astraCreed,eldarFarseer"   # allies NON-MECANIQUES (HealType=0)
NATIVE_A_UNITS = "orksNob,orksWarboss"
# `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` : pct = (dmg - hpAvant)/hpAvant*100
# compare a `overkillDmgPctOfHealth` (=100) -> il faut `dmg < 2*hpAvant` au coup letal. 3 hits a
# ~1000 depuis 3000 PV donnent 3000 -> 2096 -> 962 -> 0, pct ~5 % : mort NORMALE, pas overkill.
NATIVE_HP_PLAYER = 3000
NATIVE_DMG_TARGET = 1000


@pytest.fixture(scope="module")
def rom_native_env(live_session, rpc, build_runner, tmp_path_factory):
    """Bataille ou `RitesOfMorkai` est REELLEMENT caste par `spaceWolfPriest`.

    Ecrit le seed BC augmente HORS de `data/` (c'est une SORTIE), construit, rapproche les
    adverses de la victime, puis caste. Rend l'etat capture APRES le cast."""
    import catalog_inject as CI
    from engine.runner.components import OwnerComponent            # noqa: F401  (lisibilite)

    out = tmp_path_factory.mktemp("swp") / "seed_bc_swp.json"
    CI.write_augmented_seed_bc(out, ["spaceWolfPriest"])
    extra = ["--seed-bc", str(out), "--p-units", NATIVE_P_UNITS, "--a-units", NATIVE_A_UNITS,
             "--hp-player", str(NATIVE_HP_PLAYER), "--dmg-target", str(NATIVE_DMG_TARGET),
             "--board", "MC1_67", "--no-ai"]
    rid = build_runner("777", extra=extra)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo (natif)")
    board = Board(bg["tiles"], adjacency="evenq")

    def dv_of(inc=False):
        return rpc("decisionView", {"runnerId": rid, "maxRank": 2, "allAbilities": True,
                                    "includeInactive": inc}, 180)

    def act(a):
        return rpc("applyAction", {"runnerId": rid, "action": a}, 120)

    v0 = dv_of()
    if not _ok(v0):
        pytest.skip("decisionView KO (natif)")
    # `ctrl` bascule a chaque endturn : on fige les deux camps AU PREMIER TOUR.
    mine = [u["id"] for u in (v0.get("units") or []) if u.get("ctrl")]
    foes = [u["id"] for u in (v0.get("units") or []) if not u.get("ctrl")]
    if len(mine) < 3 or not foes:
        pytest.skip("roster natif incomplet")
    baldr, victim = mine[0], mine[1]

    def mov_of():
        return rpc("aiMovableTiles", {"runnerId": rid}, 60)

    marched = _march_foes(dv_of, mov_of, act, board, victim, foes)
    if not marched:
        pytest.skip("les adverses n'ont pas atteint la victime")
    for _ in range(3):                                    # rendre la main a mon camp
        if {u["id"]: u for u in (dv_of().get("units") or [])}.get(baldr, {}).get("ctrl"):
            break
        act({"kind": "endturn"})
    r = act({"kind": "ability", "casterId": baldr, "targetId": baldr,
             "abilityType": 1211})                        # ActiveAbilityType.RitesOfMorkai
    if not (isinstance(r, dict) and r.get("ok")):
        pytest.skip("cast RitesOfMorkai KO: %s" % str(r)[:200])
    dv = dv_of()
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live KO (natif)")
    return {"rid": rid, "dv": dv, "dv_inc": dv_of(True), "ob": ob, "snap": snap,
            "board": board, "baldr": baldr, "victim": victim, "foes": foes, "mine": mine,
            "act": act, "dv_of": dv_of}


def _bfs_dist(board, src, dst):
    from collections import deque
    a, b = board.id_at(*src), board.id_at(*dst)
    if a is None or b is None:
        return 10 ** 6
    seen, q = {a: 0}, deque([a])
    while q:
        t = q.popleft()
        if t == b:
            return seen[t]
        for n in board.neighbours(t):
            if n not in seen:
                seen[n] = seen[t] + 1
                q.append(n)
    return 10 ** 6


def _march_foes(dv_of, mov_of, act, board, victim, foes, max_rounds=10):
    """Rapproche les adverses de `victim` jusqu'a l'adjacence (mes unites restent groupees : la
    pose de 1502 est en zone range 1 autour de Baldr). Le set de destinations legales vient
    d'`aiMovableTiles` -- on ne devine JAMAIS un move (cf. runner.md §4)."""
    for _ in range(max_rounds):
        ub = {u["id"]: u for u in (dv_of().get("units") or [])}
        vp = ub[victim]["pos"]
        vpos = (vp["col"], vp["row"])
        d = [_bfs_dist(board, (ub[f]["pos"]["col"], ub[f]["pos"]["row"]), vpos)
             for f in foes if ub.get(f, {}).get("alive")]
        if d and min(d) <= 1:
            return True
        for mu in ((mov_of() or {}).get("units") or []):
            uid = mu.get("unitId")
            if uid not in foes:
                continue                                  # on ne bouge QUE l'adversaire
            tiles = [(t["col"], t["row"]) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None]
            if not tiles:
                continue
            best = min(tiles, key=lambda t: _bfs_dist(board, t, vpos))
            act({"kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}})
        act({"kind": "endturn"})
    return False


def test_native_1502_is_published_by_the_unit_channel(rom_native_env):
    """Q1 (residu #235 « rayon de souffle NON MESURE ») : apres le cast NATIF, `readEffectsByUnit`
    publie-t-il l'effectType 1502 ? Mesure, jamais heritee de la table #229 §3 -- celle-ci a deja
    ete REFUTEE live pour 1077 (`case-231-haze-transfer-active-gate.md`)."""
    for label, view in (("defaut", rom_native_env["dv"]), ("includeInactive",
                                                           rom_native_env["dv_inc"])):
        hits = [(u.get("id"), e) for u in (view.get("units") or [])
                for e in (u.get("effects") or [])
                if e.get("effectType") == RITES_OF_MORKAI_EFFECT]
        assert len(hits) == 3, \
            "canal %s : %d instance(s) 1502 publiee(s), 3 attendues (Baldr + 2 allies)" % (
                label, len(hits))
        assert all(e.get("active") for _u, e in hits), \
            "canal %s : une instance 1502 publiee INACTIVE: %s" % (label, hits)
        assert not any(e.get("removed") for _u, e in hits), \
            "canal %s : une instance 1502 publiee RETIREE" % label


def test_native_1502_is_seeded_by_load_state(rom_native_env):
    """Le canal ne suffit pas : `EffectFactory.create` doit MATERIALISER les 3 instances (sinon le
    gate porte n'a aucune prise sur l'etat que le moteur reconstruit)."""
    st = load_state(rom_native_env["dv"], rom_native_env["ob"], rom_native_env["snap"],
                    board=rom_native_env["board"])
    seeded = [(uid, e) for uid, lst in (st.effects.by_unit or {}).items()
              for e in lst if e.effect_type == RITES_OF_MORKAI_EFFECT]
    assert len(seeded) == 3, "load_state a seede %d instance(s) 1502, 3 attendues" % len(seeded)
    assert all(e.active for _u, e in seeded), "instance 1502 seedee INACTIVE"
    assert {uid for uid, _e in seeded} == set(rom_native_env["mine"]), \
        "les 3 instances ne sont pas sur les 3 allies: %s" % [uid for uid, _e in seeded]


def test_native_gate_discriminates_on_natively_posed_instance(rom_native_env):
    """Q2 : le gate `EffectComponent.IsActive @+0x5c` discrimine sur une instance posee PAR LE JEU
    (plus aucune injection). Matrice complete -- actif -> revive, inerte -> rien, re-arme -> revive,
    overkill -> rien (3e discriminant, independant du flag)."""
    env, victim, killer = rom_native_env, rom_native_env["victim"], rom_native_env["foes"][0]

    def run(mutate=None, overkill=False):
        st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"])
        st.rng = IntBasedMersenneTwister(777)
        insts = [e for e in (st.effects.by_unit.get(int(victim)) or [])
                 if e.effect_type == RITES_OF_MORKAI_EFFECT]
        assert insts, "aucune instance 1502 sur la victime u%d" % victim
        for e in insts:
            if mutate:
                mutate(e)
        res = _kill(st, victim, killer, overkill=overkill)
        uc = st.get_entity(victim).get_component(UnitComponent)
        hc = st.get_entity(victim).get_component(HealthComponent)
        return bool(uc.alive), int(hc.hp or 0), [e.consumed for e in insts], res

    alive, hp, consumed, res = run()
    assert alive and consumed == [True], "instance ACTIVE non revive: %s" % res
    assert hp == int(_maxhp(env, victim)), \
        "hp revive %d != min(reviveHP, maxPV)=%d" % (hp, _maxhp(env, victim))

    alive, _hp, consumed, res = run(mutate=lambda e: setattr(e, "active", False))
    assert not alive, "revive par une instance 1502 INACTIVE (gate IsActive absent): %s" % res
    assert consumed == [False], "effet consomme alors que le trigger n'a PAS ete evalue"

    alive, _hp, consumed, _res = run(mutate=lambda e: setattr(e, "active", True))
    assert alive and consumed == [True], "instance re-armee non revive"

    alive, _hp, consumed, _res = run(overkill=True)
    assert not alive and consumed == [False], "revive malgre l'overkill (unless Overkilled)"


def _maxhp(env, uid):
    """`StatAmount(target, Health, max)` -- la borne haute du `Min` du behaviour de revive."""
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"])
    return int(st.get_entity(uid).get_component(HealthComponent).hp_max)


def test_native_revive_agrees_with_the_port(rom_native_env):
    """AGREMENT natif <-> port : on TUE la victime inspiree EN LIVE (mort NORMALE, cf. calibrage
    `NATIVE_HP_PLAYER`/`NATIVE_DMG_TARGET`) et on exige que le jeu la ressuscite au MEME nombre de
    PV que le port. La cascade native passe par `RemoveEffect` (2e volet, `removeEffect`=1) puis le
    revive -- donc l'instance 1502 disparait du canal apres coup."""
    env, victim = rom_native_env, rom_native_env["victim"]
    expected = _maxhp(env, victim)              # Min(GetReviveHP, StatAmount(Health,max)) sature
    env["act"]({"kind": "endturn"})               # la main a l'adversaire
    trace, death_hp, revive_hp = [], None, None
    for _round in range(4):                       # 1 attaque par unite et par tour
        for fid in env["foes"]:
            v = env["dv_of"]()
            aid = next((ev.get("abilityId")
                        for p in (v.get("attackPlans") or []) if p.get("unitId") == fid
                        for ev in (p.get("evals") or []) if ev.get("targetId") == victim), None)
            if aid is None:
                trace.append("u%d: pas de plan sur u%d" % (fid, victim))
                continue
            r = env["act"]({"kind": "ability", "casterId": fid, "targetId": victim,
                            "abilityType": aid})
            # ⚠ Le revive est INSTANTANE dans la MEME cascade : hp_max -> 0 -> hp_max. Un diff
            # d'etat avant/apres ne voit donc RIEN (3000 -> 3000). Seuls les EVENEMENTS temoignent.
            death_hp, revive_hp = _scan_death_and_revive(r, victim)
            trace.append("u%d abil=%s : death_hp=%s revive_hp=%s" % (fid, aid, death_hp, revive_hp))
            if revive_hp is not None:
                break
        if revive_hp is not None:
            break
        env["act"]({"kind": "endturn"})           # mon tour (personne ne joue)
        env["act"]({"kind": "endturn"})           # de nouveau a l'adversaire
    assert death_hp == 0, "la victime inspiree n'est jamais morte en live: %s" % trace
    assert revive_hp is not None, \
        "morte mais PAS revive par le NATIF (le port, lui, revive): %s" % trace
    assert revive_hp == expected, \
        "revive natif a %d PV, port attend %d (Min(GetReviveHP, StatAmount(Health,max)))" % (
            revive_hp, expected)
    after = {x["id"]: x for x in (env["dv_of"](True).get("units") or [])}.get(victim) or {}
    assert after.get("alive") and int(after.get("hp")) == expected, \
        "etat post-revive incoherent: alive=%s hp=%s" % (after.get("alive"), after.get("hp"))
    assert not [e for e in (after.get("effects") or [])
                if e.get("effectType") == RITES_OF_MORKAI_EFFECT], \
        "l'instance 1502 survit au revive (removeEffect=1 -> RemoveEffect attendu)"


def _scan_death_and_revive(apply_result, victim):
    """Extrait de la cascade d'`applyAction` (a) les PV du coup LETAL et (b) les PV du REVIVE.

    Motif natif mesure (cf. `docs/rl/case-229-1502-rites-of-morkai-live-confrontation.md` §4.2) :
      ... UnitStats_RemainingHealth: 0, UnitStats_NumberOfMembers: 0    <- la mort
      [Group «RitesOfMorkai»] -> Effect_Id=<eid>                        <- le RemoveEffect
      ... UnitStats_Transformed: 1, UnitStats_RemainingHealth: <hp>     <- le REVIVE
    """
    import json as _json
    death_hp = revive_hp = None
    for act in ((apply_result or {}).get("actions") or []):
        for ev in (act.get("events") or []):
            if ev.get("entity") != victim or ev.get("kind") != "action":
                continue
            try:
                tags = _json.loads(ev.get("tags") or "{}")
            except Exception:
                continue
            hp = tags.get("UnitStats_RemainingHealth")
            if hp is None:
                continue
            if tags.get("UnitStats_Transformed") == 1:
                revive_hp = int(hp)
            elif int(hp) == 0 and tags.get("UnitStats_NumberOfMembers") == 0:
                death_hp = 0
    return death_hp, revive_hp
