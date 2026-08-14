"""engine.entities.rarity -- enum natif `idun.meta.Rarity` (rarete d'une unite EN BATAILLE).

Mirror 1:1 d'`idun.meta.Rarity`, transcrit depuis la table de symboles VERSIONNEE du build
(`data/symbols/<build>/frida/enums.tsv`). Meme precedent que `UnitFaction` / `UnitTrait` : un enum
natif standalone -> son propre module, foyer unique du mapping.

⚠ CINQ enums du build ont EXACTEMENT ces six membres aux memes ordinaux -- `idun.meta.Rarity`,
`IdunMetaLogic.UserProgress.Model.UnitRarity`, `...ItemRarity`, `...UpgradeRarity`,
`...XpBookRarity`. Se tromper d'appariement serait donc SILENCIEUX EN ORDINAL, et c'est
exactement pourquoi le nom PLEIN est ce qu'on inscrit au registre de `probe_313`.

**Celui que le COMBAT lit est `idun.meta.Rarity`**, et c'est LU dans `frida/methods.tsv` au TYPE
DECLARE du parametre -- jamais deduit du nom court. Trois foyers concordants :

    IdunBattleLogic.Entities.DSLSelectors.UnitsWithRarity   rarity:idun.meta.Rarity
    IdunBattleLogic.Entities.DSLTriggers.HasRarity          rarity:idun.meta.Rarity
    IdunBattle.Entities.UnitExtensions.HasRarity            rarity:idun.meta.Rarity

(`docs/rl/case-1024-shield-of-faith-on-my-position.md` §4 nomme `...Model.UnitRarity` : cet enum
existe bien, mais c'est l'enum META -- ce n'est pas celui que les gates de bataille prennent.)

SUBSTRAT DE LA VALEUR, et pourquoi ce module ne suffit PAS a armer un gate :
`IdunBattle.Entities.UnitExtensions$$HasRarity(unit, rarity)` et
`IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` lisent tous deux
`IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent(e)` puis comparent son champ `+0x74`.
Ce champ n'est publie par AUCUN RPC (`observeBattle`, `combatSnapshot`, `decisionView`) -- mesure
`docs/rl/case-1024-shield-of-faith-on-my-position.md` §4, re-verifiee pour #1036. Ce module donne
donc le VOCABULAIRE (l'ordinal nomme), pas le CANAL : tant que le capteur n'est pas pose, aucun
gate de rarete n'est evaluable offline. Cf. `docs/rl/case-1036-mythiques-cabale-et-construct.md`.

⚠ NE PAS le seeder depuis `GC.unit(<id>)["BaseRarity"]` : c'est la rarete de BASE (chaine
`"Common"` pour des MoW qui sont Mythic en bataille), pas la rarete EFFECTIVE, qui depend de la
progression. Et ne pas le seeder depuis le `targetRarity = 5` que `rl_duel build` impose non plus :
ce serait vrai dans le regime par defaut du harnais et FAUX des qu'une unite est montee par
`--unit-stat "<vis>:Rarity=N"`.
"""
from __future__ import annotations

from enum import IntEnum


class Rarity(IntEnum):
    """`idun.meta.Rarity`. Valeur == valeur d'enum natif ; nom == nom natif verbatim."""
    Common = 0
    Uncommon = 1
    Rare = 2
    Epic = 3
    Legendary = 4
    Mythic = 5
