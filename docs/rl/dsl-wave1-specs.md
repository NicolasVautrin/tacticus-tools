# DSL wave-1 — specs de port EXACTES (RE pure, build gqfc5mff6c)

Binaire ghidra `/GameAssembly.dll`, base VA 0x180000000. Toutes les VAs citees sont lues dans le
decompile. Cible port : `scripts/python/engine/dsl/nodes.py` (classe `Node`, `evaluate(ctx)`,
`DslContext`, unite = dict `{id,team,hp,alive,pos:{col,row},visualId}`).

Legende : [PROUVE] = decompile lu (Calculate/ShouldTrigger + ctor + singleton). [DEDUIT] = nom natif
non-ambigu, ctor lu mais eval non decompile (sans doute residuel).

CAVEAT MISLABEL applique partout : les ctors gshared s'affichent sous un faux nom
(`HasUsedActiveAbilityThisTurnTrigger`, `thor.Menu.WaitForCondition`, `IceTileEffect...d__5`,
`AmountIsEqualOrGreaterAbilityTrigger`). L'identite REELLE de la classe = le SINGLETON `DAT_*`
instancie par la factory (pas le nom du ctor). Verifie par singleton + eval reelle.

---

## 0. Constantes litterales du factory-this (champs partages)

Le `DSLFactory` (param_1) porte des noeuds-constantes reutilisables (prouve par double-usage dans
`NonLethalDamage @180df7280` = `Min(Max(HP-1, 0), damage)` et par les predicats zero-based) :

- `*(factory+0xb8)` = Const **0**   (borne basse de Max dans NonLethalDamage ; 2e operande de AmountIsGreaterThanZero)
- `*(factory+0xc0)` = Const **1**   (le "-1" de HP-1 via Multiply(1,-1) ; 2e operande de AmountIsZero)
- `*(factory+0xd8)` = Const **-1**  (le facteur -1 de Difference et Negative ; confirme catalogue)

Le port n'a pas a repliquer ces champs : il code directement la semantique (`a>0`, `a==0`, `-a`).

---

## 1. NOEUD CRITIQUE — Filter / binding de l'element

### Filter @180def870, FilterContinuous @180def7b0, FilterByDirection @180def700

- **Filter @180def870** : THUNK PUR (`jmp`) vers **FromTrigger @180df00e0**. [PROUVE]
  => `Filter(source, predicate)` construit un **`FromTriggerSelector`** (classe REELLE).
- **FilterContinuous @180def7b0** : THUNK PUR vers FromTrigger AUSSI. [PROUVE]
  Meme classe `FromTriggerSelector`, memes 3 args -> semantiquement IDENTIQUE a Filter au niveau
  construction (la difference "continuous" est portee par le flag `+0x28`, cf. ci-dessous : Filter
  passe le flag=0 ; l'usage continuous passerait un flag !=0 via un overload de FromTrigger).
- **FilterByDirection @180def700** : DIFFERENT. Construit un **`FilterByDirectionSelector`**
  (ctor @180eeb3a0), classe distincte avec un parametre DIRECTION en plus (champs +0x18..+0x38, dont
  un bool +0x38). NON dans le perimetre du binding predicat generique ; a porter separement si une
  ability le reference (geometrie directionnelle). [PROUVE structure ctor, eval non lue]

### Classe reelle : FromTriggerSelector

- ctor **@180eebea0** : `(this, source@+0x10, producer@+0x18, predicate@+0x20, flag@+0x28)`.
  `TestUnitProvider.ctor(this, source)` pose la base ; `+0x18`=delegate producteur d'items,
  `+0x20`=delegate predicat, `+0x28`=bool. [PROUVE]
  Pour `Filter(source, predicate)` via le thunk : arg1->`+0x18` (producer = le selecteur source qui
  ENUMERE les items), arg2->`+0x20` (predicat), flag=0.
- Select **@180eebaa0** : [PROUVE — c'est LA reponse au binding]

### MECANISME DE BINDING (verdict) — [PROUVE]

`FromTriggerSelector.Select(this, evalCtx)` fait :

1. `evalCtx` (param_2) = une struct **`AbilityEntities`** de ~0x130 octets (le "contexte d'evaluation"
   = qui-est-caster / qui-est-target / owner / etc.). Elle est copiee dans un local (`local_278`).
2. Invoke le **producer** `+0x18` sur ce contexte (`FUN_180024d10(...,+0x18, ctxCopy)`) -> obtient un
   **IEnumerable** d'items (les elements a filtrer).
3. Boucle enumerateur : `MoveNext` / `get_Current` -> item courant `uVar9` (stocke `local_128`).
4. **Pour chaque item** : re-copie l'`AbilityEntities` de base dans `local_278`, puis invoke le
   **predicat** `+0x20` via `FUN_180025220(0, DAT_183279540, +0x20, ctxCopy, 0x20)`.
   Le **5e argument `0x20`** est un INDEX de slot : `FUN_180025220` ecrit l'item courant dans le
   slot designe de la COPIE du contexte avant d'appeler le delegate predicat. Le delegate recoit
   donc `(trigger, ctxCopyAvecItemLie)` et lit l'item via un selecteur "sujet" du contexte.
5. Si le predicat renvoie true -> `List.Add(item)`. Sinon, si `flag@+0x28` (continuous) est true ->
   arret anticipe (short-circuit) ; sinon on continue.

**Reponse a la question du binding :** OUI, il existe un slot de contexte / variable d'iteration.
L'element courant N'EST PAS passe en argument positionnel au predicat : il est **injecte dans une COPIE
de l'`AbilityEntities`** (le contexte d'eval) a un slot fixe, PUIS le predicat (un arbre `AbilityTrigger`
booleen) est evalue contre ce contexte modifie. Le predicat accede a l'item via un **selecteur-sujet**
de l'ability (le champ `*(ability+0x180)` observe dans les predicats concrets — c'est le "OriginalTarget"
/ element courant du contexte). Preuve concrete :

