# #10022-r3 — `ShortestPathToEnemyUtility` : le bucket qui decide, porte et CONFRONTE EN LIVE

Build `t6dpr4k06g`. **Verdict : porte, et confronte au natif sur 5 configurations discriminantes,
avec un BRAS NEGATIF qui etablit la causalite de `#10022-r1`.**

La meme experience tranche les deux items, et c'est pour ca qu'elle est ecrite comme un seul
montage : faire varier UNIQUEMENT la geometrie, a seed / board / roster constants, et regarder si
l'ordre d'activation de l'IA suit la prediction du port.

---

## 1. Ce que le decompile porte

`IdunBattleLogic.AI.Utilities.UnitPicker.ShortestPathToEnemyUtility$$EvaluateUnitInSteps` n'alloue
que la machine a etats. Le corps est dans
`IdunBattleLogic.AI.Utilities.UnitPicker.ShortestPathToEnemyUtility.u003CEvaluateUnitInStepsu003Ed__0$$MoveNext`,
remis en C# :

```csharp
var dc = new <>c__DisplayClass0_0 { <>4__this = this,
                                    unitTile = unit.GetMainTile(this.state) };
int? minSteps = null;
foreach (var target in Enumerable.OrderBy(this.state.GetAllEnemyUnitsOfUnit(unit),
                                          dc.<EvaluateUnitInSteps>b__0)) {
    yield return BaseUtility.<statics+0x30>;                     // pas de travail (-12345)
    var targetTile = target.GetMainTile(this.state);
    if (minSteps.HasValue && minSteps.Value <= <distance>(dc.unitTile, targetTile)) continue;
    var path = this.pathfinders.<slot 4>(1, unit, dc.unitTile, targetTile, null);
    if (path != null) {
        if (minSteps.HasValue && path.Count >= minSteps.Value) continue;
        minSteps = path.Count;
        if (minSteps.Value == 1) break;
    }
}
yield return minSteps.HasValue ? Fix64(-minSteps.Value) : BaseUtility.<statics+0x18>;
```

Le comparateur du tri est un corps A PART, et c'est le seul dont Ghidra garde les arguments —
donc le seul qui donne l'ORDRE des deux tuiles
(`...ShortestPathToEnemyUtility.u003Cu003Ec__DisplayClass0_0$$u003CEvaluateUnitInStepsu003Eb__0`) :

```csharp
int b__0(IEntity target) =>
    this.<>4__this.query.<slot 0x6c>(this.unitTile, target.GetMainTile(<>4__this.state));
```

### Les six lectures qui ne se deduisent d'aucun nom

| ce qui est ECRIT au site | ce que c'est, et comment on le sait |
|---|---|
| `pathfinders.<slot 4>` | `GetPath` a **CINQ** parametres — LU dans `data/symbols/<build>/metadata/interface_slots.tsv` (`IPathfinders 4 GetPath 5`), donc la surcharge `(pathfinderType, unit, from, to, useTeleporter)` |
| le `1` du premier argument | un **LITTERAL** : `PathfinderType.IgnoreTerrain`, meme pour une unite volante. Meme pathfinder que `MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` |
| `query.<slot 0x6c>` | `GetDistance` a **DEUX** parametres, parmi TROIS homonymes (`IBattleQuery` 108/109/110). Le site passe deux `TileEntity` ⇒ la surcharge `(IEntity, IEntity)`, dont le corps entier est un forward vers le slot 9 d'`IMovementQuery`. C'est la distance **HEX** |
| `path.Count` | `route+0x18` = `List._size` : un compte de **NOEUDS, extremites incluses** = `aretes + 1`. Une flood-fill d'ARETES rend UN DE MOINS |
| les `yield` intermediaires | `BaseUtility.<statics+0x30>` = `Fix64(-12345)`. La valeur est le **DERNIER** `Current`, apres que `MoveNext()` a rendu `false` |
| aucun chemin | `BaseUtility.<statics+0x18>` = **HORS COURSE pour CE bucket** — pas le veto ferme `+0x20`, et surtout pas `0` |

### `GetAllEnemyUnitsOfUnit` a UN filtre, et un seul

`IdunBattle.Entities.StateExtensions$$GetAllEnemyUnitsOfUnit` = `GetAllEnemyUnitsOfPlayer(state,
GetCurrentPlayer(unit, state), null)`, dont le corps LU retient une entite quand **deux** conditions
tiennent : son `TeamId` differe de celui du porteur, **et** elle ne porte pas le trait `0x1b` =
`UnitTrait.Steppable` (27). C'est tout.

