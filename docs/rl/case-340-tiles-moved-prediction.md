# case-340 — la face PRÉDICTION lit le compteur RÉEL de `TilesMovedThisTurn`

**Statut : FERMÉ côté OFFLINE** (2026-07-31). Résidu `#322-r2`, classé « exige une réinjection » :
**c'était faux pour la moitié qui compte**. La voie que la chaîne de décision emprunte
(`Scene.from_state`) lit un ECS qui **portait déjà le compteur** depuis #335 — la face prédiction le
reconstruisait à zéro. Même forme que **#267** (traits reconstruits alors que le runner les tenait)
et **#266** (flag `Moved` non câblé) : *une face qui LIT ce que l'autre TIENT*.

Ce qui reste vraiment bloqué par un capteur : la voie **live-capture** (`from_predictor_sctx`), dont
le câblage Python est posé et inerte (tri-état) tant que le hook n'est pas déployé.

## 1. Le fait, lu au décompilé (`rnca9r7q6c`)

```csharp
// IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate
return *(uint *)(GetComponent<ActorStatisticsComponent>(sel) + 0xf0);

// IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile
local_108 = comp[0xec];  local_104 = comp[0xf0];   // SAUVEGARDE avant l'action simulée
... SetMovedFlag -> l'action (dont MoveUnitOperation branche SIMULATION -> RecordTilesMoved) ...
comp[0xec] = local_108;  comp[0xf0] = local_104;   // RESTAURE après

// IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedOnSameTile
// ne touche PAS l'ActorStatisticsComponent — aucune sauvegarde, aucune écriture.
```

**C'est cette sauvegarde/restauration qui fonde le modèle à deux termes** : le compteur réel n'est
jamais pollué par les tuiles candidates déjà évaluées, donc `n_prédit = réel + pas simulé` — et une
prédiction depuis la tuile **courante** rend le compteur réel **tout nu**. Le port ouvrait sur
`real = 0` en dur.

## 2. Le port

| pièce | fichier |
|---|---|
| le champ + accesseur tri-état | `engine/playbook/scene.py::Scene.tiles_moved_by_id` / `tiles_moved_this_turn` |
| la voie OFFLINE | `Scene.from_state` ← `runner/components.py::unit_tiles_moved_this_turn` |
| la voie LIVE (inerte sans le hook) | `scene.py::_tiles_moved_from_actor_stats` ← capteur `actorStats`, re-capté par pas dans `refresh_shields` |
| la lecture | `playbook/prediction/_shared.py::prediction_tiles_moved_this_turn` (`real = scene.tiles_moved_this_turn(...) or 0`) |
| le capteur (LIVRÉ, **non déployé**) | `frida/hooks/features/ai-step/rpc-snapshot.ts::actorStats` → `tilesMovedThis{Battle,Turn}` / `tilesMovedLastTurn` |

