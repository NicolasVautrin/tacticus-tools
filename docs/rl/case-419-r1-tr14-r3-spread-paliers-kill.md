# #419-r1-tr14-r3 — le spread ±20 % DISCRIMINE, dès que la cible peut mourir

Deux résidus bloqués sur le même débloqueur (« un montage où la cible peut MOURIR ») ; celui-ci est
le volet DÉCISION. Le volet COMBAT (`#419-r1-tr14-r4-r1`, l'octet `+0` des options) est traité dans
`docs/rl/case-419-r1-tr14-r4-face-combat-heavy-bolt-pistol.md` §8 — il s'est révélé **résoluble sans
le montage**, par le seul décompilé.

## 1. Pourquoi l'inertie mesurée par la tranche 14 ne prouvait rien

Le mutant `spread0` y était **inerte aux quatre crans**, et la tranche l'avait dit sans pouvoir
trancher. La cause est ALGÉBRIQUE, pas expérimentale — le composite Damage consomme les bornes de
deux façons seulement :

| feuille | ce qu'elle lit | sensibilité au spread |
|---|---|---|
| `DamageUtility` | `min_max_avg(healthDmgMin, healthDmgMax)` | **aucune** — la moyenne de `base ± d` vaut `base` |
| `KillUnitUtility` | `killSure = rawMin ≥ hp` → 100 ; `kill = rawMax ≥ hp` → 50 | **PALIER** sur chaque borne |
| `OverkillUnitUtility` | `WillBeOverkill = rawMin ≥ 2·hp` → 40 ; `MightBeOverkill = rawMax ≥ 2·hp` → 15 | **PALIER** |

À `Health = 10000`, aucun palier n'est franchissable : seule la moyenne joue, et elle est identique
à spread 0 et à spread 20. L'inertie y était donc une **propriété du régime**, et un montage qui la
constate re-mesure le régime au lieu de trancher la question.

## 2. Le débloqueur — trois crans dont les PV sont DÉRIVÉS, jamais écrits en dur

Montage de la tranche 14 réutilisé tel quel (module `probe_419r1tr14_heavy_bolt_pistol`) : bras
apparié `graft` (1083 greffé sur `tauMarksman`) / `base`, board `MC1_67`, caster sur `A` (au contact
de la cible `T`). **Seul degré de liberté ajouté : les PV de la cible.**

| cran | PV | régime installé |
|---|---|---|
| `hp_hors` | 10000 | aucun palier — **témoin d'inertie EXIGÉE** |
| `fenetre_kill` | `(rawMin+rawMax)//2` = **299** | `kill` sans `killSure` |
| `fenetre_overkill` | `(rawMin+rawMax)//4` = **149** | `MightBeOverkill` sans `WillBeOverkill`, kill acquis des DEUX côtés ⇒ **isole `OverkillUnitUtility`** |

Les bornes RAW (`rawHealthDmgMin/Max`) ne dépendent pas des PV — le cap par PV restants ne touche que
les bornes CAPÉES — donc un calibrage mesuré au premier cran reste valide aux suivants. Le probe le
**re-vérifie** à chaque cran (`attester_regime`) plutôt que de le supposer.

## 3. La mesure — décomposée par étage, natif contre port

`probe_419r1tr14r3_spread_paliers_kill.py`. Bornes RAW mesurées : **[239, 359]** à spread 20,
**[299, 299]** à spread 0 (la mutation mord bien sur les bornes — témoin non nul).

| cran | PV | feuilles à spread 20 | feuilles à spread 0 | **terme natif** | port 20 | port 0 |
|---|---|---|---|---|---|---|
| `hp_hors` | 10000 | dmg 2.989402, kill 0, over 0 | idem | **+2.989402** | +2.989402 (9e-9) | +2.989402 |
| `fenetre_kill` | 299 | dmg 89.368771, **kill 50**, over 0 | dmg 99.335548, **kill 100**, over 0 | **+139.368771** | +139.368771 (4e-9) | **+199.335548** |
| `fenetre_overkill` | 149 | dmg 98.675497, kill 100, **over 15** | dmg 98.675497, kill 100, **over 40** | **+213.675497** | +213.675497 (−1e-9) | **+238.675497** |

**Le natif arbitre, et il tranche pour le spread ±20 %** : le port au spread par défaut le reproduit
aux trois crans (écart ≤ 9e-9) ; `spread_pct = 0` s'en écarte de **+59.966777** et **+25.000000**.

Le déplacement est **décomposé, pas constaté** — la garde asserte que la somme des trois feuilles
égale le déplacement du terme :

* `fenetre_kill` : `PossibleKill → DefinitelyKill` = **+50**, plus `DamageDealt` 89.368771 → 99.335548
  = **+9.966777** (la borne haute était capée à `hp`, la moyenne remonte quand min = max = 299).
* `fenetre_overkill` : `PossibleOverkill → DefinitelyOverkill` = **exactement +25**, et les deux
  autres feuilles ne bougent **pas** (dégât capé à 149 des deux côtés, kill acquis des deux côtés).
  Ce cran isole donc une feuille unique.

## 4. Ce que la RE ajoute, et qui rend le résultat non local (`#419-r1-tr5-r2`)

Le résidu parent opposait deux ports du **même appel natif** : `psyker`/`avalanche_of_muscle`
(slot **0x23**, `spread_pct=0`) contre `light_im_up`/`heavy_bolt_pistol` (slots 0x28/0x24, spread par
défaut). Le décompilé montre que la question ne pouvait pas avoir deux réponses :

```
IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction   (casterPosition:IEntity)      = slot 0x23
    UnitPosition..ctor(&pos, casterTile)
    return BattleQuery$$GetAttackPrediction(caster, target, pos, ability, amount, ...)   # <- 0x24
```

**Le 0x23 est un THUNK sur le 0x24.** Les deux atteignent donc le même
`IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` (slot 10 d'
`IDamagePredictionQuery`), qui écrit le même octet de requête : `uStack_1ce = 1`, recopié par
`uStack_110 = CONCAT53(uStack_1cd, CONCAT12(uStack_1ce, uStack_1d0))` — soit `request+0x68 + 2` =
**`request+0x6a = 1`**, celui que la docstring du port cite comme routant vers
`IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64`.

⚠ **Le résidu était déjà tranché — et dans le même sens.** `#449` (PR #498) l'a fait par un canal
**indépendant** : la capture DIRECTE des bornes natives (`ProbableDamageEvent$$.ctor`), qui rendait
`402 → [322, 482]` là où `spread_pct=0` rendait `[402, 402]`. Les deux modules accusés portent donc
**déjà** le spread par défaut ; re-mesuré ici, `spread_pct = 0` n'apparaît **nulle part** dans un
appel exécutable d'`engine/playbook/`. Ce que cette tranche apporte n'est donc pas la correction,
c'est **la raison structurelle** (0x23 ≡ 0x24, un seul code) plus une **confirmation par un troisième
canal** (les paliers du composite). L'énoncé du résidu, lui, était **périmé** dans trois documents,
qui sont remis à l'état final.

**Pourquoi l'accord de `psyker` n'avait rien prouvé** : son montage était le régime `hp_hors`. Un
accord obtenu là ne distingue pas les deux lectures — même vice que l'inertie de la tranche 14, et
c'est le titre même de la PR #498 (« le canal qui avait *validé* la lecture fausse était DÉGÉNÉRÉ,
pas approximatif »).

## 5. La garde a été vue ROUGE — et sa PREMIÈRE version accusait le MONTAGE

`spread_pct=0` posé **dans le port livré** (`engine/playbook/heavy_bolt_pistol.py`), garde rejouée :
**5 failed, 2 passed**. Messages VERBATIM :

```
[fenetre_kill] TERME porte +199.335548 != TERME natif +139.368771 (ecart +59.966777)
-- PV cible 299, bornes RAW [299, 299]

contre-epreuve `spread0` en desaccord :
    [fenetre_kill] a_mordu=False (attendu True), deplacement=+0.000000
    [fenetre_overkill] a_mordu=False (attendu True), deplacement=+0.000000

la feuille OverkillUnit n'a PAS bouge (40.000000) : le cran ne mesure rien
```

Les **2 passed** sont `test_spread0_s_ecarte_du_natif_dans_les_fenetres` et
`test_les_feuilles_expliquent_le_deplacement` : ils restent vrais parce que le port muté **est** la
lecture à spread 0, et que le déplacement nul reste égal à la somme (nulle) des feuilles. Une garde
qui rougirait des sept côtés ne distinguerait pas les deux causes.

### Le défaut que ce rouge a révélé — le calibrage accusait le montage

La **première** version dérivait les PV des crans des bornes **mesurées par le playbook**. Mutée,
elle rendait `[299, 299]`, amplitude 0, et échouait au **setup** des sept tests par :

```
amplitude du spread trop faible (0) : aucune fenetre de palier n'est installable
-- le montage NE PEUT PAS discriminer
```

C'est un rouge qui **accuse le montage pour une faute du port** : un lecteur serait allé chercher un
board cassé. Le calibrage prend désormais le seul **centre** de l'intervalle mesuré (que la mutation
ne déplace pas) et lui applique le spread **lu de la BATAILLE**
(`BattleConfiguration.Damage.DamageSpreadPercentage`, foyer
`engine.services.damage_config.resolve_spread_pct`) — une source qui n'est pas le code testé.
Vérifié : `spread_to_min_max(299)` rend `(239, 359)`, exactement les bornes natives. Les PV des crans
sont donc **identiques** que le port soit sain ou muté (299 et 149 dans les deux runs), et le rouge
vise alors le port. Le message « c'est le montage » n'est plus émis que si l'amplitude **attendue**
est nulle — c'est-à-dire si la BC elle-même ne discrimine pas.

