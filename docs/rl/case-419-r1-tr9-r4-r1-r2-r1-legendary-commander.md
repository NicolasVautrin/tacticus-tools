# #419-r1-tr9-r4-r1-r2-r1 — `LegendaryCommander_ExtraHits` (1395), le consommateur en NÉGATION

**Verdict : PORTÉ + CONFRONTÉ LIVE.** L'effet, son sélecteur d'aura, ses quatre nœuds de trigger, sa
liste persistante (écriture ET purge) et la clé `is_first_hit_group` entrent d'un bloc. Trois
substrats neufs, un mutant par axe, accord port/natif 4/4.

## 1. La RE, RE-LUE au décompilé (`rnca9r7q6c`) — trois corrections à la lecture héritée

La fiche amont (`case-419-r1-tr9-r4-r1-r2-gate-is-normal-attack.md` §4) est **confirmée sur les deux
formules**, mais elle laissait trois choses fausses ou absentes, chacune décisive :

1. **Le porteur n'est pas la cible.**
   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegendaryCommanderAbility$$CreateBehaviour` =
   `AddEffect(0x572 = 1394, .., Owner@0x30, Owner@0x30, <turns VIDE>) & AddEffect(0x573 = 1395, ..,
   Owner@0x30, Owner@0x30, <turns VIDE>)` : **les deux effets vivent sur TRAJANN**. Les ennemis
   affectés sont les `EffectComponent.Targets @+0x48`, re-dérivés par le `CreateTargetSelector` de
   l'effet (modèle `entities/effect_targets.py`). Le canal du port est donc **AURA**
   (`aura_hits_bonus_for_attack`), pas le canal DÉFENSEUR — l'inverse aurait cherché 1395 dans les
   effets de la victime, où il n'est jamais.
2. **Le sélecteur n'était pas lu.**
   `LegendaryCommander_ExtraHitsEffect$$CreateTargetSelector` =
   `Filter( AdjacentEnemies( Filter( Friends(Owner@0x30, AllUnits@0x20, 3),
   HasUsedActiveAbilityThisTurn(Subject@0x68) ), unique = 1, 3 ), IsAdjacent(Owner@0x30,
   Subject@0x68, 3) )`. Les trois premiers nœuds sont ceux de la base
   `ALegendaryCommander_BaseEffect$$CreateTargetSelector` (partagés avec 1394) ; le **quatrième** est
   propre à 1395 — c'est le « **also** adjacent to Trajann » de l'i2. `Friends(Owner, AllUnits)`
   n'a **aucun** `- Owner` : **Trajann compte parmi les alliés dont le cast arme l'aura**, ce qui
   rend le montage confrontable avec une seule unité castante.
3. **`GetMarkCasterBehaviour` / `IsCasterMarked` / `GetClearAllMarkedAttackersBehaviour` sont MORTS**
   (xrefs = métadonnée IL2CPP seule). Le couple vivant est
   `$$CreateTargetTrigger` = `On(0xa = AttackDamageAttack) & IsValidAttack(Effect@0x38)` →
   `$$CreateTargetTriggerBehaviour` = `AddToPersistentDataList(<AbilityOrEffect>,
   EffectSource(Get(effect)), EntityId(Owner@0x30), EntityId(Caster@0x48))`, plus `$$RevertInternal`
   (§4). `GetMarkCasterBehaviour` a le **corps identique** à `CreateTargetTriggerBehaviour` : un
   doublon, pas un second mécanisme.

Le reste est confirmé mot pour mot :

```
$$IsValidAttack(<sel>) =
      get_OwnerIsTarget
    & AreFriends(Caster@0x48, EffectSource(<sel>))
    & !IsNormalAttack(CurrentAbility@0x88)
    & !(TriggeringAbilityIsNormalAttack & IsPartialAttackAbility(CurrentAbility@0x88))

$$CreateEffectHitsBonusForAttack =
    EffectBonus.ForAddition(
        trigger  = ( IsValidAttack(Effect@0x38)
                     & !IsInPersistentDataList(<AbilityOrEffect>, EffectSource(Effect@0x38),
                                               EntityId(Owner@0x30), EntityId(Caster@0x48)) )
                   & IsFirstHitGroupInAttack(),
        addition = ConfigVar(0x2f = nrOfHits, <abilityState>, config@+0x60) )
