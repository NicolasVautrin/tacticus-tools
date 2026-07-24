> Tranche de la campagne de classification
> [case-220](../case-220-classification-campaign.md) — protocole, sommaire et
> ledger §T (prerequis transverses) dans le fichier maitre.

### §6.19 Aeldari (9 items, préfixe `eldar*`)

**Constat (PROUVÉ)** : les décisions Executioner/HarvesterOfSouls sont portées+validées (couche
entités/prédiction, #122). Executioner = COMBAT PORTÉ+VALIDÉ (ci-dessous). **Doom = COUVERT**
(extra_damage.py:734, factory.py:134, validé #57c) — caveat validator : absent d'ABILITY_INIT_OWNER_EFFECTS,
confirmer que le canal COMBAT (dégât appliqué) passe par la même voie.

```
[1066 Executioner | eldarFarseer]  — COMBAT PORTÉ + VALIDÉ LIVE (native_factory #37, PR case-220)
VAs : ExecuteBehaviour @1811d9f10 ; GetHits @1811da4a0 ; GetPotentialOtherTarget @1811da6c0 ; playbook @181130150
Arbre (mirror decompile) : op_and( AttackWithAttackDamage(Target(), Psychic, hits=RoundsStarted),
  If(IsDead(Target()), AttackWithAttackDamage(PickRandomly(Alive(Enemies(AdjacentUnits(TargetTile()))),1),
  Psychic, hits=RoundsStarted, multi/pick_n=1)) ). MAIN sur la cible ; si la cible MEURT (If(IsDead) évalué
  APRÈS le main) → même attaque (hits=RoundsStarted) sur 1 ennemi VIVANT random adjacent à la CIBLE.
  native_factory="attack" (@180de9fb0, XREF ; PAS AttackWithAbilityDamage @180de9c90/dd0). SetCache-prime +
  Inform(0xc1) FOLDÉS (no-op observable : mono-cible + corpse garde sa position ; bus non modélisé).
  hits = RoundsStarted (@1811da4a0 = GetHits = SUM turnsStarted@+0x58 scope caster = stat 12, plancher
  max(1,.)) — DYNAMIQUE, override la config nrOfHits (absente pour Executioner) via la feuille (`hits=`).
Fichiers : runner/abilities/aeldari.py (NOUVEAU, isolé faction) ; handler.py (ABILITY_CLASSES[1066]) ;
  behaviours/combat.py (feuille AttackWithAttackDamage : `hits` override en mode bornes) ; test_executioner_live.py.
Validé LIVE (2 seeds, cc=0) : MAIN per-coup bit-exact port==live [2824,2186,2644]/[1208,1172,1007] (hits=3=
  RoundsStarted) ; "ability" (1 tirage/coup) DIVERGE dès le coup 2 → discriminant native_factory. A/B tree==
  execute_ability_attack. If(IsDead) offline : KILL→secondary 1 ennemi adjacent-cible K coups / SURVIVE→0 /
  CAP1→1 des 2 / ANCHOR→cible (pas caster). Zero-régression : bringer/damage_roll/savage_echoes verts.
```
```
[1067 HarvesterOfSouls | eldarMauganRa]  — [opus] direct
VAs : ExecuteBehaviour @1811e70f0 ; GetHits @1811e75b0 ; @1811e76a0
Main HeavyRound (hits +1 si n'a pas bougé) + splash MinMaxDamage2 sur les ennemis adjacents-cible
∩ rayon-3 caster — patron splash.py exact, AtomicGroup. Décision portée+validée. Risques : gate
not-moved en combat ; profil MinMax2 du splash.
```
```
[TerrorsLament | eldarJainZar passif]  — [opus]+prérequis (le + propre des passifs)
VAs : CreateBehaviour @1811a3a10 ; effets @1811a3ae0 (1119) / @1811a3d20/@1811a3d70 (1120)
2 owner-effects AURA débuff sur ennemis ADJACENTS : −582 dégât + −1 hit melee (min 1). Templates
EXACTS : Camouflage_HitReduction (hits.py:521) + FightingRetreat/GuardianOrganism damage_reduction.
Prérequis : 2 classes + ABILITY_INIT_OWNER_EFFECTS + selector ennemis-adjacents. Risques : plancher
min-1 ; aura ENNEMIS (pas alliés).
```
```
[1063 FireAndReposition | eldarRanger]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811dea00 ; effet 1110 @180f49970/@180f497c0
UseActiveAbility(attaque normale, PORTÉ behaviours.py:1077) + ResetMovement(caster) + effet 1110
(−dmg ranged 1 round, template FightingRetreat). NO_END_TURN déjà porté (base.py:104). Prérequis :
behaviour ResetMovement (2e move — ABSENT, plus léger que ResetTurn) [PARTAGÉ ItItches §2] ;
classe 1110. Risques : 2e mouvement dans le modèle de tour.
```
```
[1068 SilentDeath | eldarJainZar]  — [opus]+prérequis (borderline fable sur le RNG)
VAs : ExecuteBehaviour @181207760 ; playbook @18115abc0
SNAKE-CHAIN : cible + jusqu'à 3 ennemis supplémentaires, chacun ADJACENT AU DERNIER touché
(exclusion cumulative, PickRandomly par pas), 3x Piercing chacun. Prérequis : helper snake-chain
impératif (expand-from-last + exclusion + pick par pas — apparenté ChainBehaviour §2).
Risques : ordre de conso state.rng par pas ; arrêt si candidats vides.
```
```
[InescapableAccuracy | eldarMauganRa passif]  — [opus]+prérequis (escalade [fable] possible)
VAs : CreateBehaviour @180f88a40 ; effets @180f88d30/@180f88b70/@180f88f00/@180f88f30 (1117) /
      @180f88bb0 (1115) / @180f88d80 (1116)
3 self-buffs gated « n'a pas bougé » : +crit-chance, +crit-dmg, override-hits (ignore les
hit-reductions). Prérequis : canal CRIT-ATTAQUANT (hooks base.py:213/220 présents, 0 USER — 1er
consommateur, partagé PathOfCommand_ExtraCrit TODO factory.py:377) ; canal override-hits ;
ActiveCondition not-moved ; interaction Overwatch (§T). Risques : empilement de canaux neufs.
```
```
[WireweaveNet | eldarRanger passif]  — [fable]
VAs : CreateBehaviour @1811ad160/@1811ad0b0 ; effet 1111 @180f78b70/@180f78ad0/@180f78b40
Riposte PRE-HIT au 1er ciblage melee normal du tour ennemi : 2x Piercing sur l'attaquant ; s'il
MEURT, son attaque est ANNULÉE (interrupt + annulation du pipeline). Once-per-enemy-turn. Rejoint
les vecteurs réactifs défenseur (§T) + kill-cancel type Overwatch (case-201) mais pre-hit.
Risques : ordre trigger vs résolution ; annulation on-kill.
```
```
[1064 Loki_SwoopingHawk | eldarAutarch]  — [fable]
VAs : ExecuteBehaviour @1811d4230 (classe partagée DiveAttackAbilityBase, ids 21/1064) ;
      @1811d4c10/@1811d4b40/@1811d4960 ; playbook @181169090
Attaque en LIGNE de 3 positions avec dégât PAR POSITION (GetVariableArrayForLevel dmg[0..2]) +
LANDING : MoveUnit derrière la dernière cible (fallback hex libre le plus proche). Prérequis :
géométrie ligne (§T) ; array de dégât par position ; framing StartAttack/FinishAttack ; landing
avec fallback. Risques : direction exacte ; dégât par position ≠ min/max unique ; tuile de landing.
```
```
[Doom | eldarFarseer passif]  — COUVERT (validé #57c ; caveat seeding combat à confirmer)
```

**Synthèse Aeldari** : couvert = Doom ; COMBAT PORTÉ+VALIDÉ = Executioner (1066) ; [opus] direct restant = HarvesterOfSouls ;
[opus]+prérequis = TerrorsLament < FireAndReposition < SilentDeath < InescapableAccuracy ;
**[fable]** = WireweaveNet, SwoopingHawk. Transverses : canal CRIT-ATTAQUANT (1er user + PathOf
Command) ; ResetMovement (partagé ItItches) ; snake-chain ; riposte pre-hit + kill-cancel.
HYPOTHÈSES : passage des hits dynamiques aux feuilles combat (non smoke-testé — classification).
