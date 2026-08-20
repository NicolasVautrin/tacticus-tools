# #10040 -- UN RELAIS ARME A ECRIT SUR UNE VRAIE BATAILLE, ET ÇA A COUTE UN JETON DE BOSS DE GUILDE

## Ce qui s'est passe (2026-08-20, build t6dpr4k06g)

`sandbox_boss.py` arme `deploymentStartArmer` pour ses montages. Ce relais MEMORISE la
composition a l'appui sur START et la REJOUE **tout seul** au retour d'un ecran de deploiement
-- n'importe lequel, aucune condition sur la bataille.

Il est reste arme. L'utilisateur est entre dans une VRAIE bataille de boss de guilde ; l'ecran
de deploiement s'est ouvert ; le relais a pose les 5 unites de la reference par la voie
**runner-directe** (`committerUnePose`, `poseParFsm` etant a `false` apres le reinject). Cette
voie cree des unites REELLES que le HUD ne voit pas -- d'ou Trajann affiche a l'ecran sur
l'entite `eldarFarseer`.

Aggravation : au lieu de m'arreter, j'ai tente une reparation SUR L'ESSAI EN COURS. Le
`deploymentRetirer` a produit ses 5 `RemoveUnitMessage` mais les entites sont restees vivantes,
et le START a converti les placeholders PAR-DESSUS. Etat final : **10 unites du joueur** au lieu
de 5, dans un ordre different de la reference, MoW intercalee.

Les 17 pas produits, qui racontent tout :

```
0-4    AddUnitMessage    32519, 2299, 2735, 2955, 2740   <- l'auto-rejeu
5-9    RemoveUnitMessage 241 x5                          <- la reparation
10-13  AddUnitMessage    2955, 2735, 2740, 2299          <- le START convertit 4 placeholders
14     AddMachineMessage 2271                            <- la MoW
15     AddUnitMessage    2738                            <- le 5e heros, APRES la machine
16     StartBattleMessage 11980
```

⚠ A noter quand meme : `AddMachineMessage=2271` et `StartBattleMessage=11980` valent la
reference AU CARACTERE. La machinerie de la tranche fonctionne, y compris sur une vraie
bataille -- c'est le DECLENCHEMENT non voulu qui a tout gate.

## La faute, et ce qu'elle n'est pas

Elle n'est PAS d'avoir mal repare. Elle est qu'un relais ARME pouvait ecrire sur une partie
officielle **sans que personne ne l'ait demande**. Une consigne (<< pense a desarmer >>)
n'arrete pas un comportement : il faut un REFUS EXECUTABLE.

Corollaire, paye deux fois dans la meme heure : **sur un essai reel, une divergence ⇒ ON
S'ARRETE. On ne repare pas en vol.** Chaque ecriture de plus part d'un etat qu'on n'a pas
etabli.

## La parade

`refusHorsSandbox()` dans `frida/hooks/features/deployment-draft.ts` : toute primitive qui
ECRIT sur le runner vivant lit la source de mode active
(`idun.IdunMainView._activeGameSource`, PAR NOM) et **refuse** si sa classe n'est pas
`SandboxGameModeSource`. Couvre `committerUnePose`, `poserUnHerosParFsm`, `rejouerLaMoW`,
`retirerDuRunner`, `deploymentCommit`, `deploymentStartInvoquer`.

Le discriminant n'est pas invente : `sandbox-mode.ts` l'employait deja pour son injection de
`IdunGameViews`.

⚠ **Tri-etat** : << pas su lire la source >> REFUSE aussi. Une source non mesuree n'est pas une
source sure -- et c'est exactement le travers qui a produit l'incident (on a lu `duJoueur=0`
pour << plateau vide >> alors que la mesure ne portait pas sur ce qu'on croyait).

⚠ **L'echappatoire est `surBatailleReelle: true`, coup par coup, JAMAIS un mode persistant.**
Aucune variable globale ne le retient, et c'est delibere : c'est precisement un etat persistant
oublie qui a cause l'incident. Le rejeu AUTOMATIQUE appelle sans argument, donc il est refuse
hors sandbox -- le chemin exact de la faute est ferme.

## Reste ouvert

* La parade est **cablee et compilee, pas encore eprouvee LIVE** (elle exige un reinject).
  A verifier dans les deux sens : refus sur `GuildBossGameModeSource`, passage sur un montage
  sandbox.
* `retirerDuRunner` a rendu `ok:true` sur ses 5 cibles alors que les entites sont restees
  VIVANTES. Son verdict ne vaut donc rien -- il rapporte << `Apply` passe >>, pas << l'unite est
  partie >>. A confronter a l'effet, comme tout le reste.
