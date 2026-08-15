"""#1032-r2 -- `IdunBattle.DSL.APickSelector$$AddForcedTargetsAndUpdateCandidates`, et le noeud
`First` qui prenait un INDICE alors qu'aucune surcharge native ne le fait.

DEUX volets, un seul foyer (`engine/entities/selectors/_pick.py`) :

  (a) `IdunBattleLogic.Entities.DSLSelectors$$First(entities, amount, ignoreForcedTargets)`
      construit un `PickFirstNSelector` -- un NOMBRE, pas un indice. Le selecteur a INDICE
      (`PickAtIndexSelector`) a sa propre factory, `DSLSelectors$$AtIndex`, deja portee sous
      `geometry.AtIndex`. Le port avait donc DEUX classes pour un selecteur et AUCUNE pour
      l'autre, sous un nom qui citait une factory inexistante (`DSLFactory$$First`).
  (b) `APickSelector$$AddForcedTargetsAndUpdateCandidates` : quand `ignoreForcedTargets == 0`,
      les cibles FORCEES du caster (`UnitExtensions$$GetOnlyTargets`, le TAUNT) sont PRE-INSEREES
      dans `picked` et RETIREES des candidats avant la copie -- elles PRIMENT donc sur l'ordre du
      tri. Census PE : `ignoreForcedTargets == 0` sur **144/145** call-sites de `First` et
      **4/5** de `Last`.

Ce fichier garde la FORME (offline, aucun runner) ; la confrontation live vit dans les tests
d'ability qui consomment ces noeuds.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE FOYER de #1032-r2 et ses deux re-exports.
        "scripts/python/engine/entities/selectors/_pick.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/_shared.py",
        "scripts/python/engine/dsl/base.py",
        # Le substrat des cibles forcees (l'accesseur `ctx.only_targets` et son foyer).
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        # L'unique call-site du depot qui ecrivait un `index=` explicite.
        "scripts/python/engine/runner/abilities/loki/mind_control.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE de la forme des trois selecteurs de prelevement (First / PickFirstN "
              "/ PickLastN) et de la passe des cibles forcees. Aucun RPC, aucun runner.",
}

import pytest                                                                    # noqa: E402

from engine.dsl.base import Const, DslContext                                    # noqa: E402
from engine.entities.selectors._pick import (                                    # noqa: E402
    APickSelector, add_forced_targets_and_update_candidates)
from engine.entities.selectors.geometry import AtIndex, PickFirstN, PickLastN    # noqa: E402
from engine.entities.selectors.units import First                                # noqa: E402


class _Src:
    """Selecteur source litteral -- on teste le PRELEVEMENT, pas l'amont."""

    def __init__(self, items):
        self.items = list(items)

    def evaluate(self, ctx):
        return list(self.items)


def _u(i):
    return {"id": i, "visualId": "u%d" % i}


def _ctx(caster_id=None, forced=None, units=()):
    """`DslContext` minimal : le caster (== `AbilityEntities+0x8`, offset LU sur
    `IdunBattle.Entities.Selectors.CasterSelector$$Select`) et le canal `only_targets`."""
    kw = {"units": list(units)}
    if caster_id is not None:
        kw["caster"] = _u(caster_id)
    if forced is not None:
        kw["only_targets"] = lambda uid: list(forced)
    return DslContext(**kw)


# --------------------------------------------------------------------------------------------
# [1] `First` PREND UN NOMBRE -- et l'ancien `index=` ne compile plus
# --------------------------------------------------------------------------------------------

def test_first_prend_un_amount_pas_un_index():
    """`DSLSelectors$$First(entities, amount, ignoreForcedTargets)` : le 3e argument est un
    NOMBRE. Le defaut du port vaut 1 -- le litteral de 104 des 145 call-sites."""
    src = _Src([_u(1), _u(2), _u(3)])
    ctx = _ctx()
    assert [u["id"] for u in First(src).evaluate(ctx)] == [1]
    assert [u["id"] for u in First(src, 2).evaluate(ctx)] == [1, 2]
    assert [u["id"] for u in First(src, Const(3)).evaluate(ctx)] == [1, 2, 3]


