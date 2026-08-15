"""#1020-r5 / #1020-r7 -- garde OFFLINE de `RapidFire` (1135) et du canal de BLOCAGE d'ability.

Ce fichier ne monte AUCUN runner. Il garde ce qu'un test live ne montrerait pas : les REGIMES
SEPARANTS des deux gardes de re-entrance, le litteral `resetMovement = 0` (dont l'inverse est le
call-site du VOISIN `FightingRetreat`), et le fait que le canal de blocage reconnaisse le TROISIEME
membre de la famille -- celui que la convention de nom ratait.

NEUF etages, chacun avec une raison MESUREE pendant la tranche :

  1. `RapidFire` est au registre `ABILITY_TRIGGERS`, avec la bonne classe et le bon `event_id` ;
  2. `NOT HasFlag(Caster, Moved)` mord SEUL ;
  3. `NOT HasEffect(Caster, 1137, 0, 6)` mord SEUL -- les deux gardes sont independants, et un port
     qui n'en ecrirait qu'un resterait vert sur l'autre regime ;
  4. `IsNormalAttack()` mord : un CAST d'actif ne rouvre pas le tour ;
  5. `ResetTurn(Owner, resetMovement = 0)` retire `ActiveAbilityUsed`/`TurnFinished` mais **PAS**
     `Moved` ni `ArrivedAtFinalTile`. Recopier le `1` de `FightingRetreat` rendrait l'unite mobile,
     et le natif dit le contraire ;
  6. le behaviour pose 1137 pour UN TOUR (`Direct(1)`, deja en TOURS -- pas un `TurnsFromRounds`) et
     pose le drapeau `Moved` ;
  7. `can_use_ability` BLOQUE l'actif sur 1137 -- le membre que le suffixe `_CantUseAbility` ratait ;
  8. CONTRE-EPREUVE de la convention : le suffixe ne couvre QUE 2 des 3 membres. C'est l'etage qui
     rend la faute visible plutot que de la raconter ;
  9. le registre `ACTIVE_ABILITY_BLOCKER_EFFECTS` est CONCORDANT avec l'enum, et la condition du
     repli documente (`includeMachinePrimaryAbility` vrai pour TOUS) est verifiee -- le jour ou un
     membre ne la porte plus, ce test rougit et la branche machine doit etre separee.
"""
from __future__ import annotations

from engine.dsl.effects import ExecutionContext
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effect_type import EffectType
from engine.entities.effects.base import BaseEffect
from engine.entities.effects_state import EffectsState
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_context import UnitContext
from engine.entities.unit_flag import UnitFlag
from engine import battle_query as BQ
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent, UnitFlagsComponent,
                                      has_effect_of_type)
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.dispatch import registry as REG
from engine.runner.operations.triggers.loki import rapid_fire as RF
from engine.runner.state import State

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        # PROPRE A CE FICHIER, perimetre pris LARGE : les etages 1/9 lisent des REGISTRES que
        # n'importe quel module d'`engine` peut alimenter, les etages 2-6 executent le pipeline de
        # pose d'effet et de drapeaux, et les etages 7/8 traversent `engine/battle_query.py`.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # Les ordinaux (etages 1, 6, 9) viennent du dump.
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : les DEUX gardes de re-entrance de `RapidFireAbility$$CreateTrigger` "
              "(`NOT HasFlag(Moved)` et `NOT HasEffect(1137)`), chacun mesure SEUL ; le litteral "
              "`resetMovement = 0` du `ResetTurn`, dont l'inverse est le call-site du voisin "
              "`FightingRetreat` et rendrait l'unite mobile ; la duree `Direct(1)` DEJA EN TOURS ; "
              "et le TROISIEME membre de `BlockActiveAbilityEffect` (1137 RapidFire_BlockAbilities), "
              "que la reconnaissance par SUFFIXE `_CantUseAbility` ratait structurellement -- lu par "
              "`probe_10018_effectsdatabase_registry.py` dans le code machine d'InitializeEffects.",
}

