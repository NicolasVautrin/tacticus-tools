# Case #68 (slice-21a) — distance de **push** : 1 hex, PAS 2 (hardcode-mesure tranche)

> Resolution du hardcode-mesure `_PUSH_MAX_DIST` de `displace.py`. La slice-21a avait fige `1`
> par **HYPOTHESE** en laissant ouverte la piste « le natif passe `param_9=2` (+0x84 de
> `DisplaceUnitBehaviour`) = maxCount PROBABLE -> le push pourrait aller 2 hexes ». RE decompile +
> mesure live discriminante : la distance native = **1 hex** ; le `param_9=2` n'est PAS la distance
> de push. Meme patron que #61 (hardcode-mesure a confronter au decompile+live), verdict **inverse** :
> la valeur portee (1) etait deja correcte, seule sa JUSTIFICATION (hypothese) devient sourcee.
> Livre : commentaire RE-source + test discriminant LIVE + doc. Build `gqfc5mff6c`.

## 1. RE — decompile = verite (VAs `gqfc5mff6c`)

### 1.1 Le champ +0x84 = 2 n'est PAS la distance

- `DSLFactory.PushUnit @180df9540` construit le behaviour :
  `DisplaceUnitBehaviour..ctor(this, 1, pusherSel, pushedSel, 0, 0, 1, 0, 2, <MethodInfo>)`.
- `DisplaceUnitBehaviour..ctor @180fc4740` mappe le **9e arg -> `this+0x84`** (`*(this+0x84)=param_9=2`) ;
  le `1` (2e arg) -> `+0x50` = `DisplacementType` (= push).
