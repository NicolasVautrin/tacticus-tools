# `#599` — ce que le client ENVOIE au serveur pour une bataille de campagne

> **QUESTION D'ORIGINE, TRANCHÉE : on n'uprank PAS.** Cette fiche est née de « peut-on uprank
> une unité sur le live ? ». Décision de l'utilisateur le 2026-08-10, sur les mesures
> ci-dessous : **non**. Le roster est déclaré au serveur **deux fois par bataille** (`units` au
> lancement, `heroDetails` à la fin) et le rejeu — qui porte l'état initial complet, la graine
> et les événements de RNG — **part réellement** (mesuré sur le fil). Un rang local serait donc
> annoncé en clair ET incohérent avec ce que le serveur peut re-simuler, sans le breadcrumb ni
> le `SendPlayerPowerConcern` que la voie légitime produit.
>
> ⚠ Que le serveur **vérifie** n'est PAS établi — seulement qu'il **reçoit**. La décision ne
> repose pas sur cette inférence mais sur l'asymétrie : gain marginal, perte = le compte.
>
> ⇒ **Le besoin réel (des unités à rang arbitraire pour valider le moteur) passe par le
> harnais** — `catalog_inject`, `buildNormalizedBC`, `rl_duel build --unit-stat` — qui ne
> touche NI le compte NI le serveur. Ne pas rouvrir la piste live.

Mesuré le 2026-08-10 (session 25, build `rnca9r7q6c`), capteur `net-capture` armé à la demande.
Ce n'est pas la forme lue au décompilé : c'est une charge **observée**.

## Le cycle de vie, côté requêtes

| moment | DTO | champs |
|---|---|---|
| lancement | `thor.Client.DTO.Events.GameEvents.Request.StartCampaignLocationRequestDto` | 9 |
| victoire | `…Request.CompleteCampaignLocationRequestDto` | 23 |
| défaite | `…Request.FailCampaignLocationRequestDto` | 19 |

Les deux DTO de fin héritent d'`AEndCampaignLocationRequestDto` → `AEndLocationRequestDto`
(`idun.Idun.Source.Thor.Client.DTO.Events.Request.Location`), qui porte le tronc commun :
`seed`, `replay`, `battleId`, `heroDetails`, `unitsXp`, `heroHP`/`enemyHP`, `rewards`,
`taskProgress`, `trackerChanges`, `turnsPlayed`, `battleDuration`, `unitsKilled`,
`lootMultiplierPct`, `machineOfWarDetails`, `machineOfWarAmmoUsed`. La victoire y ajoute
`stars`, `gotLightningVictory`, `whereToFind`, `difficultyIndex`.

`StartCampaignLocationRequestDto` porte `units` (le roster déclaré), `lineupIndex`,
`battleMode`, `battleSource`, `battleId`, et l'identité du nœud.

## Le rejeu part POUR DE VRAI, et il est gros

Charge observée sur une retraite au déploiement :

```
replay  len = 75 800 caracteres,  prefixe "H4sIALQceWoA/+y9a3PbOLY2..."
```

Décodé : premiers octets `1f 8b 08 00` — **gzip**, puis base64. Donc ~**57 Ko compressés**.

⚠ **Et cette bataille avait `turnsPlayed = 0`.** Un rejeu de 57 Ko pour zéro tour joué : la
charge ne contient donc pas que les actions, elle porte **l'état initial complet** (plateau,
unités, configuration). Avec `seed` à côté, le serveur a tout pour re-simuler.

`IdunBattleLogic.Replay.ReplayRecorder` enregistre le flux de messages **et** le tampon
d'événements RNG (`SaveCurrentOutputStreamBufferToLastMessage`,
`SaveCurrentRngEventBufferToLastMessage`) ;
`thor.Scripts.Idun.Source.IdunBattle.ReplaySerialization.ReplaySerializer$$SerializeReplay`
sérialise. `replay` est un **paramètre du constructeur**, pas un extra optionnel.

### `#599-r2` — le rejeu part VRAIMENT : mesuré SUR LE FIL, pas déduit du DTO

⚠ **Hooker le ctor du DTO ne prouve que la CONSTRUCTION.** La sérialisation pouvait omettre le
champ, la charge être tronquée, l'événement ne jamais quitter la file. Cette fiche a d'abord
écrit « le rejeu part POUR DE VRAI » sur cette seule base — c'était la même faute qu'un
`ok:true` lu comme un effet.

