# Le canal CRIT n'etait aveugle que COTE PORT — `N14` ferme, et la face CRIT de 1223 portee

> **Build** `gqfc5mff6c`. Suite directe de `case-ischarging-hits-channel` (canal COUPS), dont le
> residu `N14` disait : « le canal offline **n'a aucun parametre de contexte** ; poser la face la
> rendrait INCONDITIONNELLE ». La premisse etait juste **sur le port** et fausse **sur le natif** —
> et c'est cette dissymetrie qui debloque le cas.

---

## 1. La question binaire, et sa reponse

> Le canal **CRIT** des effets offline peut-il recevoir un contexte (positions, charge, cible), ou
> est-il structurellement aveugle ?

**Il peut. Le natif le lui donne deja ; c'est le PORT qui le jetait.** Le canal n'est donc pas a
contourner, il est a **instrumenter** — exactement comme le canal COUPS l'a ete par
`build_hits_board`.

Consequence : la face CRIT de `SagaOfTheWarriorBorn_Owner` (1223) est portable **avec son gate**,
et elle l'est ici.

---

## 2. RE — la chaine native, appelant par appelant

### 2.1 L'effet : calque EXACT de la face COUPS

`IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateCritDamageBonus`, lu
verbatim, mis en regard de `…$$CreateEffectHitsBonusForAttack` (deja porte) :

```
CreateEffectHitsBonusForAttack                      CreateCritDamageBonus
  get_OwnerIsCaster(ctx@+0x48)                        get_OwnerIsCaster(ctx@+0x48)
  & IsCharging(owner@0x148, target@0x178)             & IsCharging(owner@0x148, target@0x178)
  ConfigVar(0x13, GetAbilityState(effect), cfg@+0x60) ConfigVar(0x42, GetAbilityState(effect), cfg@+0x60)
  EffectBonus.ForAddition(trigger, amount,            EffectBonus.ForAddition(trigger, amount,
                          <AbilityOrEffect +0x14..+0x2c>)                     <idem>)
```

Les deux corps sont **instruction pour instruction identiques** ; la SEULE difference est la cle du
`ConfigVar` : **0x13** (`extraHits`) contre **0x42** (`extraCritDmg`). Deux noeuds trigger, pas
trois : ni `IsNormalAttack`, ni `IsMeleeAttack`.

⚠ Les deux variables n'ont PAS le meme regime de magnitude. `gameconfig` :
`variablesAffectedByRarityBonus = ["extraCritDmg"]` — **seule `extraCritDmg` est scalee par le
multiplier**. Recopier le traitement de `extraHits` (multiplier passe mais inerte) aurait produit
une magnitude fausse d'un facteur 2 sur le porteur mesure.

### 2.2 Le canal : d'ou vient le contexte

```
IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage(this, attaquant, cible, p4, cfg)
    critDmg = UnitExtensions$$GetStat(attaquant, 10, 0)
    bonus   = GetCritDamageBonusFromEffects(this, attaquant, cible, <copie 0x14 octets de cfg>)
    cd      = Math.Max(0, critDmg + bonus)
    ...
IdunBattle.Core.Services.DamagePrediction$$GetCritDamage(this, attaquant, cible, cfg)   # meme tete
```

et, dans le canal lui-meme :

```
IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects(this, attaquant, cible, cfg)
    IdunBattle.Entities.Abilities.AbilityEntities$$.ctor(&entities, attaquant, attaquant, cible,
                                                         0,0,0,0,0,0,0,0,0, &cfgNullable, ...)
    foreach (porteur, effets) in <effets actifs>:
        foreach effetId in effets:
            entities.<champ> = GetEntity(effetId)
            bonus = <slot 0x22>(effet, entities)          # = BaseEffect$$CritDamageBonus
            if (bonus.HasValue) list.Add(bonus.Value)
    return sum(b.addition - b.subtraction for b in list)
```

**L'attaquant est passe DEUX FOIS** (positions 1 et 2 du ctor = `caster` et `owner`), la cible une
fois. Le selecteur `owner@0x148` rend donc l'attaquant, `target@0x178` la cible, et
`get_OwnerIsCaster` est VRAI par construction. `IsCharging(owner, target)` est **pleinement
evaluable** — comme le sont `HasTrait(target, …)`, `IsNormalAttack`, `CurrentAbilityIs(...)`.

`IdunBattle.Entities.Effects.BaseEffect$$CritDamageBonus` est le wrapper standard : il
`InitializeBonusCacheIfNeeded`, lit le `Nullable<EffectBonus>` cache a `effect+0x408`, evalue son
trigger contre les `entities` recues, et rend `(addition, subtraction)` — meme forme que
`BaseEffect$$HitsBonusForAttack` / `$$DamageBonusForAttack`.