RAPID_FIRE = 1135                      #: `TriggeredAbilityType.RapidFire`, ordinal MESURE
BLOCK_ABILITIES = 1137                 #: `EffectType.RapidFire_BlockAbilities`, ordinal MESURE
TAUNTED_CANT_USE = 26                  #: `EffectType.Taunted_CantUseAbility`
STUNNED_CANT_USE = 1165                #: `EffectType.Stunned_CantUseAbility`


def _porteur(st, *, moved: bool, flags=(), col=0, row=0):
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id="ultraEliminatorSgt", alive=True))
    e.add_component(OwnerComponent(team=0, player=0))
    ctx = UnitContext(entity_id=e.id, visual_id="ultraEliminatorSgt")
    ctx.passive_ability_level = 50
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=1000, hp_max=1000))
    e.add_component(PositionComponent(col=col, row=row))
    fl = UnitFlagsComponent()
    for f in flags:
        fl.add(int(f))
    if moved:
        fl.add(int(UnitFlag.Moved))
    e.add_component(fl)
    return e.id


def _etat():
    st = State()
    st.effects = EffectsState()
    return st


def _event(actor: int, *, ability_type):
    return TriggerEvent(int(EventTriggerType.UnitPostAbility), actor, actor,
                        ranged=True, profile=None, ability_type=ability_type)


#: L'`ActiveAbilityType` de l'attaque normale tel que le port le threade (`is_normal_attack`).
def _type_attaque_normale():
    from engine.runner.abilities.attack_type import NORMAL_ATTACK_KIND
    return NORMAL_ATTACK_KIND


# --- etage 1 : le registre -------------------------------------------------------------------
def test_etape1_rapid_fire_est_au_registre():
    assert int(TriggeredAbilityType.RapidFire) == RAPID_FIRE
    assert int(EffectType.RapidFire_BlockAbilities) == BLOCK_ABILITIES
    inscrites = REG.ABILITY_TRIGGERS.get(TriggeredAbilityType.RapidFire.name)
    assert inscrites == [RF.RapidFireAbility], (
        "le passif `RapidFire` doit etre inscrit sous son nom gameconfig ; sinon le trigger est "
        "MUET et l'effet 1137 n'est jamais pose -- l'elargissement de `can_use_ability` serait "
        "alors INERTE, ce que la fiche #1020-r5 exige d'eviter")
    assert RF.RapidFireAbility.event_id == int(EventTriggerType.UnitPostAbility) == 0xe
    assert RF.RapidFireAbility.TRIGGERED_ABILITY_ID == RAPID_FIRE


# --- etage 2 : `NOT HasFlag(Caster, Moved)` mord SEUL -----------------------------------------
def test_etape2_le_drapeau_moved_refuse_seul():
    st = _etat()
    uid = _porteur(st, moved=False)
    ab = RF.RapidFireAbility(uid)
    ev = _event(uid, ability_type=_type_attaque_normale())
    assert ab.matches(st, ev) is True, "regime de reference : sans `Moved`, le trigger passe"

    st2 = _etat()
    uid2 = _porteur(st2, moved=True)
    ab2 = RF.RapidFireAbility(uid2)
    assert ab2.matches(st2, _event(uid2, ability_type=_type_attaque_normale())) is False, (
        "`NOT HasFlag(Caster@<+0x48>, 0x0 = Moved)` : une unite qui a bouge n'obtient PAS "
        "la seconde attaque")


# --- etage 3 : `NOT HasEffect(Caster, 1137)` mord SEUL ----------------------------------------
def test_etape3_le_second_garde_de_reentrance_refuse_seul():
    st = _etat()
    uid = _porteur(st, moved=False)
    st.effects.add_effect(uid, BaseEffect(EffectType.RapidFire_BlockAbilities.name,
                                          effect_type=BLOCK_ABILITIES,
                                          remaining_turns=1, source=uid, target=uid))
    assert has_effect_of_type(st, uid, BLOCK_ABILITIES) is True
    ab = RF.RapidFireAbility(uid)
    assert ab.matches(st, _event(uid, ability_type=_type_attaque_normale())) is False, (
        "`NOT HasEffect(Caster, 0x471, onlyActive: 0, effectTarget: 6)` : le porteur n'a PAS bouge "
        "(le garde du drapeau ne mord pas ici), c'est l'EFFET seul qui doit refuser -- les deux "
        "gardes du trigger sont independants")


