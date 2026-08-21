# #10041-r5 — un `StartMatch` sans bataille EMPOISONNE tous les chargements suivants

**Mesure du 2026-08-21.** Coût : ~2 h de diagnostic, ~10 relances du jeu par l'utilisateur.

## Le fait

`idun.shared.commands.ViewCommandExecutor$$StartMatch(source, checkIfAlreadyRunning)` écrit la
source dans le créneau **« match courant »** du jeu (un statique) puis appelle
`thor.Loader$$LoadBattle`. Si la bataille n'aboutit pas, **le créneau reste occupé par notre
source**. Tout chargement suivant — le nôtre comme **celui du joueur** — monte alors *cette*
source-là.

Symptôme côté joueur, verbatim : *« la battle se charge et disparaît direct »*, *« y'avait
0 units »*. Une bataille sans unité se termine à l'instant où elle apparaît.

**Seule une relance du jeu libère le créneau.** Aucun désarmement de relais n'y suffit.

## Pourquoi ça a coûté si cher

Le symptôme ne désigne jamais sa cause, et il **se déplace** :

| ce qu'on observe | ce qu'on en conclut à tort |
|---|---|
| `runnerGeneration` monte | « le montage a marché » — non : le runner naît et meurt |
| `__loadingStep` reste à 0 | « `LoadBattle` refuse » — non : il a chargé, puis tout est mort |
| `sandboxProbe.instance == null` | « rien n'est monté » |
| la sandbox ne monte plus | « j'ai cassé le code » |
| une relance répare, un essai | « c'était un état transitoire » |

⚠ **Le premier montage raté rend tous les suivants ininterprétables.** On croit repartir propre
après chaque relance, on rejoue le geste, et on ré-empoisonne — donc chaque cycle mesure la même
chose sans jamais l'apprendre. C'est ce qui a fait chercher un coupable dans le CODE pendant deux
heures, jusqu'à bisecter à blanc un bundle parfaitement innocent.

## La bisection qui l'a nommé, et pourquoi elle a marché

Elle n'a marché que parce que le **discriminant était le joueur** : « peux-tu lancer une bataille
de campagne à la main ? » — une question à laquelle aucun de nos capteurs ne répond.

    jeu relancé, AUCUN agent        -> la campagne se lance          OK
    inject seul                     -> la campagne se lance          OK
    + forge de source + BC + lineup -> la campagne se lance          OK
    + `sandboxModeBcOverride`       -> la campagne se lance          OK
    + `deploymentPoolArmer` (guildWar) -> la campagne se lance       OK
    + 6 capteurs + plafond + gameViews + seed -> la campagne se lance OK
    + `StartMatch`                  -> CHARGE ET DISPARAIT, 0 unite  COUPABLE

Neuf gestes innocentés un par un ; le dernier est le seul qui écrive dans le jeu.

## Ce qu'il faut en faire

* **Ne jamais laisser un `StartMatch` en plan.** Si la bataille n'est pas là en quelques
  secondes, le créneau doit être rendu — sinon la session entière est perdue, pour nous ET pour
  le joueur.
* **`runnerGeneration` n'est PAS un témoin de montage.** Il compte les runners CRÉÉS, pas ceux
  qui vivent. Le témoin est la scène (`sandboxProbe.instance`) ou `retreatStatus.batailleActive`.
* ⚠ **Après un montage douteux, ne rien conclure de la session** : relancer d'abord. Toute mesure
  prise sur une session empoisonnée accuse au hasard.

## Reste ouvert

Pourquoi notre montage a produit une bataille **à 0 unité** ce jour-là, alors que la même chaîne
avait rendu quatre montages complets (jusqu'au bit-exact sur 38 coups) en session 130. Le
`fires` des cinq délégations de pool vaut **0** : le HUD de déploiement n'a jamais rien demandé,
donc la bataille mourait avant lui. Voir `#10041-r4` pour la chaîne, et `case-10041-*` pour la
MoW et l'ordre de pose.
