# #419-r1-tr14-r4 — `HeavyBoltPistol` (1083), face COMBAT : PORTÉE + CONFRONTÉE LIVE

La face DÉCISION était portée et confrontée (#419-r1-tr14, puis sur ses porteurs réels par
#419-r1-tr14-r1). Celle-ci est l'EXÉCUTION : ce qui part **réellement** quand le porteur frappe.
Elle n'existait pas — mesuré, **299 PV manquants par attaque**.

## 1. Le canal n'est PAS un trigger d'événement — et c'est ce qui bloquait

`HeavyBoltPistolAbility` n'a **AUCUN** `$$CreateTrigger`. Ce n'est pas le faux négatif habituel des
tables indexées par adresse : les **DEUX** sources le disent, et la seconde est indexée par CLASSE.

| source | ce qu'elle porte pour `HeavyBoltPistolAbility` | témoin |
|---|---|---|
| `data/symbols/<build>/ghidra/functions.tsv` | `$$CreateBehaviour` seul | `HeadClaimerAbility` y a ses **deux** |
| `data/symbols/<build>/frida/methods.tsv` (par CLASSE) | `CreateBehaviour` seul | `PsykerExtraAttackAbility` y a `CreateTrigger` + 4 autres |

`IdunBattle.Entities.Abilities.BaseTriggeredAbility` n'en porte pas non plus, et son
`$$GetEventTriggers` **journalise une erreur** quand la liste sort vide. L'ability n'entre donc dans
aucun registre d'`EventTriggerType` : elle est appelée **en dur**, par l'attaque normale qu'elle
substitue.

```
IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive
    1083 HeavyBoltPistol -> l'ACTIVE 1046 TemplarInitiateNormalAttack      (#419-r1-tr14-r5-r1)

IdunBattleLogic.Entities.Abilities.Active.Loki.TemplarInitiateNormalAttackAbility$$ExecuteBehaviour
    b =   DSLBehaviors$$Group(<b__0>, DSLSelectors$$None(), GroupType.Ability_Attack = 0x20)
        & DSLBehaviors$$Group(<b__1>, DSLSelectors$$None(), GroupType.Ability_Attack = 0x20)
    return AActiveAbility$$ExecuteAtomic(b, entities,
                                         GroupType.TemplarInitiateNormalAttack_AtomicGroup = 0x52)

    <b__0> = $$ExecuteNormalAttack -> ALoki_NormalAttackAbility$$ExecuteBehaviour     # coups d'ARME
    <b__1> = $$ExecuteBonusAttack  -> AActiveAbility$$Execute(
                 DSLBehaviors$$TriggerAbility(entity = Caster@DSLSelectors+0x48,
                                              abilityType = 0x43b = 1083,
                                              actor = caster = Caster@+0x48,
                                              target = Target@+0x60,
                                              unitFeetTiles = null,
                                              selectionType = 3, ignoreUnitHavingAbility = false))
```

`IdunBattle.Entities.Behaviours.TriggerAbilityBehaviour$$Execute` construit un **NOUVEL**
`AbilityEntities` à partir de celui de l'attaque normale, puis **réécrit** `actor`, `caster`,
`target` et les tuiles depuis ses quatre sélecteurs — le reste (dont `CasterPosition`) est HÉRITÉ.
C'est ce qui rend `Owner@0x30 == Caster` sur cette voie, comme sur toute ability ACTIVE
(`ActiveAbilityOperation$$GetAbilityEntities` écrit l'entité caster dans `+0x00 Actor`,
`+0x08 Caster` **et** `+0x18 Owner`, lecture établie par #478-r4).

**L'ORDRE est ARME puis BONUS**, dans le même groupe atomique — c'est le rang exact auquel le port
insère le volet.

## 2. L'arbre, LU

```
HeavyBoltPistolAbility$$CreateBehaviour
    If( DSLTriggers$$IsMeleeAttack(<DSLTriggers+0x88>),            # surcharge à UN argument
        DSLBehaviors$$InformWeapon(GetDamageProfile(cfg), isMelee: true, useSpecial: null)
        op_BitwiseAnd
        DSLBehaviors$$AttackDamage(caster  = Owner@DSLSelectors+0x30,
                                   target  = Target@+0x60,
                                   amount  = DSLFormulas$$Direct(GetVariableForLevel(cfg, 0xb)),
                                   profile = DSLSelectors$$Direct(GetDamageProfile(cfg)),
                                   hits    = DSLFormulas$$Direct(GetNumberConstant(cfg, 0x2f)),
                                   abilityOrEffect = AbilityOrEffect(this),
                                   options = Nullable(<struct 0x20 à ZÉRO sauf l'octet +0 = 1>)),
        null )
```

Quatre lectures qui ne se devinent pas :

1. **`DSLBehaviors$$AttackDamage` n'est PAS `$$AttackWithAttackDamage`.** Elle construit un
   `IdunBattle.Entities.Behaviours.AttackDamageBehaviour` **SEUL** (dernier argument du ctor :
   `targetSelectionType = 2 OnlyTargetable`), là où `AttackWithAttackDamage` l'enveloppe d'un
   `AttackBehaviour`. Conséquence portée : la feuille existante en mode **mono-cible**
   (`multi=False`), sans l'`OrderBy` d'`AttackBehaviour$$Execute`.
2. **`isMelee: true` d'`InformWeapon` est un LITTÉRAL, et il nomme la nature du coup.**
   `DSLBehaviors$$InformWeapon(damageProfileType, isMelee, useSpecial)` inscrit trois clés :
   `0x93` = `TagKey.Attack_Weapon_DamageProfile` — l'**ORDINAL du `DamageProfileType`** (`-1` =
   `DamageProfileType.None_` si le `Nullable` est vide), `0x92` = `TagKey.Attack_Weapon_IsMelee` =
   **le 2ᵉ argument `isMelee`**, `0x94` = `TagKey.Attack_Weapon_Use_Special`, ajoutée **seulement
   s'il est non nul**. Le natif DÉCLARE donc ce coup MÊLÉE — c'est ce qui fixe `is_melee=True` sur
   la feuille (axe `ExtraPierceMelee` vs `ExtraPierceRanged` de `profile_pierce`), et non une
   déduction depuis la géométrie.
   ⚠ Cette fiche écrivait « `0x93` = weaponId dérivé du profil » : **FAUX**, et mesuré live —
   le flux rend `0` pour `Physical` et `14` pour `Power`, c'est-à-dire l'ordinal de l'enum.
   La docstring du foyer, elle, intervertissait `0x92` et `0x93`. Corrigé par
   **`#419-r1-tr14-r4-r2`** (`docs/rl/case-419-r1-tr14-r4-r2-inform-weapon-tags.md`).
3. **Le montant est la variable `dmg` SEULE** (`AbilityVariableType` **11 = `dmg`**), passée par un
   `Direct(v)` — un montant à valeur UNIQUE, pas un couple `minDmg`/`maxDmg`. Le nombre de coups est
   `GetNumberConstant(0x2f)` = `AbilityConstantType.nrOfHits` (= 1 au gameconfig courant).
4. **Le profil est celui de l'ABILITY (`Bolter`), jamais l'arme du caster** — déjà établi par la
   face DÉCISION, et re-gardé ici par une contre-épreuve (§5).

## 3. La gate n'était PAS devinable offline, et le seed BC dit l'INVERSE de la mesure

```
IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(ability, caster, casterPosition, target)
    if (!ability.HasValue) return false;
    switch (GetAbilityAttackRangeType(ability)) {
      case 0 None:   return false;
      case 1 Melee:  return true;
      case 2 Ranged: return false;
      case 3 Normal: return !UnitExtensions.HasFlag(caster, 0x15 ForceRangedAttack)
                            && AreEntitiesAdjacent(casterPosition, target);
    }
```

`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` lit l'`AttackRangeType` de la
**configuration d'ability de la BATAILLE** (`BC.Abilities.*`), pas le gameconfig : pour une
`TriggeredAbilityType` il mappe les configs puis passe par
`$$SelectAbilityAttackRangeTypeFromMultiple` (qui part de `None` et ne le remplace que par un type
qui l'`Overrides`, sinon lève).

Or **`data/seed-bc.json` porte `AttackRangeType: 0` pour `HeavyBoltPistol`**. Pris au pied de la
lettre : gate toujours fausse, bonus **mort**. C'est la MESURE qui tranche, et elle dit l'inverse.
Cette tranche est donc un cas où lire le décompilé **sans mesurer** aurait produit un verdict
« dead code » faux — le symétrique exact du piège que la doctrine nomme dans l'autre sens.

## 4. La mesure — trois crans, deux hôtes, bras apparié

`probe_419r1tr14r4_heavy_bolt_pistol_bonus_attack.py`. Bras `graft` = le passif présent ;
`base` = le même moins 1083 (`--unit-stat "<visualId>:PassiveAbilities=[]"`). Retirer 1083 ramène
l'attaque normale de `1046` à `69 Loki_NormalAttack` — **les deux passent par le même
`ALoki_NormalAttackAbility$$ExecuteBehaviour` pour les coups d'arme**, donc l'écart entre les bras
EST le bonus et rien d'autre. Board `MC1_67`, `Health = 10000` (personne ne meurt).

| cran | hôte (arme) | distance | natif `graft` | natif `base` | **TERME natif** | coups natifs | port AVANT | port APRÈS |
|---|---|---|---|---|---|---|---|---|
| `npc_adj` | `templNpc1Initiate:33` (`Chain`, mêlée) — **porteur RÉEL** | contact | 1360 | 1061 | **+299** | 2 -> **3** | +0 | **+299** |
| `graft_adj` | `tauMarksman` (`Piercing` 3, portée) — 1083 greffé | contact | 1536 | 1237 | **+299** | 1 -> **2** | +0 | **+299** |
| `graft_far` | idem | 2 hex | 4401 | 4401 | **+0** | 1 -> 1 | +0 | **+0** |

Écart port − natif : **0 aux trois crans**, avant comme après (le cran `far` était déjà juste, par
accident : le port ne jouait rien nulle part).

**Le zéro de `graft_far` n'est pas un régime dégénéré** : le MÊME montage rend `+299` au contact.
C'est ce couple qui établit que la branche effective est **`Normal(3)`** — ni `Melee(1)` (qui
rendrait vrai à 2 hex), ni `None(0)` (qui rendrait faux au contact).

**Le montant est DÉCOMPOSÉ, pas fitté** : `(level 50, multiplier 180)` mesurés sur l'entité →
`ability_var(HeavyBoltPistol, dmg) = 1496`, puis perçage `Bolter` 20 % → **299**. Identique sur les
deux hôtes, **dont les armes diffèrent** — ce qui est précisément la lecture « le profil vient de
l'ABILITY ». La ventilation par coup le confirme d'un second canal : le coup supplémentaire porte
`Active_Ability_Type = None` (signature d'un `AttackDamageBehaviour` dont l'`AbilityOrEffect` est
une TRIGGERED), là où les coups d'arme portent `1046`.

## 5. Les six contre-épreuves — et le piège qui était sur le chemin

Critère = **déplacement par rapport au port non muté**, jamais l'écart au natif (piège #441/#446).
`a_mordu` est rendu SÉPARÉ du verdict.

| mutant | `npc_adj` | `graft_adj` | `graft_far` |
|---|---|---|---|
| `no_gate` (la gate ne coupe jamais) | inerte | inerte | **+299** |
| `gate_off` (elle coupe toujours = le port d'avant) | **−299** | **−299** | inerte |
| `no_dispatch` (le passif n'est pas reconnu substituant) | **−299** | **−299** | inerte |
| `profile_weapon` (le profil serait celui de l'ARME) | inerte | **+898** | inerte |
| `amount_half` (`GetVariableForLevel(0xb)` / 2) | **−149** | **−149** | inerte |
| `hits_two` (`GetNumberConstant(0x2f)` forcé à 2) | **+299** | **+299** | inerte |

**Chaque mutant mord sur au moins un cran** — aucun n'est décoratif.

⚠ **Le piège de la tranche précédente était exactement sur ce chemin, et il a été désamorcé par
MESURE.** Sur le porteur RÉEL, `profile_weapon` est **algébriquement inerte** : l'arme de
l'`Initiate` est `Chain` et l'ability porte `Bolter`, or **les deux ont `PiercingRatio = 20`**. La
faute « et si le port lisait l'arme du caster ? » y est donc INOBSERVABLE. Elle mord à **+898** sur
la greffe (`Piercing`, ratio 80 : `1496 × 0,80 = 1197`, soit `1197 − 299`). Le probe **mesure**
l'équivalence des deux profils et en **déduit** ce qu'il exige du mutant ; la garde asserte les
DEUX sens (`Chain ≡ Bolter` sur le npc, `Piercing ≠ Bolter` sur la greffe) — si l'un des deux
cesse, la ligne rougit.

De même, `no_gate` est inerte partout où la gate est déjà vraie : il ne mord qu'à 2 hex. Les
inerties attendues sont gardées **à l'envers** (on EXIGE l'inertie) plutôt que tues.

### La garde a été vue ROUGE — par mutation du mécanisme LIVRÉ

`is_melee_attack -> False` posé **dans le port livré** (c'est-à-dire exactement l'état d'avant la
tranche), garde rejouée sur le cran `npc_adj` : **3 failed, 1 passed**. Messages VERBATIM :

```
[npc_adj] TERME porte +0 != TERME natif +299 (ecart -299 PV) -- la face COMBAT de HeavyBoltPistol
ne reproduit pas l'execution native

[npc_adj] le natif emet 3 coups [537, 524, 299] et le port en joue 2 (arme [537, 524] + bonus [])
-- meme total de degats, la ventilation differe

[npc_adj] contre-epreuves en desaccord : ['no_gate: a_mordu=True (attendu False), deplacement=+299',
'gate_off: a_mordu=False (attendu True), deplacement=+0', 'no_dispatch: a_mordu=False (attendu
True), deplacement=+0', 'amount_half: a_mordu=False (attendu True), deplacement=+0', 'hits_two:
a_mordu=False (attendu True), deplacement=+0']
```

Le **1 passed** est `test_terme_natif_est_celui_attendu` : l'étage qui arbitre le NATIF reste vert.
C'est ce qui établit que la garde accuse le PORT et non le montage — une garde qui rougirait des
deux côtés ne distinguerait pas les deux causes.

Restauration → **13 passed** (les trois crans, sur l'arbre rebasé incluant #703 et #704).

## 6. Le port

| rôle | chemin |
|---|---|
| port (arbre + gate + dispatch) | `scripts/python/engine/runner/abilities/loki/heavy_bolt_pistol.py` |
| câblage | `scripts/python/engine/runner/operations/damage.py` (`visit_AttackUnitMessage`) |
| probe (MESURE) | `scripts/python/probe_419r1tr14r4_heavy_bolt_pistol_bonus_attack.py` |
| garde (TEST) | `scripts/python/tests/engine/test_419r1tr14r4_heavy_bolt_pistol_live.py` |

**DOCTRINE #149** : `CreateBehaviour` = un VRAI arbre DSL (`Seq` = le `op_BitwiseAnd` natif,
feuilles `InformWeapon` + `AttackWithAttackDamage`). Le `If` natif n'est **pas** enveloppé en nœud :
sa condition est un slot d'`IBattleQuery` (runner-couplé), évaluée impérativement par l'appelant —
la même frontière que `primary_fold_tree` / `is_melee_position` d'`abilities/loki/additional_targets.py`.

**UN SEUL SWITCH** : la gate ne ré-écrit pas `BattleQuery$$IsMeleeAttack`, elle DÉLÈGUE au foyer
`engine/services/battle_query.py::is_melee_attack` en lui passant le substrat géométrique obtenu du
`Board` par `walk_maps_by_pos()` — le même canal que `operations/triggers/loki/empyric_ambush.py`,
l'autre consommateur RUNNER de ce slot. (Cet autre consommateur, lui, ré-écrit le switch : résidu
d'unification non ouvert ici, hors périmètre.)

**Mode BORNES avec `min_key == max_key == dmg`** : le natif passe un `Direct(v)`, montant à valeur
unique ; `ability_attack_params` lit alors `ability_var(HeavyBoltPistol, dmg, <niveau du PASSIF>)` et
`execute_ability_attack(bmin == bmax)` entre dans `AttackDamageOperation$$ExecuteHit` par
`MinMaxDamageFix64(d, d)` — la branche PLATE, sans re-dériver le niveau hors du foyer.
`level_slot="passive"` parce que `UnitFactory$$AddNormalAttackAbility` monte l'attaque normale
substituée avec le `triggeredAbilityState`.

**`ability_type` n'est PAS threadé** : l'`AbilityOrEffect(this)` natif porte une
`TriggeredAbilityType`, pas une `ActiveAbilityType` — et c'est OBSERVABLE (le coup bonus rend
`Active_Ability_Type = None`). Même choix, même raison, que `triggers/loki/hateful_assault.py`.

**Le dispatch passe par le FOYER de la cascade** (`substitutes_normal_attack`), jamais par
`1083 in passives` : une unité qui porte `HeavyBoltPistol` **derrière** un autre passif substituant
reçoit l'attaque normale de l'AUTRE, n'exécute donc pas `TemplarInitiateNormalAttackAbility`, et ne
tire pas le coup de pistolet.

### Non-régression, rejouée APRÈS rebase

`master` a avancé pendant la tranche, et **#703 (`#419-r1-tr14-r1-r1`) touche l'attaque normale**
elle-même (sélection d'arme gatée sur la portée depuis la tuile d'attaque). Tout a donc été rejoué
sur l'arbre rebasé, pas sur celui de départ :

| rejoué | résultat |
|---|---|
| `test_419r1tr14r4_heavy_bolt_pistol_live.py` (cette tranche) | **13 passed** |
| `test_478_cleave_live.py` (le site JUMEAU dans `damage.py`) | **13 passed** |
| `test_419r1tr14r1_heavy_bolt_pistol_real_carriers_live.py` (même ability, face DÉCISION) | **11 passed** |
| `test_419r1tr14_heavy_bolt_pistol_live.py` (tranche mère) | **6 passed** |
| `test_419r1tr14r5_normal_attack_dispatch_live.py` (le dispatch dont dépend le volet) | **6 passed** |
| `test_419r1tr14r1r1_range_gate_generalisation_live.py` (#703, la gate de portée juste en amont) | **5 passed** |
| `probe_477r15a_stream_conformance.py` (oracle : le volet ÉMET un coup de plus) | **VERT** — `C1_02` 204/204, `MC1_67` 316/316, registre à jour |
| `probe_181_targeting_gaps.py` / `probe_120_pre_unit_ability_fork.py --step 0` | **0 manquante** / `litteral de ctor manquant: aucun` |
| `probe_449r2_spread_inventory.py` | **VERT** (ce volet n'ouvre aucun call-site en mode `amount`) |

## 7. Registre `ABILITY_CLASSES` : sans objet

`HeavyBoltPistol` est un TRIGGERED (`PassiveAbilityType` 1083), jamais casté : il n'entre pas dans
`ABILITY_CLASSES` et ne porte donc ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` (§9 de la tranche
mère). L'ACTIVE qui le tire, `1046 TemplarInitiateNormalAttack`, **porte déjà** les deux
(`runner/abilities/targeting.py` → `_NORMAL_ATTACK_OPTIONS_PRESET_00`, `runner/abilities/attack_type.py`).
Aucun compteur n'est rouvert par cette tranche — vérifié, pas supposé.

## 8. Résidus NOMMÉS

* **`#419-r1-tr14-r4-r1` — l'octet `+0` du `Nullable<AttackDamageBehaviourOptions>` est posé à `1`,
  sémantique NON RÉSOLUE.** Le call-site `memset` la struct de 0x20 octets puis écrit `1` à l'offset
  **0** avant de la passer en 8ᵉ argument. Les trois octets dont le port connaît le sens sont `+4`
  (`alwaysOverkilled`), `+5` (`alwaysCrit`) et `+6` (le drapeau « attaque normale », qui pilote le
  spread) — tous **à zéro** ici, ce que la mesure confirme (le bonus vaut exactement
  `round(dmg × PiercingRatio)`, déterministe, identique sur deux hôtes et deux seeds). L'octet `+0`
  est donc INERTE sur ce montage ; son sens reste à lire dans
  `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (il transite `AttackDamageBehaviour+0x98`).
  Débloqueur : un régime où la cible peut mourir, ou porte un bouclier.
* ~~**`#419-r1-tr14-r4-r2` — `InformWeapon` : deux arguments non portés, et une lecture FAUSSE dans
  la docstring du foyer.**~~ **RÉSOLU** — `docs/rl/case-419-r1-tr14-r4-r2-inform-weapon-tags.md`.
  Les deux clés sont portées et confrontées LIVE (le canal n'est pas un « no-op » : il part en
  `StepType.Info`), et la docstring est corrigée — elle se trompait sur **quatre** points, pas un.
* **`#419-r1-tr14-r4-r3` — l'ancrage `casterPosition` de la gate est LU mais NON EXERCÉ.**
  `BattleQuery$$IsMeleeAttack` évalue `AreEntitiesAdjacent(casterPosition, target)`, où
  `casterPosition` vient de l'`AbilityEntities` **hérité** de l'attaque normale (`TriggerAbility` ne
  réécrit ni `CasterPosition` ni son drapeau `HasCasterPosition`). Sur la voie COMBAT, la tuile
  d'attaque **est** la position réelle du caster : les deux ancres coïncident et rien ne les sépare
  ici. Un port qui lirait la position réelle passerait ces trois crans. Débloqueur : un vecteur où
  l'attaque normale s'exécute depuis une tuile ≠ position réelle. (Jumeau COMBAT de
  `#419-r1-tr14-r2`, qui nomme le même angle mort côté DÉCISION.)
* **`#478-r3` (déjà ouvert, ÉLARGI)** — le câblage ne couvre que la voie MESSAGE
  (`visit_AttackUnitMessage`), pas les portes qui appellent `AttackDamageOperation.execute`
  directement (overwatch, `UseActiveAbility`, summon AI). Ce site est le TROISIÈME jumeau (après
  MV71 et le cleave), même cause : le natif n'a qu'un site parce que l'ability EST le corps de
  l'attaque normale.

## 9. Ce qui n'est PAS couvert

* **Le second porteur `templInitiate` (SUMMON)** : il arrive en bataille mais son terme n'y est pas
  appariable — quatre causes MESURÉES par #419-r1-tr14-r1 §6 (auto-jeu `PlayAutomaticUnits`,
  `--place` détourné par le trait `Summon`, plus aucune tuile d'action, bras apparié rompu). Ce que
  la face COMBAT ajoute ne change rien à ces bornes. Le npc partage avec lui `visualId`, arme,
  `Movement`, passifs, actifs et attaque normale.
* **Le régime KILL / OVERKILL** : `Health = 10000`, personne ne meurt. `force_overkill`,
  `force_crit` et l'octet `+0` (r1) restent donc non discriminés.
* **`ExtraPierceMelee` vs `ExtraPierceRanged`** : le coup est déclaré MÊLÉE (lecture 2), mais aucun
  des deux hôtes ne porte l'un ou l'autre — le mutant qui inverserait `is_melee` serait inerte sur
  ce montage. Débloqueur : un hôte porteur d'un `ExtraPierceMelee ≠ ExtraPierceRanged`.
* **La chaîne after-hit** : le coup bonus est joué avant `after_hit_normal_attack` (rang natif), mais
  aucun trigger `On(0x26)` du montage ne le consomme — l'ordre relatif des deux n'est donc pas
  discriminé par ces crans.
