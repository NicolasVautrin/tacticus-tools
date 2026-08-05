# #270-r1 volet 1 — les 169 clés de dict que le build attribue à UN SEUL enum

**Livré le 2026-08-05.** Les cinq dicts d'`engine/` dont *toutes* les clés entières appartiennent
à un seul enum du build voient ces clés remplacées par le membre nommé. Les **128** clés des
**10** dicts que le build n'attribue pas de façon unique restent intactes : c'est un autre volet.

## 1. Le périmètre, et d'où il sort

`scripts/python/probe_270r1_enum_candidates.py --croiser` **énumère, il n'arbitre pas**. Son
signal fort est la **couverture de dict** — si toutes les clés d'un dict sont membres du même
enum, ce dict *est* clé par cet enum, quoi que le fichier importe. Mesure du 2026-08-05 :

| | avant | après |
|---|---|---|
| dicts à ≥ 3 clés entières | 15 (297 clés) | 10 (128 clés) |
| dicts à enum **UNIQUE** | **5 — 169 clés** | **0** |
| dicts AMBIGUS | 10 — 128 clés | 10 — 128 clés (inchangés) |
| candidats rôle « clé de dict » | 293 | 124 |

Le delta des candidats (293 → 124, et 569 → 400 au total) vaut exactement 169 : la vérification
est **dérivée**, pas affirmée.

| clés | table | enum |
|---|---|---|
| 105 | `runner/abilities/attack_type.ABILITY_ATTACK_TYPE` | `ActiveAbilityType` |
| 33 | `services/ability_range.DYNAMIC_TARGET_GATE_BY_ABILITY` | `ActiveAbilityType` |
| 18 | `runner/abilities/targeting.NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE` | `ActiveAbilityType` |
| 9 | `runner/operations/effects._DEFAULT_ROUNDS` | `EffectType` |
| 4 | `services/movement_query.SPECIAL_MOVEMENT_PATHFINDER_TYPES` | `EffectType` |

## 2. Le nom vient de la table DU BUILD, jamais du miroir

