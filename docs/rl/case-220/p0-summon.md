> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

## §2 P0-SUMMON — 1016, 1021, 1040, 1077, 1121, 1166

**Substrat vérifié présent** : `SpawnUnitOperation` (variantes placement), `SpawnSummon`/
`SpawnReplica`/`SpawnTutelaryHorror`, `perform_ai_attack_from_current_position`,
`DisplaceUnitOperation` (push, `displace.py`), sélecteurs tuiles (AdjacentTiles/CanAddUnit/
SurroundingTiles/First/Cache). **Absents** : `ChainBehaviour`, amount-nodes `RandomAmount`/
`Divide`/`Get`, `SortTilesByUtilityForSummon`, sous-système **Overwatch**, `PerformAIAbility`
(=PerformAIAction P1). Décision portée confirmée (playbooks noncomparable présents).

```
[1166 AberrantHypermorph | genesBiophagus]  — le plus simple
VAs : ExecuteBehaviour @1811b0550. Pas de triggered.
Arbre : Spawn(genesSmnAberrant, hex libre adjacent caster, WithStatsFromConfig(AbilityLevelAmount),
        onAppearance = PerformAIAttackFromCurrentPosition). Count=1.
Template : SpawnTutelaryHorror, placement auto-adjacent-caster (variante SpawnUnitOperation).
Prérequis MANQUANTS : AUCUN. Verdict : [opus] direct, 1 tranche.
Risques : cannot-move-this-turn du summon probablement no-op runner ; placement à confirmer.
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

**Synthèse** : [opus] direct = 1166 ; [opus]+prérequis = 1016, 1040, 1021 ; à trous = 1077 (volet
Overwatch = sous-système dédié) ; **[fable]** = 1121. Prérequis transverses NOUVEAUX identifiés :
amount-nodes DSL (RandomAmount/Divide/Get), ChainBehaviour, PickRandomly-by-count, sous-système
**Overwatch**, et confirmation de la dépendance **PerformAIAction (P1)**.
