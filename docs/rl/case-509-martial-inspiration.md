# #509 — `1191 MartialInspiration` : le buff est posé AVANT l'attaque, et son gate tient dans le 7ᵉ argument

Porteur : `custoBladeChampion` « Kariyan » (Adeptus Custodes, **lineup**, dans
`rl_duel build --list-pool` au rank 17). Avant cette tranche, l'ability était un **no-op
silencieux** : absente d'`ABILITY_CLASSES`, donc la face DÉCISION la choisissait (playbook porté
depuis #106) et l'exécution l'ignorait — 0 dégât, 0 effet, aucune erreur.

Build de RE : `rnca9r7q6c` (= `data/symbols/CURRENT`).

## 1. L'artefact natif est un ARBRE DSL, pas une boucle impérative

`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialInspirationAbility$$ExecuteBehaviour`
(slots `DSLFactory` : `+0x78 Behaviors`, `+0x80 Formulas`, `+0x90 Selectors` ; slots
`DSLSelectors` : `+0x48 Caster`, `+0x60 Target`) :

    buff = DSLBehaviors.AddEffect( 0x580 = 1408 MartialInspiration_ExtraDamage,
                                   GetAbilityStateReference(this),
                                   source = Caster@+0x48, targets = Caster@+0x48,
                                   turns  = DSLFormulas.Direct(1) )
    atk  = DSLBehaviors.AttackWithAttackDamage(
               Caster@+0x48, Target@+0x60,
               AActiveAbility.MinMaxDamage(this, abilityState, isPrediction = 0),
               DSLSelectors.Direct( Nullable(AActiveAbility.GetDamageProfile(this)) ),
               DSLFormulas.Direct( AActiveAbility.GetHits(this) ),
               abilityOrEffect = AbilityOrEffect(this), options = default, selectionType = 2 )
    AActiveAbility.Execute( this, AbilityBehaviour.op_BitwiseAnd(buff, atk), entities )

Trois lectures qui ne se « lissent » pas :

* **`op_BitwiseAnd`, pas `op_Addition`** — les deux factories allouent la MÊME classe
  `IdunBattle.DSL.CombinedBehaviour`, et l'`Execute` est PLAIN (aucun `AtomicGroup`).
