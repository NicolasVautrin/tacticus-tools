# #521 — `1195 TalonsOfTheEmperor` : deux profils, un compteur, et un `any` qui n'en était pas un

Build `rnca9r7q6c`. Porteur **unique**, lineup, **dans le pool** rank 17 : `custoAtlacoya`
(Atlacoya, Adeptus Custodes / Sisters of Silence). Face COMBAT **portée**
(`engine/runner/abilities/custodes.py`) ; avant cette tranche l'ability était un **NO-OP
SILENCIEUX** — absente d'`ABILITY_CLASSES`, donc la décision pouvait la choisir et l'exécution
l'ignorait : 0 dégât, 0 effet, aucune erreur.

## 1. L'arbre, mirror 1:1

`IdunBattleLogic.Entities.Abilities.Active.Loki.TalonsOfTheEmperorAbility$$ExecuteBehaviour`
(slots `DSLFactory` `this@+0x30` : `+0x78 Behaviors · +0x80 Formulas · +0x88 Triggers ·
+0x90 Selectors` ; slots `DSLSelectors` : `+0x48 Caster · +0x50 CasterTile · +0x60 Target`) :

```
dmg  = DSLFormulas.Sum( AActiveAbility.MinMaxDamage(this, abilityState, isPrediction = 0),
                        TalonsOfTheEmperorAbility.GetExtraDamage(this, abilityState) )
atk1 = DSLBehaviors.AttackWithAttackDamage( Caster@+0x48, Target@+0x60, dmg,
           DSLSelectors.Direct( Nullable(AActiveAbility.GetDamageProfile(this)) ),
           DSLFormulas.Direct( AActiveAbility.GetHits(this) ),
           AbilityOrEffect(this), <options ZÉRO>, selectionType = 2 )
dmg2 = <la MÊME expression, re-construite terme à terme>
atk2 = DSLBehaviors.AttackWithAttackDamage( …, Direct( Nullable(GetDamageProfile2(this)) ), … )
cond = TalonsOfTheEmperorAbility.MeetSecondDamageProfileRequirement()
AActiveAbility.Execute( DSLBehaviors.If(cond, then = atk2, else = atk1), entities )
```

`…$$MeetSecondDamageProfileRequirement` — la sous-expression est **écrite deux fois** dans le
binaire (méthode nommée + inline dans `ExecuteBehaviour`), terme pour terme :

```
DSLTriggers.HasTrait( Target@+0x60, 0x3ea = UnitTrait.Psyker )
op_BitwiseOr
DSLTriggers.HasFaction(
    DSLSelectors.NonSteppableOrObjectUnits(
        DSLSelectors.AdjacentFriends( unit = Caster@+0x48, unitTile = CasterTile@+0x50,
                                      unique = 1 ), 3 ),
    0x12 = UnitFaction.Custodes, 3 )
```

`…$$GetExtraDamage` :

```
per = DSLFormulas.ConfigVar( 8 = AbilityVariableType.extraDmg, abilityState, config@+0x60 )
has = DSLTriggers.HasEffect( Caster@+0x48, 0x58c = 1420, activeOnly = 0, sourceFlags = 6 )
lvl = DSLFormulas.EffectLevel( DSLSelectors.EffectFromOwner(Caster@+0x48, 0x58c) )
n   = DSLFormulas.If( has, lvl, DSLFormulas@+0x18 = Direct(0) )
return DSLFormulas.Multiply( per, n )
```