`Scene.unit_state` n'a **pas** été touchée volontairement : y poser le compteur RÉEL seul fermerait
`ModifiedExoarmour_ExtraDmgEffect.is_active` pour une tuile candidate distante (la condition porte sur
l'état SIMULÉ, que la Scene ignore au moment où elle est construite). L'absence de la clé = « non
mesuré » y est la dégradation correcte.

## 3. Ce que la mesure a tranché

Montage `probe_340_tiles_moved_prediction.py` (harnais #335 réutilisé tel quel). Le même bras mesure
la **même tuile d'attaque de part et d'autre du même déplacement** :

* **phase A**, avant le pas → le natif voit `0 + k` (le régime des 85 paires de #322) ;
* **phase B**, après le pas → il voit `k + 0`. **Invariant de montage : NATIF(A) == NATIF(B).**

| bras (MC1_67 / 909) | `n` | NATIF | PORT | PORT `n=0` (avant #340) |
|---|---|---|---|---|
| pas 1 hex | 1 | `[7672, 10882]` | **identique** | `[6426, 9636]` (**−1246**) |
| pas 2 hex | 2 | `[8920, 12130]` | **identique** | `[6426, 9636]` (**−2494**) |
| pas 2 hex + **rival au contact** | **6** | `[13910, 17120]` | **identique** | `[6426, 9636]` (**−7484**) |

Le troisième bras est le **discriminant chemin-vs-hex**, obtenu en ramenant le second ennemi au
contact : il BLOQUE le passage (`WalkPathfinder$$UnitIsBlockedByEnemyUnit`), donc un pas de **2 hex**
coûte **6 tuiles de chemin**. Un port comptant en distance hexagonale aurait rendu `[8920, 12130]`.
C'est le pendant, en plus large, du `hex 3 → 4 tuiles` de #335.

**L'argmax est bien renversé — mesuré, pas supposé.** Balayage des PV de la cible et du rival sur
`[6426, 17120]` : **11/35 points changent la TÊTE du classement**, et le changement porte sur
l'**action** (cible et tuile), pas seulement sur l'utilité — ex. `hp=8208` : compteur lu → attaquer
`u79` depuis `(0,1)` ; compteur nul → attaquer `u77` depuis `(1,0)`. Gain du bonus jusqu'à **+101.7**
d'utilité contre une marge top1−top2 descendant à **1.6**.

⚠ Un montage à **une seule cible** rend `0/35` : l'absence de renversement y est une propriété du
montage, pas du terme. Il faut une action concurrente pour que la question ait un sens.

## 4. Gardes (`tests/engine/test_tiles_moved_prediction_live.py`, 8 tests)

`prediction_after_move_matches_live` · `prediction_before_move_still_matches_live` ·
`both_terms_are_the_same_sum` · `counter_is_not_vacuous` · `count_scales_with_the_step` ·
`count_comes_from_the_pathfinder_not_hex_distance` · `the_term_can_flip_the_argmax` ·
`scene_from_state_reads_the_counter`.

Deux mutations adversariales, **vues rouges**, message verbatim :

| mutation | rouges | message obtenu |
|---|---|---|
| `real = 0` (l'état d'avant #340) | 5 | `bras pas=1 (n=1) : la PREDICTION depuis la tuile courante diverge -- natif=(7672, 10882) port=(6426, 9636) (delta/borne=[-1246, -1246])` ; `aucun des 35 points ne renverse la tete du classement` |
| `Scene.from_state` ne publie plus le compteur | 6 | ″ + `` `Scene.tiles_moved_this_turn` rend None alors que l'ECS porte 1 `` |

Les deux gardes restées vertes sous mutation sont celles de **non-régression** (phase A) et de
**montage** (invariant NATIF(A)==NATIF(B)) : elles ne dépendent pas du terme réel, et c'est voulu.

Deux fautes de garde commises **puis vues** en route, toutes deux du type « un échec RENDU se lit
comme une mesure » : (a) un `[OK]` calculé sur des tuiles où **les deux côtés** rendaient `None` ;
(b) un comparateur d'argmax incluant `util`, qui faisait passer **100 %** des points pour renversés
alors que l'action était la même — puis, corrigé trop loin, un comparateur sur des clés **devinées**
qui rendait deux `None` égaux et **0 %**. Le comparateur retenu prend toutes les clés **sauf** le
scalaire d'utilité.

## 5. Non-régression (tests ciblés rejoués)

| fichier | résultat |
|---|---|
| `tests/engine/test_votan_prediction_gap_live.py` + `tests/engine/runner/test_tiles_moved_combat_live.py` | 14 passed |
| `tests/engine/test_modified_exoarmour_live.py` + `tests/engine/runner/test_heavy_weapon_moved_prediction_live.py` | 6 passed |
| `probe_181_targeting_gaps.py` | 98/98, **0 manquante** |
| `probe_120_pre_unit_ability_fork.py` · `probe_273_gitignored_inputs.py --only-scan` | OK |

## 6. Résidus OUVERTS

* **Capteur `+0xf0` non déployé (`#340-r1`).** Le hook `actorStats` publie désormais les trois
  compteurs de tuiles, mais **exige une réinjection** : tant qu'elle n'a pas eu lieu, la table
  `tiles_moved_by_id` de la voie live reste vide, l'accesseur rend `None` et la prédiction
  live-capture garde le seul terme « pas simulé » (comportement strictement antérieur). Les offsets
  sont attestés par trois lectures indépendantes (`RecordTilesMoved` écrit `+0xec`/`+0xf0`,
  `TilesMovedThisTurnFormula$$Calculate` lit `+0xf0`, `DoActionInSimulatedTile` les sauve/restaure) ;
  les **noms** de champs passés à `getFieldOffset` ne sont pas vérifiables offline (aucun
  `fields.tsv` dans `data/symbols/`) — d'où le fallback décompilé, contrat déjà en place pour
  `TotalAttacksMade`/`TotalTurnsWithAttacksMade`.
* **`load_state` ne seede pas le compteur.** Un `State` rechargé depuis une capture live (au lieu
  d'un pas REJOUÉ) part à zéro — même gap de capteur, refermé par le même hook. Aucune régression :
  c'est ce que le port faisait déjà partout.
* **Régime `réel > 0` ET `pas simulé > 0` NON CONFRONTÉ, et c'est structurel** : une unité qui a joué
  son déplacement ne peut plus bouger, donc `aiPlaybookPredict` ne rend plus rien depuis une autre
  tuile (mesuré : `None` sur toutes les tuiles non courantes en phase B). Les deux termes ne sont
  donc confrontés que **séparément** — ce que le mirror `real + (Count − 1)` couvre par construction.
* **Le port offline score encore des tuiles de mouvement après un déplacement joué** (l'argmax du
  bras rival retient `to=(1,0)` alors que l'unité a déjà bougé). Observé en marge, **hors périmètre**
  de ce cas : il touche `state_bridge._move_tiles`, pas la prédiction — dont chaque valeur est ici
  bit-exacte. À qualifier séparément.
* Hors périmètre, **nommés sans être ouverts** (résidus jumeaux de #335) :
  `IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved` et
  `ReviveUnitOperation$$SetRevivePosition` (2 des 4 call-sites natifs non portés → sous-comptage sur
  déplacement **amical**/revive, jamais sur-comptage), et le lift-off de `TheQuickening`.

## 7. Fichiers

| rôle | chemin |
|---|---|
| probe MESURE (2 phases, bras rival, sensibilité argmax) | `scripts/python/probe_340_tiles_moved_prediction.py` |
| gardes | `scripts/python/tests/engine/test_tiles_moved_prediction_live.py` |
| harnais réutilisé | `scripts/python/probe_335_tiles_moved_combat.py` |
| le cas amont | `docs/rl/case-322-modified-exoarmour-extradmg.md` |

```bash
cd scripts/python
python probe_340_tiles_moved_prediction.py --steps 1,2 --rival-step 2
python -m pytest tests/engine/test_tiles_moved_prediction_live.py -q
```
