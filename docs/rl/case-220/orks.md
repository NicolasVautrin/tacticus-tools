> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.13 Orks (10 items sur les 6 kits lineup ; exclusions 1058 Waaagh / 1045 GetEmRuntz COUVERT)

**Constat (PROUVÉ)** : 3 passifs quasi-couverts que kit-coverage sous-compte — **SquigHound**
(3 axes portés, gap = PerformAIAttack on-appearance du grot, dispatch.py:245), **SmashaEad** (effet
validé bit-exact damage.py:477, gap = trigger mouvement >=2 hexes côté runner, @1811a0610),
**PowerTrip** (2 axes portés+validés hits.py:652/674, gap = debuff stateful ReduceArmor 1363 +
self −5% HP). **ProperKilly** = porteur Ghazghkull NON-lineup → non-validable, hors table (note only).

```
[1057 GrotTank | orksBigMek]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811e44c0 ; TankHealth @1811e49b0
Spawn(orksGrotTank, HP = base + RoundsStarted × perRound, PerformAIAttackFromCurrentPosition,
cannot-move-first-turn). Template GetEmRuntz/ScarabHive (~90%). Prérequis : nœud RoundsStarted côté
RUNNER (décision only, active_ability.py:395) ; StatModifierFormula(Health) au spawn ; flag no-move.
Risques : off-by-one rounds (cf. Executioner #122).
```
```
[1171 DakkaDakkaDakka combat | orksKillaKan]  — [opus]+prérequis (décision COUVERTE+validée)
VAs : ExecuteBehaviour @1811d02e0 ; GetNumHits @1811d0eb0 ; GetHealthToLose @1811d09a0
Attack(cible, numHits) + réallocation des LEFTOVER hits (cible morte → ennemis within 3, arithmétique
Divide/First/PickRandomly) + self −15% maxHP. Prérequis : primitive NumLeftOverHits [PARTAGÉE
LightImUp] + sous-arbre distribution. Bascule [fable] si la distribution résiste. Risques :
ne se voit qu'en SUR-KILL (cible fragile) ; pas de double-compte avec la décision validée.
```
```
[UnstoppableMomentumReworked 1152 | orksNob]  — [fable]
VAs : driver @181228110 ; Attack @181227e20 ; SuppressOrStun @181229b00 ; Move @181229060 ;
      Push @181229240 ; GetAllTilesInLine @181228fa0
Charge en ligne IMPÉRATIVE stateful (hex-par-hex : traverse / attaque +extraDmg×hexes / BigTarget →
Stun sinon Pinned+Push / amis déplacés sans dégât). Stunned/Pinned PORTÉS. Prérequis ABSENTS :
driver de charge en ligne + Move/Push runner + scaling per-hex + displacement ami.
```
```
[KustomForceFieldReworked | orksBigMek passif]  — [opus]+prérequis
VAs : selector @180f53700 ; magnitude @180f537c0 ; ctors @180f53970/@180f53eb0/@180f53f80
Aura +Armour (i2) self+adjacents, SPLIT Ork(1567)/non-Ork(1566). Template aura FixedArmor
ProtectorImperative. Prérequis : 2 classes 1566/1567 + magnitude ConfigVar(0x60b) + seeding split-faction.
Risques : valeur par faction non extraite ; delta d'armure = signature aura.
```
```
[LightImUp | orksWarboss passif]  — [opus]+prérequis
VAs : CreateTrigger @181108250 (On 0x26, PORTÉ dispatch.py:240) ; CreateBehaviour @181107b90 ;
      @1811082b0/@1811082e0
Après CHAQUE attaque normale : 2e attaque 3x sur la même cible ; si morte → leftover vers 1 ennemi
within 3. Prérequis : NumLeftOverHits [partagé DakkaDakka] ; AttackHitsWithModifiers à vérifier.
Risques : double-tap systématique ; leftover sur kill.
```
```
[SmashaEad | orksNob passif]  — COUVERT + [opus] mineur
Effet bit-exact (extra_damage.py:41, damage.py:477) ; reste le trigger runner « a bougé >=2 hexes
ce tour » (@1811a0610 non mirroré + tracking distance).
```
```
[PowerTrip | orksKillaKan passif]  — COUVERT + [opus] résiduel
IgnoreArmor + FullHealth+1hit VALIDÉS (hits.py:652/674, magnitude.py:72) ; reste ReduceArmor 1363
(debuff stateful FixedArmor cible −364, cumulatif) + self −5% HP à full-health.
```
```
[SquigHound | orksRuntherd passif]  — COUVERT (gap mineur)
3 axes portés (factory.py:92, spawn.py:256/528, dispatch.py:240) ; gap = attaque on-appearance du
grot summoné (dispatch.py:245).
```
```
[1200 SquigLaunchas | orksRukkatrukk MoW]  — BLOQUÉ harnais MoW (sinon [opus])
VAs : ExecuteBehaviour @18120a720 ; @18120aac0/@18120aff0/@18120af30
Attack + summon Large Squig conditionnel (>=N Orks/amis adjacents à la cible). Prérequis hors MoW :
sélecteurs HasMinimumAdjacentOrks/FriendlyUnits.
```
```
[1201 SquigMine | orksRukkatrukk MoW]  — BLOQUÉ MoW + [fable]
VAs : ExecuteBehaviour @18120b350 ; tile-effect 1441 @180f6d390/@180f6d660/@180f6d590/@180f6d790
Pose 1+4 mines (hexes random rayon-2) ; détonation Blast on-enemy-enter, clear-on-friend. Infra
tile-effect EXISTE (ContaminatedTile/FireTile) mais l'effet 1441 + marquage multi-hex + détonation =
sous-système mines.
```

**Synthèse Orks** : quasi-couverts = SquigHound, SmashaEad, PowerTrip ; [opus]+prérequis = GrotTank,
KustomForceFieldReworked, LightImUp, DakkaDakkaDakka ; **[fable]** = UnstoppableMomentum ; BLOQUÉ MoW =
SquigLaunchas, SquigMine (+fable). **Levier #1 faction = NumLeftOverHits** (DakkaDakka + LightImUp).
NOUVEAUX transverses : RoundsStarted runner ; charge-driver en ligne (Move/Push impératif) ; système
mines par occupation. HYPOTHÈSES : flag no-move GrotTank ; trigger SmashaEad exact ; extraArmor KFF
par faction.
