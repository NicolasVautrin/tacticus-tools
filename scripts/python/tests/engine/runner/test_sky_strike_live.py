"""SkyStrike (actif 1025, adeptCelestine = Celestine, Sisterhood) PORT -> arbre DSL charge+attaque, confronte
au LIVE.

`SkyStrikeAbility$$ExecuteBehaviour @181207d30` (DECOMPILE, mirror 1:1 -- cf. `abilities/sisterhood.py`) =
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
  - ATTACK = overload `AttackWithAttackDamage @180dea6b0` (VERIFIE list_xrefs : call-site @1812080b2 ; ABSENT
    de @180de9fb0) = MEME AttackDamageBehaviour, famille "attack". Node de degat = `Sum(StatAmount(Attack),
    Direct(extraDmg))` : `StatAmountFormula.Calculate @180f22d40` = UNE valeur -> HitDamage(V,V) DEGENERE ->
    AUCUN spread +/-20% (le +/-20% de l'attaque normale vient du weapon-path GetBaseDamageFix64, ABSENT du path
    ability). Chaque coup = reduce(V) FIXE, V = Attack + extraDmg. Profil/coups = arme MELEE (Celestine = Power
    / 3 coups, MeleeWeaponHits = WeaponHitsFormula @180f2f510, SANS ExtraHits). native_factory="attack" ->
    execute_ability_attack(is_attack_damage_op=True), 1 tirage/coup (node degenere : GetDamage court-circuite + resolve
    slot-8 gaspille, cf. #202).
  - `GetDynamicInvalidTargetReason @1812082a0` (eligibilite, HORS ExecuteBehaviour) : gate DidMove(caster) -> une
    Celestine DEJA bougee ET non-adjacente ne peut PAS caster (reason 0x10). CONFIRME LIVE (b1/b2 ci-dessous).

PORTEUR HORS POOL + RESIDU DE CAST LIVE (documente, idem SavageEchoes) : adeptCelestine est absente du seed BC
capture -> on l'INJECTE (clone d'une unite Sisterhood + `ActiveAbilities=[1025]`). Elle spawne AVEC SkyStrike
reconnue (abilityTargets `fromHere` non-vide quand NON bougee). MAIS le cast LIVE de 1025 ECHOUE
(`AbilityConfiguration.GetVariableForLevel(8=extraDmg)` THROW pour une unite injectee dont l'array n'est pas
materialise -- MEME limite que SavageEchoes ; l'eligibilite passe, l'EXECUTION throw). Le cast live est un RESIDU
documente : on le TENTE (forward-compat) mais on n'ASSERTE rien sur le degat live.

CE QUE LE TEST VALIDE :
  (A) A/B BIT-EXACT (deterministe, etat live-capture) : l'arbre `sky_strike_tree` (attaque) == un appel DIRECT
      `execute_ability_attack(V, V, melee_pierce, MeleeWeaponHits, native_factory=attack)` sous le MEME rng ->
      prouve base=Attack+extraDmg, hits=arme-melee, profil/pierce melee, factory=attack, node DEGENERE (V,V).
  (B) NO-SPREAD : les coups sont TOUS EGAUX (node degenere, PAS de +/-20%) ; nb de coups == MeleeWeaponHits.
  (C) CHARGE : Celestine a dist 2/5 d'une cible non-adjacente -> MOVE sur la tuile libre adjacente la plus proche
      (SANS limite de portee : dist 5 charge AUSSI -- discriminant vs VigilanceEternal reach=2) ; deja-adjacente
      -> AUCUN move.
  (D) GATE has-not-moved (LIVE) : Celestine NON bougee + tuile libre adjacente a la cible -> castable ; Celestine
      BOUGEE + non-adjacente -> NON castable (reason 0x10). Discriminant de `GetDynamicInvalidTargetReason`.

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only. Skip si build/injection/geometrie/adeptCelestine indispo.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                     # racine repo
CASTER_VIS = "adeptCelestine"
CLONE_BASE = "adeptCanoness"                                # unite Sisterhood du seed BC a cloner
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
    """Injecte `adeptCelestine` (clone d'une unite Sisterhood du seed BC, `ActiveAbilities=[1025]`,
    `PassiveAbilities=[]`) dans une COPIE du seed BC. N'ecrit JAMAIS le seed partage. None si pas de base."""
    from rl_collect_batch import _load_seed_bc
    seed = _load_seed_bc()
    units = seed.get("Units") or []
    base = next((u for u in units if u.get("VisualId") == CLONE_BASE), None)
    if base is None:
        return None
    inj = copy.deepcopy(base)
    inj.update({"Id": CASTER_VIS, "VisualId": CASTER_VIS, "QuestUnitId": CASTER_VIS,
                "ActiveAbilities": [ABILITY], "PassiveAbilities": [],
                "ConfigId": {"PureId": CASTER_VIS, "Rarity": None, "Level": None,
                             "IsBorrowed": False, "IsPvpOpponent": False}})
    p = ROOT / "data" / "rl-state" / f"sky-seedbc-{tag}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**seed, "Units": units + [inj]}), encoding="utf-8")
    return p


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
        pytest.skip("pas d'unite Sisterhood clonable dans le seed BC")
    state_file = ROOT / "data" / "rl-state" / f"sky-test-{tag}.json"
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


