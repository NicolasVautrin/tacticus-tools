# Case #61bis — MV71SniperDroneSquadAttack (1076) : port de l'attaque déclenchée du Marksman

> Successeur de #61 (clos sans port — `case-61-additional-hits-prediction-reachability.md`) : le
> SEUL appelant non porté du canal additional-hits côté prédiction. **En cours** — la
> cartographie RE est déléguée ; ce document collecte d'abord le GROUND TRUTH live (confirmation,
> pas dérivation : la mécanique vient du décompilé).

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

## 6. Ouvert (à trancher au portage / par datapoint live)

- **3ᵉ délégué de `PredictAttack`** (`m860`) : rôle « compte de coups » = INFERENCE (ghidra ne nomme que
  `b__0`/`b__1` de la `DisplayClass`). Si c'en est un autre, la prédiction distance est fausse d'un facteur
  `1 + ExtraHits`. Datapoint discriminant : Sho'syl avec `ExtraHits > 0` vs `0`.
- **Sens du tri** `SortByFormula(..., 1)` : que ce soit bien le drone de plus BASSE Health qui saute reste
  à confirmer live (le cap 3 n'a pas encore été exercé — §2).
- **Double éviction** (a)+(b) : peut-elle retirer DEUX drones ? En lecture statique (a) retire le drone de
  la tuile, donc (b) devrait être faux ensuite — à prouver.
- **`WithStatsFromConfig(cfg, target, …)`** : le 2ᵉ argument est la CIBLE, contre-intuitif pour un spawn —
  vérifier que les stats du drone n'en dérivent pas. (Ground truth §2 : stats identiques aux 3 spawns,
  cible constante — non discriminant en l'état.)
- **Attribution du dégât** : vérifier que `UnitDamaged` live rapporte l'ability **1076** et non le
  `NormalAttackType` du drone.
- **Effet 1133** : skew de nommage non arbitré — le seul `.ctor` passant `0x46d` est `@180e1e0f0`, que
  ghidra nomme `CyclicIonBlaster_AdditionalHitsEffect`, alors que `entities/effect_type.py` donne
  1133 = `MV71SniperDroneSquad_ResetInitialDmg` (et `CyclicIonBlaster_AdditionalHits = 1148`). L'ancre de
  contrôle est saine par ailleurs (`MarkerlightEffect..ctor @180f583b0` passe bien 0x462 = 1122). Le
  comportement de 1133 dans MV71 reste **non lu**.
- **Slots vtable non résolus** de l'agrégat de services `DAT_18327ff80` : `0xaa` (config d'unité), `0x66`
  (tuiles candidates), `0xc0` (config d'attaque par unitId), `0xc3` (peut-attaquer-depuis-tuile), `0x24`
  (service de prédiction) — appels indirects, noms natifs inconnus.

## 7. Plan de port (tranches)

1. **Exécution** (cœur de l'agreement d'état) : feuille `RemoveUnit` (absente — seul `KillDeadUnits`
   existe), arbre `mv71_sniper_drone_squad_attack_tree()` mirrorant §5.1, effet 1132 (4 OVERRIDE depuis
   le parent — nécessite de brancher `ValueOverride` / `StatPart.OVERRIDE=7` / `REMOVE_OVERRIDE=8`, déjà
   définis dans `entities/stats.py`, la feuille `ChangeStat` actuelle ne gérant que l'additif), Markerlight
   1122, et `PickTile` en helper impératif (filtres + tri d'utilité collapsés, doctrine FinalJustice) en
   gardant le fallback sous peine de rendre l'éviction (a) injoignable.
2. **Dispatch mêlée** (exécution ET prédiction) : délégation à l'attaque normale — supprime le faux
   « min-range » de H53.
3. **Prédiction distance** : substitution config d'arme du drone + dégât `StatAmount(caster, ATTACK)` +
   coups `1 + ExtraHits(caster)`, puis canal additional-hits (déjà porté pour ALoki).
