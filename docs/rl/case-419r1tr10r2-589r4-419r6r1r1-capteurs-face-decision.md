# Les trois capteurs manquants de la face DÉCISION — et deux résidus tranchés par la lecture

`#419-r1-tr10-r2` · `#589-r1-r1-r2-r1-r4` · `#419-r6-r1-r1` (capteurs, **NON CONFRONTÉS — fenêtre
de reinject à planifier**) · `#510-r2` (**CORRIGÉ**, confronté) · `#589-r1-r1-r2-r1-r2` et
`#510-r3` (**tranchés par le décompilé**, dans un sens qui contredit leur fiche).

Build `rnca9r7q6c`.

---

## 1. Pourquoi ces trois-là ensemble

Trois résidus butaient sur **exactement la même cause** : le mirror Python est posé et correct,
mais aucun hook ne publie son ENTRÉE côté DÉCISION. Chacun, pris seul, réclamerait sa propre
fenêtre de réinjection. Ils sont livrés dans la même PR pour qu'une seule fenêtre les paie.

**Aucune (ré)injection n'a eu lieu.** Le bundle compile (`frida-compile` OK ;
`tsc -p tsconfig.hooks.json` : **0** erreur sur les fichiers touchés, sur un total de 135
préexistantes ailleurs). Rien n'a firé, et rien ne pouvait firer.

---

## 2. `#419-r1-tr10-r2` — l'empreinte, et DEUX corrections du brief

### 2.1 Le point d'ancrage annoncé était le mauvais

Le backlog nommait `IdunBattle.Entities.UnitExtensions$$GetUnitFeet`. Son corps, relu :

```csharp
list = new List<IEntity>();
u    = UnitExtensions.GetUnit(unit, state);
comp = Entity.GetComponent<UnitComponent>(u);
for (e = UnitComponent.GetFeetEnumerator(comp); e.MoveNext(); )
    list.Add(state.GetEntity(e.Current));     // slot 0x29
return list;
```

Il rend les entités **`UnitFoot`**, pas les TUILES. Ce que le port consomme, ce sont des
coordonnées de tuile — et la résolution `UnitFoot -> Tile` (`foot.<+0x20>.<+0x14>`) est faite par
un AUTRE natif. L'artefact exact est `IdunBattle.Entities.EntityExtensions$$GetTiles(entity,
state)`, dont le corps est **littéralement**

```csharp
return new List<IEntity>( EntityExtensions.IterateTiles(entity, state) );
```

c'est-à-dire la matérialisation de l'itérateur que
`IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` consomme (`inner =
origin.Select(entities)`). C'est donc le natif du consommateur, pas un substitut.

`EntityExtensions.<IterateTiles>d__17$$MoveNext` teste **trois** types d'entité — pied → sa tuile ;
tuile → elle-même ; unité → ses pieds — et sort FAUX pour tout le reste.

### 2.2 Le FOYER annoncé était le mauvais, et il aurait produit une valeur PÉRIMÉE

Le backlog déclarait `frida/hooks/rpc-snapshot.ts`. `combatSnapshot` est un capteur **COLD** — sa
propre docstring dit « à appeler une fois au chargement de la BattleConfig ». Or une empreinte est
**DYNAMIQUE** : elle suit chaque déplacement. Publiée là, elle serait fausse dès le premier move —
pire qu'absente, parce qu'un consommateur la croirait. Elle vit donc sur `decisionView`, refrappé à
chaque pas : `projection.ts::readEntityFeet`, publié en tri-état sous `decisionView.units[].feet`.

### 2.3 Ce que les MoW exigeaient en plus

`EntityType.Machine` n'est aucun des trois types qu'`IterateTiles` reconnaît : `GetTiles(machine)`
peut donc rendre `[]` **sans que rien n'ait échoué**. L'empreinte réelle d'une MoW est l'ensemble
des `MachinePlatform` qui la portent — et elle était **déjà publiée**, éclatée en une ligne
`mows[]` par plateforme, donc jamais lisible comme un ensemble. `mows[].platformTiles` la rend
telle quelle sur chaque ligne de la même machine.

Côté Python, `scene.feet_by_id` existe parce que les MoW ne sont **pas** dans `scene.units` (canal
`.mows` séparé) : sans cette table, leurs pieds seraient publiés et jamais lus. La mesure native
prime sur la dérivation (`feet` d'abord, `platformTiles` seulement s'il est vide).

### 2.4 Un écart LU, mesuré NEUTRE — et c'est pour ça qu'on ne le corrige pas

`AdjacentTilesSelector$$Select` retire l'empreinte par `if (!inner.Contains(n))`, où `inner` est ce
que rend `origin.Select(entities)`. Quand `origin` est un sélecteur d'**unité** (`Owner`, `Caster`
— le cas des trois consommateurs portés), `inner` contient l'**entité**, pas ses tuiles : le
`Contains` compare une tuile à une unité et **ne mord jamais**. Le port, lui, soustrait toujours
l'empreinte (`if p in tiles: return False`).

L'écart est **inobservable sur ces consommateurs** : le seul occupant que le natif ajoute ainsi est
le sujet lui-même (ses autres pieds), et `AdjacentUnits`/`AdjacentFriends`/`AdjacentEnemies` le
retirent juste après par `TargetsSelector$$op_Subtraction(…, unit)`. On le NOMME sans le corriger —
corriger `adjacent_positions`, qui a d'autres appelants, pour un écart neutre serait un risque
gratuit.

---

## 3. `#589-r1-r1-r2-r1-r4` — une des deux causes ÉLIMINÉE par la lecture

