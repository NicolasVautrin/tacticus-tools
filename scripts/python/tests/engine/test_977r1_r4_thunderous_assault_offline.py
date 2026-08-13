"""#977-r1 et #977-r4 -- `1043 ThunderousAssault` : le substrat du slot `0x0b`, et un seuil
INDISCERNABLE.

GARDE, 100 % OFFLINE et DETERMINISTE : les trois foyers que le playbook interroge
(`engine.playbook.base.tile_utility`, `...noncomparable._targets.eligible_units_at_position`,
`engine.playbook.displace_utility.*`) sont SUBSTITUES, donc le scenario est choisi, pas subi.
Les trois imports du module sous test sont en FORME B (`import X as _x` puis `_x.f()`), c'est ce
qui rend la substitution MORDANTE -- une forme A gelerait la liaison au chargement et ce fichier
serait un faux vert.

#977-r1 -- LE SLOT EST RESOLU, PLUS SUPPOSE
    `IBattleQuery` slot **`0x0b` = `GetMovableTilesFor`** (3 parametres), mesure au runtime par
    `interfaceSlotProbe` sur `IdunBattle.Core.Services.IBattleQuery` ; table calee par quatre
    ancres concordantes (`0x0d = GetMovablePositionsFor`, `0x0e = GetCurrentAndMovablePositionsFor`,
    `0x40 = HasValidTargets`, `0x42 = GetValidTargets`). Le corps de
    `...ThunderousAssaultPlaybook$$GetHighestTileUtilityUnitCanMoveTo` l'invoque avec
    `(unit, ignoreFlags: 0, options: default)`. C'est le movable SEUL : la position COURANTE n'y
    est pas -- c'est `0x0e` qui la SEED, et ce seed est la seule difference entre les deux slots.

    Le port lisait `ctx.reach_nc` (= `0x0e`), donc l'ORIGINE INCLUSE : `highest` trop grand, gate
    `r.Value >= highest` trop severe, actions REFUSEES que le natif emet.

#977-r4 -- L'ENONCE DU RESIDU EST FAUX, ET C'EST LE VERDICT
    Le residu cherchait « le regime ou le defaut `MIN_UTILITY = 0.0` mord ». Il n'existe pas :
    le gate est STRICT (`util < MIN_UTILITY`), donc `0.0` et `-inf` admettent tous deux `util = 0` ;
    et `util < 0` est INATTEIGNABLE (strategie 1 gatee `diff > 0`, strategie 2 gatee
    `r.Value >= highest` avec `highest` partant de `Fix64(0)`). `-inf` reste ecrit par FIDELITE au
    `Bucket<T>..ctor` a un argument, pas parce qu'un montage l'exigerait.
"""
from __future__ import annotations

import pytest

import engine.playbook.base as _pbbase
import engine.playbook.displace_utility as _displace
import engine.playbook.noncomparable._targets as _T
from engine.playbook.noncomparable._base import NCContext
from engine.playbook.noncomparable.thunderous_assault import ThunderousAssaultPlaybook

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15). Il garde le
#: playbook `1043` et les TROIS foyers qu'il interroge -- ceux-la memes que la contre-epreuve
#: substitue. Un declencheur qui les oublierait serait un FAUX VERT.
DECLENCHEUR = {
    "chemins": (),   # tout est dans la cascade derivee par le foyer (#531)
    "build": False,
    "toujours": False,
    "raison": "100 %% OFFLINE et DETERMINISTE : les trois foyers interroges "
              "(`playbook.base.tile_utility`, `noncomparable._targets`, "
              "`playbook.displace_utility`) sont SUBSTITUES par la fixture, et la carte "
              "d'utilite est CHOISIE. Rien hors de la cascade ne peut faire varier ce "
              "verdict -- ni le gameconfig, ni le build.",
}

ORIGIN = (0, 0)
MOVES = [(1, 0), (2, 0)]
CIBLE = 201
TUILE_CIBLE = (3, 0)


@pytest.fixture
def ctx_1043():
    """`NCContext` minimal du caster de `1043` : origine + deux tuiles de move, dans l'ORDRE natif
    (`reach_nc` = origine en tete, cf. `action_tiles_for`)."""
    return NCContext(uid=101, origin=ORIGIN, reach_nc=[ORIGIN] + MOVES,
                     epos=[TUILE_CIBLE], fpos=[], plan={}, hp_cur_by_id={CIBLE: 100})


@pytest.fixture
def substrat(monkeypatch):
    """Substitue les trois foyers interroges par le playbook. Rend un `poser(util_par_tuile, diff)`
    qui installe une carte d'utilite de tuile CHOISIE et le verdict de la strategie 1."""

    def poser(util_par_tuile: dict, diff: float = 0.0, poussable: bool = True):
        monkeypatch.setattr(_pbbase, "tile_utility",
                            lambda ctx, p: float(util_par_tuile.get(tuple(p), 0.0)))
        monkeypatch.setattr(_T, "eligible_units_at_position",
                            lambda ctx, aid, P: [(CIBLE, TUILE_CIBLE)])
        monkeypatch.setattr(_displace, "pushable_tiles",
                            lambda ctx, P, tgt: [(4, 0)] if poussable else [])
        monkeypatch.setattr(_displace, "target_utility_diff_on_displace",
                            lambda ctx, P, tgt: float(diff))

    return poser


