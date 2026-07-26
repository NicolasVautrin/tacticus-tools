> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.7 Necrons (11 items après exclusions 1009 ResurrectionOrb / 1226 Chronometron)

> **MAJ #116 (lot 1)** — 3 des 4 actives NO-OP du lot sont **PORTÉES + VALIDÉES LIVE** :
> **1009 ResurrectionOrb** (summon pur, aucune résurrection — les deux exclusions ci-dessus sont donc
> levées), **1226 Chronometron**, **1006 MultiThreatEliminator** (la feuille `ChainLeftOverHits` était
> nommée « ABSENTE / partagée BloodyFury » ci-dessous : elle est désormais portée,
> `behaviours/combat.py::ChainLeftOverHitsAttackDamage`). **1005 AdaptiveStrategy reste un RÉSIDU**
> (3 prérequis, dont `RelentlessMarch` hors périmètre). Détail, mesures et résidus chiffrés :
> [`case-116-necrons-lot1.md`](../case-116-necrons-lot1.md).

**Substrat (grep PROUVÉ)** : feuille DSL `Repair` NON portée (LivingMetal = repair bespoke) ;
event `On(ArrivedAtFinalTile=28)` posé (turnflow.py:48/67) mais AUCUN vecteur ne le dispatch ;
famille `ADamageDefenseModifierAbilityEffect` présente (damage_reduction.py) ; faces DÉCISION
déjà portées (MartialApotheosis/FabricatorClaw playbooks, prédictions 1006/1008).

