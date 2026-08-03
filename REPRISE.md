# Reprise -- agent `#462-r4b-r1-r1-r1` (pose de Neuroparasite)

Mis en SUSPENS le 2026-08-03 vers 23h55, avant relance de session (plafond de sous-agents atteint).
Ce fichier n'a qu'un role : rendre le worktree SALE pour qu'il survive a la pause.
Sans lui, un worktree propre est auto-supprime et la reprise repartirait dans l'ARBRE PRINCIPAL.

## Tache

Fermer **`#462-r4b-r1-r1-r1`** : la POSE de `Neuroparasite` (1183/1218) n'est pas portee cote runner.
La MAGNITUDE, elle, vient d'etre fermee par la PR #553 (fork prediction/combat sur l'axe magnitude,
`NeuroparasiteEffect$$CreateEffectDamageMalusForDefense` indexant son `ConfigVar(8)` sur
`GetAbilityState(effect)`). Port 4448 == natif 4448, bornes `(4392, 5461)`.

Le probleme : la mesure n'a ete possible que parce que la pose venait du NATIF et que l'etat etait
seede. En self-play 100 % porte, le parasite n'apparaitrait JAMAIS. Tous les bras sont au niveau 1
(`GetIncreaseLevelBehaviour` non portee).

## A faire

1. RE de la POSE : quel behaviour/trigger natif la pose, sur quelle entite, a quel moment.
2. Porter en respectant la frontiere DSL / imperatif (`docs/rl/dsl-effect-nodes.md`).
3. `GetIncreaseLevelBehaviour` : porter si meme artefact, sinon nommer en residu avec son symbole.
4. Confronter LIVE : le parasite doit apparaitre par le seul jeu du port, magnitude inchangee.

## A lire en premier

`docs/rl/case-462-r4b-r1-r1-rayon-de-souffle-additif-defenseur.md`

## Pieges deja mesures

* `catalog_inject.write_grafted_seed_bc(..., replace=True)` **VIDE** `BC.Units[].PassiveAbilities` ;
  le natif lit les passifs sur l'ENTITE, pas sur le kit gameconfig
  (`docs/rl/case-419-r1-tr14-r5-dispatch-attaque-normale.md`).
* `Psychic` a `PiercingRatio = 100` -> le plancher est l'identite, l'axe percage est
  STRUCTURELLEMENT ferme a Neuroparasite. Un accord obtenu la ne prouve RIEN : l'assertionner comme
  BORNE, jamais comme confirmation.

## Discipline

Worktree isole, aucune (re)injection Frida ni redemarrage de host, tests cibles seulement (4 max en
parallele), banque `-Since origin/master` verte + attestation `probe_462` avant la PR, rebase et
re-jeu des tests par l'auteur, livraison PAR PULL REQUEST.
