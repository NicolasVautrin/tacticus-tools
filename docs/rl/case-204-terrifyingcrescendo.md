# Case #204 — TerrifyingCrescendo_ExtraDmg (0x590=1424) : additif ranged empilable (0..6) d'emperNoiseMarine

**Status : PORTE + VALIDE LIVE BIT-EXACT (prediction 190/190 + combat 7/7, stacks 0->6), RE COMPLETE
(decompile-citee, build gqfc5mff6c). Zero-regression prouve (garde 31337 etage prediction byte-identique
au baseline).**

Jumeau STRUCTUREL de BeaconOfRage (#189) : `ForAddition(OwnerIsCaster, Multiply(ConfigVar(8=extraDmg),
EffectLevel))` avec UNE seule difference : le gate `IsRangedAttack`.

## Ce que c'est (i2)
Passif `TerrifyingCrescendo` d'`emperNoiseMarine` <<Shiron>> (EmperorsChildren/Chaos, Uncommon) :
« Shiron's ranged attacks deal **+218 Damage for each time he Overkilled or would have Suppressed** an
enemy unit, up to a **maximum of 6 times**. » (`buffMaxLevel=6`, +218 = `extraDmg[L65]`.)

Decouvert par POLLUTION de probe (#202-B, session 2026-07-22) : les predictions natives per-tuile (canal
`ranked`) impliquant emperNoiseMarine gagnaient un additif PLAT ~+1596 par stack, croissant round apres
round — c'est cet effet 1424, alors non porte. (`~+1596` = **exactement** `extraDmg[50]=166 x mult 160% x
6 coups` = `266/coup x 6` : confirme numeriquement, cf. §Validation.)

## RE native (decompile-citee, build gqfc5mff6c) — INTEGRALE

### Symboles
| Symbole | VA | Role |
|---|---|---|
| `TerrifyingCrescendo_ExtraDmgEffect$$.ctor` | `0x180f718f0` | ctor de l'effet |
| `TerrifyingCrescendo_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` | `0x180f715e0` | feuille DEGAT (additif) |
| `TerrifyingCrescendo_ExtraDmgEffect$$GetLocalizationDataInternal` | `0x180f71720` | localisation |
| `FuelledByFury_ExtraDamageEffect$$GetCurrentExtraDamage` | `0x180f4ae70` | montant HERITE (refcount 10) |
| `TerrifyingCrescendoAbility$$CreateBehaviour` | `0x1811a3840` | accumulation (AddEffectOrIncreaseLevel) |
| `TerrifyingCrescendoAbility$$CreateTrigger` | `0x1811a3910` | evenements d'accumulation |

Ids : EffectType **0x590 = 1424** (`effect-type-names.ts:547` = "TerrifyingCrescendo_ExtraDmg") ; ability
triggered **0x59b = 1435** ("TerrifyingCrescendo", `triggered-ability-names.ts:461`). Le ctor de l'effet
reference l'ability 0x59b (`AbilityOrEffect.op_Implicit(local, 0x59b)`) = source des ConfigVar/AbilityState.

### La feuille DEGAT (@0x180f715e0)
```
CreateEffectDamageBonusForAttack(effect):
  cond   = IsRangedAttack(dslFactory) & get_OwnerIsCaster(dslFactory)      // AbilityTrigger.op_BitwiseAnd
  amount = GetCurrentExtraDamage(effect)                                   // heritee de FuelledByFury
  return Nullable<EffectBonus>( EffectBonus.ForAddition(cond, amount, <struct copie @+0x14..0x2c>) )
```
`ForAddition` -> champ DamageBonus (additif) de l'EffectBonus -> `DamageModifiers.Add @181005f10` (canal
`additive @+0x10`), applique PAR COUP (meme canal que BeaconOfRage/SmashaEad). **SEULE difference vs
BeaconOfRage `@0x180f33130`** (dont le trigger est `get_OwnerIsCaster` SEUL) : le noeud DSL `IsRangedAttack`
(`DSLFactory.IsRangedAttack`) -> le bonus est ABSENT des attaques MELEE et des attaques d'ability non-ranged.

### Le montant (@0x180f4ae70, herite de FuelledByFury_ExtraDamageEffect)
```
GetCurrentExtraDamage(effect):
  cfgVar = ConfigVar(dslFactory, 8, GetAbilityState(effect), effect@0x60)  // var index 8 = extraDmg
  lvl    = EffectLevel(dslFactory, dslFactory@0x150)                       // le stack (EffectComponent Level)
  return Multiply(dslFactory, cfgVar, lvl)                                 // extraDmg[ablvl] x EffectLevel
