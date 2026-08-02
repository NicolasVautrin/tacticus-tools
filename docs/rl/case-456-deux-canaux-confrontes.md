# #456 — les deux capteurs de la fenêtre #4, confrontés sur une branche NON dégénérée

**Question binaire** : ces deux canaux TRANSPORTENT-ils une valeur, ou se contentent-ils
d'exister ?

**Réponse, par canal** :

| canal | verdict |
|---|---|
| `#436-r1` — le lien BONDÉ | **CONFRONTÉ, FERMÉ.** `bondedEntityId` non nul et JUSTE, port hydraté en accord avec le natif, et le contrefactuel prend la dégradation permissive en flagrant délit. |
| `#443-r1a` — l'attribution du terme MOVE | **CONFRONTÉ pour l'ATTRIBUTION et pour la VALEUR** — et la valeur **TROUVE UN ÉCART** : le port rend `0.0` partout où le natif produit de la valeur. **NON CONFRONTÉ pour la DÉCOMPOSITION** — le capteur porte un faux silencieux, corrigé ici, non chargé : fenêtre de reinject requise. |

Le point de départ est la mesure de l'orchestrateur : la fenêtre a été jouée (session Frida **10**,
build `rnca9r7q6c`), les deux capteurs répondent — mais les 36 effets rendaient
`bondedEntityId: null` et le buffer MOVE était vide. Un canal MUET et un canal ABSENT se
ressemblent ; prouver qu'un champ EXISTE ne prouve pas qu'il TRANSPORTE.

---

## 1. `#436-r1` — le lien BONDÉ transporte, et la valeur est la bonne

Montage : `probe_436r1_bond_channel.py`, `MC1_67`/777, runner isolé. `tyranTyrantGuard` amené au
contact, `CrushingClaws` (1105) casté **EN LIVE** — c'est ce qui distingue ce probe de #436, qui
posait le taunt offline et ne pouvait donc rien dire du canal de capture.

| étage | mesure |
|---|---|
| E0 canal | 7/7 entrées d'effet portent `bondMeasured`, **zéro** `false` |
| E1 cast | `CrushingClaws(u85 -> u79)` `ok=True` |
| E2 lien | effet **27** de u79 -> `bondedEntityId = u85` — **NON NUL, et c'est bien le TAUNTANT** |
| E3 seed | `load_state(...)` puis `get_only_targets(u79) = [85]` |

