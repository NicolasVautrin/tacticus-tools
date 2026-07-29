# case-175 — `ctx["unit_traits"]` : 12 gates de tuile morts en silence

Build `gqfc5mff6c`. Verdict MESURE (probe `scripts/python/probe_175_tile_leaf_unit_traits.py`),
garde `scripts/python/tests/engine/test_tile_leaf_unit_traits_live.py`, montage reutilisable
`scripts/python/tests/engine/_tile_leaf_montage.py`.

## 1. Le defaut

`engine/utilities/tile.py` lit `ctx["unit_traits"]` **12 fois** (l. 233, 246, 320, 322, 337, 351,
392, 459 dans l'etat d'avant-fix) pour 7 feuilles du composite Tile(7). `tile_leaf_ctx`, l'UNIQUE
constructeur de ce dict pour les DEUX chemins natifs, ne l'emettait pas. `_has` etant strict
(`s = ctx.get(key); return bool(s) and val in set(s)`), une cle absente rend **False** — donc les
7 gates rendaient `0.0`, sans erreur ni test rouge : degradation **permissive**.

### Verdict mesure (avant fix)

Instrumentation des instances de `TILE_LEAVES` (capture des cles du `ctx` qui atteint reellement
`BaseUtility.evaluate`), runner `MC1_67`, 3v3 :

```
[MOVE]   appels=936  unit_traits PRESENT ? NON
[ATTACK] appels=78   unit_traits PRESENT ? NON
ctx keys = ['elev_by_pos','enemies','enemy_units','friend_positions','friend_units',
            'hpmax_by_id','neigh_by_pos','scene','uid','unit_triggered_abilities']
```

