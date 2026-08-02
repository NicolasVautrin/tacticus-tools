# case-443-r2-b1 — la face DÉCISION passe par la MÊME porte de canal que la face COMBAT

Résidu ouvert par #443-r2 (`case-443-r2-only-active.md` §5) : **la face DÉCISION est aveugle aux
effets INERTES**, là où le natif en voit. Écart chiffré par la mesure de #501 : **−35 points
d'utilité de paire**, exactement le poids BC `SUPPRESSIVEFIRE_TargetWithOverwatch`.

Fermé. Et la fermeture a rapporté **une décision de CIBLE** qui passe de MISS à MATCH sur une marche
d'agreement — sur un montage indépendant de celui qui a ouvert le résidu.

## 1. Le critère, avant la méthode

`playbook/scene.py::step_context` seede son `EffectsState` depuis le `dv` de son appelant. Tous les
appelants passaient le canal `decisionView` NU, qui **droppe** les effets à `EffectComponent.IsActive
@+0x5c` faux (`frida/hooks/game/effects.ts::readEffectsByUnit` : `if (info && !info.active &&
!includeInactive) continue`). Tout mirror d'un `HasEffect(..., onlyActive = 0)` rendait donc FAUX là
où le natif rend VRAI — sans erreur, sans crash.

La face COMBAT a sa porte NOMMÉE depuis #219 : `runner/snapshot.py::decision_view_seed_body`.
L'asymétrie était là, et la question binaire était : **la face DÉCISION peut-elle prendre la MÊME
porte sans déplacer autre chose ?**

## 2. L'inventaire — DÉRIVÉ, et il vaut 19, pas 9

`scripts/python/probe_443r2b1_decision_inactive_readers.py --inventory` (offline, ~20 s, dans la
banque). Il part du code exécutable (AST), pas d'une liste : toute fonction d'`engine/**` qui touche
`Scene.eff_state`, plus les appelants du foyer nommé `battle_query.scene_has_effect`, plus les
lecteurs de la liste BRUTE `<ligne>["effects"]`.

⚠ **Un nom d'attribut se lit sous DEUX formes, et n'en lire qu'une est un faux négatif silencieux.**
`scene.eff_state` est un `ast.Attribute` ; `getattr(scene, "eff_state", None)` — la forme
MAJORITAIRE ici, parce que la `Scene` est optionnelle sur la plupart des chemins — est un
`ast.Constant`. La 1re version du probe ne lisait que l'`Attribute` : **12 lecteurs au lieu de 19**,
et elle ratait `battle_query.scene_has_effect` LUI-MÊME, c'est-à-dire le foyer que la mesure de #501
a pris en flagrant délit.

Mesure du 2026-08-02 (à **re-dériver**, jamais citer) — substrat STRUCTURÉ, face DÉCISION :
**19 lecteurs**, 1 seam.

| classe | n | ce que ça veut dire | bouge ? |
|---|---|---|---|
| **PRÉSENCE** (`has_effect`, `by_unit`) | **13** | mirror d'`onlyActive = 0` ; ne filtre que `consumed` | **OUI** — il VOIT désormais l'inerte |
| ACTIVITÉ (`active_effects`, `Scene.effects`) | 4 | mirror d'`onlyActive = 1` ; conjugue flag ET `CreateActiveCondition` | non |
| indéterminé | 2 | `Scene.from_predictor_sctx` (câblage pur), `Scene.is_effect_target` (délègue à `carries`, déjà compté) | non |

Les 13 PRÉSENCE : `ai/action_generators::_heal_candidates`, `battle_query::scene_has_effect`,
`playbook/neuroparasite`, `playbook/noncomparable/doctrina_imperatives::_is_conqueror`,
`playbook/prediction/_shared::_needs_accurate_tiles_moved` et `::prediction_has_teleported`,
`playbook/prediction/ramming_speed::_has_effect_from_scene`, `playbook/scene::_camo_cloak_cover_keys`,
`::_seed_battle_counters`, `_SceneEffectTargetWorld::carries`, `::_seed_condition_gated_owner_effects`,
`playbook/suppressive_fire::_target_has_overwatch`, `utilities/tile::scene_tile_leaf_ctx`.

**Un lecteur qui ne bouge pas est un résultat.** Les 4 ACTIVITÉ ne peuvent PAS bouger : le flag les
filtre. C'est vrai en particulier de `utilities/wireweave_net::target_has_active_wireweave_net`
(1111) et de `playbook/savior_protocols::_target_has_active_markerlight` (1122) — deux effectTypes
que le canal ajoute pourtant bel et bien sur les montages mesurés.

**Face COMBAT : 0 lecteur concerné**, par construction — `State.effects` est seedé par `load_state`,
déjà sur le canal `includeInactive` depuis #219.

