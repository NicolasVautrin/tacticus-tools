# #488-r1 — `OnMeltaDamageAbility` (1211) : le trigger EXISTE, et ce n'est pas ce qui la tue

**Statut : EN COURS.**

## 1. La question, posee AVANT la methode

`case-72` a classe `1211 OnMeltaDamageAbility` en DEAD-CODE sur `gqfc5mff6c`, avec pour racine
*« l'ability n'override pas `CreateTrigger` »*. #519 a falsifie cette racine au decompile sur
`rnca9r7q6c`. La question de CETTE tranche n'est donc pas « le symbole existe-t-il » mais :

> **Le chemin est-il VIVANT ?** Et si non, par quel mecanisme exactement ?

Deux reserves, toutes deux nommees par #519, a lever AVANT tout port.

## 2. Reserve (a) — le corps est DEDUPLIQUE, mais le slot d'OnMelta y pointe

(en cours)

## 3. Reserve (b) — l'effet n'est pas observe live

(en cours)
