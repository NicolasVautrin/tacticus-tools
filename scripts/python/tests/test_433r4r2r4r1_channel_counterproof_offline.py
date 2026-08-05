"""#433-r4-r2-r4-r1 -- GARDE d'une contre-epreuve qui neutralise UN CANAL.

CE QU'IL FERME. `#433-r4-r2-r4` a mesure qu'une contre-epreuve de la forme « je neutralise le canal
X, le port doit alors diverger » CESSE DE MORDRE des qu'un canal Y redondant apparait -- sans
erreur, sans que son propre code change. Le test devient rouge pour une raison qui accuse le PORT,
et le rouge a survecu a TROIS merges (bisect : 3 passed a `3dbcd330`, 3 failed a `489bb349`).

Le helper `counterproof.assert_channel_counterproof*` mesure les TROIS causes au lieu de les
confondre, sur le MEME etat :

    seul != base                 -> la mutation MORD          -> silence
    seul == base != tous         -> un AUTRE canal l'exclut   -> InertCounterproof, canal NOMME
    seul == base == tous         -> l'etat est hors regime    -> UnconfrontableSample

CE FICHIER EST LA CONTRE-EPREUVE DU GARDE : il REND une contre-epreuve muette artificiellement --
en peuplant le second canal -- et exige que le helper morde ET nomme le concurrent. Un garde dont
on ne prouve pas qu'il mord est un inventaire deguise (`probe_181` avant #430).

Le montage n'est PAS synthetique : c'est le foyer REEL (`engine.battle_query.is_adjacent`) et la
paire de canaux REELLE (`elev_by_pos` / `neigh_by_pos`), c'est-a-dire exactement ceux qui ont paye.

OFFLINE -- joue par `probe_457` (perimetre DERIVE de `git ls-files scripts/python/tests`).
ASCII only (cp1252).
"""
from __future__ import annotations

import dataclasses

import pytest

import hexgeo
from counterproof import (InertCounterproof, UnconfrontableSample,
                          assert_channel_counterproof_call, assert_channel_counterproof_ctx)
from engine import battle_query as bq

O = (3, 2)


def _voisins():
    return list(hexgeo.neighbors(O[0], O[1]))


# --------------------------------------------------------------------- 1. la mutation MORD

def test_a_single_bearer_channel_stays_silent():
    """`elev_by_pos` EXCLUT, `neigh_by_pos` NON (la liste stockee contient bien l'arete) : couper
    l'elevation restitue l'adjacence, donc la contre-epreuve discrimine et le helper se tait.

    C'est le regime d'AVANT `489bb349`, celui pour lequel la contre-epreuve de `#433-r4-r2` avait
    ete ecrite -- et elle etait juste."""
    haut = _voisins()[1]
    assert_channel_counterproof_call(
        bq.is_adjacent, "elev_by_pos",
        tile=O, pos=haut,
        elev_by_pos={O: 2, haut: 4},                 # |dElev| = 2 -> exclut
        neigh_by_pos={O: _voisins()})                # l'arete y EST -> n'exclut pas


# ------------------------------------------------- 2. LE PIEGE : deux canaux, meme exclusion

def test_a_redundant_channel_makes_the_counterproof_bite_and_names_it():
    """LE COEUR. Les DEUX canaux excluent la meme arete -- exactement ce que `489bb349` a produit :
    `is_adjacent` enumere desormais la liste STOCKEE, qui a DEJA traverse la porte d'elevation.

    Couper `elev_by_pos` seul ne restitue plus rien. L'ancien code, lui, assertionnait le RESULTAT
    et rendait un rouge qui parlait du port. Ici le helper leve `InertCounterproof` et NOMME
    `neigh_by_pos` : le lecteur sait, a la premiere ligne, qui accuser."""
    haut = _voisins()[1]
    autres = [q for q in _voisins() if q != haut]
    with pytest.raises(InertCounterproof) as ei:
        assert_channel_counterproof_call(
            bq.is_adjacent, "elev_by_pos",
            tile=O, pos=haut,
            elev_by_pos={O: 2, haut: 4},             # |dElev| = 2 -> exclut
            neigh_by_pos={O: autres})                # l'arete N'Y EST PAS -> exclut AUSSI
    msg = str(ei.value)
    assert "neigh_by_pos" in msg, "le canal CONCURRENT doit etre nomme : %r" % msg[:200]
    assert "elev_by_pos" in msg, "le canal NEUTRALISE doit etre nomme : %r" % msg[:200]
    assert "#433-r4-r2-r4" in msg, "le remede doit renvoyer au cas qui a paye : %r" % msg[:300]


