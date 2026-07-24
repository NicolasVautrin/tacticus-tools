"""DestroyerHive (case-220 DG) : passif de deathTyphus -- au debut du tour de Typhus, sa nuee attaque 1x
un ennemi adjacent aleatoire. Agreement LIVE-vs-OFFLINE (template probe_203_livingmetal / test hypersensory).

Artefacts natifs (RE ghidra gqfc5mff6c, VAs) :
  - CreateTrigger @18121d4b0 : `On(0x16 TurnStart_Actions) & @0xa0(OwnerIsActor)
      & AmountIsGreaterThanZero(GetValidTargets)`.
  - GetValidTargets @18121d540 : `Damageable(Enemies(AdjacentUnits(caster, 1)))`.
  - CreateBehaviour @18121d320 : `AttackWithAttackDamage(caster, PickRandomly(GetValidTargets, 1),
      MinMaxDamage(minDmg 0xc/maxDmg 0xd)[passive lvl], GetDamageProfile(0)=DirectDamage(pierce-100),
      nrOfHits=GetNumberConstant(0x2f)=1, alwaysOverkilled=Nullable(HasValue=0))`. Factory "attack"
      @180de9fb0 (XREF du call-site @18121d47e ; is_attack_damage_op=True), pas de force_overkill.
  - `PickRandomly(.,1)` @180ef0be0 tire `NextInternal(0,count)` UNE fois -- consomme 1 genrand MEME a
      count==1 (branche puissance-de-2 @180e39be0) -> la pick precede l'attaque, load-bearing pour la
      bit-exactness (prouve : le port bit-exact 3 seeds ; no-draw diverge).

VALIDATION : P=deathTyphus, A=ennemi high-HP (--hp-target -> survit + armure 0). On DRIVE l'ennemi adjacent
a Typhus, on flip au tour de Typhus (endturn A->P => StartTurnOperation On(0x16) => DestroyerHive). Verifie :
  (A) le passif enregistre le trigger DestroyerHive sur Typhus (collect_triggered_abilities, event_id 22) ;
  (B) BIT-EXACT : offline start_turn_triggers(P) total == live_dmg (HP delta) ;
  (C) STRUCTURE : 1 coup, pierce 100, cible = l'ennemi adjacent ;
  (D) SCOPING : offline start_turn(A=tour adverse) ne fire PAS (gate OwnerIsActor) ;
  (E) GATE : ennemi rendu NON adjacent (offline) => DestroyerHive ne fire pas (AmountIsGreaterThanZero=0).
ASCII-only. Skip si pas de session / Typhus non buildable.
"""
from __future__ import annotations

import pytest

TYPHUS_VIS = "deathTyphus"
ENEMY_VIS = "necroWarden"
BUILD = ["--p-units", TYPHUS_VIS, "--a-units", ENEMY_VIS, "--hp-target", "60000"]


def _find_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis and uc.alive:
            return uid
    return None


