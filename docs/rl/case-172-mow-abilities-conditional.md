# Case #172 — Harnais oracle MoW (aiPlaybookPredict caster Machine) + les abilities MoW sont TOUTES conditionnelles

**Statut** : harnais oracle MoW BATI + committe (aiPlaybookPredict resout les casters EntityType.Machine).
Port des overrides + confrontation live DEFERES (voir "Reste"). Confronte live gqfc5mff6c, board MC1_67.

## Correction de premisse #172 (RE re-expert, PROUVE)

La tache disait "base = getter dedie != avg". FAUX. `DaemonicOrdnanceAbility.GetDamage @1811cfbb0` ET
`LightOfSanguiniusAbility.GetDamage @1811b2010` (HadesAutocannons ; VA du prompt 181140b1c inexistante) sont des
wrappers TRIVIAUX de `AActiveAbility.MinMaxDamage @180fb2dc0` = **avg(minDmg 0xc, maxDmg 0xd) scale par level = LE
GENERIQUE**. hits = `ArmoriumCherubAbility.GetHits` (config). param_8 = null. => STRUCTURELLEMENT pierce-only
candidates, IDENTIQUE a HarbingerOfDestruction #169 (base+hits generiques, seul gap = profil None/pierce 0).

Les 2 playbooks MoW sont enregistres dans la MEME `PlaybookDatabase` que les units (`InitializePlaybookBuilders`
b__31_150/149) ; le scorer `CalculateUtilityFromPredictions @181407890` slot vtable +0x358 est GENERIQUE (aucun test
EntityType). Donc `LoadPlaybook(1148/1147)` + `MakeDamagePredictions` marchent tels quels pour un caster MoW.

## Harnais oracle MoW (committe) — `frida/hooks/features/ai-step/rpc-predict.ts`

`aiPlaybookPredict` ne resolvait le caster que parmi `EntityType.Unit` -> "unit not found" pour un MoW (le caster
MoW = `EntityType.Machine`, vit dans `decisionView.mows`, PAS `.units`). FIX :
- resoudre le caster parmi `EntityType.Unit` OU `EntityType.Machine` (+ idByPtr des deux) ;
- UnitPosition : un MoW est OFF-BOARD (GetUnitPosition rend une UnitPosition vide) -> fallback sur la UnitPosition de
  la CIBLE (le bombard MoW s'aime sur une tuile ; les selectors MoW n'utilisent pas la position du caster, RE #172).

Prouve fonctionnel : le caster MoW resout, `LoadPlaybook` charge `DaemonicOrdnancePlaybook`/... , `MakeDamagePredictions`
tourne SANS erreur. (Build via `rl_duel build --p-mow <mow>` + un `--p-units` regular companion ; le MoW deploie et
apparait dans `decisionView.mows` avec casterId=machineId.)

## Decouverte : TOUTES les abilities MoW sont STATE-CONDITIONNELLES (fresh prediction = 0/-1 PAR DESIGN)

Confronte les 6 abilities des 3 MoW buildables (blackForgefiend, tauBroadside, ultraDreadnought) vs ultraTitus.
AUCUNE ne rend un event de degat en etat FRAIS — chacune gate son degat sur un etat prealable (lu dans la DESCRIPTION
i2, recon AVANT de prober — lecon : lire le kit d'abord) :

| ability (id) | MoW | condition de declenchement (desc i2) | fresh |
|---|---|---|---|
| DaemonicOrdnance (1148) | blackForgefiend | ennemi sur une tuile DEJA EN FEU (1er cast pose le feu) | count=0 |
| HadesAutocannons (1147) | blackForgefiend | cible = un SUMMON ennemi (ultraTitus n'en est pas un) | count=0 |
| HeavyRailRifle (1160) | tauBroadside | PENDING (tire au debut du prochain tour) | count=-1 |
| TwinSmartMissileSystem (1161) | tauBroadside | ennemi porteur d'un MARKERLIGHT (1er cast marque) | count=-1 |
| DutyEternal (1158) | ultraDreadnought | SUMMON (invoque Galatian 14550 HP) — pas de degat | count=-1 |
| MacroPlasmaIncinerator (1159) | ultraDreadnought | MINE : degat quand un ennemi FINIT son move dans la zone marquee | count=-1 |

count=0 = liste vide (selector 0 cible) ; count=-1 = `MakeDamagePredictions` rend null (listNull, cf. #110 : pas de
prediction de degat immediate). Les DEUX sont le comportement CORRECT du natif : le degat MoW est deferre/triggered.
Le harnais fonctionne ; il n'y a rien a "reparer" cote caster-resolution.

## Reste (DEFERE — gros chantiers, valeur marginale faible car reponse RE connue)

Pour une confrontation LIVE d'un degat MoW il faut, PAR ability, monter l'etat declencheur :
- DaemonicOrdnance : poser le feu (caster une 1re fois) puis re-predire sur la tuile en feu avec un ennemi dessus.
- HadesAutocannons : un SUMMON ennemi a portee (summoner adverse).
- MacroPlasma : un ennemi qui finit son move dans la zone marquee. Etc.
ET l'ENGINE ne predit pas encore un MoW (combatSnapshot/Scene ne capturent pas `EntityType.Machine` -> pas de ctx MoW
cote moteur). Donc confrontation complete = trigger-state sim PAR ability + engine MoW-scene.

Overrides `_PLAYBOOK_PROFILE_OVERRIDE[1148/1147]="None"` NON ajoutes : l'engine n'exerce jamais ces predictions (MoW
hors scene) -> ce serait du code mort. A ajouter QUAND l'engine predira les MoW (chantier separe). La reponse port
(pierce-only, base=avg) est RE-prouvee et documentee ici pour ce moment-la.

## Lecon

RECON LA DESCRIPTION (kit i2) AVANT de prober une ability inconnue. Prober blblackForgefiend a l'aveugle a fait croire
a un "harnais casse" (count=0) alors que la description dit exactement pourquoi (feu / summon requis). Les abilities MoW sont
un cas a part : toutes conditionnelles/2-phases -> jamais confrontables en etat frais sans monter le declencheur.

## Confront re-tente + CLOTURE (2026-07-16)

RE re-confirmee par decompile (spot-check) : `DaemonicOrdnanceAbility.GetDamage @1811cfbb0` ET
`LightOfSanguiniusAbility.GetDamage @1811b2010` (HadesAutocannons) sont des wrappers TRIVIAUX de
`AActiveAbility.MinMaxDamage @180fb2dc0`, dont la branche avg = `Half(Sum(GetVariableForLevel(0xc=minDmg),
GetVariableForLevel(0xd=maxDmg)))` = **avg GENERIQUE** (== `ab.get_damage`). Aucune base bespoke. => la seule
divergence est bien `param_8=null` -> pierce 0. Override `_PLAYBOOK_PROFILE_OVERRIDE[1148/1147]="None"` (committe
3cb8f5b) CONFIRME correct.

Confront numerique LIVE re-tente (build `--p-mow blackForgefiend --a-units ultraTitus,worldTerminator,custoTrajann`,
board MC1_67) : caster MoW resolu via `decisionView.mows[].casterId` (=83, PAS `.id`=75) ; `aiPlaybookPredict(83,
tgt, 1148)` operationnel mais rend **`count=0, events=[]`** sur les 3 cibles blindees (armure 2312/2813/2510). C'est
le comportement 2-phase attendu : DaemonicOrdnance ne fait de degat qu'a un ennemi sur une tuile DEJA EN FEU (le 1er
cast pose le feu) -> prediction FRAICHE vide. (La mention "62 cibles" d'une note de tache = tuiles ciblables du
selector de mouvement, PAS la prediction de degat.) HadesAutocannons (1147) = `hasAmmo:false` (hors munitions) au
build -> no-op. Donc la confrontation NUMERIQUE (pierce-0 full-armor) exige de monter l'etat feu (trigger-state sim)
ET une engine-MoW-scene -> DEUX chantiers deferres (cf. section "Reste").

## MAJ — le « ctx MoW cote moteur » EXISTE desormais (voir `case-mow-offboard-cast`)

La phrase « l'ENGINE ne predit pas encore un MoW (combatSnapshot/Scene ne capturent pas
`EntityType.Machine` -> pas de ctx MoW cote moteur) » est PARTIELLEMENT perimee :

