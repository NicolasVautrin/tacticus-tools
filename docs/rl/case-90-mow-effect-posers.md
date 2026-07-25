# Case #90 lot B — classification par PATRON D'ARTEFACT des 10 abilities MoW restantes,
# + port du lot « POSE D'EFFET(S) SEULE » (5 items)

**Statut** : classification RENDUE (10/10) ; lot « pose d'effet(s) seule » (5 items) **PORTE ET VALIDE
LIVE** (session Frida 71, build `gqfc5mff6c`, boards `C1_02` / `C2_02`). Correctif 100 % Python
(`scripts/python/**`) — aucun changement `frida/hooks`, aucun rebuild, aucun reinject.

Contexte amont : `docs/rl/case-mow-offboard-cast.md` (la MoW est une entite ECS offline —
`MachineComponent`, `_load_machines`, effets MoW dans le seed `EffectsState`).

---

## 1. Gate de confrontabilite — les 10 sont confrontables

`python rl_duel.py build --list-pool` -> **8 MoW spawnables** :
`adeptExorcist · astraOrdnanceBattery · blackForgefiend · deathCrawler · orksRukkatrukk · tauBroadside ·
tyranBiovore · ultraDreadnought`.

Balayage gameconfig des porteurs de chacune des 10 abilities (tous slots : `activeAbilities`,
`passiveAbilities`, `mythicAbilities`) : **chaque ability a exactement DEUX porteurs, une MoW du POOL et
son jumeau NPC** (`*Npc*`), jamais de hero ni de summon. Ventilation :

| ability (id) | porteur MoW (pool) | jumeau npc (hors-jeu) | confrontable |
|---|---|---|---|
| PlagueburstMortar (1169) | `deathCrawler` | `deathNpcMoWCrawler` | OUI (mow) |
| DaemonicOrdnance (1148) | `blackForgefiend` | `blackNpcMowForgefiend` | OUI (mow) |
| MalleusRocketLauncher (1142) | `astraOrdnanceBattery` | `astraNpcMowOrdnanceBattery` | OUI (mow) |
| ForwardSpotter (1143) | `astraOrdnanceBattery` | idem | OUI (mow) |
| ThriceBlessedConflagration (1187) | `adeptExorcist` | `adeptNpcMoWExorcist` | OUI (mow) |
| DevastatingRefrain (1188) | `adeptExorcist` | idem | OUI (mow) |
| HeavyRailRifle (1160) | `tauBroadside` | `tauNpcMoWBroadside` | OUI (mow) |
| TwinSmartMissileSystem (1161) | `tauBroadside` | idem | OUI (mow) |
| SquigMine (1201) | `orksRukkatrukk` | `orksNpcMoWRukkatrukk` | OUI (mow) |
| MacroPlasmaIncinerator (1159) | `ultraDreadnought` | `ultraNpcMoWDreadnought` | OUI (mow) |

Aucune n'est bloquee : les 10 se castent depuis un runner `rl_duel build --p-mow <carrier> --board C1_02`.

---

## 2. LIVRABLE — classification par PATRON D'ARTEFACT (10/10)

Toutes ont le meme *point d'entree* natif (`<X>Ability.ExecuteBehaviour`, namespace
`IdunBattleLogic.Entities.Abilities.Active[.Loki]`) : ce n'est donc PAS un discriminant. Le patron est la
**forme de l'arbre DSL** et la **famille de feuilles** en bas.

### Groupe A — « POSE D'EFFET(S) SEULE » (5 items) — **PORTE**

Le behaviour de CAST n'est QU'un arbre d'`AddEffect`/`AddBondEffect`. **Aucune** attaque, **aucun** spawn,
**aucune** mutation de stat. Le degat vit dans la PHASE 2 (l'ability *triggered* portee par l'effet).

