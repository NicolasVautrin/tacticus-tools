# #920 — `MawClawsOfThyrax` : le premier compteur de relique qui NE FILTRE PAS L'ÉQUIPE

**Question binaire.** Le natif ajoute-t-il `extraCritDmg[niveau de relique] × <unités à trait
`Summon` **adjacentes**>` au dégât de CRIT que le porteur inflige — et **de quel(s) camp(s)** ces
unités sont-elles comptées ?

**Réponse.** Oui, et **de n'importe quel camp**. L'étage de voisinage est
`DSLSelectors$$AdjacentUnits`, pas `AdjacentFriends`. Mesuré live : compagnons `Summon` posés
**côté adverse**, compteur natif **2**, bonus **654 = 327 × 2**, salve **bit-exacte**.

Build de mesure : `rnca9r7q6c`.

---

## 1. Identité — DEUX collisions d'ordinal, et chacune désigne une AUTRE relique

    EffectType            0x5b5 = 1461 = MawClawsOfThyrax_ExtraCritDmg   <- CET effet
    TriggeredAbilityType  0x5bd = 1469 = MawClawsOfThyrax                <- sa CONFIG
    TriggeredAbilityType  0x5b5 = 1461 = BookOfFate                      <- une AUTRE relique
    EffectType            0x5bd = 1469 = MischiefMakers                  <- autre chose encore

Les deux lectures sont tranchées par l'**adresse de la cible du `call`**, jamais par le nom :

```
IdunBattleLogic.Entities.Abilities.Triggered.Loki.MawClawsOfThyraxAbility$$GetEffectType
    b8 b5 05 00 00 c3     ; corps ENTIER : `return 0x5b5` = 1461

IdunBattle.Entities.Effects.Loki.MawClawsOfThyrax_ExtraCritDmgEffect$$.ctor
    ba bd 05 00 00        ; mov  edx, 0x5bd = 1469
    e8 <rel32> -> 0x181669f80 = AbilityOrEffect$$op_Implicit(triggeredAbility: TriggeredAbilityType)
                          ;   surcharge résolue par son RVA (les QUATRE sont homonymes)
    41 b0 01              ; mov  r8b, 1 = hasAutomaticActivation
    e8 <rel32> -> 0x18100c390 = BaseEffect$$.ctor(abilityOrEffect, hasAutomaticActivation)
```

`BookOfFate` **existe** au gameconfig : lire `0x5b5` comme une `TriggeredAbilityType` ne lèverait
donc **rien**, ça lirait juste la mauvaise config, en silence.

## 2. L'artefact, lu en entier — SEPT méthodes, deux dédupliquées

`IdunBattle.Entities.Effects.Loki.MawClawsOfThyrax_ExtraCritDmgEffect` (: `BaseEffect`) :

