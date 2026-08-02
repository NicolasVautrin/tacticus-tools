# #433-r3-r1 — les nœuds DSL de géométrie lisent l'EMPREINTE, pas la main tile

**Verdict : QUIRK PORTÉ sur CINQ nœuds** (`IsAdjacent`, `IsInRange`, `IsSurrounding`, `IsCharging`,
`MinDistance`), **plus deux découvertes qui n'étaient dans aucun énoncé** — `IsSurrounding` EST
`IsInRange` (même classe native), et `IsInRange` rend **VRAI** sur un sélecteur vide. Confronté LIVE
sur le régime discriminant. **14 sélecteurs restent divergents** : résidus nommés au §6.

## 1. Le périmètre, MESURÉ (et non hérité de la liste)

`probe_433_r3_r1_dsl_footprint_scan.py` — AST, pas grep. `Select-String _pos` rend **978 occurrences
sur 117 fichiers** : il compte des variables locales (`a_pos`, `t_pos`) et des homonymes, et rate ce
qui atteint la main tile sans nommer `_pos`. Le scan résout les imports (relatifs et alias), attribue
chaque site à sa classe englobante, ne retient que les **nœuds DSL** (bases `AbilityTrigger` /
`TargetsSelector` / `AAmountFormula`, fermeture transitive intra-fichier) et rapporte quatre
gisements : appel direct de `_pos`, appel de `_within`, lecture brute de `["pos"]`, et — c'est
l'AST **naïf** qui les ratait — les helpers **module-level** (`triggers.py::_units_on` collapse pour
le compte de `HasUnit` et d'`AreEnemies`).

**Compte : 24 nœuds** (361 fichiers balayés, 38 sites). La fiche #433-r3 §7 en annonçait **4**.
Les 4 sont dedans ; **20 étaient hors liste**, et l'un d'eux (`MinDistance`) portait une docstring
qui affirmait explicitement le contraire de ce que dit le décompilé.

## 2. Ce que le natif lit — les cinq nœuds tranchés

Le pivot est **`IdunBattle.DSL.TargetsSelector$$SelectTiles`**, et il n'a pas d'équivalent
« main tile » : son corps est `Select(entities)` puis, si le sélecteur n'est pas déjà un sélecteur de
tuiles, `foreach entity: foreach tile in EntityExtensions.IterateTiles(entity, state) → out.Add(tile)`.
C'est l'**empreinte complète**, aplatie en une liste. Le singulier `$$SelectTile`, lui, rend
`GetMainTile(entity)` — les deux ne se déduisent pas l'un de l'autre, ils se lisent.

| nœud | fonction native atteinte | ce qu'elle lit |
|---|---|---|
| `IsAdjacent` | `IsAdjacentAbilityTrigger$$ShouldTrigger` → `BattleQuery$$AreEntitiesAdjacent(e1, e2)` | `AreTilesAdjacent(GetTiles(e1), GetTiles(e2))` — **empreintes** |
| `IsInRange` | `IsInRangeAbilityTrigger$$ShouldTrigger` | `GetMinDistance(SelectTiles(a), SelectTiles(b)) <= range` — **empreintes** |
| `IsSurrounding` | *la même classe qu'`IsInRange`* (§3) | idem |
| `IsCharging` | `IsChargingTrigger$$ShouldTrigger` → `BattleQuery$$IsCharging` | `AreEntitiesAdjacent(caster, target) && ChargedUnitIds(caster).Contains(target.Id)` — **empreintes** |
| `MinDistance` | `MinDistanceFormula$$Calculate` | MIN sur `SelectTiles(a) × SelectTiles(b)` — **empreintes** |

La surcharge LISTE `MovementUtil$$AreTilesAdjacent(IList, IList)` est un **OU** sur les paires et rend
**faux** sur une liste vide (l'énumération s'épuise) ; la scalaire reste
`(|dElev| < 2) & (t1 == t2 || IsNeighbour(t1, t2))`.

### La faute que `MinDistance` rendait facile