⇒ **Verdict : le canal CRIT natif reçoit exactement le meme contexte que le canal COUPS.** Le
residu `N14` avait raison de ne pas poser la face sur un canal muet, et tort de croire le canal
muet par nature.

---

## 3. Ce que le canal OFFLINE recevait, et ce qui manquait

| etage | AVANT | APRES |
|---|---|---|
| face d'effet | `BaseEffect.create_effect_crit_damage_bonus_for_attack(self)` — **zero parametre** | `(self, att_ctx=None)` |
| agregateur | `crit_damage_bonus_from_effects(effects)` | `(effects, att_ctx=None)` |
| facade COMBAT | `AttackDamageOperation._crit_params(ctx, attacker_effects)` — ne connait ni `state` ni les identites du coup | `(ctx, attacker_effects, state=None, att_id=None, tgt_id=None)` ; **c'est LA que l'`att_ctx` est construit** |
| vecteurs | `damage_ops/{normal,normal_like,ability}.py` passaient `(ctx, active)` | passent en plus `state, attacker_id, target_id` |

**D'ou vient le contexte, et pourquoi de la.** `_crit_params` est a l'axe CRIT ce que
`runner/damage_model.py::build_hits_board` est a l'axe COUPS : **la facade COMBAT PARTAGEE des trois
vecteurs d'attaque**. Un seul point de calcul, pas un par call-site — c'est le patron impose par le
canal COUPS, et c'est aussi la place NATIVE (le natif batit son `AbilityEntities` DANS
`GetCritDamageBonusFromEffects`, a partir des deux entites que `CalculateCriticalDamage` lui passe).
Les vecteurs ne transportent que des IDENTITES ; aucun d'eux ne calcule le predicat.

Le gate **reutilise le foyer**, il ne le duplique pas :

```
engine/battle_query.py::is_charging                       # le predicat, foyer UNIQUE
  <- runner/damage_model.py::battle_query_is_charging     # pont ECS
       <- damage_model.py::attacker_modifiers             # canal DEGAT   (case-r32)
       <- damage_model.py::build_hits_board               # canal COUPS   (case-ischarging-hits)
       <- operations/damage.py::_crit_params              # canal CRIT    (CE CAS)
  <- effects/base.py::is_charging_attack(att_ctx)         # la lecture, forme POSITIVE
```

Polarite : `is_charging_attack` est VRAI **seulement si la charge est PROUVEE**. Contexte non
threade ⇒ aucune contribution — la degradation ne peut pas etre permissive, et c'est aussi le plus
fidele (`BattleQuery$$IsCharging` commence par `AreEntitiesAdjacent`, donc sans positions il rend
FAUX, jamais VRAI).

---

## 4. Rendre la face OBSERVABLE — le crit d'un heros n'existe pas dans un build frais

`extraCritDmg` ne mord que sur un coup qui CRITE. Un heros construit par `rl_duel build` a
`CritChance = 0` : son crit vient de ses items `I_Crit`, que la normalisation strippe. Sans levier,
la face serait portee et jamais confrontee.

Levier : **`--crit 100,700`** (`_patch_combat_stat` sur les templates `Units` des p-units) — tout
coup crite, `GetStat(10) = 700`. Le crit du COMBAT s'ajoute a la BASE d'attaque **avant** spread
(`eff_attack = attack + critDamage`), donc un `+extraCritDmg` manquant deplace **toutes** les
valeurs per-coup, pas seulement leur nombre.

Montage : `spaceBlackmane` <<Ragnar>> (HERO du pool, porteur du passif des le debut de bataille),
harnais `_charge_regime.py` **tel quel** (son ordre de poses corrige est ce qui empeche le montage
de charger la cible par accident — cf. `case-ischarging-hits-channel` §6bis).

Magnitude effective mesuree : `extraCritDmg[level 50] = 443`, multiplier du porteur **200 %** ->
**+886**. La face COUPS du meme effet vaut `extraHits[50] = 3`, NON scalee.

---

## 5. Mesure — 3 regimes x 4 colonnes, `probe_ischarging_saga_crit.py`

