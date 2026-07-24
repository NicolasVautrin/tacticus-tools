> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.14 Sisterhood / Adepta Sororitas (11 items, préfixe `adept*` ; exclusions 1039/ActOfFaith)

**Constats (PROUVÉ)** : **adeptExorcist = MACHINE OF WAR** → ses 2 actives BLOQUÉES MoW.
**FireOfAbsolution = FAUX POSITIF kit-coverage** (COUVERT : fire.py + dispatch.py:329, splash 3x Flame
+ 30% ignite). ArmoriumCherub COUVERT (strike.py, handler 1014). ActOfFaith COUVERT (act_of_faith.py,
factory.py:212, validé #138/#149). **Correction registre : le tag `SkyStrike [--] NO-OP EFFECT/BUFF`
est FAUX** — c'est un charge+attaque melee.

```
[CondemnorStake | adeptCanoness passif]  — [opus] direct (le + simple)
VAs : effet 1076 @180f39600/@180f39450
ForAddition(OwnerIsActor & HasTrait(target, Psyker), ConfigVar 8) — jumeau AvalancheOfMuscle + gate
target-trait (précédent DaughterOfTheAbyss). ⚠ NE PAS coder 2183 en dur (lire la var gameconfig).
```
```
[1062 SanctorumMissile | adeptMorvenn]  — [opus] direct — PORTÉ + VALIDÉ LIVE (face COMBAT)
VAs : ExecuteBehaviour @1812041d0 ; GetAdjacentDamageTargetsAll @1812044a0 (units-only frère
      GetAdjacentDamageTargetsUnits @181204580 = Units(All)) ; face DÉCISION prediction abilities.py OK.
Arbre = ExecuteAtomic(0x56, op_BitwiseAnd(MAIN, SPLASH)) : MAIN = AttackWithAttackDamage(target, Blast,
nrOfHits=0x2f=2) ; SPLASH = AttackWithAttackDamage(GetAdjacentDamageTargetsAll(), Blast, nrOfHits_2=0x32=1).
Sélecteur splash = Unobscured(self@0x168, (Units(AdjacentTiles(target))−caster@0x160) + EmptyOrHasSteppable(
adjTiles)) → porté `Unobscured(Sub(AdjacentUnits(TargetTile()), Caster()), Caster())`. FRIENDLY-FIRE (band UNIT
sans filtre équipe, == Stikkbomb) — CONFIRMÉ LIVE (allié adjacent touché). Hex de Morvenn EXCLU (Sub(caster))
— CONFIRMÉ LIVE (Morvenn drivée adjacente, absente des cibles). native_factory="attack" @180de9fb0 (XREFS
call-sites @18120432f/@1812043cf ; ABSENT de @180de9c90/@180de9dd0 ability) — discriminant OK 2 seeds.
GAP flaggé : band TILE EmptyOrHasSteppable @180ee83e0 (tuiles vides/steppables) NON porté — inerte pour le
degat-unite en duel (frère Units(All) l'élimine déjà). Observer Unobscured 0x168 = self/owner (≠ caster 0x160
soustrait, ≠ target 0x178 centre AdjTiles) = Morvenn en cast actif ; board plat → Unobscured passe-tout.
Placement : `runner/abilities/sisterhood.py` (NOUVEAU module Sisterhood isolé) + handler 1062 ;
test `tests/engine/runner/test_sanctorum_missile_live.py`.
```
```
[1025 SkyStrike | adeptCelestine]  — [opus] direct
VAs : ExecuteBehaviour @181207d30 ; gate @1812082a0 ; playbook @18115b110
Gate « n'a PAS bougé » : charge adjacente (SortTilesByUtility(7) → collapse plus-proche) + attaque =
NormalAttackDamage + Direct(var8) — PAS config-minmax (le chemin générique donnerait 0). Template
VigilanceEternal/HeroicFusillade EXACT. Risques : base-override décision ; gate has-not-moved.
```
```
[1041 BrazierOfHolyFire | adeptCanoness]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811bde60 ; @1811be2b0/@1811be210 ; effet 1075 @180f36b60/@180f36980
Attack(Flame, hits = ConditionalAmount(cible Daemon, 4, 2)) + pose FIRE sur l'hex + effet 1075 sur
voisins Daemon 2 rounds : vulnérabilité ForPercentIncrease REÇU (+60%, +20% si Immune — précédent
MindControl 1350). Prérequis : classe 1075 ; pose Fire via AddEffect. Risques : ne pas figer hits=2 ;
1075 = vulnérabilité (OwnerIsTarget), pas un buff caster.
```
```
[MedicusMinistorum | adeptHospitaller passif]  — [opus]+prérequis
VAs : CreateBehaviour @1812231c0 ; CreateTrigger @1812232d0
Ami adjacent (pas soi) prend du dégât → Heal(873, ForRegenerate) après le coup, sauf si vaincu.
Substrat Heal/ForRegenerate PRÉSENT. Prérequis : vecteur réactif on-adjacent-friend-damaged (On(9)
côté défenseur-voisin). Risques : skip si mort ; non-Mechanical only ; fire au tour ennemi.
```
```
[RighteousRepugnance | adeptMorvenn passif]  — volet A COUVERT / volet B [opus]+prérequis
VAs : 1107 @18119cdd0 ; normal-attack 1182 @181201570/@181201de0/@1812013e0/@1812027a0
A = double-count ActOfFaith 60% melee-kill : DÉJÀ PORTÉ (act_of_faith.py:80). B = attaque normale
CUSTOM 1182 : melee → +3x Power sur cible + ennemis adjacents-aux-DEUX (sélecteur _adjacent_to_both
PRÉSENT splash.py:232). Prérequis : handler normal-attack custom (pattern MV71, damage.py:1076).
Risques : modifie le dégât NORMAL de Morvenn (régression damage) ; ne pas re-porter le double-count.
```
```
[GeminaeSuperia | adeptCelestine passif]  — [opus]+prérequis
VAs : CreateBehaviour @18121fc60 ; CreateTrigger @18121fe40 (On 58 & IsFirstDamagingHitInSeries &
      OwnerIsTarget) ; @18121ffc0/@181220040
Celestine ATTAQUÉE → Spawn adeptSmnGeminaeSuperia adjacent + TriggerAbility(Lifewards 1049), cap 2/bataille
(Count(UnitsWithId(Children))). Prérequis : vecteur réactif on-being-hit ; TriggerAbility sur spawn ;
SummonLimit. Risques : tour ennemi ; Lifewards non modélisé = agreement partiel.
```
```
[1187 ThriceBlessedConflagration | adeptExorcist MoW]  — BLOQUÉ MoW (sinon [opus]+prérequis)
VAs : ExecuteBehaviour @181215060 ; ligne @181215510/@181215610/@1812154d0 ; effets 1401/1436
      @180f73900/@180f73680/@180f73950
Buff ami (+20% ranged vs ennemis sur Fire — ALL-attacks si Adepta Sororitas [HYP faction 1]) + Flame
sur la plus longue LIGNE depuis l'ami ciblé. Géométrie ligne = tâche partagée DarkTalonStrike/
ExcruciatingFrequencies.
```
```
[1188 DevastatingRefrain | adeptExorcist MoW]  — BLOQUÉ MoW (sinon [fable])
VAs : ExecuteBehaviour @1811d3730 ; GetShape @1811d3960 ; différé @18121d5c0 ; effets 1402/1403 @180e031f0
Marque hex + 3 hexes non-mutuellement-adjacents (bond 1402) → au turn-start suivant : Blast sur les
occupants + 75% × N accumulation ActOfFaith des alliés. Rejoint le sous-système PENDING-ATTACK.
```

**Synthèse Sisterhood** : couverts = ArmoriumCherub, FireOfAbsolution, ActOfFaith, RighteousRepugnance/A ;
[opus] direct = CondemnorStake, SanctorumMissile, SkyStrike ; [opus]+prérequis = BrazierOfHolyFire,
MedicusMinistorum, RighteousRepugnance/B, GeminaeSuperia ; BLOQUÉ MoW = ThriceBlessed (+opus),
DevastatingRefrain (+fable). NOUVEAUX transverses : vecteurs réactifs défenseur ÉTENDUS (on-being-hit
On(58) IsFirstDamagingHitInSeries, on-adjacent-friend-damaged) ; effets vulnérabilité ForPercentIncrease
OwnerIsTarget (1075/1401/1436, précédent MindControl 1350) ; custom normal-attack per-unit (pattern
MV71 étendu par 1182). HYPOTHÈSES : faction 1 = AdeptaSororitas (i2) ; events On(9)/On(58) exacts ;
effets 1401/1436 non deep-read (MoW-bloqué).
