# #512-r7 — la cloture d'attaque encadrait ce que le natif emet avant elle

**Fait.** Sur une feuille AUTONOME (`isOutsideAttack = 1`), le port emettait
`9, 0x3c?, 8, 0x42, 10`. Le natif emet `0x3c?, 8, 0x42, 9, 10`. Mesure du 2026-08-18 sur
`execute_ability_attack(is_outside_attack=True)` : `[5, 6, 57, 15, 16, 9, 8, 66, 10]`.

**Les trois lectures qui fixent l'ordre** (build `t6dpr4k06g`) :

1. `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` — `StartAttack` (slot `0x3a`) *avant*
   le behaviour enfant, `FinishAttack` (slot `0x3b`) **apres**.
2. `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` — appelee PAR COUP depuis
   `ExecuteHit`, elle n'emet que `0x3c` (sous le flag BLOCK) puis `8`.
3. `IdunBattle.Operations.ADamageOperation$$RegisterFinalDamage` — `On(0x42)` est sa derniere
   instruction, et l'appel a `RegisterFinalDamage` est la derniere instruction d'
   `IdunBattle.Operations.AbilityDamageOperation$$Execute` (`RegisterFinalDamage(...) ; return`).

**Ce que #512-r4 avait manque.** Son parametre `emit_finish_attack` reglait la CARDINALITE au bon
endroit (une feuille nue ne clot pas) mais laissait le RANG faux : la cloture partait depuis la
facade after-hit, donc avant les deux vecteurs de cette meme facade et avant le `On(0x42)` que
l'appelant emet ensuite. Le correctif DEPLACE l'emission au lieu de la gater : `On(9)` a quitte
`after_hit_ability_attack` — qui n'est plus que le mirror d'`EvaluateAfterHitTriggers` — pour vivre
chez ses deux appelants (`damage_ops/ability.py`, `damage_ops/normal_like.py`), apres
`final_damage_triggers`, sous le meme `is_outside_attack`. La cardinalite est donc conservee telle
quelle.

**La premisse de la fiche etait fausse sur un point.** Elle disait « aucun consommateur porte ne
l'observe : les trois familles d'evenements ont des ecoutants disjoints ». Les ENSEMBLES le sont
(`On(9)` : 37 classes ; `On(8)` : 1, `RefusalToBeOutdoneRecordHitAbility` / `emperExultant` ;
`On(66)` : 1, `RealityUnboundExtraMaxDamageAbility` ; `On(0x3c)` : 2, `AnvilShield*`) — mais **pas
les PORTEURS** : `thousTzaangor` porte a la fois `RealityUnboundAbility` (`On(9)`) et
`RealityUnboundExtraMaxDamageAbility` (`On(66)`). Leurs gates ne se lisent pas l'un l'autre
(`has_effect(1205)` contre `received_damage_this_turn`), donc l'ecart reste inerte *sur ce
porteur* ; il ne l'est pas par construction. C'est pourquoi le cliquet garde la **SEQUENCE**, pas
un compte.

**Cliquet.** `tests/engine/runner/test_512r7_ordre_cloture_offline.py` — 6 tests, dont le
CONTRE-CAS qui rejoue le regime d'avant par substitution de la facade. Matrice de mutants, 4/4 qui
MORDENT : cloture remise en tete, gate `is_outside_attack` retire, gate de famille d'`On(10)`
retire, cloture retiree de `normal_like`.

## Le deplacement a perime deux crans de #489-r1 — et le second est le plus interessant

Trois tests de `test_489r1_foyer_combat_offline.py` sont tombes sur ce deplacement. Ils ont ete
**re-etalonnes**, pas desarmes.

**1. Le gate `emit_finish_attack`** (`test_etage5_le_vecteur_On9_de_la_feuille_est_GATE_...`)
exigeait un PARAMETRE-RELAIS : la facade passait son `is_outside_attack` a
`after_hit_ability_attack`, qui en faisait une condition. L'emission ayant quitte cette fonction,
le relais n'a plus d'objet — le gate est desormais DIRECT, mesure sur le `ast.If` qui englobe
l'appel. Et l'exigence positive est remplacee par un **cran negatif** : le parametre ne doit pas
revenir, parce que son defaut etait VRAI — le re-introduire rearmerait un second emetteur, donc la
cardinalite double que #512-r4 avait fermee. Il n'y a plus deux gardes qui se contredisent ; il y
en a un qui interdit le retour de l'autre.

**2. Le cliquet d'ARCHITECTURE** (`..._a_DEUX_foyers_et_pas_un_de_plus`) exigeait la liste
`["combat.py", "normal.py"]`, au motif — exact — que le slot 59 est pousse par les NŒUDS, jamais
par une operation de degat. **La topologie est juste, la conclusion en liste ne l'etait pas**, et
c'est mesure : `execute_ability_attack` / `execute_normal_like` ont **8 appelants imperatifs** hors
de `combat.py` (`loki/splash.py` x2, `loki/summon.py`, `operations/summon_ai.py`,
`triggers/genestealer.py`, `triggers/loki/{destroyer_hive,hailstrike,haze_of_corruption}.py`),
**tous** au defaut `is_outside_attack = True`. Pour eux la facade ne mirroite pas seulement
l'OPERATION : elle **COLLAPSE** le couple `AttackBehaviour` + `AttackDamageBehaviour` que leur
factory (`DSLBehaviors$$AttackWithAttackDamage`) construit d'un bloc — `is_outside_attack = True`
EST le marqueur de ce collapse. Deplacer la cloture dans le seul `combat.py` aurait retire `On(9)`
a ces huit-la, **en silence**.

La nouvelle borne est **derivee du natif**, sans aucun nom de fichier :

> **un site qui CLOT une attaque est un site qui l'OUVRE** — la symetrie des deux `if` d'
> `AttackBehaviour$$Execute` (`prev != cur` -> `StartAttack` ; `next != cur` -> `FinishAttack`).

La reciproque est fausse cote port, et volontairement : un site peut ouvrir lui-meme et deleguer la
fermeture au foyer de NŒUD (`haze_of_corruption.py` le fait). Cette borne est **strictement plus
forte** sur l'axe qui compte : la liste autorisait `normal.py` a clore sans ouvrir, elle non. Et
elle survit a un renommage.

⚠ **Le piege d'attribution, note par l'orchestrateur** : ce fichier portait DEJA un rouge connu
(`test_etage4`, etranger a cette tranche). Le jouer et lire « rouge, c'est le preexistant » ne
prouve rien. **Un fichier ne se classe pas ; un TEST se classe.** Reference a comparer :
**1 failed / 20 passed**.

Mutants sur les crans re-etalonnes, **3/3 qui MORDENT** : un module qui clot sans ouvrir · le gate
`is_outside_attack` retire · la facade qui ne clot plus.

**Residu ouvert : `#512-r9`.** `execute_normal_like` n'emet AUCUN `On(0x42)`, alors que
`RegisterFinalDamage` est appelee par les deux `Execute` natives. Ce n'est pas un ecart d'ordre —
c'est un evenement entier qui manque.

Re-deriver les comptes d'ecoutants (`probe_437_on9_blast_radius.py`), jamais citer ceux-ci.
