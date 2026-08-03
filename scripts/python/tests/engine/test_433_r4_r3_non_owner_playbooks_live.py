"""GARDE #433-r4-r3 -- les deux `*NonOwnerPlaybook` absents du registre, et le PRE-GATE slot 4.

CE QUE CES GARDES PROTEGENT -- trois choses, dont deux sont des regressions SILENCIEUSES :

1. **`EcogSupport` (1487) et `PsychicFortress` (1000) doivent etre au registre NonOwner.** Leur
   classe native EXISTE et son `CalculateMovementUtilityInSteps` yielde un poids NON NUL (10 / 20,
   valeur identique dans la capture `data/seed-bc.json` ET au gameconfig vivant -- donc pas de piege
   #271 ici : le terme mordait deja cote NATIF pendant que le port rendait 0). L'argument d'absence
   ecrit dans `non_owner.py` (« `LoadPlaybookNonOwner` rend null == meme degradation ») ne vaut QUE
   pour un type SANS classe native ; c'etait le residu.

2. **Le PRE-GATE `<slot 4> || IsFriend` doit etre applique.** Le slot 4 vaut `false` (lu au bloc
   `methodPointers` du PE, cf. docstring de tete de `engine/playbook/non_owner.py`), donc le gate se
   reduit a `IsFriend` -- et `PsychicFortressNonOwnerPlaybook` n'a AUCUN gate dans son corps. Sans
   le pre-gate, son terme se verserait pour un porteur ENNEMI : le moteur donnerait +20 aux tuiles
   adjacentes a Tigurius adverse, ce qu'aucune assertion anterieure ne voyait.

3. **Les deux corps ne se ressemblent PAS**, et les confondre est le piege : celui de
   `PsychicFortress` n'a aucun gate (adjacence seule) ; celui d'`EcogSupport` en a TROIS
   (`HasTrait(case.unit, 2 = Summon)`, `GetParent(case.unit) == owner`, puis adjacence).

Le montage live est celui de `probe_433_r4_r3_non_owner_playbooks.py` : on DEPLACE le porteur
`ultraTigurius` sur une tuile voisine NATIVE de la deuxieme meilleure tuile d'un allie, ce qui doit
faire basculer le choix NATIF de cet allie. Detail : `docs/rl/case-433-r4-r3-non-owner-playbooks.md`.

ASCII only.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))     # scripts/python

import probe_433_r4_r3_non_owner_playbooks as P                  # noqa: E402

PSYCHIC_FORTRESS = P.PSYCHIC_FORTRESS                            # 1000
ECOG_SUPPORT = P.ECOG_SUPPORT                                    # 1487
KEY_PF = P.KEY_PF
KEY_ECOG = P.KEY_ECOG


# --------------------------------------------------------------------------- gardes OFFLINE

def test_both_keys_are_non_zero_in_both_tables():
    """Les deux poids doivent etre NON NULS dans la table servie ET dans la capture.

    C'est le pendant, en positif, de la garde #271 : la-bas la capture portait 0 et seul le refresh
    sauvait la mesure. Ici les deux sources concordent, et c'est ce qui rend le terme mordant SANS
    aucune precaution de montage -- si un jour l'une des deux tombait a 0, ce fichier mesurerait le
    neant et doit ROUGIR."""
    from engine import weights as W
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        wt = W.load()
    assert "REPLI sur BC.Utilities" not in err.getvalue(), \
        "engine.weights.load est retombe sur la capture -- mesure sans valeur"
    assert float(wt.sub("TriggeredAbilitiesNonOwner", KEY_PF)) > 0, "%s inerte" % KEY_PF
    assert float(wt.sub("TriggeredAbilitiesNonOwner", KEY_ECOG)) > 0, "%s inerte" % KEY_ECOG
    root = Path(__file__).resolve().parents[4]
    bc = json.loads((root / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cap = ((bc.get("Utilities") or {}).get("Default") or {}).get("TriggeredAbilitiesNonOwner") or {}
    assert cap.get(KEY_PF) == 20 and cap.get(KEY_ECOG) == 10, \
        "la CAPTURE ne porte plus 20/10 (%r/%r) -- re-etalonner" % (cap.get(KEY_PF), cap.get(KEY_ECOG))


def test_both_playbooks_are_registered_and_wired_to_their_leaf():
    """Au registre NonOwner, ET la feuille `TriggeredAbilitiesNonOwner(4)` dans le composite Tile(7).
    Un playbook au registre dont la feuille n'est pas branchee est un port vert par coincidence."""
    from engine.playbook.non_owner import load_playbook_non_owner
    from engine.utilities.tile import TILE_LEAVES, TILE_UTILITY
    from engine.utilities.utility_type import UtilityType
    for ab in (PSYCHIC_FORTRESS, ECOG_SUPPORT):
        assert load_playbook_non_owner(ab) is not None, "playbook NonOwner absent pour %d" % ab
    leaf = TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
    assert leaf is not None and leaf in TILE_UTILITY.children, \
        "feuille TriggeredAbilitiesNonOwner(4) non branchee dans Tile(7)"


