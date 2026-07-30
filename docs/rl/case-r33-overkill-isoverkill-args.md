# R33-b — les trois champs « non descendus » du `DealDamageInfo` étaient des noms manquants

**Build** `gqfc5mff6c` · **fermé le 2026-07-28** · gardes : `scripts/python/tests/engine/runner/test_overkill_gate_live.py` (8 tests) · montage : `scripts/python/probe_178_overkill_gate.py`

## 1. Le résidu hérité, et pourquoi son cadrage était le vrai défaut

La PR #170 (case #178) refermait le fork `is_overkill` et laissait ce résidu :

> `allow_flag`/`default_flag`/`extraDamage` du `DamageData` (`@+0x2c`/`@+0x1c`/`@+0x18`) **ne
> descendent pas jusqu'au chokepoint de mort** → paramètres exposés, passés à 0.

Le cadrage suggérait des champs exotiques, difficiles à atteindre, dont le seul porteur connu serait
`FlailSwing`. **C'est faux, et c'est le nommage qui l'a caché** : `default_flag`, `allow_flag`,
`cond`, `suppress`, `extra_damage` étaient des PLACEHOLDERS choisis par le port faute de signature.

La signature est pourtant lisible **hors Ghidra**, dans la table de symboles versionnée
(`data/symbols/gqfc5mff6c/frida/methods.tsv`, colonne « params ») :

```
DamagePrediction.IsOverkill(target:IEntity, hitDamage:int, deniedDamage:int, isCritical:bool,
                            isForceOverkill:bool, targetHealthBeforeAttack:Nullable<int>,
                            minimumHealth:Nullable<int>) -> bool          # surcharge d'INSTANCE
DamagePrediction.IsOverkill(targetInitialHealth:int, healthDamage:int, isCritical:bool,
                            isForceOverkill:bool, isPreventOverkill:bool, allowOverkill:bool,
                            overkillDmgPctOfHealth:int, targetMinimumHealth:Nullable<int>)  # PRIVÉE
```

Correspondance :

| placeholder du port | nom natif | offset `DealDamageInfo` |
|---|---|---|
| `default_flag` | **`isCritical`** | `@+0x1c` |
| `allow_flag` | **`isForceOverkill`** | `@+0x2c` |
| `extra_damage` | **`deniedDamage`** | `@+0x18` |
| `cond` | `allowOverkill` | config DI `DamagePrediction+0x10 @+0x30` |
| `threshold_pct` | `overkillDmgPctOfHealth` | config DI `@+0x34` |
| *(absent)* | `targetMinimumHealth` | `HealthComponent.MinimalHealth@+0x1c` |

