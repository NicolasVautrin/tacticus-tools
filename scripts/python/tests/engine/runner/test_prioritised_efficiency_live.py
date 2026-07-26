"""Tache #121 -- trait `PrioritisedEfficiency` (0x423=1059, LES TROIS Leagues of Votann) : ETAGE,
CONDITIONS et ORIENTATION du +extraDmgPct % de la stance << Hostile Acquisition >>.

Artefacts natifs (mirror 1:1, cf. `engine/entities/effects/loki/extra_damage.py` et
`.../damage_reduction.py`) :
  `IdunBattle.Entities.Effects.Loki.PrioritisedEfficiency_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
      = EffectBonus.ForPercentIncrease( DSLFactory.get_OwnerIsCaster, DSLFactory.ConfigConst(0xf) )
  `IdunBattle.Entities.Effects.Loki.PrioritisedEfficiency_DmgReductionEffect$$CreateEffectDamageMalusForDefense`
      = EffectBonus.ForPercentDecrease( DSLFactory.get_OwnerIsTarget, DSLFactory.ConfigConst(0x72) )

CE QUE CE FICHIER GARDE, et pourquoi le cas NOMINAL de #113 ne suffisait pas :
`GetDamageWithPiercing` = `max(0, dmg - armure, dmg x percage/100)`. Dans le regime PLANCHER-PERCAGE
(le terme percage gagne), un +25 % applique AVANT percage/armure et un +25 % applique APRES donnent
EXACTEMENT le meme nombre -- l'etat ne DISCRIMINE PAS l'etage. MESURE (probe_121, phase `regime`) :
sur `necroWarden` (armure 2008, percage 50, bornes [1595,2394]) les 4 coups sont dans ce regime,
ecart POST/PRE = 0 sur les 4. Reproduire le total y prouve la MAGNITUDE, pas l'ETAGE.
On CRAFTE donc une cible a armure basse (`genesMagus`, armure 1106) : le +25 % applique pre-percage
ferait BASCULER 3 coups sur 4 dans le regime ARMURE -> ecarts POST/PRE de 149 a 203 par coup.

Les 3 porteurs sont HORS du seed BC capture -> `catalog_inject.py` (#92). Fixtures de MODULE (les
runners sont rendus a la fin de CE fichier, cf. conftest `_release_module_owned_runners`).

ASCII only. Cibles prises dans `abilityTargets(...).fromHere` (une cible illegale rend le MEME
observable qu'une ability inerte).
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
from engine.entities.effects.magnitude import trait_var
from engine.services.static_battle_rules import get_damage_with_piercing

PYDIR = Path(__file__).resolve().parents[3]
DATA = PYDIR.parent.parent / "data"
BOARD = os.environ.get("PE121_BOARD", "MC1_67")
SEED = os.environ.get("PE121_SEED", "31337")

BESERK, IRONMASTER, UTHAR = "votanBeserk", "votanIronmaster", "votanUthar"
SPARE = "spaceHound"
# Cible CRAFTEE pour l'etage : armure BASSE (index gameconfig 11 -> 1106 live) => un +25 % pose
# pre-percage ferait basculer les coups du regime PLANCHER-PERCAGE au regime ARMURE.
SOFT_FOE = "genesMagus"
# Attaquant NEUTRE (aucun effet qui modifie le degat qu'il inflige) pour la face orientation.
PLAIN_ATTACKER = "necroWarden"

AUGMENTED_ASSAULT = 1221
PE_EXTRA_DMG = "PrioritisedEfficiency_ExtraDmg"
PE_DMG_REDUCTION = "PrioritisedEfficiency_DmgReduction"
PE_STANCE_OFFENSIVE = "PrioritisedEfficiency_HostileAcquisition_Stance"
PE_STANCE_DEFENSIVE = "PrioritisedEfficiency_FortifyTakeover_Stance"


def _pct() -> int:
    """ORACLE de magnitude : `ConfigConst(0xf)` = `globalValues.traitVariables
    .prioritisedEfficiencyExtraDmgPct`. Jamais un scalaire fige dans le test."""
    return int(trait_var("PrioritisedEfficiency", "prioritisedEfficiencyExtraDmgPct") or 0)


# ---------------------------------------------------------------------------------------------- #
# Harnais
# ---------------------------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def votann_bc():
    out = DATA / "_121_votann_bc.json"
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
    """DEPLACE l'unite pour obtenir la configuration voulue (doctrine : on ne se plaint jamais de la
    geometrie de spawn)."""
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


def _live_hits(a0, tgt_id, hp_before):
    """Degat COUP PAR COUP + verdict de crit, lus des events du cast (`UnitStats_RemainingHealth`
    successifs + `Attack_DidCrit`) -- jamais le seul total."""
    out, prev = [], int(hp_before or 0)
    for ev in (a0.get("events") or []):
        if ev.get("kind") != "action" or ev.get("entity") != tgt_id:
            continue
        tg = ev.get("tags") or ""
        if "UnitStats_RemainingHealth" not in tg or "Attack_DidCrit" not in tg:
            continue
        try:
            t = json.loads(tg)
        except Exception:
            continue
        hp = int(t.get("UnitStats_RemainingHealth"))
        out.append({"hp": hp, "dmg": prev - hp, "crit": bool(int(t.get("Attack_DidCrit") or 0))})
        prev = hp
    return out


def _cast_and_capture(rpc, build_runner, votann_bc, p_units, a_units,
                      caster_vis, foe_vis, ability_id, want_dist):
    """Monte un runner, amene le caster au contact, CAPTURE l'etat-avant (dv/ob/snap/rng), joue le
    coup LIVE, et rend de quoi rejouer EXACTEMENT le meme coup dans le port."""
    from engine.entities.pathfinding.board import Board
    args = ["--seed-bc", votann_bc, "--board", BOARD,
            "--p-units", p_units, "--a-units", a_units]
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

    # `ability_id=None` -> attaque NORMALE (le natif la traite comme une active `NormalAttackType`
    # PER-UNIT, cf. `decisionView.abilities[kind == 'normal']` : jamais un id generique).
    if ability_id is None:
        norm = next((ab for ab in (c.get("abilities") or []) if ab.get("kind") == "normal"), None)
        if norm is None:
            pytest.skip("pas d'attaque normale exposee")
        ability_id = int(norm["id"])
        normal_vector = True
    else:
        normal_vector = False
        legal = _from_here(rpc, rid, c["id"], ability_id)
        if f["id"] not in legal:
            pytest.skip(f"cible {f['id']} hors fromHere {legal}")

    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    act = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": c["id"], "targetId": f["id"],
        "abilityType": ability_id}}, 150)
    a0 = ((act or {}).get("actions") or [{}])[0]
    if not a0.get("mutated"):
        pytest.skip(f"coup non mute : {a0.get('error')}")

    def replay(drop_effects=()):
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
        if normal_vector:
            from engine.runner.operations.damage import AttackDamageOperation
            return st, (AttackDamageOperation.execute(st, c["id"], f["id"]) or {})
        from engine.runner.abilities.handler import ABILITY_CLASSES
        res = ABILITY_CLASSES[ability_id]().execute_behaviour(st, c["id"], f["id"])
        return st, ((res or {}).get("attack") or {})

    return {"rid": rid, "caster": c, "foe": f, "dv0": dv0,
            "live": _live_hits(a0, f["id"], f.get("hp")), "replay": replay}


@pytest.fixture(scope="module")
def pe_ability(rpc, build_runner, votann_bc):
    """ETAGE : cast AugmentedAssault (4 coups Eviscerate, percage 50) de votanBeserk sur une cible a
    armure BASSE -> etat DISCRIMINANT pre-/post-percage."""
    return _cast_and_capture(rpc, build_runner, votann_bc, f"{BESERK},{SPARE}", SOFT_FOE,
                             BESERK, SOFT_FOE, AUGMENTED_ASSAULT, want_dist=1)


@pytest.fixture(scope="module")
def pe_normal(rpc, build_runner, votann_bc):
    """VECTEUR ATTAQUE NORMALE : le natif n'a PAS de noeud `IsNormalAttack` -> le bonus doit AUSSI
    s'appliquer hors ability (i2 : « with all attacks »). #113 ne testait que le vecteur ABILITY."""
    return _cast_and_capture(rpc, build_runner, votann_bc, f"{BESERK},{SPARE}", SOFT_FOE,
                             BESERK, SOFT_FOE, None, want_dist=1)