```

⚠ `LegendaryCommander_ExtraHitsEffect$$.ctor` est un corps **dédupliqué** : les lambdas
`EffectsDatabase.<InitializeEffects>b__14_403` / `b__14_404` l'appellent toutes deux, sur des
`Il2CppClass*` distincts (1394 et 1395). Le nom du ctor ne dit pas l'identité de classe.

## 2. `IsFirstHitGroupInAttack` — le canal `hitGroupIndex`, tranché par lecture

`IdunBattleLogic.Entities.DSLTriggers$$IsFirstHitGroupInAttack` →
`IsFirstHitGroupInAttackTrigger$$ShouldTrigger` → `AbilityEntities$$get_IsFirstHitGroup`, qui rend
`Nullable<bool>( (idx.GetValueOrDefault() == 0) && idx.HasValue )` sur le `Nullable<int>`
@`AbilityEntities+0x110`. **Unique consommateur : cet effet** (xrefs, confirmant #512).

Ce champ arrive par le **3e paramètre** de `GetAttackHits`, et **les quatre façades portées valent 0** :

* COMBAT — `IdunBattle.Operations.AttackDamageOperation$$Execute` passe `*(int*)(currentAttack+0x34)`
  au slot 0xb6, et `IdunBattle.Core.OngoingAttack$$.ctor` **initialise ce bloc à zéro** (`+0x30`,
  8 octets). Les groupes de coups additionnels **à profil** re-entrent `Execute` avec un index
  incrémenté ; le port ne leur fait pas traverser la formule (`execute_additional_hits` consomme le
  `count` du descripteur #179), donc aucune sur-application de ce côté.
* PRÉDICTION — littéral `0` (déjà tranché par #419-r1-tr9-r4-r2).

D'où `attack_hits_with_modifiers(hit_group_index=0)` : un **paramètre** (pas une constante) pour
qu'un test puisse le faire mordre, posé au board et lu par le canal aura.

## 3. Face PRÉDICTION : structurellement INERTE, et c'est le natif

Les deux façades de prédiction qui traversent la formule (`make_normal_attack_predictions` et le
fold `GetAdditionalDamagePrediction`) portent `is_normal_attack = True` — le gate `!IsNormalAttack`
les ferme. La prédiction d'une attaque d'ABILITY n'interpose pas la formule (entête de
`services/attack_hits_formula.py`, point 4). **Le seul régime où 1395 mord est le COMBAT, famille
ATTACK** (`runner/operations/damage_ops/ability.py`).

## 4. Ce que la MESURE a imposé : le « first attack » est PAR FENÊTRE DE COUVERTURE

Premier montage : Trajann caste, `deathBlightlord` attaque (5 coups), tour suivant il ré-attaque —
**3 coups**. Lecture naïve : « la marque a fermé ». **Faux, et le probe l'a démonté** : entre les deux
tours, `HasUsedActiveAbilityThisTurn` retombe
(`IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags`), donc l'aura ne couvre plus
la victime et le bonus tombe **pour cette raison-là**. Le cran n'était pas discriminant : deux causes
se confondaient.

Montage corrigé — **Trajann RE-caste au tour 2** avant la 2e attaque. Mesure :
**le natif rend de nouveau 5 coups.** La marque n'a donc pas survécu à la sortie de l'aura, et le
mécanisme est `$$RevertInternal` = `ExecuteBehaviour(ClearPersistentData(<AbilityOrEffect>,
EffectSource(Get(effect)), EntityId(Target@0x60)))`, appelé par
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` quand une cible **sort** de
`Targets`. L'effet, lui, ne part jamais (`AddEffect` sans durée).

Conséquence de port : le clear est **obligatoire**, sans quoi le port sous-appliquerait (il refuserait
un bonus que le natif re-donne). Le port ne matérialisant pas `Targets`, il purge à la **clôture
d'attaque**, quand la cible n'est plus couverte alors qu'elle porte encore une marque — collapse
assumé, seul instant où le port observe le couple (cible, couverture). Résidu : une cible qui sort
puis rentre **sans qu'aucune attaque ne la vise** garde sa marque côté port.

