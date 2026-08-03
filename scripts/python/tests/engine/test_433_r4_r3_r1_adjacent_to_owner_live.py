"""GARDE #433-r4-r3-r1 -- les DIX `AdjacentToOwnerNonOwnerPlaybook<T>` et leur corps PARTAGE.

CE QUE CES GARDES PROTEGENT -- quatre choses, toutes des regressions SILENCIEUSES :

1. **NEUF des dix doivent etre au registre NonOwner, sous l'id de leur ENUM.** Leur classe native
   existe et leur `CalculateMovementUtilityInSteps` (un unique corps gshared, partage par les dix)
   yielde un poids non nul. L'argument d'absence de `non_owner.py` (« `LoadPlaybookNonOwner` rend
   null == meme degradation ») ne vaut QUE pour un type SANS classe native.
   **La dixieme, `RedemptionOfTheRisen` (1522), doit rester HORS du registre** : elle n'est
   attribuee a AUCUNE unite sur ce build (verifie par deux sources independantes, cf. la docstring
   de sa classe), et l'enregistrer serait du code que le dispatcher n'itere jamais -- le patron
   #419, dont le cliquet `test_419_playbook_wiring_ratchet_offline.py` refuse exactement cela.

2. **`PrimarchOfTheFirstLegion` doit etre indexee 1511, PAS 1462.** Son `.ctor` passe `0x5b6` =
   1462 = `NetherRealmCasket` -- copier-coller du jeu, jusqu'au `MethodInfo*` de base inflate. Ce
   n'est pas le `.ctor` qui indexe le registre mais le site d'enregistrement
   (`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`), balaye par
   `probe_433_r4_r3_r1_non_owner_registry.py` : 1511 y figure, 1462 une seule fois. Suivre le
   `.ctor` aurait, au choix, TUE l'entree 1462 de `NetherRealmCasket` (dont les porteurs sont au
   pool par la voie relique) ou pose une entree morte.

3. **`IsMechanical` n'est PAS `HasTrait(Mechanical)`.** `MyWillBeDoneOverlord` et
   `TimesplinterMantle` appellent `IdunBattle.Entities.UnitExtensions$$IsMechanical` (=
   `HasTrait(5) | HasTrait(1000) | HasTrait(1029)`) ; `NetherRealmCasket` appelle `HasTrait(5)` NU.
   La difference est OBSERVABLE sur un `LivingMetal` ou un `Vehicle` non `Mechanical`, et les
   confondre est invisible sur toute unite qui porte les deux.

4. **`PropheticSentinel` CUMULE ses deux termes.** C'est le seul des dix dont la valeur n'est pas
   booleenne : Psyker ET Chaos rend 40, pas 20. L'appariement trait -> cle est LU dans le `.cctor`
   (`statics[0]` = Psyker, `statics[1]` = Chaos), pas deduit du nom -- les deux poids valant 20, il
   est numeriquement inobservable, ce qui est precisement pourquoi il fallait le lire.

Le montage live est celui de `probe_433_r4_r3_r1_adjacent_to_owner.py` : on GREFFE le passif sur
une unite DU POOL (aucun des dix porteurs n'arrive en bataille par la voie ordinaire -- le seul
hero du pool qui en porte un, `necroOverlord`, a une entree `BC.Units` PERIMEE, #254-bc/#392-r1),
puis on DEPLACE le greffon contre la 2e meilleure tuile d'un mover pour faire basculer le choix
NATIF. Detail : `docs/rl/case-433-r4-r3-non-owner-playbooks.md`.

ASCII only.
"""
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))     # scripts/python

import probe_433_r4_r3_r1_adjacent_to_owner as P                 # noqa: E402

WATCHED_OVER = P.WATCHED_OVER                                    # 1524
PRIMARCH = P.PRIMARCH                                            # 1511
NETHER_REALM_CASKET = 1462
KEY_WO = P.KEY_WO
KEY_PR = P.KEY_PR

