# #937 — `SynapticLinchpin` (passif d'`tyranWingedPrime`) : port des deux faces

**Verdict : PORTÉ ET CONFRONTÉ LIVE.** Une seule classe native, deux faces
(`CreateTrigger` + `CreateBehaviour`), aucune face morte. Build `rnca9r7q6c`.

## L'arbre natif

```
CreateTrigger =
    On(EventTriggerType.NormalAttack = 38,
       ownerNeedsToBeAlive: NOT(OwnerIsActor
                                & TriggeringAbilityIs(TriggeredAbilityType.FinalJustice = 1024)))
    & HasTrait(actor@+0x40, UnitTrait.Synapse = 2024)
    & AreFriends(owner@+0x30, actor@+0x40, ByCurrentTeam, anyEntity: 0)
    & IsAlive(target@+0x60)                       # ordre des `op_BitwiseAnd` LU au desassemblage

CreateBehaviour =
    Repeat( If( NOT AmountIsEqualOrGreater(
                      UnitsWithId(Children(owner@+0x30), "tyranSmnHormagaunt",
                                  UnitSelectionType.OnlyAliveAndTargetable = 3),
                      Direct(GetVariableForLevel(maxSummons = 49, abilityState))),
                Spawn(owner@+0x30,
                      First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(target@+0x60)),
                                                        UtilityType.Tile = 7, caster@+0x48), 1),
                      GetStringConstant(unitId = 0),
                      WithStatsFromConfig(cfg, abilityState){+0x18 = UseNormalAttackIfAble(
                          activeTarget@+0x68, target@+0x60,
                          parentAbility: AbilityOrEffect(this.<+0x10>))}) ),
            Direct(GetNumberConstant(nrOfSummons = 16)) )
```

## Ce que le natif dit et qu'aucune table ne disait

