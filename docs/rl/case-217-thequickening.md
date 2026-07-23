# Case #217 — TheQuickening (ActiveAbilityType 1151, bloodMephiston) : face COMBAT

> Statut : **RESOLU / porte + valide live**. Porteur = `bloodMephiston` (BloodAngels, lineup, 1 unite).
> Categorie audit = EFFECT/BUFF. La face DECISION etait deja portee
> (`engine/playbook/noncomparable/the_quickening.py`, #46/#32) ; ce cas porte la face COMBAT
> (`ExecuteBehaviour`) qui etait un **NO-OP silencieux** (1151 absent de `ABILITY_CLASSES`).

## 1. Artefact natif (decompile = verite)

- `TheQuickeningAbility.ExecuteBehaviour @181211d50` (ctor `@181213150`).
- Sous-behaviours : `GetMoveOutBehaviour @181212aa0`, `GetMoveInBehaviour @181212940`,
  `GetTriggerMovementAbilitiesBehaviour @181213050`, `GetTriggerAttackBehaviour @181212cd0`.
- Formule free-attack : `DSLFactory.PercentageOfAttackCappedAtMax @180df8530`.
- Champs selecteurs sur le contexte DSL `(*(ability+0x30))` : `+0x148` Self, `+0x160` Caster,
  `+0x168` CasterTile (position d'origine, `SetCache`), `+0x178` Target (la TUILE cast).

### Arbre (7 `AActiveAbility.Execute` sequentiels)

1. `SetCache(CasterTile@0x168) & Reserve(Caster@0x160, Target@0x178) & MoveOut(Caster) & MoveOut(Attackable@Target)`
2. `MoveIn(Caster -> Target) & MoveIn(Attackable -> CasterTile@0x168)`
3. `TriggerMovementAbilities(Caster)`  = `If(unit==Caster, AddFlag(unit,1)) & EvaluateAbilities(0x1c=28) & RefreshEffects(7)`
4. `TriggerAttack(Caster)`
5. `TriggerMovementAbilities(Attackable)`
6. `TriggerAttack(Attackable)`
7. `InvalidateCaches`

- `GetMoveOutBehaviour(unit)` = `RemoveEffect(EffectFromOwner(unit,0x19)) & AddEffect(0x414 Untargetable,
  caster-src, unit) & MoveUnit(unit -> Null)` (lift off-board, marqueur transit).
- `GetMoveInBehaviour(unit, tile)` = `MoveUnit(unit -> tile) & RemoveEffect(unit, 0x414)` (atterrissage).
- `DSLFactory.Attackable @180deaa50` = `UnitsWithoutTrait(0x1b=27)` -> le swap-unit = occupant de la
  tuile cible SANS trait 27.
- `GetTriggerAttackBehaviour(unit)` = `If(HasFaction(unit, 0xe=14=BloodAngels),
    AddStatOverrideEffect(unit, 0x510 Attack_Override, PercentageOfAttackCappedAtMax(Attack, dmgPct, maxDmg))
    & AddEffect(0x529 ForcedInMelee) & PerformAIAttackFromCurrentPosition(unit)
    & RemoveEffect(unit, 0x510) & RemoveEffect(unit, 0x529))`.
- `PercentageOfAttackCappedAtMax(attack, 3, cfg13, cfg74)` = `min(cfg13, PercentageOf(StatAmount(Attack,3), cfg74))`
  = `min(maxDmg[level]xmult, round(Attack x dmgPct[level]/100))` — `cfg13`(ConfigVar 0xd)=maxDmg (cap,
  rarity-scale), `cfg74`(ConfigVar 0x4a)=dmgPct (percentage, non rarity-scale). Gameconfig `TheQuickening` :
  `maxDmg`(rarity), `dmgPct`, `range:2`.

## 2. Mecanique (net observable)

Cast TILE-TARGET (le joueur/IA choisit une TUILE a portee-mouvement 2). Sur execution :

1. **ECHANGE** : le caster se teleporte sur la tuile ciblee ; l'unite eventuellement presente y est
   deplacee vers la tuile d'origine du caster (clean swap).
2. **FREE MELEE ATTACK** (caster PUIS unite-echangee, chacun SI BloodAngels) : attaque melee immediate
   depuis la nouvelle position, Attack OVERRIDE = `min(maxDmg[meph_lvl]xmult, round(unit.Attack x
   dmgPct[meph_lvl]/100))`. Config (maxDmg/dmgPct/level/mult) = celle de l'ability de MEPH ; Attack per-unit.
3. Les effets `Untargetable(0x414)` / `ForcedInMelee(0x529)` / `TemporaryStatOverride(0x510)` sont
   **transitoires** : ajoutes ET retires DANS le cast (net-zero, AUCUN effet persistant).

### Mesure live (probe_217, runner build seed 31337, MC1_67)

- cast meph(2,6) sur tuile ally(4,7) -> POST **meph=(4,7), ally=(2,6)** (SWAP net).
- effets transitoires Untargetable/ForcedInMelee/TemporaryStatOverride tous ajoutes+retires (net-zero).
- `Attack_Override` live : meph=**1204**, ally=**4818**. Formule offline (Attack meph=1003 x120% -> 1204 ;
  ally=4015 x120% -> 4818 ; cap maxDmg=4986 non liant ; level 50, mult 180) == live **exact** (both).

## 3. Port

- `scripts/python/engine/runner/abilities/loki/quickening.py` — `TheQuickeningAbility.execute_behaviour` :
  - SWAP via `MoveUnitOperation` (pose la position sans check d'occupation ; le natif lift-off puis MoveIn
    -> l'echange direct rend l'etat NET identique) ;
  - free-attack faction-BloodAngels via `set_stat_override(ATTACK, V)` (= le canal 0x510) + le pipeline
    d'attaque normale (`AttackDamageOperation.execute`, arme melee auto a dist 1) + `remove_stat_override`
    (net-zero) ; `V = _quickening_override` (mirror `PercentageOfAttackCappedAtMax`).
- Enregistrement : `ABILITY_CLASSES[1151]` (`handler.py`), re-export `loki/__init__.py`.
- `sets_end_turn_flags`/`sets_active_ability_used_flag` = defaut (1151 absent des inventaires d'override
  base.py ; confirme par le walk stages : le tour de meph se termine apres le cast, step 16 = autre unite).

## 4. Validation adversariale

- **Test offline e2e** `tests/engine/runner/test_the_quickening_live.py` (pattern thunderous_assault,
  DETERMINISTE : `load_state` + positions controlees + MT `dumpRng`) : SWAP (caster->T, ally->C) +
  free melee attack du caster BloodAngels sur l'ennemi adjacent (hp cible decroit). **PASS**.
- **Probe live** `probe_217_thequickening.py` (pattern 202c) : (A) SWAP live ; (B) effets transitoires
  net-zero ; (C) override formule offline == live (meph 1204, ally 4818) ; (D) confrontation offline
  (`load_state` PRE-cast + rejoue le message -> meme SWAP que live). **VERDICT PASS**.
- **Zero-regression** `engine_agreement_stages.py --build --seeds 31337` : ability 13/13, move 18/18,
  prediction 10/10, utilite 10/10 = **100%**. step 15 u81 ab=1151 tgt=52 **MATCH** (decision intacte).
- Guard `test_turnflow_endturn_flags.py` (chemin handler) : 9/9 PASS.

## 5. Residus documentes (NON couverts)

- **Roll de degat de la free-attack = RNG** : non bit-exact offline (choix de cible + tirage). Approx
  faithful-structured (comme MasterOfTheTutelaries / ScarabSummon) ; en replay-diff, un cast 1151 peut
  desyncer la MT APRES le coup. Reste PREFERABLE au no-op (qui desyncait les POSITIONS, divergence plus
  large). Cible de `PerformAIAttackFromCurrentPosition` approximee par l'ennemi ADJACENT le plus proche
  (ForcedInMelee -> melee dist 1) ; tie-break id.
- **EvaluateAbilities(0x1c=28)** (phases 3/5, on-move triggers) NON porte -> surface passive separee
  (aucun on-move passif BloodAngels au roster teste ; `AddFlag(1)`/`RefreshEffects(7)` idem).
- **Filtre `Attackable = UnitsWithoutTrait(0x1b=27)`** du swap-unit approxime par « toute unite vivante
  sur la tuile cible autre que le caster » (aucune unite trait-27 sur une tuile de swap teste ; le swap
  ne cible pas les tuiles ennemies en jeu AI reel — la decision ne les valorise pas).
- **`Reserve` / `SetCache` / `InvalidateCaches` / `EffectFromOwner(0x19)`** = plomberie DSL sans effet
  net observable (memoisation de tuile, reservation, invalidation de cache) -> non materialises.
- **FORK de port `PerformAIAttackFromCurrentPosition` (finding relecture orchestrateur, au merge)** :
  le meme noeud natif a DEUX mirrors — `loki/summon.py::perform_ai_attack_from_current_position`
  (#202-C : nearest enemy toutes portees + gate `_in_attack_range` + dispatch `after_hit_normal_attack`
  avec profils) et `quickening.py::_free_melee_attack` (#217 : nearest ADJACENT + `AttackDamageOperation.
  execute` SANS dispatch after-hit). Divergence structurelle (`feedback_check_own_port_before_re`) +
  la free-attack Quickening ne pompe PAS les triggers after-hit (ex. un hit Psychic pres d'un porteur
  1197 devrait chainer un Screamer ; on-kill triggers idem). A UNIFIER en une seule feuille qui lit le
  contexte (ForcedInMelee -> domaine adjacent) et dispatche l'after-hit. `[opus]`, fix-forward.
