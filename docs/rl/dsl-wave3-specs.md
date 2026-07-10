# DSL Wave 3 — Specs de port (predicats-feuille B + accesseurs D)

Build `gqfc5mff6c`. Base VA 0x180000000. RE READ-ONLY.
Convention (cf. dsl-wave1/2-specs) : `[PROUVE]` = lu dans le decompile (VA citee) ;
`[DEDUIT]` = infere de la structure/nommage sans eval residuelle lue.

CAVEAT MISLABEL confirme partout : ghidra affiche des ctors gshared homonymes FAUX
(`HasUsedActiveAbilityThisTurnTrigger`, `CurrentShieldAmountFormula`, `TimeMachineBehaviour`,
`AllAliveMachinesSelector`, `TestUnitProvider`, `thor_Menu_WaitForCondition`,
`UnitTimelines_TypeToTimeline`...). La classe REELLE est identifiee par : (a) le singleton
`DAT_*` (une adresse = une classe), (b) l'arite/structure du ctor, (c) la methode d'eval
NOMMEE quand elle existe (le `$$ShouldTrigger`/`$$Select`/`$$Calculate` porte le VRAI nom).

---

## Table des singletons/classes reelles (preuve d'identite par DAT + eval nommee)

| Node          | Factory VA   | Singleton DAT   | Classe REELLE (via eval nommee)                    | Eval VA        |
|---------------|--------------|-----------------|----------------------------------------------------|----------------|
| HasTrait      | 180df14c0    | DAT_183269b50   | HasTrait* (ctor mislabel CurrentShieldAmountFormula, 3 args) | (pas de ShouldTrigger nomme -> voir note) |
| HasEffect     | 180df0fb0    | DAT_183269010   | Triggers.HasEffectTrigger                          | 180f9d830      |
| HasAnyEffect  | 180df0b70    | DAT_183268b10   | Triggers.HasAnyEffectTrigger                       | 180f9d0c0      |
| IsAlive       | 180df2fa0    | DAT_18320a1e8   | Conditions.IsAliveAbilityTrigger                   | 180eec930      |
| Alive         | 180de8390    | DAT_18320a1e8   | = IsAlive wrappe dans FromTrigger (filtre)         | 180eec930      |
| IsDead        | 180df3370    | DAT_18320a1e8   | = NOT(IsAlive)  (op_LogicalNot)                    | 180eec930      |
| IsMeleeAttack | 180df43f0    | DAT_18320bae8   | Triggers.IsMeleeAttackAbilityTrigger (timeline=melee) | 180fa1e00   |
| IsRangedAttack| 180df4d90    | DAT_18320c768   | Triggers.IsMeleeAttackAbilityTrigger (timeline=ranged) | 180fa1e00  |
| IsNormalAttack| 180df47c0/90 | DAT_183230bc0.. | IsCurrentAbility(type==0x3f5) OR HasUsed(...)       | (compose)      |
| IsAdjacent    | 180df2f00    | DAT_18320a0a8   | Triggers.IsAdjacentAbilityTrigger                  | 180f9f7b0      |
| IsInRange     | 180df3d80    | DAT_18320b5e8   | Triggers.IsInRangeAbilityTrigger (ctor mislabel AttackHitsWithModifiersFormula) | 180fa1720 |
| Entity        | 180def540    | DAT_18321cd70   | Selectors.* (ctor mislabel AllAliveMachinesSelector) — passe arg | 180ee0080 |
| EntityId      | 180def470    | DAT_18321caf0   | Selectors.* (ctor mislabel TestUnitProvider) — 1 arg | -            |
| Nothing       | 180df7870    | DAT_1832655b8   | Selectors.* (ctor mislabel TimeMachineBehaviour) — 0 arg | -        |
| Null          | 180df74f0    | DAT_18321cd70   | = Entity avec arg=null (MEME classe qu'Entity)     | 180ee0080      |
| EffectSource  | 180deeb90    | DAT_1832133c0   | Selectors.* (ctor mislabel AllAliveMachinesSelector) — 1 arg | -      |
| EffectLevel   | 180deead0    | DAT_183212b00   | Formulas.* (ctor mislabel thor_Menu_WaitForCondition) — 1 arg | -     |
| EffectFromOwner|180deea50    | DAT_183213780   | Selectors.EffectWithTypeSelector                   | 180ee7f30      |

---

# BATCH B — PREDICATS (retour bool)

## HasTrait @180df14c0  (161 refs)  [PROUVE structure, DEDUIT eval]
- **VA/classe** : factory 180df14c0 -> singleton DAT_183269b50. Ctor mislabel
  `CurrentShieldAmountFormula.ctor(inst, param_2, param_3, 0)` — MAIS le vrai
  `CurrentShieldAmountFormula.ctor @180f18b60` ne prend que 2 args (source@+0x10, stat@+0x18) ;
  la factory en passe 3 (source, traitId, 0) -> le ctor est LUI AUSSI mislabel (homonyme
  gshared), la classe reelle stocke (source@+0x10, traitId@+0x18).
- **Semantique** : teste `UnitExtensions.HasFlag(unit, traitId)` sur l'unite du selecteur
  `param_2`. MEME primitive que `UnitsWithTrait`/`HasFlag` (wave2). Preuve d'usage :
  `TheBetrayer_TakeTurnAbility.GetPreferredAttackTargets @1811a58a0` =
  `Filter(src, NOT(HasTrait(subject, 0xd)))` (deja documente dans nodes.py Filter/Subject).
- **Type retour** : bool.
- **Sujet** : l'operande selecteur `param_2` (arg explicite). En pratique branche sur le
  slot `subject` quand appele SOUS un Filter (l'operande passe = `Subject()`), sinon sur
  un selecteur explicite (caster/target/owner).
- **Ctx requis** : `ctx.has_trait(unit, traitId)` (DEJA present, wave2). Rien de nouveau.
- **Ordre operandes** : (source_selector, traitId).
- **Port propose** : `HasTrait(source: Node, trait)` -> `ht = ctx.has_trait ; return ht(src_unit, trait)`
  ou src_unit = source.evaluate(ctx) (unite unique ; si liste -> any). Confirmer contre agreement
  si single vs any (usages observes = single via Subject).

## HasEffect @180df0fb0  (140 refs)  [PROUVE]
- **VA/classe** : factory 180df0fb0 -> DAT_183269010 -> `HasEffectTrigger`.
  `HasEffectTrigger.ShouldTrigger @180f9d830` : evalue selecteur@+0x10 -> entity, puis
  `EntityExtensions.HasOneOfEffects(entity, effectTypesList@+0x20, sourceFlag@+0x1c, minLevel@+0x28, mode)`.
  Ctor factory : `HasEffectTrigger.ctor(inst, source, effectType, ownerEntity@fact+0x38, minLevel, sourceFlag, 0)`.
- **Semantique** : l'unite selectionnee possede-t-elle un effet du type donne (>= minLevel,
  filtre par source-flag) ? `HasOneOfEffects @180eb7640` : mode bit2 = effets OWNED,
  bit4 = effets INCOMING ; construit une liste [effectType] via ToList puis teste.
- **Type retour** : bool.
- **Sujet** : le selecteur passe (`param_2` de la factory) — souvent Subject sous Filter,
  sinon target/caster.
- **Ctx requis** : **NOUVEAU slot** `has_effect(unit, effectType, source_flag=6, min_level=0) -> bool`.
  NON captable offline en general (etat runtime des effets par unite). Defaut None -> False
  (effet absent, convention HasFlag). En prediction, l'etat effets EST partiellement dispo
  live (decisionView.effects) mais PAS dans le state offline standard {id,team,hp,alive,pos}.
- **Ordre operandes** : (source_selector, effectType, [minLevel], [sourceFlag]).

## HasAnyEffect @180df0b70  [PROUVE]
- **VA/classe** : factory 180df0b70 -> DAT_183268b10 -> `HasAnyEffectTrigger`.
  `HasAnyEffectTrigger.ShouldTrigger @180f9d0c0` : evalue selecteur@+0x10 -> entity, puis
  `HasOneOfEffects(entity, list@+0x28, source@+0x18, flag@+0x20, mode=6, 0)` — **mode=6
  HARDCODE** (bits 2|4 = owned + incoming). Ctor factory : `HasAnyEffectTrigger.ctor(inst,
  source, effectList, ownerEntity@fact+0x38, flag, 0)`.
- **Semantique** : l'unite a-t-elle AU MOINS UN effet parmi la liste (ou tout effet) ?
  Difference avec HasEffect = teste une LISTE d'effets (any), pas un type unique + niveau.
- **Type retour** : bool.
- **Sujet** : selecteur passe (`param_3`).
- **Ctx requis** : meme slot `has_effect` (variante any-of-list). NON captable offline -> False.
- **Ordre operandes** : (source_selector, effectList, flag).

## IsAlive @180df2fa0 / Alive @180de8390 / IsDead @180df3370  [PROUVE]
- **VA/classe** : les trois partagent DAT_18320a1e8 = `IsAliveAbilityTrigger`.
  `IsAliveAbilityTrigger.ShouldTrigger @180eec930` : evalue selecteur@+0x10 -> unit, puis
  `UnitExtensions.IsAlive(unit, entity@+0x18)`.
  - **IsAlive** : le trigger nu -> bool (unite vivante).
  - **Alive @180de8390** : `IsAlive(selector@fact+0x180=OriginalTarget)` puis
    `DSLFactory.FromTrigger(source, trigger)` -> c'est un **FILTRE** (garde les unites du
    source qui sont vivantes), retour list. Structurellement = `Filter(source, IsAlive(subject))`.
  - **IsDead @180df3370** : `IsAlive(selector)` puis `AbilityTrigger.op_LogicalNot` -> NOT(IsAlive)
    = mort/inexistant. Retour bool.
