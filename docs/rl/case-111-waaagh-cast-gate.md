# case-111 — « Waaagh (1058) inerte en runner isolé » : c'était le GATE DE CIBLAGE

**Verdict : l'ability n'est pas inerte, et le runner isolé monte tout ce qu'il faut.** Le natif
sort AVANT son premier étage de pose, à la validation de cible de `ActiveAbilityOperation`, parce
que la cible passée n'était pas une cible légale de Waaagh. Sur une cible légale, les cinq étages
de `WaaaghAbility$$ExecuteBehaviour` s'exécutent et les trois buffs survivent.

---

## 1. Le symptôme

`applyAction {kind:"ability", casterId:<orksWarboss>, targetId:<orksWarboss>, abilityType:1058}` :

```
ok=true  mutated=false  actionConsumed=false  spawned=0  eventCount=2
events = [ {kind:"group", group:12, entity:<caster>, source:"Waaagh"}, {kind:"finish"} ]
```

Aucun des trois buffs (1099 `Waaagh_ExtraMovement`, 1100 `Waaagh_ExtraDamage`,
1101 `Waaagh_ExtraHits`) n'est posé — ni sur le caster, ni sur l'allié adjacent. Idem au tour
suivant sans déplacement, idem en ciblant une tuile.

`mutated=false` **avec** des événements émis avait été lu comme « le behaviour s'exécute mais la
mutation se perd ». C'est l'inverse : rien du behaviour ne s'est exécuté.

## 2. Le critère : le natif atteint-il son étage de pose ?

**NON — il sort avant.** L'étage exact :

```
IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal
  -> IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget       (retour non nul => return 0)
  -> IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidTargetReason
  -> IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetDynamicInvalidTargetReason
```

`GetDynamicInvalidTargetReason` — mirror du décompilé :

```
tiles = WaaaghAbility.GetPossibleMovementTiles( Get(target) )
ents  = AbilityEntities(caster, caster, target, ...)
return Count( tiles.Evaluate(ents) ) > 0 ? 0 : 0x8000000
```

où `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetPossibleMovementTiles` =
`IdunBattleLogic.Entities.DSLFactory$$TilesUnitCanMoveToChargeTarget(caster, casterTile, target,
UnitMovementRangeWithBonus(caster, 1099, Direct(extraMovement)), canReachOnly=0)`
= `CanAddUnit(AdjacentTiles(target)) op_And MovableTilesInRange(caster, casterTile, range, 0)`.

**Ce que le prédicat exige** : il existe au moins une tuile LIBRE et marchable, hex-adjacente à la
cible, atteignable par le caster en `MOVEMENT + extraMovement` pas. Autrement dit : la cible doit
être **chargeable ce tour-ci, sans bouger d'abord**. S'y ajoute le filtre statique des
`TargetingOptions` posées par `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$.ctor`
(cible ENNEMIE) — mesuré ci-dessous comme un rejet distinct.

`ExecuteInternal` rend `0` à ce point, en amont des cinq `AActiveAbility.Execute` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour`, et donc aussi en
amont de `AddFlagsAfterAbilityExecution` — d'où `actionConsumed=false`.

**Le groupe 12 n'est pas émis par l'ability.** `GroupType 12 = User_UseAbility` est ouvert par le
handler de message AVANT le gate, puis refermé aussitôt. La signature à 2 événements
`[group User_UseAbility, finish]` est donc *exactement* la trace d'un refus de cible — jamais celle
d'un behaviour qui aurait tourné à vide.

## 3. Décomposition — mesure (session 78, build `gqfc5mff6c`, board MC1_67, seed 777)

`probe_111_waaagh_gate.py` : même caster, même état, seule la **cible** change. Warboss amené à
portée de charge (`abilityTargets.fromHere` de 1058 non vide), puis quatre casts successifs.

| cible | ok | mutated | actionConsumed | spawned | events | groups |
|---|---|---|---|---|---|---|
| A — le CASTER lui-même | true | **false** | **false** | 0 | 2 | `{12}` |
| B — un ALLIÉ (`orksNob`) | true | **false** | **false** | 0 | 2 | `{12}` |
| C — un ENNEMI hors portée de charge | true | **false** | **false** | 0 | 2 | `{12}` |
| D — un ENNEMI offert par `fromHere` | true | **true** | **true** | 2 | 210 | `{1,5,6,11,12,21,22,26,32,34,35,37,40,42,61}` |

A/B isolent le filtre statique (cible non ennemie), C isole le gate dynamique
(`GetDynamicInvalidTargetReason`) : ils sont bien **deux rejets distincts**, mais avec la **même**
observable — d'où la confusion initiale.

Sur D, les cinq groupes d'étage de `ExecuteBehaviour` sont tous présents :
`0x22 = 34` (Spawn), `0x25 = 37` (buff), `0x23 = 35` (charge), `0x20 = 32` (attaque), `0x28 = 40`
(PerformAIAction). Reproduit à l'identique sur deux runners (402, 429).

**Pose, après D** — elle survit et est lisible dans `decisionView.effects` :

| unité | distance au caster | `Waaagh_*` |
|---|---|---|
| `orksWarboss` (caster) | 0 | ExtraMovement, ExtraDamage, ExtraHits |
| `orksNob` (allié Ork, jamais bougé) | 8 hex | ExtraMovement, ExtraDamage, ExtraHits |
| `orksNpc2OrkBoy` ×2 (invoqués à l'étage 1) | adjacents | ExtraMovement, ExtraDamage, ExtraHits |

L'allié Ork à 8 hex confirme le sélecteur board-wide
`UnitsFromFaction(Friends(caster, allUnits), 5=Orks)` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffedUnitsSelector`.

