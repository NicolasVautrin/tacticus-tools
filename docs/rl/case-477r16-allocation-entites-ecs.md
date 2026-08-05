# #477-r16 — La règle d'allocation des entités ECS

**Build** `rnca9r7q6c`. RE Ghidra + confrontation live session Frida **8**
(`probe_477r16_allocation_entites_ecs.py`, 4 runners montés et disposés).

## Verdict en une ligne

**MÉCANIQUE.** L'ordre et le nombre d'allocations se reproduisent depuis la `BattleConfiguration`,
à **un scalaire près** (les env abilities dérivées, invariant, lisible dans le binaire). Prédiction
posée **avant** mesure, vérifiée **9 critères sur 9**, sur **trois** boards de tailles distinctes
(35 / 63 / 70 tuiles) — dont **84**, jamais mesuré auparavant. Un émetteur de flux est constructible.

## 1. Qui alloue

Allocateur **unique** — `IdunBattle.Entities.Components.MatchComponent$$NextId` :

```
this.<+0x10> += 1 ; return this.<+0x10>      // PRE-incrementation
```

`MatchComponent$$.ctor` pose le champ à **1**. `MatchComponent$$ReturnLastId` le décrémente.

Les **neuf** sites d'appel (xrefs Ghidra — liste exhaustive, il n'existe aucune autre voie) :

| fonction native | allocations | note |
|---|---|---|
| `AddPlayerOperation$$Execute` | 1 / joueur | → `Blueprints$$Player` |
| `AddEnvironmentAbilityOperation$$Execute` | 1 / ability | deux sites, branches **exclusives** |
| `AddEnvironmentAbilityOperation$$CreateEntity` | 1 / ability | idem ; non appelé par `Execute` |
| `AddTileOperation$$Execute` | 1 / tuile | **rollback** si la factory rend null |
| `AddTileOperation$$CreateTile` | 1 / tuile | **rollback** idem |
| `AddUnitOperation$$Execute` | **1 + 1 par pied** | 2ᵉ site **dans une boucle** sur les tuiles occupées |
| `AddMachineOperation$$Execute` | 1 / machine | `Blueprints$$Machine` — **aucun pied** |
| `AddMachineOfWarPlatformOperation$$Execute` | 1 / plateforme | |
| `AddEffectOperation$$Execute` | 1 / effet | pendant le déroulé |

⚠ **Le rollback n'existe QUE sur le chemin tuile.** `AddUnitOperation` et `AddMachineOperation`
rendent `null` sans appeler `ReturnLastId` : un échec de création **brûle l'id**. Un émetteur qui
suppose « pas d'entité ⇒ pas d'id consommé » divergera sur toute la suite du flux.

## 2. Pourquoi le pas de 2

Ce n'est **pas** « deux entités par unité » : `AddUnitOperation$$Execute` alloue l'unité, puis entre
dans une **boucle** sur les tuiles occupées et alloue une `FootEntity` par tuile
(`Blueprints$$UnitFoot` → `UnitComponent$$AddFoot`). `IdunBattle.Entities.Enum.EntityType` porte
d'ailleurs `5=UnitFoot` à côté de `1=Unit`.

Le pas vaut donc **1 + nb de pieds**, et il tombe à 2 uniquement parce que toutes les unités
observables ici sont mono-tuile — c'est **structurel** : `AddPredefinedUnits` passe
`TExtensions.ToList(<un tileId>)`, une liste à UN élément. Le flux le confirme, tag par tag
(`Tag=Unit_Foot_Tile_Id_1:<tileId>`, numéroté, donc extensible).

## 3. Ce que compte l'offset initial

`IdunBattle.Operations.SetupGameOperation$$Execute` fixe une séquence **invariante** :

```
InitializeMatch(matchEntityId = 1, Width, Height, ...)   entite Match = id LITTERAL 1,
                                                         puis InitializeMatchOperation$$Execute
                                                         fait `+= 1` -> compteur = 2
AddPlayers()                    SortedDictionary  -> ordre par cle
AddEnvironmentAbilities()       List de GetEnvironmentAbilities
AddTiles()                      for row in 0..Width-1 { for col in 0..Height-1 }
SetupRoom()                     n'alloue RIEN
AddMachinePlatform()            DEUX appels (teams 2 puis 1), 1 entite chacun
RevealHumanPlayerRoom()         n'alloue RIEN
AddPredefinedUnits() / AddPredefinedMachines() / AddBossUnit()
```

⇒ **l'id 2 n'est jamais attribué** (le Match prend 1, le compteur saute à 2, le premier `NextId`
rend 3). Mesuré : les trois joueurs reçoivent 3, 4, 5 sur les trois boards.

D'où, sans aucun paramètre ajusté :

```
premier id de tuile  = 3 + P + E
premier id d'unite   = premier id de tuile + Width*Height + 2      (+2 = plateformes MoW)
```

`P` se lit dans `BC.Player.Players`. **`E` n'est PAS entièrement dans la BC** :

| terme de E | valeur sur le seed | source |
|---|---:|---|
| `BC.EnvironmentAbilities` + `…Enhancements` | 0 | la BC |
| deux constantes **en dur** `0x5cb`, `0x18` | 2 | `SetupGameOperation$$GetEnvironmentAbilities` |
| `StaticBattleRules.DamageTrait$$GetDamageTraitAbilities` | 3 | table **statique** (`.cctor` : `0x3f8`, `0x4b3`, `0x4bb`) |
| `0x52e` si `GameMode == SyncPVP` | 0 | idem |
| `GetDerivedEnvironmentAbilities(passif)` | **1** | table **statique NON lue** — `#477-r16-r1` |

