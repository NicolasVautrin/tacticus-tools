# Case #85 — DespoiledGround : les deux manques qui lui étaient PROPRES sont fermés

**Status : LIVRÉ et CONFRONTÉ LIVE (build `gqfc5mff6c`).** Le critère binaire de la tâche —
« un DespoiledGround posé en bataille expire-t-il au même tour offline que live, et son
déclenchement sur dégât inflige-t-il ce que le natif inflige ? » — se répond **OUI aux deux**,
chiffres à l'appui (§4).

État réel des deux manques au moment de l'attaque (vérifié dans le code, pas hérité de la fiche) :

| Manque annoncé | État constaté | Ce qui a été fait |
|---|---|---|
| vecteur `On(0x10 = DamageDealt)` absent du dispatch | **ABSENT** (aucune occurrence de `EventTriggerType.DamageDealt` hors l'enum et trois commentaires « n'existe pas ») | porté (`dispatch/attack.py::damage_dealt_triggers`) |
| classe d'effet **1476** non portée (seule sa durée l'était, `_DEFAULT_ROUNDS[0x5c4] = 2`) | **ABSENT** (`EFFECT_CLASSES` n'avait ni `DespoiledGround` ni `DespoiledGround_ExtraDamagePct`) | portées toutes les deux + l'ability d'environnement qui les fait vivre |

La scission de `dispatch.py` en package (#169, merge `cf77f62`) était bien faite : le vecteur est
entré dans `dispatch/attack.py`, à côté de `damage_taken_triggers`, sans coordination d'ordre.

---

## 1. Gate de confrontabilité — QUI porte DespoiledGround

| Porteur | Catégorie | Chemin vers la bataille |
|---|---|---|
| `blackObliterator` « Volk » (Black Legion), passif `FleshmetalGuns` | **HERO** | **présent dans `rl_duel build --list-pool` rank 17** — c'est le porteur utilisé par tout ce qui suit |
| les 5 porteurs du trait `LetTheGalaxyBurn` (volet 2, `AddEffect(0x5c4)`) | HERO | dans le pool, mais ce volet-là **reste non porté** (hors périmètre, cf. §6) |
| `EnvDespoiledGroundTileAbility` | ENVIRONNEMENT | ability portée par la TUILE, pas par une unité — atteignable dès qu'une tuile porte 1476 (même patron que `EnvFireTileAbility`) |

⚠ **Volk porte les DEUX poseurs** (`traits = [Hero, LetTheGalaxyBurn, BigTarget, Daemon,
HeavyWeapon, SuppressiveFire]`, `passiveAbilities = [FleshmetalGuns]`). C'est mesurable :
sur trois montages identiques, la source de l'instance 1476 observée live a valu **la TUILE**
(FleshMetalGuns, source nulle → fallback « la source est la cible ») dans deux cas et **Volk**
(LetTheGalaxyBurn, `AbilityStateReference` explicite) dans le troisième. Les gardes assertent donc
la PRÉSENCE et la DURÉE, jamais la source.

---

## 2. RE native (décompilé ghidra, build `gqfc5mff6c`)

### 2.1 L'émetteur de `On(0x10)` n'est PAS celui que le port croyait

`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` n'émet que **deux** events :
`0x3d` (branche `if (param_6 != 0)` = le flag BLOCK) puis `8` (after-hit, inconditionnel).
**Aucun `0x10`.** Le vrai émetteur est `IdunBattle.Operations.ApplyDamageOperation$$Execute`, qui
émet dans l'ordre `0x3a` (PreDamageTaken) → `0xf` (DamageTaken) → `0x10` (DamageDealt).
Les en-têtes de `triggers/loki/fire.py` et `triggers/loki/on_toxic_damage.py` attribuaient `0x10` à
`EvaluateAfterHitTriggers` — mis-attribution corrigée.

### 2.2 L'`AbilityEntities` de `On(0x10)` : caster == actor == la SOURCE, target == la VICTIME

L'ordre des arguments d'`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` est
**`(caster, actor, target, owner, …)`**, PROUVÉ par les offsets que lisent les sélecteurs (et non
déduit d'un nom) :

| Sélecteur natif | offset lu | champ écrit par le ctor |
|---|---|---|
| `IdunBattle.Entities.Selectors.ActorSelector$$Select` | `+0x00` | 2ᵉ argument |
| `IdunBattle.Entities.Selectors.CasterSelector$$Select` | `+0x08` | 1ᵉʳ argument |
| `IdunBattle.Entities.Selectors.TargetSelector$$Select` | `+0x10` | 3ᵉ argument |
| `IdunBattle.Entities.Selectors.OwnerSelector$$Select` | `+0x18` | 4ᵉ argument |

Contrôle : `EvaluateAfterHitTriggers` construit `ctor(attaquant, défenseur, défenseur, défenseur)`
⇒ « caster = attaquant, owner = actor = target = défenseur », exactement ce que le port avait déjà
écrit pour `On(0x3d)`/`On(8)`. `ApplyDamageOperation` construit `ctor(param_3, param_3, param_4, 0)`
⇒ **caster == actor == la source du dégât, target == la victime** — donc `get_OwnerIsCaster` se lit
`ev.actor_id == owner_id` et `Tiles(Target@0x178)` est la tuile de la victime.

### 2.3 Gate de l'émission

`On(0x10)` part dans le MÊME bloc que `On(0xf)` — gate `0 < réduction de PV RÉELLEMENT appliquée ||
!HealthComponent.IsUnitWithHealthStat(cible)` — sous **un conjoint supplémentaire** (`local_7e8 == 0`)
qui combine « le dégât SANTÉ demandé est ≥ 1 » et un octet de la struct de coup (`hitInfo+0x94`).
Le port émet sous le gate lu et modélisable (`applied > 0`, le chokepoint `_apply_damage_pipeline`)
et **ne modélise pas** le conjoint `hitInfo+0x94` : résidu FLAGGÉ, qui ne peut que RESTREINDRE
l'émission native, jamais l'élargir.

### 2.4 La pose — `FleshMetalGuns_TileEffectAbility`

```
CreateTrigger   = On(0x10) & get_OwnerIsCaster & HasEffect(Self@0x148, 0x4c5 = 1221 WarpHail, 0, 6)
CreateBehaviour = AddEffect(0x5c4 = 1476, AbilityStateReference, Tiles(Target@0x178), 0, 0)
```

C'est **la même surcharge, avec les mêmes arguments**, que
`IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour`
(`AddEffect(f, 5, stateRef, Tiles(target), 0, 0)`) : 5ᵉ argument NUL = aucun nœud de durée ⇒
`DefaultAmountOfRounds(0x5c4)` = **2 rounds**, converties en TOURS par `AddEffectOperation`
(`ConvertRoundsToTurns`, #98) = **4** dans un duel standard.

**Source de l'effet : la TUILE, pas le caster.** Le sélecteur SOURCE de cette surcharge est nul, et
`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` retombe alors sur la CIBLE. GROUND
TRUTH live (`probe_85_despoiled_ground.py`, runners 365 / 8514) : `source = 51` puis `24`, soit
**l'id de la tuile ciblée**, jamais celui de Volk. Le port passait le caster ; corrigé
(`source_from_target=True`). ⚠ **La même mesure confirme le résidu jumeau flaggé dans
`on_fire_damage_tree`** (« le port passe encore le caster ») — non corrigé ici, hors périmètre.

### 2.5 Ce que la tuile INFLIGE — `EnvDespoiledGroundTileAbility`

```
CreateTrigger   = On(0x14 = TurnStart_EnvironmentEffects)
                  & AmountIsGreaterThanZero(Count(EntitiesWithAnyEffect(df@0x78, 0x5c4, 2)))

CreateBehaviour = Foreach( UnitsWithoutTraits(df@0x88, [0x1b = 27 Steppable, 0x19 = 25 Immune], 3)
                           & Units(EntitiesWithAnyEffect(df@0x78, 0x5c4, 2), 1, 1),
    AttackWithAbilityDamage( Tiles(elem@0x180), elem@0x180,
        RandomAmount( PercentageOf(StatAmount(elem, Health=5, Maximum=2), EffectConfig(9)),
                      PercentageOf(StatAmount(elem, Health=5, Maximum=2), EffectConfig(10)) ),
        AbilityOrEffect(0x5c4), { , Direct(Nullable(0xf)) } )
  + If( IsTurnOf(elem) & HasTrait(elem, 0x7ea = 2026 Chaos) & NOT HasTrait(elem, 0x19 = 25 Immune),
        AddEffect(0x5c6 = 1478, AbilityStateReference, elem@0x180, df@0xc0 = Direct(1)) ) )
```

Forme STRICTEMENT identique à `EnvFireTileAbility` (même event, même `Count(EntitiesWithAnyEffect)`,
même couple de traits exclus) ⇒ même abstraction de port : un `TileEffectTrigger` par tuile porteuse.

**Les trois lectures qui font le nombre :**

1. **`EffectConfig(9)` / `EffectConfig(10)`** — `IdunBattle.Core.Services.BattleQuery$$GetEffectConfig`
   indexe la section `Effect` de la BattleConfiguration **par l'ordre de ses entrées** :
   `0 PinnedDmgReductionPct · 1 PinnedMovementReduction · 2 StunnedMovement · 3 StunnedDmgReductionPct ·
   4 MarkerlightDmgBonusPct · 5 IceCritDmgBonusPct · 6 ContaminatedArmorReductionPct ·
   7 MachineVengeanceExtraPct · 8 DespoiledGroundExtraDmgPct · 9 DespoiledGroundMinDmgPct ·
   10 DespoiledGroundMaxDmgPct`.
   **Triple recoupement** de l'indexation 0-based : `6 → ContaminatedArmorReductionPct` (RE #132,
   indépendante), `8 → DespoiledGroundExtraDmgPct` (= la clé citée VERBATIM par l'i2
   `UnitEffects/DespoiledGround_ExtraDamagePct_Description`), `9/10` → le min/max du DoT.
   ⇒ **le DoT est un tirage uniforme dans `[6 %, 9 %]` de la PV MAX** de l'occupant.
2. **`Direct(Nullable(0xf))`** = le champ `+0x90` de l'`AbilityDamageBehaviour`. `0xf = 15` est un
   membre d'`IdunBattle.Entities.Enum.DamageProfileType` : **`15 = DirectDamage`** (PiercingRatio
   100). Corroboré par le DoT de feu, où le MÊME champ vaut `3` et où le port utilise `Flame`
   (`3 = Flame`, choix live-validé net 477 = base 1908 × PiercingRatio 25 %). Deux points
   indépendants, même énum — la note « sémantique non RE'd » de `AttackWithAbilityDamage` est levée.
3. **`RandomAmount`** — `IdunBattle.Entities.Formulas.RandomAmount$$Calculate` :
   `min = @+0x10.Calculate ; max = @+0x18.Calculate ; return rng@+0x20.<slot 2>(min, max + 1)`.
   Le `+ 1` est LU : l'intervalle est **inclusif des deux côtés**, et le slot 2 est
   `IntBasedMersenneTwister$$NextInternal(lo, hi)` (hi exclu) ⇒ **UN tirage** par occupant affecté.

### 2.6 Les deux classes d'effet

`DespoiledGroundEffect` (1476) ne surcharge que trois virtuels — recherche exhaustive des symboles
`DespoiledGroundEffect$$*` : `CreateTargetSelector` = `Self@0x148` ; `CreateActiveCondition` =
`AmountIsEqualOrGreater(Walkable(Self), 1) | AmountIsEqualOrGreater(AllAliveMachines(Self), 1)` ;
`.ctor`. **Aucune contribution de dégât propre** — même profil que `FireEffect`.

`DespoiledGround_ExtraDamagePctEffect` (1478) :
```
CreateEffectDamageBonusForAttack :
    trigger = HasTrait(target@0x178, 0x3ee = 1006 Xenos) | HasTrait(target@0x178, 0x1a = 26 Imperial)
    amount  = EffectConfig(8) = DespoiledGroundExtraDmgPct = 15
    kind    = PercentIncrease
CreateActiveCondition = IsWalkable(Self@0x148)
.ctor = BaseEffect..ctor(this, AbilityOrEffect(0x5cb), 1, 0)
```
**Le `kind` n'est pas déduit du nom** : la fabrique est INLINÉE, on la reconnaît à l'OFFSET écrit.
`EffectBonus$$ForPercentIncrease` écrit `out[0]=trigger ; out[1]=amount` (montant à **+0x08**) ;
`EffectBonus$$ForAddition` écrit `out[1]=0 ; out[2]=amount` (montant à **+0x10**) ; les deux copient
le `Nullable<AbilityOrEffect>` à **+0x34**. Le corps de 1478 pose le montant à `+0x08`, laisse `+0x10`
à zéro et le Nullable à `+0x34` ⇒ **`ForPercentIncrease`**, cohérent avec l'i2 « +15 % Damage ».

⚠ **Qualification d'énum** : le `0x5cb` du `.ctor` est **1483 = `TriggeredAbilityType.
EnvDespoiledGroundTileDamage`** (l'ability SOURCE de l'effet), PAS l'`EffectType` 1483
(`PrioritisedEfficiency_DmgReduction`).

---

## 3. Le port

| Face | Fichier | Mirror |
|---|---|---|
| Vecteur `On(0x10 = DamageDealt)` | `runner/operations/triggers/dispatch/attack.py` (`damage_dealt_triggers`) + son émission dans `runner/operations/damage.py` (`_apply_damage_pipeline`) | `ApplyDamageOperation$$Execute` (séquence `0x3a` → `0xf` → `0x10`) |
| Pose DespoiledGround | `runner/operations/triggers/loki/fleshmetal_guns.py` (`FleshmetalGunsTileEffectAbility`, `fleshmetal_guns_tile_effect_tree`) | `FleshMetalGuns_TileEffectAbility$$CreateTrigger` / `$$CreateBehaviour` |
| Classe d'effet 1476 | `entities/effects/loki/status.py` (`DespoiledGroundEffect`) + `entities/effects/factory.py` | `DespoiledGroundEffect$$CreateTargetSelector` / `$$CreateActiveCondition` / `$$.ctor` |
| Classe d'effet 1478 | `entities/effects/loki/status.py` (`DespoiledGroundExtraDamagePctEffect`) | `DespoiledGround_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack` |
| DoT d'environnement + buff Chaos | `runner/operations/triggers/loki/despoiled_ground.py` (`DespoiledGroundTileDoT`, `env_despoiled_ground_tile_tree`) | `EnvDespoiledGroundTileAbility$$CreateTrigger` / `$$CreateBehaviour` |
| Nœud VALEUR `RandomAmount` | `entities/formulas.py` | `DSLFactory$$RandomAmount` → `RandomAmount$$Calculate` |
| Nœud PRÉDICAT `IsTurnOf` | `entities/triggers.py` + `DslContext.current_player_id` (`dsl/base.py`, `runner/abilities/behaviours/context.py`) | `DSLFactory$$IsTurnOf` (ctor gshared MISLABELÉ `HasUsedActiveAbilityThisTurnTrigger..ctor` — structure lue, jamais le nom) |

Frontière DSL/impératif respectée : l'arbre `env_despoiled_ground_tile_tree()` est un arbre de nœuds
(`op_add(AttackWithAbilityDamage, If(TriggerAnd(IsTurnOf, HasTrait), AddEffect))`) ; le `Foreach`
d'occupants reste résolu en amont par le `TileEffectTrigger`, **même DSL-ification déférée que
`env_fire_tile_tree`** (#216) — pas une exception inventée pour ce cas.

---

## 4. Validation LIVE — la réponse chiffrée au critère

Montage : `probe_85_despoiled_ground.py` (build isolé board `MC1_67`, contact drivé des DEUX camps,
attente du tour **WarpHail** de la rotation NATIVE, capture `decisionView`/`observeBattle`/
`combatSnapshot`/`boardGraph`/`tileMeta`/`dumpRng`, attaque LIVE, rejeu OFFLINE sur la MÊME capture
et le MÊME MT). Gardes : `tests/engine/runner/test_despoiled_ground_live.py` (**5 passed**).

| Mesure | Victime IMPERIAL (`astraBullgryn`) | Victime CHAOS (`blackTerminator`) |
|---|---|---|
| Tuiles despoilées AU BUILD | `[]` (observation causale) | `[]` |
| Pose LIVE sur la tuile de la victime | oui, `remaining = 4` | oui, `remaining = 4` |
| Pose OFFLINE (rejeu de la même attaque) | oui, `remaining = 4` | oui, `remaining = 4` |
| `ConvertRoundsToTurns(DefaultAmountOfRounds(1476))` | **4** | **4** |
| Contrôle NÉGATIF offline (WarpHail retiré) | `[]` — rien posé | `[]` |
| **DoT au tick `On(0x14)` : LIVE** | **31 662** | **48 339** |
| **DoT au tick `On(0x14)` : OFFLINE** | **31 662** | **48 339** |
| bande `[6 %, 9 %] × StatAmount(Health, Max)` | `[24 000, 36 000]` → **dans la bande** | hors bande (cf. note) |
| buff 1478 sur l'occupant, LIVE | `[]` (gate `HasTrait(Chaos)` faux) | `['DespoiledGround_ExtraDamagePct']` |
| buff 1478 sur l'occupant, OFFLINE | `[]` | `['DespoiledGround_ExtraDamagePct']` |
| **Tour d'expiration LIVE / OFFLINE** | **3 / 3** | **3 / 3** |
| trace `(k, remaining live, présent offline)` | `[(1,2,T),(2,1,T),(3,None,F)]` | idem |

**Réponse au critère : OUI aux deux moitiés.**
* *expire-t-il au même tour ?* — **OUI** : extinction au tour **3** des deux côtés, avec la même
  trace de décrément (`4 → 3 → 2 → 1 → absent`).
* *son déclenchement inflige-t-il ce que le natif inflige ?* — **OUI, à l'unité près** : le DoT
  offline **égale exactement** le DoT natif sur les deux régimes (31 662 et 48 339), le `state.rng`
  offline étant calé sur le MT du runner avant le boundary. C'est un replay-diff, pas un scalaire
  ajusté.

**Note sur la bande, régime CHAOS.** `blackTerminator` porte `LetTheGalaxyBurn`, dont
`LetTheGalaxyBurnEffect$$CreateAdditionalHits` ajoute un coup dès que la cible est sur une tuile à
status-effect — ce que DespoiledGround est justement. Le TOTAL appliqué vaut donc ≈ 2 × la base
(48 339 pour une base d'environ 24 k), **des deux côtés à l'identique**. La bande borne la BASE, pas
le total : le test ne l'asserte que sur le régime `astraBullgryn`, qui ne porte aucun ajout de coups.

**Deux contrôles négatifs** (sans lesquels un port permissif passerait) : le gate
`HasEffect(Self, WarpHail)` (retiré → aucune pose) et le gate `HasTrait(elem, Chaos)` du 2ᵉ volet
(victime Imperial → aucun 1478, LIVE comme OFFLINE).

**Un piège de montage, corrigé et documenté** : appeler `StartTurnOperation.execute(state, joueur)`
directement laisse `state.current_player_id` PÉRIMÉ (c'est `ChangeTurnOperation` qui l'écrit), donc
`IsTurnOf` rend faux et le 1478 n'est jamais posé. Le boundary offline doit être
`EndTurnOperation.execute(state, advance=True)` — mirror complet `EndTurn → ChangeTurn → StartTurn`.

---

## 5. Non-régression

Ciblée (la face DAMAGE et la face TILE-EFFECT sont les seules touchées) :
`test_lot_pose_live.py` (rotation FleshmetalGuns, AnvilShield, MasterAnnihilator,
TerrifyingCrescendo — le registre `ABILITY_TRIGGERS["FleshmetalGuns"]` a gagné une entrée),
`test_tile_effect_dynamics_live.py` (cycle de vie des effets de tuile),
`test_damage_roll_live.py` + `test_runner_attack_live.py` (le chokepoint `_apply_damage_pipeline`),
`test_let_the_galaxy_burn_live.py` et `test_tile_leaf_unit_traits_live.py` (les deux autres
consommateurs de 1476).

Blast radius par construction :
* le vecteur `On(0x10)` n'a **qu'un seul** consommateur porté, dont le `matches` exige
  `ev.actor_id == owner` **et** `HasEffect(owner, WarpHail)` → inerte pour toute autre unité ; le cap
  phase-triggers n'est incrémenté qu'**après** un `matches` vrai, donc pas de consommation parasite ;
* `EFFECT_TRIGGERS[1476]` ne peut firer que sur un état portant déjà 1476 — impossible avant ce
  commit (ni vecteur de pose, ni classe) ;
* `DslContext.current_player_id` et le nœud `IsTurnOf` sont additifs (défaut `None` → `IsTurnOf`
  faux) ; `RandomAmount` est un nœud neuf sans autre appelant.

---

## 6. Ce qui n'est PAS couvert

1. **Le conjoint `hitInfo+0x94` du gate de `On(0x10)`** (§2.3) : non modélisé. Il ne peut que
   RESTREINDRE l'émission native ; aucun régime observé ne l'a exercé.
2. **`OnFireDamageAbility` / `OnToxicDamageAbility` restent appelés impérativement** depuis
   `after_hit_normal_attack` au lieu d'être routés sur le nouveau bus `On(0x10)`. Ils y sont déjà
   portés ET live-validés, et le Toxic consomme un `next_bool` dont l'ordre vs les tirages de dégât
   est calibré là-bas : les re-router déplacerait ce tirage. Hors périmètre, flaggé.
3. **La source de l'effet posé par `OnFireDamageAbility`** : la mesure de §2.4 confirme le résidu
   déjà flaggé (le natif met la TUILE, le port met le caster). Correction à 1 ligne
   (`source_from_target=True`), non faite ici — même surcharge native, mais autre effet et autres
   tests de garde.
4. **`LetTheGalaxyBurn` volet 2** (`LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` →
   `AddEffect(0x5c4)`) : toujours non porté. Ses DEUX prérequis (vecteur + classe d'effet) sont
   désormais levés — c'est devenu un câblage simple, mais c'est un autre artefact natif.
5. **Les `CreateActiveCondition` de 1476 et de 1478** (`Walkable(Self) | AllAliveMachines(Self)` et
   `IsWalkable(Self)`) : non modélisées, l'instance est toujours active. Dégradation PERMISSIVE mais
   bornée — les deux branches sont satisfaites dès qu'une unité peut se tenir sur la tuile, et le DoT
   est de toute façon gaté sur la présence d'un occupant. Le cycle de vie qui compte (expiration)
   passe par `remaining_turns`/`consumed`, pas par ce flag.
6. **Granularité de `On(0x10)`** : le natif émet par `ApplyDamageOperation` (= par COUP), le port une
   fois par GROUPE de dégât résolu — même approximation, même foyer et même justification que
   `damage_taken_triggers` (la pose d'un tile-effect est idempotente).
7. **Le buff 1478 côté PRÉDICTION** : sa contribution (`+15 %` vs Xenos/Imperial) est portée sur le
   canal `create_effect_damage_bonus_for_attack`, mais aucun scénario ne l'a mesurée en DÉGÂT INFLIGÉ
   (le montage ne fait qu'observer sa POSE). Le gate `target_traits is None → None` la rend inerte
   quand la cible est inconnue.
8. **ORDRE des tirages quand PLUSIEURS tuiles despoilées ont un occupant** : le natif itère un
   `Foreach` unique sur le sélecteur global, le port dispatche un `TileEffectTrigger` par tuile —
   l'ordre des `RandomAmount` peut donc différer si ≥ 2 occupants sont concernés au même tick.
   **Même propriété (et même silence) que `FireTileDoT`** ; les deux régimes mesurés n'ont qu'un seul
   occupant despoilé, donc le bit-exact ne prouve rien au-delà de ce cas.
