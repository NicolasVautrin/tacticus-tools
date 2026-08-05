# #462-r4b-r1-r1-r1-r1-b-r1 — le 3ᵉ argument d'`IsAdjacent` est un `UnitSelectionType`, pas un rayon

**Livré le 2026-08-05.** Question binaire posée par `case-462-r4b-r1-r1-r1-r1-retrait-bond.md` §8.7,
laissée ouverte faute de mesure : `IsAdjacent(a, b, 2)` — rayon, ou `selectionType` ?
**Réponse : `selectionType`. Trois sites du port étaient permissifs d'un hex.**

## 1. L'identité du nœud — un seul, pas deux

La tranche précédente soupçonnait deux nœuds distincts (« un filtre `DSLFactory` d'un côté, ce
trigger de l'autre »). **Il n'y en a qu'un.** Les trois sites appellent la même factory avec le même
littéral, lu VERBATIM sur `rnca9r7q6c` :

| module du port | symbole natif porteur du call |
|---|---|
| `runner/operations/triggers/loki/narthecium.py` | `IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter` |
| `runner/operations/triggers/loki/tainted_narthecium.py` | `IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter` |
| `runner/operations/behaviour.py` (BattleFatigue) | `IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger` |

tous trois : `IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(this, sel@+0x30, sel@+0x60, 0x2)`.

## 2. Ce que le champ fait, lu

```
// DSLTriggers$$IsAdjacent(this, selector1, selector2, selectionType)
query = this[+0x10][+0x28];
return new IsAdjacentAbilityTrigger(selector1, selector2, (int)selectionType, query);

// IsAdjacentAbilityTrigger$$.ctor
this[+0x20]=selector1 ; this[+0x28]=selector2 ; *(int*)(this+0x18)=(int)selectionType ; this[+0x10]=query

// IsAdjacentAbilityTrigger$$ShouldTrigger
A = this[+0x20].Select(entities, this[+0x18]);      // slot 3 -- LE SEUL LECTEUR de +0x18
B = this[+0x28].Select(entities, this[+0x18]);      // slot 3 -- idem
foreach (x in A) foreach (y in B)
    if (!this[+0x10].AreEntitiesAdjacent(x, y)) return false;   // slot 0x60 -- AUCUN rayon
return true;
```

Le champ `+0x18` ne descend **jamais** dans le prédicat de distance. Recoupement indépendant : la
classe sœur `IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger` appelle le **même
slot `0x60` sur le même `query`** (champ `+0x28` du même conteneur, cf.
`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacentTiles`) avec deux TUILES — et
`IdunBattle.Core.Services.MovementQuery$$IsAdjacent(unitTile1, unitTile2)` prend deux tuiles, sans
rayon.

**L'enum, lu** (`data/symbols/rnca9r7q6c/frida/enums.tsv`) :
`IdunBattle.Entities.Enum.UnitSelectionType = 0=Any, 1=OnlyAlive, 2=OnlyTargetable, 3=OnlyAliveAndTargetable`,
mirroré par `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`
(`1 -> IsAlive`, `2 -> !HasFlag(0x11)`, `3 -> les deux`, défaut -> vrai). Et
`IdunBattleLogic.Entities.DSLSelectors$$GetDefaultUnitSelectionType(onlyAlive)` vaut `2 + onlyAlive`
— **`2` est littéralement le défaut quand on n'exige pas la vie**, ce qu'un filtre `OnPreDeath` doit
prendre puisque sa cible vient de mourir. Le lire comme un rayon était doublement faux.

## 3. La confrontation LIVE — le natif refuse déjà à distance 2

`probe_462_r4b_r1_r1_r1_r1_b_r1_isadjacent_selection_type.py --step live`, board `MC1_67`, porteur
`ultraApothecary` (passif `Narthecium`, chance 100) + victime `tauAunShi` dans le camp **adverse**,
deux `worldKharn` dans le nôtre. Seule la tuile du porteur change entre les bras.

| bras | dernier coup (fatal : `hp_avant 5996 <= dmg 9994`) | issue |
|---|---|---|
| dist 1 — CONTRÔLE | `5996 -> 5983`, `isDead=False` | **REVIVE** |
| dist 2 — DISCRIMINANT | `5996 -> 0`, `isDead=True` | **TUÉE** |

`5983` = `min(GetReviveHP, maxPV)` posé par le revive.

**Quatre obstacles mesurés**, tous nommés dans le probe :
* `applyAction{"kind":"attack"}` n'existe pas → l'attaque normale est une **ability concrète
  per-unité** (69 ici), lue dans `decisionView` ;
* `ultraEliminatorSgt` (sniper) posé **au contact** ne voit pas la victime dans ses cibles — ni
  `fromHere`, ni le superset `targets` : sa portée a un **plancher** → tueur mêlée ;
* `bloodIntercessor` (la victime des tests offline) porte **`Flying`** : invisible des listes de
  cibles du tueur au contact ;
* `astraCreed` porte **`SwornProtector`** : au coup il se **déplace** et fait apparaître
  `astraSmnKell` qui encaisse → `hpDelta = 0` et géométrie détruite.

⚠ **Le critère de lecture était lui aussi faux, et c'est la leçon transférable** : le revive pose
`min(GetReviveHP, maxPV)`, qui peut être **inférieur** au reliquat d'avant le coup (5983 < 5996). Un
critère « les PV ont remonté » classe donc un revive RÉEL en « non-fatal » — il l'a fait. Le verdict
établit désormais la **fatalité du coup AVANT** d'en lire l'issue, avec le dégât calibré.

## 4. Le correctif

Les trois sites passent par le mirror `engine/entities/triggers.py::IsAdjacent`, correct depuis
`#433-r3` (quantificateur universel, empreintes complètes, porte d'élévation, court-circuit
d'identité), avec `selection_type = 2` gardé **inerte** comme le veut ce mirror (le port ne consomme
pas encore `UnitSelectionType` côté sélecteur — résidu **`#433-r3-r2`**, inchangé).

## 5. La garde et sa contre-épreuve

`probe_462_r4b_r1_r1_r1_r1_b_r1_isadjacent_selection_type.py` — **aucun runner** sur les trois
premiers pas :

* `--step re` : re-dérive la chaîne et l'enum depuis `data/symbols` (un build suffit ; le churn de
  nommage sur un build ancien ne réfute rien) ;
