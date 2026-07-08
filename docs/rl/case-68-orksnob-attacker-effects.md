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
reste en combat). Chemin #64 (debuff stat-mod) = branche separee, non touchee. (Combat magnitude/presence
SmashaEad = incertitude #68 separee, confondue par GetStuckIn.)

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
- Effet cree par `BeastSlayerAbility.CreateTrigger @180e18f90` (triggered) ; cote DEFENSE il y a AUSSI
  `BeastSlayer_ExtraBlock` (block +10% de l'armure courante ; `CreateAddBlockEffectBehaviour @180e18b70`,
  `GetBlockDamage @180e19160`, `GetBlockChance @180e19120`) — non porte, hors scope #68 (attaque).

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