def test_psychic_fortress_body_has_no_gate_but_adjacency():
    """`GetMainTile(owner) == null` -> 0 ; tuile non adjacente -> 0 ; adjacente -> le poids.
    AUCUN autre gate : ni trait, ni faction, ni parent du mover -- c'est le corps le plus court de
    la famille, et lui inventer un gate serait aussi faux que d'en oublier un."""
    from engine import weights as W
    from engine.playbook.non_owner import load_playbook_non_owner
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", KEY_PF))
    pb = load_playbook_non_owner(PSYCHIC_FORTRESS)
    owner = {"pos": (2, 1), "vis": P.CARRIER_PF, "id": 42}
    ctx = {"elev_by_pos": {(1, 1): 2, (2, 1): 2, (5, 5): 2}}
    assert pb.calculate_movement_utility_in_steps((1, 1), {"vis": P.CARRIER_PF}, True, ctx, wt) == 0, \
        "porteur SANS position (GetMainTile null) -> 0"
    assert pb.calculate_movement_utility_in_steps((5, 5), owner, True, ctx, wt) == 0, \
        "tuile NON adjacente au porteur -> 0"
    assert pb.calculate_movement_utility_in_steps((1, 1), owner, True, ctx, wt) == pytest.approx(w)
    # aucun gate de trait / faction / parent : un ctx VIDE de ces cles rend le meme poids
    assert pb.calculate_movement_utility_in_steps((1, 1), owner, True, dict(
        ctx, unit_traits=(), unit_parent_id=None, unit_faction=None), wt) == pytest.approx(w)


def test_psychic_fortress_respects_the_native_elevation_gate():
    """`MovementUtil$$AreTilesAdjacent` = `|dElev| < 2 && (t1 == t2 || IsNeighbour)`. Deux tuiles
    cote a cote separees de 2 niveaux ne sont PAS adjacentes pour le natif."""
    from engine import weights as W
    from engine.playbook.non_owner import load_playbook_non_owner
    wt = W.load()
    pb = load_playbook_non_owner(PSYCHIC_FORTRESS)
    owner = {"pos": (2, 1), "vis": P.CARRIER_PF, "id": 42}
    flat = pb.calculate_movement_utility_in_steps(
        (1, 1), owner, True, {"elev_by_pos": {(1, 1): 2, (2, 1): 2}}, wt)
    step = pb.calculate_movement_utility_in_steps(
        (1, 1), owner, True, {"elev_by_pos": {(1, 1): 2, (2, 1): 4}}, wt)
    assert flat > 0 and step == 0, \
        "porte d'elevation |dElev| < 2 non appliquee (plat=%s, marche=%s)" % (flat, step)


