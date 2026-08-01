# case-383 — `RammingSpeed` (1059) batchs 3/4 : PORTÉS et confrontés 4/4

Clôt `#353-r1` volet (b) côté PORT (la MESURE l'avait été par `#381`/`case-361`).
Suites ouvertes : `#381-r1` (mordant, §5), `#383-r1` (face COMBAT, §6).

## 1. Ce qui est livré

`RammingSpeedPlaybook$$MakeDamagePredictions` émet quatre batchs ; les deux derniers manquaient au
port. Ils y sont, sous la gate native :

```
list.AddRange(self)                                            // batch 2, le CASTER
if (!self.Any(p => p.Prediction.WillBeKill)) return list;      // <>c$$<MakeDamagePredictions>b__2_0
amount = <eval>( ExplodesAbility$$GetDamage(dsl) )             // ctx neuf : SEUL `+0x18 = caster`
tile   = RammingSpeedAbility$$GetTileToMoveTo(ability)
list.AddRange(GenerateAttackPredictions(…, Friends(<Caster>, AdjacentUnits(tile,1,3), 3),
                                        Get(amount), null, Nullable(0xf = DirectDamage), 0))
list.AddRange(GenerateAttackPredictions(…, Enemies(<Caster>, AdjacentUnits(tile,1,3), 3), …))
```

| élément | ce que le port fait | site |
|---|---|---|
| gate `WillBeKill` | `will_be_kill()` sur l'event du caster (`Any` sur 1 élément) | `prediction/abilities.py::_ramming_speed_self_events` |
| `amount` | arbre DSL `PercentageOf(StatAmount(Owner,Health,MAX), Sum(ConfigConst(1021,0xf), ConditionalAmount(HasEffect(Owner,1098), ConfigConst(1059,0xf), Get(0))))` | `prediction/ramming_speed.py::explodes_damage_tree` |
| tuile | MÊME mirror que la face COMBAT (`ramming_speed_charge_tiles_selector` + `RAMMING_SPEED_TILE_UTILITY`), substrat `Scene` | `…::tile_to_move_to` |
| sélecteurs | `Friends(AdjacentUnits(FixedTile(tile), 1))` puis `Enemies(…)` | `…::explosion_events` |
| étage dégât | `generate_multi_hit_attack_prediction(hits_override=1, profile_override="DirectDamage")` | idem |
| `friendly` | par BATCH (True pour `Friends`, False pour `Enemies`) | idem |

`hits = 1` n'est pas un choix : le slot `0x24` d'`IBattleQuery` que `GenerateAttackPredictions`
invoque est `BattleQuery$$GetAttackPrediction`, c'est-à-dire **exactement le 1ᵉʳ appel** de
`BattleQuery$$GetMultiHitAttackPrediction` (qui `memset(result,0,0xa0)`, appelle
`GetAttackPrediction(…, previousHitsPrediction = 0)` puis boucle `nrOfHits − 1` fois de plus).

Trois pièces d'infrastructure sont nées de ce port, parce que `make_damage_predictions` ne reçoit
que la `Scene` : `utilities/tile.py::scene_tile_leaf_ctx` (3ᵉ jumeau de `runner_tile_leaf_ctx` /
`tile_leaf_ctx`), `utilities/tile.py::SceneTileState` (adaptateur `.board`/`.effects` — passer la
`Scene` nue ferait lire une **méthode** `effects`), et `selectors/accessors.py::FixedTile`
(véhicule de collapse SINGULIER, `_within` attend UN centre, pas une liste).

## 2. Le bug que la généralisation a trouvé — la base est le maxPV, et le port lisait le COURANT

`StatAmount(Owner, Health, part = 2 → MAXIMUM)`. Le port lisait `UnitContext.get_stat(5, 2)`, qui
rend le **COURANT** : `entities/stats.seed_unit_stats` seede `Health` en `StatComponent` GÉNÉRIQUE
(« les stats fill-up sont seedées en StatComponent générique… le `FillUpStatComponent` spécifique
est posé au besoin »), et `StatComponent.get_stat_part(2)` = `get_CurrentValue`. Le canal du maxPV
côté `Scene` est `hpmax_by_id` (`observeBattle`).

L'axe était **INOBSERVABLE** tant que le montage passait `--hp-player`, qui pose `Health` **ET**
`RemainingHealth` (courant == max). Il s'ouvre avec un `--unit-stat <graft>:RemainingHealth=<n>`
appliqué APRÈS (l'ordre est celui de `rl_duel.build`).

MESURE (MC1_67, caster 30/60, niveau 8) : natif `[18, 27]` par voisin (25 % de **60**), port fautif
`[9, 15]` (25 % de **30**). Corrigé ; garde live `test_383_…_live.py::test_the_explosion_amount_is_a_share_of_MAX_health`,
garde offline `test_383_…_offline.py::test_amount_is_a_percentage_of_MAX_health_not_current`.

## 3. Une rectification de `case-361` §7 : ce n'est PAS `HasFaction`

`case-361` §7 écrivait « `DSLSelectors$$Friends`/`$$Enemies` allouent le **même**
`UnitsFromFactionSelector` à un bit près et **partitionnent** leur entrée par
`UnitExtensions$$HasFaction` ». C'est le faux négatif de déduplication du `CLAUDE.md` :

* `DSLSelectors$$Friends`/`$$Enemies` allouent la classe `DAT_18336e320`, `DSLSelectors$$UnitsFromFaction`
  la classe `DAT_18336e9b0` — **deux classes distinctes** ;
* leurs `.ctor` ont le MÊME corps (5 écritures de champ) ⇒ **dédupliqués**, un seul propriétaire
  dans la table de symboles, d'où le nom trompeur ;
* la classe réelle est celle dont ghidra nomme les AUTRES méthodes :
  `IdunBattle.Entities.Selectors.UnitsByTeamSelector`, dont `$$Select` délègue à `$$CountOrAdd`,
  qui filtre par `IdunBattle.Entities.UnitExtensions$$IsFriend(référent, other, state)` comparé au
  flag `+0x28` (1 pour Friends, 0 pour Enemies) ;
* `HasFaction(unit, factionId)` compare une **chaîne** (`FactionComponent+0x30`) — jamais un camp.

Le port (`entities/selectors/units.py`, filtre par `team`) était donc DÉJÀ juste ; c'est la RE
écrite qui était fausse. Corollaire lu au ctor : `+0x18` = le RÉFÉRENT (`of`), `+0x20` = le SET.

## 4. La confrontation

`probe_383_ramming_speed_explosion_port.py` — natif (`aiPlaybookPredict`) contre port
(`make_damage_predictions`), signature `(targetId, healthDmgMin, healthDmgMax, appliedHits)` triée.
Montage hérité de `probe_361` (géométrie scannée offline, drive, **`ensure_turn`**), et le probe
REFUSE de conclure si le caster n'a pas la main ou si le natif rend ≤ 2 events.

| bras (board / seed / niveau) | natif | port | tuile port == tuile native (cast réel) |
|---|---|---|---|
| MC1_67 / 38300 / 8 | 5 events | **==** | — |
| MC1_67 / 38300 / 8, caster **30/60** | 5 events | **==** | — |
| C1_03 / 38401 / 8 | 5 events | **==** | — |
| C1_20 / 38603 / 8 | 5 events | **==** | **oui** |
| MC1_63 / 38704 / 8 | 5 events | **==** | **oui** |
| **C1_74 / 38502 / 45** | 3 events | **≠** (5) | **non** → §5 |

Cinq gardes adversariales, chacune ROUGE (le port muté DIVERGE) :

| mutation | ce qu'elle ampute | port muté vs natif |
|---|---|---|
| `no-explosion` | les deux batchs (= l'état d'AVANT #383) | 2 pour 5 |
| `friends-only` | le batch `Enemies` | 3 pour 5 |
| `enemies-only` | le batch `Friends` | 4 pour 5 |
| `hp-current` | base COURANTE au lieu de MAX | `[9,15]` pour `[18,27]` |
| `tile-utility-only` | bucket réduit à `Tile(7)` (lecture réfutée par #353-r1) | 4 pour 5 |

## 5. `#381-r1` MORD sur ces batchs — mesuré, attribué, NON traité

Sur `C1_74 / 38502`, caster (2,0) et cible (3,4) :

* le port désigne **(2,4)**, le natif POSE le caster en **(4,3)** (cast réel) ;
* l'anneau de la tuile NATIVE = `{ennemis: [77]}` et les events d'explosion du natif sont
  **exactement** cet anneau ⇒ **les sélecteurs des batchs 3/4 sont HORS DE CAUSE** ;
* l'anneau de la tuile du PORT = `{ami: [83], ennemis: [77, 79]}` = exactement ce que le port émet ;
* pool du port `[(2,3), (2,4), (4,3), (4,4)]`, utilités `15 / 70 / 49 / 70` — le port prend (2,4) ;
* `aiMovableTiles(side=all, overrideRange=5)` rend **27** tuiles, et **(2,4) comme (4,4) n'y sont
  PAS**. Le pool natif se réduit donc à `[(2,3), (4,3)]`, où (4,3) gagne — ce que le natif fait.

⇒ L'écart est **entièrement** l'étage TUILE, et sa cause est le POOL. C'est `#381-r1`, deuxième
mesure indépendante (la première était un ring saturé), et cette fois avec la **décomposition
complète** : le probe sépare POOL / TRI / SÉLECTEURS et le dit dans son verdict.

**FERMÉ depuis — `case-381-r1`.** La cause n'était pas « le port TRAVERSE les unités » : derrière
l'intersection `CanAddUnit(...)`, le filtre d'occupation est inobservable. C'est le **gate
d'expansion #131** (`BasePathfinder$$NodesInNextLevel` → `IsValidContinuePathTile`) que le nœud DSL
ne posait pas — (2,4) et (4,4) ne pendent que d'un Swamp de `C1_74`. Le nœud porte désormais les
trois étages d'`AnyOrFillMoveableTiles` et, sur cette même géométrie, **désigne (4,3)** — la tuile
où le natif pose le caster.

## 6. `#383-r1` — la face COMBAT n'entrait PAS dans `ABILITY_CLASSES` — **CLOS par #389**

> **CLOS (2026-08-01, `case-389-ramming-speed-combat.md`).** `<DSLTriggers+0x20>` =
> `IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger` (la propriété DSL `OwnerIsAlive`, SANS
> opérande) — nommé par le gabarit de classe, le TYPE du champ (`MatchState`, qui écarte les 21
> candidates allouées avec un sélecteur) et le corps trivial
> `DSLTriggers$$IsRangedPosition = op_LogicalNot(<+0x18>)` qui nomme le jumeau. 1059 est au registre
> avec ses deux données et son `GetDynamicInvalidTargetReason` ; confronté LIVE 5/5 bras.
> La branche VRAIE du `ConditionalAmount` (§7) est désormais confrontée LIVE elle aussi.

Le port de `RammingSpeedAbility$$ExecuteBehaviour` était bloqué sur **un nœud non identifié**, et un
port spéculatif aurait été pire que l'absence. Structure lue :

```
ifMove = If( NOT IsAdjacent(Caster@0x48, Target@0x60, 3),
             MoveUnit(Caster@0x48, GetTileToMoveTo(), opts) )
atk1   = AttackWithAttackDamage(Owner@0x30, Target@0x60, RandomAmount(minDmg 0xc, maxDmg 0xd),
                                GetDamageProfile(), nrOfHits 0x2f, AbilityOrEffect(this.Id), opts, 2)
atk2   = AttackWithAttackDamage(Owner@0x30, Owner@0x30,  <même amount>, <même profil>,
                                nrOfHits_2 0x32, …)
addEff = AddEffect(0x44a = 1098 RammingSpeed_ExtraExplode, AbilityStateReference,
                   Owner@0x30, Owner@0x30, opts)
res    = (ifMove + addEff) + If( <DSLTriggers+0x20>, atk1 + atk2 )
```

**Le verrou** : `<DSLTriggers+0x20>` est alloué par `DSLTriggers$$InitializeShared`
(`new <DAT_183343468>(dsl+0x10 /* matchState */, 0)`) et sa classe n'est nommée nulle part dans la
table. Aucun `get_*` de `DSLTriggers` ne le lit, donc son nom ne s'obtient pas par un accesseur.
Deuxième porteur connu du même champ : `ExemplarOfTheKauyonAbility$$ExecuteBehaviour` (1087) —
**pas portée non plus**, donc aucun nommage disponible par cette voie.

**Les deux données de registre sont LUES, et prêtes à recopier** le jour où le nœud sera nommé :

```
IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$.ctor :
    TargetingOptions..ctor(&opts, isSelfCasting = 0, range = &<TargetingRange statics+0x18>,
                           forceMeleeTarget = 1, rules = 0x4002, 0, 0)
    AActiveAbility..ctor(this, &opts, 0)
```

* surcharge tranchée **par ses xrefs entrantes** : ce n'est ni `…$$.ctor(this, template)` (1811caf90)
  ni `…$$.ctor(this, template, additionalRules)` (1811cb040), dont les listes d'appelants ne
  contiennent PAS `RammingSpeedAbility$$.ctor` ⇒ c'est la surcharge **FLAGS DIRECTS**, le littéral
  EST le masque ;
* `rules = 0x4002` = `TargetMatchesDynamicRule (0x2) | TargetIsEnemy (0x4000)` ;
* `range` = `TargetingRange` statics `+0x18` = `RANGE_FROM_CONFIG` (`useRangeFromConfig = true` →
  `overrideRange = GetNumberConstant(0x16 = range)` = 5) ;
* `forceMeleeTarget = 1` = `RangedBool.False` ;
* `AbilityAttackType` = 3ᵉ argument d'`AActiveAbility..ctor` = **0 = `DirectTargetAttack`**.

⚠ `getDynamicInvalidTargetReason` est passé **nul** au ctor : le gate de ciblage de 1059 est
l'**override virtuel** `RammingSpeedAbility$$GetDynamicInvalidTargetReason`, pas un délégué.

## 7. Ce qui n'est PAS couvert

* ~~**La face COMBAT** (§6) — `1059` reste hors `ABILITY_CLASSES`~~ — **PORTÉE ET CONFRONTÉE
  (#389, `case-389`)**, avec `TARGETING_OPTIONS`, `ABILITY_ATTACK_TYPE` et
  `GetDynamicInvalidTargetReason`.
* ~~**La branche VRAIE du `ConditionalAmount`** (`HasEffect(Owner, 1098)`) n'est exercée
  qu'**OFFLINE**~~ — **CONFRONTÉE LIVE par #389** : le bras léthal de
  `probe_389_ramming_speed_combat_port.py` fait tuer le caster (`orksKillaKan`, trait `Explodes`)
  par son propre contrecoup ; la nova part PENDANT le cast et rend **75 %** du maxPV
  (`explodesDmg` 25 + `extraDmgPct` 50) — port == natif, et `--mutate no-effect` rend 25 % (ROUGE).
* **`TargetsSelector$$SelectUniqueUnits(ctx, 3)`** : ni le `unique` ni le masque `3` (vivante ET
  sans le flag `0x11 NotTargetable`) ne sont modélisés séparément — `_within` filtre déjà les
  mortes, le flag `0x11` n'a aucun substrat côté prédiction. Résidu commun à tous les sets AoE.
* **L'ORDRE de `MovableTilesInRange`** (ids croissants côté port, ordre de visite du BFS côté
  natif) — résidu hérité de `#353-r1`, il ne départage que des utilités STRICTEMENT égales.
* **Un seul niveau d'ability** en live sur les bras verts (8) ; le bras niveau 45 est celui que
  `#381-r1` fait tomber, donc l'axe NIVEAU n'est pas couvert au-delà de l'offline.
