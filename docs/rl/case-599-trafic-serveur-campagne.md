# `#599` — ce que le client ENVOIE au serveur pour une bataille de campagne

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

⚠ Ce qui reste NON ÉTABLI : que le serveur **vérifie** ce rejeu plutôt que de l'archiver. On
ne peut pas le savoir d'ici. Ce qu'on sait, c'est que le client est bâti pour le rendre
possible, et que `rewards` est **réclamé par le client** — ce qui n'est tenable que si
quelque chose vérifie.

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
                                                                    = l'instant du warmup
```

Une seule explication couvre les deux : **`battleDuration = fin - debut`, et sur une bataille
qui n'a jamais démarré le `debut` vaut `0`** — la soustraction rend alors l'horodatage absolu
brut. Le champ ne ment pas ; il **signale** que la bataille n'a pas commencé.

⚠ Cette fiche a d'abord conclu « c'est un horodatage, le nom du champ ment », sur le SEUL
relevé de la retraite. C'était faux, et l'erreur est instructive : un champ mesuré dans un
régime dégénéré (zéro tour, jamais démarré) se lit de travers, et une seule observation ne
permettait pas de le savoir. Il a fallu le cas NON dégénéré pour trancher.

## ⚠ NOTRE WARMUP ENVOIE UNE DÉFAITE ENREGISTRÉE, À CHAQUE FOIS

La capture ci-dessus **est** celle du warmup. Sa séquence `click-node` → `click-play` →
`wait-deployment-stable` → `retreat-to-campaign` produit :

```
FailCampaignLocationRequestDto
    campaignType "Standard"  campaignId "campaign1"  locationIndex 60   (= noeud 61)
    seed 912888571   turnsPlayed 0   unitsKilled 0   rewards.size 0
    heroDetails null   heroHP null   battleId "0"
    replay 75 800 car
```

⇒ **Une retraite au déploiement est comptée comme une DÉFAITE** et poussée au serveur, avec
son rejeu. Le warmup tourne à chaque (ré)inject : chaque fenêtre de harnais dépose donc une
défaite de plus sur le nœud 61 du compte. Personne ne l'avait mesuré — le warmup était réputé
neutre parce qu'il « revient sur la campagne ».

⚠ **Aucun `StartCampaignLocationRequestDto` dans ce relevé-là**, et c'est COHÉRENT : on se
retire au déploiement, la bataille ne démarre jamais. Confirmé depuis par la victoire, qui en
émet un — l'absence était bien un fait sur le warmup, pas sur le `Start`.

## Les nœuds 1..13 ne sont pas rejouables

Mesuré en cherchant une bataille facile : le bouton du nœud **2** rend `ok:true` à **cinq**
clics d'affilée et **rien ne s'ouvre** ; le nœud **14**, cliqué juste après par le même code,
ouvre l'aperçu du premier coup. Ce n'est donc pas un clic avalé (la parade « rejouer » ne
change rien) mais un handler qui ne fait rien. Cohérent avec le fait que campaign1 oppose ses
mannequins FTUE sur ses premiers nœuds.

⚠ Seul le nœud 2 a été mesuré. « 1..13 » est une INFÉRENCE depuis la borne FTUE connue, pas un
balayage — ne pas la citer comme mesurée.

## Reproduire

```
netCaptureArm      # arme les 4 hooks (3 ctors de DTO + SerializeReplay). JAMAIS auto-arme.
<jouer / se retirer d'une bataille de campagne>
netCaptureDump     # { count, entries[] }   netCaptureDisarm pour retirer
```

Foyer : `frida/hooks/features/net-capture.ts`. Le rejeu n'est **jamais** rendu en entier —
longueur + préfixe de 240 caractères. Un `Dictionary<K,V>` n'est pas décodé (son `_count`
dépend de la version du runtime) : on publie `present`, pas un compte deviné.
