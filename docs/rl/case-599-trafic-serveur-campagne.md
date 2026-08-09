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

## `battleDuration` n'est PAS une durée

```
battleDuration = 63921911700761
    lu comme une duree      -> 739 837 jours (absurde)
    lu comme des ms/an 1    -> 2026-08-09T22:35:00 UTC  = l'instant du warmup
```

C'est un **horodatage absolu** (`DateTime.UtcNow.Ticks / 10_000`), pas une durée. Le nom du
champ ment ; s'en servir comme durée de bataille donnerait n'importe quoi.

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

⚠ **Aucun `StartCampaignLocationRequestDto` n'a été capturé** dans ce relevé, et c'est
COHÉRENT : on se retire au déploiement, la bataille ne démarre jamais. Le `Start` reste donc
NON OBSERVÉ — ne pas conclure de son absence ici qu'il n'est pas envoyé.

## Reproduire

```
netCaptureArm      # arme les 4 hooks (3 ctors de DTO + SerializeReplay). JAMAIS auto-arme.
<jouer / se retirer d'une bataille de campagne>
netCaptureDump     # { count, entries[] }   netCaptureDisarm pour retirer
```

Foyer : `frida/hooks/features/net-capture.ts`. Le rejeu n'est **jamais** rendu en entier —
longueur + préfixe de 240 caractères. Un `Dictionary<K,V>` n'est pas décodé (son `_count`
dépend de la version du runtime) : on publie `present`, pas un compte deviné.