**Preuve d'offset, indépendante de la signature** : l'épilogue de
`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` recopie VERBATIM
`DealDamageInfo@+0x1c → DamageAppliedResult.didCrit@+0x12` et
`DealDamageInfo@+0x2c → DamageAppliedResult.isForceOverkill@+0x14`, à côté de
`didOverkill@+0x13` (le résultat de l'appel). Les deux lectures concordent.

## 2. Ce que le corps privé fait réellement

```
if (!allowOverkill) return false;
if (targetMinimumHealth.HasValue && targetMinimumHealth.Value >= 1) return false;
if (targetInitialHealth <= healthDamage && isForceOverkill) return true;
if (!isPreventOverkill && targetInitialHealth <= healthDamage) {
    pct = (int)((healthDamage - targetInitialHealth) / targetInitialHealth * 100);   // Fix64
    return pct < overkillDmgPctOfHealth ? isCritical : true;
}
return false;
```

**`isCritical` est la VALEUR DE RETOUR du cas « létal mais sous le seuil ».** Ce n'est pas un drapeau
par défaut : c'est la règle de jeu « un coup critique qui tue EST un overkill », même très
en-dessous de `overkillDmgPctOfHealth` (= 100, donc « 2 × PV »). Le port répondait 0 : **dégradation
permissive** — ni erreur, ni crash, aucun test rouge, et un moteur qui sous-marque massivement
l'overkill (tous les kills critiques entre 1 × et 2 × PV).

## 3. Granularité : pourquoi le port re-joue la séquence des coups

La surcharge d'instance est appelée **PAR COUP**, mais avec `targetHealthBeforeAttack` = les PV au
DÉBUT DE L'ATTAQUE :

```
hitDamage += deniedDamage;
if (targetHealthBeforeAttack.HasValue) {
    hitDamage    += (targetHealthBeforeAttack.Value - currentHealth) + unitComponent@+0x24;
    currentHealth = targetHealthBeforeAttack.Value;
}
```

Le terme `(initialHealth − currentHealth)` ré-agrège le dégât des coups précédents : l'argument
comparé est donc le **cumul de l'attaque**. Le chokepoint par-attaque du port est de ce fait un
mirror EXACT de l'appel d'un coup donné — mais `isCritical` et `deniedDamage`, eux, **varient d'un
coup à l'autre**, et `ApplyDamageOperation$$Execute+0x17d5` pose `UnitFlag.Overkilled` dès qu'UN
coup rend vrai. `AttackDamageOperation._did_overkill` boucle donc sur
`(dégât santé du coup, denied AVANT le coup, crit du coup)` — l'alternative « un seul appel avec
`did_crit` de l'attaque » sur-accorderait (crit sur un coup non létal, total final sous le seuil).

## 4. Mesure live — deux observables indépendants, trois régimes

Régime commun : PV de la victime tunés pour que **tout** le dégât soit létal ET sous le seuil
(`PV ≤ dégât < 2 × PV`) ⇒ le verdict ne dépend plus du tirage, seulement des flags.

| régime | tueur | observable | live | port |
|---|---|---|---|---|
| `crit` | `emperNoiseMarine` (crit 100/1) | crescendo `TerrifyingCrescendo` (`On(UnitDeath) & TargetIsOverkilled`) | 0 → **1** | overkill ✔ |
| `nocrit` | `emperNoiseMarine` (crit 0/0) | idem, **mêmes PV, dégât mesuré sans crit** | 0 → **0** | pas overkill ✔ |
| `revive-crit` | `ultraInceptorSgt` (crit 100/1) | `Narthecium` revive « unless Overkilled » (`On(PreUnitDeath)`) | victime **morte** | morte ✔ |
| `revive-nocrit` | `ultraInceptorSgt` (crit 0/0) | idem | victime **revive** | revive ✔ |
| `revive-flail` | `deathBlightlord` **sans aucun crit** | idem | victime **morte** | morte ✔ |

* Le corps 2-args supprimé par #178, et tout corps passant `isCritical = 0`, répond « pas overkill »
  **des deux côtés** de la paire `crit`/`nocrit` — la paire le réfute.
* `revive-*` est **indépendant** : autre consommateur, autre vecteur d'événement, et surtout autre
  tueur. C'est nécessaire pour l'ATTRIBUTION : `emperNoiseMarine` porte le trait `ThrillSeekers`
  (1056), dont le rider (« defeats an enemy with a Crit → always overkilled », forcé par
  `PredictAttackRaw`) pourrait expliquer le montage A. `ultraInceptorSgt` ne le porte pas.
* `revive-flail` isole **`isForceOverkill`** : FlailSwing pose `alwaysOverkilled`
  (`AttackOptions@+4`, 8ᵉ argument de `DSLFactory$$AttackWithAttackDamage`), aucun crit n'est
  possible (`CritDamage = 0` ⇒ `CouldCrit` faux), et la victime n'est pourtant pas revive.

### Piège de mesure attrapé en cours de route (à ne pas re-marcher dedans)

Le régime `revive-flail` a d'abord été tuné sur `aiPredict` — qui ne rend que la **preview de
l'ATTAQUE NORMALE** (`GetAllPredictions`). Sur FlailSwing il annonçait `[9393, 14091]` alors que le
vecteur inflige **20884**. Les PV tunés à 9393 donnaient `dégât ≥ 2 × PV` = **overkill NATUREL**, et
le test passait **sans que le flag serve à rien**. Le symptôme d'origine est visible en espionnant
`_did_overkill` : `damage = 20884` pour `hp_before = 9393`.

> **Mise à jour #268 (2026-07-30) — la source du dégât a changé DEUX fois.** Le correctif d'alors
> (`replay_damage_total`, rejeu OFFLINE sur une cible aux PV portés à 10⁷) faisait calibrer le
> montage par le PORT même qu'il éprouve. Et le tuning `aiPredict` des autres régimes est devenu
> franchement FAUX à la migration `rnca9r7q6c` : le décodeur rendait `[1,100]` pour tout couple, ce
> qui a fait **skipper** cinq de ces tests en accusant le roster. Les deux passes 1 sont remplacées
> par **`_measure_live_damage`** — victime increvable, cast **en live**, `hp_avant - hp_après` —, le
> tirage étant reproductible à seed et séquence égales. Les PV du tableau §4 valent donc désormais
> **2256** (et non 2178), pour un dégât mesuré de **2774** avec crit / **2375** sans.
> Détail : `case-268-decodeur-prediction-perime.md`.

## 5. Verdicts sur les deux gates « quiescents »

* **`CanBeOverkilled` — STRUCTUREL, pas un trou de montage.** `python unit_map.py find --trait
  Steppable` rend **27 porteurs, tous à `HP 0`** (25 npc de décor / power-ups + les deux decoys
  `genesDecoy` / `genesSmnDecoy`). Le gate de mort du port est `hp_before > 0 and hp_after == 0` :
  une entité à 0 PV ne l'atteint jamais. Le natif ne les tue pas par dégât mais par ÉCRASEMENT
  (`DamageReason.Steppable = 2`, chemin `movement.py::_kill_steppable_units`). **Aucun scénario ne
  peut distinguer ce gate sur la face COMBAT** — il est porté parce que le natif le porte.
* **`targetMinimumHealth` — quiescent par construction au chokepoint de mort.** Un plancher de PV
  actif empêche `HealthComponent.reduce` d'amener les PV à 0, donc la séquence de mort n'est jamais
  atteinte tant qu'il tient. Il compte en revanche sur la face PRÉDICTION.

## 6. Résidus NEUFS, nommés

1. **`unitComponent@+0x24`** — l'int qui suit immédiatement `MinimalHealth@+0x1c` dans le MÊME
   composant s'ajoute au total d'overkill. HYPOTHÈSE (structure, non mesurée) : accumulateur du
   dégât refusé par le plancher de PV. Nul tant qu'aucun plancher n'est actif. À plomber avec un
   porteur Hypersensory (Judh).
2. ~~**`MightBeOverkill` passe `MightCrit@+0xb1`**, `WillBeOverkill` passe **0 en dur**~~ →
   **FERMÉ le 2026-07-28 par `case-r34-mightbeoverkill-mightcrit.md`** (face DÉCISION), et le
   cadrage laissé ici s'est vérifié : câbler le seul consommateur aurait donné un canal lu jamais
   écrit. Le fix pose la clé **et** la lit — producteur `attacker_could_crit` (=
   `DamageCalculations$$CouldCrit`, évalué DANS `predict_attack_raw`), clé posée par
   `composite_fields` ET `_fields_from_native_event`, lue par `might_be_overkill`. Écart mesuré au
   scoreur natif : **15.0000 = `PossibleOverkill` exact**.
3. **`EffectAdditionalHits.forceOverkill`** — 6ᵉ paramètre d'`EffectAdditionalHits$$Create`, posé à
   `true` par une partie des 13 effets de coups additionnels (`FearOfTheUnseen_ExtraDamage`, …). Le
   canal `additional_hit_groups` du port ne le transporte pas, et le vecteur
   `runner/operations/additional_hits.py` n'est pas threadé (`hits_result` non passé au chokepoint).
   Fichiers laissés intacts : ils étaient **PRIS par un autre agent en vol**.
