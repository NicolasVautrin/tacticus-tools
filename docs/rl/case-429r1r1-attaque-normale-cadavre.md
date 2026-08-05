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

## 3. Reste a faire

* chiffrage avant/apres, garde live, contre-epreuve, residus.
