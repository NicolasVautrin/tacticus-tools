# case-304 — `ModifiedExoarmour` : la première feuille de tuile qui se paie PAR TUILE PARCOURUE

**Statut : LIVRÉ** (2026-07-30). Résidu N14 de #27-r1 (PR #316), fermé.

`IdunBattle.AI.Playbook.Loki.ModifiedExoarmourPlaybook$$CalculateMovementUtilityInStepsInternal`
ajoute au composite `Tile(7)` — via la feuille dispatcher `TriggeredAbilitiesUtility(2)` —
`ModifiedExoarmour_LikesMovingPerTile` (**5**) × `path.Count`. Porteur : `votanChampion` (Kimm,
HERO `LeaguesOfVotann`, hors pool → `catalog_inject`). La clé de poids est **ajoutée par le build
`rnca9r7q6c`** : absente de `data/seed-bc.json`, elle vaut 5 au gameconfig vivant.

---

## 1. La route, établie AVANT d'écrire une ligne

Le critère posé en premier était : **quel slot, appelé par qui, et à quel moment le terme entre
dans la comparaison ?** Réponse lue au décompilé, de bas en haut :

```
ComparablePlaybook<T>$$CalculateActionUtility            (argmax du Bucket, `>` STRICT)
  = CalculateCustomUtility  +  CalculateUtilityFromPredictions  +  Tile(7)@tuile
                                                                   |
  ComposedUtility Tile(7)  ->  feuille TriggeredAbilitiesUtility(2)
      IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext
        itère l'AbilitiesComponent du mover, `PlaybookDatabase$$LoadPlaybook(abilityType)`,
        somme les `ITriggeredAbilityPlaybook.CalculateMovementUtilityInSteps`
                                                                   |
  IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateMovementUtilityInSteps
        AUCUN gate (ni cooldown, ni charge, ni `IsAbilityActive`) : il fabrique le
        `Func<string,int>` (= `$$GetUtilityValue`) et appelle le vslot **+0x1d8**
        `CalculateMovementUtilityInStepsInternal(case, getUtilityVal)`
```