| méthode | corps |
|---|---|
| `$$.ctor` | `BaseEffect..ctor(this, AbilityOrEffect(0x5bd), hasAutomatic: 1)` |
| `$$CreateTargetSelector` | `<DSLSelectors+0x30>` = `Owner` — **dédupliqué** (défaut) |
| `$$CreateActiveCondition` | `DSLTriggers.AmountIsGreaterThanZero(<vslot +0x5f8>)` |
| `$$GetCalculateLevel` | le compteur, cf. §3 (c'est le `<vslot +0x5f8>`) |
| `$$CreateCritDamageBonus` | `EffectBonus.ForAddition(get_OwnerIsCaster, GetExtraCritAmount())` |
| `$$GetExtraCritAmount` | `Multiply(ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet), config@+0x60), EffectLevel(Effect@DSLSelectors+0x38))` |
| `$$GetLocalizationDataInternal` | `{ AbilityParam(0x23) : <GetExtraCritAmount> }` — affichage seul |

`$$GetExtraCritAmount` porte le corps **PARTAGÉ** avec `KardiocoreGalvanus_ExtraCritDmgEffect` : le
`config@+0x60` étant un champ d'INSTANCE, chaque effet y lit **sa** `AbilityConfiguration`.
`AbilityVariableType 0x42 = 66 = extraCritDmg` (`enums.tsv`), `UnitSelectionType 3 =
OnlyAliveAndTargetable`.

Le slot `+0x5f8` **est** `GetCalculateLevel` : `BaseEffect$$IsCalculatingLevel` et
`$$NeedsRefreshing` l'appellent tous deux et cachent le résultat dans `this+0x88`, que
`BaseEffect$$CalculateLevel` évalue ensuite. (Le slot `+0x518`, lui, est `CreateActiveCondition`,
caché en `this+0x90`.)

## 3. Le compteur — quatre nœuds, quatre RVA résolues

```
GetCalculateLevel() = Count( Unique( UnitsWithTrait( AdjacentUnits(Owner@DSLSelectors+0x30,
                                                                   unique: 1, selectionType: 3),
                                                     trait: 0x2 = UnitTrait.Summon,
                                                     selectionType: 3 ) ) )

    e8 -> 0x180eac4a0  DSLSelectors$$AdjacentUnits(origin, unique, selectionType)
    e8 -> 0x180eb5070  DSLSelectors$$UnitsWithTrait(entities, trait, selectionType)
    e8 -> 0x180eb35a0  DSLSelectors$$Unique(entities)
    e9 -> 0x180ea85e0  DSLFormulas$$Count(selector)
```

**⚠ `AdjacentUnits` NE FILTRE PAS L'ÉQUIPE.** Son corps est
`op_Subtraction( Units(AdjacentTiles(origin), unique, selectionType), origin )` — aucun `Friends`,
aucun `Enemies`. Le porteur s'exclut lui-même par ce `op_Subtraction` ; un summon **adverse**, lui,
compte.

C'est l'exacte différence avec ses deux voisins de forme, **tous deux déjà portés** :

| relique | étage de voisinage | filtre |
|---|---|---|
| `AmuletOfTheVoidwyrm` (1460) | `AdjacentFriends` | `Summon` ∪ `Decoy`, AMIS seuls |
| `KardiocoreGalvanus` (1450) | `AdjacentFriends` | `MechanicalUnits`, AMIS seuls |
| **`MawClawsOfThyrax` (1461)** | **`AdjacentUnits`** | **`Summon`, TOUS CAMPS** |

Recopier l'un des deux manquerait tous les summons adverses — silencieusement, et sur l'axe
Tyranides / Genestealer, où les **deux** camps en produisent. Le `Unique` est un nœud
**supplémentaire** que ni 1450 ni 1460 ne portent, bien qu'`AdjacentUnits` reçoive déjà `unique: 1` :
on le mirrore quand même (on porte le corps, pas l'économie qu'on pourrait en faire).

## 4. La condition d'activité — le MÊME compteur comparé à zéro (l'INVERSE de 1450)

```
$$CreateActiveCondition, relu octet à octet :
    48 8b 41 48              ; rax = this->dsl (+0x48)
    48 8b 98 88 00 00 00     ; rbx = dsl.Triggers (+0x88)
    48 8b 82 f8 05 00 00     ; rax = vtable[+0x5f8]          <- GetCalculateLevel
    ff d0                    ; call
    e9 <rel32> -> 0x180ed52d0 = DSLTriggers$$AmountIsGreaterThanZero(amount: IAmountFormula)
                             ;   surcharge tranchée par l'ADRESSE (l'autre, 0x180ed5360, prend un
                             ;   ITargetsSelector)
```

Conséquence de harnais, et c'est **l'inverse** de `KardiocoreGalvanus` (dont la condition est
`<DSLTriggers+0x70>` = `YesTrigger`, constante VRAIE) : l'effet est **INACTIF** tant qu'aucun summon
n'est adjacent, donc **ABSENT du canal `decisionView.effects`** (ACTIF-ONLY, #100) — même motif
qu'`AmuletOfTheVoidwyrm`, `NetherRealmCasket` et `VisionsOfHeresy_*`. D'où
`active_condition_ported = True` et la clé `adjacent_summons` du `unit_state`.

**GROUND TRUTH** (runner `MC1_67` / seed 31337) : à voisinage vide, `decisionView` publie
`active: false` ; dès un summon adjacent, `active: true` avec `level` = le compte.

## 5. Le canal — `ForAddition` sur le CASTER

```
$$CreateCritDamageBonus, cibles de `call` résolues par leur RVA :
    e8 -> 0x18105ef40  GetExtraCritAmount()
    e8 -> 0x180edbaa0  DSLTriggers$$get_OwnerIsCaster
    e8 -> 0x181047dc0  EffectBonus$$ForAddition(trigger, addition, abilityOrEffect)
                       (et NON 0x181048090 = $$ForSubtraction : c'est l'ADRESSE qui tranche)
```

`get_OwnerIsCaster` = `AreEqual(Owner@DSLSelectors+0x30, Caster@DSLSelectors+0x48)`, trigger **nu**
(aucun `op_BitwiseAnd`). `DamagePrediction$$GetCritDamageBonusFromEffects` accumule
`addition - subtraction` et `$$CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)` — le
port rend donc un entier **POSITIF**, et le clamp bas ne peut pas mordre sur un terme additif.

## 6. La pose — owner-effect PERMANENT, à l'init

`classes.tsv` : `MawClawsOfThyraxAbility` dérive d'`IdunBattle.Entities.Abilities.
AOwnerEffectTriggeredAbility` et n'override **que** `GetEffectType`. Le `CreateBehaviour` de base :

```
If( CreateTrigger() = OnOwnerSpecificAbilityInit(<this+0x10> = 1469),
    AddEffect( GetEffectType() = 0x5b5,
               AbilityState(Owner@DSLSelectors+0x30, AbilityType(abilityState)),
               source = targets = Owner@DSLSelectors+0x30,
               turns  = <zeroe>  ->  PERMANENT ) )
```

donc **source == porteur == Owner**, une fois à l'initialisation, jamais expiré — ce qui l'éteint est
sa `CreateActiveCondition`, pas une durée. C'est ce qui rend le niveau exact : l'`AbilityState` baké
dans l'`EffectComponent+0x18` est celui de la relique **sur son porteur**, l'état TERTIAIRE, relu par
le foyer unique `runner/operations/triggers/base.py::triggered_ability_state` (#357).

**Pas d'entrée `ABILITY_INIT_OWNER_EFFECTS`, et c'est mesuré** : `_seed_ability_owner_effects` lit le
KIT gameconfig, où la relique ne figure pas (elle arrive par `BC.Units[].TertiaryAbility`). Même
arbitrage explicite que `kardiocore_galvanus.py`.

## 7. La face DÉCISION — DEUX playbooks, un porté ici, un déjà porté, une face morte

* **`MawClawsOfThyraxNonOwnerPlaybook`** — face NON-OWNER, **déjà portée** (#271-r3 / #477-r35,
  `engine/playbook/non_owner.py`). Clé `MawClawsOfThyrax_AdjacentSummons` = 5.
* **`MawClawsOfThyraxPlaybook` (MOVE)** — **portée par cette tranche**
  (`engine/playbook/adjacent_summons.py`) :

  ```
  tile  = UtilityMovementCase.get_MovementTile(case)
  units = query.<slot 0x7a>(tile, null, null, false)          // GetAdjacentUnits
  val   = 0
  foreach (u in units)
      if (UnitExtensions.HasTrait(u, 0x2))                     // UnitTrait.Summon
          val += getUtilityVal("MawClawsOfThyrax_LikesAdjacentSummons");   // 5
  yield Fix64.FromInt(val)
  ```

  Le slot `0x7a` est déjà établi (#443-r1, `savior_protocols.py`) : `GetAdjacentUnits(tile,
  friendsOf, enemiesOf, ignoreSteppables)`, tranché par le COMPTE et l'ORDRE des arguments (4 après
  `this`, littéraux `0, 0, 0` = aucun filtre de camp, steppables inclus). **Différence lue avec
  `KardiocoreGalvanusPlaybook`** : celui-ci passe le slot `0x83` (`GetAdjacentFriends`, arité 2) et
  son corps **jette** le `get_Current` de l'énumérateur (il ne fait que compter) ; celui-ci
  **filtre** par `HasTrait`. Deux corps de même forme, un filtre chez l'un et pas chez l'autre.
  Comme toute la famille « corps propre », il **n'exclut pas le mover** (encore sur son origine
  pendant le sweep) : le port le réintroduit par `self_pos`/`unit_traits`.
  ⚠ Les deux clés BC valent **5** toutes les deux au gameconfig vivant, donc une confusion serait
  aujourd'hui **invisible** — d'où la lecture par slot de littéral (`0x33d90d0` vs `0x33d8f88`).
* **face ATTACK du playbook owner — MORTE, et c'est LU** :
  `...MawClawsOfThyraxPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext` a pour
  corps entier `yield return Fix64.op_Implicit(0)`. Pas d'entrée au registre ATTACK : elle
  n'ajouterait qu'un terme nul. Figé par un test, sans quoi « il manque une entrée » se lirait comme
  un oubli.

## 8. Les porteurs — ÉTAT 2, les quatre au pool

`items/R_Crit_MawClawsOfThyrax`, `allowedUnits = [tyranTyrantGuard, tyranWingedPrime,
tyranParasite, genesPatriarch]` — **4/4 au pool** (`rl_duel build --list-pool`, rank 17), **aucun**
ne l'équipe au seed, et la config d'ability est **absente du seed BC** (l'une des 29). Donc état 2 de
la gate relique : `rl_duel build --equip-relic`, qui pose les **trois** écritures d'un bloc.

## 9. Ce qui a été mesuré live (board `MC1_67`, seed 31337, niveau de relique 3 sauf mention)

| bras | compteur natif | compteur port | actif natif | bonus port | salve |
|---|---|---|---|---|---|
| `n=0` amis | *(périmé, cf. §10)* | 0 | **false** | `None` | LIVE == OFFLINE, aucun mutant ne mord |
| `n=1` amis | 1 | 1 | true | 327 | `[6789, 7995]` bit-exact, 2 mutants mordent |
| `n=2` amis | **4** | **4** | true | **1308** | `[7342, 8809]` bit-exact, 2 mutants mordent |
| `n=2` **ENNEMI** | **2** | **2** | true | **654** | `[7588, 6929]` bit-exact, 2 mutants mordent |
| `n=1` ennemi, **niv. 10** | 1 | 1 | true | 438 | bit-exact ; `PASSIF` ne mord PAS (clamp) |
| `n=2` ennemi, **niv. 10** | 2 | 2 | true | 876 | bit-exact ; `PASSIF` ne mord PAS (clamp) |
| `--trait Hero` (négatif) | 0 | 0 | **false** | `None` | bit-exact, canal muet |
| `--porteur-defenseur` | 2 (**PLEIN**) | 2 | true | **`None`** | cf. §10 |

Le `n=2` amis à **4** n'est pas une erreur de montage : `genesMagus`/`genesPrimus` **SPAWNENT** des
`genesSmnNeophyte` pendant les cycles de tour, et ces summons entourent l'ancre. Le natif les compte,
le port aussi. C'est ce qui a fait **corriger le probe** : son attendu ne comptait que les
COMPAGNONS, il compte désormais **tout le voisinage mesuré**, trait par trait.

## 10. Deux constats qui ne sont PAS des défauts de port

**(a) Le `level` publié d'un effet INACTIF est PÉRIMÉ.** Mesuré : voisinage **vide**,
`active: false`, et pourtant `decisionView.effects[].level = 1`.
`RefreshEffectsOperation$$UpdateLevel` n'est atteint que par le chemin qui rafraîchit un effet
**actif** ; le champ garde donc sa dernière valeur. Le probe ne confronte ce champ que sur un effet
ACTIF, et le dit. (Corollaire : le repli du port sur `self.level` quand aucun `state` n'est threadé
lirait la même valeur périmée que le nœud natif `EffectLevel` — ce n'est donc pas une divergence,
mais c'est pourquoi la mesure live threade **toujours** le compteur.)

**(b) Le bras `--porteur-defenseur` porte une divergence PRÉ-EXISTANTE de `+1` par coup.**
Montage `blackHaarken` → `tyranTyrantGuard` : LIVE `[2420, 2554, 2385, 1745]`, port
`[2421, 2555, 2386, 1746]`. **Attribué par mesure** — `scripts/python/engine` ramené à
`origin/master` (donc **sans ce port**) rend `DELTA [1, 1, 1, 1]` **identique**, et le canal
MawClaws y est de toute façon muet (`NOCHANNEL` rend le même offline). Résidu **`#920-r1`**. Ce bras
confronte donc l'**étage TRIGGER** (`get_OwnerIsCaster` avec un compteur PLEIN → bonus `None`), pas
la salve.

### (b bis) `#920-r1` — l'étage est ISOLÉ et le corps natif est LU (#949, 2026-08-12)

Décomposition par étage du rejeu offline (patch en **forme B** sur le binding de `normal.py` : un
patch du module source ne mord pas, cf. CLAUDE.md). Les étages amont sont **identiques** :

```
get_base_damage_fix64(3106)          -> [2485, 3727]     # crit = ATTACK 1106 + critDamage 2000
apply_pierce_and_modifiers(., p80, armure 0) -> identite  # pct/pctd VIDES, mult = 1.0
apply_all_modifiers(DEF, round_materialize)  -> identite
```

Le seul modificateur non trivial est un `EffectBonus(PercentSubtractionCapped, value = 33,
cap = 1996, native_face = 'defender')` — le `GuardianOrganism_DamageReduction` du défenseur, que
`#920-r1` disait « probablement hors cause ». **Il EST la cause** : rangé dans `capped_reductions`,
il est consommé par `capped_reduction_flat` (`engine/services/damage_modifiers.py`), à `D` = centre
des bornes crit = `(2485 + 3727) / 2` = **3106**.

* **port** : `int(3106 * 33 / 100.0)` = `int(1024.98)` = **1024** (troncature, en float Python) ;
* **natif** : **1025** — c'est exactement le `DELTA [1, 1, 1, 1]` mesuré.

Et le natif se **lit**, il ne se déduit pas de l'écart.
`IdunBattle.Entities.Formulas.PercentageOf$$CalculateInternal`, corps LU :

```
p = Fix64(percentage) ; p = Round(p/100 * 100, 0) / 100
v = Fix64(finalAmount) * p
v = Round(v * 100, 0) / 100                     # arrondi au CENTIEME
return IdunBattle.DSL.AAmountFormula$$RoundFix64Result(v, <this+0x20>)
```

`RoundFix64Result(., 0)` est le foyer d'arrondi PARTAGÉ de #344 (demi-vers-le-PAIR). Il n'y a
**aucune troncature** dans cette chaîne : `1024.98` en sort à **1025**. L'arbre au-dessus est
confirmé par `IdunBattle.Entities.Effects.Loki.GuardianOrganism_DamageReductionEffect$$CreateEffectDamageMalusForDefense`
= `ForSubtraction(get_OwnerIsTarget, Min(PercentageOf(CurrentDamage, ConfigVar(0x46)),
ConfigVar(0x12)))`.

**CE QUI RESTE, ET POURQUOI LE CORRECTIF N'EST PAS APPLIQUÉ ICI — deux témoins natifs en TENSION.**
La docstring de `capped_reduction_flat` revendique l'inverse, sur une mesure live de #91 :
« `PercentageOf` en Fix64 TRONQUE (confirmé LIVE #91 : D->flat=177=floor, PAS 178=round) ». Or le
modèle `Round` ci-dessus rendrait **178** pour tout `D` dans `[538, 539]`, et **177** pour
`D = 537` — c'est-à-dire qu'il est **non discriminant** si le `D` de #91 valait 537, et
**contredit** la mesure sinon. Les deux témoins ne peuvent pas être vrais ensemble.

Trancher demande **une seule mesure** : le `D` exact du montage #91 (Tyrant Guard, flat 177). S'il
vaut 537, la conclusion « floor » de #91 a été prise sur un cas où `floor == round` — la prémisse
tombe, et le correctif est un `_round_fix64(Fraction(D * pct, 100), 0)` d'une ligne. S'il vaut 538
ou 539, alors `D` du port n'est **pas** le `CurrentDamage` du natif, et c'est la RÉFÉRENCE qu'il
faut corriger, pas l'arrondi. Fixer l'arrondi sans cette mesure serait un scalaire fitté sur un
témoin en réparant un bug et en en créant un autre.

## 11. Cliquets

* `scripts/python/tests/engine/test_920_maw_claws_of_thyrax_offline.py` — **19** étages : ordinaux
  écrits aux sites, les deux collisions, structure de l'arbre (4 nœuds + littéraux), **interdiction
  d'`AdjacentFriends`/`MechanicalUnits`/`Union` dans l'arbre**, produit signé positivement, repli sur
  le niveau capté, gates, condition d'activité (+ contre-témoin `KardiocoreGalvanus` à
  `active_condition_ported = False`), playbook MOVE (registre, clé BC, deux camps, self), absence
  délibérée au registre ATTACK, clés du substrat, gate de présence GÉOMÉTRIQUE SEUL, import isolé.
* `scripts/python/tests/engine/runner/test_920_maw_claws_of_thyrax_live.py` — **3** bras (AMIS,
  ENNEMI, NÉGATIF), montage importé du probe.
* `scripts/python/probe_920_maw_claws_of_thyrax_live.py` — la MESURE, 7 bras.
* **Batterie de mutants** jouée sur les cliquets offline : **14/14 MORDENT**
  (`AdjacentFriends` au lieu d'`AdjacentUnits`, `Unique` retiré, trait `Decoy`, `selectionType 1`,
  `active_condition_ported = False`, `ForSubtraction`, `get_OwnerIsTarget`, `is_active` fermante,
  playbook amis-seulement / sans filtre / sans self / mauvaise clé BC, clé gatée sur `_has_sa`,
  compteur exigeant une équipe).

## 12. Ce qui n'est PAS couvert

* le `Unique` n'est **jamais liant** sur ce build : `AdjacentUnits` reçoit déjà `unique: 1` et le
  port dédoublonne par `id`. Il est porté par fidélité, pas parce qu'une mesure le distingue ;
* `GetLocalizationDataInternal` (affichage) n'est pas porté — aucun observable de combat ;
* aucun porteur **spawné** de cette relique n'existe : l'arbitrage « pas d'entrée
  `ABILITY_INIT_OWNER_EFFECTS` » est à rouvrir s'il en apparaît un ;
* les trois autres porteurs (`tyranWingedPrime`, `tyranParasite`, `genesPatriarch`) ne sont pas
  confrontés : le canal ne lit ni stat ni trait du porteur, donc le montage n'en dépend pas — mais
  ce n'est pas mesuré.