def test_the_named_competitor_is_the_one_that_actually_restores():
    """Le diagnostic ne vaut QUE s'il traverse les DERIVEES du foyer, pas seulement le foyer nu.

    `count_adjacent` delegue a `is_adjacent` et propage les deux canaux : une contre-epreuve ecrite
    sur la derivee doit etre attribuee comme celle ecrite sur le foyer. C'est le cas de 5 des
    9 foyers a canaux redondants mesures (`count_adjacent`, `count_adjacent_matching`,
    `are_entities_adjacent`, `is_charging`, `newly_adjacent_ids`)."""
    haut = _voisins()[1]
    autres = [q for q in _voisins() if q != haut]
    with pytest.raises(InertCounterproof) as ei:
        assert_channel_counterproof_call(
            bq.count_adjacent, "elev_by_pos",
            tile=O, positions=[haut],
            elev_by_pos={O: 2, haut: 4},
            neigh_by_pos={O: autres})
    assert "`neigh_by_pos`" in str(ei.value)


# --------------------------------------------------------- 3. l'etat qui ne confronte RIEN

def test_an_out_of_regime_state_is_named_as_such_not_as_a_dead_counterproof():
    """Deux voisins PLATS, arete presente : aucun canal n'exclut. Couper tout ne change rien.

    C'est une TROISIEME cause, et la confondre avec les deux autres enverrait re-crafter la
    mutation alors que c'est l'ETAT qu'il faut refaire. D'ou `UnconfrontableSample`."""
    plat = _voisins()[0]
    with pytest.raises(UnconfrontableSample) as ei:
        assert_channel_counterproof_call(
            bq.is_adjacent, "elev_by_pos",
            tile=O, pos=plat,
            elev_by_pos={O: 2, plat: 2},
            neigh_by_pos={O: _voisins()})
    assert "hors regime" in str(ei.value) or "ne confronte RIEN" in str(ei.value)


def test_an_unknown_channel_is_refused_instead_of_silently_passing():
    """Un canal absent de la signature ne doit pas rendre VERT : c'est le mode de defaillance des
    contre-epreuves ecrites contre un foyer qui a change de vocabulaire."""
    with pytest.raises(UnconfrontableSample) as ei:
        assert_channel_counterproof_call(
            bq.is_adjacent, "elevation_map",              # nom PERIME
            tile=O, pos=_voisins()[0], elev_by_pos={O: 2})
    assert "signature" in str(ei.value)


# ------------------------------------------------ 4. la facade CONTEXTE (la forme du bug)

@dataclasses.dataclass
class _Ctx:
    """Contexte MINIMAL a deux canaux -- la forme exacte de `NCContext` pour ce qui nous occupe.

    Le test ne construit pas un `NCContext` complet a dessein : ce qu'il garde est la DERIVATION
    des canaux par `dataclasses.fields`, pas le playbook. Un champ ajoute ici entre dans le calcul
    sans qu'aucune ligne du helper ne bouge -- c'est tout l'objet."""
    elev_by_pos: dict | None = None
    neigh_by_pos: dict | None = None


def _adjacents(ctx) -> set:
    """Le consommateur : quels voisins de `O` le foyer declare-t-il adjacents ?"""
    return {q for q in _voisins()
            if bq.is_adjacent(O, q, ctx.elev_by_pos, ctx.neigh_by_pos)}


def test_the_context_facade_derives_its_channels_from_the_dataclass():
    """La facade CONTEXTE mord sur le meme piege, et sans qu'on lui donne la liste des canaux."""
    haut = _voisins()[1]
    autres = [q for q in _voisins() if q != haut]
    # canal SEUL porteur -> silence
    assert_channel_counterproof_ctx(
        _adjacents, _Ctx(elev_by_pos={O: 2, haut: 4}, neigh_by_pos={O: _voisins()}),
        "elev_by_pos")
    # canal REDONDANT -> mord, et nomme
    with pytest.raises(InertCounterproof) as ei:
        assert_channel_counterproof_ctx(
            _adjacents, _Ctx(elev_by_pos={O: 2, haut: 4}, neigh_by_pos={O: autres}),
            "elev_by_pos")
    assert "neigh_by_pos" in str(ei.value)


def test_the_context_facade_refuses_a_field_that_does_not_exist():
    with pytest.raises(UnconfrontableSample):
        assert_channel_counterproof_ctx(_adjacents, _Ctx(elev_by_pos={O: 2}), "walkable_by_pos")


# ------------------------------------------- 5. le REJEU du 2026-08-04, sur le vrai playbook