* `--step scan` : filet **statique**, périmètre dérivé (39 fichiers de `engine/**` citant
  `IsAdjacent`) ;
* `--step guard` : garde **comportementale**, les trois porteurs à dist 1 (contrôle, non vacu) vs
  dist 2 ;
* `--step live` : la confrontation ci-dessus.

**Contre-épreuve mesurée** (code restauré à l'état d'avant) : `guard` rouge **3/3**, `scan` rouge
**2/3**. Le troisième échappe au filet statique parce que `BattleFatigueAbility.matches` seuillait en
**deux lignes** (`d = _hex_dist(...)` puis `return d <= SEUIL`) — limite nommée dans la docstring du
pas : le filet repère un site NEUF, la garde comportementale est ce qui mord.

**Tests rendus discriminants.** Les deux `test_adjacency_range_2` ne jouaient que `dist = 3`, où
`distance <= 2` et `adjacence stricte` rendent la **même** réponse : régime dégénéré, qui ne prouvait
rien du 3ᵉ argument. Ils deviennent `test_adjacency_is_strict[2,3]`, et leur `_place` vise la
**distance hex** au lieu du nombre de pas de graphe (un BFS arrêté au 2ᵉ pas peut atterrir à distance
hex 1 — le bras aurait été vacu). Contre-épreuve : `[2]` rouge sur l'ancien code, `[3]` vert.

## 6. Non couvert

* **`TaintedNarthecium` et `BattleFatigue` ne sont pas confrontés LIVE** — même nœud, même littéral,
  décompilés relus ; seul `Narthecium` a été joué contre le natif. `TaintedNarthecium` demanderait un
  porteur Chaos et un `Maybe(75)` à répéter ; `BattleFatigue` n'a de porteur non immunisé que chez
  les summons.
* Le bras `dist 2` déplace le porteur, donc les tuiles des tueurs diffèrent d'un bras à l'autre. Le
  prédicat mesuré ne lit pas le tueur, et la géométrie porteur↔victime est **relue** après les coups
  (`d_end`), mais ce n'est pas « le même geste à une tuile près ».
* Le CRIT n'est pas neutralisé : sous le seuil d'overkill, `DamagePrediction$$IsOverkill` rend
  `isCritical`. Un crit sur le coup fatal aurait rendu le contrôle négatif — le probe l'aurait dit
  (`INCONCLUSIF`), pas confondu avec un refus d'adjacence.

## 7. Résidu ouvert

* **`#462-r4b-r1-r1-r1-r1-b-r1-r1`** — `BattleFatigueAbility.matches` ne porte pas
  `NOT IsObjectOrSteppable(dying)`, pourtant présent dans `BattleFatigueAbility$$CreateTrigger` et
  **cité dans sa propre docstring**. Écart permissif (le port déclenche la fuite sur la mort d'un
  décor/decoy que le natif ignore), trouvé en relisant le décompilé de ce site ; hors du périmètre de
  cette tranche, non corrigé. Le prédicat existe déjà porté ailleurs
  (`triggers/loki/master_of_the_tutelaries.py`, `triggers/loki/barbed_ovipositor.py` : traits `27`
  Steppable / `13` Object).
