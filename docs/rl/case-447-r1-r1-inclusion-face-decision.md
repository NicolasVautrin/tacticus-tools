# #447-r1-r1 — la branche INCLUSION du bit 15 sur la face DÉCISION, et deux bugs trouvés en la confrontant

**Livré le 2026-08-05.** Build de référence : `rnca9r7q6c`. Résidu de `case-447-r1`.

**Critère binaire** : sur la face **DÉCISION** (`ability_range._zone_contains_distance` →
`is_tile_in_range_of_any_ability`, oracle `aiMovableTiles {threat: true}`), le natif verse-t-il
la tuile du caster quand `CasterIsPossibleTarget` (bit 15) est armé — et le port le suit-il ?

**Verdict** : **OUI, confronté**, dans un régime **non dégénéré construit et vérifié**. Le blocage
annoncé par `case-447-r1` §8 est **périmé sur sa cause** et **soluble sur son effet**. Et la
confrontation a trouvé **deux bugs**, tous deux corrigés et gardés.

---

## 1. Le blocage annoncé, mesuré

> « son blocage (`orksRuntherd`/1045 annulé par `AttackQuery$$GetInvalidCasterReason`, **non
> porté**) est intact »

**Faux sur « non porté »**, et c'est une lecture du code courant :
`IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason` → `AActiveAbility$$GetInvalidCasterReason`
→ `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` **est** portée depuis
`#433-r4-r2-r1-r2-r2-r1-r1-r1-r4` (`engine.services.ability_caster_gates.invalid_caster_reason`,
onze règles dans l'ordre natif, relues à l'octet et re-confirmées ici).

**Vrai sur l'effet, mais c'est un fait de MONTAGE.** La règle-déléguée
`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetDynamicInvalidCasterReason`
rend `2` quand `GetSpawnTileSelector` est vide — « aucune tuile LIBRE adjacente au caster ET
adjacente à un ennemi ». Elle se lève en **posant un ennemi**, pas en changeant le port. Mesuré,
même ability, même masque, deux exemplaires dans la **même bataille** :

| poste | ennemi contre la sortie | `abilityReason.casterReason` | natif verse la tuile source |
|---|---|---|---|
| `orksRuntherd` @(1,5) | oui | `0` | **`[(2,4)]`** |
| `orksRuntherd` @(3,7) | non | `2` `TargetMatchesDynamicRule` | **`[]`** |

⚠ Le montage hérité ne mesurait plus rien pour une **autre** raison encore : re-joué le
2026-08-05, `probe_433_…_source_tile_zone --step live` rend pour `orksRuntherd`
« movable set VIDE », pas « natif = attaque normale seule ».

## 2. Le régime — construit, pas espéré

La réponse de l'oracle est l'**UNION sur toutes les positions candidates** : dès que deux d'entre
elles sont à portée l'une de l'autre, chacune est couverte **depuis l'autre** par l'attaque
normale, et le bit 15 ne décide plus rien. C'est le piège du `#447-r1` sous une autre forme.

Le montage l'évite par la **géométrie**, et le vérifie : chaque porteur est placé sur un
**CUL-DE-SAC** — une tuile marchable dont **une seule** voisine passe la porte d'élévation
`|dElev| < 2` de `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`
— et `overrideRange: 1` borne le pas. Le movable set est alors un **singleton**, ce que le probe
**assertionne** (`n_move == 1`, et la tuile est bien la sortie re-dérivée du board).

Le board n'est pas choisi à l'œil : `--step geometrie` re-dérive les culs-de-sac de
`data/boards/global/<board>.json`. **`C1_70`** en porte **5** (61 tuiles marchables) et a assez de
spawns joueur pour un roster de cinq ; les deux contraintes ensemble ne sont satisfaites que par
**4 boards** du corpus (`C1_70`, `C3_73`, `MC1_74`, `C1_06`) — `C4_05`, plus riche en culs-de-sac,
n'a que **3** spawns joueur et **refuse** le roster.

**Le régime dégénéré est MESURÉ**, par un 5ᵉ poste en terrain ouvert (degré 6) : `n_move = 6`, et
ses **6/6** positions candidates sont dans la menace — **bit 15 désarmé côté port compris**. Une
lecture faite là serait un accord entre deux modèles algébriquement identiques.

## 3. La confrontation

Un seul runner, cinq postes, `C1_70` :

