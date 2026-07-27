"""Probe R16 -- un stat-mod EAGER present AU SEED sort-il du `UnitStats` quand l'effet part ?

MESURE, pas garde : 100 % offline (aucun runner, aucune session Frida). Jumeau exact de
`probe_118_seeded_statmod_revert.py` (qui couvre la famille DECLARATIVE `get_stat_modification_stat`
/`_amount`) pour l'AUTRE famille du port : les effets dont les `ChangeStat` sont declares par
`applied_stat_mods(stats_ctx)` -- ceux dont la magnitude se lit sur le `StatsComponent.ctx` du
porteur (niveau d'ability actif, multiplier de rarete, part INITIAL d'un autre stat).

NATIF (build gqfc5mff6c) -- il n'y a AUCUNE famille « modifie mais ne reverte pas » :

  * `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` lit
    `GetStatModification()` (vtable +0x728 -> ValueTuple<stat, amount, hidden>) et emet
    `ChangeStat(Entity(target), Position(stat, part 5|9), 4, Direct(amount), Entity(<effectEntity>))` ;
  * `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` REJOUE le meme appel avec
    `Position(stat, part 6)` et LA MEME `Entity(<effectEntity>)` ->
    `IdunBattle.Entities.Components.ValueModification$$ReverseModification` retire EXACTEMENT cette
    contribution ;
  * un effet MULTI-stat override `ApplyModification` (ex.
    `IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$ApplyModification`, deux `ChangeStat`) et
    son `RevertInternal` (`IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$RevertInternal`)
    rejoue les DEUX en `Position(9, 6)` / `Position(10, 6)` -- meme entite-effet en source.

La source est donc l'ENTITE-EFFET : elle part avec l'effet, quel que soit le chemin qui l'a posee.
Le port, lui, distinguait « pose EN JEU » (cle `stat_mod_source` renseignee par
`AddEffectOperation._apply_stat_mods` -> revert OK) de « present AU SEED » (aucune cle, contribution
noyee dans le residu opaque `CAPTURED_SOURCE` de `seed_unit_stats` -> revert IMPOSSIBLE).

DEUX CAS mesures (les deux formes de la famille EAGER) :
  1. `ProtectorImperative` (0x4df=1247, mono-stat FIXED_ARMOR, magnitude = `extraArmor[activeLevel]`
     x multiplier) -- retire par le TOGGLE de `DoctrinaImperativesAbility` (feuille `RemoveEffect`) ;
  2. `ActOfFaith_Effect` (0x3f9=1017, MULTI-stat CRIT_CHANCE + CRIT_DAMAGE, magnitude lue sur la part
     INITIAL du crit-damage du porteur) -- retire par `ActOfFaith_RemoveEffectAbility` au crit.

Sortie attendue APRES le fix : per_source = {('statmod', 1247, ...): +extraArmor} et l'armure
                               redescend a sa valeur d'origine au retrait de l'effet.
Sortie mesuree AVANT le fix  : per_source = {'captured': +extraArmor} (residu opaque) et l'armure
                               reste buffee A VIE.

Usage : depuis `scripts/python`, `python probe_r16_eager_statmod_revert.py`.
"""
from __future__ import annotations

from engine.entities import EffectFactory, EffectsState, UnitContext
from engine.entities.effects.magnitude import ability_var, global_value
from engine.entities.stats import StatType
from engine.runner.components import StatsComponent
from engine.runner.operations.effects import revert_stat_mods_of_removed_effects
from engine.runner.state import State

# Niveau d'ability ACTIVE + multiplier de rarete d'un admec au rank courant (unitConfig live).
ACTIVE_LEVEL = 50
MULT = 152
# StatTypes captes par le RPC combatSnapshot (`statTypes`) -- sous-ensemble suffisant ici.
STAT_IDS = {"attack": 0, "movement": 1, "health": 5, "fixedArmor": 16, "critChance": 9,
            "critDamage": 10}
BASE = {"attack": 1000, "movement": 4, "health": 8000, "fixedArmor": 400, "critChance": 15,
        "critDamage": 250}


def _snap_unit(entity_id: int, visual_id: str, delta: dict) -> dict:
    """`combatSnapshot.units[i]` d'une unite qui porte DEJA le buff : `stats` = Current (donc base +
    delta, le bonus est CUIT dedans -- c'est tout le probleme du cas SEEDE) et `statDelta` = le delta."""
    stats = {k: BASE[k] + int(delta.get(k, 0)) for k in BASE}
    return {"entityId": entity_id, "visualId": visual_id, "stats": stats, "statDelta": dict(delta),
            "unitConfig": {"activeAbilityLevel": ACTIVE_LEVEL,
                           "abilityVariablesMultiplier": MULT}}


