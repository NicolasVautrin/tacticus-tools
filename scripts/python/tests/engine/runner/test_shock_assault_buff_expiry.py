"""case-366-r1 -- GARDE de `ShockAssault_Buff` (0x3e8 = 1000), le « +Damage for this attack » que le
PASSIF `ShockAssault` d'`ultraInceptorSgt` pose sur ses Inceptors (`ultraSmnInceptor`).

DEUX FACES, ET C'EST LA SECONDE QUI PORTE LE RISQUE.

 1. ATTRIBUTION. `decisionView.effects` n'expose NI le stat NI le montant d'un effet capte : sans la
    classe inscrite, la contribution d'un 1000 deja pose tombe dans le RESIDU OPAQUE
    (`CAPTURED_SOURCE`) de `seed_unit_stats`, attribuee a AUCUNE source -- donc **non retirable**
    (#118). Le stat COURANT reste juste dans les deux mondes (le residu compense) : un test qui
    mesure juste apres la pose est VERT declare ou non et ne prouve RIEN.

 2. DUREE. La pose est `AddStaticStatModifierEffect(..., turns = **NULL**)` -> cote timer l'effet est
    PERMANENT. Ce qui le borne est un TRIGGER :
    `IdunBattle.Entities.Effects.Loki.ShockAssaultBuffEffect$$CreateRemoveEffectTrigger`
    = `On(0xa = AttackDamageAttack, ownerNeedsToBeAlive: 1) & get_OwnerIsCaster`, greffe par
    `IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` en
    `Triggered(<ce trigger>, RemoveEffect(df@0x150))`. Sans ce trigger porte, le +extraDmg d'ATTACK
    colle **a vie** au summon la ou l'i2 dit « for this attack ».

Le predicat `OwnerIsCaster` est le SEUL discriminant : le MEME event `On(0xa)` porte la POSE
(`ShockAssaultAbility$$CreateTrigger`, owner = le BELLATOR) et le RETRAIT (owner = l'INCEPTOR).
Un port qui retirerait l'effet sur l'attaque de N'IMPORTE QUI le detruirait avant meme qu'il serve --
d'ou la contre-epreuve `..._survives_another_units_attack`.

CROSS-UNITE : porteur (le summon) != source (le Bellator). Le niveau qui indexe `extraDmg` est celui
du PASSIF du POSEUR -- resolu par `engine/entities/effects_state.py::baked_ability_state` depuis
`captured["source"]` (mirror du bake natif `EffectComponent+0x18`). Garde dediee ci-dessous : les
deux unites portent des niveaux DIFFERENTS, ce que le regime nominal (`buildNormalizedBC` met tout a
50) ne saurait pas distinguer.

100 % offline (aucun runner) : le cycle de vie est deterministe. Le FAIT confronte au natif (« le
natif pose bien ce montant-la, et le buff redescend quand l'Inceptor frappe ») l'est par
`probe_366r1_shock_assault_buff_live.py`.
"""
from __future__ import annotations

import pytest

from engine.entities.effects.factory import EffectFactory
from engine.entities.effects_state import EffectsState
from engine.entities.unit_context import UnitContext
from engine.entities.effects.magnitude import ability_var
from engine.entities.stats import StatType, CAPTURED_SOURCE
from engine.runner.components import OwnerComponent, StatsComponent, UnitComponent
from engine.runner.operations.turnflow import EndTurnOperation
from engine.runner.operations.triggers.dispatch.attack import attack_damage_attack_triggers
from engine.runner.state import State

STAT_IDS = {"attack": 0, "movement": 1, "health": 5, "fixedArmor": 16, "critChance": 9}
BASE = {"attack": 900, "movement": 4, "health": 6000, "fixedArmor": 200, "critChance": 10}

SHOCK_ASSAULT_BUFF = 1000                 # 0x3e8
BELLATOR = "ultraInceptorSgt"             # HERO au pool -- porteur du PASSIF ShockAssault (1002)
INCEPTOR = "ultraSmnInceptor"             # le SUMMON buffe (`GetStringConstant(config, 0 = unitId)`)

CARRIER = 71                              # l'Inceptor : PORTEUR de l'effet
POSER = 12                                # le Bellator : SOURCE de l'effet
ENEMY = 99                                # une cible quelconque pour le vecteur On(0xa)

