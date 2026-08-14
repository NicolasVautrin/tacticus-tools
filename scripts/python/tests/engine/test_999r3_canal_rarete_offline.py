"""#999-r3 -- le canal `rarity` cote PORT : foyer tri-etat, les DEUX noeuds, la traversee.

Ce que ces etages gardent, et pourquoi chacun existe :

  1. `measured_rarity` -- TRI-ETAT STRICT. `0` est `Rarity.Common`, donc un repli sur `0` serait
     indiscernable d'une absence : le seul repli autorise est `None`. Un ordinal HORS mirror LEVE.
  2. `assert_rarity_channel` -- le nom PLEIN de l'enum est le SEUL discriminant. Les cinq enums de
     rarete du build portent les six memes membres aux memes ordinaux, donc aucune VALEUR ne
     trahirait un mauvais appariement (etage 7 le RE-DERIVE de `enums.tsv`, il ne le recopie pas).
  3. `triggers.HasRarity` -- mirror de `IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger`,
     y compris ses deux sorties NULLES (selecteur vide, rarete non mesuree) qui doivent rendre FAUX.
  4. `selectors.units.UnitsWithRarity` -- mirror de
     `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select`, et le CRAN qui interdit d'y
     rajouter un filtre de `UnitSelectionType` par element : le natif ne fait qu'en TRANSMETTRE la
     valeur au selecteur INTERIEUR.
  5. la TRAVERSEE : `UnitContext.from_snapshot` lit la ligne de snapshot, et le dict d'unite du
     contexte DSL publie la cle `rarity`. Sans cet etage, les deux noeuds seraient corrects sur des
     dicts fabriques a la main et INERTES sur une vraie bataille.
  6. le CLIQUET D'ORDINAL au SITE : `probe_313` compare le mirror au BUILD, donc il redevient vert
     des qu'on regenere le mirror apres un renumerotage -- alors que la valeur ECRITE au site, elle,
     a change. Cet etage fige les six ordinaux MESURES a la conversion.
  7. l'INDISCERNABILITE en ordinal, RE-DERIVEE de `data/symbols/<build>/frida/enums.tsv` : c'est
     elle qui justifie l'etage 2. Elle assertionne son propre NON-VIDE (un ensemble vide passerait
     pour vert).

Le regime SEPARANT vit dans `test_999r3_canal_rarete_live.py` (fixture `rarity_separating_case`) :
ici, tout est offline et deterministe."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from engine.entities.rarity import (RARITY_ENUM_FULL_NAME, Rarity, assert_rarity_channel,
                                    measured_rarity)
from engine.entities.selectors.units import UnitsWithRarity
from engine.entities.triggers import HasRarity
from engine.entities.unit_context import UnitContext

RACINE = Path(__file__).resolve().parents[4]


# --------------------------------------------------------------------------- etage 1

def test_measured_rarity_est_un_tri_etat_strict():
    """`None` = PAS MESURE, un membre = mesure, et JAMAIS de repli sur `0`."""
    assert measured_rarity(None) is None
    assert measured_rarity({}) is None, "champ ABSENT (capteur anterieur a #1039) -> non mesure"
    assert measured_rarity({"rarity": None}) is None, "`null` du capteur -> non mesure"
    # `0` est une VALEUR, pas une absence : c'est tout l'enjeu du tri-etat.
    assert measured_rarity({"rarity": 0}) == Rarity.Common
    assert measured_rarity({"rarity": 5}) == Rarity.Mythic
    assert isinstance(measured_rarity({"rarity": 3}), Rarity)


def test_un_ordinal_hors_mirror_LEVE_au_lieu_de_se_taire():
    """Un ordinal inconnu ne peut vouloir dire qu'une chose -- le build a bouge sous le mirror.
    Le rendre en `None` basculerait TOUS les gates de rarete en restrictif, en silence."""
    with pytest.raises(ValueError, match=r"n'est pas un membre d'idun\.meta\.Rarity"):
        measured_rarity({"rarity": 42})


# --------------------------------------------------------------------------- etage 2

def test_assert_rarity_channel_se_tait_sur_un_canal_MUET():
    """Capteur anterieur a #1039, ou resolveur du hook qui a REFUSE le canal : il rend alors
    `rarityEnum: null` ET `rarity: null` partout. Rien a garder -> no-op, comportement d'avant."""
    assert assert_rarity_channel(None) is None
    assert assert_rarity_channel({}) is None
    assert assert_rarity_channel({"rarityEnum": None}) is None


