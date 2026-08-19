# #993 — l'amorce entre et sort de bataille SANS UN SEUL CLIC

**Build** `rnca9r7q6c` · **sessions Frida** 81-88 · 2026-08-13

## Le resultat

`autoBootExtraire` ne pilote plus AUCUNE UI. Trois appels natifs, 20 steps verts,
**22,4 s** inject compris — et ce run-la enchainait DEUX aller-retours (sortie d'une bataille
heritee, puis entree / capture / sortie). `session.warmed: true`, builder 3/3.

```
ViewCommandExecutor$$StartCampaignMatch("campaign1", 74, Standard, {brut:"0101",octets:2})
IdunMainView$$OnBattleSurrender()      -> popup de confirmation (PauseSurrender DIFFERE)
IdunMainView$$ContinueSurrender()      -> fin de bataille, retour au meta
```

Le pilotage d'UI est RETIRE, **sans repli**. Un repli silencieux aurait rendu la voie native
inverifiable : elle pourrait cesser de porter sans que rien ne le signale. Toute panne est ROUGE
et porte un motif NOMME (15 motifs, deux a deux distincts).

Parti avec lui : `amorce-retreat-signal.ts` (+ son probe) et `amorce-wedge-remedy.ts` (+ le sien).
Le second ne pouvait plus reparer que « pas sur la campagne », qui n'est plus une panne.

## LE discriminant : `thor.Loader.__loadingStep`

**Trois blocages du jeu ont eu UNE seule cause.** `thor.Loader$$LoadScene` REFUSE EN SILENCE
quand un chargement est deja en cours : il journalise et retourne. Un geste de changement de
scene joue dans cette fenetre est donc ANNULE sans un mot — jeu vivant, RPC repondants, **aucun
ecran**.

Mesure (statique relue toutes les ~900 ms apres `StartCampaignMatch`) :

| t | `__loadingStep` |
|---|---|
| 1,1 s | 1 |
| 3,1 s | 6 |
| 9,8 s | 10 |
| **10,8 s** | **0** — termine |

Les trois cycles casses se retiraient entre **8 et 10 s**. Le meme geste a ~30 s rend la main sur
un ecran complet en 7,8 s.

⚠ **La garde vaut DANS LES DEUX SENS.** Se retirer trop tot bloque le retour au meta ; lancer trop
tot (pendant que le meta charge) fait refuser `LoadBattle` — et la CAPTURE reussit quand meme, car
`StartCampaignMatch` cree la source AVANT d'appeler le chargeur. Le cycle se croit alors en
bataille et echoue 20 s plus loin sur un symptome qui ne nomme pas la cause.

⚠ **Et l'ordre compte** : interroger le chargeur juste apres l'invoke rend `0` parce qu'il n'a PAS
ENCORE DEMARRE. Une garde satisfaite par l'etat d'AVANT le geste ne garde rien. D'ou : la porte
(`IdunMainView` vivante, elle nait avec la scene) d'abord, le chargeur ensuite.

⇒ Lib **`frida/hooks/game/loader.ts`** (RPC `loaderStatus`) : la question conditionne TOUT
changement de scene, pas seulement l'amorce.

## Les CINQ signaux mesures et ECARTES

Aucun ne repond a « le chargeur a-t-il fini ? » — tous disent seulement « la bataille existe » :

| signal | quand | pourquoi il ne suffit pas |
|---|---|---|
| `get_IsBattleActive` | 6,8 s | bascule avant la fin du chargement |
| instance `IdunMainView` | ~7 s | nait avec la scene, pas a sa fin |
| `UnitSelectionFsm` -> `UnitDeploymentState` | **1,2 s** | l'etat est pris d'emblee |
| boutons de deploiement (3 fragments) | 8,8 s | presents avant la fin |
| `montre-fin` du popup de confirmation | — | le popup s'affiche PAR-DESSUS une bataille qui charge |

## `get_IsActive` n'est PAS `get_IsBattleActive`

Apres un lancement avorte, mesure :

```
get_IsActive       = True     <- le garde que StartMatch(checkIfAlreadyRunning) teste
get_IsBattleActive = False    <- aucune scene de bataille
FindObjectsByType(IdunMainView) -> 0 instance
```

Le garde **survit** au lancement rate et fait refuser tous les suivants, en silence. Rien ne le
nettoie seul. `IdunMainView$$SetBattleNotRunning()` le desarme — verifie : `IsActive -> False`,
puis la bataille suivante monte (`__loadingStep` 10 -> 12 -> 0 a 8,4 s). Le cycle le detecte et le
desarme **uniquement** dans l'etat sans ambiguite (arme SANS bataille), et il le DIT.

## Deux autres pieges payes

1. **`ContinueSurrender` SEULE laisse le jeu sans ecran** (#992). Elle n'est jamais appelee sans
   que l'EFFET d'`OnBattleSurrender` ait ete OBSERVE — signal `montre-fin` du popup, jamais la
   presence de son bouton : celle-ci arrive des `montre-debut`.
2. **Un ancrage ne capture que ce qui tire APRES le chargement.** Sur une session fraiche ouverte
   pendant une bataille, le `.ctor` d'`IdunMainView` a deja tire : `mainView` reste NUL pour
   toujours, et la seule bataille qu'on ait besoin de quitter devient inquittable. Repli ajoute par
   `FindObjectsByType` — ce n'est PAS un balayage de tas (l'interdit porte sur `Memory.scan`).

## Ce qui n'est PAS exige

Le cran final demandait le noeud de campagne. **Faux** : la retraite rend la main sur
`Idun_UI_Navigation` (131 boutons), pas sur la campagne. On charge une bataille, on en sort, et on
verifie seulement qu'un ecran est remonte — `IdunNavigation` vivante. `get_IsBattleActive == false`
ne suffit pas : il vaut `false` dans les deux cas, y compris ecran noir.

## Le verdict « non contournable » de #989 etait FAUX

Sa premisse tient (un seul site de creation, ctor inline, aucun conteneur DI, trois parametres qui
DECRIVENT la bataille). Sa conclusion, non : la question posee etait « peut-on RESOUDRE l'instance
sans bataille ? » (non), alors que la bonne etait « peut-on APPELER la methode que les clics
appellent ? » (oui).

## Pointeurs

`frida/hooks/features/auto-boot.ts` (module PUR : ordre, gardes, bornes) ·
`frida/hooks/features/auto-boot.ts` (cablage) · `frida/hooks/game/loader.ts` ·
`frida/tools/probe-993-auto-boot.ts` (146 verifications, hors Frida) ·
`docs/rl/case-992-source-de-mode-sans-bataille.md`
