# #1006 — Reliques AELDARI : `Maugetar` (1498) et `PhoenixGem` (1458)

Deux abilities de relique, deux porteurs du meme roster (`eldarMauganRa`, `eldarAutarch`), donc UN
seul harnais. Toutes deux sont des `TriggeredAbilityType` : elles n'entrent pas dans
`ABILITY_CLASSES`, ne posent ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE`.

## 1. L'enum : `Maugetar` EST un `TriggeredAbilityType` 1498 (l'inversion de voie ne tient pas)

`docs/rl/combat-ability-coverage.md` la listait parmi les no-op ACTIVES a id `?`, parce qu'elle
apparait dans les `activeAbilities` d'un npc. La mesure tranche par le NOM, pas par la voie :

| enum | membre 1498 | membre 1458 |
|---|---|---|
| `IdunBattle.Entities.Enum.TriggeredAbilityType` | **`Maugetar`** | **`PhoenixGem`** |
| `IdunBattle.Entities.Enum.EffectType` | `ExemplarOfTheMontka` | `RelicBoltPistol_ExtraCritDamage` |

Confirmation structurelle : les trois classes natives vivent sous
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.*` et derivent de
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` (`frida/classes.tsv`). Aucune classe
`...Abilities.Active.Loki.Maugetar*` n'existe.

Les effets qu'elles posent, eux, sont bien des `EffectType` : `1497 Maugetar_HasNotMoved` et
`1451 PhoenixGem_CanRevive` — deux ordinaux qui, dans `TriggeredAbilityType`, nomment
`HunterOfSouls` et `WisdomOfTheAncients`. L'ordinal ne discrimine dans aucun sens.

## 2. `Maugetar` — RE (build `rnca9r7q6c`)

Item `R_Crit_Maugetar` (`isUniqueRelic`), `allowedUnits = ['eldarMauganRa']`.
Gameconfig : `profile = DirectDamage{PiercingRatio: 100}`, `nrOfHits = 1`,
`dmg 1765-2350 (lvl1) -> 2622-3492 (lvl10)`.

> « During his turn, if Maugan Ra has not moved, he can move after attacking and his attacks that
> contain a Crit deal an additional 1x 2622-3492 Direct Damage. When Overwatching, Crits deal this
> additional hit if he has not moved in his last turn. »

TROIS artefacts natifs pour l'id 1498 (patron `DaemonfleshPlate` : deux classes d'ability, une cle) :

**(a) `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Maugetar_AddEffectAbility`**

    CreateTrigger    = DSLTriggers$$On(0x12 = TurnStart_EffectActivation, ownerNeedsToBeAlive: true)
                     & <DSLTriggers+0x28>                                    # IsTurnOf(Owner)
    CreateBehaviour  = DSLBehaviors$$AddEffect(0x5d9 = 1497 Maugetar_HasNotMoved,
                                               BaseTriggeredAbility$$get_AbilityStateReference,
                                               <DSLSelectors+0x30> = Owner, null)

**(b) `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Maugetar_ResetMovementAbility`**

    CreateTrigger    = DSLTriggers$$On(0xe = UnitPostAbility, ownerNeedsToBeAlive: true)
                     & DSLTriggers$$get_OwnerIsCaster
    CreateBehaviour  = DSLBehaviors$$If(
                          DSLTriggers$$HasEffect(Owner, 0x5d9 = 1497, onlyActive: false,
                                                 targetType: 6 = EffectTargetType.Both),
                          DSLBehaviors$$ResetMovement(Owner), null)

⚠ Son `CreateTrigger` est **INVISIBLE des tables** : le corps est fondu par l'ICF avec celui de
`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnance_RemoveCritChance$$CreateTrigger`.
Appartenance etablie slot a slot dans le bloc `methodPointers` du PE
(`probe_8889_methodptr_vtable.py --window 6 1812a09a0`) : le motif du bloc est
`[CreateTrigger, CreateBehaviour, <corps trivial>]` par classe, verifie sur les quatre voisins
nommes (`MastersOfManoeuvre`, `MischiefMakers`, `ModifiedExoarmour`, `Maugetar_AddEffect`).

`IdunBattle.Entities.Behaviours.ResetMovementBehavior$$Execute` retire quatre `UnitFlag` a la cible :
`ArrivedAtFinalTile` (1), `Moved` (0), `TurnTerminated` (27), `TurnFinished` (3) — et n'emet son
message d'etat que si le dernier etait pose.

**(c) `IdunBattle.Entities.Effects.Loki.Maugetar_HasNotMovedEffect`** (`EffectType` 1497)

    CreateRemoveEffectTrigger = DSLTriggers$$On(0x1f = PreUnitMove, ownerNeedsToBeAlive: true)
                              & DSLTriggers$$get_OwnerIsActor
    CreateAdditionalHits      = EffectAdditionalHits$$Create(
          trigger        = get_OwnerIsCaster & DSLTriggers$$AttackDamageIsCritical,
          damageFormula  = BaseEffect$$GetMinMaxDamage(false),      # min
          maxDamage      = BaseEffect$$GetMinMaxDamage(true),       # max
          hitsFormula    = DSLFormulas$$ConfigConst(0x2f = AbilityConstantType.nrOfHits),
          damageProfileType = AbilityConfiguration$$GetDamageProfile(cfg), defaut 0xf,
          additionalHitsType = null, forceOverkill = false)

Le `.ctor` de l'effet est nu (`BaseEffect$$.ctor(this, AbilityOrEffect(Maugetar), true)`).

## 3. `PhoenixGem` — RE (build `rnca9r7q6c`)

Item `R_Booster_Block_PhoenixGem` (`isUniqueRelic`), `allowedUnits = ['eldarAutarch']`.

> « The first time each battle that Aethana is defeated, she is instead revived with a maximum of
> 5817 Health remaining, even if Overkilled. »

**(a) `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_InitAbility`**
— derive d'`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`, dont :

    CreateTrigger   = DSLTriggers$$OnOwnerSpecificAbilityInit(<abilityId> = 1458)
    CreateBehaviour = DSLBehaviors$$If(CreateCondition,                     # <DSLTriggers+0x70> =
                        DSLBehaviors$$AddEffect(GetEffectType(),            #   YesTrigger constant
                          DSLSelectors$$AbilityState(Owner, AbilityType(1458)),
                          Owner, Owner, null), null)

`PhoenixGem_InitAbility$$GetEffectType` rend `0x5ab` = **1451 `PhoenixGem_CanRevive`** (litteral lu).
C'est donc le canal `ABILITY_INIT_OWNER_EFFECTS`, pas un trigger d'evenement.

**(b) `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility`**

    CreateTrigger   = DSLTriggers$$OnPreDeath(ownerNeedsToBeAlive: true, null)
                    & DSLTriggers$$get_OwnerIsTarget
                    & DSLTriggers$$HasEffect(Owner, 0x5ab = 1451, onlyActive: false,
                                             targetType: 6 = Both)
    CreateBehaviour = DSLBehaviors$$Revive(
          caster    = Owner,      targets = Owner,
          hp        = DSLFormulas$$Direct(AbilityConfiguration$$GetVariableForLevel(
                          0x1d = AbilityVariableType.hp, abilityState, 0)),
          healType  = 2 = HealType.Any,
          ability   = AbilityOrEffect(abilityState),
          targetsTile = null,
          priority  = -1000)                                     # 0xfffffc18

**(c) `IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect`** (`EffectType` 1451)
— `CreateHandleTriggerAbilitiesInternal` inscrit DEUX triggers d'effet, tous deux
`RemoveEffect(<DSLSelectors+0x38>)` (l'effet lui-meme) :

    BaseEffect$$On(0x2d = UnitRevived)      & get_OwnerIsTarget & CurrentAbilityIs(PhoenixGem)
    BaseEffect$$On(0x2e = UnitResurrected)  & get_OwnerIsTarget

C'est ce qui realise le « the first time each battle » : l'effet est CONSOMME au revive.

## 4. La MESURE qui retourne deux premisses ecrites

`probe_1006_reliques_aeldari.py`, sur deux runners `rl_duel build --equip-relic` (niveaux 1 et 10) :

| ce qui etait ECRIT | ce qui est MESURE |
|---|---|
| « `PhoenixGem` n'est pas posable via `rl_duel build` » (`test_revive_retrofit_offline_live.py`) | les DEUX effets (1451, 1497) sont POSES par le natif et publies par `decisionView.effects` |
| `#884-r2` : `Maugetar_HasNotMovedEffect` -> `BLOCAGE: porteur` | `eldarMauganRa` est au pool rank 17 ; le montage #237 suffit |

