"""#371 (gisement G1 de case-366) -- GARDE des instances GENERIQUES `StaticStatModifierEffect`
inscrites au registre : leur stat-mod SEEDE doit SORTIR quand l'effet part, et RESTER quand il ne
part pas.

LE CRITERE EST LA DUREE, PAS LA VALEUR. `decisionView.effects` n'expose NI le stat NI le montant
d'un effet capte : un stat-mod deja actif au chargement d'un `State` arrive donc sans stat-modification
declaree et sa contribution tombe dans le RESIDU OPAQUE (`CAPTURED_SOURCE`) de `seed_unit_stats` --
attribuee a AUCUNE source, donc **non retirable**. Le stat COURANT reste juste dans les deux mondes
(le residu compense) : un test qui mesure la stat juste apres la pose passe au vert declare ou non et
**ne prouve RIEN**. C'est seulement APRES le retrait que les deux mondes divergent -- d'ou le montage
`_seeded` ci-dessous, qui FAIT EXPIRER.

RE (decompile, build `rnca9r7q6c`) -- la feuille commune est
`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`
(`(targets, effectType, statType, amount, turns, isHidden)`) et sa variante `...ToOwner`
(`(effectType, statType, amount, turns, isHidden)`) :

  | effet                              | poseur                                              | stat        | montant                    | turns              |
  |------------------------------------|-----------------------------------------------------|-------------|----------------------------|--------------------|
  | 1171 `SereneUnifierStormOfFire`    | `SereneUnifierAbility$$CreateBehaviour` (k = 0)      | 0 ATTACK    | `ConfigVar(8 = extraDmg)`  | `TurnsFromRounds(1)` |
  | 1251 `UnbreakableDuty_Health`      | `UnbreakableDutyAbility$$ExecuteBehaviour`          | 5 HEALTH    | `ConfigVar(0x1e = extraHp)`| **NULL**           |
  | 1256 `UnbreakableDuty_Damage`      | idem                                                 | 0 ATTACK    | `ConfigVar(8 = extraDmg)`  | **NULL**           |

=> UN SEUL des trois porte un vrai timer. Les deux autres sont PERMANENTS : leur inscription ne ferme
pas un bug de duree mais l'ATTRIBUTION (residu opaque -> cle par-source), et elle introduit un risque
SYMETRIQUE -- qu'un revert « au tick » erode un buff permanent. Les deux faces sont gardees ici.

100 % offline (aucun runner) : le cycle de vie est deterministe. Le FAIT confronte au natif (« le buff
redescend quand l'effet part ») l'est par la garde live jumelle
`test_serene_unifier_storm_of_fire_live.py`.
"""
from __future__ import annotations

import pytest

from engine.entities import EffectFactory, EffectsState, UnitContext
from engine.entities.effects.magnitude import ability_var
from engine.entities.stats import StatType, CAPTURED_SOURCE
from engine.runner.components import OwnerComponent, StatsComponent, UnitComponent
from engine.runner.operations.turnflow import EndTurnOperation
from engine.runner.state import State

STAT_IDS = {"attack": 0, "movement": 1, "health": 5, "fixedArmor": 16, "critChance": 9}
BASE = {"attack": 1200, "movement": 4, "health": 9000, "fixedArmor": 400, "critChance": 15}
UID = 71

STORM_OF_FIRE = 1171          # 0x493
UD_HEALTH = 1251              # 0x4e3
UD_DAMAGE = 1256              # 0x4e8

AUN_SHI = "tauAunShi"         # HERO au pool -- porteur du passif SereneUnifier (1145)
ANCIENT = "templAncient"      # HERO au pool -- porteur de l'active UnbreakableDuty
LEVEL = 50                    # niveau d'ability normalise par `buildNormalizedBC`