- `DisplaceUnitBehaviour.Execute @180fc3ff0` lit `*(param_2+0x84)` mais le passe UNIQUEMENT dans la
  couche de **selecteurs DSL** (contexte d'evaluation du selecteur `+0x60`), **pas** a l'operation de
  deplacement. => le `2` ne parametre pas la selection de tuile.

### 1.2 La destination sort d'un ARC ARRIERE distance-1

- `DisplaceUnitOperation.Execute @180e685a0`, **case 1 (push)** :
  `lVar7 = FindTileToPush(param_1, pusher, pushed, 0)` — appele avec un `0` **litteral**, aucune
  distance / aucun champ +0x84 transmis.
- `FindTileToPush @180e695e0` :
  1. `list = interface(param_1+0x30).slot_0x4c(pusher, pushed)` (liste de tuiles candidates) ;
  2. filtre : retire les tuiles ou `slot_0x5f(ctx, pushed, tile)==false` ;
  3. pick : `list.Count==1 -> index 0` ; sinon **random** parmi les `IsEmptyOrSteppable`.
- Le slot d'interface **0x4c** = `GetMinimumTiles180Behind @181064f98` ->
  `GetMinimumTiles180BehindFromTile @1810642a0` : un **arc arriere (180 deg)** de tuiles **TOUTES a
  distance 1**. Cas aligne (source/target sur un axe hex — TOUJOURS vrai en melee, pousseur adjacent)
  -> l'arc **degenere en 1 seule tuile straight-back**.
- **Symetrie confirmatoire** : le pull `FindTileToPull @180e69080` utilise le slot **0xa6** = arc AVANT
  (`GetMinimumTiles180Front @181064fa0`, meme structure distance-1). push=arriere / pull=avant, memes
  mecaniques -> les deux sont des selections **distance-1**.
- La seule source list qui marche >1 hex, `GetTilesBehind @18106a150` (ligne, `maxCount` Nullable ;
  `maxCount` NON fixe -> marche NON bornee par count quand null), sert aux AoE **ligne/cone**
  (`GetTilesBetweenInLine @18106aa50`, `GetTilesInConeShape`), **jamais** au push.

**Conclusion RE : push = 1 hex.** L'hypothese « maxCount=2 -> 2 hexes » est REFUTEE par le decompile.

## 2. Discrimination live — mesure discriminante (distance = 1)

`test_thunderous_assault_push_distance_live` (dans `test_thunderous_assault_push_live.py`) monte un
runner live `templSwordBrother` (ThunderousAssault 1043) vs `spaceBlackmane` (deplacable), place
caster+cible sur **4 tuiles collineaires LIBRES** (C, T, B1, B2) via la geometrie du port, caste LIVE
(moteur natif via `applyAction`), et lit la nouvelle position de la cible. **B2 libre => 1 et 2 sont
DISTINGUABLES** (un maxCount>=2 pousserait a B2).

| # | caster C | cible T | B1 (1 hex) | B2 (2 hex, LIBRE) | cible poussee -> | distance |
|---|----------|---------|-----------|-------------------|------------------|----------|
| 1 | (3,1)    | (3,2)   | (3,3)     | (3,4)             | **(3,3)**        | **1**    |
| 2 | (2,4)    | (3,4)   | (4,3)     | +1 meme dir       | **(4,3)**        | **1**    |
| 3 (test) | (0,0) | (0,1) | (0,2)    | (0,3)             | **(0,2)**        | **1**    |

Deux axes/parites distincts + le test automatise : le natif s'arrete a B1 (1 hex) en **ignorant B2
pourtant libre et atteignable**. Le caster CHARGE ensuite dans la tuile T liberee (mirror
`MoveUnit(caster, TargetTile())` de `ThunderousAssaultAbility.ExecuteBehaviour @1812158b0`). Distance
native = **1**, sans ambiguite.

## 3. Fix

- `engine/runner/operations/displace.py` : `_PUSH_MAX_DIST = 1` **inchange** (valeur correcte), mais le
  commentaire passe de **HYPOTHESE** a **constante SOURCEE** (chaine RE §1 + confirmation live §2, VAs
  citees). La docstring du module retire le « push MULTI-hex slice-21b » (REFUTE).
- `tests/engine/runner/test_thunderous_assault_push_live.py` : **nouveau** test
  `test_thunderous_assault_push_distance_live` = discriminant LIVE 1-vs-2 (garde de regression) +
  docstring du module remise a l'etat « tranche ».

Aucun changement de comportement du moteur (le port poussait deja 1 hex) -> le fix est
**documentaire + garde de test**, pas un correctif de valeur.

## 4. Validation (adversariale)

- **Discriminant LIVE** (§2, test automatise) : B2 libre ignore -> distance native = 1 ; mesure sur 2
  axes/parites. PASS.
- **Zero-regression** (tests CIBLES) : `test_thunderous_assault_push_live` (2/2 : discriminant + offline
  e2e), `test_mortis_round_live` (2 pass + 2 skip pre-existants Eliminator), `test_rad_saturation_live`
  (3/3). Le fix etant commentaire-only cote moteur, ces tests ne pouvaient pas regresser
  fonctionnellement — relances par discipline.
- **Contrefactuel** : le scenario EXIGE B2 libre pour discriminer ; un push contre un mur/occupant a
  1 hex reste borne (0 move + knockback #47, chemin deja porte/teste).

## 5. Residu (slice-21b eventuelle, hors #68)

- **Arc arriere NON-degenere** : pour un pousseur **NON adjacent** (source/target non axis-aligne),
  `GetMinimumTiles180BehindFromTile` rend 2-3 tuiles de l'arc distance-1 et `FindTileToPush`
  **random-pick** parmi les valides -> la DIRECTION peut differer du straight-back du port. **Sans objet**
  pour `PushUnit(caster, target)` **melee** (pousseur toujours adjacent -> arc = 1 tuile straight-back
  deterministe). A porter seulement si un push d'un pousseur non-adjacent (AoE/ranged) apparait. `[opus]`.
- **steppable-crush / fall-damage d'elevation / absorption par allie** au push : residus deja flagges
  dans la docstring de `displace.py` (branches `IsSteppable` / `GetElevationDifference` d'`Execute
  @180e685a0`), inchanges par #68.
