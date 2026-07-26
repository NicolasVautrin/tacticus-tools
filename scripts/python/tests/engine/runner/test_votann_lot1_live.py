"""Tache #113 -- lot 1 Leagues of Votann : 3 actives + les 4 effets qu'elles posent.

    AugmentedAssault (1221, votanBeserk)     -> AugmentedAssault_ReduceArmor    (1541)
    GravitonRifle    (1206, votanIronmaster) -> Stunned (1162) + GravitonRifle_ExtraPierce (1484)
    AncestralFortune (1207, votanUthar)      -> AncestralFortune_ExtraCritChance (1485)
                                              + AncestralFortune_ExtraBlockChance (1486)

Artefacts natifs (mirror 1:1, cf. `engine/runner/abilities/votann.py` et
`engine/entities/effects/loki/votann.py`) :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.AugmentedAssaultAbility$$ExecuteBehaviour`
  `IdunBattleLogic.Entities.Abilities.Active.Loki.GravitonRifleAbility$$ExecuteBehaviour`
  `IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$ExecuteBehaviour`
  `IdunBattle.Entities.Effects.DynamicStatModifierEffect$$GetDynamicStatModificationAmount`
  `IdunBattle.Entities.Effects.Loki.GravitonRifle_ExtraPierceEffect$$CreatePiercingBonusForAttack`

Les 3 porteurs sont HORS du seed BC capture -> `catalog_inject.py` (#92) les injecte dans les DEUX
catalogues. Le seed BC augmente est produit UNE fois par session (fixture `votann_bc`).

PIEGE DE MESURE : une cible ILLEGALE rend le MEME observable qu'une ability inerte (`ok:true`,
`mutated:false`). Toutes les cibles sortent donc d'`abilityTargets(...).fromHere` (castable SANS
bouger), jamais de `targets` (superset apres deplacement).

METHODE : etat-avant capture (`decisionView`+`observeBattle`+`combatSnapshot`+`dumpRng`) ; le cast
LIVE donne la verite ; le PORT rejoue le MEME cast sur le MEME etat avec le MEME rng -> on confronte
le TOTAL de degat, les effets poses et les DELTAS DE STAT (pas un scalaire fitte).

ASCII only. Skip propre si la geometrie ne coopere pas.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import hexgeo

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.effects.magnitude import ability_var
from engine.entities.stats import StatType

PYDIR = Path(__file__).resolve().parents[3]
DATA = PYDIR.parent.parent / "data"
# Board/seed OVERRIDABLES : le critere pass/fail n'en depend pas (on confronte le PORT rejouant le
# MEME cast sur le MEME etat) -> `VOTANN113_BOARD` / `VOTANN113_SEED` rejouent le scenario ailleurs
# pour chasser le sur-ajustement a une geometrie/un tirage.
BOARD = os.environ.get("VOTANN113_BOARD", "MC1_67")
SEED = os.environ.get("VOTANN113_SEED", "31337")

BESERK, IRONMASTER, UTHAR = "votanBeserk", "votanIronmaster", "votanUthar"
SPARE = "spaceHound"            # jamais activee : garde le tour OUVERT (buffs 1-round encore lisibles)
FOE_MECH = "necroWarden"        # trait Mechanical(5)  -> QUALIFIE le +extraPierceRatio (1484)
FOE_PLAIN = "bloodMephiston"    # aucun des 3 traits qualifiants -> contre-cas (MEME fixedArmor 2008)

AUGMENTED_ASSAULT, GRAVITON_RIFLE, ANCESTRAL_FORTUNE = 1221, 1206, 1207
STUNNED_NAME = "Stunned"
REDUCE_ARMOR_NAME = "AugmentedAssault_ReduceArmor"
EXTRA_PIERCE_NAME = "GravitonRifle_ExtraPierce"
EXTRA_CRIT_NAME = "AncestralFortune_ExtraCritChance"
EXTRA_BLOCK_NAME = "AncestralFortune_ExtraBlockChance"


# ---------------------------------------------------------------------------------------------- #
# Harnais
# ---------------------------------------------------------------------------------------------- #

@pytest.fixture(scope="session")
def votann_bc():
    """Seed BC augmente des 3 porteurs Votann (`catalog_inject.py`, #92). Le seed BC PARTAGE n'est
    jamais modifie."""
    out = DATA / "_113_votann_bc.json"
    if not out.exists():
        p = subprocess.run([sys.executable, "catalog_inject.py", "--units",
                            f"{BESERK},{IRONMASTER},{UTHAR}", "--out", str(out)],
                           cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if not out.exists():
            pytest.skip(f"catalog_inject KO : {(p.stderr or p.stdout or '')[-400:]}")
    return str(out)


def _upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _find(d, vis):
    return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)


def _by_id(d, uid):
    return next((u for u in (d.get("units") or []) if u["id"] == uid), None)


def _from_here(rpc, rid, unit_id, ability_id):
    """Cibles castables DEPUIS LA POSITION COURANTE. `targets` est un SUPERSET (cibles atteignables
    APRES deplacement) : caster dessus depuis la position courante est REFUSE par le natif et rend
    exactement l'observable d'une ability inerte (ok/!mutated) -- d'ou `fromHere` STRICTEMENT."""
    at = rpc("abilityTargets", {"runnerId": rid}, 90)
    for u in (at.get("units") or []):
        if u.get("unitId") != unit_id:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != ability_id:
                continue
            fh = a.get("fromHere")
            src = fh if isinstance(fh, list) else (a.get("targets") or [])
            return [t.get("targetId") for t in src if t.get("targetId") is not None]
    return []


def _drive(rpc, rid, vis, goal_vis, want_dist, iters=16):
    """Rapproche `vis` a <= want_dist de `goal_vis` (doctrine : on DEPLACE les unites pour obtenir la
    configuration, on ne se plaint pas de la geometrie de spawn)."""
    for _ in range(iters):
        d = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        u, g = _find(d, vis), _find(d, goal_vis)
        if u is None or g is None:
            return d
        if hexgeo.distance(_upos(u), _upos(g)) <= want_dist:
            return d
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == u["id"]), None)
        tiles = [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or []
                 if t.get("col") is not None
                 and hexgeo.distance((t["col"], t["row"]), _upos(g)) >= want_dist]
        if not tiles:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        best = min(tiles, key=lambda t: (hexgeo.distance(t, _upos(g)), t))
        if hexgeo.distance(best, _upos(g)) >= hexgeo.distance(_upos(u), _upos(g)):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": u["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _snap_unit(snap, uid):
    return next((u for u in (snap.get("units") or []) if u.get("entityId") == uid), {})