et `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(unit, unitTile, unique)` (LU : la
factory ne fait que **composer**, elle n'alloue aucun sélecteur dédié) :

```
Friends( of = unit, op_Subtraction( Units(AdjacentTiles(unitTile), unique, 3), unitTile ), 3 )
```

**Ni rayon ni `includeCenter`** dans cette signature : la portée est le ring-1 hex et le porteur est
exclu (`AdjacentTilesSelector$$Select` retire déjà son origine, ce qui rend l'`op_Subtraction`
inerte — il est mirroré parce qu'il est écrit).

**Les deux branches partagent `MinMaxDamage` ET `GetHits`.** Le décompilé rappelle
`AActiveAbility$$MinMaxDamage` (jamais `MinMaxDamage2`) et `AActiveAbility$$GetHits` (jamais
`GetHits2`) dans la seconde branche : les clés de config restent `minDmg` / `maxDmg` / `nrOfHits`.
La seule différence est `GetDamageProfile` (`constants.damageProfile` = `Power`, `PiercingRatio 40`)
contre `GetDamageProfile2` (`damageProfile_2` = `DirectDamage`, `PiercingRatio 100`). Un port qui
aurait basculé sur `minDmg_2` / `nrOfHits_2` aurait lu des clés **absentes** du kit.

i2 : « Deals `{nrOfHits}`x `{minDmg}-{maxDmg}` Power Damage to an adjacent enemy unit. This attack
deals +`{extraDmg}` Damage for each time a friendly Character has used an active ability this
battle. If the target is a Psyker or Atlacoya is adjacent to a friendly Adeptus Custodes, this
attack deals Direct Damage instead. » — les trois phrases sont les trois étages ci-dessus.

## 2. Le câblage, et le littéral qui contredit l'œil

`…TalonsOfTheEmperorAbility$$.ctor` est de forme **STATIC-COPY** : aucun appel à
`TargetingOptions$$.ctor`, il recopie les 0x40 octets du preset `<TargetingOptions statics>+0x40`
puis appelle `AActiveAbility..ctor(this, &opts, 2)`. Le masque effectif est donc la constante écrite
par `IdunBattle.Core.Services.TargetingOptions$$.cctor` — champs **relus** dans le `cctor` :
`+0x40 isSelfCasting = 0`, `+0x48..0x5f range` = `<TargetingRange statics>+0x30` = `RANGE_ADJACENT`,
`+0x60 forceMeleeTarget = 1` (`RangedBool.False`), `+0x68 rules = 0x4000` = `TargetIsEnemy` **seul**.
C'est le **même preset** que `MartialInspirationAbility$$.ctor` (1191) — l'entrée qui existait dans
`TARGETING_OPTIONS_UNPORTED` portait déjà exactement ces valeurs, et la tranche l'a **migrée** sur la
classe (contrat de disjonction).

En revanche le **3ᵉ argument littéral diffère** : `2` = `AbilityAttackType.Others` ici, `0` =
`DirectTargetAttack` pour 1191. **Transcrit, jamais déduit** : 1195 est une attaque directe
mono-cible sur la cible du message et porterait `DirectTargetAttack` à l'œil. Même configuration que
`1197 ExcruciatingFrequencies`. Le preset de ciblage est partagé ; le littéral d'`AbilityAttackType`
ne l'est pas.

## 3. Ce que la mesure a trouvé : `HasFaction` n'est pas un `any` (#521-r2)

`IdunBattle.Entities.Triggers.HasFactionTrigger$$ShouldTrigger` résout son sélecteur par **une**
invocation d'interface qui rend **une** entité (`if (unit == 0) return 0` puis
`UnitExtensions.HasFaction(unit, this+0x10)`) : il n'itère rien. Le nœud porté
(`engine/entities/triggers.py::HasFaction`) faisait `any(...)` sur l'ensemble — **indiscernable**
tant que son unique consommateur (`HasFaction(Target(), Sisterhood)` de
`ThriceBlessedConflagration`) passait un sélecteur mono-unité.

Ce call-site est le **premier à passer un ENSEMBLE**, et c'est ce qui l'a rendu observable. Deux
montages qui ne diffèrent que par l'échange de deux tuiles :

| régime | ami sur `(5,7)` (3ᵉ voisin) | ami sur `(4,8)` (5ᵉ voisin) | profil NATIF |
|---|---|---|---|
| `mixte`     | `darkaCompanion` (DarkAngels) | `custoKyrus` (Custodes) | **14 `Power`** |
| `mixte_inv` | `custoKyrus` (Custodes) | `darkaCompanion` (DarkAngels) | **15 `DirectDamage`** |

Les trois hypothèses étaient séparées **par construction** : `any` aurait rendu `DirectDamage` dans
les deux, un `SingleOrDefault` (0-ou-1) `Power` dans les deux. Le natif change de branche ⇒
`SelectSingle` = **le premier élément** (mirror de `IdunBattle.DSL.TargetsSelector$$SelectFirst`,
qui énumère et rend le premier `get_Current` non nul). Le nœud est réparé en `resolve_unit`.

**Conséquence de jeu, et elle contredit l'i2** : le texte promet « si Atlacoya est adjacent à un ami
Adeptus Custodes », mais le natif ne regarde que le **premier** ami de l'ordre d'adjacence stocké de
la tuile du caster. Un ami Custodes en 2ᵉ position ne déclenche pas la bascule.

**Rayon de souffle de la réparation** : deux consommateurs exécutables du nœud, tous deux
mono-unité (`sisterhood.py::ThriceBlessedConflagrationAbility`, `probe_354`) — comportement
inchangé, vérifié en rejouant `test_thrice_blessed_decision_live.py` (4 passed) et
`test_mow_groups_bcd_live.py` (6 passed, 1 skip préexistant).

## 4. Le montage : un cast par runner, et c'est une mesure

Le kit 1195 ne porte **aucun `cooldownTurns`** (contraste `MartialInspiration`, qui porte
`cooldownTurns = 2`). Mesuré sur le runner : après le premier cast, le champ `CanUse` de
l'`ActiveAbility` reste `false` pour toute la bataille (`usable: false`, `unresetedLastTurnUsed: 0`,
`cooldown: null`), à travers **10 cycles de tour complets**. 1195 est donc **une fois par bataille**,
et le compteur ne peut pas se balayer en rejouant l'ability : **chaque point de mesure est un
build**. Le second régime de compteur s'obtient en faisant caster un allié **avant** Atlacoya —
`custoTrajann` / `1184 MomentShackle`, self-cast, placé loin.

Six régimes (`probe_521_talons_of_the_emperor.py`), **armure non nulle partout** — sans elle
`Power` et `DirectDamage` rendraient le même dégât et l'étage `If` ne serait pas mesuré :

