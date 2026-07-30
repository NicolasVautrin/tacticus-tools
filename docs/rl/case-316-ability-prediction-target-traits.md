# case-316 — la prédiction d'une ABILITY ne lisait pas les traits de la CIBLE

**Verdict** : bug de câblage CONFIRMÉ au décompilé, corrigé, validé live sur **trois** volets et vu
ROUGE par mutation du correctif sur les trois. Le cadrage hérité (`N16` / backlog `#308-r`) était
**plus étroit que le défaut** : ni propre à `MartialInspiration` (1191), ni à la branche
`base_override`.

---

## 1. Ce que dit le décompilé (build `rnca9r7q6c`)

La chaîne de prédiction d'une ability, relue de bout en bout :

```
MartialInspirationPlaybook.<MakeDamagePredictions>d__2$$MoveNext
    -> slot d'interface 0x28  (caster = this+0xf8, target = this+0x108, position = this+0x118,
                               Nullable<AbilityOrEffect>, damage, Nullable<DamageProfile>, hits = 1)
    -> DamagePredictionQuery$$GetAttackPrediction        # memset(request, 0xb8) ;
                                                         # request+0x38 = caster ; request+0x50 = target
    -> DamagePrediction$$PredictAttack                   # recopie la request VERBATIM dans sa closure
    -> DamagePrediction$$PredictAttackRaw
           -> AbilityEntities$$.ctor(caster = actor = request+0x38, target = request+0x50)
              # Actor -> +0x0 ; Caster -> +0x8 ; Target -> +0x10
           -> slot de vtable 0xd = DamageCalculations$$CalculateAttackerModifiersForPrediction(
                  state, entities, activeEffects)
```

Deux faits tranchent, et ils sont **lus**, pas déduits :

1. `CalculateAttackerModifiersForPrediction` **ne reçoit aucun identifiant d'ability**. Sa signature
   est `(state: IMatchState, entities: AbilityEntities, activeEffects: List<EffectWithTarget>)`. Il
   itère les effets actifs et évalue leurs arbres DSL contre `entities` — qu'il recopie d'abord par
   le copy-ctor `AbilityEntities$$.ctor(this, entities, activeTarget)`, lequel **reconduit
   `Target@+0x10` tel quel**.
2. Ce foyer est **PARTAGÉ** avec l'attaque normale : `ALoki_NormalAttackAbility$$PredictAttack` ne
   construit pas son propre `AbilityEntities` pour ce slot — les deux chemins convergent sur le même
   `PredictAttackRaw`.

⇒ les gates `HasTrait(target, …)` des effets d'**attaquant** s'évaluent pour une ability
**exactement** comme pour l'attaque normale. Il n'existe aucun aiguillage natif qui les éteindrait.

Les deux gates du montage principal, verbatim :

```
BeastSlayer_ExtraDmgEffect$$CreateDamageModifier
    ForPercentIncrease( OwnerIsCaster & IsMeleeAttack
                        & ( HasTrait(target, 0x3f9 = BigTarget)
                            | HasTrait(target, 0x405 = Vehicle) ),
                        ConfigConst(0xf = beastSlayerExtraDmgPct) )

MartialKatah_DmgBonusEffect$$CreateEffectDamageBonusForAttack
    ForPercentIncrease( OwnerIsCaster & HasTrait(target, 2 = Summon),
                        Direct(GetNumberConstant(0xf = martialKatahExtraDmgPct)) )
```

## 2. Le défaut, et pourquoi il était plus large que la fiche

`engine/playbook/prediction/normal_attack.py::make_normal_attack_predictions` threadait
`target_traits=_entity_traits(scene, tgt_id)` depuis #267-r1.
`engine/playbook/prediction/abilities.py::generate_multi_hit_attack_prediction` — le per-cible de
`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions`, **par où passent toutes les abilities à
dégât** — ne le threadait pas.

Le défaut `None` de `BaseEffect.create_effect_damage_bonus_for_attack` signifie « cible inconnue »,
donc **aucun** bonus. Trois propriétés de cette dégradation :

* **silencieuse** — ni erreur ni crash ; le moteur annonce simplement moins de dégât ;
* **unilatérale** — le port ne peut que sous-estimer, jamais sur-estimer ;
* **fork prédiction↔combat** — la face COMBAT du **même** vecteur ability threade déjà
  `target_traits` (`engine/runner/operations/damage_ops/ability.py`). Le port **annonçait moins
  qu'il n'exécute**.

Six effets d'attaquant sont gatés sur les traits de la cible (compte re-dérivé du code, pas hérité) :
`BeastSlayer_ExtraDmg`, `MartialKatah_DmgBonus`, `CondemnorStake_ExtraDmg`, `HeavyGravCannon`,
`DestroyTheWitch_ExtraDamage`, `DespoiledGround_ExtraDamagePct`.

