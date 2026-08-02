# #456-r1 — les 9 lignes du terme MOVE : DEUX causes, une par ability, et elles sont additives

**Question binaire** : les 9 lignes où le port rend `0.0` viennent-elles **(a)** d'un playbook non
porté, ou **(b)** d'un kit lu trop étroit ?

**Réponse : LES DEUX, sur des abilities différentes, et le partage est mesuré — 4 + 5 = 9.**

| ability | porteur | cause | preuve |
|---|---|---|---|
| `1145 SereneUnifier` | `tauAunShi` (HERO du pool) | **(a)** playbook non porté | kit natif `[1145]` == kit port `[1145]` ; `--drop-playbook 1145` rouvre **5/102** |
| `1120 SaviorProtocols` (greffée) | `tauCrisis` | **(b)** kit trop étroit | kit natif `[1120, 1030]`, kit port `[1133]` ; `--no-bind` rouvre **4/102** |
| `1133 CyclicIonBlaster` | `tauCrisis` | **ni (a) ni (b) — le natif la skippe AUSSI** | kit natif `[1133, 1030]` (montage non greffé) et **`nat_owner ≡ {0.0}`** |

Le troisième verdict corrige #456, qui nommait `1133` comme cause. Son `missing` dérivait du kit
**PORT** (gameconfig), jamais confronté au kit natif ni au fait que le natif rend `0.0` pour son
porteur. Aucune classe `CyclicIonBlasterPlaybook` n'existe (ni `ghidra/functions.tsv`, ni
`frida/classes.tsv`) : `PlaybookDatabase$$LoadPlaybook` rend `null` et le dispatcher `continue` —
exactement ce que fait le port.

---

## 1. Le discriminant est le KIT, pas la valeur

`probe_456r1_move_kit_vs_playbook.py`. Il confronte, **par unité**, la collection que
`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
énumère (`case.unit@+0x10` → GetComponent → `+0x18` → `GetEnumerator`, lue par `unitAbilityStates`,
`raw[0]`) à ce que le port boucle (`runner_tile_leaf_ctx(...)["unit_triggered_abilities"]`).

Son verdict a **trois** états, et c'est le troisième qui manquait à #456 :

* **(b) décidable seul** — `kit_natif \ kit_port ≠ {}` est un fait de canal, aucune valeur requise ;
* **(a) SUSPECTE** — ability sans playbook porté *et* natif non nul. Jamais établie ici : le natif
  skippe lui aussi toute ability sans playbook, donc l'imputation demanderait la décomposition ;
* **(a) ÉCARTÉE PAR LA MESURE** — abilities sans playbook porté mais `nat_owner ≡ {0.0}`. Sans cet
  état, tout kit un peu fourni se lirait comme un trou (`1143`, `1051`, `1044`, `1251`, `1250`,
  `1518`, `1024`, `1030` : **8 ids**, tous écartés ainsi).

La suspicion résiduelle est levée par la **valeur** : un accord total prouve qu'aucune ability
manquante ne contribue.

## 2. Cause (a) — `SereneUnifierPlaybook`, porté

`IdunBattle.AI.Playbook.Loki.SereneUnifierPlaybook$$.ctor` → base avec `0x479` = **1145**.
`…u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` :

```
units = query.GetAdjacentFriends(case.MovementTile, case.Unit);   // slot 0x83, self INCLUS
units.RemoveAll(u => u.Id == case.Unit.Id);                       // <>c__DisplayClass1_0.b__0
yield Fix64.op_Implicit(units.Count * 0x65);                      // 101, LITTERAL
```

Quatre lectures, toutes dans `engine/playbook/serene_unifier.py` :

1. **`101` est un `imul` du corps, PAS un poids BC.** Aucun `GetUtilityValue`, aucun
   `GetNumberConstant` dans la SM — il n'y a **rien à chercher** dans `BC.Utilities`, et une clé
   inventée y serait une fausse vérité. La mesure live le corrobore indépendamment : les totaux
   natifs du porteur sont exactement `{0, 101, 202, 303}`.
2. **`RemoveAll`, pas `FilterInPlace`** — la liste est mutée puis comptée, et le prédicat garde ce
   qui DIFFÈRE. `FilterInPlace(u.Id == case.Unit.Id)` bornerait le compte à 1, donc l'utilité à
   `{0, 101}` : le natif rend **303**.
3. **Le prédicat est l'EXCLUSION DE SOI** (`Id(u) == Id(case.Unit)`). L'accesseur est celui que
   `IdunBattleLogic.Validation.MessageValidator$$RegisterInvalidUnit` boxe comme identifiant d'unité
   et que `IdunBattle.Operations.RemoveTriggeredAbilityOperation$$Execute` passe comme id d'entité à
   son event — deux sites NOMMÉS et indépendants. Nécessaire : `GetAdjacentFriends` travaille par
   TUILE et ne connaît pas « soi », et le mover reste sur son origine pendant tout le sweep.
4. **Le slot `0x83` est `GetAdjacentFriends(tile, unit)`** — le même que `KardiocoreGalvanusPlaybook`.
   Il valait `0x82` sur `gqfc5mff6c` ; le glissement de +1 se recoupe sur un second point d'appui
   (`AstartesBanner`/`FirstAmongTraitors` : `0x74` → `0x75`). **Les slots se re-lisent à chaque
   build.** L'adjacence est celle de `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, donc
   ring-1 **avec** la porte `abs(Δelev) < 2`.

