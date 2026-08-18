# case-589-r1 — l'AVAL de `tilesMovedThisTurn`, mesuré consommateur par consommateur

`#589-r1`. #589 a rebranché `beeline_pathfinder` sur le `ConnectivityComponent` : le port rendait
**4** là où le natif enregistre **6**. La correction était validée sur SA face (le compteur) ; sa
fiche nommait deux trous — « l'effet aval sur le dégât des 4 consommateurs » et « la route `Fly`
pure sur un board à `Bridge` ». **Les deux sont fermés, et le second était FAUX en tant que
"probablement inerte" : la route `Fly` pure porte exactement le même bug de 50 %.**

---

## 1. Le recensement natif, RE-DÉRIVÉ — six call-sites, quatre porteurs

XREFS de `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn` (build `rnca9r7q6c`). Le nœud
construit un `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula`, dont `$$Calculate` rend
`ActorStatisticsComponent+0xf0` — **il n'existe aucun autre lecteur de ce champ**.

| # | call-site natif | forme lue | sujet | 4 → 6 change ? |
|---|---|---|---|---|
| 1 | `ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus` | `Multiply(ConfigVar(8 = extraDmg), n)` | `DSLSelectors+0x30` = Owner | **OUI — LINÉAIRE** |
| 2 | `ModifiedExoarmour_ExtraDmgEffect$$GetExtraDamageMultiplier` | `n` brut | Owner | OUI — linéaire |
| 3 | `ModifiedExoarmour_ExtraDmgEffect$$CreateActiveCondition` | `AmountIsGreaterThanZero(n)` | Owner | **NON** — seuil `0` |
| 4 | `EmpyricAmbushEffect$$IsValidAttackForBuff` | `AmountIsEqualOrGreater(n, Direct(GetNumberConstant(0x51)))` | `DSLSelectors+0x48` = Caster de l'attaque | **PEUT** — seuil `4` |
| 5 | `MastersOfManoeuvreAbility$$CreateTrigger` | `AmountIsEqualOrGreater(n, Get(GetNumberConstant(0x88)))` | `DSLSelectors+0x40`, sujet du `On(0x4)` | **NON** — seuil `2` |
| 6 | `SmashaEadAbility$$CreateTrigger` | `AmountIsEqualOrGreater(n, Direct(2))` | Owner | **NON** — seuil `2`, LITTÉRAL |

`0x51` / `0x88` sont résolus par `IdunBattle.Configuration.AbilityConstantType` (`81 = movement`,
`136 = tilesTraversed`) et leurs VALEURS relues du gameconfig — pas recopiées du décompilé.
Porteurs : `votanChampion` (1-3), `eldarLhykhis` (4), `darkaStormSpeeder` (5), `orksNob` (6).

⚠ **Le sujet n'est pas toujours le porteur.** Les call-sites 4 et 5 lisent le compteur d'une unité
TIERCE (le caster de l'attaque en cours ; le sujet de l'événement `On(0x4)`), donc potentiellement
un VOLANT — c'est ce qui les rendait candidats à un basculement.

## 2. La BORNE qui décide des seuils, et elle se DÉRIVE

