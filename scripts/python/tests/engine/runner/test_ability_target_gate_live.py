"""Tache #115 -- GATE DE CIBLE d'une ability active, cote MOTEUR OFFLINE.

Le port ne mirrorait d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` que le gate
ACTEUR-MORT (#70) : un cast que le natif REFUSE executait quand meme sa behaviour offline. Ce
fichier GARDE le gate porte (`engine/runner/abilities/targeting.py`), des DEUX cotes :

  * REFUS : le moteur offline refuse EXACTEMENT les cibles que le natif refuse, et pour la BONNE
    raison (`TargetingRule`) -- filtre STATIQUE des `TargetingOptions` du ctor (cible non ennemie)
    vs regle DYNAMIQUE de l'ability (`GetDynamicInvalidTargetReason`). #111 avait mesure que ces
    DEUX rejets partagent la meme observable live a 2 evenements ; c'est le code de raison qui les
    distingue, donc c'est LUI qu'on assert.
  * EXECUTION : une cible LEGALE traverse le gate et la behaviour s'execute integralement (le gate
    ne doit RIEN retirer a un cast legal -- non-regression).

ORACLE = le LIVE, et pas seulement un booleen : `abilityReason(casterId, abilityType, targetId)`
rend le masque `TargetingRule` NATIF (`targetReason.hex` + les noms de flags). L'agrement est teste
sur TOUTES les unites vivantes du plateau, avec le CONTRAT DE FIDELITE du port :

    natif == 0        =>  port == 0            (STRICT : le port n'invente aucun refus)
    natif != 0        =>  port == natif        (regle PORTEE)
                      ou  port == 0            (regle NON PORTEE -> permissif, cf. targeting.py)
    jamais            :   port != 0 et port != natif  (refus pour la MAUVAISE raison)

`abilityTargets(...).fromHere` ne sert plus qu'a CHOISIR une cible legale pour la face execution.

PORTEUR : Waaagh (1058, `orksWarboss`, HERO -> `--list-pool`) = 1re instanciation du patron
`GetDynamicInvalidTargetReason`, seul cas dont le decompile ET la mesure sont etablis (#111).

ASCII only. Skip propre si pas de session / geometrie non cooperative.
"""
from __future__ import annotations

import os

import pytest

import hexgeo

from engine.entities.pathfinding.board import Board
from engine.runner.abilities.handler import ABILITY_CLASSES, AbilityHandler
from engine.runner.abilities.targeting import is_invalid_target
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.snapshot import load_state

CASTER = "orksWarboss"
ALLY = "orksNob"
SPARE = "spaceHound"                      # 3e unite : garde le tour OUVERT apres les casts
FOES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt"
WAAAGH = 1058
GROUP_USE_ABILITY = 12                    # GroupType.User_UseAbility (enum_maps)
BOARD = os.environ.get("GATE115_BOARD", "MC1_67")
SEED = os.environ.get("GATE115_SEED", "777")


def _upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _groups(action_result):
    return {e.get("group") for e in (action_result.get("events") or [])
            if e.get("kind") == "group"}