`MC1_67` / seed 777. `shipped` = le port livre ; `off` = la face CRIT desactivee (l'etat PRE-FIX) ;
`always` = le gate court-circuite (le bonus rendu INCONDITIONNEL — la regression exacte que `N14`
nommait). Les deux bornes sont ce qui rend chaque MATCH probant.

```
[CHARGE] face CRIT : 1 appel(s) [(True, 886)]
[CHARGE] live     n=10 [3231, 3841, 3408, 3292, 4108, 4082, 3747, 3073, 3110, 3510]
[CHARGE] shipped  n=10 [3231, 3841, 3408, 3292, 4108, 4082, 3747, 3073, 3110, 3510]  OK
[CHARGE] off      n=10 [2611, 2415, 3124, 2762, 2902, 2120, 2873, 2511, 2754, 2508]  MISMATCH
[CHARGE] always   n=10 [3231, 3841, 3408, 3292, 4108, 4082, 3747, 3073, 3110, 3510]  OK
[CHARGE] VERDICT shipped=OK (discriminant: oui)

[STEP_ADJACENT] face CRIT : 1 appel(s) [(False, None)]
[STEP_ADJACENT] live     n=7 [2437, 2193, 2096, 2005, 2428, 1819, 2260]
[STEP_ADJACENT] shipped  n=7 [2437, 2193, 2096, 2005, 2428, 1819, 2260]  OK
[STEP_ADJACENT] off      n=7 [2437, 2193, 2096, 2005, 2428, 1819, 2260]  OK
[STEP_ADJACENT] always   n=7 [2715, 3290, 3012, 2553, 2788, 2518, 3344]  MISMATCH
[STEP_ADJACENT] VERDICT shipped=OK (discriminant: oui)

[NO_STEP] face CRIT : 1 appel(s) [(False, None)]
[NO_STEP] live     n=7 [1941, 2124, 1688, 2096, 1865, 2052, 2004]
[NO_STEP] shipped  n=7 [1941, 2124, 1688, 2096, 1865, 2052, 2004]  OK
[NO_STEP] off      n=7 [1941, 2124, 1688, 2096, 1865, 2052, 2004]  OK
[NO_STEP] always   n=7 [2734, 2965, 2641, 3423, 3287, 3102, 2559]  MISMATCH
[NO_STEP] VERDICT shipped=OK (discriminant: oui)
```

Lecture, ligne a ligne :

* **`CHARGE`** — `off` MISMATCHE : le `+886` est **REQUIS**, le match de `shipped` n'est pas une
  coincidence. C'est le cas ROUGE avant le fix.
* **`STEP_ADJACENT`** — le caster BOUGE (`UnitFlag.Moved` VRAI) mais la cible etait DEJA adjacente,
  donc `UpdateCharging` ne l'inscrit pas : `charged=[]`, `IsCharging` FAUX. `shipped` == `off` ==
  live, et `always` MISMATCHE. **C'est le TEMOIN d'inconditionnalite** : il prouve que la face
  posee n'accorde rien ici, ce que `N14` redoutait par-dessus tout.
* **`NO_STEP`** — bit-exact des deux cotes du fix, `always` MISMATCHE quand meme : le regime deja
  juste avant le port n'a pas bouge, et il n'est pas vide pour autant.

### 5.1 Le canal est VIVANT — compte des appels

`face CRIT : 1 appel(s)` sur **chacun** des trois regimes, avec le contexte recu affiche
(`(True, 886)` en charge, `(False, None)` sinon). Un canal branche mais jamais emprunte rendrait des
verts creux ; ici la face est effectivement APPELEE, et l'`att_ctx` qu'elle recoit porte la bonne
valeur. Un appel par ATTAQUE (et non par coup) est la place documentee du port : le natif relit
`CalculateCriticalDamage` par coup, mais aucune entree ne varie a l'interieur d'une attaque
(`operations/damage.py`, en-tete).

### 5.2 Generalisation — 2e couple (board, seed)

`C1_25` / seed 31337, cibles `orksNob,tyranTyrantGuard` : memes verdicts sur `CHARGE` et
`STEP_ADJACENT` (tests `test_charge_other_board` / `test_step_adjacent_other_board`).

---

## 6. Epreuve du fix par MUTATION adversariale — DEUX vues ROUGES

### 6.1 Mutation A — etat PRE-FIX (la face CRIT ne contribue jamais)

Un `return None` en tete de `create_effect_crit_damage_bonus_for_attack` de 1223, rien d'autre.
Les DEUX boards tombent, sur la valeur per-coup :

```
E   AssertionError: CHARGE : le port n'applique pas le +extraCritDmg de charge --
E   live n=10 [3231, 3841, 3408, 3292, 4108, 4082, 3747, 3073, 3110, 3510]
E   offline n=10 [2611, 2415, 3124, 2762, 2902, 2120, 2873, 2511, 2754, 2508]
E   assert [2611, 2415, ...02, 2120, ...] == [3231, 3841, ...08, 4082, ...]
E     At index 0 diff: 2611 != 3231

E   AssertionError: CHARGE (C1_25/31337) :
E   live=[2505, 2144, 2665, 2205, 2941, 2104, 2948, 2228, 2594, 2969]
E   offline=[2091, 1902, 2051, 1579, 1471, 1658, 1890, 1478, 1504, 1455]
E     At index 0 diff: 2091 != 2505
FAILED test_ischarging_saga_crit_live.py::test_charge_grants_extra_crit_damage
FAILED test_ischarging_saga_crit_live.py::test_charge_other_board
```

Le **NOMBRE** de coups est identique des deux cotes (n=10 partout) : la face COUPS, livree par
`case-ischarging-hits`, tient. La divergence est localisee au **crit**, etage par etage — aucun
scalaire fitte.

### 6.2 Mutation B — le CANAL, gate remplace par le proxy `has_moved`

`_crit_params` pose `unit_has_moved(state, att_id)` a la place de
`battle_query_is_charging(state, att_id, tgt_id)`, tout le reste inchange. Resultat :
**exactement les deux tests `STEP_ADJACENT` tombent (les deux boards)** ; `CHARGE` et `NO_STEP`
restent VERTS.

```
E   AssertionError: la face CRIT doit etre APPELEE avec `is_charging=False` (canal vivant,
E   gate ferme) ; trace=[(True, 886)]

E   AssertionError: STEP_ADJACENT (C1_25/31337) :
E   live=[1246, 1246, 1619, 1449, 1657, 1667, 1488]
E   offline=[1923, 2135, 1914, 1857, 1643, 2219, 2404]
E     At index 0 diff: 1923 != 1246
FAILED test_ischarging_saga_crit_live.py::test_step_adjacent_grants_no_crit_bonus
FAILED test_ischarging_saga_crit_live.py::test_step_adjacent_other_board
2 failed, 6 passed
```

La trace `[(True, 886)]` est litterale : le proxy **declare la charge et verse 886** la ou le natif
ne verse rien. La garde discrimine donc le **GATE**, et rien d'autre — ni la magnitude, ni le canal,
ni le niveau. Les deux mutations sont revertees (`git diff` sans occurrence de `MUTATION`).

---

## 7. Ce qui n'est PAS couvert

* **L'axe DEFENSEUR du meme canal** — residu NEUF **`N17`**. `crit_damage_bonus_from_effects` ne
  balaie que les effets de l'ATTAQUANT ; le natif enumere aussi ceux d'autres entites :
  `IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$CreateCritDamageBonus`
  = `ForSubtraction(get_OwnerIsTarget, GetCritDmgReductionAmount(), AbilityOrEffect(0x5b8))` vit sur
  la CIBLE (meme famille : `TalismanOfRage_`, `NetherRealmCasket_`, `SupaCyborkBody_`). **NO-OP
  aujourd'hui** (aucune de ces classes n'est portee), donc pas une regression — mais un axe absent.