# (id d'enum, nom de classe portee, cles BC lues par son `GetAdjacencyUtility`)
FAMILY = [
    (1459, "RelicOfLostCadiaNonOwnerPlaybook", ["RelicOfLostCadia_AdjacentImperialSummons"]),
    (1462, "NetherRealmCasketNonOwnerPlaybook", ["NetherRealmCasket_AdjacentMechanicals"]),
    (1464, "AmuletOfTheVoidwyrmNonOwnerPlaybook", ["AmuletOfTheVoidwyrm_AdjacentSummons"]),
    (1511, "PrimarchOfTheFirstLegionNonOwnerPlaybook",
     ["PrimarchOfTheFirstLegion_AdjacentDarkAngels"]),
    # 1522 `RedemptionOfTheRisen` n'est PAS ici : portee mais HORS registre (zero porteur, #419).
    # Sa garde dediee est `test_redemption_of_the_risen_is_ported_but_DELIBERATELY_unregistered`.
    (1524, "WatchedOverNonOwnerPlaybook", ["WatchedOver_AdjacentFriends"]),
    (1534, "TimesplinterMantleNonOwnerPlaybook",
     ["TimesplinterMantle_FriendlyMechanicalLikeThothmek"]),
    (1543, "PropheticSentinelNonOwnerPlaybook",
     ["PropheticSentinel_PsykerLikesToBeAdjacent", "PropheticSentinel_ChaosLikesToBeAdjacent"]),
    (1552, "IconOfObstinacyNonOwnerPlaybook",
     ["IconOfObstinacy_TerminatorFriendLikesToBeAdjacent"]),
    (1556, "MyWillBeDoneOverlordNonOwnerPlaybook",
     ["MyWillBeDoneOverlord_FriendlyMechanicalLikeAnuphet"]),
]


def _wt():
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        from engine import weights as W
        wt = W.load()
    assert "REPLI sur BC.Utilities" not in err.getvalue(), \
        "engine.weights.load est retombe sur la capture -- mesure sans valeur"
    return wt


# --------------------------------------------------------------------------- gardes OFFLINE

def test_the_ten_are_registered_under_their_ENUM_id():
    """POINT #1. Les dix au registre, chacun sous l'id de son enum et avec sa classe portee."""
    from engine.playbook.non_owner import load_playbook_non_owner
    for aid, cls, _keys in FAMILY:
        pb = load_playbook_non_owner(aid)
        assert pb is not None, "playbook NonOwner absent pour %d (%s)" % (aid, cls)
        assert type(pb).__name__ == cls, \
            "id %d resout vers %s, attendu %s" % (aid, type(pb).__name__, cls)


def test_primarch_is_indexed_1511_and_does_NOT_shadow_nether_realm_casket():
    """POINT #2 -- la regression que le litteral du `.ctor` aurait produite.

    Si l'on avait suivi le `.ctor` (`0x5b6` = 1462), l'entree 1462 aurait porte le playbook de
    `PrimarchOfTheFirstLegion` (gate `HasFaction(DarkAngels)`) au lieu de celui de
    `NetherRealmCasket` (gate `HasTrait(Mechanical)`), et 1511 n'aurait plus rien. Aucune erreur,
    aucun crash : juste un gate substitue a un autre sur un porteur bien reel."""
    from engine.playbook.non_owner import load_playbook_non_owner
    assert type(load_playbook_non_owner(PRIMARCH)).__name__ == \
        "PrimarchOfTheFirstLegionNonOwnerPlaybook"
    assert type(load_playbook_non_owner(NETHER_REALM_CASKET)).__name__ == \
        "NetherRealmCasketNonOwnerPlaybook", \
        "1462 doit rester NetherRealmCasket -- le `.ctor` de Primarch recopie ce litteral par erreur"


def test_every_key_of_the_family_is_non_zero_in_the_served_table():
    """Onze cles pour dix classes (PropheticSentinel en a deux). Une cle a 0 rend son terme INERTE :
    le port et le natif seraient d'accord ET vides -- exactement le piege #271."""
    wt = _wt()
    for _aid, cls, keys in FAMILY:
        for k in keys:
            assert float(wt.sub("TriggeredAbilitiesNonOwner", k)) > 0, \
                "%s : cle %s inerte dans la table servie" % (cls, k)


def test_the_leaf_is_wired_and_reaches_the_new_playbooks_through_a_carrier_kit():
    """Cablage bout en bout : c'est le `triggered` du VOISIN qui selectionne le playbook. Un
    playbook au registre dont la feuille n'est pas branchee est un port vert par coincidence."""
    from engine.utilities.tile import TILE_LEAVES, TILE_UTILITY
    from engine.utilities.utility_type import UtilityType
    wt = _wt()
    leaf = TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
    assert leaf is not None and leaf in TILE_UTILITY.children, \
        "feuille TriggeredAbilitiesNonOwner(4) non branchee dans Tile(7)"
    elev = {(1, 1): 2, (2, 1): 2}
    base = {"elev_by_pos": elev, "enemy_units": []}
    with_kit = dict(base, friend_units=[{"pos": (2, 1), "id": 42, "triggered": (WATCHED_OVER,)}])
    without = dict(base, friend_units=[{"pos": (2, 1), "id": 42, "triggered": ()}])
    assert leaf.evaluate((1, 1), None, with_kit, wt) == pytest.approx(
        float(wt.sub("TriggeredAbilitiesNonOwner", KEY_WO)))
    assert leaf.evaluate((1, 1), None, without, wt) == 0


