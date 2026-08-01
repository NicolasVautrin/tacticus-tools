# #432 — l'armure Terminator ne protégeait pas « toujours » : **une attaque par tour**, et le port l'ignorait

## 1. Le fait

`1147 TerminatorArmour_ReduceDmg` (**44 porteurs**) réduisait, côté port, **toute** attaque reçue de
−75 %. Le natif ne la donne qu'à la **première attaque qualifiante de chaque tour** — l'i2 le dit
(`Traits/TerminatorArmour_Description` : « **The first attack each turn** against this unit deals
{[dmgPctReduction]}% Damage »), le décompilé le porte, et la mesure live le chiffre.

Écart mesuré (`probe_432_terminator_armour_cycle`, build `rnca9r7q6c`, `MC1_67`/seed 4321) sur la
**2ᵉ attaque du tour** contre `spaceStormcaller` : natif **15 576**, port d'avant **3 521** —
**−77,4 %**, soit **12 055 points de dégât escamotés par attaque**, à partir de la deuxième de
chaque tour, chez 44 porteurs.

## 2. La RE (décompilé = vérité)

`TerminatorArmour_ReduceDmg_Effect : PlayerTurnEffect : BaseEffect` (`classes.tsv`).

### 2.1 Le ctor fixe la fenêtre et la fréquence

    TerminatorArmour_ReduceDmg_Effect$$.ctor =
        PlayerTurnEffect..ctor(this, turnsEnabled = 2, activationFrequency = 1,
                               sourceAbility = Nullable(AbilityOrEffect(0x476)))

Les trois littéraux sont **lus à l'assembleur** (`mov edx, 0x476` avant `AbilityOrEffect$$op_Implicit`),
et les trois enums sont dans le dump du build :

| enum | valeur |
|---|---|
| `PlayerTurnEffect.TurnsEnabled` | 0=Player, 1=Enemy, **2=Both** |
| `PlayerTurnEffect.ActivationFrequency` | 0=Automatic, **1=PerTurn**, 2=PerRound |
| `TriggeredAbilityType` | **1142 = TerminatorArmour** |

### 2.2 La fenêtre — branche `PerTurn` de `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal`

    On(0x12 = TurnStart_EffectActivation) & IsEnabledTurnType()  -> ActivateEffect(<Sel+0x38>)
    On(0x17 = TurnEnd)                    & IsEnabledTurnType()  -> DeactivateEffect(<Sel+0x38>)

⚠ La branche `PerRound` (celle de `WireweaveNet_CounterAttack`, `case-366-r1b`) est **l'inverse**
(deactivate au turn-start, activate au turn-end) : ne pas transposer l'une sur l'autre.

`PlayerTurnEffect$$IsEnabledTurnType` : `2 -> <DSLTriggers+0x70>` ; `0 -> <DSLTriggers+0x28>` =
`IsTurnOf(Owner)` (construit sur `<DSLSelectors+0x30>` par `DSLTriggers$$InitializeShared`) ;
sinon la négation de ce dernier.

Le 3ᵉ `Triggered()` de la même méthode (`On(0x2e = UnitResurrected) & OwnerIsTarget ->
ActivateEffect`) est gaté par un virtuel booléen (`vtable +0x728`) dont l'implémentation sur la
chaîne `PlayerTurnEffect` est un stub `return 0` — **non bâti**, donc non porté (même constat que
`case-366-r1b` §2).

### 2.3 La consommation — `$$CreateTargetTrigger` / `$$CreateTargetTriggerBehaviour`

    CreateTargetTrigger =
          On(9 = Attack, true)
        & AreEqual( Units(<Sel+0x60 = Target>, true, 3), <Sel+0x30 = Owner> )
        & CurrentAttackDamageProfilesContainOtherThan(
              GetEnumArrayConstant(config@+0x60, 0x52), includeNotApplied = true)
        & AmountIsZero( CurrentShieldAmount(<Sel+0x60>, 3) )
        & ( AmountIsGreaterThanZero( HealthDamageFromEvent() ) | WasBlock() )

    CreateTargetTriggerBehaviour = DeactivateEffect(effect)

