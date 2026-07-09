# Case study #68 : effets de degat ATTAQUANT d'orksNob (SmashaEad + BeastSlayer)

Build `gqfc5mff6c`. Ground truth mesuree 2026-07-08 (replay-diff orksNob 1v1 + RE ghidra). GREP ce
fichier avant de re-investiguer #68.

## Contexte : ce que la game applique reellement

`decisionView.effects` sur orksNob (Tanksmasha) au moment de l'attaque =
`[BeastSlayer_ExtraDmg, BeastSlayer_ExtraBlock, SmashaEad]`.

Le runner offline **seed ses effets depuis ce snapshot** (`load_state` -> `EffectFactory.create_many`
depuis `decisionView.effects`, avec `activeAbilityLevel`) — donc PAS besoin de porter les triggers de
CREATION d'effet pour le replay (l'etat live est charge tel quel). Il faut juste que la CLASSE d'effet
soit portee + enregistree dans `factory.py`, et que sa magnitude/condition soient fideles.

## SmashaEad — PORTE (#69)

`SmashaEadEffect.CreateEffectDamageBonusForAttack @180f6bee0` = `EffectBonus.ForAddition(OwnerIsCaster
& IsNormalAttack, ConfigVar(8=extraDmg))`. Additif PLAT, canal `additive @+0x10`, **POST-percage**
(cf. #69 : DamageModifiers.Add @181005f10 -> CalculateBaseDamageWithAllModifiers @18102d3f0). Classe
`SmashaEadExtraDamageEffect` (loki.py) = `for_addition(extraDmg[activeLvl] x mult)`. Magnitude :
`extraDmg` in variablesAffectedByRarityBonus (scale par mult) ; array VA jusqu'a L50 (`extraDmg[50] x
mult180 = 599`, PAS 41 : l'hypothese '14 niveaux clamp 23' etait FAUSSE).

**RESOLU #71 (verdict re-expert + fix valide)** : la sur-prediction venait du trigger natif de SmashaEad
`ForAddition(OwnerIsCaster & IsNormalAttack, ...)` (@180f6bee0). Le noeud DSL **`IsNormalAttack` evalue
FALSE dans le contexte PREDICTION DISPLAY** (RapidAssault, trigger `OwnerIsCaster` SEUL, evalue TRUE ->
matche). Le port avait collapse le AbilityTrigger en un bool `owner_is_caster` sans porter `IsNormalAttack`.
FIX : flag `is_prediction` threade dans le funnel attaquant ; `calculate_attacker_modifiers_for_prediction`
passe `is_prediction=True` -> `SmashaEadExtraDamageEffect.create_effect_damage_bonus_for_attack` renvoie
None (additif absent de la prediction, matche le DISPLAY) ; `build_attacker_modifiers_from_effects`
(COMBAT) garde `is_prediction=False` -> additif applique. Gate SPECIFIQUE a SmashaEad (seul effet dont
le trigger natif contient IsNormalAttack ; RapidAssault/FightingRetreat = OwnerIsCaster seul, non gates).
VALIDE : deterministe off_avec == off_sans == (964,1448) ~= oracle (948,1311) [avant : off_avec=(1563,2047)] ;
test_predict_live 2/2 (RapidAssault matche) ; combat armored/ability 2/2 (is_prediction=False, SmashaEad
reste en combat). Chemin #64 (debuff stat-mod) = branche separee, non touchee.

**MAJ 2026-07-09 (GetStuckIn combat porte => confond LEVE) — DIAGNOSTIC : MAGNITUDE ~2x, PAS presence.**
Replay-diff orksNob->bloodIntercessor (cible NON-Big, seed 4242, per-hit) en isolant la contribution SmashaEad :
- `off_SANS_SmashaEad` = [1240,1438,1226]
- `live`              = [1540,1738,1526]  = off_sans **+ 300 CONSTANT**
- `off_AVEC_SmashaEad` (port, 599/coup) = [1839,2037,1825] = off_sans **+ 599**
(base=2411 ; effects offline=[BeastSlayer_ExtraDmg, BeastSlayer_ExtraBlock, SmashaEad]).
=> **le LIVE applique bien SmashaEad en combat (~+300/coup), le PORT applique ~+599/coup = ~2x trop grand.**
La 1re hypothese "SmashaEad absent en combat" (fix `return None`) etait FAUSSE : le fix a fait passer off SOUS
live (-300) => REVERT. L'ecart CONSTANT sur des coups a rolls DIFFERENTS => additif POST-reduction constant
(donc NI placement pre-percage — #69 reste valide — NI per-coup-vs-once — les deux sont per-coup). GetStuckIn
ECARTE (coup index 0 PAIR sans Maybe porte le meme offset ; l'ecart constant a travers la frontiere Maybe
PROUVE le bon positionnement du tirage, cf. case-62c). RESTE #68 = **RE de la VALEUR** : `extraDmg` (array
gameconfig) x `ability_variables_multiplier` x niveau (`active_ability_level`) -> pourquoi 599 vs ~300 live
(facteur ~2 : multiplier double-applique ? mauvais niveau ? confusion extraDmg/extraDmg_2 ?). Corriger la
valeur => off==live => test xfail `test_getstuckin_combat_absolute_bit_exact` xpass. `IsNormalAttack`
(= `IsRegularAttack(ability declenchante)` @180f8d260/@181555b40) = FALSE sans contexte d'ability (explique
l'absence en PREDICTION display #71), mais en COMBAT SmashaEad EST bien applique (presence confirmee).

**RESOLU (RE re-expert, bit-exact) : le bug = le MULTIPLIER (180 au lieu de 90).** Formule native PROUVEE :
additif = `round(extraDmg[level-1] x multiplier/100)` (ConfigVar(8)@180f6bee0 -> ConfigAmount.Calculate@180f171c0
-> GetVariableForLevel@181576fb0 -> TryGetVariableArrayForLevel@181577510 ; index=level-1 @181565ce0 ; multiplier
applique SSI var in variablesAffectedByRarityBonus, lu = `AbilityState+4`). level=50/extraDmg[49]=333/index :
tous CORRECTS. SEUL le multiplier est faux : le port prend `self.ability_variables_multiplier=180` (UnitConfig
+0x74 = multiplier de l'ability PRIMAIRE/active) ; or la TRIGGERED SmashaEad a son PROPRE multiplier par-ability
= **90** (`GetAbilityVariablesMultiplierPercentage(abilityId)@181696230` est PAR-ABILITY : +0x24 ou +0x2c selon
appartenance liste). `round(333x0.9)=300` = live EXACT ; `round(333x1.8)=599` = port. Ce multiplier par-ability
des triggered N'est capte par AUCUN champ actuel (combatSnapshot = UnitConfig +0x74=180/+0x78=100, aucun=90) ->
fix FIDELE = nouveau capteur (tache #75) ; stopgap `mult/2` = coincidence non generalisee (a FLAGGER hardcode).

---

**(historique) SUR-PREDICTION (mesure DETERMINISTE, #71)** : via `Scene.from_state` (aiPredict, aucun roll RNG),
orksNob->worldTerminator (cible NON-Big -> BeastSlayer=0, isole SmashaEad) :
- off WITH SmashaEad = `(1563, 2047)` ; oracle `decisionView` = `(948, 1311)` ; off WITHOUT = `(964, 1448)` ~= oracle.
- => l'oracle DISPLAY (`decisionView` = `GetAllPredictions`, lit `GetStat(Attack Current)`) **N'APPLIQUE PAS**
  l'additif SmashaEad ; le port l'applique (+599 une fois) -> **SUR-PREDICTION de +599**. off WITHOUT ~= oracle
  confirme que le RESTE (base+RapidAssault %-mult) matche ; c'est bien l'additif effet qui sur-compte.
- DISPLAY != SCORING : le %-mult (RapidAssault) EST reflete dans le DISPLAY (valide) mais l'additif effet ne
  l'est apparemment PAS -> asymetrie a RE (#71 : `GetAllPredictions @181090f50` applique-t-il l'additif @+0x10 ?).
  Si non -> retirer l'additif effet du chemin prediction display-matchant, le garder en COMBAT/scoring.
- Caveat : sample `predOpt=True` (worldTerminator TerminatorArmour) confond le match absolu, PAS le +599 relatif.
- Reconcilier avec le replay COMBAT (off~=live+11-33, PAS +599) : le combat n'appliquait pas +599 non plus
  -> niveau/presence de SmashaEad a re-verifier en combat aussi. **SmashaEad PAS valide (voir #71).**

NB harnais : la validation DETERMINISTE via `Scene.from_state` + le drive du replay CONTOURNE le snag
`build_samples` (`0 units cold` / `base non capturable` sur runner 1v1 isole). Voie reutilisable.

## BeastSlayer_ExtraDmg — PORTE + VALIDE LIVE (2026-07-08)

**Classe `BeastSlayerExtraDmgEffect`** (loki.py) = `for_percent_increase(True, beastSlayerExtraDmgPct=20)`
gate `not is_ranged` (IsMeleeAttack) ET cible BigTarget/Vehicle ; enregistree `"BeastSlayer_ExtraDmg"`
dans factory. **Threading TARGET** : `target_traits` (set de noms de traits cible, mirror `HasTrait`)
ajoute a `create_effect_damage_bonus_for_attack` (base + 5 overrides), au funnel partage
`_attacker_effect_bonuses` + `build_attacker_modifiers_from_effects` +
`calculate_attacker_modifiers_for_prediction`, et calcule chez les 2 appelants NORMAL-ATTACK :
prediction (`prediction.py`, depuis `scene.vis_by_id`->gameconfig traits) et combat
(`damage.py` normal-attack, via helper `target_trait_names(state, target_id)` lisant
`StatsComponent.ctx.traits`). Chemins ability/splash/trigger (damage.py:364/431, triggers.py:1016) =
`target_traits=None` (BeastSlayer no-op documente ; melee-ability = follow-up si besoin).

**Validation** (replay-diff, off-RNG seede depuis live) :
- Logique unitaire : BigTarget/Vehicle melee -> PercentIncrease 20 (x1.2) ; Hero/ranged/no-target -> None.
- No-regression : test_predict_live 2/2 + test_damage_normal_armored/ability 2/2 (funnel + 2 appelants).
- LIVE end-to-end vs cible BigTarget (tauCrisis) :
  - custoBladeChampion : live [1419,1449,1119] vs offWITH [1418,1448,1118] (-1/coup = arrondi Fix64 //100,
    PAS une erreur) ; offSANS-BeastSlayer [943,1228,881] (~20% plus bas).
  - ultraTitus : live [692,752,666,508] vs offWITH [691,751,665,507] (-1/coup) ; offSANS [524,626,582,466].
  => avec BeastSlayer, off reproduit l'oracle live a +/-1 (arrondi) ; sans, off chute ~20%. PORT CONFIRME.

## (RE, conserve) BeastSlayer_ExtraDmg

RE ghidra + gameconfig + i2 :
- **gameconfig (trait BeastSlayer)** : `beastSlayerExtraDmgPct=20`, `beastSlayerBlockChance=10`,
  `beastSlayerBlockAsMaxArmorPct=100`. (Variable de TRAIT -> globale, NON scalee par le mult.)
- **i2** : "+{extraDmgPct}% Damage with **melee** attacks to **Big Targets and Vehicles**. Added
  {blockChance}% chance to Block {blockDmgPct}% of current Armour as Damage."
- **`BeastSlayer_ExtraDmgEffect.CreateDamageModifier @180f336c0`** : magnitude = `ConfigConst(0xf)` =
  `beastSlayerExtraDmgPct` = **+20% (PercentIncrease)** ; condition =
  `OwnerIsCaster & IsMeleeAttack & ( HasTrait(target, 0x405=1029 BigTarget) | HasTrait(target, 0x3f9=1017 Vehicle) )`.
- Effet cree par `BeastSlayerAbility.CreateTrigger @180e18f90` (triggered).

### BeastSlayer_ExtraBlock (cote DEFENSE) — PORTE + VALIDE LIVE (2026-07-09, #72)

**RESOLU** : source de bloc supplementaire + roll-gating fidele. Validation replay-diff BIT-EXACT
(necroDestroyer 6 coups -> orksNob) : off per-hit == live, PV egaux (`test_beast_slayer_block_live.py`).
Diagnostic double-compte LEVE (live) : orksNob snapshot `blockChance=0` -> BeastSlayer ABSENT du scalaire
GetStat(7/8) (aucun double-compte ; le runner le manquait entierement avant le port).

**Port** : (1) `BeastSlayerExtraBlockEffect` (loki.py) `create_effect_block_source_for_defense(armor)` ->
`BlockSource(chance=beastSlayerBlockChance=10, amount=beastSlayerBlockAsMaxArmorPct% x FixedArmor, block_id=chance)`,
enregistre `"BeastSlayer_ExtraBlock"` (factory). (2) Canal defenseur : agregateur `defender_effect_block_sources`
(effects/__init__.py) + helper PARTAGE `AttackDamageOperation._block_sources(tsc, tgt_effects, armor)` = base
(scalaire GetStat 7/8) + sources d'effet, appele par les 3 vecteurs (mirror du `GetMultiValueStat(7)` unique
du natif). (3) **ROLL-GATING (RE CLE, decouvert par replay-diff)** : `ApplyRandomBlockDamage @181000390`
ajoute l'id (= la chance `local_88`) d'une source ECHOUEE a `failedList` ; `CalculateBlockChances @181002350`
(rebuild PAR COUP) fait `Contains(failedList, id)` -> **EXCLUT toute source AYANT ECHOUE des coups suivants**
(une source qui REUSSIT reste jouable, ApplyRandomBlockDamage return sans AddFailedBlockId). Donc une source
de bloc est jouee chaque coup JUSQU'A son 1er echec, puis plus jamais. Porte dans
`AttackDamageOperation._run_hits` (accumulateur `failed_block` inter-coups + filtre par-coup). Preuve : orksNob
BeastSlayer (chance 10) hit1 succes + hit2 echec -> 0 roll hits 3-6 = **8 tirages RNG (pas 12)** -> replay
bit-exact. NB : `--block-target` (chance 100) NE l'exercait PAS (100% ne rate jamais -> jamais exclu -> roll
chaque coup ; c'est pourquoi le test block de base passait sans ce gating). Refacto au passage (#72) : helpers
partages `_block_sources` + `_crit_params` (dedup des 3 vecteurs normale/ability/splash).

> **RESOLU 2026-07-09 (#73) — le CRIT n'a PAS ce gating (le port etait deja correct).** RE fidele
> (decompile) : la fonction de roll `DamagePrediction.RollCritical @1810387a0` (-> `DamageCalculations.RollCritical
> @1810057b0` = `NextBool(chance)`) est SANS ETAT : chance = `GetStat(attaquant, 9)` + `GetCritChanceBonusFromEffects`,
> `<1` -> false sans tirage, sinon `NextBool` ; AUCUN input de coup precedent, AUCUN accumulateur "deja rate".
> `CalculateCriticalDamage @18102da90` = `GetStat(10)`+bonus, pur, sans RNG. Dans `ExecuteHit @180e5eff0`, le
> block appelle explicitement `OperationResult.AddFailedBlockIds` (threade par `ExecuteHits`->`RegisterBlocks`->
> HitGroup) ; il N'EXISTE AUCUN "AddFailedCrit" analogue, et la chance de crit passee chaque coup est un champ
> constant (jamais reduit apres un non-crit). Le gating du BLOCK existe PARCE QUE le block est multi-source (chaque
> source a un id -> exclusion individuelle) ; le crit est une chance UNIQUE -> rien a exclure. Chaque coup tire le
> crit INDEPENDAMMENT (deja valide bit-exact a CC=100 : RollCritical tire a CHAQUE coup, 2 tirages/coup). Le
> "comme les crits" utilisateur = analogie libre, PAS un mecanisme partage. Port `_run_hits` (crit independant
> par coup) = deja fidele, aucun changement de code. Nuance distincte (hors #73) : le natif relit `GetStat(9)`+bonus
> PAR COUP alors que le port lit `crit_chance` UNE FOIS avant la boucle -> divergerait seulement si un effet
> modifiait la crit-chance de l'ATTAQUANT EN COURS d'attaque (aucun porteur connu ; suivi en tache separee).

**(RE conserve)** c'est un ROLL de bloc SUPPLEMENTAIRE (pas un simple bonus de chance).
- `GetBlockChance @180e19120` = `GetNumberConstant(0x2d)` = `beastSlayerBlockChance` = **10%**.
- `GetBlockDamage @180e19160` = `PercentageOf(StatAmount(0x10=FixedArmor), Direct(GetNumberConstant(0x36)=100))`
  = **100% du FixedArmor COURANT** comme montant de bloc.
- `CreateAddBlockEffectBehaviour @180e18b70` = `AddExtraBlockEffectToOwner(0x5ed, Direct(chance=10), GetBlockDamage)`
  + 2 `AddOrUpdateStaticStatModifierEffect` (0x619/0x61a) gates `If(ActorHasTriggeredAbility(0x5e9), ...)`.
  i2 : « +10% chance to Block 100% of current Armour as Damage ».
Port : le moteur a un systeme de bloc (`damage_combat.py apply_random_block_damage(rng, block_sources, dmg)`
= chaine de sources, 1er succes bloque). MAIS le runner (damage.py:226/369/436) construit `block_sources`
= UNE SEULE source depuis `tsc.ctx.block_chance/block_damage` (snapshot `GetStat(7/8)` mono-valeur ;
unit_context.py:178 blockChance/blockDamage plats). Le natif utilise `GetMultiValueStat(7)`
(`CalculateBlockChances @181002350`) = LISTE de sources ; BeastSlayer ajoute une entree SEPAREE
(chance 10%, amount=100% FixedArmor, via `AddOrUpdateStaticStatModifierEffect 0x619/0x61a`) avec un
amount DIFFERENT du bloc de base. Donc porter fidelement = (a) canal MULTI-source de bloc cote defenseur
(collecter les sources de bloc des effets de la CIBLE), (b) verifier le DOUBLE-COMPTE (le snapshot
`blockChance` d'orksNob inclut-il deja le +10% de BeastSlayer ? a checker live), (c) l'ORDRE des sources
(CalculateBlockChances trie la multi-value). SLICE DEDIEE non-triviale (risque double-compte/ordre) —
NON faite. RE mecanisme = complete ci-dessus ; l'integration reste a faire proprement (defense, hors
scope attaque #68).

### Port a faire (slice wiring)
1. Classe `BeastSlayerExtraDmgEffect` (loki.py) : `create_effect_damage_bonus_for_attack` renvoie
   `for_percent_increase(True, trait_var("BeastSlayer","beastSlayerExtraDmgPct"))` gate
   `not is_ranged` (melee) ET `target_is_big_or_vehicle`. Enregistrer `"BeastSlayer_ExtraDmg"` dans factory.
2. **Threading TARGET** (comme #59 cote defenseur) : ajouter `target_is_big_or_vehicle` (ou les traits
   cible) a `create_effect_damage_bonus_for_attack` (base + 5 overrides loki.py) et
   `build_attacker_modifiers_from_effects` ; le calculer chez les 2 appelants (prediction Scene +
   runner combat `damage_model`) via HasTrait(target, 1029|1017) — le port connait deja BigTarget/Vehicle
   (engine/entities/traits/combat.py, damage_model.py).
3. **Validation** : NE PEUT PAS se faire vs worldTerminator (infanterie -> BeastSlayer=0, 'present !=
   applique'). Monter un setup avec cible **Big Target ou Vehicle** (unit_map : chercher trait 1029/1017)
   + isolation deterministe (aiPredict) pour confirmer le +20% melee.
