"""#10009 -- garde OFFLINE des trois ports livres sur le foyer `engine/entities/effects/factory.py`
par la tranche du 2026-08-15 : `#963-r3` (Lifewards), `#999-r1` (la pose de MastersOfManoeuvre) et
`#922-r1` volet b (les trois owner-effects de relique).

Ce fichier ne monte AUCUN runner. Il garde ce qu'un test live ne voit pas -- les REGIMES SEPARANTS
des gates, les valeurs MESUREES au decompile, et les deux ecritures dont l'absence serait
SILENCIEUSE.

HUIT etages, chacun avec une raison MESUREE pendant la tranche :

  1. `Lifewards` est au registre, avec la BONNE classe et le bon `event_id` ;
  2. le 2e conjoint de son trigger est une DISJONCTION -- une Geminae MORTE qui porte 1240 protege
     ENCORE. C'est le regime SEPARANT : rabattre sur `IsAlive` seul serait restrictif et muet ;
  3. son behaviour pose les DEUX bonds AVEC leur `bondedEntity` = `Parent(Owner)` = Celestine, et
     le second exige `IsAlive(Owner)` la ou le premier ne l'exige pas ;
  4. `BOND_REMOVAL_GATES[1060]` porte la mesure `--step declared`, et le bloc `methodPointers` ne
     l'aurait PAS donnee (contre-epreuve : deux entrees seulement dans le bloc des CORPS) ;
  5. le retrait de 1240 est `On(0x9 = Attack)` SANS AUCUN conjoint -- ne pas recopier le
     `get_OwnerIsCaster` de son voisin de forme ;
  6. `MastersOfManoeuvre` : DEUX classes, un `event_id` chacune, et le noeud `TilesMovedThisTurn`
     avec son substrat LIVE ;
  7. le parametre `ability_state` d'`AddEffect` -- sans lui, la pose lirait le couple des PASSIFS
     (dernier palier) au lieu du couple TERTIAIRE ;
  8. les trois entrees `ABILITY_INIT_OWNER_EFFECTS` de #922-r1, avec les ordinaux MESURES.
"""
from __future__ import annotations

import inspect

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.effect_type import EffectType
from engine.entities.effects import factory as FACT
from engine.entities.formulas import TilesMovedThisTurn
from engine.entities.rarity import Rarity
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_faction import UnitFaction
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.abilities.behaviours.context import _LIVE_KEYS, entities_from_state
from engine.runner.abilities.behaviours.effects import AddEffect
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.triggers.bond_removal import BOND_REMOVAL_GATES
from engine.runner.operations.triggers.dispatch import registry as REG
from engine.runner.operations.triggers.loki import lifewards as LW
from engine.runner.operations.triggers.loki import masters_of_manoeuvre as MOM
from engine.runner.state import State
from engine.entities.effects_state import EffectsState
from engine.entities.unit_context import UnitContext

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        # PROPRE A CE FICHIER, perimetre pris LARGE : l'etage 7 lit le SOURCE de la feuille
        # `AddEffect`, les etages 1/4/5/6/8 lisent des REGISTRES que n'importe quel module
        # d'`engine` peut alimenter, et les etages 2/3 executent le pipeline de pose.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # Les ordinaux (etages 1, 6, 8) viennent du dump, les constantes du gameconfig.
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : la DISJONCTION `IsAlive(Owner) | HasEffect(Owner, 1240)` du trigger "
              "de Lifewards (rabattue sur `IsAlive` seul, une Geminae morte cesserait de proteger, "
              "sans erreur) ; le `bondedEntity = Parent(Owner)` des deux `AddBondEffect` ; la mesure "
              "`--step declared` de `LifewardsBondEffect` (get_RemoveOnBondedEntityDeath = TRUE), "
              "que le bloc `methodPointers` du PE ne donne PAS -- il n'a que deux entrees, un "
              "virtuel a corps trivial etant ICF-deduplique ; le retrait de 1240 SANS conjoint ; les "
              "deux `event_id` de MastersOfManoeuvre et le substrat LIVE de `TilesMovedThisTurn` ; "
              "le parametre `ability_state` d'`AddEffect`, sans lequel une pose par ability "
              "TERTIAIRE lirait le couple des PASSIFS (donc le dernier palier apres clamp) ; et les "
              "trois ordinaux d'effet de #922-r1 mesures au decompile.",
}

