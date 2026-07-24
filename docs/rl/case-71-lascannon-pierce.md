# Case 71 -- LasCannon pierce bonus (+50) : cablage du gate + valeur de la constante

## Symptome (audit DamageTrait)

`DamageTrait.LasCannon(3)` est porte par le profil de degat `Las` (gameconfig : `PiercingRatio=10`,
`Traits=['LasCannon']`). La formule de percage etait deja prete cote services
(`static_battle_rules.get_piercing_ratio` + `damage_prediction.get_attack_piercing_damage_ratio`
appliquent le bonus SI `profile_has_lascannon AND attacker_has_heavy_weapon_or_emplacement`), MAIS :

- le seul call-site (`entities/abilities/active_ability.py:205`, `NormalAttackAbility.get_pierce`)
  passait `profile_has_lascannon=False` EN DUR (et `lascannon_bonus` par defaut = 0) ;
- le foyer partage reellement utilise (prediction ET combat) `services/battle_query.select_weapon_pierce`
  reimplementait la formule INLINE (`prof_ratio + extra_pierce + dir_pierce`) SANS le bonus lascannon.

Resultat : le bonus n'etait JAMAIS applique offline (ni prediction, ni combat).

## RE (decompile = verite, gqfc5mff6c)

### `StaticBattleRules.Damage.GetPiercingRatio @181559a40`

    p = profile.PiercingDamageRatio                          # DamageProfile @+0x14
    if profile.HasTrait(DamageTrait.LasCannon=3)
       and attacker.HasTrait(HeavyWeapon=0x3e9=1001 | Emplacement=0x3f8=1016):
        p += **(int **)(DAT_183218fd8 + 0xb8)                # static_field[0] de StaticBattleRules.DamageTrait
    return clamp(0, 100, p)

### Constante = 50 (definitive)

`StaticBattleRules.DamageTrait$$.cctor @1815597c0` :

    **(undefined4 **)(DAT_183218fd8 + 0xb8) = 0x32;          # static_field[0] = 0x32 = 50

`DAT_183218fd8` = classe `StaticBattleRules.DamageTrait` (offset 0xb8 = `Il2CppClass.static_fields`).
`GetPiercingRatio` lit `iVar3 += **(int **)(cls + 0xb8)` = ce meme static_field[0]. Donc bonus = **50**.
(Le static_field +8 = la List `{0x3f8, 0x4b3, 0x4bb}` de `GetDamageTraitAbilities` -- hors sujet.)

### Les DEUX faces natives appellent GetPiercingRatio

- **PREDICTION/UI** : `GetAttackPiercingDamageRatio @181030a20` :
  `base = GetPiercingRatio(profile, attackerTraits)` PUIS `+ ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}
  + extraMin + extraMax`, clamp 0..100. Xrefs DATA-only (invoque par delegate/slot) = service partage.
- **COMBAT** : `GetBaseDamageWithFixedPiercedArmor @181030d10` (appele par `CalculateBaseDamageWithAll
  Modifiers @18102d726`, la fn per-coup partagee combat+prediction) : meme resolution interne
  `iVar4 = GetPiercingRatio(param_7, attackerTraits)` puis `GetDamageWithPiercing(dmg, pierce, armor)`.

Le port Python a UN seul foyer partage `battle_query.select_weapon_pierce` (prediction ET combat) : le fix
y ajoute le bonus via `get_piercing_ratio` -> les deux faces sont couvertes par une edition localisee.

## Fix (mirror 1:1)

