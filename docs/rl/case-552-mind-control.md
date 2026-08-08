# Case #552 — `1164 MindControl` (`genesMagus`), les DEUX faces

> Statut : **PORTÉ ET CONFRONTÉ LIVE** (2026-08-08, build `rnca9r7q6c`). Avant ce commit, 1164
> était absente d'`ABILITY_CLASSES` **et** de `PLAYBOOKS` : la DÉCISION pouvait la choisir, et
> l'EXÉCUTION l'ignorait — 0 debuff, 0 taunt, **aucune erreur**.
> Mesure : `scripts/python/probe_552_mind_control.py` · garde :
> `scripts/python/tests/engine/runner/test_552_mind_control_live.py` (14 tests).

## 1. La catégorie annoncée est JUSTE — et ce n'est pas une déduction

`docs/rl/combat-ability-coverage.md` classait 1164 `EFFECT/BUFF`. Cette colonne dérive du
`damageProfile` de l'**arme du porteur**, pas du behaviour : elle ne prouve rien. La lecture le
confirme quand même — `IdunBattleLogic.Entities.Abilities.Active.Loki.MindControlAbility$$ExecuteBehaviour`
ne porte **aucun** `AttackWithAttackDamage`, `UseActiveAbility`, `Spawn` ou `ChangeStat` : quatre
poses d'effet, un `Inform`, deux `If`.

MESURÉ, pas supposé : après le cast, les PV des cinq unités sont **inchangés des deux côtés** ET
l'état complet du MT19937 (`dumpRng` : `callCount`, `mti`, empreinte des 624 mots) est
**strictement égal**. Un jet de crit ou de block en consommerait un
(`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`) : le canal dégât est donc
STRUCTURELLEMENT hors de ce behaviour, pas seulement inobservé.

⚠ Le littéral `AbilityAttackType` du ctor vaut pourtant **`0` = `DirectTargetAttack`**
(`AActiveAbility..ctor(this, &opts, 0)`). Il est TRANSCRIT tel quel — même contre-exemple que
`StormOfWrath` (1019) et `BloodyFury` (1129).

## 2. Ce n'est PAS un owner-swap

Le nom l'évoque ; l'arbre ne touche **ni** l'appartenance d'équipe (aucun `OwnerComponent`, aucun
`ChangeTeam`) **ni** l'ordre d'activation (aucun `PerformAIAction`, `FinishUnitTurn`,
`ResetTurnFlags`). Hypothèse déjà réfutée par #219, **re-lue** ici sur `rnca9r7q6c` et **mesurée** :
`decisionView.units[].team` de la cible est identique avant et après le cast.

Le « contrôle » est un TAUNT : la cible ne peut plus attaquer que l'allié désigné, elle frappe
moins fort et encaisse plus.

## 3. L'arbre (mirror 1:1)

Slots de `DSLSelectors` (`factory+0x90`) : `+0x30 Owner`, `+0x38 Effect`, `+0x48 Caster`,
`+0x60 Target`, `+0x68 It`.

```
duree  = TurnsFromRounds(2)                       # LITTERAL 2 (constants ne porte que `range`)

out    = AddEffect( 1349 MindControl_OutoingDamageReduction, stateRef, Caster, Target, duree )
inc    = AddEffect( 1350 MindControl_IncomingDamageBonus,    stateRef, Caster, Target, duree )

cache  = Cache( First( SortByFormula( Attackable( Friends( of: Owner,
                                                  AdjacentUnits(Target, unique:1, 3), 3), 3),
                                      StatAmount(It, 5 = HEALTH), ascending: 0 ), 1 ), 1 )

taunt  = AddBondEffect( 27 Taunted_OnlySpecificTargets, stateRef, Caster, Target, bond = cache, duree )
marque = AddBondEffect( 1367 MindControl_Taunter,       stateRef, Caster, cache,  bond = Target, duree )

Execute( (out & inc) & If( !HasTrait(Target, 25 = Immune),
                           Inform(0xcb = TagKey.Custom_Unit_Id, cache) & If(cache, taunt & marque) ) )
```

Trois lectures que le décompilé impose, et qu'aucune ne se devine :

* **`Friends(of: Owner, ...)` = les alliés du CASTER**, pas ceux de la cible. Le 1ᵉʳ argument de
  `IdunBattleLogic.Entities.DSLSelectors$$Friends(this, of, entities, selectionType)` est le
  RÉFÉRENT ; corroboré mot à mot par l'i2 (« adjacent to one or more **friendly** units »).
* **`ascending = 0` trie DESCENDANT** (le flag natif est `ascending`, pas `descending`), donc
  `First(..., 1)` rend l'allié à la Health **la plus haute** — l'i2 « highest current Health ».
* **Le gate `Immune` ne couvre QUE le taunt** : les deux debuffs sont dans le membre GAUCHE du
  `op_BitwiseAnd` de tête. Et ce n'est pas une redite du gate générique d'`AddEffectOperation` :
  `data/symbols/<build>/metadata/can_be_immune_to.tsv` ne liste, de cette famille, que
  `IdunBattle.Entities.Effects.TauntedEffect` — 1349/1350/1367 ne sont pas immuno-gatés.
  ⚠ **NON CONFRONTÉ** : aucune unité du gameconfig ne porte le trait `Immune` en base (balayage
  exhaustif : 0 sur 669). Le gate n'est donc atteignable que par un effet qui AJOUTE le trait.

