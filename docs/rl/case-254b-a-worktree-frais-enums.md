# case-254b-a — Un worktree frais ne savait pas décoder un compte rendu d'`applyAction`

> **Verdict** : `stream_events` lisait ses ordinaux dans un artefact **gitignoré**. La source est
> désormais la table **versionnée** `data/symbols/<CURRENT>/frida/enums.tsv`. L'invariant 3 du
> `CLAUDE.md` (« un worktree frais est RUNNABLE par son seul checkout ») était **faux sur ce
> chemin** ; il est rendu **vrai**, pas amendé.

## 1. Le symptôme, et pourquoi il mentait deux fois

Dans un worktree créé à l'instant depuis `origin/master`, la première commande de pilotage
échouait :

```
$ python rl_duel.py act move --unit 87 --to 2,0 --state-file <abs>
  File ".../rl_duel.py", line 716, in cmd_act
    _print_apply(label, r, my_ids)
  File ".../rl_probe_step.py", line 88, in _print_apply
    an = stream_events.analyze(evs, my_ids)
  File ".../stream_events.py", line 195, in analyze
    if step == step_id("UnitDamaged"):
KeyError: 'StepType.UnitDamaged absent de enums.json (build courant) -- le pas a-t-il ete
           renomme ou retire ? Re-verifier contre data/symbols/<build>/frida/enums.tsv.'
```

**Premier mensonge — la cause.** Le message accuse une **renumérotation d'enum**, ce qui envoie
lire `data/symbols`, differ deux builds, chercher une migration. La cause réelle est un **fichier
absent**.

**Second mensonge — l'état.** La levée vient du **DÉCODAGE de la réponse**, `rl_duel.py:716`,
c'est-à-dire **après** le RPC `applyAction` de la ligne 714. Mesure faite dans le worktree frais,
sur le même runner, juste après l'échec :

| | avant `act` | après l'« échec » |
|---|---|---|
| position de `u87` | `(1,0)` | **`(2,0)`** — l'action a été appliquée |
| `action_log` du state-file | `null` | **`null`** — l'append + `_save_state` (l. 722-731) n'ont jamais été atteints |

Un appelant qui lit « erreur » et retente **joue l'action deux fois**. Et la trajectoire du dataset
IL perd l'action, alors que le runner, lui, l'a jouée.

## 2. La cause, re-dérivée par la lecture du code

`stream_events._enums()` faisait `(<repo>/frida/data/meta).glob("*/enums.json")` et prenait la
version la plus haute. Ce fichier est écrit par le HOST à l'inject —
`frida/host/meta-sync.ts::syncEnums`, RPC `dumpEnums` (`frida/hooks/features/introspect.ts`,
liste `DEFAULT_ENUMS`). Or :

```
$ git check-ignore -v frida/data/meta/1.41.128/enums.json
.gitignore:24:frida/data/	frida/data/meta/1.41.128/enums.json
```

`frida/data/` est **gitignoré** ⇒ absent de tout worktree frais ⇒ `_enums()` rendait `{}` ⇒
`step_id` levait. Aucun `data/` versionné n'était en cause, aucune migration de build non plus.

## 3. L'arbitrage — mesuré, pas préféré

Deux voies étaient ouvertes.

**(b) régénérer à la volée** par le RPC `dumpEnums`. **Refusée.** Elle fait dépendre le
**décodage d'un compte rendu** — opération purement locale — d'un host vivant : « host éteint »
devient un second mode de panne du même chemin. Et l'artefact produit reste **non gardé** : pas
d'estampille, indexé par **version de jeu** (`1.41.128`) et non par **hash de build**, choisi par
un simple tri de version. Une table périmée y ment en silence — exactement le motif #251/#252 que
l'on cherchait à éviter.

**(a) lire un artefact versionné.** **Retenue** — et elle ne demande **aucun fichier nouveau** :
la table existe déjà, c'est `data/symbols/<CURRENT>/frida/enums.tsv`, produite par
`preprocess_il2cpp_dump.py`, lue par le même chemin que `catalog_inject.enum_map`.

Trois mesures la justifient (re-jouables : `probe_269_stream_events_source.py`).

| mesure | résultat |
|---|---|
| **équivalence** `enums.tsv` (`rnca9r7q6c`) ↔ `frida/data/meta/1.41.128/enums.json` | `StepType` **62/62**, `GroupType` **104/104**, **0** ordinal divergent, 0 membre en trop/en moins des deux côtés |
| la table versionnée est-elle présente dans un worktree frais ? | **oui** (`git check-ignore` → non ignoré) |
| **contre-épreuve** — la même comparaison contre l'archive `gqfc5mff6c` | **55 ordinaux divergents**, `RestoreArmorInfo` en trop : lire la MAUVAISE table est exactement la panne #254bis. C'est `data/symbols/CURRENT` qui l'empêche. |

Changer de source ne change donc **aucune valeur décodée** aujourd'hui.

**Le coût accepté** : la table doit être re-dérivée à chaque changement de build. Ce coût est
**déjà payé** — tout le dépôt en dépend (`catalog_inject.enum_map`, `targeting_rule.py`,
`active_ability_type.py`, `unit_faction.py`, …) — et surtout il est **GARDÉ** :
`enums.tsv` porte `#!il2cpp-provenance sha256=… build=…` et l'**axe 1** de
`scripts/python/symbols_sync.py` compare ce sha256 au `GameAssembly.dll` **installé**, fail-closed.
Une péremption y est **détectable** ; sur l'artefact host, elle ne l'était pas du tout.

