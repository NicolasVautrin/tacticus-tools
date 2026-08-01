# case-419 — inventaire des playbooks TRIGGERED à corps ATTACK, et le patron « porté + non câblé »

**Critère** : combien de playbooks triggered ont un corps ATTACK (et MOVE) non trivial, et pour
chacun — sur **deux axes indépendants** — est-il *porté* côté Python, et *câblé* (le dispatcher
itère-t-il son id pour un porteur réel) ?

**Réponse, mesurée** sur `data/symbols/rnca9r7q6c` :

| | surchargée | dont corps TRIVIAL (`yield Fix64(0)`) | **gisement réel** |
|---|---:|---:|---:|
| face ATTACK | 58 | 29 | **29** |
| face MOVE (corps propres) | 85 | 34 | 51 |

Le « ~60 » hérité visait la face ATTACK : il est **juste sur les corps surchargés (58)** et **faux
d'un facteur deux sur le gisement** — la moitié rend `0` quelle que soit l'entrée.

Re-dérivation : `python scripts/python/probe_419_triggered_playbook_inventory.py [--residuals]`.
Cliquet : `scripts/python/tests/test_419_playbook_wiring_ratchet_offline.py`.

---

## 1. Trois canaux de chargement, à ne pas additionner

`IdunBattle.AI.PlaybookDatabase` porte **quatre** couples `Dictionary<clé, builder>` + cache, un par
canal — lus au décompilé, chacun avec ses offsets propres :

| méthode | builders / cache | clé | classes concernées |
|---|---|---|---:|
| `PlaybookDatabase$$LoadPlaybook(ability)` | +0x88 / +0x90 | `TriggeredAbilityType` | **86** |
| `PlaybookDatabase$$LoadPlaybookNonOwner` | +0x98 / +0xa0 | `TriggeredAbilityType` | **15** |
| `PlaybookDatabase$$LoadPlaybook(specificBehaviour)` | +0xa8 / +0xb0 | *unité*, pas ability | **4** |
| `PlaybookDatabase$$LoadDefaultActiveAbilityPlaybook` | +0x80 / +0x78 | `ActiveAbilityType` | — |

Seul le premier est ce que #419 vise : c'est lui qu'itèrent **les deux faces** du dispatcher
`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility` (UtilityType 2). Les mélanger gonfle le gisement
de 86 à 105. Les quatre `*SpecificBehaviourPlaybook` (Magnus, Mortarion, Cyrus, Riptide) **ne portent
aucun `TriggeredAbilityType`** — `ability_id = None` est le verdict juste pour eux, pas un trou.

**Deux nomenclatures, et n'en compter qu'une fait tomber 16 classes à zéro** : la base OWNER
(`TriggeredAbilityPlaybook<T>`) expose un wrapper `<Face>` qui délègue au virtuel `<Face>Internal`
(c'est celui-là qu'un concret override) ; la base NON-OWNER n'a pas ce relais et ses concrets
overrident `<Face>` **nu**. Deux OWNER font de même (`CabalOfSorcerers`, `WisdomOfTheAncients`).

## 2. Le filtre décisif : la moitié des corps ATTACK rend 0

Calibrage fait **sur le build courant**, pas hérité : le corps de la base
`IdunBattle.AI.Playbook.TriggeredAbilityPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__37u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`
est **décompilé lu** — il rend `Fix64.op_Implicit(0)` et rien d'autre — et pèse **0x80** octets.
**29 des 58** corps ATTACK propres pèsent exactement 0x80. Le premier corps actif au-dessus est
`SwornProtector_ProtectPlaybook` (0xd0).

⚠ Le filtre est **par FACE** : `PsykerPlaybook` (attack 0xf20) et `SuppressiveFirePlaybook`
(attack 0x1e0) sont *actifs* en ATTACK et *triviaux* en MOVE. Un item classé ici se relit au
décompilé avant tout port — la taille trie, elle ne conclut pas.

