# Les trois capteurs de la face DÉCISION, CONFRONTÉS — un canal armé, deux résidus retournés, une lecture qui saturait

`#419-r7`. Build `rnca9r7q6c`, session Frida 65, bundle **déjà chargé** (aucune (ré)injection).

| résidu | verdict | par quoi |
|---|---|---|
| `#419-r1-tr10-r2` — empreinte multi-tuiles | **FERMÉ** — canal PRÉSENT, 3 tuiles lues, voisinage 6 → 7 | `probe_419r1tr10r2_multi_tuiles_canal.py --summon` |
| `#589-r1-r1-r2-r1-r4` — adjacence native | **le capteur répond, et il répond NON** — les DEUX lectures du résidu éliminées | `probe_589r1r1r2r1r4_adjacence_native.py` |
| `#419-r6-r1-r1` — utilité par cible | **volet ORDRE mesuré (prémisse RÉFUTÉE) ; volet CLÉ non mesuré — lecture SATURÉE, correctif livré** | `probe_419r6r1r1_sort_utility_trace.py` |
| `#589-r1-r1-r2-r1-r2` — union non dédupliquée | **CONFRONTÉ, quirk CONFIRMÉ en live** | `probe_589r1r1r2r1_amulet_crit_reduction_live.py --trait Summon,Decoy` |

---

## 1. `#589-r1-r1-r2-r1-r2` — le bras UNION n'était PAS jouable, et c'est l'outil qui bloquait

La fiche le donnait « armé (`--trait Summon,Decoy`), confrontable sans rien de spécial ». **Il
échouait au build** :

```
[error] --unit-stat: valeur non-JSON pour genesMagus.Traits: '["Summon"'
```

`rl_duel` découpait les champs de `--unit-stat` par un `fields.split(",")` naïf, donc
`Traits=["Summon","Decoy"]` partait en deux morceaux dont le premier n'est pas du JSON. La limite
était **documentée** (« pas de virgule DANS une valeur ») mais elle interdisait exactement le seul
montage qui arme le régime. Foyer : `_split_hors_json` — profondeur `[]`/`{}` + état chaîne, un
séparateur n'en est un qu'à profondeur 0 hors chaîne.

**Mesure, une fois le montage jouable** — deux bras, même seed / board / géométrie :

| bras | compteur du port | `bonus_signe` | LIVE | `NOCHANNEL` (témoin sans réduction) | accord |
|---|---|---|---|---|---|
| `--trait Decoy` | **1** | −432 | `[2493, 2636, 2377, 2537]` | `[3703, 3661, 2679, 2971]` | **True** |
| `--trait Summon,Decoy` | **2** | −864 | `[2568, 2438, 2074, 2456]` | `[3703, 3661, 2679, 2971]` | **True** |

Le `NOCHANNEL` est **identique** dans les deux bras — même seed, mêmes rolls, même montage — et le
LIVE **diffère**. Un seul compagnon est adjacent dans les deux cas. Le natif compte donc **deux
fois** l'unité qui porte les deux traits, et le port le mirrore : `TargetsSelector$$op_Addition` →
`CombinedSelector` mode 1 → `CombinedSelector$$SelectUnion` = `AddRange; AddRange`, sans
dédoublonnage. Le quirk était **lu** ; il est maintenant **confronté**.

---

## 2. `#419-r1-tr10-r2` — le porteur n'était pas celui qu'on cherchait

La §8.1 prescrivait de viser une **MoW** (`adeptExorcist`). Deux mesures l'écartent :

* une MoW est **hors plateau** — `decisionView.mows[].pos = null` sur `MC1_67` **et** sur le board
  MoW-capable `C1_02`, une seule ligne `mows`, `feet = []` et `platformTiles = []`. Le capteur ne
  publiait rien parce qu'il n'y avait **rien à publier** ; ce n'est pas un verdict ;
* `platformTiles` **ne peut pas dépasser une tuile**, et la prémisse qui le justifiait est fausse
  (§5 ci-dessous).

**Le porteur multi-tuiles réel est un SUMMON.** `ultraDreadnought` (MoW du pool) caste
`DutyEternal` et fait apparaître `ultraSmnDreadnought` **sur 3 hexes** — une `EntityType.Unit`,
donc l'un des trois types qu'`EntityExtensions.<IterateTiles>d__17$$MoveNext` reconnaît, contrairement
à l'`EntityType.Machine`. Mesure :

```
summon u77 ultraSmnDreadnought pos=(1, 2)
  feet                                  = [(0,2), (1,3), (1,2)]        <- 3 tuiles
  scene.feet_by_id[77]                  = [(0,2), (1,3), (1,2)]
  adjacency.iterate_tiles(u77)          = [(0,2), (1,3), (1,2)]  card 3
  adjacency.adjacent_positions          = 7 tuiles
  (repère) voisinage sur la MainTile    = 6 tuiles
  non-régression mono-pied              : 7 unités mesurées, 0 écart
```

Le mirror n'est donc plus inerte : il **change le résultat observable** (6 → 7 tuiles de
voisinage), et il ne change rien là où il ne doit rien changer.

