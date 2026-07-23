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
[1037 RevitalizingMalignancy | deathRotbone]  --- PORTE + VALIDE LIVE (case-220 opus-solver)
VAs : ExecuteBehaviour @181200eb0, GetAllHealTargets @181201150 (+Chaos @181201230 / Regular @181201280),
      callback b__0 @181218d00
Arbre : AllHealTargets = Healable(WithoutTrait(0x1a Imperial, Union(Friends(AdjacentUnits(self,1)), self)))
        AtomicGroup( Heal(regular = WithoutTrait(0x7ea Chaos) , Direct(var0x20=hpToHeal))          # non-Chaos
                   & Heal(chaos   = WithTrait(0x7ea)          , Direct(var0x22+var0x20)) )          # Chaos (CUMUL)
   var0x20 = GetVariableForLevel(0x20) = hpToHeal ; var0x22 = GetVariableForLevel(0x22) = hpToHeal_2.
Port : runner/abilities/deathguard.py (RevitalizingMalignancyAbility + revitalizing_malignancy_tree) ;
   feuille Heal `guard=` (behaviours/stats.py) ; enregistre handler.py (1037). Test :
   test_revitalizing_malignancy_live.py.
PREREQUIS (porte) : (a) garde `Healable` cote mutation = HP<max ET non-mechanical
   (`IsAffectedByHealType(unit,0) @180ed77d0` ; IsMechanical @180ed8a30 = Mechanical|LivingMetal|Vehicle) ;
   (b) *** NON LISTE au triage, DECOUVERT au port *** : le trait Chaos(0x7ea)/Imperial(0x1a) est ABSENT de
   gameconfig.unit().traits (0 unite le porte) -> DERIVE de la GrandAlliance (`GrandAlliance.GetTrait
   @1815647a0` : Imperial->26, Xenos->1006, Chaos->2026). Porte via `_grand_alliance_trait` (context.py :
   ajoute le trait d'alliance au set runner ; nom == GrandAllianceId). Sans ca le split est mort (tout en
   regular, aucune exclusion Imperial). Reutilisable pour le jumeau 1002 CombatRestoratives.
VALIDE LIVE (rank 17, deathRotbone lvl50 mult180 -> regular 3490, chaos 6980) : deathBlightbringer[Chaos]
   +6980, eldarRanger[Xenos] +3490, adeptHospitaller[Imperial] +0, necroWarden[LivingMetal, blesse] +0.
   Le « chaos » = SOMME de 2 vars lues+arrondies separement (iVar14+iVar13), PAS un scalaire fitte
   (6980 = 3490+3490 confirme live). Offline (port) == live sur les 5 discriminateurs.
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
