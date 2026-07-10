# DSL wave-2 — specs de port EXACTES (RE pure, build gqfc5mff6c)

Binaire ghidra `/GameAssembly.dll`, base VA 0x180000000. Toutes VAs citees = lues dans le decompile.
Cible port : `scripts/python/engine/dsl/nodes.py` (classe `Node`, `evaluate(ctx)`, `DslContext`,
unite = dict `{id,team,hp,alive,pos:{col,row},visualId}`). READ-ONLY : rien ecrit sous engine/.

Legende : [PROUVE] = decompile lu (Select/Calculate + ctor + singleton). [DEDUIT] = nom factory
non-ambigu, ctor+structure lus mais eval residuelle non decompilee.

CAVEAT MISLABEL applique partout : les ctors gshared s'affichent sous un faux nom
(`IceTileEffect<FreezeCoroutine>d__5`, `SortReverseSelector`, `HasUsedActiveAbilityThisTurnTrigger`,
`AllAliveMachinesSelector`). L'identite REELLE = le SINGLETON `DAT_*` instancie + la methode
`Select`/`Calculate` de la classe reelle. Le MEME ctor gshared sert des DIZAINES de classes ; deux
factories peuvent afficher le meme nom de ctor tout en instanciant des singletons/classes DIFFERENTS
(prouve ci-dessous : First vs Filter, Tiles vs SortReverse).

Convention selecteurs : toutes les classes `*Selector` heritent de `TestUnitProvider` (ctor pose la
source de base a `+0x10` = le `factory+0x10` = "toutes les entites"). Le vrai enfant utile est stocke
a `+0x18` (source a filtrer) et suivants. `Select(this, evalCtx)` recoit le CONTEXTE d'evaluation
(struct `AbilityEntities` ~0x130 octets : caster/target/owner/actor + slot sujet).

---

## RECAP EXECUTIF (1 ligne / noeud)

GEOMETRIE (C) :
- **Friends** @180df0040 -> list ; unites du selecteur ALLIEES au referent (arg2). ctx: referent-team (caster std).
- **Units** @180e01340 -> list ; unites DEBOUT sur les tiles du selecteur source. ctx: units + tile->unit.
- **Tiles** @180dfdc60 -> list[pos] ; MainTile de chaque unite du selecteur. ctx: units (positions).
- **First** @180defae0 -> list (0/1 elt) ; element a l'index (defaut 0) de la liste source, [] si hors borne. ctx: ordre-source.
- **Unique** @180dfeec0 -> list ; dedup (Distinct) de la source. ctx: identite d'elt.
- **UnitsWithTrait** @180e00b10 -> list ; unites source ou HasFlag(unit,traitId)==true. ctx: traits/flags par unite (NON standard offline).
- **UnitsWithoutTrait** @180e01040 -> list ; idem trait==false. ctx: idem.
- **AdjacentFriends** @180de81d0 -> list ; symetrique d'AdjacentEnemies (finit par Friends). ctx: caster-team.
- **SurroundingEnemies** @180dfc570 -> list ; anneau R des ennemis autour du caster. ctx: caster-team+pos.
- **SurroundingFriends** @180dfc640 -> list ; anneau R des allies autour du caster. ctx: caster-team+pos.
- **SortByFormula** @180dfb0a0 -> list ; tri STABLE par formule/elt ; flag=0->DESC, flag=1->ASC. ctx: slot subject (binding par-elt).
- **SortByDistance** @180dfb020 -> list ; tri STABLE ASC par distance au refPoint (arg2). ctx: refPoint (selecteur, PAS force caster).

ETAT (D) :
- **Get** @180df05d0 -> int ; = Const/Direct : enveloppe une valeur litterale int/enum en noeud. ctx: aucun.
- **ConfigVar** @180decac0 -> int ; GetVariableForLevel(key, level-runtime) : variable de config SCALEE par le niveau de l'ability de l'unite resolue. ctx: ability-level (caster std = ctx.ability_level ; autre unite = NON offline).
- **Cache** @180deb0d0 -> list ; memoise le resultat du sous-arbre (pass-through semantique). ctx: aucun (pure optim).
- **StatAmount** @180dfbf60 -> int ; SOMME GetStat(unit,statType,variant,level) sur les unites du selecteur. ctx: stat par unite (Health capte ; autres a exposer).
- **get_OwnerIsTarget** @180e026f0 -> bool ; AreEqual(Owner, Target). ctx: Owner/Target refs (runtime).
- **get_OwnerIsCaster** @180e02610 -> bool ; AreEqual(Owner, Caster). ctx: Owner/Caster refs.
- **get_OwnerIsActor** @180e02530 -> bool ; AreEqual(Owner, Actor). ctx: Owner/Actor refs.