⚠ **Aucun filtre de ciblabilite**, contrairement a `MovementActionGenerator$$FindClosestEnemy`
(qui, lui, ecarte Environment / non-ciblable / `IsIrrelevantObject` / mort / hors `GetOnlyTargets`).
Un ennemi en deep-strike, sous taunt ou neutre **compte** pour cette utilite.

### Ne pas confondre avec `MinDistanceToClosestEnemyUtility` (17)

Meme pathfinder, calcul different :

| | `MinDistanceToClosestEnemy` (17) | `UnitWithShortestPathToEnemy` (72) |
|---|---|---|
| combien d'ennemis | **UN** — le `ClosestEnemy` FIGE en amont | **TOUS** ceux de `GetAllEnemyUnitsOfUnit` |
| filtres de ciblabilite | quatre | **aucun** |
| tuiles de la cible | le **FOOTPRINT COMPLET** | la **MAIN TILE** seule |
| canal | MOUVEMENT (`EvaluateMovementInSteps`) | UNITE (`EvaluateUnitInSteps`) |

Les deux divergent des qu'une unite est multi-hex ou qu'un ennemi est non ciblable.

---

## 2. Ce que les deux elagages changent — et ce qu'ils ne changent PAS

Le port les mirrore tels quels, mais il faut savoir ce qu'ils valent, sinon on ne sait pas ce
qu'on valide.

