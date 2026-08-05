# #429-r1-r1 — L'attaque NORMALE sur un cadavre (EN COURS)

**Build de reference** : `rnca9r7q6c`. Fiche en cours de redaction — l'etat FINAL remplacera ceci.

## 1. La question prealable, repondue AVANT tout port

> Les attaques DECLENCHEES empruntent-elles `DamageHandler.visit_AttackUnitMessage` ?

**NON, cote port** — derive du code, pas suppose : aucun module d'`engine/**` ne CONSTRUIT
`AttackUnitMessage`. Les chemins declenches appellent directement `AttackDamageOperation.execute`.

**OUI, cote natif** — mais par le MEME site que l'attaque commandee, donc le gate ne les distingue pas.

## 2. RE (en cours)

* `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute` appelle
  `IOperationProcessor.ActiveAbility(caster, target, abilityType, options)` ;
* `Core.Services.OperationProcessor$$ActiveAbility` -> `IdunBattle.Operations.ActiveAbilityOperation$$Execute`
  (SEUL appelant CODE hors la re-entree `ExecuteForReplacedTarget`) -> `$$ExecuteInternal` -> le gate
  `IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`.

Le gate lui-meme ne lit AUCUN flag d'`AbilityOptions` (decompile relu ce jour) :

```
IsDeadUnitAndNotAllowedByAbility(this, abilityType, target):
    ability = AbilitiesDatabase.Get(abilityType)
    if (!EntityExtensions.IsUnit(target))                 return false
    if (UnitExtensions.IsAlive(target, this@+0x18))       return false
    return slot_0x11(ability) ^ 1                         // !CanContinueOnDeadTarget()
```

-> contrairement au gate ACTEUR-mort post-`On(0x2a)` (qui lit `options@+0x4a`, le litteral `1`
que `UseActiveAbilityBehaviour$$Execute` force), le gate CIBLE-morte n'a **aucune derogation**.

`AttackUnitMessage` **n'existe PAS en natif** (`search_symbols_by_name` : 0 symbole) : c'est une
simplification du port.

## 3. Reste a faire

* chiffrage avant/apres, garde live, contre-epreuve, residus.
