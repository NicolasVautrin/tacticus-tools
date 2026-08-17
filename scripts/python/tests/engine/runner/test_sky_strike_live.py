"""SkyStrike (actif 1025, adeptCelestine = Celestine, Sisterhood) PORT -> arbre DSL charge+attaque, confronte
au LIVE.

`SkyStrikeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 -- cf. `abilities/sisterhood.py`) =
template VigilanceEternal EXACT, MOINS la contrainte de reach du move, PLUS attaque = attaque melee NORMALE :
    op_BitwiseAnd(
      If( Not(IsAdjacent(caster@0x160, target@0x178, 3)),                                         # MOVE (charge)
          MoveUnit(caster, First(SortTilesByUtility(CanAddUnit(AdjacentTiles(target)), caster,
                                 UtilityDefinition(7)), 1)) ),
      If( <factory+0x98 = gate alive>,                                                            # ATTACK gate
          AttackWithAttackDamage(caster, target,
              Sum(NormalAttackDamage(caster)=StatAmount(Attack), Direct(GetVariableForLevel(8=extraDmg))),
              NormalMeleeAttackDamageProfile(caster), MeleeWeaponHits(caster)) ) )                # melee normale

FINDINGS DECOMPILE (VA citees dans sisterhood.py) :
  - dest = `CanAddUnit(AdjacentTiles(target))` SANS `MovableTilesInRange` (contraste VigilanceEternal
    `GetPossibleMovementTiles`) -> AUCUNE limite de portee (Celestine vole). Collapse = tuile libre ring-1 de
    la cible la PLUS PROCHE du caster.
  - ATTACK = overload `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (VERIFIE list_xrefs : call-site IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour+0x382 ; ABSENT
    de IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage) = MEME AttackDamageBehaviour, famille "attack". Node de degat = `Sum(
    NormalAttackDamage(caster), Direct(extraDmg))` ou `IdunBattleLogic.Entities.DSLFormulas$$NormalAttackDamage`
    est LA MEME factory que celle de l'ATTAQUE NORMALE (`IdunBattleLogic.Entities.Abilities.Active.Loki.
    ALoki_NormalAttackAbility$$AttackAmount`, xrefs verifiees). **#226-r : LE COUP PORTE LE SPREAD +-20 %.**
    Le 8e argument natif (`Nullable<AttackDamageBehaviourOptions>`) est construit avec l'OCTET **+6 = 1**
    (`uStack_1e2 = 1`, seul octet non nul ; +4 = alwaysOverkilled, +5 = alwaysCrit) -- le meme octet que
    `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` renseigne DEPUIS UN GETTER de l'ability pour
    l'attaque NORMALE = drapeau « calcul de degat d'ARME ». Il transite `AttackDamageBehaviour+0x9e` ->
    `AttackDamageOperation$$ExecuteHit` (options+0x2f) -> `AttackPredictionRequest+0x6a` -> slot 4
    `IdunBattle.Core.Services.DamagePrediction$$PredictAttack`, ou `GetBaseDamageFix64` etale les bornes
    autour de V = Attack + extraDmg. Pipeline = celui de l'attaque NORMALE : bornes REDUITES puis 1 tirage/
    coup (reduce-then-roll) -> mode `amount` + `amount_spread_pct=20`. CONTRASTE : le smite Psyker
    (`PsykerExtraAttackAbility$$CreateBehaviour`) passe ce meme Nullable VIDE et n'a AUCUNE variance (live).
    Profil/coups = arme MELEE (Celestine = Power / 3 coups, MeleeWeaponHits = WeaponHitsFormula
    IdunBattle.Entities.Formulas.WeaponHitsFormula$$Calculate, SANS ExtraHits).
  - `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$GetDynamicInvalidTargetReason` (eligibilite, HORS ExecuteBehaviour) : gate DidMove(caster) -> une
    Celestine DEJA bougee ET non-adjacente ne peut PAS caster (reason 0x10). CONFIRME LIVE (b1/b2 ci-dessous).

PORTEUR HORS POOL : adeptCelestine est absente du seed BC capture -> on l'INJECTE via
`catalog_inject.write_augmented_seed_bc` (bloc `Units` + configs `Abilities`, `ActiveAbilities=[1025]`). Elle
spawne AVEC SkyStrike reconnue (abilityTargets `fromHere` non-vide quand NON bougee) et le cast LIVE de 1025
REUSSIT (volet E).

  (#226 -- ce que l'ancien « residu de cast live » etait vraiment.) Le cast levait « system error » tant que le
  seed BC injecte n'embarquait QUE le bloc Unit : `BattleConfiguration.Abilities` du seed capture ne porte que
  les abilities des unites de CETTE bataille, donc `AbilityConfiguration.GetVariableForLevel(8=extraDmg)`
  tournait sur une config NULLE. Ce n'etait ni le rang du porteur ni un array « non materialise hors
  progression roster » (diagnostics anterieurs, FAUX). Mesure a bloc Unit CONSTANT
  (`probe_226_seed_bc_ability_configs.py`) : sans configs `ok=False errors=['system error']` ; avec configs
  `ok=True hits=[3188, 2660, 3249]`.

CE QUE LE TEST VALIDE :
  (A) A/B BIT-EXACT (deterministe, etat live-capture) : l'arbre `sky_strike_tree` (attaque) == un appel DIRECT
      `execute_normal_like(V, melee_pierce, MeleeWeaponHits, spread_pct=20)` sous le MEME rng -> prouve
      base=Attack+extraDmg, hits=arme-melee, profil/pierce melee, famille attack, pipeline d'ARME.
  (B) SPREAD : nb de coups == MeleeWeaponHits et chaque coup vit dans la plage V+-20 % (bornes brutes).
  (C) CHARGE : Celestine a dist 2/5 d'une cible non-adjacente -> MOVE sur la tuile libre adjacente la plus proche
      (SANS limite de portee : dist 5 charge AUSSI -- discriminant vs VigilanceEternal reach=2) ; deja-adjacente
      -> AUCUN move.
  (D) GATE has-not-moved (LIVE) : Celestine NON bougee + tuile libre adjacente a la cible -> castable ; Celestine
      BOUGEE + non-adjacente -> NON castable (reason 0x10). Discriminant de `GetDynamicInvalidTargetReason`.
      AUCUN cast n'y est emis : un cast consommerait l'action de Celestine et rendrait (b2) vacuous (elle
      serait refusee pour « a deja agi », pas pour le gate).
  (E) CAST LIVE (runner DEDIE, garde de non-regression #226 + AGREEMENT #226-r) : le cast natif de 1025
      REUSSIT et rend `MeleeWeaponHits` coups (un seed BC injecte sans ses configs d'ability rendrait
      `ok=False errors=['system error']`), ET le port rejoue sur l'etat pre-cast avec le rng dumpe rend
      les MEMES valeurs coup par coup (BIT-EXACT).

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only. Skip si build/injection/geometrie/adeptCelestine indispo.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo
import gameconfig as GC

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                     # racine repo
CASTER_VIS = "adeptCelestine"
ABILITY = 1025
A_UNITS = "necroWarden,necroWarden,necroOverlord"


# ------------------------------------------------------------------ helpers etat

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _find_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _team(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _enemies_of(state, uid):
    from engine.runner.components import UnitComponent, OwnerComponent
    mine = _team(state, uid)
    out = []
    for oid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team == mine:
            continue
        out.append(oid)
    return out


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _caster_params(state, cid):
    """(V=Attack+extraDmg, melee_pierce, melee_hits, profile) du caster (mirror des nodes SkyStrike)."""
    from engine.runner.components import StatsComponent
    from engine.runner.damage_model import select_weapon, select_weapon_pierce
    from engine.entities.stats import StatType
    from engine.entities.effects.magnitude import ability_var
    ctx = state.get_entity(cid).get_component(StatsComponent).ctx
    atk = int(ctx.stats.get_stat(int(StatType.ATTACK), 0))
    pierce, _ranged, whits = select_weapon_pierce(ctx, 1)
    profile = (select_weapon(ctx, 1) or {}).get("DamageProfile")
    extra = int(ability_var("SkyStrike", "extraDmg", ctx.active_ability_level,
                            multiplier_pct=ctx.ability_variables_multiplier) or 0)
    return atk + extra, pierce, int(whits), profile


def _walk_nbrs(board, tid):
    return [n for n in board.neighbours(tid) if board.walkable(n)]


def _park_others(state, board, keep_ids, center_coord):
    from engine.runner.components import UnitComponent
    used = set()
    far = [t for t in board.by_id
           if board.walkable(t) and hexgeo.distance(board.coord(t), center_coord) > 4]
    far.sort()
    it = iter(far)
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uid in keep_ids or uc is None or not uc.alive:
            continue
        for t in it:
            if t not in used:
                used.add(t)
                _set_pos(state, uid, *board.coord(t))
                break


def _find_charge(board, start_dist):
    """(T, cel_start) : T marchable avec >=2 voisins marchables ; cel_start a dist HEX `start_dist` de T.
    AUCUNE contrainte de reach (SkyStrike vole). Renvoie None si aucune."""
    for T in sorted(board.by_id):
        if not board.walkable(T):
            continue
        if len(_walk_nbrs(board, T)) < 2:
            continue
        for js in sorted(board.by_id):
            if not board.walkable(js) or js == T:
                continue
            if hexgeo.distance(board.coord(js), board.coord(T)) == start_dist:
                return board.coord(T), board.coord(js)
    return None


def _find_adjacent_pair(board):
    for T in sorted(board.by_id):
        if not board.walkable(T):
            continue
        nbrs = _walk_nbrs(board, T)
        if len(nbrs) >= 2:
            return board.coord(T), board.coord(nbrs[0])
    return None


# ------------------------------------------------------------------ injection seed BC

def _write_injected_seed_bc(tag: str):
    """Seed BC augmente d'`adeptCelestine` -- bloc `Units` **ET** configs `Abilities` (`SkyStrike`,
    `GeminaeSuperia`) -- via `catalog_inject.write_augmented_seed_bc`, le mirror de
    `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration`. N'ECRIT JAMAIS le seed
    partage. `ActiveAbilities` est restreint a 1025 pour ISOLER SkyStrike de la passive GeminaeSuperia
    (non portee) ; les CONFIGS restent toutes posees (une config non portee est inerte).
    None si le seed BC de reference est absent.

    PAS DE CLONE DE BLOC UNIT (etat anterieur) -- deux defauts, mesures par
    `probe_226_seed_bc_ability_configs.py` :
      1. sans les configs d'ability, le cast natif rend `ok=False errors=['system error']`
         (`IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` sur config nulle) ;
      2. le clone portait les STATS de l'unite clonee : SkyStrike = `Sum(StatAmount(Attack), extraDmg)`
         donc l'Attack d'une Canoness deguisee, pas celle de Celestine. La synthese, elle, laisse
         `buildNormalizedBC` recalculer les stats du VRAI porteur (clone `hits=[3188, 2660, 3249]` vs
         synthese `hits=[3334, 3156, 2477]` sur le meme montage)."""
    import catalog_inject as CI
    if not CI.SEED_BC.exists():
        return None
    path, _units, _abilities = CI.write_augmented_seed_bc(
        ROOT / "logs" / "runners" / f"sky-seedbc-{tag}.json",
        [CASTER_VIS], restrict_abilities={CASTER_VIS: ([ABILITY], [])})
    return path


# ------------------------------------------------------------------ fixture

@pytest.fixture(scope="module")
def sky_state(rpc):
    """Etat LIVE reel (adeptCelestine injectee + necrons) capture au SPAWN (Celestine NON bougee), rejouable."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister

    tag = uuid.uuid4().hex[:8]
    bc_file = _write_injected_seed_bc(tag)
    if bc_file is None:
        pytest.skip("seed BC de reference absent (data/seed-bc.json)")
    state_file = ROOT / "logs" / "runners" / f"sky-test-{tag}.json"
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(state_file),
         "--seed-bc", str(bc_file), "--board", "MC1_67", "--roster", "1",
         "--p-units", CASTER_VIS, "--a-units", A_UNITS, "--hp-target", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        for p in (state_file, bc_file):
            try:
                p.unlink()
            except Exception:
                pass
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        rpc("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"]); r.mti = rng0["mti"]
            st.rng = r
        return st

    if _find_by_vis(build_state(), CASTER_VIS) is None:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip("adeptCelestine absente du build (injection KO)")
    yield {"build_state": build_state, "board": board, "rid": rid,
           "dv": dv, "ob": ob, "snap": snap, "rng0": rng0}
    try:
        rpc("disposeRunner", {"runnerId": rid}, 20)
    except Exception:
        pass
    for p in (state_file, bc_file):
        try:
            p.unlink()
        except Exception:
            pass


