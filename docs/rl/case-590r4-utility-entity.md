# #590-r4 — `utilityEntity` (`PerformAIAbilityUnitBehaviour+0x80`) : la fiche décrivait le mauvais étage

**Livré le 2026-08-10** (build `rnca9r7q6c`). Foyer :
`scripts/python/engine/runner/abilities/behaviours/ai_control.py`. Garde :
`scripts/python/tests/engine/test_590r4_utility_entity_offline.py`.

## 1. Ce que la fiche disait, et ce que le décompilé dit

> « C'est un sélecteur résolu par `SelectFirst` et passé à la couche d'utilité comme entité de
> référence du scoring ; le moteur d'utilité porté (`engine/ai/tactic.py`) n'expose pas ce point
> d'ancrage. `1101` y passe `Owner@sel+0x30` = le CASTER […] : le défaut du port coïncide donc sur ce
> call-site. »

`IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`, relu en entier :

```
utilityEntity = <invocateur>(1,  <ITargetsSelector>, behaviour+0x80, abilityEntities);  // SelectFirst
movementTiles = <invocateur>(10, <ITargetsSelector>, behaviour+0x88, abilityEntities);  // SelectTiles
foreach (acteur in <invocateur>(4, <ITargetsSelector>, behaviour+0x50, …)) {
    …
    if (movementTiles == null) {
        if (behaviour+0x90 != 0) {                                   // customUtility
            ValueTuple..ctor(&tuple, acteur, utilityEntity);         // (Item1, Item2)
            utilite = <invoke du delegue +0x90>(tuple);
        }
        <message 0x37 …, utilite>
    } else <message 0x38 …>
}
```

**Trois lectures qui contredisent la fiche** :

1. **`utilityEntity` n'a AUCUN lecteur dans la couche d'utilité.** Son unique consommateur est le
   `ValueTuple` du délégué `customUtility`. Le champ est donc inerte *si et seulement si* `+0x90`
   est nul — c'est une propriété du **call-site**, pas du champ. Corollaire : le foyer annoncé
   `engine/ai/tactic.py` n'était pas le bon (le `custom_utility` que
   `calculate_ability_action_for_unit` accepte et ignore est un résidu **distinct**, déjà nommé dans
   sa propre docstring).
2. **`1101` le consomme.**
   `IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$GetAttackCustomUtility`
   fait `GetPreferredAttackTarget(this, input+8, input+0)` — donc `Item2` (= `utilityEntity`) devient
   le paramètre **`caster`** de
   `…AttemptedPossessionAbility$$GetPreferredAttackTarget(caster, possessedUnit)`, et `Item1`
   (= l'acteur courant) le `possessedUnit`.
3. **La résolution a lieu UNE FOIS, avant la boucle** — pas par acteur. Avec un sélecteur constant
   les deux régimes rendent la même valeur : seul un **compteur d'évaluations** les sépare, et c'est
   ce que garde l'étage 3 du test.

Le slot est **lu**, jamais deviné : `ITargetsSelector 1 SelectFirst / 1` dans
`data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` (`10 SelectTiles`, `4 SelectUniqueUnits`).

## 2. « Ça coïncide déjà » était vrai en VALEUR et faux en CANAL

Le consommateur porté (`attempted_possession_custom_utility`) déclare `(state, actor_id)` et
**capture `caster_id` par fermeture** au call-site. Sur `1101` la valeur est la bonne — `Owner()` y
résout au caster, et l'owner-swap a déjà eu lieu quand le possédé agit. Mais la valeur ne vient pas
du sélecteur `+0x80` : un call-site qui y passerait autre chose que l'owner serait rendu **faux en
silence**, sans qu'aucun témoin ne bouge.

C'est la différence entre « le port rend la bonne valeur » et « le port lit la bonne source ». La
première se mesure ; la seconde est ce qui tient au prochain call-site.

## 3. Ce qui est livré, et pourquoi en compatibilité

**Rayon de souffle mesuré** : `PerformAIAbility` a **un seul consommateur exécutable** dans tout
`scripts/python` (`attempted_possession.py`) ; les autres occurrences sont des docstrings. Le canal
est donc posé sans rupture :

- `utility_entity` est résolu **une fois**, par `resolve_unit` (mirror `SelectFirst`) ;
- un `custom_utility` déclarant **trois** paramètres positionnels (ou `*args`) reçoit l'id résolu ;
  un `custom_utility` à **deux** garde exactement son contrat — value-preserving ;
- une signature illisible (builtin, C-extension) est traitée comme un refus : on ne tente pas un
  appel à trois arguments « pour voir » ;
- l'`emit` porte désormais `utility_entity`. La fiche l'annonçait « conservé, **journalisé** » — il
  ne l'était pas, donc le seul canal d'observation du champ était muet.

## 4. Validation, et ce qui n'est PAS couvert

**7 gardes offline**, `3 mutations / 3 rouges` (vues avant le fix, messages verbatim) :

| mutation | rouges | message |
|---|---|---|
| threading retiré | 4 | `TypeError: …<lambda>() missing 1 required positional argument: 'u'` |
| résolution PAR ACTEUR | 1 | `AssertionError: 3 acteurs, UNE resolution … assert 3 == 1` |
| `emit` muet | 2 | `KeyError: 'utility_entity'` |

Non-régression : `test_590_attempted_possession_offline.py` + la garde neuve = **30 passed**.

**NON COUVERT :**

- **`#590-r9`** — le consommateur de `1101` capture toujours par fermeture. Le canal est posé, pas
  encore lu. Value-preserving sur `1101`, donc **aucun témoin ne peut le distinguer** sans un
  call-site où `utilityEntity != caster` — et il n'en existe aucun de porté.
- **Aucune confrontation LIVE.** Il n'existe pas de test live pour `1101` (le port de #590 est
  offline), et la valeur coïncidant, un run live ne séparerait rien. Ce qui rendrait le canal
  observable est un call-site où les deux divergent : les cinq appelants natifs recensés de la
  surcharge à 6 arguments (`ShockAssaultAbility$$CreateBehaviour`,
  `ECogSupportAbility$$CreateBehaviour`, `DaGreatWaaaghAbility$$ExecuteBehaviour` +
  `$$GetMoveAndAttackBehaviour`, `ItItchesAbility$$ExecuteBehaviour`) ne sont pas portés sur ce
  chemin — c'est là qu'il faudra regarder.
- **Le champ `+0x88` (`movementTiles`)** — découvert au passage, non porté. Il commute le behaviour
  vers un **autre message** (`0x38` au lieu de `0x37`) : c'est la surcharge à 3 arguments de
  `DSLBehaviors$$PerformAIAbility`, dont l'unique appelant est `BurrowersAbility_Appear`. Le port ne
  l'expose pas, et le nœud n'a aucun moyen de le poser — donc pas de dégradation silencieuse
  possible aujourd'hui, mais la lecture est consignée ici pour qui portera `BurrowersAbility`.
- L'écart **score → exclusion** de `OnlyCertainTargetUtility` reste `#590-r5` (`BLOCAGE: capteur`),
  inchangé.