@pytest.fixture(scope="module")
def gate115(rpc, build_runner):
    """Amene le Warboss a portee de CHARGE (le gate dynamique de Waaagh s'ouvre), FIGE l'etat
    (dec/ob/snap pre-cast, rejouable offline autant de fois qu'on veut), lit l'oracle natif
    (`fromHere`) puis joue les casts live -- les refus d'abord, le cast legal en DERNIER (seul a
    muter)."""
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
        """Oracle natif : ids offerts par `abilityTargets(...).fromHere` pour 1058 (legalite du cast
        IMMEDIAT, position figee) = exactement ce que `IsInvalidTarget` laisse passer."""
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": uid, "allAbilities": True}, 90)
        return {t.get("targetId") for u in (at.get("units") or []) if u.get("unitId") == uid
                for a in (u.get("abilities") or []) if a.get("abilityId") == WAAAGH
                for t in (a.get("fromHere") or []) if t.get("kind") == "unit"}

    def cast(caster_id, target_id):
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster_id, "targetId": target_id,
            "abilityType": WAAAGH}}, 150)
        return ((r or {}).get("actions") or [{}])[0]

    # --- approche : avancer le Warboss jusqu'a ce que le gate dynamique s'ouvre (cf. #111).
    legal: set = set()
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

    # --- etat FIGE, pre-cast : c'est CE snapshot que le moteur offline rejouera pour chaque cible.
    d0 = dv()
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    wb, ally = find(d0, CASTER), find(d0, ALLY)
    if wb is None or ally is None or not ally.get("alive"):
        pytest.skip("caster/allie absent apres l'approche")
    alive_ids = [u["id"] for u in (d0.get("units") or []) if u.get("alive")]
    foes = [u for u in (d0.get("units") or [])
            if u.get("owner") != wb.get("owner") and u.get("alive")]
    far = next((e for e in foes if e["id"] not in legal), None)

    # ORACLE de RAISON, par cible, sur l'etat FIGE : `abilityReason` rend le masque `TargetingRule`
    # natif (`targetReason.hex`) -- c'est lui qui distingue refus STATIQUE et refus DYNAMIQUE, que
    # l'observable live a 2 evenements confond (#111).
    native = {}
    for uid in alive_ids:
        r = rpc("abilityReason", {"runnerId": rid, "casterId": wb["id"],
                                  "abilityType": WAAAGH, "targetId": uid}, 60) or {}
        native[uid] = {
            "target_hex": int(((r.get("targetReason") or {}).get("hex") or "0x0"), 16),
            "target_names": list((r.get("targetReason") or {}).get("reasons") or []),
            "caster_hex": int(((r.get("casterReason") or {}).get("hex") or "0x0"), 16)}

    out = {"rid": rid, "board": board, "dec0": d0, "ob0": ob0, "snap0": snap0,
           "caster_id": wb["id"], "ally_id": ally["id"], "alive_ids": alive_ids,
           "legal_ids": legal, "far_id": (far or {}).get("id"), "native": native,
           "self_cast": cast(wb["id"], wb["id"]),
           "ally_cast": cast(wb["id"], ally["id"])}
    out["far_cast"] = cast(wb["id"], far["id"]) if far is not None else None
    out["legal_cast"] = cast(wb["id"], sorted(legal)[0])       # DERNIER : le seul qui mute
    return out


@pytest.fixture(scope="module")
def caster_moved115(rpc, build_runner):
    """Runner DEDIE au volet CASTER : le Warboss atteint une cible legale, PUIS se deplace d'une
    tuile. `abilityReason` doit alors rendre `CasterHasNotMoved` (0x10) sur cette MEME cible."""
    rid = build_runner(SEED, extra=["--p-units", f"{CASTER},{ALLY},{SPARE}", "--a-units", FOES,
                                    "--board", BOARD])["rid"]

    def dv():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    def find(d, vis):
        return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)

    def offered(uid):
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": uid, "allAbilities": True}, 90)
        return {t.get("targetId") for u in (at.get("units") or []) if u.get("unitId") == uid
                for a in (u.get("abilities") or []) if a.get("abilityId") == WAAAGH
                for t in (a.get("fromHere") or []) if t.get("kind") == "unit"}

    legal: set = set()
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

    d0 = dv()
    wb = find(d0, CASTER)
    tgt = sorted(legal)[0]

    def reason():
        r = rpc("abilityReason", {"runnerId": rid, "casterId": wb["id"],
                                  "abilityType": WAAAGH, "targetId": tgt}, 60) or {}
        return int(((r.get("casterReason") or {}).get("hex") or "0x0"), 16)

    before = reason()
    mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
    mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == wb["id"]), None)
    tiles = [(t["col"], t["row"]) for t in ((mu or {}).get("tiles") or [])
             if t.get("col") is not None]
    if not tiles:
        pytest.skip("le Warboss ne peut pas bouger (aucune tuile)")
    dst = min(tiles, key=lambda t: (hexgeo.distance(t, _upos(wb)), t))
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": wb["id"], "to": {"col": dst[0], "row": dst[1]}}}, 60)
    return {"rid": rid, "caster_id": wb["id"], "target_id": tgt,
            "before": before, "after": reason(),
            "dec": dv(), "ob": rpc("observeBattle", {"runnerId": rid}, 40),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
            "bg": rpc("boardGraph", {"runnerId": rid}, 60)}


def _fresh_state(g):
    """Etat offline NEUF depuis le snapshot PRE-CAST (chaque cible repart du meme etat)."""
    return load_state(g["dec0"], g["ob0"], g["snap0"], board=g["board"])


def _offline_gate(g, target_id) -> int:
    """`TargetingRule` que le moteur offline oppose a ce couple (caster, cible) -- 0 = accepte."""
    state = _fresh_state(g)
    return is_invalid_target(state, int(g["caster_id"]), int(target_id),
                             ABILITY_CLASSES[WAAAGH]())


