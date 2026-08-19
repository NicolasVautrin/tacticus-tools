# #462-r4a — le `+1` de `Terrifying` : DEUX CANAUX, pas un arrondi de plus

`tests/engine/runner/test_terrifying_defense_live.py::test_terrifying_melee_replay_bitexact` rendait,
sur `master`, `off = live - 1` **sur les six coups** (`[433,402,434,378,350,403]` contre
`[434,403,435,379,351,404]`). Les bases diffèrent d'un coup à l'autre : ce n'est pas un facteur.

Ce n'est pas non plus « un `Round` manquant ». C'est **un `Round` DE TROP**, et il vient de #446-r2 :
la face DÉFENSEUR y avait été rangée **entre** les deux étages MULTIPLICATEUR, donc derrière un
arrondi qui n'a rien à faire là pour un effet.

## 1. Ce que dit le décompilé — QUATRE étapes, et surtout DEUX CANAUX

`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, lu verbatim :

```csharp
d = GetBaseDamageWithFixedPiercedArmor(...)                       // Fix64 FRACTIONNAIRE
if (attackModifiers.HasValue)  d = slot 0x11 (attackModifiers,  d);   // ApplyCappedModifiers, liste @0x18
if (defenseModifiers.HasValue) d = slot 0x11 (defenseModifiers, d);
if (attackModifiers.HasValue)  d = slot 0x10 (d, attackModifiers@0x30);   // Round
if (defenseModifiers.HasValue) d = slot 0x10 (d, defenseModifiers@0x30);  // Round
if (defenseModifiers.Override.HasValue) d = override;
```

L'accumulateur a donc **deux canaux distincts**, et ils ne se composent pas de la même façon :

| canal | champ | étage | arrondi |
|---|---|---|---|
| **LISTE** | `@0x18` (entrées `{mult, cap}`) | 1 et 2 (`ApplyCappedModifiers`) | composition sans arrondi entre les faces (#98) |
| **MULTIPLICATEUR** | `Multiplier@0x30` | 3 et 4 (`CalculateBaseDamageWithModifiers`) | **`Fix64.Round(., AwayFromZero)` à CHAQUE étage, même à multiplicateur neutre** |

Et `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` alimente les
deux **par des chemins séparés** :

* les **modifications de stat** (`CalculateModifiersFromStatModifications`, ex. la tuile Thorns) sont
  foldées en UN produit par la surcharge **LISTE** de `GetMultiplierFromDamageBonus`, puis posées par
  `IdunBattle.Core.Services.DamageModifiers$$Add(this, modifier)` — la surcharge **1-ARGUMENT**, qui
  écrit `Multiplier@0x30` ;
* les **effets** passent par la boucle finale et `Add(this, damageBonus, modifier)` — surcharge
  2-ARGUMENTS.

Le port confondait les deux : tout pourcentage, quelle que soit sa provenance, atterrissait dans la
`%-list`. #446-r2 a alors « réparé » le symptôme du canal MULTIPLICATEUR en insérant un `Round` entre
les deux FACES — ce qui est juste pour une modification de stat et **faux pour un effet**.

## 2. La mesure — six régimes, dont deux jamais montés

Oracle : la prédiction native (`aiPlaybookPredict`, `healthDmgMin/Max` divisés par `appliedHits`) et,
pour le montage principal, le **replay RNG-seedé** des six coups. Les deux concordent.

| régime | perçage `P` (Fix64 exact) | face ATT | face DEF | natif |
|---|---|---|---|---|
| `necroDestroyer` → `eldarMauganRa`, armure 100 | `625` | — | effet `x0.70` | **437** |
| idem, armure 200 | `525` | — | effet `x0.70` | **367** |
| idem, armure 400/1200/2208/3400 (MIN) | `435.000000068` | — | effet `x0.70` | **305** |
| idem (MAX, armures 1200+) | `652.200000101` | — | effet `x0.70` | **457** |
| **deux faces** : élévation ET `Terrifying` | `725` / `1087` | `x1.50` | effet `x0.70` | **761 / 1141** |
| #446-r2 `T` : tuile Thorns | `288.99999993` | — | **stat-mod `x1.50`** | **434** |
| #446-r2 `A` : élévation | `288.99999993` | `x1.50` | — | **433** |

Trois choses que ce tableau tranche, et qu'aucun point isolé n'aurait tranchées :

1. **L'armure 100 réfute `ceil` et la soustraction tronquée.** `P = 625` exact, `0,70 x 625 = 437,5`
   *pile* — et le natif rend **437**, pas 438. Ce n'est possible que si le multiplicateur est
   STRICTEMENT sous `0,7` : `GetFloatMultiplierFromPercentage(-30)` = `One - Div(30,100)` =
   raw `3006477107`, soit `0.69999999995`. L'arithmétique Fix64 exacte est donc confirmée **par la
   valeur natives elle-même**, et les deux modèles « de surface » (`ceil(0,7 P)`, `P - floor(0,3 P)`)
   tombent — alors qu'ils collaient 10/12.
2. **Le cran DEUX FACES sépare la chaîne unique des deux chaînes.** `Round(725 x 1,50 x 0,70)` = 761
   contre `Round(Round(725 x 1,50) x 0,70)` = 762 ; en MAX, 1141 contre 1142. Le natif rend 761/1141.
   C'est le régime que #446-r2 **n'avait pas pu monter** (sa case-doc §4bis le dit : « NON-RÉGRESSION,
   pas une reproduction »), et c'est lui qui interdit d'arrondir entre les faces.
3. **`T` et `A` de #446-r2 gardent leur asymétrie** — même perçage, même `x1,50`, 434 contre 433 — et
   elle s'explique désormais par le CANAL, pas par la face : `T` est une modification de stat
   (`Multiplier`, donc `Round` intercalé), `A` une élévation (`%-list`, donc pas d'arrondi).

Le montage à deux faces **DÉPLACE les unités** (recherche d'un couple adjacent à dénivelé, `_drive_to`)
et force les PV à 90 000 : sans ça la prédiction native est écrêtée par la santé restante
(`FillUpStatComponent.MaxReduceByMinimum`) et l'oracle rend `17`, inexploitable.

## 3. Le fix

* `engine/services/effect_bonus.py` — `EffectBonus.from_stat_mod` : le CANAL d'arrivée.
* `engine/services/damage_modifiers.py` — `DamageModifiers.multiplicative` (déjà déclaré, **jamais
  alimenté**) et `multiplicative_defender` ; `add_modifier` route les `from_stat_mod` vers le premier ;
  `calculate_modifiers_from_stat_modifications` pose le drapeau ; `apply_all_modifiers` consomme les
  deux étages MULTIPLICATEUR (no-op strict à `1.0`).
* `engine/services/damage_prediction.py` — `apply_pierce_and_modifiers` joue **UNE seule chaîne**
  (`pct_list` puis `pct_list_defender`), puis les deux `CalculateBaseDamageWithModifiers`.
* `engine/runner/operations/damage.py` — `_apply_defender_flat_reductions` **déplace** aussi la
  `%-list` et le `Multiplier` du défenseur dans l'accumulateur attaquant (et vide la source), pour que
  le COMBAT n'ait plus qu'une chaîne. Il le faisait déjà pour `flat_reductions` et `extra_pierce`.
* `engine/playbook/prediction/_shared.py` — le `Multiplier` défenseur (stat-mods + auras) suit.
* `engine/playbook/prediction/normal_attack.py` — `meta["mult_att"]`/`["mult_def"]`.

## 4. Mesure du fix

| | avant | après |
|---|---|---|
| `test_terrifying_defense_live.py` | 1 failed, 4 passed | **5 passed** |
| per-coup live/offline | `[433,402,434,378,350,403]` vs `[434,…]` | **identiques**, PV cible `4623` = live |
| bornes du coup | `304 / 456` | **`305 / 457`** = natif |
| balayage d'armure (12 bornes) | 5/12 | **12/12** |
| deux faces non neutres (2 bornes) | 0/2 (`762 / 1142`) | **2/2** (`761 / 1141`) |
| `probe_446_r2_base_min_residual.py` | 30 couples, 0 DIFF | **30 couples, 0 DIFF** |

## 5. Contre-épreuves — critère = déplacement du port NON MUTÉ

`probe_462_r4a_terrifying_rounding.py --mutants` (offline, les six régimes ci-dessus). Les modèles
alternatifs sont ÉCRITS, pas monkeypatchés : l'arbre réel n'est jamais touché, et son intégrité est
revérifiée en fin de course.

| mutant | déplace | pire |
|---|---|---|
| `round_inter` (la séquence de `master`) | **4/6** | `terrifying` `305 -> 304`, `deux faces` `761 -> 762` |
| `statmod_pct` (stat-mods remis dans la `%-list`) | **1/6** | `446r2 T` `434 -> 433` |

Les deux mutations sont nécessaires : la première seule laisserait passer une régression du canal
MULTIPLICATEUR, la seconde seule une régression de la chaîne.

## 6. Ce qui n'est PAS couvert — résidus NOMMÉS

* **`#462-r4a-r1` — le décompilé de `DamageModifiers$$Add` route en APPARENCE les DEUX canaux vers
  `Multiplier@0x30`.** La surcharge 2-ARGUMENTS (celle des effets) appelle bien
  `Add(this, modifier.Value)` quand `damageBonus@0x20` a une valeur, et cette surcharge écrit
  `Multiplier@0x30`. La MESURE (6 régimes, dont 2 à deux faces) établit pourtant que les %-list
  d'effets se composent SANS arrondi intercalé, donc qu'elles ne traversent PAS cet étage. Deux
  lectures restent ouvertes, et aucune n'est tranchée : (a) le `damageBonus` d'un effet remplit en
  réalité `@0x48/@0x50` (l'entrée « capée » de la liste `@0x18`) et non `@0x20` — auquel cas
  `ApplyCappedModifiers` arrondirait PAR ENTRÉE, ce que le cran deux-faces réfute aussi ; (b) le
  décompilé Ghidra confond deux corps distincts sous le même symbole. **Canal qui trancherait** : lire
  le `Nullable<DamageBonus>` rendu par le slot `0x1a` d'un effet, champ par champ, à l'exécution — le
  RPC `readDamagePredictionResult` (`frida/hooks/game/damage-prediction.ts`) ne l'expose pas ; il
  faudrait un capteur sur `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$
  CreateEffectDamageBonusForAttack` (retour, 0x58 octets). **CONFRONTÉ le 2026-08-04 (§8.5) : la
  lecture (a) est RÉFUTÉE pour ce chemin** — le `damageBonus` d'un effet ne porte aucun
  pourcentage ; le multiplicateur arrive par le 3ᵉ argument `modifier` et atterrit dans
  `Multiplier@0x30`. Le fix de §3 reste juste EN VALEUR, mais par équivalence algébrique en
  régime sans `cap` (résidu `#462-r4a-r1-r1`).
* **`attackModifiers` est un `Nullable` MIS À ZÉRO dans `CalculateAbilityDamage`** (lu : les 0x40
  octets sont écrasés juste avant l'appel), alors que `PredictAttackRaw` construit ses DEUX `Nullable`
  (`Nullable<>..ctor` × 2, aux deux call-sites). Les deux appelants du même foyer ne traversent donc
  PAS les mêmes étapes. Le port n'a qu'UNE chaîne pour les deux (il modélise « bornes réduites puis
  tirage »), et cette fusion reste **bit-exacte sur tout le corpus mesuré** — mais elle n'est pas le
  mirror littéral de la structure d'appel. Non exploité ici ; à rouvrir si un régime la sépare.
* **La liste CAPÉE `@0x18` n'a toujours aucun canal propre côté port** (résidu `#446-r2-r1`, inchangé) :
  aucun `EffectBonus` porté ne pose de `cap`, donc `Clamp` n'est jamais exercé.
* **La face ATTAQUANT des modifications de stat** reste gatée `apply_stat_mod_debuff=False` (#49) : le
  canal `multiplicative` de l'attaquant existe désormais mais **aucun producteur ne l'alimente**. Sa
  branche de code (`étape 3` avec un multiplicateur non neutre) est donc **NON CONFRONTÉE** ; canal
  qui la confronterait : ouvrir le gate #49 sur un porteur mesuré, ou trouver un effet ATTAQUANT dont
  le natif passe par `Multiplier@0x30`.
* **Le capteur manquant hérité de #446-r1** : `IndividualHitDamage@0x80` n'est pas exposé par
  `readDamagePredictionResult`. Il aurait donné la décomposition par coup en UNE mesure au lieu d'un
  balayage.

## 7. Livré

* `scripts/python/probe_462_r4a_terrifying_rounding.py` — décomposition par étage (Fix64 exact),
  balayage d'armure (`--sweep`), cran DEUX FACES (`--two-faces`, unités déplacées), contre-épreuves
  (`--mutants`).
* `scripts/python/engine/services/{effect_bonus,damage_modifiers,damage_prediction}.py`,
  `.../runner/operations/damage.py`, `.../playbook/prediction/{_shared,normal_attack}.py`.
* `scripts/python/tests/engine/test_446_r2_inter_face_rounding_offline.py` — les DEUX crans neufs
  (`test_effet_defenseur_reste_dans_la_meme_chaine`,
  `test_chaine_unique_quand_les_deux_faces_sont_non_neutres`). Les montages de #446-r2 y posent
  désormais leur `x1.50` dans le canal `Multiplier` ; **les bornes natives attendues (434 / 650 / 433)
  sont inchangées**.
* `scripts/python/probe_446_r2_base_min_residual.py` et
  `.../tests/engine/test_446_r2_inter_face_rounding_live.py` — leur diagnostic lisait la face
  défenseur dans la seule `%-list` et rendait, depuis le fix, une chaîne AMPUTÉE du `x1.50` d'une
  tuile Thorns (faux signal). Ils lisent maintenant les deux canaux.

## 8. `#462-r4a-r1` — le capteur, écrit (#466), **CONFRONTÉ le 2026-08-04** (§8.5)

Les §8.1-8.4 sont la RE et le plan d'**avant** la fenêtre, **conservés tels quels** : c'est ce qui
rend lisible ce que la mesure a réfuté. La mesure et ses conséquences sont en **§8.5**.

### 8.1 Ce que le décompilé tranche déjà — la lecture (a) est CORROBORÉE

`IdunBattle.Core.Services.DamageModifiers$$Add(this, damageBonus, modifier)` — la surcharge
2-ARGUMENTS, celle des effets — relue verbatim sur `rnca9r7q6c` le 2026-08-04 :

```csharp
if (modifier.HasValue)            Add(this, modifier.Value);      // -> Multiplier@0x30 *= v
if (damageBonus.@0x28.HasValue)   this.@0x10 += Fix64(v);         // ADDITIF
if (damageBonus.@0x30.HasValue)   this.@0x10 -= Fix64(v);         // SOUSTRACTIF
if (damageBonus.@0x48.HasValue) {                                 // POURCENTAGE + CAP
    entry = { One + PctMultiplier(@0x48.Value), Fix64(@0x50.Value) };
    this.@0x18.Add(entry);                                        // -> LISTE CAPÉE
}
if (touched) this.@0x38.Add(damageBonus);                         // traçabilité
```

Le `Multiplier@0x30` n'est touché **que** par l'argument `modifier` (le troisième), jamais par un
champ du `damageBonus` ; un **pourcentage** porté par le `damageBonus` part dans la **liste capée
`@0x18`**. C'est exactement la lecture (a), et elle explique la mesure de §2 sans arrondi
intercalé. La lecture (b) — « Ghidra confond deux corps » — n'a plus de motif : les deux
surcharges se distinguent par leur **compte d'arguments** (`Add(damageBonus, modifier)` vs
`Add(modifier)`), et la 1-argument est un `Multiplier *= modifier` sec.

Le rédigé de §6 disait « quand `damageBonus@0x20` a une valeur » ; la relecture montre que le test
porte sur le **paramètre `modifier`**, pas sur `@0x20`. L'apparente contradiction du résidu vient
de là.

### 8.2 CE QUE ÇA NE SUFFIT PAS À CONCLURE — et pourquoi le capteur reste nécessaire

Le **même `DamageBonus` peut alimenter les DEUX canaux selon l'APPELANT**. Dans
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`, un champ de
pourcentage est converti par
`IdunBattle.Core.Services.BaseCalculations$$GetFloatMultiplierFromPercentage` puis passé **comme
troisième argument** (`modifier`) — donc vers `Multiplier@0x30`, l'étage arrondi. Savoir « ce que
la fabrique produit » ne dit donc RIEN sans savoir « où l'appelant le verse ». C'est le nœud, et
aucune lecture statique ne le referme : il faut voir les deux **sur le même événement**.

⚠ Deuxième raison, structurelle : `CreateEffectDamageBonusForAttack` couvre **107 corps** dans
`frida/methods.tsv` (un par effet concret) et rend un `System.Nullable<IdunBattle.Entities.Effects
.EffectBonus>` — pas un `DamageBonus`. Le symbole nommé par le résidu est le **forwarder** de la
classe de base ; un effet qui surcharge ne passe pas par lui. Un capteur posé là **seul** peut donc
ne jamais tirer sur l'effet mesuré.

### 8.3 Ce qui est livré — `frida/hooks/features/effect-bonus-trace.ts`

Trois ancrages, tous résolus RUNTIME (aucune RVA en dur) :

| # | cible | ce qu'elle apporte |
|---|---|---|
| 1 | `DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack` | la FABRIQUE nommée par le résidu : les 0x58 octets du `Nullable<EffectBonus>`, la classe CONCRÈTE de l'effet, et quels slots sont occupés |
| 2 | `DamageCalculations$$Calculate{Attacker,Defender}ModifiersForPrediction` (toutes surcharges) | **ÉTIQUETTENT la face** — c'est la réponse directe au résidu. Pile de faces : les deux s'imbriquent, et un `onLeave` qui viderait la pile effacerait la face englobante. Hors fenêtre ⇒ `face: null`, jamais une face devinée |
| 3 | `DamageModifiers$$Add`, **les deux** surcharges | le CANAL D'ATTERRISSAGE : accumulateur lu AVANT et APRÈS (`additive@0x10`, count de la liste capée `@0x18`, `Multiplier@0x30`, `@0x38`). Le canal se **lit**, il ne se déduit pas. Voit TOUS les effets, quel que soit leur corps concret — c'est ce qui couvre le trou de §8.2 |

**Trois niveaux de publication, par ordre de fiabilité** : `rawHex` (les octets — aucune
interprétation ne peut les fausser), `fields` (le layout NOMMÉ lu au runtime, l'arbitre), `guess`
(l'interprétation best-effort, étiquetée HYPOTHÈSE). Conséquence opérationnelle : **une
interprétation fausse se corrige côté Python, sans seconde fenêtre.** Les slots d'`EffectBonus`
sont déduits de l'ABI des fabriques statiques (`ForAddition` écrit `@0x10`, `ForPercentIncrease`
`@0x08`, `ForSubtraction` `@0x18`, `ForOverride` `@0x28`, chacune zérotant les autres) — c'est
une hypothèse, et le capteur le dit. Les `Nullable<int>` sont publiés dans **les deux ordres de
champ** (`has_value`-first et `value`-first) : ce dépôt documente les deux, et ce capteur ne
tranche pas à l'aveugle.

**Discipline** : `DamageModifiers$$Add` est sur le chemin de dégât. Le `register` n'arme RIEN ;
armement on-demand par `effectBonusTraceOn`, sous **budget d'événements** (défaut 4000) qui éteint
la capture toute seule — un capteur oublié ne pèse pas sur une session partagée.
RPC : `effectBonusTrace{On,Off,Clear,Dump,Layout}`.

### 8.4 PLAN DE MESURE — ce que la fenêtre doit jouer, et ce que chaque résultat tranche

Prérequis : reinject + `autoBootExtraire({force:true})`. Montage = **celui de §2**, déjà écrit
et reproductible : `probe_462_r4a_terrifying_rounding.py --two-faces` (élévation `x1.50` côté
ATTAQUANT + effet `Terrifying` `x0.70` côté DÉFENSEUR, unités DÉPLACÉES vers un couple adjacent à
dénivelé, PV forcés à 90 000). C'est le seul régime où les deux faces sont non neutres, donc le
seul qui sépare les canaux.

Séquence : `effectBonusTraceLayout` → `effectBonusTraceOn {budget: 2000}` → jouer le montage →
`effectBonusTraceDump {runnerId}` → `effectBonusTraceOff`.

| # | mesure | résultat attendu | ce qu'un ÉCART trancherait |
|---|---|---|---|
| 0 | `effectBonusTraceLayout` : `EffectBonus`, `DamageBonus`, `DamageModifiers` | offsets nommés == `assumedOffsets` | tout écart invalide `guess` et les champs interprétés des mesures 1-5 — **le corriger côté Python AVANT de lire quoi que ce soit d'autre** ; les `rawHex`, eux, restent exploitables |
| 1 | `adds` : chaque `Add` porte-t-il une `face` non nulle ? | oui pour ceux de la prédiction | `face: null` en masse ⇒ le chemin emprunté n'est pas `Calculate*ModifiersForPrediction` (combat plutôt que prédiction) : **c'est une information, pas une panne** — ré-ancrer sur le chemin combat |
| 2 | **l'`Add` qui porte le `x0.70` de `Terrifying`** : `pct` HasValue ? `cappedAfter == cappedBefore + 1` ? `multAfter == multBefore` ? | **oui / oui / oui** | c'est LE cran. Il confirme la lecture (a) **au runtime** : un pourcentage d'effet va dans la liste capée et NE touche PAS `Multiplier`. Si au contraire `multAfter != multBefore`, l'effet passe par le canal MULTIPLICATEUR et **le fix de §3 est faux** — la mesure de §2 serait alors expliquée autrement, à re-ventiler par étage |
| 3 | la `face` de cet `Add` | `"defender"` | `"attacker"` ⇒ l'attribution de face du port est inversée sur ce chemin ; `null` ⇒ cf. 1 |
| 4 | l'`Add` du `x1.50` d'élévation | `face: "attacker"`, même canal (liste capée) | canal MULTIPLICATEUR ⇒ l'élévation est un stat-mod déguisé, ce que §2 cran 3 avait attribué au canal et non à la face — **à re-trancher** |
| 5 | `overload: 1` (`Add(modifier)`) : apparaît-il, et sur quelle face ? | présent sur le montage `T` (tuile Thorns), `multAfter != multBefore` | absent partout ⇒ le canal `Multiplier` n'est alimenté par AUCUN chemin porté, et le résidu « face ATTAQUANT des stat-mods NON CONFRONTÉE » (§6) reste entier |
| 6 | `factory` : l'événement de fabrique tire-t-il pour `Terrifying` ? | **peut-être pas** — cf. §8.2 | s'il ne tire pas, ce n'est PAS un échec : l'ancrage 3 a déjà tranché. Le noter comme « effet à corps propre », et lire `effectBonusTraceLayout.damageModifierAbilityEffectChain` pour savoir quels effets passent par le forwarder |

**Ce qui restera NON COUVERT même après la fenêtre** : la face ATTAQUANT des modifications de stat
(gate `apply_stat_mod_debuff=False`, #49 — aucun producteur ne l'alimente, donc l'étage 3 à
multiplicateur non neutre reste non confronté sauf à ouvrir le gate), la liste capée exercée avec
un `cap` réel (`#446-r2-r1` : aucun `EffectBonus` porté ne pose de `cap`, donc `Clamp` n'est jamais
exercé — la mesure 2 lira le `cap` natif et dira s'il est seulement non nul), et
`IndividualHitDamage@0x80`, toujours non exposé par `readDamagePredictionResult`.

### 8.5 LA MESURE — jouée le 2026-08-04, session 3, build `rnca9r7q6c`

`probe_462r4ar1_effect_bonus_channel_live.py --wide`, montage `--two-faces` de §2 (natif
**761 / 1141**, port idem). **Le canal TRANSPORTE : 693 `Add` captés.** Et il **réfute le cran
central**.

| # | attendu (§8.4) | obtenu | ce que l'écart tranche |
|---|---|---|---|
| 0 | offsets nommés == `assumedOffsets` | **concordance EXACTE des 8 constantes**, une fois l'en-tête de boxing retiré | cf. « le faux écart de 0x10 » ci-dessous |
| 1 | face non nulle sur les `Add` de la prédiction | **693/693 portent une face**, 0 `null` — mais **100 % `attacker`, 0 `defender`** | **INDÉCIDABLE** — cf. ci-dessous |
| **2** | `pct` HasValue **oui** / `cappedAfter == cappedBefore+1` **oui** / `multAfter == multBefore` **oui** | **non / non / non** : `pct` jamais renseigné, la liste capée **ne grossit sur AUCUN des 693**, le `Multiplier` bouge sur **276** | **RÉFUTÉ.** Les pourcentages de ce montage passent par le canal MULTIPLICATEUR |
| 3 | face de cet `Add` == `"defender"` | `"attacker"` | même indétermination que 1 |
| 4 | `x1.50` d'élévation : `attacker`, **même canal** que l'effet | `attacker`, **même canal** — et **même accumulateur** | « même canal » **confirmé**, mais c'est le MULTIPLICATEUR, pas la liste capée |
| 5 | `overload: 1` présent **sur le montage `T`** (tuile Thorns) | **138 événements, SANS aucune tuile Thorns** | le résidu « le canal `Multiplier` n'est alimenté par AUCUN chemin porté » est **fermé par la négative** |
| 6 | la fabrique « peut-être ne tire pas » | **0 événement** | **exactement le trou nommé d'avance** (§8.2) : le symbole est le forwarder de la base, l'effet a un corps propre |

**Ce que la mesure montre, en une ligne** : sur un **même accumulateur**, la surcharge
1-argument applique `x0.6999999999534339` (`Terrifying`) **puis** `x1.5` (élévation) —
`1 -> 0.6999999999534339 -> 1.0499999998137355`. Les deux faces alimentent **UN SEUL**
`Multiplier@0x30`, donc **UN SEUL** étage `CalculateBaseDamageWithModifiers`, donc **UN SEUL**
`Round`. C'est `fusionne_1_round`, et c'est exactement ce que le natif rend (761 / 1141 contre
762 / 1142 pour tout ordre à deux arrondis).

**Le fix de §3 rend les bonnes valeurs par le mauvais chemin.** Le port range les %-effets dans
`pct_list`/`pct_list_defender` (composés sans arrondi, puis un `Round`) ; le natif les range dans
`Multiplier` (composés sans arrondi entre eux, puis un `Round`). **Algébriquement identiques
tant qu'aucun `cap` n'entre en jeu** — et `#446-r2-r1` établit qu'aucun `EffectBonus` porté n'en
pose. La mesure le confirme **côté natif** : `pct`/`cap` du `DamageBonus` ne sont renseignés sur
**aucun** des 693 événements, la liste capée reste à `0`. C'est donc un **accord en régime
dégénéré** : les deux modèles ne se sépareront que le jour où un `cap` réel apparaîtra, ou qu'un
producteur versera dans la liste capée. **Résidu `#462-r4a-r1-r1`** — le port n'est pas faux sur
le corpus mesuré, il est *juste pour une autre raison que celle écrite*, et §6/§8.1 doivent se
lire ainsi : la lecture (a) (« un pourcentage d'effet part dans la liste capée `@0x18` ») est
**réfutée pour ce chemin**. Le `damageBonus` n'y porte pas de pourcentage du tout — le
multiplicateur arrive par le **3ᵉ argument** `modifier`, et la surcharge 2 **délègue** alors à la
surcharge 1 (`if (modifier.HasValue) Add(this, modifier.Value)`), ce que la trace montre par
l'imbrication des `seq` (l'appel interne sort avant l'englobant).

**Preuve que la lecture est JUSTE, et non plausible** : `multAfter == multBefore x modifierValue`
sur **138/138** événements de la surcharge 1. Une valeur lue au mauvais offset ne satisferait pas
cette identité.

**Reproductibilité — trois passes, dont une APRÈS rebase sur `origin/master`** (21 commits
absorbés). Le VOLUME varie avec le placement (693, 693, **282** `Add` ; 138, 138, **36** de la
surcharge 1) ; les **valeurs** ne varient pas : `0.7` puis `1.5`, `1 -> 0.6999999999534339 ->
1.0499999998137355`, cohérence multiplicative **100 %** à chaque passe, liste capée à `0` sur
tous les événements des trois passes, `factory = 0`. Le volume n'est pas la mesure — les
transitions le sont.

⚠ **Le rebase a fait tomber le montage, et c'était un vrai signal.** `#437-r1` a ajouté le
paramètre `separate_face_lists` à `apply_pierce_and_modifiers` ; l'enveloppe d'observation
`_instrument()` du probe hôte figeait la signature de sa cible et levait un `TypeError` — alors
que le signal observé n'avait pas bougé d'un chiffre. Corrigé : les deux enveloppes prennent
`**kw` et le **repassent** tel quel. Une enveloppe d'observation ne doit jamais figer la
signature de ce qu'elle observe.

**Preuve que le régime n'est PAS dégénéré** : **4 accumulateurs distincts** portent **deux**
multiplicateurs de valeurs différentes (`0.7` et `1.5`) composés l'un après l'autre. Le produit
(`1.05`) diffère de chacun des facteurs, donc la mesure sépare « un seul terme » de « deux termes
composés » — et sépare la composition sans arrondi de la composition avec. Un montage à une seule
face aurait rendu le même `PASS` sans rien établir.

**Le faux écart de `0x10` (cran 0), et pourquoi il valait d'être publié.** `field_get_offset`
rend l'offset dans la représentation **BOXÉE** ; les constantes du capteur sont ceux de la struct
**NUE**, celle qu'un `ValueType` passé par pointeur présente aux `Add`. Lues côte à côte, les
deux séries semblent toutes décalées. Elles concordent **exactement** à `-0x10` près :

| struct | champ déclaré (boxé) | nu | constante | |
|---|---|---|---|---|
| `DamageModifiers` | `Addition@0x20` | `0x10` | `DM_ADDITIVE` | OK |
| | `CappedModifiers@0x28` | `0x18` | `DM_CAPPED_LIST` | OK |
| | `Multiplier@0x40` | `0x30` | `DM_MULTIPLIER` | OK |
| | `DamageBonusesForInfo@0x48` | `0x38` | `DM_BONUS_LIST` | OK |
| `DamageBonus` | `Addition@0x38` | `0x28` | `DB_FLAT_PLUS` | OK |
| | `Subtraction@0x40` | `0x30` | `DB_FLAT_MINUS` | OK |
| | `CapModifier@0x58` | `0x48` | `DB_PCT` | OK (son vrai nom est `CapModifier`) |
| | `Cap@0x60` | `0x50` | `DB_CAP` | OK |

Et les **quatre slots d'`EffectBonus`** que §8.3 étiquetait HYPOTHÈSE sont **confirmés** par les
noms déclarés : `Multiplicator@0x08`, `Addition@0x10`, `Subtraction@0x18`, `Override@0x28` (nus).
`DAMAGE_BONUS_BYTES = 0x58` est la taille nue exacte (`Cap@0x50` + 8). Le capteur annote
désormais les deux référentiels (`nakedFields`, `isValueType`) — **non déployé**.

**Ce que la mesure ne peut PAS trancher, et pourquoi (cran 1/3).** `0 defender` sur 693 admet
deux lectures incompatibles : *(a)* la fenêtre défenseur n'est pas traversée sur ce chemin,
*(b)* son hook n'a pas été posé. Rien de ce que le capteur publiait ne les sépare. Le décompilé
ne referme pas non plus : `CalculateDefenderModifiersForPrediction` **existe en 2 surcharges**
(la 2-paramètres appelle la 3-paramètres) et **appelle bien `DamageModifiers$$Add`**, mais ses
deux corps n'ont **aucun appelant `CALL` direct** — que des références DATA, donc appel indirect
par `MethodInfo` — et `CalculateAttackerModifiersForPrediction` est dans **exactement le même
cas**. L'asymétrie observée n'est donc explicable ni par l'arité ni par les xrefs. **NON
CONFRONTÉ**, et le capteur est corrigé pour que la prochaine fenêtre tranche : `facesPosed`
(quelles surcharges ont reçu un `attach`, avec arité et pointeur) et `faceEnters` (combien de fois
chaque fenêtre est franchie, **indépendamment de tout `Add`**). **Résidu `#462-r4a-r1-r2`.**

> ✅ **`#462-r4a-r1-r2` FERMÉ le 2026-08-04, sans seconde fenêtre** (#437-r1-r1). Le même capteur,
> **même bundle**, armé sur le montage de #437-r1 (`probe_437r1_overwatch_offbyone.py --channel`)
> rend **20 événements `face: "defender"`** (`TerminatorArmour_ReduceDmg`, `x0.25`) à côté de ses
> `face: "attacker"`. Le hook défenseur **est** posé et il **tire** : le `0 defender` ci-dessus
> n'est donc pas une panne de capteur, c'est **une mesure** — sur le montage à deux faces, le natif
> verse `Terrifying_ExtraDefense` dans l'accumulateur **ATTAQUANT**. C'est ce qui explique le
> `1 -> 0.6999999999534339 -> 1.0499999998137355` sur un seul accumulateur, et donc le `Round`
> unique. Détail et conséquences : `docs/rl/case-437-r1-r1-canal-et-face.md`.

**Un fait de portée générale, mesuré au passage** : `aiPlaybookPredict` **ne traverse pas**
`DamageModifiers$$Add` — `adds` vaut **657 avant** l'appel et **657 après**. Les 693 événements
viennent des `applyAction move` du placement (657) et de l'**attaque réelle** jouée en fin de
montage (36). C'est pour cela que la première passe, armée autour du seul `aiPlaybookPredict`,
a rendu **0 événement** : une fenêtre de capture correctement ancrée sur le point de mesure du
montage hôte, et pourtant **muette**. Le montage de §2 compare une prédiction native à un replay
offline ; il ne fait **jamais** jouer le chemin de dégât natif. Toute confrontation ultérieure de
ce capteur doit donc jouer une **action réelle** (`--wide`), sans quoi elle conclura à tort que le
canal est mort. **Résidu `#462-r4a-r1-r3`** : par où `aiPlaybookPredict` calcule-t-il ses bornes,
si ce n'est par `DamageModifiers$$Add` ? Non instruit ici.

**Le layout du `Nullable<int>` est tranché** : sur les 6 événements qui bougent `Addition`,
`flatPlus` lu `has_value`-first rend `898` et `addAfter` vaut `898` ; l'ordre `value`-first
rendrait `130`. ⇒ **`has_value` en tête, valeur à `+4`**. Le capteur publiait les deux ordres
sans trancher ; c'est la mesure qui le fait.
⚠ En revanche `modifierHasValue` valait **`51`** sur 30 événements : l'octet `@+8` du
`Nullable<Fix64>` **n'est pas** son `has_value` sur ce build. Corrigé en tri-état (hors `{0,1}`
⇒ `-1` = « pas mesuré ») plutôt que publié sous un nom qui promet un booléen. Sans effet sur les
conclusions : la question se tranche par la délégation à la surcharge 1.
