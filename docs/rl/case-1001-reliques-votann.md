# #1001 — les deux reliques LEAGUES OF VOTANN

`BladeOfTheAncestors` (`TriggeredAbilityType` 0x5d3 = **1491**, `votanUthar` « Ûthar ») et
`VolummsMasterArtifice` (0x5d0 = **1488**, `votanIronmaster` « Vynn »). Deux items du gameconfig
(`R_Crit_BladeOfTheAncestors`, `R_Crit_VolummsMasterArtifice`), un `allowedUnits` d'UNE unité
chacun, les deux porteurs HORS du pool rank 17 — donc **un seul montage pour les deux** :
`catalog_inject.augment` les injecte ensemble, `equip_relic` équipe les deux reliques.

Build de référence : `rnca9r7q6c`. Décompilé = vérité, live = confirmation.

---

## 1. Le canal, lu ability par ability

Les deux relèvent de **`RELIC_ABILITY_TRIGGERS`** (`CreateTrigger` + `CreateBehaviour` présents et
propres). Ce n'est ni `ABILITY_INIT_OWNER_EFFECTS` ni l'attaque normale substituée.

⚠ `BladeOfTheAncestorsAbility` et `BladeOfTheAncestors_RemoveEffectAbility` vivent sous
`IdunBattleLogic.Entities.Abilities.**Active**.Loki` — **le namespace ment** : leur base, LUE dans
`frida/classes.tsv`, est `IdunBattle.Entities.Abilities.BaseTriggeredAbility`, et l'id est un
`TriggeredAbilityType`. Même piège, même namespace que `ActOfFaith`.

## 2. `BladeOfTheAncestors` — RE

### `...BladeOfTheAncestorsAbility$$CreateTrigger`

```
  ( On(0 = UnitDeath, ownerNeedsToBeAlive = 1)
    & AreFriends( Targets@DSLSelectors+0x60, Owner@+0x30, 0, 0 )
    & HasTrait(   Targets@+0x60, 0x10 = UnitTrait.Hero ) )
| ( On(0 = UnitDeath, ownerNeedsToBeAlive = 1)
    & AreFriends( Actor@DSLSelectors+0x40, Owner@+0x30, 0, 0 )
    & HasTrait(   Actor@+0x40, 0x10 = Hero )
    & IsNormalUnit( Targets@+0x60 ) )
```

