# case-334 — `DefendTheDivineWork` (1117), face COMBAT : deux Operations, deux sélecteurs

**Question** : `IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour`
enchaîne deux Operations. Que répare-t-il, et **qui** attaque ensuite ?

**Réponse, lue au désassemblage puis mesurée live** : l'étage 1 répare **le caster ET ses alliés
adjacents** ; l'étage 2 fait attaquer **les alliés adjacents mécaniques SEULS**. Les deux étages
partent du même sous-arbre — et c'est précisément le `op_Addition Caster` de l'étage 1, **absent**
de l'étage 2, qui les sépare.

Re-dérivation : `python scripts/python/probe_334_defend_the_divine_work.py --scenario {repair,attack,caster}`
Tests : `scripts/python/tests/engine/runner/test_defend_the_divine_work_live.py`
Port : `scripts/python/engine/runner/abilities/admec.py` (+ `abilities/repair.py` pour l'étage 2).

---

## 1. L'artefact natif, verbatim

`DefendTheDivineWorkAbility$$ExecuteBehaviour(this, abilityState, entities)` :

```
hpToRepair = AbilityConfiguration.GetVariableForLevel( config@0x60, 0x24 = 36 hpToRepair,
                                                       abilityState, 0 )

# ---- étage 1 : la RÉPARATION -----------------------------------------------------------------
adj      = DSLSelectors.AdjacentUnits( CasterTile@0x50, unique = 1, selectionType = 3 )
friends  = DSLSelectors.Friends( of = Caster@0x48, adj, 3 )
targets  = friends  op_Addition  Caster@0x48                      # == `$$GetHealTargets`
beh1     = DSLBehaviors.Repair( mechanic = Caster@0x48, targets,
                                DSLFormulas.Get(hpToRepair),
                                AbilityOrEffect(this+0x10 = 0x45d = 1117),
                                RepairBehaviourOptions.ForRepair() )    # scope 0, removeEffects 1
AActiveAbility.ExecuteAtomic( beh1, entities, groupType = 0x2a )

# ---- étage 2 : le COUP GRATUIT de GalvanicField -----------------------------------------------
acting   = DSLSelectors.Friends( of = Caster@0x48,
                                 DSLSelectors.AdjacentUnits(CasterTile@0x50, 1, 3) )
                                                                  # == `$$GetAdjacentFriends`
beh2     = Repair_GalvanicFieldAbility.CreateAttackBehavior( dsl@0x30, acting )
return AActiveAbility.Execute( beh2, entities )
```

Deux **invocations distinctes** du pipeline (pas d'`op_Addition` / `op_BitwiseAnd` entre elles) :
l'étage 2 ré-évalue donc son sélecteur **après** la réparation.

`$$GetHealTargets` et `$$GetAdjacentFriends` sont deux méthodes natives NOMMÉES qui matérialisent
chacune un des deux sous-arbres — confirmation croisée du découpage ci-dessus.

## 2. Le piège du cas — et pourquoi il ne se lit qu'au désassemblage

L'erratum de la tranche 1 (#328, `case-317` §3) l'avait déjà nommé : *une cellule de table qui
résume `feuilleA + feuilleB` perd la distinction de leurs arguments, et le décompilé Ghidra réutilise
le même nom de variable pour l'arbre filtré et l'arbre nu*. Ici la forme est la même, sur un autre
axe : **les deux étages construisent le MÊME `Friends(AdjacentUnits(...))`, et un seul lui ajoute le
caster.** Au décompilé, les deux blocs se ressemblent à s'y méprendre.

```
; ---- étage 1
1812ef9b1  mov  r12, [rdx+0x48]   ; Caster       <- `of` de Friends ET opérande de l'addition
1812ef9c0  mov  rdx, [rdx+0x50]   ; CasterTile   <- origine des adjacents
1812ef9cd  call DSLSelectors$$AdjacentUnits
1812ef9e6  call DSLSelectors$$Friends
1812efa08  mov  rdx, [rdx+0x48]   ; Caster       <- RELECTURE, 2e opérande
1812efa12  call TargetsSelector$$op_Addition     ;  Friends(...) + Caster
...
1812efb26  mov  r9d, 0x2a
1812efb52  call AActiveAbility$$ExecuteAtomic

; ---- étage 2
1812efb77  mov  rdi, [r14+0x48]   ; Caster
1812efb8f  mov  rdx, [rdx+0x50]   ; CasterTile
1812efb93  call DSLSelectors$$AdjacentUnits
1812efbac  call DSLSelectors$$Friends
1812efbb4  mov  rdx, rax          ; <- PASSÉ DIRECTEMENT, **aucun op_Addition**
1812efbba  call Repair_GalvanicFieldAbility$$CreateAttackBehavior
```

L'i2 dit la même chose deux fois, dans deux textes distincts :

* 1117 — « Repairs **himself and** all friendly adjacent units {hpToRepair} Health. »
* `GalvanicField` — « Whenever Actus repairs **another unit**, that unit immediately attacks… »

Trois sources indépendantes (désassemblage, méthodes natives nommées, i2) concordent.

## 3. Identifier `DSLSelectors+0x48` / `+0x50` — deux voies, jamais une seule

Le champ `+0x48` sert à la fois de référence d'équipe et d'opérande d'addition ; `+0x50` est
l'origine des adjacents. Les nommer par déduction sémantique serait une hypothèse. Deux lectures
indépendantes les fixent :

1. **Les noms de paramètres de la signature native.**
   `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetHealTargets` appelle
   `DSLSelectors$$AdjacentFriends(this, unit = <sel+0x48>, unitTile = <sel+0x50>, 1)` — la signature
   nomme le 2ᵉ argument `unit` et le 3ᵉ `unitTile`. Donc `+0x48` = l'unité, `+0x50` = **sa tuile**.
   (`BladeOfMagnusAbility$$GetAdjacentTargets` fait le même appel avec le couple `+0x60`/`+0x78`.)

2. **La carte `DSLFactory`, déjà documentée, à décalage CONSTANT.** Le mapping de
   `entities/selectors/accessors.py::ActiveTarget` (`factory+0x148 Owner · 0x158 Actor · 0x160
   Caster · 0x168 CasterTile · 0x170 CasterTiles · 0x178 Target · 0x180 ActiveTarget · 0x190
   TargetTiles`) est celui de `DSLSelectors` **décalé de 0x118**, sans exception :

   | `DSLSelectors` | `DSLFactory` | rôle |
   |---|---|---|
   | `+0x30` | `+0x148` | `Owner` |
   | `+0x40` | `+0x158` | `Actor` |
   | `+0x48` | `+0x160` | **`Caster`** |
   | `+0x50` | `+0x168` | **`CasterTile`** |
   | `+0x58` | `+0x170` | `CasterTiles` |
   | `+0x60` | `+0x178` | `Target` |
   | `+0x68` | `+0x180` | `ActiveTarget` |
   | `+0x78` | `+0x190` | `TargetTiles` |

   Contrôle croisé : `RevitalizingMalignancyAbility$$GetAllHealTargets` (déjà portée) fait
   `Friends(of = Owner@0x30, AdjacentUnits(CasterTiles@0x58)) + Owner@0x30` — cohérent avec la table.
   `RelentlessMarchAbility$$CreateBehaviour` (triggered) fait, lui, `Friends(of = Owner@0x30,
   AdjacentUnits(Owner@0x30))` : `AdjacentTiles` accepte les deux domaines (entité ou tuile).

## 4. Le port

`engine/runner/abilities/admec.py` (module de la faction du porteur, à côté de `RadBombardment`) :

```
defend_the_divine_work_adjacent_friends()  = Friends(AdjacentUnits(CasterTile(), 1), Caster())
defend_the_divine_work_heal_targets()      = Union(<ci-dessus>, Caster())
defend_the_divine_work_repair_tree(amount) = AtomicGroup(Repair(<heal_targets>, amount,
                                                                guard=None, scope=0,
                                                                remove_effects=True))
DefendTheDivineWorkAbility.execute_behaviour = <repair_tree>.execute(...)          # ExecuteAtomic
                                             + galvanic_field_attack_behavior(...)  # Execute
```

Doctrine #149 respectée : la structure de l'arbre et les sélecteurs sont **déclaratifs** (nœuds DSL
du vocabulaire existant — aucun nœud neuf n'a été nécessaire) ; `RepairUnitOperation` et
`AddEffectOperation`/`apply_stat_override` restent **impératifs**, sous les feuilles.

`guard = None` sur la feuille `Repair` : le natif ne pré-filtre PAS ce sélecteur (aucun `Healable` /
`Repairable` autour), exactement comme `RepairAbility$$CreateBehaviour` — c'est le gate
`AttackQuery$$EntityCanBeRepaired` **de l'Operation** qui tranche, là où le natif le place.

### `CreateAttackBehavior` devient une fonction MODULE — parce que le natif en est une

`Repair_GalvanicFieldAbility$$CreateAttackBehavior(dsl, actingUnits)` prend le **`dsl`** en `this`,
pas l'ability : c'est une fonction partagée, et 1117 en est le **second appelant natif**. Le port la
sort donc de `Repair_GalvanicFieldAbility` vers `abilities/repair.py::galvanic_field_attack_behavior`,
paramétrée par un sélecteur d'unités agissantes :

| appelant | `actingUnits` |
|---|---|
| `Repair_GalvanicFieldAbility$$CreateBehaviour` (1119) | `<Target@0x60> - <Caster@0x48>` |
| `DefendTheDivineWorkAbility$$ExecuteBehaviour` (1117) | `Friends(Caster@0x48, AdjacentUnits(CasterTile@0x50))` |

Le corps, lui, est **inchangé** et reste le mirror de #299 : `UnitsAffectedByHealType(acting, 1)`
puis `AddStatOverrideEffect(1242) → PerformAIAttackFromCurrentPosition → RemoveEffect(1242)`
(net-zéro). Le filtre `UnitsAffectedByHealType` est désormais le **nœud DSL natif** plutôt qu'un test
impératif par unité — gain de fidélité au passage, à comportement identique pour 1119 (vérifié :
`test_repair_execution_live.py` 7/7 vert).

### Registre — les deux données obligatoires, dans le même commit

`DefendTheDivineWorkAbility$$.ctor` (surcharge « FLAGS DIRECTS » à 7 arguments — le littéral EST donc
le masque effectif ; le `TargetingRange` recopié est le **même champ statique** que celui de
`RepairAbility$$.ctor`) :

```
TargetingOptions..ctor(&opts, isSelfCasting = 1, &<TargetingRange statics>+0x30,
                       forceMeleeTarget = 1, rules = 0x8c02, 0, 0)
AActiveAbility..ctor(this, &opts, 2)                     # AbilityAttackType.Others
```

`0x8c02`, décomposition exhaustive (aucun bit résiduel) :

| bit | valeur | règle | statut dans le port |
|---|---|---|---|
| 1 | `0x2` | `TargetMatchesDynamicRule` | **portée** — `get_dynamic_invalid_target_reason` (mirror ci-dessous) |
| 10 | `0x400` | `TargetIsFriendly` | **portée** — refuse toute cible ennemie |
| 11 | `0x800` | `AddCasterIfAtLeastOneTarget` | règle d'AJOUT, pas de refus → non portée au filtre statique ; sans effet ici (le behaviour s'ancre sur `Caster`/`CasterTile`, jamais sur `Target`) |
| 15 | `0x8000` | `CasterIsPossibleTarget` | LECTURE du masque, jamais un refus |

`GetDynamicInvalidTargetReason` est **proche** de celui de `Repair_GalvanicFieldAbility` mais **pas
identique**, et les différences sont LUES : ici la branche B n'a ni garde `IsUnit(target)`, ni repli
`IsEnemy(...) ? 0x400 : 0`.

```
if (caster != target
    && attackQuery.<slot 2>(target, GetUnitPosition(target, state), GetNormalAttackType(target))) {
    if (UnitExtensions.IsEnemy(target, caster, state))  return 0x400 TargetIsFriendly;
    return UnitExtensions.IsAffectedByHealType(target, 1) ? 0 : 1 ValidRequest;
}
return attackQuery.<slot 0x13>(target, 0, true) ? 0 : 0x10000 TargetIsRepairable;
```

## 5. Ce qui est MESURÉ live (et ce que chaque régime prouve seul)

Montage : `admecManipulus` (caster) + `admecRuststalker` (allié mécanique, amené au contact) +
`admecDestroyer` (allié mécanique **témoin négatif**, éloigné à ≥ 3 hex), board `MC1_67`, seed 777,
positions CONDUITES. `hpToRepair[50] × 180 % = 5983`.

| régime | géométrie | réparation (live = port) | attaques | dégât ennemi (live / port) |
|---|---|---|---|---|
| `repair` | camps éloignés | caster **+5983**, adjacent **+5983**, éloigné **0** | 0 | 0 / 0 |
| `attack` | allié adjacent au contact d'un ennemi, caster non | idem | 1 (l'allié) | **7353 / 7353** |
| `caster` | **caster** au contact d'un ennemi, allié adjacent non | idem | **0** | **0 / 0** |
| `two` | les DEUX alliés adjacents au caster ET au contact | **3 × +5983** | **2** | **18038 / 18038** |

