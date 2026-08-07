# #527-r1 — Le classement de cible de `SortUnitsByDamageUtilitySelector` : la clé est la PRÉDICTION COMPLÈTE, et son `damageProfile` est **NUL**

**Statut : RÉSOLU** (#494-r1-r1, 2026-08-07). Les **6 régimes sur 6** concordent avec le natif, dont
les trois qui divergeaient (`nominal`, `haute`, `seuil2200`).

Ce dossier garde aussi ce qui a été **éliminé** en chemin : deux explications plausibles et fausses,
et un seuil correctement mesuré mais mal attribué.

## 0. Le fait

`AncestralFortuneAbility$$GetAttackTarget` =
`First(SortUnitsByDamageUtility(NormalUnits(AdjacentEnemies(caster, 1), 3), MinMaxDamage(entities, 1), 3), 1)`.

Avec **deux** ennemis adjacents à `votanUthar`, le natif frappait `bloodMephiston` (79), le port
`necroWarden` (77). L'étage **DÉGÂT** était hors de cause : cible **forcée** à celle du natif, le
port est **bit-exact** (per-hit `[993, 977, 1131]`, total 3101). C'est l'étage **CHOIX**.

## 1. La cause, LUE — et elle tient en deux lectures

### 1.1 Le sélecteur appelle la PRÉDICTION COMPLÈTE, pas des bornes brutes

`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select`, relu intégralement :

```
units    = (+0x20).SelectUnits(entities, unitSelectionType)
owner    = (+0x18).SelectUnit(entities)                       -> dc+0x18
ownerPos = EntityExtensions.GetUnitPosition(owner)            -> dc+0x20
if ownerPos.IsEmpty : return new List<IEntity>()
damage   = (+0x40).Calculate(entities)                        -> dc+0x10
hits     = 1 ; if (+0x48) != null : hits = (+0x48).Calculate(entities)   -> dc+0x14
ability  = AbilityOrEffect(GetNormalAttackType(owner)) ; if (+0x28) != null : ability = (+0x28).Select(entities)
foreach u in units :
    pred = (+0x50 = IBattleQuery).<slot 0x26>(owner, u, ownerPos, ability,
                                              () => damage, () => hits,
                                              damageProfile: null, defenderInitialHealth: null,
                                              previousHitsPrediction: default, null, null)
    dict[u] = UtilityDecider.CalculateUtility(+0x38, u, pred)
return units.OrderBy(u => Fix64.op_UnaryNegation(dict[u])).ToList()
```

Deux corrections d'en-tête, toutes deux structurelles :

* **`+0x48` est `hits`, pas un `dmgMax`.** Le ctor l'atteste (`frida/methods.tsv`) :
  `SortUnitsByDamageUtilitySelector..ctor(state, battleQuery, utilitiesDatabase, targets, caster,
  ability, utilityDefinition, damage, hits, aiLogger)`. Son défaut est **1**, écrit en dur
  (`*(dc+0x14) = 1` avant le test de nullité). Le nœud de dégât rend **un** entier.
* Le slot `0x26` d'`IBattleQuery` (`metadata/interface_slots.tsv` :
  `IBattleQuery 38 GetAttackPrediction 11`) est la surcharge
  `(caster, target, casterPosition, ability, calculateDamageAtTile:Func<Int32>,
  calculateHitsAtTile:Func<Int32>, damageProfile, defenderInitialHealth, previousHitsPrediction,
  prePredictionAction, postPredictionAction)` →
  `DamagePredictionQuery$$GetAttackPrediction` (memset 0xb8 de l'`AttackPredictionRequest`, puis
  slot 5 = `DamagePrediction$$PredictAttack`) → `$$PredictAttackRaw`. **ARMURE, DÉFENSE,
  modificateurs d'attaquant et de défenseur, bouclier et scénarios de BLOCK entrent donc dans la
  clé de tri.**

### 1.2 `damageProfile` est NUL, et c'est ce qui met le PERÇAGE à ZÉRO

Le sélecteur passe `null` en 7ᵉ argument. Et
`IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` commence par :

```
if (damageProfile != null) {
    extra   = GetStat(attacker, ExtraPierce);
    dir     = GetStat(attacker, isMelee ? ExtraPierceMelee : ExtraPierceRanged);
    base    = StaticBattleRules.Damage$$GetPiercingRatio(damageProfile, GetTraits(attacker));
    return Min(100, Max(base > 0, dir + extra + defMod + attMod + base));
}
return 0;                                   // <-- LE GARDE
```