> **Détail de nommage** : le summon a pour `visualId` **`orksNpc2OrkBoy`**, alors que la constante
> lue par l'ability est `GetStringConstant(0) = "orksOrkBoys"` (l'`unitId`). Chercher les Ork Boyz
> par `visualId == "orksOrkBoys"` ne rend rien — piège rencontré au premier probe.

## 4. La recette de cast (ce que tout appelant doit faire)

Prendre la cible dans **`abilityTargets(...).fromHere`** — « légalité EXACTE du cast immédiat » —
et **pas** dans `targets`, qui est le superset « ce tour, déplacement INCLUS ». Une cible de
`targets \ fromHere` n'est castable qu'APRÈS un déplacement : `applyAction` (qui ne bouge pas) y
rendrait un no-op moteur, c'est-à-dire de nouveau le symptôme de ce cas.

## 5. Conséquences sur les consommateurs

- **`probe_106_waaagh_splash.py`** castait `targetId = <le Warboss lui-même>` : no-op garanti, puis
  sortie en « NON DISCRIMINANT: le psyker ne porte pas Waaagh_ExtraDamage ». Corrigé (cible lue dans
  `fromHere`) **et** la boucle d'approche exige désormais que le Warboss ait lui aussi une cible
  légale, sans quoi elle « réussissait » sur la seule géométrie du psyker. Le probe converge et rend
  un verdict discriminant : splash ranged `live=1335`, `port=1335`, `legacy=1004`.
- **`test_waaagh_buff_contrib_live.py` (#95)** cherchait déjà une cible légale (7/7 verts avant comme
  après) mais piochait dans `targets` : durci sur `fromHere`, `targets` en repli. Sans ce durcissement
  une géométrie où `targets ⊋ fromHere` aurait donné un `pytest.skip` vert sans rien valider.
- **`#PAI-c`** : le 5ᵉ étage `PerformAIAction` s'exécute bien (groupe 40 présent, les deux Ork Boyz
  jouent dans la foulée du cast) — la face est exerçable.

## 6. Tests

`tests/engine/runner/test_waaagh_cast_gate_live.py` (6 tests) garde les DEUX faces :

- refus : pour chacune des trois cibles illégales, `mutated=false` ET `actionConsumed=false` ;
- refus : la trace ne contient QUE le groupe `User_UseAbility` (`eventCount == 2`) — aucun groupe
  d'étage de l'ability, donc le refus est bien en amont ;
- exécution : cible `fromHere` ⇒ `mutated`, `actionConsumed`, `spawned >= 1`, groupes `0x22` et
  `0x25` présents ;
- exécution : les trois effets sur le caster, sur l'allié Ork **loin** (assertion préalable
  `distance > 1`, sinon le buff pourrait venir d'`AdjacentFriends` et le test ne testerait plus le
  sélecteur board-wide) et sur les summons.

## 7. Ce qui n'est PAS couvert

- **Le port n'a AUCUN gate de cible.** `AbilityHandler.visit_ActiveAbilityMessage` ne mirror de
  `ExecuteInternal` que le gate ACTEUR-MORT (#70) ; ni `IsInvalidTarget`, ni `IsValidCaster`, ni
  `IsDeadUnitAndNotAllowedByAbility`. Offline, un `ActiveAbilityMessage` Waaagh sur le caster
  lui-même exécuterait le behaviour, là où le natif refuse. Non atteint par les harnais actuels
  (les messages viennent de l'IA native, qui ne produit que des casts légaux) ; le porter
  supposerait `GetDynamicInvalidTargetReason` + `TargetingOptions` par ability — chantier
  transverse, hors périmètre de ce cas. Reporté au backlog.
- **Le reste des rejets de `ExecuteInternal`** n'a pas été décomposé (`IsValidCaster`,
  `IsAbilityBlocked`, cooldown, `IsAllowedToStartInAtomicMode`) : ils partagent l'observable
  « 2 événements » et pourraient être confondus avec un refus de cible.
- **`GroupType 40`** est étiqueté `ResurrectUnit` par `enum_maps` alors qu'il porte ici le 5ᵉ étage
  (`PerformAIAction`). Les quatre autres étages correspondent exactement
  (32 `Ability_Attack`, 34 `Ability_Summon`, 35 `Ability_Move`, 37 `Ability_Stance`) : l'étiquette
  40 est douteuse, non load-bearing, non tranchée ici.