⚠ **L'appariement id ↔ classe est INVERSE de l'ordre des ctors** et se lit dans l'enum `EffectType` :
`MindControl_OutoingDamageReduction = 1349` (le nom natif porte bien la faute de frappe),
`MindControl_IncomingDamageBonus = 1350` — alors que `...IncomingDamageBonusEffect$$.ctor` PRÉCÈDE
`...OutoingDamageReductionEffect$$.ctor` en adresse.

## 4. Les trois effets

| id | classe native | corps | canal PORT | face NATIVE |
|---|---|---|---|---|
| 1349 | `...Loki.MindControl_OutoingDamageReductionEffect` | `ForAddition(get_OwnerIsCaster, Negative(ConfigVar 0x12 = dmgReduction))` | `create_effect_damage_bonus_for_attack` | `attacker` |
| 1350 | `...Loki.MindControl_IncomingDamageBonusEffect` | `ForPercentIncrease(get_OwnerIsTarget, ConfigVar 0xa = extraDmgPct)` | `create_effect_damage_malus_for_defense` | `attacker` |
| 1367 | `Idun.Source...Loki.MindControl_TaunterEffect` | `get_Range` = `Nullable(1)` + `CreateActiveCondition` | — (aucune contribution) | — |

* **`0xa` / `0x12` sont des `AbilityVariableType`**, pas des `AbilityConstantType` : l'accesseur est
  `DSLFormulas$$ConfigVar(this, variableType, abilityState, config)` — le 2ᵉ paramètre est DÉCLARÉ
  `variableType` dans `frida/methods.tsv` — et le gameconfig de 1164 porte `extraDmgPct` /
  `dmgReduction` sous `variables`. L'`AbilityConstantType` homonyme vaut 15 / 114 : les confondre
  lirait la mauvaise clé **sans lever**.
