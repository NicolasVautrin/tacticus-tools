"""#547-r13 -- UN CADAVRE NE PORTE AUCUN EFFET, et `KeepOnRevive` n'y peut RIEN.

## La premisse fausse que ce fichier existe pour empecher de renaitre

`#547-r12` a mesure live (trois cadavres, runners 638 et 669, board `MC1_67`) que
`decisionView.units[]` CONSERVE les morts mais qu'ils portent `effects=[]`, y compris sous
`includeInactive: true`. `#547-r13` a oppose a cette mesure une lecture :
`LifewardsProtectingEffect` HERITE `get_KeepOnRevive = True` (`IEffect` slot 2, corps `b0 01 c3`),
donc il DEVRAIT survivre -- << une des deux lectures est fausse >>.

**Les deux sont justes, et c'est la TROISIEME qui etait fausse.** La derivation confirme la valeur
(`probe_547r13_keep_on_revive.py` : defaut de `BaseEffect` = `True`, corps `b0 01 c3`) et
l'observation reste juste. Ce qui etait faux, c'est d'appliquer ce getter au chemin de MORT : le
`if` imbrique de `IdunBattle.Operations.RemoveEffectsOperation$$Execute` porte une CONJONCTION que
le resume avait perdue --

    if (options.step.HasValue && effect.<IEffect slot 4> != options.step.Value) continue
    if (options.<+0x08>       && effect.<IEffect slot 2>)                       continue
        ^^^^^^^^^^^^^^^^ CE conjoint

-- et `options.<+0x08>` vaut **0** aux quatre producteurs de MORT / DESPAWN
(`KillUnitOperation`, `DestroyMachineOperation`, `FleeOperation`, `RemoveUnitOperation`), **1** au
SEUL `IdunBattle.Operations.ReviveUnitOperation$$Execute`. Le slot 2 est donc INERTE sur la mort.

## Les trois etages, et pourquoi le 2 est celui qui mord

  1. **LA CLAUSE PERDUE** -- un effet qui declare `keep_on_revive = True` est retire quand meme.
     Si quelqu'un << corrigeait >> le port d'apres la fausse lecture (ajouter le gate au chemin de
     mort), cet etage rougit. C'est le seul cran qui vise la faute elle-meme.
  2. **LA CONSEQUENCE, DERIVEE** -- la sequence de mort du port joue les steps qu'elle joue (LUS
     dans l'AST de `damage.py`, jamais recopies ici), et leur union COUVRE le domaine complet de
     `KillUnitStep`. Un cadavre ressort donc sans aucun effet. Retirer un des trois appels, ou
     ajouter une valeur de step au domaine sans ajouter la passe, fait rougir cet etage.
  3. **LA VALEUR FIGEE** -- concordance avec l'entree versionnee `metadata/keep_on_revive.tsv`.
     C'est ce qui garantit qu'une future re-derivation retrouve `True` et n'en RE-CONCLUE PAS que
     l'effet survit : le lien entre le getter et l'observable est l'etage 1, pas le getter seul.

Les etages 1 et 2 ne dependent PAS du jeu installe ; seul le 3 skippe sans le build. Ce fichier ne
peut donc jamais rendre `passed == 0 and skipped > 0` (le regime que #455 fait rougir).

ASCII only (console cp1252).
"""
from __future__ import annotations

import ast
import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.effects.base import BaseEffect                        # noqa: E402
from engine.entities.effects_state import EffectsState                     # noqa: E402
from engine.entities.kill_unit_step import KillUnitStep                    # noqa: E402
import engine.runner.operations.damage as DMG                              # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LE SOCLE DE LA DERIVATION (etage 3), qu'aucun import de production n'amene :
        "scripts/python/build_pin.py",
        "scripts/python/il2cpp_metadata.py",
        "scripts/python/probe_175r2_can_be_immune_to.py",
        "scripts/python/probe_547r13_keep_on_revive.py",
        "scripts/python/verdict_cache.py",
        # L'ENTREE VERSIONNEE : elle change au changement de JEU, sans qu'aucun fichier de code ne
        # bouge -- donc AUCUNE cascade d'imports ne la revele. C'est le seul chemin de cette liste
        # que `--proposer` ne pouvait pas voir (il ne lit que les imports, et il le DIT).
        "data/symbols/*/metadata/keep_on_revive.tsv",
    ),
    # DERIVE : l'etage 3 lit `data/symbols/**` du build courant.
    "build": True,
    "toujours": False,
    "raison": ("les cinq chemins que la cascade d'imports ne couvre PAS -- le deriveur du getter "
               "et son socle (`probe_175r2`, `il2cpp_metadata`, `build_pin`, `verdict_cache`) -- "
               "plus l'entree versionnee, seule source de verdict qui bouge sans qu'aucun code ne "
               "bouge. Les foyers que ce fichier garde vraiment (`remove_effects.py`, `damage.py` "
               "dont l'AST est LU, `kill_unit_step.py`, `effects/base.py`) ne sont PAS declares : "
               "ils sont deja dans la cascade DERIVEE par les imports, et les redeclarer serait la "
               "duplication que #531 interdit."),
}

