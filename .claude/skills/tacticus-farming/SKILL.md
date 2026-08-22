---
name: tacticus-farming
description: Farmer la VRAIE campagne en rejouant un replay N fois — jetons, énergie et récompenses réels. MUST BE USED dès que l'utilisateur veut enchaîner des passes sur un nœud, rejouer une bataille gagnée, ou savoir ce qu'un geste COÛTE sur son compte. Encapsule une asymétrie contre-intuitive : entrer est gratuit, renoncer coûte une défaite.
---

# Farming — rejouer un replay sur le compte réel

⛔ **Ici, tout est RÉEL.** Chaque passe consomme un jeton et de l'énergie, et ce qui part au
serveur est irréversible. C'est l'exact opposé de `tacticus-sandbox`, qui ne touche à rien.

## Une commande

```powershell
python scripts/python/campagne_rejeu_reel.py --replay data/replays/campaign/<x>.json
python scripts/python/campagne_rejeu_reel.py --replay <...> --armer          # UNE passe
python scripts/python/campagne_rejeu_boucle.py --replay <...> --armer        # N passes
```

**Jouer la forme sans `--armer` d'abord, TOUJOURS.** Elle déroule les six crans gratuits et
refuse avant tout coût si le nœud n'est pas le bon — c'est là qu'on découvre qu'un replay ne
correspond pas, pas après avoir dépensé.

## Ce que chaque geste COÛTE — l'asymétrie, mesurée

| geste | coût réel |
|---|---|
| **entrer** dans la bataille | **RIEN** — 14 requêtes, **zéro `game-event`** (telemétrie `ct-live` + état `player2`) |
| **START** | **le jeton** — `HandleStartMatch` → `GenerateNewBattleId` → `StartCampaignLocation` |
| **renoncer** depuis `Setup` | **une DÉFAITE comptée** — `FAIL_LOCATION`, `timesLost` 1 → 2 ; jetons et énergie INTACTS |

⇒ **Entrer est gratuit ; RENONCER coûte.** Une fois dedans, les deux issues écrivent : jouer
(le START engage le jeton) ou se retirer (une défaite de plus au compteur).

⚠ Le fichier a d'abord affirmé le contraire **dans les deux sens** — que l'entrée engageait,
puis que la sortie était gratuite. Les deux étaient FAUX, et c'est le capteur de fil réseau qui
les a corrigés. Le cran 17 **remesure à chaque passage** : ne jamais re-déduire, lire ce qui est
sorti.

## Le plafond de passes se LIT, il ne se demande pas

`campaignNodeState.hasTokens` est un **booléen** — « peux-tu jouer ? », pas « combien de fois ? ».
Une boucle bâtie dessus ignore quand elle finira et réclame son plafond à un humain qui, lui, lit
le chiffre à l'écran. `jetons_restants()` descend la chaîne native et rend `5 / 6`.

`--passes N` ne peut que **baisser** ce plafond : un `N` plus grand est ramené aux jetons
disponibles — on ne planifie pas des passes qui seront refusées.

## Les pièges

1. **LE SEED S'ARME AVANT L'ENTRÉE.** `IdunRunner$$Initialize(runner, BC, seed, ...)` crée le
   `MersenneTwister` **à la construction** : une fois la bataille montée il est trop tard, et
   **rien ne le signale**. C'est ce qui impose l'ordre des crans 9 et 10 ; la leçon a coûté une
   soirée sur la chaîne sandbox.
   ⚠ Et l'imposer ne ment à personne : hors PvP synchrone, le seed est l'horloge locale tronquée
   en `Int32`, **aucun contact serveur**. Le champ `seed` que `CompleteCampaignLocation` remonte
   est donc le seed réellement joué, imposé ou non.

2. **LA BC DU NŒUD DOIT ÊTRE IDENTIQUE À CELLE DU REPLAY** — diff récursif, **zéro écart**
   (cran 3). C'est le seul cran qui peut refuser **avant tout coût**. La forge est une
   PRÉDICTION ; le cran 10 relit la BC **réellement montée**, qui est le FAIT. Les deux sont
   exigées.

3. **UN REPLAY SANS `EndReason` NE TERMINE PAS LA BATAILLE.** Ni `CompleteCampaignLocation` ni
   `FailCampaignLocation` ne partent. Le cran 0 lit ce champ et le DIT. Ce qui se passe après le
   dernier coup t'appartient : continuer à la main, ou te retirer — ce qui émet un
   `FailCampaignLocation`.

