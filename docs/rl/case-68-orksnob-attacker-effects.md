# Case study #68 : effets de degat ATTAQUANT d'orksNob (SmashaEad + BeastSlayer)

Build `gqfc5mff6c`. Ground truth mesuree 2026-07-08 (replay-diff orksNob 1v1 + RE ghidra). GREP ce
fichier avant de re-investiguer #68.

## Contexte : ce que la game applique reellement

`decisionView.effects` sur orksNob (Tanksmasha) au moment de l'attaque =
`[BeastSlayer_ExtraDmg, BeastSlayer_ExtraBlock, SmashaEad]`.

Le runner offline **seed ses effets depuis ce snapshot** (`load_state` -> `EffectFactory.create_many`
depuis `decisionView.effects`, avec `activeAbilityLevel`) — donc PAS besoin de porter les triggers de
CREATION d'effet pour le replay (l'etat live est charge tel quel). Il faut juste que la CLASSE d'effet
soit portee + enregistree dans `factory.py`, et que sa magnitude/condition soient fideles.

## SmashaEad — PORTE (#69)

`SmashaEadEffect.CreateEffectDamageBonusForAttack @180f6bee0` = `EffectBonus.ForAddition(OwnerIsCaster
& IsNormalAttack, ConfigVar(8=extraDmg))`. Additif PLAT, canal `additive @+0x10`, **POST-percage**
(cf. #69 : DamageModifiers.Add @181005f10 -> CalculateBaseDamageWithAllModifiers @18102d3f0). Classe
`SmashaEadExtraDamageEffect` (loki.py) = `for_addition(extraDmg[activeLvl] x mult)`. Magnitude :
`extraDmg` in variablesAffectedByRarityBonus (scale par mult) ; array VA jusqu'a L50 (`extraDmg[50] x
mult180 = 599`, PAS 41 : l'hypothese '14 niveaux clamp 23' etait FAUSSE).

**RESOLU #71 (verdict re-expert + fix valide)** : la sur-prediction venait du trigger natif de SmashaEad
`ForAddition(OwnerIsCaster & IsNormalAttack, ...)` (@180f6bee0). Le noeud DSL **`IsNormalAttack` evalue
FALSE dans le contexte PREDICTION DISPLAY** (RapidAssault, trigger `OwnerIsCaster` SEUL, evalue TRUE ->
matche). Le port avait collapse le AbilityTrigger en un bool `owner_is_caster` sans porter `IsNormalAttack`.
FIX : flag `is_prediction` threade dans le funnel attaquant ; `calculate_attacker_modifiers_for_prediction`
passe `is_prediction=True` -> `SmashaEadExtraDamageEffect.create_effect_damage_bonus_for_attack` renvoie
None (additif absent de la prediction, matche le DISPLAY) ; `build_attacker_modifiers_from_effects`
(COMBAT) garde `is_prediction=False` -> additif applique. Gate SPECIFIQUE a SmashaEad (seul effet dont
le trigger natif contient IsNormalAttack ; RapidAssault/FightingRetreat = OwnerIsCaster seul, non gates).
VALIDE : deterministe off_avec == off_sans == (964,1448) ~= oracle (948,1311) [avant : off_avec=(1563,2047)] ;
test_predict_live 2/2 (RapidAssault matche) ; combat armored/ability 2/2 (is_prediction=False, SmashaEad
reste en combat). Chemin #64 (debuff stat-mod) = branche separee, non touchee.

**MAJ 2026-07-09 (GetStuckIn combat porte => confond LEVE) — DIAGNOSTIC : MAGNITUDE ~2x, PAS presence.**
Replay-diff orksNob->bloodIntercessor (cible NON-Big, seed 4242, per-hit) en isolant la contribution SmashaEad :
- `off_SANS_SmashaEad` = [1240,1438,1226]
- `live`              = [1540,1738,1526]  = off_sans **+ 300 CONSTANT**
- `off_AVEC_SmashaEad` (port, 599/coup) = [1839,2037,1825] = off_sans **+ 599**
(base=2411 ; effects offline=[BeastSlayer_ExtraDmg, BeastSlayer_ExtraBlock, SmashaEad]).
=> **le LIVE applique bien SmashaEad en combat (~+300/coup), le PORT applique ~+599/coup = ~2x trop grand.**
La 1re hypothese "SmashaEad absent en combat" (fix `return None`) etait FAUSSE : le fix a fait passer off SOUS
live (-300) => REVERT. L'ecart CONSTANT sur des coups a rolls DIFFERENTS => additif POST-reduction constant
(donc NI placement pre-percage — #69 reste valide — NI per-coup-vs-once — les deux sont per-coup). GetStuckIn
ECARTE (coup index 0 PAIR sans Maybe porte le meme offset ; l'ecart constant a travers la frontiere Maybe
PROUVE le bon positionnement du tirage, cf. case-62c). RESTE #68 = **RE de la VALEUR** : `extraDmg` (array
gameconfig) x `ability_variables_multiplier` x niveau (`active_ability_level`) -> pourquoi 599 vs ~300 live
(facteur ~2 : multiplier double-applique ? mauvais niveau ? confusion extraDmg/extraDmg_2 ?). Corriger la
valeur => off==live => test xfail `test_getstuckin_combat_absolute_bit_exact` xpass. `IsNormalAttack`
(= `IsRegularAttack(ability declenchante)` @180f8d260/@181555b40) = FALSE sans contexte d'ability (explique
l'absence en PREDICTION display #71), mais en COMBAT SmashaEad EST bien applique (presence confirmee).

**RESOLU (RE re-expert, bit-exact) : le bug = le MULTIPLIER (180 au lieu de 90).** Formule native PROUVEE :
additif = `round(extraDmg[level-1] x multiplier/100)` (ConfigVar(8)@180f6bee0 -> ConfigAmount.Calculate@180f171c0
-> GetVariableForLevel@181576fb0 -> TryGetVariableArrayForLevel@181577510 ; index=level-1 @181565ce0 ; multiplier
applique SSI var in variablesAffectedByRarityBonus, lu = `AbilityState+4`). level=50/extraDmg[49]=333/index :
tous CORRECTS. SEUL le multiplier est faux : le port prend `self.ability_variables_multiplier=180` (UnitConfig
+0x74 = multiplier de l'ability PRIMAIRE/active) ; or la TRIGGERED SmashaEad a son PROPRE multiplier par-ability
= **90** (`GetAbilityVariablesMultiplierPercentage(abilityId)@181696230` est PAR-ABILITY : +0x24 ou +0x2c selon
appartenance liste). `round(333x0.9)=300` = live EXACT ; `round(333x1.8)=599` = port. Ce multiplier par-ability
des triggered N'est capte par AUCUN champ actuel (combatSnapshot = UnitConfig +0x74=180/+0x78=100, aucun=90) ->
fix FIDELE = nouveau capteur (tache #75) ; stopgap `mult/2` = coincidence non generalisee (a FLAGGER hardcode).

### CAPTURE RECIPE #75 (RE close 2026-07-09, chaine LUE integralement)

Ou vit le 90 au RUNTIME et comment le capter fidelement.

**1. Le multiplier est BAKE par-ability dans l'AbilityState.Level, PAS derivable d'un champ UnitConfig.**
`@181696230` (`UnitConfigUtil.GetAbilityVariablesMultiplierPercentageForProgressionIndex`, META/setup) lit sur
l'entree de progression de l'unite DEUX champs sur le MEME objet : `+0x24` (=180, "normal") et `+0x2c` (=90,
"rarity-bonus"). Le choix = `bVar2` = « la VARIABLE (param_4) est-elle dans `variablesAffectedByRarityBonus`
de l'ability (item+0x88) ? ». extraDmg y est -> 90. Ce resultat est BAKE dans le `Level.multiplier` de chaque
AbilityState au setup. => 90 n'est sur AUCUN champ battle UnitConfig ; l'unique source battle-time = l'AbilityState.

**2. Chaine battle-time (LUE) :** l'effet SmashaEad porte un `ConfigAmount` (ConfigVar(8=extraDmg)). Sa resolution :
`ConfigAmount.Calculate @180f171c0` -> `GetAbilityState @180f175a0` (resout l'AbilityState de l'ability SOURCE
via `UnitExtensions.GetAbilityState(unit, abilityType)`) -> le `Level{level@0, multiplier@4}` de cet AbilityState
-> `GetVariableForLevel @181576fb0` -> `TryGetVariableArrayForLevel @181577510` : applique `Round(raw x Level+4/100)`
SSI la variable in `AbilityConfiguration+0x28` (=`variablesAffectedByRarityBonus`). Donc **`Level.multiplier` (=+4
du struct Level) = 90 pour la triggered SmashaEad**.

**3. `UnitExtensions.GetAbilityState(unit, abilityType)` (LUE, 3 overloads) :**
- `@180eced70(out, unit, int abilityType)` = le resolveur COMPLET (le bon pour SmashaEad) : `GetActiveAbilityUsedForConfig(type)`
  -> sinon `TriggeredAbilityComponent.TryGetAbility(type)` (l'instance triggered porte le Level a +0x20/+0x24/+0x28
  = level/multiplier/rarity) -> sinon `GetTriggeredAbilityUsedForConfig`. Retour = Nullable<Level> (16 o) dans `out`.
- `@180ecea30(out, unit, int)` = enumere SEULEMENT la collection ActiveAbility (component+0x20 ; ActiveAbility.type@+0x44 ;
  `get_AbilityState`) -> RATE les triggered. NE PAS utiliser pour SmashaEad.
- `@180ecec80(out, unit, AbilityType*)` = variante prenant un objet AbilityType.

**4. IDs :** SmashaEad = TriggeredAbilityType **1246** (`triggered-ability-names.ts`) ; EffectType SmashaEad = **1319**
(`effect-type-names.ts`). L'effet 1319 est cree par l'ability triggered 1246 -> c'est le multiplier de 1246 qu'il faut.

**5. Plan capture (frida) :** par unite, exposer `abilityMultipliers: {abilityName -> Level.multiplier}` en appelant
`invokeMethod(GetAbilityState@180eced70, null, [unitPtr, ptr(int abilityType)])` (retour boxe -> struct @+0x10 ;
`multiplier = boxed+0x14`, `level = boxed+0x10`) pour chaque ability du kit (actives via ActiveAbilityComponent +
triggered via TriggeredAbilityComponent/nom-enum). Overload a DESAMBIGUER live (prendre `@180eced70`, param_3=int
TriggeredAbilityType). **Wiring offline** : `snapshot.py` lit `unitConfig.abilityMultipliers` -> `ctx.ability_multipliers`
(dict) ; `EffectFactory.create` passe le multiplier par-effet quand connu ; `SmashaEadExtraDamageEffect` fait
`mult = ctx.ability_multipliers.get("SmashaEad", self.ability_variables_multiplier)`. **Valider** : xpass
`test_getstuckin_combat_absolute_bit_exact` (off==live) + un 2e triggered a rarete/niveau different (prouver la
capture, pas un /2).

### VERDICT RECONCILIE #68/#75 (2026-07-09, hint terrain/elevation user) — c'est le MULTIPLIER RARITY par-ability (90), PAS l'elevation NI un /2 downstream

Enquete terrain/elevation (hint user "c'etait un trigger qui modifiait les degats") + RE combat -> dossier clos :
- **ELEVATION ECARTEE (preuve arithmetique + decompile).** `CalculateElevationBonusModifier @181003ea0`
  = %-leaf POSITIONNEL (ecrit un Nullable pct au slot `DamageModifiers+0x20` SSI tuiles d'elevation
  differentes ; coupe si attaquant OU cible porte l'effet 0x423). PAS un trigger, PAS flat. Un % NE PEUT
  PAS produire l'ecart FLAT constant +300. Et comme `live = off_sans + 300` EXACT et constant sur des
  coups a rolls DIFFERENTS, TOUS les etages non-SmashaEad (base/pierce/armure/**ELEVATION**/crit) matchent
  DEJA dans off_sans -> l'elevation (et tout terrain) n'est pas le delta. (Le hint pointe le bon TYPE de
  mecanisme — un trigger — mais le bon trigger est SmashaEad lui-meme, ability TRIGGERED 1246, pas l'elevation.)
- **COMBAT ne resout PAS l'additif via `DamageBonusForAttack`/`GetVariableForLevel`** (0 fire combat).
  `AttackDamageOperation.ExecuteHit @180e5eff0` calcule le degat par des appels de service INTERFACE-dispatches
  (`DAT_183287ef8`, slots +0xb/+4/+8/+0xac = crit/block/armure/bonus) ; `HitDamage.GetDamage` ne rend que la
  base {2411,2411}. L'additif effet passe par CE service (chemin DISTINCT de la prediction).
- **VRAIE CAUSE (LOGIQUE LUE @181696230 `GetAbilityVariablesMultiplierPercentageForProgressionIndex`)** :
  pour une variable dans `variablesAffectedByRarityBonus` (extraDmg L'EST -> `bVar2=true` via Contains sur
  `ability+0x88`), le multiplier = progression entry **`+0x2c` (RARITY)**, sinon `+0x24` (normal). Fonction
  META/setup (bake le `Level.multiplier` de l'AbilityState au roster). orksNob SmashaEad : +0x24=180,
  +0x2c=90 (mesure prior). => additif combat = `round(333 x 90/100) = 300` = live EXACT. Le PORT applique
  180 (mult unit-global `ability_variables_multiplier`) a TOUS les additifs -> 599.
- **"/2 DOWNSTREAM" (hypothese MESURES DEFINITIVES ci-dessous) REFUTEE par le SEPARATEUR u90 PowerTrip** :
  son additif matche a 180 SANS /2 (rarity==normal==180 pour u90). Un /2 combat UNIVERSEL halverait aussi
  u90 -> faux. Ce n'est PAS un /2 ; c'est que 90 = la moitie de 180 POUR CETTE unite/ability (rarity), une
  coincidence de ratio qui a fait croire a un /2. (Lecon : un facteur ~0.5 sur UN cas = hypothese ; le 2e
  cas qui SEPARE tranche. cf. CLAUDE.md.)
- **SOURCE DU 90 — ENCORE NON MESUREE DIRECTEMENT (attention)** : le `Level.multiplier` de l'instance
  triggered a DEJA ete lu live = **180** (section REFUTATION plan-5 ci-dessous), et `GetVariableForLevel`
  resout a 180 -> 599 (MESURES). Donc le 90 n'est NI sur l'instance triggered NI sur la resolution
  prediction. L'hypothese P1 (RE, non confirmee live) : le 90 vit dans le **Level CACHE du ConfigAmount
  PROPRE de l'effet** (`ConfigAmount+0x20`, bake a la creation par `CreateEffectDamageBonusForAttack` avec
  le rarity `+0x2c`=90 de @181696230). Hypothese P3 concurrente NON ecartee par u90 : l'additif SmashaEad
  serait un **ExtraMaxDamage** (canal MAX seul) -> midpoint per-coup n'en reflete que ~la moitie. **u90
  separe P2(/2 universel) mais PAS P1 vs P3.**
- **FIX FIDELE (capture) — LA SONDE JAMAIS POSEE** : lire, LIVE, l'additif au SITE DE RESOLUTION COMBAT
  (dans `ExecuteHit`/le service interface-dispatche) : (a) la VALEUR ajoutee par coup (300 ? 599 ?) et
  (b) son CANAL (additif plat @+0x10 vs ExtraMaxDamage @MAX). Ou, equivalent statique : lire le
  `ConfigAmount+0x20` cache de l'effet SmashaEad (P1 -> 90). UN de ces deux reads separe P1/P3 et donne la
  source fidele. `GetAbilityState(unit,1246)` (plan-5) = REFUTE (rend 180=active). Valider : xpass
  `test_getstuckin_combat_absolute_bit_exact` (off==live) + 2e triggered rarity!=normal.

### MESURE BACKTRACE DECISIVE (probe #75, 2026-07-09) — COMBAT NE RESOUT PAS l'additif ; il lit une valeur BAKEE a la creation

Sonde : hook `GetVariableForLevel @181576fb0` + BACKTRACE par fire (`modifier-observe`, champ `frames`),
classe COMBAT (chaine via `AttackDamageOperation.*` 0xe5e..0xe62) vs PREDICTION (via `DamagePrediction.*`
0x102..0x104). Attaque orksNob->bloodIntercessor (applyAction ability, RNG seede). Resultat :
- **3 fires extraDmg(id8), TOUS mult=180 -> 599, TOUS classes PREDICTION** (frames :
  `ConfigAmount.Calculate -> DamageBonusForAttack(0x2fe62) -> CalculateAttackerModifiers(0x1001061) ->
  DamagePrediction(0x103489e) -> MakeDamagePredictions(0x1054041)`).
- **0 fire classe COMBAT.** => **le COMBAT n'appelle JAMAIS GetVariableForLevel pendant le coup.**
=> **VERDICT (outcome C) : l'additif combat est une valeur BAKEE a la CREATION de l'effet** (ConfigAmount
resolu une fois avec le Level PROPRE de SmashaEad, mult rarity **90** -> ~300, mis en cache
`ConfigAmount+0x10`), que le combat LIT. La PREDICTION, elle, RE-resout frais via le Level de l'ability
ACTIVE (180 -> 599) — d'ou les 3 fires 180 et la sur-prediction #71 (gate display). **P1-tel-quel (combat
re-resout a 90) ET P3 (/2 aval) REFUTES** : combat ne re-resout pas du tout ; il lit le bake. Le PORT
recalcule `extraDmg x ability_variables_multiplier(180)` = 599 en combat au lieu de lire le bake (300).

**MAJ (probe arme AU DEBUT de bataille, 2026-07-09) — "MULT 90" REFUTE PAR MESURE ; hypothese P3 (ExtraMaxDamage).**
Sonde re-armee AVANT la nav (pour capter le fire de CREATION mult-90 attendu) : extraDmg fire **9x, TOUS
mult=180 -> 599, TOUS PREDICTION ; 0 CREATION, 0 COMBAT, 0 a mult 90**. En plus, l'effet resout deja au 1er
decisionView AVANT qu'orksNob bouge -> il est **pre-cree (dans la seed)**, avant tout arm. => **il n'existe
AUCUN fire mult-90** (ni creation, ni combat, ni prediction). Donc **le combat n'obtient PAS son +300 via
`GetVariableForLevel(90)`** ; le "90 rarity" (round(333x0.9)=300) est un FIT du ratio `300=599/2` (et `90=180/2`),
PAS une valeur mesuree -> **REFUTE**. Le combat n'utilise NI GetVariableForLevel NI `DamageModifiers.Add`
(canal prediction-only, #69) pour cet additif. **NE PAS coder un fix "mult 90"** (coincidence-fit, cf. CLAUDE.md).
HYPOTHESE SURVIVANTE **P3** (a confirmer, non fittee) : l'additif SmashaEad = **ExtraMaxDamage (canal MAX seul)**
et le chemin mesure prend le **midpoint** (`GetBaseDamageFix64` = {base-spread, base+spread+ExtraMaxDamage} ;
`HitDamage.GetDamage` avgFlag=midpoint) -> `base + 599/2 = base+300` CONSTANT ; le PORT ajoute 599 A PLAT
(min ET max, #69) -> +599. TEST DECISIF qui SEPARE P3 : rejouer avec une unite/arme a **spread (min!=max)** OU
hooker le canal additif COMBAT reel (service interface-dispatche dans `ExecuteHit`, PAS DamageModifiers) : si
ExtraMaxDamage, l'ecart off-live serait ASYMETRIQUE (plus grand cote MIN). NON fait. **#68 = mecanisme combat
encore OUVERT** (le "90" et le "/2 downstream" tous deux refutes ; P3 = piste, pas un fait).

**MAJ 2 (probe CREATION #75b, 2026-07-09) — extraDmg est un construit PREDICTION-ONLY ; le +300 combat vient d'AILLEURS.**
SmashaEad est cree SUR LE MOVE (PAS pre-seede) : absent au debut (`[BeastSlayer_ExtraDmg, BeastSlayer_ExtraBlock]`),
present apres qu'orksNob bouge 4 hexes. MAIS la creation fire **0 GetVariableForLevel** (`total varLevelDumps=0` —
RIEN, pas juste extraDmg). Combine avec #75a (combat = 0 fires) : **extraDmg (599) n'est resolu QUE sur le chemin
PREDICTION** (mult 180). Creation = 0, combat = 0. => **le +300 combat ne vient PAS du `ForAddition` extraDmg via
un resolveur nomme** (`GetVariableForLevel`, `DamageBonusForAttack`, `DamageModifiers.Add` — tous prediction-side).
Le `extraDmg x 180 = 599` que le PORT applique en combat est un CONSTRUIT PREDICTION-ONLY ; le vrai +300 combat vient
d'un canal DISTINCT encore non localise (service interface-dispatche dans `ExecuteHit`). **La premise "additif extraDmg
en combat" est FAUSSE.** Localiser le vrai +300 = RE profonde du service opaque d'`ExecuteHit` (dig couteux pour UN
effet faible valeur). **RECO : PARK #68** avec cet etat (le port sur-applique un construit prediction-only en combat ;
fix fidele impossible sans localiser le mecanisme combat reel). #71 (gate prediction display) reste correct et couvre
le chemin AI-pertinent ; le residu = +299/coup replay-diff combat sur ce seul effet, sans impact decision.

**MAJ 3 (dig profond ExecuteHit, 7 sondes + RE complete, 2026-07-09) — TOUS les canaux nommes/interrogeables ELIMINES.**
RE lue integralement du pipeline combat + sondes backtrace :
- `AttackDamageOperation.Execute/ExecuteHits/ExecuteHit/GetHitDamage` : `HitDamage.GetDamage` combat = **{2411,2411} base pur** (0 additif dans la plage). Le degat final = service INTERFACE-dispatche (`FUN_1800267c0` slot 0x42 de l'interface `DAT_1831d3468` sur la BattleQuery, consommant les `AbilityEntities` batis par les slots 4/8/0xb/10 de `DAT_183287ef8`).
- `DamageCalculations.CalculateBaseDamageWithModifiers @1810021c0` (combat) = `clamp(Round(base x mult))`, **PAS d'additif**.
- `DamageModifiers.Add @181005f10` (additif `@+0x10 += FromInt(DamageBonus)`) = appele SEULEMENT par `CalculateBaseDamageWithAllModifiers` (PREDICTION).
- `ApplyCappedModifiers @181000020` = etage **%-mult** (`v x chaque pct, clamp`), pas l'additif.
- `ApplyTraitDamageModifiers @180e5a3e0` = caps DEFENSEUR (trait 0x1c immunite, 0x3f1=1009 can't-die), pas l'additif.
- **Sondes backtrace** : `varForLevel` extraDmg = 3 fires TOUS mult180->599 PREDICTION ; `dmgBonus` SmashaEad = PREDICTION (frames DamagePrediction/MakeDamagePredictions) ; **creation = 0 fires** ; **combat = 0 fires** de tous ces resolveurs.
- **`statModSources(orksNob)` = `mods: {}` VIDE** : SmashaEad (effectId 97, effectType 1319, source=self 80, level 1) n'ajoute **AUCUNE stat-mod**.
=> **SmashaEad ne contribue au combat via AUCUN canal hookable/interrogeable** (ni effect-bonus, ni additif, ni stat-mod). Or live=off_sans+300 et retirer SmashaEad du port fait passer off SOUS live (-300, teste, reverti). **PARADOXE** : soit (i) SmashaEad applique +300 via le SERVICE OPAQUE d'ExecuteHit qui lit une valeur PRE-BAKEE sur l'effet (~300) sans re-resoudre (coherent avec 0 fire partout), soit (ii) le +300 live n'est PAS SmashaEad et le `off_sans` du port a un gap AILLEURS (SmashaEad +599 combat = spurious). **NON TRANCHE.**
**PROCHAIN PAS (2 options, lourdes)** : (a) resolution VTABLE LIVE du service opaque (hook `FUN_1800267c0` filtre slot 0x42 -> walk vtable -> adresse concrete -> decompile -> trouver le champ +300) ; (b) mesure LIVE A/B combat WITH vs WITHOUT SmashaEad (orksNob attaque sans avoir bouge >=2 hexes, puis apres, meme cible) pour CONFIRMER que SmashaEad contribue +300 en combat (vs off_sans buggy). (b) tranche i-vs-ii ; (a) nomme le canal. **RECO : PARK** (1 effet faible valeur, mur architectural il2cpp interface-dispatch ; #71 couvre le chemin AI). Sondes : `_probe75{,b,c}_*_live.py`.

**MAJ 4 (VTABLE DIG, canal TROUVE, 2026-07-09) — le +300 est dans le calcul de degat COMBAT (AttackHit/board-node), PAS le canal prediction.**
Resolution vtable live (`FUN_1800267c0` slot 0x42 -> walk il2cpp) + trace complete :
`AttackDamageOperation.ExecuteHit` -> `OperationProcessor.DealDamage @180e074c0` -> `DealDamageOperation.Execute @180e65d20`
-> `DamagePrediction.CalculateDamageOperation @18102dc30` (calcul REEL : soustrait armure/block/crit/shield/overkill).
**MESURE LIVE (hook `CalculateDamageOperation` in/out) : in/out = [(1540,1540),(1738,1738),(1526,1526)]** =
EXACTEMENT les valeurs LIVE per-coup, et **in == out**. => le degat qui ARRIVE a CalculateDamageOperation est
**deja 1540 = base 2411 - armure + 300** (armure ET +300 appliques EN AMONT, dans le calcul de degat de
`ExecuteHit` via le board-node de l'attaquant, interface `DAT_183287ef8` slot 0xb) ; DealDamage/CalculateDamageOperation
ne font que le passer (shield/overkill). **=> LE CANAL DU +300 = le chemin de degat COMBAT AttackHit/board-node**
(valeur per-coup entierement calculee), **PAS** le `ForAddition`/`DamageModifiers` (prediction-only, 599).
**GROUND TRUTH : degat combat live per-coup = 1540.** Le PORT calcule **1839** (`off_sans 1240 + ForAddition 599`)
-> **sur-applique de 299**. **Le modele du port "SmashaEad = additif ForAddition +599 post-percage en combat" est
STRUCTURELLEMENT FAUX** : le combat n'utilise PAS ce canal. **Micro-suivis restants** : (1) resoudre le board-node
slot 0xb (methode-feuille qui produit le +300) ; (2) A/B live WITH/WITHOUT SmashaEad sur l'ENTRANT CalculateDamageOperation
(1540 vs ?) pour confirmer que le +300 EST SmashaEad (vs off_sans buggy). Sondes : `_probe75_*` + hooks TEMP
modifier-observe (dispatch42 vtable-resolve + calcDmgOp in/out) — A RETIRER avant commit. VA cles : DealDamage
@180e074c0, DealDamageOperation.Execute @180e65d20, CalculateDamageOperation @18102dc30.

**MAJ 5 (LEAF NOMME, offline, 2026-07-09) — LE COMBAT REJOUE LA PREDICTION (CACHEE). C'est LE resultat cle.**
Slot map de l'interface `DAT_183287ef8` (= `IDamagePrediction`, lue via les forwarders `CachedDamagePrediction$$`) :
slot 0=get_IgnoreDamageSpread, 3=PredictNormalAttack (CACHE dans un Dict), **4=PredictAttack**, 6=CalculateAbilityDamage,
7=CalculateDirectDamage, 8=RandomlyResolveMinMaxDamage, 0xa=RollCritical, 0xb=CalculateCriticalDamage,
0xc=CalculateDamageOperation, 0xd=GetAttackHits, 0xe=GetDefaultAttackHits, 0xf=GetKnockback.
`ExecuteHit` dispatche les slots **4/8/0xa/0xb** sur le service : **slot 4 = `DamagePrediction.PredictAttack`**
calcule le resultat de degat par-coup (`local_498`), puis roll (8)/crit (0xa/0xb). => **le COMBAT calcule le degat
par-coup en appelant `PredictAttack` (la MEME machinerie que la prediction), via le decorateur
`CachedDamagePrediction`.** D'ou : (1) combat = 0 fire GetVariableForLevel/DamageBonusForAttack (il LIT le CACHE
peuple pendant la phase de prediction de l'IA, il ne recalcule pas) ; (2) le degat combat per-coup (1540) EST la
prediction. **=> STRUCTURE : le combat natif NE calcule PAS le degat separement ; il REJOUE la prediction (cachee).**
Le PORT, lui, a un chemin COMBAT SEPARE (base + ForAddition 599) distinct de son chemin PREDICTION -> **c'est le
fork structurel** (viole "structure offline == structure native"). **FIX FIDELE = faire pointer le degat COMBAT du
runner sur sa PROPRE prediction (PredictAttack) au lieu d'un modele additif separe** ; alors SmashaEad (deja gate
hors prediction display par #71) sera coherent des 2 cotes automatiquement. Le "+300 vs +599" disparait car il n'y
a plus 2 chemins qui divergent. C'est un refactor structurel (aligner combat sur prediction), PAS un capteur de valeur.
VA : PredictAttack forwarder slot 4 @CachedDamagePrediction.PredictAttack 180e2f720 ; concret DamagePrediction.PredictAttack.

**MAJ 6 (RE CLOSE definitive, offline decompile, 2026-07-09) — le +300 = MULTIPLIER RARITY (+0x2c=90), pas +0x24=180. Contradiction du doc TRANCHEE.**
Lecture INTEGRALE de `UnitConfigUtil.GetAbilityVariablesMultiplierPercentageForProgressionIndex @181696230` :
```
entry = unitConfig.progression[progressionIndex]     # +0x80 (ou +0x88 si MoW)
if (variable IN rarity-affected-list for this ability):   # local_res8+0x88 List.Contains(variable)
    return entry + 0x2c      # multiplier RARITY
else:
    return entry + 0x24      # multiplier NORMAL
```
=> DEUX multipliers par entree de progression. Pour orksNob : `+0x24`=180 (normal), `+0x2c`=90 (rarity).
SmashaEad `extraDmg` EST rarity-flaggee (dans `variablesAffectedByRarityBonus`) => resolue avec `+0x2c`=90
=> additif = base(333) x 90/100 = **300**. Pour u90 PowerTrip : `+0x2c`=`+0x24`=180 (pas de divergence) =>
c'est le cas qui **separe** l'hypothese et la CONFIRME (magnitude x180 y matche parce que +0x2c=180 la).
`ConfigAmount.GetAbilityState @180f175a0` : 1re branche teste `Nullable.HasValue(ConfigAmount+0x20)` (Level
baké a la creation de l'effet) ; si present -> le renvoie DIRECTEMENT (valeur rarity-resolue cachee). C'est ce
Level baké (mult 90) que le COMBAT rejoue via PredictAttack (MAJ 5). => **le +300 combat = mult rarity 90, LU
dans le decompile, PAS un fit de scalaire** (300=333x90/100 est la CONSEQUENCE du branchement lu, pas un fit).

**CONTRADICTION DU DOC RESOLUE** : la section « MESURES DEFINITIVES / CORRECTION #75 » (additif=599 des 2 cotes)
mesurait le resolveur `DamageBonusForAttack` dans le contexte PREDICTION-DISPLAY (mult normal 180) — que #71 gate
de toute facon. Le COMBAT utilise le Level baké (mult rarity 90 -> 300). La section « (HISTORIQUE, REFUTE) » avait
donc RAISON sur le fond (mult 90) ; sa « refutation » conflatait les deux chemins. Verdict final = mult rarity 90.

**FORK DU PORT (localise) : `engine/entities/effects/magnitude.py::ability_var`** applique UN SEUL `multiplier_pct`
(= `abilityVariablesMultiplier` de l'unite = `+0x24`=180 capte dans le snapshot) aux variables rarity-flaggees.
Or le natif utilise `+0x2c` (rarity) pour CES variables. => le port doit resoudre les variables rarity-flaggees
avec le multiplier RARITY (`+0x2c`), pas le normal (`+0x24`). **Le port ne capte AUJOURD'HUI que `+0x24`**
(`uc["abilityVariablesMultiplier"]`, snapshot.py) ; le `+0x2c` doit etre expose offline (le jeu l'a : cf.
`UnitStats_{Active,Triggered}Ability_VariableMultiplierPercentage` dans rl_collect_batch). **FIX = (1) capturer le
multiplier RARITY (+0x2c) par unite dans le snapshot (a cote du normal +0x24) ; (2) `ability_var` selectionne
+0x2c si `var_key IN variablesAffectedByRarityBonus`, +0x24 sinon (mirror exact de @181696230).** Non fait ; non commit.
Impact GENERAL (pas juste SmashaEad) : toute unite dont `+0x2c != +0x24` sur une variable rarity-flaggee diverge.

**MAJ 6b (path OFFLINE ecarte, 2026-07-09) — le multiplier de resolution N'EST PAS derivable de gameconfig statique ; « 90 » = un FIT non confirme.**
Chaine de resolution LUE : `ConfigAmount.Calculate @180f171c0` -> `GetAbilityState` (renvoie `Level{level,multiplier}`)
-> `AbilityConfiguration.GetVariableForLevel(config, varKey, Level)`. Le multiplier applique = celui du `Level`
(baké dans le ConfigAmount de l'effet), resolu par `@181696230` (+0x2c rarity / +0x24 normal), valeur RUNTIME de la
progression du unit-model (`param_1+0x80[idx]`). **Gameconfig statique a `units.abilityPowerModifiers.<ability>.baseMultiplier`
(SmashaEad=85, PowerTrip=100, seule cle `baseMultiplier`) MAIS ce N'EST PAS le multiplier de resolution des variables** :
PREUVE = u90 PowerTrip `armorIgnored` resout ×180 (validé live 277×180/100=499) alors que
`abilityPowerModifiers.PowerTrip.baseMultiplier`=100 (donnerait 277) -> le multiplier utilise = `abilityVariablesMultiplier`
(live @0x74=180), PAS abilityPowerModifiers. Donc **path (c) [derive offline depuis gameconfig] est MORT**. Et le
`abilityVariablesMultiplier` rarity (+0x2c) n'est PAS dans gameconfig statique (valeur meta/progression runtime).
**Le « 90 » (300=333×90/100) est un FIT** ; 85 (abilityPowerModifiers) donne 283≠300 ; aucune valeur statique ne
reconcilie proprement. => la divergence #68 combat depend de la valeur RUNTIME du rarity mult (+0x2c) d'orksNob, que
SEULE une lecture LIVE tranche (l'unique usage live legitime : confirmer une valeur runtime que le decompile ne resout
pas statiquement). Fix = capturer live soit (a) la magnitude BAKEE resolue de l'effet, soit (b) le +0x2c par unite.
NE PAS shipper un fit (90). Game off-menu -> mesure requiert amorce.

**MAJ 7 (MESURE LIVE DEFINITIVE, 2026-07-09, probe _probe75 session 43) — SUPERSEDE MAJ 6b : le « 90 » EST REEL (baké dans l'effet), combat=300 CONFIRME. Mon read UnitConfig 180/100 l'a manque car le 90 est sur la PROGRESSION, pas UnitConfiguration.**
Drive qui marche (endturn pour avancer les tours, attaque via `kind:ability` id normale ; PAS aiturn). Mesures :
- `extraDmg` (id 8) : **3 fires, TOUTES class=PREDICTION, mult=180, result=599** (re-resolution `GetVariableForLevel`
  avec `UnitConfiguration.abilityVariablesMultiplier`=180). 0 fire COMBAT, 0 fire CREATION.
- `dmgBonus` SmashaEad `retWords[12]` = **599** (class MIXED).
- **`CalculateDamageOperation` in/out par coup = [(1540,1540),(1738,1738),(1526,1526)]** = DEGAT COMBAT REEL.
  `1540 = off_sans(1240) + 300` => **le combat applique +300 CONSTANT par coup, PAS +599.**
- `dispatch42` slot 0x42 -> `OperationProcessor.DealDamage @180e074c0` (confirme le chemin combat).
=> **RECONCILIATION COMPLETE ET MESUREE** : la PREDICTION re-resout l'additif a 599 (mult 180) ; le COMBAT applique
300 (il LIT une valeur bakee, 0 re-resolution). `300 = 333 x 90/100` : le **90 = mult rarity** (`@181696230` `+0x2c`
sur `progression[idx]` du unit-model, baké dans le `ConfigAmount+0x20` Level de l'effet A SA CREATION). Le **90 N'EST
PAS sur UnitConfiguration** (@0x74=180 normal, @0x78=100 tertiary) — c'est pourquoi ma MAJ 6b (read live 180/100 ->
"no 90, port correct") ETAIT FAUSSE : j'ai lu le mauvais objet. La section « (HISTORIQUE, REFUTE) » du doc (mult 90
baké dans ConfigAmount Level) avait RAISON ; la « MESURE DEFINITIVE 599 des 2 cotes » mesurait la RE-RESOLUTION
prediction (mult 180), gatée hors display par #71.
**=> BUG PORT CONFIRME (mesure) : `magnitude.ability_var("SmashaEad","extraDmg", mult=180)` -> 599 applique en combat
(`operations/damage.py` via `build_attacker_modifiers_from_effects`) ; le vrai combat = 300 (mult rarity 90 baké).
Sur-application +299/coup. FIX = path (a) : capturer la valeur bakée de l'effet (additif 300 OU mult 90 via
`EffectComponent.AbilityState@0x18` -> Level.multiplier) dans le snapshot d'effet, et faire consommer CETTE valeur
par le port pour les variables rarity-flaggees d'effets triggered (SmashaEad), au lieu de re-resoudre a mult 180.**
Note MAJ 5 nuancee : le combat ne « rejoue » pas la re-resolution prediction (sinon 599) ; il lit le BAKE (300).

**MAJ 7b (CORRECTION de MAJ 7 : « mult 90 » = RED HERRING ; l'additif = 599, le combat le /2 DOWNSTREAM, 2026-07-09).**
Le probe montre `dmgBonus SmashaEad retWords[12] = 599` (l'additif RESOLU par `BaseEffect.DamageBonusForAttack`) ET
`extraDmg` re-resout 599 (mult 180). **Si le combat resolvait a mult 90, le resolveur rendrait 300 — il rend 599.**
Donc l'additif SE RESOUT bien a **599 (mult 180)**, et le **300** que le combat applique = **599/2 via un /2 DOWNSTREAM**
dans le build de la HitDamage combat (`Execute`/`ExecuteHits`/`GetBaseDamageFix64`/`CalculateBaseDamageWithAllModifiers`),
PAS une re-resolution a mult 90. Le « 90 » est un RED HERRING : `333x90/100=300` coincide numeriquement avec `599/2=300`,
indistinguables par la VALEUR seule (piege classique fit-de-scalaire). => **le locus exact du /2 (ou 599 devient 300 dans
le build combat) reste NON LU.** Prochain pas fidele = DECOMPOSITION PAR ETAGE (`tools/damage_decomp.py` + modifier-observe
par-etage) sur le pipeline HitDamage combat pour localiser l'etage ou l'additif passe de 599 a 300 (candidats : additif
route en ExtraMaxDamage canal MAX -> mais REFUTE si la contribution est +300 CONSTANT par coup [mesure : off_sans varie
1240/1438/1226, delta constant +300] -> ce n'est PAS un canal-max-midpoint qui varierait ; donc /2 FLAT en amont du roll).
Le fix offline depend de CE locus (lire d'abord, ne pas fitter un /2). #75 reste OUVERT sur ce point precis.

**MAJ 7c (DECOMPOSITION PAR ETAGE, outil damage_decomp, 2026-07-09) — ApplyCappedModifiers ECARTE ; /2 toujours non localise.**
`test_damage_decomp_live` (orksNob->bloodIntercessor) imprime la valeur PAR ETAGE :
- `extraDmg` : mult=180 result=599 (x3) ; additif attaquant agrege 599 ; par-source `{SmashaEadEffect: 599}`.
- **`HitDamage.GetDamage` COMBAT per-coup = {min:2411, max:2411, result:2411}** (base pure = stat Attack, ZERO additif, ZERO spread a ce hook).
- per-hit off=[1839,2037,1825] (port base+599) ; live=[1540,1738,1526] ; **delta constant +299**.
- `applyCapped` fires=12 MAIS `percentsX1000` (liste %-mult attaquant ET defenseur) = **VIDE** -> `ApplyCappedModifiers`
  (`value=Round(value x mod)` clampe, boucle sur la liste) est un **NO-OP** ici -> **ECARTE comme locus du /2**.
- defender mods : additive=0 pierce=0 pen=0 percents=[] (rien cote defense).
=> **VERDICT OUTIL** : etage divergent = ADDITIF (contribue 599) transforme AVAL en +299 par le build HitDamage combat ;
locus exact du /2 **NON LU** (ni ApplyCappedModifiers=liste vide, ni mult-90=additif reellement 599). Candidats restants
NON hookes : `GetHitDamage @180e61730`, `Execute @180e60c70`/`ExecuteHits @180e607b0` (build de la plage combat),
`GetBaseDamageFix64` chemin combat (additif route en ExtraMaxDamage ? mais delta CONSTANT +299 sur rolls varies refute
un canal-max-midpoint). **ETAT #75 : mecanisme entierement mesure, /2 non localise malgre decompose-par-etage ; dernier
pas = hooker le build HitDamage combat (GetHitDamage/ExecuteHits) pour voir a quel etage 599 devient ~300. Effort
disproportionne pour 1 effet low-value -> candidat PARK avec mecanisme documente.**

**MAJ 8 (VERDICT re-expert worktree, RE decompile, 2026-07-09) — additif = Addition PLAT (pas ExtraMaxDamage) ; /2 dans slot 0x42 runtime ; le ½ est DEDUIT, PAS lu -> 2e cas separateur requis avant fix.**
PROUVE (VAs) : (1) build de la HitDamage combat = `AttackDamageBehaviour.GetDamage @180fbb250` (min=slot2, max=slot3
d'une interface formula) -> l'additif d'effet N'ENTRE PAS dans cette range (coherent : HitDamage.GetDamage combat=2411
base pure). (2) `HitDamage.GetDamage @181007bf0` : Min==Max->Min ; `param_3!=0 -> (Min+Max)/2` MIDPOINT deterministe
(flag `FUN_180002560(0,DAT_183287ef8)`) ; sinon rng.Next(Min,Max+1). (3) additif SmashaEad = `EffectBonus.ForAddition
@180f406e0` = **scalaire Addition PLAT** (param_1[2]=value unique) -> **hypothese ExtraMaxDamage canal-max REFUTEE**
(le canal ExtraMaxDamage de GetBaseDamageFix64 param_5 est un FromInt distinct stat 0x19, NON alimente par cet effet).
(4) `DamageModifiers.Add @181005f10` additif plat `+0x10 += FromInt(value)`, pas de /2. (5) `ApplyCappedModifiers`
no-op confirme (que le %-list). (6) **prediction et combat = pipelines DISJOINTS** (xref : `GetBaseDamageFix64`/
`CalculateBaseDamageWithAllModifiers`/`CalculateMin-MaxDamage` appeles UNIQUEMENT par PredictAttackRaw ; combat ne les
appelle pas). La divergence pred(599)/combat(300) est INTENTIONNELLE (2 pipelines), PAS un bug de prediction.
NON RESOLU statiquement : le locus exact du /2 = **slot 0x42 de `DAT_1831d3468`** dispatche dans ExecuteHit
(`FUN_1800267c0(&local_568,0x42,DAT_1831d3468,BattleQuery,...)` -> amount@+0x30) — dispatch d'interface resolu RUNTIME,
tokens metadata non resolubles par read_bytes. 2 hypotheses residuelles pour le ½ : **(H-mid)** slot 0x42 construit
`[roll, roll+additif]` et renvoie le MIDPOINT = roll+round(599/2)=roll+300 (le PLUS compatible : +300 constant PLAT
sur rolls varies, independant du roll) ; **(H-half)** /2 flat litteral. **DEPARTAGE = 1 mesure LIVE sur un 2e cas
SEPARATEUR** (autre effet ForAddition d'ampleur A != 599 : autre level SmashaEad OU BeaconOfRage/BioBarrage/
EnmityForTheUnworthy_ExtraDamage/... -> si delta combat = round(A/2) le ½ est UNIVERSEL sur l'additif attaquant combat ;
si delta = A le 599 avait une autre cause). **NE PAS FITTER ½ sur le seul cas 599.** FIX (apres confirmation) = COMBAT
SEUL dans `operations/damage.py` : EXTRAIRE l'additif attaquant (`mods.additive`) de `apply_pierce_and_modifiers`/
`apply_all_modifiers` (qui reste le chemin PREDICTION, additif plein +599 -> NE PAS toucher, #70/#71 valides) et
l'appliquer PAR COUP apres le roll via un helper combat dedie (midpoint ou /2 selon H-mid/H-half). IMPACT GENERAL :
si ½ universel, TOUS les effets ForAddition attaquants sont sur-evalues 2x en combat par le port -> le fix les corrige
tous (a VERIFIER sur >=2 effets). Point faible n1 a attaquer par le validator : le ½ non-lu (fit-risk).

**MAJ 9 (2026-07-10, session post-incident) — separateur --rank ECARTE (mesure) ; re-expert dispatche sur le READ du multiplier BAKE.**
- **Baseline RE-CONFIRME live** (session 3, `test_getstuckin_combat_live.py`) : live=[1540,1738,1526] port off=[1839,2037,1825]
  base=2411 offset **+299 CONSTANT** ; port additif=**599** (mult 180, al=50, extraDmg[49]=333) ; live additif=**300**. Identique aux mesures anterieures.
- **SEPARATEUR --rank ECARTE (mesure directe, `_probe75_ranksep_live.py`)** : rank-sweep orksNob rangs [17,13,9,5,2].
  `N` (=`abilityVariablesMultiplier` @0x74) reste **180** ET le port additif reste **599** a TOUS les rangs =>
  **`--rank` ne change PAS le multiplier de variable d'ability** (il est fixe par la rarete/roster de la seed BC, pas par le
  rang de build). Aux rangs bas l'offset off-live devient NON-constant (la BASE elle-meme diverge off/live pour des raisons
  hors-SmashaEad) -> lever inutilisable. => **impossible d'obtenir un orksNob a T != N/2 via le build** ; le rank-sweep NE PEUT PAS
  separer (R) de (H). (Ne pas re-tenter ce lever.)
- **DECISIF RESTANT = read DIRECT du multiplier BAKE de l'effet** (90 -> (R) mult rarity/kind par-unite bake ; 180 -> (H) additif 599
  /2 aval). Les events de l'attaque n'exposent PAS le mult triggered (probe : `mult_tags` vide). **Re-expert dispatche** (worktree,
  decompile-only) : (a) le decompile peut-il trancher R/H sans live (chemin combat = dispatch interface slot 0x42 runtime, peut-etre
  non resoluble statiquement) ; (b) recette de read exacte (offsets `EffectComponent` -> Level.multiplier bake, candidats +0x18
  AbilityState / EffectBonus->ConfigAmount+0x20/+0x10) pour un hook read-only. **Fix selon verdict** : (R) => capter le mult bake
  par-effet des triggered ; (H) => combat applique l'additif attaquant a MOITIE (impact GENERAL : tous les additifs attaquants).

**MAJ 10 (2026-07-10, VERDICT FERME : (R) CONFIRMEE, (H) REFUTEE PAR LE DECOMPILE).**
- **Re-expert (decompile, VAs)** : **(H) REFUTEE** — AUCUN `/2` en aval. `CalculateBaseDamageWithAllModifiers
  @18102d3f0` recoit l'additif DEJA RESOLU (`add = attacker.add + defender.add`) et l'ADDITIONNE tel quel ;
  combat et prediction empruntent le MEME `PredictAttack` (`CachedDamagePrediction.PredictAttack @180e2f720`
  slot 4 = simple forwarder). La divergence 599(pred)/300(combat) vient du CONTEXTE de resolution (effet
  attache ou non), PAS d'un /2. Le multiplier est resolu DYNAMIQUEMENT via un provider lazy
  (`AbilityStateFromEffect @180de5e60`), JAMAIS bake numeriquement (`ConfigAmount+0x20` prouve VIDE).
- **(R) fermee par COMBINAISON** : (H)-refutee (pas de /2) + additif combat MESURE **+300 constant** +
  `extraDmg[49]=333` (gameconfig) => mult combat = 300x100/333 = **90** (le triggered's own RARITY mult ;
  extraDmg rarity-flaggee => `+0x2c`=90 via `@181696230`). Le `90=180/2` d'orksNob etait une COINCIDENCE.
- **Read live (`dumpEffectBaked` / `_probe75_baked_read.py`, session 4)** : l'entite-effet SmashaEad
  (1319, owner 80) ne porte QU'UN `EffectComponent` (pas de composant AbilityState separe ; `+0x28=1246`=id
  triggered source ; `+0x68=1`=rounds). **Le multiplier N'EST PAS un champ stocke sur l'effet** -> coherent
  avec "resolu dynamiquement". Donc la source fidele du 90 = le mult TRIGGERED de l'unite, PAS un read d'effet.
- **FIX (R), non-/2** : le port applique le mult ACTIF (180, `abilityVariablesMultiplier` @0x74) a TOUS les
  effets ; pour un effet source d'une ability **TRIGGERED** (SmashaEad), il faut le mult **TRIGGERED**
  (90 = `UnitStats_TriggeredAbility_VariableMultiplierPercentage`). Pieces : (1) snapshot expose le mult
  triggered par-unite ; (2) `BaseEffect.triggered_ability_variables_multiplier` ; (3) `SmashaEadExtraDamageEffect`
  (+ effets triggered-sourced) l'utilisent. PAS un /2 universel (=H, refutee). xpass attendu :
  `test_getstuckin_combat_absolute_bit_exact`.

**MAJ 11 (2026-07-10, read DECISIF : triggered-ability mult = 180, PAS 90 -> fix "capter le mult triggered" INVALIDE ; mecanisme REOUVERT).**
- **`dumpTriggeredMult(orksNob)`** (walk `TriggeredAbilityComponent+0x18` -> collection -> 3 instances triggered ;
  walk VALIDE : `level@0x20=50` correct, `SetAbilityVariableMultiplierPercentageForAll @180fab570` ecrit bien
  `+0x24`) : les 3 abilities TRIGGERED d'orksNob (dont SmashaEad 1246) portent `Level {level@0x20=50,
  multiplier@0x24=`**`180`**`}`, `rarity@0x28=0`. => **le mult de variable des abilities TRIGGERED = 180 (= l'actif),
  PAS 90. Il n'existe AUCUN "90" stocke sur l'ability triggered.**
- => **le FIX planifie (exposer `triggeredAbilityVariablesMultiplier`=90 par-unite) est INVALIDE.** La confiance
  85% (R) du re-expert reposait sur "le composant effet/ability stocke 90" — **REFUTEE par mesure directe** (le
  point faible que le re-expert avait lui-meme flagge : "si le read montre 180, mon modele est faux").
- **Mecanisme du +300 REOUVERT.** La (H)-refutation du re-expert portait sur le pipeline PREDICTION
  (`CalculateBaseDamageWithAllModifiers @18102d3f0` = 599, pas de /2). Le pipeline COMBAT est DISJOINT (MAJ 8)
  et lit un CACHE (`CachedDamagePrediction`, 0 fire `GetVariableForLevel` en combat). D'ou vient le 300 dans le
  cache ? NON localise : NI l'ability-state Level (=180 MESURE), NI une re-resolution combat (0 fire), NI un /2
  dans le pipeline prediction (refute). Candidats survivants TOUJOURS INSEPARABLES pour orksNob (90=180/2) :
  (A) /2 dans le pipeline COMBAT disjoint (slot 0x42 runtime, non trace) ; (B) mult rarity `progression+0x2c`
  applique a la POPULATION du cache (source du 90 = progression unit-model, PAS l'ability instance).
- **ETAT** : 11 MAJs + re-expert + reads directs -> le +300 combat reste non cleanement localise ; le seul dig
  restant = vtable slot 0x42 runtime (`DAT_1831d3468`) du pipeline combat cache (cout eleve). Effort
  DISPROPORTIONNE : 1 effet, **ZERO impact decision AI** (#71 gate le chemin AI ; residu = +299/coup replay-diff
  combat seul). **RECO FORTE : PARK** avec ce corpus. Hooks read-only (`effect-baked-dump.ts` :
  dumpEffectBaked/dumpTriggeredMult) + probes `_probe75_*` = A RETIRER au park.

**MAJ 12 (2026-07-10, MECANISME RESOLU — 2e re-expert : (R) confirme, (H) refutee STRUCTURELLEMENT ; additif combat = 300 = extraDmg x rarity-mult(90) BAKE a la creation ; 90 = meta progression+0x2c, HORS gameconfig).**
- **(H) REFUTEE STRUCTURELLEMENT** (2e re-expert, xrefs VERIFIES) : AUCUN `/2` dans le decompile combat.
  `MinMaxDamage.Avg @181052470` (seul midpoint) = xrefs EXCLUSIVEMENT AI/prediction, JAMAIS
  `ExecuteHit`/`CalculateDamageOperation`/`DealDamage`. `RandomlyResolveMinMaxDamage @181038600` = roll
  uniforme. `CalculateDamageOperation @18102dc30` recoit un degat DEJA scalaire (1540), 0 `/2`. Additif
  PLAT (min ET max), PAS ExtraMaxDamage (canal max = `FromInt` distinct non alimente). Combat+prediction
  PARTAGENT range (`PredictAttackRaw`) + modifiers (`CalculateAttackerModifiersForPrediction`), PAS de flag
  `is_prediction`. => **impossibilite structurelle d'un `/2` combat.**
- **=> (R) SEUL SURVIVANT** : l'additif combat VAUT reellement 300 (rarity-mult 90). Le combat LIT une
  valeur BAKEE (0 fire `GetVariableForLevel`) ; la prediction-display RE-resout a 180->599 (gatee hors
  display par #71). `90=180/2` = COINCIDENCE numerique, PAS un `/2`.
- **SOURCE du 90 (RE `@181696230` LUE)** : `UnitConfigUtil.GetAbilityVariablesMultiplierPercentageForProgressionIndex`
  (**META**, `IdunMetaLogic.UserProgress`) : `config+0x80[progIdx]` (units) / `+0x88` (MoW) = entree progression ;
  renvoie `+0x2c` (RARITY) SSI la variable in `variablesAffectedByRarityBonus` (extraDmg L'EST), sinon `+0x24`
  (NORMAL=180). orksNob : +0x24=180, +0x2c=90. Applique a la **CREATION de l'effet** (bake le ConfigAmount) ;
  le combat lit ce bake. Coherent avec MAJ 11 (instance ability battle=180 : le 90 n'est PAS sur l'instance,
  c'est la META progression).
- **PowerTrip.armorIgnored (rarity-flaggee, ACTIVE) = x180 (valide) : NON contredit** — resolu FRESH via le
  Level instance (180) dans `CalculateAttackerModifiers`, PAS bake via un ConfigAmount d'effet. => la regle
  n'est PAS "rarity-flaggee -> 90" universel ; c'est **"additif d'EFFET bake a la creation -> rarity-mult ;
  resolution FRESH -> normal-mult"**. Distinction CLE du fix (ne pas x90 PowerTrip).
- **90 HORS gameconfig (RE-confirme)** : orksNob gameconfig = `powerMultiplier=98`, `BaseRarity=Epic` ; AUCUN
  champ rarity-mult. Le `+0x2c` est META/progression RUNTIME (MAJ 6b re-confirme) => **fix = CAPTURE live**
  (meta `progression+0x2c` OU valeur bakee de l'effet), PAS derivable offline.
- **FIX (recette)** : capturer le rarity-mult par-unite (90) et l'appliquer dans `magnitude.ability_var` aux
  variables rarity-flaggees des effets BAKE-a-la-creation (triggered-sourced type SmashaEad), en laissant 180
  pour les resolutions FRESH (PowerTrip). Capture = read meta `progression+0x2c` (acces config meta depuis le
  runner = RE additionnelle) OU la valeur bakee de l'effet (`ConfigAmount+0x10`).
- **ETAT : mecanisme RESOLU + documente. Implementation = DERNIERE MILE AWKWARD** (capture d'une valeur META
  runtime hors gameconfig, pour 1 effet a ZERO impact decision AI). Le mystere des 11 MAJ est TRANCHE : (R),
  pas de `/2`. Hooks read-only (`effect-baked-dump`) + probes `_probe75_*` = a retirer.

**MAJ 13 (2026-07-10 soir, VRAI MECANISME LU + RECONSTRUIT BIT-EXACT 3/3 — MAJ 12 ((R) mult-90) REFUTEE
PAR MESURES DIRECTES ; l'additif ForAddition d'un effet attaquant est applique en COMBAT au degat ROULE,
AVANT percage/armure : `live = Round_half_even(GetDamageWithPiercing(roll + 599, 50, armor=2208))` =
1540/1738/1526 EXACTS sur les 3 coups. Le port l'applique POST-percage (+599 plat) -> sur-compte de la
fraction non-percante. Le "x90" de MAJ 10-12 = coincidence numerique (599x50% ~= 300).**

- **3 REFUTATIONS PAR LECTURE DIRECTE (session du soir, RPCs read-only frais)** :
  1. `effectAbilityStates` (nouveau RPC, walk `EffectComponent.AbilityStateReference@0x18`, dump gqfc5mff6c
     TypeDefIndex 24412/24402) : l'effet SmashaEad live (id 97, owner 80) porte
     `{Owner:80, AbilityType:[0,0,1,1246], Nullable<AbilityState>: VIDE}` -> **RIEN n'est bake a la creation**
     (MAJ 12 "bake au ConfigAmount" = faux ; la resolution est LAZY depuis (owner, type)).
  2. `unitAbilityStates` (nouveau RPC) : TOUTES les instances d'ability d'orksNob (actives 1152/69 +
     triggered 1246/1234/1518) = `{level:50, mult:180}`, override VIDE -> **aucun 90 nulle part dans l'etat**.
  3. `varTrace` (hook TEMP one-shot arme a la demande sur `TryGetVariableArrayForLevel @181577510`, l'unique
     impl concrete) : pendant l'ATTAQUE combat, extraDmg(8) resout **3x avec {level:50, mult:180} -> 599 par
     coup**. La mesure historique "0 fire GetVariableForLevel en combat" hookait un autre overload -> FAUSSE.
     => le combat RESOUT bien 599 ; il ne l'applique juste PAS en +degat plat.
- **`abilityConfigProbe` (nouveau RPC, invoke natif)** : la config battle de 1246 (via
  `AbilitiesDatabase.GetConfig(TriggeredAbilityType) @180fdb2c0` -> `AbilitiesConfiguration.GetPassive
  @181575ab0`, pur lookup registre) = la MEME table que gameconfig (`extraDmg[49]=333`, `[64]=437`,
  rarityFlagged=[8]) ; `GetVariableForLevel(extraDmg, {50,180})=599`, `{50,100}=333`, `{50,90}=300` ->
  formule confirmee `round_fix64(table[level-1] x mult/100)` (Fix64.Round, 299.7->300, 599.4->599).
- **PIPELINE PARTAGE LU (les VAs qui ferment le dossier)** :
  - `CalculateBaseDamageWithAllModifiers @18102d3f0` (callers : `CalculateAbilityDamage @18102cb50` = COMBAT
    par-coup + `PredictAttackRaw` x2 = PREDICTION) : lit `DamageModifiers.Piercing@+0x20` att+def (-> args
    pierce), **`DamageModifiers.IgnoreArmor@+0x28` att+def -> sommes -> arg `add` de
    GetBaseDamageWithFixedPiercedArmor**, puis slot 0x11 `ApplyCappedModifiers @181000020` (%-list SEUL,
    clamp(Round(v x mult), +/-cap)) par cote, puis slot 0x10 `CalculateBaseDamageWithModifiers` (x Multiplier
    @+0x30) par cote, puis `Override@+0x0` (remplace). **`Addition@+0x10` N'EST PAS consommee ici.**
  - `GetBaseDamageWithFixedPiercedArmor @181030d10` : pierceTotal = clamp(profilePierce(GetPiercingRatio) +
    stats att 26/21-22 + Piercing att + Piercing def, <=100) ; **`armor = Max(GetStat(def, 16=FixedArmor) -
    (int)add, 0)`** ; d = GetDamageWithPiercing(d, pierceTotal, armor) [x2 si trait 0x3f5 def ; x3 cas
    triggered 0x4b6]. **L'arg `add` (= IgnoreArmor somme) REDUIT L'ARMURE, plancher 0.**
  - `CalculateAbilityDamage @18102cb50` (COMBAT par-coup) : shieldAbs=Min(dmg,shield) ; mods = **slot 0xf
    de IDamageCalculations = `CalculateDefenderModifiersForPrediction(state, entities)` 2-args @181002a70**
    (delegue au 3-args @181002c30 avec la liste des effets ACTIFS state-wide) ; CBDWAM(dmg-shieldAbs, ...,
    modsA=VIDE, modsB=ce builder) ; puis `result += modsB.Addition` (plat, par coup) ; Max(0) ;
    ApplyTraitDamageLimits ; re-ajout shieldAbs.
  - **Builder 3-args @181002c30** : stat-mods defenseur (negate) en %-mult ; boucle sur TOUS les
    EffectWithTarget actifs x leurs cibles : slot 0x1a (effet) -> Nullable<DamageBonus> -> ajoute a la liste
    + **`IgnoreArmor += DamageBonus+0x38`** + `Override = DamageBonus+0x40` ; slot 0x1b -> 2e famille ->
    liste ; slot 0x19 -> `Piercing += valeur` ; puis pour chaque DamageBonus de la liste :
    `DamageModifiers.Add @181005f10` (bonus+0x28 -> Addition@+0x10 ; +0x30 -> soustraction ; +0x48/+0x50 ->
    %-list {mult 1+round(pct)/100, cap}). `IDamageCalculations` : slot 13/14/15 = builders, 16 =
    CalculateBaseDamageWithModifiers, 17 = ApplyCappedModifiers (interface TypeDefIndex 11732).
  - Struct `DamageModifiers` (TypeDefIndex 11734) : Override@0x0, Addition@0x10, CappedModifiers@0x18,
    Piercing@0x20, IgnoreArmor@0x28, Multiplier@0x30, DamageBonusesForInfo@0x38.
- **ARITHMETIQUE DISCRIMINANTE — RECONSTRUCTION BIT-EXACT 3/3 (mesures combatSnapshot : bloodIntercessor
  entityId 78 FixedArmor=2208, orksNob 80 attack=2411)** :
  - Port off=[1839,2037,1825] = GDWP(roll,50,2208)+599 -> rolls = [2480,2876,2452] (branche PIERCE : roll/2 >
    roll-2208), donc GDWP baseline = [1240,1438,1226] (valeurs .0, aucune ambiguite d'arrondi).
  - **Modele PRE-PERCAGE : live = GDWP(roll+599, 50, 2208) = pierce((roll+599)x0.5) = [1539.5, 1737.5,
    1525.5] -> Fix64.Round half-to-even -> [1540, 1738, 1526] = LES 3 VALEURS LIVE EXACTES.** ✓✓✓
  - Modele "IgnoreArmor" (armure-599) REFUTE : branche pierce dominante -> armor' sans effet -> live=1240 ✗.
    (Ma 1re deduction "armor=300 neutralisee" etait fausse — fondee sur une armure supposee, la mesure
    combatSnapshot l'a tuee. L'arg `add` de GetBaseDamageWithFixedPiercedArmor = le canal IgnoreArmor@+0x28
    (PowerTrip.armorIgnored), PAS celui de SmashaEad.)
  - `GetDamageWithPiercing @1815598b0` (LU) : ENTIEREMENT Fix64 — pierced = damage x (pct/100) SANS
    troncature interne ; result = max(0, damage - armor, pierced) en Fix64 ; la conversion int finale
    (aval, chaine CalculateAbilityDamage/op) arrondit HALF-TO-EVEN (1539.5->1540, 1737.5->1738,
    1525.5->1526 — 3/3, = Fix64.Round de FixMath.NET). ⚠ le port `get_damage_with_piercing` fait `//`
    (floor) — indiscernable sur les valeurs .0 des tests passes, FAUX sur les .5 -> a aligner.
  - L'additif entre en INT (599 = GetVariableForLevel deja Fix64.Round-e), ajoute au ROLL (largeur de plage
    inchangee -> le test RNG-aligned passait) AVANT GetDamageWithPiercing, dans le caller combat de
    CalculateAbilityDamage (ExecuteHits / op slot-0x42 : le param damage arrive DEJA additive).
  - Le "x90" de MAJ 10-12 = coincidence numerique (599 x 50% pierce = 299.5~=300 ~= 333x0.9). Les 3
    verdicts re-expert successifs (mult-90 bake / meta progression+0x2c / mythicAbilityStatMultiplierPct)
    sont tous REFUTES par lectures directes ; `heroProgressionSteps.mythicAbilityStatMultiplierPct@+0x2c`
    (UnitsConfigDto @0x80, dump 16438/16445) et le mapping `GetActiveAbilityUsedForConfig @1815808e0`
    (dict statique ; 1246 n'y est PAS, seulement dans le HashSet `ShouldBeSimulated`@+0x68) documentes au
    passage comme vocabulaire.
  - **Reconciliation #88 (Neuroparasite -582, additif PLAT scale par %-mods)** : COMPATIBLE — pre-percage
    implique aussi pre-%-list ; avec pierce=100 (Psychic) l'additif passe entier -> indiscernable d'un flat
    scale. #88 et #75 = LE MEME placement natif (pre-percage), observe sous deux pierce differents.
- **CHAINE DE RESOLUTION LAZY (lue, pour reference)** : `SmashaEadEffect.CreateEffectDamageBonusForAttack
  @180f6bee0` = `EffectBonus.ForAddition(OwnerIsCaster & IsNormalAttack, ConfigVar(8=extraDmg,
  GetAbilityState, effect.Config@0x60), ctx)` ; `BaseEffect.GetAbilityState @180f11780` ->
  `DSLFactory.AbilityStateFromEffect @180de5e60` (selecteur `<Effect>@factory+0x150`) ; eval :
  `ConfigAmount.GetAbilityState @180f175a0` (provider -> `BattleQuery.GetAbilityState @18105a7b0` : ref
  vide -> owner entity -> `UnitExtensions.GetAbilityState @180eced70` : mapping actif? sinon
  `TriggeredAbilityComponent.TryGetAbility` -> instance {50,180}) ; `ConfigAmount.Calculate @180f171c0` ->
  `GetVariableForLevel @181576fb0` -> `TryGetVariableArrayForLevel @181577510` (Split(','), Int32.TryParse,
  mult SSI var dans `_variablesAffectedByRarityBonus`@config+0x28, Fix64.Round). Les multipliers d'instance
  sont poses au SETUP par `UnitExtensions.ApplyStatModifier @180ecd0e0` (case 14 = mult triggered via
  `SetAbilityVariableMultiplierPercentageForAll @180fab570`, case 19 = mult actives, overrides kind 7/8).
- **QUESTIONS RESIDUELLES (2 lectures, non bloquantes pour le fix)** : (a) le call-site combat EXACT qui
  ajoute mods.Addition au roll avant CalculateAbilityDamage (ExecuteHits / op slot-0x42 `DAT_1831d3468` —
  gshared, l'empirie 3/3 le contraint totalement) ; (b) le point exact du Fix64.Round final (aval de
  CalculateAbilityDamage, half-to-even 3/3).
- **FIX PORT (recette REELLE, bit-exact-contrainte)** : dans le COMBAT runner, l'additif ForAddition des
  effets ATTAQUANTS (DamageBonusForAttack) s'ajoute au DEGAT ROULE AVANT
  `get_base_damage_with_fixed_pierced_armor` (roll + additive -> pierce/armure), PAS apres (flat
  post-percage comme aujourd'hui). Et `get_damage_with_piercing`/la conversion finale doit arrondir
  HALF-TO-EVEN (Fix64.Round), pas floor (`//`) — indiscernable sur .0, decisif sur .5. La PREDICTION garde
  son chemin actuel (Addition flat once-per-attack = le natif prediction, #70/#71 ; la pred NATIVE diverge
  du combat natif ici — c'est un predOptimistic-like assume). Test juge :
  `test_getstuckin_combat_absolute_bit_exact` (xfail -> xpass attendu) + regression #88 (Neuroparasite)
  + slice damage ciblee (bit-exact .0 preserves).
- **Outils AJOUTES (bundle, non commit)** : RPCs read-only `effectAbilityStates` / `unitAbilityStates` /
  `abilityConfigProbe` (+ helper `readEffectAbilityStateRaw` dans game/effects.ts) + hook TEMP arme a la
  demande `varTraceInstall`/`varTraceRead`/`varTraceRemove` (rpc-view.ts). A conserver (diagnostics
  generiques utiles), varTrace JAMAIS auto-arme.
- **FIX IMPLEMENTE + VALIDE (2026-07-11 00h)** : `apply_pierce_and_modifiers(...,
  attacker_additive_pre=True)` (damage_prediction.py — additif au degat AVANT la boucle GDWP, puis
  %-list SEUL via ApplyCappedModifiers) + les 3 call-sites COMBAT du runner
  (runner/operations/damage.py : attaque normale `_reduced_bounds`, ability `_reduce`, normal-like
  `_reduced`) passent True ; PREDICTION inchangee (False, defaut). RESULTAT :
  `test_getstuckin_combat_absolute_bit_exact` **XPASS (off_ph == live_ph au coup pres + PV egaux)** —
  xfail retire ; gardes slice DAMAGE 11/11 verts (roll x2, armored, attack x2, ability, crit x2,
  block x2, splash). L'arrondi half-even du GDWP final n'a PAS eu besoin de changer (le modele
  reduce-then-roll donne des bornes .0 sur ce cas ; `//` conserve — vigilance future sur bornes
  impaires, cf. QUESTIONS RESIDUELLES).

**FIX (ANCIENNES options — SUPERSEDEES par MAJ 5 : le vrai fix = aligner combat sur prediction, pas capturer une valeur)** : le runner seed les effets depuis `decisionView.effects`. Options :
(a) exposer la magnitude BAKEE de l'effet (lire `ConfigAmount+0x10` cache OU `ConfigAmount+0x20` Level.mult=90)
dans le snapshot d'effet -> le port l'utilise au lieu de recalculer ; (b) capturer par-ability le multiplier
RARITY (`@181696230 +0x2c`) + flag `variablesAffectedByRarityBonus` -> le port choisit 90 vs 180 par variable.
(a) = plus simple/direct (lit la valeur reelle) ; (b) = plus general (rejoue la logique). NON fait ; non commit.

### MESURES DEFINITIVES (outil damage_decomp, 2026-07-09) — l'additif=599 des 2 cotes, le COMBAT n'en applique que 300 ; la /2 est DOWNSTREAM dans ExecuteHit

**Tout mesure via `tools/damage_decomp` (modifier-observe etendu) sur orksNob->bloodIntercessor :**
- `extraDmg` resout a **mult=180 -> 599** (GetVariableForLevel, 3x, chemin PREDICTION). PAS 90. => l'hypothese
  "multiplier 90/rarity" est REFUTEE PAR MESURE DIRECTE (3e refutation ; cf. lecon fit-de-scalaire).
- Additif attaquant (SmashaEad `DamageBonusForAttack` retWords[6]=1246 type, retWords[12]=**599**). Le PORT
  calcule 599 AUSSI -> la VALEUR matche des 2 cotes.
- `HitDamage.GetDamage` combat = **{min:2411, max:2411} -> 2411** (base = stat Attack, min==max, PAS de roll
  ici ; pierce/armure/spread/additif sont AVAL).
- DEFENDER DamageModifiers : additive=0, pierce=0, penetration=0, **%-mult list @0x18 = VIDE**. ATTACKER :
  additive=599, %-mult VIDE. => la /2 n'est PAS un modifier attaquant/defenseur capture.
- COMBAT applique **+300 CONSTANT** (off_sans+300=live ; test RNG-aligned PASSE -> base rolls identiques,
  seul l'additif differe). `300 = 599/2` (intuition user "degats/2").
=> **La /2 (599->300) est DOWNSTREAM dans `AttackDamageOperation.ExecuteHit @180e5eff0`** (non encore hooke) :
candidats = `GetBonusDamage`, `CritDamageInfo`, **`ApplyCappedModifiers`** (fire 12x, cote defense/cap),
`IsAttackMaxOutDamage`. `ExecuteHit` recoit la HitDamage {min,max} DEJA construite par `Execute`/`ExecuteHits`
en AMONT -> l'additif y est folde ; c'est LA (build de la HitDamage combat) que se trouve la /2. NB : le combat
n'appelle PAS `GetVariableForLevel`/`DamageBonusForAttack`/`GetBaseDamageWithFixedPiercedArmor` (0 fire combat ;
tous les fires = les 3 predictions) -> il resout l'additif par un AUTRE chemin non hooke.

**HINT USER (2026-07-09) : "creuse cote defense"** — mais additive/pierce/pen/%-mult defenseur = 0/vide dans
les mods captures. Candidat defense restant NON hooke : `ApplyCappedModifiers` (cap per-coup cote defenseur).
bloodIntercessor (Mataneo, Uncommon) : traits Hero/TeleportStrike/Flying/RapidAssault, PAS de reduction-degat
evidente. A ELUCIDER : quelle mecanique defensive precise (armure appliquee a l'additif ? cap ? profil de
degat ?) -> hooker `ApplyCappedModifiers`/le build HitDamage combat (Execute) au prochain passage.

**ETAT OUTIL (livre, non commite)** : `scripts/python/tools/damage_decomp.py` + demo
`tests/engine/runner/test_damage_decomp_live.py` + extensions `modifier-observe.ts` (retWords par-source,
varForLevel, hitDmgGet, percentsX1000). Regle "decompose d'abord" ajoutee a CLAUDE.md + memory
`feedback_damage_decomposition_measure_stage`. La /2 combat = SEULE inconnue restante de #68.

### CORRECTION #75 (OUTIL DE DECOMPOSITION, 2026-07-09) — l'additif VAUT 599 des 2 cotes ; c'est le COMBAT qui l'applique de moitie

**MESURE DIRECTE par `tools/damage_decomp` (attribution par-source via `BaseEffect.DamageBonusForAttack`
retWords) : SmashaEad contribue un additif de `599` (retWords[6]=1246=type SmashaEad, retWords[12]=599).**
Le PORT calcule 599 AUSSI. => **la VALEUR de l'additif (599) MATCHE des deux cotes** ; le port n'a PAS un
mult/valeur faux. Or l'ecart FINAL combat = +299 constant (off applique +599 a plat, live ~+300). Donc :
=> **la divergence #68 = un ETAGE AVAL (build de la HitDamage combat) qui n'applique QUE ~la moitie de
l'additif 599** (== l'intuition user « degats/2 », CONFIRMEE par la mesure). PISTE (a RE pour clore) :
`GetBaseDamageFix64` = `{base-spread, base+spread+ExtraMaxDamage}` -> si l'additif SmashaEad est un
**ExtraMaxDamage** (ajoute au MAX seul, pas a plat), alors le degat par-coup n'en reflete que ~la moitie
(effet midpoint/plage), tandis que le port `_run_hits` l'ajoute A PLAT (min ET max) -> sur-applique ~2x.
A CLORE : RE `AttackDamageOperation.ExecuteHit @180e5eff0` / la construction de la HitDamage combat pour
voir si 599 = ExtraMaxDamage (canal MAX) vs additif plat, et aligner le port. **TOUTES les hypotheses
"mult 90" / "rarity mult" / "300 resolu" ci-dessous sont REFUTEES par cette mesure (l'additif = 599, pas
300 ; il n'y a pas de mult 90).** Lecon : l'outil de decompo l'a montre en 1 run ; le fit-de-scalaire a
coute ~5 reinjects (cf. CLAUDE.md "Divergence de degat = DECOMPOSITION PAR ETAGE").

### (HISTORIQUE, REFUTE) CONCLUSION #75 — c'est la VALEUR resolue (300), pas un multiplier capturable

**Diagnostic FINAL (mesure par etage, pas fit de scalaire) :**
- `extraDmg[49]` = **333** (gameconfig), extraDmg in `variablesAffectedByRarityBonus`.
- `AbilityState.Level.multiplier` = **180** sur l'instance ACTIVE **ET** l'instance TRIGGERED SmashaEad
  (lu live : triggered instance Level words `{level=50, multiplier=180, rarity=0}`). Donc PAS 90.
- `UnitConfiguration` : AUCUN offset 0x40..0xE0 ne contient 90 (probe live). Donc 90 n'est PAS un champ unite.
- `DamageModifiers.Add @181005f10` ajoute l'additif **A PLAT** (`additive@+0x10 += FromInt(DamageBonus)`,
  AUCUN /2) ; delta per-coup live constant **+300**. => **l'additif RESOLU que le jeu applique = 300**,
  pas 599. `300 = round(333 x 90/100)`.
=> Le multiplier EFFECTIF a la resolution = **90**, MAIS il n'est ni sur UnitConfig, ni sur le Level de
l'instance d'ability (180). Il est **bake dans le `ConfigAmount` PROPRE de l'effet** au moment de sa creation
(`@181696230` renvoie le rarity `+0x2c`=90 pour orksNob quand la variable est rarity-flagged ; `+0x24`=180
sinon). Pour u90 PowerTrip, `+0x2c`=`+0x24`=180 -> pas de divergence (c'est pourquoi magnitude.py x180 y matche).
Le rarity multiplier est donc PAR-UNITE (orksNob 90 vs u90 180), distinct du normal (180), et vit dans le
ConfigAmount de l'effet.

**Statut : #68/#75 PARKED (xfail-tracked).** Le port sur-applique (+299/coup) car `magnitude.ability_var`
scale les vars rarity-flagged par le multiplier NORMAL (`abilityVariablesMultiplier`=180) au lieu du rarity
(90). Le fix OFFLINE est trivial (utiliser 90) mais la CAPTURE fidele du 90 est profonde (lire le Level cache
du ConfigAmount de l'effet, ou porter le calcul rarity `@181696230 +0x2c` — non fait). Faible valeur (un
effet), donc parked. Outil a construire : un DIFF DE DECOMPOSITION (valeur par etage off vs live) pour
localiser mecaniquement l'etage divergent (ici : additif off=599 vs live=300) au lieu de deviner le parametre.

### (HISTORIQUE) REFUTATION du plan 5 (LIVE, 2026-07-09) — `GetAbilityState(unit,1246)` rend 180, PAS 90

Le plan 5 a ete IMPLEMENTE + teste live (frida `game/ability-state-multiplier.ts` : `invokeMethod(GetAbilityState
@180eced70, [unitPtr, ptr(1246)])`, diag boxe). Resultat mesure (orksNob, abilityType=1246) : boxe words @[0x10,0x14,..]
= **[level=50, multiplier=180, 0, 0]**. => **le multiplier rendu = 180, pas 90.**

CAUSE (RE-relue) : `@180eced70` fait d'abord `TriggeredAbility.GetActiveAbilityUsedForConfig(1246)` ; pour SmashaEad
ca rend l'ACTIVE (Tanksmasha) -> il RECURSE dans l'overload actif `@180ecea30` et rend le `Level.multiplier` de
l'**ACTIVE (180)**, pas celui de la triggered. Donc `UnitExtensions.GetAbilityState(unit, triggeredType)` N'EST PAS
la resolution que fait le combat pour l'additif SmashaEad.

VRAI locus du 90 (RE `ConfigAmount.GetAbilityState @180f175a0`, relue) : la 1re branche teste `Nullable.HasValue`
sur **`ConfigAmount+0x20`** (un `Level` CACHE sur le ConfigAmount de l'effet) ; si present -> le renvoie DIRECTEMENT
(sans passer par GetActiveAbilityUsedForConfig). Ce Level cache est BAKE a la creation de l'EffectBonus/ConfigAmount
par `SmashaEadAbility.CreateEffectDamageBonusForAttack` avec le multiplier PROPRE de SmashaEad (90, le `+0x2c` rarity
de `@181696230`). => **le 90 vit dans le ConfigAmount de l'EFFET (Level cache @+0x20), atteignable par
effet -> EffectComponent -> EffectBonus -> ConfigAmount -> Level.multiplier**, PAS par une requete d'ability au niveau
unite. Capture fidele = lecture INTERNE de l'effet (fiddly), ou lecture directe de l'instance triggered (a verifier :
donne-t-elle 90 ou 180 ?). #75 RESTE OUVERT : le plan 5 (simple) est refute ; la capture fidele demande soit la
lecture du Level cache du ConfigAmount de l'effet, soit un chemin encore a RE. Le fix OFFLINE reste trivial (mettre
mult=90 -> port==live) ; SEULE la SOURCE fidele du 90 manque.

---

**(historique) SUR-PREDICTION (mesure DETERMINISTE, #71)** : via `Scene.from_state` (aiPredict, aucun roll RNG),
orksNob->worldTerminator (cible NON-Big -> BeastSlayer=0, isole SmashaEad) :
- off WITH SmashaEad = `(1563, 2047)` ; oracle `decisionView` = `(948, 1311)` ; off WITHOUT = `(964, 1448)` ~= oracle.
- => l'oracle DISPLAY (`decisionView` = `GetAllPredictions`, lit `GetStat(Attack Current)`) **N'APPLIQUE PAS**
  l'additif SmashaEad ; le port l'applique (+599 une fois) -> **SUR-PREDICTION de +599**. off WITHOUT ~= oracle
  confirme que le RESTE (base+RapidAssault %-mult) matche ; c'est bien l'additif effet qui sur-compte.
- DISPLAY != SCORING : le %-mult (RapidAssault) EST reflete dans le DISPLAY (valide) mais l'additif effet ne
  l'est apparemment PAS -> asymetrie a RE (#71 : `GetAllPredictions @181090f50` applique-t-il l'additif @+0x10 ?).
  Si non -> retirer l'additif effet du chemin prediction display-matchant, le garder en COMBAT/scoring.
- Caveat : sample `predOpt=True` (worldTerminator TerminatorArmour) confond le match absolu, PAS le +599 relatif.
- Reconcilier avec le replay COMBAT (off~=live+11-33, PAS +599) : le combat n'appliquait pas +599 non plus
  -> niveau/presence de SmashaEad a re-verifier en combat aussi. **SmashaEad PAS valide (voir #71).**

NB harnais : la validation DETERMINISTE via `Scene.from_state` + le drive du replay CONTOURNE le snag
`build_samples` (`0 units cold` / `base non capturable` sur runner 1v1 isole). Voie reutilisable.

## BeastSlayer_ExtraDmg — PORTE + VALIDE LIVE (2026-07-08)

**Classe `BeastSlayerExtraDmgEffect`** (loki.py) = `for_percent_increase(True, beastSlayerExtraDmgPct=20)`
gate `not is_ranged` (IsMeleeAttack) ET cible BigTarget/Vehicle ; enregistree `"BeastSlayer_ExtraDmg"`
dans factory. **Threading TARGET** : `target_traits` (set de noms de traits cible, mirror `HasTrait`)
ajoute a `create_effect_damage_bonus_for_attack` (base + 5 overrides), au funnel partage
`_attacker_effect_bonuses` + `build_attacker_modifiers_from_effects` +
`calculate_attacker_modifiers_for_prediction`, et calcule chez les 2 appelants NORMAL-ATTACK :
prediction (`prediction.py`, depuis `scene.vis_by_id`->gameconfig traits) et combat
(`damage.py` normal-attack, via helper `target_trait_names(state, target_id)` lisant
`StatsComponent.ctx.traits`). Chemins ability/splash/trigger (damage.py:364/431, triggers.py:1016) =
`target_traits=None` (BeastSlayer no-op documente ; melee-ability = follow-up si besoin).

**Validation** (replay-diff, off-RNG seede depuis live) :
- Logique unitaire : BigTarget/Vehicle melee -> PercentIncrease 20 (x1.2) ; Hero/ranged/no-target -> None.
- No-regression : test_predict_live 2/2 + test_damage_normal_armored/ability 2/2 (funnel + 2 appelants).
- LIVE end-to-end vs cible BigTarget (tauCrisis) :
  - custoBladeChampion : live [1419,1449,1119] vs offWITH [1418,1448,1118] (-1/coup = arrondi Fix64 //100,
    PAS une erreur) ; offSANS-BeastSlayer [943,1228,881] (~20% plus bas).
  - ultraTitus : live [692,752,666,508] vs offWITH [691,751,665,507] (-1/coup) ; offSANS [524,626,582,466].
  => avec BeastSlayer, off reproduit l'oracle live a +/-1 (arrondi) ; sans, off chute ~20%. PORT CONFIRME.

## (RE, conserve) BeastSlayer_ExtraDmg

RE ghidra + gameconfig + i2 :
- **gameconfig (trait BeastSlayer)** : `beastSlayerExtraDmgPct=20`, `beastSlayerBlockChance=10`,
  `beastSlayerBlockAsMaxArmorPct=100`. (Variable de TRAIT -> globale, NON scalee par le mult.)
- **i2** : "+{extraDmgPct}% Damage with **melee** attacks to **Big Targets and Vehicles**. Added
  {blockChance}% chance to Block {blockDmgPct}% of current Armour as Damage."
- **`BeastSlayer_ExtraDmgEffect.CreateDamageModifier @180f336c0`** : magnitude = `ConfigConst(0xf)` =
  `beastSlayerExtraDmgPct` = **+20% (PercentIncrease)** ; condition =
  `OwnerIsCaster & IsMeleeAttack & ( HasTrait(target, 0x405=1029 BigTarget) | HasTrait(target, 0x3f9=1017 Vehicle) )`.
- Effet cree par `BeastSlayerAbility.CreateTrigger @180e18f90` (triggered).

### BeastSlayer_ExtraBlock (cote DEFENSE) — PORTE + VALIDE LIVE (2026-07-09, #72)

**RESOLU** : source de bloc supplementaire + roll-gating fidele. Validation replay-diff BIT-EXACT
(necroDestroyer 6 coups -> orksNob) : off per-hit == live, PV egaux (`test_beast_slayer_block_live.py`).
Diagnostic double-compte LEVE (live) : orksNob snapshot `blockChance=0` -> BeastSlayer ABSENT du scalaire
GetStat(7/8) (aucun double-compte ; le runner le manquait entierement avant le port).

**Port** : (1) `BeastSlayerExtraBlockEffect` (loki.py) `create_effect_block_source_for_defense(armor)` ->
`BlockSource(chance=beastSlayerBlockChance=10, amount=beastSlayerBlockAsMaxArmorPct% x FixedArmor, block_id=chance)`,
enregistre `"BeastSlayer_ExtraBlock"` (factory). (2) Canal defenseur : agregateur `defender_effect_block_sources`
(effects/__init__.py) + helper PARTAGE `AttackDamageOperation._block_sources(tsc, tgt_effects, armor)` = base
(scalaire GetStat 7/8) + sources d'effet, appele par les 3 vecteurs (mirror du `GetMultiValueStat(7)` unique
du natif). (3) **ROLL-GATING (RE CLE, decouvert par replay-diff)** : `ApplyRandomBlockDamage @181000390`
ajoute l'id (= la chance `local_88`) d'une source ECHOUEE a `failedList` ; `CalculateBlockChances @181002350`
(rebuild PAR COUP) fait `Contains(failedList, id)` -> **EXCLUT toute source AYANT ECHOUE des coups suivants**
(une source qui REUSSIT reste jouable, ApplyRandomBlockDamage return sans AddFailedBlockId). Donc une source
de bloc est jouee chaque coup JUSQU'A son 1er echec, puis plus jamais. Porte dans
`AttackDamageOperation._run_hits` (accumulateur `failed_block` inter-coups + filtre par-coup). Preuve : orksNob
BeastSlayer (chance 10) hit1 succes + hit2 echec -> 0 roll hits 3-6 = **8 tirages RNG (pas 12)** -> replay
bit-exact. NB : `--block-target` (chance 100) NE l'exercait PAS (100% ne rate jamais -> jamais exclu -> roll
chaque coup ; c'est pourquoi le test block de base passait sans ce gating). Refacto au passage (#72) : helpers
partages `_block_sources` + `_crit_params` (dedup des 3 vecteurs normale/ability/splash).

> **RESOLU 2026-07-09 (#73) — le CRIT n'a PAS ce gating (le port etait deja correct).** RE fidele
> (decompile) : la fonction de roll `DamagePrediction.RollCritical @1810387a0` (-> `DamageCalculations.RollCritical
> @1810057b0` = `NextBool(chance)`) est SANS ETAT : chance = `GetStat(attaquant, 9)` + `GetCritChanceBonusFromEffects`,
> `<1` -> false sans tirage, sinon `NextBool` ; AUCUN input de coup precedent, AUCUN accumulateur "deja rate".
> `CalculateCriticalDamage @18102da90` = `GetStat(10)`+bonus, pur, sans RNG. Dans `ExecuteHit @180e5eff0`, le
> block appelle explicitement `OperationResult.AddFailedBlockIds` (threade par `ExecuteHits`->`RegisterBlocks`->
> HitGroup) ; il N'EXISTE AUCUN "AddFailedCrit" analogue, et la chance de crit passee chaque coup est un champ
> constant (jamais reduit apres un non-crit). Le gating du BLOCK existe PARCE QUE le block est multi-source (chaque
> source a un id -> exclusion individuelle) ; le crit est une chance UNIQUE -> rien a exclure. Chaque coup tire le
> crit INDEPENDAMMENT (deja valide bit-exact a CC=100 : RollCritical tire a CHAQUE coup, 2 tirages/coup). Le
> "comme les crits" utilisateur = analogie libre, PAS un mecanisme partage. Port `_run_hits` (crit independant
> par coup) = deja fidele, aucun changement de code. Nuance distincte (hors #73) : le natif relit `GetStat(9)`+bonus
> PAR COUP alors que le port lit `crit_chance` UNE FOIS avant la boucle -> divergerait seulement si un effet
> modifiait la crit-chance de l'ATTAQUANT EN COURS d'attaque (aucun porteur connu ; suivi en tache separee).

**(RE conserve)** c'est un ROLL de bloc SUPPLEMENTAIRE (pas un simple bonus de chance).
- `GetBlockChance @180e19120` = `GetNumberConstant(0x2d)` = `beastSlayerBlockChance` = **10%**.
- `GetBlockDamage @180e19160` = `PercentageOf(StatAmount(0x10=FixedArmor), Direct(GetNumberConstant(0x36)=100))`
  = **100% du FixedArmor COURANT** comme montant de bloc.
- `CreateAddBlockEffectBehaviour @180e18b70` = `AddExtraBlockEffectToOwner(0x5ed, Direct(chance=10), GetBlockDamage)`
  + 2 `AddOrUpdateStaticStatModifierEffect` (0x619/0x61a) gates `If(ActorHasTriggeredAbility(0x5e9), ...)`.
  i2 : « +10% chance to Block 100% of current Armour as Damage ».
Port : le moteur a un systeme de bloc (`damage_combat.py apply_random_block_damage(rng, block_sources, dmg)`
= chaine de sources, 1er succes bloque). MAIS le runner (damage.py:226/369/436) construit `block_sources`
= UNE SEULE source depuis `tsc.ctx.block_chance/block_damage` (snapshot `GetStat(7/8)` mono-valeur ;
unit_context.py:178 blockChance/blockDamage plats). Le natif utilise `GetMultiValueStat(7)`
(`CalculateBlockChances @181002350`) = LISTE de sources ; BeastSlayer ajoute une entree SEPAREE
(chance 10%, amount=100% FixedArmor, via `AddOrUpdateStaticStatModifierEffect 0x619/0x61a`) avec un
amount DIFFERENT du bloc de base. Donc porter fidelement = (a) canal MULTI-source de bloc cote defenseur
(collecter les sources de bloc des effets de la CIBLE), (b) verifier le DOUBLE-COMPTE (le snapshot
`blockChance` d'orksNob inclut-il deja le +10% de BeastSlayer ? a checker live), (c) l'ORDRE des sources
(CalculateBlockChances trie la multi-value). SLICE DEDIEE non-triviale (risque double-compte/ordre) —
NON faite. RE mecanisme = complete ci-dessus ; l'integration reste a faire proprement (defense, hors
scope attaque #68).

### Port a faire (slice wiring)
1. Classe `BeastSlayerExtraDmgEffect` (loki.py) : `create_effect_damage_bonus_for_attack` renvoie
   `for_percent_increase(True, trait_var("BeastSlayer","beastSlayerExtraDmgPct"))` gate
   `not is_ranged` (melee) ET `target_is_big_or_vehicle`. Enregistrer `"BeastSlayer_ExtraDmg"` dans factory.
2. **Threading TARGET** (comme #59 cote defenseur) : ajouter `target_is_big_or_vehicle` (ou les traits
   cible) a `create_effect_damage_bonus_for_attack` (base + 5 overrides loki.py) et
   `build_attacker_modifiers_from_effects` ; le calculer chez les 2 appelants (prediction Scene +
   runner combat `damage_model`) via HasTrait(target, 1029|1017) — le port connait deja BigTarget/Vehicle
   (engine/entities/traits/combat.py, damage_model.py).
3. **Validation** : NE PEUT PAS se faire vs worldTerminator (infanterie -> BeastSlayer=0, 'present !=
   applique'). Monter un setup avec cible **Big Target ou Vehicle** (unit_map : chercher trait 1029/1017)
   + isolation deterministe (aiPredict) pour confirmer le +20% melee.
