# #494 — `1102 Doombolt` : l'ordre des cibles, et les DEUX causes que le montage d'origine mélangeait

`test_doombolt_live.py` restait **VERT** alors que la 4ᵉ cible (celle à 0 coup) différait du natif.
Le test n'était pas aveugle : `test_doombolt_zero_hit_target_and_sort_order_live` faisait bien `N = 3`
sur **4** cibles et assertait l'ordre. Ce qui lui manquait est la **GÉOMÉTRIE** qui fait diverger le
tri — ses quatre cibles sont placées par le montage `db-4`, où l'accord tenait… par **compensation**
de deux erreurs (§5).

Mesures : `python scripts/python/probe_494_doombolt_sort_order.py --regime <A|B|C|I1..I5|J1|K1|L1..L3>`
et `python scripts/python/probe_494r1_db4_decompose.py [--egalise]`
(board `MC1_67`, seed 777 / 31337, build `rnca9r7q6c`, 2026-08-07).

## 1. La divergence, reproduite et décomposée

Géométrie de `case-487` §8 (régime `A`) : `thousAhriman@(3,3)`, `orksNob@(3,4)` (cible du message),
`orksWarboss@(4,4)`, `orksBigMek@(2,4)`, `orksRuntherd@(3,5)`.

| étage | mesure |
|---|---|
| 0 — régime | `hp = maxHp = 400000` partout (`--hp-target`, qui met aussi `Armor = FixedArmor = 0`) |
| 1 — ordre SOURCE du port (`DoomboltAbility$$GetTargets`, avant tri) | `[83, 85, 79, 81]` |
| 2 — utilité portée par cible | **les 4 EXACTEMENT ÉGALES** (`0.2992485038`) |
| 3 — ordre final PORT | `[79, 81, 83, 85]`, coups `[1,1,1,0]` → frappe `{79, 81, 83}` |
| 4 — ordre final NATIF (séquence d'évènements) | `[79, 81, 85, 83]` → frappe `{79, 81, 85}` |

Les utilités portées étant **toutes égales**, le classement du port était entièrement décidé par son
tie-break — et `sort_units_by_damage_utility` imposait `sorted(int(c) for c in candidates)`, l'ordre
par **id**. C'est là que portait l'écart, pas dans la répartition des coups (juste des deux côtés).

## 2. Le montage hétérogène MÉLANGE deux causes — et c'est lui qu'il fallait corriger d'abord

`orksBigMek` porte le trait **`Mechanic`** et POSE un `statDelta {fixedArmor: +1197}` sur ses
voisins. Mesuré, ligne `combatSnapshot` par ligne :

| régime | `orksBigMek` | `fixedArmor` résolu (79 / 81 / 83 / 85) |
|---|---|---|
| `A` | `(2,4)` | 1197 / **0** / 1197 / 1197 |
| `B` | `(4,3)` | 1197 / 1197 / 1197 / **0** |

**Déplacer UNE unité change l'ARMURE des autres.** Un A/B de position sur ce roster ne mesure donc
pas ce qu'il prétend mesurer. Et l'unité SANS le bonus est, dans les deux régimes, **la première du
classement natif** parmi les non-cibles : l'armure entre bien dans l'utilité native.

⇒ **Confirmation INDÉPENDANTE de `#527-r1`, sur une SECONDE ability**, et par un mécanisme
différent de celui qui l'avait établie. Le foyer accusé est le même — `_target_utility`
(`engine/runner/operations/damage_utility.py`).

## 3. Le régime PROPRE : N × `orksNob` identiques

Pour isoler l'ordre, les régimes `I*`/`J1`/`K1`/`L*` montent **N copies de la même unité** — mêmes
traits, mêmes stats, `statDelta` vide. Plus aucune stat de cible ne peut ordonner : ce qui reste est
purement géométrique.

**Réfuté par ces régimes** : l'ordre par id (ce que le port imposait), l'id décroissant,
`cube-lex (x,y)` seul, `cube-lex (x,y)` décroissant, `cube-lex (y,x)`, `cube-lex (z,x)`.

⚠ **Le probe s'est fait piéger par son propre critère, et c'est le vice de `db-4` transposé** : son
verdict portait sur la seule VICTIME, or `K1` (`N % C == 0`) n'en a aucune des deux côtés — il
rendait `ACCORD` sur un régime dont la séquence jouée DIVERGE. Le verdict porte désormais sur
l'**ORDRE JOUÉ** *et* sur la victime.

## 4. La loi de « rotation d'un cran » — mesurée sur 7 géométries, puis RÉFUTÉE (#494-r1)

Une loi compatible avec les 7 premières géométries avait été dégagée : l'énumération de tuiles
`cube-lex (x, y)` ASCENDANT, **rotée d'un cran vers la gauche**. Elle tenait y compris sur deux
prédictions hors échantillon (`J1` à 5 cibles, `K1` à 3, qui font varier `C` donc la RÉPARTITION).
Elle n'était attribuée à **aucun** étage natif — les sept étages de la chaîne avaient été lus et
préservent tous l'ordre (§6) — et c'est pourquoi elle n'avait pas été portée.

**Elle est FAUSSE.** Trois régimes qui font varier l'**ÉLÉVATION** et rien d'autre la contredisent
tous les trois (prédictions écrites AVANT la mesure) :

| régime | positions des cibles | élévations | ordre SOURCE | « rot-1 » prédit | NATIF joué |
|---|---|---|---|---|---|
| `L1` | `(3,4) (1,4) (2,4) (5,4)` | 3 3 3 3 | `[81, 83, 79, 85]` | `[79, 83, 85, 81]` | **`[79, 81, 83]`** |
| `L2` | `(3,4) (1,4) (2,4) (4,4)` | 3 3 3 **2** | `[81, 83, 79, 85]` | `[79, 83, 85, 81]` | **`[79, 85, 81]`** |
| `L3` | `(3,4) (1,2) (2,4) (5,4)` | 3 **2** 3 3 | `[81, 83, 79, 85]` | `[79, 83, 85, 81]` | **`[79, 81, 83]`** |

(caster `thousAhriman@(3,3)`, élévation 3 ; cible du message `u79`.)

`L1` est le témoin : à élévation **PLATE**, le natif rend l'ordre SOURCE **tel quel**. `L2` et `L3`
sont les épreuves : la seule cible plus BASSE que le caster remonte, et le reste garde l'ordre
source. La « rotation » n'était pas une loi d'ordre — c'était l'**OMBRE d'une clé de tri non
constante**, tous les montages de #494 ayant par hasard mélangé des élévations.

## 5. La cause, NOMMÉE : la clé est calculée PAR CIBLE, avec la POSITION DU CASTER

`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select`, lu intégralement :

```
units  = (+0x18).SelectUnits(entities, 3)          # l'ordre SOURCE du selecteur
owner  = (+0x20).SelectUnit(entities)              # dc+0x18
ownerP = EntityExtensions.GetUnitPosition(owner)   # dc+0x20  <-- LA POSITION DU CASTER
foreach u in units :
    pred    = IBattleQuery.<slot 0x26>(+0x50, owner, u, ownerP, ability, dmgMin, dmgMax, ...)
    dict[u] = UtilityDecider.CalculateUtility(UtilityDefinition(0x23 = UtilityType.Damage), u, pred)
return units.OrderBy(u => Fix64.op_UnaryNegation(dict[u])).ToList()
```

Deux conséquences, et ce sont les deux faces du résidu `#494-r1` :

1. **La prédiction est faite DANS la boucle, avec `ownerP`** ⇒ les feuilles POSITIONNELLES du builder
   partagé `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` —
   `…$$CalculateElevationBonusModifier` (« +`ElevationBonus` % si la tuile de l'attaquant est plus
   HAUTE que celle de la cible ») et `…$$CalculateTrenchReduction` — rendent la plage prédite
   **différente d'une cible à l'autre**, sans qu'aucune stat de cible n'ait bougé. L'en-tête du port
   affirmait l'inverse (« pré-armure ⇒ la PLAGE est la MÊME pour toutes les cibles ») : *pré-armure*
   n'implique pas *pré-géométrie*.
2. **`System.Linq.Enumerable.OrderBy` est STABLE** ⇒ à clé égale, l'ordre SOURCE ressort intact. Le
   `sorted(by id)` du port ne l'approximait pas : il le DÉTRUISAIT, en substituant un ordre source
   qui n'est pas celui du natif.

### `db-4` était un cas de COMPENSATION, et c'est ce qui l'a rendu lisible

Le montage historique `db-4` (4 visualId différents, PV NATURELS) a rougi dès que la part
positionnelle est entrée dans la clé. Décomposition à UNE seule variable
(`probe_494r1_db4_decompose.py`, même roster, même géométrie, même seed) :

| régime | `fixedArmor` | NATIF joué | PORT (clé positionnelle) |
|---|---|---|---|
| `db-4` | 2761 / 2662 / 1806 / 2161 | `[77, 81, 79]` | `[77, 83, 81, 79]` — DIVERGE |
| `db-4 --egalise` | 0 partout | `[77, 83, 79]` | `[77, 83, 79, 81]` — **ACCORD** |

Sur la MÊME géométrie, armures neutralisées, port et natif sont d'accord : `orksNob` (élévation 2,
seul plus BAS que le caster à 3) remonte en 2ᵉ position des deux côtés. Ce qui restait était donc
l'**armure** (`#527-r1`), pas l'ordre — et `db-4` passait parce que ses deux absences (armure ET
géométrie) se corrigeaient l'une l'autre sur cette configuration-là.

