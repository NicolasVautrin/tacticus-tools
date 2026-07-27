# case-133 — deux passifs GAP-ABSENT portés : `DestroyTheWitch` et `MartialSuperiority`

Issus de la file de `docs/rl/passive-ability-coverage.md` (items 8 et 24 : les deux étaient
**GAP-ABSENT**, aucune trace nulle part dans le moteur, pas même en prose). Canal canonique des
passifs = `TriggeredAbilityType`, donc `ABILITY_TRIGGERS` / `EFFECT_CLASSES`, jamais
`ABILITY_CLASSES` (keyé `ActiveAbilityType`).

| item | porteur | id natif | canal de port | verdict |
|---|---|---|---|---|
| `DestroyTheWitch` | `templHelbrecht` (HERO, pool rank 17) | `TriggeredAbilityType` **1091** | **E** effet (2 classes dans `EFFECT_CLASSES`) | **porté + validé live** (4 scénarios) |
| `MartialSuperiority` | `templChampion` (HERO, pool rank 17) | `TriggeredAbilityType` **1092** | **T** trigger (`ABILITY_TRIGGERS`) | **porté + validé live** (3 scénarios) |

Les deux symboles annoncés par l'audit ont été **confirmés en ghidra** avant tout port
(`search_symbols_by_name`) : ce sont bien les mécaniques que leur nom suggère, et l'enum
d'appartenance est qualifié (`TriggeredAbilityType` 1091/1092 ≠ `ActiveAbilityType` 1091/1092 =
`HolyDuel_Taunt` / `DarkTalonStrike` — le piège d'homonymie d'id est réel ici).

---

## 1. Le fait le moins intuitif du cas : un corps natif **FONDU** que les DEUX tables mislabellent

`DestroyTheWitch_ExtraMoveEffect` et `DestroyTheWitch_ExtraDamageEffect` ont **le même corps de
`CreateActiveCondition`**. IL2CPP **fond les corps de méthode identiques** : une seule adresse pour
N méthodes. Or les deux tables de symboles du dépôt sont **dédupliquées par adresse** (mesure :
121 501 lignes pour 121 501 RVA distinctes côté frida) — chacune ne garde donc qu'**un** représentant
du groupe fondu, et **elles n'ont pas gardé le même** :

| table | nom rendu pour ce corps |
|---|---|
| `data/symbols/<build>/frida/methods.tsv` | `…DestroyTheWitch_ExtraMoveEffect.CreateActiveCondition` |
| `data/symbols/<build>/ghidra/functions.tsv` | `…DestroyTheWitch_ExtraDamageEffect$$CreateActiveCondition` |

Même signature exactement au même endroit ailleurs : `MartialSuperiority_VisualEffect.CreateActiveCondition`
(frida) vs `AReactivateOverwatchEffect$$CreateActiveCondition` (ghidra) — corps
`NOT IsTurnOf(owner@0xa0)`, trivialement partageable.

**Ce que ça change pour la doctrine** : « ghidra mislabel, frida fait foi » est une lecture
INCOMPLÈTE. Sur un corps fondu, **aucune des deux tables n'est complète** — le nom manquant n'est
pas faux, il est *absent*. Le seul arbitre est la structure + la mesure live. Ici la mesure tranche
sans ambiguïté (§2) : la condition gouverne **les deux** effets.

---

## 2. `DestroyTheWitch` — RE

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DestroyTheWitchAbility$$CreateBehaviour`

```
AddStaticStatModifierEffectToOwner( 0x440 = 1088 DestroyTheWitch_ExtraMove,
                                    stat = 1 (MOVEMENT),
                                    Direct( GetNumberConstant(cfg, 0xe) = extraMovement = 1 ) )
&  AddEffect( 0x441 = 1089 DestroyTheWitch_ExtraDamage, AbilityStateReference, cible = Owner@0x148 )
```

### `CreateActiveCondition` (corps FONDU, partagé par les deux effets)

```
AmountIsEqualOrGreater( Enemies( Owner@0x148,
                                 UnitsWithTrait( AllUnits@0x80, 0x3ea = 1002 Psyker, 3 ), 3 ),
                        One@0xc0 )