def test_psychic_fortress_carries_the_identity_short_circuit():
    """`AreTilesAdjacent` porte le COURT-CIRCUIT D'IDENTITE (`t1 == t2` -> vrai), a la difference
    d'`IterateAdjacentTiles`. Ce foyer-la (`battle_query.are_entities_adjacent`) est celui que
    #433-r1 designe ; retomber sur `is_adjacent` REFUSERAIT l'adjacence que le natif accorde.

    Le regime est inatteignable en bataille (la tuile du porteur est occupee, donc jamais candidate
    pour le mover) -- on le mirrore quand meme plutot que de le supprimer sur un argument
    d'atteignabilite, exactement comme le fait `KustomForceFieldReworkedNonOwnerPlaybook`."""
    from engine import weights as W
    from engine.playbook.non_owner import load_playbook_non_owner
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", KEY_PF))
    pb = load_playbook_non_owner(PSYCHIC_FORTRESS)
    owner = {"pos": (2, 1), "vis": P.CARRIER_PF, "id": 42}
    assert pb.calculate_movement_utility_in_steps(
        (2, 1), owner, True, {"elev_by_pos": {(2, 1): 2}}, wt) == pytest.approx(w)


def test_ecog_support_body_gates_on_summon_trait_then_parent_then_adjacency():
    """Les TROIS gates du corps, releves un par un. Chacun seul doit suffire a annuler le terme."""
    from engine import weights as W
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.playbook.non_owner import load_playbook_non_owner
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", KEY_ECOG))
    pb = load_playbook_non_owner(ECOG_SUPPORT)
    owner = {"pos": (2, 1), "vis": P.CARRIER_ECOG, "id": 7}
    ok = {"elev_by_pos": {(1, 1): 2, (2, 1): 2, (5, 5): 2},
          "unit_traits": (int(UnitTrait.Summon),), "unit_parent_id": 7}
    assert pb.calculate_movement_utility_in_steps((1, 1), owner, True, ok, wt) == pytest.approx(w)
    assert pb.calculate_movement_utility_in_steps(
        (1, 1), owner, True, dict(ok, unit_traits=()), wt) == 0, "mover SANS trait Summon -> 0"
    assert pb.calculate_movement_utility_in_steps(
        (1, 1), owner, True, dict(ok, unit_parent_id=99), wt) == 0, "parent != owner -> 0"
    assert pb.calculate_movement_utility_in_steps(
        (1, 1), owner, True, dict(ok, unit_parent_id=None), wt) == 0, "parent inconnu -> 0"
    assert pb.calculate_movement_utility_in_steps((5, 5), owner, True, ok, wt) == 0, \
        "tuile non adjacente au porteur -> 0"
    assert pb.calculate_movement_utility_in_steps(
        (1, 1), {"vis": P.CARRIER_ECOG, "id": 7}, True, ok, wt) == 0, \
        "porteur SANS position (GetMainTile null) -> 0"


def test_the_pre_gate_excludes_an_ENEMY_carrier():
    """LE POINT #2 -- et il ne se voit QUE par la feuille, pas par les corps.

    `PsychicFortressNonOwnerPlaybook` n'a aucun gate d'amitie : appele directement avec
    `is_friend=False` il rend quand meme son poids (c'est FIDELE a son corps). C'est
    `IterateAbilities` qui l'ecarte, donc la feuille -- et c'est ce que ce test verifie, en faisant
    porter l'ability a un ENNEMI dans le `ctx`."""
    from engine import weights as W
    from engine.playbook.non_owner import load_playbook_non_owner
    from engine.utilities.tile import TILE_LEAVES
    from engine.utilities.utility_type import UtilityType
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", KEY_PF))
    pb = load_playbook_non_owner(PSYCHIC_FORTRESS)
    carrier = {"pos": (2, 1), "vis": P.CARRIER_PF, "id": 42, "triggered": (PSYCHIC_FORTRESS,)}
    elev = {(1, 1): 2, (2, 1): 2}
    # le CORPS ignore `is_friend` -- c'est voulu, il n'a pas ce gate au decompile
    assert pb.calculate_movement_utility_in_steps(
        (1, 1), carrier, False, {"elev_by_pos": elev}, wt) == pytest.approx(w)
    leaf = TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
    friend_ctx = {"elev_by_pos": elev, "friend_units": [carrier], "enemy_units": []}
    enemy_ctx = {"elev_by_pos": elev, "friend_units": [], "enemy_units": [carrier]}
    assert leaf.evaluate((1, 1), None, friend_ctx, wt) == pytest.approx(w), \
        "porteur AMI adjacent : la feuille doit verser le poids"
    assert leaf.evaluate((1, 1), None, enemy_ctx, wt) == 0, \
        ("porteur ENNEMI : le pre-gate `<slot 4 = false> || IsFriend` doit l'ecarter -- "
         "sans lui le moteur verse %s sur les tuiles adjacentes a un Tigurius ADVERSE" % w)


