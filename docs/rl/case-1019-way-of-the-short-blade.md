# case-1019 — `WayOfTheShortBlade` (tauFarsight) et `SaviorProtocols` (drones T'au)

Deux passifs T'au, **aucun des deux couvert** par `_passive_covered` au commit `bbc3f386`
(ni `ABILITY_TRIGGERS`, ni `ABILITY_INIT_OWNER_EFFECTS`, ni `CUSTOM_NORMAL_ATTACK_BY_PASSIVE`, ni
`RELIC_ABILITY_TRIGGERS`, ni `IMPERATIVE_ABILITY_VECTORS`, ni effet nommé d'après eux — les six
voies vérifiées en exécutant le prédicat).
RE : décompilé ghidra, build `rnca9r7q6c`. Numéro alloué par
`probe_468_collision_numeros.py --suggere` → **#1019**.

---

## 0. Ce que la gate de confrontabilité a réellement mesuré

Le brief annonçait `tauFarsight` comme porteur **`lineup` donc direct**. **Faux, et re-mesuré ici** :
`rl_duel.py build --list-pool` ne contient que **cinq** T'au réguliers — `tauAunShi`, `tauCrisis`,
`tauDarkstrider`, `tauMarksman`, `tauShadowsun` (+ `tauBroadside` en MoW). `tauFarsight` en est
absent : c'est un `L~` (lineup hors pool), donc **injection catalogue**.

**L'injection FONCTIONNE, mesurée** :

```
python catalog_inject.py --units tauFarsight --out <abs>.json
  -> catalogue Units 175 -> 176 ; 2 configs d'ability ajoutées : ExemplarOfTheMontka, WayOfTheShortBlade
python rl_duel.py build --seed 777 --board MC1_67 --seed-bc <abs>.json \
       --p-units tauFarsight,tauCrisis,tauMarksman --a-units ultraTitus,ultraCalgar
```

Aucun `data/unspawnable_rank*.json` n'existe dans l'arbre → aucun refus légitime.

**Et le porteur n'est PAS le facteur limitant de ce lot** — c'est l'ÉTAGE (§4). Le passif dont le
porteur est *gratuit* (`SaviorProtocols`, summons atteignables via `tauMarksman`) est celui dont la
mécanique est **bloquée**, et l'inverse pour `WayOfTheShortBlade`.

---

## 1. `WayOfTheShortBlade` — l'artefact natif

Quatre classes, deux effets ; l'appariement est **lu**, pas déduit du nom.

| classe native | rôle |
|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WayOfTheShortBlade_InitAbility` | pose les DEUX effets sur le porteur |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WayOfTheShortBlade_AttackAbility` | l'attaque supplémentaire |
| `IdunBattle.Entities.Effects.Loki.WayOfTheShortBladeEffect` | effet `0x5db` = 1499 `WayOfTheShortBlade_DamageBuff` |
| `IdunBattle.Entities.Effects.Loki.WayOfTheShortBlade_AdditionalAttackMarkerEffect` | effet `0x5dc` = 1500 `..._AdditionalAttackMarker` |

```
WayOfTheShortBlade_InitAbility$$CreateTrigger   = OnOwnerSpecificAbilityInit(this.AbilityType)
WayOfTheShortBlade_InitAbility$$CreateBehaviour = AddEffect(0x5db, AbilityStateReference,
                                                            source = Owner@<DSLSelectors+0x30>,
                                                            targets = Owner@<+0x30>, turns = <zeroe>)
                                                & AddEffect(0x5dc, ..., targets = Owner@<+0x30>, ...)
```

**Les deux effets vivent sur FARSIGHT** et se projettent par leur propre `CreateTargetSelector` —
canal AURA côté SOURCE, patron `DefenderOfTheGreaterGood_ExtraDmg`. **CONFIRMÉ LIVE** (runner
`--seed-bc`, MC1_67, seed 777) : `decisionView.effects` porte
`WayOfTheShortBlade_DamageBuff` + `WayOfTheShortBlade_AdditionalAttackMarker` sur **`u81
[tauFarsight]` et sur personne d'autre**, alors que deux autres T'au (`tauCrisis` @dist 1,
`tauMarksman` @dist 1) étaient à portée. C'est ce qui **réfute** le modèle « effet posé sur les
bénéficiaires » et impose le canal aura.

