# #10030 — quatre cliquets rouges, et le parseur autoritaire qui lisait la prose

Mesuré sur `master` = `b1e50c7c`, build `t6dpr4k06g`, arbre propre. Quatre fichiers de cliquets
rouges, trois d'attribution + un méta-cliquet. **Aucun n'accusait un inventaire faux** : trois
accusaient du code neuf non instruit, le quatrième portait quatre prémisses expirées **et** un
défaut réel du parseur qu'il utilise.

| cliquet | verdict | cause |
|---|---|---|
| `test_514_allunits_pool8_offline` | **le cliquet a RAISON** | 3 ports neufs livrés sans déclarer leur attribution pool-8 |
| `test_449_r2_spread_face_combat_offline` | **le cliquet a RAISON** | 1 port neuf livré sans son attestation de variance nulle |
| `test_1041_kit_item_voies_offline` | **le cliquet a RAISON** | 3 conteneurs neufs muets dans la partition |
| `test_1081_foyer_factory_offline` | **PRÉMISSE EXPIRÉE (×4) + défaut du parseur** | témoin figé + 3 fiches déplacées ; `backlog_entries` mordait sur l'étiquette SANS deux-points |

---

## 1. `#514` — trois sites `AllUnits(` non attribués

Le cliquet exige que tout site exécutable écrivant `AllUnits(` (pool 8 = **morts inclus**) cite
le symbole natif qui le justifie. Trois sites l'écrivaient sans déclaration :

| site | natif LU (`t6dpr4k06g`) | verdict |
|---|---|---|
| `engine/runner/abilities/admec.py::solar_atomizer_tree` | `IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$ExecuteBehaviour` | pool 8 **JUSTE** |
| `engine/runner/abilities/admec.py::invocation_of_machine_vengeance_tree` | `...Active.InvocationOfMachineVengeanceAbility$$ExecuteBehaviour` | pool 8 **JUSTE** |
| `engine/runner/operations/triggers/loki/power_up_spawn.py::spawn_tile_tree` | `...Triggered.Loki.APowerup_SpawnAbility$$GetSpawnTile` | pool 8 **JUSTE** |

Les trois décompilés écrivent un appel **explicite** à `IdunBattleLogic.Entities.DSLSelectors$$AllUnits(<dsl>)`,
jamais le champ partagé `<dsl>+0x20` (= `AllAliveUnits`). Le port était donc correct ; ce qui
manquait était la déclaration. Les trois sont inscrits dans `SITES_POOL8` avec leur symbole.

### Le cran ajouté : l'attribution n'est plus une prose libre

L'étape 3 vérifiait qu'un site est **déclaré** ; elle ne disait rien de ce que la déclaration
**cite**. Un symbole plausible mais qui n'appelle pas `DSLSelectors$$AllUnits` rendait donc le
cliquet vert sur une justification **inventée** — pire que l'absence, parce qu'elle a l'air lue.
**Cran 3b** : tout symbole déclaré (hors auto-tests, reconnaissables à leur forme `<...>`) doit
appartenir au relevé `CALL_SITES_NATIFS_POOL8`. Contre-épreuve par mutation dans le test.

Le relevé lui-même a été **re-dérivé** (`list_xrefs` sur `t6dpr4k06g`) : **24 appels**, identiques
à ceux du 2026-08-07 sur `rnca9r7q6c` (28 xrefs dont 4 `DATA`). Il n'était donc pas périmé — mais
`APowerup_SpawnAbility$$GetSpawnTile` y figurait déjà **sans que le site porté soit déclaré**,
l'écart exact que l'étape 3 existe pour voir.

## 2. `#449-r2` — un site à variance nulle sans attestation

`engine/runner/operations/triggers/loki/solar_atomizer_attack.py:138` (`AttackWithAttackDamage`),
livré par #894-r2, prend le défaut `amount_spread_pct` sans attestation : `master` en était rouge.

LU dans `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SolarAtomizer_PendingAttackAbility$$CreateBehaviour` :
les **cinq qwords** du 8ᵉ argument (`Nullable<AttackDamageBehaviourOptions>`, 0x28 octets) sont mis
à **ZÉRO** juste avant l'appel à `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`.
Nullable VIDE ⇒ octet d'aiguillage `+6` nul ⇒
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` prend la branche **PLATE**.

**Contre-preuve du même décompilé** : le 5ᵉ argument (`damageProfile`) est un `Nullable` **NON
vide** (`System.Nullable<T>..ctor(&local_c0, &profil)` juste avant). La struct à zéro est donc une
**écriture**, pas un artefact de décompilation.

⇒ La variance nulle est **JUSTE** ; l'attestation est inscrite dans `EXPECTED_ZERO`.

## 3. `#1041` — trois conteneurs muets

Le recenseur **dérive** bien (il a vu les trois neufs) ; c'est la partition qu'il fallait compléter.

