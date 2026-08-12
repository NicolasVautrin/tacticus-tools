# #952 — deux passifs de kit SANS face `CreateTrigger` propre

`HuntersBeyondDeath` (`spaceHound` « Tjark ») et `GalvanicField` (`admecManipulus` « Actus »). Les
deux étaient le dernier item manquant de leur kit ; les deux porteurs sont au pool (97 unités),
aucune injection catalogue.

## 1. Recensement — par le bloc `methodPointers`, jamais par grep de nom

Le tableau de pointeurs du PE est lu, résolu pointeur par pointeur, et **segmenté par classe**.
Chaque bloc est donné avec sa proportion de **corps PROPRES** (un corps qu'aucune autre classe ne
partage — les autres sont fondus par l'ICF et n'apparaissent donc **pas** dans
`frida/methods.tsv`).

| classe | slots | propres | faces DÉDUPLIQUÉES (donc invisibles au grep) |
|---|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HuntersBeyondDeathAbility` | 3 | **1** | `CreateTrigger` (= `…Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`), `.ctor` |
| `IdunBattle.Entities.Effects.Loki.HuntersBeyondDeath_ExtraDamageEffect` | 4 | **1** | `.ctor`, `CreateActiveCondition` (= `…WisdomOfTheAncients_DamageReductionEffect$$…`), `CreateTargetSelector` (= `…WhisperingWebEffect$$…`) |
| `IdunBattle.Entities.Effects.Loki.HuntersBeyondDeathEffect` | 4 | **2** | `.ctor`, `CreateActiveCondition` (= `…WayOfTheShortBlade_AdditionalAttackMarkerEffect$$…`) |
| `IdunBattle.Entities.Effects.Loki.HuntersBeyondDeathPsykerSuppressionEffect` | 3 | **1** | `.ctor`, `CreateActiveCondition` |
| **total `HuntersBeyondDeath`** | **14** | **5 (36 %)** | |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GalvanicFieldAbility` | 3 | **1** | `CreateTrigger` (même corps que ci-dessus), `.ctor` |
| `IdunBattle.AI.Playbook.Loki.GalvanicFieldPlaybook` | 3 | **3** | — |
| ses deux itérateurs `<Calculate…InStepsInternal>d__N` | 6 + 6 | 3 + 3 | `.ctor`, `Dispose`, `IEnumerator<T>.get_Current` |
| **total `GalvanicField`** | **18** | **10 (56 %)** — **4/6 hors itérateurs** | |

**LES DEUX ITEMS ONT UN `CreateTrigger`.** Le « 0 `CreateTrigger` » du dispatch est un artefact du
grep de nom : le corps est le **même pour les deux**, fondu par l'ICF avec celui d'une troisième
classe, et il rend `<DSLTriggers+0x30>` — le trigger d'INIT **partagé** que
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` met en cache :
`On(0x21 = EventTriggerType.AbilityInit) & <YesTrigger> & get_OwnerIsActor`.

⇒ registre `ABILITY_INIT_OWNER_EFFECTS`, **jamais** `ABILITY_TRIGGERS` — même arbitrage que
`EnmityForTheUnworthy` (#948).

**Comment `<DSLTriggers+0x70>` et `<+0x40>` ont été identifiés comme le MÊME `YesTrigger`** : les
deux sont construits par `DSLTriggers$$.ctor` à partir de la **même classe** avec le **même ctor
vide**, et le champ voisin `<+0x48>` de la même classe est `op_LogicalNot(new <cette classe>())` —
or `<DSLTriggers>+0x48` était déjà lu comme la constante **FAUSSE**
(`runner/abilities/base.py`). Les trois `CreateActiveCondition` du kit sont donc des constantes
VRAIES : aucun `active_condition_ported`.

**Comment la segmentation `.ctor` a été tranchée** : le `.ctor` de
`HuntersBeyondDeathPsykerSuppressionEffect` a **exactement 3 références** dans le tableau — une par
classe du kit. La lecture « `.ctor` en fin de bloc » attribuerait à `PsykerSuppression` le corps
`…HuntersInstincts_ExtraDamageEffect$$.ctor`, qui appelle `StaticStatModifierEffect..ctor` — or
`classes.tsv` donne `BaseEffect` pour base de `PsykerSuppression`. Réfuté. (Les faces NON-ctor,
elles, s'attribuent **à l'identique** sous les deux lectures : la RE est robuste au doute.)

## 2. `HuntersBeyondDeath` — les arbres (mirror 1:1)

```
HuntersBeyondDeathAbility$$CreateBehaviour
      AddEffect(0x4a6 = 1190 HuntersBeyondDeath,             AbilityStateReference, Owner@+0x30, Owner@+0x30, options = default)
    + AddEffect(0x494 = 1172 HuntersBeyondDeath_ExtraDamage, …)
    + AddEffect(0x4a7 = 1191 HuntersBeyondDeathPsykerSuppression, …)
    (op_Addition, pas op_BitwiseAnd ; options Nullable mises à ZÉRO -> PERMANENT)

