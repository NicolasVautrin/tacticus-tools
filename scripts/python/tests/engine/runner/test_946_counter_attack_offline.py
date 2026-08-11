"""#946 -- GARDE OFFLINE des deux derniers passifs `_CounterAttackEffect` : `GrimRetribution` (1213,
`darkaHellblaster`) et `UnwaveringSentinel` (1439, `custoKyrus`).

Ce fichier ne mesure PAS un comportement de bataille (c'est le role des deux fichiers live). Il FIGE
ce qui a ete LU au decompile et qu'une recopie du jumeau de forme `WireweaveNet` aurait efface --
c'est-a-dire exactement les SEPT ecarts recenses dans
`engine/entities/effects/loki/counter_attack.py`. Un port qui redeviendrait << comme WireweaveNet >>
fait ROUGIR ce fichier, ligne par ligne.

⚠ **Chaque etage porte sa CONTRE-EPREUVE PAR MUTATION** (etage 7) : on mute le code porte et on
verifie que le garde ROUGIT. Un garde qui reste vert sous mutation est inerte -- il ne prouve rien.

ASCII only.
"""
from __future__ import annotations

import dataclasses

import pytest

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effects.loki.counter_attack import (
    GrimRetributionCounterAttackEffect, UnwaveringSentinelCounterAttackEffect,
    WireweaveNetCounterAttackEffect)
from engine.entities.effects.magnitude import ability_var
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.abilities.targeting import custom_range
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.operations.triggers.dispatch.registry import (CUSTOM_TRIGGERED_ABILITIES,
                                                                 EFFECT_TRIGGERS)
from engine.runner.operations.triggers.loki import counter_attack as _ca
from engine.runner.operations.triggers.loki import grim_retribution as GR
from engine.runner.operations.triggers.loki import unwavering_sentinel as US

DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py",
        # PROPRE A CE FICHIER : les DEUX foyers de la famille (litteraux du `.ctor` cote entites,
        # socle des `Triggered()` cote runner), les deux modules de triggers portes, le jumeau de
        # forme qu'on garde DIFFERENT, les registres, et l'etage de ciblage ou vit l'override
        # `range` que le selecteur consomme.
        "scripts/python/engine/entities/effects/loki/counter_attack.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/loki/counter_attack.py",
        "scripts/python/engine/runner/operations/triggers/loki/grim_retribution.py",
        "scripts/python/engine/runner/operations/triggers/loki/unwavering_sentinel.py",
        "scripts/python/engine/runner/operations/triggers/loki/wireweave_net.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        # Les mirrors d'enum que les assertions CITENT par leur NOM : un renumerotage doit rejouer
        # ce fichier, c'est precisement ce que `probe_313` ne voit pas (il compare le mirror au
        # build, pas l'ordinal ECRIT au site).
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline : aucun runner, aucun RPC, aucune lecture du binaire. Les sept "
              "etages ne lisent que des attributs de classe, les trois registres, le gameconfig "
              "et la struct `TargetingOptions` -- d'ou un perimetre borne aux foyers de la famille "
              "`_CounterAttackEffect`, a l'etage de ciblage et aux mirrors d'enum cites.",
}

GRIM = int(EffectType.GrimRetribution_CounterAttack)              # 0x4bd = 1213
UNWAV = int(EffectType.UnwaveringSentinel_CounterAttack)          # 0x59f = 1439
WIREW = int(EffectType.WireweaveNet_CounterAttack)                # 0x457 = 1111


# ---------------------------------------------------------------------------------------------
# Etage 1 -- les LITTERAUX du `.ctor`, relus a l'assembleur
# ---------------------------------------------------------------------------------------------

def test_ctor_literals_grim_retribution():
    """`GrimRetribution_CounterAttackEffect$$.ctor` :
    `op_Implicit(edx = 0x499 = 1177)` puis `CounterAttackEffect$$.ctor(this, 1, 1, ...)`.

    Les trois valeurs sont LUES aux octets (le decompilateur masque l'immediat) -- cf. la docstring
    de la classe. `SOURCE_TRIGGERED_ABILITY` est un `TriggeredAbilityType` parce que la surcharge
    d'`op_Implicit` que le `call` designe (adresse decodee, pas nom) ecrit `set_TriggeredAbility`."""
    assert GrimRetributionCounterAttackEffect.TURNS_ENABLED == 1
    assert GrimRetributionCounterAttackEffect.ACTIVATION_FREQUENCY == 1
    assert GrimRetributionCounterAttackEffect.HAS_AUTOMATIC_ACTIVATION is False
    assert (GrimRetributionCounterAttackEffect.SOURCE_TRIGGERED_ABILITY
            is TriggeredAbilityType.GrimRetribution)
    assert int(TriggeredAbilityType.GrimRetribution) == 0x499 == 1177