def _offline_cast(g, target_id) -> dict:
    """Rejoue le cast dans le moteur offline (handler complet) -> diagnostic `handler.last`."""
    state = _fresh_state(g)
    h = AbilityHandler(state)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(int(g["caster_id"]), int(target_id), WAAAGH))
    return dict(h.last or {}), state


# ================================================================================================ #
# AGREMENT PORT <-> ORACLE NATIF, sur TOUTES les unites vivantes du plateau
# ================================================================================================ #

def test_gate_never_refuses_what_the_native_accepts(gate115):
    """LA propriete « zero regression » : une regle NON PORTEE est permissive, donc le port ne peut
    JAMAIS refuser une cible que le natif accepte. Verifiee sur toutes les unites vivantes."""
    g = gate115
    bad = [(uid, hex(_offline_gate(g, uid))) for uid in g["alive_ids"]
           if g["native"][uid]["target_hex"] == 0 and _offline_gate(g, uid) != 0]
    assert not bad, f"le port refuse des cibles que le natif ACCEPTE (uid, raison portee) : {bad}"


def test_gate_reason_matches_the_native_reason_on_every_unit(gate115):
    """Contrat de fidelite, cible par cible, contre `abilityReason` (masque `TargetingRule` natif) :
    le port rend soit EXACTEMENT la raison native (regle portee), soit 0 (regle non portee) --
    jamais une AUTRE raison non nulle. Un refus pour la mauvaise raison serait un port faux qui
    passerait un test purement booleen accepte/refuse."""
    g = gate115
    wrong, exact = [], []
    for uid in g["alive_ids"]:
        nat, port = g["native"][uid]["target_hex"], _offline_gate(g, uid)
        if port == nat:
            if nat:
                exact.append((uid, hex(nat), g["native"][uid]["target_names"]))
            continue
        if port == 0:
            continue                       # regle native non portee -> permissif (documente)
        wrong.append((uid, hex(port), hex(nat), g["native"][uid]["target_names"]))
    assert not wrong, (
        "le port refuse pour une raison DIFFERENTE du natif (uid, port, natif, noms natifs) : "
        f"{wrong}")
    assert exact, "aucun refus natif reproduit a l'identique : test non discriminant"


def test_static_and_dynamic_refusals_are_distinguished(gate115):
    """#111 avait mesure que les deux rejets partagent la MEME observable live (2 evenements) : le
    port doit, lui, les SEPARER, et avec les MEMES codes que le natif. Cible non ennemie (soi /
    allie) -> filtre STATIQUE `TargetIsEnemy` (bit des `TargetingOptions` du ctor) ; ennemi hors
    portee de charge -> regle DYNAMIQUE (`GetDynamicInvalidTargetReason` -> `TargetIsInRange`)."""
    g = gate115
    for key, label in (("caster_id", "soi-meme"), ("ally_id", "un allie")):
        uid = g[key]
        assert g["native"][uid]["target_hex"] == TR.TargetIsEnemy, (
            f"precondition natif : cast sur {label} attendu TargetIsEnemy, "
            f"lu {g['native'][uid]['target_names']}")
        assert _offline_gate(g, uid) == TR.TargetIsEnemy, (
            f"cast sur {label} : le port n'oppose pas le filtre STATIQUE TargetIsEnemy")
    if g["far_id"] is None:
        pytest.skip("pas d'ennemi hors du gate dans cette geometrie")
    assert g["native"][g["far_id"]]["target_hex"] == TR.TargetIsInRange, (
        "precondition natif : ennemi hors charge attendu TargetIsInRange, "
        f"lu {g['native'][g['far_id']]['target_names']}")
    assert _offline_gate(g, g["far_id"]) == TR.TargetIsInRange, (
        "ennemi hors portee de charge : le port n'oppose pas la regle DYNAMIQUE de Waaagh")


# ================================================================================================ #
# FACE REFUS -- le no-op offline est COMPLET, et le live confirme la meme observable
# ================================================================================================ #

@pytest.mark.parametrize("key,label", [("caster_id", "le CASTER lui-meme"),
                                       ("ally_id", "un ALLIE"),
                                       ("far_id", "un ENNEMI hors portee de charge")])