**Un deuxième blocage, dans le probe** : il interrogeait `build_predictor` seul — les tables
**COLD** (`combatSnapshot`), qui ne portent **aucun** `feet_by_id`. L'empreinte est DYNAMIQUE et
vit dans `step_context(predictor, dv)` : exactement la raison pour laquelle le capteur a été posé
sur `decisionView` plutôt que sur `combatSnapshot`. Mesure de l'écart : `scene.feet_by_id` rendait
`0 entrée` alors que le hook publiait bien ses trois tuiles — un canal **présent** qui se lisait
**absent**.

---

## 3. `#589-r1-r1-r2-r1-r4` — le capteur répond, et il répond NON

Board `C3_14`, origine `(5,4)`, régime `selector` (les arguments EXACTS d'`AdjacentTilesSelector$$Select`) :

```
selector count=5 : (5,5), (6,4), (6,3), (4,3), (4,4)      <- (5,3) ABSENT
graph    count=5 : (5,5), (6,4), (6,3), (4,3), (4,4)      <- identique
connectivity     : [62, 70, 69, 51, 52]                   <- l'id de (5,3) est 60
diag.unmappedNeighbours = 0     |     boardGraph.diag.adjUnmapped = 0
```

Les **deux** lectures que le résidu laissait ouvertes sont éliminées :

* **la capture n'est pas incomplète** — `unmappedNeighbours = 0` et `adjUnmapped = 0`, et
  `connectivity` == `neighbours` == ce que rend le sélecteur ;
* **l'écart d'arguments ne mord pas** — `selector` (`onlyWalkableTiles = true`) et `graph`
  (`false`) rendent le MÊME ensemble.

Et la mesure a été refaite **dans le montage `--geo-only` lui-même**, par `entityIds` (la forme que
prend l'appel quand le DSL passe `Owner`, `BattleQuery.<IterateAdjacentTiles>d__95$$MoveNext`
résolvant son `from` par `EntityExtensions$$IterateTiles`) :

```
porteur   u77 pos=(5,4) feet=[(5,4)]
compagnon u79 pos=(5,3) feet=[(5,3)]
effet actif côté NATIF = True
origine id=77 : selector count=5 : (5,5), (6,4), (6,3), (4,3), (4,4)     <- (5,3) TOUJOURS absent
```

⇒ **Les deux faits sont vrais et incompatibles par le chemin supposé.**
`AmuletOfTheVoidwyrm_CritDamageReductionEffect$$GetAdjacentFriendlySummonsAndDecoysCount` passe par
`DSLSelectors$$AdjacentFriends(Owner, 1, 3)` = `Friends(unit, Units(AdjacentTiles(unit), …) − unit, …)`,
qui ne peut pas rendre une unité dont la tuile n'est pas dans `AdjacentTiles(Owner)`. C'est donc la
mesure de `case-589-r1-r1-r2-r1` §6 — qui **infère** « le natif compte » depuis l'ACTIVITÉ de
l'effet, jamais d'une énumération — qu'il faut reprendre. Le capteur, lui, a répondu.

⚠ **Le même run montre un DÉSACCORD port/natif que la fiche donnait pour un accord.** Sur le bras
`--geo-only`, `compteur: 0` et `effet_actif_port: False` côté port contre `actif_natif: True`,
`accord=False`. La fiche §6 écrivait « le port aussi (`_within` filtre par
`hexgeo.distance <= radius`) : accord » — ce n'est plus vrai du port courant. Résidu ouvert
ci-dessous.

---

## 4. `#419-r6-r1-r1` — le capteur fire, et sa clé était une SATURATION

Le capteur **a firé** dans les deux bras : `selectFires: 1`, `lambdaFires: 4`. Le montage traverse
bien `SortUnitsByDamageUtilitySelector$$Select` — donc la mesure est **faite**, pas absente.

Mais les 4 paires des 2 régimes rendaient toutes `keyRaw = 9223372036854775807` = `Int64.MaxValue`.
**Cause, vérifiée numériquement** : `NativePointer.toString()` rend l'hexa NON SIGNÉ, et la clé de
tri est `-utilité` — toute utilité positive donne une clé négative, donc un hexa à bit de signe
posé, que `new Int64(...)` lit comme ~1,8 × 10¹⁹ et **rabat sur `Int64.MaxValue`** :

| utilité | clé Fix64 | hexa non signé | > `Int64.Max` ? |
|---|---|---|---|
| 13,243 | −56 878 251 900 | `0xfffffff2c1cac084` | oui |
| 83,241 | −357 517 372 686 | `0xffffffacc24dd2f2` | oui |
| 240,0 | −1 030 792 151 040 | `0xffffff1000000000` | oui |
| 172,122 | −739 258 360 922 | `0xffffff53e0c49ba6` | oui |

**4 sur 4.** Une utilité NÉGATIVE n'aurait pas saturé — la panne n'est donc visible que sur un
montage où toutes les utilités sont du même signe, ce qui est le cas nominal.

**La conséquence est le pire cas possible** : deux régimes qui diffèrent réellement se lisent
IDENTIQUES. Le critère binaire de la §8.3 (« utilités identiques ⇒ l'étage neutralisant est en
aval ») aurait donc été rendu VRAI **par une panne de lecture**.

Correctif : `raxToInt64` (`writePointer` puis `readS64` — réinterprétation des 64 bits en
complément à deux, sans arithmétique ni chaîne). Cliquet : `diag.keysAtInt64Max`, qui compte les
clés exactement égales à `Int64.MaxValue` — une valeur qui n'existe pas dans le domaine. Le probe
le lit **et** détecte la saturation directement sur `keyRaw`, pour rester valable sur un bundle
antérieur : il déclare alors le volet CLÉ **NON MESURÉ** au lieu d'en tirer un verdict.

### 4bis. Ce que l'ORDRE, lui, a mesuré — et il RÉFUTE la prémisse du résidu

`sessions[].ordered` ne passe par aucune conversion : il tient. Mesure :

| bras | `CouldCrit(owner)` | ordre natif | bit-exact vs live |
|---|---|---|---|
| `--crit 100,700` | `True` | `[83, 81, 85, 79]` | production **True**, contrefactuel **False** |
| `--no-bis-items` | `False` | `[83, 85, 81, 79]` | production **True**, contrefactuel **True** |

L'ordre natif **change** entre les deux régimes alors que seul le canal crit du caster a bougé, et
le port de production (qui LIT le flag) est bit-exact **dans les deux**. ⇒ **il n'y a aucun étage
neutralisant à chercher : le flag EST classant.** La prémisse du résidu (« le natif ne fait pas
entrer `MightCrit` dans ce classement ») est réfutée sur ce montage — ce qui rejoint #494-r1-r1,
par un canal indépendant.

⚠ **Et le probe le disait à l'envers.** `probe_419r6r1_face_decision.py` imprimait
« => le NATIF ne fait PAS entrer `MightCrit` » sous la condition
`exact_production and not exact_contrefactuel`. Le contrefactuel a **changé de sens** en #494-r1-r1
(il jouait « le port s'il LISAIT le flag », il joue « le port s'il ne le lisait PAS ») ; la
conclusion imprimée, elle, est restée celle d'avant. La MÊME mesure se lisait donc à l'envers.
Corrigé, avec les deux branches explicites.

---

## 5. `mows[].platformTiles` — inerte par construction, et non mordant

`projectMowsFull` agrège `proj.mows` par `machineId`. Or `projectMatchState` n'émet **qu'une ligne
par MACHINE** (`for (const [machineId, m] of machines)` ; `platformByMachine` garde la PREMIÈRE
plateforme comme ancre), et son propre commentaire le dit — « emit ONE row PER MACHINE ». Agréger
des lignes déjà uniques ne peut donc jamais rendre plus d'une tuile. La §2.3 de la case-doc des
capteurs affirmait l'inverse (« déjà publiée, éclatée en une ligne `mows[]` par plateforme`) :
cette prémisse est **périmée** par un correctif antérieur de `match-state.ts`.

**Ce n'est pas mordant** : une MoW est hors plateau, donc sans empreinte à publier, et le porteur
multi-tuiles réel est un summon, couvert par `units[].feet` (§2). Le commentaire du champ est
corrigé pour dire ce qu'il fait, et nommer ce qu'il faudrait faire (balayer les
`EntityType.MachinePlatform` sur place) *si* une MoW acquérait un jour une empreinte.

---

## 6. Ce qui n'est PAS couvert

* **Le volet CLÉ de `#419-r6-r1-r1` n'est pas mesuré** — le correctif vit dans `frida/hooks/**`,
  livré et **non injecté**. « NON CONFRONTÉ — correctif livré, fenêtre à planifier. » Le probe se
  rejoue tel quel une fois le bundle rechargé ; il rend déjà son volet ORDRE.
* **Le désaccord port/natif du bras `--geo-only`, et le chemin qui l'explique** (§3) : résidu
  `#589-r1-r1-r2-r1-r7`. Les deux sont **le même fait** vu des deux côtés — le port ne compte pas
  ce voisin, le natif le compte, et aucun des deux chemins d'énumération mesurés ne le rend. Les
  séparer en deux résidus ferait travailler deux fois sur une seule cause.
  (⚠ `-r5` et `-r6` étaient **déjà pris** sous ce parent : numéro re-demandé, pas choisi.)
* **Aucun test de garde neuf** n'est posé : les trois confrontations sont des **probes** (mesure),
  et deux d'entre elles rendent un verdict qui rouvre un résidu plutôt qu'il n'en ferme un —
  garder un comportement qu'on vient de déclarer faux serait le figer.
* **Un seul board par montage** : `C3_14` pour l'adjacence (celui de la mesure d'origine, choisi
  pour ça), `C1_02` pour le summon, `MC1_67` pour l'utilité. La généralisation géométrique n'est
  pas faite.
* **`platformTiles` n'est pas réparé**, seulement rendu honnête (§5) — le remplir n'aurait aucun
  observable aujourd'hui.
