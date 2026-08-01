# #420-r1 — L'axe DÉGÂT de `DefenderOfTheGreaterGood` : le gate Psychic était nu

**Verdict : le port est FIDÈLE — aucune divergence trouvée. La tranche se ferme par la GARDE seule.**

Effets : `1182 DefenderOfTheGreaterGood_ExtraDmg` (`tauShadowsun`) et son jumeau drone `1306`
(`tauSmnDroneCommandLink`). Le canal COUPS (`1183`/`1307`) est un autre item — cf. `case-372`.

## Pourquoi la tranche existait

PR #420 a threadé `damage_profile` jusqu'aux modifiers ATTAQUANT (`damage_ops/ability.py`,
`damage_ops/normal_like.py`). Avant elle la clé était ABSENTE, donc
`!DamageProfileIs(0xd = Psychic)` ne fermait **jamais** : le port accordait le bonus même sur une
attaque Psychic. Le changement est RESTRICTIF — il corrige une sur-application — mais **aucun test
ne retenait ce gate** : les seules occurrences de `DefenderOfTheGreaterGood` dans les tests
portaient sur l'axe COUPS.

## RE (build `rnca9r7q6c`) — ce que le natif dit vraiment

`IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier` :

    trigger = get_OwnerIsCaster & IsRangedAttack() & !DamageProfileIs(0xd = Psychic)
    amount  = ConfigVar(8 = extraDmg, GetAbilityState(effet), config = effet+0x60)

Trois points que la seule lecture des NOMS ne donne pas :

1. **`ForAddition` est INLINE** (aucun `call` dans le corps). On tranche le canal à la DISPOSITION
   des champs : `IdunBattle.Entities.Effects.EffectBonus$$ForAddition` écrit son montant à `+0x10`,
   `...$$ForPercentIncrease` à `+0x08`. Le corps écrit `trigger` à `+0x00`, `0` à `+0x08`, `amount`
   à `+0x10` ⇒ canal **ADDITIF**.
2. **Les surcharges se tranchent par l'adresse du `call`** : `DamageProfileIs` a trois surcharges,
   c'est celle à **UN scalaire** ; `IsRangedAttack` en a deux, c'est celle **sans ability** (la même
   que `SpotterReworked_ExtraDamage`).
