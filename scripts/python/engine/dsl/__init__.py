"""Socle DSL = les 4 BASES de famille (mirror `IdunBattle.DSL`) : `AAmountFormula`/`AbilityTrigger`/
`TargetsSelector` (LAZY, base.py) + `AbilityBehaviour` + infra walker (`OperationResult`/
`ExecutionContext`, effects.py). Les NOEUDS CONCRETS vivent dans leur namespace natif
`entities/{formulas,triggers,selectors,behaviours}` et se construisent via la FACADE `DSLFactory` =
`dsl/nodes.py` (importee `as dsl` par les abilities/prediction). cf. nodes.py.

NB (cycle) : ce `__init__` n'importe QUE base + effects (feuilles, sans dep `entities/`) -> importer
`engine.dsl.base` depuis `entities/*` ne re-declenche PAS la facade -> pas de cycle d'import.
"""
#: RE-EXPORT GARDE -- `DslContext` est lu par ACCES ATTRIBUTAIRE (`from .. import dsl` puis
#: `dsl.DslContext`) dans `playbook/tile_targets.py`, `playbook/loki_custom.py`,
#: `playbook/resurrection_orb.py`, plus un probe et un test live. Cette voie ne laisse aucune
#: trace dans un recensement d'`ImportFrom` : #485-r1-r1 l'a videe et les trois modules du
#: MOTEUR levaient un `AttributeError` a l'appel, sans qu'aucun test tombe le montre.
#: Cliquet : `probe_485r1r1_acces_attributaires.py`.
from .base import DslContext  # noqa: F401
