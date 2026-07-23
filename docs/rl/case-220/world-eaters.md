> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.3 WorldEaters (6 items réels — la table kit-coverage est STALE)

**Constat (PROUVÉ)** : `kit-coverage.md` surestime — déjà couverts : **MurderousSwing 1137**
(PORTÉ+VALIDÉ #108, la marque `[--]` est périmée), **BeaconOfRage** (#189/#191). Exclusions :
BloodyFury (P0-DAMAGE [fable]), BlessingsOfKhorne (CLOS). Restent 6 items.

```
[1131 JakhalStimms | worldJakhal]  — [opus] direct (léger)
VAs : ExecuteBehaviour @1811ec770 ; GetAttackBehaviour @1811ecb40 ; GetAdjacentTargets @1811ecab0 ;
      playbook @1811478e0
Attaque melee 4x Physical sur cible + AoE INTERSECTION (adjacents de la cible ∩ adjacents du caster)
+ self-loss 25% PV COURANTS (ChangeStat Subtract) ; free action. ZÉRO primitive manquante (selectors
op_BitwiseAnd + ChangeStat behaviours.py:908 + template BlackRage/MurderousSwing).
Risques : AoE = intersection seulement ; 25% du PV COURANT après l'attaque ; compte d'events du
playbook (MakeDamagePredictions non décompilé — à lire avant le port).
```
```
[WrathfulDevotion | worldTerminator passif 1214]  — [opus]+prérequis
VAs : CreateTrigger @1811ad6b0 (On 0x37 kill-melee OR On 0x3c=60 arrivée TeleportStrike) ;
      CreateBehaviour @1811ad410 ; GetTargets @1811ad860
Shield(var 0x27=2910, 1 round) sur self + amis Chaos adjacents. CreateShield (behaviours.py:1128) +
sélecteurs + On(55) EXISTENT ; shields captés live → prédiction gratuite.
Prérequis : émettre l'event deep-strike-landing On(UnitBecameTargetable=60) dans turnflow.py ;
gate IsDefeatedByMeleeAttack. Risques : non-double-shield (capté vs posé) ; expiration 1 round.
```
```
[Skullsmasher | worldJakhal passif 1217]  — [opus]+prérequis
VAs : effet @180f6bd90/@180f6bb10/@180f6ba00/@180f6b9d0 ; stun @1811a03a0/@1811a0320 + @1811a04d0/@1811a0450
(a) +extraDmg additif = var(8) x floor(PV%-manquant du CASTER / 10), Max(0,...) — patron BeaconOfRage
+ contexte PV-caster à ajouter. (b) stun 2-triggers : marqueur 0x4f0 au kill melee (hors trait 0xd),
puis Stunned 1162 sur chaque cible attaquée. Combat-only (pas dans le dégât prédit).
```
```
[TrophyTaker | worldExecutions passif 1229]  — [opus]+prérequis
VAs : effet 1289 @180f74250/@180f74080/@180f74420 ; ability @1811a8e00/@1811a8cb0 ; @1811a8e80
(a) +873 dmg ET (b) +873 crit-dmg vs cible <50% PV (gate strict Not(>=50)) ; (c) snowball
+16% crit-chance x kills (StaticStatModifier posé On(55) — capté live → prédiction gratuite).
Prérequis : CONTEXTE PV-CIBLE (target_health_pct) threadé dans create_effect_damage_bonus_for_attack
+ create_effect_crit_damage_bonus_for_attack (prédiction ET combat) ; ability-trigger On(55) offline.
Risques : strict <50 vs i2 « at or below » ; canal crit SÉPARÉ de l'additif ; pas de double-compte
crit-chance (déjà dans GetStat 9).
```
```
[1141 OverwhelmingWrath | worldEightbound]  — [opus]+prérequis (S2 candidat fable)
VAs : ExecuteBehaviour @1811f8bc0 ; attaque différée @1811109a0 (triggered 1237) ; playbook @1811503b0
Active = RangeDmgReduction 1301 (PORTÉ #190) + Taunt bond 27 sur adjacents + bond 0x514=1300
PendingAttack self ; l'AoE 2x Eviscerate fire au TURN-START SUIVANT du porteur.
Prérequis : plumbing « pending-attack » (effet-bond portant un triggered turn-start + consommation).
Risques : NE PAS frapper au tour du cast ; sélecteur recalculé à la position N+1 ; confront stateful.
```
```
[1132 KillMaimBurn | worldKharn]  — [fable], le plus dur de la faction
VAs : ExecuteBehaviour @1811ecd50 ; GetNextTarget @1811ed370 ; @1811ed340/@1811ed330 ; playbook @181148210
3 attaques séquentielles multi-profil (1x Piercing / 6x Eviscerate / 1x Plasma portée 2), ciblage
chaîné kill-priority (même cible jusqu'à mort puis SortUnitsByDamageUtility(0x22)), Group(0x20) x3 +
ExecuteAtomic. Prérequis ABSENTS : MinMaxDamage2/3 + GetDamageProfile2/3 ; GetNextTarget ;
prédiction 3-events multi-profil.
```

**Synthèse WE** : [opus] direct = JakhalStimms ; [opus]+prérequis = WrathfulDevotion, Skullsmasher,
TrophyTaker, OverwhelmingWrath ; **[fable]** = KillMaimBurn. HYPOTHÈSES : bindings 0x168/0x178
JakhalStimms ; comptes d'events playbooks non décompilés ; trait 0xd (Skullsmasher) ; ordre args
Percent(max,cur).
