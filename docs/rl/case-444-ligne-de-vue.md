# #444 — `TargetIsUnobscured` : la LIGNE DE VUE, armée pour les 103 masques, portée

**Livré le 2026-08-01.** Build de référence : `rnca9r7q6c`.

## 1. La règle, relue verbatim

`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments), **dans**
le bloc `if (!ignoreRangeChecks)`, juste APRÈS le volet portée et AVANT `TargetIsSummon` :

```
tiles = this.GetTilesObscuringTerrain(caster, casterTiles, pcVar12, options);
if (tiles == null) throw;
if (0 < tiles.Count) return <box ObscuredTerrainBrokenTargetingRule(tiles)>;   // get_Type = 0x1000000
```

Elle n'est **gatée par aucun bit** — pas même par le sien (24), qui n'est que le code rendu. Elle
n'est pas non plus gatée par la branche de portée : un `UseWholeBoard` saute le calcul de distance,
pas la ligne de vue. Sa place dans la cascade fixe la raison : hors de portée **et** masquée rend
`TargetIsInRange`.

`TargetingQuery$$GetTilesObscuringTerrain` (surcharge LISTE) porte **cinq** conditions, dont trois
antérieures aux bits :

| # | condition | effet |
|---|---|---|
| 1 | `config.EnableObscuringTerrain` (`TargetingConfiguration+0x10`) | à faux → set vide |
| 2 | `UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt(target, caster)` | cible AMIE → set vide |
| 3 | `HasTrait(caster, 0x3ed IndirectFire)` | retire le SEUL volet élévation |
| 4 | `AllowObscuredTargetByElevation` (bit 25) | idem |
| 5 | `AllowObscuredTargetByWalls` (bit 26) | retire le volet murs |

Le masque des murs est posé **par défaut** : sans le bit 26, `obscuringType >= 4`, donc le
court-circuit `t2 == 0` exige les DEUX désarmements. **19 abilities du registre** posent au moins un
des deux bits (`0x6000000` chez 13 d'entre elles).

`MovementQuery$$GetTilesObscuringTerrain` (`idun.meta.ObscuringType` : `None=0, Elevation=2, Wall=4,
All=6`) trace **deux** lignes `from -> to` par `MovementUtil$$DrawLineBetweenCoordinates`, qui ne
diffèrent que par le SIGNE d'un nudge constant — `MovementUtil$$.cctor` :
`FloatCubeCoordinate(1e-6, 2e-6, -3e-6)`, la valeur canonique « Red Blob ». Puis :

* `FirstOrFallbackIfOutsidePlayableArea` remplace une ligne qui sort du plateau par l'autre ;
* **`2 < lineA.Count`** — donc **distance 1 : JAMAIS obscurci**, murs compris. C'est structurel, pas
  un gate d'adjacence à ajouter ;
* élévation : `DetermineBlockingTiles(1, elev(from))` et `(Count-2, elev(to))` — seulement les deux
  tuiles **adjacentes aux extrémités**, `elev(mid) - ref >= 2`, comparaison SIGNÉE (une tuile plus
  basse n'obscurcit jamais). Fat-line (candidates différentes) → **ET** des deux ;
* murs : **toute** la ligne, endpoints compris, même ET de fat-line, sur `TileComponent.IsWall @+0x41`.

## 2. Ce que le port savait de l'obstruction — la leçon de #436 appliquée

La vérification exigée par le brief (« la règle ne sert à rien si sa donnée n'existe pas ») a rendu
**quatre** pièces présentes et **une** absente :

| donnée native | côté port | verdict |
|---|---|---|
| élévation de tuile | `Board.elevation` | présente |
| `TileComponent.IsWall` | `Board.is_wall` (publié par `boardGraph`) | présente — le résidu « `wall_by_pos` À PLUMBER » de #49 est **clos** |
| `GetTileAt` null | `Board.id_at -> None` | présente |
| `BoardComponent$$IsPositionInside` | rectangle englobant des tuiles captées | présente (approximation nommée) |
| `TargetingConfiguration.EnableObscuringTerrain` | **aucun canal** | ABSENTE |

Ce champ n'est ni un état dynamique ni un composant d'entité : c'est un champ de la
**BattleConfiguration** (`BC.Targeting`), qu'aucun RPC ne publie. `State.enable_obscuring_terrain`
le porte, avec pour défaut la valeur **lue** dans `data/seed-bc.json` (`true`) — la seed dont partent
tous les runners — et non une déduction ; `load_state(targeting_config=...)` permet à un appelant qui
connaît SA BC de la poser. `test_obscured_targeting_live::test_la_seed_versionnee_active_bien_l_obscurcissement`
relit la seed et rougit si elle change, pour que le défaut ne devienne pas une invention en silence.

## 3. Le canal de mesure MENTAIT, et c'est ce qui rendait la règle invisible

`frida/hooks/features/ai-step/rpc-targeting.ts::decodeRule` ne sait extraire le flag que d'un
`GenericBrokenTargetingRule`. Pour toute autre classe il publie **`hex: "0x0"`**. Or la ligne de vue
est la SEULE règle du filtre dont le refus passe par une autre classe. Conséquence :

> tout lecteur qui fait `int(payload["hex"], 16)` lit **0** — « cible VALIDE » — sur un refus.

Tant que le port ne portait pas la règle, les deux côtés rendaient `0` : **accord parfait, faux des
deux côtés**. C'est exactement le mode de défaillance `feedback_agreement_worthless_on_shared_stale_input`,
et il explique pourquoi aucun des ~40 lecteurs de `ruleClass` du dépôt n'avait jamais vu ce refus.

Deux correctifs, l'un immédiat, l'autre en attente :

* `scripts/python/targeting_reason.py::native_target_reason` — le foyer de décodage : lit `hex`
  quand il porte l'information, retombe sur la CLASSE sinon
  (`ObscuredTerrainBrokenTargetingRule -> 0x1000000`). Correct AVANT comme APRÈS le correctif du hook ;
* le hook lui-même publie désormais le code de `get_Type` pour les classes non génériques.
  **Il demande une fenêtre de reinject** — la mesure de cette tranche a été faite sans lui, par le
  foyer Python.

## 4. La confrontation — `probe_444_obscured_targeting.py`

Board **`C1_09`**, choisi par un balayage OFFLINE des 779 boards versionnés : c'est celui dont la
plus grande part des paires (from, to) à distance 2..4 entre tuiles marchables est coupée par
l'élévation (**203 / 973, 20,9 %**). Le craft place, avec `Movement` monté à 20 pour que toute tuile
soit atteignable en un tour, **deux cibles à la MÊME distance 2** du caster — l'une derrière un
relief, l'autre à découvert. Cette égalité de distance est load-bearing : la portée PRÉCÈDE la ligne
de vue, donc un refus qui ne tomberait que sur la plus lointaine l'accuserait, elle.

| cible | d | natif | port | port AVANT (`AllowObscuredTarget`) | tuiles vues |
|---|---|---|---|---|---|
| `necroWarden` u84 (derrière le relief) | 2 | **`0x1000000`** | **`0x1000000`** | **`0x0`** | `1/3` |
| `necroWarden` u86 (à découvert) | 2 | `0x0` | `0x0` | `0x0` | — |
| `custoKyrus` (allié) | 3 | `0x4000` | `0x4000` | `0x4000` | — |

Accord **15/20** lignes, **0 désaccord imputable à cette tranche** (les 5 restants sont nommés au §6).
Une ligne refusée que le port **acceptait** avant : la dégradation permissive est fermée.

**Le désarmement est CONFRONTÉ AU NATIF**, pas seulement au port : sur la MÊME paire (u92, u84),
l'attaque normale (`0x4002`) rend `0x1000000` et `HeroicFusillade` 1180 (`0x6004002`) rend `0x0`.
Seule la permission change.

### Généralisation

Même verdict sur un montage entièrement différent — board `C1_05`, seed `31337`, autre roster adverse
(`deathBlightlord`) : craft `(0,3) / (2,4) / (0,5)`, natif `0x1000000` = port sur la cible obscurcie,
`0x0` des deux côtés sur la cible libre à la même distance.

### Trois contre-épreuves, chacune vérifiée mordante

| mutation | rouges |
|---|---|
| règle neutralisée dans la cascade (`if False and …`) | **4** |
| refus systématique (port TROP strict — l'axe inverse) | **5**, dont `test_axe_inverse_les_casts_legitimes_passent` |
| port trop strict au niveau du prédicat (`len(line_a) > 1`) | 7 (le craft lui-même devient impossible) |

**La première contre-épreuve a d'abord MENTI**, et c'est le point de méthode de la tranche : le
critère d'imputabilité était « le contrefactuel du champ fait disparaître le désaccord ». Or
neutraliser la règle rend `port == port_disarmed`, donc le désaccord se classait « PRÉEXISTANT » et
le probe rendait PASS avec 2 rouges seulement. Deux lecteurs qui partagent le même code muté
s'accordent toujours. Le critère est désormais « l'un des deux côtés vaut `TargetIsUnobscured` », qui
ne dépend pas du code mesuré → 4 rouges.

## 5. Ce qui a été joué (relevé daté)

`test_obscured_targeting_live` 8 ✅ · `test_targeting_masks_live` 13 ✅ ·
`test_ability_target_gate_live` 13 ✅ · `test_targeting_adjacency_rules_live` 22 ✅ ·
`test_splash_targeting_live` 10 ✅ · `test_summon_targeting_live` 6 ✅ ·
`test_target_is_healable_live` 3 ✅ · `test_taunt_targeting_live` 7 ✅ ·
`test_ability_target_gate_lot181_live` 26 ✅ · `test_targeting_rule_inventory` 17 ✅ ·
`test_targeting_options_sources` 5 ✅ · `test_targeting_options_masks_live` 4 ✅ ·
`test_astramilitarum_targeting_live` 4 ✅ · `test_runner_attack_live` 2 ✅ ·
`test_mow_targeting_predicate_live` 7 ✅ · `test_loki_solo_targeting_live` 5 ✅ ·
`test_deathguard_targeting_live` 6 ✅ — et la **banque de cliquets VERTE** (24 entrées, mur 115 s).

Ce périmètre large est délibéré : `abilities/targeting.py` est le foyer de TOUS les casts, et l'axe
restrictif de cette règle porte sur **103 masques**.

## 6. Résidus nommés

* **`#444-r1` — le hook `decodeRule` demande une fenêtre de reinject.** Le correctif est livré
  (`NON_GENERIC_RULE_CODES`) ; tant qu'il n'est pas injecté, tout lecteur qui n'passe pas par
  `targeting_reason.native_target_reason` lit `0x0` sur un refus de ligne de vue. Les ~40 lecteurs
  existants de `ruleClass` du dépôt sont dans ce cas — **aucun ne rougit** (mesuré : les 17 fichiers
  de test ci-dessus sont verts), parce qu'aucun de leurs montages ne réalise d'obstruction.