def test_shared_body_gates_on_adjacency_elevation_and_owner_position():
    """LE CORPS PARTAGE, mesure sur `WatchedOver` (le seul des dix SANS gate sur le mover, donc le
    seul ou l'on isole le corps de la face variable).

    Trois sorties precoces, chacune seule suffisante :
      * porteur sans position -> `AreEntitiesAdjacent(tiles, unit)` rend faux ;
      * tuile non adjacente ;
      * porte d'elevation `|dElev| < 2` de `MovementUtil$$AreTilesAdjacent`.
    Et le COURT-CIRCUIT D'IDENTITE (`t1 == t2` -> vrai), que ce foyer porte et
    `IterateAdjacentTiles` non (#433-r1)."""
    from engine.playbook.non_owner import load_playbook_non_owner
    wt = _wt()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", KEY_WO))
    pb = load_playbook_non_owner(WATCHED_OVER)
    owner = {"pos": (2, 1), "id": 42}
    ctx = {"elev_by_pos": {(1, 1): 2, (2, 1): 2, (5, 5): 2}}
    assert pb.calculate_movement_utility_in_steps((1, 1), {"id": 42}, True, ctx, wt) == 0, \
        "porteur SANS position -> 0"
    assert pb.calculate_movement_utility_in_steps((5, 5), owner, True, ctx, wt) == 0, \
        "tuile NON adjacente au porteur -> 0"
    assert pb.calculate_movement_utility_in_steps((1, 1), owner, True, ctx, wt) == pytest.approx(w)
    assert pb.calculate_movement_utility_in_steps(
        (1, 1), owner, True, {"elev_by_pos": {(1, 1): 2, (2, 1): 4}}, wt) == 0, \
        "porte d'elevation |dElev| < 2 non appliquee"
    assert pb.calculate_movement_utility_in_steps(
        (2, 1), owner, True, {"elev_by_pos": {(2, 1): 2}}, wt) == pytest.approx(w), \
        "court-circuit d'identite `t1 == t2` absent (#433-r1)"
    # AUCUN gate sur le mover : un `ctx` vide de traits/faction/parent rend le meme poids
    assert pb.calculate_movement_utility_in_steps((1, 1), owner, True, dict(
        ctx, unit_traits=(), unit_faction=None, unit_parent_id=None), wt) == pytest.approx(w)


def test_shared_body_yields_nothing_in_the_SPAWN_regime():
    """`if (case.unit == null) yield break;` -- le regime SPAWN (`SortTilesByUtilityForSummon`,
    case-205) est le seul ou le sujet manque, et le `ctx` de ce foyer ne porte aucune cle d'unite."""
    from engine.playbook.non_owner import load_playbook_non_owner
    wt = _wt()
    pb = load_playbook_non_owner(WATCHED_OVER)
    owner = {"pos": (2, 1), "id": 42}
    ctx = {"elev_by_pos": {(1, 1): 2, (2, 1): 2}, "is_spawning": True}
    assert pb.calculate_movement_utility_in_steps((1, 1), owner, True, ctx, wt) == 0


