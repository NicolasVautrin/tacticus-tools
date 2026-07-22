# Case #61bis — MV71SniperDroneSquadAttack (1076) : port de l'attaque déclenchée du Marksman

> Successeur de #61 (clos sans port — `case-61-additional-hits-prediction-reachability.md`) : le
> SEUL appelant non porté du canal additional-hits côté prédiction. **Tranches 1 (exécution) et
> 2 (dispatch mêlée) LIVRÉES et validées live (§8, 2026-07-22)** ; reste la tranche 3 (prédiction
> distance). La cartographie RE vient du décompilé (confirmée par le ground truth, pas dérivée).

## 1. Ce que fait l'ability (i2, vérité fonctionnelle)

`tauMarksman` / « Sho'syl » (**lineup**, T'au, move 2, ranged r3), passif `MV71SniperDroneSquad`
(triggered `1119`), constantes `{"unitId": "tauSmnDroneSniper", "maxSummons": "3"}` :

> *Instead of a ranged attack, Sho'syl summons a MV71 Sniper Drone and commands it to attack the
> target. **This attack uses Sho'syl's Damage stat, while other effects, like buffs, are taken from
> the Drone.** If Sho'syl already controls 3 MV71 Sniper Drones, the one with the lowest Health is
> removed before the new Drone is summoned. The target also gains a Markerlight until the end of
> Sho'syl's next turn.*

**L'attaque normale de Sho'syl EST l'ability 1076** — confirmé live : `decisionView` la liste
`{"id": 1076, "name": "MV71SniperDroneSquadAttack", "kind": "normal"}`. Côté natif,
`PredictAttack @18110a5f0` bascule sur `IsMeleeAttack @181109960` : en mêlée elle délègue
intégralement à `ALoki_NormalAttackAbility.PredictAttack`, à distance elle prend le chemin drone.

## 2. GROUND TRUTH live (runner 88, seed 61001, board MC1_67, session 71)

