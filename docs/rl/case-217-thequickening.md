# Case #217 — TheQuickening (ActiveAbilityType 1151, bloodMephiston) : face COMBAT

> Statut : **RESOLU / porte + valide live**. Porteur = `bloodMephiston` (BloodAngels, lineup, 1 unite).
> Categorie audit = EFFECT/BUFF. La face DECISION etait deja portee
> (`engine/playbook/noncomparable/the_quickening.py`, #46/#32) ; ce cas porte la face COMBAT
> (`ExecuteBehaviour`) qui etait un **NO-OP silencieux** (1151 absent de `ABILITY_CLASSES`).

## 1. Artefact natif (decompile = verite)

- `TheQuickeningAbility.ExecuteBehaviour @181211d50` (ctor `@181213150`).
- Sous-behaviours : `GetMoveOutBehaviour @181212aa0`, `GetMoveInBehaviour @181212940`,
  `GetTriggerMovementAbilitiesBehaviour @181213050`, `GetTriggerAttackBehaviour @181212cd0`.
- Formule free-attack : `DSLFactory.PercentageOfAttackCappedAtMax @180df8530`.
- Champs selecteurs sur le contexte DSL `(*(ability+0x30))` : `+0x148` Self, `+0x160` Caster,
  `+0x168` CasterTile (position d'origine, `SetCache`), `+0x178` Target (la TUILE cast).

### Arbre (7 `AActiveAbility.Execute` sequentiels)

1. `SetCache(CasterTile@0x168) & Reserve(Caster@0x160, Target@0x178) & MoveOut(Caster) & MoveOut(Attackable@Target)`
2. `MoveIn(Caster -> Target) & MoveIn(Attackable -> CasterTile@0x168)`
3. `TriggerMovementAbilities(Caster)`  = `If(unit==Caster, AddFlag(unit,1)) & EvaluateAbilities(0x1c=28) & RefreshEffects(7)`
4. `TriggerAttack(Caster)`
5. `TriggerMovementAbilities(Attackable)`
6. `TriggerAttack(Attackable)`
7. `InvalidateCaches`

- `GetMoveOutBehaviour(unit)` = `RemoveEffect(EffectFromOwner(unit,0x19)) & AddEffect(0x414 Untargetable,
  caster-src, unit) & MoveUnit(unit -> Null)` (lift off-board, marqueur transit).
- `GetMoveInBehaviour(unit, tile)` = `MoveUnit(unit -> tile) & RemoveEffect(unit, 0x414)` (atterrissage).
- `DSLFactory.Attackable @180deaa50` = `UnitsWithoutTrait(0x1b=27)` -> le swap-unit = occupant de la
  tuile cible SANS trait 27.
- `GetTriggerAttackBehaviour(unit)` = `If(HasFaction(unit, 0xe=14=BloodAngels),
    AddEffect(0x529 ForcedInMelee, source=AbilityStateReference, target=unit, durée=Nullable<int>(1))
    & AddStatOverrideEffect(unit, 0x510 Attack_Override, PercentageOfAttackCappedAtMax(Attack, dmgPct, maxDmg))
    & PerformAIAttackFromCurrentPosition(unit, utilityEntity=unit, customUtility=<lambda>, skipAtomicCheck=0)
    & RemoveEffect(unit, 0x510) & RemoveEffect(unit, 0x529))`
  — **ordre relu au décompilé** (chaîne `op_BitwiseAnd` : `AddEffect(0x529) & AddStatOverride & PerformAI
  & Remove(0x510) & Remove(0x529)`) : l'`AddEffect(0x529)` précède l'`AddStatOverrideEffect`, et il n'est
  **pas décoratif** — cf. §5.
- `PercentageOfAttackCappedAtMax(attack, 3, cfg13, cfg74)` = `min(cfg13, PercentageOf(StatAmount(Attack,3), cfg74))`
  = `min(maxDmg[level]xmult, round(Attack x dmgPct[level]/100))` — `cfg13`(ConfigVar 0xd)=maxDmg (cap,
  rarity-scale), `cfg74`(ConfigVar 0x4a)=dmgPct (percentage, non rarity-scale). Gameconfig `TheQuickening` :
  `maxDmg`(rarity), `dmgPct`, `range:2`.

## 2. Mecanique (net observable)

Cast TILE-TARGET (le joueur/IA choisit une TUILE a portee-mouvement 2). Sur execution :

1. **ECHANGE** : le caster se teleporte sur la tuile ciblee ; l'unite eventuellement presente y est
   deplacee vers la tuile d'origine du caster (clean swap).
2. **FREE MELEE ATTACK** (caster PUIS unite-echangee, chacun SI BloodAngels) : attaque melee immediate
   depuis la nouvelle position, Attack OVERRIDE = `min(maxDmg[meph_lvl]xmult, round(unit.Attack x
   dmgPct[meph_lvl]/100))`. Config (maxDmg/dmgPct/level/mult) = celle de l'ability de MEPH ; Attack per-unit.
3. Les effets `Untargetable(0x414)` / `ForcedInMelee(0x529)` / `TemporaryStatOverride(0x510)` sont
   **transitoires** : ajoutes ET retires DANS le cast (net-zero, AUCUN effet persistant).

### Mesure live (probe_217, runner build seed 31337, MC1_67)

- cast meph(2,6) sur tuile ally(4,7) -> POST **meph=(4,7), ally=(2,6)** (SWAP net).
- effets transitoires Untargetable/ForcedInMelee/TemporaryStatOverride tous ajoutes+retires (net-zero).
- `Attack_Override` live : meph=**1204**, ally=**4818**. Formule offline (Attack meph=1003 x120% -> 1204 ;
  ally=4015 x120% -> 4818 ; cap maxDmg=4986 non liant ; level 50, mult 180) == live **exact** (both).

## 3. Port

- `scripts/python/engine/runner/abilities/loki/quickening.py` — `TheQuickeningAbility.execute_behaviour` :
  - SWAP via `MoveUnitOperation` (pose la position sans check d'occupation ; le natif lift-off puis MoveIn
    -> l'echange direct rend l'etat NET identique) ;
  - free-attack faction-BloodAngels (`_free_melee_attack`) = mirror de la chaine `op_BitwiseAnd` de
    `GetTriggerAttackBehaviour` DANS L'ORDRE NATIF : feuille `AddEffect(0x529 ForcedInMelee, Target(),
    duration_turns=1)` -> `set_stat_override(ATTACK, V)` (= le canal 0x510) -> **le port UNIQUE du noeud**
    `perform_ai_attack_from_current_position` -> `remove_stat_override` -> feuille `RemoveEffect(0x529)`
    (net-zero) ; `V = _quickening_override` (mirror `PercentageOfAttackCappedAtMax`). Cf. §5 (de-fork).
- Enregistrement : `ABILITY_CLASSES[1151]` (`handler.py`), re-export `loki/__init__.py`.
- `sets_end_turn_flags`/`sets_active_ability_used_flag` = defaut (1151 absent des inventaires d'override
  base.py ; confirme par le walk stages : le tour de meph se termine apres le cast, step 16 = autre unite).

## 4. Validation adversariale

- **Test offline e2e** `tests/engine/runner/test_the_quickening_live.py` (pattern thunderous_assault,
  DETERMINISTE : `load_state` + positions controlees + MT `dumpRng`) : SWAP (caster->T, ally->C) +
  free melee attack du caster BloodAngels sur l'ennemi adjacent (hp cible decroit). **PASS**.
- **Probe live** `probe_217_thequickening.py` (pattern 202c) : (A) SWAP live ; (B) effets transitoires
  net-zero ; (C) override formule offline == live (meph 1204, ally 4818) ; (D) confrontation offline
  (`load_state` PRE-cast + rejoue le message -> meme SWAP que live). **VERDICT PASS**.
- **Zero-regression** `engine_agreement_stages.py --build --seeds 31337` : ability 13/13, move 18/18,
  prediction 10/10, utilite 10/10 = **100%**. step 15 u81 ab=1151 tgt=52 **MATCH** (decision intacte).
- Guard `test_turnflow_endturn_flags.py` (chemin handler) : 9/9 PASS.
- **De-fork (2026-07-26)** : agreement re-joue **100%** (ability 13/13, move 18/18, prediction 10/10,
  utilite 10/10 ; step 15 u81 ab=1151 tgt=52 MATCH), + garde discriminante
  `test_perform_ai_attack_node_live.py` (3/3) et les tests des autres consommateurs du noeud
  (aberrant 4/4, summon_consumers 23/23, summon_ability_ports, summon_trigger, summon_trait_effects,
  alpha_warrior, ironkin_steeljack, scarab_summon_migration, runner_attack, overwatch) — cf. §5.

## 5. De-fork `PerformAIAttackFromCurrentPosition` (2026-07-26)

Le noeud natif n'a plus qu'**UN** port : `abilities/loki/summon.py::perform_ai_attack_from_current_position`.
La feuille DSL `PerformAIAttack` (`abilities/behaviours/summon.py`, domaine TUILE ou UNITE) et
`quickening.py::_free_melee_attack` y **delèguent** ; `_nearest_adjacent_enemy` est supprime.

### Ce que le decompile a tranche (et qui n'etait pas arbitrable entre les deux mirrors)

`DSLFactory$$PerformAIAttackFromCurrentPosition(unit, utilityEntity, customUtility, skipAtomicCheck)`
n'est qu'un CONSTRUCTEUR de `Entities.Behaviours.PerformAIAbilityUnitBehaviour` :

| champ | valeur pour ce noeud | role |
|---|---|---|
| `+0x50` | `unit` | selecteur d'ACTEURS, itere par `Execute` |
| `+0x68` | Func cache du `<>c` de `DSLFactory` | resolveur de l'ability d'ATTAQUE (seul delta vs `PerformAIAbility`, ou il est fourni) |
| `+0x70` / `+0x71` | `0` / `skipAtomicCheck` | drapeaux d'options — `+0x70` = `allowMoveAction` (cf. §7) |
| `+0x78` | **`factory+0xb8` = `Direct(0)`** | l'option `Nullable<int>` de l'appel IA = **0** : c'est LITTERALEMENT le « FromCurrentPosition » (budget de deplacement nul). Le noeud cousin `PerformAIAttack` est le MEME behaviour avec `+0x70` et `+0x78` FOURNIS par l'appelant — **§7 corrige la lecture initiale** : tous ses call-sites passent `moveAmount = null` (pas `1`) |
| `+0x80` / `+0x90` | `utilityEntity` / `customUtility` | surcharges d'UTILITE du choix de cible |
| `+0x88` | `0` | -> `Execute` prend la branche « pas de cible imposee » (appel IA slot 0x37) : **c'est l'IA qui choisit la cible** |

1. **Le dispatch after-hit est INCONDITIONNEL.** Aucun champ ne le gate : l'IA execute une VRAIE ability
   d'attaque, donc `FinishAttackOperation$$Execute` emet `On(0x26)`/`On(8)`/`On(9)` comme sur toute
   attaque normale. Preuve live pre-existante : la chaine Horror -> Screamer de #202-C passe par `On(9)`.
   **Les deux mirrors sans after-hit etaient donc FAUX** (voir « divergences chiffrees » ci-dessous).
2. **Le domaine adjacent de la free-attack n'est PAS un choix du port.**
   `IdunBattle.Core.Services.TargetingQuery$$GetRange` contient, juste avant son `Math.Min` final :
   `if (EntityExtensions.HasEffect(unit, …, 0x529, 0, 0)) { range = Math.Min(1, range); }`.
   L'`AddEffect(0x529 ForcedInMelee)` de `GetTriggerAttackBehaviour` est donc le PARAMETRE contextuel qui
   reduit la portee a 1. Le port **pose reellement l'effet** (feuille `AddEffect`, duree `Nullable<int>(1)`
   du decompile) avant d'appeler le noeud et le retire apres (feuille `RemoveEffect`) — net-zero conserve.
   Le clamp vit dans `_in_attack_range` / `_forced_in_melee` (`operations/triggers/base.py`), inerte
   partout ailleurs (aucun autre poseur de 0x529 porte).

### Divergences observables corrigees (chiffrees, seed 31337 / board MC1_67)

- **TheQuickening** : Meph porte une arme **ranged portee 2** (Psychic, gameconfig). Sans le clamp
  ForcedInMelee, la free-attack tire sur un ennemi a **distance 2** — mesure de la mutation :
  `attacks=[{attacker:81, target:77, override:1204, total:3321}]` la ou le natif ne fait **rien**.
  C'etait le piege exact de l'« union permissive » entre les deux anciens mirrors.
- **TheQuickening** : la free-attack ne reveillait **aucun** trigger post-attaque. Sonde = Judh
  (`genesKelermorph`, `On(9) & OwnerIsTarget`) : avant, zero reaction ; apres, l'effet-drapeau 1407 est
  pose (Judh se deplace + pose un decoy + contre-attaque).
- **Feuille DSL `PerformAIAttack`** (GetEmRuntz 1045, Poxwalkers 1040, drones Tau, ForwardSpotter 1143) :
  meme correction — les summons ne pompaient aucun trigger after-hit a l'apparition.

### Garde

`tests/engine/runner/test_perform_ai_attack_node_live.py` (3 tests, **verifies discriminants par
mutation** : desactiver le clamp ou l'after-hit les fait tomber).

## 6. Residus documentes (NON couverts)

- **Roll de degat de la free-attack = RNG** : non bit-exact offline (choix de cible + tirage). Approx
  faithful-structured (comme MasterOfTheTutelaries / ScarabSummon) ; en replay-diff, un cast 1151 peut
  desyncer la MT APRES le coup. Reste PREFERABLE au no-op (qui desyncait les POSITIONS, divergence plus
  large).
- **Choix de cible** : le moteur d'utilite IA natif n'est pas mirrore — approx `_nearest_enemy` A PORTEE
  (portee = `GetRange`, clamp ForcedInMelee inclus). TheQuickening passe EN PLUS un `customUtility`
  (lambda du display-class de l'ability, `+0x90`) qui ne peut que reordonner des cibles equivalentes en
  portee : non mirrore, meme classe de residu. Tie-break `id`.
- **EvaluateAbilities(0x1c=28)** (phases 3/5, on-move triggers) NON porte -> surface passive separee
  (aucun on-move passif BloodAngels au roster teste ; `AddFlag(1)`/`RefreshEffects(7)` idem).
- **Filtre `Attackable = UnitsWithoutTrait(0x1b=27)`** du swap-unit approxime par « toute unite vivante
  sur la tuile cible autre que le caster » (aucune unite trait-27 sur une tuile de swap teste ; le swap
  ne cible pas les tuiles ennemies en jeu AI reel — la decision ne les valorise pas).
- **`Reserve` / `SetCache` / `InvalidateCaches` / `EffectFromOwner(0x19)`** = plomberie DSL sans effet
  net observable (memoisation de tuile, reservation, invalidation de cache) -> non materialises.

## 7. De-fork RESIDUEL : `SpawnReplica` (ScarabSummon 1047) et le noeud cousin `PerformAIAttack` (2026-07-27)

Le §5 avait laisse UN call-site en dehors du corps unique : la feuille `SpawnReplica`
(`abilities/behaviours/summon.py`) re-cablait `_nearest_enemy` + `AttackDamageOperation.execute` a la
main. Elle delegue desormais, comme tout le monde, au corps unique — renomme
`perform_ai_ability_unit_behaviour` (homonyme du corps natif `PerformAIAbilityUnitBehaviour$$Execute`),
atteint par l'un des **deux** constructeurs `DSLFactory` :

- `perform_ai_attack_from_current_position(state, unit)` -> `allow_move_action=False`, `move_amount=0` ;
- `perform_ai_attack(state, unit, allow_move_action, move_amount)` -> valeurs de l'appelant.

### Correction de RE : le litteral `1` de `PerformAIAttack(1)` n'est PAS un budget de deplacement

`DSLFactory$$PerformAIAttack(unit, allowMoveAction, moveAmount, utilityEntity, customUtility)` — le `1`
est le **2e** argument (`+0x70`, un `bool`), le budget est le **3e** (`+0x78`) et vaut **`0` = null** a
TOUS les call-sites lus : `ScarabSummonAbility$$ExecuteBehaviour`, `ForwardSpotterAbility$$ExecuteBehaviour`,
`HunterOfSoulsAbility$$CreateBehaviour`, `TheArdentBlade_TriggerAbility$$CreateBehaviour`,
`AetherStrideAbility$$ExecuteBehaviour`, `CallInReinforcementsAbility$$CreateBehaviour` — tous
`PerformAIAttack(<selecteur>, 1, 0, 0, 0)`.

| champ | `...FromCurrentPosition` | `PerformAIAttack` |
|---|---|---|
| `+0x70` `allowMoveAction` | `0` (code en dur) | **`1`** (appelant) |
| `+0x71` `skipAtomicCheck` | appelant | `0` (code en dur) |
| `+0x78` `moveAmount` | `factory+0xb8` = `Direct(0)` | **`null`** (appelant, jamais renseigne) |
| `+0x90` `customUtility` | appelant | `Func` liant un display-class dont la capture vaut `null` |

**Ce que ces deux champs FONT**, chaine lue jusqu'au consommateur :
`Execute` -> `AiControl$$ExecuteAbilityActionFor(unit, abilityId, options)` ->
`DefaultAiUnitTactic$$CalculateAbilityActionForUnit` ->
`DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`, ou

- le `Nullable<int>` issu de `+0x78` part TEL QUEL dans
  `ABaseAiUnitTactic$$GenerateActionTiles(unit, true, maxDistance)` = les tuiles depuis lesquelles
  l'acteur peut AGIR (`0` = la tuile courante seule ; `null` = sa plage de deplacement normale) ;
- `allowMoveAction` ajoute le `MovementActionGenerator` (`tactic+0x58`, ecrit par
  `DefaultAiUnitTactic$$.ctor`) a la liste des generateurs -> l'IA peut choisir un DEPLACEMENT PUR.

**i2 confirme, et c'est le discriminant le plus net** : `PerformAIAttack` => « which then immediately
**takes a turn** » (ScarabSummon), « immediately **takes a turn** » (ForwardSpotter,
CallInReinforcements) ; `...FromCurrentPosition` => « can immediately **attack**, but **cannot move
this turn** » (AberrantHypermorph, GetEmRuntz).

Ordre verifie au decompile de `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` : l'on-appearance
(`options+0x18`) fire **AVANT** la pose du flag « cannot move » (slot `0x23`) — le flag ne gate donc
pas l'attaque du double.

### Divergences observables corrigees (chiffrees, seed 31337 / board MC1_67, `probe_r20_replica_rng_flow.py`)

| regime | AVANT (fork) | APRES (corps unique) |
|---|---|---|
| double a >= 3 hex du 1er ennemi | **1 attaque, 4860 degats**, 6 tirages MT | **0 attaque**, **1 tirage** (le `PickRandomly` du placement) |
| double AU CONTACT de Judh | 1 attaque, 4860 degats, 6 tirages, **`after_hit=False`** | 1 attaque, **4860 degats (identiques)**, **12 tirages**, **`after_hit=True`** (drapeau 1407 pose) |

Lecture du flux MT (le total de degat est IDENTIQUE dans les deux colonnes -> l'etage degat n'a pas
bouge) : 6 = 1 placement + 5 coups de l'arme du swarm. Hors portee, les 5 rolls disparaissent — c'etait
un degat roule pour une attaque que le natif n'execute jamais. Au contact, les 6 tirages
supplementaires sont ceux du vecteur after-hit (`On(9)` -> reaction Hypersensory de Judh), que le fork
sautait. La nouvelle consommation est donc la consommation NATIVE dans les deux regimes.

### Garde

`tests/engine/runner/test_perform_ai_attack_node_live.py` sections **D** (gate de portee) et **E**
(dispatch after-hit), **separees** pour qu'un echec dise laquelle des deux proprietes saute. Les deux
ont ete **vues ROUGES** sur le code d'avant (D : « le double a ATTAQUE une cible hors de portee …
total 7960 » ; E : « Judh n'a PAS reagi »). Tuile d'atterrissage rendue DETERMINISTE en bloquant toutes
les voisines du scarab sauf une avec des allies.

### Residu NOUVEAU, localise (candidat tache)

`move_amount is None` ne fait PAS bouger le double : ni `ABaseAiUnitTactic$$GenerateActionTiles` ni le
`MovementActionGenerator` ne sont portes. Le domaine d'action reste la tuile courante, donc un double
hors portee ne fait RIEN la ou le natif l'aurait fait avancer puis frapper. C'est un **manque-a-agir**,
jamais une attaque illegale. Il est visible dans `test_scarab_summon_migration_live.py`, dont la
geometrie a du etre PILOTEE (le double tombait au hasard a 1 ou 2 hex de la cible) pour continuer a
valider l'on-appearance plutot que ce residu. Les deux champs natifs sont **threades explicitement**
dans `perform_ai_ability_unit_behaviour` (et remontes dans son diag) pour que le residu reste localise
la, et non re-invente par un fork chez un appelant.
- **Effet `ForcedInMelee (0x529)` : SEUL le clamp de portee est porte.** `TargetingQuery$$GetRange`
  bascule aussi son drapeau `isMelee` de retour (2e sortie de la fonction) — non lu par le port, dont la
  nature melee/ranged d'un coup se derive de la POSITION (`_is_ranged_position`, mirror
  `DSLFactory$$IsRangedPosition`). Les deux convergent tant que la portee est clampee a 1 (cible
  adjacente -> melee), donc inerte ici ; a revoir si un autre poseur de 0x529 apparait.
- **`skipAtomicCheck` (`+0x71`) et l'ordonnancement ATOMIQUE de l'appel IA** ne sont pas materialises
  (le port execute la feuille sur-le-champ, comme tous les autres call-sites du noeud).
