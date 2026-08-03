"""CONFRONTATION LIVE #433-r4-r2 -- la porte d'elevation gouverne le partage A/B, et le port suit.

Deux oracles, et le PREMIER est ce qui rend le second interpretable :

(A) **La bascule du NATIF, mesuree contre LUI-MEME** (`--step partition`). Meme caster, MEME tuile
    d'origine, meme sweep, meme ennemi : on ne bouge que la TUILE de l'ennemi, d'un voisin hex a
    `|dElev| >= 2` a un voisin PLAT. Le natif doit changer de BRANCHE, et ca se lit au bonus a
    `d = 4` : `0` (branche A, `IsTileInRangeOfAnyAbility` vrai) contre `50` (branche B,
    `d > FindRangedWeapon().Range = 3`). Aucun terme du port n'entre dans cette mesure -- c'est
    donc la preuve, sans confusion possible, que `MovementUtil$$AreTilesAdjacent` (et sa porte
    d'elevation) est bien ce qui tranche « caster adjacent a E ».

(B) **Le couple divergence -> convergence du PORT** (`--step couple`), sur un montage ou le sweep
    est CONFINE a `d <= 3` de l'ennemi (`--unit-stat tauCrisis:Movement=2`) -- c'est-a-dire dans le
    domaine ou les deux approximations de branche du port sont exactes (mesure (A) : le natif
    couvre au moins jusqu'a `d = 4`, et sa branche B ne verse rien avant `d > 3`). Trois lectures
    du MEME etat : le natif, le port AVEC le canal d'elevation (l'etat livre), le port avec le
    canal NEUTRALISE (`elev_by_pos = None`, l'etat d'AVANT). Sans la troisieme, un accord
    port/natif ne prouverait pas que la porte MORD.

Le quadruplet (tuile d'origine, voisin haut, voisin plat) est DERIVE du `boardGraph` : aucune tuile
hardcodee. Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268). ASCII only.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r2_adjacency_foyer as P


@pytest.fixture(scope="module")
def slots(live_session):
    r = P.step_slots(verbose=False)
    if not r.get("slots"):
        pytest.fail("resolution des slots IBattleQuery KO -- rien a confronter", pytrace=False)
    return r


@pytest.fixture(scope="module")
def partition(live_session):
    r = P.step_partition(verbose=True)
    if "error" in r:
        pytest.fail("montage PARTITION non installe : %s" % r["error"], pytrace=False)
    return r


@pytest.fixture(scope="module")
def couple(live_session):
    r = P.step_couple(verbose=True)
    if "error" in r:
        pytest.fail("montage COUPLE non installe : %s" % r["error"], pytrace=False)
    return r


# --------------------------------------------------------------------------- slots

def test_the_six_interface_slots_are_what_the_docstrings_claim(slots):
    """Les six slots `IBattleQuery` cites par les deux corps, RE-DERIVES au runtime.

    Ils ont bouge d'un cran entre `gqfc5mff6c` et `rnca9r7q6c` : une citation recopiee d'une fiche
    peut donc designer la METHODE VOISINE, et le port serait faux sans aucune erreur. `0xb3` est
    celui qui comptait le plus -- il etait ecrit « NON identifie » dans le port."""
    got = slots["slots"]
    bad = {s: (got.get(s), n) for s, n in P.EXPECTED_SLOTS.items() if got.get(s) != n}
    assert not bad, "slots divergents (obtenu, attendu) : %r" % bad


# --------------------------------------------------------------------------- (A) la bascule native

def test_the_high_neighbour_is_absent_from_the_native_adjacency_list(partition):
    """Verrou de montage : le `boardGraph` publie la liste rendue par `GetAdjacentTiles` ->
    `IterateAdjacentTiles`, qui a DEJA traverse la porte. Le voisin a `|dElev| >= 2` doit donc en
    etre absent, et le voisin plat present. Sans ce contraste, la mesure (A) n'oppose rien."""
    assert partition["hi_absent_de_la_liste_native"], (
        "le voisin HAUT %r est present dans la liste d'adjacence native de %r : la porte ne mord "
        "pas sur ce montage" % (partition["Y_hi"], partition["O"]))
    assert partition["lo_present_dans_la_liste_native"], (
        "le voisin PLAT %r est absent de la liste native : montage a re-etalonner"
        % (partition["Y_lo"],))