CELESTINE = "adeptCelestine"
GEMINAE = "adeptSmnGeminaeSuperia"


def _unit(st, vis, team, *, alive=True, parent=None, hp=1000, col=0, row=0,
          rarity=None, tertiary=None, tertiary_level=None, passive_level=50):
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id=vis, alive=alive,
                                  parent_id=None if parent is None else int(parent)))
    e.add_component(OwnerComponent(team=team))
    ctx = UnitContext(entity_id=e.id, visual_id=vis)
    ctx.passive_ability_level = passive_level
    if rarity is not None:
        ctx.rarity = rarity
    if tertiary is not None:
        ctx.tertiary_ability = tertiary
        ctx.tertiary_ability_level = tertiary_level
        ctx.tertiary_ability_variables_multiplier = 100
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=hp, hp_max=1000))
    e.add_component(PositionComponent(col=col, row=row))
    return e.id


def _lifewards_state(*, geminae_alive=True, protecting=False, adjacent=True):
    """Celestine en (0,0) et sa Geminae (son ENFANT) adjacente en (1,0), meme equipe."""
    st = State()
    st.effects = EffectsState()
    celestine = _unit(st, CELESTINE, 1, col=0, row=0)
    gem = _unit(st, GEMINAE, 1, alive=geminae_alive, parent=celestine,
                hp=1000 if geminae_alive else 0,
                col=1 if adjacent else 5, row=0)
    if protecting:
        st.effects.add_effect(gem, FACT.EffectFactory.create(
            {"name": EffectType.Lifewards_Protecting.name,
             "effectType": int(EffectType.Lifewards_Protecting), "remaining": 0}))
    return st, celestine, gem


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- `Lifewards` est INSCRIT, avec la bonne classe et le bon vecteur
# --------------------------------------------------------------------------------------------
def test_lifewards_est_au_registre_avec_son_vecteur():
    """UNE classe pour l'id 1049 cote COMBAT (la seconde classe native, `LifewardsAddEffectAbility`,
    est une branche d'INIT et ne passe PAS par ce registre -- cf. le residu en tete du module)."""
    ent = REG.ABILITY_TRIGGERS.get("Lifewards")
    assert ent is not None, "Lifewards absent d'ABILITY_TRIGGERS"
    assert [c.__name__ for c in ent] == ["LifewardsAbility"]
    assert ent[0].event_id == int(EventTriggerType.PreDamageTaken) == 0x39
    assert ent[0].TRIGGERED_ABILITY_ID == int(TriggeredAbilityType.Lifewards) == 1049
    # Le declenchement DIRECT par `TriggerAbility` de `GeminaeSuperia` : sans cette entree, la
    # feuille rendait `dispatched: False` et la Geminae n'absorbait RIEN.
    from engine.runner.abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
    assert TRIGGERED_ABILITY_BEHAVIOURS.get(1049) is not None
    # Les deux effets ont une CLASSE nommee (pas un `BaseEffect` anonyme).
    assert FACT.EFFECT_CLASSES.get("Lifewards_BondEffect") is not None
    assert FACT.EFFECT_CLASSES.get("Lifewards_Protecting") is not None
    assert int(EffectType.Lifewards_BondEffect) == 0x424 == 1060
    assert int(EffectType.Lifewards_Protecting) == 0x4d8 == 1240


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- LE REGIME SEPARANT : `IsAlive(Owner) | HasEffect(Owner, 1240)`
# --------------------------------------------------------------------------------------------
def test_geminae_vivante_absorbe():
    """Cas nominal : la Geminae est vivante, adjacente, et Celestine est bien `Parent(Owner)`."""
    st, celestine, gem = _lifewards_state()
    ab = LW.LifewardsAbility(owner_id=gem)
    ev = _pre_damage_event(celestine, attacker=None)
    assert ab.matches(st, ev) is True


