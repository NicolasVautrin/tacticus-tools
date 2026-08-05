# #449-r2-r4 — le spread de dégât se LIT dans `BattleConfiguration.Damage`, il ne s'écrit pas

Le port codait `spread_pct = 20` dans **13 signatures**. Le natif ne connaît ce pourcentage
**que** par sa configuration. Une BC portant une autre valeur faisait donc diverger le port — en
silence, parce que la seed versionnée porte justement `20`.

**Ce n'est plus théorique : c'est mesuré.** Même seed, même board, mêmes unités, seule la section
`BC.Damage` change :

| `BC.Damage` | natif (dégât infligé) | port corrigé | port d'AVANT (`20` en dur) | écart |
|---|---|---|---|---|
| `DamageSpreadPercentage = 20` | 9388 | 9388 | 9388 | 0 (référence) |
| `DamageSpreadPercentage = 60` | **7774** | **7774** | 9388 | **1614** |
| champ **ABSENT** | **8434** | **8434** | 9388 | **954** |
| `IgnoreDamageSpread = true` | **8434** | **8434** | 9388 | **954** |

## 1. La chaîne native, lue de bout en bout (build `rnca9r7q6c`)

```
IdunBattle.Runner.IdunRunner$$Initialize
  -> IdunBattle.Core.Services.DamageCalculations$$Init(configuration, random, state, ...)
         `configuration` = BattleConfiguration.Damage  ->  DamageCalculations+0x18   (2e argument)
  -> IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64
         pct = Fix64(*(uint*)(configuration + 0x20)) / Fix64(100)
         cache paresseux dans le Nullable<Fix64> `DamageCalculations+0x38`
         configuration == null -> FUN_1801f51f0 (NullReferenceException) : AUCUN repli
  -> IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread(damage)
         le corps du getter y est INLINE (meme sequence, meme cache)
         delta = Fix64.Round(damage * pct, AwayFromZero)
  -> IdunBattle.Core.Services.DamageCalculations$$CalculateMinDamage = Round(damage - delta, 1)
     IdunBattle.Core.Services.DamageCalculations$$CalculateMaxDamage = Round(damage + delta, 1)
         (aucun appelant DIRECT : atteints par les slots 8 et 9 de l'interface)
  -> IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64        (slots 8/9)
  -> IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw          (branche SPREAD)
```

**La signature native n'a AUCUN paramètre de spread.** C'est le fait structurant : côté natif il
n'existe aucune valeur à coder en dur, seulement une configuration à lire. Tout défaut écrit dans
une signature du port était donc, par construction, une invention.

`get_DamageSpreadPercentageFix64` n'a que des xrefs **DATA** (table de méthodes) — son corps est
inliné dans `CalculateDamageSpread`, dont les deux seuls appelants sont `CalculateMinDamage` et
`CalculateMaxDamage`. Le chemin du spread est donc **unique**.

## 2. Le champ N'A PAS de défaut natif — c'est LU, puis CONFRONTÉ

`IdunBattle.Configuration.DamageConfiguration$$.ctor` n'initialise **que** le `Dictionary` `+0x40`
(`DamageProfiles`). Aucun autre champ n'a d'initialiseur : un champ absent du JSON reste à la
valeur par défaut de son type C#, donc `DamageSpreadPercentage` absent vaut **0**, jamais 20.

Le bras `absent` le confirme en bataille : bornes natives `[8434, 8434]`, dégât 8434. **Le natif ne
fabrique pas 20.** Fabriquer `20` comme repli aurait donc recréé le même vice sous un autre nom.

