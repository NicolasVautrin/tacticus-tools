# Validation adversariale OFFLINE — nœuds DSL waves 1+2 (`engine/dsl/nodes.py`)

Build **gqfc5mff6c**, binaire `/GameAssembly.dll`, base VA 0x180000000. ghidra-mcp (port 13337).
Méthode : re-décompilation native à chaque VA + re-dérivation indépendante de la sémantique, puis
confrontation au port. Deux étages exécutés :
1. **Conformité statique** (décompilé natif vs Python) — le cœur de cette passe.
2. **Reproduction from-scratch OFFLINE** : import du module + tests sémantiques par-nœud
   (auto-vérifiés, aucune valeur codée en dur du live) + **simulation BIT-EXACTE de Fix64**
   (Round/Ceiling/Floor/op_Division/op_Multiply/op_Explicit tous lus dans le décompilé) pour
   Divide/PercentageOf.

Hors scope (délégué à l'orchestrateur) : agrément LIVE. Aucun runner/RPC/reinject touché.

---

## VERDICT PAR NŒUD

### WAVE 1

| Nœud | VA | Verdict | Note |
|---|---|---|---|
| Filter | 180def870→df00e0→eebaa0 | **CONFORME** | thunk→FromTrigger→FromTriggerSelector.Select. Binding item confirmé : `FUN_180025220(...,+0x20,ctxCopy,0x20)` injecte l'item courant au slot sujet d'une COPIE du contexte, puis évalue le prédicat. Port `predicate.evaluate(replace(ctx, subject=item))` = mirror exact (copie + slot subject). flag=0 → pas de short-circuit (accumulation complète). |
| Count | 180decfa0→f18040 | **CONFORME** | Calculate = cardinal du sélecteur +0x10. `len(selector.evaluate(ctx))`. |
| AreEqual | 180de9000 | **CONFORME (déduit)** | Singleton `DAT_183200238`, ctor (a,b,0) — MÊME singleton que OwnerIs*. Eval résiduelle non décompilée mais == établi par usage OwnerIs*. Seul écart possible : comparaison de types non-int (théorique). |
| AmountIsEqual | 180de8820→ee0bd0 | **CONFORME** | `return iVar14==iVar15` = a==b. |
| AmountIsGreater | 180de8a40→ee11f0 | **CONFORME** | Singleton `DAT_1832482b0` (DISTINCT). ShouldTrigger `return iVar16(b,+0x20) < iVar15(a,+0x10/18)` = **a>b STRICT**. Ordre a/b re-vérifié via ctor+slots. |
| AmountIsEqualOrGreater | 180de8660→ee0e00 | **CONFORME** | Singleton `DAT_183248030` (DISTINCT). `return iVar16(b) <= iVar15(a)` = **a>=b**. 2 singletons distincts confirmés (strict vs non-strict) malgré ctor mislabel commun. |
| AmountIsGreaterThanZero | 180de88f0 | **CONFORME** | ctor(a, factory+0xb8=Const 0) sur DAT_1832482b0 = a>0. |
| AmountIsZero | 180de8b10 | **CONFORME** | ctor(a, factory+0xc0=Const 1) sur DAT_183248030 + op_LogicalNot = NOT(a>=1) = **a<=0** (PAS a==0). Confirmé. |
| AmountIsOdd | 180de8ab0→ee10e0 | **CONFORME** | AmountIsEven `return ~(byte)val & 1` (pair) ; Odd=NOT = (a&1)==1. |
| Max | 180df62e0 | **CONFORME (déduit)** | Singleton `DAT_1832457c8`, ctor (a,b,0). Eval résiduelle ; usage NonLethalDamage = max. |
| Divide | 180dee5a0→f19800 | **CONFORME** | `FromInt(a)/FromInt(b)` puis `RoundFix64Result(_, mode@ctor+0x20)`. mode 1=Ceiling/2=Floor/0=Round-half-to-even. **Sim bit-exacte : 0 mismatch** sur a∈[-40,40]×b∈[±1,±24]×mode. |
| Half | 180df0840 | **CONFORME** | = Divide(a,2,mode), même arrondi Fix64. Testé (2.5→2 even, ceil→3, floor→2). |
| Double | 180dee6f0 | **CONFORME** | Multiply(a,2) entier exact. |
| Negative | 180df7090 | **CONFORME** | Multiply(a,-1) = -a. |
| Modulo | 180df69a0→eeda30 | **CONFORME** | ShouldTrigger `return iVar15 % iVar16 == iVar17` = **(a mod b)==c PRÉDICAT bool**, modulo C signé (opérandes int). Port `_c_mod` (trunc vers zéro) + prédicat. Testé -7%3==-1. |
| PercentageOf | 180df8720→f20fc0 | **CONFORME** | CalculateInternal reconstruit pas-à-pas (Fix64 : base/100*100, Round, /100, *pct, *100, Round, /100, RoundFix64Result mode). **Sim bit-exacte : 0 mismatch** sur pct∈[-50,300]×base∈[0,10000]×mode, incluant ancres 665/499/582/2873. L'affirmation "arrondis 2-décimales inertes pour entiers" TIENT malgré l'erreur binaire Fix64. |
| TurnsFromRounds | 180dfec50→f26a50 | **A-VALIDER-LIVE** | Conversion rounds→turns via méthode runtime index 0x1b (nb d'équipes actives). Port marque non-captable (`turns_per_round` défaut 1 = identité). Correctement flaggé non-captable. |

### WAVE 2

| Nœud | VA | Verdict | Note |
|---|---|---|---|
| Get | 180df05d0 | **CONFORME** | Singleton `DAT_183202d40` + ctor (value,0) IDENTIQUES à Direct @180dee2a0 (=Const). `class Get(Const)` exact. |
| ConfigVar | 180decac0→f171c0 | **CONFORME** (réserve tranchée) | voir section RÉSERVE ci-dessous. |
| Cache | 180deb0d0→ee35f0 | **CONFORME** | CacheSelector = memo transparent en valeur ; pass-through fidèle (divergence perf seule, non observable). |
| StatAmount | 180dfbf60→f22d40 | **CONFORME structure ; A-VALIDER-LIVE variant** | Calculate = **SOMME** `GetStat(unit,type@+0x18,variant@+0x1c,lvl)` sur le sélecteur (`uVar17 += iVar8`). Port = sum(). Le statVariant +0x1c est passé à get_stat mais le défaut dégradé ne le mappe pas (rend hp courant ; natif lit selon variant). |
| OwnerIsTarget | 180e026f0 | **CONFORME** | AreEqual(+0x148 Owner, +0x178 Target), singleton DAT_183200238. |
| OwnerIsCaster | 180e02610 | **CONFORME** | AreEqual(+0x148 Owner, +0x160 Caster). |
| OwnerIsActor | 180e02530 | **CONFORME** | AreEqual(+0x148 Owner, +0x158 Actor). 3 paires d'offsets factory-this vérifiées exactes. Défaut owner→caster documenté (A-VALIDER-LIVE si owner≠caster). |
| Friends | 180df0040 | **CONFORME** | UnitsByTeamSelector flag=1 ; Enemies flag=0 (symétrie exacte). Referent=arg2 (caster std). Port compare vs ctx.caster.team = correct au cas standard. |
| Units | 180e01340 | **CONFORME** | UnitsOnTilesSelector : unités sur les tiles source. Mode occupation inerte offline. |
| Tiles | 180dfdc60→f02150 | **CONFORME** | Singleton DISTINCT `DAT_183278e98` (≠ SortReverse DAT_18322b588) confirmé. UnitsMainTilesSelector : unités→GetMainTile. Mislabel "SortReverse" écarté par structure. |
| First | 180defae0→ef02e0 | **CONFORME** | Singleton `DAT_183285620` (≠ Filter DAT_1832409e0). PickAtIndexSelector : ToList (ordre tel quel) puis `[list[index]]` si index<count sinon []. |
| Unique | 180dfeec0→ee0080 | **CONFORME structure ; DÉDUIT critère** | Select = 1 appel LINQ index 0x95 mono-source (Distinct). Dedup par id cohérent ; comparateur exact non lu (0x95 non nommé). A-VALIDER si une ability Unique existe. |
| UnitsWithTrait | 180e00b10 | **CONFORME structure ; A-VALIDER-LIVE has_trait** | UnitsWithFlagSelector flag=1 ; Without flag=0 (symétrie). HasFlag(unit,traitId). Défaut has_trait absent → WithTrait=[]/Without=source. |
| UnitsWithoutTrait | 180e01040 | **CONFORME structure ; A-VALIDER-LIVE has_trait** | idem flag=0. |
| AdjacentFriends | 180de81d0 | **CONFORME** | Friends(Units(AdjacentTiles(caster))−{caster}) ; AdjacentEnemies symétrique. radius=1 (AdjacentTiles=R1). |
| SurroundingEnemies | 180dfc570 | **CONFORME** | Enemies(Units(SurroundingTiles(caster,1,R)−Tiles(caster))). Centre exclu (minR=1 + soustraction). |
| SurroundingFriends | 180dfc640 | **CONFORME** | Friends(...) symétrique. |
| SortByFormula | 180dfb0a0→ef3010 | **CONFORME** | flag@+0x28==0→OrderByDescending (DESC défaut), !=0→OrderBy (ASC). Port ascending=False défaut, reverse=not ascending = exact. Binding subject par-élément (state +0x140). Stable (OrderBy .NET ↔ sorted). |
| SortByDistance | 180dfb020→ef2ce0 | **CONFORME** | refPoint=arg2 (+0x20) résolu via index 0xc, PAS codé au caster. OrderBy ASC (proche d'abord), stable. Port prend ref_point Node. |

---

## RÉSERVE ConfigConst / ConfigVar — **TRANCHÉE : CONFORME (non bloquant)**

Décompilé natif :
- `GetNumberConstant @181576af0` = `Int32.Parse(GetStringConstant(key))` — lit le dict de STRINGS
  `+0x18` via TryGetValue, **AUCUN niveau d'ability**. Constante FIXE.
- `GetVariableForLevel @181576fb0` = `TryGetVariableArrayForLevel(key, level)` → `array[level].value`
  — INDEXÉ par le niveau.
- `ConfigAmount.Calculate @180f171c0` (le ConfigVar natif) choisit SOIT GetNumberConstant (source de
  clé +0x38) SOIT GetVariableForLevel (source +0x30), selon la source de clé renseignée.

Wrapper Python `AbilityConfiguration.get_variable_for_level`
(`engine/entities/abilities/ability_configuration.py:30`) implémente **LES DEUX chemins par le
CONTENU de la clé** :
- clé dans `variables` → `arr[level-1]` clampé = GetVariableForLevel (par niveau) ;
- sinon clé dans `constants` → `constants[key]` = GetNumberConstant (fixe, hors niveau).

Donc `ConfigConst("nrOfHits")` (nrOfHits est une CONSTANTE → dict `constants`) tombe dans la branche
constants = **fixe hors niveau = comportement natif GetNumberConstant exact**. `ConfigVar("minDmg")`
(variable par niveau → dict `variables`) tombe dans la branche variables = GetVariableForLevel exact.
Le wrapper réconcilie comme le natif (dispatch par source de clé). **Pas de divergence fonctionnelle.**

Seule DIVERGENCE résiduelle assumée (documentée L89-91 du port) : le natif THROW si la clé est
absente ; le Python retourne `default`. Garde-fou offline inerte tant que la clé existe (un arbre ne
référence que des clés présentes), mais MASQUERAIT une clé manquante. **Non bloquant.**

---

## PRIORITÉ 2/3/4/5 — synthèse

- **P2 Divide/PercentageOf (arrondi Fix64)** : CONFORME. Sim bit-exacte 0 mismatch (Round half-to-even,
  Ceiling, Floor, op_Division long-division, op_Multiply trunc — tous lus). L'inertie 2-décimales pour
  entiers est PROUVÉE numériquement (pas juste asserée).
- **P3 Modulo** : CONFORME. Prédicat bool `(a%b)==c` (pas valeur), modulo C signé (trunc vers zéro).
- **P4 binding subject Filter/SortByFormula** : CONFORME. Le natif injecte l'item dans une COPIE du
  contexte au slot sujet (FUN_180025220 arg 0x20 pour Filter ; state +0x140 pour SortByFormula), le
  port `replace(ctx, subject=item)` en est le mirror fidèle.
- **P5 déduits (AreEqual, Max, Unique)** : sémantique cohérente ; eval résiduelle (AreEqual/Max) ou
  comparateur LINQ non nommé (Unique 0x95) → confiance haute, seul un usage sur type inattendu
  divergerait (aucun dans le batch).

Aucun bug compensatoire, ordre d'opérande inversé, off-by-one, confusion valeur/prédicat, ni arrondi
entier-vs-Fix64 détecté.

---

## REPRODUCTION FROM-SCRATCH (offline)

- `import engine.dsl` OK, tous les nœuds exportés (`__init__.py`).
- Test sémantique par-nœud (numérique+prédicat) : **0 FAIL** — incl. Half/Divide half-to-even,
  AmountIsGreater strict, AmountIsZero(a<=0), AmountIsOdd(-3), Modulo prédicat + C-signé.
- Test ciblage/tri/filtre : **0 FAIL** — incl. Filter binding subject, SortByFormula DESC-défaut+ASC+
  stable, SortByDistance ASC+stable, First(idx/oob/vide), Unique dedup, Units/Tiles round-trip,
  Surrounding/Adjacent Enemies/Friends, Count, OwnerIs*.
- Sim Fix64 : `scratchpad/fix64_sim.py` (Divide 0 mismatch, PercentageOf 0 mismatch étendu).

Pas de régression à re-dérouler (aucun step live dans le scope ; aucun rebuild).

---

## CE QUE L'AGRÉMENT LIVE DEVRA CIBLER (priorisé)

1. **TurnsFromRounds** — facteur rounds→turns runtime (index 0x1b). Port défaut=identité (turns_per_round=1).
   Aucune donnée offline. À capter dès qu'une ability l'utilise.
2. **StatAmount statVariant (+0x1c)** — base/current/max. Défaut dégradé rend hp COURANT ; le natif lit
   selon variant (souvent maxHP). À valider par unité portant un StatAmount à variant ≠ current.
3. **UnitsWithTrait/WithoutTrait — has_trait réel** — défaut = trait absent. À valider avec un porteur
   de trait (unit_map : sélectionner une ability filtrant par trait) pour confirmer HasFlag(unit,traitId).
4. **OwnerIs\* quand owner≠caster** — défaut owner→caster. À valider sur un effet transféré/buff-sur-autrui
   où Owner≠Caster (sinon OwnerIsCaster toujours True).
5. **Unique — critère de dedup** (0x95 non nommé) — confirmer dedup par identité d'entité si une ability
   Unique existe.
6. **SurroundingUnits — sémantique du centre** — le port fixe centre-EXCLU (include_center=False) ; le
   natif `SurroundingTiles(caster, minRadius=param5, R)` dépend de param5. Pour Harvester (seul usage,
   `SurroundingUnits(OwnerTile, range)`), l'exclusion du centre est neutralisée par le `And` avec
   AdjacentEnemies(target) → sans conséquence. À re-confirmer si un futur usage a minRadius=0 et centre
   pertinent.
7. **Friends/Enemies referent ≠ caster** — le port fixe referent=caster ; fidèle au cas standard, à
   surveiller si un arbre passe un referent explicite ≠ caster.

## OUTILLAGE MANQUANT
Aucun contrôle offline manquant pour cette passe (ghidra-mcp + repo suffisent). Les 7 points ci-dessus
requièrent l'oracle LIVE (état runtime non-captable offline) — c'est structurel, pas un trou d'outillage.
