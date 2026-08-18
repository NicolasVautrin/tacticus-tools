# #10023-r1 — `Tiles(origin)` en domaine TUILE : la prémisse du résidu était FAUSSE

**Verdict** : sur les trois défauts annoncés, **un seul était réel**. Les deux autres reposaient sur
une résolution TUILE → OCCUPANT que la mesure live **réfute** (19 casts sur 19). Le port revient au
comportement d'avant sur ce point, désormais sous cliquet — et la thèse réfutée est gardée comme
**mutation** pour qu'elle ne puisse pas revenir en silence.

## 1. Ce que le résidu annonçait, et ce qui est mesuré

| # | énoncé du résidu | verdict | preuve |
|---|---|---|---|
| (a) | une origine **TUILE VIDE** ne fait rien retrancher au natif | **FAUX** | 19 casts live de `1201 SquigMine`, `P = 0,0039` sur les 8 retenues |
| (b) | `_within` appelle `_main_tile(center)` **sans `board`** ⇒ exclusion vide en domaine ID | **VRAI** | `_origin_tiles(list[int], None)` rend `[]` — corrigé |
| (c) | une origine à **N unités distinctes** retranche N main tiles | **VRAI mais INERTE** | boucle native verbatim ; 35 instanciations recensées, 35 mono-unité |

## 2. La mesure qui tranche

`1201 SquigMine` (`orksRukkatrukk`, MoW **du pool**) porte `TargetTileIsFree` dans son masque : la
tuile ciblée est **toujours vide**. Le régime (a) y est donc systématique, pas accidentel.

L'observable n'est **pas** l'ensemble des tuiles minées (l'ordre d'énumération du pool n'est pas
porté — résidu `#215`) mais son **CARDINAL** :

```
pool   = EntitiesWithoutEffects(CanAddUnit(SurroundingTiles(Target, includeCenter: 0, range)), [1441])
picked = PickRandomly(pool, nrOfTiles)
targets = Cache(Target op_Addition picked, unique: 1)
```

`Union` étant **unique**, si la cible était dans le pool `PickRandomly` pourrait la tirer et le
total tomberait à `nrOfTiles`. Mesuré sur `MC1_67`, cible `(6,0)`, `|pool| = 7 + 1`,
`nrOfTiles = 4` : **19/19 casts rendent 5 tuiles**, jamais 4. Sous l'hypothèse « la cible est dans
le pool », chaque cast avait `p = 4/8` de la tirer.

⇒ **le natif RETRANCHE la tuile ciblée, vide.** `probe_10023r1_squig_pool_live.py`, rc 0 sur
`--seeds 777,31337,4242,11,22,33,44,55`.

## 3. Pourquoi le décompilé et la mesure ne se contredisent pas

La chaîne, relue verbatim sur `t6dpr4k06g` :

```
DSLSelectors$$SurroundingTiles(includeCenter == 0) = SurroundingTiles(..., 1, ...) op_Subtraction Tiles(origin)
DSLSelectors$$Tiles(entities)                      = new UnitsMainTilesSelector(inner: entities, state)
UnitsMainTilesSelector$$Select                     = foreach (e in inner.<slot 3 = SelectAllUnits>(entities, 0))
                                                        if ((t = GetMainTile(e, state)) != null) result.Add(t)
TargetsSelector$$SelectAllUnits                    = list = this.<slot 0x17 = Select>(entities);
                                                     if (this.<klass+0x278>()) return list;   // <- TEL QUEL
                                                     foreach (e in list) if ((u = SelectUnit(this, e, 0)) != null) out.Add(u)
EntityExtensions$$GetMainTileId, 3e branche        = if (!IsTile(entity)) return 0; return <id>(entity)
```

**La porte `klass+0x278` est la clé, et elle n'est pas celle qu'on croit** :
`TargetsSelector$$SelectTiles` teste `klass+0x268` — deux offsets **distincts** dans le même
binaire. La vtable IL2CPP commence à `klass+0x138`, entrées de `0x10` ⇒ slots **20** et **19**,
soit `get_ReturnsOnlyUnits` et `get_ReturnsOnlyTiles` (slots confirmés par `ITargetsSelector` :
`Select` y est slot 23 = `0x17`, exactement ce que le décompilé courant invoque).

