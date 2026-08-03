# #462-r4b-r1 — l'additif DÉFENSEUR n'était pas dans le même slot que celui de l'attaquant

Résidu nommé par #462-r4b (`case-462-r4b-pose-vs-etat-final.md` §7), **qu'aucun test n'assertionnait** :

```
blackAbaddon (trait TerminatorArmour)   PORT 10038 -> 2308   (7730 infligés)
                                        LIVE 10038 -> 7442   (2596 infligés)   facteur 2,98
```

La lecture spontanée — « la réduction `TerminatorArmour` n'est pas appliquée sur l'attaque commandée »
— est **fausse**. La réduction est appliquée, sur ce chemin comme ailleurs. Ce qui lui échappait,
c'est un **autre terme** : le `+997` d'`ExemplarOfHate_Target`, posé par la chaîne elle-même.

## 1. Ce que la mesure établit, étage par étage

`probe_462_r4b_r1_terminator_commanded_attack.py` instrumente les deux foyers que
`_reduced_bounds` enchaîne. Sur le bras `blackAbaddon`, AVANT correctif :

| étage | valeur mesurée |
|---|---|
| bornes `GetBaseDamageFix64` (override d'Attack 2008, spread 20 %) | 1606 / 2410 |
| perçage / armure | 40 / 2510 |
| `mods.additive` (ATTAQUANT) | **997** — `FearedInterrogator_Owner.extraDmg` |
| `def_mods.additive` (DÉFENSEUR) | **997** — `ExemplarOfHate_Target.extraDmg` |
| `def_mods.pct_list` | **`(0.25, None)`** — `TerminatorArmour_ReduceDmg` |
| sortie de `apply_pierce_and_modifiers` | 260 / 341 |
| sortie de `apply_all_modifiers(., def_mods)` | **1257 / 1338** |

La `%-list` `x0.25` **était bien là et bien appliquée** (`def_pct_moved` la porte, et 260 = `0.25 x
1041`). Ce qui la contournait, c'est l'additif défenseur : `apply_all_modifiers` l'ajoutait **après**
les deux `%-list` et les deux `Multiplier@0x30`. Un `+997` par coup, ni dilué par l'armure, ni réduit.

⚠ Les deux `997` sont deux effets DISTINCTS (même variable `extraDmg`, même niveau/multiplicateur du
même caster) — pas un double-compte. Le lire comme tel aurait envoyé le correctif au mauvais endroit ;
c'est `mods.details` qui le tranche (`Addition 997 owner_is_caster=True` d'un côté, `Addition 997
owner_is_caster=False` de l'autre).

## 2. La RE — l'appelant somme les DEUX `Addition@+0x10`

`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`, lu verbatim : il résout ses deux
accumulateurs par les slots d'interface `0xd` et `0xe`, lit le champ `+0x10` de **chacun**
(`FixMath.NET.Fix64$$op_Explicit`) et appelle

```
CalculateBaseDamageWithAllModifiers( request, (int)(base + Addition(0xd) + Addition(0xe)), ... )
```

aux **deux** call-sites — borne MIN (`PredictAttackRaw+0x2039`) et borne MAX (`+0x229d`), avec les
deux triplets `uVar35 + uVar39 + uVar38` puis `uVar40 + uVar41 + iVar20`.

`CalculateBaseDamageWithAllModifiers` **ne re-consomme pas** `+0x10` : il commence par
`GetBaseDamageWithFixedPiercedArmor`, puis enchaîne les quatre étapes de #462-r4a (deux
`ApplyCappedModifiers`, deux `CalculateBaseDamageWithModifiers`). L'additif du DÉFENSEUR partage donc
**exactement** le slot pré-perçage de celui de l'ATTAQUANT (#75).

La **PRÉDICTION** le faisait déjà (`_add_positional_and_defender_mods` : `mods.additive +=
def_mods.additive`, validé live sur Neuroparasite le 2026-07-12). Le **COMBAT** ne le faisait pas :
c'était un fork prédiction/combat, resté silencieux tant qu'aucun porteur d'additif défenseur ne se
matérialisait en combat — ce que la docstring de `NeuroparasiteEffect` disait explicitement
(« Combat : parasite non matérialisé par le runner -> def additive=0 -> inerte »). `ExemplarOfHate`
POSE le sien au milieu de sa propre chaîne : le canal a cessé d'être inerte sans que personne ne le
voie.

## 3. Le correctif

`AttackDamageOperation._apply_defender_flat_reductions` — le foyer qui DÉPLAÇAIT déjà
`flat_reductions`, `pct_list`, `multiplicative` et `extra_pierce` — déplace désormais aussi
`additive`, et **vide la source** (sans quoi `apply_all_modifiers(def_mods)` le compterait une
seconde fois). Trois lignes, un seul endroit.

**Rayon de souffle, mesuré** :

