"""`WallOfMirrors` (0x576 = 1398) — l'effet de PERCAGE que le cast de `WallOfMirrors` (1186) pose sur
son propre caster, le temps d'UNE attaque normale, avant de le retirer (#433-r4-r1-r1).

`IdunBattle.Entities.Effects.Loki.WallOfMirrorsEffect$$.ctor` =
`BaseEffect(AbilityOrEffect(<1186>), hasAutomaticActivation: 1)` -> la config lue est celle de
l'ability **1186**, pas une config d'effet propre.

`IdunBattle.Entities.Effects.Loki.WallOfMirrorsEffect$$CreatePiercingBonusForAttack`
(MIRROR 1:1 du decompile) :

    return Nullable( EffectBonus.ForAddition(
                         DSLTriggers.get_OwnerIsCaster,
                         DSLFormulas.Get( AbilityConfiguration.GetNumberConstant(config@0x60, 0x40) ) ) )

**UN SEUL gate** -- `get_OwnerIsCaster`. Pas de `CurrentAbilityIs`, pas de `HasTrait(target, ...)` :
contrairement a `GravitonRifle_ExtraPierce` (trois gates), ce bonus s'applique a TOUTE attaque du
porteur tant que l'effet est actif. C'est coherent avec l'arbre qui le pose : `AddEffect(0x576)` juste
AVANT le `UseNormalAttack` et `RemoveEffect(0x576)` juste APRES (cf.
`runner/abilities/loki/wall_of_mirrors.py`) -- la fenetre d'activite EST l'attaque.

`0x40` = `extraPierce`, tranche PAR ELIMINATION (meme methode que `BrazierOfHolyFire`) : la config
gameconfig de `WallOfMirrors` ne porte que DEUX constantes, `range` et `extraPierce`, et
`IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant`/`GetNumberConstant` LEVE si la cle
manque. `0x16 = range` est deja ancre (`AActiveAbility$$SetConfigValuesInTargetingOptions`,
cf. `runner/abilities/targeting.py::ABILITY_CONSTANT_RANGE`) -> `0x40` ne peut etre que `extraPierce`.
C'est une CONSTANTE (`GetNumberConstant`), donc sans indexation par niveau : `extraPierce = 15`.

Le montant est ADDITIF au ratio de percage du coup, consomme par
`IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` :
`Min(100, Max(base>0, dirPierce + extraPierce + <ces bonus> + basePiercingRatio))` -- meme canal que
`GravitonRifle_ExtraPierce`, agrege par `entities/effects/__init__.py::piercing_bonus_from_effects`.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var

_WALL_OF_MIRRORS = "WallOfMirrors"          # la cle gameconfig de l'ability 1186


class WallOfMirrorsEffect(BaseEffect):
    """`WallOfMirrors` (0x576 = 1398) — canal PERCAGE pur (aucun `applied_stat_mods`)."""

    def create_effect_piercing_bonus_for_attack(self, ctx=None) -> "int | None":
        """`CreatePiercingBonusForAttack` — bonus ADDITIF au ratio de percage du coup courant, ou
        `None` si le gate `get_OwnerIsCaster` tombe. `ctx` (fourni par `piercing_bonus_from_effects`)
        : `{owner_id, att_id, ...}` -- `owner_id == att_id` mirror `get_OwnerIsCaster`."""
        c = ctx or {}
        oid, aid = c.get("owner_id"), c.get("att_id")
        if oid is None or aid is None or oid != aid:          # get_OwnerIsCaster
            return None
        amt = ability_var(_WALL_OF_MIRRORS, "extraPierce", is_constant=True)
        return int(amt) if amt else None
