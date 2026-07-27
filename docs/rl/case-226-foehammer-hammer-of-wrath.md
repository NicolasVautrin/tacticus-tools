# case-226 — Foehammer (1097) et HammerOfWrath (1153), profil POWER

Deux actives NO-OP offline (absentes d'`ABILITY_CLASSES`) portées en arbre DSL, plus **un gap
cross-cutting** qu'elles ont révélé (mods ATTAQUANT de la famille ABILITY) et **un gap de seed**
(traits d'un cadavre). Build ghidra `gqfc5mff6c`.

---

## 1. Foehammer — 1097, `spaceRockfist` « Arjac » (Space Wolves)

`IdunBattleLogic.Entities.Abilities.Active.Loki.FoehammerAbility$$ExecuteBehaviour`, MIRROR 1:1 :

```
Execute( op_Addition(
    AddEffect( 0x48a = Stunned, AbilityStateReference, source = Self@0x148,
               cible = Target@0x178, duree = TurnsFromRounds(1) ),
    AttackWithAttackDamage( caster@0x160, target@0x178,
        degat = Sum( MinMaxDamage(minDmg 0xc / maxDmg 0xd),
                     Multiply( Direct(GetVariableForLevel(config, 8 = extraDmg)),
                               Count(GetDeadHeroes) ) ),
        GetDamageProfile(config) = Power, GetNumberConstant(0x2f) = nrOfHits = 1,
        AbilityOrEffect(this@+0x10 = 1097) ) ) )
```

* `FoehammerAbility$$GetDeadHeroes` = `UnitsWithTrait(AllDeadOrResurrectedUnits, 0x10 = Hero)` —
  **aucun filtre d'équipe** (le « each Character that has been defeated » de l'i2 compte les héros
  des DEUX camps).
* Famille **ATTACK** : l'`ExecuteBehaviour` appelle `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
  (2 tirages/coup à cc=0). `attackRangeType = Ranged` (range 2) → `is_melee=False`.
* Le `2183` du tooltip = `variables.extraDmg[65]` de la config 1097 — LU par `ability_var`, jamais
  codé en dur (le niveau du runner n'est pas 65).
* `Stunned` (composite 1162) est posé AVANT l'attaque ; il est INERTE pour ce coup (son enfant
  `Stunned_DamageModifier` 1167 est un `ForPercentDecrease` gaté `OwnerIsActor` = dégât SORTANT du
  stunné, or la cible est DÉFENSEUR ici) et déterministe → l'ordre `state.rng` de l'attaque est
  inchangé.

Port : `engine/runner/abilities/spacewolves.py::foehammer_tree` / `FoehammerAbility`.

### Masque de ciblage

`FoehammerAbility$$.ctor` **n'appelle pas** `TargetingOptions..ctor` : il COPIE VERBATIM un preset
statique (champs statiques `TargetingOptions +0x140..0x17f`) puis `AActiveAbility..ctor(this,&opts,0)`.
Masque effectif LU dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
`*(statics + 0x168) = 0x4002` = `TargetMatchesDynamicRule(0x2) | TargetIsEnemy(0x4000)`. Ce n'est
PAS l'overload « preset + flags » (aucun flag OR'é après la copie). Foehammer ne surcharge PAS
`GetDynamicInvalidTargetReason` → le défaut 0 du port est fidèle.

