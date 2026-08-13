# #934 / #941-r1 / #941-r3 / #962-r1 / #943-r1 / #933-r1 — le parc des rouges offline, RE-MESURÉ

Six résidus dispatchés ensemble sur le thème « tests rouges de `master` que personne ne voit ».
La première action a été une **mesure**, pas une réparation — et elle a périmé l'essentiel de ce
que les fiches annonçaient.

## 1. La mesure : passe COMPLÈTE du périmètre offline, sur `28429702`

Périmètre dérivé (`git ls-files scripts/python/tests` moins `_live.py`) = **372 fichiers**, joués
en 8 shards parallèles (`pytest -q --tb=no`, 42 min de mur, le shard le plus long).

**25 tests rouges dans 19 fichiers.**

L'isolement a été fait sur un **worktree témoin détaché**, propre, au même commit
(`git worktree add --detach <tmp> 28429702`) : **24 des 25 y sont reproduits à l'identique**. Le
25e (`test_463r1_ecart_empreinte_offline.py`) n'a pas été re-confronté — son cliquet est suspendu
par consigne. Aucun rouge n'était donc un artefact de l'arbre de travail.

| fichier | rouges | nommé par |
|---|---|---|
| `tests/engine/runner/test_448_r2b_stormboyz_teleporting_in_offline.py` | 1 | — |
| `tests/engine/runner/test_statmod_captured_channel_offline.py` | 1 | **#934** |
| `tests/engine/test_270r4r2_cycles_imports_offline.py` | 1 | #941-r1 |
| `tests/engine/test_270r4r2r2_differes_offline.py` | 2 | — |
| `tests/engine/test_270r4r2r2r3_gardes_du_hissage_offline.py` | 1 | #941-r1 |
| `tests/engine/test_359r5_selector_only_event_order_offline.py` | 2 | — |
| `tests/engine/test_477r24r1_slots_interface_offline.py` | 2 | #941-r1, **#962-r1** |
| `tests/engine/test_477r25_slots_autres_interfaces_offline.py` | 1 | — |
| `tests/engine/test_498r4_face_decision_is_displaceable_offline.py` | 1 | — |
| `tests/engine/test_566r1_sure_kill_gate_offline.py` | 1 | — |
| `tests/engine/test_603_index_foyers_offline.py` | 2 | #941-r1 |
| `tests/engine/test_nc_priority_tiers_offline.py` | 2 | — |
| `tests/test_366_r1_bcpatch_port_blindspot_offline.py` | 1 | — |
| `tests/test_431_build_pin_offline.py` | 2 | — |
| `tests/test_463r1_ecart_empreinte_offline.py` | 1 | — |
| `tests/test_464_sibling_script_offline.py` | 1 | — |
| `tests/test_480r8_rpc_joignable_offline.py` | 1 | — |
| `tests/test_additional_hits_variant_signatures_offline.py` | 1 | — |
| `tests/test_enum_ordinal_ratchet_offline.py` | 1 | — |

### Ce que le recoupement #934 ↔ #941-r1 donne, et il n'est pas celui qu'on attendait

Les deux fiches ne recouvrent pas le même gisement : **elles sont toutes deux largement périmées.**

* **#934 nommait 7 fichiers (10 échecs). Il en reste UN rouge** — `test_statmod_captured_channel`.
  Les six autres (`test_287r14_get_actual_target`, `test_287r14r1_resolution_tile_target`,
  `test_421_effect_active_gate`, `test_camo_seed_inventory`,
  `test_refresh_active_flag_discriminant`, `test_270r1_volet2_dict_keys_enum`) sont **VERTS**.
* **#941-r1 nommait 9 fichiers. Il en reste QUATRE** (`test_477r24r1`, `test_603_index_foyers`,
  `test_270r4r2_cycles_imports`, `test_270r4r2r2r3_gardes_du_hissage`). Cinq sont verts.
* **Onze fichiers rouges ne sont nommés par AUCUNE des deux fiches** — soit 58 % du parc.

Autrement dit : la ventilation héritée aurait envoyé réparer douze fichiers déjà verts et laissé
onze rouges hors champ. Le parc se **re-mesure**, il ne se cite pas.

