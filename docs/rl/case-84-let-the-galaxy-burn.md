# case-84 — LetTheGalaxyBurn, volet 1 : le coup additionnel (trait 1058 → triggered 1482 → effet 1477)

Chemin-effet Black Legion, même patron que #73 (Terrifying) et #74 (SuppressiveFire) : un **trait**
accorde une **ability déclenchée**, qui arme un **effet** porteur du canal de combat.

> ⚠ **Homonymie** — `ActiveAbilityType.Waaagh` vaut AUSSI **1058**. Les espaces `UnitTrait`,
> `TriggeredAbilityType`, `ActiveAbilityType` et `EffectType` sont indépendants. Ici :
> **1058 = UnitTrait**, **1482 = TriggeredAbilityType**, **1477 = EffectType** (l'owner-effect),
> **1476 = EffectType `DespoiledGround`** (le volet 2, tile-effect).

## 1. Artefacts natifs (décompile ghidra, build `gqfc5mff6c`)

| Symbole | VA |
|---|---|
| `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$.ctor` | `0x180f55080` |
| `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` | `0x180f54e30` |
| `…Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` | `0x1811076f0` |
| `…Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour` | `0x1811075c0` |
| `…Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$TargetHasTileEffect` | `0x181107810` |
| `…Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$.cctor` | `0x181107840` |
| `…Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` | `0x1811078a0` |
| `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` | `0x180f405b0` |
| `IdunBattleLogic.Entities.DSLFactory$$HasTileStatusEffect` | `0x180df13f0` |
| `IdunBattleLogic.Entities.DSLFactory$$IsPersistentData` | `0x180df4bb0` |
| `IdunBattle.Entities.Triggers.GetPersistentDataFormula$$Calculate` | `0x180f9cb10` |
| `IdunBattle.Entities.Components.PersistentDataComponent$$ClearPersistentData` | `0x180fa6960` |

`LetTheGalaxyBurnEffect..ctor @180f55080` = `BaseEffect(AbilityOrEffect(0x5ca = 1482), 1, 0)` →
**owner-effect auto-porté** (aucune classe `Ability` ne le pose ; même patron que
`InfernalPacts_AdditionalHitsEffect` @180f527a0). Confirmé live : `decisionView.effects` de
`blackObliterator`/`blackTerminator` contient `LetTheGalaxyBurn` dès le premier pas.

### 1.1 Le canal — `CreateAdditionalHits @180f54e30`

```
EffectAdditionalHits.Create(
    condition = get_OwnerIsCaster
                & ( TargetHasTileEffect                       # @181107810 = HasTileStatusEffect(Targets@0x190)
                  | IsPersistentData(0x5ca, Self@0x148, Get(<statique .cctor @181107840>)) ),
    dmg       = FirstHitInCurrentAttackDamageRange,           # param_3
    param_4   = 0,
    profil    = -1,                                            # Nullable<DamageProfileType> NULL
    count     = <noeud NULL>,                                  # param_6 = 0
    param_7   = 0,
    display   = FirstHitInCurrentAttackDamageRange,            # param_8
    cap       = <NULL> )                                       # param_9 = 0
```

**Comparaison discriminante avec `MasterAnnihilator_AdditionalHitEffect.CreateAdditionalHits
@180f58d50`** (le canal jumeau, déjà porté) : même `FirstHitInCurrentAttackDamageRange`, même
profil `-1`, mais MasterAnnihilator passe `count = ConfigConst(0x2f = nrOfHits)` et
`cap = ConfigVar(0xd = maxDmg)` là où LetTheGalaxyBurn passe **NULL** aux deux. Le `count` NULL →
**1 coup** (mesuré : 4 → 5, jamais 4 → 6).

⇒ ce n'est **pas** le canal hétérogène de FleshmetalGuns/#65 (`additional_hit_groups`, dégât et profil
propres) mais le canal `create_effect_hits_bonus_for_attack` : **+1 coup d'ARME ordinaire**, côté
**ATTAQUANT** (`OwnerIsCaster`) au lieu du côté défenseur de MasterAnnihilator (`OwnerIsTarget`).

### 1.2 L'armement — `CreateTrigger @1811076f0` / `CreateBehaviour @1811075c0`

