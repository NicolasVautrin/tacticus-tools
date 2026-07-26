# Case #117 — DarkAngels lot 2 : DarkTalonStrike (COMBAT), DeathOnTheWind, Hailstrike

**Statut** : 3/3 items PORTES ; 3/3 confrontes LIVE. Correctif 100 % Python (`scripts/python/**`) —
aucun changement `frida/hooks`, aucun rebuild, aucun reinject. Build `gqfc5mff6c`.

| ability | id | porteur | verdict |
|---|---|---|---|
| DarkTalonStrike | 1092 | `darkaAzrael` (HERO) | **PORTE + VALIDE LIVE** (2 geometries + mutation-test du gate) |
| DeathOnTheWind  | 1213 | `darkaStormSpeeder` (MoW) | **PORTE + VALIDE LIVE** (ligne + effet 1257 + gate de ciblage) |
| Hailstrike      | 1214 | `darkaStormSpeeder` (MoW) | **PORTE + VALIDE LIVE** (pose d'effet) ; PHASE 2 portee par #123 (§5bis) |

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
**FERME PAR #124** (`case-124-elevation-gate-decision.md`) : les deux feuilles de DECISION
consomment desormais le MEME mirror que la face COMBAT (`engine.battle_query.get_tiles_behind`,
extrait de `TilesBehindInLine` pour eviter le fork de port), confronte live avec mutation-test.

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

> **FAIT DEPUIS (#123)** : les deux maillons sont portes et confrontes — cf. §5bis. La transcription
> ci-dessus a ete re-verifiee au decompile et est exacte ; elle omettait deux choses tranchantes,
> corrigees en §5bis : `0x20` de `CreateBehaviour` est `EventTriggerType.Custom` (donc la branche
> `== 0x20` est le REVEIL differe, pas le fire initial), et `0x14` de `GetDamageProfileOrDefault` est le
> profil par DEFAUT (`Piercing`), pas le profil retenu (la config 1214 impose `Projectile`).

## 5bis. PHASE 2 de Hailstrike — PORTEE (#123)

**Statut** : 2/2 maillons PORTES. (b) **BIT-EXACT LIVE** ; (a) **canal + magnitude confirmes live par
ENVELOPPE**, bit-exactitude du coup buffe = residu chiffre (§5ter).

Code : `engine/entities/effects/loki/darkangels.py` (nouveau) · `engine/runner/operations/triggers/loki/
hailstrike.py` (nouveau) · `engine/runner/operations/triggers/dispatch.py` (registre
`ACTIVE_ABILITY_TRIGGERS`) · `engine/services/battle_query.py` + `engine/runner/damage_model.py`
(`effect_bonus` du percage) · `engine/runner/operations/damage_ops.py` (cablage voie NORMALE +
`is_overwatch`) · `engine/runner/abilities/base.py` (`ability_pierce_effect_bonus` etendu) ·
`engine/runner/abilities/darkangels.py` (`scale_from_source=True`).
Probe : `scripts/python/probe_123_hailstrike_phase2.py`. Test : `tests/engine/runner/
test_hailstrike_phase2_live.py`.

### (b) `Hailstrike_AttackAbility` (triggered 0x5e3 = 1507) — l'attaque liee de la MACHINE

**Le verrou etait le REGISTRE, pas le behaviour.** Le port n'avait que DEUX chemins d'enregistrement
d'ability-trigger (par TRAIT, par `passiveAbilities`) ; or `darkaStormSpeeder` n'a ni trait ni passif —
uniquement `activeAbilities = [DeathOnTheWind, Hailstrike]`. Le 3e chemin natif, LU au decompile :

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`
= lookup d'un dict statique `ActiveAbilityType -> List<TriggeredAbilityType>` peuple par
`...StaticBattleRules.ActiveAbility$$.cctor`. Entree LUE : **`0x4be (1214) -> [0x5e3 (1507)]`** (39
entrees dans ce dict, meme forme `Add(dict, <activeId>, ToList(<triggeredId>))`). Posseder l'ability
ACTIVE fait donc porter la triggered-ability **des l'init**, sans aucun cast — c'est le gate
`HasEffect(attaquant, 1509)` du trigger qui la rend inerte tant que personne ne porte le buff.
Port : registre `ACTIVE_ABILITY_TRIGGERS` (cle = nom gameconfig de l'active), collecte dans
`collect_triggered_abilities`.

Trigger et behaviour = mirror 1:1 de la transcription §5 (RE re-verifiee au decompile). Deux precisions
LUES qui n'y etaient pas :

- `CreateBehaviour(abilityState, triggerType)` : `triggerType` est un **`EventTriggerType`** (signature du
  dump), et `0x20 = 32 = Custom`. La branche `== Custom` est donc le **REVEIL DIFFERE**, la branche
  `!= Custom` le fire INITIAL qui planifie `TriggerAbilityDelayed(owner, 1507, kind=3)`. Patron
  identique a `MasterOfTheTutelaries_SummonAbility` (#202-C) -> meme COLLAPSE : l'attaque part inline a
  la fin du vecteur `On(9)`.
- profil = `GetDamageProfileOrDefault(0x14)` =
  `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetDamageProfileOrDefault` =
  `config.GetDamageProfile() ?? Piercing(20)`. **PIEGE** : `0x14` est le DEFAUT, pas le profil. La config
  1214 definit `damageProfile = Projectile` -> c'est Projectile qui sort (confirme live : tous les coups
  de la MoW ont `DamageProfileType = 1`).
- degat = `BaseTriggeredAbility$$MinMaxDamage(abilityState)` =
  `RandomAmount(GetVariableForLevel(0xc = minDmg), GetVariableForLevel(0xd = maxDmg))` sur la config 1214
  au niveau de l'ability ACTIVE de la MoW (rarity-scale : `variablesAffectedByRarityBonus` = [minDmg,
  maxDmg]). Coups = `GetNumberConstant(0x2f = nrOfHits)` = 3. Factory native = `AttackWithAbilityDamage`
  -> famille ABILITY (`is_attack_damage_op=False` : 1 tirage/coup, aucun crit, mods attaquant vides,
  arrondi `Round(AwayFromZero)`).

**MESURE LIVE** (probe `--phase ab` / `ab_noarmor`, runner MC1_67, allie `darkaAzrael` buffe tirant au
Plasma a portee 2 sur `astraBullgryn`) — les tags de l'evenement de degat identifient la source sans
ambiguite : `Attacker_Id` = **la MoW** (et non l'allie), `Passive_Ability_Type` = **1507**,
`DamageProfileType` = 1 (Projectile), 3 coups, MEME cible que l'attaque declenchante.

| configuration | coups MoW LIVE | coups MoW OFFLINE |
|---|---|---|
| cible armure 3513 | `[317, 315, 302]` | `[317, 315, 302]` |
| cible armure 0 (`--hp-target`) | `[2116, 2099, 2011]` | `[2116, 2099, 2011]` |

**BIT-EXACT, per-coup, dans les deux configurations** — donc le trigger, son ciblage, son ordre dans le
vecteur `On(9)`, son nombre de coups, son profil, ses bornes de degat, sa consommation RNG et son
arrondi sont tous justes. Le total HP de l'action (coup de l'allie + 3 coups MoW) est egalement
bit-exact a armure 0 : live 9578 == offline 9578.

### (a) `Hailstrike_ExtraPierceEffect` (effet 0x5e5 = 1509) — le bonus de percage

Mirror 1:1 de `CreatePiercingBonusForAttack` (§5) : `ForPiercing(get_OwnerIsCaster & (IsRangedAttack |
IsOverwatchAttack), ConfigVar(0x3f = extraPierceRatio, GetAbilityState(this), this+0x60))`. Trois points
LUS qui ont demande du cablage, au-dela du simple clone de `GravitonRifle_ExtraPierce` :

1. **Porteur != source.** GravitonRifle est un OWNER-effect (porteur == source) ; Hailstrike est pose par
   la MoW **sur un ALLIE**. Or `BaseEffect$$GetAbilityState` rend l'`AbilityState` de la SOURCE. Deux
   consequences : le `AddEffect` du behaviour de cast passe desormais `scale_from_source=True` (mirror de
   l'`AbilityStateReference` natif), et l'effet CAPTE depuis le live (que `EffectsState.seed` scale sur le
   PORTEUR) re-resout son niveau depuis `self.source` via le resolveur `unit_ctx_of` du contexte de coup.
   Sans ca l'effet lisait `extraPierceRatio` au niveau de l'ALLIE — la courbe VARIE (10 / 12 / 15).
2. **AUCUN gate `CurrentAbilityIs`** (contraste GravitonRifle, qui en a un). Le bonus s'applique donc a
   l'attaque **NORMALE** ranged du porteur. Le port ne cablait l'agregateur `piercing_bonus_from_effects`
   que sur la voie ABILITY -> il fallait le cabler sur la voie NORMALE (`damage_ops.execute`), avec
   `ability_type=None` (une attaque normale n'a pas d'AbilityOrEffect d'ability : les effets gates
   `CurrentAbilityIs` restent muets, comme le natif).
3. **`IsRangedAttack | IsOverwatchAttack` est une DISJONCTION.** `Overwatch_AutoAttackEffect` resout son
   coup par `UseActiveAbility(NormalAttack)` : cote port c'est `AttackDamageOperation.execute`, qui ne
   savait pas distinguer un overwatch. Ajout d'un flag `is_overwatch` (passe par `OverwatchAutoAttack`)
   pour que le gate reste vrai sur un overwatch de MELEE (le mover arrive au contact).

Le terme entre dans le clamp UNIQUE du natif :
`GetAttackPiercingDamageRatio(damageProfile, attacker, defender, isMelee, attackModifier, defenderModifier)`
(signature LUE) = `Min(100, Max(base>0, dirPierce + extraPierce + defenderModifier + attackModifier +
basePierce))` — `attackModifier` EST la somme des `BaseEffect$$PiercingBonusForAttack`. Le port le passe
donc a `battle_query.select_weapon_pierce(..., effect_bonus=...)` pour qu'il entre dans la MEME somme,
jamais dans un second clamp.

**MESURE LIVE — decomposition par etage** (probe `--phase ab`, `--phase ab_noarmor`, `--phase samples`) :

| etage | scenario | resultat |
|---|---|---|
| controle | allie SANS buff, cible armure 3513 | live 1798 == offline 1798 (percage 65 = profil Plasma) — **le port de base est bit-exact pour ce couple unite/arme** |
| « le buff ajoute-t-il du DEGAT ? » | allie AVEC buff, cible **armure 0** | live 3352 == offline 3352 (**bit-exact**) -> a armure nulle le percage est inerte : le buff n'ajoute **AUCUN** degat. C'est bien un canal PERCAGE et rien d'autre |
| magnitude | allie AVEC buff, cible armure 3513, 7 tirs | valeurs live `1921, 2422, 2700, 2015, 2445, 2153` (+ `2617` sur un autre run) |

L'enveloppe des 7 tirs IDENTIFIE le ratio live (bornes du port = `[int(2250*p/100), int(3376*p/100)]`,
base = Attack 2813 +/- spread 20 %) :
- il faut `p >= 80` pour que **2700** soit atteignable (`p = 79 -> borne haute 2667 < 2700`) ;
- il faut `p <= 85` pour que **1921** soit atteignable (`p = 86 -> borne basse 1935 > 1921`) ;
- **4 valeurs sur 7 depassent 2194 = la borne haute a `p = 65`** -> sans le bonus, le port ne peut PAS
  produire ce que le live produit : **le bonus est PORTANT**, et la garde le prouve.

`p in [80, 85]` avec `extraPierceRatio[L50] = 15` et un profil Plasma a 65 -> **`p = 80`**, exactement ce
que le port calcule.

## 5ter. Ce qui n'est PAS couvert par #123

- **Bit-exactitude du coup de l'ALLIE quand il est buffe ET que la cible a de l'armure.** Le controle
  (sans buff) et le cas armure-0 (avec buff) sont bit-exacts ; le cas buffe-avec-armure diverge (ex.
  live 1921 / offline 2301 ; live 2617 / offline 2248). La divergence n'est **pas** causee par le port
  de #123 : un balayage exhaustif `bonus de percage 0..40` x `tirages RNG brules 0..24` (1025
  combinaisons, probe `--phase ab`) ne reproduit **aucune** valeur live — donc ni la valeur du percage,
  ni un decalage de flux RNG ne l'expliquent, et le port SANS le bonus (`bonus = 0`) ne matche pas
  davantage. L'etage divergent est en amont du bonus (modele de tirage `reduce-then-roll` du port vs
  natif quand les bornes reduites changent). **CANDIDAT fable-solver**, hors perimetre #123 : c'est le
  moteur de degat de l'attaque normale, pas Hailstrike.
- **Face DECISION** : `HailstrikePlaybook` (`GetTargetUtility`, `GetPierceRatioUtility`,
  `HasRangedAttackAndCanAttackThisTurn`) n'est pas portee ; la prediction ne passe pas encore
  `effect_bonus` a `select_weapon_pierce` (meme residu que GravitonRifle avant #113).
- **`overwatch` reel** : le flag `is_overwatch` est cable (`OverwatchAutoAttack` le passe) mais n'a pas
  ete confronte live (il faudrait un mover qui declenche l'overwatch d'un allie buffe).
- **Re-pose / refresh** de l'effet 1509 sur une unite qui le porte deja (le probe re-caste ; le gate
  « deja present » du port no-ope) — non confronte.
- **Gate de ciblage** de 1214 : inchange depuis §7 (le filtre STATIQUE `TargetingOptions` n'est pas porte ;
  le test prend ses cibles dans `abilityTargets.fromHere`).

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
- ~~**`ExcruciatingFrequencies` / `DarkTalonStrike` face DECISION** : geometrie de ligne sans le gate
  d'elevation (§1, spillover).~~ **FERME par #124** (`case-124-elevation-gate-decision.md`).
- **`tileComponent+0x40` vs `IsWalkable`** : la branche `checkWalkable == False` du natif teste le
  drapeau de tuile SEUL (sans le composant MUR) ; le port utilise `board.walkable` (qui fond les deux).
  Inerte pour ses call-sites (`FilterContinuous(HasUnit & ...)` en aval).