@pytest.fixture(scope="module")
def pe_defender(rpc, build_runner, votann_bc):
    """ORIENTATION : le Votann est la CIBLE d'une attaque normale d'un attaquant NEUTRE. Le gate
    `get_OwnerIsCaster` doit rendre l'effet MUET (le degat recu est celui d'une cible sans trait)."""
    return _cast_and_capture(rpc, build_runner, votann_bc, PLAIN_ATTACKER, f"{BESERK},{SPARE}",
                             PLAIN_ATTACKER, BESERK, None, want_dist=1)


# ---------------------------------------------------------------------------------------------- #
# 1. MAGNITUDE + ORIENTATION structurelles (offline, sans bataille)
# ---------------------------------------------------------------------------------------------- #

def _fx(name, effect_type):
    from engine.entities.effects.factory import EffectFactory
    return EffectFactory.create({"name": name, "effectType": effect_type,
                                 "level": 1, "remaining": 0})


def test_magnitude_is_read_from_config_never_a_literal():
    """`ConfigConst(0xf)` -> `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` ->
    `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` de la config designee par la
    SOURCE de l'effet. Cette source est `AbilityOrEffect(0x5ce)` = **TriggeredAbilityType**
    .PrioritisedEfficiency = 1486 (surtout PAS EffectType 1486 = AncestralFortune_ExtraBlockChance) ;
    pour une triggered DERIVEE D'UN TRAIT, sa config vit dans `globalValues.traitVariables`.
    => la magnitude est `prioritisedEfficiencyExtraDmgPct`, PAS un 25 code en dur (piege `GetStuckIn`
    100/30 : les DEUX branches lisaient une variable de trait)."""
    eb = _fx(PE_EXTRA_DMG, 1481).create_effect_damage_bonus_for_attack()
    assert _pct() > 0, "gameconfig sans prioritisedEfficiencyExtraDmgPct"
    assert eb is not None and eb.kind == "PercentIncrease", f"kind != ForPercentIncrease : {eb}"
    assert eb.value == _pct(), f"magnitude {eb.value} != config {_pct()}"
    assert eb.owner_is_caster is True, "get_OwnerIsCaster -> contribution ATTAQUANT"
    assert eb.cap is None, "ForPercentIncrease natif sans plafond (pas de CappedEffectBonus)"