**Le correctif est d'une ligne** — le threading manquant — au foyer, pas dans le handler d'une
ability : `_martial_inspiration_inputs` n'est PAS en cause, et `base_override` non plus.

## 3. La mesure — trois volets, deux magnitudes, deux canaux

Montage : `scripts/python/probe_316_ability_prediction_target_traits.py`. Oracle =
`aiPlaybookPredict` (`<Ability>Playbook.MakeDamagePredictions` natif invoqué en direct), **jamais**
`aiPredict` (Attack-based quel que soit l'abilityType).

### 3.a Fixture synthétique — une seule variable, la ligne `BC.Units[].Traits` de la cible

`custoBladeChampion` <<Kariyan>> (BeastSlayer **et** MartialKatah) vs un mannequin amené au contact,
board `MC1_67` / seed 3081. Le trait est posé **en bataille** (`--unit-stat <cible>:Traits=[…]`),
donc le NATIF le voit aussi — ce n'est pas une substitution de canal côté port.

| bras | traits mesurés | 1191 natif | 1191 port AVANT | 1191 port APRÈS | facteur natif |
|---|---|---|---|---|---|
| `none` | `Hero` | `[1496, 2244]` | `[1496, 2244]` | `[1496, 2244]` | 1.0000 |
| `BigTarget` | `BigTarget, Hero` | `[1795, 2692]` | `[1496, 2244]` | `[1795, 2692]` | **1.1996** |
| `Vehicle` | `Hero, Vehicle` | `[1795, 2692]` | `[1496, 2244]` | `[1795, 2692]` | **1.1996** |
| `Summon` | `Summon` | `[2993, 4488]` | `[1496, 2244]` | `[2993, 4488]` | **2.0000** |

L'attaque **NORMALE** du même caster était bit-exacte dans les **quatre** bras, avant comme après —
c'est le **témoin de contraste** : il établit, bras par bras, que le trait est bien posé et bien vu
par le natif. Sans lui, un bras plat serait indiscernable d'un trait mal posé.

**Les deux magnitudes sont le second cas discriminant** : un correctif qui recollerait un facteur
constant (×1.2, ou ×2) tomberait forcément sur l'un des deux bras. Les deux pourcentages sont
**dérivés de gameconfig** (`beastSlayerExtraDmgPct`, `martialKatahExtraDmgPct`), jamais écrits en dur.

### 3.b Cibles RÉELLES — aucun patch de `Traits`, autre board et autre seed

`C3_01` / seed 777. Ce volet ferme le seul doute que la fixture synthétique laisse ouvert : que
patcher `BC.Units[].Traits` fabriquerait un régime artificiel.

| cible | traits (kit) | 1191 natif | 1191 port AVANT | 1191 port APRÈS | `pairUtility` natif |
|---|---|---|---|---|---|
| `necroWarden` | — | `[1496, 2244]` | `[1496, 2244]` | `[1496, 2244]` | 21.9021 |
| `tauCrisis` | `BigTarget` | `[1795, 2692]` | `[1496, 2244]` | `[1795, 2692]` | **21.2822** |

Les deux `pairUtility` natifs sont **exactement** ceux du datapoint qui avait nommé le résidu (#308).

### 3.c Canal ADDITIF — autre caster, autre ability, autre arithmétique

Les deux gates ci-dessus sont des `ForPercentIncrease` : ils entrent dans le `%-list`. Valider le
threading sur ce seul canal aurait laissé ouverte l'hypothèse qu'on ait généralisé à tort une loi de
facteur. `CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` est un `ForAddition`
(slot `DamageModifiers+0x10`, ajouté à la base **avant** perçage puis scalé une seule fois par le
`%-list` — `attacker_additive_pre`) :

`adeptCanoness` <<Roswitha>> (passif `CondemnorStake` **conservé**) caste `BrazierOfHolyFire` (1041,
**RANGED**, 2 coups, profil Flame), board `C4_09` / seed 909 :

| bras | 1041 natif | 1041 port AVANT | 1041 port APRÈS |
|---|---|---|---|
| `none` | `[3286, 7942]` | `[3286, 7942]` | `[3286, 7942]` |
| `Psyker` | `[13258, 17914]` | `[3286, 7942]` | `[13258, 17914]` |

**Quatre axes changent d'un coup** : canal (additif), caster, ability (et sa portée), trait, board.

> **Piège de mesure rencontré, et sa parade.** Au premier essai le montage rendait `[8536, 8536]`
> côté natif sur les **deux** vecteurs : le bonus tuait la cible, et `aiPlaybookPredict` rend alors
> le dégât **SANTÉ plafonné aux PV restants** tandis que le port rend le **RAW**. On comparait deux
> étages différents, et c'est le TÉMOIN qui tombait — pas le gate. Parade : `Health` /
> `RemainingHealth` du mannequin relevés par `--unit-stat` (et **non** `--hp-target`, qui remettrait
> aussi `Armor`/`FixedArmor` à 0, cf. résidu R8). Le test porte ce diagnostic dans son message
> d'échec.

## 4. Le rouge, vu AVANT — mutation du correctif

Le correctif retiré (la seule ligne `target_traits=_tgt_traits`), la garde rougit. Message verbatim
du volet « cibles réelles » :

```
AssertionError: [C3_01/777] la PREDICTION portee de 1191 DIVERGE de l'oracle natif sur
['tauCrisis'] : tauCrisis (traits ['BigTarget']) port=(1496, 2244) natif=(1795, 2692). Verifier que
`engine.playbook.prediction.abilities.generate_multi_hit_attack_prediction` passe toujours
`target_traits=_entity_traits(scene, tgt)` a `calculate_attacker_modifiers_for_prediction` -- le
natif n'a qu'UN `AbilityEntities` pour la normale et les abilities
(`DamagePrediction$$PredictAttackRaw` -> `AbilityEntities$$.ctor`, `Target@+0x10`), donc les gates
`HasTrait(target, ...)` des effets d'attaquant s'y evaluent dans les deux cas.
```

Sous la même mutation, le volet additif rend `A1 … ECART sur {'Psyker': ((3286, 7942), (13258,
17914))}` et **`A3 témoin attaque NORMALE port == natif sur 2/2 bras`** : la mutation ne touche que
le vecteur ability. L'attribution est donc exacte, pas seulement corrélée.

Le fichier de garde embarque en outre sa propre contre-épreuve
(`test_dropping_the_target_traits_would_have_been_visible`) : `_entity_traits` neutralisé dans les
**trois** modules de la couche prédiction (ils l'importent par nom — patcher le seul `_shared` ne
les atteindrait pas), le port doit redevenir **plat**. Sans cette moitié, l'accord ne prouverait rien.

## 5. Ce qui reste OUVERT, et pourquoi ce n'est pas porté ici

`calculate_attacker_modifiers_for_prediction` a **quatre** appelants côté prédiction. Deux sont
désormais threadés (`normal_attack.py`, `abilities.py`) ; deux ne le sont pas :

* `engine/playbook/psyker.py` — volet SPLASH d'un caster Psyker ;
* `engine/playbook/fury_of_the_ancients.py` — `bloodMephiston`.

Le natif n'ayant qu'un builder, ils **devraient** l'être. Ils ne le sont pas parce qu'ils sont
**INERTES**, et c'est **mesuré**, pas affirmé (`probe_316… --inert-call-sites`) :

```
BeastSlayer        porteurs=27  dont Psyker=0
CondemnorStake     porteurs=4   dont Psyker=0
DespoiledGround    porteurs=0   dont Psyker=0
DestroyTheWitch    porteurs=3   dont Psyker=0
HeavyGravCannon    porteurs=4   dont Psyker=0
MartialKatah       porteurs=4   dont Psyker=0
bloodMephiston (FuryOfTheAncients) porte : aucun de ces gates
```

Aucun porteur confrontable ⇒ les câbler serait un port **spéculatif**. Le compte est un **cliquet,
pas un acquis** : le jour où une unité `Psyker` gagne l'un des six gates, il cesse d'être nul et le
résidu (`N22` de l'inventaire) doit être rouvert **et confronté live**.

**Autres angles non couverts, nommés** :

* la face DÉCISION n'est pas assertée par cette garde (le probe expose `pairUtility` natif à titre
  informatif) — c'est `test_normal_attack_bonus_decision_live.py` qui garde l'étage utilité ;
* les quatre autres gates (`HeavyGravCannon`, `DestroyTheWitch_ExtraDamage`,
  `DespoiledGround_ExtraDamagePct`, et la branche `Vehicle` sur un porteur autre que Kariyan) ne
  sont pas confrontés individuellement : le correctif est au FOYER, donc ils l'empruntent tous, mais
  seuls trois d'entre eux ont été mesurés live.

## 6. Fichiers

| rôle | chemin |
|---|---|
| correctif | `scripts/python/engine/playbook/prediction/abilities.py::generate_multi_hit_attack_prediction` |
| montage (3 volets + cliquet) | `scripts/python/probe_316_ability_prediction_target_traits.py` |
| garde live (7 tests) | `scripts/python/tests/engine/test_ability_prediction_target_traits_live.py` |
| fixture pytest | `scripts/python/tests/engine/conftest.py::target_trait_ability_case` |
| note périmée corrigée | `scripts/python/probe_308_normal_attack_bonus.py` (« cible à éviter : `tauCrisis` ») |
