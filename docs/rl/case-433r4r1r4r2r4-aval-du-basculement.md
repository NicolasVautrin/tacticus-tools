# #433-r4-r1-r4-r2-r4 — l'AVAL du basculement d'adjacence

**MESURE, pas port** — aucune écriture dans `engine/`.

**Le basculement de #606 EST un écart d'IMPACT, pas seulement de fidélité — mais rare.**
Sur **725** situations (board x seed x état x unité activable), l'action choisie par le playbook
diffère entre les deux substrats **8 fois (1,1 %)**, soit **4 configurations distinctes** ; **0**
changement de classement sans changement d'action. Conditionnellement aux situations où une
adjacence a réellement basculé (**113**), le taux monte à **7,1 %**.

## 1. La question

#433-r4-r1-r4-r2 (PR #606) a montré que `battle_query.is_adjacent` **change de verdict** quand on le
branche sur la liste stockée du `ConnectivityComponent`, et que **le natif est d'accord** (oracle
indépendant : le splash de `FragBomb`). Solde : **4** arêtes permissives fermées sur `C1_74`, **38**
sur `C3_14`, **0** restrictive. Non mesuré jusqu'ici : est-ce que ça change une **DÉCISION** ?

Le sens de lecture compte : le substrat NAT est le comportement du port **depuis #606**, et c'est
lui qui est juste. Les 8 décisions comptées ci-dessous sont donc **8 décisions que le port prenait
FAUSSES avant #606** — pas 8 régressions.

## 2. Le discriminant, et la SURFACE exacte de la mesure

Comparaison **DIRECTE des deux substrats du MÊME port**, sur le MÊME état live — le natif n'entre
pas dans cette mesure (un critère à trois valeurs noierait le cas utile, leçon de `#589-r1`) :

    NAT = `is_adjacent(t, p, elev, neigh)`   <- ce que le port fait DEPUIS #606
    GEO = `is_adjacent(t, p, elev, None)`    <- ce qu'il faisait AVANT

