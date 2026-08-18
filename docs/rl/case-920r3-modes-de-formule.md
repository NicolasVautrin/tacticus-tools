# #920-r3 -- Modes CalculateMin / CalculateMax des noeuds `IAmountFormula` (build `rnca9r7q6c`)

RE PURE, lecture offline (`mcp__ghidra__decompile_function`). Aucun live, aucun runner.

## 0. Le socle, LU (pas suppose)

`IdunBattle.DSL.IAmountFormula` -- slots `0 IsSimple`, `1 Calculate`, `2 CalculateMin`,
`3 CalculateMax`, `4 CalculateAverage` (`data/symbols/rnca9r7q6c/metadata/interface_slots.tsv`,
confirme par la declaration Il2CppDumper de l'interface).

Dispatcher d'interface : `FUN_180025fb0(<slot>, <Il2CppClass* DAT_18333c498>, <cible>, <entities>,
<result>)`. Le premier argument EST le slot -- c'est lui qui porte le MODE.

Cote vtable (offsets relatifs, lus dans `IdunBattle.DSL.AAmountFormula$$CalculateAverage`) :
`+0x1c8` IsSimple, `+0x1d8` Calculate, `+0x1e8` CalculateMin, `+0x1f8` CalculateMax
(slots MethodInfo 9/10/11/12 -- concordance exacte avec le dump de declarations).

Hierarchie (`frida/classes.tsv`) :

- `AAmountFormula` declare `IsSimple` / `Calculate` / `CalculateMin` / `CalculateMax`
  **ABSTRAITS** (RVA -1), et implemente `CalculateAverage` :
  `IsSimple() ? Calculate() : (CalculateMax() + CalculateMin()) / 2` (division entiere).
- `ASimpleAmountFormula` override `CalculateMin` ET `CalculateMax` : les deux **replient sur
  `Calculate`** par appel VIRTUEL du slot `+0x1d8`. Les deux corps partagent **la MEME RVA**
  (dedup IL2CPP, visible directement dans le dump de declarations).
- `AComplexAmountFormula` n'override QUE `IsSimple` -> `CalculateMin`/`CalculateMax` y restent
  **ABSTRAITS**. Consequence : **tout noeud complexe DOIT les implementer**, donc le recensement
  des overrides est exhaustif par construction (9 classes complexes <-> 9 paires d'overrides).

## 1. Tableau -- patron (a) = "propager le slot aux enfants, meme arithmetique" / (b) = autre

| # | Noeud (symbole natif verbatim) | Base | Patron | Corps de `CalculateMin` / `CalculateMax` |
|---|---|---|---|---|
| 1 | `IdunBattle.Entities.Formulas.SumAmount` | Complex | **(a)** | Corps STRICTEMENT identique a `$$Calculate`, seul le slot change (`1`/`2`/`3`). Somme des 5 enfants `+0x10..+0x30` dans l'ORDRE ; `+0x10` et `+0x18` inconditionnels (null -> throw), `+0x20/+0x28/+0x30` sous `if (champ != 0)`. `result` propage. |
| 2 | `IdunBattle.Entities.Formulas.MultiplyAmount` | Complex | **(a)** | Idem, slot `1`/`2`/`3`. Retour `(uint)(iVar15 * iVar14)` dans les TROIS. **AUCUN croisement de bornes** : le min est le produit des min, le max le produit des max. Les 2 enfants sont obligatoires. |
| 3 | `IdunBattle.Entities.Formulas.MultiplyPercentageRecursively` | Complex | **(a)** | Idem, slot `1`/`2`/`3` sur les 3 enfants (`+0x10` value, `+0x18` percentage, `+0x20` times, tous obligatoires), puis le MEME `$$CalculateInternal` non modifie. |
| 4 | `IdunBattle.DSL.IfAmount` | Complex | **(a)** | Condition (`+0x10`) evaluee via un AUTRE dispatcher, `FUN_180026100(0, DAT_183339c18, ...)` -> retour `char`, **mode non concerne**. Puis UN SEUL appel sur la branche choisie (`+0x18` si vrai, `+0x20` sinon) avec le slot propage `1`/`2`/`3`. Ce n'est donc PAS `min(then, else)` : c'est le min DE LA BRANCHE PRISE. Nuance : `result` est **mis a ZERO** avant l'appel enfant (les 0x40 octets), dans les trois. |
| 5 | `IdunBattle.Entities.Formulas.ConditionalAmount` | Complex | **(a)** | Structure identique a `IfAmount` (meme dispatcher de condition, meme selection de branche, slot propage). SEULE difference : `result` est **PROPAGE** (copie), pas zeroise. |
| 6 | `IdunBattle.Entities.Formulas.CacheAmount` | Complex | **(a)** | Un seul enfant (`+0x10`), slot propage `1`/`2`/`3`. Memoisation `Nullable<int>` dans **TROIS champs DISTINCTS** : `+0x18` (Calculate), `+0x20` (CalculateMin), `+0x28` (CalculateMax). Les trois modes ont donc chacun leur cache -- ils ne se polluent pas. `result` propage. |
| 7 | `IdunBattle.Entities.Formulas.RandomAmount` | Complex | **(b)** | COURT-CIRCUIT. `CalculateMin` lit **`+0x10` SEUL**, `CalculateMax` lit **`+0x18` SEUL**, et **tous deux appellent le slot `1` (= `Calculate`)**, pas leur propre slot : le mode NE se propage PAS. Aucun tirage RNG, retour immediat. Le `result` passe a l'enfant est **zeroise**. Le null-check porte sur le SEUL champ lu (`CalculateMax` ne leve pas si `+0x10` est null). Pour memoire `$$Calculate` evalue les deux en slot `1` puis appelle le RNG `+0x20` avec `(min, max + 1)`. |
| 8 | `IdunBattle.Entities.Formulas.FirstHitInCurrentAttackDamageRange` | Complex | **(b)** | Aucun enfant `IAmountFormula` (`+0x10` est le `IPseudoRNG`). Les trois lisent la meme liste ECS, meme garde (`liste == null` ou `Count <= 0` -> **retourne 0**), puis `ListExtensions.FirstOrDefault<HitDamage>`. Ensuite : `Calculate` -> `IdunBattle.Core.HitDamage$$GetDamage(&hit, this+0x10, 0)` ; `CalculateMin` -> **les 32 bits BAS** du `HitDamage` ; `CalculateMax` -> **les 32 bits HAUTS** (`>> 0x20`). Aucun appel a `GetDamage`. |

Semantique de `HitDamage` etablie par lecture de `IdunBattle.Core.HitDamage$$GetDamage` :
`+0` = min, `+4` = max ; `min == max -> min` ; `ignoreSpread -> (max + min) / 2` ;
sinon `random.Range(min, max + 1)`. Donc `CalculateMin`/`CalculateMax` de #8 rendent bien
les bornes brutes du range du premier coup.

## 2. Question supplementaire -- `Min`, `Max`, `Difference`, `Divide`, `Negative`, `Half`, `Double`

**La recherche initiale echouait sur le NOM, pas sur l'existence.** Le mirror Python nomme ses
classes `Min`/`Max`/`Divide`/... la ou le natif nomme `MinAmount`/`MaxAmount`/`DivideAmount` --
et les quatre autres n'ont **aucune classe native du tout**.

### 2a. `MinAmount`, `MaxAmount`, `DivideAmount` : PAS d'override -- ETABLI, pas indecidable

Ces trois classes derivent d'**`ASimpleAmountFormula`** (pas de `AComplexAmountFormula`).
Trois observations independantes concordent :

1. **Ghidra (`rnca9r7q6c`)** : 0 symbole `MinAmount$$CalculateMin` / `MaxAmount$$...` / `DivideAmount$$...`.
2. **`frida/methods.tsv` (`rnca9r7q6c`)** : le recensement EXHAUSTIF des declarations de
   `CalculateMin`/`CalculateMax` rend **20 lignes** -- `ASimpleAmountFormula.CalculateMax`
   plus les **9 paires** des 9 noeuds complexes. `MinAmount`/`MaxAmount`/`DivideAmount` n'y
   declarent que `Calculate`.
3. **Declarations Il2CppDumper (source NON dedupliquee, indexee par CLASSE)** : `MinAmount`,
   `MaxAmount`, `DivideAmount` declarent `.ctor` + `Calculate` (Slot 10), **et rien d'autre**.

Le point 3 est celui qui tranche : cette source liste les methodes **declarees**, donc la dedup
par adresse ne peut pas y masquer une entree. Elle **explique** aussi l'anomalie du point 2 --
`ASimpleAmountFormula.CalculateMin` et `.CalculateMax` y portent **la meme RVA**, ce qui est
exactement pourquoi une seule des deux survit dans une table indexee par adresse.

Corps effectif, donc :

- `MinAmount$$Calculate` = `Math.Min(a.Calculate(slot 1), b.Calculate(slot 1))`, `a`=`+0x10`, `b`=`+0x18`, les deux obligatoires (LU).
- `MaxAmount$$Calculate` = `Math.Max(...)`, idem (LU).
- `DivideAmount` : champs `_left +0x10`, `_right +0x18`, `_roundingRule +0x20` (corps non lu dans cette passe).
- Et pour les trois : `CalculateMin(e, r) == CalculateMax(e, r) == Calculate(e, r)`,
  **avec les enfants evalues en mode NORMAL (slot 1)**. Le mode ne descend pas.

### 2b. `Difference`, `Negative`, `Half`, `Double` : ce ne sont PAS des noeuds

Ce sont des **methodes de FABRIQUE** (`IdunBattleLogic.Entities.DSLFormulas$$<nom>`, retour
`IAmountFormula`). La question "ont-elles un override" ne se pose donc pas : le comportement
Min/Max est **celui du noeud qu'elles construisent**. Identifie par la STRUCTURE (pointeur de
classe alloue), jamais par le nom -- Ghidra mislabelle les ctors gshared ici en
`QuoteInstruction..ctor` et `IsInTeamTrigger..ctor` :

| Fabrique | Classe allouee | Arguments du ctor | Noeud reel |
|---|---|---|---|
| `DSLFormulas$$Multiply(a, b)` | `DAT_1833fe9f0` | `(a, b)` | `MultiplyAmount` |
| `DSLFormulas$$Double(a)` | **meme `DAT_1833fe9f0`** | `(a, Const(2))` | `MultiplyAmount` -> **patron (a)** |
| `DSLFormulas$$Negative(a)` | **meme `DAT_1833fe9f0`** | `(a, <factory +0x38>)` | `MultiplyAmount` -> **patron (a)** |
| `DSLFormulas$$Divide(a, b, rule)` | `DAT_183398ec0` | `(a, b, rule)` | `DivideAmount` |
| `DSLFormulas$$Half(a, rule)` | **meme `DAT_183398ec0`** | `(a, Const(2), rule)` | `DivideAmount` -> **repli sur `Calculate`** |

**Asymetrie a retenir** : `Double` PROPAGE le mode a `a` (c'est un `MultiplyAmount`, complexe),
`Half` NE LE PROPAGE PAS (c'est un `DivideAmount`, simple).

**Et `Negative` est le piege le plus couteux** : `Negative(a) = Multiply(a, -1)` suit le patron (a),
donc `Negative(a).CalculateMin = a.CalculateMin * (-1)`, qui est la borne **HAUTE** de `-a`.
Sur un `a` d'amplitude non nulle, le natif rend donc `CalculateMin > CalculateMax`. Ce n'est pas
un bug a corriger dans le port : c'est le comportement natif, a mirrorer tel quel.

## 2c. LE PORT (2026-08-18) — et la prémisse RE-MESURÉE sur le build chargé

**Recensement RE-DÉRIVÉ, pas recopié** : recherche LITTÉRALE du dispatcher à slot **2**
(`FUN_180025fb0(2,DAT_18333d6c8`) dans tout le décompilé du build chargé — donc insensible à la
dedup IL2CPP par adresse. **12** fonctions le portent : les **7 propagateurs** (`SumAmount`,
`MultiplyAmount`, `MultiplyPercentageRecursively`, `IfAmount`, `ConditionalAmount`, `CacheAmount`,
`PercentageOf`) et **5 CONSOMMATEURS** (`BaseEffect$$AdditionalHits`,
`AttackDamageBehaviour$$GetDamage`, `AbilityDamageBehaviour$$GetDamage`,
`SortTargetsByDamagePredictionSelector`, `SortAttackersByDamagePredictionSelector`).
`RandomAmount$$CalculateMin` et `FirstHitInCurrentAttackDamageRange` n'y sont PAS — confirmation
directe du court-circuit. `PercentageOf` relu verbatim : `Calculate` = slot **1** sur `+0x10` ET
`+0x18` ; `CalculateMin` = slot **2** sur les deux ; même `CalculateInternal`.

**Porté** (`engine/dsl/base.py::invoke_slot` + `engine/entities/formulas.py`) : les **5**
propagateurs qui ont un mirror (`Sum`, `Multiply`, `If`, `ConditionalAmount`, `PercentageOf`) plus
les **2** fabriques qui allouent un `MultiplyAmount` déguisé (`Double`, `Negative`). Un seul corps
par nœud (`_par_slot`), trois points d'entrée — exactement la forme native. Les nœuds SIMPLES
(`Min`, `Max`, `Divide`, `Half`) gardent le repli d'`AAmountFormula` : c'est un RÉSULTAT, pas un
oubli, et le cliquet l'assertionne.

**CE QUE LA PROPAGATION CHANGE, ET CE QU'ELLE NE CHANGE PAS.** L'énoncé visait le scalaire-centre
de la réduction CAPÉE défenseur (`capped_reduction_flat((min+max)/2)`). Or l'arbre de
`GuardianOrganism` est `Min(PercentageOf(CurrentDamage, pct), cap)` — **sa RACINE est un
`MinAmount`, nœud SIMPLE**. Le natif lui-même ne le parcourt donc qu'UNE fois, et le scalaire FLAT
du port (confirmé LIVE deux fois, #91) n'est PAS le gisement de ce résidu. Les deux lectures se
réconcilient au lieu de se contredire, et le « montage discriminant » proposé (des bornes dont une
seule dépasse le cap) ne discriminerait **rien** sur ce porteur.

**CONSÉQUENCE OBSERVABLE, mesurée** : `calculate_average` d'un composite ne consomme plus AUCUN
tirage (avant, il retombait sur `Calculate`, donc sur le tirage de `RandomAmount` — une prévision
qui consomme le PRNG). Cliquet : `tests/engine/test_920r3_modes_de_formule_offline.py` (6 tests,
5 étages, contre-épreuve jouée : retirer la propagation de `Sum` fait rougir 3 étages).

**NON EXERCÉ AUJOURD'HUI, et c'est dit** : côté port, le SEUL consommateur des slots min/max est
`AAmountFormula.calculate_average`, et les deux arbres qui y arrivent
(`BaseTriggeredAbility.min_max_damage_average` = `Half(Sum(Const, Const))`, et `RandomAmount`) ne
sont pas des composites à enfant à plage. Le canal `AdditionalHits` du port, lui, résout ses
bornes impérativement et ne construit pas d'arbre. La propagation est donc **ARMÉE et fidèle**,
pas confrontée live — il n'existe aujourd'hui aucun montage qui la sépare.

## 3. Ce qui reste INCERTAIN

- **`DSLFormulas$$Difference`** : declaree dans le dump Il2CppDumper, **0 symbole** cote Ghidra
  `rnca9r7q6c`. Non re-verifiee ici. Le mirror Python la documente comme `Sum(a, Multiply(b,-1))`
  -- ce qui donnerait `SumAmount` (complexe, patron (a)), mais **ce n'est pas LU**.
- **Valeur du champ `<factory +0x38>`** utilise par `Negative` : presume `Const(-1)`, NON LU.
- **Corps de `DivideAmount$$Calculate`** : non lu (hors perimetre). Seuls ses champs le sont.
- **Le dump de declarations date d'un AUTRE build** (2026-05-20). Il n'est utilise ici que pour
  la question "quelles methodes une classe declare-t-elle", et il est corrobore sur `rnca9r7q6c`
  par Ghidra ET par `frida/methods.tsv`. Un changement de forme entre les deux builds reste
  possible mais aucun indice ne le suggere.
- **Litteraux load-bearing lus dans le pseudo-C** : les slots `1`/`2`/`3` passes a
  `FUN_180025fb0`. Le seul dont la conclusion depend entierement est le `1` de
  `RandomAmount$$CalculateMin` et `$$CalculateMax` -- il a ete **verifie au niveau machine**
  (`48 8D 44 24 30` / **`B9 01 00 00 00`** = `mov ecx,1` / `48 89 44 24 20` / `E8 <call>`,
  dans les DEUX fonctions). Ce n'est donc pas un repli de registre.