def test_geminae_MORTE_sans_marqueur_n_absorbe_PAS():
    """1er disjoint FAUX, 2e disjoint FAUX -> le gate ferme."""
    st, celestine, gem = _lifewards_state(geminae_alive=False, protecting=False)
    ab = LW.LifewardsAbility(owner_id=gem)
    assert ab.matches(st, _pre_damage_event(celestine, attacker=None)) is False


def test_geminae_MORTE_AVEC_le_marqueur_1240_absorbe_ENCORE():
    """LE REGIME QUI SEPARE, et la raison d'etre de l'effet 1240 : `IsAlive` est FAUX, mais
    `HasEffect(Owner, 0x4d8, onlyActive: 0, 6)` est VRAI -> le gate PASSE.

    Un port qui aurait rabattu le 2e conjoint sur `IsAlive(Owner)` seul rendrait `False` ici, sans
    erreur et sans qu'aucun test d'appartenance au registre ne le voie."""
    st, celestine, gem = _lifewards_state(geminae_alive=False, protecting=True)
    ab = LW.LifewardsAbility(owner_id=gem)
    assert ab.matches(st, _pre_damage_event(celestine, attacker=None)) is True


def test_le_gate_d_adjacence_MORD():
    """`IsAdjacent(Owner@+0x30, Target@+0x60, 0)` -- la Geminae eloignee n'absorbe pas."""
    st, celestine, gem = _lifewards_state(adjacent=False)
    ab = LW.LifewardsAbility(owner_id=gem)
    assert ab.matches(st, _pre_damage_event(celestine, attacker=None)) is False


def test_le_gate_de_parente_MORD():
    """`AreEqual(Target@+0x60, Parent(Owner@+0x30))` -- un ALLIE adjacent qui n'est pas la mere du
    summon n'est PAS protege. Sans ce conjoint, la Geminae absorberait pour toute son equipe."""
    st, celestine, gem = _lifewards_state()
    autre = _unit(st, "alliedHero", 1, col=1, row=1)
    ab = LW.LifewardsAbility(owner_id=gem)
    assert ab.matches(st, _pre_damage_event(autre, attacker=None)) is False


def _pre_damage_event(target_id, attacker=None):
    from engine.runner.operations.triggers.base import TriggerEvent
    return TriggerEvent(int(EventTriggerType.PreDamageTaken), attacker, target_id,
                        ranged=False, profile=None)


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- le behaviour pose les DEUX bonds, avec leur `bondedEntity`
# --------------------------------------------------------------------------------------------
def test_le_behaviour_pose_les_deux_bonds_lies_a_celestine():
    """`AddBondEffect(0x424, ..., bondedEntity = Parent(Owner))` puis `AddBondEffect(0x4d8, ...)`.

    Le `bonded` est ce que `ABondEffect$$BondedEntityId` relit et ce que consomme le gate (a) de
    `BOND_REMOVAL_GATES[1060]` -- une pose sans lui rendrait le retrait MUET."""
    st, celestine, gem = _lifewards_state()
    attaquant = _unit(st, "ennemi", 2, col=2, row=0)
    LW.LifewardsAbility(owner_id=gem).execute_behaviour(
        st, _pre_damage_event(celestine, attacker=attaquant))
    poses = {e.name: e for e in st.effects.by_unit.get(gem, [])}
    assert EffectType.Lifewards_BondEffect.name in poses
    assert EffectType.Lifewards_Protecting.name in poses
    for nom in (EffectType.Lifewards_BondEffect.name, EffectType.Lifewards_Protecting.name):
        assert poses[nom].bonded == celestine, (
            "%s pose sans son bondedEntity = Parent(Owner) : le gate (a) serait muet" % nom)


