# #462-…-r3-r1-r1-r1 — la face DÉCISION du substrat `unit_state` : **0 ATTEIGNABLE**

**Statut** : RÉSOLU par la mesure. La prémisse du résidu est **confirmée** (la `Scene` porte bien
des morts) et sa conclusion est **infirmée** : les quatre balayages de la face DÉCISION portent
**déjà** leur gate de vivacité, là où la face COMBAT en avait un sans (`defender_fixed_armor`).

## 1. Ce qui était mesuré, et ce qui ne l'était pas

Le résidu disait juste sur le substrat : `build_scene_ctx` construit `pos_by_id` / `team_by_id` /
`hp_by_id` et l'`EffectsState` depuis **TOUT** `dv.units` (morts compris), alors que `ctx_by_id`
vient du `predictor`, donc de `combatSnapshot`, donc des **vivants seuls**. Un
`Scene.unit_state(mort)` n'a donc **aucune clé `traits`**, et le consommateur unique
(`PinnedEffect.is_active` = `Not(HasTrait(Self, TerminatorArmour))`) dégraderait en VRAI.

Ce qui n'était pas mesuré, c'est **qui appelle**. Le résidu écrivait « ~30 appelants sous
`playbook/` ». Mesure : **29 appels** pour **15 clés** `(fichier, fonction)` sous `playbook/`…
**et un 16ᵉ hors `playbook/`**.

## 2. Le 16ᵉ site a été trouvé par le CLIQUET, pas par le recensement

`engine/utilities/wireweave_net.py::target_has_active_wireweave_net`. Une énumération bornée à
`playbook/` — exactement ce que le résidu prescrivait — l'aurait raté. C'est le cliquet
d'exhaustivité du probe (clés non ventilées ⇒ rc 1) qui l'a fait apparaître, à l'inscription des
15 autres.

Même faute que celle corrigée par le recenseur de `#270-r1` : **une portée choisie ne peut pas
montrer le site qu'elle exclut**. Le portail se ventile par la MÉTHODE (`effects`), pas par le
répertoire.

## 3. La ventilation — 36 clés, **0 non ventilée**

| verdict | clés | face |
|---|---|---|
| `INERTE-VIVANT` | 23 | le sujet est un combattant du coup (`att_id`, `tgt_id`, `uid` d'attaquant) |
| `INERTE-AMONT` | 10 | un gate antérieur écarte le cadavre |
| `INERTE-AVAL` | 2 | le portail `Scene.effects` lui-même |
| `ATTEIGNABLE` | 1 | `damage_model::defender_fixed_armor` — **face COMBAT**, déjà traité |

**Face DÉCISION : 0 ATTEIGNABLE.**

Les **quatre balayages** de la face DÉCISION portent leur gate :

| site | gate |
|---|---|
| `prediction/_shared.py::_apply_ally_attack_dmg_bonus` | `(scene.hp(uid) or 0) > 0` dans la compréhension |
| `prediction/_shared.py::_add_positional_and_defender_mods` (`_def_carriers`) | idem |
| `prediction/normal_attack.py::_display_attack_base` (`carriers`) | idem |
| `prediction/normal_attack.py::make_normal_attack_predictions` (`aura_sources`) | itère `_alive_ids` |

Le portail `Scene.effects` **ne choisit aucun sujet** : il relaie celui de son appelant. Son
verdict est donc l'union des leurs — d'où `INERTE-AVAL`, et non un verdict propre.

⚠ **Même réserve que côté COMBAT** : le gate porte sur les **PV**, pas sur `uc.alive`. Il tient
parce que `Scene.hp_by_id` lit `dv.units[].hp`, qui vaut 0 pour un mort. Une capture sans `hp`
le rendrait inerte — la faiblesse est identique sur les deux faces, et elle est écrite au site.

## 4. Ce qui n'est PAS couvert

* **Aucun bras live.** La ventilation est un tri de **sources** (AST) ; le régime qui la falsifierait
  — un cadavre-au-chargement traversant l'un des quatre balayages — exige un état construit hors
  capture, exactement comme côté COMBAT (§2 de la fiche parente : « aucun critère de VALEUR ne
  pouvait voir ce trou »).
* **La réserve `hp` vs `uc.alive`** n'est pas fermée : elle est **héritée**, pas introduite.
* **`StatPart` et les autres substrats** de la `Scene` ne sont pas concernés — seul `unit_state`
  l'était.

## 5. Reproduction

```
python scripts/python/probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_r1_appelants.py --step ventilation
python -m pytest scripts/python/tests/engine/runner/test_462_r4b_substrat_mort_appelants_offline.py -q
```
