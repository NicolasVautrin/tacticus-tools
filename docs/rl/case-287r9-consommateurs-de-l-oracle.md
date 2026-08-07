# #287-r9 — qui mesure à travers un oracle court-circuité, et qui n'y est pas

#287-r6 a posé le cran (`scripts/python/oracle_targeting.py`) et laissé ses candidats en
« aucun démontré faux — **non vérifiés** ». Cette tranche VÉRIFIE. Trois résultats la dépassent :
le gisement était **sous-compté**, le foyer lui-même **ne débloquait pas tout**, et deux fichiers
lisaient `reasons` **au mauvais niveau** — dont une assertion qui ne pouvait pas rougir.

## 1. Le recensement, re-dérivé

`probe_287r9_consommateurs_oracle.py` (offline, corpus = 2 031 `.py` de `scripts/python`).
Critère de consommateur : la chaîne `"abilityReason"` en **argument d'appel** (rôle dérivé du nœud
parent), pas une mention.

| état | n | ce que ça veut dire |
|---|---|---|
| `SAIN` | 34 | ids d'ability FIXÉS au source, **aucun** dans le gisement |
| `REPARE` | 8 | consulte le foyer (2 l'étaient déjà, 6 posés ici) |
| `SAIN_MESURE` | 7 | ne consulte pas le foyer mais **débloque, et son déblocage ROUGIT s'il échoue** |
| `INDETERMINE` | 4 | aucun id fixé au source — indéterminable offline, **jamais rabattu sur SAIN** |
| `SAIN_LU` | 1 | le recenseur statique le croit exposé, la lecture du site le réfute |
| `NON_VERIFIE` | 7 | exposé, non débloqué, personne n'a mesuré → **résidu `#287-r10`** |

**61 consommateurs**, pas 59 (critère différent : appel réel vs citation). Les chiffres se
**re-dérivent** (`python scripts/python/probe_287r9_consommateurs_oracle.py --tout`).

Deux discriminants ont fait tout le tri, et le second n'était pas prévu :

* **ITÉRER ≠ RÉSOUDRE.** « Le fichier importe `ABILITY_CLASSES` » marquait 34 fichiers exposés.
  La voie de loin la plus fréquente est le LOOKUP `ABILITY_CLASSES[<un id>]()`, qui n'exerce que
  cet id. Seule une **itération** (`for`, `sorted`, `.items()`) exerce les 104. 34 → 17.
* **DÉBLOQUER ≠ GARDER.** `test_multihex_dutyeternal_live` et `probe_91_duty_eternal` portent la
  **même** boucle d'attente sur 1158 ; le premier a `for ... else: pytest.fail`, le second n'avait
  **rien**. Une boucle non gardée qui expire laisse la mesure partir, sans un mot. 17 → 13.

## 2. Le gisement était sous-compté de SIX

`oracle_targeting.ids_a_cooldown_initial()` sans argument ne visite qu'`ABILITY_CLASSES` : il rend
**15**. L'étage amont natif ne connaît pas notre registre — il mord sur l'`ActiveAbilityType`, porté
ou non. Balayé sur l'enum **complet** (260), le gisement est de **21** : `1087`, `1144`, `1152`,
`1208`, `1209`, `1231` court-circuitent sans être portés. Un recenseur ne peut pas rendre zéro sur
ce qu'il ne visite pas.

## 3. `EXPOSÉ ET VÉRIFIÉ` — la mesure, deux bornes exigées

`probe_287r9_expose_mesure_live.py` mesure `casterReason` au tour 1, puis après déblocage. Les deux
bornes : le seul `AVANT` ne dirait pas la CAUSE, le seul `APRÈS` ne dirait pas l'exposition.

| couple | AVANT (tour 1) | APRÈS |
|---|---|---|
| `1158 DutyEternal` / `ultraDreadnought` (MoW) | `ValidRequest`, `cooldown: 2` | `0` |
| `1232 EmpyricAmbush` / `eldarLhykhis` | `ValidRequest`, `cooldown: 1` | `0` |

Un `AVANT` à `0` serait un résultat, pas un échec : le probe le rend en `SAIN (mesure)`.

## 4. Le foyer lui-même ne débloquait pas tout — deux défauts MESURÉS

**(a) `rendre_oracle_passant` comptait UN tour.** Sur `1158` (`initialCooldownTurns = 2`), un tour
fait passer `cooldown` de `2` à `1` et `casterReason` reste `ValidRequest`. Trois ids du gisement
sont dans ce régime (`1143`, `1144`, `1158`). Un consommateur qui aurait appelé le foyer aurait lu
« la bascule n'a pas eu lieu, donc la cause n'est pas le cooldown » — **faux**.
`debloquer_oracle(rpc, rid, caster, ability)` MESURE au lieu de compter : il boucle jusqu'à ce que
`casterReason` tombe à `0`, et rend une PHRASE sinon.

**(b) Le SECOND terme amont EST exercé — #287-r6 le déclarait « non exercé ».**
`*(int*)(ability+0x44) == 0` est le terme **MUNITIONS** d'une Machine of War. Mesuré sur le même
couple `1158` / `ultraDreadnought` :

| `MachineOfWarAmmo` | après 4 tours |
|---|---|
| `0` | `cooldown: 0` et `casterReason` **toujours** `ValidRequest` |
| `9` | `cooldown: 0` et `casterReason` → `0` |

**Aucun nombre de tours ne lève ce court-circuit-là.** Le distinguer du cooldown est ce qui évite de
faire tourner des tours pour rien puis de conclure sur la mauvaise cause.

**Capteur, et il demande une fenêtre de reinject** : `rpc-targeting.ts` publiait `usable`,
`cooldown`, `disabled` — pas `hasAmmo`, pourtant déjà lu par `readAbilityState` et publié par
`decisionView`. Une recopie de deux champs, **livrée** dans cette PR. Tant qu'elle n'est pas
injectée, `cause_du_court_circuit` rend `indeterminee, et le CAPTEUR MANQUE` — jamais un silence.

## 5. `reasons` était lu À LA RACINE — trois oracles muets, dont une assertion vacue

La réponse d'`abilityReason` est `{ok, casterId, targetId, abilityType, resolved, casterReason,
targetReason, abilityState, mutated}`. `reasons` vit **dans** `targetReason`/`casterReason`.
Trois sites lisaient `<reponse>.get("reasons")` — toujours `None` :

* `probe_91_duty_eternal.py` — l'étage A comparait le port à un oracle **structurellement muet**,
  qui « acceptait » tout. Avant : désaccord sur toutes les tuiles sans aire. **Après :
  `accord = 63, désaccord = 0`**, le natif refusant par `TargetMatchesDynamicRule` (0x2) exactement
  là où le port refuse.
* `test_multihex_dutyeternal_live.py` — même faute, **et une doctrine bâtie dessus** :
  un test entier, `test_ability_reason_is_blind_to_the_dynamic_rule_here`, VERROUILLAIT le constat
  « `abilityReason` rend `reasons: []` sur une cible-TUILE de MoW » et servait à ABANDONNER cet
  oracle. Le canal n'était pas aveugle : **le lecteur regardait à côté**. Le test est devenu
  `test_ability_reason_reproduces_the_dynamic_rule_tile_by_tile`, avec un témoin de non-vacuité.
* `test_multihex_dutyeternal_live.py` (second site) — `assert "TargetIsInRange" not in names` où
  `names` valait `""` **quoi qu'il arrive**. Cette assertion ne pouvait pas rougir.

Même signature que #444 (un champ absent lu comme « cible valide »), transposée du `hex` au `reasons`.

## 6. Ce qui n'est PAS couvert

- ~~**Résidu `#287-r10` — 7 consommateurs EXPOSÉS et NON VÉRIFIÉS**~~ — **TRAITÉ**, plus un
  huitième arrivé depuis (`probe_287r11r1r1`, qui rendait `master` ROUGE sur le cran A). Les huit
  sont **JUSTES** ; deux crans posés, quatre déclarés sains par lecture ou par leur propre garde.
  L'« indéterminable offline » de trois d'entre eux était **faux** : le kit gameconfig tranche.
  Détail : `docs/rl/case-287r10-consommateurs-verifies.md`.