NOUVEAUX champs DslContext requis : voir section FINALE. En bref : `unit_traits`(fn/dict, defaut
absent), `unit_stat`(fn/dict, defaut via champs existants), `owner`/`actor` (refs entite pour Owner*),
+ le slot `subject` (DEJA present wave1) reutilise par SortByFormula. Cache = AUCUN nouveau champ.

===================================================================================================
## PARTIE C — GEOMETRIE / SELECTEURS
===================================================================================================

## C1. Friends @180df0040  [PROUVE]

- Factory : singleton `DAT_1831cb890`, classe REELLE `UnitsByTeamSelector`.
  `ctor(this, factory+0x10, referent@param2, source@param3, flag=1, param4, 0)` (ctor @180f00af0).
  Le `1` (5e arg) -> `+0x28` = discriminant "friendly".
- Enemies @180deedd0 = MEME classe, MEME ctor, mais **flag=0** (prouve cote a cote). SYMETRIE EXACTE.
- Select @180f009e0 -> CountOrAdd @180f00570 : pour chaque candidate,
  `IsFriend(referent@+0x18, candidate, source) == (+0x28)`. Garde si egal.
  -> Friends garde `IsFriend==true`, Enemies garde `IsFriend==false`.
- **Referent d'equipe = arg2 de la factory (`+0x18`), PAS forcement le caster global.** Dans les
  compositions Adjacent*/Surrounding* c'est le caster passe en param2. Le port actuel `Enemies`
  compare vs `ctx.caster["team"]` : CORRECT tant que le referent = caster (cas standard). Pour rester
  fidele au general, le referent devrait etre le 1er arg de l'arbre (souvent CasterTile/caster).
- Retour : **list[unit]**. Ordre operandes : referent(1), source(2).
- ctx requis : `ctx.caster.team` (referent std) + la source (selecteur enfant). Captable offline.
- PORT : symetrique d'`Enemies` deja porte :
  `Friends(inner).evaluate = [u for u in inner if u.team == referent_team]`.
  Recommande : `class Friends(Node)` prenant `inner`, filtre `u.get("team") == (ctx.caster or {}).get("team")`.

## C2. Units @180e01340  [PROUVE]

- Factory : singleton `DAT_1831cc3a8`, classe REELLE `UnitsOnTilesSelector`.
  `ctor(this, factory+0x10, tilesSource@param2, boolMode@param3, param4, 0)` (ctor @180f025e0 :
  `+0x18`=source, `+0x20`=bool, `+0x24`=param5).