Le garde n'existerait pas si aucun chemin ne passait un profil nul. La clé prédit donc un coup
**SANS PERÇAGE** : `StaticBattleRules.Damage$$GetDamageWithPiercing(d, 0, armure) =
max(0, d − armure)` — **l'armure est soustraite EN ENTIER**. Ce n'est ni le profil de l'ability, ni
celui de l'arme ; c'est `null`, donc aussi **aucun gate de profil**
(`DamageProfileIs`, traits d'arme, `CalculateTrenchReduction`).

⇒ Le port fabriquait un `pred` synthétique (bornes brutes, `armor = 0`). C'est la MÊME cause que
`#494-r1-r1` (la défense), et c'est pour cela que les deux résidus se sont fermés du même geste.

## 2. Deux explications ÉLIMINÉES — les garder évite de les ressortir

### 2.1 « L'armure entre par le plancher perçage du profil `Plasma` (65 %) » — RÉFUTÉE

`AncestralFortune` porte le profil `Plasma` (`PiercingDamageRatio = 65`). Sur la moyenne des bornes
de l'ability (`avg = 2044`), `max(0, d − armure, d × 65 %)` rend **exactement 1328.6 pour 2662 ET
pour 2008** : le plancher perçage domine, l'armure ne mord qu'à 300. Le calcul est juste — c'est
l'HYPOTHÈSE qui était fausse : **`Plasma` n'est pas le profil de la clé**, puisque la clé n'en a
aucun.

### 2.2 Le canal BLOCK — ÉLIMINÉ par A/B à une variable

`aiPredict` montrait que seule `bloodMephiston` porte un scénario de block
(`blockScenarioCount = 1`, `blockProbability = 30`) et que c'est ELLE que le natif préfère. A/B joué
(`--unit-stat bloodMephiston:BlockChance=0,BlockDamage=0`, rien d'autre touché) : **le natif frappe
toujours `bloodMephiston`**. Le block n'est pas le facteur.

⚠ `aiPredict` est Attack-based (`GetAllPredictions`, ability `69 Loki_NormalAttack`) : il répond à
« le dégât prédit dépend-il de la cible ? », pas à « quelle est la clé ».

## 3. Le seuil 2100/2200 : la MESURE était bonne, l'ATTRIBUTION était fausse

Les régimes bornaient la bascule native entre armure **2100** (le natif préfère `necroWarden`) et
**2200** (il bascule sur `bloodMephiston`), tout le reste inchangé. `#527-r1` en avait déduit
`seuil = d × 35 %` donc `d ∈ [6000, 6286] = 3 × 2044` — « le natif emploie le dégât des TROIS
coups ». C'était cohérent avec un perçage de 65 %, et **faux**, parce que le perçage vaut 0.

Avec la clé réelle (`amount = 2044`, ±20 %, **perçage 0**, `hits = 1`), la bascule tombe au même
endroit sans qu'aucun scalaire soit ajusté — mesuré, port et natif :

| armure `necroWarden` | prédiction du port (accurate) | utilité port | NATIF | PORT |
|---|---|---|---|---|
| 2100 | `[1, 441]` | 2.588 | `necroWarden` | `necroWarden` |
| 2200 | `[1, 316]` | 1.851 | `bloodMephiston` | `bloodMephiston` |

(`bloodMephiston`, armure 2008 : `[1, 389]`, utilité 2.044 — constante d'un régime à l'autre.)

⚠ **La leçon** : un seuil correctement encadré *mesure* quelque chose, mais ne dit pas QUOI tant que
la loi qui l'engendre n'est pas lue. Ici deux inconnues (le dégât employé, le perçage) se
compensaient : `3 × 2044` à 65 % et `2044` à 0 % donnent le même seuil à ~50 près.

## 4. Les SIX régimes, après le fix

`python probe_527_votann_lot1_rouges.py --etage armure|cle --regime <r>` (l'étage `cle` est neuf : il
imprime les ENTRÉES — mêlée, armure résolue — et les SORTIES — bornes prédites, champs du composite,
utilité — au lieu du seul verdict, qui ne distinguait pas « le fix ne mord pas » de « le fix mord et
se trompe »).

| régime | necro (maxHP / armure) | meph (maxHP / armure) | NATIF | PORT | u(necro) | u(meph) |
|---|---|---|---|---|---|---|
| `nominal`    | 8536 / 2662 | 9537 / 2008 | `bloodMephiston` | `bloodMephiston` | 0.012 | 2.044 |
| `haute`      | 8536 / 2662 | 8536 / 2008 | `bloodMephiston` | `bloodMephiston` | 0.012 | 2.284 |
| `basse`      | 8536 / **300** | 8536 / 2008 | `necroWarden` | `necroWarden` | 25.533 | 2.284 |
| `hp`         | 8536 / 2008 | 9537 / 2008 | `necroWarden` | `necroWarden` | 3.256 | 2.044 |
| `seuil_2100` | 8536 / 2100 | 9537 / 2008 | `necroWarden` | `necroWarden` | 2.588 | 2.044 |
| `seuil_2200` | 8536 / 2200 | 9537 / 2008 | `bloodMephiston` | `bloodMephiston` | 1.851 | 2.044 |

**6/6.** Avant le fix : 3/6 (`basse`, `hp`, `seuil_2100`) — et le banc offline `--etage modele` ne
dépassait pas 4/6, quelles que soient les entrées qu'il faisait varier (armure appliquée, 1/2/3
coups), parce qu'il cherchait dans le mauvais espace : le perçage y était figé à 65.

## 5. Ce qui a changé dans le port

* **`engine/runner/operations/attack_prediction.py` (NEUF)** — le mirror de
  `BattleQuery$$GetMultiHitAttackPrediction` monté depuis l'ECS. Il vivait dans
  `damage_prediction_sort.py` (le mirror d'un AUTRE sélecteur) ; il a désormais **deux**
  consommateurs, donc son propre module. Accepte `damage_profile = None` →
  `DamageProfileType.None_`.
* **`engine/utilities/damage.py::composite_fields_from_prediction`** — la lecture
  `UtilityAttackCase$$ForDamagePrediction`, extraite de `ProbableDamageEvent.composite_fields` (qui
  y délègue). Les deux chaînes — playbook et sélecteur de tri — lisent le MÊME
  `DamagePredictionResult` ; en recopier la lecture aurait été un fork du mirror.
* **`engine/runner/operations/damage_utility.py`** — `_target_utility` a deux chemins : MIRROR
  (prédiction complète) quand `owner_id` est fourni et le couple prédictible, DÉGRADÉ (pré-armure)
  sinon. Le natif, lui, sort sec (`ownerPos.IsEmpty -> new List<IEntity>()`) ; le port ne peut pas
  rendre une liste vide à un appelant qui ne lui a rien dit du caster, donc il dégrade **en le
  documentant**. Ce chemin est celui des étages OFFLINE (stubs sans `StatsComponent`).
* **`final_justice.py`** — le nœud `+0x40` de FinalJustice est
  `DSLFormulas$$NormalAttackDamage(caster)` = `StatAmountFormula(caster, StatType.Attack = 0,
  StatPart = 0)`, donc **la stat `Attack`**, base d'UN coup. Le port y passait
  `_normal_attack_health_range` : la plage SANTÉ du TOTAL de l'attaque (hits d'arme + effets). Tant
  que la clé était pré-armure, l'écart était un facteur commun donc invisible ; il ne l'est plus,
  l'armure n'étant pas linéaire. `_normal_attack_health_range` est remplacé par
  `_normal_attack_damage_node`.

## 6. Ce qui reste ouvert

* **`#494-r1-r1-r1`** — `isMelee` et `hits` de la clé ne sont pas LUS dans `PredictAttackRaw`
  (non parcouru intégralement) : le port dérive `isMelee` de l'ability du nœud `+0x28` (attaque
  normale → l'arme ; Doombolt → `Ranged` ; KillMaimBurn → mêlée), et fixe `hits = 1` parce
  qu'**aucun** des quatre call-sites portés ne fournit de nœud de coups. Un call-site à `hits > 1`
  n'existe pas dans le lot, donc le comportement de `PredictAttackRaw` sur ce paramètre est
  **NON CONFRONTÉ**.
* **`MightCrit`** — `PredictAttackRaw` le calcule (`CouldCrit(attacker)`), et le live a pourtant
  RÉFUTÉ qu'il entre dans ce classement (#419-r6-r1). Le port reste où la mesure l'a mis : le
  service de prédiction ne reçoit pas d'`attacker_ctx` sur ce chemin. L'étage exact qui neutralise
  le flag n'est toujours pas isolé.
* **Bouclier de la cible** dans le terme `combinedMax` du composite (`shieldBefore`) — résidu
  partagé avec le reste du moteur.

## 7. Instrument, rejouable

```
python probe_527_votann_lot1_rouges.py --etage cle    --regime nominal|haute|basse|hp|seuil_2100|seuil_2200
python probe_527_votann_lot1_rouges.py --etage armure --regime <idem>
python probe_527_votann_lot1_rouges.py --etage predict --regime nominal
python probe_527_votann_lot1_rouges.py --etage replay
```

⚠ **Toute garde future de ce foyer doit REFUSER un régime à armure nulle**, sinon elle sera verte
pour la même mauvaise raison que #419-r6-r1 (qui avait validé ce foyer sur Doombolt avec
`FixedArmor = Armor = 0` sur toutes ses cibles). La garde exécutable est
`test_doombolt_live.py::test_doombolt_ordre_heterogene_bloque_par_l_armure_live` (montage `db-4`,
`fixedArmor` NATURELS et tous différents) : il portait le `xfail(strict=True)` de ce résidu, il est
passé en `xpass`, le marqueur a été retiré, et il est désormais **vert** — donc il rougira si
l'armure ressort de la clé.