# ------------------------------------------------------------------ tests

def test_skystrike_charge_dist2_move_then_attack(sky_state):
    """(C) Celestine a dist 2 d'une cible non-adjacente -> MOVE sur la tuile libre adjacente la plus proche
    (charge), termine ADJACENTE ; l'attaque endommage la cible."""
    from engine.runner.abilities.sisterhood import SkyStrikeAbility
    state = sky_state["build_state"]()
    board = sky_state["board"]
    cel = _find_by_vis(state, CASTER_VIS)
    enemies = _enemies_of(state, cel)
    if cel is None or not enemies:
        pytest.skip("Celestine + 1 ennemi requis")
    clus = _find_charge(board, start_dist=2)
    if clus is None:
        pytest.skip("aucune geometrie de charge dist2")
    t_coord, cel_coord = clus
    target = enemies[0]
    _park_others(state, board, {cel, target}, t_coord)
    _set_pos(state, target, *t_coord)
    _set_pos(state, cel, *cel_coord)
    assert hexgeo.distance(cel_coord, t_coord) == 2

    hp0 = _hp(state, target)
    res = SkyStrikeAbility().execute_behaviour(state, cel, target)
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
    assert res["move"] is not None and res["move"].get("moved") is True, f"pas de charge: {res['move']}"
    assert hexgeo.distance(_pos(state, cel), t_coord) == 1, \
        f"Celestine pas adjacente post-charge: {_pos(state, cel)} vs {t_coord}"
    assert res["attack"] is not None and _hp(state, target) < hp0, \
        f"cible pas endommagee (hp {hp0} -> {_hp(state, target)})"


