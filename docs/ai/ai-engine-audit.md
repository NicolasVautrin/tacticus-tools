# Audit du moteur IA — WH40K Tacticus

Audit réalisé par décompilation Ghidra du build IL2CPP. Sur Tacticus
**Android** (initial) : `libil2cpp.so` ARM64 → `data/decompiled_tacticus/`
(1877 méthodes IA). Sur Tacticus **PC** (cible actuelle) :
`GameAssembly.dll` x86_64 → `sources_win/` (cf. `decompilation.md`).

La logique IA est identique sur les 2 plateformes (même C# managed code) ;
seules les RVA et la calling convention diffèrent. Les findings de cet
audit restent valables pour le port PC.

## Architecture

Systeme **utility-based greedy sequentiel**. Chaque unite est evaluee independamment, dans un ordre heuristique. Pas de planification multi-unites, pas de lookahead.

## Boucle principale

```
AutomaticBattleRunner.Run()
  └── while (match.Stage != 2 && turn < maxTurns) :
        aiControl.CalculateNextActionForPlayer(currentPlayer)
          └── DefaultPlayerStrategy
                └── DefaultGroupOperator
                      ├── PickNextUnit — ordre via UnitPicker utilities
                      └── pour chaque unite (sequentiel) :
                            ├── CalculateNextActionForUnit
                            │     ├── GenerateActionTiles → positions atteignables
                            │     ├── ActionGenerators : move × ability combos
                            │     ├── Playbooks : score chaque combo
                            │     └── meilleure action (score max)
                            ├── runner.Apply(messages) ← board mis a jour
                            └── unite suivante voit le board modifie
```

Chaque unite joue, puis le board est mis a jour avant l'unite suivante.

## UnitPicker (10 utilities) — ordre de jeu

Determine quelle unite joue en premier :

| Utility | Critere |
|---------|---------|
| ShortestPathToEnemyUtility | Plus proches de l'ennemi d'abord |
| PreferAbilitiesUtility | Ability prete |
| MinPossibleNormalAttackTargetUtility | Moins de cibles = plus urgent |
| PreferFreshlySpawnedUtility | Nouvelles unites en priorite |
| PreferNonBossUtility | Non-boss d'abord (boss joue en dernier) |
| LastAbilitiesUtility | Abilities qui vont expirer |
| PreferSummonsAndObjectsUtility | Invocations et objets |
| RandomUtility | Bruit aleatoire |
| RemainingUtility | Unites restantes |
| UnitOrderUtility | Ordre pre-defini |

## ActionGenerators — generation d'actions

Pour chaque unite, genere les combinaisons (position, ability) :

| Generator | Role |
|-----------|------|
| MovementActionGenerator | Deplacements + attaque normale |
| ActiveAbilityActionGenerator | Abilities actives |
| LokiBossActiveAbilityActionGenerator | Boss Loki specifique |
| RandomAbilityActionGenerator | Aleatoire (certains boss) |

## Playbooks (50+) — scoring des abilities

Chaque ability a un playbook dedie qui implemente `EvaluateInternal` (virtuel).

**Flow :**
```
PlaybookDatabase.LoadPlaybook(abilityType)
  → cache hit ? retourner
  → sinon : builder() → playbook.Init(dependencies) → cache
BasePlaybook.Evaluate(caster, position, utility)
  → DSL.SetDisallowRandom()
  → GetAbilityState(caster)
  → EvaluateInternal(caster, pos, abilityState, utility)  ← virtuel
  → DSL.SetAllowRandom()
  → retourne Bucket<UnitAction> (actions scorees)
```

**Playbooks par ability (exemples) :**

| Playbook | Logique |
|----------|---------|
| HealPlaybook | score = healAmount; ne heal pas soi-meme sauf boss |
| DefaultActiveAbilityPlaybook | score base sur damage prediction |
| ArcScourgePlaybook | score = damage × ennemis touches |
| BlightGrenadesPlaybook | grenades de corruption |
| CloudOfFliesPlaybook | nuage de mouches |
| PlagueburstMortarPlaybook | mortier a longue portee |
| SanguinaryPriestPlaybook | pretre sanguinaire |
| RepairPlaybook | reparation de machines |

## Utilities (70+) — scoring du positionnement

Score de chaque tile pour le mouvement. La decision finale combine playbook + utilities.

### Offensif

| Utility | Role |
|---------|------|
| DamageUtility | Degats estimes |
| KillUnitUtility | Bonus pour kill |
| OverkillUnitUtility | Bonus overkill |
| MinDistanceToClosestEnemyUtility | Se rapprocher |
| AttackTargetWithEffectUtility | Bonus attaque avec effet |
| ContaminatedUtility | Zone de degats |
| RammingSpeed_MostAdjacentEnemies | Foncer dans le tas |

### Defensif

| Utility | Role |
|---------|------|
| MaxDistanceToEnemiesUtility | Fuir (ranged units) |
| NoMovementToTileWithAdjacentEnemiesUtility | Eviter la melee |
| RangedAdjacentEnemyUtility | Penalite ranged en contact |
| ElevationUtility | Preferer les hauteurs |
| RoyalGuard_AvoidAdjacentEnemiesUtility | Gardes royaux fuient le contact |
| SwornProtector_AvoidAdjacentEnemiesUtility | Protecteurs aussi |
| PreferMovementAwayFromTargetUtility | Reculer strategiquement |

### Support

| Utility | Role |
|---------|------|
| HealUtility | Se rapprocher des blesses |
| RepairedAmountUtility | Reparation |
| DefenderOfTheGreaterGoodUtility | Proteger les allies |
| SaviorProtocolsUtility | Sauvetage |

### Tactique / Terrain

| Utility | Role |
|---------|------|
| CapturePointTileUtility | Capturer les objectifs |
| TileEffectsUtility | Eviter zones dangereuses |
| PowerUpTileUtility | Power-ups |
| EnemyOnTerritoryUtility | Controle de territoire |
| TileDistanceUtility | Gestion des distances |

## Strategies alternatives

| Strategie | Usage |
|-----------|-------|
| DefaultPlayerStrategy | IA principale |
| EnvironmentPlayerStrategy | Joueur "environnement" (pieges, terrain) |
| WithSomeRandomnessStrategy | Ajoute du bruit au scoring |
| RandomAIUnitTactic | Actions aleatoires |
| SkipTurnAiUnitTactic | Passe le tour |
| OnlyMoveAiUnitTactic | Mouvement seul |
| LokiBossAiUnitTactic | Boss Loki specifique |

## Score final

```
score_action = playbook.EvaluateInternal(caster, position, abilityState, utility)
             + sum(utility_weight * utility_score pour chaque tile)
```

L'IA choisit l'action au score le plus eleve.

## Faiblesses identifiees

1. **Greedy sequentiel** — chaque unite optimisee seule, pas de coordination
2. **Pas de lookahead** — ne simule pas la reponse de l'adversaire
3. **Ordre fixe** — l'ordre de jeu (UnitPicker) est heuristique, pas optimise
4. **Pas de synergie** — unite A ne cree pas d'ouverture pour unite B

## Fichiers decompiles

```
data/decompiled_tacticus/
├── IdunBattle/AI/
│   ├── DefaultPlayerStrategy.c
│   ├── PlaybookDatabase.c
│   ├── ActionGenerators/             — generation d'actions
│   ├── OperationalDeciders/          — orchestration des groupes
│   ├── Playbook/                     — 30+ playbooks + coroutines mouvement
│   │   ├── BasePlaybook.c
│   │   └── Common/ (Heal, Repair, DefaultActiveAbility)
│   ├── Tactics/                      — tactiques + coroutines unite
│   ├── _CalculateNextActionForPlayer_d__*.c
│   └── _CalculateNextActionForUnit_d__*.c
├── IdunBattleLogic/AI/Utilities/     — 70+ utilities
│   └── UnitPicker/                   — 10 utilities d'ordre
└── Runner/AutomaticBattleRunner.c
```