LEVEL = 50                                # niveau d'ability normalise par `buildNormalizedBC`
MULT = 180                                # AbilityVariablesMultiplierPercentage typique d'un roster rank-up


def _amount(level=LEVEL, mult=MULT):
    """`Get(ConfigVar(8 = extraDmg, <AbilityState du PASSIF du poseur>))` -- `extraDmg` est la SEULE
    variable de `ShockAssault` et elle est dans son `variablesAffectedByRarityBonus`."""
    v = ability_var("ShockAssault", "extraDmg", level, multiplier_pct=mult)
    assert v, "ShockAssault.extraDmg non resoluble en gameconfig -> scenario vide"
    return int(v)


def _cap(remaining=0, source=POSER, stat_mod=None):
    """`turns = NULL` au decompile -> `remaining` capte 0 -> materialise PERMANENT par `EffectFactory`.

    `stat_mod` = le `StatModifierComponent` de l'entite-effet tel que le capteur le publie. Il est
    ABSENT par defaut ici : les montages ci-dessous exercent alors le REPLI gameconfig. Le canal
    natif, lui, est exerce par `test_shock_assault_buff_prefers_the_captured_native_amount` et par
    la garde LIVE."""
    c = {"name": "ShockAssault_Buff", "effectType": SHOCK_ASSAULT_BUFF, "level": 1,
         "remaining": remaining, "source": source}
    if stat_mod is not None:
        c["statMod"] = stat_mod
    return c


def _add_unit(st, uid, visual, *, team, stats=None, level=LEVEL, mult=MULT, effs=()):
    su = {"entityId": uid, "visualId": visual, "stats": dict(stats or BASE), "statDelta": {},
          "unitConfig": {"activeAbilityLevel": level, "passiveAbilityLevel": level,
                         "abilityVariablesMultiplier": mult}}
    ctx = UnitContext.from_snapshot(su, None, STAT_IDS, list(effs))
    ent = st.add_entity(uid)
    ent.add_component(StatsComponent(ctx=ctx))
    ent.add_component(OwnerComponent(player=3 if team == 1 else 4, team=team))
    ent.add_component(UnitComponent(visual_id=visual, alive=True))
    return ctx


def _scene(*, poser_level=LEVEL, carrier_level=LEVEL, poser_mult=MULT, carrier_mult=MULT,
           remaining=0):
    """MONTAGE NOMME -- voie SEEDE de `snapshot._load_stats_and_effects` : le buff est DEJA CUIT dans
    le `Current` capte de l'Inceptor (`stats`) et son montant est dans `statDelta`, exactement comme
    un `combatSnapshot` pris apres la pose. C'est la seule forme ou le bug de duree existe.

    Renvoie `(state, ctx_inceptor, montant)`. Le montant est celui du POSEUR (Bellator)."""
    amt = _amount(poser_level, poser_mult)
    st = State()
    _add_unit(st, POSER, BELLATOR, team=1, level=poser_level, mult=poser_mult)
    _add_unit(st, ENEMY, "tyranTyrantGuard", team=2)
    cap = _cap(remaining=remaining)
    stats = dict(BASE)
    stats["attack"] = BASE["attack"] + amt
    su = {"entityId": CARRIER, "visualId": INCEPTOR, "stats": stats,
          "statDelta": {"attack": amt},
          "unitConfig": {"activeAbilityLevel": carrier_level,
                         "passiveAbilityLevel": carrier_level,
                         "abilityVariablesMultiplier": carrier_mult}}
    effs = EffectFactory.create_many([cap], poser_mult, poser_level, poser_level)
    ctx = UnitContext.from_snapshot(su, None, STAT_IDS, effs)
    ent = st.add_entity(CARRIER)
    ent.add_component(StatsComponent(ctx=ctx))
    ent.add_component(OwnerComponent(player=3, team=1))
    ent.add_component(UnitComponent(visual_id=INCEPTOR, alive=True))
    # `ability_state_by_unit` = le triple PAR ENTITE, consulte par la SOURCE de chaque effet.
    abstate = {POSER: (poser_mult, poser_level, poser_level),
               CARRIER: (carrier_mult, carrier_level, carrier_level)}
    st.effects = EffectsState.seed({CARRIER: [cap]}, {CARRIER: carrier_mult},
                                   {CARRIER: carrier_level}, abstate)
    st.current_player_id = 3
    return st, ctx, amt


