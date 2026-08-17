"""Tache #111 -- GATE DE CIBLAGE de Waaagh (1058) : le cast est-il seulement ATTEINT ?

Le symptome rapporte (« Waaagh INERTE en runner isole ») etait une cible ILLEGALE, pas une
ability morte. Ce fichier GARDE le constat, des DEUX cotes, pour qu'aucun probe/test ne
re-conclue « inerte » sur un cast que le moteur refuse en amont.

NATIF (chaine mesuree, decompile = verite) :
  `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
      -> `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`
      -> `IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidTargetReason`
      -> `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetDynamicInvalidTargetReason`
         = `Count( GetPossibleMovementTiles(target) ) > 0`, ou
           `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetPossibleMovementTiles` =
           `IdunBattleLogic.Entities.DSLSelectors$$TilesUnitCanMoveToChargeTarget(caster, casterTile, target,
              UnitMovementRangeWithBonus(caster, 1099, Direct(extraMovement)), canReachOnly=0)`
         => cible LEGALE ssi il existe une tuile LIBRE adjacente a la cible, atteignable par le
            caster en (MOVEMENT + extraMovement) pas. Sinon `ExecuteInternal` rend 0 AVANT le
            premier des cinq `AActiveAbility.Execute` de
            `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour`.

OBSERVABLE du refus (signature a 2 evenements) : le groupe `User_UseAbility` (GroupType 12) est
ouvert par le handler de message EN AMONT du gate, puis referme aussitot -> `events` = [group 12,
finish], `mutated=false`, `actionConsumed=false` (no-op moteur, cf. `ActionResult.actionConsumed`).
AUCUN des cinq groupes d'etage de l'ability (0x22 Summon / 0x25 Stance / 0x23 Move / 0x20 Attack /
0x28) n'apparait.

RECETTE (ce que tout appelant doit faire) : prendre la cible dans `abilityTargets(...).fromHere`
(legalite EXACTE du cast immediat), jamais dans `targets` (superset « ce tour, MOVE inclus »), et
jamais le caster / un allie.

ASCII only. Skip propre si pas de session / geometrie non cooperative.
"""
from __future__ import annotations

import os

import pytest

import hexgeo

CASTER = "orksWarboss"
ALLY = "orksNob"                       # Ork LOIN : buffe par UnitsFromFaction(Orks) board-wide
# 3e unite de MON camp, JAMAIS activee : elle garde le tour OUVERT apres le cast. Les 3 buffs durent
# `Direct(1)` = 1 TOUR ; si le tour bascule, le tick de fin de tour les a deja retires quand on relit
# `decisionView` (piege deja paye sur #95 ; re-paye ici des que l'allie doit etre deplace).
SPARE = "spaceHound"
FOES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt"
WAAAGH = 1058
WAAAGH_EFFECTS = {"Waaagh_ExtraMovement", "Waaagh_ExtraDamage", "Waaagh_ExtraHits"}
# Les 5 groupes d'etage de `WaaaghAbility$$ExecuteBehaviour` (`DSLFactory.Group(<b>, caster, <id>)`).
STAGE_SUMMON, STAGE_STANCE = 0x22, 0x25          # Spawn Ork Boyz / pose des 3 buffs
GROUP_USE_ABILITY = 12                           # GroupType.User_UseAbility (enum_maps)
# Board/seed OVERRIDABLES : le critere pass/fail n'en depend pas (on pilote les positions).
BOARD = os.environ.get("WAAAGH111_BOARD", "MC1_67")
SEED = os.environ.get("WAAAGH111_SEED", "777")


def _upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _groups(action_result):
    return {e.get("group") for e in (action_result.get("events") or [])
            if e.get("kind") == "group"}