def test_skystrike_charge_dist5_no_reach_limit(sky_state):
    """(C) DISCRIMINANT vs VigilanceEternal : dist 5 (bien au-dela d'une move-range) -> Celestine CHARGE
    QUAND MEME (dest = `CanAddUnit(AdjacentTiles(target))` SANS `MovableTilesInRange` -- elle vole). Un port
    avec reach (VigilanceEternal) ne trouverait AUCUNE tuile atteignable a dist 5 -> pas de move."""
    from engine.runner.abilities.sisterhood import SkyStrikeAbility
    state = sky_state["build_state"]()
    board = sky_state["board"]
    cel = _find_by_vis(state, CASTER_VIS)
    enemies = _enemies_of(state, cel)
    if cel is None or not enemies:
        pytest.skip("Celestine + 1 ennemi requis")
    clus = _find_charge(board, start_dist=5)
    if clus is None:
        pytest.skip("aucune geometrie de charge dist5")
    t_coord, cel_coord = clus
    target = enemies[0]
    _park_others(state, board, {cel, target}, t_coord)
    _set_pos(state, target, *t_coord)
    _set_pos(state, cel, *cel_coord)
    assert hexgeo.distance(cel_coord, t_coord) == 5

    res = SkyStrikeAbility().execute_behaviour(state, cel, target)
    assert res is not None
    assert res["move"] is not None and res["move"].get("moved") is True, \
        f"Celestine devrait charger depuis dist 5 (aucune limite de reach): {res['move']}"
    assert hexgeo.distance(_pos(state, cel), t_coord) == 1, \
        f"Celestine pas adjacente post-charge dist5: {_pos(state, cel)}"