def test_977r1_l_origine_est_exclue_du_highest(ctx_1043, substrat):
    """Le regime DECISIF : l'ORIGINE porte STRICTEMENT la plus haute utilite de tuile.
    Sans l'exclusion, `highest` vaut 100 et la strategie 2 refuse une action que le natif emet."""
    carte = {ORIGIN: 100.0, (1, 0): 10.0, (2, 0): 5.0, TUILE_CIBLE: 50.0}
    substrat(carte, diff=0.0)                      # diff = 0 -> la strategie 1 rend None
    pb = ThunderousAssaultPlaybook()

    # temoin NON DEGENERE : le scenario n'a de sens que si l'origine domine STRICTEMENT.
    assert carte[ORIGIN] > max(carte[t] for t in MOVES), "regime degenere : l'origine ne domine pas"

    highest = pb.highest_tile_utility_unit_can_move_to(ctx_1043)
    assert highest == 10.0, ("highest doit etre le max des tuiles de MOVE seules (10.0), "
                             "l'origine (100.0) n'appartient pas au slot 0x0b ; obtenu %r" % highest)

    r = pb.strategy2(ctx_1043, ORIGIN)
    assert r is not None, "la strategie 2 refuse une action que le natif emet"
    assert r == (CIBLE, 50.0), r


def test_977r1_le_montage_rougirait_avec_l_origine_incluse(ctx_1043, substrat):
    """CONTRE-EPREUVE INTERNE : on RECALCULE `highest` a l'ancienne (origine comprise) et on
    verifie que le gate de la strategie 2 aurait bien BASCULE. Sans cet etage, rien ne dit que le
    scenario est DISCRIMINANT -- il pourrait passer pour les deux implementations."""
    carte = {ORIGIN: 100.0, (1, 0): 10.0, (2, 0): 5.0, TUILE_CIBLE: 50.0}
    substrat(carte, diff=0.0)
    ancien_highest = max([0.0] + [carte[p] for p in ctx_1043.reach_nc])   # origine INCLUSE
    assert ancien_highest == 100.0
    assert not (50.0 >= ancien_highest), "le scenario ne discrimine pas les deux substrats"


def test_977r1_sans_tuile_de_move_le_highest_retombe_sur_son_plancher(substrat):
    """Cas limite : une unite immobile (`reach_nc` = la seule origine). Le natif itere alors sur un
    ensemble VIDE et rend le seed `Fix64(0)` -- pas l'utilite de sa propre tuile."""
    substrat({ORIGIN: 100.0}, diff=0.0)
    ctx = NCContext(uid=101, origin=ORIGIN, reach_nc=[ORIGIN], epos=[], fpos=[], plan={},
                    hp_cur_by_id={})
    assert ThunderousAssaultPlaybook().highest_tile_utility_unit_can_move_to(ctx) == 0.0


def test_977r4_min_utility_est_indiscernable_du_defaut_a_utilite_nulle(ctx_1043, substrat):
    """Le regime que `#977-r4` voulait exercer : utilite EXACTEMENT 0. Les deux seuils ADMETTENT --
    le gate est strict. Ce n'est donc pas un manque de montage, c'est une impossibilite."""
    substrat({ORIGIN: 0.0, (1, 0): 0.0, (2, 0): 0.0, TUILE_CIBLE: 0.0}, diff=0.0)
    pb = ThunderousAssaultPlaybook()
    r_inf = pb.evaluate_at(ctx_1043, ORIGIN)
    assert r_inf == (CIBLE, 0.0), r_inf                    # temoin NON NUL : une action existe

    class _AvecDefaut(ThunderousAssaultPlaybook):
        MIN_UTILITY = 0.0                                  # le defaut de `NonComparablePlaybook`

    assert _AvecDefaut().evaluate_at(ctx_1043, ORIGIN) == r_inf, (
        "les deux seuils divergent a utilite 0 : le gate ne serait pas strict")


@pytest.mark.parametrize("carte,diff", [
    ({ORIGIN: -50.0, (1, 0): -20.0, (2, 0): -30.0, TUILE_CIBLE: -10.0}, -5.0),
    ({ORIGIN: -1.0, (1, 0): -1.0, (2, 0): -1.0, TUILE_CIBLE: -1.0}, 0.0),
])
def test_977r4_aucune_utilite_negative_n_est_atteignable(ctx_1043, substrat, carte, diff):
    """L'autre moitie du verdict : meme en poussant TOUTES les utilites de tuile dans le negatif,
    `evaluate_at` ne rend jamais une utilite `< 0` -- la strategie 1 gate `diff > 0`, et la
    strategie 2 gate `r.Value >= highest`, ou `highest` part du plancher `Fix64(0)`. C'est ce qui
    rend `-inf` et `0.0` STRICTEMENT equivalents sur ce corps."""
    substrat(carte, diff=diff)
    r = ThunderousAssaultPlaybook().evaluate_at(ctx_1043, ORIGIN)
    assert r is None or r[1] >= 0.0, r