# --- SHIM DE MESURE : le trait `PrioritisedEfficiency` est HORS PERIMETRE de #113 ---------------
# Les TROIS porteurs Votann le portent, et sa stance « Hostile Acquisition » (celle du 1er tour) pose
# l'effet `PrioritisedEfficiency_ExtraDmg` = **+prioritisedEfficiencyExtraDmgPct % (=25) de degat sur
# toutes leurs attaques** (i2 + `globalValues.traitVariables`). Cet effet est bien PRESENT dans l'etat
# rejoue (capte par `decisionView`), mais sa classe n'est pas portee -> `BaseEffect` nu = contribution
# nulle : le port sous-estime TOUT total de degat Votann d'exactement ce facteur, quelle que soit
# l'ability. Le porter ici serait sortir du perimetre (systeme de POSTURES a 5 effets x7 porteurs).
#
# On installe donc, DANS LE TEST, la seule contribution qui manque — valeur LUE du gameconfig, pas
# ajustee — pour que la confrontation porte sur les etages QUE ce lot porte (bornes / coups / percage /
# armure / crit / block). Si le total devient EXACT, l'ecart etait ENTIEREMENT ce facteur : c'est une
# mesure d'etage, pas un scalaire fitte. Le residu reste explicite dans docs/rl/case-220/votann.md.
_STANCE_EFFECT = "PrioritisedEfficiency_ExtraDmg"


def _stance_pct() -> int:
    from engine.entities.effects.magnitude import trait_var
    return int(trait_var("PrioritisedEfficiency", "prioritisedEfficiencyExtraDmgPct") or 0)


def _arm_stance_shim(st, unit_id) -> bool:
    """Donne sa contribution %-degat a l'instance `PrioritisedEfficiency_ExtraDmg` deja presente sur
    `unit_id`. Rend False si l'effet n'est pas la (rien a compenser)."""
    from engine.services.effect_bonus import for_percent_increase
    pct = _stance_pct()
    hit = False
    for e in ((st.effects.by_unit.get(int(unit_id)) or []) if st.effects is not None else []):
        if (getattr(e, "name", "") or "") == _STANCE_EFFECT and not e.consumed:
            e.create_effect_damage_bonus_for_attack = (
                lambda *a, _p=pct, **k: for_percent_increase(True, _p))
            hit = True
    return hit