4. **ON NE RETRAITE JAMAIS UNE BATAILLE RÉELLE POUR FAIRE DE LA PLACE** (cran 5) : si une
   bataille tourne, le script REFUSE. La retraite est un geste qui coûte (cf. le tableau).

5. **La team affrontée n'est pas fabriquée** : elle vit dans `BattleConfiguration.PredefinedUnits`,
   portée par le nœud. On ne la pose pas, on VÉRIFIE qu'elle est celle du replay.

## Ce qu'on ne sait pas encore lire — dit plutôt que deviné

Le **lineup effectif** n'est pas confrontable AVANT l'entrée :
`CampaignGameModeSource$$GetBattleLineup(lineupIndex)` rend un `System.String[]`, et
`decoderRetour` passe par `type_get_class_or_element_class` — il nomme donc le retour `String`,
le lit comme une chaîne et rend `valeur: null`. Ce `null` ne distingue pas « tableau nul » de
« je ne sais pas lire un tableau » : on n'en tire RIEN. Le lineup est gaté au cran 14, sur la
bataille montée, avant le START.

⛔ **ET ON NE LE CONTOURNE PAS PAR UN INVOKE SUR UNE BOXE.** `GetUnitsForDeploymentHUD` rend un
`PooledList<String>` (type **valeur**, et **mis en pool**) : enchaîner un `get_Item` sur le
pointeur de boxe passe l'en-tête comme `this` et **TUE LE PROCESS** — mesuré le 2026-08-21,
minidump WER, session perdue. `viewJson` sur la même boxe rend `{"Count":6}` sans risque.

## Pourquoi une BOUCLE, et pas N appels à la main

Une reproduction qui marche UNE fois ne prouve pas qu'elle est déterministe — elle prouve
qu'elle a marché une fois. Ce qui se mesure, c'est la **constance** : même seed imposé, même BC,
même déploiement, mêmes coups, sur des batailles réellement distinctes côté serveur. Et la
constance ne se lit que si l'on garde la trace de **chaque** passe, y compris de celles qui
diffèrent. La boucle ne juge rien : elle compte, et relit l'état du nœud entre deux passes pour
dire ce qui a RÉELLEMENT changé sur le compte.

## Obtenir un replay

`replayFinAuto` capture **dans la pompe**, à la transition (`stage -> Finished`, `_runner -> null`).

⚠ **Un replay ne se SONDE pas, il se PREND À LA FRAME** : le runner disparaît à la fin de la
bataille, donc un sondage externe arrive toujours trop tard et rend
`runner has no ReplayRecorder` — un message qui accuse le mécanisme alors que seul le TIMING est
en cause. Un replay entier a déjà été perdu ainsi. Relire : `replayFinEtat {avecReplay: true}`.

## Ne pas faire

- **Ne jamais lancer ni relancer Tacticus** : geste UTILISATEUR.
- **Ne pas armer un montage SANDBOX avant une session de farm.** Mesuré le 2026-08-22 :
  `sandboxModeBcOverride` et `deploymentMemoire` restaient **armés** après un montage — le
  premier substituerait la BC de la bataille réelle, le second viderait le plateau pour rejouer
  la composition précédente. Le désarmement fiable est un **reinject** (session vierge), pas une
  liste de RPC qu'on risque d'oublier. Contrôle : `sandboxModeBcOverride {}` et
  `deploymentMemoire {}` doivent rendre `arme: false`, et `getBattleConfigPatchStatus` un
  `pending: null`.
- **Ne pas injecter d'unités dans une bataille réelle** pour gonfler un compteur d'événement :
  `CompleteCampaignLocation` remonte `battleId`, `turnsPlayed`, `battleDuration`, `seed` et
  `heroHp`. Le banc sandbox ne rapporte rien, et c'est voulu.

## Aller plus loin

- `scripts/python/campagne_rejeu_reel.py` — les **17 crans**, listés en tête de fichier, avec la
  frontière GRATUIT / `--armer` / LE SEUL CRAN QUI ENGAGE.
- `scripts/python/campagne_rejeu_boucle.py` — la boucle N passes et la lecture des jetons.
- `scripts/python/campagne_rejeu.py` — le même patron **en sandbox** (ne coûte rien), utile pour
  valider un replay avant de le jouer pour de vrai.
- `scripts/python/replay_rejouer.py` — le rejeu des coups : appariement, arrêt au premier écart,
  delta par `Apply`. Les trois chaînes le DÉLÈGUENT plutôt que de le recopier.
- `scripts/python/victoire_eclair.py` — le seuil de victoire éclair d'un nœud (pièces ×2), propre
  à chaque bataille.
