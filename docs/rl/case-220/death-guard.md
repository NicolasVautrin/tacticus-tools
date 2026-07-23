> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.8 DeathGuard (8 items après exclusions 1037/1040/1038/1169/PutridExplosion)

**Constat (PROUVÉ)** : **ExplosiveMaladies = FAUX POSITIF kit-coverage** — PORTÉ+validé bit-exact
(#57c-C, `loki/hits.py:244-304`, factory.py:70/120) ; résidu mineur = flag « always overkilled »
non porté (annoté hits.py:254).

```
[DestroyerHive | deathTyphus passif]  — [opus] direct (le + facile)
VAs : CreateTrigger @18121d4b0 ; GetValidTargets @18121d540
On(0x16 TurnStart, tour du porteur) : 1x DirectDamage pierce-100 sur UN ennemi adjacent random.
Tous primitifs présents (template Ambush/LivingMetal + AttackWithAttackDamage + PickRandomly).
HYPOTHÈSE : CreateBehaviour non symbolisée (random-adjacent inféré du kit) ; gate +0xa0.
```
```
[1042 FlailSwing | deathBlightlord]  — [opus] direct
VAs : ExecuteBehaviour @1811ded80
InformWeapon + AttackWithAttackDamage(target, 3x Power, flag « always overkilled » Nullable=1).
PAS de splash ni trigger interne (le déclenchement Haze = passif séparé). Prérequis : passthrough
flag overkill (mineur). Risques : l'overkill ne se voit que vs Resilient/revive.
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

**Synthèse DG** : couvert = ExplosiveMaladies ; [opus] direct = DestroyerHive, FlailSwing ;
[opus]+prérequis = PlagueWind, CursedPlagueBell x2 ; BLOQUÉ MoW = EntropyCannons ; **[fable]** =
TaintedNarthecium, HazeOfCorruption. **Levier #1 faction = PRIMITIVE AURA CONTAGION**
(`ContagionsOfNurgleRange @180dece10`, `CalculateRange @180f39940` : rounds ≤2→1, 3-4→2, 5+→3,
`IsInUnitContagionsOfNurgleAura`) — non portée (enum+gate d'immunité seulement) ; débloque
CursedPlagueBell x2 + ciblage EntropyCannons + FoulInfusion (§3). **Gap séparé flaggé** : l'aura
armor-reduction Contagion ELLE-MÊME (−armor% ennemis dans l'aura, x6 héros DG) n'est PAS matérialisée —
le consommateur `target_armor_reduced` existe (base.py:97) mais aucune source ne l'alimente →
tâche dédiée à créer à la synthèse.
