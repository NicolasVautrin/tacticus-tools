# Case study #70 : gate ACTEUR-MORT — l'attaque d'un attaquant mort est un NO-OP (combat)

## Symptome (residu remonte par #65, axe reetiquete)

Le residu documente en fin de `case-65-noblocking-block-bypass.md` (« seed 123 u95->u81/u83 :
`live_dmg=0` vs `off=2924`, blk=None -- attaque Psychic sur cible Infiltrate/untargetable ») etait
etiquete **cible-eligibilite (Infiltrate/untargetable)**. Cette etiquette est **REFUTEE**.

- **u95** = astraPrimarisPsy (Psyker, team 1), attaque normale Psychic (id 69, `Loki_NormalAttack`).
- **u81** = tauDarkstrider (team 2), effets `[StructuralAnalyserDmgBoost, StructuralAnalyser_Visual,
  RangedSpecialist, Infiltrate]`.
- **u83** = templAggressor (team 2), effet `[CrushingStrike]` — **PAS d'Infiltrate**.

Les deux cibles (Infiltrate ET non-Infiltrate) donnent le MEME `live_dmg=0` -> la cause n'est pas un
trait de cible.

## Diagnostic (mesure du discriminant, RE = verite)

**Signal decisif : `live_ndraw=0`.** Le live consomme ZERO tirage RNG pour ces attaques (vs `live_ndraw=9`
pour u95->u79 la meme passe) -> l'attaque est un **no-op complet cote live** (pas une immunite qui roulerait
puis annulerait le degat).

**Cause reelle = l'ATTAQUANT est MORT.** L'etat capture (dv2/ob2 PRE-attaque de `probe_65_block_repro`)
montre **u95 hp=0, isDead=True** pour les deux cas. Le residu #65 est un **artefact de la boucle sequentielle**
du probe : il traite les cibles d'u95 en serie et, entre u79 et u81, u95 MEURT.

Mecanisme de la mort (deterministe seed 123, board MC1_67) : u95 drive au contact -> se deplace en (4,6)
(overwatch -2884 -> hp 2638) -> attaque u79 (genesKelermorph) -> **hp=0** (retaliation/overwatch au coup).
Les iterations suivantes (u81, u83) forcent alors une attaque depuis un u95 **deja mort**.

**Discriminant vivant/mort (meme position (4,6), meme cible, meme distance) :**

| attaquant u95 | -> u81 (Infiltrate) | -> u83 |
|---|---|---|
| **VIVANT** (hp>0) | live 2873 | live 3594 |
| **MORT** (hp=0)   | live 0, ndraw 0 | live 0, ndraw 0 |

-> la SEULE variable est la liveness de l'attaquant. u81 (Infiltrate) et u83 sont parfaitement ciblables
et prennent des degats normaux quand u95 est vivant. **Ce n'est ni un axe cible-eligibilite, ni un axe
pipeline-de-degat-a-0 : c'est un gate ATTAQUANT-liveness.**

### Racine (RE decompile = verite, gqfc5mff6c)

- `ActiveAbilityOperation.ExecuteInternal @180e44ec0` gate le CASTER EN AMONT de toute execution
  (call site `IsDead` a `0x180e45cff`, early-return `~0x180e45d0c`) :
  ```c
  if (EntityExtensions.IsUnit(caster) != 0) {
    if (UnitExtensions.IsDead(caster, battle) != 0) return 0;   // NO-OP, 0 RNG, 0 degat, 0 flag
  }
  ```
- `UnitExtensions.IsDead @180ed8050` = `!IsAlive(caster) && !HasFlag(caster, 9=Fled)`.
- `HealthComponent.IsAlive @180f9ed10` = `hp >= 1` (teste `FillUpStat.CurrentValue @+0x18`).
- L'attaque normale native EST une ActiveAbility per-unite (#139) -> passe par le MEME gate
  ExecuteInternal (normal-attack ET active-ability).