⇒ Le défaut du port est **DÉRIVÉ**, pas écrit : `engine/services/damage_config.py` lit
`data/seed-bc.json` (entrée versionnée, la seed dont partent tous les runners `rl_duel build`) et
**lève** si elle est illisible. Même patron que `State.enable_obscuring_terrain` (#444), un cran
plus loin : là-bas la valeur est un littéral gardé par un test, ici elle n'est plus écrite du tout.

## 3. Le SECOND champ du même aiguillage — `#449-r2-r2` FERMÉ

`#449-r2` avait laissé ouvert : « `configuration+0x31`, le second aiguillage vers la branche plate
de `PredictAttackRaw`, n'est pas nommé ». Il l'est :

```
IdunBattle.Core.Services.DamagePrediction$$get_IgnoreDamageSpread
    this+0x10 -> +0x31           (`this+0x10` = `configuration`, posé par $$.ctor, 2e argument)
```

C'est **`BattleConfiguration.Damage.IgnoreDamageSpread`**, dans la même section, à 0x11 octets du
premier. Confronté : bras `ignore`, natif `[8434, 8434]` — bornes plates malgré
`DamageSpreadPercentage = 20`. Le port le rabat sur `spread_pct = 0`, la façon dont il modélise
déjà la branche plate (#449-r2).

## 4. Ce que le port fait maintenant

**Un seul foyer** : `scripts/python/engine/services/damage_config.py`.

* `DamageConfiguration` — mirror des deux champs (`+0x20` uint, `+0x31` bool), `from_bc(section)` ;
  un champ absent de la section vaut `0` comme le natif ; **section non fournie → `None`**, jamais
  un zéro fabriqué (tri-état).
* `default_damage_spread_percentage()` — dérivé de `data/seed-bc.json`, `lru_cache`, lève si absent.
* `resolve_spread_pct(spread_pct=None, state=None)` — l'ordre : valeur explicite (l'appelant a lu
  SON décompilé, ex. les `0` de #449-r2) → BC de cette bataille (`State`) → défaut dérivé.
  `IgnoreDamageSpread` court-circuite à `0`, **sauf** une valeur explicite.

**Le canal** : `State.damage_spread_percentage` / `State.ignore_damage_spread`, posés par
`load_state(damage_config=<BC.Damage>)` — même nature que `targeting_config` (#444) : la section
vit sur DISQUE, **aucun RPC ne la publie**.

**Les 13 littéraux ont disparu.** Les trois nommés dans l'énoncé :

| porteur | avant | après |
|---|---|---|
| `Runner.install_default_handlers` | `spread_pct: int = 20` | `= None` → foyer |
| `DamageHandler.__init__` | `spread_pct: int = 20` | `= None` → `resolve_spread_pct(spread_pct, state)` |
| `HitDamage.from_base` | `spread_pct: int = 20` | **OBLIGATOIRE** |

`from_base` est le seul traité différemment, et c'est mesuré : **il n'a aucun appelant** sous
`scripts/python` (0 site `.from_base(`). Un défaut y aurait été un littéral que rien n'exerce, donc
que rien ne peut invalider ; l'exiger force le futur appelant à dire d'où vient sa valeur.

Les dix autres portes (`UseActiveAbility`, `execute_additional_hits`, `AttackDamageOperation.
execute`, `execute_normal_like`, `calculate_damage_spread`, `spread_to_min_max`,
`get_base_damage_fix64`, `predict_attack_raw`, `get_multi_hit_attack_prediction`,
`get_attack_prediction`) passent au même régime `= None`. Celles qui ont un `state` le résolvent
avec lui ; les fonctions pures laissent le `None` descendre jusqu'au foyer.

⚠ `UseActiveAbility` résout **à l'exécution**, pas à la construction : l'arbre DSL est bâti avant
toute bataille (aucun `State`), et le natif lui aussi lit sa configuration au moment du calcul.

**Le seul `20` restant du rail est celui de `data/seed-bc.json`.**

## 5. La garde, et sa contre-épreuve

`probe_449r2_spread_inventory.py` classait les défauts par VALEUR (`20` attesté). Il classe
désormais par **RÉGIME**, dérivé de l'AST : `REQUIS` / `LU_BC` (défaut `None`) / `LITTERAL` /
`DYNAMIQUE`. Nouveau motif rouge **`LITTERAL DE SPREAD REVENU`** : *tout* défaut entier non nul sur
une porte de variance rougit — le seul entier légitime est `0`, et seulement là où le décompilé
impose la variance nulle (mode `amount`, `Nullable<AttackDamageBehaviourOptions>` vide).

⚠ Cette garde **ne peut pas être blanchie par une attestation** : elle est évaluée avant
`EXPECTED_DEFAULT`, et le cas d'auto-test `C2ter` le vérifie dans les deux sens (un `20` attesté
rougit quand même ; un `0` attesté non).

Quatre cas d'auto-test neufs, joués à chaque run du cliquet : `C2bis` exige que les **quatre
régimes se classent différemment** — sans quoi la garde ne pourrait pas mordre.

**Contre-épreuves jouées le 2026-08-05, mutation VÉRIFIÉE PAR RELECTURE AST à chaque fois** (le
`git diff` ne suffit pas : un patch qui ne matche pas rend un vert menteur) :

| mutation | `probe_449r2` | garde pytest |
|---|---|---|
| `install_default_handlers(spread_pct = None → 20)` | **ROUGE**, par 2 voies | — |
| `calculate_damage_spread(spread_pct = None → 20)` | — | **2 failed / 8 passed** |
| `load_state` : `_dmgcfg = DamageConfiguration.from_bc(...)` → `None` (canal débranché) | — | **1 failed / 9 passed** |
| aucune mutation | **VERT** | **10 passed** |

Après chaque contre-épreuve, `git diff` sur `scripts/python/engine` est **vide**.

## 6. Validation

**Le montage qui sépare** — `probe_449r2r4_spread_from_bc.py`, quatre bras qui ne diffèrent que par
la section `BC.Damage` d'une copie de `data/seed-bc.json` (le rattrapage `_load_seed_bc` ne touche
que `BC.Abilities`/`BC.Utilities`, et `normalize-bc` ne touche pas la section globale `Damage` —
donc le patch survit ; c'est d'ailleurs *démontré* par le fait que les bornes natives bougent).

`ultraCalgar` (2 coups) sur `tauCrisis`, board `MC1_67`, tuiles `2,5`/`2,6` **choisies** (on déplace
les unités, on ne subit pas la géométrie de spawn), `--hp-target 900000` (cible increvable ET sans
armure → le dégât infligé EST le tirage brut), crit et block forcés à 0.

Quatre étages, et le probe **REFUSE de conclure** si le premier ne tient pas :

1. **identification** — le centre `(min+max)/2` est le même dans les quatre bras (8434, 8433, 8434,
   8434 : ±1 de matérialisation de borne) ⇒ même base, l'écart n'est imputable qu'au spread ;
2. **natif** — demi-amplitude observée vs `centre × pct/100` : 1686 vs 1686,7 · 5061 vs 5060,1 ·
   0 vs 0 · 0 vs 0. Le natif SUIT le champ ;
3. **port** — le pct obtenu par le canal RÉEL (BC → `load_state` → `State` → `Runner` →
   `DamageHandler`) : 20 · 60 · 0 · 0 ;
4. **face COMBAT** — replay-diff, `state.rng` calé sur le MT live : le port corrigé reproduit le
   dégât infligé **4 bras sur 4**, bit-exact.

**La non-dégénérescence est vérifiée, pas supposée** : le probe imprime `REGIME DEGENERE` quand les
deux modèles coïncident. Ils coïncident sur le bras `bc20` — normal, c'est la référence — et
**diffèrent de 1614 / 954 / 954** sur les trois autres. Le PRNG est le même dans les deux modèles
(même état MT de départ) : ce qui change est la BORNE, pas la séquence.

**Tests rejoués** (ciblés ; 4 en parallèle) :

| fichier | résultat |
|---|---|
| `tests/test_449_r2_spread_face_combat_offline.py` | **10 passed** (7 avant) |
| `tests/engine/runner/test_runner_attack_live.py` | **2 passed** |
| `tests/engine/runner/test_damage_roll_live.py` | **2 passed** |
| `tests/engine/runner/test_psyker_splash_live.py` | **1 passed** |
| `tests/engine/runner/test_cursed_plague_bell_attack_live.py` | **7 passed** |
| `tests/engine/runner/test_haze_of_corruption_transfer_live.py` | **9 passed** |
| `tests/engine/runner/test_damage_decomp_live.py` | **1 passed** |
| `tests/engine/runner/test_normal_attack_bounds_rounding_live.py` | **1 passed** |
| `tests/engine/runner/test_sky_strike_live.py` | **6 passed** |

## 7. Résidus NOMMÉS

* **`#449-r2-r4-r1`** — **le canal `damage_config` n'est alimenté par AUCUN appelant réel.** Seuls
  le probe et la garde le passent ; tous les runners de production retombent sur le défaut dérivé
  de la seed. C'est **exact tant qu'ils partent de `data/seed-bc.json`**, et faux dès qu'un montage
  utilise `--seed-bc` avec une section `Damage` modifiée. Même trou que `targeting_config` (#444) :
  la BC vit sur disque, aucun RPC ne la publie. Ce qui le fermerait : un canal ambiant à la
  `bind_live_rpc` qui retienne le chemin de seed BC du build et fasse lire sa section `Damage` par
  `load_state`. **Le probe #449-r2-r4 est la preuve que le montage marche** — il ne manque que le
  câblage par défaut.
* **`#449-r2-r4-r2`** — **~40 fichiers de tests passent encore `install_default_handlers(20)`
  explicitement.** Inerte (la seed vaut 20), et *correct* pour un runner monté sur la seed. Mais un
  test qui monterait une BC patchée en gardant ce `20` mentirait en silence — exactement la forme
  du vice, déplacée dans le harnais. Un seul a été migré (`test_runner_attack_live.py`, le
  replay-diff de référence) ; les migrer tous est mécanique mais large, donc hors périmètre ici. La
  garde ne les voit pas : elle balaie `engine/`, pas `tests/`.
* **`#449-r2-r4-r3`** — **`IgnoreDamageSpread` est rabattu sur `spread_pct = 0`, ce qui n'est pas
  STRICTEMENT la branche plate native.** `PredictAttackRaw` y fait
  `MinMaxDamageFix64(d, maxOverride ?? d)`, alors que `spread_pct = 0` passe par
  `GetBaseDamageFix64`, dont le haut est `d + extraMaxDamage`. Les deux coïncident **si et seulement
  si** `ExtraMaxDamage == 0` — ce qui est le cas du montage confronté (bras `ignore` : natif 8434 =
  port 8434). **NON CONFRONTÉ en régime `ExtraMaxDamage != 0`** (stat 0x19, porteurs à recenser).
  Même réserve pour le bras `absent`, qui emprunte le même chemin. C'est la modélisation
  préexistante de la branche plate (#449-r2), pas une régression introduite ici.
* **`#449-r2-r4-r4`** — **les AUTRES champs de `BC.Damage` portent le même vice**, et le foyer est
  prêt à les accueillir. Recensés en dur dans le port : `_KNOCKBACK_PCT = 20`
  (`operations/displace.py`, `KnockbackPercentage` `+0x24`), `armor_percentage = 50`
  (`predict.py::CombatConstants`, `ArmorPercentage` `+0x1c`), et non portés/non lus :
  `ElevationBonus`, `ClassBonus`, `AffinityBonus`, `RangedInMeleeReductionPercentage`,
  `TrenchReductionPercentage`, `OverkillDmgPctOfHealth`, `AllowOverkill`,
  `DamagedMachineDestroyChanceIncrease`. Chacun a son getter natif nommé
  (`$$get_ArmorPercentageFix64`, `$$get_KnockbackPercentageFix64`, …) et le même montage
  (une section `BC.Damage` écrite) les confronte. **Non traités : hors périmètre de ce résidu.**
* **`#449-r2-r4-r5`** — **`predict.py::CombatConstants.from_bc` est un SECOND lecteur de la même
  section**, avec ses propres défauts littéraux (`armor_percentage = 50`,
  `damage_spread_percentage = 20`) et `.get(..., 20)` en repli. Il appartient à la couche prédiction
  iso-AI (« PARTIE 2 — couche RÉSOLUTION réelle, NON utilisée par l'iso-AI ») et n'alimente pas le
  rail corrigé ici, mais il duplique le foyer. À fusionner dans `damage_config` quand `#449-r2-r4-r4`
  sera traité — les deux touchent les mêmes champs.

**Ce qui n'est PAS couvert** : la face `frida/` (TypeScript) n'est pas balayée ; le régime
ÉLÉVATION (hérité `#449-r4`) ; l'angle mort des noms d'appel ambigus (`#449-r2-r5-r1`, inchangé) ;
et la mesure porte sur **un** couple attaquant/cible sur **un** board — ce qui suffit ici parce que
l'étage est identifié par une identité algébrique vérifiée (centre constant + amplitude ∝ pct), pas
par un scalaire ajusté.