### 3.1 Le sélecteur n'est PAS géométrique

`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, lu :

```csharp
elevOrigin = tile.<+0x20>.<+0x18>
foreach (id in tile.<+0x30>.<+0x10>)              // une LISTE STOCKEE, aucun calcul de coordonnee
    t = state.GetEntity(id);            if (t == null) continue;
    if (!allowTemporary       && TileExtensions.IsTemporary(t))              continue;
    if ( onlyWalkableTiles    && !TileExtensions.IsWalkable(t, true))        continue;
    if ( onlyEmptyOrSteppable && !TileExtensions.IsEmptyOrSteppable(t, st))  continue;
    if (abs(elevOrigin - t.<+0x20>.<+0x18>) < 2) yield t;
```

Le ring-1 natif est une **liste portée par la tuile**, filtrée. La lecture « le sélecteur est
réellement géométrique » est donc **éliminée**.

### 3.2 Et les deux natifs lisent LE MÊME substrat — la fiche disait l'inverse

`case-589-r1-r1-r2-r1` §6 conclut : « `AdjacentTilesSelector` (le chemin DSL) et
`BattleQuery$$IterateAdjacentTiles` … **ne lisent pas le même substrat** ». La chaîne d'appel,
relue de bout en bout, dit le contraire :

```
DSLSelectors$$AdjacentFriends(unit, unique, selType)
  = Friends( unit, Units(AdjacentTiles(unit), unique, selType) - unit, selType )
DSLSelectors$$AdjacentTiles(origin)   -> new AdjacentTilesSelector(state, battleQuery, origin)
AdjacentTilesSelector$$Select         -> battleQuery.<slot 0x50>(t, false, true, true)
BattleQuery.<IterateAdjacentTiles>d__95$$MoveNext
  = foreach t in EntityExtensions$$IterateTiles(from) : foreach n in tileQuery.IterateAdjacentTiles(t, …)
