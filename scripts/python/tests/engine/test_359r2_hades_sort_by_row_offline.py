"""#359-r2 -- l'ORDRE du selecteur de `1147 HadesAutocannons`, et le SENS que lui donne l'equipe.

`IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` finit par
trois noeuds que le port n'avait pas, lus VERBATIM au decompile :

    desc = IdunBattleLogic.Entities.DSLSelectors$$SortByRow(Tiles(w), 0, 0, false)
    asc  = IdunBattleLogic.Entities.DSLSelectors$$SortReverse(desc)
    return IdunBattleLogic.Entities.DSLSelectors$$If(
               IdunBattleLogic.Entities.DSLTriggers$$AreEqual(
                   IdunBattleLogic.Entities.DSLSelectors$$CurrentPlayer(),
                   IdunBattleLogic.Entities.DSLSelectors$$Player(1)),
               desc, asc)

DEUX pieges de lecture, que ce fichier RETIENT parce que la docstring du port etait tombee dans
les deux :

  * `false` est le parametre `ascending` (5e argument de la factory ; champ `+0x38` du ctor
    `IdunBattle.Entities.Selectors.SortByRowSelector$$.ctor(this, tiles, state, pseudoRng,
    sameColumnIsRandom, additionalSortingFormula, ascending)`), et
    `IdunBattle.Entities.Selectors.SortByRowSelector$$Select` prend `OrderByDescending` quand il
    vaut 0. La premiere branche est donc DECROISSANTE -- elle etait nommee `asc`.
  * `Player(1)` prend une **TEAM** (`IdunBattleLogic.Entities.DSLSelectors$$Player` nomme son
    parametre `team` et le passe a `PlayersByTeamSelector$$.ctor(this, state, team)`), pas un
    numero de joueur. Les deux coincident sur un duel 1v1 -- donc l'erreur serait INVISIBLE ici et
    fausse des qu'un camp compte plusieurs joueurs.

CE QUE CE FICHIER NE PROUVE PAS, et le dit : l'ordre des EVENTS emis. Le natif boucle sur le
selecteur TEL QUEL, cible incluse (`includeCenter: 1`), donc la cible principale occupe sa place
TRIEE (mesure #359 : natif `[113, 110, 116]`). Le port, lui, l'extrait du set et l'emet en TETE,
pour toutes les abilities AoE -- residu `#359-r5`. L'etage teste ici est le SELECTEUR.

DECLENCHEUR ci-dessous : `chemins` VIDE, mesure de `probe_486r15 --proposer` (la fermeture
d'imports tient dans la cascade derivee du foyer, qu'on ne redeclare pas -- #531).

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": True,
    "raison": "`chemins` VIDE parce que `probe_486r15 --proposer` mesure que la fermeture d'imports "
              "de ce fichier (474 modules) tient ENTIEREMENT dans la cascade derivee du foyer, "
              "qu'on ne redeclare pas (#531) -- rien ne reste a borner, et un perimetre vide avec "
              "`toujours: False` ne serait JAMAIS rejoue. D'ou `toujours: True` : le fichier est "
              "offline et court (7 tests, ~2 s, aucun runner). Ce qu'il garde justifie de le "
              "rejouer toujours : le SENS du tri et l'ancre d'equipe sont deux litteraux relus au "
              "decompile (`ascending = false`, `Player(<team>)`), et se tromper sur l'un comme sur "
              "l'autre est SILENCIEUX -- l'ensemble reste identique, seul l'ordre change, et la "
              "garde live compare des ensembles. `build: False` : rien n'est fige depuis le "
              "binaire, c'est le texte de la citation qui tient les deux litteraux, pas une table.",
}

import pytest

from engine.dsl import nodes as dsl
from engine.entities.abilities.ability_configuration import AbilityConfiguration
from engine.entities.abilities.active_ability import HadesAutocannonsAbility
from engine.entities.selectors.geometry import SortByRow
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.unit_context import UnitContext
import gameconfig as GC

_RANGE = 2


def _u(uid, team, pos, summon):
    return {"id": uid, "team": team, "pos": {"col": pos[0], "row": pos[1]}, "alive": True,
            "hp": 100, "traits": [int(UnitTrait.Summon)] if summon else []}


def _cfg():
    return AbilityConfiguration(name="HadesAutocannons", variables={},
                                constants={"range": _RANGE})


def _ability():
    return HadesAutocannonsAbility(ability_type=1147, caster=UnitContext(entity_id=1),
                                   config=_cfg(), ability_state={"level": 1, "multiplier": 100})


def _units():
    """Rows 6 / 3 / 5 pour les summons, 4 pour la cible : l'ordre par ROW contredit l'ordre d'ID
    ET l'ordre d'insertion. Sans tri, les trois regimes rendraient la meme liste."""
    return [_u(1, team=1, pos=(0, 0), summon=False),      # caster
            _u(10, team=2, pos=(3, 4), summon=True),      # cible, row 4 (includeCenter)
            _u(11, team=2, pos=(3, 6), summon=True),      # row 6
            _u(12, team=2, pos=(3, 3), summon=True),      # row 3
            _u(13, team=2, pos=(3, 5), summon=True)]      # row 5


def _ctx(units, cur_team):
    by = {u["id"]: u for u in units}
    return dsl.DslContext(units=units, caster=by[1], target=by[10], config=_cfg(), ability_level=1,
                          has_trait=lambda u, t: int(t) in ((u or {}).get("traits") or []),
                          current_player_team=cur_team)


def _rows(lst):
    return [u["pos"]["row"] for u in lst]


def test_range_constant_still_matches_the_montage():
    """Le `range` n'est pas ecrit en dur : il est RELU du gameconfig et confronte a la constante du
    montage, pour qu'un changement de config fasse rougir ICI plutot que de fausser le test en
    silence (meme garde que `test_1147_aoe_set_mirrors_its_native_selector`)."""
    assert int((GC.ability("HadesAutocannons") or {}).get("constants", {}).get("range")) == _RANGE


def test_team1_sorts_by_row_descending():
    """`ascending = false` -> `OrderByDescending`. C'est LA branche que la docstring nommait `asc`."""
    got = _ability().get_aoe_targets(_ctx(_units(), cur_team=1))
    assert _rows(got) == [6, 5, 4, 3], (
        "team courante = 1 : rows %s -- attendu decroissant [6, 5, 4, 3] ; si c'est [3, 4, 5, 6], "
        "le sens d'`ascending` a ete relu a l'envers" % _rows(got))


