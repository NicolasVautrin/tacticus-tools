# #572-r1 / #564-r1 / #564-r2 / #564-r3 — SOIN, RÉSURRECTION et RÉSERVOIRS DE PV

**Statut : les QUATRE items RÉSOLUS et CONFRONTÉS LIVE** (build `rnca9r7q6c`, session 65).
35 crans, **7 mutations posées, 7 rouges**.

---

## 1. `#572-r1` — un stat-mod HEALTH relève le MAXIMUM, et le port avait deux réservoirs

### Ce que le décompilé tranche

Le résidu posait la question en deux branches (« `hp_max` DÉRIVE de `UnitStats[HEALTH]` ou les
stat-mods HEALTH sont ROUTÉS vers `HealthComponent` ? »). Le natif ne laisse pas le choix :

`IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` — **xref UNIQUE** d'`ApplyModifier`, donc
foyer unique de toute stat-modification — a un `switch (statModifier.StatType)` dont **trois** cases
seulement vont à `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier` :

| case | `StatType` | composant natif |
|---|---|---|
| 4 | `Armor` | `ArmorComponent` |
| **5** | **`Health`** | **`HealthComponent`** |
| 20 | `NumberOfMembers` | `GroupUnitComponent` |

Toutes les autres vont à `StatComponent$$ApplyModifier`. **Pour la santé, le natif n'a AUCUN
`StatComponent`** : la modification vit dans le `ValueModification` (+0x28) du composant fill-up
lui-même, et

```
get_CurrentMaximumValue() = override ?? ( Math.Min(int.MaxValue - initial,
                                          Math.Max(-initial, modTotal)) + base )
```

`+0x10` = `initial` (part `StatPart.Initial`), `+0x14` = `base`, que
`IdunBattle.Entities.Components.FillUpStatComponent$$Initialize` pose égaux (`+0x10 = +0x14 = +0x18`).

### Le port

`HealthComponent` (runner) porte désormais le layout complet — `max_initial`, `max_base`,
`max_modification`, `max_override` — et `current_maximum_value()` en mirror 1:1. **`hp_max` devient
la LECTURE de ce calcul** (property ; le setter est `ApplyModifier` case 2, qui pose
`+0x14 = +0x10 = value`), donc **aucun des ~40 lecteurs existants n'a eu à changer**. `stat_ops`
route HEALTH vers ce composant pour les quatre parts (`Modification`, `ResetModification`,
`Override`, `RemoveOverride`).

⚠ **Le seed lisait DÉJÀ le mauvais canal, et le résidu ne le disait pas.**
`observeBattle.hpMax` lit le champ **brut** `+0x14` (`game/match-state.ts::COMP_FIELD.hpMax`), pas
`GetStat(Health, StatPart.Maximum)`. `hp_max` ratait donc aussi les modifications **déjà posées au
chargement**, pas seulement celles posées en cours de simulation.

### Le lecteur : `context.py::_get_stat` réécrivait la ventilation

Il route HEALTH vers `HealthComponent` depuis longtemps, mais avec `if p in (2, 3): return mx` —
`Maximum` et `Initial` confondus. Ils **coïncident au déploiement** et **divergent** dès qu'une
modification existe : le fix aurait donc déplacé l'erreur de `Maximum` vers `Initial` (consommateur
réel : `ghost_revive`). Le bloc **délègue** maintenant à `HealthComponent.get_stat_part`, mirror
d'`IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart`.
⚠ Ce fichier est dans `runner/abilities/**` — édition minimale, hors du territoire de la tranche,
signalée au rapport.

### Confrontation LIVE — `probe_572r1_hpmax_effectif.py` (gate OUVERT de `1061`)

| canal | natif | port |
|---|---|---|
| **MAXIMUM EFFECTIF** (`combatSnapshot.healthMax` = `GetStat(Health, StatPart.Maximum)`) | 10038 → **20008** (Δ **9970**) | 10038 → **20008** (Δ **9970**) |
| **contre-lecture, canal BRUT** (`observeBattle.hpMax` = `+0x14`) | 10038 → **10038** | — |