Le point de fil est `Snowprint.ClientSdk.Web.WwwWebHelper$$PostString(url, postData, …)`.
Chaîne complète : `GameEventService$$CompleteCampaignLocation(…, replay:String, …)` →
`GameEventService$$SendGameEvent` → `ClientAPI$$SendGameEvent` →
`GameEventQueueProcesser$$AddToQueue` (une FILE — d'où l'envoi différé) → `PostString`.

Mesuré le 2026-08-10 (session 29, victoire sur `Campaign1_06`) :

```
ReplaySerializer.SerializeReplay          82 324 car
CompleteCampaignLocationRequestDto.replay 82 324 car
POST https://api-live.loki.snowprintstudios.com/game-event/game3/
     corps = 85 702 car   marque gzip "H4sI" PRESENTE, offset 2982
POST https://ct-live.loki.snowprintstudios.com/ct/userId/...
     corps = 658 car      pas de marque   (telemetrie, sans rejeu)
```

⇒ **Le corps posté = le rejeu + 3 378 caractères d'enveloppe**, et la marque gzip tombe à
l'offset 2982, donc DANS le JSON, là où commence la valeur de `replay`. La taille seule aurait
laissé la question ouverte ; c'est la **marque** qui tranche.

⚠ Reste NON ÉTABLI : que le serveur **vérifie** ce rejeu plutôt que de l'archiver. On ne peut
pas le savoir d'ici. Ce qu'on sait : il le REÇOIT, et `rewards` est **réclamé par le client** —
ce qui n'est tenable que si quelque chose vérifie.

### Le module est désormais WIRE-ONLY — et il a fallu TROIS portes, pas une

