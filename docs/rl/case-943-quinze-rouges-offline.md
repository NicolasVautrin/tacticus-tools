# #943 — les quinze rouges OFFLINE de `master`, et ce qu'ils avaient en commun

Mesure d'entrée (`probe_457 --jobs 8`, `origin/master` = `8f357878`) : **326 fichiers, 311 VERT,
15 ROUGE**, tous dans `scripts/python/tests/engine/`. Aucun runner, aucune session Frida.

## 1. Le patron : **treize sur quinze** sont notre PROPRE cadence de portage

Douze fichiers rouges accusent la même chose sous des noms différents — une entrée est arrivée
dans un registre **sans sa ligne de déclaration jumelle**, et le cliquet qui garde ce couplage a
viré au rouge sur `master` sans que la PR fautive le voie. Les commits armeurs sont **tous** du
2026-08-10 ou du 2026-08-11, c'est-à-dire des ~36 heures qui précèdent la mesure.

| rouge | ce qu'il accusait | armé par | réparation |
|---|---|---|---|
| `test_287r14_get_actual_target_offline` · `test_287r14r1_resolution_tile_target_offline` | `1194` `NovaShield`, `1209` `InfernalCannon`, `1231` `TitanhammerSquad` posent `TargetIsTile` sans résoudre leur cible en tête d'`execute_behaviour` | `0ac24084` (#605), `d87b2095` (#895), `f65f3ded` (#448-r2d-r2) | `target_id = self.get_actual_target(...)` en tête des trois |
| `test_421_effect_active_gate_offline` | 3 classes au registre des effets-triggers sans rail déclaré dans `probe_229.RAIL` | `903cbe3e` (#922), `dde62f07` (#892) | rails `ARRAYSET` lus au décompilé + entrée `ARRAYSET_READS_BY_TREE` |
| `test_camo_seed_inventory_offline` · `test_refresh_active_flag_discriminant_offline` | 6 classes surchargent `is_active` sans verdict de POSE ni attestation | #904/#906, #909, #911, #917, #919 | `POSE_VECTOR` + `CONDITIONS_PORTEES_ATTESTEES` |
| `test_statmod_captured_channel_offline` | 3 classes re-dérivent une magnitude ability-state sans classification de leur feuille de pose | `f65f3ded` (#448-r2d-r2), `834c6950` (#913), `5dbe6c9c` (#928) | `POSE_TARGETS` : les trois sont `SRC` |
| `test_433_r4_…_caster_reason_offline` | `1032` `Catalyst`, `1173` `ArcScourge`, `1192` `NovaBoost` portent `CasterMatchesDynamicRule` sans régime déclaré | `c94aa0e2` (#697), `cf11fd3b` (#894), `d87b2095` (#895) | 2 corps RELUS (`NOT_DERIVABLE`), 1 absent des tables (`NOT_READ`) |
| `test_270r1_volet2_dict_keys_enum_offline` | `1216` : la valeur du couple a CHANGÉ en migrant | `46ba95e8` (#923) | snapshot re-mesuré, la correction est JUSTE (§2) |
| `test_lions_wrath_custom_utility` | `KeyError: 1217` — la prémisse « face COMBAT non portée » a expiré | `d62d94e3` (#889) + `dde62f07` (#892) | lecture par le RÉSOLVEUR, disjonction RETOURNÉE |
| `test_462r4eor2_over_reduce_purge_offline` | `AttributeError` — le double de test ne portait pas `by_unit` | `aa690301` (#924, qui porte `AttackQuery$$HasHealBlockers`) | surface du double élargie, montage réparé |
| `test_270r4r2_cycles_imports_offline` | SCC `effects` → `effects.factory` → `loki.dark_angels_passives` → `effects` | `bade659e` (#925) | `from .. import x` (déclare le PAQUET) → `import <module> as X` |
| `test_270r4r2r2r3_gardes_du_hissage_offline` | un différé `import gameconfig as GC` OMBRAGE le module-level du même nom | `cf11fd3b` (#894) | différé RETIRÉ (le hissage l'avait rendu redondant) |
| `test_477r24r1_slots_interface_offline` | 2 citations de slot au NOM faux | `568deb8c` (#889-r5), `53d9766b` (#886) | §3 |
| `test_603_index_foyers_offline` | `docs/rl/index-foyers.md` non re-dérivable | `ff201caf` (#932) | index régénéré (le résidu `#935-r1` était entré sans lui) |

**Ce que ça dit.** Ces douze cliquets font exactement ce pour quoi ils existent, et pourtant le
rouge a vécu jusqu'à 36 h : ils ne sont joués ni par la PR qui les arme, ni au merge. Le coût
n'est pas la réparation (mécanique, une ligne par entrée) — c'est la **latence de détection**.

## 2. Le seul rouge où le PORT avait raison contre le TEST

`test_270r1_volet2` fige `(1216, (32788, True, **None**, 1))`. `#923` (`46ba95e8`) a re-lu le
préset et remplacé `range=None` par `RANGE_SELF` sur `MartialExemplarAbility` — donc la valeur
EFFECTIVE a changé, et l'étage 2 (qui interroge le résolveur, pas le dict) l'a vu. La tranche a
simplement omis de reporter la mesure dans le snapshot.

RE-VÉRIFIÉ ici avant de toucher au snapshot, indépendamment de #923 :

* `IdunBattle.Core.Services.TargetingOptions$$.cctor` écrit le préset `<statics>+0x280` en copiant
  `<TargetingRange statics>+0x60..0x77` dans `<preset>+0x288..0x29f`, avec `<preset>+0x280 = 1`
  (`isSelfCasting`), `+0x2a0 = 1` (`forceMeleeTarget` = `RangedBool.False`) et `+0x2a8 = 0x8004` ;
* `IdunBattle.Core.Services.TargetingRange$$.cctor` pose `<statics>+0x60 = 1`
  (`onlyAdjacent` = `RangedBool.False`), `+0x68 = Nullable(0)` (`overrideRange`), `+0x70 = null` —
  c'est-à-dire `RANGE_SELF`.

Le snapshot portait donc un aveu de non-lecture, pas une mesure. **Corollaire non corrigé :** le
même préset est recopié par `IdunBattleLogic.Entities.Abilities.Active.Loki.InstrumentsOfVengeanceAbility$$.ctor`
(forme STATIC-COPY), et `TARGETING_OPTIONS_UNPORTED[1215]` porte encore `range = None` — résidu
**#943-r1**, laissé ouvert parce que le corriger RESSERRE un gate qu'une tranche 100 % offline ne
peut pas confronter live.

## 3. Deux citations de slot fausses — le site, pas la table

`probe_477r24r1` apparie un `slot <n>` et un nom de méthode sur une fenêtre de 3 lignes, dès qu'un
receveur (`processor.` / `OperationProcessor`) apparaît dans le SPAN du couple. Les deux rouges
étaient des **sur-appariements**, et la table avait raison :

* `runner/abilities/behaviours/combat.py` écrivait `// slot 0` en fin d'une ligne de pseudo-C
  d'`ITargetsSelector`, juste au-dessus d'un `processor.ActiveAbility(...)` → couple
  `(0, ActiveAbility)`. Les deux numéros sont maintenant dans la PROSE au-dessus (où ils étaient
  déjà), les lignes de pseudo-C nomment l'interface.
* `runner/components.py` écrivait `` `…ResurrectUnitOperation$$Execute` y arrive par
  `processor.<slot 35 = FinishUnitTurn>(…)` `` → `Execute` était à moins de 40 caractères de
  `slot 35`, d'où le couple `(35, Execute)`. Une incise déplacée devant l'appel suffit ; le couple
  juste, écrit au même endroit, n'a pas bougé.

Le remède employé est celui que `case-477r25` documente (réécrire le site), pas le marqueur
`[slot-attribution:refute]`, qui est réservé aux lignes citant une attribution RÉFUTÉE.

## 4. Le cycle d'import : `from . import x` déclare le PAQUET

`from .. import aura_selectors as ASel` (posé par #925 pour garder la FORME B) refermait le SCC.
La forme B est conservée — c'est `import engine.entities.effects.aura_selectors as ASel` qui la
donne sans déclarer le paquet, exactement comme `services/ability_range.py` le fait déjà. Le
compte reste **430/430** modules importables seuls.

## 5. Le quinzième — un rouge HONNÊTE, et une étape 5 qui devenait inerte quand il y avait
quelque chose à garder

`test_433r4r1r4r2r1r1_derivation_morte_offline` portait DEUX rouges, et **une seule cause**.

L'étage 2 de `probe_433r4r1r4r2_neigh_channel_wired` (« un mirror déclaré fait-il de la géométrie
NUE sans toucher le canal de voisinage ? ») nommait trois foyers :

* `playbook/noncomparable/bio_minefield.py::_free_adjacent_tiles` (#934, arrivé **pendant** cette
  tranche) — **RÉPARÉ** : son jumeau exact, `doctrina_imperatives._free_adjacent_tiles`, mirrore le
  MÊME `BattleQuery$$GetFreeAdjacentTiles` et consomme déjà `neigh_by_pos`. L'adjacence passe
  désormais par `engine.battle_query.is_adjacent`, qui dégrade seul en `hexgeo` quand les canaux
  sont vides — donc NO-OP démontrable là où ils le sont ;
* `aura_selectors.py::adjacent_friends_including_owner` (#925) et
  `icon_of_obstinacy.py::create_aura_attack_damage_bonus_for_ally` (#913) — **NON RÉPARÉS**,
  résidu **#943-r4**. Balayage des **64** fonctions qui citent `IterateAdjacentTiles` : **3**
  seulement font de la géométrie nue, mais **trois autres** (`effect_targets._adjacent_friends`,
  `imperative.create_aura_attack_damage_bonus_for_ally`, `get_em_runtz._spawn_tile_count`) font la
  même et sont invisibles au critère — leur docstring ne NOMME pas le natif. Réparer ici seulement
  serait le fork que les deux sites annoncent, et la porte d'élévation peut déplacer la ground
  truth live de #930 (`statModSources`, `orksBigMek`) qu'une tranche offline ne peut pas re-mesurer.

**Le second rouge du fichier était un DÉFAUT DU CLIQUET, et il est réparé.** L'étape 5 re-mesure
« la suspension d'un natif est-elle encore justifiée ? » en l'armant pour de faux et en regardant
si quelque chose rougit. Elle regardait la rougeur **ABSOLUE**, pas le **DELTA** : dès qu'un vice
existe ailleurs — le régime normal d'un cliquet, qui existe pour en trouver — toute suspension
devient « justifiée », y compris celle d'un natif absent de toute docstring. Contre-épreuve dans
les deux sens après correction : `NatifQuiNexistePas` est dénoncé PÉRIMÉ (delta vide), et les deux
vraies suspensions restent justifiées avec leurs foyers **attribuables** (`AdjacentTiles` → 1 foyer
au lieu d'une liste polluée par les rouges des voisins).

## 6. Ce qui n'est PAS couvert

* **`#943-r4`** — les deux sélecteurs d'aura à géométrie nue (§5). `test_433r4r1r4r2r1r1_
  derivation_morte_offline::test_le_VICE_REEL_de_orks_est_CORRIGE_et_la_liste_ELARGIE` reste
  **ROUGE** : 14 fichiers sur 15 sont verts, celui-ci porte 1 test rouge sur 12.
* **`#943-r1`** — `TARGETING_OPTIONS_UNPORTED[1215].range` (§2).
* **`#943-r2`** — `scripts/cliquets-cache/probe_477r24r1_slots_interface.tsv` périmé : `rc=6`, et
  **24** lignes de diff sur **2372** sont imputables à cette tranche. Non régénéré ici : le cache
  se re-clé par `sha256` de chaque fichier balayé, donc le régénérer garantit un conflit avec toute
  PR en vol.
* **`scripts/ratchets-457-vert-offline.json`** — laissé NON commité, comme demandé.
* **Aucune confrontation LIVE.** Les trois `get_actual_target` ajoutés sont idempotents (la
  résolution était déjà faite par `AbilityHandler` au rang natif) : ils ne mordent que sur un appel
  DIRECT à `execute_behaviour`. Le régime live n'a donc rien à mesurer — mais il n'a pas été mesuré.
* **Les 63 lignes `nom_ecarte_par_un_cran`** de `probe_477r24r1` restent le gisement de #477-r34 ;
  cette tranche n'y touche pas.
