# #985 — « pas d'entrée à son nom » n'est pas « config introuvable »

**Le fait.** `#970-r2` déclarait la face DÉCISION de `1160 HeavyRailRifle` **structurellement
bloquée** (`BLOCAGE: seeding`) sur cette prémisse : *« `HeavyRailRifle_Attack` est ABSENTE du
gameconfig (572 abilities indexées, seul `HeavyRailRifle` y figure), donc ni `minDmg`/`maxDmg` ni
`nrOfHits` du TRIGGERED ne sont lisibles offline — or c'est cette config-là que le playbook
évalue, pas celle de l'active. »*

La prémisse est **fausse**, et sa moitié vérifiable est **vraie** — c'est ce qui la rendait
convaincante. `HeavyRailRifle_Attack` est bel et bien introuvable dans les **deux** substrats
(gameconfig **et** seed BC, qui ne porte même aucune section `TriggeredAbilities`). Mais elle
confond deux choses : « l'ability n'a pas d'entrée **à son nom** » et « la config qu'elle **LIT**
est introuvable ». Un triggered n'a pas nécessairement de config propre : il partage
l'`AbilityConfiguration` de son **active parente**.

**Ce qui tranche, et pourquoi ce n'est pas circulaire.**
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility$$GetFinalUnitDamageAmount`
lit, sur son `this@+0x20`, `IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(0x4c)` et
`ConfigConst(0xf)` — soit `dmgPctReduction` et `extraDmgPct`. Une concordance de noms ne prouve
rien si les noms sont ubiquitaires : l'étage décisif est la **spécificité**.

| mesure | valeur |
|---|---|
| abilities indexées | 572 |
| portant `dmgPctReduction` | 6 (1,0 %) |
| portant `extraDmgPct` | 8 (1,4 %) |
| portant **les deux** | **1** — `HeavyRailRifle` |

L'appariement est **unique**. ⇒ le triggered lit la config de l'active, et `minDmg` / `maxDmg` /
`nrOfHits` / `damageProfile` sont lisibles offline. Mesure :
`scripts/python/probe_985_config_du_triggered.py` (4 étages) ; garde :
`scripts/python/tests/engine/test_985_faces_decision_offline.py`, qui **assertionne l'unicité**
elle-même — si ces constantes se banalisaient, la réfutation changerait de forme.

**Le corollaire d'outillage.** La ligne du call-site
`IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$EvaluateNonComparable → (GetDamage, 4)`
existait **déjà** dans `TRIGGERED_PREDICTION_AVERAGE_FORM` (#350-r3b) et n'avait **aucun
consommateur**. Une entrée de registre sans consommateur ne signale pas qu'elle est utilisable :
elle a coexisté avec une fiche déclarant le port impossible.

**Ce qui bloquait vraiment, et n'était pas ce qu'on croyait.** Le second bloqueur nommé en
passant par `#970-r2` (« mineur ») est le seul réel : `IdunBattle.Entities.EntityExtensions$$IsMachine`
= `GetEntityType(entity) == EntityType.Machine (6)`, et ce type n'a **aucun canal côté DÉCISION**
(une Machine n'est jamais dans `decisionView.units` — elle vit dans `.mows`). Contourné en
dérivant le prédicat du gameconfig par `mythicAbilities` : **11** unités désignées, exactement le
compte de Machines of War du build, **0 faux négatif** sur les 8 du pool spawnable.

**L'écart assumé.** `IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$ShouldPreferMachine`
= `pseudoRNG.<slot 5 = NextBool>(50)`, un tirage à 50 % qui ne gouverne **que** la branche
`IsMachine(cible)` (utilité `int.MaxValue` ou `1`). Le port prend la face **déterministe** et le
dit. Conséquence pratique : sur un montage sans cible Machine, le port est intégralement
déterministe — c'est le régime confrontable.

**La leçon transférable.** Une prémisse de blocage se re-mesure **par ses étages**, pas par son
verdict. Celle-ci portait un fait vrai (l'absence) et une inférence fausse (l'illisibilité), et
seule la décomposition les sépare. Voir aussi `case-970-*` pour la RE d'origine, et
`docs/rl/case-350r3b-moyennes-triggered.md` pour le registre des formes de moyenne.