def _build(entity_id: int, visual_id: str, captured: list, delta: dict):
    """`State` minimal reproduisant la voie SEEDE de `snapshot._load_stats_and_effects` :
    `UnitContext.from_snapshot` (attribution) + `EffectsState.seed` (instances evoluees)."""
    su = _snap_unit(entity_id, visual_id, delta)
    effs = EffectFactory.create_many(captured, MULT, None, ACTIVE_LEVEL)
    ctx = UnitContext.from_snapshot(su, None, STAT_IDS, effs)
    ctx.ability_variables_multiplier = MULT
    ctx.active_ability_level = ACTIVE_LEVEL
    st = State()
    st.add_entity(entity_id).add_component(StatsComponent(ctx=ctx))
    st.effects = EffectsState.seed({entity_id: captured}, {entity_id: MULT})
    return st, ctx


def _report(title: str, ctx, st: State, uid: int, stats_watched: list, expected_drop: dict) -> bool:
    """Retire l'effet (mirror de la feuille `RemoveEffect` : l'instance est CONSOMMEE) puis joue le
    mirror de `RevertModification` et confronte la stat a sa valeur d'origine."""
    print("== %s" % title)
    before = {int(s): ctx.stat(int(s)) for s in stats_watched}
    for s in stats_watched:
        comp = ctx.stats.components.get(int(s))
        print("   stat %-2d per_source = %s" % (int(s), comp.modification.per_source if comp else None))
    print("   avant retrait    : %s" % before)
    for e in st.effects.by_unit[uid]:
        e.consumed = True                      # feuille `RemoveEffect` / toggle / consommation
    out = revert_stat_mods_of_removed_effects(st)
    after = {int(s): ctx.stat(int(s)) for s in stats_watched}
    print("   reverts joues    : %s" % out)
    print("   apres retrait    : %s" % after)
    ok = True
    for s in stats_watched:
        want = before[int(s)] - int(expected_drop.get(int(s), 0))
        got = after[int(s)]
        flag = "OK" if got == want else "KO"
        print("   stat %-2d : %s -> %s (attendu %s) [%s]" % (int(s), before[int(s)], got, want, flag))
        ok = ok and (got == want)
    print("   VERDICT          : %s" % ("REVERTE" if ok else "NON REVERTE"))
    return ok


def case_protector() -> bool:
    """Mono-stat EAGER : `ProtectorImperativeEffect.applied_stat_mods` = FIXED_ARMOR += extraArmor."""
    amt = int(ability_var("DoctrinaImperatives", "extraArmor", ACTIVE_LEVEL, multiplier_pct=MULT))
    captured = [{"name": "ProtectorImperative", "effectType": 1247, "level": 1,
                 "remaining": 0, "source": 41}]
    st, ctx = _build(41, "admecMarshall", captured, {"fixedArmor": amt})
    return _report("ProtectorImperative 1247 (FIXED_ARMOR += %d)" % amt, ctx, st, 41,
                   [StatType.FIXED_ARMOR], {int(StatType.FIXED_ARMOR): amt})


