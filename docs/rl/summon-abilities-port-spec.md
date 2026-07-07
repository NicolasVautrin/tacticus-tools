# Summon active abilities — PORT SPEC (RE re-expert, build gqfc5mff6c)

Retour du re-expert (#65 SLICE 2 part c' = apply des abilities actives des summons). Base : le chemin
`engine/runner/operations/summon_ai.py::_apply_active_ability` route (1) port DÉDIÉ via `AbilityHandler`/
`ABILITY_CLASSES` (`handler.py` : 1043 ThunderousAssault, 1206 GravitonRifle, 1007 ScarabHive/ScarabSummon,
1105 CrushingClaws) ; sinon (2) GÉNÉRIQUE `AttackDamageOperation.execute_ability_attack` (attaque active à
`damageProfile`, config via `ability_attack_params`) ; sinon (3) no-op.

## Calibration ctx (natives déjà portées : ThunderousAssault @1812158b0, CrushingClaws @1811cd5e0, ScarabSummon @181205290)
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