- **COMBAT/EXECUTION : DEBLOQUE.** `load_state` materialise desormais la MoW comme entite ECS
  (`_load_machines`/`_load_machine_stats`, mirror `AddMachineOperation.Execute @180e4b5e0` + jeu de
  composants mesure : ni `HealthComponent` ni `PositionComponent`) avec un `StatsComponent`
  (level/mult = `AbilityState` per-ability) -> un port d'ability MoW s'execute et se confronte au live.
  Sweep : 13 des 16 abilities MoW du pool castent live sans mise en scene (les 3 autres = predicats de
  ciblage montables, PROUVE pour SquigLaunchas).
- **DECISION : DEBLOQUEE par R14** (`case-r14-mow-decision.md`). Le chemin natif dedie n'est PAS
  `aiPlaybookPredict` (qui est le harnais oracle de PREDICTION monte ici) mais le tactic
  `IdunBattle.AI.Tactics.DefaultMachineTactic`, sur lequel
  `IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit` route des `IsMachine(actor)` : pas de
  `MovementActionGenerator`, caster a `UnitPosition.NullPosition`, tuiles candidates VIDES. Porte
  (`engine.ai.tactic.DefaultMachineTactic` + `engine.ai.context.build_machine`), sweep 8/8 MoW,
  coincidence mesuree sur 1187. Aucune origine inventee.
- ~~**combatSnapshot reste `EntityType.Unit`-only**~~ -- **PERIME** : `d9d0008` (2026-07-26) a elargi
  `combatSnapshot.allUnits` ET `statModSources.targetUnits` a `EntityType.Machine`
  (`rpc-snapshot.ts:131` et `:367`, + champ `entityType`). La spec de `case-mow-offboard-cast` §8 est
  implementee. Base gameconfig = 0 pour les 8 MoW (inchange). ⚠ Effet de bord ouvert : la ligne Machine
  ainsi emise ecrase le `StatsComponent` de la MoW cote port -> residu **N7** de
  `port-residuals-inventory.md` (`case-162` §4).

CLOTURE : le port (override pierce-0, base=avg generique, hits generique) est RE-PROUVE + committe, et STRUCTURELLEMENT
IDENTIQUE aux 4 candidats param_8=null deja VALIDES LIVE sur ultraTitus blinde (1020 HeraldOfTheApocalypse / 1062
SanctorumMissile / 1017 FragBomb / 1006 MultiThreatEliminator). Meme base de cloture que le frere #169
(HarbingerOfDestruction : "retenu sur preuve decompile, carrier non confrontable live"). Confront numerique MoW =
deferre au chantier engine-MoW-scene + trigger-state sim (ou l'override sera enfin exerce).
