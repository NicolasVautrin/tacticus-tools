# case-175 — `combatSnapshot` empoisonnait tout runner contenant une Machine

**Statut** : cause LOCALISEE et contournee (2026-07-28). Le correctif natif n'existe pas de
notre cote : c'est un comportement du jeu, on cesse de le declencher.

## Le symptome

Appeler le RPC `combatSnapshot` sur un runner ou une MoW est deployee rendait **toute pose
d'effet ulterieure un no-op SILENCIEUX** : `applyAction` repondait `ok=true`, l'action etait
consommee, le degat passait normalement (mesure #162 : 6180 PV identiques avec et sans), mais
`AddEffect` n'ecrivait plus rien. Ni erreur, ni exception. Non reversible — ca survivait aux
fins de tour. Ca frappait aussi les casts d'UNITE, pas seulement ceux de la MoW.

C'est un instrument de mesure qui DETRUIT ce qu'il mesure. Et c'est ce qui rendait les deux
mesures de #162 contradictoires en apparence : `live=[]` etait une empreinte d'EFFETS (bloquee)
et `live_delta=1631` un delta de PV (qui, lui, passait). Meme montage, deux observables.

## Ou ca sort, cote natif

`IdunBattle.Operations.AddEffectOperation$$Execute` a trois sorties precoces :

| sortie | trace ? |
|---|---|
| cible nulle | LOGUE |
| `IdunBattle.Entities.UnitExtensions$$HasFlag(cible, 6)` | LOGUE |
| appel d'interface **slot +0x28** sur la DEFINITION de l'effet, argument = la CIBLE | **`return 0`, MUET** |

Seule la troisieme est silencieuse — c'est donc elle. C'est le gate d'immunite
(`IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect`, porte en #137).

## La bissection — et ce qu'elle a REFUTE

Instrument : parametre de diagnostic `debugOnly` sur `combatSnapshot`, qui restreint le RPC aux
sous-lectures nommees. On teste la **suffisance** (« celle-la seule empoisonne-t-elle ? »), pas
la necessite : « tout sauf X » ne distingue pas une cause unique de causes redondantes.
Un runner NEUF par cas — la corruption etant irreversible, un runner reutilise donnerait un
faux positif a tous les cas suivants.

Rejouable : `python scripts/python/probe_175_combatsnapshot_machine.py`.

```
SANS-SNAPSHOT      POSE     (temoin +)
only=[]            POSE     snapshot sans aucun invoke natif
only=stats         POSE
only=ctrl          POSE
only=turnsFinished POSE
only=unitConfig    POSE
only=abilityStates POSE
only=normalAttack  NO-OP    <- suffit A ELLE SEULE
COMPLET            NO-OP
```

Resserrage DANS `readNormalAttack` (boutons temporaires, retires depuis) :

```
GetUnitPosition seul, sans boucle de prediction   POSE
Machine exclue comme ATTAQUANTE                   NO-OP   <- le correctif que la fiche proposait
Machine exclue comme CIBLE                        POSE    <- le correctif REEL
```

**Le vecteur est la Machine en CIBLE de `GetNormalAttackPrediction`, pas en attaquant.** La
fiche #175 recommandait de gater `readNormalAttack` sur `entityType != Machine` cote attaquant,
en raisonnant que la MoW etant hors plateau sa `UnitPosition` est vide et que l'appel ne
rapporte rien. Le raisonnement sur l'absence d'information etait juste ; la conclusion sur le
correctif etait fausse. Applique sans mesure, il aurait ferme la tache **sans rien reparer**,
et le no-op silencieux serait revenu au premier banc MoW suivant.

## Le correctif

`readNormalAttack` n'inclut plus AUCUNE entite `EntityType.Machine` parmi les cibles de
prediction. Cout fonctionnel : nul. Le degat de base d'arme est independant de la cible, et
l'attaquant conserve toutes ses cibles UNIT — y compris quand l'attaquant est lui-meme la MoW.

### Verification que le correctif n'a pas VIDE le canal

Un correctif qui fait taire le symptome en supprimant la mesure serait le meme defaut sous un
autre nom. Le probe verifie donc que `normalAttack` mesure encore : **4 lignes sur 5 portent un
`maxDmg > 0`** apres correctif. La 5e est la MoW elle-meme, dont la ligne rend
`aucune cible atteignable au deploiement` — etat qui PRECEDE le correctif (la fiche #175 le
constatait deja) et qui tient a sa position hors plateau, pas a l'exclusion des cibles Machine.

### Nature du correctif

C'est un **CONTOURNEMENT**, pas une reparation : on sait ce qui declenche, pas encore pourquoi
le natif reagit ainsi. `IdunBattleLogic.Core.Services.Caches.CachedDamagePredictionQuery$$GetNormalAttackPrediction`
n'ecrit aucun cache malgre son nom — c'est une pure delegation (slot 9 de l'interface enveloppee
puis recopie de 0xC0 octets) ; la mutation est plus bas, dans
`IdunBattle.Core.Services.DamagePredictionQuery$$GetNormalAttackPrediction`. Non explore.

## Portee — ce qui reste NON ETABLI

Tentative de generalisation sur `aiPlaybookPredict` (une unite predisant CONTRE la MoW) :
**NON CONCLUANTE**. Le RPC repond `ok:false, "target <casterId> not found"` — il ne sait pas
adresser une MoW en cible. Ce n'est pas une preuve d'innocuite, c'est une inatteignabilite.

Le premier jet de ce test comptait ce cas comme un succes : le probe voyait « la pose marche »
apres un RPC qui n'avait rien calcule, verdict indiscernable du temoin sain. La garde de
vivacite ajoutee depuis (`GEN-INERTE` si `ok:false` ou zero event) l'a attrape. **Un canal de
generalisation qui ne calcule rien vaut zero information, pas une bonne nouvelle.**

## Consequence sur le harnais

La parade « runner JUMEAU » en tete de
`scripts/python/tests/engine/runner/test_mow_effect_posers_live.py` (snapshot pris sur un runner
jumeau, dispose aussitot) reste correcte mais n'est plus necessaire. La retirer est un chantier
separe : elle ne coute qu'un build, et la garder documente le piege.