def _per_source(ctx, stat):
    return dict(ctx.stats.components[int(stat)].modification.per_source)


def _statmod_keys(ctx, stat, effect_type):
    return [k for k in _per_source(ctx, stat)
            if isinstance(k, tuple) and k[:2] == ("statmod", effect_type)]


# --------------------------------------------------------------------------------------------------
# Face 1 -- ATTRIBUTION (condition NECESSAIRE du revert)
# --------------------------------------------------------------------------------------------------

def test_shock_assault_buff_seed_attribution_is_not_opaque():
    """Au seed, la contribution vit sous une cle d'effet, PAS dans le residu opaque. Si elle
    retombait dans `CAPTURED_SOURCE`, le test de retrait ci-dessous deviendrait silencieusement
    inoperant (rien a retirer, donc rien qui rougit).

    Validation NON CIRCULAIRE : le montant vient de gameconfig
    (`ShockAssault.variables.extraDmg`), le `statDelta` vient de la capture -- residu 0 == les deux
    concordent."""
    st, ctx, amt = _scene()
    assert int(ctx.stat(StatType.ATTACK)) == BASE["attack"] + amt, \
        "le seed ne reproduit pas le Current capte"
    keys = _statmod_keys(ctx, StatType.ATTACK, SHOCK_ASSAULT_BUFF)
    assert keys, ("1000 SEEDE non attribue (per_source=%s) -- sa contribution est dans le residu "
                  "opaque, donc NON retirable" % (_per_source(ctx, StatType.ATTACK),))
    assert sum(_per_source(ctx, StatType.ATTACK)[k] for k in keys) == amt
    assert int(_per_source(ctx, StatType.ATTACK).get(CAPTURED_SOURCE, 0)) == 0, \
        "residu opaque non nul : %s" % (_per_source(ctx, StatType.ATTACK),)


def test_shock_assault_buff_prefers_the_captured_native_amount():
    """LE CANAL PRINCIPAL, et c'est CELUI QUI COMPTE EN LIVE.
    `StaticStatModifierEffect$$GetStatModificationAmount` retourne litteralement
    `StatModifierComponent+0x14`, et la capture publie ce composant sous ses NOMS NATIFS
    (`{StatType, Amount, ApplyCounter, IsDynamic, IsHidden}`). Le port doit LIRE ce champ, pas le
    re-deriver.

    Pourquoi ce n'est pas un detail : la feuille de pose passe `source = null`, donc
    `EffectComponent.SourceUnit` -- le canal de `baked_ability_state` -- designe le **PORTEUR** (le
    summon), pas le Bellator. MESURE LIVE 2026-08-01 : natif `Amount = 499`, re-derivation par le
    porteur `extraDmg[1] = 5`. Le montage ci-dessous reproduit ce cas : niveau/mult du porteur
    (donc de la source captee), et un `statMod` natif qui ne peut PAS en decouler."""
    native = 499
    st, ctx, _ = _scene(poser_level=1, poser_mult=100, carrier_level=1, carrier_mult=100)
    cap = _cap(stat_mod={"StatType": 0, "Amount": native, "ApplyCounter": 1,
                         "IsDynamic": 0, "IsHidden": 1})
    eff = EffectFactory.create(cap, 100, 1, 1)
    assert _amount(1, 100) != native, "montage non discriminant : le repli donnerait deja %d" % native
    assert eff.get_stat_modification_amount() == native, (
        "magnitude RE-DERIVEE (%s) au lieu du `statMod.Amount` natif (%d) -- c'est exactement "
        "l'ecart mesure live (5 au lieu de 499)"
        % (eff.get_stat_modification_amount(), native))
    assert eff.captured_stat_mod_amount() == native


