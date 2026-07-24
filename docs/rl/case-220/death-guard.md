> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.8 DeathGuard (8 items après exclusions 1037/1040/1038/1169/PutridExplosion)

**Constat (PROUVÉ)** : **ExplosiveMaladies = FAUX POSITIF kit-coverage** — PORTÉ+validé bit-exact
(#57c-C, `loki/hits.py:244-304`, factory.py:70/120) ; résidu mineur = flag « always overkilled »
non porté (annoté hits.py:254).

```
[DestroyerHive | deathTyphus passif]  — [opus] direct — PORTÉ + VALIDÉ LIVE (bit-exact 3 seeds)
VAs : CreateTrigger @18121d4b0 ; GetValidTargets @18121d540 ; CreateBehaviour @18121d320 (SYMBOLISÉE,
      contra l'hypothèse) ; AttackWithAttackDamage @180de9fb0 (CALLEE "attack", XREF du call-site @18121d47e) ;
      MinMaxDamage @180fbca20 ; PickRandomly @180ef0be0 ; NextInternal @180e39be0.
CreateTrigger = On(0x16 TurnStart_Actions) & @0xa0(OwnerIsActor, == LivingMetal @0xa0) &
      AmountIsGreaterThanZero(GetValidTargets). GetValidTargets = Damageable(Enemies(AdjacentUnits(caster,1))).
CreateBehaviour = AttackWithAttackDamage(caster, PickRandomly(GetValidTargets,1), MinMaxDamage(minDmg 0xc/
      maxDmg 0xd)[PASSIVE lvl], GetDamageProfile(0)=DirectDamage(pierce-100), nrOfHits=GetNumberConstant(0x2f)=1,
      alwaysOverkilled=Nullable(HasValue=0)). => artefact = AttackWithAttackDamage famille "attack" (PAS un
      effet DirectDamage : "DirectDamage" est le NOM du profil d'arme, pierce 100) ; PAS de force_overkill ;
      degat au niveau PASSIF (passiveAbility -> passive_ability_level, cf. Hypersensory) ; mono-coup.
PLACEMENT : passif TRIGGERED (PAS un summon comme la roadmap le supposait) -> triggers/loki/destroyer_hive.py,
      registre ABILITY_TRIGGERS['DestroyerHive'] (template LivingMetal), NON deathguard.py/handler.ABILITY_CLASSES.
FINDING RNG : PickRandomly(count=1) tire NextInternal(0,count) UNE fois -> consomme 1 genrand MEME a count==1
      (branche puissance-de-2, comme le wasted-resolve #220). La pick precede l'attaque -> le tirage est
      LOAD-BEARING pour la bit-exactness (le helper `_pick_randomly` base.py, sans tirage a n==1, désyncherait) ;
      `_pick_target` (destroyer_hive.py) tire toujours. Validé : port bit-exact vs live 3 seeds (1557/1568/1480),
      n==2 même cible + bit-exact, control no-draw diverge, gate/scoping OK. test_destroyer_hive_live.py.
```
```
[1042 FlailSwing | deathBlightlord]  — [opus] direct — PORTÉ + VALIDÉ LIVE (PR #220)
VAs : ExecuteBehaviour @1811ded80 ; DSLFactory.AttackWithAttackDamage @180de9fb0 (CALLEE = "attack") ;
      DSLFactory.InformWeapon @180df2010 ; ApplyResilientTraitDamageLimit @18102c3a0
Arbre (mirror 1:1) : Execute( op_BitwiseAnd( InformWeapon(Power), AttackWithAttackDamage(target, MinMaxDamage,
Power, nrOfHits=GetNumberConstant(0x2f)=3, alwaysOverkilled=Nullable(true)) ) ) — plain Execute (PAS atomic).
PAS de splash ni trigger interne (le déclenchement Haze = passif séparé). Port :
`deathguard.py:flail_swing_tree` = `op_and(InformWeapon("Power"), AttackWithAttackDamage(Target(),"FlailSwing",
"Power",melee, force_overkill=True))`. `InformWeapon` = canal weapon-inform metadata COMBAT-INERTE (leaf no-op
`combat.py:InformWeapon`). native_factory="attack" (2 tirages/coup, VÉRIFIÉ par XREF de @1811ded80, tip #2).
Flag « always overkilled » (Nullable=1) PORTÉ via `force_overkill=True` (feuille -> execute_ability_attack ->
`_run_hits` force overkill=True/coup -> bypasse le cap Resilient) — NON un résidu. VALIDÉ LIVE : (a) 3x Power
bit-exact per-coup (live==offline, ratio 1.0) ; (b) A/B tree==execute_ability_attack ; (c) native_factory
attack vs ability discriminant (2 seeds) ; (d) overkill : custoKyrus Resilient HP 10000 -> live tue [5070,4555,
375] sum=PV full ; port force_overkill=True hp->0 (tue) ; control False hp->1 (survit) = le flag est le seul
écart. Zéro-régression (revitalizing_malignancy + damage_roll + vigilance_eternal). test_flail_swing_live.py.
```
```
[1035 PlagueWind | deathTyphus]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811f8f40 ; GetDamage3 @1811f94f0
Onde 3 tiers : T1 = cible (MinMax) ; T2 = adjacents de T1 (MinMax2) ; T3 = adjacents de T2 − T1 − T2
(MinMax3) ; 3 groupes AttackWithAbilityDamage Psychic, AtomicGroup. Prérequis : courbes MinMaxDamage2/3
[PARTAGÉ KillMaimBurn §6.3] ; sélecteur wavefront-exclusion (Cache + soustractions). Risques :
exclusivité des tiers ; le splash ne re-déclenche pas Psyker (#147).
```
```
[CursedPlagueBell mouvement | deathBlightbringer passif]  — [opus]+prérequis
VAs : GetTargetsSelector @18121c3b0 ; effet @180f3b260/@180f3b080/@180f3b000/@180f3b440
Turn-start : +1 Movement (1 tour) aux amis Chaos non-Stationary DANS L'AURA CONTAGION.
Prérequis : PRIMITIVE AURA CONTAGION (transverse, cf. synthèse). Risques : range = f(round) ;
apply/revert.
```
```
[CursedPlagueBell reflect Psyker | deathBlightbringer passif]  — [opus]+prérequis
VAs : CreateBehaviour @18121bdb0 ; profile @18121c1b0 ; gate @18121c230 (IsInUnitContagionsOfNurgleAura)
Ennemi Psyker dans l'aura qui inflige du Psychic → se prend 1x 1310 Psychic (self-attack).
Prérequis : aura Contagion [même primitive] ; trigger damage-Psychic (CreateTrigger non décompilée =
HYPOTHÈSE, RE à compléter avant port). Risques : anti-boucle (le reflect ne re-déclenche pas).
```
```
[1168 EntropyCannons | deathCrawler MoW]  — BLOQUÉ harnais MoW (veille)
VAs : ctor @1811c01e0 ; playbook @18112f190/@18112f310
2x Energy pierce-30, 1 munition, ciblage = ennemi armour-reduced OU dans une aura Contagion amie.
Mécanique simple mais INVALIDABLE (bucket PlagueburstMortar/DutyEternal). target_armor_reduced
consommateur EXISTE (base.py:97) ; la SOURCE Contagion manque.
```
```
[TaintedNarthecium | deathRotbone passif]  — [fable]
VAs : effet @180f70a90/@180f709b0 ; base ReviveEffect @180f46e60/@180f46d80/@180f46a70
Allié Chaos adjacent vaincu → Maybe(75%) Revive-en-place (PV = min(3565, maxPV)), once-per-turn,
« even if Overkilled ». Prérequis ABSENTS : feuille Revive-en-place (≠ Resurrect/ambush) ; nœud
Maybe PRNG en exécution ; gate once-per-turn ; bond on-adjacent-ally-death. Risques : tirage PRNG ;
2e mort le même tour ; overkill bypass.
```
```
[HazeOfCorruption | deathBlightlord passif]  — [fable]
VAs : effet @180f4d6d0/@180f4cf70/@180f4d9e0/@180f4d8c0/@180f4d890/@180f4dcd0
Bond sur la cible de FlailSwing ; à sa mort → transfert du DÉGÂT RÉSIDUEL (overkill spillover chiffré,
GetLeftOverDamages) + 1x Toxic sur un ennemi adjacent-à-la-fois (Maladus & cible) ; re-trigger si
Maladus meurt ; persistent data 0x434. Prérequis ABSENTS : canal leftover-overkill chiffré ; bond
attack→cible ; sélecteur adjacent-both ; re-trigger on-death. Risques : dépend de l'overkill EXACT
(modèle de dégât + Resilient/TerminatorArmour) ; tester couplé à FlailSwing.
```

**Synthèse DG** : couvert = ExplosiveMaladies, **FlailSwing (PR #220, porté+validé LIVE : 3x Power +
InformWeapon no-op + flag overkill via `force_overkill`)**, **DestroyerHive (porté+validé LIVE bit-exact :
passif turn-start AttackWithAttackDamage mono-coup pierce-100 sur ennemi adjacent random ; pick-draw
load-bearing ; triggers/loki/destroyer_hive.py)** ; [opus] direct restant = aucun ;
[opus]+prérequis = PlagueWind, CursedPlagueBell x2 ; BLOQUÉ MoW = EntropyCannons ; **[fable]** =
TaintedNarthecium, HazeOfCorruption. **Levier #1 faction = PRIMITIVE AURA CONTAGION**
(`ContagionsOfNurgleRange @180dece10`, `CalculateRange @180f39940` : rounds ≤2→1, 3-4→2, 5+→3,
`IsInUnitContagionsOfNurgleAura`) — non portée (enum+gate d'immunité seulement) ; débloque
CursedPlagueBell x2 + ciblage EntropyCannons + FoulInfusion (§3). **Gap séparé flaggé** : l'aura
armor-reduction Contagion ELLE-MÊME (−armor% ennemis dans l'aura, x6 héros DG) n'est PAS matérialisée —
le consommateur `target_armor_reduced` existe (base.py:97) mais aucune source ne l'alimente →
tâche dédiée à créer à la synthèse.