Sa docstring concluait : « le natif lit UNE position par ENTITE (`GetComponent<PositionComponent>`
puis `Distance`), donc la MainTile — PAS l'empreinte ». Le `GetComponent<PositionComponent>` est bien
là, mais il s'applique à l'élément **énuméré**, et cet élément est une **TUILE** rendue par le slot
`SelectTiles`. La lecture s'arrêtait un cran trop tôt.

## 3. `IsSurrounding` n'est pas un nœud frère — c'est le MÊME

`IdunBattleLogic.Entities.DSLTriggers$$IsSurrounding` et `$$IsInRange` allouent le **même pointeur de
classe** et appellent le **même `.ctor`**, arguments dans le **même ordre** (`query`, `selector1`,
`selector2`, `range`). Il n'existe aucun symbole `IsSurroundingAbilityTrigger` dans le binaire. Les
deux factories ne diffèrent que par leur nom.

L'ancienne docstring du port disait « sens DÉDUIT de l'usage + i2 » : la déduction tombait juste, la
voilà **lue**. Le port fait désormais hériter `IsSurrounding` d'`IsInRange` — aucun corps propre,
donc aucune divergence possible entre les deux.

⚠ Ghidra mislabel le `.ctor` partagé en `IdunBattle.Entities.Triggers.IsUnitOnTileEffectTrigger$$.ctor`
(corps dédupliqué à 4 champs) : c'est le pointeur de classe qui tranche, jamais le nom.

## 4. `IsInRange` rend VRAI sur le vide — le seul écart qui mord sans multi-hex

`BattleQuery$$GetMinDistance` seed à `int.MaxValue` et, si **aucune paire** n'a été évaluée, rend
**`-1`** (`if (best == int.MaxValue) best = -1`). Le trigger conclut par `GetMinDistance(...) <= range`,
donc `-1 <= range` = **VRAI**. Le port rendait **FAUX** (un `any` sur un produit vide).

Ce n'est pas le sentinel de `MovementQuery$$GetDistance`, qui rend `int.MaxValue` dans le même cas —
et ce n'est pas non plus celui de `MinDistanceFormula`, qui rend lui aussi `int.MaxValue`. **Trois
fonctions, deux sentinels** : `services/movement_query.py::get_min_distance` les sépare explicitement
et délègue la double boucle à `get_distance` (aucune géométrie dupliquée).

⚠ Les trois autres écarts exigent une unité multi-hex pour être observables. Celui-ci **suffit d'un
sélecteur qui ne rend rien**.

## 5. Le port — UN foyer, pas un cinquième mirror

