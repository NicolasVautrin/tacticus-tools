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

### 3bis. Le bras `neutered` déclenche `#366-r1-bcpatch-invisible` — et ce que ça a coûté d'honnêteté

La banque de cliquets a **rougi** sur ce montage, au premier passage :
`probe_366_r1_bcpatch_port_blindspot` recense les couples `(ability, variable)` qu'une fixture écrit
dans un seed BC **et** que le moteur Python lit depuis `gameconfig` — toute intersection est une
**désynchronisation ARMÉE**. Les trois variables patchées y entrent, par un site de lecture à
ability DYNAMIQUE.

Le verdict n'est pas silencé, il est **qualifié**. Ici le patch fait **CONVERGER** les deux faces au
lieu de les écarter : le port ne modélise pas les effets 1563/1564, donc les mettre à 0 côté natif
supprime un écart, il n'en crée pas. Trois entrées NOMMÉES sont déclarées dans
`probe_366_r1_bcpatch_port_blindspot._EXCEPTIONS`, avec leur **condition de validité** — *tant que la
face COMBAT n'est pas portée*.

Et cette condition est **mécaniquement gardée**, pas promise :
`test_neutered_arm_condition_of_validity` (OFFLINE, dérivé du registre `EFFECT_CLASSES`, jamais
d'une liste saisie) rougit dès que `SpecialIssueCombiMelta_AdditionalHits` ou `_ExtraDmg` y entre,
et dit quoi refaire. **Contre-épreuve JOUÉE** : l'entrée injectée à la main dans `EFFECT_CLASSES`
fait bien rougir le garde. Second filet, indépendant : le jour où la face COMBAT sera portée,
`test_pair_utility_matches_native_on_all_distances` rougira LIVE — le port appliquerait les coups
supplémentaires du gameconfig là où le natif en applique zéro. Les deux échecs sont **bruyants**,
c'est-à-dire exactement le contraire du mode de panne que le cliquet redoute.

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

* Garde jumelle `scripts/python/tests/engine/test_419r1tr11_combi_melta_live.py` : **7 tests,
  0 skip**, ~23 s (2 runners, libérés au fil de l'eau).
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
* ~~**`#419-r1-tr11-r3`**~~ — **la face COMBAT de 1545 n'est pas portée**. **FERMÉ le 2026-08-10**
  (cf. §7). Les effets **1563** (`d == 2`) et **1564** (`d == 1`) sont portés ; le `Pinned` 1065
  reste ouvert sous `#419-r1-tr11-r4`, et un écart résiduel de 0,96 point sous `#419-r1-tr11-r5`.

## 6bis. La face COMBAT, LUE (2026-08-10) — trois portées, trois constantes, un `==`

`SpecialIssueCombiMelta_InitAbility$$CreateBehaviour` (corps entier) :

```
AddEffect(0x61b = 1563, AbilityStateReference, targets = Owner@DSLSelectors+0x30, options = null)
  op_BitwiseAnd
AddEffect(0x61c = 1564, AbilityStateReference, targets = Owner@DSLSelectors+0x30, options = null)
```

Les deux effets gatent par `IsAtRange`, et **le prédicat est une ÉGALITÉ, pas un `<=`** :
`IdunBattle.Entities.Triggers.IsAtRangeAbilityTrigger$$ShouldTrigger` évalue la formule (slot
`+0x28`), résout les deux sélecteurs (`+0x18`, `+0x20`), demande la distance à la query
(slot `0x6f`) et rend `distance == formule.Calculate()`.

**Le point qui manquait, et il ne se devine pas** : les formules ne sont pas des `Get(n)` au
call-site mais des **champs pré-construits de l'instance `DSLFormulas`**, posés par son `.ctor` :

```
DSLFormulas..ctor :  +0x18 = Const(0)   +0x20 = Const(1)   +0x28 = Const(2)
                     +0x30 = Const(100) +0x38 = Const(-1)
```

D'où les trois portées, chacune sur son propre artefact :

| artefact natif | gate complet | portée |
|---|---|---|
| `..._ExtraDmgEffect$$CreateEffectDamageBonusForAttack` (**1564**) | `OwnerIsCaster & IsAtRange(Caster@+0x48, Target@+0x60, DSLFormulas+0x20) & IsNormalAttack` | **d == 1** |
| `..._AdditionalHitsEffect$$CreateAdditionalHits` (**1563**) | `OwnerIsCaster & IsAtRange(Caster@+0x48, Target@+0x60, DSLFormulas+0x28)` | **d == 2** |
| `..._AddEffectAbility$$CreateTrigger` (`Pinned` **1065**) | `On(0x26 = NormalAttack) & OwnerIsCaster & IsAtRange(..., DSLFormulas.Get(3))` | **d == 3** |

Ces trois valeurs **corroborent** l'empreinte du §3 (d=1 montant plat, d=2 coup entier, d=3 rien)
au lieu de la fitter : elles sont lues au décompilé, l'empreinte les confirme.

Charges utiles, lues aussi : 1564 = `EffectBonus.ForAddition(ConfigAmount(query, config,
abilityState, 8))` — et `AbilityVariableType(8) = extraDmg` ; 1563 = `EffectAdditionalHits.Create`
avec `hits = GetNumberConstant(config, 0x2f = nrOfHits)`, `profile = GetDamageProfile(config)`,
`MinMax = GetMinMaxDamage(this, 0)` / `(this, 1)` (les deux nœuds ROLL et DISPLAY) ;
`_AddEffectAbility$$CreateBehaviour` = `AddEffect(0x429 = 1065 Pinned, AbilityStateReference,
targets = Target@DSLSelectors+0x60)`. Enums vérifiés sur `rnca9r7q6c` : 1563
`SpecialIssueCombiMelta_AdditionalHits`, 1564 `SpecialIssueCombiMelta_ExtraDmg`, 1065 `Pinned` ;
kit = `{damageProfile: Bolter, nrOfHits: 1}`, variables `minDmg` / `maxDmg` / `extraDmg`.

## 7. La face COMBAT, PORTÉE (2026-08-10, `#419-r1-tr11-r3` fermé)

Ce qui bloquait n'était pas la RE mais **un `ctx` incomplet** : le canal #179 portait `t_pos` côté
COMBAT et **ni l'une ni l'autre** position côté PRÉDICTION, donc tout gate `IsAtRange` y était
inévaluable. Les deux `ctx` sont enrichis d'`att_pos` (et de `t_pos` côté prédiction) —
`collect_additional_hit_groups` (`runner/operations/additional_hits.py`) et les deux `_ah_ctx` de
`playbook/prediction/normal_attack.py`. Le gate lui-même a un **foyer unique**,
`entities/effects/base.py::is_at_range`, partagé par les deux effets.

Port : `SpecialIssueCombiMeltaAdditionalHitsEffect` (`effects/loki/hits.py`) et
`SpecialIssueCombiMeltaExtraDmgEffect` (`effects/loki/extra_damage.py`), au registre
`EFFECT_CLASSES` dans le même commit.

**MESURE (bras `raw`, aucun patch — seed 41545, `MC1_67`, 26 lignes), et sa CONTRE-ÉPREUVE**
(`probe_419r1tr11_combi_melta.py [--sans-face-combat]`, MÊME runner, MÊME géométrie) :

| | lignes en accord | |écart| max | régime |
|---|---|---|---|
| sans la face COMBAT (état d'avant) | 11 / 26 | **78,007022** | 15 lignes fausses à d = 1 et d = 2 |
| avec la face COMBAT | **22 / 26** | **0,960412** | 4 lignes, toutes `necroWarden` à d = 2 |

À d = 1 la prédiction native `3457-4661` / `5185-6992` / `5185-6331` est reproduite **au bit près** —
c'est exactement l'empreinte du §3, désormais expliquée au lieu d'être subie.

### 7bis. Le bras `neutered` est MORT, et c'est son propre garde qui l'a tué
`test_neutered_arm_condition_of_validity` disait : *« dès que la face COMBAT entre au registre, le
même geste devient une DÉSYNCHRONISATION »*. Il a rougi au premier passage, comme écrit. La réponse
prescrite est appliquée : **bras `neutered` supprimé** (`write_neutered_seed_bc` retirée), tout
bascule sur `raw`, et les **trois** entrées `SpecialIssueCombiMelta` de
`probe_366_r1_bcpatch_port_blindspot._EXCEPTIONS` sont retirées — vérifié mécaniquement, le couple
n'apparaît plus au recensement. Le garde vit maintenant **à l'envers**
(`test_combat_face_is_registered`) : il rougit si un des deux effets QUITTE le registre.

## 8. Résidus OUVERTS par cette tranche

* **`#419-r1-tr11-r4`** — le **`Pinned` (1065) à d == 3** n'est pas porté.
  `SpecialIssueCombiMelta_AddEffectAbility$$CreateTrigger` = `On(0x26 = NormalAttack, 1) &
  OwnerIsCaster & IsAtRange(Caster@+0x48, Target@+0x60, DSLFormulas.Get(3))` ;
  `$$CreateBehaviour` = `AddEffect(0x429 = 1065 Pinned, AbilityStateReference,
  targets = Target@DSLSelectors+0x60)`. **RE COMPLÈTE** (les deux corps sont lus). Ce qui manque est
  le **montage de la triggered dérivée** : par quelle voie 1545 accorde-t-elle cette ability au
  porteur (`StaticBattleRules.ActiveAbility$$.cctor` / `GetDerivedTriggeredAbilities`, patron
  `Hailstrike` de `#BL-1029r`) — non lu ici. **FOYER:** `scripts/python/engine/runner/operations/triggers/loki/`,
  `scripts/python/engine/services/static_battle_rules.py` — **BLOCAGE:** `etage`.
* **`#419-r1-tr11-r5`** — **4 lignes à −0,960412**, toutes `necroWarden` à d = 2, sur le bras `raw`.
  CAUSE LOCALISÉE : le **bi-canal ROLL/DISPLAY** du canal #179.
  `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` pose
  `min = max = <nœud DISPLAY>.Calculate()` quand `useDisplay` — une cellule **DÉGÉNÉRÉE** que le
  pipeline de prédiction étale ensuite — alors que le port publie `predefined = [min, max]` pour
  tout descripteur à forme PREDEFINED. Le TOTAL ne bouge pas (même moyenne), seule la LARGEUR de la
  plage change : l'écart n'apparaît donc que sur une cible où un terme NON LINÉAIRE de l'utilité
  (`KillUnit` / `OverkillUnit`) est sensible aux bornes. L'étage est **PARTAGÉ** par tous les
  descripteurs #179 à forme PREDEFINED (SquigHound, CordClaw, SorcerousFacade, FearOfTheUnseen,
  FleshmetalGuns, 1563) — le corriger depuis cette tranche changerait six autres effets. Gardé
  dans les TROIS sens par `test_residual_regime_is_exactly_what_we_claim`.
  **FOYER:** `scripts/python/engine/playbook/prediction/normal_attack.py`,
  `scripts/python/engine/entities/effects/loki/hits.py` — **BLOCAGE:** `etage`.

## 9. Ce que ce cas n'établit PAS

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
