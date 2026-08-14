# case-1052 — `AllIsDust` et `Pyreblaster` : deux passifs `S?` dont le porteur NPC était la clé

Deux `GAP-ABSENT` de `passive-ability-coverage.md`, tous deux `S?=1 N=1` — « summon sans summoner
dérivable, plus un npc ». L'audit rendait `S?` parce que son graphe de summon ne balaie que les
abilities **des unités** ; la moitié du travail était de le trancher.

## 1. Les porteurs, ventilés

| passif | summon | npc jumeau (`visualId`) | invocateur du summon | chemin retenu |
|---|---|---|---|---|
| `AllIsDust` (1158) | `thousSmnRubricMarine` | `thousNpc3RubricMarine` | `EnvFactionSummons:ThousandSons` (`constants.unitId`, `nrOfSummons` 2) — ability **d'ENVIRONNEMENT** du live-event *Faction War* (`liveEvents.idunLiveEventConfigs[].factionWarData.factions[].abilityId`), portée par AUCUNE unité | **npc**, `--explicit-stats thousNpc3RubricMarine:45` |
| `Pyreblaster` (1098) | `templInitiatePyreblaster` | `templNpc3InitiatePyreblaster` | **AUCUN** — balayage EXHAUSTIF du gameconfig (toute chaîne de l'arbre, pas seulement `constants.unitId*`) : cet `unitId` n'apparaît nulle part hors de sa propre définition. `EnvFactionSummons:BlackTemplars` invoque `templInitiate`, pas lui | **npc**, `--explicit-stats templNpc3InitiatePyreblaster:45` |

Les deux npc portent leur table `units.npc[].stats[]` (45 paliers) ⇒ **confrontables** par le chemin
de stats explicite (case-92 §5bis recours 4), avec LEURS stats, LEURS traits, LEURS armes.

⚠ **Le palier n'est pas cosmétique.** Le perçage est un **PLANCHER**
(`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
= `max(base − armure, base × perçage%)`) : il ne DÉCIDE du dégât que si `armure >= base`. Au palier
3 l'armure du Rubric Marine vaut **37** face à une base de ~1600 — mesuré, `port_avec == port_sans`
alors que `extra = -19` était bel et bien appliqué. Au palier 45 (`FixedArmor` 5740) l'effet devient
observable, facteur **~20×**.

## 2. RE — les deux `CreateTrigger` sont INVISIBLES des tables (ICF)

Ni `AllIsDustAbility$$CreateTrigger` ni `PyreblasterAbility$$CreateTrigger` n'existe comme symbole.
Leurs corps sont **dédupliqués** ; l'appartenance a été établie **slot à slot** dans le bloc
`methodPointers` du PE, puis **confirmée par le CONTENU** :

* `AllIsDust` → même corps que
  `IdunBattleLogic.Entities.Abilities.Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`
  = `<DSLTriggers+0x30>` = `On(0x21 = AbilityInit) & get_OwnerIsActor` ;
* `Pyreblaster` → même corps que
  `IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateTrigger`
  = `On(0x4a = AttackInAtomicGroup, ownerNeedsToBeAlive: 1) & get_OwnerIsActor & IsRangedAttack`.

### `AllIsDust` — un `EffectBonus` de perçage NÉGATIF

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AllIsDustAbility$$CreateBehaviour`
= `AddEffect(0x4a5 = 1189, AbilityStateReference, Caster@<DSLSelectors+0x48>, turns = null)`.

`IdunBattle.Entities.Effects.Loki.AllIsDustEffect$$CreatePiercingBonusForAttack` :

```
total   = Sum( AttackPiercingRatio(),                       # PiercingRatio BRUT du profil
               GetPierceStatModifier(),                     # ExtraPierce + (melee ? ExtraPierceMelee : Ranged), part 5 = Modification
               CasterEffectPierceAddition(excluded = 0x4a5) )
trigger = get_OwnerIsTarget & NOT AmountIsGreater(total, ConfigConst(0x49 = pierceRatio))   # STRICT et NIÉ => total <= 35
montant = Negative( Subtract(total, <DSLFormulas+0x20> = Direct(1)) )                       # -(total - 1)
-> EffectBonus.ForPiercing(trigger, montant)
```

⚠ **Deux bases de perçage différentes, et c'est LU** : `AttackPiercingRatio()`
(`IdunBattle.Entities.Formulas.AttackPiercingRatioFormula$$Calculate`) rend le champ BRUT du profil,
alors que `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` passe par
`StaticBattleRules.Damage$$GetPiercingRatio(profil, traits)`, qui **ajoute** un bonus global quand
le profil porte le `DamageTrait` 3 et que l'attaquant porte le trait `0x3e9` ou `0x3f8`.

### `Pyreblaster` — une attaque DERRIÈRE la cible + deux tuiles en feu

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PyreblasterAbility$$CreateBehaviour` :

```
op_Addition(
  AttackWithAttackDamage( Caster@<+0x48>,
                          Enemies(Caster, Units(TileBehindFilled(CasterTile@<+0x50>, Target@<+0x60>), 1, 3), 3),
                          RandomAmount(GetVariableForLevel(0xc), GetVariableForLevel(0xd)),
                          GetDamageProfile(),                      # Flame
                          GetNumberConstant(0x2f = nrOfHits) = 3,
                          AbilityOrEffect(this), <options ZÉROÉES>, selectionType = 2 ),
  AddEffect( 0x5 = Fire, AbilityStateReference,
             Walkable( TileBehindFilled(CasterTile, Target) op_Addition Tiles(Target@<+0x60>) ),
             turns = null ) )
```

⚠ **Le feu couvre DEUX tuiles**, l'attaque UNE — l'i2 ne mentionne que « the hex behind ».
⚠ **L'ordre du `op_Addition` est ATTAQUE puis FEU**, alors que le nœud `AddEffect` est CONSTRUIT en
premier dans le décompilé.

`IdunBattleLogic.Entities.DSLSelectors$$TileBehindFilled` délègue à `IBattleQuery` **slot 85** =
`IdunBattle.Core.Services.BattleQuery$$GetTilesBehindFilled(from, direction, checkElevation = 1)`.

## 3. Confrontation live (probe `probe_1052_all_is_dust_pyreblaster.py`)

`AllIsDust` — dégât PAR COUP, `thousNpc3RubricMarine:45`, mutation = effet retiré d'`EFFECT_CLASSES` :

| attaquant | profil (perçage) | live | port AVEC | port SANS | verdict |
|---|---|---|---|---|---|
| `adeptHospitaller` | Bolter **20** | `[18, 24, 19]` | idem | `[386, 392, 324]` | mord, bit-exact |
| `necroSpyder` | Particle **35** | `[12, 14, 10, 14, 12]` | idem | `[414, 386, 402, 426, 494]` | **cas limite du `<=`** — le natif applique à 35 = 35 |
| `darkaTerminator` | Power **40** | `[989, 959, 855]` | idem | idem | gate FERMÉ, inerte |

Canal interne mesuré : `pierce + mods.extra_pierce == 1` dans les deux régimes qui mordent.

`Pyreblaster` — porteur `templNpc3InitiatePyreblaster:45` tire sur `orksNob`, `darkaAsmodai` placé
sur la tuile dérivée par `get_tiles_behind_filled` :

| observable | live | port AVEC | port SANS |
|---|---|---|---|
| attaque normale du porteur (cible) | `[1197, 3696, 2733]` | idem | idem |
| coups du passif (unité derrière) | `695 + 672 + 710 = 2077` | **2077** | **0** |
| tuiles passées en `Fire` | `{23, 24}` | `{23, 24}` | `{23}` |

L'attribution vient des **tags** d'événement : les coups du passif portent `Attacker_Id` = le porteur
et **aucun** `Active_Ability_Type` ; le DoT de tuile porte `Effect_Type: 5` et `Attacker_Id` = l'id de
TUILE.

⚠ **Un choix de témoin a d'abord faussé la mesure** : avec `astraBullgryn` derrière (trait
`BigTarget`, « adjacent friendly units receive -1 hit from ranged attacks »), le PORT faisait 2 coups
là où le NATIF en faisait 3 — le flux `state.rng` divergeait donc **avant** le passif, et l'écart
mesuré ensuite n'accusait pas le passif. Résidu `#1052-r3`.

## 4. Résidus

* **`#1052-r1`** — la branche NON-ALIGNÉE de `BattleQuery$$GetTilesBehindFilled` (deux tuiles via
  `IdunBattle.Core.Services.MovementUtil$$RoundDirection`) n'est pas portée : le facteur `by` du
  `Lerp` passe par XMM et le nudge est un champ statique écrit par un `.cctor` — ni l'un ni l'autre
  n'est lisible dans le pseudo-C. Le mirror rend `[]` : dégradation **restrictive et dite**.
  **Inatteignable à distance 1** (deux hexes adjacents partagent toujours une composante cube).
* **`#1052-r2`** — le natif applique le tick de DoT de la tuile `Fire` **immédiatement à la pose**
  (mesuré : 336 sur la cible, 678 sur l'unité derrière, `Effect_Type: 5`, `Attacker_Id` = la tuile).
  Le port ne le fait qu'au turn-start. **PRÉ-EXISTANT** : il manque aussi dans le régime SANS
  Pyreblaster, où la tuile de la cible brûle par le trait `OnFire` de l'arme.
* **`#1052-r3`** — le malus de coups de `BigTarget` : le port l'applique géométriquement, le natif
  le porte par un effet posé à l'init/turn-start. Après un déplacement piloté, les deux divergent.
