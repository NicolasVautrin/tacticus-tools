"""Garde OFFLINE de #964-r1 -- `EcogSupport` (`TriggeredAbilityType` 1487), passif de
`votanIronmaster` << Vynn >>.

Ce fichier fige ce qu'un rebuild, un renumerotage d'enum ou un refactor peuvent casser EN SILENCE.
Il ne mesure rien qui ne soit LU au decompile (`rnca9r7q6c`) ; la confrontation live vit dans
`scripts/python/probe_964r1_ecog_support.py`.

SEPT etages, et chacun garde un mode de panne DISTINCT :

  1. les ordinaux ECRITS AUX SITES (`probe_313` compare le mirror au build, pas le site) ;
  2. l'inscription au registre, sur le BON vecteur et dans le BON registre ;
  3. le flag d'init ET SON LECTEUR -- c'est ce couple qui separe un port d'un mensonge de
     couverture ;
  4. l'EMETTEUR `On(0x30 UnitRepaired)`, sans lequel l'etage 2 serait registered-but-dead ;
  5. la STRUCTURE de l'arbre (`If(maxSummons > count, Spawn, PerformAIAbility)`) et ses trois
     parametres qui ne se devinent pas ;
  6. l'asymetrie de `UnitNormalRepairType` face a son jumeau ATTACK ;
  7. la NON-REGRESSION des huit appelants anterieurs de `PerformAIAbility`.

ASCII only (console cp1252).
"""
from __future__ import annotations

#: Perimetre du declencheur (#486-r15).
DECLENCHEUR = {
    # VIDE, et ce n'est pas un oubli : `probe_486r15 --proposer` mesure que la fermeture d'imports
    # de ce fichier (568 modules) est ENTIEREMENT couverte par la cascade DERIVEE du foyer -- les
    # 25 chemins que ce port touche (module porteur, les deux registres, le vecteur `On(0x30)`, les
    # trois etages neufs, `PerformAIAbility` et son corps partage, le gate de reparation, le seed
    # d'init, les cinq mirrors d'enum) y sont tous. Les redeclarer serait du bruit que #531 interdit.
    "chemins": (),
    # Le fichier LIT le gameconfig versionne (`maxSummons = 3`, `unitId = votanSmnEcog`,
    # `votanIronmaster.passiveAbilities`, `votanSmnEcog.traits`) : un changement de build peut le
    # faire changer de verdict, et c'est ce qu'on veut qu'il fasse.
    "build": True,
    "toujours": False,
    "raison": ("Purement offline : le fichier ne lit que les registres, les mirrors d'enum, la "
               "STRUCTURE des arbres (par construction, sans les executer) et le gameconfig "
               "versionne. Aucun runner, aucun RPC, aucun etat live -- il ne peut donc changer de "
               "verdict que par un de ces deux canaux, l'un derive du foyer, l'autre declare par "
               "`build`. Il prouve que le port d'`EcogSupport` est CABLE (registre + flag + "
               "emetteur) et que ses six lectures non devinables (sens de l'If, Func de repair, "
               "override_movement, ActiveTarget, mode de selection, substrat du repair-type) sont "
               "figees. Ce qu'il NE prouve PAS -- que le trigger fire et que l'E-Cog apparait -- "
               "est le perimetre de `probe_964r1_ecog_support.py`, qui exige un runner."),
}

import inspect

import pytest

from engine.dsl.base import Const, DslContext
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.behaviours import If
from engine.entities.formulas import UnitNormalAttackType, UnitNormalRepairType
from engine.entities.selectors.accessors import ActiveTarget, Owner
from engine.entities.selectors.valid_targets import UnitsWithAnyValidTarget
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_flag import UnitFlag
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.abilities.behaviours.ai_control import PerformAIAbility
from engine.runner.abilities.behaviours.summon import Spawn
from engine.runner.operations.triggers.loki import ecog_support as ES