Le convertisseur lit `data/symbols/rnca9r7q6c/frida/enums.tsv` — le build de `CURRENT`, vérifié
égal à celui que rend `ghidra_symbols.py build`. C'est la précaution centrale : nommer depuis un
miroir dérivé écrirait des noms **faux**, strictement pires que l'ordinal, qui ne prétend rien
(`TriggeredAbilityType` porte 107 ids morts, #270-c ; les générateurs des autres tables sont
cassés, #270-b).

**Mesuré, et c'est le résultat qui rendait la tranche sûre : 0 clé manquante et 0 nom divergent.**
Les 169 clés existent dans les miroirs Python (`active_ability_type.py`, `effect_type.py`) *et*
y portent exactement le nom du build. **Aucun membre n'a eu à être ajouté** — les deux miroirs
sont générés depuis `enums.tsv` et gardés par `tests/test_enum_mirror_ratchet_offline.py`.

## 3. Ce qui rend la conversion value-preserving

`IntEnum` hérite `__hash__` d'`int` (MRO : `IntEnum` → `int` → `ReprEnum` → `Enum`), donc
`d[1004]` et `d[ActiveAbilityType.MortisRound]` désignent la **même** entrée. Les consommateurs
font tous `.get(int(...))` ou un subscript avec un `int` — aucun n'a été touché. La propriété est
**attestée sur les 169 clés** par le test, pas supposée.

L'**ordinal reste en commentaire de fin de ligne**. Il n'a plus valeur de désignation, mais le
dépôt entier (backlog, fiches, i2) référence les abilities par id. Le **nom de classe native** est
conservé dès qu'il porte autre chose que le membre + `Ability` — `# 1040 SpawnPoxwalkersAbility`
en face de `ActiveAbilityType.Poxwalkers` : ce sont deux artefacts natifs distincts, et c'est le
nom de classe qui est le symbole grepable vers `$$.ctor`.

## 4. La garde — trois étages, et elle mord

`scripts/python/tests/engine/test_270r1_dict_keys_enum_offline.py` (5 tests, 100 % offline).

Le mode d'échec propre à une conversion de masse est **le bon nom en face de la mauvaise valeur** :
il ne casse aucun import, ne lève rien, et déplace silencieusement une entrée d'une ability sur une
autre — les consommateurs dégradent l'id devenu absent en `None`.

* **CLIQUET** (`test_cles_sont_des_membres_d_enum`) — chaque clé est une instance de son enum. Ne
  se périme jamais ; rougit si une entrée revient avec un ordinal nu. **Vérifié rouge sur l'état
  d'avant conversion.**
* **ANTI-DÉPLACEMENT** (`test_snapshot_ordinal_valeur_et_ordre`) — les 169 couples
  (ordinal, valeur) mesurés avant conversion, même valeur, même ordre relatif. **Sur-ensemble
  ordonné, pas égalité** : une ability ajoutée passe sans re-figer 169 couples — une garde qui
  imposerait ce coût à chaque port serait contournée, pas maintenue.
* **ACCESSEURS PUBLICS** (`test_generalisation_les_accesseurs_publics_sur_les_169`) — les 169
  traversées par le chemin réel des appelants (`ability_has_attack_type`,
  `dynamic_target_gate_of`, `default_amount_of_rounds`, `get_pathfinder_type_for_unit`,
  `normal_attack_zone_contains`), avec l'ordinal **et** avec le membre. Il existe parce que les
  tests de comportement n'en exercent qu'une poignée : un déplacement sur une clé jamais jouée
  n'était vu par personne.

**Deux anti-dégénérescences, toutes deux mesurées.** Sur un caster de **mêlée**
(`custoBladeChampion`) les 18 profils d'attaque normale rendent tous `[True, False, False]` :
l'égalité int/membre aurait tenu **même sur une table entièrement mélangée**. Porteur passé à
`tauMarksman` (arme Range=3), où `1146 FloatingDeath_NormalAttack` se sépare des 17 autres — son
`RANGE_ADJACENT` (`overrideRange = 1`) gagne sur la portée d'arme — et le test **exige** cette
séparation. Second garde-fou : `ability_has_attack_type` est confronté aux deux *autres* valeurs
d'`AbilityAttackType`, qui doivent rendre `False`.

**Quatre mutations essayées, quatre détectées** : membre valant une autre entrée de la table
(1004 → membre valant 1006) ; membre **voisin plausible** (`FearOfTheUnseen_Moving` 1241 au lieu
de `_TeleportingIn` 1238) ; membre hors table ; profil aplati (les 18 rendus identiques). Un nom
*inexistant*, lui, ne s'importe pas — `AttributeError` au chargement du module. Chaque
restauration a été vérifiée par `git status`, jamais supposée.

## 5. Ce qui reste

* **128 clés, 10 dicts AMBIGUS** — hors périmètre **délibérément**. Le build ne les attribue pas à
  un enum unique : `targeting.py:568` (44) et `ability_caster_gates.py:400` (12) hésitent entre
  `ActiveAbilityType` et `TriggeredAbilityType` ; `playbook/noncomparable/_base.py:43` (22) et
  `playbook/prediction/abilities.py` (13 + 9 + 3) entre `ActiveAbilityType` et `EffectType` ;
  `battle_query.py:22/30` et `entities/selectors/geometry.py:47` (6 chacun) ont **454** candidats
  — leurs clés sont de petits entiers que presque tout enum contient. Les trancher demande de lire
  chaque site, et pour la paire `Active`/`Triggered` de vérifier d'abord #270-c : le miroir
  `TriggeredAbilityType` n'est **pas** attesté.
* **`#270-r1-r1` — le gisement que le probe ne voit pas.** Ses cinq rôles (clé de dict,
  comparaison, opération de bit, argument d'appel, argument nommé) **ignorent les éléments de
  conteneur**. Mesuré sous `engine/` : **161 littéraux non structurels dans 31 tuples/listes/sets,
  16 fichiers** — `entities/abilities/active_ability.py` 55, `runner/abilities/base.py` 27,
  `runner/abilities/attack_type.py` 23 (`REGULAR_ATTACK_ABILITY_TYPES`,
  `NOT_ACTIVE_ABILITY_TYPES`), `services/movement_query.py` 12
  (`SPECIAL_MOVEMENT_EFFECT_TYPES`). Ce sont les mêmes `ability_id` et `effect_type` que les clés
  converties, dans la même règle, et le chiffre « 284 clés » du CLAUDE.md ne les compte pas.
  ⚠ Deux de ces conteneurs sont **adjacents** à des dicts convertis par ce volet : les laisser
  rend le diff visiblement hétérogène. C'est assumé — convertir un gisement à moitié, sans l'avoir
  recensé, se ferait passer pour une couverture complète.

## 6. Validation

**405 tests, 0 échec, aucun fichier à `0 passed / N skipped`.** Offline (365) : les consommateurs
des cinq tables — famille `433_r4` (portée, gates dynamiques, whole-board, zone de tuile source),
famille `366_r1` (casts Burrowers / GrapnelLauncher / TunnelingHorror), famille `448_r2`
(teleporting-in, les 4 effets de mouvement spécial), `459_tile_accessors`, `multihex_substrate`,
`389_ramming_speed`, `337_dsl_triggers`, registre (`ability_registry_ratchet`,
`targeting_options_sources`, `targeting_rule_inventory`). Live (40) :
`419r1tr14r5r2r1r2_normal_attack_options`, `419r1tr14r5r2r1r2r1r1_only_adjacent`,
`381r5_special_movement`, `effect_duration_rounds`, `433_r4_r2_r1_ability_range`,
`summon_targeting`. Gardes de non-régression : `probe_120` (étape 0 — « littéral de ctor
manquant : aucun ») et `probe_181` (104 abilities, 0 masque manquant), les deux **OK**.

Tests **re-joués après rebase** sur `origin/master` (15 commits d'écart), probe inclus.

⚠ **Non couvert** : la conversion est value-preserving par construction, donc aucun scénario ne
peut faire *diverger* le comportement avant/après — il n'y a pas de « scénario où le port change
le résultat » à crafter ici. Ce qui est couvert à la place, c'est l'**atteignabilité des 169
clés** par le chemin des appelants (étage 3). Reste hors portée : les appelants **hors `engine/`**
qui liraient ces tables (aucun trouvé), et les 128 clés ambiguës.