```
= `extraDmg[abilityLevel] x multiplier x stack_level` PAR COUP. `extraDmg` = variables TerrifyingCrescendo,
`[L1..L65] = [3..218]`, **DANS `variablesAffectedByRarityBonus`** -> scale x le multiplier de l'unite
(contrairement a BeaconOfRage dont extraDmg est HORS rarityBonus = mult no-op). Cet heritage
FuelledByFury/TerrifyingCrescendo est confirme par le `refcount 10` de GetCurrentExtraDamage et l'appel
DIRECT de `FuelledByFury_ExtraDamageEffect$$GetCurrentExtraDamage` depuis la feuille de TerrifyingCrescendo.

### L'ACCUMULATION — combien de stacks, quel evenement, cap, reset ?
`CreateTrigger @0x1811a3910` (disjonction de deux branches `op_BitwiseAnd` reliees par `op_BitwiseOr`) :
```
branche1 = On(0)      & get_OwnerIsActor & TargetIsOverkilled     // le porteur OVERKILL une cible
branche2 = On(0x3e=62) & get_OwnerIsActor & TriggeringEffectIs(0x429=1065)   // le porteur POSE Suppressed
trigger  = branche1 | branche2
```
- **branche1** = `On(evt 0) & OwnerIsActor & TargetIsOverkilled` = « each time he Overkilled ».
- **branche2** = `On(evt 62) & OwnerIsActor & TriggeringEffectIs(1065)` = « would have Suppressed » :
  l'effet 0x429=1065 est **Pinned/Suppressed** (UI « Suppressed ») que le trait **SuppressiveFire** de
  Shiron pose sur chaque ennemi touche par une attaque RANGED.

`CreateBehaviour @0x1811a3840` (le behaviour execute au declenchement) :
```
constant = AbilityConfiguration.GetNumberConstant(cfg, 0x62)     // constante de niveau-increment
value    = DSLFactory.Direct(constant)                           // noeud valeur (Direct)
DSLFactory.AddEffectOrIncreaseLevel(dslFactory, 0x590=effectId, AbilityStateReference,
                                    self@0x148, self@0x148 (selector), df@0xc0, Direct(constant))
```
= si l'effet 0x590 est absent -> `AddEffect` niveau=increment ; sinon -> `IncreaseLevel(+increment)`.
Increment = 1 par declenchement (Direct d'une constante). **Cap = `buffMaxLevel=6`** (constants de
l'ability) enforce A L'ECRITURE par le natif. **Pas de reset per-tour** : c'est un buff CUMULATIF sur la
bataille (comme la rage BeaconOfRage), `remaining=0` (permanent, pas de timer) — confirme live (rem=0).
Le level cappe arrive TEL QUEL dans `decisionView.effects[].level` (`EffectComponent Level @0x68`).

## Port (mirror 1:1)

`engine/entities/effects/loki/extra_damage.py::TerrifyingCrescendoExtraDmgEffect` (a cote de BeaconOfRage,
sa famille structurelle) + enregistrement `engine/entities/effects/factory.py`
(`"TerrifyingCrescendo_ExtraDmg" -> TerrifyingCrescendoExtraDmgEffect`) + export `loki/__init__.py`.

Corps = jumeau exact de `BeaconOfRageExtraDamageEffect` + gate `if not is_ranged: return None` (mirror
`IsRangedAttack`) :
```python
if not is_ranged:            return None    # gate IsRangedAttack @180f715e0 (melee/inconnu -> 0)
crescendo = self.level                       # EffectLevel (stack), cappe (buffMaxLevel=6) a l'ecriture
if not crescendo or crescendo <= 0: return None
if self.ability_level is None:      return None    # ConfigVar sans AbilityState -> pas de magnitude
per = ability_var("TerrifyingCrescendo", "extraDmg", self.ability_level,
                  multiplier_pct=self.ability_variables_multiplier)
