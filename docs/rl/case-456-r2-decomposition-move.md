# #456-r2 — la DÉCOMPOSITION du terme MOVE, confrontée ; et deux gardes qui ne pouvaient pas rougir

**Question binaire** : le canal `contribs` du capteur `#443-r1a` TRANSPORTE-t-il une décomposition
par playbook, et cette décomposition est-elle JUSTE ?

**Réponse** : **oui, et elle l'est — mais le probe qui devait l'établir ne pouvait pas le dire.**
Deux de ses étages étaient structurellement incapables de rougir, et le vert qu'il rendait était
obtenu sur un régime dégénéré. Les deux sont fermés ici, avec leur contre-épreuve.

| ce qui est confronté | verdict |
|---|---|
| la DÉCOMPOSITION (E3) — le seul reste nommé de #456 | **CONFRONTÉE, FERMÉE.** 100/100 events décomposés, `sum(contribs) == total` partout, et **4 events où DEUX playbooks distincts se partagent le total**. |
| le lien BONDÉ (#436-r1) | **RE-CONFRONTÉ** sur la session du jour, inchangé : `bondedEntityId = u85` non nul, hydratation `get_only_targets(u79) = [85]`, gate 6/6, contrefactuel mordant. |
| l'étage E0 du probe MOVE | **DÉFAUT TROUVÉ ET FERMÉ.** Il interrogeait le canal AVANT l'armement : verdict structurellement vide, message faux, `fallbacks` jamais lus, et aucun chemin vers un rc non nul. |
| le régime de E3 | **DÉFAUT TROUVÉ ET FERMÉ.** Mesuré dégénéré : 0 event à deux contributions sur 102. |

---

## 1. La fenêtre attendue par #456 a EU LIEU — mesuré, pas supposé

`case-456-deux-canaux-confrontes.md` §3.4 livrait la résolution structurelle des champs de la state
machine **non chargée** (« fenêtre de reinject requise »). Elle l'est aujourd'hui :

| ce qui est mesuré | valeur |
|---|---|
| session Frida | id **2**, pid 52708, `running`, démarrée **2026-08-03T22:47:52Z** |
| bundle chargé | `frida/dist/hooks.js`, **1 092 308 o**, mtime **2026-08-02 10:42:23** |
| `resolveByStructure` / `:ambiguous(` dans le bundle | **5** / **1** occurrences |

Ces deux littéraux n'existent **que** dans le correctif de #456 §3.4 — c'est le discriminant, et il
ne demande aucun armement. La taille du bundle est celle que §3.4 citait pour son propre build.

**Le correctif MORD, et la mesure le prouve doublement.** `triggeredMoveTraceStatus`, interrogé
APRÈS armement, rend `fallbacks: []` sur les **trois** blocs et la disposition RÉELLE :

| bloc | `caseArg` | `acc` | `outerEnum` | `innerEnum` |
|---|---|---|---|---|
| `TriggeredAbilitiesUtility` | `case` @32 | `<evaluation>5__2` @48 | `<>7__wrap2` @56 | `<triggeredAbilityUtility>5__4` @**64** |
| `TriggeredAbilitiesNonOwnerUtility` | **`moveCase`** @32 | `<evaluation>5__2` @48 | `<>7__wrap2` @56 | `<triggeredAbilityUtility>5__4` @**64** |

`innerEnum` résout à **64**, `outerEnum` à **56**. L'ancienne résolution par nom cherchait
`<>7__wrap2` pour `innerEnum` — elle aurait donc rendu **56**, et étiqueté chaque contribution du
nom de l'énumérateur EXTERNE au lieu du playbook. Les étiquettes observées
(`SaviorProtocolsPlaybook.<CalculateMovementUtilityInStepsInternal>d__4`) sont la preuve directe
que le repli LU était juste et que la résolution par nom était strictement pire.

## 2. E3 — la décomposition, et le régime qui la rendait creuse

### 2.1 Le montage de référence était DÉGÉNÉRÉ (mesuré)

Le probe rendait `E3 [ok] 102/102 event(s) decomposes, sum(contribs) == total partout`. Distribution
réelle des contributions sur ce montage (1120 greffée sur `tauCrisis`, `replace=True`) :

```
events=102   nb_contribs = {1: 9, 0: 93}     events a >=2 contributions : 0
```

**Zéro.** À un seul terme, `sum(contribs) == total` n'est que `contrib == total` : la contrainte
vérifie le décodage de l'accumulateur, mais **jamais** que le canal SÉPARE deux abilities — la
seule chose qu'il apporte sur `ai-trace` L3, qui donne déjà le total. C'est le vice de tout ce cas
(« un canal muet et un canal absent se ressemblent ») transposé sur l'axe décomposition.

### 2.2 Le régime utile, atteint et mesuré

Greffer 1120 **en plus** sur `tauAunShi` avec `replace=False` — il GARDE `1145 SereneUnifier` —
met deux playbooks sur le même mover. `replace=False` est load-bearing : avec `replace=True` la
greffe remplace `PassiveAbilities` et l'on retombe à une contribution par event.

| unité | tuile | total natif | décomposition |
|---|---|---|---|
| u83 | (0,0) | **323** | SaviorProtocols **20** + SereneUnifier **303** |
| u83 | (1,2) | **222** | 20 + 202 |
| u83 | (2,1) | **121** | 20 + 101 |
| u83 | (2,0) | **242** | 40 + 202 |

Les termes sont cohérents avec les deux modèles portés indépendamment (`SereneUnifier` =
`101 x |voisins amis|`, `SaviorProtocols` = `+20` par voisin retenu) — deux lectures qui ne
partagent aucun code avec le décodeur d'accumulateur.

E3 exige désormais **au moins un event à deux ÉTIQUETTES DISTINCTES**. Le critère porte sur les
étiquettes et non sur un compte : deux deltas portant le même playbook prouveraient plutôt que
l'accumulateur a été lu deux fois.

## 3. E0 — un étage de diagnostic dont le verdict était vide

`install()` n'est appelé que par `triggeredMoveTraceOn`. Le probe interrogeait
`triggeredMoveTraceStatus` **avant** tout montage, donc sur `installed: {}` et `resolved: {}`.
Trois conséquences, toutes mesurées :

1. **Message FAUX** — il imprimait, à chaque exécution :
   `capteur CHARGE mais AUCUN hook pose : {}. La resolution runtime a echoue (classe utility, state
   machine nested ou MoveNext introuvable)`. Rien n'avait échoué : rien n'avait été tenté.
2. **Les `fallbacks` n'étaient JAMAIS lus.** `check_channel` sait les extraire — mais `resolved`
   est vide à cet instant. Or les `fallbacks` sont exactement le canal d'auto-vérification que
   #456 §3.4 a créé après y avoir trouvé un faux silencieux.
3. **Aucun chemin vers un rc non nul.** E0 n'entrait pas dans `verdicts` ; seul `not_reinjected`
   sortait (rc 7). Un capteur posé sur des offsets de repli aurait rendu `VERDICT: OK`.

Fermé en deux temps : `check_presence` (E0a, avant montage — la seule question posable : le RPC
existe-t-il ?) et `check_channel` (E0b, après armement, **dans `verdicts`**). Et un repli n'est
plus vert : statut `degraded`. E3 n'attrape que les replis `acc`/`innerEnum` via `contribs: null` ;
`caseArg`, `state`, `current` et les offsets du `UtilityMovementCase` passaient inaperçus.

## 4. `#443-r1b` n'est plus inerte — le régime réputé inatteignable, atteint

Le montage double fait rougir l'attribution : u83 perd **exactement une tuile**, `(0,3)`, sur les
**deux** utilities (11 → 10 tuiles, 102 → 100 events), pendant que u81 garde ses 12/12.
**Reproductible à l'identique sur deux passes.**

Ce n'est pas un défaut du capteur. `case-443-r1` §5 : le corps de
`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook$$FilterMovementTiles` ouvre sur
`if (UnitExtensions.HasRangedWeapon(unit)) return;` — court-circuit total — et le résidu `#443-r1b`
était classé INERTE parce que « le régime *porteur sans arme à distance* n'est atteint par aucun
porteur connu ». `tauAunShi` est un héros de **mêlée** : la greffe l'atteint. `tauCrisis`, ranged,
court-circuite — d'où l'asymétrie, qui est elle-même la contre-épreuve.

⚠ **Le CRITÈRE du filtre reste NON TRANCHÉ.** La prédiction de `case-443-r1` §5 (garder les tuiles
ayant un protégeable dans le rayon rendu par le slot `0x77`, `range = 2`) a été **testée et ne
sépare pas** : `(0,3)` (écartée) et `(1,3)` (gardée) ont toutes deux `ultraTitus` à d=2 en
adjacence. Le rayon natif est peut-être géométrique et non connectif, ou « protégeable valide »
porte une condition de plus. Résidu **`#456-r2-r1`**.

Conséquence de conception : **le probe joue DEUX montages**, chaque étage jugé là où son critère
est valide — MONO (filtre inerte) pour E1/E2/E5, DOUBLE pour E3/E4. L'attribution est **re-mesurée
et imprimée** sur le montage double, en information : l'écart reste visible et chiffré, jamais tu.
Exiger l'identité là ferait rougir un capteur juste sur un comportement natif correct.

## 5. Mesures, avant / après

| | avant (2026-08-02) | après (2026-08-04) |
|---|---|---|
| E3 décomposition | `not-measured` — capteur non chargé | **100/100 décomposés, 4 events à 2 playbooks** |
| E4 `SaviorProtocolsPlaybook` | `absent` | **4 contributions attribuées à u81** |
| replis de résolution | inconnus | **`fallbacks: []` sur les 3 blocs** |
| E5 valeur | 102 lignes, accord partout (#456-r1) | **102 lignes, accord partout**, 6 valeurs distinctes |
| E2 attribution (MONO) | 4/4 identité stricte | **4/4 identité stricte** |
| gardes offline | 48 | **54** |

## 6. Fichiers

| pièce | fichier |
|---|---|
| E0 en deux temps + garde anti-dégénérescence | `scripts/python/probe_443r1a_triggered_move_anchor.py::check_presence`, `check_channel`, `check_decomposition` |
| les deux montages | `.../probe_443r1a_triggered_move_anchor.py::MONO_SPECS`, `DOUBLE_SPECS`, `_collect` |
| gardes offline | `scripts/python/tests/engine/test_443r1a_triggered_move_anchor_offline.py` (+6) |

## 7. Validation

**54 gardes offline vertes.** Quatre mutations adversariales, **toutes vérifiées mordantes**, patch
confirmé appliqué et restauration re-vérifiée :

| mutant | ce qu'on retire | test qui rougit |
|---|---|---|
| m1 | la garde anti-dégénérescence de E3 | `test_une_SEULE_ability_contributrice_est_un_regime_DEGENERE` |
| m2 | le non-vert sur un repli (`degraded` → `measured`) | `test_les_REPLIS_d_offset_sont_DITS_pas_tus` |
| m3 | le critère par ÉTIQUETTES (→ compte de contributions) | `test_deux_contributions_du_MEME_playbook_ne_LEVENT_pas_la_degenerescence` |
| m4 | E0a rendu à son ancien comportement | `test_presence_NE_CONCLUT_RIEN_des_hooks_non_encore_poses` |

m4 rejoue verbatim le faux rouge d'origine : `assert 'not-installed' == 'present'`, avec le message
`capteur CHARGE mais AUCUN hook pose : {}. La resolution runtime a echoue`.

### Ce qui n'est PAS couvert, nommé

* **`#456-r2-r1` — le critère de `SaviorProtocolsPlaybook$$FilterMovementTiles`.** Son EFFET est
  mesuré (une tuile retirée, reproductible, asymétrie ranged/mêlée) ; son CRITÈRE ne l'est pas —
  le rayon 2 en adjacence ne sépare pas `(0,3)` de `(1,3)`. Ancrage : le slot `0x77` appelé par
  ce corps, signature `(from, range = 2, includeCenter = 0)`, non tranché faute d'un second
  call-site nommé. Le filtre lui-même reste **non porté** (`#443-r1b`).
* **La valeur de `SaviorProtocols` change entre les deux montages** pour u81 (40 → 20 sur la même
  tuile). Le port SUIT le natif dans les deux cas (E5 en accord 102/102 et 100/100), donc ce n'est
  pas un écart de portage — mais la cause n'a pas été investiguée.
* **Le régime `bondMeasured = false`** n'a toujours pas été observé live (il exigerait que
  `findClassAnywhere` échoue sur `BondComponent`). Exercé offline seulement.
* **`TriggeredAbilitiesNonOwnerUtility`** fire (la moitié des events) mais rend 0 partout sur ces
  montages : son rôle dans le sweep reste constaté non muet, pas mesuré.
* **La voie 3 de `ForcedAttackTargets`** (`AddForcedAttackTargetBehaviour`) reste non portée —
  écart déjà nommé par #436, inchangé.

## 8. Re-dériver

```
python scripts/python/probe_443r1a_triggered_move_anchor.py --state-file <ABSOLU>
python scripts/python/probe_436r1_bond_channel.py
python -m pytest tests/engine/test_443r1a_triggered_move_anchor_offline.py \
                 tests/engine/test_436r1_bond_channel_offline.py -q
```
