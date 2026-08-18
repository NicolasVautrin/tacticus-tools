# case-488-r3 — le profil du GROUPE, l'événement qui manquait, et deux liaisons figées

Tranche de trois réparations de foyer (`#488-r3`, `#512-r9`, `#10031-r1`) plus un quatrième item
(`#952-r7`) qui s'est révélé **déjà livré**. Chacune part d'une lecture du décompilé sur le build
`t6dpr4k06g` et se termine par une confrontation — deux d'entre elles **live**.

---

## 0. `#952-r7` — DÉJÀ LIVRÉ, et la fiche ne le disait pas

`ai/state_bridge.py::_granted_abilities` dérivait l'ability accordée par une convention de nommage
(`Heal_<Passif>`) qui ratait deux artefacts natifs sur trois. **La délégation au registre littéral
était déjà faite** : `a6baf20a` (« state_bridge : 4 residus PORTES (#1015-r4, …) ») a remplacé la
convention par `entities.active_abilities.passive_granted_active_ability_ids`, dont le registre
porte bien les trois entrées lues sur les xrefs de
`IdunBattleLogic.Entities.DSLBehaviors$$AddActiveAbility` :

| passif | ability accordée | forme du nom |
|---|---|---|
| `TwistedScience` | `ActiveAbilityType.Heal_TwistedScience` | `Heal_<P>` — la seule que la convention voyait |
| `HealingBalms` | `ActiveAbilityType.HealingBalms_Heal` | `<P>_Heal` — l'autre sens |
| `GalvanicField` | `ActiveAbilityType.Repair_GalvanicField` | `Repair_<P>` |

C'est le mode dominant annoncé au dispatch : un résidu fermé *en passant* par un voisin de foyer
est commité sous le numéro du voisin, donc **invisible au journal git** si l'on cherche son propre
numéro. La ligne a été retirée de `backlog.md`.

---

## 1. `#488-r3` — les mods ATTAQUANT au profil du GROUPE

### Le gisement

Côté natif, un groupe additionnel du canal #179 **à profil propre** n'est pas un morceau de
l'attaque : c'est une **sous-opération entière**.

```
IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute
    -> slot 0x3c
    -> IdunBattle.Operations.AttackDamageOperation$$Execute
        -> IdunBattle.Operations.AttackDamageOperation$$ExecuteHits
            -> IdunBattle.Operations.AttackDamageOperation$$ExecuteHit
```

Cet `ExecuteHit` rebâtit un `IdunBattle.Entities.Abilities.AbilityEntities` **neuf**, dont le
`DamageProfile` est celui **du groupe** (`IBattleQuery.GetDamageProfile(damageProfileType)`, slot
d'itable `0xad`, puis écriture dans le champ profil de la struct) — et c'est cet objet que
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` passe à
chaque effet.

Côté port, `execute_additional_hits` recevait `mods` **en argument**, résolus une seule fois par la
phase d'ARME. Il threadait pourtant déjà `g_profile` dans **trois** autres canaux du groupe
(`make_pre_damage_taken_sink`, `_apply_damage_pipeline`, `_target_limits`) : les mods attaquant
étaient le quatrième, et il manquait.

**Conséquence mesurée** (`probe_488r2_profil_du_groupe.py` étape 3) : `MeltaExtraDmgEffect` rend
`None` au profil `HeavyRound` et `+50 %` au profil `Melta`. Sur `blackObliterator` (arme
`HeavyRound`, cycle `FleshmetalGuns` au profil `Melta`) contre un `Vehicle`, le bonus était donc
**inerte** sur les coups du groupe.

### La réparation, et pourquoi ce n'est PAS une re-collecte en bloc

La fiche du résidu interdisait explicitement de re-collecter en bloc : la docstring
d'`execute_additional_hits` porte une mesure live (`2468 s14`) qui **valide le partage** des mods
pour les bonus NON gatés par profil — `ExplosiveMaladies` y subit le ×1.5 `CrushingStrike` de la
phase d'arme.

La réparation isole donc strictement l'axe PROFIL, par **double collecte prise au même instant** :

```
temoin = attacker_mods_for_profile(<profil de l'ARME>)
mesure = attacker_mods_for_profile(<profil du GROUPE>)
si mesure != temoin  ->  on prend `mesure`
sinon                ->  on garde l'OBJET de la phase d'arme, bit à bit
```

Tout ce qui aurait changé d'état entre la phase d'arme et le groupe **s'annule dans la
comparaison**. Un groupe qui hérite du profil de l'arme (`g_profile is None`) n'appelle même pas le
re-collecteur.

Le re-collecteur est fourni **par l'appelant** (`damage_ops/normal.py`, `damage_ops/ability.py`),
parce que lui seul a les huit autres axes sous la main (`is_ranged`, `target_traits`,
`is_normal_attack`, `is_overwatch`, `ability_type`…). Foyer partagé :
`damage_model.attacker_modifiers_at_profile`, qui refait aussi les **deux feuilles positionnelles**
(`apply_elevation_bonus`, `apply_trench_reduction`) — le builder natif les porte dans le même
étage, et `apply_trench_reduction` **lit elle aussi le profil**.

⚠ La famille ABILITY ne reçoit **aucun** re-collecteur : son bras est déjà sous
`if is_attack_damage_op`, et ses mods attaquant sont ZÉROÉS (#226). Une re-collecte y fabriquerait
des mods que le natif ne construit pas.

### La confrontation live — 3 seeds, bit-exacte

`tests/engine/runner/test_488r3_groupe_melta_live.py` monte `blackObliterator` (cycle sur sa
variante `FocusedMalice`, profil `Melta`) tirant sur `admecDestroyer` (trait `Vehicle`), puis
rejoue le **même** état offline sur le **même** flux RNG, une fois avec le canal câblé et une fois
avec le canal muet (l'état d'AVANT).

| seed | live (coups du groupe) | port LIVRÉ | port AVANT |
|---|---|---|---|
| 777 | `906, 1572, 1805` | `906, 1572, 1805` | `906, 1048, 1203` |
| 31337 | `906, 1571, 1484` | `906, 1571, 1484` | `906, 1047, 1429` |
| 12345 | `906, 1695, 1677` | `906, 1695, 1677` | `906, 1130, 1253` |

**3/3 bit-exact pour le port livré, 3/3 divergent pour l'état d'avant.** La réparation n'est donc
pas un sur-ajustement : c'était le port qui sous-estimait.

Le **premier** coup (`906`) est identique dans les trois régimes — c'est le groupe
`LetTheGalaxyBurn`, sans profil propre, qui hérite de celui de l'arme et n'est donc jamais
substitué. L'étage E4 du cliquet offline s'en trouve confirmé live, sans avoir été monté pour ça.

### Deux pièges du montage, tous deux mesurés

1. Le groupe est gaté `IsRangedAttack`
   (`IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits` :
   `condition = OwnerIsCaster & IsRangedAttack`). Un `drive` **au contact** fait choisir l'arme
   `Power` — mesure : `livre == []`, la comparaison portait sur le vide.
2. Capturer `execute_additional_hits` **à l'appel** dans la variante rend la substitution
   elle-même → `RecursionError`. La capture se fait au **chargement** du module.

---

## 2. `#512-r9` — l'événement `On(0x42 = FinalDamage)` qui manquait au vecteur `amount`

### Le gisement

`IdunBattle.Operations.ADamageOperation$$RegisterFinalDamage` vit sur la base **commune** et ses
xrefs entrantes sont **exhaustives** : `IdunBattle.Operations.AttackDamageOperation$$Execute` et
`IdunBattle.Operations.AbilityDamageOperation$$Execute`.

Le port a **trois** vecteurs d'attaque, dont **deux** mirroitent la première :
`damage_ops/normal.py` (l'attaque normale) et `damage_ops/normal_like.py` (le mode `amount`). Les
deux autres émettaient déjà l'événement ; `normal_like` n'émettait **rien**. Ce n'était pas un
écart d'ORDRE — celui-là (`8` → `9`) a été réparé par `#512-r7` — mais un événement **entier**.

### Trois lectures qui fixent la place et le gate

1. l'appel est la **dernière** instruction d'`AttackDamageOperation$$Execute`, après la boucle des
   groupes additionnels et après l'agrégation `attack@+0x28 += hitGroup@+0x4c` ;
2. il **précède** `On(9)`/`On(10)`, qui sortent du slot **59** (`FinishAttack`) poussé par le
   NŒUD ;
3. l'émission dans `RegisterFinalDamage` est **inconditionnelle** — elle vit **hors** du
   `if (0 < totalDamage)` qui garde, lui, la liste `currentAttack@+0x60` et le slot d'itable `0x4b`.

⇒ aucun gate sur le dégât, et **aucun gate `is_outside_attack`** : celui-ci sépare ce qu'émet le
NŒUD de ce qu'émet l'OPÉRATION, et `RegisterFinalDamage` est du côté OPÉRATION.

### Rayon de souffle, mesuré AVANT d'émettre

`probe_512r9_final_damage_blast_radius.py` : **1 seul** écouteur de l'event 66 dans tout le
registre — `RealityUnboundExtraMaxDamageAbility` (passif `RealityUnbound`, porteurs
`thousTzaangor` en lineup + 4 npc). Son étape 3 est un **invariant** : les trois vecteurs
d'attaque de `damage_ops/` doivent émettre, et les vecteurs sont dérivés (pas listés).

### La confrontation live — et le capteur qui mentait

`tests/engine/runner/test_512r9_final_damage_live.py` : `thousSorcerer` (trait `Psyker`, arme
ranged `Psychic`) tire sur un ennemi A ; le splash `PsykerExtraAttackAbility` frappe un ennemi B
**adjacent**, en `Psychic`, **par le vecteur `amount`**. `thousTzaangor`, allié, pose un
`EXTRA_MAX_DAMAGE` par victime distincte — les instances **cumulent**.

| capteur | mesure | lecture |
|---|---|---|
| `decisionView.effects` (par NOM) | 1 « instance » | **FAUX** — la vue déduplique |
| `statModSources(extraMaxDamage).total` | **598** | 2 × 299 ⇒ **DEUX poses** |

La magnitude unitaire (`299`) est **dérivée** du foyer du port
(`reality_unbound_extra_max_damage`, qui lit `RealityUnbound.extraMaxDmg` au niveau passif et au
multiplicateur de rareté de l'unité), jamais fittée sur le total mesuré.

⚠ **Le premier capteur aurait fait retirer une réparation juste.** Ce test a d'abord accusé « le
natif ne pose qu'une instance » sur la vue par nom. Un capteur qui déduplique ne peut pas compter —
et l'absence d'un événement dans une vue ne prouve rien.

---

## 3. `#10031-r1` — deux liaisons figées, et le ratchet que son gardien empêchait d'atteindre zéro

`engine/ai/state_bridge.py` figeait `make_can_continue` et
`engine/runner/operations/movement.py` figeait `is_like_flying`, en **forme A** — donc les
substitutions posées par les instruments de `#381-r4` étaient **muettes** sur ces chemins. Les deux
sont passées en **forme B** (liaison de module).

### Ce que la réparation a changé, mesuré

| mesure | avant | après |
|---|---|---|
| `morsure_substitution` sur les deux couples | 1 liaison figée chacun | **0** |
| `test_381r4_imperative_collapses_live.py` | 2 passed | 2 passed |
| `probe_381r1_movable_tiles_pool.py --mutate none` | `PORT == NATIF 9/9 WALK, 1/1 VOLANTES` | identique |
| `probe_381r1 --mutate no-fly` | `rc 1`, « ne discrimine pas » | identique |

⚠ **La prémisse du résidu est partiellement RÉFUTÉE.** La fiche annonçait que réparer
`is_like_flying` ferait mordre `test_448r1r1r1r1_flying_tiles_moved_*` — or **ce test ne substitue
pas** ce nom : il l'importe et l'**appelle** dans une assertion. Les seuls substitueurs réels sont
les bras `no-fly` de `probe_381r1_movable_tiles_pool.py` et
`probe_381r4_imperative_collapses.py`, et **aucun des deux ne change de verdict** — leur chemin
passe par les sélecteurs de tuiles, pas par le dispatch de `MoveUnitOperation`. Aucun verdict
d'autre tranche n'a donc bougé.

### Le ratchet dont le gardien interdisait l'arrivée

`test_e2bis` exigeait `atteste["liaisons"]` **non vide**. Refermer le ratchet à zéro — ce que le
résidu prescrivait — le faisait donc **rougir**. Un ratchet dont le gardien interdit l'arrivée ne
descend jamais. À vide, ce qu'on exige change de nature : `ouverture == 0` (le fichier **dit**
qu'il est refermé), un champ `_ferme` qui **nomme** la tranche, et **aucune** raison orpheline.

### Le zéro fait disparaître la preuve de non-vacuité — d'où un TÉMOIN

Tant que des liaisons étaient attestées, le non-vide de la mesure prouvait que le balayage AST
visitait encore quelque chose. À zéro, cette preuve disparaît : un recenseur cassé rendrait
`set()` partout et E2 passerait. Le non-vide se prend donc sur un **témoin écrit**
(`test_e2ter`, `test_e2quater`), jamais sur le gisement — un arbre jetable où l'on écrit les cinq
formes et où le recenseur doit rendre **exactement** la forme A :

| forme écrite | attendu |
|---|---|
| A `from <src> import foo` (module) + appel | **FIGÉE** |
| B `from pkg import src as _s` + `_s.foo()` | libre |
| C `from <src> import foo` dans la fonction + appel | libre (re-exécutée) |
| RE-EXPORT : forme A **sans** appel | libre |
| HOMONYME : forme A depuis un **autre** module + appel | libre |
| A en import **relatif** (`from ...pkg.mod import nom`) | **FIGÉE** |

Les deux dernières lignes sont venues de la matrice de mutants : sans l'homonyme, un recenseur qui
accepterait n'importe quel module source passait ; sans le relatif, le témoin ne couvrait pas
l'écriture de tout `engine/runner/**` — c'est-à-dire précisément le gisement réparé.

---

## 4. Matrice de mutants — 22 mutants, 21 mordent

Le seul muet est **sémantiquement équivalent** : capturer `g_mods` par fermeture au lieu d'un
défaut d'argument dans `_reduce`. `_run_hits` est synchrone, donc la fermeture voit la même valeur ;
la précaution reste défensive et n'a rien à mordre.

**Trois mutants ont trouvé un vrai trou** et ont fait ajouter un étage :
* `attacker_modifiers_at_profile` cessant de propager le profil (à la collecte, au trench) ou
  n'appliquant plus l'élévation était **muet** → étage E8 ;
* un recenseur acceptant n'importe quel module source était **muet** → l'homonyme du témoin.

⚠ **Trois mutants ont d'abord été mal construits** : re-figer une liaison exige de muter **deux**
choses à la fois (l'import ET l'appel). Muter l'une seule ne produit pas une liaison figée — un
import sans appel nu est un re-export, un appel nu sans import est un `NameError`. Un mutant mal
construit se lit comme un trou de garde et fait chercher au mauvais endroit.

---

## 5. Résidus ouverts par cette tranche

* **`#488-r4`** — la double collecte n'isole que l'axe PROFIL ; le natif re-collecte à l'état
  **courant**, donc un effet posé ou retiré pendant la phase d'arme entre dans les mods du groupe
  côté natif et pas côté port.
* **`#512-r10`** — `RegisterFinalDamage` écrit **aussi** deux listes de profils
  (`currentAttack@+0x58` inconditionnel = les profils TENTÉS ; `currentAttack@+0x60` sous
  `0 < totalDamage` = ceux ayant réellement infligé du dégât) et invoque un slot d'itable `0x4b` ;
  aucun des trois n'est porté, et on ne sait pas laquelle des deux listes
  `CurrentAttackDamageProfilesContainOtherThan` interroge.

## 6. Ce qui n'est PAS couvert

* La face **PRÉDICTION** du canal #179 : `get_multi_hit_attack_prediction` prédit les groupes avec
  les mods de l'arme, exactement comme le faisait la face COMBAT. Elle n'a pas été touchée, donc
  prédiction et combat **divergent** désormais sur un groupe à profil propre dont un bonus est gaté
  par profil. Non mesuré ici (le résidu `#449-r6` occupe déjà ce foyer).
* Le second consommateur du même axe, `PsychicStalk_FriendlyChaosExtraDamage`
  (`DamageProfileIs`), n'a **pas** été confronté live — seul `MeltaExtraDmgEffect` l'a été.
* Les deux seeds sur quatre où `test_512r9_final_damage_live.py` **skippe** (le Psyker n'amène pas
  sa cible à portée sur cette géométrie) : le skip est nommé, mais aucune recherche de seed
  n'a été faite pour l'éliminer.