- **Semantique** : vivant/mort de l'unite selectionnee.
- **Type retour** : IsAlive/IsDead = bool ; Alive = list (filtre).
- **Sujet** : selecteur passe (Subject sous Filter, ou caster/target explicite). Pour Alive,
  le sujet du predicat interne est l'element courant du source (binding Filter, slot@+0x180).
- **Rapport avec Damageable (wave1)** : `Damageable` filtre `alive AND hp>0` (ciblabilite).
  `IsAlive`/`Alive` teste UNIQUEMENT le vivant via `UnitExtensions.IsAlive` (pas la
  ciblabilite/hp>0 explicite — mais alive implique hp>0 dans le state). Nuance : Damageable
  = filtre de CIBLAGE (wave1) ; IsAlive = predicat pur reutilisable dans n'importe quel arbre.
- **Ctx requis** : `u.get("alive")` / hp>0 (DEJA dispo dans le state offline). RIEN de nouveau.
- **Port propose** :
  - `IsAlive(source)` : bool = bool(unit.alive) and (unit.hp or 0) > 0.
  - `IsDead(source)` : NOT du precedent.
  - `Alive(source)` : `Filter(source, IsAlive(Subject()))` (retour list) — ou classe dediee
    reutilisant le meme predicat par-element.

## IsMeleeAttack @180df43f0 (72) / IsRangedAttack @180df4d90 (54)  [PROUVE structure, incertitude ctx]
- **VA/classe** : DEUX singletons DISTINCTS (DAT_18320bae8 melee, DAT_18320c768 ranged) mais
  **MEME ctor reel** `IsMeleeAttackAbilityTrigger.ctor @180fa24e0` et **MEME ShouldTrigger
  @180fa1e00**. La difference melee/ranged = un **timeline-type** passe au ctor
  (`FUN_180002560(3, DAT_1831b81f8)` construit un enum-value + un `UnitTimelines.TypeToTimeline`
  distinct par cas). Donc : une seule classe parametree par le type d'attaque a tester.
