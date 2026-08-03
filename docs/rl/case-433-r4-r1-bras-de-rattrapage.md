# #433-r4-r1 — le bras de rattrapage de `FilterTilesIfCanAttackTargetTileFromSelector$$Select`

**PORTÉ** (nœud DSL `entities/selectors/tiles.py::FilterTilesIfCanAttackTargetTileFrom`), câblé dans
le REPLI de `MV71SniperDroneSquadAttackAbility$$PickTile` (les deux faces), **10 tests offline** dont
la contre-épreuve par mutation (4 mutations, 4 rouges, arbre restauré bit-exact).

**Trois énoncés de l'inventaire #433-r4 sont RÉFUTÉS au décompilé** — et deux d'entre eux réduisent le
gisement d'un facteur 2 à 3.

## 1. RÉFUTATION — « 3 nœuds DSL, 4 abilities » : c'est **1 nœud, 2 abilities**

`DSLSelectors$$AttackTilesForTarget`, `$$CanAddMultiTileUnit` et `$$FilterTilesIfCanAttackTargetTileFrom`
appellent bien **le même corps de `.ctor`** — mais c'est une **déduplication IL2CPP**, pas une classe
commune : chacun alloue un `Il2CppClass*` DIFFÉRENT, et chacun a son propre `Select` :

| nœud DSL | classe allouée | `Select` | appelle `IsAdjacentTo` ? |
|---|---|---|---|
| `$$AttackTilesForTarget` | (DAT distinct) | `AttackTilesForTargetSelector$$Select` → `$$CanGenericUnitAttackTargetFrom` | **NON** (slots `IBattleQuery` `0x60`/`0x81`) |
| `$$CanAddMultiTileUnit` | (DAT distinct) | `CanAddMultiTileUnitTileSelector$$Select` → `TileExtensions$$CanAddUnitFromAbility` | **NON** (slots `0x4f`/`0xf`) |
| `$$FilterTilesIfCanAttackTargetTileFrom` | (DAT distinct) | `FilterTilesIfCanAttackTargetTileFromSelector$$Select` | **OUI** |

Le champ commun n'est que le **schéma d'affectation** du ctor partagé (`f18=arg3, f20=arg4, f28=arg5,
f30=arg6`) — et les trois nœuds y rangent des choses différentes (`AttackTilesForTarget` met la query
en `f20`, `CanAddMultiTileUnit` en `f18`, `FilterTiles…` en `f30`). C'est le piège
`reference_ctor_name_is_not_class_identity`, appliqué à un **corps de ctor**.

**Les consommateurs réels**, clôture MÉCANIQUE (`refcount` 6 de `DSLSelectors$$FilterTilesIfCanAttackTargetTileFrom`
= **2** `UNCONDITIONAL_CALL` + 4 entrées DATA) :

* `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PickTile` (**1076**) —
  branche de **REPLI uniquement** ;
* `IdunBattleLogic.Entities.Abilities.Active.Loki.WallOfMirrorsAbility$$GetPossibleTiles` (**1186**) — ability
  NON portée.

`1016 SendInTheNextWave` et `NovaBoost_Attack` ne sont **PAS** des consommateurs : le commentaire
« `AttackTilesForTarget -> identite offline` » de `runner/abilities/astramilitarum.py` porte sur un
AUTRE sélecteur, et il ne faut pas le « corriger » ici.

## 2. RÉFUTATION — le premier opérande n'est pas une « raison d'invalidité », c'est un **CARDINAL**

Transcription VERBATIM (mirror 1:1 du décompilé) :

```
enemyOf    = this.<+0x18>.SelectUnit(entities, 0);      // vslot 7
targetTile = this.<+0x20>.SelectTile(entities);         // vslot 0xc (SINGULIER)
if (enemyOf == null || targetTile == null) return new List<Tile>();
result = new List<Tile>();
foreach (tile in this.<+0x28>.SelectTiles(entities))    // vslot 0xa
    if (query.<slot 0x7a>(tile, null, enemyOf, false).<ICollection.get_Count> == 0
        || TileExtensions.IsAdjacentTo(tile, targetTile))
        result.Add(tile);
return result;
```

**`IBattleQuery` slot `0x7a` = `BattleQuery$$GetAdjacentUnits(from, friendsOf, enemiesOf, ignoreSteppables)`**,
établi **mécaniquement** et non par ressemblance : le décorateur d'enregistrement
`RecordedSimulationRequestsBattleQuery` ré-appelle la query interne **par le même slot** depuis ses
fermetures, et les trois portent leurs numéros en clair —
`…u003Cu003Ec__DisplayClass149_0$$u003CGetAdjacentUnitsu003Eb__0` → **`0x7a`**,
`…DisplayClass150_0…` → `0x7b`, `…DisplayClass151_0…` → `0x7c`. Les trois surcharges de
`GetAdjacentUnits` occupent donc `0x7a..0x7c`. Corroboration indépendante :
`ExemplarOfTheKauyonAbility$$GetDynamicInvalidTargetReason` appelle le MÊME slot puis
`ICollection.Remove(caster)` — on ne retire pas un caster d'une liste de raisons.

