"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1 -- `Lakrimae_SummonPoxwalker_Ability` et son etage neuf.

GARDE OFFLINE. Deux volets, et le premier existe parce que la fiche du residu portait DEUX
transcriptions FAUSSES du `CreateTrigger`, relevees au decompile dans cette tranche :

  * le 4e conjoint est `<DSLTriggers+0x28>` = **`IsTurnOf(Owner)`**, pas `get_OwnerIsActor` ;
  * le `Filter` porte sur **`AllAliveUnits`** (`DSLSelectors+0x20`), pas `AllUnits`.

Les deux MORDENT : la premiere eteint le summon sur un kill d'overwatch pendant le tour adverse,
la seconde fait que les Poxwalkers MORTS ne comptent pas dans le cap `nrOfUnits`.

Volet 2 : la FACTORY `free_tiles_or_adjacent_free_tiles`, le seul etage qui manquait reellement --
les deux que la fiche declarait absents (`IsObjectOrSteppable`, `ContagionsOfNurgleRange`) etaient
PORTES.

⚠ Ce que ce fichier NE garde PAS : la confrontation LIVE du spawn (elle vit dans
`test_462_r4b_r1_r1_r1_r1_c_r3_r1_r4_post_unit_kill_live.py`, dont le montage
`--equip-relic deathTyphus:Lakrimae:50` est deja ecrit et vert).
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/runner/operations/triggers/loki/lakrimae.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
    ),
    "build": True,            # gameconfig (`unitId`, `nrOfUnits`) et enums sont per-build
    "toujours": False,
    "raison": ("garde les DEUX corrections de transcription du CreateTrigger de "
               "Lakrimae_SummonPoxwalker (IsTurnOf et AllAliveUnits), la forme composee de "
               "FreeTilesOrAdjacentFreeTiles (Otherwise, PAS une union), et l'inscription au "
               "registre des DEUX classes du triggered 1541"),
}

import pytest                                                                    # noqa: E402

from engine.dsl.event_trigger_type import EventTriggerType                       # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType            # noqa: E402
from engine.entities.selectors.geometry import Otherwise                         # noqa: E402
from engine.entities.selectors.tiles import (AdjacentTiles, CanAddUnit,          # noqa: E402
                                             free_tiles_or_adjacent_free_tiles)
from engine.entities.selectors.units import Tiles                                # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                          # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType          # noqa: E402
from engine.entities.triggers import IsTurnOf                                    # noqa: E402
from engine.runner.operations.triggers.loki import lakrimae as LK                # noqa: E402


# --------- [1] LA FACTORY `FreeTilesOrAdjacentFreeTiles` : COMPOSEE, ET LE REPLI EST UN `Otherwise`
def test_462r4r1_free_tiles_est_une_composition_pas_une_classe():
    """`IdunBattleLogic.Entities.DSLSelectors$$FreeTilesOrAdjacentFreeTiles` n'alloue AUCUNE classe
    de selecteur : les DEUX surcharges composent
    `CanAddUnit(tiles, isSteppable).Otherwise(CanAddUnit(AdjacentTiles(tiles), isSteppable))`."""
    src = Tiles(None, as_ids=True)
    n = free_tiles_or_adjacent_free_tiles(src)
    assert isinstance(n, Otherwise), "le repli natif est un `Otherwise`, PAS une union"
    assert isinstance(n.primary, CanAddUnit)
    assert n.primary.source is src, "la branche PRIMAIRE vise les tuiles DEMANDEES"
    assert isinstance(n.fallback, CanAddUnit)
    assert isinstance(n.fallback.source, AdjacentTiles), "le REPLI vise les ADJACENTES"


def test_462r4r1_allow_steppable_est_celui_de_la_surcharge_2_args():
    """La surcharge 2-args code son trigger a `<DSLTriggers+0x48>` = l'`op_LogicalNot` du constant
    VRAI, et `CanAddUnitTileSelector$$Select` INVERSE (`allowSteppable = !ShouldTrigger`) -> **TRUE**.
    C'est le defaut du port ; les DEUX branches doivent le porter identiquement."""
    n = free_tiles_or_adjacent_free_tiles(Tiles(None, as_ids=True))
    assert n.primary.allow_steppable is True
    assert n.fallback.allow_steppable is True
    m = free_tiles_or_adjacent_free_tiles(Tiles(None, as_ids=True), allow_steppable=False)
    assert m.primary.allow_steppable is False and m.fallback.allow_steppable is False


def test_462r4r1_le_meme_sous_arbre_sert_aux_deux_sites():
    """Le natif cite `FreeTilesOrAdjacentFreeTiles(Target@+0x60)` DEUX fois -- sous `IsCanAddUnit`
    dans le trigger, et sous `PickRandomly` dans le behaviour. Le port a UNE fonction pour les deux :
    un second dépliage divergerait en silence."""
    a, b = LK.lakrimae_free_tiles(), LK.lakrimae_free_tiles()
    assert isinstance(a, Otherwise) and isinstance(b, Otherwise)
    # domaine EXPLICITE : le natif passe `Target` nu, normalise par le slot 10 (`SelectTiles`).
    assert isinstance(a.primary.source, Tiles)
    assert a.primary.source.as_ids is True


