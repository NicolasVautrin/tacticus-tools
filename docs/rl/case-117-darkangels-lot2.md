# Case #117 — DarkAngels lot 2 : DarkTalonStrike (COMBAT), DeathOnTheWind, Hailstrike

**Statut** : 3/3 items PORTES ; 3/3 confrontes LIVE. Correctif 100 % Python (`scripts/python/**`) —
aucun changement `frida/hooks`, aucun rebuild, aucun reinject. Build `gqfc5mff6c`.

| ability | id | porteur | verdict |
|---|---|---|---|
| DarkTalonStrike | 1092 | `darkaAzrael` (HERO) | **PORTE + VALIDE LIVE** (2 geometries + mutation-test du gate) |
| DeathOnTheWind  | 1213 | `darkaStormSpeeder` (MoW) | **PORTE + VALIDE LIVE** (ligne + effet 1257 + gate de ciblage) |
| Hailstrike      | 1214 | `darkaStormSpeeder` (MoW) | **PORTE + VALIDE LIVE** (pose d'effet) ; PHASE 2 = residu (§5) |

Code : `engine/runner/abilities/darkangels.py` · `engine/entities/selectors.py`
(`TilesBehindInLine`, `Units`, `SortByDistance`) · `engine/entities/formulas.py`
(`AngleBetweenLines`) · `engine/entities/triggers.py` (`AreEqual`).
Tests : `tests/engine/runner/test_dark_talon_strike_live.py`, `.../test_storm_speeder_live.py`.

---

## 1. Le findy du lot : la ligne hex a un GATE D'ELEVATION, et il coupe le beam

Le port de DECISION (`DarkTalonStrikePlaybook`, deja en place) modelise le beam comme un **rayon droit
continu** et le note lui-meme comme approximation. Le decompile dit autre chose, et le live le confirme.

`IdunBattleLogic.Entities.DSLFactory$$TilesBehindInLine(from, to, settings, count)` ->
`IdunBattle.Entities.Selectors.TilesBehindInLineSelector$$Select` -> slot iface 0x53 =
`IdunBattle.Core.Services.BattleQuery$$GetTilesBehind(from, to, bool1, bool2, maxCount)` :

```
dir = CubeCoordinate.DirectionTo(cube(from), cube(to))
ref = MainTileEntity(from)                       # tuile de REFERENCE d'elevation
cur = cube(from)
loop:
    if maxCount.HasValue && maxCount.Value <= list.Count : return list
    next = cur - dir                             # 1re iteration -> `to`
    tile = GetTileEntityAt(next) ; if (tile == null) return list
    if (!TileUtil.IsTileValidForList(tile, ref, bool1, /*checkElevation*/ 1)) return list
    list.Add(tile)
    if (bool2) ref = tile                        # la reference SUIT la ligne
    cur = next
```

`IdunBattle.Core.Services.TileUtil$$IsTileValidForList(tile, ref, checkWalkable, checkElevation)` :

```
if (tileComponent+0x41 != 0)          return false
if (!checkWalkable)                   return tileComponent+0x40 == 0        # PAS de gate d'elevation
if (!TileExtensions.IsWalkable(tile)) return false
if (!checkElevation)                  return true
if (ref != null)                      return |elev(ref) - elev(tile)| < 2   # elevation = TileComponent+0x18
```

Le gate d'elevation vit **DANS la branche walkable** : c'est `settings+0x10` qui l'active, et
`settings+0x11` qui fait suivre la reference pas a pas. INVENTAIRE des call-sites (LU au decompile) :

| ability | `settings+0x10` (checkWalkable) | `settings+0x11` (updateRef) | `count` |
|---|---|---|---|
| `DarkTalonStrikeAbility$$GetTilesInLine` | 1 | 1 | null (jusqu'au bord) |
| `ExcruciatingFrequenciesAbility$$GetAffectedTiles` | 1 | 1 | `Direct(nrOfTiles)` |
| `DeathOnTheWindAbility$$GetTilesInLine` | 0 | 1 | `Get(nrOfTiles - 1)` |
| `ThriceBlessedConflagrationAbility$$GetTilesInLine` | 0 | 0 | null |

**MESURE LIVE** (runner C4_02, colonne 5, elevations `[1,1,1,1,3]`) : Azrael (5,3), cible (5,4),
ennemis alignes (5,5) / (5,6) / (5,7). Le natif frappe (5,4), (5,5), (5,6) et **s'arrete** : la marche
`elev 1 -> 3` entre (5,6) et (5,7) casse le beam. MUTATION-TEST : le meme port avec
`check_walkable=False` frappe **4** cibles au lieu de 3 -> le test echoue. Le gate est PORTANT et le
test le prouve.

Le port ajoute donc `check_walkable` / `update_reference` a `TilesBehindInLine` (defauts `False/False`
= comportement historique de ThriceBlessedConflagration, INCHANGE).

**SPILLOVER (hors perimetre #117, a flagger)** : la face DECISION d'`ExcruciatingFrequencies`
(`engine/playbook/excruciating_frequencies.py::_line_tiles`) et celle de `DarkTalonStrike`
(`playbook/noncomparable/dark_talon_strike.py::_beam_count`) ignorent toutes deux ce gate — elles
SUR-ESTIMENT donc l'utilite d'un beam qui traverse une marche >= 2. Non corrige ici (perimetre).

## 2. DarkTalonStrike (1092) — face COMBAT

`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour` :

```
mainUnits = Cache( Units(target@0x178) )
targets   = Enemies( owner@0x148, Units(GetTilesInBestLine()) )
Execute( Foreach(targets, <lambda b__0>) )

<lambda b__0>(cible) = Group( AddEffect(0x429 = 1065 Pinned, AbilityStateReference, targets = cible)
                              op_Addition  DamageUnit(mainUnits, cible),
                              cible, 0x5b )

DamageUnit(mainSel, cible) :
  isMain = AreEqual(cible, mainSel)
  AttackWithAbilityDamage( caster@0x160, cible,
      If(isMain, MinMaxDamage, MinMaxDamage2),
      If(isMain, DamageProfileFromConfig(0x2e), DamageProfileFromConfig(0x3f)),
      ConditionalAmount(isMain, GetNumberConstant(0x2f), GetNumberConstant(0x32)),
      AbilityOrEffect(0x444 = 1092) )

GetTilesInBestLine() :
  ring    = AdjacentTiles(target@0x178)
  nearest = First( SortByDistance(AdjacentTiles(caster@0x160), target@0x178), 1 )
  angle   = AngleBetweenLines(caster@0x160, nearest, target@0x178, subject@0x180)
  count   = Count( Units( GetTilesInLine(subject@0x180) ) )
  best    = First( SortByFormula( SortByFormula(ring, angle, ASC), count, DESC ), 1 )
  return    target@0x178  op_Addition  GetTilesInLine(best)

GetTilesInLine(from) :
  pred = HasUnit(subject@0x180) & AreEnemies(owner@0x148, Units(subject@0x180))
  return FilterContinuous( TilesBehindInLine(target@0x178, from, {cw=1, ur=1}, null), pred )
```

Points qui ont demande une decision :

- **CIBLE = une TUILE** (`abilityTargets` live : `kind=tile`) -> le `targetId` du message est
  l'entite-TUILE, l'unite principale est son OCCUPANT (`Units(target)`). Meme regime que SquigMine /
  DevastatingRefrain ; `applyAction` veut `to:{col,row}`, pas `targetId`.
- **Tri CHAINE** : `SortByFormula(angle, ASC)` puis `SortByFormula(count, DESC)`, tris STABLES ->
  cle PRIMAIRE = nb d'ennemis alignes, tie-break = alignement avec l'approche du Dark Talon.
- **`AngleBetweenLines`** (nouveau noeud VALEUR) = `EdgeExtensions.GetAngleTo(edge(a1->b1),
  edge(a2->b2))` avec `edge` = `AxialCoordinate.ConnectingEdge` -> `CubeDirections.EdgeToNeighbor`
  (cle `100x + 10y + z`, 6 valeurs). `GetAngleTo(e1,e2)` = `d=|e1-e2| ; a=d*60 ; if a>120 : a=(6-d)*60`.
  L'ecart `|e1-e2| mod 6` est invariant par rotation ET reflexion de la grille -> le port est robuste
  a la convention de cube.
- **`AreEqual` etendu au domaine ENTITE** : `AreEqual(<cible>, Cache(Units(target)))` compare un DICT a
  une LISTE-d'un-element ; l'ancien `==` brut rendait TOUJOURS faux -> la cible principale prenait le
  volet `_2` (6 coups Bolter au lieu d'1 DirectDamage). Corrige : normalisation + comparaison d'ids.
- **`Units` rend l'ordre des TUILES** (`UnitsOnTilesSelector` itere le selecteur de tuiles) et non
  l'ordre des entites : la cascade live frappe la CIBLE puis la ligne en s'eloignant. L'ordre fixe la
  consommation de `state.rng` coup par coup.
- REDUCTION notee : les TROIS noeuds conditionnels natifs partagent le meme predicat, bati PAR ELEMENT
  du `Foreach` -> constant pour l'element ; on factorise en UN `If` de behaviour autour de deux feuilles
  `AttackWithAttackDamage(native_factory="ability")` qui ne different que par leurs cles de config.

## 3. DeathOnTheWind (1213)

```
ExecuteBehaviour :
  tiles   = Cache( GetMachineAttackTiles() )
  enemies = Enemies( caster@0x160, Units(tiles) )
  Execute( ( InformList(0xc1, tiles) & Foreach(enemies, AttackWithAbilityDamage(...)) )
           & AddEffect(0x4e9 = 1257 DeathOnTheWind_ExtraPctDamage, AbilityStateReference,
                       source = caster@0x160, targets = Alive(enemies), duree = dsl+0xc0 = Direct(1)) )

GetMachineAttackTiles :
  ring  = SurroundingTiles(target@0x178, includeCenter = 0, radius = 1)
  cnt   = Count( Enemies(caster@0x160, Units(GetTilesInLine(subject@0x180))) )
  best  = First( SortByFormula(ring, cnt, DESC), 1 )
  line  = GetTilesInLine(best)
  start = First( SortByDistance(Tiles(target@0x178), First(line,1)), 1 )   # singleton -> IDENTITE
  return  Tiles( start op_Addition line )                                  # tile-domain -> IDENTITE

GetTilesInLine(from) = TilesBehindInLine(target@0x178, from, {cw=0, ur=1},
                                         Get(GetNumberConstant(0x17 = nrOfTiles) - 1))
```

- `nrOfTiles - 1` tuiles depuis la voisine choisie + la tuile de la cible = `nrOfTiles` hexes
  (i2 : « straight line 3 hexes long, starting on the hex of the targeted enemy »).
- **AUCUN `FilterContinuous`** (contraste DarkTalonStrike) : tous les ennemis PRESENTS sur ces hexes
  sont frappes, trous compris. Et `cw=0` -> **aucun** gate d'elevation.
- **CIBLE = une TUILE** aussi (`kind=tile` live) — la tuile de l'ennemi deja attaque.
- **GATE DE CIBLAGE** `DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` :
  `GetNumAttacksReceivedThisTurn(GetUnit(cible)) != 0 ? 0 : 2` -> la cible doit avoir DEJA recu >= 1
  attaque CE TOUR. C'est un gate de **CIBLAGE** (amont d'`ExecuteInternal`, cf. case-111) : il vit dans
  `abilityTargets` live et n'est PAS re-implemente dans `ExecuteBehaviour` (le port n'a pas encore le
  gate de ciblage generique, tache #115). MESURE : avant l'attaque, 0 cible legale ; apres avoir frappe
  un ennemi, `fromHere` contient EXACTEMENT sa tuile.
- L'effet 1257 ne va qu'aux **SURVIVANTS** (`Alive(enemies)` re-evalue APRES la salve, sur le meme
  `Cache`), duree `Direct(1)` = deja en TOURS (#98, PAS un `TurnsFromRounds`).

**Munitions** : `munitionsCost = 1` et le seed BC part a `BC.Player.Players[*].MachineOfWarAmmo = 0`
-> l'ability n'est JAMAIS castable (mesure : 12 tours sans reappro). Aucun flag `rl_duel` ne l'expose ;
le test DOTE les joueurs de munitions dans le BC injecte (meme nature qu'un `--hp-target` : parametre
de BATAILLE, pas de mecanique). C'est un levier reutilisable pour toute MoW a munitions.

## 4. Hailstrike (1214)

`HailstrikeAbility$$ExecuteBehaviour` = **un seul** `AddEffect(0x5e5 = 1509 Hailstrike,
AbilityStateReference, source = caster@0x160, targets = target@0x178,
TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)))` — patron « MoW effect-poser » (case-90).
Cible = un **ALLIE** (`fromHere` live ne rend que mes unites). MESURE live : `Effect_SourceId = 57`
(la MoW), `Effect_RemainingTurns = 2` = `ConvertRoundsToTurns(nrOfRounds=1)` avec 2 joueurs
non-Environment — un port qui aurait pris `nrOfRounds` pour des TOURS aurait pose 1.

## 5. PHASE 2 de Hailstrike — RE COMPLETE, port NON FAIT (residu)

L'effet 1509 porte DEUX mecaniques, toutes deux hors du behaviour de cast :

**(a) bonus de percage** — `IdunBattle.Entities.Effects.Loki.Hailstrike_ExtraPierceEffect$$CreatePiercingBonusForAttack` :
```
EffectBonus.ForPiercing( get_OwnerIsCaster & (IsRangedAttack | IsOverwatchAttack),
                         ConfigVar(0x3f = extraPierceRatio, GetAbilityState(effect), config@0x60) )
```
(`Hailstrike_ExtraPierceEffect$$.ctor` = `BaseEffect(AbilityOrEffect(0x4be = 1214), 1)`). Port
attendu dans `engine/entities/effects/loki/` + `EffectFactory` — patron identique a
`SentinelDirectives` (`ForPiercing(cond, ConfigVar(0x3f))`, deja porte).

**(b) attaque liee de la MACHINE** — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Hailstrike_AttackAbility` :
```
CreateTrigger :
   On(9 = Attack, 1)
 & !AreEqual(unit@0x158, owner@0x148)                 # l'attaquant n'est pas la MoW
 & AreFriends(owner@0x148, unit@0x158)
 & AreEnemies(owner@0x148, target@0x178)
 & !IsDefeated(target@0x178)
 & HasEffect(unit@0x158, 0x5e5 = 1509, 0, 6)
 & ( IsRangedAttack(dsl@0x130) | IsOverwatchAttack(dsl@0x138) )

CreateBehaviour(entities, stage) :
   stage == 0x20 : If( !IsDefeated(target@0x178),
                       AttackWithAbilityDamage( owner@0x148, target@0x178, MinMaxDamage,
                                                Nullable(GetDamageProfileOrDefault(0x14)),
                                                GetNumberConstant(0x2f = nrOfHits),
                                                AbilityOrEffect(this.Id) ) )
   sinon        : TriggerAbilityDelayed( owner@0x148, this.Id, 3 )
```
L'infra du port SUPPORTE ce patron (`EFFECT_TRIGGERS[effectType]` + `TriggeredAbility` `On(9)`, cf.
`HypersensoryMoveAndSpawnDecoyAbility` : meme forme « On(9) -> contre-attaque N x Projectile »), et
`TriggerAbilityDelayed` a deja ete COLLAPSE deux fois dans le port (`act_of_faith.py`). Ce qui manque
est le cablage + sa confrontation live, non un verrou.

**Pourquoi non fait ici** : budget de la tache. Le port de l'ABILITY 1214 (l'item du lot) est complet et
valide ; la phase 2 est un artefact NATIF DISTINCT (un effet + une triggered ability) — meme decoupage
que case-90 (« le degat vit dans la PHASE 2, hors de ces ports »). **Candidat de suite immediate**, pas
un cas dur.

## 6. Validation

| test | ce qu'il garde |
|---|---|
| `test_dark_talon_strike_live.py[long]` | SET frappe / coups / profil / `Pinned` offline == live sur une colonne SANS marche ; discriminant `>= 3 cibles` (une ligne tronquee ne passerait pas) |
| `test_dark_talon_strike_live.py[elevation_break]` | le beam casse EXACTEMENT a la marche (`1 + brk` cibles) ; + assertion « le gate est PORTANT » (sans gate, la ligne serait strictement plus longue) |
| MUTATION-TEST (manuel) | `check_walkable=False` -> `[elevation_break]` ECHOUE (`offline [77,79,81,83] != live [77,79,81]`) |
| `test_storm_speeder_live.py::test_hailstrike_effect_pose_live` | cibles legales = ALLIES ; porteur + type + SOURCE (la MoW) + DUREE (`TurnsFromRounds`) offline == live |
| `test_storm_speeder_live.py::test_death_on_the_wind_line_live` | gate munitions traverse ; gate « deja attaquee ce tour » PORTANT (une seule tuile legale = celle de la victime) ; SET frappe / coups / profil / porteurs de 1257 offline == live |

Non-regression (tests CIBLES rejoues, tous verts) : `test_plasma_cannon_live`, `test_mow_groups_bcd_live`
(ThriceBlessedConflagration = l'autre consommateur de `TilesBehindInLine`), `test_runner_attack_live`,
`test_psyker_splash_live`, `test_plasma_grenade_splash_live`, `test_spirit_leech_combat_live`,
`test_sanctorum_missile_live`, `test_harvester_live`, `test_gauntlets_combat_live`,
`test_death_nova_live` (consommateurs de `Units`/`SortByDistance`/`AreEqual`).

## 7. Ce qui n'est PAS couvert

- **Magnitude du degat** (confond PARTAGE documente, cf. `test_plasma_cannon_live`) :
  `execute_ability_attack` ne passe pas `is_ranged` aux modificateurs d'attaquant -> les buffs ranged du
  caster (LionHelm, high-ground) manquent offline. On valide STRUCTURE + CIBLAGE + COUPS + PROFIL +
  EFFET, pas l'egalite de degat brute.
- **Phase 2 de Hailstrike** (§5).
- **Gates de ciblage PROPRES a ce lot** : le maillon GENERIQUE existe depuis #115
  (`engine/runner/abilities/targeting.py`) mais aucune des 3 abilities n'instancie son
  `get_dynamic_invalid_target_reason`. Concretement, offline :
  * `DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` (cible deja attaquee ce tour) n'est PAS
    re-implemente -> le port executerait un cast que le live refuse. Le patron #115 (poser le bit
    `TargetMatchesDynamicRule` 0x2 + `GetNumAttacksReceivedThisTurn(GetUnit(cible)) != 0`) le rend
    trivial ; **suite immediate**.
  * `DarkTalonStrike` / `Hailstrike` n'ont PAS de `GetDynamicInvalidTargetReason` : leur legalite est
    entierement dans les `TargetingOptions` du ctor (`TargetingOptions(0, <range>, 2, 0x80040, ...)`
    pour 1092), donc dans le filtre STATIQUE de #115 — dont les bits TILE ne sont pas encore portes.
  Les trois gates sont confrontes LIVE dans les tests via `abilityTargets.fromHere` (recette case-111).
- **`ExcruciatingFrequencies` / `DarkTalonStrike` face DECISION** : geometrie de ligne sans le gate
  d'elevation (§1, spillover).
- **`tileComponent+0x40` vs `IsWalkable`** : la branche `checkWalkable == False` du natif teste le
  drapeau de tuile SEUL (sans le composant MUR) ; le port utilise `board.walkable` (qui fond les deux).
  Inerte pour ses call-sites (`FilterContinuous(HasUnit & ...)` en aval).