`ABILITY_ATTACK_TYPE` (l'autre donnée obligatoire du registre) : `FoehammerAbility$$.ctor` =
`AActiveAbility..ctor(this, &opts, 0, 0)` → 3ᵉ argument **0 = DirectTargetAttack**.

---

## 2. HammerOfWrath — 1153, `bloodIntercessor` « Mataneo » (Blood Angels)

`IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$ExecuteBehaviour`, MIRROR 1:1 :

```
Execute( op_BitwiseAnd( op_BitwiseAnd(
    AddEffect( 0x416 = Infiltrate_UnitEffect, AbilityStateReference, Self@0x148, Self@0x148,
               duree = Direct(1)@dsl+0xc0 ),                                        # [1] en TOURS
    MoveUnit( caster@0x160,                                                          # [2] CHARGE
        First( SortTilesByUtility(
                 Filter( CanAddUnit(AdjacentTiles(target@0x178)),
                         NOT( AmountIsGreater( MinDistance(It@0x180, CasterTiles@0x170),
                                               Get(GetNumberConstant(0x16 = range)) ) ) ),
                 caster@0x160, UtilityDefinition(7 = Tile) ), 1 ), <options ZEROEES> ) ),
    If( IsAlive(caster@0x160),
        AtomicGroup( 0x1d, op_BitwiseAnd(
            AttackWithAbilityDamage( caster, target@0x178, GetDamage,  Power,    GetHits ),      # [3]
            AttackWithAbilityDamage( caster, GetAdjacentTargets, GetDamage2, Physical,
                                     GetHitsToBonusTarget ) ) ) ) ) )                            # [4]
```

* `GetDamage`  = `ConditionalAmount( GetDoubleCondition, Multiply(MinMaxDamage,  Get(2)), MinMaxDamage )`
* `GetDamage2` = idem avec `MinMaxDamage2` (`minDmg_2`/`maxDmg_2`, profil `damageProfile_2` = Physical)
* `GetDoubleCondition` = `HasEffect(Self@0x148, 0x534 = HammerOfWrath_ConditionalDamage, activeOnly=1)`
* `GetAdjacentTargets` = `Enemies( caster@0x160, AdjacentUnits(target@0x178, 1) )`
* `GetHits` / `GetHitsToBonusTarget` : corps DÉDUPLIQUÉS IL2CPP (ghidra les affiche
  `ArmoriumCherubAbility$$GetHits` / `BringerOfDespairAbility$$GetHitsToBonusTarget`) =
  `GetNumberConstant(0x2f)` et `GetNumberConstant(0x32)` — structure LUE, jamais le nom.
* Famille **ABILITY** (`AttackWithAbilityDamage` → `AbilityDamageOperation`, 1 tirage/coup, aucun crit).

**Le `Multiply(MinMaxDamage, 2)` double les BORNES, pas la valeur tirée** :
`IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$GetDamage` teste si le nœud de dégât
implémente l'interface min/max et, si oui, appelle ses slots `CalculateMin`/`CalculateMax` — or
`MultiplyAmount` et `ConditionalAmount` implémentent tous deux ces slots (symboles
`MultiplyAmount$$CalculateMin/Max`, `ConditionalAmount$$CalculateMin/Max`).

**`HammerOfWrath_ConditionalDamage` (1332)** = owner-effect PERMANENT posé à l'INIT de l'ability par
la triggered 1258 (`AOwnerEffectTriggeredAbility$$CreateBehaviour` = `If(cond, AddEffect(effectType,
AbilityState(owner), owner, owner, <durée ZÉROÉE>))`, trigger `OnOwnerSpecificAbilityInit`), dont
l'`ActiveCondition` est
`HealthPctIsBelowOrEqual( Self, ConfigConst(1153, Self, 0x4f = healthPct) )` — soit le MÊME patron
qu'`AnvilShield_BlockChanceBelowHealthCap` (entité-effet permanente, seul `IsActive` bascule, donc
ABSENTE du seed live tant que la condition est fausse). Porté :
`entities/effects/loki/status.py::HammerOfWrathConditionalDamageEffect` +
`ABILITY_INIT_OWNER_EFFECTS["HammerOfWrath"]`.

⚠ Le « **If Mataneo has not moved** » de l'i2 n'est PAS une branche de l'`ExecuteBehaviour` (l'`AddEffect`
Infiltrate y est INCONDITIONNEL) : c'est la règle de ciblage `CasterHasNotMoved` (0x10) du masque.