# --- etage 4 : `IsNormalAttack()` ---------------------------------------------------------------
def test_etape4_un_cast_d_actif_ne_rouvre_pas_le_tour():
    st = _etat()
    uid = _porteur(st, moved=False)
    ab = RF.RapidFireAbility(uid)
    # 1174 `SolarAtomizer` : un `ActiveAbilityType` quelconque qui n'est PAS une attaque reguliere.
    assert ab.matches(st, _event(uid, ability_type=1174)) is False
    assert ab.matches(st, _event(uid, ability_type=None)) is False, (
        "`ability_type` non threade -> NON MESURE -> refus (degradation RESTRICTIVE)")


# --- etage 5 : `resetMovement = 0` ---------------------------------------------------------------
def test_etape5_le_reset_ne_rend_pas_la_mobilite():
    st = _etat()
    uid = _porteur(st, moved=False, flags=(UnitFlagsComponent.ACTIVE_ABILITY_USED,
                                           int(UnitFlag.ArrivedAtFinalTile)))
    ab = RF.RapidFireAbility(uid)
    out = ab.execute_behaviour(st, _event(uid, ability_type=_type_attaque_normale()))
    fl = st.get_entity(uid).get_component(UnitFlagsComponent)
    assert not fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED), (
        "`ResetTurn` retire TOUJOURS `ActiveAbilityUsed` : c'est ce qui rend l'unite re-activable")
    assert fl.has(int(UnitFlag.ArrivedAtFinalTile)), (
        "`resetMovement = 0` (2e argument LU du `ResetTurn`) : `ArrivedAtFinalTile` RESTE. Le "
        "call-site voisin `FightingRetreat` passe `1` et le retirerait -- recopier ce voisin de "
        "forme rendrait l'unite mobile, l'exact contraire de la mecanique")
    assert UnitFlagsComponent.ACTIVE_ABILITY_USED in (out or {}).get("reset_flags", ())


# --- etage 6 : l'effet est pose, pour UN TOUR, et le drapeau `Moved` tombe -----------------------
def test_etape6_pose_de_1137_et_du_drapeau_moved():
    st = _etat()
    uid = _porteur(st, moved=False)
    ab = RF.RapidFireAbility(uid)
    out = ab.execute_behaviour(st, _event(uid, ability_type=_type_attaque_normale()))
    assert out["blocked"] is True and out["effect"] == BLOCK_ABILITIES
    assert out["moved_flag_added"] is True
    fl = st.get_entity(uid).get_component(UnitFlagsComponent)
    assert fl.has(int(UnitFlag.Moved)), (
        "`AddFlag(Caster@<+0x48>, 0x0 = Moved)` : c'est CE drapeau qui eteint le conjoint "
        "`NOT HasFlag(Owner, 0)` de `HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` -- l'unique "
        "effet DAMAGE de cette ability, et il est indirect")
    poses = [e for e in st.effects.by_unit.get(uid, ()) if int(e.effect_type) == BLOCK_ABILITIES]
    assert len(poses) == 1
    assert int(poses[0].remaining_turns) == 1, (
        "`turns = <DSLFormulas+0x20> = Direct(1)` -- une duree DEJA EN TOURS. La convertir depuis "
        "des ROUNDS (`TurnsFromRounds`) doublerait la fenetre de blocage")
    # le trigger ne peut plus repartir : les DEUX gardes sont armes
    assert ab.matches(st, _event(uid, ability_type=_type_attaque_normale())) is False


