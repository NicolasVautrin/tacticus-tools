"""GARDES OFFLINE des DEUX etages ouverts par la tranche du foyer `dispatch/registry.py`
(#1019-r2 et #1002-r1), plus les deux feuilles DSL neuves.

Chaque garde est ecrite en MUTATION ADVERSARIALE : on etablit d'abord que le TEMOIN est NON
DEGENERE (les deux regimes different vraiment sur l'observable), puis on verifie que hors regime le
port est un no-op EXACT. Un cran qui compare un mutant a une constante peut rendre << ca mord >>
alors que port et mutant sont identiques -- c'est le faux vert que ce fichier existe pour eviter.

RE des deux etages : decompile ghidra, build `rnca9r7q6c`. Les CLASSES et METHODES citees ont ete
RE-CONFIRMEES PAR NOM contre le dump frida du build suivant (`t6dpr4k06g`) : 24/26 classes et 27/29
methodes presentes telles quelles, les 2+2 manquantes n'etant qu'une correction de NAMESPACE
(`...Abilities.Triggered.LifewardsAbility`, sans `.Loki`) et de NOM
(`Lakrimae_SummonPoxwalker_Ability`, avec le suffixe) -- aucune ne concerne CE fichier.
`UnitFlag.ForceRangedAttack` vaut toujours **21** dans `t6dpr4k06g`.
"""
from __future__ import annotations

import pytest

from engine.dsl.base import TargetsSelector
from engine.dsl.effects import ExecutionContext, OperationResult
from engine.entities.effect_type import EffectType
from engine.entities.unit_flag import UnitFlag
from engine.runner.abilities.behaviours.flags import AddFlag, RemoveFlag
from engine.runner.abilities.behaviours.lifecycle import (TriggerAbility,
                                                          TRIGGERED_ABILITY_BEHAVIOURS)
from engine.runner.components import UnitFlagsComponent
from engine.runner.operations.triggers.dispatch.registry import (ABILITY_TRIGGERS,
                                                                 EFFECT_TRIGGERS)
from engine.services import battle_query as BQ
import gameconfig as GC

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LES DEUX ETAGES gardes.
        "scripts/python/engine/services/battle_query.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        # LES DEUX FEUILLES DSL neuves.
        "scripts/python/engine/runner/abilities/behaviours/flags.py",
        "scripts/python/engine/runner/abilities/behaviours/__init__.py",
        # LES DEUX INSCRIPTIONS de registre et leurs mirrors.
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/loki/way_of_the_short_blade.py",
        "scripts/python/engine/runner/operations/triggers/loki/final_vengeance.py",
        "scripts/python/engine/runner/operations/triggers/loki/final_justice.py",
        # LA GEOMETRIE de cibles de l'effet 1500 et les deux mirrors d'enum lus.
        "scripts/python/engine/entities/effect_targets.py",
        "scripts/python/engine/entities/effects/loki/way_of_the_short_blade.py",
        "scripts/python/engine/entities/unit_flag.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/runner/components.py",
    ),
    # Le balayage de non-regression parcourt TOUTES les unites du gameconfig et compare leurs
    # armes : un changement de build change les armes, donc peut changer le verdict.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier garde les DEUX etages ouverts par la tranche du foyer `dispatch/registry.py` "
        "-- `force_ranged_attack` dans le service de selection d'arme, et `ignoreUnitHavingAbility` "
        "dans le noeud `TriggerAbility` -- plus les deux feuilles DSL `AddFlag`/`RemoveFlag` et les "
        "deux inscriptions de registre. Les chemins listes sont ceux dont une modification peut "
        "faire changer un verdict ; le `build` y est parce que le balayage de non-regression lit "
        "les armes de TOUTES les unites du gameconfig."),
}