def test_shock_assault_buff_fallback_follows_the_POSER_not_the_carrier():
    """LE REPLI, quand la capture ne publie pas `statMod` (pose OFFLINE, capture antérieure) :
    `ConfigVar(8 = extraDmg)` indexe par l'`AbilityState` que `baked_ability_state` resout depuis
    `captured["source"]`. Le regime NOMINAL est DEGENERE (`buildNormalizedBC` met tous les niveaux a
    50) : on DISSOCIE -- source L50/x180, porteur L20/x100 -- pour que le test ait un observable.

    ⚠ En LIVE ce repli n'est PAS exact (la source captee EST le porteur) : c'est pour cela que
    `statMod` prime. Ce test garde le comportement du repli, pas une propriete du natif."""
    st, ctx, amt = _scene(poser_level=50, poser_mult=180, carrier_level=20, carrier_mult=100)
    carrier_amount = _amount(20, 100)
    assert amt != carrier_amount, \
        "montage non discriminant : les deux lectures donnent le meme montant (%d)" % (amt,)
    eff = st.effects.by_unit[CARRIER][0]
    assert eff.stat_mod is None, "ce montage doit exercer le REPLI (pas de statMod capte)"
    assert eff.get_stat_modification_amount() == amt, (
        "magnitude lue sur le PORTEUR (%s) au lieu de la SOURCE (%d) -- `baked_ability_state` "
        "ne resout pas `captured['source']`" % (eff.get_stat_modification_amount(), amt))
    assert eff.ability_level == 50 and eff.ability_variables_multiplier == 180


def test_shock_assault_buff_fallback_reads_the_PASSIVE_slot():
    """`ShockAssault` est un PASSIF (`TriggeredAbilityType` 0x3ea = 1002) : le natif passe
    l'`AbilityState` que `UnitFactory$$Build` fabrique pour les passives
    (`config+0xbc PassiveAbilityLevel`). Lire l'ACTIF serait un faux -- invisible en runner
    normalise, mesurable en dissociant les deux slots (le bras LIVE
    `--unit-stat <bellator>:PassiveAbilityLevel=20` le fait, actif reste 50 : natif 47, pas 499)."""
    st, ctx, amt = _scene()
    eff = st.effects.by_unit[CARRIER][0]
    eff.active_ability_level = 5                        # actif DISSOCIE du passif
    assert eff.get_stat_modification_amount() == amt, \
        "la magnitude suit l'ACTIF (%s) alors que ShockAssault est un PASSIF" \
        % (eff.get_stat_modification_amount(),)


# --------------------------------------------------------------------------------------------------
# Face 2 -- DUREE : le retrait est un TRIGGER (`On(0xa) & OwnerIsCaster`), pas un timer
# --------------------------------------------------------------------------------------------------

def test_shock_assault_buff_leaves_when_its_carrier_finishes_an_attack():
    """LE CRITERE DU CAS. `On(0xa = AttackDamageAttack)` avec le PORTEUR en attaquant ->
    `RemoveEffect(<cette instance>)`, et la `ValueModification` d'ATTACK sort dans le meme passage
    (`AStatModifierEffect$$RevertModification`, `ChangeStat` part 6).

    Sans le trigger inscrit, `has_effect` reste True ET le buff reste : l'Inceptor frapperait
    +extraDmg a CHAQUE attaque, pour toujours."""
    st, ctx, amt = _scene()
    assert st.effects.has_effect(CARRIER, effect_type=SHOCK_ASSAULT_BUFF)

    attack_damage_attack_triggers(st, CARRIER, ENEMY, ranged=False, profile="Bolter")

    assert not st.effects.has_effect(CARRIER, effect_type=SHOCK_ASSAULT_BUFF), \
        "1000 non retire a la cloture de l'attaque de son porteur (On(0xa) & OwnerIsCaster)"
    after = int(ctx.stat(StatType.ATTACK))
    assert after == BASE["attack"], (
        "effet RETIRE mais buff CONSERVE : ATTACK=%d au lieu de %d (+%d colle a vie)"
        % (after, BASE["attack"], after - BASE["attack"]))


def test_shock_assault_buff_survives_another_units_attack():
    """CONTRE-EPREUVE du predicat `get_OwnerIsCaster`. Le MEME event `On(0xa)` porte la POSE
    (declenchee par l'attaque du BELLATOR) : si le port retirait le buff sur l'attaque de n'importe
    qui, l'Inceptor perdrait son bonus avant meme de frapper -- exactement l'inverse du bug de
    duree, et tout aussi silencieux."""
    st, ctx, amt = _scene()

    attack_damage_attack_triggers(st, POSER, ENEMY, ranged=False, profile="Bolter")

    assert st.effects.has_effect(CARRIER, effect_type=SHOCK_ASSAULT_BUFF), \
        "1000 retire par l'attaque d'une AUTRE unite -- le gate OwnerIsCaster ne mord pas"
    assert int(ctx.stat(StatType.ATTACK)) == BASE["attack"] + amt