# --- etage 7 : `can_use_ability` reconnait 1137 --------------------------------------------------
def test_etape7_le_canal_de_blocage_voit_le_troisieme_membre():
    porteur = {"effects": [{"effectType": BLOCK_ABILITIES,
                            "name": EffectType.RapidFire_BlockAbilities.name}]}
    assert BQ.can_use_ability(porteur, {"kind": "active"}) is False, (
        "`ActiveAbilitiesAreBlocked() = blockers.Count > 0` : 1137 ferme les ACTIFS")
    assert BQ.can_use_ability(porteur, {"kind": "normal"}) is True, (
        "`NormalAttackIsBlocked() = any(v.includeNormalAttack)` et les trois membres portent 0 -- "
        "c'est toute la mecanique : la seconde action ne peut etre qu'une attaque NORMALE")
    # les deux membres historiques ne changent pas de verdict
    for et in (TAUNTED_CANT_USE, STUNNED_CANT_USE):
        u = {"effects": [{"effectType": et}]}
        assert BQ.can_use_ability(u, {"kind": "active"}) is False
        assert BQ.can_use_ability(u, {"kind": "normal"}) is True
    # un effet hors famille ne bloque rien
    assert BQ.can_use_ability({"effects": [{"effectType": 31, "name": "StatModifier"}]},
                              {"kind": "active"}) is True


# --- etage 8 : la CONVENTION de nom ne couvre pas la famille ------------------------------------
def test_etape8_le_suffixe_ratait_structurellement_un_membre():
    membres = set(BQ.ACTIVE_ABILITY_BLOCKER_EFFECTS)
    assert membres == {TAUNTED_CANT_USE, BLOCK_ABILITIES, STUNNED_CANT_USE}
    par_suffixe = {int(m) for m in EffectType if m.name.endswith("_CantUseAbility")}
    assert par_suffixe == {TAUNTED_CANT_USE, STUNNED_CANT_USE}
    manques = membres - par_suffixe
    assert manques == {BLOCK_ABILITIES}, (
        "CONTRE-EPREUVE : la reconnaissance par SUFFIXE `_CantUseAbility` couvre 2 membres sur 3. "
        "Le troisieme s'appelle `RapidFire_BlockAbilities` -- une convention de nom n'est jamais "
        "une source, seul le litteral du decompile en est une")
    # et l'appariement du registre reste concordant avec l'enum, nom PAR nom
    for et, spec in BQ.ACTIVE_ABILITY_BLOCKER_EFFECTS.items():
        assert EffectType(et).name == spec["name"], (
            "l'enum a bouge sous le registre : re-derivez `probe_10018_effectsdatabase_registry.py`")