def test_l_ancien_index_ne_passe_plus_en_silence():
    """Le regime FAUX doit ECHOUER BRUYAMMENT, pas se reinterpreter en `amount`. Sans ce cran,
    un `First(x, index=1)` deviendrait `amount=1` et rendrait le PREMIER element la ou son
    auteur voulait le DEUXIEME -- une divergence muette."""
    with pytest.raises(TypeError):
        First(_Src([_u(1)]), index=0)


def test_first_est_pick_first_n_et_at_index_est_l_autre_selecteur():
    """UN selecteur natif = UNE implementation. `First` EST `PickFirstN` ; `AtIndex` est la
    classe DISTINCTE (`PickAtIndexSelector`), et c'est le seul port de celle-la."""
    assert issubclass(First, PickFirstN)
    assert issubclass(PickFirstN, APickSelector) and issubclass(PickLastN, APickSelector)
    assert not issubclass(AtIndex, APickSelector)
    src = _Src([_u(1), _u(2), _u(3)])
    ctx = _ctx()
    # Le regime ou les deux COINCIDENT (celui de 25/25 des call-sites d'alors) ...
    assert First(src, 1).evaluate(ctx) == AtIndex(src, 0).evaluate(ctx)
    # ... et celui ou ils DIVERGENT, qui est ce que le nom `First` promettait a tort.
    assert [u["id"] for u in AtIndex(src, 1).evaluate(ctx)] == [2]
    assert [u["id"] for u in First(src, 2).evaluate(ctx)] == [1, 2]


# --------------------------------------------------------------------------------------------
# [2] LA PASSE DES CIBLES FORCEES
# --------------------------------------------------------------------------------------------

def test_une_cible_forcee_prime_sur_l_ordre_du_tri():
    """La cible forcee est en QUEUE de la source ; le natif la fait passer DEVANT."""
    src = _Src([_u(1), _u(2), _u(3)])
    sans = [u["id"] for u in First(src, 1).evaluate(_ctx(caster_id=9, forced=[]))]
    avec = [u["id"] for u in First(src, 1).evaluate(_ctx(caster_id=9, forced=[3]))]
    assert sans == [1], "temoin NON FORCE : l'ordre source doit tenir"
    assert avec == [3], "la cible forcee doit primer sur l'ordre du tri"
    assert sans != avec, "TEMOIN DEGENERE : les deux regimes ne se distinguent pas"


def test_le_balayage_part_de_la_FIN_donc_les_forcees_entrent_en_ORDRE_INVERSE():
    """`for (i = candidates.Count - 1 ; i >= 0 ; i--)` -- LU. Le sens du balayage est
    observable des que DEUX cibles sont forcees, et l'intuition (« dans l'ordre de la source »)
    donne la reponse inverse."""
    src = _Src([_u(1), _u(2), _u(3), _u(4)])
    got = [u["id"] for u in First(src, 2).evaluate(_ctx(caster_id=9, forced=[1, 3]))]
    assert got == [3, 1], "les forcees entrent depuis la FIN des candidats"


def test_la_forcee_n_est_pas_recopiee_ensuite():
    """`candidates.RemoveAt(i)` quand `allowDuplicates == false` : la cible forcee ne doit pas
    reapparaitre dans la copie qui suit."""
    src = _Src([_u(1), _u(2), _u(3)])
    got = [u["id"] for u in First(src, 3 - 1).evaluate(_ctx(caster_id=9, forced=[1]))]
    assert got == [1, 2], "la forcee est prise une seule fois, puis la copie reprend a 0"


def test_amount_superieur_ou_egal_au_compte_ne_passe_PAS_par_les_forcees():
    """`if (n < candidates.Count)` enveloppe la passe : quand tout est pris, il n'y a rien a
    prioriser et l'ordre SOURCE est rendu intact. C'est LU, pas deduit."""
    src = _Src([_u(1), _u(2), _u(3)])
    got = [u["id"] for u in First(src, 3).evaluate(_ctx(caster_id=9, forced=[3]))]
    assert got == [1, 2, 3]