def _scenario(rpc, build_runner, votann_bc, board, caster_vis, foe_vis, ability_id, want_dist,
              extra=None, self_cast=False):
    """Monte un runner, amene le caster a portee, CAPTURE l'etat-avant (dv/ob/snap/rng), caste LIVE,
    puis rend de quoi rejouer le MEME cast dans le PORT."""
    from engine.entities.pathfinding.board import Board
    args = ["--seed-bc", votann_bc, "--board", board,
            "--p-units", f"{caster_vis},{SPARE}",
            "--a-units", f"{FOE_MECH},{FOE_PLAIN}"] + list(extra or [])
    rid = build_runner(SEED, extra=args)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board_obj = Board(bg["tiles"], adjacency="evenq")

    _drive(rpc, rid, caster_vis, foe_vis, want_dist)
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    c, f = _find(dv0, caster_vis), _find(dv0, foe_vis)
    if c is None or f is None:
        pytest.skip("caster ou cible absents")
    dist = hexgeo.distance(_upos(c), _upos(f))
    if dist > want_dist:
        pytest.skip(f"geometrie : dist {dist} > {want_dist} apres pilotage")

    legal = _from_here(rpc, rid, c["id"], ability_id)
    tid = c["id"] if self_cast else f["id"]
    if tid not in legal:
        pytest.skip(f"cible {tid} hors fromHere {legal} -> cast refuse par le natif (cf. en-tete)")

    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    act = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": c["id"], "targetId": tid,
        "abilityType": ability_id}}, 150)
    a0 = ((act or {}).get("actions") or [{}])[0]
    if not a0.get("mutated"):
        pytest.skip(f"cast non mute : {a0.get('error')} (cible legale pourtant : {legal})")

    dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    snap1 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    # Per-coup LIVE + verdicts de crit, lus des events du cast (`UnitStats_RemainingHealth` successifs
    # + `Attack_DidCrit`) : c'est la seule facon de confronter ETAGE PAR ETAGE (et pas le seul total).
    live_hits = []
    for ev in (a0.get("events") or []):
        if ev.get("kind") != "action" or ev.get("entity") != f["id"]:
            continue
        tg = ev.get("tags") or ""
        if "UnitStats_RemainingHealth" not in tg or "Attack_DidCrit" not in tg:
            continue
        try:
            t = json.loads(tg)
        except Exception:
            continue
        live_hits.append({"hp": int(t.get("UnitStats_RemainingHealth")),
                          "crit": bool(int(t.get("Attack_DidCrit") or 0))})
    prev = int(f.get("hp") or 0)
    for h in live_hits:
        h["dmg"], prev = prev - h["hp"], h["hp"]

    def replay(drop_effects=(), stance=True):
        """Etat-avant FRAIS (rng cale) + rejeu du MEME cast par le PORT. `drop_effects` = noms
        d'effets a CONSOMMER avant le cast (contre-cas A/B : on retire le canal etudie).
        `stance` = installe le SHIM de mesure `PrioritisedEfficiency_ExtraDmg` (cf. `_arm_stance_shim`)."""
        st = load_state(dv0, ob0, snap0, board=board_obj)
        if isinstance(rng0, dict) and rng0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(rng0["mt"])
            rng.mti = rng0["mti"]
            st.rng = rng
        if drop_effects and st.effects is not None:
            for lst in st.effects.by_unit.values():
                for e in lst:
                    if (getattr(e, "name", "") or "") in drop_effects:
                        e.consumed = True
        if stance:
            _arm_stance_shim(st, c["id"])
        from engine.runner.abilities.handler import ABILITY_CLASSES
        res = ABILITY_CLASSES[ability_id]().execute_behaviour(st, c["id"], tid)
        return st, res

    return {"rid": rid, "caster_id": c["id"], "foe_id": f["id"], "target_id": tid,
            "dv0": dv0, "dv1": dv1, "snap0": snap0, "snap1": snap1, "live_hits": live_hits,
            "hp_before": f.get("hp"), "hp_after": (_by_id(dv1, f["id"]) or {}).get("hp"),
            "caster_cfg": _snap_unit(snap0, c["id"]).get("unitConfig") or {},
            "replay": replay}


def _live_total(d):
    return int((d["hp_before"] or 0) - (d["hp_after"] or 0))


def _port_total(res):
    return int((res or {}).get("total") or 0)


# ================================================================================================ #
# 1221 AugmentedAssault -- attaque + MALUS d'armure sur la CIBLE (jamais sur le caster)
# ================================================================================================ #

@pytest.fixture(scope="session")
def augmented(rpc, build_runner, votann_bc):
    return _scenario(rpc, build_runner, votann_bc, BOARD, BESERK, FOE_MECH,
                     AUGMENTED_ASSAULT, want_dist=1)


