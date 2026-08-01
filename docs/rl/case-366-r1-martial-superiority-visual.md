# case-366-r1 — `1255 MartialSuperiority_Visual` : un prédicat RÉEL que PERSONNE ne lit

**Question, binaire.** Le flag `IsActive` de l'instance 1255 portée par Brother Jaeger suit-il, côté
port, exactement la condition que le natif évalue — et un consommateur quelconque de cet effet
existe-t-il ?

**Réponses : OUI pour la première, confrontée LIVE sur TROIS dates consécutives ; NON pour la
seconde, et c'est une MESURE exhaustive du binaire, pas une absence d'observable.** Porteur
`templChampion` (Brother Jaeger), HERO **au pool** ; voie directe, ni greffe, ni injection, ni
relique.

⚠ **« Visual » dans le nom n'a rien tranché et ne pouvait rien trancher.** La
`CreateActiveCondition` de cette classe est un prédicat RÉEL (pas un stub `return 1`), donc l'effet
porte une sémantique observable. Ce qui le rend sans effet de bord est un fait indépendant, établi
au §3.

## 1. La chaîne, à sa propre source

`data/symbols/<build>/frida/classes.tsv` :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.MartialSuperiorityAddEffectAbility
        : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility : BaseTriggeredAbility
    IdunBattle.Entities.Effects.Loki.MartialSuperiority_VisualEffect
        : IdunBattle.Entities.Effects.BaseEffect                                (taille 0x480)

La classe d'ABILITY n'a **aucune ligne** dans les deux tables — ce qui ne prouve rien (dedup par
adresse). Son unique override est `GetEffectType`, identifié par **balayage du PE** : le corps
`b8 e7 04 00 00 c3` (`mov eax, 0x4e7 ; ret`) est **UNIQUE dans tout le binaire** et porte **DEUX**
entrées dans `methodPointers` — l'une dans la région des EFFETS (c'est
`GazeOfMagnusEffect$$GetTriggeredAbilityType`, à qui les deux tables l'attribuent :
`TriggeredAbilityType 1255 = GazeOfMagnus_Attack`, homonymie d'id), l'autre dans la région des
ABILITIES, **immédiatement avant les trois méthodes de `MartialSuperiorityAbility`**
(`CreateTrigger`/`CreateBehaviour`/`GetInitialTarget`, entrées contiguës) — les deux classes sœurs
sont déclarées côte à côte, donc contiguës en ordre de métadonnées.

Tout le comportement du poseur vient de la base, sans override :

    AOwnerEffectTriggeredAbility$$CreateTrigger   = OnOwnerSpecificAbilityInit(this.Id@+0x10)
    AOwnerEffectTriggeredAbility$$CreateCondition = <DSLTriggers+0x70>      # YesTrigger (size 16)
    AOwnerEffectTriggeredAbility$$CreateBehaviour =
        If( CreateCondition(abilityState),
            AddEffect( GetEffectType() = 0x4e7, AbilityState(Owner@<Sel+0x30>, <AbilityType>),
                       targets = Owner@<Sel+0x30>, source = Owner@<Sel+0x30>, <durée ZÉROÉE> ) )

⇒ owner-effect **permanent**, posé à l'init sur le porteur.

## 2. Le `.ctor` et la condition — lus à l'ASSEMBLEUR