- `TheBetrayer_TakeTurnAbility$$GetPreferredAttackTargets @1811a58a0` :
  `Filter(source=param_2, predicate = NOT(HasTrait(ability+0x180, 0xd)))`. Le `HasTrait` lit son sujet
  via `ability+0x180` = l'element courant lie par Filter (PAS le caster). [PROUVE]
- `EnvStrategicBuffAbility$$GetValidTargetsWithoutCorrectBuff @180f7e8c0` :
  `Filter(units, IsHumanPlayer(OriginalOwner(ability+0x180)))` — meme slot +0x180 = sujet courant. [PROUVE]

**Implication design Python (recommandation) :** le `DslContext` doit gagner un slot **`subject`**
(= "element courant" / OriginalTarget). `Filter(source, predicate)` s'evalue :
```
out = []
for item in source.evaluate(ctx):
    child_ctx = replace(ctx, subject=item)   # copie + item lie au slot subject
    if predicate.evaluate(child_ctx):        # predicat = arbre bool lisant ctx.subject
        out.append(item)
return out
```
Les feuilles-sujet (`Subject`/`CurrentElement`, mirror du selecteur `ability+0x180`) lisent
`ctx.subject`. TOUT le sous-systeme predicats (HasTrait/HasEffect/Is*/AmountIs*) opere sur ce slot
quand il est sous un Filter — c'est la piece manquante a modeliser AVANT de porter les predicats.

- Type de retour Filter : **list[unit]** (List<T> construite par accumulation). [PROUVE]
- Contexte requis : la source (selecteur), le predicat, et le contexte d'eval avec slot subject.
  NON-captable offline : rien de specifique tant que source+predicat sont des noeuds portes.

---

## 2. Count @180decfa0

- Factory : ctor mislabel `thor.Menu.WaitForCondition.ctor`, singleton **`DAT_1831d8b90`**.
  Classe REELLE = **`CountFormula`** (Calculate @180f18040). [PROUVE]
- ctor `(this, selector@+0x10, 0)`.
- Calculate @180f18040 : lit le selecteur `+0x10`, l'evalue en liste, retourne le **cardinal** (nombre
  d'elements enumeres). [PROUVE]
- Retour : **int** (>=0). Ordre operandes : 1 enfant (le selecteur).
- Contexte requis : `ctx.units` (+ caster/target selon le selecteur enfant). Captable offline.
- Port : `Count(selector).evaluate = len(selector.evaluate(ctx))`.

---

## 3. Predicats de comparaison (retour bool) — AbilityTrigger