⚠ Le piège nommé (#378) est écarté par construction : `ChildComponent.ParentId` est AUSSI un
`BEntityId` int32 à `+0x10` dans une classe de 24 octets. Ici la valeur lue est portée par
l'entité-**EFFET** et vaut le **CASTER**, pas le parent d'une unité — et le probe refuse
explicitement `bondedEntityId == source` comme preuve (chez les quatre producteurs lus les deux
coïncident, ce qui rendrait une confusion invisible).

## 2. L'HYDRATATION — le gate mord, et c'est bien LE CANAL qui l'arme

`get_only_targets` non vide prouve que l'ENTRÉE de la règle est peuplée. Ce n'est pas la même
question que « le port refuse ce que le natif refuse » : entre les deux il y a toute la cascade de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, et le port pourrait refuser
**pour une autre raison** (portée, camp, cible morte) en rendant un accord trompeur.

Étage E4, neuf : le verdict du natif (`abilityReason`, ability **69** du TAUNTÉ) confronté cible par
cible à `get_invalid_target_reason` sur l'état **HYDRATÉ** — jamais muté par le port, le taunt n'y
étant arrivé que par `load_state`. Avec son **CONTREFACTUEL** : le même `decisionView` privé de
`bondMeasured`, c'est-à-dire littéralement ce que rendait le hook d'avant #496.

| cible | natif | port hydraté | port SANS canal |
|---|---|---|---|
| u77 / u79 / u81 / u83 `necroWarden` | `0x4000` | `0x4000` | `0x4000` |
| u85 `tyranTyrantGuard` (le tauntant) | `0x0` | `0x0` | `0x0` |
| **u87 `ultraCalgar`** | **`0x800000`** | **`0x800000`** | **`0x0`** |

La dernière ligne EST la mesure : accord parfait natif/port sur les 6 cibles, un refus
`TargetIsAllowedForCaster`, une acceptation, **et une ligne que le port sans canal ACCEPTAIT**.
La dégradation PERMISSIVE de #436-r1 est prise en flagrant délit et fermée.

`ultraCalgar` est amené à **d=1** du tauntée, et c'est load-bearing : à d≥2, `necroWarden` (ranged
r3, clampé en mêlée par `forceMeleeTarget` dès qu'il est adjacent à un ennemi) serait déjà refusé
pour PORTÉE avant tout taunt — la ligne resterait un refus, mais le contrefactuel ne montrerait
plus rien.

Le repli sur `eff.source` reste **refusé** (déduction, pas lecture ; dégradation RESTRICTIVE).

## 3. `#443-r1a` — le canal MOVE transporte ; sa DÉCOMPOSITION, non

### 3.1 Quel déclencheur fait firer le hook — mesuré

C'était l'inconnue que la fenêtre devait lever en premier (#443-r1 avait mesuré qu'`aiStepDryRun` ne
faisait firer aucun hook RVA).

| déclencheur | events |
|---|---|
| `decisionView(allAbilities, maxRank=32)` | **0** |
| `aiMovableTiles(friendly)` | **0** |
| **`aiDryRunAllUnits`** | **102** |

Le sweep de mouvement n'est parcouru que par un **TOUR D'IA**, jamais par une vue de décision.

### 3.2 L'ATTRIBUTION est exacte — et le critère qui la jugeait était faux

Premier jet : **8 events sur 102** hors des tuiles atteignables, verdict `wrong`, « signature du
faux positif de #443-r1 ». Diagnostic, mesuré :

* les 8 se ventilent en **4 unités × 2 utilities × 1 tuile** ;
* **8/8** portent EXACTEMENT la **position courante** de leur unité ;
* contrôle apparié : `aiMovableTiles` n'inclut la position courante d'**AUCUNE** des 6 unités.

Ancrage natif : `IdunBattle.AI.Utilities.UtilityMovementCase$$StaysOnTile` compare
`EntityExtensions.GetMainTile(case.Unit)` à `UnitPosition.get_MainTile(case + 0x18)` — le natif
évalue donc explicitement le fait de **RESTER SUR PLACE**, et trois playbooks lisent ce prédicat.
C'était un défaut du **CRITÈRE**, pas du capteur.

Le critère passe de l'INCLUSION à l'**IDENTITÉ d'ensemble** :

```
{tuiles attribuées à u}  ==  aiMovableTiles(u) UNION {position courante de u}
```

C'est **plus strict**, pas plus permissif : l'inclusion laissait passer un capteur qui ne rendrait
qu'une tuile sur trois. Après correction : **102 events, 4 unités distinctes, 4/4 unités en identité
STRICTE** (0 manquante, 0 en trop). Les totaux sont non nuls et discriminés par tuile (u81 : 40 sur
sa tuile courante, 20 ailleurs ; u83 : 303).

### 3.3 LA VALEUR — confrontée sans attendre la décomposition, et elle trouve un écart

La décomposition n'est **pas** requise pour confronter la valeur : le total natif est la SOMME des
contributions des triggered abilities du mover, et le port en a l'homologue exact —
`engine/utilities/tile.py::TriggeredAbilitiesUtility.evaluate` (et son jumeau NonOwner), qui boucle
sur `load_playbook(ab)` exactement comme `PlaybookDatabase$$LoadPlaybook` dans
`<EvaluateMovementInSteps>d__2$$MoveNext`. La décomposition n'est indispensable que pour **imputer**
un écart à une ability précise.

Étage E5, neuf. Trois gardes contre l'**accord dégénéré** — le vice même que ce cas ferme, transposé
sur l'axe valeur : au moins une valeur native non nulle, au moins deux valeurs natives distinctes,
puis accord partout. Sans elles, « 0 == 0 » sur 102 lignes serait un accord parfait et vide.

**Résultat : 102 lignes, 93 en accord, 9 en ÉCART — le port rend `0.0` partout où le natif produit
de la valeur** (20, 40, 101, 202, 303).

Décomposition par étage du port (jamais un scalaire global) :

| étage | u81 `tauCrisis` | u83 `tauAunShi` |
|---|---|---|
| S0 `ctx.is_spawning` | `False` | `False` |
| S1 `unit_triggered_abilities` | `[1133]` | `[1145]` |
| **S2 `load_playbook(ab)`** | **`None`** | **`None`** |
| natif / port | 40, 20, 20, 20 / **0.0** | 303, 202, 101, 101 / **0.0** |

`1133` = `CyclicIonBlaster`, `1145` = `SereneUnifier` — **absents des 15 entrées du registre MOVE**
du port. `IdunBattle.AI.Playbook.Loki.SereneUnifierPlaybook$$CalculateMovementUtilityInStepsInternal`
existe bien au décompilé ; aucun `CyclicIonBlasterPlaybook` n'y porte de nom propre.

⚠ **Ce qui n'est PAS établi, et E5 refuse de le conclure.** Deux causes restent non départagées :
(i) le playbook de ces abilities n'est pas porté ; (ii) le kit lu par le port est plus étroit que
l'`AbilitiesComponent` que le natif itère (le natif somme sur SON kit, qui peut contenir des
abilities que le canal ne publie pas — c'est exactement le vice que #419 avait mesuré sur la face
ATTACK). **Seule la DÉCOMPOSITION les sépare** — et c'est la meilleure démonstration de ce à quoi
elle sert. E5 rend donc `gap`, qui NOMME l'ability et s'arrête où la mesure s'arrête, plutôt que
`wrong`, qui enverrait chercher un bug de formule dans un chemin où rien n'est calculé.

