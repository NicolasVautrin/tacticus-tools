> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

## §2 P0-SUMMON — 1016, 1021, 1040, 1077, 1121, 1166

**Substrat vérifié présent** : `SpawnUnitOperation` (variantes placement), `SpawnSummon`/
`SpawnReplica`/`SpawnTutelaryHorror`, `perform_ai_attack_from_current_position`,
`DisplaceUnitOperation` (push, `displace.py`), sélecteurs tuiles (AdjacentTiles/CanAddUnit/
SurroundingTiles/First/Cache). **Absents** : `ChainBehaviour`, amount-nodes `RandomAmount`/
`Divide`/`Get`, `SortTilesByUtilityForSummon`, sous-système **Overwatch**, `PerformAIAbility`
(=PerformAIAction P1). Décision portée confirmée (playbooks noncomparable présents).

```
[1166 AberrantHypermorph | genesBiophagus]  — le plus simple  [PORTE + valide live]
VAs : ExecuteBehaviour @1811b0550 ; ctor @1811b0730.
Arbre (mirror 1:1 @1811b0550, CONFIRME decompile) :
  Execute( Spawn(caster@0x160, Target@0x178=TUILE, GetStringConstant(config,0)="genesSmnAberrant",
                 WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, AbilityType(1166)))
                   .onAppearance(+0x18) = PerformAIAttackFromCurrentPosition(Target@0x178)) ). Count=1.
UN SEUL noeud Spawn (plain AActiveAbility.Execute, PAS ExecuteAtomic, PAS d'AddEffect, PAS d'op_BitwiseAnd).
DISTINCT de MasterOfTheTutelaries @1811f30c0 (op_BitwiseAnd(AddEffect(1197), Spawn) + onAppearance
Spawned@0x180) : ici PAS d'effet-marqueur, et l'onAppearance passe Target@0x178 (le MEME selecteur que la
tuile de spawn) au lieu de Spawned@0x180 -> les DEUX resolvent au MEME summon (Target@0x178 apres le spawn =
l'unite sur la tuile-cible = le summon fraichement pose ; tuile libre AVANT le spawn par la legalite du cast).
Placement = cast TILE-target (ctor @1811b0730 = TargetingOptions(0, statsFromClass, 1, 0x1040) IDENTIQUE a
MasterOfTheTutelaries) : hex libre adjacent au caster choisi par le targeting (abilityTargets kind="tile" ;
CONFIRME live : decisionView now[3] = tuiles libres adjacentes). PAS un selecteur auto interne -> le port
porte le tile_id resolu par la classe.
Prérequis MANQUANTS : AUCUN (confirme).
Port : `loki/summon.py` -> feuille `SpawnAberrant` + `aberrant_hypermorph_tree` + classe
  `AberrantHypermorphAbility` (mirror de SpawnTutelaryHorror SANS AddEffect) ; registre `handler.py` 1166.
Validation (test_aberrant_hypermorph_live.py, board MC1_67, genesBiophagus lvl50 mult180 vs ultraTitus) :
  - SPAWN live-EXACT : summon team=caster(1), hpMax=7477 == summonHp[50]x180 (port) ; summonDmg=3888,
    summonArmor=1397 confirmes ; sur la tuile ciblee (live squadId 95, teamId 1, (0,0)).
  - Attaque a l'apparition : port total=2013 (cible=ennemi adjacent 77) ; live enemy 9537->6344/7099
    (delta ~2400-3200). Ecart de degat EXACT = passive Hypermorph du summon (buff/transform attaque pose au
    spawn, UnitStats_Attack_Modification lvl50) NON portee -> HORS ExecuteBehaviour de 1166
    (raffinement/gap connu, meme classe que l'effet 0x4a3 de ScarabHive). Attaque a lieu des DEUX cotes,
    bonne cible.
  - Flags de tour : defauts base (SetsEndTurnFlags/SetsActiveAbilityUsedFlag=True ; 1166 absent des
    inventaires) -> tour du caster termine (live : UnitStats_TurnFinished=1 + ActiveAbility used) ; VERIFIE.
Risque leve : cannot-move-this-turn du summon (TriggerSpawnedUnitBehaviours @180fd57b0, flag 0x23) = NO-OP
  runner (summon a agi a l'apparition, non rejoue ce tour). Placement CONFIRME (cast tile-target hex libre).
Verdict : [opus] direct -> PORTE + valide live (spawn EXACT ; attaque structurelle + gap Hypermorph flagge).
```
```
[1016 SendInTheNextWave | astraYarrick]
VAs : ExecuteBehaviour @181206490 ; GetNumSummons @181206a70 ; GetSpawnTilesSelector @181206cc0 ;
      GetSpawnedUnitRange @181206ed0
Arbre : Spawn(astraSmnGuardsman, onAppearance=UseNormalAttackIfAble(target)).
        count = Min(2 + Count(Attackable(Friends(AllDeadOrResurrectedUnits))), maxSummons=5).
        Placement = PickRandomly(AttackTilesForTarget(CanAddUnit(SurroundingTiles(target, r=2))))
        prioritaire + fallback PickRandomly(SurroundingTiles libres).
Prérequis MANQUANTS : (a) formule count dynamique (morts alliés) ; (b) placement range-2
   attack-priority (extension _free_tiles_adjacent → _free_tiles_within_range + priorité AttackTiles).
Verdict : [opus]+prérequis, 2 tranches.
Risques : scénario de validation à crafter avec pertes amies ; placement RNG non calé exact.
```
```
[1077 EarlyWarningOverride | tauCrisis]  — mixte spawn + overwatch
VAs : ExecuteBehaviour @1811d7310 ; effet ReactivateOverwatchEffect @180f40550 /
      GetOverwatchExtraDamage @180f40360 / LegitDeathReasons @180f403b0
Arbre : (a) Spawn(First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(self))), N=2),
        tauSmnDroneShield, onAppearance=PerformAIAttackFromCurrentPosition) op_Addition
        (b) via CreateSnapshot(caster) : 4x AddEffect(0x3f1=1009 Overwatch, 0x478, 0x479, 0x47d,
        TurnsFromRounds(1)) sur le caster = Overwatch réactivé +1892 dmg.
Prérequis MANQUANTS : sous-système OVERWATCH en combat (grep : commentaires only, damage.py:382 —
   blind spot connu) + sémantique effets 1009/1144/1145/1149 ; SortTilesByUtilityForSummon absent.
Verdict : [opus]+prérequis nommé (spawn) ; volet overwatch = tâche dédiée « sous-système Overwatch »
   (identifié, uncharted). Découpe : 2 tranches.
Risques : sans overwatch le combat reste partiellement no-op (drones OK, +1892 manquant) → agreement partiel.
```
```
[1040 Poxwalkers | deathBlightbringer]
VAs : ExecuteBehaviour @181208b80 ; range = ContagionsOfNurgle_ArmorReduction_Effect.CalculateRange
Arbre : tiles = CanAddUnit(SurroundingTiles(caster, 0, range)) ;
        n = Divide(RandomAmount(Count(tiles)*var0x3a, Count(tiles)*var0x3b), Get(100)) ;
        Spawn(PickRandomly(tiles, n), onAppearance=PerformAIAttackFromCurrentPosition).
Prérequis MANQUANTS : amount-nodes DSL RandomAmount/Divide/Get(const) comme nœuds de count ;
   PickRandomly(tiles, amount) piloté par count-node ; range depuis CalculateRange d'un effet Nurgle.
Verdict : [opus]+prérequis, 2 tranches (amount-nodes+range ; spawn+placement+attaque).
Risques : count RNG-exact (tirage natif) non trivial à confronter.
```
```
[1021 Incursion | blackPossession]
VAs : ExecuteBehaviour @1811e9fe0 ; GetNextSpawnTile @1811ea520 ; GetContinueTrigger @1811ea420
Arbre : ChainBehaviour(Null, Func(GetNextSpawnTile), Direct(maxSummons=6),
        Spawn(blackSmnBloodletter adjacent cible, onAppearance=UseNormalAttackIfAble(target))) —
        RÉPÈTE <=6 tant que target vivante + à portée + hex libre (GetContinueTrigger).
Prérequis MANQUANTS : combinateur ChainBehaviour (loop-with-reevaluated-condition) +
   Func(GetNextSpawnTile) + Direct(count).
Verdict : [opus]+prérequis, 2 tranches. Boucle bornée, conditions claires — pas DUR, le cœur =
   ré-évaluation par-itération (target morte → stop).
Risques : cible qui meurt en cours de chaîne → scénario de validation avec cible fragile.
```
```
[1121 ItItches | tyranParasite]  — le plus dur
VAs : ExecuteBehaviour @1811ebd40 ; GetTargetUnits @1811ec5e0 ; GetPushVector @1811ec550 ;
      GetTargetTiles @1811ec590
Arbre (multi-étage op_BitwiseAnd + ExecuteAtomic(0x2a) + Group(0x22)) :
        Suppress AddEffect(0x429) sur ennemis adjacents (cible+parasite) ;
        push 1 hex DisplaceUnitInAdjacentDirection(VectorFromAdjacentTo) ;
        Kill(DeadUnits, ForClearDeadUnits) (steppables écrasés) ;
        Reserve/RemoveReservation des hexes ;
        Foreach(hexes libérés, Spawn(tyranSmnRipperSwarm) + PerformAIAbility) ;
        ResetMovement(caster) (rejoue).
Prérequis MANQUANTS : PerformAIAbility (= P1 PerformAIAction) ; Reserve/RemoveReservation ;
   nœuds Kill/DeadUnits ; ResetMovement ; ordonnancement ExecuteAtomic/Group.
   DisplaceUnitOperation PRÉSENT (displace.py).
Verdict : **[fable]** — multi-étage atomique positionnel (push → hexes libérés → spawn),
   dépend de P1 PerformAIAction. Découpe : 3+ tranches.
Risques : ordre push/spawn strict.
```

**Synthèse** : [opus] direct = 1166 (**PORTE + valide live**, cf. bloc ci-dessus) ; [opus]+prérequis =
1016, 1040, 1021 ; à trous = 1077 (volet
Overwatch = sous-système dédié) ; **[fable]** = 1121. Prérequis transverses NOUVEAUX identifiés :
amount-nodes DSL (RandomAmount/Divide/Get), ChainBehaviour, PickRandomly-by-count, sous-système
**Overwatch**, et confirmation de la dépendance **PerformAIAction (P1)**.
