# case-277 — l'écart de dégât de `FlailSwing` (1042) : un DÉCALAGE de flux, pas un étage de formule

**Critère (binaire)** : l'écart port/live relevé sur le montage `revive-flail` de `probe_178`
(port **21680**, live **21023**, +3,1 %) vient-il d'UN étage identifié de la chaîne de dégât, ou
est-il diffus ?

**Réponse** : d'UN étage identifié, et il n'est PAS dans la chaîne de dégât — il est **en amont**.
Le rejeu offline de `probe_178` appelait `FlailSwingAbility().execute_behaviour(...)` **à la main**,
ce qui court-circuite `AbilityHandler.visit_ActiveAbilityMessage`, donc l'émission de
`On(0x2b = PreUnitAbility)`, donc le `PickRandomly` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`
que `deathBlightlord` paie à **chaque** cast (case-207). Le flux RNG du rejeu démarrait donc
`|pool|` tirages **trop tôt** et les trois coups d'arme lisaient la mauvaise fenêtre.

**Tous les étages de la formule sont IDENTIQUES des deux côtés**, mesurés et non déduits :
`GetStat(Attack)` = 2609, `PiercingRatio` = 40, armure du défenseur = 0, `nrOfHits` = 3, et la
cellule d'arme réduite = `[4487, 5085]` — la même sur les 4 montages, les 3 seeds et les 2 régimes.

**Le port de `FlailSwing` n'a jamais eu ce défaut** : sa voie de PRODUCTION
(`Runner.apply(ActiveAbilityMessage)`) est bit-exacte avec le live, per-coup, 3/3 seeds. Le défaut
était dans l'**instrument**.

| | genrand natif | genrand port | somme des coups |
|---|---|---|---|
| avant (`execute_behaviour` à la main) | **7** | 6 | 21680 vs live 21023 |
| après (`Runner.apply`) | **7** | **7** | **21023 == 21023** |

---

## 0. Pourquoi « +3,1 % » n'était PAS un facteur

Le premier réflexe interdit ici aurait été de chercher (ou pire, de poser) un correctif
multiplicatif. Trois seeds du **même** montage, même géométrie, même rank, suffisent à le réfuter :

| seed | régime | live | port (raccourci) | « écart » |
|---|---|---|---|---|
| 777 | k1 | 21650 | 21760 | **+0,51 %** |
| 17831 | k1 | 21287 | 21553 | **+1,25 %** |
| 17833 | k1 | 21023 | 21680 | **+3,13 %** |
| 17833 | k2 | 21695 | 21680 | **−0,07 %** |

Un étage multiplicatif rendrait le même pourcentage partout. Ici l'« écart » est simplement
`somme(raw[0..2]) − somme(raw[k..k+2])` dans la même cellule : il change de **magnitude** d'un seed à
l'autre — et **de signe** dès qu'on change le cardinal du pool.

## 1. Décomposition par étage

`probe_277_flail_damage_stages.py` mesure chaque étage séparément, sur le MÊME état et le MÊME flux.

| étage | natif | port (raccourci) | port (production) | verdict |
|---|---|---|---|---|
| profil d'arme (`GetDamageProfile` = Power, `PiercingRatio`) | 40 | 40 | 40 | **identique** |
| `GetStat(Attack)` de l'attaquant | — | 2609 | 2609 | **identique** |
| armure du défenseur (`defender_fixed_armor`) | — | 0 | 0 | **identique** |
| nombre de coups (`GetNumberConstant(0x2f)`) | 3 | 3 | 3 | **identique** |
| cellule réduite reçue par `_run_hits` | — | `[4487, 5085]` | `[4487, 5085]` | **identique** |
| **tirages `genrand_int32` consommés** | **7** | **6** | **7** | **DIVERGE** |
| coups (seed 17833) | `[6785, 7170, 7068]` | `[7194, 7388, 7098]` | `[6785, 7170, 7068]` | **DIVERGE** |

L'étage DÉCALAGE tranche sans modèle : on rejoue le raccourci avec le flux **avancé de `k`
tirages**, `k = 0..4`.

```
decalage k=0  -> [7194, 7388, 7098]
decalage k=1  -> [6785, 7170, 7068]   <== REPRODUIT LE LIVE   (3 seeds sur 3)
decalage k=2  -> [7388, 7098, 7209]
decalage k=3  -> [7170, 7068, 6759]
```

`k = 1` reproduit le live **à l'unité** sur les trois coups et les trois seeds. Une cellule fausse ne
peut pas faire ça : le résidu du modulo change à chaque tirage. Donc **la cellule du port est juste**
et il manque exactement **un tirage en amont**.

## 2. L'artefact natif

### 2.1 Le point d'entrée du cast

Le natif n'a qu'**UN** point d'entrée de cast,
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`, et il émet `On(0x2b)` **tout en
haut**, avant la behaviour. Côté port ce vecteur vit dans
`AbilityHandler.visit_ActiveAbilityMessage` (#120) : `<Ability>.execute_behaviour(...)` est
**en dessous**, et ne l'émet pas. Appeler la behaviour directement, c'est entrer par le milieu de
l'opération native.

### 2.2 Le consommateur qui rend le vecteur NUMÉRIQUE

`…HazeOfCorruption_TargetFinderAbility$$CreateTrigger` = `On(0x2b) & get_OwnerIsCaster` — **aucun
gate d'attaque**, donc il fire pour n'importe quelle ability de `deathBlightlord`, `FlailSwing`
comprise. Son `CreateBehaviour` appelle `TargetsSelector.SelectAllUnits(PickRandomly(pool, 2, …))`
**dans** `CreateBehaviour`, donc paie `min(|pool|, 2)` tirages avant tout coup (case-207, loi
case-130).

Sur le montage `revive-flail` la victime est au centre et `deathBlightlord` **comme**
`ultraApothecary` sont sur son ring 1 :

| terme | contenu |
|---|---|
| `AdjacentEnemies(Self = Blightlord)` | {genesPrimus, ultraApothecary} |
| `AdjacentFriends(Target = genesPrimus)` | {ultraApothecary} |
| intersection (pool) | **{ultraApothecary}** → 1 tirage |

**Témoin direct** : le flux d'événements natif du cast porte **1** bond
`Effect_SourceTriggeredAbility = 1076`, et `NextInternal` côté production ouvre bien sur
`(lo=0, hi=1)` — la signature du `PickRandomly` à pool 1 — avant les trois `(4487, 5086)` des coups.

### 2.3 Pourquoi les tests existants ne le voyaient pas

Les volets (1)-(3) de `test_flail_swing_live.py` rejouent aussi par `execute_behaviour`, et ils sont
**justes** — parce que leur géométrie place le 2ᵉ ennemi à distance > 1 du caster, ce qui vide
l'intersection : `|pool| = 0`, donc 0 tirage à sauter. L'instrument était complice de sa propre
géométrie.

## 3. Le fix

* `scripts/python/probe_178_overkill_gate.py::_replay_attack` — la voie d'ABILITY passe désormais par
  `Runner.apply(ActiveAbilityMessage(...))`, la voie de production. La voie d'ATTAQUE NORMALE reste
  sur `AttackDamageOperation.execute` : elle émet **déjà** `On(0x2b)` en interne
  (`damage_ops/normal.py`, marqueur `ability_type = 1013`), elle n'a jamais eu ce trou, et la router
  par le `Runner` ajouterait à ces régimes des vecteurs after-hit / turn-flow qu'ils n'ont pas.
* `scripts/python/engine/runner/operations/triggers/dispatch/ability.py` — la liste des consommateurs
  de `On(0x2b)` disait encore « AUCUN autre trigger » alors que case-207 en avait ajouté un **qui
  consomme du RNG**. Corrigée : c'est précisément cette ligne qui laissait croire le vecteur inerte.
* **Aucun changement de code moteur** : le port de `FlailSwing`, le trigger Haze et la chaîne de
  dégât sont inchangés.

## 4. La mesure

```
python probe_277_flail_damage_stages.py --seeds 17833 --regimes k1,k0,k2
python probe_277_flail_damage_stages.py --seeds 17831,777 --regimes k1
python probe_178_overkill_gate.py --case revive-flail
python -m pytest tests/engine/runner/test_flail_swing_live.py -q
```

### 4.a L'échelle `k = |pool|` — le second cas discriminant

Les trois régimes sont le **même montage** ; seules bougent les positions des **alliés de la
victime** (`applyAction move` ignore portée et propriété). Un étage multiplicatif survivrait à ce
déplacement ; un décalage de flux le suit.

| seed | régime | bonds natifs | genrand natif | raccourci | production | décalage requis | live == raccourci | live == production |
|---|---|---|---|---|---|---|---|---|
| 17831 | **k0** | 0 | 6 | 6 | 6 | 0 | **oui** | **oui** |
| 17831 | **k1** | 1 | 7 | 6 | 7 | 1 | non | **oui** |
| 17833 | **k1** | 1 | 7 | 6 | 7 | 1 | non | **oui** |
| 777 | **k1** | 1 | 7 | 6 | 7 | 1 | non | **oui** |
| 17833 | **k2** | 2 | 8 | 6 | 8 | 2 | non | **oui** |

* En `k0` les trois voies de rejeu ET le live rendent la MÊME chose (`[6734, 7317, 7502]`) : l'écart
  n'existe plus du tout.
* En `k2` (les deux voisins communs du caster et de la victime occupés — la borne naturelle sur une
  grille hex, qui sature `amount = 2`), le `NextInternal` de la voie de production ouvre sur
  `(0, 2)` puis `(0, 1)` : **bornes décroissantes**, la loi `PickRandomAmountSelector` de case-130,
  et le décalage requis passe à 2.

Cette échelle réfute d'un coup le modèle « forfait de 2 tirages par cast du porteur » (il prédirait
2 partout, donc un `k0` faux) et le modèle « pas de tirage quand le pool tient dans `amount` » (0
partout, donc un `k1`/`k2` faux). Le port suit le **cardinal**, pas une constante.