def test_skystrike_already_adjacent_no_move(sky_state):
    """(C) GATE `Not(IsAdjacent)` : Celestine DEJA adjacente -> AUCUN move. L'attaque a lieu quand meme."""
    from engine.runner.abilities.sisterhood import SkyStrikeAbility
    state = sky_state["build_state"]()
    board = sky_state["board"]
    cel = _find_by_vis(state, CASTER_VIS)
    enemies = _enemies_of(state, cel)
    if cel is None or not enemies:
        pytest.skip("Celestine + 1 ennemi requis")
    pair = _find_adjacent_pair(board)
    if pair is None:
        pytest.skip("aucune paire adjacente")
    t_coord, cel_coord = pair
    target = enemies[0]
    _park_others(state, board, {cel, target}, t_coord)
    _set_pos(state, target, *t_coord)
    _set_pos(state, cel, *cel_coord)
    assert hexgeo.distance(cel_coord, t_coord) == 1

    hp0 = _hp(state, target)
    res = SkyStrikeAbility().execute_behaviour(state, cel, target)
    assert res is not None
    assert res["move"] is None, f"un move a fire alors que Celestine etait adjacente: {res['move']}"
    assert _pos(state, cel) == cel_coord, "Celestine a bouge malgre le gate deja-adjacent"
    assert res["attack"] is not None and _hp(state, target) < hp0, "l'attaque devrait avoir lieu"


