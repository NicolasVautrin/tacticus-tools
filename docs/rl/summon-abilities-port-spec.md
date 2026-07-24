# Summon active abilities — PORT SPEC (RE re-expert, build gqfc5mff6c)

Retour du re-expert (#65 SLICE 2 part c' = apply des abilities actives des summons). Base : le chemin
`engine/runner/operations/summon_ai.py::_apply_active_ability` route (1) port DÉDIÉ via `AbilityHandler`/
`ABILITY_CLASSES` (`handler.py` : 1043 ThunderousAssault, 1206 GravitonRifle, 1007 ScarabHive,
1105 CrushingClaws) ; sinon (2) GÉNÉRIQUE `AttackDamageOperation.execute_ability_attack` (attaque active à
`damageProfile`, config via `ability_attack_params`) ; sinon (3) no-op.

## ⚠ ScarabHive (1007) ≠ ScarabSummon (1047) — DEUX abilities, ne PAS les confondre (RE ghidra + gameconfig)

Piège de nommage corrigé (#65) : le port a longtemps eu UNE classe `ScarabSummonAbility` (id 1007, VA citée
`@181205290`) qui portait EN FAIT **ScarabHive**. Les deux abilities sont distinctes et TOUTES DEUX spawnent
`necroSmnSwarm` mais par des chemins différents :

| Ability | id | VA native | Porteur | Placement | Owner+stats | On-appearance |
|---|---|---|---|---|---|---|
| **ScarabHive**  | 1007 | `ScarabHiveAbility.ExecuteBehaviour @181204cb0` | necroSpyder (SUMMONER) | `First(SortByDistance(CanAddUnit(AdjacentTiles(target@0x178)), self@0x160))` = adjacent **CIBLE** | `WithStatsFromConfig(config)` → stats **summoner-scaled** `ability_var(ScarabHive, summon*, casterLevel, mult)` | `UseNormalAttackIfAble` |
| **ScarabSummon** | 1047 | `ScarabSummonAbility.ExecuteBehaviour @181205290` | necroSmnSwarm (le SCARAB, auto-DÉDOUBLEMENT) | `PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)))` = adjacent **SOI** | `CopyOwner(caster)` → owner + **stats CLONÉES du parent** | `PerformAIAttack` (« immediately takes a turn ») |

- **`CopyOwner @180fd5ba0` copie des STATS, pas juste l'owner** (RE) : il bâtit une liste
  `StatAmount(caster, statType, StatPart=3)` pour les StatType `{5=Health, 16=Armor, 0=Attack, 1=Movement, 20}`
  puis `CreateSpawnOptions(owner)`. ⇒ le scarab auto-dédoublé est un **clone** du parent (mêmes Attack/Move/HP/
  Armor), PAS un `ability_var(ScarabSummon,…)` (qui n'existe pas — `ScarabSummon.constants` = `{unitId, chance:50}`).
- **Le scarab n'est JAMAIS apparition-only** : trait `Summon` = « Moves and attacks automatically at the beginning
  of its turn » → joué au TURN-START via `run_ai_control_pass` (chemin SÉPARÉ de `PickNextUnit`/`aiStepDryRun`).
  Le gate défensif `_APPEARANCE_ONLY_SUMMON_ABILITIES` (qui mettait ScarabHive → `ai_controlled=False`) était
  FAUX (basé sur un « 0 action » via `aiStepDryRun`, un artefact de sonde) → **retiré #65** : tous les summons =
  `ai_controlled=True`. Playbook du dédoublement = `ScarabSummonPlaybook` (`GetUseProbability` = 1.0 ou 1/2 selon
  un compteur runtime ; utilité 3/2 par cible éligible).
- **PORTÉ + VALIDÉ LIVE (#65)** : ScarabSummon (1047) = classe `ScarabSummonAbility` (`loki.py`,
  `SpawnUnitOperation.execute_self_replica`) + `ScarabSummonPlaybook` (`noncomparable/scarab_summon.py`, NC prio 0, util 1.5)
  + registre `ABILITY_CLASSES`/`PLAYBOOKS`. **Confronté live** (necroSpyder vs 2 healers) : le count de scarabs
  snowball 2->3->5->6->8 (auto-dédoublement natif), tous hpMax=2218 IDENTIQUES (clone). Offline : l'auto-play
  décide ScarabSummon(1047) pour chaque scarab, `execute_self_replica` produit un clone hp=2218/atk=998 adjacent
  au parent, ai_controlled=True (récursif). GAP restant : `GetUseProbability` (RNG 50%) + cap `UnitDuplicationLimit`
  non modélisés (le port se dédouble à chaque tour dès qu'une tuile ring-1 est libre).

## Auto-DÉDOUBLEMENT : 2 mécanismes DISTINCTS (scan exhaustif 55 summons, actives ET passives)

**SEULS 2 summons se ré-invoquent EUX-MÊMES** — et par des chemins différents (ne PAS généraliser l'un à l'autre) :

| | **ScarabSummon** (necroSmnSwarm) | **PileIn** (orksGrot) |
|---|---|---|
| Nature | **active** (l'IA décide en tour, playbook `ScarabSummonPlaybook`) | **passive** = TRIGGER fin-de-tour (`PileInAbility` @181223990/@181223c50) |
| Gate | `GetUseProbability` ~50% | `On(0x17 fin-de-tour)` & `OwnerHasFinishedMinTurns(2)` & PV PLEINS (`IsUnitWithStatAmount(Health Cur==Max)`) & `Maybe(75 − 5×#grots)%` |
| Stats du double | `CopyOwner @180fd5ba0` = **CLONE du parent** (Attack/Move/Health/Armor du parent) | `WithStatsFromConfig(config)` = **stats de base config** (2910 PV / 1455 dmg), PAS un clone |
| Placement | `PickRandomly(CanAddUnit(AdjacentTiles(self)))` | `First(SortByFormula(Randomize(CanAddUnit(AdjacentTiles(self)))))` |
| À l'apparition | `PerformAIAttack` (attaque IMMÉDIATE) | agit à son PROCHAIN tour (pas d'attaque immédiate) |

- **PileIn PORTÉ (#65)** : c'est un TRIGGER fin-de-tour (`triggers.end_turn_summon_triggers` appelé par
  `EndTurnOperation`), PAS une active+playbook. `SpawnUnitOperation.execute_pilein_replica` = spawn grot
  `WithStatsFromConfig(PileIn)` = `ability_var(PileIn, summon*, level, mult)` (PAS `CopyOwner`). Constantes :
  `GetStringConstant(0x46)`=summonId(orksGrot), `GetNumberConstant(0x2a)`=chance(75), `(0x33)`=chance_2(5).
  Gates : owner a fini >=2 tours (`OwnerHasFinishedMinTurns(2)` -> `turn_counts>=2`), grot à PV PLEINS
  (`IsUnitWithStatAmount(Health Cur==Max)`), proba `75 − 5×#grots amis` (RNG `Maybe` non modélisé -> fire si
  chance>0 ; cap naturel n=15). Stats confirmées : `ability_var(PileIn,summonHp,65,100)=2910`,
  `ability_var(GetEmRuntz,...)=4802` (== tooltips) -> PileIn grot = ~0.606× le grot GetEmRuntz, PAS un clone.
  **VALIDÉ OFFLINE** (grot lvl50/mult200 injecté : trigger fire à PV pleins & >=2 tours, produit un grot hp=4432
  =config ≠ parent 7312, adjacent, ai_ctrl ; gates PV-pleins/<2-tours refusent). GAP RESTANT : observation LIVE
  isolée impraticable (GetEmRuntz/SquigHound/PileIn spawnent TOUS des grots + condition PV-pleins) -> on s'appuie
  sur le décompilé (=vérité) + match tooltip + validation offline. Autres traits grot : `Diminutive` — **PORTÉ
  + VALIDÉ LIVE (#75)** : trait 0x408=1032 -> triggered ability 0x43f=1087 (`DiminutiveAbility` @180e20c80)
  -> owner-effect `Diminutive_HitReduction` (@180f3f550, hits @180f3f3c0) = **-1 coup sur TOUTE attaque
  reçue** (mêlée ET ranged), plancher 1 ; `BattleFatigue` (fuite si allié adjacent tué) — déjà connu.

## GetEmRuntz (1045) + SquigHound — PORTÉS (#65) — LÈVENT le GAP level de PileIn

Le GAP « grot seedé sans `activeAbilityLevel` → PileIn résout mal » est **LEVÉ** : un grot spawné par le port
GetEmRuntz/SquigHound porte `active_ability_level = niveau du caster` (le Runtherd, capté offline via
`snapshot.py:120` depuis `combatSnapshot.activeAbilityLevel`) -> `build_summon_context` propage ce niveau
(`spawn.py:77`) -> PileIn résout `ability_var(PileIn, ..., casterLevel)` correctement.

| Ability | Native | Type | Placement | Stats | Port |
|---|---|---|---|---|---|
| **GetEmRuntz** (1045) | `@1811e2210` (+`GetSpawnTileSelector @1811e26b0`) | ACTIVE (orksRuntherd décide, `GetEmRuntzPlaybook @18113ee00`) | 1 grot par hex LIBRE **adj-caster ∩ adj-ennemi** | `WithStatsFromConfig(GetEmRuntz)` (7312@50/200) | `SpawnUnitOperation.execute_getemruntz` + `GetEmRuntzAbility` + `GetEmRuntzPlaybook` |
| **SquigHound** | `@1811a1a30` (+`CreateTrigger @1811a1c60`) | TRIGGERED (après attaque du caster, `On(0x26)&OwnerIsCaster`) | 1 grot adj-CIBLE si **<maxSummons(5)** grots | `WithStatsFromConfig(SquigHound)` (7312@50/200) | `execute_squighound_summon` + hook `after_hit_normal_attack` |

- **GetEmRuntzPlaybook** : utilité = `numTiles` (# grots qui apparaîtraient) ; `MIN_UTILITY` dynamique =
  `minSummons` selon PV% du caster (`GetMinSummonsToUse @18113f0b0` : <=49→1, 49<..<75→2, >=75→3). Caste si
  `numTiles >= minSummons`. Le caster ne bouge pas.
- **VALIDÉ OFFLINE** (Runtherd lvl50 + ennemi adjacent) : GetEmRuntz spawn grot hp=7312 level=50 ; ce grot PileIn
  -> grot hp=4432 (**GAP LEVÉ**, ≠ 0) ; SquigHound after-attack -> grot hp=7312 level=50 adj-cible.
- **Effets secondaires PORTÉS + VALIDÉS OFFLINE** (#65) :
  - **Taunt GetEmRuntz** (`TauntWithNewChildrenWhoDidDamage @1811e27a0`) : chaque ennemi attaqué par un NOUVEAU
    grot (LastUnitAttackedBy, vivant, a subi du dégât) est **Taunted(27)** 1 round (`AddBondEffect(0x1b)`,
    COMPOSITE 25/26/1237). Porté dans `GetEmRuntzAbility.execute_behaviour` (AddEffectOperation après l'attaque).
  - **SquigHound_IgnoreBattleFatigue** (`@180f6d210`, aura Snotflogga -> grots amis) : pose **IgnoreBattleFatigue
    (1079=0x437)** sur les grots amis quand la team a un porteur `SquigHound` VIVANT -> immunisés du flee
    `BattleFatigue` (gate DÉJÀ porté `behaviour.py:121`). Porté = `_maybe_seed_ignore_battle_fatigue` dans
    tous les spawns de grot (GetEmRuntz/SquigHound/PileIn). Distinction ids : 1078=SquigHound_IgnoreBattleFatigue
    (l'aura sur Snotflogga) / 1079=IgnoreBattleFatigue (le status projeté sur le grot, vérifié par BattleFatigue).
    VALIDÉ : grot d'un Runtherd -> 1079 posé ; grot d'une team sans SquigHound -> refusé. ⚠ snapshot au spawn
    (retrait si Snotflogga meurt non modélisé).
- **FLAGGÉ non porté** (reste) : `SquigHound_AdditionalHitsEffect` (1292 : Snotflogga +2 coups Physical de
  dégât PROPRE 1746-2619 — nécessite l'infra « coups additionnels à plage de dégât propre », slice DÉGÂT
  distincte, hors thème summon) ; on-appearance `PerformAIAttackFromCurrentPosition` (approx : ennemi le plus
  proche — OK pour poser le Taunt) ; exclusion `UnitsWithoutTrait(0x1b)` (enum trait non mappé, non-fonctionnel
  comme dans ArcaneShield) ; placement RNG-exact (`SortTilesByUtilityForSummon`).

## Calibration ctx (natives déjà portées : ThunderousAssault @1812158b0, CrushingClaws @1811cd5e0, ScarabHive @181204cb0)
- **ctx+0x160 = caster/actor** (attacker de `AttackWithAttackDamage`, actor de `MoveUnit`/`PushUnit`).
- **ctx+0x178 = TARGET** (ennemi) — attaques ; aussi `Tiles(target)` pour la géométrie splash.
- **ctx+0x148 = caster SELF-ref** (self-cast : `RemoveUnitFromItsTiles`/self-`AddEffect`).
- **ctx+0x168 = caster tile/pos ref** (2ᵉ opérande splash « adjacent-à-both »).
- Handler : `caster_id = summon uid`, `target_id = action["target"]`.
- `MinMaxDamage`/`GetVariableForLevel(0xc,0xd)` = `minDmg`/`maxDmg` ; `GetNumberConstant(0x2f)`=`nrOfHits`,
  `(0x32)`=`nrOfHits_2`, `(0x11)`=`nrOfTargets`, `(0xb)`=`dmg`, `(0x45)`=`nrOfRounds`, `(0x77)`=`nrOfRounds_2`.
- `DefaultAmountOfRounds @181559ff0` : non-null seulement pour {79→3 ; 1065/1162/1244→1 ; 5/17/18/58/1476→2} ;
  tous les EffectType ci-dessous → 0 → `AddEffectOperation` fallback = 1 round (table `operations/effects.py:52` complète).

## CLASSIFICATION

| Ability | id | VA native | Classe | Chemin générique actuel |
|---|---|---|---|---|
| **IncendiaryShells** | 1044 | 1811e9b60 | **(A) GÉNÉRIQUE OK** | correct (3-hit Flame mono) |
| Stikkbomb | 1051 | 18120c180 | (B) splash | main 2-hit OK, **rate splash** |
| PlasmaGrenade | 1098 | 1811f99e0 | (B) splash | main 2-hit OK, **rate splash** |
| Fragstorm | 1078 | 1811e0a00 | (B) splash (pick random) | main 4-hit OK, **rate splash** |
| ScythingTalons | 1065 | 1812059f0 | (B) splash + hits cond-trait | main 3-hit OK, **rate splash + doublement** |
| DevoutPush | 1053 | 1811d3de0 | (B) attaque-normale + move | **no-op** (pas de damageProfile) |
| WallOfMirrors | 1186 | 18122c450 | (B) move + attaque-normale + buff | **no-op** (rate l'attaque normale) |
| ForwardObservers | 1185 | 1811df700 | (B) paire d'effets, no dmg | no-op (dmg-fidèle) |
| Burrowers | 1023 | 1811caa80 | (B) self-effect + off-board | no-op (dmg-fidèle) |
| TunnelingHorror | 1011 | 181216860 | (B) self reposition + bond | no-op (dmg-fidèle) |
| **ValkyrieStrike** | 1018 | 181229e40 | **(GAP)** airstrike différé | **le générique TIRE À TORT un Blast immédiat** |
| **PrecisionShot** | 1015 | 1811fa430 | **(GAP)** aim→shoot 2 étapes | générique = 0 dmg (pas de minDmg) |
| **KissOfDeath** | 1108 | 1811ed5a0 | **(GAP)** chain-attack + blink | générique = 0 dmg (clé `dmg`) |
| **SlashingDive** | 1091 | base 1811d4230 | **(GAP)** dive ligne 3-cibles + move | générique = 0 dmg (clé `dmg` array) |

Note : IncendiaryShells `attackRangeType=None` → le générique passe `ranged=False` ; natif = tir portée 2 →
mettre `ranged=True` pour le perçage exact (mineur).

## (A) GÉNÉRIQUE SUFFIT — rien à faire
**IncendiaryShells (1044)** @1811e9b60 : `AttackWithAttackDamage(caster, target, RandomAmount(minDmg,maxDmg),
Flame, nrOfHits=3)` + `InformWeapon` (visuel). Mono-cible 3-hit → `execute_ability_attack` + `ability_attack_params`
(défaut minDmg/maxDmg/nrOfHits) OK. Optionnel : `ranged=True` pour le perçage.

## (B) PORTS DÉDIÉS

### B1 — Splash (mirror `CrushingClawsAbility`, `loki.py:158`) — PRIORITÉ HAUTE
Les 4 = **1 attaque main sur `target` + 1 volet splash sur un set proche, PARTAGEANT la MÊME plage de dégât**
(le natif calcule `RandomAmount`/`MinMaxDamage` UNE fois, alimente les 2 `AttackWith*Damage` ; seul le nb de
hits diffère). ⇒ le splash réutilise `min_key=minDmg,max_key=maxDmg` et SEULEMENT `hits_key=nrOfHits_2` — **PAS**
`minDmg_2/maxDmg_2` (pattern var-séparées = CrushingClaws only). Chaque volet = `execute_ability_attack`.

- **PlasmaGrenade (1098)** @1811f99e0 — eldarSmnGuardian, Plasma, ranged. main `hits=nrOfHits=2` ; splash set =
  **ennemis adjacents (hex) à `target`** = `Enemies(caster, AdjacentUnits(target))` → helper
  `_adjacent_enemies_of(state, caster_id, target_id)` (ennemis du caster sur `board.neighbours(target tile)`,
  vivants, exclut target) ; splash `hits=nrOfHits_2=1`.
- **Stikkbomb (1051)** @18120c180 — orksOrkBoys, Blast, ranged. Même forme. main `hits=2` ; splash set =
  `AdjacentUnits(target)` (team-param 3 → même `_adjacent_enemies_of`) ; splash `hits=nrOfHits_2=1`. `AtomicGroup`
  (no-op offline). Profil Blast.
- **Fragstorm (1078)** @1811e0a00 — templSmnAggressor, Blast, ranged. main `hits=nrOfHits=4` ; splash = **jusqu'à
  `nrOfTargets=4` tuiles PICK-RANDOM** parmi `AdjacentTiles(target) − tuiles alliées`, `hits=nrOfHits_2=2`. Port :
  `_adjacent_enemies_of` puis `PickRandomly` ≤4 via `state.rng.next_internal` (mirror `spawn.py:_pick_randomly`).
  **GAP** : ordre/coût RNG du pick non calibré → subset trié déterministe si rng non calé ; placement = raffinement.
- **ScythingTalons (1065)** @1812059f0 — tyranSmnWarrior, Bio, melee. main `hits=condHits1` ; splash set =
  **ennemis adjacents à la FOIS au caster ET au target** = réutiliser `_adjacent_to_both(state,caster,target)`
  (`loki.py:118`) ; splash `hits=condHits2`. **Hits conditionnels** : `ConditionalAmount(HasTrait(target@0x180,
  trait=2), nrOfHits*2, nrOfHits)` → hits DOUBLENT (3→6 main, 2→4 splash) si le target a le trait enum `2`.
  **GAP** : trait enum `2` non résolu (pas de map TRAIT dans `enum_maps.py` ; même famille que `0xd` CrushingClaws).
  Porter les hits de base ; ajouter le doublement une fois trait 2 identifié (via `target` gameconfig `traits`).

Ajouter ces sous-classes `ActiveAbility` dans `loki.py` + `ABILITY_CLASSES` (`handler.py:19`). Pas de volet
effet/push pour ces 4 (AoE dégât pur).

### B2 — Attaque-normale + déplacement — PRIORITÉ MOYENNE
Le volet dégât = l'attaque NORMALE du summon (pas un dégât d'ability) → `AttackDamageOperation.execute(state,
caster, target)` (`damage.py:150`, lit l'arme/stats du summon).
- **DevoutPush (1053)** @1811d3de0 — templInitiate : `UseActiveAbility(caster,target,UnitNormalAttackType)` +
  `Kill(deadUnits)` + `PerformAIMovement(caster, Direct(1))` (avance d'1 dans la tuile libérée). Port =
  `execute(caster,target)` + **[move TODO]** avance caster (différer à la tranche mouvement, cf. push
  ThunderousAssault `loki.py:73`).
- **WallOfMirrors (1186)** @18122c450 — tauSmnStealthSuit, `extraPierce=15` : `MoveUnit(caster→best tile par
  SortTilesByUtility)` **&** temp `AddEffect(Untargetable 1044)`+`RemoveEffect` (blink) **&** `If(cond@0x98)[
  UseNormalAttack(caster,target) & temp AddEffect(WallOfMirrors 1398, +15 pierce)]`. Port minimal :
  `execute(caster,target)` pour le tir ; **[move TODO]** repositionnement ; le `+15 pierce` vit dans l'effet
  1398 (non porté → le tir manque le +15). **GAP** : temp-buff pierce + repositionnement + gate `If` non
  modélisables offline maintenant.

### B3 — Effet-seul / self — PRIORITÉ BASSE (dmg-fidèle en no-op aujourd'hui)
`AddEffectOperation.execute(state, source=caster, target=<tgt>, effect_type=<int>, name="<EnumName>",
duration_override=<turns>)` (`effects.py:72`). Aucun de ces EffectType dans `EFFECT_CLASSES` (`factory.py:36`)
→ matérialisé en `BaseEffect` (nom présent sur la cible, diffable ; pas de contribution stat).
- **ForwardObservers (1185)** @1811df700 — tauSmnStealthSuit, no dmg : `AddEffect(Markerlight 1122,
  TurnsFromRounds(nrOfRounds=2))` + `AddEffect(ForwardObservers_DamageReduction 1397, TurnsFromRounds(nrOfRounds_2
  =1))`, `dmgPctReduction=50` payload de 1397. **GAP** : décompilé ancre les 2 sur ref `0x148` (avec `0x178`=ennemi
  relié sur le Markerlight) — cible self-vs-ennemi ambiguë ; confirmer ce que le playbook décide. Effets non
  portés (no-op) → risque bas.
- **Burrowers (1023)** @1811caa80 — tyranSmnRipperSwarm, self, no dmg : `RemoveUnitFromItsTiles(self)` +
  `RemoveAllForcedAttackTargets` + `AddEffect(Burrowers_Hidden 1040, target=self, default→1 round)`. Port =
  `AddEffect(1040, source=caster, target=caster)`. **GAP** : retrait off-board (burrow) non modélisable (le ripper
  quitte le board puis ré-émerge ; offline ne peut que tagger l'effet).
- **TunnelingHorror (1011)** @181216860 — necroSmnDestroyer, self, no dmg : `RemoveUnitFromItsTiles(self)` +
  `RemoveAllForcedAttackTargets` + `AddBondEffect(TunnelingHorror_PendingSummon 1113, default→1 round)`. Port =
  `AddEffect(1113,...)`. **GAP** : reposition off-board + ré-émerge/summon bond non modélisables.

## GAPS — non portables offline proprement (valeur capturée ou nœud DSL non-RE)
- **ValkyrieStrike (1018)** @181229e40 — astraSmnVoxcaster : ExecuteBehaviour = **UNIQUEMENT** `AddBondEffect(
  ValkyrieStrike_Effect 1022, caster↔target)` — **PAS d'attaque immédiate**. Le Blast minDmg/maxDmg = payload du
  strike DIFFÉRÉ (l'effet fire au tour suivant). ⚠ **Le chemin générique TIRE À TORT un Blast immédiat** (1018 a
  `constants.damageProfile` → `_is_attack_ability` renvoie True à `summon_ai.py`). Fix fidèle : **EXCLURE 1018 du
  chemin d'attaque générique** (port dédié no-op qui ne pose que l'effet 1022). Modéliser l'airstrike différé =
  sa propre tranche pending-effect.
- **PrecisionShot (1015)** @1811fa430 — necroSmnDeathmark : ExecuteBehaviour = `UseActiveAbility(caster, caster,
  PrecisionShot_Aim=1012)` — **aim→shoot 2 étapes** (aim ce tour via 1012, dégât livré par PrecisionShot_Attack=1013
  plus tard). Pas de dégât immédiat au cast 1015. Générique = 0 dmg (pas de minDmg) → pas de sur-tir, mais port
  fidèle = poser l'état Aim, pas du dégât. Chaînage sous-abilities (1012/1013) non modélisé ; recommander no-op
  dédié pour le dégât immédiat + flag.
- **KissOfDeath (1108)** @1811ed5a0 — eldarSmnHarlequin : `ChainAttackDamage(target, dmg[0xb], DirectDamage, hits,
  maxAdjacentTargets=2)` (chaîne jusqu'à 2 adjacents) **+ blink** `MoveUnit(caster→best tile)` wrappé temp
  `AddEffect(Untargetable 1044)`+`RemoveEffect`. `ChainAttackDamage` = **primitive distincte NON portée** ; dégât
  via la clé `dmg` (0xb), pas minDmg/maxDmg. Nécessite un port chain-damage + blink. Flag.
- **SlashingDive (1091)** base `DiveAttackAbilityBase.ExecuteBehaviour` @1811d4230 — thousSmnScreamer : **dive
  LIGNE 3-cibles** — boucle indices 0..2 sur `GetTargetTilesSelector` (un chemin), chaque index i :
  `AbilityDamage(caster, enemy@i, Direct(dmg[i]), Power, nrOfHits)`, `dmg` = `GetVariableArrayForLevel(0xb)` triple
  (`"25,20,15"` = décroissant), gated `StartAttack`/`FinishAttack`/`AmountIsGreaterThanZero`, puis
  `GetMovementBehavior` (le dive move). Nécessite la géométrie ligne-chemin (`GetTargetTilesSelector` non-RE) +
  dégât par-index + move. Fallback minimal : mono-cible `dmg[0]` Power sur la cible décidée ; ligne complète =
  tranche dédiée. Flag.

## PASSIVES de summon comportementales (follow-up trigger-ports, PAS active-apply)
- **tyranSmnSporeMine — FloatingDeath** (0 active) : le tour de la spore = suicide-explosion ; **death/proximity
  trigger**, pas une active. Trigger-port.
- **thousSmnPinkHorror — Split** (0 active) : à la mort splitte en Blue Horrors ; **death-trigger + spawn** (réutiliser
  `SpawnUnitOperation`). Trigger-port.
- **tyranSmnRipperSwarm — InstinctiveBehaviour** (+ son active Burrowers) : InstinctiveBehaviour DROPPÉ (décision
  antérieure) ; Burrowers ci-dessus.
- **orksOrkBoys / templNeophyte / templSmnAggressor / tauSmnStealthSuit — Summon, BattleFatigue** : Summon = tag
  spawn-source (pas un comportement de tour) ; BattleFatigue déjà porté. Pas d'active-apply.
- Autres (CallInReinforcements, ReanimationProtocols, WhipcoilBody, HarlequinsPanoply, ReinforcedHiveNode,
  WeaverOfFate, SuppressiveFire, Camouflage/Infiltrate/Flying) : passives/auras/triggers — aucune active-apply.

## Ce que le validator doit attaquer d'abord
1. **Partage de plage splash** (B1) : confirmer que le volet splash réutilise `minDmg/maxDmg` (PAS `_2`) et seulement
   `nrOfHits_2` — une mauvaise clé zéro-e le splash silencieusement. Tester PlasmaGrenade/Stikkbomb/Fragstorm/
   ScythingTalons (compte splash + dégât par-cible vs live).
2. **Sur-tir ValkyrieStrike** : vérifier que 1018 ne fait plus de dégât immédiat après exclusion du générique.
3. **Doublement trait-2 ScythingTalons** : hits de base vs live selon que le target a/n'a pas trait 2 (non-mappé →
   sous-compte les hits).
4. **Helper géométrie splash** : `_adjacent_enemies_of` (adjacent-au-target) vs `_adjacent_to_both` (ScythingTalons)
   — mauvais helper = mauvais set. Les 2 exigent `state.board` ; no-board = no-op propre.
5. **Pick random Fragstorm** : ordre/coût RNG non calibré — désync `state.rng` si consomme autrement que live.

**PROUVÉ** (décompilé, VAs citées) : chaque chaîne de behaviour, ints EffectType, constantes nb-hits, partage
plage-dégât, calibration offsets ctx, table DefaultAmountOfRounds. **HYPOTHÈSE/GAP** (flaggé inline) : identité
trait-2 ScythingTalons, cible self-vs-ennemi ForwardObservers, coût RNG pick Fragstorm, tous les mécanismes
déplacement/off-board/effet-différé/chain.
