# case-576 — `1175 BloodChalice` : la catégorie annoncée était `HEAL`, le volet principal n'est pas un soin

> **Build** `rnca9r7q6c`. Porteur **unique** : `bloodSanguinary` (« Sanguinary Priest », Blood Angels).
> Décompilé = vérité ; live = confirmation (5 étages, tous bit-exacts).

---

## 1. L'état d'avant, et ce que l'audit annonçait

`1175 BloodChalice` était un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc
`AbilityHandler.visit_ActiveAbilityMessage` rendait `ported: False` — 0 PV touché, 0 effet, **aucune
erreur**. Sa face DÉCISION, elle, était portée depuis #82
(`playbook/bespoke.py::BloodChalicePlaybook`, override total d'`EvaluateInternal`) : le moteur
**choisissait** le cast et ne **faisait** rien.

`docs/rl/combat-ability-coverage.md` la classait `HEAL | 1` — une catégorie, une mécanique. Les deux
sont faux, et pour deux raisons différentes.

---

## 2. La lecture : `ExecuteBehaviour` porte TROIS mécaniques

`IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$ExecuteBehaviour` — mirror :

```
b1 = ChangeStat( GetTargets(), Position(HEALTH=5, 0, 0), mode **0** = SetAbsolute,
                 PercentageOf( StatAmount(It@DSLSelectors+0x68, HEALTH=5, MAXIMUM=2),
                               ConfigConst(0x4f healthPct), roundingRule **2** = Floor ) )
b2 = AddEffect( 0x558 = BloodChalice_HealOnAttack, AbilityStateReference,
                source = Owner@DSLSelectors+0x30, targets = GetTargets(), TurnsFromRounds(1) )
b3 = AddStaticStatModifierEffect( GetTargets(), 0x559 = BloodChalice_ExtraPiercing,
                                  0x15 = StatType.ExtraPierceMelee,
                                  ConfigVar(0x3f extraPierceRatio), TurnsFromRounds(1),
                                  isHidden = false )
return AActiveAbility.Execute(this, op_Addition(op_Addition(b1, b2), b3))
```

`Execute` **plain** (pas d'`ExecuteAtomic`, aucun `Group`). Les trois volets sont déterministes.

`$$GetTargets` — **trois** étages, dont **deux muets dans le tooltip** :

```
adj  = AdjacentFriends(Caster@DSLSelectors+0x48, unique: true, selectionType 3)
mech = MechanicalUnits(adj, selectionType 3)
return UnitsWithoutTrait(adj op_Subtraction mech, 0x19 = UnitTrait.Immune, 3)
```

⚠ La surcharge d'`AdjacentFriends` est tranchée **par ses xrefs entrantes** : le build en porte deux,
et `GetTargets` appelle la 4-args **UNIT-ancrée**, pas la TILE-ancrée qu'appelle
`...RitesOfRestorationAbility$$GetHealTargets`.

i2 : « All adjacent friendly non-mechanical units are set to `{healthPct}%` Health. Until the start
of their next turn, affected units gain `+{extraPierceRatio}%` pierce ratio with melee attacks and
heal for `{hpToHeal}` Health if they perform a melee attack. » — appariement **un à un** avec les
trois nœuds. Le filtre `Immune`, lui, n'apparaît nulle part dans l'i2.

---

## 3. Le volet 1 n'est PAS un soin — et c'est ce qui rend le régime témoin obligatoire

`IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute`, case **0** (relue pour cette tranche) :

```
cur = UnitExtensions.GetStat(unit, stat, 0);
statModifiers.Add(new StatModifier(stat, **amount**, ...));   // la valeur FINALE, absolue
this+0x18 += amount - cur;                                    // le delta RAPPORTÉ
```

Le modifier impose `GetStat(stat) == amount`. Health étant une stat **fill-up**
(`HealthComponent`, pas un `StatComponent`), le SetAbsolute s'y lit `hc.hp = amount`.

**Conséquence observable, contre-intuitive pour une ability classée « HEAL »** : un allié adjacent
**au-dessus** de `healthPct %` est **ramené vers le bas**. Le gate `EntityCanBeHealed` n'intervient
pas — ce n'est pas un `Heal`.

C'est aussi le seul régime où les deux lectures divergent : sur des cibles blessées, « SET à 50 % »
et « soin » produisent le même verdict. Le montage exige donc une cible **pleine** (étage E2).

**Mesuré** : `bloodDeathCompany` à `20001/20001` → **`12049`**. Elle descend.

---

## 4. L'étage voisin qui a failli faire fitter un scalaire

Le live rendait `hp_apres = floor(hp_max × healthPct/100) + **2049**`. Le `2049` n'est pas du 1175.

Le porteur possède le passif **`SanguinaryPriest`** (`TriggeredAbilityType` **1296**), **non porté**.
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility$$CreateBehaviour` :

```
Heal( Owner@DSLSelectors+0x30,
      AdjacentFriends(Owner, unique, 3) op_Subtraction MechanicalUnits(.),
      RandomAmount( GetVariableForLevel(0x20 hpToHeal), GetVariableForLevel(0x47 maxHpToHeal) ),
      HealBehaviourOptions.**ForRegenerate** )
```

— un soin **aléatoire** sur **exactement le même ensemble** que `BloodChalice.GetTargets()`.
Plage dérivée du gameconfig au niveau 50, multiplier 180 : `[1496, 2194]`. `2049` y tombe.

**Un critère sur la valeur absolue aurait donc soit rougi à tort, soit été « ajusté » de 2049** — un
fit de scalaire. La mesure **isole l'étage** à la place : `hp_max` **varie** sur trois runners, et
c'est l'**écart** au SET porté qui doit rester constant. Un `healthPct` faux, une base fausse
(courant au lieu de MAXIMUM) ou un arrondi faux le feraient varier avec `hp_max`.

| `hp_max` | `hp_après` live | SET porté `floor(max×50/100)` | écart |
|---|---|---|---|
| 20001 | 12049 | 10000 | **2049** |
| 30001 | 17049 | 15000 | **2049** |
| 20003 | 12050 | 10001 | **2049** |

⚠ **`roundingRule = 2` = Floor, et le départage exige `hp_max ≡ 3 (mod 4)`.** À `healthPct = 50`,
`hp_max/2` ne tombe sur un demi que si `hp_max` est impair ; et le demi n'a un entier pair
*au-dessus* que si `hp_max ≡ 3 (mod 4)`. Sur `20001` (≡ 1), Floor et half-to-even rendent **la même
valeur** — un premier montage y a rendu « non discriminant », ce que l'étage **dit** au lieu de
rendre un faux vert. Sur `20003` : `d_live = 1 = d_floor`, `d_half-to-even = 2` **réfuté**.

⚠ **`bloodIntercessor` a été écarté du montage APRÈS mesure** : il porte `TeleportStrike`, donc il
arrive avec `TeleportStrike_TeleportingIn` (1035) et `unitFlags [17]` — il n'est pas encore posé,
aucune ability ne le voit. Le montage rendait « 1 seule cible » et **se lisait comme un bug de
`GetTargets`**. Ce n'en était pas un.

---

## 5. Les deux effets — et le résidu que le live a fondé

**1368 `BloodChalice_HealOnAttack`** porte **deux** volets, tous deux lus :

* `$$CreatePiercingBonusForAttack` = `ForPiercing(get_OwnerIsCaster & IsMeleeAttack,
  ConfigVar(0x3f extraPierceRatio))`. ⚠ **Face INVERSE de son jumeau structurel**
  `Supercharge_ExtraPiercingEffect` (1208), qui gate sur `DamageProfileIs(Plasma) &
  get_OwnerIsTarget` : recopier le voisin aurait inversé la face sans rien casser d'autre. Aucun
  gate de `damageProfile` ici — le seul discriminant est mêlée/distance.
* `$$CreateTargetTrigger` = `On(0x9 Attack, 1) & get_OwnerIsCaster & IsMeleeAttack` →
  `$$CreateTargetTriggerBehaviour` = `Heal(EffectSource, Owner@+0x30, ConfigVar(0x20 hpToHeal),
  HealBehaviourOptions.**ForHeal**)`. Fabrique **lue** : `ForHeal` = `(scope 0, removeEffects 1)`,
  pas `ForRegenerate` `(1, 0)` — que le passif du **même** porteur, lui, utilise bien. Les deux
  entités sont **distinctes** : le soigneur est la SOURCE de l'effet, la cible est le PORTEUR. Le
  port passe par `HealUnitOperation.execute`, qui porte le gate `AttackQuery$$EntityCanBeHealed`
  **et** `PredictHeal` — jamais une mutation directe (c'est la panne trouvée deux fois, #520 puis
  #564).

**1369 `BloodChalice_ExtraPiercing`** est un `AStatModifierEffect` dont la seule surcharge est
`$$CreateActiveCondition = IsCharging(Owner@+0x30, Target@+0x60)`.

**Mesure décisive** : après le cast, `decisionView` publie 1368 sur la cible et **rien pour 1369**.
`readEffectsByUnit` droppe les entrées `IsActive == 0` : l'effet est **posé et inerte** hors charge.
La condition n'existe **que** dans le décompilé — le tooltip ne l'annonce pas.

⇒ le port **sur-accorde** : il applique le `StatModifier` une fois à la pose et ne le reverse qu'au
retrait. Biais **unilatéral**, silencieux. → résidu **#576-r1**, dont les deux volets sont
indissociables : threader l'`ActiveTarget` jusqu'à `is_active`, **et** brancher le revert
conditionnel de `RefreshEffectsOperation$$RefreshEffect` — sans le second, poser `is_active` ne
changerait rien à la stat.

---

## 6. Le registre, et ce que le masque dit de la catégorie

`...BloodChaliceAbility$$.ctor` — forme **flags directs** (le 5ᵉ argument atterrit tel quel à
`options+0x28`) ; le `statics+0xb8` copié alimente le **range**, pas les règles :

```
TargetingOptions..ctor(&opts, 1, &<TargetingRange statics+0x30>, 1, **0xc02**, 0, 0)
AActiveAbility..ctor(this, &opts, **2**)
```

`0xc02` = `TargetMatchesDynamicRule | TargetIsFriendly | AddCasterIfAtLeastOneTarget`.

⚠ **Pas de `TargetIsHealable` (0x0100)** — contraste avec 1002 et 1039, qui sont de vrais soins. Le
masque lui-même dit que ce n'est pas un heal ; le gate non-mécanique passe par la **règle dynamique**
seule (`GetDynamicInvalidTargetReason`, déjà portée par #287-r5, re-lue et concordante).

`AbilityAttackType` = **2 = `Others`**, transcrit du 3ᵉ argument.

Les deux entrées migrent hors de `TARGETING_OPTIONS_UNPORTED` et `DYNAMIC_TARGET_RULE_UNPORTED`
(contrat de disjonction).

---

## 7. Ce qui n'est PAS couvert

* **`UnitsWithoutTrait(0x19 Immune)`** — **0** des 99 unités du pool porte ce trait, donc aucun
  montage ne peut le faire mordre. Le terme est porté parce que le décompilé l'écrit ; il est gardé
  **structurellement** (`test_576…::test_le_selecteur_de_cibles_porte_ses_TROIS_etages`), jamais en
  live.
* **Le trigger de soin sur attaque mêlée (1368)** est porté et gardé offline (registre, `event_id`,
  passage par l'Operation qui porte le gate, tri-état `ranged`) mais **non confronté live** : il
  exige de faire attaquer un bénéficiaire en mêlée dans le tour suivant le cast.
* **Le régime « les deux canaux de perçage contribuent ensemble »** (= en charge) n'est mesuré par
  rien — c'est le second volet de #576-r1.
* **`SanguinaryPriest` (1296)** reste **non porté**. Son absence est sans effet sur cette tranche
  (elle est mesurée et écartée par construction), mais tout port futur du Sanguinary Priest devra
  la traiter.
