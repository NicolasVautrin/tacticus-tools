# #1008-r2 — `IgnoreArmor` n'est pas un slot d'interface : il est APPELÉ DEPUIS le slot `0x1a`

Tranche du 2026-08-15, build **`t6dpr4k06g`**, RE pure (décompilé ghidra). Le résidu affirmait que
la magnitude `armorIgnored` de `1583 Helspear_IgnoreArmor` **n'atteint pas** le calcul de dégât,
faute de lecteur natif côté DÉFENSEUR. **Prémisse RÉFUTÉE** : le lecteur existe, la chaîne est
complète, et elle est strictement symétrique entre attaquant et défenseur.

| point | verdict |
|---|---|
| « aucun des trois slots défenseur n'est `IgnoreArmor` » | **vrai, mais ne conclut pas** — le lecteur est *dans* le `0x1a` |
| « le lecteur natif reste à localiser » | **RÉFUTÉ** — `BaseEffect$$DamageMalusForDefense` appelle `this.IgnoreArmor()` |
| « l'`EffectBonus` condition-seule est un no-op » | **RÉFUTÉ** — c'est le PORTEUR DE LA GATE |
| point d'ancrage suggéré (`GetBaseDamageWithFixedPiercedArmor`) | **juste** — c'est bien là que `ignoreArmor` est consommé |
| `BLOCAGE: etage` | **tombe** |

---

## 1. La chaîne complète

```
<Effect>$$Create<Face>                        -> Nullable<EffectBonus> : porte la CONDITION SEULE
<Effect>$$IgnoreArmor        (vtable +0x718)  -> IAmountFormula        : porte la MAGNITUDE
        |
BaseEffect$$DamageBonusForAttack   (slot 22)  ]  combinent : SI le trigger de l'EffectBonus est vrai,
BaseEffect$$DamageMalusForDefense  (slot 26)  ]  evaluent IgnoreArmor() -> DamageBonus+0x38
        |
DamageCalculations$$CalculateAttackerModifiersForPrediction  (slots 0x16 / 0x17 / 0x18)
DamageCalculations$$CalculateDefenderModifiersForPrediction  (slots 0x1a / 0x1b / 0x19)
        |  accumulent DamageBonus+0x38  ->  DamageModifiers+0x28   (les DEUX faces)
        |  accumulent le slot piercing  ->  DamageModifiers+0x20
        |
DamagePrediction$$CalculateBaseDamageWithAllModifiers
        ignoreArmor = Fix64.op_Addition( attackModifiers.@0x28 , defenseModifiers.@0x28 )
        |
DamagePrediction$$GetBaseDamageWithFixedPiercedArmor
        armor_eff = Math.Max( defender.GetStat(0x10 = Armor) - (int)ignoreArmor , 0 )
```

`DamagePrediction$$CalculateBaseDamageWithAllModifiers` est l'appelant **unique en CODE** de
`GetBaseDamageWithFixedPiercedArmor` ; Ghidra y nomme lui-même `additionalPiercing`,
`defenderPiercing` et le local sommé qui devient l'argument `ignoreArmor`.

## 2. Le tableau des slots (`metadata/interface_slots.tsv`, re-dérivés PAR NOM)

`IEffect` porte **47** slots. **Aucun** ne se nomme `IgnoreArmor` / `ArmorPenetration` — c'est
pourquoi la fiche ne l'a pas trouvé. Les ordinaux sont **inchangés** depuis `rnca9r7q6c`.

| face | damage-bonus | capped | piercing |
|---|---|---|---|
| ATTAQUANT | `0x16`=22 `DamageBonusForAttack` | `0x17`=23 `CappedDamageBonusForAttack` | `0x18`=24 `PiercingBonusForAttack` |
| DÉFENSEUR | `0x1a`=26 `DamageMalusForDefense` | `0x1b`=27 `CappedDamageMalusForDefense` | `0x19`=25 `PiercingMalusForDefense` |

Types de retour (`frida/methods.tsv`) : les slots 22/26 rendent `Nullable<Core.Services.DamageBonus>`
(**pas** `Nullable<EffectBonus>`, comme l'écrivait la fiche — c'est la structure **ÉVALUÉE**), les
slots 24/25 rendent `Nullable<Core.Services.PiercingBonus>`.