# ==================================================================================================
# ETAGE 1 -- `!HasFlag(attacker, 0x15 = ForceRangedAttack)`, le 2e conjoint de la branche MELEE de
# `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack` (slot `0xaf`).
# ==================================================================================================
def _unite_a_deux_armes():
    """Un `visualId` du gameconfig qui porte A LA FOIS une arme de MELEE et une arme de DISTANCE.

    C'EST LA CONDITION DE NON-DEGENERESCENCE : sur une unite mono-arme, les deux regimes du drapeau
    rendent le MEME resultat (soit l'arme melee dans les deux cas si elle est seule et l'unite
    adjacente -- non, elle rendrait `None` --, soit la ranged dans les deux cas). Un test monte sur
    une telle unite passerait au vert sans rien mesurer."""
    for vid in ("tauAunShi", "tauCrisis", "tauShadowsun", "tauDarkstrider", "tauMarksman",
                "ultraTitus", "custoTrajann", "adeptCanoness"):
        gu = GC.unit(vid) or {}
        armes = gu.get("weapons") or []
        melee = [w for w in armes if BQ.weapon_is_melee(w)]
        ranged = [w for w in armes if not BQ.weapon_is_melee(w)]
        if melee and ranged:
            return vid, melee, ranged
    return None, None, None


def test_force_ranged_attack_bascule_la_selection_d_arme_et_le_temoin_est_non_degenere():
    vid, melee, ranged = _unite_a_deux_armes()
    if vid is None:
        pytest.skip("aucune unite du gameconfig ne porte a la fois melee ET ranged "
                    "(temoin degenere : le test ne mesurerait rien)")
    # -- TEMOIN NON DEGENERE : les deux jeux d'armes sont distincts et non vides.
    assert melee and ranged, "temoin degenere"
    assert {w.get("DamageProfile") for w in melee} != {w.get("DamageProfile") for w in ranged} \
        or len(melee) + len(ranged) >= 2

    # Regime NOMINAL (drapeau absent) : adjacent -> arme de MELEE.
    w_off, ranged_off = BQ.get_attack_weapon_for_default_normal_attack(
        vid, is_adjacent=True, dist=1, force_ranged_attack=False)
    assert w_off is not None, "montage : l'unite doit pouvoir attaquer au contact"
    assert ranged_off is False, "sans le drapeau, une attaque au CONTACT est en MELEE"

    # Regime du DRAPEAU : la branche melee est ETEINTE -> `FindRangedWeapon(..., dist)`.
    w_on, ranged_on = BQ.get_attack_weapon_for_default_normal_attack(
        vid, is_adjacent=True, dist=1, force_ranged_attack=True)
    assert w_on is not None, ("`FindRangedWeapon(dist = 1)` doit rendre une arme : "
                              "une portee >= 1 couvre le contact")
    assert ranged_on is True, "avec le drapeau, l'attaque au CONTACT devient DISTANCE"

    # -- LE PORT ET SON MUTANT DIFFERENT VRAIMENT (contre-epreuve non degeneree).
    assert w_on is not w_off and w_on != w_off, (
        "les deux regimes rendent la MEME arme -> le temoin ne separe rien")


def test_force_ranged_attack_est_un_no_op_exact_hors_regime():
    """Hors regime (drapeau absent), le port doit rendre EXACTEMENT ce qu'il rendait avant l'etage.

    Le controle porte sur TOUTES les unites du gameconfig et sur les deux geometries : le defaut
    `False` du parametre doit etre indiscernable de l'ancienne signature."""
    # `all_unit_ids()` rend un dict `kind -> [visualId]` (`lineup` / `npc` / `summons`) : on balaye
    # les TROIS, pas seulement le pool -- l'etage vit dans un service PARTAGE.
    unites = sorted({vid for lst in (GC.all_unit_ids() or {}).values() for vid in (lst or ())})
    assert len(unites) > 100, "le gameconfig doit publier les kits (sinon le balayage est vide)"
    vus = 0
    for vid in unites:
        for adj, dist in ((True, 1), (False, 3)):
            a = BQ.get_attack_weapon_for_default_normal_attack(vid, is_adjacent=adj, dist=dist)
            b = BQ.get_attack_weapon_for_default_normal_attack(vid, is_adjacent=adj, dist=dist,
                                                               force_ranged_attack=False)
            assert a == b, "le defaut du parametre n'est pas un no-op sur %s" % vid
            vus += 1
    assert vus > 200, "balayage trop etroit pour conclure (%d couples)" % vus