```

Le slot **80 = 0x50** est LU dans `data/symbols/<build>/metadata/interface_slots.tsv`
(`IBattleQuery 80 IterateAdjacentTiles 4`), pas déduit du nom. Et
`BattleQuery$$GetAdjacentTiles(from, …)` est `new OrderedSet(6); AddRange(IterateAdjacentTiles(…))`
— la matérialisation exacte du même itérateur. **Un seul substrat.**

### 3.3 Reste la CAPTURE, et le capteur vise ce qu'elle perd

Deux écarts séparent ce que le sélecteur voit de ce que le port lit :

* **les ARGUMENTS** — `onlyWalkableTiles` vaut `true` pour le sélecteur, `false` pour `boardGraph`.
  Le graphe est donc un SUR-ensemble : cet écart ne peut pas faire *manquer* une arête ;
* **la REPROJECTION**, qui le peut. `boardGraph` remappe chaque voisin en `(col,row)`
  (`idByCoord.get(…)`) et **jette en silence** celui qu'il ne sait pas remapper — aucun compteur,
  aucune trace. L'arête disparaissait du graphe et se lisait ensuite « le natif n'a pas cette
  arête », ce qui est exactement le symptôme mesuré sur `C3_14`.

Le RPC `adjacentTilesNative` publie les voisins **par entityId ET (col,row)**, sans en jeter un,
dans les deux régimes d'arguments, plus le `ConnectivityComponent` brut et l'empreinte de
l'origine — et il accepte une **unité** comme origine, ce que `boardGraph`, indexé par tuile, ne
sait pas faire alors que le sélecteur part de `Owner`. `boardGraph.adjUnmapped` rend la perte
visible là où elle était muette. Aucun `Interceptor` : on invoque la fonction nommée.

`diag.unmappedNeighbours > 0` **est** le verdict cherché. Zéro partout dit l'inverse — et alors
c'est la mesure de la fiche qu'il faut reprendre, pas le capteur.

---

## 4. `#419-r6-r1-r1` — la lambda, et pourquoi PAS `CalculateUtility`

Le corps de `SortUnitsByDamageUtilitySelector$$Select` termine par
`OrderBy(<liste source>, new Func(<DisplayClass9_0>, <Select>b__0)) -> ToList()`, et la lambda est

```csharp
// SortUnitsByDamageUtilitySelector.u003Cu003Ec__DisplayClass9_0$$u003CSelectu003Eb__0(this, unit)
return -this.<+0x28 = Dictionary<IEntity, Fix64>>[unit];
```

C'est **exactement** la clé de tri, unité par unité, lue du dictionnaire que la boucle a rempli
avec le retour d'`IdunBattleLogic.AI.Utilities.UtilityDecider$$CalculateUtility`.

On ancre la LAMBDA, pas `$$CalculateUtility`, pour deux raisons mesurées :

1. `$$CalculateUtility` est une **définition générique**
   (`...$$CalculateUtilityu003C__Il2CppFullySharedGenericTypeu003E`) : `findMethod` y rend le thunk
   d'invocation, pas le corps partagé (#259-b) — le piège du hook `enabled` à **0 fire** ;
2. son corps gshared est partagé par **tout** le décideur d'utilité de l'IA. L'ancrer poserait un
   trampoline sur un chemin chaud pour n'en garder qu'une fraction infime. La lambda a **deux**
   xrefs dans tout le binaire, les deux dans ce sélecteur.

La classe imbriquée est résolue **par son déclarant** (`class_get_nested_types` sur
`SortUnitsByDamageUtilitySelector`) : `<>c__DisplayClass9_0` est un nom court que le compilateur
génère une fois par méthode à closure — `findClassAnywhere` rendrait la première trouvée, sans la
moindre erreur.

`$$Select` est ancré en plus pour **délimiter les sessions** et publier l'ORDRE natif rendu : sans
lui, les paires de deux casts successifs se mélangeraient et « l'utilité par cible » perdrait le
seul contexte qui la rende interprétable.

Le `.ctor` du sélecteur, LU, donne les slots :
`+0x10 state · +0x18 targets · +0x20 caster · +0x28 ability · +0x30 utilityDefinition ·
+0x38 utilityDecider · +0x40 damage · +0x48 hits · +0x50 battleQuery`.