def test_other_team_sorts_by_row_ascending():
    """L'autre branche du `If` = `SortReverse(desc)` -> croissant."""
    got = _ability().get_aoe_targets(_ctx(_units(), cur_team=2))
    assert _rows(got) == [3, 4, 5, 6], (
        "team courante = 2 : rows %s -- attendu croissant [3, 4, 5, 6]" % _rows(got))


def test_the_two_branches_are_exact_mirrors_and_keep_the_same_set():
    """Un TRI ne filtre RIEN. C'est ce qui distingue un bug d'ordre d'un bug d'ensemble -- et c'est
    la propriete que la garde live (qui compare des ENSEMBLES) continuerait de voir verte si le tri
    se mettait a perdre une entite."""
    units = _units()
    d = _ability().get_aoe_targets(_ctx(units, cur_team=1))
    a = _ability().get_aoe_targets(_ctx(units, cur_team=2))
    assert [u["id"] for u in d] == list(reversed([u["id"] for u in a]))
    assert {u["id"] for u in d} == {u["id"] for u in a} == {10, 11, 12, 13}


def test_unmeasured_current_team_degrades_to_the_false_branch():
    """TRI-ETAT. `current_player_team = None` = **non mesure** -> `CurrentPlayerIsOfTeam` rend False
    -> branche FAUSSE (croissante). Degradation NOMMEE : on ne devine jamais une equipe. Le regime
    existe pour de bon -- un `DslContext` construit hors du seam de prediction n'a pas ce canal."""
    got = _ability().get_aoe_targets(_ctx(_units(), cur_team=None))
    assert _rows(got) == [3, 4, 5, 6]


def test_sort_is_stable_on_row_ties():
    """`Enumerable.OrderBy`/`OrderByDescending` sont STABLES, `sorted` aussi : deux entites de meme
    row gardent l'ordre du selecteur SOURCE. Sans stabilite, l'ordre natif serait irreproductible
    des qu'un plateau aligne deux summons sur la meme rangee -- le cas le plus banal."""
    units = [_u(1, team=1, pos=(0, 0), summon=False),
             _u(10, team=2, pos=(3, 4), summon=True),
             _u(21, team=2, pos=(2, 5), summon=True),     # meme row que 22
             _u(22, team=2, pos=(4, 5), summon=True)]
    got = _ability().get_aoe_targets(_ctx(units, cur_team=1))
    src = [u["id"] for u in got if u["pos"]["row"] == 5]
    assert src == sorted(src), (
        "ex aequo de row rendus dans l'ordre %s : le tri n'est pas stable" % src)


def test_les_deux_options_de_tri_sont_PORTEES_et_degradent_en_le_DISANT():
    """CE TEST ETAIT UN GARDE DE RESIDU PERIME, ET IL RENDAIT `master` ROUGE. Il exigeait un
    `NotImplementedError` sur `sameColumnIsRandom` et `additionalSortingFormula` : le second a ete
    porte par #1027 (le `raise` a disparu, le test est reste), le premier par #1027-r1. Un garde
    qui survit a ce qu'il gardait n'est pas un garde -- c'est une passe rouge de plus.

    Ce qu'il garde DESORMAIS, et qui est la vraie chose a ne pas <<simplifier>> : les deux options
    sont evaluables, et quand leur substrat manque le noeud rend l'ordre SOURCE **sans tirer**, ce
    qui est *un* des ordres que le natif peut rendre -- jamais un ordre invente.
    (Le port POSITIF des deux options vit a l'etage 6 et a l'etage 9 de
    `tests/engine/runner/test_1027_belisarius_actives_offline.py`, avec son call-site.)"""
    src = dsl.UnitSet([_u(2, 1, (0, 1), True), _u(3, 1, (1, 1), True)])
    ctx = dsl.DslContext(units=[])          # ni `board`, ni `pseudo_rng_next` : hors runner
    ordre = [u["id"] for u in SortByRow(src).evaluate(ctx)]
    assert [u["id"] for u in SortByRow(src, same_column_is_random=True).evaluate(ctx)] == ordre, (
        "sans canal PRNG, `sameColumnIsRandom` ne doit RIEN changer -- et surtout pas lever")

    class _Zero:
        def evaluate(self, c):
            return 0

    assert [u["id"] for u in SortByRow(src, additional_sorting=_Zero()).evaluate(ctx)] == ordre, (
        "une formule secondaire CONSTANTE ne departage rien : l'ordre source stable tient")
