# Case-35 — LordOfTempests `AddIce` (triggered 1194, Njal spaceStormcaller) : face RUNNER « pose de glace »

**Statut : LIVRÉ + VALIDÉ LIVE (2/2 replay-diff + 3 gardes).** Build `gqfc5mff6c`, session 2026-07-22.
Complément runner de la face DECISION déjà portée (#29 : `LordOfTempestsExtraDamageEffect`,
`extra_damage.py` — +extraDmg × Count(Ice ring-1 de la position d'attaque), validée bit-exact 31337 s18).
i2 : « Njal's normal attacks deal +237 Damage for each hex surrounding him that is covered in Ice.
**The hex of each enemy that is hit by Njal's normal attacks is covered in Ice at the end of the attack.** »
La 2e phrase = ce case.

## 1. Artefact natif (arbre DSL pur — classification #149 : DSL, pas d'impératif)

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility` :

- **`CreateTrigger @181108670`** = `OnNormalAttackOrSmite() & get_OwnerIsCaster`.
- **`CreateBehaviour @1811085d0`** = feuille UNIQUE
  `AddEffect(0x11=Ice, AbilityStateReference, source=Self@0x148, cible=Tiles(Target@0x178), <Nullable ZÉROÉ>, 0)`
  → pose l'effet **Ice (17)** sur la MainTile de la cible touchée ; Nullable zéroé = pas de
  `TurnsFromRounds` → `DefaultAmountOfRounds(0x11)=2` (switch @181559ff0, déjà transcrit
  `effects.py _DEFAULT_ROUNDS[0x11]=2`). `source=Self@0x148` == caster (triggered Owner==Caster).

### `OnNormalAttackOrSmite @180df7c70` — décomposé (le « Smite » n'est PAS un flag)

```
On(0x26=38 NormalAttack)  |  ( On(9=Attack) & <trigger DAT_18322f680>(DirectAbilitySelector(AbilityOrEffect 0x3f5=1013)) )
```

Le 2e terme alloue la **MÊME classe `DAT_18322f680`** (même ctor gshared MISLABELÉ
`HasUsedActiveAbilityThisTurnTrigger @180e03c50`, refcount 132) avec le **MÊME
`DirectAbilitySelector(0x3f5=1013)`** que la 2e branche d'`IsNormalAttack @180df4690` — verdict
déjà acquis `dsl-wave3-specs.md` « IsNormalAttack [PROUVE] » : sémantique = **« l'ability COURANTE
de l'event est du KIND attaque-normale (marqueur 1013) »**, PAS « has-used-this-turn ». Le splash
« Smite » du trait Psyker porte `AbilityOrEffect(1013)` (case-34, chaîne Njal) ⇒ branche 2 = le
coup de smite → **la victime du splash Psyker est glacée aussi** (cohérent avec « each enemy that
is hit »). Une attaque d'ability ordinaire (ex. Stormcaller 1113) ne porte PAS 1013 → pas de glace
LordOfTempests sur ses coups (la zone de glace de Stormcaller = SON propre artefact,
`StormcallerAbility.GetAddIceTiles @18120cf70`, NON porté — hors périmètre #35).

## 2. Port (mirror 1:1)

- **`engine/runner/operations/triggers/loki/lord_of_tempests.py`** (NOUVEAU) :
  `lord_of_tempests_add_ice_tree()` = `AddEffect(Ice=17, "Ice", Tiles(Target()), duration_rounds=None)` ;
  `LordOfTempestsAddIceAbility(TriggeredAbility)` — `matches` = OwnerIsCaster + (`On(38)` |
  (`On(9)` & `ev.ability_type == 0x3f5`)) ; behaviour via `entities_from_state` + ExecutionContext
  (patron RadSaturation). Enregistré `ABILITY_TRIGGERS["LordOfTempests"]` (dispatch.py — Njal
  `passiveAbilities=['LordOfTempests']`).
- **Payload d'event `ability_type`** (mirror du champ AbilityOrEffect de l'event natif, lu par
  `DirectAbilitySelector`) : `TriggerEvent.ability_type` (défaut None) ← `after_hit_ability_attack`
  ← `execute_ability_attack`/`execute_normal_like` ← feuille `AttackWithAttackDamage(ability_type=...)`.
  SEUL le smite Psyker le renseigne (`psyker_smite_tree` → `0x3f5`) ; tous les autres sites = None
  (défauts additifs, zéro changement de comportement).
- **Couplage COMBAT de la face snowball** : `damage_model._positional_att_ctx(state, unit_id)`
  (NOUVEAU) = `{att_pos, tile_effects_by_pos}` du centre + ring-1, effets DYNAMIQUES lus de
  `state.effects.by_unit[tile_id]` (même lecture que le PickTile MV71) + covers terrain — threadé
  par `attacker_modifiers` → `build_attacker_modifiers_from_effects(att_ctx=...)`. Avant #35 le
  combat passait `att_ctx=None` → `LordOfTempestsExtraDamageEffect` INERTE en sim (count=0).
  Seul consommateur d'att_ctx à ce jour → rayon d'impact limité aux porteurs LordOfTempests.

## 3. Validation (`test_lord_of_tempests_ice_live.py`, 2/2 + gardes 3/3)

1. **Poseur** (seed 35001, d=2 RANGED) : replay-diff `AttackUnitMessage` — NOUVELLES tuiles
   glacées live (tileMeta) == offline (`state.effects` tile-ids) = {tuile de la cible} ; dégât
   attaque-1 bit-exact et SANS bonus (la glace se pose APRÈS le dégât, « at the end of the attack »).
2. **Snowball** (seed 35002) : attaque 1 pose la glace, puis Njal drivé ADJACENT (d=1, ≥1 hex
   glacé ring-1) → dégât attaque-2 live == offline BIT-EXACT (le +extraDmg×count est LE
   discriminant : couplage att_ctx manquant ⇒ divergence d'exactement extraDmg×count par coup).
   La glace offline est seedée du tileMeta live (gap d'hydratation, cf. §4).
3. **Gardes** : `test_psyker_splash_live` 1/1 (feuille `AttackWithAttackDamage` + vecteur ability
   avec le nouveau param) + `test_damage_roll_live` 2/2 (visiteur + `attacker_modifiers` threadé).

## 4. Résidus (non bloquants, à promouvoir sur miss d'agreement)

- **Branche 2 (glace sur la victime du smite) non exercée LIVE** : exige un 2e ennemi adjacent à
  la cible (build mono-ennemi). Structurellement câblée + unit-testée (5 branches `matches`) ; le
  threading emprunte le chemin Psyker déjà bit-exact. `[opus]`.
- **`is_normal_attack` face attaquant toujours True dans le foyer combat** (pré-existant) : si une
  attaque d'ABILITY de Njal était simulée (Stormcaller non porté), le bonus snowball s'appliquerait
  à tort (l'i2 dit « normal attacks »). Inerte aujourd'hui. Le smite (normal-like 1013) le reçoit —
  plausible-correct, non mesuré. `[opus]`.
- **`load_state` n'hydrate PAS les effets de TUILE** d'un snapshot mi-bataille (le test 2 les seede
  du tileMeta). N'affecte pas les walks complets (notre trigger pose la glace en simulant). `[opus]`.
- **Stormcaller (active 1113) non porté runner** — sa pose de glace de zone
  (`GetAddIceTiles @18120cf70` : cible + ring-1) et ses 3× hits AoE = tranche dédiée si besoin. `[opus]`.
- **Mécaniques ICE aval toujours GATE** (pré-existant, terrain-effects.md §2) : blocage de mouvement
  (`NotBlockingMovementOfTraits(0x11)`, #131) et crit-bonus (`IceEffect.
  CreateEffectDamageBonusForAttack @180f44940`, direction/sélecteur À TRANCHER). Le stun Flying de
  Stormcaller idem.

## VAs
`LordOfTempests_AddIceAbility.CreateBehaviour @1811085d0` · `CreateTrigger @181108670` ·
`DSLFactory.OnNormalAttackOrSmite @180df7c70` · `DSLFactory.IsNormalAttack @180df4690` (nœud
branche-2 partagé, classe DAT_18322f680 + ctor gshared @180e03c50 + `ShouldTrigger @180e037d0`) ·
`DSLFactory.AddEffect @180de6d20` · `StaticBattleRules.Effect.DefaultAmountOfRounds @181559ff0` ·
`LordOfTempests_ExtraDamageEffect.{GetHexesIncreasingDamage @180f56b40, CreateEffectDamageBonusForAttack
@180f569a0}` (face DECISION, #29) · `StormcallerAbility.GetAddIceTiles @18120cf70` (hors périmètre).
