"""DoT de tuile `EnvFireTile` — la feuille route la famille ABILITY (`AbilityDamageOperation`),
PAS le degat direct.

RE (decompile = verite) :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour` appelle
  `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`, dont le corps construit
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
bouclier. Ces quatre tests confrontent le port au LIVE sur les deux faces -- dont les DEUX regimes
du cap `Resilient` (cape a `hp-1` / bypasse par `IsOverkill`), cf.
`docs/rl/case-455-r4-fenetre-cap-resilient.md`.

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
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.base import profile_pierce
from engine.dsl.effects import ExecutionContext
from engine.entities.pathfinding.board import Board
from engine.services.damage_prediction import apply_pierce_and_modifiers

W, H, MV_VIN = 7, 9, 3
P_UNITS = "adeptRetributor"
HP_TARGET = 500000          # -> dot = 20 % de PVmax = 100000, armure forcee a 0
# 2e p-unit JAMAIS activee, indispensable au test du cap `Resilient` (cf. sa docstring) : tant qu'une
# unite de mon camp n'a pas agi, le tour NE BASCULE PAS tout seul apres l'attaque, donc le tick de
# debut de tour adverse reste ISOLABLE. Passif `ToughToKill` = regen + reduction de degat SELF, aucune
# aura sur la cible ; elle reste a son spawn, hors du splash `FireOfAbsolution` (adjacents de la cible).
IDLE_UNIT = "astraDreir"


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


def _approach_only(rpc, rid, vin, tgt, me, max_rounds=8):
    """Amene l'attaquant a distance 2 EXACTEMENT **sans jamais attaquer** -> aucun feu pose, donc
    aucun tick, donc les PV de la cible restent CEUX DU BUILD. Rend la distance finale.

    Les tuiles candidates viennent d'`aiMovableTiles` (le BFS NATIF, creuse par blockers/terrain) et
    non d'une deduction hexagonale bornee par `W`/`H` : deviner la tuile ne marchait que sur
    `MC1_67`, et rendait un « distance 2 non atteinte » qui se lit comme une limite du montage
    (mesure : sur `C3_01` la deduction restait bloquee a distance 5 pendant 8 tours)."""
    d = None
    for _ in range(max_rounds):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        tu = next((u for u in (dec.get("units") or []) if u.get("id") == tgt), None)
        vu = next((u for u in _alive(dec) if u.get("id") == vin), None)
        if tu is None or not tu.get("alive") or vu is None:
            return None
        vp, tp = _pos(vu), _pos(tu)
        d = hexgeo.distance(vp, tp)
        if d == 2:
            return 2
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
        reach = []
        for mu in (mov.get("units") or []):
            if mu.get("unitId") == vin:
                reach = [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                         if t.get("col") is not None]
        occ = {_pos(u) for u in _alive(dec)} - {vp}
        reach = [t for t in reach if t not in occ]
        reach.sort(key=lambda t: (abs(hexgeo.distance(t, tp) - 2), hexgeo.distance(t, tp)))
        for t in reach[:8]:
            r = rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "move", "unitId": vin, "to": {"col": t[0], "row": t[1]}}]}, 60)
            if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
                vp = t
                break
        d = hexgeo.distance(vp, tp)
        if d == 2:
            return 2
        _endturn(rpc, rid)
        _skip_enemy(rpc, rid, me)
    return d


def _setup(rpc, rid, foe=None):
    """`foe` = visualId EXPLICITE de la cible ; sans lui, « la premiere qui n'est pas l'attaquant »
    (valide en 1v1 seulement — des qu'un allie inerte est present, il faut le nommer)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    vin = next((u["id"] for u in _alive(dv) if u.get("visualId") == P_UNITS), None)
    tgt = next((u["id"] for u in _alive(dv)
                if (u.get("visualId") == foe if foe else u.get("visualId") != P_UNITS)), None)
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


def _stage_burning_at(rpc, build_runner, pct, pierce, start_ratio):
    """MONTAGE PARTAGE des deux tests `Resilient` (#455-r4) : amene la cible `astraYarrick` sur une
    tuile EN FEU avec des PV COURANTS a `start_ratio x dot`, le tick de debut de tour adverse restant
    A VENIR. Rend `(rid, tgt, me, dot, hp_avant_tick)`.

    Deux leviers, tous deux necessaires (mesures dans `docs/rl/case-455-r4-*`) :
      * `--unit-stat "<cible>:RemainingHealth=<v>"` POSE les PV dans le regime voulu au lieu d'y
        descendre a coups d'attaques -- le pas de descente valait `attaque + tick` = ~110 000 pour
        une fenetre large de `dot/2` = 50 000, donc y atterrir tenait du tirage ;
      * une 2e p-unit JAMAIS activee (`IDLE_UNIT`) : sans elle l'attaque terminait l'activation de la
        SEULE p-unit, le tour basculait TOUT SEUL et le tick tombait dans le meme geste -- le degat
        lu melait attaque et tick, jamais isolables.
    L'approche se fait SANS attaquer (aucun feu, donc aucun tick) : les PV restent ceux du build
    jusqu'a l'unique attaque qui pose le feu. Les gardes ci-dessous echouent FRANCHEMENT (jamais un
    skip) : un montage non exerce doit rougir, cf. #455."""
    start_hp = int(round(HP_TARGET * int(pct) / 100 * start_ratio))
    rid = build_runner("90101", extra=["--p-units", f"{P_UNITS},{IDLE_UNIT}",
                                       "--a-units", "astraYarrick",
                                       "--hp-target", str(HP_TARGET),
                                       "--unit-stat", f"astraYarrick:RemainingHealth={start_hp}"])["rid"]
    vin, tgt, vin_norm, me = _setup(rpc, rid, foe="astraYarrick")
    st0, _ = _load(rpc, rid)
    thc0 = st0.get_entity(tgt).get_component(HealthComponent)
    base0 = int(round(int(thc0.hp_max) * int(pct) / 100))
    # `dot` = le tick NON cape, re-derive de l'etat REEL apres build (`--hp-target` met l'armure a 0,
    # donc le percage est no-op) : les deux bornes de la fenetre en descendent, rien n'est suppose.
    dot = int(round(apply_pierce_and_modifiers(
        base0, pierce_pct=pierce, armor=defender_fixed_armor(st0, tgt), mods=None)))
    assert _approach_only(rpc, rid, vin, tgt, me) == 2, \
        "distance 2 non atteinte (au contact l'arme est Physical, pas Flame) -> montage non exerce"
    # UNE attaque : elle POSE le feu sur la tuile de la cible et laisse le tour OUVERT (IDLE_UNIT
    # n'a pas agi), donc le tick de debut de tour adverse reste a venir et sera mesure SEUL.
    rpc("applyAction", {"runnerId": rid, "actions": [
        {"kind": "ability", "casterId": vin, "targetId": tgt, "abilityType": vin_norm}]}, 90)
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    tu = next((u for u in (dec.get("units") or []) if u.get("id") == tgt), None)
    assert tu is not None and tu.get("alive"), "cible morte a l'attaque -> montage non exerce"
    assert dec.get("currentPlayer") == me, \
        (f"le tour a bascule apres l'attaque (currentPlayer={dec.get('currentPlayer')}, me={me}) : "
         "le tick n'est plus isolable -> l'unite inerte n'a pas joue son role")
    assert _fire_on(rpc, rid, _pos(tu)), "la tuile de la cible n'a pas pris feu -> montage non exerce"
    return rid, tgt, me, dot, int(tu.get("hp") or 0)


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
    la TUAIT. Le cap ne mord que dans la fenetre `(dot/2, dot]` : sous `dot/2`,
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` rend vrai (`(dmg - hp)/hp*100 >= 100`,
    seuil `overkillDmgPctOfHealth`) et
    `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` passe le cap en
    BYPASS ; au-dessus de `dot`, le cap ne mord pas (`dmg <= hp-1`).

    MONTAGE (#455-r4) -- il ne DESCEND plus les PV a coups d'attaques, il les POSE dans la fenetre,
    pour deux raisons MESUREES (`probe_455r4_resilient_window.py --volet descente`) :
      * le pas de descente vaut `attaque + tick` = **~110 000** par tour pour une fenetre large de
        `dot/2` = **50 000** : atterrir dedans tenait du tirage, et le tour ou il y arrivait la
        tuile ne brulait pas -> le tour suivant tuait la cible (`cible morte avant la fenetre`) ;
      * l'attaque terminait l'activation de la SEULE p-unit, donc le tour basculait TOUT SEUL et le
        tick tombait dans le meme geste : le degat lu melait attaque et tick, jamais isolables.
    D'ou les deux leviers : `--unit-stat "<cible>:RemainingHealth=<v>"` (MESURE : mord bien, hp=90000
    pour hpMax=500000 -- ce n'est pas un champ ignore comme `Shield`, #342) et une 2e p-unit inerte
    (`IDLE_UNIT`) qui garde le tour ouvert apres l'attaque. L'approche se fait SANS attaquer, donc
    aucun feu, aucun tick, et les PV restent ceux du build jusqu'a l'unique attaque qui pose le feu."""
    pct = GC.global_value(FIRE_DMG_PCT_KEY)
    if not pct:
        pytest.skip("fireDmgPct absent du gameconfig")
    pierce = int(profile_pierce(None, FIRE_PROFILE))
    # PV COURANTS poses DANS la fenetre au BUILD. `--hp-target` met l'armure a 0, donc le tick vaut
    # exactement `pct % de PVmax` ; 90 % de cette valeur laisse la marge de l'unique attaque qui
    # pose le feu (~8 600 mesure) sans sortir de la fenetre. Le `dot` REEL est re-derive de l'etat
    # apres build (ci-dessous) et la fenetre re-verifiee avant le tick : rien n'est suppose.
    rid, tgt, me, dot, hp_win = _stage_burning_at(rpc, build_runner, pct, pierce, 0.9)
    assert dot // 2 < hp_win <= dot, \
        (f"PV {hp_win} hors de la fenetre discriminante ({dot // 2}, {dot}] -> le cap Resilient ne "
         "mordrait pas (au-dessus) ou serait bypasse par IsOverkill (en-dessous)")

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


def test_env_fire_tile_dot_resilient_cap_bypassed_on_overkill_live(rpc, build_runner):
    """LE BORD OPPOSE du meme etage : sous `dot/2`,
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` rend VRAI --
    `(healthDamage - initialHealth) / initialHealth * 100 >= 100` (le global
    `overkillDmgPctOfHealth`) -- et
    `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` passe alors
    `isGuaranteedOverkill` a
    `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit`, qui NE MORD PLUS :
    la cible `Resilient` MEURT du tick.

    POURQUOI CE TEST EXISTE, mesure a l'appui : le test du regime `(dot/2, dot]` ci-dessus **passe
    encore** si l'on neutralise le gate `IsOverkill` du port (`if not overkill:` -> `if True:`),
    parce que dans ce regime `overkill` vaut Faux de toute facon. Sans cette seconde garde, la
    moitie du bord est invisible -- un port qui caperait TOUJOURS resterait vert."""
    pct = GC.global_value(FIRE_DMG_PCT_KEY)
    if not pct:
        pytest.skip("fireDmgPct absent du gameconfig")
    pierce = int(profile_pierce(None, FIRE_PROFILE))
    rid, tgt, me, dot, hp_win = _stage_burning_at(rpc, build_runner, pct, pierce, 0.4)
    assert 0 < hp_win <= dot // 2, \
        (f"PV {hp_win} hors du regime overkill (0, {dot // 2}] -> `IsOverkill` serait faux et le cap "
         "mordrait : le bypass ne serait pas exerce")

    st, _dec = _load(rpc, rid)
    tile_id = st.board.id_at(*_pos(next(u for u in _alive(_dec) if u.get("id") == tgt)))
    off_total, _hb, off_after = _dot_offline(st, tile_id, tgt, pct)

    hp_before, hp_after, alive = _tick_once(rpc, rid, tgt, me)
    print(f"\n[ENVFIRE resilient overkill] dot={dot} hp {hp_before}->{hp_after} alive={alive} "
          f"port={off_total} (offline hp_after={off_after})")
    assert not alive, ("la cible Resilient a SURVECU au tick alors que `IsOverkill` est vrai -> le "
                       "cap n'a pas ete bypasse")
    assert off_after == 0, \
        (f"le port laisse la cible a {off_after} PV la ou le natif la TUE -> il cape encore malgre "
         "`IsOverkill` (gate `isGuaranteedOverkill` non porte)")
    assert off_total >= hp_before, \
        (f"port {off_total} < PV {hp_before} : le degat predit n'est pas letal, donc il est encore "
         "cape -- le bypass `IsOverkill` n'a pas eu lieu cote port")


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