COLS, ROWS, PORTEUR = 5, 5, 20


def _state_reel():
    """Un `State` COMPLET : `remove_effects_operation` ne collecte pas, elle RETIRE (revert des
    modifications, deux events), donc elle a besoin des canaux de `State`."""
    import hexgeo                     # module de `scripts/python`, pas du paquet `engine`
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [c * ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": col * ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    decision = {"currentPlayer": 1, "units": [
        {"id": PORTEUR, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 2, "row": 2}, "effects": []}]}
    observe = {"units": [{"squadId": PORTEUR, "hp": 1000, "hpMax": 1000}]}
    st = load_state(decision, observe, board=Board(tiles, adjacency="evenq"))
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _restants(st) -> list:
    return [int(e.effect_type) for e in st.effects.by_unit.get(PORTEUR, []) if not e.consumed]


# ------------------------------------------------------- etage 1 : LA CLAUSE PERDUE

def test_un_effet_a_keep_on_revive_est_retire_QUAND_MEME_par_la_mort():
    """`options.<+0x08>` vaut 0 au chemin de mort, donc `IEffect` slot 2 n'y est jamais lu.

    L'effet pose ci-dessous DECLARE `keep_on_revive = True` -- l'attribut n'existe nulle part dans
    le port, et c'est le point : s'il en apparaissait un, LU par la boucle de filtrage, ce test
    rougirait immediatement. C'est la contre-epreuve de la fausse lecture de la fiche, pas une
    verification de ce que le port fait aujourd'hui.

    ⚠ TEMOIN NON DEGENERE : on pose DEUX effets de meme step, l'un declarant le flag et l'autre
    non. Les deux doivent partir. Si un seul partait, un gate serait deja la."""
    st = _state_reel()
    garde = BaseEffect(name="garde_au_revive", effect_type=4242, target=PORTEUR)
    garde.keep_on_revive = True                 # attribut ETRANGER au port -- volontairement
    nu = BaseEffect(name="ordinaire", effect_type=4243, target=PORTEUR)
    assert int(garde.remove_on_kill_step) == int(nu.remove_on_kill_step), (
        "les deux temoins doivent partager le meme step, sinon le test compare deux choses")
    st.effects.add_effect(PORTEUR, garde)
    st.effects.add_effect(PORTEUR, nu)
    retires = DMG._kill_unit_remove_effects(st, PORTEUR, int(nu.remove_on_kill_step))
    assert sorted(int(x) for x in retires) == [4242, 4243], retires
    assert _restants(st) == [], _restants(st)


# ------------------------------------------------------- etage 2 : LA CONSEQUENCE, DERIVEE

def _steps_joues_par_la_sequence_de_mort() -> list:
    """Les `KillUnitStep` que la sequence de mort du port joue, DANS L'ORDRE -- LUS dans l'AST de
    `engine/runner/operations/damage.py`.

    Pourquoi l'AST et pas une constante ecrite ici : une liste recopiee ne peut pas voir la
    disparition d'un des trois appels. On visite les `ast.Attribute` de la forme
    `KillUnitStep.<nom>` situes dans la fonction qui porte les cles `kill_remove_effects`, et on
    rend leur ORDRE SOURCE.

    ⚠ Ce recenseur ASSERTE SON PROPRE NON-VIDE : un balayage qui ne trouverait rien (fonction
    renommee, cle changee) rendrait une liste vide, et << aucun step ne survit a zero passe >>
    serait vrai par vacuite."""
    src = Path(DMG.__file__).read_text(encoding="utf-8")
    arbre = ast.parse(src)
    vus = []
    for fn in ast.walk(arbre):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cles = [n.value for n in ast.walk(fn)
                if isinstance(n, ast.Constant) and n.value == "kill_remove_effects"]
        if not cles:
            continue
        for n in ast.walk(fn):
            if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                    and n.value.id == "KillUnitStep"):
                vus.append((n.lineno, n.col_offset, n.attr))
    noms = [a for _l, _c, a in sorted(vus)]
    # dedoublonnage en gardant l'ordre (chaque step apparait deux fois : la cle `step` du trace et
    # l'argument de l'appel).
    ordre, vu = [], set()
    for a in noms:
        if a not in vu:
            vu.add(a)
            ordre.append(a)
    assert ordre, ("le recenseur AST n'a trouve AUCUN `KillUnitStep.<nom>` dans la fonction qui "
                   "porte `kill_remove_effects` -- il ne mesure plus rien")
    return [KillUnitStep[a] for a in ordre]