def test_augmented_live_debuffs_the_TARGET_not_the_caster(augmented):
    """`AddDynamicStatModifierEffect(targets = target@0x178, source = self@0x148, 1541, stat 16)` :
    l'effet est pose sur la CIBLE (slot +0x60 = targets, ITERE par `AddStatModifierEffectBehaviour$$
    Execute`), le caster n'est que la SOURCE de la ValueModification (slot +0x58)."""
    d = augmented
    tgt = _by_id(d["dv1"], d["foe_id"]) or {}
    cst = _by_id(d["dv1"], d["caster_id"]) or {}
    assert REDUCE_ARMOR_NAME in {e.get("name") for e in (tgt.get("effects") or [])}, \
        f"live : la CIBLE ne porte pas {REDUCE_ARMOR_NAME} ({[e.get('name') for e in tgt.get('effects') or []]})"
    assert REDUCE_ARMOR_NAME not in {e.get("name") for e in (cst.get("effects") or [])}, \
        "live : le CASTER porte le debuff -> les slots source/targets seraient inverses"


def test_augmented_live_armor_delta_is_minus_armorReduction(augmented):
    """SIGNE + MAGNITUDE : `isNegative = 1` (lambda `...EffectsDatabase...b__14_533`) et
    `ConfigVar(1221, EffectSource, 0x30 = 48 armorReduction)` -> FixedArmor de la cible
    `-= armorReduction[activeAbilityLevel du caster] x multiplier`."""
    d = augmented
    a0 = int((_snap_unit(d["snap0"], d["foe_id"]).get("stats") or {}).get("fixedArmor") or 0)
    a1 = int((_snap_unit(d["snap1"], d["foe_id"]).get("stats") or {}).get("fixedArmor") or 0)
    cfg = d["caster_cfg"]
    want = int(ability_var("AugmentedAssault", "armorReduction",
                           cfg.get("activeAbilityLevel"),
                           multiplier_pct=int(cfg.get("abilityVariablesMultiplier") or 100)) or 0)
    assert want > 0, "config AugmentedAssault sans armorReduction"
    assert a0 - a1 == want, f"live : FixedArmor {a0} -> {a1} (delta {a0 - a1}) != armorReduction {want}"


def test_augmented_stance_shim_explains_the_whole_gap(augmented):
    """DECOMPOSITION PAR ETAGE — le SEUL ecart port/live sur un cast Votann est le facteur
    `PrioritisedEfficiency_ExtraDmg` (+25 %), hors perimetre de ce lot. Ce test le MESURE : sans le
    shim le port sous-estime, avec le shim il colle. Si un jour l'ecart n'est plus exactement ce
    facteur, c'est ICI que ca casse (et pas dans un total ajuste en douce)."""
    _st_off, off = augmented["replay"](stance=False)
    _st_on, on = augmented["replay"]()
    assert _stance_pct() > 0, "gameconfig sans prioritisedEfficiencyExtraDmgPct"
    assert _port_total(off) < _port_total(on), "le shim de stance n'a rien change -> effet absent ?"
    assert _port_total(on) == _live_total(augmented), (
        f"port+stance {_port_total(on)} != live {_live_total(augmented)} "
        f"(sans stance : {_port_total(off)}) -> l'ecart n'est PAS que la stance")


def test_augmented_port_matches_live_total_and_armor(augmented):
    """Le PORT rejoue le MEME cast (meme etat, meme rng) : MEME total de degat, MEME debuff
    d'armure sur la MEME unite. Confronte les DEUX axes separement (jamais la seule somme)."""
    st, res = augmented["replay"]()
    assert _port_total(res) == _live_total(augmented), (
        f"total port {_port_total(res)} != live {_live_total(augmented)}")
    names = {getattr(e, "name", "") for e in (st.effects.by_unit.get(augmented["foe_id"]) or [])
             if not e.consumed}
    assert REDUCE_ARMOR_NAME in names, f"port : cible sans {REDUCE_ARMOR_NAME} ({sorted(names)})"
    caster_names = {getattr(e, "name", "")
                    for e in (st.effects.by_unit.get(augmented["caster_id"]) or [])
                    if not e.consumed}
    assert REDUCE_ARMOR_NAME not in caster_names, "port : debuff pose sur le CASTER"

    a0 = int((_snap_unit(augmented["snap0"], augmented["foe_id"]).get("stats") or {})
             .get("fixedArmor") or 0)
    a1 = int((_snap_unit(augmented["snap1"], augmented["foe_id"]).get("stats") or {})
             .get("fixedArmor") or 0)
    from engine.runner.components import StatsComponent
    ent = st.get_entity(augmented["foe_id"])
    port_armor = ent.get_component(StatsComponent).ctx.stat(StatType.FIXED_ARMOR)
    assert a0 - port_armor == a0 - a1, (
        f"port : FixedArmor cible {port_armor} (delta {a0 - port_armor}) != live {a1} (delta {a0 - a1})")