- **Semantique** : teste si l'ATTAQUE COURANTE (l'AbilityEntities `param_2` passe a ShouldTrigger)
  est de type melee (resp. ranged). ShouldTrigger @180fa1e00 lit :
  `get_HasCasterPosition`/`get_CasterPosition`/`GetUnitPosition` (position d'attaque) +
  compare le timeline-type de l'ability vs le type attendu. C'est un predicat sur le
  **contexte d'ability en cours d'evaluation**, pas sur une unite du state.
- **Type retour** : bool.
- **Sujet** : NI subject NI un selecteur d'unite — c'est l'**ability/attaque courante** (le
  contexte d'ability evalue). Le "sujet" est implicite = l'action en cours.
- **Ctx requis** : **NOUVEAU slot** `attack_kind` (enum: 'melee'|'ranged'|None) OU
  `is_melee: bool | None` decrivant le type de l'ability actuellement evaluee. NON captable
  depuis le state d'unites — vient du contexte d'evaluation de l'ability (la couche
  active_ability sait quelle ability elle porte : melee vs ranged est une prop du weapon/ability
  dans gameconfig). Defaut None -> predicat indetermine ; proposer defaut conservateur documente.
- **INCERTITUDE (point le plus faible du batch)** : quel champ runtime alimente le type ?
  Le type melee/ranged d'une ability est une donnee STATIQUE (gameconfig : l'ability/weapon
  a un profil melee ou ranged), donc CAPTABLE offline si la couche ability fournit son propre
  type. Ce n'est pas un etat de bataille volatil comme times_attacked. -> A cabler par la
  couche ability qui pose `ctx.attack_kind = <type de l'ability portee>`.