### 4bis. La purge par SORTIE de cible — portée au REFRESH (2026-08-15)

Deux choses écrites au §4 étaient **fausses au moment d'être relues**, et une troisième était
sous-estimée.

* ❌ « **le port ne matérialise pas `Targets`** » — faux depuis #477-r21-r2 volet A :
  `refresh_effects.update_effect_targets` est un mirror **1:1** avec `EffectComponentView.targets`,
  `get_targets_to_remove` et `remove_targets_from_effect`. Ce qui restait vrai est plus étroit et
  plus intéressant : **ce mirror n'avait aucun appelant dans le flux de combat** (un probe, un test,
  un traducteur de flux — rien d'autre).
* ❌ Le **foyer** annoncé au backlog citait `entities/effects/loki/extra_damage_aura.py`, qui n'a
  rien à voir. Les vrais sont `loki/hits.py` (la classe 1395) et `effects/base.py` (le protocole).
* ⚠ « **Sous-application possible en self-play multi-tours** » sous-estime : le régime est le régime
  **NORMAL**. Le sélecteur exige `HasUsedActiveAbilityThisTurn` d'un allié, et
  `UnitFlagsComponent$$RemoveTurnFlags` le retire à **chaque** entrée de tour — la couverture tombe
  donc tous les tours, et le port **refusait un bonus que le natif re-donne**. C'est très exactement
  ce que la mesure du §4 avait établi *sur le natif*.

**Ce qui est livré.** `BaseEffect.targets_to_revert_on_exit` (défaut `()`, discriminant par **MRO** —
un `hasattr` confondrait « pas porté » et « rien à purger »), sa surcharge sur 1395, et le driver
`refresh_effects.revert_effects_for_exited_targets`, appelé par `refresh_stat_modifier_effects`.
Le point d'appel n'est pas un choix de commodité : le natif **ne scinde pas** les deux volets
(`RefreshEffectsOperation$$Execute` évalue `ShouldBeActive` **puis** appelle `UpdateEffectTargets`),
et les trois sites qui appellent déjà ce driver (`turnflow` en `TurnChanged` — **après**
`remove_turn_flags` —, `movement`, `damage`) sont ceux où le natif refresh.

**Pourquoi aucune matérialisation n'est nécessaire — et c'est une ÉQUIVALENCE, pas un collapse.**
`RevertInternal` de 1395 est un `ClearPersistentData` **par cible** : sur une cible sortie mais **non
marquée**, c'est un no-op. L'ensemble des cibles *marquées* est donc un sur-ensemble suffisant de
`targetsToRemove` **pour ce qui est observable** — balayer les marques rend le même état que
balayer `Targets`.

Contre-épreuve : **4 mutations du code de production, 4 rouges**
(`tests/engine/test_419r1tr9r4r1r2r1b_purge_hors_attaque_offline.py`, 7 tests).

## 5. Le port — ce qui entre, et où

| pièce | fichier |
|---|---|
| l'effet (sélecteur d'aura + 4 nœuds + persist + first-hit-group) | `engine/entities/effects/loki/hits.py::LegendaryCommanderExtraHitsEffect` |
| registre + `EFFECT_CLASSES["LegendaryCommander_ExtraHits"]` | `engine/entities/effects/factory.py` |
| `hit_group_index` + `is_normal_attack` au board, ctx aura = board complet | `engine/services/attack_hits_formula.py` |
| `used_active_by_id`, `persistent_data_list` au board COMBAT | `engine/runner/damage_model.py::build_hits_board` |
| le target-trigger `On(0xa)` : marquage **et** purge | `engine/runner/operations/triggers/loki/legendary_commander.py` |
| `EFFECT_TRIGGERS[1395]` + rail `TARGETS` (probe_229) | `.../dispatch/registry.py`, `probe_229_effect_triggers_active.py` |
| `TriggerEvent.is_normal_attack` (tri-état) + son threading | `.../triggers/base.py`, `.../dispatch/attack.py`, `damage_ops/{normal,ability}.py` |