* **`dsl/base.py::_feet(u)`** — mirror `EntityExtensions$$GetTiles` côté DSL. Lit `unit["feet"]`
  (posé par `runner/.../context.py::_unit_dict` depuis `get_unit_feet`, #R30/#91) ; **repli
  `[_pos(u)]` documenté** quand le dict n'en porte pas (face DÉCISION, contexte de test) — exact
  pour toute unité mono-tuile, dégradation nommée au-delà. Le pattern existait déjà **copié deux
  fois** (`CanAddUnit`, `ThreeTileUnitSpawnShape`) : les deux y passent maintenant, sans changement
  de comportement.
* **`services/battle_query.py::are_entities_adjacent(feet_a, feet_b, board)`** — mirror de la
  surcharge ENTITE/ENTITE. Avec board, il **DÉLÈGUE** à
  `runner/abilities/targeting.py::are_entities_adjacent` (le foyer #R30) : le verdict de ciblage et
  le verdict DSL sortent littéralement de la même fonction. Sans board, la même double boucle
  retombe sur `are_tiles_adjacent(a, b, None)`. **Une seule boucle sur les empreintes dans tout le
  port.**
* `IsCharging` recevait ici sa **troisième** correction d'un coup : il écrivait
  `hexgeo.distance(pa, pb) != 1` — ni empreinte, ni porte d'élévation, ni court-circuit d'identité.
  La correction #433-r1 n'avait jamais atteint ce nœud.

**Rayon de souffle, mesuré** (`--step readers`, AST) : **10 lecteurs EXÉCUTABLES**, contre ~110
mentions textuelles du même nom. `IsAdjacent` 6 (VigilanceEternal, RammingSpeed ×2, SkyStrike,
TheBetrayer, HarlequinsPanoply), `IsInRange` 1 (Incursion), `IsSurrounding` 1 (HeroicFusillade),
`IsCharging` 1 (TacticalPrecision), `MinDistance` 1 (`IsInUnitAura` → CursedPlagueBell).

## 6. Ce qui a été MESURÉ

### LIVE — `test_433_r3_r1_dsl_footprint_live.py`, 4/4

Porteur multi-hex : `ultraDreadnought` (MoW du pool) → `DutyEternal` (1158) → `ultraSmnDreadnought`
sur **3 tuiles**. Consommateur observable : `custoKyrus` (pool) → `VigilanceEternal` (1202), dont
l'étage MOVE est `If(Not(IsAdjacent(Caster, Target)), MoveUnit(Caster, dest))` — le verdict du nœud
est donc *le déplacement du caster*.

| cran | mesure |
|---|---|
| régime STRICTEMENT discriminant | cible à 3 pieds ; attaquant à **d=1** d'un pied et **d≥2** de `feet[0]` |
| port | `IsAdjacent = True` |
| contre-épreuve (collapse main tile rejoué) | `IsAdjacent = False` — **la correction MORD** |
| **natif** | le caster **NE BOUGE PAS** → il a jugé adjacent **par un pied non-ancre** |

⚠ **Piège de harnais, mesuré** : le premier jeu a rendu `ok: true, mutated: false,
actionConsumed: false` avec pourtant `casterReason = NoBrokenTargetingRule` — l'attaquant avait
dépensé son activation pour rejoindre le poste d'observation. Le filtre STATIQUE de ciblage ne voit
pas l'activation. La gate est **`decisionView.toActivate`**, et sa signature de refus est
**identique** au « le natif a jugé adjacent, donc n'a rien déplacé » qu'on veut mesurer.

### OFFLINE — `test_433_r3_r1_dsl_footprint_offline.py`, 18/18

Un axe par nœud, **chacun avec sa contre-épreuve** (le collapse d'avant, rejoué par monkeypatch,
doit inverser le verdict) : empreinte lue sur les 5 nœuds, quantificateur universel d'`IsAdjacent`
non relâché, sentinel `-1` de `GetMinDistance` vs `int.MaxValue` de `MinDistanceFormula`,
court-circuit d'identité rendu à `IsCharging`, identité de classe `IsSurrounding`/`IsInRange`, et le
repli documenté de `_feet`. Ce fichier rejoint l'entrée `pytest_adjacency` de `scripts/ratchets.ps1`
(même gisement, offline pur).

### Non-régression

Rejoués verts : `test_433_r3_isadjacent_node_offline` (15), `test_433_r1_identity_shortcircuit_offline`,
`test_multihex_dutyeternal_live` (20), `test_targeting_adjacency_rules_live` (22),
`test_vigilance_eternal_live` (6), `test_sky_strike_live` (6), `test_harlequins_panoply_live` (10),
`test_ischarging_extra_damage_live` (7), `test_ischarging_saga_hits_live` (7),
`test_cursed_plague_bell_attack_live` (7), `test_contagions_aura_range_live` (3),
`test_thebetrayer_rage_duration_live`, les quatre fichiers RammingSpeed.

⚠ **Trois rouges de `test_multihex_substrate.py` PRÉEXISTENT** (`IndexError` sur
`board.neighbours_native(...)[0]`, board de test sans voisinage) : contre-épreuve faite en
restaurant `engine/` à `HEAD~1` — mêmes trois échecs. Rouge de `master`, hors de cette tranche.

## 7. Résidus NOMMÉS

* **`#433-r3-r1a` — 14 SÉLECTEURS divergent encore.** Classement établi par RE déléguée (citations
  verbatim, recoupé par lecture directe de `CasterTileSelector$$Select` — le fallback
  `GetTiles(caster, state)` y est bien présent). Par gravité :
  1. **`Units` (occupation) et `HasUnit`/`_units_on`** — `UnitsOnTilesSelector$$Select` résout
     l'occupant par `TargetsSelector$$SelectUnit` → `UnitExtensions$$GetUnit`, qui lit le
     `TileContentComponent` (**n'importe quel pied**) et re-résout même un PIED en son unité. Le port
     indexe par `_pos(u)` : une tuile sous un pied secondaire est vue VIDE. **C'est le foyer** — toute
     la famille `Surrounding*`/`Adjacent*` passe par `Units(...)`.
  2. **`AdjacentUnits` / `AdjacentEnemies` / `AdjacentFriends` / `SurroundingUnits`** — le natif
     unionne le voisinage de **tous les pieds** du centre ; le port part d'une seule tuile.
  3. **`SurroundingTiles` / `SurroundingEnemies` / `SurroundingFriends`** — même cause sur le disque.
     ⚠ **Piège en corrigeant** : l'exclusion du centre soustrait `Tiles(origin)` = la **main tile
     SEULE**, donc les pieds secondaires de l'origine RESTENT dans le résultat. Un fix qui exclurait
     toute l'empreinte introduirait une seconde erreur.
  4. **`UnitsOnTilesWithEffect`** — vrai dès qu'**UNE** tuile de l'unité porte l'effet.
  5. **`CasterTile` / `OwnerTile` / `TargetTile`** — collapses de port ; impact réel seulement quand
     le caster/owner/cible est multi-hex et sert d'ancre géométrique.
  6. **`Unobscured`** — côté cible : le natif exige que **toutes** les tuiles soient obscurcies.
  7. **`CanAddUnit`** — la source n'est pas ouverte par `SelectTiles` ; inobservable tant que tous
     les call-sites passent déjà un sélecteur de tuiles (c'est le cas des call-sites portés).

  D'accord avec le natif : `ThreeTileUnitSpawnShape` (ancre = `SelectTile`), `MovableTilesInRange`
  (départ = `GetMainTile`), `Tiles` (`UnitsMainTilesSelector$$Select`).
* **`#433-r3-r1b` — quantificateur d'`IsCharging`.** Le natif prend **UNE** unité de chaque côté
  (`SelectUnit(entities, 3)` / `SelectUnit(entities, 0)`, un `FirstOrDefault` filtré par
  `UnitExtensions$$MatchesUnitSelectionType`) et fait **un seul** appel à `IsCharging` ; le port
  boucle (`any`). Identique sur des singletons — tous les call-sites lus sont `Caster`/`Target`. Le
  porter exige d'abord le filtre `UnitSelectionType`, qui est `#433-r3-r2`.
* **`#433-r3-r1c` — l'empreinte n'existe pas côté DÉCISION.** Seuls les dicts du runner portent
  `feet` ; la scène de playbook/prédiction n'en construit pas. Les nœuds y dégradent donc en main
  tile, silencieusement. Combler demande de porter l'empreinte jusqu'à `Scene`.
* **`#433-r3-r1d` — namespace `DSLSelectors`.** Les docstrings du port citent
  `IdunBattleLogic.Entities.DSLFactory$$<X>` pour les SÉLECTEURS ; sur `rnca9r7q6c` le symbole est
  `IdunBattleLogic.Entities.DSLSelectors$$<X>`. Le grep code ↔ table est cassé sur ce lot. Transverse,
  non traité ici.
* **`#433-r3-r1e` — trois rouges préexistants** dans `test_multihex_substrate.py` (§6).

Résidus hérités et toujours ouverts : `#433-r3-r2` (`UnitSelectionType` non consommé),
`#433-r3-r3` (numérotation de slots datée dans `runner/abilities/targeting.py` — re-mesurée ici :
`AreEntitiesAdjacent` occupe bien `0x60/0x61/0x62`, `GetMinDistance` est à `0x6f`).
