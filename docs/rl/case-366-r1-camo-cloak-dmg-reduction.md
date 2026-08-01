# case-366-r1 — `1014 CamoCloak_DmgReduction` : une réduction PLATE gatée par le COUVERT

**Question, binaire.** Le port retire-t-il du dégât ranged reçu par Certus (`ultraEliminatorSgt`)
exactement ce que le natif retire, et se tait-il exactement quand le natif se tait ?

**Réponse : OUI**, sur 3 régimes de couvert × 2 axes × 2 boards × 2 seeds × 2 niveaux, tous
bit-exacts, sans aucun correctif de trajectoire. Porteur HERO **au pool** (`--list-pool` : 97
unités, il y figure) ; voie directe, ni greffe npc, ni injection catalogue, ni relique.

## 1. Ce que l'inventaire annonçait, et ce que le décompilé dit

`case-366-gisement-96-effets.md` §3.3 : « `CreateDamageModifier` + `CreateActiveCondition` ». Les
deux méthodes existent, mais la colonne ne dit ni le CANAL ni la CONDITION — et c'est tout le cas.
Établi à la source :

`IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$CreateDamageModifier` (corps INLINE) :

    EffectBonus.ForAddition(
        get_OwnerIsTarget
          & HasValidEffectTrigger(Target@0x178)
          & IsRangedAttack,
        Multiply( ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60),
                  Direct(-1)@DSLFormulas+0x38 ) )

`IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$CreateActiveCondition` :

    HasValidEffectTrigger(Owner@0x148)

`IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$HasValidEffectTrigger(sel)` — un
seul prédicat, appelé DEUX fois :

    DSLTriggers.HasEffect(sel, 0x3f5 = 1013 LightCover, onlyActive = 0, effectTargetType = 6)
    op_BitwiseOr
    DSLTriggers.IsEffectTarget(sel, 0x402 = 1026 BigTarget_AdjacentEffect)

Sous le `get_OwnerIsTarget` en tête du AND, `Target@0x178` et `Owner@0x148` désignent la MÊME
entité : le gate de couvert est donc porté **une seule fois**, dans `is_active`. Slots lus au
décompilé (`DSLSelectors` = `DSLFactory − 0x118` : `+0x40` = Actor, confirmé indépendamment par
`MarkerlightEffect$$CreateDamageModifier` que le port documente déjà `HasFaction(actor@0x158)`).

**Le canal n'est PAS celui de `1110 FireAndReposition`** (le voisin de PR #408). Deux noms natifs
différents, deux slots différents de la struct `EffectBonus` — et pourtant le même bac d'arrivée
côté port, ce qui n'était pas déductible du nom :

| | natif | slot `EffectBonus` | port |
|---|---|---|---|
| `1110` | `CreateEffectDamageMalusForDefense` → `ForSubtraction` | **+0x18** | `flat_reductions` |
| `1014` | `CreateDamageModifier` → `ForAddition(… × Direct(-1))` | **+0x10** | `flat_reductions` |