- **Elagage 1** (`minSteps <= hexDist(unitTile, targetTile)` -> skip) est **ADMISSIBLE** sur un
  graphe ou toute arete relie deux voisins hex : un chemin de `hexDist` aretes compte `hexDist + 1`
  noeuds, donc `path.Count >= hexDist + 1 > minSteps` — la cible elaguee ne pouvait pas ameliorer.
  ⚠ **Un TELEPORTEUR le rendrait FAUX** (`IgnoreTerrainPathfinder$$IsValidPathNode` autorise une
  arete entre deux tuiles de teleportation quelle que soit l'elevation). Ce serait un elagage errone
  **DU NATIF**, a mirrorer tel quel — pas un bug du port. Aucun board de `data/boards/` n'en porte.
- **Elagage 2** (`path.Count >= minSteps` -> skip) n'ecrase pas un meilleur minimum.
- Le **`break` a `minSteps == 1`** exigerait que la main tile de l'unite SOIT celle d'un ennemi
  (chemin d'un seul noeud) : jamais en pratique, mais porte.

⇒ Hors teleporteur, **le resultat est exactement `min over ennemis of pathNodeCount(unitTile,
targetMainTile)`**, et l'ordre de visite n'y change rien.

---

## 3. Le port

`scripts/python/engine/utilities/unit_picker.py` — `ShortestPathToEnemyUtility.evaluate_unit(...)`.
Les quatre dependances sont **INJECTEES**, parce qu'elles le sont aussi cote natif
(`BaseUtility$$Init` renseigne `state` en `+0x10`, `query` en `+0x20`, `pathfinders` en `+0x28`) :
la classe ne connait ni le `State` ni le `Board` du port. C'est le **canal UNITE**, distinct du
canal TUILE (`utilities/tile.py`) et du canal MOUVEMENT (`utilities/move.py`).

Les sentinelles de `IdunBattle.AI.Utilities.BaseUtility$$.cctor` entrent dans
`engine/utilities/base.py`, LUES :

```
statics+0x00 = Fix64.op_Implicit(0)                                  # NEUTRE, pas sentinelle
statics+0x08 = Fix64.op_Implicit(0x186a0)                            # 100000
statics+0x10 = Fix64.statics+0x10                                    # MaxValue
statics+0x18 = Fix64.MinValue / Fix64.FromIntFraction(0xf4241, 0xf4240)
statics+0x20 = Fix64.statics+0x18                                    # MinValue
statics+0x28 = Fix64.MinValue / Fix64.FromIntFraction(0xf4242, 0xf4240)
statics+0x30 = Fix64.op_Implicit(0xffffcfc7)                         # -12345
```

⚠ **Deux d'entre elles sont des DIVISIONS `Fix64`** dont le port ne mirrore pas l'arithmetique
Q32.32 : leur valeur flottante est **APPROCHEE**. Elles sont donc portees en **SINGLETONS**
(`Fix64Sentinel(float)`) et se testent **par `is`, jamais par `==`** — ce qui est aussi le canal
FIDELE : le natif les compare a un CHAMP STATIQUE, donc ce qui circule est une valeur DESIGNEE,
pas un intervalle numerique.

⚠ `HARD_VETO` est la MEME valeur que `engine.utilities.move.NO_PATH_UTILITY`, ecrite la-bas en
float NU avant que ce foyer existe. On n'a pas touche a `move.py` (hors perimetre), mais un futur
`#10022-r2` qui rendra le decideur sensible aux sentinelles devra les CONFONDRE volontairement :
le float nu ne passerait aucun test `is`.

---

## 4. Cliquet offline — `probe_10022r3_shortest_path_to_enemy.py`

Sept etages, `rc 0/1/2`. Les trois premiers gardent la FRAICHEUR (symboles de l'iterateur, slots
d'interface, les deux ordinaux ECRITS au site) ; le 5e garde l'IDENTITE des sentinelles ; le 6e la
STABILITE du tri.

**L'etage 4** est le seul qui teste du comportement : il confronte le mirror fidele a l'argmin naif
sur 240 configurations de grille hex avec murs et relief. Il **assertionne son propre non-vide sur
quatre axes** — elagage 1 exerce **185** fois, elagage 2 **82**, detours reels (`pathCount >
hexDist + 1`) **184**, hors-course **13**. Sans ces crans, une grille sans obstacle rendrait un
accord parfait ET VIDE.

**Contre-epreuve, cinq mutations du port jouees** :

| mutation | effet |
|---|---|
| elagage 1 au sens inverse | 32 divergences |
| elagage 2 au sens inverse | 63 divergences |
| signe du resultat | 227 divergences |
| sentinelle rabattue sur `0` | 13 divergences |
| **elagage 1 elargi (`<=` -> `<= +1`)** | **VERT** |

La cinquieme n'est pas un trou du cliquet : c'est une **equivalence PROUVEE**
(`pathCount >= hexDist + 1`, donc la cible elaguee ne pouvait de toute facon pas ameliorer). Ce qui
separe les deux formes est le **NOMBRE de requetes `GetPath`** — d'ou l'**etage 7**, un temoin
fabrique pour vivre exactement dans le regime discriminant (`minSteps == hexDist(B) + 1`), ou le
natif interroge DEUX cibles et la variante elargie une seule. Il rougit sur la mutation, et son
temoin **verifie d'abord sa propre premisse** (sinon il serait vacant).

---

## 5. Confrontation LIVE — `probe_10022r3_ordre_activation_live.py`

### 5.1 Le montage, et pourquoi il est fait comme ca

Roster IA = **trois CLONES du meme `unitId`** (`astraBullgryn`). Ce n'est pas une commodite : c'est
ce qui NEUTRALISE mecaniquement les buckets 0 a 5, un par un —

| bucket | sur trois clones | departage ? |
|---|---|---|
| 0 `PreferSummons` | aucun n'est Summon/Object -> tous VETO_CONDITIONNEL, donc `best` reste nul et la boucle de veto ne s'execute pas | non |
| 1 `PreferNonBoss` | aucun n'est boss -> tous `0`, `diff 0 > 1` faux | non |
| 2 `PreferFreshlySpawned` | meme provenance -> meme valeur | non |
| 3 `UnitOrder` | meme `unitId`, memes abilities, memes traits -> meme somme ; le flag de cut n'elimine personne a valeurs egales | non |
| 4 `LastAbilities` | aucun ne porte `RealityUnbound` | non |
| 5 `PreferAbilities` | constante HORS COURSE pour toute unite dans ce build | non |
| **6 `UnitWithShortestPathToEnemy`** | **la seule chose qui les distingue est leur POSITION** | **oui** |

Les positions des DEUX camps sont posees par `--place` / `--a-place` **au build** : `--a-place`
sort l'unite de `BC.PredefinedUnits` et la pose par `AddUnitMessage`, donc la geometrie varie
**sans consommer l'action d'aucune unite** (un `act move` la marquerait comme ayant bouge et
changerait ce qu'on mesure).

L'oracle est `aiPlayByUnit(maxTurns: 1, maxActivations: 1, captureEvents: true)`, dont chaque entree
de `demos` porte `activatedUnitId` **et** le `toActivate` capture juste avant — l'oracle et son
temoin dans le meme objet.

### 5.2 La garde anti-court-circuit

`decisionView.toActivate` **n'est PAS** l'ordre choisi par le natif : c'est l'ENSEMBLE des unites
activables dans l'ordre d'ITERATION de l'ECS, soit (a un cran pres) l'ENTREE du picker
(`AnAiGroupOperator$$GetValidUnits`). Une prediction qui coinciderait avec `toActivate[0]` ne
prouverait donc rien.

Le probe classe chaque configuration en **TROIS** etats, pas deux : `DISCRIMINANT` (l'ECS est
mesure et il differe de la prediction), `DEGENERE` (il coincide), `ECS_INCONNU` (`toActivate` non
mesure). Le troisieme existe parce qu'un `toActivate` vide ne veut pas dire « non degenere » : il
veut dire qu'on N'A PAS MESURE, et le rabattre sur « discriminant » gonflerait le compte du bras
positif avec des configurations dont on ignore si elles prouvent quoi que ce soit. **Une serie
entierement degeneree rend ROUGE** — c'est un echec de montage, pas un succes.

### 5.3 Bras POSITIF — 5/5

Board `MC1_67`, seed `777`, six geometries. L'ordre d'iteration ECS est **constamment `[79, 81, 83]`**
et la prediction, elle, varie :

| config | placements IA | utilites portees | ECS | predit | ACTIVE | verdict |
|---|---|---|---|---|---|---|
| 1 | (6,8) (6,7) (2,6) | 79:-12 81:-11 83:-9 | [79,81,83] | 83 | **83** | ACCORD |
| 2 | (2,6) (6,8) (6,7) | 79:-9 81:-12 83:-11 | [79,81,83] | 79 | 79 | accord DEGENERE (ecarte) |
| 3 | (6,8) (2,5) (5,8) | 79:-11 81:-7 83:-10 | [79,81,83] | 81 | **81** | ACCORD |
| 4 | (5,8) (6,7) (3,5) | 79:-10 81:-10 83:-6 | [79,81,83] | 83 | **83** | ACCORD |
| 5 | (6,6) (4,5) (6,8) | 79:-10 81:-8 83:-12 | [79,81,83] | 81 | **81** | ACCORD |
| 6 | (6,7) (3,6) (6,8) | 79:-10 81:-7 83:-11 | [79,81,83] | 81 | **81** | ACCORD |

**5 discriminantes, 5 accords, 0 a ECS non mesure.** Dans les cinq, l'unite activee n'est PAS la
premiere de l'ordre d'iteration.

**Contre-epreuve du probe lui-meme** : muter le SIGNE du port (`-min_steps` -> `min_steps`) fait
predire l'unite la plus LOIN et rend **3 desaccords sur 3**. Le vert du bras positif n'est donc pas
un vert de construction.

### 5.4 Bras NEGATIF — la CAUSALITE de `#10022-r1`

Le bras positif, seul, est compatible avec « la geometrie commande, mais par un autre chemin ». Le
bras negatif ferme cette porte : **memes six geometries, meme seed, meme board, meme roster — un
seul champ change**, `RandomizeAiInput` passe a `true` dans un seed BC copie sous `logs/`
(`--randomize`).

Resultat : l'unite activee est **`83` dans les six configurations**, quelle que soit la geometrie
(2 « accords » sont des coincidences — avec trois candidats, environ un tiers). C'est exactement la
signature de `IdunBattle.AI.OperationalDeciders.RandomGroupOperation.u003CPickNextUnitu003Ed__7$$MoveNext`
= `validUnits[random(validUnits.Count)]` : a seed et effectif constants, le tirage rend toujours le
meme INDEX, et il ne lit **aucune** position.

⇒ **`BattleConfiguration.RandomizeAiInput` pilote bien le choix de strategie.** `#10022-r1` n'est
pas une correlation lue au decompile : le champ est CAUSAL, mesure sur le regime confrontable.

Le critere du bras negatif est **INVERSE** dans le probe : un accord parfait y rendrait ROUGE, en
disant qu'il REFUTE `#10022-r1`.

---

## 6. Ce qui n'est PAS couvert

- **Les buckets 0 a 5 ne sont pas portes** (`#10022-r2`, `#10022-r4`, `#10022-r5`). Le montage les
  neutralise par construction (clones) ; il ne les VALIDE pas. Une confrontation sur des unites
  HETEROGENES exigerait `#10022-r2` d'abord.
- **Seule la PREMIERE activation est confrontee.** Apres elle, l'unite a bouge et les distances ont
  change ; predire la sequence complete exigerait de re-simuler chaque deplacement.
- **L'exception TELEPORTEURS** de `IgnoreTerrainPathfinder$$IsValidPathNode` (section 2) : non
  portee en amont, donc non exercee ici.

⚠ **LES TROIS AUTRES PUCES QUI VIVAIENT ICI SONT LEVEES par `#10022-r7`** — second couple
(board, seed), unite MULTI-HEX, ennemi non ciblable. Chiffres et verdicts (dont **UNE** face
qu'aucun montage ne peut trancher par cet oracle, residu `#10022-r8`) :
`docs/rl/case-10022r7-trois-axes-de-generalisation.md`. Le probe y a gagne **trois gardes**, tous
nes d'un FAUX ROUGE : l'argmax se prend sur l'ENTREE DU PICKER, un CANDIDAT doit etre vivant la ou
un ENNEMI n'a pas a l'etre, et `team_ia` n'est plus la team MAJORITAIRE (indeterminee a effectifs
egaux).