```
CreateTrigger   : On(5 = PreAttack) & get_OwnerIsCaster
                                    & Maybe( ConfigConst(0x2a, config) )
                                    & !HasTileStatusEffect( Targets@0x190 )
CreateBehaviour : SetPersistentData( AbilityOrEffect(0x5ca), Self@0x148,
                                     Get(<statique>), Direct(1)@0xc0 )
```

`ConfigConst 0x2a` = le slot **chance** générique (même slot que le 30 % de
`GetStuckInAbility.GetBonusHitChance @180f83460`). L'ability `LetTheGalaxyBurn` n'existant pas dans
`units.abilities`, ce slot est seedé depuis les vars de trait (même mécanique que
Camouflage/Diminutive/Parry) → `traitVariables.LetTheGalaxyBurnChancePct` = **33**.

### 1.3 Le désarmement — `LetTheGalaxyBurn_ResetAbility.CreateBehaviour @1811078a0`

```
  If( IsPersistentData(0x5ca, Self@0x148, Get(<statique>)) & AttackUsedAttackDamage,
      Foreach( Targets@0x190,
               If( !HasTileStatusEffect(Current@0x180),
                   AddEffect(0x5c4 = 1476 DespoiledGround, AbilityStateReference,
                             source = Self@0x148, cible = Current@0x180, options ZERO) ) ) )
+ ClearPersistentData( AbilityOrEffect(0x5ca), Self@0x148, Get(<statique>) )
```

Le `ClearPersistentData` est **hors du `If`** → inconditionnel. Le flag est donc **intra-attaque**.
Le volet `AddEffect(1476)` = **volet 2** (non porté, cf. §5).

### 1.4 Les deux branches du gate sont EXCLUSIVES

Le trigger de pose exige `!HasTileStatusEffect(cible)`, tandis que le gate du coup accepte
`TargetHasTileEffect | IsPersistentData`. Donc :

| Situation de la CIBLE | pose du flag | coup additionnel |
|---|---|---|
| tuile **sans** status-effect | roll 33 % | seulement si le roll passe |
| tuile **avec** status-effect | **jamais** | **toujours** (100 %) |

`HasTileStatusEffect` est **générique** : n'importe quel status-effect de la tuile, pas un type précis.

## 2. Ground truth live