return for_addition(True, int(per) * int(crescendo))   # Multiply(ConfigVar(extraDmg), EffectLevel)
```

### DEUX faces couvertes par UN port (canal partage)
La feuille `create_effect_damage_bonus_for_attack` est appelee par la boucle PARTAGEE
`_attacker_effect_bonuses` (`entities/effects/__init__.py`) qui alimente :
- **PREDICTION** (`calculate_attacker_modifiers_for_prediction`, slot 0xd) -> `make_normal_attack_predictions`
  (`is_ranged=_ranged` threade ligne 652 de `playbook/prediction.py`) ;
- **COMBAT** (`build_attacker_modifiers_from_effects`, slot 0xf) -> pipeline damage du runner
  (`runner/operations/damage.py`).
Le meme `for_addition` -> `DamageModifiers.additive` -> `apply_all_modifiers` sert les deux faces (aucun
fork), exactement comme BeaconOfRage. **Feuille DSL / Operation** : la partie DECLARATIVE (arbre DSL
trigger/behaviour + selecteur) reste implicite (l'accumulation vit dans le natif du runner LIVE, capte dans
`decisionView.effects[].level` = verite, comme BeaconOfRage) ; la partie IMPERATIVE (l'`EffectBonus.ForAddition`
-> `DamageModifiers.Add`) est le `for_addition` porte. On ne re-calcule PAS le compteur offline.

### Accumulation : NON re-simulee offline (comme BeaconOfRage rage)
Le `level` capte EST la verite (le natif enforce le cap +1/declenchement a l'ecriture ; le compteur de
triggers n'est pas expose). Le port lit `self.level`. Un runner OFFLINE pur (sans live) qui voudrait
auto-incrementer le stack necessiterait une operation-trigger dediee (branche1/branche2 ci-dessus) dans
`runner/operations/triggers/` — HORS scope #204 (identique au traitement BeaconOfRage : rage lue, pas
re-simulee). La validation utilise le runner LIVE (le natif incremente ; l'offline lit le level frais).

## Validation live ADVERSARIALE (probe_204_crescendo.py, seed 20204, MC1_67)

Setup drive-positions : Shiron + 2 fillers vs 3x necroWarden HP GONFLE (400k, personne ne meurt ->
accumulation par SUPPRESS seule = +1/round propre, croissance 0->6). Shiron tire en RANGED chaque round
(tuile plate, pas de x1.5 elevation) puis avance au contact si hors portee.

**A. Capture** : `ablvl=50 mult=160 extraDmg[50]=266` (base 166 x 1.6). Stack croit 0->1->2->3->4->5->6
puis CAPE a 6 (rem=0 permanent). +1/round via suppress.

**B. PREDICTION per-tuile (canal `ranked` natif == offline)** : **190/190 match** sur 7 rounds, TOUS
niveaux L0..L6, tuiles RANGED **et** MELEE (le controle melee = pas de bonus, byte-exact) :
| L | additif/coup attendu | B match |
|---|---|---|
| 0 | 0    | 22/22 |
| 1 | 266  | 26/26 |
| 2 | 532  | 30/30 |
| 3 | 798  | 26/26 |
| 4 | 1064 | 30/30 |
| 5 | 1330 | 26/26 |
| 6 | 1596 | 30/30 |

**C. COMBAT ranged (stream_events)** : le total observe des 6 coups tombe DANS la plage offline predite
(qui INCLUT l'additif) a chaque niveau (7/7) ; la plage monte de **EXACTEMENT +1596 (min ET max) par
niveau** = `266/coup x 6 coups` = preuve bit-exacte que le COMBAT applique l'additif per-coup, pas
seulement la prediction :
```
L0 off_rng (2904, 4356)  obs 3331
L1 off_rng (4500, 5952)  obs 5423   (+1596)
L2 off_rng (6096, 7548)  obs 6419   (+1596)
L3 off_rng (7692, 9144)  obs 8616   (+1596)
L4 off_rng (9288,10740)  obs 9808   (+1596)
L5 off_rng (10884,12336) obs 11745  (+1596)
L6 off_rng (12480,13932) obs 12865  (+1596)
```

**Cas 0-stack** : couvert (L0, additif=0, native==offline).

## Zero-regression (garde 31337 etage prediction)
`engine_agreement_stages.py --build --seeds 31337 --steps 40` :
- AVEC #204   : etage PREDICTION 21/23 (91%, 2 mismatch-logic pre-existants) ; UTILITE 23/23 ; ability 27/27.
- SANS #204 (baseline, edits stashes) : **IDENTIQUE** 21/23, memes 2 residus, memes champs.
Les 2 mismatches formule (`healthDmgMin/Max`) sont des residus Fix64/aura PRE-EXISTANTS du roster
Mephiston/Njal — le seed 31337 n'a PAS emperNoiseMarine, donc l'effet 1424 n'y est jamais materialise et
le port est byte-inerte. **#204 introduit ZERO nouveau mismatch.**

## Residus / non couverts (honnetes)
- **Multiplier per-ability des triggered (#68/#75)** : le port utilise `self.ability_variables_multiplier`
  (GLOBAL de l'unite = 160). Validation LIVE bit-exacte (190/190) => le natif utilise BIEN le multiplier
  GLOBAL pour ce passif (pas un multiplier per-ability distinct comme SmashaEad triggered-actif #68). Le
  risque #68 est donc EXCLU pour TerrifyingCrescendo par la mesure.
- **Double-increment overkill+suppress dans un meme tir** : le natif a DEUX branches OR ; un tir qui touche
  ET overkill pourrait incrementer 2x. Non isole ici (setup no-kill = suppress-only, +1/round). Sans impact
  sur le port (on lit le level abouti, pas le compteur). A explorer si un scenario overkill est requis.
- **Accumulation offline auto-simulee** : NON portee (comme BeaconOfRage rage) — le runner LIVE incremente,
  l'offline lit le level capte. Un runner offline pur ne verrait pas le stack croitre sans une operation-
  trigger dediee (candidat futur, hors #204).