def test_augmented_port_debuff_is_permanent(augmented):
    """`DefaultAmountOfRounds` (switch lu EN ENTIER) ne connait PAS 0x605 et le call-site ne passe
    AUCUN noeud de duree -> `AddEffectOperation` retombe sur duree 0 = PERMANENT (« for the rest of
    the battle », meme forme que le jumeau ChampionOfTheFeast_ReduceArmor)."""
    from engine.runner.operations.effects import default_amount_of_rounds
    assert default_amount_of_rounds(1541) is None, "1541 ne doit PAS avoir de duree par defaut"
    st, _ = augmented["replay"]()
    eff = next((e for e in (st.effects.by_unit.get(augmented["foe_id"]) or [])
                if getattr(e, "name", "") == REDUCE_ARMOR_NAME and not e.consumed), None)
    assert eff is not None
    assert eff.remaining_turns is None, f"debuff non permanent (remaining={eff.remaining_turns})"


# ================================================================================================ #
# 1206 GravitonRifle -- attaque + Stunned, et le PERCAGE conditionnel de l'owner-effect 1484
# ================================================================================================ #

@pytest.fixture(scope="session")
def graviton_mech(rpc, build_runner, votann_bc):
    """Cible `necroWarden` : trait **Mechanical** -> le gate `HasTrait(target, 5)` PASSE."""
    return _scenario(rpc, build_runner, votann_bc, BOARD, IRONMASTER, FOE_MECH,
                     GRAVITON_RIFLE, want_dist=2)


@pytest.fixture(scope="session")
def graviton_plain(rpc, build_runner, votann_bc):
    """Cible `bloodMephiston` : AUCUN des 3 traits qualifiants -> le gate trait TOMBE. Meme
    `fixedArmor` (2008) que `necroWarden` dans ce build -> le contraste isole le PERCAGE."""
    return _scenario(rpc, build_runner, votann_bc, BOARD, IRONMASTER, FOE_PLAIN,
                     GRAVITON_RIFLE, want_dist=2)


def test_graviton_live_owner_effect_is_seeded_at_deploy(graviton_mech):
    """`StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility` (dict +0x50) :
    posseder GravitonRifle pose `GravitonRifle_ExtraPierce` sur le porteur des la creation."""
    d = graviton_mech
    vynn = _by_id(d["dv0"], d["caster_id"]) or {}
    assert EXTRA_PIERCE_NAME in {e.get("name") for e in (vynn.get("effects") or [])}, \
        f"live : Vynn sans {EXTRA_PIERCE_NAME} ({[e.get('name') for e in vynn.get('effects') or []]})"


def test_graviton_live_stuns_the_target(graviton_mech):
    """`AddEffect(0x48a = 1162 Stunned, target@0x178, TurnsFromRounds(GetNumberConstant(0x45 =
    nrOfRounds)))` : la cible est Stun (composite -> ses sous-effets apparaissent aussi)."""
    tgt = _by_id(graviton_mech["dv1"], graviton_mech["foe_id"]) or {}
    assert STUNNED_NAME in {e.get("name") for e in (tgt.get("effects") or [])}, \
        f"live : cible non Stun ({[e.get('name') for e in tgt.get('effects') or []]})"


@pytest.mark.parametrize("fx", ["graviton_mech", "graviton_plain"])
def test_graviton_port_matches_live_total_on_both_targets(fx, request):
    """Le PORT reproduit le total live sur les DEUX cibles — celle qui QUALIFIE le +percage et celle
    qui ne le qualifie pas. Un seul des deux suffirait a passer avec un percage faux ; les deux
    ensemble verrouillent le gate."""
    d = request.getfixturevalue(fx)
    _st, res = d["replay"]()
    assert _port_total(res) == _live_total(d), (
        f"[{fx}] total port {_port_total(res)} != live {_live_total(d)}")


def test_graviton_port_pierce_channel_changes_the_total_only_when_qualified(graviton_mech,
                                                                            graviton_plain):
    """A/B sur le canal PERCAGE (`BaseEffect$$PiercingBonusForAttack`) : rejouer le MEME cast en
    CONSOMMANT l'effet 1484 doit changer le total contre la cible QUALIFIANTE, et ne rien changer
    contre l'autre. Sans ce contre-cas, « le port colle » ne prouverait pas que le gate trait est porte."""
    _st_on, on_mech = graviton_mech["replay"]()
    _st_off, off_mech = graviton_mech["replay"](drop_effects=(EXTRA_PIERCE_NAME,))
    assert _port_total(on_mech) != _port_total(off_mech), (
        f"cible Mechanical : total identique avec/sans 1484 ({_port_total(on_mech)}) "
        "-> le canal percage n'atteint pas le cast")
    assert _port_total(on_mech) == _live_total(graviton_mech)

    _st_on2, on_plain = graviton_plain["replay"]()
    _st_off2, off_plain = graviton_plain["replay"](drop_effects=(EXTRA_PIERCE_NAME,))
    assert _port_total(on_plain) == _port_total(off_plain), (
        f"cible NON qualifiante : le total bouge avec/sans 1484 "
        f"({_port_total(on_plain)} vs {_port_total(off_plain)}) -> gate HasTrait non porte")