⇒ `db-4e` (égalisé) porte désormais la confrontation d'ORDRE ; `db-4` reste comme TÉMOIN de
`#527-r1`, en `xfail(strict=True)` — il repassera au vert le jour où l'armure entrera dans la clé,
et le xpass forcera à retirer le marqueur.

## 6. Ce qui a été lu, et qui préserve l'ordre

Aucun étage de la chaîne ne réordonne — c'est ce qui rend l'ordre SOURCE `cube-lex (x, y)`
attribuable :

* `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` — triple
  boucle CUBE, **`f0` en boucle EXTERNE, `f1` en boucle MÉDIANE**, filtre `f0+f1+f2 == 0`, émission
  `CubeCoordinate(f0, f1, f2)`. `IdunBattle.Utils.Hex.CubeCoordinate$$ToAxialCoordinate` fixe
  `col = f0` et `row = (f0 + (f0 & 1))/2 + f2` — l'énumération est `lex(x, y)` ASCENDANT, exactement
  ce que `hexgeo.disk` produit ;
* `IdunBattle.Core.Services.BattleQuery$$GetSurroundingTiles` — `OrderedSet.Add` dans l'ordre de
  l'itérateur, aucun tri (`OrderedSet$$Add` = `if (hashSet.Add(x)) list.Add(x)`, ordre d'insertion
  STRICT ; `$$AddRange` boucle dessus) ;