Tailles **déboxées** (`frida/classes.tsv` donne la taille BOXÉE, retrancher 0x10) : `EffectBonus`
0x50 · `DamageBonus` **0x58** · `PiercingBonus` **4** · `DamageModifiers` **0x40**.

## 3. `+0x718` = `IgnoreArmor` — quatre sources indépendantes

`(0x718 - 0x138) / 0x10` = **slot 94** de la vtable de classe (la vtable IL2CPP commence à `+0x138`,
entrées de `0x10` — vérifié dans le décompilé de `CalculateDefenderModifiersForPrediction` lui-même).

1. **Signature unique compatible** — `frida/methods.tsv` :
   `IdunBattle.Entities.Effects.Loki.WayOfTheShortBladeEffect.IgnoreArmor -> IdunBattle.DSL.IAmountFormula`,
   **0 paramètre**. C'est la seule méthode d'effet à cette signature.
2. **Corps lu** — `WayOfTheShortBladeEffect$$IgnoreArmor` =
   `DSLFormulas.ConfigVar(0x40, BaseEffect.GetAbilityState(this), <cfg>@this+0x60)`, et
   `frida/enums.tsv` donne `IdunBattle.Configuration.AbilityVariableType.64 = armorIgnored`.
3. **Le port le nommait déjà** — `engine/runner/operations/triggers/revive_effect.py` écrit
   `+0x718 IgnoreArmor`, et que le corps de BASE est `33 c0 c3` (`xor eax,eax ; ret` = `null`).
   C'est pourquoi `BaseEffect.IgnoreArmor` est **dédupliqué** et n'apparaît nulle part sous son nom
   propre : cas d'école de « l'ABSENCE d'une méthode dans les tables ne prouve RIEN ».
4. **Comptage croisé 5/5** — le corps porte **5 xrefs DATA** (5 slots de vtable), et le gameconfig
   porte **exactement 5** abilities avec une variable `armorIgnored`. Aucune n'est en trop, aucune
   ne manque.

## 4. Le patron des 5 porteurs — CONDITION dans `Create*`, MAGNITUDE dans `IgnoreArmor()`

| effet | `EffectType` | face | trigger de l'`EffectBonus` (lu au décompilé) |
|---|---|---|---|
| `PowerTrip_IgnoreArmorEffect` | 1361 | ATK (22) | `IsNormalAttack & get_OwnerIsCaster & !get_OwnerIsTarget` |
| **`Helspear_IgnoreArmorEffect`** | **1583** | **DEF (26)** | `get_OwnerIsTarget & IsUnit(Caster)` |
| **`StrikeFromTheShadowsEffect`** | **1549** | **DEF (26)** | `IsRangedAttack & get_OwnerIsTarget` |
| `KanOpenerEffect` | 1102 | ATK (22) | non lu |
| `WayOfTheShortBladeEffect` | 1499 | ATK (22) | non lu (propriétaire du corps `IgnoreArmor`) |

Enums qualifiés — `1583` est un **`EffectType`** (l'homonyme `TriggeredAbilityType` est
`1558 = Helspear`) ; `StrikeFromTheShadows` vaut `ActiveAbilityType 1225` **et** `EffectType 1549` ;
`WayOfTheShortBlade` vaut `TriggeredAbilityType 1500` alors que son EFFET est `EffectType 1499`
(`EffectType 1500` est `WayOfTheShortBlade_AdditionalAttackMarker`, une AUTRE classe). Collisions
d'ordinaux entre enums : ne jamais attribuer par l'ordinal seul.

### ⚠ Un `EffectBonus` « condition-seule » N'EST PAS un no-op — c'est le contresens de la fiche

