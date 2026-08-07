# #491 — `1069 SeekerMissileFrequencyLock` : le cast NE FRAPPE PAS, l'audit disait `DAMAGE`

Build `rnca9r7q6c`. Porteur lineup : `tauMarksman` (Sho'syl), pool rank 17. 4 porteurs npc
(`tauBossMarksman`, `tauBossMarksmanInc`, `tauBossMarksmanLHE`, `tauNpcMarksman`).

## Le contre-résultat

`IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$ExecuteBehaviour`
ne porte **aucun** nœud d'attaque. Mirror 1:1 :

```
turns = Sum( TurnsFromRounds(1), Direct(1) )   == DSLFactory$$TurnsUntilEndOfCurrentPlayersNextTurn
AActiveAbility.Execute(
      AddEffect(     0x462 = 1122 Markerlight,       AbilityStateReference,
                     source=Caster@DSLSelectors+0x48, targets=Target@+0x60, turns )
    & AddBondEffect( 0x463 = 1123 SeekerMissileFrequencyLock_Target, CreateSnapshot(abilityState),
                     source=Caster@+0x48, targets=Target@+0x60, bonded=Caster@+0x48, options=ZERO )
    & AddBondEffect( 0x470 = 1136 SeekerMissileFrequencyLock_Aiming, CreateSnapshot(abilityState),
                     source=Caster@+0x48, targets=Caster@+0x48, bonded=Target@+0x60, options=ZERO ),
    entities )
```

Le `DAMAGE(HeavyRound)` de `combat-ability-coverage.md` est le profil du **kit**
(`constants: range=5, nrOfHits=1, damageProfile=HeavyRound` + `minDmg`/`maxDmg`[level]) : il
appartient à la **phase 2**,
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SeekerMissileFrequencyLock_AttackAbility$$CreateBehaviour`
(`TriggeredAbilityType.SeekerMissileFrequencyLock_Attack` = 1127, rendu par
`IdunBattle.Entities.Effects.Loki.SeekerMissileFrequencyLockTargetEffect$$GetTriggeredAbilityType`).
Même patron 2-phases que `HeavyRailRifle` (1160).

**Mesuré live** : le cast ne retire aucun HP, alors que la prédiction native annonçait
`[8818-12049]` pour ce même cast. Prédire ≠ exécuter, et la prédiction a raison *à terme* — le
missile part au tour suivant.

## Les deux bonds sont INVERSES

Les deux `AddBondEffect` passent les **mêmes** deux sélecteurs dans l'ordre opposé — lu au
décompilé, **confirmé par la cascade native** :

| effet | posé sur | bondé à | durée |
|---|---|---|---|
| 1123 `_Target` (`APendingAttackEffect`) | la CIBLE | le CASTER | défaut (`remaining 0`) |
| 1136 `_Aiming` (`BaseEffect`) | le CASTER | la CIBLE | défaut (`remaining 0`) |
| 1122 `Markerlight` | la CIBLE | — | `TurnsUntilEndOfCurrentPlayersNextTurn` (= 3 mesuré) |

C'est le seul étage que l'empreinte d'effets **ne peut pas voir** : `decisionView.effects` ne
publie pas le bond. Seule la cascade du cast le porte.

`SeekerMissileFrequencyLock_AimingEffect$$CreateHandleTriggerAbilitiesInternal` retire l'effet sur
`On(0xc = EventTriggerType.UnitActiveAbility) & TriggeringAbilityIs(<self>) &
AreEqual(Caster@+0x48, BondedEntityFromEffect(Effect@+0x38))` — un nouveau cast de Sho'syl annule
le verrouillage précédent.

## Le piège d'enum, sur le chemin

`GetTriggeredAbilityType` rend `0x467 = 1127`. C'est un **`TriggeredAbilityType`** ; l'`EffectType`
de même ordinal existe et vaut `AnnihilatorBeam_PendingAttack` — une autre ability. Qualifié par
**nom**, jamais par ordinal.

## Masque de ciblage — forme PRESET STATIQUE COPIÉ

`$$.ctor` n'appelle **aucun** `IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les
0x40 octets du champ statique `TargetingOptions statics+0x180`, puis
`AActiveAbility..ctor(this, &opts, 0)`.

- masque effectif = `IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28`
  (`*(statics+0x1a8)`) = **0x4002** = `TargetMatchesDynamicRule | TargetIsEnemy`, 0 bit résiduel ;
- `TargetingRange` ← `TargetingRange statics+0x18` = `RANGE_FROM_CONFIG` → `constants.range` = **5**
  (l'arme de `tauMarksman` porte 3 : c'est l'ability qui étend) ;
- `forceMeleeTarget` = `*(statics+0x1a0)` = **1** = `RangedBool.False` ;
- `AbilityAttackType` = **0** `DirectTargetAttack` — littéral transcrit tel quel, comme `Drachnyen`
  (1029) : le ctor dit 0 même quand le behaviour n'attaque pas.

⚠ **La voisine ment** : `HellfyreMissileRack` (1088) a le même masque 0x4002 et le même
`RANGE_FROM_CONFIG`, mais son preset `+0x140` écrit `forceMeleeTarget = 0` (`RangedBool.True`).

La valeur **migre** de `TARGETING_OPTIONS_UNPORTED` vers la classe (contrat de disjonction, garde
`tests/engine/runner/test_targeting_options_sources.py`). `TargetMatchesDynamicRule` reste sans
effet : la classe native n'a que **deux** corps (`$$.ctor`, `$$ExecuteBehaviour`), donc pas de
`GetDynamicInvalidTargetReason` → défaut 0.

## Validation

`probe_491_seeker_missile_frequency_lock.py` (mesure) et
`tests/engine/runner/test_seeker_missile_frequency_lock_live.py` (garde) — **une seule
implémentation**, le test importe le probe. Runner MC1_67, positions **forcées** (`--place` /
`--a-place`) : la géométrie de spawn met Sho'syl hors de sa portée 5.

7 étages, tous verts : `ported=True` · empreinte port == natif
(`{caster:{1136:0}, cible:{1122:3, 1123:0}}`) · bonds inversés côté **port ET natif** · aucun dégât
des deux côtés · `Markerlight` mord (prédiction native `6008→6910`, `9014→10366` = +15 %) · gate
`TargetIsEnemy` refuse allié et soi (0x4000) des deux côtés.

**Deux précautions de mesure**, écrites parce qu'elles ont failli produire un faux verdict :

1. l'étage Markerlight **ne reconstitue pas l'arrondi natif**. Premier jet : « ÉCART » sur
   `6008 → 6910` (attendu 6909). `dmgMin` est *déjà* arrondi — la valeur interne vit dans
   `[6007.5, 6008.5)` et son image contient 6909 comme 6910. Le critère est l'**encadrement**, plus
   un **témoin non-nul** (un encadrement passe trivialement à bonus nul).
2. il compare la **même tuile** avant/après (indexation par `(col,row)`), jamais `ranked[0]` : la
   meilleure tuile peut changer, et l'écart de *géométrie* serait attribué à l'effet.

Le canal des bonds a dû être retrouvé : `act.events` est une liste **plate** dont `tags` est une
**chaîne JSON**, et dont `Effect_Id` est un id d'**instance** (108/109/110), pas un `EffectType`.
Résolution instance → nom (`group.source`) → `EffectType`. Une cascade muette rend `NON MESURE`,
jamais un vert.

## Résidus

- **#491-r1 — FERMÉ par #513** (`case-513-attaque-differee-pending-attack.md`). Le foyer
  `IdunBattle.Entities.Effects.APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` est porté
  pour les **20** dérivées, le vecteur `On(0x15 = TurnStart_DelayedAttacks)` est câblé, et le missile
  part au tour du CASTER pour **3424 = 3424** (4 tirages des deux côtés). L'énoncé d'origine, conservé
  pour la traçabilité de la lecture :
  ~~`SeekerMissileFrequencyLock_AttackAbility$$CreateBehaviour`~~
  (1127) : `AttackWithAbilityDamage(Caster, Target, RandomAmount(ConfigVar(0xc minDmg),
  ConfigVar(0xd maxDmg)), GetDamageProfileOrDefault(0x13), GetNumberConstant(0x2f nrOfHits))
  & RemoveEffect(Caster, 1136 _Aiming)`, l'état d'ability étant repris via
  `AbilityStateFromEffect(EffectFromOwner(Target, 0x463))`. Le déclencheur est
  `APendingAttackEffect` (dont `SeekerMissileFrequencyLockTargetEffect` hérite) — c'est **lui** le
  point d'entrée à RE. Tant qu'elle manque, le missile ne part jamais offline : le port pose le
  verrouillage et rien n'en sort. Même résidu que `HeavyRailRifle` (1160).
- **#491-r2 — `audit_combat_ability_coverage.py` ne peut pas voir qu'un cast ne frappe pas.** Sa
  colonne `categorie` dérive du **gameconfig** (`damageProfile`), pas de l'`ExecuteBehaviour` :
  1069 y reste `DAMAGE(HeavyRound)` *après* le port. C'est l'angle mort qui a produit le brief de
  cette tranche, et il vaut pour tout patron 2-phases (1160 `HeavyRailRifle`, 1142
  `MalleusRocketLauncher`…). Piste : marquer les abilities dont le behaviour ne porte aucun nœud
  d'attaque — l'information est déjà dans le registre, pas dans le kit.

## Non couvert

Le régime **npc** (`dmg_reduction` au kit des quatre porteurs npc) n'est pas confronté : le porteur
lineup n'a aucune mécanique de ce type, et rien dans l'`ExecuteBehaviour` ne les distingue. La
mesure porte sur un seul board (MC1_67) et un seul couple caster/cible.