def test_native_switches_branch_on_the_elevation_gate(partition):
    """L'ORACLE (A). Meme O, meme sweep, meme ennemi -- seule la tuile de l'ennemi change.

    Voisin PLAT -> le natif prend la branche B et verse `+50` des que `d > 3` (la portee de l'arme
    a distance, `FindRangedWeapon` slot 0xb3). Voisin a `|dElev| >= 2` -> il prend la branche A et
    ne verse RIEN a la meme distance (`IsTileInRangeOfAnyAbility` vrai jusque-la). Le natif
    compare a lui-meme : c'est le terme d'ADJACENCE, et lui seul, qui a change."""
    hi, lo = partition.get("hi") or {}, partition.get("lo") or {}
    assert 4 in hi and 4 in lo, (
        "le sweep n'atteint pas d=4 dans les deux bras (hi=%r lo=%r) : la distance ou les deux "
        "branches different n'est pas couverte" % (hi, lo))
    assert hi[4] == [0.0], "voisin HAUT : bonus a d=4 attendu 0 (branche A), obtenu %r" % (hi[4],)
    assert lo[4] == [50.0], "voisin PLAT : bonus a d=4 attendu 50 (branche B), obtenu %r" % (lo[4],)
    for d in (1, 2, 3):
        assert hi.get(d) == [0.0] and lo.get(d) == [0.0], (
            "a d=%d les deux branches doivent valoir 0 (hi=%r lo=%r) -- si ce n'est pas le cas, "
            "le contraste a d=4 n'isole plus le terme d'adjacence" % (d, hi.get(d), lo.get(d)))


# --------------------------------------------------------------------------- (B) le couple

def test_the_montage_confines_the_sweep_where_both_branches_are_exact(couple):
    """Verrou de montage du couple : sweep NON VIDE et entierement a `d <= 3` de l'ennemi.

    Au-dela, un desaccord port/natif serait imputable a l'approximation de la branche A
    (`#433-r4-r2-r1`), pas au terme corrige -- l'oracle ne prouverait plus rien."""
    assert couple["n"] >= 8, "sweep trop court (%d positions)" % couple["n"]
    assert couple["d_max"] <= 3, (
        "le sweep atteint d=%d : hors du domaine ou la branche A du port est exacte"
        % couple["d_max"])
    assert abs(couple["elev_O"] - couple["elev_Y"]) >= 2, (
        "montage plat (elev %s vs %s) : le test serait vert pour la mauvaise raison"
        % (couple["elev_O"], couple["elev_Y"]))


def test_the_channel_flips_the_partition(couple):
    """La MUTATION mord : avec le canal, l'ennemi n'est PAS en branche B ; sans lui, il y est.
    Un couple dont la mutation ne change rien serait un vert sans contenu."""
    assert couple["adj_on"] == [], "avec le canal, l'ennemi ne doit pas etre declare adjacent"
    assert couple["adj_off"] == [list(couple["Y"])] or \
        [tuple(x) for x in couple["adj_off"]] == [tuple(couple["Y"])], \
        "sans le canal, l'ennemi doit retomber en branche B (obtenu %r)" % (couple["adj_off"],)


def test_port_converges_on_the_native_only_with_the_channel(couple):
    """L'ORACLE (B) : divergence -> convergence sur le MEME etat, position par position."""
    assert not couple["diff_on"], (
        "le port AVEC le canal diverge du natif sur %d/%d positions : %r"
        % (len(couple["diff_on"]), couple["n"], couple["diff_on"][:4]))
    assert couple["diff_off"], (
        "le port SANS le canal ne diverge NULLE PART : le montage ne discrimine rien, "
        "l'accord ci-dessus serait tautologique")
    assert len(couple["diff_off"]) >= couple["n"] // 2, (
        "seulement %d/%d positions divergentes sans le canal -- contraste trop faible"
        % (len(couple["diff_off"]), couple["n"]))


def test_the_emitted_action_no_longer_overshoots_the_native(couple):
    """Consequence OBSERVABLE : sans le canal le port emet un cast d'utilite `+30`, une valeur que
    le natif n'atteint NULLE PART sur ce sweep (son maximum est negatif). Avec le canal, il ne
    l'emet plus.

    NB : « le port n'emet plus » n'est pas « le natif n'emet pas » -- le Bucket natif de ce
    playbook n'a pas de `min` (residu `#433-r4-r2-r3`). L'assertion porte sur l'utilite EMISE,
    qui, elle, se compare."""
    off, on = couple["cand_off"], couple["cand_on"]
    assert off and off[0]["ability"] == P.ABILITY, \
        "sans le canal le port doit emettre un cast de %d (obtenu %r)" % (P.ABILITY, off)
    assert couple["native_best"] is not None and off[0]["pred"] > couple["native_best"], (
        "l'utilite emise sans le canal (%r) devrait depasser le maximum natif du sweep (%r)"
        % (off[0]["pred"], couple["native_best"]))
    assert on != off, "l'action emise ne change pas avec le canal"