**Corollaire important pour l'exhaustivité** : côté MOVE, il existe une population à corps **hérité**
(concrets d'`AdjacentUnitPreferenceTriggeredAbilityPlaybook<T>`, invisibles d'une table indexée par
adresse — c'est l'objet de `case-193`). Côté ATTACK, **il n'y en a pas** : la seule base qui
implémente cette face est `TriggeredAbilityPlaybook<T>`, et son corps rend 0. Les corps propres
**sont** donc l'inventaire complet de la face ATTACK.

## 3. La tranche fondatrice était MORTE — et c'est le résultat

La consigne était « porter la face MOVE de 1044 ». Elle **n'existe pas** :
`SuppressiveFirePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` est un
`yield Fix64.FromInt(0)` — **décompilé lu**, 0x80 octets. Rien à porter ; son absence de
`TRIGGERED_MOVE_PLAYBOOKS` **est** le comportement natif. La docstring de
`engine/playbook/suppressive_fire.py` disait « a son propre corps, NON porté », ce qui se lisait
comme un résidu ouvert : corrigé.

Bonus de RE : le natif factorise le prédicat dans
`IdunBattle.AI.Playbook.Loki.SuppressiveFirePlaybook$$TriggersSuppressiveFire`
(`HasEffect(target, 1009, onlyActive:0) && !AreEntitiesAdjacent(casterTile, target)`), mais la face
ATTACK l'**inline** — le port de #415 est donc structurellement fidèle. Cette méthode n'a **aucun
appelant code** (xrefs : deux références DATA de table IL2CPP) : pas de second consommateur.

## 4. Le patron qui saigne — « porté + non câblé »

Le croisement à deux axes, **corps non triviaux seulement** :

| face | porté+câblé | **PORTÉ + NON CÂBLÉ** | non porté+câblé | non porté+non câblé |
|---|---:|---:|---:|---:|
| ATTACK | 4 | **0** | 20 | 5 |
| MOVE | 5 | **0** | 40 | 6 |
| NON-OWNER | 1 | **0** | 14 | 0 |

**Le zéro n'est pas un acquis, c'est ce que ce cas a produit.** L'axe câblage se lit à **deux
niveaux**, et les confondre rend le verdict faux :

* `wired` — la voie dispatchée **offline** : `kit_triggered_ability_ids` = `passiveAbilities`
  gameconfig + `TRAIT_TRIGGERED_ABILITY_IDS` ;