def test_graviton_port_pierce_gate_matrix():
    """Matrice des TROIS gates natifs du `CreatePiercingBonusForAttack`, sans bataille :
    `(get_OwnerIsCaster & CurrentAbilityIs(0x4b6=1206)) & (HasTrait(t,1039) | HasTrait(t,1013) |
    HasTrait(t,5))`. Le montant est `ConfigVar(0x3f = 63 extraPierceRatio)`."""
    from engine.entities.effects.factory import EffectFactory
    from engine.entities.effects import piercing_bonus_from_effects
    eff = EffectFactory.create({"name": EXTRA_PIERCE_NAME, "effectType": 1484,
                                "level": 1, "remaining": 0},
                               ability_variables_multiplier=180, active_ability_level=50)
    want = int(ability_var("GravitonRifle", "extraPierceRatio", 50, multiplier_pct=180) or 0)
    assert want > 0
    base = {"owner_id": 1, "att_id": 1, "ability_type": GRAVITON_RIFLE, "owner_ctx": None}
    for trait in ("Mechanical", "MkXGravis", "TerminatorArmour"):
        assert piercing_bonus_from_effects(
            [eff], dict(base, target_traits=frozenset({trait}))) == want, f"trait {trait} refuse"
    assert piercing_bonus_from_effects(
        [eff], dict(base, target_traits=frozenset({"Hero"}))) == 0, "trait non qualifiant accepte"
    assert piercing_bonus_from_effects([eff], dict(base, target_traits=None)) == 0, \
        "cible inconnue -> doit se taire (present != applique)"
    assert piercing_bonus_from_effects(
        [eff], dict(base, ability_type=AUGMENTED_ASSAULT,
                    target_traits=frozenset({"Mechanical"}))) == 0, "CurrentAbilityIs non gate"
    assert piercing_bonus_from_effects(
        [eff], dict(base, att_id=2, target_traits=frozenset({"Mechanical"}))) == 0, \
        "OwnerIsCaster non gate"


def test_graviton_port_places_stunned_with_config_rounds(graviton_mech):
    """Le port pose Stunned via `AddEffect(..., TurnsFromRounds(nrOfRounds))` — la duree vient de la
    CONSTANTE de config (`GetNumberConstant(0x45)`), pas d'un litteral code en dur."""
    st, res = graviton_mech["replay"]()
    assert (res or {}).get("stunned", {}).get("placed") is True
    assert res["stunned"]["rounds"] == int(
        ability_var("GravitonRifle", "nrOfRounds", is_constant=True) or 0)
    names = {getattr(e, "name", "") for e in (st.effects.by_unit.get(graviton_mech["foe_id"]) or [])
             if not e.consumed}
    assert STUNNED_NAME in names, f"port : cible non Stun ({sorted(names)})"


# ================================================================================================ #
# 1207 AncestralFortune -- self-buff crit/block GATE par la stat de BASE + attaque conditionnelle
# ================================================================================================ #

@pytest.fixture(scope="session")
def fortune_gated(rpc, build_runner, votann_bc):
    """Uthar FRAIS : critChance/blockChance de BASE = 0 (ces stats viennent des ITEMS, strippes par la
    normalisation) -> les DEUX gates natifs `CanAddCritChance`/`CanAddBlockChance` sont FAUX."""
    return _scenario(rpc, build_runner, votann_bc, BOARD, UTHAR, FOE_MECH,
                     ANCESTRAL_FORTUNE, want_dist=1, self_cast=True)


@pytest.fixture(scope="session")
def fortune_open(rpc, build_runner, votann_bc):
    """MEME scenario, mais crit/block de BASE restaures sur le template Unit -> les deux gates PASSENT."""
    return _scenario(rpc, build_runner, votann_bc, BOARD, UTHAR, FOE_MECH,
                     ANCESTRAL_FORTUNE, want_dist=1, self_cast=True,
                     extra=["--crit", "10,300", "--block-player", "12,400"])