```

`AllUnits@0x80` = le sélecteur battlefield-wide de `DSLFactory$$InitializeShared` — identifié par
`IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$OtherBuffTargets`
(`Friends(owner, @0x80 − owner)` = « tous les AUTRES alliés du plateau »), **pas** par le nom de son
ctor (mislabelé `AllAliveMachinesSelector..ctor`, un gshared partagé — `DSLFactory$$AllUnits` et
`DSLFactory$$AllAliveMachines` construisent le même ctor depuis deux singletons différents).

**GROUND TRUTH LIVE** (`probe_133_destroy_the_witch.py`, board `MC1_67`, seed 777) :

| configuration | 1088 sur Helbrecht | 1089 sur Helbrecht |
|---|---|---|
| a-units = `astraPrimarisPsy`, `orksNob` | **oui** (`statMod {StatType:1, Amount:1}`) | **oui** |
| a-units = `orksNob`, `orksRuntherd` | non | non |
| p-units = Helbrecht + `astraPrimarisPsy` (Psyker **ALLIÉ**) | non | non |

La 3ᵉ ligne est le discriminant : elle sépare `Enemies(Owner, UnitsWithTrait(Psyker))` d'un simple
`UnitsWithTrait(Psyker)`. Et les deux effets apparaissent/disparaissent **ensemble** ⇒ le corps fondu
est bien la `CreateActiveCondition` des deux.

### `DestroyTheWitch_ExtraDamageEffect` (`: BaseEffect`, classes.tsv)

```
CreateTargetSelector             = Unique( SurroundingFriends(Owner@0x148, radius=1, 3)
                                           op_Addition  Owner@0x148 )
CreateEffectDamageBonusForAttack = EffectBonus{ amount  = ConfigVar(8 = extraDmg, GetAbilityState),
                                                trigger = get_OwnerIsCaster & IsMeleeAttack
                                                          & HasTrait(Target@0x178, 0x3ea Psyker) }
```

`DSLFactory$$SurroundingFriends(sel, r, …)` = `Friends(sel, Units(SurroundingTiles(sel, r) − Tiles(sel)))`
→ anneau-1, **porteur EXCLU** ; le `op_Addition Owner` le RE-AJOUTE. Bénéficiaires = **Helbrecht +
ses alliés hex-adjacents**.

### Forme du port

`engine/entities/effects/loki/destroy_the_witch.py` (module dédié : les deux classes partagent le
prédicat `_enemy_psyker_on_battlefield`, mirror du corps fondu).

- volet MOVE = canal stat-mod **déclaratif** (`get_stat_modification_stat/amount` +
  `reverted_stats` + `is_active`), comme `AnvilShield_BlockChanceBelowHealthCap` ;
- volet DÉGÂT = **deux pattes** — `create_effect_damage_bonus_for_attack` (le porteur attaque, le
  sélecteur contient `Owner`) et `create_aura_attack_damage_bonus_for_ally` (un allié adjacent
  attaque). Pas de double-compte : l'agrégateur d'auras exclut déjà `uid == att_id`.

Le ctx d'aura ATTAQUANT a dû être enrichi de `tgt_id`/`tgt_traits`/`t_pos`/`tgt_team` (combat
`damage_model._apply_ally_attack_damage_auras` + prédiction `_shared._apply_ally_attack_dmg_bonus`) :
c'est la première aura ATTAQUANT dont le gate porte sur la **cible**. L'agrégateur DÉFENSE
(`aura_defense_damage_malus_from_units`) portait déjà `tgt_traits` — le canal attaquant est
maintenant symétrique.

---

## 3. `MartialSuperiority` — RE

### `…MartialSuperiorityAbility$$CreateTrigger`

```
On(0x2b = PreUnitAbility, 1)
& NOT ctx@0xa0                          # NOT IsTurnOf(Owner)  -> pendant le tour ADVERSE
& IsDirectTargetAttack(@0x130)          # l'ability EN COURS est une attaque directe/normale
& NOT IsDirectTargetAttack(@0x140)      # ... et n'est pas la FILLE d'une attaque directe
& get_OwnerOrOwnerTileIsTarget          # AreEqual(Target@0x178, Owner) | AreEqual(Target, Tiles(Owner))
& IsMeleeAttack                         # POSITIONNEL (caster adjacent) — le « adjacent enemy » d'i2
& ctx@0x90                              # conjoint de contexte NON QUALIFIÉ (résidu, cf. §5)
```

`DSLFactory$$IsDirectTargetAttack(df, sel)` = `AbilityHasAttackTypeTrigger(sel, 0 = DirectTargetAttack)
| IsNormalAttack(df, sel)` — porté en primitive nommée
(`abilities/attack_type.ability_is_direct_target_attack`). À ne pas confondre avec le
`ability_is_attack` de SwornProtector (`0 | 1`) : `IsDirectTargetAttack` EXCLUT
`SummonAndAttackTarget` et prend l'autre branche (attaque normale). Ses **deux seuls** call-sites
natifs (`list_xrefs`) sont ce `CreateTrigger` et
`IdunBattle.Entities.Effects.CounterAttackEffect$$GetDirectTargetAbilityTrigger`, qui bâtit le MÊME
idiome `IsDirectTargetAttack(@0x130) & !IsDirectTargetAttack(@0x140)`.

### `…$$GetInitialTarget` / `…$$CreateBehaviour`

```
GetInitialTarget = Actor@0x158                                        # l'ATTAQUANT
CreateBehaviour  = AttackWithAttackDamage( Owner@0x148, Actor@0x158,
                       RandomAmount( GetVariableForLevel(0xc minDmg), GetVariableForLevel(0xd maxDmg) ),
                       GetDamageProfile(cfg) = "Power",
                       GetNumberConstant(cfg, 0x2f) = nrOfHits = 2,
                       AbilityOrEffect(1092) )