def test_assert_rarity_channel_REFUSE_un_enum_homonyme():
    """Le nom PLEIN est le seul canal ou la confusion est visible (cf. etage 7)."""
    assert assert_rarity_channel({"rarityEnum": RARITY_ENUM_FULL_NAME}) == RARITY_ENUM_FULL_NAME
    for homonyme in ("IdunMetaLogic.UserProgress.Model.UnitRarity",
                     "IdunMetaLogic.UserProgress.Model.ItemRarity",
                     "IdunMetaLogic.UserProgress.Model.UpgradeRarity",
                     "IdunMetaLogic.UserProgress.Model.XpBookRarity"):
        with pytest.raises(RuntimeError, match="canal de rarete REFUSE"):
            assert_rarity_channel({"rarityEnum": homonyme})


# --------------------------------------------------------------------------- etage 3

class _Sel:
    """Selecteur MINIMAL : `resolve_unit` du DSL accepte un noeud a `.evaluate(ctx)`."""

    def __init__(self, units):
        self.units = list(units)

    def evaluate(self, ctx):
        return self.units

    def select(self, ctx):
        return self.units


def _u(eid, rarity):
    d = {"id": eid, "team": 0, "player": 0, "alive": True, "hp": 10,
         "pos": {"col": 0, "row": 0}, "visualId": "v%d" % eid, "_traits": set()}
    if rarity is not _ABSENT:
        d["rarity"] = rarity
    return d


_ABSENT = object()


def test_hasrarity_mirroir_des_quatre_sorties_du_natif():
    """`entity == null` -> 0 ; sinon `buc[+0x74] == this[+0x18]`. La rarete NON MESUREE est la
    cinquieme sortie, qui n'existe que cote port : elle rend FAUX (restrictif), jamais VRAI."""
    ctx = object()
    assert HasRarity(_Sel([]), Rarity.Mythic).should_trigger(ctx) is False, "selecteur VIDE"
    assert HasRarity(_Sel([_u(1, 5)]), Rarity.Mythic).should_trigger(ctx) is True
    assert HasRarity(_Sel([_u(1, 3)]), Rarity.Mythic).should_trigger(ctx) is False
    assert HasRarity(_Sel([_u(1, None)]), Rarity.Mythic).should_trigger(ctx) is False, \
        "rarete NON MESUREE -> FAUX (jamais permissif)"
    assert HasRarity(_Sel([_u(1, _ABSENT)]), Rarity.Mythic).should_trigger(ctx) is False, \
        "cle ABSENTE (entite-tuile, cadavre) -> FAUX"


def test_hasrarity_compare_bien_a_la_valeur_demandee_et_pas_a_Mythic():
    """Contre-epreuve du fit : le noeud doit discriminer sur SON argument, pas sur `5` en dur."""
    ctx = object()
    assert HasRarity(_Sel([_u(1, 3)]), Rarity.Epic).should_trigger(ctx) is True
    assert HasRarity(_Sel([_u(1, 0)]), Rarity.Common).should_trigger(ctx) is True
    assert HasRarity(_Sel([_u(1, 0)]), Rarity.Epic).should_trigger(ctx) is False


# --------------------------------------------------------------------------- etage 4

def test_unitswithrarity_filtre_et_exclut_les_non_mesurees():
    ctx = object()
    src = _Sel([_u(1, 5), _u(2, 3), _u(3, None), _u(4, 5), _u(5, _ABSENT)])
    got = [u["id"] for u in UnitsWithRarity(src, Rarity.Mythic).select(ctx)]
    assert got == [1, 4], "ordre de la source PRESERVE, non mesurees EXCLUES"
    assert [u["id"] for u in UnitsWithRarity(src, Rarity.Epic).select(ctx)] == [2]
    assert UnitsWithRarity(src, Rarity.Legendary).select(ctx) == []


def test_unitswithrarity_n_a_PAS_de_parametre_selection_type():
    """CRAN DE NON-REGRESSION. Le natif LIT `this[+0x24]` et le passe au selecteur INTERIEUR
    (`inner.Select(entities, selType)`) ; sa propre boucle ne compare QUE la rarete. Un parametre
    `selection_type` ici serait soit INERTE (donc un piege : on le recopierait en croyant filtrer),
    soit un SECOND filtre que le natif n'applique pas."""
    params = list(inspect.signature(UnitsWithRarity.__init__).parameters)
    assert params == ["self", "source", "rarity"], (
        "signature inattendue %s -- si un `selection_type` est ajoute, il faut d'abord RELIRE "
        "`IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select`, qui ne filtre PAS par "
        "element." % params)


# --------------------------------------------------------------------------- etage 5

