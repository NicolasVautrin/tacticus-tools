# Case study #65 : le trait `NoBlocking` du PROFIL de degat bypasse le block (combat)

## Symptome (residu block pre-existant, code-independant)

Sur l'attaque normale, l'OFFLINE (replay) declenchait parfois un BLOCK que le LIVE n'appliquait
PAS -> l'offline sortait plus BAS. Cas de repro FIXE (deterministe) :

- **seed 123, u95 (astraPrimarisPsy) -> u79 (genesKelermorph)** : `off=1569` vs `live=2873`.
- Prouve code-independant (rejoue sur le `damage.py` d'avant le split #60 = divergence identique)
  -> vrai residu de l'etage BLOCK, PAS une regression du refactor.
- Meme classe de residu que le block-roll non-validable de PsychicFortress (effet ExtraBlock 1007) :
  fermer ce cas DEBLOQUE la validation bit-exact de tous les sources de block (BeastSlayer,
  PsychicFortress, Daemon, AnvilShield...).

## Diagnostic (mesure par etage, discriminant a/b/c)

Repro deterministe : `probe_65_block_repro.py --seed 123` (replique le fixture
`test_offline_attack_reproduces_live_damage` epingle seed 123, capture chaque cas mono-coup +
sauve un JSON rejouable). Mesure `probe_65_block_measure.py` (replay OFFLINE avec/sans block).

Mesures sur le cas u95->u79 :

| variante offline | total | did_block | tirages (main hit) |
|---|---|---|---|
| execute() AVEC block | 1569 | True  | value(1) + block(1) = 2 |
| execute() SANS block | 2873 | False | value(1) = 1 |
| **LIVE (u79)**       | **2873** | - | - |

- **offline-SANS-block == live EXACT (2873)** -> le stage VALEUR est correct ; seul le block est de trop.
- La cible genesKelermorph porte le trait `BeastSlayer` -> effet `BeastSlayer_ExtraBlock` = source de
  block (chance 10 / amount = 100% FixedArmor = 1304). L'offline la roule et reussit (10%) -> -1304.
- **L'attaque est `ranged=True profile=Psychic`** (astraPrimarisPsy Psyker). Le #72 (block APPLIQUE et
  valide) etait un cas MELEE (necroDestroyer melee -> orksNob). Discriminant : **(a)** le natif ne roule
  PAS le block pour cette paire -- le block source est SUR-INCLUS cote offline.

### Racine (RE decompile = verite, gqfc5mff6c)

- `gameconfig` : le profil **`Psychic` porte `Traits=['NoBlocking']`** (PiercingRatio 100).
- `DamageTrait.NoBlocking = 0` (enum `entities/damage_trait.py`, dump.cs TypeDefIndex 24353).
- `AttackDamageOperation.ExecuteHit @180e5eff0` :
  `cVar = DamageProfile.HasTrait(profile, 0=NoBlocking); if (cVar != 0) *(metadata+0x2a) = 1;`
  -> le flag propage dans la metadata passee a la sous-op 0x42.
- `DamagePrediction.CalculateDamageOperation @18102dc30` (sous-op 0x42, le split + roll block) :
  la branche block/evade est GATEE par `if ((metadata[3] >> 0x30) == 0) { ...slot+3/slot+2
  (ApplyRandomBlockDamage)... }`. Le flag NoBlocking (metadata+0x2a) rend ce test faux -> **toute la
  branche block/evade est SKIPPEE** -> AUCUN tirage block consomme (le natif ne roule pas le block).
- Doctrine (wiki.md l.185-195) : « `Psychic` (PiercingRatio 100 + NoBlocking) = bypass definitif ;
  `NoBlocking` (Cannot be blocked) bypasse le Block ».
- La docstring `damage_trait.py:13` documentait deja : « NoBlocking (0) : PredictAttackRaw skip la
  boucle multi-outcome -- **non wire** » : NoBlocking etait cable en prediction mais PAS dans le COMBAT.

Verdict : **quirk porte -- (a) source de block sur-incluse** ; l'offline ignorait le trait `NoBlocking`
du profil de degat dans la chaine block du combat.

## Fix (mirror 1:1)