`MartialSuperiority_VisualEffect$$.ctor` (le décompilateur masque l'immédiat) :

    ba 44 04 00 00      mov  edx, 0x444                  ; 1092
    e8 ..               call IdunBattle.Core.AbilityOrEffect$$op_Implicit
    41 b0 01            mov  r8b, 1                       ; hasAutomaticActivation = TRUE
    e8 ..               call IdunBattle.Entities.Effects.BaseEffect$$.ctor

**Qualification d'enum** : la surcharge d'`op_Implicit` visée par le `call` est celle dont
`methods.tsv` donne la signature `op_Implicit(triggeredAbility: TriggeredAbilityType)` — c'est la
LECTURE qui qualifie, jamais le nom. `1092` y vaut `MartialSuperiority`, l'ability SOURCE. Aux mêmes
ids : `EffectType 1092 = HolyDuel_ExtraDmg`, `ActiveAbilityType 1092 = DarkTalonStrike`. Trois enums,
un nombre.

`BaseEffect$$.ctor(abilityOrEffect, hasAutomaticActivation: System.Boolean)` reçoit **TRUE** :
contrairement à `WireweaveNet_CounterAttackEffect` (`PlayerTurnEffect`, `hasAutomaticActivation =
False` + machine à états), cet effet **s'arme seul à la pose** et n'a **aucun** trigger — sa seule
horloge est sa condition.

    MartialSuperiority_VisualEffect$$CreateActiveCondition
        = op_LogicalNot( <DSLTriggers+0x28> )            # = NOT IsTurnOf(Owner)

C'est-à-dire **exactement la fenêtre du gate `NOT IsTurnOf(Owner)` de la riposte**
(`MartialSuperiorityAbility$$CreateTrigger`, portée par #133) : le halo « riposte armée ».
`<DSLTriggers+0x28>` = `IsTurnOf(Owner)` (identification de `case-366-r1` §2, et corps FONDU partagé
avec `AReactivateOverwatchEffect` — cf. `case-133` §1).

La classe n'a qu'**un troisième slot** dans son bloc `methodPointers`, et son corps est le
`return <DSLSelectors+0x30>` partagé par ~250 classes d'effet (unique propriétaire nommé :
`WhisperingWebEffect$$CreateTargetSelector`) : `CreateTargetSelector = Owner`, structurel. **Aucun**
`CreateEffect*`, **aucun** stat-mod, **aucun** `ApplyInternal`.

## 3. Le fait qui tranche : ZÉRO consommateur, et c'est mesuré

Balayage du PE pour **toute** occurrence de l'immédiat 4 octets `0x4e7` dans les sections de code.
Méthode validée sur un **CONTRÔLE** : le même balayage sur `0x457 = 1111 WireweaveNet` retrouve bien
son consommateur IA (`IdunBattle.AI.Utilities.WireweaveNet_FirstAttack.<EvaluateAttackInSteps>d__1$$MoveNext`),
son `.ctor` d'effet, son `GetEffectType` et ses 4 sites d'enregistrement.

Pour `0x4e7`, les **seuls** sites sont des enregistrements ou des tables statiques :

| site | rôle |
|---|---|
| `GazeOfMagnusEffect$$GetTriggeredAbilityType` | le corps partagé (= `…AddEffectAbility$$GetEffectType`) |
| `AbilitiesDatabase$$InitializeTriggeredAbilities` | `TriggeredAbilityType 1255` (GazeOfMagnus_Attack) |
| `EffectsDatabase$$InitializeEffects` | `EffectType 1255` → fabrique `<InitializeEffects>b__14_268` |
| `StaticBattleRules.Effect$$.cctor` | table statique |
| `StaticBattleRules.TriggeredAbility$$.cctor` (×2) | table statique |

⇒ **aucun gate `HasEffect`, aucune utilité IA, aucun canal de bonus/malus, aucun sélecteur** ne lit
1255. Confirmé par une source INDÉPENDANTE, côté DONNÉES : la chaîne `MartialSuperiority` apparaît
**une seule fois** dans le BattleConfiguration (sa config d'ability), et aucun bucket de
`BC.Utilities.Default` — ni les trois utilités GÉNÉRIQUES keyées par NOM D'EFFET
(`UnitEffectsAdjacent`, `UnitEffectsRanged`, `UnitEffectsSurrounding`), ni `TileEffects`, ni
`TriggeredAbilities` — ne porte de clé `MartialSuperiority*`. `RemoveEffectsBehaviour$$ExecuteByOwner`
filtre par `StaticBattleRules.Effect$$GetReplaceableEffectType` **plus** un `EffectType` explicite :
rien ne balaie en aveugle.

**Conséquence** : le port est de **FIDÉLITÉ**, pas de comportement — rayon de souffle NUL sur les
axes DÉGÂT et DÉCISION tant qu'aucun consommateur de 1255 n'existe. Il est fait parce que le prédicat
est **LU**, et parce que le laisser sur `BaseEffect.is_active` (qui rend `True` INCONDITIONNELLEMENT)
publierait le halo « riposte armée » **pendant le tour de Jaeger**, où le natif l'éteint.

## 4. Ce qui est porté

| quoi | où |
|---|---|
| classe d'effet | `scripts/python/engine/entities/effects/loki/martial_superiority.py` |
| registre | `scripts/python/engine/entities/effects/factory.py` (`EFFECT_CLASSES["MartialSuperiority_Visual"]`, + le commentaire qui documente l'entrée `ABILITY_INIT_OWNER_EFFECTS` VOLONTAIREMENT absente) |
| clé `is_turn_of_owner`, face COMBAT | `scripts/python/engine/runner/components.py` (`UnitEffectStateView`) |
| clé `is_turn_of_owner`, face DÉCISION | `scripts/python/engine/playbook/scene.py` (`Scene.unit_state`, via `Scene.is_turn_of`) |
| montage live | `scripts/python/probe_366_r1_martial_superiority_visual.py` |
| gardes | `scripts/python/tests/engine/runner/test_martial_superiority_visual_live.py` (6) |

La clé `is_turn_of_owner` existait déjà sur le canal `att_ctx` (foyer
`entities/effects/base.py::is_turn_of_owner`, posé par `1110 FireAndReposition_ReduceDmg`) ; ce cas
la pose sur le canal `unit_state`, avec **la même lecture native** des deux côtés
(`IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer` — invoquée par le hook côté
DÉCISION, `OwnerComponent.player == State.current_player_id` côté COMBAT).

**Pas d'entrée `ABILITY_INIT_OWNER_EFFECTS["MartialSuperiority"]`**, même raisonnement que
`WireweaveNet` (`case-366-r1b` §7ter) mais en plus fort : l'instance n'étant lue par RIEN, la
matérialiser quand le canal de capture ne l'a pas vue n'apporte aucun observable, et exposerait au
piège #312 (le seed lit les passives du KIT gameconfig, pas de la MESURE).

## 5. Confrontation LIVE — trois dates, deux canaux

`probe_366_r1_martial_superiority_visual.py`, board `MC1_67`, seed 777, duel 1v1
`templChampion` vs `orksNob`. Instance mesurée : `{effectId: 92, name: MartialSuperiority_Visual,
effectType: 1255, remaining: 0, level: 1, source: 79 (Jaeger)}`.

| date | NATIF `active` | NATIF canal par DÉFAUT | PORT `is_active` | PORT flag | PORT `active_effects` |
|---|---|---|---|---|---|
| tour du PORTEUR | `false` | absent | `False` | `False` | absent |
| tour ADVERSE | `true` | présent | `True` | `True` | présent |
| retour au PORTEUR | `false` | absent | `False` | `False` | absent |

Le **retour** au 3ᵉ échantillon est ce qui sépare « suit la condition » de « figé à la capture » — un
test à deux dates aurait été vert pour un flag qui ne bascule qu'une fois.

Le flag OFFLINE est écrit par `refresh_stat_modifier_effects`, que
`runner/operations/turnflow.py` joue au StartTurn pour `RefreshEffectTrigger.TurnChanged` →
`RefreshEffectsOperation$$Execute(effectEntity = NUL)`. Ce cas passe par le **discriminant #366-r1b**
(`_active_condition_is_ported` = « la classe surcharge-t-elle `is_active` ? ») : porter une
`CreateActiveCondition` fait automatiquement entrer la classe dans la branche « ré-évaluer et écrire
le flag ». Le cliquet a été **remonté délibérément** — plancher `>= 15` dans
`test_refresh_active_flag_discriminant_offline` (compte RE-DÉRIVÉ : il disait `>= 13` alors que
`CamoCloak_DmgReduction` était déjà entrée ; un plancher qu'on ne remonte pas cesse d'être un
cliquet).

**Contre-épreuve** (`[4]` du probe, et garde
`test_unported_class_would_publish_the_halo_during_the_owner_turn`) : le MÊME effet capté, routé sur
`BaseEffect` (= le port AVANT ce cas) rend `is_active = True` pendant le tour de Jaeger. Le régime
MORD.

## 6. Mutations adversariales — 5 mutations, 5 ROUGES

Chaque remplacement **échoue bruyamment** s'il ne matche pas exactement une fois, et l'effet de la
mutation est re-vérifié avant lecture du résultat (piège CRLF).

| mutation | ce qui rougit |
|---|---|
| M1 `is_active` → `return True` (condition neutralisée) | 3 tests, dont `..._port_reproduces_the_native_on_the_three_dates` |
| M2 polarité inversée (`return bool(v)`) | les mêmes 3 |
| M3 clé `is_turn_of_owner` retirée du canal COMBAT (`UnitEffectStateView`) | 2 tests |
| M4 entrée de registre retirée | `..._is_posed_and_routed_to_the_ported_class` + le CLIQUET du discriminant |
| M5 clé retirée de la face DÉCISION (`Scene.unit_state`) | `..._decision_face_carries_the_same_turn_key` |

**Cliquets** : `probe_181` (99/99, 0 manquante), `probe_120 --step 0`, `probe_273 --only-scan`,
`probe_365`, `probe_391` — tous verts. **Non-régression** : 23 tests offline (registre/partition,
cliquet du discriminant, ratchet d'abilities) + 35 tests live voisins
(`test_martial_superiority_live` 4/4 — MÊME porteur, `test_wireweave_net_counter_live` 6/6,
`test_contagions_lifecycle_live` + `test_anvil_shield_stun_live` + `test_camo_cloak_dmg_reduction_live`
18/18, `test_visions_of_heresy_pierce_live` + `test_aura_position_live` 5/5, `test_predict_live` 2/2).

## 7. Ce qui n'est PAS couvert

* **La face DÉCISION n'a pas de consommateur à confronter** : aucune utilité IA ne lit 1255 (§3),
  donc la garde de cette face porte sur la clé `is_turn_of_owner` de `Scene.unit_state` et sur la
  valeur de la condition, pas sur un score. Il n'y a rien de plus à confronter tant que le natif
  lui-même n'en fait rien.
* **Le troisième slot de vtable** (`CreateTargetSelector = Owner`) est établi par CONTIGUÏTÉ du bloc
  `methodPointers`, pas par un symbole nommé : le corps est partagé par ~250 classes. La conclusion
  est structurelle (un owner-effect se cible lui-même) et sans enjeu — mais ce n'est pas une lecture
  de symbole.
* **`ShouldRefreshForTrigger` n'est toujours pas porté** (résidu NOMMÉ de `case-366-r1b` §8) : le
  port ne mirrore pas le CHOIX natif entre « ré-évaluer » et « conserver ». Ici le natif re-évalue
  TOUJOURS (l'effet n'a aucun trigger, donc son set vtable `+0x5c8` est vide et
  `BaseEffect$$ShouldRefreshForTrigger` rend TRUE) — le port fait donc la même chose, mais pour une
  raison qu'il ne LIT pas.
* **L'instance n'existe offline que si la capture l'a vue.** Elle est PERMANENTE et publiée par le
  canal `includeInactive` dans les deux régimes (mesuré), donc `snapshot.decision_view_seed_body` la
  livre toujours ; mais un `load_state` sur le canal par DÉFAUT pris pendant le tour du porteur n'en
  aurait AUCUNE. Sans conséquence tant que rien ne lit 1255 — à rouvrir avec un seed d'owner-effects
  si un consommateur apparaît.
* **Le poseur `MartialSuperiorityAddEffectAbility` n'est inscrit dans aucun registre du port**
  (ni `ABILITY_TRIGGERS`, ni `ABILITY_INIT_OWNER_EFFECTS`) : c'est délibéré (§4), pas un oubli.