def test_shock_assault_buff_survives_the_expiry_tick():
    """CONTRE-EPREUVE de la permanence. `turns = NULL` au decompile -> `remaining <= 0` materialise
    PERMANENT cote port -> le gate `!Removed && HasTurns` d'
    `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` ne le touche pas. Un revert
    declenche « au tick » ferait fondre le buff en silence, alors que le natif attend l'attaque."""
    st, ctx, amt = _scene()
    assert st.effects.by_unit[CARRIER][0].remaining_turns is None, \
        "1000 doit etre materialise PERMANENT (turns = NULL au decompile)"
    before = int(ctx.stat(StatType.ATTACK))
    for _ in range(5):
        EndTurnOperation.execute(st, advance=False)
    assert st.effects.has_effect(CARRIER, effect_type=SHOCK_ASSAULT_BUFF), \
        "1000 PERMANENT retire par le tick de duree"
    assert int(ctx.stat(StatType.ATTACK)) == before, \
        "buff erode par le tick : %d -> %d" % (before, int(ctx.stat(StatType.ATTACK)))


def test_shock_assault_buff_removal_is_idempotent():
    """UNE fois : les `On(0xa)` suivants sont des no-op (l'instance est consommee, la cle de source
    poppee). Un double revert ferait descendre l'ATTACK SOUS sa base."""
    st, ctx, amt = _scene()
    for _ in range(3):
        attack_damage_attack_triggers(st, CARRIER, ENEMY, ranged=False, profile="Bolter")
    assert int(ctx.stat(StatType.ATTACK)) == BASE["attack"], \
        "double revert : ATTACK=%d != base %d" % (int(ctx.stat(StatType.ATTACK)), BASE["attack"])
    per_source = _per_source(ctx, StatType.ATTACK)
    assert all(v >= 0 for v in per_source.values()), "per_source negatif : %s" % (per_source,)


# --------------------------------------------------------------------------------------------------
# Cliquet de fidelite : ce que le registre rend == ce que la feuille native passe
# --------------------------------------------------------------------------------------------------

def test_shock_assault_registry_mirrors_the_decompiled_leaf():
    """`ShockAssaultAbility$$CreateBehaviour` passe a
    `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect` :
    `(targets = GetAffectedUnits(Owner), effectType = 0x3e8, statType = **0 ATTACK**,
      amount = Get(ConfigVar(8 = extraDmg)), turns = **NULL**, isHidden = true)`.

    Un statType faux ne rougit nulle part ailleurs (le `Current` reste juste, le residu compense)
    mais ferait reverter la MAUVAISE stat au retrait."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    assert "ShockAssault_Buff" in EFFECT_CLASSES, "ShockAssault_Buff absent du registre"
    eff = EffectFactory.create(_cap(), MULT, LEVEL, LEVEL)
    assert eff.get_stat_modification_stat() == 0, \
        "statType %s != 0 ATTACK (decompile)" % (eff.get_stat_modification_stat(),)
    assert eff.get_stat_modification_amount() == _amount(), \
        "montant %s != ShockAssault.extraDmg[L%d] x %d%% = %d" \
        % (eff.get_stat_modification_amount(), LEVEL, MULT, _amount())
    assert eff.reverted_stats() == [0], \
        "reverted_stats %s -- le discriminant du revert par-source" % (eff.reverted_stats(),)
    assert eff.remaining_turns is None, "turns = NULL au decompile -> PERMANENT cote timer"


def test_shock_assault_buff_trigger_is_registered_on_the_right_event():
    """Le vecteur est `On(0xa = AttackDamageAttack)`, PAS `On(9 = Attack)` : le natif ecoute le 2e
    des deux events de cloture de `FinishAttackOperation$$Execute`, celui qui est gate par
    `currentAttack@+0x2c != 0` (« cette attaque a comporte une ATTAQUE-A-DEGATS »)."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    entries = EFFECT_TRIGGERS.get(SHOCK_ASSAULT_BUFF) or []
    assert entries, "aucun trigger inscrit pour 1000 -- le buff serait PERMANENT"
    assert [e.event_id for e in entries] == [int(EventTriggerType.AttackDamageAttack)], \
        "events inscrits %s != [0xa]" % ([e.event_id for e in entries],)


if __name__ == "__main__":                                   # execution directe = mesure lisible
    raise SystemExit(pytest.main([__file__, "-q"]))