- Select @180f02450 : selon `+0x20` (bool) invoque `FUN_180025220` avec index 3 (mode occupant
  "main"/steppable) ou 4 (autre mode d'occupation) sur la source de tiles -> unites presentes dessus.
  Le bool `param3` = variante d'occupation (unite principale vs steppable). Par defaut (0) -> mode 3.
- Retour : **list[unit]** (les unites debout sur les tiles). Ordre : tilesSource(1), mode(2).
- ctx requis : `ctx.units` + mapping position->unite (une tile "occupee" = une unite dont pos == tile).
- **DEJA porte inline** dans `SurroundingUnits`/`AdjacentEnemies` (via `_within` qui teste les positions).
  A generaliser : `Units(tilesSelector)` = les unites de `ctx.units` dont `_pos(u) in tiles`.
- PORT : `Units(inner).evaluate = [u for u in ctx.units if _pos(u) in set(inner.evaluate(ctx))]`
  (inner renvoie une liste de positions). Mode occupation (steppable) = raffinement inerte offline
  tant qu'on ne modelise qu'une unite par tile.

## C3. Tiles @180dfdc60  [PROUVE]

- Factory : singleton **`DAT_183278e98`** (class-ptr, bytes `3f8c0120...`), ctor AFFICHE
  `SortReverseSelector.ctor` -> **MISLABEL**. La classe REELLE = `UnitsMainTilesSelector`
  (verifie : SortReverse factory @180dfb270 instancie `DAT_18322b588`, DIFFERENT de `DAT_183278e98`).
  ctor(this, source@param2, factory+0x10, 0).
- Select = `UnitsMainTilesSelector.Select @180f02150` : enumere les UNITES de la source `+0x18`,
  pour chacune `EntityExtensions.GetMainTile(unit)` -> ajoute la tile. Retourne la liste des tiles.
- **Semantique : unites -> leurs tuiles principales.** (Le nom mislabel "SortReverse" est FAUX.)
- Retour : **list[position]** (tiles). Ordre : source(1).
- ctx requis : `ctx.units` (positions). Captable offline.
- PORT : `Tiles(inner).evaluate = [_pos(u) for u in inner.evaluate(ctx) if _pos(u)]`.
  (Utilise deja dans Surrounding*/AdjacentFriends pour retirer la tuile du caster.)

## C4. First @180defae0  [PROUVE]

- Factory @180defae0 (overload int, 128 refs) : enveloppe l'index brut `param3` en noeud Const
  (`DAT_183202d40` = classe Const/Direct, ctor `(index,0)`) PUIS delegue a l'overload reel
  @180defa40 (19 refs).
- Overload reel @180defa40 : singleton **`DAT_183285620`**, classe REELLE = **`PickAtIndexSelector`**
  (verifie : ce singleton != celui de Filter `DAT_1832409e0`, malgre le meme nom de ctor mislabel
  `FromTriggerSelector.ctor`). ctor(this, factory+0x10, source@param2, indexNode@param3, flag@param4, 0).
- Select = `PickAtIndexSelector.Select @180ef02e0` : resout la source `+0x18` en IEnumerable ->
  **`ToList`** (ordre de la liste TEL QUEL, aucun tri interne) -> si `index(+0x20) < list.Count`
  retourne une liste-singleton `[list[index]]`, SINON retourne une liste VIDE.
- **Semantique : element a l'index donne (defaut 0 = premier) de la liste source, [] si hors borne.**
  Ordre = celui de la liste source (donc First s'appuie sur un tri prealable si l'appelant en pose un,
  ex. SortByDistance puis First). Le flag `+0x28` (param4) N'EST PAS lu par Select (residuel).
- Retour : **list[unit]** de 0 ou 1 element (PAS un element nu). Ordre : source(1), index(2, defaut 0).
- ctx requis : la source (selecteur enfant). Captable offline.
- PORT : `First(source, index=0).evaluate`: `lst = source.evaluate(ctx); return [lst[index]] if index < len(lst) else []`.

## C5. Unique @180dfeec0  [PROUVE structure / DEDUIT semantique]

- Factory : singleton `DAT_1831c18d0`, ctor AFFICHE `AllAliveMachinesSelector.ctor` -> MISLABEL.
  ctor(this, factory+0x10, source@param2, 0) (@180ee00d0 : `+0x18`=source).
- Select @180ee0080 : `FUN_180004fd0(0x95, singleton, source@+0x18, 0)` = UN appel LINQ generique
  (index de methode 0x95) enveloppant la source unique -> pattern **Distinct** (dedup).
- **Semantique DEDUITE (nom factory `Unique` non-ambigu + pattern mono-source LINQ) : dedup de la
  source.** Le critere de dedup = l'egalite d'ELEMENT (reference d'entite / EqualityComparer par
  defaut du type generique) -> pour des unites, dedup par IDENTITE d'entite (== par id).
- Retour : **list[unit]** dedupe (ordre de 1re apparition preserve par Distinct .NET). Ordre : source(1).
- ctx requis : la source. Captable offline.
- PORT : `Unique(source).evaluate` = dedup stable par `u["id"]` :
  `seen=set(); out=[]; for u in source.evaluate(ctx): id=u.get("id"); if id not in seen: seen.add(id); out.append(u); return out`.
- A CONFIRMER si doute : le FUN_180004fd0(0x95) n'est pas nomme -> si un cas montre un dedup par autre
  cle (visualId/tile), verifier. Par defaut : dedup par id.

## C6. UnitsWithTrait @180e00b10 / UnitsWithoutTrait @180e01040  [PROUVE]

- Les deux : singleton `DAT_1831cd4f0`, classe REELLE `UnitsWithFlagSelector`.
  `ctor(this, factory+0x10, source@param2, traitId@param3, flag, param4, 0)` (@180f04340 :
  `+0x18`=source, `+0x20`=traitId, `+0x24`=flag(bool), `+0x28`=param6).
  UnitsWithTrait -> **flag=1** ; UnitsWithoutTrait -> **flag=0** (prouve cote a cote).
- Select @180f04030 : enumere la source `+0x18`, pour chaque unite
  `UnitExtensions.HasFlag(unit, traitId@+0x20)` -> garde si `HasFlag == (+0x24)`.
- **Point vocabulaire cle : "trait" est teste par `UnitExtensions.HasFlag(unit, id)` — meme primitive
  que HasFlag. Le `traitId` (param3) est un enum UnitFlag/trait.** WithTrait garde ceux qui ONT,
  WithoutTrait ceux qui N'ONT PAS.
- Retour : **list[unit]**. Ordre : source(1), traitId(2).
- ctx requis : **les traits/flags PAR UNITE** — NON present dans le state standard `{id,team,hp,alive,
  pos,visualId}`. Necessite d'exposer un test `has_trait(unit, id)` (nouveau champ DslContext, cf.
  section finale). Sans ca -> filtre degrade (documenter : WithTrait=[] / WithoutTrait=source si on
  suppose "aucun trait connu", a choisir selon la mecanique).
- PORT :
  `UnitsWithTrait(source, trait).evaluate = [u for u in source.evaluate(ctx) if ctx.has_trait(u, trait)]`
  `UnitsWithoutTrait(...) = [u for u in source.evaluate(ctx) if not ctx.has_trait(u, trait)]`.

## C7. AdjacentFriends @180de81d0  [PROUVE — composition]