@pytest.mark.parametrize("aid,traits,faction,expected_keys", [
    # (id, traits du MOVER, faction du MOVER, cles attendues -- [] = terme nul)
    (1459, (26, 2), None, ["RelicOfLostCadia_AdjacentImperialSummons"]),   # Imperial ET Summon
    (1459, (26,), None, []),                                              # Imperial seul -> 0
    (1459, (2,), None, []),                                               # Summon seul -> 0
    (1462, (5,), None, ["NetherRealmCasket_AdjacentMechanicals"]),        # HasTrait(Mechanical) NU
    (1462, (1000,), None, []),                                            # LivingMetal -> 0 ici
    (1462, (1029,), None, []),                                            # Vehicle -> 0 ici
    (1464, (2,), None, ["AmuletOfTheVoidwyrm_AdjacentSummons"]),          # Summon
    (1464, (), None, []),
    (1511, (), 10, ["PrimarchOfTheFirstLegion_AdjacentDarkAngels"]),      # HasFaction(DarkAngels)
    (1511, (), 7, []),
    (1524, (), None, ["WatchedOver_AdjacentFriends"]),                     # AUCUN gate
    (1534, (5,), None, ["TimesplinterMantle_FriendlyMechanicalLikeThothmek"]),
    (1534, (1000,), None, ["TimesplinterMantle_FriendlyMechanicalLikeThothmek"]),   # IsMechanical
    (1534, (1029,), None, ["TimesplinterMantle_FriendlyMechanicalLikeThothmek"]),   # IsMechanical
    (1534, (26,), None, []),
    (1543, (1002,), None, ["PropheticSentinel_PsykerLikesToBeAdjacent"]),
    (1543, (2026,), None, ["PropheticSentinel_ChaosLikesToBeAdjacent"]),
    (1543, (1002, 2026), None, ["PropheticSentinel_PsykerLikesToBeAdjacent",
                                "PropheticSentinel_ChaosLikesToBeAdjacent"]),   # CUMUL
    (1543, (), None, []),
    (1552, (1039,), None, ["IconOfObstinacy_TerminatorFriendLikesToBeAdjacent"]),
    (1552, (5,), None, []),
    (1556, (5,), None, ["MyWillBeDoneOverlord_FriendlyMechanicalLikeAnuphet"]),
    (1556, (1000,), None, ["MyWillBeDoneOverlord_FriendlyMechanicalLikeAnuphet"]),  # IsMechanical
    (1556, (1029,), None, ["MyWillBeDoneOverlord_FriendlyMechanicalLikeAnuphet"]),  # IsMechanical
    (1556, (26,), None, []),
])
def test_each_get_adjacency_utility_gate(aid, traits, faction, expected_keys):
    """POINTS #3 et #4 -- la face VARIABLE, corps par corps.

    Le porteur est toujours adjacent : seule la face `GetAdjacencyUtility` discrimine ici. Les ids
    de trait sont QUALIFIES contre `IdunBattle.Entities.Enum.UnitTrait` (2=Summon, 5=Mechanical,
    26=Imperial, 1000=LivingMetal, 1002=Psyker, 1029=Vehicle, 1039=TerminatorArmour, 2026=Chaos)
    et la faction contre `UnitFaction` (10=DarkAngels).

    Les couples 1462/1534 et 1462/1556 sur `(1000,)` et `(1029,)` sont le DISCRIMINANT entre
    `HasTrait(Mechanical)` NU et `IsMechanical` : les confondre est invisible sur toute unite qui
    porte les deux traits."""
    from engine.playbook.non_owner import load_playbook_non_owner
    wt = _wt()
    pb = load_playbook_non_owner(aid)
    owner = {"pos": (2, 1), "id": 42}
    ctx = {"elev_by_pos": {(1, 1): 2, (2, 1): 2}, "unit_traits": traits, "unit_faction": faction}
    got = pb.calculate_movement_utility_in_steps((1, 1), owner, True, ctx, wt)
    want = sum(float(wt.sub("TriggeredAbilitiesNonOwner", k)) for k in expected_keys)
    assert got == pytest.approx(want), \
        "ability %d, traits=%r faction=%r : terme=%s, attendu=%s (%r)" % (
            aid, traits, faction, got, want, expected_keys)


def test_the_pre_gate_excludes_an_ENEMY_carrier_for_the_new_family():
    """Le pre-gate `<slot 4 = false> || IsFriend` d'`IterateAbilities`, sur la famille NEUVE.

    Le corps partage ne teste PAS `IsFriend` -- appele directement avec `is_friend=False` il rend
    son poids, et c'est FIDELE. C'est la feuille qui ecarte le porteur adverse. Sans elle, un
    porteur ENNEMI de `WatchedOver` verserait +20 sur ses tuiles adjacentes."""
    from engine.playbook.non_owner import load_playbook_non_owner
    from engine.utilities.tile import TILE_LEAVES
    from engine.utilities.utility_type import UtilityType
    wt = _wt()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", KEY_WO))
    pb = load_playbook_non_owner(WATCHED_OVER)
    carrier = {"pos": (2, 1), "id": 42, "triggered": (WATCHED_OVER,)}
    elev = {(1, 1): 2, (2, 1): 2}
    assert pb.calculate_movement_utility_in_steps(
        (1, 1), carrier, False, {"elev_by_pos": elev}, wt) == pytest.approx(w)
    leaf = TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
    assert leaf.evaluate((1, 1), None, {"elev_by_pos": elev, "friend_units": [carrier],
                                        "enemy_units": []}, wt) == pytest.approx(w)
    assert leaf.evaluate((1, 1), None, {"elev_by_pos": elev, "friend_units": [],
                                        "enemy_units": [carrier]}, wt) == 0, \
        "porteur ENNEMI : le pre-gate doit l'ecarter -- sans lui le moteur verse %s" % w


