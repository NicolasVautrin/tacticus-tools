# #949 — `LetTheGalaxyBurn` : le coup n'a jamais manqué, et l'écart réel valait **1 point**

Résidu ouvert par #947 (`case-947-948-passifs-extra-damage.md` §6) sur cette mesure : ledger natif
**8 coups** `[1779, 1539, 1713, 1688, 1520, 1885, 1704, 66723]` contre **6** offline pour 10 124 pts,
« un coup SUPPLÉMENTAIRE que le port ne matérialise pas ». Question ouverte : lequel des deux
disjoints du gate (`TargetHasTileEffect | IsPersistentData`) tenait, et l'écart venait-il du **gate**
ou du **canal** ?

**Réponse : ni l'un ni l'autre.** Les trois termes de la mesure d'origine étaient faux, et l'écart
réel — qui existe — est ailleurs, plus fin, et **pas propre à cette ability**.

## 1. Décomposition par étage (`probe_949_ltgb_coup_manquant.py`)

Board `MC1_67` / seed 4321, `blackHaarken` avec ses traits **NATIFS**, montage de #947 **moins**
`--unit-stat "blackHaarken:Traits=[]"`.

| étage | ce qui est mesuré | résultat |
|---|---|---|
| 1 · **attribution** | `Effect_Type` de chaque event de dégât | le `66723` porte **1476** = `DespoiledGround` — **ce n'est pas un coup** |
| 2 · **compte de coups** | coups natif vs port | **7** contre **7** (et non 8 contre 6) |
| 3 · **magnitude** | valeur du coup surnuméraire | **1704** des deux côtés |
| 4 · **gate** | status-effects de la tuile de la cible, live | **aucun** ⇒ `TargetHasTileEffect` FAUX |

**Le disjoint qui tenait est `IsPersistentData`** : le `Maybe(LetTheGalaxyBurnChancePct = 33)` de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` avait
armé le flag. Le port l'arme aussi — trace : `matches` → `true`, `MaybeTrigger` → `true`,
`LetTheGalaxyBurnEffect.additional_hit_groups` → `{count: 1, min: 1106, max: 1106, profile: null}`,
`execute_additional_hits` → `1704`.

### Les trois erreurs de la mesure d'origine

1. **Le lecteur additionnait deux populations d'events.** `probe_947._attack` retient tout event
   portant un `Amount`, canaux étrangers à l'attaque compris. Le tick `DespoiledGround` (déjà porté
   et confronté bit-exact par **#BL-1029r-r2**, 35 902 = 35 902) entrait donc dans le « ledger de
   coups ».
2. **Le lecteur ne lisait qu'un canal côté port.** `damage_ops/normal.py::execute` publie la phase
   d'arme dans `per_hit` et le canal #179 **à côté**, dans `additional_hits` — deux sous-opérations
   natives distinctes, donc deux clés. `probe_947._replay` ne lisait que la première.
3. **D'où un faux « bit-exact » rassurant** avec `Traits=[]` : sans `LetTheGalaxyBurn`, aucun groupe
   #179 n'existe, donc les deux lectures coïncident. L'isolation ne masquait aucun bug — elle
   éteignait le seul régime où le lecteur était faux.

**Arbitre décisif** : `hp_delta = 11828` = la somme EXACTE des 7 coups natifs. Le retrait réel de PV
est insensible à la façon dont le port ventile ses canaux.

## 2. Le décompilé — le gate était fidèle depuis le début

`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`, relu sur
`rnca9r7q6c` : `get_OwnerIsCaster & (TargetHasTileEffect | IsPersistentData(...))`, dégât
`FirstHitInCurrentAttackDamageRange` en `param_3` **et** `param_8`, profil `0xffffffff` (NULL),
count `0` (⇒ 1 coup), cap `0`. Le port en est le mirror exact. **Rien à corriger côté gate.**

## 3. L'écart RÉEL : 1 point, et il n'appartient pas à `LetTheGalaxyBurn`

Généralisation (`--bras isolation`, 6 attaques enchaînées, même flux RNG, les DEUX branches du gate
exercées) : compte de coups **6/6** correct, un seul écart de valeur.

| rang | `Maybe` | tuile cible | natif | port (avant) |
|---|---|---|---|---|
| 1 | `False` | — | `[943, 969, 797, 1026]` | identique |
| 2 | `True` | *(vide)* → branche `IsPersistentData` | `[…, **443**]` | `[…, **442**]` |
| 3 | `True` | `DespoiledGround` → branche `TargetHasTileEffect` | `[…, 885]` | identique |
| 4-6 | `False` | — | 4 coups | identique |

**Décomposition du point manquant** — même entrée `[1106, 1106]` aux rangs 2 et 3 :

```
percage(1106, pierce 80, armure 1608) = 884.8000000515021      # FRACTIONNAIRE
rang 3 : face defenseur neutre            -> Round(884.8)                 = 885   OK
rang 2 : face defenseur x0.50 (SereneUnifierSenseOfStone)
         natif : Round(884.8) = 885 ; Round(885 x 0.5) = Round(442.5)     = 443
         port  : Round(884.8 x 0.5)       = Round(442.4)                  = 442   (-1)