* **La face CHANCE de crit** (`GetCritChanceBonusFromEffects` /
  `create_effect_crit_chance_bonus_for_attack()`) reste **sans contexte**, volontairement : aucun
  effet porte ne l'override, changer sa signature sans consommateur serait du port speculatif. Le
  debloqueur est le symetrique exact de celui-ci (meme `att_ctx`, meme foyer). Compte dans `N17`.
* **La face PREDICTION** de ce canal **n'existe pas** : `engine/playbook/` ne modelise aucun crit
  (zero reference a `CRIT_DAMAGE`), donc il n'y a pas de second cote a cabler ici — a l'inverse du
  canal COUPS, ou `playbook/prediction/normal_attack.py` portait la moitie du travail.
* **Le vecteur ABILITY** thread desormais le contexte, mais la famille ABILITY force
  `(0, 0, False)` juste apres (`AbilityDamageOperation$$ExecuteHit` n'a AUCUN chemin crit natif,
  #45f) : seule la famille ATTACK peut l'exercer. Aucun porteur actuel de 1223 n'attaque par une
  ability famille ATTACK (l'active de Ragnar, `WarHowl` 1106, est un buff) -> **structurel, non
  observable**, comme la face ability du canal COUPS.
* **Le pas per-COUP** : le natif appelle `CalculateCriticalDamage` a chaque coup, le port calcule
  `_crit_params` une fois par attaque. Aucune entree ne varie a l'interieur d'une attaque
  aujourd'hui (`is_charging` inclus : ni le caster ni la cible ne bougent entre deux coups), mais un
  futur effet qui muterait le contexte EN COURS d'attaque exposerait l'ecart. Residu deja documente
  en tete d'`operations/damage.py`, inchange.
* **Les 4 consommateurs restants du canal COUPS** (`N16`) et la **branche charge de
  `FeederTendrils_NormalAttack`** (`N15`) : hors perimetre, inchanges.