Le mapping des slots `DSLSelectors` est **lu**, pas supposé : `DSLTriggers$$get_OwnerIsTarget` =
`AreEqual(<+0x30>, <+0x60>)`, `$$get_OwnerIsActor` = `AreEqual(<+0x30>, <+0x40>)`,
`$$get_OwnerIsCaster` = `AreEqual(<+0x30>, <+0x48>)` ⇒ **+0x30 Owner · +0x38 Effect · +0x40 Actor ·
+0x48 Caster · +0x60 Target**.

### 2.4 Le 4ᵉ `Triggered()` — la re-pose

    On(0x3e = 62 EffectAdded)
      & AreEqual( <Sel+0x90 = TriggeringAbilityOrEffect>, Direct(AbilityOrEffect(this@+0x10)) )
      & AreEqual( <Sel+0x48 = Caster>, OwnerOfEffect(<Sel+0x38>) )
    -> ActivateEffect(<Sel+0x38>)

Le littéral de `Direct(...)` est lu à l'assembleur (`mov edx, [rdi+0x10]` juste avant
`AbilityOrEffect$$op_Implicit`) : `BaseEffect+0x10` est l'id propre de l'effet — son `.ctor` écrit
`+0x14..+0x3c` et **jamais** `+0x10`. **Structurellement inerte** aujourd'hui : le seul poseur de
1147 est `TerminatorArmour_AddEffectAbility` (`GetEffectType = 0x47b`), dont le `CreateTrigger`
hérité d'`AOwnerEffectTriggeredAbility` est `OnOwnerSpecificAbilityInit(this.Id)` et dont le
`CreateBehaviour` pose l'effet **sans durée** — il n'existe aucun chemin de re-pose en bataille.
Porté quand même (1 `Triggered()` natif = 1 classe).

## 3. Le point qui décidait le montage : `On(9)` est **par ATTAQUE**, pas par coup

`IdunBattle.Operations.FinishAttackOperation$$Execute` émet `On(9)` **inconditionnellement, une
seule fois**, à la clôture de l'attaque (`FUN_1800280e0(0x50, .., 9, entities)`), suivi du `On(10)`
gaté par `currentAttack@+0x2c`. La désactivation tombe donc **après le dernier coup** : tous les
coups de la première attaque sont réduits.

⇒ **le régime mono-coup est DÉGÉNÉRÉ** (les deux lectures y coïncident) et **le nombre de coups
n'est pas le discriminant** : le discriminant est *deux attaques dans le même tour*. Le ledger par
coup, lui, tranche « premier COUP » contre « première ATTAQUE ».

**Mesure** (`tauAunShi`, 5 coups, profil `Power`, contre `spaceStormcaller`) :

| régime | total | coups |
|---|---|---|
| 1ʳᵉ attaque du tour (armure armée) | 1 663 | 390, 285, 309, 299, 380 |
| 2ᵉ attaque du tour (armure consommée) | 6 616 | 1426, 1046, 1395, 1529, 1220 |

Bandes **disjointes**, **5/5** coups réduits — « premier coup seulement » prédirait 1/5. Ratio
**3,98** (= 1/0,25, `terminatorArmourDmgReduction = −75`). Idem sur `astraBullgryn` (4/4 coups) et
sur un second couple `C3_01`/seed 777 (1 499 → 6 659).

## 4. Le jumeau `_Visual` (1375) **ne réduit RIEN** — la prémisse « jumeau » est réfutée

    TerminatorArmour_Visual_Effect : TerminatorArmour_ReduceDmg_Effect       (classes.tsv)
    TerminatorArmour_Visual_Effect$$CreateEffectDamageMalusForDefense =
        { zéroe les 0x58 octets du `Nullable<EffectBonus>` de retour ; AUCUN ctor }

