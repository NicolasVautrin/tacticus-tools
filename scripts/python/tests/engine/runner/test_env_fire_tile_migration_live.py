"""DoT de tuile `EnvFireTile` — la feuille route la famille ABILITY (`AbilityDamageOperation`),
PAS le degat direct.

RE (decompile = verite) :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour` appelle
  `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`, dont le corps construit
  `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$.ctor` + `IdunBattle.Entities.Behaviours.
  AttackBehaviour$$.ctor` -> famille ABILITY (`IdunBattle.Operations.AbilityDamageOperation` ->
  `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`). Il n'y a AUCUN
  `IdunBattle.Operations.DirectDamageOperation` sur ce chemin. `AttackBehaviour$$Execute` resout
  +0x50 = le CASTER en UNE entite (ici `Tiles(<occupant>)` = la TUILE) et +0x58 = les cibles
  (l'occupant). Le profil de degat vient du champ +0x90 de l'`AbilityDamageBehaviour`, lu par
  `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$GetDamageProfile` : c'est le
  `Direct(Nullable(3))` de l'arbre, et `3` = `DamageProfileType.Flame`.

Le port routait ce DoT par `AttackDamageOperation.execute_direct` (percage/armure SEULS, mods=None) :
numeriquement equivalent SEULEMENT pour une cible sans mod defenseur, sans cap de trait et sans
bouclier. Ces trois tests confrontent le port au LIVE sur les deux faces.

Runner isole, ennemi JAMAIS active (son tour est passe par endturn) : les seules mutations de PV
entre deux de mes tours sont les ticks de debut de tour. `adeptRetributor` porte l'arme
`hits=4 DamageProfile=Flame Range=2` -> son attaque normale POSE le feu (`OnFireDamageAbility`).
ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
import gameconfig as GC
from engine.runner.snapshot import load_state
from engine.runner.components import HealthComponent, StatsComponent, UnitComponent
from engine.runner.damage_model import defender_fixed_armor
from engine.runner.operations.triggers.loki import (env_fire_tile_tree, FIRE_PROFILE,
                                                    FIRE_DMG_PCT_KEY)
from engine.runner.abilities.behaviours import entities_from_state
from engine.runner.abilities.base import profile_pierce
from engine.dsl.effects import ExecutionContext
from engine.entities.pathfinding.board import Board
from engine.services.damage_prediction import apply_pierce_and_modifiers

W, H, MV_VIN = 7, 9, 3
P_UNITS = "adeptRetributor"
HP_TARGET = 500000          # -> dot = 20 % de PVmax = 100000, armure forcee a 0


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _alive(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _load(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tm), dec


def _dot_offline(state, tile_id, uid, pct):
    """La FEUILLE portee (`env_fire_tile_tree` -> famille ABILITY) executee sur `state`, avec la
    TUILE en caster (comme le natif). Renvoie (total, hp_before, hp_after) ou (None, None, None)."""
    ectx = ExecutionContext(state=state, rng=state.rng)
    env_fire_tile_tree(int(pct), FIRE_PROFILE).execute(
        entities_from_state(state, tile_id, uid), ectx)
    hit = next((p for n, p in ectx.emitted if n == "AttackWithAbilityDamage"), None)
    atk = (hit or {}).get("attack")
    if not atk:
        return None, None, None
    return atk.get("total"), atk.get("hp_before"), atk.get("hp_after")


def _fire_on(rpc, rid, pos):
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    rows = tm.get("tiles") if isinstance(tm, dict) else tm
    for t in (rows or []):
        if (t.get("col"), t.get("row")) == pos:
            for e in (t.get("effects") or []):
                if str(e.get("name") or "").lower().startswith("fire"):
                    return True
    return False


def _endturn(rpc, rid):
    try:
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    except Exception:
        pass


def _skip_enemy(rpc, rid, me):
    for _ in range(6):
        if rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer") == me:
            return
        _endturn(rpc, rid)


def _attack_once(rpc, rid, vin, tgt, vin_norm, me):
    """UN tour : approche a distance 2 puis attaque (baisse les PV ET re-pose le feu), endturn."""
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    tu = next((u for u in (dec.get("units") or []) if u.get("id") == tgt), None)
    vu = next((u for u in _alive(dec) if u.get("id") == vin), None)
    if tu is None or not tu.get("alive") or vu is None:
        return False
    vp, tp = _pos(vu), _pos(tu)
    occ = {_pos(u) for u in _alive(dec)} - {vp}
    if hexgeo.distance(vp, tp) != 2:
        ring2 = sorted([t for t in hexgeo.ring(tp[0], tp[1], 2)
                        if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ
                        and hexgeo.distance(vp, t) <= MV_VIN],
                       key=lambda t: hexgeo.distance(vp, t))
        cands = ring2 or sorted(
            [t for t in hexgeo.disk(vp[0], vp[1], MV_VIN)
             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ and t != vp],
            key=lambda t: hexgeo.distance(t, tp))[:6]
        for t in cands:
            r = rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "move", "unitId": vin, "to": {"col": t[0], "row": t[1]}}]}, 60)
            if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
                vp = t
                break
    if hexgeo.distance(vp, tp) == 2:
        rpc("applyAction", {"runnerId": rid, "actions": [
            {"kind": "ability", "casterId": vin, "targetId": tgt,
             "abilityType": vin_norm}]}, 90)
    _endturn(rpc, rid)
    _skip_enemy(rpc, rid, me)
    return True


def _drive_until_burning(rpc, rid, vin, tgt, vin_norm, me, max_rounds=8):
    """Approche Vindicta a distance 2 EXACTEMENT (au contact son arme est Physical, pas Flame),
    attaque pour POSER le feu, puis rend la main des que la tuile de la cible brule."""
    for _ in range(max_rounds):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        tu = next((u for u in (dec.get("units") or []) if u.get("id") == tgt), None)
        vu = next((u for u in _alive(dec) if u.get("id") == vin), None)
        if tu is None or not tu.get("alive") or vu is None:
            return False
        vp, tp = _pos(vu), _pos(tu)
        if _fire_on(rpc, rid, tp):
            return True
        occ = {_pos(u) for u in _alive(dec)} - {vp}
        if hexgeo.distance(vp, tp) != 2:
            ring2 = [t for t in hexgeo.ring(tp[0], tp[1], 2)
                     if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ
                     and hexgeo.distance(vp, t) <= MV_VIN]
            ring2.sort(key=lambda t: hexgeo.distance(vp, t))
            cands = ring2 or sorted(
                [t for t in hexgeo.disk(vp[0], vp[1], MV_VIN)
                 if 0 <= t[0] < W and 0 <= t[1] < H and t not in occ and t != vp],
                key=lambda t: hexgeo.distance(t, tp))[:6]
            for t in cands:
                r = rpc("applyAction", {"runnerId": rid, "actions": [
                    {"kind": "move", "unitId": vin, "to": {"col": t[0], "row": t[1]}}]}, 60)
                if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
                    vp = t
                    break
        if hexgeo.distance(vp, tp) == 2:
            rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "ability", "casterId": vin, "targetId": tgt,
                 "abilityType": vin_norm}]}, 90)
        _endturn(rpc, rid)
        _skip_enemy(rpc, rid, me)
    return False


def _setup(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    vin = next((u["id"] for u in _alive(dv) if u.get("visualId") == P_UNITS), None)
    tgt = next((u["id"] for u in _alive(dv) if u.get("visualId") != P_UNITS), None)
    vin_norm = None
    for u in (dv.get("units") or []):
        if u.get("id") == vin:
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    vin_norm = ab.get("id") if ab.get("id") is not None else ab.get("abilityId")
    if vin is None or tgt is None or vin_norm is None:
        pytest.skip("roster/attaque normale introuvables")
    return vin, tgt, vin_norm, dv.get("currentPlayer")


def _tick_once(rpc, rid, tgt, me):
    """Passe MON tour sans attaquer -> le tour ennemi demarre -> tick de debut de tour. Renvoie
    (hp_avant, hp_apres, vivant_apres)."""
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    tu = next((u for u in (dec.get("units") or []) if u.get("id") == tgt), None)
    hp_before = int((tu or {}).get("hp") or 0)
    _endturn(rpc, rid)
    _skip_enemy(rpc, rid, me)
    dec2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    tu2 = next((u for u in (dec2.get("units") or []) if u.get("id") == tgt), None)
    if tu2 is None or not tu2.get("alive"):
        return hp_before, 0, False
    return hp_before, int(tu2.get("hp") or 0), True


# --------------------------------------------------------------------- (2) LE GAIN, PROUVE

def test_env_fire_tile_dot_applies_defender_modifiers_live(rpc, build_runner):
    """CIBLE `TerminatorArmour` (mod DEFENSEUR x0.25, gate `DamageProfileIs` que le profil Flame ne
    declenche PAS d'exclusion) : le tick de feu NATIF vaut le quart de la base. La route
    `execute_direct` (mods=None) rendait 4x trop. Le port doit predire le chiffre natif."""
    rid = build_runner("90201", extra=["--p-units", P_UNITS, "--a-units", "darkaTerminator",
                                       "--hp-target", str(HP_TARGET)])["rid"]
    vin, tgt, vin_norm, me = _setup(rpc, rid)
    pct = GC.global_value(FIRE_DMG_PCT_KEY)
    if not pct:
        pytest.skip("fireDmgPct absent du gameconfig")
    assert _drive_until_burning(rpc, rid, vin, tgt, vin_norm, me), \
        "la tuile de la cible n'a pas pris feu -> montage non exerce"

    st, _dec = _load(rpc, rid)
    tile_id = st.board.id_at(*_pos(next(u for u in _alive(_dec) if u.get("id") == tgt)))
    e = st.get_entity(tgt)
    thc, tsc = e.get_component(HealthComponent), e.get_component(StatsComponent)
    armor = defender_fixed_armor(st, tgt)
    off_total, _hb, _ha = _dot_offline(st, tile_id, tgt, pct)
    # modele de l'ANCIENNE route (percage/armure SEULS) : c'est lui que la migration doit corriger
    pierce = int(profile_pierce(None, FIRE_PROFILE))
    base = int(round(int(thc.hp_max) * int(pct) / 100))
    legacy = int(round(apply_pierce_and_modifiers(base, pierce_pct=pierce, armor=armor, mods=None)))

    hp_before, hp_after, alive = _tick_once(rpc, rid, tgt, me)
    native = hp_before - hp_after if alive else None
    traits = sorted((GC.unit(e.get_component(UnitComponent).visual_id) or {}).get("traits") or [])
    print(f"\n[ENVFIRE ability-route] traits={traits} hp {hp_before}->{hp_after} "
          f"natif={native} port={off_total} legacy(execute_direct)={legacy}")
    assert native is not None, "la cible est morte au tick -> montage non exerce"
    assert native == off_total, f"port {off_total} != natif {native} (legacy aurait dit {legacy})"
    assert native != legacy, ("montage NON discriminant : l'ancienne route donne le meme chiffre "
                              "-> le gain de la migration n'est pas exerce")


def test_env_fire_tile_dot_applies_resilient_cap_live(rpc, build_runner):
    """CIBLE `Resilient` : l'etage LIMITES mode 2 de `CalculateAbilityDamage`
    (`IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit`) cape le tick a
    `hp-1` -> la cible SURVIT a 1 PV la ou `execute_direct` (aucun etage limites hors member-cap)
    la TUAIT. On amene les PV dans la fenetre (dot/2, dot] (au-dela, `IsOverkill` bypasse le cap)."""
    rid = build_runner("90101", extra=["--p-units", P_UNITS, "--a-units", "astraYarrick",
                                       "--hp-target", str(HP_TARGET)])["rid"]
    vin, tgt, vin_norm, me = _setup(rpc, rid)
    pct = GC.global_value(FIRE_DMG_PCT_KEY)
    if not pct:
        pytest.skip("fireDmgPct absent du gameconfig")
    pierce = int(profile_pierce(None, FIRE_PROFILE))

    st0, _ = _load(rpc, rid)
    thc0 = st0.get_entity(tgt).get_component(HealthComponent)
    base0 = int(round(int(thc0.hp_max) * int(pct) / 100))
    dot = int(round(apply_pierce_and_modifiers(
        base0, pierce_pct=pierce, armor=defender_fixed_armor(st0, tgt), mods=None)))
    # On DESCEND les PV avec l'attaque Flame (qui re-enflamme la tuile a chaque coup) jusqu'a la
    # fenetre (dot/2, dot] : au-dessus le tick n'est pas discriminant, en-dessous `IsOverkill`
    # (seuil overkillDmgPctOfHealth=100) bypasse le cap Resilient.
    for _ in range(12):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        tu = next((u for u in (dec.get("units") or []) if u.get("id") == tgt), None)
        if tu is None or not tu.get("alive"):
            pytest.fail("cible morte avant la fenetre discriminante")
        hp = int(tu.get("hp") or 0)
        if dot // 2 < hp <= dot and _fire_on(rpc, rid, _pos(tu)):
            break
        if not _attack_once(rpc, rid, vin, tgt, vin_norm, me):
            pytest.fail("pilotage KO (cible ou attaquant perdu)")
    else:
        pytest.skip(f"fenetre ({dot // 2}, {dot}] non atteinte")

    st, _dec = _load(rpc, rid)
    tile_id = st.board.id_at(*_pos(next(u for u in _alive(_dec) if u.get("id") == tgt)))
    thc = st.get_entity(tgt).get_component(HealthComponent)
    hp_avant = int(thc.hp)
    off_total, _hb, off_after = _dot_offline(st, tile_id, tgt, pct)

    hp_before, hp_after, alive = _tick_once(rpc, rid, tgt, me)
    print(f"\n[ENVFIRE resilient] dot={dot} hp {hp_before}->{hp_after} alive={alive} "
          f"port={off_total} (offline hp_after={off_after})")
    assert alive, ("la cible Resilient est MORTE du tick -> c'est le comportement de l'ancienne "
                   "route `execute_direct`, pas celui du natif")
    assert hp_after == 1, f"cap Resilient attendu a 1 PV, lu {hp_after}"
    assert hp_before - hp_after == off_total, \
        f"port {off_total} != natif {hp_before - hp_after} (hp avant tick offline={hp_avant})"


# ------------------------------------------------------------- (1) NON-REGRESSION

def test_env_fire_tile_dot_unchanged_on_neutral_targets(rpc, build_runner):
    """NON-REGRESSION : sur les cibles NEUTRES (aucun mod defenseur, aucun cap de trait, aucun
    bouclier), la route ABILITY rend EXACTEMENT le percage/armure de l'ancienne route
    `execute_direct` — sauf sur un demi-entier, ou l'ancien `int(round(...))` de Python arrondissait
    au PAIR alors que le natif materialise `Round(..., AwayFromZero)` (etage #90 de
    `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`) : l'ecart est
    alors de +1, et c'est l'ANCIENNE valeur qui etait fausse. Property-based sur toutes les unites."""
    rid = build_runner("777")["rid"]
    pct = GC.global_value(FIRE_DMG_PCT_KEY)
    if not pct:
        pytest.skip("fireDmgPct absent du gameconfig")
    st, dec = _load(rpc, rid)
    pierce = int(profile_pierce(None, FIRE_PROFILE))
    tile_ids = [t.get("id") for t in ((rpc("boardGraph", {"runnerId": rid}, 60) or {}).get("tiles")
                                      or []) if t.get("id") is not None]
    if not tile_ids:
        pytest.skip("boardGraph sans tuiles")
    src = tile_ids[0]                       # caster = une entite TUILE (comme le natif)

    checked, diffs = 0, []
    for eid in list(st.entities):
        e = st.get_entity(eid)
        thc, tsc, tuc = (e.get_component(HealthComponent), e.get_component(StatsComponent),
                         e.get_component(UnitComponent))
        if thc is None or tsc is None or tuc is None or not tuc.alive:
            continue
        traits = set((GC.unit(tuc.visual_id) or {}).get("traits") or [])
        if traits & {"TerminatorArmour", "Resilient"}:
            continue                        # cibles a mod/cap : couvertes par les 2 tests LIVE ci-dessus
        armor = defender_fixed_armor(st, eid)
        base = int(round(int(thc.hp_max) * int(pct) / 100))
        raw = apply_pierce_and_modifiers(base, pierce_pct=pierce, armor=armor, mods=None)
        legacy = int(round(raw))
        # `Round(..., AwayFromZero)` du natif : seule difference admise avec `int(round())` Python
        expected = int(raw) + 1 if (raw - int(raw)) >= 0.5 else int(raw)
        st2, _ = _load(rpc, rid)            # etat FRAIS (le DoT MUTE les PV)
        got, _hb, _ha = _dot_offline(st2, src, eid, pct)
        checked += 1
        if got != expected:
            diffs.append(f"u{eid} {tuc.visual_id}: got={got} attendu={expected} legacy={legacy}")
    print(f"\n[ENVFIRE non-regression] {checked} cible(s) neutre(s) confrontee(s)")
    assert checked > 0, "aucune cible neutre -> setup non exerce"
    assert not diffs, f"{len(diffs)} divergence(s): {diffs[:8]}"