Tous : eval = `ShouldTrigger(this, evalCtx)`. Les operandes (a,b,c) sont des sous-noeuds evalues en
**int** (FUN_1800250d0 = eval formule -> int ; FUN_180024d10 = count d'un selecteur -> int). Comparaisons
sur **ENTIERS SIGNES** (pas Fix64). Ordre : a = 1er arg factory, b = 2e, c = 3e.

| Noeud | VA factory | Classe reelle (singleton) | eval VA | Semantique [PROUVE] |
|---|---|---|---|---|
| AreEqual(a,b) | 180de9000 | generique 2-arg (`DAT_183200238`) | (residuel) | a == b [DEDUIT nom ; ctor 2-arg lu] |
| AmountIsEqual(a,b) | 180de8820 | `AmountIsEqualAbilityTrigger` (DAT_183247ef0) | ShouldTrigger @180ee0bd0 | `return iVar14 == iVar15` = **a == b** |
| AmountIsGreater(a,b) | 180de8a40 | `AmountIsGreaterAbilityTrigger` (DAT_1832482b0) | ShouldTrigger @180ee11f0 | `return iVar16 < iVar15` = **a > b** (STRICT) |
| AmountIsEqualOrGreater(a,b) | 180de8660 | `AmountIsEqualOrGreaterAbilityTrigger` (DAT_183248030) | ShouldTrigger @180ee0e00 | `return iVar16 <= iVar15` = **a >= b** |
| AmountIsGreaterThanZero(a) | 180de88f0 | `AmountIsGreaterAbilityTrigger` (DAT_1832482b0) | via @180ee11f0 | `AmountIsGreater(a, 0)` = **a > 0** (2e op = Const 0 = factory+0xb8) |
| AmountIsZero(a) | 180de8b10 | `AmountIsEqualOrGreater` (DAT_183248030) + op_LogicalNot | via @180ee0e00 | `NOT(a >= 1)` = **a <= 0** (2e op = Const 1 = factory+0xc0 ; == 0 pour un count) |
| AmountIsOdd(a) | 180de8ab0 | `AmountIsEvenAbilityTrigger` (DAT_183248170) + op_LogicalNot | ShouldTrigger @180ee10e0 | `NOT(AmountIsEven)` = **(a & 1) == 1** (a impair) |

Details PROUVES cles :
- **AmountIsGreater vs AmountIsEqualOrGreater = DEUX classes distinctes** (singletons DAT_1832482b0 vs
  DAT_183248030), malgre le MEME nom de ctor mislabel. AmountIsGreater = `<` strict (@180ee11f0),
  AmountIsEqualOrGreater = `<=` (@180ee0e00). NE PAS confondre : lire le singleton, pas le nom du ctor.
- **AmountIsEven** @180ee10e0 : evalue la formule, retourne `~(byte)value & 1` = **bit0 de la valeur
  est 0** = pair. AmountIsOdd = la negation = **impair (a % 2 == 1)**. Teste le bit de poids faible de
  l'INT (parite entiere classique).
- Les classes Amount* comparent soit une VALEUR de formule (slot +0x18/+0x20 via FUN_1800250d0) soit un
  COUNT de selecteur (slot +0x10 via FUN_180024d10) — pour le port, on evalue simplement a et b en int.
- `AreEqual` (180de9000) : ctor generique 2-arg (singleton DAT_183200238, distinct de Amount*). Nom
  non-ambigu -> **a == b** [DEDUIT]. Se distingue de AmountIsEqual (classe dediee) par une eval
  potentiellement non-numerique (egalite d'objets/enums) — a confirmer si une ability l'utilise sur
  des non-int, sinon a == b.

Retour : **bool**. Contexte : les enfants (formules/selecteurs). Captable offline si a/b le sont.

---

## 4. Arithmetique

### Max(a,b) @180df62e0  [PROUVE semantique via NonLethalDamage]
- ctor generique 2-arg, singleton **`DAT_1832457c8`**. Meme singleton utilise par `NonLethalDamage`
  @180df7280 comme `Max(HP-1, 0)` (borne basse) => **max(a,b)**. Eval non decompilee (residuelle) mais
  usage prouve. Retour **int**. Ordre : a=1er, b=2e (sans importance pour max).
- Contexte : enfants. Captable offline.

### Divide(a,b,mode) @180dee5a0  [PROUVE arrondi — CRITIQUE]
- Classe REELLE **`DivideAmount`** (singleton DAT_183205a40), ctor @180f19a60 `(a@+0x10, b@+0x18, mode@+0x20)`.
- Calculate @180f19800 : `Fix64.FromInt(a) / Fix64.FromInt(b)` (division Fix64 exacte) PUIS
  `RoundFix64Result(quotient, mode)`. **PAS une division entiere brute.**
- **mode (3e arg factory) -> arrondi** (RoundFix64Result @180ffa110) :
  - mode==1 -> **Ceiling** ; mode==2 -> **Floor** ; sinon (0) -> **Round** (half-to-even, Fix64.Round).
- Retour **int** (op_Explicit Fix64->int apres arrondi). Ordre : Divide(a, b, mode) = round_mode(a/b).
- Contexte : enfants + mode (constante du ctor). Captable offline.

### Half(a,mode) @180df0840  [PROUVE]
- = `DivideAmount(a, Const(2), mode)`. Le "2" = noeud Const via ctor generique 1-arg (mislabel
  `IceTileEffect...d__5.ctor(this, 2, 0)`). Donc **Half(a) = Divide(a, 2, mode)** — MEME arrondi que
  Divide (Ceiling/Floor/Round selon mode). PAS un simple `a>>1` ni `a//2`. Retour int.

### Double(a) @180dee6f0  [PROUVE]
- = `Multiply(a, Const(2))` (singleton Multiply DAT_18325be78 + noeud Const 2). **Double(a) = a * 2**.
  Multiplication entiere exacte, aucun arrondi. Retour int.

### Negative(a) @180df7090  [PROUVE structure]
- = `Multiply(a, Const(-1))` (singleton Multiply DAT_18325be78, 2e operande = factory+0xd8 = -1).
  **Negative(a) = -a**. Retour int.

### Modulo(a,b,c) @180df69a0  [PROUVE — c'est un PREDICAT, pas une valeur]
- Classe REELLE **`ModuloAbilityTrigger`** (singleton DAT_183252378), ctor @180eedd00 `(a@+0x10,b@+0x18,c@+0x20)`.
- ShouldTrigger @180eeda30 : `return (iVar15 % iVar16) == iVar17` = **(a mod b) == c**. Modulo ENTIER
  signe C (`iVar15 % iVar16`, operande signee). Retour **bool** (pas int !). Ordre : a, b, c.
- ATTENTION : `Modulo` dans ce DSL n'est PAS l'operateur "a mod b -> int" ; c'est le PREDICAT
  "(a mod b) vaut c". Pour une valeur modulo pure, il faudrait un autre noeud (non dans ce batch).
- Contexte : 3 enfants. Captable offline.

### PercentageOf(pct,base,mode) @180df8720  [PROUVE arrondi — CRITIQUE]
- Classe REELLE **`PercentageOf`** (singleton DAT_1832813e8), ctor @180f217c0 `(pct@+0x10, base@+0x18, mode@+0x20)`.
- Calculate @180f215a0 -> CalculateInternal @180f20fc0 (Fix64) :
  1. `pctF = Fix64(pct)`, `baseF = Fix64(base)`.
  2. Normalise base a 2 decimales : `t = Round(baseF/100 * 100) / 100`.
  3. `r = pctF * t` ; `r = Round(r*100)/100` (arrondi a 2 decimales).
  4. `RoundFix64Result(r, mode)` -> int (Ceiling/Floor/Round selon mode, cf. #Divide).
- Net : **PercentageOf(pct, base, mode) ~= round_mode( pct% * base )** avec des Round intermediaires
  half-to-even a 2 decimales sur Fix64 (PAS un `pct*base//100` entier). `pct` = pourcentage entier
  (ex. 50 = 50%). Ordre : PercentageOf(pct, base, mode). Retour int.
- Contexte : 2 enfants + mode. Captable offline.
- NB port : pour fidelite, implementer via Fraction/Decimal a 2 decimales + arrondi mode, PAS via
  `pct*base//100` (divergerait sur les demi-unites et le half-to-even).

### TurnsFromRounds(rounds) @180dfec50  [PROUVE structure — NON captable offline]
- Classe REELLE **`TurnsFromRoundsFormula`** (singleton DAT_18328aa50), ctor @180f26be0
  `(convObj@+0x20, +0x28, rounds@+0x10)`. Les +0x20/+0x28 = champs FIXES du factory-this (contexte de
  conversion), `rounds` = arg utilisateur (ou child +0x18 si fourni).
- Calculate @180f26a50 : `n = rounds` (ou eval child +0x18) ; puis `FUN_180003b40(0x1b, convObj@+0x28, n)`
  = invoque une methode runtime (index 0x1b) qui convertit rounds -> nombre de TURNS.
- **NON captable offline de facon triviale** : la conversion rounds->turns depend de l'etat runtime
  (nombre d'equipes/joueurs actifs qui jouent dans un round). Marquer comme dependance runtime, au
  meme titre que times_attacked/times_repaired. Defaut offline a documenter (ex. identite ou
  facteur = nb equipes vivantes). Retour int.
- Contexte : rounds + objet de conversion runtime (NON dans le state offline actuel).

---

## 5. Recap non-captable-offline

- **TurnsFromRounds** : conversion rounds->turns = etat runtime (participants au round). A traiter
  comme les compteurs runtime existants (slot dedie / defaut documente).
- **Filter/Count** : captables si source+predicat le sont ; Filter EXIGE le nouveau slot `subject`.
- **PercentageOf/Divide/Half** : captables mais l'ARRONDI (mode Ceiling/Floor/Round-half-to-even) doit
  etre porte fidelement (Fix64), pas approxime en division entiere.

## 6. Points a confirmer (residuels, non bloquants)

- `AreEqual` @180de9000 et `Max` @180df62e0 : eval (Calculate) non decompilee (ctor generique
  residuel) — semantique DEDUITE du nom + usage. Si une ability du batch les branche sur des types
  non-int (AreEqual sur enums), verifier au port.
- Offset exact du slot subject dans AbilityEntities (le "0x20" de FUN_180025220 mappe vers
  `ability+0x180`) : le port peut modeliser ca abstraitement (slot `ctx.subject`) sans l'offset binaire.
