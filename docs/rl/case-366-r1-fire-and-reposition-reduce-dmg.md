# case-366-r1 — `1110 FireAndReposition_ReduceDmg` : une lecture PAR COUP, gatée par le TOUR

**Question, binaire.** Le port retire-t-il du dégât reçu par Calandis (`eldarRanger`) exactement ce
que le natif retire, et se tait-il exactement quand le natif se tait ?

**Réponse : OUI, après DEUX câblages** — le fil du gate de tour, et le niveau d'ability ACTIVE.
Porteur `eldarRanger`, HERO **au pool** (`rl_duel build --list-pool` : 97 unités, il y figure) ;
voie directe, ni greffe npc, ni injection catalogue, ni relique.

## 1. Le canal : lecture PAR COUP côté DÉFENSE, pas une stat, pas une aura

`IdunBattle.Entities.Effects.Loki.FireAndReposition_ReduceDmgEffect$$CreateEffectDamageMalusForDefense` :

    EffectBonus.ForSubtraction(
        get_OwnerIsTarget & IsRangedAttack & NOT <DSLTriggers+0x28>,
        ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60) )

`ForSubtraction` écrit le slot `EffectBonus` **@+0x18** ; l'agrégateur est
`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`. Côté port :
`create_effect_damage_malus_for_defense` → `flat_reductions` → **additif DÉFENSEUR PRÉ-perçage**,
exactement le slot @+0x10 de `NightshroudDmgReductionEffect` (#120/#111). Ce n'est donc **ni** le
canal STAT projetée (`AddDynamicStatModifierEffectToOwner`, cf. `1107`/#373), **ni** une pose de
`statType` lue par `get_stat` (cf. `1345`/`1346`).

Corollaire de mesure : le montant config n'est le dégât retiré **que si l'armure du porteur est
nulle** — sinon il traverse le perçage et se dilue. D'où `--hp-player` dans le montage (il met
`Armor`/`FixedArmor` à 0), qui fait lire la soustraction 1 pour 1.

## 2. `DSLTriggers+0x28` = `IsTurnOf(Owner)` — lu, pas deviné

Le champ n'est pas nommé au décompilé ; il est **écrit** par
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`, avec la MÊME classe (`DAT_1833ab568`) et
la MÊME forme d'appel que `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)`, sur
`DSLSelectors+0x30`. Ce dernier est identifié **Owner** de longue date
(`entities/selectors/accessors.py`, quatre lectures convergentes).

Deuxième confirmation, indépendante : le corps de
`IdunBattle.Entities.Effects.Loki.MartialSuperiority_VisualEffect$$CreateActiveCondition` est
**exactement** `op_LogicalNot(<DSLTriggers+0x28>)` — un corps trivial, donc partageable, et qui
porte **4 xrefs DATA** (4 slots de vtable). C'est le nœud `NOT IsTurnOf(Owner)` déjà connu du port
(`destroy_the_witch.py` le documente sous son autre nom de table,
`AReactivateOverwatchEffect$$CreateActiveCondition`).

**Le gate n'est PAS redondant avec la durée** `TurnsFromRounds(1)` de la pose : il ferme la fenêtre
du RESTE du tour de Calandis, où un tir ennemi peut la toucher — l'**OVERWATCH** (elle-même porte le
trait `Overwatch`, et son adversaire type aussi).

### Le natif expose ce gate DEUX fois, et la seconde est mesurable directement

`EffectComponent.IsActive` (champ ECS, relu par le hook et publié en `decisionView.effects[].active`)
bascule avec le tour — **mesuré**, sur les deux boards :

| | tour du PORTEUR | tour ENNEMI |
|---|---|---|
| canal `decisionView` ACTIF | absent | présent |
| `EffectComponent.IsActive` | **False** | **True** |
| `remaining` | 2 | 1 |

Il y a donc, en plus du trigger de l'`EffectBonus` lu au §1, une **active-condition** qui éteint
l'effet entier pendant le tour du porteur. Son corps est le `NOT IsTurnOf(Owner)` ci-dessus ; il
n'est **pas attribuable statiquement** à cette classe (corps fondu, un seul propriétaire nommé dans
chaque table), donc le port **ne** déclare **pas** d'`is_active` — ce serait écrire une méthode qu'on
n'a pas lue sur cette classe. Sans conséquence observable : sur le canal live-seed, l'effet n'est de
toute façon pas matérialisé pendant le tour du porteur ; sur la voie COMBAT offline, où l'instance
survit au changement de tour, c'est le gate du §1 qui ferme.

## 3. La magnitude est indexée par le niveau de l'ability **ACTIVE**

`IdunBattle.Entities.Effects.Loki.FireAndReposition_ReduceDmgEffect$$.ctor` écrit `mov edx, 0x427`
(= `ActiveAbilityType.FireAndReposition` = 1063) puis appelle la surcharge de
`IdunBattle.Core.AbilityOrEffect$$op_Implicit` qui exécute `set_ActiveAbility` — surcharge tranchée
**par son corps**, jamais par son nom (les quatre homonymes écrivent trois champs différents).
Donc l'`AbilityState` que résout `GetAbilityState(effet)` est celle de l'ACTIVE.

`ConfigVar(0x12)` = `AbilityVariableType 18 = dmgReduction`, 65 niveaux (30 → **2183**), et
`dmgReduction` ∈ `variablesAffectedByRarityBonus` ⇒ **scalé par le multiplier de rareté**.
i2 : « … she takes -{dmgReduction} Damage from ranged attacks. »

**Ce point a REFUTÉ le port initial.** Le régime nominal ne peut pas le voir : `buildNormalizedBC`
met `ActiveAbilityLevel` **et** `PassiveAbilityLevel` à `targetAbilityLevel` (50), si bien que lire
l'un ou l'autre donne le même chiffre. En les dissociant
(`--unit-stat "eldarRanger:ActiveAbilityLevel=30"`, passif 50) :

* natif — retire `dmgReduction[30] x 1.8 = **716**` ;
* port (avant fix) — retirait `dmgReduction[50] x 1.8 = **2992**`.

Cause : `EffectsState.seed` ne propageait **que** le niveau PASSIF. La cascade
`active_ability_level -> ability_level -> level`, qu'écrivent **19 classes d'effet** (dont
`OverwhelmingWrath_RangeDmgReduction`, `SmashaEad`, `Waaagh_ExtraDamage`, `Hailstrike_ExtraPierce`,
`ConquerorImperative`…), retombait donc TOUJOURS sur le passif.

**Le fix a été RÉ-ÉCRIT au rebase, et c'est le rebase qui a donné la bonne forme.** `#382`
(`case-382-effect-source-ability-state.md`), mergé pendant ce cas, a introduit dans
`EffectsState.seed` un `ability_state_by_unit = {uid: (multiplier, abilityLevel,
activeAbilityLevel)}` — le triple **complet**, par entité — consulté **par la SOURCE** de chaque
effet (`baked_ability_state`). Il laissait explicitement le troisième membre à `None` pour le
**REPLI porteur** (« l'élargir ici déborderait du cas »). Or c'est exactement ce repli que prend un
owner-effect comme `1110` (source == porteur). Le fix se réduit donc à **une seule ligne de
sémantique** : le repli tire le triple d'`ability_state_by_unit[porteur]` quand il y est, au lieu
de forcer `None`. Aucune table nouvelle, aucun paramètre nouveau — les DEUX faces alimentaient déjà
ce triple (COMBAT `runner/snapshot.py::_ability_state_from_config`, DÉCISION
`playbook/scene.py::_effect_source_ability_states`), et le fork « moteur ≠ prédiction » ne peut donc
pas se rouvrir.

## 4. La pose

`IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$ExecuteBehaviour` :

    UseActiveAbility(Owner@0x48, Target@0x60, UnitNormalAttackType(Owner))
  + ResetMovement(...)
  + AddEffect(0x456, <AActiveAbility.get_AbilityStateReference>, source=Owner, targets=Owner,
              TurnsFromRounds(1))

`source == targets == Owner` ⇒ ce cas n'est **pas** dans le régime « porteur ≠ source » de
`#366-r1-src` : l'`AbilityState` bakée par le natif est bien celle du porteur.

## 5. Mesures live — 2 boards, 2 seeds, 4 axes, toutes bit-exactes

Montage : `probe_366_r1_fire_and_reposition.py` (1v1 `eldarRanger` vs `necroWarden`, pilotage des
DEUX camps, cast, captures, rejeux offline sur le MÊME flux MT). `necroWarden` porte **une arme
mêlée ET une arme ranged r3** : le même ennemi sert les deux axes, une variable de moins.
`--crit 0,0 --crit-target 0,0 --block-target 0,0 --block-player 0,0` : une seule variable bouge.

| | `MC1_67` / 31337 | `C4_09` / 4242 |
|---|---|---|
| RANGED, tour ennemi — **live** | `[17433, 17920]` | `[13533, 20641]` |
| RANGED — **port** | `[17433, 17920]` | `[13533, 20641]` |
| CONTRE-ÉPREUVE (sans l'effet, même flux) | `[20425, 20912]` | `[16525, 23633]` |
| écart par coup | **2992** = `dmgReduction[50] x 1.8` | **2992** |
| CONTREFACTUEL de tour (`current_player` = porteur) | `[20425, 20912]` | `[16525, 23633]` |
| MÊLÉE, tour ennemi — live / port / sans effet | `[20912]` / idem / idem | `[23633]` / idem / idem |
| NIVEAU dissocié (`ActiveAbilityLevel`) | 30, attendu **716** | 20, attendu **284** |
| — live / port | `[19709, 20196]` / idem | `[16241, 23349]` / idem |
| — écart par coup | **716** | **284** |

La contre-épreuve est ce qui rend la mesure opposable : sans elle, « port == live » ne prouverait pas
que la réduction change quoi que ce soit dans ce montage.

**Deux pièges de montage, tous deux mesurés et corrigés dans le probe :**

* **L'ennemi mourait avant la pose.** `FireAndReposition` ENCHAÎNE une attaque normale de Calandis
  (`UseActiveAbility`), et elle mitraille l'approchant en **Overwatch** : sur l'axe mêlée,
  `necroWarden` passait 5061 → 1446 PV pendant le placement, puis mourait au cast
  (`Match_Winner`) — plus d'effet à mesurer. D'où `--hp-target`.
* **`1111 WireweaveNet_CounterAttack` décale le flux MT.** La contre-attaque de Calandis
  (« the first time Calandis is targeted by a normal melee attack during the enemy's turn »)
  n'est PAS portée (ability de la tâche voisine) et consomme des tirages **avant** le coup mesuré :
  le rejeu offline partait décalé (live `[20649]` vs port `[20912]`, écart **263** — du bruit de
  tirage, pas une réduction). Le probe retire donc le passif du porteur
  (`--unit-stat "eldarRanger:PassiveAbilities=[]"`), et l'axe mêlée redevient **bit-exact**.
  Sans ce levier, le bras mêlée n'aurait rien pu conclure : Δ = 263 est indiscernable du bruit,
  alors que la réduction cherchée vaut 2992.

## 6. Mutations adversariales — les gardes sont ROUGES quand on les casse

| mutation | ce qui rougit |
|---|---|
| **M1** inscription `EFFECT_CLASSES` retirée | `1110 est route sur BaseEffect` + `le contrefactuel ne CHANGE rien` |
| **M2** gate `NOT IsTurnOf(Owner)` neutralisé | `le gate NOT IsTurnOf(Owner) ne ferme pas` + `au tour du PORTEUR la reduction s'applique encore ([17433, 17920] au lieu de [20425, 20912])` |
| **M3** gate `IsRangedAttack` neutralisé | `le gate IsRangedAttack ne ferme pas (['Subtraction', 2992])`, sur les 4 axes |
| **M4** `EffectsState.seed` sans le niveau ACTIF (repli porteur forcé à `None`) | `le port a seede active_ability_level=None alors que le natif expose L30 pour l'ACTIVE` |

M4 est la mutation qui compte : elle remet le port dans l'état **d'avant ce cas** — qui est aussi,
littéralement, l'état dans lequel `#382` l'avait laissé — et c'est un état que le régime nominal
déclare vert.

## 7. Ce qui n'est PAS couvert

* **`is_active` (l'active-condition) n'est pas portée** — §2 : le corps existe et est mesuré côté
  natif, mais il n'est pas attribuable statiquement à cette classe. Aucune conséquence observable
  sur les canaux du port (1110 n'alimente que le canal dégât-défense, déjà gaté).
* **`1111 WireweaveNet_CounterAttack`** (même porteur) n'est pas portée — hors périmètre, et
  explicitement retirée du montage pour que l'axe mêlée soit mesurable. Sa queue live est visible
  dans le montage `--keep-passive` (contre-attaque `[2373, 2664]`).
* **`FireAndReposition` (l'ability, 1063) n'entre pas dans `ABILITY_CLASSES`.** Le runner offline ne
  sait donc pas POSER 1110 lui-même ; il le matérialise depuis la capture (canal `decisionView`),
  ce qui suffit à tout ce qui est mesuré ici. Résidu NOMMÉ : porter l'ability exigerait
  `UseActiveAbility` + `ResetMovement` + `AddEffect` en DSL, plus son `TARGETING_OPTIONS` et son
  `ABILITY_ATTACK_TYPE`.
* ~~**`IsTurnOf` générique agrège par `any`, le natif par `all`**~~ — **FERMÉ (2026-08-01)**,
  `case-366-r1-turnof-all.md` : mirror `all(...)` posé, **set vide → VRAI**. Sans effet ici (`Owner`
  est un singleton) — et sans effet nulle part au natif : sur les **17** opérandes du build, aucun ne
  peut rendre 2 entités-unités (recensement exhaustif par xrefs du slot de cache de classe, qui
  révèle **deux allocations INLINÉES** invisibles des xrefs de la factory).
* **Aucune mesure de l'EXPIRATION** : `remaining` 2 → 1 est observé, la fin de vie ne l'est pas.
* **La face DÉCISION n'est pas confrontée séparément** : l'effet n'apparaît dans `decisionView`
  qu'au tour ennemi, où le playbook ne calcule pas les attaques de l'adversaire. Le câblage
  `scene.is_turn_of` / `att_ctx["is_turn_of_owner"]` y est posé et cohérent avec le COMBAT (même
  clé, même sémantique), mais il n'est **exercé** que par la voie COMBAT.

## 8. Artefacts

| quoi | où |
|---|---|
| classe d'effet | `scripts/python/engine/entities/effects/loki/damage_reduction.py` (`FireAndRepositionReduceDmgEffect`) |
| registre | `scripts/python/engine/entities/effects/factory.py` + `effects/loki/__init__.py` |
| foyer du gate de tour | `scripts/python/engine/entities/effects/base.py` (`is_turn_of_owner`) |
| fil COMBAT | `scripts/python/engine/runner/damage_model.py` (`_owner_turn_flag`, `defender_modifiers`) |
| fil DÉCISION | `scripts/python/engine/playbook/scene.py` (`Scene.is_turn_of`, `from_state`), `playbook/prediction/_shared.py` |
| niveau d'ability ACTIVE | `scripts/python/engine/entities/effects_state.py` (`seed` : le REPLI porteur tire le triple d'`ability_state_by_unit`), `playbook/scene.py` (`_seed_condition_gated_owner_effects`) |
| montage live | `scripts/python/probe_366_r1_fire_and_reposition.py` |
| gardes | `scripts/python/tests/engine/runner/test_fire_and_reposition_reduce_dmg_live.py` (8 : 4 axes × 2 couples) |
