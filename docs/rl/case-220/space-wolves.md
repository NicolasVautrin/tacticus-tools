> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.15 SpaceWolves (9 items, préfixe `space*` ; exclusions 1090/1113/LordOfTempests — spaceStormcaller COMPLET)

**Substrat (grep PROUVÉ)** : aucun port combat SW ; MAIS les canaux crit-chance ET crit-dmg additifs
(base.py:213/220, damage.py:292-293), hits/dmg additifs, tuile Ice (case-35) et la résolution de block
(did_block, damage.py:448) sont PORTÉS — dé-risquent la moitié des items. L'event `UnitBlocked=0x3d`
n'est PAS émis.

```
[1089 GreatFrostAxe | spaceWulfen]  — [opus] direct (le + facile)
VAs : ExecuteBehaviour @1811e3500 ; playbook @18113fbd0 (prédiction VALIDÉE 54321 s18)
Attack(RandomAmount(min,max), Piercing-80, 4 hits) & AddEffect(Ice, tuile cible + ring-1) — patron
Stormcaller inversé, 0 prérequis dur. Risques : bonus crit-sur-Ice déféré (impact coups critiques only).
```
```
[1097 Foehammer | spaceRockfist]  — [opus]+1 sélecteur
VAs : ExecuteBehaviour @1811df2d0 ; GetDeadHeroes @1811df610
Stun(cible, 1 round) + Attack(MinMax + var8 × Count(héros MORTS — AllDeadOrResurrectedUnits), Power-40,
1 hit). Prérequis : sélecteur AllDeadOrResurrectedUnits [PARTAGÉ RitesOfRestoration §1, SendInTheNextWave §2].
```
```
[SagaOfTheWarriorBorn | spaceBlackmane passif]  — [opus]+prérequis (borderline)
VAs : effet 1223 @180f6a710/@180f6a580 ; kill-ability @18119d640/@18119d740
Owner-effect Ragnar : EN CHARGE → +3 hits + +582 crit-dmg (canaux PORTÉS) ; au kill d'un Hero →
propage 1224 aux Space Wolves amis. Prérequis : gate IsCharging en canal COMBAT eager (status.py:437) ;
kill-propagation faction. Risques : attaque hors-charge doit annuler le bonus.
```
```
[1106 WarHowl | spaceBlackmane]  — [opus]+prérequis
VAs : ExecuteBehaviour @18122cfc0 ; @18122d1b0 ; effet 1222 @180f77990/@180f77ba0
Buff self + alliés melee-only (sans arme ranged, hors Summon) : +36% crit-chance +1164 flat, melee
normal only + grant Unstoppable (résidu inerte). Prérequis : sélecteur UnitsWithoutRangedWeapons ;
classe 1222. Canaux crit PORTÉS.
```
```
[HuntersBeyondDeath | spaceHound passif]  — [opus]+prérequis (borderline fable)
VAs : CreateBehaviour @180f87100 ; effets @180f50e80/@180f51170/@180f512d0 (1172/1190/1191)
3 owner-effects : +582 vs Psykers (offense) ; −ConfigVar défense des Psykers ennemis à dist<=2 (aura) ;
SUPPRESSION du splash psyker (1191) — le consommateur psyker.py:21 lit déjà has_effect(psyker, 1191)
TARGET-side mais RIEN ne le pose → inerte. Prérequis : 3 classes + matérialisation aura target-side.
```
```
[HealingBalms | spaceWolfPriest passif+active 1212]  — [opus]+prérequis (borderline fable)
VAs : triggered @180f85a50 ; active @1811e7830 ; effet 1508 @180f4eb80/@180f4ea60
Remplace l'active Heal(18) par 1212 : Heal(HealAmount trait Healer) + buffs crit 2 rounds (canaux OK)
+ effet différé 1508 (re-heal 3638 au turn-start suivant, patron LivingMetal). Prérequis : 1re active
HEAL dans ABILITY_CLASSES + formule HealAmount (Damage × max hits) + effet différé. Note : dp=False
en case-27 pour la décision — la face combat reste portable.
```
```
[AnvilShield | spaceRockfist passif]  — [fable]
VAs : @180e16340 ; ApplyIce @180e16480/@180e16500 ; ApplyStun @180e16590/@180e16680 ;
      FrozenAttackerAdvantage @180e16840/@180e168e0 (effets 1200/1201/1202)
Tout gate On(UnitBlocked=0x3d) & OwnerIsTarget : +block-dmg (1202 PORTÉ factory.py:308) ; +block-chance
conditionnel (1200, gate santé <35% abs-vs-% NON tranché factory.py:307) ; glace la tuile de
l'attaquant ; Stun l'attaquant melee. Prérequis ABSENT : DISPATCH UnitBlocked (did_block résolu mais
event jamais émis) — rejoint le vecteur ON-BLOCK du ledger (Deathwing §6.5). Validation probabiliste.
```
```
[SavageKiller | spaceHound passif]  — [fable]
Interrupt pré-ability On(0x2b) à la réaction du mouvement d'un Summon (HasTrait(target, 2) — tooltip
« When a Summon moves »). ⚠ Bloc détail absent du rapport agent (seul le classement + l'hypothèse
trait-2 rendus) — VAs à compléter au moment du port.
```
```
[1211 RitesOfMorkai | spaceWolfPriest]  — [fable]
VAs : ExecuteBehaviour @181202ca0 ; @1812031f0/@181203220 (effets 1502 Inspired / 1529)
Inspired = REVIVE-ONCE 5456 HP sur self+amis non-méca rayon-2 (rejoint le sous-système REVIVE) +
+582 aux porteurs FinalVengeance + UseNormalAttack post-cast (SortUnitsByDamageUtility). Prérequis :
revive-once partagé ; feuilles UseNormalAttack/ValidNormalAttackTargets/SortUnitsByDamageUtility.
```

**Synthèse SW** : [opus] direct = GreatFrostAxe ; [opus]+prérequis = Foehammer, SagaOfTheWarriorBorn,
WarHowl, HuntersBeyondDeath (borderline), HealingBalms (borderline) ; **[fable]** = AnvilShield
(on-block), SavageKiller, RitesOfMorkai (revive-once). Transverses : AllDeadOrResurrectedUnits ;
IsCharging combat ; dispatch UnitBlocked=0x3d ; active-heal + HealAmount (tous les Healers du roster) ;
revive-once → REVIVE. HYPOTHÈSES : trait 2=Summon, 0x3ea=Psyker (triangulés) ; faces DÉCISION des
actives non-RE'd (à faire au port).