**Résidu nommé — `IsPartialAttackAbility` non porté.**
`AbilityIsPartialAttackAbilityTrigger$$IsPartialAttack` teste l'appartenance du `CurrentAbility` à
l'un de deux `HashSet` statiques (`StaticBattleRules.TriggeredAbility$$IsPartialAttackAbility`,
`StaticBattleRules.Effect$$IsPartialAttack`) et rend **faux pour toute ACTIVE**. Ces ensembles ne
sont pas lus. Le port remplace `!(TriggeringAbilityIsNormalAttack & IsPartialAttackAbility)` par son
**premier conjoint seul** — une borne qui ne peut que **restreindre**, jamais élargir. Régime
concerné : une attaque d'ability **déclenchée par une attaque normale** ; hors de lui les deux formes
coïncident. **NON CONFRONTÉ** (aucun montage porté ne l'atteint).

**Résidu nommé — la POSE.** `LegendaryCommander` n'est pas dans `ABILITY_TRIGGERS` : le port ne pose
pas 1395 lui-même, il le reçoit du snapshot live. En simulation multi-tours partie de zéro, l'effet
n'apparaîtrait pas. Sans conséquence sur ce cas (le harnais hydrate depuis le live).

## 6. La confrontation — `probe_419r1tr9_r4_r1_r2_r1_legendary_commander.py`

Deux bras, **même board (`MC1_67`), même seed (41395), même géométrie, même cast** ; la seule
variable est le cast de Trajann. `custoTrajann` + `deathBlightlord` (`FlailSwing`, famille ATTACK,
`nrOfHits = 3`) contre `astraBullgryn` ; victime sur une tuile à 6 voisins marchables, Trajann et
l'attaquant sur deux d'entre eux (placement **drivé et relu**, jamais subi).

```
                       natif   port
  armed / attaque 1      5       5      (3 + ConfigVar(0x2f) = 2)
  armed / attaque 2      5       5      (Trajann a RE-caste -> l'aura re-couvre, la marque est partie)
  idle  / attaque 1      3       3
  idle  / attaque 2      3       3

  [1] montage : effet 1395 present sur custoTrajann, d(armed - idle) = +2 = nrOfHits  (100 % NATIF)
  [2] accord port/natif : 4/4
  [3] mutants, deplacement du PORT dans `armed` / dans `idle` :
        effect_off            -2 / 0      no_first_hit_group    -2 / 0
        no_used_active        -2 / 0      as_normal_attack      -2 / 0
        attacker_not_friend   -2 / 0      no_persistent_gate     0 / 0   (cf. ci-dessous)
  [4] << first attack >> DANS la fenetre (deux casts consecutifs, meme State porte) :
        port            [5, 3]
        no_persist      [5, 5]      <- la reciproque : le mutant du gate persistant, et lui seul,
        idle            [3, 3]         remonte la 2e attaque
```

Le cran [1] est **entièrement natif** : le port n'entre pas dans la définition du verdict. Le
mutant `no_persistent_gate` est **structurellement inerte** sur la première attaque (le sac est
encore vide — le marquage a lieu **après**, sur `On(0xa)`) ; son cran à lui est [4], et c'est là
qu'il mord. Chaque mutant patche la **méthode** de la classe, jamais le registre `EFFECT_CLASSES` —
la scène est déjà hydratée quand il tourne, retirer une clé ne défait rien et rendrait un vert
menteur (mesure #419-r1-tr9-r4-r1-r2).

**Garde** : `tests/engine/runner/test_419r1tr9_r4_r1_r2_r1_legendary_commander_live.py` — **6 tests,
0 skip, 26 s**.

## 7. Non-régression rejouée

| fichier | résultat |
|---|---|
| `tests/engine/entities/test_attack_nature_gates_offline.py` | 17 passed, 2,0 s |
| `tests/engine/test_419r1tr9_r4_r1_r2_normal_attack_gate_live.py` | 6 passed, 118 s |
| `tests/engine/runner/test_ability_hits_channel_live.py` | 5 passed, 135 s |
| `tests/engine/runner/test_flail_swing_live.py` | 4 passed, 109 s |
| `tests/engine/runner/test_419r1tr9_r4_r1_r2_r1_legendary_commander_live.py` (neuf) | 6 passed, 26 s |

**38 tests, 0 skip.** Banque de cliquets : `pwsh -File scripts/ratchets.ps1` → **33 verts, mur
176,9 s** (relevé daté ; la composition fait foi dans `scripts/ratchets.ps1`, pas ici). Elle a
**rougi d'abord** — `probe_229`, `probe_421`, `probe_457:s1`, tous sur la même cause : une classe
entrée dans `EFFECT_TRIGGERS` sans son rail. Corrigé dans le même commit (rail `TARGETS` déclaré,
et le port lit désormais `EffectComponent.IsActive` comme le fait
`EvaluateEffectTriggerTargets` avant tout `$$CreateTargetTrigger`).

## 8. Ce que ce cas n'établit PAS

* **`IsPartialAttackAbility`** (§5) — nœud approximé par excès, non confronté.
* **Le régime multi-groupes** : `hit_group_index != 0` n'est pas atteint par le port (les groupes
  additionnels ne traversent pas la formule) ; le nœud est confronté par **mutation**, pas par une
  attaque native à plusieurs groupes.
* ~~**La purge hors attaque**~~ — **FERMÉE le 2026-08-15 (`#419-r1-tr9-r4-r1-r2-r1b`)**, cf. §4bis.
  Ce qui reste ouvert est sa **confrontation live** sur le régime propre (`#419-r1-tr9-r4-r1-r2-r1b-r2`).
* **Une seule magnitude** : `nrOfHits[L50] = 2`, lue, jamais codée en dur — mais une seule valeur a
  été confrontée.

## 9. `#419-r1-tr9-r4-r1-r2-r1a-r1` — le canal du PREMIER conjoint, LOCALISÉ (2026-08-17)

**La prémisse tient**, re-vérifiée sur le code courant : `damage_ops/normal.py` passe
`trigger_ability_type=triggering_ability` à `build_hits_board` mais pas `ability_type` ;
`damage_ops/ability.py` fait l'**inverse** (`ability_type=ability_type`, pas de
`trigger_ability_type`). Sur la seule face où l'effet reste ouvert, le premier conjoint lit donc
`None` et la conjonction ne peut pas mordre.