**Sémantique**, une fois les deux opérandes lus : une unité engagée au contact ne peut pas TIRER →
la tuile candidate n'est gardée que si `enemyOf` n'y aurait **aucun ennemi adjacent**, **ou** si elle
est **adjacente à la tuile cible** (une attaque de MÊLÉE redevient possible). Les deux call-sites
passent `(enemyOf = Caster()@DSLSelectors+0x48, target = Target()@+0x60)` — mapping corroboré deux
fois : `DSLSelectors$$InitializeShared` écrit **11 slots** qui correspondent un pour un à la carte
`DSLFactory` déjà citée par le port (`0x148 Owner … 0x198 UnitFeetTiles`) avec un **delta constant de
0x118**, et la paire `CasterTile`/`CasterTiles` y partage un `Il2CppClass*` comme le dit `#433-r3-r1a-r2`.

Filtre d'unités (`BattleQuery$$CountOrGetUnitsOnTiles`, verbatim) : `GetUnit(tile)` (le
`TileContentComponent`, donc **n'importe quel pied** résout en son unité), `ignoreSteppables == false`
→ les steppables **comptent**, `friendsOf == null` → inerte, `IsEnemy(u, enemyOf)`. Seul le CARDINAL
est lu : ni l'ordre ni la déduplication de l'`OrderedSet` ne sont observables.

## 3. RÉFUTATION — le régime d'IDENTITÉ n'est atteignable par **aucun** des deux consommateurs

L'inventaire classait ce consommateur « ATTEINT ». Mesuré ici :

* **`WallOfMirrors`** — `GetPossibleTiles` construit l'anneau à distance **EXACTEMENT `range`** :
  `SurroundingTiles(Target, r) − SurroundingTiles(Target, r−1)`, et le gameconfig donne
  **`range = 2`**. Une candidate est donc à distance 2 de la tuile cible ⇒ `IsAdjacentTo` est
  **toujours faux** : chez ce consommateur, le bras de rattrapage lui-même est **structurellement
  mort** (sauf cible MULTI-HEX, où l'anneau est l'UNION de ceux des pieds et où une tuile à 2 d'un
  pied peut être à 1 de la main tile — non instruit).
* **`MV71` (repli)** — la candidate est la tuile du drone le plus faible, occupée par ce drone ; la
  tuile cible est occupée par la cible. Deux entités distinctes ⇒ jamais la même tuile.

⇒ Ce qui mord, c'est le bras de rattrapage par **ADJACENCE** (distance 1), pas par identité. Le
court-circuit d'identité reste néanmoins porté (`battle_query.are_entities_adjacent`), parce que c'est
le mirror exact de `MovementUtil$$AreTilesAdjacent` et que la garde le verrouille — mais il est
**inerte aux deux call-sites connus**, et c'est dit comme tel.

## 4. Ce qui est porté

`FilterTilesIfCanAttackTargetTileFrom(enemy_of, target, from_tiles)` — nœud DSL, domaine TUILE, dans
`entities/selectors/tiles.py`, re-exporté par `entities/selectors/__init__.py` (donc par la façade
`dsl/nodes.py`). Il n'invente aucune primitive : les deux adjacences sont les **foyers existants**,
et le port ne les confond pas (c'est tout l'objet de `#433-r1`) —