* **`engine.entities.effects.factory.ABILITY_INIT_OWNER_BOND_EFFECTS`** → **VOIE**. Pendant BOND de
  `ABILITY_INIT_OWNER_EFFECTS` (#963-r5) : même trigger d'init partagé, **même boucle
  consommatrice** (`spawn._seed_ability_owner_effects` via
  `get_owner_bond_effects_added_on_ability_init`), mais le `CreateBehaviour` écrit `AddBondEffect`
  au lieu d'`AddEffect`. Inscrite avec `gate=GATE_EFFET_CLASSE`, comme son jumeau.
* **`...loki.call_ripper_swarms.SPAWN_ABILITY_PALIERS`** → **ÉCARTÉ, FAIT NATIF** : les trois bras
  du fork `CallRipperSwarms_PendingSummonEffect$$GetSpawnAbilityType`, dans l'ordre du décompilé.
  Table de routage, pas un montage. Mesure : **0 bascule**.
* **`...loki.call_ripper_swarms.SPAWN_ABILITY_CONFIG`** → **ÉCARTÉ, DONNÉE ANNEXE** : quelle
  `AbilityConfiguration` (`config@this+0x20`) un palier triggered lit. Mesure : **0 bascule**.

### Le gate ne savait pas lire la forme de sa valeur

`_gate_passe` ne retenait que les `str` d'un conteneur. La valeur de la voie BOND est
`[("<Effet>", "<selecteur>")]` : il n'y aurait trouvé **aucune cible**, donc le gate serait
**tombé**, donc `Lifewards` aurait été compté **PARTIEL** — un montage complet dégradé en
silence. Nouveau foyer `_cibles_d_effet`, qui retient le **premier membre** du tuple.

⚠ Aplatir tout le tuple ferait entrer `"Parent(Owner)"` dans les cibles, et le second cran du gate
(`classe_d_effet_native`) jugerait un mot qui n'est pas un `EffectType`. **Mesure au 2026-08-18 :
les trois autres voies gate-ées ne portent que des `str`, donc l'extension est INERTE pour elles.**

Après : `MUETS 0`, `PORTE 429 / PARTIEL 1 / ABSENT 59`, `Lifewards` PORTE par 5 voies (dont la
neuve). Contre-épreuve par mutation : sous la lecture « `str` seulement », `Lifewards` bascule
PARTIEL.

## 4. `#1081` — quatre prémisses expirées, et le parseur qui lisait la prose

### 4a. Le défaut réel : `backlog_entries` mordait sur l'étiquette SANS deux-points

`_MARQ_FOYER` / `_MARQ_BLOCAGE` acceptaient un `:` **optionnel** (`:?`). Le marqueur mordait donc
sur toute occurrence du **mot** en prose — `**BLOCAGE RE-MESURE ET CONFIRME**`,
`(champs FOYER/BLOCAGE RETIRES : ...)`, `le FOYER réel n'était pas ...` — et le parseur
**autoritaire** rendait le premier mot alphabétique qui suivait.

**Mesure sur les 1024 entrées du backlog (2026-08-18)** :

| | avant | après |
|---|---|---|
| champs `BLOCAGE` hors vocabulaire | **4** (`RE`, `RE`, `RETIRES`, `sont`) | **0** |
| champ juste mais périmé | 1 (`#175-r3` rendait `etage`, sa MAJ écrit `aucun`) | 0 |
| entrées dont le `FOYER` capturait de la prose | **34** | 0 |
| chemins de foyer dérivés | 1071 | **1008** (63 fantômes retirés) |
| entrées qui **PERDENT** un champ réel | — | **0** |

Les 2 seules entrées dont la ligne porte pourtant un `FOYER:` (#433-r4-r3-r1-r3, BL-1020r) l'ont
**dans une zone barrée**, donc déjà retiré par la convention du backlog.

Correctif : `\*{0,2}FOYER\*{0,2}\s*:\*{0,2}` — les `**` restent tolérées des deux côtés
(`**FOYER:**`, `**FOYER**:`, `FOYER :` sont des formes réellement écrites) ; c'est le `:` qui
sépare un champ d'une phrase.

### 4b. Le témoin de parseur était un couple FIGÉ, et il s'est périmé en trois jours

Il valait `("943-r7", "seeding")`. La fiche a été **résolue le 2026-08-15** et son champ est passé
à `aucun` : le cliquet rougissait sur un **mouvement légitime** du backlog, pas sur le vice gardé.

Le témoin est désormais **DÉRIVÉ** (`temoins_de_parseur`) : **toutes** les entrées qui citent
l'étiquette sans deux-points, avec trois crans — non-vide du gisement, champ rendu **du
vocabulaire**, et **non-dégénérescence** (au moins une entrée où la lecture naïve diffère du champ
rendu). Mesure : **28 entrées** citent l'étiquette en prose, **25 discriminent**, **0 hors
vocabulaire**.

Contre-épreuve exécutable (`test_1081_le_temoin_de_parseur_est_DERIVE_et_MORD`) : en remettant le
`:?`, des champs hors vocabulaire **réapparaissent** — le cran mord.

### 4c. Trois fiches déplacées, prises pour des rouges

L'étage 3 comparait le champ écrit à une attestation par résidu, et traitait « fiche absente »
comme un rouge. Or trois des dix ont bougé, **toutes par une fermeture réussie** :

| fiche | mouvement | par |
|---|---|---|
| `#924-r1` | FERMÉE ; sa MAJ écrit « l'attribution `etage` de #924-r2 est RÉFUTÉE […] il ne reste aucun étage à construire » | — |
| `#952-r2` | **RENOMMÉE `#952-r7`** (son objet a changé : convention de nommage d'`ai/state_bridge.py`) | `5b77f894` (#10014) |
| `#961-r3` | RETIRÉE — « delta 579 → 0, ratio 1.000000 : la cause était le CANAL de capture du probe » | `a0d3d8ba` (#1091) |
| `#999-r1` | FERMÉE — « LES DEUX ARBRES DE LA POSE SONT PORTÉS », ce que l'étage 1 confirme (0/6 non portée) | — |

⇒ `blocage_mesure = None` signifie désormais « **ce n'est plus un résidu OUVERT** » : la fiche doit
être **fermée** (`~~..~~`) **ou retirée**, les deux acceptées. Confondre les deux avec un rouge
faisait rougir le cliquet sur sa propre mesure de succès.

⚠ **La convention « une fiche fermée ne porte plus FOYER/BLOCAGE » n'est PAS tenue, et c'est
mesuré** : **115 des 615 fiches fermées (18,7 %)** en portent encore un. Le probe l'exigeait — une
cinquième prémisse fausse. Le cran est retiré **avec sa mesure**, pas par commodité.

**Anti-vacuité** : si les dix devenaient toutes fermées ou retirées, l'étage ne comparerait plus
aucun champ et passerait pour vert. Il rougit alors explicitement. État courant : **2 ouvertes
comparées** (#922-r1 `aucun`, #965-r2 `etage`), 8 fermées ou retirées.

---

## Effet de bord signalé — `test_603_index_foyers_offline` (**pas ma tranche**)

Le correctif de `backlog_entries` est le **foyer partagé** de #603. Mesuré avant/après :

| étage | avant | après |
|---|---|---|
| `test_etage3_aucun_foyer_ne_designe_un_fichier_disparu` | ROUGE (23 absents, **4 pourris**) | ROUGE (21 absents, **les mêmes 4 pourris**) |
| `test_etage4_le_vocabulaire_de_blocage_est_tenu` | **ROUGE** (`assert not ['RE']`) | **VERT** |
| `test_etage5_l_index_se_re_derive_a_l_identique` | ROUGE (480 foyers) | ROUGE (479 foyers) |

Bilan **3 failed → 2 failed**. Les 4 foyers pourris (`frida/hooks/features/ui-nav.ts`,
`scripts/python/game_nav.py`, `scripts/python/gamenav/`, `scripts/python/gamenav/carte.py`, cités
par #595-r1/#595-r2/#596/#596-r2) sont **identiques** avant et après : ce sont de vraies fiches à
requalifier, pas des artefacts de prose. `docs/rl/index-foyers.md` est un **généré** déjà périmé
sur `master` ; il l'est d'un foyer de plus après ce correctif — **non régénéré ici** (doctrine :
régénération au merge, acteur unique).

## Résidu ouvert

* **#10030-r1** — un identifiant de résidu **renommé** est indistinguable d'un résidu disparu.
  `#952-r2` est devenu `#952-r7` sans qu'aucun mécanisme ne relie les deux, et tout consommateur
  qui cite l'ancien (`probe_1081.LES_DIX`, une case-doc, un message de commit) le croit retiré.
  Coût mesuré : un rouge de cliquet diagnostiqué à la main.

## Ce que cette tranche NE couvre PAS

* **Aucune confrontation live.** Les quatre items sont offline par construction (inventaires AST,
  parseur de backlog, registres importés). Les trois ports dont l'attribution est inscrite
  (`SolarAtomizer`, `InvocationOfMachineVengeance`, `APowerup_Spawn`) sont **lus au décompilé**, pas
  rejoués en bataille — leurs porteurs sont des **npc/boss** (`admecBossBelisarius`) et des
  power-ups.
* Le **relevé** `CALL_SITES_NATIFS_POOL8` reste une attestation : le cran 3b garde qu'un symbole
  déclaré y figure, pas que le relevé soit à jour. Il a été re-dérivé une fois ici.
* Les étages 3 et 5 de `test_603` restent rouges (cause : 4 foyers pourris + généré périmé).
* La règle « une fiche fermée perd ses champs » n'est **plus** gardée nulle part — elle ne l'était
  qu'implicitement par ce probe, et la mesure établit qu'elle n'est pas la pratique.