* `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select` — `OrderedSet.AddRange` ;
* `IdunBattle.DSL.CombinedSelector$$Select` → `$$SelectExclusion` (le `- Tiles(unit)` de
  `IdunBattleLogic.Entities.DSLSelectors$$SurroundingEnemies`, qui appelle `SurroundingTiles` avec
  `includeCenter = 1` puis retranche) — `foreach left : if (!right.Contains(x)) result.Add(x)` ;
* `IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select` → `IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits`
  — `ArraySet.Add` puis `ToList`, ordre d'insertion strict ;
* `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$Select` → `$$CountOrAdd` — `List.Add` filtré ;
* `IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$Select` — `List.Add` filtré ;
* `IdunBattleLogic.Entities.DSLSelectors$$Damageable` — `UnitsWithoutTrait(source, 0x40e, 3)`
  (`0x40e` = `UnitTrait.Invincible`).

Et l'ability finit par `list.Remove(actor); list.Insert(0, actor)` (`ICollection<T>` slot 6 /
`IList<T>` slot 3), donc la cible du message est toujours en tête et compte dans `C`.

## 7. Ce qui est PORTÉ, et ce qui ne l'est pas

Porté (`engine/runner/operations/damage_utility.py`) :

* **tie-break = l'ordre de `candidates`**, tel quel — mirror de la stabilité de l'`OrderBy`. La
  responsabilité de fournir l'ordre du sélecteur natif passe à l'appelant ;
* **`positional_damage_range(state, owner_id, target_id, dmin, dmax)`** — les bornes passées par
  `apply_elevation_bonus` et `apply_trench_reduction` (MÊMES fonctions que le COMBAT, pas de fork).
  ⚠ Depuis #494-r1-r1 cette fonction ne sert plus qu'au chemin **DÉGRADÉ** : la clé de production
  passe par la prédiction complète, qui applique ces deux feuilles elle-même ;
* `owner_id=` câblé aux **quatre** call-sites (Doombolt, FinalJustice, AncestralFortune,
  KillMaimBurn). Un call-site qui l'oublierait retomberait sur la clé constante d'avant, en silence
  — d'où le balayage AST de `test_494r1_ordre_cibles_offline.py`.

NON porté, et nommé (état du 2026-08-07, AVANT #494-r1-r1) :

* l'**ARMURE** de la cible (`#527-r1`) ;
* la **DÉFENSE** de la cible (`#494-r1-r1`) ;
* `ShouldApplyRangedInMelee` — feuille du même builder, mais elle ne dépend que de l'ATTAQUANT, donc
  facteur COMMUN à toutes les cibles ⇒ **sans effet sur l'ORDRE** (elle en a un sur les seuils
  kill/overkill) ;
