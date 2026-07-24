> Tranche de la campagne de classification
> [case-220](../case-220-classification-campaign.md) — protocole, sommaire et
> ledger §T (prerequis transverses) dans le fichier maitre.

### §6.16 Tyranids (10 items, préfixe `tyran*` ; exclusion 1121 ItItches ; AUCUN porteur MoW)

**Constat (PROUVÉ)** : le registre sur-reporte — DÉJÀ COUVERTS : SpiritLeech 1104 (strike.py:169,
handler 35), CrushingClaws 1105 (splash.py:351), FeederTendrils (extra_damage.py:111), Neuroparasite
(damage_reduction.py:215, validé bit-exact #86), GuardianOrganism (damage_reduction.py:156, validé
#89/#91). ScythingTalons 1065 du summon tyranSmnWarrior PORTÉ (splash.py:494) → le summon
d'AlphaWarrior est fonctionnel. **AlphaWarrior 1112 PORTÉ COMBAT + validé LIVE bit-exact (tyranids.py).**
Restent 5 items ([opus]+prérequis / [fable]), tous ABSENTS des registres.

```
[1145 SporeMineLauncher | tyranBiovore]  — PORTÉ (COMBAT) + validé LIVE (tyranids.py ; handler 1145)
VAs : ExecuteBehaviour @18120a3f0 ; gate @18120a590 ; corps-frère @1811b0550 (Aberrant/Ironkin)
Spawn(tyranSmnSporeMine, TUILE-CIBLE directe, WithStatsFromConfig) — pas d'on-appearance, pas de cap.
RE : @18120a3f0 == structure Spawn de @1811b0550 (Aberrant/Ironkin live-validé) MOINS le volet
on-appearance (PerformAIAttackFromCurrentPosition + *(options+0x18)=onAppearance ABSENTS ici) — vérifié
par comparaison des deux décompilés. gate @18120a590 : tuile valide ssi PAS occupée par un ennemi.
Feuille SpawnSporeMine -> _spawn_config_grot (Operation live-validée par ScarabHive/Aberrant/Ironkin).
VALIDATION LIVE (Biovore SPAWNABLE en MoW `--p-mow tyranBiovore`) : cast natif spawn UN tyranSmnSporeMine
sur la tuile ciblée, hp=summonHp[50]x150%=1664 BIT-EXACT vs port, owner=(team1,player3), 0 dégât
on-appearance, gate exclut les tuiles ennemies. 2 boards/tuiles (C4_41 (3,2) ; pool (0,1)) + test committé
test_spore_mine_launcher_live.py (3 tests PASS). Décision NC playbook @18115d8f0 = tâche PLAYBOOK séparée.
⚠ RÉSIDU (hors périmètre COMBAT) : le spore mine est INERTE offline tant que son passif de détonation
FloatingDeath (kit summon SÉPARÉ) n'est pas porté — l'ability exécute (mine posé, PV réels) mais l'AoE
downstream = 0. tyranSmnSporeMine n'ayant NI arme NI ability active (summonDmg=0), rien d'observable hors
son existence. Port FloatingDeath = tâche summon-downstream séparée (cf. Transverses ci-dessous).
```
```
[1112 AlphaWarrior | tyranWingedPrime]  — PORTÉ (COMBAT) + validé LIVE bit-exact (tyranids.py ; handler 1112)
VAs : ExecuteBehaviour @1811b1400 ; GetSummonId @1811b15c0 ; IsInSynapseRange @1811b15f0/@1811b1620 ;
      GetDynamicInvalidTargetReason @1811b1590 ; ctor @1811b1930
Spawn(tyranSmnWarrior, TUILE-CIBLE directe, onAppearance=PerformAIAttackFromCurrentPosition) — TEMPLATE EXACT
AberrantHypermorph @1811b0550 (Spawn tile-target + WithStatsFromConfig + on-appearance), à TROIS détails près
(vérifiés par comparaison des deux décompilés) : config AlphaWarrior ; nœud amount de WithStatsFromConfig = null
(vs AbilityLevelAmount) — le level qui indexe summonHp/summonDmg/summonArmor vient du contexte d'ability du
caster, PAS de ce nœud (confirmé BIT-EXACT live) ; sujet on-appearance = Spawned@0x180 (vs Target@0x178,
résolvent au MÊME summon, cf. MasterOfTheTutelaries). ctor @1811b1930 : AActiveAbility.ctor(..., 2, 0)
(IDENTIQUE Aberrant/Spore → flags de tour défauts, 1112 hors frozensets base.py → termine le tour + pose
ActiveAbilityUsed). Feuille `SpawnAlphaWarrior` → `_spawn_config_grot` (Operation live-validée) + on-appearance
`perform_ai_attack_from_current_position` (arme par distance : summon a melee 3-hit Physical + ranged r2 3-hit Bio).
Gate de légalité IsInTeamSynapseRange (GetDynamicInvalidTargetReason @1811b1590 → IsInSynapseRange →
DSLFactory.IsInTeamSynapseRange : tuile valide ssi dans la portée synapse de l'équipe) = ciblage live/RPC, HORS
ExecuteBehaviour → ABSENT du port COMBAT (IA sur-permissive, comme SporeMineLauncher/obscuring — résidu documenté).
NOTE visualId : le natif Spawn reçoit le constant config "tyranSmnWarrior" (== GetSummonId), mais la résolution
DOWNSTREAM (SpawnUnitBehaviour, HORS ExecuteBehaviour) spawn la variante NPC "tyranNpc4Warrior" (MÊME kit —
mêmes armes/abilities/passifs, SEULE diff : pas de trait `Summon`) → le port mirror l'ExecuteBehaviour (spawn
"tyranSmnWarrior") ; stats depuis la config d'ABILITY = bit-exact quel que soit le visualId.
VALIDATION LIVE (tyranWingedPrime SPAWNABLE en p-unit `--p-units tyranWingedPrime`) : cast tile-target natif
spawn le summon sur la tuile ciblée, hp=summonHp[50]×180%=7976 BIT-EXACT vs port (event `appeared.hpAfter`),
owner=(team1,player3)=caster, atk=summonDmg[50]×180%=2992 ; on-appearance = le summon attaque l'ennemi à portée
(melee r1 adjacent OU ranged r2), l'ennemi perd des HP (live + offline). Généralisation vérifiée : ennemi dist=2
→ attaque ranged Bio ; dist=3 (hors portée max r2) → no-op fidèle. Test committé test_alpha_warrior_live.py
(4 tests PASS : FACE1 port offline, FACE2 spawn live bit-exact, FACE2bis on-appearance live, no-op).
Décision NC playbook (`AlphaWarriorPlaybook.ShouldEvaluate @18111af90` = should_evaluate _turns_started_gate DÉJÀ
PORTÉ _base.py:140 ; EvaluateNonComparable @18111ab90) = tâche PLAYBOOK séparée.
⚠ RÉSIDU (hors périmètre COMBAT) : le summon `tyranSmnWarrior/tyranNpc4Warrior` a son propre kit (ScythingTalons
1065 PORTÉ splash.py:494, passif ReinforcedHiveNode non porté) — son ability active et son mouvement instinctif
aux tours SUIVANTS ne sont pas rejoués offline (aucun consommateur runner), mais l'attaque à l'apparition (le
volet de CET ExecuteBehaviour) est fidèle. Gate synapse ABSENT = seul écart (ciblage, pas COMBAT).
```
```
[1204 BarbedOvipositor | tyranParasite passif]  — [opus]+prérequis
VAs : CreateTrigger @180e17f40 ; CreateBehaviour @180e17dc0 ; playbook @181164070
Kill par le Parasite → Spawn(tyranSmnRipperSwarm) sur la tuile du mort (.Otherwise adjacent).
Prérequis : vecteur On(UnitDeath=0, owner=TUEUR) — le dispatch a On(1)/On(55) victime-side seulement
[famille kill-events killer-side, ledger §T] ; spawn-sur-dead-tile (.Otherwise pattern spawn.py:624).
HYPOTHÈSES : exclusions trait 5 / ability 1080.
```
```
[1192 SynapticLinchpin | tyranWingedPrime passif]  — [opus]+prérequis
VAs : CreateTrigger @1811a2f70 ; CreateBehaviour @1811a2bf0
Un allié SYNAPSE (trait 2024) fait une attaque normale → Repeat(16) : spawn tyranSmnHormagaunt près
de la cible jusqu'au cap maxSummons[level] (var 0x31), chacun attaque (UseNormalAttackIfAble).
Prérequis : trigger réactif cross-unit (owner≠actor, gates trait+amitié sur l'ACTEUR) ; behaviour
repeat-until-cap réutilisable (aujourd'hui bespoke spawn.py:583 ControlEdict/PileIn).
Risques : vérifier var 0x31 = CAP TOTAL (pas +N par trigger).
```
```
[1115 FearOfTheUnseen | tyranDeathleaper]  — [opus]+prérequis (escalade [fable] sur le volet flee)
VAs : ExecuteBehaviour @1811dd1d0 ; @1811dd5c0 ; effets 1238 @180f488b0 / 1239 @180f487a0
      (CreateAdditionalHits @180f485c0) ; pathfinder @180f1a240
⚠ Tag roadmap « DAMAGE(DirectDamage) » TROMPEUR : AUCUN dégât direct — teleport + Pinned(1065 PORTÉ)
aux ennemis rayon-2 + TriggerAbility(ennemis, 1025 BattleFatigue) on-demand + self-buffs 1238
TeleportingIn (template 1035) et 1239 +3 hits DirectDamage sur l'attaque SUIVANTE (canal hits.py).
Prérequis : classes 1238/1239 ; sélecteur NonSteppableOrObjectUnits ; TELEPORT du caster (pas dans
l'ExecuteBehaviour — framework teleport-strike à confirmer) ; TriggerAbility-BattleFatigue on-demand
(= le point dur). Validation MULTI-STEP (attaque au tour suivant).
```
```
[1144 BioMinefield | tyranBiovore]  — [fable]
VAs : ExecuteBehaviour @1811b9310 ; @1811b98b0/@1811b99e0/@1811b91f0/@1811b9230/@1811b97c0 ;
      effet 1315 ; utility 61 PORTÉE (tile.py:462)
Cycle re-cast : sous le cap(3) → spawn une mine (RandomAdjacentFreeTile) ; au cap → PerformAIMovement
(les mines bougent vers l'ennemi) + Kill(Filter(mines, HasAdjacentEnemies)) = DÉTONATION d'unités
VIVANTES. Prérequis ABSENTS (>=4 neufs) : PerformAIMovement ; RandomAdjacentFreeTile ; Kill-self-
destruct (≠ KillDeadUnits) ; HasAdjacentEnemies ; EntitiesWithoutEffects en feuille ; marqueur 1315.
Même dépendance FloatingDeath que SporeMineLauncher.
```

**Synthèse Tyranids** : couverts = SpiritLeech, CrushingClaws, FeederTendrils, Neuroparasite,
GuardianOrganism, **SporeMineLauncher (PORTÉ COMBAT + validé LIVE bit-exact, tyranids.py)**,
**AlphaWarrior (PORTÉ COMBAT + validé LIVE bit-exact, tyranids.py)** ; [opus]+prérequis =
BarbedOvipositor, SynapticLinchpin, FearOfTheUnseen (escalade possible) ; **[fable]** = BioMinefield.
Transverses : repeat-until-cap spawn générique (SynapticLinchpin + BioMinefield) ; trigger réactif
cross-unit ; **kits de summons Tyranides downstream** (tyranSmnSporeMine.FloatingDeath,
tyranSmnRipperSwarm.Burrowers, tyranSmnHormagaunt.AdrenalGlands) = tâche séparée sans laquelle les
spawns exécutent mais les effets aval = 0. HYPOTHÈSES : trait 5 / ability 1080 (BarbedOvipositor) ;
effet 25 (BioMinefield) ; chemin teleport FearOfTheUnseen.