def _seeded(captured, delta, *, visual, level=LEVEL, mult=100):
    """MONTAGE NOMME ET REUTILISABLE -- `State` minimal reproduisant la voie SEEDE de
    `snapshot._load_stats_and_effects` : chaque stat-mod est DEJA CUIT dans le `Current` capte
    (`stats`) et son montant est dans `statDelta`, exactement comme un `combatSnapshot` pris APRES la
    pose. C'est la seule forme ou le bug de duree existe -- un effet POSE offline renseigne, lui, sa
    cle de source a la pose.

    Renvoie `(state, ctx)`. Faire expirer = `EndTurnOperation.execute(state, advance=False)`."""
    stats = {k: BASE[k] + int(delta.get(k, 0)) for k in BASE}
    su = {"entityId": UID, "visualId": visual, "stats": stats, "statDelta": dict(delta),
          "unitConfig": {"activeAbilityLevel": level, "passiveAbilityLevel": level,
                         "abilityVariablesMultiplier": mult}}
    effs = EffectFactory.create_many(captured, mult, level, level)
    ctx = UnitContext.from_snapshot(su, None, STAT_IDS, effs)
    st = State()
    ent = st.add_entity(UID)
    ent.add_component(StatsComponent(ctx=ctx))
    ent.add_component(OwnerComponent(player=3, team=1))
    ent.add_component(UnitComponent(visual_id=visual, alive=True))
    st.effects = EffectsState.seed({UID: captured}, {UID: mult})
    st.current_player_id = 3
    return st, ctx


def _cap(name, effect_type, remaining):
    return {"name": name, "effectType": effect_type, "level": 1,
            "remaining": remaining, "source": UID}


def _per_source(ctx, stat):
    return dict(ctx.stats.components[int(stat)].modification.per_source)


def _statmod_keys(ctx, stat, effect_type):
    return [k for k in _per_source(ctx, stat)
            if isinstance(k, tuple) and k[:2] == ("statmod", effect_type)]


def _storm_state(remaining=1):
    """Aun'Shi buffe par SA PROPRE phase `k = 0` (source == porteur) -> magnitude EXACTE offline."""
    amt = ability_var("SereneUnifier", "extraDmg", LEVEL)
    assert amt, "SereneUnifier.extraDmg non resoluble en gameconfig -> scenario vide"
    st, ctx = _seeded([_cap("SereneUnifierStormOfFire", STORM_OF_FIRE, remaining)],
                      {"attack": int(amt)}, visual=AUN_SHI)
    return st, ctx, int(amt)


# --------------------------------------------------------------------------------------------------
# 1171 -- LE cas a TIMER : c'est LUI qui porte le bug de duree du lot.
# --------------------------------------------------------------------------------------------------

def test_storm_of_fire_seed_attribution_is_not_opaque():
    """CONDITION NECESSAIRE du revert : au seed la contribution vit sous une cle d'effet, pas dans le
    residu opaque. Si elle retombait dans `CAPTURED_SOURCE`, le test d'expiration ci-dessous
    deviendrait silencieusement inoperant (rien a retirer, donc rien qui rougit).

    C'est aussi une validation NON CIRCULAIRE : le montant vient de gameconfig
    (`SereneUnifier.variables.extraDmg`), le delta vient du natif -- residu 0 == les deux concordent."""
    st, ctx, amt = _storm_state(remaining=1)
    assert int(ctx.stat(StatType.ATTACK)) == BASE["attack"] + amt, \
        "le seed ne reproduit pas le Current capte"
    keys = _statmod_keys(ctx, StatType.ATTACK, STORM_OF_FIRE)
    assert keys, ("1171 SEEDE non attribue (per_source=%s) -- sa contribution est dans le residu "
                  "opaque, donc NON retirable" % (_per_source(ctx, StatType.ATTACK),))
    assert sum(_per_source(ctx, StatType.ATTACK)[k] for k in keys) == amt
    assert int(_per_source(ctx, StatType.ATTACK).get(CAPTURED_SOURCE, 0)) == 0, \
        "residu opaque non nul : %s" % (_per_source(ctx, StatType.ATTACK),)


def test_storm_of_fire_seeded_statmod_leaves_with_its_effect_at_expiry():
    """LE CRITERE DU LOT, sur le SEUL membre inscrit qui porte un timer : a l'echeance de
    `TurnsFromRounds(1)`, l'effet ET son buff partent dans le MEME passage.

    Sans l'inscription de `SereneUnifierStormOfFire` au registre, `has_effect` devient False (retrait
    a echeance effectif) alors que `GetStat(ATTACK)` garde le +extraDmg : effet absent, buff present.
    Le natif, lui, sort la `ValueModification` dans le meme passage
    (`IdunBattle.Operations.EndTurnOperation$$RefreshEffects` -> `RefreshEffect` branche
    `DeactivateEffect` -> virtuel `RevertInternal` = `AStatModifierEffect$$RevertModification`)."""
    st, ctx, amt = _storm_state(remaining=1)
    assert st.effects.has_effect(UID, effect_type=STORM_OF_FIRE)

    EndTurnOperation.execute(st, advance=False)

    assert not st.effects.has_effect(UID, effect_type=STORM_OF_FIRE), \
        "l'effet a timer n'a pas ete retire a l'echeance"
    after = int(ctx.stat(StatType.ATTACK))
    assert after == BASE["attack"], (
        "effet RETIRE mais buff CONSERVE : ATTACK=%d au lieu de %d (+%d colle a vie). "
        "L'effet a disparu de has_effect, sa ValueModification non."
        % (after, BASE["attack"], after - BASE["attack"]))


