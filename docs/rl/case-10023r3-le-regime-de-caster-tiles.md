# #10023-r3 — `ReturnsOnlyUnits` : le discriminant est le NŒUD, et il retourne #10023

**Verdict : le mirror portait le MAUVAIS régime, et les deux faces portaient la MÊME erreur.**
Build `t6dpr4k06g`.

---

## 1. Ce que le résidu demandait, et ce qui est mesuré

`IdunBattle.DSL.TargetsSelector$$SelectAllUnits`, relu verbatim :

```
lVar8 = <slot 0x17 = Select>(this, entities);
cVar5 = (**(code **)(*(longlong *)this + 0x278))(this, ...);   // slot 20 = get_ReturnsOnlyUnits
if (cVar5 == '\0') { foreach (e in lVar8) if ((u = SelectUnit(this,e,sel)) != null) out.Add(u); }
return <lVar8 TEL QUEL si la porte est VRAIE, sinon la liste resolue>;
```

Les slots viennent de **deux sources indépendantes** qui concordent :
`data/symbols/<build>/metadata/interface_slots.tsv` donne `TargetsSelector 19 get_ReturnsOnlyTiles`,
`20 get_ReturnsOnlyUnits`, `23 Select` ; et la vtable IL2CPP commence à `klass+0x138` par entrées de
`0x10`, donc `0x138 + 20*0x10 = 0x278` — exactement l'offset du binaire.

**La propriété n'est pas résoluble par la table des symboles** : `frida/methods.tsv` est indexée par
ADRESSE et IL2CPP déduplique les corps triviaux — elle porte **2** `get_ReturnsOnlyTiles` pour tout
le binaire et **aucun** `get_ReturnsOnlyUnits`.

| slot | valeur mesurée | comment |
|---|---|---|
| `<DSLSelectors+0x60>` = `Target` | **VRAI** | 19 casts de `1201 SquigMine` (#10023-r1) |
| `<DSLSelectors+0x58>` = `CasterTiles` | **VRAI** | ce résidu, ci-dessous |

## 2. La mesure — `1094 TheLantern` sur `deathBossMortarion`

`probe_10023r3_caster_tiles_regime_live.py`. Board `GB_Mortarion_05`, seed `777`, cible **`(1,7)`**
(l'une des **2** tuiles que `abilityTargets.fromHere` déclare légales).

**Le caster SEPT-HEX n'arrive PAS par `--p-units`** : `SetupGameOperation$$AddBossUnit` est la seule
voie qui pose un porteur sur une LISTE de tuiles, `AddPredefinedUnits` n'en pose qu'UNE (#10018-r1).
Monter Mortarion par le roster donnerait un caster mono-hex, sur lequel les deux régimes coïncident
— le régime dégénéré exact qui a empêché #10023 de trancher. Le montage écrit donc `BC.BossUnit`
dans une COPIE du seed BC. Mesuré : `feet = [(4,8),(3,9),(4,9),(5,9),(5,8),(4,7),(3,8)]`.

⚠ **La main tile est `feet[0]`, pas `pos`** : `decisionView.units[].pos` vaut `(3,8)` — le DERNIER
pied projeté (`runner/snapshot.py::_load_feet`).

| | aire | verdict |
|---|---|---|
| NATIF (tuiles `1195 TheLantern_PendingTarget`) | **9** | — |
| régime « retranche l'empreinte » | 9 | `B\natif = natif\B = []` |
| régime « retranche la main tile seule » | 10 | `A\natif = [(3,8)]` |

⇒ **`CasterTiles.ReturnsOnlyUnits == VRAI`.** L'aire entière concorde, pas une tuile isolée.

### L'explication concurrente, écartée des DEUX côtés

Un pied absent s'expliquerait aussi par un filtre d'**OCCUPATION** — les pieds sont les seules
tuiles occupées à distance 2 de la cible.

- **Décompilé** : `TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` n'appelle
  `TileExtensions$$IsEmptyOrSteppable` que sous le flag `onlyMovable`, que `TheLanternAbility` passe
  à `0` ; `TileUtil$$IsTileValidForList` ne lit que le mur (`tileComponent+0x41`), `IsWalkable` et —
  sous `checkElevation`, ici à `0` — l'écart d'élévation. **Aucun test d'occupant.**
- **Mesure** : bras de contrôle — une unité alliée posée sur `(2,8)`, tuile VIDE de l'aire au même
  étage (`ring2 & cring1`), y **reste marquée** après le même cast.

## 3. Le port

`engine/dsl/base.py` :

- `TargetsSelector.RETURNS_ONLY_UNITS = True` — le défaut est la **mesure**, pas une commodité ;
- `_main_tile_of(entity, …)` mirrore les **trois** branches de `EntityExtensions$$GetMainTileId`
  (unité → `feet[0]`, entité à pieds → `set[0]` récursif, tuile → **elle-même**) ;
- `_main_tiles(origin, board, units, only_units)` boucle par ENTITÉ ; le régime `False` (jamais
  déclaré par aucun nœud) résout d'abord l'occupant, donc une tuile VIDE y disparaît ;
- `returns_only_units(node)` lit la propriété du NŒUD. Call-sites : `accessors.SurroundingTiles`
  (`self.center`) et `_within(center_node=…)` (4 nœuds `Surrounding*`).

**L'effet correctif** : le foyer retranchait `_origin_tiles(origin, board)[:1]`, donc UNE tuile sur
une empreinte de sept. Invisible sur toute origine à un élément — **34 des 35** instanciations
recensées.

**La face DÉCISION aussi** : `playbook/noncomparable/the_lantern.py::_ring` excluait `feet[:1]`.
#10023 avait aligné la face COMBAT sur elle ; il fallait l'inverse.

## 4. Ce qu'aucun cliquet ne pouvait voir

`probe_10023r1` étage 4 assertionnait « UNE SEULE tuile retranchée » et il était **VERT** — l'oracle
et le port portaient la **même** erreur. Le test qui le joue rangeait même cet étage parmi ceux qui
« survivent à la mutation `résolution d'occupant' », et c'était vrai : sous cette mutation les sept
pieds résolvent vers la même unité, donc une seule tuile aussi. Seule une mesure **extérieure**
pouvait rouvrir le dossier.

Depuis : l'étage est renommé `etage4_empreinte_retranchee_en_entier`, il porte un cran de non-vide
sur son propre écart, et **deux** mutations mordent désormais dessus (`résolution d'occupant`,
`port d'avant`). `test_1030_the_lantern_offline` a vu sa contre-épreuve **inversée** (la zone mutée
est désormais plus GRANDE).

## 5. Ce que la tranche NE couvre PAS

- **Le régime `ReturnsOnlyUnits == False` est porté, jamais exercé** : aucun nœud du dépôt ne le
  déclare. Il est écrit parce que c'est le natif.
- **Deux slots mesurés sur N.** `Target` et `CasterTiles` concordent ; les autres accesseurs
  (`Owner`, `Actor`, `TargetTile`, …) prennent le défaut sans mesure propre. Un nœud qui rendrait
  `False` doit l'ÉCRIRE avec la mesure qui l'établit.
- **Le régime « N unités distinctes »** reste inerte : 35 instanciations, aucune origine multi-unité.
- Le montage n'a qu'**une** cible discriminante par run (`abilityTargets.fromHere` n'en déclare que
  2, le gate dynamique `|A ∩ B| == 1` de #1030-r1 étant très restrictif).