def test_redemption_of_the_risen_is_ported_but_DELIBERATELY_unregistered():
    """LE DEAD CODE NOMME. `RedemptionOfTheRisen` (1522) n'est attribuee a AUCUNE unite sur ce
    build -- la classe est portee (sa RE est faite et son corps est exact), mais l'enregistrer
    ferait tourner du code que le dispatcher n'itere jamais : le patron #419.

    Cette garde tient les DEUX bouts, pour qu'aucun des deux ne derive en silence :
      * l'absence du registre est VOULUE (et non un oubli qu'un futur lecteur « corrigerait ») ;
      * la classe reste JUSTE, donc reactivable en une ligne le jour ou une unite portera 1522.
    Le corps est identique a celui de `PrimarchOfTheFirstLegion`, cle et poids compris."""
    from engine.playbook.non_owner import (NON_OWNER_MOVE_PLAYBOOKS,
                                           RedemptionOfTheRisenNonOwnerPlaybook)
    wt = _wt()
    assert 1522 not in NON_OWNER_MOVE_PLAYBOOKS, (
        "1522 est au registre alors qu'AUCUNE unite ne porte RedemptionOfTheRisen sur ce build -- "
        "code inerte (patron #419, cliquet test_419_playbook_wiring_ratchet_offline.py)")
    pb = RedemptionOfTheRisenNonOwnerPlaybook()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", "RedemptionOfTheRisen_AdjacentDarkAngels"))
    assert w > 0, "la cle existe au gameconfig meme sans porteur -- si elle tombe a 0, re-lire"
    owner = {"pos": (2, 1), "id": 42}
    elev = {"elev_by_pos": {(1, 1): 2, (2, 1): 2}}
    assert pb.calculate_movement_utility_in_steps(
        (1, 1), owner, True, dict(elev, unit_faction=10), wt) == pytest.approx(w)
    assert pb.calculate_movement_utility_in_steps(
        (1, 1), owner, True, dict(elev, unit_faction=2), wt) == 0


def test_registry_key_probe_agrees_with_the_port():
    """Le probe de registre (`probe_433_r4_r3_r1_non_owner_registry.py`) balaye le site
    d'enregistrement natif et doit trouver CHACUN des dix ids d'enum. Il est la SEULE source du
    choix `1511` pour `PrimarchOfTheFirstLegion` cote offline -- s'il rougit, le port l'est aussi.

    Le probe couvre les DIX classes natives ; le registre porte n'en compte que NEUF (1522 en est
    delibrement absente, cf. la garde ci-dessus). L'ecart attendu est donc EXACTEMENT {1522} -- le
    figer ici empeche qu'une autre disparition passe pour ce dead-code-la."""
    import probe_433_r4_r3_r1_non_owner_registry as R
    from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS
    enum_ids = {e for (_n, _c, e) in R.ADJACENT_TO_OWNER}
    assert enum_ids - {1522} == {aid for (aid, _c, _k) in FAMILY}, \
        "le probe de registre et cette garde ne parlent pas de la meme famille"
    assert enum_ids - set(NON_OWNER_MOVE_PLAYBOOKS) == {1522}, \
        "l'ecart registre natif / registre porte n'est plus le seul dead-code nomme (1522)"
    assert R.main.__module__  # le probe est importable ; son verdict est joue par la banque


# --------------------------------------------------------------------------- gardes LIVE

@pytest.fixture(scope="module")
def watched_over_case(live_session):
    """ETAPE A -- `WatchedOver` (poids 20, AUCUN gate) greffe sur une unite du pool, puis le greffon
    DEPLACE contre la 2e meilleure tuile d'un mover. Le probe dispose ses runners lui-meme.
    Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268)."""
    r = P.run_tile_flip(P.WATCHED_OVER, "WatchedOver", P.KEY_WO, verbose=True)
    if "error" in r:
        pytest.fail("montage WatchedOver NON INSTALLE : %s" % r["error"], pytrace=False)
    return r


