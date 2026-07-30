"""GARDE #271 -- `KustomForceFieldReworked` (1547, `orksBigMek`) : les DEUX faces + l'adjacence.

CE QUE CES GARDES PROTEGENT. Trois choses qui, chacune, sont dej tombees une fois :

1. **Les poids doivent venir du gameconfig VIVANT.** Les deux cles valaient 0 dans la table de la
   CAPTURE et valent 10 au gameconfig. Tant que le natif et le moteur lisaient la meme table
   perimee, ils etaient d'accord ET faux tous les deux -- un A/B rendait « aucun ecart ». Si
   `engine.weights.load` retombe un jour sur la capture, ce fichier doit ROUGIR, pas passer.

2. **Le predicat d'adjacence du port doit etre celui du NATIF.** `IBattleQuery.GetAdjacent*` passe
   par `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, qui gate
   `abs(elev(tuile) - elev(voisin)) < 2`. `hexgeo.distance == 1` NU sur-compte -- mesure #271 :
   33 faux sur 4 963 paires (3 boards), toujours dans le sens permissif. C'est ce trou qui a fait
   rendre a l'A/B du cas un faux « le natif n'applique pas le terme », CONTROLE COMPRIS.

3. **Les deux faces doivent etre au registre ET consommees par leur feuille.** Face OWNER ->
   `TriggeredAbilities(2)` (`load_playbook`) ; face NON-OWNER -> `TriggeredAbilitiesNonOwner(4)`
   (`load_playbook_non_owner`), feuille qui n'existait PAS avant ce cas. Un playbook au registre
   dont la feuille n'est pas branchee est un port speculatif, vert par coincidence.

Le montage live est celui de `probe_271_kustom_force_field_reworked.py --driven` : on DEPLACE un
allie sur une tuile voisine NATIVE de la deuxieme meilleure tuile du Big Mek, ce qui doit faire
basculer le choix NATIF. Detail et resultats : `docs/rl/case-271-kustom-force-field-reworked.md`.

ASCII only.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))     # scripts/python

ABILITY = 1547
CARRIER = "orksBigMek"
KEY_OWNER = "KustomForceFieldReworked_LikesAdjacentFriends"
KEY_NONOWNER = "KustomForceFieldReworked_FriendsLikeToBeAdjacent"

P_UNITS = "orksBigMek,orksNob,astraBullgryn,necroWarden,orksWarboss"
A_UNITS = "worldKharn,templChampion,tauMarksman"


# --------------------------------------------------------------------------- gardes OFFLINE

def test_weights_come_from_the_live_gameconfig_not_the_capture():
    """Sans ca, tout ce fichier mesurerait le NEANT : c'est le motif meme du cas."""
    from engine import weights as W
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        wt = W.load()
    assert "REPLI sur BC.Utilities" not in err.getvalue(), (
        "engine.weights.load est retombe sur la table de la CAPTURE -- les deux cles y valent 0, "
        "toute mesure de ce fichier serait vide de sens")
    assert wt.sub("TriggeredAbilities", KEY_OWNER) > 0, (
        "%s vaut 0 cote moteur -- terme inerte" % KEY_OWNER)
    assert wt.sub("TriggeredAbilitiesNonOwner", KEY_NONOWNER) > 0, (
        "%s vaut 0 cote moteur -- terme inerte" % KEY_NONOWNER)