def test_no_gate_on_attack_nature_or_target():
    """CONDITIONS : le corps natif n'a QUE `get_OwnerIsCaster`. Aucun `IsNormalAttack`, aucun
    `IsMeleeAttack`/`IsRangedAttack`, aucun `HasTrait(cible, ...)`, aucun `CreateActiveCondition`
    (ces symboles n'existent pas pour cet effet). La contribution doit donc etre INVARIANTE a tout
    le contexte de coup — c'est ce qui distingue ce trait de `SmashaEad` (IsNormalAttack),
    `HeavyWeapon` (IsRangedAttack) ou `BeastSlayer` (trait de la cible)."""
    eff = _fx(PE_EXTRA_DMG, 1481)
    ref = eff.create_effect_damage_bonus_for_attack()
    for kwargs in ({"is_ranged": True}, {"is_ranged": False}, {"is_normal_attack": False},
                   {"is_normal_attack": True}, {"is_prediction": True}, {"has_moved": True},
                   {"has_moved": False}, {"target_traits": frozenset({"Mechanical"})},
                   {"target_traits": frozenset()}, {"target_armor_reduced": True}):
        got = eff.create_effect_damage_bonus_for_attack(**kwargs)
        assert got == ref, f"contribution gatee par {kwargs} : {got} != {ref}"


