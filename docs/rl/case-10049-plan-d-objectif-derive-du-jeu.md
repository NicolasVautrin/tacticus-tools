# #10049 — Le plan de farm se dérive du JEU, sans le planner

**Mesuré le 2026-08-27, build `t6dpr4k06g`.** Outil : `scripts/python/plan_objectif.py`.

Question posée : peut-on calculer soi-même l'utilité d'un upgrade et la rentabilité d'un nœud,
au lieu de lire `tacticusplanner.app` ? **Oui — tout est dans le gameconfig versionné et l'état
live.** Seul l'OBJECTIF (quel personnage, jusqu'à quel rang) n'est pas une donnée du jeu.

## La chaîne, et où chaque brique se lit

| brique | source | volume mesuré |
|---|---|---|
| recettes de rang | `units.lineup[<id>].upgrades[rang]` | **116** unités × **20** rangs × **6** matériaux |
| craft | `upgrades[<id>].crafting` | récursif, ex. `upgHpU004C <- upgHpC002 x6` |
| catalogue | `upgrades` | 558 |
| drop / coût / plafond | `battles.campaigns[].battles[].loot`, `staminaCost`, `maxAttempts` | **1316/1316** avec `loot` ; 1311 avec coût et plafond |
| rang et slots posés | live, `UnitProgressionData.units[<id>]` | `rank`, `upgrades` |
| inventaire | live, RPC `inventaireUpgrades` | — |

**Chemin de lecture live, sans aucun scan** :
`viewField {cible: "executor", chemin: "_unitProgression._unitProgressionData"}` puis
`viewJson {chemin: "units"}`.

## Les quatre pièges, tous payés

**1. `loot.base` est versé à CHAQUE passe — l'ignorer sous-compte l'Elite d'un facteur ~13.**
`elite4 26` porte `base: [gold, upgArmR039]` **et** `chanceOf: upgArmR039%1/12` : le taux est
**1,083/passe**, pas 0,083. C'est le « (x2) » du planner. Conséquence contre-intuitive :
**l'Elite est moins cher à l'unité malgré son coût d'énergie double**. Témoin : 11 passes réelles
(`elite4 13` ×5 + `eliteMirror4 11` ×6) → attendu **11,9**, mesuré **+12** ; l'ancien modèle
prédisait 0,9. `star1/star2/star3` sont one-shot et n'entrent PAS dans un calcul de farm.

**2. `rank` est le rang ; `progressionIndex` ne l'est PAS.** Les confondre a placé Shiron 11 crans
trop haut (Silver 3 au lieu de Stone 1) et rendu un plan à **152** d'énergie au lieu de **1 530** —
facteur 10. `progressionIndex` est l'axe ÉTOILES/RARETÉ. Et `upgrades` liste les slots **déjà
posés** au rang courant (`[1,2,3,4,5]` = 5 sur 6) : ne pas les déduire recompte un rang entier.
Calage : `rank: 0` ↔ « Stone 1 » à l'écran, dit par l'utilisateur.

**3. Une passe est indivisible.** Compter `qté × énergie/unité` rend des passes fractionnaires,
donc une énergie sous-estimée : **1 530** en fractionnaire contre **1 586** en passes entières.

**4. L'or est un REVENU, pas seulement un coût — et l'ignorer fait choisir des nœuds STRICTEMENT
DOMINÉS.** À énergie **égale** (60), `eliteMirror3 21` rend **909** d'or là où `mirror1 24` en rend
**590**. Le critère « moins cher en énergie » prenait le second par simple ordre de rencontre :
**5 matériaux sur 12** étaient concernés.

## Ce que ça donne — Shiron (`emperNoiseMarine`) Stone 1 → Gold 3

| critère | énergie | or gagné | or NET |
|---|---|---|---|
| énergie seule (dominé) | 1 578 | 18 928 | +2 828 |
| énergie puis or | 1 578 | 20 268 | +4 168 |
| **passes minimales** (défaut) | 1 630 | 24 758 | **+8 658** |

**Le plan se paie tout seul** : 16 100 d'or de craft contre 18 900 à 24 700 gagnés. L'annoncer
comme un coût net est faux. Et `passes` domine : **+52** d'énergie (3 %, ~0,1 jour) pour
**+5 830** d'or — c'est le critère que suit le planner.

**Budget d'énergie** : 1 point / 5 min = 288/jour, **+ 220 de refill blackstone** = **508/jour**.
Le refill fait passer un plan de 1 530 de **6 jours à 4** ; c'est le levier dominant, devant tout
choix de nœud.

## Confrontation au planner — même objectif, écart de 0,8 %

Le planner affiche pour Shiron `Lv 27→41`, énergie **1 573**, 3 jours. **Que ce soit le même
objectif est établi, pas supposé** : `upgradeSlots.xpLevelRequirements[13]` =
`[38,39,38,40,38,41]` — finir les 6 slots du rang 13 (Gold 2), donc atteindre Gold 3, exige le
niveau 41.

- **Nœuds** : 6 identiques sur 12 ; les 5 divergents sont tous « planner = Elite, moi = Mirror ».
- **Énergie** : 1 573 (planner) contre 1 586 en passes entières. **Les 13 restants ne sont pas
  expliqués**, et l'explication par le choix de nœud va dans le MAUVAIS sens (les Elite du planner
  coûtent plus d'énergie, son total devrait être supérieur).
- **Jours** : 3 contre 4 — le planner suppose le stock d'énergie courant, l'outil le décompte
  explicitement.
- **`Raids plan (3 Days | 1573)` du planner n'est pas un COÛT mais un BUDGET** : 3 × 508 = 1 524,
  à 3 % près. Ne pas comparer un coût minimal à une enveloppe.

## Les MoW ne se calculent pas ainsi

Les **11** unités de `lineup` sans `upgrades` sont exactement les Machines of War. Elles n'ont ni
rang ni matériaux : en jeu `rank: 0`, `upgrades: []`, `xpLevel: 1`,
`progressionIndexDirectionAscension: null`. Deux axes, **aucun en énergie** :
`heroProgressionStepsMoW` (étoiles) et `abilityUpgradeCostsMoW` (niveaux d'ability).
⚠ **Leurs devises se DÉRIVENT** — 14 clés côté ability, 7 côté étoiles. Une première version en
énumérait 4 et en laissait tomber 10 **en silence**.

## Résidus

- **#10049-r1 — le filtre sur les nœuds DÉBLOQUÉS n'existe pas.** Un nœud non atteint gonfle le
  débit et rend le coût optimiste. L'outil l'imprime à chaque exécution plutôt que de le taire.
- **L'écart de 13 d'énergie avec le planner** reste sans cause établie (0,8 %). Documenté ici,
  pas ouvert en tâche : il n'a aucune conséquence pratique.

⛔ **NE JAMAIS appeler `mapRanks` / `findProgInstances`** pour lire un rang : ce sont des SONDES
qui font un `findInstanceByHeapScan` **et** un invoke managé hors pompe. Elles ont **tué le jeu
deux fois** le 2026-08-26 (`Tacticus.exe.77604.dmp`, `.53392.dmp`). Le chemin de lecture donné
plus haut n'ancre rien et ne scanne rien.