def test_une_geminae_MORTE_ne_re_obtient_PAS_son_marqueur():
    """Le second `If` porte `& IsAlive(Owner@+0x30)` la ou le premier ne l'a PAS -- LU, pas
    harmonise. Une Geminae morte garde/obtient son BOND mais pas sa protection."""
    st, celestine, gem = _lifewards_state(geminae_alive=False, protecting=True)
    # On retire le marqueur pose par le montage pour observer la RE-pose (ou son absence).
    st.effects.by_unit[gem] = []
    attaquant = _unit(st, "ennemi", 2, col=2, row=0)
    LW.LifewardsAbility(owner_id=gem).execute_behaviour(
        st, _pre_damage_event(celestine, attacker=attaquant))
    noms = {e.name for e in st.effects.by_unit.get(gem, [])}
    assert EffectType.Lifewards_BondEffect.name in noms      # 1er If : PAS de gate IsAlive
    assert EffectType.Lifewards_Protecting.name not in noms  # 2e If : gate IsAlive -> ferme


# --------------------------------------------------------------------------------------------
# ETAGE 4 -- la mesure `--step declared`, que le bloc `methodPointers` ne donne PAS
# --------------------------------------------------------------------------------------------
def test_bond_removal_gates_1060_porte_la_mesure():
    """`LifewardsBondEffect` : `get_Range = none`, `get_Adjacent = false`,
    `get_RemoveOnBondedEntityDeath = **true**` -> gate (a) SEUL.

    ⚠ CONTRE-EPREUVE DE << lire le bloc `methodPointers` suffit >> : ce bloc ne porte que DEUX
    entrees pour cette classe (`.ctor`, `CreateActiveCondition`), donc conclure de lui aurait pose
    `(False, None, False)` -- AUCUN retrait, et le bond aurait survecu a la mort de Celestine."""
    g = BOND_REMOVAL_GATES.get(int(EffectType.Lifewards_BondEffect))
    assert g is not None, "BOND_REMOVAL_GATES[1060] absent : le bond ne tomberait jamais"
    assert g.native == "IdunBattle.Entities.Effects.Loki.LifewardsBondEffect"
    assert (g.remove_on_bonded_entity_death, g.range, g.adjacent) == (True, None, False)
    # Le trigger (a) est DERIVE de la table : la derivation doit avoir produit une entree.
    assert REG.EFFECT_TRIGGERS.get(int(EffectType.Lifewards_BondEffect))


# --------------------------------------------------------------------------------------------
# ETAGE 5 -- le retrait de 1240 : `On(0x9)` SANS AUCUN conjoint
# --------------------------------------------------------------------------------------------
def test_retrait_1240_sur_On_Attack_sans_conjoint():
    """Corps ENTIER du natif : `On(0x9 = Attack, ownerNeedsToBeAlive: 0)`, un seul noeud.

    ⚠ Ne PAS recopier le `get_OwnerIsCaster` de son voisin de forme `ShockAssaultBuffRemove` :
    l'ajouter rendrait le marqueur quasi-permanent (une Geminae morte n'attaque plus jamais)."""
    ent = REG.EFFECT_TRIGGERS.get(int(EffectType.Lifewards_Protecting))
    assert ent is not None and [c.__name__ for c in ent] == ["LifewardsProtectingRemove"]
    assert ent[0].event_id == int(EventTriggerType.Attack) == 0x9
    assert ent[0].effect_type == int(EffectType.Lifewards_Protecting)
    # Le retrait MORD : une attaque de N'IMPORTE QUI retire le marqueur du porteur.
    st, celestine, gem = _lifewards_state(geminae_alive=False, protecting=True)
    assert any(e.name == EffectType.Lifewards_Protecting.name
               for e in st.effects.by_unit.get(gem, []))
    from engine.runner.operations.triggers.base import TriggerEvent
    LW.LifewardsProtectingRemove(owner_id=gem).execute_behaviour(
        st, TriggerEvent(int(EventTriggerType.Attack), gem, gem, ranged=False, profile=None))
    restants = [e for e in st.effects.by_unit.get(gem, [])
                if e.name == EffectType.Lifewards_Protecting.name and not e.consumed]
    assert restants == [], "le marqueur 1240 n'a pas ete retire par On(0x9)"