Roster `--p-units tauMarksman,templAncient --a-units astraYarrick --hp-target 30000`.
Tir de `u79` (Sho'syl, @(4,4)) sur `u77` (Yarrick, @(6,6), 30000 PV) via
`applyAction {kind: ability, casterId: 79, targetId: 77, abilityType: 1076}` :

- **Dégât cible : 30000 -> 20609 (−9391) en une action.**
- **Drone invoqué** : entité `u104`, visual `tauSmnDroneSniper`, apparu en **(3,4) — ADJACENT AU
  CASTER** (Sho'syl @(4,4)), *pas* près de la cible @(6,6). (Contraste avec `ScarabHive`, qui
  spawn adjacent à la CIBLE.)
- Tags de spawn : `Unit_Owner_Id: 3` (joueur du caster), `Unit_IsSummoned: 1`,
  `Unit_SpawnSource: 2`, **`Unit_Parent_Id: 79`** (lien de parenté vers Sho'syl — support probable
  du comptage `maxSummons` / de l'éviction), `Unit_Foot_Tile_Id_1: 43`.
- Stats du drone posées au spawn : `MaxHealth 1996`, `MaxArmor 0`, **`FixedArmor 499`**,
  `MaxMembers 1`, **`Attack 2093`**, `Range 0`, `Movement 3`, crit/block 0.
- Abilities posées sur le drone : `ActiveAbility_Id 69` (level 50, multiplicateur 180),
  `TriggeredAbility_Id 1120`.
- Effet posé sur le drone : `Effect_Id 106` = `RangedSpecialist` (`Effect_SourceTrait 1060`,
  source = le drone lui-même).
- **La cible gagne l'effet `Markerlight`** (conforme i2).
- Le drone finit son tour immédiatement (`UnitStats_TurnFinished: 1`).

**Tirs 2 et 3 (mêmes conditions, tours suivants)** — la règle de tuile se confirme :

| tir | dégât cible | drone apparu | tuile | Sho'syl |
|---|---|---|---|---|
| 1 | −9391 (30000 -> 20609) | `u104` | (3,4) | (4,4) |
| 2 | −7972 (16603 -> 8631) | `u110` | (4,3) | (4,4) |
| 3 | −236 (236 -> 0, kill) | `u115` | (5,4) | (4,4) |

⇒ **tuile libre ADJACENTE AU CASTER**, jamais près de la cible. Les drones **persistent et
agissent aux tours suivants** : entre le tir 2 et le tir 3, Yarrick perd 8395 PV supplémentaires
hors de mes actions explicites (les deux drones en jeu ont tiré). Le cap `maxSummons: 3` n'a PAS
été exercé (la cible est morte au 3ᵉ tir) — à valider sur une cible plus dure.

**Le dégât ne vient PAS du stat du drone** : `decisionView` proposait deux plans pour u79,
`[4818-7227]` et `[8487-12729]` ; le dégât réel **9391 tombe dans le second**, très au-dessus de
ce que produirait l'Attack 2093 du drone — cohérent avec « uses Sho'syl's Damage stat ».
Le mécanisme exact (effets `MV71SniperDroneSquad_InitialDmg 1132` / `_ResetInitialDmg 1133`,
`ApplyStat @180f573f0` / `ResetStat @180f57620`) est à lire dans le décompilé, pas à déduire d'ici.

## 3. État du port offline

Ability **1076 absente de `ABILITY_CLASSES`** (`runner/abilities/handler.py`) : tout cast tombe en
**no-op silencieux** (comptabilisé dans `AbilityHandler.unported`). Seules les entrées d'énumération
existent (`active_ability_type.MV71SniperDroneSquadAttack = 1076`,
`triggered_ability_type.MV71SniperDroneSquad = 1119`, `effect_type.MV71SniperDroneSquad_InitialDmg
= 1132` / `_ResetInitialDmg = 1133`, `utility_type.MV71SniperDroneSquad_ClosestToParent = 55`).

Conséquence mesurable : offline, le tir de Sho'syl est traité comme une attaque à l'arme ordinaire
— **aucun drone matérialisé** (donc aucun corps, aucun blocage, aucune attaque des tours suivants),
**aucun Markerlight**, et un dégât calculé sur l'arme de Sho'syl (Piercing r3, `PiercingRatio 80`)
au lieu du chemin drone.

Patron de port visé (voisin direct) : `runner/abilities/loki/summon.py` — arbre DSL + feuille
`SpawnSummon`/`SpawnReplica` déléguant à `SpawnUnitOperation`, classe enregistrée par `ABILITY_TYPE`.

## 4. Levier de validation du canal additional-hits

`AstartesBanner` (`templAncient`, **lineup**, Black Templars) = constantes `{range: 2, extraHits: 1}`,
matérialisé live en effet `AstartesBanner_ExtraHit` sur le porteur. Un drone posté à ≤ 2 hexes de
l'Ancient doit donc porter un `EffectAdditionalHits` pendant son tir — c'est le scénario qui exerce
le couple `GetAdditionalHitsFromEffectsForPrediction @180fb0ed0` /
`AddAdditionalHitsToPrediction @180faff30` sur la branche MV71.

⚠ Piège de scénario rencontré : l'Ancient (mêlée, move 3) fonce au contact et se fait tuer par la
cible — le monter en garde du drone demande de le tenir en retrait (ou de neutraliser la cible).

## 5. RE — la chaîne native (décompilé = vérité)

Contexte `ctx` = struct 0x130 (`memset` @181109630) : **`ctx+0x08` = caster**, **`ctx+0x10` = target**
(prouvé par l'usage dans `PickTile`). Champs d'ability : `+0x18` monde, `+0x20` agrégat de services,
`+0x30` `DSLFactory`, `+0x40` exécuteur, `+0x60` `AbilityConfiguration`.

### 5.1 `ExecuteBehaviour @181108900`

```
if IsMeleeAttack(this, ctx) -> ALoki_NormalAttackAbility.ExecuteBehaviour(...) ; RETURN
tile = PickTile(this, ctx, firstOnly=0)            # @181109ac0 ; null -> RETURN (no-op)
unitId = GetStringConstant(cfg@0x60, 0)            # "tauSmnDroneSniper"
(a) if HasUnitId(tile, unitId) : Execute( RemoveUnit( Units(Get(tile), 1, 3) ) )
(b) sel = AlreadySpawnedSummonsSortedSelector(this)               # @1811087e0
    if HasToManySummons(this, ctx, sel) :                         # @181109870
        Execute( RemoveUnit( First(sel, 1, 0) ) )
(c) spawnR = Execute( Spawn(Caster@0x160, Get(tile), Get(unitId),
                            SpawnUnitOptions.WithStatsFromConfig(cfg, target, 0,0,0)) )
(d) foreach drone in spawnR.list :
        AddEffect(1132 MV71SniperDroneSquad_InitialDmg,      AbilityStateReference, Get(drone))
        AddEffect(1133 MV71SniperDroneSquad_ResetInitialDmg, AbilityStateReference, Get(drone))
        UseActiveAbility( Alive(Get(drone)), Target@0x178,
                          GetNormalAttackType(drone), Nullable<AbilityOrEffect>(1076) x2 )
(e) AddEffect(1122 Markerlight, AbilityStateReference, Caster@0x160, Target@0x178,
              Sum(TurnsFromRounds(1), Direct(1)))              # = fin du prochain tour du caster
```

**C'est le DRONE qui attaque** (`UseActiveAbility` avec **son propre** `NormalAttackType`), l'attribution
du dégât étant forcée à l'ability 1076. L'étape (e) est **dans** le bloc « au moins un spawn » : pas de
drone ⇒ pas de Markerlight. La durée est identique à celle de
`StructuralAnalyser_AddMarkerlightAbility.CreateBehaviour @1811a2a00`.

### 5.2 Le « Damage de Sho'syl, buffs du Drone » = l'effet 1132

`MV71SniperDroneSquad_InitialDmgEffect.ApplyInternal @180f57320` : `parent = GetParentUnit(drone)` puis
`ApplyStat` sur **4 stats — `0 ATTACK`, `9 CRIT_CHANCE`, `10 CRIT_DAMAGE`, `0x11 EXTRA_HITS`**.
`ApplyStat @180f573f0` = `ChangeStat(drone, Position(stat, part 7 = OVERRIDE), mode 4, Direct(valeur
CURRENT du parent))` — un **OVERRIDE**, pas un additif. `ResetStat @180f57620` = même chose en part
`8 = REMOVE_OVERRIDE` à zéro ; `RevertInternal @180f577d0` reverte les 4.
`CreateTargetTrigger @180f575c0` = `On(AttackDamageAttack = 10, 1) & OwnerIsCaster`.
Tout le reste (arme, profil de dégât, traits, auras, buffs) demeure celui du drone — exactement l'i2.

### 5.3 Éviction et tuile

`AlreadySpawnedSummonsSortedSelector @1811087e0` =
`SortByFormula( UnitsWithId( Friends(Self), unitId ), StatAmount(Subject, stat 5 = HEALTH), dir=1 )` ;
`HasToManySummons @181109870` = `sel.Count() >= GetNumberConstant(cfg, 0x3c)` (= `maxSummons` = 3).
L'i2 est confirmé : tri par Health, `First(sel,1,0)` retire le plus faible. Les deux évictions sont
distinctes — (a) libère la tuile choisie quand `PickTile` a rendu celle d'un drone existant, (b) applique
le cap 3 — et **précèdent** le spawn.

`PickTile @181109ac0` : candidates = tuiles autour des tuiles de **la cible** (via la config du drone),
filtrées par `CanAddUnit`, `!IsTilePendingDrafting` et « peut attaquer la cible depuis cette tuile » ;
puis **tri d'utilité** `UtilityBucket[ WeightedUtility(7 = Tile), WeightedUtility(0x37 =
MV71SniperDroneSquad_ClosestToParent) ]`. **C'est ce second terme qui explique le ground truth §2** : parmi
les tuiles d'où le drone (portée 4) peut tirer, celle la plus proche du parent gagne — d'où l'apparition
collée à Sho'syl. Fallback si aucune tuile libre : la tuile **du drone le plus faible**, si adjacente à la
cible, non obstruée et permettant le tir — d'où l'éviction (a).

### 5.4 H53 (« portée minimale ~2 hexes ») — INFIRMÉE

`GetDynamicInvalidTargetReason @181109630` ne contient **aucun** prédicat de distance minimale : le seul
gate dynamique est « il existe au moins une tuile de spawn valide » (`PickTile(firstOnly=1) != null`).
Le comportement observé « pas de drone au contact » vient de `IsMeleeAttack @181109960` : cible adjacente
⇒ l'ability **délègue** à l'attaque normale mêlée, côté exécution **et** côté prédiction. C'est un
dispatch, pas un refus de cible. `.ctor @18110b330` confirme la parenté :
`ALoki_NormalAttackAbility..ctor(this, TargetingOptions.CustomLokiNormalAttackOptions(2), 1, 0)`.

### 5.5 Prédiction, branche distance (`PredictAttack @18110a5f0`)

Clone structurel de `ALoki_NormalAttackAbility.PredictAttack @1811afa50` avec deux substitutions :
l'arme du caster est remplacée par la **config d'attaque du drone** (résolue depuis `unitId`), et les deux
délégués par défaut deviennent des lambdas de la `DisplayClass` — `b__1 @181119590` =
`StatAmount(Caster, ATTACK)` (le dégât de Sho'syl) et un troisième délégué non nommé par ghidra.
`AttackAmount @1811088c0` = `StatAmount(Caster@0x160, ATTACK, CURRENT)` : c'est bien un **montant**, pas un
compte de coups. Le nombre de coups vient de `ExtraHitsComponent(caster).CurrentValue + 1`. Aucune tuile
valide ⇒ **prédiction vide**. Le canal additional-hits s'insère après le retour du service, clé =
`attackTypeId` du drone (identique à ALoki).

## 6. Ouvert / tranché (MAJ 2026-07-22, tranches 1-2)

- **3ᵉ délégué de `PredictAttack`** (`m860`) : TOUJOURS OUVERT (tranche 3). Rôle « compte de coups » =
  INFERENCE. Datapoint discriminant : Sho'syl avec `ExtraHits > 0` vs `0`.
- **Sens du tri** `SortByFormula(..., 1)` : **CONFIRMÉ LIVE** (test cap §8) — au 4ᵉ cast, le drone de
  plus BASSE Health est retiré (évincé identique live/offline).
- **Double éviction** (a)+(b) : au 4ᵉ cast, **exactement 1 drone évincé** live (test cap) — (b) seul
  exercé ; (a) reste réservée au fallback (tuile d'un drone existant), non atteinte à ce jour.
- **`WithStatsFromConfig(cfg, target, …)`** : stats identiques re-validées (1996/2093/499 == live via
  `ability_var(lvl passif 50, mult 180)`) — le 2ᵉ arg (cible) n'influence pas les stats observées.
- **Attribution du dégât** (`UnitDamaged` = 1076 vs NormalAttackType du drone) : non re-vérifiée
  (le replay-diff compare les PV, pas l'attribution) — sans enjeu offline à ce stade.
- **Effet 1133 — skew ARBITRÉ** : le `.ctor @180e1e0f0` (« CyclicIonBlaster_AdditionalHitsEffect »)
  passe `AbilityOrEffect(0x46d)` = **TriggeredAbilityType.CyclicIonBlaster = 1133** (l'ATTRIBUTION
  SOURCE de l'effet CyclicIonBlaster, EffectType 1148) — PAS un EffectType. Le `AddEffect(0x46d)` de
  l'arbre MV71 = EffectType **1133 = MV71SniperDroneSquad_ResetInitialDmg**, conforme à l'enum du dump.
- **Slots de services résolus au passage** : `0xbe` = `GetEffectConfig` (règles BC section `Effect` —
  Markerlight lit l'ordinal 4 = `MarkerlightDmgBonusPct` = 15) ; `0x6b` = distance entre deux tuiles
  (consommé par SpawnTileUtility) ; `0x79` = unités adjacentes à une tuile filtrées par relation
  (amis/ennemis d'une unité de référence). Restent inconnus : `0xaa`/`0x66`/`0xc0`/`0xc3`/`0x24`.

## 7. Plan de port (tranches)

1. **Exécution** — **LIVRÉE + VALIDÉE** (§8).
2. **Dispatch mêlée** — **LIVRÉ + VALIDÉ** (§8 ; exécution seule — la face prédiction du dispatch va
   avec la tranche 3).
3. **Prédiction distance** — RESTE À FAIRE : substitution config d'arme du drone + dégât
   `StatAmount(caster, ATTACK)` + coups `1 + ExtraHits(caster)`, puis canal additional-hits (déjà
   porté pour ALoki) ; « aucune tuile valide ⇒ prédiction vide » ; + threading du % Markerlight dans
   la face prédiction des defender-mods.

## 8. Tranches 1-2 livrées (2026-07-22) — port + validation live

**Port** (fichiers) :
- `engine/runner/abilities/loki/mv71.py` — `MV71SniperDroneSquadAttackAbility` (1076, enregistrée au
  handler) : dispatch mêlée (délégation attaque normale), `_pick_tile` (candidats libres à portée-4 de
  la cible ; score = **Tile(7) porté** (`utilities/tile.py`, élévation active) + **utilité 0x37**
  `_spawn_tile_utility_0x37`), évictions (a)/(b), spawn `_spawn_config_grot(cfg MV71SniperDroneSquad,
  niveau PASSIF du caster)`, AddEffect 1132/1133, attaque commandée (`AttackDamageOperation.execute`
  du DRONE — les overrides passent par GetStat), consommation 1132/1133 + revert, flags de tour du
  drone, Markerlight durée `turns_from_rounds(1)+1`.
- `entities/stats.py` — `StatComponent.apply_override/remove_override` + `UnitStats.set_stat_override/
  remove_stat_override` (mirror `ApplyModifier @180fa8800` parts **7/8** → `SetOverride @180faea70` /
  `RemoveOverride @180fae930` — part-switch RE-confirmé) ; `runner/operations/stat_ops.py` —
  `apply_stat_override`/`remove_stat_override`.
- `entities/effects/loki/status.py` — `MV71InitialDmgEffect` (DATA `overridden_stats()` = ATTACK/
  CRIT_CHANCE/CRIT_DAMAGE/EXTRA_HITS) + `MV71ResetInitialDmgEffect` ; `AddEffectOperation.
  _apply_stat_overrides` (snapshot `GetStat(parent=source, CURRENT)` à l'apply, **modifiable** — les
  buffs du drone s'appliquent par-dessus, i2) + `revert_stat_overrides`.
- `entities/effects/loki/damage_reduction.py` — `MarkerlightEffect` : `CreateDamageModifier @180f58170`
  = `OwnerIsTarget & HasFaction(actor, 9=T'au) & IsRangedAttack → ForPercentIncrease(
  MarkerlightDmgBonusPct=15)` (règle GLOBALE BC `Effect`, slot 0xbe = GetEffectConfig(4)) ; gate
  faction threadé par `damage_model.defender_modifiers` (att_ctx["faction"]).
- `runner/abilities/behaviours.py` — feuille `RemoveUnit` (`DSLFactory.RemoveUnit @180df9fd0` →
  `RemoveUnitBehaviour.Execute @180fce1d0` : despawn SANS vecteur on-death).

**RE complémentaire** (décompilé, VAs) : `ExecuteBehaviour @181108900` re-lu 1:1 (AddEffect 0x46c/0x46d,
`UseActiveAbility(GetNormalAttackType(drone), attribution 2× AbilityOrEffect(1076))`, Markerlight
`Sum(TurnsFromRounds(1), Direct(1))`) ; `PickTile @181109ac0` intégralement décodé (candidats slot 0x66
sur les tuiles de la CIBLE × config drone slot 0xaa, filtres CanAddUnit/!PendingDrafting/slot 0xc3,
`firstOnly` = 1er candidat = gate de GetDynamicInvalidTargetReason, fallback au cap seulement) ;
`MV71SniperDroneSquad_SpawnTileUtility <d__5>.MoveNext @181100f60` = `-steps(cand→parent) ×
W[AdjacentToParent=50] + W[NoAdjacentEnemy=40] si aucun ennemi adjacent + par ami adjacent :
W[InRangeOfStructuralAnalyser=3]/W[InRangeOfDefenderOfTheGreaterGood=25] (gate aucun-ennemi-adjacent)
+ W[AdjacentToTau=20] si `CanBeProtector @1810e0a50` (= T'au ET PAS SaviorProtocols 0x460)` — poids BC
catégorie `MV71SniperDroneSquad_ClosestToParent` (⚠ 2 sous-clés portent le typo natif « DDrone ») ;
`ChangeStatBehaviour.Execute @180fbfb10` mode 4 décodé (StatModifier + Position(part) → Transform).

**Validation** (`tests/engine/runner/test_mv71_sniper_drone_live.py`, 3 tests, replay-diff MT seedé) :
1. cast à distance : TUILE du drone == live (le bucket Tile(7)+0x37 reproduit le choix natif — le
   collapse « distance seule » divergait, (4,7) vs (3,6)), stats 1996/2093/499, **dégât commandé
   bit-exact**, Markerlight posé, 1132/1133 consommés + overrides revertés (ATTACK du drone == propre) ;
2. cap/éviction : 4ᵉ cast → le plus faible évincé (identique live/offline), tuile du 4ᵉ drone exacte,
   3 drones des deux côtés ;
3. dispatch mêlée : dégât == attaque normale (bit-exact), AUCUN drone, AUCUN Markerlight.
Gardes de non-régression : `test_damage_roll_live` + `test_effect_stun_live` (3/3 PASS).

**Résidus flaggés (non bloquants)** :
- LoS (`UnobscuredTiles`/slot 0xc3 complet) non portée dans `_pick_tile` (MC1_67 ouvert ; boards à
  obstacles → à porter) ; `steps` = distance hex (== pas sur board ouvert) ;
- l'énumération native des candidats (slot 0x66) n'est pas RE'd — tie-break stable par id de tuile,
  aucun tie observé sur les 2 scénarios validés ;
- consommation de 1132/1133 exécutée par l'ability après l'attaque commandée (le SEUL On(10) du
  porteur atteignable dans le cast) — PAS câblée aux attaques AI-turn (un drone qui n'attaquerait pas
  au cast garderait l'effet offline) ;
- Markerlight : retrait au HEAL/REPAIR non porté (durée seule) ; % non threadé dans la face
  PRÉDICTION (tranche 3) ; contribution combat active (att_ctx faction) mais non exercée par un
  datapoint dédié (tir de drone ULTERIEUR sur cible marquée = AI-turn replay, hors tranche 1).