HuntersBeyondDeath_ExtraDamageEffect$$CreateEffectDamageBonusForAttack
    ForAddition( get_OwnerIsCaster & HasTrait(Target@+0x60, 0x3ea = Psyker),
                 ConfigVar(8 = extraDmg, GetAbilityState(effet), config@+0x60) )
HuntersBeyondDeath_ExtraDamageEffect$$CreateTargetSelector   =  <DSLSelectors+0x30> = Owner   (SELF)

HuntersBeyondDeathEffect$$CreateEffectDamageMalusForDefense
    src = EffectSource(Effect@DSLSelectors+0x38)
    ForSubtraction( NOT AreFriends(src, Caster@+0x48, 0, false)
                  &     AreFriends(src, Target@+0x60, 0, false)
                  &     HasTrait(Caster@+0x48, Psyker)
                  & NOT AmountIsGreater(MinDistance(src, Caster@+0x48), Direct(2)),
                    ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60) )
HuntersBeyondDeathEffect$$CreateTargetSelector
    UnitsWithTrait( SurroundingEnemies(Owner@+0x30, <+0x50>, range = 2, unique = 1, selType = 3),
                    Psyker, 3 )

HuntersBeyondDeathPsykerSuppressionEffect   — AUCUN canal de dégât (déjà porté côté cible, #418-r1)
```

**Surcharges tranchées par l'ADRESSE RÉELLE de la cible du `call` (`E8 rel32`)** : `ConfigVar` =
la variante `(variableType, abilityState : IAbilityStateSelector, config)` (donc le 1er argument
est bien un `AbilityVariableType`) ; `AmountIsGreater` = la variante `(IAmountFormula,
IAmountFormula)`, **et son corps a été relu** —
`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` finit littéralement
sur `return minAmount < amount`, comparaison **STRICTE**. Le `op_LogicalNot` du call-site donne donc
`d <= 2`, borne **INCLUSE**. C'est exactement le piège de mislabel ICF que `battle_query.py`
signale : ici c'est le CORPS du trigger qui tranche, pas le nom du `.ctor`.

**Ce que le REBASE a supprimé, et c'est une mesure.** La tranche avait threadé `att_pos` /
`owner_pos` dans les deux foyers de contexte défenseur (`damage_model.defender_modifiers`,
`playbook/prediction/_shared`) — sous le nom `pos` côté `attacker_ctx`. Le rebase sur `origin/master`
a montré que **#950 (`TerrorsLament_DamageReduction`) venait de poser exactement les mêmes deux clés,
sous les noms `att_pos` / `owner_pos`, pour un gate géométrique DIFFÉRENT** (`IsAdjacent(Caster,
Owner, 3)`). Résolution : les clés de #950 sont ADOPTÉES telles quelles, la variante `pos` est
SUPPRIMÉE (une seule clé pour une seule donnée), et il ne reste de cette tranche qu'**une** clé neuve
par foyer — `att_traits`, le `HasTrait(Caster, Psyker)`. Deux gates indépendants convergent sur le
même triplet parce que c'est l'`AbilityEntities` natif que les deux mirrorent ; livrer sans rebaser
aurait créé un fork de nommage sur un foyer partagé.

`DSLFormulas$$MinDistance(a, b)` passe par
`IdunBattle.Core.Services.BattleQuery$$GetMinDistance(tilesA, tilesB)` = MIN de `GetDistance` sur le
produit des deux jeux de tuiles — distance **hexagonale**, aucun pathfinding. Foyer porté :
`engine/entities/effects/base.py::min_distance_at_most`, distinct d'`is_at_range` (qui est une
ÉGALITÉ).

### Les écarts qu'une recopie du voisin aurait effacés

1. **1172 est un effet SELF, 1190 est une AURA** — et cela ne se lit QUE dans le corps dédupliqué de
   `CreateTargetSelector` de 1172 (`<DSLSelectors+0x30>` = Owner). Le brancher sur le canal AURA de
   son voisin l'aurait rendu **inerte sur son propre porteur**, c'est-à-dire inerte tout court :
   l'agrégateur `aura_attack_damage_bonus_from_allies` EXCLUT `att_id == owner_id`.
2. **1190 exige DEUX pattes de port, pas une.** `IdunBattle.Entities.UnitExtensions$$IsFriend`
   n'écarte pas l'égalité, donc `AreFriends(src, Target)` est VRAI quand Tjark **est** le défenseur ;
   or les DEUX call-sites de `aura_defense_damage_malus_from_units` sautent le porteur
   (`uid == tgt_id -> continue`). D'où `create_effect_damage_malus_for_defense` (SELF) **plus**
   `create_aura_defense_damage_malus_for_ally` (alliés). Foyers disjoints : ni trou, ni
   double-compte. Le mutant `m_self` (live) ne fait diverger QUE le bras `self` — c'est la mesure
   de cette disjonction.
3. **Le SÉLECTEUR de 1190 n'est PAS son gate.** Le sélecteur matérialise `EffectComponent.Targets`
   (les Psykers ennemis à 2) ; la condition d'application, elle, **re-dérive** la géométrie par
   `MinDistance(src, Caster)` et porte sur l'**attaquant du coup**. Les deux ne visent pas le même
   sujet. Le port ne consomme donc pas ce sélecteur (résidu #952-r1).
4. **La borne est INCLUSIVE.** `d = 2` doit passer. Le mutant `m_dist` (borne stricte) fait diverger
   `aura_pres`, où Tjark est à exactement 2.
5. **`extraDmg` et `dmgReduction` portent le MÊME tableau** (65 valeurs, 8..582, les deux dans
   `variablesAffectedByRarityBonus`). Aucun levier NUMÉRIQUE ne sépare les deux faces — ce qui les
   sépare est leur canal et leur gate. Voir §5.

## 3. `GalvanicField` — verdict MESURÉ : rien à porter, et les trois raisons

```
GalvanicFieldAbility$$CreateBehaviour
      AddFlag(Owner@+0x30, 0x18 = UnitFlag.CanRepairFullHealthUnits)
    & RemoveActiveAbility(Owner@+0x30, 0x1c = ActiveAbilityType.Repair)
    & AddActiveAbility(Owner@+0x30, 0x45f = ActiveAbilityType.Repair_GalvanicField, abilityState)
```

**Mesure live** (`combatSnapshot`, runner 367, board MC1_67) sur `admecManipulus` :

```
unitFlags     = [24]
abilityStates = [ {1117 DefendTheDivineWork, kind active}, {1119 Repair_GalvanicField, kind granted, level 50, multiplier 180} ]
```

— soit les **trois** feuilles déjà appliquées par le natif AVANT la capture. Côté port :

| feuille | consommateur porté | état |
|---|---|---|
| `AddFlag(CanRepairFullHealthUnits)` | `snapshot._load_unit_flags` → `UnitFlagsComponent` → `attack_query.entity_can_be_repaired` (disjunct `HasFlag(caster, 0x18)`) | **branché** |
| `AddActiveAbility(1119)` | `unitAbilityStates.actives[]` → `ABILITY_CLASSES[1119]` (`Repair_GalvanicFieldAbility`, #299/#334, masque + `AbilityAttackType` posés) | **branché** |
| `RemoveActiveAbility(28)` | rien à retirer : le port ne dérive **jamais** `Repair` d'un trait (`"Mechanic" not in TRAIT_DERIVED_ABILITIES`), sa liste d'actives vient de la capture POST-échange | **structurellement satisfait** |

**Face DÉCISION : DEAD, lu au décompilé.** `IdunBattle.AI.Playbook.Loki.GalvanicFieldPlaybook` a
ses **3 corps propres**, et les deux itérateurs qu'ils rendent ont un `MoveNext` dont le corps
ENTIER est « `state = -1` ; `current = Fix64.op_Implicit(0)` ; `state = 1` ; return true » puis
`return false`. Les DEUX utilités (`CalculateMovementUtilityInStepsInternal`,
`CalculateAttackUtilityInStepsInternal`) rendent donc **`Fix64(0)`** et rien d'autre. Porter ce
playbook ajouterait un terme nul.

⇒ **`GalvanicField` : aucun code à écrire.** Le livrable est le VERDICT + son cliquet exécutable
(`test_952_hunters_beyond_death_offline.py`, section [6]), qui rougit si l'un des trois
consommateurs disparaît. Résidu #952-r2 pour le seul régime non couvert.

## 4. Validation

**Offline** — `tests/engine/test_952_hunters_beyond_death_offline.py`, 34 tests dont **8
contre-épreuves par MUTATION**, l'une d'elles écrite comme une **NON-morsure mesurée** (§5).

**Live** — `probe_952_hunters_beyond_death.py` + `tests/engine/runner/…_live.py`, board `MC1_67`,
seed `4321`, géométrie **calculée** depuis le `boardGraph` puis **assertionnée** contre les
positions réelles (un bras qui n'obtient pas sa configuration rend `indisponible`, ce qui fait
ÉCHOUER le test — jamais un skip). Rejeu offline depuis la même capture, même flux RNG,
comparaison **coup par coup** :

| bras | régime | natif | port | écart |
|---|---|---|---|---|
| `self` | psyker ennemi frappe TJARK, d = 1 | `[519, 311]` = 830 | 830 | 0 |
| `aura_pres` | il frappe l'ALLIÉ, Tjark à d = **2** | `[765, 692]` = 1457 | 1457 | 0 |
| `aura_loin` | même attaque, Tjark à d = 5 | `[1403, 1330]` = 2733 | 2733 | 0 |
| `extra` | TJARK frappe le psyker (face 1172) | `[2323, 2829, 2378, 0]` = 7530 | 7530 | 0 |

`aura_pres` vs `aura_loin` : **−1276** de dégât natif pour la seule position de Tjark — le probe
REFUSE de conclure si les deux régimes rendent le même total.

⚠ **La comparaison porte sur la LISTE des coups, jamais sur le scalaire `total`** : quand l'attaque
TUE (bras `extra`), le natif tague `Amount = 0` pour les coups suivants alors que le `total` côté
port porte encore le dégât BRUT du coup surnuméraire (mesure : 7530 contre 10390). Les listes, elles,
coïncident — c'est donc la liste qui est l'observable.

**Les cinq mutants mordent, et chacun SUR SON BRAS** (c'est ce second cran qui établit que les deux
pattes de 1190 sont disjointes) :

| mutant | bras divergents | inerte ailleurs |
|---|---|---|
| `m_effet` (1190 hors `EFFECT_CLASSES`) | `self` (+865), `aura_pres` (+1276) | `aura_loin`, `extra` |
| `m_self` (patte SELF neutralisée) | `self` seul | `aura_pres`, `aura_loin`, `extra` |
| `m_aura` (patte AURA neutralisée) | `aura_pres` seul | `self`, `aura_loin`, `extra` |
| `m_dist` (borne stricte `< 2`) | `aura_pres` seul | `self`, `aura_loin`, `extra` |
| `m_extra` (1172 hors `EFFECT_CLASSES`) | `extra` seul | les trois autres |

## 5. La mutation qui NE MORD PAS — écrite comme un résultat

Échanger `extraDmg` et `dmgReduction` **ne change aucun chiffre** : les deux tableaux du gameconfig
sont **identiques** (65 valeurs, 8..582, tous deux rarity-scalés). Aucun levier numérique ne sépare
les deux faces du kit ; un test de magnitude seul aurait été **inerte** sur cette confusion. Ce qui
les sépare est structurel — le **canal** (`ForAddition` attaquant contre `ForSubtraction` défenseur)
et le **gate** (`HasTrait(Target, Psyker)` contre `HasTrait(Caster, Psyker)` + distance). Les deux
sont gardés ; la non-morsure est gardée elle aussi
(`test_mutation_variable_croisee_NE_MORD_PAS`), pour qu'un lecteur futur ne la prenne pas pour un
oubli.

## 6. Ce que ce lot mesure sur le CRITÈRE de groupement

Le critère « 0 face `CreateTrigger` » **ne prédit rien** — il était faux : les deux items en ont une,
partagée et fondue par l'ICF. Ce qui a prédit, c'est la **proportion de corps PROPRES** :

* `HuntersBeyondDeath` = **5/14 (36 %)** → **9 faces invisibles au grep**, dont deux qui changent le
  port (le `CreateTargetSelector` SELF de 1172, les trois `CreateActiveCondition` constantes) → un
  vrai port, 3 classes, 2 foyers partagés threadés, 4 bras live, 5 mutants ;
* `GalvanicField` = **10/18 (56 %)**, et surtout **4/6 hors itérateurs**, dont un playbook entier à
  corps propres → aucune face cachée, tout est lisible du premier coup → **verdict, zéro ligne de
  port**.

Le prédicteur n'est donc pas le nombre de méthodes (6 contre 14 au dispatch) mais l'inverse : le
kit qui déclare le MOINS de corps propres est celui qui cache le plus. Coût propre mesuré :
`HuntersBeyondDeath` ≈ **4×** `GalvanicField` (RE + port + 2 fichiers de test + 1 probe contre RE +
verdict + section de test).

## 7. Résidus

* ~~**#952-r1**~~ — **FERMÉ EN REFUS, et le refus est désormais VÉRIFIABLE.** Prémisse re-mesurée le
  2026-08-12 : `EFFECT_TARGET_SELECTORS` porte exactement `{1026, 1191}`, et **aucun** consommateur
  du foyer (`playbook/psyker.py`, `playbook/savior_protocols.py`,
  `entities/effects/loki/damage_reduction.py`, `runner/operations/movement.py`) n'interroge `1190` —
  la fiche tient, aucun lecteur n'est apparu. `is_effect_target(_, _, 1190)` rend donc `None`
  (« non porté »), jamais `False`.
  Ce qui a été ajouté, c'est le cran contre la confusion que la fiche mettait en garde :
  `tests/engine/test_952r1_geometrie_non_consommee_offline.py` **INSCRIT réellement** 1190 au
  registre avec une géométrie qui rendrait tout le monde cible, et vérifie que les **quatre**
  verdicts du gate du malus sont **inchangés** — parce que le gate re-dérive
  `MinDistance(EffectSource, Caster@+0x48) <= 2` et porte sur l'**ATTAQUANT**, là où le sélecteur
  vise les **Psykers ennemis**. Deux sujets, aucun chemin partagé : brancher l'un ne branche pas
  l'autre. Le fichier grave aussi que le gate MORD dans les deux sens (d = 2 vs d = 3, trait
  présent vs absent), sans quoi l'étage précédent serait vide de sens.
  À rouvrir dès qu'un nœud porté lira la liste `Targets` de 1190.
* **#952-r2 — `GalvanicField` n'a AUCUN filet de spawn.** Ses trois feuilles arrivent par la
  capture ; un `admecManipulus` matérialisé sans capture (spawn offline pur) n'aurait ni le flag ni
  l'échange d'ability. Aucun chemin de spawn ne le produit aujourd'hui (ce n'est ni un summon ni un
  deep-strike), donc le régime est **inatteignable** — d'où le refus de porter un filet spéculatif,
  et le résidu qui le nomme.
* **`MinDistance` sur sélecteur VIDE** : `GetMinDistance` seede à `int.MaxValue` et rend **−1** quand
  aucune paire de tuiles n'existe, ce qui rend `NOT (−1 > 2)` VRAI côté natif. Le port ferme
  (position absente ⇒ gate FAUX). Le régime n'a pas de substrat offline (une unité sans position
  n'est pas placée) et ouvrir un gate sur une inconnue serait pire ; l'écart est NOMMÉ dans le foyer.
* **Le cas où la CIBLE de 1172 n'est pas mesurée** (`target_traits` absent) ferme le gate : sous-compte
  possible, jamais sur-compte. Même convention que `owner_is_caster`.
