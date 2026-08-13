# Couverture combat des abilities actives (audit #95)

> Genere par `scripts/python/audit_combat_ability_coverage.py` (source de verite : `gameconfig.activeAbilities` par unite x `AbilityHandler.ABILITY_CLASSES`). A regenerer au changement de build ou apres un port d'ability.

## Contexte : DECIDER != EXECUTER

Le runner combat route chaque ability choisie via `ActiveAbilityMessage` -> `AbilityHandler.visit_ActiveAbilityMessage` : tout `ActiveAbilityType` **absent** de `ABILITY_CLASSES` fait un **NO-OP SILENCIEUX** (`ported:False`, 0 degat, 0 effet, AUCUNE erreur). La DECISION (prediction/scoring) peut CHOISIR l'ability alors que l'EXECUTION l'ignore -> divergence d'etat INVISIBLE en replay/self-play. Cf. doctrine CLAUDE.md "DECIDER != EXECUTER". Durcissement : `AbilityHandler.unported` accumule les casts tombes sur no-op ; les tests d'execution assert `last['ported'] is True`.

## Bilan

- ActiveAbilityType castables par les unites : **175** distinct
- **PORTED** (dans `ABILITY_CLASSES`) : **165**
- **NO-OP silencieux** (a porter) : **10**
- Ventilation NO-OP : **DAMAGE**=6, **SUMMON**=2, **EFFECT/BUFF**=2

## Priorisation & templates de port

1. **DAMAGE** (impact combat direct : degat non inflige = divergence PV) -> template `SpiritLeechAbility`/`CrushingClawsAbility` (`ability_attack_params` + `execute_ability_attack`, config minDmg/maxDmg + profil + nrOfHits ; splash/effets composes selon `ExecuteBehaviour`). Prioriser par #units. ATTENTION : quelques "DAMAGE" sont en fait des BUFF a `damageProfile` (NovaBoost/NovaCharge/NovaShield 1192-1194 = NonComparable buff/tile) -> verifier `ExecuteBehaviour` avant de porter comme attaque.

> ⚠ **LA COLONNE `categorie` DERIVE DU KIT, PAS DU BEHAVIOUR -- elle N'EST PAS VERIFIEE.** Elle lit le `damageProfile` du gameconfig, c'est-a-dire le profil de l'ARME du porteur. Pour une ability NON PORTEE, son `ExecuteBehaviour` n'est connu de personne : la categorie ne peut donc PAS etre derivee, c'est une limite structurelle. **Mesure du 2026-08-07 : quatre tranches ont ete briefees comme des ports d'ATTAQUE alors que leur cast ne frappe pas** -- patron 2-PHASES (le cast pose des effets, le degat appartient a une TRIGGERED), ou `AddEffect` suivi d'une attaque normale libre, ou boucle imperative. Un solveur envoye porter « une attaque » qui n'en est pas perd son temps, ou pire **invente le degat au cast**.
>
> **Avant tout dispatch : LIRE `<X>Ability$$ExecuteBehaviour` au decompile.** Les cas ou la derivation a ete mesuree FAUSSE sont ecrases dans le tableau et s'affichent `2-PHASES (cast sans degat) [kit: DAMAGE(...)]` ; le registre qui les porte est `CATEGORIE_MESUREE` dans le generateur. Une ability qui n'y figure pas n'est PAS « verifiee DAMAGE » : elle est **non verifiee** (residu `#491-r2`).