Deux tables statiques du binaire entrent donc dans un offset qu'on croirait dérivable du BC.
**Un émetteur doit les mirrorer.**

## 4. Effets, summons, machines, projectiles

Même compteur, aucune exception : un **effet** = 1 (`AddEffectOperation$$Execute`, au fil du
déroulé — cohérent avec les `Effect_Id` 97/98 consécutifs mesurés en #477-r15) ; un **summon** passe
par `AddUnitOperation` donc 1 + pieds ; une **machine** = 1 sans pied ; une **plateforme MoW** = 1.
Les **projectiles n'ont pas d'entité** — ils ne figurent pas dans `EntityType`.

## 5. Chemins non déterministes

Aucun sur le chemin d'allocation, à une réserve près :

- `AddPlayers` — `SortedDictionary` : ordre **par clé**, déterministe et dérivable du BC ;
- `AddTiles` — double boucle **indexée** ;
- `AddPredefinedUnits` / `AddPredefinedMachines` — `List` ;
- `SetupRoom` itère un **`HashSet<int>`**, mais **n'alloue rien** : sans effet sur les ids ;
- rien d'asynchrone — les coroutines (`System_GameSetup_GroupHandler$$ExecuteStepInternalCoroutine`)
  sont côté **vue**, pas dans la logique.

⚠ **La seule réserve** : `GetEnvironmentAbilities` itère un **`Dictionary<,>`** (les passifs du BC)
pour appeler `GetDerivedEnvironmentAbilities`. `Dictionary` ne garantit pas son ordre par contrat ;
en pratique il rend l'ordre d'insertion tant qu'aucun `Remove` n'a eu lieu, et les insertions
viennent de la désérialisation du BC. Cela n'affecte que **l'ordre interne** du bloc env abilities,
jamais leur nombre ni les blocs suivants — donc jamais les ids des tuiles ni des unités.

## Mesure — 9/9, trois tailles de board

`python scripts/python/probe_477r16_allocation_entites_ecs.py --session <sid> --mow adeptExorcist`

joueurs `3..2+P` / nb tuiles == `Width*Height` / tuiles contiguës / 2 plateformes MoW juste après /
première unité == 1ʳᵉ tuile + T + 2 / pas == 2 / aucun trou dans `3..max` / `derived` invariant /
tout pas expliqué par `1 + pieds + intercalées`.

Le probe **refuse de conclure** sous trois tailles distinctes — deux points valident n'importe
quelle droite, et `MC1_67`/`C1_70` font tous deux 63 tuiles (piège payé en #477-r15).

## Trois pièges payés ici même

1. **Un accord parfait peut venir de deux erreurs qui s'annulent.** La première version prédisait
   `3 + P + E + T` avec un `E` trop grand de 2 et **sans** les plateformes MoW : la prédiction sur
   l'unité tombait juste sur les **trois** boards (49 / 77 / 84) alors que l'offset des tuiles était
   faux. Un seul point d'observation ne valide pas une décomposition — le probe vérifie désormais
   **chaque étage séparément**.
2. **L'enum ne dit pas la table.** `E` avait été dérivé de `IdunBattle.Entities.Enum.DamageTrait`
   (6 membres) au lieu de `StaticBattleRules.DamageTrait$$.cctor` (**3** entrées). L'enum nomme des
   *traits*, la table nomme des *abilities*.
3. **Le build qui fait foi ne se devine pas.** Le probe re-dérivait « quel build » à la main et
   retenait `gqfc5mff6c` (archive) au lieu de `rnca9r7q6c`. Foyer unique :
   `symbols_layout.current_build()`.

## Résidus

- **#477-r16-r1** — `GetDerivedEnvironmentAbilities` non lue. Elle vaut **1** sur ce seed BC
  (mesuré, invariant par board), mais son contenu vit dans le `.cctor` de
  `StaticBattleRules.TriggeredAbility` et **dépend des passifs du BC** : un autre seed changerait
  l'offset. Un émetteur doit mirrorer ce dictionnaire.
- **#477-r16-r2** — la **boucle sur les pieds** est lue au décompilé mais **non confrontée** : aucun
  porteur multi-tuiles n'est atteignable par les montages testés (les unités prédéfinies sont
  mono-tuile par construction, une MoW n'a aucun pied). Le porteur est le **BOSS**
  (`AddBossUnit` / `GetBossPlatform`) — montage à écrire.

## Ce que je n'ai PAS fait

- **Aucun émetteur écrit** — la tranche RE et mesure, elle ne porte rien.
  `engine/runner/events.py` et le writer de grammaire n'ont pas été touchés.
- **Le déroulé n'est pas confronté** — la mesure porte sur `System_GameSetup`. Les allocations
  d'effets *pendant* la bataille suivent le même compteur (lu), mais leur ORDRE dépend de l'ordre
  d'exécution des opérations : c'est la fidélité du port, pas une règle d'allocation supplémentaire.
- **`replaySteps` / `replayRngEvents` non utilisés** — déployés pendant la fenêtre #10, mais ma
  mesure n'en avait pas besoin : le flux porte déjà `Entity=` sur chaque ligne.