def test_the_leaf_still_reaches_the_registered_playbooks_through_a_carrier_kit():
    """Cablage bout en bout de la feuille : c'est le `triggered` du VOISIN qui selectionne le
    playbook. Un porteur dont le kit ne contient pas l'id ne doit rien verser."""
    from engine import weights as W
    from engine.utilities.tile import TILE_LEAVES
    from engine.utilities.utility_type import UtilityType
    wt = W.load()
    leaf = TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
    elev = {(1, 1): 2, (2, 1): 2}
    base = {"elev_by_pos": elev, "enemy_units": []}
    with_kit = dict(base, friend_units=[{"pos": (2, 1), "vis": P.CARRIER_PF, "id": 42,
                                         "triggered": (PSYCHIC_FORTRESS,)}])
    without = dict(base, friend_units=[{"pos": (2, 1), "vis": P.CARRIER_PF, "id": 42,
                                        "triggered": ()}])
    assert leaf.evaluate((1, 1), None, with_kit, wt) > 0
    assert leaf.evaluate((1, 1), None, without, wt) == 0


# --------------------------------------------------------------------------- garde LIVE

@pytest.fixture(scope="module")
def pf_case(live_session):
    """Le montage crafte du cas (`probe_433_r4_r3_non_owner_playbooks.run_psychic_fortress`) :
    build isole, porteur DEPLACE contre la 2e meilleure tuile d'un allie, argmax du port avec et
    sans le terme, proposition NATIVE de l'allie. Le probe dispose ses runners lui-meme.

    Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268)."""
    r = P.run_psychic_fortress(verbose=True)
    if "error" in r:
        pytest.fail("montage PsychicFortress NON INSTALLE : %s" % r["error"], pytrace=False)
    return r


def test_live_carrier_kit_holds_the_ability_on_BOTH_substrates(pf_case):
    """GARDE DE SOURCE. Le port lit le `triggered` du voisin (substrat d'ENTITE) ; le NATIF lit
    l'`AbilitiesComponent` ECS. Les deux doivent porter 1000, sinon la mesure est vide."""
    assert PSYCHIC_FORTRESS in pf_case["kit_port"], \
        "kit du port sans 1000 : %r" % (pf_case["kit_port"],)
    assert PSYCHIC_FORTRESS in pf_case["kit_live"], \
        "AbilitiesComponent LIVE sans 1000 : %r" % (pf_case["kit_live"],)