| poste | ability | `rules` | `n_move` | natif verse la source | port |
|---|---|---|---|---|---|
| `astraCreed` @(2,1) | `1028 SupremeCommander` | `0x208000` | 1 | **`[(1,1)]`** | `[(1,1)]` |
| `astraBullgryn` @(6,5) | `1017 FragBomb` | `0x80040` | 1 | **`[]`** | `[]` |
| `orksRuntherd` @(1,5) | `1045 GetEmRuntz` | `0x8004` | 1 | **`[(2,4)]`** | `[(2,4)]` |
| `orksRuntherd` @(3,7) | `1045` | `0x8004` | 1 | **`[]`** | `[]` |
| `astraBullgryn` @(5,2) | `1017` | `0x80040` | 6 | `[6/6]` — DÉGÉNÉRÉ | idem |

`astraCreed` est le porteur le moins cher du gisement (§6 de `case-447-r1`) : `RANGE_SELF` + bit 15
et **aucun** gate caster, donc la zone de son ability est **exactement** `casterTiles` — tout ce
qu'elle verse est l'effet du bit. Son contrôle a le **même** `unit_threat_reach` (1) et une seule
ability active de chaque côté (re-dérivé, pas supposé).

Sur les quatre postes isolés, l'accord porte sur la **zone ENTIÈRE**, pas seulement la tuile
source : **FP 0 / FN 0**, résidu d'attaque normale **0**.

**Contre-épreuves** (le bras muté doit DIFFÉRER du témoin, et la mutation est relue *par le chemin
du port*, `ability_range._options_of`, pas par le nom importé — c'est ce qui avait rendu un faux
vert au premier jet) :

* bit 15 désarmé → `astraCreed` et l'ork qui passe **perdent** la tuile (le natif, lui, la verse) ;
  le contrôle ne bouge pas ;
* 4ᵉ gate court-circuité → le port verse `(3,6)`, que le natif **refuse**.

## 4. Premier bug — une portée NON RE-LUE annulait l'ajout aval

Les deux `AddRange(casterTiles)` vivent dans `TargetingQuery$$GetPossibleTargetsForOptions`,
l'**appelant** de `GetTilesInRange`, et ne consultent **ni la portée ni la branche**. Le port,
lui, court-circuitait en amont : `_ability_covers_tile` faisait
`base = tiles_in_range_reach(...); if base is None: return False`, et
`zone_contains_for_options` rendait `None` dès que `_range_terms` l'était.

**Gisement re-dérivé** : exactement **2** abilities ont `bit 15 | bit 57` et un
`tiles_in_range_reach` à `None` — `1215 InstrumentsOfVengeance` et `1216 MartialExemplar`, dont le
`range` est `None` **délibéré** (bloc `<preset>+0x08..0x1f` non résolu). Toutes deux sur le seul
`darkaBossLion` (npc) → **greffe** sur une unité du pool (`case-92` §5bis, recette de
`probe_27_r6`), placée sur un cul-de-sac.

| | natif | port AVANT | port APRÈS |
|---|---|---|---|
| `1215` greffée sur `darkaAsmodai` @(2,1) | **`[(1,1)]`** | `[]` | `[(1,1)]` |

Écart **RESTRICTIF**, corrigé en rabattant le triplet manquant sur `(None, False, False)` — portée
non décidable, ce que `_zone_contains_distance` rend déjà par `None` à toute autre distance — au
lieu d'un `return None` qui retirait **aussi** l'ajout aval. Le rayon ne sert plus qu'au gate
`GATE_NOT_DERIVABLE`, qui a besoin de savoir si la borne est finie.

## 5. Second bug — la 2ᵉ clause de `CasterHasNotMoved` n'est PAS inerte chez l'autre consommateur