@pytest.fixture(scope="module")
def waaagh_gate(rpc, build_runner):
    """Amene le Warboss a portee de CHARGE d'un ennemi, puis caste QUATRE fois la MEME ability
    depuis le MEME etat, en ne changeant QUE la cible (A self / B allie / C ennemi hors gate /
    D ennemi offert). Seul D est cense muter -> il est joue en DERNIER."""
    from engine.entities.pathfinding.board import Board

    rid = build_runner(SEED, extra=["--p-units", f"{CASTER},{ALLY},{SPARE}", "--a-units", FOES,
                                    "--board", BOARD])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    def dv():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    def find(d, vis):
        return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)

    def offered(uid):
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": uid, "allAbilities": True}, 90)
        return [t for u in (at.get("units") or []) if u.get("unitId") == uid
                for a in (u.get("abilities") or []) if a.get("abilityId") == WAAAGH
                for t in (a.get("fromHere") or []) if t.get("kind") == "unit"]

    def cast(caster_id, target_id):
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster_id, "targetId": target_id,
            "abilityType": WAAAGH}}, 150)
        return ((r or {}).get("actions") or [{}])[0]

    # --- approche : avancer le Warboss vers l'ennemi le plus proche jusqu'a ce que le gate ouvre.
    legal = []
    for _ in range(14):
        d = dv()
        wb = find(d, CASTER)
        if wb is None or not wb.get("alive"):
            pytest.skip("Warboss absent/mort pendant l'approche")
        if d.get("currentPlayer") != wb.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        legal = offered(wb["id"])
        if legal:
            break
        foes = [u for u in (d.get("units") or [])
                if u.get("owner") != wb.get("owner") and u.get("alive")]
        if not foes:
            pytest.skip("plus d'ennemi vivant")
        goal = min(foes, key=lambda e: hexgeo.distance(_upos(wb), _upos(e)))
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == wb["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((mu or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            best = min(tiles, key=lambda t: (hexgeo.distance(t, _upos(goal)), t))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": wb["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    if not legal:
        pytest.skip("aucune cible legale de Waaagh atteinte (geometrie)")

    # L'allie Ork doit etre a >1 hex du Warboss, sinon `AdjacentFriends(caster, 1)` suffirait a
    # expliquer son buff et le sELecteur board-wide `UnitsFromFaction(..., Orks)` ne serait plus
    # teste. Selon le board, les spawns le collent au Warboss (mesure : C2_19/4242, distance 1) ->
    # on le DEPLACE au lieu de skipper sur la geometrie.
    d0 = dv()
    wb, ally = find(d0, CASTER), find(d0, ALLY)
    if ally is None or not ally.get("alive"):
        pytest.skip("allie Ork absent/mort")
    if hexgeo.distance(_upos(wb), _upos(ally)) <= 1:
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == ally["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((mu or {}).get("tiles") or [])
                 if t.get("col") is not None and hexgeo.distance((t["col"], t["row"]),
                                                                 _upos(wb)) > 1]
        if not tiles:
            pytest.skip("allie Ork ne peut pas s'eloigner du Warboss (aucune tuile a >1 hex)")
        best = max(tiles, key=lambda t: (hexgeo.distance(t, _upos(wb)), t))
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": ally["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
        d0 = dv()
        wb, ally = find(d0, CASTER), find(d0, ALLY)
        if ally is None or not ally.get("alive"):
            pytest.skip("allie Ork perdu apres deplacement")
        # le deplacement de l'allie peut changer les tuiles libres autour des cibles -> on relit
        legal = offered(wb["id"]) or legal
    legal_ids = {t["targetId"] for t in legal}
    foes = [u for u in (d0.get("units") or [])
            if u.get("owner") != wb.get("owner") and u.get("alive")]
    far = next((e for e in foes if e["id"] not in legal_ids), None)

    out = {"rid": rid, "board": board, "wb": wb, "ally": ally,
           "ally_dist": hexgeo.distance(_upos(wb), _upos(ally)),
           "ids_before": {u["id"] for u in (d0.get("units") or [])},
           "legal_ids": sorted(legal_ids),
           "self": cast(wb["id"], wb["id"]),
           "ally_cast": cast(wb["id"], ally["id"]),
           "far": cast(wb["id"], far["id"]) if far is not None else None}
    out["legal"] = cast(wb["id"], sorted(legal_ids)[0])
    out["dv1"] = dv()
    return out


# ================================================================================================ #
# FACE « REFUS » -- cible illegale => NO-OP moteur en amont de tout etage de pose
# ================================================================================================ #

@pytest.mark.parametrize("key,label", [("self", "le CASTER lui-meme"),
                                       ("ally_cast", "un ALLIE"),
                                       ("far", "un ENNEMI hors portee de charge")])
def test_illegal_target_is_a_silent_engine_noop(waaagh_gate, key, label):
    """`ActiveAbilityOperation.ExecuteInternal` sort a `IsInvalidTarget` : le cast rend `ok=true`
    (le message a bien ete applique) mais ne mute RIEN et ne consomme PAS l'activation. C'est LA
    signature qui avait ete lue comme « ability inerte »."""
    a = waaagh_gate[key]
    if a is None:
        pytest.skip("pas d'ennemi hors du gate dans cette geometrie")
    assert a.get("ok") is True, f"cast sur {label} : le message n'a meme pas ete applique"
    assert a.get("mutated") is False, f"cast sur {label} a mute l'etat (attendu : refus)"
    assert a.get("actionConsumed") is False, (
        f"cast sur {label} a consomme l'activation (attendu : no-op moteur)")


def test_illegal_target_emits_no_ability_stage_group(waaagh_gate):
    """Le refus est en AMONT des cinq `AActiveAbility.Execute` : la trace ne contient que le groupe
    `User_UseAbility` ouvert par le handler de message (+ son finish), aucun groupe d'etage."""
    a = waaagh_gate["self"]
    g = _groups(a)
    assert g == {GROUP_USE_ABILITY}, (
        f"groupes {sorted(g)} != {{{GROUP_USE_ABILITY}}} -- un etage de l'ability s'est execute")
    assert a.get("eventCount") == 2, (
        f"eventCount={a.get('eventCount')} (attendu 2 : group User_UseAbility + finish)")


# ================================================================================================ #
# FACE « EXECUTION » -- cible legale => les etages de pose sont ATTEINTS et la pose SURVIT
# ================================================================================================ #

def test_legal_target_executes_the_full_behaviour(waaagh_gate):
    """Cible prise dans `abilityTargets(...).fromHere` : le cast mute, consomme l'activation, spawne
    les Ork Boyz, et la trace porte les groupes d'etage Spawn (0x22) et Buff (0x25) de
    `WaaaghAbility$$ExecuteBehaviour`."""
    a = waaagh_gate["legal"]
    assert a.get("ok") is True and a.get("mutated") is True, (
        f"cast legal non mute : error={a.get('error')}")
    assert a.get("actionConsumed") is True, "cast legal sans consommation d'activation"
    assert (a.get("spawned") or 0) >= 1, "cast legal : aucun Ork Boy invoque (etage Spawn)"
    g = _groups(a)
    assert {STAGE_SUMMON, STAGE_STANCE} <= g, (
        f"groupes d'etage manquants : {sorted(g)} ne couvre pas "
        f"{{{STAGE_SUMMON}, {STAGE_STANCE}}}")


def test_legal_target_posts_the_three_buffs(waaagh_gate):
    """La pose SURVIT et est LISIBLE : les 3 effets (1099/1100/1101) sont sur le caster ET sur
    l'allie Ork LOIN (selecteur `UnitsFromFaction(Friends(caster, allUnits), 5=Orks)` board-wide,
    aucun rayon) ET sur les Ork Boyz invoques au 1er etage."""
    d = waaagh_gate
    assert d["ally_dist"] > 1, (
        f"l'allie Ork est a {d['ally_dist']} hex du Warboss -- le buff pourrait venir de "
        f"AdjacentFriends, ce n'est pas un test du selecteur board-wide")
    units = {u["id"]: u for u in (d["dv1"].get("units") or [])}

    def eff(uid):
        return {e.get("name") for e in (units.get(uid) or {}).get("effects") or []}

    assert WAAAGH_EFFECTS <= eff(d["wb"]["id"]), (
        f"caster : {sorted(eff(d['wb']['id']))} ne couvre pas {sorted(WAAAGH_EFFECTS)}")
    assert WAAAGH_EFFECTS <= eff(d["ally"]["id"]), (
        f"allie Ork loin ({d['ally_dist']} hex) : {sorted(eff(d['ally']['id']))} "
        f"ne couvre pas {sorted(WAAAGH_EFFECTS)}")
    # Les summons = les entites APPARUES pendant le cast (etage Spawn), pas « tout ce qui n'est ni le
    # caster ni l'allie » : la 3e unite de mon camp pourrait se trouver dans l'anneau du Warboss et
    # etre buffee par `AdjacentFriends` -> l'assertion passerait pour la mauvaise raison.
    summons = [u for u in units.values()
               if u.get("alive") and u["id"] not in d["ids_before"]
               and WAAAGH_EFFECTS <= {e.get("name") for e in (u.get("effects") or [])}]
    assert summons, "aucun Ork Boy invoque ne porte les 3 buffs (etage Spawn avant etage Buff)"
