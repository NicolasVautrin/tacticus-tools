"""DestroyerHive (case-220 DG) : passif de deathTyphus -- au debut du tour de Typhus, sa nuee attaque 1x
un ennemi adjacent aleatoire. Agreement LIVE-vs-OFFLINE (template probe_203_livingmetal / test hypersensory).

Artefacts natifs (RE ghidra gqfc5mff6c, VAs) :
  - IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateTrigger : `On(0x16 TurnStart_Actions) & @0xa0(OwnerIsActor)
      & AmountIsGreaterThanZero(GetValidTargets)`.
  - IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets : `Damageable(Enemies(AdjacentUnits(caster, 1)))`.
  - IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateBehaviour : `AttackWithAttackDamage(caster, PickRandomly(GetValidTargets, 1),
      MinMaxDamage(minDmg 0xc/maxDmg 0xd)[passive lvl], GetDamageProfile(0)=DirectDamage(pierce-100),
      nrOfHits=GetNumberConstant(0x2f)=1, alwaysOverkilled=Nullable(HasValue=0))`. Factory "attack"
      IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage (XREF du call-site IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateBehaviour+0x15e ; is_attack_damage_op=True), pas de force_overkill.
  - `PickRandomly(.,1)` IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select tire `NextInternal(0,count)` UNE fois -- consomme 1 genrand MEME a
      count==1 (branche puissance-de-2 IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal) -> la pick precede l'attaque, load-bearing pour la
      bit-exactness (prouve : le port bit-exact 3 seeds ; no-draw diverge).

VALIDATION : P=deathTyphus, A=ennemi high-HP (--hp-target -> survit + armure 0). On DRIVE l'ennemi adjacent
a Typhus, on flip au tour de Typhus (endturn A->P => StartTurnOperation On(0x16) => DestroyerHive). Verifie :
  (A) le passif enregistre le trigger DestroyerHive sur Typhus (collect_triggered_abilities, event_id 22) ;
  (B) BIT-EXACT : offline start_turn_triggers(P) total == live_dmg (HP delta) ;
  (C) STRUCTURE : nb de coups + percage lus de la CONFIG (cf. ORACLE), cible = l'ennemi adjacent ;
  (D) SCOPING : offline start_turn(A=tour adverse) ne fire PAS (gate OwnerIsActor) ;
  (E) GATE : ennemi rendu NON adjacent (offline) => DestroyerHive ne fire pas (AmountIsGreaterThanZero=0).

ORACLE (#96) -- le degat resolu est CALCULE, donc confronte au LIVE (volet B) ; les deux scalaires de
STRUCTURE (volet C) sont BRUTS, donc confrontes a la CONFIG. Le decompile tranche :
`DestroyerHiveAbility$$CreateBehaviour` lit `GetDamageProfile(config, 0)` et `GetNumberConstant(config,
0x2f)` et passe les DEUX **tels quels** a `AttackWithAttackDamage` -- aucune formule entre la config et le
noeud. Donc `constants.nrOfHits` et `damageProfiles[constants.damageProfile].PiercingRatio` (0x2f =
`nrOfHits`, indices resolus sur `IdunBattle.Configuration.AbilityConstantType`). Aucun de ces deux nombres
n'est ecrit en dur ici : un re-equilibrage deplace l'attendu AVEC le jeu.
ASCII-only. Skip si pas de session / Typhus non buildable.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import (assert_ability_damage_profile,     # noqa: E402
                            damage_profile_pierce)

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
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    from engine.runner.operations.triggers.loki.destroyer_hive import DestroyerHiveAbility
    state = dh_state["build_state"]()
    mine = [t for t in collect_triggered_abilities(state)
            if isinstance(t, DestroyerHiveAbility) and t.owner_id == dh_state["tid"]]
    assert len(mine) == 1, "Typhus doit porter exactement 1 trigger DestroyerHive"
    # #283 : etait `== 22`, l'ordinal en dur (juste aujourd'hui, muet au prochain build).
    from engine.dsl.event_trigger_type import EventTriggerType
    assert mine[0].event_id == EventTriggerType.TurnStart_Actions, \
        "le trigger ecoute On(TurnStart_Actions)"


def _fire_offline(dh_state, player):
    from engine.runner.operations.triggers.dispatch.turn import start_turn_triggers
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
    """(C) STRUCTURE : nb de coups == `constants.nrOfHits`, percage == `PiercingRatio` du profil NOMME PAR
    LA CONFIG, cible = l'ennemi adjacent.

    ORACLE = gameconfig (cf. en-tete). `CreateBehaviour` prend les deux scalaires TELS QUELS
    (`GetNumberConstant(0x2f)`, `GetDamageProfile(0)`) -> BRUTS -> l'oracle est la config, jamais un
    litteral. Le percage EFFECTIF du port est `clamp(0,100, PiercingRatio + ExtraPierce + ExtraPierceMelee)`
    (`profile_pierce`) : on exige d'abord que le porteur n'ait AUCUN percage supplementaire, sans quoi
    l'egalite ne testerait plus le choix du PROFIL mais la somme."""
    import gameconfig as GC
    from engine.runner.components import StatsComponent
    cst = (GC.ability("DestroyerHive") or {}).get("constants") or {}
    n_hits, prof = cst.get("nrOfHits"), cst.get("damageProfile")
    assert n_hits is not None and prof, \
        f"oracle introuvable : constants.nrOfHits/damageProfile de l'ability DestroyerHive (lu: {cst})"
    ratio = damage_profile_pierce(prof)      # ECHOUE sur cle absente (jamais un None qui passe en 0)
    ctx = dh_state["build_state"]().get_entity(dh_state["tid"]).get_component(StatsComponent).ctx
    assert (ctx.extra_pierce, ctx.extra_pierce_melee) == (0, 0), (
        f"le porteur a un percage supplementaire ({ctx.extra_pierce}/{ctx.extra_pierce_melee}) : le percage "
        f"effectif n'est plus l'identite du PiercingRatio de profil -- adapter le setup ou l'attendu")
    off = _fire_offline(dh_state, dh_state["p_team"])
    assert off is not None
    # `assert_ability_damage_profile` epingle le nom de profil LU EN CONFIG a celui du decompile
    # (`DestroyerHiveAbility$$CreateBehaviour` -> `AbilityConfiguration$$GetDamageProfile`) : sans lui, un
    # profil renomme en config deplacerait silencieusement l'attendu avec lui.
    assert_ability_damage_profile("DestroyerHive", "DirectDamage")
    assert off.get("hits") == int(n_hits), \
        f"coups {off.get('hits')} != constants.nrOfHits={n_hits} (oracle gameconfig, GetNumberConstant 0x2f)"
    assert off.get("pierce") == int(ratio), (
        f"pierce {off.get('pierce')} != damageProfiles[{prof}].PiercingRatio={ratio} (oracle gameconfig, "
        f"profil lu par GetDamageProfile(config, 0))")
    assert off.get("target") == dh_state["eid"], "cible = l'unique ennemi adjacent"