Le port documentait : « la 2e clause (`GetTiles(caster).IsEquivalentTo(casterTiles)`) est INERTE
dans le régime du consommateur ». Vrai pour **`BattleQuery$$IsTileInRangeOfAnyAbility`**, qui passe
le singleton `{GetMainTile(caster)}`. **Faux** pour l'autre — `AttackQuery$$GetAllTilesInAbilityRange(unit,
possiblePositions, true)`, l'oracle `aiMovableTiles` — qui **itère les positions candidates** et
passe chacune en `casterTiles` : le natif refuse alors **toute** position différente de la tuile
courante, et ne verse **rien**.

L'attribution n'est pas déduite, elle est **mesurée** par une paire du **même preset** dont les
masques ne diffèrent **que** par ce bit :

| ability | `rules` | `abilityReason.casterReason` (tuile COURANTE) | natif verse la source | port AVANT |
|---|---|---|---|---|
| `1215` | `0x8004` | `0` | `[(1,1)]` | `[]` (bug §4) |
| `1216` | `0x8014` | `0` | **`[]`** | `[(1,1)]` — PERMISSIF |

⚠ `abilityReason` rend `0` **des deux côtés** : il évalue depuis la tuile COURANTE. Ce canal ne
peut donc pas voir cette clause — seule la zone la révèle.

**Généralisation, sans greffe** : `spaceBlackmane` / `1106` (`0x8014`, portée **lue**, kit
d'origine, HERO au pool) sur le même cul-de-sac — natif `[]`, port `[]` après correctif, et
**`[(1,1)]`** si l'on retire la clause. Deux chemins sans rien de commun, même verdict.

Porté par un champ `interrogated_pos` de `CasterSubstrate` (la position **interrogée**, distincte
de `pos` = la tuile courante) et par un paramètre `is_turn_of_unit` de
`is_tile_in_range_of_any_ability` — tous deux en **tri-état** : un fait non mesuré ne refuse
jamais, donc les appelants de production (qui ne publient ni l'un ni l'autre) sont **inchangés**.

## 6. L'instrument du parent le confirme — et ne confirme pas tout

`probe_447_r1_caster_is_possible_target.py --step lecteurs` classe chaque fonction lectrice du
bit 15 en trois états. Après cette tranche :

| fonction lectrice | avant | après |
|---|---|---|
| `_zone_contains_distance` (`ability_range`) | (2) garde OFFLINE seule | **(1) PORTÉ ET CONFRONTÉ** |

Le basculement n'est pas gratuit : ce balayage lit l'**AST** des tests, pas leurs docstrings, donc
il fallait interroger le foyer **par son nom, dans du code exécutable** — c'est ce que fait
`test_le_LECTEUR_du_bit_15_repond_comme_le_natif`, avec une assertion qui vaut par elle-même (zone
`True` ⟺ bit armé, et « le natif ne verse la source que si la zone répond `True` »).

⚠ **Le même balayage ne corrobore PAS une ligne de la table de `case-447-r1` §2** : il rend
`caster_is_possible_target` = **(2) PORTÉ, JAMAIS ÉPROUVÉ**, là où la fiche écrit
« (1) PORTÉ ET CONFRONTÉ ». Cause mesurée : `test_447_r1_caster_is_possible_target_live.py` ne
nomme `caster_is_valid_target` que **dans sa prose**. Rien à corriger dans le port — c'est la
garde qui ne se voit pas. Hors périmètre de cette tranche, signalé.

## 7. Validation

* **LIVE** — `tests/engine/test_447_r1_r1_zone_inclusion_decision_live.py` : **20 passed**,
  3 runners (~23 s). Le fichier garde le **RÉGIME** avant le discriminant, et refuse bruyamment
  (`pytest.fail`) un montage qui ne monte pas — jamais un skip.
* **NON-RÉGRESSION** — **208 passed** offline (`source_tile_zone`, `ability_range`,
  `whole_board_gates`, `dynamic_target_gate`, `line_of_sight`, `friend_gates`, `walkability`,
  `adjacency_foyer`, `tiles_in_range_order`, `caster_gates`, `caster_reason`,
  `targeting_options_sources`) et **87 passed** live en 3 vagues de 4
  (`caster_reason_live`, `caster_gates_live`, `ability_range_live`, `pool_masks_live`,
  `447_r1_caster_is_possible_target_live`, `walkability_live`, `line_of_sight_live`,
  `only_adjacent_live`, `friend_gates_live`, `whole_board_gates_live`, `adjacency_foyer_live`).
* **GARDES DU DÉPÔT** — `probe_273 --only-scan`, `probe_365`, `probe_468` : PASS.
* **NON COUVERT**, nommé : cf. §8.

## 8. Résidus nommés

* ~~**`#447-r1-r1-r1`**~~ — **PORTÉ (2026-08-15), et l'arbitrage « non porté plutôt que porté sans
  pouvoir l'exercer » est REVENU sur : on PEUT l'exercer.** Le natif filtre la walkability **dans**
  `GetTilesInRange` (dernière instruction du corps, lambda
  `TargetingQuery.u003Cu003Ec$$u003CGetTilesInRangeu003Eb__36_0`), donc **avant** les deux
  `AddRange(casterTiles)`, qui vivent chez son appelant `GetPossibleTargetsForOptions` — alors que
  les trois `RemoveAll` (`b__0`, `b__1`, `b__2`), eux, sont bien **après** et s'y appliquent. Le
  port soumettait l'ajout aval au filtre : écart RESTRICTIF, corrigé par
  `ability_range.verse_par_ajout_aval`, **foyer unique** partagé avec `_zone_contains_distance`
  (deux écritures du même fait natif se désynchroniseraient).
  **EXERCÉ par un cran synthétique**, deux bras : (A) le brouillard posé sur la tuile SOURCE ne
  change plus rien pour les **31** porteurs de l'ajout aval — le critère est l'INVARIANCE, pas
  « la tuile est gardée », plusieurs d'entre eux étant déjà retirés par le court-circuit
  `TargetIsFriendly && !TargetIsEnemy` en amont ; (B) le brouillard retire **encore** une tuile
  entrée par `GetTilesInRange` — sans ce bras, un correctif qui aurait simplement supprimé l'appel
  à `_unwalkable` passerait pour juste. **CONTRE-ÉPREUVE JOUÉE** (ancre comptée avant substitution,
  port restauré à l'identique) : l'ancien ordre remis, le bras A rougit sur **22 lignes sur 31**,
  le bras B reste vert.
  **NON CONFRONTÉ live, et c'est une MESURE** : l'écart exige un caster sur une tuile non marchable
  ou en brouillard. Sondage `boardGraph` sur deux boards contrastés — `MC1_67` (pvp, **0** tuile en
  fog sur 63) et `C6_02` (campagne à salles, **32** en fog et 22 non marchables sur 63) —
  intersection « occupée ET (fog ou non marchable) » = **0**. Cause structurelle, LUE :
  `AddUnitOperation$$AreTilesDisallowedAndLog` refuse au spawn toute tuile qui ne passe pas son gate
  `<IBattleQuery slot 0xa1>` ou dont le `TileContentComponent$$IsFilled` est vrai,
  `GetMovableTilesFor` n'en rend pas en brouillard, et le brouillard RECULE (il se lève à
  l'exploration) au lieu d'avancer.
  ⚠ Ce que le canal ne montre PAS, et le probe l'IMPRIME plutôt que de rendre un zéro muet : sur un
  board à salles, les unités d'une salle fermée ne sont pas ENCORE instanciées (`C6_02` :
  `observeBattle.counts.units` = **3** pour six unités demandées au build). Le zéro ne se lit donc
  pas seul — c'est l'argument structurel qui le porte.
  L'attaque normale n'est pas concernée : aucun de ses 18 profils ne porte `CasterIsPossibleTarget`
  ni `TargetIsCasterOrEnemy` (cran dédié).