## 2. Le vrai mécanisme de l'invisibilité — et ce n'est pas « 50 trous »

#934 accusait les **trous du ledger** (`scripts/ratchets-457-vert-offline.json`) : un fichier sans
entrée est indiscernable d'un vert. C'est vrai, et le compte est **50 fichiers sans entrée** sur
372. Mais confronter les 19 fichiers rouges au ledger donne autre chose :

```
15 rouges portent une entree VERT au ledger
 3 rouges n'ont AUCUNE entree
 1 rouge porte une entree ROUGE  (test_477r24r1, celui que #962-r1 declarait)
```

**Et pourtant `probe_547` rend `PASS`.** La raison est son tri-état, qui fonctionne : aucune de ces
15 attestations n'est *valable sur cet arbre*. Le probe le dit lui-même, chiffres du 2026-08-13 :

```
entrees attestees : 322 | perimetre offline derive : 372
attestations VALABLES sur CET arbre : 0 / 372
PAS MESURE ICI (vert d'un AUTRE arbre) : 371 -- ni vert ni rouge, un TROU
   une dependance MESUREE a change depuis 6679e202   169
   une dependance MESUREE a change depuis 15fc2a4c   124
   aucune attestation                                 50
   le fichier de test a CHANGE depuis l'attestation   16
   une dependance MESUREE a change depuis 0d6283b6    12
```

⚠ **`probe_547` ne peut se prononcer sur AUCUN fichier du dépôt, et rend `PASS`.** Son verdict
repose alors sur la seule entrée qu'il sait lire. Le mécanisme d'invisibilité n'est donc pas « 50
trous » mais **371 sur 372**, et le cliquet que #934 (b) proposait — borner le nombre de trous, qui
« ne peut que décroître » — serait immédiatement à son maximum : il ne mordrait jamais.

Ce n'est **pas** un défaut d'implémentation : `test_547_ledger_sans_verdict_non_vert_offline.py::
test_un_vert_PERIME_ne_compte_PAS_comme_une_attestation` écrit noir sur blanc que « le cliquet peut
rendre `PASS` avec ZERO attestation valable ; ce qui est interdit, c'est qu'il le TAISE ». C'est un
arbitrage explicite de #547-r2, gardé par un test. **Le renverser n'est pas du ressort d'une
tranche qui le découvre** — résidu **#934-r3**.

## 3. Les cinq réparations livrées

### #962-r1 — la citation de slot d'`AtomicGroupOperation$$Execute` (RÉSOLU, issue (a))

Le résidu tenait pour indécidable ce que `slot 10` désigne, et interdisait de deviner. Il n'y avait
rien à deviner : les trois slots du groupe atomique sont ceux de **`Core.Services.IMatchState`**,
pas d'`IBattleQuery`, et ils sont LUS dans l'entrée versionnée
`data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` :

```
IMatchState  10  TryDequeueBattleEvent        # « puis DEPILE »
IMatchState  20  IncreaseAtomicModeCounter    # « ouvre le groupe »
IMatchState  21  DecreaseAtomicModeCounter    # « ferme le groupe »
```

Le triplet tombe sur la **même** interface et sa sémantique concorde mot pour mot avec ce que
`docs/rl/runner-engine.md` §1.5bis décrivait déjà sans le nommer (« ouvre le groupe
(`state.BeginAtomic` slot+0x14) … mini-drain FIFO local au groupe (`state` dequeue slot+10) ») : le
receveur est le **`state`**, pas la requête. `IBattleQuery` slot 20/21 vaut `GetPathTo` /
`GetConnectedPathTo`, ce qui n'a aucun sens dans une file de groupe — l'incohérence était lisible
sans le décompilé.

`test_477r24r1_slots_interface_offline` : **2 failed / 57 passed → 59 passed**.