# --------------------------------------------------------------------------------------------
# ETAGE 6 -- `MastersOfManoeuvre` : deux classes, deux vecteurs, et le noeud qui manquait
# --------------------------------------------------------------------------------------------
def test_masters_of_manoeuvre_deux_classes_deux_vecteurs():
    """La disjonction d'`On()` se ventile en DEUX classes, le registre etant indexe par `event_id`.
    Elles partagent l'id 1508 et le gate COMMUN."""
    ent = REG.RELIC_ABILITY_TRIGGERS.get("MastersOfManoeuvre")
    assert ent is not None, "MastersOfManoeuvre absent de RELIC_ABILITY_TRIGGERS"
    assert [c.__name__ for c in ent] == ["MastersOfManoeuvrePlaceOnMove",
                                         "MastersOfManoeuvrePlaceOnTurnEnd"]
    assert {c.TRIGGERED_ABILITY_ID for c in ent} == {int(TriggeredAbilityType.MastersOfManoeuvre)}
    assert ent[0].event_id == int(EventTriggerType.UnitAfterMove) == 4
    assert ent[1].event_id == int(EventTriggerType.UnitFinishedTurn) == 0x28
    # Les ordinaux ECRITS aux sites, figes a la valeur MESUREE (`probe_313` compare le mirror au
    # build, PAS la valeur ecrite -- cf. le cran manquant nomme dans le CLAUDE.md).
    assert int(TriggeredAbilityType.MastersOfManoeuvre) == 0x5e4 == 1508
    assert MOM.MASTERS_OF_MANOEUVRE_EFFECT == int(EffectType.MastersOfManoeuvre) == 0x5e6 == 1510
    assert int(AbilityConstantType.nrOfRounds) == 0x45
    assert int(AbilityConstantType.tilesTraversed) == 0x88
    assert int(Rarity.Mythic) == 5
    assert int(UnitFaction.DarkAngels) == 0xa
    assert MOM._SELECTION == int(UnitSelectionType.OnlyAliveAndTargetable) == 3
    # Les constantes viennent du GAMECONFIG, jamais du code.
    assert MOM.masters_of_manoeuvre_constant(AbilityConstantType.nrOfRounds) == 1
    assert MOM.masters_of_manoeuvre_constant(AbilityConstantType.tilesTraversed) == 2


def test_tiles_moved_this_turn_a_son_substrat_et_il_est_LIVE():
    """Le SEUL noeud qui manquait au vocabulaire de #999-r1. Son substrat
    (`ActorStatisticsComponent+0xf0`) existait deja ; ce qui manquait etait la voie DSL.

    ⚠ La cle est dans `_LIVE_KEYS`, et c'est LOAD-BEARING : `AddTilesMoved` incremente `+0xf0`
    depuis `MoveUnitOperation$$Execute` AVANT qu'`EvaluateAfterMoveTriggers` ne publie `On(4)` --
    le vecteur meme qui fait relire ce compteur. Figee au seed, la valeur serait celle d'AVANT le
    deplacement, donc 0 au premier move du tour, et le gate ne matcherait JAMAIS."""
    assert "tilesMovedThisTurn" in _LIVE_KEYS
    st = State()
    u = _unit(st, "mover", 1, col=0, row=0)
    ents = entities_from_state(st, u, u, u)
    assert TilesMovedThisTurn(__import__(
        "engine.entities.selectors.accessors", fromlist=["Actor"]).Actor()).calculate(ents) == 0
    from engine.runner.components import record_tiles_moved
    record_tiles_moved(st, u, 3)
    ents2 = entities_from_state(st, u, u, u)
    from engine.entities.selectors.accessors import Actor
    assert TilesMovedThisTurn(Actor()).calculate(ents2) == 3