Gate `AttackDamageOperation._block_sources(tsc, effects, armor, damage_profile=None)`
(`engine/runner/operations/damage.py`) : si le profil porte `DamageTrait.NoBlocking`, retourne `None`
AVANT toute source (base scalaire GetStat(7/8) ET sources d'effet) -> 0 tirage block. Mirror du flag
`ExecuteHit` -> skip block de `CalculateDamageOperation`.

Cable dans les 3 vecteurs (`engine/runner/operations/damage_ops.py`) : `execute` (attaque normale,
`_profile`), `execute_ability_attack` + `execute_normal_like` (`damage_profile`).

Coups additionnels #179 (`engine/runner/operations/additional_hits.py`) : le flag NoBlocking est
PER SOUS-OPERATION (le natif relit `DamageProfile.HasTrait` du profil DU COUP courant dans ExecuteHit) ->
re-gate `block_sources` sur le profil DU GROUPE (un coup Psychic InfernalPacts bypasse le block meme si
l'arme principale ne l'etait pas).

## Validation (les deux faces + zero-reg)

- **Cas repro** (`probe_65_block_repro.py --seed 123`) : POST-fix u95->u79 `off_total=2873 ==
  live_dmg=2873`, `did_block=False`, 1 tirage de moins (le block-roll spurious disparait). Non-divergent.
- **Generalisation adversariale** (`probe_65_generalize.py`, eldarFarseer = Piercing melee + Psychic
  ranged vs orksNob BeastSlayer, positions DRIVEES) :
  - RANGED-Psychic (NoBlocking) : `off per_hit=[1618,1615] == live`, `did_block=False`, draws 2==2 --
    BIT-EXACT (block bypasse).
  - MELEE-Piercing (blockable)  : block fire toujours (`did_block=True`, hit1=0 des deux cotes),
    draws 4==4 (le fix ne casse PAS le block blockable). (Residu VALEUR pre-existant de ~33 sur le hit 2,
    hors scope block : Piercing n'est PAS NoBlocking -> chemin byte-identique a avant le fix.)
- **Test-verrou LIVE** (`tests/engine/runner/test_noblocking_bypass_live.py`, deterministe,
  independant version/seed) : astraPrimarisPsy Psychic -> orksNob BeastSlayer. Verifie (1) la source de
  block EXISTE sans gate profil et DISPARAIT sous profil Psychic ; (2) l'offline NE bloque PAS
  (did_block False) + per-hit == live + PV egaux. 2/2 PASS.
- **Zero-reg tranche degat/block** (tests CIBLES) :
  `test_beast_slayer_block_live` + `test_damage_block_live` (4) ; `test_damage_crit_live` +
  `test_damage_normal_armored_live` + `test_damage_roll_live` + `test_psychic_fortress_aura_live` (9) ;
  `test_runner_attack_live` (2) ; `test_cord_claw_live` (#179) (2) ; `test_noblocking_bypass_live` (2).
  Tous verts.

## Non couvert / residus documentes

- **PREDICTION (slice SEPAREE, meme racine) : FERME par #69** (`docs/rl/case-69-noblocking-prediction-block.md`).
  Le gate NoBlocking est desormais threade dans `defender_prediction_block_amount(scene, tgt, damage_profile)`
  (`engine/playbook/prediction/_shared.py`) aux 5 call-sites (`normal_attack.py` x4, `abilities.py`) -> un
  attaquant Psychic ne deduit plus de block (`block_raw_min` None, killSure sur le scalaire raw). RE-confirme
  decompile : `PredictAttackRaw @181032fb0` fait `DamageProfile.HasTrait(profile, 0=NoBlocking)` (@181035b9c)
  et SKIP la boucle de construction du scenario block. Test-verrou `tests/engine/test_noblocking_prediction_live.py`.
  **Residu restant (per-groupe, symetrique combat #179)** : les coups ADDITIONNELS #179 au profil NoBlocking
  (aura InfernalPacts Psychic, porteur Abraxas thousInfernalMaster) partagent le `defender_block_amount` gate
  sur le profil de L'ARME PRINCIPALE dans `_with_block` -> une attaque a arme BLOCKABLE + groupe Psychic
  InfernalPacts deduirait le block sur le coup Psychic aussi (le combat, lui, re-gate par groupe :
  `additional_hits.py` L138-143). Non ferme (validation Abraxas dediee requise) ; cf. case-69 §residu.
- **NoBlocking vs EVASION** : le flag natif (metadata>>0x30) skippe block ET evade dans
  `CalculateDamageOperation`. L'evasion offline n'est pas exercee (`evasion_branch=False` partout) -> le
  gate NoBlocking cote offline ne couvre que le block (moot pour l'evade tant que non implementee).
- **Residu SEPARE observe (hors #65)** : seed 123 u95->u81/u83 (`live_dmg=0` vs `off=2924`, blk=None) --
  attaque Psychic sur cible Infiltrate/untargetable qui prend 0 en live ; pas un probleme de block
  (aucune source), axe cible-eligibilite distinct.