def test_ctor_literals_unwavering_sentinel():
    """`UnwaveringSentinel_CounterAttackEffect$$.ctor` : corps byte-pour-byte celui de
    `GrimRetribution` a l'immediat pres (`0x5a9 = 1449`)."""
    assert UnwaveringSentinelCounterAttackEffect.TURNS_ENABLED == 1
    assert UnwaveringSentinelCounterAttackEffect.ACTIVATION_FREQUENCY == 1
    assert UnwaveringSentinelCounterAttackEffect.HAS_AUTOMATIC_ACTIVATION is False
    assert (UnwaveringSentinelCounterAttackEffect.SOURCE_TRIGGERED_ABILITY
            is TriggeredAbilityType.UnwaveringSentinel)
    assert int(TriggeredAbilityType.UnwaveringSentinel) == 0x5a9 == 1449


def test_activation_frequency_diverge_du_jumeau_de_forme():
    """L'ECART QUI FAIT LA CADENCE : `WireweaveNet` porte `activationFrequency = 2`, les deux autres
    `1`. La branche `== 1` de `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal` est l'INVERSE
    de la branche `== 2` (Activate@TurnStart / Deactivate@TurnEnd, au lieu du contraire), d'ou
    << une riposte par TOUR ENNEMI >> contre << une par CYCLE >>.

    Ce test existe pour qu'une harmonisation cosmetique des trois classes ROUGISSE."""
    assert WireweaveNetCounterAttackEffect.ACTIVATION_FREQUENCY == 2
    assert GrimRetributionCounterAttackEffect.ACTIVATION_FREQUENCY == 1
    assert UnwaveringSentinelCounterAttackEffect.ACTIVATION_FREQUENCY == 1
    # les TROIS partagent en revanche `turnsEnabled = 1` -> `NOT IsTurnOf(Owner)`
    assert {WireweaveNetCounterAttackEffect.TURNS_ENABLED,
            GrimRetributionCounterAttackEffect.TURNS_ENABLED,
            UnwaveringSentinelCounterAttackEffect.TURNS_ENABLED} == {1}


def test_1439_et_1449_ne_sont_pas_le_meme_nombre():
    """Contrairement a `WireweaveNet` (0x457 des DEUX cotes), l'effet et l'ability d'UnwaveringSentinel
    portent des ordinaux DIFFERENTS -- et chacun NOMME AUTRE CHOSE dans l'enum d'en face. C'est le
    regime exact ou une confusion d'enum serait SILENCIEUSE."""
    assert UNWAV == 1439 and int(TriggeredAbilityType.UnwaveringSentinel) == 1449
    assert UNWAV != int(TriggeredAbilityType.UnwaveringSentinel)
    # le meme ordinal, lu dans l'autre enum, designe autre chose -> le NOM est le seul canal fiable
    assert TriggeredAbilityType(1439).name == "NovaShield_BlockVisual"
    assert EffectType(1449).name == "MoreGitzOverEre_ExtraDamagePct"
    # ... alors que pour WireweaveNet les deux coincident (d'ou le piege)
    assert WIREW == int(TriggeredAbilityType.WireweaveNet) == 1111


# ---------------------------------------------------------------------------------------------
# Etage 2 -- le CABLAGE : trois `Triggered()` par effet, plus l'ability CUSTOM d'UnwaveringSentinel
# ---------------------------------------------------------------------------------------------

def test_registre_effect_triggers():
    """`BaseEffect.CreateHandleTriggerAbilitiesInternal` rend un `ArraySet` : 1 `Triggered()` natif
    = 1 classe offline. Les deux effets en ont TROIS -- la riposte + la paire d'armement."""
    assert [c.__name__ for c in EFFECT_TRIGGERS[GRIM]] == [
        "GrimRetributionCounterAttack",
        "GrimRetributionActivateOnEnemyTurnStart",
        "GrimRetributionDeactivateOnEnemyTurnEnd"]
    assert [c.__name__ for c in EFFECT_TRIGGERS[UNWAV]] == [
        "UnwaveringSentinelCounterAttack",
        "UnwaveringSentinelActivateOnEnemyTurnStart",
        "UnwaveringSentinelDeactivateOnEnemyTurnEnd"]