## 3. Cause (b) — le kit déclenché RÉEL, dans les deux jumeaux restants

Les trois producteurs du `ctx` tile-leaf dérivaient le kit du gameconfig par `visualId`. #304 a
recâblé la face DÉCISION (`tile_leaf_ctx` → `live_triggered_ability_ids`) ; **`runner_tile_leaf_ctx`
et `scene_tile_leaf_ctx` ne l'ont jamais été** — 4 lectures sur 6 (mover + voisins × 2 foyers).

Fermé par un foyer unique, pendant exact d'`entity_trait_ids` sur l'axe ABILITY :

| pièce | fichier |
|---|---|
| substrat d'entité | `engine/entities/unit_context.py::UnitContext.triggered_abilities` (ids, tri-état) |
| lecteur | `engine/entities/triggered_ability_type.py::entity_triggered_ability_ids` |
| seed | `engine/runner/snapshot.py::_load_triggered_abilities` (toutes hiérarchies, `raw[0]`) |
| consommateurs | `engine/utilities/tile.py` — `runner_tile_leaf_ctx` et `scene_tile_leaf_ctx`, mover ET voisins |

**Le REMPLACEMENT est délibéré, et l'union serait fausse dans le sens qui compte** : elle ne peut
qu'AJOUTER, donc elle réintroduirait un passif que la bataille n'a pas monté. Mesuré : natif
`[1120, 1030]`, gameconfig `[1133]`, union `[1133, 1120, 1030]`.

Le seed **ne filtre aucune hiérarchie** — c'est ce qui le distingue de ses deux voisins sur le même
payload (`_load_passive_abilities` = 2, `_load_tertiary_abilities` = 3) : le dispatcher natif ne
filtre pas non plus. Et il **garde un id hors enum** : le natif le présente à `LoadPlaybook`, qui le
skippe ; le faire disparaître changerait le CARDINAL du kit et masquerait un enum périmé.

⚠ **Tri-état, donc le fix ne mord QUE si un transport ambiant est lié** (`snapshot.bind_live_rpc`,
#363). `probe_443r1a._port_rows` ne le liait pas — c'est le trou d'EXÉCUTION derrière la mesure de
#456. Corrigé, avec un bras `bind=False` qui EST la contre-épreuve.

## 4. Le régime le plus dangereux : le kit du port TROP LARGE

Greffe **remplaçante** de `1120` sur `tauAunShi` : le natif porte `[1120]`, le gameconfig annonce
`[1145]` — **dont le playbook est porté**. Sans le câblage, le port verse un terme FANTÔME :

| tuile | natif | port sans câblage |
|---|---|---|
| (0,0) | 40.0 | **303.0** |
| (0,2) | 0.0 | **101.0** |
| (1,2) | 20.0 | **202.0** |

`check_value` classe l'écart `wrong` = « divergence de FORMULE » — le pire diagnostic possible : il
enverrait chercher un bug dans `SaviorProtocolsPlaybook`, où il n'y en a aucun. C'est la dégradation
**permissive** que le brief demandait de chasser : le port n'omet pas de la valeur, il en **invente**.

## 5. Fichiers

| pièce | fichier |
|---|---|
| playbook 1145 | `scripts/python/engine/playbook/serene_unifier.py` (+ entrée `TRIGGERED_MOVE_PLAYBOOKS`) |
| kit d'entité | `unit_context.py`, `triggered_ability_type.py::entity_triggered_ability_ids`, `snapshot.py::_load_triggered_abilities`, `utilities/tile.py` (4 sites) |
| mesure + tranchage | `scripts/python/probe_456r1_move_kit_vs_playbook.py` (`check_kit_gap`, E4 valeur, E5 élévation) |
| contre-épreuve du câblage | `probe_443r1a_triggered_move_anchor.py::_port_rows(bind=…)` |
| gardes offline | `scripts/python/tests/engine/test_456r1_serene_unifier_and_kit_offline.py` (20) |

## 6. Validation

**Le critère du cas est atteint : 102/102 lignes en accord** (contre 93/102), 9 non nulles,
**6 valeurs natives distinctes** (`0, 20, 40, 101, 202, 303`) — les 93 autres ne bougent pas.

Généralisation, **trois couples (board, seed)** et des positions DRIVÉES :

| montage | lignes | non nulles | verdict |
|---|---|---|---|
| `MC1_67`/777, greffe 1120 sur `tauCrisis` | 102 | 9 | accord partout |
| `C4_09`/999, 3 unités déplacées | 122 | 12 | accord partout |
| `MC1_67`/777, greffe **remplaçante** sur `tauAunShi` | 100 | 4 | accord partout |
| `PVP_desert_08`/31337 | 86 | 8 | accord partout |
| `C1_35`/31337, montage d'ÉLÉVATION | 98 | 8 | accord partout, **porte exercée** |

**Six mutants offline, tous mordants** (restauration re-vérifiée) : self non exclu, facteur 100,
porte d'élévation retirée, UNION au lieu de REMPLACEMENT, seed filtré sur la hiérarchie 2, verdict
privé de l'état « écartée ». ⚠ Deux d'entre eux n'avaient **pas matché au premier essai** (motif LF
contre fichier CRLF) et rendaient VERT : une mutation non appliquée est un verdict NUL, pas un
succès.

