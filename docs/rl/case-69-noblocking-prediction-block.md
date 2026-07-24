# Case study #69 : le trait `NoBlocking` du PROFIL de degat bypasse le block deduit (PREDICTION)

## Symptome (residu DIRECT de #65, face PREDICTION)

#65 a gate le block du COMBAT sur le trait `NoBlocking` du profil de degat (`AttackDamageOperation.
_block_sources(damage_profile)` -> profil Psychic = aucune source, 0 tirage). La face **PREDICTION avait
le MEME gap NON corrige** : `defender_prediction_block_amount` (`engine/playbook/prediction/_shared.py`)
+ `get_multi_hit_attack_prediction._with_block` (`engine/services/damage_prediction.py`) ne gataient PAS
`NoBlocking` -> une prediction d'attaque Psychic sur-comptait le block DEDUIT.

- Impact : le scenario `list[0]@0x50` (port `block_raw_min`) alimente `killSure`/`WillBeKill` du composite
  Damage (`ProbableDamageEvent.composite_fields`, `killSure = will_min >= hp` avec `will_min = block_raw_min
  if not None else rawMin`). Un attaquant Psychic (block reellement bypasse au combat) voyait sa prediction
  DEDUIRE un block -> `will_min` sous-estime -> `killSure` PESSIMISTE (l'IA croit qu'un block sauve la cible
  alors qu'il est bypasse) -> selection de cible / priorisation de kill faussee.
- **N'affecte PAS le min/max de degat affiche** (`block_raw_min` est un champ SEPARE de `accurate_health_
  damage`/`dmgMin`/`dmgMax`) -> INVISIBLE aux tests degat/block et a l'agrement `test_predict_live`
  (oracle `decisionView` dmgMin/dmgMax) -> le gap etait silencieux.

## Racine (RE decompile = verite, gqfc5mff6c)

- `gameconfig` : le profil `Psychic` porte `Traits=['NoBlocking']` (PiercingRatio 100). `DamageTrait.
  NoBlocking = 0` (`entities/damage_trait.py`).
- `DamagePrediction.PredictAttackRaw @181032fb0` (le coeur de la prediction UN COUP) fait
  `IdunShared.Battle.DamageProfile.HasTrait(profile, 0=NoBlocking)` (call site @181035b9c) et STOCKE le flag,
  puis GATE la construction du scenario block :
  ```
  uVar17 = DamageProfile.HasTrait(profile, 0);          // @181035b9c  (0 = NoBlocking)
  local_res8 = uVar17;                                  // stocke le flag
  param_1[10] = <new List>;                             // la liste scenario block (VIDE par defaut)
  if ((blockList != 0) && ((char)local_res8 == '\0')) { // SI sources de block ET flag NoBlocking == 0
      for (...) { ... build block-adjusted scenarios ... }   // sinon SKIP -> liste reste VIDE
  }
  ```
  -> profil NoBlocking => `HasTrait != 0` => la boucle est SKIPPEE => scenario block VIDE => `get_WillBeKill
  @18102bef0` retombe sur le scalaire raw (pas de block deduit). C'est le **mirror EXACT** du gate COMBAT
  (`ExecuteHit @180e5eff0` pose metadata+0x2a -> `CalculateDamageOperation @18102dc30` skip block/evade).

Verdict : **quirk porte -- block deduit sur-inclus cote prediction** ; l'offline ignorait le trait
`NoBlocking` du profil dans la chaine block de la PREDICTION.

## Fix (mirror 1:1 du gate combat)

`defender_prediction_block_amount(scene, tgt_id, damage_profile=None)` (`_shared.py`) : si le profil porte
`DamageTrait.NoBlocking`, retourne `0` AVANT toute source (scalaire GetStat(7/8) ET sources d'effet du
defenseur) -> `_with_block` no-op -> `block_raw_min` reste None -> `killSure`/`WillBeKill` sur le scalaire
raw. Mirror 1:1 de `AttackDamageOperation._block_sources(..., damage_profile)` (retourne None si NoBlocking)
et du skip natif de `PredictAttackRaw @181035b9c`. Le param defaut `None` = retro-compat (aucun gate).

Cable aux **5 call-sites** en threadant le nom de profil deja disponible localement :
- `normal_attack.py` : `make_normal_attack_predictions` (arme, `prof_name`), `_make_mv71_drone_predictions`
  (`prof_name`), `get_additional_damage_prediction` (`prof`), `get_klaw_attack1_prediction` (`prof`) ;
- `abilities.py` : `generate_multi_hit_attack_prediction` (`profile_name`).

Reutilise `DamageTrait.NoBlocking` (`entities/damage_trait.py`) + `GC.damage_profile(name).Traits` (checks
name-based #156), pas de reinvention.

## Validation (les deux faces + zero-reg)

Test-verrou LIVE DETERMINISTE `tests/engine/test_noblocking_prediction_live.py` (independant version/seed) :
astraPrimarisPsy (arme Psychic = NoBlocking, melee+range) vs orksNob (BeastSlayer -> effet
`BeastSlayer_ExtraBlock`, source de block). Mesures live (build 777 MC1_67, runner isole) :

- **(1) GATE** (`test_pred_source_gated`) : `defender_prediction_block_amount(scene, tgt)` = **1507**
  (block source presente sans gate) ; sous profil `Psychic` = **0** (bypass) ; sous profil blockable
  `Bolter` = **1507** (block conserve). La source de block EXISTE et le gate la DISCRIMINE.
- **(2) E2E + DISCRIMINATION** (`test_pred_e2e_bypass_and_discrimination`) :
  - Discrimination via `get_attack_prediction` (meme cible) : block amount NON-gate (1507) ->
    `block_raw_min=2679` (block DEDUIT) ; block amount gate (0, Psychic) -> `block_raw_min=None` (bypass).
    Le gate est la SEULE difference.
  - E2E via le VRAI point d'entree `make_normal_attack_predictions` (tuile ranged hex-dist 2, arme
    Psychic resolue par `_weapon_pierce` = `Psychic`) -> `block_raw_min=None` : l'attaque normale Psychic
    reelle bypasse le block de bout en bout.
- **Zero-reg (tests CIBLES)** :
  - `test_predict_live` (agrement prediction dmgMin/dmgMax vs oracle `decisionView`) : 2/2 PASS (le gate
    block n'affecte PAS le min/max affiche -> aucun impact).
  - `test_noblocking_bypass_live` (2), `test_damage_block_live` (2), `test_beast_slayer_block_live` (2) :
    6/6 PASS (le fix ne touche QUE la slice prediction ; le gate combat merge #65 est intact).

## Non couvert / residus documentes

- **Per-groupe (coups additionnels #179) au profil NoBlocking -- SYMETRIQUE au combat #179, NON ferme.**
  Le combat re-gate le block PAR SOUS-OPERATION (`runner/operations/additional_hits.py` L138-143 :
  `g_block = None si groupe NoBlocking else block_sources`) car `ExecuteHit @180e5eff0` relit
  `DamageProfile.HasTrait` du profil DU COUP courant. La PREDICTION applique un SEUL `defender_block_amount`
  (gate sur le profil de L'ARME) a TOUS les coups via `_with_block`, y compris les `extra_groups`. Consequence :
  une attaque a arme **BLOCKABLE** + un groupe additionnel **Psychic** (aura `InfernalPacts` d'Abraxas
  thousInfernalMaster, effet 1198, profil `affectedDamageProfile`=Psychic, aux amis Chaos adjacents ring-1)
  deduirait le block sur le coup Psychic aussi (le natif le bypasse). Porteur SPAWNABLE (Abraxas) donc
  invalidable en principe, mais le scenario de validation dedie (Abraxas + ami Chaos a arme blockable
  positionne adjacent + cible a source de block + aura firant en prediction) n'est pas trivial -> laisse
  comme **candidat follow-up** (mirror per-groupe = ajouter le flag NoBlocking du profil de chaque
  `extra_group` et gater son `_with_block` a 0, cf. combat `additional_hits.py`). Impact borne : sous-compte
  `block_raw_min` de l'ordre du block-amount sur le(s) coup(s) Psychic additionnel(s) -> killSure legerement
  pessimiste pour un attaquant a arme blockable adjacent a Abraxas.
- **NoBlocking vs EVASION** : idem #65 -- le flag natif skippe block ET evade ; l'evasion offline n'est pas
  exercee -> gate NoBlocking cote prediction = block seul (moot pour l'evade tant que non implementee).