1. **`On(t, X)` n'est PAS `Event(t) & X`.** `IdunBattleLogic.Entities.DSLTriggers$$On(triggerType,
   ownerNeedsToBeAlive: IAbilityTrigger)` rend `EventTypeTrigger(t) & (this.<+0x20> | Not(X))`. La
   surcharge **booléenne** tranche l'identité de `<+0x20>` : `On(t, bool b)` rend
   `EventTypeTrigger(t) & this.<b ? +0x20 : +0x70>` (`cmove` lu), et `+0x70` est le trigger
   toujours-vrai que le port nomme déjà `YesTrigger` ⇒ **`<+0x20>` = `OwnerIsAlive`**. Donc
   `On(t, X) == Event(t) & (OwnerIsAlive | !X)`.
   Ici `X = !(OwnerIsActor & TriggeringAbilityIs(FinalJustice))`, soit un gate effectif
   **« le porteur doit être vivant, SAUF quand c'est lui qui frappe via `FinalJustice` »** — et
   `FinalJusticeAbility$$CreateTrigger` = `OnPreDeath(triggerOnOverKill: 1) & OwnerIsTarget`, c'est
   l'attaque post-mortem du trait que `tyranWingedPrime` porte. Le disjunct fait vivre le passif
   pendant la mort de son porteur. Lire ce 2ᵉ argument comme une condition d'événement aurait
   inversé le sens.

2. **Les slots de sélecteur de `DSLSelectors` s'établissent par recoupement des getters nommés**,
   chacun construisant `AreEqual(<slot>, <slot>)` : `OwnerIsActor`(0x30,0x40) ·
   `OwnerIsTarget`(0x30,0x60) · `OwnerIsCaster`(0x30,0x48) · `OwnerIsCasterTile`(0x30,0x50) ·
   `CasterIsTarget`(0x48,0x60) · `CasterIsCasterTile`(0x48,0x50) · `OwnerIsTargetTile`(0x78,0x30).
   Le champ COMMUN à plusieurs paires est identifié : **0x30 Owner** (4 getters), **0x48 Caster**
   (3), **0x60 Target** (3), d'où **0x40 Actor**, **0x50 CasterTile**, **0x78 TargetTile**.
   **0x68** n'est couvert par aucun getter : il est établi par deux sources concordantes — l'ordre
   des slots homologues du `DSLFactory` (`0x178 Target · 0x180 ActiveTarget`) et
   `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`, qui écrit `unitSpawned` dans le champ `+0x20`
   de la copie d'`AbilityEntities` (= `activeTarget`, arg 12 du ctor à 32 arguments) avant
   d'exécuter `options.<+0x18>`. ⇒ **`0x68 = ActiveTarget`**.

3. **Le piège du voisin, deux fois dans la même fonction.** Le `TriggeringAbilityIs` du trigger
   passe par un `op_Implicit` dont le pseudo-C **efface l'immédiat** : au désassemblage,
   `mov edx, 0x400` précède l'appel, et la surcharge visée est celle dont `frida/methods.tsv`
   déclare `triggeredAbility: TriggeredAbilityType` (les quatre homonymes ont des RVA distinctes —
   aucune fusion ICF). `1024` est **valide dans les trois espaces** et y nomme trois choses
   différentes (`FinalJustice` / `Burrowers_Appear` / `Emplacement_RangedEffect`). Le
   **second** `op_Implicit`, dans `CreateBehaviour`, n'a **pas** d'immédiat : son argument vient
   d'un appel que ghidra étiquette `CenterSpace.Free.MersenneTwister$$get_Count` (fold ICF, corps =
   `return *(int*)(this + 0x10)`) — c'est le `TriggeredAbilityType` de **cette** ability (1192).
   Recopier l'un pour l'autre n'aurait rien levé.

4. **`RepeatBehaviour$$Execute`** : `times` évalué **une seule fois** avant la boucle, `n` itérations
   du **même** `entities` (aucune liaison de `subject`/`active_target`), et **aucun court-circuit**
   (contraste `CombinedBehaviour`, qui teste le flag). `n <= 0` ⇒ zéro itération.

## Ground truth live (`probe_937_synaptic_linchpin.py`, board MC1_67, seed 777)

Le journal du cast ouvre un groupe `source: "SynapticLinchpin"` et y pose, dans l'ordre :

| étape | mesure |
|---|---|
| `step 9` | `Unit_Owner_Id=3`, `Unit_IsSummoned=1`, **`Unit_Parent_Id=81`** (le Winged Prime) |
| `step 12` | `MaxHealth=2992`, `FixedArmor=599`, `Attack=2194` |
| `step 13` | `ActiveAbility_Id=69 Level=50 VariableMultiplierPercentage=180` (+ 4 triggered au même état) |
| `step 29`/`4` | le summon **attaque la cible** (2 coups mêlée) |
| `step 12` | `UnitStats_TurnFinished=1` (`FinishUnitTurn(spawned, true)`, APRÈS l'on-appearance) |

* `2992 / 2194 / 599` == `summonHp/summonDmg/summonArmor[49] × 180 %` — c'est-à-dire, bit pour bit,
  `ability_var(...)` du port (`ToZeroBasedIndex = level - 1`).
* **`Unit_Parent_Id = 81` même quand c'est le `tyranNeurothrope` qui frappe** ⇒ le `parentSelector`
  est `owner@+0x30`, pas l'acteur : le slot Owner est bien réécrit sur le porteur du passif.
* `tyranTyrantGuard` (allié **sans** `Synapse`) frappe la même cible avec deux tuiles libres autour
  ⇒ **aucun summon**. Le gate `HasTrait(actor, Synapse)` mord.
* ⚠ Le `visualId` LIVE du summon est **`tyranNpc1Hormagaunt`**, pas la clé de config
  `tyranSmnHormagaunt` que le port pose — même dualité que `admecSmnVanguard`/`admecNpc1Vanguard`.

### Un groupe de trigger OUVERT et VIDE n'est pas un trigger muet

Premier montage : la cible n'avait **aucun voisin libre** ⇒ `CanAddUnit(AdjacentTiles(target))`
vide ⇒ le groupe `SynapticLinchpin` s'ouvre et se ferme **sans rien poser**. Vu du delta d'état,
c'est indiscernable d'un trigger qui n'a pas fire — et c'est exactement ce qui aurait fait conclure
« passif mort » ou « port faux ». Ce qui l'a tranché : **le journal d'events** (`captureEvents`,
`actions[].events`), qui NOMME la source du groupe. Le montage a ensuite été **piloté** (choix de
cible classé par voisins libres décroissants), pas subi.

### L'adjacence du montage doit être la NATIVE

`board.neighbours()` **trie et symétrise** ; le nœud `AdjacentTiles` mirrore
`AdjacentTilesSelector$$Select`, qui lit la liste **stockée** (`board.neighbours_native`). Mesuré :
la tuile 24 de MC1_67 a **6** voisins symétrisés et **4** natifs. Un montage calé sur le premier
croit avoir 5 tuiles posables et n'en a que 3 — ce qui rabat le plafond observé sur la GÉOMÉTRIE au
lieu du `maxSummons`, et rend l'assertion `<= cap` **verte sans rien discriminer**. Faux vert
attrapé au 1ᵉʳ jet du fichier de test, corrigé par `_victim_spot` + une garde de non-vacuité
`len(free_tiles) >= cap` et `len(hormagaunts) == cap`.

## Ce qui a changé dans le port

| fichier | changement |
|---|---|
| `engine/runner/operations/triggers/loki/synaptic_linchpin.py` | **neuf** — les deux faces |
| `engine/runner/operations/triggers/dispatch/registry.py` | entrée `"SynapticLinchpin"` + import |
| `engine/entities/behaviours.py` | nœud **`Repeat`** (absent du port) |
| `engine/entities/selectors/geometry.py` | `UnitsWithId` **applique** enfin son `UnitSelectionType` |

### `UnitsWithId` : un foyer PARTAGÉ, et pourquoi il fallait y toucher

Le 3ᵉ argument `mode` était **stocké et jamais lu**. Tant que la source était elle-même un sélecteur
filtré (`Friends`, `SurroundingEnemies` — les **deux** seuls call-sites exécutables antérieurs :
`playbook/geminae_superia.py` et `runner/abilities/genestealer.py`), l'omission était **inerte**,
les morts étant écartés en amont. Elle cesse de l'être dès que la source ne filtre rien :
`ChildrenOf` (`DSLSelectors$$Children(parent)`) rend **toutes** les entités enfants, cadavres
compris. Sans le filtre, un Hormagaunt **mort** tenait un slot du cap et le port refusait un spawn
que le natif fait. Le filtre passe par le foyer unique
`entities/unit_selection_type.py::selection_ok_from_ctx`, jamais par un `alive` à la main.
Régression rejouée : `tests/engine/runner/test_cultdemagogue_migration_live.py` (6 passed).

## Validation adversariale — `probe_937_mutants.py`

**10 mutants sur 10 MORDENT.** Chacun altère un conjoint natif du port ; le verdict est lu dans le
**bilan pytest**, jamais dans le code retour :

| mutant | conjoint natif visé | verdict |
|---|---|---|
| M1 | `HasTrait(actor, Synapse)` retiré | MORD (3 cas) |
| M2 | `AreFriends(owner, actor)` retiré | MORD |
| M3 | `IsAlive(target)` retiré | MORD |
| M4 | cap sur l'accumulateur du CAST au lieu de `Children(owner)` | MORD (2 cas) |
| M5 | `UnitsWithId` n'applique plus son `UnitSelectionType` | MORD |
| M6 | `on_appearance` retiré (le summon n'attaque plus) | MORD |
| M7 | `Spawn` ancré sur l'ACTEUR au lieu du PORTEUR | MORD |
| M8 | `AdjacentTiles(Target)` → `AdjacentTiles(Owner)` | MORD (2 cas) |
| M9 | `ability_state` retiré | MORD **après déplacement** |
| M10 | `Repeat` → une seule itération | MORD **après déplacement** |

### Deux mutants étaient INERTES — ils ont été DÉPLACÉS, pas laissés au score

* **M9** : après `buildNormalizedBC`, `passiveAbilityLevel == activeAbilityLevel == 50`, donc lire
  l'un ou l'autre donne les mêmes stats — **régime dégénéré**. Le cas
  `..._summon_stats_follow_the_PASSIVE_level_offline` sépare les deux niveaux (50 / 12) et
  **assertionne d'abord que les deux cellules diffèrent**, sinon il ne discriminerait rien.
* **M10** : `nrOfSummons == 1`, donc la boucle `Repeat` ne fait jamais qu'un tour dans ce régime —
  l'observable n'est gardé nulle part. Le nœud est donc confronté à son décompilé **hors ability**,
  dans `tests/engine/test_937_repeat_node_offline.py` (5 cas : nombre exact de tours, `n <= 0`,
  `times` lu UNE fois avant la boucle, absence de court-circuit sur `stop` **avec contre-épreuve
  sur `Seq` qui, lui, court-circuite**, et non-liaison du contexte).

### Le harnais lui-même a produit un faux positif, et il en porte la correction

Au 1ᵉʳ passage, une fenêtre de maintenance a tué la session au milieu de la série : les six derniers
mutants ont rendu `2 deselected, 9 errors` — **zéro assertion évaluée** — et un lecteur qui ne
regarde que `rc != 0` les compte tous comme des morsures. `probe_937_mutants.py` lit désormais le
bilan et distingue **MORD / INERTE / INDISPONIBLE** ; `INDISPONIBLE` sort en `rc=99` et n'est ni un
vert ni un rouge. Les six verdicts ont été **rejoués** après réouverture : tous MORDENT réellement.

## Deux réparations collatérales (rendues visibles en gravant l'empreinte #457)

Graver l'empreinte offline de mon fichier neuf a aussi mesuré trois fichiers qui ne l'étaient pas,
ce qui a fait passer leur confrontation de UNE à DEUX sources et révélé deux défauts **préexistants** :

* **`tests/engine/test_927_fury_offline.py` lisait un build PÉRIMÉ.** `_methods_tsv()` prenait le
  **premier** répertoire rendu par `os.listdir(data/symbols)` — `gqfc5mff6c` — et non `CURRENT`.
  Son « verdict DEAD » de l'étape 5 était donc rendu contre le mauvais dump, et son annonce « si un
  build futur ajoute une voie ATTAQUE, ce test rougit » était **fausse** : le fichier lu ne bougeait
  jamais. Corrigé (lecture de `data/symbols/CURRENT`, repli nommé) — et le verdict DEAD **reste
  vrai** sur `rnca9r7q6c`. `BUILD_DIR` est en outre **normalisé** : sans `normpath`, les chemins
  ouverts portaient le `../../../..` littéral, que le cliquet d'empreinte ne pouvait pas rattacher.
* **`tests/engine/runner/test_929_savage_killer_offline.py`** déclarait un périmètre trop étroit :
  il lit `data/i2_en.json` (entrée versionnée, invisible du graphe d'imports). Élargi.

## Résidus

* ~~**`#937-r1`**~~ — **RÉSOLU (2026-08-15), et la branche VIT.** L'énoncé disait que
  `fire_on_death` mirrore `IsAtomic`, « valeur **non lue** pour cette ability » : le nom était
  FAUX et la valeur est LISIBLE. Le gate de `CanGetAbilityTrigger` appelle
  `IdunBattle.Entities.Abilities.ITriggeredAbility` **slot 8 = `get_AllowForDeadOwner`** (`IsAtomic`
  désigne une AUTRE propriété, `ITriggerable` slot 0 = `get_AllowInAtomicMode`). Et
  `SynapticLinchpinAbility` **surcharge** cette propriété — slot 22 de sa vtable, `flags=0x08c6`,
  pas de `NewSlot` — avec un corps `b0 01 c3` = `mov al,1 ; ret` = **VRAI**, le **même** que
  `FinalJusticeAbility$$get_AllowForDeadOwner`. Le corps étant trivial donc DÉDUPLIQUÉ, il est
  absent des deux tables : la RVA se résout par le TOKEN (`Il2CppCodeGenModule.methodPointers`,
  414/414 couples de contrôle relus justes). **Correctif** : `fire_on_death = True`. **Garde** :
  `tests/engine/runner/test_937r1_synaptic_linchpin_porteur_mort_offline.py` (8 bras ; contre-épreuve
  jouée : `False` ⇒ 2 bras indépendants rougissent). Méthode et chiffres :
  `docs/rl/case-10015-allow-for-dead-owner.md`.
