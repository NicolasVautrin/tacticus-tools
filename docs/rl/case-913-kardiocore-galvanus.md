# #913 — `1457 KardiocoreGalvanus` : la face EXÉCUTION d'une relique dont seule la DÉCISION était portée

**Verdict : PORTÉ + CONFRONTÉ LIVE.** `EffectType.KardiocoreGalvanus_ExtraCritDmg` (0x5aa = 1450)
était **déclaré dans l'enum et jamais posé**. Il l'est.

---

## 1. Le cas, et pourquoi un hit dans `engine/playbook/` ne le fermait pas

`KardiocoreGalvanusPlaybook` et `KardiocoreGalvanusNonOwnerPlaybook` sont portés depuis #477-r33 :
la face **DÉCISION** (l'IA aime se placer à côté d'amis mécaniques) était donc verte. La face
**EXÉCUTION** — le bonus de dégât critique que la relique accorde réellement — ne l'était pas :
aucune classe d'effet, aucune entrée `EFFECT_CLASSES`, donc `BaseEffect` no-op et
`create_effect_crit_damage_bonus_for_attack` rendant `None`.

Dégradation **PERMISSIVE À L'ENVERS** et **SILENCIEUSE** : le porteur frappait **moins fort** que le
natif. Amplitude mesurée sur le montage de ce cas (`extraCritDmg[3] = 327`, deux amis mécaniques
adjacents) : **+654 par coup critique**, soit `[4343, 5398]` porté contre `[6555, 6690]` natif.

## 2. L'artefact, lu en entier — SEPT méthodes, et DEUX sont invisibles des tables

`IdunBattle.Entities.Effects.Loki.KardiocoreGalvanus_ExtraCritDmgEffect` (: `BaseEffect`).
`ghidra/functions.tsv` et `frida/methods.tsv` n'en nomment que **cinq**. Les deux autres ont un
corps **dédupliqué** avec une autre classe, donc un seul propriétaire dans la table — l'absence ne
prouve rien (CLAUDE.md). Elles ont été retrouvées par le bloc `methodPointers` du PE, dont
l'ordonnancement s'aligne **slot à slot** sur celui des deux sœurs de forme
(`IntoxicatingElixir_ExtraCritDmgEffect`, `MawClawsOfThyrax_ExtraCritDmgEffect`) — appariement
vérifié sur 9 positions consécutives, `.ctor` en tête :

| slot | KardiocoreGalvanus | MawClawsOfThyrax |
|---|---|---|
| +0 | `$$.ctor` | `$$.ctor` |
| +1 | **`WisdomOfTheAncients_DamageReductionEffect$$CreateActiveCondition`** (dédup) | `$$CreateActiveCondition` |
| +2 | `WhisperingWebEffect$$CreateTargetSelector` (dédup, défaut) | idem |
| +3 | `$$CreateCritDamageBonus` | `$$CreateCritDamageBonus` |
| +4 | `$$GetCalculateLevel` | `$$GetCalculateLevel` |
| +5 | `$$GetLocalizationDataInternal` | `$$GetLocalizationDataInternal` |
| +6 | **`MawClawsOfThyrax_ExtraCritDmgEffect$$GetExtraCritAmount`** (dédup) | `$$GetExtraCritAmount` |

Les arbres, verbatim :

```
$$.ctor                    = BaseEffect..ctor(this, AbilityOrEffect(0x5b1), hasAutomatic: 1)
$$CreateActiveCondition    = <DSLTriggers+0x70> = YesTrigger              -> TOUJOURS VRAI
$$CreateTargetSelector     = <DSLSelectors+0x30> = Owner
$$CreateCritDamageBonus    = EffectBonus.ForAddition( get_OwnerIsCaster, GetExtraCritAmount() )
$$GetExtraCritAmount       = DSLFormulas.Multiply(
                                 ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet), cfg@+0x60),
                                 DSLFormulas.EffectLevel(Effect@DSLSelectors+0x38) )
$$GetCalculateLevel        = DSLFormulas.Count(
                                 DSLSelectors.MechanicalUnits(
                                     DSLSelectors.AdjacentFriends(Owner@+0x30, unique: 1, sel: 3),
                                     sel: 3 ) )
```

POSE : `KardiocoreGalvanusAbility` dérive d'`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`,
dont le `CreateBehaviour` de base est
`If( OnOwnerSpecificAbilityInit(1457), AddEffect(GetEffectType() = 0x5aa, AbilityState(Owner, …),
source = Owner, targets = Owner, turns = <zéroé>) )` — owner-effect **PERMANENT** sur le porteur.
`$$GetEffectType` a pour corps ENTIER `return 0x5aa`, donc l'appariement ability → effet est LU.

## 3. Le piège d'ordinal est RÉEL, et c'est la SURCHARGE qui le tranche

```
EffectType            0x5aa = 1450 = KardiocoreGalvanus_ExtraCritDmg   <- CET effet
TriggeredAbilityType  0x5b1 = 1457 = KardiocoreGalvanus                <- sa CONFIG
EffectType            0x5b1 = 1457 = RelicBoltPistol_ExtraPierce       <- une AUTRE relique
```

