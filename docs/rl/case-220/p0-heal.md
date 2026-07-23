> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

## §1 P0-HEAL/REPAIR — 1002, 1037, 1039, 1082, 1117

**Substrat vérifié présent** (grep) : feuille Heal `runner/abilities/behaviours.py:751` +
`operations/heal.py` (caps #60/#203) ; sélecteurs `entities/selectors.py` (AdjacentUnits, Friends,
AdjacentFriends, Union=op_Addition, Sub=op_Subtraction, UnitsWithTrait/WithoutTrait,
Unique=SelectUniqueUnits) ; feuille `If` `entities/behaviours.py:77` ; `ResurrectUnitOperation`
`operations/resurrect.py:31` ; AddStatOverrideEffect + PercentageOfAttackCappedAtMax +
PerformAIAttackFromCurrentPosition (single-unit) dans `abilities/loki/quickening.py` ; RemoveEffect
`behaviours.py:710` ; repair de combat = réutilise `HealUnitOperation`
(`triggers/loki/living_metal.py:116`). Traits : 0x1a=Imperial, 0x7ea=Chaos.

```
[1002 CombatRestoratives | ultraApothecary]
VAs : ExecuteBehaviour @1811cc590, HealTargets @1811cca50, callback b__0 @1811e3e90
Arbre : AtomicGroup(Union(Friends(AdjacentUnits(self,1)), self))
        -> split UnitsWithTrait(0x1a Imperial) vs op_Subtraction (sans) via SelectUniqueUnits
        -> Heal(withImperial, GetVarForLevel 0x22=5456) & Heal(sans, 0x20=4365)
Prérequis MANQUANTS : AUCUN. Verdict : [opus] direct, 1 tranche.
Risques : split-trait = 2 feuilles Heal distinctes (pas 1 amount conditionnel) ; ordre d'emit.
```
```
[1037 RevitalizingMalignancy | deathRotbone]
VAs : ExecuteBehaviour @181200eb0, GetAllHealTargets @181201150 (+Chaos @181201230 / Regular @181201280)
Arbre : AllHealTargets = Healable(WithoutTrait(0x1a, Union(Friends(AdjacentUnits), self)))
        -> regular = WithoutTrait(0x7ea Chaos) heal var0x20=2546
        -> chaos   = WithTrait(0x7ea)          heal var0x20+var0x22 (CUMUL iVar14+iVar13)
Prérequis MANQUANTS : garde `Healable` côté mutation (HP<max & non-mechanical) — à porter comme
   garde de la feuille. Verdict : [opus] direct, 1 tranche.
Risques : le « +2546 Chaos » est une SOMME des 2 vars, pas un 2e var isolé — ne pas fitter.
```
```
[1039 RitesOfRestoration | adeptHospitaller]
VAs : ExecuteBehaviour @1812033c0, GetHealTargets @181203c80, GetPossibleResurrectTargets @181203d80,
      GetResurrectTargets @181203e20, GetResurrectTiles @181203f70
Arbre : Heal(Healable(Union(AdjacentFriends(self,1), self)), ConfigVar 0x20=2183)
        & Resurrect( PickRandomly(WithTrait 0x10 heroes, NumberConst 0x43=1)
                     + PickRandomly(WithTrait 2 summons, NumberConst 0x10=2),
                     tiles=CanAddUnit(AdjacentTiles(self)), hp=ConfigVar 0x1d=1819,
                     AbilityType 0x40f, cannot-act-this-turn )
        Possible = UnitsAffectedByHealType(WithTrait(0x1a, Friends(AllDeadUnits))) [non-Mechanical]
Prérequis MANQUANTS : (a) sélecteur `AllDeadUnits` ; (b) feuille DSL `Resurrect` au-dessus de
   l'opération existante ; (c) garde `UnitsAffectedByHealType`.
Verdict : [opus]+prérequis nommés, 2 tranches (heal ; resurrect+placement+no-act).
Risques : RNG double PickRandomly (ordre/coût tirage), placement hexes adjacents, flag no-act.
```
```
[1082 InspiredToGreatness | tauAunShi]
VAs : ExecuteBehaviour @1811eac00, RepairOrHeal @1811eb050, OverrideLevelEffect ctor @180f529b0
Arbre : primary = UnitsThatCanHaveActiveAbilityReset(target) ; others = target - primary
        AddStatOverrideEffect(primary, stat 0x49c, mode 0x12,
            Min(AbilityLevelAmount(0x43a), PrimaryActiveAbilityLevelAmount))
        & RepairOrHeal(primary, var0x20=1091) & RepairOrHeal(others, var0x22=4365)
        & ResetActiveAbility(primary)   [RepairOrHeal = If(IsRepairable) Repair else Heal]
Prérequis MANQUANTS : (a) **ResetActiveAbility** (réactivation d'active — ABSENTE du runner) ;
   (b) sélecteur UnitsThatCanHaveActiveAbilityReset ; (c) formule Min de niveaux ;
   (d) prédicat IsRepairable ; (e) effet InspiredToGreatness_OverrideLevelEffect. 5 primitives neuves.
Verdict : **[fable]** — réactivation d'active + override de niveau touchent l'état d'activation/tour.
Découpe : 3 tranches (repair/heal ; effet override-level ; ResetActiveAbility + sélecteur).
Risques : re-cast dans le même tour (boucle action), gate « hasn't used ability yet », Min de niveaux.
```
```
[1117 DefendTheDivineWork | admecManipulus | REPAIR]
VAs : ExecuteBehaviour @1811d30b0, GetAdjacentFriends @1811d33a0, GalvanicField.CreateAttackBehavior @1811ffb30
Arbre : (1) ExecuteAtomic Repair(Union(Friends(AdjacentUnits(self,1)), self), var0x24=4365, ForRepair)
        (2) GalvanicField.CreateAttackBehavior(Friends(AdjacentUnits(self,1))) =
              AddStatOverrideEffect(UnitsAffectedByHealType(mech,1), stat 0x4da,
                 PercentageOfAttackCappedAtMax(Attack, ConfigVar 0x4af[0xd], [0x4a]))
              & PerformAIAttackFromCurrentPosition(mech friends) & RemoveEffect(0x4da)
Template : Repair = clone Heal (HealUnitOperation) ; galvanic = PATTERN quickening.py DÉJÀ porté,
   à étendre multi-unit.
Prérequis MANQUANTS : (a) feuille Repair multi-cible + variante `ForRepair` (réveil membres swarm,
   documentée non implémentée `living_metal.py:104`) ; (b) PerformAIAttack MULTI-unités
   (quickening=single) ; (c) garde UnitsAffectedByHealType(mech).
Verdict : [opus]+prérequis nommés, 2 tranches (repair ; galvanic-field attack).
Risques : **le tooltip ne dit QUE « repair » mais le décompilé ajoute une attaque galvanique des
   alliés mech** — à confirmer live ; cible AI de PerformAIAttack = approximée (quickening.py:41).
```

**Synthèse (facilité croissante)** : 1002 → 1037 → 1117 → 1039 → **1082 = [fable]**.
**Angles validator post-port** : 1037 montant Chaos = somme (pas un var isolé) ; 1039 ordre/coût
RNG + flag no-act ; 1082 non-relance infinie de l'active ; 1117 confirmer live l'attaque galvanique.