# --------------------------------------------------------------------------------------------- #
# Etage 1 -- les ordinaux ECRITS AUX SITES
# --------------------------------------------------------------------------------------------- #

def test_ordinaux_ecrits_aux_sites():
    """Les cinq valeurs que le port ECRIT, figees a la valeur MESUREE a la conversion.

    `probe_313` compare le MIRROR au BUILD : il redevient vert des qu'on regenere le mirror apres
    un renumerotage, alors que la valeur ecrite au site, elle, a change. C'est ce cran-la."""
    assert int(TriggeredAbilityType.EcogSupport) == 0x5cf == 1487
    assert int(EventTriggerType.UnitRepaired) == 0x30 == 48
    assert int(AbilityConstantType.maxSummons) == 0x3c == 60
    assert int(AbilityConstantType.unitId) == 0x0
    assert int(UnitFlag.CanRepairFullHealthUnits) == 0x18 == 24
    assert int(UnitSelectionType.OnlyAliveAndTargetable) == 3


def test_constantes_gameconfig():
    """`GetNumberConstant(0x3c)` = 3 et `GetStringConstant(0)` = `votanSmnEcog`, LUES au gameconfig
    vivant. Le decompile ne donne que les CLES ; ce test garde les VALEURS."""
    import gameconfig as GC
    consts = (GC.ability("EcogSupport") or {}).get("constants") or {}
    assert int(consts["maxSummons"]) == 3
    assert consts["unitId"] == "votanSmnEcog"
    assert ES._max_summons() == 3


def test_porteur_et_summon_existent_au_gameconfig():
    """`votanIronmaster` porte bien `EcogSupport` en PASSIF, et `votanSmnEcog` existe."""
    import gameconfig as GC
    assert "EcogSupport" in ((GC.unit("votanIronmaster") or {}).get("passiveAbilities") or [])
    assert GC.unit("votanSmnEcog") is not None


# --------------------------------------------------------------------------------------------- #
# Etage 2 -- le registre, le vecteur, et le piege de NAMESPACE
# --------------------------------------------------------------------------------------------- #

def test_inscrit_au_registre_des_passives_sur_le_vecteur_unit_repaired():
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    classes = ABILITY_TRIGGERS.get("EcogSupport")
    assert classes == [ES.ECogSupportAbility]
    assert ES.ECogSupportAbility.event_id == int(EventTriggerType.UnitRepaired)
    assert int(ES.ECogSupportAbility.TRIGGERED_ABILITY_ID) == 1487


def test_absent_des_registres_d_actives_et_d_effets():
    """PIEGE DE NAMESPACE : `1487` peut etre un membre valide d'un AUTRE enum. `EcogSupport` est un
    `TriggeredAbilityType` -- il n'a rien a faire dans les registres d'ACTIVES ni d'EFFETS."""
    from engine.runner.operations.triggers.dispatch.registry import (ACTIVE_ABILITY_TRIGGERS,
                                                                     EFFECT_TRIGGERS)
    from engine.runner.abilities.handler import ABILITY_CLASSES
    assert "EcogSupport" not in ACTIVE_ABILITY_TRIGGERS
    assert 1487 not in ABILITY_CLASSES
    assert 1487 not in EFFECT_TRIGGERS


