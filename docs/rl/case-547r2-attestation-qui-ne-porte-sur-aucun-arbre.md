# #547-r2 — six rouges offline, et un ledger dont le compte était faux par construction

**Fait central.** `probe_547` rendait `entrees NON-VERT : 0, dont 0 NON DECLAREES` / `PASS` pendant
que **six** fichiers offline étaient rouges sur `master`. Il n'en voyait que trois. Les trois autres
sont des tests de couverture **à l'échelle du registre** : leur verdict dépend de tout l'arbre, pas
de leur propre blob — donc leur attestation restait verte sans jamais se périmer.

**La mesure qui tranche** (2026-08-10, périmètre de 290 fichiers, foyer
`ledger_vert_offline.raison_de_rejeu` composé avec l'impact de `probe_457`) :

| état de l'attestation | compte |
|---|---|
| VALABLE sur l'arbre courant | **0 / 290** |
| invalidée par « une dépendance MESURÉE a changé depuis » | 272 |
| sans attestation | 11 |
| blob du test changé | 4 |
| non-VERT | 3 |

Le foyer **savait déjà** : les trois rouges invisibles sortaient verbatim en
`une dependance MESUREE a change depuis a55d7539`. Il manquait un **lecteur**, pas un capteur —
c'est pourquoi la piste « marquer les tests à périmètre ARBRE » a été **écartée par la mesure**.

**Correctif.** `probe_547` ne lit plus un verdict écrit : il classe chaque fichier du périmètre en
**tri-état** — `VALABLE ICI` / `non-VERT` / **`PAS MESURE ICI`** — et imprime le **dénominateur avant
le numérateur**. `classer()` est pure ; quatre mutants (`V1..V4`) exercent la discrimination neuve
(16/16 conformes). La staleness **ne rougit pas**, et c'est dit : toute PR change une dépendance de
presque tous les tests, donc ce rouge-là serait permanent, donc muet.

## Les six rouges, et qui était fautif

| rouge | fautif | ce qui l'a fermé |
|---|---|---|
| `test_270r4r2r2_differes_offline` — étage 1 | le **code** | 3 différés GRATUITS hissés en **FORME B** (`morsure` classait `valid_normal_attack_targets` en `HISSAGE_DESARMERAIT` : forme A → 3 failed, forme B → 4 passed) |
| `test_270r4r2r2_differes_offline` — étage 3 | le **seuil** | re-mesuré (270/173) + marge de 20 bornée des deux côtés ; un plafond posé *à* la valeur rougit au merge suivant — arrivé 3 fois |
| `test_448_r1_stormboyz_port_offline` | le **test** | stub de tri à 4 arguments contre 5 ; signature **confirmée au décompilé** (deux surcharges de `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility`, dont le `.ctor` du sélecteur ne garde que `utilityDefinition`) |
| `test_462_r4b_r1_r1_defender_additive_carriers_offline` | **ni l'un ni l'autre** — un port entré sans confrontation (PR #836) | bras `herald` : port **3151** == natif **3151**, contre-modèle écrit **3265** |
| `test_477r24r1_slots_interface_offline` | l'**écriture des deux sites** | citations réécrites en une forme que le parseur apparie juste (banc d'essai, pas devinette) |
| `test_421_effect_active_gate_offline` | le **port** | `BloodChaliceHealOnMeleeAttack` était au registre sans rail *et* sans son gate `EffectComponent.IsActive @+0x5c` (rail TARGETS) — gate posé |
| `test_camo_seed_inventory_offline` | deux **ports** entrés sans verdict de pose (PR #867) | `BloodChalice_ExtraPiercing` et `MindControl_Taunter`, tous deux `runtime` (posés par un `ExecuteBehaviour` d'active) |

## Le bras `herald` (le seul live)

`blackHaarken` est **au pool**. Il caste l'active 1020 à portée 2 ; l'effet 1027 est **LU** sur ses
porteurs dans `decisionView` (charge à usage unique, `On(9 = Attack) & get_OwnerIsTarget &
IsUnit(caster)` — la primaire peut avoir consommé la sienne, celle de derrière non, d'où **deux**
ennemis au roster). Armure forcée 50000 → branche PERÇAGE (sur la branche ARMURE le plancher est
affine de pente 1 : les deux placements coïncident et un accord n'y prouve rien).

Étages vérifiés terme à terme, jamais un scalaire fitté : `def_mods = {additive: 1795.0}`
(`extraDmg[50] = 997 x mult 180`), puis `def_additive_left = 0.0` / `att_additive = 1795.0` après
`_apply_defender_flat_reductions` ; bornes `round((4016+1795) x 0.65 x 1.25) = 4721`, et de même
`6024 -> 6353`, `6614 -> 6832`, `9922 -> 9520`.

## Ce qui reste ouvert

- **#547-r5** — le ledger *sait* quels fichiers rejouer (`probe_457 --depuis-ledger`), et rien ne le
  joue au merge. C'est ce qui fait retomber « attestations valables » à ~0 dès la PR suivante.
- **#270-r4-r2-r2-r4** — les **46** HISSABLES (28 à son ouverture) restent le vrai gisement des
  différés ; le total, lui, ne fait que dériver.