**Deux contre-épreuves LIVE**, chacune sur son montage :

* câblage du kit retiré → **4/102** (`--no-bind`), et **5/100** de terme fantôme sur le montage
  remplaçant ;
* playbook 1145 retiré → **5/102** (`--drop-playbook 1145`) ;
* porte d'élévation retirée → **2/98** sur `C1_35`, exactement les 2 couples que E5 avait comptés.

**42 tests live** verts (4 fichiers, 0 skip) + **72 gardes offline** des tranches voisines.

### Ce qui n'est PAS couvert, nommé

* **`#456-r1a` — `_adjacent_units` (face DÉCISION) reste sur l'UNION** (`tile_leaf_ctx`, kit du
  VOISIN). Le mover y est en remplacement depuis #304, le voisin non : un passif que le gameconfig
  connaît et que la bataille n'a pas monté reste donc visible **des voisins** sur ce foyer-là. Non
  observé ici (les deux consommateurs — `SaviorProtocolsPlaybook` et les feuilles steppable/decoy —
  n'ont pas été mis en régime remplaçant côté DÉCISION).
* **La DÉCOMPOSITION par playbook (`contribs`) reste NON CONFRONTÉE** — le correctif `innerEnum` de
  #456 vit dans `frida/hooks/*` et n'est pas chargé. Ce cas s'en est passé (le tranchage se fait par
  le KIT, pas par la décomposition), mais imputer un écart à une ability précise quand le mover en
  porte **plusieurs avec playbook** l'exigerait toujours.
* **Le drive de position échoue EN SILENCE** quand la tuile est hors du movable set : `applyAction`
  rend `ok`. Mesuré — 1 move sur 4 sans effet, et le montage d'élévation qui en dépendait rendait
  « branche non atteinte ». Le probe **relit la position** depuis ; les autres appelants d'`applyAction
  move` ne le font pas.
* **Une tuile dont les six accès franchissent `|Δelev| ≥ 2` est inaccessible au MOUVEMENT** — donc
  toute paire à fort dénivelé n'est pas exploitable. Sur les 779 boards : **762** ont une élévation
  variable, **685** une paire adjacente `|Δ| ≥ 2`, mais seulement **629** une telle paire dont les
  DEUX tuiles sont accessibles. C'est ce filtre qui a fait échouer le premier montage.
* **Le régime SPAWN** (`case.unit == null`) de la feuille : inchangé, toujours court-circuité par
  `is_spawning` (case-205).

## 7. Re-dériver

```
python scripts/python/probe_456r1_move_kit_vs_playbook.py --state-file <ABSOLU>
python scripts/python/probe_456r1_move_kit_vs_playbook.py --state-file <ABSOLU> --no-bind
python scripts/python/probe_456r1_move_kit_vs_playbook.py --state-file <ABSOLU> --drop-playbook 1145
python scripts/python/probe_456r1_move_kit_vs_playbook.py --state-file <ABSOLU> --board C1_35 \
       --seed 31337 --no-graft --moves "tauCrisis:1,5;tauDarkstrider:0,3"
python -m pytest tests/engine/test_456r1_serene_unifier_and_kit_offline.py -q
```
