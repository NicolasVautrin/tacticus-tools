> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

## §4 P0-EFFECT + P0-WALK restants — 1050, 1081, 1183, 1153, 1191

**Constat transversal** (grep-vérifié) : les faces DÉCISION des 5 sont DÉJÀ portées — playbooks NC
(`playbook/noncomparable/__init__.py:54-131`) pour HolyDuel/Vexilla/FightingRetreat/HammerOfWrath,
et **MartialInspiration via `prediction.py:925 _martial_inspiration_inputs`** (pattern
MakeDamagePredictions, pas NC — le tag `[--]` de la roadmap était FAUX sur la moitié décision).
Le gap réel = la face COMBAT (aucune dans `ABILITY_CLASSES`). Feuilles présentes : AddBondEffect,
AttackWithAttackDamage/AbilityDamage, AddEffect, MoveUnit, UseActiveAbility, Foreach/If/AtomicGroup,
TurnsFromRounds, FinishUnitTurnOperation (`turnflow.py:45`).

```
[1050 HolyDuel | templChampion]
VAs : ExecuteBehaviour @1811e97a0 ; TauntEffect @180f4fef0/@180f4fbe0 ; ExtraDmgEffect @180f4fb10/
      @180f4f960 ; DmgReductionEffect @180f4f890/@180f4f6c0 ; playbook @181144b00 (DONE)
Arbre : op_and( AddBondEffect(0x443 Duel, caster, target),
                UseActiveAbility(caster, target, UnitNormalAttackType(caster)) )
        — le bond porte Taunt 1091 no-expiry + ExtraDmg 1092 (+582) + DmgReduction 1093 (-364).
Prérequis MANQUANTS : les 3 classes d'effet du bond (enum OK effect_type.py:228-230, AUCUNE classe ;
   seul TauntedEffect générique 0x1b existe). Clones ForAddition + taunt-bond mutuel sans expiration.
Verdict : [opus]+prérequis (3 effet-classes), 1 tranche.
Risques : taunt MUTUEL no-expiry != Taunted 0x1b standard ; gate « while Taunted by him » = condition de bond.
```
```
[1081 FightingRetreat | tauDarkstrider]
VAs : ExecuteBehaviour @1811ddf90 ; DmgReduction @180f49580 (PORTÉ 1157) ; HitReduction @180f495d0
      (PORTÉ 1158) ; playbook @181131ff0 (DONE)
Arbre : AddEffect(0x485+0x486 sur ennemis adjacents, TurnsUntilEndOfCurrentPlayersNextTurn)
        + Foreach(adjE, AddEffect(0x462 Markerlight))
        + Foreach(adjF+caster, If(HasTrait 0x424 RangedSpecialist, ActivateEffect(EffectFromOwner(0x5eb))))
        + If(count(adjE)>0, ResetTurn(caster,1), FinishTurn(caster))   [PAS d'attaque directe]
Prérequis MANQUANTS : selector NonSteppableOrObjectUnits ; feuilles ResetTurn (NEUVE) + FinishTurn ;
   durée TurnsUntilEndOfCurrentPlayersNextTurn ; feuille ActivateEffect ; effet 0x5eb.
Verdict : **[fable]** — la ré-entrance de tour (ResetTurn + « peut rebouger ») touche le scheduler ;
   ~6 primitives neuves sans template. Découpe : 2 tranches.
Risques : ResetTurn ré-arme le tour → risque boucle/double-jeu ; interaction skipEndTurn à mirrorer.
```
```
[1183 VexillaMagnifica | custoVexilusPraetor]
VAs : ExecuteBehaviour @18122a020 ; DmgReductionEffect @180f76650 (PORTÉ 0x567/1383,
      damage_reduction.py:88) ; playbook @18117f6f0 (DONE)
Arbre : ExecuteAtomic( Attack(target) & Attack(sec) & AddEffect(0x48a Stun, target+sec)
        & AddEffect(0x567 self DmgReduc, TurnsFromRounds(0x45)) )
        sec = Cache(First(SortUnitsByDamageUtility(NormalUnits(AdjacentEnemies(caster,1)) - target)))
Prérequis MANQUANTS : selectors SortUnitsByDamageUtility + NormalUnits (2 seulement).
Verdict : [opus]+prérequis, 1 tranche (template splash.py bon fit ; Stun DÉJÀ porté status.py:195).
Risques : SortUnitsByDamageUtility = tri par dégât prédit (fidélité ciblage du secondaire).
```
```
[1153 HammerOfWrath | bloodIntercessor]  *** P0-WALK (garde 31337) ***
VAs : ExecuteBehaviour @1811e5a40 ; GetAdjacentTargets @1811e6150 ; GetDamage @1811e62d0 ;
      GetDoubleCondition @1811e63e0 ; ConditionalDamageEffect @180f4ce10 (HealthPctIsBelowOrEqual 50) ;
      playbook @181141680 (DONE)
Arbre : dbl = HasEffect(0x534, actif si caster HP<=50%) ; mainDmg = ConditionalAmount(dbl, MinMax*2, MinMax)
        Attack(target, mainDmg 2x Power) + Attack(Enemies(AdjacentUnits(target,1)), splash 1x Physical)
        charge = First(SortTilesByUtility(Filter(CanAddUnit(AdjacentTiles(target)),
                 !AmountIsGreater(MinDistance(casterTile, tile), range 0x16)), Tile7))
        + MoveUnit(caster, charge) + AddEffect(0x416 Infiltrate, self) + If(IsAlive, AtomicGroup(attaques))
Prérequis MANQUANTS : formules ConditionalAmount + MinDistance ; tile-pick SortTilesByUtility(Tile7)
   à collapser (genestealer.py:312 le plus proche) ; effet-marqueur Infiltrate 1046.
Verdict : [opus]+prérequis, escalade [fable] si Tile7 ne collapse pas proprement (la tuile de charge
   fausse l'attaque). Découpe : 2 tranches (double-dmg+attaques ; charge+Infiltrate+gate).
Risques : double-condition = HP du CASTER (pas la cible) ; GetHits = gshared mislabels (lire la structure).
```
```
[1191 MartialInspiration | custoBladeChampion]  *** P0-WALK ***
VAs : ExecuteBehaviour @1811f2b30 ; ExtraDamageEffect @180f588e0/@180f58600/GetBuffPct @180f58880 ;
      décision DÉJÀ portée (prediction.py:925, validée #106 walk 31337 s16)
Arbre : op_and( AddEffect(0x580 self ExtraDamage, Direct(1)), Attack(target, MinMax, profil, hits) )
Effet 0x580 : ForPercentIncrease( OwnerIsCaster & (CurrentAbilityIs(1191) | CurrentAbilityIs(1319
   LegacyOfCombat)), Multiply(ConfigVar(10)=+33%, TotalTurnsWithAttacksMade) )
Prérequis MANQUANTS : classe effet MartialInspiration_ExtraDamage (enum only) ; trigger
   CurrentAbilityIs ; compteur TotalTurnsWithAttacksMade (+0x30) — DISTINCT de TotalAttacksMade
   (+0x20, formulas.py:163) que la PRÉDICTION utilise (divergence notée prediction.py:932).
Verdict : [opus]+prérequis, 1 tranche — le plus simple du groupe (template ArmoriumCherub).
Risques : ne PAS réutiliser total_attacks_made (+0x20) pour le compteur +0x30 ; le buff couvre 1191 ET 1319.
```

**Synthèse** : priorité walk = MartialInspiration (le plus simple) puis HammerOfWrath (tile-pick =
point sensible) ; VexillaMagnifica et HolyDuel = [opus]+prérequis 1 tranche ; **FightingRetreat =
seul [fable]** (ré-entrance de tour). Points validator : tile-pick Tile7 (HoW) et compteur +0x30 (MI).