---

## 2. Effet 1499 `WayOfTheShortBlade_DamageBuff` — PORTÉ

```
WayOfTheShortBladeEffect$$CreateTargetSelector =
    A = UnitsWithTrait( SurroundingFriends(Owner@<+0x30>, range = GetNumberConstant(0x16), 1, 3),
                        0x10 = UnitTrait.Hero, 3 )
    Unique( UnitsWithRangedWeapons(A)  op_Addition  UnitsFromFaction(A, 9 = UnitFaction.Tau, 3) )

WayOfTheShortBladeEffect$$IsValidAttackForBonus =
    get_OwnerIsCaster & IsNormalAttack & IsRangedAttack
      & !CurrentAttackDamageProfileIs(0xd = DamageProfileType.Psychic)
      & AmountIsGreaterThanZero( UnitsWithTrait( Friends(Owner@<+0x30>,
                                                         AdjacentUnits(Target@<+0x60>, 1, 3), 3),
                                                 0x10 = Hero, 3 ) )

WayOfTheShortBladeEffect$$CreateEffectDamageBonusForAttack =
    EffectBonus.ForPercentIncrease( IsValidAttackForBonus(),
                                    ConfigVar(0xa = extraDmgPct, GetAbilityState(this), cfg@+0x60) )

WayOfTheShortBladeEffect$$IgnoreArmor =
    ConfigVar(0x40 = armorIgnored, GetAbilityState(this), cfg@+0x60)
```

**Trois lectures qui ne se devinent pas**

1. **`SurroundingFriends` exclut le porteur, et ce sélecteur-ci n'ajoute PAS `+ Owner`** —
   contrairement à celui de 1500, qui l'ajoute explicitement (§3). Farsight ne reçoit donc **pas**
   son propre bonus de dégât (« of **other** friendly Characters » à l'i2). Les deux sélecteurs se
   ressemblent à un nœud près, et ce nœud change **qui** est concerné : recopier l'un sur l'autre
   donne un bénéficiaire de plus, silencieusement.
2. **UNION, pas intersection** : `UnitsWithRangedWeapons(A) + UnitsFromFaction(A, Tau)` puis
   `Unique`. Un T'au **sans** arme de portée est donc buffé — cohérent, puisque 1500 va lui faire
   tirer une attaque normale à distance. 1500, lui, utilise `UnitsFromFaction` en **intersection**.
   Même vocabulaire, sémantique opposée.
3. **`range` est la CONSTANTE `0x16` du gameconfig** (`AbilityConstantType.range` = 2), pas un
   littéral DSL.

**Le corps de `IgnoreArmor` est PARTAGÉ** (RVA `1059b60`, 6 xrefs DATA / 0 CODE = six slots de
vtable). #1008 l'attribue à `Helspear_IgnoreArmorEffect` par contiguïté d'émission ; la table, elle,
nomme `WayOfTheShortBladeEffect`. Les deux lectures **coïncident** — même corps
`ConfigVar(0x40 = armorIgnored)`, et les deux gameconfigs portent bien cette variable.

`extraDmgPct` n'est **pas** dans `variablesAffectedByRarityBonus` (`armorIgnored` l'est, seul) :
`ability_var` applique le multiplicateur de rareté à l'un et pas à l'autre, sans code dédié.

### Le nœud qui n'avait AUCUN canal

`AmountIsGreaterThanZero( UnitsWithTrait( Friends(Owner, AdjacentUnits(Target)), Hero ) )` est le
terme **discriminant** (« against enemies that are adjacent to a friendly Character »). Le ctx
d'aura ne publiait **rien** sur le voisinage de la CIBLE : sans canal, le gate serait fermé en
permanence et l'effet **inerte** — un port qui se lit comme fait et ne change rien.