- Composition native EXACTE (pas de classe dediee) :
  ```
  ring  = AdjacentTiles(caster@param2)             # anneau adjacent (tiles) du caster
  units = Units(ring, mode@param3)                 # unites debout dessus
  units = op_Subtraction(units, caster@param2)     # retire le caster lui-meme (par id)
  return  Friends(caster@param2, units, param4)     # garde ceux ALLIES au caster
  ```
- Symetrique EXACT d'`AdjacentEnemies` deja porte (qui finit par `Enemies` au lieu de `Friends`).
- Retour : **list[unit]** (allies adjacents, self exclu). Ordre : caster(1).
- ctx requis : `ctx.caster` (pos + team) + `ctx.units`. Captable offline.
- PORT : cf. `AdjacentEnemies` existant, remplacer le filtre final `team != ct` par `team == ct` :
  `ring=_within(ctx.units, center, radius=1); ct=(ctx.caster or {}).get("team");`
  `return [u for u in ring if u.get("team")==ct]` (self deja exclu par _within d>0).
  (radius par defaut 1 comme AdjacentEnemies ; AdjacentTiles = anneau R1.)

## C8. SurroundingEnemies @180dfc570 / SurroundingFriends @180dfc640  [PROUVE — composition]

- Composition native EXACTE (les deux, seul le filtre final differe) :
  ```
  ring  = SurroundingTiles(caster@param2, 1, radius@param3, ...)   # anneau rayon R (tiles), centre inclus
  ring  = op_Subtraction(ring, Tiles(caster@param2))              # retire la tuile du caster
  units = Units(ring, mode@param4)                                # unites debout dessus
  return  Enemies/Friends(caster@param2, units, param5)            # filtre equipe
  ```
  (SurroundingEnemies -> Enemies ; SurroundingFriends -> Friends. Symetriques de SurroundingUnits.)
- Retour : **list[unit]** dans le rayon, centre exclu, filtre equipe. Ordre : caster(1), radius(2).
- ctx requis : `ctx.caster` (pos+team) + `ctx.units`. Captable offline.
- PORT : reutiliser `_within(ctx.units, center=CasterTile, radius)` (centre deja exclu, include_center
  False) puis filtrer `team != ct` (Enemies) ou `team == ct` (Friends). Equivaut a
  `Enemies(SurroundingUnits(CasterTile, radius))` / `Friends(SurroundingUnits(...))`.

## C9. SortByFormula @180dfb0a0  [PROUVE — TRICKY resolu]

- Factory : singleton `DAT_18322aa48`, classe REELLE `SortByFormulaSelector`.
  `ctor(this, source@param2, formula@param3, factory+0x10, flag@param4, 0)` (@180ef32b0 :
  `+0x18`=source, `+0x20`=formula, `+0x28`=flag bool).
- Select @180ef3010 :
  1. construit un state-machine (`lVar12`) qui porte `param_1`(=le selector this) a `+0x140`
     -> permet au keySelector d'evaluer la formula avec acces au contexte.
  2. resout la source `+0x18` en IEnumerable.
  3. **si `+0x28 == 0` -> `OrderByDescending`** (delegate keySelector `DAT_1831bb508`).
     **si `+0x28 != 0` -> `OrderBy`** (ascendant, delegate `DAT_1831bb648`).
  4. `ToList`.
