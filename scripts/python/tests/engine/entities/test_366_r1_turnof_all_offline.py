"""#366-r1-turnof -- le noeud `IsTurnOf` agrege par `all`, et le set VIDE rend VRAI.

RE : `docs/rl/case-366-r1-turnof-all.md`. Le natif est
`IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger`, dont la boucle est

    foreach (e in selector.<slot 6>(ctx, selectionType = 0))
        if (e.GetComponent<OwnerComponent>().CurrentPlayerEntityId != ctx.CurrentPlayer.Id)
            return false;                 # sort FAUX des qu'UNE entite diverge
    return true;                          # enumeration epuisee (set VIDE inclus) -> VRAI

Le port agregeait par `any(...)` : sur un set d'UN element les deux agregations coincident (c'est
pour cela que l'ecart etait INERTE), elles divergent des DEUX cotes du set a >= 2 elements ET sur le
set vide. Ces cliquets verrouillent les quatre faces :

  * **le DISCRIMINANT** (2 unites, equipes differentes) : `all` FERME, `any` OUVRE ;
  * **le set VIDE rend VRAI** -- la face la plus facile a re-casser en croyant << durcir >> (un
    `if not units: return False` conservateur serait un mirror FAUX) ;
  * **la garde de tete** (`ctx@+0x50 == 0 -> return false`) n'est PAS mangee par la verite vacue :
    sans joueur courant, VIDE ou pas, le noeud rend FAUX ;
  * **le regime SINGLETON reste inchange** -- c'est la totalite des call-sites natifs du build
    (case-doc sec.3), donc la non-regression de tout ce qui consomme deja `IsTurnOf`.

Le montage passe par le VRAI selecteur du port (`Units(<tiles>)` = mirror d'
`IdunBattle.Entities.Selectors.UnitsOnTilesSelector`), c'est-a-dire la FORME EXACTE du seul
call-site natif a selecteur de collection (`IdunBattle.Entities.Effects.FirstAidHealEffect$$
CreateTargetTrigger` = `On(0x13) & IsTurnOf(Units(Owner))`) -- avec DEUX tuiles la ou le natif n'en
a qu'une (l'`Owner` d'un effet de tuile). C'est precisement pourquoi la geometrie discriminante
n'est pas atteignable LIVE : cf. la case-doc sec.3 et sec.6.

100 % OFFLINE (aucun board, aucun runner) : le noeud ne lit que `ctx.current_player_id` et le
champ `player` des unites. ASCII only.
"""
from __future__ import annotations

from engine.dsl.base import DslContext
from engine.entities.selectors import FixedTiles, Owner, Units
from engine.entities.triggers import IsTurnOf

ME, FOE = 1, 2
T_A, T_B, T_EMPTY = (1, 1), (2, 2), (5, 5)


def _u(uid, pos, player):
    return {"id": uid, "pos": {"col": pos[0], "row": pos[1]}, "team": player, "player": player,
            "alive": True, "hp": 100}


def _ctx(units, current=ME, owner=None):
    return DslContext(units=list(units), owner=owner, caster=owner, current_player_id=current)


def _on_tiles(*tiles):
    """`Units(<tiles>)` -- le mirror du `UnitsOnTilesSelector` que le natif passe a `IsTurnOf`."""
    return Units(FixedTiles(list(tiles)))


# --------------------------------------------------------------- le DISCRIMINANT : 2 entites, 2 camps

def test_two_selected_units_of_different_players_close_the_gate():
    """LA face qui separe `all` de `any`. Le natif sort FAUX des qu'UNE entite selectionnee
    n'appartient pas au joueur courant -> ici l'ennemi ferme le noeud, MEME si l'autre selectionnee
    est bien a moi. Sous l'ancien `any(...)`, ce cas rendait VRAI."""
    units = [_u(10, T_A, ME), _u(20, T_B, FOE)]
    ctx = _ctx(units)
    sel = _on_tiles(T_A, T_B)
    # ANTI-VERT-VACUE : le selecteur doit VRAIMENT rendre les deux unites, sinon le FAUX ci-dessous
    # ne prouverait rien (un set vide rendrait VRAI, un singleton ennemi rendrait FAUX pour la
    # mauvaise raison).
    picked = sel.evaluate(ctx)
    assert [u["id"] for u in picked] == [10, 20], "montage casse : %r" % ([u["id"] for u in picked],)
    assert IsTurnOf(sel).should_trigger(ctx) is False