```

Le sélecteur de cibles natif **est** le slot `Actor@0x158` — porté par le sélecteur `Actor()`
(`entities/selectors/accessors.py`, MÊME slot), pas par un `UnitSet` reconstruit.

### Le gate qui rend « before the enemy attack executes » OBSERVABLE

`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`, séquence lue VERBATIM :

```
FUN_180026490(0x4d, .., 0x2b);                                        # On(PreUnitAbility)
if (options@0x4a == 0 && IsUnit(caster) && IsDead(caster, state))  return 0;   # <-- MANQUAIT
... (bloc #120bis de RE-RÉSOLUTION DE CIBLE) ...
... exécution de la behaviour ...
```

Le natif teste **deux fois** la mort du caster : en tête d'opération (#70, déjà porté) et **juste
après l'événement**, parce que la cascade réveillée par `0x2b` peut l'avoir tué. Le port n'avait que
le premier. Ce lot ajoute le second sur **les deux voies** (`damage_ops.execute` pour l'attaque
normale, `AbilityHandler.visit_ActiveAbilityMessage` pour un cast), au même rang que le natif.

Second artefact du passif, **non porté sans observable** : `MartialSuperiorityAddEffectAbility`
(`: AOwnerEffectTriggeredAbility`, classes.tsv) pose `MartialSuperiority_VisualEffect : BaseEffect`,
qui n'override QUE `CreateActiveCondition` (`NOT IsTurnOf(owner)`) — aucun `CreateEffect*`, aucun
stat-mod : halo visuel « riposte armée » pendant le tour adverse.

---

## 4. Validation live (11 tests neufs, tous verts)

`tests/engine/runner/test_martial_superiority_live.py` — 4 tests

| scénario | mesure |
|---|---|
| POSITIF (`orksNob` adjacent, tour adverse) | live per-target `{attaquant: [3018, 2960], Jaeger: [2006, 2187]}` ; PV offline == live des **deux** côtés ⇒ la riposte est jouée au MÊME rang dans le flux RNG |
| NÉGATIF `IsMeleeAttack` (`necroWarden` à 2 hexes) | live : attaquant intact ; offline == live (sans le gate : 2 coups fantômes) |
| LÉTAL (attaquant à 2 500 PV) | riposte `[2500, 0]` → attaquant mort ; **Jaeger ne perd AUCUN PV** ⇒ l'attaque entrante est annulée ; offline == live |
| gate `NOT IsTurnOf(Owner)` (OFFLINE pur) | `matches()` True au tour adverse, False au tour du porteur |

> Le gate de tour ne peut PAS être confronté live : le moteur natif **refuse** l'action d'une unité
> hors-tour (mesuré : `applyAction` rend 0 événement, 0 delta de PV) — aucun scénario live ne
> distingue « le gate a bloqué la riposte » de « l'action n'a pas eu lieu ». D'où l'isolation
> offline sur l'état déjà chargé (même événement, même géométrie, seul le joueur courant change).

`tests/engine/runner/test_destroy_the_witch_live.py` — 7 tests (3 présence + 4 dégât)

| patte | Helbrecht ↔ attaquant | bonus porté | live per-hit | offline per-hit |
|---|---|---|---|---|
| `self` (Helbrecht frappe le Psyker) | 0 | `Addition 1496` | `[2911, 3115, 3011, 3285, 2893, 2851]` | idem |
| `none` (Helbrecht frappe un non-Psyker) | 0 | `None` | `[916, 1120, 1016, 1290, 898, 856]` | idem |
| `aura` (allié adjacent frappe le Psyker) | 1 | `Addition 1496` | `[5557]` | idem |
| `aura-far` (MÊME allié/cible, Helbrecht loin) | 10 | `None` | `[4061]` | idem |

`aura` − `aura-far` = **5557 − 4061 = 1496** = `extraDmg[L50] × 1.8` exactement. Même attaquant,
même cible, même base de tirage (`base: 4617`) : la SEULE variable est la distance Helbrecht↔allié.

### Deux pièges de HARNAIS rencontrés (ni l'un ni l'autre n'est un bug du port)

- `templSwordBrother` (le voisin « naturel » de Helbrecht) comme allié de l'aura : son passif
  `ChampionOfTheFeast` est lui-même un GAP non porté et ajoute LIVE un 2ᵉ événement de dégât
  `Active_Ability_Type = None` que l'offline ne produit pas (le 1ᵉʳ coup, lui, était déjà bit-exact).
- `astraBullgryn` : son passif `AvalancheOfMuscle` (+599/coup à L50×1.8) est gaté `IsCharging`, porté
  offline par le PROXY `has_moved` (`UnitFlag.Moved`) — résidu **déjà documenté** dans
  `AvalancheOfMuscleExtraDamageEffect`. Selon le nombre de tours consommés par la marche, les deux
  prédicats divergent et injectent un écart de 599/coup SANS RAPPORT avec l'aura.

⇒ allié retenu : `ultraApothecary` (traits {Healer, Hero}, passif `Narthecium` = trigger de revive),
**sans aucun modificateur de dégât propre**.

### Tests de garde rejoués (31, tous verts)

`test_dead_attacker_noop_live` · `test_pre_unit_ability_fork_live` · `test_sworn_protector_kell_live` ·
`test_anvil_shield_stun_live` · `test_beast_slayer_extradmg_live` · `test_psychic_fortress_aura_live` ·
`test_damage_roll_live` · `test_runner_attack_live` · `test_aura_position_live` · `test_predict_live` ·
`test_ability_hits_channel_live` · `test_effect_immunity_live`.

---

## 5. Résidus explicites

- **`NOT IsDirectTargetAttack(@0x140)`** — `@0x140` est le 3ᵉ sélecteur d'ability du factory (aux
  côtés de `@0x130` CurrentAbility, lu par `CurrentAbilityIs`, et `@0x138` TriggeringAbility, lu par
  `TriggeringAbilityIs`) ; `AbilityEntities` expose bien un `get_ParentAbilityType` (propagé par
  `AttackBehaviour$$GetAttackOptions`), ce qui en fait l'ability PARENTE. Le port ne matérialise pas
  de chaîne parent : il n'émet `On(0x2b)` que depuis les deux portes d'opération top-level, jamais
  depuis une attaque FILLE ⇒ le conjoint est VRAI par construction sur tous les vecteurs portés.
- **`ctx@0x90`** — nœud-trigger SINGLETON du factory (classe instanciée UNIQUEMENT dans
  `DSLFactory$$InitializeShared`, et lue UNIQUEMENT par ce `CreateTrigger` dans tout le binaire). Il
  ne reçoit que le service `factory@0x28` — aucun owner/cible — donc il ne peut porter qu'une
  condition GLOBALE. Non qualifié, non porté : MÊME traitement que le conjoint `ctx@0x98` des
  `Triggered()` d'overwatch (case-127 §8.3). La mesure live confirme que la riposte part.
- **`AbilityOrEffect(1092)`** passé par le `AttackWithAttackDamage` natif n'est PAS threadé dans
  `ability_type` : ce canal du port est keyé sur l'espace `ActiveAbilityType` des gates
  `IsNormalAttack`/`AbilityHasAttackType`, où 1092 = `DarkTalonStrike`. Même choix que
  `MartialApotheosis`.
- **Révocation du +1 MOVEMENT** : `refresh_stat_modifier_effects` n'est appelé aujourd'hui que sur
  l'unité qui vient de PRENDRE des dégâts (`operations/damage.py`). La mort du DERNIER Psyker ennemi
  ne retire donc pas le bonus de mouvement de Helbrecht offline tant que ce driver partagé n'est pas
  élargi (hors périmètre). **Sans effet sur l'axe DÉGÂT** : le gate `HasTrait(Target, Psyker)` du
  bonus subsume la présence d'un Psyker ennemi (une attaque vise un ennemi du bénéficiaire).
- **Le repli sans board d'un prédicat n'est pas réutilisable tel quel** : `_is_ranged_position` rend
  `False` (= mêlée) quand le board manque — sens CONSERVATEUR pour son consommateur (splash Psyker :
  pas de re-trigger), sens PERMISSIF pour un trigger de riposte. Mesuré : la riposte partait sur un
  attaquant à 9 hexes. Le port exige donc une **preuve positive** d'adjacence (`_is_adjacent_units`).

## 6. Hors périmètre, corrigé au passage

`FrenziedFiring` (1036) est entré dans `ABILITY_CLASSES` avec le lot #61 (`d2be96e`) **sans son
littéral `AbilityAttackType`** → l'étape 0 du garde-fou `probe_120_pre_unit_ability_fork` échouait
sur `origin/master`. Littéral RELU :
`IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$.ctor` =
`AActiveAbility..ctor(this, &opts, 0, 0)` → **0 = DirectTargetAttack**. Entrée ajoutée. Ses
`TARGETING_OPTIONS` restent NON renseignés : le `&opts` y est un PRESET lu d'un champ STATIQUE de la
classe, pas un littéral inline — les deviner serait pire que l'absence (règle `154b5f0`).