def test_le_gate_de_tuiles_MORD_au_seuil_du_gameconfig():
    """`AmountIsEqualOrGreater(TilesMovedThisTurn(Actor), Get(tilesTraversed = 2))` -- STRICTEMENT
    en dessous du seuil le gate ferme, au seuil il ouvre."""
    from engine.runner.components import record_tiles_moved
    for parcourues, attendu in ((0, False), (1, False), (2, True), (5, True)):
        st = State()
        u = _unit(st, "mover", 1, col=0, row=0)
        record_tiles_moved(st, u, parcourues)
        ents = entities_from_state(st, u, u, u)
        assert bool(MOM.masters_of_manoeuvre_tiles_gate().should_trigger(ents)) is attendu, (
            "seuil tilesTraversed mal porte pour %d tuile(s)" % parcourues)


# --------------------------------------------------------------------------------------------
# ETAGE 7 -- `ability_state` d'`AddEffect` : le 2e argument natif, sans lequel la magnitude ment
# --------------------------------------------------------------------------------------------
def test_add_effect_expose_ability_state_et_il_PRIME():
    """Le derive `scale_from_source` rend le couple des PASSIFS (`50 / 180` en runner normalise) ;
    `ToZeroBasedIndex(50)` clampe au DERNIER palier, or `dmgReductionPct` n'en a que QUATRE. Une
    pose par ability TERTIAIRE lirait donc 20 % la ou le natif donne 10 % au niveau 1."""
    sig = inspect.signature(AddEffect.__init__)
    assert "ability_state" in sig.parameters
    assert sig.parameters["ability_state"].default is None, (
        "le defaut doit rester None = comportement STRICTEMENT anterieur pour les call-sites "
        "existants")
    # Le port de MastersOfManoeuvre le RENSEIGNE -- sinon la correction serait inerte.
    src = inspect.getsource(MOM.masters_of_manoeuvre_add_effect_tree)
    assert "ability_state=ability_state" in src
    # ... et il l'alimente par le foyer qui distingue TERTIAIRE de PASSIF.
    assert "triggered_ability_state" in inspect.getsource(MOM._MastersOfManoeuvreBase.execute_behaviour)


def test_ability_state_PRIME_sur_le_derive_et_c_est_la_VALEUR_POSEE_qui_le_dit():
    """⚠ **CE TEST EXISTE PARCE QUE LE PRECEDENT NE MORDAIT PAS.** Mesure adversariale du
    2026-08-15 : neutraliser la prise en compte du parametre (`if False:` a la place de
    `if self.ability_state is not None:`) laissait la garde VERTE -- l'etage ci-dessus verifie la
    SIGNATURE et le call-site, jamais l'EFFET. Un parametre declare, cite au site, et IGNORE a
    l'execution aurait donc passe.

    Ce qui est verifie ici est la VALEUR REELLEMENT POSEE sur l'instance : le couple explicite
    (`1 / 100`, celui d'une TERTIAIRE) doit l'emporter sur le derive `scale_from_source` (`50 / 180`,
    celui des PASSIFS d'un runner normalise)."""
    from engine.dsl.effects import ExecutionContext
    from engine.entities.selectors.accessors import Target
    st = State()
    st.effects = EffectsState()
    poseur = _unit(st, "mow", 1, col=0, row=0, passive_level=50)
    st.get_entity(poseur).get_component(StatsComponent).ctx.ability_variables_multiplier = 180
    cible = _unit(st, "allie", 1, col=1, row=0)
    ectx = ExecutionContext(state=st, rng=st.rng)
    AddEffect(int(EffectType.MastersOfManoeuvre), EffectType.MastersOfManoeuvre.name,
              Target(), duration_rounds=1, scale_from_source=True,
              ability_state=(1, 100)).execute(
        entities_from_state(st, poseur, cible, poseur), ectx)
    inst = [e for e in st.effects.by_unit.get(cible, [])
            if e.name == EffectType.MastersOfManoeuvre.name]
    assert len(inst) == 1, "la pose n'a rien materialise : le test ne mesure plus rien"
    assert (inst[0].ability_level, inst[0].ability_variables_multiplier) == (1, 100), (
        "l'`abilityState` EXPLICITE n'a pas prime sur `scale_from_source` : la pose lirait le "
        "couple des PASSIFS (50/180), donc le DERNIER palier apres `ToZeroBasedIndex` -- 20 %% au "
        "lieu de 10 %% sur `dmgReductionPct`, en silence")