def test_ignore_forced_targets_desarme_la_passe():
    """Le litteral `ignoreForcedTargets = 1` existe (1 call-site de `First`, 1 de `Last`)."""
    src = _Src([_u(1), _u(2), _u(3)])
    ctx = _ctx(caster_id=9, forced=[3])
    assert [u["id"] for u in First(src, 1, ignore_forced_targets=True).evaluate(ctx)] == [1]
    assert [u["id"] for u in First(src, 1, ignore_forced_targets=False).evaluate(ctx)] == [3]


def test_canal_absent_ne_reordonne_RIEN():
    """`ctx.only_targets` non branche (contexte hors runner) -> aucune cible forcee, donc le
    MEME resultat que `GetOnlyTargets` vide, qui est le cas de la quasi-totalite des unites.
    Une non-mesure ne fabrique pas un reordonnancement."""
    src = _Src([_u(1), _u(2), _u(3)])
    assert [u["id"] for u in First(src, 1).evaluate(_ctx(caster_id=9))] == [1]
    assert [u["id"] for u in First(src, 1).evaluate(_ctx())] == [1]


def test_domaine_TUILE_ne_matche_pas_un_id_d_unite_forcee():
    """Les ids de TUILE vivent dans `state.board`, les ids d'UNITE dans `state.entities` : deux
    espaces DISJOINTS cote port. Confondre les deux ferait remonter une tuile parce qu'une
    unite du meme numero est tauntee -- un faux positif que le natif n'a pas (ses `BEntityId`
    sont uniques toutes entites confondues)."""
    src = _Src([11, 12, 13])                       # ids de TUILE
    got = PickFirstN(src, 1).evaluate(_ctx(caster_id=9, forced=[13]))
    assert got == [11], "un id de tuile ne doit pas etre lu comme un `IEntity.Id` d'unite"


# --------------------------------------------------------------------------------------------
# [3] `PickLastN` -- l'indice de depart absorbe les forcees
# --------------------------------------------------------------------------------------------

def test_pick_last_n_indice_de_depart_absorbe_les_forcees():
    """`for (i = picked.Count + candidates.Count - n ; i < candidates.Count ; i++)`. La passe
    deplace `k` elements de `candidates` vers `picked`, donc la somme des deux longueurs ne
    bouge pas : `i` vaut toujours `Count_initial - n`, et le total rendu vaut `n`."""
    src = _Src([_u(1), _u(2), _u(3), _u(4)])
    sans = [u["id"] for u in PickLastN(src, Const(2)).evaluate(_ctx(caster_id=9, forced=[]))]
    avec = [u["id"] for u in PickLastN(src, Const(2)).evaluate(_ctx(caster_id=9, forced=[1]))]
    assert sans == [3, 4]
    assert avec == [1, 4], "la forcee entre d'abord, puis la QUEUE reprend a l'indice decale"
    assert len(avec) == 2, "le total rendu reste `amount`"
    assert sans != avec, "TEMOIN DEGENERE"


def test_pick_last_n_regimes_de_bord_inchanges():
    """Les quatre regimes que #940 avait figes ne bougent pas (non-regression)."""
    ctx = _ctx()
    src = _Src([_u(1), _u(2), _u(3)])
    assert [u["id"] for u in PickLastN(src, Const(5)).evaluate(ctx)] == [1, 2, 3]
    assert PickLastN(src, Const(0)).evaluate(ctx) == []
    assert PickLastN(_Src([]), Const(1)).evaluate(ctx) == []
    assert [u["id"] for u in PickLastN(src, Const(1)).evaluate(ctx)] == [3]


# --------------------------------------------------------------------------------------------
# [4] LE FOYER EST APPELE PAR LES DEUX SELECTEURS (pas de 2e implementation)
# --------------------------------------------------------------------------------------------