def test_storm_of_fire_reverts_exactly_once_and_on_the_right_turn():
    """UNE fois, au BON tour : le revert tombe au tick ou `remaining` atteint 0 -- pas avant (le buff
    tient tant que l'effet dure), pas deux fois (les ticks suivants sont des no-op)."""
    st, ctx, amt = _storm_state(remaining=3)
    base = BASE["attack"]
    seen = []
    for _ in range(6):
        EndTurnOperation.execute(st, advance=False)
        seen.append(int(ctx.stat(StatType.ATTACK)))
    assert seen == [base + amt, base + amt, base, base, base, base], \
        "profil de revert inattendu (ATTACK par tick) : %s" % (seen,)
    per_source = _per_source(ctx, StatType.ATTACK)
    assert all(v >= 0 for v in per_source.values()), "double revert : per_source=%s" % (per_source,)
    assert int(ctx.stat(StatType.ATTACK)) == base, \
        "sur-revert : ATTACK=%d < base %d" % (int(ctx.stat(StatType.ATTACK)), base)


# --------------------------------------------------------------------------------------------------
# 1251 / 1256 -- les PERMANENTS : ce que ferme leur inscription est l'ATTRIBUTION, et le risque
# qu'elle introduit est l'EROSION AU TICK. Les deux faces sont gardees.
# --------------------------------------------------------------------------------------------------

def _duty_state(remaining=0):
    hp = ability_var("UnbreakableDuty", "extraHp", LEVEL)
    dmg = ability_var("UnbreakableDuty", "extraDmg", LEVEL)
    assert hp and dmg, "UnbreakableDuty.extraHp/extraDmg non resolubles -> scenario vide"
    cap = [_cap("UnbreakableDuty_Health", UD_HEALTH, remaining),
           _cap("UnbreakableDuty_Damage", UD_DAMAGE, remaining)]
    st, ctx = _seeded(cap, {"health": int(hp), "attack": int(dmg)}, visual=ANCIENT)
    return st, ctx, int(hp), int(dmg)


def test_unbreakable_duty_seed_attribution_is_not_opaque():
    """Les DEUX self-buffs permanents sont attribues par-source, et le residu opaque tombe a 0 sur
    les deux stats -- validation non circulaire (magnitudes gameconfig == delta natif)."""
    st, ctx, hp, dmg = _duty_state()
    assert int(ctx.stat(StatType.HEALTH)) == BASE["health"] + hp
    assert int(ctx.stat(StatType.ATTACK)) == BASE["attack"] + dmg
    for stat, eff_t, amt in ((StatType.HEALTH, UD_HEALTH, hp), (StatType.ATTACK, UD_DAMAGE, dmg)):
        keys = _statmod_keys(ctx, stat, eff_t)
        assert keys, "%d SEEDE non attribue (per_source=%s)" % (eff_t, _per_source(ctx, stat))
        assert sum(_per_source(ctx, stat)[k] for k in keys) == amt
        assert int(_per_source(ctx, stat).get(CAPTURED_SOURCE, 0)) == 0, \
            "residu opaque non nul sur stat %d : %s" % (int(stat), _per_source(ctx, stat))