Les hooks de DTO sont **retirés** : le point de fil est à la fois plus sûr (c'est ce qui part)
et plus large (il ignore les types, donc il attrape toutes les requêtes, pas seulement les
trois DTO qu'on avait pensé à nommer).

⚠ **Et `PostString` seul n'aurait PAS suffi.** `WwwWebHelper` expose trois portes —
`PostString(url, String, …)`, `PostBytes(url, Byte[], …)`, `PostData(url, Byte[], …)`. Mesuré
sur un simple geste de navigation (session 30) :

```
PostString  len 790   ct-live.loki.snowprintstudios.com/ct/userId/...
PostData    len 516   ct-live.loki.snowprintstudios.com/ct/userId/...
```

Deux tailles **différentes**, donc deux requêtes distinctes — pas la même charge vue deux fois
à travers un empilement d'appels. `PostData` est une porte à part entière : ancrer la seule
`PostString` aurait laissé cette requête sans trace, et « on capte tout ce qui part » aurait
été FAUX sans qu'aucun symptôme ne le dise. Le journal publie `via` pour que la question reste
mesurable au lieu d'être supposée.

⚠ Le corps est conservé EN ENTIER tant qu'un budget global (2 M caractères) le permet ; au-delà
on ne garde que taille + préfixe et `corpsOmis` compte les renoncements — un journal qui tronque
en silence se lirait comme complet.

**Confirmé par la comparaison des deux relevés** : une bataille de 2 tours avec 8 morts pèse
`83 644` caractères contre `75 800` pour zéro tour, soit **+7 844 (+10 %)**. Les 90 % restants
sont l'état initial, qui part quoi qu'il arrive.

## La charge d'une VICTOIRE (nœud 14, 3 étoiles)

```
StartCampaignLocationRequestDto
    battleId "366837210626300529"   locationIndex 13  (= noeud 14)
    campaignType "Standard"  campaignId "campaign1"
    units.size 5   lineupIndex 5   battleMode 0   battleSource 0   whereToFind false

CompleteCampaignLocationRequestDto
    battleId "366837210626300529"      <- IDENTIQUE au lancement
    seed 2136456800     replay 83 644 car
    stars 3   gotLightningVictory false   difficultyIndex 0   lootMultiplierPct 0
    turnsPlayed 2   unitsKilled 8   battleDuration 43755
    heroDetails.size 5   rewards.size 4   taskProgress.size 10   trackerChanges.size 1
    unitsXp present   heroHP / enemyHP present   machineOfWarDetails null
```

⇒ **`battleId` apparie le lancement et la fin**, et il est frappé par le client. ⇒ Le client
déclare son roster **deux fois** : `units` au lancement, `heroDetails` à la fin. ⇒ Il **réclame
ses 4 récompenses**, ses 10 progressions de tâche et son XP.

## `battleDuration` EST une durée — et sa valeur absurde est un SYMPTÔME

Deux relevés, et c'est le second qui donne la lecture juste :

```
victoire (noeud 14, 2 tours)   battleDuration =          43755   -> 43,8 s : la duree reelle
retraite (au deploiement)      battleDuration = 63921911700761   -> 2026-08-09T22:35:00 UTC
                                                                    = l'instant de l'amorce
```

Une seule explication couvre les deux : **`battleDuration = fin - debut`, et sur une bataille
qui n'a jamais démarré le `debut` vaut `0`** — la soustraction rend alors l'horodatage absolu
brut. Le champ ne ment pas ; il **signale** que la bataille n'a pas commencé.

⚠ Cette fiche a d'abord conclu « c'est un horodatage, le nom du champ ment », sur le SEUL
relevé de la retraite. C'était faux, et l'erreur est instructive : un champ mesuré dans un
régime dégénéré (zéro tour, jamais démarré) se lit de travers, et une seule observation ne
permettait pas de le savoir. Il a fallu le cas NON dégénéré pour trancher.

## ⚠ NOTRE AMORCE ENVOIE UNE DÉFAITE ENREGISTRÉE, À CHAQUE FOIS

La capture ci-dessus **est** celle de l'amorce. Sa séquence `click-node` → `click-play` →
`wait-deployment-stable` → `retreat-to-campaign` produit :

```
FailCampaignLocationRequestDto
    campaignType "Standard"  campaignId "campaign1"  locationIndex 60   (= noeud 61)
    seed 912888571   turnsPlayed 0   unitsKilled 0   rewards.size 0
    heroDetails null   heroHP null   battleId "0"
    replay 75 800 car
```

⇒ **Une retraite au déploiement est comptée comme une DÉFAITE** et poussée au serveur, avec
son rejeu. L'amorce tourne à chaque (ré)inject : chaque fenêtre de harnais dépose donc une
défaite de plus sur le nœud 61 du compte. Personne ne l'avait mesuré — l'amorce était réputé
neutre parce qu'il « revient sur la campagne ».

⚠ **Aucun `StartCampaignLocationRequestDto` dans ce relevé-là**, et c'est COHÉRENT : on se
retire au déploiement, la bataille ne démarre jamais. Confirmé depuis par la victoire, qui en
émet un — l'absence était bien un fait sur l'amorce, pas sur le `Start`.

## `#599-r1` — voir qu'un nœud est INJOUABLE : à moitié résolu, et je dis quelle moitié

Le bouton du nœud **2** rend `ok:true` à **cinq** clics d'affilée sans rien ouvrir ; le nœud
**14**, cliqué juste après par le même code, ouvre du premier coup. Pas un clic avalé — un
handler inerte.

⚠ **« mannequin FTUE » et « nœud de tutoriel » sont INDÉPENDANTS**, et les confondre a produit
une borne inventée. La fiche a d'abord écrit « les nœuds 1..13 ne sont pas rejouables », déduit
de « campaign1 oppose ses mannequins FTUE sur ses premiers nœuds ». Or le nœud **14** oppose
lui aussi des `necroNpc1TutWarriorFTUEtest` et **se joue très bien**. Les nœuds de tutoriel
d'Indomitus sont **1 à 5**.

**Le grisé est invisible à notre outillage, structurellement.** Le jeu grise le bouton d'un
nœud injouable ; `uiList` n'énumère que des `UnityEngine.UI.Button` et ne voit ni l'`Image`
d'habillage ni l'icône de verrou qui vivent DANS le bouton. Et ce n'est pas l'état désactivé du
`Selectable` : le nœud 2 rapporte `interactable: true`.

**Lire la CAUSE plutôt que le teint** — RPC `campaignNodeState({locationIndex})` (0-basé), sur
`IdunMetaLogic.UserProgress.CampaignProgression` (`_campaignProgression` du
`CampaignGameModeSource`, offset résolu par NOM) :

```
IsLocationReached · HasTokensToPlayCampaignBattle · HasStaminaToPlayCampaignBattle · IsLocked
HasWonLocation · GetTimesWon · GetTimesLost · GetStarsOfLocation · IsInCampaignTutorial
```

Contre-épreuve passée (un lecteur qui ne peut pas échouer ne vaut rien) :
`locationIndex 999` → `reached=false, stars=0, timesWon=0` ; `-5` → `null` (PAS MESURÉ, pas 0) ;
nœud 14 → **`timesWon=14, timesLost=2`**. Donc les valeurs sont réelles et varient.

⚠ **ET IL NE RÉPOND PAS À LA QUESTION POSÉE.** Sur le nœud 2 — celui qui refuse — il rend
`reached=true, tokens=true, stamina=true, locked=false, won=true, stars=3`, soit **tout vert**.
Le refus d'un nœud de tutoriel ne vit donc PAS dans la couche progression ; il est au-dessus,
dans l'écran ou le widget. `campaignNodeState` répond « la progression bloque-t-elle ? », pas
« ce nœud est-il jouable ? » — s'en servir pour la seconde question donnerait un FAUX VERT.

### La moitié manquante est RÉSOLUE, et hors ligne

Frontière **mesurée** (clic, popup attendu) : nœuds **1,2,3,4,5 refusent · 6 et 7 ouvrent**.
Le catalogue (`dumpCampaignCatalog`, `Standard` → `campaign1`, 75 batailles) donne le
discriminant :

| critère | nœuds concernés | partitionne {1..5} ? |
|---|---|---|
| `staminaCost == 0` | **1,2,3,4,5** | **OUI, exactement** |
| `maxAttempts == null` | **1,2,3,4,5** | **OUI, exactement** |
| `boardId` contient `_t_` | 1,2,3,4,5,**7,8,11** | NON — le 7 s'ouvre |

⚠ Le `_t_` du `boardId` est le piège : il **ressemble** à un marqueur de tutoriel et se réfute
sur un seul contre-exemple mesuré. Lire `staminaCost`/`maxAttempts`, jamais le nom du board.

⚠ **`maxAttempts` n'est pas 5** sur ce corpus : `null` ×5, `3` ×9, `10` ×57, `7` ×4. Le
plafond par nœud existe donc bien mais varie ; sa sémantique exacte (parties ? drops ?) reste
NON ÉTABLIE — ne pas la citer comme le « 5 parties par jour ».

### Pourquoi je ne VOYAIS pas le refus : il n'a aucun `Button`

Mesuré en photographiant l'écran avant/après un clic sur le nœud 2, par MULTIPLICITÉ :

```
boutons ACTIFS      48 -> 48      apparus 0   disparus 0
boutons + inactifs 455 -> 455     apparus 0   disparus 0
```

Ce qui s'affiche ne porte **aucun `UnityEngine.UI.Button`** — ce n'est pas une détection
ratée, c'est hors de l'énumération. Et `vue.popup()` DÉRIVE les popups des *chemins de
boutons* : sans bouton, aucun chemin, donc « rien ne s'est passé ». Cohérent avec
`IdunLocalization.Tooltips$$Campaign_TutorialLevel(title, description)` — une **infobulle**,
donc du texte.

⇒ Le remède n'est pas un meilleur filtre, et ce n'est pas non plus d'ajouter des types un par
un (`TMP_Text`, puis `Image`, puis…) : c'est un **point d'interception unique**, en dessous.

### `GameObject.SetActive` — le point unique, validé par ses DEUX témoins

`frida/hooks/features/ui-mutations.ts`, RPC `uiMutations({start|stop|clear|depuis|max})`.
Un seul ancrage, sur `UnityEngine.GameObject$$SetActive` — le goulot par lequel TOUT affichage
passe, quel que soit le composant.

Mesuré le 2026-08-10 (session 27), le couple témoin positif / cas en question :

```
noeud 6 (OUVRE)   +457 mutations   ButtonPortrait_..., Skull, RemoveButton, ...   (temoin positif)
noeud 2 (REFUSE)   +31 mutations   ON DynamicTooltip(Clone)
                                   ON DynamicTooltip_Title(Clone)
                                   ON DynamicTooltip_Separator(Clone)
                                   ON DynamicTooltip_Description(Clone)
```

⇒ **Une infobulle `DynamicTooltip` à Titre / Séparateur / Description** — exactement la forme
de `IdunLocalization.Tooltips$$Campaign_TutorialLevel(title, description)` lu au décompilé. La
prédiction offline est confirmée par la capture live.

Récapitulatif des trois couches sur le MÊME clic (nœud 2) :

| capteur | granularité | ce qu'il voit du refus |
|---|---|---|
| `uiListAll` (+ inactifs) | type `Button` | **0** — l'infobulle n'a aucun `Button` |
| `uiWindowEvents` | ÉCRAN (`ScreenVisibilityManager`) | **0** — le refus est sous cette couche |
| `uiMutations` | **objet** (`GameObject.SetActive`) | **31**, dont l'infobulle nommée |

⚠ La séquence relevée est `ON, ON, off ×4, ON ×4` : le widget est **recyclé**, pas créé — ce
qui confirme le `idun.ui.widgetPool.IWidgetPool` et explique que `SetActive` suffise ici. La
réserve écrite dans l'en-tête du module (un widget INSTANCIÉ n'appellerait pas `SetActive`)
n'est donc pas levée en général, seulement sur ce cas.

⚠ Volume mesuré : 31 pour une infobulle, 457 pour un popup — loin du plafond de 800,
`ecartes: 0`. Le plafond est donc dimensionné pour UNE action ; il ne l'est pas pour une
session laissée armée, et le module n'est pas fait pour ça (armé à la demande, fenêtré).

### `uiTexts` — et le jeu le disait depuis le début

`uiMutations` donne le NOM des objets, pas leur CONTENU. D'où `uiTexts({inclureInactifs?,
nonVide?, contient?, max?})` dans `ui-nav.ts` : il énumère les mêmes `texteSystemTypes` que
`lireLabel` (`TMP_Text` d'abord — la BASE, donc `TextMeshProUGUI` compris —, `UI.Text` en
repli) et rend `{path, text, active}`. C'est la première fois qu'on peut lire **ce qui est
écrit à l'écran** plutôt que déduire d'un nom d'objet.

Sur le clic du nœud 2 :

```
DynamicTooltip_Title(Clone)        "Tutorial Battle"
DynamicTooltip_Description(Clone)  "You already finished this tutorial"
```

⇒ **Le jeu répondait explicitement, en toutes lettres, depuis le premier clic.** Il a fallu
trois couches d'outillage pour l'entendre — et j'ai d'abord cliqué cinq fois de plus, puis
inventé une borne « 1..13 », puis cherché un marqueur dans le `boardId`. La leçon n'est pas
« il manquait un capteur » : c'est qu'un outil qui ne rend QUE des `Button` transforme un
message clair en silence, et qu'un silence se raconte trop facilement.

⚠ `types` DIT sur quoi la mesure a porté (`['type0:30','type1:0']` = 30 `TMP_Text`, 0
`UI.Text`) : une liste vide avec `types: []` serait une panne de résolution, pas un écran sans
texte.

Piste non aboutie pour la moitié manquante : le jeu a bien la notion
(`GetTotalAmountOfStarsClaimedExcludingTutorialLevels`, infobulle
`IdunLocalization.Tooltips$$Campaign_TutorialLevel`, `CampaignProgression$$GetTutorialToTrigger`),
mais l'infobulle n'a que des xrefs DATA et la classe du bouton de campagne standard n'apparaît
pas dans les tables — ce qui, par la règle du dépôt, ne prouve rien.

⚠ **Le plafond de 5 parties est JOURNALIER, pas cumulé** : `GetTimesWon` rend **14** sur le
nœud 14. Le budget du jour est `HasTokensToPlayCampaignBattle` + `CampaignTokenProgression`
(`RefillTokensIfResetDue`, `GetNextTokenResetTime`, `CanSpendDefaultAmount`). Au relevé, les 13
nœuds échantillonnés ont **tous** leurs jetons.

⇒ **Une retraite ne consomme PAS de jeton** — connaissance de l'utilisateur (2026-08-10), pas
une mesure de notre part ; question CLOSE, ne pas aller la re-mesurer. Le coût de l'amorce est
donc une **ligne de défaite dans les statistiques** du nœud, pas une ressource : cosmétique,
mais poussée au serveur avec son rejeu à chaque exécution. L'interdiction de l'amorce
([[feedback-no-amorce-until-asked]]) tient indépendamment — c'est une décision de
l'utilisateur, pas une conséquence de ce coût.

## Reproduire

```
netCaptureArm      # arme les 4 hooks (3 ctors de DTO + SerializeReplay). JAMAIS auto-arme.
<jouer / se retirer d'une bataille de campagne>
netCaptureDump     # { count, entries[] }   netCaptureDisarm pour retirer
```

Foyer : `frida/hooks/features/net-capture.ts`. Le rejeu n'est **jamais** rendu en entier —
longueur + préfixe de 240 caractères. Un `Dictionary<K,V>` n'est pas décodé (son `_count`
dépend de la version du runtime) : on publie `present`, pas un compte deviné.