⚠ **Piège de rédaction, mesuré** : écrire le nom du second slot **pleinement qualifié**
(`IOperationProcessor.UnregisterEntityFromTriggers` slot 85) rouvre un couple faux — la forme C du
détecteur exige un qualificateur, donc `(78, UnregisterEntityFromTriggers)` se forme en franchissant
le saut de ligne et ne cède pas (`ceder_aux_locaux` ne fait céder que ce qui franchit une
**virgule**). Le nom nu est ce qui laisse la forme B (nom PUIS slot, jamais multi-ligne) faire son
office. Corrigé dans le même geste.

### #943-r1 — `TARGETING_OPTIONS_UNPORTED[1215]`, `range = None` → `RANGE_SELF` (RÉSOLU)

`InstrumentsOfVengeanceAbility$$.ctor` est une STATIC-COPY du preset
`<TargetingOptions statics>+0x280` — **le même** que celui de `1216 MartialExemplar`, dont #923 a
résolu la portée après avoir lu `TargetingOptions$$.cctor` (qui remplit `<preset>+0x08..0x1f` en
copiant `<TargetingRange statics>+0x60..0x77`) et `TargetingRange$$.cctor` (`+0x60 = 1`,
`+0x68 = Nullable(0)`, `+0x70 = null` = `RANGE_SELF`). Deux STATIC-COPY du même preset ne peuvent
pas avoir deux portées ; seul `additionalRules = 0x10` les sépare.

Delta observable, mesuré sur le foyer unique de la résolution de portée :

```
AVANT  _range_terms(1215) = None            # aucun gate -> get_range() None -> PERMISSIF
APRES  _range_terms(1215) = (0, False, False)
TEMOIN _range_terms(1216) = (0, False, False)
```

La correction **concorde** avec la seule mesure live existante (`probe_27_r6` :
`abilityTargets(1215)` rend UNE cible, le caster) : avec `overrideRange = 0`, seule la tuile du
caster passe le gate. Le `None` d'avant ne pouvait pas *produire* cette unique cible par la portée.

### #941-r3 — deux cliquets qui rendaient VERT sans rien visiter (RÉSOLU sur 2 des 7)

**Le critère syntaxique de #941 est faux au grain du FICHIER**, et c'est le résultat principal de ce
volet. Sur les sept fichiers nommés, la lecture site par site donne :

| fichier | verdict |
|---|---|
| `test_ability_registry_ratchet.py` | **VRAI** — le cas nommé, réparé |
| `test_421_effect_active_gate_offline.py` | **VRAI** au grain du TEST (deux tests), réparé |
| `test_231r1_master_tutelaries_expiry_offline.py` | faux positif — `is True` / `is False`, aucun ensemble |
| `test_refresh_active_flag_discriminant_offline.py` | faux positif — porte déjà `flagged < overrides` (strict) et `PORTED in overrides` |
| `test_433_r4_r2_r1_r2_line_of_sight_offline.py` | faux positif — table de vérité, `is True` / `is False` |
| `test_498r1_unstoppable_momentum_playbook_offline.py` | faux positif — porte un « TEMOIN NON NUL » explicite (`libre == 3.0`) |
| `test_462_r4b_r1_defender_additive_offline.py` | faux positif — `att.additive == ADD_ATT + ADD_DEF`, `!=` |

Le critère comptait `== 0` (`eff.remaining_turns == 0`) et `not rules & ELEV` comme « assertions de
vide ». Cinq des sept portent déjà leur témoin non nul.

**Contre-épreuve du cas nommé**, par mutation de la racine du balayage (`PY_ROOT`) :

```
[B1 corpus SYNTHETIQUE porteur d'un fautif]  garde : DETECTE   tests gardes : rouge / rouge
[B2 racine EFFONDREE (corpus vide)]          garde : DETECTE   tests gardes : VERT  / VERT
[A1 racine un cran TROP HAUT]                garde : DETECTE   tests gardes : VERT  / VERT
[A2 racine un cran TROP BAS]                 garde : DETECTE   tests gardes : VERT  / VERT
[SAIN -- corpus reel]                        garde : PASSE     tests gardes : VERT  / VERT
```

Le couple **(B1, B2)** est le discriminant : même critère, même détecteur, seul le CORPUS change —
et le verdict passe de rouge à VERT. C'est « un recenseur ne peut pas rendre zéro sur ce qu'il ne
visite pas », appliqué au corpus.