`MovementQuery$$GetConnectedPathTo` ne recoud par une beeline QUE `if (GetDistance(last, next) > 1)`.
Le sous-chemin recousu compte alors au moins `d >= 2` arêtes — **dans les deux substrats**. Et
comme `N ⊆ C ⊆ G` (#584) donne `n_G <= n_C` :

    dès que le rebranchement peut mordre :  min(n_G, n_C) >= 2

⇒ **tout seuil `K <= 2` est déjà franchi AVANT le rebranchement** ; il ne peut pas basculer. Ça
sature les call-sites 3, 5 et 6 — par un mécanisme, pas par chance.

**Mesuré** (`--only SCAN`, `C1_74`, 63 tuiles, 3906 couples ordonnés × 4 régimes) :
`min(beeline)` = **2** en `G` comme en `C` ; et **aucun** seuil `<= 2` ne bascule, aucun régime.

## 3. Le RÉGIME décide avant le consommateur — mesuré par régime

Le rebranchement ne touche que la beeline, et la beeline n'est appelée que par
`GetConnectedPathTo`. Un chemin de `BasePathfinder$$FindPath` a tous ses nœuds adjacents : pour un
MARCHEUR la densification est un no-op et le substrat n'entre jamais en jeu.

| régime (`GetPathfinderTypeForUnit`) | `C1_74` (2 `Bridge`) | `C3_14` (15 `Bridge`) | seuil qui bascule |
|---|---|---|---|
| `Walk` (0) | **0 / 3906** | **0 / 3906** | aucun |
| `Fly` (3) | **106 / 3906** (`+1` : 104, `+2` : 2) | **943 / 3906** (`+1` : 423 … `+6` : 1) | `EmpyricAmbush` (K=4) : 22 / 262 |
| `TeleportStrike(Walk)` (6) | 110 / 3906 | 1992 / 3906 | `EmpyricAmbush` : 24 / 498 |
| `TeleportStrike(+Fly)` (7) | 110 / 3906 | 1992 / 3906 | `EmpyricAmbush` : 24 / 498 |

**Le second board n'est pas une redite : il change l'ORDRE DE GRANDEUR sans changer aucune des
trois conclusions.** `C3_14` porte 15 ponts contre 2, et l'écart `n_C - n_G` y monte jusqu'à `+6`.
Le `Walk` y reste à **0**, et seul `EmpyricAmbush` y bascule — donc l'inertie de la marche et la
saturation des seuils `<= 2` ne tiennent pas à la maigreur du gisement de `C1_74`.

## 4. Verdict par consommateur

### 4.1 `ModifiedExoarmour_ExtraDmg` (call-sites 1-3) — **INERTE, par le RÉGIME**

Son sujet est l'`Owner`, et son unique porteur `votanChampion` (<<Kimm>>) n'a ni le trait `Flying`
ni aucun des quatre effets `*_TeleportingIn` : il sort en `ptype = 0`.

**MESURÉ** (`--only TILES --unit votanChampion --inject`, `C1_74`, seed 777) : `ptype = 0` sur
toutes les activations, **6 mesures, accord CANAL 6, accord GÉOMÉTRIE 6**, dont un move partant du
`Bridge` lui-même. Aucun couple discriminant — et c'est le **résultat**, pas un défaut de montage :
le SCAN dit que le régime `Walk` n'en a aucun sur 3906.

⇒ le passage 4 → 6 **ne se produit jamais pour ce porteur**. L'aval de #589 ne le touche pas.

### 4.2 Le consommateur EST sensible — mesuré, pour ne pas conclure d'un régime dégénéré

« Pas d'écart » ne vaut que si l'on a montré que le consommateur AURAIT bougé. On a donc GREFFÉ
`ModifiedExoarmour` (`catalog_inject.write_grafted_seed_bc`, recette `case-92` §5bis) sur
`blackHaarken` — trait `Flying`, arme melee portée 0, 4 coups — et mesuré `aiPredict` après chaque
move, **à tuile d'attaque CONSTANTE** :

| tuile | n | `willKill` | `mightKill` |
|---|---|---|---|
| `(0,5)` | 2 | 6024 | 7440 |
| `(0,5)` | 3 | 7624 | 9036 |
| `(0,5)` | 4 | 9220 | 10632 |
| `(0,5)` | 5 | 10816 | 12232 |
| `(0,3)` | 2 | 9040 | 11160 |
| `(0,3)` | 3 | 11432 | 13556 |

Pente à tuile constante : **+1596 à +1600 par tuile** sur `(0,5)`, **+2392 à +2396** sur `(0,3)` —
le rapport `2396 / 1596 = 1.5` est le %-list de surplomb, pas un bruit.

**CONTRE-BRAS `--no-graft`** (obligatoire) : sans le passif, `willKill` vaut **2832** pour `n` = 2,
3, 4 **et** 5 — pente **0.0** sur les quatre paires et les deux tuiles. L'attribution du dégât au
compteur est donc établie, pas supposée.

### 4.3 L'AVAL, chiffré **sans aucun modèle** — trois couples discriminants

Les deux valeurs `n_G` et `n_C` ont été lues **sur la même tuile d'attaque**, donc l'écart est une
différence de DEUX MESURES :

| trajet | port AVANT #589 (`n_G`) | natif (`n_C`) | écart de dégât |
|---|---|---|---|
| `(2,4) -> (0,5)` | 2 → 6024 / 7440 | 3 → 7624 / 9036 | **+1600 / +1596** |
| `(3,4) -> (0,5)` | 3 → 7624 / 9036 | 4 → 9220 / 10632 | **+1596 / +1596** |
| `(4,3) -> (0,5)` | 4 → 9220 / 10632 | 5 → 10816 / 12232 | **+1596 / +1600** |

⚠ Ces chiffres valent pour le GREFFON, pas pour Kimm : la greffe ne transporte ni ses stats, ni
ses traits, ni ses armes. Ce qu'ils établissent est la **chaîne**, pas une valeur transposable.

### 4.4 `EmpyricAmbush` (call-site 4) — **PEUT basculer, mais NON PORTÉ**

Seul seuil au-dessus de la borne (`movement = 4`), et son sujet est le **caster de l'attaque**,
donc n'importe quel allié — volant compris. **Mesuré** : 22 couples de `C1_74` le font basculer en
régime `Fly`, 24 en `TeleportStrike`.

Côté port, l'ability n'a **aucun** trigger : le seuil n'est exercé nulle part, donc rien à
corriger aujourd'hui. Le cran offline `test_aucun_trigger_a_SEUIL_n_est_porte...` rougit le jour où
l'un des trois porteurs à seuil entre au registre — c'est ce qui rouvrira la question.

### 4.5 `MastersOfManoeuvre` / `SmashaEad` (call-sites 5-6) — **SATURÉS**

Seuil `2` des deux côtés, borne `n >= 2` : franchi avant comme après. Mesuré, 0 basculement sur
3906 couples × 4 régimes. `SmashaEadExtraDamageEffect` est porté côté EFFET, mais le trigger qui le
pose ne l'est pas — le seuil n'est donc pas exercé.

## 5. ITEM 2 — la route `Fly` PURE n'est PAS inerte

`fly_pathfinder` garde la GÉOMÉTRIE (override natif `FlyPathfinder$$AddNeighbours` →
`GetSurroundingTiles`), et c'est fidèle : il n'a **pas** été rebranché, à juste titre. Mais
`GetConnectedPathTo` recoud SES waypoints par la beeline, qui, elle, l'est. Un vol DIRECT se réduit
d'ailleurs à `[from, to]` (§3 de `case-448-r1-r1-r1-r1`) — exactement le régime `TeleportStrike`.

**MESURÉ** (`--only TILES --unit blackHaarken`, `C1_74`, seed 777) — 9 mesures :

| trajet | NATIF | port `G` | port `C` |
|---|---|---|---|
| `(1,5) -> (5,5)` | **6** | 4 | 6 |
| `(5,5) -> (1,5)` | **6** | 4 | 6 |
| `(1,5) -> (5,7)` | **5** | 4 | 5 |
| `(5,3) -> (1,5)` | **5** | 4 | 5 |
| `(1,5) -> (5,6)` | **5** | 4 | 5 |

**accord CANAL 9/9, accord GÉOMÉTRIE 4/9** (les 4 restants sont des témoins `G == C`, tous justes).
⇒ le rebranchement était **nécessaire pour la route `Fly` aussi**, et le port livré est juste. Avant
#589 un volant pur enregistrait 4 là où le natif en compte 6 : le **même écart de 50 %**.

**GÉNÉRALISÉ sur un SECOND board à `Bridge`** — `C3_14`, même porteur, 8 mesures, **accord CANAL
8/8, accord GÉOMÉTRIE 5/8** :

| trajet | NATIF | port `G` | port `C` |
|---|---|---|---|
| `(1,2) -> (5,3)` | **6** | 4 | 6 |
| `(5,3) -> (3,3)` | **4** | 2 | 4 |
| `(2,2) -> (4,2)` | **6** | **2** | 6 |

Le dernier couple porte un écart de **4 tuiles** — un facteur **3**, pas 1,5. La géométrie y coupe
par trois ponts d'affilée. C'est le rappel que « 287 boards à `Bridge` » ne dit rien de
l'AMPLITUDE : `C1_74` en est le cas le plus PAUVRE, pas le cas typique.

⚠ **C'est le montage qui a failli faire conclure l'inverse.** Un premier run a rendu « 5 mesures,
0 désaccord, accord CANAL == accord GÉOMÉTRIE » : le critère de discrimination était
`len({n_G, n_C, n_N}) > 1`, or sur `C1_74` les couples où seul `N` diffère sont bien plus nombreux
(58 arêtes contre 16) — ils noyaient le cas utile, et le porteur n'a jamais approché le pont. Le
discriminant d'un rebranchement `G -> C` est **`n_G != n_C`**, rien d'autre.

## 6. Deux pièges de mesure payés ici, et ils resserviront

1. **Le dégât dépend AUSSI de la tuile d'attaque.** La même valeur `n = 2` rend `6024` depuis
   `(1,4)` et `9040` depuis `(0,3)` — le %-list de surplomb. Une pente calculée sur des tuiles
   différentes mélange les deux effets et n'attribue plus rien. La mesure doit être indexée par
   **(tuile, n)**, et la pente calculée à tuile CONSTANTE.
2. **L'adjacence de JEU n'est pas `hexgeo.distance <= 1`.** `MovementUtil$$AreTilesAdjacent` vaut
   `(|Δelev| < 2) & ConnectivityComponent$$IsNeighbour` — c'est exactement le champ
   `neighbours_native`. Mesuré : depuis `(2,4)`, `hexgeo` donne `d = 1` vers `(1,5)` et le natif
   rend `pred: null` (`dictCount = 0`). Un montage qui vise l'adjacence géométrique perd ses
   mesures sans dire pourquoi.

Et un troisième, de MONTAGE : poser la cible SUR le pont ne sert à rien — ses seuls voisins de
connectivité sont ses deux voisins d'axe, donc tout strike y arrive par le chemin que les deux
substrats partagent. L'ancre utile est un voisin **géométrique et non connexe** du pont.

## 7. Les gardes

* `scripts/python/tests/engine/entities/pathfinding/test_589r1_tiles_moved_consumers_offline.py`
  — 7 crans. **Contre-épreuve jouée** : le mutant « beeline géométrique » (l'état d'avant #589)
  fait rougir les 3 crans de régime/borne ; le mutant « `walk_maps_by_pos` sur la géométrie » fait
  rougir le cran d'inertie de la marche, et lui seul.
  ⚠ Deux crans écrits d'abord **ne gardaient rien**, et c'est la contre-épreuve qui l'a dit :
  (a) interroger `pathfinders.find_path(Walk)` rend `None` par conception → la branche dégénérée
  `[from, to]`, donc `n = 1` quel que soit le substrat ; (b) un test qui compare deux MONTAGES est
  aveugle à une mutation qui frappe les deux — d'où les valeurs ABSOLUES ajoutées.
* `scripts/python/probe_589r1_tiles_moved_consumers_live.py` — 4 crans :
  `INV` (offline, recensement dérivé + seuils relus du gameconfig), `SCAN` (gisement et
  basculements par régime), `TILES` (le compteur natif vs les trois substrats, porteur
  paramétrable), `EXO` (l'aval du dégât, avec son contre-bras `--no-graft`).

## 8. Reproduction

    python probe_589r1_tiles_moved_consumers_live.py --only INV
    python probe_589r1_tiles_moved_consumers_live.py --only SCAN --board C1_74
    python probe_589r1_tiles_moved_consumers_live.py --only SCAN --board C3_14
    python probe_589r1_tiles_moved_consumers_live.py --only TILES --unit blackHaarken --turns 24
    python probe_589r1_tiles_moved_consumers_live.py --only TILES --unit blackHaarken \
        --board C3_14 --turns 20
    python probe_589r1_tiles_moved_consumers_live.py --only TILES --unit votanChampion --inject \
        --fillers necroWarden --turns 16
    python probe_589r1_tiles_moved_consumers_live.py --only EXO --turns 34
    python probe_589r1_tiles_moved_consumers_live.py --only EXO --no-graft --turns 24
    python -m pytest tests/engine/entities/pathfinding/test_589r1_tiles_moved_consumers_offline.py

## 9. Ce qui n'est PAS couvert

* ~~**`EmpyricAmbush` n'est pas confronté au natif.**~~ **FERMÉ** par `#589-r1-r1` (l'effet et son
  gate, seuil confronté à `movement = 4`) puis `#589-r1-r1-r2` (le PRODUIT avec le compteur
  rebranché, sur `C1_74` et `C3_14`). ⚠ La phrase « le porteur `eldarLhykhis` est au pool » était
  **FAUSSE** : elle est hors catalogue et s'injecte (`catalog_inject --missing`).
* ~~**`MastersOfManoeuvre`** : saturé par la borne, mais non confronté.~~ **FERMÉ** par `#589-r2`.
  Son trigger est porté depuis `#999-r1` (`MastersOfManoeuvrePlaceOnMove`), donc son seuil est
  **exercé** — ce qui a fait rougir, à raison, le cran offline et le cran `INV` ci-dessous. La
  saturation n'est plus déduite : **5253 couples divergents** sur `C1_74` + `C3_14`, **0 bascule**
  du gate porté, témoin non-nul à **1328**. Et l'hypothèse cachée de la borne (« la beeline trouve
  toujours un chemin ») est désormais **mesurée** au lieu d'être écartée en silence par `S1`.
  Détail : `docs/rl/case-589-r2-aval-masters-of-manoeuvre.md`.
* **Le sujet des sélecteurs 4 et 5** (`DSLSelectors+0x48` = Caster, `+0x40` = sujet du `On(0x4)`)
  est lu au décompilé et **non confronté live**. S'il était autre, la ventilation « le sujet peut
  être un volant » changerait — pas les verdicts, qui reposent sur la borne.
* **L'aval est mesuré sur le PREVIEW** (`aiPredict` → `GetAllPredictions`), pas sur le dégât
  INFLIGÉ. Le pont preview ↔ combat est porté et gardé ailleurs (#322 magnitude, #335 face combat) ;
  il n'a **pas** été rejoué ici.
* **Le gisement « 287 boards à `Bridge` » reste un ESTIMATEUR** (hérité de #589), mais il n'est
  plus adossé à un seul board : `C1_74` et `C3_14` ont été confrontés au natif (17 mesures, 8
  discriminantes, **17/17 CANAL**). Les 285 autres restent non confrontés, et le contraste entre
  les deux mesurés (106 vs 943 couples en `Fly`) dit que l'amplitude, elle, n'est pas estimable
  depuis un board.
* **La greffe ne transporte pas** les stats, traits et armes de `votanChampion` : les pentes
  chiffrées valent pour `blackHaarken` greffé.
* **`ModifiedExoarmour_ExtraDmgEffect$$GetExtraDamageMultiplier`** (call-site 2) : sa forme est lue
  (`n` brut, donc linéaire), mais **son consommateur natif n'a pas été identifié** — il n'a aucune
  XREF directe hors de la vtable. Classé linéaire par sa forme, pas par son usage.
