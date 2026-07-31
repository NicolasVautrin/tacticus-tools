# case-340 — la face PRÉDICTION lit le compteur RÉEL de `TilesMovedThisTurn`

**Statut : FERMÉ — les deux voies.** Le volet OFFLINE ci-dessous (2026-07-31), puis le volet
LIVE-CAPTURE (`#340-r1`) une fois le capteur déployé : **§8**. Ce dernier a trouvé, au passage, que
le capteur lisait **deux de ses trois champs à `comp - 1`** — un bug de repli, pas de RE.

**Statut du volet OFFLINE : FERMÉ** (2026-07-31). Résidu `#322-r2`, classé « exige une réinjection » :
**c'était faux pour la moitié qui compte**. La voie que la chaîne de décision emprunte
(`Scene.from_state`) lit un ECS qui **portait déjà le compteur** depuis #335 — la face prédiction le
reconstruisait à zéro. Même forme que **#267** (traits reconstruits alors que le runner les tenait)
et **#266** (flag `Moved` non câblé) : *une face qui LIT ce que l'autre TIENT*.

Ce qui restait bloqué par un capteur : la voie **live-capture** (`from_predictor_sctx`), dont le
câblage Python était posé et inerte (tri-état) tant que le hook n'était pas déployé. **C'est le
volet `#340-r1`, fermé au §8.**

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

* ~~**Capteur `+0xf0` non déployé (`#340-r1`).**~~ **FERMÉ (§8)** — le capteur est déployé et
  CONFRONTÉ ; les deux voies live sont bit-exactes sur 5 valeurs de `n`, 2 plateaux.
* ~~**`load_state` ne seede pas le compteur.**~~ **FERMÉ (§8)** — `load_state(actor_stats=…)` +
  `snapshot._load_actor_statistics`.
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
| probe `#340-r1` (capteur + 2 voies live + garde, §8) | `scripts/python/probe_340_r1_actorstats_live.py` |
| gardes `#340-r1` | `scripts/python/tests/engine/test_actorstats_sensor_live.py` |
| harnais réutilisé | `scripts/python/probe_335_tiles_moved_combat.py` |
| le cas amont | `docs/rl/case-322-modified-exoarmour-extradmg.md` |

```bash
cd scripts/python
python probe_340_tiles_moved_prediction.py --steps 1,2 --rival-step 2
python -m pytest tests/engine/test_tiles_moved_prediction_live.py -q
```

---

## 8. `#340-r1` — le capteur déployé, et le bug qu'il portait

**Statut : FERMÉ** (2026-07-31). Les deux voies LIVE lisent le compteur. **Et le contrôle du
capteur a trouvé un bug que la RE ne pouvait pas voir : deux de ses trois champs lisaient
`comp - 1`.**

### 8.1 Le contrôle — pourquoi on ne croit pas un capteur sur parole

Les offsets `+0xec` / `+0xf0` / `+0xf4` sont attestés par le décompilé (relu sur `rnca9r7q6c` :
`UnitExtensions$$RecordTilesMoved` écrit les deux premiers, `TilesMovedThisTurnFormula$$Calculate`
rend `+0xf0`, `TilesMovedLastTurnFormula$$Calculate` rend `+0xf4`,
`ActorStatisticsComponent$$ResetThisTurn` fait `if (wasOwnTurn) +0xf4 = +0xf0; +0xf0 = 0`). Mais les
**noms** passés à `getFieldOffset` ne sont pas vérifiables offline (aucun `fields.tsv`), et un hook
qui lit au mauvais endroit **ne lève rien** — il rend un entier plausible.

Le discriminant n'est donc pas une valeur, ce sont les **deux transitions** du composant, exigées
sur chaque champ :

| | un pas de `n` tuiles | `EndTurnOperation` |
|---|---|---|
| `+0xec` battle | `+= n` | inchangé |
| `+0xf0` turn | `+= n` | **0** |
| `+0xf4` last | inchangé | `= +0xf0` |

Deux transitions différentes sur le même champ ne peuvent pas être un alignement heureux.

### 8.2 Ce que la mesure a trouvé

`+0xf0` : **exact**, sur 5 valeurs de `n` et les deux transitions. `+0xec` et `+0xf4` :
**-1201836032 tous les deux**, constants, insensibles au pas comme au reset.

**La même valeur aux deux offsets est la signature** : les deux lisaient la **même adresse**.
Cause racine, lue dans `frida/hooks/il2cpp/helpers.ts` — `getFieldOffset` rend **`-1`** sur un nom
absent, et l'idiome `getFieldOffset(k, "X") || 0xec` ne teste que `0`, or **`-1` est *truthy* en
JS**. Le repli décompilé n'était donc **jamais** pris : l'offset restait `-1` et le hook lisait
`comp - 1`. Seul `TilesMovedThisTurn` porte un nom qui **existe** dans les métadonnées — d'où le
champ correct au milieu de deux faux, et d'où le fait que le cas lui-même n'était pas bloqué.

