# case-445 — `AvalancheOfMuscle` (1028), face PLAYBOOK ATTACK

Quatrieme des 20 residus ATTACK de `case-419` §7. **RE EN COURS** — ce fichier sera reecrit a
l'etat final avant la PR.

## 0. Le piege du nom, leve

`1028` a deja une entree cote EFFET (`engine/entities/effects/factory.py`, jumeau de
`FeederTendrils`). Le residu vise ici est la face **PLAYBOOK ATTACK**, artefact different :
`IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook`.

## 1. Le corps natif (decompile lu)

`IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook$$CalculateAttackUtilityInStepsInternal`
monte la SM `d__2` (case @+0x20, playbook @+0x28) ; corps =
`AvalancheOfMusclePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`.
SEPT etats de yield.

(en cours de redaction)
