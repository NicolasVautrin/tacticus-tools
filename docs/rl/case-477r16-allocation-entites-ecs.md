# #477-r16 — La règle d'allocation des entités ECS

**Build** `rnca9r7q6c`. RE Ghidra + confrontation live session Frida **8**
(`probe_477r16_allocation_entites_ecs.py`, 4 runners montés et disposés).

## Verdict en une ligne

**MÉCANIQUE, et sans aucun terme libre depuis `#477-r16-r1`.** L'ordre et le nombre d'allocations
se reproduisent depuis la `BattleConfiguration` **plus deux tables statiques du binaire**, toutes
deux désormais lues et mirrorées. Prédiction posée **avant** mesure, vérifiée **10 critères sur
10**, sur **trois** boards de tailles distinctes (35 / 63 / 70 tuiles) **et trois BC** dont deux
fabriqués pour faire varier le dernier terme. Un émetteur de flux est constructible.

⚠ **Le scalaire `derived` était le point faible, et il a été attaqué comme tel** : mesuré par
DIFFÉRENCE, il absorbait silencieusement toute allocation manquée avant les tuiles — exactement
le mode de panne qui avait déjà produit ici « trois accords parfaits, modèle faux » (cf. Pièges).
Il est maintenant **prédit** (§3ter), et le contre-test le fait **bouger dans les deux sens**.

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

`P` se lit dans `BC.Player.Players`. **`E` n'est PAS entièrement dans la BC**, et ses termes
n'ont pas tous le même statut — **trois sont CONDITIONNELS** (cf. § suivant) :

| terme de E | valeur sur le seed | source | ajout |
|---|---:|---|---|
| `BC.EnvironmentAbilities` + `…Enhancements` (2 `AddRange`) | 0 | la BC | inconditionnel |
| `GetDerivedEnvironmentAbilities(passif)` | **1** | table **statique** `+0x38` (2 entrées) | inconditionnel |
| `EnvDespoiledGroundTileDamage`, `EnvFireTileDamage` | 2 | constantes en dur | **dédupliqué** |
| `StaticBattleRules.DamageTrait$$GetDamageTraitAbilities` | 3 | table **statique** (`.cctor`, 3 entrées) | inconditionnel |
| `EnvCapturePointShield` si `GameMode == SyncPVP` | 0 | idem | **dédupliqué** |

Deux tables statiques du binaire entrent donc dans un offset qu'on croirait dérivable du BC.
**Un émetteur doit les mirrorer.**

### 3bis. `IncludeEnvironmentAbility` DÉDUPLIQUE — la somme n'est pas une somme (#477-r16-r1)

`IdunBattle.Operations.SetupGameOperation$$IncludeEnvironmentAbility` n'est **pas** un `Add` :
elle construit un prédicat sur l'id (`<>c__DisplayClass18_0$$<IncludeEnvironmentAbility>b__0`
compare `cfg.Id` au type capturé), appelle
`idun.shared.extensions.ListExtensions$$Contains<T>` et **retourne sans rien ajouter** si la
liste porte déjà cette ability. Les **deux boucles** (derived, damage traits) font au contraire
un `List.Add` **direct** et ne dédupliquent rien. L'ordre de construction est donc :

```
list.AddRange(BC.EnvironmentAbilities.EnvironmentAbilities)              # AddRange
list.AddRange(BC.EnvironmentAbilities.EnhancementsEnvironmentAbilities)  # AddRange
foreach kv in BC.Abilities.PassiveAbilities: list.Add(derived(kv.Key))   # Add DIRECT
IncludeEnvironmentAbility(EnvDespoiledGroundTileDamage)                  # DEDUP
IncludeEnvironmentAbility(EnvFireTileDamage)                             # DEDUP
foreach x in GetDamageTraitAbilities(): list.Add(x)                      # Add DIRECT
if SyncPVP: IncludeEnvironmentAbility(EnvCapturePointShield)             # DEDUP
```

La formule « `|BC| + 2 + 3 + derived + syncpvp` » de la première version reste juste **ici**
uniquement parce que les deux listes du BC sont **VIDES** sur le seed. Elle est fausse dès qu'un
BC porte l'une des trois. Résidu `#477-r16-r1-r1`.

### 3ter. `derived` est LU, plus mesuré par différence (#477-r16-r1, FERMÉ)

`StaticBattleRules.TriggeredAbility$$GetDerivedEnvironmentAbilities(passiveAbilityType)` est un
`TryGetValue` sur le champ **statique `+0x38`** de `StaticBattleRules.TriggeredAbility`, un
`Dictionary<TriggeredAbilityType, TriggeredAbilityType>` — signature lue dans
`frida/methods.tsv`, pas déduite. La valeur trouvée est un **scalaire**, emballé par
`IdunBattleLogic.Extensions.TExtensions$$ToList<T>` : le retour est une liste à **UN** élément,
ou `null`. Le `.cctor` y écrit **DEUX** entrées, et rien d'autre :

| clé (passif du BC) | valeur (env ability allouée) |
|---|---|
| `PowerUp_ReinforcementShield` | `EnvReinforcementShield` |
| `Ambush` | `EnvAmbushResurrect` |