## 4. Ce qui a changé

* **`scripts/python/stream_events.py`** — source = `data/symbols/<CURRENT>/frida/enums.tsv` via
  `symbols_layout.build_dir()`, enums cités par leur nom **pleinement qualifié**
  (`IdunBattle.Streams.StepType` / `…GroupType`). Nouvelle exception `EnumTableUnavailable` :
  table absente ⇒ message qui **NOMME le fichier** et **la commande qui le régénère**
  (`dump_il2cpp.py` → `preprocess_il2cpp_dump.py`, garde `symbols_sync.py`). Un **membre**
  disparu garde son `KeyError` — deux causes, deux messages, jamais le même.
  Les chemins sont rendus en `as_posix()` : `str(KeyError)` passe par `repr`, qui **double les
  antislashs** d'un chemin Windows et le rend illisible.
* **`scripts/python/rl_probe_step.py`** — `_print_apply` **ne propage plus**. C'est de
  l'AFFICHAGE : il imprime le diff d'état (la preuve que l'action a porté), rend la panne de
  décodage à son appelant, et ne l'annule pas.
* **`scripts/python/rl_duel.py`** — `cmd_act` / `cmd_play` récupèrent cette panne **après** avoir
  sauvegardé l'état, l'affichent avec « L'ACTION A DEJA ETE APPLIQUEE … NE PAS LA REJOUER », et
  `cmd_act` rend **rc 3**. L'échec est **rendu**, jamais avalé — mais il ne fabrique plus le
  double-play. Idem `_ability_had_real_effect` : un décodage impossible n'est pas « l'ability a
  raté » (ce verdict-là faisait sauter l'append `action_log`).

## 5. Validation

**La preuve demandée — worktree créé à l'instant, même runner, même seed.**

| tranche | commande | résultat |
|---|---|---|
| **AVANT** — worktree neuf sur `origin/master` (`27bab5d5`) | `act move --unit 87 --to 2,0` | `KeyError: StepType.UnitDamaged`, **rc 1** ; `u87 (1,0) -> (2,0)` **appliqué** ; `action_log` **null** |
| **APRÈS** — worktree d'agent, `frida/data` absent | `act move --unit 89 --to 1,0` | cascade **décodée** (`User_MoveUnit`, `ChangePosition`, `ReceiveEffect`, `ChangeStats`, `LoseEffect`, `Effect_Refresh`), **rc 0**, `action_log` = `{"kind":"move","unitId":89,…}` |

**Gardes et mesures**

| mesure | résultat |
|---|---|
| `python stream_events.py` (smoke du module, worktree frais) | `StepType(62) GroupType(104) ; UnitDamaged=4 RemoveUnit=11 ReceiveEffect=15` |
| `pytest tests/test_stream_events_offline.py` (garde neuve, offline) | **16 passed** |
| `probe_269 --state-file <abs>` étape 0 (source) | source `data/symbols/rnca9r7q6c/frida/enums.tsv`, **non gitignorée** |
| `probe_269` étape 1 (équivalence host) | **0 divergence** sur `StepType` et `GroupType` |
| `probe_269` étape 2 (décodage vs BRUT, tour IA réel, 389 events) | `UnitDamaged` 6/6, `RemoveUnit` 1/1, `ReceiveEffect` 33/33 ; **0** ordinal sans nom |

L'étape 2 est **discriminante**, pas décorative : sur cette même cascade les pas **voisins** que
les anciens littéraux désignaient sont massivement peuplés — **28 `ChangeStats`** et
**31 `LoseEffect`**. Sous le code d'avant `da556fbb`, `deaths` aurait rapporté **28** au lieu de
**1** et `effects` **31** au lieu de **33**. La contamination mesurée est aujourd'hui **nulle**.

## 6. Ce qui n'est PAS couvert

* **Les deux autres défauts du billet `#254b-a` étaient déjà fermés** par `da556fbb`
  (`analyze()` par nom, `step_name` inversé). Ce cas ne ferme que le troisième — l'infrastructure —
  qui était précisément celui qui rendait les deux premiers **invisibles** en worktree.
* **`#254b-b` reste ouvert** : `probe_202c_tutelaries.py` filtre encore `step == 10/13/14/16/30`,
  cinq littéraux décalés de −1. Le correctif est le même geste (`SE.step_id("<Nom>")`) mais il
  touche un autre fichier et n'a pas été rejoué ici.
* **Un autre gitignoré est LU, et il n'est pas traité ici** : `frida/data/ai-traces`
  (`engine_agreement_stages.py`, `probe_32_casttile.py`, `probe_49g_l3tiles.py`,
  `diag_summoner_crash.py`). Le host écrit ces traces dans l'arbre **principal** ; un worktree
  résout `ROOT/frida/data/ai-traces` sur **son** arbre, donc vide. Balayage complet des chemins
  construits depuis `ROOT`/`REPO` dans `scripts/python/**` : **134** chemins, **111** gitignorés —
  mais 105 d'entre eux sont des **SORTIES** sous `logs/` (state-files, dumps), conformes à
  l'invariant 3. Les seules **ENTRÉES** gitignorées restantes sont `frida/data/ai-traces`,
  `frida/data/rl-batches`, `frida/assets/{public,raw}` (outillage d'assets) et `.env`.
* **L'estampille de provenance n'est pas vérifiée à chaque décodage** : `stream_events` ne
  calcule pas le sha256 d'un DLL de 60 Mo à l'import. C'est le rôle de `symbols_sync.py`, à jouer
  au changement de build.
