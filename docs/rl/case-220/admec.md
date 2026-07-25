> Tranche de la campagne de classification
> [case-220](../case-220-classification-campaign.md) — protocole, sommaire et
> ledger §T (prerequis transverses) dans le fichier maitre.

### §6.17 AdeptusMechanicus (9 items, préfixe `admec*` ; exclusions 1117/1122 ; admecMarshall COMPLET)

**Constats (PROUVÉ)** : Vehicle = CLOS (§5, rattaché #131/B4). **GalvanicField = COUVERT côté
décision** (Repair_GalvanicField 1119 bespoke Comparable, action_generators.py:487-523) et son combat
= FOLD dans le port DefendTheDivineWork §1 (même classe galvanique, enregistrer 1117 ET 1119 —
l'ability-swap natif AddActiveAbility/RemoveActiveAbility est registered-but-dead pour le runner).

```
[1139 SentinelDirectives | admecDestroyer]  — [opus] direct — COMBAT PORTÉ + VALIDÉ LIVE
VAs : ExecuteBehaviour @1811c4a30 ; playbook @181135f70 (décision DONE)
PORT : abilities/admec.py (SentinelDirectivesAbility, arbre `sentinel_directives_tree`) + registre
handler.py (1139). Mirror 1:1 du décompilé @1811c4a30 :
    Execute( op_Add( op_Add( InformWeapon(Physical),
                             AttackWithAttackDamage(caster,target,MinMaxDamage,Physical,nrOfHits=1) ),
                     AddEffect(0x429=Pinned, source=AbilityStateReference=caster, target, dur DEFAUT) ) )
plain Execute (aucun AtomicGroup). native_factory="attack" (callee = `DSLFactory$$AttackWithAttackDamage`,
JAMAIS AttackWithAbilityDamage — contraste SpiritLeech "ability"). Quasi-clone SpiritLeech MOINS
GetAttackDamage conditionnel (MinMaxDamage brute, aucun damage_override) et MOINS Heal/SetCache
(aucun callee Heal), PLUS InformWeapon (comme FlailSwing, canal weapon-inform combat-inerte).
Turn-flow (« ne finit pas le tour, peut entrer en Overwatch ») = 1139 déjà dans les 2 frozensets
base.py (NO_END_TURN + NO_ABILITY_USED) -> slot générique (handler `_add_flags_after_execution`).
VALIDATION LIVE (admecDestroyer Sy-Gex, seul porteur ; test_sentinel_directives_live) : config
[minDmg 4254,maxDmg 5318] pierce=1 hits=1 ; A/B tree==pipeline direct BIT-EXACT (off=3067==A/B=3067) ;
Pinned posé live (delta pre/post)==offline ; turn-flow live (currentPlayer inchangé, 2 flags False).
RÉSIDU (hors port, confound caster-intrinsèque) : live=3510 >= off=3067 (delta 443) = passifs Sy-Gex
HeavyWeapon_ExtraDmg(1008) + HeavyGravCannon(1291) non entièrement consommés par le pipeline d'attaque
d'ability -> égalité bit-exacte live confondue (assert direction live>=off). HeavyGravCannon = item
séparé ci-dessous ([opus]+prérequis canal PIERCING). Le TREE SentinelDirectives lui-même est fidèle.
```
```
[HeavyGravCannon | admecDestroyer passif]  — [opus]+prérequis
VAs : effet @180f4ee20/@180f4ec20/@180f4ed60/@180f4ef20 (1291 enum-only)
Owner-effect ranged vs Mechanical/MkXGravis(1013)/TerminatorArmour(1039) : +364 dégât (clone
BeastSlayer, trivial) + +60% PIERCE. Prérequis : canal PIERCING attaquant — `for_piercing` DÉFINI
(effect_bonus.py:72) mais JAMAIS consommé par damage_model [ledger §T pierce]. Risques : effet capté
live sans classe = no-op silencieux ; dégât vs blindés faux sans le canal.
```
```
[1116 RadBombardment | admecDominus]  — [opus]+prérequis (décision DONE NC)
VAs : ExecuteBehaviour @1811fdb60 ; GetAffectedTiles @1811fde10 ; AffectedTileAmount @1811fda60
LIGNE 1-des-6-directions depuis la cible, longueur = 1 + RoundsStarted + TotalRepairActionsAmount
(amis Mechanic), moins les bloquants → AttackWithAbilityDamage(Toxic) + Pinned + AddEffect(1244
Contaminated, tuiles — pose réutilisable rad_saturation.py, aval ContaminatedTileEffect PORTÉ).
Prérequis : sélecteur LIGNE runner (helper cube existe côté décision) [ledger géométrie ligne] ;
compteur TotalRepairActionsAmount (souvent 0 offline). Risques : longueur croissante exacte ;
Subtraction(Blocking).
```
```
[MasterAnnihilator | admecDominus passif]  — **PORTE + VALIDE LIVE (#222)**
VAs : CreateTrigger @18110ba90 ; CreateBehaviour @18110b940 ; effet @180f58d50/@180f58f40
L'effet-marqueur 1249 (+1 coup, non-Psychic, first-hit) etait PORTE+CONSOMME ; la POSE est desormais
cablee : On(0x26) attaque normale de Vitruvius -> RemoveEffect(OwnerOfEffect(EffectsFromUnitSource(
Self,1249)), 1249) + AddEffect(1249, Target()). Prerequis LEVES : entree ABILITY_TRIGGERS +
selecteurs EffectsFromUnitSource/OwnerOfEffect + RemoveEffect multi-cible. Live : le marqueur SE
DEPLACE (u77->u79->u77), level 1 rem 0, jamais en double ; un marqueur d'AUTRE source n'est pas retire.
Residus : remove-self a la mort de la source (@180f58f40) ; cap 5456 non modelise (TODO hits.py).
cf. case-222-maillons-de-pose.md §1.
```
```
[OptimizedGait | admecRuststalker passif]  — [fable]
VAs : reposition @18110fb90/@18110fa80 ; attaque réactive @181110410/@18110fe00 ;
      normal-attack @1811f8740/@1811f84f0/@1811f8640 ; utility 59 @1810f11f0
(A) Un ami MECHANICAL attaque un ennemi adjacent à Exitor-Rho → il l'attaque aussi (2x Energy,
RandomAmount, + interaction CordClaw 0x4e2). (B) Ennemi adjacent tué par un ami Mechanical OU par (A)
→ Exitor-Rho OCCUPE l'hex libéré (MoveUnit). Prérequis ABSENTS : vecteur réactif react-to-ALLY-attack
(les On(9) portés sont OwnerIsTarget/Caster) ; death-cause (trait du tueur / ability tueuse) ;
RandomAmount [partagé Poxwalkers] ; move-into-vacated-hex. Validation en TOUR ENNEMI.
```
```
[Vehicle x8 | trait]  — CLOS (§5)   |   [GalvanicField | admecManipulus]  — COUVERT décision, combat = fold §1
```

**Synthèse AdMec** : couvert/fold = Vehicle, GalvanicField ; [opus] direct = SentinelDirectives (PORTÉ+VALIDÉ) ;
[opus]+prérequis = MasterAnnihilator, HeavyGravCannon, RadBombardment ; **[fable]** = OptimizedGait.
Transverses : canal PIERCING attaquant (HeavyGravCannon + GravitonRifle §6.10) ; sélecteur ligne
runner (RadBombardment + DarkTalonStrike §3) ; RandomAmount (OptimizedGait + Poxwalkers §2) ;
remove-effect-by-source (MasterAnnihilator). HYPOTHÈSES : trait 0xc=Mechanic ; magnitudes ConfigVar ;
cap 5456 ; for_piercing = seul canal manquant.