**Ce que la RE ajoute** — et qui déplace le travail restant. Dans
`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`, l'`AbilityEntities` est construit avec
(paramètres nommés LUS dans `data/symbols/<build>/frida/methods.tsv`) :

| paramètre | source |
|---|---|
| p13 `currentAbilityOrEffect` (`+0x60`) | `context+0x10..0x28` |
| p14 `parentAbilityOrEffect` | **VIDE** |
| p15 `triggerAbilityOrEffect` (`+0x98`) | `context+0x2c..0x44` |

et `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` remplit ces deux blocs depuis des
**sources différentes** : `+0x10..0x28` ← son 5ᵉ argument `abilityOrEffect` (ce que le port pose
déjà en `ability_type`), `+0x2c..0x44` ← **`AttackDamageOptions+0x54..0x6c`**.

Le premier conjoint ne se répare donc **ni** en recopiant `ability_type` — ce que la fiche
craignait à juste titre — **ni** en recopiant `state.trigger_ability_type` sans preuve : il faut
d'abord établir ce que porte ce champ d'options.

**Ce qui bloque.** `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` est
l'étage qui remplit les options, et son décompilé Ghidra ne montre qu'**un seul**
`Nullable<AbilityOrEffect>` construit alors que le struct en porte deux — le remplissage de `+0x54`
doit être lu **à l'assembleur**, comme les deux `HashSet` de `#419-r1-tr9-r4-r1-r2-r1a` l'ont été.
Le risque nommé par la fiche d'origine reste entier : `PurgeResponse` (1538,
`TriggeringAbilityIs(EffectType 1009 Overwatch_AutoAttack)`) lit le **même** canal, donc une valeur
fausse y ferait firer un second consommateur à tort. `BLOCAGE: etage`. **NON CONFRONTÉ.**