def test_the_two_stance_faces_are_mirrored_and_not_swapped():
    """1481 (offensif, `get_OwnerIsCaster`) et 1483 (defensif, `get_OwnerIsTarget`) sont les DEUX
    faces de la MEME stance. Aucune ne doit fuir sur le hook de l'autre — sinon « +25 % » se
    verrait aussi sur le degat RECU par le porteur (et le cas nominal, ou l'attaquant porte
    l'effet, ne le detecterait pas)."""
    atk = _fx(PE_EXTRA_DMG, 1481)
    assert atk.create_effect_damage_malus_for_defense() is None, \
        "1481 contribue cote DEFENSE -> slots source/targets inverses"
    dfn = _fx(PE_DMG_REDUCTION, 1483)
    assert dfn.create_effect_damage_bonus_for_attack() is None, "1483 contribue cote ATTAQUE"
    red = dfn.create_effect_damage_malus_for_defense()
    want = int(trait_var("PrioritisedEfficiency", "prioritisedEfficiencyDmgReductionPct") or 0)
    assert want > 0, "gameconfig sans prioritisedEfficiencyDmgReductionPct"
    assert red is not None and red.kind == "PercentDecrease" and red.owner_is_caster is False
    assert red.value == want, f"magnitude {red.value} != config {want}"


def test_stance_markers_stay_inert():
    """1479/1480 sont des MARQUEURS : aucune methode native (ni `CreateEffectDamage*`, ni
    `CreateActiveCondition`) — ils ne servent qu'aux `HasEffect` des behaviours de stance et de
    `GrimEfficiency`. Les porter avec une contribution serait un DOUBLE-COMPTE du +25 %."""
    for name, et in ((PE_STANCE_OFFENSIVE, 1479), (PE_STANCE_DEFENSIVE, 1480)):
        m = _fx(name, et)
        assert m.create_effect_damage_bonus_for_attack() is None, f"{name} contribue en attaque"
        assert m.create_effect_damage_malus_for_defense() is None, f"{name} contribue en defense"


# ---------------------------------------------------------------------------------------------- #
# 2. ETAGE — le cas DISCRIMINANT (live)
# ---------------------------------------------------------------------------------------------- #

def _stage_candidates(d):
    """Reconstruit COUP PAR COUP les DEUX placements candidats du bonus.

    Le degat REDUIT sans bonus (`off`) et les bornes de config donnent le tirage BRUT `raw` :
    `GetDamageWithPiercing(raw, p, a) = max(0, raw - a, raw x p/100)` -> `raw` vaut `off + a`
    (regime ARMURE) ou `off x 100/p` (regime PLANCHER-PERCAGE) ; on retient la branche COHERENTE
    (dans les bornes ET qui reproduit `off`). Puis :
        POST (etage natif) : `round( GetDamageWithPiercing(raw, p, a) x (1 + pct/100) )`
        PRE  (le leurre)   : `GetDamageWithPiercing( round(raw x (1 + pct/100)), p, a )`
    Rend `(pierce, armor, rows)` avec `rows[i] = {raw, off, post, pre}` ; `raw=None` si irreconciliable."""
    _st_off, off = d["replay"](drop_effects=(PE_EXTRA_DMG,))
    _st_on, on = d["replay"]()
    pierce, armor = int(on.get("pierce") or 0), int(on.get("armor") or 0)
    bmin, bmax = int(on.get("base_min") or 0), int(on.get("base_max") or 0)
    pct = _pct()
    rows = []
    for v in (off.get("per_hit") or []):
        raw = None
        cands = ([int(round(v * 100.0 / pierce))] if pierce > 0 else []) + [int(v) + armor]
        for cand in cands:
            if not (bmin - 1 <= cand <= bmax + 1):
                continue
            if abs(int(get_damage_with_piercing(cand, pierce, armor)) - int(v)) > 1:
                continue
            raw = cand
            break
        if raw is None:
            rows.append({"raw": None, "off": int(v), "post": None, "pre": None})
            continue
        base = int(get_damage_with_piercing(raw, pierce, armor))
        rows.append({"raw": raw, "off": int(v),
                     "post": int(round(base * (1 + pct / 100.0))),
                     "pre": int(get_damage_with_piercing(int(round(raw * (1 + pct / 100.0))),
                                                         pierce, armor))})
    return pierce, armor, rows, on