---

## 5. `#510-r2` — CORRIGÉ, et la conséquence mordante n'était pas la ligne

`IdunBattle.Core.Services.BattleQuery$$GetTilesBehind` pose
`dir = IdunBattle.Utils.Hex.CubeCoordinate$$DirectionTo(cube(from), cube(to))`, qui fait
`Max(Min(delta, 1), -1)` **par composante**, puis avance par `next = cur - dir`. Le mirror posait
`dir = cube(to) - cube(from)` **sans clamp**. Identique quand `to` est adjacent — le régime de trois
des quatre call-sites natifs et de tous les montages joués — faux au-delà.

**La conséquence mordante n'est pas la ligne, ce sont les gates.** Les tuiles sautées n'étaient
jamais soumises à `tile_exists` (bord de plateau) ni à `TileUtil$$IsTileValidForList` (mur,
élévation) : la ligne **traversait un mur sans s'arrêter**. Dégradation PERMISSIVE, silencieuse.

Le correctif passe par le foyer `battle_query.direction_to`, déjà exact, plutôt que de
re-transcrire le clamp — deux transcriptions du même natif, c'est deux endroits où il peut devenir
faux, et c'est la cause même de ce résidu.

**Consommateurs re-confrontés AVANT le correctif**, re-dérivés du code et non recopiés de la
fiche : les deux SEULS appelants effectifs sont `engine/playbook/excruciating_frequencies.py`
(DÉCISION) et `engine/entities/selectors/geometry.py::TilesBehindInLine` (COMBAT).
`loki_custom.py` n'appelle **pas** ce foyer (il passe par
`get_minimum_tiles_180_behind_from_tile`). `unstoppable_momentum._first_step` reste : il devient un
no-op EXACT une fois le clamp posé.

**Contre-épreuve jouée** contre l'ancien corps : **3 étages sur 4 ROUGES**, verbatim
`[(2, 5), (2, 8), (2, 11), (2, 14)]` là où le natif rend `[(2,3), (2,4), (2,5), (2,6)]` ; le
quatrième (value-preserving sur cible adjacente) reste **VERT** — c'est ce qu'on lui demande de
montrer.

**Après correctif** : offline `28 passed` ; live `test_dark_talon_strike_live` **2 passed**,
`test_unstoppable_momentum_live` **9 passed**,
`test_dark_talon_beam_direction_decision_live` **1 passed**.

---

## 6. `#589-r1-r1-r2-r1-r2` — la mesure TIENT, la conclusion NON

Re-dérivée sur le gameconfig **versionné du build courant** (683 unités : 127 `lineup`, 491 `npc`,
65 `summons`) : **59** portent `Summon`, **2** portent `Decoy` (`genesDecoy`, `genesSmnDecoy`, tous
deux `['Steppable','Decoy']`), et **0** porte les deux. La mesure de la fiche est donc confirmée.

**Mais sa conclusion — « régime inatteignable, quirk lu, non confronté » — est FAUSSE.** Le natif
ne lit pas le gameconfig : `UnitsWithTrait` teste
`IdunBattle.Entities.UnitExtensions$$HasFlag(unit, trait)`, donc le substrat d'ENTITÉ
`BC.Units[].Traits` → `BaseUnitComponent` (#264) — exactement le champ que le montage du probe
**écrit déjà** pour piloter `n`. Poser les deux traits sur le même compagnon arme le régime, sans
aucun porteur natif :

```
python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 1 --level 3 --trait Summon,Decoy
```

et la réduction attendue est celle d'un bras `--n 2 --trait Decoy` (le quirk : `SelectUnion` =
`AddRange; AddRange`, le compagnon compte deux fois). Le résidu n'est donc **pas à parquer** : il
est CONFRONTABLE par le montage déjà écrit, et ce bras n'a **pas** été joué ici (budget).