Le `.ctor`, relu **octet à octet** : `ba b1 05 00 00` (`mov edx, 0x5b1`) puis un `call` dont la
cible, résolue par son **RVA** (`next_ip + rel32`), est
`IdunBattle.Core.AbilityOrEffect$$op_Implicit(triggeredAbility: TriggeredAbilityType)` — les quatre
surcharges sont HOMONYMES dans les tables, seule l'adresse les sépare.

⚠ **La confusion ne lèverait PAS** : `RelicBoltPistol` existe au gameconfig. Elle lirait juste la
mauvaise variable, en silence. C'est exactement le régime que la règle « un ENTIER qui DÉSIGNE
passe par un ENUM » est écrite pour rendre visible.

## 4. Ce qui SÉPARE cet effet de ses deux jumeaux déjà portés

`AmuletOfTheVoidwyrm_CritDamageReduction` (#589-r1-r1-r2-r1) et `SupaCyborkBody_CritDmgReduction`
(#503-r4) sont ses voisins immédiats au PE et partagent sa forme. **Trois** différences, et chacune
est un bras de validation :

| | Amulet / SupaCybork | KardiocoreGalvanus |
|---|---|---|
| canal | `ForSubtraction` (terme NÉGATIF) | **`ForAddition`** (terme POSITIF) |
| trigger | `get_OwnerIsTarget` — le porteur DÉFEND | **`get_OwnerIsCaster`** — le porteur ATTAQUE |
| `CreateActiveCondition` | GÉOMÉTRIQUE (`AmountIsGreaterThanZero` / `HasAdjacentEnemies`) | **`YesTrigger`**, CONSTANTE VRAIE |

Conséquences portées :

* **aucune garde de saturation** n'est requise : `CalculateCriticalDamage` fait
  `Math.Max(0, GetStat(10) + somme)` et la somme est positive, donc le clamp bas ne peut pas mordre
  (les deux probes `ForSubtraction` en ont une, et elle est indispensable chez eux) ;
* **pas d'`active_condition_ported`, pas de clé de `unit_state`, pas de seed conditionnel** :
  l'effet est publié ACTIF par `decisionView` **même à compteur 0**, donc le régime commun
  (`BaseEffect.is_active`) coïncide avec le natif. L'écrire autrement inventerait un gate que le
  décompilé ne porte pas.

## 5. L'observable qui rend l'étage COMPTEUR confrontable SANS passer par le dégât

`decisionView.effects[].level` publie le niveau **STOCKÉ** (`EffectComponent+0x68`), que
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel` tient ÉGAL à `$$GetCalculateLevel`
(il appelle le slot `CalculateLevel`, compare, et ÉCRIT si ça diffère).

C'est donc **le compteur natif, lu directement**. Découvert par mesure : `admecRuststalker` déployé
en `(1,0)` avec deux amis mécaniques en `(0,0)` et `(1,1)` publie `level: 2`. Chaque bras
l'assertionne AVANT la magnitude — ce qui sépare « le compteur est faux » de « la magnitude est
fausse » sans avoir à jouer une attaque.

Chez les deux jumeaux, l'activité de l'effet jouait ce rôle ; ici elle est constante, et cet
observable-là la remplace **avantageusement** (il donne le cardinal, pas seulement son signe).

## 6. La confrontabilité — état 1, et le montage est GRATUIT

`data/seed-bc.json` : **4** unités portent une `TertiaryAbility`, et **deux sont ce cas** —
`admecMarshall` et `admecRuststalker`, toutes deux `TertiaryAbility = 1457`,
`TertiaryAbilityLevel = 1`. Vérifié en live : les deux publient
`KardiocoreGalvanus_ExtraCritDmg` **dès le déploiement, sans aucun montage**, et `admecDestroyer`
(3ᵉ porteur autorisé, relique non équipée) ne le publie pas.

Le probe passe quand même par `--equip-relic` (état 2) : c'est le seul moyen de **maîtriser le
niveau**, donc d'armer le bras `PASSIF`.

## 7. Le port

* `engine/entities/effects/loki/kardiocore_galvanus.py` — la classe + l'arbre DSL du compteur ;
* `engine/entities/effects/factory.py` — `EFFECT_CLASSES["KardiocoreGalvanus_ExtraCritDmg"]` ;
* `engine/runner/components.py` — `adjacent_mechanical_friends_count` (donne son `AbilityEntities`
  à l'arbre, tri-état `None` = non mesuré) ;
* `engine/runner/operations/damage.py` — `adjacent_mechanical_friends_of` dans `_crit_board`.

Les deux sélecteurs (`AdjacentFriends`, `MechanicalUnits`) et le prédicat `is_mechanical`
existaient déjà et sont réutilisés — **aucun fork**.

**PAS d'entrée `ABILITY_INIT_OWNER_EFFECTS`, et c'est MESURÉ** :
`spawn.py::_seed_ability_owner_effects` lit `GC.unit(vid).activeAbilities + passiveAbilities`, le
**KIT** gameconfig. Or les kits des trois porteurs sont `['ControlEdict']`, `['OptimizedGait']`,
`['HeavyGravCannon']` — la relique n'y figure pas (elle arrive par `BC.Units[].TertiaryAbility`).
Une entrée serait donc INERTE ; et le seed DÉCISION ne prend que les classes
`active_condition_ported` + `seed_witness_effect`, que cet effet n'a pas. Même arbitrage explicite
que `martial_superiority.py`. À rouvrir SI un porteur **spawné** apparaît — il n'en existe aucun
(les trois `allowedUnits` sont des HEROES du pool).

## 8. Les DEUX faces

* **EXÉCUTION** — portée ici, foyer unique `AttackDamageOperation._crit_params` (`damage.py`), la
  façade CRIT partagée par les 3 vecteurs d'attaque.
* **DÉCISION** — **rien à porter, et c'est LU** : `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`
  évalue `CouldCrit(attacker)` sur `GetStat` **NU** ; la couche calc-time
  `GetCritDamageBonusFromEffects` n'a que **deux** appelants (`$$CalculateCriticalDamage` et
  `$$GetCritDamage`, xrefs relues), aucun sur le chemin de prédiction du port. Déjà établi par #N14
  (`case-ischarging-crit-channel.md`) ; ce cas hérite du même régime que ses deux jumeaux.
* **DÉCISION / MOUVEMENT** — déjà portée (#477-r33, #n13) : les deux playbooks.

## 9. Validation — 13 tests, 5 mutants, 5 rouges

`test_kardiocore_galvanus_crit_live.py` (13 passed) et `probe_913_kardiocore_galvanus_live.py`.
Tous les bras : LIVE == OFFLINE **bit-exact**, coup par coup.

| bras | compteur natif | port | résultat |
|---|---|---|---|
| `n = 0 / 1 / 2`, lvl 3 | 0 / 1 / 2 | idem | bonus `None` / **+327** / **+654** — le PRODUIT discrimine |
| `--trait LivingMetal`, `Vehicle` | 2 | 2 | les TROIS traits d'`IsMechanical` comptent pareil |
| `--trait Hero` (négatif) | **0** | 0 | `MechanicalUnitsSelector` mord |
| `--ennemi` (2 mécaniques adverses adjacents) | **0** | 0 | `Friends(reference = Owner)` mord |
| `--porteur-defenseur` | **2** (PLEIN) | 2 | bonus `None` — `get_OwnerIsCaster` mord |
| `--level 1` / `10` | 2 | 2 | **+590** / **+876** — les paliers discriminent |

⚠ **Le bras `--porteur-defenseur` est le seul qui sépare cet effet de ses jumeaux**, et ce qui le
rend probant est son **TÉMOIN NON NUL** : le compteur vaut 2 et le canal se tait quand même. Un
bras à compteur nul aurait été vert par dégénérescence.

**Mutants** — `M1` `get_OwnerIsCaster` → `get_OwnerIsTarget` (2 rouges) ; `M2` filtre
`MechanicalUnits` retiré (`2 == 0`) ; `M3` `AdjacentFriends` → `AdjacentUnits` (`3 == 0`) ;
`M5` `ForAddition` → `ForSubtraction` (2 rouges) ; `M6` niveau PASSIF au lieu de TERTIAIRE
(rouge à `level 1`, **vert à `level 10` — attendu et assertionné** : le repli clampe au dernier
palier, le régime y est dégénéré).

**Deux pièges de montage MESURÉS**, tous deux réparés dans le probe :

1. l'occupation pré-soustraite proposait comme ancre une tuile **encore occupée** → `place` échouait
   sans que rien ne désigne la cause (REFUS sur les trois valeurs de `n`) ;
2. `place` est un `MoveUnitOperation` **complet** : amener une unité adverse au contact déclenche
   les réactions du porteur (`OptimizedGait` attaque au mouvement) et **consomme son action** —
   l'`applyAction` suivant rend `mutated: false, changes: []`, **sans erreur**. Les autres bras y
   échappaient par hasard. Le montage récupère l'action par un cycle de tour.

## 10. Ce qui n'est PAS couvert

* l'attaque **à DISTANCE** du porteur (`admecMarshall` a une 2ᵉ arme `Range 2`) : le décompilé ne
  porte **aucun** gate `IsRangedAttack` sur ce canal, donc rien ne le distingue — non requis, mais
  non confronté ;
* `admecDestroyer`, 3ᵉ porteur autorisé — même classe, même config, aucun discriminant attendu ;
* `$$GetLocalizationDataInternal` (`{AbilityParam(0x21) : <GetExtraCritAmount>}`) : affichage seul,
  aucun observable de combat — non porté, et c'est dit plutôt que supposé ;
* les unités à **empreinte multiple** (multi-tuiles) adjacentes au porteur.
