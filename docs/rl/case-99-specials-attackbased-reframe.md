# Case #99/#101a/#110 — Les specials ne sont PAS "Attack-based" : reframing decompile

**Statut** : RE fait (decompile, build `gqfc5mff6c`) + **CONFIRME LIVE** (predict_sweep) + fix applique
(`_PREDICT_VIA_NORMAL_ATTACK` vide) + no-reg (test_predict_live 2/2). #99 CLOS ; #101a CLOS ; residu x2 = #160.
**Tache** : #99 (enumerer les Attack-based), #101a (re-verifier SpiritLeech), #110 (oracle null playbook).

## TL;DR

La conclusion historique « SpiritLeech est Attack-based » (#90/#92, `_PREDICT_VIA_NORMAL_ATTACK =
{"SpiritLeech"}`) est **FAUSSE**. Lue directement au decompile (artefact-free), SpiritLeech (et tous les
specials audites) predisent leur degat par **`<Special>Playbook.MakeDamagePredictions -> GenerateMultiHit(
base = ability.GetAttackDamage(), ...)`**, et `SpiritLeechAbility.GetAttackDamage` est **CONFIG-based**
(DSL `MinMaxDamage`), pas Attack-based (GetStat). Le "2670 == normale exact" mesure historique etait
l'**ARTEFACT du preview** `GetAllPredictions`/aiPredict (Attack-based quelle que soit l'ability — piege
#96/#101a). => `_PREDICT_VIA_NORMAL_ATTACK` doit devenir **VIDE** ; la premisse de #99 (« il existe des
specials Attack-based ») **se dissout**.

## Methode (artefact-free) : slot vtable 0x27

- `ability.PredictAttack` = **slot vtable 0x27 = byte 0x328** dans l'Il2CppClass (mesure via RPC
  `resolveVtableSlot{ns,cls,start,end}` ; le slot ou `method=="PredictAttack"`).
- Deux impls de base :
  - `AActiveAbility$$PredictAttack @180fb2f20` = **STUB ABSTRAIT QUI THROW** (String.Format + System.Exception
    + `FUN_1801f2230` "does not return"). Jamais un vrai chemin de prediction.
  - `ALoki_NormalAttackAbility$$PredictAttack @1811afa50` = **Attack-based** (`FindAttackWeapon` ->
    `GetAttackHitPrediction` = GetStat(Attack)+arme -> `GetAdditionalHitsFromEffectsForPrediction` /
    `AddAdditionalHitsToPrediction`).

### Resultat live (session 12, build gqfc5mff6c) — slot 0x328

| classe (ns IdunBattleLogic.Entities.Abilities.Active.Loki) | slot 0x328 | verdict |
|---|---|---|
| ALoki_NormalAttackAbility (CONTROLE) | `1811afa50` | Attack-based (OK) |
| SpiritLeechAbility | `180fb2f20` | **throw-stub** |
| PlasmaCannonAbility | `180fb2f20` | throw-stub |
| DoomboltAbility | `180fb2f20` | throw-stub |
| JakhalStimmsAbility | `180fb2f20` | throw-stub |
| GauntletsOfUltramarAbility | `180fb2f20` | throw-stub |

=> **Aucun special ne predit via `ability.PredictAttack`** (ca throw). L'hypothese #92 « SpiritLeech herite
ALoki_NormalAttackAbility.PredictAttack » (notee explicitement « HYPOTHESE non lisible statiquement »
prediction.py:385) est refutee.

## Le vrai chemin : `<Special>Playbook.MakeDamagePredictions`

- `SpiritLeechPlaybook$$MakeDamagePredictions @18115d490` :
  `base = SpiritLeechAbility.GetAttackDamage()` ; `hits = ArmoriumCherubAbility.GetHits()` ;
  `profile = KillMaimBurnAbility.GetFirstAttackDamageProfile()` ; ->
  `ComparablePlaybook.GenerateMultiHitAttackPredictions(base, hits, profile, ...)`.
- `PlasmaCannonPlaybook$$MakeDamagePredictions @181150b10` :
  `base = BlightGrenadesAbility.GetDamageFormula()` ; `hits = GetAttackHits()` ;
  `profile = AActiveAbility.GetDamageProfile()` ; 2 appels GenerateMultiHit (cible + secondaires
  UnitsDirectlyBehind, pondere Fix64.FromIntFraction(iVar4,iVar3)). Config-based.

Donc le discriminant N'EST NI le slot vtable (tous throw) NI la structure playbook (tous GenerateMultiHit) :
c'est **ce que retourne `ability.GetAttackDamage()`** (config maxDmg vs override).

## Les 4 SEULS overrides de GetAttackDamage du binaire

- `ExemplarOfHateAbility$$GetAttackDamage @1811dac90`
- `SpiritLeechAbility$$GetAttackDamage @181209dd0`
- `PsykerExtraAttackAbility$$GetAttackDamage @181224550` (absente de ACTIVE_ABILITY_TYPE)
- `ElectroShock_NormalAttackAbility$$GetAttackDamage @1811d7980` (variante normale, kind==normal)

### `SpiritLeechAbility.GetAttackDamage @181209dd0` = CONFIG (DSL)

```
config8   = DSLFactory.ConfigVar(8, ...)                          # config var id 8
minmax    = AActiveAbility.MinMaxDamage(...)                      # spread config autour de maxDmg (0xd)
noEffect  = !DSLFactory.HasEffect(..., 0x429, kind=6)            # 0x429 = 1065
GetAttackDamage = ConditionalAmount(noEffect, minmax, Sum(minmax, config8))
```

=> base = `MinMaxDamage` (config), + `ConfigVar(8)` si l'effet 0x429 est present. **CONFIG-based** — pas de
GetStat(Attack). Le "2670 mesure" = artefact preview, pas la base playbook.

## #110 — Doombolt / JakhalStimms / GauntletsOfUltramar

**Aucun** `<X>Playbook$$MakeDamagePredictions` n'existe pour ces 3 (verifie par recherche de symboles) :
leur `MakeDamagePredictions` herite de la base qui renvoie une liste vide/null -> `aiPlaybookPredict` rend
`ok:true, count=-1, listNull:true` (l'oracle direct ne peut PAS les mesurer). Ce n'est PAS un signe
"Attack-based" : c'est un trou de COUVERTURE de l'oracle.

**FIX APPLIQUE (sweep-side, PAS hook-side)** : `predict_sweep.classify` collapsait `ok:false` (vrai echec RPC)
ET `ok:true, count=-1` (playbook null) dans le meme bucket `ORACLE_FAIL` (22 rows de bruit). On distingue :
`live_main_event` flag `empty` quand `ok:true & count==-1/listNull` -> nouveau statut **`ORACLE_EMPTY`**
(inmesurable par playbook direct, categorie ATTENDUE), reserve `ORACLE_FAIL` aux vrais echecs (`ok:false`).
On **NE fallback PAS** sur `GetAllPredictions` : ce preview est l'ARTEFACT Attack-based (cf. TL;DR) ;
l'injecter dans l'oracle contaminerait la verite playbook pur (#102/#103) et fabriquerait de faux
agreements/gaps. Le hook `aiPlaybookPredict` reste CORRECT (il rend fidelement null = la verite). Marquer
"inmesurable" est la bonne des deux options du plan initial ; si on RE un jour le vrai degat de
Doombolt/JakhalStimms (playbook-null mais preview != 0), on upgrade l'ORACLE_EMPTY en mesure reelle.

## Consequences (port)

1. **Retirer SpiritLeech de `_PREDICT_VIA_NORMAL_ATTACK`** (le set devient vide) ; le mecanisme "route vers
   la normale" repose sur une mesure contaminee -> a supprimer. SpiritLeech passe par le chemin config
   generique (`make_damage_predictions` -> `generate_multi_hit_attack_prediction(base=MinMaxDamage, ...)`).
2. Refinement optionnel : porter le bonus conditionnel `ConfigVar(8) si HasEffect(0x429)` de
   SpiritLeech.GetAttackDamage (sinon base = MinMaxDamage seule).
3. #110 : fallback oracle pour playbook null.

## Confirmation LIVE (predict_sweep Neurothrope MC1_67 seed777) + fix

`aiPlaybookPredict` (vrai playbook #102) vs `disp`/GetAllPredictions (artefact) sur u81(tyranNeurothrope)->u77 :

| mesure | SpiritLeech |
|---|---|
| oracle `aiPlaybookPredict` (vrai playbook) | **[2074, 3112]** (config) |
| `disp` = GetAllPredictions (ARTEFACT preview) | [3111, 4668] |
| eng AVANT fix (`_PREDICT_VIA_NORMAL_ATTACK={SpiritLeech}`) | [16, 202] (casse) |
| eng APRES fix (set vide -> chemin config generique) | [1037, 1556] |

- **oracle [2074,3112] != artefact [3111,4668]** => le vrai playbook n'est PAS le preview Attack-based =>
  **config-based confirme** ; le "2670==normale" historique etait l'artefact `disp`.
- Fix `_PREDICT_VIA_NORMAL_ATTACK = frozenset()` : SpiritLeech passe de casse [16,202] a config [1037,1556].
  No-reg : test_predict_live 2/2.

### Residu (tache #160, DISTINCT) : x2 caster ranged

eng APRES fix = EXACTEMENT la moitie de l'oracle, sur SpiritLeech ([1037,1556] vs [2074,3112]) ET sur la
NORMALE (Loki_NormalAttack [803,1205] vs [1606,2410]). Facteur x2.0 partage, PRE-EXISTANT (sur la normale
avant le fix) = modificateur caster/position (RangedSpecialist +33% ported x elevation +50% ? = 1.33*1.5=2.0)
non pleinement applique en prediction. A tracer artefact-aware (statModSources/predCalcDumps) -> #160.