Le second est ce qui rend le premier non trivial : il **établit** que la modification vit dans
`+0x28` et pas dans `+0x14`. Un banc qui aurait lu `observeBattle.hpMax` — le canal dont le runner
seed `hp_max` — aurait vu « natif inchangé, port inchangé » et conclu à un accord, résidu intact.

Parts du port après cast : `current 20008 · maximum 20008 · initial 10038 · modification 9970`.

---

## 2. `#564-r1` et `#564-r2` — deux problèmes de MONTAGE, résolus par deux leviers

Ni l'un ni l'autre n'était un défaut de port. Le banc unique `probe_564r1r2_soin_et_no_action.py`
les lève tous les deux :

1. **`--unit-stat "<vid>:Health=H,RemainingHealth=h"` blesse AU MONTAGE**, sans dépendre d'un coup
   de l'IA. Le caster étant dans **sa propre** patte de `GetHealTargets`
   (`Healable(caster@0x48, caster + AdjacentFriends(...))`), un caster blessé **se soigne lui-même** :
   le volet SOIN cesse de dépendre d'une géométrie d'adjacence favorable ;
2. une **3ᵉ unité joueur qui n'agit pas** empêche le cast de clôturer le tour → `toActivate` reste
   lisible juste après le cast.

### Le SOIN, en DEUX RÉGIMES (décomposition par étage, jamais un scalaire fitté)

`IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp` = `Min(amount, CurrentMaximumValue -
Current)`. On mesure donc le **montant** d'un côté et le **plafond** de l'autre :

| cible | manquant | soin natif | port |
|---|---|---|---|
| caster (`adeptHospitaller`) | 39 000 ≫ `hpToHeal` | **2992** | **2992** |
| 3ᵉ unité (`adeptCanoness`) | 1 000 < `hpToHeal` | **1000** | **1000** |

`2992` = `ConfigVar(0x20)` = `AbilityVariableType.hpToHeal`, level 50 × mult 180 %. **Première
confrontation de ce montant à un delta de PV natif.** Un port au bon plafond et au mauvais montant
est vert sur l'un et rouge sur l'autre ; un seul régime ne séparerait pas les deux étages.

### Le `no-action`

`toActivate` **[81, 85] → [85]** : le caster a consommé son action, la 3ᵉ reste activable (donc le
canal est lisible), et **le ressuscité n'y est pas**. Ses flags natifs portent
**`NoActionAvailable`**. C'est le bras `if (!options) processor.<slot 0x23>(unit, 1)` =
`IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute`, le « and are unable to act on
this turn » de l'i2 — confronté pour la première fois.

Tuile de réapparition et PV plafonnés : **accord** sur ce montage-ci aussi (3 unités joueur, pas 2).

