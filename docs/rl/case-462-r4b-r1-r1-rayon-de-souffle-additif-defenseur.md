# #462-r4b-r1-r1 — le rayon de souffle de #462-r4b-r1 sur ses deux producteurs non confrontés

#462-r4b-r1 (PR #548) a déplacé l'additif DÉFENSEUR dans le slot pré-perçage de l'attaquant. **Trois**
producteurs alimentent `def_mods.additive` ; **un seul** avait été confronté. Le comportement des deux
autres avait donc changé sans qu'aucune mesure ne le voie — ni erreur, ni crash.

Les deux ont été confrontés en COMBAT. Le premier confirme le correctif dans un régime que #548 ne
pouvait pas atteindre ; le second a trouvé **un second défaut, indépendant du placement**.

## 1. Ce que chaque bras mesure, et par quel étage il sépare

| bras | producteur | ce qui SÉPARE les deux placements | port | contre-modèle | natif |
|---|---|---|---|---|---|
| `chrono` | `Chronometron_ExtraDamage` (1550) | branche **PERÇAGE** seule (`Physical`, ratio 1 %, armure 50000) | **61** | 950 | **61** |
| `chrono-flat` | idem, armure 0 | *rien* — branche ARMURE, plancher affine | 5983 | 5983 | 5983 |
| `neuro` | `Neuroparasite` (1218) | `%-list` **ATTAQUANT** (`RangedSpecialist` ×1.33) | **4448** | 3888 | **4448** |

Les deux bras discriminants séparent par des étages **différents**, et tous deux différents de celui
de #548 (qui reposait sur la `%-list` DÉFENSEUR `TerminatorArmour` ×0.25). Le correctif tient donc sur
les trois étages qui peuvent le révéler.

`chrono` est le plus net : `A × (1 − pierce/100)` = 890 sur 898, d'où un contre-modèle à **15,6× le
natif**. C'est le premier datapoint COMBAT de ce producteur, tous cas confondus.

## 2. Le second défaut, trouvé par le bras `neuro` : l'effet était MATÉRIALISÉ et pourtant INERTE

Sur ce bras, **avant correctif** : natif 4448, port **2192**. `def_mods` sortait **vide** alors que
l'effet 1218 était bien dans l'état chargé. L'écart valait **2256 = 1696 × 1.33** — exactement le
séparateur #88 que la face PRÉDICTION avait mesuré le 2026-07-12.

Cause, lue au décompilé :
`IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateEffectDamageMalusForDefense` =
`ForAddition(OwnerIsTarget & AreEqual(BondedEntity, damageSource) & DamageProfileIs(0xd),
Multiply(ConfigVar(8 = extraDmg, GetAbilityState(effect)), EffectLevel(Effect)))`. Le `ConfigVar`
s'indexe sur l'`AbilityState` de la **SOURCE**, et le gate `AreEqual` **fait de l'attaquant cette
source** — la magnitude se lit donc sur l'attaquant. La PRÉDICTION posait déjà `ability_level` /
`multiplier` dans son `attacker_ctx` (`playbook/prediction/_shared.py`) ; le COMBAT **ne les posait
pas**, donc `create_effect_damage_malus_for_defense` retournait `None` sur `src_lvl is None`.

**C'est le même fork prédiction/combat que #462-r4b-r1 vient de fermer sur l'axe PLACEMENT, resté
ouvert sur l'axe MAGNITUDE.** Corrigé dans le même foyer (`damage_model.defender_modifiers`), en
lisant la MÊME source que la `Scene` (`StatsComponent.ctx`). Rayon de souffle **mesuré** : ces deux
clés n'ont **qu'un seul consommateur** dans tout `engine/` (`NeuroparasiteEffect`).

Après correctif, les bornes du port valent **(4392, 5461)** — exactement celles que la docstring de
`NeuroparasiteEffect` attestait côté PRÉDICTION (« L1 (4392, 5461) »). Confirmation croisée
indépendante : les deux faces s'indexent désormais à l'identique.

La docstring qui disait « Combat : parasite non matérialisé par le runner -> def additive=0 -> inerte »
décrivait donc une cause **fausse** : ici le parasite ÉTAIT matérialisé.

## 3. Les régimes dégénérés, nommés et assertionnés

`GetDamageWithPiercing` = `max(d × pierce%, d − armure)`.

* **Branche ARMURE** : affine de pente 1 ⇒ `P(v + A) = P(v) + A`, les deux placements **coïncident**.
  C'est le bras témoin `chrono-flat` (5983 partout) — une **borne**, jamais une confirmation.
* **`PiercingRatio = 100`** ⇒ le plancher est l'**identité**, même régime dégénéré, quelle que soit
  l'armure. Or `Neuroparasite` est gaté `DamageProfileIs(0xd = Psychic)` et `Psychic` vaut 100 :
  **l'axe perçage lui est structurellement fermé.** Seule une `%-list` (l'une ou l'autre face) peut
  rendre son placement observable — ici la `%-list` attaquant.

Les deux faits sont figés par des tests offline, pour qu'aucune mesure future ne se lise comme une
confirmation.