# ==================================================================================================
# ETAGE 2 -- `ignoreUnitHavingAbility`, le 8e argument de
# `IdunBattleLogic.Entities.DSLBehaviors$$TriggerAbility`, code en dur a `false` avant #1002-r1.
# ==================================================================================================
class _EtatBidon:
    """Substrat MINIMAL : `TriggerAbility.execute` ne lit du `state` que ce que
    `_unit_has_triggered_ability` consulte (`get_entity` -> `StatsComponent.ctx`)."""

    def __init__(self, entites):
        self.entities = entites
        self.rng = None

    def get_entity(self, eid):
        return self.entities.get(int(eid))


class _CtxBidon:
    triggered_ability_ids = ()
    tertiary_ability = None
    traits = ()


class _EntiteBidon:
    def __init__(self):
        self._c = {}

    def get_component(self, cls):
        return self._c.get(cls)

    def add_component(self, c):
        self._c[type(c)] = c
        return c


class _SelBidon(TargetsSelector):
    """Selecteur de cibles minimal -- rend la liste d'unites qu'on lui donne.

    Il DERIVE de `TargetsSelector` : c'est la base qui fournit `evaluate`, et `_units_of` appelle
    `evaluate`, pas `select`. Un duck-type sans la base passe le typage et LEVE a l'execution."""

    def __init__(self, unites):
        self.unites = unites

    def select(self, entities):
        return list(self.unites)


def _run_trigger_ability(ignore: bool, ability_type: int = 424242):
    """Joue `TriggerAbility` sur UNE unite qui ne porte PAS `ability_type`, et rend l'event emis."""
    ent = _EntiteBidon()
    st = _EtatBidon({7: ent})
    appels = []
    TRIGGERED_ABILITY_BEHAVIOURS[ability_type] = (
        lambda state, owner_id, entities, ectx: appels.append(int(owner_id)) or {"ok": True})
    try:
        ectx = ExecutionContext(state=st, rng=None)
        noeud = TriggerAbility(_SelBidon([{"id": 7}]), ability_type,
                               ignore_unit_having_ability=ignore)
        assert isinstance(noeud.execute([], ectx), OperationResult)
        ev = next(p for (n, p) in ectx.emitted if n == "TriggerAbility")
        return ev, appels
    finally:
        TRIGGERED_ABILITY_BEHAVIOURS.pop(ability_type, None)


def test_ignore_unit_having_ability_mord_et_le_temoin_est_non_degenere():
    ev_off, appels_off = _run_trigger_ability(False)
    ev_on, appels_on = _run_trigger_ability(True)

    # -- TEMOIN NON DEGENERE : les deux regimes doivent produire des observables DIFFERENTS.
    assert (ev_off["notCarrying"], appels_off) != (ev_on["notCarrying"], appels_on), (
        "les deux regimes sont identiques -> la contre-epreuve ne mesure rien")

    # `false` (le comportement HISTORIQUE) : l'unite ne porte pas l'ability -> ecartee, rien joue.
    assert ev_off["notCarrying"] == [7]
    assert appels_off == []
    # `true` (le bras que `FinalVengeance_UnitEffect` passe) : le gate est BYPASSE.
    assert ev_on["notCarrying"] == []
    assert appels_on == [7]
    assert ev_on["ignoreUnitHavingAbility"] is True
    assert ev_off["ignoreUnitHavingAbility"] is False


def test_le_defaut_de_trigger_ability_reste_le_comportement_historique():
    """Un `TriggerAbility(sel, id)` sans le nouveau parametre doit se comporter comme avant."""
    ent = _EntiteBidon()
    st = _EtatBidon({7: ent})
    ectx = ExecutionContext(state=st, rng=None)
    TriggerAbility(_SelBidon([{"id": 7}]), 424243).execute([], ectx)
    ev = next(p for (n, p) in ectx.emitted if n == "TriggerAbility")
    assert ev["notCarrying"] == [7], "le defaut doit encore APPLIQUER le gate `GetAbilityState`"
    assert ev["ignoreUnitHavingAbility"] is False