Ce n'était **pas une erreur de RE** : les trois offsets étaient justes. C'était un repli qui ne se
déclenchait pas.

**Correctif au foyer** : `helpers.ts::fieldOffsetOr(klass, name, fallback)` (`off >= 0 ? off :
fallback`), qui rend l'idiome faux inexprimable. Les **14** call-sites du pattern y passent
(`rpc-snapshot` 8, `effects` 8, `projection` 1) — même bug latent partout, même réinjection ; aucun
changement de comportement quand le nom existe. ⛔ **Exige une réinjection pour prendre effet.**

Côté port, `snapshot._load_actor_statistics` **refuse une valeur négative** : les trois champs sont
des compteurs à incréments `>= 1` (`RecordTilesMoved` sort sur `if ((int)tiles < 1) return;`), donc
un négatif dénonce une **lecture** invalide, jamais un état de jeu — on ne l'ingère pas dans l'ECS.

### 8.3 Le port

| pièce | fichier |
|---|---|
| voie `load_state` | `engine/runner/snapshot.py::load_state(actor_stats=…)` → `_load_actor_statistics` |
| voie live-capture | `scene.py::_tiles_moved_from_actor_stats` (posée par #340) — désormais ALIMENTÉE |
| le capteur | `frida/hooks/features/ai-step/rpc-snapshot.ts::actorStats` |
| le repli correct | `frida/hooks/il2cpp/helpers.ts::fieldOffsetOr` |

### 8.4 Validation

`probe_340_r1_actorstats_live.py` — quatre volets : **V1** le capteur (deux transitions × trois
champs), **V2** `load_state`, **V3** live-capture, **V4** le garde anti-garbage. Chacun porte son
contrefactuel (canal retiré) ; une tuile où le contrefactuel rend la même valeur est dénoncée comme
INERTE.

| plateau / seed | bras | `n` | NATIF == PORT (deux voies) | contrefactuel |
|---|---|---|---|---|
| MC1_67 / 909 | 1 hex | 1 | `[7672, 10882]` | **−1246** |
| MC1_67 / 909 | 2 hex | 2 | `[8920, 12130]` | **−2494** |
| MC1_67 / 909 | 2 hex + **rival bloquant** | **6** | `[13910, 17120]` | **−7484** |
| C1_25 / 31337 | 2 hex + rival | 3 | `[10168, 13378]` | **−3742** |
| C1_25 / 31337 | 3 hex | 4 | `[11416, 14626]` | **−4990** |

Le bras rival est le discriminant **chemin-vs-hex appliqué au CAPTEUR** : l'ennemi au contact bloque
le passage, 2 hex coûtent 6 tuiles de chemin, et le capteur rend 6. Les valeurs reproduisent celles
du §3 — mais par les voies LIVE, là où le §3 passait par le rejeu offline, **qui masquait le trou**
(c'est le moteur qui reposait le compteur).

Gardes : `tests/engine/test_actorstats_sensor_live.py` (12 passed + 1 xfail). Le xfail est le
**cliquet du reinject** : il exige aujourd'hui le régime pré-correctif (les deux champs faux rendent
la MÊME valeur négative) et exigera le patron natif complet une fois réinjecté — dans les deux cas
il MESURE, au lieu de virer au vert à vide.

Quatre mutations adversariales, **vues rouges** :

| mutation | rouges | message obtenu |
|---|---|---|
| seed `load_state` retiré | 3 | `bras pas=1 : load_state(actor_stats=...) seede None au lieu de 1` |
| table live-capture vidée | 4 | `la table tiles_moved_by_id de la voie live est VIDE` |
| garde `< 0` retiré | 1 | `du garbage NEGATIF est entre dans l'ECS : battle=-1201836032 last=-1201836032` |
| comptage en distance HEX | 5 | `bras pas=2 : load_state seede 6 au lieu de 2` — le CAPTEUR compte le chemin, c'est le port muté qui a tort |

### 8.5 Résidus

* ⛔ **`+0xec` et `+0xf4` restent faux jusqu'à la réinjection.** Le correctif est livré ; aucun
  lecteur porté n'en dépend (`tiles_moved_this_battle` n'a aucun consommateur, `tiles_moved_last_turn`
  non plus), et le garde `< 0` empêche le garbage d'entrer dans l'ECS. À re-jouer après reinject :
  le xfail de `test_the_two_other_counters_are_measured_either_way` doit devenir un PASS.
* **Les 13 autres call-sites de `fieldOffsetOr` ne sont pas re-confrontés un par un.** Leurs noms
  existent (tous validés live de longue date), donc le correctif est un no-op pour eux
  aujourd'hui — mais c'est au prochain **changement de build** qu'il compte : un nom qui disparaît
  y produisait jusqu'ici du garbage silencieux, il produira désormais le repli décompilé.
* **Une seule tuile mesurante par bras**, structurellement : après un déplacement joué,
  `aiPlaybookPredict` ne rend plus rien depuis une autre tuile (déjà noté au §6). Les 5 bras
  compensent en variant `n`, pas en variant la tuile.
