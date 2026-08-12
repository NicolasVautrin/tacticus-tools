"""`WhisperingWeb` (`TriggeredAbilityType` 0x62a = 1554, passif d'`eldarLhykhis`) -- LA TOILE
MONO-CIBLE (#965).

`...WhisperingWebAbility$$CreateTrigger` (LU) :

    On(EventTriggerType.NormalAttack = 0x26, ownerNeedsToBeAlive = 1)
      & IsRangedAttack
      & get_OwnerIsCaster
      & AreEnemies(Target@<DSLSelectors+0x60>, Caster@<DSLSelectors+0x48>)

`...WhisperingWebAbility$$CreateBehaviour` (LU) :

    sel = OwnerOfEffect( EffectsFromUnitSource(Owner@<DSLSelectors+0x30>,
                                               EffectType.WhisperingWeb = 0x62b) )
        RemoveEffect(sel, Nullable(EffectType.WhisperingWeb), null)
      + AddBondEffect(EffectType.WhisperingWeb, AbilityStateReference,
                      source   = Caster@<DSLSelectors+0x48>,
                      targets  = Target@<DSLSelectors+0x60>,
                      bondWith = Caster@<DSLSelectors+0x48>,
                      turns    = default)

Le `RemoveEffect` de TETE est ce qui rend la toile MONO-CIBLE : le selecteur remonte de l'effet a
SON PORTEUR (`OwnerOfEffect`), en ne retenant que les instances dont la SOURCE est Lhykhis
(`EffectsFromUnitSource(Owner)`) -- donc Lhykhis retire sa toile de la cible precedente avant de la
poser sur la nouvelle. Il ne touche pas a la toile d'un AUTRE Lhykhis (miroir, duel), ce que le
filtre par source garantit.

CE MODULE NE PORTE QUE L'ABILITY (la POSE). L'EFFET 1579 et sa magnitude sont un RESIDU
--------------------------------------------------------------------------------------
`IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateEffectDamageBonusForAttack` (LU) :

    trigger = get_OwnerIsTarget
            & ( AreFriends(Caster@<DSLSelectors+0x48>, EffectSource(<DSLSelectors+0x38>))
                & IsHero(Caster@<DSLSelectors+0x48>) )
    amount  = ConfigVar(AbilityVariableType.extraDmg = 8) * CurrentHitIndex()
    return EffectBonus.ForAddition(trigger, amount)

Le facteur `CurrentHitIndex()` est ce qui BLOQUE le port de la magnitude, et le blocage est
STRUCTUREL, pas un manque de RE (#965-r2) : le canal d'accueil est
`BaseEffect.create_effect_damage_malus_for_defense` (l'effet vit sur la CIBLE, le natif verse sa
contribution dans `attackModifiers` -> `DEFENSE_MALUS_NATIVE_FACE = "attacker"`, meme regime que
`ExemplarOfHate_Target` / `Chronometron_ExtraDamage`), or son `attacker_ctx` ne porte PAS
`hit_index` et ne peut pas le porter en l'etat : `runner/damage_model.py::defender_modifiers` est
appele UNE FOIS PAR ATTAQUE, avant la boucle de coups (`damage_ops/normal.py`, le `hit_index` n'est
threade que dans `_crit_params`). Poser la classe d'effet avec une magnitude qui rend `None` en
l'absence de `hit_index` la rendrait MATERIALISEE ET INERTE -- exactement le vice que #462-r4b-r1-r1
a ferme ailleurs. Le residu nomme le foyer (le pipeline de degat) et ce qu'il faut y threader.

⚠ Consequence assumee : apres cette tranche, l'effet 1579 est POSE et RETIRE fidelement (donc
visible du `decisionView` et de l'IA), mais il n'ajoute AUCUN degat. C'est un ecart RESTRICTIF,
nomme, et non un port silencieusement faux.

⚠ `WhisperingWebEffect$$CreateTargetSelector` est un corps DEDUPLIQUE par ICF
(`return <DSLSelectors+0x30>` = `Owner`), que ghidra attribue arbitrairement a cette classe : six
modules du port le citent deja comme corps d'emprunt d'un AUTRE effet. Il ne dit rien de
`WhisperingWeb` en particulier.

RE complete : `docs/rl/case-965-whispering-web-refusal-to-be-outdone.md`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner, Target
from .....entities.selectors.tiles import Caster
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddBondEffect, RemoveEffect
from ....components import OwnerComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: `TriggeredAbilityType` de l'ability qui POSE.
WHISPERING_WEB = int(TriggeredAbilityType.WhisperingWeb)                    # 0x62a = 1554
#: `EffectType` de la toile -- l'argument des DEUX feuilles du behaviour.
WEB_EFFECT = int(EffectType.WhisperingWeb)                                 # 0x62b = 1579


def _owner_component(state: State, unit_id) -> Optional[OwnerComponent]:
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    return e.get_component(OwnerComponent) if e is not None else None


def webs_placed_by(state: State, source_id: int) -> list:
    """`OwnerOfEffect( EffectsFromUnitSource(Owner@<DSLSelectors+0x30>, 0x62b) )` -- les PORTEURS
    des instances de 1579 dont la SOURCE est `source_id`.

    Le filtre par SOURCE est LU, pas ajoute : `EffectsFromUnitSource` prend le selecteur `Owner`
    en argument. C'est lui qui empeche Lhykhis de retirer la toile d'un autre poseur."""
    out: list = []
    effects = getattr(state, "effects", None)
    if effects is None:
        return out
    for uid, effs in (getattr(effects, "by_unit", None) or {}).items():
        for e in (effs or ()):
            if int(getattr(e, "effect_type", -1) or -1) != WEB_EFFECT:
                continue
            src = getattr(e, "source", None)
            if src is not None and int(src) == int(source_id):
                out.append(int(uid))
                break
    return out


class WhisperingWebAbility(TriggeredAbility):
    """`On(0x26 = NormalAttack) & IsRangedAttack & get_OwnerIsCaster & AreEnemies(Target, Caster)`
    -> `RemoveEffect(<toiles posees par Lhykhis>) + AddBondEffect(1579, Target)`.

    OBSERVABLE : apres chaque attaque normale A DISTANCE de Lhykhis sur un ennemi, la cible porte
    1579 et la cible precedente ne la porte plus."""
    event_id = int(EventTriggerType.NormalAttack)              # `On(0x26)`
    TRIGGERED_ABILITY_ID = WHISPERING_WEB                      # 0x62a = 1554

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner_id = int(self.owner_id)
        # `get_OwnerIsCaster` : le porteur du passif est l'auteur de l'attaque normale.
        if int(getattr(ev, "actor_id", -1)) != owner_id:
            return False
        # `IsRangedAttack` -- le natif conjoint ce predicat, donc une attaque de MELEE de Lhykhis
        # ne pose RIEN. Tri-etat : canal non renseigne -> on ne pose pas (restrictif, jamais
        # une pose inventee).
        if getattr(ev, "ranged", None) is not True:
            return False
        # `AreEnemies(Target@+0x60, Caster@+0x48)`.
        tc = _owner_component(state, getattr(ev, "target_id", None))
        oc = _owner_component(state, owner_id)
        if tc is None or oc is None or tc.team is None or oc.team is None:
            return False
        return tc.team != oc.team

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        owner_id, target_id = int(self.owner_id), int(ev.target_id)
        # Le `RemoveEffect` de TETE porte sur les PORTEURS des toiles deja posees par Lhykhis --
        # pas sur la nouvelle cible. On resout la liste AVANT la pose, sinon on retirerait
        # aussitot ce qu'on vient d'ajouter.
        precedents = [u for u in webs_placed_by(state, owner_id) if u != target_id]
        retirees = []
        for uid in precedents:
            ent = entities_from_state(state, owner_id, owner_id, actor_id=owner_id)
            ent.target = {"id": uid}
            RemoveEffect(WEB_EFFECT, Target()).execute(ent, ectx)
            retirees.append(uid)
        # `AddBondEffect(0x62b, AbilityStateReference, source = Caster@+0x48,
        #                targets = Target@+0x60, bondWith = Caster@+0x48, turns = default)`.
        ent = entities_from_state(state, owner_id, owner_id, actor_id=owner_id)
        ent.target = {"id": target_id}
        AddBondEffect(WEB_EFFECT, EffectType.WhisperingWeb.name, Caster(), Target(),
                      duration_rounds=None, bonded_ref=Caster()).execute(ent, ectx)
        return {"ability": TriggeredAbilityType.WhisperingWeb.name, "owner": owner_id,
                "target": target_id, "removed_from": retirees, "dsl": True}