Clé **scalaire** (un COMPTE, pas un booléen — le natif écrit `AmountIsGreaterThanZero`) et
**tri-état** ajoutée aux **deux** foyers, additive (aucune classe existante ne la lit) :

* COMBAT — `engine/runner/damage_model.py::_friend_heroes_adjacent_to`
* PRÉDICTION — `engine/playbook/prediction/_shared.py::_friend_heroes_adjacent_to`

`None` = question **non posée** (pas de cible, pas de position, équipe inconnue), jamais `0` : le
lecteur **ferme** son gate sur `None`. L'adjacence est celle du natif (`battle_query.is_adjacent` =
liste stockée du `ConnectivityComponent` + porte `|dElev| < 2`), pas `hexgeo.distance == 1`
(#271 / #943-r7).

---

## 3. Effet 1500 `..._AdditionalAttackMarker` + `WayOfTheShortBlade_AttackAbility` — RÉSIDU `#1019-r2`

```
WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateTargetSelector =
    UnitsFromFaction( UnitsWithTrait( SurroundingFriends(Owner@<+0x30>, range, 1, 3), 0x10 = Hero, 3),
                      9 = UnitFaction.Tau, 3 )
    op_Addition  Owner@<+0x30>
WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateActiveCondition = <DSLTriggers+0x40>  (VRAI constant)
WayOfTheShortBlade_AdditionalAttackMarkerEffect$$.ctor = BaseEffect(AbilityOrEffect(<lit>), hasAutomaticActivation = 1)

WayOfTheShortBlade_AttackAbility$$CreateTrigger =
    On(0x9 = EventTriggerType.Attack, <bool>) & IsMeleeAttack()
      & AreFriends(Caster@<+0x48>, Owner@<+0x30>)
      & IsEffectTarget(Caster@<+0x48>, 0x5dc = 1500)

WayOfTheShortBlade_AttackAbility$$CreateBehaviour =
    AddFlag(Caster@<+0x48>, 0x15 = UnitFlag.ForceRangedAttack)
      & UseNormalAttackIfAble(caster = Caster@<+0x48>, target = Target@<+0x60>,
                              parentAbility = <vide>, triggerAbilityOrEffect = <vide>,
                              options{+0x8 = 0x0101})
      & RemoveFlag(Caster@<+0x48>, 0x15)
```

**`0x15` = `UnitFlag.ForceRangedAttack` (21)** — c'est *exactement* le « even if they are adjacent
to it » de l'i2, et c'est ce qui rend le triptyque `AddFlag / UseNormalAttackIfAble / RemoveFlag`
lisible : sans le flag, `UseNormalAttackIfAble` retomberait sur l'arme de mêlée au contact.

**Ce que le port a déjà** : `On(Attack = 9)` a **deux** émetteurs
(`triggers/dispatch/attack.py`), `UseNormalAttackIfAble` est portée
(`runner/abilities/behaviours/combat.py`), `UnitFlag.ForceRangedAttack` existe
(`entities/unit_flag.py`). Ce module pose déjà la classe d'effet 1500 avec son sélecteur mirroré
(`aura_selector_covers`) — c'est-à-dire le prédicat `IsEffectTarget(Caster, 1500)` sous forme
calculable. Ce qui reste : la classe `TriggeredAbility` + son entrée `ABILITY_TRIGGERS`, et
l'exercice live du flag `ForceRangedAttack` (aucun porteur porté ne l'arme aujourd'hui).

**Porteur confrontable identifié** : `tauAunShi` est T'au, `Hero`, **au pool**, et n'a qu'**une**
arme (pas de portée) → il attaque en mêlée, donc il déclenche le marqueur. C'est le montage à jouer.

---

## 4. `SaviorProtocols` — RE complète, port BLOQUÉ par deux étages (résidu `#1019-r3`)

Face **DÉCISION** déjà portée (#443 / #443-r1, `engine/playbook/savior_protocols.py`) : les deux
faces ATTACK et MOVE. Ce qui manque est la face **COMBAT**.

```
SaviorProtocolsAbility$$CreateTrigger =
    On(0x39 = EventTriggerType.PreDamageTaken)
      & TargetIsValidTrigger()
      & IsAdjacent(Owner@<DSLSelectors+0x30>, Target@<+0x60>)
      & !TriggeringAbilityIs(<AbilityOrEffect A>)
      & !TriggeringAbilityIs(<AbilityOrEffect B>)

SaviorProtocolsAbility$$TargetIsValidTrigger =            // PARTAGÉ avec la face MOVE (#443-r1)
    AreFriends(Target@<+0x60>, Owner@<+0x30>)
      & HasFaction(Target, 9 = UnitFaction.Tau, 3)
      & !ActorHasTriggeredAbility(Target, 0x460 = 1120 SaviorProtocols)
      & !AreEqual(Target, Owner)

SaviorProtocolsAbility$$CreateBehaviour =
    If( Maybe( ConfigConst(0x2a = AbilityConstantType.chance, cfg) ),      // gameconfig : chance = 50
        TransferDamage( caster        = Caster@<+0x48>,
                        originalTarget= Target@<+0x60>,
                        transferTarget= Owner@<+0x30>,                     // le DRONE
                        transferAbility = <DSLSelectors+0x88>,
                        attackAbility   = <DSLSelectors+0x90> ),
        null )
```

**La chaîne impérative, lue jusqu'au bout** :

```
DSLBehaviors$$TransferDamage -> TransferDamageBehaviour$$.ctor(caster, originalTarget,
                                    transferTarget, transferAbility, attackAbility)
TransferDamageBehaviour$$Execute -> Core.Services.OperationProcessor$$TransferDamage(
                                    ..., hitIndex)                 // slot 68 de l'interface
                                 -> IdunBattle.Operations.TransferDamageOperation$$Execute
```

et le point clé, dans `IdunBattle.Operations.TransferDamageOperation$$GetDamage` :

```
d = <pendingDamageComponent>+0x64        // Nullable<DamageAppliedResult>
if (!d.HasValue) return null;
dmg = DamageAppliedResult.get_Damage(d.Value);
*(qword*)(comp+0x64) = 0;                // <-- LA VALEUR PENDANTE EST **CONSOMMÉE** (mise à null)
*(qword*)(comp+0x6c) = 0;
return new Damage(d.Value.<+0x00>, dmg);
```

Puis `Execute` boucle sur `transferTargets`, émet un pas de flux `0x23`
(`StepType.TransferDamage = 35`) portant `{0xb4: originalTarget, 0xb7: transferTargets,
0xb8: transferTarget}`, et appelle le slot **`0x40` = `DirectDamage`** (6 arguments) sur le drone.
**La redirection n'est donc pas un « bonus » : c'est une consommation** — le dégât en attente sur la
cible originale est mis à `null`, donc `ApplyDamageOperation` n'en applique plus rien.

### Les deux étages qui bloquent, et le rayon de souffle

1. **La granularité.** Le natif transfère **par COUP** (`hitIndex` est un paramètre de
   `OperationProcessor$$TransferDamage`, et `On(PreDamageTaken)` est émis par coup dans
   `ApplyDamageOperation$$Execute`). Le port n'a qu'un chokepoint **par GROUPE** —
   `engine/runner/operations/damage.py::_apply_damage_pipeline` le dit lui-même : « le natif émet
   PAR COUP, le port a un chokepoint PAR GROUPE ». Or l'i2 dit « X % chance **for each hit** ».
2. **L'irréversibilité du dégât pendant.** Côté port, `pre_damage_taken_triggers(...)` est appelé
   et **son retour est jeté**, puis `applied = thc.reduce(total)` deux lignes plus bas. Il n'existe
   aucun canal par lequel un trigger `PreDamageTaken` puisse **annuler** ou **détourner** le dégât.
   Le seul consommateur porté de ce vecteur (`GeminaeSuperia`, #963) n'en avait pas besoin.

**Rayon de souffle mesuré** : les deux réparations vivent dans
`engine/runner/operations/damage.py::_apply_damage_pipeline`, **le chokepoint de dégât partagé par
les quatre vecteurs de dégât**. Passer l'émission de `PreDamageTaken` de « par groupe » à « par
coup » change aussi le régime de `GeminaeSuperia` (son `IsFirstDamagingHitInSeries` et son cap
`SummonLimit` deviennent évalués N fois). Ce n'est **pas** une tranche bornée : c'est une tranche
d'ÉTAGE, à mener seule.

`#963-r3` nommait déjà ce trou (« Le transfert de dégât … `TransferDamage` reste à porter »).
Ce case-doc lui apporte la RE complète du côté `SaviorProtocols` et la mesure du blocage.

**Ce qui reste NON LU** : les deux constantes des `!TriggeringAbilityIs(...)`. Le décompilé perd
l'argument de `IdunBattle.Core.AbilityOrEffect$$op_Implicit` (buffer de retour seul visible) ;
`read_bytes` plafonne à 32 octets par appel et la fonction en fait 416. À reprendre par lecture
d'octets chaînée ou par un `set_function_prototype` sur l'`op_Implicit` concerné.

---

## 5. Ce qui n'est PAS couvert par cette tranche

* **`#1019-r1`** — la pénétration d'armure de 1499 (`ConfigVar(0x40 = armorIgnored)`) est **exposée
  et non branchée** : `BaseEffect.get_armor_penetration` n'est appelé que par
  `_attacker_effect_bonuses` (les effets de l'ATTAQUANT), or cet effet vit sur Farsight et n'entre
  que par les agrégateurs d'AURA, qui n'ont aucun canal armure côté attaquant. Même étage que
  `#1008-r2`, pris par l'autre face. `get_armor_penetration` **n'est délibérément pas surchargé** :
  le trou reste visible au lieu d'être un no-op qui se lit comme « porté ». Conséquence
  arithmétique réelle : le port rend le `+extraDmgPct %` mais pas les `armorIgnored` points de
  perçage.
* **`#1019-r2`** — 1500 + `WayOfTheShortBlade_AttackAbility` (§3).
* **`#1019-r3`** — `SaviorProtocols` face COMBAT (§4).
* **La CONFRONTATION LIVE de la valeur de dégât de 1499 n'a PAS été jouée** — voir §6.

---

## 6. État de la validation

**FAIT, live** : le montage d'injection (`catalog_inject --units tauFarsight` + `build --seed-bc`)
fonctionne, et le régime de POSE des deux effets est **confronté** — ils sont sur Farsight et sur
lui seul. C'est ce qui a tranché la forme du port (aura côté source vs effet sur le bénéficiaire).

**NON FAIT** : la confrontation de la **valeur** (`+extraDmgPct %` sur une attaque normale à
distance d'un T'au `Hero` à ≤ 2 hexes de Farsight, contre un ennemi ayant un `Hero` ami adjacent).
Le montage exact, prêt à jouer :

```
python catalog_inject.py --units tauFarsight --out <abs>.json
python rl_duel.py build --seed 777 --board MC1_67 --state-file <abs unique>.json \
       --seed-bc <abs>.json --p-units tauFarsight,tauCrisis,tauMarksman --a-units ultraTitus,ultraCalgar
# DÉPLACER : tauCrisis à <= 2 hexes de tauFarsight ET à portée 2 de ultraTitus ;
#            tauMarksman ADJACENT à ultraTitus (c'est lui, le « friendly Character adjacent »)
# puis : comparer la prédiction du port (`view`, PLANS D'ATTAQUE) au dégât RÉELLEMENT appliqué
#        par `act` — et rejouer le même coup avec tauMarksman DÉPLACÉ hors adjacence (la
#        bascule du gate discriminant), plus une contre-épreuve « effet muté » qui doit ROUGIR.
```

Le discriminant est **la position de `tauMarksman`**, pas la géométrie de spawn : les deux régimes
s'obtiennent en déplaçant une unité d'un hex.