Ce que chaque ligne établit, et qu'aucune autre ne donne :

* `repair` — la garde d'**adjacence** discrimine réellement : même cast, même trait `Mechanical`,
  seule la DISTANCE change, et l'allié éloigné n'est pas réparé. Aucune attaque ne peut partir, donc
  rien ne masque un écart de réparation ;
* `attack` — l'étage 2 **mord** : un ennemi perd des PV, du même montant total des deux côtés ;
* `caster` — **LE test du cas.** Miroir exact du précédent. Contre-épreuve de discriminance :
  `AttackQuery$$HasValidTargets` depuis la tuile courante rend **caster = 1, allié = 0** — le caster
  POUVAIT frapper — et pourtant **aucun ennemi ne perd de PV**. Si le natif passait
  `Friends(...) + Caster` à `CreateAttackBehavior`, ce zéro serait impossible ;
* `two` — **généralisation** : les trois autres régimes ne placent qu'UN allié adjacent, donc un
  port qui ne ferait attaquer que le premier élément du sélecteur (ou qui ne poserait l'override
  que sur lui) y passerait inaperçu. Ici l'`actingUnits` en contient deux, et le caster — qui a
  pourtant **2** cibles valides — reste muet.

## 6. Quirks portés et résidus NOMMÉS

* **Quirk porté, et il CONTREDIT le texte i2.** L'étage 2 ne filtre pas « a effectivement été
  réparé » : `CreateAttackBehavior` n'applique que `UnitsAffectedByHealType(acting, 1)`. Une machine
  amie adjacente **à pleine vie**, que `RepairUnitOperation` REFUSE de réparer (gate
  `EntityCanBeRepaired` → `IsDamagedUnit`), attaque quand même. L'i2 dit « whenever Actus repairs
  another unit » ; le décompilé fait foi, le port suit le décompilé.
