# #939 — `1144 BioMinefield` : l'audit annoncait un SUMMON, le natif en fait UNE BRANCHE SUR DEUX

Build `rnca9r7q6c`. Porteur : `tyranBiovore` (MoW **du pool**, `--list-pool` : 8 MoW spawnables).
Le second porteur, `tyranNpcMowBiovore`, est npc.

Etat avant : **NO-OP SILENCIEUX**. `AbilityHandler.ABILITY_CLASSES` ne connaissait pas 1144, donc
l'IA la choisissait et l'execution n'en faisait RIEN — zero degat, zero effet, aucune erreur.

## 1. Les faces, et leur verdict

| Face native | Verdict |
|---|---|
| `BioMinefieldAbility$$ExecuteBehaviour` | **VIVANTE** (vtable). Portee. |
| `$$AliveChildren` · `$$MoveChildren` · `$$AttackWithChildren` · `$$SpawnUnits` | **DEAD comme corps standalone** — seules xrefs = DATA (bloc `methodPointers` + metadata), **aucun `CALL`**. IL2CPP les a INLINEES dans `ExecuteBehaviour`, dont elles sont exactement les quatre sous-arbres. Relues : elles **corroborent** la structure, sous-arbre par sous-arbre. |
| `IdunBattle.AI.Playbook.Loki.BioMinefieldPlaybook` | **VIVANTE**, enregistree (`metadata/active_playbook_builders.tsv` : `active 1144`). Portee. |
| `IdunBattle.AI.Utilities.BioMinefield_MoveTowardsTargetUtility` | **DEJA PORTEE** (`UtilityType` 62, `TILE_LEAVES`). |
| `BioMinefieldVisuals` | Couche VUE, hors moteur. |
| `CreateTrigger` / `CreateBehaviour` / `Effect$$Create*` | **N'EXISTENT PAS.** L'effet `1315 BioMinefield_Target` n'a **aucune classe native** : c'est un marqueur, instancie par `AddEffectBehaviour` a partir de son seul `EffectType`, et son unique lecteur est la feuille d'utilite 62. |

**La colonne SUMMON de l'audit etait a moitie fausse** : le summon est la branche `else` d'un `If`.

## 2. L'arbre (17 primitives — recensement corrobore par `dsl-usage-owners.tsv`)

```
Execute(   AddEffect(EffectType.BioMinefield_Target, <abilityStateRef>,
                     source = Owner@DSLSelectors+0x30, targets = Target@+0x60,
                     turns  = <DSLFormulas+0x20> = Direct(1))
         & If( AmountIsEqualOrGreater(Count(Alive(Children(Owner))),
                                      Direct(GetNumberConstant(nrOfSummons))),
               then =   PerformAIMovement(EntitiesWithoutEffects(Alive(Children(Owner)),
                                              [EffectType.Taunted_BlockMovement]),
                                          Direct(1), <ability+0xf0 : UtilityDefinition>)
                      & Kill(Filter(Alive(Children(Owner)),
                                    HasAdjacentEnemies(Subject@+0x68, Tiles(Subject@+0x68),
                                                       false, false)),
                             <LE MEME selecteur>, 0),
               else =   Spawn(Caster@+0x48,
                              RandomAdjacentFreeTile(Target@+0x60,
                                  Direct(GetNumberConstant(nrOfSummons_2))),
                              GetStringConstant(unitId), WithStatsFromConfig(...)) ) )
```

Config LUE : `unitId = tyranSmnSporeMine`, `nrOfSummons = 3`, `nrOfSummons_2 = 3`.

**Toutes les surcharges ont ete tranchees par la CIBLE REELLE du `call`** (decodage des `E8 rel32`
du corps, resolus contre `ghidra/functions.tsv`), jamais par le pseudo-C : `AddEffect` a 6 args,
`AmountIsEqualOrGreater(amount, minAmount)`, `If(abilityTrigger, then, else)`,
`WithStatsFromConfig` a 4 args, `Get(amount)`, `Spawn` — 37 sites, dans l'ordre d'execution.

## 3. Les quatre lectures qui changent le port

1. **`DSLSelectors$$Children(parent)` est `ChildrenOf`, PAS `Children`** (piege #590). Deux
   primitives natives homonymes. Brancher celle sans argument rendrait un ensemble TOUJOURS VIDE au
   premier cast ⇒ condition toujours fausse ⇒ **branche `then` inatteignable**, sans erreur.
2. **`Kill(pvVar13, pvVar13, 0)`** — killer ET cibles sont **le meme sous-arbre** : les mines se
   tuent ELLES-MEMES. Le degat de l'explosion n'est pas dans 1144, il appartient au kit de
   `tyranSmnSporeMine`.
3. **`HasAdjacentEnemies` alloue le singleton d'`AmountIsEqualOrGreater`** (`DAT_1833d73e0`, le
   MEME que ses deux surcharges) — le nom `AmountIsGreaterAbilityTrigger` affiche par ghidra est un
   mislabel ICF. Le seuil est **`>= 1`** ; lire `>` rendrait le predicat faux pour exactement UN
   ennemi adjacent, le cas normal.
