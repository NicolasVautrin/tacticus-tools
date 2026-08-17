# #479-r6 — la garde de flotte de `nettoyer_livraison` a une COURSE AU DÉMARRAGE

> Mesuré le 2026-08-17, en nettoyant la scène git **juste après** un refill de 5 agents.

## Le fait

`nettoyer_livraison.py` (DRY-RUN) a proposé de supprimer le worktree d'un agent **lancé
40 secondes plus tôt** — un des cinq du refill, `tip 21ff277b` (= `master`), donc « ancêtre
d'`origin/master` », donc classé **livré**. Les quatre autres du même refill étaient
correctement protégés `AGENT EN VOL`. Rien n'a été appliqué.

Re-joué quelques minutes plus tard, sans rien changer : les **cinq** sortent `AGENT EN VOL`,
et la proposition tombe de **9 à 8**. C'est donc une **course**, pas un défaut permanent.

## Pourquoi la garde a ce trou

La protection est `fleet_board.collect(only_alive=True)` (`nettoyer_livraison.chemins_en_vol`),
et `fleet_board` dérive la vivacité du **transcript** de l'agent. Or le worktree est créé
**avant** que l'agent n'écrive sa première ligne : il existe une fenêtre de quelques dizaines
de secondes où le répertoire est là et le transcript n'est pas encore là. Dans cette fenêtre,
l'agent est invisible de la seule source qui le protège.

## Ce que le critère A mesure RÉELLEMENT — et ce n'est pas « livré »

Le dépôt merge en **squash**, et le skill le dit déjà : `merge-base --is-ancestor` est
**aveugle à un squash-merge**. Une branche réellement livrée n'est donc *pas* ancêtre de
`master`. Conséquence, qui n'était écrite nulle part :

> « ancêtre d'`origin/master` » ne désigne pas un agent qui a **livré**, il désigne un agent
> qui n'a **rien commité**.

Mesure du même passage : sur les 7 worktrees du gisement A, **6** portaient ce motif et **1**
seulement une PR mergée (`#1103`). Le gisement est donc, à 6/7, une pile de « n'a rien
produit » — et un agent qui vient de naître y ressemble **exactement**. Les deux ne sont
séparés que par la mesure de vivacité, celle qui a la course ci-dessus.

## La parade tenue ici

**Re-jouer le DRY-RUN et vérifier NOMMÉMENT chaque agent du dernier refill** avant
`--appliquer`. C'est ce qui a évité la suppression.

## Une piste RÉFUTÉE, une piste MESURÉE

**`.agent-alive` — RÉFUTÉ.** Il est écrit **par l'agent**, pas déposé par le harnais à la
création : sur le même refill, les trois marqueurs lisibles portent des textes *choisis par
chaque agent* et sont apparus à **22:08:57 / 22:09:21 / 22:11:04** pour un lancement commun.
Il a donc la même course, décalée de jusqu'à trois minutes.

**Le VERROU git — MESURÉ, et il n'a pas la course.** `git worktree list --porcelain` rend
`locked` sur **5 des 5** worktrees du refill, alors que **6 seulement sur 64** le portent au
total. Il est posé par le **harnais au lancement**, donc il ne dépend d'aucune écriture de
l'agent : c'est exactement l'invariant qui manque à la fenêtre du nouveau-né.

⚠ Ne PAS en conclure que `locked` remplace la mesure de vivacité — le skill mesure l'inverse
(0 verrou sur 15 agents dont 8 travaillaient), parce qu'il n'est **jamais reposé par une
reprise `SendMessage`**. Les deux sources ont des angles morts **complémentaires** : le
transcript est aveugle au nouveau-né, le verrou est aveugle au repris. La garde qui ferme ce
résidu est leur **UNION**, pas leur remplacement l'une par l'autre.

⚠ Et pas de seuil d'âge : un seuil se dégrade en silence — c'est l'anti-patron déjà
documenté (`feedback_threshold_guard_decays`).

## Portée

Ne concerne QUE la fenêtre « nettoyer immédiatement après un refill ». Un nettoyage joué à
froid, sans agent lancé dans la minute, ne rencontre pas la course.
