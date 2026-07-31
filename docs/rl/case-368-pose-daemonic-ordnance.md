# case-368 — la POSE de `1148 DaemonicOrdnance` (face COMBAT)

Résidu `#359-r4`, ouvert par cette phrase de `case-350r3` : *« sur `C1_15` le natif n'allume que
`{(3,3), (3,4)}` du triangle `{(2,3), (3,3), (3,4)}` […] la seule covariable mesurée est
`walkable = False` »*. Question binaire de la tranche : **le port allume-t-il les MÊMES tuiles que
le natif ?**

Réponse mesurée : **oui sur le régime que le résidu décrivait — le résidu s'expliquait par
l'ÉLÉVATION, déjà portée. Un écart RÉEL subsiste, plus étroit, borné aux tuiles NON MARCHABLES.**

---

## 1. L'artefact natif, lu de bout en bout

`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$ExecuteBehaviour` étage [5] :

    AddEffect( 5 = Fire, AbilityStateReference, source = DSLSelectors@+0x30 (Owner),
               targets = GetTargetAreaTiles(), options ZERO )

`...DaemonicOrdnanceAbility$$GetTargetAreaTiles` (relu, inchangé) :

    dir  = If( IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4) )
    zone = TilesOnSameElevation( Target@+0x60, TilesInTriangleShape(Target@+0x60, dir), maxDiff = 1 )

`IdunBattleLogic.Entities.DSLSelectors$$TilesInTriangleShape` / `$$TilesOnSameElevation` construisent
les deux sélecteurs **sans enveloppe** (pas de `Walkable`, contrairement à
`MacroPlasmaIncineratorAbility`). ⚠ Ghidra mislabelle le ctor de `TilesOnSameElevationSelector` en
`UnitsWithEffectsOfTypeSelector` (ctor gshared foldé) — on lit la STRUCTURE
`(state, compareTile, filterTiles, allowedDifference)`, jamais le nom.

### Les filtres de la chaîne de POSE — étage par étage, exhaustif

| étage natif | ce qu'il filtre | inerte sur une entité-TUILE ? |
|---|---|---|
| `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape` | n'ajoute au HashSet que les `IdunBattle.Entities.StateExtensions$$GetTileAt` **non nuls** ; `GetTileAt` rend null si `IdunBattle.Entities.Components.BoardComponent$$IsPositionInside` est faux (bornes seules) **ou si l'entrée du tableau `BoardComponent+0x18` vaut 0** | — c'est le SEUL point où une tuile peut disparaître pour une raison qui lui est propre |
| `IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select` | `IdunBattle.Entities.TileExtensions$$GetElevationDifference(tile, ancre) <= maxDiff`, et ce corps est `abs(TileComponent+0x18 − TileComponent+0x18)`, **rien d'autre** | non — c'est lui qui ampute |
| `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` | saute la cible si `IdunBattle.Entities.UnitExtensions$$HasFlag(entity, 6 = UnitFlag.Dead)` | **OUI** : `HasFlag` rend false dès que `EntityType` n'est ni `1 = Unit` ni `6 = Machine` (`Tile = 0`) |
| `IdunBattle.Operations.AddEffectOperation$$Execute` | `owner == null` ; `<effet>.EntityIsImmuneToEffect(owner)` ; `IsUnit(owner) && HasFlag(owner, 6)` | **OUI** : `IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` = `HasTrait(entity, 0x19)` → `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent`, et `IdunBattle.Entities.Blueprints$$Tile` ne monte **aucun** `BaseUnitComponent` |
| `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` | rien — `List.Add(effectId)` inconditionnel sur l'`EffectsOwnedComponent` | oui |

**Aucun étage ne lit la marchabilité.** Vérifié aussi par les **xrefs entrantes exhaustives** des
trois surcharges de `IdunBattle.Entities.TileExtensions$$IsWalkable` et de
`IdunBattle.Core.Services.BattleQuery$$IsWalkableTile` : pathfinders, `TileQuery.IterateAdjacentTiles`,
`TargetingQuery`, `TileUtil$$IsTileValidForList`, `BattleQuery$$GetTilesInDiamondShape`, View —
**rien du pipeline d'effets**.

---

## 2. Ce que le résidu décrivait, c'était l'ÉLÉVATION

Le « nominal » de `#359-r4` était la géométrie calculée **à la main** dans
`probe_302_3._burn_stage` (`geo["zone_hot"] = {ancre} ∪ voisines(dir)`), **sans** le filtre
d'élévation. Le port, lui, l'applique.

Balayage offline des 779 dumps (`probe_368 --scan`) : **658** boards portent au moins une ancre où
`|triangle| = 3` et `|zone| = 2`. L'exemple cité par `#359-r4` en fait partie —
`MC1_67`, ancre `(4,1)` : voisines `(4,2)` **élévation 4** et `(5,2)` élévation 2, ancre à 2 →
`(4,2)` sort par `|Δ| = 2 > 1`. Le triangle mesuré sur `C1_15` (`(2,3)` non marchable) était le
**second** régime, décrit au §3.

### Mesure LIVE — accord PARFAIT sur les deux branches du `If`

`probe_368_daemonic_ordnance_pose.py --pose` : le port de la face COMBAT est exécuté sur l'état
chargé **avant** le cast (`load_state`), le natif caste réellement, et on compare les ensembles.

| bras | board (dir) | porteur | tuile amputée | élévations | natif | port |
|---|---|---|---|---|---|---|
| A | `MC1_67` (dir 1) | **MoW `blackForgefiend`** | `(1,3)`, **MARCHABLE** | 2 / **4** / 2 | `{(1,2),(2,2)}` | = natif |
| B | `C1_15` (dir 4) | greffe `deathTyphus` | `(2,0)` | **3** / 1 / 2 | `{(3,0),(3,1)}` | = natif |

