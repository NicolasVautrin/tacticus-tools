# Case #173 — HellfireShells (1080) prediction : base=Direct(minDmg) + hits trait-conditionnel

**Statut** : RE COMPLETE (decompile, build `gqfc5mff6c`, VAs citees) + PORTE (`_hellfire_shells_inputs`).
**NON mesurable live** (carrier non-spawnable) -> verdict decompile-proof, standard #169 HarbingerOfDestruction.

## TL;DR

`HellfireShellsPlaybook.MakeDamagePredictions @181143a00` = mirror parfait de `CrushingClawsPlaybook
@1811274b0` (meme signature `(param_1..param_5)`, meme appel `GenerateMultiHitAttackPredictions @181409da0`).
Il SURCHARGE la base/hits/profil generiques du port sur 3 axes -> gap BASE + HITS + PROFIL. Porte via un
handler dans `_MAKE_DMG_INPUT_OVERRIDES` (mirror de `_martial_inspiration_inputs` #106 / `_crushing_claws_inputs`
#164).

## Chaine native (VAs, build gqfc5mff6c)

### BASE = Direct(minDmg) = minDmg SEUL (rarity-scaled), PAS avg(minDmg,maxDmg)
```
uVar4 = GetVariableForLevel(cfg, 0xc, level_ctx)   // @181576fb0 ; var 0xc = minDmg
uVar8 = DSLFactory.Direct(uVar4)                    // @180dee2a0 (Direct scalaire) -- PAS Half(Sum(...))
```
- var 0xc = `minDmg` (gameconfig `variables.minDmg`, `variablesAffectedByRarityBonus=[minDmg,maxDmg]`).
- Rarity-scaled OUI (`TryGetVariableArrayForLevel @181577510` scale x mult/100 ; level+mult = AbilityState
  per-ability, param_5, mecanisme #100).
- Gap : @lvl65 mult100, minDmg=582 vs avg(minDmg 582, maxDmg 873)=727 -> le generique SUR-PRED +145/coup.

### HITS = nrOfHits + (BigTarget de la CIBLE ? extraHit : 0)
```
iVar5 = GetNumberConstant(cfg, 0x2f)                // nrOfHits = 2
iVar6 = GetNumberConstant(cfg, 0x2b)                // extraHit = 2
cVar3 = UnitExtensions.HasTrait(param_4, 0x3f9)     // param_4 = TARGET ; 0x3f9 = 1017 = UnitTrait.BigTarget
if (cVar3 != 0) iVar5 = iVar5 + iVar6               // 2 vs cible normale, 4 vs BigTarget
```
- `param_4` = la CIBLE (prouve : `GenerateMultiHitAttackPredictions @181409da0` recoit param_4 comme target,
  `local_368=param_4`, `GetTiles(param_4,...)` ; identique CrushingClaws).
- trait 0x3f9=1017 = `UnitTrait.BigTarget` (port `unit_trait.py`, nom gameconfig "BigTarget").
- LITTERAL pur, PAS de `+ExtraHits` stat (le generique `get_special_hits` ajoute les ExtraHits -> faux ici).
- Croise avec le COMBAT `HellfireShellsAbility.ExecuteBehaviour @1811e8030` : `If(HasTrait(target,0x3f9),
  event_base+bonus, event_base)` -- MEME condition, MEME trait, MEME cible. Prediction et combat concordent.

### PROFIL = param_8 null -> None (pierce 0, armure PLEINE)
```
local_38 = 0; GenerateMultiHitAttackPredictions(..., Direct(minDmg), iVar5, 0, &local_38=0, 0, ...)
                                                                       ^param_8=0 (null)
```
MEME quirk que CrushingClaws #164 (param_8=null -> profil None enum -1 -> pierce 0). Le port applique
`profile_override="None"` -> `profile_idx=-1`, `GC.damage_profile("None")=None` -> pierce 0 (armure pleine).

## Carrier / non-mesurabilite

Les 3 carriers -- `ultraNpc4HeavyIntercessor`, `ultraNpc4HeavyIntercessorSurv`, summon
`ultraSmnHeavyIntercessor` (`PowerUp_SummonSpawn_ultraSmnHeavyIntercessor`, EnvFactionSummons Ultramarines) --
sont NON-spawnables via `rl_duel build` (NPC campagne + summon d'ENVIRONNEMENT, pas invocables par une unite
lineup ; `--p-units ultraSmnHeavyIntercessor` -> "hors pool"). Aucune confrontation `aiPlaybookPredict`
possible. Verdict DECOMPILE-PROOF (structure-identique CrushingClaws, base/hits/profil exclus par lecture),
meme standard que #169.

## Port (`scripts/python/engine/playbook/prediction.py`)

Handler `_hellfire_shells_inputs(scene, caster_id, target_id, ab, cfg)` -> `{base_override: minDmg(0xc,
rarity-scaled), hits_override: nrOfHits(+extraHit si cible BigTarget), profile_override: "None"}`, entree
`_MAKE_DMG_INPUT_OVERRIDES[1080]`.

CHANGEMENT DE CONTRAT (transverse) : le hits etant target-conditionnel, la signature des handlers passe de
`(scene, caster_id, ab, cfg)` a `(scene, caster_id, target_id, ab, cfg)`. `_martial_inspiration_inputs` +
`_crushing_claws_inputs` recoivent `target_id` (ignore, contrat registre) ; le dispatch (`make_damage_predictions`)
passe `main_tgt_id`. HellfireShells mono-cible (config sans nrOfTargets) -> `main_tgt_id` = la seule cible.
`_PLAYBOOK_PROFILE_OVERRIDE[1080]` PAS ajoute (profil via le handler, evite le double-set).

## Confirmation offline (carrier non-mesurable live)

- cible non-BigTarget -> `{base_override: 582, hits_override: 2, profile_override: "None"}`.
- cible BigTarget -> `{base_override: 582, hits_override: 4, profile_override: "None"}`.
- gap base corrige : generique avg 727 -> minDmg 582 (-145/coup).
- Non-regression signature : `_martial_inspiration_inputs`/`_crushing_claws_inputs` OK sous signature etendue.
- Pipeline aval `profile_override="None"` = MEME chemin que CrushingClaws #164 (valide bit-exact live).

## Non couvert
Aucune confrontation oracle live (carrier non instanciable). Le triplet exact (582 / 2 ou 4 / pierce0) repose
sur le decompile ; l'integration (base/hits/profile_override) est reprise telle quelle des precedents valides
bit-exact (HammerOfWrath, CrushingClaws). Si un jour le summon est spawnable : `aiPlaybookPredict(carrier,
ultraTitus, 1080)` = base+-20% pierce0 (2 coups) ; vs cible BigTarget = 4 coups.