Les DEUX chemins (sweep MOVE via `MovementActionGenerator` -> `engine.move.best_move_faithful` ;
terme Tile(7) de l'ATTAQUE via `engine.playbook.base.tile_utility`) passent par le MEME
`tile_leaf_ctx` -> le defaut etait **symetrique**, pas d'asymetrie a arbitrer.

## 2. La source native

`IdunBattle.Entities.UnitExtensions$$HasTrait(unit, traitId)` delegue a
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, qui interroge **trois** collections du
composant :

| offset | role | lecture |
|---|---|---|
| `+0x50` | traits RETIRES | present -> `return 0` (court-circuit) |
| `+0x40` | traits de BASE | present -> `return 1` |
| `+0x48` | traits ACCORDES en bataille | present -> `return 1` |

Chaque feuille passe `case.unit` (`case@+0x10`, l'unite qui evalue la tuile) :
`CapturePointTileUtility.<d__3>` teste `HasTrait(unit, 2)` puis `HasTrait(unit, 0xd)` ;
`DespoiledGroundUtility.<d__5>` teste `0x7ea`, puis `0x1a`, puis `0x3ee` ; etc.

**Substrat offline** de la liste de BASE : le kit gameconfig (`UnitContext.traits =
gameconfig.unit(vis).traits`) **plus** le pseudo-trait de GRANDE-ALLIANCE — absent de tout kit,
derive du `GrandAllianceId` (mirror `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` :
Imperial -> `0x1a`=26, Xenos -> `0x3ee`=1006, Chaos -> `0x7ea`=2026). Les xrefs de `GetTrait` sont
toutes dans la couche META (`UnitProgression$$GetIdsOfFactionsByAlliance`, widgets de quete) : c'est
elle qui injecte le trait dans la BattleConfiguration, jamais le moteur de bataille.

Les collections `+0x50` (retires) et `+0x48` (accordes en bataille) ne sont **pas observables
offline** — limite ASSUMEE, ecrite dans la docstring de `unit_trait_ids`.

> **Depasse depuis.** `+0x48` (et `+0x40` sur octroi permanent) est porte depuis **#225**
> (`case-225-dynamic-trait-gates.md` : le leaf DSL `AddTrait` ecrit `UnitContext.traits`, lu par
> `entity_trait_names/ids`). `+0x50` est **ferme par #265**
> (`case-265-disabled-traits-aucun-ecrivain.md`) : ce n'etait pas une limite d'observabilite mais
> un champ **sans aucun ecrivain dans le binaire** — le veto de `HasTrait` est INERTE, il n'y a
> rien a observer.

## 3. Le fix

- **`engine/entities/traits/unit_trait.py`** (module d'autorite du mapping id <-> nom) recoit la
  primitive CANONIQUE : `GRAND_ALLIANCE_TRAITS`, `grand_alliance_trait_name(visual_id)`,
  `unit_trait_names(visual_id)`, `unit_trait_ids(visual_id)` (ids natifs, tries, cache LRU).
  Louder-on-bug : un nom gameconfig absent de l'enum leve `ValueError` (le catalogue est mesure
  complet, cf. `docs/rl/unit-trait-coverage.md`).
- **`engine/runner/abilities/behaviours/context.py`** : son `_grand_alliance_trait` **delegue**
  desormais a cette primitive (alias). Aucune 3e resolution — un 2e mapping
  `Imperial/Xenos/Chaos -> 26/1006/2026` aurait ete un fork de port.
- **`engine/utilities/tile.py::tile_leaf_ctx`** emet `"unit_traits": unit_trait_ids(me["visualId"])`.

### Co-gates metadata — pourquoi le fix ne suffisait pas seul

Les 8 sites de lecture ont TOUS un co-gate `meta` par-tuile. Mesure : **aucun** n'etait peuple.
Peupler `unit_traits` seul n'aurait donc change **aucun score** — port invalidable, donc speculatif.
Deux de ces co-gates etaient deja REMONTES par le RPC `tileMeta` et **jetes** par le port :

- `is_territory` <- `tileMeta.isTerritory` = `TileComponent+0x2e`, l'octet EXACT que lit
  `IdunBattle.Entities.TileExtensions$$IsTerritoryTile` ;
- `tile_effect_type_ids` <- `tileMeta.effects[].effectType` = `EffectComponent+0x58` (le port ne
  gardait que le NOM de l'effet, clef de poids BC de la feuille TileEffects(9)).

Ils sont desormais derives dans `AiDecisionContext` (`_tile_attribute_maps`), transportes par
`tile_leaf_ctx` sous forme de cartes par-position (comme `elev_by_pos`/`neigh_by_pos` deja
presents), et poses dans `meta` par `apply_tile_attributes` — appele par les DEUX constructeurs de
`meta` (`engine.move` et `engine.playbook.base.tile_utility`). `engine/ai/action_generators.py`
n'est pas touche.

## 4. Etat des 8 sites, apres fix

(numeros de ligne = etat APRES fix)

| tile.py | feuille | co-gate `meta` | etat | poids BC |
|---|---|---|---|---|
| 244 | `CapturePoint(24)` | `is_territory` | CABLE, 0 tuile | +/-300 |
| 257 | `PowerUp(26)` | `occupant_is_powerup` | co-gate absent | -300 |
| 331 | `DespoiledGround(28)` Chaos | `tile_effect_type_ids` | **CABLE + VALIDE LIVE** | -5 |
| 333 | `DespoiledGround(28)` Imp/Xenos | `tile_effect_type_ids` | **CABLE + VALIDE LIVE** | -25 |
| 348 | `SummonDislikeDoorOpening(29)` | `door` | co-gate absent | -50 |
| 362 | `HeroLikeDoorOpening(30)` | `door` | co-gate absent | -50 / (10-cost)*10 |
| 403 | `AttractMechanicals(57)` | `attract_mechanicals_neighbor` | co-gate absent | +10 |
| 470 | `MasterOfTheTutelaries(62)` | `movetowards_hexdist` | co-gate absent | -20 x d |

### Ce qui reste INEXERCABLE, et pourquoi (nomme, pas corrige a l'aveugle)

- **`CapturePoint(24)`** — le plumbing est fait, mais **0 tuile territoire** sur les seeds du
  harnais : `data/seed-bc.json` a `RuleSet: null` / `GameMode: Campaign`, et le territoire est un
  attribut du ruleset `TerritoriesRulesetBattleConfig` (modes Survival / SyncPvp), pas du board
  (aucun dump de `data/boards/` ne porte de champ territoire). Le +/-300 est donc **non confrontable
  live** sans injecter un ruleset Territories dans la seed BC — chantier distinct.
- **`PowerUp(26)`, `SummonDislikeDoorOpening(29)`, `HeroLikeDoorOpening(30)`,
  `AttractMechanicals(57)`, `MasterOfTheTutelaries(62)`** — leur co-gate n'est remonte par
  **aucun RPC** aujourd'hui. Points d'ancrage natifs a exposer (par ordre de cout croissant) :
  - `door` : `RoomTileType` (0=Floor, 1=Wall, 2=Door) est DEJA projete par
    `projectMatchState` (`frida/hooks/game/match-state.ts`, champ `roomTileType`) mais le RPC
    `tileMeta` ne le renvoie pas ; il manque encore l'etat OUVERT/FERME et le lien de porte
    (`BC.Board.Doors`, present dans 15 des 779 dumps de board) ;
  - `occupant_is_powerup` : occupant de tuile + predicat power-up (canal occupance) ;
  - `attract_mechanicals_neighbor` : voisinage x `ActiveAbilityType` 1118 sur les unites ;
  - `movetowards_hexdist` : distance hex a l'unite porteuse de l'ability/effet 1096 (derivable
    offline des positions, pas besoin de RPC).

## 5. Residus de FIDELITE reperes au decompile (hors perimetre, non corriges)

`DespoiledGroundUtility.<d__5>` et `ContaminatedUtility.<d__4>` commencent par un test
d'EXCLUSION que le port ne modelise que du cote Contaminated (`ctx.contaminated_excluded`,
jamais peuple) :

```
cfg = TryGetValue(this+0x60, 0x5c4)        # dict par EffectType
if (Contains(cfg, unit)) return 0;         # unite EXCLUE -> aucune penalite
```

Cote port, `DespoiledGroundUtility.evaluate` n'a pas d'equivalent : sur une unite exclue, il
sur-penalise. Le contenu de `this+0x60` (qui alimente cette exclusion) n'a pas ete RE'd ici.
A ouvrir si un agreement de decision diverge sur une tuile despoilee.

## 6. Validation

- **Garde vue ROUGE par mutation, avant/apres** (`test_tile_leaf_unit_traits_live.py`) :
  - M0 = cle `unit_traits` retiree (etat exact d'avant-fix) -> **4/4 rouges** ;
    `chemin MOVE : le ctx qui atteint BaseUtility.evaluate N'A PAS 'unit_traits' -> les 7 feuilles
    a gate de trait ... rendent 0.0 EN SILENCE` (MOVE : 234 appels, ATTACK : 26) ;
  - M1 = source des traits videe (`unit_traits: ()`) -> 3/4 rouges ;
  - M2 = derivation de grande-alliance neutralisee -> 3/4 rouges, dont
    `le ctx du porteur ne porte pas le trait Chaos (2026) : unit_traits=(16,1039,1058,2020)` —
    c'est la garde du piege « le trait d'alliance n'est dans AUCUN kit gameconfig ».
- **Mesure avant/apres, gate DespoiledGround** (montage `_tile_leaf_montage`) : le NATIF pose
  l'effet de tuile `DespoiledGround` (1476) via `LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`
  (volet 2 du kit, non porte offline -> c'est bien le moteur natif qui fabrique l'etat).
  Sur la tuile despoilee `(6,8)` :

  | mesure | avant | apres |
  |---|---|---|
  | `DespoiledGroundUtility` — porteur Chaos | 0.0 | **-5** (BC `ChaosAffectedUnit`) |
  | `DespoiledGroundUtility` — cible Imperial | 0.0 | **-25** (BC `ImperialAndXenosAffectedUnit`) |
  | tuile temoin `(0,0)` (sans 1476) | 0.0 | 0.0 |
  | composite `Tile(7)@(6,8)` (Imperial) | **5.0** | **-20.0** (delta -25 exact) |

- **Non-regression** : `test_playbook_live.py` + `test_stay_in_place_live.py` (5 passed),
  `test_doctrina_gate_cap_live.py` + `test_line_elevation_gate_decision_live.py` (6 passed),
  `test_revitalizing_malignancy_live.py` + `test_combat_restoratives_live.py` (5 passed — la
  delegation de `_grand_alliance_trait`).

### NON couvert

- Le `+/-300` de `CapturePoint(24)` (cf. §4).
- La confrontation du terme Tile(7) au SCORE NATIF par-feuille : elle exigerait
  `aiUtilityTrace`/`movement-trace`, dont les hooks sont **session-globaux** et posent un
  `Interceptor.attach` sur `Dictionary<string,int>.TryGetValue` (chemin hot) — proscrit tant que
  d'autres agents partagent la session. La validation porte donc sur l'ETAT (l'effet 1476 est bien
  pose par le natif et lu par le port) et sur les poids BC, pas sur une egalite de score natif.
- ~~Les traits `+0x48` (accordes en bataille) et `+0x50` (retires) du `BaseUnitComponent`.~~
  `+0x48` porte par **#225** ; `+0x50` ferme par **#265** (aucun ecrivain dans le binaire, donc rien
  a couvrir) — cf. l'encart du §2.