- ~~**`InFogOfWarBrokenTargetingRule` toujours non décodée**~~ — **MESURÉE** (#287-r10, board
  `C6_09`, 34 tuiles en brouillard sur 63) : `hex: "0x0"` pour un REFUS, `casterReason == 0`, et son
  `Type` vaut **1**. Son `get_Type` est absent des tables parce qu'IL2CPP **déduplique** son
  `return 1` — l'absence d'un symbole ne prouvait rien. Décodeur Python **corrigé** ; la ligne du
  hook est **livrée et non injectée** (résidu `#287-r10-r1`, `BLOCAGE: capteur`).
- **Le troisième terme amont reste hors mesure** : `IsDamagedMachine && !IsMachinePrimaryAbilityType`
  n'est publié par aucun champ. `cause_du_court_circuit` le range en `indeterminee`.
- **Les 4 `INDETERMINE`** (`probe_243_splash_range_clamp`, `probe_r34_overkill_decision`, `rl_duel`,
  `test_valkyrie_strike_targeting_live`) ne fixent aucun id au source. Ils ne sont **pas** déclarés
  sains : le recensement statique ne peut pas les trancher.
- **`test_targeting_options_masks_live` garde son `if nt == 0x1: continue`** — écartement silencieux
  sans lire `casterReason`. Inoffensif aujourd'hui (`POOL_CASES` n'intersecte pas le gisement),
  faux vert dès qu'un id du gisement y entrera.

## 7. La garde

`probe_287r9_consommateurs_oracle.py`, trois crans :

- **A** — aucun consommateur EXPOSÉ hors du registre `DETTE`. C'est le cliquet anti-cadence : chaque
  probe neuf qui exerce un des 21 ids sans débloquer le rouvre, même forme que `TARGETING_OPTIONS`.
- **B** — aucun `REPARE` ne cesse de consulter le **foyer**. Recopier le prédicat rendrait le cran
  inerte sans que rien ne rougisse.
- **C** — gisement et corpus non vides, 0 fichier illisible. Un enum vide rendrait un vert qui ne
  mesure rien.

**Contre-épreuves, `a_mordu` séparé du verdict** :

| mutation | effet |
|---|---|
| `test_multihex` : lecture remise À LA RACINE | le témoin de non-vacuité **ROUGIT** (`assert []`) |
| `probe_115` : version `origin/master` sur runner frais | **8 VIOLATIONS**, toutes `PlasmaCannon`, toutes `natif=0x1 ValidRequest` |
| `probe_115` : version #287-r9, **même** runner | **0 violation, 0 ability non mesurée** |