**Le patch porte sur la PRIMITIVE, jamais sur le canal.** `neigh_by_pos` a d'autres lecteurs qui le
lisent directement (l'ordre natif des voisins pour la cible exacte de `GauntletsOfUltramar`, #117) et
qui sont identiques dans les deux états du dépôt : neutraliser le canal mesurerait autre chose.

**Surface**, dérivée du code par parcours AST (pas un grep) : **65** call-sites passent le canal aux
quatre primitives d'adjacence, **15** ne le passent pas. Ces 15 restent géométriques *dans les deux
substrats*, donc structurellement invisibles ici : `battle_query.in_arc` / `is_charging`
(`#433-r4-r1-r4-r2-r1`), `heroic_fusillade` (`-r2`), plus `entities/triggers.py`,
`runner/abilities/targeting.py`, `services/movement_query.py`, `utilities/ramming_speed.py`,
`runner/operations/spawn.py`.

## 3. Les voies, MESURÉES (pas supposées)

Le probe ventile chaque bascule par **call-site métier** (remontée de frames jusqu'au premier
appelant hors `battle_query`). Sur les trois campagnes, par ordre de fréquence :

| voie | rôle | bascules |
|---|---|---|
| `utilities/tile.py:apply_tile_attributes` | `UnitEffectsAdjacentUtility` — effets des AMIS adjacents à la tuile candidate | 164 |
| `playbook/noncomparable/aberrant_hypermorph.py:generate_candidates` | utilité = `GetAdjacentEnemies(tuile de spawn).Count` | 48 |
| `playbook/adjacent_unit_preference.py:calculate_movement_utility_in_steps` | amis/ennemis adjacents à la tuile d'arrivée | 31 |
| `playbook/non_owner.py:calculate_movement_utility_in_steps` | même feuille, côté non-propriétaire | 11 |
| `playbook/noncomparable/fighting_retreat.py` / `bloody_fury.py` | comptages `GetAdjacentEnemies/Friends` | 6 |

**La voie la plus fréquente est aussi la plus INERTE** : `apply_tile_attributes` ne fait que poser la
liste des effets d'un voisin ; si aucun de ces effets ne porte de valeur d'utilité dans les poids BC,
la feuille rend `0` des deux côtés. C'est la raison mesurée pour laquelle 260 bascules ne produisent
que 8 changements d'action.

⚠ **La surface EXERCÉE est bien plus étroite que la surface branchée.** Un relevé exhaustif des
appels (`--voies`, `C3_14`, 4 pas, 17 situations) ne trouve que **2 call-sites empruntés** —
`aberrant_hypermorph.generate_candidates` (297 appels) et `tile.py:apply_tile_attributes` (189) —
sur les **65** branchés. Ce sont les rosters en jeu qui décident quelles voies existent, pas le
board : les six voies observées sur l'ensemble des campagnes ne sont pas les mêmes d'un seed à
l'autre.

## 4. Les trois taux

Trois campagnes, `--steps 12`, session live warmée, rank 17.

| campagne | N | bascules | situations avec bascule | **DÉCISION** | **CLASSEMENT** | utilité bougée |
|---|---|---|---|---|---|---|
| seed 777, rosters aléatoires, 6 boards | 302 | 56 | 30 | **3** | **0** | 9 |
| seed 1357, rosters aléatoires, 4 boards | 214 | 86 | 37 | **0** | **0** | 0 |
| seed 777, roster CRAFTÉ `genes*`, 3 boards | 209 | 118 | 46 | **5** | **0** | 1 |
| **total** | **725** | **260** | **113** | **8 (1,1 %)** | **0** | **10** |

Ventilation par board (gisement = arêtes dirigées que le basculement ferme, mesuré sur le
`boardGraph` du runner) :

| board | gisement | N | bascules | DÉCISION |
|---|---|---|---|---|
| `C3_14` | 38 | 173 | 192 | 5 |
| `C4_40` | 16 | 195 | 56 | 0 |
| `C4_33` | 10 | 76 | 5 | 2 |
| `C1_74` | 4 | 184 | 7 | 1 |
| `MC1_67` | 0 | 59 | 0 | 0 |
| `C6_25` | 0 | 38 | 0 | 0 |

**Le gisement du board ne prédit pas l'impact.** `C3_14` (gisement 38) rend 0 décision au seed 777
en roster aléatoire et 5 en roster crafté ; `C4_33` (gisement 10) en rend 2 là où `C4_40`
(gisement 16, N plus grand) en rend 0. Ce qui décide, c'est **quel playbook est en jeu** — pas la
densité d'arêtes. Les deux boards sans `Bridge` rendent **0 bascule**, ce qui borne le phénomène :
il ne peut rien se passer là où le graphe stocké coïncide avec la couronne hex.

**Amplitude en utilité brute** (les **10** situations où au moins un candidat commun change de
valeur) : min **1,0**, max **30,0** — des entiers, ce que la nature des feuilles explique (un
comptage d'unités, ou une valeur d'utilité d'effet lue dans les poids BC). Ventilé par campagne :
seed 777 aléatoire `min 1 / med 10 / max 10` (n=6) et `1 / 1 / 1` (n=3) ; roster crafté `30` (n=1).

**Classabilité** (campagne seed 777, 302 situations) : le générateur RETENU est le fallback
**Movement 171** fois, **Comparable 93**, un tier **NonComparable 38** ; et seules **73 situations
sur 302 (24 %)** exposent **≥ 2 candidats** à ordonner (médiane : **1**). Beaucoup d'unités listées
par `aiMovableTiles` ont déjà agi et n'ont plus qu'une tuile candidate — leur situation est comptée
dans `N` mais n'offre aucun choix. C'est le dénominateur manquant du taux de classement (§8).

**Les 8 changements d'action portent TOUS sur `1166 AberrantHypermorph`** (tier NonComparable 0),
dont l'utilité *est* `GetAdjacentEnemies(tuile de spawn).Count`. Ce qui change est la **tuile de
spawn du summon** et la destination du caster — p. ex. `C4_33` : `tgt=30, to=(2,1)` (NAT) contre
`tgt=31, to=(2,2)` (GEO). Porteurs : `genesBiophagus` (hero, dans le pool) + trois variantes npc.

## 5. Le harnais DISCRIMINE — trois crans

1. **Contre-épreuve de DÉTECTION** (`--substrat mut`) : le substrat alternatif est remplacé par un
   substrat volontairement faux (disque hex `r <= 2`), **borné au même court-circuit que `geo`**
   (appels avec canal seulement — sans cette borne il aurait prouvé la détection sur une surface
   plus large que celle mesurée). Résultat : **2 décisions changées** sur `C4_33`. Le harnais
   rapporte donc bien un changement d'action quand il y en a un, sur exactement la surface mesurée.
2. **Cran anti-contamination** : chaque situation rejoue NAT une 2ᵉ fois APRÈS l'alternatif, et
   compare action + classement. **0 instabilité** sur 725 situations — le triple appel du tactic sur
   le même `ctx` ne se contamine pas.
3. **Régime non dégénéré** : le probe compte les bascules d'adjacence *traversées par la décision* et
   **rougit si elles valent zéro**. Un « 0 décision changée » sans bascule ne conclurait rien ; ici il
   y en a 260.
4. **Reproductibilité** : la campagne seed 777 a été jouée deux fois, une fois **scindée en deux
   processus** (3 + 3 boards) et une fois **d'un bloc** (6 boards). Tous les compteurs coïncident
   (302 / 56 / 3 / 0 / 9), voies comprises.

## 6. Lecture

**Écart de fidélité AVEC impact, mais un impact rare et concentré.** Trois faits :

* Il **existe** : 8 actions différentes, 4 configurations distinctes, sur une mécanique
  (le placement d'un summon) qui n'est pas cosmétique.
* Il est **rare** : 1,1 % des situations, 7,1 % de celles où une adjacence bascule.
* Il est **concentré** : un seul playbook, celui dont l'utilité *est* un comptage d'adjacents.
  La voie la plus traversée (`UnitEffectsAdjacentUtility`) est presque toujours inerte.

Conséquence pour la priorisation : les quatre foyers non branchés de `#433-r4-r1-r4-r2-r1` méritent
d'être branchés (même famille, même gisement), mais on n'attend pas d'eux un bouleversement de la
politique — plutôt le même profil, quelques décisions par millier.

## 7. Ce qui n'est PAS couvert

* **Les 15 call-sites sans canal** (§2) : ils dégradent identiquement dans les deux substrats, donc
  cette mesure ne dit **rien** de ce qu'ils coûtent. C'est le périmètre de `-r1`/`-r2`.
* **63 des 65 call-sites branchés ne sont pas exercés** par le relevé exhaustif (§3). Les taux
  ci-dessus valent pour les voies que ces rosters mettent en jeu, pas pour la couche d'adjacence
  entière — un roster qui porterait `CordClaw`, `FoulInfusion`, `SereneUnifier` ou les playbooks
  `loki_custom` de comptage explorerait des voies non visitées ici.
* **Les MACHINES OF WAR** : le balayage saute les casters `machine_row` (tactic `DefaultMachineTactic`
  dédié, position nulle, aucune tuile candidate).
* **`spawn_groups`** n'est pas passé au contexte : tout arbre dont la géométrie dépend du côté du
  plateau marche sur sa branche `else`. Identique dans les deux substrats, donc sans effet sur la
  comparaison, mais le régime exploré n'est pas exactement celui d'une bataille pilotée.
* **Les situations ne sont pas indépendantes** : une même unité dans un état inchangé est comptée à
  chaque pas — les 8 décisions valent **4 configurations distinctes**.
* **6 boards sur 287 porteurs de `Bridge`** (résidu `-r3`, déjà ouvert et chiffré).
* **L'amplitude ne porte que sur les candidats APPARIÉS** (même identité des deux côtés). Quand la
  bascule change l'identité même d'un candidat — les **8** situations comptées en « ensembles
  changés » — aucune amplitude ne lui est attribuée : c'est un changement plus fort qu'un écart de
  valeur, pas un écart nul.
* **Le CLASSEMENT à 0 est en partie STRUCTUREL** : seules **73 situations sur 302 (24 %)** exposent
  ≥ 2 candidats au générateur retenu, et le générateur retenu dans les 8 cas qui changent est un
  tier NonComparable dont le playbook rend **déjà son propre argmax** — le renversement a lieu
  *dans* le playbook, invisible à un classement mesuré au grain du `Bucket`. Le taux « classement
  changé sans action changée » ne mord donc que sur Comparable et Movement (résidu
  `#433-r4-r1-r4-r2-r4-r1`).

## 8. Résidu NOMMÉ

* **`#433-r4-r1-r4-r2-r4-r1` — le classement est mesuré au grain du `Bucket`, pas des options
  RÉELLES.** `0/725` est mesuré, et le dénominateur est publié pour la campagne seed 777 (**73/302**
  situations à ≥ 2 candidats), mais un playbook NonComparable qui rend son propre argmax n'expose
  qu'**un** candidat : ses options internes — les 6 tuiles de spawn d'`AberrantHypermorph`, par
  exemple — ne sont jamais soumises au classement. Mesurer le renversement *à l'intérieur* d'un
  playbook demanderait d'instrumenter chaque `generate_candidates`, pas le `Bucket`.

## 9. Reproduction

    python probe_433r4r1r4r2r4_aval_decision_live.py --board C3_14 --board C4_40 --board C4_33 \
        --board C1_74 --board MC1_67 --board C6_25 --seed 777 --steps 12
    python probe_433r4r1r4r2r4_aval_decision_live.py --board C3_14 --board C4_40 --board C4_33 \
        --board C1_74 --seed 1357 --steps 12
    python probe_433r4r1r4r2r4_aval_decision_live.py --board C3_14 --board C4_40 --board C4_33 \
        --board C1_74 --seed 777 --steps 12 --units "genesBiophagus,genesPatriarch,genesMagus,genesPrimus"
    python probe_433r4r1r4r2r4_aval_decision_live.py --board C3_14 --board C4_33 --steps 10 --substrat mut