# ==================================================================================================
# LES DEUX FEUILLES DSL NEUVES -- `AddFlagBehaviour` / `RemoveFlagBehaviour`
# ==================================================================================================
def test_addflag_removeflag_mordent_et_sont_idempotents():
    ent = _EntiteBidon()
    st = _EtatBidon({7: ent})
    ectx = ExecutionContext(state=st, rng=None)
    sel = _SelBidon([{"id": 7}])

    # Le composant est ABSENT au depart : `AddFlag` doit le CREER (le natif, lui, en a un d'office).
    assert ent.get_component(UnitFlagsComponent) is None
    AddFlag(sel, UnitFlag.ForceRangedAttack).execute([], ectx)
    c = ent.get_component(UnitFlagsComponent)
    assert c is not None and c.has(int(UnitFlag.ForceRangedAttack))
    ev1 = [p for (n, p) in ectx.emitted if n == "AddFlag"][-1]
    assert ev1["added"] is True and ev1["flag"] == "ForceRangedAttack"

    # IDEMPOTENCE : le natif teste `Contains` avant `Add` -> le 2e passage n'ajoute rien.
    AddFlag(sel, UnitFlag.ForceRangedAttack).execute([], ectx)
    ev2 = [p for (n, p) in ectx.emitted if n == "AddFlag"][-1]
    assert ev2["added"] is False, "le 2e AddFlag doit signaler que le drapeau etait DEJA pose"
    assert c.has(int(UnitFlag.ForceRangedAttack))

    # RETRAIT.
    RemoveFlag(sel, UnitFlag.ForceRangedAttack).execute([], ectx)
    assert not c.has(int(UnitFlag.ForceRangedAttack))
    ev3 = [p for (n, p) in ectx.emitted if n == "RemoveFlag"][-1]
    assert ev3["removed"] is True
    # Retirer un drapeau ABSENT est un no-op cote natif (aucun test prealable, `Remove` seul).
    RemoveFlag(sel, UnitFlag.ForceRangedAttack).execute([], ectx)
    ev4 = [p for (n, p) in ectx.emitted if n == "RemoveFlag"][-1]
    assert ev4["removed"] is False


def test_removeflag_no_ope_quand_le_composant_manque():
    """Cote port le `UnitFlagsComponent` est OPTIONNEL : `RemoveFlag` ne doit ni lever ni le creer
    (retirer d'un ensemble absent == retirer d'un ensemble vide)."""
    ent = _EntiteBidon()
    st = _EtatBidon({7: ent})
    ectx = ExecutionContext(state=st, rng=None)
    RemoveFlag(_SelBidon([{"id": 7}]), UnitFlag.ForceRangedAttack).execute([], ectx)
    assert ent.get_component(UnitFlagsComponent) is None
    ev = [p for (n, p) in ectx.emitted if n == "RemoveFlag"][-1]
    assert ev["removed"] is False


# ==================================================================================================
# LES DEUX INSCRIPTIONS AU REGISTRE (une entree neuve DOIT etre visible d'un cliquet)
# ==================================================================================================
def test_les_deux_entrees_de_registre_sont_posees():
    from engine.runner.operations.triggers.loki.way_of_the_short_blade import (
        WayOfTheShortBladeAttackAbility, WAY_OF_THE_SHORT_BLADE_KEY)
    from engine.runner.operations.triggers.loki.final_vengeance import (
        FinalVengeanceUnitEffectTrigger, FINAL_VENGEANCE_UNIT_EFFECT)
    assert WAY_OF_THE_SHORT_BLADE_KEY == "WayOfTheShortBlade"
    assert WayOfTheShortBladeAttackAbility in ABILITY_TRIGGERS[WAY_OF_THE_SHORT_BLADE_KEY]
    assert FINAL_VENGEANCE_UNIT_EFFECT == int(EffectType.FinalVengeance_UnitEffect) == 1454
    assert FinalVengeanceUnitEffectTrigger in EFFECT_TRIGGERS[FINAL_VENGEANCE_UNIT_EFFECT]
    # `FinalJustice` doit etre DISPATCHABLE par le noeud `TriggerAbility`, sinon l'effet 1454
    # rendrait `dispatched: False` -- exactement le symptome que `#963-r3` decrit pour Geminae.
    assert 1024 in TRIGGERED_ABILITY_BEHAVIOURS


def test_le_marqueur_1500_a_desormais_une_geometrie_de_cibles():
    """`IsEffectTarget(_, 1500)` rendait `None` (non porte) : le gate du trigger de #1019-r2 aurait
    ete un refus PERMANENT, donc un port INERTE."""
    from engine.entities.effect_targets import EFFECT_TARGET_SELECTORS
    assert int(EffectType.WayOfTheShortBlade_AdditionalAttackMarker) in EFFECT_TARGET_SELECTORS
