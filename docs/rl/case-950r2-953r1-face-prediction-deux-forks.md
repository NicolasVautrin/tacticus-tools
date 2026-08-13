# #950-r2 / #953-r1 — la face PRÉDICTION jamais confrontée : **deux forks**, dont un que le résidu ne visait pas

Les deux résidus disaient la même chose : les passifs sont portés symétriquement dans les deux
façades, seul le COMBAT est mesuré, « un fork prédiction/combat y serait silencieux ». **Il y en
avait deux.** Aucun ne cassait de test ; aucun ne levait.

## L'instrument, mutualisé — `prediction_confrontation.py`

Oracle = `decisionView.attackPlans[].evals[].ranked[]`, les bornes `dmgMin`/`dmgMax` que le natif
publie **par tuile candidate** (`IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions`
construit une `UnitPosition(tuile de sélection)` posée comme CasterTile dans
`AbilityEntities..ctor`). Port = `prediction.make_normal_attack_predictions` sur la **même** tuile.
Recette non circulaire de `tests/engine/test_aura_position_live.py` (#153), extraite pour être
partagée par les deux résidus. Deux filtres, tous deux **comptés et rendus** (`predOptimistic`,
`dmgMax is None`) ; tolérance `TOL = 3`, celle de `predict_samples.sample_is_ok`, pas un ajustement
de cette tranche.

Les montages ne sont pas réécrits : les carrés géométriques de `probe_950` et `probe_953_954` sont
réutilisés tels quels, seule la face mesurée change.

## Fork 1 (#950-r2) — les réductions PLATES d'AURA n'étaient jamais consommées

Carré `aura`/`away` de #950, Jain Zar adjacente à l'attaquant, tout le reste égal :

| tuile candidate | oracle natif | port (avant) | écart |
|---|---|---|---|
| **(0,1)** — attaquant adjacent au porteur | (2045, 5055) | (6030, 9040) | **+3985** |
| (1,1) (1,0) (2,1) (2,0) | — | identiques | 0 |
| témoin `tl_away`, 6 tuiles | — | identiques | 0 |

`+3985 = 5 coups × 797` = `ConfigVar(0x12 = dmgReduction)` de
`TerrorsLament_DamageReductionEffect$$CreateEffectDamageMalusForDefense`. Le port appliquait déjà
l'autre moitié du passif (`TerrorsLament_HitReduction`, 6 coups → 5 : `7236 × 5/6 = 6030`), ce qui
rend l'écart lisible comme un fork de **canal**, pas de gate.

**Cause.** Dans `_add_positional_and_defender_mods`, la patte SELF *consommait* ses réductions
plates (`mods.additive -= sum(def_mods.flat_reductions)`) tandis que la patte AURA les *versait*
dans `mods.flat_reductions` — un bac que le pipeline de prédiction ne vide **jamais** (seuls le
combat, via `AttackDamageOperation._apply_defender_flat_reductions`, et la patte SELF le font).

**Fix.** La patte AURA consomme au même endroit. C'est le même placement parce que c'est la **même
boucle native** : le port scinde en deux pattes (Owner == cible / Owner != cible) un univers que
`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` parcourt
d'un seul tenant, board-wide, et verse dans un seul accumulateur.

## Fork 2 (#953-r1) — `scene.hpmax` structurellement vide sur la voie prédiction-live

`worldJakhal` « Macer » blessé (9 474 / 20 000 PV, **52,63 %** manquants) :

| tuile | oracle natif | port (avant) | écart | coups |
|---|---|---|---|---|
| (1,1) (0,1) (0,2) | (15342, 20760) | (10842, 16260) | **−4500** | 3 |
| (2,1) (2,2) | (10227, 13839) | (7227, 10839) | **−3000** | 2 |

**1 500 par coup** = `floor(52,63 % / hpPct = 10) = 5 paliers × extraDmg = 300`. Le port rendait
**exactement** la prédiction du porteur intact : le canal était entièrement muet, sur les 5 tuiles.

**La cause n'est pas celle que le résidu visait.** #953-r1 soupçonnait `adjacent_enemy_ids_of`,
résolue par deux substrats différents. Elle n'est pas en cause : les bras `oa_aura`/`oa_away`
d'`ObsessiveAnnunciation` concordaient **déjà** à l'unité avant tout correctif (7364/10316 contre
5903/8855, port == natif des deux côtés). Le fork était **un étage plus bas**, dans le substrat de
`Scene` : `hpmax_by_id` est vide sur la voie prédiction-live parce que `step_context` ne le produit
pas — et ne le **peut** pas : `decisionView.units[]` ne publie aucune clé de PV max (ses 17 clés
mesurées : `abilities, alive, ctrl, defeatedByMelee, effects, feet, hasAction, hp, id, killerId,
owner, parentId, parentMeasured, pos, ranged, team, visualId`). `scene.hpmax` rendait donc `None`
pour **toute** unité, la clé `StatAmount(Owner, Health, {Missing, Maximum})` arrivait en
`(9474, None)`, et le tri-état fermait le gate. Côté offline, `Scene.from_state` la remplissait
depuis `HealthComponent.hp_max` : **les deux voies de la même classe divergeaient.**

**Fix.** `from_predictor_sctx` prend `predictor["hpmax_eff_by_id"]` en repli —
`combatSnapshot.healthMax` = `GetStat(e, 5, part = Maximum)`, exactement le `Maximum` que lit
`Skullsmasher_ExtraDamageEffect$$GetMissingHealthSteps`. Pas `observeBattle.hpMax`, qui est la base
seule. `sctx` reste prioritaire s'il porte un jour la clé.

## Ce que ça dit du gisement

Le premier fork est un **canal non consommé**, le second un **substrat vide**. Aucun des deux n'est
un gate ni une formule — les deux façades appelaient bien le même code d'effet. Un port peut donc
être « symétriquement câblé » et rester muet d'un côté, et c'est **exactement** ce que les deux
résidus annonçaient sans pouvoir le montrer : la seule chose qui les révèle est la confrontation à
l'oracle natif, tuile par tuile.

Le fork 2 porte au-delà de `Skullsmasher` : `scene.hpmax` était `None` pour **toute** unité sur
cette voie, donc **tout** consommateur de PV max en prédiction se dégradait en silence. Le
recensement de ces consommateurs n'est pas fait ici → résidu **#953-r5**.

## Validation

Chaque garde a été **vue rouge par mutation avant son fix**, message verbatim :

* `test_950r2_prediction_aura_live.py` — rouge sur `tl_aura` seul, vert sur `tl_away`, ce qui
  localise l'écart sur la géométrie du passif et non sur un terme de base ;
* `test_953r1_prediction_passifs_live.py` — sous retrait du repli, 2 étages sur 3 rougissent, et le
  message désigne le **substrat** (`scene.hpmax(u<id>) rend None`), pas la valeur.

Les deux fichiers assertionnent leur propre **régime discriminant** (le porteur porte ses effets ;
le natif sépare bien les deux bras ; au moins une ligne existe) : sans ce cran, un port qui
n'appliquerait *aucun* canal serait vert des deux côtés — l'état exact qui précédait.

Non-régression, **82 tests live verts** : `test_950_terrors_lament_tough_to_kill_live` (19),
`test_953_954_skullsmasher_obsessive_annunciation_live` (20), `test_952_hunters_beyond_death_live`
(7), `test_predictor_traits_live` (7), `test_prediction_trait_gates_live` (6),
`test_350_prediction_average_forms_live` (5), `test_950r2_prediction_aura_live` (3),
`test_953r1_prediction_passifs_live` (3), `test_nightshroud_combat_live` (2),
`test_psychic_fortress_aura_live` (2), `test_predict_live` (2), `test_aura_position_live` (1),
`test_heavy_weapon_moved_prediction_live` (1).

## Non couvert

Les autres bras de `probe_953_954` (`oa_melee`, `oa_crit*`, `sk_stun`, `sk_nostun`) ne sont pas
confrontés en prédiction ; seul le couple porteur/témoin de chaque passif l'est. Et la face
prédiction des **abilities** (`prediction/abilities.py`) n'est pas touchée : seule l'attaque
normale est mesurée ici.
