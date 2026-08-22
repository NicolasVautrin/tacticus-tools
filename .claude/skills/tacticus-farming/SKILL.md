---
name: tacticus-farming
description: Farmer la VRAIE campagne en rejouant un replay N fois — jetons, énergie et récompenses réels. MUST BE USED dès que l'utilisateur veut enchaîner des passes sur un nœud, rejouer une bataille gagnée, ou savoir ce qu'un geste COÛTE sur son compte. Encapsule une asymétrie contre-intuitive : entrer est gratuit, renoncer coûte une défaite.
---

# Farming — rejouer un replay sur le compte réel

⛔ **Ici, tout est RÉEL.** Chaque passe consomme un jeton et de l'énergie, et ce qui part au
serveur est irréversible. C'est l'exact opposé de `tacticus-sandbox`, qui ne touche à rien.

## La chaîne

```
tacticusplanner.app/plan/dailyRaids          QUI DROPPE QUOI
  -> scripts/planner/extraire-raids.js       (MCP Chrome, page CONNECTÉE)
  -> logs/planner-raids.json
  -> farming_plan.py                         L'ORDRE des nœuds a farmer
  -> campagne_rejeu_boucle.py                N passes sur le compte RÉEL
  -> replayFinAuto -> data/replays/_captures/
  -> classer_replay.py                       -> data/replays/campaign/
  -> farming_suivi.py                        ce qui a été GAGNÉ
```

## Par où commencer : `farming_plan.py`

```powershell
python scripts/python/farming_plan.py        # l'ordre, + les commandes prêtes à jouer
```

Il croise **trois** entrées : le plan du planner (qui droppe quoi), l'**inventaire vivant** du
jeu (le besoin restant) et `data/replays/campaign/` (ce qui est rejouable). Il classe les nœuds
par utilité et **imprime les commandes** — il ne joue RIEN.

- **Un nœud sert plusieurs matériaux** : son utilité est la **somme** des besoins restants qu'il
  touche. On ne divise pas par le nombre de matériaux — farmer un nœud qui en sert trois avance
  sur les trois à la fois.
- ⚠ **UN BESOIN N'EST PAS UNE DISPONIBILITÉ**, et le script a confondu les deux (2026-08-22) : il
  mettait en tête des nœuds **épuisés** (`campaign1` 28, utilité 27, **0 jeton sur 10**). La
  commande imprimée ne pouvait que se faire refuser. Les jetons sont donc **lus**, et un nœud
  sans jeton **sort des commandes en le disant**.
- ⚠ **Tri-état** : jetons `None` = **pas mesuré**, jamais rabattu sur 0. Un nœud dont la lecture
  échoue reste **proposé** — la boucle relit de toute façon. L'inverse ferait disparaître un
  nœud jouable pour une panne de lecture.

## Jouer une passe

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

## `--entree start` — dès qu'on CHANGE de nœud

`--entree` vaut `auto` par défaut : la voie d'entrée de la **première** passe est choisie sur le
signal d'écran, avec repli sur le runner.

⚠ **`Finished` ne dit pas QUELLE bataille vient de finir.** Mesuré le 2026-08-22 : après avoir
épuisé `campaign1` 28, la boucle lancée sur `elite2` 12 a choisi **retry** depuis l'écran de
victoire du **premier** — donc « play again » aurait rejoué `campaign1` 28. La chaîne l'a refusé
(rc 2, aucun jeton consommé), mais le diagnostic n'était lisible qu'après coup. **`--entree start`
tranche à la source**, et c'est ce qu'il faut passer dès qu'on change de nœud (`farming_plan.py`
le met dans toutes ses commandes).

⚠ **Le forçage ne vaut QUE pour la première passe**, et l'imposer à chaque tour casse la seconde :
mesuré le même jour, la passe 2 est refusée au cran 5 (« une bataille TOURNE DÉJÀ ») — normal, la
passe 1 vient de gagner et l'écran de fin est là. Ce qu'on impose, c'est **par où l'on entre quand
on arrive de l'extérieur** ; une fois dans le nœud, c'est le retry qui enchaîne.

## Classer les captures — `classer_replay.py`

```powershell
python scripts/python/classer_replay.py              # toutes les captures en attente
python scripts/python/classer_replay.py <fichier>    # une seule
```