## 6. Livré

| rôle | chemin |
|---|---|
| probe (MESURE) | `scripts/python/probe_419r1tr14r3_spread_paliers_kill.py` |
| garde (TEST) | `scripts/python/tests/engine/test_419r1tr14r3_spread_paliers_kill_live.py` (7 tests) |

**Aucun fichier d'`engine/` n'est modifié par ce volet** : le port était juste, il manquait le régime
qui le prouve. Le seul changement de code est une docstring (volet r4-r1).

## 7. Résidu OUVERT — `#419-r3` (numéro alloué par `probe_468 --suggere 419`)

**`#419-r3` — le port ne modélise aucune `OngoingAttack`, donc `isOutsideAttack = false` est
INEXPRIMABLE.** Nommé par la résolution de `#419-r1-tr14-r4-r1` (§8 de la fiche r4). Le natif porte
un objet `IdunBattle.Core.OngoingAttack` (0x68 octets) partagé par tous les groupes de coups d'une
même attaque : `hitGroupIndex` (`+0x34`), dégât refusé cumulé (`+0x28`), drapeaux (`+0x38`/`+0x39`/
`+0x40`). Le port part d'un état neuf à chaque `execute_ability_attack` — ce qui **coïncide** avec
`isOutsideAttack = true`, la valeur que pose `HeavyBoltPistol`. Le trou n'est donc pas visible ici ;
il le deviendra sur le **premier** call-site qui pose `false` (le cas par défaut d'un `AttackDamage`
imbriqué dans une attaque en cours). Trois conséquences mesurables à porter le jour venu : le
`hitGroupIndex` transmis à `AttackDamageOperation$$GetAttackHits` (qui le pose dans l'`AbilityEntities`
où les effets « coups supplémentaires » le lisent), l'éligibilité à
`AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` (gardée par
`attack+0x34 == 1`), et l'agrégation finale par `ADamageOperation$$RegisterFinalDamage`.
**Débloqueur : un call-site qui laisse l'octet `+0` des options à ZÉRO** — à recenser par balayage
des appels à `DSLBehaviors$$AttackDamage` / `$$AttackWithAttackDamage`, non fait ici.

## 8. Ce qui n'est PAS couvert

* **Le régime BOUCLIER** — le second débloqueur nommé par `#419-r1-tr14-r4-r1` (« ou porte un
  bouclier »). `AccurateShieldDamage@0x78` a ses propres bornes, et le split bouclier est per-coup ;
  aucune unité du montage n'en porte, et `--unit-stat` n'a pas été exercé sur cet axe ici.
* **Les autres consommateurs du slot** — `light_im_up` (0x28, `GetMultiHitAttackPrediction`),
  `shrapnel`, `fury_of_the_ancients` : ils partagent le foyer `get_attack_prediction` du port, donc le
  correctif les couvre par construction, mais **aucun** n'est confronté en régime à palier ici.
* **`hits > 1`** — ce call-site force `hits = 1` (littéral natif). L'interaction spread × multi-coups
  (`previousHitsPrediction`) n'est pas exercée.
* **Le seuil d'overkill** est lu (`_overkill_threshold_pct`), pas varié : le cran overkill suppose le
  seuil courant. S'il change au gameconfig, le cran se re-dérive tout seul (les PV viennent des
  bornes), mais la fenêtre pourrait cesser d'exister — la garde le dirait (`regime NON INSTALLE`).
