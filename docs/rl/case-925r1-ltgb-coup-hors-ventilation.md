# `#925-r1` — le `+1 coup` de `LetTheGalaxyBurn` : primaire ou cleave ? (EN CHANTIER)

> Numero reserve pour tout residu neuf de cette tranche : **`#925-r3`**
> (`probe_468_collision_numeros.py --suggere 925`, allocation atomique).

## La question binaire

Le `+1 coup` arme par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger`
et materialise par `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`
est-il attribue par le NATIF a la cible PRIMAIRE ou a une cible du CLEAVE — et le port fait-il
l'inverse ?

## Etat : re-mesure de l'enonce herite en cours

L'enonce du backlog date du **2026-08-11** (`78726235`). Deux tranches ont touche le meme pipeline
DEPUIS :

* **#949** (`ec18e5d4`, 2026-08-12) — « le coup manquant n'existait pas, c'etait le LECTEUR », plus
  un correctif d'ORDRE PAR FACE dans `apply_pierce_and_modifiers` (1 point d'ecart).
* **#953-r2** (`ce81d47e`, 2026-08-12) — la PLACE de `On(PreAttack = 5)` dans le vecteur d'attaque
  normale a ete REDESCENDUE sous `attacker_modifiers`.

Les deux deplacent exactement les entrees que l'enonce mesure. La re-mesure est donc le premier
geste, avant toute reparation.
