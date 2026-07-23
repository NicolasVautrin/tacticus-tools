> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

## §3 P0-DAMAGE — 1000, 1038, 1090, 1092, 1122, 1129, 1202

Les 7 ont déjà leur playbook (`playbook/noncomparable/*.py`) — décision portée ; le trou est la
face COMBAT (aucune dans `ABILITY_CLASSES`, `runner/abilities/handler.py:24`).

**Substrat vérifié présent** : `AttackWithAttackDamage` (multi/pick_n/amount/damage_override,
hits_key), `AddEffect`, `MoveUnit`, `Foreach`, `op_and`/`op_add`, `If`/`Not`/`IsAlive`/
`IsSurrounding`, sélecteurs AdjacentEnemies/SurroundingEnemies/SurroundingFriends/UnitsWithTrait/
Units/First/Union, `get_movable_positions`, `_pick_randomly_n`. **Effets extra-hits DÉJÀ portés**
(canal #179, `entities/effects/loki/hits.py`) : CordClaw 0x4e2 et FoulInfusion 0x432 — la DATA
existe, seule la POSE (`AddEffect`) + l'attaque manquent.

```
[1000 GauntletsOfUltramar | ultraCalgar]
VAs : ExecuteBehaviour @1811e1c80 ; GetAdjacentTargetsSelector @1811e2010 ; GetSurroundingTargetsSelector @1811e20d0
Arbre : op_and( Attack(adjSel, nrOfHits 0x2f + nrOfHits_2 0x32, prof, MinMax),
                Attack(surrSel, nrOfHits 0x2f, prof, MinMax) )   # 2 bandes de portée
        adjSel = Unique(Enemies(AdjacentTiles(caster))) ; surrSel = Unobscured(Surrounding(r=2) - adjSel)
Prérequis MANQUANTS : (a) sélecteur set-diff (Surrounding - Adjacent) ~trivial ; (b) hits = somme
   de 2 constantes en mode bornes (petit ajout param).
Verdict : [opus] direct, 1 tranche. Risques : bande extérieure (dist exactement 2) vs anneau<=2.
```
```
[1038 FoulInfusion | deathPutrifier]
VAs : ExecuteBehaviour @1811dffb0 ; effet 0x432 CreateAdditionalHits @180f4a340 (DÉJÀ porté)
Arbre : op_add( AddEffect(0x432, WithTrait(SurroundingFriends(ContagionsOfNurgleRange, r=3), 0x7ea)+self,
                          TurnsFromRounds(2)),
                UseNormalAttack( PickRandomly(Attackable(AdjacentEnemies(caster,1)), 1) ) )
Prérequis MANQUANTS : feuille `UseNormalAttack` (thin, ~AttackDamageOperation.execute) + chaîne
   sélecteur aura amie.
Verdict : [opus]+prérequis, 1 tranche.
Risques : effet posé sur AMIS → validable seulement multi-step (un ami Chaos attaque melee ensuite).
```
```
[1090 GrapnelLauncher | spaceHound]
VAs : ExecuteBehaviour @1811e29c0
Arbre : op_add( PullUnitOneTile(target, dist=NumberConst 0x5b),
                op_add( If(!IsDead(target), Attack(target, 0x2f)),
                        If(IsDead & AreEqual..., KillDeadUnits + RemoveUnitFromItsTiles
                           + MoveUnit(First(tiles)) / MoveUnit(PickRandomly(CanAddUnit(AdjacentTiles)))) ) )
Prérequis MANQUANTS : PullUnitOneTile, KillDeadUnits, RemoveUnitFromItsTiles, IsCanAddUnit,
   AmountIsGreaterThanZero, sélecteurs de tuiles AdjacentTiles/CanAddUnit — AUCUN grep hit.
Verdict : **[fable]** (>=6 primitives mouvement/tuile nouvelles + If imbriqués sur IsDead/AreEqual ;
   validation positionnelle délicate). Découpe : 2 tranches.
Risques : ordre pull-avant-attaque, cible morte (retrait de tuile), placement random adjacent (RNG).
```
```
[1092 DarkTalonStrike | darkaAzrael]
VAs : ExecuteBehaviour @1811d1440 ; GetTilesInBestLine @1811d16f0 ; GetTilesInLine @1811d18c0 ;
      GetAttackTargets @1811d1680 ; DamageUnit @1811d1260 ; AttackUnit @1811d1180
Arbre : Foreach( Enemies(Units(GetTilesInBestLine)), enemy -> DamageUnit(enemy) )   # BEAM en ligne
Prérequis MANQUANTS : géométrie ligne hex (GetTilesInLine) + sélection « best line » (heuristique) +
   feuille DamageUnit/AttackUnit. Aucun helper ligne dans engine/.
Verdict : [opus]+prérequis, borderline [fable] — RE `GetTilesInBestLine @1811d16f0` AVANT de figer.
Découpe : 1-2 tranches. Risques : heuristique best-line = point de divergence.
```
```
[1122 CordClaw | admecRuststalker]
VAs : ExecuteBehaviour @1811ccbf0 ; effet 0x4e2 CreateAdditionalHits @180f3a900 (DÉJÀ porté, hits.py:51)
Arbre : op_add( Attack(target, hits=GetHits, GetDamageProfile, MinMax),
                AddEffect(0x4e2, caster, TurnsFromRounds(2)) )   # jumeau CrushingClaws
Prérequis MANQUANTS : AUCUN (confirmer GetHits = NumberConst 0x2f ; partagé avec ArmoriumCherub 1014).
Verdict : [opus] direct, 1 tranche. Risques : source exacte de GetHits (gshared mislabel) ;
   self-buff → validable au tour suivant du caster.
```
```
[1129 BloodyFury | worldTerminator]
VAs : ExecuteBehaviour @1811bbbc0 ; GetNumTotalHits @1811bc270 ; GetNumBaseHits @1811bc100 ;
      GetNumExtraHits @1811bc140 ; GetOtherTargets @1811bc3f0
Arbre : ChainLeftOverHitsAttackDamage( self, target, MinMax, profile, numTotalHits,
            selector=SortTargetsByDamagePredictionSelector(Damageable(AdjacentEnemies(self) - target)) )
        numTotalHits = nrOfHits 0x2f + Min( extraHit 0x2b * TotalTimesAttacked(self),
                                            maxHits 0x48 - nrOfHits 0x2f )   # monte avec les attaques, capé
Prérequis MANQUANTS : primitive ChainLeftOverHitsAttackDamage (coups-restants après kill chaînent
   sur voisins triés par dégât prédit) ; SortTargetsByDamagePredictionSelector ; formule GetNumTotalHits.
Verdict : **[fable]** (chaîne nouvelle, RNG per-coup, tri par prédiction, kill intra-attaque).
Découpe : 2 tranches. Risques : ordre exact des coups-restants, seuil de kill par coup.
```
```
[1202 VigilanceEternal | custoKyrus]
VAs : ExecuteBehaviour @18122a580 ; GetPossibleMovementTiles @18122ae10
Arbre : op_and( If(Not(IsAdjacent(caster,target,3)),
                   MoveUnit(caster, First(SortTilesByUtility(GetPossibleMovementTiles, 0x20)))),
                If(IsAlive(caster) & IsAlive(target), Attack(target, 0x2f, GetDamageProfile, MinMax)) )
        GetPossibleMovementTiles = TilesUnitCanMoveToChargeTarget(caster, tile, target, range 0x16, 1)
Template : HeroicFusillade (`genestealer.py:329`) EXACT, MOINS splash/crit.
Prérequis MANQUANTS : AUCUN — collapse charge-tile comme HF._move_dest_tile.
Verdict : [opus] direct, 1 tranche. Risques : TilesUnitCanMoveToChargeTarget vs MovableTilesInRange
   (charge = s'arrête adjacent) ; SortTilesByUtility(0x20) collapse → plus proche (proxy, déjà fait HF).
```

**Synthèse** : [opus] direct = CordClaw, VigilanceEternal, GauntletsOfUltramar ; [opus]+prérequis =
FoulInfusion ; borderline = DarkTalonStrike (RE best-line d'abord) ; **[fable]** = GrapnelLauncher,
BloodyFury. Hypothèses restantes (1 décompile ciblé au port) : source GetHits (CordClaw),
heuristique best-line (DarkTalon).