⚠ **Deux, et pas une de plus** : le `.cctor` fait 980 lignes décompilées et peuple **19** champs
statiques, mais il les écrit dans une séquence d'offsets **strictement croissante**
(`+0x0, +0x8, +0x10, … +0x90`), chacun **une seule fois**. `+0x38` n'a donc **qu'un seul site
d'écriture**, et il porte ces deux `Dictionary.Add`.

⚠ Nuance lue, sans effet ici : `TExtensions$$ToList<T>` **teste une garde sur la valeur** avant
son unique `List.Add` et rend `null` si elle échoue. La sémantique exacte de cette garde
(`FUN_1801f53a0`, helper IL2CPP non nommé) n'est **pas** établie — HYPOTHÈSE : « valeur ≠
défaut ». Sans effet sur ce compte : les deux valeurs de la table sont non nulles.

La boucle appelante n'en lit que les **clés**, et le dictionnaire itéré est
**`BC.Abilities.PassiveAbilities`** (`BC+0x90` = `AbilitiesConfiguration` par son `.ctor`,
`+0x18` = le dict des passifs, cf. `AbilitiesConfiguration$$GetPassive`). D'où :

```
derived = |{PowerUp_ReinforcementShield, Ambush} INTER keys(BC.Abilities.PassiveAbilities)|
```

**Domaine `0..2`.** Le `1` du seed n'est donc pas un scalaire ajusté : `Ambush` y est présent,
`PowerUp_ReinforcementShield` non. `GetEnvironmentAbilities` est le **seul** appelant (xrefs).

**Contre-test joué, et il DISCRIMINE** (`probe … --contre-derived`, session 8, board `C1_02`,
prédictions imprimées avant mesure) :

| montage | `derived` | 1ʳᵉ tuile prévue | mesurée |
|---|---:|---:|---:|
| seed intact (témoin, 3 boards) | 1 | 12 | **12** |
| `+ PowerUp_ReinforcementShield` dans `BC.Abilities.PassiveAbilities` | 2 | 13 | **13** |
| `− Ambush` | 0 | 11 | **11** |

Un terme obtenu par différence aurait absorbé n'importe quelle allocation manquée en amont ;
celui-ci **bouge dans les deux sens, de la quantité prévue**. Le probe porte un cran
anti-régime-dégénéré : `_load_seed_bc` re-synthétise `BC.Abilities` (#254) et pourrait recombler
une clé retirée — si la prédiction de la variante n'est pas distincte du témoin, il **refuse de
conclure** au lieu de rendre un vert.

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

⚠ **La seule réserve** : `GetEnvironmentAbilities` itère un **`Dictionary<,>`**
(`BC.Abilities.PassiveAbilities`) pour appeler
`GetDerivedEnvironmentAbilities`. `Dictionary` ne garantit pas son ordre par contrat ;
en pratique il rend l'ordre d'insertion tant qu'aucun `Remove` n'a eu lieu, et les insertions
viennent de la désérialisation du BC. Cela n'affecte que **l'ordre interne** du bloc env abilities,
jamais leur nombre ni les blocs suivants — donc jamais les ids des tuiles ni des unités.

## Mesure — 10/10, trois tailles de board et trois BC

```
python scripts/python/probe_477r16_allocation_entites_ecs.py \
    --session <sid> --mow adeptExorcist --contre-derived
```

joueurs `3..2+P` / nb tuiles == `Width*Height` / tuiles contiguës / 2 plateformes MoW juste après /
première unité == 1ʳᵉ tuile + T + 2 / pas == 2 / aucun trou dans `3..max` / `derived` invariant /
`derived` mesuré == `derived` **lu** / tout pas expliqué par `1 + pieds + intercalées` /
`derived` **fait varier expres** suit la prédiction.

Le probe **refuse de conclure** sous trois tailles distinctes — deux points valident n'importe
quelle droite, et `MC1_67`/`C1_70` font tous deux 63 tuiles (piège payé en #477-r15). Il refuse
**aussi** de conclure si une mutation de contre-épreuve n'a pas mordu.

## Quatre pièges payés ici même

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
4. **Une liste d'`Add` n'est pas forcément une somme.** Trois des cinq termes de `E` passent par
   `IncludeEnvironmentAbility`, qui **déduplique** (§3bis) — la formule additive tenait par
   accident, parce que les listes du BC sont vides sur ce seed. Le nom de la fonction ne le
   disait pas ; seul son corps le dit. Corollaire général : **lire le corps de chaque « helper
   d'ajout » avant de compter ses appels.**

## Résidus

- ~~**#477-r16-r1**~~ — **FERMÉ** (§3ter) : la table est lue (2 entrées), `derived` est prédit et
  confronté, et le contre-test le fait varier dans les deux sens.
- **#477-r16-r1-r1** — la branche **DÉDUPLICATION** d'`IncludeEnvironmentAbility` (§3bis) est lue
  mais **NON CONFRONTÉE** : sur tous les montages disponibles, `BC.EnvironmentAbilities` est
  **vide**, donc les trois termes conditionnels valent invariablement 1/1/0 — régime dégénéré sur
  cet axe. Il faudrait un BC portant déjà `EnvDespoiledGroundTileDamage` ou `EnvFireTileDamage`
  dans `BC.EnvironmentAbilities.EnvironmentAbilities`. Conséquence directe : la **forme
  sérialisée** d'un élément de ces listes n'a jamais été observée —
  `probe.ids_env_abilities_du_bc` lève plutôt que de deviner, mais son extracteur d'id est donc
  lui-même non validé.
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
