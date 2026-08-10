# `#503-r1` — la PHASE 2 de `1141 OverwhelmingWrath` : la triggered `1237`

Build `rnca9r7q6c`. Porteur lineup `worldEightbound` (Azkor), **au pool**. #503 avait porté la face
COMBAT du CAST (trois poses d'effet, **zéro dégât**) et laissé le `2x Eviscerate` du kit à une
TRIGGERED non portée. Cette tranche la porte et la confronte.

## 1. L'artefact, lu en entier

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.OverwhelmingWrath_AttackAbility$$CreateBehaviour(abilityState, triggerType)` :

```
amount  = IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage(this, abilityState)
profile = IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetDamageProfileOrDefault(this, 0x14)
hits    = IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config@+0x20, 0x2f)
target  = IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies(Caster@DSLSelectors+0x48,
                                                                 unique: 1, unitSelectionType: 3)
return    IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage(
              caster = Caster@+0x48, targets = target, amount, Nullable(profile), hits,
              abilityOrEffect = AbilityOrEffect(this), options = <struct ZEROEE>, selectionType = 2)
```

et les deux helpers, corps entiers :

* `$$MinMaxDamage` = `DSLFormulas$$RandomAmount( GetVariableForLevel(0xc = minDmg, abilityState),
  GetVariableForLevel(0xd = maxDmg, abilityState) )` — le mode **BORNES**, pas un dégât-node ;
* `$$GetDamageProfileOrDefault(d)` = `config.GetDamageProfile() ?? d`.

**Aucun `RemoveEffect` ici**, et ce n'est pas un oubli : le retrait appartient au `Triggered()` de
`IdunBattle.Entities.Effects.APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal`, qui
compose `TriggerAbility(...) op_BitwiseAnd RemoveEffect(Effect@DSLSelectors+0x38)`. Contraste **LU**
avec la phase 2 de `1069`, dont le `CreateBehaviour` porte **son propre** `RemoveEffect(1136)`.

## 2. Ce qui manquait vraiment — une classe et **une ligne de table**

L'infrastructure était déjà là (#513) : `runner/operations/triggers/pending_attack.py` porte le
`Triggered()` du foyer commun (`On(0x15 = TurnStart_DelayedAttacks) & IsTurnOf(bondé)` →
`TriggerAbility` & `RemoveEffect`). Le port de `1300` était déjà posé par #503. Il manquait donc
uniquement l'arbre de phase 2 et son inscription — et c'est la raison pour laquelle ce résidu, une
fois le foyer en place, coûte deux fichiers.

La dérivation d'`APendingAttackEffect` est **LUE**, pas déduite du nom :
`...OverwhelmingWrath_PendingAttackEffect$$.ctor` a pour corps entier
`APendingAttackEffect..ctor(this, Nullable(AbilityOrEffect(...)))`, et
`$$GetTriggeredAbilityType` pour corps entier `return 0x4d5`.

## 3. Cinq points de fidélité, tous lus

1. **`MinMaxDamage` est CONSOMMÉE** ici — chez `1069` elle est appelée et **jetée** (aucun registre
   ne porte son résultat au site d'appel). Deux abilities de la même famille, deux réponses.
2. **La config est celle de l'ACTIVE 1141.** `GC.ability("OverwhelmingWrath_Attack")` rend `None` :
   la triggered n'a **aucune** entrée gameconfig, alors que `this@+0x20` est non nul au runtime.
   `OverwhelmingWrath.constants` porte **exactement** `{damageProfile: Eviscerate, nrOfHits: 2}` —
   les deux seules constantes que ce behaviour lit. Le site natif de cette attribution n'est pas
   RE'd (résidu #513-r3, partagé avec 1069).
3. **`GetDamageProfileOrDefault(0x14)`** : le défaut n'est jamais atteint (le kit porte le profil).
   L'écrire en dur serait un fit (résidu #513-r2, partagé).
4. **`is_melee=None`, LU et non choisi.** Les **cinq** surcharges de
   `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` ont été décompilées : toutes
   construisent le même couple `AttackDamageBehaviour` + `AttackBehaviour` à partir de
   `(caster, target, amount, damageProfile, hits, abilityOrEffect, options, selectionType)`, et
   **aucune ne porte de bit melee/ranged** — le constat déjà écrit pour `AttackWithAbilityDamage`.
   Écrire `True` (ce que le porteur mêlée et le sélecteur `AdjacentEnemies` invitent à faire) serait
   une **déduction**. Sur ce profil l'axe perçage est **inerte** (`Eviscerate` =
   `{PiercingRatio: 50}` seul, aucun `ExtraPierceMelee`/`Ranged`) → résidu **#503-r5**.
5. **`multi=True`** — différence **structurelle** avec le cleave de #478. Ici le natif passe le
   sélecteur multi **directement**, donc **un seul** `AttackBehaviour` porte N cibles et son
   `OrderBy(b__5_0)` s'applique (`if (Count > 1) targets.OrderBy(...)`). Le cleave, lui, enveloppe
   chaque cible dans son propre `DSLBehaviors$$Attack` via un `Foreach` — l'`OrderBy` ne s'y
   applique pas, d'où son `multi=False`. Confondre les deux déplacerait la consommation RNG dès
   que deux cibles sont adjacentes.

## 4. La mesure — 5 étages verts, 1 écart de magnitude

`probe_503r1_overwhelming_wrath_phase2.py`, board `MC1_67`, seed 777, placement **forcé**, deux
`endturn` **nus** :

| étage | résultat |
|---|---|
| [1] CAST | port == natif, empreinte d'effets identique |
| [2] TOUR ENNEMI | **rien** ne part, des deux côtés — témoin NÉGATIF |
| [3] TOUR DU PORTEUR | ensembles de cibles **identiques** `{81, 83}` ; `u81` **8761 == 8761** (bit-exact) ; `u83` port **12049** vs natif **10957** |
| [4] EFFETS | `1300` disparaît des deux côtés |
| [5] TIRAGES | **28 == 28** — le flux MT est identique |
| [6] CARDINAL | 2 cibles → `multi=True` **exercé** |

**Ce que ça établit** : structure et rang justes. Le tir part au début du tour du porteur et pas
avant, il frappe exactement les ennemis adjacents au **caster**, l'effet se retire, et le port
consomme **exactement les mêmes tirages** que le natif — donc l'écart restant est un étage
d'**application**, ni de tirage ni de ciblage.

### L'écart, décomposé — résidu `#503-r4`