* les modificateurs d'**EFFETS** par cible.

## 8. Résidus (état à la clôture de #494-r1)

* **`#494-r1-r1`** — la clé de tri doit passer par la prédiction COMPLÈTE par cible. **FERMÉ, §10.**
* **`#527-r1`** — confirmé ici sur une seconde ability, avec le TÉMOIN EXÉCUTABLE
  `test_doombolt_live.py::test_doombolt_ordre_heterogene_bloque_par_l_armure_live`
  (`xfail(strict=True)`). **FERMÉ, §10** — le cliquet a joué (xpass), le marqueur est retiré.
* **Hors périmètre, LU en chemin** : `IdunBattleLogic.Entities.DSLSelectors$$Damageable` n'est pas
  « vivant et PV > 0 » (ce que porte `entities/selectors/units.Damageable`) mais
  `UnitsWithoutTrait(source, UnitTrait.Invincible, 3)`. Non mesuré, non porté ici — le signaler,
  pas le corriger au passage.

## 10. #494-r1-r1 — la clé EST la prédiction complète, et son `damageProfile` est NUL

Deux relectures ferment les deux résidus d'un seul geste.

**(a) `+0x48` est le nœud `hits`, pas un `dmgMax`** — le ctor l'atteste
(`SortUnitsByDamageUtilitySelector..ctor(state, battleQuery, utilitiesDatabase, targets, caster,
ability, utilityDefinition, damage, hits, aiLogger)`), et son défaut est **1**, écrit en dur. Le
nœud de dégât rend UN entier. Les **quatre** call-sites portés passent `hits = null`.

