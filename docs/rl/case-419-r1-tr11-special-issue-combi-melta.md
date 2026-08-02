# case-419-r1 tranche 11 — `SpecialIssueCombiMelta` (1545), le terme de PORTÉE EXACTE

**Verdict : PORTÉ + CONFRONTÉ LIVE.** Onzième des résidus ATTACK de `#419-r1`. Le port vit dans
`scripts/python/engine/playbook/special_issue_combi_melta.py` (l'en-tête du module porte la RE
complète, lecture par lecture) ; il entre au registre `psyker.TRIGGERED_ATTACK_PLAYBOOKS` dans le
même commit.

Porteurs : `darkaSternguard` « Ramus » (HERO, `kind` lineup) et le npc `darkaBossSternguardLHE`.

## 1. Le corps, en une seule sortie — et une branche qui n'en a AUCUNE

`IdunBattle.AI.Playbook.Loki.SpecialIssueCombiMeltaPlaybook$$CalculateAttackUtilityInStepsInternal`
monte la SM `d__3`. **La disposition se lit dans le WRAPPER, et elle est INVERSÉE** par rapport à
`CosmicHorror` / `SaviorProtocols` : `sm@+0x20 = this` (le playbook), `sm@+0x28 = case`,
`sm@+0x30 = getUtilityVal`. Corps
`SpecialIssueCombiMeltaPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext` :

```
if (this.<IBattleQuery, champ #3 de TriggeredAbilityPlaybook<T>>
        .<slot 0x6c = GetDistance>(case.Target /* @+0x20 */,
                                   case.CasterPosition.MainTile /* @+0x18 */) != 3)
    yield break;                                          // AUCUN yield -- pas un `yield 0`
yield return Fix64.op_Implicit(getUtilityVal("SpecialIssueCombiMelta_LikesRange3"));
```

