"""engine.utilities — réimplémentation FIDÈLE des leaf-utilities natives `IdunBattle.AI.Utilities`,
UNE CLASSE `*Utility` par `UtilityType` (nom natif), dont `evaluate(...)` porte le corps de son
`*Utility.<Evaluate*InSteps>d__N.MoveNext` (ghidra gqfc5mff6c) + poids `BattleConfiguration.Utilities`.

Le composite à scorer (Damage=35, Tile=7) = INSTANCE `ComposedUtility` (SOMME de ses feuilles ; ce ne
sont PAS des classes dédiées). La MEMBERSHIP exacte est LUE À L'EXÉCUTION (RPC `dumpComposedUtility`,
doc §13.8) — pas devinée. cf. docs/rl/playbook-engine.md §13.7 / §13.8 / §13.9.

Base + enum : `base.py` (BaseUtility/ComposedUtility), `utility_type.py` (enum UtilityType, dump.cs).
Wrappers minces `tile_composite`/`damage_composite` conservés pour les appelants existants.
"""
from __future__ import annotations

from .damage import damage_composite  # noqa: F401
from .tile import tile_composite  # noqa: F401
from . import move  # noqa: F401  -- ENREGISTREUR : l'import EST l'effet (registre)