**(b) le slot `0x26` est la PRÉDICTION COMPLÈTE.** `metadata/interface_slots.tsv` donne
`IBattleQuery 38 GetAttackPrediction 11` = la surcharge à `calculateDamageAtTile:Func<Int32>` /
`calculateHitsAtTile:Func<Int32>` → `DamagePredictionQuery$$GetAttackPrediction` (memset 0xb8 de
l'`AttackPredictionRequest`, puis slot 5 = `DamagePrediction$$PredictAttack`) → `$$PredictAttackRaw`.
Armure, défense, modificateurs d'attaquant et de défenseur, bouclier et scénarios de BLOCK entrent
donc dans la clé.

**(c) et `damageProfile` est passé `null`**, ce qui met le **perçage à ZÉRO** :
`IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` commence par
`if (damageProfile == null) return 0`. Le garde n'existerait pas si aucun chemin ne passait un
profil nul. La clé prédit donc `GetDamageWithPiercing(d, 0, armure) = max(0, d − armure)` :
**l'armure est soustraite en entier**, et aucun gate de profil ne joue.

Le nœud d'ability (`+0x28`) reste ce qu'il désigne — `Direct(AbilityOrEffect(1102))` pour Doombolt,
`Direct(AbilityOrEffect(1132))` pour KillMaimBurn, `UnitNormalAttackType` pour FinalJustice,
**rien** pour AncestralFortune (donc `GetNormalAttackType(owner)`).

### Mesure — les HUIT régimes, `python probe_494_doombolt_sort_order.py --regime <r>`

| régime | NATIF joué | PORT joué | verdict |
|---|---|---|---|
| `I1` | `[79, 85, 81]` | idem | ACCORD |
| `I3` | `[79, 85, 83]` | idem | ACCORD |
| **`I5`** | `[79, 83, 85]` | idem | **ACCORD** (divergeait : port `[79, 85, 81]`) |
| **`J1`** | `[79, 83, 85]` | idem | **ACCORD** (divergeait) |
| `K1` | `[79, 83, 81]` | idem | ACCORD |
| `L1` | `[79, 81, 83]` | idem | ACCORD |
| `L2` | `[79, 85, 81]` | idem | ACCORD |
| `L3` | `[79, 81, 83]` | idem | ACCORD |

**8/8** (6/8 avant). `I5`/`J1` sont exactement les régimes où une cible se tient sur la tuile `(1,3)`
de `MC1_67`, qui porte `Thorns_DefenseReduction` : son occupant descend à `defense = 50`
(`statDelta {"defense": -50}`) et prend donc **plus** de dégât. Le port la classe désormais
DEVANT la cible qui bénéficie du bonus d'élévation — comme le natif. La défense pèse plus, ici, que
le +50 % d'élévation : ce n'est pas un réglage, c'est ce que la prédiction rend.

Côté `#527-r1` (AncestralFortune, `probe_527 --etage cle|armure`) : **6/6**, dont la bascule
d'armure entre 2100 et 2200 reproduite. Détail :
`docs/rl/case-527-r1-choix-de-cible-ancestral-fortune.md`.

### Ce que ça a coûté, et la leçon transposable

⚠ **Un seuil correctement encadré MESURE, mais n'ATTRIBUE pas.** `#527-r1` avait borné la bascule
native entre armure 2100 et 2200, et en avait déduit — par la loi `seuil = d × 35 %` du profil
`Plasma` — que le natif employait le dégât des TROIS coups (`3 × 2044 = 6132`). Le seuil était
juste ; la loi était la mauvaise. Deux inconnues se compensaient : `6132` à 65 % de perçage et
`2044` à **0 %** donnent le même seuil à ~50 près. Il a fallu LIRE `GetAttackPiercingDamageRatio`
pour trancher — aucune quantité de mesure ne l'aurait fait, parce que les deux modèles prédisent la
même chose sur cet axe.

⚠ **UN MONTAGE DISCRIMINANT EST DISCRIMINANT POUR UNE CLÉ DONNÉE.** L'étage 1 de
`probe_419r6r1_face_decision.py` cherchait son régime sur un stub à PV seuls — donc, depuis ce
changement, sur le chemin DÉGRADÉ de `_target_utility`. Résultat mesuré : le montage est revenu
`montage_discriminant = False`, un **rouge de MONTAGE** qui ne juge pas le port. La réparation est
la transposition exacte de ce que ce probe disait déjà de son dégât (« un montage réglé sur une
valeur SUPPOSÉE ne prouve rien ») : la reconnaissance rend désormais aussi l'**ÉTAT**
(`_reco_du_runner`), et le balayage exerce la clé RÉELLE. Corollaire de coût : le produit cartésien
naïf devenait ~200 000 prédictions complètes ; le balayage est SÉPARABLE (l'utilité d'un rôle ne
dépend que de SES PV), ce qui le ramène à ~1 100 évaluations pour exactement la même couverture.

### Résidus ouverts

* **`#494-r1-r1-r1`** — `isMelee` et `hits` de la clé ne sont pas LUS dans `PredictAttackRaw`
  (non parcouru intégralement). Le port dérive `isMelee` de l'ability du nœud `+0x28` et fixe
  `hits = 1` parce qu'aucun call-site porté ne fournit de nœud de coups ; le comportement de
  `PredictAttackRaw` à `hits > 1` est donc **NON CONFRONTÉ**.
### Un verdict RETOURNÉ en chemin : `MightCrit` (#419-r6-r1)

`#419-r6-r1` avait mesuré que le sélecteur ne fait PAS entrer `MightCrit` — contre le décompilé, qui
dit l'inverse. La mesure avait été faite sur la clé PRE-ARMURE et concluait par **compensation** ;
rejouée à l'identique sur la clé corrigée, elle s'inverse : le port AVEC le flag est bit-exact avec
le live (`[79, 83, 81]`), SANS le flag il diverge (`[79, 83, 85]`). Le port passe donc désormais
l'`attacker_ctx` à la prédiction, et le test a changé de sens. Détail :
`docs/rl/case-527-r1-choix-de-cible-ancestral-fortune.md` §6bis.

## 9. Ce que ce cas a coûté, et la leçon transposable

⚠ **Un critère d'égalisation qui ne lit qu'une LISTE CHOISIE de stats fabrique de fausses lois.**
`probe_494` imprimait « REGIME EGALISE : OUI » en ne lisant que `hp/maxHp/armor/fixedArmor` — donc il
déclarait égalisés des régimes où une cible se tenait sur une tuile `Thorns_DefenseReduction`, et il
ne regardait pas du tout l'ÉLÉVATION (une propriété de la TUILE, pas de l'unité). Sur sept géométries
ainsi mal qualifiées, une permutation régulière a émergé — assez régulière pour survivre à deux
prédictions hors échantillon. Le critère lit désormais aussi `defense` et `statDelta`, et imprime
l'élévation à part.

⚠ **Un montage qui laisse varier une seconde cause ne mesure pas ce qu'il croit mesurer, et il peut
être VERT pour cette raison-là.** `db-4` passait par compensation ; `#419-r6-r1` a dû, pour la même
raison, poser une géométrie PLATE au build (mesure : sur les 1870 régimes de PV qui rendent son
montage discriminant à plat, **0** survit dès qu'une des trois cibles classantes reçoit le bonus
d'élévation — la fenêtre « létal MAIS sous le seuil d'overkill » est exactement ce qu'un ×1,5 fait
sortir).