Les lectures qui ne se devinent pas (les huit sont détaillées dans l'en-tête du module) ; les
quatre qui portent :

* **La tuile lue est celle du CASTER**, pas celle de la cible. Le symbole du getter est
  `IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile` — corps `UnitPosition.get_MainTile(this + 0x18)`
  **dédupliqué par l'ICF** ; sur un `UtilityAttackCase`, `+0x18` est `CasterPosition`. Même quirk
  que `cosmic_horror.py` et `rapid_fire.py`.
* **Le slot `0x6c` est `GetDistance(IEntity, IEntity)`**, identifié par deux proxys NOMMÉS qui
  l'appellent sur le même cache de classe d'interface et consomment sa sortie comme une distance :
  `IdunBattle.AI.Utilities.TileDistanceUtility$$DistanceTo` et
  `IdunBattle.Entities.Selectors.NearestSelector$$GetDistance`. Il retombe sur
  `IdunBattle.Core.Services.MovementQuery$$GetDistance` = `GetTiles` des deux côtés puis MIN sur les
  paires de `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` — **distance hexagonale, aucun
  pathfinding**, `int.MaxValue` si un côté est nul.
* **La branche « pas à portée 3 » ne fait AUCUN yield.** C'est le premier playbook attack porté dans
  ce cas — tous les autres versent un `Fix64(0)` explicite. Sans effet observable, et c'est
  **démontré, pas supposé** : le consommateur
  `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext`
  accumule `total = Fix64.op_Addition(total, step)` depuis un seed `Fix64(0)` — une énumération VIDE
  y contribue exactement 0.
* **AUCUNE gate sur l'ability du case** : ni `IsRegularAttack`, ni `IsNormalAttack`, ni lecture de
  `case.AbilityType` (`@+0xf0`). Le terme tombe pour TOUT case d'attaque à distance 3. C'est une
  divergence assumée avec la face COMBAT de la même ability, dont l'effet `_ExtraDmg` ajoute bien
  `DSLTriggers.IsNormalAttack` à son trigger.

Le littéral `3` est corroboré **deux fois, indépendamment** : le trigger de la face combat
(`SpecialIssueCombiMelta_AddEffectAbility$$CreateTrigger` = `On(EventTriggerType.NormalAttack /* 0x26 */)
& OwnerIsCaster & IsAtRange(Caster, Target, DSLFormulas.Get(3))`, où
`IdunBattleLogic.Entities.DSLFormulas$$Get(int)` fabrique un montant CONSTANT), et le nom de la clé
BC. Le littéral de chaîne est **LU** (`probe_212_bc_key_literals.py` sur ce symbole) :
`SpecialIssueCombiMelta_LikesRange3`, `Utilities.Default.TriggeredAbilities` = **25**.

**Face MOVE** : `...u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` est un unique
`yield Fix64(0)`, son wrapper n'écrit rien dans la SM, et `probe_212` n'y lit AUCUN littéral. Son
absence de `TRIGGERED_MOVE_PLAYBOOKS` **est** le comportement natif.

## 2. Les SIX artefacts natifs de l'id 1545 — et ce qui est porté ici

| artefact natif | face | dans cette tranche |
|---|---|---|
| `IdunBattle.AI.Playbook.Loki.SpecialIssueCombiMeltaPlaybook` (2 faces) | DÉCISION | **PORTÉ** |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_InitAbility` | COMBAT | hors périmètre (`#419-r1-tr11-r3`) |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_AddEffectAbility` | COMBAT | hors périmètre |
| `...Effects.Loki.SpecialIssueCombiMelta_AdditionalHitsEffect` (`EffectType` **1563**) | COMBAT | hors périmètre |
| `...Effects.Loki.SpecialIssueCombiMelta_ExtraDmgEffect` (`EffectType` **1564**) | COMBAT | hors périmètre |
| `IdunBattle.View.AbilityConfigs.Loki.SpecialIssueCombiMeltaVisuals` | VUE | hors périmètre |

Ce que fait la face COMBAT, lu au décompilé : `_InitAbility$$CreateBehaviour` pose sur le porteur
`AddEffect(0x61b = 1563) & AddEffect(0x61c = 1564)` ; `_AdditionalHitsEffect$$CreateAdditionalHits`
construit un `EffectAdditionalHits` (`GetNumberConstant(config, 0x2f)` pour le nombre de coups,
`GetDamageProfile` pour le profil) sous `OwnerIsCaster & IsAtRange(...)` ;
`_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` construit un `EffectBonus.ForAddition`
(`ConfigAmount(..., 8)`) sous `OwnerIsCaster & IsAtRange(...) & IsNormalAttack` ; et
`_AddEffectAbility$$CreateBehaviour` pose `AddEffect(0x429)` sur la cible — **`EffectType` 1065 =
`Pinned`**, c'est-à-dire « Suppressed » côté joueur.

⚠ **ENUMS À QUALIFIER** : à id égal, `EffectType` 1545 = `NanoscarabRepairProtocols` (mécanique sans
rapport). Et les ids des deux effets de la famille (**1563 / 1564**) sont dans un **espace de
numérotation DIFFÉRENT** de l'ability 1545 — ils se re-dérivent de
`data/symbols/<build>/frida/enums.tsv` du build COURANT, jamais d'une fiche antérieure. Sur
`rnca9r7q6c`, `1563 = SpecialIssueCombiMelta_AdditionalHits` (re-dérivé le 2026-08-02).

## 3. Le montage — injection catalogue, DEUX bras, et pourquoi il en faut deux

`darkaSternguard` est un HERO mais **hors catalogue du seed BC** (il figure aux 21 unités que
`catalog_inject.py --missing` recense). Il entre par
`catalog_inject.write_augmented_seed_bc` + `rl_duel build --seed-bc` : le playbook est confronté
**sur son porteur réel**, pas par une greffe.

Le problème que le montage doit résoudre : **la même ability porte une face COMBAT non portée**, et
ses effets 1563/1564 modifient la PRÉDICTION de dégât — donc l'utilité de paire — par un canal qui
n'est pas ce playbook. Empreinte MESURÉE (bornes de dégât natives contre celles du port, board
`MC1_67`) :

| distance | natif | port | écart |
|---|---|---|---|
| 1 | `3457-4661`, 1 coup | `2409-3614`, 1 coup | un montant PLAT (`_ExtraDmg`) |
| 2 | `1280-2578`, **2 coups** | `642-1305`, 1 coup | un COUP ENTIER (`_AdditionalHits`) |
| 3 | `642-1305`, 1 coup | `642-1305`, 1 coup | **RIEN** |

D'où les deux bras :