| terme natif | foyer du port |
|---|---|
| `GetAdjacentUnits` → `IterateAdjacentTiles` (liste d'adjacence stockée, jamais la tuile source) | `battle_query.is_adjacent` |
| `TileExtensions$$IsAdjacentTo` → `MovementUtil$$AreTilesAdjacent` (court-circuit d'identité) | `battle_query.are_entities_adjacent` |
| `GetUnit(tile)` par pied, vivants seulement | `dsl.base._occupants_by_tile` |
| `SelectTile` (singulier) | `dsl.base._select_tile` |

**Câblage** — `runner/abilities/loki/mv71.py`, DERNIER étage du repli natif, sur les DEUX faces
(runner `_pick_tile` et prédiction `pick_tile_scene`), par le même helper
`_filter_tiles_if_can_attack_target_tile_from` : aucun fork de prédicat, seule l'hydratation diffère
(ECS vs `Scene`, où le caster est virtuellement sur `parent_pos`, #153). La STRUCTURE émerge de
l'arbre DSL (doctrine #149) ; le collapse impératif ne fournit que le véhicule `FixedTileIds`.

**Ce que le câblage change, observable** : quand la tuile du drone le plus faible a un ennemi du
caster adjacent ET n'est pas adjacente à la cible, `PickTile` rend désormais `null` → cast **NO-OP**.
Le port d'avant rendait la tuile : éviction du drone, spawn, attaque et Markerlight **de trop**.

## 5. Validation

**OFFLINE — `tests/engine/test_433_r4_r1_filter_tiles_can_attack_offline.py`, 10 passed.** Axes :
le bras change l'ensemble (**3 tuiles gardées contre 0** sur un montage où toutes les candidates ont
un ennemi adjacent) ; identité `tile == targetTile` ; l'occupant de la tuile candidate n'est pas son
propre voisin ; ami vs ennemi ; mort ; **pied secondaire** d'une multi-hex ; porte d'élévation sur les
DEUX bras ; sélections vides ; ordre et doublons ; et le **câblage** du repli de `PickTile` dans ses
trois régimes.

**Contre-épreuve par MUTATION** (arbre restauré, sha256 vérifié bit-exact après chaque passe) :

| mutation | résultat |
|---|---|
| bras de rattrapage RETIRÉ | rc 1 — **3 failed** / 6 passed |
| bras en `hexgeo.distance == 1` (port naïf) | rc 1 — 2 failed ; ciblée : `test_identite_…` **rouge** |
| premier bras sur `are_entities_adjacent` (mauvaise primitive) | rc 1 — 1 failed |
| câblage `pick_tile_scene` retiré | rc 1 — `test_le_repli_de_pick_tile_traverse_le_bras` rouge |

**NON CONFRONTÉ LIVE, et la raison est STRUCTURELLE — pas un manque de montage** :

* `MV71` repli — il n'est atteint que si le chemin PRIMAIRE rend une liste VIDE, c'est-à-dire si
  **aucune** tuile libre à distance 1..4 de la cible ne passe `IsFreeTile` (portée du drone
  `tauSmnDroneSniper` = **4**, lue au gameconfig : `Range: 4`). Ce sont jusqu'à **60 tuiles** à
  neutraliser simultanément — hors d'atteinte d'un roster de bataille.
* `WallOfMirrors` (1186) — ability NON portée, et ses seuls porteurs sont `tauNpc5StealthSuit` (npc)
  et `tauSmnStealthSuit` (summon dont **aucun kit du gameconfig ne cite le summoner**). Son gate
  `GetDynamicInvalidTargetReason` (≠ null, cible portant **Markerlight `0x462`**, `GetPossibleTiles()`
  non vide) serait un oracle LIVE à 1 bit via `abilityTargets` — mais il exige d'abord la greffe de
  l'ability sur une unité du pool ET le port de `GetPossibleTiles` (anneau à distance exacte,
  `CanAddUnit`, `FromTrigger(!IsObscured)` — la LoS n'est pas portée). Montage nommé, non joué.

**Régression** — les tests live qui exercent 1076 par son chemin PRIMAIRE (`test_443_savior_protocols_pair_term_live.py`,
`test_443r1_savior_protocols_move_term_live.py`, `test_unit_removed_vector_live.py`) sont rejoués :
le changement est confiné à la branche de repli, qu'aucun d'eux n'atteint.

## 6. Résidus NOMMÉS

* **`#433-r4-r1-r1` — `WallOfMirrorsAbility` (1186) non portée.** Chaîne native lue et transcrite :
  `GetPossibleTiles` = anneau à distance exacte `range=2` autour de `Target`, `CanAddUnit`,
  `FromTrigger(!IsObscured(ActiveTarget@+0x68, Target@+0x60))`, puis CE nœud ;
  `ExecuteBehaviour` = `SortTilesByUtility(…, Caster, 7)` → `First` → `FlyUnit(Caster)` &
  `AddEffect(0x414)` & `RemoveEffect` & `UseNormalAttack(Caster, Target)` & `AddEffect(0x576 = 1398
  WallOfMirrors)` & `RemoveEffect`, le tout sous un `If(<trigger>)`. Masque lu au ctor :
  `TargetingOptions..ctor(&opts, isSelfCasting: 0, &range(statics+0x48..0x58), forceMeleeTarget: 1,
  rules: **0x6004012**, 0, 0)` puis `AActiveAbility..ctor(this, &opts, **2**)`. Porteurs : npc +
  summon sans summoner trouvé → **greffe** (case-92 §5bis) obligatoire.
* **`#433-r4-r1-r2` — le bras de rattrapage est STRUCTURELLEMENT MORT chez `WallOfMirrors`** tant que
  la cible est mono-hex (anneau à distance exacte 2). Le régime multi-hex (anneau = union des rings
  des pieds, `targetTile` = la main tile) le rouvrirait : **non instruit**.
* **`#433-r4-r1-r3` — `UnobscuredTiles` (LoS) toujours non portée** dans le repli de `PickTile` : mon
  étage est le SUIVANT, pas celui-là. Le flag existait déjà dans la docstring de `mv71.py`.
* **`#433-r4-r1-r4` — porte d'élévation inerte côté runner** : `entities_from_state` ne pose pas
  `elev_by_pos`, donc `|dElev| < 2` dégrade en no-op PERMISSIF pour les deux bras. Dégradation
  PARTAGÉE avec tous les autres nœuds d'adjacence du runner (pas un fork local) — mais elle vaut
  d'être fermée en un seul geste, pour tout le substrat.
