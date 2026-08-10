# case-589-r1-r1-r2-r1-r8 — l'accord de `--geo-only` était une COMPENSATION, et le vrai bug est une unité SANS SANTÉ

`#589-r1-r1-r2-r1-r8`. Deux mesures du dépôt se contredisaient. Elles avaient **toutes les deux
raison sur leur objet** — c'est l'**attribution** qui était fausse des deux côtés.

## 1. La question binaire, et sa réponse mesurée

> « Que compte RÉELLEMENT `AmuletOfTheVoidwyrm_CritDamageReductionEffect$$
> GetAdjacentFriendlySummonsAndDecoysCount` sur le montage `--geo-only` de `C3_14` ? »

**Il compte `genesSmnDecoy` (u88), qui était là depuis le déploiement — jamais le compagnon en
`(5,3)`.** Et le port ne le comptait pas, pour une raison qui n'a rien à voir avec l'adjacence.

| | S0 tous LOIN | S1 compagnon en `(5,3)` | S2 compagnon sur un voisin STOCKÉ | S3 retour LOIN |
|---|---|---|---|---|
| `actif_natif` | `False` | **`False`** | `True` | `False` |
| dans `AdjacentTiles(Owner)` | `False` | `False` | `True` | `False` |

Compteur natif **lu du DÉGÂT** (modèles entiers 0/1/2/3, RNG neutralisé, la substitution est
vérifiée non-inerte) :

| régime | natif | port AVANT | port APRÈS |
|---|---|---|---|
| 1 compagnon sur un voisin STOCKÉ | **1** | 1 | 1 |
| intrus seul, compagnons LOIN | **1** | **0** | 1 |
| intrus + compagnon en `(5,3)` | **1** | **0** | 1 |

La troisième ligne est celle qui clôt : ajouter le compagnon hex-1 hors liste stockée **n'ajoute
rien** (1 → 1). S'il comptait, on lirait 2.

## 2. Ce que chaque mesure antérieure avait vraiment établi

* **`#589-r1-r1-r2-r1-r4` a raison** : `adjacentTilesNative` régime `selector` sur `(5,4)` ne rend
  pas `(5,3)`, et c'est **conforme au décompilé** — aucun chemin ne peut compter une unité hors de
  la liste stockée (§3).
* **`case-589-r1-r1-r2-r1` §6 est RÉFUTÉE.** Son « le natif compte ce voisin » était une
  **INFÉRENCE depuis l'activité de l'effet**, dans une configuration où l'activité venait
  d'ailleurs. Son bras `--geo-only` ne vérifiait la position que des **deux compagnons** ; il n'a
  jamais fait l'inventaire des porteurs de trait.
* **`#589-r1-r1-r2-r1-r7` a raison sur le CONSTAT** (« le port ne compte pas un voisin que le
  natif compte ») et **faux sur l'ACCUSÉ** : ce n'est pas le compagnon en `(5,3)`, c'est `u88`.
* **L'accord de `case-589` §1 sur la ligne `C3_14` était une COMPENSATION** : le port comptait 1
  par géométrie, le natif comptait 1 par `u88`. Deux causes différentes, le même 1, donc le même
  dégât — `[2713, 2198, 2962, 2787]`, valeur re-mesurée à l'identique ici.

## 3. La chaîne native, relue de bout en bout — elle ne laisse aucune porte

    ...AmuletOfTheVoidwyrm_CritDamageReductionEffect$$GetAdjacentFriendlySummonsAndDecoysCount
      -> IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(Owner, unique: 1, selectionType: 3)
         = Friends( Owner, Units(AdjacentTiles(Owner), 1, 3) op_Subtraction Owner, 3 )
      -> IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select
         = <tilesSelector>.<ITargetsSelector slot 4 = SelectUniqueUnits>(entities, selectionType)
      -> IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits
         = foreach e in <vtable Select>(entities) : SelectUnit(e, selectionType)
      -> IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select
         = foreach t in origin.<slot 10 = SelectTiles>(entities) :
             foreach a in battleQuery.<IBattleQuery slot 80 = IterateAdjacentTiles>(t, 0, 1, 1) :
               if (!tiles.Contains(a)) set.Add(a)
      -> IdunBattle.Core.Services.BattleQuery.u003CIterateAdjacentTilesu003Ed__95$$MoveNext
         = foreach t in EntityExtensions$$IterateTiles(from) :
             foreach n in tileQuery.IterateAdjacentTiles(t, oes, owt, at)
      -> IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext
         = foreach id in tile.<+0x30>.<+0x10>       // une LISTE STOCKÉE, aucune géométrie

Les slots **4** (`SelectUniqueUnits`), **10** (`SelectTiles`) et **80** (`IterateAdjacentTiles`)
sont **LUS** dans `data/symbols/<build>/metadata/interface_slots.tsv`, pas déduits d'un nom.

Deux choses n'avaient jamais été lues et changent la carte :

* `UnitsOnTilesSelector$$Select` n'appelle **pas** `Select` sur son enfant, mais le **slot 3/4**
  (`SelectAllUnits`/`SelectUniqueUnits`) selon son champ `unique` @+0x20 ;
* la surcharge d'`AdjacentFriends` employée est bien `(this, unit, unique, selectionType)`
  (`180eac2a0`), **et non** `(this, unit, unitTile, unique)` — le compteur n'est pas dans les
  xrefs de la seconde.

`MatchesUnitSelectionType(unit, 3, state)` = `IsAlive(unit, state) && !HasFlag(unit, 0x11)`.

## 4. LE BUG — `HealthComponent$$IsAlive` a TROIS branches, le port n'en portait qu'UNE

