> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.12 BloodAngels (8 items après exclusions 1163/1151/1153/1177)

**Découverte transverse #1 (PROUVÉ)** : event `On(ArrivedAtFinalTile=28)` — le flag est posé au
turn-finish (turnflow.py:48/67) et le natif publie l'event 0x1c ; le dispatch n'émet que On(4)/On(29).
Réalise le « after move, OU fin de tour si pas bougé » → débloque 3 items BA + 2 Necrons (§6.7).

```
[1230 SavageEchoes | bloodTerminator]  — [opus] direct (le + sûr)
VAs : ExecuteBehaviour @181204660 ; GetDamage @181204ab0 ; GetRegenerateCondition @181204bd0 ;
      playbook @181158870/@1811586d0
SetCache(HP<=50% AVANT l'attaque) & Attack(4x Eviscerate, dégât = MinMax + var8 × count(tuiles
adjacentes LIBRES du caster)) & If(cache, Heal(self, var 0x1d, ForRegenerate)). RÉUTILISE
ArmoriumCherubAbility.GetHits (PORTÉ, handler 1014). 0 primitive manquante. Playbook custom = tâche
décision secondaire. Risques : var8 × free-tiles ; cache lu AVANT l'attaque.
```
```
[1301 LordOfTheHost volet ExtraHit 1377 | bloodDante passif]  — [opus]+prérequis
VAs : CreateBehaviour @1811086e0 ; effet 1377 @180f57250/@180f57100 ; (1378 ExtraDamage = COUVERT
      extra_damage.py:689, factory.py:130)
1377 = stat-mod EXTRA_HITS(23) +1 hit melee, amis rayon-2 RapidAssault/Flying à <=50% PV. JUMEAU du
1378 porté + Filter(HealthPct<=50). Prérequis : canal AURA sur stat EXTRA_HITS (les auras +hit portées
ajoutent une ATTAQUE, pas un stat-mod nrOfHits). Risques : melee-only ; gate 50% re-évalué par candidat.
```
```
[1296 SanguinaryPriest | bloodSanguinary passif]  — [opus]+prérequis (le + simple des after-move)
VAs : CreateBehaviour @18119d7d0 ; CreateTrigger @18119d960 (On 28) ; GetTargets @18119d9e0
On(28) : Heal(amis adjacents non-méca, RandomAmount(1091-1601), ForRegenerate). Prérequis : vecteur
On(28) [T1]. Risques : émettre On(28) AUSSI en fin de tour sans mouvement ; RandomAmount (min pour
la prédiction).
```
```
[1175 BloodChalice | bloodSanguinary]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811bb530 ; GetTargets @1811bba00 ; effets 1368 @180f36360/@180f362e0,
      1369 @180f36060 ; playbook COUVERT (bespoke.py:41)
Amis adjacents non-méca : ChangeStat(Health = 50% de maxHP) + effet 1368 (heal 3638 quand le porteur
attaque en MELEE, target-trigger) + 1369 (+20% perce melee, stat 21), 1 round. Prérequis : 2 classes
d'effet (1368 heal-on-melee-attack ; 1369 stat-mod perce). Risques : trait 0x19=25 du filtre
(HYPOTHÈSE « Immune ») ; melee-only du 1368.
```
```
[1551 RedRampage | bloodTerminator passif]  — [opus]+prérequis
VAs : Attack @1811166f0/@181116850 (On 28) ; Buff @181116910/@181116a90/@181116c10
(a) On(28) : Attack(TOUS les ennemis adjacents, 2x Power — profil MassiveScythingTalons).
(b) On(55 UnitDefeated, PORTÉ) : +1 MOVEMENT (effet 1570, template BlackRage_ExtraMove), refresh
ChangeEffectTurns(+1) si déjà posé. Prérequis : vecteur On(28) [T1] ; effet 1570 ; ChangeEffectTurns
[partagé]. Risques : logique refresh non-infinie ; profil emprunté.
```
```
[1264 VisionsOfHeresy | bloodDeathCompany passif]  — [opus]+prérequis
VAs : CreateTrigger @1811ab540 (On 38 NormalAttack, PORTÉ) ; SelectTarget @1811ab5b0 ; effets
      1345/1346 @180e12e40/@180e12d60
Après attaque normale : 2e attaque 2x Bolter sur la MEILLEURE cible (SortTargetsByDamagePrediction,
préfère la cible courante si à portée+vivante). Owner-effects 1345/1346 : +20% perce si HP<=50%
(active-condition). Prérequis : sélecteur SortTargetsByDamagePrediction + ValidNormalAttackTargets ;
2 owner-effects à active-condition. Risques : la 2e attaque ne re-trigger pas ; bascule perce à 50%.
```
```
[1247 FuryOfTheAncients | bloodMephiston passif]  — [fable]
VAs : CreateBehaviour @180f81c40 ; CreateTrigger @180f82020 (On 28) ; @180f82270/@180f820f0/
      @180f82120 ; effet 1320 @180f4b120 ; face MOVE COUVERTE (adjacent_unit_preference.py:162)
On(28) : cible primaire = max(Sum des prédictions de dégât primaire+amis adjacents) →
ChainAttackDamage(primaire, 2e cible = ennemi adjacent-à-la-primaire, 2x Psychic) + effet 1320
« no-heal/no-revive/no-repair 2 rounds ». Prérequis ABSENTS : primitive ChainAttackDamage ;
effet SUPPRESSION-de-soin cross-cutting (hooks heal/repair/resurrect — fuite silencieuse si un canal
oublié) ; SortByFormula prediction. Risques : couvrir TOUS les canaux de restauration.
```
```
[1248 AggressiveOnslaught | bloodIntercessor passif]  — [fable] / BLOQUÉ-dépendance HammerOfWrath
VAs : CreateBehaviour @180e15270 ; CreateTrigger @180e15520 (On 11 UnitAbility & IsCharging) ;
      GetMaxSummon @180e156c0 ; face ATTACK COUVERTE (aggressive_onslaught.py)
À la CHARGE (HammerOfWrath 1153, §4 — non portée) : Spawn 2 bloodSmnIntercessor près de la cible,
attaque immédiate ; ils QUITTENT au début du tour suivant de Mataneo (persistent-data cleanup, non
RE en détail). À traiter APRÈS 1153. Prérequis : vecteur On(11)+IsCharging ; tracking + leave-at-turn-start.
```

**Synthèse BA** : [opus] direct = SavageEchoes ; [opus]+prérequis = LordOfTheHost/1377,
SanguinaryPriest, BloodChalice, RedRampage, VisionsOfHeresy ; **[fable]** = FuryOfTheAncients,
AggressiveOnslaught (bloqué 1153). Débloqueur #1 = **vecteur On(28)** (3 items BA + 2 Necrons).
NOUVEAUX transverses : canal aura EXTRA_HITS stat-mod ; ChainAttackDamage ; effet suppression-de-soin
(1320). HYPOTHÈSES : trait 0x19=25 ; cond@0xa0 SanguinaryPriest ; leave-at-turn-start ; On(11) émis
par la charge HoW.