- `AttackDamageOperation.Execute @180e60c70` (que l'offline `execute` mirror) n'a **AUCUN** gate liveness
  -> le gate vit au niveau OPERATION (ExecuteInternal), pas dans l'operation de degat.

Un caster a hp=0 encore sur le board (IsAlive=false, non-Fled) -> `IsDead`=true -> `ExecuteInternal`
retourne 0 avant tout roll. Exactement l'observation live (`live_ndraw=0`, `live_dmg=0`).

Verdict : **quirk porte — gate ACTEUR-MORT manquant cote offline.** L'offline sur-executait une attaque
complete (2924) depuis un attaquant mort ; le natif la no-op.

## Fix (mirror 1:1)

Gate au niveau DISPATCH offline (mirror d'ExecuteInternal, en amont de toute selection/boucle RNG) :

- **`engine/runner/components.py`** : helpers `unit_is_alive` (mirror `HealthComponent.IsAlive @180f9ed10`,
  hp>=1) et `unit_is_dead` (mirror `UnitExtensions.IsDead @180ed8050`, `!IsAlive && !HasFlag(Fled=9)` ;
  restreint aux unites — une source non-unite/tuile sans HealthComponent est toujours vivante).
- **`engine/runner/operations/damage.py`** `DamageHandler.visit_AttackUnitMessage` : si l'attaquant est
  `unit_is_dead` -> `self.last=None`, `after_hit=[]`, return (NO-OP, avant le dispatch MV71 et l'`execute`).
- **`engine/runner/abilities/handler.py`** `AbilityHandler.visit_ActiveAbilityMessage` : si le caster est
  `unit_is_dead` -> no-op (aucune behaviour, aucun degat, AUCUN flag de tour — le natif retourne 0 en amont
  du `AddFlagsAfterAbilityExecution`).

Le gate est **INERTE pour tout attaquant/caster vivant** (`unit_is_dead` -> False) -> aucune attaque
legitime n'est sur-immunisee. En replay/AI-sim les tours sont pris sur des unites vivantes -> zero
regression structurelle. Gate d'ELIGIBILITE en AMONT de la boucle de coups (pas de patch dans la
sequence RNG `_run_hits`).

## Validation (les deux faces + zero-reg)

Test-verrou LIVE-agreement deterministe : `tests/engine/runner/test_dead_attacker_noop_live.py` (seed 123,
board MC1_67).

- **CONTREFACTUEL** (`test_alive_attacker_deals_normal_damage`) : u95 VIVANT -> u79 : `off_dead=False`,
  `last` non-None (gate inerte), offline 2873 == live 2873. Le gate ne sur-immunise pas un attaquant vivant.
  (Cette attaque tue u95, deterministe.)
- **REPRO** (`test_dead_attacker_is_noop`, parametrise u81/u83) : u95 MORT -> u81 (Infiltrate) et u83 :
  live 0 degat / 0 tirage ; offline post-fix 0 degat / 0 tirage / `last`=None. Pre-fix l'offline
  sur-executait 2924. off == live == 0.
- **Zero-reg CIBLES (10 PASS, 0 FAIL)** : `test_dead_attacker_noop_live` (3) ; `test_noblocking_bypass_live`
  (2, meme zone #65) ; `test_runner_attack_live` (2, gate visit_AttackUnitMessage attaquant vivant) ;
  `test_damage_ability_live` (1, gate visit_ActiveAbilityMessage caster vivant) ; `test_damage_roll_live` (2).

## Non couvert / residus documentes

- **Vecteurs after-hit / overwatch / triggers** appelant `execute*` DIRECTEMENT (pas via message) : leur
  caster-liveness releve de leur PROPRE reachability (un overwatcher/retaliateur mort ne devrait pas tirer).
  Non exerce par ce cas ; axe separe (le gate #70 couvre les deux dispatch d'ability : attaque normale +
  ability active, = les deux points ExecuteInternal du natif).
- **Correction du residu #65** : la note de fin de `case-65-noblocking-block-bypass.md` (etiquette
  Infiltrate/untargetable) est reetiquetee ici — attaquant mort, PAS cible-eligibilite.
- **Portee pratique** : le gate est un no-op en replay/AI-sim (attaquants toujours vivants) ; il durcit le
  harnais de mesure (les probes qui FORCENT une attaque depuis un etat arbitraire — le patron de tous les
  probes de degat — matchent desormais le live meme quand l'attaquant est mort).
