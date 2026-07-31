# case-339 — les deux `// 2` residuels de #333 : deux artefacts NATIFS DIFFERENTS

WIP — RE en cours.

## 1. Site (a) `engine/playbook/fury_of_the_ancients.py:103`

L'artefact natif n'est **PAS** `AActiveAbility$$MinMaxDamageAverage` (attribution heritee de #333 §7).

Chaine lue au decompile `rnca9r7q6c` :

```
IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction
  -> <Ability>$$GetDamage(abilityState)            (corps dedupe = BaseTriggeredAbility$$MinMaxDamage)
  -> IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage
       = IdunBattleLogic.Entities.DSLFormulas$$RandomAmount(minDmg[0xc], maxDmg[0xd])
  -> IAmountFormula slot 4 = CalculateAverage
  -> IdunBattle.DSL.AAmountFormula$$CalculateAverage
```

TODO : conclusion + confrontation live.

## 2. Site (b) `engine/ai/action_generators.py:417-418`

`IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealAmountForPrediction`
= `PercentageOf(DamagePredictionFormula(...), ConfigVar 0x4b, roundUp=1)`, et
`IdunBattle.Entities.Formulas.DamagePredictionFormula$$Calculate` se termine par
`IdunBattle.Core.Services.MinMaxDamage$$Avg(prediction+0x40)` — donc le FOYER de #333.

TODO : conclusion + confrontation live.
