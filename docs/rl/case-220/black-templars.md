> Tranche de la campagne de classification
> [case-220](../case-220-classification-campaign.md) — protocole, sommaire et
> ledger §T (prerequis transverses) dans le fichier maitre.

### §6.20 BlackTemplars (9 items, préfixe `templ*` ; exclusion 1050 HolyDuel)

**Constats (PROUVÉ)** : COUVERTS = **ThunderousAssault 1043** (handler.py:25, validé live) et
**AstartesBanner** (hits.py:618, validé live seed999). Aucune des 3 actives restantes dans
ABILITY_CLASSES, aucun passif dans les registres triggers ; faces DÉCISION des actives 1061/1049
ABSENTES (playbooks natifs @18117d970/@181126ba0 non portés). Ids vérifiés : Immune=25, Hero=16,
Imperial=26, Psyker=1002 ; stat EXTRA_PIERCE_MELEE=21, Armour=16.

```
[1049 CrusadeOfWrath | templHelbrecht]  — [opus]+prérequis (le + mécanique)
VAs : ExecuteBehaviour @1811ccf20 ; GetBuffTargets @1811cd420 ; décision NC @181126ba0 (non portée)
Amis rayon-2 (excl. self) : +364 Damage (1086) + +24% EXTRA_PIERCE_MELEE (1087), 2 rounds ; puis
attaque normale gratuite sur un adjacent random (UseActiveAbility PORTÉ). Prérequis : feuille
AddStaticStatModifierEffect sur SÉLECTEUR (2 classes 1086/1087) ; face DÉCISION NC. Risques :
durée 2 rounds ; excl-self ; skipEndTurn de l'attaque gratuite.
```
```
[ChampionOfTheFeast | templSwordBrother passif]  — [opus]+prérequis
VAs : CreateTrigger @180e1cc30 (On 28) ; CreateBehaviour @180e1c8d0 ; effet @180f384c0
On(ArrivedAtFinalTile=28) : attaque un adjacent (préférence non-Immune, Otherwise fallback) + si
survit → debuff −728 Armour PERMANENT (1083). Prérequis : vecteur On(28) [T structurant] ;
AddStaticStatModifierEffect. Risques : émettre On(28) AUSSI sans mouvement ; durée 0 = permanent.
```
```
[Boltstorm | templAggressor passif]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811bc6e0 ; @1811bd8b0/@1811bcf60/@1811bceb0/@1811bd7e0 ; décision PORTÉE
      (prediction.py:346)
ATTAQUE NORMALE CUSTOM : en position ranged → 3x Bolter sur cible + ennemis adjacents-cible
non-obscurés + Suppress ; en melee → pipeline normal. Template MV71 (damage.py:1073, pattern
custom normal-attack [T]). Prérequis : special-case combat + Unobscured côté combat. Risques :
ne pas double-compter avec la prédiction portée.
```
```
[DestroyTheWitch | templHelbrecht passif]  — [opus]+prérequis
VAs : CreateBehaviour @180e20b90 ; ExtraMove @180f3f2f0 ; ExtraDamage @180f3f2a0/@180f3efb0/
      @180f3f220/@180f3f050
+1 Movement (1088) + AURA self+adjacents (1089) : +1091 melee FLAT vs cibles PSYKER, ActiveCondition
= au moins 1 ennemi Psyker en jeu. Templates BeastSlayer (trait-cible) + AstartesBanner (aura).
Prérequis : 2 classes + AddStaticStatModifierEffectToOwner. HYPOTHÈSE : le +1 Move gate-t-il aussi
sur Psyker-présent ? (pas de CreateActiveCondition explicite au ctor).
```
```
[1061 UnbreakableDuty | templAncient]  — [opus]+prérequis
VAs : ExecuteBehaviour @1812191d0 ; GetAmountOfDeadImperialUnits @181219800 ; effet 1097
      @1812278a0/@181227700 ; décision NC @18117d970 (non portée)
Aura −33% reçu self+amis-r2 1 round (1097 = clone EXACT VexillaMagnifica, damage_reduction.py:88) ;
si >=2 Imperial-HERO morts : +7275 Health (max ET courant : AddStatMod + ChangeStat) + +1455 Damage
+ attaque normale gratuite. Prérequis : classe 1097 (template direct) ; AddStaticStatModifierEffect
ToOwner ; sélecteur count dead-Imperial-Hero ; décision NC. Risques : gate Imperial ET Hero ; balloon
double ; 4e arg UseActiveAbility = literal 69 (HYPOTHÈSE vs UnitNormalAttackType).
```
```
[1048 FragstormGrenadeLauncher | templAggressor]  — [opus]+prérequis (candidat fable)
VAs : ExecuteBehaviour @1811e1060 ; GetOtherTargets @1811e1470 ; playbook @18113ce50
ChainLeftOverHitsAttackDamage(target, 6 hits Blast, report kill-priority sur les ennemis rayon-2
triés Health puis DamagePrediction). MÊME feuille que MultiThreatEliminator/BloodyFury [T]. ⚠ Le
summon Fragstorm 1078 porté (splash.py) est un arbre DIFFÉRENT — aucun reuse. Risques : ordre
hits/kills/re-ciblage/RNG.
```
```
[MartialSuperiority | templChampion passif]  — [fable]
VAs : CreateTrigger @18110b7e0 (On 0x2b=43 PreUnitAbility) ; CreateBehaviour @18110b620 ; @18110b920
CONTRE-ATTAQUE 2x Power AVANT que l'attaque melee ennemie ne résolve — si l'attaquant meurt,
l'attaque est ANNULÉE. Behaviour triviale ; le vecteur pré-ability + annulation = primitive d'ORDRE
D'EXÉCUTION neuve, partagée SwornProtector [T]. Risques : timing « avant » ; melee-only ; tour ennemi.
```
```
[1043 ThunderousAssault]  — COUVERT (handler.py:25)   |   [AstartesBanner]  — COUVERT (hits.py:618)
```

**Synthèse BT** : couverts = ThunderousAssault, AstartesBanner ; [opus]+prérequis = CrusadeOfWrath,
ChampionOfTheFeast, Boltstorm, DestroyTheWitch, UnbreakableDuty, Fragstorm (candidat fable) ;
**[fable]** = MartialSuperiority. **Levier #1 faction = feuille AddStaticStatModifierEffect
(ToOwner/sélecteur)** (4 items BT + DoomSiren/LeadingTheCharge/TrophyTaker §T). Le vecteur On(28)
et ChainLeftOverHits rejoignent leurs familles §T. HYPOTHÈSES : arg 69 UnbreakableDuty ; gate du
+1 Move DestroyTheWitch ; faces DÉCISION à re-vérifier au port.