⚠ **Deux flags natifs que le port ne pose PAS**, mesurés au passage :
`ActiveAbilityUsed` (le `Add(2)` que `update_flags_on_resurrect` déclare non porté — cette mesure
est le premier régime qui l'exerce) et `TurnTerminated`. → résidu **#564-r4**.

---

## 3. `#564-r3` — les étages en aval du gate, aux polarités LUES une par une

Quatre gates portés **au rang natif** (entre `CanBeResurrected` et la première mutation). **Leurs
polarités ne sont pas homogènes** — deux refusent quand ils rendent VRAI :

```
if ( TilesAreOccupied(tiles))                     return;   <- VRAI = refus
if (!TilesAreWalkable(unit, tiles))               return;   <- FAUX = refus
if ( GetFeetCount(unit) != unitFeetTiles.Count)   return;
if ( IsTileReservedForAnotherUnit(tiles, unit))   return;   <- VRAI = refus
```

Les **deux** gates de tuile sont littéralement les **mêmes slots d'`IBattleQuery`** que les gates
amont de `MoveUnitOperation` (`0xa1` `IsWalkableTile`, `0xa5` `IsTileReservedForAnotherUnit`,
résolus par `data/symbols/<build>/metadata/interface_slots.tsv`) : le port **réutilise leur foyer**
(#448-r1-r1-r2-r2-r1) au lieu d'en écrire un second — une correction de polarité profite aux deux.

Deux lectures qui ne se devinent pas :

* **`allowSteppable: 1`** dans `IsFreeTile` est lu aux octets du call-site, et il est LOAD-BEARING :
  c'est ce qui laisse réapparaître **sur** un decoy `Steppable`, que `KillSteppableUnits` écrase
  juste après. Avec `0`, le cas nominal de `1039` serait refusé dès qu'un decoy occupe la tuile ;
* **un cadavre GARDE ses pieds** — c'est `ResetFeet`, **après** ce gate, qui détache leur `TileId`.
  Donc `GetFeetCount != tiles.Count` **passe** sur un mono-hex mort. S'il refusait ici, plus aucune
  résurrection ne passerait.

S'ajoute `ResurrectUnitOperation$$ResetPersistentData` : **deux** `ClearAllPersistentData`
(le `PersistentDataComponent` **et** le `TriggeredAbilityComponent`), avant `SetHealth`.

⚠ **`dest_coord is None` n'est PAS une empreinte VIDE**, même distinction que le `()` vs `None` du
lift-off. Aucun call-site NATIF ne passe d'empreinte vide (`ResurrectBehaviour` zippe
`targets × tiles`, l'Ambush passe `Tiles(decoy)`) : `None` est un régime **propre au port**, où les
gates sont **NON APPLICABLES**. Les y armer ferait refuser toute résurrection par
`GetFeetCount != 0`.

**Reste NON PORTÉ, et c'est dit** : l'empreinte **multi-hex**. Le port n'écrit qu'une
`PositionComponent` là où le natif joue `ResetPreviousTileIfStillOwned` + `ResetFeet` +
`processor.<slot 0x7e>(unit, unitFeetTiles)`. Le fermer exige que la feuille DSL `Resurrect`
transmette la **liste** de tuiles — foyer `runner/abilities/behaviours/lifecycle.py`. Conséquence
chiffrée **nulle** sur les deux call-sites portés, tous deux mono-hex.

---

## 4. Mutations — sept posées, sept rouges

| # | mutation | message verbatim |
|---|---|---|
| M1 | routage HEALTH désarmé | `le maximum n'a pas bouge (10038 -> 10038)` |
| M2 | clamp bas `max(0, mod)` | `clamp bas faux : 1000 (attendu 0)` |
| M3 | `Initial` confondu avec `Maximum` | `` `Initial` a suivi la modification (20008) `` |
| M4 | `hp_max` rend la BASE | `le maximum n'a pas bouge (10038 -> 10038)` |
| M5 | polarité de `TilesAreOccupied` | zip du pipeline resurrect rouge |
| M6 | gates armés sur `dest_coord=None` | `une resurrection SANS tuile a ete refusee` |
| M7 | `ResetPersistentData` désarmé | `le sac de donnees persistantes a survecu` |

⚠ **M6 est d'abord ressortie VERTE** contre les trois seuls tests préexistants qui exercent
`dest_coord=None` (les bancs #462-r4e-o) : leurs unités n'ont pas de `PositionComponent`, donc
`GetFeetCount` y rend **0** et le gate muté passe quand même. Seule la garde dédiée la voit.
**Un fichier qui exerce un régime ne garde pas forcément ce que ce régime discrimine.**

---

## 5. Résidus ouverts

* **#572-r3** — `Armor` (4) et `NumberOfMembers` (20) sont les deux autres cases fill-up du switch
  natif ; côté port elles vivent encore dans `UnitStats` sous un `StatComponent`, dont
  `StatPart.Current` et `StatPart.Maximum` rendent **la même valeur** là où le natif les sépare.
  Le capteur existe pourtant des deux côtés (`combatSnapshot.armorMax` / `.numberOfMembersMax`,
  #477-r15-r5/r7).
* **#564-r4** — `ActiveAbilityUsed` et `TurnTerminated`, posés par le natif sur le ressuscité,
  ne le sont pas par le port.

Non traité et **nommé**, hors résidu : l'empreinte multi-hex de la résurrection (§3), dont le foyer
est chez un autre porteur.