def test_les_passes_de_la_sequence_de_mort_couvrent_le_domaine_ENTIER():
    """`RemoveEffectsOperation$$Execute` compare le slot 4 a `options.step` par EGALITE. Un effet
    survit donc a la sequence de mort si et seulement si son step n'est joue par AUCUNE passe.

    L'invariant n'est PAS << il y a trois passes >> (un compte se degrade en silence) mais
    << l'union des passes EGALE le domaine >>. Ajouter un membre a `KillUnitStep` sans ajouter la
    passe correspondante fait rougir ici, et c'est exactement le regime ou un cadavre garderait un
    effet."""
    joues = _steps_joues_par_la_sequence_de_mort()
    domaine = {int(s) for s in KillUnitStep}
    assert domaine == {0, 1, 2}, ("le domaine de `KillUnitStep` a bouge : %s" % sorted(domaine))
    assert {int(s) for s in joues} == domaine, (
        "passes jouees %s != domaine %s" % (sorted(int(s) for s in joues), sorted(domaine)))


def test_aucun_effet_ne_survit_a_la_sequence_de_mort():
    """LA CONSEQUENCE OBSERVABLE, celle que `#547-r12` a mesuree live sur trois cadavres.

    On pose UN effet par valeur du domaine (donc un temoin pour chaque passe), on rejoue les passes
    dans l'ordre SOURCE de `damage.py`, et on exige la liste VIDE. Le porteur reste dans l'etat --
    c'est bien le regime << cadavre >> : l'entite survit, ses effets non."""
    joues = _steps_joues_par_la_sequence_de_mort()
    st = _state_reel()
    poses = []
    for s in KillUnitStep:
        e = BaseEffect(name="temoin_%d" % int(s), effect_type=5000 + int(s), target=PORTEUR)
        e.remove_on_kill_step = s
        st.effects.add_effect(PORTEUR, e)
        poses.append(5000 + int(s))
    assert len(set(poses)) >= 2, "temoin DEGENERE : il faut au moins deux steps distincts"
    assert sorted(_restants(st)) == sorted(poses)
    for s in joues:
        DMG._kill_unit_remove_effects(st, PORTEUR, int(s))
    assert _restants(st) == [], (
        "un effet SURVIT a la sequence de mort : %s -- l'observable de #547-r12 est contredit"
        % _restants(st))


def test_aucune_classe_portee_ne_sort_du_domaine_des_steps():
    """Le recensement qui rend l'etage precedent generalisable : TOUTES les classes d'effet du port
    ont un `remove_on_kill_step` DANS le domaine.

    Le balayage importe tout `engine/entities/effects/**` -- pas une liste blanche de modules : une
    liste blanche ne peut pas montrer la classe qu'elle a oubliee. Il asserte son propre non-vide et
    IMPRIME ce qu'il a visite."""
    import engine.entities.effects as PKG
    for m in pkgutil.walk_packages(PKG.__path__, PKG.__name__ + "."):
        try:
            importlib.import_module(m.name)
        except Exception:                        # noqa: BLE001 -- un module non importable est
            continue                             # un autre gisement (#485), pas celui-ci
    vues, pile = set(), [BaseEffect]
    while pile:
        c = pile.pop()
        if c in vues:
            continue
        vues.add(c)
        pile.extend(c.__subclasses__())
    assert len(vues) > 50, ("le balayage n'a visite que %d classes -- il ne mesure rien" % len(vues))
    domaine = {int(s) for s in KillUnitStep}
    hors = sorted((c.__name__, int(c.remove_on_kill_step)) for c in vues
                  if int(getattr(c, "remove_on_kill_step", 1)) not in domaine)
    assert not hors, ("classes hors du domaine `KillUnitStep` : %s" % hors)


# ------------------------------------------------------- etage 3 : LA VALEUR FIGEE

def test_la_valeur_du_getter_concorde_avec_l_entree_versionnee():
    """`get_KeepOnRevive` : le defaut est VRAI, et TROIS classes le renversent.

    C'est la valeur que la fiche `#547-r13` citait, et elle etait JUSTE. La figer ici est ce qui
    empeche la prochaine re-derivation d'en re-conclure que l'effet survit a la mort : c'est
    l'etage 1 qui porte le lien, pas ce getter.

    Skippe en le disant quand le build n'est pas la -- les etages 1 et 2 ont deja tourne."""
    sys.path.insert(0, str(PYDIR))
    import probe_547r13_keep_on_revive as P                                # noqa: E402
    try:
        table = P.lire_tsv()
    except SystemExit as exc:
        pytest.skip("entree versionnee absente pour le build courant : %s" % exc)
    assert table, "l'entree versionnee est VIDE -- un accord sur rien ne prouve rien"
    assert table.get("IdunBattle.Entities.Effects.BaseEffect") is True, (
        "le DEFAUT de `BaseEffect` n'est plus VRAI : %s" % table.get(
            "IdunBattle.Entities.Effects.BaseEffect"))
    faux = sorted(k for k, v in table.items() if v is False)
    assert faux == [
        "IdunBattle.Entities.Effects.Loki.HealingBalmsEffect",
        "IdunBattle.Entities.Effects.Loki.PrecisionShot_AimEffect",
        "IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect",
    ], faux
    # NON-DEGENERESCENCE : les deux valeurs booleennes doivent etre representees, sinon l'accord
    # serait compatible avec un lecteur qui rendrait la meme constante partout.
    assert set(table.values()) == {True, False}, sorted(set(table.values()))