C'est un `return null` : la sous-classe **neutralise** la réduction de sa base. 1375 est un pur
marqueur d'affichage (`TerminatorArmour_AddVisualEffectAbility$$GetEffectType = 0x55f`). Côté port
il n'a **aucune** classe dans `EffectFactory` — il était donc déjà inerte, et il ne doit surtout pas
en recevoir une. Il **suit le même cycle** que 1147 (triggers hérités) : mesuré, sa trajectoire
`active` est identique pas à pas, ce qui en fait un témoin gratuit du cycle.

## 5. Le port

`scripts/python/engine/runner/operations/triggers/loki/terminator_armour.py` — **quatre**
`EffectTrigger`, inscrits dans `EFFECT_TRIGGERS[1147]`, qui n'écrivent qu'une chose :
`EffectComponent.IsActive @+0x5c` (`BaseEffect.active`), déjà conjoint de
`EffectsState.active_effects` :

| classe | vecteur | rail | geste |
|---|---|---|---|
| `TerminatorArmourDeactivateOnAttack` | `On(9)` | **TARGETS** (lit le flag) | `DeactivateEffect` |
| `TerminatorArmourActivateOnTurnStart` | `On(0x12)` | ARRAYSET | `ActivateEffect` |
| `TerminatorArmourDeactivateOnTurnEnd` | `On(0x17)` | ARRAYSET | `DeactivateEffect` |
| `TerminatorArmourActivateOnEffectAdded` | `On(0x3e)` | ARRAYSET | `ActivateEffect` |

Deux canaux d'événement neufs sur le vecteur de clôture (`TriggerEvent`) : `health_damage`
(= `HealthDamageFromEvent()`, la part SANTÉ, bouclier déduit — `r["total"]` du port) et `was_block`
(= `WasBlock()`). Threading : `damage.py` (voie NORMALE), `damage_ops/ability.py` et
`damage_ops/normal_like.py` (voie ABILITY).

## 6. Validation

* **Cliquets** — la banque est `scripts/ratchets.ps1` (composition définie **là**, jamais recopiée
  ici) : relevé du **2026-08-01, après rebase sur `43b19959`** — **19/19 verts, mur 112,7 s**.
  `probe_229` a **mordu** en cours de route : il a refusé les 4 classes tant que leur `RAIL` n'était
  pas déclaré, et imposé la lecture du flag `IsActive` sur la seule classe du rail TARGETS (le
  correctif est dans le port, pas dans le probe).
* **Garde** : `tests/engine/test_432_terminator_armour_cycle_live.py` (4 tests) — natif, port,
  contre-épreuve, gate de profil. Rejouée **après rebase**, verte, avec
  `test_damage_roll_live`, `test_runner_attack_live`, `test_overkill_gate_live`.
* **Contre-épreuve** : l'entrée `EFFECT_TRIGGERS[1147]` **retirée** — ce n'est pas une caricature,
  c'est *exactement* l'état d'`origin/master` (les quatre classes n'existaient pas, et les deux
  canaux d'event neufs n'ont aucun autre consommateur) — la 2ᵉ attaque tombe à **3 521** (vs natif
  15 576) et le flag `e.active` **ne tombe plus**. C'est ce second point qui atteste que la mutation
  a **mordu** avant qu'on lise le verdict : sur une contre-épreuve, VERT est le résultat suspect.
* **Généralisation** : second couple (`C3_01`, seed 777) ; bras `psychic` (§7).
* **Bit-exactitude** : le rejeu OFFLINE **enchaîné** des deux attaques du tour 1 (même `State`, même
  flux RNG) rend **1 663 / 15 576** = le natif **à l'unité**, sur les deux couples.

⚠ Le rejeu doit être **enchaîné**. Un rejeu attaque-par-attaque depuis une capture fraîche serait
**tautologique** : `decisionView` par défaut ne publie que les effets ACTIFS, donc l'armure consommée
y est déjà absente et un port sans cycle « aurait raison » sans rien porter.

## 7. Le régime qui SÉPARE les deux lectures — le gate de profil