```
u81  crits [true, false]  rolls [6609, 2152]  armor 2161  ->  8761   == natif
u83  crits [true, true]   rolls [6531, 6162]  armor 2460  ->  12693 brut, 12049 appliqué (TUE)
                                                              natif : 10957 (la cible survit à 1092)
```

Trois causes **éliminées par la mesure** :

* **BLOCK** — `block_chance` de `u83` vaut **0** ;
* **ORDRE des cibles** — s'il était inversé, `u81` recevrait les rolls de `u83` (avec son armure à
  elle) et ne serait pas bit-exact ; il l'est ;
* **un CRIT de trop au 2ᵉ coup** — le surplus de crit mesuré sur `u81` (~4300, écart entre le coup
  crit et la fenêtre non-crit) ne rend pas compte des **1736** manquants sur le 2ᵉ coup de `u83`.

**Ce qui bloque** : la ventilation par coup **native**. `captureEvents: True` sur un `endturn` rend
`{}` — les événements du turn-start ne passent pas par `applyAction`, alors que c'est par ce canal
que #478 avait tranché la même forme de question. Point d'ancrage nommé dans le résidu.

## 5. Trouvé en passant, mesuré, non corrigé — `#503-r3`

`TRIGGERED_ABILITY_BEHAVIOURS` n'est peuplé que par `runner/abilities/handler.py`. En process
**frais**, en n'important que la chaîne trigger (`dispatch/registry.py`) :

