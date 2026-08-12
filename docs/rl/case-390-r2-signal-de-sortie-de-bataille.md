# #390-r2 — la retraite du warmup detecte par SIGNAL, et NOMME ce qu'elle traverse

`retreatToCampaign` (`frida/hooks/features/warmup-singletons.ts`) sondait l'UI toutes les
250 ms apres le clic de confirmation — « le noeud de campagne est-il la ? », puis « une
instance `IdunNavigation` est-elle vivante ? » — sur deux budgets de 12 s poses au jugement.
Un warmup VERT ne disait rien de ce qui s'etait passe entre les deux : campagne remontee
seule, ou frame intersticielle traversee ? Personne ne pouvait le dire.

Le signal existait deja dans le depot : `frida/hooks/features/ui-windows.ts` ancre les cinq
points de `idun.ui.ScreenVisibilityManager` et note chaque transition avec son `GuiId` NOMME.

## La mesure — deux cycles complets, sequences IDENTIQUES

Session 73, build `rnca9r7q6c`, bundle de `b0db23fc`. Journal arme par
`uiWindowEvents {start, clear}`, puis `warmupGameSingletons({force:true})` (vert 8/8),
puis relecture. **28 transitions, deux fois de suite, a l'identique.**

```
#7   retire       Campaign        <- l'ecran campagne est RETIRE a l'entree en bataille
#11  inscrit      PauseMenu       <- l'ecran de pause s'inscrit : on est EN bataille
#13  montre-debut PauseMenu       <- clic pause
#19  montre-debut MessagePopup    <- clic retraite -> confirmation
#23  cache-debut  MessagePopup    <- clic confirmation : le popup cede (== confirmPopupReplaced)
#25  cache-debut  ChestScreen
#27  retire       PauseMenu       <- LE SIGNAL : la scene de bataille est dechargee
#28  cache-debut  ChestScreen
(plus rien)
```