Les deux dataient d'avant le montage `--equip-relic` (#237). Elles n'etaient pas seulement
documentaires : **personne ne pouvant monter la relique, personne n'avait vu le bug de niveau.**

**LE NIVEAU NE SE LIT PAS SUR L'INSTANCE D'EFFET.** L'instance captee publie `ability_level = 50`
(l'etat PASSIF du porteur sur tout runner normalise) que la relique soit au niveau 1 ou 10 :

| relique | `ctx.tertiary_ability_level` | `Maugetar` [min, max] | `PhoenixGem` hp |
|---|---|---|---|
| niveau 1 (regime SEPARANT) | 1 | **[1765, 2350]** | **3915** |
| niveau 10 | 10 | [2622, 3492] | 5817 |
| lecture par l'INSTANCE (les deux runners) | 50 -> clampe au 10e palier | [2622, 3492] | 5817 |

Soit **+49 %** sur les deux magnitudes, en silence. C'est le residu que #357 avait ferme pour
`DawnBlade` et qui restait ouvert ici. Le foyer UNIQUE est `triggered_ability_state` (#357) ; il
exige le canal ambiant `unitAbilityStates` (`snapshot.bind_live_rpc`, pose par `tests/conftest.py`).

**Le gate `AttackDamageIsCritical` est de PORTEE ATTAQUE.** `IdunBattle.Operations.
AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` remplit l'`AbilityEntities`
qu'il passe a `GetAdditionalHitsFromEffectsInternal` avec `currentAttack+0x50` (le `HitDamage`) PUIS
`hitGroup+0x3d` -- l'etat du groupe de coups d'ARME qui vient d'etre resolu. Ce n'est donc pas un
tirage per-coup, ce que dit aussi l'i2 (« his attacks that CONTAIN a Crit »). Cote port, cet etat
sort de `r["crits"]` de la phase d'arme et entre au ctx sous `attack_had_critical` -- tri-etat :
cle absente = NON MESUREE -> aucun groupe.

## 5. Ce que ce cas n'etablit PAS

* **`combat-ability-coverage.md` classe toujours `Maugetar` en active no-op** (`| ? | Maugetar |
  DAMAGE(DirectDamage) | 1 | N |`) : l'audit enumere les `activeAbilities` du gameconfig, ou la
  relique figure par un npc. L'id `?` EST le symptome de l'inversion de voie. Residu `#1006-r1`.
* **`audit_kit_coverage` ne compte pas `PhoenixGem` comme portee** : ses six canaux sont indexes par
  NOM d'ability, et l'ability de revive est inscrite par son EFFET (`EFFECT_TRIGGERS[1451]`). Meme
  forme que le trou `TalonOfHorus`. `Maugetar`, elle, entre bien (11 -> 12 reliques portees). Residu
  `#1006-r2`.
* **`ABILITY_INIT_OWNER_EFFECTS["PhoenixGem"]` n'est PAS pose**, et c'est delibere :
  `_seed_ability_owner_effects` derive sa liste d'abilities du gameconfig
  (`activeAbilities` + `passiveAbilities`), jamais de `UnitContext.tertiary_ability` -- l'entree
  serait INERTE. Sans consequence sur un etat CAPTURE (le natif pose l'effet, le port le lit), mais
  un etat construit hors capture n'aura aucun marqueur. Residu `#1006-r3`.
* **Le tir d'OVERWATCH** (« when Overwatching, Crits deal this additional hit if he has not moved in
  his last turn ») n'a **aucun etage natif propre** : c'est le MEME effet 1497, qui survit au tour
  adverse parce que seul un deplacement DU PORTEUR le retire. Rien de specifique n'est porte, et
  c'est LU -- pas suppose. Non confronte live sur ce vecteur.
* **`ownerNeedsToBeAlive = true`** des trois `On(...)` n'est pas re-teste : le port n'inscrit de
  triggers que pour des entites vivantes sur ces vecteurs.
* **La publication de stream** de `ResetMovementBehavior` (`Publish(<0xc>, e, {<0x70>: 0})`) reste
  non portee -- deja documentee sur la feuille.

## 6. Validation

* **17 tests live** (`tests/engine/runner/test_1006_reliques_aeldari_live.py`), montage
  `--equip-relic "...:Maugetar:1"` + `"...:PhoenixGem:1"` sur `MC1_67`. Le niveau **1** est choisi
  pour que les deux modeles de magnitude DIVERGENT : au niveau 10 ils coincident, donc un montage a
  10 aurait rendu VERT le port faux.
* **8 mutants sur 8 sont VUS** : entree `EFFECT_CLASSES` retiree (4 rouges), gate crit supprime,
  niveau lu sur l'instance (2 rouges), `RELIC_ABILITY_TRIGGERS` retire (2), `EFFECT_TRIGGERS[1497]`
  retire (4), `_level` de `PhoenixGem` revenu a l'instance, gate `OwnerIsCaster` supprime,
  `IsTurnOf(Owner)` supprime.
* **Cliquets de registre** : `probe_229` et `probe_421` etaient VERTS sur `origin/master` et ROUGES
  apres l'entree au registre -- le rail natif du trigger 1497 les referme. `probe_486r15` est rouge
  des deux cotes sur un AUTRE fichier (preexistant). `probe_437r1r1r1` et `probe_313` : rouges /
  `rc=6` des deux cotes, preexistants.
* **DEUX ROUGES DE `master` REPARES** dans le canal que cette tranche touche :
  `test_additional_hits_roll_order_live.py` (5 failed) et `test_additional_hits_rounding_live.py`
  (3 failed) tombaient en `TypeError` -- les quatre substitutions d'`execute_additional_hits`
  n'avaient pas suivi l'ajout de `damaging_done0` (#963-r2), ce que
  `test_additional_hits_variant_signatures_offline.py` disait deja. Verifie sur un worktree temoin
  detache sur `origin/master` : memes 8 echecs, meme trace.
* **Non-regression** : `test_additional_hits_{amount_bounds,scalar_bounds,after_hit_maybe,roll_order,
  rounding}_live`, `test_884_average_display_live`, `test_revive_retrofit_offline_live`,
  `test_357_relic_rail_live`, `test_dawn_blade_repair`, `test_runner_attack_live` -- tous verts.
