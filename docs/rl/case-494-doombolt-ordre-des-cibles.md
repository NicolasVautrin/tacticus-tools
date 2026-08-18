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

### #494-r1-r1-r1 — `hits` est CLOS par la mesure, `isMelee` est une VRAIE divergence

**Volet `hits` : FERMÉ, le régime `hits > 1` N'EXISTE PAS dans ce build.** Le recensement utile
n'est pas celui de `PredictAttack` (méthode d'interface, xrefs DATA seules) mais celui du SÉLECTEUR :
`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$.ctor` n'a qu'UN appelant,
`IdunBattleLogic.Entities.DSLSelectors$$SortUnitsByDamageUtility`, en **4 surcharges** — soit
**13 call-sites / 11 abilities**, et **13/13 passent `hits = null`** (`KillMaimBurn`, `RitesOfMorkai`,
`FinalJustice` ×2, `WyrdmakersHelm`, `Doombolt`, `MartialExemplar`, `EcstaticSlaughter` ×2,
`VexillaMagnifica`, `Drachnyen_ExtraAttack`, `AncestralFortune` ×2). Le `hits = 1` du port est donc
**FIDÈLE, pas une simplification** : il n'existe ni HERO, ni MoW, ni SUMMON, ni NPC pour l'exercer.
Détail qui tranche l'intention : `AncestralFortune` et `Drachnyen_ExtraAttack` appellent bien
`GetHits` — mais pour l'**ATTAQUE** (`DSLBehaviors$$AttackWithAttackDamage`), jamais pour le **TRI**.
Contrôle de non-péremption au prochain build : re-jouer `list_xrefs` sur les 4 surcharges.

Au passage, ce que `PredictAttackRaw` fait de `hits` **ailleurs** (donc le comportement que le port
possède déjà par un autre chemin) : ni multiplié ni ignoré — **BOUCLÉ avec état déplété**. C'est le
lambda `DamagePrediction.u003Cu003Ec__DisplayClass12_0$$u003CPredictAttacku003Eb__0` qui appelle
`PredictAttackRaw` une fois, puis `for (i = 1; i < hits; i++)` en réécrivant `HitIndex` (+0x6c),
`PreviousHitsPrediction` (+0x84) et `DefenderInitialHealth` (+0x7c) avant chaque coup, et en cumulant
par `DamagePredictionResult.Add`. La surcharge sans `Func` ne boucle pas.

**Volet `isMelee` : DIVERGENCE RÉELLE, et sa source n'est pas l'arme.** Le natif :
`DamagePrediction$$IsMeleeAttack` → `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` =

    switch (GetAbilityAttackRangeType(ability)) {
      case None:   return false;                                        // et c'est le cas par DEFAUT
      case Melee:  return true;                                         // sans condition de distance
      case Ranged: return false;                                        // sans condition de distance
      case Normal: return !HasFlag(caster, UnitFlag.ForceRangedAttack)
                          && AreEntitiesAdjacent(casterPosition, target);
    }

La source est donc la **config de l'ability** (`attackRangeType`), pas le type d'arme. Mesure
gameconfig `rnca9r7q6c` : sur 572 abilities, **166** portent le champ (85 `Ranged`, 71 `Melee`,
10 `Normal`) et **406 ne le portent pas** ⇒ `None` ⇒ `false`. Le port, lui, décide par la SEULE
adjacence (`engine/services/battle_query.py::normal_attack_is_melee` →
`get_attack_weapon_for_default_normal_attack`) : il applique donc la branche `Normal` **à tous les
cas**. Quatre régimes de divergence, nommés : `Melee` + cible non adjacente ; `Ranged` + cible
adjacente ; `attackRangeType` absent ; `ForceRangedAttack` posé (le flag n'a AUCUN consommateur dans
`engine/`). S'y ajoute une polarité de repli traître — quand aucune arme n'est éligible,
`select_weapon_pierce` rend `is_ranged = False`, donc `is_melee = True`, l'inverse de la vérité
native pour une unité purement ranged.