Signal retenu : `ScreenVisibilityManager$$Unregister` portant `idun.tracking.GuiId.PauseMenu`.
Symetrique exact de l'inscription d'entree (#11), NOMME, reproductible.

**Aucune frame intersticielle n'a ete traversee** dans les deux runs — zero `montre-debut`
entre #23 et #27. C'est la reponse a la question que le step ne savait pas poser.

## Trois criteres REFUTES par cette mesure

1. **« attendre que l'ecran de CAMPAGNE se montre »** — il n'y a AUCUN `montre-debut`/
   `montre-fin` de `GuiId.Campaign` au retour. L'ecran campagne est `retire` a l'entree (#7)
   et ne se reinscrit pas. Fonder la detection dessus aurait rendu le plafond systematique.
2. **« la nav est vivante »** — deja refute par #390 : juste apres le remplacement du popup,
   l'invoke rend `no live IdunNavigation instance`.
3. **`uiWindows` comme substitut du journal** — au meme instant, `FindObjectsByType(
   ScreenVisibility, Include)` rend 8 ecrans **sans aucun `Campaign`**, alors que `#7` prouve
   qu'il en existait un. `Register` prend une INTERFACE (`idun.ui.IScreenVisibility`) : des
   implementations qui ne sont pas des `ScreenVisibility` MonoBehaviour passent par le
   manager sans etre enumerables. **Le journal est strictement plus complet que le sondage.**

## Ce que la mesure a trouve dans `ui-windows.ts` — et qui est repare

Le journal publiait `ordinal -1988785488` sur deux transitions de chaque cycle. Cause lue
dans `frida/methods.tsv` :

```
ScreenVisibilityManager.Register    screen:idun.ui.IScreenVisibility
ScreenVisibilityManager.Register    screen:idun.ui.ITemporarilyHideable
ScreenVisibilityManager.Unregister  screen:idun.ui.ITemporarilyHideable
```

Ce sont des INTERFACES : rien ne garantit que l'objet recu soit un `idun.ui.ScreenVisibility`,
et lire `<GuiId>k__BackingField` a SON offset sur un objet d'une autre classe rend un entier
arbitraire. D'ou `classe` (nom IL2CPP de la classe reelle, lu au premier slot de l'objet),
AJOUTE a `TransitionVue` et au journal. **L'ordinal reste publie tel quel** — le rabattre sur
`null` masquerait la mesure ; `classe` est ce qui le rend LISIBLE. Elle explique aussi les
PAIRES (`montre-debut <wrapper>` puis `montre-debut PauseMenu`) :
`BlurredBackgroundScreenVisibilityManagerProxy$$CreateBlurredBackgroundWrapper` inscrit un
wrapper de fond floute EN PLUS du vrai ecran.

## Ce qui a ete AJOUTE a `ui-windows.ts`, et pourquoi pas autre chose

`ecouterTransitions()` — un abonnement PUSH, purement ADDITIF. Il ne lit ni n'ecrit `actif`,
ne touche ni au tampon ni a `recus`. **Pas** un `uiWindowEvents({start})` suivi d'un
`{stop}` : le drapeau et le tampon sont l'etat de l'OPERATEUR, et un `start`/`stop` du warmup
ETEINDRAIT un journal arme a la main (un `clear` effacerait ses transitions). La diffusion aux
abonnes precede le gate `actif` ; sortie immediate quand personne n'ecoute.

Les crans du module sont intacts : toutes les surcharges d'un nom restent attachees,
`ancrages` reste tri-etat, `installerAncrages` reste le seul poseur.

## Deux commandes natives EXAMINEES et NON retenues

- **`ViewCommandExecutor$$CanShowInterstitialPopup(offerVisualId)`** — le decompile est un
  relais nu vers `idun.ui.WebstoreOfferPromotionPopup$$CanShowFor(offerVisualId)`. Elle repond
  « ce VISUEL D'OFFRE est-il montrable », pas « une frame va-t-elle s'intercaler ». Son
  appelant est `ShowOfferInterstitialPopupIfNecessaryCommand$$IsEligibleForInterstitial`, dans
  le tri d'eligibilite des offres. **Inutilisable comme predicat de frame.**
- **`ViewCommandExecutor$$HideInterstitialPopup()`** — non invoquee, trois raisons :
  (a) elle ECRIT et je ne peux pas l'observer (pas de reinject) ;
  (b) le decompile montre une garde (`this+0x530`, puis `+0x268`) dont l'echec tombe sur
  `FUN_1801f51f0` — *Subroutine does not return*, donc une LEVEE. Sur le chemin nominal, ou
  la mesure donne ZERO frame intersticielle, l'appeler leverait a chaque warmup ;
  (c) le geste est deja couvert DEUX fois par la voie UI — `dismissOpenPopups` a l'entree du
  cycle et le volet A de `runWedgeRemedy` a la sortie. Une troisieme voie serait un troisieme
  foyer pour un meme geste.

## `ProcessFinishSurrender` — meilleur capteur d'EVENEMENT, mauvais capteur de SORTIE

Xrefs verifiees (ghidra, `rnca9r7q6c`) : `idun.IdunMainView$$ProcessFinishSurrender` a
exactement DEUX appelants de code — `idun.IdunMainView$$OnBattleSurrender` (branche directe)
et `idun.IdunMainView$$ContinueSurrender` (branche interposee, l'`Action` que
`CampaignGameModeSource$$PauseSurrender(continueSurrender)` recoit puis rappelle). Le reste
est DATA : les deux appelants sont eux-memes invoques par delegue.

`CampaignGameModeSource$$PauseSurrender` **existe bien** (contrairement au doute initial) et
teste `IdunBattle.View.FSM.VisualBattleQuery$$IsBattleStarted` : deux delegues distincts selon
que la bataille a demarre. **Notre warmup se retire en phase de DEPLOIEMENT**, donc dans la
branche « pas demarree ».

⚠ **Deux raisons de ne PAS en faire le signal d'attente, et ce sont des mesures :**

1. **Il tire au DEBUT de la sortie, pas a la fin.** `ProcessFinishSurrender` precede
   `CleanupBattle` -> `EndBattleAndGoToMeta` -> `thor.Loader$$LoadBackToMeta` -> `LoadMetaScene`
   -> `LoadScene`. Rendre la main a ce moment, c'est la rendre AVANT le chargement de la scene
   meta — l'etat exact que #390 a mesure comme `no live IdunNavigation instance`. Le cran
   suivant du cycle (`ToCampaign`) echouerait. `retire/PauseMenu` marque la FIN.
2. **`UNCONDITIONAL_CALL` qualifie l'INSTRUCTION, pas le flot.** Dans les deux appelants,
   `ProcessFinishSurrender` est sur une branche — l'alternative etant
   `IdunMainView$$ProcessFinishBattle(this, 2)`, precedee de deux tests
   (`FUN_180002590(0x23, ...)` puis `(0x22, ...)`). « Exactement une fois par retraite » n'est
   donc pas etabli par la xref.

Il reste un capteur precieux pour DATER le debut de la sortie — cf. residu.

## Ce qui est livre

- `frida/hooks/features/warmup-retreat-signal.ts` — module PUR (aucun import), portant la
  logique, les motifs NOMMES et le plafond. Meme decoupe que `warmup-wedge-remedy.ts`.
- `frida/hooks/features/ui-windows.ts` — `ecouterTransitions()`, `TRANSITION` (foyer des
  libelles), `classe` sur les transitions.
- `frida/hooks/features/warmup-singletons.ts` — cablage ; les deux appelants publient
  desormais `reason` + `info` dans leur step.
- `frida/tools/probe-390-r2-signal-retraite.ts` — garde offline, **98/98**, trois etages
  (comportement avec doublures qui comptent / cablage sur source verbatim / le membre d'enum
  existe dans la table versionnee).

**Le plafond est un FILET, jamais l'instrument** : `RETREAT_SIGNAL_WAIT_MS = 45 000`,
dimensionne sur un chargement de scene (le budget que le cran 8 s'accorde deja pour le meme
phenomene — une frame `cache-debut` de chargement encadre les `retire`). Il n'est jamais paye
sur le chemin nominal. Les deux `waitFor` restants vivent UNIQUEMENT dans le filet, atteint
seulement si le signal n'a pas joue ; le probe garde ce compte a 2.

`signal ABSENT` (le jeu n'a pas emis) et `signal INDISPONIBLE` (aucun ancrage) sont deux
motifs DISTINCTS : les confondre ferait chercher la mauvaise cause.

## NON CONFRONTE LIVE

Le code livre n'a **jamais tourne** : la mesure ci-dessus a ete prise avec le bundle
PRECEDENT, via le RPC `uiWindowEvents`. Il faut un reinject, interdit a un agent. Le premier
warmup joue apres deploiement repondra en une ligne, puisque le step publie sa branche.

## Residus

- **#390-r6** — `ProcessFinishSurrender` comme capteur du DEBUT de sortie : il permettrait de
  DERIVER le plafond (duree mesuree du chargement) au lieu de le poser a 45 s, et de dater les
  deux branches (directe / interposee par `PauseSurrender`). Exige un ancrage neuf, donc une
  fenetre de reinject.
- **#390-r7** — `uiWindows` (`FindObjectsByType`) est INCOMPLET : il ne voit pas les
  `IScreenVisibility` qui ne sont pas des `ScreenVisibility` MonoBehaviour (mesure : 8 ecrans,
  aucun `Campaign`, alors que le journal en voit un). Son `devant` n'est donc pas « l'ecran
  devant » mais « le `ScreenVisibility` devant ».
- **#390-r8** — `ViewCommandExecutor$$HideInterstitialPopup` : etablir la garde
  (`this+0x530` / `+0x268`) et le slot de vtable `+0x428` avant tout invoke.
- Bonus non traite : `CompleteLocationHandler$$HandleClearReconciliationData(
  hasSurrenderedBeforeDeployment)` — dirait si le warmup coute reellement une defaite.
