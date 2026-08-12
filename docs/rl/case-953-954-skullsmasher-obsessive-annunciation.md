# #953 — `Skullsmasher` (`worldJakhal`) et #954 — `ObsessiveAnnunciation` (`emperKakophonist`)

Deux passifs de kit, chacun le DERNIER item manquant de son kit. Portés, confrontés live (huit
bras, égalité **à l'unité** port/natif), sous garde
`tests/engine/test_953_954_skullsmasher_obsessive_annunciation_live.py` (20 tests). Montage,
mesure et verdicts : `scripts/python/probe_953_954_skullsmasher_obsessive_annunciation.py`.

## 1. Recensement — par le bloc `methodPointers`, jamais par grep de nom

| famille | classe native (base LUE dans `frida/classes.tsv`) | ce qu'elle DÉCLARE |
|---|---|---|
| #953 | `IdunBattleLogic…Triggered.Loki.Skullsmasher_DamageEffectAbility` : `AOwnerEffectTriggeredAbility` | `GetEffectType` (`return 0x4ef`) · `.ctor` — **rien d'autre** |
| #953 | `…Skullsmasher_ActivateStunAbility` : `BaseTriggeredAbility` | `CreateTrigger` · `CreateBehaviour` · `.ctor` |
| #953 | `…Skullsmasher_TriggerStunAbility` : `BaseTriggeredAbility` | `CreateTrigger` · `CreateBehaviour` · `.ctor` |
| #953 | `IdunBattle.Entities.Effects.Loki.Skullsmasher_ExtraDamageEffect` (`EffectType 0x4ef = 1263`) | `.ctor` · `CreateActiveCondition` · **`CreateTargetSelector`** · `CreateEffectDamageBonusForAttack` · `GetAttackModifier` · `GetMissingHealthSteps` · `GetLocalizationDataInternal` |
| #954 | `…ObsessiveAnnunciationAbility` : `AOwnerEffectTriggeredAbility` | `GetEffectType` (`return 0x598`) · `.ctor` |
| #954 | `…ObsessiveAnnunciation_OverkillAbility` : `BaseTriggeredAbility` | `CreateTrigger` · `CreateBehaviour` · `.ctor` |
| #954 | `…Effects.Loki.ObsessiveAnnunciation_ExtraDmgEffect` (`0x598 = 1432`) | `.ctor` · `CreateActiveCondition` · `CreateTargetSelector` · `CreateEffectDamageBonusForAttack` |
| #954 | `…Effects.Loki.ObsessiveAnnunciation_ExtraCritDmgEffect` (`0x599 = 1433`) | `.ctor` · `CreateActiveCondition` · **`CreateTargetSelector`** · `CreateCritDamageBonus` |
| #954 | `IdunBattle.AI.Playbook.Loki.ObsessiveAnnunciationPlaybook` : `TriggeredAbilityPlaybook<…Ability>` | `.ctor` · les deux `Calculate*UtilityInStepsInternal` |

### ⚠ Le bloc `methodPointers` change les DEUX verdicts d'aura — et un grep en aurait raté un dans chaque sens

Les deux effets de #954 partagent **trois** corps, tous FONDUS par l'ICF donc invisibles à tout grep :

    _ExtraCritDmg : [ .ctor <0x106a610>, CreateActiveCondition <0xec58e0>,
                      CreateTargetSelector <0x106a5c0>, CreateCritDamageBonus <0x106a370> ]
    _ExtraDmg     : [ .ctor <0x106a610>, CreateActiveCondition <0xec58e0>,
                      CreateTargetSelector <0x106a5c0>, CreateEffectDamageBonusForAttack <0x106a660> ]

`1433` est donc une **AURA** au même titre que `1432` — un grep n'en rend qu'une. Le rater aurait
donné un +crit qui ne touche que son porteur, or Adamatar n'est jamais la cible du régime visé :
**le bonus n'aurait JAMAIS mordu**, sans erreur ni trace.

Symétriquement, `Skullsmasher_ExtraDamageEffect` **DÉCLARE** un `CreateTargetSelector` — et il vaut
le corps par DÉFAUT (`<DSLSelectors+0x30>` = `Owner`, `return Selectors@+0x30`). C'est un
SELF-effect. Sur ce lot, la seule présence de la méthode ne dit donc rien : **il faut lire le
CORPS**, les deux cas coexistant dans la même paire d'items.

## 2. Les arbres (mirror 1:1 ; surcharges tranchées par l'ADRESSE de la cible du `call`)

```
1263 $$GetMissingHealthSteps =
    Divide( Percent( StatAmount(Owner@+0x30, StatType.Health = 5, StatPart.Missing = 4, null),
                     StatAmount(Owner@+0x30, Health, StatPart.Maximum = 2, null),
                     RoundingRule.Default ),
            ConfigConst(AbilityConstantType.hpPct = 0x12), RoundingRule.Floor )
1263 $$GetAttackModifier      = Max( <DSLFormulas+0x18> = Direct(0),
                                     Multiply(GetMissingHealthSteps(), ConfigVar(extraDmg = 8)) )
1263 $$CreateActiveCondition  = AmountIsGreaterThanZero( GetMissingHealthSteps() )   # surcharge `IAmountFormula` = 0xed52d0
1263 $$CreateEffectDamageBonusForAttack = ForAddition( get_OwnerIsCaster, GetAttackModifier() )

Skullsmasher_ActivateStunAbility$$CreateTrigger =
    OnDeath(overkill: true, steppable: false) & NOT HasTrait(Target@+0x60, UnitTrait.Object = 0xd)
    & get_OwnerIsActor
    -> AddEffect(0x4f0 = Skullsmasher_StunEffect, stateRef, Owner, Owner, options = <VIDE>)
Skullsmasher_TriggerStunAbility$$CreateTrigger =
    On(EventTriggerType.Attack = 9, ownerNeedsToBeAlive: true) & get_OwnerIsActor
    & HasEffect(Owner@+0x30, 0x4f0, onlyActive: false, EffectTargetType.Both = 6)
    -> AddEffect(0x48a = Stunned, stateRef, source = Owner, targets = Target@+0x60, options = <VIDE>)

1432/1433 $$CreateTargetSelector (COMMUN) =
    AdjacentEnemies(Owner@+0x30, unique: true, UnitSelectionType.OnlyAliveAndTargetable = 3)
1432 $$CreateEffectDamageBonusForAttack = ForAddition(
        get_OwnerIsTarget & IsRangedAttack
        & AreFriends(EffectSource(Effect@+0x38), Caster@+0x48, ByCurrentTeam, anyEntity: false),
        ConfigVar(extraDmg = 8) )
1433 $$CreateCritDamageBonus            = ForAddition(
        get_OwnerIsTarget & AreFriends(<les mêmes>)
        & HasTrait(Caster@+0x48, UnitTrait.Chaos = 0x7ea),
        ConfigVar(extraCritDmg = 0x42) )
ObsessiveAnnunciation_OverkillAbility$$CreateTrigger =
    OnDeath(overkill: true, steppable: false) & TargetIsOverkilled()
    & NOT HasEffect(Owner@+0x30, 0x599, onlyActive: false, Both)
    -> AddEffect(0x599, stateRef, Owner, Owner, turns = <DSLFormulas+0x20> = Direct(1))
```

`OnDeath(a, b)` = `OnDeathEvent(**0**, a, b)`, corps RELU : `On(triggerType) & <Yes@+0x70> &
(a ? Yes : NOT TargetIsOverkilled()) & (b ? Yes : NOT HasTrait(Target, 0x1b = Steppable))`. Les deux
littéraux sont décodés aux OCTETS (`mov dl, 1` / `xor r8d, r8d`).

⚠ **L'event est `UnitDeath = 0`, pas `PreUnitDeath_2 = 2`** — l'écart avec `HeadClaimer` (#947),
qui appelle `OnPreDeath2`.
⚠ **Le gate d'overkill apparaît DEUX FOIS chez #954 et les deux ne disent PAS la même chose** :
`a = true` **DÉSARME** celui d'`OnDeathEvent` ; c'est le `TargetIsOverkilled()` **séparé** du
`CreateTrigger` qui l'EXIGE. Le lire comme « overkill requis » inverse le sens ; l'omettre parce
qu'il est « déjà là » supprime la seule occurrence qui MORD.
⚠ **`ObsessiveAnnunciation_OverkillAbility` n'a AUCUN `get_OwnerIsActor`, ni gate d'équipe** :
n'importe quel overkill du board arme l'aura, y compris celui d'un adversaire. C'est l'écart net
avec ses deux voisins de forme (`TerrifyingCrescendoOverkillAbility`, `HeadClaimerOnDeathAbility`),
qui le portent tous deux.
⚠ **Deux SURCHARGES d'`AddEffect`, une par item** : `0xe9e8b0` (`options:
Nullable<AddEffectBehaviourOptions>` VIDE → durée par `DefaultAmountOfRounds`, donc PERMANENT pour
`0x4f0` et **1 round** pour `Stunned`) chez #953 ; `0xe9e9b0` (`turns: IAmountFormula = Direct(1)`
→ **1 TOUR**, jamais converti) chez #954. Le pseudo-C affiche le même nom et la même arité.

## 3. Ce que la recopie d'une moitié sur l'autre aurait effacé

Les deux moitiés de #954 ont TOUTES DEUX trois conjoints, et **deux seulement sont communs** :

| | conjoints |
|---|---|
| commun | `get_OwnerIsTarget` · `AreFriends(EffectSource, Caster)` |
| DÉGÂT seul | `IsRangedAttack` (surcharge SANS argument, `0xed9990`) |
| CRIT seul | `HasTrait(Caster, Chaos)` |

L'i2 le confirme dans l'autre sens : « +Damage from **RANGED** attacks » contre « +Crit Damage from
**ALL** attacks by friendly **CHAOS** units ». Recopier le gate ranged sur la moitié crit tuerait le
bonus sur toute attaque de mêlée d'un allié Chaos ; l'inverse ferait profiter du +crit un allié
non-Chaos. **Les deux fautes sont silencieuses** — et le test les falsifie séparément (§5).

Autres écarts que la forme n'annonce pas :

* `ForAddition` (`0x1047dc0`) des DEUX côtés de #954, jamais `ForSubtraction` (`0x1048090`) —
  contraste exact avec `ToughToKill` (#950), dont les deux canaux crit sont des soustractions ;
* `extraDmg` **et** `extraCritDmg` sont TOUS DEUX dans `VariablesAffectedByUnitRarityMultiplier`
  (`[8, 66]`) — fait qui ne se lit QUE dans la config (#947 avait le cas inverse) ;
* la magnitude de #953 ne lit AUCUN `EffectLevel` : elle relit les PV du porteur **à chaque coup**,
  et c'est le seul membre de sa fratrie à porter une `CreateActiveCondition` ;
* `Skullsmasher` n'a **AUCUNE face DÉCISION** : ni `SkullsmasherPlaybook` dans le build, ni clé
  `Skullsmasher*` dans `BC.Utilities` (vérifié).

## 4. Le port — où vit chaque face, et la SEULE clé de contexte neuve

Le natif n'a qu'UNE boucle par axe : `EffectsQuery$$GetActiveEffectsWithBonuses` rend
`(effet, CIBLES)` et **ÉCRIT `AbilityEntities+0x18 (Owner) ← la cible courante de l'effet**` avant
d'évaluer chaque trigger (relu verbatim dans `DamagePrediction$$GetCritDamageBonusFromEffects`).
`get_OwnerIsTarget` y signifie donc « la cible du coup est l'une des cibles de l'effet », et non
« le porteur est la cible ». Les agrégateurs du port posent `owner_id = le PORTEUR` : le gate est
rendu en RÉ-ÉVALUANT le `CreateTargetSelector`.

| face | canal | clé neuve |
|---|---|---|
| #953 dégât (SELF) | `create_effect_damage_bonus_for_attack` | `owner_health` = `(hp, hp_max)` — **2 façades** (combat `damage_model.attacker_modifiers`, prédiction `normal_attack` + `abilities`) |
| #953 marqueur + stun | `ABILITY_TRIGGERS["Skullsmasher"]` (2 classes) | aucune |
| #954 dégât (AURA) | `create_aura_defense_damage_malus_for_ally` | **aucune** — `att_pos`/`att_team`/`is_melee`/`owner_pos`/`owner_team` y sont déjà (#950) |
| #954 crit (AURA) | `create_effect_crit_damage_bonus_for_attack` | `adjacent_enemy_ids_of` — un callable PAR PORTEUR |
| #954 décision | `TRIGGERED_MOVE_PLAYBOOKS[1443]` | aucune |

`adjacent_enemy_ids_of` est posé dans les DEUX canaux (crit **et** aura-défense) et par les DEUX
faces : un seul résolveur, donc les deux moitiés du kit ne peuvent pas diverger sur la géométrie.
Il rend les ids de `AdjacentEnemies(...)` évalués contre l'état RÉEL, donc **avec la porte
d'élévation** du ring-1 natif — ce qu'un `hexgeo.distance == 1` écrit au site ne porterait pas
(#271).

## 5. La confrontation live — géométrie CALCULÉE, huit bras, deux boards

Le solveur de géométrie (`probe.geometry`) cherche cinq tuiles **à élévation CONSTANTE**, jouables,
non-`Block`, avec LOS : `V` (victime), `A1` (Adamatar ADJACENT à V, ≥ 2 hex de l'attaquant), `R`
(attaquant ranged, à 2 hex de V), `A2` (Adamatar **ADJACENT À L'ATTAQUANT**, ≥ 2 hex de V), `M`
(tuile de mêlée). `A2` est le cran qui rend le témoin DISCRIMINANT : un port qui lirait l'adjacence
à l'ATTAQUANT rendrait `oa_away` identique à `oa_aura`. La géométrie est ensuite **assertionnée
contre le `boardGraph` LIVE**.

| bras | natif | port | ce qu'il isole |
|---|---|---|---|
| `oa_aura` | 5338 | 5338 | l'aura DÉGÂT mord |
| `oa_away` | 4364 | 4364 | TÉMOIN — Adamatar adjacent à l'ATTAQUANT, pas à la victime |
| `oa_melee` | 4364 | 4364 | TÉMOIN — gate `IsRangedAttack` |
| `oa_crit` | 7064 | 7064 | l'aura CRIT, après overkill |
| `oa_crit_ctl` | 5518 | 5518 | TÉMOIN — aucun overkill ⇒ 1433 absente |
| `oa_crit_nonchaos` | 8766 | 8766 | TÉMOIN — attaquant Imperial |
| `sk_full` | 8973 | 8973 | TÉMOIN — 0 palier |
| `sk_hurt` | 11879 | 11879 | 5 paliers de PV manquants |
| `sk_stun` | 2917 | 2917 | `Stunned` posé, marqueur 1264 |
| `sk_nostun` | 1107 | 1107 | TÉMOIN — même montage, même passage de tour, SANS kill |

**Décomposition par étage, jamais un scalaire fitté :**

* `oa_aura − oa_away` = **974** = `extraDmg[L50] × 160 %` (609 × 1,6). **Re-mesuré sur un second
  couple (board, seed)** — `C4_09`/31337 : 6339 contre 5365, **le même 974** ;
* `sk_hurt` sous mutation : port 8879 contre natif 11879, soit **−3000 = 5 paliers × 200**, et
  `200 = extraDmg[L50] × 180 %`. Les paliers : `(20000 − 9474) × 100 / 20000 = 52 %`,
  `52 // hpPct(10) = 5` ;
* face CRIT sous mutation SÉLECTIVE : **−155** sur le coup (la contribution est +974 points de
  `critDmgPct`, dont la conversion en dégât dépend de la base du coup — non décomposée, §7).

**Les mutations mordent, et seulement où il faut** (registre neutralisé = l'état d'`origin/master`) :
`oa_aura` −974, `sk_hurt` −3000, `oa_crit` (mutation SÉLECTIVE de 1433) −155 ; les trois témoins
`oa_away`, `oa_melee`, `sk_full` **ne bougent pas**. Et le même geste sélectif sur
`oa_crit_nonchaos` ne change **RIEN** : c'est la preuve exécutable que le conjoint
`HasTrait(Caster, Chaos)` MORD.

## 6. Ce que la confrontation a trouvé — un bug de FOYER PARTAGÉ

`melee_defeats`, le compteur de `BlessingsOfKhorne` (« +3 % de dégât par unité vaincue en mêlée »,
TOUTE la faction World Eaters), n'était posé que par la face DÉCISION
(`Scene._seed_battle_counters`). Sur un état **RECHARGÉ** (`runner/snapshot.load_state`) il restait
`None` → `N = 0` → **tout le `+3 % × N` disparaissait dès le premier kill de mêlée**,
silencieusement, et hors de portée de tout test : le régime exige un kill de MÊLÉE **avant** la
mesure.

MESURE (bras `sk_stun`, Macer après UN kill) : natif `[1210, 1204, 503]` = 2917, port
`[791, 607, 1089]` = 2487 — **et en forçant `melee_defeats = 1` sur l'instance, le port rend
exactement `[1210, 1204, 503]`**. L'écart n'était PAS lisible comme un facteur de 3 % : le bonus
déplace `min`/`max`, donc chaque tirage tombe sur un autre entier.

Le canal EXISTAIT et était déjà publié (`decisionView.units[].defeatedByMelee` = `True` sur l'unité
morte en mêlée) : rien à capter, juste à LIRE. Correctif : le corps devient un **foyer PARTAGÉ**
(`entities/effects_state.py::melee_defeats_from_units` / `seed_battle_counters`), appelé par la
face DÉCISION **et** par `snapshot._load_battle_counters` — même rang que `_load_forced_attack_targets`
et `_load_effect_parent_links`, dont il partage exactement la nature (une ENTRÉE de gate que seule
la simulation posait).

Le gisement était **inatteignable** avant : aucun bras porté ne tuait en mêlée avant de mesurer.

## 7. Ce qui n'est PAS couvert

* **La face PRÉDICTION des deux passifs (#953-r1)** : les clés (`owner_health`,
  `adjacent_enemy_ids_of`) sont posées symétriquement dans `playbook/prediction/`, mais aucune
  mesure live ne les confronte. Même contraste assumé que #950-r2.
* **La face DÉCISION de `ObsessiveAnnunciation` (#954-r1)** : `ObsessiveAnnunciationPlaybook` est
  porté (slot **128**, `10 × |ennemis adjacents à la tuile candidate|`) et enregistré, mais aucune
  mesure live ne confronte l'utilité de mouvement. Sa face ATTAQUE est DEAD (`yield Fix64(0)`
  constant, corps relu) — absence du registre == 0, la même valeur.
* **Le facteur de conversion `critDmgPct → dégât` (#954-r2)** : la face CRIT contribue +974 points
  de `critDmgPct` et l'écart observable est +155 sur le coup mesuré. La contribution est confrontée
  et falsifiée séparément (mutation sélective), mais la **conversion** n'est pas décomposée par
  étage — `--armor-target 0` ne l'a pas amplifiée, donc l'atténuation ne vient pas de l'armure.
* **Un ÉCART PRÉEXISTANT, étranger à ce lot (#953-r2)** : avec `emperNoiseMarine` comme attaquant
  RANGED, le port SUR-estime le natif **dans le témoin** (`oa_away` : natif 4699, port 6396) — et
  `--mutate` ne change RIEN à cet écart, donc il ne vient pas de ce port. Ses quatre passifs
  touchant le dégât ranged (`TerrifyingCrescendo`, `SuppressiveFire`, `HeavyWeapon`,
  `ThrillSeekers`) sont les suspects. Le probe a **changé d'attaquant** (`thousTzaangor`, kit inerte
  sans source psychique) plutôt que de mesurer à travers.
* **Le régime `oa_melee` ne prouve rien sur la face CRIT** : elle n'a pas de gate de nature de coup,
  donc une attaque de mêlée d'un allié Chaos DOIT en bénéficier — ce cas-là n'est pas monté (le bras
  `oa_melee` est joué sans overkill préalable).
* **`Skullsmasher_StunEffect` (1264) n'a pas de classe portée** : c'est un marqueur sans canal, posé
  et lu par les deux triggers du même passif. Aucune entrée `EFFECT_CLASSES` — `BaseEffect` est le
  comportement juste.