**14 lecteurs de la liste BRUTE**, et le probe imprime l'orthographe du RECEVEUR (`u`, `t`, `meta`,
`unit or {}`) : c'est ce qui discrimine mécaniquement une ligne d'UNITÉ (canal basculé) d'une ligne de
TUILE (`tileMeta`, canal NON basculé — ces lecteurs-là ne sont même pas sur le chemin).

## 3. La porte — le même foyer, pas un second mécanisme

`snapshot.decision_view_seed_body(rid, **extra)` devient la porte des **DEUX** faces. Côté DÉCISION
elle est posée aux trois sites de capture de PRODUCTION : `engine_validate.py` (la marche
d'agreement), `predict_sweep.py`, `predict_samples.py`.

Le canal `includeInactive` est un **sur-ensemble STRICT** du canal par défaut — le hook n'y fait
qu'UNE chose de moins (`!active` n'est plus droppé) ; le drop des `removed` et l'émission de la clé
`active` (`active: info?.active ?? true`) sont INCONDITIONNELS. Ce que le canal ajoute doit donc
atterrir dans **exactement un endroit** :

* **`EffectsState`** (STRUCTURÉ, porteur du flag par instance) — `has_effect` le voit, `active_effects`
  le filtre. C'est le fix ;
* **PAS** la liste BRUTE, dont les lecteurs n'ont aucun flag à consulter.

D'où la seconde moitié, `snapshot.active_only_rows` / `active_only_effect_rows` : la **projection
ACTIF-ONLY**, qui ramène un payload `includeInactive` EXACTEMENT au payload par défaut. Elle n'est
pas un mécanisme neuf : `snapshot._effect_names` faisait déjà cela sur la face COMBAT, et **il en est
désormais un consommateur** (un seul foyer). Appliquée aux deux seams de la face DÉCISION
(`scene.step_context` pour `sctx["units"]`, `ai/context.build` + `build_machine` pour
`ctx.units`/`ctx.me`), elle rend tout lecteur brut **INDÉPENDANT DU CANAL**. Sur un payload nu elle
est l'IDENTITÉ — la ligne n'est même pas copiée.

## 4. Ce que la bascule DÉPLACE — trois mesures, trois échelles

### 4.1 Le montage discriminant de #501, rejoué à l'identique

`probe_443r2_only_active_overwatch.py` (board `MC1_67`, seed 41504) rend les **mêmes chiffres**
qu'avant la tranche — c'est la garde de non-régression de ma propre correction :

```
A 1009 ACTIF    natif 40.043221   port[nu] 40.043221   port[porte] 40.043221
B 1009 INERTE   natif 40.043221   port[nu]  5.043221   port[porte] 40.043221
```

### 4.2 Balayage PAR PAIRE — `probe_443r2b1_pair_sweep.py`