def test_init_ability_n_est_PAS_dans_ability_triggers():
    """`ECogSupport_InitAbility` est un `OnOwnerSpecificAbilityInit`, pas un event : l'inscrire ici
    creerait un trigger que rien n'emet. Son canal est `ABILITY_INIT_OWNER_FLAGS`."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    assert len(ABILITY_TRIGGERS["EcogSupport"]) == 1


# --------------------------------------------------------------------------------------------- #
# Etage 3 -- le flag d'init ET SON LECTEUR (le couple, pas la moitie)
# --------------------------------------------------------------------------------------------- #

def test_flag_d_init_inscrit():
    from engine.entities.effects.factory import (ABILITY_INIT_OWNER_FLAGS,
                                                 get_owner_flags_added_on_ability_init)
    assert ABILITY_INIT_OWNER_FLAGS["EcogSupport"] == [int(UnitFlag.CanRepairFullHealthUnits)]
    assert get_owner_flags_added_on_ability_init("EcogSupport") == [24]
    assert get_owner_flags_added_on_ability_init("<inexistante>") == []


def test_le_lecteur_du_flag_EXISTE_et_MORD():
    """LE test qui separe le port du mensonge de couverture.

    `AttackQuery$$EntityCanBeRepaired` a pour 4e disjunct `caster != null && HasFlag(caster,
    0x18)`. On le lit SUR LE SOURCE du foyer unique -- un balayage de MENTIONS compterait les
    docstrings (#965 a cru une ability portee sur 9 occurrences, toutes en prose)."""
    from engine.runner.abilities import attack_query as AQ
    src = inspect.getsource(AQ.entity_can_be_repaired)
    assert "UNIT_FLAG_CAN_REPAIR_FULL_HEALTH" in src, "le disjunct du flag a disparu du gate"
    assert int(AQ.UNIT_FLAG_CAN_REPAIR_FULL_HEALTH) == int(UnitFlag.CanRepairFullHealthUnits)


def test_le_seed_pose_le_flag():
    """`_seed_ability_owner_effects` (boucle `InitializeActorAbilitiesOperation$$Execute`) consomme
    bien le registre de FLAGS, pas seulement celui des EFFETS."""
    from engine.runner.operations import spawn as SP
    src = inspect.getsource(SP._seed_ability_owner_effects)
    assert "get_owner_flags_added_on_ability_init" in src
    assert "_add_owner_flag_on_ability_init" in src


# --------------------------------------------------------------------------------------------- #
# Etage 4 -- l'EMETTEUR, sans lequel tout le reste serait registered-but-dead
# --------------------------------------------------------------------------------------------- #

def test_l_emetteur_unit_repaired_existe():
    from engine.runner.operations.triggers.dispatch import repair as RD
    assert callable(RD.unit_repaired_triggers)


def test_repair_operation_appelle_l_emetteur():
    """Le vecteur n'a de valeur que s'il est APPELE, et a la BONNE place : le natif l'emet APRES la
    mutation `FillUp` et APRES le gate de sortie anticipee (`if (filled <= 0) return 0`)."""
    from engine.runner.operations.repair import RepairUnitOperation
    src = inspect.getsource(RepairUnitOperation.execute)
    assert "unit_repaired_triggers" in src
    i_gate = src.index("if filled <= 0")
    i_emit = src.index("unit_repaired_triggers")
    assert i_gate < i_emit, "l'event doit etre emis APRES le gate de sortie anticipee"


def test_l_emetteur_porte_le_reparateur_en_acteur():
    """`processor.<slot 0x51>(caster, caster, target, 0x30, ...)` : c'est le REPARATEUR qui occupe
    le slot ACTOR -- c'est ce qui rend `get_OwnerIsCaster` discriminant."""
    from engine.runner.operations.triggers.dispatch import repair as RD
    src = inspect.getsource(RD.unit_repaired_triggers)
    assert "EventTriggerType.UnitRepaired" in src
    assert "caster_id" in src


# --------------------------------------------------------------------------------------------- #
# Etage 5 -- la STRUCTURE de l'arbre et ses trois parametres qui ne se devinent pas
# --------------------------------------------------------------------------------------------- #

def test_arbre_forme_et_sens_du_if():
    """`If( AmountIsGreater(maxSummons, Count(dejaSummones)), Spawn, PerformAIAbility )`.

    Le SENS est load-bearing : `maxSummons > count` ⇒ `then` = SPAWN. L'inverser ferait reparer
    tant qu'il reste de la place et spawner une fois le cap atteint -- exactement le contraire."""
    tree = ES.ecog_support_tree(3)
    assert isinstance(tree, If)
    assert isinstance(tree.then, Spawn)
    assert isinstance(tree.otherwise, PerformAIAbility)
    # `AmountIsGreater(a, b)` = `a > b` STRICT, avec `a` = maxSummons.
    assert tree.cond.a.evaluate(None) == 3


def test_perform_ai_ability_joue_le_REPAIR_pas_l_attaque_normale():
    """Le `Func<IEntity,int>` `+0x68` = `GetRepairType`, PAS `GetNormalAttackType`.

    C'est le piege du voisin de forme : les QUATRE autres noeuds de cette famille cachent leur
    `Func` dans un `<>c` et il vaut l'attaque normale ; le port le codait donc en dur."""
    tree = ES.ecog_support_tree(3)
    assert tree.otherwise.get_ability_type is ES._repair_type_of


def test_override_movement_est_direct_zero_pas_none():
    """`overrideMovement = <DSLFormulas+0x18 = Direct(0)>` -> `GenerateActionTiles(maxDistance = 0)`
    = la tuile COURANTE seule. Un `None` ouvrirait la plage de deplacement normale de l'E-Cog."""
    tree = ES.ecog_support_tree(3)
    om = tree.otherwise.override_movement
    assert isinstance(om, Const)
    assert int(om.evaluate(None)) == 0


def test_le_cap_compte_les_enfants_vivants_et_ciblables():
    """`UnitsWithId(Children(Owner), unitId, 3)` -- `Children` ne filtre RIEN, donc sans le mode un
    E-Cog MORT tiendrait un slot que le natif a libere."""
    sel = ES.already_summoned_units()
    assert sel.unit_id == "votanSmnEcog"
    assert int(sel.mode) == int(UnitSelectionType.OnlyAliveAndTargetable)


def test_le_filtre_de_reparation_lit_ACTIVE_TARGET():
    """`UnitNormalRepairType(ActiveTarget@+0x68)`, jamais `Owner` ni `Caster`.

    C'est ce qui rend le filtre PAR E-COG : `UnitsWithAnyValidTargetSelector$$Select` ECRIT
    l'unite courante dans `AbilityEntities+0x20` (= `activeTarget`) avant chaque evaluation."""
    sel = ES.get_possible_trigger_repair_summons()
    assert isinstance(sel, UnitsWithAnyValidTarget)
    assert isinstance(sel.ability_sel, UnitNormalRepairType)
    assert isinstance(sel.ability_sel.selector, ActiveTarget)


def test_le_spawn_prend_ses_stats_du_passif():
    """`SpawnUnitOptions$$WithStatsFromConfig(config, abilityState, 0, 0)` : sans l'`abilityState`,
    l'E-Cog lirait `summonHp`/`summonDmg`/`summonArmor` a l'index 0 (mode de panne #174)."""
    tree = ES.ecog_support_tree(3, ability_state=(50, 180))
    assert tree.then.ability_state == (50, 180)
    assert tree.then.summon_ability == "EcogSupport"


# --------------------------------------------------------------------------------------------- #
# Etage 6 -- l'asymetrie de `UnitNormalRepairType` (et son SUBSTRAT)
# --------------------------------------------------------------------------------------------- #

def test_repair_type_rend_None_sur_selecteur_vide():
    """`UnitNormalRepairAbilitySelector$$Select` GARDE son `SelectSingle` (`if (unit != null)`) et
    rend un `Nullable` VIDE ; `UnitNormalAttackAbilitySelector$$Select`, lui, n'a PAS cette garde.

    Le vide n'est pas « pas de filtre » : c'est un REJET (`if (ability.HasValue)` cote selecteur)."""
    ctx = DslContext(units=[], caster=None, target=None, board=None)
    assert UnitNormalRepairType(Owner()).calculate(ctx) is None


def test_le_substrat_du_repair_type_n_est_PAS_le_kit_gameconfig():
    """LE piege qui rendait ce port MUET, et il est MESURE.

    Le jumeau `UnitNormalAttackType` derive du `visualId` + gameconfig. Ce raccourci ne marche pas
    ici : `votanSmnEcog` -- le SEUL porteur qui compte -- a `activeAbilities = []` au gameconfig et
    repare quand meme (il tient l'ability de son TRAIT `Mechanic`). Une derivation par kit aurait
    rendu `None` sur lui, donc un filtre TOUJOURS VIDE, sans erreur ni trace."""
    import gameconfig as GC
    from engine.entities.traits.unit_trait import UnitTrait
    ecog = GC.unit("votanSmnEcog") or {}
    assert (ecog.get("activeAbilities") or []) == [], \
        "si l'E-Cog gagne une active au gameconfig, re-verifier l'ORDRE des trois voies"
    assert UnitTrait.Mechanic.name in (ecog.get("traits") or [])
    # La voie (3) EST donc celle qui repond pour ce porteur -- et elle rend l'ability GENERIQUE.
    from engine.entities.active_ability_type import ActiveAbilityType
    assert int(ActiveAbilityType.Repair) == 28
    src = inspect.getsource(_targeting_module().normal_repair_type_for)
    assert "UnitTrait.Mechanic" in src and "ActiveAbilityType.Repair" in src


def test_la_formule_passe_par_le_contexte_pas_par_le_gameconfig():
    """`UnitNormalRepairType` ne doit RIEN deriver elle-meme : elle consomme `ctx.normal_repair_type`
    (le foyer unique cote runner). Un second port de la lecture serait un fork."""
    # Le CORPS, pas la classe : la docstring PARLE du gameconfig (pour dire qu'elle ne le lit pas),
    # et un balayage de MENTIONS confondrait les deux -- meme vice que le `git grep` de #965.
    corps = inspect.getsource(UnitNormalRepairType.calculate)
    assert "normal_repair_type" in corps
    assert "gameconfig" not in corps, "la formule ne doit pas re-deriver le kit"


def _targeting_module():
    from engine.runner.abilities import targeting
    return targeting


def test_les_deux_formules_sont_DEUX_classes():
    """Jumelles au decompile (meme allocation, meme `.ctor(unit, 0)`), mais elles lisent des champs
    DIFFERENTS du meme composant : `+0x28` (attaque) contre `+0x2c` (reparation)."""
    assert UnitNormalRepairType is not UnitNormalAttackType
    src = inspect.getsource(UnitNormalRepairType)
    assert "0x2c" in src and "GetRepairType" in src


# --------------------------------------------------------------------------------------------- #
# Etage 6bis -- le selecteur neuf et son canal d'HONNETETE
# --------------------------------------------------------------------------------------------- #

def _ctx(units, probe=None, unknown=None):
    return DslContext(units=list(units), caster=None, target=None, board=None,
                      has_any_valid_target=probe, unknown_ability_types=unknown)


def test_selecteur_sans_accesseur_rend_vide_et_ne_filtre_pas_au_hasard():
    """Contexte hors runner : la cascade de ciblage n'est pas evaluable sans `State`. Le noeud rend
    `[]` -- degradation NOMMEE, jamais un verdict invente."""
    u = {"id": 1, "alive": True, "hp": 10}
    sel = UnitsWithAnyValidTarget(_FixedUnits([u]), _FixedAmount(28))
    assert sel.select(_ctx([u])) == []


def test_selecteur_ecarte_et_DECLARE_quand_le_masque_est_inconnu():
    """`probe` rend `None` = masque non RE-lu. L'unite est ECARTEE **et** l'ability est declaree :
    sans ce canal, « le natif l'exclut » et « le port ne sait pas » seraient indiscernables."""
    u = {"id": 1, "alive": True, "hp": 10}
    vus = set()
    sel = UnitsWithAnyValidTarget(_FixedUnits([u]), _FixedAmount(9999))
    assert sel.select(_ctx([u], probe=lambda unit, aid: None, unknown=vus)) == []
    assert vus == {9999}


def test_selecteur_ecarte_sur_nullable_VIDE_sans_appeler_le_predicat():
    """`if (ability.HasValue)` : un `None` de la formule fait SAUTER l'unite, et le predicat n'est
    meme pas consulte."""
    u = {"id": 1, "alive": True, "hp": 10}
    appels = []

    def probe(unit, aid):
        appels.append(aid)
        return True

    sel = UnitsWithAnyValidTarget(_FixedUnits([u]), _FixedAmount(None))
    assert sel.select(_ctx([u], probe=probe)) == []
    assert appels == []


def test_selecteur_pose_ACTIVE_TARGET_avant_d_evaluer_la_formule():
    """L'ECRITURE `entities.<+0x20> = unit` EST le mecanisme du noeud : la formule d'ability est
    evaluee PAR UNITE, sur un contexte ou l'unite courante est l'`ActiveTarget`."""
    a, b = {"id": 1, "alive": True, "hp": 10}, {"id": 2, "alive": True, "hp": 10}
    vus = []

    class _Espion:
        def evaluate(self, ctx):
            vus.append((ctx.active_target or {}).get("id"))
            return 28

    sel = UnitsWithAnyValidTarget(_FixedUnits([a, b]), _Espion())
    sel.select(_ctx([a, b], probe=lambda unit, aid: True))
    assert vus == [1, 2]


def test_selecteur_garde_ce_que_le_predicat_accepte():
    a, b = {"id": 1, "alive": True, "hp": 10}, {"id": 2, "alive": True, "hp": 10}
    sel = UnitsWithAnyValidTarget(_FixedUnits([a, b]), _FixedAmount(28))
    gardes = sel.select(_ctx([a, b], probe=lambda unit, aid: unit["id"] == 2))
    assert [u["id"] for u in gardes] == [2]


class _FixedUnits:
    """Selecteur-source de test : rend une liste figee."""
    def __init__(self, units):
        self.units = units

    def evaluate(self, ctx):
        return list(self.units)

    def select(self, ctx):
        return list(self.units)


class _FixedAmount:
    """Formule de test : rend une valeur figee (ou `None` = `Nullable` VIDE)."""
    def __init__(self, value):
        self.value = value

    def evaluate(self, ctx):
        return self.value


# --------------------------------------------------------------------------------------------- #
# Etage 7 -- NON-REGRESSION des huit appelants anterieurs de `PerformAIAbility`
# --------------------------------------------------------------------------------------------- #

def test_perform_ai_ability_sans_func_reste_sur_l_attaque_normale():
    """`get_ability_type = None` = le comportement d'avant, octet pour octet : les quatre noeuds
    natifs de cette famille CACHENT leur `Func` et il vaut `GetNormalAttackType`."""
    noeud = PerformAIAbility(_FixedUnits([]))
    assert noeud.get_ability_type is None


def test_le_corps_partage_conserve_son_defaut():
    """`perform_ai_ability_unit_behaviour(..., ability_type=None)` -> `NORMAL_ATTACK_ID`, et le
    clamp `_in_attack_range` (volet PORTEE D'ARME) reste arme sur ce seul chemin."""
    from engine.runner.abilities.loki.summon import perform_ai_ability_unit_behaviour as f
    sig = inspect.signature(f)
    assert sig.parameters["ability_type"].default is None
    src = inspect.getsource(f)
    assert "_aid = NORMAL_ATTACK_ID if ability_type is None else int(ability_type)" in src
    assert "if ability_type is None and not _in_attack_range" in src


def test_has_valid_targets_est_tri_etat():
    """`None` = masque non RE-lu. Le rabattre sur `False` filtrerait une unite que le natif garde ;
    sur `True`, il en garderait une que le natif ecarte. Les deux sont des inventions."""
    from engine.runner.abilities.targeting import has_valid_targets, valid_targets_for
    assert has_valid_targets(None, None, None) is None
    assert has_valid_targets(None, 1, None) is None
    assert valid_targets_for(None, 1, None) is None


if __name__ == "__main__":                                      # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