def test_state_is_actually_stage_discriminant(pe_ability):
    """GARDE-FOU du test suivant : sans elle, « le port colle » ne prouverait RIEN sur l'etage.
    On EXIGE qu'au moins un coup separe nettement les deux placements candidats (le regime
    PLANCHER-PERCAGE les rend IDENTIQUES — c'est le cas de la cible armure-2008 de #113)."""
    pierce, armor, rows, _on = _stage_candidates(pe_ability)
    assert armor > 0 and pierce < 100, f"armure {armor} / percage {pierce} : etage indiscriminable"
    known = [r for r in rows if r["raw"] is not None]
    assert known, f"aucun coup reconcilie avec GetDamageWithPiercing (rows={rows})"
    gaps = [abs(r["pre"] - r["post"]) for r in known]
    assert max(gaps) > 20, (
        f"aucun coup ne separe les deux etages (ecarts {gaps}, armure {armor}, percage {pierce}) "
        f"-- il faut une cible a armure PLUS BASSE, sinon le test suivant est vide")


def test_bonus_lands_after_pierce_and_armor_not_before(pe_ability):
    """CAS DISCRIMINANT (le livrable de #121). `ForPercentIncrease` alimente la **%-list** du
    `DamageModifiers` ATTAQUANT (`IdunBattle.Core.Services.DamageModifiers$$Add`), consommee par
    `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` **APRES** percage/armure
    (`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`) — donc jamais
    sur les bornes de degat ni sur la valeur tiree avant reduction.

    Sur les coups ou les deux placements different, le LIVE doit valider POST et REFUTER PRE."""
    pierce, armor, rows, _on = _stage_candidates(pe_ability)
    live = pe_ability["live"]
    assert live, "events per-coup indisponibles"
    checked = 0
    for i, h in enumerate(live):
        if i >= len(rows) or rows[i]["raw"] is None:
            continue
        r = rows[i]
        assert r["post"] == h["dmg"], (
            f"coup {i} : placement POST-percage = {r['post']}, live = {h['dmg']} "
            f"(raw {r['raw']}, percage {pierce}, armure {armor})")
        if r["pre"] != r["post"]:
            assert r["pre"] != h["dmg"], f"coup {i} : PRE-percage colle AUSSI ({r['pre']})"
            checked += 1
    assert checked >= 1, (
        f"aucun coup DISCRIMINANT confronte au live (rows={rows}) -- l'etage n'est pas tranche")


def test_port_matches_live_hit_by_hit_on_the_soft_target(pe_ability):
    """CONFRONTATION PER-COUP sur l'etat CRAFTE (jamais le seul total) : meme nombre de coups, meme
    verdict de crit, meme degat. C'est le 2e etat (cible armure basse) qui complete le nominal de
    #113 (armure 2008) : un port dont le facteur serait juste << ajuste >> sur l'un raterait l'autre."""
    _st, on = pe_ability["replay"]()
    live = pe_ability["live"]
    assert live, "events per-coup indisponibles"
    per = on.get("per_hit") or []
    crits = on.get("crits") or []
    assert len(per) == len(live), f"coups port {len(per)} != live {len(live)}"
    for i, h in enumerate(live):
        assert bool(crits[i]) == h["crit"], f"coup {i} : verdict de crit port != live"
        assert per[i] == h["dmg"], f"coup {i} : port {per[i]} != live {h['dmg']}"


