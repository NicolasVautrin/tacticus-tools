"""CONFRONTATION LIVE #433-r4-r2 -- la porte d'elevation gouverne le partage A/B, et le port suit.

Deux oracles, et le PREMIER est ce qui rend le second interpretable :

(A) **La bascule du NATIF, mesuree contre LUI-MEME** (`--step partition`). Meme caster, MEME tuile
    d'origine, meme sweep, meme ennemi : on ne bouge que la TUILE de l'ennemi, d'un voisin hex a
    `|dElev| >= 2` a un voisin PLAT. Le natif doit changer de BRANCHE, et ca se lit au bonus a
    `d = 4` : `0` (branche A, `IsTileInRangeOfAnyAbility` vrai) contre `50` (branche B,
    `d > FindRangedWeapon().Range = 3`). Aucun terme du port n'entre dans cette mesure -- c'est
    donc la preuve, sans confusion possible, que `MovementUtil$$AreTilesAdjacent` (et sa porte
    d'elevation) est bien ce qui tranche « caster adjacent a E ».

(B) **Le couple divergence -> convergence du PORT** (`--step couple`), sur un montage qui ATTEINT
    `d = 4..5` (`--unit-stat tauCrisis:Movement=4`) -- c'est-a-dire la zone `3 < d <= 5` ou les
    deux branches DIFFERENT (branche A muette, zone d'ability de portee 5 ; branche B `+50` des
    `d > 3`, portee de l'ARME). L'ancien montage CONFINAIT le sweep a `d <= 3`, domaine ou les
    approximations d'alors restaient exactes ; #433-r4-r2-r1/-r2 les ayant portees, ce confinement
    retirait justement les distances discriminantes. Trois lectures du MEME etat : le natif, le
    port AVEC le canal d'elevation (l'etat livre), le port avec le canal NEUTRALISE
    (`elev_by_pos = None`, l'etat d'AVANT). Sans la troisieme, un accord port/natif ne prouverait
    pas que la porte MORD.

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

def test_the_montage_reaches_the_distance_where_the_branches_differ(couple):
    """Verrou de montage du couple, RE-ETALONNE par #433-r4-r2-r1/-r2.

    L'ancien verrou exigeait `d_max <= 3` : c'etait le domaine ou les deux APPROXIMATIONS d'alors
    (branche A = portee d'ARME, branche B = `threshold` fige a 1) restaient exactes. Les deux etant
    desormais portees, ce confinement RETIRAIT justement les distances ou les branches different.
    Sur `tauMarksman` la separation est `3 < d <= 5` : la branche A ne verse rien (zone d'ability
    de portee 5) la ou la branche B verse `+50` (`d > 3`, portee de l'ARME). Sans `d >= 4` dans le
    sweep, la mutation du canal serait INOBSERVABLE et l'oracle vide."""
    assert couple["n"] >= 8, "sweep trop court (%d positions)" % couple["n"]
    assert couple["d_max"] >= 4, (
        "le sweep s'arrete a d=%d : il n'atteint pas la zone `3 < d <= 5` ou les deux branches "
        "different" % couple["d_max"])
    assert abs(couple["elev_O"] - couple["elev_Y"]) >= 2, (
        "montage plat (elev %s vs %s) : le test serait vert pour la mauvaise raison"
        % (couple["elev_O"], couple["elev_Y"]))
    seuils = {(e["reach"], e["threshold"]) for e in couple["enemies"]}
    assert seuils == {(5, 3)}, (
        "les deux seuils de branche doivent DIFFERER (zone d'ability 5, arme a distance 3), "
        "obtenu %r -- sinon le partage A/B est indiscernable dans le port" % (seuils,))


def test_the_channel_flips_the_partition(couple):
    """La MUTATION mord : avec le canal, l'ennemi n'est PAS en branche B ; sans lui, il y est.
    Un couple dont la mutation ne change rien serait un vert sans contenu."""
    assert couple["adj_on"] == [], "avec le canal, l'ennemi ne doit pas etre declare adjacent"
    assert [tuple(x) for x in couple["adj_off"]] == [tuple(couple["Y"])], \
        "sans le canal, l'ennemi doit retomber en branche B (obtenu %r)" % (couple["adj_off"],)


def test_port_converges_on_the_native_only_with_the_channel(couple):
    """L'ORACLE (B) : divergence -> convergence sur le MEME etat, position par position.

    LE RESIDU EST BORNE, PAS NIE. Sur ce montage a RELIEF, une position reste divergente AVEC le
    canal : le natif retire de la zone d'ability une tuile a `d = 4` que ses voisines de meme
    distance contiennent (LoS / elevation dans `AttackQuery$$GetAllTilesInAbilityRange`), la ou le
    port modelise la zone par un DISQUE. Mesure : **1/34** ici, **0/40** sur le montage PLAT du
    meme kit (`probe_433_r4_r2_r1_ability_range.py --step kit`, `tauMarksman`) -- l'ecart est donc
    bien porte par le relief, et non par la portee. Le SENS compte : le port dit « en portee » la
    ou le natif dit « hors », donc il SOUS-estime l'utilite (residu `#433-r4-r2-r1`, volet ZONE)."""
    assert len(couple["diff_on"]) <= 1, (
        "le port AVEC le canal diverge du natif sur %d/%d positions (residu LoS borne a 1) : %r"
        % (len(couple["diff_on"]), couple["n"], couple["diff_on"][:4]))
    for r in couple["diff_on"]:
        assert r["natif"] - r["port_on"] == 50.0, (
            "la divergence residuelle doit valoir exactement un bonus de couverture en faveur du "
            "NATIF (LoS) ; obtenu natif=%r port=%r" % (r["natif"], r["port_on"]))
    assert couple["diff_off"], (
        "le port SANS le canal ne diverge NULLE PART : le montage ne discrimine rien, "
        "l'accord ci-dessus serait tautologique")
    assert len(couple["diff_off"]) > len(couple["diff_on"]) + 3, (
        "seulement %d/%d positions divergentes sans le canal (contre %d avec) -- contraste trop "
        "faible" % (len(couple["diff_off"]), couple["n"], len(couple["diff_on"])))


def test_the_emitted_action_changes_with_the_channel(couple):
    """Consequence OBSERVABLE : sans le canal le port emet un cast (branche B, `d > 3`), avec le
    canal il n'en emet plus (branche A : rien n'est hors de la zone de portee 5 sur ce sweep).

    RE-ETALONNE : avant #433-r4-r2-r1/-r2, le port emettait `+30` (branche B a `threshold` fige a
    1, des `d = 2`) contre un maximum natif NEGATIF -- le depassement etait la signature du bug.
    Avec le `threshold` porte a 3, la 1re position qui verse est `d = 4`, l'utilite emise tombe a
    `+10` et le natif ATTEINT lui aussi `+10` (sur la tuile que son LoS retire de la zone). Le
    depassement a donc DISPARU : ce qui se compare desormais, c'est le CHANGEMENT d'action.

    NB : « le port n'emet plus » n'est pas « le natif n'emet pas » -- le Bucket natif de ce
    playbook n'a pas de `min` (residu `#433-r4-r2-r3`)."""
    off, on = couple["cand_off"], couple["cand_on"]
    assert off and off[0]["ability"] == P.ABILITY, \
        "sans le canal le port doit emettre un cast de %d (obtenu %r)" % (P.ABILITY, off)
    assert couple["native_best"] is not None and off[0]["pred"] <= couple["native_best"], (
        "l'utilite emise sans le canal (%r) DEPASSE le maximum natif du sweep (%r) : le port "
        "sur-evalue a nouveau" % (off[0]["pred"], couple["native_best"]))
    assert on != off, "l'action emise ne change pas avec le canal"
