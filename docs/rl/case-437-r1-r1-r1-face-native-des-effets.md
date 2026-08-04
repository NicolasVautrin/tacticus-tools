# #437-r1-r1-r1 — la face d'un `EffectBonus` est le SLOT VIRTUEL, pas le porteur

**VERDICT : RÉSOLU.** La face se LIT, exhaustivement et hors-ligne, dans la structure de classes du
binaire. Table dérivée sur les **59** classes d'effet du port à face de dégât, **0 non résolu** :
**9 divergences**, dont **5 à conséquence arithmétique**. La séparation des deux faces est devenue
**inconditionnelle** et le drapeau `separate_face_lists` est **retiré**.

## 1. Le critère, posé AVANT de mesurer

*Qu'est-ce qui ferait conclure qu'un effet donné est sur la face ATTAQUANT plutôt que DÉFENSEUR ?*

`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` applique **un
`Fix64.Round` par accumulateur `Multiplier@0x30` non nul** (loi #437-r1-r1). Donc, pour un effet `X`
de contribution `m != 1` monté avec un second bonus `m'` sur l'autre face :

* face(`X`) = ATTAQUANT ⇒ borne native = `Round(P x m' x m)` — **un** `Round` ;
* face(`X`) = DÉFENSEUR ⇒ borne native = `Round(Round(P x m') x m)` — **deux**.

Les deux prédictions diffèrent de 1 dès que `P x m'` tombe sur un demi-entier. **Un régime où elles
coïncident est DÉGÉNÉRÉ** — et il y en a une classe entière, nommée en §4.

## 2. La loi native, relue de bout en bout (`rnca9r7q6c`)

`CalculateAttackerModifiersForPrediction` et `CalculateDefenderModifiersForPrediction` ont la
**même forme**, à un seul détail près :

```csharp
acc = DamageModifiers.Empty()
<fold des stat-mods de SA face>  ->  DamageModifiers$$Add(acc, modifier)          // surcharge 1-ARG
foreach (entree du MEME dictionnaire d'effets)          // le 5e argument, celui de l'ETAT
    foreach (effet de l'entree)
        b = effet.<SON slot>(abilityEntities)           // 0x16/0x17 attaquant | 0x1a/0x1b defenseur
        if (b.HasValue) liste.Add(b.Value)
foreach (damageBonus in liste)
    modifier = damageBonus.@0x48.HasValue
             ? Nullable(GetFloatMultiplierFromPercentage(@0x48)) : null
    DamageModifiers$$Add(acc, damageBonus, modifier)    // surcharge 2-ARGS -> Multiplier@0x30
```

Trois faits, et c'est tout ce dont la règle a besoin :

1. **Les deux builders énumèrent le MÊME dictionnaire d'effets** — celui de l'état, pas « ceux du
   porteur ». Le trigger (`OwnerIsTarget` / `OwnerIsCaster` / `OwnerIsActor`) choisit **quelle unité
   déclenche**, jamais l'accumulateur.
2. Le pourcentage part dans `Multiplier@0x30` de l'accumulateur **de ce builder-là**.
3. `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack` est
   un **forwarder nu** vers le slot virtuel `CreateDamageModifier` de la sous-classe (lu : il
   recopie les `0x58` octets du `Nullable<EffectBonus>` rendu, rien d'autre).

⇒ **La face d'un effet est le slot qu'il IMPLÉMENTE** :

| slot natif | famille | accumulateur |
|---|---|---|
| `CreateEffectDamageBonusForAttack` (direct) | — | **attaquant** |
| `CreateDamageModifier` | `DamageModifierAbilityEffect` | **attaquant** |
| `CreateEffectDamageMalusForDefense` (direct) | — | **défenseur** |
| `CreateDamageDefenseModifier` | `ADamageDefenseModifierAbilityEffect` | **défenseur** |

## 3. Deux sources de symboles indépendantes, 0 désaccord

`probe_437r1r1r1_effect_face_table.py` dérive la face de **deux** façons et publie leur désaccord
(`--audit`) — un garde-fou dont les deux sources sont fondues ne peut plus signaler sa panne :

* **`frida/classes.tsv`** — la chaîne de parents (**19** filles de `DamageModifierAbilityEffect`,
  **14** de `ADamageDefenseModifierAbilityEffect`) ; immunisée à la déduplication de corps ;
* **`frida/methods.tsv`** — la classe **déclarante** de chaque slot (**19** `CreateDamageModifier`,
  **14** `CreateDamageDefenseModifier`, **107** `CreateEffectDamageBonusForAttack`, **39**
  `CreateEffectDamageMalusForDefense`).

Les comptes concordent exactement, et `--audit` rend **0** classe en désaccord.

## 4. La table — 59 classes, 9 divergences, dont 5 seulement DÉPLACENT une valeur

Le probe couvre **CINQ** canaux du port, pas deux : les trois canaux AURA
(`create_aura_attack_damage_bonus_for_ally`, `..._malus_for_enemy`,
`create_aura_defense_damage_malus_for_ally`) mirroient la boucle state-wide `EffectWithTarget` des
**mêmes** builders, donc un effet-aura a une face comme les autres. Les omettre laissait **13** des
59 classes hors table — et deux des neuf divergences avec elles.

| effet (port) | canal du port | face NATIVE | conséquence |
|---|---|---|---|
| `Terrifying_ExtraDefense` | malus défense | **attaquant** | **%** — mesurée au capteur |
| `MartialKatah_DmgReduction` | malus défense | **attaquant** | **%** |
| `Markerlight` | malus défense | **attaquant** | **%** |
| `DaughterOfTheAbyss_ExtraDamagePct` | aura défense | **attaquant** | **%** |
| `Stunned_DamageModifier` | bonus attaque | **défenseur** | **%** — divergence dans l'AUTRE sens |
| `ExemplarOfHate_Target` | malus défense | attaquant | additif — **DÉGÉNÉRÉ** |
| `Chronometron_ExtraDamage` | malus défense | attaquant | additif — **DÉGÉNÉRÉ** |
| `CamoCloak_DmgReduction` | malus défense | attaquant | additif — **DÉGÉNÉRÉ** |
| `PsychicFortress_DmgReduction` | aura défense | attaquant | additif — **DÉGÉNÉRÉ** |

**Pourquoi les quatre dernières sont DÉGÉNÉRÉES, et ce n'est pas une commodité** :
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` lit `Addition@+0x10` des **DEUX**
accumulateurs et passe `base + Addition(0xd) + Addition(0xe)` à `CalculateBaseDamageWithAllModifiers`
(RE #462-r4b-r1) — le canal additif est donc face-neutre **par construction native**. Idem pour
`Piercing@+0x20` et `ArmorPenetration@+0x28`, sommés eux aussi. La face y est **posée quand même**,
parce qu'elle est LUE, mais aucune valeur ne bouge.

**Deux enseignements que la règle « déduite du porteur » ne pouvait pas exprimer** :

* `Stunned_DamageModifier` est porté par l'**attaquant** et versé côté **défenseur** — la divergence
  existe dans les deux sens, donc aucune heuristique de porteur ne pouvait marcher, même inversée ;
* les deux volets de **la même ability** peuvent être sur des faces **opposées** :
  `DaughterOfTheAbyss_ExtraDamagePct` (slot attaque) contre `DaughterOfTheAbyss_FriendlyDmgReductionPct`
  (slot défense), même porteur.

**Rectification au passage** : la docstring de `PsychicFortressDmgReductionEffect` annonçait une base
`ADamageDefenseModifierAbilityEffect`. `classes.tsv` donne `DamageModifierAbilityEffect`, et
`methods.tsv` ne lui connaît que `CreateDamageModifier` — cohérent avec le symbole qu'elle citait
elle-même deux lignes plus bas.

## 5. Le port — le routage entre à l'ENTRÉE, plus au site de fusion

`DamageModifiers.pct_list` est **l'accumulateur attaquant** et `pct_list_defender` le **défenseur**,
désormais dans **tout** `DamageModifiers` — y compris celui que rend le builder défenseur. Avant, ce
dernier entassait tout dans `pct_list` et le pont (`_apply_defender_flat_reductions`,
`_add_positional_and_defender_mods`) **déplaçait en bloc** : la face était structurellement
indicible, ce qui *forçait* à la déduire du builder.

* `EffectBonus.native_face` porte la face ; **les builders la posent**, depuis un attribut de la
  classe d'effet (`BaseEffect.{ATTACK_BONUS,DEFENSE_MALUS,AURA_*}_NATIVE_FACE`) ;
* `add_modifier` est le **foyer unique** de routage (`pct_list` / `pct_list_defender`, et
  `multiplicative` / `multiplicative_defender` pour le canal stat-mod) ;
* les deux ponts **préservent** la face au lieu de la décider ;
* `apply_all_modifiers` consomme désormais `pct_list_defender` — il le **droppait silencieusement**.

## 6. La dérogation retirée

`separate_face_lists` valait `True` en COMBAT et `False` en PRÉDICTION. Il ne compensait **pas** un
étage d'arrondi mais cette attribution de face. Elle étant corrigée, le paramètre est supprimé, et un
cran token-aware (`test_la_separation_est_INCONDITIONNELLE`) interdit son retour par les **deux**
portes : la signature de `apply_pierce_and_modifiers`, et tout appel d'`engine/` qui passerait le
mot-clé.

**Ce que sa présence coûtait, et personne ne l'avait vu** : #437-r1 avait armé la séparation en
COMBAT **sans** corriger l'attribution. Sur le montage `--two-faces` de #462-r4a, le vecteur COMBAT
de `master` rendait donc `762 / 1142` contre `761 / 1141` natif — un `+1` par borne, actif, qu'aucun
test ne regardait (le seul cran qui montait ce régime construisait son accumulateur à la main).

## 7. Confrontations — quatre canaux indépendants, tous d'accord

1. **Décompilé** — les deux builders, les deux forwarders, lus verbatim (§2).
2. **Capteur `effect-bonus-trace` (#466)** — sur le montage `--two-faces`, **un seul** accumulateur
   qui compose `1 -> 0.6999999999534339 -> 1.0499999998137355`, les deux bonus étiquetés
   `face=attacker` ; sur le montage #437-r1, **deux** accumulateurs distincts (`attacker x1.25`,
   `defender x0.25`, 41/41 sans composition). Mesures antérieures, réexpliquées sans reste par §2.
3. **Inversion PRNG** (#462-r4d-r3, cellule à TROIS entrées : élévation `x1.5` + `MartialKatah`
   `x0.8` + `Thorns` `x1.5`) — natif `(783, 1175)`. `MartialKatah` rangé côté **défenseur** rend
   **1173** ; rangé côté **attaquant**, ce que dit le décompilé, rend **1175**. C'est un canal
   indépendant du capteur ET du décompilé.
4. **Live** :
   * `probe_462_r4a --two-faces` (COMBAT) → le foyer réel trace `modsATT=[1.5, 0.7] modsDEF=[]`,
     natif `761/1141` == port. Avant/après **sur les entrées d'étage mesurées** (`P = 725 / 1087`) :
     `762 / 1142` → `761 / 1141`.
   * `probe_437r1r3` (PRÉDICTION) → `pct_att=[1.25] pct_def=[0.25]` **préservés**,
     `aiPredict = port = (1130, 1695)`. Le régime à deux faces RÉELLES ne bouge pas.

## 8. Ce qui n'est PAS couvert

* **Les 5 effets à conséquence ne sont pas tous confrontés live un par un.** Deux le sont
  (`Terrifying` au capteur + en combat, `MartialKatah` par inversion PRNG) ; `Markerlight`,
  `DaughterOfTheAbyss_ExtraDamagePct` et `Stunned_DamageModifier` reposent sur la **règle du slot**,
  établie exhaustivement au décompilé et vérifiée sur ses deux tables de symboles. Un montage
  discriminant leur manque : il faudrait apparier chacun à un bonus non neutre de l'autre face sur un
  perçage produisant un demi-entier. Leurs tests live actuels (`test_mv71_sniper_drone_live`,
  `test_effect_stun_live`) sont **verts mais non discriminants** — face unique non neutre, régime
  dégénéré.
* **`#437-r1-r1-r2` reste ouvert** (une face portant à la fois un %-effet et un stat-mod : le port y
  ferait deux `Round`, le natif un seul). La correction de face **rapproche** ce régime — la face
  attaquante porte désormais plus d'entrées — sans le réunir : aucun montage du corpus ne pose un
  stat-mod ATTACK (le fold `apply_stat_mod_debuff` reste gaté à `False`, gate non élucidé).
* **`BetterDamagePrediction`** (arbitrage entre tuiles du movable set) n'est toujours ni RE ni mesuré
  — hérité de #437-r1-r1-r3, sans effet sur ce verdict.

## 9. Livré

* `scripts/python/probe_437r1r1r1_effect_face_table.py` — la table, dérivée des deux tables de
  symboles ; `rc` = divergences + non résolus. **Entré à la banque de cliquets.**
* `engine/services/effect_bonus.py`, `damage_modifiers.py`, `damage_prediction.py` —
  `native_face`, routage dans `add_modifier`, `separate_face_lists` retiré.
* `engine/entities/effects/{base,__init__}.py` + 4 modules `loki/` — les cinq attributs de face et
  les neuf dérogations, chacune citant son symbole.
* `engine/runner/operations/damage.py`, `engine/playbook/prediction/_shared.py` — les deux ponts
  préservent la face ; 4 vecteurs COMBAT allégés du drapeau.
* `tests/engine/runner/test_437_r1_face_lists_cells_offline.py` — montage corrigé, cran
  d'inconditionnalité, câblage des 5 faces, routage d'`add_modifier`.
* `tests/engine/test_446_r2_inter_face_rounding_offline.py`,
  `tests/engine/runner/test_462_r4d_r3_two_channels_defender_offline.py` — montages aux faces
  mesurées, contre-épreuves conservées.
* `scripts/python/probe_462_r4a_terrifying_rounding.py` — régimes aux faces natives, **+3 cellules
  #437-r1** (le seul régime du corpus à deux %-faces réelles) et mutant `round_inter` remplacé par
  `fusionne_faces` : l'ancien reproduisait le port depuis que la séparation est la loi.

## 10. La technique, réutilisable

1. **Quand une propriété semble « à mesurer effet par effet », chercher d'abord si elle est
   STRUCTURELLE.** Ici la face n'était pas un comportement à échantillonner mais un **slot de
   vtable** : lisible pour les 59 classes d'un coup, au lieu de 59 montages. La consigne
   « MESURER, pas DÉDUIRE » visait juste — mais l'alternative à la déduction n'était pas
   l'échantillonnage, c'était la **lecture exhaustive**.
2. **Ventiler les divergences par CONSÉQUENCE avant de les traiter.** 9 divergences, 5 qui déplacent
   une valeur, 4 dégénérées *par une propriété native* (la somme des deux `Addition@+0x10`). Dire
   laquelle est laquelle évite à la fois de sur-vendre le correctif et de taire ce qu'on a lu.
3. **Corriger une attribution peut RENDRE AVEUGLE une contre-épreuve.** En rendant `Terrifying` à la
   face attaquante, plus aucun régime de la table #462-r4a n'avait deux %-faces : le mutant
   `round_inter` passait de « mord » à **0/6**, en silence, et la suite restait verte. Un mutant qui
   ne déplace plus rien n'est pas un succès, c'est une garde éteinte — le vérifier fait partie du fix.
4. **Un mutant peut DEVENIR le port.** `round_inter` décrivait l'alternative tant que le port
   fusionnait ; la séparation devenue loi, il décrivait le port lui-même. L'alternative à refuter
   est toujours *de l'autre côté* de la décision courante.
5. **Le canal le moins cher est parfois déjà au dossier.** La cellule à trois entrées de #462-r4d-r3
   dormait dans un test : elle sépare `1173` de `1175` et tranche l'attribution de `MartialKatah`
   sans monter le moindre runner. Relire les cellules natives déjà inversées avant d'en fabriquer.