* **3 vecteurs de combat** appellent ce foyer et sont donc tous corrigés :
  `damage_ops/normal.py` (attaque normale, dont l'attaque COMMANDÉE par `UseActiveAbility`),
  `damage_ops/ability.py`, `damage_ops/normal_like.py`. `operations/additional_hits.py` reçoit les
  mêmes accumulateurs déjà fusionnés.
* **3 producteurs** alimentent `def_mods.additive` (`git grep "for_addition(False"` sur `engine/`) :
  `ExemplarOfHate_Target` (1293), `Chronometron_ExtraDamage` (1550), `Neuroparasite` (1183/1218).
  Les trois étaient mal placés en combat ; aucun autre canal n'écrit ce champ côté défenseur.
* **La PRÉDICTION n'est pas touchée** : elle avait déjà le bon placement. Le correctif REND les deux
  faces cohérentes au lieu de les diviser.

## 4. La borne du phénomène — pourquoi il s'était caché

Le plancher de `GetBaseDamageWithFixedPiercedArmor` est `max(d x pierce%, d - armure)`. Sur la
branche **ARMURE** il est affine de pente 1, donc `P(v + A) = P(v) + A` : **les deux placements
rendent le même nombre**. Il faut donc OU une `%-list` défenseur, OU la branche PERÇAGE gagnante,
pour qu'un écart apparaisse.

C'est mesuré, pas déduit : le bras `followup` du probe (Hellblaster mêlée `Physical`, perçage bas,
armure 2510) rend **port == contre-modèle == natif == 2746**. Un accord qui ne prouve rien.

## 5. Validation

**Bit-exactitude live** (état port calé sur le RNG du runner, donc même flux des deux côtés) :

| bras | PORT avant | PORT après | LIVE |
|---|---|---|---|
| `blackAbaddon` (réduction + additif) | `[1260,1267,1260,1320,1315,1308]` = 7730 | `[449,401,428,445,460,413]` = **2596** | `[449,401,428,445,460,413]` = **2596** |
| `blackPossession` (additif seul, axe armure) | `[2083,2295,2418,…]` | `[1883,2295,1862,…]` | `[1883,2295,1862,1994*,0,0]` |
| `followup` (attaque normale, autre attaquant) | 2746 | 2746 | 2746 |

`*` coup létal écrêté aux PV restants ; le test dérive le préfixe non écrêté des PV au lieu de
supposer un compte de coups.

**Gardes livrées** :

* `tests/engine/runner/test_462_r4b_r1_defender_additive_live.py` (6 tests) — les trois bras, le
  contre-modèle ÉCRIT rejoué sur le MÊME état, et la non-dégénérescence (l'effet est bien posé par la
  chaîne, l'armure est bien ACTIVE au chargement).
* `tests/engine/test_462_r4b_r1_defender_additive_offline.py` (5 tests) — le geste du foyer, les
  bornes natives 360/474, le contre-modèle 1257/1338, la dilution par l'armure, et la borne §4.

**Contre-épreuve** (le correctif retiré de l'arbre, `if False and …`) : offline **3 failed / 1
passed**, live **2 failed / 3 passed** — les deux axes bit-exacts tombent, les deux tests de
contre-modèle restent verts (ils gardent le pouvoir discriminant du régime, pas le correctif).
Arbre restauré par `git checkout --` du seul fichier, `git diff` vide, offline re-vert.

**Non-régression rejouée** (tous verts) : `test_damage_roll_live` 2, `test_runner_attack_live` 2,
`test_damage_crit_live` 2, `test_damage_block_live` 2, `test_446_r2_inter_face_rounding_offline` 7,
`test_446_r2_inter_face_rounding_live` 4, `test_terrifying_defense_live` 5,
`test_chain_after_refused_addeffect_live` 4, `test_432_terminator_armour_cycle_live` 4,
`test_nightshroud_combat_live` 2, `test_441_neuroparasite_pair_term_live` 5,
`test_additional_hits_rounding_live` 3. Banque de cliquets **VERTE, 37 cliquets** (relevé du
2026-08-03, post-rebase).

## 6. Ce qui n'est PAS couvert

* **Les deux autres porteurs d'additif défenseur ne sont pas confrontés en COMBAT.**
  `Chronometron_ExtraDamage` (1550) et `Neuroparasite` (1183/1218) traversent le même foyer et sont
  corrigés par construction, mais aucune mesure live ne les exerce sur ce vecteur.
  **Canal qui les établirait** : `necroChronomancer` est hors pool → injection catalogue
  (`catalog_inject`, cf. `case-92` §6) puis cast de `Chronometron` sur une cible ADJACENTE à un allié
  du Chronomancer, cet allié frappant ensuite — avec une armure de cible assez haute pour que la
  branche PERÇAGE gagne (`rl_duel build --armor-target`), faute de quoi le régime est dégénéré (§4).
* **La troncature PAR TERME.** Le natif applique `op_Explicit` (`raw >> 32`) à **chaque** `Addition`
  séparément avant de sommer ; le port somme des flottants puis arrondit dans
  `apply_pierce_and_modifiers`. Aucun producteur porté ne rend de valeur fractionnaire (les trois
  passent par `int(...)`), donc les deux se confondent aujourd'hui. Un producteur fractionnaire futur
  les séparerait.
* **L'identité des slots `0xd` / `0xe`** (lequel est l'attaquant, lequel le défenseur) n'a pas été
  tranchée — elle est **sans effet** ici : la somme est symétrique et les deux `Nullable` sont passés
  aux deux call-sites. Une lecture qui en dépendrait devrait la trancher.
* **Le bras `followup` n'est pas discriminant** (§4) : c'est un datapoint d'ACCORD sur un autre
  vecteur, et le test l'assertionne comme tel pour qu'il ne se lise jamais comme une confirmation.
