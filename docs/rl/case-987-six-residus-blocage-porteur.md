# #987 — les six résidus `BLOCAGE: porteur`, re-mesurés

Un champ `BLOCAGE:` s'écrit à la fermeture d'une tranche, et **rien ne le re-mesure ensuite**.
Ce lot rouvre les six résidus `BLOCAGE: porteur` du dépôt en commençant par la **prémisse**, pas
par le montage.

## 0. Verdicts

| résidu | prémisse re-mesurée | issue |
|---|---|---|
| `#945-r1` | **FAUSSE au moment où elle a été écrite** — `AlphaWarriorPlaybook` n'est pas le seul consommateur du slot 195 | **fermé** — porté ET confronté live |
| `#952-r2` | **VRAIE, et définitivement** — aucun chemin de spawn ne peut produire le porteur | **fermé** — le régime n'existe pas dans le build |

## 1. `#945-r1` — la branche MACHINE OF WAR du slot 195

**Énoncé du résidu** : « `AlphaWarriorPlaybook` (1112) est le seul consommateur porté et son
porteur `tyranWingedPrime` n'est pas une MoW, donc la branche est INATTEIGNABLE par lui ».
La consigne qu'il donnait — « vérifier s'il existe un playbook de summon à porteur MoW » — se
tranche en **deux requêtes**, et elle était déjà tranchée.

**Les consommateurs de `GetSummonId`, par les XREFS entrantes** (pas par grep de nom) :
`IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$GetSummonId` est le corps
DÉDUPLIQUÉ, et il a **deux** appelants — `IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$EvaluateNonComparable`
**et `IdunBattle.AI.Playbook.Loki.ForwardSpotterPlaybook$$EvaluateNonComparable`**. Le second
appelle le même slot `0xc3 = 195` (`FUN_180005420(0xc3, <IBattleQuery>, query, caster, summonId, tile)`),
après un slot `0x4f` qui énumère les tuiles.

**Le porteur de `1143 ForwardSpotter` est `astraOrdnanceBattery`** (Malleus Rocket Launcher),
`kind: lineup`, **trait `MachineOfWar`** — lu au gameconfig, pas déduit. C'est donc la SEULE
branche qu'il emprunte : `EntityExtensions.IsMachine(parent)` est vrai à chaque évaluation.

⇒ La branche n'est pas seulement atteignable : elle est **portée depuis #967**
(`engine/playbook/noncomparable/summon_attack_range.py`, foyer des deux branches, `machine_parent`
en paramètre) **et confrontée live** (#967-r5 : seed 777 / MC1_67, step 11 `natif ab=1143 tgt=84`,
MISS → MATCH). Le port est fidèle au décompilé
`IdunBattle.Core.Services.BattleQuery$$HasSummonTargetInAttackRangeAtTileWithMachineParent` :

```
player  = EntityExtensions.GetOriginalPlayer(machineParent, state)   ; null -> throw
enemies = GetAllEnemiesOf(player.Id)                                 ; null -> throw
foreach target in enemies:
    if (IsTargetInAttackRangeForSummon(machineParent, unitId, tile, target)) return true
return false
```

**Un écart subsiste et il est nommé** : le port itère `ctx.enemies` (les ennemis du point de vue du
caster) là où le natif passe par `GetOriginalPlayer(machineParent)` → `GetAllEnemiesOf(player.Id)`.
Les deux coïncident tant que la MoW n'a pas changé de camp ; sous une possession, le natif garderait
les ennemis du propriétaire **d'origine**, le port ceux du propriétaire courant. Écart théorique :
aucune ability du build ne retourne une MoW.

## 2. `#952-r2` — `GalvanicField` sans filet de spawn

**Énoncé du résidu** : « un `admecManipulus` matérialisé SANS capture n'aurait ni le flag ni
l'échange d'ability, mais aucun chemin de spawn ne le produit aujourd'hui ». Ce n'est pas un défaut
de recherche : c'est **mesurable exhaustivement**, et la mesure ferme la question.

**Les porteurs de `GalvanicField`, toutes voies du gameconfig** — 6, et **un seul lineup** :
`admecManipulus`, plus ses cinq variantes boss `npc` (`admecBossManipulus`, `…LEG`, `…LHE`, `…CE`,
`…Surv`).

**Les 117 `constants.unitId` du gameconfig qui désignent une unité connue** — balayage exhaustif de
`activeAbilities` ∪ `passiveAbilities` : **aucun** ne désigne `admecManipulus` ni aucune de ses cinq
variantes. Aucune ability ne l'invoque.

**Trois `PowerUp_HeroSpawn_*` spawnent bien un héros de LINEUP** en cours de bataille
(`custoVexilusPraetor`, `custoBladeChampion`, `votanUthar`) — c'est le seul chemin du build qui
matérialise une unité de lineup après le seed. `admecManipulus` n'en fait pas partie ; et sur les
**779 boards** de `data/boards/`, **zéro** cite un `PowerUp_HeroSpawn_*` ou un
`PowerUp_SummonSpawn_*` (le seul token `PowerUp*` présent est la clé `PowerUpUnits`).

**Le passif ne peut pas non plus se re-déclencher** :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GalvanicFieldAbility` porte **`CreateBehaviour`
et rien d'autre** — aucun `CreateTrigger`, donc aucune ré-application en cours de bataille. Ses
trois feuilles s'exécutent une fois, au `UnitFactory`, donc **toujours avant** la capture.

⇒ Le régime « `GalvanicField` appliqué hors capture » **n'existe pas dans ce build**. Écrire le
filet de spawn serait un port dont aucun chemin de jeu ne peut exercer la différence. Ce qui reste
vrai et ne justifie pas un port : un TEST pourrait vouloir construire l'état sans capture — c'est
un besoin d'outillage, pas un régime.