⚠ Le slot **+0x1d8** est celui de la face MOUVEMENT, distinct du `CalculateCustomUtility` de #27
(0x338 sur les playbooks d'ACTIVE, 0x548/0x5a8/0x668/0x7b8 sur sept playbooks TRIGGERED). Ici on n'a
pas eu à le lire à la main : le registre `TRIGGERED_MOVE_PLAYBOOKS`
(`engine/playbook/adjacent_unit_preference.py`) est déjà le mirror de ce slot pour 13 concrets.

`GetUtilityValue(dict, key)` = `dict.TryGetValue(key, out v)` ; clé absente ⇒ log + **0**. C'est
pourquoi ce terme est *invisible* pour qui lit la table de la CAPTURE : elle n'a pas la clé. Le
refresh `catalog_inject.refresh_ai_utilities` (natif) / `engine.weights.load` (port) sert le
gameconfig vivant aux DEUX côtés — même piège que #271.

## 2. Le corps, remis en C#

```csharp
// <CalculateMovementUtilityInStepsInternal>d__2$$MoveNext
int val = 0;
if (case.Unit != null && !case.StaysOnTile(state)) {
    var path = pathfinders.GetPath(case.Unit,                              // IPathfinders slot 3
                                   EntityExtensions.GetMainTile(case.Unit, state),
                                   case.MovementTile, null);
    if (!CollectionExtensions.IsNullOrEmpty(path))
        val = getUtilityVal("ModifiedExoarmour_LikesMovingPerTile") * path.Count;
}
yield return Fix64.op_Implicit(val);
```

Quatre lectures que l'on ne devine pas :

1. **`Count` compte des NOEUDS, extrémités INCLUSES.**
   `IdunBattle.Entities.Pathfinding.BasePathfinder$$FindPath` ajoute `toTile`, remonte le dict
   parent jusqu'à `fromTile` **inclus**, puis `Reverse` ⇒ `Count = arêtes + 1`. Une tuile ADJACENTE
   vaut donc `5 × 2 = 10`, pas 5. Même convention que
   `MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy`, qui lit le même `route+0x18` et
   l'appelle « distance ». **C'est le point qu'un off-by-one aurait fait rater** : la mutation
   `n − 1` retourne la décision native sur le montage de référence (cf. §5).
2. **`StaysOnTile` court-circuite AVANT le pathfinding.**
   `IdunBattle.AI.Utilities.UtilityMovementCase$$StaysOnTile` = `GetMainTile(case.Unit, state) ==
   case.MovementPosition.MainTile` ⇒ rester sur place vaut **0**, pas `5 × 1`. Confondre les deux
   fausse tout l'encadrement du poids (mesuré : `w > 6.15` au lieu de `w > 4.61`).
3. **Le pathfinder n'est PAS le type 1.** Le playbook appelle le **slot 3** de `IPathfinders`
   (`GetPath(unit, from, to, useTeleporter)`), dont `IdunBattle.Entities.Pathfinding.Pathfinders$$GetPath`
   dérive le type par `IMovementQuery.GetPathfinderTypeForUnit(unit)` — **`WalkPathfinder` = 0**
   pour une unité non volante sans effet de mouvement spécial. La feuille
   `MinDistanceToClosestEnemy(17)`, elle, passe le LITTÉRAL `1` (slot 4) et tombe sur
   `IgnoreTerrainPathfinder`. Les deux diffèrent sur le coût d'arête ET sur le blocage par
   occupant ⇒ **`ctx.pathdist_by_pos` n'est pas réutilisable ici**.
   `GetPathfinderTypeForUnit(unit, ignoreSpecialMovement=false)` :
   `HasEffect(0x40b)`→`IsLikeFlying?7:6`, `0x474`→`9:8`, `0x4d6`→`11:10`, `0x625`→`13:12`,
   sinon `IsLikeFlying?3:0`.
4. **Aucun gate d'ability** (cf. §1).

## 3. Ce que le port ajoute : la face « chemin exact » du WalkPathfinder

`engine/entities/pathfinding/walk_pathfinder.py` ne portait que l'**énumération** (flood-fill par
niveaux). Le **chemin exact pondéré** — que l'en-tête du package annonçait « non porté » — est
désormais là, en domaine POSITION (`get_path_node_counts_by_pos`), mirror de :

* `BasePathfinder$$GenerateBreadthFirstTree` — A\* : `newCost = WeightCost(unit, n) + cost[tile]`,
  priorité `newCost + Heuristic(n, to)` avec `Heuristic = |dcol| + |drow|` (≤ 2 par pas, coût réel
  ≥ 6) donc **admissible** ⇒ un Dijkstra depuis l'origine retrouve le même optimum pour TOUTES les
  destinations en une passe ;
* `WalkPathfinder$$WeightCost` = `(GetTileBlockingReasons & 1 ? 10000 : 10) − elevation(tile)` —
  ⚠ à ne pas confondre avec `IgnoreTerrainPathfinder$$WeightCost` = `10 + IsFilled(to)` ;
* `WalkPathfinder$$IsValidPathNode` = `IsWalkable(to)` ∧ `|Δelev| ≤ 1` ∧
  `!UnitIsBlockedByEnemyUnit(to, unit)` (occupant `Steppable` = trait `0x1b` ⇒ ne bloque pas) ;
* `WalkPathfinder$$IsValidFinalTile` = `!IsTemporary(to) ∧ IsWalkable(to)` (pré-gate de `FindPath` :
  faux ⇒ `null` ⇒ terme 0).

