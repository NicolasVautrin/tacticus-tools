# Case #100 — Résidus AnvilShield : `ApplyStun` + `FrozenAttackerAdvantage` (le « +20 % Block » d'Arjac)

**Status : LIVRÉ et CONFRONTÉ LIVE (build `gqfc5mff6c`).** Les deux volets étaient documentés en #222
comme *dead-code garanti en l'état* : leurs prérequis (effets 1200/1201, vecteur `On(PreUnitAbility)`,
canal stat 7) n'existaient pas. Ils existent maintenant, et les deux volets sont **atteignables,
observables et validés live** — 3 tests de garde, zéro régression.

> **Ce que ça débloque** : plus de la MOITIÉ de la passive d'Arjac était morte offline. Le kit i2
> **« If Arjac is below 35% Health, or if his attacker is on a hex covered in Ice, he gains +20% Block
> chance and if he blocks a melee attack, the attacker is Stunned until the end of the attacker's next
> turn »** est désormais porté **en entier**.

---

## 1. RE — les quatre artefacts natifs (citations par SYMBOLE)

### 1.1 La POSE (init) — `AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour`
```
AddStaticStatModifierEffect(Self@0x148, 0x4b2 = 1202, statType 8 = BLOCK_DAMAGE,
                            GetVariableForLevel(0x14 = blockDmg))
+ AddStaticStatModifierEffect(Self@0x148, 0x4b0 = 1200, statType 7 = BLOCK_CHANCE,
                              GetVariableForLevel(0x15 = blockChance))
```
Trigger = corps dédupliqué `IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAddEffectAbility$$CreateTrigger`
(`return df@0xa8`), `df@0xa8` construit par `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` =
`On(0x21 = AbilityInit) & OwnerIsActor` ⇒ **owner-effects posés à l'INIT** (confirmé #222).

