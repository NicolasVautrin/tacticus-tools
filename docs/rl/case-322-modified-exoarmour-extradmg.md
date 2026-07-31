# case-322 — `ModifiedExoarmour_ExtraDmgEffect` : le modèle de MAGNITUDE, et le port

**Statut : FERMÉ** (2026-07-31). Les deux résidus laissés ouverts par #312 (`R1` magnitude,
`R2` tuile (4,0)) sont **le même** résidu, et il tombe d'un coup : #312 composait l'écart *après*
coup (`624 × n × M`) alors que le natif l'arrondit **une fois par coup**, sur
`(base_percée + additif_percé) × M`. Le port qui suit cette structure rend les **six** tuiles de
mêlée bit-exactes, min et max, aux deux `Damage` — la sixième comprise.

Point de départ : `docs/rl/case-312-votan-prediction-gap.md` (localisation étage 1
`MakeDamagePredictions`, écart `44.395` natif vs `17.783` port).

**Les DEUX faces sont désormais portées et confrontées live.** La face PRÉDICTION (§1-§4) est
bit-exacte sur 85 paires ; la face COMBAT, laissée inerte par la première tranche, est fermée par
#335 (§5bis) : le runner tient lui-même le compteur de tuiles, parce que c'est lui qui applique le
déplacement.

---

## 1. La réponse au critère

> Existe-t-il un modèle qui explique **624** ET **4306**, et qui tombe juste sur les **six** tuiles
> de mêlée — pas cinq ?

**Oui.** Il n'a aucun degré de liberté : ses deux entrées (`V`, `n`) sont lues, et le pipeline qui
les consomme était **déjà porté**.

```
bonus = V × n            V = Round(mult% / 100 × extraDmg[level−1])     n = TilesMovedThisTurn
```

appliqué par le canal `attacker_additive_pre=True` existant — additif **par coup**, **avant**
perçage/armure, puis traversant le `%-list`.

| | #312 (`écart = 624 × n × M`) | #322 (le pipeline) |
|---|---|---|
| (2,0) n=1 M=1.25 | 1624 | 1624 |
| (2,1) n=2 M=1.25 | 2248 | 2248 |
| (3,2) n=3 M=1.25 | 2872 | 2872 |
| (4,1) n=4 M=1.25 | 3496 | 3496 |
| (3,0) n=2 M=1.875 | 3372 | 3372 |
| **(4,0) n=3 M=1.875** | **4308** ✗ | **4306** ✓ |

Le natif mesure **4306**. `R2` n'était pas du bruit : c'était le modèle multiplicatif qui arrondissait
au mauvais étage. Sur `(4,0)` : `(400 + 1497/2) × 1.875 = 2153.4375 → 2153`, `× 2 coups = 4306` ;
le modèle multiplicatif reconstruisait `1500 + 624 × 3 × 1.5 = 4308`.

Et `R1` tombe avec : la magnitude n'est pas « une combinaison de 277 et 180 » à trouver, c'est
`Round(1.8 × 277) = **499**`, un **entier**, et l'écart de **624** est ce que 499 devient *après* le
pipeline (`(400 + 499/2) × 1.25 × 2 − 1000`). Les quatre régimes de config de #312 §5, **y compris
le bras `level=1` écarté comme « non linéaire »**, sortent du même calcul :

| `PassiveAbilityLevel` | `AbilityVariablesMultiplierPercentage` | `extraDmg[lvl−1]` | `V` | écart mesuré | modèle |
|---|---|---|---|---|---|
| 50 | 180 | 277 | 499 | 624 (n=1) | 624 |
| 50 | 100 | 277 | 277 | 346 (n=1) | 346 |
| 10 | 180 | 15 | 27 | 34 (n=1) | 34 |
| 1 | 180 | 5 | 9 | 12 (n=1) | 12 |
| 1 | 180 | 5 | 9 | **22** (n=2) | **22** |

