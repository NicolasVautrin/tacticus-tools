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


class ActiveAbility:
    """Base d'une ability active (`AActiveAbility`). `ABILITY_TYPE` = ActiveAbilityType (enum int).
    `execute_behaviour` mute `state` via les operations portées, en miroir 1:1 du DSL natif."""
    __slots__ = ()
    ABILITY_TYPE: int = -1

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:  # pragma: no cover
        raise NotImplementedError(
            f"{type(self).__name__}.execute_behaviour non porté (cf. plan tranche EFFETS/ABILITIES)")