Branche 1 = « a friendly character **dies** » ; branche 2 = « a friendly character **kills an enemy
unit** ». `IsNormalUnit` est `IdunBattle.Entities.UnitExtensions$$IsNormalUnit`, lu :
`NOT HasTrait(0xd = Object) AND NOT HasTrait(0x1b = Steppable)` — ce n'est **pas** un no-op offline
(les mines `Steppable` et les power-ups sont exactement ce qu'il exclut).

### `...BladeOfTheAncestorsAbility$$CreateBehaviour(abilityState, triggerType)`

```
if (triggerType == 0x20 = Custom) return Nothing();
return AddEffect( 0x5d1 = 1489 BladeOfTheAncestors_Effect,
                  BaseTriggeredAbility$$get_AbilityStateReference(this),
                  targets = Owner@+0x30, turns = null )      // surcharge 4 args : source = cible
```

### `...BladeOfTheAncestors_RemoveEffectAbility`

```
CreateTrigger   = On(9 = Attack, 1) & get_OwnerIsCaster & WasCrit
                & HasEffect( Owner@+0x30, 0x5d1, onlyActive = false, targetType = 6 = Both )
CreateBehaviour = triggerType != Custom -> TriggerAbilityDelayed( Owner@+0x30, 0x5d3, 3 )
                  triggerType == Custom -> RemoveEffect( Owner@+0x30, Nullable(0x5d1) )
```

### `IdunBattle.Entities.Effects.Loki.BladeOfTheAncestorsBuffEffect` (EffectType 1489)

Base `BaseEffect` (LUE), pas `AStatModifierEffect` : la classe construit elle-même ses `ChangeStat`.

```
.ctor               = BaseEffect(hasAutomaticActivation = 1, Nullable(0),
                                 Nullable(AbilityOrEffect(0x5d3)))     // `mov edx,0x5d3`, relu
ApplyModification   = ChangeStat(Entity(target), Stat(9  = CritChance, 5 = Modification), 4,
                                 Direct(GetVariableForLevel(0x41 = extraCritChance)), Entity(effect), 3)
                    ; ChangeStat(Entity(target), Stat(10 = CritDamage,  5), 4,
                                 Get(   GetVariableForLevel(0x42 = extraCritDmg)),    Entity(effect), 3)
RevertInternal      = les MÊMES deux, `StatPart` 6 = ResetModification, <DSLFormulas+0x18> = Direct(0)
UpdateInternal      = ApplyModification NU
RefreshValueInternal= <slot 0x578> puis ApplyModification × GetTimesApplied(effect)
```

⇒ l'empilement est **additif** (`stacks_stat_mod_on_add = True`, patron `ActOfFaithBuffEffect`).

⚠ **Ce n'est PAS `ActOfFaith`, et l'écart est numérique.** `ActOfFaithBuffEffect` pose
`Ceiling(GetStat(CritDamage, part 3 = Initial) × actOfFaithExtraCritDmgPct%)`, un **pourcentage**.
Ici les deux montants sont des **variables de niveau plates** (`extraCritChance[10] = 10`,
`extraCritDmg[10] = 877`), ce que l'i2 dit mot pour mot. Recopier le voisin de forme aurait écrit un
pourcentage là où le natif lit une constante de config.

### Le fait porteur : **le reset est DIFFÉRÉ**

Le crit n'efface pas le buff sur place — il **enfile** un re-déclenchement de 1491, que
`InputMessageProcessor$$ProcessPendingTriggeredAbilities` draine **après la clôture complète du
message top-level** (#406). Au drain, le natif rappelle le slot 4 de chaque classe de 1491 avec
`triggerType = 0x20` : `BladeOfTheAncestorsAbility` rend `Nothing()`, `_RemoveEffectAbility` retire
l'effet. Conséquence observable : les coups **suivants** de la salve qui a crité bénéficient encore
du buff.

## 3. `VolummsMasterArtifice` — RE

```
CreateTrigger    = On( 0x30 = 48 UnitRepaired, ownerNeedsToBeAlive = 1 )
                 & ( AreEqual( DSLSelectors$$Parent(Caster@+0x48, root = false), Owner@+0x30 )
                   | get_OwnerIsCaster )

GetPersistentData= GetPersistentData( AbilityOrEffect(0x5d0), Owner@+0x30, Get(<literal>) )

CreateBehaviour  = cond = AmountIsEqualOrGreater( GetPersistentData(...),
                                                  ConfigVar(0x9b = 155 nrOfRepairs) )
                   THEN =   Heal( Owner@+0x30, Owner@+0x30, ConfigVar(0x20 = 32 hpToHeal),
                                  HealBehaviourOptions$$ForHeal )
                          & ResetActiveAbility( Owner@+0x30, allowUseless = true )
                          & SetPersistentData( AbilityOrEffect(0x5d0), Owner@+0x30, Get(<literal>),
                                               <DSLFormulas+0x18> = Direct(0) )
                   return   AddPersistentData( ..., <DSLFormulas+0x20> = Direct(1) )
                          & If( cond, THEN, null )
```

**L'ORDRE EST LU, ET IL EST L'INVERSE DE `DaemonfleshPlate`.** Le dernier `op_BitwiseAnd` est
`op_BitwiseAnd(AddPersistentData, If(...))` : l'increment est à **gauche**, donc il s'exécute avant
que le `If` ne relise le compteur. Le seuil est `compteur >= nrOfRepairs` sur le compteur **déjà
incrémenté** — le soin tombe à la N-ième réparation, `N = nrOfRepairs`. `DaemonfleshPlate`, lui,
teste AVANT d'incrémenter et compare à `nrOfAttacks - 1`. Recopier le voisin de forme décalerait le
déclenchement d'une réparation.

Le reset du compteur est un `SetPersistentData(..., Direct(0))`, **pas** un `ClearPersistentData` :
le cycle repart de zéro et **recommence** (mesuré live : trois soins dans une même partie quand les
E-COGs réparent aussi).

Le vecteur `On(0x30 = UnitRepaired)` existe côté port depuis #964-r1 (`dispatch/repair.py`) — donc
l'inscription n'est pas *registered-but-dead*. `Parent` couvre les E-COGs que le passif de kit
`EcogSupport` (1487) du **même porteur** invoque.

## 4. Ce que la mesure LIVE a rendu

`probe_1001_votann_relics.py`, board `MC1_67`, seed 777, reliques équipées au **niveau 3** (le seul
qui sépare le palier demandé du palier CLAMPÉ que rendrait une lecture du niveau des passifs).

| mesure | natif | port | contre-épreuve `sans rail` | contre-épreuve `niveau PASSIF` |
|---|---|---|---|---|
| Blade — pose (`critChance`, `critDamage`) | +8, +654 | +8, +654 | 0, 0 | +10, +877 |
| Blade — reset après crit (`critDamage`) | −654, retour base | −654, retour base, 0 pile | — | — |
| Volumm — rang du soin | 8ᵉ réparation | 8ᵉ | jamais | 7ᵉ |
| Volumm — montant | 6509 | 6509 | — | 8729 |

`extraCritDmg[3] = 654` / `[10] = 877` ; `nrOfRepairs[3] = 8` / `[10] = 7` ; `hpToHeal[3] = 6509` /
`[10] = 8729`. Les deux contre-épreuves rougissent, donc le vert nominal n'est pas un accident.

Le reset du port passe bien par la **file** (`queued: True, dispatched: True`) puis le **drain**
(`removed: 1`) — pas par un retrait immédiat.

**Le montage du volet `volumm` RETIRE `EcogSupport` des passifs de Vynn** (greffe déclarée). Sans ce
retrait, chaque réparation fait apparaître un E-COG, et les E-COGs réparent tout seuls pendant le
tour de leur équipe : le compteur monte de plusieurs crans par tour, par des événements que rien
n'horodate, et le **rang** du franchissement devient incomptable. Mesure du régime avec E-COGs :
trois soins de 6509 en huit actions, rang non attribuable.

## 5. Résidus nommés

* **`#1001-r1` — la lecture d'`ActOfFaith_RemoveEffectAbility` est contredite par ce corps-ci.**
  `engine/runner/operations/triggers/loki/act_of_faith.py` écarte la branche `!= 0x20` de son
  `CreateBehaviour` en la disant « cross-instantiation gshared », et porte `RemoveEffect` sur la
  branche `== 0x20` comme si c'était le chemin nominal. Or `BladeOfTheAncestors_RemoveEffectAbility`
  a **exactement la même fourche**, son corps n'est **pas** gshared, et la lecture y est sans
  ambiguïté : `!= Custom` → `TriggerAbilityDelayed`, `== Custom` → `RemoveEffect`. Le port
  d'`ActOfFaith` retire donc probablement ses stacks **un cran trop tôt** (au milieu de la salve au
  lieu qu'à sa fin) — non re-mesuré ici, hors périmètre.
* **`AreFriends(a, b, comparisonType = 0, anyEntity = 0)`** — les deux derniers arguments ne sont
  pas modélisés (collapse standard du dépôt : comparaison de `team`).
* **la `dataKey`** de Volumm : `DSLFormulas$$Get(<littéral de chaîne>)`, non résoluble
  statiquement. Seule son **unicité** est load-bearing — le sac est indexé par
  `(GetPersistentDataId(AbilityOrEffect(1488)), key)`.
* **`ResetActiveAbility` non confronté live** : dans le montage, l'active de Vynn n'a jamais été
  consommée, donc le re-armement n'a aucun observable. Le port l'exécute (`ResetActiveAbilityOperation`,
  gate `EntityCanHaveActiveAbilityReset`).
* **`unitSelectionType = 3`** de `TriggerAbilityDelayed` et **`isHidden`** : tracés, jamais lus.

## 6. Effet de bord mesuré : le seuil `borne < 1000` de #468 a EXPIRÉ

`tests/test_468_collision_numeros_offline.py::test_sur_le_depot_REEL_le_numero_suggere_n_apparait_NULLE_PART`
portait `assert borne < 1000, "la borne a absorbé un identifiant qui n'est pas une tâche"`. Prémisse :
aucun numéro de **tâche** n'atteint 1000, donc une borne ≥ 1000 ne peut venir que d'une case-doc
nommée d'après un **id d'ability** (`case-1014-*`, `case-1203-*`, `case-1547-*`).

Cette prémisse est tombée : `probe_468 --suggere` a rendu **#1001** (borne 996, 997..1000 déjà pris).
Le premier agent qui écrit une case-doc `case-1001-*` rend donc `master` **ROUGE** — et quatre autres
tranches de reliques allouent au même moment.

Réparation faite ici : le seuil magique est remplacé par l'**invariant** qu'il approximait — la borne
doit être **DÉFINIE dans `backlog.md`** (1ʳᵉ cellule d'une ligne, racine ou résidu), pas seulement
portée par une case-doc. `#1001` passe (ligne `#1001-r1`) ; les trois contaminants ne passeraient pas,
et un second bras **assertionne son propre non-vide** pour que le test ne devienne pas un vert qui
ment le jour où ces case-docs disparaissent. Un seuil plus haut n'aurait fait que reporter la même
péremption.

## 7. Où ça vit

| | |
|---|---|
| triggers | `engine/runner/operations/triggers/loki/blade_of_the_ancestors.py`, `.../volumms_master_artifice.py` |
| effet | `engine/entities/effects/loki/votann.py::BladeOfTheAncestorsBuffEffect` |
| registres | `RELIC_ABILITY_TRIGGERS` + `CUSTOM_TRIGGERED_ABILITIES[1491]` (`dispatch/registry.py`), `EFFECT_CLASSES["BladeOfTheAncestors_Effect"]` (`effects/factory.py`) |
| probe | `scripts/python/probe_1001_votann_relics.py` (`--volet blade|reset|volumm`) |
| gardes | `tests/engine/test_1001_votann_relics_offline.py` (22), `tests/engine/runner/test_1001_votann_relics_live.py` (9) |