Résidu nommé : **`#456-r1`**.

### 3.4 Le faux silencieux du capteur — la trouvaille

`triggeredMoveTraceStatus` annonçait `innerEnum` **résolu par nom**, donc hors `fallbacks` : un
succès. Il était FAUX. Le RPC `classFields`, appliqué à la state machine dont le `<>4__this` est
bien `TriggeredAbilitiesNonOwnerUtility` — c'est ce champ qui l'identifie, 39 classes du build
portant un `<EvaluateMovementInSteps>d__N` — donne la disposition RÉELLE :

| offset | nom | type |
|---|---|---|
| `0x10` | `<>1__state` | Int32 |
| `0x18` | `<>2__current` | Fix64 |
| `0x20` | **`moveCase`** | UtilityMovementCase |
| `0x28` | `<>4__this` | — |
| `0x30` | **`<evaluation>5__2`** | Fix64 |
| `0x38` | **`<>7__wrap2`** | IEnumerator\`1 |
| `0x40` | **`<triggeredAbilityUtility>5__4`** | IEnumerator\`1 |

Trois écarts avec les listes de noms devinés, dont un **faux silencieux** :

* le `case` s'appelle `moveCase` sur la jumelle NonOwner (`case` sur l'Owner) ;
* l'accumulateur s'appelle `<evaluation>5__N` — aucun des sept candidats ;
* **le seul `<>7__wrapN` de la SM est l'énumérateur EXTERNE**, l'INTERNE étant un local NOMMÉ. La
  liste `innerEnum: ["<>7__wrap2", …]` résolvait donc `innerEnum` **sur l'énumérateur EXTERNE**, au
  même offset que `outerEnum`, **sans entrer dans `fallbacks`**.

Le repli LU (`0x40`) était juste. **La résolution par nom était STRICTEMENT PIRE que pas de
résolution** — et le status l'aurait annoncée comme un succès. Seul le hasard a évité une mesure
fausse : `acc` étant, lui, en repli, `decomposable` valait `false` et `contribs` était publié `null`
plutôt qu'étiqueté du mauvais playbook.

Le décompilé tranche : dans `…d__2$$MoveNext`, `this+0x40` reçoit le retour du slot
`CalculateMovementUtilityInSteps`, sert de récepteur au `MoveNext`/`get_Current` interne, puis est
**remis à zéro** juste après `this+0x30 = op_Addition(this+0x30, it.Current)` ; `this+0x38`, lui,
reçoit le `GetEnumerator()` de la collection d'abilities et est disposé en fin de boucle.

**Le correctif** : les trois champs dérivés du source se résolvent par **STRUCTURE** — type du champ
+ convention Roslyn (`<>7__wrapN` = `foreach` implicite, `<nom>5__N` = local explicite hoisté) — avec
**unicité EXIGÉE** : zéro comme deux candidats retombent sur le repli LU et sont NOMMÉS dans
`fallbacks`. Et `classFields` de la SM est publié tel quel par `triggeredMoveTraceStatus`, pour que
le prochain build se diagnostique sans re-RE.

⚠ **NON CONFRONTÉ.** `frida-compile` rc 0 (bundle 1 092 308 o), `tsc --noEmit` 0 erreur sur le
fichier touché (les 146 restantes sont préexistantes, toutes dans `hooks/scratch/`,
`normalize-bc/debug-rpcs.ts`, `rl/tensorizer.ts`). Le bundle n'est **pas chargé** : la session 10
porte l'ancien. E3 (décomposition) et E4 (`SaviorProtocolsPlaybook`) restent donc `not-measured` /
`absent` — **fenêtre de reinject requise**, et c'est le seul reste de ce cas.

---

## 4. Fichiers

| pièce | fichier |
|---|---|
| E4 du probe BOND — gate hydraté + contrefactuel | `scripts/python/probe_436r1_bond_channel.py::check_gate`, `_strip_bond_channel` |
| critère d'attribution durci | `scripts/python/probe_443r1a_triggered_move_anchor.py::check_attribution` |
| confrontation de la VALEUR + ventilation de l'écart | `.../probe_443r1a_triggered_move_anchor.py::check_value`, `_port_rows` |
| résolution structurelle des champs de la SM | `frida/hooks/features/triggered-move-trace.ts::resolveByStructure`, `listFields` |
| gardes offline | `scripts/python/tests/engine/test_436r1_bond_channel_offline.py` (22), `.../test_443r1a_triggered_move_anchor_offline.py` (26) |

## 5. Validation

**48 gardes offline vertes** (32 avant la tranche, +16). Trois mutations adversariales, **toutes
vérifiées mordantes**, avec restauration contrôlée et re-vérifiée :

| mutant | ce qu'on retire | test qui rougit |
|---|---|---|
| m1 | l'IDENTITÉ d'ensemble (retour à l'inclusion) | `test_attribution_PARTIELLE_est_refusee` |
| m2 | le terme `UNION {position courante}` | `test_la_tuile_COURANTE_est_une_candidate_LEGITIME` |
| m3 | la condition (4) du contrefactuel de E4 | `test_gate_refuse_quand_le_CONTREFACTUEL_ne_mord_PAS` |

Le terme `UNION {position}` porte sa propre contre-épreuve **dans** la banque de tests
(`test_le_terme_POSITION_est_LOAD_BEARING`) : le même jeu d'events sans `pos_by_unit` DOIT rougir —
sans quoi rien ne dirait si l'élargissement élargit réellement quoi que ce soit.

### Ce qui n'est PAS couvert, nommé

* ~~**`#456-r1` — l'écart de valeur de E5 n'est pas FERMÉ, il est LOCALISÉ.**~~ **FERMÉ le
  2026-08-02 — `case-456-r1-terme-move-kit-et-playbook.md`.** Les deux causes mordaient, sur des
  abilities **différentes**, et elles sont additives (4 + 5 = 9) : `1145 SereneUnifier` = playbook
  non porté, `1120 SaviorProtocols` (greffée) = kit du port trop étroit. Deux rectifications de
  cette fiche : **(i)** `1133 CyclicIonBlaster` était un **faux coupable** — le `missing` de E5
  dérive du kit **PORT**, jamais confronté au kit natif, et le natif rend `0.0` pour son porteur
  (il la skippe aussi) ; **(ii)** la **DÉCOMPOSITION n'était PAS nécessaire** au tranchage — le
  discriminant est le KIT (`unitAbilityStates` contre `runner_tile_leaf_ctx`), pas la valeur.
  102/102 en accord.