* `wired_live` — ce que le dispatcher voit **réellement** en bataille : l'`AbilitiesComponent`, lu
  par `unitAbilityStates`, qui porte **aussi** relique / mythique / item (#323).

Une ability de **relique** n'est jamais `wired` et toujours `wired_live`. Compter au seul niveau
offline classait à tort `KardiocoreGalvanus` (1457) en « porté non câblé » — il est câblé depuis
#304, côté MOVE.

## 5. L'asymétrie corrigée — la face ATTACK ne lisait pas l'`AbilitiesComponent`

Le dispatcher natif
`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext`
lit `case.unit@+0x10` → GetComponent → `+0x18` (la Collection) → `GetEnumerator`, puis
`LoadPlaybook(type)` par item : **littéralement la même collection que la face MOVE**.

Or côté port, la face MOVE lit le canal live depuis #304 tandis que la face ATTACK ne lisait que le
kit gameconfig+traits. Elle était donc **aveugle à tout ce que la bataille monte et que le
gameconfig ignore — au premier rang les abilities de RELIQUE**
(`UnitConfiguration.TertiaryAbility`, 5e chemin de registration #357). Corrigé dans
`engine/utilities/tile.py::TriggeredAbilitiesUtility.evaluate_attack_in_steps`, avec le **même**
repli que #304 : lecture live vide (RPC indisponible, entité absente, contexte offline) ⇒ kit
gameconfig, comportement d'avant.

Sans ce câblage, **aucun** des 5 playbooks ATTACK de relique du binaire ne pourrait jamais tirer.

## 6. La tranche portée — `Lakrimae` (1541), les DEUX bouts

Choisi parce qu'il **exige** les deux bouts : premier playbook ATTACK dont le porteur arrive par une
voie que le kit gameconfig ignore. Porté sans le câblage, il serait resté INERTE — le patron même
que ce cas recense.

`IdunBattle.AI.Playbook.Loki.LakrimaePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
(SM : case @+0x20, délégué scorer @+0x28) :

```
target = case@+0x20
if (EntityExtensions.HasTrait(target, (UnitTrait)5))   // 5 = Mechanical
    yield return Fix64.FromInt(0)
else
    yield return Fix64.FromInt(GetUtilityValue(<clé statique du .cctor>))
```

* **`UnitTrait` 5 = `Mechanical`**, qualifié des deux côtés : le mirror rend `Mechanical`, et la clé
  BC le dit en toutes lettres (`Lakrimae_LikesNonMechanicalEnemies`). Prédicat **nié**.
* La clé est le champ statique unique écrit par
  `IdunBattle.AI.Playbook.Loki.LakrimaePlaybook$$.cctor` (`statics+0xb8`), lue par le délégué
  `TriggeredAbilityPlaybook<T>$$GetUtilityValue`. Poids **5**.
* Le prédicat porte sur la **CIBLE** seule : ni stats ni traits du caster.
* Face MOVE de `Lakrimae` : `yield Fix64(0)` constant — non portée, comme le natif.

⚠ **Le piège #271 était armé** : la capture `data/seed-bc.json` porte cette clé à **0**, le
gameconfig vivant à **5**. Sans `catalog_inject.refresh_ai_utilities`, natif et port liraient tous
deux 0, seraient parfaitement d'accord — et faux. Le montage vérifie donc que le poids servi n'est
pas nul avant de conclure.

**Porteur** : `deathTyphus`, HERO **au pool** (rank 17), **seul** `allowedUnits` de l'item relique
`R_Crit_Lakrimae` → état 2 des trois états d'une relique (montage écrit `--equip-relic`). Cinq npc
`deathBossTyphus*` la portent en dur (`relicAbilities`).

### Mesure

Board `MC1_67`, seed 41504, caster au contact de deux cibles — `admecDestroyer` (`Mechanical`) et
`astraBullgryn` (sans) :

```
admecDestroyer  mech=True  @(3,4) nat=16.293112 port=16.293112 d=+0.000000 | muté=16.293112 manque=-0.000000
astraBullgryn   mech=False @(3,4) nat=15.611047 port=15.611047 d=-0.000000 | muté=10.611047 manque=+5.000000
```

Conformité exacte sur les deux régimes ; playbook retiré du registre ⇒ le port perd **exactement 5**
sur la non-mécanique et **rien** sur la mécanique.

**Contre-épreuve du câblage, JOUÉE** : lecture live désactivée (`if False and callable(...)`) ⇒
`test_lakrimae_pair_term_matches_native` et `test_lakrimae_requires_live_kit_channel` rougissent tous
deux, écart mesuré **5.000000**. La garde garde bien le câblage, pas seulement le playbook.

## 7. Ce que ce cas n'établit PAS

* **Le régime des 20 résidus ATTACK non portés à porteur réel** : `probe_419 --residuals` les liste
  avec porteurs et ventilation par `kind`, leur corps n'est pas lu. Une tâche par item.
* **La face MOVE** : re-dérivée ici sur les corps propres seulement ; la population héritée et le
  classement par valeur restent ceux de `case-193` / `case-193c`.
* **Les 5 ATTACK « non porté + non câblé »** : aucun porteur par aucune voie dérivable du
  gameconfig. Ce n'est pas une preuve de mort (4 voies restent hors de portée d'un recensement
  offline, cf. `case-323` §2) — c'est un « non confronté », pas un « non pertinent ».
* **Le canal `specific`** (4 `*SpecificBehaviourPlaybook`) et le canal `active`
  (`LoadDefaultActiveAbilityPlaybook`) : identifiés, non inventoriés.
* **La face `CalculateRepairUtilityInSteps`** : 3 classes la portent
  (dont `VoltagheistFieldPlaybook`), aucune n'est dans le périmètre des deux faces de #419.