⚠ **Portée BORNÉE, et c'est ce qui rend la confrontation piégeuse.** Sur la clé de tri
(`damageProfile = null`), `isMelee` ne change la valeur native que par **`StatType.ExtraMaxDamage`**
(25) — le bloc de perçage `ExtraPierceMelee`/`ExtraPierceRanged` est gardé par
`if (damageProfile != null)` et reste donc inerte. Or le port ne renseigne pas du tout `extra_max`
dans le chemin PRÉDICTION (`engine/runner/operations/attack_prediction.py`), alors que le natif
l'applique dans `GetBaseDamageFix64` **hors** de cette garde, et que l'étage COMBAT le renseigne
correctement. Un test qui ne monte ni `ExtraMaxDamage` (effet `RealityUnbound_ExtraMaxDamage` 1207)
ni un effet gaté `IsMeleeAttack`/`IsRangedAttack` mesurera **0 écart** et se lira comme un vert.

Résidu **`#494-r2`** : le foyer d'`isMelee` est PARTAGÉ décision↔combat (`damage_model.py` l'appelle
aussi), donc sa correction déborde de ce cas et prend son propre numéro.

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

## 11. #494-r2 — `isMelee` ne vient PAS de l'arme, et le régime annoncé était le SYMÉTRIQUE du vrai

### 11.1 Le natif, LU

`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`, verbatim :

```
isMelee  = DamagePrediction.IsMeleeAttack(ability, attacker, attackerPos, defender);
extraMax = isMelee ? 0 : UnitExtensions.GetStat(attacker, 0x19);   // StatType.ExtraMaxDamage
base     = GetBaseDamageFix64(damage, isMaxOut, ..., extraMax);
```

et `IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack` ne fait QUE déléguer au slot **2**
d'`IBattleQuery` = `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, c'est-à-dire le switch sur
`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType(ability)` :
`None(0)` et `Ranged(2)` rendent `false` **sans condition de distance**, `Melee(1)` rend `true`
**sans condition**, et seul `Normal(3)` teste
`!UnitExtensions.HasFlag(caster, 0x15 = UnitFlag.ForceRangedAttack) && AreEntitiesAdjacent(casterPosition, target)`.
**L'arme n'entre nulle part.**

### 11.2 La prémisse de la fiche était FAUSSE sur un point, et le vrai régime est plus large

La fiche annonçait, comme régime de divergence, « une unité purement ranged » : mesuré
(`scripts/python/probe_494r2_attack_range_type_normal.py`, gameconfig du build `t6dpr4k06g`),
il n'y en a **AUCUNE** — **0** ranged-only, **271** melee-only, **331** mixtes, **81** sans arme.
Le régime qui mord est son **symétrique** :

| régime | natif (slot 2) | ancien port (arme) | |
|---|---|---|---|
| attaquant ADJACENT | melee | melee | d'accord |
| NON adjacent, arme ranged EN PORTÉE | ranged | ranged | d'accord |
| NON adjacent, AUCUNE arme éligible | **ranged** | **melee** | **ÉCART** |

`get_attack_weapon_for_default_normal_attack` rend `(None, False)` sur un ensemble vide, donc
`select_weapon_pierce` rendait `is_ranged = False`, donc l'ancien `normal_attack_is_melee` rendait
`True` — l'INVERSE du natif — pour **toute** unité melee-only évaluée contre une cible non adjacente.

### 11.3 La branche prise est bien `Normal(3)`, et c'est une MESURE

Les **18** ids d'attaque normale du build (les deux génériques, la boss, les 14 de la table passive
de `services/custom_normal_attack.py` et celui de la table active) n'ont **AUCUNE** entrée
`gameconfig.abilities` : `GetAbilityAttackRangeType` rend donc « pas d'entrée » et le natif prend
`Normal(3)`. Le port **résout et passe le nom quand même** — c'est ce qui le garde juste le jour où
un build en renseignera un. Le cran est exécutable : `test_494r2_normal_attack_is_melee_offline`
étage 2 rougit si un de ces 18 ids reçoit un `attackRangeType`.

### 11.4 Le RAYON de la correction est celui du natif — et c'est ce qui autorise le fix à la SOURCE

`IdunBattle.Entities.Abilities.AbilityEntities..ctor` a **33** paramètres et **aucun** ne porte la
nature du coup (ni `isMelee`, ni `isRanged`) : le natif n'a pas de champ à propager, toutes ses
gates RECALCULENT le prédicat par ce même slot 2
(`IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger`). Corriger la SOURCE
côté port — et laisser la valeur se propager dans `attacker_modifiers(is_ranged=…)` /
`defender_modifiers(is_melee=…)` — est donc le mirror, pas un élargissement. Ampleur du canal :
**99** classes d'effet du port lisent `is_melee`/`is_ranged` dans un slot de dégât ou de perçage.

