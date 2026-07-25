> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.4 EmperorsChildren (10 items, namespace natif « Loki » ; ThrillSeekers exclu)

Toutes les 5 actives sont `[--]` (les playbooks natifs Euphoric/DaemonicPatrons/DoomSiren/Lash
existent → face DÉCISION à porter en parallèle ; seule ExcruciatingFrequencies a déjà
`playbook/excruciating_frequencies.py`). **TerrifyingCrescendo_ExtraDmgEffect 1424 DÉJÀ porté/validé
#204** — seule la pose manque.

```
[TerrifyingCrescendo | emperNoiseMarine passif]  — **PORTE + VALIDE LIVE (#222)**
VAs : @1811a3840/@1811a3910 ; effet @180f715e0/@180f4ae70
Trigger = overkill OR pose-de-Pinned(1065) par le porteur (On 0x3e=62) → AddEffectOrIncreaseLevel
(1424, +218/stack, cap 6). Prérequis LEVES : factory AddEffectOrIncreaseLevel + vecteurs On(0=UnitDeath)
et On(0x3e=PreEffectAdded)&TriggeringEffectIs. Port : triggers/loki/terrifying_crescendo.py.
Live 8 tirs suppress : stack 1..6 puis cap ; offline identique. Branche OVERKILL non exercee (residu).
cf. case-222-maillons-de-pose.md §3.
```
```
[1196 LashOfTorment | emperLucius]  — [opus]+prérequis (PullUnitOneTile)
VAs : ExecuteBehaviour @1811edc60 ; playbook @181148dc0
Attaque 6x Eviscerate + PULL 1 hex (If IsAlive) + Taunt bond si adjacent (3 rounds var 0x68).
Prérequis : PullUnitOneTile = symétrique du push DisplaceUnitOperation @180e685a0 (toward-pusher).
Risques : parité even-q (hexgeo) ; taunt évalué APRÈS le pull.
```
```
[1198 EuphoricStrikes | emperExultant]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811d9080 ; effet 1429 @180f43170/@180f42e80/@180f43080 ; playbook @18112fa70
Attaque Power 1 hit + effet 1429 sur la CIBLE : « prochaine attaque CONTRE elle ce tour = +30% crit »,
consommable one-shot (CreateRemoveEffectTrigger). No-end-turn. Prérequis : canal crit-reçu one-shot
consommable + SetsEndTurnFlags. Risques : +30% seulement au 1er coup suivant, par un attaquant TIERS.
```
```
[1197 ExcruciatingFrequencies | emperNoiseMarine]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811d9360 ; GetAffectedTiles @1811d9730 ; @1811d9840/@1811d9dc0 ;
      playbook @18112fe70/@181130060
Ligne de 3 tuiles (1 des 6 directions) → self-crit-buff transient (+var 0x41 x count unités, posé
puis RETIRÉ après l'attaque) + attaque Blast multi. Prérequis : GetAffectedTiles (géométrie ligne —
probablement déjà côté décision) + stat-mod self transient. Risques : bit-exactness du crit pendant
l'attaque ; choix de direction.
```
```
[1199 DoomSiren | emperKakophonist]  — attaque [opus] / buff overkill [fable]
VAs : ExecuteBehaviour @1811d5140 ; playbook @18112d180/@18112cd30
Attaque 3x DirectDamage sur cible + ≤2 adjacents PickRandomly (template plasma_grenade) ; puis
Foreach(UnitsDamagedThisPhase, If(IsDead & Overkill flag 8, AddStaticStatModifierEffect self 1431
stat 0x11 : +1 hit aux attaques NORMALES, reste de la bataille, accumulé)).
Prérequis : UnitsDamagedThisPhase ; canal « modificateur de nrOfHits d'attaque normale ».
Risques : RNG PickRandomly(2) ; canal nrOfHits jamais touché.
```
```
[EcstaticSlaughter | emperFlawlessBlade passif]  — [opus] (prérequis ThrillSeekers LEVÉ)
VAs : @180e222f0/@180e225a0 ; @180e228c0/@180e227c0/@180e228f0
Trigger = gain de Thrilled(1434) OU kill-overkill ennemi adjacent → attaque 3x Eviscerate sur
First(SortUnitsByDamageUtility(Randomize(adjacents))) + Taunt bond 1 round.
Prérequis restant : SortUnitsByDamageUtility+First (collapse impératif type
_black_rage_charge_positions). La branche Thrilled est DÉBLOQUÉE — `case-thrillseekers` a porté
l'effet 1434 (pose + refresh + expiration, validés live) ; TargetIsOverkilled = ev.overkill (déjà
dispatché). ⚠ `emperFlawlessBlade` n'est PAS dans le pool spawnable du rank 17 : validation live à
re-vérifier avant de porter (les 2 porteurs confrontables sont emperKakophonist/emperNoiseMarine).
```
```
[ObsessiveAnnunciation | emperKakophonist passif]  — ExtraDmg [opus] / crit-overkill [fable]
VAs : @180f5ca60 ; @180f5c7e0/@180f5c9d0/@180f5ca10 ; OverkillAbility @18110f740/@18110f7b0
Aura sur ennemis adjacents : 1432 = +800 REÇU des attaques RANGED amies (jumeau DaughterOfTheAbyss
en FLAT) ; 1433 = +800 crit-dmg REÇU d'alliés Chaos, gate marqueur overkill self.
Prérequis : classes 1432/1433 ; canal AURA-CRIT-DÉFENSE (inexistant) ; marqueur overkill.
```
```
[1203 DaemonicPatrons | emperFlawlessBlade]  — [fable]
VAs : ExecuteBehaviour @1811cff80 ; effets @180f2f960/@180f2f8a0/@180f3be20/@180f3c270 ;
      Finale @180e1f1c0/@180e1f330/@180e1f430
Taunt bond + 2 self-effects « watched » à magnitude PAR-ennemi-taunted-adjacent (+364 dmg / −30%
reçu) ; Finale = recast si kill taunted-adjacent pendant watched, sinon −30% HP self.
Prérequis ABSENTS : état watched multi-tour ; magnitudes dynamiques ; re-trigger recast.
```
```
[RefusalToBeOutdone | emperExultant passif]  — [fable]
VAs : @181117210/@181117450 ; @181117670/@1811177c0/@181117d70/@181117f10 ; @181117cb0/@181118370 ;
      reset @181118490/@181118610
État « Outrage » accumulé PER-AMI (SavedDamageForFriend, hits non-Psychic d'amis Chaos près de
Laviscus) → Damage +120% Outrage + crit-dmg dynamique ; reset fin-de-tour/après attaque.
```
```
[ArmourOfShriekingSouls | emperLucius passif]  — [fable], le plus lourd de la faction
VAs : @180e174a0/@180e17740/@180e17810 ; effet 1423 @180f32360/@180f31f20/@180f32310/@180f32150
À la mort de Lucius : pose Elated(1423) sur le tueur = DoT start-of-turn 1091-1455 + trigger de
RÉSURRECTION différée (le tueur meurt/part → Lucius revit à maxHealth PARAMÉTRÉ 6548 sur le dernier
hex du tueur, gate IsTeamDefeated). Prérequis ABSENTS : feuille DSLFactory.Resurrect (+ HP-cible
paramétré + FreeTilesOrAdjacentFreeTiles) ; death-trigger self ; effet porteur de son propre trigger.
```

**Synthèse EC** : [opus]+prérequis = TerrifyingCrescendo, LashOfTorment, EuphoricStrikes,
ExcruciatingFrequencies, EcstaticSlaughter (+ moitiés opus de DoomSiren/ObsessiveAnnunciation) ;
**[fable]** = DaemonicPatrons, RefusalToBeOutdone, ArmourOfShriekingSouls (+ moitiés fable DoomSiren
extra-hit, ObsessiveAnnunciation crit). HYPOTHÈSES : magnitudes config par index ; stat 0x11=17 ;
SuppressiveFire pose bien Pinned 1065 en combat (requis par TerrifyingCrescendo branche 2).
