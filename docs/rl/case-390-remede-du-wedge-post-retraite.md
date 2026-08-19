# #390 — l'amorce APPLIQUE le remède qu'il nommait

## 1. La question binaire

> Quand le cran 8 de l'amorce (`wait-back-to-campaign`) expire, le cycle a-t-il **appliqué
> lui-même** le remède qu'il nomme dans son propre message — et un lecteur de `steps`
> peut-il distinguer **« remède non tenté » / « tenté et sans effet » / « tenté et
> INAPPLICABLE »** ?

Avant : **non** aux deux. Le cran rendait `ok: false` avec un message disant littéralement
`try rpc navToCampaign, else relaunch the game`, alors que ce RPC est enregistré vingt lignes
plus bas dans le même fichier. Un seul état d'échec, zéro tentative. Le suivi de tâche portait
`navToCampaign 2/2` : les deux fois où un humain l'a tapé, il a débloqué.

## 2. La RE — ce qui autorise le remède, et ce qui le borne

Chaîne native du retour post-retraite (build `rnca9r7q6c`) :

```
thor.Idun.Source.Thor.Menu.PauseMenu$$OnBackToMapPressed
  -> IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$PauseSurrender
  -> idun.IdunMainView$$ProcessFinishSurrender
  -> idun.IdunMainView$$CleanupBattle
  -> idun.IdunMainView$$EndBattleAndGoToMeta
  -> thor.Loader$$LoadBackToMeta -> thor.Loader$$LoadMeta
  -> thor.Loader$$LoadMetaScene -> thor.Loader$$LoadScene
```

**Le retour au méta est un CHARGEMENT DE SCÈNE, pas une navigation d'écran.**
`idun.UI.IdunNavigation$$ToCampaign` n'est sur **aucun** maillon : ses quatre appelants sont
`idun.Tutorials.TutorialManager$$StartTutorial` et les trois
`idun.shared.commands.ViewCommandExecutor$$ToCampaign` / `$$ToCampaignBattle` / `$$ToDeepLink`.
Le remède n'est donc pas « rejouer ce que le jeu fait » : c'est une voie **distincte**, qui agit
sur la scène méta **une fois chargée**.

Deux faits tranchent ce que le remède peut et ne peut pas :

- **`thor.Loader$$LoadScene` refuse EN SILENCE** de charger quand un chargement est déjà en
  cours (`_scenesToLoad.Count >= 1`, ou `thor.Loader$$IsLoadingInternal` c.-à-d.
  `_loadingStep > 0`) : il journalise par `idun.Idun.Source.Util.Logging.IdunViewLogger$$Log`
  et retourne. Dans ce régime la scène méta n'existe pas, donc `IdunNavigation` non plus →
  le remède est **inapplicable**, et c'est un état à **nommer**, pas à réessayer.
- **`idun.UI.IdunNavigation$$ToCampaign` n'a AUCUN court-circuit « déjà sur cet écran »** —
  contrairement à ce que le commentaire de l'étape 2 affirmait. Elle exécute toujours
  `UnityEngine.PlayerPrefs$$SetString` +
  `idun.UI.Screens.CampaignScreen.IdunCampaignScreen$$SetCampaignToShow` +
  `idun.UI.IdunNavigation$$ShowScreenAndHideOthers(screen, null, createScreenInstance: true)`,
  qui masque les autres écrans. C'est ce qui la rend capable de sortir d'un écran méta qui
  n'est pas la campagne.

## 3. Le message du cran 8 était FAUX — constat structurel, pas hypothèse

Depuis #332, le prédicat du cran 8 (`findButtonBySuffix(r, NODE_SUFFIX)`) est **exactement**
celui qui valide déjà le dernier clic de l'étape 7 (`retreatToCampaign`, maillon
`RETREAT_CONFIRM_KEY` → `expect: la campagne`). Atteindre le cran 8 implique donc que le nœud
de campagne **a été vu** quelques millisecondes plus tôt.

⇒ Le cran ne peut plus signaler « la campagne n'est jamais remontée » — ce régime est attrapé
par l'étape 7, sous le nom `retreat-to-campaign`. Il ne reste **qu'un** régime possible : le
nœud est revenu puis a **cessé** d'être `active && interactable`, et l'est resté 45 s pleines
(un seul poll positif suffirait à passer). Le message a été réécrit en conséquence.

## 4. Les trois régimes, et les deux volets du remède

| régime | ce qui se passe | volet qui répare |
|---|---|---|
| (1) scène méta absente | `thor.Loader$$LoadScene` a refusé en silence | **aucun** → `scene-meta-absente` |
| (2) méta chargée, mauvais écran | `IdunNavigation` pointe ailleurs | volet B — `ToCampaign` |
| (3) campagne remontée mais **masquée** | un popup modal la rend non-interactable | volet A — fermeture |

