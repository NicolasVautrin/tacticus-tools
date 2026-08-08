"""VexillaMagnificaPlaybook — attaque NonComparable (_PlanTarget), utilite = PV cible."""
from __future__ import annotations

from engine import battle_query as bq

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType

from ._base import _PlanTargetPlaybook

#: `EntityExtensions.HasEffect(entity, this.State@+0x20, (EffectType)0x48a, onlyActive: null)` --
#: 0x48a = 1162 = `EffectType.Stunned`, l'effet COMPOSITE pose par cette ability elle-meme
#: (`VexillaMagnificaAbility$$ExecuteBehaviour` b3). A QUALIFIER : l'ordinal 1162 nomme AUSSI
#: `ActiveAbilityType.AncientFury_NormalAttack` -- c'est le NOM qui tranche, jamais l'entier.
_STUNNED = int(EffectType.Stunned)                             # 0x48a = 1162


class VexillaMagnificaPlaybook(_PlanTargetPlaybook):
    """IdunBattle.AI.Playbook.Loki.VexillaMagnificaPlaybook$$EvaluateNonComparable = FromInt(GetStat(cible,5=Health))
    -> PV courants de la cible. IdunBattle.AI.Playbook.Loki.VexillaMagnificaPlaybook$$.cctor : MIN_UTILITY=1.

    CORPS NATIF, RELU INTEGRALEMENT (#566) -- il tient en QUATRE lignes par cible :

        bucket = new Bucket(0, Nullable(<statics[0]>))                 # cctor : Fix64(1) = MIN_UTILITY
        foreach entity in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
            utility = Fix64( UnitExtensions.GetStat(entity, 5 = Health, 0, 0) )
            if (EntityExtensions.HasEffect(entity, this.State@+0x20, 0x48a = 1162 Stunned,
                                           onlyActive: null))  continue;          # <- LE FILTRE
            bucket.AddAction( BasePlaybook.GenerateAction(casterPosition, entity, utility) )

    Le `continue` est SOUS le calcul d'utilite (le natif calcule puis jette) : l'ordre est sans
    observable, `GetStat` n'ayant aucun effet de bord. Ce qui est observable, c'est l'EXCLUSION --
    et elle est loin d'etre theorique : 1183 STUNNE ses deux cibles, donc au cast suivant le natif
    refuse de re-viser une unite qu'il vient d'immobiliser, meme si elle est la plus basse en PV.
    Le port RENDAIT alors `float(hp)` et pouvait donc CHOISIR une cible que le natif ecarte."""
    ABILITY_ID = int(ActiveAbilityType.VexillaMagnifica)  # 1183
    MIN_UTILITY = 1.0

    def should_evaluate(self, ctx) -> bool:
        """Slot 4 de la vtable (0x298, résolu LIVE #46) -> corps FOLDÉ IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$ShouldEvaluate (= le
        `HammerOfWrathPlaybook$$ShouldEvaluate`, COMDAT) : `!EnemyWillBeKilledWithNormalAttack` —
        le natif n'évalue pas Vexilla si l'attaque normale du caster sure-kill déjà un ennemi."""
        from .hammer_of_wrath import _enemy_killed_by_normal_attack
        return not _enemy_killed_by_normal_attack(ctx)

    def evaluate_non_comparable(self, tile, target, ctx):
        hp = ctx.hp_cur_by_id.get(target)                          # GetStat(cible, 5=Health)
        if not hp or hp <= 0:
            return None
        if self._target_is_stunned(target, ctx):                   # `continue` du corps natif
            return None
        return float(hp)

    def _target_is_stunned(self, target, ctx) -> bool:
        """`EntityExtensions$$HasEffect(entity, state, 0x48a, onlyActive: null)`.

        `onlyActive` est le litteral `0` au call-site => le natif ne lit PAS
        `EffectComponent.IsActive @+0x5c` : cote port c'est le foyer PARTAGE
        `battle_query.scene_has_effect` (le MEME que `SuppressiveFire` 1044 et `Neuroparasite` 1183
        triggered), pas une copie locale -- ce serait un fork de port du meme corps natif.

        `ctx.scene` absent (contexte de decision sans scene) -> `False` : le port ne peut pas
        AFFIRMER une presence d'effet qu'aucun substrat ne lui donne, et la degradation va dans le
        sens PERMISSIF (la cible reste candidate), c'est-a-dire le comportement d'avant #566."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return False
        return bool(bq.scene_has_effect(sc, int(target), _STUNNED))
