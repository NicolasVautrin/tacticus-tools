# Case #129 — la face DECISION de `ThriceBlessedConflagration` (1187) : elle existe nativement, elle n'avait AUCUN port

**Statut** : 1/1 item PORTE + CONFRONTE LIVE (conformite ET discriminance, sur DEUX couples
board/seed) + mutation-test. Correctif 100 % Python (`scripts/python/**`) — aucun changement
`frida/hooks`, aucun rebuild, aucun reinject. Build `gqfc5mff6c`. Residu nomme au §9.6 de
`case-124-elevation-gate-decision.md` (« candidat de suite », hors perimetre #126).

| item | ability | feuille DECISION | verdict |
|---|---|---|---|
| (a) | `ThriceBlessedConflagration` 1187 (`adeptExorcist`, **MACHINE OF WAR** Adepta Sororitas) | `engine/playbook/noncomparable/thrice_blessed_conflagration.py` | **QUIRK PORTE + VALIDE LIVE** (conforme + discriminant + mutation-test) |

Code : `engine/battle_query.py` (`get_surrounding_tiles` — mirror NEUF ; `is_tile_valid_for_list`
gagne le 4e argument natif `checkElevation`) · `engine/playbook/noncomparable/thrice_blessed_conflagration.py` ·
registre `engine/playbook/noncomparable/__init__.py`.
Test : `tests/engine/test_thrice_blessed_decision_live.py` · Probe :
`scripts/python/probe_129_thrice_blessed_decision.py`.

---

## 1. La question, et la reponse

> Sur un etat ou l'IA native CASTE 1187, le moteur offline caste-t-il la MEME ability, sur la MEME
> cible ?

**Avant #129 : NON, par CONSTRUCTION.** `IdunBattle.AI.Playbook.Loki.ThriceBlessedConflagrationPlaybook$$EvaluateNonComparable`
existe cote natif ; `engine/playbook/noncomparable/` ne connaissait PAS l'id 1187. L'ability
n'etait donc jamais proposee : ce n'etait pas une utilite fausse, c'etait une feuille **ABSENTE**.
Sa face COMBAT, elle, etait deja portee et fidele
(`engine/runner/abilities/sisterhood.py::thrice_blessed_get_tiles_in_best_line`) — asymetrie
classique « decider != executer ».

**Apres #129 : OUI** — natif et port rendent `1187` sur la MEME cible, sur deux couples
board/seed, et la mutation « geometrie DarkTalonStrike » diverge (chiffres au §4).

## 2. L'arbre natif, lu au decompile

### 2.1 Le playbook

`IdunBattle.AI.Playbook.Loki.ThriceBlessedConflagrationPlaybook$$.ctor` =
`NonComparablePlaybook<T>(0x4a3)` -> **ability_id = 1187**.
`...Playbook$$.cctor` = `**(DAT+0xb8) = FixMath.NET.Fix64$$FromInt(1)` -> **MIN_UTILITY = 1**
(DarkTalonStrike : 2 — c'est la premiere des differences qui comptent).

`...Playbook$$EvaluateNonComparable(this, unit, position)` :

    bucket = Bucket.ctor(bucket, 0, Nullable(Fix64(1)))          # le min du cctor
    foreach T in BasePlaybook$$GetEligibleTargetsSelectable(this, unit, position, 0):
        ability       = this+0x68
        bestLine      = ThriceBlessedConflagrationAbility$$GetTilesInBestLine(ability)
        attackTargets = ThriceBlessedConflagrationAbility$$GetAttackTargets(ability, bestLine)
        util          = Fix64.FromInt( <slot 2 de l'iface>(attackTargets, ctx(T)) )
        action        = BasePlaybook$$GenerateAction(this, position, T, util)
        Bucket$$AddAction(bucket, action)                        # argmax STRICT, keep-first au tie

Structure IDENTIQUE a `DarkTalonStrikePlaybook$$EvaluateNonComparable` — l'utilite est un ENTIER
(`Fix64.FromInt` d'un `.Count`), jamais une prediction de degat.

### 2.2 L'arbre de ciblage — TROIS differences avec DarkTalonStrike, toutes lues, deux portantes

`IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInBestLine`
(slots `InitializeShared` : `0x148 Owner · 0x160 Caster · 0x168 CasterTile · 0x178 Target ·
0x180 ActiveTarget`) :

    ring  = SurroundingTiles(Target@0x178, includeCenter=0, radius=1, 0, 0)
    count = Count( GetTilesInLine(ActiveTarget@0x180) )
    best  = First( SortByFormula(ring, count, 0 = DESC), 1 )
    return  Target@0x178  op_Addition  GetTilesInLine(best)

`...Ability$$GetAttackTargets(bestLine)` = `Enemies(Owner@0x148, bestLine, 3)`.

`...Ability$$GetTilesInLine(from)` :

    settings = new TilesBehindInLineSettings ; *(byte*)(settings+0x10) = 0   # +0x11 laisse au ctor
    pred     = HasUnit(ActiveTarget@0x180, 3) & AreEnemies(Owner@0x148, Units(ActiveTarget@0x180))
    start    = First( SortByDistance( Tiles(Target@0x178), from ), 1 )
    return     FilterContinuous( TilesBehindInLine(start, from, settings, null), pred )

| | `DarkTalonStrike` 1092 | `ThriceBlessedConflagration` 1187 | portant ? |
|---|---|---|---|
| MIN_UTILITY (cctor) | `Fix64(2)` | **`Fix64(1)`** | oui (1 ennemi suffit) |
| `ring` | `AdjacentTiles(Target)` | **`SurroundingTiles(Target, 0, 1, 0, 0)`** | **oui** (§2.3) |
| tris | `SortByFormula(angle, ASC)` **puis** `(count, DESC)` | **UN SEUL** `SortByFormula(count, DESC)` | tie-break seulement |
| settings de ligne | `*(u16*)(s+0x10) = 0x101` -> 1/1 | **`*(u8*)(s+0x10) = 0`** -> 0/0 | **oui** (§2.3) |
| `from` de `TilesBehindInLine` | `Target@0x178` direct | `First(SortByDistance(Tiles(Target)), 1)` | non (identite mono-tuile) |
| cle du compte | `Count(Units(GetTilesInLine(...)))` | `Count(GetTilesInLine(...))` | non (la ligne est deja `HasUnit`-filtree) |
| cible | une TUILE (l'aim du beam) | une **UNITE ALLIEE** (porteuse du buff 1401/1436) | oui (nature de la cible emise) |

Un copier-coller de la feuille 1092 serait donc FAUX sur trois axes — et **mesurablement** faux
(§4.2 : il ne caste pas la ou le natif caste).

### 2.3 Pourquoi `SurroundingTiles` != `AdjacentTiles` (la lecture qui ne se devine pas)

`IdunBattleLogic.Entities.DSLFactory$$SurroundingTiles(dsl, entity, includeCenter, radius, p5, p6)` :
`includeCenter == 0` -> branche `SurroundingTiles(entity, 1, radius, p5, p6) - Tiles(entity)`
(anneau plein rayon `radius`, centre retire au niveau DSL). Sinon
`IdunBattle.Entities.Selectors.SurroundingTilesSelector$$.ctor(this, …, service, entitySel,
radius -> +0x38, p5 -> +0x28, p6 -> +0x29)`.

`IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select` appelle le slot `0x65` du service
avec `(tileEntity, radius, requireEmptyOrSteppable=0, checkWalkable=(this+0x29 == 0),
unitFilter=this+0x28, includeSelf=1)` -> `IdunBattle.Core.Services.BattleQuery$$GetSurroundingTiles`
-> `...BattleQuery$$IterateSurroundingTiles` -> `IdunBattle.Core.Services.TileQuery$$IterateSurroundingTiles`
-> `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` :

    cube = CubeCoordinate(srcTile)
    for x in cube.x-R..cube.x+R: for y in cube.y-R..cube.y+R: for z in cube.z-R..cube.z+R:
        if (x + y + z != 0)                                            continue
        tile = GetTileEntityAt(CubeCoordinate(x,y,z).ToAxialCoordinate())
        if (tile == null)                                              continue
        if (requireEmptyOrSteppable && !IsEmptyOrSteppable(tile))      continue
        if (!includeSelf && tile == srcTile)                           continue
        if (TileUtil.IsTileValidForList(tile, srcTile, checkWalkable, 0))   yield tile

Le 4e argument d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList` est le **litteral `0`** :
`checkElevation` est DESACTIVE. Or ce meme `IsTileValidForList` est celui de la ligne hex, ou
`IdunBattle.Core.Services.BattleQuery$$GetTilesBehind` passe le litteral **`1`**. Le port l'avait
cable en dur a `True` (« unique call-site porte », #124) — #129 le rend PARAMETRE, comme le natif.

Consequence directe : **le ring de 1187 ignore le relief**. La `|Delta elev| < 2` INCONDITIONNELLE
de `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` (le ring-1 de
`AdjacentTiles`, donc de DarkTalonStrike) N'EXISTE PAS ici. Et comme les settings de ligne sont
`0/0`, la ligne elle-meme n'est ni gatee walkable ni gatee elevation : c'est le `FilterContinuous`
(prefixe contigu d'ennemis) qui la borne, rien d'autre.

Les flags p5/p6 du call-site 1187 (`0, 0`) sont les MEMES que ceux du seul autre consommateur
porte (`GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector`, r=2, valide live case-49x) —
le mapping `checkWalkable = (p6 == 0) = True` est donc confirme par deux chemins.

**ORDRE du ring** : la triple boucle cube ASCENDANTE emet en ordre LEXICOGRAPHIQUE
`(cube.x, cube.y)` croissant (pour (x,y) donnes, un seul z satisfait `x+y+z == 0`). C'est deja la
cle `battle_query.iterate_surrounding_tiles_order_key`. Comme 1187 n'a **qu'un** `SortByFormula`
(stable), cet ordre EST le tie-break entre directions d'egal compte.

## 3. Le correctif : un mirror de plus dans le foyer UNIQUE, une feuille de plus dans le registre

Meme regle qu'aux #124/#126 : **1 fonction native = 1 foyer offline**. Les briques manquantes
rejoignent `engine/battle_query.py` (domaine POSITION), et la feuille les CONSOMME :

| ajout / modif | natif |
|---|---|
| `get_surrounding_tiles(pos, radius, include_center, check_walkable, …)` | `BattleQuery$$GetSurroundingTiles` (slot 0x65) -> `TileQuery.<IterateSurroundingTiles>d__6` |
| `is_tile_valid_for_list(..., check_elevation=True)` | le 4e argument LITTERAL de `TileUtil$$IsTileValidForList` — `1` chez `GetTilesBehind`, `0` chez `IterateSurroundingTiles` |

La feuille `thrice_blessed_conflagration.py` reprend le decoupage de `dark_talon_strike.py`
(`_line_enemy_count` / `_best_line_direction` / `_beam_count` / la classe), mais **aucune ligne
n'est recopiee a l'identique** : les settings de ligne sont `0/0`, le ring est
`get_surrounding_tiles`, et il n'y a **qu'un** tri.

Deux points structurels, tous deux DEDUITS de l'arbre natif (pas de l'experience) :

1. **La feuille ne gate PAS sur `ctx.origin`.** `GetTilesInBestLine` de 1187 ne lit NI
   `Caster@0x160` NI `CasterTile@0x168` : tout est ancre a `Target@0x178`. Or son SEUL porteur est
   une MACHINE OF WAR, entite **sans `PositionComponent`** (`observeBattle` : `pos = null` by
   design). Un gate `origin is None` — celui de la feuille 1092, ou l'angle a besoin du caster —
   aurait rendu la feuille MORTE sur son unique porteur.
2. **La cible emise est un id d'UNITE**, pas une entite-tuile : `abilityTargets(mow, 1187)` ne rend
   que des entrees `kind == "unit"` designant MES unites (mesure live), chacune portant sa `pos`
   -> c'est cette position qui ancre le beam.

Degradation SURE : cartes absentes -> `tiles_behind_accessors` rend des accesseurs `None`, le ring
retombe sur les 6 voisins geometriques et la ligne n'est plus bornee que par le `FilterContinuous`
(borne SUPERIEURE : on ne tronque jamais a l'aveugle).

## 4. Confrontation LIVE — conformite ET discriminance

Porteur `adeptExorcist` : **MACHINE OF WAR presente dans `--list-pool`** (8 MoW spawnables) ->
confrontable par la porte MoW du gate de confrontabilite.

**LEVIER MUNITIONS** (sans quoi rien ne caste) : `munitionsCost = 1` (gameconfig 1187) et le seed
BC part a `BC.Player.Players[*].MachineOfWarAmmo = 0`. Le harnais dote les joueurs de 5 munitions
dans un BC derive (`--seed-bc`), meme levier que `test_storm_speeder_live` (#117). `initialCooldownTurns = 1`
-> 2 `endturn` avant mesure.

**ORACLE** : `aiStepDryRun` (`CalculateNextActionForPlayer`, `mutated: false`), JAMAIS `aiPredict`.
Pourquoi pas `aiDryRunAllUnits` (l'oracle des cas #124/#126) : il n'itere que les `EntityType.Unit`
— **la MoW n'y figure pas** (mesure : `units: [56, 58]` pour un caster `55`). `aiStepDryRun` rend
la prochaine action du JOUEUR, toutes unites confondues ; on CLOT donc d'abord l'activation de
chaque allie (`applyAction {kind: finish}` -> `UnitStats_ActionsAvailable: 0`, `mutated: false`)
pour isoler la proposition de la MoW. Mesure de ce besoin : sur `C1_25` sans `finish`, l'oracle
rendait `(58, 1014, 51)` — une action d'UNITE, pas la MoW ; apres `finish` des deux allies :
`(55, 1187, 58)`.

### 4.1 Conformite + ARGMAX SUR LES CIBLES — board `C1_02`, seed 4242 (terrain PLAT)

Allies 56 @(0,0) et 58 @(1,0) ; ennemis 49 @(1,1) et 51 @(1,2). `fromHere` = `[56, 58]` (ordre id
CROISSANT — la cible de l'argmax est donc en QUEUE).

| | ability | cible |
|---|---|---|
| natif | **1187** | **58** |
| moteur (feuille #129) | **1187** | **58** (`pred 2.0`, `scored=[(56, 1), (58, 2)]`) |

Mecanique : depuis (1,0), la direction `(1,1)` aligne `[(1,1), (1,2)]` = **2** ennemis contigus ;
depuis (0,0), la meme paire n'est plus alignee — la ligne vers (1,1) continue en (2,1), VIDE ->
**1**. Un port keep-first (ou un port qui ne compterait qu'un ennemi) rendrait **56** : la cible
native prouve donc l'argmax, pas seulement la presence de la feuille.

Etat de controle (meme runner, avant deplacement de 51) : ennemis @(1,1),(2,1) -> `scored=[(56, 2),
(58, 1)]`, natif **1187 -> 56**, moteur **1187 -> 56**. La cible SUIT la geometrie dans les deux
sens.

### 4.2 Discriminance des QUIRKS — la MARCHE d'elevation, sur DEUX boards

Le scenario qui separe `SurroundingTiles` d'`AdjacentTiles` : une marche `|Delta elev| >= 2` entre
la tuile de la CIBLE et le 1er ennemi, la ligne restant ensuite sur un palier unique. Derive du
pool (scan des 779 dumps via `board.py` + `rl_duel._board_mow_ok`) : **168 boards MoW-capables**
portent une telle configuration.

MUTATION testee = la feuille remise a la geometrie de DarkTalonStrike : ring `AdjacentTiles`
(porte `|Delta elev| < 2`) + settings de ligne `1/1`. C'est EXACTEMENT ce qu'un copier-coller de
1092 produirait.

| board / seed | geometrie | natif | moteur #129 | moteur MUTE (DarkTalon-like) |
|---|---|---|---|---|
| `C1_38` / 4242 | cible 90 @(1,0) elev **2** ; ennemis (1,1),(1,2) elev **4**,**4** | **1187 -> 90** | **1187 -> 90** (`pred 2.0`) | **`[]`** (aucun cast) |
| `C1_25` / 777 | cible 58 @(0,2) elev **4** ; ennemis (0,3),(0,4) elev **2**,**2** | **1187 -> 58** | **1187 -> 58** (`pred 2.0`) | **`[]`** (aucun cast) |

Les deux sens de la marche sont couverts (montante et descendante), et dans les deux cas la cible
native est en QUEUE de `fromHere` — l'argmax est donc exerce AUSSI par ces deux mesures.

Le port mute rend `[]` parce que la marche exclut l'unique direction riche du ring
(`AdjacentTiles`) : le compte tombe a 0 pour toutes les cibles -> `0 < MIN_UTILITY(1)` -> aucun
candidat NonComparable -> le moteur ne caste pas 1187, la ou le natif le caste. **Le test est donc
incapable de passer sur un copier-coller de la feuille 1092.**

## 5. Ce qui n'est PAS couvert

- ~~**Le DRIVER de decision offline n'active pas les MACHINES OF WAR**~~ — **FERME par R14**
  (`case-r14-mow-decision.md`, 2026-07-27). `engine_decide` route desormais un `casterId` de MoW vers
  le tactic natif DEDIE `IdunBattle.AI.Tactics.DefaultMachineTactic` (mirror de
  `IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit`, branche `IsMachine`) : generateurs
  d'ability SANS `MovementActionGenerator`, caster a `UnitPosition$$NullPosition`, tuiles candidates
  VIDES. Le chemin `engine_decide -> NonComparableGenerator -> feuille 1187` est ATTEINT et confronte
  (`test_thrice_blessed_decision_live.py` passe par `engine_decide`, plus par un `NCContext` bati a
  la main). L'exclusion des MoW de `_dv_units`/`_obs_units` est CONSERVEE : elle etait fidele (canal
  `.mows` separe cote natif), pas le blocage.
- **AIM depuis l'ORIGINE uniquement** (`fromHere`) : le natif balaie aussi les positions de MOVE.
  Inerte ici — la MoW ne se deplace pas, et l'utilite de 1187 est position-INDEPENDANTE (ancree a
  la tuile de la CIBLE). Le seul effet possible serait un set de cibles plus large apres
  deplacement, ce qui ne s'applique pas a un caster immobile.
- **Ordre du ring en tie-break de DERNIER recours** : le port suit l'ordre cube-lexicographique
  mirrore ; a comptes EGAUX entre deux directions, l'utilite est la MEME, donc la DECISION est la
  meme — l'ordre n'est observable que cote COMBAT (quelle ligne est reellement frappee), ou la face
  DSL a son propre foyer. Non exerce en live.
- **Cible multi-tuiles** : `start = First(SortByDistance(Tiles(Target), from), 1)` et le
  `- Tiles(entity)` du ring degenerent en la tuile unique pour toutes les cibles confrontees. Le
  port retire la SEULE tuile `pos` (au lieu de toutes les tuiles de l'entite) — RESIDU documente,
  non exerce.
- **`tileComponent+0x40` vs `IsWalkable`** : residu herite de #117/#124 — les substrats offline
  fondent `+0x41` (mur) et `IsWalkable`. Consequence PROPRE a 1187 : avec `checkWalkable = 0` sur
  la ligne, le natif testerait `tileComponent+0x40 == 0` la ou le port applique son proxy
  walkable. INERTE ici : la ligne s'arrete de toute facon au 1er non-ennemi (`FilterContinuous`) et
  une tuile portant un ennemi est walkable.
- **`GetUseProbability` / slot 4 `ShouldEvaluate`** : la vtable du playbook 1187 n'a pas ete
  resolue ; la feuille garde le `should_evaluate` de base (True constant), comme les 30 autres
  portees. Non exerce (le natif a caste a chaque mesure).

## 6. Non-regression (tests CIBLES rejoues)

| test | ce qu'il couvre |
|---|---|
| `tests/engine/runner/test_mow_groups_bcd_live.py` | face COMBAT 1187 (l'autre consommateur de la geometrie de ligne) + les 4 autres MoW B/C/D |
| `tests/engine/test_dark_talon_beam_direction_decision_live.py` | argmax de direction 1092 (consommateur de `get_adjacent_tiles`) |
| `tests/engine/test_line_elevation_gate_decision_live.py` | gate d'elevation 1092/1197 (consommateur de `is_tile_valid_for_list`, dont la signature bouge) |
| `tests/engine/test_playbook_live.py` | agrement DECISION global (le registre NC gagne une entree) |
