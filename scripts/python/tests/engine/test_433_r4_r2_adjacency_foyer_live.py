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
    port LIVRE, et le port d'AVANT `#433-r4-r2` (adjacence = distance hex nue, TOUS les autres
    canaux intacts). Sans la troisieme, un accord port/natif ne prouverait pas que le foyer MORD.

RE-ETALONNAGE `#433-r4-r2-r4`. La contre-epreuve etait `elev_by_pos = None`, et elle a cesse de
mordre le 2026-08-04 a `489bb349` (`fix(#433-r4-r1-r4-r2)`) -- bisect a deux points : 3 passed a
`3dbcd330` (20:29), 3 failed a `489bb349` (20:58), memes tests, meme message. AUCUN port n'avait
regresse : `is_adjacent` enumere desormais `neigh_by_pos`, la liste STOCKEE que
`BattleQuery$$GetAdjacentTiles(t, 0, 0, 1)` rend -- DEJA traversee par la porte d'elevation. Les
deux canaux portent donc la MEME exclusion, et en neutraliser un seul ne restitue rien. Pire, depuis
`feat(#433-r4-r2-r1-r2)` `elev_by_pos` est AUSSI le substrat de la ligne de vue de la branche A : la
mutation elargissait la zone d'ability de l'ennemi au lieu de rendre une adjacence. Le verrou
`test_neutralising_one_channel_alone_no_longer_restores_adjacency` fixe ce fait pour qu'aucune
contre-epreuve ne le suppose a nouveau.

Second correctif de la meme passe : `rows` confrontait au natif un `utility_at` AMPUTE de ses canaux
(elevation, murs, equipes, walkability, brouillard) -- ceux que `generate_candidates` lui passe. Il
fabriquait ainsi une divergence de `1/34`, imputee au residu LoS de la ZONE. Canaux reellement
passes : **0/34**.

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


def test_neutralising_one_channel_alone_no_longer_restores_adjacency(couple):
    """LE VERROU DU PIEGE `#433-r4-r2-r4`, et la raison pour laquelle la contre-epreuve a change.

    Le foyer d'adjacence est porte par DEUX canaux qui disent la MEME chose sur cette arete :
    `neigh_by_pos` (la liste STOCKEE, deja traversee par la porte de
    `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`) et `elev_by_pos` (la porte re-jouee,
    idempotente sur ce substrat). En neutraliser UN SEUL laisse donc l'exclusion en place -- et
    c'est exactement ce qui a vide l'ancien bras de contre-epreuve, silencieusement.

    Ce test fixe la REDONDANCE elle-meme : si un jour un seul canal suffisait a restituer
    l'adjacence, la mesure aurait change de nature et toute contre-epreuve batie dessus serait a
    re-lire. Il ne juge PAS le port -- les quatre lectures sortent du meme foyer livre."""
    par_canal = couple["adj_par_canal"]
    Y = tuple(couple["Y"])
    assert par_canal["elev+neigh"] == [], \
        "les deux canaux presents : l'ennemi ne doit pas etre adjacent (obtenu %r)" \
        % (par_canal["elev+neigh"],)
    for tag in ("neigh seul", "elev seul"):
        assert par_canal[tag] == [], (
            "canal `%s` : l'exclusion doit TENIR -- si elle tombe, les deux canaux ne sont plus "
            "redondants et la contre-epreuve du couple est a re-etalonner (obtenu %r)"
            % (tag, par_canal[tag]))
    assert [tuple(x) for x in par_canal["aucun"]] == [Y], (
        "les DEUX canaux neutralises : l'adjacence doit retomber sur la couronne hex nue, sans "
        "quoi le montage n'oppose plus rien (obtenu %r)" % (par_canal["aucun"],))


def test_the_channel_flips_the_partition(couple):
    """La MUTATION mord : le foyer LIVRE ne met pas l'ennemi en branche B, celui d'AVANT si.
    Un couple dont la mutation ne change rien serait un vert sans contenu."""
    assert couple["adj_on"] == [], \
        "foyer livre : l'ennemi ne doit pas etre declare adjacent (obtenu %r)" % (couple["adj_on"],)
    assert [tuple(x) for x in couple["adj_avant"]] == [tuple(couple["Y"])], \
        "port d'AVANT #433-r4-r2 : l'ennemi doit retomber en branche B (obtenu %r)" \
        % (couple["adj_avant"],)