Quand l'origine **déclare rendre des unités**, il n'y a **aucune** résolution : l'entité-TUILE
traverse, et `GetMainTileId` finit par sa troisième branche — **une tuile est sa propre main
tile**. C'est le régime du slot `Target` (`<DSLSelectors+0x60>`), construit dans
`DSLSelectors$$InitializeShared` depuis une **classe distincte** de celle de `CasterTiles`
(`+0x58`). Sur un cast tile-target, ce slot porte une entité-tuile tout en restant « unit-domain ».

**Cette propriété n'est pas résoluble en statique** : les corps triviaux `return 1` sont
dédupliqués par IL2CPP et n'ont aucun propriétaire nommé — « l'absence dans les tables ne prouve
RIEN ». Seule la mesure pouvait trancher. Elle n'est **pas portée** : résidu `#10023-r3`.

## 4. Le témoin qu'aucune lecture n'aurait désigné

Contre-épreuve **jouée** (thèse réfutée câblée dans `_main_tiles`, quatre tests cibles rejoués) :

- **verts** sous la thèse réfutée : `test_1030_the_lantern_offline`, `test_units_directly_behind_offline`,
  `test_979_ports_decision_offline` ;
- **ROUGE** : `test_967r2_include_non_walkable_offline::test_etage4_les_deux_faces_de_1187_s_accordent`
  (`1187 ThriceBlessedConflagration`).

La banque **refusait déjà** la thèse du résidu, par un fichier que rien dans la fiche ne désignait.
Et `test_1030` — le plus proche du sujet — reste vert **dans les deux régimes** : sur son
call-site, les sept entités-tuile d'une empreinte résolvent toutes vers la même unité, donc les
deux thèses y rendent la MÊME tuile. **C'est exactement pourquoi #10023 n'avait pas pu trancher**,
et pourquoi il fallait un call-site à tuile VIDE.

## 5. Le port

`engine/dsl/base.py::_main_tiles(origin, board, units)` — deux régimes, séparés par le **domaine
de l'origine**, faute de pouvoir lire `ReturnsOnlyUnits` :

- **domaine UNITÉ** (tous les éléments reconnus par `_est_unite`) → une main tile **par entité**
  (`GetMainTile` est dans la boucle, verbatim) ;
- **domaine TUILE** → `_origin_tiles(origin, board)[:1]` : la tuile elle-même, et **une seule** sur
  une empreinte (non-régression #10023).

`board` devient **obligatoire** aux trois call-sites (`_within`, `accessors.SurroundingTiles`,
`units.UnitsDirectlyBehind`) — c'est la correction (b), la seule réelle.

## 6. Ce que la tranche NE couvre PAS

- **`ITargetsSelector.ReturnsOnlyUnits` n'est pas porté** (`#10023-r3`). Le port sépare les deux
  régimes par le domaine de la valeur ; le natif les sépare par une propriété du **nœud**. Les deux
  critères coïncident sur les 35 call-sites actuels, rien ne garantit qu'ils coïncident toujours.
- **#10023 lui-même reste NON CONFRONTÉ live.** Que `Tiles(CasterTiles)` d'une empreinte de sept
  tuiles rende **une** tuile et non sept dépend de `CasterTiles.ReturnsOnlyUnits == false`, qui est
  supposé (classe distincte de celle du slot `Target` dans `InitializeShared`) et non mesuré.
  Montage nommé pour le confronter : `1094 TheLantern` sur `deathBossMortarion` (boss ⇒
  `--explicit-stats`), en comptant les tuiles portant `1195 TheLantern_PendingTarget` —
  `|area|` diffère de plusieurs tuiles entre les deux régimes.
- Le régime **N unités distinctes** (c) est porté mais **jamais exercé** : aucun des 35 call-sites
  ne construit une telle origine.
- Le cardinal du pool de `SquigMine` change de +1 côté port avec la correction (b) ? **Non** — (b)
  ne touche que `_within`, pas `accessors.SurroundingTiles` ; le pool de SquigMine est inchangé.

## Résidus ouverts

- **`#10023-r3`** — `ITargetsSelector.ReturnsOnlyUnits` n'est pas porté, et c'est lui le vrai
  discriminant des deux régimes de `Tiles(origin)`.
