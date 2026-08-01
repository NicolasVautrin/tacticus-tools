# case-366-r1-statmod — quelles classes de stat-modifier re-dérivent une magnitude déjà ÉCRITE ?

`IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` retourne littéralement
`StatModifierComponent+0x10` et `IdunBattle.Entities.Effects.StaticStatModifierEffect$$
GetStatModificationAmount` littéralement `+0x14` : **le natif RELIT**. Le capteur publie déjà ce
composant champ par champ (`frida/hooks/game/effects.ts::readStatModifier`), et #423 a posé
`BaseEffect.captured_stat_mod_amount()`. Question de ce cas : **qui d'autre re-dérive, et où est-ce
FAUX ?**

## 1. Le discriminant, lu au décompilé — il est DANS LA FEUILLE, pas dans l'ability

Les **trois** surcharges `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`
`(targets, effectType, statType, amount, turns, isHidden)` construisent
`IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$.ctor(this, logger, isDynamic,
**source = NULL**, targets, …)`. Les **deux** `…$$AddStaticStatModifierEffectToOwner` y passent
`Owner@DSLSelectors+0x30` **en source ET en cibles**.

Et `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute`, dans sa boucle sur les
cibles :

    lVar9 = <entité-cible de l'itération>;
    if (sourceSelectionné != 0) lVar9 = sourceSelectionné;   // sinon : la CIBLE reste la source

⇒ **`source = null` n'est pas un choix d'ability : c'est la feuille.** Toute pose
`AddStaticStatModifierEffect(<sélecteur ≠ Owner>)` écrit `EffectComponent.SourceUnit = le PORTEUR`.
`effects_state.baked_ability_state` résout l'`AbilityState` PAR ce champ : il ne peut donc pas
retrouver le poseur, et aucun correctif de ce côté-là n'aurait fermé l'écart.

Deux corollaires qui bornent le gisement :

* une magnitude qui ne consulte **aucun** `AbilityState` (constante d'ability `GetNumberConstant`,
  variable de TRAIT, section `Effect` de la BC, littéral, delta pré-calculé à la pose) est
  insensible au porteur ⇒ la feuille ne l'atteint pas, même cross-unité ;
* la famille **DYNAMIQUE** ne lit pas `+0x14` du tout :
  `IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$GetStatModificationAmount` appelle son
  slot `+0x798` et **recalcule**. Les surcharges `AddDynamicStatModifierEffect*` ne passent aucun
  `amount` ⇒ `Execute` écrit **0** dans le composant. Lire ce 0 serait pire qu'une dérivation
  approchée — d'où le gate `IsDynamic` de `captured_stat_mod_amount()`.

## 2. Le recensement — 31 classes, re-dérivé du code

`python scripts/python/probe_366r1_statmod_rederivation_census.py` (mesure **comportementale** :
on fait varier `(ability_level, active_ability_level, multiplier)` et on regarde si le montant bouge ;
la forme OVERRIDE `applied_stat_mods` est scannée textuellement, faute de pouvoir fabriquer un
`StatsComponent.ctx`).

`EFFECT_CLASSES` = **151** entrées, **31** déclarent une stat-modification. Ventilation :