- Le keySelector evalue **la formula PAR ELEMENT** : chaque element courant est injecte dans le
  contexte d'eval de la formula. C'est le MEME mecanisme de binding que Filter (l'element courant ->
  slot sujet de l'AbilityEntities). **-> SortByFormula utilise le binding `subject` (comme Filter).**
  La formula est un sous-arbre DSL numerique lisant `Subject` (= `ctx.subject`).
- **Sens du tri : flag(param4)=0 (defaut) => DESCENDANT ; flag=1 => ASCENDANT.** Tri STABLE
  (`Enumerable.OrderBy`/`OrderByDescending` .NET = mergesort stable : elements de meme cle gardent
  l'ordre source).
- Retour : **list[unit]** triee. Ordre operandes : source(1), formula(2), ascending(3, defaut false=DESC).
- ctx requis : la source + la formula (evaluee avec `subject`=element courant). Captable offline SI la
  formula ne depend que d'etat capte.
- PORT :
  ```
  class SortByFormula(Node):  # SortByFormulaSelector.Select @180ef3010
      def __init__(self, source, formula, ascending=False):
          self.source, self.formula, self.ascending = source, formula, ascending
      def evaluate(self, ctx):
          lst = list(self.source.evaluate(ctx))
          key = lambda u: self.formula.evaluate(replace(ctx, subject=u))
          return sorted(lst, key=key, reverse=not self.ascending)   # Python sorted = STABLE
  ```
  (`sorted` Python est stable -> fidele a OrderBy/OrderByDescending .NET.)

## C10. SortByDistance @180dfb020  [PROUVE — TRICKY resolu]

- Factory : singleton `DAT_18322a908`, classe REELLE `SortByDistanceSelector`.
  `ctor(this, source@param2, refPoint@param3, factory+0x10, 0)` (@180ef2fd0 :
  `+0x18`=source, `+0x20`=refPointSelector).
- Select @180ef2ce0 :
  1. resout la source `+0x18` en IEnumerable.
  2. resout le **refPoint** via `FUN_180024d10(0xc, ..., +0x20, ctx)` (index 0xc = resolution en une
     position/tile de reference) -> stocke dans le state `+0x18`.
  3. **`OrderBy`** (ASCENDANT) avec keySelector = distance de chaque element au refPoint. `ToList`.
- **Point de reference = arg2 de la factory (un SELECTEUR de tile/unite, ex. CasterTile ou TargetTile),
  PAS force le caster.** C'est explicite et parametrable.
- **Sens du tri : ASCENDANT par distance croissante (plus proche EN PREMIER). PAS de flag descending.**
  Tri STABLE (OrderBy .NET).
- Retour : **list[unit]** triee proche->loin. Ordre : source(1), refPoint(2).
- ctx requis : la source + le refPoint (resolu en position). Distance = `hexgeo.distance`. Captable offline.
- PORT :
  ```
  class SortByDistance(Node):  # SortByDistanceSelector.Select @180ef2ce0
      def __init__(self, source, ref_point):  # ref_point = Node -> position (CasterTile/TargetTile/...)
          self.source, self.ref_point = source, ref_point
      def evaluate(self, ctx):
          rp = self.ref_point.evaluate(ctx)     # position (col,row)
          lst = list(self.source.evaluate(ctx))
          return sorted(lst, key=lambda u: hexgeo.distance(_pos(u), rp))   # ASC, stable
  ```
  Si `ref_point` resout une UNITE (pas une position), prendre `_pos(ref_unit)`.

===================================================================================================
## PARTIE D — ACCESSEURS D'ETAT
===================================================================================================

## D1. Get @180df05d0  [PROUVE — verdict : c'est Const/Direct]

- L'overload du batch (`param_2 = undefined4` = un int/enum brut) : singleton **`DAT_183202d40`**,
  ctor `(value, 0)` (@180df05d0). **IDENTIQUE a `Direct @180dee2a0`** (meme singleton `DAT_183202d40`,
  meme ctor `(value,0)`) -> `Direct` = `Const` (etabli wave1). DONC **`Get @180df05d0` = Const : un
  noeud CONSTANTE LITTERALE qui enveloppe une valeur brute int/enum en Node.**
- Le nom de ctor affiche `IceTileEffect<FreezeCoroutine>d__5.ctor` est un MISLABEL gshared pur (ce
  trampoline .ctor a refcount 2029, partage par des centaines de types) -> la classe reelle est le
  noeud constante `Formulas.Direct/ConstantAmount`, PAS un accesseur.
- **CE N'EST NI de la persistent-data NI une propriete NI un indexeur.** C'est le wrapper "valeur ->
  noeud" utilise partout ou une factory attend un `Node` mais recoit un int/enum nu (ex. un StatType
  passe a StatAmount, un index passe a First/AtIndex, un flag-id). Le catalogue "accesseur generique"
  etait trompeur (base sur le mislabel).
- ATTENTION overloads distincts (hors batch, semantiques DIFFERENTES, ne pas confondre) :
  `Get @180df0690` (arg objet) -> `AllAliveMachinesSelector` (singleton `DAT_18321cd70`) ;
  `Get @180df0630` (arg objet) -> singleton `DAT_183203380` via TestUnitProvider. Le BATCH cible
  UNIQUEMENT `@180df05d0` (arg int/enum) = Const.
- Retour : **int** (la valeur litterale). ctx requis : AUCUN.
- PORT : reutiliser la classe `Const` existante. `Get(x)` == `Const(x)`. (Optionnel : un alias
  `Get = Const` pour coller au nom natif, mais NE PAS creer une nouvelle classe divergente.)

## D2. ConfigVar @180decac0  [PROUVE — vs ConfigConst tranche]

- Factory : singleton `DAT_1831d03d0`, classe REELLE `Formulas.ConfigAmount`.
  `ctor(this, factory+0x28, param4, keyEnum@param3, param2, 0)` (plusieurs overloads @180f179e0+ ;
  le noeud porte des champs Nullable `+0x30`/`+0x38`/`+0x40`/`+0x48` = differentes sources de cle).
- Calculate @180f171c0 (branche principale, cle `+0x30` string) :
  1. `GetAbilityState(this, ctx)` (@180f175a0) -> resout l'ability-instance/level sur l'unite courante
     (owner/caster/actor selon les champs) et son AbilityConfiguration.
  2. `AbilityConfiguration.GetVariableForLevel(config, key, level)` -> **valeur du tableau de config
     INDEXEE PAR LE NIVEAU** de l'ability sur l'unite resolue.
  (Branche alternative `+0x38` : `GetNumberConstant(key)` = constante fixe -> equivalent ConfigConst.)
- **DIFFERENCE PROUVEE ConfigConst vs ConfigVar :**
  - **ConfigConst** -> `GetNumberConstant(key)` @181576af0 = `Int32.Parse(GetStringConstant(key))` :
    constante STRING de config, **INDEPENDANTE du niveau**.
  - **ConfigVar (ConfigAmount)** -> `GetVariableForLevel(key, level)` @181576fb0 =
    `TryGetVariableArrayForLevel(key, level)` -> `array[level].value` : **variable SCALEE par le
    NIVEAU** de l'ability, level lu au RUNTIME via GetAbilityState sur l'unite resolue.
- **>> RESERVE FIDELITE (a remonter, hors batch) :** le port actuel `ConfigConst.evaluate` appelle
  `ctx.config.get_variable_for_level(key, ability_level)` -> c'est le comportement de **ConfigVar**,
  pas de ConfigConst (qui devrait etre `GetNumberConstant`, sans niveau). Soit le wrapper Python
  `get_variable_for_level` fait deja la bonne chose pour les deux (a verifier cote AbilityConfiguration
  wrapper), soit ConfigConst/ConfigVar doivent appeler des chemins distincts. Le validator devrait
  trancher : la table de config expose-t-elle number-constant (fixe) vs variable-array (par niveau) ?
- **NON captable offline (cas general) :** le NIVEAU utilise = niveau de l'ability sur l'unite RESOLUE
  (owner/caster/actor). Pour le CASTER au niveau courant -> `ctx.ability_level` (deja capte). Pour une
  AUTRE unite (GetAbilityState d'une entite tierce) -> le niveau de SON ability n'est pas trivialement
  offline (dependance runtime, cf. times_attacked). Cas standard = caster.
- Retour : **int**. Ordre operandes : keyEnum(param3) + slots owner/level du factory-this.
- PORT (cas standard caster) : proche de ConfigConst mais chemin "variable par niveau" explicite :
  `ConfigVar(key).evaluate = ctx.config.get_variable_for_level(key, ctx.ability_level, default)`.
  Distinguer explicitement de ConfigConst (number-constant fixe) selon le verdict validator ci-dessus.

## D3. Cache @180deb0d0  [PROUVE]

- Factory : singleton `DAT_1832820c8`, classe REELLE `CacheSelector`.
  `ctor(this, factory+0x10, source@param2, flag@param3, 0)` (@180ee38a0 :
  `+0x18`=source, `+0x20`=flag "keyed" bool, `+0x28`=resultat memoise (init 0), `+0x30`=Dictionary vide).
- Select @180ee35f0 :
  - si `+0x20 == 0` (NON keyed) : `cached = +0x28` (resultat memoise unique, scalaire).
  - si `+0x20 != 0` (keyed) : `Dictionary.TryGetValue(+0x30, CLE = le contexte d'eval param_2)` -> `cached`.
  - si `cached != 0` -> **retourne le cache**.
  - sinon : evalue la source `+0x18` -> `ToList` ; stocke dans `+0x28` ET `dict[ctx] = result`
    (`+0x30`) ; retourne.
- **Cle de cache = l'AbilityEntities (contexte d'eval COMPLET : caster/target/owner/actor).**
- **Portee = l'INSTANCE du noeud CacheSelector.** L'arbre d'ability etant construit une fois et
  reutilise, le cache persiste ENTRE evaluations tant que l'instance vit. **Aucune invalidation
  explicite** (le dict croit). En pratique = "n'evalue le sous-arbre qu'une fois par contexte distinct".
- **Semantiquement TRANSPARENT** : le resultat est IDENTIQUE a evaluer la source directement. Le port
  offline (qui recalcule a chaque fois) est fidele en VALEUR ; la seule divergence est la perf/le
  partage d'objet (non observable sur les valeurs).
- Retour : **list** (ou valeur du sous-arbre). Ordre : source(1), keyed(2).
- ctx requis : la source. AUCUN nouveau champ. Captable offline.
- PORT (pass-through, divergence perf assumee) :
  `class Cache(Node): __init__(self, source): self.source=source
   def evaluate(self, ctx): return self.source.evaluate(ctx)`
  (Optionnel : memo par id(ctx) si perf necessaire — non requis pour la fidelite.)

## D4. StatAmount @180dfbf60  [PROUVE — TRICKY]

- Factory : singleton `DAT_18323bac0`, classe REELLE `Formulas.StatAmountFormula`.
  `ctor(this, unitSelector@param2, statType@param3, statVariant@param4, levelFormula@param5, param6, 0)`
  (@180f230f0 : `+0x10`=selecteur, `+0x18`=statType, `+0x1c`=statVariant, `+0x20`=levelFormula(opt),
  `+0x28`=param6).
- Calculate @180f22d40 :
  1. si `+0x20` (levelFormula) != 0 : l'evalue -> un niveau (Nullable<int>) passe a GetStat.
  2. enumere les UNITES du selecteur `+0x10` ; pour chaque unite :
     `iVar8 = UnitExtensions.GetStat(unit, statType@+0x18, statVariant@+0x1c, levelNullable)` ;
     **`total += iVar8`** (SOMME).
  3. retourne `total`.
- **Semantique : SOMME de GetStat sur TOUTES les unites du selecteur.** Pour un selecteur singleton
  (le caster via un slot owner), c'est la stat d'UNE unite. Pour un selecteur multi (ex.
  SurroundingEnemies) c'est la somme.
- **De QUELLE unite ?** = du selecteur `param2` (1er arg). La note nodes.py "StatAmount(@0x160,Health)
  =maxHP caster" : le `@0x160` = un SELECTEUR owner/caster resolu (slot du contexte d'eval), pas un
  offset dans StatAmount. Le statType (`+0x18`) = enum StatType (Health, etc.) ; statVariant (`+0x1c`)
  = variante (base/current/max — a mapper selon les usages ; pour Health le port existant lit maxHP).
- **NON captable offline (cas general) :** le state standard expose `hp` (current) et implicitement
  maxHP via templates ; les AUTRES StatType (Armour, Damage, ...) et variantes ne sont PAS dans
  `{id,team,hp,alive,pos,visualId}`. Necessite un accesseur `get_stat(unit, statType, variant)`
  (nouveau champ, cf. section finale). Le levelFormula (`+0x20`) = dependance runtime si != caster.
- Retour : **int** (somme). Ordre : selecteur(1), statType(2), variant(3), levelFormula(4, opt).
- PORT :
  ```
  class StatAmount(Node):  # StatAmountFormula.Calculate @180f22d40
      def __init__(self, selector, stat_type, variant=0, level=None):
          self.selector, self.stat_type, self.variant, self.level = selector, stat_type, variant, level
      def evaluate(self, ctx):
          lvl = self.level.evaluate(ctx) if self.level else None
          return sum(ctx.get_stat(u, self.stat_type, self.variant, lvl) for u in self.selector.evaluate(ctx))
  ```
  `ctx.get_stat` = nouveau champ (defaut : Health->hp/maxHP via templates deja disponibles).

## D5-D7. get_OwnerIsTarget / get_OwnerIsCaster / get_OwnerIsActor  [PROUVE]

- Les trois : singleton **`DAT_183200238`** = comparateur d'egalite generique 2-arg (**LE MEME
  singleton que `AreEqual` @180de9000** du wave1). ctor mislabel affiche
  `HasUsedActiveAbilityThisTurnTrigger.ctor` -> MISLABEL. ctor `(this, A, B, 0)`.
