> Tranche de la campagne de classification
> [case-220](../case-220-classification-campaign.md) — protocole, sommaire et
> ledger §T (prerequis transverses) dans le fichier maitre.

### §6.21 Genestealer Cults (4 items après exclusions 1164/1166 ; genesKelermorph/genesPrimus COMPLETS)

**Substrat (grep PROUVÉ)** : spawn_decoy/build_decoy_context + _spawn_config_grot (spawn.py:118/211),
on-appearance PerformAIAttack (spawn.py:625/637), Maybe RNG-gate (behaviours.py:783), Pinned 1065
PORTÉ (factory.py:215), BattleFatigue porté, trait Decoy 1053 + énumération decoys
(triggers/genestealer.py). Tous les porteurs lineup → AUCUN blocage MoW.

```
[TwistedScience | genesBiophagus passif]  — COUVERT (décision) + résiduel combat [opus] direct
VAs : CreateBehaviour @1811a9100 (swap Heal(18) → Heal_TwistedScience 1167) ; ExecuteBehaviour
      @181217ad0 ; effet @180f75380
Décision LIVE-VALIDÉE (777 s15 : bump maxHP +2992, predict.py:200-220 ; gate HasEffect(1355)
action_generators.py:364 ; HEAL_ABILITY_IDS inclut 1167 state_bridge.py:91). Résiduel full-sim :
registrer 1167 + classes 1355/1356 (+2183 HP max&courant one-shot, +364 dmg si GSCult) +
AddDynamicStatModifierEffect. N'affecte PAS l'oracle. Risques : ne pas re-porter la prédiction.
```
```
[1165 MightFromBelow | genesPatriarch]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811f3420 ; GetPossibleSpawnTiles @1811f3900 ; playbook @18114bf20/
      @18114bda0/@18114ba60 (non porté)
5x Psychic P100 sur l'adjacent + KillDeadUnits + Spawn(genesSmnGenestealer Purestrain) sur la tuile
de CHAQUE decoy adjacent, attaque immédiate. Prérequis : SPAWN-SUR-TUILE-DE-DECOY (consomme le
decoy — transverse partagé SpiritualLeader) ; sélecteur tiles-des-decoys-adjacents. Risques : count
= nb decoys adjacents ; ordre attaque→kill→spawn ; gate IsAlive(caster).
```
```
[SpiritualLeader | genesMagus passif 1275]  — [opus]+prérequis
VAs : CreateTrigger @1811a1550 (On 28) ; CreateBehaviour @1811a1270 ; @1811a15b0/@1811a16e0
On(ArrivedAtFinalTile=28) [+ chemin fin-de-tour-si-pas-bougé, i2] : pose un DECOY sur hex libre
adjacent ; si >=2 decoys adjacents → Spawn(genesSmnNeophyte — DÉJÀ porté G4, mêmes stats) sur un
decoy random. Prérequis : vecteur On(28) [T] ; spawn-sur-decoy [partagé] ; sélecteur
GetAdjacentDecoys. Risques : seuil 2 exact ; double-déclenchement move vs fin-de-tour.
```
```
[CosmicHorror | genesPatriarch passif 1277]  — [fable]
VAs : OnKill @180e1daf0/@180e1d7e0 ; OnMove @180e1dc70/@180e1dbf0
(A) Kill par le Patermine (On 55 KILLER-side, victime non-Steppable) → decoy sur la tuile du mort +
Foreach(ennemis autour, Maybe(60%) : TriggerAbility(1025 BattleFatigue) & Pinned 1 round).
(B) Le move du Patermine CRUSHE un decoy ami → On(54 PostUnitKill) → Heal self 2910. Prérequis
ABSENTS : On(54) émis au crush (silencieux aujourd'hui, _kill_steppable_units) ; On(55) killer-side
en trait-trigger ; nœud TriggerAbility [T] ; ⚠ AMBIGUÏTÉ un-Maybe-vs-deux-gates-60% (décompilé vs
i2) → RE de l'ability 1025 OBLIGATOIRE avant port. Risques : structure des 2 gates ; ordre
crush→event→heal ; interplay BattleFatigue RNG.
```

**Synthèse GS** : couvert = TwistedScience (décision) ; [opus]+prérequis = MightFromBelow,
SpiritualLeader ; **[fable]** = CosmicHorror. Transverses : SPAWN-SUR-TUILE-DE-DECOY (2 items) ;
events decoy-liés On(28)/On(54 crush)/On(55 killer-side) à émettre depuis movement/dispatch.
HYPOTHÈSES : gates 60% x1-vs-x2 (RE 1025 requis) ; chemin fin-de-tour SpiritualLeader (2e trigger
non localisé) ; +364 GS dans la prédiction de dégât.