`--trait` accepte désormais une liste et **refuse** tout trait hors des deux comptés : un trait
inerte ferait tomber `n` à zéro sans qu'aucune assertion ne désigne la cause.

Le cliquet de réouverture est `test_589r1r1r2r1r2_union_non_dedupliquee_offline.py` (3 étages) : il
rougit le jour où un build ajoute un porteur des deux traits — le quirk devient alors observable
**sans** montage. Sa prémisse est assertionnée (un catalogue vide rendrait un ensemble vide, donc un
VERT qui ne mesure rien).

---

## 7. `#510-r3` — le premier verrou est LEVÉ, et il RÉFUTE la cause candidate

Le résidu nommait un verrou explicite : « NON ÉTABLI : que le playbook interrogé passe par
`PredictNormalAttack` (les deux `PredictAttack` sont des forwarders PURS, sans cache) ». Les trois
corps du décorateur ont été relus :

| symbole | accès au cache (`this+0x18`) |
|---|---|
| `IdunBattleLogic.Core.Services.Caches.CachedDamagePrediction$$PredictAttack` (2 params) | **aucun** — forward pur vers le slot 4 de l'inner |
| `…$$PredictAttack` (6 params) | **aucun** — forward pur vers le slot 5 |
| `…$$PredictNormalAttack` | `TryGetValue` puis `set_Item` — **le seul** |

La clé lue au corps : `(<id de l'arg 2>, <id de l'arg 4>, <arg 3>)` — le triplet
`DamagePredictionKey(attackerId, attackerPosition, secondEntityId)`, sans PV ni effets, conforme à
la fiche.

Et la chaîne du playbook passe par `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction`,
qui appelle le **slot 4** = `PredictAttack` (lecture indépendante, `case-419-r6-r1` §1.2).

⇒ **Le cache est hors de cause sur ce chemin.** Le « 0,70 constant dans trois régimes » n'est pas
une entrée périmée. Le résidu reste OUVERT, mais sa cause candidate est éliminée et la direction
change : la dégradation hors-tour porte sur le gate
`HealthPctIsBelowOrEqual(Target, ConfigConst(0x4f = healthPct))` qui rend FAUX hors-tour alors que
`target` est un pass-through intégral (établi par `#510-r1`). Le champ que
`CalculateAttackerModifiersForPrediction` écrit ET qui dépend du tour est `+0x50 activePlayer`
(`StateExtensions$$GetCurrentPlayer`) : c'est la prochaine hypothèse à instruire, et elle n'est pas
mesurée ici.

La contre-épreuve que la fiche décrit reste valable et ne coûte aucun runner neuf (prédire → muter
les PV **sans appliquer d'opération** → re-prédire) : elle départage maintenant « cache » (réfuté
par lecture) de « contexte de tour » (la piste restante). Elle **n'a pas été jouée**.

---

## 8. FENÊTRE DE REINJECT — ce qu'il faut jouer, capteur par capteur

Après chargement du bundle (`autoBootExtraire({force:true})` si la session est froide) :

### 8.1 `#419-r1-tr10-r2` — l'empreinte

```
python probe_419r1tr10r2_multi_tuiles_canal.py --state-file <ABS propre> --mow adeptExorcist
```

Verdict attendu : `CANAL PRESENT` avec **> 1** tuile. ⚠ Le probe cherche la MoW dans
`decisionView.units`, où elle **n'est jamais** (canal `.mows` séparé) — et elle est **hors plateau
au pas 0**, donc le montage exige de jouer le déploiement. Le canal se lit plus directement par

```
python -c "import rl_collect_batch as R; ..."   # decisionView -> units[].feet / mows[].platformTiles
```

Critère binaire : au moins une entité dont `feet` (ou `platformTiles`) porte **plus d'une** tuile.
Non-régression : sur une unité mono-pied, `feet == [MainTile]` et
`adjacency.iterate_tiles` rend exactement ce qu'il rendait avant.