Les trois `Create*` lus rendent un `Nullable<EffectBonus>` dont **toutes les formules sont nulles**
et dont seul le champ trigger (`EffectBonus+0x00`) est renseigné. La fiche en concluait « ce n'est
donc PAS par ce slot que passe la pénétration ». **C'est l'inverse** : le design SÉPARE la condition
(portée par l'`EffectBonus`) et la magnitude (portée par `IgnoreArmor()`), et `BaseEffect$$<Face>`
les recombine. Un `EffectBonus` sans formule est exactement ce que ce design demande.

Corps de `BaseEffect$$DamageMalusForDefense`, verbatim en structure :

```
InitializeBonusCacheIfNeeded(this)
bonus = <Nullable<EffectBonus>> caché à this+0x1d8       # = Create...(), mémoïsé
si !bonus.HasValue                          -> Nullable<DamageBonus> VIDE
si !bonus.Value.trigger.<slot 0>(entities)  -> Nullable<DamageBonus> VIDE      # <<< LA GATE
sinon:
   DamageBonus+0x00..+0x1f = bonus+0x30..+0x4f       (flags + Nullable<AbilityOrEffect>)
   DamageBonus+0x20 = eval(bonus+0x08)               # IAmountFormula, slot 1 = Calculate(entities)
   DamageBonus+0x28 = eval(bonus+0x10)
   DamageBonus+0x30 = eval(bonus+0x18)
   DamageBonus+0x38 = eval( this.IgnoreArmor() )     # <<< vtable +0x718, PAS un champ du bonus
   DamageBonus+0x40 = eval(bonus+0x28)
```

`BaseEffect$$DamageBonusForAttack` fait **exactement la même chose** — même gate, même
`*(code **)(*this + 0x718)` appelé avec `*(this + 0x720)` comme `MethodInfo*`, même destination
`DamageBonus+0x38`. La symétrie est mesurée, pas supposée.

## 5. Où atterrissent les accumulateurs

`CalculateDefenderModifiersForPrediction` :

- slot `0x1a` → poussé dans une `List<DamageBonus>` ; `DamageBonus+0x38` **accumulé** →
  `Fix64.op_Implicit` → **`DamageModifiers+0x28`** ; `DamageBonus+0x40` → `Nullable<Fix64>` →
  `DamageModifiers+0x00` (l'OVERRIDE final du dégât de base).
- slot `0x1b` → poussé dans la même famille de liste.
- slot `0x19` → `Nullable<PiercingBonus>` accumulé → **`DamageModifiers+0x20`**.
- puis, par `DamageBonus` de la liste : `+0x20` → `BaseCalculations$$GetFloatMultiplierFromPercentage`
  → `DamageModifiers$$Add(bonus, Nullable<Fix64>)`.

`CalculateAttackerModifiersForPrediction` : idem avec les slots `0x16` / `0x17` / `0x18`. Le sret y
est typé `undefined4 *` par Ghidra — `puVar22 + 8` vaut donc **`+0x20`** et `puVar22 + 10` vaut
**`+0x28`**, pas `+0x40` / `+0x50`. Piège de lecture à connaître.

`DamageModifiers` (0x40), reconstitué : `+0x00` `Nullable<Fix64>` OVERRIDE · `+0x20` `Fix64`
PIERCING · `+0x28` `Fix64` IGNORE-ARMOR · `+0x30` `Fix64` MULTIPLIER.

## 6. `GetBaseDamageWithFixedPiercedArmor` — la formule d'étage

```
N = 1
si defender.HasTrait(UnitTrait.MkXGravis = 0x3f5) et !isCrit :  N = 2
pierce_pct = 0
si damageProfile != null :
    pierce_pct = Min(100, Max(0,  StaticBattleRules.Damage.GetPiercingRatio(damageProfile, attacker.GetTraits())
                                + attacker.GetStat(0x1a)
                                + attacker.GetStat(isMelee ? 0x15 : 0x16)
                                + (int)Fix64.op_Explicit(additionalPiercing)
                                + (int)Fix64.op_Explicit(defenderPiercing) ))
si defender a TriggeredAbilityType.AblativePlating = 0x4b6 et !isCrit :
    v = AbilityConfiguration.GetVariableForLevel(cfg, AbilityVariableType.pierceRatio = 0x51, lvl)
    si damageProfile == null ou pierce_pct < v :  N = 3

armor_eff = Math.Max( defender.GetStat(0x10 = Armor) - (int)Fix64.op_Explicit(ignoreArmor), 0 )

pour i dans 1..N :
    baseDamage = StaticBattleRules.Damage.GetDamageWithPiercing(baseDamage, pierce_pct, armor_eff)
```

⚠ `armor_eff` est consommé **1, 2 ou 3 fois**. Une pénétration correcte avec un mauvais nombre de
passes donne un faux vert sur les cibles ordinaires (`N = 1`) et un écart sur `MkXGravis` /
`AblativePlating`.

## 7. La pose sur le DÉFENSEUR (question annexe, confirmée)

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Helspear_BuffActiveAbility$$CreateBehaviour` =

```
DSLBehaviors.AddEffect( EffectType.Helspear_IgnoreArmor = 0x62f, get_AbilityStateReference(this),
                        source = <DSLSelectors+0x30>, targets = <DSLSelectors+0x60> )   # = Target
+ DSLBehaviors.AddEffect( EffectType.DespoiledGround = 0x5c4, ..., targets = DSLSelectors.Tiles(<+0x60>) )
```

L'effet 1583 est bien posé sur `Target`. Le second volet (`DespoiledGround` sur les tuiles) n'est
pas couvert ici.

## 8. Ce que le port en fait, et l'écart D'UN ÉTAGE assumé

Le port avait déjà `DamageModifiers.armor_penetration` annoté `@0x28`, et
`armor_eff = max(armor - armor_penetration, 0)`. **Il ne manquait que le remplissage côté
défenseur** : `get_armor_penetration` n'était appelé que par `_attacker_effect_bonuses`.

Le natif n'appelle `IgnoreArmor()` **que sous le trigger** de l'`EffectBonus` du même effet. La
forme la plus fidèle serait donc d'imbriquer l'appel sous `create_effect_damage_malus_for_defense`.
**On ne le fait pas**, et c'est un choix mesuré : le port modélise l'`EffectBonus` condition-seule
par `None` (les classes concernées ne surchargent pas `create_effect_damage_*`), donc l'imbrication
rendrait l'effet MUET. On garde l'appel indépendant — comme le fait déjà la face attaquant — et la
gate est portée **dans** `get_armor_penetration`. **Écart d'un étage, assumé et nommé** ; il est
sans conséquence arithmétique tant qu'un effet ne porte pas à la fois une formule de dégât et une
pénétration sous des conditions différentes.

## 9. Ce qui reste ouvert (résidus ouverts par cette tranche)

- **slot de piercing défenseur** — le port appelle `create_piercing_bonus_for_attack` (slot **24**)
  dans la boucle DÉFENSEUR, là où le natif appelle le slot **25** `PiercingMalusForDefense`. Seul
  override natif du 25 : `ModifiedExoarmour_PierceReductionEffect$$CreatePiercingMalusForDefense`,
  non porté — donc conséquence arithmétique probablement nulle aujourd'hui, canal faux quand même.
- **`StrikeFromTheShadows` (`EffectType` 1549)** — même canal défenseur `IgnoreArmor`, effet
  **absent d'`EFFECT_CLASSES`**. Le correctif de cette tranche ne l'active pas.
- **triggers non lus** de `KanOpenerEffect` et `WayOfTheShortBladeEffect` (faces ATTAQUANT, donc
  hors du périmètre de `#1008-r2`).

## 10. Leçon de méthode

**Un lecteur peut vivre à l'INTÉRIEUR d'un slot, pas à côté de lui.** La fiche a énuméré les slots
d'interface invoqués par le consommateur, constaté qu'aucun ne s'appelait `IgnoreArmor`, et s'est
arrêtée. Le pas manquant était de **descendre dans le corps** d'un de ces slots. Le signal qui
aurait dû alerter : un effet nommé `..._IgnoreArmorEffect` dont le seul override rend un bonus
**sans aucune valeur** ne peut pas être un no-op — sinon la classe n'existerait pas, et surtout la
variable `armorIgnored` du gameconfig ne serait lue par personne. **Une variable de gameconfig qui
existe a un lecteur** ; ne pas le trouver accuse la recherche, pas le jeu.