`blackTerminator` (« Angrax ») vs `bloodSanguinary`, board `MC1_67`, attaque normale melee
(base d'arme = 4 coups). Le tile-effect de la branche B apparaît **tout seul** : c'est le volet 2 du
même kit qui pose `DespoiledGround` sur la tuile de la cible quand le flag était armé.

| Branche | n | Résultat |
|---|---|---|
| A — cible sur tuile **sans** status-effect | 73 | 25 attaques à 5 coups (48 à 4) = **34.2 %** (config 33 %) |
| B — cible sur tuile **avec** status-effect | 23 | **23 / 23** à 5 coups (100 %) |

Aucune attaque à 6 coups → `count` NULL vaut bien **1**.
Le +1 est parfaitement corrélé à l'apparition de `DespoiledGround` sur la tuile de la cible.

Corrobore le confound déjà documenté sur `test_bringer_of_despair_live.py` (Angrax live 5 = 4 + 1).

Reproduction : `scripts/python/probe_84_ltgb.py` (une session) et
`scripts/python/probe_84_ltgb_chance.py` (accumulation multi-runners).

## 3. Port

| Face | Fichier | Contenu |
|---|---|---|
| effet / canal | `engine/entities/effects/loki/hits.py` | `LetTheGalaxyBurnEffect.create_effect_hits_bonus_for_attack` + `LET_THE_GALAXY_BURN_PERSISTENT_KEY` |
| registre | `engine/entities/effects/factory.py` | `"LetTheGalaxyBurn" → LetTheGalaxyBurnEffect` |
| behaviours | `engine/runner/operations/triggers/loki/let_the_galaxy_burn.py` | `LetTheGalaxyBurnArmAbility` (On 5) + `LetTheGalaxyBurnResetAbility` (On 9) |
| registre triggers | `engine/runner/operations/triggers/dispatch.py` | `TRAIT_TRIGGERS["LetTheGalaxyBurn"]` + **nouveau vecteur `pre_attack_triggers` (`On(PreAttack=5)`)** |
| état | `engine/runner/components.py` | `PersistentDataComponent` + `persistent_data_keys` |
| threading | `engine/services/attack_hits_formula.py` | params `tile_effects_by_pos` / `attacker_persistent_data` → `hits_bonus_from_effects(att_ctx=…)` |
| façade combat | `engine/runner/operations/damage_ops.py` | émission `pre_attack_triggers` **avant** la formule + `tile_status_effects_by_pos` / `persistent_data_keys` |
| façade prédiction | `engine/playbook/prediction/normal_attack.py` | `tile_effects_by_pos=scene.tile_effects_by_pos` |
| lecture tuile | `engine/runner/damage_model.py` | `tile_status_effects_by_pos` (effets **dynamiques** portés par l'entité-tuile) |

**Le coût réel était un threading**, pas une formule : le canal `hits` ne recevait aucun contexte de
la CIBLE. `attack_hits_with_modifiers` construit désormais un `att_ctx` = son `board`
(`{att_id, tgt_id, attack_pos, t_pos, …}`) **+** `tile_effects_by_pos` **+** `persistent_data`, passé à
`hits_bonus_from_effects`. Les DEUX façades le peuplent, avec la même sémantique de tuile.

**Nouveau vecteur `On(PreAttack=5)`** : le port ne l'émettait pas (SuppressiveFire avait été routé sur
`On(38)` faute de timing critique). Ici le timing est **structurel** : le behaviour arme un flag que le
canal de coups de la MÊME attaque relit ; router après coup serait un no-op silencieux. Vérifié :
aucun autre trigger porté n'écoute l'event 5 → émettre ce vecteur ne réveille rien d'autre, et le seul
coût RNG (`Maybe`) ne se paie que pour les 5 porteurs.

**Frontière DSL/impératif** : trigger + behaviour sont des prédicats/feuilles collapsés impérativement
dans `matches`/`execute_behaviour` (doctrine des triggers, précédent SuppressiveFire #74) ; le canal de
l'effet reste un `create_effect_*` pur, et l'état persistant vit dans un composant ECS mirroré
(`PersistentDataComponent`), jamais fusionné avec le behaviour.

## 4. Confrontabilité

5 porteurs, **tous HERO** et présents dans `rl_duel.py --list-pool` : `blackAbaddon`, `blackHaarken`,
`blackObliterator`, `blackPossession`, `blackTerminator`. Item pleinement validable live.

## 5. Résidus (explicites)

1. **Volet 2 non porté** : `AddEffect(0x5c4 = 1476 DespoiledGround)` sur les tuiles des cibles.
   ⚠ **Ses deux PRÉREQUIS sont levés depuis #85** (`case-85-despoiled-ground.md`) : la classe d'effet
   1476 ET l'effet `1478 DespoiledGround_ExtraDamagePct` sont portés, et le vecteur
   `On(0x10 = DamageDealt)` existe. Ce qui reste est le seul câblage de ce `AddEffect`-là.
   Conséquence offline **tant qu'il n'est pas câblé** : la branche B ne s'auto-alimente pas PAR CE
   KIT (elle l'est en revanche par `FleshMetalGuns_TileEffectAbility` depuis #85, et par tout autre
   tile-effect Fire / Ice / Contaminated, ainsi que par le contexte LIVE threadé).
   ⚠ **Piège de mesure démontré (#85)** : `blackObliterator` porte les DEUX poseurs de 1476
   (`LetTheGalaxyBurn` en trait ET `FleshmetalGuns` en passif) — la SOURCE de l'instance observée
   live change selon celui qui a gagné la course (la TUILE pour FleshMetalGuns, l'unité pour LTGB).
   Ne jamais attribuer une pose de 1476 à un kit sur la seule base de sa présence.
2. **Attaques d'ABILITY** : le gate natif est `OwnerIsCaster` sans `IsNormalAttack`, et le ground truth
   Angrax (BringerOfDespair = ability, 5 = 4 + 1) montre que le +1 s'y applique aussi. Le port ne câble
   le canal que sur l'attaque NORMALE (`AttackDamageOperation.execute`) : `execute_ability_attack`
   reçoit un `hits` fixe issu de la config d'ability et ne traverse pas
   `attack_hits_with_modifiers`. Y brancher le canal toucherait aussi `FightingRetreat_HitReduction`
   (trigger `OwnerIsCaster` seul, @180f495d0) → chantier séparé, hors périmètre du volet 1.
3. **`CreateTrigger` du Reset non lu** : corps dédupliqué (absent de la table des symboles). Le port
   route le clear sur `On(Attack=9)` — le seul vecteur fin-d'attaque générique (normale + ability) du
   port, contraint par le `AttackUsedAttackDamage` du behaviour. **Hypothèse assumée.**
4. **Ordre de consommation RNG** : le natif place `Maybe` **avant** `!HasTileStatusEffect` dans la
   conjonction ; le port évalue les gates déterministes d'abord et ne roll que si la pose est possible.
   Non confronté bit-exact (les porteurs ne le sont de toute façon pas, cf. résidu 2).
5. ~~**Covers de terrain**~~ **CONFRONTÉ LIVE — le port est correct** (§7 G3) :
   `tile_status_effects_by_pos` n'inclut délibérément pas `terrain_tile_effects` (DryBush →
   LightCover), qui sont posés sur les **unités** de la tuile et non sur la tuile. Vérifié :
   16 attaques d'affilée sur une cible **parquée en DryBush** donnent 10/16 avec le +1 — soit
   exactement l'oscillation du roll, pas les 100 % qu'imposerait un `TargetHasTileEffect` vrai. Le
   gate ne voit donc que les status-effects **dynamiques** portés par l'entité-tuile.

## 6. Tests

`scripts/python/tests/engine/runner/test_let_the_galaxy_burn_live.py` (3 tests, confrontent le natif —
la base de coups est **mesurée**, jamais codée en dur) :

1. `test_ltgb_live_gate_two_branches` — LIVE : les comptes observés ⊆ `{base, base+1}` ; branche A
   contient au moins un `base` (le roll échoue) ; branche B = `base+1` **partout**.
2. `test_ltgb_offline_arm_read_and_clear` — OFFLINE (anti no-op) : même oscillation à la même
   fréquence, flag **toujours** effacé après l'attaque, + 2 counterfactuels load-bearing (effet 1477
   retiré → plus aucun `+1` ; tuile de la cible forcée à un status-effect → `+1` à 100 % **et** aucune
   pose, gate exclusif).
3. `test_ltgb_prediction_channel_is_wired` — la formule partagée rend `base+1` sur tuile à effet,
   `base` sinon, et **rien** pour un effet posé sur une AUTRE tuile.

Non-régression rejouée : `test_death_nova_live.py`, `test_lightcover_gate_live.py`,
`test_damage_roll_live.py`, `test_runner_attack_live.py`, `test_predict_live.py`,
`test_bringer_of_despair_live.py`.

## 7. Validation adversariale — généralisation (`scripts/python/probe_84_generalize.py`)

Configurations **non utilisées pour construire le port** :

| # | Variation | Résultat |
|---|---|---|
| G1 | autre carrier `blackHaarken` (arme **Piercing** melee, kit Terrifying/Flying) | base 4, branche A 5/11 avec `+1`, branche B **5/5** à `base+1` → le canal ne dépend ni du profil d'arme ni du reste du kit |
| G2 | autre board `C1_74` | idem |
| G3 | cible **parquée en DryBush** (cover hébergé par le terrain), attaquant **melee** (LightCover est gaté `!IsMeleeAttack` → aucun confond de coups) | 10/16 avec `+1` — **pas** 100 % ⇒ `HasTileStatusEffect` ne compte **pas** les covers de terrain (résidu 5 levé) |

Ce qui n'est **pas** couvert : le résidu 2 (attaques d'ABILITY), le volet 2 (pose de
`DespoiledGround` offline), la fidélité **bit-exact** du flux RNG d'un porteur (résidu 4), et les
3 autres carriers (`blackAbaddon`, `blackObliterator`, `blackPossession`) — non exercés
individuellement, le canal étant porté par l'effet et non par le kit.