`replayFinAuto` + `frida/host/replay-store.ts` déposent sous
`data/replays/_captures/<GameMode>-<seed>-f<frame>.json` — un nom qui porte le **mode** et le
**seed**, mais ni la campagne ni le nœud. Ce script les nomme.

- **L'identité se lit DANS le fichier, jamais dans son nom.** Le préfixe dit `Campaign`, pas
  `campaign1` : c'est `BattleConfiguration.Id` (`Campaign1_19`) qui porte campagne et nœud.
  Classer sur le nom de fichier rangerait une bataille sous une campagne qui n'est pas la sienne.
- **N'écrase JAMAIS** : un nom canonique déjà pris est un **refus**. Deux passages du même nœud
  portent des seeds différents, donc une collision signale un vrai problème.

⛔ **NE PAS CLASSER UNE CAPTURE DE BANC.** Mesuré le 2026-08-22 : `_captures/` contenait un
`Campaign1_06` portant **nos** vagues greffées (`UnitSpawningOverTime.Tiers` = 5 tours) et
`EndReason: None` — une bataille de test jamais terminée. Classée, elle serait rejouée **telle
quelle sur le compte**. Avant de classer, vérifier `BattleConfiguration.UnitSpawningOverTime` et
`BattleResult.EndReason` : des vagues inattendues ou un `EndReason` nul dénoncent un replay de
banc, pas une partie.

## Le suivi — `farming_suivi.py`

```powershell
python scripts/python/farming_suivi.py                 # besoin restant par matériau
python scripts/python/farming_suivi.py --jalon avant   # poser un jalon
python scripts/python/farming_suivi.py --depuis avant  # ce qui a été GAGNÉ depuis
```

⛔ **Le miroir sur disque ne sert à rien ici.** `user_progression.json` (AppData/LocalLow) ne se
rafraîchit PAS à chaque bataille — **37 minutes de retard** mesurées alors qu'une dizaine de raids
venaient d'être joués. On lit `UpgradeProgression$$GetAmount` **en mémoire**, par le RPC
`inventaireUpgrades`.

⚠ **LE PREMIER NOMBRE DU PLANNER EST UN PLAFOND**, `couvert = min(inventaire, requis)`. Une ligne
« 4/4 » ne dit **pas** « j'en ai 4 », elle dit « il y en a assez » — le stock réel valait 7. Le
reste se calcule sur la quantité lue **en jeu**. Et un écart ne se déclare pas par simple
inégalité : comparé à plat, le plafond fabrique un faux écart sur toute ligne couverte (2 écarts
annoncés, 2 faux, exactement les 2 lignes plafonnées).

| régime | ce qu'on peut conclure |
|---|---|
| `couvert < requis` | le plafond NE MORD PAS, le nombre **est** l'inventaire → égalité EXIGÉE |
| `couvert == requis` | plafonné → `jeu >= requis` exigé, **et rien de plus** ; un stock supérieur est NORMAL |

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

- `scripts/python/farming_plan.py` — l'ordre des nœuds : besoin restant × jetons lus.
- `scripts/python/farming_suivi.py` — le besoin restant et les jalons.
- `scripts/python/classer_replay.py` — nommer les captures de `_captures/`.
- `scripts/python/raids_plan.py` — la COUVERTURE : quels nœuds du plan n'ont pas de replay, et
  la commande de montage **sandbox** (gratuite) pour en capturer un.
- `scripts/planner/extraire-raids.js` — l'extraction du plan, via MCP Chrome sur la page
  connectée `tacticusplanner.app/plan/dailyRaids`.
- `scripts/python/campagne_rejeu_reel.py` — les **17 crans**, listés en tête de fichier, avec la
  frontière GRATUIT / `--armer` / LE SEUL CRAN QUI ENGAGE.
- `scripts/python/campagne_rejeu_boucle.py` — la boucle N passes et la lecture des jetons.
- `scripts/python/campagne_rejeu.py` — le même patron **en sandbox** (ne coûte rien), utile pour
  valider un replay avant de le jouer pour de vrai.
- `scripts/python/replay_rejouer.py` — le rejeu des coups : appariement, arrêt au premier écart,
  delta par `Apply`. Les trois chaînes le DÉLÈGUENT plutôt que de le recopier.
- `scripts/python/victoire_eclair.py` — le seuil de victoire éclair d'un nœud (pièces ×2), propre
  à chaque bataille.