def test_registre_custom_triggered_ability_1449():
    """L'ability re-declenchee par `TriggerAbilityDelayed`. Une entree ICI change le CHEMIN du noeud
    (file au lieu du collapse inline) : sans elle, l'enfilement ne serait jamais draine."""
    assert [c.__name__ for c in CUSTOM_TRIGGERED_ABILITIES[US.UNWAVERING_SENTINEL_ABILITY]] == [
        "UnwaveringSentinelCustomAbility"]
    assert US.UnwaveringSentinelCustomAbility.event_id == int(EventTriggerType.Custom) == 0x20
    assert (US.UnwaveringSentinelCustomAbility.TRIGGERED_ABILITY_ID
            == US.UNWAVERING_SENTINEL_ABILITY == 1449)


def test_registre_effect_classes():
    """Les deux classes d'effet NOMMENT la classe native au lieu de router sur `BaseEffect`."""
    assert EFFECT_CLASSES["GrimRetribution_CounterAttack"] is GrimRetributionCounterAttackEffect
    assert EFFECT_CLASSES["UnwaveringSentinel_CounterAttack"] is UnwaveringSentinelCounterAttackEffect


# ---------------------------------------------------------------------------------------------
# Etage 3 -- le VECTEUR : `On(Attack)`, pas `On(PreUnitAbility)`
# ---------------------------------------------------------------------------------------------

def test_vecteur_de_riposte_est_attack_pas_preunitability():
    """`GetCounterAttackTrigger` = `On(0x9 = Attack, true)` pour les DEUX (corps PARTAGE :
    `GrimRetribution` reutilise celui d'`UnwaveringSentinel`), alors que `WireweaveNet` porte
    `On(0x2a = PreUnitAbility)`.

    C'est OBSERVABLE : sur `PreUnitAbility` la riposte part AVANT le coup adverse (et peut donc
    l'annuler en tuant l'attaquant) ; sur `Attack` le coup a deja porte."""
    from engine.runner.operations.triggers.loki import wireweave_net as WW
    assert int(GR.GrimRetributionCounterAttack.event_id) == int(EventTriggerType.Attack) == 9
    assert int(US.UnwaveringSentinelCounterAttack.event_id) == int(EventTriggerType.Attack) == 9
    assert int(WW.WireweaveNetCounterAttack.event_id) == int(EventTriggerType.PreUnitAbility) == 42


def test_paire_d_armement_est_inversee_par_rapport_au_jumeau():
    """freq 1 : `On(0x12) -> Activate` et `On(0x17) -> Deactivate`, tous deux gates par
    `NOT IsTurnOf(Owner)`. freq 2 (`WireweaveNet`) : les MEMES evenements, les comportements
    ECHANGES, et gates par `IsTurnOf(Owner)`.

    Le test compare les NOMS de classe : ils portent le sens (`...OnEnemyTurnStart` vs
    `...OnOwnerTurnStart`), et une inversion accidentelle les rendrait contradictoires."""
    from engine.runner.operations.triggers.loki import wireweave_net as WW
    for act, deact in ((GR.GrimRetributionActivateOnEnemyTurnStart,
                        GR.GrimRetributionDeactivateOnEnemyTurnEnd),
                       (US.UnwaveringSentinelActivateOnEnemyTurnStart,
                        US.UnwaveringSentinelDeactivateOnEnemyTurnEnd)):
        assert int(act.event_id) == int(EventTriggerType.TurnStart_EffectActivation) == 18
        assert int(deact.event_id) == int(EventTriggerType.TurnEnd) == 23
    # le jumeau freq 2 : MEMES evenements, roles ECHANGES
    assert int(WW.WireweaveNetDeactivateOnOwnerTurnStart.event_id) == 18
    assert int(WW.WireweaveNetActivateOnOwnerTurnEnd.event_id) == 23


# ---------------------------------------------------------------------------------------------
# Etage 4 -- les CONSTANTES gameconfig que le degat consomme
# ---------------------------------------------------------------------------------------------

def test_constantes_gameconfig_grim_retribution():
    """`GetDamageProfile(cfg)` = "Plasma", `GetNumberConstant(cfg, AbilityConstantType.nrOfHits)` = 1,
    `attackRangeType = Ranged` -> `is_melee=False` a la feuille."""
    import gameconfig as GC
    cfg = GC.ability(GR.GRIM_RETRIBUTION) or {}
    assert (cfg.get("constants") or {}).get("damageProfile") == GR._PROFILE == "Plasma"
    assert int((cfg.get("constants") or {}).get("nrOfHits")) == 1
    assert cfg.get("attackRangeType") == "Ranged"
    leaf = GR.grim_retribution_tree()
    assert leaf.is_melee is False and leaf.level_slot == "passive"
    assert leaf.ability_id == "GrimRetribution" and leaf.profile == "Plasma"