def test_unbreakable_duty_permanents_survive_the_expiry_tick():
    """CONTRE-EPREUVE, et c'est le risque que l'inscription INTRODUIT : `turns = NULL` au decompile
    -> `remaining <= 0` materialise PERMANENT cote port -> le gate `!Removed && HasTurns` de
    `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` ne les touche pas. Un revert
    declenche « au tick » au lieu de « au retrait » ferait fondre ces buffs en silence."""
    st, ctx, hp, dmg = _duty_state()
    for e in st.effects.by_unit[UID]:
        assert e.remaining_turns is None, \
            "%s doit etre materialise PERMANENT (turns = NULL au decompile)" % (e.name,)
    before = (int(ctx.stat(StatType.HEALTH)), int(ctx.stat(StatType.ATTACK)))
    for _ in range(5):
        EndTurnOperation.execute(st, advance=False)
    assert st.effects.has_effect(UID, effect_type=UD_HEALTH), "1251 PERMANENT retire par le tick"
    assert st.effects.has_effect(UID, effect_type=UD_DAMAGE), "1256 PERMANENT retire par le tick"
    after = (int(ctx.stat(StatType.HEALTH)), int(ctx.stat(StatType.ATTACK)))
    assert after == before, "buffs permanents erodes par le tick : %s -> %s" % (before, after)


# --------------------------------------------------------------------------------------------------
# Cliquet de fidelite : le couple (stat, permanence) inscrit == celui LU AU DECOMPILE.
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,effect_type,stat,ability,var_key,has_timer", [
    # (nom capte, EffectType, statType du CreateBehaviour, ability gameconfig, cle de variable, timer ?)
    ("SereneUnifierStormOfFire", STORM_OF_FIRE, 0, "SereneUnifier", "extraDmg", True),
    ("UnbreakableDuty_Health", UD_HEALTH, 5, "UnbreakableDuty", "extraHp", False),
    ("UnbreakableDuty_Damage", UD_DAMAGE, 0, "UnbreakableDuty", "extraDmg", False),
])
def test_g1_registry_mirrors_the_decompiled_leaf(name, effect_type, stat, ability, var_key, has_timer):
    """Le registre doit rendre EXACTEMENT le `(statType, amount)` que la feuille native passe a
    `AddStaticStatModifierEffect` -- un stat faux ne rougit nulle part ailleurs (le `Current` reste
    juste, le residu compense) mais ferait reverter la MAUVAISE stat au retrait."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    assert name in EFFECT_CLASSES, "%s absent du registre" % (name,)
    eff = EffectFactory.create(_cap(name, effect_type, 1 if has_timer else 0),
                               100, LEVEL, LEVEL)
    assert eff.get_stat_modification_stat() == stat, \
        "%s : statType %s != %d (decompile)" % (name, eff.get_stat_modification_stat(), stat)
    expected = ability_var(ability, var_key, LEVEL)
    assert expected, "%s.%s non resoluble en gameconfig" % (ability, var_key)
    assert eff.get_stat_modification_amount() == int(expected), \
        "%s : montant %s != %s.%s[L%d] = %d" % (name, eff.get_stat_modification_amount(),
                                                ability, var_key, LEVEL, int(expected))
    assert eff.reverted_stats() == [stat], \
        "%s : reverted_stats %s -- le discriminant du revert par-source" % (name, eff.reverted_stats())
    assert (eff.remaining_turns is not None) == has_timer, \
        "%s : permanence portee %s != decompile (timer=%s)" % (name, eff.remaining_turns, has_timer)


def test_might_of_heroes_stays_dead():
    """VERDICT GARDE (case-371) : `1004/1005/1006 MightOfHeroes_*` sont DEAD -- l'ability existe en
    binaire (`MightOfHeroesAbility$$ExecuteBehaviour` pose bien les trois
    `AddStaticStatModifierEffect`, stats 0x11/0x0/0x10, `Nullable<int>(2)` tours) mais elle est
    ABSENTE du gameconfig, donc ses variables ne sont PAS resolubles : un port serait INERTE
    (magnitude None -> aucune contribution).

    Si ce test rougit, c'est que l'ability est REVENUE au gameconfig -> les trois effets deviennent
    portables et il faut les inscrire (la RE est deja ecrite, cf. case-371)."""
    import gameconfig as GC
    assert not (GC.ability("MightOfHeroes") or {}), \
        "MightOfHeroes est de retour au gameconfig -- porter 1004/1005/1006 (cf. case-371)"
    from engine.entities.effects.factory import EFFECT_CLASSES
    for n in ("MightOfHeroes_ExtraHits", "MightOfHeroes_ExtraDamage", "MightOfHeroes_ExtraArmor"):
        assert n not in EFFECT_CLASSES, "%s inscrit alors que sa magnitude est irresoluble" % (n,)


if __name__ == "__main__":                                   # execution directe = mesure lisible
    raise SystemExit(pytest.main([__file__, "-q"]))