## IsNormalAttack @180df47c0 / @180df4690  [PROUVE]
- **VA/classe** : overload 180df47c0 delegue a 180df4690 avec `fact+0x130` (slot ability
  courante). Le coeur 180df4690 : `AbilityOrEffect.op_Implicit(0x3f5)` = **abilityType 0x3f5
  = 1013** (un type "normal attack" generique/marqueur), pose dans `DirectAbilitySelector`,
  cree un trigger `IsCurrentAbility(ability == thatType)` (ctor mislabel
  HasUsedActiveAbilityThisTurnTrigger) puis `op_BitwiseOr` avec une autre branche.
- **Semantique** : l'ability courante EST-ELLE une attaque normale (type 1013) ? (OR de
  conditions equivalentes). Predicat sur le contexte d'ability, comme Is*Attack.
- **Type retour** : bool.
- **Sujet** : l'ability courante (implicite), pas une unite.
- **Ctx requis** : **NOUVEAU slot** `attack_ability_type` (int, le ActiveAbilityType de
  l'ability courante) OU un flag `is_normal_attack`. Le type d'attaque normale par unite est
  un ActiveAbilityType concret (cf. memory: Loki_NormalAttack=69, jamais l'abstrait 17) ;
  1013=0x3f5 est le marqueur AbilityOrEffect generique compare. Captable si la couche ability
  fournit son type. Defaut None -> False.
- **Note** : `IsNormalAttackOrHealOrRepair @180df4550` = variante (meme mecanique, OR
  supplementaire) — hors batch strict mais meme famille.

## IsAdjacent @180df2f00  (46)  [PROUVE]
- **VA/classe** : factory 180df2f00 -> DAT_18320a0a8 -> `IsAdjacentAbilityTrigger`.
  Ctor @180f9fc10 : stocke (selectorA@+0x20, selectorB@+0x28, flag@+0x18, entity@+0x10).
  `ShouldTrigger @180f9f7b0` : evalue selectorA (+0x20) et selectorB (+0x28) -> deux
  ensembles d'unites ; pour CHAQUE paire (a in A, b in B) teste
  `FUN_1800051a0(0x5f, entity, posA, posB)` = **adjacence hex** (helper 0x5f). Retourne 1
  des qu'une paire est adjacente (else 0). (Structure : boucle imbriquee A x B, court-circuit
  au 1er adjacent.)
- **Semantique** : au moins une unite de A est-elle hex-adjacente a au moins une de B ?
  Adjacence = **distance hex == 1** [DEDUIT du helper 0x5f "IsAdjacent" ; la valeur exacte du
  seuil n'est pas lue litteralement mais l'helper est l'op d'adjacence standard].
- **Type retour** : bool.
- **Sujet** : DEUX operandes selecteurs explicites (A@+0x20, B@+0x28) — PAS le slot subject.
  Typiquement (subject/target vs caster) selon l'ability.
- **Ordre operandes** : (selectorA, selectorB, [flag]).
- **Ctx requis** : positions (DEJA dispo). RIEN de nouveau. `hexgeo.distance(a,b)==1`.
- **Port propose** : `IsAdjacent(a: Node, b: Node)` -> any(dist(pa,pb)==1 for pa in A for pb in B).

## IsInRange @180df3d80  (15)  [PROUVE]
- **VA/classe** : factory 180df3d80 -> DAT_18320b5e8 -> `IsInRangeAbilityTrigger` (ctor
  mislabel AttackHitsWithModifiersFormula). Ctor factory : args (fact+0x28=entity, param_2,
  param_3, param_4). `ShouldTrigger @180fa1720` :
    - rangeThreshold = formule@+0x28 evaluee (`FUN_1800250d0` -> iVar14 = valeur de range) ;
    - posA = selecteur@+0x18 evalue -> position ;
    - posB = selecteur@+0x20 evalue -> position ;
    - dist = `FUN_1800051a0(0x6e, entity, posA, posB)` (helper 0x6e = distance hex, iVar15) ;
    - **return dist <= rangeThreshold** (`iVar15 <= iVar14`).
- **Semantique** : la distance hex entre A et B est-elle <= au seuil de range ? Le seuil vient
  d'une FORMULE (souvent la range de l'ability via ConfigConst, pas une constante figee).