def test_live_native_follows_the_non_owner_term(pf_case):
    """LE CONFRONT. Le porteur pose contre T2 (et pas T1) doit renverser l'argmax du MOVER, et le
    natif doit jouer la tuile que le port retient AVEC le terme.

    `p_on != p_off` est l'exigence adversariale : sans elle le montage ne pourrait rien
    contredire."""
    assert pf_case["p_on"] != pf_case["p_off"], (
        "le terme ne renverse PAS l'argmax du port (T1=%s T2=%s, porteur pose en %s) -- montage a "
        "re-etalonner" % (pf_case["t1"], pf_case["t2"], pf_case["slot"]))
    assert pf_case["native"] == pf_case["p_on"], (
        "le NATIF joue %s ; le port AVEC le terme retient %s, SANS le terme %s. mover=u%s, "
        "porteur u%s pose en %s." % (pf_case["native"], pf_case["p_on"], pf_case["p_off"],
                                     pf_case["mover"], pf_case["carrier"], pf_case["slot"]))


@pytest.fixture(scope="module")
def ecog_case(live_session):
    """Le montage `EcogSupport` (`probe_433_r4_r3_non_owner_playbooks.run_ecog_support`) : porteur
    HORS pool injecte au catalogue, E-Cog REELLEMENT invoque par une reparation
    (`On(0x30 = UnitRepaired) & OwnerIsCaster`), puis le terme du port mesure sur le `ctx` LIVE du
    summon. Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268)."""
    r = P.run_ecog_support(verbose=True)
    if "error" in r:
        pytest.fail("montage EcogSupport NON INSTALLE : %s" % r["error"], pytrace=False)
    return r


def test_live_ecog_summon_really_appears_and_carries_the_two_gates(ecog_case):
    """L'ATTEIGNABILITE, mesuree et non deduite : le summon apparait, et les deux gates non triviaux
    du corps (`HasTrait(case.unit, 2)` et `GetParent(case.unit) == owner`) passent sur le `ctx`
    LIVE. Sans ces deux cles, le terme serait INERTE sans que rien ne le signale -- c'est
    exactement la degradation que `scene_tile_leaf_ctx` porte encore (residu nomme)."""
    assert ecog_case["summon_vis"] == "votanNpc1Ecog", (
        "le summon apparait sous le `visualId` de son entree gameconfig, pas sous son id "
        "(`case-92` §5) -- obtenu %r" % ecog_case["summon_vis"])
    assert ecog_case["has_summon_trait"], \
        "le `ctx` live du summon ne porte pas `UnitTrait.Summon` -- gate 1 inerte"
    assert ecog_case["parent_uid"] == ecog_case["carrier"], (
        "`unit_parent_id` du `ctx` live (%r) ne resout pas vers le porteur u%s -- gate 2 inerte"
        % (ecog_case["parent_uid"], ecog_case["carrier"]))


def test_live_ecog_term_lands_exactly_on_the_carrier_neighbourhood(ecog_case):
    """Le terme vaut le poids EXACTEMENT sur les tuiles que `MovementUtil$$AreTilesAdjacent` declare
    adjacentes au porteur, et 0 partout ailleurs -- balaye sur TOUT le voisinage natif du plateau.

    NON CONFRONTE, et c'est STRUCTUREL : un summon n'entre jamais dans `decisionView.toActivate`
    (#291), donc `aiMovableTiles` lui rend zero tuile et `aiDryRunAllUnits` un
    `FinishUnitTurnMessage`. Son mouvement est joue par `PlayAutomaticUnits` au turn-start SUIVANT :
    oracle DESTRUCTIF (un point de mesure par bataille) sur une geometrie de spawn TIREE AU SORT par
    le natif (`PickRandomly(CanAddUnit(AdjacentTiles(Caster)), 1)`)."""
    assert ecog_case["n_tiles"] > 20, \
        "voisinage natif trop petit (%d tuiles) -- montage a re-etalonner" % ecog_case["n_tiles"]
    assert ecog_case["n_tiles_scored"] > 0, (
        "le terme ne mord sur AUCUNE tuile alors que le porteur est en %s -- inerte"
        % (ecog_case["carrier_pos"],))
    assert not ecog_case["mismatch"], (
        "le terme diverge du predicat d'adjacence natif sur %d tuiles : %r"
        % (len(ecog_case["mismatch"]), ecog_case["mismatch"][:5]))