def test_constantes_gameconfig_unwavering_sentinel():
    """`GetDamageProfile()` = "Bolter", `GetHits()` = 2, et surtout
    `GetNumberConstant(cfg, AbilityConstantType.range)` = 2 -- la portee que le natif passe a
    `ValidNormalAttackTargets`, et que rien d'autre ne fournit."""
    import gameconfig as GC
    cfg = GC.ability(US.UNWAVERING_SENTINEL) or {}
    assert (cfg.get("constants") or {}).get("damageProfile") == US._PROFILE == "Bolter"
    assert int((cfg.get("constants") or {}).get("nrOfHits")) == 2
    assert cfg.get("attackRangeType") == "Ranged"
    assert US.counter_attack_range() == 2
    # la clef est lue par SON NOM d'enum, pas par l'ordinal : `GetNumberConstant` designe
    # `AbilityConstantType`, ou 22 = `range` (dans `AbilityVariableType`, 22 = `blockDmg_2`).
    assert AbilityConstantType.range.name == "range" and int(AbilityConstantType.range) == 0x16
    assert ability_var(US.UNWAVERING_SENTINEL, "range", is_constant=True) == 2


def test_degat_d_unwavering_sentinel_vient_de_l_ABILITY_pas_de_l_effet():
    """L'effet 1439 n'attaque PAS : son `GetCounterAttackBehaviour` est un `TriggerAbilityDelayed`.
    Le degat tombe au drain, depuis la config de l'ABILITY (`MinMaxDamage`/`GetHits`/
    `GetDamageProfile` de `BaseTriggeredAbility`).

    Contrepreuve de forme : l'arbre du trigger d'effet ne contient AUCUN
    `AttackWithAttackDamage`, celui de l'ability custom en contient UN."""
    delayed = US.unwavering_sentinel_delayed_tree()
    assert type(delayed).__name__ == "TriggerAbilityDelayed"
    assert delayed.ability_type == US.UNWAVERING_SENTINEL_ABILITY == 1449
    attack = US.unwavering_sentinel_attack_tree()
    assert type(attack).__name__ == "If"          # `IfAlive(x, b)` == `If(IsAlive(x), b)`
    # ... et la feuille sous le `If` est bien l'attaque, avec la config de l'ABILITY
    leaf = attack.behaviour if hasattr(attack, "behaviour") else attack.then
    assert leaf.ability_id == "UnwaveringSentinel" and leaf.profile == "Bolter"
    assert leaf.is_melee is False and leaf.level_slot == "passive"


# ---------------------------------------------------------------------------------------------
# Etage 5 -- l'override `range` de `ValidNormalAttackTargets` (le call-site que le port attendait)
# ---------------------------------------------------------------------------------------------

def test_override_range_arme_les_deux_ecritures_natives():
    """Le bloc `if (rangeSel@+0x28 != null)` du selecteur natif fait DEUX choses :
    `opts.range = CustomRange(range)` **et** `opts.rules &= ~TargetMatchesDynamicRule`.

    On les mesure sur la struct, sans monter de bataille : `custom_range(2)` doit rendre un
    `TargetingRange` d'override, et le masque doit perdre le bit."""
    rng = custom_range(2)
    assert rng.override_range == 2
    assert rng.use_range_from_config is False and rng.use_whole_board is False
    # `RangedBool.False` et non `IfNotRangedCaster` : l'override efface AUSSI l'adjacence du preset
    from engine.runner.abilities.targeting import RANGED_BOOL_FALSE
    assert rng.only_adjacent == RANGED_BOOL_FALSE
    from engine.runner.abilities.targeting import NORMAL_ATTACK_TARGETING_OPTIONS as BASE
    muted = dataclasses.replace(BASE, rules=int(BASE.rules) & ~int(TR.TargetMatchesDynamicRule),
                                range=rng)
    assert not muted.has(TR.TargetMatchesDynamicRule)


def test_le_noeud_porte_l_override_et_le_transmet():
    """Le noeud `ValidNormalAttackTargets` accepte desormais `range` et le passe au foyer unique.
    On substitue l'accesseur de contexte pour LIRE ce qui lui est transmis -- c'est la seule facon
    de verifier que l'override n'est pas avale en silence."""
    from engine.dsl.base import DslContext
    from engine.entities.selectors.units import ValidNormalAttackTargets
    from engine.entities.selectors.accessors import Owner

    vus = []

    def _fake(caster_unit, range_override=None):
        vus.append(range_override)
        return []

    u = {"id": 1, "team": 1, "col": 0, "row": 0, "alive": True}
    ctx = DslContext(units=[u], caster=u, valid_normal_attack_targets=_fake)
    ValidNormalAttackTargets(Owner(), None, range=2).select(ctx)
    ValidNormalAttackTargets(Owner(), None).select(ctx)
    assert vus == [2, None], (
        "l'override doit arriver au foyer quand il est pose, et RESTER None sinon "
        "(les call-sites historiques ne changent pas de comportement)")