- `services/static_battle_rules.py` : constante `W_LASCANNON_PIERCE_BONUS = 50` (VA citee) ; defaut du
  parametre `lascannon_bonus` de `get_piercing_ratio` = la constante (le natif la lit du static field,
  pas d'un param appelant -> intrinseque).
- `services/damage_prediction.py` : defaut `lascannon_bonus` de `get_attack_piercing_damage_ratio` = la
  constante (idem).
- `services/battle_query.py` : `select_weapon_pierce` calcule `profile_has_lascannon =
  DamageTrait.LasCannon.name in dp.Traits` et `attacker_hw_emp = UnitTrait.HeavyWeapon.name in ctx.traits
  or UnitTrait.Emplacement.name in ctx.traits`, puis `base = get_piercing_ratio(prof_ratio, ...)`. Les deux
  flags sont derives DANS la fonction depuis `ctx`/`dp` (aucun threading appelant).
- `entities/abilities/active_ability.py` : `NormalAttackAbility.get_pierce` calcule les flags depuis
  `self.caster` au lieu du `False` code en dur. NB : DEAD CODE actuel (aucun call-site ; prediction ET
  combat passent par `select_weapon_pierce`) -- rendu fidele pour ne pas re-introduire le gap si recable.

Traits gameconfig = NOMS de chaine (`DamageProfile.Traits` / `unit.traits`) -> checks name-based, reutilise
les enums existants `DamageTrait` (3) + `UnitTrait.HeavyWeapon` (1001) / `Emplacement` (1016).

## Validation

- **OFFLINE (test committe `tests/engine/runner/test_lascannon_pierce_offline.py`, 11/11)** :
  constante=50 ; `get_piercing_ratio` (60/10/10/10, clamp 100) ; `get_attack_piercing_damage_ratio` applique
  le bonus par defaut ; carrier reel `astraNpc2Lascannon` (Las Range4 + Emplacement) -> pierce 60 au range ;
  TOGGLE du discriminant (retirer Emplacement -> 10 ; ajouter HeavyWeapon -> 60 ; arme non-Las -> pas de bonus) ;
  le bonus CHANGE le degat de combat contre armure (`GetDamageWithPiercing` roll 3000 armure 1909 : pierce 60
  -> 1800 vs pierce 10 -> 1091) ; zero-regression pool (astraCreed/astraOrdnance sans HW/Emp -> jamais de bonus).
- **ZERO-REGRESSION LIVE** : `test_damage_normal_armored_live` (3 passed, combat pierce+armure bit-exact),
  `test_runner_attack_live` (2 passed). `test_damage_roll_live` (2 skipped : contrainte de scenario
  mono-coup, pre-existante, non liee au fix).

## Non-confrontable LIVE (patron CondemnorStake -- documente)

Le gate COMPOSE (profil Las ET attaquant HeavyWeapon/Emplacement) n'est satisfait par AUCUN carrier
spawnable :

- Les 18 unites a arme `Las` du gameconfig : les seules portant AUSSI HeavyWeapon/Emplacement sont des NPC
  (`astraNpc2Lascannon`) et summons (`astraSmnLascannon`), HORS du pool spawnable (`rl_duel build --list-pool`
  rank 17 : 97 units + 8 MoW, aucun ne combine Las+HW/Emp). L'injection seed-BC (patron SavageEchoes) ne rend
  pas les NPC normalisables (buildNormalizedBC les filtre) ; `astraSmnLascannon` n'est invoque que par
  `EnvFactionSummons:Custodes` (mecanique Environnement, non drivable).
- Les Las du pool (astraCreed, astraOrdnance) n'ont PAS HeavyWeapon/Emplacement -> pas de bonus (contrefactuel) ;
  les HeavyWeapon du pool (adeptRetributor, blackObliterator, darkaHellblaster, ...) n'utilisent PAS de Las.

=> validation par MIRROR + TOGGLE OFFLINE (spawnabilite verifiee AVANT ; aucun datapoint live mande sur un
artefact non spawnable, doctrine feedback_validate_discriminant_spawnable). Zero-regression : le bonus etant
un no-op prouve pour tout carrier spawnable, les tests combat live du pool restent inchanges.

## Verdict

Constante RESOLUE (50, cctor @1815597c0) + cablage du gate sur les DEUX faces via le foyer partage
`select_weapon_pierce`. Le gap etait un cablage (formule prete mais flag en dur / reimplementation inline
sans bonus), pas une divergence de formule.