### 1.2 L'ActiveCondition de 1200 — la question laissée ouverte par #133, TRANCHÉE
`IdunBattle.Entities.Effects.Loki.AnvilShield_BlockChanceBelowHealthCapEffect$$CreateActiveCondition`
```
AmountIsEqualOrGreater( Direct(GetNumberConstant(0x4f)),
                        StatAmount(Self@0x148, 5 = HEALTH, 1 = CURRENT_PCT) )
```
`StatPart 1 = CURRENT_PCT` ⇒ **c'est un POURCENTAGE**, pas une valeur absolue. `GetNumberConstant(0x4f)`
= `gameconfig.ability('AnvilShield').constants['healthPct']` = **35**. L'ancienne note
« ambiguïté abs-vs-% du cap » (#133) est résolue par le décompilé, pas par une expérience.

### 1.3 `AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger` / `$$CreateBehaviour`
```
On(0x2b = PreUnitAbility) & IsNormalAttack & get_OwnerIsTarget
  & IsUnitOnTileWithEffect(caster@0x160, 0x11 = Ice)
  & !HasEffect(Self@0x148, 0x4b0, 1, 6) & !HasEffect(Self@0x148, 0x4b1, 1, 6)
->
AddStaticStatModifierEffect(Self@0x148, 0x4b1 = 1201, statType 7 = BLOCK_CHANCE,
                            GetVariableForLevel(0x15 = blockChance))
```
1201 utilise **la même stat et la même variable** que 1200 : les deux voies donnent le MÊME +20 %.

Durée : aucun override, et `0x4b1` est absent de `DefaultAmountOfRounds` ⇒ `remaining = 0` = permanent.
Ce qui le retire est son **trigger propre** :
`IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger` =
`On(0xe = UnitPostAbility) & AreEqual(target@0x178, EffectSource(thisEffect@0x150))` ⇒ le bonus ne vit
que **le temps de l'ability qui l'a déclenché**.

### 1.4 `AnvilShieldAbility_ApplyStun$$CreateTrigger` / `$$CreateBehaviour`
```
On(0x3d = UnitBlocked) & get_OwnerIsTarget & IsMeleeAttack
  & !HasTrait(caster@0x160, 0x1b = Steppable) & IsUnit(caster) & IsAlive(caster)
  & ( HasEffect(target@0x178, 0x4b0, 1, 6) | HasEffect(target@0x178, 0x4b1, 1, 6) )
->
AddEffect( 0x48a = 1162 Stunned, AbilityStateReference, source = Self@0x148, cible = caster@0x160,
           durée = If(IsTurnOf(caster), TurnsUntilEndOfCurrentPlayersNextTurn, TurnsFromRounds(1)) )
```

### 1.5 RECTIFICATION — le 4ᵉ argument de `DSLFactory$$HasEffect` est ACTIVE-ONLY, pas un `minLevel`

#222 le lisait « lvl>=1 ». Le décompilé dit autre chose :
`IdunBattleLogic.Entities.DSLFactory$$HasEffect(sel, type, p4, p5)` construit
`IdunBattle.Entities.Triggers.HasEffectTrigger(sel, type, query, p5, p4)`, dont le `ShouldTrigger`
appelle `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects(entity, query, [type], p4, p5)`.
Dans `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` :
```
if (param_4 != 0) { if (*(char *)(effect + 0x5c) == '\0') goto next; }   // saute l'effet INACTIF
if (*(int *)(effect + 0x58) == effectType) return 1;                      // +0x58 = EffectType
```
et `+0x5c` **est le flag IsActive** — prouvé par
`IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` (`if (comp+0x5c == 0) return;
comp+0x5c = 0;`). Le 5ᵉ argument `6 = 2|4` sélectionne les deux branches `owned | incoming` de
`HasOneOfEffects` (= `IsOwnerOfEffect || IsTargetOfEffect`, cf.
`IdunBattle.Entities.EntityExtensions$$HasEffect`).

**Conséquence directe** : le gate d'`ApplyStun` n'est PAS « l'effet est présent », mais « l'effet est
ACTIF ». C'est ce qui rend la mécanique cohérente : 1200 est présent en permanence sur Arjac et
n'ouvre le gate qu'en-dessous de 35 % PV.

### 1.6 Émetteurs des deux vecteurs
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` émet, dans l'ordre :
`On(0x2b = PreUnitAbility)` **tout en haut** (avant l'exécution de l'ability), puis
`On(0xb = UnitAbility)`, `On(0xc = UnitActiveAbility)`, et enfin `On(0xe = UnitPostAbility)`.
L'attaque NORMALE emprunte cette opération (elle EST une active ability, `NormalAttackType`).

---

## 2. GROUND TRUTH LIVE (`scripts/python/probe_anvil_shield_residues.py`)

| mesure | observé |
|---|---|
| Arjac 100 % PV | `blockChance = 0`, 1200 **absent** de `decisionView.effects` |
| Arjac 31.8 % puis 8.2 % PV | 1200 **présent**, `blockChance = 20` |
| attaquant sur tuile GLACÉE, Arjac **pleins PV** | **7 stuns / 15 attaques** (3 coups/attaque × 20 % de block ⇒ ~49 %/attaque : la mesure colle) |
| `Stunned` posé | `level 1`, **`remaining 3`**, `source = Arjac` + sous-effets 1165/1166/1167 |
| après l'attaque | 1201 **absent**, `blockChance` retombé à 0 ⇒ effet **transitoire** |
| attaquant HORS glace, Arjac > 35 % | **0 stun** (contrôle négatif) |

`decisionView.effects` n'expose donc **que les effets ACTIFS** — c'est le même filtre que le gate
`HasEffect(..., activeOnly=1)`, et c'est ce qui explique que 1200 soit « invisible » à pleins PV.

**`remaining 3` = `ConvertRoundsToTurns(1) = 2` + 1** ⇒
`TurnsUntilEndOfCurrentPlayersNextTurn = TurnsFromRounds(1) + 1`, ce qui est exactement la structure
du nœud natif (`IdunBattleLogic.Entities.DSLFactory$$TurnsUntilEndOfCurrentPlayersNextTurn` bâtit son
nœud sur un `TurnsFromRoundsFormula(df, .., 1)` ET un nœud constant `1`).

---

## 3. Le PORT

| brique | fichier | contenu |
|---|---|---|
| effet 1200 | `entities/effects/loki/hits.py` | `AnvilShieldBlockChanceBelowHealthCapEffect` — `is_active` = `healthPct >= hp%`, stat 7 / `blockChance` (NON rarity-scale) |
| effet 1201 | idem | `AnvilShieldFrozenAttackerAdvantageEffect` — stat 7 / `blockChance`, `applied_stat_mods` + `reverted_stats` |
| inscription | `entities/effects/factory.py` | `EFFECT_CLASSES` ×2 + `ABILITY_INIT_OWNER_EFFECTS["AnvilShield"] = [1200]` |
| gate actif | `entities/triggers.py`, `runner/abilities/behaviours/context.py` | `HasEffect(..., active_only=True)` → `ctx.has_effect(..., active_only)` évalue `BaseEffect.is_active` |
| driver | `runner/operations/refresh_effects.py` (**nouveau**) | mirror `RefreshEffectsOperation` (volet stat-modifier) : Apply/Revert de la modification selon l'`ActiveCondition` |
| vecteurs | `runner/operations/triggers/dispatch.py` | `pre_unit_ability_triggers` (`On(0x2b)`) + `unit_post_ability_triggers` (`On(0xe)`) |
| câblage | `runner/operations/damage_ops.py`, `dispatch.py`, `damage.py` | `On(0x2b)` en TÊTE de l'attaque normale (avant le block !), `On(0xe)` en clôture, refresh au chokepoint dégât |
| triggers | `runner/operations/triggers/loki/anvil_shield.py` | `AnvilShieldApplyStunAbility`, `AnvilShieldFrozenAttackerAdvantageAbility`, `AnvilShieldFrozenAdvantageExpire` |

### Deux points de conception qui méritent d'être explicites

**(a) Pourquoi 1200 est posé à l'INIT côté port.** Le seed live (`decisionView.effects`) ne contient
que les effets ACTIFS ⇒ dans tout runner démarrant Arjac à pleins PV, 1200 serait ABSENT et la branche
« below 35 % » du gate serait **morte** — exactement le no-op silencieux que ce case corrige. Il est
donc inscrit dans `ABILITY_INIT_OWNER_EFFECTS` (le poseur `_seed_ability_owner_effects` est idempotent :
si Arjac démarre sous le seuil, l'effet capté live est conservé tel quel).

**(b) Pourquoi un driver plutôt qu'un `applied_stat_mods`.** La contribution de 1200 doit ENTRER et
SORTIR du `UnitStats` au franchissement du seuil. `AddEffectOperation._apply_stat_mods` ne s'exécute
qu'à la POSE : il ne peut pas suivre une condition. Le driver `refresh_stat_modifier_effects` reproduit
`RefreshEffectsOperation` et se limite, **par construction**, aux effets qui (1) déclarent un
`get_stat_modification_stat()` et (2) ne déclarent AUCUN `applied_stat_mods` (les stat-mods « eager »
— ActOfFaith, DoctrinaImperatives, 1201 — restent gérés par `AddEffect`/`RemoveEffect`). Il réutilise
la **clé de source du seed** (`statmod_source_key`, factorisée) et `ValueModification.Modify` est un
**replace par-source** ⇒ ré-appliquer la même valeur est un no-op EXACT ; seule la bascule
`is_active() == False` change quelque chose. Blast radius = 0 pour tout effet sans ActiveCondition.

### Granularité / résidus honnêtes
- `On(0x2b)`/`On(0xe)` sont émis sur la voie d'attaque **NORMALE** uniquement (c'est ce qu'exige le
  gate `IsNormalAttack` de FrozenAttackerAdvantage). Les attaques d'ABILITY passent aussi par
  `ActiveAbilityOperation` côté natif : aucun consommateur porté ne le demande aujourd'hui.
- `On(0xb)`/`On(0xc)` (les deux événements intermédiaires de la même opération) ne sont pas émis :
  aucun trigger porté ne les écoute.
- `IsMeleeAttack` est résolu **par POSITION** (`_is_ranged_position`, mirror
  `IdunBattleLogic.Entities.DSLFactory$$IsRangedAttack`) et non par le type de timeline de l'ability —
  même convention que SuppressiveFire.
- `On(UnitBlocked)` reste agrégé **per-attaque** côté port (résidu #222 inchangé) : la pose de Stunned
  est idempotente, donc observationnellement équivalente.

---

## 4. Validation

### 4.1 Tests de garde — `tests/engine/runner/test_anvil_shield_stun_live.py` (3, tous verts)

| test | oracle natif | ce qu'il garderait |
|---|---|---|
| `test_anvil_shield_stuns_blocked_melee_attacker_on_ice_live` | 2 coups, **seule** variable = « l'attaquant est-il sur la glace » (block CRAFTÉ à 100 % via `--block-target 100,500`, Arjac à pleins PV ⇒ 1200 inactif) : coup #1 hors glace = **pas de Stun**, coup #2 depuis la glace = **Stunned** (source Arjac, `remaining = ConvertRoundsToTurns(1)+1`), 1201 absent après | vecteur `On(0x2b)` muet ; gate `activeOnly` traité comme minLevel ; `On(0xe)` non consommé (le +20 % deviendrait permanent) ; durée non convertie |
| `test_anvil_shield_stun_via_health_cap_branch_and_gates_live` | Arjac descendu sous 35 % ⇒ Stun par la branche **1200** (et 1201 NON posé : son gate `!HasEffect(1200)`) ; + 4 contrôles négatifs offline (`OwnerIsTarget`, `IsMeleeAttack`, `IsAlive(caster)`, `HasEffect(activeOnly)` une fois soigné) | n'importe lequel des prédicats du `CreateTrigger` supprimé ou inversé |
| `test_anvil_shield_block_chance_cap_activates_below_health_pct_live` | `blockChance` live 0 → **20** au franchissement du seuil, 1200 absent puis présent ; offline : effet posé mais INERTE au-dessus du seuil, driver qui l'ajoute puis le **retire** au « soin » | `ActiveCondition` en absolu au lieu de % ; `blockChance` scalé par erreur ; contribution stat 7 qui fuit ou ne revient jamais |

Le CONTRÔLE NÉGATIF du 1ᵉʳ test est obtenu **naturellement** : en arrivant au contact, l'overwatch
d'Arjac déclenche une riposte mêlée que le block à 100 % arrête ⇒ `ApplyIce` glace la tuile de
l'attaquant — un coup mêlée BLOQUÉ, gate FAUX, **aucun Stun**. C'est le discriminant exact.

### 4.2 Zéro-régression
- Garde agreement `engine_agreement_stages.py --build --seeds 31337 --steps 40` :
  **PREDICTION 21/23 (91 %, les 2 mêmes `mismatch-logic` `healthDmgMin/Max` pré-existants),
  UTILITÉ 23/23, ability 27/27** — identique au baseline case-222/case-204.
- Tests ciblés rejoués, tous verts (aucun SKIPPED de cap) : `test_lot_pose_live` (les 4 maillons #222,
  dont AnvilShield ApplyIce), `test_effect_stun_live`, `test_beast_slayer_block_live`,
  `test_noblocking_bypass_live`, `test_damage_block_live`, `test_damage_roll_live`,
  `test_runner_attack_live`, `test_doctrina_imperatives_live`,
  `test_act_of_faith_crit_resets_both_paths`, `test_act_of_faith_reset_live`,
  `test_suppressive_fire_live`, `test_lord_of_tempests_ice_live`, `test_turnflow_live`.

### 4.3 NON couvert (honnête)
- **Branche `TurnsFromRounds(1)` de la durée du Stun** (`If(IsTurnOf(caster), …)` FAUX) : elle exige
  une attaque portée HORS du tour de l'attaquant (overwatch, contre-attaque). Portée, jamais exercée.
- **`On(0x2b)`/`On(0xe)` sur la voie ABILITY** : non émis (cf. résidus §3).
- **1201 sur une attaque d'ABILITY** : le gate natif `IsNormalAttack` l'exclut de toute façon, mais la
  voie n'est pas exercée.
- **Cumul 1200 + 1201** : impossible par construction (le gate de 1201 exige `!HasEffect(1200)`) —
  vérifié live dans le test 2, jamais dans une configuration adverse.
- **Le `remaining` du Stun avec ≠ 2 joueurs non-Environment** : le facteur vient de
  `ConvertRoundsToTurns` (déjà validé #98), non re-mesuré ici.
