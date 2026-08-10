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
  (cf. §7). Les effets **1563** (`d == 2`) et **1564** (`d == 1`) sont portés.
* ~~**`#419-r1-tr11-r4`**~~ (le `Pinned` à `d == 3`) et ~~**`#419-r1-tr11-r5`**~~ (les 4 lignes à
  −0,96) — **FERMÉS le 2026-08-10**, cf. §8. Les TROIS portées du kit sont désormais portées et
  confrontées live.

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

## 8. Résidus ouverts par la tranche 7 — les DEUX sont FERMÉS (2026-08-10)

### 8.1 `#419-r1-tr11-r4` — le `Pinned` (1065) à `d == 3` : PORTÉ + CONFRONTÉ LIVE

Port : `SpecialIssueCombiMeltaAddEffectAbility`
(`runner/operations/triggers/loki/special_issue_combi_melta.py`), au registre
`ABILITY_TRIGGERS["SpecialIssueCombiMelta"]` dans le même commit.

**LE MONTAGE ANNONCÉ ÉTAIT FAUX, et les deux dicts natifs ont été LUS.** La fiche pistait
`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities` (patron `Hailstrike` / `Drachnyen`).
Or :

* `...ActiveAbility$$GetDerivedTriggeredAbilities` est indexé par **`ActiveAbilityType`** ; l'active
  de `darkaSternguard` est `SternguardFocus`, pas 1545 ;
* `...**TriggeredAbility**$$GetDerivedTriggeredAbilities` (dict `<statics>+0x88`, peuplé en fin de
  `StaticBattleRules.TriggeredAbility$$.cctor`) compte **DEUX entrées, lues verbatim** :
  `0x3ef -> [0x3fc]` (1007 `LivingLightning` -> 1020 `LivingLightning_MoveEffect`) et
  `0x48e -> [0x491]` (1166 `TheWrathfulDead` -> 1169 `TheWrathfulDead_Overkill`). **`0x609` (1545)
  n'y figure pas** (0 occurrence dans tout le cctor).

Le montage est le chemin **ORDINAIRE d'une passiveAbility** : `units.passiveAbilities` de
`darkaSternguard` porte `SpecialIssueCombiMelta`, et DEUX classes natives vivent sous ce nom
(`_InitAbility` + `_AddEffectAbility`) — forme identique à `LetTheGalaxyBurnAbility` /
`LetTheGalaxyBurn_ResetAbility`. Corroboration indépendante : `classes.tsv` porte
`TriggeredAbilityPlaybook<...SpecialIssueCombiMelta_AddEffectAbility>`, donc le playbook du §1 est
attaché à CETTE classe — le +25 mesuré live prouve que le porteur en tient une instance.

Deux lectures de plus, faites ici et non recopiées :