- Les operandes A/B = des noeuds-REFERENCE pre-construits stockes sur le `DSLFactory`-this (champs
  fixes, initialises au ctor du factory) :
  - **`+0x148` = Owner** (commun aux trois : c'est le 1er operande A partout).
  - **`+0x158` = Actor**, **`+0x160` = Caster**, **`+0x178` = Target**.
  - get_OwnerIsTarget @180e026f0 : `AreEqual(Owner=+0x148, Target=+0x178)`.
  - get_OwnerIsCaster @180e02610 : `AreEqual(Owner=+0x148, Caster=+0x160)`.
  - get_OwnerIsActor  @180e02530 : `AreEqual(Owner=+0x148, Actor=+0x158)`.
- **Semantique : predicat bool "l'entite OWNER est-elle la MEME entite que Target/Caster/Actor ?"**
  (egalite de reference d'entite resolue au runtime). "Owner" = le proprietaire de l'effet/ability en
  cours ; "Caster" = qui lance ; "Actor"/"Target" = acteur/cible du contexte. Ces 4 references sont
  des roles distincts de l'AbilityEntities ; souvent Owner==Caster mais pas toujours (effets
  transferes, buffs sur autrui, triggers).
- **>> Espaces d'offsets a NE PAS confondre :** ici `+0x148/+0x158/+0x160/+0x178` = slots du
  **DSLFactory-this** (noeuds-reference pre-construits). C'est DISTINCT de l'AbilityEntities contexte
  d'eval (la struct ~0x130 passee a Select/Calculate) et du `+0x180` = OriginalTarget/sujet observe
  dans les predicats sous Filter (wave1). Trois espaces d'adresses distincts.
- Retour : **bool**. ctx requis : les references Owner/Target/Caster/Actor resolues au runtime.
- **NON captable offline directement** : le state standard n'expose pas explicitement les 4 roles
  distincts owner/actor/caster/target comme entites separees. On a `ctx.caster` et `ctx.target` ;
  il faut ajouter `ctx.owner` et `ctx.actor` (nouveaux champs). Cas standard offline : Owner==Caster
  -> get_OwnerIsCaster=True, get_OwnerIsTarget = (caster is target), get_OwnerIsActor = (caster is actor).
- PORT :
  ```
  class OwnerIsTarget(Node):  # AreEqual(Owner, Target) @180e026f0
      def evaluate(self, ctx): return _same_entity(ctx.owner or ctx.caster, ctx.target)
  class OwnerIsCaster(Node):  # @180e02610
      def evaluate(self, ctx): return _same_entity(ctx.owner or ctx.caster, ctx.caster)
  class OwnerIsActor(Node):   # @180e02530
      def evaluate(self, ctx): return _same_entity(ctx.owner or ctx.caster, ctx.actor or ctx.caster)
  # _same_entity(a,b) = a is b OR a.get("id")==b.get("id")
  ```
  Defaut `ctx.owner=None` -> retombe sur caster (Owner==Caster, hypothese standard documentee).

===================================================================================================
## NOUVEAUX CHAMPS DslContext REQUIS (avec defaut propose)
===================================================================================================

1. **`owner: dict | None = None`** — role OWNER de l'AbilityEntities (proprietaire de l'effet/ability
   en cours ; slot factory `+0x148`). Requis par get_OwnerIs*. DEFAUT None -> les predicats retombent
   sur `ctx.caster` (hypothese standard Owner==Caster, documentee comme divergence assumee).