4. **Les deux formules de `WithStatsFromConfig` SONT son propre fallback.** La surcharge a 4 args
   delegue a celle a 5, dont le corps fait `if (abilitiesLevel == null) abilitiesLevel =
   new Direct(abilityState.<f0>)` (idem pour le multiplicateur). Or 1144 passe precisement
   `Get(abilityState.<f0>)` / `Get(abilityState.<f1>)` ⇒ **strictement identique** a
   `WithStatsFromConfig(config, abilityState, null, null)`, la forme que le defaut du port rend
   deja. Poser un `ability_state` explicite ferait croire a une divergence.

## 4. Confrontation LIVE (board MC1_67, seed 777, 2026-08-11)

`probe_939_bio_minefield.py`. **Le manque de munitions n'empeche pas le cast** : le terme munitions
de `get_CanCurrentlyBeUsed` est DECISION-ONLY (`SpendAmmoOperation$$Execute` echoue silencieusement
a stock nul, et `MachineOfWarAmmo` vaut 0 dans le seed BC). Sans cette lecture, le montage paraissait
impossible.

Mesure de la branche `else`, **concordante avec le port** :

* **3 mines** `tyranSmnSporeMine` (`nrOfSummons_2 = 3`), `Unit_Parent_Id = 81` (la MoW) ;
* leurs tuiles sont **adjacentes a la CIBLE** (cible (1,1) ; mines (2,0), (0,0), (2,1)) — pas au
  caster, qui n'a aucune tuile ;
* `BioMinefield_Target` sur la cible, `Effect_SourceId = 81`, `Effect_RemainingTurns = 1` ;
* les mines montent leur kit sous `Level = 50` / `VariableMultiplierPercentage = 150` = l'`AbilityState`
  du cast.

### Le faux positif qu'il a fallu ecarter

Un **second cast au tour suivant a RE-SPAWNE** au lieu de prendre `then`. Ce n'est **pas** une
divergence : entre les deux casts, les 3 mines avaient DISPARU — elles jouent au turn-start par
`PlayAutomaticUnitsOperation` (trait `Summon`, #291) et, posees adjacentes a la cible, explosent
immediatement (cible 9927 → 6419 PV, **−3508**). `Count(Alive(ChildrenOf(Owner)))` valait donc **0**
au 2e cast. Le natif a pris la bonne branche.

**Corollaire mesure** : toute mine posee par 1144 est adjacente a un ennemi **par construction**,
donc morte au tour suivant. Le seul chemin vers `then` est d'accumuler des mines qui SURVIVENT via
`1145 SporeMineLauncher` (qui cible une tuile libre quelconque) — **une seule mine par cast**, donc
**3 casts** sur des tuiles eloignees, puis 1144. Quatre tours de MoW ; la partie s'est terminee avant.
⇒ **branche `then` NON CONFRONTEE LIVE**, residu `#939-r1`.

## 5. Ce qui reste ouvert

* **`#939-r1`** — la branche `then` en live (montage ci-dessus).
* **`PerformAIMovement` est INERTE pour son unique consommateur, et c'est NOMME.** La feuille 62
  derive de `MoveTowardsUnitUtility`, dont le port lit `meta["movetowards_hexdist"]` — une cle
  qu'**aucun producteur de `meta` du depot ne remplit** (mesure : 0 site d'ecriture). Score plat ⇒
  argmax **keep-first** (le natif remplace sur `Fix64$$op_GreaterThan`, STRICT) ⇒ position
  courante ⇒ aucun `MoveUnitOperation`. C'est **le comportement natif a utilite plate**, pas une
  invention : ce qui manque sont les deux etages de `MoveTowardsUnitUtility$$GetMinDistanceToTarget`
  (resolution de la cible par balayage `GetAllAliveUnits` + distance de **CHEMIN** par tuile), et ils
  appartiennent au foyer du residu **`#175-r`** deja ouvert.
* Le playbook `BioMinefieldPlaybook` (utilite = `100 × |GetFreeAdjacentTiles(cible)| + 100 × PV%`,
  `IBattleQuery` slot **82**) est porte mais **non confronte** a un tour d'IA observe.

## 6. Foyers

Code : `engine/runner/abilities/loki/bio_minefield.py` (neuf),
`engine/playbook/noncomparable/bio_minefield.py` (neuf),
`engine/entities/selectors/composites.py` (`random_adjacent_free_tile`),
`engine/entities/triggers.py` (`has_adjacent_enemies`),
`engine/runner/abilities/behaviours/ai_control.py` (`PerformAIMovement`),
`engine/runner/operations/summon_ai.py` (`ai_control_execute_movement_for`,
`ComputerMovementActionOperation`), `engine/ai/action_generators.py`
(`movement_action_with_override`), + les trois registres (`handler.py`, `attack_type.py`,
`targeting.py` — d'ou 1144 a **migre**, contrat de disjonction).

Cliquet : `tests/engine/runner/test_939_bio_minefield_offline.py` (14 crans).
Mesure : `probe_939_bio_minefield.py`.