Le critère est le **déplacement entre les deux canaux du port**, jamais l'écart au natif ; le natif
ARBITRE le sens (GAIN si le port s'en rapproche, RÉGRESSION s'il s'en écarte).

| montage | paires | bougent | GAIN | RÉGRESSION |
|---|---|---|---|---|
| 1v1 `MC1_67`/41504, stage #501 | 4 | 1 | **1** (`+35.000000`) | 0 |
| 3v3 `MC1_67`/41504, géométrie pilotée | 36 | 1 | **1** (`+35.000000`) | 0 |

**ANTI-MUET.** « 0 paire ne bouge » ne vaut RIEN si le canal n'ajoutait rien — c'est exactement le
vice de la contre-épreuve `CE3` de #443. Le rayon de souffle est donc mesuré par régime, et le
balayage ÉCHOUE s'il est nul partout. Sur le 3v3 : **+4 entrées** en régime A, **+5** en régime B,
sur 2 à 3 unités, types `1009`, `1014`, `1111`, `1345`, `1346`.

⚠ **Le premier 3v3 rendait « 0 bouge » pour une raison de GÉOMÉTRIE, pas de mécanique** : il plaçait
les deux camps sur deux anneaux CONCENTRIQUES, d'où des paires au CONTACT — et le prédicat natif de
`SuppressiveFire` y est NIÉ (`if (!AreEntitiesAdjacent(tile, target))`). Le montage place désormais
deux AMAS séparés (`gap = 4` ⇒ distances croisées ≥ 2), imprime les distances obtenues et **échoue**
si une paire est au contact. On pilote les positions, on ne subit pas la géométrie de spawn.

### 4.3 Marche d'AGREEMENT — `probe_443r2b1_walk_channel.py`

C'est l'échelle qui compte : une utilité qui bouge ne déplace la décision que si elle change
l'argmax. **UNE seule marche, DEUX décisions par pas** — le walk utilise le canal de production, la
sonde par-étage recapture le canal nu et redécide sur le MÊME état. (Comparer deux runners
« avant/après » serait FAUX : la marche MUTE l'état, deux runners divergent dès le premier
désaccord.)

```
MC1_67 / 41504, 3v3   14 pas, canal ajoute des inertes aux 14 (8 effectTypes)   0 decision deplacee
C4_09  /   777, 3v3   16 pas, canal ajoute des inertes aux 16 (8 effectTypes)   1 GAIN, 0 REGRESSION
```

Sur `C4_09`/777, l'agreement `ability` de la marche passe de **9/13 à 10/13**. Et le pas déplacé est
**attribué** puis **décomposé par étage**, pas constaté :

```
step 9 u92   nu = (ability, (4,4), 69, 86)    production = (ability, (4,4), 69, 84)
             natif = move (4,4), ability 69, cible 84
  u92 recoit du canal : rien
  u86 recoit du canal : rien
  u84 recoit du canal : 1111 WireweaveNet_CounterAttack, 1009 Overwatch_AutoAttack   <- les inertes
  etage [nu        ] cible u84 : utilite  3.763334   dont feuille TRIGGERED   0.000000
  etage [nu        ] cible u86 : utilite 37.773872   dont feuille TRIGGERED   0.000000
  etage [production] cible u84 : utilite 38.763334   dont feuille TRIGGERED  35.000000
  etage [production] cible u86 : utilite 37.773872   dont feuille TRIGGERED   0.000000
```

Le déplacement est **intégralement** dans la feuille des abilities déclenchées, et il vaut
**35.000000** — le même terme que #501, sur un board, un seed, un roster et un chemin de code
DIFFÉRENTS (la spine de décision complète, pas un `pairUtility` isolé). L'argmax bascule de 37,77 à
38,76 et rejoint le natif.

## 5. Les contre-épreuves — 6 crans, 6 mordent, et le sixième mentait

Chaque cran du cliquet a été muté, rejoué (rouge attendu), restauré, rejoué (vert attendu) :

| cran | mutation | verdict |
|---|---|---|
| [A] le STRUCTURÉ voit l'inerte | seed depuis la liste PROJETÉE (le bug d'avant) | MORD |
| [B] l'inerte ne contribue à rien | `active_effects` cesse d'honorer le flag | MORD |
| [C] la liste BRUTE reste actif-only | `units` non projetés | MORD |
| [D] projection = identité sur le canal nu | la projection copie toujours | MORD |
| [E] les 2 seams d'`ai/context` projettent | `build` sans projection | MORD |
| [F] tout consommateur de prod passe par la porte | site de capture sans la porte | MORD |

⚠ **[F] NE MORDAIT PAS dans sa première forme.** Il testait `"decision_view_seed_body" in src` : la
contre-épreuve a retiré l'APPEL dans `engine_validate.py` et le cran est resté **VERT**, parce que le
COMMENTAIRE qui explique la porte contient son nom. Un garde-fou qu'une phrase de prose désarme ne
garde rien — les trois prédicats de [F] se lisent désormais en **AST**.

C'est [F] qui garde le seul gisement que **notre propre cadence** rouvre : un nouveau consommateur de
la face DÉCISION qui capte son `decisionView` lui-même repart, par défaut, sur le canal nu.

## 6. Ce qui a été rejoué

* **Cliquets** : `pwsh -File scripts/ratchets.ps1` → **28 cliquets, BANQUE VERTE, mur 106,1 s**
  (2026-08-02, après ajout de `probe_443r2b1` à **31,8 s** — très en dessous du mur, coût marginal
  quasi nul). `probe_439` vert : la nouvelle entrée peut rougir.
* **Tests ciblés** (12 fichiers, 4 en parallèle, tous VERTS) : `test_443r2_only_active_overwatch_live`
  (7, dont la garde LIVE neuve), `test_443r2b1_decision_inactive_seed` (7), `test_360_mow_caster_oracle_live`,
  `test_aura_position_live`, `test_predictor_traits_live`, `test_prediction_trait_gates_live`,
  `runner/test_ability_hits_channel_live`, `test_443_savior_protocols_pair_term_live`,
  `test_443r1_savior_protocols_move_term_live`, `test_noblocking_prediction_live`,
  `runner/test_camo_cloak_dmg_reduction_live`, `runner/test_camo_cloak_seed_move_live`,
  `runner/test_damage_roll_live`, `runner/test_camo_seed_inventory_offline`.
  Les deux modules CAMO sont là parce que `1014 CamoCloak_DmgReduction` fait partie de ce que le
  canal AJOUTE sur les montages mesurés — c'était le risque le plus proche.

## 7. Ce qui n'est PAS couvert