* **`#447-r1-r1-r2` — le bit 57 `TargetIsCasterOrEnemy` reste un mirror non confronté sur cette
  face.** **2** masques le portent (`1008`, `1102`, tous deux `0x200000000000004`) ; leurs porteurs
  (`necroPlasmancer`, `thousAhriman`) arment aussi `CasterMatchesDynamicRule` en régime
  `not_derivable`, donc une confrontation doit d'abord **établir** `casterReason == 0` avant de lire
  la zone — sans quoi elle mesurerait le gate, pas le bit.
* ~~**`#447-r1-r1-r3`**~~ — **TRANSPORT LIVRÉ, GISEMENT MESURÉ VIDE (2026-08-07).** Le canal est
  câblé de bout en bout : `NCContext.current_player` (`TurnComponent._currentPlayerId`, rempli par
  `ai/action_generators.py` depuis `ctx.cur`) + `noncomparable/_base.py::is_turn_of_unit_by_pos`
  (mirror de `IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit` :
  `observeBattle.units[].playerId == currentPlayer`, **jamais `teamId`** — les deux divergent sous
  contrôle mental) → `early_warning_override.py` → `is_tile_in_range_of_any_ability`.
  **Son effet observable est NUL, et c'est le résultat**, pas un aveu : sur l'unique appelant de
  production, le port mirrore `BattleQuery$$IsTileInRangeOfAnyAbility`, dont `casterTiles` est le
  **singleton** `{GetMainTile(unit)}` — la 2ᵉ clause y est donc inerte **CHEZ LE NATIF AUSSI**
  (`interrogated_pos == pos` par construction), et `has_moved` reste non publié côté DÉCISION.
  S'y ajoute que le « caster » interrogé y est un **ENNEMI** du joueur courant, donc
  `IsTurnOfUnit` y vaut `False`, ce qui est déjà le comportement d'un `None`. Le transport ferme le
  canal et devient le **prérequis** de tout câblage de `has_moved` ; il ne ferme aucun écart.
  Résidu neuf : `#447-r1-r1-r3-r1` (le canal `has_moved`, `combatSnapshot.units[].unitFlags`).

## 9. Re-dériver

```
python scripts/python/probe_447_r1_r1_zone_inclusion_decision.py --step offline
python scripts/python/probe_447_r1_r1_zone_inclusion_decision.py --step live
python scripts/python/probe_447_r1_r1_zone_inclusion_decision.py --step portee_non_lue [--ability 1216]
python scripts/python/probe_447_r1_r1_zone_inclusion_decision.py --step has_not_moved
python -m pytest tests/engine/test_447_r1_r1_zone_inclusion_decision_live.py -q
```