3. **L'additif est appliqué APRÈS le perçage/armure**, pas avant :
   `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` appelle
   `...$$GetBaseDamageWithFixedPiercedArmor` d'abord, puis le %-list, puis l'additif. La docstring du
   port disait « pré-perçage » — corrigée. Les docstrings voisines (`SpotterReworked`,
   `LordOfTheHost`, `Doom`, `BeaconOfRage`) portent la même affirmation et restent à corriger
   (résidu ci-dessous).

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector` :

    sel = AdjacentFriends(dsl, Owner, ownerTiles, unique = 1) - Owner
    sel = Unique( sel + UnitsFromFaction(SurroundingFriends(dsl, Owner, ownerTiles,
                                                            range = 2, unique = 1,
                                                            selectionType = 3), 9 = Tau, 3) )
    sel = UnitsWithRangedWeaponsExcludingDamageProfile(dsl, sel, 0xd = Psychic)
    if isDrone: sel = EntitiesIsNotTargetOfEffect(dsl, sel, int[]{ 0x49e = 1182 })

⚠ **Piège #419 confirmé sur ce site — les littéraux ne sont pas tous des rayons.**
`IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(this, unit, unitTile, unique)` n'a **aucun**
paramètre de rayon : le `1` du call-site est `unique`, et l'adjacence vient d'`AdjacentTiles`. En
revanche `IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(this, unit, unitTile, range,
unique, unitSelectionType)` en a un, et le call-site y passe bien `range = 2`. Les deux tiers sont
donc : **d = 1 toute faction**, et **d ≤ 2 T'au seulement**. Le port les avait justes.

`UnitsWithRangedWeaponsExcludingDamageProfile` monte un
`IdunBattle.Entities.Selectors.UnitsWithWeaponsSelector` à `minRange = 2` +
`excludedDamageProfile = Psychic` ; `...$$HasMatchingWeapon` exige qu'**une même arme** satisfasse
les deux. Non porté : subsumé par le gate d'attaque pour toute attaque d'ARME (résidu ci-dessous).

## Le montage qui confronte la bascule

Les 12 héros du lineup à arme ranged Psychic ont **tous** cette arme comme SEULE arme de portée ≥ 2 :
pour eux, filtre carrier et gate d'attaque ferment ensemble, et l'observable est le même.
`ultraTigurius` (melee Physical + ranged **Psychic** r2) est le bras Psychic ; `darkaHellblaster`
(Imperial, ranged non-Psychic) et `tauCrisis` (T'au) portent les tiers de géométrie.

Chaque bras rend TROIS séries sur le MÊME état : `live` (événements natifs), `offline` (rejeu du
port), et `no_aura` (même rejeu, effet `1182` retiré du porteur). `no_aura` est la **contre-épreuve
de sensibilité** — sans elle, deux absences se comparent et le vert ne prouve rien.

Mesuré (`probe_420r1_dotgg_extra_dmg.py`, MC1_67, ablvl 50 × mult 180 ⇒ `extraDmg = 499`) :

| bras | d(porteur) | profil natif du coup | live | offline | no_aura | Δ/coup |
|---|---|---|---|---|---|---|
| `darkaHellblaster` ADJACENT | 1 | non-Psychic | `[6930, 7105]` | idem | `[6306, 6481]` | **+624** |
| `ultraTigurius` ADJACENT | 1 | **13 = Psychic** | `[3336]` | idem | `[3336]` | **0** |

`624 = round(499 × 1,25)` — le ×1,25 aval est celui du bénéficiaire. L'armure de la cible est nulle
sur ce montage (`--hp-target` met `Armor`/`FixedArmor` à 0), donc l'étage perçage n'y est **pas**
exercé : la mesure établit que l'apport est additif et **par coup**, pas l'ordre additif/perçage
(celui-là est tranché au décompilé, ci-dessus).

## Contre-épreuve mutante — le cliquet MORD

Trois mutations du port, jouées et vérifiées (`git diff --stat` avant de conclure) :

| mutation | vue ROUGE |
|---|---|
| gate de profil retiré | `test_psychic_ranged_attack_gets_nothing` : `live=[2984] offline=[3483]` (**+499**) |
| gate de faction retiré (`d ≤ 2` sans `UnitsFromFaction`) | `test_ring2_non_tau_gets_nothing` : `live=[5522] offline=[6146]` (**+624**) |
| `is_melee is not False` → `is True` | `test_ranged_gate_is_tristate_offline` : clé absente ⇒ `Addition/277` au lieu de `None` |

## Les deux gates n'ont PAS la même polarité sur la clé absente

Ça ne se devine pas, et c'est ce que la garde fige :

* **`is_melee` est TRI-ÉTAT** (calque `SpotterReworked._trigger_ok`) : seul `False` ouvre ; `True`
  ferme, et `None`/clé absente **ferme aussi**. Corollaire de mesure (#422) : **retirer** cette clé
  FERME le gate au lieu de l'ouvrir — pour l'éprouver il faut **forcer** `is_melee`.
* **`damage_profile` absent laisse le gate de PROFIL OUVERT** : le natif compare à `13`, et un
  contexte sans profil vaut `DamageProfileType.None_ = -1`, hors égalité.

## Livré

* `tests/engine/runner/test_dotgg_extra_dmg_live.py` — 5 gardes offline (polarité du profil,
  tri-état de `IsRangedAttack`, deux tiers du sélecteur, magnitude sur le niveau du PASSIF du
  porteur, anti-double-comptage du drone) + 4 bras live.
* `probe_420r1_dotgg_extra_dmg.py` — la mesure.
* `_dotgg_aura_regime.py` — capture du profil natif du coup (TagKey `DamageProfileType` ; le TagKey
  `Attack_Weapon_DamageProfile` n'est PAS présent sur ces événements), fenêtre `tgt_dist` (une arme
  r2 exige `(2, 2)`, sinon l'attaque est refusée et `live_per_hit` revient VIDE — ce rouge accuse le
  montage), rejeu `drop_carrier_effects`, `p_extra` (plusieurs bénéficiaires par runner : 2 runners
  au lieu de 3 pour les mêmes tiers).

## Résidus

* **Attaque « ranged » sans arme de portée ≥ 2** — le port n'implémente pas le filtre CARRIER
  `UnitsWithRangedWeaponsExcludingDamageProfile` (déclaré subsumé). Il l'est pour toute attaque
  d'ARME ; il ne l'est pas pour une ability non-mêlée portée par une unité sans arme r ≥ 2, que le
  port accorderait et que le natif refuserait. **NON CONFRONTÉ** — aucun porteur de ce profil
  identifié dans le montage T'au.
* **« pré-perçage » dans les docstrings voisines** — `SpotterReworked_ExtraDamage`,
  `LordOfTheHost_ExtraDamage`, `Doom_extraDmg`, `BeaconOfRage_FriendlyExtraDamage` portent la même
  affirmation, infirmée par
  `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`. Corrigé
  seulement sur `DefenderOfTheGreaterGood` (périmètre de la tranche).
* **Face PRÉDICTION du canal DÉGÂT** — le cliquet #372 confronte la face prédiction pour l'axe
  COUPS ; celui-ci ne confronte que le combat. Les deux faces partagent le même agrégateur
  (`aura_attack_damage_bonus_from_allies`), mais la bascule Psychic n'est pas confrontée côté
  prédiction.