```

La cause est l'**ordre des quatre consommations** de `apply_pierce_and_modifiers` : le port faisait
`(pct_att, pct_def, mult_att, mult_def)`, donc le multiplicateur de la face ATTAQUANTE s'appliquait
**après** le %-effet de la face DÉFENSEUR. Or `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
**clôt** la face attaquant (étape 3, `CalculateBaseDamageWithModifiers`, **inconditionnelle même à
multiplicateur neutre**) avant d'ouvrir la face défenseur (étape 4). C'est exactement la loi que
#446-r2 avait mesurée et écrite — elle manquait simplement quand la face attaquant n'a pas de
%-effet, parce que `apply_pct_entries([])` rend la valeur **inchangée, sans `Round`**.

**Correctif** : les quatre appels sont groupés **par face**. Rayon dérivé, pas supposé — déplacer
`apply_pct_entries(d, [])` est un no-op pur, et un `Round` sur une valeur déjà arrondie est
l'identité :

* `pct_list_defender` **vide** → inchangé (#446-r2 stat-mod Thorns, #462-r4a, #98) ;
* `pct_list` **non vide** → inchangé, son `Round` a déjà matérialisé (#437-r1) ;
* seul change « face ATT sans %-effet **+** face DÉF avec %-effet », qu'aucune mesure n'exerçait.
  **17** effets portent une face défenseur réelle.

Le coup `LetTheGalaxyBurn` rend l'écart **systématique** (cellule DÉGÉNÉRÉE `min == max` ⇒ toujours
le même côté du `.5`) là où les coups d'arme ne le montrent qu'au hasard des tirages : c'est ce qui
l'a rendu visible, pas ce qui le cause.

## 4. Une prémisse périmée trouvée en chemin

`test_446_r2_inter_face_rounding_offline.py::test_effet_defenseur_reste_dans_la_meme_chaine`
affirmait l'inverse (témoin natif **305**, sans `Round` intercalé) — et il **rougissait** sur le
correctif. Il posait `Terrifying_ExtraDefense` (`x0.70`) dans `pct_list_defender`, c'est-à-dire dans
la face que **#437-r1-r1-r1 lui a retirée** : le test juste en dessous, dans le même fichier, énonce
depuis lors que cet effet dérive de `DamageModifierAbilityEffect`, sort par le forwarder
`CreateEffectDamageBonusForAttack`, et est étiqueté `face=attacker` — les deux sources de
`probe_437r1r1r1_effect_face_table.py` (port et natif) le rendent `attacker`, concordantes.

**Le témoin `305` n'avait donc jamais été mesuré sur une face défenseur.** Le cran est conservé
entier — même valeur, même sens — sur la face que la mesure lui donne ; il reste vert.

Le témoin de #949, lui, porte sur `SereneUnifierSenseOfStone` (1169), dont la classe native
`IdunBattle.Entities.Effects.Loki.SereneUnifierSenseOfStoneEffect` **ne déclare que**
`...$$CreateEffectDamageMalusForDefense` — le slot défenseur, sans forwarder d'attaque. C'est le
premier témoin natif d'une face défenseur **réelle**.

## 5. Gardes

* `test_446_r2_inter_face_rounding_offline.py` — `test_effet_defenseur_reel_materialise_la_face_attaquant`
  (témoin natif **443**) + `test_percage_949_rend_le_regime_discriminant`, qui **assertionne son
  propre régime** : partie entière 884, matérialisation à 885, 885 **impair**, et `442` sans
  matérialisation. ⚠ Ce dernier a d'abord été écrit avec le seuil « à un cheveu sous l'entier »
  **recopié de #446-r2** — faux ici (884.8) : il a rougi, et c'est ce qui a évité un vert obtenu
  pour la mauvaise raison.
* `test_949_ledger_complet_offline.py` — le **contrat de ventilation** (`normal.py::execute` publie
  `additional_hits` à part, `per_hit` reste la phase d'arme), les **lecteurs** de la famille qui
  doivent recoller, et l'**ordre par face** (cliquet de forme).
* **Contre-épreuve par mutation, vérifiée mordante** : sous l'ordre d'avant, `apply_pierce_and_modifiers`
  rend **442** et les deux gardes rougissent. ⚠ Une première tentative n'avait **pas** muté le
  fichier (substitution manquée) et rendait 12 verts — un vert sous mutation non appliquée ne prouve
  rien ; la contre-épreuve vérifie désormais la morsure **avant** de conclure.

## 6. Validation

Offline : 90 passed / 3 skipped sur les 7 fichiers gardant les étages d'arrondi ; 3 passed sur le
garde #949. Live (build `rnca9r7q6c`) : `test_let_the_galaxy_burn_live` 3, `test_446_r2_…_live` 4,
`test_offbyone_armor_38_live` 2, `test_normal_attack_bounds_rounding_live` + `test_additional_hits_rounding_live` 4,
`test_additional_hits_{amount_bounds,roll_order,scalar_bounds}_live` 16,
`test_947_948_extra_damage_passives_live` 2. Ledger natif reproduit **6/6 bit-exact** après correctif.

**Non couvert** : le balayage des ~100 sites `damage_handler.last` du corpus, dont certains peuvent
porter le même vice de lecteur → résidu **#949-r1**. Le résidu `#437-r1-r1-r2` (une face portant à
la fois un %-effet et un stat-mod : deux `Round` port contre un natif) est **inchangé** — le
regroupement rend les faces consécutives, il ne fusionne pas les deux conteneurs.
