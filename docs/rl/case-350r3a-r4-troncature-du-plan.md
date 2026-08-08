# #350-r3a-r4 — le résidu désignait 6 SITES ; c'est **une SOURCE** qui tronque

**Statut** : RÉSOLU pour les trois gates de POSITION, avec un foyer unique et un cliquet
structurel. Les deux gates de DÉGÂT restent exposés et c'est **mesuré, pas supposé** (§5). Le
correctif harnais est **livré et exige une réinjection** (§6).

## 1. Le mécanisme, hérité et non re-mesuré

`computeAttackPlans` (`frida/hooks/features/ai-step/projection.ts`) plafonne son shrink-and-recall :
`for (let r = 0; r < maxRank; r++)`. Ce plafond n'existe **nulle part** côté natif —
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` interroge
`IdunBattle.Core.Services.AttackQuery$$GetValidTargets(caster, UnitPosition(P), ability)` une fois
par position, sans borne. Mesure de la tranche parente (`case-350r3-oracle-noncomparable.md` §9) :
à `maxRank = 6` — le défaut du RPC `decisionView`, donc le régime de **production** — **21 positions
sur 33** disparaissent, et l'argmax se déplace (natif `(1,3)`, port `(0,3)`).

## 2. L'axe du résidu était FAUX — ce n'est pas le site, c'est la source

Le résidu recensait « 6 sites lisent encore `ranked` ». Mesuré : **les mêmes six sites servent deux
faces**, et une seule tronque.

| face | source du `plan` | `ranked` |
|---|---|---|
| DÉCISION | `dv["attackPlans"]` ⇒ `computeAttackPlans` | **TRONQUÉ** à `maxRank` |
| COMBAT | `engine/ai/state_bridge.py::_plans_for_unit` | **COMPLET** — énumère toutes les tuiles candidates dans la portée |

Réparer par site aurait donc multiplié la surface par six **sans fermer le gisement** : un septième
lecteur de `ranked` serait né exposé, et aucun test de valeur ne l'aurait vu.

## 3. Le foyer — `engine/ai/cast_positions.py`, TRI-ÉTAT

```
ev["rankComplete"] is True   -> `ranked` EST complet. ZÉRO RPC.
ev["rankComplete"] is False  -> le plan DIT qu'il a plafonné -> `castFromTiles`.
drapeau ABSENT               -> PAS MESURÉ, jamais rabattu sur True -> `castFromTiles`.
```

Rabattre l'absence sur `True` aurait été la dégradation permissive elle-même : ni erreur ni crash,
et le gate refuse des attaques que le natif autorise. Le drapeau est posé par `state_bridge`
(gratuit) et par `projection.ts` (livré, §6).

`castFromTiles` = `AttackQuery$$GetInvalidTargetReason` tuile par tuile : **le même prédicat que
`GetBestTileToAttackFrom`, sans le plafond** — écart mesuré contre l'éligibilité native : 0 position
sur 33, à tous les rangs.

**Trois replis NOMMÉS et COMPTÉS** (seam absente, RPC en erreur, ensemble vide) rendent `ranked`
plutôt que `set()` : faire disparaître la cible est pire que la tronquer.

## 4. Les trois gates de POSITION, câblés

| site | ce que la troncature lui faisait dire |
|---|---|
| `ai/action_generators.py::_best_attack` | `tile not in legal[tgt]` ⇒ attaque refusée depuis une tuile que le natif autorise. **Le plus large des six** : le tier COMPARABLE couvre toutes les attaques, attaque normale comprise |
| `playbook/noncomparable/_base.py::_get_num_attack_targets_in_position` | compte de cibles trop FAIBLE — et ce compte **est** l'utilité de `TheQuickeningPlaybook` |
| `playbook/loki_custom.py::_get_target` | cible déclarée non valide depuis `caster_tile` ⇒ `SelectFirst` élit une autre cible, ou aucune |

`_PlanTargetPlaybook.eligible_positions` (corrigé par `#350-r3a-r3`) **délègue** désormais au même
foyer et lui passe l'eval : sur la face COMBAT il ne paie plus de RPC du tout.

`runner/operations/summon_ai.py` n'est **pas** exposé : sa source est le bridge offline. Son
re-filtrage par `range_gate` recopie l'eval (`ev = dict(ev)`), donc il **préserve** `rankComplete`.

## 5. Les deux gates de DÉGÂT ne sont PAS réparables côté port — et c'est structurel

`noncomparable/hammer_of_wrath.py::_enemy_killed_by_normal_attack` (lit `dmgMin`) et
`noncomparable/holy_duel.py::_enemy_might_be_killed…` (lit `kill` / `dmgMax`) lisent des champs de
**dégât**, qui ne vivent que dans `ranked` : `castFromTiles` rend des positions, pas des dégâts.
Une tuile sure-kill écartée par `maxRank` fait rendre **FAUX à tort**, donc l'ability est évaluée là
où le natif s'abstient (`ShouldEvaluate = !EnemyCouldBeKilledWithNormalAttack`). Seul le harnais
peut servir ce cas. Les deux sites le **déclarent en commentaire**, et le cliquet ne les garde pas —
les inscrire dans la liste des gates de position aurait été une fausse fermeture.