Le régime (3) n'est pas un état du jeu mais un angle mort de **notre détecteur** :
`enumerateButtons(r, false)` ne retient que les boutons `active && interactable`, et le dépôt
documente déjà, à l'étape 1 de l'amorce, que les popups « disable everything behind them ».
`idun.UI.IdunNavigation` porte précisément une famille de popups de retour-au-méta
(`$$ShowDelayedRewards`, `$$ShowLiveEventInterstitialPopupIfNecessary`,
`$$ShowOfferInterstitialPopupIfNecessary`, `$$ShowCampaignUnlockedIfNecessary`,
`$$ShowPowerLevelUpSequenceScreenIfNecessary`), tous invoqués par delegate — donc invisibles
d'une xref statique. **Le régime (3) reste une HYPOTHÈSE** : ce qui est établi, c'est le filtre
du détecteur et l'existence de ces popups, pas qu'ils soient la cause du wedge observé. Il
expliquerait l'intermittence (ces popups n'apparaissent pas à chaque retour) et cadre avec le
constat §3 (disparition après apparition).

**Le remède est aussi l'instrument qui tranchera** : `recovered` nomme le volet qui a porté.
Au prochain wedge, `steps` répond à la question au lieu de la reposer.

## 5. Ce qui est livré

- `frida/hooks/features/amorce-wedge-remedy.ts` — module **pur** (aucun accès Frida), donc
  éprouvable hors du jeu. `runWedgeRemedy(deps)`, deux volets ordonnés (popups puis nav),
  cinq motifs **nommés** : `campagne-remontee-apres-fermeture-de-popup`,
  `campagne-remontee-apres-nav-to-campaign`, `scene-meta-absente`, `nav-to-campaign-a-leve`,
  `remede-epuise`. `no-nav-instance` **arrête immédiatement** (réessayer sans scène méta ne
  peut rien changer) ; une levée, elle, est retentée (elle peut être transitoire).
- **Bornes déclarées et exportées** : `WEDGE_REMEDY_ATTEMPTS = 2`,
  `WEDGE_REMEDY_POPUP_WAIT_MS = 8000`, `WEDGE_REMEDY_NAV_WAIT_MS = 12000` → **+40 s au pire**,
  en plus des 45 s d'attente initiale, et **0 s sur le chemin nominal**. Un retry non borné
  transformerait un wedge visible en attente muette — pire que le défaut réparé.
- **Le wedge reste VISIBLE après rattrapage** : le step `wait-back-to-campaign` reste à
  `ok: false`, les steps `wedge-remedy-*` tracent chaque volet, et `AmorceResult.recovered`
  porte le motif. Trois états lisibles là où il n'y en avait qu'un.
- **Deux foyers uniques**, la leçon de #332 appliquée avant qu'elle ne coûte :
  `navToCampaignOnMainThread(animated)` sert l'étape 2 du cycle, le RPC de secours
  `navToCampaign` **et** le remède (`invokeToCampaign` n'a plus qu'un seul appelant) ;
  `dismissOpenPopups(r)` sert l'étape 1 **et** le remède.

## 6. Ce qui est mesuré, et ce qui ne l'est pas

- `frida/tools/probe-390-wedge-remedy.ts` — **60/60**. Étage 1 : exerce le code de production
  avec des doublures qui **comptent** leurs appels (court-circuit du volet B, économie
  d'attente, arrêt immédiat, borne, motifs distincts, ASCII, non-levée). Étage 2 : confronte
  le **câblage** au source de `auto-boot.ts` (appel dans la branche du cran 8, foyers
  uniques, `recovered` publié, prédicat partagé, bornes journalisées).
- **Contre-épreuve : 6/6 mutants détectés** — décâblage de l'appel, borne relâchée à 5, perte
  de l'arrêt immédiat, fusion de deux motifs en une sentinelle, duplication du foyer d'invoke,
  suppression de la recopie des steps. La garde mord.
- **NON CONFRONTÉ LIVE.** Le code vit dans `frida/hooks/*` : il exige un rebuild + reinject
  pour être actif, et le wedge est **intermittent** — l'observer exige en plus qu'il se
  produise. Le bundle **compile** (`frida-compile hooks/main.ts`, rc 0) et le module est bien
  dans la sortie ; c'est tout ce qu'on peut établir sans fenêtre.
- Gardes voisines rejouées vertes : `amorce.probe.ts` 24/24, `probe_480_hooks_audit.py`,
  `probe_480r1_entrees_de_build.py`, `probe_365_versioned_imports_gitignored.py`.

## 7. Résidus

- **#390-r1** — `frida/hooks/probes/try-to-campaign.ts` est une **troisième copie** du triplet
  `résoudre la classe` + `trouver l'instance vivante` + `invoquer ToCampaign`, avec ses propres
  littéraux (`"campaign1"`, `campaignType 0`) et son propre décodage d'`Il2CppArray`. Elle est
  classée `SONDE` par `probe_480_hooks_audit.py` et n'a pas été touchée ici (hors périmètre).
  C'est exactement la forme de duplication qui a coûté #332 : la faire passer par
  `navToCampaignOnMainThread`, ou la retirer si la sonde a fait son temps.
