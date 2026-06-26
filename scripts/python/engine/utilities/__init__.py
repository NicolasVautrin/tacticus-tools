"""engine.utilities — réimplémentation FIDÈLE des leaf-utilities natives, une fonction par
`UtilityType`, portée depuis son `*Utility.<Evaluate*InSteps>d__N.MoveNext` (ghidra gqfc5mff6c)
+ poids `BattleConfiguration.Utilities` (BC JSON).

Le composite à scorer (ex. Damage(34), Tile(7)) = SOMME de ses feuilles. La MEMBERSHIP exacte est
LUE À L'EXÉCUTION (RPC `dumpComposedUtility`, doc §13.8) — pas devinée. cf. docs/rl/playbook-engine.md
§13.7 (DamageUtility) / §13.8 (composition runtime) / §13.9 (plan de portage).

Principe : chaque leaf = `f(pred|tile|ctx) -> float` sur la MÊME devise Fix64 que le natif (pas de
knob de scale ; les constantes sont LUES, ex. W_damage=80, W_remaining=20).
"""
from __future__ import annotations

from .damage import damage_composite, damage_dealt, kill_unit, overkill_unit  # noqa: F401
from .tile import tile_composite, TILE_LEAVES, TILE_LEAF_IDS  # noqa: F401