def test_les_deux_selecteurs_passent_par_LE_foyer(monkeypatch):
    """Un 2e port de la passe serait une divergence garantie. On substitue le foyer DANS le
    module `_pick` -- forme B, la seule qui morde quand la liaison est au niveau module."""
    import engine.entities.selectors._pick as P

    vus = []

    def _espion(ctx, candidates, picked, allow_duplicates, max_amount):
        vus.append((len(candidates), allow_duplicates, max_amount))

    monkeypatch.setattr(P, "add_forced_targets_and_update_candidates", _espion)
    src = _Src([_u(1), _u(2), _u(3)])
    ctx = _ctx(caster_id=9, forced=[3])
    PickFirstN(src, 1).evaluate(ctx)
    PickLastN(src, Const(1)).evaluate(ctx)
    First(src, 1).evaluate(ctx)
    assert len(vus) == 3, "les trois noeuds doivent passer par le foyer : %r" % (vus,)
    assert all(a is False for _, a, _m in vus), "`allowDuplicates` est le litteral FALSE du natif"
    assert all(m == 1 for _c, _a, m in vus), "`maxAmount` est l'`amount` du selecteur"


def test_le_foyer_MUTE_la_liste_des_candidats():
    """`candidates.RemoveAt(i)` : le natif mute la liste que l'appelant va recopier. Un port qui
    copierait avant muterait dans le vide et re-inserait la cible forcee."""
    candidates = [_u(1), _u(2), _u(3)]
    picked: list = []
    add_forced_targets_and_update_candidates(_ctx(caster_id=9, forced=[2]), candidates, picked,
                                             allow_duplicates=False, max_amount=2)
    assert [u["id"] for u in picked] == [2]
    assert [u["id"] for u in candidates] == [1, 3], "la forcee doit avoir quitte les candidats"


def test_allow_duplicates_vrai_ne_retire_rien():
    """Branche `if (!allowDuplicates)` -- portee meme si aucun call-site connu ne la prend, pour
    que le mirror reste lisible terme a terme."""
    candidates = [_u(1), _u(2), _u(3)]
    picked: list = []
    add_forced_targets_and_update_candidates(_ctx(caster_id=9, forced=[2]), candidates, picked,
                                             allow_duplicates=True, max_amount=2)
    assert [u["id"] for u in picked] == [2]
    assert [u["id"] for u in candidates] == [1, 2, 3]


def test_les_noeuds_restent_VISIBLES_a_un_walk_d_arbre():
    """CE CRAN EXISTE PARCE QUE LE PIEGE A MORDU. La refonte avait pose `__slots__` sur la BASE
    `APickSelector` : les attributs quittent alors le `__dict__` sans entrer dans le `__slots__`
    de la classe CONCRETE, or les walks d'arbre du depot enumerent `vars(n)` puis
    `type(n).__slots__` -- sur la classe EXACTE, jamais la MRO. Resultat mesure : deux tests de
    #889-r6 tombes sur « aucun SortByFormula trouve : le walk ne voit plus l'arbre », sans qu'AUCUN
    test de selecteur ne bronche. Un noeud invisible a un walk est un faux vert par construction :
    le walk ne trouve rien, donc il n'accuse rien."""
    src = _Src([_u(1)])
    for noeud in (First(src, 1), PickFirstN(src, 1), PickLastN(src, Const(1)), AtIndex(src, 0)):
        enfants = dict(vars(noeud)) if hasattr(noeud, "__dict__") else {}
        for nom in (getattr(type(noeud), "__slots__", ()) or ()):
            enfants[nom] = getattr(noeud, nom, None)
        assert any(v is src for v in enfants.values()), (
            "%s n'expose PAS sa source a un walk `vars()` + `type().__slots__` : %r"
            % (type(noeud).__name__, sorted(enfants)))


def test_max_amount_borne_la_passe():
    """`if (picked.Count >= maxAmount) return;` -- teste AVANT chaque ajout."""
    candidates = [_u(1), _u(2), _u(3)]
    picked: list = []
    add_forced_targets_and_update_candidates(_ctx(caster_id=9, forced=[1, 2, 3]), candidates,
                                             picked, allow_duplicates=False, max_amount=2)
    assert len(picked) == 2 and [u["id"] for u in picked] == [3, 2]