| ability | VA `ExecuteBehaviour` | arbre | cible du cast |
|---|---|---|---|
| HeavyRailRifle (1160) | `@1811e7d70` | `AddEffect(1334→cible) & AddEffect(1333→la MoW)` | unit |
| MacroPlasmaIncinerator (1159) | `@1811f1910` | `AddEffect(1335→Walkable(SameElevation(TrianglShape(cible,dir)))) & AddEffect(1336→la MoW)`, `TurnsFromRounds(1)` | tile |
| DevastatingRefrain (1188) | `@1811d3730` | `AddEffect(1403→la MoW) + AddBondEffect(1402→cible + 3 voisines {3,1,5}/{0,2,4})` | tile |
| SquigMine (1201) | `@18120b350` | `AddEffect(1441→Cache(cible + PickRandomly(pool, nrOfTiles)))`, `TurnsFromRounds(nrOfRounds)` | tile |
| MalleusRocketLauncher (1142) | `@1811f1d90` | `Inform + AddBondEffect(1308) + AddEffect(1309) + AddEffect(1310)`, tous sur la tuile ciblee | tile |

**Briques exigees** : feuilles `AddEffect`/`AddBondEffect` (existantes) + selecteurs de TUILES
(`TilesInTriangleShape`, `TileFromVector`, `Walkable`, `TilesOnSameElevation`, `EntitiesWithoutEffects` —
**ajoutes ici**) + predicat `IsPositionMachineForCurrentPlayer` (**ajoute ici**) + conversion
rounds→turns fidele (`convert_rounds_to_turns`, **ajoutee ici**).

### Groupe B — « ATTAQUE DSL filtree par un ETAT + entretien de cet etat » (2 items)

`AttackWithAbilityDamage` sur un ensemble d'ennemis SELECTIONNE PAR UN PREDICAT D'ETAT, puis pose/refresh
de cet etat. Meme squelette que le groupe A pour la partie effet, mais avec une **feuille d'attaque**.

| ability | VA | arbre |
|---|---|---|
| TwinSmartMissileSystem (1161) | `@1812175c0` | `AttackWithAbilityDamage(caster, EntitiesWithAnyEffect(Enemies, 1122 Markerlight), MinMaxDamage, Direct(profil), ConfigConst(nrOfHits))` **&** `If(HasEffect(cible,1122), ChangeEffectTurns(cible,1122,TurnsFromRounds(2)), AddEffect(1122, cible, TurnsFromRounds(2)))` ; `ExecuteAtomic(…, 0x2a)` |
| PlagueburstMortar (1169) | `@1811c3db0` | cibles = `Unique( Filter(Enemies(caster,cible), GetIsValidAdjacentEnemyTrigger) + Filter(Enemies(caster,Units(AdjacentTiles(cible))), même prédicat) )` ; `AttackWithAbilityDamage(…, hits=GetHits)` **&** `AddEffect(1065 Pinned → cibles)` **&** `AddEffect(1244 Contaminated → cible + PickRandomly(AdjacentTiles(cible), ConfigVar(0x66=nrOfTiles) − 1))` |

**Briques manquantes** : `EntitiesWithAnyEffect` (jumeau de `EntitiesWithoutEffects`, trivial),
`ChangeEffectTurns` (feuille de refresh de duree — **absente**), et pour 1169 le predicat custom
`PlagueburstMortarAbility.GetIsValidAdjacentEnemyTrigger @1811c43c0` (a RE ; `GetAdjacentEnemies
@1811c4330`, `GetMainDamageTarget @1811c44b0`, `GetAdjacentDamageTargets` sont ses helpers de
preview/playbook). Le reste (`AttackWithAbilityDamage`, `Filter`, `Unique`, `ConfigVar`, `Difference`,
`PickRandomly` folde) existe.

### Groupe C — « SPAWN template » (1 item, seul de son patron)

| ability | VA | arbre |
|---|---|---|
| ForwardSpotter (1143) | `@1811dfa90` | `Spawn( caster@0x160, First(SortTilesByUtilityForSummon(TilesUnitCanAttackFrom(CanAddUnit(AdjacentTiles(cible)), caster, unitId, 1).Otherwise(CanAddUnit(AdjacentTiles(cible))), 7, owner), Direct(nrOfSummons)), GetStringConstant(0)=astraSmnGuardsman, WithStatsFromConfig(config, level).onAppearance = PerformAIAttack(ActiveTarget@0x180, 1) )` |

