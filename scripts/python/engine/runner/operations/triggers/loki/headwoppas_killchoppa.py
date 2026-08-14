"""`HeadwoppasKillchoppa_ExtraDmg` (`EffectType` 0x620 = 1568) -- le COMPTEUR de l'owner-effect de
la relique `R_Crit_HeadwoppasKillchoppa` d'`orksWarboss` << Gulgortz >>. Tache #1012-r1.

La classe d'effet (les DEUX pattes de degat, la magnitude, l'`ActiveCondition`, et la RE complete
de la pose au niveau 0) vit dans `engine/entities/effects/loki/headwoppas_killchoppa.py`. Ce
module-ci ne porte QUE le `Triggered()` interne.

`IdunBattle.Entities.Effects.Loki.HeadwoppasKillchoppaEffect$$CreateHandleTriggerAbilitiesInternal`
-- MIRROR du decompile, ArraySet d'UN SEUL element ::

    DSLFactory.Triggered(
        trigger   = BaseEffect$$On( 0x36 = 54 EventTriggerType.UnitDefeated )
                  & NOT IsSteppableUnit( Targets@DSLSelectors+0x60 )
                  & AreEqual( DSLSelectors$$Attacker(), Owner@DSLSelectors+0x30 ),
        behaviour = IncreaseEffectLevel( Owner@+0x30, <this.effectType @+0x10> = 1568,
                                         amount = null, max = null ),
        null )

TROIS lectures, et aucune ne se devine :

1. **`amount = null` vaut `Direct(1)`** -- `IdunBattleLogic.Entities.DSLBehaviors$$IncreaseEffectLevel`
   substitue `<DSLFormulas+0x20>` quand l'argument est nul, et
   `IdunBattleLogic.Entities.DSLFormulas$$.ctor` construit ce champ avec `(1, 0)` (`+0x18` = 0,
   `+0x20` = 1, `+0x28` = 2, `+0x30` = 100, `+0x38` = -1).
2. **`max = null` => AUCUN CAP** -- le clamp d'
   `IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute` est desactive quand `max` n'a pas
   de valeur. Contraste explicite avec `Neuroparasite`, qui, lui, ecrit `$$GetMaximumLevel`.
3. **IL N'Y A QU'UNE INSTANCE D'EFFET, donc un seul compteur.** `AddEffect` a pose l'effet sur
   `targets = Owner` (Gulgortz seul) ; `CreateTargetSelector` ne pose rien, il liste les unites
   AFFECTEES (evalue par `IdunBattle.Entities.Effects.BaseEffect$$GetTargets`). Et
   `IncreaseEffectLevel(Owner@+0x30, ...)` descend a `DSLSelectors$$EffectFromOwner(owner, type)` :
   c'est l'instance DONT GULGORTZ EST PROPRIETAIRE qui monte. => **seuls les kills du PORTEUR
   comptent**, et le niveau obtenu sert Gulgortz ET ses Ork Boyz.
   ⚠ `docs/rl/case-1012-reliques-tau-et-orks.md` SS 2.2 dit l'inverse (<< chaque recipiendaire a SA
   propre instance ; un Ork Boy qui tue monte SON niveau >>) : c'est FAUX, et la case-doc est
   corrigee dans le meme commit.

⚠ **`Attacker()` N'EST PAS `Actor` -- mais l'ecart est INERTE ici, et c'est LU.**
`IdunBattleLogic.Entities.DSLSelectors$$Attacker` construit

    UnobscuredEntitiesSelector( state,
        cond = AreEqual( TriggeringAbility@DSLSelectors+0x98,
                         DirectAbilitySelector( AbilityOrEffect(0x434) ) ),
        ParentSelector( state, <DSLSelectors+0x48> ),      # si la cond tient : le PARENT
        <DSLSelectors+0x48> )                              # sinon : l'acteur

Le littéral `0x434` est RELU AUX OCTETS (`ba 34 04 00 00`, le pseudo-C le perd) : **1076 =
`ActiveAbilityType.MV71SniperDroneSquadAttack`** -- le tir du drone sniper Tau, dont le kill est
attribue a son SUMMONER. Aucun regime accessible a Gulgortz ne passe par cette ability, donc
`Attacker() == Actor` partout ou cet effet vit : le port lit `ev.actor_id`, et l'ecart est NUL,
pas seulement << non mesure >>.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Target
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggers import HasTrait
from ....abilities.behaviours.context import entities_from_state
from ....components import UnitComponent
from ....state import State
from ..base import EffectTrigger, TriggerEvent

#: `EffectType` 0x620 = 1568 -- l'effet PORTEUR de ce trigger (`this.effectType @+0x10`).
HEADWOPPAS_KILLCHOPPA_EXTRA_DMG = int(EffectType.HeadwoppasKillchoppa_ExtraDmg)
#: `NOT IsSteppableUnit( Targets@DSLSelectors+0x60 )` -- noeud DSL du foyer partage (meme
#: construction que `helspear.py` / `ecstatic_slaughter.py` sur le MEME evenement). Passer par le
#: noeud plutot que par `ctx.traits` est ce qui garde VOYANT un cadavre charge sans `StatsComponent`.
_TARGET_IS_STEPPABLE = HasTrait(Target(), int(UnitTrait.Steppable))


class HeadwoppasKillchoppaIncreaseLevelOnKill(EffectTrigger):
    """`Triggered()` unique de
    `...HeadwoppasKillchoppaEffect$$CreateHandleTriggerAbilitiesInternal` : +1 niveau a l'instance
    1568 de Gulgortz par unite non-`Steppable` qu'il abat, SANS cap."""

    event_id = int(EventTriggerType.UnitDefeated)          # 0x36 = 54
    effect_type = HEADWOPPAS_KILLCHOPPA_EXTRA_DMG

    def _victim(self, ev: "TriggerEvent"):
        """`Targets@DSLSelectors+0x60` sur un evenement MORT : `dying_id` (slot 0x178) quand il est
        threade, `target_id` sinon -- meme lecture que `helspear.py`."""
        return ev.dying_id if ev.dying_id is not None else ev.target_id

    def _instance(self, state: "State"):
        """L'instance 1568 DONT LE PORTEUR EST PROPRIETAIRE -- mirror de
        `DSLSelectors$$EffectFromOwner(Owner@+0x30, this.effectType)`."""
        if state.effects is None:
            return None
        for e in state.effects.by_unit.get(int(self.owner_id), []):
            if not e.consumed and e.effect_type == HEADWOPPAS_KILLCHOPPA_EXTRA_DMG:
                return e
        return None

    def matches(self, state: "State", ev: "TriggerEvent") -> bool:
        """Les TROIS conjoints du `CreateTrigger`, dans l'ordre du decompile.

        ⚠ **AUCUN gate `IsActive`** : ce trigger vient de `CreateHandleTriggerAbilitiesInternal`,
        donc du rail `EvaluateEffectTriggerEffectAbilities`, qui n'accede JAMAIS a
        `EffectComponent+0x5c` (case-229). Le gater sur `IsActive` GELERAIT le compteur a zero pour
        toujours -- l'effet naît INACTIF (niveau 0) et ne s'active QUE parce que ce trigger le fait
        monter. C'est la difference exacte avec `BloodChaliceHealOnMeleeAttack`, qui vient de
        `CreateTargetTrigger` et porte le gate, lui."""
        # `AreEqual( Attacker(), Owner@+0x30 )` -- cf. l'en-tete : `Attacker() == Actor` dans tout
        # regime accessible a ce porteur.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        owner = state.get_entity(int(self.owner_id))
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:
            return False
        victim = self._victim(ev)
        if victim is None or int(victim) == int(self.owner_id):
            return False
        if state.get_entity(int(victim)) is None:
            return False
        # `NOT IsSteppableUnit( Targets@+0x60 )`
        entities = entities_from_state(state, int(self.owner_id), int(victim),
                                       actor_id=ev.actor_id)
        return not _TARGET_IS_STEPPABLE.should_trigger(entities)

    def execute_behaviour(self, state: "State", ev: "TriggerEvent") -> Optional[dict]:
        """`IncreaseEffectLevel( Owner@+0x30, 1568, amount = Direct(1), max = null )`.

        L'arbre natif vise l'instance par `EffectFromOwner`, une seule cible : on incremente
        directement l'instance du porteur au lieu de re-monter un selecteur a un element -- meme
        arbitrage que `BloodChaliceHealOnMeleeAttack`, qui appelle `HealUnitOperation` en direct.
        Le clamp d'`IncreaseEffectLevelOperation$$Execute` est INOPERANT (`max = null`), donc il n'y
        a rien a mirrorer de ce cote."""
        inst = self._instance(state)
        if inst is None:
            return None                                    # aucune instance -> le natif n'ecrit rien
        inst.level = int(inst.level or 0) + 1               # amount = <DSLFormulas+0x20> = Direct(1)
        return {"effect": "HeadwoppasKillchoppa_ExtraDmg", "owner": self.owner_id,
                "victim": self._victim(ev), "level": inst.level}
