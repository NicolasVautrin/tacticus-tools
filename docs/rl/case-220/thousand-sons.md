> Tranche de la campagne de classification
> [case-220](../case-220-classification-campaign.md) — protocole, sommaire et
> ledger §T (prerequis transverses) dans le fichier maitre.

### §6.18 ThousandSons (9 items, préfixe `thous*` ; exclusions kit Abraxas #202 / 1100 SorcerousFacade)

**Constats (PROUVÉ)** : les 5 actives (1102/1088/1101/1208/1209) ABSENTES d'ABILITY_CLASSES →
NO-OP combat réel. **ArcaneShield = COUVERT** (arcane_shield.py, #149 slice-23). Le substrat #202
(dict psychic-damage-this-turn : components.py:46, damage.py:206-210, reset turnflow.py:205 ;
sélecteur sœur UnitsThatTakenDamageThisTurnSelector @180f2e230) dé-risque 3 items.

```
[RealityUnbound | thousTzaangor passif]  — [opus]+prérequis (le + léger)
VAs : CreateBehaviour @1811162a0 ; ExtraMaxDamage @181116530/@181116440/@181116620
3+ ennemis distincts ont subi du Psychic ce tour → +1 Move (1205) +1 Range (1206) 1 tour ; par
ennemi distinct → +181 MaxDamage (1207, stacking). AddStaticStatModifierEffect PORTÉ ; comptage =
patron WeaverOfFate (#202). 0 primitive nouvelle. Risques : ranged only ; per-ennemi-DISTINCT ;
stat 0x19=MaxDamage (pas Attack).
```
```
[1102 Doombolt | thousAhriman]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811d55b0 ; GetTargets @1811d62e0 ; NrOfHitsFormula @1811d6390 ;
      reset @180e20fe0
hits = Min(base + Count(hexes en FEU), 9) DISTRIBUÉS ÉGALEMENT entre <=3 cibles
(SortUnitsByDamageUtility 0x22 ; hits%N premières = hits/N+1). Reset : kill à l'attaque normale →
ré-arme. Primitives Min/Sum/Count/EntitiesWithAnyEffect(5)/Sort PORTÉES. Prérequis : helper
distribution-égale de N hits ; trigger Doombolt_Reset. Risques : effets 5 vs 6 dans le fire-count ;
tie-break du tri.
```
```
[1088 HellfyreMissileRack | thousTerminator]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811e83c0 ; GetAffectedUnits @1811e8710
1x HeavyRound à la cible (range 3) + 1x à CHAQUE ennemi ayant subi du PSYCHIC ce tour (cible
re-touchable). Prérequis : sélecteur HasTakenDamageOfDamageProfileThisTurn (wrapper MINCE sur le
dict #202 — coût faible) [partagé InfernalCannon] ; nœuds AbilityDamage + SortedAttackSeries
[partagé FragBomb §6.2]. Risques : double-compte de la cible.
```
```
[PsychicStalk | thousAhriman passif]  — [opus]+prérequis (aura = risque → possible [fable])
VAs : ApplyFireTile @1811151e0/@181115240 ; effets @180f66cd0/@180f66f50 ; conditions
      @180f5f0c0/@180f5f1d0
(1) Attaque normale ranged d'Ahriman → met les hexes des cibles EN FEU (AddEffect Fire PORTÉ).
(2) +33% dégât self si profil Flame|Psychic ET cible sur tuile en feu. (3) AURA +364 flat aux
alliés CHAOS mêmes conditions (create_aura PORTÉ damage_model.py:167). Prérequis : gate
cible-sur-tuile-en-feu dans les hooks bonus. Risques : l'aura (statDelta inexpliqué historique) ;
condition évaluée au calc-time.
```
```
[TimeFlux | thousTerminator passif]  — LES DEUX VOLETS SONT PORTÉS ET VALIDÉS LIVE
VAs : CreateBehaviour @1811a8690 ; CreateTrigger @1811a8850 ; ReviveAbility @1811a88a0 (effet 1186)
Regen turn-start = Heal(self, Min(873 + LastHitDamageTakenLastTurn, 4365), ForRegenerate) — LIVRÉ
(#133, `triggers/loki/time_flux.py`). TIME GHOST + REVIVE at-position — LIVRÉ (#213,
`triggers/loki/ghost_revive.py`) : le classement [fable] « substrat neuf » est PÉRIMÉ, les trois
pièces (vecteur On(PreUnitMove), effet porté par une TUILE, `SetRevivePosition`) ont été portées
d'affilée. Correctif de RE : le ghost est posé sur `CurrentTurnStartTile` (`UnitComponent+0x18c`),
PAS sur « l'hex quitté » ; le PV de résurrection est `3290 = round(hp[L50] x 180 %)` au rank 17
(2401 est la valeur L65 du tooltip). Détail : `case-66-revive-in-place` §8.2.
```
```
[1101 AttemptedPossession | thousSorcerer]  — [fable]
VAs : ExecuteBehaviour @1811b7530 ; @1811b7e00/@1811b7d20 ; effet Possessed
      @180f326b0/@180f32a70/@180f32850
POSSÈDE la cible + ses Summons : bond 1209 + PerformAIAbility(possessedSet — unités ENNEMIES
arbitraires, MOVE puis attaque la cible préférée) + override dégât PercentageOfAttackCappedAtMax
(cap 4001, PORTÉ quickening.py). Prérequis ABSENTS : PerformAIAbility GÉNÉRALISÉ (le porté =
grot-spawn only) + move-before-attack + GetPreferredAttackTarget. Plus dur que MindControl.
Dépend du chantier P1 PerformAIAction.
```
```
[1209 InfernalCannon | thousDaemonPrince MoW]  — BLOQUÉ harnais MoW
VAs : ExecuteBehaviour @1811ea7b0
Flame sur les ennemis (rayon 3) sur tuile en feu OU ayant subi du Psychic ce tour + pose Fire.
Behaviour quasi-mécanique une fois HasTakenDamageOfDamageProfileThisTurn porté — mais case-172 :
le moteur ne capture pas EntityType.Machine.
```
```
[1208 AetherStride | thousDaemonPrince MoW]  — BLOQUÉ MoW + multi-hex
VAs : ExecuteBehaviour @1811b0d10 ; GetTargetAreaTiles @1811b12b0
JUMEAU EXACT de DutyEternal (case-219 §5) : RemoveMachine + Spawn(ThreeTileUnitSpawnShape) +
transfert questUnitId + Stationary + HunterOfSouls conditionnel. Double blocage (MoW + footprint
multi-hex).
```

**Synthèse TS** : couvert = ArcaneShield ; [opus]+prérequis = RealityUnbound (le + léger), Doombolt,
HellfyreMissileRack, PsychicStalk (aura à risque) ; **LIVRÉ** = TimeFlux (regen #133 + ghost-revive
#213) ; **[fable]** = AttemptedPossession ; BLOQUÉ MoW = InfernalCannon, AetherStride. Transverses :
HasTakenDamageOfDamageProfileThisTurn (wrapper dict #202, quasi-gratuit) ; distribution-égale de
hits ; PerformAIAbility généralisé (unités ennemies + move). HYPOTHÈSES : stats 0x18/0x19 ; effets
5 vs 6 ; move des summons possédés ; logique ghost non isolée (LEVEE #213 : le ghost EST isole, cf. case-66 §8.2).
