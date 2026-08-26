# case-10047 — LE GARDE-JETON EST STRUCTURELLEMENT TROP TARD EN PvP

Rapporte par l'utilisateur le 2026-08-26, build `t6dpr4k06g`, session 148 : la popup du garde
s'affiche **alors que le jeton est deja depense**. La premisse du module est donc FAUSSE pour ce
mode-la.

## Ce que le garde suppose, et ou ca a ete mesure

`garde-jeton.ts` s'ancre sur `IdunBattle.View.FSM.VisualBattleQuery$$IsMinUnitAmountToBringToStartBattleReached`,
consulte par `IdunBattle.View.FSM.UnitDeployment.UnitDeploymentState$$StartBattle`. La premisse
ecrite en tete du module -- << entrer est GRATUIT, c'est le START qui engage le jeton >> -- vient
de la chaine CAMPAGNE : `AGameModeSource$$HandleStartMatch` -> `GenerateNewBattleId` ->
`StartCampaignLocation`. Les mesures du module (session 148) ont ete prises en **sandbox guerre de
guilde**, ou rien n'est engage.

**Aucune mesure n'a jamais porte sur le PvP.** Le chemin bloquant n'y a ete exerce pour la
premiere fois que le 2026-08-26, sur une vraie bataille -- et c'est la que la premisse tombe.

## Pourquoi le PvP n'a pas la meme forme

- `PvpGameModeSource` **n'override PAS** `HandleStartMatch` (table des symboles : la classe porte
  `LoadBattleInternal`, `GetBattleLineup`, `HandleFinishBattle`... pas de `HandleStartMatch`). La
  chaine campagne dont la premisse est tiree ne s'applique pas telle quelle.
- L'ecran qui precede est `idun.Meta.View.Hud.PvpBattlePreviewPopup`, et il porte deja le COUT :
  `$$ShowTokenCost`, `$$ShowStaminaWidget`, et un etat de bouton `Pvp_BattleButton_OutOfBattleToken`
  (literal). Le jeton est donc une affaire de **cet ecran-la**, pas de la FSM de deploiement.
- `$$HandleOnStartBattleTapped` mene a `IdunMetaLogic.UserProgress.PvP.PvpProgression$$LoadPvpBattle`,
  qui dialogue avec le serveur (`Contract$$Require`, dispatch par slot d'interface) AVANT que
  l'ecran de deploiement n'existe.

⇒ Notre predicat est **en aval** de tout ca. En PvP il ne peut, par construction, refuser que ce
qui est deja paye.

## Statut de chaque affirmation

| affirmation | statut |
|---|---|
| le jeton est parti quand la popup s'affiche | **MESURE** (observation utilisateur, 2026-08-26) |
| `PvpGameModeSource` n'a pas de `HandleStartMatch` | **ETABLI** (table des symboles) |
| le cout est affiche par le popup de previsualisation | **ETABLI** (symboles + literal) |
| le jeton est preleve exactement au tap de << Battle >> | **NON MESURE** -- plausible, non prouve |

⚠ Le dernier point ne se prouve pas au decompile seul (les corps sont des dispatchs par slot) :
il faut lire la stamina PvP avant/apres le tap, et ce test **coute un jeton**.

## Ce qu'il faudrait pour que le garde serve en PvP

Un second ancrage, **en amont** : `idun.Meta.View.Hud.PvpBattlePreviewPopup$$HandleOnStartBattleTapped`
(ou `PvpProgression$$LoadPvpBattle`), avec la meme discipline -- echec OUVERT, exemption de ce
qu'on ne sait pas debloquer, popup differee et etranglee. Demande un rebuild + reinject.

## En attendant

`gardeJetonArmer {bloquer: false}` (pose le 2026-08-26 a la demande de l'utilisateur) : l'ancrage
observe toujours, `decisions` reste lisible, plus aucun refus. Le register rearme a `true` au
prochain reinject.

⚠ **Ne pas couper la POPUP seule** (`popup: false`) : le refus subsisterait et deviendrait MUET --
un START qui ne part pas, sans rien pour le dire.