### 4.b Anti-tautologie

Le probe rejoue aussi la voie de production **avec le trigger `HazeOfCorruption_TargetFinderAbility`
neutralisé** (colonne `pipeline_nohaze`). Elle retombe exactement sur le raccourci (6 tirages,
`[7194, 7388, 7098]`) et **ne reproduit pas** le live : la mesure n'est donc pas vraie « quoi qu'on
fasse ».

### 4.c Garde

`tests/engine/runner/test_flail_swing_live.py::test_flail_swing_cast_entry_point_haze_pool_live`
monte EXPRÈS la géométrie à pool non vide et exige :

* le montage est discriminant (`bonds >= 1`, et `natif > raccourci` en tirages) — sinon il le DIT ;
* `Runner.apply` consomme le même nombre de tirages que le natif **et** rend les mêmes coups ;
* **anti-tautologie** : le raccourci `execute_behaviour` ne reproduit PAS le live.

## 5. Ce qui n'est PAS couvert

* **Le raccourci `execute_behaviour` est un motif SYSTÉMIQUE** : ~136 call-sites directs dans 71
  fichiers de `scripts/python` (probes et tests). Il n'est FAUX que lorsque le caster porte un
  consommateur de `On(0x2b)` non inerte — aujourd'hui `HazeOfCorruption_TargetFinder` (RNG),
  `SwornProtector*` (déplacement d'unité) et `AnvilShield_FrozenAttackerAdvantage` (stat-mod block).
  Le balayage de ces call-sites contre la liste des porteurs n'est pas fait ici : résidu au backlog.
* **`|pool| > 2`** : la CONSOMMATION est exacte à tout cardinal (`min(k, 2)`), mais **qui** est piqué
  dépend de l'ordre source — résidu #215, inchangé.
* **Le régime CRIT** : les mesures ci-dessus sont toutes à `--crit 0,0`. Un crit change le nombre de
  tirages par coup, pas le tirage amont du pool — le décalage serait le même, mais ce n'est pas
  mesuré ici.
* **Les autres régimes de `probe_178`** (`control`/`titus`/`nocrit`/`crit`/`revive-nocrit`/
  `revive-crit`) passent par l'attaque NORMALE, non touchée par ce fix.