def case_act_of_faith() -> bool:
    """Multi-stat EAGER : `ActOfFaithBuffEffect.applied_stat_mods` = CRIT_CHANCE += extraCritChance et
    CRIT_DAMAGE += Ceiling(base_critDmg x extraCritDmgPct%)."""
    cc = int(global_value("actOfFaithExtraCritChance") or 0)
    pct = int(global_value("actOfFaithExtraCritDmgPct") or 0)
    cd = -(-(BASE["critDamage"] * pct) // 100)
    captured = [{"name": "ActOfFaith_Effect", "effectType": 1017, "level": 1,
                 "remaining": 0, "source": 42}]
    st, ctx = _build(42, "adeptCanoness", captured, {"critChance": cc, "critDamage": cd})
    return _report("ActOfFaith_Effect 1017 (CRIT_CHANCE += %d, CRIT_DAMAGE += %d)" % (cc, cd),
                   ctx, st, 42, [StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE],
                   {int(StatType.CRIT_CHANCE): cc, int(StatType.CRIT_DAMAGE): cd})


def case_expiry_by_timer() -> bool:
    """CROISEMENT avec O3 (`EffectsState.on_turn_end`) : le seul membre du gisement a porter un VRAI
    timer est `Waaagh_ExtraMovement` (0x44b=1099, pose avec `duree@dsl+0xc0 = Direct(1)`). Depuis que le
    retrait a echeance est effectif (mirror `EffectComponent$$RemoveOneTurn` + `$$ShouldBeRemoved`), un
    stat-mod EAGER seede non retirable produisait un etat INCOHERENT -- effet absent de `has_effect`,
    buff toujours applique. Ici on joue le VRAI foyer (`EndTurnOperation.execute` : tick de toutes les
    entites PUIS `revert_stat_mods_of_removed_effects`), pas une sequence rejouee a la main.

    Les autres membres sont PERMANENTS (`BlackRage_ExtraMove` 0x53e=1342 pose avec duree 0 ;
    `AnvilShield_FrozenAttackerAdvantage` 0x4b1=1201 absent de `DefaultAmountOfRounds`, retire par son
    trigger `On(UnitPostAbility)` ; `ProtectorImperative` 0x4df=1247 mesure `rem=0` live) -> le tick de
    duree ne les concerne pas, leur retrait passe par une feuille `RemoveEffect`."""
    from engine.runner.components import OwnerComponent, UnitComponent
    from engine.runner.operations.turnflow import EndTurnOperation

    amt = int(ability_var("Waaagh", "extraMovement", is_constant=True) or 0)
    uid, rem0 = 55, 3
    captured = [{"name": "Waaagh_ExtraMovement", "effectType": 1099, "level": 1,
                 "remaining": rem0, "source": uid}]
    stats = {k: BASE[k] for k in BASE}
    stats["movement"] = BASE["movement"] + amt
    su = {"entityId": uid, "visualId": "orksWarboss", "stats": stats,
          "statDelta": {"movement": amt},
          "unitConfig": {"activeAbilityLevel": ACTIVE_LEVEL, "abilityVariablesMultiplier": MULT}}
    effs = EffectFactory.create_many(captured, MULT, None, ACTIVE_LEVEL)
    ctx = UnitContext.from_snapshot(su, None, STAT_IDS, effs)
    st = State()
    ent = st.add_entity(uid)
    ent.add_component(StatsComponent(ctx=ctx))
    ent.add_component(OwnerComponent(player=3, team=1))
    ent.add_component(UnitComponent(visual_id="orksWarboss", alive=True))
    st.effects = EffectsState.seed({uid: captured}, {uid: MULT})
    st.current_player_id = 3

    print("== Waaagh_ExtraMovement 1099 SEEDE rem=%d, expiration par TIMER (MOVEMENT +%d)"
          % (rem0, amt))
    comp = ctx.stats.components[int(StatType.MOVEMENT)]
    print("   per_source        = %s" % (comp.modification.per_source,))
    print("   t0                : MOVEMENT=%d has_effect=%s"
          % (ctx.stat(int(StatType.MOVEMENT)), st.effects.has_effect(uid, effect_type=1099)))
    profile = []
    for i in range(rem0 + 2):
        e = st.effects.by_unit[uid][0]
        EndTurnOperation.execute(st, advance=False)
        mv = ctx.stat(int(StatType.MOVEMENT))
        profile.append(mv)
        print("   EndTurn %d (rem %s->%s) : MOVEMENT=%d has_effect=%-5s per_source=%s"
              % (i + 1, e.remaining_turns if i == 0 else "-", e.remaining_turns, mv,
                 st.effects.has_effect(uid, effect_type=1099), comp.modification.per_source))
    want = [BASE["movement"] + amt] * (rem0 - 1) + [BASE["movement"]] * 3
    ok = (profile == want)
    print("   profil            : %s (attendu %s)" % (profile, want))
    print("   VERDICT           : %s"
          % ("UNE fois, au tick ou remaining atteint 0" if ok else "profil de revert FAUX"))
    return ok


def inventory() -> bool:
    """INVENTAIRE du gisement : toute classe du registre qui OVERRIDE `applied_stat_mods` doit rendre
    une cle de source retirable (`effect_stat_mod_key != None`) meme SEEDEE, sinon son buff resterait
    colle. Balaye `EFFECT_CLASSES` pour eviter de ne fermer que les deux porteurs mesures ci-dessus."""
    from engine.entities.effects import EFFECT_CLASSES, effect_stat_mod_key
    from engine.entities.effects.base import BaseEffect

    print("== inventaire des classes a `applied_stat_mods` (forme OVERRIDE d'ApplyModification)")
    ok = True
    seen = set()
    for name, klass in sorted(EFFECT_CLASSES.items()):
        if klass in seen or klass.applied_stat_mods is BaseEffect.applied_stat_mods:
            continue
        seen.add(klass)
        eff = klass(name=name, effect_type=0)
        key = effect_stat_mod_key(eff)
        flag = "OK" if key is not None else "KO"
        print("   %-34s %-44s reverted_stats=%s cle=%s [%s]"
              % (klass.__name__, name, [int(s) for s in (eff.reverted_stats() or [])],
                 "derivee" if key is not None else None, flag))
        ok = ok and (key is not None)
    print("   VERDICT          : %s" % ("toutes retirables" if ok else "au moins une NON retirable"))
    return ok


def main() -> int:
    ok = case_protector()
    print("")
    ok = case_act_of_faith() and ok
    print("")
    ok = case_expiry_by_timer() and ok
    print("")
    ok = inventory() and ok
    print("")
    print("R16 : %s" % ("les stat-mods EAGER seedes SONT revertables"
                        if ok else "les stat-mods EAGER seedes NE SONT PAS revertables"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