* **`raw`** — seed BC augmenté, aucun patch. Le terme y est confrontable **à la distance 3
  exactement**, la seule où les deux prédictions coïncident nativement. C'est le bras qui vaut dans
  la **configuration réelle du jeu**.
* **`neutered`** — `minDmg`/`maxDmg`/`extraDmg` de l'ability forcés à **0** dans `BC.Abilities`
  (`catalog_inject.write_variable_patched_seed_bc`, qui écrit AUSSI le sidecar d'épinglage
  `<seed-bc>.pins.json` — sans lui `refresh_ability_configs` réécrirait la config depuis le
  gameconfig vivant, **en silence**, cf. #375). Le coup supplémentaire subsiste mais frappe pour 0,
  et le composite Damage ne lit pas `appliedHits` : les deux prédictions coïncident alors **aux
  trois distances**, et le port est confrontable partout. Le poids d'IA, lui, vit dans
  `BC.Utilities` — le patch ne le touche pas.

**Le patch est PROUVÉ mordant par une mesure NATIVE**, jamais supposé :
`test_combat_face_perturbs_only_below_range_3` compare `pairUtility` des DEUX bras et exige qu'ils
coïncident à la distance 3 et DIFFÈRENT aux distances 1 et 2. Un patch avalé rendrait deux bras
identiques → rouge.

**Deux cibles ADJACENTES** (`astraBullgryn` et `necroWarden`) : une même tuile d'attaque est alors à
distance `d` de l'une et `d ± 1` de l'autre. Un port qui lirait autre chose que `case.Target`
(l'ennemi le plus proche, le caster) rendrait la MÊME valeur sur les deux — ces lignes-là le
trahissent, et le test les exige (`test_target_read_is_the_case_target`).

## 4. Mesures (board `MC1_67`, seed 41545, 26 lignes, 2026-08-02)

`python scripts/python/probe_419r1tr11_combi_melta.py --state-file <abs> [--stage] [--mutants]`

Bras `neutered` — `port == natif` sur **les 26 lignes** (|écart| < 1e-6), et le terme natif
(`natif − port_sans_1545`) vaut :

```
  astraBullgryn  d=3 @(0, 2)  nat=  37.248192 port=  37.248192 | terme_nat=+25.000000
  astraBullgryn  d=3 @(0, 3)  nat=  42.352479 port=  42.352479 | terme_nat=+25.000000
  necroWarden    d=3 @(0, 3)  nat=  60.254158 port=  60.254158 | terme_nat=+25.000000
  astraBullgryn  d=2 @(1, 3)  nat=  17.352479 port=  17.352479 | terme_nat=+0.000000
  necroWarden    d=3 @(1, 3)  nat=  60.254158 port=  60.254158 | terme_nat=+25.000000
  ...
  astraBullgryn  d=1 @(2, 4)  nat=  33.608636 port=  33.608636 | terme_nat=+0.000000
```

**+25.000000 sur les 10 lignes à distance 3, +0.000000 sur les 16 autres.** La ligne `(1,3)` est
exemplaire : depuis cette tuile `astraBullgryn` est à 2 (terme 0) et `necroWarden` à 3 (terme 25) —
c'est la lecture de `case.Target` prise en flagrant délit.

Bras `raw` (aucun patch) — sur les **10** lignes à distance 3, `port == natif` au même bit près et
`terme_nat = +25.000000` ; aux distances 1 et 2 l'écart mesuré va de **+10.01** à **+34.79**, et il
est **entièrement** imputé à la face COMBAT non portée (résidu `#419-r1-tr11-r3`), pas au playbook —
le port et le port-sans-1545 y rendent la même valeur.

### Contre-épreuves — critère = déplacement de `port` par rapport au NATIF

Le critère est licite **parce que** le port non muté colle au natif au bit près sur ce bras. Chaque
mutant doit mordre **et** rester inerte quelque part (une contre-épreuve qui mord partout ne
discrimine rien).

| mutant | d1 | d2 | d3 | lignes inertes |
|---|---|---|---|---|
| `no_gate` (gate retirée) | +25.000 | +25.000 | +0.000 | 13/26 |
| `le_range` (`<= 3`) | +25.000 | +25.000 | +0.000 | 13/26 |
| `range_two` (littéral 2) | +0.000 | +25.000 | +25.000 | 4/26 |
| `caster_tile` (tuile RÉELLE du caster) | +25.000 | +25.000 | +25.000 | 12/26 |
| `caster_not_target` (distance caster↔tuile) | +25.000 | +25.000 | +25.000 | 10/26 |
| `literal_weight` (1 au lieu de la clé BC) | +0.000 | +0.000 | +24.000 | 13/26 |

`range_two` est celle qui compte le plus : c'est **exactement** la lecture qu'un RE de la face
COMBAT ferait croire (ses effets mordent à 1 et 2), et elle est fausse.

## 5. Ce qui a été rejoué

* Garde jumelle `scripts/python/tests/engine/test_419r1tr11_combi_melta_live.py` : **6 tests,
  0 skip**, 28,7 s (2 runners, libérés au fil de l'eau).
* Cliquet `tests/test_419_playbook_wiring_ratchet_offline.py` : **3 passés** (l'entrée 1545 a un
  porteur réel et un corps natif non trivial).
* Voisins de registre : `test_419_lakrimae_pair_term_live.py`,
  `test_419_r1_fire_of_absolution_pair_term_live.py`, `test_419_t6_cosmic_horror_pair_term_live.py`,
  `test_419r1tr9_rapid_fire_live.py`.
* Banque de cliquets `scripts/ratchets.ps1`.

Chiffres à RE-DÉRIVER, pas à citer.

## 6. Résidus NOMMÉS

* **`#419-r1-tr11-r1`** — **le MULTI-HEX est collapsé à la main tile** dans la face DÉCISION.
  `MovementQuery$$GetDistance` prend le MIN sur les paires de PIEDS (`EntityExtensions$$GetTiles`) ;
  `scene.pos_by_id` ne porte que la MainTile, et le seul côté qui pourrait avoir plusieurs pieds ici
  est la CIBLE (la tuile d'attaque est un `(col,row)` unique). Une MoW visée à distance 3 de sa main
  tile mais 2 d'un de ses pieds ferait rendre 25 au port là où le natif rend 0. **NON CONFRONTÉ**
  (aucune MoW au montage). Fermeture : publier l'empreinte de la cible dans la `Scene` de décision,
  comme `engine.runner.components.get_unit_feet` le fait côté runner.
* **`#419-r1-tr11-r2`** — **`aiPredict` INFIDÈLE à la tuile demandée** sur 3 tuiles du montage : il y
  rend le profil d'une AUTRE distance, de façon **stable et reproductible** (`fresh: true` compris),
  alors que `pairUtility` et le port s'accordent au bit près. Le canal est donc un **diagnostic, pas
  un oracle** — il n'entre dans AUCUNE assertion de la tranche (mode `--stage` seulement). Point
  d'ancrage à instrumenter pour trancher : le chemin `GetAllPredictions` du RPC contre le
  `ComparablePlaybook$$MakeDamagePredictions` qu'emprunte `pairUtility`.
* **`#419-r1-tr11-r3`** — **la face COMBAT de 1545 n'est pas portée** (effets 1563/1564, et le
  `Pinned` 1065 posé sur la cible). Empreinte mesurée sur la prédiction native au §3. C'est le seul
  écart natif/port restant du montage, et il est entièrement hors du périmètre de la face DÉCISION.

## 7. Ce que ce cas n'établit PAS

* Le comportement sur le porteur **npc** `darkaBossSternguardLHE` : le montage ne joue que
  `darkaSternguard`. Ce qui est confronté, c'est le CORPS du playbook, dont la RE établit qu'il ne
  lit ni stat, ni trait, ni arme du caster.
* Les distances **> 3** : hors portée de l'arme, `pairUtility` et le port ne calculent plus la même
  chose (le port ne produit aucune action). Le corps natif y rend 0 par la même gate `!= 3`, mais ce
  n'est pas confronté.
* Le régime **`case.Target` non-unité** (une tuile, un objet) : le dispatcher n'appelle la face
  ATTACK qu'avec des cibles-unités.
* Le régime **KILL** : aucune ligne du montage ne tue (PV ~8,5 k contre ~7 k de dégât max), donc les
  feuilles `KillUnit`/`OverkillUnit` du composite Damage valent 0 des deux côtés. Le terme, lui, ne
  les lit pas.