def test_live_grafted_kit_holds_the_ability_on_BOTH_substrates(watched_over_case):
    """GARDE DE SOURCE. Le port lit le `triggered` du voisin (substrat d'ENTITE) ; le NATIF lit
    l'`AbilitiesComponent` ECS. La greffe doit apparaitre dans les DEUX, sinon le bras « AVEC
    terme » ne mesure que le port et l'accord serait un artefact."""
    assert WATCHED_OVER in watched_over_case["kit_port"], \
        "kit du port sans 1524 : %r" % (watched_over_case["kit_port"],)
    assert WATCHED_OVER in watched_over_case["kit_live"], \
        "AbilitiesComponent LIVE sans 1524 : %r" % (watched_over_case["kit_live"],)


def test_live_native_follows_the_shared_body_term(watched_over_case):
    """LE CONFRONT DU CORPS PARTAGE. `p_on != p_off` est l'exigence adversariale : sans elle le
    montage ne pourrait rien contredire."""
    c = watched_over_case
    assert c["p_on"] != c["p_off"], (
        "le terme ne renverse PAS l'argmax du port (T1=%s T2=%s, greffon pose en %s) -- montage a "
        "re-etalonner" % (c["t1"], c["t2"], c["slot"]))
    assert c["native"] == c["p_on"], (
        "le NATIF joue %s ; le port AVEC le terme retient %s, SANS le terme %s. mover=u%s, "
        "greffon u%s pose en %s." % (c["native"], c["p_on"], c["p_off"], c["mover"],
                                     c["carrier"], c["slot"]))


@pytest.fixture(scope="module")
def primarch_case(live_session):
    """ETAPE B -- `PrimarchOfTheFirstLegion` (poids 20, gate `HasFaction(DarkAngels)`) greffee sous
    l'id **1511**. Le montage tranche EN VIVANT la cle de registre : si le natif n'avait pas
    d'entree sous 1511, `LoadPlaybookNonOwner` rendrait null et il ne suivrait pas le terme."""
    r = P.run_tile_flip(P.PRIMARCH, "PrimarchOfTheFirstLegion", P.KEY_PR,
                        mover_faction=P.DARK_ANGELS, verbose=True)
    if "error" in r:
        pytest.fail("montage PrimarchOfTheFirstLegion NON INSTALLE : %s" % r["error"],
                    pytrace=False)
    return r


def test_live_primarch_registry_key_1511_is_the_one_the_native_uses(primarch_case):
    """POINT #2, tranche EN VIVANT et independamment du balayage offline.

    Le mover retenu DOIT etre Dark Angels (sinon le gate l'aurait annule et le montage ne prouverait
    rien), et le natif doit suivre le changement de tuile -- ce qu'il ne ferait pas si son registre
    n'avait aucune entree sous 1511."""
    c = primarch_case
    assert c["mover_faction"] == P.DARK_ANGELS, \
        "le mover retenu (%s) n'est pas Dark Angels -- le gate l'annulerait" % c["mover_vis"]
    assert PRIMARCH in c["kit_live"], \
        "AbilitiesComponent LIVE sans 1511 : %r" % (c["kit_live"],)
    assert c["p_on"] != c["p_off"], (
        "le terme ne renverse PAS l'argmax du port (T1=%s T2=%s, greffon en %s)"
        % (c["t1"], c["t2"], c["slot"]))
    assert c["native"] == c["p_on"], (
        "le NATIF joue %s, le port AVEC terme %s (SANS terme %s) -- si le registre natif n'avait "
        "PAS d'entree sous 1511, c'est exactement ce qu'on verrait."
        % (c["native"], c["p_on"], c["p_off"]))


def test_live_primarch_gate_is_exactly_zero_outside_dark_angels(primarch_case):
    """POINT #3 sur la face variable, EN VIVANT : greffon a la MEME position, un mover d'une autre
    faction doit voir le terme valoir EXACTEMENT 0 sur TOUTES ses tuiles candidates -- pas « peu »,
    pas « en moyenne »."""
    g = primarch_case.get("gate") or {}
    assert g, "aucun mover hors gate dans le roster -- le gate n'est pas confronte"
    assert g["tiles"] > 0, "le mover hors gate n'a aucune tuile candidate -- rien de mesure"
    assert g["max_delta"] == 0.0, (
        "le terme mord sur un mover faction %s (delta max=%s) alors que le gate est "
        "HasFaction(DarkAngels)" % (g["faction"], g["max_delta"]))
