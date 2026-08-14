# #1015-r1 — `CloseCombatWeakness` : le trait T'AU, ses deux effets et ses deux faces

Résidu de #1015 (« 5 traits portés ne sont lus NULLE PART dans `engine/**` »). Item traité ici :
**`CloseCombatWeakness`**, 16 porteurs, tous `units.npc`.

## 1. La chaîne, lue de bout en bout

```
units.npc.<u>.traits[] = "CloseCombatWeakness"                     (gameconfig, 16 unites)
  -> idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor
     dict GetTriggeredAbility (+0x0) : cle 0x40b (UnitTrait 1035) -> valeur 0x46a
  -> IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities
     (jumeau : IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities)
  -> TriggeredAbilityType.CloseCombatWeakness (1130)
  -> IdunBattleLogic.Entities.Abilities.Active.Loki.CloseCombatWeakness_AddEffectAbility$$.ctor
       = AOwnerEffectSpecificTriggeredAbility(0x46a)
     $$GetEffectType — corps ENTIER `return 0x46a` -> EffectType.CloseCombatWeakness_ReduceDmg (1130)
  -> IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger
       = OnOwnerSpecificAbilityInit(0x46a) -> AddEffect(owner, 1130) a l'init
```

Même patron que `Terrifying` (#73) et `Diminutive` (#75). **Confronté LIVE** : `unitAbilityStates`
rend `triggered = [1028, 1030, 1130]` sur un porteur greffé, `[1028, 1030]` sans le trait.

## 2. L'effet 1130, nœud par nœud

`IdunBattle.Entities.Effects.Loki.CloseCombatWeakness_ReduceDmg_Effect` :

```
$$NearbyEnemiesCondition =
    NOT HasEffect(Owner@DSLSelectors+0x30, 0x478 = SuppressCloseCombatWeakness, onlyActive: 1, targetType: 6)
    & (   HasAdjacentEnemies(unit = Caster@+0x48, unitTile = CasterTile@+0x50, false, false)
        | HasEffect(Owner@+0x30, 0x469 = CloseCombatWeakness_StartedTurnAdjacentToEnemy, 1, 6) )

$$CreateActiveCondition = return NearbyEnemiesCondition()          # corps ENTIER, un seul appel

$$CreateEffectDamageBonusForAttack = EffectBonus.ForPercentIncrease(
    trigger = get_OwnerIsActor & NearbyEnemiesCondition & NOT CurrentAbilityIs(<self>),
    pct     = If( IsMeleeAttack,
                  ConfigConst(0x4c = dmgPctReduction),
                  If( HasEffect(Caster@+0x48, 0x487 = SuppressRangeCloseCombatWeakness, 0, 6),
                      <DSLFormulas+0x18> = Direct(0),
                      ConfigConst(0x53 = dmgPctReduction_2) ) ) )

$$CreateTargetTrigger = On(0x12 = TurnStart_EffectActivation, ownerNeedsToBeAlive: 1)
                        & HasAdjacentEnemies(Owner@+0x30, Tiles(Owner@+0x30), false, false)
$$CreateTargetTriggerBehaviour = AddEffect(0x469, Direct(GetAbilityStateReference(this)),
                                           source = Owner, targets = Owner,
                                           turns = <DSLFormulas+0x20> = Direct(1))
$$GetRefreshTriggers = EventTriggerType[3] via RuntimeHelpers.InitializeArray — NON LU (blob statique)
```

**`ForPercentIncrease`, pas `ForPercentDecrease`, et ce n'est pas une lecture de nom.** Le corps est
INLINE : il écrit `ret+0x00 = trigger`, `ret+0x08 = pct`, puis zérote `+0x10/+0x18/+0x20/+0x28` et le
dword `+0x30` — l'empreinte exacte de `IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease`.
`ForPercentDecrease` alloue un `Direct(-1)` et un `Multiply` (classes `DirectAmount`/`MultiplyAmount`)
qui n'apparaissent PAS dans le bloc d'init de classes de ce corps. Les deux constantes sont
**négatives**, donc le signe est déjà dans la donnée.

## 3. `HasAdjacentEnemies` — le comparateur est INCLUSIF, et c'est mesuré

```
IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies(unit, unitTile, includeObjects, includeSteppables) =
    AmountIsEqualOrGreater(
        UnitsWithoutTrait( UnitsWithoutTrait(
            Enemies(of = unit, AdjacentUnits(unitTile, unique: 1, 3), 3),
            UnitTrait.Object = 0xd, 3), UnitTrait.Steppable = 0x1b, 3),
        Direct(1) )
```

Le `.ctor` visible au décompilé est un corps TRIVIAL **dédupliqué par IL2CPP** (#293) : son nom ne dit
rien de la classe allouée. `python probe_293_aura_predicate_comparator.py --inventory` classe
`DSLTriggers$$HasAdjacentEnemies` dans la famille **INCLUSIF** (`AmountIsEqualOrGreaterAbilityTrigger`,
encodage `setge`) ⇒ **`>= 1` ennemi adjacent**. Prendre le nom du ctor aurait donné `> 1`, et le malus
n'aurait jamais tiré au contact d'un seul ennemi.

## 4. Magnitudes — et la config qui n'est PAS dans la BC

`ConfigConst(<key>, <config de l'ability de trait>)`. Côté gameconfig client :

| clé `AbilityConstantType` | `globalValues.traitVariables` | valeur |
|---|---|---|
| `0x4c = dmgPctReduction` (branche MÊLÉE) | `closeCombatWeaknessMeleeDmgPctReduction` | **-50** |
| `0x53 = dmgPctReduction_2` (branche AUTRE) | `closeCombatWeaknessRangeDmgPctReduction` | **-25** |

L'appariement est **corroboré par l'i2**, qui cite littéralement les noms de membres :
« Whenever this unit is adjacent – or started the turn adjacent – to enemy units, it deals
{[dmgPctReduction]}% Damage with melee attacks and {[dmgPctReduction_2]}% Damage with ranged attacks. »

⚠ **MESURE INATTENDUE** : `BC.Abilities.Traits` ne contient que `{HeavyWeapon, MartialKatah,
RangedSpecialist}` — **pas** `CloseCombatWeakness` — et le natif applique quand même le -50 %. La
config de cette ability de trait n'est donc pas lue depuis la `BattleConfiguration` ; **aucune
injection de config n'est requise** pour la confronter, contrairement au verrou d'une ability de
RELIQUE (#237). Le port lit la source AMONT (`trait_var`), comme `MartialKatahDmgReductionEffect`.

## 5. Face DÉCISION — `CloseCombatWeaknessPlaybook`, deux faces qui ne disent pas la même chose

```
<CalculateMovementUtilityInStepsInternal>d__2$$MoveNext :
    tile    = UtilityMovementCase.get_MovementTile(case)
    enemies = <query>.GetAdjacentEnemies(tile, case.<+0x10>, false)         # slot 0x7f
    yield Fix64( getUtilityVal("CLOSECOMBATWEAKNESS_PerAdjacentEnemy") * enemies.Count )

<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext :
    yield Fix64(0)                                                          # CONSTANTE, corps entier
```

* le slot `0x7f` est **`IBattleQuery.GetAdjacentEnemies`, arité 3** — LU dans
  `data/symbols/<build>/metadata/interface_slots.tsv` (`IBattleQuery 127 GetAdjacentEnemies 3`) ;
* la clé de poids est le **littéral `0x336efa0`** de `metadata/string_literals.tsv` =
  `"CLOSECOMBATWEAKNESS_PerAdjacentEnemy"`, que le `MoveNext` charge (`DAT_18336efa0`) ;
  `BC.Utilities.Default.TriggeredAbilities` lui donne **-40** ⇒ le porteur **FUIT** le contact ;
* ni cap, ni filtre, ni branche AMIS ⇒ **corps propre**, il n'hérite pas de la famille
  `AdjacentUnitPreferenceTriggeredAbilityPlaybook` (dont les slots `vtbl+0x228/0x238/0x248/0x258`
  n'existent pas ici). D'où un module dédié.
* la face ATTAQUE est une **constante zéro** : l'ability n'entre PAS dans
  `psyker.TRIGGERED_ATTACK_PLAYBOOKS`, et **son absence EST le comportement natif** (un step à 0 ne
  se distingue pas d'un playbook absent).

## 6. Ce qui est PORTÉ

| foyer | contenu |
|---|---|
| `engine/entities/effects/loki/close_combat_weakness.py` | l'arbre `has_adjacent_enemies_selector`, `CloseCombatWeaknessReduceDmgEffect` (canal `create_effect_damage_bonus_for_attack`, `active_condition_ported`), `CloseCombatWeaknessStartedTurnAdjacentToEnemyEffect` (marqueur) |
| `engine/entities/effects/factory.py` | `EFFECT_CLASSES` x2, `TRAIT_DERIVED_ABILITIES["CloseCombatWeakness"]`, `ABILITY_INIT_OWNER_EFFECTS["CloseCombatWeakness"]` |
| `engine/entities/effects/__init__.py` | `att_ctx["owner_effect_names"]` — foyer UNIQUE des trois `HasEffect(Owner/Caster, …)`, posé là où la liste des effets de l'attaquant existe RÉELLEMENT (partagé prédiction/combat) |
| `engine/runner/components.py` + `engine/runner/damage_model.py` | face COMBAT du terme géométrique (`close_combat_weakness_adjacent_enemies_count` → `att_ctx`) |
| `engine/playbook/scene.py` + `engine/playbook/prediction/normal_attack.py` | face PRÉDICTION du même terme, évaluée à la TUILE CANDIDATE (#948-r1) |
| `engine/runner/operations/triggers/loki/close_combat_weakness.py` + `dispatch/registry.py` | `EFFECT_TRIGGERS[1130]` — le marqueur 1129 posé au début de tour, `turns = Direct(1)` |
| `engine/playbook/close_combat_weakness.py` + `adjacent_unit_preference.TRIGGERED_MOVE_PLAYBOOKS` | face DÉCISION (MOVE, -40 / ennemi adjacent) |
| `engine/entities/triggered_ability_type.py` | `TRAIT_TRIGGERED_ABILITY_IDS["CloseCombatWeakness"]` — sans quoi le dispatcher n'itère jamais 1130 |

**Nature du coup INCONNUE ⇒ aucune contribution.** Le natif n'a pas d'état « inconnu »
(`IsMeleeAttack` se dérive de `GetAbilityAttackRangeType`), donc sa branche `else` couvre tout ce qui
n'est pas mêlée. Côté port, `is_ranged is None` veut dire « la façade appelante n'a pas threadé la
nature » : appliquer -25 % là imputerait un malus que le natif ne met que sur un coup RÉELLEMENT
non-mêlée. On se tait (même discipline que l'encadré `is_melee_attack` d'`effects/base.py`).

Le gate `NOT CurrentAbilityIs(<self>)` n'est **pas porté** : `<self>` est l'ability passive 1130,
qui n'a ni ciblage ni behaviour d'attaque — aucun vecteur ne peut l'avoir pour ability courante, donc
le gate est toujours vrai.

## 7. Validation

`python probe_1015r1_close_combat_weakness.py` (deux runners par volet, MÊME seed / board / unités /
`Movement`, le seul écart est le trait — **témoin non-nul structurel**).

**Volet MÊLÉE — VERT, écart 0.**

| tuile candidate | natif SANS trait | natif AVEC | ratio | port SANS | port AVEC |
|---|---|---|---|---|---|
| (5,8) vs u77 | (3604, 8420) | (1804, 4212) | 0.5006 / 0.5002 | (3604, 8420) | (1804, 4212) |
| (6,7) vs u77 | (3604, 8420) | (1804, 4212) | 0.5006 / 0.5002 | (3604, 8420) | (1804, 4212) |

Le natif applique **×0.50 exactement** ; le port est **bit-exact** dans les DEUX régimes.

**Volet RANGED — NON CONFRONTÉ.** Le régime discriminant exige une tuile au CONTACT d'un ennemi
CIBLABLE et une cible à distance ≥ 2 EN CLAIR. Trois montages éliminés, chacun pour une raison
mesurée :

1. `tauDarkstrider` (portée 2), 2 ennemis : les spawns les posent **colinéaires** ((6,8) / (6,7)),
   donc toute tuile au contact de l'un met l'autre DERRIÈRE lui — le natif n'émet aucun plan ;
2. `necroWarden` (portée 3), 5 ennemis dont `bloodDante` : la seule tuile au contact met
   `bloodDante` en voisin — mais il porte `TeleportStrike`, arrive en deep-strike et n'est **pas
   ciblable**, donc écarté par le `UnitSelectionType 3` que `HasAdjacentEnemies` propage. Natif et
   port rendaient tous deux AUCUN malus : **accord, mais en régime dégénéré** ;
3. même montage avec `astraYarrick` à la place : le natif ne classe alors plus aucune tuile au
   contact dans ses `ranked` (c'est une mauvaise tuile pour lui), et un déplacement forcé consomme
   l'action.

Deux erreurs de MESURE ont été trouvées au passage, toutes deux dans le sens PERMISSIF, et elles sont
figées dans le probe : `hexgeo.distance == 1` sur-compte l'adjacence (porte d'élévation `|dElev| < 2`,
#271), et ignorer le `selectionType 3` compte un voisin non ciblable.

**Face DÉCISION — non-régression validée, discrimination NON obtenue.** `engine_validate --steps 6`
sur les deux runners : **5/5 positions exactes, 2/2 abilities**, dans les deux régimes. Mais les
positions natives sont IDENTIQUES avec et sans le trait : le terme -40 n'a pas fait diverger le natif
sur ce montage, donc l'accord ne prouve pas que le terme est porté juste — seulement qu'il ne casse
rien.

**Marqueur 1129 (`CreateTargetTrigger`) — non confronté** : aucun montage n'a été joué où le porteur
COMMENCE son tour au contact puis se DÉSENGAGE.

## 8. Résidu

`#1015-r3` (alloué par `probe_468_collision_numeros.py --suggere 1015`) : les trois régimes non
confrontés ci-dessus — branche RANGED (`ConfigConst(0x53)` + le gate `SuppressRangeCloseCombatWeakness`),
terme MOVE `-40 / ennemi`, et marqueur 1129.
