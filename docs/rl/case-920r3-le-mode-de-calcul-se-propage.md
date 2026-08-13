# #920-r3 — le natif propage un MODE, il ne réduit pas les bornes à un scalaire

Build `rnca9r7q6c`. **Décompilé = vérité.** Cette fiche **réfute** l'hypothèse sur laquelle le
résidu reposait depuis #91, et **reformule** la question.

## Ce que le résidu demandait

Trois call-sites du port passent à `capped_reduction_flat` un centre `(lo + hi) / 2.0` qui peut
valoir `.5`. `#920-r1` avait corrigé l'**arrondi** de ce centre ; `#986` avait établi que le natif
ne voit **jamais** un fractionnaire (`IdunBattle.Entities.Formulas.CurrentDamageFormula$$Calculate`
lit `AbilityEntities+0xe8` en `Nullable<int>`). La question devenait donc « **quel** entier ? », et
le point d'entrée désigné était « le WRITER de `+0xe8` ».

## Ce que la lecture rend — la question était mal posée

`IdunBattle.Entities.Formulas.PercentageOf` porte **trois** points d'entrée, et leurs corps sont
**structurellement identiques**. Ils ne diffèrent que par **un entier** : le numéro de slot invoqué
sur les deux sous-formules.

```
PercentageOf$$Calculate(this, entities, result)
    a = <this+0x10>.slot_1(entities, result)      // sous-formule POURCENTAGE
    b = <this+0x18>.slot_1(entities, result)      // sous-formule MONTANT
    return PercentageOf$$CalculateInternal(this, a, b)

PercentageOf$$CalculateMin  : le meme corps, slot_2 sur les deux sous-formules
PercentageOf$$CalculateMax  : le meme corps, slot_3 sur les deux sous-formules
```

Et ces slots sont **nommés** dans `data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` :

| slot | `IAmountFormula` |
|---|---|
| 0 | `IsSimple` |
| 1 | `Calculate` |
| 2 | `CalculateMin` |
| 3 | `CalculateMax` |
| **4** | **`CalculateAverage`** |

⇒ **Le mode de calcul se PROPAGE récursivement dans l'arbre de formules.** `CalculateMin` demande
le minimum de chaque sous-formule, qui le demande à son tour aux siennes, jusqu'aux feuilles. Le
natif ne réduit donc **jamais** un couple de bornes à un scalaire avant d'entrer dans
`PercentageOf` : il **parcourt l'arbre deux fois**, une fois en mode MIN, une fois en mode MAX, et
chaque parcours reste cohérent de bout en bout.

Il ne voit pas « un » `finalAmount` — **il en voit deux**, dans deux parcours distincts.

## Conséquences

1. **L'hypothèse « c'est le CENTRE des bornes réduites » est RÉFUTÉE.** Ce n'était pas une lecture
   mais un **fit** de #91 (« D ≈ centre »), et le résidu le disait déjà de lui-même.
2. **L'écart n'est pas un ARRONDI, c'est une divergence de STRUCTURE.** Chercher quel scalaire
   pré-arrondir revenait à raffiner une réduction que le natif ne fait pas.
3. **Cela explique pourquoi aucun montage ne discriminait**, et c'est vérifiable sans mesure :
   `CalculateInternal` est **linéaire** en son entrée **sauf là où il clampe**. Tant que le cap ne
   mord sur **aucune** borne, `f(centre)` et `(f(lo) + f(hi)) / 2` coïncident exactement — donc tout
   montage « ordinaire » rend un accord qui ne prouve rien. L'écart n'apparaît que lorsque le cap
   mord sur **une seule** des deux bornes.
4. **Le mode `CalculateAverage` (slot 4) existe**, et c'est le seul qui ressemble au centre du port.
   `PercentageOf` ne le déclare pas dans la table des symboles (corps hérité de la base, ou
   dédupliqué) : établir *qui* l'appelle, et si le pipeline de dégât l'emprunte, reste à faire —
   mais il ne peut pas se substituer aux deux parcours, puisque les call-sites de bornes invoquent
   les slots 2 et 3, **lus ci-dessus**.

## Ce qui reste, et ce que ça n'est plus

Le résidu **n'est pas fermé** : le fix est de porter les **deux parcours** (`calculate_min` /
`calculate_max` propagés dans l'arbre de formules), là où le port en fait **un** avec un centre.
C'est un chantier structurel sur `services/damage_modifiers.py`,
`services/damage_prediction.py` et `runner/operations/damage_hits.py` — pas une correction d'arrondi.

**Montage discriminant, désormais spécifiable** : des bornes réduites dont **une seule** dépasse le
cap. C'est la seule configuration où les deux régimes divergent, et c'est ce que les montages
précédents (#920, `D = 3106`) ne réalisaient pas.

⚠ **Ce que cette fiche ne mesure PAS** : elle ne confronte rien en live. Elle établit par lecture
que la question posée n'avait pas de réponse, et en substitue une qui en a une. Le port n'a pas été
modifié.