Le bras A est le discriminant : la tuile que le natif n'allume pas y est **marchable**. La
marchabilité n'était donc qu'une covariable dans la formulation du résidu.

**Vue ROUGE** (même montage, même état) : `TilesOnSameElevation` privé de son `maxDiff` allume une
tuile de plus — `[(1,2), (1,3), (2,2)]` contre `[(1,2), (2,2)]` côté natif.

---

## 3. Le résidu qui RESTE — et il est plus étroit

Sur une ancre dont les **3** tuiles de la zone passent l'élévation, mais dont l'une est **non
marchable**, le natif n'en embrase que 2 ; le port les embrase toutes.

| bras | board (dir) | porteur | tuile non allumée | terrain | élévations | `isWall` |
|---|---|---|---|---|---|---|
| C | `C1_15` (dir 4) | greffe | `(1,0)` | `Water` | 2 / **1** / 2 (ancre 2) | false |
| E | `C1_15` (dir 4) | greffe | `(0,1)` | `Block` | 2 / **1** / 2 (ancre 2) | false |
| D | `MC1_67` (dir 1) | **MoW** | `(0,8)` | `Block` | 1 / 1 / 1 (**identiques**) | false |

Trois mesures, deux boards, les deux branches du `If`, les deux types de caster, deux terrains
distincts, et le bras D annule l'élévation (les trois tuiles sont à la même). La seule covariable
qui survit est **`walkable = False`**.

### Pourquoi ce n'est PAS porté

1. **Aucun artefact natif ne le dit** (tableau du §1). Poser un `Walkable` dans
   `daemonic_ordnance_target_area_tiles` serait fitter la mesure — et le commentaire du port dit
   déjà, à raison, « AUCUN `Walkable` ici, ne pas recopier le filtre de l'autre MoW ».
2. **La mesure est AMBIGUË à un étage** : `tileMeta` **filtre les effets inactifs**
   (`readEffectsByTile` : `!info.active && !includeInactive → continue`) et n'expose pas le drapeau.
   « La tuile ne porte pas `Fire` » ne distingue donc pas *jamais posé* de *posé puis désactivé*
   (`IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` → `ActiveCondition` de l'effet,
   slot `+0x518` de `BaseEffect`, **non lu**).
3. **Hypothèse restante, non démontrée** : les tuiles non marchables ne seraient pas inscrites dans
   `BoardComponent+0x18`, donc invisibles de `GetTileAt` — alors que le `boardGraph` du port énumère
   les **entités** `Tile` et les voit. Ce serait un écart de **substrat**, pas de logique.
   `IdunBattle.Operations.AddTileOperation$$Execute` paraît pourtant inscrire toutes les tuiles
   construites : la contradiction n'est pas levée.

### Portée de l'écart : INERTE sur les deux faces

Tout consommateur d'un effet de tuile passe par une **unité debout dessus** —
`DaemonicOrdnanceAbility$$GetAllDamageableTargets` = `Enemies(Units(Filter(zone, HasEffect(Tiles(Subject), Fire))))`,
et `TileEffectsUtility` ne note que des tuiles de **déplacement**. Or aucune unité ne peut occuper
une tuile non marchable (`TileExtensions$$CanAddUnit` exige `IsWalkable`). Le sur-marquage du port
ne peut donc produire ni cible de plus, ni dégât, ni préférence de tuile.

### Le capteur qui trancherait (code livré, NON activé — reinject requis)

`ctx.rpc.tileMeta` accepte désormais `includeInactive` et publie alors `active` par effet — strict
pendant de `decisionView`, même raison. Il est **livré mais inerte tant que le bundle n'est pas
réinjecté**. Avec lui, une seule mesure tranche : si `(0,8)` porte un `Fire` **inactif**, la pose a
lieu et le refus est une `ActiveCondition` ; si elle ne porte rien, le refus est au sélecteur
(`GetTileAt`), et c'est alors le substrat `board.id_at` du port qu'il faut corriger — pas 1148.

---

## 4. Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `tests/engine/test_368_daemonic_ordnance_pose_live.py` — A/B | natif == port == zone-après-élévation, sur les DEUX branches du `If`, avec le régime EXERCÉ (`|triangle| = 3`, `|zone| = 2`) |
| idem — vue ROUGE | `maxDiff` neutralisé ⇒ le port allume une tuile de plus que le natif ; sans elle l'accord ne désignerait pas ce filtre |
| idem — C | RÉSIDU BORNÉ : `port \ natif` == **exactement** les tuiles non marchables de la zone, et les marchables de la zone brûlent **toutes** |
| `probe_368_daemonic_ordnance_pose.py` | le montage (`--scan`, `--pose [--only A\|B\|C\|D\|E] [--mutate elev]`) ; il **REFUSE** de mesurer si l'ancre n'est pas du régime demandé, au lieu de rendre un montage dégradé |

## 5. Ce qui n'est PAS couvert

- **La cause native du refus sur tuile non marchable** — non tranchée (§3). Capteur nommé, livré,
  non activé.
- **L'ORDRE des events de 1148** — hors périmètre, cf. `case-350r3`.
- **Les autres poseurs d'effet de tuile** (`MacroPlasmaIncinerator`, `RadBombardment`, …) : ils
  filtrent explicitement (`Walkable`, `− Blocking`), donc le régime ne s'y observe pas — mais la
  question « le natif refuse-t-il tout effet sur une tuile non marchable ? » reste **générale** et
  n'a été mesurée que sur 1148.