Le bras `level=1` n'a rien de non linéaire : `(400 + 9/2) × 1.25 = 505.625 → 506` puis
`(400 + 9) × 1.25 = 511.25 → 511` — deux troncatures voisines, pas une anomalie.
Re-dérivation, sans aucun live : `python probe_322_exoarmour_magnitude.py`.

## 2. La chaîne native, lue au décompilé (build `rnca9r7q6c`)

```csharp
// IdunBattle.Entities.Effects.Loki.ModifiedExoarmour_ExtraDmgEffect
CreateEffectDamageBonusForAttack() = EffectBonus.ForAddition( OwnerIsCaster & IsMeleeAttack,
                                                              GetCurrentDamageBonus() )
GetCurrentDamageBonus()            = DSLFormulas.Multiply( ConfigVar(8 = extraDmg),
                                                           TilesMovedThisTurn(Self) )
CreateActiveCondition()            = AmountIsGreaterThanZero( TilesMovedThisTurn(Self) )
```

Trois lectures font la magnitude, et **aucune ne se devine** :

1. **`IdunBattle.Entities.Formulas.MultiplyAmount$$Calculate` est un produit d'ENTIERS** —
   `return (int)b.Calculate() * (int)a.Calculate();`. La valeur de config est donc arrondie **avant**
   d'être multipliée par le compte de tuiles ; il n'y a pas de Fix64 qui traînerait jusqu'au bout.