C'est **exactement** le template `SpawnSummon` deja porte (SendInTheNextWave / DeathFromAbove /
Incursion / Poxwalkers) : `Spawn` + `WithStatsFromConfig` + on-appearance `PerformAIAttack`.
**Briques manquantes** : les DEUX selecteurs de tuiles de placement — `TilesUnitCanAttackFrom`
(`DSLFactory`, tuiles d'ou l'unite pourrait attaquer) et `SortTilesByUtilityForSummon` (tri d'utilite IA,
mode 7) — plus `TargetsSelector.Otherwise` (fallback si le 1er selecteur est vide). Ces trois-la sont des
selecteurs **AI/pathfinding lourds** : la doctrine slice-18/19 autorise leur COLLAPSE imperatif
(comme `SendInTheNextWaveAbility.GetSpawnTilesSelector @181206cc0` l'a fait), ce qui rend l'item
**portable rapidement** — mais il est SEUL de son patron dans ce lot.

### Groupe D — « composite lourd » (2 items, chacun seul de son patron)

| ability | VA | arbre (structure) | pourquoi a part |
|---|---|---|---|
| DaemonicOrdnance (1148) | `@1811cf4d0` | `ChangeStat(owner, CritChance, +extraCritChance)` **+** `AttackWithAttackDamage(owner, Enemies(Units(Filter(GetTargetAreaTiles(), HasEffect(Tiles(ActiveTarget), 5=feu)))), MinMaxDamage, Direct(profil), Direct(GetHits), AbilityOrEffect(1148))` **+** `ChangeStat(owner, CritChance, −extraCritChance)` **+** `If(HasEffect(owner,1316), AddOrUpdateStaticStatModifierEffect(owner, 1316, stat 9, (TotalActiveAbilityUsed(owner,1148)+1) × extraCritDmg))` **+** `AddEffect(5=feu → GetTargetAreaTiles())` | 5 etages heterogenes : buff/debuff temporaire ENCADRANT l'attaque, attaque **conditionnee par un effet de TUILE** (le feu pose au cast precedent = 2-phases), et un **stat-modifier cumulatif indexe sur le nb d'usages** |
| ThriceBlessedConflagration (1187) | `@181215060` | `Foreach( Enemies(owner, cible + GetTilesInLine(First(SortByFormula(SurroundingTiles(cible,1), Count(GetTilesInLine(ActiveTarget)))))), <lambda b__0 @1812188c0> )` **&** `If(HasFaction(cible, 1), AddEffect(1401, cible, TurnsFromRounds(nrOfRounds)), AddEffect(1436, cible, TurnsFromRounds(nrOfRounds)))` | la cible est un ALLIE (buff `ThriceBlessedConflagration_ExtraPctDamage`) et le degat part sur une **LIGNE** choisie par optimisation (`SortByFormula` sur la longueur de ligne), avec un corps `Foreach` = **lambda C#** (`AttackUnit @181214d30` / `DamageUnit @181214ee0`), pas un nœud DSL |

**Briques manquantes** : `TotalActiveAbilityUsed` (formule), `AddOrUpdateStaticStatModifierEffect`
(feuille), `HasFaction` (predicat), `ThriceBlessedConflagrationAbility.GetTilesInLine @181215610`
(geometrie de ligne), et le portage du corps `Foreach` en feuille dediee (les lambdas C# ne sont pas des
nœuds `DSLFactory` : il faut porter `AttackUnit`/`DamageUnit` comme feuilles d'ability).

### Recapitulatif dispatch

| groupe | items | brique pivot | statut |
|---|---|---|---|
| A — pose d'effet(s) seule | 1160, 1159, 1188, 1201, 1142 | selecteurs de TUILES + `AddEffect`/`AddBondEffect` | **PORTE + valide live** |
| B — attaque filtree par etat | 1161, 1169 | `EntitiesWithAnyEffect`, `ChangeEffectTurns`, predicat custom 1169 | a porter (1 tranche) |
| C — spawn template | 1143 | `TilesUnitCanAttackFrom` / `SortTilesByUtilityForSummon` (collapsables) | a porter (rapide, seul de son patron) |
| D — composite lourd | 1148, 1187 | `AddOrUpdateStaticStatModifierEffect` + `TotalActiveAbilityUsed` (1148) ; `GetTilesInLine` + feuille `AttackUnit` (1187) | 1 tranche CHACUN |

---

## 3. Le lot porte (groupe A) — RE et decisions

### 3.1 Geometrie hexagonale par DIRECTION — RE complet, aucune deduction

`CubeDirections..cctor @180e30ec0` alloue six `int[3]` (cube x/y/z aux offsets +0x20/+0x24/+0x28) puis
les range dans l'array statique indexe par direction : `[V0, V3, V2, V1, V4, V5]` avec
`V0=(0,-1,1) V1=(0,1,-1) V2=(1,0,-1) V3=(1,-1,0) V4=(-1,1,0) V5=(-1,0,1)`.
`AxialCoordinate.NeighbourAt @180e2c1f0` lit `array[dir][0]` (= dx, ajoute a la COLONNE) et
`array[dir][2]` (= dz, ajoute au z cube `row − (col + (col&1))/2`) — c'est **exactement** la conversion
`hexgeo.to_cube`/`from_cube` (meme parite odd-q-UP, live-validee vs `boardGraph`). D'ou la table :

| direction | (dx, dz) cube | offset (odd-q-UP) |
|---|---|---|
| 0 | (0, +1) | **S** |
| 1 | (+1, 0) | **SE** |
| 2 | (+1, −1) | **NE** |
| 3 | (0, −1) | **N** |
| 4 | (−1, 0) | **NW** |
| 5 | (−1, +1) | **SW** |

CONFIRME LIVE : `DevastatingRefrain` (directions `{3,1,5}` du ctor) caste sur `(2,3)` marque `(2,2)`=N,
`(3,4)`=SE, `(1,4)`=SW — et sur `(1,1)` (colonne IMPAIRE, autre parite) marque `(1,0)`=N, `(2,1)`=SE,
`(0,1)`=SW.

`BattleQuery.GetTilesInTriangleShape @18106ba60` = la tuile + les DEUX voisines du **coin** `dir` (les
deux branches de parite du decompile donnent le meme couple de directions) :
`0={SW,S} · 1={S,SE} · 2={SW,NW} · 3={SE,NE} · 4={NW,N} · 5={N,NE}`. `dir > 5` -> la tuile seule.

### 3.2 `IsPositionMachineForCurrentPlayer`

`DSLFactory.IsPositionMachineForCurrentPlayer @180df4d10` -> `IsPositionMachineForPlayerTrigger
.ShouldTrigger @180fa3520` :

```
turn = state.GetMatchTurn() ; player = state.GetPlayer(turn.CurrentPlayerId)
if (player == null) return false
return battleQuery.<MachineOfWarPosition>(player) == this.Position (@+0x20)
```

-> le slot (`MachineOfWarPosition` 1=Top / 2=Bottom) de la MoW du **joueur COURANT**, pas du caster.
Port : `ctx.current_player_machine_position` (slot de la `MachineComponent` dont l'`OwnerComponent.player`
== `state.current_player_id`), None -> False.

### 3.3 `TurnsFromRounds` — l'identite est CONTREDITE dans nos runners

`BattleQuery.ConvertRoundsToTurns @181058af0` = `count(joueurs du turnOrder dont PlayerType != 2) ×
rounds`. **MESURE** : `observeBattle.counts.player = 3` (2 joueurs + l'unique Environment permanent) ->
`convert(1) = 2`, et le live confirme (`MacroPlasmaIncinerator` `TurnsFromRounds(1)` et `SquigMine`
`TurnsFromRounds(nrOfRounds=1)` posent leurs effets a `remaining = 2`).

Le helper historique `abilities/base.py::turns_from_rounds` rend l'IDENTITE (sa docstring anticipait
justement « ne divergerait QUE dans une bataille a count>=2, ex. arene MoW »). **Aucun call-site
historique n'est retouche ici** (blast radius : des dizaines de ports live-valides). A la place :

- `State.turn_order_player_count` (seede par `load_state` depuis `observeBattle.counts.player − 1`),
- `abilities/base.py::convert_rounds_to_turns(state, rounds)` = mirror exact @181058af0 (identite si le
  compteur est absent),
- `AddEffect`/`AddBondEffect` acceptent un `duration_turns` **deja converti** (prioritaire sur
  `duration_rounds`) — opt-in, defaut `None` = comportement historique inchange.

> **A INSTRUIRE (hors perimetre)** : reconcilier `turns_from_rounds` (identite) avec la mesure. Soit les
> effets historiques ne passent PAS par `TurnsFromRounds` (leur duree vient de `DefaultAmountOfRounds`,
> deja en TOURS — c'est ce que suggere `test_effect_stun_live`, qui compare `default_amount_of_rounds
> (1162)` au `remaining` live), soit une partie des durees portees est a moitie de la valeur native. La
> tache demande un avant/apres CHIFFRE par effet, pas un flip global.

### 3.4 Fichiers

Briques partagees (chacune dans SON namespace natif) :
- `engine/entities/selectors.py` — `TilesInTriangleShape`, `TileFromVector`, `Walkable`,
  `TilesOnSameElevation`, `EntitiesWithoutEffects`, `neighbour_at` + table `_CUBE_DIRECTIONS`
  (`IdunBattle.Entities.Selectors` / `IdunBattle.Utils.Hex`) ; `SurroundingTiles` accepte desormais un
  centre du domaine ID (cast tile-target).
- `engine/entities/triggers.py` — `IsPositionMachineForCurrentPlayer` (`IdunBattle.Entities.Triggers`).
- `engine/dsl/base.py` — champ `DslContext.current_player_machine_position`.
- `engine/runner/abilities/behaviours/effects.py` — `duration_turns` sur `AddEffect`/`AddBondEffect` ;
  `AddBondEffect` ITERE desormais son selecteur-cible et accepte le domaine TILE (mirror
  `AddBondEffectBehaviour`, meme mold qu'`AddEffectBehaviour` — les call-sites mono-unite historiques
  sont inchanges).
- `engine/runner/state.py` + `snapshot.py` — `turn_order_player_count`.

Classes d'ability (une par FACTION, comme l'org existante) :
`abilities/tau.py` (**nouveau module**, HeavyRailRifle) · `ultramarines.py` (MacroPlasmaIncinerator) ·
`sisterhood.py` (DevastatingRefrain) · `orks.py` (SquigMine) · `astramilitarum.py`
(MalleusRocketLauncher) ; 5 entrees dans `abilities/handler.py`.

---

## 4. Validation

Test livre : `scripts/python/tests/engine/runner/test_mow_effect_posers_live.py` (**8 tests, tous
passants**), sans AUCUNE constante attendue en dur — l'oracle est le cast natif.

**Protocole** : pour chaque ability, runner isole avec sa MoW -> cible legale (`abilityTargets`) ->
execution du port sur l'etat charge (`load_state` + `_apply_active_ability`) -> **meme cast LIVE** ->
comparaison de l'EMPREINTE D'EFFETS `{entite|TUILE -> {effectType: remaining}}`. Les effets de TUILE ne
sont visibles que par `tileMeta` (`readEffectsByTile`), ceux d'unite/MoW par `decisionView` (cle MoW =
`casterId`, PAS le `id` de la ligne qui est la plateforme).

| test | resultat |
|---|---|
| 1160 HeavyRailRifle | empreinte offline == live : `{cible: {1334: 0}, mow: {1333: 0}}` |
| 1159 MacroPlasmaIncinerator | empreinte offline == live : 3 tuiles `{1335: 2}` + mow `{1336: 2}` |
| 1188 DevastatingRefrain | empreinte offline == live : 4 tuiles `{1402: 0}` + mow `{1403: 0}` |
| 1201 SquigMine | POOL du port == geometrie INDEPENDANTE (hexgeo + tuiles legales) ; cardinal `1+nrOfTiles` et signature d'effet `{1441: 2}` identiques offline/live ; les deux tirages inclus dans le pool |
| 1142 MalleusRocketLauncher | empreinte offline == live : 3 effets (1308/1309/1310) sur la SEULE tuile ciblee |
| 1159 filtre ELEVATION (isole) | cible `(4,3)` elev 4, triangle brut `{(4,4) elev 4, (5,4) elev 2}` tous walkable -> `(5,4)` ecartee ; offline == live |
| 1159 filtre WALKABLE (isole) | cible `(1,3)`, triangle brut `{(1,4), (2,3) NON walkable}` ecart d'elevation 1 -> `(2,3)` ecartee ; offline == live |
| BRANCHE OPPOSEE de `IsPositionMachineForCurrentPlayer` | autre board `C2_02`, 2 MoW, main passee au camp adverse (slot 1) -> `machineSide=False` -> triplet COMPLEMENTAIRE `{0,2,4}` = {S,NE,NW} ; offline == live |

**Garde anti-degat fantome** intégrée au harnais : aucun PV ne bouge, offline NI live. C'est une
correction de fond : avant ce port, `_apply_active_ability` retombait sur le chemin GENERIQUE
`execute_ability_attack` (les 5 abilities ont toutes un `damageProfile` en `constants`) et infligeait des
degats que le natif ne fait PAS au cast.

**Non-regression** (tests CIBLES rejoues, 54 tests verts) : `test_mow_caster_load_live`,
`test_effect_stun_live`, `test_damage_crushingclaws_live`, `test_valkyrie_strike_migration_live`,
`test_spore_mine_launcher_live`, `test_supreme_commander_live`, `test_combat_restoratives_live`,
`test_mortis_round_live`, `test_sanctorum_missile_live`, `test_sky_strike_live`,
`test_summon_ability_ports_live`, `test_summon_spawn_live`, `test_cultdemagogue_migration_live`,
`test_load_state_board_elevation`, `test_scarab_summon_migration_live`, `test_runner_state_live`,
`test_turnflow_live`.

Probe reutilisable : `scripts/python/probe_90b_mow_effects.py` (`cast` / `sweep`) — mesure
AVANT/APRES sur les DEUX canaux d'effets.

---

## 5. Ce qui n'est PAS couvert (residus)

1. **PHASE 2 non portee** pour les 5 items : le degat differe (`HeavyRailRifle_AttackAbility`
   `GetFinalUnitDamageAmount @180f86360`, `MalleusRocketLauncher_AttackAbility.CreateBehaviour
   @1812226b0` / `GetTargetTiles @181222aa0`, `SquigMine_TileEffect.GetAttackBehaviour @180f6d660`, les
   effets `MacroPlasmaIncinerator_AutoAttack` / `DevastatingRefrain_Attack`). Le cast est fidele ; le
   coup qui suit ne l'est pas encore. C'est une **tranche `Abilities.Triggered.Loki` dediee**.
2. **`load_state` ne SEEDE PAS les effets de TUILE.** `EffectsState.seed` ne lit que
   `decisionView.units[].effects` + `mows[].effects` ; les effets de tuile ne sont exposes que par
   `tileMeta`. Consequence : un etat offline RE-CHARGE apres un cast a perdu les marquages de tuiles
   (mines, zones), donc (a) `EntitiesWithoutEffects([1441])` de SquigMine est **inerte sur un etat
   recharge**, (b) toute phase 2 tile-driven sera inconfrontable tant que ce canal n'est pas branche.
   **Correctif propose** : passer `tileMeta` a `load_state` (ou l'ajouter au `combatSnapshot`) et
   alimenter `EffectsState` avec les entrees keyees tile-id — meme cle que la pose `AddEffectOperation`.
3. **`EntitiesWithoutEffects` non discrimine live** (consequence de (2) + aucun runner frais n'a de mine
   preexistante) : un port qui l'oublierait passerait les tests actuels. Le nœud est porte fidelement,
   mais sa validation attend (2).
4. **GAP RNG #215 sur `PickRandomly`** (SquigMine) : quand `|pool| > nrOfTiles`, l'ENSEMBLE tire differe
   du live (le cardinal, le pool et la signature d'effet, eux, sont exacts). Aucune saturation du pool
   (`|pool| <= nrOfTiles`) n'est atteignable sur `C1_02`/`C2_02` sans mise en scene supplementaire.
5. **`turns_from_rounds` (identite) vs la mesure** — cf. §3.3, tache a instruire.
6. **Face DECISION MoW** toujours hors-jeu (le natif ne met que `EntityType.Unit` dans
   `decisionView.units` ; cf. `case-mow-offboard-cast.md` §8) : ces 5 abilities ne sont pas choisies par
   le playbook offline, seulement executees quand on les caste.
