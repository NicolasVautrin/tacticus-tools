> Tranche de la campagne de classification
> [case-220](../case-220-classification-campaign.md) — protocole, sommaire et
> ledger §T (prerequis transverses) dans le fichier maitre.

### §6.22 AdeptusAstartes (2 items — kit astarCyrus, lineup ; DERNIÈRE tranche de la campagne)

⚠ **i2 ABSENT pour ce kit** (dump antérieur à Cyrus) — le décompilé est la SEULE source ;
point d'attention validation.

```
[1225 StrikeFromTheShadows | astarCyrus]  — [opus]+prérequis
VAs : ExecuteBehaviour @18120d660 ; effet 1549 @180f6e5c0/@180f6e490
Attack(3x Bolter) + AddEffect(1549 sur la CIBLE : vulnérabilité au ranged reçu, OwnerIsTarget &
IsRangedAttack, 1 round) + ResetMovement(caster). Template SpiritLeech (strike.py:284). Prérequis :
classe 1549 (défenseur, template factory.py:216-261) ; feuille ResetMovement [PARTAGÉE ItItches §2,
FireAndReposition §6.19]. ⚠ MAGNITUDE du malus NON localisée (pas de var dans les constants —
1 décompile de la création du modifier AVANT port ; introuvable → bascule [fable]).
Risques : direction/valeur du 1549 ; ResetMovement potentiellement no-op dans le turn-model.
```
```
[HaywireMine | astarCyrus passif (+ summon astarSmnHaywireMine)]  — [fable] (le + dur du lot)
VAs : pose 1531 @180f84e60/@180f851c0 ; explosion 1542 @180f85380/@180f85680 ; reset @180f857f0/
      @180f858a0 ; playbook évitement @181166ff0/@181166f70
Pose auto après move (gate « un seul mine » via PersistentData ; TriggerAbilityDelayed si aucune
tuile) ; le mine (Steppable) EXPLOSE à sa mort par écrasement (OnPreDeath & HasDeathReason(2)) :
Blast à l'écraseur + Energy 2 hits SI Mechanical (trait 5 PROUVÉ) ; reset au turn-start de Cyrus.
Prérequis ABSENTS : PersistentData store ; TriggerAbilityDelayed (écarté 2x par collapse —
act_of_faith.py:96) ; **OnPreDeath-depuis-crush + death-reason** : `_kill_steppable_units`
(movement.py:50) est un kill PROPRE qui ne fire AUCUN death-trigger → l'explosion ne peut pas
reposer sur l'OnPreDeath naïf (le port décoy a contourné via attribution summoner On(0x1d)) ;
contexte spawn mine (passif + Steppable + niveau Cyrus). Choix d'architecture mirror-natif vs
patron-décoy à trancher (doctrine → mirror, valider les deux faces).
```

**Synthèse AA** : [opus]+prérequis = StrikeFromTheShadows (magnitude 1549 à RE) ; **[fable]** =
HaywireMine (persistent-data + delayed + OnPreDeath-crush). Transverses : ResetMovement (3e
consommateur) ; fondation « trap/mine explose à sa mort » (OnPreDeath-depuis-crush + HasDeathReason)
— générique pour toute mécanique de mine. HYPOTHÈSES : magnitude 1549 ; death-reason 2 = crushed ;
fréquence de pose (auto/tour, inféré).