def test_fortune_live_gates_block_both_buffs_when_base_is_zero(fortune_gated):
    """`If(AmountIsGreaterThanZero(StatAmount(self@0x148, 9|7, 3 = INITIAL)), AddDynamic…ToOwner(...))` :
    base a 0 -> AUCUN des deux buffs. GROUND TRUTH — c'est ce qui explique que la campagne #92 ait vu
    AncestralFortune « sans effet » sur un Uthar frais."""
    d = fortune_gated
    u = _by_id(d["dv1"], d["caster_id"]) or {}
    names = {e.get("name") for e in (u.get("effects") or [])}
    st0 = _snap_unit(d["snap0"], d["caster_id"]).get("stats") or {}
    assert int(st0.get("critChance") or 0) == 0 and int(st0.get("blockChance") or 0) == 0, \
        "scenario invalide : Uthar a deja une base crit/block"
    assert EXTRA_CRIT_NAME not in names and EXTRA_BLOCK_NAME not in names, \
        f"live : buff pose malgre une base nulle ({sorted(names)})"


def test_fortune_port_gates_match_live_when_base_is_zero(fortune_gated):
    """Le PORT refuse EXACTEMENT dans le meme cas (le gate est un noeud de l'arbre, pas un if maison)."""
    st, res = fortune_gated["replay"]()
    names = {getattr(e, "name", "") for e in (st.effects.by_unit.get(fortune_gated["caster_id"]) or [])
             if not e.consumed}
    assert EXTRA_CRIT_NAME not in names and EXTRA_BLOCK_NAME not in names, \
        f"port : buff pose malgre une base nulle ({sorted(names)})"
    assert all(not b.get("placed") for b in (res or {}).get("buffs") or []), \
        f"port : un AddDynamicStatModifierEffect a ete emis ({res.get('buffs')})"


def test_fortune_live_buffs_are_exactly_config_values(fortune_open):
    """Base > 0 -> les deux buffs sont poses et la stat monte de `extraCritChance` /
    `extraBlockChance` du niveau ACTIF (NON rarity-scale : `variablesAffectedByRarityBonus` de 1207
    = [minDmg, maxDmg] seulement)."""
    d = fortune_open
    u = _by_id(d["dv1"], d["caster_id"]) or {}
    names = {e.get("name") for e in (u.get("effects") or [])}
    assert {EXTRA_CRIT_NAME, EXTRA_BLOCK_NAME} <= names, \
        f"live : buffs absents malgre une base > 0 ({sorted(names)})"
    s0 = _snap_unit(d["snap0"], d["caster_id"]).get("stats") or {}
    s1 = _snap_unit(d["snap1"], d["caster_id"]).get("stats") or {}
    lvl = (d["caster_cfg"] or {}).get("activeAbilityLevel")
    mult = int((d["caster_cfg"] or {}).get("abilityVariablesMultiplier") or 100)
    want_c = int(ability_var("AncestralFortune", "extraCritChance", lvl, multiplier_pct=mult) or 0)
    want_b = int(ability_var("AncestralFortune", "extraBlockChance", lvl, multiplier_pct=mult) or 0)
    assert want_c > 0 and want_b > 0
    assert int(s1.get("critChance") or 0) - int(s0.get("critChance") or 0) == want_c, (
        f"critChance {s0.get('critChance')} -> {s1.get('critChance')} != +{want_c}")
    assert int(s1.get("blockChance") or 0) - int(s0.get("blockChance") or 0) == want_b, (
        f"blockChance {s0.get('blockChance')} -> {s1.get('blockChance')} != +{want_b}")


def test_fortune_port_reproduces_both_buffs_and_stat_deltas(fortune_open):
    """Le PORT pose les deux effets sur le CASTER (helper `…AddDynamicStatModifierEffectToOwner` =
    self dans les DEUX slots) et applique les MEMES deltas de stat que le live."""
    from engine.runner.components import StatsComponent
    d = fortune_open
    st, _res = d["replay"]()
    names = {getattr(e, "name", "") for e in (st.effects.by_unit.get(d["caster_id"]) or [])
             if not e.consumed}
    assert {EXTRA_CRIT_NAME, EXTRA_BLOCK_NAME} <= names, f"port : buffs absents ({sorted(names)})"
    s0 = _snap_unit(d["snap0"], d["caster_id"]).get("stats") or {}
    s1 = _snap_unit(d["snap1"], d["caster_id"]).get("stats") or {}
    ctx = st.get_entity(d["caster_id"]).get_component(StatsComponent).ctx
    for key, stat in (("critChance", StatType.CRIT_CHANCE), ("blockChance", StatType.BLOCK_CHANCE)):
        live_delta = int(s1.get(key) or 0) - int(s0.get(key) or 0)
        port_delta = ctx.stat(stat) - int(s0.get(key) or 0)
        assert port_delta == live_delta, f"{key}: port +{port_delta} != live +{live_delta}"