```
[MartialApotheosis | necroOverlord passif — 1045 TriggeredAbility]  — [opus] direct — PORTE + VALIDE
VAs : CreateBehaviour @181222d00 ; GetValidTargets @18121d540 (partage) ; CreateTrigger herite @18121d4b0 ;
      MinMaxDamage @180fbca20 ; playbook @181168a30/@1811689d0.
Port : runner/operations/triggers/loki/martial_apotheosis.py (MartialApotheosisAttackAbility) +
       ABILITY_TRIGGERS["MartialApotheosis"] (dispatch.py). PAS handler.py : c'est un TRIGGERED (1045),
       PAS un ActiveAbility -- et 1045 en ActiveAbilityType = GetEmRuntz (collision ; MartialApotheosis
       ne se cast JAMAIS via ActiveAbilityMessage -> handler.py serait dead-code + collision).
STRUCTURE (mirror 1:1) : la classe native MartialApotheosisAbility ETEND DestroyerHiveAbility (son
CreateBehaviour appelle DestroyerHive.GetValidTargets(this) sur `this` = methode d'INSTANCE heritee ;
aucun symbole propre CreateTrigger/GetValidTargets/.ctor). HYPOTHESE trigger RESOLUE :
  CreateTrigger (herite @18121d4b0) = On(TurnStart_Actions=0x16) & OwnerIsActor(@0xa0)
                                      & AmountIsGreaterThanZero(GetValidTargets).
  GetValidTargets (@18121d540, refcount 6) = Damageable(Enemies(AdjacentUnits(casterTile@0x148, radius=1)))
                                             = ennemis damageable ANNEAU-1 (PAS le disque rayon-2 Harbinger).
  CreateBehaviour @181222d00 = AttackWithAttackDamage(caster@0x160, PickRandomly(GetValidTargets, count=1),
    MinMaxDamage(minDmg/maxDmg[level]), GetDamageProfile(0)="Energy"(pierce 30), GetNumberConstant(0x2f)=
    nrOfHits=2). Famille "attack" (DSLFactory.AttackWithAttackDamage @180de9fb0), attackRangeType=Melee,
    level=PASSIVE (level_slot="passive" ; active==passive==50 verifie live necroOverlord).
VALIDATION (test_martial_apotheosis_live.py, 5 PASS, porteur necroOverlord SPAWNABLE) : (A) vecteur
turn-start + OwnerIsActor (muet au tour adverse) ; (B) AmountIsGreaterThanZero (0 adjacent -> pas de fire) ;
(C) ciblage ANNEAU-1 (dist1 frappe, dist2 exclu) ; (D) A/B bit-exact (arbre==execute_ability_attack 2 coups
Energy pierce 30, meme MT) + params ; (E) LIVE replay-diff (cible offline==live ; degat exact hors scope =
calage RNG cascade turn-start, == TheBetrayer). COLLAPSE PickRandomly(count=1) : pool<=1 => deterministe.
```
```
[1008 HarbingerOfDestruction | necroPlasmancer]  — [opus] direct — PORTÉ + VALIDÉ (caster-agnostique)
VAs : ExecuteBehaviour @1811e6750 ; GetAdditionalTargets @1811e6a40 ; GetEnemiesInRange @1811e6e50 ;
      GetTargetAmount @1811e6fa0.  Port : runner/abilities/necrons.py (HarbingerOfDestructionAbility).
ARBRE (mirror 1:1) : UN SEUL AttackWithAttackDamage(caster, If(AreEqual(caster,target), additional,
Target()+additional), MinMaxDamage, Direct(GetDamageProfile(0)="DirectDamage"), Direct(GetNumberConstant(
0x2f)=nrOfHits=1)). additional = PickRandomly( Damageable(Unobscured(caster, SurroundingEnemies(casterTile,
range=GetNumberConstant(0x16)=2) − Target())), count = nrOfUnits(var 0x9a) − 1 ).
= cible + (N−1) ennemis random dans le DISQUE rayon-2 du CASTER (non obscurcis, damageable), 1 coup chacun.
CORRECTIONS RE vs classif initiale : (a) "DirectDamage" = NOM DU PROFIL (PiercingRatio 100), PAS l'effet
direct-damage — c'est un AttackWithAttackDamage (famille "attack", native_factory défaut, PAS flaggé
"ability"). (b) UN SEUL leaf COMBINÉ (main+additionnels attaqués ensemble, tri par id unique), PAS deux
volets séparés (contraste BringerOfDespair). (c) sélecteur rayon-2 = SurroundingEnemies(CasterTile, 2)
(disque, == le natif Enemies(Units(SurroundingTiles(incl=0,2))), IDENTITÉ prouvée) + Sub(Target) + Unobscured
+ Damageable — primitives LIVE-VALIDÉES par Gauntlets (rayon-2 Unobscured) + BringerOfDespair (caster-anchor
+ Sub + PickRandomly). N = nrOfUnits (var 0x9a) = 3 (lvl<=16) / 4 / 5 (lvl>=35), config-driven.
VALIDATION : porteur necroPlasmancer = UNSPAWNABLE_FALLBACK connu (rl_collect_batch.py) ; NPC porteurs hors
pool arène ; force-cast 1008 sur non-porteur = NO-OP (vérifié) → AUCUN cast LIVE réel possible → validation
CASTER-AGNOSTIQUE offline (config globale, précédent PlasmaGrenade summon-only). Tests
test_harbinger_of_destruction_live.py (4 PASS) : routage handler 1008, ciblage rayon-2 (d1&d2 frappés, d3
exclu), cap N−1 + exclude-target, caster-anchor, A/B bit-exact (tree==execute_ability_attack), params
DirectDamage pierce 100 / nrOfHits 1. Conso RNG du PickRandomly CALÉE depuis #130 (`min(|pool|, N−1)`
tirages, bornes décroissantes, même quand le pool tient — la baseline A/B du test la reproduit
explicitement ; cf. `case-130-pick-randomly-rng.md`). Résidu #215 restant, NON root-cause : sous
pool > N−1, l'ordre d'énumération natif (non id-trié) décide QUELLES unités sont piquées.
```
```
[1006 MultiThreatEliminator | necroDestroyer]  — [opus]+prérequis (candidat fable)
VAs : ExecuteBehaviour @1811f57e0 ; GetExtraHits @1811f5b60 ; nextHitTargetSel @1811f5ba0
ChainLeftOverHitsAttackDamage(target, 6 hits Gauss, +1 hit/kill, report des hits restants sur l'ennemi
suivant adjacent-au-dernier & range-2). Feuille ChainLeftOverHits ABSENTE — PARTAGÉE avec BloodyFury
§3. Prédiction 1006 validée live. Risques : ordre hits/kills, re-ciblage, conso RNG → si délicat, [fable].
```
```
[FabricatorClawArray | necroSpyder passif]  — [opus]+prérequis
VAs : CreateBehaviour @18121ea20 ; CreateTrigger @18121eb30 (On 0x1c=28 ArrivedAtFinalTile) ;
      GetTargetSelector @18121ebd0
Repair(PickRandomly(AdjacentFriends & Repairable, 1), var 0x24) avec Otherwise(negative-effects).
Prérequis : vecteur On(28) [PARTAGÉ LivingLightning] ; feuille Repair DSL ; sélecteurs Repairable/
UnitsAffectedByHealType/UnitsWithNegativeEffects. Risques : le single-trigger couvre « ait bougé ou
non » (ne pas splitter) ; cap maxHP ; branche Otherwise.
```
```
[RelentlessMarch | necroWarden passif]  — [opus]+prérequis (AVANT AdaptiveStrategy)
VAs : CreateBehaviour @1812250e0 ; effet @180f68680/@180f684c0/@180f68840/@180f68470
Turn-start : AddEffect(1011, amis adjacents non-Stationary, +1 MOVEMENT 1 tour) + Repair(amis
adjacents Mechanical, var 0x24). Prérequis : feuille Repair [partagée] ; effet aura Movement Apply/
Revert. Risques : exclusion Stationary ; timing apply/revert.
```
```
[LivingLightning | necroPlasmancer passif]  — [opus]+prérequis
VAs : Ability @181221d90/@181221f20/@1812220e0 ; MoveEffect @1812222a0/@181222300/@181222420 ;
      RemoveTrigger @180f568f0
On(28) : attaque un ennemi random — adjacent si le porteur a bougé (marqueur 0x3fc posé On(31
PreUnitMove)), sinon rayon config. Prérequis : vecteur On(28) [partagé] ; logique adjacent-vs-rayon
via marqueur move. Risques : distinction bougé/pas-bougé ; PickRandomly(1).
```
```
[1005 AdaptiveStrategy | necroWarden]  — [opus]+prérequis (APRÈS RelentlessMarch)
VAs : ExecuteBehaviour @1811b0840 ; selector @1811b0b80 ; playbook @181119d80
If(HasTriggeredAbility 0x3ec) TriggerAbility(RelentlessMarch) + PerformAIAction(amis non-Character
adjacents) + AddStatOverrideEffect(0x3f4 override-dégât)/RemoveEffect autour de l'action forcée.
Prérequis : RelentlessMarch porté d'abord ; nœud TriggerAbility ; PerformAIAction (P1). Risques :
override posé/retiré autour de l'action ; chaque ami agit 1x.
```
```
[TimesplinterMantle | necroChronomancer passif]  — [opus]+prérequis (pivot → fable)
VAs : Ability @1811a88b0/@1811a8a00/@1811a8a80 ; effet @180f73e30/@180f73bb0/@180f73d90 ;
      playbooks @181189ec0/@180e3dd80
Turn-start : Foreach(self + amis Mechanical adjacents non-steppables, AddEffect(1551)) ; effet =
ForSubtraction FLAT (famille damage_reduction PORTÉE) ; retiré On(9)|On(TurnEnd). PIVOT : confirmer
que le COMBAT applique la réduction flat (sinon [fable]). Risques : re-pose/retrait ; expiration.
```
```
[InescapableDeath | necroDestroyer passif]  — [fable]
VAs : effet @180f52420 (AReactivateOverwatchEffect) ; gate IsOverwatchAttack @180f523f0
Kill en overwatch → RESTE en overwatch avec 1 hit de moins ; +655/hit overwatch-only. Prérequis :
substrat re-arm overwatch + hits décroissants + extra-damage gate overwatch (rejoint le sous-système
Overwatch §2). Risques : reproduire un kill-en-overwatch ; décrément cumulatif.
```
```
[1223 ReanimationBeam | necroReanimator MoW]  — [fable] / BLOQUÉ MoW
VAs : ExecuteBehaviour @1811ff080 ; @1811ff410/@1811ff510/@1811ff3b0 ; ReviveEffect @180f67b90/@180f67ac0
Repair(amis Mechanical porteurs 0x609) + les summons agissent (PerformAIAction + override-attaque) +
ReviveEffect. Couplé NanoscarabRepairProtocols. INVALIDABLE tant que le cast-MoW n'est pas prouvé.
```
```
[1224 NanoscarabRepairProtocols | necroReanimator MoW]  — [fable] / BLOQUÉ MoW
VAs : ExecuteBehaviour @1811f60d0 ; @1811f63e0/@1811f6370 ; effet @180f5aca0/@180f5ab60
AddEffect(0x609 repair-bonus ForAddition) + buff maxHealth. Même blocage cast-MoW ; couplage 0x609
consommé par ReanimationBeam.
```

**Synthèse Necrons** : [opus] direct = **MartialApotheosis (PORTÉ+VALIDÉ)**, **HarbingerOfDestruction (PORTÉ+VALIDÉ)** ; [opus]+prérequis =
FabricatorClawArray, RelentlessMarch, LivingLightning, MultiThreatEliminator (candidat fable),
AdaptiveStrategy, TimesplinterMantle (pivot combat-flat) ; **[fable]** = InescapableDeath +
ReanimationBeam/NanoscarabRepairProtocols (BLOQUÉS MoW). Débloqueurs faction : feuille **Repair DSL**
(+sélecteurs) et vecteur **On(28)** — chacun débloque 2+ items.
