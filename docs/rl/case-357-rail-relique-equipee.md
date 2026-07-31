# #357 — Le rail de la RELIQUE ÉQUIPÉE : le port la LIT enfin, et au bon niveau

**Question binaire.** Une relique montée en bataille par le montage #237 produit-elle son effet
côté port, et au **niveau** demandé ?

**Réponse.** Non — sur aucune des deux faces — et c'était **silencieux** : le trigger n'était jamais
inscrit. Ce cas pose le rail, sur **une** relique (`DawnBlade`, 1501), et le confronte live.

Build de mesure : `rnca9r7q6c`. Montage : `probe_357_relic_rail.py`.

---

## 1. Où la relique entre côté natif, et où elle DEVAIT entrer côté port

`IdunBattle.Entities.Factories.UnitFactory$$Build` fabrique **trois** `AbilityState` depuis la
`UnitConfiguration`, puis les distribue par
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` :

| `AbilityState` | niveau | multiplicateur | destination |
|---|---|---|---|
| `activeAbilityState` | `+0xb8` `ActiveAbilityLevel` | `+0x74` | `AddActiveAbility` |
| `passiveAbilityState` | `+0xbc` `PassiveAbilityLevel` | `+0x74` | `TriggeredAbilityComponent$$TryAdd(id, …, 2)` |
| `tertiaryAbilityState` | `+0xc0` `TertiaryAbilityLevel` | **`+0x78`** | `TryAdd(id, …, **3**)` si `+0xb0 TertiaryAbility` a une valeur |

Le **`3`** est la hiérarchie `Tertiary` : c'est le discriminant « cette entrée est une relique
équipée », et le multiplicateur n'est **pas** celui des deux autres états.

Côté port, le mirror de la registration est
`engine/runner/operations/triggers/dispatch/core.py::collect_triggered_abilities` (mirror du
registre `AbilityAndEffectCache`, volet ability-trigger). Il lisait **quatre** voies, toutes
dérivées du **gameconfig** — `traits`, `passiveAbilities`, `activeAbilities`, `relicAbilities`. Or
l'item relique équipé est un **état JOUEUR** (`BattleConfiguration.Units[].TertiaryAbility`) : aucune
de ces quatre voies ne peut le voir. Le rail manquait donc entièrement, et son absence ne produisait
ni erreur ni trace — juste un trigger jamais inscrit.

## 2. Ce qui est posé

**CINQUIÈME chemin de registration**, mirror de la branche tertiaire d'`AddConfiguredAbilities` :

* **canal** — `snapshot._load_tertiary_abilities`, alimenté par `load_state(ability_states=…)`
  (payload du RPC `unitAbilityStates`, entrées de hiérarchie **3**). Le RPC dumpe
  `TriggeredAbilityComponent+0x18` instance par instance ; `raw` = 12 × int32 depuis `+0x10`, donc
  `raw[0]` = `AbilityName` et `raw[10]` = hiérarchie, `level`/`mult` venant de `+0x20`/`+0x24` ;
* **substrat** — `UnitContext.tertiary_ability` / `…_level` / `…_variables_multiplier`, mirror de
  `UnitConfiguration+0xb0` / `+0xc0` / `+0x78`, à côté des champs actif/passif déjà portés ;
* **registration** — `collect_triggered_abilities` inscrit `RELIC_ABILITY_TRIGGERS[<nom>]`, avec
  **déduplication** quand un npc porte la même relique en dur (mirror du `TryAdd` sur
  `KeyedCollection` : la seconde insertion est un no-op) ;
* **magnitude** — `triggers/base.py::triggered_ability_state(state, unit, ability)` rend le couple
  `(level, multiplier)` de l'`AbilityState` sous lequel l'ability est montée : **tertiaire** si elle
  vient de l'item équipé, **passif** sinon. C'est ce couple que
  `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` indexe.

**Le canal était OPT-IN.** ⚠ **Plus depuis #363** : `ability_states` est un **tri-état** — un payload
(l'appelant a fait le RPC), `None` = **AUTO** (le canal se sert lui-même quand un transport ambiant
est lié, ce que `conftest.live_session` fait pour toute la suite live) et `False` = **refus
explicite**. Un état chargé hors harnais live reste strictement celui d'avant. Coût mesuré avant
branchement : **33 ms par bataille**, cache par runner. Cf. `case-363-canal-relique-par-defaut.md`.

### Pourquoi ce canal et pas `combatSnapshot.unitConfig`

Le capteur `unitConfig` publie bien `tertiaryAbilityVariablesMultiplier` (`+0x78`) mais **ni**
`TertiaryAbility` (`+0xb0`) **ni** `TertiaryAbilityLevel` (`+0xc0`) : les ajouter exigerait une
réinjection. `unitAbilityStates` porte les **trois** informations, et il les porte là où le natif les
a réellement posées (l'`AbilityState` monté) plutôt que là où elles sont déclarées. C'est donc à la
fois le canal disponible et le plus fidèle — et son jumeau côté config sert de **contrôle**.

## 3. Pourquoi `DawnBlade` et pas une autre des 32

* effet mesurable **à l'état** — `Repair(self, self, Get(hpToHeal[lvl]), ForRepair)` sur un kill en
  mêlée : on lit un entier sur les PV, pas un modificateur noyé dans une plage de dégât ;
* behaviour **déjà porté** (#317) ⇒ la mesure porte sur **le rail** et rien d'autre ;
* porteur en **état 3** (hors catalogue) ⇒ le montage exerce aussi la voie d'injection catalogue.

## 4. Ce qui a été MESURÉ live (`rnca9r7q6c`, `MC1_67`, seed 777, `tauFarsight` ← `DawnBlade`)

Montage : `catalog_inject.write_augmented_seed_bc([tauFarsight])` puis
`rl_duel build --seed-bc … --equip-relic "tauFarsight:DawnBlade:<lvl>" --unit-stat
"tauFarsight:RemainingHealth=2000" --hp-target 1 --dmg-target 1`, positions **conduites** (le porteur
est amené au contact), kill réel par l'attaque normale (`ActiveAbilityType` **69**, `applyAction`
`kind: ability` — `kind: "attack"` n'existe pas).

La **même capture pré-kill** est rejouée trois fois côté port ; le natif est le delta de PV du
porteur sur ce seul coup.

| niveau | NATIF (ΔPV) | port **avec** rail | port **sans** canal | port niveau **passif** | `hpToHeal[lvl]` |
|---|---|---|---|---|---|
| 8 | **+6745** | 6745 | **0** | **7273** | 6745 |
| 3 | **+5423** | 5423 | **0** | **7273** | 5423 |

Les deux bras de droite sont les deux façons de se tromper, et ils rougissent tous les deux :
« sans canal » est l'état d'avant ce cas ; « niveau passif » est ce que le port faisait de la
magnitude (les passifs valent **50** sur tout runner normalisé, et
`TryGetVariableArrayForLevel` clampe ⇒ **toujours** `hpToHeal[10] = 7273`).

**Deux régimes NÉGATIFS, sur le même montage** — inscrire la relique ne doit pas rendre le port
permissif :

| régime | NATIF | port | gate |
|---|---|---|---|
| kill à **d = 2** (portée d'arme) | **0** | 0 | `IdunBattleLogic.Entities.DSLTriggers$$IsDefeatedByMeleeAttack` |
| porteur à **PV pleins** | **0** | 0 | `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` |

## 5. `TertiaryAbilityVariablesMultiplierPercentage` — l'écart « 200 vs 100 » de #237, tranché

L'écart signalé par #237 (« **200** au seed contre **100** synthétisé ») n'est **pas** un écart de
synthèse : c'est le multiplicateur de progression du porteur, et il suit exactement la présence
d'une relique.

* seed BC, 175 unités : `TertiaryAbilityVariablesMultiplierPercentage` = **200** sur **4** entrées,
  **100** sur **171**. Les 4 sont EXACTEMENT celles qui portent une `TertiaryAbility`
  (`necroSpyder`, `orksRuntherd`, `admecMarshall`, `admecRuststalker`), et elles portent **aussi**
  `AbilityVariablesMultiplierPercentage = 200`. Les 171 autres n'ont pas de relique : leur `+0x78`
  est un champ neutre que rien ne lit — `catalog_inject.synthesize` écrivant `100` est correct.
* en bataille, mesuré à **deux sources indépendantes** sur le porteur monté :
  l'`AbilityState` (`unitAbilityStates`, `+0x24`) = **100** et `unitConfig.tertiary
  AbilityVariablesMultiplier` (`+0x78`) = **100** — elles coïncident, ce qui autorise à seeder le
  port depuis la première. Le multiplicateur d'ability (`+0x74`) vaut, lui, **180** : deux champs
  distincts, deux valeurs, et c'est ce contraste qui établit que le port lit le bon.

⚠ Sans conséquence de magnitude **sur cette relique** : `hpToHeal` n'est pas dans
`variablesAffectedByRarityBonus` de `DawnBlade`, donc `TryGetVariableArrayForLevel` n'applique aucun
scaling. Le champ est porté quand même — c'est le natif qui décide de l'appliquer, pas nous.

## 6. Ce que ce cas a corrigé en route

* **`hpToHeal` mal étiqueté dans `case-237` §6bis** — les valeurs `537` / `579` y sont annoncées
  comme `hpToHeal` de `DawnBlade` ; ce sont ses **`extraDmg`** (`[390…579]`). Le probe #237 sonde
  `sorted(variables)[0]`, donc `extraDmg`. `hpToHeal` vaut `[4895…7273]`. Corrigé dans la fiche.
* **« Aucun porteur de `DawnBlade` n'est confrontable par le harnais »** (`probe_317_dawn_blade.py`
  et `test_dawn_blade_repair.py`) — vrai à l'écriture, faux depuis #237 + ce cas. Les deux en-têtes
  sont corrigés ; le sondage `--pool` reste (sa mesure — le npc ne se normalise pas — tient
  toujours, seule sa conclusion tombe).

## 7. Résidus fermés

* **`N317-a`** (le rail COMBAT ne lit pas la relique équipée) — **FERMÉ**. C'est l'objet de ce cas.
* **`N317-e`** (le niveau de la variable d'une relique est hors substrat) — **FERMÉ** :
  `triggered_ability_state` rend le couple tertiaire, mesuré exact sur deux niveaux.
* **`N317-d`** (le marqueur « défaite par attaque de MÊLÉE » est approximé positionnellement) —
  **le régime redouté est MESURÉ, et le port a raison dessus.** Le risque nommé était « une arme à
  distance employée à l'adjacence » : `tauFarsight` porte une arme de **portée 2**, et le natif
  **soigne** quand il tue depuis une tuile adjacente (donc il compte la défaite comme mêlée) et **ne
  soigne pas** depuis `d = 2`. La lecture positionnelle du port coïncide sur les deux bras. Le résidu
  n'est pas *démontré* nul pour autant : un seul porteur, une seule arme — il reste ouvert comme
  approximation, mais son régime discriminant connu ne le prend plus en faute.

## 8. Ce qui n'est PAS couvert

* ~~**Le canal n'a qu'UN producteur**~~ — **FERMÉ par #363** (`case-363-canal-relique-par-defaut.md`).
  Le coût a été mesuré avant d'être tranché (33,4 ms médians, **constants** de 4 à 10 unités, contre
  312–1347 ms pour la capture déjà faite), et le canal est **ON PAR DÉFAUT**. La prémisse
  « `engine_validate` / `rl_collect_batch` ne le passent pas » s'est révélée une **non-question** :
  balayage AST, **0** appel de `load_state` hors `tests/` et `probe_*` sur **569**.
* **Une seule relique sur 32.** Les 31 autres n'ont pas d'entrée dans `RELIC_ABILITY_TRIGGERS` (leur
  ability n'est pas portée) : le rail les inscrirait, il n'a rien à inscrire. Chacune est une tranche
  de port à part entière.
* **Les 4 unités qui équipent une relique AU SEED** (`necroSpyder` 1462, `orksRuntherd` 1475,
  `admecMarshall` / `admecRuststalker` 1457) ne sont pas confrontées ici : leurs abilities ne sont
  pas portées, et `buildNormalizedBC` écrase leur niveau à 50 (donc palier 10) — c'est le régime que
  le montage #237 voie A décrit. ⚠ **#363 les a depuis amenées en bataille et mesurées** : les
  quatre arrivent côté port avec `(ability, 50, 200)`, conformes aux deux oracles (natif hiérarchie 3
  et `seed-bc.json`). Ce qui reste non couvert est l'**effet** de leurs abilities, pas leur montage.
* **`allow_unlisted` toujours pas joué live** (résidu #237 inchangé) : le montage utilise le porteur
  légitime de `allowedUnits`.
* **La face DÉCISION n'est pas touchée.** Elle lit déjà le kit déclenché réel par un autre chemin
  (`engine/ai/context.py::live_triggered_ability_ids`, même RPC). Les deux lectures coexistent ;
  les unifier n'a pas été tenté.