* **La DÉCOMPOSITION par playbook** (`contribs`) et donc **la valeur du terme `SaviorProtocols`** :
  NON CONFRONTÉES. Le capteur corrigé n'est pas chargé — fenêtre requise. Le montage est prêt et
  discriminant (greffe 1120 sur `tauCrisis`, `aiDryRunAllUnits` identifié comme LE déclencheur).
  C'est aussi ce qui débloquera `#456-r1`.
* **La greffe de 1120 sur `tauCrisis` n'apparaît PAS** dans le kit lu par le port
  (`unit_triggered_abilities = [1133]`), et E4 rend `absent`. Non départagé : greffe non prise, ou
  canal aveugle à l'ability greffée. Même déblocage.
* **Le régime `bondMeasured = false`** n'a toujours pas été observé live : il exigerait que
  `findClassAnywhere` échoue sur `BondComponent`. Il reste exercé offline.
* **`TriggeredAbilitiesNonOwnerUtility`** fire (51 des 102 events) mais rend **0 partout** sur ce
  montage : son rôle dans le sweep n'est pas mesuré, seulement constaté non muet.
* **La voie 3 de `ForcedAttackTargets`** (`AddForcedAttackTargetBehaviour`, 23 porteurs summons
  Tyranides) reste non portée — écart déjà nommé par #436, inchangé.
* Le contrefactuel de E4 coupe le canal sur **un** effet 27 ; un état portant PLUSIEURS effets
  bondés simultanés n'a pas été monté.

## 6. Re-dériver

```
python scripts/python/probe_436r1_bond_channel.py
python scripts/python/probe_443r1a_triggered_move_anchor.py --state-file <ABSOLU>
python -m pytest tests/engine/test_436r1_bond_channel_offline.py \
                 tests/engine/test_443r1a_triggered_move_anchor_offline.py -q
```
