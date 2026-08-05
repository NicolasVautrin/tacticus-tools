# #448-r3 — le pas de mouvement est ATOMIQUE : on n'observe un marqueur transitoire que de l'INTÉRIEUR

**Statut** : RÉSOLU pour les trois fichiers de garde de la famille `ATeleportingEffect`
(`1036`, `1241`, `1574`). Un quatrième fichier (`r2b`, `1140`) reste rouge **pour une autre
cause**, documentée en §6 et ouverte en `#448-r3-r1`.

## 1. Le symptôme, et pourquoi il accusait le mauvais coupable

Sur `master` propre, trois tests live rougissaient en disant que le port avait **perdu** le
trigger qui pose le marqueur transitoire :

```
AssertionError: T4 n'a pas pose 1036 pendant le pas : [1107, 1112]
AssertionError: T4 n'a pas pose 1241 pendant le pas : [78, 1048, 1134, 1239, 1243]
AssertionError: T4 n'a pas pose 1574 pendant le pas : [1147, 1375]
```

**Le port n'avait rien perdu.** Les trois gardes mesuraient l'état intermédiaire en **découpant**
le pas :

```python
MoveUnitOperation(uid, dest).execute(st, EventBus())   # censé s'arrêter avant le vecteur
mid = <effets de uid>                                  # on lisait le marqueur ICI
after_move_triggers(st, uid)                           # censé jouer la suite
```

C'était le contrat du port au **2026-08-01**. `9767a8e4` (#448-r1-r1-r2-r1, **2026-08-04**) a
**replié le vecteur after-move DANS `MoveUnitOperation.execute`**. Le premier appel joue donc
désormais le pas **entier** : le marqueur est posé *puis retiré* avant qu'on regarde, et
`mid` ne contient plus que les passives d'atterrissage (`1107 PathOfCommand_ExtraCrit`,
`1112 PathOfCommand_ExtraDmg`). Le second appel, lui, **rejouait** un vecteur déjà joué.

## 2. Le repli est le MIRROR — mesuré sur le binaire, pas supposé

Build `rnca9r7q6c`, xrefs lues dans Ghidra :

| symbole | call-sites | où |
|---|---|---|
| `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` | **2** | `MoveUnitOperation$$Execute+0x9de` et `+0x1111` (les 2 autres xrefs sont DATA) |
| `IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers` | **0** | corps **INLINE** dans le même `Execute` |

⇒ le natif publie `On(0x1f = PreUnitMove)` **et** `On(0x04 = UnitAfterMove)` dans le **même**
`Execute`. Le pas est **atomique**, et il en découle un fait structurel qui commande tout le
reste : **aucun état natif RECHARGÉ ne peut porter le marqueur** — il naît et meurt à l'intérieur.
Le réclamer d'un `applyAction` serait exiger un témoin que le natif ne peut pas produire.

La chaîne DSL, lue verbatim (`ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal`) :

```
T4  On(0x1f) & OwnerIsActor & <vslot 0x738> & <vslot 0x748>  ->  GetAddMovingEffectBehaviour
    GetAddMovingEffectBehaviour : GetMovingEffectType() (vslot 0x758)
        HasValue == 0  ->  DSLBehaviors$$Nothing()
        sinon          ->  DSLBehaviors$$AddEffect(<type>, GetAbilityState(), targets, Nullable<int>(1))
    TeleportStrike_TeleportingInEffect$$GetMovingEffectType : local_res18[0] = 0x40c  ->  1036
TeleportMovingEffect$$CreateHandleTriggerAbilitiesInternal
  = UN SEUL Triggered( On(0x04) & OwnerIsActor -> GetRemoveEffectBehaviour() )
```

## 3. Le TÉMOIN NATIF non-nul

`probe_448_r3_move_step_atomicity.py`, étape **E-CASCADE** : la cascade d'events du `applyAction`
(`actions[i].events[]` — **par action**, jamais à la racine), groupes `Effect_Refresh` dont la
`source` est le nom de l'effet. Mesure identique sur les **deux** couples (`MC1_67`/777 et
`C3_26`/31337) :

```
TeleportStrike_Moving : add=[2, 3]   rem=[16, 17]   (ChangePosition a 5)
```

Le natif **active** `1036` avant le déplacement et le **retire** après : le marqueur **encadre**
le `ChangePosition`. C'est exactement ce que fait le port. Les ordinaux de step/group sont résolus
par `stream_events` depuis `data/symbols/<build>/frida/enums.tsv`, jamais en dur (la
renumérotation `gqfc5mff6c -> rnca9r7q6c` avait déjà inversé add/remove en silence).

## 4. Le correctif : un foyer unique, l'observation par INSTRUMENTATION

`probe_448_r3_move_step_atomicity.play_step_instrumented(st, uid, dest)` joue le pas **une seule
fois** et capte l'état à l'entrée du vecteur after-move — le seul point d'observation qui subsiste.
`movement.py` importe `after_move_triggers` **dans le corps** d'`execute`, donc l'attribut est
résolu à l'appel : patcher le module `triggers` le capte. Le spy **délègue** au vrai vecteur (il
observe, il ne remplace pas), donc l'état final reste celui du pas nominal.