| régime | compteur 1420 | profil natif | port | ce qu'il exerce |
|---|---|---|---|---|
| `power`     | 0 | 14 | 2764 = 2764 | branche `else`, témoin |
| `power_n1`  | 1 | 14 | 3650 = 3650 | `Sum(MinMaxDamage, GetExtraDamage)` (`extra = 886`) |
| `psyker`    | 0 | 15 | 5717 = 5717 | branche `then` par `HasTrait` (+ l'aura `DaughterOfTheAbyss`) |
| `custodes`  | 0 | 15 | 4764 = 4764 | branche `then` par `HasFaction` |
| `mixte`     | 0 | 14 | 2764 = 2764 | ordre d'adjacence, non-Custodes en tête |
| `mixte_inv` | 0 | 15 | 4764 = 4764 | ordre d'adjacence, Custodes en tête |

Chaque cast est confronté **coup par coup** (`UnitDamaged` natif filtré sur
`Active_Ability_Type = 1195`), **profil par profil** (`DamageProfileType`) et **tirage par tirage**
(`dumpRng` avant/après contre l'état MT du port : 2 `genrand_int32` par coup à `critChance = 0`,
famille ATTACK). Cinq contre-épreuves hors-ligne rejouent la **même capture** avec **un seul**
élément du mirror retiré ; le probe **exige** que celles qui doivent discriminer discriminent :

* `sans_extra` diverge à compteur 1 (3650 → 2764) et **pas** à compteur 0 — c'est ce qui distingue
  « le port lit le compteur » de « le port l'ignore » ;
* `profil_fixe_power` diverge dans `psyker` / `custodes` / `mixte_inv`, `profil_fixe_direct` dans
  `power` / `mixte` ;
* `psyker_seul` diverge dans `custodes` (le volet FACTION décide), `faction_seule` dans `psyker`
  (le volet TRAIT décide).

## 5. Résidus nommés

* **`#521-r1`** — la face TRIGGERED
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TalonsOfTheEmperor_UsedAbilitiesAbility`
  (`TriggeredAbilityType` 1330), qui **accumule** le niveau de l'effet 1420, n'est pas portée. Son
  `CreateTrigger` est LU et son corps est le **même** que celui de
  `…FuelledByFury_ExtraDamageAbility$$CreateTrigger` (dédupliqué par IL2CPP — un seul propriétaire
  dans la table) : `On(0xe = UnitPostAbility) & AreFriends(Owner@+0x30, actor@+0x48) &
  (HasTrait(actor, 0x10 = Hero) & !HasTrait(actor, 0x419 = MachineOfWar)) &
  IsActiveAbilityCountedAsUsed(isPreAbilityTrigger = 0)`. Le port **lit** le niveau depuis la capture
  (`decisionView.units[].effects[].level` → `EffectsState`, même canal que
  `FuelledByFury_ExtraDamage`) ; il ne le fait pas avancer sur un état rejoué plusieurs tours
  hors-ligne. Porter 1330 est une tranche à part : le rail `runner/operations/triggers/loki/` et
  `is_active_ability_counted_as_used` existent déjà, il ne manque que la classe et son inscription.
* **`#521-r2`** — **TRANCHÉ** par ce cas (§3) : sémantique `SelectSingle` = premier élément,
  mesurée et gardée par le couple `mixte` / `mixte_inv`.
* **`#521-r3`** — `entities/triggers.py::HasTrait` porte le **même** idiome `any(...)` et sa
  docstring porte déjà le doute (« single-vs-any sur une liste = à confirmer à l'agreement »).
  Aucun de ses call-sites portés n'est multi-unités, donc **aucune** mesure ne le tranche ; on ne le
  change pas sur la foi du voisin réparé ici. Le montage qui le trancherait est le même patron :
  un call-site natif qui passe un ENSEMBLE à `HasTrait`, deux arrangements qui échangent l'ordre.
* `selectionType = 2` (9ᵉ argument d'`AttackWithAttackDamage`) et l'`options` struct **zéroée**
  (8ᵉ argument) : aucun étage porté — résidus **partagés** par tous les call-sites de cette feuille.

## 6. Ce qui garde

* `scripts/python/tests/engine/runner/test_521_talons_of_the_emperor_live.py` — 12 tests : le
  câblage du registre (masque + `AbilityAttackType = Others` + disjonction sur les DEUX listes),
  l'appariement **nom ↔ ordinal** des quatre enums (1195 / 1420 / 1002 / 18, chacun nommant autre
  chose dans un enum voisin), la **différence** des deux profils et de leur perçage, l'absence de
  `cooldownTurns` (le jour où un build en ajoute un, le montage « un cast par runner » redevient
  discutable et ce test le dit), le nœud `HasFaction` **hors live** (le pendant offline du couple
  `mixte`/`mixte_inv`), la disjonction du gate, et les six confrontations live.
* `scripts/python/probe_521_talons_of_the_emperor.py` — la MESURE (montage + critères), foyer
  unique appelé par le test.
