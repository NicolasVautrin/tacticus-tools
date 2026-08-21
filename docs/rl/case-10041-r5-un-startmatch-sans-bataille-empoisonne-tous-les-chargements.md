# #10041-r5 — un `StartMatch` sans bataille EMPOISONNE tous les chargements suivants

**Mesure du 2026-08-21.** Coût : ~2 h de diagnostic, ~10 relances du jeu par l'utilisateur.

## Le fait

`idun.shared.commands.ViewCommandExecutor$$StartMatch(source, checkIfAlreadyRunning)` écrit la
source dans le créneau **« match courant »** du jeu (un statique) puis appelle
`thor.Loader$$LoadBattle`. Si la bataille n'aboutit pas, **le créneau reste occupé** et — c'est
là le fait — **le verrou d'entrée reste armé** : plus aucun chargement ne démarre, ni le nôtre,
ni **celui du joueur**.

Symptôme côté joueur, verbatim : *« la battle se charge et disparaît direct »*, *« y'avait
0 units »*.

⚠ **CE FICHIER A PORTÉ « tout chargement suivant monte CETTE source-là ». Ça ne tient pas au
décompilé** : `StartMatch` **réécrit** le créneau à chaque appel (`*S = holder`, sans condition),
donc la source montée par le joueur était la **sienne**. Ce qui a été établi, c'est le **verrou**
(section suivante) ; la bataille **à 0 unité** reste, elle, **inexpliquée** — et l'expliquer par
une phrase qu'on n'a pas mesurée est exactement ce qui a fait chercher deux heures du mauvais
côté.

⚠ **CE FICHIER A PORTÉ « seule une relance du jeu libère le créneau ». C'EST FAUX**, et la
phrase a survécu une journée entière en faisant demander des relances à l'utilisateur. Ce qui
était vrai — et qui reste écrit ici parce que c'est ce qui l'a rendue crédible — c'est
qu'**aucun désarmement de relais n'y suffit** : on cherchait le remède du mauvais côté.

## Le verrou est `IdunMainView.IsActive`, et le jeu porte sa propre libération

Le refus de `StartMatch` teste **un statique d'`IdunMainView`**, celui que lit
`idun.IdunMainView$$get_IsActive`. Ce n'est **pas** `IsBattleActive`, que lit
`idun.IdunMainView$$get_IsBattleActive` — le statique **VOISIN d'un octet**, et celui que publie
`retreatStatus.batailleActive`. D'où la lecture qui n'a aucun sens tant qu'on confond les deux :
*« aucune bataille ne tourne, et pourtant plus rien ne se charge »*.

`idun.IdunMainView$$SetBattleNotRunning()` — **statique, sans argument** — remet les **deux** à
zéro. C'est ce que le jeu s'appelle à lui-même en fin de bataille, et c'est joignable par
`viewInvoke {cible: "statique"}`. Foyer : `rejeu_commun.liberer_le_verrou_de_match`.

⚠ **Et la libération est CONDITIONNELLE.** Un verrou armé pendant qu'une bataille vit est
**légitime** : le lever autoriserait le montage suivant à écraser un match dont la tentative est
déjà enregistrée côté serveur. Le foyer n'ouvre que sur un verrou **ORPHELIN** — armé, sans
`IdunMainView` vivante, chargeur au repos — et **ARRÊTE** sinon.

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
  le joueur. Le rendre, c'est `liberer_le_verrou_de_match` ; **pas** une relance.
* ⚠ **Désarmer `checkIfAlreadyRunning` n'est PAS ce remède** — c'est passer outre. Le montage
  passe alors quoi qu'il y ait dans le créneau, et surtout **la partie du joueur reste bloquée** :
  SON `StartMatch`, lui, teste toujours. `sandbox_gw.py` a porté ce contournement une journée.
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
