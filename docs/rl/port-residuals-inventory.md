# Inventaire des résidus de portage — confronté au CODE (2026-07-26)

> **Pourquoi ce fichier.** `backlog.md` décrit des INTENTIONS horodatées, `port-roadmap.md` un
> découpage figé au 2026-07-23 : ni l'un ni l'autre ne décrit l'état du code. Trois entrées avaient
> déjà été trouvées périmées le jour même (`getstuckin_combat_chance`, prérequis « canal pierce »
> AdMec, FireOfAbsolution). Ce document est le résultat d'une **confrontation item par item au
> commit courant** : chaque ligne porte un verdict **OUVERT / PÉRIMÉ / NON PERTINENT**, et seul
> OUVERT produit une tâche dispatchable.
>
> **Base de la mesure** : commit `fc23f1e` (`origin/master` au 3ᵉ rebase), build `gqfc5mff6c`,
> session Frida 1 `running`, pool `rl_duel build --list-pool` rank 17 = **97 unités + 8 MoW**.
>
> **Démonstration en direct de l'utilité de ce document** : l'inventaire a d'abord été établi sur
> `7f47c29` ; **trois rebases successifs** avant PR ont ramené 6 commits qui ont fermé **6 des
> résidus que je venais d'inventorier comme OUVERTS** (+ un sous-item de R28) (R2 gate d'immunité, R3 overwatch un-tir,
> R10 override de niveau 1180, R11 phase-2 EarlyWarningOverride, R18 bouclier × limites,
> R22 EnvFireTile). Ils sont passés en §5.0 avec leur commit, et les **6 résidus neufs** que ces
> commits nomment dans leurs case docs — absents de tout backlog — ont été ajoutés (N1-N6). Les
> comptes des trois GISEMENTS, eux, sont **inchangés après les deux rebases** (aucun de ces commits
> ne porte d'ability neuve) — re-vérifié à chaque fois en relançant les deux audits et les trois
> dérivations.
>
> **Ce document n'est PAS auto-généré** — mais tous ses comptes le sont. Pour les re-dériver :
> `python audit_combat_ability_coverage.py`, `python audit_kit_coverage.py` et
> `python audit_passive_ability_coverage.py` depuis `scripts/python/` (le 3ᵉ interroge le pool
> live ; les deux autres sont offline). Les fichiers générés (`combat-ability-coverage.md`,
> `kit-coverage.md`, `passive-ability-coverage.md`) étaient **déjà à jour** au commit courant :
> c'est `port-roadmap.md` (rédigé à la main) qui a dérivé.

---

## 0. Recalage des chiffres — ce qui a bougé depuis les audits cités

| Chiffre | Valeur citée (backlog / roadmap) | Valeur RE-DÉRIVÉE (2026-07-26) | Sens |
|---|---|---|---|
| actives castables | 171 | **171** | inchangé |
| actives portées COMBAT (`ABILITY_CLASSES`) | 16 (roadmap §intro) | **75** (registre : 76 entrées ; la 76ᵉ, 1076 `MV71SniperDroneSquadAttack`, n'est dans les `activeAbilities` d'aucune unité — attaque déléguée du drone) | +59 |
| actives **NO-OP combat** | 96 | **96** | inchangé (les ports ont suivi les nouvelles entrées) |
| actives **`[-D]`** (décision portée, combat NO-OP) | 27 | **20** dont **18** à porteur confrontable | −7 |
| kits lineup avec du travail | 119 | **101** | −18 |
| items manquants (kit-coverage) | 249 | **139** | −110 |
| kits lineup COMPLETS | 4 | **22** | +18 |
| abilities du registre **sans `TARGETING_OPTIONS`** | 60 | **75** sur 76 | **+15** (le gisement GROSSIT à chaque port) |
| overlays `CalculateCustomUtility` portés | 2 | **6** (`playbook.REGISTRY` = 7 avec `Repair`) | +4 |

**Le seul compte qui a EMPIRÉ est `TARGETING_OPTIONS`** : chaque ability portée depuis #115 est
entrée au registre sans son masque de ciblage. C'est la dette qui s'accumule mécaniquement.

---

## 1. Gisement 1 — les 96 actives NO-OP en combat

`AbilityHandler.visit_ActiveAbilityMessage` route tout `ActiveAbilityType` absent de
`ABILITY_CLASSES` vers un **NO-OP silencieux** (`ported:False`, 0 dégât, 0 effet, aucune erreur).

**Ventilation par confrontabilité** (gate HERO / MoW / SUMMON / NPC) :

| Verdict | N | Dispatchable ? |
|---|---|---|
| **HERO** — porteur lineup DANS le pool rank 17 | 52 | oui |
| **MoW** — porteur MoW du pool (harnais débloqué, `a9714a4`) | 2 | oui |
| **SUMMON** — porteur summon amené par un summoner du pool | 2 | oui |
| **HERO (catalog_inject)** — lineup absent du seed BC, injectable (`ab98129`) | 11 | oui |
| **SUMMON-ENV** — summon d'environnement, aucun summoner joueur | 8 | **NON PERTINENT** |
| **NPC** — tous les porteurs sont npc | 21 | **NON PERTINENT** |

⇒ **67 dispatchables, 29 non pertinents.** Taille par item = **1 ability**.

> ⚠ **Correction de méthode** : la catégorie « SUMMON » se dérive de `constants.unitId` **ET**
> `unitId_2/3/4`. Ne lire que `unitId` classe à tort `SlashingDive` (thousSmnScreamer) en non
> confrontable, alors que `MasterOfTheTutelaries` (`thousInfernalMaster`, dans le pool) pose le
> Screamer via `unitId_2`.

> ⚠ **`catalog_inject` a fermé le verrou « porteur hors pool »** (`case-92`, 10 porteurs confrontés
> live dont les 4 Votann, `thousDaemonPrince`, `necroReanimator`, `bloodTerminator`,
> `necroChronomancer`). Toute mention « porteur hors pool ⇒ inconfrontable » antérieure au
> 2026-07-25 est fausse.

### 1.a — NO-OP confrontables directement (pool rank 17) — 56

Colonne `D` = face DÉCISION portée (un des trois registres, cf. §2).

| id | ability | catégorie | faction | porteur | D | symbole natif |
|---|---|---|---|---|---|---|
| 1117 | DefendTheDivineWork | REPAIR | AdMec | admecManipulus | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour` |
| 1116 | RadBombardment | DAMAGE/Toxic | AdMec | admecDominus | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$ExecuteBehaviour` |
| 1068 | SilentDeath | DAMAGE/Piercing | Aeldari | eldarJainZar | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.SilentDeathAbility$$ExecuteBehaviour` |
| 1064 | Loki_SwoopingHawk | DAMAGE/Piercing | Aeldari | eldarAutarch | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase$$ExecuteBehaviour` (classe `...Loki.SwoopingHawkAbility`, dérivée de `DiveAttackAbilityBase`) |
| 1063 | FireAndReposition | EFFECT | Aeldari | eldarRanger | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$ExecuteBehaviour` |
| 1204 | LeadingTheCharge | DAMAGE/Power | AstraMilitarum | astraDreir | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.LeadingTheChargeAbility$$ExecuteBehaviour` |
| 1027 | PsychicMaelstrom | DAMAGE/Psychic | AstraMilitarum | astraPrimarisPsy | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicMaelstromAbility$$ExecuteBehaviour` |
| 1026 | BasiliskBarrage | DAMAGE/Blast | AstraMilitarum | astraOrdnance | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$ExecuteBehaviour` |
| 1017 | FragBomb | DAMAGE/Blast | AstraMilitarum | astraBullgryn | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour` |
| 1036 | FrenziedFiring | DAMAGE/HeavyRound | BlackLegion | blackObliterator | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour` |
| 1029 | Drachnyen | DAMAGE/Piercing | BlackLegion | blackAbaddon | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.DrachnyenAbility$$ExecuteBehaviour` |
| 1020 | HeraldOfTheApocalypse | DAMAGE/Piercing | BlackLegion | blackHaarken | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.HeraldOfTheApocalypseAbility$$ExecuteBehaviour` |
| 1061 | UnbreakableDuty | EFFECT | BlackTemplars | templAncient | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$ExecuteBehaviour` |
| 1050 | HolyDuel | EFFECT | BlackTemplars | templChampion | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` |
| 1049 | CrusadeOfWrath | EFFECT | BlackTemplars | templHelbrecht | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.CrusadeOfWrathAbility$$ExecuteBehaviour` |
| 1048 | FragstormGrenadeLauncher | DAMAGE/Blast | BlackTemplars | templAggressor | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormGrenadeLauncherAbility$$ExecuteBehaviour` |
| 1177 | LightOfSanguinius | DAMAGE/Melta | BloodAngels | bloodDante | D | `IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$ExecuteBehaviour` |
| 1175 | BloodChalice | HEAL | BloodAngels | bloodSanguinary | - | `IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$ExecuteBehaviour` |
| 1153 | HammerOfWrath | DAMAGE/Power | BloodAngels | bloodIntercessor | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$ExecuteBehaviour` |
| 1195 | TalonsOfTheEmperor | DAMAGE/Power | Custodes | custoAtlacoya | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.TalonsOfTheEmperorAbility$$ExecuteBehaviour` |
| 1191 | MartialInspiration | DAMAGE/Eviscerate | Custodes | custoBladeChampion | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.MartialInspirationAbility$$ExecuteBehaviour` |
| 1184 | MomentShackle | DAMAGE/Bolter | Custodes | custoTrajann | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.MomentShackleAbility$$ExecuteBehaviour` |
| 1183 | VexillaMagnifica | DAMAGE/Physical | Custodes | custoVexilusPraetor | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.VexillaMagnificaAbility$$ExecuteBehaviour` |
| 1038 | FoulInfusion | DAMAGE/Toxic | DeathGuard | deathPutrifier | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.FoulInfusionAbility$$ExecuteBehaviour` |
| 1035 | PlagueWind | DAMAGE/Psychic | DeathGuard | deathTyphus | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$ExecuteBehaviour` |
| 1199 | DoomSiren | DAMAGE/DirectDamage | EmperorsChildren | emperKakophonist | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour` |
| 1197 | ExcruciatingFrequencies | DAMAGE/Blast | EmperorsChildren | emperNoiseMarine | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$ExecuteBehaviour` |
| 1165 | MightFromBelow | DAMAGE/Psychic | Genestealers | genesPatriarch | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.MightFromBelowAbility$$ExecuteBehaviour` |
| 1164 | MindControl | EFFECT | Genestealers | genesMagus | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.MindControlAbility$$ExecuteBehaviour` |
| 1005 | AdaptiveStrategy | EFFECT | Necrons | necroWarden | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour` |
| 1171 | DakkaDakkaDakka | DAMAGE/Projectile | Orks | orksKillaKan | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$ExecuteBehaviour` |
| 1152 | UnstoppableMomentumReworked | DAMAGE/DirectDamage | Orks | orksNob | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.UnstoppableMomentumReworkedAbility$$ExecuteBehaviour` |
| 1057 | GrotTank | SUMMON | Orks | orksBigMek | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.GrotTankAbility$$ExecuteBehaviour` |
| 1041 | BrazierOfHolyFire | DAMAGE/Flame | Sisterhood | adeptCanoness | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour` |
| 1039 | RitesOfRestoration | HEAL | Sisterhood | adeptHospitaller | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$ExecuteBehaviour` |
| 1106 | WarHowl | EFFECT | SpaceWolves | spaceBlackmane | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$ExecuteBehaviour` |
| 1097 | Foehammer | DAMAGE/Power | SpaceWolves | spaceRockfist | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.FoehammerAbility$$ExecuteBehaviour` |
| 1090 | GrapnelLauncher | DAMAGE/Physical | SpaceWolves | spaceHound | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.GrapnelLauncherAbility$$ExecuteBehaviour` |
| 1087 | ExemplarOfTheKauyon | DAMAGE/Blast | Tau | tauShadowsun | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$ExecuteBehaviour` |
| 1069 | SeekerMissileFrequencyLock | DAMAGE/HeavyRound | Tau | tauMarksman | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$ExecuteBehaviour` |
| 1102 | Doombolt | DAMAGE/Psychic | ThousandSons | thousAhriman | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$ExecuteBehaviour` |
| 1101 | AttemptedPossession | EFFECT | ThousandSons | thousSorcerer | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$ExecuteBehaviour` |
| 1100 | SorcerousFacade | DAMAGE/Psychic | ThousandSons | thousTzaangor | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$ExecuteBehaviour` |
| 1088 | HellfyreMissileRack | DAMAGE/HeavyRound | ThousandSons | thousTerminator | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.HellfyreMissileRackAbility$$ExecuteBehaviour` |
| 1121 | ItItches | SUMMON | Tyranids | tyranParasite | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$ExecuteBehaviour` |
| 1115 | FearOfTheUnseen | DAMAGE/DirectDamage | Tyranids | tyranDeathleaper | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour` |
| 1154 | TacticalPrecision | DAMAGE/Bolter | Ultramarines | ultraTitus | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.TacticalPrecisionAbility$$ExecuteBehaviour` |
| 1019 | StormOfWrath | DAMAGE/Psychic | Ultramarines | ultraTigurius | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.StormOfWrathAbility$$ExecuteBehaviour` |
| 1141 | OverwhelmingWrath | DAMAGE/Eviscerate | WorldEaters | worldEightbound | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour` |
| 1137 | MurderousSwing | DAMAGE/Piercing | WorldEaters | worldExecutions | D | `IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$ExecuteBehaviour` |
| 1132 | KillMaimBurn | DAMAGE/Piercing | WorldEaters | worldKharn | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$ExecuteBehaviour` |
| 1129 | BloodyFury | DAMAGE/Chain | WorldEaters | worldTerminator | D | `IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$ExecuteBehaviour` |
| 1144 | BioMinefield | SUMMON | Tyranids | tyranBiovore (**MoW**) | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.BioMinefieldAbility$$ExecuteBehaviour` |
| 1158 | DutyEternal | SUMMON | Ultramarines | ultraDreadnought (**MoW**) | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$ExecuteBehaviour` — ⛔ bloqué **multi-hex** (`case-mow-offboard-cast` §6) |
| 1091 | SlashingDive | DAMAGE/Power | ThousandSons | thousSmnScreamer ← thousInfernalMaster (**SUMMON**) | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.SlashingDiveAbility$$.ctor` (pas de `*Behaviour` nommé : lire le ctor) |
| 1023 | Burrowers | EFFECT | Tyranids | tyranSmnRipperSwarm ← tyranParasite (**SUMMON**) | - | `IdunBattleLogic.Entities.Abilities.Active.Loki.BurrowersAbility$$ExecuteBehaviour` |

### 1.b — NO-OP confrontables via `catalog_inject.py` — 11

Porteurs lineup **absents du seed BC** : `python catalog_inject.py --units <id> --out <abs>.json`
puis `rl_duel build --seed-bc <abs>.json`. Procédure validée live sur 10 porteurs (`case-92` §4).

| id | ability | catégorie | faction | porteur | symbole natif |
|---|---|---|---|---|---|
| 1225 | StrikeFromTheShadows | DAMAGE/Bolter | AdeptusAstartes | astarCyrus | `IdunBattleLogic.Entities.Abilities.Active.Loki.StrikeFromTheShadowsAbility$$ExecuteBehaviour` |
| 1228 | SternguardFocus | EFFECT | DarkAngels | darkaSternguard | `IdunBattleLogic.Entities.Abilities.Active.Loki.SternguardFocusAbility$$ExecuteBehaviour` |
| 1203 | DaemonicPatrons | EFFECT | EmperorsChildren | emperFlawlessBlade | `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicPatronsAbility$$ExecuteBehaviour` |
| 1198 | EuphoricStrikes | DAMAGE/Power | EmperorsChildren | emperExultant | `IdunBattleLogic.Entities.Abilities.Active.Loki.EuphoricStrikesAbility$$ExecuteBehaviour` |
| 1196 | LashOfTorment | DAMAGE/Eviscerate | EmperorsChildren | emperLucius | `IdunBattleLogic.Entities.Abilities.Active.Loki.LashOfTormentAbility$$ExecuteBehaviour` |
| 1224 | NanoscarabRepairProtocols | REPAIR | Necrons | necroReanimator (MoW) | `IdunBattleLogic.Entities.Abilities.Active.Loki.NanoscarabRepairProtocolsAbility$$ExecuteBehaviour` |
| 1223 | ReanimationBeam | REPAIR | Necrons | necroReanimator (MoW) | `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$ExecuteBehaviour` |
| 1211 | RitesOfMorkai | EFFECT | SpaceWolves | spaceWolfPriest | `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour` |
| 1210 | ExemplarOfTheMontka | EFFECT | Tau | tauFarsight | `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheMontkaAbility$$ExecuteBehaviour` |
| 1209 | InfernalCannon | DAMAGE/Flame | ThousandSons | thousDaemonPrince (MoW) | `IdunBattleLogic.Entities.Abilities.Active.Loki.InfernalCannonAbility$$ExecuteBehaviour` |
| 1208 | AetherStride | SUMMON | ThousandSons | thousDaemonPrince (MoW) | `IdunBattleLogic.Entities.Abilities.Active.Loki.AetherStrideAbility$$ExecuteBehaviour` — suspicion multi-hex (jumeau DutyEternal) |

### 1.c — NON PERTINENTS (aucun porteur atteignable) — 29

**Ne pas y envoyer d'agent.** 21 npc-only + 8 summons d'environnement (posés par
`EnvFactionSummons:<Faction>` / `ATemptingTrap`, qu'aucune unité jouable ne porte).

NPC-only : `Maugetar` (eldarBossMauganRaUltra) · 1010 StormOfFlensingBlades · 1032 Catalyst ·
1052 CallRipperSwarms · 1056 StranglethornCannon · 1093 MortarionsPlagueWind · 1094 TheLantern ·
1095 ReapingScythe · 1107 Reveal · 1133 WarConstruct · 1170 ExplosivePresents ·
1172 InvocationOfMachineVengeance · 1173 ArcScourge · 1174 SolarAtomizer · 1176 BlightGrenades ·
1192 NovaBoost · 1193 NovaCharge · 1194 NovaShield · 1215 InstrumentsOfVengeance ·
1216 MartialExemplar · 1217 TheLionsWrath.

SUMMON-ENV (8) : 1011 TunnelingHorror (necroSmnDestroyer) · 1015 PrecisionShot (necroSmnDeathmark) ·
1044 IncendiaryShells (templNeophyte) · 1053 DevoutPush (templInitiate) · 1080 HellfireShells
(ultraSmnHeavyIntercessor — déjà constaté par `case-173`) · 1108 KissOfDeath (eldarSmnHarlequin) ·
1185 ForwardObservers + 1186 WallOfMirrors (tauSmnStealthSuit).

⚠ Ne PAS ajouter 1091 `SlashingDive` ici : son porteur `thousSmnScreamer` EST amené par
`MasterOfTheTutelaries` (`thousInfernalMaster`, dans le pool) via `constants.unitId_2` — il est en
§1.a. C'est le piège de la dérivation « `unitId` seul ».

---

## 2. Gisement 2 — les actives `[-D]` : la décision CHOISIT, l'exécution NO-OP

**C'est le gisement à valeur la plus haute** : divergence d'état *invisible* (aucune erreur,
`mutated=false`) en replay / self-play, sur des abilities que l'IA portée choisit réellement.

> ⚠ **`audit_kit_coverage.py` SOUS-COMPTE ce gisement.** Il ne consulte que DEUX registres de
> décision (`playbook.noncomparable.PLAYBOOKS`, `playbook.REGISTRY`) et rate le TROISIÈME :
> `engine/entities/abilities/active_ability.py::_SPECIAL_ABILITY_CLASSES` (mirrors
> `AActiveAbility` par ability : prédictions multi-hit / dégât conditionnel) et
> `_NONCOMPARABLE_ABILITIES`. Résultat : `kit-coverage.md` affiche 14 `[-D]`, le vrai compte est
> **20**. C'est exactement le faux `[--]` déjà relevé sur 1191 MartialInspiration
> (`port-roadmap.md` §3). **Correctif possible en 3 lignes** dans `audit_kit_coverage.py`
> (`collect()`, champ `decision`) — item dispatchable à part entière, il rend l'audit fiable.

Les 20, tous à porteur confrontable sauf 2 :

| id | ability | porteur | conf. | registre décision | symptôme | taille |
|---|---|---|---|---|---|---|
| 1129 | BloodyFury | worldTerminator | HERO | NC + `_SPECIAL` + NonComparable | non mesuré (structurel) | 1 ability (primitive `ChainLeftOverHitsAttackDamage`) |
| 1153 | HammerOfWrath | bloodIntercessor | HERO | NC + NonComparable | non mesuré | 1 ability |
| 1183 | VexillaMagnifica | custoVexilusPraetor | HERO | NC + NonComparable | non mesuré | 1 ability |
| 1121 | ItItches | tyranParasite | HERO | NC + NonComparable | non mesuré | 1 ability (multi-étage positionnel) |
| 1039 | RitesOfRestoration | adeptHospitaller | HERO | NC + NonComparable | non mesuré | 1 ability |
| 1117 | DefendTheDivineWork | admecManipulus | HERO | NC | non mesuré | 1 ability |
| 1050 | HolyDuel | templChampion | HERO | NC | non mesuré | 1 ability (3 classes d'effet) |
| 1038 | FoulInfusion | deathPutrifier | HERO | NC | non mesuré | 1 ability |
| 1090 | GrapnelLauncher | spaceHound | HERO | NC | non mesuré | 1 ability (≥6 primitives) |
| 1020 | HeraldOfTheApocalypse | blackHaarken | HERO | `REGISTRY` (custom utility) | non mesuré | 1 ability |
| 1029 | Drachnyen | blackAbaddon | HERO | `REGISTRY` | non mesuré | 1 ability |
| 1100 | SorcerousFacade | thousTzaangor | HERO | `REGISTRY` | non mesuré ; lire `case-171` (interaction attaque normale) | 1 ability |
| 1177 | LightOfSanguinius | bloodDante | HERO | `REGISTRY` | non mesuré | 1 ability |
| 1199 | DoomSiren | emperKakophonist | HERO | `REGISTRY` | non mesuré | 1 ability |
| 1116 | RadBombardment | admecDominus | HERO | `_NONCOMPARABLE` | non mesuré | 1 ability (sélecteur ligne runner) |
| 1036 | FrenziedFiring | blackObliterator | HERO | `_SPECIAL` | **mesuré côté décision** (`case-61` : le port rendait 1 coup au lieu de la formule) — face combat toujours NO-OP | 1 ability |
| 1137 | MurderousSwing | worldExecutions | HERO | `_SPECIAL` | **mesuré côté décision** (`case-108` : ×1,60 + 4 events) — face combat toujours NO-OP | 1 ability |
| 1171 | DakkaDakkaDakka | orksKillaKan | HERO | `_SPECIAL` | non mesuré | 1 ability |
| 1192 | NovaBoost | tauBossRiptide | **NPC** | NC | — | **NON PERTINENT** |
| 1194 | NovaShield | tauBossRiptide | **NPC** | NC | — | **NON PERTINENT** |

⇒ **18 dispatchables.** Les symboles natifs sont dans les tables §1.a.

> **Piège de lecture à ne PAS reproduire** : `port-roadmap.md` §6.3 dit « MurderousSwing 1137 DÉJÀ
> porté #108 » et §6.13 range DakkaDakkaDakka en « [opus]+prérequis » — dans les deux cas le port
> #108 est **la face DÉCISION seule** (`entities/abilities/active_ability.py`). La face COMBAT
> reste un NO-OP. Un tag « déjà porté » sans préciser la FACE est un faux constat.

**Fichiers touchés par un item de ce gisement** (base de la détection de collision) :

- `engine/runner/abilities/handler.py` — **collision systématique** : *tout* port d'ability y ajoute
  un import + une entrée `ABILITY_CLASSES`. Deux agents concurrents s'y croisent toujours.
- `engine/runner/abilities/<faction>.py` — modules existants : `admec, aeldari, astramilitarum,
  blacklegion, bloodangels, darkangels, deathguard, genestealer, necrons, orks, sisterhood,
  spacewolves, tau, tyranids, ultramarines, votann, worldeaters` (+ `loki/*` pour l'historique).
  **Pas de module** BlackTemplars / Custodes / EmperorsChildren / ThousandSons / AdeptusAstartes →
  un port de ces factions en CRÉE un (zéro collision).
- `engine/entities/effect_type.py`, `engine/entities/effects/factory.py` si l'ability pose un effet neuf.
- `engine/runner/operations/triggers/dispatch.py` si elle exige un vecteur d'event neuf.

---

## 3. Gisement 3 — `TARGETING_OPTIONS` : 75 abilities du registre sur 76 sans masque

**Symptôme chiffré** : `ABILITY_CLASSES` = 76 entrées ; **1 seule** (`WaaaghAbility`, 1058) porte
`TARGETING_OPTIONS`. Le backlog annonçait « 60 restantes » — le gisement a **grossi de 15** parce
que chaque port depuis #115 entre au registre sans son masque.

**Conséquence exacte** (lue dans `engine/runner/abilities/targeting.py`) :
`get_invalid_target_reason` et `get_invalid_caster_reason` commencent tous deux par
`options = getattr(ability, "TARGETING_OPTIONS", None)` ; `None` ⇒ **retour 0 immédiat**, aucun
gate. Le port accepte donc des casts que
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` refuserait (ami/ennemi, cible ==
caster, caster ayant bougé). Dégradation **permissive**, donc silencieuse en self-play.

- **Symbole natif** : `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` (le masque est le
  littéral passé par `<X>Ability$$.ctor` à `IdunBattle.Core.Services.TargetingOptions$$.ctor`) ;
  cascade consommatrice : `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`.
- **Piège documenté** (`targeting.py` docstring `TargetingOptions`) : l'overload **PRESET + flags**
  (`TargetingOptions..ctor(&opts, &preset, <flags>, 0)`, ex.
  `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor`) — le littéral
  visible n'est PAS le masque effectif. Recopier ce littéral serait FAUX. Ne renseigner que les
  masques EFFECTIFS lus.
- **Confrontabilité** : chaque ability du registre a déjà un porteur confrontable (elle est portée).
- **Taille** : **1 sous-système** si pris en lot (1 ligne/ability, lecture du ctor décompilé) ;
  se découpe naturellement par faction. La règle de non-régression est simple : un port qui entre
  au registre pose son `TARGETING_OPTIONS` dans le même commit.
- **Fichiers** : `engine/runner/abilities/<faction>.py` (attribut de classe) — **pas** `handler.py`,
  donc collision faible ; garde possible dans `tests/engine/runner/`.

---

## 3bis. Gisement 4 — les PASSIFS (207), hors du périmètre demandé mais plus gros que les trois

Non demandé par la tâche, mais il faut le nommer sinon la prochaine vague le rate : un **troisième
audit** existe, `scripts/python/audit_passive_ability_coverage.py`, et son verdict est plus lourd
que les trois gisements réunis.

Re-dérivé au commit courant :

```
passifs=207 | enum : TriggeredAbilityType=206, ActiveAbilityType=1
porte=46  zone-grise=11  gap=150
confrontables : gap=63  zone-grise=7
canaux : T=18, O=4, E=31, G=1, X=0, B=3
```

⇒ **63 passifs à porteur confrontable, non portés.** L'angle mort est **structurel** et vaut d'être
répété ici : un passif n'est PAS une active non castable, c'est une `TriggeredAbilityType` — un
objet d'un AUTRE enum. `audit_combat_ability_coverage.py` (le gisement 1) ne pouvait donc rien en
voir, et l'intersection nom-à-nom actives/passifs est **VIDE**. Cas fondateur : `HeavyGravCannon`,
qui expliquait un delta live/offline resté longtemps sans cause et n'apparaissait dans AUCUN audit.

⚠ **Homonymie à TROIS faces** à qualifier systématiquement : `EffectType 1291 = HeavyGravCannon`
(le nom CAPTÉ live) · `TriggeredAbilityType 1233 = HeavyGravCannon` (la CONFIG du passif) ·
`TriggeredAbilityType 1291 = SelfRepairMechanism` (**sans rapport**). 27 des 207 passifs sont
homonymes d'un `EffectType` : c'est exactement la population exposée à ce piège.

Détail par passif (canal, verdict, porteur, confrontabilité) : `docs/rl/passive-ability-coverage.md`
— **régénérer** plutôt que fusionner en cas de conflit.

---

## 4. Résidus NOMMÉS hors gisement — vérifiés OUVERTS au commit courant

Triés **symptôme mesuré > symptôme nommé > supposé**. Chacun a été relu dans le code ; la
référence de ligne est le point d'ancrage.

### 4.a — Symptôme MESURÉ (chiffres au dossier)

| # | Résidu | Symptôme chiffré | Symbole natif | Porteur / conf. | Fichiers | Taille |
|---|---|---|---|---|---|---|
| R1 | **Tuile d'ORIGINE dans les candidats d'ability du port, pas du natif** — `state_bridge._plans_for_unit` fait `cand_tiles.append(origin)` (`ai/state_bridge.py:318`) | S3 (`C4_02`, `emperNoiseMarine`) : natif `69 tgt=77 to=(3,3)` = **exactement** l'argmax du port une fois l'origine retirée (39.961) ; port rend `69 tgt=79 to=(2,2)` (41.886) | `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` (= `IBattleQuery` slot +0xe, `GetMovableTilesFor` **exclut** la tuile courante) ; branche `NullPosition` de `ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7` seulement si la liste est vide | tout hero du pool | `engine/ai/state_bridge.py` | **1 sous-système** — touche TOUTE unité qui attaquerait sans bouger ⇒ exige une passe d'agreement complète, pas un smoke |
| ~~R2~~ | ~~Gate d'IMMUNITÉ d'effet non porté~~ | **FERMÉ pendant la rédaction — cf. §5 (`42de74d`, #224)** | — | — | — | — |
| ~~R3~~ | ~~OVERWATCH : un seul tir par activation~~ | **FERMÉ pendant la rédaction — cf. §5 (`7c412b8`, #127)** | — | — | — | — |
| R4 | **Resolve slot-8 non matérialisé dans `execute_normal_like`** — `HitDamage.get_damage` court-circuite à `min == max` (`operations/damage_hits.py:49`) | splash Psyker : le live consomme **1 `genrand_int32` de plus que le port par volet splash** — constant, mesuré sur pool=1 et pool=2, absent quand le splash ne fire pas | `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` appelle `Next(v, v+1)` **sans gate largeur-1** | astraPrimarisPsy / tout Psyker du pool | `engine/runner/operations/damage_hits.py`, `damage_ops.py` | **1 effet** — ⚠ conditionner à la FAMILLE de factory native, pas à la largeur des bornes (le porter inconditionnellement casse Stormcaller 3-hit bit-exact) |
| R5 | **`test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` échoue** | **REPRODUIT au commit `7f47c29`** (run du 2026-07-26, 1 failed / 2 passed) : `res={'moved': (6,5), 'kind':'ability', 'ability': 17, 'target': 79}`, `d_bfs 3->3`, `hp 8536->8536`, `atk(ranged=True, hits=3)`. Deux anomalies dans la même trace : le move ne réduit pas la distance BFS, ET 3 coups infligent 0 dégât. `ability: 17` = le NormalAttack ABSTRAIT, alors que l'attaque normale est un id CONCRET par unité | `IdunBattle.AI.Tactics.…` (pass IA générique) + route d'attaque | admecDestroyer / Skitarii Vanguard (summon), dans le pool via son summoner | `engine/ai/*` (pass générique), `engine/runner/abilities/base.py` (NormalAttackType) | **1 sous-système** — pré-existant, pas une régression |
| R6 | **`execute_normal_like` et `additional_hits` restent TRONQUANTS** (`damage_ops.py:837-840` : `apply_all_modifiers(..., def_mods)` sans `round_materialize`, re-vérifié sur l'arbre rebasé) | la famille ATTACK d'`execute_ability_attack` a été basculée sur `Round(AwayFromZero)` le 2026-07-26 **sur mesure** (14 casts / 2 régimes d'armure : live == arrondi 14/14, == troncature 12/14, les 2 écarts exactement sur les fractions ≥ .5). Les deux autres vecteurs n'ont **aucune** mesure (note explicite `damage_ops.py:554`) | `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` (slot 0x10 de `…$$CalculateBaseDamageWithAllModifiers`) : `Fix64.Round(Mul(v, multiplier), AwayFromZero)` **inconditionnel** dès qu'un `Nullable<DamageModifiers>` HasValue | régime discriminant : les DEUX %-list vides **ET** la branche perçage du plancher gagne (armure haute + perçage élevé) | `engine/runner/operations/damage_ops.py` | **1 effet** par vecteur, mais **chacun exige sa campagne de datapoints** |
| R7 | **`execute_normal_like` ne threade pas `target_traits`** (`damage_ops.py:804-805` : `attacker_modifiers(...)` sans `target_traits` — re-vérifié sur l'arbre rebasé) | jumeau du prérequis levé pour `execute_ability_attack` le 2026-07-26, dont la mesure était **+443 = `extraDmg[50] × 160%`** de `HeavyGravCannon` (gate `HasTrait(target, 5=Mechanical)`) | `IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` — un SEUL collecteur natif, pas un par famille | aucun porteur de `BeastSlayer`/`MartialKatah`/`CondemnorStake`/`HeavyGravCannon` n'a d'attaque `normal_like` confrontée aujourd'hui | `engine/runner/operations/damage_ops.py` | **1 effet** (+ idem `additional_hits`) |
| R8 | **`--hp-target` remet `Armor`/`FixedArmor` à 0** (`rl_duel.py:349-359`) | mesuré : `adeptMorvenn` 2411 → 0, `necroWarden` 2008 → 0. **Le code le fait EXPRÈS** (commentaire « armure nulle → kill DÉTERMINISTE ») — le résidu réel est que `runner.md` ne le dit pas : il documente `--hp-target` comme « force `Health` ET `RemainingHealth` », point | — (outillage) | — | `.claude/skills/tacticus/references/runner.md` | **1 ligne de doc** — piège de mesure : tout test qui force les PV supprime SILENCIEUSEMENT l'étage armure, donc tout régime où la branche perçage du plancher mordrait |

### 4.b — Symptôme NOMMÉ (mécanique lue, pas encore chiffrée)

| # | Résidu | Symbole natif | Porteur / conf. | Fichiers | Taille |
|---|---|---|---|---|---|
| R9 | **Magnitude de `Chronometron_ExtraDamage` (1550)** — effet POSÉ (visible `decisionView`) mais INERTE. Les 3 entrées manquent à `attacker_ctx` (`{id, is_normal_attack, faction}`) : équipe de l'attaquant vs équipe de la SOURCE de l'effet, trait `Mechanical` de l'attaquant, compteur `TimesEffectApplied` par instance | `IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` (+ `$$CreateRemoveEffectTrigger` = `On(9)`, effet CONSOMMÉ au 1ᵉʳ coup allié) | necroChronomancer — **catalog_inject** (déjà confronté live, `case-92` §4) | `engine/runner/operations/damage_ops.py` (`attacker_ctx`), `engine/entities/effects/loki/*`, face prédiction | **1 sous-système** (élargissement d'`attacker_ctx` DEUX faces + compteur par instance) |
| ~~R10~~ | ~~Retrait de `InspiredToGreatness_OverrideLevel` (1180)~~ — **FERMÉ pendant la rédaction, cf. §5.0 (`b6d174c`, #114 résidus Tau)** | — | — | — | — |
| ~~R11~~ | ~~Phase 2 d'`EarlyWarningOverride` (effet 1145 inerte)~~ — **FERMÉ pendant la rédaction, cf. §5.0 (`b6d174c`)** | — | — | — | — |
| R12 | **Les 2 derniers consommateurs de `DSLFactory.Revive`** : `FuelledByFury` (`ultraTitus`) et `GhostRevive`/`TimeFlux` (`thousTerminator`). Base REVIVE portée (`864a371`) ; reste 3 points nommés pour FuelledByFury (émetteur de `On(PendingDeathAdded=3)` non localisé, contexte `TriggeringAbilityIs(FinalJustice)` non threadé, pose de l'effet 1324) et pour GhostRevive un vecteur `On(PreUnitMove=31)` + un effet portant une TUILE + un revive **non in-place** | `IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` (non porté, cf. `triggers/dispatch.py:836`) ; ancrage à hooker pour l'émetteur : `IdunBattle.MatchState$$AddDeath` ; `IdunBattle.Operations.…$$SetRevivePosition` | ultraTitus, thousTerminator — **HERO pool tous deux** | `engine/runner/operations/revive.py`, `operations/triggers/revive_effect.py`, `dispatch.py` | **2 abilities** (1 par consommateur) |
| R13 | **`AdaptiveStrategy` (1005, `necroWarden`)** — ⚠ **un prérequis sur trois est TOMBÉ** : le sous-système OVERRIDE-ATTAQUE existe désormais (`AddStatOverrideEffect`, `abilities/behaviours/stats.py:281`, 1ᵉʳ user #112/#114). Restent (1) `RelentlessMarch` 1004 (sans lui la branche `If(ActorHasTriggeredAbility) TriggerAbility(…)` est un no-op structurel) et (2) les nœuds `TriggerAbility` + `ActorHasTriggeredAbility` | `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour` ; `…Loki.RelentlessMarchAbility$$CreateBehaviour` | necroWarden — **HERO pool** | `engine/runner/abilities/necrons.py`, `handler.py`, `entities/behaviours.py` | **1 ability + 1 passif** |
| R14 | **Face DÉCISION des MoW** — `state_bridge._plans_for_unit` ne feede pas l'attaque d'une MoW à `_best_attack` (`origin=None`) ; `engine_decide(…, cid)` n'a aucune entrée pour un `casterId` de MoW (`_dv_units` les exclut). ⇒ AUCUNE ability de MoW n'est proposable, y compris celles dont la feuille NC est portée et validée live (1187 `ThriceBlessedConflagration`) | chemin natif dédié `aiPlaybookPredict` caster Machine (`case-172`) — ne PAS faire passer une entité sans position pour une unité | 8 MoW du pool | `engine/ai/state_bridge.py` (`_dv_units`, `_plans_for_unit`), `engine_validate.engine_decide`, `engine/playbook/scene.py` | **1 sous-système** — oracle utilisable : `aiStepDryRun` après `finish` des alliés (`aiDryRunAllUnits` n'itère que `EntityType.Unit`) |
| R15 | **`CalculateCustomUtility` — overlays non portés** : le compte réel est **16**, pas 20 (`playbook.REGISTRY` = 7, dont 6 overlays loki + `Repair`). Les 4 portés depuis `case-27` sont 1020 / 1029 / 1100 / 1199 — ce qui a créé 4 nouveaux `[-D]` (décision portée, combat NO-OP) | par overlay, cf. `case-27` (VA + formule mirroir par ligne) | mixte ; ⚠ le blocage « porteur MoW hors-plateau » est **levé côté COMBAT** (`a9714a4`) et « porteur hors pool » **levé** (`ab98129`) — reste le blocage DÉCISION = R14 | `engine/playbook/loki_custom.py`, `engine/playbook/__init__.py` | **1 sous-système par débloqueur**, puis 1 overlay/ability |
| R16 | **Stat-mods EAGER présents AU SEED : appliqués mais non revertables** — famille `ActOfFaith_Effect` (1017), `ProtectorImperative`/`ConquerorImperative` (1247/1248). Leur magnitude se calcule depuis le `StatsComponent.ctx` du porteur, or l'attribution du seed précède la création du `UnitStats` (`UnitContext.from_snapshot` : `attributed` avant `seed_unit_stats`) et ActOfFaith lit `StatPart.INITIAL` du crit-damage → **dépendance circulaire à démêler** | `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` (le volet des effets posés EN JEU est porté : `operations/effects.py::revert_stat_mods_of_removed_effects`) | adeptCanoness / adeptRetributor (ActOfFaith), admec* (Doctrina) — **pool** | `engine/runner/snapshot.py`, `engine/runner/operations/effects.py`, `engine/entities/stats.py` | **1 sous-système** — le débloqueur *alternatif* (exposer `StatModificationComponent`) exige rebuild+reinject : **hors périmètre**, mais le chemin offline ne l'exige pas |
| R17 | **Ordre intra-groupe de `PerformAIAction(asGroup=1)`** — natif = argmax d'utilité du picker ; port = ordre du sélecteur. Live observé : les 2 gardes de SupremeCommander agissent dans l'ORDRE INVERSE de leur spawn. Manque la sémantique des 8 ids de `UtilityBucket` (aucun dump d'enum) + le scoreur par-unité derrière le slot 1 | `IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$PickNextUnit` (slot 1 de `operator+0x28`, picker `operator+0x30`) ; `…DefaultGroupOperator$$.ctor` = 8 `IdunBattleLogic.AI.Utilities.UtilityBucket` (ids 0x4a/0x44/0x45/0x4c/0x4b/0x49/0x47/0x48) | astraCreed, orksWarboss — **pool** | `engine/runner/abilities/behaviours/summon.py`, `engine/ai/*` | **1 sous-système** — sans incidence tant que les unités du groupe sont interchangeables |
| ~~R18~~ | ~~Bouclier × limites sur la voie ability~~ — **FERMÉ pendant la rédaction, cf. §5 (`21494b6`, #67b)**. Il a engendré N1-N3 | — | — | — | — |
| N1 | **Ciblage d'`ArcaneShield` sur un allié NON-Chaos** : écart port/natif nommé par `21494b6` (`case-67` §6.5) | à relire dans `IdunBattleLogic.Entities.Abilities.…ArcaneShieldAbility` | thousSorcerer — **HERO pool** | `engine/runner/abilities/` (ThousandSons) | **1 effet** |
| N2 | **Famille ATTACK en bounds-mode : cap SCALAIRE vs cap sur les CELLULES** (`case-67` §6.5) — les deux familles ont des ordres opposés ; le fix #67b est gaté sur `is_attack_damage_op`, la face ATTACK bounds-mode n'a pas été confrontée | `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` vs `…$$CalculateDamageOperation` (`Math.Max(0, dmg - shieldPart)`) | pool | `engine/runner/operations/damage.py`, `damage_ops.py` | **1 effet** |
| N3 | **Ordre réduction × bouclier sur `execute_normal_like`** — indiscernable à `spread_pct = 0`, donc jamais mesuré (`case-67` §6.5) | idem N2 | pool | `engine/runner/operations/damage_ops.py` | **1 effet** — exige un montage à `spread_pct != 0` |
| N5 | **Chaîne `&` derrière un `AddEffect` REFUSÉ** : confond non éliminé par #224 — quand la pose est abandonnée par le gate d'immunité, la suite de l'`op_and` est-elle exécutée ? (`case-224-effect-immunity-gate` §5) | `IdunBattle.Operations.AddEffectOperation$$Execute` (abandon avant matérialisation) | darkaAsmodai / blackAbaddon — **pool** (le montage #224 existe déjà) | `engine/runner/operations/effects.py`, `engine/entities/behaviours.py` | **1 effet** |
| N6 | **`test_hailstrike_phase2_live` rouge** — échec PRÉ-EXISTANT, vérifié par stash et signalé **indépendamment par deux commits** (`7c412b8` et `ad5692e`) ⇒ ce n'est pas un artefact de branche. Jumeau de R5 : un test de garde rouge que personne ne possède | — | darkaStormSpeeder (MoW) / Hailstrike — cf. `case-117` | `engine/runner/abilities/darkangels.py`, test associé | **1 ability** (diagnostic d'abord) |
| R19 | **Nature du coup, résidus** : (a) le mode `AttackRangeType.Both` (3) n'est pas modélisé — le port DÉCLARE la nature (`is_melee` du behaviour) là où le natif la CALCULE ; (b) famille ABILITY — la mesure #45f dit que le natif reçoit des modifiers ATTAQUANT **vides**, le port ne les vide pas (il se contente de rendre les gates inertes) ⇒ les bonus SANS gate de nature (`DecoysAndMisdirection`, `RapidAssault`) y passent encore | `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` = `AreUnitsInMelee(attPos, tgtPos)` pour ce mode ; `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` | pool | `engine/runner/operations/damage_ops.py`, `engine/services/damage_modifiers.py` | **1 effet** chacun |
| R20 | **`SpawnReplica` ré-implémente `PerformAIAttack` à la main** — ScarabSummon 1047 on-appearance : `_nearest_enemy` + `AttackDamageOperation.execute` recodés, **sans gate de portée ni dispatch after-hit**, alors que le corps unique existe (`abilities/loki/summon.py::perform_ai_attack_from_current_position`, de-forké le 2026-07-26) | `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttack` — MÊME `PerformAIAbilityUnitBehaviour` que `…FromCurrentPosition` à un champ près : `+0x78` (budget de déplacement) fourni par l'appelant au lieu de `factory+0xb8 = Direct(0)` | necroSpyder (ScarabSummon) — **HERO pool** | `engine/runner/abilities/behaviours/summon.py`, `abilities/loki/summon.py` | **1 effet** (rabattre sur le corps unique ; l'amount reste inerte tant qu'aucun étage ne fait bouger un summon avant son attaque) |
| R21 | **`UnitFlag.ArrivedAtFinalTile` (1) non posé par `MoveUnitOperation`** — `movement.py:98` n'appelle que `set_moved_flag` ; le flag n'est posé que par `FinishUnitTurnOperation` (`operations/turnflow.py:67-68`) | le natif l'ajoute juste après `SetMovedFlag`, gaté par l'option `MoveUnitOptions` @+0x0 | pool | `engine/runner/operations/movement.py` | **1 effet** — aucun consommateur porté n'en dépend aujourd'hui ; à câbler avec le reste des `MoveUnitOptions` |
| ~~R22~~ | ~~Migration du DoT de tuile `EnvFireTile` vers la route `AbilityDamageOperation`~~ — **FERMÉ pendant la rédaction, cf. §5 (`ad5692e`)**. ⚠ ce résidu était classé « latent / numériquement équivalent » : **il était FAUX** — tick natif 25000 vs port 100000 sur `darkaTerminator`, et `astraYarrick` (Resilient) SURVIT à 1 PV côté natif alors que le port le TUAIT. Leçon : « latent » sans mesure ne veut rien dire | — | — | — | — |
| N4 | **Le STADE natif du refus `TerminatorArmour` / `Pinned` n'est pas identifié** (`case-224-effect-immunity-gate` §5) : `PinnedEffect` n'override PAS `EntityIsImmuneToEffect`, et la base ne teste que le trait `Immune`, qu'aucune unité ne porte — le port #224 a fait un **collapse assumé**. Le comportement est live-correct sur 4 porteurs, mais le chemin natif exact reste inconnu | `IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` ; `IdunBattle.Entities.Effects.Loki.PinnedEffect$$CreateActiveCondition = Not(HasTrait(0x40f))` | blackAbaddon / deathTyphus / blackObliterator — **pool** | `engine/entities/effects/*` | **1 effet** — ⚠ **candidat `fable`** (collapse assumé, le décompilé ne rend pas le stade) |
| R23 | **`audit_kit_coverage.py` sous-compte la face DÉCISION** (cf. §2) : `collect()` ne lit que 2 des 3 registres → `[-D]` affiché 14 au lieu de 20, et des `[--]` faux (1191 MartialInspiration) | — (outillage) | — | `scripts/python/audit_kit_coverage.py` | **1 effet** (~3 lignes) — rend l'audit fiable pour toutes les vagues suivantes |
| R24 | **`tests/conftest.py` écrit ses state-files dans `data/`** (`STATE_PREFIX = ROOT/"data"/"_pytest_duel_state"`, `conftest.py:52-53`) alors que `data/` est VERSIONNÉ depuis le 2026-07-26 (`data/` = ce qu'on LIT, `logs/` = ce qu'on ÉCRIT). Unlinkés au teardown, donc invisibles la plupart du temps — une passe interrompue les laisse dans `git status` | — (outillage) | — | `scripts/python/tests/conftest.py` | **1 ligne** — contournement en attendant : `TACTICUS_PYTEST_STATE_PREFIX=<worktree>/logs/runners/...` |
| R25 | **3 constantes de gameplay encore FIGÉES dans les tests** (#96, lots A-D livrés) : `test_damage_crushingclaws_live.py:178` `main["hits"] == 2` (= `nrOfHits` de CrushingClaws) ; `test_fragstorm_migration_live.py` cap `nrOfTargets` (= `GetNumberConstant(cfg, 0x11)`) écrit en dur ; `test_jakhal_stimms_live.py:288` `exp_loss = round(hp0 * 25 / 100)` (`hpPct` en dur) | oracle = la CONFIG (`gameconfig.ability(id).constants`) — les 3 sont des valeurs BRUTES passées telles quelles aux nœuds DSL | — | `scripts/python/tests/engine/runner/` (3 fichiers), oracles centralisés dans `tests/engine/runner/_config_oracle.py` | **1 effet** (lot de 3 fichiers) |
| R26 | **Rider OVERKILL de `ThrillSeekers`** (face PRÉDICTION) : le port passe `allow_flag=0` en dur (`services/trait_damage_limits.py::compute_prediction_overkill`) | `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` force son `allow_flag` à 1 quand l'attaquant `HasTrait(0x420)` ET `HasEffect(0x59a)` ET (`default_flag` OU le flag de crit) | emper* — **pool** | `engine/services/trait_damage_limits.py`, face prédiction | **1 effet** — biais UNILATÉRAL (le port sous-estime l'overkill des porteurs *Thrilled* qui critent, donc `OverkillUnitUtility`) |
| R27 | **Seuil `should_evaluate` de BlackRage** : `playbook/noncomparable/black_rage.py:77` gate à `hp <= hpmax * 0.5` fixe, alors que la RE combat montre un `hpPct` **par niveau** (30 → 50 %) — correct seulement au niveau max | `IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$…` | bloodDeathCompany — **HERO pool** | `engine/playbook/noncomparable/black_rage.py` | **1 effet** — n'affecte pas la garde actuelle (Lucien caste à hp=1) |
| R28 | **`PickRandomly` — ordre d'énumération du pool quand `len(pool) > amount`** : la LOI de consommation est close et bit-exacte (`_pick_randomly_n`, `abilities/loki/splash.py:396-403`, mirror 1:1) ; reste que le natif tire dans l'ordre du sélecteur source (ECS, non trié) et le port id-trie → **QUI** est piqué peut différer (Fragstorm, PlasmaCannon >2 derrière, BringerOfDespair >1 adjacent, Harbinger, Supercharge, SquigMine). Sous-résidus frères : `Fragstorm` tire des **HEXES** pas des occupants (le cardinal du pool diffère) ; `AddForcedTargetsAndUpdateCandidates` non porté (`ignoreForcedTargets` @+0x38 FAUX partout → le natif pré-remplit le résultat avec `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets(caster)`, ce qui RÉDUIT le nombre de tirages) ; ~~les 4 sites `First(…)` de placement~~ — **FERMÉ pendant la rédaction par `fc23f1e` (case-130 SS5)** : les 4 nœuds sont portés (`SortByDistance`, `SortTilesByUtilityForSummon`, `Randomize`+`SortByFormula`, `First`), le tirage parasite retiré, l'ordre SOURCE natif (`boardGraph.neighbours`) branché | `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` | pool | `engine/runner/abilities/loki/splash.py`, sélecteurs (⚠ `operations/spawn.py` vient d'être réécrit par `fc23f1e`) | **1 sous-système** réduit à 3 sous-items (porter l'ordre du sélecteur source + le sélecteur en tuiles + les forced-targets) |
| R29 | **`case-61` — canal de coups des abilities, résidus** : (b) `On(PreAttack=5)` absent du vecteur ability (**fidèle** : le natif l'émet depuis `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteNormalAttack`) ⇒ sur ce vecteur `LetTheGalaxyBurn` ne s'arme que par `TargetHasTileEffect` ; (c) per-coup non bit-exact contre `templChampion` (même nb de coups, dégât différent — effets `MartialSuperiority`/`RapidAssault_ExtraDamage` de la cible ; le témoin `necroWarden` est bit-exact) ; (d) flag `Moved` absent de la face PRÉDICTION (×1,25 uniforme `HeavyWeapon_ExtraDmg` sur tout caster ranged déjà déplacé — débloqueur = exposer `UnitFlagsComponent`, **rebuild requis**) | — | pool | face prédiction | **1 effet** chacun — à promouvoir si un miss d'agreement les fait surface |
| R30 | **Substrat MULTI-HEX** (une unité occupant N tuiles) — MESURÉ : `DutyEternal` (1158) spawn `ultraSmnDreadnought` sur **3 hexes** (1 squad, 3 `UnitFoot`) ; le moteur offline modélise 1 `PositionComponent` par unité | `IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$ExecuteBehaviour` (`RemoveMachine` + `Spawn(ThreeTileUnitSpawnShape)`) | ultraDreadnought (MoW pool) ; probablement aussi `AetherStride` | `engine/runner/components.py`, `state.py`, pathfinding, ciblage | **1 sous-système** (N pieds par squad : occupation / adjacence / ciblage / blocage pathfinding) — **le plus gros de la liste** |

### 4.c — Reste en VEILLE (à promouvoir seulement sur miss d'agreement)

Vérifiés présents, sans symptôme actionnable aujourd'hui : résidus MV71 (`case-61bis` §6/§8/§9),
per-player 1180 (`case-31`), `ReachedSummonCap` (`case-38` §4 — branche `IsActive` sans caller
connu), `LordOfTempests` AddIce (`case-35` §4), `LivingMetal` swarm no-wake top-off (`case-203`
§5, chemin jamais atteint sous le member-cap), les 2 résidus `move` (#17, nature RNG),
arc arrière NON dégénéré du push (`case-push-distance` §5 — sans objet pour un pousseur adjacent),
trait `Unstoppable` 1042 (à câbler DANS la tranche movement-stop #131/B4, sinon
registered-but-dead), `#202` face DÉCISION Abraxas non confrontée oracle (au premier walk
Thousand Sons), `#5` chantier `DslContext` live-state (architecture à poser).

### 4.d — HORS PÉRIMÈTRE de cet inventaire

- **`[fable]`** (non inventoriés, par consigne) : arbitrage Comparable `ExcruciatingFrequencies`
  vs attaque normale ; étage d'ARRONDI quand la %-list est vide sur les vecteurs restants ; coups
  post-mortem / dérive du flux MT ; crit-roll non tiré à cc=0 sur la voie ABILITY multi-hit.
- **Bloqués par une fenêtre d'atelier vide** (exigent rebuild + reinject, donc pas du RE) :
  `StatModificationComponent`, `ChildComponent.ParentId`, `EffectComponent.IsActive`,
  `UnitFlagsComponent` dans `combatSnapshot`, stats résolues des MoW (`EntityType.Machine` dans
  `combatSnapshot.allUnits` et `statModSources.targetUnits`).
- **NON PERTINENTS** : `Impervious` (28) et cap boss `0x5d4` — tous les porteurs sont des boss npc.

---

## 5. PÉRIMÉS — à sortir du backlog / de la roadmap

### 5.0 — Fermés PENDANT la rédaction de cet inventaire (rebase du 2026-07-26)

Ces quatre-là étaient OUVERTS sur `7f47c29` et FERMÉS sur `21494b6`. Ils sont listés à part parce
qu'ils **mesurent la vitesse de péremption** : 4 résidus fermés en une soirée. Un backlog relu à
J+3 ment déjà.

| Résidu inventorié | Commit | Ce qu'il laisse ouvert |
|---|---|---|
| **R2** gate d'immunité d'effet | `42de74d` (#224) | **N4** (stade natif du refus TerminatorArmour/Pinned — collapse assumé, candidat `fable`) et **N5** (chaîne `&` derrière un `AddEffect` refusé) |
| **R3** overwatch un seul tir par activation | `7c412b8` (#127) | rien de nommé ; le port est passé par le flag natif `EffectComponent.IsActive @+0x5c` (`BaseEffect.active`) + le vecteur `On(AttackDamageAttack=10)` — pas par le marqueur ad hoc que le backlog suggérait |
| **R18** bouclier × limites, voie ability | `21494b6` (#67b) | **N1** (ciblage ArcaneShield allié non-Chaos), **N2** (famille ATTACK bounds-mode), **N3** (ordre réduction × bouclier sur `execute_normal_like`) |
| **R22** DoT de tuile `EnvFireTile` → route `AbilityDamageOperation` | `ad5692e` | rien de nommé. ⚠ le résidu était étiqueté « latent, numériquement équivalent » — **c'était faux** : 4× d'écart mesuré, et un kill fantôme sur un porteur `Resilient` |
| **R10** retrait de `InspiredToGreatness_OverrideLevel` (1180) | `b6d174c` (#114 résidus Tau) | rien de nommé ; a produit les primitives réutilisables `is_active_ability`, vecteur `On(0xc)` |
| **R11** phase 2 d'`EarlyWarningOverride` (effet 1145 inerte) | `b6d174c` | rien de nommé ; a produit `turns_until_unit_owner_turn`, `has_death_reason`, `UnitComponent.death_source` |
| — | `7c412b8` + `ad5692e` | **N6** : `test_hailstrike_phase2_live` rouge, signalé indépendamment par les deux |

| **R28**, sous-item « TRI natif des 4 sites de placement `First(…)` » | `fc23f1e` (case-130 SS5) | R28 reste ouvert sur ses **3 autres** sous-items (ordre du sélecteur source, Fragstorm en HEXES, `AddForcedTargetsAndUpdateCandidates`) |

**Cadence mesurée pendant la rédaction de ce document** : **6 résidus entiers fermés** (R2, R3,
R10, R11, R18, R22) **+ 1 sous-item** (R28/placement), et **6 résidus neufs** (N1-N6), en une
soirée, sur **trois rebases successifs**. C'est le chiffre à retenir : un backlog relu à J+3 décrit
un arbre qui n'existe plus. **Re-confronter avant de dispatcher n'est pas une précaution, c'est la
seule façon d'obtenir une file juste** — et c'est pourquoi cet inventaire porte son commit de base
en tête plutôt qu'une date.

### 5.1 — Entrées à sortir du backlog / de la roadmap

| Entrée | Verdict | Commit qui l'a fermée | Preuve |
|---|---|---|---|
| **`#PAI-c` — consommateurs de `PerformAIAction` restants** (Waaagh 1058, SendInTheNextWave 1016, Incursion 1021, Poxwalkers 1040, retrofit CultDemagogue 1179) | **PÉRIMÉ** | `3f7b9d1` (2026-07-25) « #94 consommateurs SPAWN/AI-CONTROL » | les 5 ids sont dans `ABILITY_CLASSES` (`WaaaghAbility`, `SendInTheNextWaveAbility`, `IncursionAbility`, `SpawnPoxwalkersAbility`, `CultDemagogueAbility`) |
| **FireOfAbsolution, volet feu-sur-cible « non modélisé par `execute()` »** | **PÉRIMÉ** | `ac1144f` (2026-07-17) « #149 slice-14 DSL FireOfAbsolution » (+ `8b34e7f` fix friendly-fire) | `operations/triggers/loki/fire.py::fire_of_absolution_tree` porte les 3 volets, dont l'ignite `Foreach(AdjacentTiles(Target()), Maybe(30, SetOnFire(Fire)))` ; dispatché par `dispatch.py:623` `_fire_of_absolution_after_attack` |
| **« Harnais cast-par-MoW hors-plateau — 17 items BLOQUÉS, `fable` (prouver le cast MoW en runner) »** (roadmap §4.1) | **PÉRIMÉ côté COMBAT** | `a9714a4` (2026-07-25) « débloqueur cast MoW hors-plateau » | 13/16 abilities MoW castent sans mise en scène (sweep `probe_mow_cast.py`), les 3 restantes étaient des prédicats de ciblage, **portés + validés** (`case-mow-targeting-predicates`). **Restent bloqués** : `DutyEternal` (multi-hex, R30) et la **face DÉCISION** (R14) |
| **« 1169 PlagueburstMortar / 1148 DaemonicOrdnance / 1142 MalleusRocketLauncher — BLOQUÉ harnais »** (roadmap §5.2) | **PÉRIMÉ côté COMBAT** | `a9714a4` + `bf61e8b`/`34872ac`/`f4591dd` (#90) | les **trois** sont dans `ABILITY_CLASSES` (`PlagueburstMortarAbility`, `DaemonicOrdnanceAbility`, `MalleusRocketLauncherAbility`) |
| **« porteur hors pool ⇒ inconfrontable »** (`case-27` lignes Chronometron 1226 / HealingBalms_Heal 1212 / SavageEchoes 1230 ; `case-220` §6.10 Votann ; `case-mow-offboard-cast` §7 `thousDaemonPrince`/`necroReanimator`) | **PÉRIMÉ** | `ab98129` (2026-07-25) « #92/#54 injection de porteurs au catalogue » | 10 porteurs confrontés live (4 Votann, 2 MoW, `adeptCelestine`, `bloodTerminator`, `tauFarsight`, `necroChronomancer`) ; 1226 et 1230 sont depuis PORTÉS |
| **`#116-r` prérequis (2) « sous-système OVERRIDE-ATTAQUE (`AddStatOverrideEffect` + blueprint `StatOverrideEffect`) »** | **PÉRIMÉ (prérequis levé)** | `71dca97` (#112 ExemplarOfHate) et `d67b6ac` (#114 InspiredToGreatness) | `AddStatOverrideEffect` existe (`abilities/behaviours/stats.py:281`) et a deux users runner |
| **`#217` « 27 actives `[-D]` »** | **CHIFFRE PÉRIMÉ** | ports #94/#112/#113/#114/#116/#117 | **20** au commit courant, dont 18 dispatchables (§2) |
| **`#115` (a) « renseigner `TARGETING_OPTIONS` sur les 60 autres abilities du registre »** | **CHIFFRE PÉRIMÉ (à la hausse)** | — | **75** sur 76 (§3) |
| **`case-27` « 20 résidus »** | **CHIFFRE PÉRIMÉ** | #112/#116 (overlays 1020/1029/1100/1199) | **16** ; `playbook.REGISTRY` = 7 |
| **`port-roadmap.md` en-tête : « 119 kits avec du travail, 249 items, 16 abilities portées combat »** | **CHIFFRE PÉRIMÉ** | — | **101 kits / 139 items / 75 portées** — `kit-coverage.md` et `combat-ability-coverage.md` (générés) étaient DÉJÀ à jour |
| **`port-roadmap.md` §3 P0 : 16 des 26 lignes sont PORTÉES** | **PÉRIMÉ ligne à ligne** | #94/#112/#113/#114/#116/#117/#204/#205… | portées (16) : 1113, 1163, 1151, 1002, 1037, 1082, 1166, 1016, 1040, 1021, 1077, 1122, 1202, 1000, 1092, 1081. Restent ouvertes (10) : 1153, 1191, 1117, 1039, 1121, 1038, 1090, 1129, 1183, 1050. Et le §3 **rate 8 `[-D]`** que l'inventaire §2 liste : 1020, 1029, 1036, 1100, 1116, 1137, 1171, 1199 |
| **`port-roadmap.md` §5.2 : 1009 ResurrectionOrb, 1058 Waaagh, 1028 SupremeCommander, 1226 Chronometron, 1230 SavageEchoes** | **PÉRIMÉ** | `dbc9379`, `3f7b9d1`, `85b5d1f` | tous dans `ABILITY_CLASSES` |
| **`getstuckin_combat_chance` code les deux chances en dur** | **PÉRIMÉ** (déjà barré au backlog) | `886335f` (2026-07-26) | — |
| **`case-220` §6.17 prérequis « canal PIERCING attaquant »** | **PÉRIMÉ** (déjà corrigé dans `case-220/admec.md`) | `8341bd1` (#113) / `169b4b2` (#117) | le vrai prérequis manquant était `target_traits` non threadé, levé le 2026-07-26 |

---

## 6. Ordre de dispatch conseillé (valeur décroissante)

1. **R1 tuile d'origine** — symptôme mesuré, cause localisée à UNE ligne
   (`state_bridge.py:317-318`), impact transverse. Exige une passe d'agreement complète, pas un
   smoke : le prévoir dans la tâche.
2. **Gisement 2 (§2), 18 items** — un agent par ability, un `[-D]` à la fois. Prioriser ceux dont
   la face décision est déjà mesurée (1036 FrenziedFiring, 1137 MurderousSwing) : l'oracle existe.
3. **R23** (3 lignes) — à faire AVANT la vague suivante : sans lui, l'audit continue de mentir sur
   `[-D]` et sur les `[--]`.
4. **R5** et **N6** — deux tests de garde ROUGES que personne ne possède, dont un re-reproduit ce
   jour. Un test rouge toléré est un oracle perdu.
5. **R4 resolve slot-8**, **R9 Chronometron**, **N1-N3** (les trois résidus laissés par #67b) —
   symptômes mesurés ou cause nommée, taille contenue.
6. **Gisement 4 (§3bis), 63 passifs confrontables** — le plus gros volume, et il est INVISIBLE des
   deux audits historiques. À traiter en parallèle du gisement 1 (il ne touche PAS `handler.py`,
   donc pas de collision avec les ports d'actives).
7. **Gisement 3 (§3)** — par faction, ou en règle de non-régression sur chaque nouveau port.
8. **Gisement 1 (§1), 49 items restants** (67 − les 18 du gisement 2) — piocher par faction ;
   les 11 de §1.b n'ont plus d'obstacle de harnais.
8. **R14 face décision MoW**, **R30 multi-hex** — sous-systèmes, à isoler.
9. **R24, R25, R8** — dette d'outillage / de tests, très peu coûteuse.

**Ne PAS dispatcher `N4`** en `[opus]` : c'est un collapse assumé que le décompilé ne tranche pas
— candidat `fable-solver`, et sans urgence (le comportement est live-correct sur 4 porteurs).

## 7. Collisions entre agents concurrents

| Fichier | Qui le touche | Risque |
|---|---|---|
| `engine/runner/abilities/handler.py` | **tout** port d'ability (gisements 1 et 2) | **ÉLEVÉ** — conflit textuel garanti si 2 agents portent en parallèle. Conflit trivial (2 lignes ajoutées), mais à résoudre par l'auteur au rebase |
| `engine/runner/operations/damage_ops.py` | R4, R6, R7, R9, R19, N3 | **ÉLEVÉ** — 6 résidus s'y croisent. Ne pas dispatcher deux d'entre eux en même temps |
| `engine/ai/state_bridge.py` | R1, R14 | **ÉLEVÉ** — R1 (`_plans_for_unit`) et R14 (`_dv_units`, `_plans_for_unit`) touchent la MÊME fonction. **Sérialiser** |
| `engine/runner/operations/damage.py` | N2, R18 (fermé) | MOYEN |
| `engine/runner/operations/effects.py`, `engine/entities/effects/factory.py` | N5, R16 | MOYEN — le canal d'immunité #224 vient d'y atterrir |
| `engine/runner/operations/triggers/effect_triggers.py` | R11 | FAIBLE depuis #127 (R3 fermé) |
| `engine/runner/operations/triggers/dispatch.py` | R12, tout vecteur d'event neuf | MOYEN |
| `engine/runner/abilities/<faction>.py` | 1 par faction | FAIBLE — deux factions différentes ne se croisent pas |
| `engine/entities/effect_type.py`, `entities/effects/factory.py` | tout effet neuf | FAIBLE (ajouts en fin de liste) |
| `docs/rl/combat-ability-coverage.md`, `docs/rl/kit-coverage.md` | régénérés | **ne jamais fusionner un conflit** : régénérer (`audit_*.py`) |