- **Type retour** : bool.
- **Sujet** : deux selecteurs de position (A@+0x18, B@+0x20) + une formule de range (@+0x28).
- **Ordre operandes** : (rangeFormula, selectorA, selectorB). (NB l'ordre exact des args
  factory param_2/3/4 -> slots +0x28/+0x18/+0x20 : rangeFormula d'abord dans le ctor, a
  confirmer au cablage par ability ; la STRUCTURE +0x28=range est prouvee par l'eval.)
- **Ctx requis** : positions + config (DEJA dispo pour la formule range via ConfigConst).
  RIEN de nouveau si la formule range est un sous-arbre deja portable.
- **Port propose** : `IsInRange(range: Node, a: Node, b: Node)` ->
  `hexgeo.distance(posA, posB) <= range.evaluate(ctx)`.

---

# BATCH D — ACCESSEURS

## Entity @180def540 (124) / EntityId @180def470 (36)  [PROUVE structure, DEDUIT ref]
- **VA/classe** : Entity -> DAT_18321cd70 (MEME que Null), ctor(fact+0x10=entity, param_2, 0).
  EntityId -> DAT_18321caf0, ctor(param_2, 0). `AllAliveMachinesSelector.Select @180ee0080`
  (classe reelle mislabel d'Entity) : lit slot@+0x18 et appelle `FUN_180004fd0(0x95, entity, x)`
  = resolution d'une reference d'entite depuis un descripteur.
- **Semantique** : `Entity(ref)` resout une REFERENCE d'entite (un descripteur/role passe en
  arg) vers l'entite concrete (le selecteur/unite). `EntityId(ref)` = son ID uniquement.
  L'argument `param_2` designe QUELLE entite (un role : caster/target/owner/subject selon le
  descripteur passe par l'ability). Ce n'est PAS un slot fixe cote factory — c'est l'operande.
- **Type retour** : Entity -> selecteur/unite (ou position via aval) ; EntityId -> int (id).
- **Sujet/ref** : l'argument explicite (`param_2`) = la reference cible. En pratique branche
  sur caster/target/owner/subject selon ce que l'ability passe.
- **Ctx requis** : les roles existants (`ctx.caster/target/owner/actor/subject`). RIEN de
  nouveau si l'argument mappe sur un role connu. Si l'argument est un descripteur runtime
  arbitraire (index d'AbilityEntities) -> a resoudre via la couche ability.
- **Port propose** : `Entity(ref: Node)` -> `ref.evaluate(ctx)` (l'arg fait deja la resolution
  de role) ; `EntityId(ref)` -> `ref.evaluate(ctx).get("id")`. Souvent l'arg EST deja un noeud
  role (Caster/Target/Subject) donc Entity/EntityId sont de fins wrappers.

## Nothing @180df7870 (52) / Null @180df74f0 (23)  [PROUVE]
- **Nothing** : DAT_1832655b8 (singleton DISTINCT), ctor 0-arg. Aucun operande. C'est un
  **selecteur/noeud VIDE** (no-op) — retourne un ensemble vide `[]` (selecteur sans source).
  Usage typique = branche neutre d'un `If`, ou source vide a soustraire.
- **Null** : DAT_18321cd70 (**MEME classe qu'Entity**), ctor(fact+0x10, **0**, 0) = Entity avec
  arg=null. Donc Null = une REFERENCE d'entite nulle (entity absente / "aucune cible").
  `Select` : slot@+0x18 = null -> resolution d'une entite nulle.
- **Distinction** : `Nothing` = SELECTEUR vide (0 element, type list) ; `Null` = ENTITE nulle
  (une reference d'entite qui vaut "personne", type entity/None). Nothing est un ensemble,
  Null est un singleton nul.
- **Type retour** : Nothing -> list vide `[]` ; Null -> None (entite absente).
- **Ctx requis** : aucun. RIEN de nouveau.
- **Port propose** : `Nothing()` -> `[]` ; `Null()` -> `None`.

## EffectSource @180deeb90 (85) / EffectLevel @180deead0 (27) / EffectFromOwner @180deea50  [PROUVE structure]
- **EffectSource** : DAT_1832133c0 (classe distincte d'Entity), ctor(fact+0x10, param_2, 0).
  Accede a la **source (le lanceur/owner d'un EFFET)** — resout l'entite qui a applique
  l'effet courant. Retour = entite (l'applicateur de l'effet).
- **EffectLevel** : DAT_183212b00 (Formula, ctor mislabel thor_Menu_WaitForCondition),
  ctor(param_2, 0). Retour = int (le NIVEAU de l'effet courant/passe en arg). Formule scalaire.
- **EffectFromOwner** : DAT_183213780 -> `EffectWithTypeSelector`. `Select @180ee7f30` :
  parcourt les composants d'effets de l'entite (source@+0x10), et pour chacun
  `EntityExtensions.GetOwnedEffect(component, source@+0x10, effectType@+0x20)` -> collecte les
  effets OWNED du type donne. Retour = liste d'effets. Ctor factory : (fact+0x10, param_2=source,
  param_3=effectType).
- **Semantique** : ces noeuds accedent a l'**EFFET COURANT** (ou aux effets d'une entite) —
  source, niveau, et l'objet effet lui-meme filtre par type.
- **Type retour** : EffectSource -> entite ; EffectLevel -> int ; EffectFromOwner -> list[effet].
- **Sujet/ctx** : requiert un **CONTEXTE D'EFFET COURANT**. Ces noeuds n'ont de sens QUE dans
  l'application/evaluation d'un effet (ex. CreateEffectDamageBonusForAttack) — l'effet en cours
  fournit source+level. En PREDICTION d'attaque hors application d'effet, il N'Y A PAS d'effet
  courant -> **DEPENDANCE RUNTIME a flagger** (pas captable offline sauf si la couche fournit
  l'effet). GetOwnedEffect exige l'etat runtime des effets par unite (non present dans le state
  offline standard).
- **Ctx requis** : **NOUVEAU slot** `effect` (l'objet effet courant : source, level, type) +
  reutilise `has_effect`/un accesseur effets par unite. Defaut None -> EffectSource=None,
  EffectLevel=0, EffectFromOwner=[]. **FLAG : ces noeuds ne sont evaluables qu'en contexte
  d'effet ; hors application d'effet (prediction pure) ils degradent vers neutre.**

---

# NOUVEAUX champs DslContext requis (nommes + defaut + role)

| Champ                | Defaut | Represente / source                                            | Captable offline ? |
|----------------------|--------|----------------------------------------------------------------|--------------------|
| `has_effect`         | None   | callable `(unit, effectType, source_flag=6, min_level=0)->bool`. Mirror `EntityExtensions.HasOneOfEffects @180eb7640`. Fournit par la couche ability (etat effets runtime). | NON (partiel via decisionView.effects live) ; defaut -> False |
| `attack_kind`        | None   | Type de l'attaque/ability COURANTE : 'melee' / 'ranged' (mirror timeline-type de `IsMeleeAttackAbilityTrigger`). Prop statique de l'ability portee (gameconfig weapon profile). | OUI si fourni par la couche ability (statique, pas volatil) |
| `attack_ability_type`| None   | ActiveAbilityType (int) de l'ability courante, pour `IsNormalAttack` (compare vs 0x3f5=1013). | OUI si fourni par la couche ability |
| `effect`             | None   | Objet EFFET courant (source, level, type) pour EffectSource/EffectLevel/EffectFromOwner. N'existe QUE en application d'effet. | NON hors application d'effet -> degrade neutre |

Note : `has_trait`, `get_stat`, `subject`, `caster/target/owner/actor`, `caster_pos`,
positions, `config`/`ability_level` sont DEJA presents (waves 1/2) et couvrent HasTrait,
IsAlive/IsDead/Alive, IsAdjacent, IsInRange, Entity/EntityId, Nothing/Null.

---

# Verdict sur les 3 plus incertains

1. **Is*Attack (melee/ranged/normal)** : le contexte qui les alimente est le **type de
   l'ability COURANTE** (timeline melee/ranged pour Is*Attack ; ActiveAbilityType==1013 pour
   IsNormalAttack), PAS une unite du state ni le slot subject. Bonne nouvelle : ce type est
   une donnee STATIQUE de gameconfig (profil d'arme melee/ranged, ActiveAbilityType concret),
   donc CAPTABLE si la couche active_ability pose `ctx.attack_kind` / `ctx.attack_ability_type`
   au moment ou elle evalue son arbre. Ce n'est pas un etat volatil type times_attacked.
   Prouve : `IsMeleeAttackAbilityTrigger.ShouldTrigger @180fa1e00` (compare timeline de
   l'AbilityEntities param_2) ; `IsNormalAttack @180df4690` (compare vs op_Implicit(0x3f5)).

2. **HasEffect (slot requis)** : requiert un NOUVEAU slot `ctx.has_effect(unit, effectType,...)`
   mirrorant `HasOneOfEffects @180eb7640` (mode 6 = owned|incoming). NON captable dans le
   state offline standard {id,team,hp,alive,pos,visualId} ; partiellement dispo live via
   decisionView.effects. Defaut None -> False (effet absent, convention HasFlag). HasAnyEffect
   = meme slot, variante any-of-list (mode 6 HARDCODE dans le natif).

3. **Entity (quelle reference)** : Entity(ref) resout la reference d'entite passee EN ARGUMENT
   (pas un slot fixe) — l'arg designe le role (caster/target/owner/subject) que l'ability
   choisit. Souvent l'operande EST deja un noeud role, donc Entity/EntityId sont de fins
   wrappers (`ref.evaluate(ctx)` / `.id`). Null = MEME classe qu'Entity avec arg null -> entite
   nulle (None). Nothing = classe DISTINCTE = selecteur vide ([]). Ne pas confondre :
   Null=None (entite), Nothing=[] (ensemble).

---

# Resume 1-ligne / noeud

- **HasTrait** [B, bool] : HasFlag(unit, traitId) sur le selecteur-operande (souvent Subject sous Filter) ; ctx.has_trait (existant). @180df14c0/DAT_183269b50.
- **HasEffect** [B, bool] : unite selectionnee a un effet du type (>=level, source-flag) ; NOUVEAU ctx.has_effect, non-offline. @180df0fb0->HasEffectTrigger@180f9d830.
- **HasAnyEffect** [B, bool] : unite a au moins un effet parmi liste (mode 6) ; ctx.has_effect, non-offline. @180df0b70->@180f9d0c0.
- **IsAlive** [B, bool] : UnitExtensions.IsAlive(selector) ; alive/hp existant. @180df2fa0->@180eec930.
- **Alive** [B, list] : Filter(source, IsAlive(subject)) = filtre vivants ; existant. @180de8390.
- **IsDead** [B, bool] : NOT(IsAlive(selector)) ; existant. @180df3370.
- **IsMeleeAttack** [B, bool] : l'ability COURANTE est melee (timeline-type) ; NOUVEAU ctx.attack_kind (statique, cablable). @180df43f0/DAT_18320bae8->@180fa1e00.
- **IsRangedAttack** [B, bool] : idem ranged (meme classe, singleton DAT_18320c768). @180df4d90->@180fa1e00.
- **IsNormalAttack** [B, bool] : ability courante == type normal-attack (0x3f5=1013) OR ... ; NOUVEAU ctx.attack_ability_type. @180df47c0/@180df4690.
- **IsAdjacent** [B, bool] : une unite de A hex-adjacente (dist==1) a une de B ; 2 selecteurs, positions existantes. @180df2f00->@180f9f7b0.
- **IsInRange** [B, bool] : dist(A,B) <= rangeFormula ; positions+config existants. @180df3d80->@180fa1720.
- **Entity** [D, entite] : resout la reference d'entite passee en arg (role caster/target/subject) ; roles existants. @180def540/DAT_18321cd70->@180ee0080.
- **EntityId** [D, int] : id de l'entite resolue. @180def470/DAT_18321caf0.
- **Nothing** [D, list] : selecteur VIDE [] (ctor 0-arg, classe distincte). @180df7870/DAT_1832655b8.
- **Null** [D, entite] : reference d'entite NULLE = None (MEME classe qu'Entity, arg null). @180df74f0/DAT_18321cd70.
- **EffectSource** [D, entite] : applicateur de l'effet courant ; NOUVEAU ctx.effect, contexte-effet uniquement. @180deeb90/DAT_1832133c0.
- **EffectLevel** [D, int] : niveau de l'effet courant ; ctx.effect. @180deead0/DAT_183212b00.
- **EffectFromOwner** [D, list[effet]] : effets OWNED du type sur l'entite (GetOwnedEffect) ; ctx.effect + etat effets runtime. @180deea50->EffectWithTypeSelector@180ee7f30.