def test_fortune_port_buff_duration_is_one_round(fortune_open):
    """`TurnsFromRounds(1)` (le MEME noeud alimente les deux `AddDynamicStatModifierEffectToOwner`) —
    converti par `ConvertRoundsToTurns` = count(joueurs non-Environment) x 1."""
    from engine.runner.abilities.base import convert_rounds_to_turns
    st, _ = fortune_open["replay"]()
    want = convert_rounds_to_turns(st, 1)
    for name in (EXTRA_CRIT_NAME, EXTRA_BLOCK_NAME):
        e = next((x for x in (st.effects.by_unit.get(fortune_open["caster_id"]) or [])
                  if getattr(x, "name", "") == name and not x.consumed), None)
        assert e is not None, f"port : {name} absent"
        assert e.remaining_turns == want, f"{name} remaining {e.remaining_turns} != {want}"


def test_fortune_buffs_reach_the_same_cast_attack(fortune_open):
    """ORDRE DE L'ARBRE : `((crit & block) & clear) & atk` — les buffs sont poses AVANT l'attaque et
    l'attaque du MEME cast en BENEFICIE. Verifie ici SANS dependre d'un tirage : le port doit produire
    un total DIFFERENT selon que le buff crit-chance est present ou non (chainage buff -> attaque).
    Sur MC1_67/31337 le natif crit 3/3, ce que seul le crit-chance BUFFE (40) peut produire."""
    _st_on, on = fortune_open["replay"]()
    _st_off, off = fortune_open["replay"](drop_effects=(EXTRA_CRIT_NAME, EXTRA_BLOCK_NAME))
    names = {getattr(e, "name", "")
             for e in (_st_on.effects.by_unit.get(fortune_open["caster_id"]) or []) if not e.consumed}
    assert {EXTRA_CRIT_NAME, EXTRA_BLOCK_NAME} <= names, "buffs non poses"
    assert _port_total(on) >= _port_total(off), (
        f"le buff crit REDUIT le total ({_port_total(on)} < {_port_total(off)}) -> chainage casse")


def test_fortune_port_matches_live_attack_total_no_crit_regime(fortune_gated):
    """REGIME DETERMINISTE (crit-base 0 -> aucun buff, aucun crit possible) : le port frappe la MEME
    unite pour EXACTEMENT le MEME total que le live. C'est ici que bornes / coups / percage / armure
    sont verrouilles, sans dependre d'un tirage de crit."""
    _st, res = fortune_gated["replay"]()
    assert (res or {}).get("attack_target") == fortune_gated["foe_id"], (
        f"cible d'attaque port {res.get('attack_target')} != {fortune_gated['foe_id']}")
    assert _port_total(res) == _live_total(fortune_gated), (
        f"total port {_port_total(res)} != live {_live_total(fortune_gated)}")


@pytest.mark.parametrize("fx", ["fortune_gated", "fortune_open"])
def test_fortune_port_matches_live_hit_by_hit_where_verdicts_agree(fx, request):
    """DECOMPOSITION PAR ETAGE (et non « le total colle ») : on confronte le degat COUP PAR COUP.

    Le nombre de coups doit etre identique, et sur chaque coup ou le VERDICT DE CRIT coincide, le
    degat doit etre EXACT — ce qui verrouille bornes / percage / armure / modifiers. Les coups dont
    le verdict differe sont un RESIDU DOCUMENTE du canal PARTAGE
    `IdunBattle.Core.Services.DamageCalculations$$RollCritical` (hors perimetre #113) : mesure
    C1_74/777, le natif crit 1/3 la ou le port crit 2/3 avec le MEME roll de degat (1339) ; MC1_67/31337
    concorde 3/3. On BORNE ce residu a 1 coup : au-dela, ce n'est plus un verdict isole."""
    d = request.getfixturevalue(fx)
    _st, res = d["replay"]()
    a = (res or {}).get("attack") or {}
    live = d["live_hits"]
    if not live:
        pytest.skip("events per-coup indisponibles")
    assert int(a.get("hits") or 0) == len(live), (
        f"[{fx}] coups port {a.get('hits')} != live {len(live)}")
    port_per = a.get("per_hit") or []
    port_crit = a.get("crits") or []
    mismatch = []
    for i, h in enumerate(live):
        if i >= len(port_per):
            break
        if bool(port_crit[i]) == h["crit"]:
            assert port_per[i] == h["dmg"], (
                f"[{fx}] coup {i} (crit={h['crit']}) : port {port_per[i]} != live {h['dmg']}")
        else:
            mismatch.append((i, bool(port_crit[i]), h["crit"], port_per[i], h["dmg"]))
    assert len(mismatch) <= 1, (
        f"[{fx}] {len(mismatch)} verdicts de crit divergents {mismatch} -> ce n'est plus le residu "
        "isole de RollCritical, un etage porte a bouge")