def test_skystrike_attack_ab_and_no_spread(sky_state):
    """(A) A/B BIT-EXACT + (B) NO-SPREAD : Celestine adjacente (aucun move) -> l'attaque de l'arbre == un appel
    DIRECT `execute_ability_attack(V, V, melee_pierce, MeleeWeaponHits, native_factory=attack)` (meme rng) ;
    tous les coups EGAUX (node degenere, pas de +/-20%) ; nb de coups == MeleeWeaponHits."""
    from engine.runner.abilities.sisterhood import SkyStrikeAbility
    from engine.runner.operations.damage import AttackDamageOperation
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

    # (B) NO-SPREAD + nb de coups == MeleeWeaponHits
    assert len(tree_ph) == whits, f"nb de coups {len(tree_ph)} != MeleeWeaponHits {whits}"
    assert len(set(tree_ph)) == 1, f"coups NON egaux (spread inattendu, node degenere): {tree_ph}"

    # (A) A/B : sequence directe execute_ability_attack(V, V, wasted) sous le MEME rng
    st_dir = sky_state["build_state"]()
    cel_d, target_d = _setup(st_dir)
    direct = AttackDamageOperation.execute_ability_attack(
        st_dir, cel_d, target_d, V, V, pierce, whits,
        damage_profile=profile, is_melee=True, is_attack_damage_op=True)   # native_factory="attack"
    assert tree_ph == (direct or {}).get("per_hit"), (
        f"arbre per_hit {tree_ph} != sequence directe {(direct or {}).get('per_hit')} "
        f"(la feuille n'appelle pas execute_ability_attack(V,V) fidele)")


def test_skystrike_has_not_moved_gate_live(sky_state, rpc):
    """(D) GATE has-not-moved (LIVE) : `GetDynamicInvalidTargetReason @1812082a0` -> une Celestine NON bougee
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

    # cast LIVE tente (RESIDU documente : out-of-pool extraDmg throw -> souvent ok=False ; non asserte)
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cel["id"], "targetId": target["id"], "abilityType": ABILITY},
        "captureEvents": True}, 120)
    # si le cast a REUSSI (config materialisee), confronter le nb de coups au port ; sinon (residu) skip l'assert.
    if _ok(cast):
        live = {}
        for act in (cast.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                if td:
                    td = json.loads(td) if isinstance(td, str) else td
                    if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                        live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
        if live.get(target["id"]):
            # forward-compat : si un jour le cast passe, tous les coups egaux (no-spread)
            assert len(set(live[target["id"]])) == 1, f"coups live NON egaux (spread ?): {live[target['id']]}"

    # (b2) Celestine BOUGEE (dist 2, non-adjacente) -> NON castable
    d2 = [t for t in walk if hexgeo.distance(board.coord(t), tc) == 2 and t != T
          and board.coord(t) != cel_pos
          and board.coord(t) not in [board.coord(n) for n in board.neighbours(T)]]
    if not d2:
        pytest.skip("pas de tuile dist2 pour deplacer Celestine (b2)")
    # re-lire Celestine (peut avoir bouge/charge si le cast a reussi) ; sinon toujours au spawn
    dvc = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    cel_c = next((u for u in (dvc.get("units") or []) if u.get("id") == cel["id"] and u.get("alive")), None)
    if cel_c is None:
        pytest.skip("Celestine morte/absente pour (b2)")
    _mv(cel["id"], d2[0])
    fh2 = _fromhere(cel["id"])
    assert target["id"] not in fh2, \
        f"Celestine BOUGEE non-adjacente NE devrait PAS pouvoir caster (gate has-not-moved): {fh2}"