* le sélecteur SOURCE de l'`AddEffect` est **NUL** (surcharge 5 args ; les deux surcharges 5 args
  passent `0` en `param_5` d'`AddEffectBehaviour$$.ctor`), et le fallback est LU dans
  `AddEffectBehaviour$$Execute` : `src = <cible courante>; if (Select(+0x60) != 0) src = ...` ⇒
  **la source EST la cible**, d'où `source_from_target=True`. ⚠ `SuppressiveFireAbility$$Create
  Behaviour`, qui pose le MÊME effet 1065, appelle la surcharge **6 args** avec
  `source = Owner@+0x30` : recopier le patron sans relire la surcharge aurait écrit la mauvaise
  source ;
* le littéral de portée est un `DSLFormulas.Get(3)` **construit au call-site**, contrairement aux
  deux effets du même kit dont la formule est un champ pré-construit (`+0x20 = Const(1)`,
  `+0x28 = Const(2)`). Trois artefacts, trois lectures.

**MESURE LIVE** (`probe_419r1tr11_r4_pinned.py`, seed 41545, `MC1_67`, porteur injecté au
catalogue) :

| bras | natif | port |
|---|---|---|
| `d == 3` | `Pinned` posé | `Pinned` posé |
| `d == 2` | rien | rien |

Le second bras est ce qui rend le premier discriminant (`IsAtRange` compare par **égalité** : un
port écrit `<= 3` passerait le premier et tomberait sur celui-là). Garde :
`tests/engine/runner/test_419r1tr11_r4_pinned_live.py` (4 tests) ; **contre-épreuve JOUÉE** —
l'entrée `ABILITY_TRIGGERS` retirée fait rougir 2 tests, le bras `d == 2` restant vert.

⚠ **PIÈGE DE MONTAGE, mesuré** : piloter le port par
`ActiveAbilityMessage(ability_type = <id concret d'attaque normale>)` rend `ported: false` — un
NO-OP **silencieux**. Le premier run rendait donc « port : pas de Pinned », et ce faux rouge
accusait le montage, pas le port. La porte du port est `AttackUnitMessage`.

### 8.2 `#419-r1-tr11-r5` — les 4 lignes à −0,960412 : FERMÉ, et la fiche se trompait de nœud

**`GetMinMaxDamage(this, 1)` n'est PAS un `RandomAmount` — c'est une MOYENNE.** Corps entier de
`IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, isPrediction, 0xc, 0xd)` :

```
minNode = ConfigVar(0xc = minDmg, AbilityStateFromEffect(...), config)
maxNode = ConfigVar(0xd = maxDmg, AbilityStateFromEffect(...), config)
isPrediction == 0 -> DSLFormulas.RandomAmount(minNode, maxNode)     # nœud ROLL    (+0x08)
isPrediction != 0 -> DSLFormulas.Average(minNode, maxNode)          # nœud DISPLAY (+0x10)
```

et `DSLFormulas$$Average(a, b)` = `DivideAmount(SumAmount(a, b), Direct(2), rule = null)` ->
`DivideAmount$$Calculate` -> `AAmountFormula$$RoundFix64Result(., 0)` = **`Fix64.Round`
demi-vers-le-PAIR** — donc un ENTIER, jamais un `.5`. C'est le même foyer et le même arrondi que la
famille (a) de #344.

`BaseEffect$$AdditionalHits(this, entities, useDisplay)` choisit : `useDisplay` ⇒
`min = max = <+0x10>.Calculate()` (cellule dégénérée à la moyenne, que le pipeline étale ensuite à
±20 % via `GetBaseDamageFix64`) ; sinon `min = <+0x08>.CalculateMin()`, `max = ...CalculateMax()`.

**Correctif** : le descripteur 1563 publie désormais `amount` (canal PREDICTION) **en plus** de
`min`/`max` (canal COMBAT) — patron déjà en place chez `InfernalPacts` et `FleshmetalGuns. La face
COMBAT **ne peut pas** bouger : `runner/operations/additional_hits.py` préfère `min`/`max` dès
qu'ils existent, ce qui EST le mirror du `useDisplay = 0` d'`ExecuteAdditionalHitsWithoutDamage
ProfileType`.

**MESURE** (même runner, même géométrie, 26 lignes) : **22/26 en accord, |écart| max 0,960412**
avant → **26/26, 0,000000** après.

**RAYON DE SOUFFLE, MESURÉ — et la fiche le décrivait de travers.** Elle annonçait « six autres
descripteurs », dont `FleshmetalGuns` (qui publie DÉJÀ `amount`, donc hors radius) et sans nommer
trois autres. Le vrai critère est arithmétique : `avg ± 20 %` et `[min, max]` coïncident
**exactement ssi `max == 1.5 × min`**. Balayage des courbes gameconfig (50 niveaux) :

| descripteur | publie `amount` ? | niveaux où les 2 modèles coïncident | écart max (pts/coup) |
|---|---|---|---|
| `SpecialIssueCombiMelta_AdditionalHits` (1563) | **oui, depuis ce commit** | 0/50 | 221,6 |
| `SorcerousFacade_AdditionalHits` | non | **0/50** | **111,2** |
| `FearOfTheUnseen_ExtraDamage` | non | **0/50** | **66,6** |
| `SquigHound_AdditionalHits` | non | 17/50 | 0,4 |
| `CordClaw_AdditionHits` | non | 20/50 | 0,4 |
| `InfernalPacts` / `FleshmetalGuns` / `CyclicIonBlaster` | oui | — | — |

⇒ le correctif de 1563 ne touche **aucun** autre descripteur (le fichier n'est modifié qu'au
descripteur 1563), et **quatre** autres portent le même défaut, dont deux à 66–111 points. Résidu
`#884`.

⚠ **CE QUE LE MONTAGE NE DISCRIMINE PAS, et il faut le dire** : au niveau servi
(`ability_level = 50`, `multiplier = 180`) les bornes valent `[3589, 4387]`, de somme **PAIRE** ⇒
`Fix64.Round` et la moyenne exacte `.5` rendent le MÊME entier. La contre-épreuve a été JOUÉE
(mutant `amount = (min + max) / 2` sans arrondi) : **26/26 à 0,000000**, comme le port non muté.
L'arrondi demi-vers-le-pair est donc établi **par le décompilé seul** ; il faudrait un couple
(niveau, multiplicateur) de somme IMPAIRE pour le séparer live (195 des 450 balayés le sont, ex.
`mult = 180, lvl = 21` → `[360, 441]`). C'est exactement le vice qu'un témoin non discriminant
produit, et il est nommé plutôt que maquillé.

Le garde `test_residual_regime_is_exactly_what_we_claim` **a rougi comme il était écrit pour le
faire** (sa 3ᵉ assertion exigeait qu'au moins une ligne diverge) et prescrivait la suite : retirer
l'exemption `_is_residual` de (1), le supprimer, fermer le résidu. C'est fait ; à sa place,
`test_bi_channel_display_is_modelled_and_discriminant` empêche le vert de (1) d'être VIDE (il exige
`max/min != 1.5` sur le montage, et que le descripteur publie les deux canaux).

## 9bis. Résidu OUVERT par cette tranche

* **`#884`** — **le bi-canal ROLL/DISPLAY du canal #179 est faux sur QUATRE autres descripteurs**.
  `SorcerousFacade_AdditionalHits` et `FearOfTheUnseen_ExtraDamage` publient `min`/`max` sans
  `amount` alors que leur `CreateAdditionalHits` passe un 8ᵉ argument `GetMinMaxDamage(this, 1)` =
  `Average` : la PRÉDICTION du port y publie `predefined = [min, max]` là où le natif publie une
  cellule dégénérée à la moyenne, étalée ±20 %. Écart mesuré sur les courbes gameconfig :
  **111,2** et **66,6** points par coup au pire niveau (ratio `max/min` = 2,00 et 1,25).
  `SquigHound_AdditionalHits` et `CordClaw_AdditionHits` portent le même défaut mais à **0,4 point**
  (leurs courbes sont à `max ≈ 1,5 × min`, où les deux modèles coïncident presque) — c'est ce qui a
  rendu le gisement invisible. Le correctif est d'une ligne par descripteur (patron
  `InfernalPacts` : ajouter `"amount": _round_fix64(Fraction(mn + mx, 2), 0)`), mais chacun exige sa
  CONFRONTATION LIVE sur son propre porteur — le porter en aveugle serait spéculatif.
  **FOYER:** `scripts/python/engine/entities/effects/loki/hits.py` — **BLOCAGE:** `porteur`.

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