def test_dh_hits_derived_from_config(dh_state, monkeypatch):
    """DERIVATION du nb de coups : on DECALE `constants.nrOfHits` et le port doit SUIVRE.

    Sans ce controle, l'egalite du test precedent ne prouverait rien : `nrOfHits` vaut 1, exactement la
    valeur de repli du lecteur (`ability_var(..., is_constant=True) or 1`) -- une cle MAL nommee rendrait
    donc 1 elle aussi et passerait inapercue. C'est le piege " cle voisine de meme valeur " (#96). L'etat
    est reconstruit a neuf par `_fire_offline` (payloads deja en cache) : aucun RPC, aucun runner de plus."""
    import gameconfig as GC
    cst = (GC.ability("DestroyerHive") or {}).get("constants") or {}
    base = int(cst["nrOfHits"])
    bumped = base + 2
    orig_ability = GC.ability
    patched = dict(orig_ability("DestroyerHive") or {})
    patched["constants"] = {**cst, "nrOfHits": str(bumped)}
    monkeypatch.setattr(GC, "ability", lambda aid: patched if aid == "DestroyerHive" else orig_ability(aid))
    off = _fire_offline(dh_state, dh_state["p_team"])
    assert off is not None, "DestroyerHive doit fire (ennemi adjacent)"
    assert off.get("hits") == bumped, (
        f"coups {off.get('hits')} != oracle decale {bumped} (base {base}) : le port ne DERIVE pas de "
        f"constants.nrOfHits -- cle mal nommee retombant sur le repli 1, ou valeur figee")
    assert len(((off.get("attack") or {}).get("per_hit")) or []) == bumped, \
        "le nb de coups REELLEMENT joues ne suit pas non plus l'oracle"


def test_dh_scoping_owner_turn(dh_state):
    """(D) SCOPING (OwnerIsActor @0xa0) : au tour ADVERSE (A), DestroyerHive de Typhus (P) ne fire PAS."""
    off = _fire_offline(dh_state, dh_state["a_team"])
    assert off is None, "DestroyerHive ne doit PAS fire au tour adverse"


def test_dh_gate_no_adjacent(dh_state):
    """(E) GATE AmountIsGreaterThanZero(GetValidTargets) : ennemi rendu NON adjacent -> pas de fire."""
    from engine.runner.operations.triggers.dispatch.turn import start_turn_triggers
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
