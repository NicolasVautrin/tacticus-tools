# #10019 — La prédiction comptait les coups avec la bonne formule, mais il lui manquait UN COUP

*Question posée : « la face PRÉDICTION appelle-t-elle `GetDefaultAttackHits` là où le natif appelle
`GetAttackHits` ? »*

**Réponse : NON.** Sur le vecteur qui diverge — l'attaque NORMALE — la prédiction traverse **déjà**
la formule complète. Le symptôme de la fiche est réel et se reproduit à l'identique ; son foyer est
faux. La cause est **un terme manquant DANS** la formule, et il a un nom :
`MasterAnnihilator_extraHit`.

---

## 1. La mesure de la fiche se reproduit — et son foyer tombe

`engine_agreement_stages.py --build --seeds 777,909 --steps 20` (board `MC1_67`, session 10) :
**19 confrontations, 16 match, 0 staleness, 3 mismatch-logic** — les trois divergences annoncées,
aux mêmes valeurs.

Le dump JSON les localise, et c'est ce qui tranche : **toutes les trois portent sur `ability 69`**
— l'attaque NORMALE — vers la cible `93`. Or ce vecteur passe par
`playbook/prediction/normal_attack.py` → `attack_hits_with_modifiers` (mirror du corps de
`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`), alimenté par un jumeau de
`board` / `aura_sources` / `target_effects` bâti depuis la `Scene`. **Le « jumeau côté scène » que
la fiche demandait d'écrire existe**, et son substrat publie bien auras et couverture — le point
qu'elle signalait comme non mesuré est donc acquis, par constat d'existence.

Les deux foyers qu'elle nommait ne peuvent porter aucun des trois cas :

| foyer annoncé | ce qu'il est réellement |
|---|---|
| `active_ability.py::get_hits` | **zéro appelant** dans `engine/**` (balayage du dépôt) |
| `active_ability.py::get_special_hits` | vecteur **ABILITY**, que `case-61` déclare FIDÈLE avec ground truth live — l'asymétrie y est NATIVE |

## 2. Le discriminant, et pourquoi le témoin s'explique

`probe_10019_prediction_hits.py` décompose les six étages de la formule à chaque appel de
prédiction. Il rend le discriminant en une ligne : la cible `93` (`templChampion`) porte
`MasterAnnihilator_extraHit` chez les **trois** divergents et **pas** chez le concordant. C'est le
seul effet dans ce cas (`PowerTrip_ReduceArmor` manque chez u85).

| unité | composition portée | port | natif | rapport |
|---|---|---|---|---|
| u85 `orksKillaKan` | base 3 + 1 `PowerTrip` | 4 | 5 | 5/4 |
| u79 `tauDarkstrider` | base 3 − 1 `Parry` | 2 | 3 | 3/2 — **`kill` bascule** |
| u77 `eldarMauganRa` | base 6 | 6 | 7 | 7/6 |
| **u83 `admecDominus`** | base 1 | **1** | **1** | **témoin, immobile** |

Le témoin n'est pas une coïncidence : **u83 EST le poseur de la marque** (`MasterAnnihilator`
= passif de Vitruvius). Au pas 5 elle n'est pas encore là — elle est le fruit de son attaque.

Le dégât **par coup** est identique des deux côtés (277, 30, 399) : seul le **compte** diffère,
d'exactement un.

## 3. Deux faces, deux rendus — et les deux sont mesurés

`#204` avait retiré ce terme de la formule de coups. **Ce retrait reste juste pour le COMBAT** :
l'événement supplémentaire y vaut une CONSTANTE (stat `ATTACK` à l'unité, 4617 sur 5/5) quand les
coups d'arme prennent 8 valeurs distinctes sur 8 — c'est un groupe du canal #179.

Ce que `#204` n'avait pas mesuré, c'est la **PRÉDICTION** : son verdict s'appuyait sur la
**déduction** de `case-227` §2.5 (« hors `OngoingAttack`, `FirstHitInCurrentAttackDamageRange` rend
0 »). Vérifié : les quatre mesures de `#227` (§4.1 à §4.3) portent **toutes** sur le combat.

La mesure la réfute pour ce porteur, et l'argument est arithmétique : un groupe à dégât **constant**
ajouterait le **même entier aux deux bornes**. u77 exigerait `+399` et `+598` à la fois — exclu.

## 4. La contre-épreuve causale