⚠ **`IsValidContinuePathTile` n'existe PAS sur cette route** : `GenerateBreadthFirstTree` ne
l'appelle jamais. Une tuile block-entering reste **traversable** par un chemin (elle coûte
`10000 − elev`), alors qu'elle est un cul-de-sac pour l'ÉNUMÉRATION (`NodesInNextLevel`, #131).

## 4. Effet de bord fermé au passage : le kit déclenché du mover

`tile_leaf_ctx` UNIONNAIT le kit gameconfig avec la lecture live du `TriggeredAbilityComponent`
(N13, « jamais retirer un id connu »). Or cette lecture EST la collection que le dispatcher natif
itère. **Mesure** (fixture #27-r1, bras où le seed BC pose `votanChampion.PassiveAbilities = []`) :

| source | kit rendu |
|---|---|
| `unitAbilityStates` (live, = AbilitiesComponent) | `[1486]` |
| `gameconfig.passiveAbilities` | `[1529, 1486]` |
| union (comportement d'avant) | `[1529, 1486]` ← **faux** |

L'union réintroduisait un passif que la bataille n'a pas. L'écart était **invisible** tant qu'aucun
playbook n'était enregistré pour 1529 ; enregistrer le terme l'a rendu observable en rougissant
`test_mass_driver_custom_utility_live.py::test_engine_matches_native_on_all_cells`. La lecture live
FAIT AUTORITÉ quand elle rend quelque chose ; le repli gameconfig reste entier quand elle est vide
(RPC indisponible, entité absente, contexte offline `rid` faux) — le seul régime que N13 protégeait.

## 5. Confrontation live — PAR ÉTAGE, jamais sur la décision complète

Sur ce montage, la décision complète du moteur est masquée par un écart **antérieur et étranger** :
la prédiction de dégât de l'attaque normale de Kimm depuis une tuile d'arrivée. Mesuré (MC1_67/909,
`Damage = 1000`) : `pairUtility(69, (4,0))` natif = **44.395**, la même paire côté port = **17.8**.
Comparer des décisions conclurait sur ce résidu-là. On injecte donc l'étage PRÉDICTION du NATIF :

```
u_action(ability, tuile) = pairUtility(ability, tuile)   <- NATIF
                         + CalculateCustomUtility        <- +1 normale, 0 pour 1222 (#27-r1)
                         + Tile(7)(tuile)                <- PORT   (seul étage testé)
```

`probe_304_modified_exoarmour.py` — **4 bras**, deux plateaux, `--passive-on` (kit RÉEL) :

| montage | Damage | action native | \|chemin\| joué |
|---|---|---|---|
| MC1_67 / 909 | 900 | `1222` sur place | 0 |
| MC1_67 / 909 | 1000 | `69` @ (4,0) | **4** |
| C4_09 / 31337 | 3000 | `1222` sur place | 0 |
| C4_09 / 31337 | 3600 | `69` @ (1,0) | **3** |

Résultats :

* **V2** — l'argmax `pair_natif + custom + Tile7_port` reproduit l'action ET la tuile natives dans
  les 4 bras.
* **V3 (le ROUGE)** — terme RETIRÉ, l'argmax choisit `1222` **sur place** là où le natif bouge :
  c'est exactement le fait qui avait obligé #27-r1 à retirer le passif de son montage.
* **V8 / V9 — le modèle est CONTRAINT, pas ajusté.** Chaque bras impose une inégalité sur le
  coefficient ; l'intersection des 4 donne
  * modèle `k × |chemin|` : **4.6130 < k < 5.0563** — le poids LU au gameconfig (**5**) y tombe,
    dans une fenêtre de 0,44 point (±4,4 %) ;
  * modèle FORFAIT (`k` dès qu'on bouge) : **18.4518 < k < 16.4454** ⇒ **VIDE, RÉFUTÉ**.
  C'est la présence de **deux longueurs de chemin JOUÉES** (4 et 3) qui sépare les deux modèles :
  avec une seule, ils sont indistinguables (V4 le dit bras par bras).
* Mutation adversariale `n − 1` : V1 et V2 rougissent (l'argmax repasse à `1222`) — le harnais
  discrimine à **une tuile près**.

**Non couvert / résidus :**

* **Phase B (mouvement PUR)** — non concluante : `MinDistanceToClosestEnemy.PerTileDistance` (−100
  par tuile de chemin) écrase le terme ; aucune des 14 positions d'ennemi balayées ne le rend liant
  sur MC1_67/909. Ce n'est pas une réfutation, c'est un montage non discriminant — le probe le dit.
* `IsValidFinalTile` : le volet `IsTemporary` n'a pas de source dans le `tile_leaf_ctx`
  (dégradation PERMISSIVE — une tuile temporaire recevrait un compte au lieu de rien).
* Tie-break entre deux chemins de MÊME coût et de longueurs différentes : non lu au décompilé (il
  dépend de la `PriorityQueue` native ; le natif garde le PREMIER, la mise à jour étant sur `<`
  STRICT). Ici, moins de noeuds gagne — même résidu que `ignore_terrain_pathfinder`. Sans relief,
  l'ambiguïté n'existe pas.
* `GetTileBlockingReasons` : le bit 0x4 (bloqueur posé par une UNITÉ, `blockerId != 0`) n'est pas
  porté — `tileMeta` ne remonte pas le `blockerId`. Hérité de `tile_blocking.tile_blocks_entering`.
* **Contraintes HORS MODÈLE** (`V10`) : les comparaisons à `|chemin|` ÉGAL ne portent aucune
  information sur le coefficient ; violées, elles mesurent une feuille `Tile(7)` non portée ou un
  tie-break. Le probe les compte à part au lieu de les faire passer pour une réfutation.
* **`ModifiedExoarmour` a aussi une face COMBAT** non portée par ce cas :
  `IdunBattle.Entities.Effects.Loki.ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus` /
  `$$GetExtraDamageMultiplier` et `ModifiedExoarmour_PierceReductionEffect$$
  CreatePiercingMalusForDefense`. C'est un candidat sérieux pour l'écart de prédiction ci-dessus
  (44.395 natif vs 17.8 port) — **hypothèse non vérifiée**, à ouvrir comme cas propre.
* **Enum `TriggeredAbilityType`** : 1529 est ajouté ; **8 autres membres du build `rnca9r7q6c`
  manquent encore** (1543 `PropheticSentinel`, 1546 `HeavyWarpFlamer_AttackTrackingAbility`,
  1552 `IconOfObstinacy`, 1554 `WhisperingWeb`, 1555 `EmpyricAmbush_Reset`,
  1556 `MyWillBeDoneOverlord`, 1557 `PhasalSubjugator`, 1558 `Helspear`). Aucun playbook porté ne
  les lit aujourd'hui ; re-dériver par diff `engine/entities/triggered_ability_type.py` ×
  `data/symbols/<CURRENT>/frida/enums.tsv`.

## 6. Fichiers

| rôle | chemin |
|---|---|
| playbook (le terme) | `scripts/python/engine/playbook/modified_exoarmour.py` |
| chemin exact WalkPathfinder | `scripts/python/engine/entities/pathfinding/walk_pathfinder.py` (§ CHEMIN EXACT PONDÉRÉ) |
| registre | `scripts/python/engine/playbook/adjacent_unit_preference.py` (`TRIGGERED_MOVE_PLAYBOOKS`) |
| enum | `scripts/python/engine/entities/triggered_ability_type.py` (`ModifiedExoarmour = 1529`) |
| kit du mover (§4) | `scripts/python/engine/utilities/tile.py` (`tile_leaf_ctx`) |
| probe (MESURE) | `scripts/python/probe_304_modified_exoarmour.py` |
| test (GARDE) | `scripts/python/tests/engine/test_modified_exoarmour_live.py` |
| fixture réutilisée | `scripts/python/probe_27_r1_massdriver_custom.py` (`MDA_FIXTURE`, `--passive-on`) |

Rejouer :

```bash
cd scripts/python
python probe_304_modified_exoarmour.py --damage 900,1000 --also C4_09:31337:3000,3600
python -m pytest tests/engine/test_modified_exoarmour_live.py tests/engine/test_mass_driver_custom_utility_live.py -q
```