Un port qui aurait codé « on saute la réduction à partir de la 2ᵉ attaque » passerait tout ce qui
précède. Le bras `psychic` le tue : la 1ʳᵉ attaque du tour est **PSYCHIQUE**
(`terminatorArmourExcludedDmgProfiles = "Psychic,DirectDamage"`), donc elle **ne consomme pas**
l'armure — et la 2ᵉ attaque du même tour est **RÉDUITE**.

Mesuré (`astraPrimarisPsy` puis `tauAunShi`) : psychique **3 539** (armure `active=True` après),
puis Power **1 584** = [285, 309, 299, 380, 311] — la bande RÉDUITE — armure `active=False` après.
Port : **3 539 / 1 584**, à l'unité, avec la même trajectoire de flag.

## 8. Ce qui n'est PAS couvert

* **`<DSLTriggers+0x70>`** (le conjoint de `TurnsEnabled.Both`) est un **singleton non qualifié** :
  même classe et même argument (`0`) que `<+0x40>`, dont `<+0x48>` est la négation logique. Il est
  lu **trivialement vrai**, seule lecture compatible (a) avec le nom de la valeur d'enum (`Both` =
  l'union de `Player` et `Enemy`, dont les deux autres branches sont exactement le trigger et sa
  négation), (b) avec `DSLTriggers$$InitializeShared`, qui l'emploie comme conjoint de
  `On(0x21) & OwnerIsActor` et de `On(0x41) & OwnerIsActor` — qu'un conjoint FAUX rendrait morts —
  et (c) avec l'i2. **Confronté live** par le ré-armement observé à chaque boundary de tour.
* **`includeNotApplied = true`** (2ᵉ argument de `CurrentAttackDamageProfilesContainOtherThan`) n'est
  pas modélisé : le port ne connaît que le SET des profils de l'attaque, sans distinguer les coups
  appliqués des coups annulés.
* **Le vecteur `On(9)` du port ne couvre pas les attaques déclenchées par un TRIGGER** — dont le tir
  d'overwatch, qui appelle directement `AttackDamageOperation.execute`. Divergence **structurelle
  préexistante** (documentée dans `dispatch/attack.py::attack_damage_attack_triggers`), non élargie
  ici : un tir d'overwatch sur un porteur d'armure la consomme côté natif, pas côté port.
* **Le 3ᵉ `Triggered()` de `PlayerTurnEffect`** (`On(0x2e = UnitResurrected)`) : gaté par un stub
  `return 0`, donc non bâti — non porté.
* **La branche `WasBlock()`** de la disjonction est portée mais **non confrontée** : le montage force
  `--block-target 0,0` pour retirer le bruit de block. Un coup entièrement bloqué (0 PV perdu)
  consomme l'armure côté natif ; côté port le canal `was_block` est câblé sur le même `did_block` que
  `On(0x3c)`, mais aucune mesure ne l'a exercé.
* **Le régime « bouclier »** (`AmountIsZero(CurrentShieldAmount)`) est porté et non confronté : il
  faudrait faire poser un bouclier sur le porteur (`thousSorcerer` dans son équipe, cf. `case-342`).
  Le sens du gate ne peut que RESTREINDRE la consommation, jamais l'élargir.

## 9. Pièges de montage rencontrés (à ne pas re-payer)

* **Le tour se clôt SEUL** dès que toutes mes unités ont agi (le natif enchaîne
  `EndTurn`/`ChangeTurn`/`StartTurn`). La lecture du flag prise *après la dernière attaque du tour*
  porte donc déjà le `On(0x12)` de ré-armement du tour suivant — lue naïvement, elle dit « l'armure
  n'a pas été consommée ». Parade : une unité **spectatrice** qui n'attaque jamais, pour que
  l'attaque mesurée ne soit pas la dernière.
* **`applyAction {kind:"endturn"}` existe** (la doc RPC ne liste que `move|ability|finish`) et il
  clôt le tour **courant** : après l'auto-clôture ci-dessus, **un seul** `endturn` ramène la main.
* Sur `MC1_67`/seed 4321, la tuile du porteur n'a que **2 voisins** : ne placer sur l'anneau que les
  unités qui doivent frapper, laisser les spectatrices à leur spawn.