Les trois divergences n'établissent qu'une **corrélation** : quatre unités différentes.
`probe_10019_causal_prediction_hits.py` supprime ce degré de liberté — montage de `probe_204
--case master` (`admecDominus` poseur, `ultraApothecary` témoin à **1 coup**, `bloodSanguinary`),
même attaquant, même cible, même tuile, même runner, la marque étant la **seule** variable :

```
phase NUE    marque=False   oracle natif raw = (3694,  5540)
phase ARMEE  marque=True    oracle natif raw = (7388, 11080)
rapports natifs : min=2.0000  max=2.0000        <- (h+1)/h avec h=1
port : nue=1  armee=2  rapport=2.0
```

C'est aussi une **généralisation** : base 1 (jamais testée dans le seed 777, qui a 4/2/6), autres
unités, autre cible, en **mêlée**. Le probe **refuse de conclure** si la marque n'a pas été posée ou
si les deux phases rendent le même nombre — un accord en régime dégénéré ne prouverait rien.

## 5. Le port

`is_prediction` est un paramètre **séparé** d'`include_bonus_hit_behaviours`, à dessein : le cliquet
qui garde `#204` est monté en régime COMBAT tout en passant `include_bonus_hit_behaviours=True` —
les confondre l'aurait fait rougir sur une vérité qu'il garde correctement. Défaut `False` : toute
façade qui ne le passe pas (les quatre du combat, tous les probes) garde son comportement au bit
près. La contribution est un `for_addition` **positif**, donc `BlockHitsReduction` ne l'éteint pas —
fidèle au tri natif, qui porte sur le **signe** et non sur la provenance.

**Avant / après**, mêmes seeds, même board :

| étage | avant | après |
|---|---|---|
| PRÉDICTION | 16/19 (84 %), 3 logic | **19/19 (100 %), 0 logic** |
| champs divergents | `raw*` 3+3, `health*` 2+2, `kill` 1 | **aucun** |
| misses `[move]` | 29/32 — dont `pos-pair-prediction` 1 | **30/32** — ce miss a disparu |
| misses `[ability]` | 22/24 | 22/24 (inchangé) |

Le `pos-pair-prediction` qui tombe est la **décision de tuile** que la fiche chiffrait à **+70,0**
d'utilité : le gain est bien une décision, pas seulement un chiffre.

## 6. RE — ce qui a été lu sur `t6dpr4k06g`

`DamagePrediction$$GetAttackHits` : après la base (verbatim `GetDefaultAttackHits`), il trie les
`HitsBonusForAttack` en **deux listes selon le SIGNE** du `Nullable<int>` à `+0x1c`, somme les
positives inconditionnellement, les négatives seulement si aucun effet n'arme `BlockHitsReduction`,
applique le **plafond** `Max(total, Min(base, cap))` (`Nullable<int>` `+0x24`), puis un **override
absolu** (`+0x2c`) et enfin une branche qui **réinitialise à `weaponHits`** (booléen `+0x34`).
Les deux détails que la fiche demandait de ne pas perdre sont donc **lus** et **déjà portés**.

Point (c) de la fiche — **RÉFUTÉ** : `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`
n'est **pas** le même code que `GetAttackHits`, elle l'**appelle** — elle évalue ses trois
sous-formules (attaquant, défenseur, `weaponHits`) puis invoque le slot d'interface `0xb6`, avec
`hitGroupIndex` = `0` littéral.

## Résidus

- **`#10019-r1`** — la **VOIE** native du coup prédit n'est pas tranchée. Cette classe ne déclare
  aucun `CreateEffectHitsBonusForAttack` (absent de `ghidra/functions.tsv` **et** de
  `frida/methods.tsv` ; un corps non trivial n'aurait pas été dédupliqué), donc `GetAttackHits` ne
  le compte pas : le coup vient de `IdunBattle.Entities.Abilities.AActiveAbility$$AddAdditionalHitsToPrediction`,
  qui appelle le **même** slot `PredictAttack` (`0x27`) que les coups d'arme et somme par
  `IdunBattle.Core.Services.DamagePredictionResult$$Add`. On porte l'**effet mesuré**, pas la voie —
  même forme que `GetStuckIn`. Trancher exige un capteur sur ce maillon.
- **Les deux jumeaux du même nœud ne sont PAS instruits** : `LetTheGalaxyBurnEffect` et le
  troisième porteur de `attack_hit_damage` gardent leur face prédiction éteinte. La déduction de
  `case-227` §2.5 vient d'être réfutée pour **un** porteur ; rien ne dit qu'elle l'est pour eux,
  et personne ne les a mesurés. Ne pas généraliser sans montage.
