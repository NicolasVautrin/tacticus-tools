# #443-r1c — `probe_193c` retranchait des indices de feuille PÉRIMÉS

**Statut : LIVRÉ (2026-08-02).** Bug corrigé ; le gisement balayé rend **0 autre site** ;
cliquet `probe_443r1c_ordinal_index_perime.py` posé sur la forme, avec sa preuve de morsure.

## 1. Le bug

`scripts/python/probe_193c_move_playbook_terms.py:234` :

```python
p_x = p_tot - leaves.get(8, 0.0) - leaves.get(9, 0.0)      # 8=Elevation 10=TileEffects
```

`8` et `9` sont les ordinaux de `gqfc5mff6c`. Depuis l'insertion d'`AttackTile` en 8 (#252,
`Elevation` 8→9, `TileEffects` 9→10), re-dérivée de `data/symbols/rnca9r7q6c/frida/enums.tsv` :

| ordinal | `gqfc5mff6c` | `rnca9r7q6c` |
|---|---|---|
| 8 | `Elevation` | `AttackTile` |
| 9 | `TileEffects` | `Elevation` |
| 10 | `UnitEffectsAdjacent` | `TileEffects` |

Effet **mesuré** : `leaves.get(8)` désigne `AttackTile`, **absent de `TILE_LEAVES`** → rend
`0.0`, un no-op ; `leaves.get(9)` retranche `Elevation` — juste **par coïncidence** du décalage
+1 ; et `TileEffects` n'est **jamais** retranché. Or le membre natif de la comparaison l'exclut
(`X_natif = Tile(7) − Elevation − TileEffects`). Les deux côtés ne portaient donc pas la même
somme. L'écart est **nul tant qu'aucune tuile candidate ne porte d'effet** — d'où la survie
silencieuse, et d'où le fait que le probe « passait ».

**Correction** : clés en MEMBRES (`int(UtilityType.Elevation)` / `.TileEffects`), la règle que
`TILE_LEAVES` impose déjà par assertion depuis #254. Une renumérotation future est sans effet.

## 2. Pourquoi `probe_283` ne l'a pas vu — deux angles morts, mesurés

1. **`--step exec` ne visite que `ast.Subscript`.** Un indice passé par ACCESSEUR
   (`.get` / `.pop` / `.setdefault`) n'est servi par aucun de ses motifs (`visit_Call` ne sert que
   les signatures POSITIONNELLES dérivées, et `get` n'en est pas une). S'y ajoute que son
   heuristique `_root_of` lit le **nom du récepteur** : `leaves` ne porte aucune racine `_ROOTS`.
2. **`--step prose` écarte les membres AMBIGUS** — présents dans plusieurs enums à des ordinaux
   différents — quand la ligne ne NOMME pas l'enum (étape 4), et **inconditionnellement** en 4bis.
   `Elevation` est ambigu : `IdunBattle.Configuration.UtilityType` = 9,
   `IdunBattle.Core.Services.DamageModifierSource` = 0, `idun.meta.ObscuringType` = 2.

**Le vice qui a fait durer le bug : le commentaire s'auto-atteste À MOITIÉ.** Mesure directe sur la
ligne fautive — l'étape 4, enum non nommé, rend `[('TileEffects', '10')]` : sa moitié **juste** est
vue et comptée parmi ses ~1200 citations justes, pendant que sa moitié **fausse** (`8=Elevation`)
est structurellement invisible. Le rapport de couverture était donc **vert sur une ligne à moitié
fausse** — pire qu'un silence.

> Confirmation croisée, obtenue par accident : la docstring de `probe_443r1c`, qui **reproduit** la
> ligne fautive, **fait rougir** `--step prose`. La seule différence avec l'original est qu'elle
> NOMME `UtilityType` — ce qui lève l'écart des ambigus. Exactement le mécanisme ci-dessus. D'où
> son entrée à l'`ALLOWLIST` de `probe_283`, même précédent que
> `test_enum_ordinal_ratchet_offline.py` : ses citations périmées **sont** les données du détecteur.