* **`#937-r2`** — la branche n'est pas **confrontée LIVE**. ⚠ Le montage a une contrainte non
  évidente : `FinalJusticeAbility.matches` refuse sur `ev.overkill`, et l'overkill natif est
  `dmg >= 2*PV` — le coup fatal doit donc tomber dans `PV_restants <= dmg < 2*PV_restants`, si bien
  qu'**user le Prime par attrition fait échouer le montage** (à faible PV restant, tout coup
  overkille). Recette : `catalog_inject.write_trait_seed_bc(out, ["tyranWingedPrime:FinalJustice"])`
  puis `rl_duel build --seed-bc <out> --board MC1_67 --a-units tyranWingedPrime,… --p-units <tueur>,…`
  — mettre le Prime du côté **adverse** rend le coup fatal pilotable par `applyAction` au lieu de
  dépendre de l'IA. Attendu : un `tyranSmnHormagaunt` apparaît alors que le Prime est mort.
  Contre-épreuve obligatoire : le même montage **sans** `FinalJustice` ne doit rien spawner.
* **`ignoreForcedTargets: 0`** du `First` natif : aucune contrepartie portée. Le `First(source,
  index=0)` du port est un `PickAtIndexSelector` ; il rend le **même** singleton que le
  `First(source, amount=1)` natif — écart de **citation**, pas de valeur, tant que `amount == 1`.