def test_port_converges_on_the_native_only_with_the_channel(couple):
    """L'ORACLE (B) : divergence -> convergence sur le MEME etat, position par position.

    DURCI par `#433-r4-r2-r4`, et le durcissement est une CORRECTION DE MESURE, pas un progres du
    port : la borne etait `<= 1`, au motif d'un residu LoS. Cette divergence unique venait de la
    CONFRONTATION -- `rows` appelait `utility_at` sans les canaux (elevation, murs, equipes,
    walkability, brouillard) que `generate_candidates` lui passe, donc comparait au natif un port
    ampute. Canaux reellement passes, le port livre colle au natif sur **34/34** positions ; le
    seul ecart (`(5, 2)`, `d = 4` : natif 10, port ampute -40) valait exactement le bonus que la
    ligne de vue accorde, et le port l'accorde bien des qu'on le lui donne a lire.

    Le volet ZONE de `#433-r4-r2-r1` n'est donc PAS observable sur ce montage. Il reste nomme dans
    la case-doc -- une divergence LoS peut exister sur un autre relief -- mais ce test ne lui
    reserve plus de marge : une divergence ici serait un fait a expliquer, pas un residu admis."""
    assert couple["diff_on"] == [], (
        "le port LIVRE diverge du natif sur %d/%d positions : %r"
        % (len(couple["diff_on"]), couple["n"], couple["diff_on"][:4]))
    assert couple["diff_avant"], (
        "le port d'AVANT ne diverge NULLE PART : le montage ne discrimine rien, "
        "l'accord ci-dessus serait tautologique")
    assert len(couple["diff_avant"]) >= 4, (
        "seulement %d/%d positions divergentes pour le port d'AVANT -- contraste trop faible"
        % (len(couple["diff_avant"]), couple["n"]))
    for r in couple["diff_avant"]:
        assert abs(r["port_avant"] - r["natif"]) == 50.0, (
            "chaque divergence du port d'AVANT doit valoir exactement UN bonus de couverture "
            "(c'est le seul terme que le foyer d'adjacence commute) ; obtenu natif=%r avant=%r"
            % (r["natif"], r["port_avant"]))
    # Sur CE montage precis les ecarts sont tous de MEME SENS -- le port d'AVANT declare adjacent
    # un ennemi que la porte ecarte, prend la branche B et verse `+50` la ou le natif ne verse
    # rien. Le SENS n'est PAS une propriete generale : mesure sur la 4e paire de relief du meme
    # board (`probe_433_r4_r2_r4_canaux_adjacence.py --pick 3`), la branche B est au contraire
    # MUETTE (`threshold = 3` non depasse a `d <= 3`) la ou la branche A verse -- le port d'AVANT
    # y SOUS-evalue de 50 sur 16/48 positions. D'ou la valeur absolue ci-dessus.
    assert len({r["port_avant"] - r["natif"] for r in couple["diff_avant"]}) == 1, (
        "les divergences de ce montage doivent etre de meme sens : %r"
        % ({r["port_avant"] - r["natif"] for r in couple["diff_avant"]},))


def test_the_emitted_action_changes_with_the_channel(couple):
    """Consequence OBSERVABLE, et c'est la seule qui compte pour un moteur de decision : les deux
    ports emettent bien un cast de 1077, mais PAS DEPUIS LA MEME TUILE.

    RE-ETALONNE deux fois. Avant #433-r4-r2-r1/-r2 le port emettait `+30` contre un maximum natif
    NEGATIF -- le depassement etait la signature du bug ; les deux seuils portes, le depassement a
    disparu et ce qui se comparait etait « emet / n'emet pas ». Depuis `#433-r4-r2-r4`, la
    contre-epreuve n'eteint plus la ligne de vue en meme temps que l'adjacence, donc les deux
    branches versent : le discriminant devient la POSITION choisie, confrontee a ce que le natif
    attribue A CETTE POSITION.

      * port LIVRE   -> une tuile ou le natif atteint son MAXIMUM du sweep ;
      * port d'AVANT -> une tuile que le natif evalue STRICTEMENT en dessous (il y declare adjacent
        un ennemi que la porte d'elevation ecarte, donc verse `+50` a tort et deplace l'argmax).

    NB : « le port emet » n'est pas « le natif caste » -- le Bucket natif de ce playbook n'a pas de
    `min` (residu `#433-r4-r2-r3`)."""
    avant, on = couple["cand_avant"], couple["cand_on"]
    natif_par_pos = {r["pos"]: r["natif"] for r in couple["rows"]}
    O = tuple(couple["O"])
    for tag, cand in (("AVANT", avant), ("LIVRE", on)):
        assert cand and cand[0]["ability"] == P.ABILITY, \
            "port %s : un cast de %d est attendu (obtenu %r)" % (tag, P.ABILITY, cand)
    assert on != avant, "l'action emise ne change pas avec le foyer d'adjacence"
    pos_on = tuple(on[0]["to"]) if on[0]["to"] is not None else O
    pos_avant = tuple(avant[0]["to"]) if avant[0]["to"] is not None else O
    assert couple["native_best"] is not None
    assert natif_par_pos.get(pos_on) == couple["native_best"], (
        "le port LIVRE choisit %r, que le natif evalue %r alors que son maximum de sweep est %r"
        % (pos_on, natif_par_pos.get(pos_on), couple["native_best"]))
    assert natif_par_pos.get(pos_avant) is not None \
        and natif_par_pos[pos_avant] < couple["native_best"], (
        "le port d'AVANT choisit %r, que le natif evalue %r : sans ecart au maximum natif (%r) "
        "cette contre-epreuve ne demontre aucun gain de decision"
        % (pos_avant, natif_par_pos.get(pos_avant), couple["native_best"]))