def test_the_real_2026_08_04_regression_is_now_attributed_to_the_counterproof():
    """LE REJEU. Meme playbook, meme foyer, meme paire de canaux que le rouge qui a survecu a trois
    merges -- on le reproduit en peuplant `neigh_by_pos` dans le contexte du test offline, ce que
    `489bb349` a rendu decisif.

    AVANT ce garde : l'assertion `adjacent_at_origin(ctx_off) == {haut}` echouait avec un message
    qui parlait du port. APRES : `InertCounterproof` nomme `neigh_by_pos` a la premiere ligne.

    Le contexte est celui du fichier de gardes de `#433-r4-r2` -- pas une maquette."""
    from engine.playbook.noncomparable import NCContext
    from engine.playbook.noncomparable.early_warning_override import EarlyWarningOverridePlaybook

    haut = _voisins()[1]
    autres = [q for q in _voisins() if q != haut]
    pb = EarlyWarningOverridePlaybook()

    def _ctx(neigh):
        return NCContext(
            uid=79, origin=O, reach_nc=[], epos=[haut], fpos=[], plan={}, hp_cur_by_id={},
            enemies=[{"id": 900, "visualId": "tauMarksman",
                      "pos": {"col": haut[0], "row": haut[1]}}],
            elev_by_pos={O: 2, haut: 4}, neigh_by_pos=neigh,
            ability_targets=lambda u, a: {"units": []})

    def _adj(ctx):
        return frozenset(pb.adjacent_at_origin(ctx, pb.enemies_of(ctx)))

    # (a) canal de voisinage NON peuplE (l'etat du fichier offline) : la contre-epreuve MORD
    assert_channel_counterproof_ctx(_adj, _ctx({}), "elev_by_pos")

    # (b) canal de voisinage peuplE SANS l'arete (l'etat live depuis `489bb349`) : elle est MUETTE
    with pytest.raises(InertCounterproof) as ei:
        assert_channel_counterproof_ctx(_adj, _ctx({O: autres}), "elev_by_pos")
    assert "neigh_by_pos" in str(ei.value), str(ei.value)[:300]

    # et la MESURE que le message rapporte est vraie : couper l'elevation seule ne restitue rien.
    ctx = _ctx({O: autres})
    assert _adj(ctx) == _adj(dataclasses.replace(ctx, elev_by_pos=None)) == frozenset()
    assert _adj(dataclasses.replace(ctx, elev_by_pos=None, neigh_by_pos=None)) == frozenset([haut])


# ------------------------------------------ 6. le DETECTEUR du probe, garde dans les 3 sens

def test_the_probe_classifier_separates_the_three_regimes():
    """AUTO-TEST du detecteur de `probe_433_r4_r2_r4_r1_contre_epreuves.classer_appel`.

    Le probe rend `VERDICT: PASS` -- et un PASS ne vaut RIEN si son detecteur a cesse de mordre
    (c'est ce que `probe_181` faisait avant #430 : un inventaire deguise en garde-fou). Les trois
    regimes sont donc fixes ici, sur le foyer REEL, et dans les trois sens."""
    import probe_433_r4_r2_r4_r1_contre_epreuves as P

    haut = _voisins()[1]
    plat = _voisins()[0]
    autres = [q for q in _voisins() if q != haut]

    # (1) PORTEUR UNIQUE : seule l'elevation exclut -- la couper restitue
    cl = P.classer_appel(bq.is_adjacent, (O, haut),
                         {"elev_by_pos": {O: 2, haut: 4}, "neigh_by_pos": {O: _voisins()}})
    assert cl["regime"] == "porteur_unique" and cl["uniques"] == ["elev_by_pos"], cl
    # `neigh_by_pos` y figure en `concurrents` -- il n'exclut simplement PAS. Ce n'est pas une
    # redondance, et les confondre surevaluait le gisement d'un facteur ~3.
    assert cl["concurrents"] == ["neigh_by_pos"], cl

    # (2) REDONDANT : les DEUX excluent -- en couper un seul ne restitue rien
    cl = P.classer_appel(bq.is_adjacent, (O, haut),
                         {"elev_by_pos": {O: 2, haut: 4}, "neigh_by_pos": {O: autres}})
    assert cl["regime"] == "redondant", cl
    assert set(cl["concurrents"]) == {"elev_by_pos", "neigh_by_pos"} and not cl["uniques"], cl

    # (3) INERTE : aucun canal n'exclut -- il n'y a rien a restituer
    cl = P.classer_appel(bq.is_adjacent, (O, plat),
                         {"elev_by_pos": {O: 2, plat: 2}, "neigh_by_pos": {O: _voisins()}})
    assert cl["regime"] == "inerte", cl

    # (4) HORS GISEMENT : aucun canal actif -> `None`, jamais un verdict fabrique
    assert P.classer_appel(bq.is_adjacent, (O, plat), {}) is None


def test_the_probe_classifier_survives_compensating_channels():
    """LE PIEGE QUI A FAIT RATER 8 FAUX NEGATIFS AU PREMIER JET : deux canaux de sens OPPOSES.

    Ici couper `a_by_pos` RESTREINT et couper `b_by_pos` ELARGIT, si bien que les couper TOUS LES
    DEUX rend le verdict de depart. Un detecteur qui conclurait « aucun canal ne mord » de ce
    `tous == base` declarerait MUETTE une contre-epreuve qui mord parfaitement."""
    import probe_433_r4_r2_r4_r1_contre_epreuves as P

    def foyer(x, a_by_pos=None, b_by_pos=None):
        n = 0
        if a_by_pos:
            n += 1
        if b_by_pos:
            n -= 1
        return x + n

    cl = P.classer_appel(foyer, (10,), {"a_by_pos": {1: 1}, "b_by_pos": {1: 1}})
    assert cl["base"] == 10 and cl["tous"] == 10, cl
    assert cl["regime"] == "porteur_unique", cl
    assert set(cl["uniques"]) == {"a_by_pos", "b_by_pos"}, cl