* Le cap compare `visualId == "tyranSmnHormagaunt"` (clé de config, celle que `_spawn_config_grot`
  pose). Un Hormagaunt arrivé par une autre voie sous le nom LIVE `tyranNpc1Hormagaunt` ne serait
  pas compté ; aucune voie portée ne le produit aujourd'hui.

## Non couvert

* Le régime **`FinalJustice`** (porteur mourant) — cf. `#937-r1`.
* `nrOfSummons > 1` **en régime d'ability** : la constante vaut `1`, donc la ré-évaluation du cap
  **entre deux itérations** du `Repeat` est portée mais non confrontée. Le nœud lui-même, lui, est
  gardé hors ability (`test_937_repeat_node_offline.py`).
* L'ordre du `SortTilesByUtilityForSummon` n'est pas confronté tuile à tuile au natif : seules
  l'**adjacence** du summon et l'appartenance à `CanAddUnit(AdjacentTiles(target))` le sont.
  Le mutant M8 mord sur l'**ancrage** du sélecteur (Target vs Owner), pas sur le **classement**.
* Le `UseNormalAttackIfAble` porte son `IF_ABLE_OPTION = 2` sans lui prêter d'effet (résidu
  **#889-r5-r2**, antérieur) : le port ne devine pas le gate « seulement si l'unité PEUT attaquer ».