# --------------------------------------------------------------------------------------------
# ETAGE 8 -- #922-r1 volet b : les trois entrees, et les ordinaux MESURES
# --------------------------------------------------------------------------------------------
def test_les_trois_owner_effects_de_relique_sont_seedes():
    """L'artefact que la fiche nommait (`<X>_InitAbility$$CreateBehaviour`) N'EXISTE PAS pour ces
    trois-la. Les vrais sont de DEUX formes : `AOwnerEffectTriggeredAbility` + `GetEffectType` pour
    les deux premieres, un `CreateBehaviour` propre a DEUX `AddEffect` pour la troisieme."""
    r = FACT.ABILITY_INIT_OWNER_EFFECTS
    assert r.get("IntoxicatingElixir") == ["IntoxicatingElixir"]
    assert r.get("AmuletOfTheVoidwyrm") == ["AmuletOfTheVoidwyrm_CritDamageReduction"]
    assert r.get("NetherRealmCasket") == ["NetherRealmCasket_CritDamageReduction",
                                          "NetherRealmCasket_LivingMetalBonus"]
    # Ordinaux LUS au decompile (`GetEffectType` / les deux `AddEffect`), figes ici.
    assert int(EffectType.IntoxicatingElixir) == 0x5b3 == 1459
    assert int(EffectType.AmuletOfTheVoidwyrm_CritDamageReduction) == 0x5b4 == 1460
    assert int(EffectType.NetherRealmCasket_CritDamageReduction) == 0x5af == 1455
    assert int(EffectType.NetherRealmCasket_LivingMetalBonus) == 0x5b0 == 1456
    # `hpToHeal` = la variable du `CreateEffectRepairBonus` de 1456, face NON portee mais NOMMEE.
    assert int(AbilityVariableType.hpToHeal) == 0x20
    # Les trois abilities existent au gameconfig sous CES noms (la cle du registre en depend).
    import gameconfig as GC
    for nom in ("IntoxicatingElixir", "AmuletOfTheVoidwyrm", "NetherRealmCasket"):
        assert GC.ability(nom) is not None, "%s absente du gameconfig" % nom


def test_les_trois_effets_seedes_ont_un_lecteur_sauf_celui_qui_est_NOMME():
    """Trois des quatre effets seedes ont une CLASSE dans `EFFECT_CLASSES` ; le quatrieme (1456)
    n'en a pas, et c'est ECRIT -- son instance sera un `BaseEffect` NU, visible et inerte, le regime
    deja assume par `LegendaryCommander_ExtraDamage`. Le natif POSE les deux : n'en seeder qu'un
    ferait mentir `HasEffect(owner, 1456)`."""
    for nom in ("IntoxicatingElixir", "AmuletOfTheVoidwyrm_CritDamageReduction",
                "NetherRealmCasket_CritDamageReduction"):
        assert FACT.EFFECT_CLASSES.get(nom) is not None, "%s a perdu sa classe" % nom
    assert FACT.EFFECT_CLASSES.get("NetherRealmCasket_LivingMetalBonus") is None, (
        "1456 a desormais une classe : mettre a jour le commentaire de son entree, qui declare "
        "explicitement son instance INERTE")