## 6. Le correctif harnais — LIVRÉ, exige une RÉINJECTION

`projection.ts` publie `rankComplete` sur chaque `AttackEval` : `true` **uniquement** sur la sortie
par épuisement (`best.isNull()`). Plafond atteint, `Remove` non résolu, `Remove` rendant faux,
exception ⇒ `false`. Un défaut à `true` aurait fait taire le cas nominal ; il est donc **faux par
défaut**.

Ce n'est **pas** un détronquage : le coût du shrink-and-recall reste borné. Le drapeau rend la
troncature **lisible**, ce qui permet au port de ne payer un `castFromTiles` que là où il en a
besoin — au lieu de le payer partout (régime actuel, `non-mesure`) ou de se dégrader en silence.

⚠ **Tant que la fenêtre n'a pas lieu, la face DÉCISION paie un `castFromTiles` par paire
(ability, cible)** — mesuré sur la fixture `carte` : **8** appels pour 2 cibles × 4 abilities. C'est
le prix de la fidélité sans réinjection, et il disparaît à la réinjection.

## 7. Le témoin — il MORD sur les POSITIONS, il ne mord PAS sur la DÉCISION

`probe_350r3a_r4_comparable_gate.py` réutilise le montage de `#350-r3a-r3` (fixture `carte`, lue
chez elle, jamais recopiée) et compare, sur le MÊME état, `legal` par `ranked` brut (régime de
`master`, obtenu par **mutation** du foyer) et par le foyer.

| anneaux | `maxRank=32` | `maxRank=6` — `legal(ranked)` | `legal(foyer)` | positions gagnées | action déplacée |
|---|---|---|---|---|---|
| 1,3 (défaut) | identique | `{77:6, 79:6}` | `{77:27, 79:13}` | **28** | non |
| 2,5 | identique | `{77:6, 79:6}` | `{77:19, 79:7}` | **14** | non |
| 1,4 | identique | `{77:6, 79:6}` | `{77:27, 79:10}` | **25** | non |
| 3,5 | identique | `{77:6, 79:6}` | `{77:15, 79:7}` | **10** | non |

**Ce que ça établit** : à `maxRank=32` le foyer ne change **rien** (0 position gagnée — contrôle que
le fix ne fabrique pas de positions) ; à `maxRank=6` le gate rendait une réponse **amputée de 10 à
28 positions** sur les quatre géométries.

**Ce que ça n'établit PAS** : aucun **déplacement d'action** du tier COMPARABLE n'a été reproduit.
L'explication est mécanique : `ranked` est classé par `GetBestTileToAttackFrom`, c'est-à-dire par
une utilité de **mouvement**, qui corrèle avec la proximité de la cible — or la position gagnante en
utilité d'**action** y est souvent aussi. Les six premiers rangs contenaient donc le gagnant dans les
quatre cas. Le déplacement est démontré sur la face **NonComparable** (`case-350r3` §9), pas ici.
Résidu `#350-r3a-r4-r1`.

## 8. Le cliquet

`tests/engine/test_350r3a_r4_cast_positions_offline.py` — **13 passed**, 100 % offline. Trois
étages :

1. le **tri-état** du foyer (complet ⇒ aucune seam consultée ; tronqué ⇒ positions récupérées ;
   absent ⇒ mesure, jamais supposition) et les trois replis **comptés** ;
2. `plan_est_complet` prend le membre le plus **faible** — un seul eval tronqué suffit à déplacer un
   argmax ;
3. **garde STRUCTURELLE par AST** : chacun des trois gates de position doit appeler
   `positions_castables`. C'est ce qui empêche un septième lecteur de naître exposé — le mode de
   défaillance qui a laissé six sites survivre au fix de `#350-r3a-r3`. Plus deux gardes de
   non-perte : le bridge déclare ses plans complets, `projection.ts` publie le drapeau **faux par
   défaut**.

## 9. Non-régression

`tests/engine/test_350r3a_r3_position_gate_live.py` — **9 passed** (inchangé). C'est le test du fix
NC, que la délégation au foyer traverse désormais.

## 10. Ce qui n'est PAS couvert

* **Le déplacement d'action du tier COMPARABLE** (§7) — résidu `#350-r3a-r4-r1`.
* **Les deux gates de dégât** (§5) — dépendants d'une réinjection.
* **Le drapeau n'est pas encore actif en live** (§6) : le régime mesuré est `non-mesure` (8 appels
  sur la fixture), donc la branche `rankComplete is False` du foyer n'a été exercée **qu'en
  offline** (cliquet étage 1), jamais contre un vrai plan.
* **Le coût RPC en bataille pleine n'est pas mesuré** — seulement sur une fixture 1 caster / 2
  ennemis.

## 11. Reproduction

```
python scripts/python/probe_350r3a_r4_comparable_gate.py --ranks 32,6
python scripts/python/probe_350r3a_r4_comparable_gate.py --ranks 32,6 --rings 2,5
python -m pytest scripts/python/tests/engine/test_350r3a_r4_cast_positions_offline.py -q
python -m pytest scripts/python/tests/engine/test_350r3a_r3_position_gate_live.py -q
```