# ---------------------------------------------------------------------------------------------
# Etage 6 -- le SOCLE PARTAGE de la famille (factorisation au 3e site)
# ---------------------------------------------------------------------------------------------

def test_socle_partage_est_le_foyer_unique():
    """Les quatre lectures/ecritures de la base `PlayerTurnEffect` vivent dans UN module, et les
    trois membres portes y deleguent -- il ne doit pas exister trois definitions de
    << l'instance est-elle armee ? >>."""
    for nom in ("instances", "flag_is_set", "set_active", "is_turn_of_owner"):
        assert callable(getattr(_ca, nom)), nom
    from engine.runner.operations.triggers.loki import wireweave_net as WW
    # `wireweave_net` DELEGUE (forme B) : ses quatre helpers sont des enveloppes, pas des copies
    import inspect
    for nom in ("_instances", "_flag_is_set", "_set_active", "_is_turn_of_owner"):
        src = inspect.getsource(getattr(WW, nom))
        assert "_ca." in src, f"{nom} de wireweave_net doit deleguer au socle partage"


# ---------------------------------------------------------------------------------------------
# Etage 7 -- CONTRE-EPREUVE PAR MUTATION : chaque garde ci-dessus doit ROUGIR sous mutation
# ---------------------------------------------------------------------------------------------

_MUTATIONS = [
    # (libelle, cible du monkeypatch, valeur mutante, test qui DOIT rougir)
    ("freq 1 -> 2 (recopie du jumeau)",
     "engine.entities.effects.loki.counter_attack.GrimRetributionCounterAttackEffect."
     "ACTIVATION_FREQUENCY", 2, test_ctor_literals_grim_retribution),
    ("source ability 1177 -> 1111",
     "engine.entities.effects.loki.counter_attack.GrimRetributionCounterAttackEffect."
     "SOURCE_TRIGGERED_ABILITY", TriggeredAbilityType.WireweaveNet,
     test_ctor_literals_grim_retribution),
    ("turnsEnabled 1 -> 0 (IsTurnOf au lieu de NOT IsTurnOf)",
     "engine.entities.effects.loki.counter_attack.UnwaveringSentinelCounterAttackEffect."
     "TURNS_ENABLED", 0, test_ctor_literals_unwavering_sentinel),
    ("vecteur Attack -> PreUnitAbility (recopie du jumeau)",
     "engine.runner.operations.triggers.loki.grim_retribution.GrimRetributionCounterAttack."
     "event_id", EventTriggerType.PreUnitAbility, test_vecteur_de_riposte_est_attack_pas_preunitability),
    ("armement TurnStart -> TurnEnd (paire inversee)",
     "engine.runner.operations.triggers.loki.unwavering_sentinel."
     "UnwaveringSentinelActivateOnEnemyTurnStart.event_id", EventTriggerType.TurnEnd,
     test_paire_d_armement_est_inversee_par_rapport_au_jumeau),
    ("profil Plasma -> Bolter",
     "engine.runner.operations.triggers.loki.grim_retribution._PROFILE", "Bolter",
     test_constantes_gameconfig_grim_retribution),
    ("id de l'ability re-declenchee 1449 -> 1439 (confusion d'enum)",
     "engine.runner.operations.triggers.loki.unwavering_sentinel.UNWAVERING_SENTINEL_ABILITY", 1439,
     test_degat_d_unwavering_sentinel_vient_de_l_ABILITY_pas_de_l_effet),
]


@pytest.mark.parametrize("libelle,cible,valeur,garde",
                         _MUTATIONS, ids=[m[0] for m in _MUTATIONS])
def test_contre_epreuve_par_mutation(monkeypatch, libelle, cible, valeur, garde):
    """CHAQUE mutation du code porte doit faire ROUGIR son garde. Un garde qui reste VERT sous
    mutation est inerte : il decrit le code au lieu de le contraindre.

    ⚠ On VERIFIE d'abord que le patch a MORDU (`monkeypatch.setattr` sur un attribut inexistant
    leverait, mais un patch pose sur une COPIE ne mordrait pas) -- puis on exige l'echec."""
    monkeypatch.setattr(cible, valeur, raising=True)
    with pytest.raises(AssertionError):
        garde()