* **Les MoW ne sont toujours pas seedées côté DÉCISION.** `step_context` ne seede son `EffectsState`
  que depuis `dv.units` ; `dv.mows[].effects` n'y entre pas (la face COMBAT, elle, les charge —
  `snapshot.py`, `_load_stats_and_effects`). Trou PRÉEXISTANT, indépendant du canal ; la bascule ne
  l'aggrave ni ne le ferme.
* **`tileMeta` n'est pas basculé.** Les effets de TUILE ont eux aussi un `includeInactive` côté hook ;
  aucun lecteur de tuile n'a été confronté ici.
* **L'attribution du GAIN de la marche est faite au niveau de l'ÉTAGE, pas du call-site.** Le
  déplacement est prouvé intégralement dans la feuille TRIGGERED et égal au poids
  `SUPPRESSIVEFIRE_TargetWithOverwatch` ; le probe ne va pas jusqu'à instrumenter le call-site
  `suppressive_fire::_target_has_overwatch` lui-même.
* **Les 13 lecteurs PRÉSENCE n'ont pas été confrontés un par un.** Ce qui est mesuré est l'effet
  AGRÉGÉ de la bascule (paires + décisions). Deux d'entre eux ont été confrontés nommément
  (`suppressive_fire`, via #501 et via la marche) ; les onze autres sont couverts par l'absence de
  régression sur 72 paires et 30 pas de décision, pas par une mesure dédiée.

## 8. Résidus NOMMÉS

* **`#443-r2-b1-r1`** — `battle_query::entity_has_effect` et son appelant
  `loki_custom::any_enemy_has_markerlight` lisent la liste BRUTE alors que le natif y est en
  PRÉSENCE. RE faite, littéral LU :
  `IdunBattle.AI.Playbook.Loki.ForwardObserversPlaybook$$CheckIfAnyEnemyHasMarkerLight` appelle
  `IdunBattle.Entities.EntityExtensions$$HasEffect(entity, state, 0x462, onlyActive = 0)`. Le port est
  donc **permissif-en-moins** : il ne verra pas un Markerlight inerte. La projection ACTIF-ONLY posée
  ici **conserve** ce comportement (elle ne l'introduit pas) ; le fermer veut dire migrer ce lecteur
  du BRUT vers `EffectsState` — tranche distincte, avec sa propre confrontation. Porteur de `1185` :
  `tauSmnStealthSuit` (SUMMON) et `tauNpc5StealthSuit` (npc) ⇒ passe par `catalog_inject`.
* **`#443-r2-b1-r2`** — `battle_query::can_use_ability` mirroire `IdunBattle.Core.Services.
  AttackQuery$$CanUseAbility`, dont le maillon (2) est un **dispatch d'interface (slot 0x13)** non
  résolu ici : on ne sait donc PAS si le natif y consulte `IsActive` sur les effets
  `*_CantUseAbility`. Le port lit la liste BRUTE, désormais projetée ACTIF-ONLY = comportement
  strictement antérieur. Résoudre le slot (par `resolveVtableSlot` live, cf. #38b) tranchera.
* **`#443-r2-b1-r3`** — `1014 CamoCloak_DmgReduction` arrive maintenant INERTE dans le substrat de la
  face DÉCISION, mais `active_condition_ported` vaut **False** pour sa classe : `active_effects`
  l'exclut même quand la tuile SIMULÉE serait en couvert. Le natif, lui, recalcule
  (`RefreshEffectsOperation$$RefreshEffect` sur `RefreshTrigger.Simulation`). L'instance existe enfin
  côté décision — ce qui manque est le rallumage en simulation. Aucun changement de comportement dans
  cette tranche (avant : absente ; après : présente et éteinte).

## 9. Fichiers

* Porte + projection : `scripts/python/engine/runner/snapshot.py`
  (`decision_view_seed_body`, `active_only_effect_rows`, `active_only_rows`).
* Seams : `scripts/python/engine/playbook/scene.py::step_context`,
  `scripts/python/engine/ai/context.py::build` / `::build_machine`.
* Sites de capture : `engine_validate.py`, `predict_sweep.py`, `predict_samples.py`.
* Inventaire + cliquet : `scripts/python/probe_443r2b1_decision_inactive_readers.py` (`--inventory`).
* Mesures : `scripts/python/probe_443r2b1_pair_sweep.py` (`--stage 501|rings`, `--gap`),
  `scripts/python/probe_443r2b1_walk_channel.py`.
* Gardes : `scripts/python/tests/engine/test_443r2b1_decision_inactive_seed.py` (offline, 7 tests),
  `scripts/python/tests/engine/test_443r2_only_active_overwatch_live.py` (7 tests, dont la garde
  LIVE du partage STRUCTURÉ/BRUT).
