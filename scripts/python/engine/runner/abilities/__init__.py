"""`engine.runner.abilities` — abilities ACTIVES portées 1:1 (`IdunBattleLogic.Entities.Abilities.Active.*`).

Une ability active native a une `ExecuteBehaviour` qui BÂTIT une behaviour-seq DSL (attaque + AddEffect +
déplacements…) que le pipeline d'operations exécute. Côté Python on porte CHAQUE ability comme une classe
(1:1, VA citée) dont `execute_behaviour(state, caster_id, target_id)` appelle DIRECTEMENT les operations
portées dans le MÊME ordre que le DSL natif — fidèle au niveau ability, sans réimplémenter l'interpréteur
DSL générique. C'est le « wiring ability-exec » : `Runner.apply(ActiveAbilityMessage(...))` → l'engine
DÉRIVE les effets posés (au lieu d'un appel direct à AddEffectOperation).

`ABILITY_CLASSES` = registre `ActiveAbilityType (int) -> classe`. `AbilityHandler` (visiteur post) route
`ActiveAbilityMessage` → l'ability → `execute_behaviour`.
"""
from __future__ import annotations

from . import loki  # noqa: F401  -- ENREGISTREUR : l'import EST l'effet (registre)

__all__ = []