2. **`actor: dict | None = None`** — role ACTOR de l'AbilityEntities (slot factory `+0x158`). Requis
   par get_OwnerIsActor. DEFAUT None -> retombe sur `ctx.caster`.

3. **`has_trait: callable | None = None`** — predicat `has_trait(unit, traitId) -> bool` (mirror de
   `UnitExtensions.HasFlag(unit, id)`). Requis par UnitsWithTrait/WithoutTrait (et generalisera le
   futur HasTrait predicat). DEFAUT None -> filtre degrade documente (proposer : traiter comme "trait
   absent" => WithTrait=[] / WithoutTrait=source, OU exposer les traits via le state kit unit_map).
   Alternative : champ `unit_traits: dict[id -> set[traitId]]` si un dict est plus simple qu'un callable.

4. **`get_stat: callable | None = None`** — accesseur `get_stat(unit, statType, variant, level) -> int`
   (mirror de `UnitExtensions.GetStat`). Requis par StatAmount (generalisation). DEFAUT None -> chemin
   degrade : Health/maxHP via les champs `hp` + templates deja dispo (le port existant lit deja maxHP
   caster) ; autres StatType a exposer quand une ability les reference.

5. **`subject`** — DEJA present (wave1, slot `ability+0x180` / OriginalTarget). REUTILISE tel quel par
   SortByFormula (binding par-element de la formula de tri). AUCUN nouveau champ.

Cache = AUCUN nouveau champ (pass-through). Get = AUCUN (== Const). Friends/Units/Tiles/First/Unique/
Adjacent*/Surrounding* = captables avec les champs existants (units/caster + le team du referent).

===================================================================================================
## VERDICT sur les 3 plus TRICKY
===================================================================================================

- **Get @180df05d0 : c'est Const/Direct.** Meme singleton `DAT_183202d40` et meme ctor `(value,0)`
  que `Direct` (= Const, etabli wave1). Le nom `IceTileEffect...d__5` est un mislabel gshared pur ; la
  classe reelle est le noeud CONSTANTE LITTERALE. Get(x) enveloppe un int/enum brut en Node. PAS de
  persistent-data, PAS de propriete. Port = alias/reuse de `Const`. (Les autres overloads `Get
  @180df0690/@180df0630`, sur arg objet, sont des SELECTEURS distincts, hors batch.)

- **Cache @180deb0d0 : cle = le contexte d'eval (AbilityEntities), portee = l'instance du noeud.**
  `CacheSelector` (singleton `DAT_1832820c8`) : dict `+0x30` clef par le contexte complet, resultat
  scalaire `+0x28` pour le mode non-keyed ; pas d'invalidation. Semantiquement TRANSPARENT (memoise le
  sous-arbre). Port = pass-through (`Cache(source)==source.evaluate(ctx)`) — divergence perf assumee,
  VALEUR identique.

- **SortByFormula @180dfb0a0 : binding `subject` OUI, sens flag=0->DESC / flag=1->ASC, STABLE.**
  `SortByFormulaSelector` (singleton `DAT_18322aa48`) : evalue la formula PAR ELEMENT via le meme
  binding que Filter (element courant -> slot `subject` de l'AbilityEntities), puis OrderByDescending
  si flag(param4)==0 (DEFAUT), OrderBy (ascendant) si flag==1. Tri STABLE (mergesort .NET) -> `sorted`
  Python (stable) avec `reverse=not ascending`. (SortByDistance = variante figee : ASC par distance au
  refPoint arg2, sans flag, STABLE.)
