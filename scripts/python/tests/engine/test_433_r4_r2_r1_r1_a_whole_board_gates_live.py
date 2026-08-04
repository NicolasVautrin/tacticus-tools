"""LIVE #433-r4-r2-r1-r1-a -- la zone des `UseWholeBoard` dont le gate n'avait pas ete lu.

CE QUE CE FICHIER MESURE, et pourquoi il ne peut pas etre offline : la question est « le natif
met-il cette tuile dans la zone de menace de cette unite », et le seul oracle est le natif lui-meme.
On l'isole par la branche A d'`EarlyWarningOverridePlaybook` -- `bonus = util + 10 * Sum_E d(P,E)`
vaut `0` exactement quand `IdunBattle.Core.Services.BattleQuery$$IsTileInRangeOfAnyAbility` est vrai,
et `50` sinon -- sur un sweep de 40 positions `d = 2..10`, avec EXACTEMENT UN ennemi vivant (sans
quoi la partition n'est attribuable a aucun kit).

LE MONTAGE EST DISCRIMINANT PAR CONSTRUCTION. L'ability est GREFFEE seule sur `custoBladeChampion`,
dont l'arme est de MELEE (`unit_weapon_range == 1`) : les deux modeles en competition rendent alors
`40/40` (zone = plateau entier) ou `0/40` (zone vide), et le sweep commence a `d = 2`. Le probe
REFUSE un greffon dont l'arme porterait plus loin -- sans quoi « zone = portee d'arme » donnerait le
bon resultat par coincidence.

COUT : chaque test monte un runner (plus un, memoise, pour lire le board). Trois tests, choisis pour
couvrir les TROIS verdicts du cas : zone vide, plateau entier, et l'ATTRIBUTION de l'ecart residuel.
ASCII only.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r2_r1_r1_a_whole_board_gates as P
from rl_collect_batch import _resolve_session


@pytest.fixture(scope="module")
def sid():
    s = _resolve_session()
    if not s:
        pytest.skip("aucune session Frida")
    return s


def _ok(res):
    if "error" in res:
        pytest.fail("montage REFUSE : %s" % res["error"])
    return res


def test_a_friendly_only_whole_board_ability_contributes_no_tile(sid):
    """`1100 SorcerousFacade` sur son porteur NATIF `thousTzaangor` -- dont c'est la SEULE active.

    `TargetingQuery$$GetPossibleTargetTiles` court-circuite sur `TargetIsFriendly` sans
    `TargetIsEnemy` et rend un ensemble VIDE : il ne doit rester que l'arme, de portee 2. Le port
    d'avant cette tranche rendait le plateau entier -- 38 faux positifs sur ce meme sweep.

    Aucune greffe ici : c'est le cas le plus fort du fichier, le kit natif du jeu."""
    res = _ok(P.sweep(sid, "thousTzaangor"))
    assert res["exact"], "FP=%r FN=%r" % (res["faux_positifs"], res["faux_negatifs"])
    par_d = res["par_distance"]
    assert par_d[2] == (2, 2), "a d = 2 l'arme porte : %r" % (par_d,)
    for d, (n, _tot) in par_d.items():
        if d > 2:
            assert n == 0, "d = %d devrait etre HORS zone (l'ability n'apporte rien) : %r" % (d, par_d)


def test_a_read_gate_that_does_not_bite_keeps_the_whole_board(sid):
    """`1145 SporeMineLauncher`, greffee seule. Son gate teste
    `IdunBattle.Entities.TileExtensions$$HasSteppableUnit` sur la tuile : faux sur une tuile libre,
    donc il ne retire RIEN et la zone reste le plateau entier.

    C'est le pendant exact du test precedent, et le contraste avec lui est ce qui prouve que le
    port ne rend pas simplement « toujours le plateau » ni « jamais »."""
    seed, reports = P._grafted_seed(1145)
    assert reports and reports[0]["activeAbilitiesAfter"] == [1145], "greffe : %r" % (reports,)
    res = _ok(P.sweep(sid, P.GRAFT_HOST, seed, [1145]))
    assert res["entity_abilities"] == [1145], "l'ENTITE doit ne porter que la greffe"
    assert res["exact"], "FP=%r FN=%r" % (res["faux_positifs"], res["faux_negatifs"])
    for d, (n, tot) in res["par_distance"].items():
        assert n == tot, "d = %d : le plateau ENTIER est attendu, lu %d/%d" % (d, n, tot)


def test_the_residual_gap_belongs_to_the_obscuring_stage_not_to_the_gate(sid):
    """L'ATTRIBUTION, et c'est ce qui empeche d'imputer au gate un ecart qui ne lui appartient pas.

    `1161 TwinSmartMissileSystem` n'a AUCUN gate -- `GetPossibleTargetsForOptions` ne construit le
    troisieme predicat que `if ((rules & 2) != 0)`, et son masque ne porte pas ce bit. Elle n'a pas
    non plus `AllowObscuredTargetByElevation` / `AllowObscuredTargetByWalls`. L'ecart qu'elle
    montre est donc integralement celui du DEUXIEME predicat -- le residu `#433-r4-r2-r1-r2`.

    On verrouille deux choses : que cet ecart existe (sinon ce test dormirait), et qu'il soit un
    SOUS-ENSEMBLE de celui de `1168 EntropyCannons`, dont le gate ajoute exactement la tuile
    OCCUPEE par le caster."""
    witness = _ok(P.sweep(sid, P.GRAFT_HOST, *_graft(1161)))
    assert witness["entity_abilities"] == [1161]
    assert witness["faux_negatifs"] == [], "le port ne doit jamais RETRECIR : %r" % (witness,)
    assert witness["faux_positifs"], \
        "l'etage d'obscurcissement ne mord plus : ce test ne prouve plus rien, le relire"

    gated = _ok(P.sweep(sid, P.GRAFT_HOST, *_graft(1168)))
    assert gated["entity_abilities"] == [1168]
    assert gated["faux_negatifs"] == []
    wit, gat = set(map(tuple, witness["faux_positifs"])), set(map(tuple, gated["faux_positifs"]))
    assert wit <= gat, "l'ecart SANS gate doit etre inclus dans l'ecart AVEC : %r vs %r" % (wit, gat)
    extra = gat - wit
    assert extra == {tuple(gated["O"])}, \
        "le seul ajout du gate doit etre la tuile OCCUPEE par le caster : %r" % (extra,)


def _graft(aid):
    seed, reports = P._grafted_seed(aid)
    assert reports and reports[0]["activeAbilitiesAfter"] == [aid], "greffe %d : %r" % (aid, reports)
    return seed, [aid]