## 4. Le résidu de TRONCATURE PAR TERME — reste une borne, désormais MESURÉE

Le natif tronque **chaque** `Addition` (`FixMath.NET.Fix64$$op_Explicit` = `raw >> 32`) avant de
sommer ; le port somme des flottants puis arrondit (`round(d + mods.additive)`). Les deux coïncident
tant que chaque terme est déjà entier. **Vérifié sur les trois producteurs** : `898`, `1696`, `997` —
tous entiers, et la garde `test_les_magnitudes_des_producteurs_sont_INTEGRALES` le **mesure** au lieu
de le supposer. Si elle rougit un jour, le régime devient observable et c'est un vrai bug.

## 5. Le garde qui manquait — le cliquet du canal

`test_le_registre_des_producteurs_d_additif_defenseur_est_COMPLET` balaie `engine/` par AST (chemin
dérivé du fichier de test, donc jamais au-dessus de son propre checkout — #434) et rend les classes
appelant `for_addition(False, …)`. Un **quatrième** producteur qui entrerait sans mesure reproduirait
exactement la régression silencieuse d'origine ; il fait maintenant rougir la banque. Il garde aussi
le sens inverse (un producteur attesté qui disparaîtrait rendrait les gardes live muets).

## 6. Montage (reproductible)

`probe_462_r4b_r1_r1_defender_additive_carriers.py [chrono|chrono-flat|neuro|all]`.

* `necroChronomancer` est **hors pool** → injection catalogue (`case-92` §6), puis `Chronometron`
  (self-cast) pose 1550 sur les ennemis du disque rayon 2 ; un **allié** frappe (`AreFriends(caster,
  EffectSource)`). Armure forcée à 50000 pour que la branche PERÇAGE gagne.
* `tyranNeurothrope` est **au pool**. Quatre pièges de montage, tous **mesurés** avant d'être fermés :
  1. l'arme PSYCHIQUE est la **ranged** (portée 3) — au contact il frappe en `Physical` et le gate
     `CurrentAttackDamageProfilesContain(0xd)` ne s'ouvre pas ⇒ `min_dist=2` ;
  2. le parasite se pose à la **clôture** (`On(9)`) : son additif ne joue qu'à la frappe **suivante**
     ⇒ montage multi-tours ;
  3. le tour adverse tuait le porteur et déplaçait la cible ⇒ PV bornés + `Movement: 0` ;
  4. l'avance de tour se pilote sur `decisionView.currentPlayer` (patron `rl_duel aiturn`), **pas** sur
     `ctrl` ; et `my_team` se lit **avant** toute action — avec un roster d'une unité le tour bascule
     dès qu'elle a agi, `my_team` sort `None` et inverse `amine`/`aenemy`.

## 7. Validation

* **Gardes livrés** : `test_462_r4b_r1_r1_defender_additive_carriers_live.py` (6) et
  `..._offline.py` (7) — 13 verts.
* **Contre-épreuves** (mutations vérifiées mordantes, arbre restauré, `git diff` vide) :
  * fix MAGNITUDE retiré → **2 rouges** (le live bit-exact `neuro`, le garde offline du threading) ;
  * déplacement #462-r4b-r1 retiré → **4 rouges** (les deux live bit-exacts, les deux régimes offline).
  Dans les deux cas les tests de contre-modèle et le témoin dégénéré **restent verts** : ils gardent
  le pouvoir discriminant du régime, pas le correctif.
* **Non-régression rejouée, tous verts** : `test_462_r4b_r1_defender_additive_live` + `_offline` (11),
  `test_441_neuroparasite_pair_term_live` (5), `test_damage_roll_live` + `test_runner_attack_live` (4),
  `test_terrifying_defense_live` + `test_nightshroud_combat_live` +
  `test_432_terminator_armour_cycle_live` (11).

## 8. Ce qui n'est PAS couvert

* ~~La POSE du parasite n'est pas portée côté runner~~ — **FERMÉ par #462-r4b-r1-r1-r1** (le
  triggered 1183 et les deux `Triggered()` de montée de niveau sont portés et confrontés live ;
  détail, contre-épreuves et résidus : `docs/rl/case-462-r4b-r1-r1-r1-pose-neuroparasite.md`).
  Ce qui reste ouvert de ce côté-là est le **RETRAIT** hérité d'`ABondEffect` (trois triggers sous
  virtuels de vtable non lus).
* **La branche `IsOverwatchAttack`** d'`ExemplarOfHate_Target` reste non threadée (résidu de #548).
* **`ability_level == 0`** : le port pose alors `0` (mirror strict de la prédiction), là où le natif
  `Idun.Shared.Level$$ToZeroBasedIndex` **lève** sur `<= 0`. Ce bord est commun aux DEUX faces, donc
  ce n'est plus un fork — mais il n'est pas tranché.
* **Le régime `TimesEffectApplied > 1`** de Chronometron (re-pose incrémentant le compteur) n'est pas
  mesuré : tous les bras sont à `times_applied = 1`.