def test_skystrike_attack_ab_and_spread(sky_state):
    """(A) A/B BIT-EXACT + (B) SPREAD : Celestine adjacente (aucun move) -> l'attaque de l'arbre == un appel
    DIRECT `execute_normal_like(V, melee_pierce, MeleeWeaponHits, spread_pct=20)` (meme rng) ; les coups sont
    tires dans la plage V+-20 % REDUITE (et non tous egaux) ; nb de coups == MeleeWeaponHits.

    #226-r : la reference A/B a CHANGE (avant : `execute_ability_attack(V, V)` bornes degenerees). Le 8e
    argument natif d'`AttackWithAttackDamage` pose l'OCTET +6 des `AttackDamageBehaviourOptions` a 1 -- le
    drapeau « calcul de degat d'ARME » que `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` renseigne
    pour l'attaque NORMALE -> `GetBaseDamageFix64` etale les bornes autour de V. Le CAST LIVE est confronte
    bit-exact dans `test_skystrike_cast_live`."""
    from engine.runner.abilities.sisterhood import SkyStrikeAbility
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.services.damage_calculations import spread_to_min_max
    board = sky_state["board"]
    pair = _find_adjacent_pair(board)
    if pair is None:
        pytest.skip("aucune paire adjacente")
    t_coord, cel_coord = pair

    def _setup(st):
        cel = _find_by_vis(st, CASTER_VIS)
        enemies = _enemies_of(st, cel)
        if cel is None or not enemies:
            return None, None
        target = enemies[0]
        _park_others(st, board, {cel, target}, t_coord)
        _set_pos(st, target, *t_coord)
        _set_pos(st, cel, *cel_coord)
        return cel, target

    st = sky_state["build_state"]()
    cel, target = _setup(st)
    if cel is None:
        pytest.skip("Celestine + 1 ennemi requis")
    V, pierce, whits, profile = _caster_params(st, cel)
    res = SkyStrikeAbility().execute_behaviour(st, cel, target)
    assert res["move"] is None, "adjacente -> aucun move attendu (isole l'attaque)"
    inner = (res.get("attack") or {}).get("attack") or {}
    tree_ph = inner.get("per_hit")
    assert tree_ph, f"pas de per_hit dans l'attaque portee: {res.get('attack')}"

    # (B) nb de coups == MeleeWeaponHits + les coups vivent dans la plage V+-20 % (bornes BRUTES = borne
    # SUPERIEURE de la plage reduite : perçage/armure ne peuvent que la RETRECIR).
    assert len(tree_ph) == whits, f"nb de coups {len(tree_ph)} != MeleeWeaponHits {whits}"
    mm = spread_to_min_max(int(V), 20)
    assert all(0 <= h <= mm.max for h in tree_ph), \
        f"coup hors de la plage brute V+-20 % [0,{mm.max}] (V={V}): {tree_ph}"

    # (A) A/B : sequence directe execute_normal_like(V, spread 20) sous le MEME rng
    st_dir = sky_state["build_state"]()
    cel_d, target_d = _setup(st_dir)
    direct = AttackDamageOperation.execute_normal_like(
        st_dir, cel_d, target_d, V, pierce, hits=whits, spread_pct=20,
        damage_profile=profile, is_melee=True, ability_type=ABILITY,
        is_attack_damage_op=True)                                          # native_factory="attack"
    assert tree_ph == (direct or {}).get("per_hit"), (
        f"arbre per_hit {tree_ph} != sequence directe {(direct or {}).get('per_hit')} "
        f"(la feuille n'appelle pas execute_normal_like(V, spread 20) fidele)")