2. **SUMMON** -> template `ScarabHiveAbility`/`GetEmRuntzAbility` (`SpawnUnitOperation` + summon on-appearance).
3. **HEAL** / lifesteal / **REPAIR** -> **DEBLOQUE** (#520). Les deux Operations sont portees et COMPLETES : `IdunBattle.Operations.RepairUnitOperation$$Execute` (`runner/operations/repair.py`, #299) et `IdunBattle.Operations.HealUnitOperation$$Execute` (`runner/operations/heal.py`, #520). Chacune porte son gate (`AttackQuery$$EntityCanBeRepaired` / `$$EntityCanBeHealed`), sa prediction (`DamagePrediction$$PredictRepair` / `$$PredictHeal`) et ses deux fabriques d'options (`ForRepair`/`ForRegenerate`, `ForHeal`/`ForRegenerate`). Un port de cette categorie construit une feuille `Repair`/`Heal` (`runner/abilities/behaviours/stats.py`) et DECLARE sa fabrique lue au decompile.

> ⚠ **CETTE LIGNE A ANNONCE « BLOQUE sur un `HealOperation`/`RepairOperation` combat absent du runner (tache #94) » BIEN APRES QUE LES DEUX EURENT ETE PORTEES**, et c'est la forme de degat la plus couteuse d'une citation perimee : elle a fait RENONCER a dispatcher une categorie entiere. Pire, elle designait le mauvais bloqueur -- le vrai etait qu'`HealUnitOperation` n'appelait NI son gate NI `PredictHeal`, donc les QUATRE abilities HEAL deja au registre soignaient des cibles que le natif refuse, en rendant `ported: True`. Mesure #520 sur le seed 777 : **3 unites blessees sur 10** etaient refusees par le gate et soignees par le port. Un no-op silencieux DANS une ability declaree portee ne se voit par AUCUN compteur de cet audit -- il ne compte que les absentes du registre.

4. **EFFECT/BUFF** -> `AddEffectOperation` (+ stat-mods) ; certains deja modelises cote prediction (NonComparable) mais pas executes.

Legende `kinds` : **L**=lineup (jouable), **N**=npc, **S**=summons.

## NO-OP SILENCIEUX en combat (a porter, tries categorie puis frequence) (10)

| id | ability | categorie | #units | kinds |
|---|---|---|---|---|
| 1015 | PrecisionShot | DAMAGE(Energy) | 2 | NS |
| 1215 | InstrumentsOfVengeance | DAMAGE(HeavyRound) | 1 | N |
| ? | Maugetar | DAMAGE(DirectDamage) | 1 | N |
| 1193 | NovaCharge | DAMAGE(Particle) | 1 | N |
| 1174 | SolarAtomizer | DAMAGE(Melta) | 1 | N |
| 1094 | TheLantern | DAMAGE(Energy) | 1 | N |
| 1053 | DevoutPush | EFFECT/BUFF | 2 | NS |
| 1107 | Reveal | EFFECT/BUFF | 1 | N |
| 1052 | CallRipperSwarms | SUMMON | 1 | N |
| 1172 | InvocationOfMachineVengeance | SUMMON | 1 | N |

## PORTED (registry) (165)

| id | ability | categorie | #units | kinds |
|---|---|---|---|---|
| 1141 | OverwhelmingWrath | 2-PHASES (cast sans degat) [kit: DAMAGE(Eviscerate)] | 2 | LN |
| 1069 | SeekerMissileFrequencyLock | 2-PHASES (cast sans degat) [kit: DAMAGE(HeavyRound)] | 5 | LN |
| 1115 | FearOfTheUnseen | DAMAGE(DirectDamage) | 7 | LN |
| 1036 | FrenziedFiring | DAMAGE(HeavyRound) | 7 | LN |
| 1104 | SpiritLeech | DAMAGE(Psychic) | 7 | LN |
| 1122 | CordClaw | DAMAGE(DirectDamage) | 6 | LN |
| 1105 | CrushingClaws | DAMAGE(Piercing) | 6 | LN |
| 1029 | Drachnyen | DAMAGE(Piercing) | 6 | LN |
| 1008 | HarbingerOfDestruction | DAMAGE(DirectDamage) | 6 | LN |
| 1088 | HellfyreMissileRack | DAMAGE(HeavyRound) | 6 | LN |
| 1020 | HeraldOfTheApocalypse | DAMAGE(Piercing) | 6 | LN |
| 1006 | MultiThreatEliminator | DAMAGE(Gauss) | 6 | LN |
| 1035 | PlagueWind | DAMAGE(Psychic) | 6 | LN |
| 1116 | RadBombardment | DAMAGE(Toxic) | 6 | LN |
| 1026 | BasiliskBarrage | DAMAGE(Blast) | 5 | LN |
| 1022 | BringerOfDespair | DAMAGE(Power) | 5 | LN |
| 1171 | DakkaDakkaDakka | DAMAGE(Projectile) | 5 | LN |
| 1102 | Doombolt | DAMAGE(Psychic) | 5 | LN |
| 1087 | ExemplarOfTheKauyon | DAMAGE(Blast) | 5 | LN |
| 1017 | FragBomb | DAMAGE(Blast) | 5 | LN |
| 1048 | FragstormGrenadeLauncher | DAMAGE(Blast) | 5 | LN |
| 1180 | HeroicFusillade | DAMAGE(Projectile) | 5 | LN |
| 1004 | MortisRound | DAMAGE(HeavyRound) | 5 | LN |
| 1027 | PsychicMaelstrom | DAMAGE(Psychic) | 5 | LN |
| 1065 | ScythingTalons | DAMAGE(Bio) | 5 | NS |
| 1068 | SilentDeath | DAMAGE(Piercing) | 5 | LN |
| 1100 | SorcerousFacade | DAMAGE(Psychic) | 5 | LN |
| 1152 | UnstoppableMomentumReworked | DAMAGE(DirectDamage) | 5 | LN |
| 1014 | ArmoriumCherub | DAMAGE(Flame) | 4 | LN |
| 1041 | BrazierOfHolyFire | DAMAGE(Flame) | 4 | LN |
| 1042 | FlailSwing | DAMAGE(Power) | 4 | LN |
| 1038 | FoulInfusion | DAMAGE(Toxic) | 4 | LN |
| 1000 | GauntletsOfUltramar | DAMAGE(Bolter) | 4 | LN |
| 1064 | Loki_SwoopingHawk | DAMAGE(Piercing) | 4 | LN |
| 1165 | MightFromBelow | DAMAGE(Psychic) | 4 | LN |
| 1062 | SanctorumMissile | DAMAGE(Blast) | 4 | LN |
| 1139 | SentinelDirectives | DAMAGE(Physical) | 4 | LN |
| 1019 | StormOfWrath | DAMAGE(Psychic) | 4 | LN |
| 1154 | TacticalPrecision | DAMAGE(Bolter) | 4 | LN |
| 1043 | ThunderousAssault | DAMAGE(Power) | 4 | LN |
| 1189 | CalibaniteGreatsword | DAMAGE(Power) | 3 | LN |
| 1092 | DarkTalonStrike | DAMAGE(DirectDamage) | 3 | LN |
| 1080 | HellfireShells | DAMAGE(Piercing) | 3 | NS |
| 1150 | PlasmaCannon | DAMAGE(Plasma) | 3 | LN |
| 1091 | SlashingDive | DAMAGE(Power) | 3 | NS |
| 1103 | Supercharge | DAMAGE(Plasma) | 3 | LN |
| 1129 | BloodyFury | DAMAGE(Chain) | 2 | LN |
| 1148 | DaemonicOrdnance | DAMAGE(Plasma) | 2 | LN |
| 1213 | DeathOnTheWind | DAMAGE(HeavyRound) | 2 | LN |
| 1188 | DevastatingRefrain | DAMAGE(Blast) | 2 | LN |
| 1168 | EntropyCannons | DAMAGE(Energy) | 2 | LN |
| 1078 | Fragstorm | DAMAGE(Blast) | 2 | NS |
| 1147 | HadesAutocannons | DAMAGE(Flame) | 2 | LN |
| 1214 | Hailstrike | DAMAGE(Projectile) | 2 | LN |
| 1160 | HeavyRailRifle | DAMAGE(Piercing) | 2 | LN |
| 1044 | IncendiaryShells | DAMAGE(Flame) | 2 | NS |
| 1209 | InfernalCannon | DAMAGE(Flame) | 2 | LN |
| 1131 | JakhalStimms | DAMAGE(Physical) | 2 | LN |
| 1132 | KillMaimBurn | DAMAGE(Piercing) | 2 | LN |
| 1108 | KissOfDeath | DAMAGE(DirectDamage) | 2 | NS |
| 1204 | LeadingTheCharge | DAMAGE(Power) | 2 | LN |
| 1159 | MacroPlasmaIncinerator | DAMAGE(Plasma) | 2 | LN |
| 1142 | MalleusRocketLauncher | DAMAGE(Blast) | 2 | LN |
| 1137 | MurderousSwing | DAMAGE(Piercing) | 2 | LN |
| 1169 | PlagueburstMortar | DAMAGE(Toxic) | 2 | LN |
| 1098 | PlasmaGrenade | DAMAGE(Plasma) | 2 | NS |
| 1230 | SavageEchoes | DAMAGE(Eviscerate) | 2 | LN |
| 1200 | SquigLaunchas | DAMAGE(Physical) | 2 | LN |
| 1201 | SquigMine | DAMAGE(Blast) | 2 | LN |
| 1051 | Stikkbomb | DAMAGE(Blast) | 2 | NS |
| 1113 | Stormcaller | DAMAGE(Psychic) | 2 | LN |
| 1225 | StrikeFromTheShadows | DAMAGE(Bolter) | 2 | LN |
| 1187 | ThriceBlessedConflagration | DAMAGE(Flame) | 2 | LN |
| 1161 | TwinSmartMissileSystem | DAMAGE(Blast) | 2 | LN |
| 1018 | ValkyrieStrike | DAMAGE(Blast) | 2 | NS |
| 1207 | AncestralFortune | DAMAGE(Plasma) | 1 | L |
| 1173 | ArcScourge | DAMAGE(Particle) | 1 | N |
| 1221 | AugmentedAssault | DAMAGE(Eviscerate) | 1 | L |
| 1176 | BlightGrenades | DAMAGE(Toxic) | 1 | N |
| 1199 | DoomSiren | DAMAGE(DirectDamage) | 1 | L |
| 1232 | EmpyricAmbush | DAMAGE(Eviscerate) | 1 | L |
| 1198 | EuphoricStrikes | DAMAGE(Power) | 1 | L |
| 1197 | ExcruciatingFrequencies | DAMAGE(Blast) | 1 | L |
| 1170 | ExplosivePresents | DAMAGE(Blast) | 1 | N |
| 1097 | Foehammer | DAMAGE(Power) | 1 | L |
| 1090 | GrapnelLauncher | DAMAGE(Physical) | 1 | L |
| 1206 | GravitonRifle | DAMAGE(Physical) | 1 | L |
| 1089 | GreatFrostAxe | DAMAGE(Piercing) | 1 | L |
| 1153 | HammerOfWrath | DAMAGE(Power) | 1 | L |
| 1227 | HeavyWarpFlamer | DAMAGE(Flame) | 1 | L |
| 1196 | LashOfTorment | DAMAGE(Eviscerate) | 1 | L |
| 1177 | LightOfSanguinius | DAMAGE(Melta) | 1 | L |
| 1216 | MartialExemplar | DAMAGE(Power) | 1 | N |
| 1191 | MartialInspiration | DAMAGE(Eviscerate) | 1 | L |
| 1222 | MassDriverAccelerator | DAMAGE(DirectDamage) | 1 | L |
| 1184 | MomentShackle | DAMAGE(Bolter) | 1 | L |
| 1093 | MortarionsPlagueWind | DAMAGE(Psychic) | 1 | N |
| 1192 | NovaBoost | DAMAGE(Particle) | 1 | N |
| 1194 | NovaShield | DAMAGE(Particle) | 1 | N |
| 1095 | ReapingScythe | DAMAGE(Chain) | 1 | N |
| 1056 | StranglethornCannon | DAMAGE(Blast) | 1 | N |
| 1195 | TalonsOfTheEmperor | DAMAGE(Power) | 1 | L |
| 1217 | TheLionsWrath | DAMAGE(Power) | 1 | N |
| 1183 | VexillaMagnifica | DAMAGE(Physical) | 1 | L |
| 1202 | VigilanceEternal | DAMAGE(Power) | 1 | L |
| 1005 | AdaptiveStrategy | EFFECT/BUFF | 6 | LN |
| 1023 | Burrowers | EFFECT/BUFF | 6 | NS |
| 1118 | DoctrinaImperatives | EFFECT/BUFF | 6 | LN |
| 1066 | Executioner | EFFECT/BUFF | 6 | LN |
| 1210 | ExemplarOfTheMontka | EFFECT/BUFF | 6 | LN |
| 1050 | HolyDuel | EFFECT/BUFF | 6 | LN |
| 1101 | AttemptedPossession | EFFECT/BUFF | 5 | LN |
| 1226 | Chronometron | EFFECT/BUFF | 5 | LN |
| 1081 | FightingRetreat | EFFECT/BUFF | 5 | LN |
| 1063 | FireAndReposition | EFFECT/BUFF | 5 | LN |
| 1067 | HarvesterOfSouls | EFFECT/BUFF | 5 | LN |
| 1164 | MindControl | EFFECT/BUFF | 5 | LN |
| 1025 | SkyStrike | EFFECT/BUFF | 5 | LN |
| 1003 | DeathFromAbove | EFFECT/BUFF | 4 | LN |
| 1011 | TunnelingHorror | EFFECT/BUFF | 4 | NS |
| 1061 | UnbreakableDuty | EFFECT/BUFF | 4 | LN |
| 1049 | CrusadeOfWrath | EFFECT/BUFF | 3 | LN |
| 1140 | ExemplarOfHate | EFFECT/BUFF | 3 | LN |
| 1010 | StormOfFlensingBlades | EFFECT/BUFF | 3 | N |
| 1185 | ForwardObservers | EFFECT/BUFF | 2 | NS |
| 1228 | SternguardFocus | EFFECT/BUFF | 2 | LN |
| 1186 | WallOfMirrors | EFFECT/BUFF | 2 | NS |
| 1133 | WarConstruct | EFFECT/BUFF | 2 | N |
| 1163 | BlackRage | EFFECT/BUFF | 1 | L |
| 1032 | Catalyst | EFFECT/BUFF | 1 | N |
| 1203 | DaemonicPatrons | EFFECT/BUFF | 1 | L |
| 1211 | RitesOfMorkai | EFFECT/BUFF | 1 | L |
| 1151 | TheQuickening | EFFECT/BUFF | 1 | L |
| 1106 | WarHowl | EFFECT/BUFF | 1 | L |
| 1082 | InspiredToGreatness | HEAL | 5 | LN |
| 1002 | CombatRestoratives | HEAL | 4 | LN |
| 1037 | RevitalizingMalignancy | HEAL | 4 | LN |
| 1039 | RitesOfRestoration | HEAL | 4 | LN |
| 1175 | BloodChalice | HEAL | 1 | L |
| 1231 | TitanhammerSquad | HEAL | 1 | L |
| 1117 | DefendTheDivineWork | REPAIR | 6 | LN |
| 1224 | NanoscarabRepairProtocols | REPAIR | 2 | LN |
| 1223 | ReanimationBeam | REPAIR | 2 | LN |
| 1112 | AlphaWarrior | SUMMON | 8 | LN |
| 1121 | ItItches | SUMMON | 7 | LN |
| 1016 | SendInTheNextWave | SUMMON | 7 | LN |
| 1096 | MasterOfTheTutelaries | SUMMON | 6 | LN |
| 1009 | ResurrectionOrb | SUMMON | 6 | LN |
| 1007 | ScarabHive | SUMMON | 6 | LN |
| 1028 | SupremeCommander | SUMMON | 6 | LN |
| 1077 | EarlyWarningOverride | SUMMON | 5 | LN |
| 1045 | GetEmRuntz | SUMMON | 5 | LN |
| 1057 | GrotTank | SUMMON | 5 | LN |
| 1021 | Incursion | SUMMON | 5 | LN |
| 1058 | Waaagh | SUMMON | 5 | LN |
| 1166 | AberrantHypermorph | SUMMON | 4 | LN |
| 1179 | CultDemagogue | SUMMON | 4 | LN |
| 1040 | Poxwalkers | SUMMON | 4 | LN |
| 1047 | ScarabSummon | SUMMON | 3 | NS |
| 1208 | AetherStride | SUMMON | 2 | LN |
| 1144 | BioMinefield | SUMMON | 2 | LN |
| 1158 | DutyEternal | SUMMON | 2 | LN |
| 1143 | ForwardSpotter | SUMMON | 2 | LN |
| 1145 | SporeMineLauncher | SUMMON | 2 | LN |
| 1219 | IronkinSteeljack | SUMMON | 1 | L |
