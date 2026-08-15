# #1013-r3 — Un `customUtility` de call-site n'est JAMAIS sommé : il VETO, il FORCE, ou il est jeté

**Tranché le 2026-08-15 par RÉFUTATION, sans port.** Build de référence : `t6dpr4k06g`.
Retombée : **`#590-r5` tranché HORS LIGNE** dans la foulée (il demandait un capteur).

## 1. Ce que le résidu disait, et ce qui est faux

> « La face DECISION de `TheArdentBlade` — le `customUtility` du `PerformAIAttack` n'est pas porté,
> donc la Geminae rejouée choisit sa cible par l'utilité par DEFAUT. »

Tout le constat est **exact** : la `UtilityDefinition` existe au site, l'utilité 66 vaut bien
`+30`, la feuille portée n'expose pas le paramètre. Ce qui est faux est l'**implication** — le
« donc » sous-entend que le natif, lui, ferait autrement.

**Il fait pareil.** Et ça se lit.

## 2. La chaîne, du call-site au consommateur

```
TheArdentBlade_TriggerAbility$$CreateBehaviour
  -> PerformAIAttack(unit = chosen, allowOnlyMove = 1, ..., customUtility = def)
     def = UtilityDefinition( UtilityBucket([ WeightedUtility(6  UnitMovement,          w=null),
                                              WeightedUtility(66 TheArdentBlade_Geminae, w=null) ]) )

ActiveAbilityActionGenerator.<GenerateActions>d__7$$MoveNext   # d__7+0x38 = customUtility
  -> slot 7 du playbook
  -> ComparablePlaybook<T>$$EvaluateInternal                   # 5e argument
  -> ComparablePlaybook<T>$$CalculateActionUtility             # param_7
```

Corps de `CalculateActionUtility`, **lu verbatim** :

```
if (customUtility == null || customUtility.Buckets.Length == 0)   -> chemin NORMAL
r = UtilityDecider.CalculateUtility(db,
        UtilityAttackCase.Base(unit, position, target, abilityOrEffect),
        customUtility.Buckets[0], evaluate)
if (r == BaseUtility.statics+0x18 || r == BaseUtility.statics+0x20) -> Nullable VIDE
if (r == BaseUtility.statics+0x10)                                  -> utilité = r
sinon                                                               -> chemin NORMAL, r est JETÉE
```

**Le `customUtility` n'entre dans aucune somme.** Trois issues, et trois seulement.

## 3. Les sentinelles, lues

`IdunBattle.AI.Utilities.BaseUtility$$.cctor` écrit sept statics ; `FixMath.NET.Fix64$$.cctor`
donne les deux valeurs auxquelles elles renvoient (`Fix64.statics+0x10 = 0x7fffffffffffffff` =
MaxValue, `+0x18 = 0x8000000000000000` = MinValue).

| slot | valeur | rôle dans `CalculateActionUtility` |
|---|---|---|
| `+0x00` | `Fix64(0)` | **NEUTRE** — pas testée ⇒ chemin normal |
| `+0x08` | `Fix64(100000)` | pas testée |
| `+0x10` | `Fix64.MaxValue` | **MUST-DO** |
| `+0x18` | `Fix64.MinValue / (1000001/1000000)` | **VETO** |
| `+0x20` | `Fix64.MinValue` | **VETO** |
| `+0x28` | `Fix64.MinValue / (1000002/1000000)` | pas testée |
| `+0x30` | `Fix64(-12345)` | pas testée |

## 4. Les deux call-sites, en sens inverse — c'est ce qui valide la lecture

| utilité | ce qu'elle yield | effet |
|---|---|---|
| `OnlyCertainTargetUtility` (1101) | `statics+0x20` = MinValue hors liste, `statics+0x00` = 0 dedans | **ÉLIMINATION** / scoring normal |
| `TheArdentBlade_GeminaeUtility` (1468) | `Fix64(0)` ou `+30` | **JETÉE** — chemin normal |

`TheArdentBlade_GeminaeUtility.<EvaluateAttackInSteps>d__1$$MoveNext`, corps lu :

```
x = Fix64(0)
parent = UnitExtensions.GetParent(case.unit, state, root: false)
if (AreEntitiesAdjacent(UnitPosition.get_MainTile(case.position), parent))
    x += BaseUtility.GetUtilityValue("LikesAdjacentCelestine")     # = 30 au seed
yield x
```

L'autre membre du bucket, `UnitMovement(6)`, est un **composite de feuilles numériques**
(`Tile` + `MinDistanceToClosestEnemy`). La somme ne peut donc valoir aucune des trois sentinelles
testées.

⇒ **Le port est déjà conforme.** Porter (a) le paramètre sur la feuille et (b) la classe d'utilité
n'aurait changé **aucun observable**.

> L'intention du designer (« la Geminae devrait préférer rester près de Celestine ») est lisible
> dans la donnée ; le **mécanisme** ne la réalise pas. On porte le mécanisme, pas l'intention.

## 5. Retombée : `#590-r5` tranché, et le port avait raison

Le résidu portait `BLOCAGE: capteur` — « la POLARITÉ de ces deux constantes n'est pas lisible
offline ; trancher demande de lire les deux champs statiques à l'exécution ». **Aucun capteur n'a
été nécessaire** : les constantes ne sont pas des `DAT_*` opaques mais les statics de `BaseUtility`,
dont le `.cctor` est nommé. La crainte de la fiche — « si la constante de rejet était seulement
BASSE et non éliminatoire, le port refuserait de frapper là où le natif frapperait faute de
mieux » — est **écartée** : `MinValue` n'est pas basse, elle est éliminatoire par un test d'égalité
explicite.

## 6. Ce qui est gardé, et ce qui ne l'est pas

`scripts/python/tests/engine/test_1013r3_custom_utility_sentinelles_offline.py` (3 tests, ~2 s) :

1. le poids `LikesAdjacentCelestine` **existe** au seed et reste un nombre **fini** — la réfutation
   repose sur cette donnée, qui peut bouger sous elle ;
2. le `custom_utility` du port reste une **exclusion** (`set[int] | None`) et la feuille le propage
   en `allowed_targets`, jamais en score ;
3. `None` (aucune cible préférée) = **aucune contrainte**, jamais `set()` — qui interdirait tout.

**NON COUVERT** : aucun montage live n'a été joué sur le régime `grp2` de la relique. La réfutation
est **structurelle** (décompilé), pas observée. Un live la confirmerait en montrant que la Geminae
ne privilégie pas les tuiles adjacentes à Celestine — observable faible, montage lourd (relique
équipée + pas de Geminae morte + pas de tuile libre + géométrie discriminante).

## 7. Re-dériver

```
python -m pytest scripts/python/tests/engine/test_1013r3_custom_utility_sentinelles_offline.py -q
```

Décompilés à relire si le build change : `ComparablePlaybook<T>$$CalculateActionUtility`,
`BaseUtility$$.cctor`, `FixMath.NET.Fix64$$.cctor`,
`OnlyCertainTargetUtility.<EvaluateAttackInSteps>d__3$$MoveNext`,
`TheArdentBlade_GeminaeUtility.<EvaluateAttackInSteps>d__1$$MoveNext`.