⚠ **Et la mutation a d'abord NE PAS mordu** : `_balayer_ciblage(racine=PY_ROOT)` fige sa racine en
**valeur par défaut**, à l'import — réaffecter `M.PY_ROOT` seul laisse les deux tests balayer le
vrai corpus. Il faut substituer `_balayer_ciblage` **et** `_sources_python`. Une contre-épreuve qui
ne mord pas ressemble exactement à une garde qui marche.

Pour `test_421`, la mesure AVANT/APRÈS sur l'arbre témoin donne le gain net :

```
M1 registre EFFECT_TRIGGERS + RAIL vides
   AVANT : test_no_targets_rail_trigger_is_left_without_its_gate = VERT   (`[] == []`)
   APRES : ROUGE -- « la boucle n'a visite que 0 classe(s) du rail TARGETS/APPLY_REVERT »
```

⚠ **La borne du non-vide est MESURÉE, et la première valeur écrite était FAUSSE** : « la plupart des
90 classes » donnait 60 ; la ventilation réelle est `ARRAYSET 77 / TARGETS 17 / ENV_ABILITY 2 /
APPLY_REVERT 1`, soit **18** sur le rail gardé. Borne écrite basse (12) : elle garde l'effondrement,
pas la cadence.

### #933-r1 — le montage de `1227` attaquait à distance 3 avec une arme de portée 2 (RÉSOLU pour panoply)

Le résidu proposait de lire `_place_at_distance` comme un échec de montage : c'est le cas, mais pas
là où il le disait (la fonction ASSERTE, elle ne rend pas `None`). Le `None` vient de l'attaque
elle-même. Diagnostic live, même état, deux distances :

```
distance 3 -> AttackDamageOperation.execute rend None
distance 2 -> rend son dict complet
stats / PV / gate cible-morte / gate caster-mort : SAINS des deux cotes
```