* **Choix de cible de l'attaque gratuite — résidu hérité de #299 / `TheQuickening`.**
  `perform_ai_attack_from_current_position` approxime le choix natif (ennemi le plus proche à
  portée) au lieu d'invoquer le moteur d'utilité. MESURÉ sur le régime `attack` : le port frappe
  `orksWarboss` là où le natif frappe `orksKillaKan` — **même montant total**, victime différente.
  Sur `two`, la RÉPARTITION diffère aussi (port : 18038 sur un seul ennemi ; natif : 7795 + 10243),
  pour un total identique. Les tests verrouillent donc le montant TOTAL et l'identité de
  l'ATTAQUANT, jamais celle de la victime.
* **`groupType = 0x2a` d'`ExecuteAtomic`** : donnée de VUE (`DSLBehaviors$$AtomicGroup`), sans
  observable d'état porté — `AtomicGroup` est un pass-through côté port (RE #201).
* **`source` / `AbilityOrEffect(1117)`** de la feuille `Repair` : l'attribution n'a pas d'observable
  d'état porté (même statut que sur tous les autres call-sites de `DSLBehaviors$$Repair`).
### NON COUVERT (explicitement)

* **Un allié adjacent NON mécanique.** Aucune unité du montage n'échappe à
  `IsAffectedByHealType(., 1)` : les cinq unités présentes portent `Mechanical`. Le filtre
  `UnitsAffectedByHealType(acting, 1)` de l'étage 2 n'est donc **jamais exercé négativement ici** —
  il l'est en revanche par 1119, dont les tests couvrent ce disjunct
  (`test_repair_execution_live.py::test_repair_refuses_a_non_mechanical_target`).
* **Le quirk « pleine vie » de l'étage 2** (§6, 1ᵉʳ point) : lu au décompilé, mais aucun montage ne
  le joue. Il demanderait un allié adjacent mécanique **à 100 % de PV** pendant que le caster est
  blessé — faisable au `--unit-stat`, non fait ici.
* **Plus de deux alliés adjacents**, et l'ORDRE des attaques quand ils sont ≥ 3 (le natif itère le
  sélecteur ; le port aussi, mais rien ne le mesure au-delà de deux).
* **Le montant de l'override `GalvanicField_DmgOverride`** n'est pas isolé par ces tests : il est
  déjà verrouillé côté 1119 (#299) et le port réutilise LE MÊME code (`galvanic_override_amount`).
