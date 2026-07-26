"""Effets de la faction DARK ANGELS (case-117 phase 2) — namespace natif
`IdunBattle.Entities.Effects.Loki`.

Un seul effet ici : `Hailstrike_ExtraPierceEffect` (0x5e5 = 1509), le canal PERCAGE du buff pose par
`HailstrikeAbility` (1214, `darkaStormSpeeder`). Meme famille que `GravitonRifle_ExtraPierce`
(effects/loki/votann.py) : une classe d'effet DEDIEE cote natif, qui n'override QUE
`CreatePiercingBonusForAttack` (aucun stat-mod, aucun bonus de degat).

DIFFERENCE STRUCTURELLE avec GravitonRifle (et c'est ce qui a demande une resolution de scaling
propre ici) : l'effet GravitonRifle est un OWNER-effect (porteur == source == Vynn), alors que
Hailstrike est pose par la MACHINE OF WAR **sur un ALLIE** -> porteur != source. Or le montant est
`ConfigVar(0x3f, GetAbilityState(effect), config@0x60)` = l'AbilityState de **la SOURCE**, jamais
celle du porteur. Cf. `_source_scaling` ci-dessous.
"""
from __future__ import annotations

from ..base import BaseEffect, is_ranged_attack
from ..magnitude import ability_var

_HAILSTRIKE = "Hailstrike"        # ActiveAbilityType 0x4be = 1214 (darkaStormSpeeder / Storm Speeder)


class HailstrikeExtraPierceEffect(BaseEffect):
    """`Hailstrike_ExtraPierce` (0x5e5 = 1509) — buff pose sur un ALLIE par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HailstrikeAbility$$ExecuteBehaviour`
    (`AddEffect(0x5e5, AbilityStateReference, source = caster@0x160, targets = target@0x178,
    TurnsFromRounds(nrOfRounds))`, cf. runner/abilities/darkangels.py).

    `IdunBattle.Entities.Effects.Loki.Hailstrike_ExtraPierceEffect$$.ctor` =
    `BaseEffect(AbilityOrEffect(0x4be = 1214 Hailstrike), 1)` -> la config lue est celle de l'ability
    1214 (`extraPierceRatio`), au niveau de la SOURCE.

    `IdunBattle.Entities.Effects.Loki.Hailstrike_ExtraPierceEffect$$CreatePiercingBonusForAttack`
    (MIRROR 1:1 du decompile) :

        gate = get_OwnerIsCaster & ( IsRangedAttack() | IsOverwatchAttack() )
        return Nullable( EffectBonus.ForPiercing( gate,
                             ConfigVar(0x3f = 63 extraPierceRatio, GetAbilityState(this), this+0x60) ) )

    Le montant est ADDITIF au ratio de percage de l'attaque, consomme par
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` :
    `Min(100, Max(base>0, dirPierce + extraPierce + <bonus d'effets> + basePiercingRatio))`.

    DEUX gates cumulatifs SEULEMENT (contraste avec GravitonRifle qui en a trois) :
      * `get_OwnerIsCaster` : le PORTEUR de l'effet doit etre l'ATTAQUANT du coup courant (la MoW,
        elle, ne beneficie de rien) ;
      * `IsRangedAttack | IsOverwatchAttack` : DISJONCTION -- **aucun** gate `CurrentAbilityIs`, donc
        le bonus s'applique a l'attaque NORMALE ranged du porteur comme a ses abilities ranged
        (i2 : « Ranged and Overwatch attacks have +X% pierce ratio »). C'est pourquoi le port cable
        l'agregateur de percage sur la voie d'attaque NORMALE aussi (runner/operations/damage_ops.py).
    """

    def _source_scaling(self, ctx) -> "tuple[int, int]":
        """(niveau d'ability ACTIVE, multiplier de rarete %) qui indexent le `ConfigVar` du montant.

        `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` rend l'`AbilityState` attachee a
        l'effet, c.-a-d. celle que l'`AbilityStateReference` du call-site a capturee : celle de la
        **SOURCE** (`caster@0x160` = la Storm Speeder), PAS celle du porteur du buff. Deux chemins de
        materialisation cote port, dans cet ordre :
          1. effet POSE offline par `AddEffectOperation` avec `scale_from_source=True` -> le niveau
             actif de la source est deja seede sur l'instance (`active_ability_level`) ;
          2. effet CAPTE depuis le live (`EffectsState.seed`) -> l'instance ne porte QUE le niveau du
             PORTEUR (mauvaise unite) ; on re-resout depuis `self.source` via le resolveur
             `unit_ctx_of` que l'agregateur cote runner depose dans le `ctx` du coup (l'inversion de
             dependance evite a `engine/entities` de connaitre l'ECS `engine/runner`).
        Aucun repli sur `self.ability_level` (= le niveau du PORTEUR) : ce serait la mauvaise unite,
        et `extraPierceRatio` VARIE avec le niveau (10 / 12 / 15 selon la config 1214). Faute de
        source resolvable -> (0, 100) = premiere entree de la courbe, jamais un niveau invente.
        """
        lvl = self.active_ability_level
        mult = self.ability_variables_multiplier
        if lvl is None:
            resolve = (ctx or {}).get("unit_ctx_of")
            sctx = resolve(self.source) if (callable(resolve) and self.source is not None) else None
            if sctx is not None:
                lvl = getattr(sctx, "active_ability_level", None)
                mult = getattr(sctx, "ability_variables_multiplier", mult)
        return int(lvl) if lvl is not None else 0, int(mult or 100)

    def create_effect_piercing_bonus_for_attack(self, ctx=None) -> "int | None":
        """`CreatePiercingBonusForAttack` — bonus ADDITIF au ratio de percage du coup courant, ou None
        si un gate tombe. `ctx` (fourni par `piercing_bonus_from_effects`) :
        `{owner_id, att_id, is_ranged, is_overwatch, unit_ctx_of, ...}` — `owner_id == att_id` mirror
        `get_OwnerIsCaster` ; `is_ranged`/`is_overwatch` mirrorent la disjonction
        `IsRangedAttack | IsOverwatchAttack`. `is_ranged is None` (nature du coup non threadee par la
        facade appelante) = les DEUX gates natifs se TAISENT (`BattleQuery$$IsRangedAttack` ne rend
        VRAI que si la nature est PROUVEE distance, cf. `is_ranged_attack` #106) -> pas de bonus."""
        c = ctx or {}
        oid, aid = c.get("owner_id"), c.get("att_id")
        if oid is None or aid is None or oid != aid:              # get_OwnerIsCaster
            return None
        if not (is_ranged_attack(c.get("is_ranged")) or bool(c.get("is_overwatch"))):
            return None                                           # IsRangedAttack | IsOverwatchAttack
        lvl, mult = self._source_scaling(c)
        amt = ability_var(_HAILSTRIKE, "extraPierceRatio", lvl, multiplier_pct=mult)
        return int(amt) if amt else None