### 8.2 `#589-r1-r1-r2-r1-r4` — l'adjacence native

Le montage de la mesure d'origine : board `C3_14`, porteur en `(5,4)`, compagnon en `(5,3)`.

```
RPC adjacentTilesNative {"runnerId": <rid>, "tiles": [{"col":5,"row":4}, {"col":5,"row":3}]}
RPC adjacentTilesNative {"runnerId": <rid>, "entityIds": [<id du porteur>]}
RPC boardGraph          {"runnerId": <rid>}      # lire diag.adjUnmapped
```

Critère binaire : `origins[0].byRegime.selector.tiles` contient-il `(5,3)` ?
* **oui** ⇒ la capture `boardGraph` est incomplète ; `diag.unmappedNeighbours` et
  `boardGraph.adjUnmapped` disent de combien et où. Résidu FERMÉ, correctif dans le remapping ;
* **non** ⇒ le natif ne compte pas ce voisin par CE chemin, et c'est la mesure de `case-589` §6
  (qui infère « le natif compte » depuis l'ACTIVITÉ de l'effet) qu'il faut reprendre.

### 8.3 `#419-r6-r1-r1` — l'utilité par cible

Montage de `case-419-r6-r1` §1.4 : Doombolt `1102` / `thousAhriman` / `MC1_67` / seed 31337,
`--crit 100,700`, armure nulle, trois rôles d'utilité distincts.

```
RPC sortUtilityTrace {"action":"arm"}          # verifier resolution.{select,lambda} == true
<jouer le cast qui declenche le selecteur>
RPC sortUtilityTrace {"action":"read","clear":true}
```

Critère binaire, à jouer **deux fois** — une avec `--crit 100,700` (le flag `MightCrit` est posé),
une en `--no-bis-items` (le témoin, où `CouldCrit` est faux) :
* `pairs[].utility` **identiques** entre les deux régimes ⇒ l'étage neutralisant est **en aval** de
  la prédiction (le décideur, ou l'utilité) ;
* `pairs[].utility` **différentes** alors que `sessions[].ordered` ne bouge pas ⇒ la neutralisation
  est dans le **tri** (égalités, arrondi de la clé).

`diag.lambdaFires == 0` avec `resolution.lambda == true` = le sélecteur n'a pas été traversé : le
montage n'a pas déclenché ce chemin, ce n'est **pas** un verdict.

⚠ `disarm` avant de rendre la main : les deux `Interceptor` restent posés sinon.

---

## 9. Ce qui n'est PAS couvert

* **Les trois capteurs n'ont FIRÉ nulle part** — aucune injection n'a eu lieu, aucune ne pouvait
  avoir lieu. « NON CONFRONTÉ — capteur livré, fenêtre à planifier ».
* **Le bras UNION de `#589-r1-r1-r2-r1-r2` n'est pas joué** : il est armé (`--trait Summon,Decoy`)
  et confrontable sans fenêtre, mais il coûte trois runners que cette tranche n'a pas dépensés.
* **`#510-r3` reste ouvert** : la cause candidate est réfutée, la suivante (`+0x50 activePlayer`)
  est nommée et **non mesurée**. La contre-épreuve sans runner neuf n'est pas jouée.
* **`#419-r1-tr10-r2` : le mirror reste inerte tant que le capteur n'a pas firé.** Le repli sur la
  MainTile est value-preserving sur toute unité à un pied — c'est-à-dire partout sauf les MoW.
* **L'écart `!inner.Contains(n)` (§2.4) n'est pas porté**, et il est mesuré NEUTRE sur les trois
  consommateurs actuels. Un futur consommateur dont `origin` rend des TUILES le rendrait mordant.
* **`test_510r2_tiles_behind_clamp_offline.py` n'entre pas dans l'empreinte `#457`** : l'obligation
  `--measure-missing` est SUSPENDUE par décision de l'utilisateur, donc le fichier se rejouera sous
  `--since`. Signalé, pas contourné.
