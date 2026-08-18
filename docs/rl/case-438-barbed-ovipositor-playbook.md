# case-438 — `BarbedOvipositor` (1204), et le SECOND axe de câblage de la face ATTACK

Premier des 20 résidus ATTACK de `case-419` §7 (tête de liste, **7 porteurs dispatchés**).
Le corps n'avait pas été lu ; il ne ressemble à aucun de ses voisins.

**Résultat** : le playbook est porté, et il a fallu **ouvrir un canal que le port n'avait pas** — la
`DamagePrediction` du case. Sans lui, le playbook serait entré au registre et serait resté **INERTE**,
sans erreur ni test rouge : exactement le patron « porté + non câblé » que #419 recense, mais sur un
autre axe que le sien (#419 : le kit live de l'attaquant ; ici : le contenu du case).

## 1. Le corps natif — QUATRE sorties, dont trois valent 0 pour des raisons différentes

`IdunBattle.AI.Playbook.Loki.BarbedOvipositorPlaybook$$CalculateAttackUtilityInStepsInternal` monte
la SM `d__4` (case @+0x20, délégué scorer @+0x28). Corps :
`BarbedOvipositorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__4$$MoveNext`.

```
if (!case.DamagePrediction.HasValue)                       yield Fix64(0)      // état 1
else if (!case.DamagePrediction.Value.MightBeKill)         yield Fix64(0)      // état 2
else if (UnitExtensions.HasTrait(case.Target, (UnitTrait)5)) yield Fix64(0)    // état 3
else yield Fix64(GetUtilityValue(case.DamagePrediction.Value.WillBeKill
                                 ? "BARBEDOVIPOSITOR_DefinitelyKill"
                                 : "BARBEDOVIPOSITOR_PossibleKill"))           // état 4
```

* **Offsets du case, LUS** (`IdunBattle.AI.Utilities.UtilityAttackCase$$.ctor` et
  `$$ForDamagePrediction`) : caster@+0x10, casterPosition@+0x18, target@+0x20,
  **damagePrediction@+0x28** (`Nullable<DamagePredictionResult>`, 0xa8 o), heal@+0xd0, repair@+0xdc,
  effectType@+0xe8, abilityType@+0xf0.
* **`UnitTrait` 5 = `Mechanical`**, qualifié des DEUX côtés : le mirror rend `Mechanical`, et
  `BarbedOvipositorAbility$$CreateTrigger` monte la MÊME exclusion côté COMBAT (trigger `(target, 5)`
  passé à `AbilityTrigger$$op_LogicalNot`). Le playbook ne fait que refléter le trigger : une cible
  mécanique ne peut pas être pondue dedans.
* **Pas de `.cctor`** — contrairement à `Lakrimae`, les deux clés sont des **littéraux de chaîne**
  chargés dans le corps même (`FUN_1801f4fb0(&DAT_…)`), pas un champ statique.
* **Face MOVE** : `d__3$$MoveNext` est un `yield Fix64(0)` CONSTANT (décompilé lu) — rien à porter,
  son absence de `TRIGGERED_MOVE_PLAYBOOKS` EST le comportement natif.

Poids au gameconfig **et** au seed BC servi (les deux concordent, pas de piège #271) :
`BARBEDOVIPOSITOR_DefinitelyKill` = **50**, `BARBEDOVIPOSITOR_PossibleKill` = **25**.
Régime à **trois niveaux** (0 / 25 / 50) : non dégénéré, donc mesurable.

## 2. Le second axe de câblage — le case porte une PRÉDICTION, le port ne la transportait pas

1204 est le **premier playbook ATTACK porté qui lit `case.DamagePrediction`** (`Psyker`,
`AggressiveOnslaught`, `SuppressiveFire`, `Lakrimae` ne consultent que la cible ou le caster). Le port
éclate le case natif en composants (`ctx, attacker_uid, ability_id, case_tgt_id, attack_tile`) — il en
manquait un. Ajouté : `prediction=None` sur `TriggeredAbilitiesUtility.evaluate_attack_in_steps`,
`triggered_abilities_attack_utility` et les cinq playbooks du registre (quatre l'ignorent, comme
leurs corps natifs).

`None` **mirror `HasValue == false`** — le régime des cases `ForEffect` / `ForHealPrediction` /
`ForRepairPrediction` : ce n'est pas une dégradation défensive, c'est l'état 1 du natif.

**Les trois call-sites qui ont la prédiction la passent** : `playbook/base.py` et
`playbook/excruciating_frequencies.py` (`ev.prediction` de l'event courant), et
`engine_agreement_stages.py::_formula_pair_utility`, qui n'a que des events natifs décodés et
**rematérialise** la struct par `_prediction_from_native_fields` (les trois champs que lisent les deux
accesseurs : `CurrentHealth`, rawMin, rawMax — le reste du décodeur n'est lu par aucun playbook, le
remplir inventerait des valeurs).

## 3. Mesure — les quatre régimes, board `MC1_67`, seed 41504, caster `tyranParasite`

Les PV **ne s'obtiennent pas par chance** : au rank 17 aucun kill n'est possible naturellement
(cibles à ~9 500 PV, attaque normale à ~5 000 max) — un montage nu tombe ENTIER dans le régime
« aucun kill », d'accord pour rien. Ils sont donc calibrés en deux passes, sur les bornes RAW
**natives** (`aiPlaybookPredict` : `willKillDmg` = rawMin@0x1c, `mightKillDmg` = rawMax@0x20 — les
deux scalaires que comparent `get_WillBeKill` et `get_MightBeKill`), puis posés par
`--unit-stat <cible>:Health=N,RemainingHealth=N`.

⚠ **`Health` seul ne mord pas** : `RemainingHealth` est le PV COURANT, et c'est lui que lit
`CurrentHealth@0x00`. Mesuré — avec `Health=1` la cible restait à 9539 PV et les trois régimes de kill
s'effondraient sur un seul. (`--hp-target`/`--hp-player` écrivent bien les deux.)

```
astraBullgryn   mech=F might=T will=T  hp=1      nat=223.333333 port=223.333333 d=+0.000000 | manque=+50.000000
astraCreed      mech=F might=T will=F  hp=2531   nat=174.881563 port=174.881563 d=+0.000000 | manque=+25.000000
astraDreir      mech=F might=F will=F  hp=10693  nat= 44.357176 port= 44.357176 d=-0.000000 | manque= -0.000000
admecDestroyer  mech=T might=T will=T  hp=1      nat=173.333333 port=173.333333 d=+0.000000 | manque= -0.000000
```

Conformité exacte sur les quatre régimes ; playbook retiré du registre ⇒ le port perd **exactement 50**
sur le kill garanti, **exactement 25** sur le kill possible, **rien** sur les deux régimes nuls.
C'est cette mesure qui **TRANCHE l'assignation des deux littéraux** (`DefinitelyKill` sur la branche
`WillBeKill`) — elle n'est pas déduite du nom.

## 4. Le gain, mesuré sur un walk d'agreement réel

`engine_agreement_stages --build --seeds 41504 --steps 26`, même montage, étage UTILITÉ :

| | confrontations | match | pire écart |
|---|---:|---:|---|
| **sans** le playbook 1204 | 4 | 2 (50 %) | `step 6 u85 ab=69->t79 off=214.921 nat=264.921 delta=-50.0` |
| **avec** | 4 | 3 (75 %) | (ce trou a disparu) |

Le trou fermé vaut **-50.000 exactement** — le poids `DefinitelyKill`, sur le Parasite attaquant une
cible non mécanique qu'il tue à coup sûr. Ce même run atteste le chemin
`_prediction_from_native_fields` : c'est lui qui alimente la prédiction dans cet étage.

**Résidu PRÉEXISTANT, hors périmètre** : le mismatch `step 10 u77 ab=69->t85 delta=-18.7429` est
présent dans les DEUX runs, sur un attaquant qui ne porte pas 1204 — étranger à cette tranche.

## 5. Contre-épreuves JOUÉES (sur une contre-épreuve, VERT est le résultat suspect)

1. **Clés inversées** (`DefinitelyKill` ↔ `PossibleKill`) → `test_..._matches_native` et
   `test_..._requires_case_prediction` ROUGISSENT (« rend 25.0 … alors qu'elle doit rendre 50.0 »).
   L'ancre du patch a été vérifiée présente avant d'appliquer la mutation.
2. **Câblage retiré** (`base.py` n'envoie plus `ev.prediction`) → `test_..._matches_native` ROUGIT
   d'**exactement 49.999999992239**. La garde attrape donc la faute au CALL-SITE, pas seulement au
   foyer.
3. **Registre vidé de 1204** → walk d'agreement à 50 % au lieu de 75 % (§4).

Après chaque contre-épreuve, la restauration a été vérifiée **identique au commit**
(`git diff --cached` vide).

## 6. Ce que ce cas ne couvre PAS

* ~~**Le régime MULTI-EVENTS (AoE)**~~ — **MESURÉ (#438-r1, 2026-08-18)**, et la piste indiquée ici
  était FAUSSE : une unité à **Blast** rend **UN SEUL** event (le profil d'arme multiplie les COUPS
  d'un event, pas les events), et le splash **Psyker** aussi (c'est un TERME évalué DANS la feuille).
  La source multi-events est une **ability active à ZONE**. Montage retenu : `1204` greffé sur
  `astraBullgryn` (`PassiveAbilities`, en AJOUT), qui lance `FragBomb (1017)` sur un groupe de trois
  — 3 events, régimes de kill SÉPARÉS par calibrage des PV. `pairUtility` natif
  **123.33483331371099** contre port **123.334833** ; contre-épreuve `--mutant premiere-prediction`
  à **+50,000000 exactement**. Détail : `docs/rl/case-932r1-deathwing-et-scene-de-decision.md` §5.
* **`probe_45_psyker.py`** appelle la feuille SANS prédiction (il isole Psyker, qui ne la lit pas) :
  sans conséquence aujourd'hui, faux dès qu'un porteur de 1204 y passerait.
* **`cannot_be_guaranteed_killed`** reste à `False` dans la struct rematérialisée : le décodeur
  `aiPlaybookPredict` ne publie pas ce flag, exactement comme le `killSure` de
  `_fields_from_native_event`. Même borne inférieure assumée que #372, pas un verdict divergent.
* **Le régime BLOCK** de `get_WillBeKill` (`BlockScenarios[0]` au lieu de `rawMin`) n'est pas exercé
  par ce montage — les quatre cibles n'ont pas de source de block.

## 7. Fichiers

* Port : `scripts/python/engine/playbook/barbed_ovipositor.py` ; registre + câblage :
  `engine/playbook/psyker.py`, `engine/utilities/tile.py`, `engine/playbook/base.py`,
  `engine/playbook/excruciating_frequencies.py`, `engine_agreement_stages.py`.
* Mesure : `scripts/python/probe_438_barbed_ovipositor_pair_term.py`.
* Garde : `scripts/python/tests/engine/test_438_barbed_ovipositor_pair_term_live.py` (4 tests).