`IdunBattle.Entities.Components.HealthComponent$$IsAlive` :

    if (RemainingValue@+0x18 >= 1)          return true;    // PV courants > 0 -> VIVANT
    if (get_CurrentMaximumValue() > 0)      return false;   // PV <= 0 mais un MAX -> MORT
    if (<+0x1c> is Nullable<int> HasValue)  return Value != -1;
    return true;                                            // PV <= 0 ET max <= 0 -> VIVANT

Le champ `+0x1c` **EST** `HealthComponent.minimal_health` côté port (le plancher du HP-floor) : le
mirror est donc écrivable **exactement**, pas par approximation.

**Mesure** : `genesSmnDecoy` porte `combatSnapshot.stats.health = 0` **et** `healthMax = 0`, avec
`decisionView.alive = true`. C'est une unité **sans santé**, pas un cadavre — et la 3ᵉ branche
existe pour elle. Le port la déclarait morte :

* `engine/dsl/base.py::_is_alive` = `bool(alive) and (hp or 0) > 0` ⇒ `_within` la retirait de
  **tout** sélecteur d'occupation (`_within_ids = [83]`, `adjacent_friends_ids = []`) ;
* `engine/runner/components.py::unit_is_alive` portait `hp >= 1` seul, et sa docstring déclarait la
  branche « non exercée (une unité à plancher de PV a hp>=1) » — **c'est cette phrase qui est
  fausse**.

La dégradation était **silencieuse** : aucune erreur, aucun événement, juste un compteur à 0.

## 5. Le correctif

* `unit_is_alive` — mirror des quatre branches, `minimal_health` compris.
* `_is_alive` (DSL) — même mirror, sur le dict.
* `_unit_dict` publie `hpMax` (et `_LIVE_KEYS` le re-lit : le maximum **mute**, cf. les bumps de
  `healthMax`). Sans cette clé, `_is_alive` ne peut pas distinguer un cadavre d'une unité sans
  santé, et le mirror serait **inerte sans qu'aucune assertion ne rougisse**.

**DEUX dégradations NOMMÉES, toutes deux conservatrices** (elles gardent le verdict d'avant) :
`hp` non capté ⇒ vivant ; **maximum** non capté avec `hp <= 0` ⇒ **mort**. La seconde est ce qui
empêche l'entité-TUILE de `_tile_entity` (`hp: None`, aucun `hpMax`) d'entrer dans les sélecteurs
d'occupation.

## 6. Ce que le montage a coûté, et qui resservira

* **Le témoin non nul a mordu au premier essai** : le probe REFUSE de conclure si l'effet est actif
  alors que tous les porteurs de trait sont à hex ≥ 4. C'est ce refus — pas une assertion finale —
  qui a nommé `u88`.
* **L'inventaire des porteurs se prend côté NATIF** (`combatSnapshot.units[].traits`, #233) et sa
  clé d'unité est **`entityId`**, pas `id` : la lire de travers rend un inventaire d'anonymes.
* **UN RUNNER PAR FRAPPE.** Une seconde `applyAction ability` sur le même runner revient
  `ok: true, mutated: false, changes: []`.
* **On DÉPLACE les intrus** (les deux camps sont pilotables), on ne subit pas la géométrie de
  spawn.
* La substitution du compteur porte sur **DEUX** bindings, et ils ne se valent pas :
  `components.adjacent_friendly_summons_and_decoys_count` (résolu en global du module par
  `UnitEffectStateView`, il gouverne `is_active`) **et**
  `damage.adjacent_friendly_summons_and_decoys_count` (liaison `from … import` **figée** au
  chargement — patcher le module d'origine ne mord pas dessus).

## 7. Les gardes

* `scripts/python/tests/engine/runner/test_589r1r1r2r1r8_unite_sans_sante_offline.py` — **18
  passed**. Les quatre branches de `HealthComponent$$IsAlive`, les deux dégradations nommées, la
  publication de `hpMax`, la consommation par `AdjacentFriends` (avec le témoin **CADAVRE** au même
  endroit : sans lui, un `_is_alive` rendu inconditionnellement vrai passerait), et un cran
  d'anti-vacuité sur `_within`.
* `scripts/python/probe_589r1r1r2r1r8_compteur_natif.py` — la mesure : inventaire natif, activité
  différentielle S0…S3, valeur du compteur par le dégât, reproduction du montage de `case-589` §6.

## 8. Reproduction

    python probe_589r1r1r2r1r8_compteur_natif.py
    python probe_589r1r1r2r1r8_compteur_natif.py --bras repro
    python -m pytest tests/engine/runner/test_589r1r1r2r1r8_unite_sans_sante_offline.py

## 9. Ce qui n'est PAS couvert

* **Le plancher `+0x1c` n'est pas dans le dict DSL** : la branche `Value != -1` n'est portée que
  côté ENTITÉ (`unit_is_alive`). Elle ne mord que sur une unité à `hp <= 0`, `max <= 0` **et**
  plancher posé — régime non rencontré.
* **Un seul porteur de « unité sans santé » a été joué** (`genesSmnDecoy`). Le recensement des
  autres unités à `healthMax == 0` du parc n'est pas fait : il demande un balayage live, le
  gameconfig ne portant pas cette grandeur sous une forme directement interrogeable.
* **Le rayon de `unit_is_alive` déborde l'adjacence** : il alimente `unit_extensions_is_alive`,
  donc les gates de message et de cast. Les tests joués (§ validation de la PR) ne couvrent pas
  toutes ses branches d'appel.
* **`--geo-only` reste un bras à revoir** : `_stage_geo` ne fige toujours que les deux compagnons.
  Tant qu'il ne fait pas l'inventaire des porteurs de trait, il peut re-mesurer autre chose que ce
  qu'il annonce. Résidu à ouvrir si le bras est réutilisé.