def test_the_capture_really_carries_zero_for_both_keys():
    """Le CONTRE-EXEMPLE qui donne son sens a la garde precedente : la table de la capture porte
    bien 0. Si un jour elle portait la bonne valeur, la garde ci-dessus deviendrait vacante et il
    faudrait le SAVOIR (le refresh `refresh_ai_utilities` ne serait plus ce qui nous sauve)."""
    root = Path(__file__).resolve().parents[4]
    bc = json.loads((root / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    default = (bc.get("Utilities") or {}).get("Default") or {}
    assert (default.get("TriggeredAbilities") or {}).get(KEY_OWNER) == 0
    assert (default.get("TriggeredAbilitiesNonOwner") or {}).get(KEY_NONOWNER) == 0


def test_both_faces_are_registered_and_wired_to_their_leaf():
    """Face OWNER dans `TRIGGERED_MOVE_PLAYBOOKS`, face NON-OWNER dans `NON_OWNER_MOVE_PLAYBOOKS`,
    ET la feuille `TriggeredAbilitiesNonOwner(4)` branchee dans le composite `Tile(7)`."""
    from engine.playbook.adjacent_unit_preference import load_playbook
    from engine.playbook.non_owner import load_playbook_non_owner
    from engine.utilities.tile import TILE_LEAVES, TILE_UTILITY
    from engine.utilities.utility_type import UtilityType
    assert load_playbook(ABILITY) is not None, "face OWNER absente du registre 1547"
    assert load_playbook_non_owner(ABILITY) is not None, "face NON-OWNER absente du registre 1547"
    leaf = TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
    assert leaf is not None, "feuille TriggeredAbilitiesNonOwner(4) non portee"
    assert leaf in TILE_UTILITY.children, (
        "feuille 4 portee mais ABSENTE du composite Tile(7) -- elle ne serait jamais evaluee")


def test_owner_face_doubles_for_an_ork_neighbour():
    """`HasFaction(unit, 5)` lu DANS l'accesseur : 2 x le poids pour un ami Orks, 1 x sinon.
    Le multiplicateur est un `imul` du litteral, PAS un second poids BC."""
    from engine import weights as W
    from engine.playbook.adjacent_unit_preference import load_playbook
    wt = W.load()
    w = float(wt.sub("TriggeredAbilities", KEY_OWNER))
    pb = load_playbook(ABILITY)
    ork = {"pos": (2, 1), "vis": "orksNob", "traits": ()}
    other = {"pos": (2, 1), "vis": "astraBullgryn", "traits": ()}
    flat = {"elev_by_pos": {(1, 1): 2, (2, 1): 2}}
    v_ork = pb.calculate_movement_utility_in_steps((1, 1), dict(flat, friend_units=[ork]), wt)
    v_oth = pb.calculate_movement_utility_in_steps((1, 1), dict(flat, friend_units=[other]), wt)
    assert v_ork == pytest.approx(2 * w), "ami Orks : attendu 2 x %s, obtenu %s" % (w, v_ork)
    assert v_oth == pytest.approx(w), "ami non-Orks : attendu %s, obtenu %s" % (w, v_oth)


def test_owner_face_respects_the_native_elevation_gate():
    """Le corps commun retient les voisins par `battle_query.is_adjacent` (hexgeo + porte
    d'elevation `|Delta| < 2`), PAS par `hexgeo.distance == 1` nu. Un ami a 2 niveaux d'ecart
    n'est PAS un voisin pour le natif -- et le port doit le refuser."""
    from engine import weights as W
    from engine.playbook.adjacent_unit_preference import load_playbook
    wt = W.load()
    pb = load_playbook(ABILITY)
    friend = [{"pos": (2, 1), "vis": "orksNob", "traits": ()}]
    same = pb.calculate_movement_utility_in_steps(
        (1, 1), {"friend_units": friend, "elev_by_pos": {(1, 1): 2, (2, 1): 2}}, wt)
    step = pb.calculate_movement_utility_in_steps(
        (1, 1), {"friend_units": friend, "elev_by_pos": {(1, 1): 2, (2, 1): 4}}, wt)
    assert same > 0, "voisin de meme elevation : le terme doit compter"
    assert step == 0, ("voisin a 2 niveaux d'ecart : le natif ne le compte PAS "
                       "(TileQuery.IterateAdjacentTiles, gate |Delta| < 2), obtenu %s" % step)


def test_non_owner_face_gates_on_friendship_and_adjacency():
    """`IsFriend(case.unit, owner)` PUIS `IsAdjacentTo(case.MovementTile, ownerTile)`, et le x2 lit
    la faction du MOVER (`ctx['unit_faction']`), pas celle du porteur."""
    from engine import weights as W
    from engine.entities.unit_faction import UnitFaction
    from engine.playbook.non_owner import load_playbook_non_owner
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", KEY_NONOWNER))
    pb = load_playbook_non_owner(ABILITY)
    owner = {"pos": (2, 1), "vis": CARRIER}
    elev = {"elev_by_pos": {(1, 1): 2, (2, 1): 2, (5, 5): 2}}
    base = dict(elev, unit_faction=None)
    assert pb.calculate_movement_utility_in_steps((1, 1), owner, False, base, wt) == 0, \
        "porteur ENNEMI : IsFriend faux -> 0"
    assert pb.calculate_movement_utility_in_steps((5, 5), owner, True, base, wt) == 0, \
        "tuile NON adjacente au porteur -> 0"
    assert pb.calculate_movement_utility_in_steps((1, 1), owner, True, base, wt) \
        == pytest.approx(w), "mover non-Ork adjacent au porteur -> w"
    ork_ctx = dict(elev, unit_faction=int(UnitFaction.Orks))
    assert pb.calculate_movement_utility_in_steps((1, 1), owner, True, ork_ctx, wt) \
        == pytest.approx(2 * w), "mover ORK adjacent au porteur -> 2w (HasFaction(case.unit, 5))"


# --------------------------------------------------------------------------- gardes LIVE

@pytest.fixture(scope="module")
def kff_stage(rpc, build_runner):
    """Le montage crafte du cas : runner `MC1_67`/777, roster mixte Orks / non-Orks."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    rid = build_runner("777", extra=["--p-units", P_UNITS, "--a-units", A_UNITS],
                       board="MC1_67")["rid"]
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    ids = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or [])}
    uid = ids.get(CARRIER)
    if uid is None:
        pytest.fail("le porteur %s n'est pas dans la bataille -- montage a re-etalonner" % CARRIER)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    pred = _scene.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    ctx = _ai_ctx.build(lambda m, b, t: rpc(m, b, t), rid, dv0, mov_by_unit, uid, wt, pred)
    return {"rid": rid, "uid": uid, "ids": ids, "ctx": ctx, "wt": wt, "dv": dv0,
            "mov": mov_by_unit}


def test_live_kit_carries_the_triggered_ability(kff_stage, rpc):
    """GARDE DE SOURCE, DEUX substrats. Le port lit le kit gameconfig ; le NATIF lit
    l'`AbilitiesComponent` ECS. Les deux doivent porter 1547, sinon le playbook n'est JAMAIS appele
    d'un cote ou de l'autre et tout ce qui suit serait vert par coincidence."""
    from engine.utilities.tile import tile_leaf_ctx
    s = kff_stage
    kit = tile_leaf_ctx(s["ctx"]).get("unit_triggered_abilities") or []
    assert ABILITY in kit, "kit du port sans 1547 : %r" % kit
    states = rpc("unitAbilityStates", {"runnerId": s["rid"]}, 180)
    row = next((u for u in (states.get("units") or []) if u.get("entityId") == s["uid"]), None)
    assert row is not None, "porteur absent de unitAbilityStates"
    live = [t.get("raw", [None])[0] for t in (row.get("triggered") or [])]
    assert ABILITY in live, (
        "l'AbilitiesComponent LIVE du porteur ne contient pas 1547 (%r) -- le natif n'evaluerait "
        "jamais ce playbook" % live)


def test_port_adjacency_predicate_matches_the_native_board_graph(kff_stage):
    """LE COEUR DU PIEGE #271 : `battle_query.is_adjacent` doit reproduire EXACTEMENT le voisinage
    natif que rend `boardGraph`, la ou `hexgeo.distance == 1` NU sur-compte. On exige les deux :
    zero faux pour le predicat du port, ET au moins un faux pour hexgeo nu -- sans ce second volet,
    le test passerait aussi sur un board plat, ou il ne verifie RIEN."""
    import hexgeo
    from engine import battle_query as bq
    ctx = kff_stage["ctx"]
    nb = {p: set(tuple(q) for q in (v or [])) for p, v in (ctx.neigh_by_pos or {}).items()}
    elev = ctx.elev_by_pos
    n = hex_bad = bq_bad = 0
    for p in nb:
        for q in nb:
            if p >= q:
                continue
            n += 1
            nat = q in nb[p]
            hex_bad += int((hexgeo.distance(p, q) == 1) != nat)
            bq_bad += int(bq.is_adjacent(p, q, elev) != nat)
    assert n > 100, "voisinage natif trop petit (%d paires) -- montage a re-etalonner" % n
    assert bq_bad == 0, (
        "battle_query.is_adjacent diverge du voisinage NATIF sur %d paires / %d" % (bq_bad, n))
    assert hex_bad > 0, (
        "hexgeo NU ne se trompe sur aucune des %d paires de ce board : le test ne DISCRIMINE pas "
        "les deux predicats ici -- prendre un board a marches d'elevation (MC1_67, C4_09)" % n)


def _score_map(ctx, wt, with_term: bool):
    """`UnitMovement(6)` du port par tuile candidate, terme 1547 ACTIF ou AMPUTE des DEUX faces."""
    from engine.playbook.base import tile_utility
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS
    from engine.utilities.move import MIN_DIST_UTILITY
    saved = None
    if not with_term:
        saved = (TRIGGERED_MOVE_PLAYBOOKS.pop(ABILITY, None),
                 NON_OWNER_MOVE_PLAYBOOKS.pop(ABILITY, None))
    try:
        out = {}
        for t in (ctx.move_tiles or []):
            p = (t["col"], t["row"])
            out[p] = tile_utility(ctx, p) + MIN_DIST_UTILITY.evaluate_movement(
                p, ctx.tgt_epos or ctx.epos, wt, ctx.pathdist_by_pos, case=ctx.mindist_case)
        return out
    finally:
        if saved is not None:
            if saved[0] is not None:
                TRIGGERED_MOVE_PLAYBOOKS[ABILITY] = saved[0]
            if saved[1] is not None:
                NON_OWNER_MOVE_PLAYBOOKS[ABILITY] = saved[1]


def test_live_native_follows_the_owner_term_when_an_ally_is_placed(kff_stage, rpc, build_runner):
    """LE CONFRONT DU CAS. On pose un allie sur une tuile voisine NATIVE de la deuxieme meilleure
    tuile du Big Mek (et PAS de la premiere) : le terme doit renverser le classement, et le NATIF
    doit jouer la tuile que le port retient AVEC le terme.

    Sans le terme (etat `master`), le port retient l'autre tuile -- c'est l'amputation du registre
    qui rend la mesure adversariale : si l'argmax ne bougeait pas, le montage ne prouverait rien."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    s = kff_stage
    ctx, wt = s["ctx"], s["wt"]
    base = _score_map(ctx, wt, with_term=False)
    if len(base) < 2:
        pytest.fail("moins de 2 tuiles candidates -- montage a re-etalonner")
    nb = {p: set(tuple(q) for q in (v or [])) for p, v in (ctx.neigh_by_pos or {}).items()}
    occupied = set(ctx.epos) | set(ctx.fpos) | {ctx.origin}
    order = sorted(base.items(), key=lambda kv: -kv[1])
    t1 = order[0][0]
    pick = None
    for t2, s2 in order[1:]:
        if base[t1] - s2 > 25.0:
            break
        for u in (s["dv"].get("units") or []):
            if not u.get("ctrl") or u.get("id") == s["uid"]:
                continue
            for t in ((s["mov"].get(u["id"]) or {}).get("tiles") or []):
                c = (t["col"], t["row"])
                # `c` PEUT etre une tuile candidate du porteur : l'allie l'occupe, elle sort du
                # set -- sans consequence tant que ce n'est ni T1 ni T2, tout etant RECALCULE sur
                # l'etat mute juste apres.
                if c in occupied or c in (t1, t2):
                    continue
                if c in nb.get(t2, ()) and c not in nb.get(t1, ()):
                    pick = (t1, t2, u["id"], c)
                    break
            if pick:
                break
        if pick:
            break
    if pick is None:
        pytest.fail("aucune tuile ou poser un allie voisin de T2 seule -- montage a re-etalonner")
    t1, t2, ally, slot = pick

    # runner NEUF : le stage de module est partage, on ne le MUTE pas.
    rid = build_runner("777", extra=["--p-units", P_UNITS, "--a-units", A_UNITS],
                       board="MC1_67")["rid"]
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": ally, "to": {"col": slot[0], "row": slot[1]}}}, 90)
    assert (res.get("actions") or [{}])[0].get("ok"), "applyAction move KO : %r" % res

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt2 = W.load()
    pred = _scene.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    ctx2 = _ai_ctx.build(lambda m, b, t: rpc(m, b, t), rid, dv, mov_by_unit, s["uid"], wt2, pred)
    off = _score_map(ctx2, wt2, with_term=False)
    on = _score_map(ctx2, wt2, with_term=True)
    p_off = max(off, key=lambda k: off[k])
    p_on = max(on, key=lambda k: on[k])

    allu = rpc("aiDryRunAllUnits", {"runnerId": rid}, 240)
    row = next((u for u in (allu.get("units") or []) if u.get("unitId") == s["uid"]), None)
    assert row is not None, "porteur absent de aiDryRunAllUnits"
    msgs = row.get("proposed") or []
    mv = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    assert mv is not None and not any(m.get("cls") == "ActiveAbilityMessage" for m in msgs), (
        "la proposition native n'est pas un MOVE PUR (%r) -- la tuile viendrait du sweep d'ATTAQUE, "
        "hors du modele UnitMovement(6)" % [m.get("cls") for m in msgs])
    native = (mv["to"]["col"], mv["to"]["row"])

    assert p_on != p_off, (
        "le terme ne renverse PAS l'argmax du port sur ce montage (T1=%s T2=%s, allie en %s) -- "
        "la mesure ne peut rien contredire, montage a re-etalonner" % (t1, t2, slot))
    assert native == p_on, (
        "le NATIF joue %s ; le port AVEC le terme retient %s, SANS le terme %s. T1=%s T2=%s, "
        "allie u%s pose en %s." % (native, p_on, p_off, t1, t2, ally, slot))