## 3. Le balayage — ce qu'il couvre, et ce qu'il ne peut pas voir

Périmètre : `scripts/python/**`, **1518** fichiers, **8612** indices littéraux entiers
(8527 `[]`, 69 `.get`, 4 `.pop`, 0 `.setdefault`). Trois angles :

| angle | ce qu'il cherche | résultat |
|---|---|---|
| A | accesseur `.get/.pop/.setdefault(<lit>)` sur récepteur nommé `_ROOTS` (le trou syntaxique pur) | **0 site** |
| B | indice littéral dont la PROSE de la ligne cite un membre des enums renumérotés | **1 périmé** (le nôtre), 7 bénins |
| C | dict prouvé keyé par un membre d'enum, relu par littéral | non instrumenté — voir résidu |

**Le zéro de l'angle A est un vrai zéro** : la contre-épreuve sur l'état fautif fait passer B de
0 à 1 périmé, donc le détecteur mord. Un zéro non contre-épreuvé n'aurait rien valu.

**Ce que le balayage NE VOIT PAS**, et il faut le dire : un `leaves.get(8)` **sans commentaire**
reste invisible à tout balayage syntaxique — rien dans la source ne dit alors que `leaves` est
keyé par un ordinal d'enum. C'est le résidu **`#443-r1c-r1`**. Le seul remède général est
d'écrire les clés en MEMBRES ; il ne se garde pas, il s'impose à l'écriture.

## 4. Le cliquet — `probe_443r1c_ordinal_index_perime.py`

**Critère** : un indice littéral `v` est rouge si un membre `m` cité dans la prose de sa ligne
valait `v` sur le build archivé et ne le vaut plus, **et** que `m` ne vaut `v` dans **aucun** enum
du build courant. C'est cette seconde clause qui rend l'ambiguïté inoffensive et permet d'aller là
où 4bis renonce : un nom ambigu n'est écarté que s'il existe une lecture **actuelle** qui justifie
le nombre. Même raisonnement que 4bis, rendu décidable membre par membre au lieu d'être abandonné
en bloc. Périmètre **dérivé** du diff entre builds — aucune liste saisie, aucune allowlist.

**Étape 0 = auto-test dans le verdict** (modèle `probe_440`) : la faute exacte de #443-r1c doit
rougir par ses **deux** angles, ses voisines légitimes doivent rester muettes. C'est le résidu
`#439-r1` (« rougit sur SON gisement », et pas seulement « peut rendre un code non nul ») fermé
pour cette entrée.

**Mesures (2026-08-02)** — à re-dériver, pas à citer :

- dépôt propre : **0 rouge** ; état fautif : **rc=2**, les deux angles ;
- pré-filtre exact (fichiers citant un membre décalé) : **47,7 s → 23,3 s**, 683/1518 fichiers
  retenus, verdict identique dans les deux sens, contre-épreuve jouée sur le dépôt **réel** ;
- **coût marginal en parallèle : nul.** Mur de la banque **avec** = 88,3 s, **sans** = 79,2 s puis
  94,1 s : l'entrée n'ordonne pas la mesure, et `probe_443r1c` (55,4 s) reste loin sous le mur, tenu
  par `probe_319` dans les trois passes.

`probe_283 --step exec` gagne au passage la forme ACCESSEUR, symétrique de `visit_Subscript`.
Mesurée à **0 site** : elle ferme la forme, elle ne rattrape rien — ce qui a rattrapé #443-r1c,
c'est `probe_443r1c`.

## 5. Résidus

- **`#443-r1c-r1`** — un indice littéral **sans citation en prose** est invisible à tout balayage
  syntaxique (cf. §3). Non gardable ; se prévient à l'écriture (clés en membres).
- **`#443-r1c-r2`** — l'`ALLOWLIST` de `probe_283` exempte le fichier **entier**, pour
  `probe_443r1c` comme pour le témoin existant. Une vraie faute future y serait donc muette côté 283
  (côté 443, son auto-test la verrait). Granularité ligne non instrumentée.