* **Les DEUX faces natives sont `attacker`** : les deux classes dérivent DIRECTEMENT de
  `IdunBattle.Entities.Effects.BaseEffect` (`classes.tsv`) et déclarent
  `CreateEffectDamageBonusForAttack` en propre (`methods.tsv`), donc le slot 0x16 — celui
  qu'invoque `CalculateAttackerModifiersForPrediction`. 1350 passe par le canal DÉFENSEUR du port
  (seule liste qui balaie les effets de la cible) avec `DEFENSE_MALUS_NATIVE_FACE = "attacker"`,
  comme `MarkerlightEffect` et `Terrifying_ExtraDefense` (#437-r1-r1-r1).
* **1367 entre au `BOND_REMOVAL_GATES`** : §8.7 de `case-462-r4b-r1-r1-r1-r1-retrait-bond.md` le
  classait « (b) armé à `Nullable<int>(1)`, mais son `EffectType` n'est pas établi et le port ne
  pose aucun de ces effets ». Les deux verrous tombent ici. Les trois virtuels RE-MESURÉS
  (`--step declared`) : `get_RemoveOnBondedEntityDeath` **true**, `get_Range` **1**,
  `get_Adjacent` **false`.

## 5. La face DÉCISION

`IdunBattle.AI.Playbook.Loki.MindControlPlaybook` — **`NonComparablePlaybook`**, et le nom ghidra
dit le contraire : le ctor décompilé affiche `ComparablePlaybook<...>..ctor(this, 0x48c)` (corps
gshared dédupliqué, donc mislabelé). La chaîne de parents LUE dans `frida/classes.tsv` tranche.

`$$EvaluateNonComparable` = `Bucket(0, minUtility = <cctor> = Fix64(1))`, une action par cible
éligible, `utility = Fix64(GetStat(cible, 5 = HEALTH))`. Patron **identique** à
`VexillaMagnificaPlaybook`, à ceci près que la cible y est un ALLIÉ et ici un ENNEMI.

⚠ **La même stat, sur deux populations différentes** : la DÉCISION classe les ENNEMIS par PV,
l'arbre de COMBAT classe MES ALLIÉS par PV. Les confondre donnerait une décision qui a l'air juste
et vise la mauvaise unité.

## 6. Ce qui a été confronté LIVE (board `MC1_67`, seed 777)

Montage COMBAT — positions forcées + PV craftés pour que **« premier voisin énuméré »** et
**« plus basse Health »** désignent tous deux l'AUTRE allié que **« plus haute Health »** : caster
`(3,2)` (distance 2, NON adjacent), allié FAIBLE `(2,4)` (2ᵉ voisin de la cible), allié FORT
`(4,4)` (dernier voisin), cible `(3,4)`, témoin isolé `(5,2)`.

| étage | résultat |
|---|---|
| exécution portée | `routed=handler`, `ported=True`, `mutated=True` |
| empreinte d'effets | port **==** natif : cible `{25,26,27,1237,1349,1350}` rem 4 ; taunteur `{1367}` rem 4 |
| bonds (cascade native) | 27 sur la cible **bondé au taunteur** ; 1367 sur le taunteur **bondé à la cible** ; 1349/1350 non bondés |
| DISCRIMINANT | le taunteur est l'allié à **40 000** PV (dernier énuméré), pas celui à **4 000** (premier) |
| dégât / PRNG | PV inchangés des deux côtés ; MT `(0, 624, …)` strictement égal |
| équipe de la cible | `2 → 2` (pas d'owner-swap) |
| taunt opposable | port `GetOnlyTargets(cible) = [taunteur]` ; natif : l'allié faible passe de `0` à `0x800000 TargetIsAllowedForCaster`, le taunteur reste `0` ; **matrice port == natif** |
| debuffs vivants | prédiction native SORTANTE `(3858, 5790) → (1468, 3400)` (baisse) ; ENTRANTE `(903, 3624) → (1086, 4350)` (+≈20 %) |
| `EffectBonus` du port | 1349 `Addition -797 owner_is_caster=True face=attacker` ; 1350 `PercentIncrease 20 owner_is_caster=False face=attacker` |
| gate + règle dynamique | port **==** natif sur 4 sondes : soi `0x4000`, allié `0x4000`, cible `0`, **témoin isolé `0x2 TargetMatchesDynamicRule`** |

Montage DÉCISION (runner séparé) — deux ennemis LÉGAUX à 5 000 et 50 000 PV, le faible **premier**
dans `fromHere` : `aiDryRunAllUnits` propose `1164` sur l'ennemi à 50 000, le port décide la MÊME
cible, et les utilités du playbook valent exactement `5000.0` / `50000.0`.

⚠ **Le témoin de la règle dynamique a dû être RE-CHOISI.** Le premier essayé, `(5,3)`, est un
`Swamp` à **élévation 4** contre 2 pour le caster : les deux moteurs y rendaient
`0x1000000 TargetIsUnobscured` — un refus RÉEL, mais d'un AUTRE étage. Un témoin qui confond deux
gates n'en mesure aucun.

## 7. Mutations adversariales (la garde a été VUE ROUGE)

| mutation | rouges |
|---|---|
| M1 — `ascending=True` (tri inversé) | **4** dont le discriminant |
| M2 — règle dynamique → `return 0` | **1** (`ennemi_isole` port 0 ≠ natif 2) |
| M3 — `bonded_ref` du taunt = `Target()` | **2** |
| M4 — signe de 1349 (`-v` → `+v`) | **2** |
| M5 — 1350 `PercentIncrease` → `PercentDecrease` | **2** |
| M6 — utilité du playbook `-hp` | **1** (le port retombe sur l'attaque normale) |
| M7 — `Friends(reference=Target())` | **4** |

Source restaurée après chaque mutation, `git status` propre, 14/14 verts.

⚠ **M4 a d'abord laissé `test_..._debuffs_bite_in_both_directions` VERT** : ce test ne lisait que
l'ORACLE natif, donc aucune mutation du PORT ne pouvait le faire rougir. Il a été **couplé** au
signe que rend le port — « une garde jamais vue rouge ne garde rien ».

## 8. Résidus ouverts

* **`#552-r1`** — `MindControl_TaunterEffect$$CreateActiveCondition` non portée (`is_active` reste
  au défaut `True`) : elle interroge les effets d'une AUTRE unité et leur `bonded`, que
  `unit_state_for_effects` n'expose pas. Écart confiné à la LISTE d'effets (1367 ne contribue à
  rien). `BLOCAGE: seeding`.
* **`#552-r2`** — le prédicat du `FilterInPlace` de `GetDynamicInvalidTargetReason` : `Func<T,bool>`
  sans capture de `MindControlAbility.<>c`, corps DÉDUPLIQUÉ, absent des DEUX tables. Résidu
  **borné** : `FilterInPlace` ne peut que RETIRER (corps lu : `RemoveAt(i)` sur prédicat faux),
  donc l'ensemble AVANT filtre borne le refus par le haut et le port ne peut pas accepter ce que
  le natif refuse. ⚠ **Ne pas le rabattre sur `!IsSteppable`** : le natif avait le flag
  `ignoreSteppables` au MÊME appel et l'a passé à `false`. `BLOCAGE: capteur`.
* **`#552-r3`** — le slot 4 `ShouldEvaluate` de `MindControlPlaybook` non mesuré (l'absence dans
  les tables ne prouve pas l'absence de surcharge — c'est ainsi que celui de Vexilla a été raté
  puis retrouvé live, #46). `BLOCAGE: aucun`.

Non couvert et nommé, en plus des trois : le gate `Immune` (aucun porteur du trait, §3) ; le
`selectionType: 3` des étages 1–3 du sélecteur (résidu PARTAGÉ `#433-r3-r2`, dégradation
permissive bornée à « un allié MORT occupant encore sa tuile ») ; l'arithmétique EXACTE des deux
debuffs (le sens et le canal sont mesurés, la reconstitution des arrondis Fix64 ne l'est pas).
