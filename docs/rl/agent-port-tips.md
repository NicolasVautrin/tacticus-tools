# Tips agents de port — NE PAS perdre de temps en validation

> À LIRE avant de valider un port (opus-solver / fable-solver). Compile les gains de temps
> récurrents. Les prompts de dispatch pointent ici. Ajouter un tip dès qu'un agent reperd du
> temps sur un piège déjà vu.

## 1. Forcer les HP dans le build du runner (scénario déterministe)
`rl_duel build --hp-target <N>` force `Health`+`RemainingHealth` d'une unité **cible/ennemie** à N
ET met son armure à 0 (one-shottable) ; `--hp-player <N>` fait pareil côté unité **JOUEUR** (p-unit).
Réf : `rl_duel.py:339-356`. Usages :
- rendre un allié **blessé** (HP < max) donc **healable** sans le faire tabasser d'abord (heal/repair) ;
- caler une cible fragile pour un **kill déterministe** (revive, kill-events, death-triggers) ;
- stabiliser un tir mesurable (self-buff qui se manifeste au tour suivant, ex. additional-hits).

## 2. Bugs du pipeline PARTAGE déjà connus -> NE PAS re-root-cause
Si le symptôme correspond à un bug **partagé déjà tracké**, reporte-le par son numéro et AVANCE —
ne perds pas 100K tokens à le ré-expliquer :
- **#37** — attaque d'ABILITY multi-coups à `cc=0` : désync RNG (coups >=2 divergent, coup 1 exact,
  total ~1% off). Cause = crit-roll skip à cc=0 dans `_run_hits` (`operations/damage.py`). Un
  fable-solver est dessus. Prouve que TON port est structurellement correct (tip #4), reporte #37.
- **#205** — désync per-coup après le 1er coup d'une cible multi-coups (même racine que #37).
> Mets à jour cette liste quand un nouveau bug partagé est identifié.

## 3. ETAPE 0 OBLIGATOIRE — rebaser sur le master LOCAL (base stale garantie)
Le harness crée ta branche depuis **`origin/master`**, qui est **STALE** : l'orchestrateur merge en
LOCAL sans push -> `origin/master` reste bloqué plusieurs commits en arrière (ex. `1e45f5d`,
pré-modularisation ; le package `runner/abilities/behaviours/` n'existe PAS sur cette base). AVANT DE
CODER, dans ton worktree :
1. `git log --oneline -3` — doit montrer les derniers merges + `git ls-files | grep behaviours/` non vide.
2. Si base stale : **`git rebase master`** (rebase ta branche sur le master LOCAL, visible via le .git
   partagé). NE PAS `git checkout master` -> ÉCHOUE (master est déjà checkout dans l'arbre principal).
   Si tu n'as RIEN committé encore : `git reset --hard master`.
Sinon : placement dans un fichier inexistant, merge 3-way douloureux, temps perdu (vécu : Vigilance/
CordClaw sur `1e45f5d` ; Aberrant s'est rebasé -> OK).

## 4. A/B pour isoler la structure du pipeline partagé
Compare **arbre porté == séquence directe** (`execute_ability_attack` / la baseline damage). Si A==B,
ton port n'introduit AUCUN bug de dégât -> tout écart restant vient du pipeline partagé (tip #2), pas
de toi. Ça évite de chasser un bug qui n'est pas le tien.

## 5. Piloter les positions, ne pas se plaindre de la géométrie
`applyAction` **ignore propriété + portée** -> DÉPLACE n'importe quelle unité (des 2 camps) pour
crafter l'adjacence / la distance / le banding exacts. Jamais « bloqué par la géométrie de spawn ».
Choisir l'unité/trait qui REMPLIT la condition testée via `unit_map.py` (index des 669 kits) ; adapter
rosters + positions pour que la condition soit remplie ET **stable**.

## 6. Board choisi pour isoler la variable
`--board` / `--board-pool` + `board.py`. Board plat pour isoler le banding/la portée ; élévation
contrôlée seulement quand c'est la variable testée. Ne pas subir un board qui brouille la mesure.

## 7. Mesurer le ground truth, jamais fitter
Divergence de dégât -> MESURER chaque étage (offline vs live), trouver un **2e cas discriminant** ;
JAMAIS caler une constante/un scalaire sur une seule mesure. Diagnostiquer depuis les `tool_use`
réels + le décompilé, pas des proxies. Hypothèses marquées et vérifiées AVANT de conclure.

## 8. decisionView garde les cadavres
Une unité morte reste dans `decisionView.units`. Mort = `observeBattle.isDead` (`ctx.obs_units`), pas
l'absence de la liste. Ne pas conclure « disparue » d'un scan decisionView.

## 9. Discipline runner (rappel)
state-file à NOM UNIQUE en chemin ABSOLU, `--runner` explicite, dispose TES runners (jamais ceux des
autres), MAX_RUNNERS=10. Session Frida PARTAGEE et warm : **jamais de reinject / restart host**. Froide
ou wedged -> STOP + reporte, aucune récupération toi-même.