# --- etage 9 : la branche MACHINE est SEPAREE, et elle consulte SON booleen ----------------------
def test_etape9_la_branche_machine_primaire_est_separee():
    """#1020-r9 -- ce que gardait l'etage 9 d'avant etait le REPLI (`MachinePrimaryAbilityIsBlocked`
    fondu dans `ActiveAbilitiesAreBlocked`), et son message prescrivait le geste fait ici :
    « il faut alors separer la branche, pas relacher ce test ». La branche EST separee, donc l'etage
    garde desormais la SEPARATION -- ce qui est strictement plus fort : l'assertion d'avant
    (`all(include_machine_primary_ability)`) reste vraie et reste asserte ci-dessous, mais elle ne
    justifie plus un repli, elle explique seulement pourquoi l'ecart est NUL aujourd'hui."""
    specs = BQ.ACTIVE_ABILITY_BLOCKER_EFFECTS.values()
    assert specs, "registre vide : ce test serait vacant"
    assert all(s["include_machine_primary_ability"] for s in specs), (
        "les trois membres portent `includeMachinePrimaryAbility = 1` : c'est CE fait qui rend "
        "l'ecart de la separation NUL aujourd'hui. Un membre a `0` le rendrait observable -- et la "
        "branche separee ci-dessous le prendra alors correctement en compte, sans retouche")
    assert not any(s["include_normal_attack"] for s in specs), (
        "aucun membre ne bloque l'attaque normale ; si l'un le fait un jour, `can_use_ability` le "
        "prend deja en compte (le corps DERIVE du registre) -- c'est cette assertion qui doit "
        "changer, et elle rend le changement visible")

    # --- le DISCRIMINANT : `machineId` (present sur `decisionView.mows`, absent de `.units`) et
    #     l'INDICE 0 de la liste d'actives (= `ActiveAbilityComponent+0x30`, ecrit par
    #     `MachineFactory$$AddConfiguredAbilities`). Formes MESUREES live (MC1_67, adeptExorcist).
    mow = {"machineId": 87, "visualId": "adeptExorcist",
           "abilities": [{"id": 1187, "kind": "active"}, {"id": 1188, "kind": "active"}]}
    unite = {"abilities": [{"id": 1187, "kind": "active"}]}          # pas de `machineId`
    assert BQ.machine_primary_ability_id(mow) == 1187, "l'indice 0 des ACTIVES est la primaire"
    assert BQ.machine_primary_ability_id(unite) is None, (
        "sans `machineId`, `kind(unit) != EntityKind.Machine` -> le natif rend 0")
    assert BQ.machine_primary_ability_id({"machineId": 1, "abilities": []}) is None, (
        "canal muet -> NON MESURE, jamais un id invente")
    # le canal EXPLICITE prime sur l'indice quand le dedup de `mowAbilityTypes` ne l'a pas efface
    assert BQ.machine_primary_ability_id(
        {"machineId": 1, "abilities": [{"id": 9, "kind": "active"},
                                       {"id": 7, "kind": "machinePrimary"}]}) == 7
    # l'attaque NORMALE, poussee en tete par `unitAbilityTypes`, n'est jamais prise pour la primaire
    assert BQ.machine_primary_ability_id(
        {"machineId": 1, "abilities": [{"id": 3, "kind": "normal"},
                                       {"id": 5, "kind": "active"}]}) == 5

    # --- ECART NUL aujourd'hui : la branche separee rend le MEME verdict que le repli, sur les
    #     trois membres du registre et sur les deux etats (bloqueur present / absent).
    for et in BQ.ACTIVE_ABILITY_BLOCKER_EFFECTS:
        bloquee = {**mow, "effects": [{"effectType": et}]}
        assert BQ.can_use_ability(bloquee, {"kind": "active", "id": 1187}) is False
        assert BQ.can_use_ability(bloquee, {"kind": "active", "id": 1188}) is False
    assert BQ.can_use_ability({**mow, "effects": []}, {"kind": "active", "id": 1187}) is True

    # --- CONTRE-EPREUVE : un membre a `include_machine_primary_ability = False` fait DIVERGER les
    #     deux bras. Sans elle, ce test passerait sur le code d'AVANT (le repli), donc ne prouverait
    #     pas que la branche est separee. Registre restaure par `finally`.
    faux = 999_999
    BQ.ACTIVE_ABILITY_BLOCKER_EFFECTS[faux] = {
        "name": "TEMOIN_include_machine_primary_ability_a_zero",
        "include_normal_attack": False, "include_machine_primary_ability": False}
    try:
        porteur = {**mow, "effects": [{"effectType": faux}]}
        assert BQ.can_use_ability(porteur, {"kind": "active", "id": 1187}) is True, (
            "branche SEPAREE : `MachinePrimaryAbilityIsBlocked() = any(v[+9])` est FAUX -> la "
            "primaire de la MoW reste utilisable. Le repli d'avant rendait `False` (RESTRICTIF)")
        assert BQ.can_use_ability(porteur, {"kind": "active", "id": 1188}) is False, (
            "la SECONDAIRE, elle, passe par `ActiveAbilitiesAreBlocked() = Count > 0` -> bloquee")
        assert BQ.can_use_ability({"effects": [{"effectType": faux}]},
                                  {"kind": "active", "id": 1187}) is False, (
            "une UNITE (pas de `machineId`) n'emprunte jamais la branche machine")
    finally:
        BQ.ACTIVE_ABILITY_BLOCKER_EFFECTS.pop(faux, None)