def test_skystrike_has_not_moved_gate_live(sky_state, rpc):
    """(D) GATE has-not-moved (LIVE) : `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$GetDynamicInvalidTargetReason` -> une Celestine NON bougee
    (au spawn) + cible avec tuile libre adjacente est CASTABLE (`fromHere` non-vide) ; une Celestine BOUGEE et
    non-adjacente est NON castable (reason 0x10). Le cast LIVE est TENTE mais non asserte (RESIDU out-of-pool
    extraDmg, idem SavageEchoes)."""
    rid = sky_state["rid"]
    board = sky_state["board"]
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    units = dv.get("units") or []
    cel = next((u for u in units if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    if cel is None:
        pytest.skip("Celestine absente live")
    myp = cel.get("owner")
    enemies = [u for u in units if u.get("owner") != myp and u.get("alive")]
    if not enemies:
        pytest.skip("aucun ennemi")
    target = enemies[0]
    cel_pos = (cel.get("pos") or {}).get("col"), (cel.get("pos") or {}).get("row")

    def _mv(uid, tid):
        c = board.coord(tid)
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

    def _fromhere(cid):
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
        us = at.get("units") or []
        uu = next((x for x in us if x.get("unitId") == cid), {})
        ab = next((a for a in (uu.get("abilities") or []) if a.get("abilityId") == ABILITY), {})
        return [x.get("targetId") for x in (ab.get("fromHere") or [])]

    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    # cible T a dist 2 du spawn Celestine, >=2 voisins libres ; on NE bouge PAS Celestine (elle reste au spawn)
    T = next((t for t in walk if hexgeo.distance(board.coord(t), cel_pos) == 2
              and len([n for n in board.neighbours(t) if board.walkable(n) and board.coord(n) != cel_pos]) >= 2),
             None)
    if T is None:
        pytest.skip("aucune cible dist2 du spawn")
    tc = board.coord(T)
    far = [t for t in walk if hexgeo.distance(board.coord(t), tc) > 6
           and hexgeo.distance(board.coord(t), cel_pos) > 2]
    others = [u for u in units if u["id"] not in (cel["id"], target["id"])]
    for u, ft in zip(others, far):
        _mv(u["id"], ft)
    _mv(target["id"], T)                                    # SEULE la cible bouge ; Celestine reste au spawn

    # (b1) Celestine NON bougee -> castable
    fh1 = _fromhere(cel["id"])
    assert target["id"] in fh1, f"Celestine NON bougee devrait pouvoir caster SkyStrike sur {target['id']}: {fh1}"

    # AUCUN cast ici : il consommerait l'action de Celestine et (b2) refuserait pour « a deja agi »
    # au lieu du gate has-not-moved -> assertion vacuous. Le cast live vit dans le test (E), runner dedie.

    # (b2) Celestine BOUGEE (dist 2, non-adjacente) -> NON castable
    d2 = [t for t in walk if hexgeo.distance(board.coord(t), tc) == 2 and t != T
          and board.coord(t) != cel_pos
          and board.coord(t) not in [board.coord(n) for n in board.neighbours(T)]]
    if not d2:
        pytest.skip("pas de tuile dist2 pour deplacer Celestine (b2)")
    dvc = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    cel_c = next((u for u in (dvc.get("units") or []) if u.get("id") == cel["id"] and u.get("alive")), None)
    if cel_c is None:
        pytest.skip("Celestine morte/absente pour (b2)")
    _mv(cel["id"], d2[0])
    fh2 = _fromhere(cel["id"])
    assert target["id"] not in fh2, \
        f"Celestine BOUGEE non-adjacente NE devrait PAS pouvoir caster (gate has-not-moved): {fh2}"


def test_skystrike_cast_live(rpc):
    """(E) LE PORT == LE CAST LIVE, BIT-EXACT (et garde #226 : le cast REUSSIT).

    Runner DEDIE (celui de `sky_state` sert au gate (D) et un cast y consommerait l'action de Celestine).
    Le test tombe -- `ok=False errors=['system error']` -- si le seed BC injecte reperd ses configs
    d'ability (`BC.Abilities`), c'est-a-dire si quelqu'un re-clone un bloc `Units` a la main au lieu
    d'appeler `catalog_inject.write_augmented_seed_bc`.

    #226-r : la divergence « coups live INEGAUX vs port PLAT » est TRANCHEE. Le noeud
    `Sum(NormalAttackDamage(caster), Direct(extraDmg))` n'est pas degenere du point de vue du PIPELINE :
    le 8e argument natif d'`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` pose l'OCTET +6
    du `Nullable<AttackDamageBehaviourOptions>` a **1** -- le meme octet que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`
    renseigne depuis un getter de l'ability pour l'attaque NORMALE (drapeau « calcul de degat d'ARME ») ;
    `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64` etale alors les bornes de
    +-`DamageSpreadPercentage` autour de V = Attack + extraDmg, REDUIT, puis tire (1 tirage/coup).
    Le port rejoue donc ICI la MEME sequence sous le rng dumpe AVANT le cast et doit rendre les MEMES
    valeurs, coup par coup. (Contre-modeles refutes, `probe_226r_skystrike_spread.py` : bornes degenerees
    (V,V) -> coups tous egaux ; bornes brutes roll-then-reduce -> 2 tirages/coup, diverge des le 2e coup,
    et des le 1er contre une cible armuree.)"""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.abilities.sisterhood import SkyStrikeAbility

    tag = uuid.uuid4().hex[:8]
    bc_file = _write_injected_seed_bc(tag)
    if bc_file is None:
        pytest.skip("seed BC de reference absent (data/seed-bc.json)")
    state_file = ROOT / "logs" / "runners" / f"sky-cast-{tag}.json"
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(state_file),
         "--seed-bc", str(bc_file), "--board", "MC1_67", "--roster", "1",
         "--p-units", CASTER_VIS, "--a-units", A_UNITS, "--hp-target", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    rid = None
    try:
        if not state_file.exists():
            pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
        rid = json.loads(state_file.read_text())["runnerId"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        cel = next((u for u in units if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        if cel is None:
            pytest.skip("Celestine absente du build (injection KO)")
        if dv.get("currentPlayer") != cel.get("owner"):
            pytest.skip("le tour n'est pas au camp de Celestine")
        target = next((u for u in units if u.get("owner") != cel.get("owner") and u.get("alive")), None)
        if target is None:
            pytest.skip("aucun ennemi")
        # cible COLLEE a Celestine : gate `Not(IsAdjacent)` faux -> aucun move, on isole l'ATTAQUE.
        cp = cel.get("pos") or {}
        occ = {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
               for u in units if u.get("alive")}
        here = board.id_at(cp.get("col"), cp.get("row"))
        dest = next((n for n in board.neighbours(here)
                     if board.walkable(n) and board.coord(n) not in occ), None)
        if dest is None:
            pytest.skip("aucune tuile libre adjacente a Celestine")
        dc = board.coord(dest)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": target["id"], "to": {"col": dc[0], "row": dc[1]}}}, 60)

        # ETAT + RNG capturés JUSTE AVANT le cast -> le port rejouera la MEME sequence.
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cel["id"], "targetId": target["id"], "abilityType": ABILITY},
            "captureEvents": True}, 120)
        errs = [a.get("error") for a in (cast.get("actions") or []) if a.get("error")]
        assert _ok(cast), (
            f"cast LIVE de {ABILITY} KO: errs={errs}. 'system error' = faute d'invoke il2cpp -- le seed BC "
            f"injecte n'embarque probablement plus les configs d'ability (cf. #226 / "
            f"catalog_inject.write_augmented_seed_bc)")
        hits = []
        for act in (cast.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "Amount" in td and td.get("Active_Ability_Type") == ABILITY \
                        and td.get("Target_Id") == target["id"]:
                    hits.append(td.get("Amount"))
        assert hits, f"cast ok mais aucun coup capture sur la cible: {cast.get('actions')}"
        want_hits = next((int(w["hits"]) for w in (GC.unit(CASTER_VIS) or {}).get("weapons") or []
                          if w.get("Range") is None), None)
        assert want_hits, f"oracle introuvable : gameconfig.unit('{CASTER_VIS}').weapons[melee].hits"
        assert len(hits) == want_hits, \
            f"cast LIVE : {len(hits)} coups {hits} != MeleeWeaponHits gameconfig {want_hits}"

        # --- LE PORT, REJOUE SUR L'ETAT PRE-CAST AVEC LE MEME RNG, DOIT RENDRE LES MEMES COUPS ---
        st = load_state(dv0, ob0, snap0, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"]); r.mti = rng0["mti"]
            st.rng = r
        else:
            pytest.skip("dumpRng indisponible (rejeu bit-exact impossible)")
        cel_off = _find_by_vis(st, CASTER_VIS)
        tgt_off = target["id"] if st.get_entity(target["id"]) is not None else None
        if cel_off is None or tgt_off is None:
            pytest.skip("etat offline incomplet (caster/cible absents du snapshot)")
        res = SkyStrikeAbility().execute_behaviour(st, cel_off, tgt_off)
        port_hits = ((res or {}).get("attack") or {}).get("attack", {}).get("per_hit")
        assert port_hits == hits, (
            f"per-hit du PORT {port_hits} != cast LIVE {hits} (V = Attack + extraDmg ; le noeud "
            f"`Sum(NormalAttackDamage, Direct(extraDmg))` suit le pipeline d'ARME : bornes V+-20 % "
            f"REDUITES puis 1 tirage/coup -- cf. l'octet +6 des AttackDamageBehaviourOptions, #226-r)")
        print(f"[sky-cast] cast LIVE OK hits={hits} (MeleeWeaponHits={want_hits}) == port BIT-EXACT")
    finally:
        if rid is not None:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass
        for p in (state_file, bc_file):
            try:
                p.unlink()
            except Exception:
                pass