| verdict | n | classes |
|---|---|---|
| **CROSS — concernées** | **2** | `1000 ShockAssault_Buff` (#423), **`1171 SereneUnifierStormOfFire` (ce cas)** |
| OWNER — `…ToOwner` / `(Owner@+0x30)`, porteur == poseur | 15 | `AnvilShield_AdditionalBlock` · `AnvilShield_BlockChanceBelowHealthCap` · `AnvilShield_FrozenAttackerAdvantage` · `RealityUnbound_ExtraMaxDamage` · `UnbreakableDuty_Damage` · `UnbreakableDuty_Health` · `VisionsOfHeresy_ExtraPierceMelee` · `VisionsOfHeresy_ExtraPierceRanged` · `StandVigil_ExtraArmor` · `MomentShackle_ExtraBlockChance` · `MomentShackle_ExtraBlockDamage` · `AncestralFortune_ExtraCritChance` · `AncestralFortune_ExtraBlockChance` · `MyWillBeDoneOverlord_ExtraDamage` · `ProtectorImperative` |
| SRC — source passée EXPLICITEMENT au poseur | 1 | `AugmentedAssault_ReduceArmor` (`AddDynamicStatModifierEffect(targets = target@0x178, **source = self@0x148**)`) |
| insensible à l'`AbilityState` (constante / ctx / littéral) | 13 | `ActOfFaith_Effect` · `BlackRage_ExtraMove` · `ContagionsOfNurgle_ArmorReduction1/2` · `Contaminated_Unit` · `CursedPlagueBell_ExtraMove` · `DestroyTheWitch_ExtraMove` · `RealityUnbound_Movement` · `RealityUnbound_Range` · `RelentlessMarch_Effect` · `Swarm_HitReduction` · `ThrillSeekers` · `Waaagh_ExtraMovement` |

Feuilles vérifiées au décompilé pour les 18 classées :
`AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour` (les deux volets sur
`Owner@+0x30`), `RealityUnboundExtraMaxDamageAbility$$CreateBehaviour` (`Owner@+0x30`),
`VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour` (`Owner@+0x30` ×2),
`UnbreakableDutyAbility$$ExecuteBehaviour` (`…ToOwner` ×2),
`SereneUnifierAbility$$CreateBehaviour` (sélecteur `units`).

⚠ **`Waaagh_ExtraMovement` est bien posé CROSS-UNITÉ** (`AddStaticStatModifierEffect(<sélecteur
Waaagh>)`) et n'est PAS concerné : sa magnitude est `Direct(GetNumberConstant(0xe))`, la même sur
n'importe quel porteur. Le seul axe « cross-unité » ne suffit donc pas — c'est la CONJONCTION.

⇒ **`1000` n'était PAS le seul cas** : il y en avait deux, et il n'y en a que deux.

## 3. `1171 SereneUnifierStormOfFire` — la bascule, chiffrée

Pose (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour`,
branche `k = 0` du cycle `Modulo(PlayerTurnsStarted, Direct(3), Direct(0))`) :

    AddStaticStatModifierEffect( units, 0x493, statType = 0 ATTACK,
                                 ConfigVar(8 = extraDmg, <AbilityState du PASSIF d'Aun'Shi>),
                                 TurnsFromRounds(1), isHidden = 0 )

`units = (AdjacentFriends(Caster@+0x48, 1) + Caster@+0x48) + UnitsFromFaction(SurroundingFriends(
Caster, ConfigConst(0x16)) − AdjacentFriends, T'au = 9)` — self **et** alliés.

Montage `probe_366r1_statmod_captured_channel.py` : `MC1_67`, seed `3711`, `tauAunShi` + `tauCrisis`,
`--no-ai`. Le régime NOMINAL est **dégénéré** (`buildNormalizedBC` met tous les niveaux à 50) ⇒ bras
DISSOCIÉ obligatoire : `--unit-stat "tauCrisis:PassiveAbilityLevel=20"` (appliqué APRÈS la
normalisation).

| mesure | Aun'Shi (u81) | allié `tauCrisis` (u83) |
|---|---|---|
| `EffectComponent.SourceUnit` | **81** | **83** ← le porteur, pas le poseur |
| `StatModifierComponent` natif | `{StatType 0, Amount 797, ApplyCounter 1, IsDynamic 0, IsHidden 0}` | **identique** |
| `unitConfig` (passif / actif / mult) | 50 / 50 / 180 | **20** / 50 / 180 |
| re-dérivation gameconfig depuis CE porteur | 797 | **76** (`extraDmg[20] × 180 %`) |

Conséquence offline sur l'allié, **avant → après** la bascule :

| | attribué | résidu opaque | ATTACK avec l'effet | ATTACK après expiration |
|---|---|---|---|---|
| LIVE (natif) | — | — | 1501 | **704** |
| MOTEUR **avant** | 76 | **721** | 1501 | **1425** (écart +721) |
| MOTEUR **après** | **797** | **0** | 1501 | **704** (écart 0) |

Bras NOMINAL rejoué : `derived(allié) == derived(Aun'Shi) == Amount == 797`, moteur 704 == live 704.
Il ne **prouve** rien (les deux modèles y sont indiscernables) — il atteste la **non-régression**.

## 4. Ce que le port change

* `entities/effects/base.py` — `captured_stat_mod_amount()` gagne le gate **`IsDynamic`** (mirror du
  dispatch natif) ; nouvel accesseur **`captured_stat_mod_stat()`** (`+0x10`), jumeau exact sur
  l'autre champ de la paire, **sans** le gate (le stat est relu par TOUTE la famille, seul le montant
  bifurque).
* `entities/effects/loki/serene_unifier.py` — lit le canal capté (stat **et** montant), repli sur la
  dérivation `ConfigVar(8)` indexée par le slot PASSIF quand le canal est absent (pose offline,
  capture antérieure au capteur) : EXACT sur Aun'Shi, APPROCHÉ sur un allié (sous-attribution
  absorbée par le résidu opaque, jamais une sur-attribution).
* `entities/effects/loki/shock_assault.py` — lit aussi `captured_stat_mod_stat()` (le montant l'était
  déjà depuis #423).

Aucune autre classe n'est touchée : les 16 OWNER/SRC gardent leur dérivation, **validée live sur des
porteurs-source où elle est exacte**.

## 5. Le cliquet

`probe_366r1_statmod_rederivation_census.py --check` (rc 1) + les deux tests
`test_statmod_captured_channel_offline.py::test_no_unclassified_ability_state_rederivation_in_the_registry`
/ `…::test_every_cross_unit_class_reads_the_captured_channel`. Toute nouvelle classe dont la
magnitude bouge avec l'`AbilityState` doit inscrire sa feuille de pose dans `POSE_TARGETS`
(`OWNER` / `SRC` / `CROSS`), et une `CROSS` doit lire le canal. **Ce gisement n'est alimenté que par
notre propre cadence de portage** — c'est exactement la forme de `probe_181` / `probe_120`.

Contre-épreuve jouée : `native = None` forcé dans `serene_unifier.get_stat_modification_amount`
⇒ **2 tests rouges** (`…prefers_the_captured_native_amount`, `…every_cross_unit_class_reads…`),
`git diff --stat` vérifié avant lecture.

## 6. Ce qui n'est PAS couvert

* **La face DÉCISION.** `playbook/scene.py::_effect_source_ability_states` alimente la même
  `EffectsState.seed`, donc la bascule vaut aussi côté prédiction — mais elle n'y est **pas
  confrontée** (aucun montage de prédiction sur un allié buffé par 1171).
* **Le canal `AbilityState` de l'entité-effet** (`EffectComponent+0x18`, exposé par
  `readEffectAbilityStateRaw`) n'est **pas** branché sur `EffectFactory.create`. C'est l'autre
  réponse possible au même problème — elle rendrait la dérivation exacte au lieu de la
  court-circuiter, et couvrirait les classes DYNAMIQUES (que `Amount` ne peut pas servir). Non fait :
  aucun consommateur mesuré n'en a besoin aujourd'hui. **Résidu nommé.**
* **La famille DYNAMIQUE cross-unité.** Aujourd'hui aucune : la seule classe dynamique posée hors de
  l'Owner (`AugmentedAssault_ReduceArmor`) reçoit sa source explicitement. Si une arrive, le canal
  `Amount` ne la servira pas (gate `IsDynamic`) — il faudra le canal `AbilityState` ci-dessus.
* **`ApplyCounter > 1`** : ASSERTÉ à 1 dans le montage, jamais atteint. Régime neuf s'il apparaît.
* **`IsHidden`** : capté (`0` ici, `1` pour 1000), non consommé par le port.
* **Un seul couple (board, seed)** pour 1171 cross-unité (`MC1_67` / 3711) — la mécanique n'est
  positionnelle que par le sélecteur d'adjacence/portée, que le montage exerce (l'allié est bien
  arrosé).
* **Les 13 classes « insensibles »** ne sont pas confrontées une par une : leur exclusion repose sur
  la mesure comportementale (le montant ne bouge pas avec l'`AbilityState`), pas sur une lecture de
  chacune de leurs feuilles de pose.