* **`#444-r2` — le slot 0 d'`idun.shared.collections.ISPSet<T>`** (la combinaison des sets quand le
  caster a plusieurs pieds) n'est pas résolu par son nom : générique pleinement partagé, absent du
  dump Frida, et l'index de `search_code` ne rend pas ses call-sites. Porté en **intersection**, par
  lecture SÉMANTIQUE — une union rendrait une unité multi-pieds strictement plus aveugle qu'une unité
  à un pied, ce que contredit le pendant CIBLE (`IsTargetUnitObscured` : obscurcie ssi TOUTES ses
  tuiles le sont). **Inerte pour tout caster à un pied** (le natif court-circuite sur `Count == 1`).
* **`BoardComponent$$IsPositionInside`** approximé par le rectangle englobant des tuiles captées
  (le `Board` du port n'a ni `Width` ni `Height`). Plus STRICT que le natif si le `boardGraph`
  publiait moins que le rectangle ; l'effet resterait borné au CHOIX de ligne, jamais au verdict.
* **Deux désaccords PRÉEXISTANTS**, mesurés par le probe et sans lien avec cette tranche (ils
  survivent au désarmement) : `1180 HeroicFusillade` — le natif rend `TargetMatchesDynamicRule`
  (`0x2`) à d=5/6, sa règle dynamique n'est pas portée ; `1202 VigilanceEternal` — le natif rend
  `TargetIsInRange`, son `TargetingRange` n'est pas lu côté port (`range=None` = aucun gate).
* **`IndirectFire` (trait 1005) NON CONFRONTÉ** : ses 9 porteurs sont des npc, un summon, et
  `astraOrdnance` — une MACHINE OF WAR, qui n'a aucune tuile, donc `casterTiles` vide et la règle
  inerte. Le désarmement par ce trait est porté, jamais exercé.

## 7. Re-dériver

```
python scripts/python/probe_444_obscured_targeting.py
python scripts/python/probe_444_obscured_targeting.py --seed 31337 --board C1_05 \
    --a-units "necroWarden,necroWarden,deathBlightlord,deathBlightlord"
python scripts/python/probe_429_targeting_rule_inventory.py --only-gaps
python -m pytest tests/engine/runner/test_obscured_targeting_live.py -q
```

Après cette tranche, `probe_429` compte **23** règles GATE non portées sur 46 (contre 24), et les
abilities touchées par au moins une règle non portée tombent de **103/103 à 88/103**. Le gisement
ciblé (hors règles armées par défaut) reste **26/103**. ⚠ Chiffres à re-dériver, pas à citer.