### 11.5 Le foyer RUNNER, et pourquoi c'est un module

Trois sites du runner montaient chacun à sa façon le substrat du slot 2 (positions, graphe du
board, élévation, `UnitFlagsComponent`) : `operations/damage_utility.py` (face DÉCISION),
`abilities/loki/heavy_bolt_pistol.py` (face COMBAT) et
`operations/triggers/loki/empyric_ambush.py` (face TRIGGER, qui va jusqu'à ré-écrire le switch).
Le montage n'appartient à aucun des trois, et `abilities/targeting.py` — où vivent `_visual_id` et
`normal_attack_type_for` — **charge** `operations/damage_utility.py`, donc l'y poser fermerait un
cycle. D'où `engine/runner/battle_query_state.py`, qui s'importe SEUL et ne tire ni l'un ni l'autre.
Il accepte déjà `caster_position=` : c'est le point d'ancrage de `#419-r1-tr14-r4-r3`.

### 11.6 Validation

* **Garde vue ROUGE avant le fix**, par restauration de l'ancien corps
  (`git checkout HEAD~3 -- damage_utility.py`) : 2 failed / 10 passed, message verbatim
  `AssertionError: le consommateur GetMultiHitAttackPrediction doit recevoir is_melee=False
  (cible NON adjacente, branche Normal(3)) -- recu [True]`.
* **Contre-épreuve intégrée** : l'étage 1 rejoue l'ANCIENNE décision (`select_weapon_pierce`) sur le
  même montage et **exige qu'elle diffère** — sans ce cran, un montage où les deux coïncident
  passerait pour un succès (l'accord en régime dégénéré que la doctrine interdit).
* **Deux témoins où le canal ne doit PAS s'ouvrir** : attaquant adjacent, et attaquant à distance
  AVEC arme ranged en portée. Verts des deux côtés.
* **Étage 4 — le CÂBLAGE** : la valeur corrigée doit ARRIVER à `GetMultiHitAttackPrediction` (d'où
  elle commande les deux familles de modificateurs). Substitution du consommateur, trois crans dont
  la voie « l'appelant connaît déjà l'ability » (`is_melee` fourni → passé tel quel), qui interdit
  un fix recalculant TOUJOURS.
* **Non-régression rejouée** : offline `test_494r1_ordre_cibles_offline`, `test_333_minmax_avg_
  rounding_offline`, `test_960_ecstatic_slaughter_armour_shrieking_souls_offline`,
  `test_bl_1029r_drachnyen_extra_attack_offline`, `test_943r4_adjacence_cablee_offline` (73 passed) ;
  live `test_419r6r1_face_decision_live` (4), `test_504_kill_maim_burn_live` (7),
  `test_finaljustice_live` (1), `test_566_vexilla_magnifica_live` (25), `test_votann_lot1_live` (21).

### 11.7 Ce qui n'est PAS couvert

**Sans effet gaté melee/ranged, le fix est arithmétiquement NEUTRE.** La valeur corrigée n'entre
dans la clé que par `attacker_modifiers` / `defender_modifiers` ; sur un roster normalisé sans
effet de cette famille, les deux modèles rendent la même clé et **aucun montage live ne les
sépare** — c'est exactement le régime dégénéré qu'on ne doit pas prendre pour une preuve. Le montage
qui discriminerait est nommé : `worldKharn` (le seul porteur `lineup` de `KillMaimBurn`, et il est
**melee-only**, maxRange 0) contre des cibles à distance ≥ 2, l'une d'elles portant un des 99 effets
gatés ; ou `thousAhriman` (`Doombolt`, maxRange **2**) contre une cible à distance ≥ 3, seul régime
où son arme ranged sort de portée.

**`StatType.ExtraMaxDamage` reste hors du chemin PRÉDICTION du port.** Le natif l'applique dans
`PredictAttackRaw` **hors** de la garde `damageProfile != null`, et le port ne renseigne `extra_max`
que sur l'étage COMBAT (`damage_ops/normal.py`). Ce canal-là n'est donc toujours pas confronté sur
la face DÉCISION — et c'est ce que la fiche annonçait comme piège de confrontation.