def test_traversee_from_snapshot_puis_dict_du_contexte_dsl():
    """La ligne de snapshot -> `UnitContext.rarity` -> cle `rarity` du dict d'unite DSL.

    Sans cet etage, les deux noeuds seraient corrects sur des dicts fabriques et INERTES en
    bataille -- exactement le profil << porte mais jamais atteint >>."""
    ctx = UnitContext.from_snapshot({"entityId": 7, "visualId": "x", "rarity": 3}, None)
    assert ctx.rarity == Rarity.Epic and isinstance(ctx.rarity, Rarity)
    assert UnitContext.from_snapshot({"entityId": 7, "visualId": "x"}, None).rarity is None
    assert UnitContext(entity_id=1).rarity is None, "defaut = NON MESURE"

    # Le dict d'unite du contexte DSL : la cle DOIT exister, et valoir la rarete du ctx.
    from engine.runner.abilities.behaviours import context as CTXMOD
    src = inspect.getsource(CTXMOD._unit_dict)
    assert '"rarity"' in src, (
        "`_unit_dict` ne publie plus la cle `rarity` : les deux noeuds de rarete deviendraient "
        "INERTES en bataille, sans erreur (ils liraient `None` partout).")


def test_le_dict_d_une_entite_TUILE_porte_rarity_None():
    """Une TUILE n'a pas de `BaseUnitComponent` : `GetBaseUnitComponent` y rend null et le natif
    LEVE avant toute comparaison. Une valeur inventee ferait passer un gate inatteignable."""
    from engine.runner.abilities.behaviours.context import _tile_entity

    class _B:
        by_id = {42: None}

        def coord(self, tid):
            return (1, 2)

    class _S:
        board = _B()

    d = _tile_entity(_S(), 42)
    assert d is not None and "rarity" in d and d["rarity"] is None


# --------------------------------------------------------------------------- etage 6

def test_les_six_ordinaux_ECRITS_au_site_sont_figes():
    """`probe_313` compare le MIRROR au BUILD -- il redevient vert des qu'on regenere le mirror
    apres un renumerotage, alors que la valeur ECRITE au site, elle, a change. Ce cran-ci fige les
    ordinaux MESURES a la conversion (#999-r3, build `rnca9r7q6c`)."""
    assert {m.name: int(m) for m in Rarity} == {
        "Common": 0, "Uncommon": 1, "Rare": 2, "Epic": 3, "Legendary": 4, "Mythic": 5}
    assert int(Rarity.Mythic) == 5, "l'ordinal que portent les CINQ gates natifs de rarete"


# --------------------------------------------------------------------------- etage 7

def test_l_ordinal_ne_discrimine_RIEN_et_c_est_re_derive_du_build():
    """La JUSTIFICATION de l'etage 2, re-derivee de la table VERSIONNEE -- jamais recopiee.

    Le lecteur d'`enums.tsv` est celui de `probe_1039_canal_rarete` (FOYER unique) : en ecrire un
    second ici, c'aurait ete forker le parsing du format, et un parsing faux rend un dict VIDE --
    donc une assertion << absent >> qui accuse le build au lieu du lecteur (vu ROUGE au 1er jeu).

    Assertionne son PROPRE NON-VIDE : si le balayage ne trouvait aucun homonyme, l'assertion
    << aucun homonyme ne differe par ses ordinaux >> passerait pour verte sur un ensemble vide."""
    import probe_1039_canal_rarete as P1039
    build = P1039.build_courant()
    enums = P1039.lire_enums(build)
    assert RARITY_ENUM_FULL_NAME in enums, (
        "%s absent d'enums.tsv du build %s : le type DECLARE des gates n'existe plus"
        % (RARITY_ENUM_FULL_NAME, build))
    attendu = {m.name: int(m) for m in Rarity}
    assert enums[RARITY_ENUM_FULL_NAME] == attendu, (
        "le mirror `engine/entities/rarity.py` diverge du build %s" % build)
    homonymes = sorted(n for n, membres in enums.items()
                       if n != RARITY_ENUM_FULL_NAME and membres == attendu)
    assert homonymes, (
        "AUCUN enum homonyme trouve dans le build %s -- l'etage 2 (refus par le NOM) perdrait sa "
        "raison d'etre, et ce test serait un vert VIDE. Re-lire case-1039 Sec.3 avant de conclure."
        % build)
    assert len(homonymes) >= 4, (
        "%d homonyme(s) seulement (%s) : #1039 en mesurait quatre en plus d'`%s`"
        % (len(homonymes), homonymes, RARITY_ENUM_FULL_NAME))