Port : `engine/runner/abilities/bloodangels.py` (2e section).

### Masque de ciblage + règle dynamique

Même schéma que Foehammer (copie d'un preset statique, `TargetingOptions +0x240..0x27f`) ; masque LU :
`*(statics + 0x268) = 0x102004032` =
`TargetMatchesDynamicRule(0x2) | CasterHasNotMoved(0x10) | TargetHasFreeAdjacentTile(0x20) |
 TargetIsEnemy(0x4000) | AllowObscuredTargetByElevation(0x2000000) | bit32(0x100000000)`.

`ABILITY_ATTACK_TYPE` : `HammerOfWrathAbility$$.ctor` = `AActiveAbility..ctor(this, &opts, 0, 0)` →
3ᵉ argument **0 = DirectTargetAttack**. Garde-fou `probe_120` étape 0 vert après rebase : 81 abilities
au registre, **aucun** littéral de ctor manquant.

`HammerOfWrathAbility$$GetDynamicInvalidTargetReason` (+ sa lambda
`<>c__DisplayClass8_0$$<GetDynamicInvalidTargetReason>b__0`) :

```
dc.ability = this ; dc.<0x18> = <casterTiles> ; dc.range = GetNumberConstant(0x16)
tiles = battleQuery.<slot 0x52>(<target>)
return (tiles != null && Any(tiles, t => battleQuery.<slot 0x6c>(t, dc.<0x18>) <= dc.range)) ? 0 : 0x20
```

→ porté en réutilisant le MÊME sélecteur que la charge (`hammer_of_wrath_dest_tile`).

### Résidu NOMMÉ — le natif refuse EN PLUS une cible DÉJÀ ADJACENTE

Sweep MESURÉ (MC1_67, u83 déplacé autour de Mataneo @(4,7), 3 ennemis écartés du champ) :

| position cible | d(caster,cible) | `abilityTargets.fromHere` |
|---|---|---|
| (4,8) | 1 | **refusé** |
| (5,7) | 1 | **refusé** |
| (6,6) | 2 | accepté |
| (2,7) | 2 | accepté |
| (1,7) | 3 | accepté |
| (0,7) | 4 | accepté |
| (0,3) | 6 | accepté |

La bande acceptée est `d >= 2` — et PAS `d <= range` (d=6 passe : la contrainte `MinDistance(tuile,
CasterTiles) <= range` porte sur la TUILE de charge, pas sur la cible). **Aucune lecture de la lambda
ci-dessus ne produit ce refus à d=1** (les tuiles libres du ring-1 y sont à distance ≤ 2 du caster,
donc `Any` est vrai). Le refus vient donc d'un AUTRE étage de la cascade statique — HYPOTHÈSE : le bit
**0x100000000** (bit 32, `prédicat battleQuery slot 0x61 sur les tuiles`), que `WaaaghAbility` (l'autre
ability de CHARGE portée) porte aussi et qui n'y est pas porté non plus. **Non implémenté** : c'est une
règle PARTAGÉE de la cascade et je n'ai de mesure que sur UNE ability ; l'implémenter globalement
risquerait de régresser Waaagh (live-validé sans elle). Le port ACCEPTE donc un cast sur une cible déjà
adjacente que le natif REFUSE (permissif — même classe de résidu que toutes les règles non portées de
`targeting.py`). **Candidat de suivi.**

### `SortTilesByUtility(UtilityDefinition(7 = Tile))` — collapse REFUTÉ, mirror rétabli

Les ports frères (`SkyStrikeAbility`, `HeroicFusilladeAbility`, `ForwardSpotterAbility`) collapsent ce
sélecteur en « la tuile la plus PROCHE du caster ». **Mesure (MC1_67, Mataneo @(4,7), cible @(6,7))** :
les deux tuiles libres du ring-1 sont (5,7) elev 1 (distance 1) et (6,6) elev **2** (distance 2) — le
natif charge sur **(6,6)** (`Unit_Foot_Tile_Id_1 = 72`), donc sur la plus ÉLEVÉE. Le collapse
« plus proche » est donc FAUX sur ce call-site.

Le port appelle désormais le composite **Tile(7) DÉJÀ PORTÉ** (`engine/utilities/tile.py::TILE_UTILITY`,
29 feuilles) : sur une carte plate toutes les feuilles rendent 0 sauf `ElevationUtility`
(BC `Elevation.Multiplier=10`, `HighestElevation=+10`, `LowestElevation=-5`), min/max d'élévation sur le
**BOARD ENTIER** (mirror `ElevationUtility$$LoadRelevantTileElevations`). Tri DÉCROISSANT **stable** →
l'ordre du sélecteur (`board.neighbours(tuile-cible)`) tranche les égalités. Les trois ports frères
gardent leur ancien collapse (hors périmètre — candidat de suivi).

---

## 3. Gap cross-cutting RÉVÉLÉ — mods ATTAQUANT de la famille ABILITY (fix)

`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` ne construit **QUE** les mods
DÉFENSEUR (slot d'interface 0xf) et passe à `CalculateBaseDamageWithAllModifiers` un `DamageModifiers`
ATTAQUANT **memset à 0** (`local_498..uStack_460 = 0` juste avant l'appel) : il n'existe AUCUN appel à
`CalculateAttackerModifiersForPrediction` sur ce vecteur.

#45f avait déjà gaté les feuilles POSITIONNELLES (élévation/trench) et les threads `is_ranged` /
`trigger_ability_type` / `target_traits` sur cette base, mais les bonus attaquant issus des EFFETS
**non gatés** (et les auras alliées) continuaient de passer — invisible tant qu'aucun porteur
ability-family n'en avait.

**Discriminant MESURÉ** : Mataneo porte le trait `RapidAssault` → effet 1229
`ForPercentIncrease(get_OwnerIsCaster, 25)` SANS aucun gate. Offline = `round(live × 1.25)` sur les
4 coups des DEUX volets (main 1930/1544, 2144/1715 ; splash 2309/1847, 2415/1932). Struct zéroée →
bit-exact. Fix : `runner/operations/damage_ops.py::execute_ability_attack`, `mods = DamageModifiers()`
quand `is_attack_damage_op` est faux.

## 4. Gap de seed RÉVÉLÉ — les traits d'un CADAVRE (fix)

`_load_stats_and_effects` ne pose un `StatsComponent` que pour les entrées de `combatSnapshot.units`,
dont une unité MORTE est absente — alors que `decisionView` la garde et que le natif teste bien les
flags d'une entité morte (`UnitsWithFlagSelector` sur `AllDeadUnitsSelector`). Conséquence mesurée :
`Count(UnitsWithTrait(AllDeadOrResurrectedUnits, Hero))` rendait **0** avec un héros mort au sol
(live 2142 vs port 343). Fix : repli gameconfig dans
`runner/abilities/behaviours/context.py::_unit_dict` — la source du repli est EXACTEMENT celle du
chemin vivant (`UnitContext.traits = gameconfig.unit(vis).traits`).

---

## 5. Validation live

Harnais : `scripts/python/probe_226_hammer_foehammer.py` (rosters + PV patchés PAR VISUAL-ID, ce que
`rl_duel --hp-target` ne sait pas faire). Tests de garde :
`tests/engine/runner/test_foehammer_live.py`, `tests/engine/runner/test_hammer_of_wrath_live.py`.

### Foehammer — 2 cas discriminants, MÊME cible, MÊME runner

| board / seed | cas | héros morts | live | offline |
|---|---|---|---|---|
| MC1_67 / 226226 | A | 0 | **365** | 365 |
| MC1_67 / 226226 | C | 1 | **2142** | 2142 |
| C3_01 / 31337 | A | 0 | **255** | 255 |
| C3_01 / 31337 | C | 1 | **1707** | 1707 |

(le cast intercalaire B tue le héros sacrifiable `orksNob`, monté à 100 PV / armure 0 ; son `Amount`
live est clampé aux PV restants — exclu de la comparaison, même convention que
`test_great_frost_axe_live`.) `Stunned` posé live (groupe d'effet dans les events) et côté port.

### HammerOfWrath — 2 cas discriminants (PV pleins / ~33 %), 2 volets par cast

| board / seed | cas | 1332 actif | volet | live | offline |
|---|---|---|---|---|---|
| MC1_67 / 226226 | A | non | main 2× Power | 1544, 1715 | 1544, 1715 |
| | | | splash u77 / u81 | 1847 / 1932 | 1847 / 1932 |
| MC1_67 / 226226 | B | oui | main 2× Power | 5278, ~~3258~~ | 5278, ~~5787~~ |
| | | | splash u77 / u81 | 5697 / 5721 | 5697 / 5721 |
| C3_01 / 31337 | A | non | main / splash | 1427, 1740 / 1923 | idem |
| C3_01 / 31337 | B | oui | main / splash | 5642, ~~2894~~ / 4460 | 5642, ~~4429~~ / 4460 |

(~~barré~~ = coup CLAMPÉ par la mort de la cible : le tag `Amount` est le dégât APPLIQUÉ, le `per_hit`
offline le dégât DEMANDÉ — exclu de la comparaison.) Tuile de charge : port == position live du
caster après le cast, sur les DEUX boards.

### Non couvert

* Le refus natif d'une cible DÉJÀ ADJACENTE (§2, résidu nommé) — le port l'accepte.
* La face COMBAT de `AggressiveOnslaught` (triggered 1248, 2 `bloodSmnIntercessor` invoqués quand
  Mataneo charge) : NON portée (seule sa face DÉCISION l'est). Elle ne pollue PAS le flux `state.rng`
  des coups de HammerOfWrath — son trigger est
  `On(0xb = UnitAbility) & OwnerIsCaster & (IsPersistentData | IsCharging)` et `On(0xb)` est émis par
  `ActiveAbilityOperation$$ExecuteInternal` **après** l'exécution de la behaviour (vérifié dans les
  events : le groupe `AggressiveOnslaught` et le spawn arrivent après les 4 coups).
* `Infiltrate_UnitEffect` (1046) : posé, mais sans classe d'effet portée (`BaseEffect` nu) — aucun
  terme de dégât n'en dépend.
* Crit / block sur ces deux abilities : non exercés (cc=0 sur les porteurs testés).
* Les tests `test_hailstrike_phase2_live.py` échouent — **échec PRÉEXISTANT**, vérifié en rejouant le
  fichier avec le `damage_ops.py` d'`origin/master` : mêmes valeurs (live 2700 hors de [1688, 2532]).

## 6. Re-jeu après rebase sur `137ef85` (PR #129 + #132 + #133 mergées entre-temps)

Deux rebases successifs (conflits `factory.py` / `loki/__init__.py` résolus en **union** : les effets
`DestroyTheWitch*` de #129 et `HammerOfWrath_ConditionalDamage` coexistent). Le gate ACTEUR-MORT
POST-`On(0x2b)` de #129 (`handler.py`) et le fix « mods attaquant famille ABILITY » de ce lot
(`damage_ops.py`) sont tous deux présents — surfaces disjointes du même fichier.

Tests rejoués **sur la base finale** : `test_foehammer_live`, `test_hammer_of_wrath_live`,
**`test_martial_superiority_live`**, **`test_destroy_the_witch_live`** (13 passed) ;
`test_spirit_leech_combat_live`, `test_great_frost_axe_live`, `test_ability_target_gate_live`
(15 passed) ; `probe_120_pre_unit_ability_fork` OK.