def test_consuming_the_effect_changes_the_result(pe_ability):
    """A/B : consommer l'effet 1481 dans l'etat rejoue DOIT changer le degat — sinon le canal ne
    traverse pas le cast et l'egalite ci-dessus serait une coincidence."""
    _s1, on = pe_ability["replay"]()
    _s2, off = pe_ability["replay"](drop_effects=(PE_EXTRA_DMG,))
    carrier = _by_id(pe_ability["dv0"], pe_ability["caster"]["id"]) or {}
    assert PE_EXTRA_DMG in {e.get("name") for e in (carrier.get("effects") or [])}, \
        f"le caster ne porte pas {PE_EXTRA_DMG} -> l'A/B ne teste rien"
    assert int(off.get("total") or 0) < int(on.get("total") or 0), \
        "consommer 1481 ne change rien -> classe d'effet non branchee"


# ---------------------------------------------------------------------------------------------- #
# 3. « WITH ALL ATTACKS » — le vecteur ATTAQUE NORMALE (live)
# ---------------------------------------------------------------------------------------------- #

def test_bonus_applies_to_the_normal_attack_too(pe_normal):
    """Le natif n'ayant AUCUN noeud `IsNormalAttack`/`IsMeleeAttack`, le bonus s'applique aussi hors
    ability. #113 n'exercait que le vecteur ABILITY (`AttackWithAttackDamage`) ; ici c'est
    `AttackDamageOperation.Execute` (attaque normale, reduce-then-roll) : le port doit reproduire le
    live COUP PAR COUP, et retirer l'effet doit changer le resultat."""
    _st, on = pe_normal["replay"]()
    live = pe_normal["live"]
    assert live, "events per-coup indisponibles"
    per = on.get("per_hit") or []
    assert len(per) == len(live), f"coups port {len(per)} != live {len(live)}"
    for i, h in enumerate(live):
        assert per[i] == h["dmg"], f"coup {i} : port {per[i]} != live {h['dmg']}"
    _st2, off = pe_normal["replay"](drop_effects=(PE_EXTRA_DMG,))
    assert (off.get("per_hit") or []) != per, \
        "retirer 1481 ne change pas l'attaque NORMALE -> le canal ne la traverse pas"


# ---------------------------------------------------------------------------------------------- #
# 4. ORIENTATION — le porteur ATTAQUE ne gagne rien (live)
# ---------------------------------------------------------------------------------------------- #

def test_carrier_under_attack_takes_plain_damage(pe_defender):
    """`get_OwnerIsCaster` : quand le porteur est la CIBLE, l'effet 1481 est MUET. Deux verdicts :
      (a) le port reproduit le live COUP PAR COUP alors que la cible porte l'effet ;
      (b) consommer l'effet ne change RIEN (invariance) — un port qui l'aurait cable cote defenseur
          surestimerait le degat recu ET casserait (a)."""
    votann = _by_id(pe_defender["dv0"], pe_defender["foe"]["id"]) or {}
    assert PE_EXTRA_DMG in {e.get("name") for e in (votann.get("effects") or [])}, \
        f"la cible ne porte pas {PE_EXTRA_DMG} -> le test ne prouve rien"
    _st, on = pe_defender["replay"]()
    _st2, off = pe_defender["replay"](drop_effects=(PE_EXTRA_DMG,))
    live = pe_defender["live"]
    assert live, "events per-coup indisponibles"
    per = on.get("per_hit") or []
    assert len(per) == len(live), f"coups port {len(per)} != live {len(live)}"
    for i, h in enumerate(live):
        assert per[i] == h["dmg"], f"coup {i} : port {per[i]} != live {h['dmg']}"
    assert (off.get("per_hit") or []) == per, \
        "l'effet sur la CIBLE modifie le degat recu -> il a fui sur le hook defenseur"