def test_refused_cast_is_a_complete_noop_offline(gate115, key, label):
    """Le natif rend 0 en amont du 1er `AActiveAbility.Execute` ET d'`AddFlagsAfterAbilityExecution`
    -> offline : aucune behaviour (`dsl` absent), aucun spawn, AUCUN flag de tour pose."""
    g = gate115
    if g[key] is None:
        pytest.skip("cible indisponible dans cette geometrie")
    last, state = _offline_cast(g, g[key])
    assert last.get("invalid_target"), f"cast sur {label} : le moteur offline ne l'a PAS refuse"
    assert "dsl" not in last, f"cast sur {label} : la behaviour s'est executee malgre le refus"
    assert "flags" not in last, (
        f"cast sur {label} : des flags de tour ont ete poses -- le natif sort AVANT "
        f"AddFlagsAfterAbilityExecution (actionConsumed=false)")
    assert set(state.entities) == set(_fresh_state(g).entities), (
        f"cast sur {label} : le jeu d'entites a change (spawn) malgre le refus")


@pytest.mark.parametrize("key,label", [("self_cast", "le CASTER lui-meme"),
                                       ("ally_cast", "un ALLIE"),
                                       ("far_cast", "un ENNEMI hors portee de charge")])
def test_refused_cast_live_observable(gate115, key, label):
    """Cote LIVE la meme cible rend la signature de refus mesuree en #111 : `ok`, PAS de mutation,
    PAS de consommation d'activation, et le SEUL groupe `User_UseAbility` (aucun groupe d'etage)."""
    a = gate115[key]
    if a is None:
        pytest.skip("cible indisponible dans cette geometrie")
    assert a.get("ok") is True, f"cast sur {label} : le message n'a meme pas ete applique"
    assert a.get("mutated") is False and a.get("actionConsumed") is False, (
        f"cast sur {label} : le live a mute/consomme (attendu : refus)")
    assert _groups(a) == {GROUP_USE_ABILITY} and a.get("eventCount") == 2, (
        f"cast sur {label} : la trace live porte un groupe d'etage "
        f"({sorted(_groups(a))}, eventCount={a.get('eventCount')})")


# ================================================================================================ #
# FACE EXECUTION -- non-regression : le gate ne retire RIEN a un cast legal
# ================================================================================================ #

def test_legal_cast_still_executes_the_full_behaviour_offline(gate115):
    """Cible prise dans `fromHere` : le gate laisse passer et les 5 etages de
    `WaaaghAbility$$ExecuteBehaviour` s'executent offline comme avant #115 (spawn + 3 buffs +
    flags de tour), exactement comme le live (qui mute et consomme l'activation)."""
    g = gate115
    tid = sorted(g["legal_ids"])[0]
    assert _offline_gate(g, tid) == 0, "le gate refuse une cible que le natif offre"
    last, state = _offline_cast(g, tid)
    assert "invalid_target" not in last and last.get("dsl") is True, (
        f"cast legal non execute offline : {last}")
    assert last.get("spawned"), "cast legal : aucun Ork Boy invoque offline (etage Spawn)"
    assert last.get("buffed"), "cast legal : aucun buff pose offline (etage Buff)"
    assert last.get("flags") is not None, "cast legal : flags de tour non poses"
    live = g["legal_cast"]
    assert live.get("mutated") is True and live.get("actionConsumed") is True, (
        f"le live n'a pas execute le cast legal : {live}")