Cause : `necroDestroyer` porte **deux** armes — `unit_map melee-multihit` rend `6hmp60/6hR2p60`,
donc mêlée portée 1 **et** tir portée **2** — alors que l'en-tête du fichier n'en citait qu'une
(« 6 coups de MELEE »). Au-delà de 2, `FindAttackWeapon` (slot `0xaf` d'`IBattleQuery`) ne rend
aucune arme et `ALoki_NormalAttackAbility$$ExecuteBehaviour` sort **avant** `ExecuteNormalAttack`.
Le port mirrore ce gate depuis **#419-r1-tr14-r1-r1**, et c'est lui qui a rendu la distance 3
injouable : **le port avait raison contre le montage**.

La distance de montage est bornée des deux côtés — `>= 2` (gate natif
`NOT IsAdjacent(Owner@+0x30, Caster@+0x48, 3)`) et `<= 2` (portée d'arme) — donc **une seule valeur
tient** : elle est nommée `DIST_MONTAGE`, avec les deux bornes écrites au-dessus.

`test_harlequins_panoply_live` : **2 failed / 8 passed → 10 passed**.

Le second fichier de #933-r1, `test_heroic_fusillade_migration_live.py`, reste **ROUGE** :
`test_g5_move_splash_crit_wiring` voit Judh bouger (`res["move"]["moved"] is True`) mais finir à
distance **2** de la cible au lieu de 1. Cause **différente** de celle de panoply, non tranchée
ici — résidu **#933-r2**.

## 3bis. Deux rouges LIVE de plus, et ils n'ont qu'UNE cause : la bascule BiS

Signalés en cours de tranche (rencontrés par une autre tranche, qui a correctement refusé de se les
attribuer). Reproduits sur mon arbre, qui ne touche à aucun des deux :

```
test_462_r4b_r1_r1_r1_neuroparasite_pose_live.py       port=4677 live=4677 attendu 4448
test_462_r4b_r1_r1_r1_r1_c_r1_tile_owner_gate_live.py  « le montage ne brule pas (tuile=74) »
```

**Le discriminant est bon marché et il est net.** Même arbre, même montage, seule la bascule change :

| fichier | `TACTICUS_BIS_ITEMS` défaut | `TACTICUS_BIS_ITEMS=0` |
|---|---|---|
| `..._neuroparasite_pose_live.py` | 1 failed / 6 passed | **7 passed** |
| `..._tile_owner_gate_live.py` | 1 failed / 6 passed | **7 passed** |

⇒ **une seule cause pour les deux**, et c'est la bascule — deux instances de plus du vice de
`#914-r2` (« toute prémisse de montage écrite AVANT cette bascule est suspecte »).

### Le premier : un rouge qui accuse l'ATTESTATION, pas le code

Lire le triplet dans l'ordre : `port == live`, et c'est la **première** assertion du test qui le
dit. L'accord port/natif n'a jamais été rompu — dans **aucun** des deux régimes. Seul le nombre
gravé `NEURO_ATTACK2 = 4448` (attesté par #462-r4b-r1-r1, PR #553, **avant** la bascule) est
périmé. Faire diverger le port pour satisfaire cette attestation morte aurait été la faute.

Re-gravé à **4677**, avec les deux mesures, leur date et **le régime de chacune** écrits au site.
La contre-épreuve du test (« si ça rougissait au DOUBLE, le port aurait monté le niveau avant de
résoudre le dégât ») est reformulée en `2 x NEURO_ATTACK2` pour survivre au prochain re-gravage.

### Le second : un échec de montage AUTO-DÉCLARÉ, laissé ouvert

`assert dot_a > 0` avec son propre message (« le montage ne brûle pas, la suite ne prouverait
rien ») : l'assertion fait exactement son office, il ne faut pas la retirer. Mais réparer le montage
exige de savoir **quelle stat du régime BiS éteint la brûlure** — non tranché ici. Résidu #933-r4.

### Ce que ces deux-là apprennent sur le cliquet #933

`tests/engine/test_933_premisse_regime_offline.py` est **VERT** (5 passed) et ne connaît ni l'un ni
l'autre. Ce n'est pas un trou de sa liste attestée : son critère cherche une prémisse de régime
**ÉCRITE** dans une docstring, alors que `NEURO_ATTACK2 = 4448` est un **SCALAIRE**. Un test live qui
confronte une mesure à une constante de module est régime-dépendant **par construction**, sans
qu'aucune phrase ne le déclare. Angle mort structurel — et probablement la forme la plus répandue.

## 4. Ce qui n'est PAS couvert

* **Le ledger n'a pas été mis à jour.** `probe_457` refuse sans `TACTICUS_ALLOW_RATCHETS=1` et ses
  cliquets voisins sont suspendus par consigne ; les 15 entrées `VERT` de fichiers rouges restent
  donc écrites. Elles ne mentent pas (le tri-état les classe `PAS MESURE`), mais elles ne
  disparaîtront qu'au premier rejeu. La ligne `NON_VERTS_DECLARES` de `test_477r24r1` reste en
  place **pour cette raison** — le CRAN 1 rougirait sans elle tant que l'attestation dit `ROUGE` —
  et le CRAN 2 la fera sortir toute seule au premier rejeu. Elle a été **réécrite**, pas laissée
  périmée : elle dit que la cause est réparée.
* **17 des 19 fichiers rouges ne sont pas réparés** (résidu **#934-r2**, avec la ventilation
  ci-dessus). Deux l'ont été : `test_477r24r1` (#962-r1) et — hors périmètre offline —
  `test_harlequins_panoply_live` (#933-r1).
* **`engine/runner/operations/damage_ops/normal.py:355` porte la MÊME citation fausse** que celle
  réparée dans le test (« slots 20/21 d'`IBattleQuery` … slot 10 »). Elle échappe aux deux
  détecteurs parce qu'aucun couple ne s'y forme. **Non corrigée ici : ce fichier est le foyer d'une
  autre tranche en vol.** À router.
* `test_463r1_ecart_empreinte_offline.py` n'a pas été re-confronté sur le témoin (cliquet suspendu).
* Le volet #941-r3 ne pose **aucun** non-vide sur les cinq faux positifs : ils n'en ont pas besoin,
  et en ajouter aurait été du bruit qui se lit comme une couverture.