# ---------------- [2] LES DEUX CORRECTIONS DE TRANSCRIPTION DE LA FICHE ------------------------
def _conjoints(node) -> list:
    """Aplatit l'arbre `TriggerAnd` associatif a gauche en la liste de ses feuilles."""
    from engine.entities.triggers import TriggerAnd
    if isinstance(node, TriggerAnd):
        return _conjoints(node.a) + _conjoints(node.b)
    return [node]


def test_462r4r1_le_4e_conjoint_est_is_turn_of_pas_owner_is_actor():
    """LE VICE QUE CE TEST GARDE : la fiche `#462` transcrivait `<owner-is-actor>`. Le decompile lit
    `op_BitwiseAnd(T, <DSLTriggers+0x28>)`, et ce champ est `IsTurnOf(Owner@DSLSelectors+0x30)`
    (`DSLTriggers$$IsTurnOf` alloue EXACTEMENT la meme classe, meme signature ; balayage LITTERAL
    de la classe = TROIS sites). L'ecart MORD : un kill d'OVERWATCH pendant le tour adverse ne doit
    PAS faire apparaitre de Poxwalker."""
    cs = _conjoints(LK.lakrimae_summon_poxwalker_trigger())
    assert len(cs) == 9, "le CreateTrigger porte NEUF conjoints hors `On(0x35)` : %d" % len(cs)
    assert any(isinstance(c, IsTurnOf) for c in cs), \
        "`IsTurnOf(Owner)` ABSENT -- c'est la transcription `owner-is-actor` de la fiche"


def test_462r4r1_le_filter_porte_sur_les_unites_VIVANTES():
    """LE VICE QUE CE TEST GARDE : la fiche ecrivait `AllUnits@+0x20`. `DSLSelectors+0x20` est
    `AllAliveUnits` (morts EXCLUS, cf. sa docstring). Avec `AllUnits`, trois Poxwalkers MORTS
    suffiraient a bloquer le cap pour le reste de la bataille."""
    from engine.entities.selectors.tiles import AllAliveUnits
    from engine.entities.selectors.units import Filter
    cap = LK.lakrimae_poxwalker_cap_reached()
    # `AmountIsEqualOrGreater(Count(Filter(AllAliveUnits, ...)), Get(nrOfUnits))`
    src = cap.a.selector if hasattr(cap.a, "selector") else None
    assert isinstance(src, Filter), type(src)
    assert isinstance(src.source, AllAliveUnits), \
        "le Filter doit partir d'`AllAliveUnits` (DSLSelectors+0x20), pas d'`AllUnits`"


def test_462r4r1_les_constantes_sont_lues_du_gameconfig():
    """`GetStringConstant(cfg, 0x0 = unitId)` et `Get(GetNumberConstant(cfg, 0x78 = nrOfUnits))` --
    LUS, jamais devines. Recopier `unitId_2` (une autre constante) rendrait `None` = spawn
    silencieusement absent."""
    assert LK._poxwalker_visual_id() == "deathPoxwalker"
    assert LK._nr_of_units() == 3
    assert int(AbilityConstantType.unitId) == 0x0
    assert int(AbilityConstantType.nrOfUnits) == 0x78


# ------------------------------------ [3] LE REGISTRE -----------------------------------------
def test_462r4r1_registre_les_deux_classes_du_1541():
    """UN id, DEUX classes (patron `DaemonfleshPlate`) -- la cle EXISTAIT deja, il fallait AJOUTER
    la classe a la liste, pas creer l'entree."""
    from engine.runner.operations.triggers.dispatch.registry import RELIC_ABILITY_TRIGGERS as R
    noms = [c.__name__ for c in (R.get("Lakrimae") or [])]
    assert noms == ["LakrimaeAddContaminationAbility", "LakrimaeSummonPoxwalkerAbility"], noms
    classes = R["Lakrimae"]
    assert {int(c.TRIGGERED_ABILITY_ID) for c in classes} == {1541}
    # vecteurs DISTINCTS -- si les deux ecoutaient le meme event, l'une serait morte.
    assert {int(c.event_id) for c in classes} == {int(EventTriggerType.NormalAttack),
                                                 int(EventTriggerType.PostUnitKill)}


@pytest.mark.parametrize("membre,attendu,ou", [
    (int(TriggeredAbilityType.Lakrimae), 1541, "`AbilityOrEffect(this)` du NOT TriggeringAbilityIs"),
    (int(EventTriggerType.PostUnitKill), 53, "`DSLTriggers$$On(this, 0x35, 1)`"),
    (int(UnitTrait.Mechanical), 5, "`NOT HasTrait(Target@+0x60, 5)`"),
])
def test_462r4r1_ordinaux_ecrits_au_site(membre, attendu, ou):
    """Fige l'ordinal MESURE a la conversion."""
    assert membre == attendu, "ordinal glisse -- lu au site %s" % (ou,)