```
1134 FullThrottle             présent   (import pour EFFET DE BORD explicite dans registry.py)
1127 SeekerMissile_Attack     ABSENT    (dépend de abilities/tau.py)
1237 OverwhelmingWrath_Attack ABSENT    (dépend de abilities/worldeaters.py)
```

Ce n'est pas théorique : sans le module de phase 2, le `Triggered()` rend `dispatched: False`
**et retire l'effet quand même** — un marqueur qui disparaît sans que rien ne frappe, le régime que
`pending_attack.py` déclare lui-même **pire que le statu quo**. En régime réel le runner charge
`handler`, donc le port fonctionne ; la dépendance reste **implicite**, et elle vaut aussi pour
`1127`, livré par #513.

**Non corrigé, et la raison est une mesure** : les deux arêtes candidates ne sont pas de la même
classe (protocole du CLAUDE.md — charger la cible seule dans un process frais) —
`pending_attack -> worldeaters` est **GRATUITE**, `pending_attack -> tau` est **PORTEUSE**. Hisser
l'une et différer l'autre inscrirait une asymétrie que rien dans le natif ne justifie.

## 6. Ce qui est livré

| Fichier | Contenu |
|---|---|
| `engine/runner/abilities/worldeaters.py` | `overwhelming_wrath_attack_tree()` + `TRIGGERED_ABILITY_BEHAVIOURS[1237]` |
| `engine/runner/operations/triggers/pending_attack.py` | l'entrée `1300 -> 1237` + la §3 (dépendance mesurée) |
| `probe_503r1_overwhelming_wrath_phase2.py` | la MESURE (6 étages) |
| `tests/engine/runner/test_503r1_overwhelming_wrath_phase2_live.py` | la GARDE (9 tests) |

`ABILITY_CLASSES` n'est **pas** touché (`1237` est une TRIGGERED, comme `1127`) : rien à poser côté
`TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE`. `probe_181` rejoué : **141/141, 0 manquante**.

Le garde a été **vu rouge** par mutation adversariale (retrait de l'entrée `1300` de
`PENDING_ATTACK_EFFECTS`) :

```
>       assert len(tirs) == 1
E       assert 0 == 1
E        +  where 0 = len([])
```

Le garde générique de #513 (`test_la_phase2_de_1069_est_inscrite`) itère `PENDING_ATTACK_EFFECTS` :
il couvre donc **automatiquement** toute entrée neuve, y compris celle-ci.

## 7. Ce qui n'est PAS couvert

* **L'écart de magnitude sur la 2ᵉ cible** (`#503-r4`) — décomposé ci-dessus, non localisé.
* **`is_melee`** (`#503-r5`) — le mirror est `None` par lecture ; aucune cible du montage ne porte
  de réducteur gaté `IsRangedAttack`, donc le choix n'est pas discriminé.
* **`GetAttackingUnitSelector`** — ce porteur ne peut pas le trancher : `1300` est posé **sur** le
  caster et bondé **au** caster (les deux slots coïncident). La lecture reste attestée par la mesure
  de #513, où les deux candidats appartiennent à deux **joueurs** différents.
* **La face DÉCISION** (`IdunBattle.AI.Playbook.Loki.OverwhelmingWrathPlaybook`) — hors périmètre,
  inchangée.

## 8. Résidus ouverts par cette tranche

* `#503-r5` — `is_melee` non confronté (contre-épreuve : une cible portant un réducteur gaté RANGED).
* `#503-r3` — `TRIGGERED_ABILITY_BEHAVIOURS` peuplé par une dépendance implicite (vaut aussi pour
  `1127`).
* `#503-r4` — l'écart de magnitude de la 2ᵉ cible.