def test_caster_has_not_moved_rule_matches_live(caster_moved115):
    """VOLET CASTER (`TargetingQuery$$GetInvalidCasterReason`, bit 0x10 `CasterHasNotMoved`, pose
    par les `TargetingOptions` de Waaagh) : le natif ACCEPTE le cast tant que le Warboss n'a pas
    bouge, et le REFUSE des qu'il s'est deplace. Le port doit rendre le MEME code.

    Le flag `Moved` n'est PAS expose par les RPC -> `load_state` ne le seede pas : on le pose
    explicitement (`set_moved_flag`, l'UNIQUE poseur du port, appele par `MoveUnitOperation`) pour
    reproduire l'etat que le live vient d'atteindre. Sans ce cablage manuel le test ne testerait
    rien -- c'est aussi la raison pour laquelle la regle est INERTE sur tout etat charge (donc sans
    aucun risque de regression sur les tests existants)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import set_moved_flag

    d = caster_moved115
    assert d["before"] == 0, (
        f"precondition natif : casterReason non nul AVANT le move ({hex(d['before'])})")
    assert d["after"] == TR.CasterHasNotMoved, (
        f"precondition natif : casterReason attendu CasterHasNotMoved APRES le move, "
        f"lu {hex(d['after'])}")

    board = Board(d["bg"]["tiles"], adjacency="evenq")
    state = load_state(d["dec"], d["ob"], d["snap"], board=board)
    caster, tgt = int(d["caster_id"]), int(d["target_id"])
    assert is_invalid_target(state, caster, tgt, ABILITY_CLASSES[WAAAGH]()) != \
        TR.CasterHasNotMoved, (
        "flag Moved non pose (load_state ne le seede pas) : la regle ne doit pas mordre")
    set_moved_flag(state, caster)                        # = ce que fait MoveUnitOperation offline
    assert is_invalid_target(state, caster, tgt, ABILITY_CLASSES[WAAAGH]()) == \
        TR.CasterHasNotMoved, (
        "le port n'oppose pas CasterHasNotMoved a un Warboss qui vient de se deplacer")


def test_unported_targeting_options_means_no_gate(gate115):
    """DEGRADATION EXPLICITE : une ability dont les `TARGETING_OPTIONS` n'ont pas ete RE-lues n'est
    PAS gatee (le port ne peut pas inventer un refus). Garde la propriete « zero regression » sur
    les 60 autres abilities du registre, qu'aucun changement de #115 ne doit avoir mises a refuser."""
    g = gate115
    state = _fresh_state(g)
    caster, ally = int(g["caster_id"]), int(g["ally_id"])
    gated = [t for t, k in ABILITY_CLASSES.items() if getattr(k, "TARGETING_OPTIONS", None) is None
             and is_invalid_target(state, caster, ally, k()) != 0]
    assert not gated, f"abilities sans TARGETING_OPTIONS pourtant gatees : {sorted(gated)}"
    assert any(getattr(k, "TARGETING_OPTIONS", None) is not None
               for k in ABILITY_CLASSES.values()), "aucune ability gatee : test non discriminant"


def test_friendly_fire_effect_flips_the_enemy_rule(gate115):
    """`IdunBattle.Core.Services.TargetingQuery$$UnitsCanAttackEachOther` : le porteur de l'effet
    `FriendlyFire` (0x67) ne peut attaquer QUE ses amis -- la relation est INVERSEE, pas relaxee.
    Le gate porte doit donc, sur un caster sous 0x67, cesser d'opposer `TargetIsEnemy` a l'ALLIE et
    se mettre a l'opposer a l'ENNEMI. Aucun effet 0x67 n'est pose par les seeds : on le pose offline
    pour exercer la branche (sans elle, le mirror de cette ligne du decompile ne serait jamais
    teste).

    NB l'allie ne devient pas pour autant une cible ACCEPTEE : la regle DYNAMIQUE de Waaagh
    (chargeabilite) le refuse ensuite -- c'est bien la SEPARATION des deux etages qu'on lit ici."""
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import EffectFactory
    from engine.runner.abilities.targeting import EFFECT_FRIENDLY_FIRE, units_can_attack_each_other
    assert int(EffectType.FriendlyFire) == EFFECT_FRIENDLY_FIRE, (
        "l'effet 0x67 lu par UnitsCanAttackEachOther n'est plus FriendlyFire dans l'enum porte")
    g = gate115
    caster, ally = int(g["caster_id"]), int(g["ally_id"])
    enemy = int(sorted(g["legal_ids"])[0])
    state = _fresh_state(g)
    assert units_can_attack_each_other(state, caster, enemy) is True
    assert units_can_attack_each_other(state, caster, ally) is False
    assert is_invalid_target(state, caster, ally, ABILITY_CLASSES[WAAAGH]()) == TR.TargetIsEnemy

    state.effects.add_effect(caster, EffectFactory.create(
        {"name": "FriendlyFire", "effectType": EFFECT_FRIENDLY_FIRE}))
    assert units_can_attack_each_other(state, caster, enemy) is False, (
        "sous FriendlyFire l'ennemi doit devenir inattaquable (relation inversee, pas relaxee)")
    assert units_can_attack_each_other(state, caster, ally) is True, (
        "sous FriendlyFire l'allie doit devenir attaquable")
    assert is_invalid_target(state, caster, enemy,
                             ABILITY_CLASSES[WAAAGH]()) == TR.TargetIsEnemy, (
        "sous FriendlyFire le filtre statique doit refuser l'ennemi")
    assert is_invalid_target(state, caster, ally,
                             ABILITY_CLASSES[WAAAGH]()) != TR.TargetIsEnemy, (
        "sous FriendlyFire le filtre statique ne doit plus refuser l'allie")