@pytest.fixture(scope="session")
def dh_state(rpc, build_runner):
    """Build deathTyphus (P) + necroWarden (A, hp 60000), DRIVE l'ennemi adjacent a Typhus, capture S au
    tour ENNEMI, puis LIVE endturn (A->P) => DestroyerHive attaque. Renvoie de quoi rejouer offline + le
    live_dmg mesure. destructif -> scope session (une seule fois)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister

    rid = build_runner("777", extra=BUILD)["rid"]

    def dv(all_ab=False, mr=1):
        b = {"runnerId": rid, "maxRank": mr}
        if all_ab:
            b["allAbilities"] = True
        return rpc("decisionView", b, 150 if all_ab else 60)

    def cp():
        return dv().get("currentPlayer")

    def alive_units():
        return [u for u in (dv().get("units") or []) if u.get("alive")]

    def enemy_hp(eid):
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        for u in (snap.get("units") or []):
            if u.get("entityId") == eid:
                return int((u.get("stats") or {}).get("health") or 0)
        return None

    def endturn():
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)

    def move(uid, col, row):
        rpc("applyAction", {"runnerId": rid,
                            "actions": [{"kind": "move", "unitId": uid, "to": {"col": col, "row": row}}]}, 60)

    al = alive_units()
    ty = next((u for u in al if u.get("visualId") == TYPHUS_VIS), None)
    en = next((u for u in al if u.get("visualId") == ENEMY_VIS), None)
    if not ty or not en:
        pytest.skip("deathTyphus et/ou necroWarden absents du build")
    tid, eid, p_team = ty["id"], en["id"], cp()

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles")
    if not tiles:
        pytest.skip("boardGraph indispo")
    by_id = {t["id"]: t for t in tiles}
    ttile = next((t for t in tiles if t.get("occupantUnitId") == tid), None)
    if ttile is None:
        pytest.skip("tuile de Typhus introuvable")
    dest = None
    for nid in (ttile.get("neighbours") or []):
        nt = by_id.get(nid)
        if nt and nt.get("walkable") and not nt.get("isWall") and nt.get("occupantUnitId") in (None, eid):
            dest = nt
            break
    if dest is None:
        pytest.skip("pas de tuile adjacente libre pour l'ennemi")
    move(eid, dest["col"], dest["row"])
    bg2 = rpc("boardGraph", {"runnerId": rid}, 60)
    et2 = next((t for t in bg2["tiles"] if t.get("occupantUnitId") == eid), None)
    tt2 = next((t for t in bg2["tiles"] if t.get("occupantUnitId") == tid), None)
    if not (et2 and tt2 and et2["id"] in (tt2.get("neighbours") or [])):
        pytest.skip("l'ennemi n'est pas adjacent apres le move")

    cur = cp()
    if cur == p_team:                       # flip au tour ENNEMI (A) avant de mesurer P-turn-start
        endturn()
        cur = cp()

    dec = dv(all_ab=True)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    hp_before = enemy_hp(eid)

    endturn()                                # LIVE : A -> P turn-start -> DestroyerHive
    hp_after = enemy_hp(eid)
    live_dmg = (hp_before - hp_after) if (hp_before is not None and hp_after is not None) else None

    board = Board(tiles, adjacency="evenq")

    def build_state():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"]); r.mti = rng0["mti"]
            st.rng = r
        return st

    return {"build_state": build_state, "tid": tid, "eid": eid, "p_team": p_team,
            "a_team": cur, "live_dmg": live_dmg}


def test_dh_trigger_registered(dh_state):
    """(A) Le passif DestroyerHive enregistre le trigger sur Typhus (voie passiveAbilities du registre)."""
    from engine.runner.operations.triggers.dispatch import collect_triggered_abilities
    from engine.runner.operations.triggers.loki.destroyer_hive import DestroyerHiveAbility
    state = dh_state["build_state"]()
    mine = [t for t in collect_triggered_abilities(state)
            if isinstance(t, DestroyerHiveAbility) and t.owner_id == dh_state["tid"]]
    assert len(mine) == 1, "Typhus doit porter exactement 1 trigger DestroyerHive"
    assert mine[0].event_id == 22, "le trigger ecoute On(0x16=TurnStart_Actions)"


def _fire_offline(dh_state, player):
    from engine.runner.operations.triggers.dispatch import start_turn_triggers
    state = dh_state["build_state"]()
    res = start_turn_triggers(state, player)
    dh = [x for x in res if isinstance(x, dict) and x.get("type") == "destroyer_hive"]
    return dh[0] if dh else None


def test_dh_bit_exact_damage(dh_state):
    """(B) BIT-EXACT : offline start_turn_triggers(P) degat == live_dmg (HP delta mesure). Preuve du
    modele complet (targeting + MinMax[passive lvl] + pierce-100 + factory attack + pick-draw)."""
    if dh_state["live_dmg"] is None:
        pytest.skip("live_dmg non mesurable")
    off = _fire_offline(dh_state, dh_state["p_team"])
    assert off is not None, "DestroyerHive doit fire au tour de Typhus (ennemi adjacent)"
    off_total = (off.get("attack") or {}).get("total")
    assert off_total == dh_state["live_dmg"], \
        f"offline total={off_total} != live_dmg={dh_state['live_dmg']}"


def test_dh_structure(dh_state):
    """(C) STRUCTURE : 1 coup (nrOfHits=1), pierce 100 (DirectDamage), cible = l'ennemi adjacent."""
    off = _fire_offline(dh_state, dh_state["p_team"])
    assert off is not None
    assert off.get("hits") == 1, "nrOfHits=1 (mono-coup)"
    assert off.get("pierce") == 100, "profil DirectDamage pierce-100"
    assert off.get("target") == dh_state["eid"], "cible = l'unique ennemi adjacent"


def test_dh_scoping_owner_turn(dh_state):
    """(D) SCOPING (OwnerIsActor @0xa0) : au tour ADVERSE (A), DestroyerHive de Typhus (P) ne fire PAS."""
    off = _fire_offline(dh_state, dh_state["a_team"])
    assert off is None, "DestroyerHive ne doit PAS fire au tour adverse"


def test_dh_gate_no_adjacent(dh_state):
    """(E) GATE AmountIsGreaterThanZero(GetValidTargets) : ennemi rendu NON adjacent -> pas de fire."""
    from engine.runner.operations.triggers.dispatch import start_turn_triggers
    from engine.runner.components import PositionComponent
    state = dh_state["build_state"]()
    # eloigner l'ennemi de Typhus (offline) : le rendre non adjacent -> GetValidTargets vide.
    board = state.board
    tpc = state.get_entity(dh_state["tid"]).get_component(PositionComponent)
    epc = state.get_entity(dh_state["eid"]).get_component(PositionComponent)
    ttile_id = board.id_at(tpc.col, tpc.row)
    neigh = set(board.neighbours(ttile_id))
    occ = {(p.col, p.row) for p in
           (e.get_component(PositionComponent) for e in state.entities.values()) if p is not None}
    far = None
    for tid_, t in board.by_id.items():                  # tuile libre NON adjacente a Typhus
        if tid_ == ttile_id or tid_ in neigh or not board.walkable(tid_):
            continue
        c = (t["col"], t["row"])
        if c not in occ:
            far = c
            break
    if far is None:
        pytest.skip("aucune tuile non-adjacente libre trouvee")
    epc.col, epc.row = far
    res = start_turn_triggers(state, dh_state["p_team"])
    dh = [x for x in res if isinstance(x, dict) and x.get("type") == "destroyer_hive"]
    assert not dh, "sans ennemi adjacent, DestroyerHive ne doit pas fire"