* **`Direct(1)` est déjà en TOURS** (pas un `TurnsFromRounds`) → le buff dure un tour.
* **le buff est à GAUCHE** : il est posé avant que l'attaque ne calcule son dégât, et il buffe
  donc CETTE attaque. Même forme que `FoulInfusion` (#500).

`...$$.ctor` : forme **STATIC-COPY** (aucun `TargetingOptions$$.ctor`) — recopie des 0x40 octets du
preset `<TargetingOptions statics>+0x40` puis `AActiveAbility..ctor(this, &opts, 0)`.
→ masque `0x4000 = TargetIsEnemy` **seul**, `isSelfCasting = 0`, `range = RANGE_ADJACENT`,
`forceMeleeTarget = 1` ; **`AbilityAttackType = 0 = DirectTargetAttack**` (3ᵉ argument littéral).
Même preset que 1195 `TalonsOfTheEmperor` et 1217 `TheLionsWrath`.

## 2. L'effet 1408, et les TROIS surcharges d'`op_Implicit`

`IdunBattle.Entities.Effects.Loki.MartialInspiration_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

    pct    = DSLFormulas.ConfigVar( 0xa = extraDmgPct, GetAbilityState(this), config@this+0x60 )
    turns  = DSLFormulas.TotalTurnsWithAttacksMade( Owner@DSLSelectors+0x30 )
    gate   = get_OwnerIsCaster & ( CurrentAbilityIs(0x4a7) | CurrentAbilityIs(0x527) )
    return Nullable( EffectBonus.ForPercentIncrease( gate, Multiply(pct, turns),
                                                     AbilityOrEffect(0x580) ) )

Les trois `mov edx, imm32` du corps sont suivis de **trois `call` DISTINCTS** — lus à
l'assembleur, l'argument étant perdu par la décompilation :

| littéral | surcharge appelée | enum réel |
|---|---|---|
| `0x4a7` = 1191 | `AbilityOrEffect$$set_ActiveAbility` | **`ActiveAbilityType.MartialInspiration`** |
| `0x527` = 1319 | `AbilityOrEffect$$set_TriggeredAbility` | **`TriggeredAbilityType.LegacyOfCombat`** |
| `0x580` = 1408 | `AbilityOrEffect$$set_Effect` | **`EffectType.MartialInspiration_ExtraDamage`** |

Les rabattre sur un seul enum aurait été **silencieux** : `1191` est aussi
`TriggeredAbilityType.HyperAggression` et `EffectType.HuntersBeyondDeathPsykerSuppression`,
`1319` est aussi `EffectType.SmashaEad`.

`...$$GetBuffPct(dsl, config, abilityState)` est le même couple `ConfigVar(0xa) ×
TotalTurnsWithAttacksMade(Owner)`, exposé à part.

**ÉTAGE** — `ForPercentIncrease` écrit la %-list du `DamageModifiers` ATTAQUANT, consommée
**APRÈS** perçage/armure : ce n'est ni un scale des bornes d'arme, ni un additif.

## 3. Le compteur `+0x30` n'est pas `+0x20`, et la divergence est NATIVE

`IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackMade` (volet lu) :

    this[0x50] = target.Id;
    if (this[0x40] != null) {                        // HashSet unitsAttackedThisTurn
        if (Count(this[0x40]) == 0) this[0x30] += 1; // TotalTurnsWithAttacksMade
        Add(this[0x40], target.Id);
        this[0x20] += 1;                             // TotalAttacksMade
        ...
    }

`+0x30` n'avance donc **qu'une fois par tour**, au premier coup porté ; `+0x40` est vidé par
`...$$ResetUnitsAttackedThisTurn`, appelé par `StartTurnOperation$$Execute` / `$$ResetUnit` /
`$$ResetMachine` (jamais `EndTurnOperation`). Seul appelant de `RegisterAttackMade` :
`IdunBattle.Operations.RegisterAttackOperation$$Execute` — le **même** que
`RegisterAttackReceived`, dont le port plaçait déjà le mirror (`record_attacked`) dans le
chokepoint post-résolution `AttackDamageOperation._apply_damage_pipeline`.

⚠ **La face PRÉDICTION lit `+0x20`, la face COMBAT lit `+0x30`.** C'est une divergence NATIVE,
portée telle quelle des deux côtés (`playbook/prediction/abilities.py::_martial_inspiration_inputs`
contre `entities/effects/loki/martial_inspiration.py`) — elle était déjà documentée dans
`probe_17_martial_inspiration.py`, et cette tranche porte la seconde moitié.

## 4. Ce que la tranche livre

| fichier | rôle |
|---|---|
| `engine/runner/abilities/custodes.py` | `martial_inspiration_tree()` + `MartialInspirationAbility` (masque + `ABILITY_ATTACK_TYPE`) |
| `engine/entities/effects/loki/martial_inspiration.py` | l'effet 1408 (gate + magnitude) |
| `engine/entities/effects/factory.py` | entrée `EFFECT_CLASSES` |
| `engine/runner/components.py` | `register_attack_made` / `unit_turns_with_attacks_made` / `reset_units_attacked_this_turn` + 2 champs `UnitComponent` |
| `engine/runner/operations/damage.py` | le volet ATTAQUANT de `RegisterAttackOperation`, dans le chokepoint partagé |
| `engine/runner/operations/turnflow.py` | `ResetUnitsAttackedThisTurn` à l'entrée de tour |
| `engine/runner/damage_model.py` | `att_ctx["turns_with_attacks_made"]` + `att_ctx["ability_type"]` (canal `CurrentAbilityIs`, distinct de `trigger_ability_type` = `TriggeringAbilityIs`) |
| `engine/runner/snapshot.py` | seed de `+0x30` depuis `actorStats.totalTurnsWithAttacksMade` — **le hook le publiait déjà**, aucun capteur neuf requis |
| `engine/runner/abilities/targeting.py` + 2 tests | contrat de disjonction (5 endroits) |

## 5. Le bug que seul un régime NON DÉGÉNÉRÉ a montré

Le premier port était **bit-exact au régime `TotalTurnsWithAttacksMade = 0`** et faux d'un facteur
`1 + n × 33 %` partout ailleurs. Cause : la feuille `AttackWithAttackDamage` était construite
**sans son `ability_type`** — c'est-à-dire sans le **7ᵉ argument natif**
(`abilityOrEffect = AbilityOrEffect(this)`), qui alimente `att_ctx["ability_type"]`, donc le gate
`CurrentAbilityIs(1191)` de l'effet. Le gate restait fermé, l'effet posé et `active` mais **inerte**.

À `n = 0` le produit `pct × n` est nul : un port qui IGNORE l'effet est alors indiscernable du
port juste. **C'est exactement le régime dégénéré que le montage doit refuser.**

## 6. Validation live (`probe_509_martial_inspiration.py`, `test_509_martial_inspiration_live.py`)

Montage : board `MC1_67`, Kariyan `(5,8)` — l'**unique** voisin libre de `(6,8)` (la tuile n'a que
DEUX voisins, `boardGraph`), toutes à élévation 1 ; `necroWarden (6,8)` + `necroOverlord (6,7)` à
300 000 PV ; `--crit 0,0 --block-target 0,0` ; un figurant `deathRotbone` côté joueur pour que le
cast ne bascule pas le tour (sans lui, le `dumpRng` d'après compte aussi le turn-start ennemi).
Le montage DRIVE Kariyan : quand 1191 est en cooldown il attaque normalement, ce qui fait avancer
`+0x30`.

Deux régimes d'armure × deux régimes de compteur (**0** et **3**), séquence coup par coup :

| régime | compteur | PORT | NATIF |
|---|---|---|---|
| nominal (armure 0) | 0 | `[4456, 3923, 4320]` | idem |
| nominal | 3 | `[5970, 5960, 6169]` | idem |
| armure (2000) | 0 | `[2228, 1961, 2160]` | idem |
| armure | 3 | `[2985, 2980, 3084]` | idem |

**Attribution EXACTE des tirages** (2 `genrand_int32` par coup à `cc = 0`, famille ATTACK) :
port `6 = 2 × 3`, natif `18 = 2 × 9`. Les **6 coups d'écart** ne sont pas un mystère : ce sont ceux
de la triggered `1319 LegacyOfCombat` (3× Power sur chacun des deux ennemis adjacents), que le natif
joue dans le même appel `act` et que le port ne porte pas. L'identité `tirages_natif == 2 ×
<tous les coups>` est **vérifiée**, pas supposée.

**Contre-épreuves** (hors ligne, même capture, même MT) — à compteur 3, chacune diverge :

| variante | total nominal | total armure |
|---|---|---|
| `ref` | 18099 | 9049 |
| `sans_effet` | 9095 | 4548 |
| `ordre_inverse` (attaque puis buff) | 9095 | 4548 |
| `sans_ability_type` | 9095 | 4548 |

Ratio `ref / sans_effet` = **1.9900** en nominal = `1 + 3 × 33 %` **exact** ; **1.9897** en régime
armure — l'écart est la signature de la %-list appliquée **après** perçage/armure (un port qui
scalerait les bornes d'arme serait bit-exact à armure 0 et faux ici).

À compteur 0, les trois contre-épreuves rendent le MÊME résultat que `ref` : c'est la preuve que
ce régime, seul, ne mesure rien.

## 7. Résidus nommés

* **`#509-r1` — la triggered `1319 LegacyOfCombat` n'est pas portée.** C'est le passif de Kariyan
  (« After performing his first attack each turn, Kariyan performs an additional attack »), MESURÉ
  live : après le cast de 1191, le natif joue 3× Power sur **chaque** ennemi adjacent (6 coups, 12
  tirages, deux cibles). Conséquence directe : la **2ᵉ branche** du gate de l'effet 1408
  (`CurrentAbilityIs(TriggeredAbilityType 1319)`) est structurellement inatteignable côté port, et
  le dégât total d'un tour de Kariyan est sous-estimé. Le mirror la porte quand même (elle est
  testée offline) : le jour où 1319 entre au registre, elle s'allume sans rien changer ici.
* `selectionType = 2` (9ᵉ argument d'`AttackWithAttackDamage`) : aucun étage de `UnitSelectionType`
  n'est matérialisé sur cette feuille — résidu PARTAGÉ par tous ses call-sites.
* `options` (8ᵉ argument) : struct ZÉROÉE au call-site → aucun `isForceOverkill`, aucun `forceCrit`.
* `TotalAttacksMade` (`+0x20`) reste **non seedé** dans le `State` : aucun consommateur du runner
  ne le lit (la face PRÉDICTION a son propre canal, `playbook/scene.py::actorstats_by_id`).
* Un `State` rechargé **sans** `actor_stats=` repart à `turns_with_attacks_made = 0` : le bonus est
  alors NUL, pas faux (dégradation restrictive), comme les trois compteurs de tuiles voisins.