Mesure côté port, deux couples :

```
[E-ATOMIC] after_move_triggers appele 1 fois par execute()
[E-MOVING] port, a l'entree du vecteur after-move : [1035, 1036]
[E-END]    port, apres le pas : [1107, 1112]
[E-NATIF]  natif, apres le pas : [1107, 1112]
```

Sites rebranchés sur ce foyer : les 3 tests live (`r2`, `r2c`, `r2d`) et les 4 probes
(`r2`, `r2b`, `r2c`, `r2d`).

## 5. Ce que la correction a AUSSI trouvé : la dégradation était SYMÉTRIQUE

Le découpage périmé ne produisait pas que des faux rouges. Un marqueur posé **puis retiré**
n'apparaît pas davantage dans un `mid` pris après le pas complet — donc **toute assertion
NÉGATIVE passait sans rien exercer** :

- `test_448_r2d::test_a_walk_far_from_the_mark_poses_no_moving_marker` (bras négatif du
  vslot `0x748`) ;
- `probe_448_r2b`, contrôle « aucun `*_Moving` posé » (branche `Nothing()` de T4).

**Démonstration, mesurée** : en collapsant `_custom_moving_condition` à `True` (la régression même
que ce test prétend garder), le test **d'origine** rend `1 failed, 2 passed` — le bras négatif
**passe**. Le test **corrigé** rend le bras négatif **rouge** :

```
AssertionError: le port pose 1574 sur un pas LOIN de la marque :
                le vslot 0x748 est collapse a True ([1147, 1375, 1573, 1574])
```

Un test qui rougit se voit ; un test qui verdit sans rien exercer, non. Le second est le plus
coûteux des deux, et c'est celui que le découpage avait installé en silence.

### Contre-épreuves jouées (une garde qu'on ne sait pas faire échouer ne garde rien)

| mutation | attendu | obtenu |
|---|---|---|
| T4 retiré de `EFFECT_TRIGGERS[1035]` | `test_448_r2` rouge | rouge — `mid = [1035]` |
| `_custom_moving_condition` collapsé à `True` | `test_448_r2d` bras **négatif** rouge | rouge — `mid = [..., 1574]` |
| idem, sur le test **d'origine** | (démonstration du vert-qui-ment) | **VERT** — la garde n'exerçait rien |
| `probe_448_r3 --mutate` | détecte | détecte — `[E-MOVING] [1035]` |

## 6. Résidu — `r2b` / `1140 StormboyzStrike_TeleportingIn` reste ROUGE, autre cause

`test_448_r2b_stormboyz_teleporting_in_live.py` rend **3 failed / 6 passed**, et c'est
**préexistant** : re-mesuré avec le probe remis à l'état `628f08cc`, **mêmes 3 échecs, mêmes
messages**. Ce n'est ni cette tranche ni les PR du jour.

```
E-MOVING  : 1140 deja retire PENDANT le pas -- T1 fire trop tot
FINISH-a  : le port a RETIRE 1140 sur une unite HORS PLATEAU -- le gate `HasTile(Owner)` de T3
            est perdu (degradation PERMISSIVE)
FINISH-a  : le port a repose l'unite -- il n'a pourtant PAS le Fallback
```

Ce qui est **éliminé** : ce n'est pas le découpage du pas. Après rebranchement sur
`play_step_instrumented`, le vecteur est bien joué **une seule fois** (aucun échec `calls != 1`)
et `1140` est malgré tout **absent** de l'état intermédiaire — il part donc **avant** le vecteur
`On(0x04)`, alors que son retrait porté (T1) y est branché.

Ce qui reste **ouvert** : quel étage retire `1140` et **repose l'unité** hors plateau. Les deux
échecs `FINISH-a` disent l'**inverse** de ce que la docstring du probe décrit (le port devait
*garder* `1140` hors plateau, faute de porter `...StormboyzStrike_FallbackAbility`), ce qui
suggère un étage entré depuis. Pistes non confrontées : le bloc « unité qui REVIENT sur le
plateau » de `MoveUnitOperation.execute` (`pc is None -> set_unit_feet`, #448-r1), et la
primitive de position précédente (`076d16c4`). Suivi : **`#448-r3-r1`**.

## 7. Fichiers

- `scripts/python/probe_448_r3_move_step_atomicity.py` — le foyer + les 5 étapes + `--mutate`.
- `scripts/python/tests/engine/runner/test_448_r2_teleporting_in_live.py` (1036).
- `scripts/python/tests/engine/runner/test_448_r2c_fear_of_the_unseen_live.py` (1241).
- `scripts/python/tests/engine/runner/test_448_r2d_titanhammer_squad_live.py` (1574, **2 bras**).
- `scripts/python/probe_448_r2{,b,c,d}_*.py` — mêmes sites, rebranchés.

**Aucun fichier de `engine/` n'est modifié par cette tranche** : le port était juste.