2. **`IdunBattle.Entities.Formulas.ConfigAmount$$Calculate`** →
   `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` →
   `$$TryGetVariableArrayForLevel`, dont voici le corps :

   ```csharp
   idx  = clamp( Math.Max(0, Level.ToZeroBasedIndex(level)), 0, arr.Length − 1 );
   v[i] = Int32.TryParse(arr[idx].Split(',')[i], out p) ? p : −1;
   if (this.<scalables @+0x28> != null && scalables.Contains(variableType))
       v[i] = (int) Fix64.Round( Fix64(level.multiplierPercentage) / Fix64(100) * Fix64(v[i]) );
   ```

   C'est **exactement** `magnitude.ability_var(..., multiplier_pct=…)` du port — même foyer, même
   arrondi, même gate `variablesAffectedByRarityBonus`. L'ancre est partagée avec `PowerTrip`
   (`armorIgnored[L50] = 277 × 1.8 → 499`, déjà bit-exacte live). Vérifié pour ce passif :
   `extraDmg` **est** dans `variablesAffectedByRarityBonus` (et `extraPierceRatio` ne l'est pas).
3. **`TilesMovedThisTurn` est le FACTEUR, pas un interrupteur.** Le bonus vaut `V × n` : la
   `CreateActiveCondition` (`n > 0`) est donc **redondante** avec la magnitude. Elle est quand même
   mirrorée (`is_active`), parce que le natif l'écrit — mais elle ne peut pas être le discriminant
   d'une valeur.

### D'où vient `n` — le compteur, ses quatre écritures et son reset

`IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` rend **`ActorStatisticsComponent
+0xf0`** — le composant que `IdunBattle.Operations.StartTurnOperation$$ResetUnit` passe à
`ActorStatisticsComponent$$ResetAttacksReceivedThisTurn`, PAS le `UnitComponent` (étiquette
corrigée par #335 ; elle n'a rien changé au port, mais elle change le point d'ancrage à hooker pour
`R2`). Ce champ n'est écrit que par `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` :

```csharp
if ((int)tiles < 1) return;   // no-op silencieux : 0 et négatifs ne comptent pas
comp->+0xec += tiles;         // cumul BATAILLE  (aucun lecteur porté)
comp->+0xf0 += tiles;         // cumul CE TOUR   -> TilesMovedThisTurnFormula
                              // +0xf4 = TilesMovedLastTurnFormula (roulé au reset)
```

**Quatre call-sites** (xrefs relues) : les DEUX branches de `MoveUnitOperation$$Execute`,
`IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` et
`IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved`.

**Le reset est en FIN de tour, pas au début** — `IdunBattle.Operations.EndTurnOperation$$Execute`
itère `StateExtensions$$GetAllUnits` et appelle, par unité,
`IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn(comp, wasOwnTurn)` :

```csharp
if (wasOwnTurn) comp->+0xf4 = comp->+0xf0;   // TilesMovedLastTurn
comp->+0xf0 = 0;                             // INCONDITIONNEL, pour TOUTE unité
```

`wasOwnTurn` = `PlayerComponent.CurrentlyOwnedUnitIds` du joueur qui finit **contient** l'unité.
⚠ `StartTurnOperation$$ResetUnit` ne touche NI `+0xf0` NI `+0xf4` — chercher le reset là est une
impasse.

`IdunBattle.Operations.MoveUnitOperation$$Execute` l'appelle sur **les deux** branches, et la
branche SIMULATION est le corps de `MoveUnitOperation$$GetNumTilesMovedForSimulation`, **inliné**
(ce qui explique qu'aucun xref d'appel ne pointe vers lui) :

```csharp
if (state.IsSimulating) {
    events.MoveUnit(unit, position, false);
    if (!options.<+0x16>) {
        num = 0;
        if (HasTriggeredAbility(unit, 0x5f9) || HasTriggeredAbility(unit, 0x4de)) {
            CalculatePaths(unit, movementStart, previous, startTile, endTile, options,
                           out path, out connectedPath);
            num = BattleQuery.GetNumTilesMoved(connectedPath);      // = Count − 1
        }
        RecordTilesMoved(unit, num, state);
    }
    UpdateCharging(...); return;
}
```

Trois conséquences, toutes portées :

* la prédiction depuis une tuile candidate voit **`compteur réel + tuiles du pas simulé`** (c'est un
  `+=`, pas une affectation) — même structure à deux termes que `prediction_has_moved` (#266) ;
* le chemin est celui de `IPathfinders.GetPath(GetPathfinderTypeForUnit(unit), …)` = le
  **WalkPathfinder**, exactement le pathfinder que la face MOUVEMENT du même passif utilise déjà
  (#304) — d'où le foyer partagé `walk_pathfinder.get_path_node_counts_by_pos` ;
* `0x4de` est `TriggeredAbilityType.SmashaEad` (résolu dans `enums.tsv`), l'autre passif qui a besoin
  du compte exact ; pour toute autre unité, `GetNumTilesMovedForSimulation` rend **0 sans même
  lancer le pathfinding** — ce gate est porté (`_needs_accurate_tiles_moved`), autant pour la
  fidélité que pour le coût.

## 3. Le port

| pièce | fichier | rôle |
|---|---|---|
| l'effet | `engine/entities/effects/loki/extra_damage.py::ModifiedExoarmourExtraDmgEffect` | gates + magnitude, mirror 1:1 |
| le gate partagé | `engine/entities/effects/base.py::tiles_moved_this_turn` | foyer unique du canal `att_ctx` |
| `n` prédictif | `engine/playbook/prediction/_shared.py::prediction_tiles_moved_this_turn` | réel + pas simulé |
| le seed | `engine/playbook/scene.py::_seed_condition_gated_owner_effects` | l'effet inactif n'est pas publié |
| le registre | `engine/entities/effects/factory.py` | `EFFECT_CLASSES` + `ABILITY_INIT_OWNER_EFFECTS` |

**Rien n'a été ré-ordonnancé dans le pipeline de dégât** : `ForAddition` écrit
`DamageModifiers.Addition @+0x10`, que `attacker_additive_pre=True` consomme depuis #75/#70.

### Ce qui a demandé de l'infra, et pourquoi

L'effet **existe dès le déploiement** (`ModifiedExoarmourAbility$$CreateBehaviour` =
`AddEffect(0x607) & AddEffect(0x608)`, une seule expression `AbilityBehaviour$$op_Addition`) mais
son `EffectComponent.IsActive` est faux tant que l'unité n'a pas bougé. Le canal `decisionView` par
défaut ne publie **que** les actifs — MESURE live sur la fixture : `1543 PierceReduction` présent dès
le déploiement, `1544 ExtraDmg` seulement avec `includeInactive`. D'où deux ajouts :

* **`BaseEffect.active_condition_ported`** — le flag capté décrit l'état RÉEL ; pour un effet dont la
  condition porte sur l'état SIMULÉ, le natif le **recalcule**
  (`RefreshEffectsOperation$$RefreshEffect` sur `RefreshTrigger.Simulation`). Le lire comme un filtre
  ferme le port à tort. Défaut `False` ⇒ blast radius nul sur les autres classes.
* **`_seed_condition_gated_owner_effects`** — pendant DÉCISION de
  `spawn.py::_owner_effects_from_abilities`, qui n'existait que côté COMBAT.

### La régression que le contre-bras de #312 a attrapée

La **première** version du seed lisait `GC.unit(visualId).passiveAbilities` — le **KIT**. Le
contre-bras (seed BC avec `PassiveAbilities: []`) l'a prise en faute immédiatement : le port
accordait le bonus à une Kimm qui **n'a pas** le passif en bataille, **+2806 de trop** sur la tuile
(4,0) (`4306` annoncé contre `1500` natif). Même piège que #264 côté traits.

La correction est un substrat d'**ENTITÉ** : `BaseEffect.seed_witness_effect`. Le témoin est
`ModifiedExoarmour_PierceReduction`, l'effet **frère** posé par la même expression et
**inconditionnel** (ses seuls membres natifs sont `.ctor` et `CreatePiercingMalusForDefense` — aucun
`CreateActiveCondition`), donc toujours publié. Sa présence atteste que le behaviour a tourné sur
CETTE entité.

## 4. Validation

Toutes les mesures via `probe_312_votan_prediction_gap.py` (étage PRÉDICTION champ à champ + étage
CONVERSION), fixture `MDA_FIXTURE` de #27-r1.

| bras | plateau / seed | `Damage` | config | paires | écart |
|---|---|---|---|---|---|
| nominal | MC1_67 / 909 | 1000 | L50, mult 180 | 14 | **0** |
| second `Damage` | MC1_67 / 909 | 2000 | L50, mult 180 | 14 | **0** |
| contre-bras (passif retiré) | MC1_67 / 909 | 1000 | — | 14 | **0** |
| régime config B | MC1_67 / 909 | 1000 | L50, mult **100** | 14 | **0** |
| régime config C | MC1_67 / 909 | 1000 | **L10**, mult 180 | 14 | **0** |
| second plateau | **C4_09 / 31337** | 1000 | L50, mult 180 | 7 | **0** |
| troisième plateau | **C1_25 / 2468** | 1400 | L50, mult 180 | 8 | **0** |

**85 paires, 0 écart.** Avant le port, le bras nominal divergeait de +624 à +2806 par tuile
(`44.395` contre `17.783` en utilité sur (4,0)).

Le troisième plateau apporte un discriminant qu'on n'avait pas cherché : `C1_25` place une tuile
`(1,3)` à distance **hex 1** de la cible mais **non adjacente au sens natif** (`boardGraph`) — le
natif n'y accorde aucun bonus, et le port non plus. Le gate `IsMeleeAttack` est donc confronté sur sa
frontière fine, pas seulement sur « loin/près ».

### Gardes (`tests/engine/test_votan_prediction_gap_live.py`, 6 tests)

Chacune **vue ROUGE** par mutation adversariale, message rapporté verbatim :

| garde | mutation | message obtenu |
|---|---|---|
| `conversion_stage_is_exact` | `damage_composite × 1.02` | `l'etage CONVERSION diverge sur 56 paire(s) [('on', 69, (3, 3), 7.1131, 7.2553), …] -- la localisation de #312 ne tient plus` |
| `..._without_the_passive` | seed sans le témoin d'entité | `sans le passif de Kimm, le port diverge du natif sur [(69, (3, 0), (3372, 4122), (1500, 2250)), (69, (4, 0), (4306, 5056), (1500, 2250)), …]` |
| `..._with_the_passive` | gate `IsMeleeAttack` retiré | `l'etage PREDICTION diverge ENCORE sur 6 paire(s) avec le passif : [(69, (3, 3), 4, (2096, 2572), (600, 900)), …]` |
| ″ | `multiplier_pct=100` figé | `… [(69, (4, 0), 3, (3058, 3808), (4306, 5056)), (69, (3, 2), 3, (2038, 2538), (2872, 3372)), …]` |
| `..._confined_to_melee_after_movement` | gate `IsMeleeAttack` retiré | `des paires divergent HORS du domaine de ModifiedExoarmour_ExtraDmgEffect (melee + TilesMovedThisTurn>0) : [(69, (3, 3), False, 4), …]` |
| `montage_is_discriminating` | mutation rendue inerte | `port PRIVE de ModifiedExoarmour_ExtraDmgEffect : AUCUNE paire ne diverge -- le montage n'active donc pas le passif et les gardes de fermeture ne mesurent rien` |
| `magnitude_generalises_across_config_regimes` | gate `IsMeleeAttack` retiré | `sous le regime de config alternatif [...=100], le port diverge sur [(69, (3, 3), (1430, 1730), (600, 900)), …] -- la magnitude est ajustee au regime nominal` |

La garde de montage a **deux volets** depuis #322 : (a) le plateau exerce les deux côtés de la
frontière mêlée/déplacement (héritée de #312) ; (b) le port **privé de l'effet** doit y re-diverger.
Sans (b), les gardes de fermeture seraient vertes sur un montage qui n'active jamais le passif.

### Non-régression (tests ciblés rejoués)

| fichier | résultat |
|---|---|
| `tests/engine/test_modified_exoarmour_live.py` (face MOUVEMENT, #304) | 12 passed |
| `tests/engine/runner/test_ischarging_extra_damage_live.py` (canal `att_ctx` voisin) | ″ |
| `tests/engine/runner/test_heavy_weapon_moved_prediction_live.py` | 7 passed |
| `tests/engine/test_prediction_trait_gates_live.py` | ″ |
| `tests/engine/runner/test_damage_roll_live.py` | 10 passed |
| `tests/engine/runner/test_effect_immunity_live.py` | ″ |
| `probe_181_targeting_gaps.py` | 97/97, **0 manquante** |
| `probe_273_gitignored_inputs.py --only-scan` | OK |

## 5. Un trou de HARNAIS trouvé en route (et refermé côté probe)

`MDA.build_fixture` lance `rl_duel build` avec `check=False` et `stdout=DEVNULL` : **un build refusé
ne lève rien**, et `_runner_id()` relit paisiblement l'ANCIEN runner du même `--state-file`. Le probe
mesure alors un bras qu'il croit neuf et rend des chiffres parfaitement cohérents… de la mesure
précédente.

**VÉCU sur ce cas** : un bras `--board C2_19 --damage 1400` (le plateau n'a que 3 spawns joueur pour
5 unités → `[error] 3 spawns joueur < 5 units`) a rendu, à la ligne près, les valeurs du bras
`C4_09 --damage 1000` d'avant. Sans vérification, il aurait compté comme un troisième plateau validé.

`probe_312.build_arm` **exige désormais un runner NEUF** et refuse franchement sinon (vu rouge sur ce
cas même). ⚠ **La cause racine est dans `probe_27_r1_massdriver_custom.py::build_fixture`, fixture
PARTAGÉE** — non modifiée ici (elle porte d'autres consommateurs, dont #305) : à durcir au même
endroit que `_assert_placed`, qui applique déjà exactement cette doctrine (« On refuse plutôt que de
mesurer du vide »).

## 5bis. La face COMBAT — `R1` FERMÉ (#335, 2026-07-31)

Le compteur est posé **au foyer, l'Operation de déplacement** — pas chez les appelants.

| pièce | fichier | mirror natif |
|---|---|---|
| le champ | `engine/runner/components.py::UnitComponent.tiles_moved_{this_battle,this_turn,last_turn}` | `ActorStatisticsComponent +0xec / +0xf0 / +0xf4` |
| l'écriture | `components.py::record_tiles_moved` | `UnitExtensions$$RecordTilesMoved` (`+=`, garde `< 1`) |
| l'appel | `runner/operations/movement.py::MoveUnitOperation.execute` | `MoveUnitOperation$$Execute`, branche réelle |
| le compte | `movement.py::_num_tiles_moved` | `BattleQuery$$GetNumTilesMoved(connectedPath)` = `Count − 1` |
| le graphe | `entities/pathfinding/board.py::Board.walk_maps_by_pos` | `IPathfinders.GetPath(GetPathfinderTypeForUnit(u), …)` |
| le reset | `runner/operations/turnflow.py::EndTurnOperation` → `reset_tiles_moved_this_turn` | `ActorStatisticsComponent$$ResetThisTurn` |
| la lecture | `components.py::unit_tiles_moved_this_turn` + `UnitEffectStateView["tiles_moved_this_turn"]` | `TilesMovedThisTurnFormula$$Calculate` |
| le threading | `runner/damage_model.py::attacker_modifiers` | l'`AbilityEntities` per-coup |

Trois lectures décident du port, et **aucune ne se devine** :

1. **La branche RÉELLE n'a PAS le gate `HasTriggeredAbility(0x5f9) || (0x4de)`.** Ce gate est propre
   à `MoveUnitOperation$$GetNumTilesMovedForSimulation` (économie de pathfinding en simulation). Un
   mouvement JOUÉ compte ses tuiles pour **toute** unité.
2. **`connectedPath` vient du MÊME pathfinder que `path`.** `MovementQuery$$GetConnectedPathTo`
   appelle l'overload `Pathfinders$$GetPath(unit, from, to, maxRange)` — celui **sans** type
   explicite, qui résout lui-même `GetPathfinderTypeForUnit(unit)`. D'où le foyer partagé
   `Board.walk_maps_by_pos`, extrait de `prediction/_shared.py` pour que les deux faces voient le
   même graphe (le champ `neighbours` BRUT, ni trié ni symétrisé).
3. **`MoveUnitOptions +0x16` existe pour empêcher un DOUBLE comptage.**
   `DisplaceUnitOperation$$Execute` fait `processor.MoveUnit(...)` **puis** `$$AddTilesMoved`, qui
   refait le `RecordTilesMoved` avec ses propres gates (`options+0x10` et
   `!IsEnemy(caster, target)` — seul un déplacement AMICAL compte). Les call-sites de déplacement
   forcé du port passent donc `record_tiles=False` (push, switch, lift-off de `TheQuickening`).

### Ce que la mesure live a tranché

Montage : `probe_335_tiles_moved_combat.py` (runner isolé, `catalog_inject` pour Kimm hors pool,
géométrie DRIVÉE, snapshot **avant** le pas, pas REJOUÉ offline, MT re-calé après le pas).

| plateau / seed | pas demandé | `n` porté | live | offline | `n` forcé à 0 | `n` forcé à 1 |
|---|---|---|---|---|---|---|
| MC1_67 / 909 | 1 | 1 | `[3980, 4303]` | **identique** | `[3357, 3680]` | (= live) |
| MC1_67 / 909 | 2 | 2 | `[5500, 5073]` | **identique** | `[4253, 3826]` | `[4876, 4449]` |
| C1_25 / 31337 | 1 | 1 | `[5233, 4301]` | **identique** | `[4610, 3678]` | (= live) |
| C1_25 / 31337 | **3 (hex)** | **4** | `[7049, 6124]` | **identique** | `[4554, 3629]` | `[5177, 4252]` |

La dernière ligne est le discriminant qu'on n'avait pas cherché : sur `C1_25`, un pas de distance
**hex 3** coûte **4 tuiles de chemin** (détour). Le natif facture 4, le port aussi — un port qui
aurait compté en distance hexagonale aurait rendu ~`6425` au lieu de `7049`. C'est ce qui prouve que
le compte vient du PATHFINDER, pas de la géométrie.

Le **reset de fin de tour** est confronté par sa CONSÉQUENCE (aucun capteur ne publie `+0xf0`) : la
même attaque, depuis la même tuile, un tour plus tard et sans bouger, rend `[4456, 4568]` live ET
offline ; en CONSERVANT le compteur du tour précédent le port rendrait `[5703, 5815]`.

### Gardes (`tests/engine/runner/test_tiles_moved_combat_live.py`, 8 tests)

`test_combat_damage_matches_live_for_each_step` · `test_bonus_is_not_vacuous` ·
`test_count_is_threaded_not_a_constant` · `test_effect_magnitude_scales_with_the_count` ·
`test_turn_end_resets_the_counter_live` · `test_end_turn_operation_zeroes_the_counter_offline` ·
`test_att_ctx_channel_is_threaded_by_the_runner` ·
`test_count_comes_from_the_pathfinder_not_hex_distance`.

Deux mutations adversariales, **vues rouges**, message verbatim :

| mutation | rouges | message obtenu |
|---|---|---|
| `att_ctx["tiles_moved_this_turn"]` NON threadé (l'état d'avant #335) | 4 | `pas de 1 tuile(s) (n=1) : le degat de COMBAT diverge -- live=[3980, 4303] offline=[3357, 3680] (delta/coup=[-623, -623])` ; `attacker_modifiers ne threade PAS la cle tiles_moved_this_turn dans l'att_ctx (cles=['att_pos', 'has_teleported', 'is_charging', …])` |
| `reset_tiles_moved_this_turn` neutralisé dans `EndTurnOperation` | 1 | `ActorStatisticsComponent$$ResetThisTurn : +0xf0 doit retomber a 0, obtenu 2` |

Non-régression rejouée après ce port : `test_votan_prediction_gap_live.py` + `test_modified_exoarmour_live.py`
(11 passed), `test_ischarging_extra_damage_live.py` + `test_turnflow_endturn_flags.py` (16 passed),
`test_damage_roll_live.py` + `test_turnflow_live.py` (4 passed), `probe_181` (97/97, 0 manquante),
`probe_120_pre_unit_ability_fork` (OK), `probe_273 --only-scan` (OK).

## 6. Résidus OUVERTS

* ~~**Terme RÉEL de `TilesMovedThisTurn` non mesuré — côté PRÉDICTION SEULEMENT.**~~ **FERMÉ côté
  OFFLINE (#340)** — `docs/rl/case-340-tiles-moved-prediction.md`. Ce résidu était classé « exige
  une réinjection » ; c'était faux pour la voie qui compte : `Scene.from_state` lit un ECS qui
  portait **déjà** le compteur depuis #335, et la face prédiction le reconstruisait à zéro. Le
  modèle à deux termes est désormais ATTESTÉ au décompilé —
  `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` **sauvegarde `+0xec` et
  `+0xf0` avant l'action simulée et les restaure après**, le pendant `$$DoActionInSimulatedOnSameTile`
  ne touche pas le composant. Mesuré bit-exact sur trois bras (`n` = 1, 2 et **6**, contrefactuel
  `n=0` à −1246 / −2494 / −7484), argmax **renversé** sur 11/35 points.
  **La voie live-capture est fermée à son tour (`#340-r1`, 2026-07-31)** — capteur déployé et
  CONFRONTÉ, les deux voies live bit-exactes sur 5 valeurs de `n` et 2 plateaux : `case-340` §8.
  Le contrôle du capteur y a trouvé un bug de repli d'offset (`#340-r2`, correctif livré, exige une
  réinjection) qui ne touche PAS `+0xf0`, donc pas ce cas.
* **`DisplaceUnitOperation$$AddTilesMoved` non porté.** Un déplacement FORCÉ (push, pull, switch)
  compte nativement ses tuiles par cette fonction, gatée `options+0x10 && !IsEnemy(caster, target)`
  — donc **seulement pour un déplacement AMICAL**. Les call-sites de déplacement du port passent
  `record_tiles=False` (sinon le port compterait là où le natif ne compte pas) : la dégradation
  résiduelle est un SOUS-comptage sur le seul cas amical. Même chose pour
  `ReviveUnitOperation$$SetRevivePosition`, 4ᵉ call-site natif de `RecordTilesMoved`.
* **Lift-off de `TheQuickening`.** Le natif fait `MoveUnit` vers une `UnitPosition` VIDE puis un
  `MoveIn` ; sur ce lift-off, `CalculatePaths` prend sa branche `Count(movementStartPosition) == 0`
  et rend `[endTile, endTile]` — soit **1 tuile**, quelle que soit la distance. Le port faisant
  l'échange DIRECT, ce chemin n'est pas reproductible : il n'enregistre rien (`record_tiles=False`)
  plutôt que de facturer une distance de MARCHE que le natif ne calcule jamais.
* **`ModifiedExoarmour_ExtraDmgEffect$$GetExtraDamageMultiplier`** (`TilesMovedThisTurn(Self)` seul,
  sans le `ConfigVar`) n'a **aucune xref de code** — seulement des références de table de méthodes.
  Non porté ; à relire si un jour une lecture d'UI/tooltip en dépend.
* **`connectedPath` vs `path`.** Le natif compte sur `BattleQuery$$GetConnectedPathTo` →
  `MovementQuery$$GetConnectedPathTo`, qui **densifie** le chemin du pathfinder (ré-insertion des
  tuiles intermédiaires entre deux nœuds distants de plus de 1, cas téléporteur/saut). Sur un chemin
  de marche ordinaire les deux listes ont la même longueur — les 85 paires mesurées ne les
  distinguent pas. Un porteur de `ModifiedExoarmour` avec un effet de mouvement spécial les
  séparerait.
* **`block_entering_positions` non dérivable.** `tile_effects_by_pos` porte des NOMS, la table de
  blocage des ids `EffectType` — le pathfinder ne facture donc pas les `10000 − elevation` que le
  natif applique aux tuiles bloquantes. Dégradation PERMISSIVE (chemin éventuellement plus court).
  Même résidu que la face MOUVEMENT (#304), et il vaut désormais pour les DEUX faces : la face
  COMBAT (`movement.py::_num_tiles_moved`) passe elle aussi une liste vide.
* **`SmashaEad` (0x4de) ne lit pas ce canal.** Son port bake la condition « a traversé ≥ 2 hexes »
  dans la matérialisation de l'effet ; il n'est donc pas inscrit dans
  `_TILES_MOVED_CARRIER_EFFECTS`. Le jour où il passera au canal, l'y ajouter.
* **Face DÉFENSE `ModifiedExoarmour_PierceReduction` (1543)** : hors périmètre, non confrontée ici.

## 7. Fichiers

| rôle | chemin |
|---|---|
| probe MODÈLE (offline, aucun live) | `scripts/python/probe_322_exoarmour_magnitude.py` |
| probe MESURE PRÉDICTION (2 bras, N plateaux, `--unit-stat`) | `scripts/python/probe_312_votan_prediction_gap.py` |
| probe MESURE COMBAT (N longueurs de pas, N plateaux) | `scripts/python/probe_335_tiles_moved_combat.py` |
| gardes PRÉDICTION | `scripts/python/tests/engine/test_votan_prediction_gap_live.py` |
| gardes COMBAT | `scripts/python/tests/engine/runner/test_tiles_moved_combat_live.py` |
| fixture réutilisée | `scripts/python/probe_27_r1_massdriver_custom.py` |
| face MOUVEMENT du même passif | `docs/rl/case-304-modified-exoarmour-move.md` |
| localisation d'origine | `docs/rl/case-312-votan-prediction-gap.md` |

Rejouer :

```bash
cd scripts/python
python probe_322_exoarmour_magnitude.py                                  # le modele, sans live
python probe_312_votan_prediction_gap.py --damage 1000,2000              # bras passif ON
python probe_312_votan_prediction_gap.py --damage 1000 --passive-off     # contre-bras
python probe_312_votan_prediction_gap.py --damage 1000 \
       --unit-stat "votanChampion:AbilityVariablesMultiplierPercentage=100"
python probe_312_votan_prediction_gap.py --board C4_09 --seed 31337 --damage 1000
python -m pytest tests/engine/test_votan_prediction_gap_live.py -q
```