Le slot est lu au corps inline, pas déduit : `EffectBonus$$ForAddition` écrit `ret+0x10`,
`ForPercentIncrease` `ret+0x08`, `ForSubtraction` `ret+0x18`, et le corps de `1014` écrit `+0x10`.
Le `× Direct(-1)` rend le montant négatif ⇒ soustraction plate. **Jumeau STRUCTUREL EXACT** de
`PsychicFortress_DmgReductionEffect$$CreateDamageModifier` (déjà porté, même `ForAddition(Multiply(
ConfigVar 0x12, Direct(-1)))`) → `for_subtraction(False, |amt|)` = additif DÉFENSEUR **PRÉ-perçage**
(famille Nightshroud, ground truth #120/#111).

Corollaire de mesure : le montant config n'est le dégât retiré **que si l'armure du porteur est
nulle** — d'où `--hp-player` dans le montage, qui la met à 0 et fait lire la soustraction 1 pour 1.

## 2. Le gate est un gate de COUVERT, et l'i2 le paraphrase

i2 : « Whenever an incoming **ranged attack has its number of hits reduced for any reason**, it
deals -{dmgReduction} Damage per hit to this unit. »

« for any reason » est une paraphrase, pas la règle. Le natif **nomme deux ids et rien d'autre** :
`1013 LightCover` (−2 coups ranged) et `1026 BigTarget_AdjacentEffect` (−1 coup ranged). Les autres
réducteurs de coups du jeu — `Camouflage`, `Diminutive`, `FightingRetreat_HitReduction` — n'y sont
PAS. Un port écrit d'après l'i2 aurait donc été trop large ; c'est le décompilé qui tranche.

Les deux membres passent par des primitives DIFFÉRENTES, et c'est structurel :
`IdunBattle.Entities.EntityExtensions$$HasOneOfEffects` a deux branches (`targetType & 2` →
`IsOwnerOfEffects`, `targetType & 4` → `IsTargetOfEffects`) ; `1013` est POSSÉDÉ par l'unité en
couvert, `1026` est possédé par l'ami `BigTarget` et CIBLE ses voisins — d'où `HasEffect` pour le
premier et `IsEffectTarget` pour le second.

⚠ **`onlyActive = 0`** (lu au décompilé) : le natif ne consulte PAS `EffectComponent.IsActive` sur
`1013`. Le mirror est donc `EffectsState.has_effect` (filtre `consumed` seul) et **pas**
`active_effects` — qui rappellerait `is_active` et bouclerait, ce lecteur alimentant justement le
`unit_state` des `is_active`. La fidélité et la terminaison coïncident ici ; ce n'est pas un
contournement.

### Le natif expose ce gate une seconde fois, et elle est mesurable directement

`EffectComponent.IsActive` (champ ECS relu par le hook, publié en `decisionView.effects[].active`)
suit le couvert — **mesuré**, sans rien déduire du port :

| régime | `1013` sur Certus | `1026` sur l'ami | `1014` canal actif | `IsActive` |
|---|---|---|---|---|
| `bigtarget` | absent | **présent** | **présent** | **True** |
| `lightcover` | **présent** | — | **présent** | **True** |
| `none` | absent | — | absent | **False** |

## 3. La magnitude est indexée par le niveau **PASSIF**

`...CamoCloak_DmgReductionEffect$$.ctor` = `xor r9d,r9d ; xor r8d,r8d ; mov edx, 0x3eb ;
jmp <DamageModifierAbilityEffect$$.ctor>` — cible du `jmp` **calculée depuis l'encodage** (rel32),
pas choisie à l'œil parmi les trois homonymes. Ce `.ctor` appelle la surcharge d'
`IdunBattle.Core.AbilityOrEffect$$op_Implicit` qui exécute **`set_TriggeredAbility`** — surcharge
tranchée **par son corps**, jamais par son nom. Donc l'`AbilityState` que résout
`GetAbilityState(effet)` est celle d'une ability NON-active ⇒ **niveau PASSIF** du porteur.

`0x3eb = 1003 = TriggeredAbilityType.CamoCloak` (et `unit_map kit ultraEliminatorSgt` le classe
`voie: passive`). ⚠ Piège d'enum voisin : `0x3f6 = 1014` est `EffectType.CamoCloak_DmgReduction`
côté `AddEffect`, mais **`TriggeredAbilityType.RitesOfBattle`** — le port a déjà une classe pour
cet homonyme (`RitesOfBattlePlaybook`, ability 1014). Deux enums, même valeur.

`ConfigVar(0x12)` = `AbilityVariableType 18 = dmgReduction`, 65 niveaux (5 → 364 ; L50 = **277**), et
`dmgReduction ∈ variablesAffectedByRarityBonus` ⇒ scalé par le multiplier de rareté : `277 × 1.8 =
**499**`.

**Le régime nominal est DÉGÉNÉRÉ** (`buildNormalizedBC` met passif ET actif à 50) : lire l'un ou
l'autre y donne le même chiffre. Le montage les dissocie
(`--unit-stat "ultraEliminatorSgt:PassiveAbilityLevel=30"`, actif 50) :

* natif — retire `dmgReduction[30] × 1.8 = **119**` ;
* si le port avait lu l'ACTIF — il retirerait `dmgReduction[50] × 1.8 = **499**`.

Le port rend 119. C'est la seule mesure qui pouvait RÉFUTER la lecture du `.ctor`.

## 4. La pose

`IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour` :

    AddEffect(0x3f6, <BaseTriggeredAbility.get_AbilityStateReference>, Owner@0x148, durée = 0)

`BaseTriggeredAbility` malgré le namespace `Abilities.Active.Loki` : c'est un PASSIF, la pose est
permanente et a lieu à l'init du porteur. `source == targets == Owner` ⇒ pas de régime
« porteur ≠ source » (#382).

## 5. Mesures live — 3 régimes × 2 axes × 2 boards × 2 seeds, toutes bit-exactes

Montage : `probe_366_r1_camo_cloak.py` (`ultraEliminatorSgt` [+ `astraBullgryn` en régime
`bigtarget`] vs `necroWarden`, pilotage des DEUX camps, géométrie de couvert FABRIQUÉE, captures,
rejeux offline sur le MÊME flux MT). `necroWarden` porte **une arme mêlée ET une arme ranged r3** :
le même ennemi sert les deux axes, une variable de moins. `--crit 0,0 --crit-target 0,0
--block-target 0,0 --block-player 0,0` : une seule variable bouge.

| | `bigtarget` / `MC1_67`+31337 | `bigtarget` / `C4_09`+4242 | `lightcover` / `C4_09`+4242 |
|---|---|---|---|
| RANGED — **live** | `[17632]` | `[19335]` | `[19335]` |
| RANGED — **port** | idem | idem | idem |
| CONTRE-ÉPREUVE (sans 1014, même flux) | `[18131]` | `[19834]` | `[19834]` |
| **écart par coup** | **499** = `dmgReduction[50] × 1.8` | **499** | **499** |
| CONTREFACTUEL de couvert (support retiré) | 1er coup `18131` | 1er coup `19834` | 1er coup `19834` |

Les deux colonnes `C4_09` coïncident : même board, même seed, même position d'attaque — mais **deux
voies de couvert différentes** (`1026` porté par un ami vs `1013` porté par Certus). C'est ce qui
rend l'égalité informative : les deux membres du `op_BitwiseOr` produisent le même dégât, comme le
natif.

| autres bras | mesure |
|---|---|
| MÊLÉE, `bigtarget`, effet ACTIF | live `[20425]` / port idem / **sans effet idem** — le gate `IsRangedAttack` ferme |
| SANS couvert (`none`) | natif `IsActive = **False**`, absent du canal actif ; live `[18131, 20425]` == port ; sans effet **identique** |
| NIVEAU dissocié (passif 30 / actif 50) | live `[18012]`, sans effet `[18131]` → **écart 119**, pas 499 |

**Cohérence croisée entre runners indépendants** : le régime `none` (2 coups pleins, `18131` au
premier) et le régime `bigtarget` (1 coup, aura `−1 hit`, `17632`) donnent `18131 − 17632 = 499`
— exactement la valeur de config, obtenue sur deux montages qui ne partagent rien.

**Deux pièges de mesure, tous deux dans le probe :**

* **Le contrefactuel de couvert change le NOMBRE de coups.** Retirer le support (`1013` ou `1026`)
  retire du même geste sa réduction de coups. La comparaison est donc **coup à coup**, jamais liste
  à liste — et c'est littéralement ce que dit l'i2. Une garde écrite « liste == liste » aurait
  rougi sur un port CORRECT.
* **La géométrie ne se subit pas.** L'ami `BigTarget` est AMENÉ en ring-1 et l'ennemi à distance 3
  (ou 1) par un sweep multi-tours ; en régime `lightcover`, Certus est DÉPLACÉ sur une `DryBush`
  (`MC1_67` n'en a que 3, hors de sa portée depuis le spawn — d'où `C4_09`, qui en a 17).

## 6. Mutations adversariales — les gardes sont ROUGES quand on les casse

| mutation | ce qui rougit |
|---|---|
| **M1** inscription `EFFECT_CLASSES` retirée | 6/7 — `1014 est route sur BaseEffect`, et `live [18012] ≠ port [18131]` |
| **M2** gate `IsRangedAttack` neutralisé | 5/7 — `le gate IsRangedAttack ne ferme pas (['Subtraction', 119])` |
| **M3** `is_active` → `True` (ActiveCondition neutralisée) | 1/7 — seul le CONTREFACTUEL de couvert |
| **M4** magnitude lue sur `active_ability_level` | 1/7 — seul le bras NIVEAU DISSOCIÉ (`499` au lieu de `119`) |
| **M5** clés de couvert retirées du `unit_state` runner | 6/7 — `us_light_cover=None`, gate dégradé en VRAI |
| **M6** clés de couvert retirées de `Scene.unit_state` | 5/7 — fork moteur/prédiction |

M3 et M4 sont les mutations qui comptent : **le régime nominal les déclare vertes**. M3 parce que
le canal live-seed ne publie que les effets actifs (le natif a déjà fermé) — seul le contrefactuel
offline, où l'instance survit, l'attrape. M4 parce que `buildNormalizedBC` égalise les deux niveaux.

## 7. La face DÉCISION-MOUVEMENT existe, et elle est **registered-but-DEAD** (mesuré)

`IdunBattle.AI.Playbook.Loki.CamoCloakPlaybook` (`.ctor` : `0x3eb = 1003`) a son propre
`CalculateMovementUtilityInStepsInternal`. Corps remis en C# depuis
`...CamoCloakPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

    int val = 0;
    var tile = UtilityMovementCase.get_MovementTile(case);        // = UnitPosition.get_MainTile
    var trig = DSLTriggers.HasEffect(DSLSelectors.Entity(tile), 0x3f5, onlyActive: 0, targetType: 6);
    if (trig != null && trig.ShouldTrigger(entities))
        val += getUtilityVal("CAMOCLOAK_LightCover");             // BC = 15
    yield return Fix64.op_Implicit(val);

Le prédicat interroge l'**entité-TUILE**. Or `1013 LightCover` n'y est jamais :

1. **Décompilé** — `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$CreateBehaviour`
   = `AddEffect(0x3f5, stateRef, UnitsThatNeedEffect(), 0)`, et `UnitsThatNeedEffect` =
   `UnitsWithoutTraits(EntitiesWithoutEffects(Units(coverPatch@0x30), [0x3f5]), <traits>)` : les
   CIBLES sont des **unités**. La branche `IsTargetOfEffects` ne peut donc pas rendre la tuile.
2. **Mesure live** — `tileMeta` publie littéralement l'`EffectsOwnedComponent.ActiveEffectIds @0x10`
   des entités `Tile` (`readEffectsByTile`), c'est-à-dire **la liste même** qu'itère
   `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffectOfType`. Sur `C4_09`, **17 tuiles
   `DryBush`, 0 avec `1013`** — y compris celle qu'occupe Certus, qui porte lui `1013` dans SES
   effets (`effects: []` côté tuile, vérifié aussi avec `includeInactive: true`). Les tuiles savent
   pourtant porter des effets : `Thorns_DefenseReduction`(11), `BlockEnteringUnits`, `Melta_ExtraDmg`
   (1297) apparaissent dans le même relevé.

⇒ le terme vaut **0 pour toute tuile candidate**. `1003` n'est donc **PAS** inscrit dans
`TRIGGERED_MOVE_PLAYBOOKS` : c'est exactement la dégradation que le registre documente (« absence
du registre == 0, même dégradation »), et l'inscrire produirait un +15 que le natif n'accorde
jamais. Le poids BC `Utilities.Default.TriggeredAbilities["CAMOCLOAK_LightCover"] = 15` est
enregistré et jamais consommé.

⚠ Ce verdict est **falsifiable par une seule mesure** : un point d'ancrage natif sur
`IdunBattle.AI.Playbook.Loki.CamoCloakPlaybook.<CalculateMovementUtilityInStepsInternal>d__2$$MoveNext`
(ou sur le `Func<string,int>` qu'il invoque) rendrait le terme directement. Aucun hook existant ne
l'expose, et cette tranche ne réinjecte pas — c'est le résidu NOMMÉ à hooker si on veut le clore
autrement que par les deux lectures ci-dessus.

## 8. Ce qui n'est PAS couvert

* **Le playbook de mouvement n'est pas porté** (§7) — verdict DEAD appuyé sur décompilé + mesure,
  pas confronté par un hook du terme lui-même.
* **Le porteur SUMMON `ultraSmnEliminator` n'est pas confronté.** Il porte le même passif ; sa voie
  (spawner son summoner, observer sans le commander — `case-291`) n'a pas été montée. Le porteur
  HERO suffisait à la confrontation principale.
* **Un porteur capté HORS couvert n'a pas d'instance 1014 matérialisée** : `active_condition_ported`
  reste `False` (le flag capté fait foi, `is_active` ne peut que FERMER en plus). Donc un
  déplacement offline VERS une tuile de couvert ne fait pas apparaître l'effet. C'est un résidu de
  **SEED**, pas de gate ; le combler demanderait une entrée `ABILITY_INIT_OWNER_EFFECTS` +
  `seed_witness_effect` + `active_condition_ported = True`, non fait ici (aucun observable mesuré
  ne l'exigeait).
* **`IsEffectTarget` est re-dérivé géométriquement, pas lu.** Le port ne matérialise pas les cibles
  d'une aura : `is_target_of_adjacent_friend_aura` applique le sélecteur de
  `BigTargetAdjacentEffect$$CreateTargetSelector` (amis hex-adjacents, porteur exclu) sur les
  porteurs de `1026`. C'est la même dérivation que celle déjà en service pour le canal COUPS de cet
  effet ; un `1026` dont le sélecteur différerait la ferait diverger.
* **`CamoCloak` (1003) n'entre pas dans `ABILITY_CLASSES`** : c'est une TRIGGERED, non castable —
  les obligations `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE` ne s'y appliquent pas. Cliquets
  re-joués : `probe_181` (98/98, 0 manquante), `probe_120 --step 0` (0 littéral manquant).
* **Aucune mesure de l'EXPIRATION** : la pose est permanente (durée 0), rien à mesurer, mais le
  cycle « entrer puis SORTIR du couvert en cours de bataille » n'a été exercé qu'offline (le
  contrefactuel), jamais live.

## 9. Artefacts

| quoi | où |
|---|---|
| classe d'effet + prédicat de couvert | `scripts/python/engine/entities/effects/loki/damage_reduction.py` (`CamoCloakDmgReductionEffect`, `camo_cloak_cover`) |
| registre | `scripts/python/engine/entities/effects/factory.py` + `effects/loki/__init__.py` |
| substrat COMBAT du gate | `scripts/python/engine/runner/components.py` (`has_effect_of_type`, `is_target_of_adjacent_friend_aura`, `UnitEffectStateView`) |
| substrat DÉCISION du gate | `scripts/python/engine/playbook/scene.py` (`Scene._camo_cloak_cover_keys`) |
| montage live | `scripts/python/probe_366_r1_camo_cloak.py` |
| gardes | `scripts/python/tests/engine/runner/test_camo_cloak_dmg_reduction_live.py` (7) |
