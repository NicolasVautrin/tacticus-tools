"""Base des abilities actives portées + helpers DSL communs.

`ActiveAbility` = base d'une ability native `AActiveAbility` ; chaque sous-classe porte UNE ability
(VA citée) et implémente `execute_behaviour` (mirror de `<Ability>.ExecuteBehaviour`).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import State


def ability_attack_params(state: "State", caster_id: int, ability_id: str,
                          profile_name: str, ranged: bool = False,
                          min_key: str = "minDmg", max_key: str = "maxDmg",
                          hits_key: str = "nrOfHits"):
    """Paramètres de l'attaque d'une ability (mirror `MinMaxDamage`/`GetHits`/`GetDamageProfile`) depuis
    l'ECS + gameconfig : `(base_min, base_max, pierce, hits)`.
      • base_min/base_max = `GetVariableForLevel(config, 0xc/0xd, level)` = `minDmg`/`maxDmg`[active_ability_level]
        scalés par `AbilityVariablesMultiplier` (vars flaggées rareté) — via `ability_var`.
      • hits = `GetNumberConstant(config, 0x2f)` = `nrOfHits` (constante).
      • pierce = clamp(0,100, profil.PiercingRatio + ExtraPierce + ExtraPierce{Melee|Ranged}) — même
        modèle que l'attaque normale (`select_weapon_pierce`), avec le PROFIL de l'ability.

    `min_key`/`max_key`/`hits_key` = noms des variables/constantes config à lire (défaut minDmg/maxDmg/
    nrOfHits). Une ability à DEUX volets de dégât (ex. CrushingClaws : attaque principale + splash) passe
    le 2ᵉ jeu de clés (`minDmg_2`/`maxDmg_2`/`nrOfHits_2`) + son profil pour le volet secondaire."""
    from ..components import StatsComponent
    from ...entities.effects.magnitude import ability_var
    import gameconfig as GC
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = ctx.active_ability_level if ctx is not None else 0
    mult = ctx.ability_variables_multiplier if ctx is not None else 100
    bmin = ability_var(ability_id, min_key, level, multiplier_pct=mult) or 0
    bmax = ability_var(ability_id, max_key, level, multiplier_pct=mult) or 0
    hits = ability_var(ability_id, hits_key, is_constant=True) or 1
    dp = GC.damage_profile(profile_name) or {}
    extra = ctx.extra_pierce if ctx is not None else 0
    dir_pierce = ((ctx.extra_pierce_ranged if ranged else ctx.extra_pierce_melee)
                  if ctx is not None else 0)
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + extra + dir_pierce))
    return int(bmin), int(bmax), pierce, int(hits)


def turns_from_rounds(rounds: int) -> int:
    """`DSLFactory.TurnsFromRounds` @180dfec50 -> `TurnsFromRoundsFormula.Calculate` @180f26a50 =
    `BattleQuery.ConvertRoundsToTurns` @181058af0 = `count(joueurs du turnOrder, PlayerType != 2) * rounds`
    (RE #174 : PlayerType@+0x20 = config statique, Environment=2 exclu ; count = CONSTANTE de bataille).

    Le port rend l'IDENTITE (rounds) car dans NOS runners 1v1, `count(non-Env) = 1` -- PROUVE DIRECTEMENT
    par le test committe test_effect_stun_live (Stunned DefaultAmountOfRounds=1 -> convert(1) = live_remaining
    = 1, pose mid-turn sans decrement). count etant constant, TOUT effet round y vaut rounds x 1 = rounds :
    l'identite est CORRECTE pour nos runners (PAS une approximation). Elle ne divergerait QUE dans une bataille
    a count>=2 (ex. arene MoW ou le feu = convert(2)=4), NON simulee par le port ; si un tel contexte est un
    jour valide, brancher `convert_rounds_to_turns(state, rounds)` lisant le turnOrder runtime (cf. #174)."""
    return int(rounds)


# ---------------------------------------------------------------------------
# « Does not end turn » (#139) — mirror des virtuals `SetsEndTurnFlags` / `SetsActiveAbilityUsedFlag`.
#
# NATIF : chaque ability active expose deux virtuals retournant un `IdunBattle.DSL.IAbilityTrigger` :
#   • `AActiveAbility.SetsEndTurnFlags` @180fb3150          = `_dslFactory(+0x30).True(+0xf8)` (défaut)
#   • `AActiveAbility.SetsActiveAbilityUsedFlag`            = `_dslFactory.True` (même body, foldé IL2CPP)
# Après exécution, `ActiveAbilityOperation.ExecuteInternal` @180e44ec0 calcule :
#   skipEndTurn     = options.skipEndTurnFlag  || !ability.SetsEndTurnFlags().Evaluate(entities)
#                     (`GetSkipEndTurnFlag` @180e47120, slot iface 0x17)
#   skipAbilityUsed = options.skipAbilityUsedFlag || !ability.SetsActiveAbilityUsedFlag(caster).Evaluate(...)
#                     (`GetSkipAbilityUsedFlag` @180e46f60, slot iface 0x18)
# puis `AddFlagsAfterAbilityExecution(caster, skipAbilityUsed, skipEndTurn)` @180e447f0 :
#   !skipAbilityUsed -> UnitFlags.Add(ActiveAbilityUsed=2)
#   !skipEndTurn     -> OperationProcessor.FinishUnitTurn @180e081c0 -> FinishUnitTurnOperation @180e72140
#                       (UnitFlags.Add(ArrivedAtFinalTile=1) + Add(TurnFinished=3)).
#
# INVENTAIRE des overrides (dump symbols.json build gqfc5mff6c ; ids = ActiveAbilityType) — les corps
# constants sont FOLDÉS par IL2CPP (dédup) : fold-winners lus = `ArcScourgeAbility.SetsEndTurnFlags`
# @1811b3d40 (`return _dsl.No(+0x118)`) et `.SetsActiveAbilityUsedFlag` @1811b3d20 (`return _dsl.False
# (+0x100)`, 27 refs vtable). Sémantique croisée avec les tooltips i2 (« does not end X's turn »).
#
# Ability -> unité (i2) : 1014 ArmoriumCherub=Vindicta · 1063 FireAndReposition=Calandis · 1077
# EarlyWarningOverride=Re'vas · 1081 FightingRetreat=Darkstrider · 1106 WarHowl=Ragnar · 1118
# DoctrinaImperatives=Tan Gi'da · 1121 ItItches=Parasite of Mortrex · 1127 ArmouredMight_Move ·
# 1131 JakhalStimms=Macer · 1139 SentinelDirectives=Sy-Gex · 1173 ArcScourge=Belisarius Cawl ·
# 1189 CalibaniteGreatsword=Forcas · 1198 EuphoricStrikes=Laviscus · 1202 VigilanceEternal=Tyrith ·
# 1210 ExemplarOfTheMontka=Farsight.

# Classes overridant `SetsEndTurnFlags` (l'ability NE termine PAS le tour) — 14 classes.
NO_END_TURN_ABILITY_TYPES = frozenset({
    1014, 1063, 1081, 1106, 1118, 1121, 1127, 1131, 1139, 1173, 1189, 1198, 1202, 1210,
})

# Classes overridant `SetsActiveAbilityUsedFlag` (pas de flag ActiveAbilityUsed=2) — 13 classes
# (PAS 1063 FireAndReposition ni 1121 ItItches ; + 1077 EarlyWarningOverride qui n'override QUE celui-ci).
NO_ABILITY_USED_FLAG_ABILITY_TYPES = frozenset({
    1014, 1077, 1081, 1106, 1118, 1127, 1131, 1139, 1173, 1189, 1198, 1202, 1210,
})

# Ability 1081 FightingRetreat (Darkstrider) = SEUL override CONDITIONNEL lu dans le build courant :
# `FightingRetreatAbility.SetsActiveAbilityUsedFlag` @1811de7e0 = `_dsl.Direct(!Any(battleQuery slot 0x7c
# (caster, currentPlayerEntityId)))` — pose les flags UNIQUEMENT si AUCUN ennemi adjacent (i2 : « does not
# end Darkstrider's turn IF he is adjacent to an enemy »). Son SetsEndTurnFlags (corps foldé, non isolable
# offline) est aligné sur la même condition par le texte i2 — ASSOMPTION DOCUMENTÉE, même prédicat.
FIGHTING_RETREAT = 1081


def _fighting_retreat_sets_flags(state: "State", caster_id: int) -> bool:
    """Mirror @1811de7e0 : True (pose les flags = tour fini) ssi PAS d'ennemi VIVANT adjacent (dist hex 1)
    au caster. Ennemi = `team` differente (meme convention que les autres ports, ex. `_nearest_enemy`)."""
    import hexgeo
    from ..components import OwnerComponent, PositionComponent, UnitComponent
    e = state.get_entity(caster_id)
    if e is None:
        return True
    oc = e.get_component(OwnerComponent)
    pc = e.get_component(PositionComponent)
    if oc is None or pc is None:
        return True
    src = (pc.col, pc.row)
    for oid, other in state.entities.items():
        if oid == caster_id:
            continue
        ouc = other.get_component(UnitComponent)
        ooc = other.get_component(OwnerComponent)
        opc = other.get_component(PositionComponent)
        if ooc is None or opc is None or ooc.team == oc.team:
            continue
        if ouc is not None and not ouc.alive:
            continue
        if hexgeo.distance(src, (opc.col, opc.row)) == 1:
            return False
    return True


def sets_end_turn_flags_for(ability_type: int, state: "State", caster_id: int) -> bool:
    """Verdict `ability.SetsEndTurnFlags().Evaluate(entities)` pour UN ActiveAbilityType (défaut base
    @180fb3150 = True ; overrides = inventaire RE ci-dessus). Utilisé par le handler pour TOUTE ability
    exécutée, portée ou non (le natif pose les flags indépendamment du contenu de la behaviour)."""
    at = int(ability_type)
    if at == FIGHTING_RETREAT:
        return _fighting_retreat_sets_flags(state, caster_id)
    return at not in NO_END_TURN_ABILITY_TYPES


def sets_active_ability_used_flag_for(ability_type: int, state: "State", caster_id: int) -> bool:
    """Verdict `ability.SetsActiveAbilityUsedFlag(caster).Evaluate(entities)` (défaut True ; overrides =
    inventaire RE)."""
    at = int(ability_type)
    if at == FIGHTING_RETREAT:
        return _fighting_retreat_sets_flags(state, caster_id)
    return at not in NO_ABILITY_USED_FLAG_ABILITY_TYPES


class ActiveAbility:
    """Base d'une ability active (`AActiveAbility`). `ABILITY_TYPE` = ActiveAbilityType (enum int).
    `execute_behaviour` mute `state` via les operations portées, en miroir 1:1 du DSL natif."""
    __slots__ = ()
    ABILITY_TYPE: int = -1

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:  # pragma: no cover
        raise NotImplementedError(
            f"{type(self).__name__}.execute_behaviour non porté (cf. plan tranche EFFETS/ABILITIES)")

    def sets_end_turn_flags(self, state: "State", caster_id: int) -> bool:
        """Mirror du virtual `SetsEndTurnFlags` @180fb3150 (défaut `_dsl.True`) — résolu par la table
        d'overrides RE (une sous-classe portée PEUT surcharger pour une logique bespoke)."""
        return sets_end_turn_flags_for(self.ABILITY_TYPE, state, caster_id)

    def sets_active_ability_used_flag(self, state: "State", caster_id: int) -> bool:
        """Mirror du virtual `SetsActiveAbilityUsedFlag` (défaut `_dsl.True`, body foldé @180fb3150)."""
        return sets_active_ability_used_flag_for(self.ABILITY_TYPE, state, caster_id)