def test_two_selected_units_of_the_current_player_open_the_gate():
    """Contre-epreuve du precedent, MEME cardinalite : c'est bien l'appartenance qui decide, pas le
    nombre d'entites."""
    units = [_u(10, T_A, ME), _u(20, T_B, ME)]
    ctx = _ctx(units)
    sel = _on_tiles(T_A, T_B)
    assert len(sel.evaluate(ctx)) == 2
    assert IsTurnOf(sel).should_trigger(ctx) is True


def test_the_gate_closes_whichever_of_the_two_is_the_enemy():
    """`all` est symetrique : l'ordre de selection ne doit rien changer (le natif sort au PREMIER
    ecart, quel qu'il soit)."""
    units = [_u(10, T_A, FOE), _u(20, T_B, ME)]
    ctx = _ctx(units)
    assert IsTurnOf(_on_tiles(T_A, T_B)).should_trigger(ctx) is False
    assert IsTurnOf(_on_tiles(T_B, T_A)).should_trigger(ctx) is False


# --------------------------------------------------------------------------- le set VIDE rend VRAI

def test_an_empty_selection_is_vacuously_true():
    """`MoveNext()` faux du premier coup -> `return 1`. Un `if not units: return False`
    << conservateur >> serait un mirror FAUX : ce cliquet l'interdit.

    Cote natif ce regime est atteignable (une tuile VIDE disparait du set : l'enumeration mappe
    chaque entite par `IdunBattle.DSL.TargetsSelector$$SelectUnit`, qui resout une TUILE en son
    occupant et rend `null` s'il n'y en a pas)."""
    ctx = _ctx([_u(10, T_A, ME)])
    sel = _on_tiles(T_EMPTY)
    assert sel.evaluate(ctx) == [], "montage casse : la tuile temoin doit etre VIDE"
    assert IsTurnOf(sel).should_trigger(ctx) is True


def test_a_selector_that_resolves_to_nothing_is_also_vacuously_true():
    """Meme face par l'autre voie du port : un accesseur SINGLETON dont le contexte n'a pas
    l'entite rend `None`, que `_units_of` normalise en `[]`. C'est le meme regime natif (l'entite
    est filtree par `SelectUnit` -> set vide), pas une degradation inventee."""
    ctx = _ctx([_u(10, T_A, ME)], owner=None)
    assert IsTurnOf(Owner()).should_trigger(ctx) is True


# ------------------------------------------------------------- la garde de tete survit a la verite vacue

def test_no_current_player_closes_the_gate_even_on_an_empty_selection():
    """`if (ctx@+0x50 == 0) return false;` est EN TETE, AVANT toute enumeration : sans joueur
    courant le noeud rend FAUX, y compris sur le set vide qui rendrait VRAI autrement. C'est la
    seule interaction entre les deux nouveautes de ce cas."""
    ctx = _ctx([_u(10, T_A, ME)], current=None)
    assert IsTurnOf(_on_tiles(T_EMPTY)).should_trigger(ctx) is False
    assert IsTurnOf(_on_tiles(T_A)).should_trigger(ctx) is False


# ------------------------------------------------------- non-regression : le regime SINGLETON natif

def test_a_singleton_owner_keeps_both_polarities():
    """Les 16 operandes natifs du build hors `Player(team)` sont des SINGLETONS (case-doc sec.3) :
    `all` et `any` y coincident, et ce cliquet verrouille qu'aucune polarite n'a bouge."""
    mine, foe = _u(10, T_A, ME), _u(20, T_B, FOE)
    assert IsTurnOf(Owner()).should_trigger(_ctx([mine, foe], owner=mine)) is True
    assert IsTurnOf(Owner()).should_trigger(_ctx([mine, foe], owner=foe)) is False


def test_a_dead_selected_unit_still_counts():
    """`selectionType = 0` ne filtre RIEN : `IdunBattle.Entities.UnitExtensions$$
    MatchesUnitSelectionType` rend VRAI inconditionnellement pour 0 (seuls 1/2/3 testent la vie et
    le flag 0x11). Un porteur MORT reste donc dans le set et continue de decider -- le noeud ne doit
    pas se mettre a l'ignorer."""
    dead_foe = _u(20, T_B, FOE)
    dead_foe["alive"] = False
    dead_foe["hp"] = 0
    assert IsTurnOf(Owner()).should_trigger(_ctx([dead_foe], owner=dead_foe)) is False
    dead_mine = _u(10, T_A, ME)
    dead_mine["alive"] = False
    dead_mine["hp"] = 0
    assert IsTurnOf(Owner()).should_trigger(_ctx([dead_mine], owner=dead_mine)) is True
