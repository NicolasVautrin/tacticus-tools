# Inventaire des résidus de portage — confronté au CODE (2026-07-27)

> **Pourquoi ce fichier.** `backlog.md` décrit des INTENTIONS horodatées, `port-roadmap.md` un
> découpage figé : ni l'un ni l'autre ne décrit l'état du code. Ce document est le résultat d'une
> **confrontation item par item au commit courant**. Chaque ligne porte un verdict
> **OUVERT / PÉRIMÉ / NON CONFRONTABLE**, et seul OUVERT produit une tâche dispatchable.
>
> **Base de la mesure** : commit `6110d37` (`origin/master` au rebase avant PR ; l'inventaire a été
> établi sur `e972c99` et **re-dérivé après rebase** — `6110d37` est un refactor de FORME des
> masques de ciblage, sa propre preuve de non-régression montre les 28 masques strictement
> identiques, et les trois audits re-joués rendent le même contenu au caractère près),
> build `gqfc5mff6c`, session Frida 3
> `running` (injectée le 2026-07-27 à 16:24 locale, **postérieure** au bundle `frida/dist/hooks.js`
> du même jour 16:13 — les 3 fixes d'outillage de `3c7a7ae` sont donc ACTIFS dans cette session),
> pool `rl_duel build --list-pool` rank 17 = **97 unités + 8 MoW**.
>
> **Ce que cette passe ajoute à la précédente** (`3f70c6d`, base `fc23f1e`) : **26 commits** se sont
> intercalés. Ils ferment **6 résidus supplémentaires** (R19b, R21, R23, N3-câblage, plus deux
> entrées `[fable]` du backlog qui étaient déjà fausses avant l'inventaire précédent : le crit-roll
> `cc=0` et les coups post-mortem), et ils déplacent **tous** les comptes de gisement. Le compte
> `TARGETING_OPTIONS`, qui EMPIRAIT structurellement, s'est **inversé** : 75 manquants → **53**.
>
> **Ce document n'est PAS auto-généré — mais tous ses comptes le sont.** Pour les re-dériver :
> `python audit_combat_ability_coverage.py`, `python audit_kit_coverage.py` et
> `python audit_passive_ability_coverage.py` depuis `scripts/python/` (le 3ᵉ interroge le pool
> live ; les deux autres sont offline). **`combat-ability-coverage.md` et `kit-coverage.md` étaient
> PÉRIMÉS au commit courant** — les régénérer produit un diff de 81 insertions / 87 suppressions
> (5 abilities portées sans régénération). `passive-ability-coverage.md`, lui, **était à jour** :
> les auteurs des 4 ports de passifs l'ont régénéré (`3848490` en dernier) ; seul un compteur
> interne de volume de code y bouge. Les trois sont régénérés dans le même commit que ce fichier.

---

## 0. Recalage des chiffres — TOUT a bougé en 24 h

| Chiffre | Inventaire du 2026-07-26 (`fc23f1e`) | RE-DÉRIVÉ au 2026-07-27 (`e972c99`) | Sens |
|---|---|---|---|
| actives castables | 171 | **171** | inchangé |
| `ABILITY_CLASSES` (entrées du registre) | 76 | **81** | +5 |
| actives portées COMBAT | 75 | **80** | +5 |
| actives **NO-OP combat** | 96 | **91** | **−5** |
| … dont **dispatchables** | 67 | **62** | −5 |
| … dont **non pertinents** (npc + summon-env) | 29 | **29** | inchangé |
| actives **`[-D]`** (décision portée, combat NO-OP) | 20 (méthode réfutée) | **15 lineup + 2 npc** | **−3** |
| kits lineup | 123 | **123** | inchangé |
| kits lineup **COMPLETS** | 22 | **28** | +6 |
| kits **avec du travail** | 101 | **95** | −6 |
| items manquants (kit-coverage) | 139 | **126** | −13 |
| registre **sans `TARGETING_OPTIONS`** | 75 sur 76 | **53 sur 81** | **−22 — la tendance s'INVERSE** |
| registre **sans `ABILITY_ATTACK_TYPE`** | 3 (constaté le 2026-07-27 au matin) | **0 sur 81** | **fermé** |
| passifs **portés** | 46 | **54** | +8 |
| passifs **gap** | 150 | **142** | −8 |
| passifs gap **confrontables** | 63 | **55** | −8 |
| overlays `CalculateCustomUtility` **non portés** | 16 | **15** | −1 (correction de comptage, cf. R15) |

**Les deux gisements « que notre propre cadence aggrave » ne l'aggravent plus.** `TARGETING_OPTIONS`
a reculé de 22 en une journée (`89518da` 10 DarkAngels/Aeldari/WorldEaters, `ff66741` 13
Necrons/Orks/Votann/GenestealerCults, plus les masques posés en même temps que chaque nouveau port).
`ABILITY_ATTACK_TYPE` est à **zéro manquant** : la garde `probe_120` étape 0 passe au commit courant.
La règle de non-régression du `CLAUDE.md` a donc pris — c'est le seul endroit de ce document où la
tendance s'est retournée, et il vaut de le noter avant que quiconque recopie « 60 restantes ».

---

## 1. Gisement 1 — les 91 actives NO-OP en combat

`AbilityHandler.visit_ActiveAbilityMessage` route tout `ActiveAbilityType` absent de
`ABILITY_CLASSES` vers un **NO-OP silencieux** (`ported:False`, 0 dégât, 0 effet, aucune erreur).

**Ventilation par confrontabilité** (gate HERO / MoW / SUMMON / NPC) :

| Verdict | N | Dispatchable ? |
|---|---|---|
| **HERO** — porteur lineup DANS le pool rank 17 | 47 | oui |
| **MoW** — porteur MoW du pool (harnais débloqué, `a9714a4`) | 2 | oui |
| **SUMMON** — porteur summon amené par un summoner du pool | 2 | oui |
| **HERO (catalog_inject)** — lineup absent du seed BC, injectable (`ab98129`) | 11 | oui |
| **SUMMON-ENV** — summon d'environnement, aucun summoner joueur | 8 | **NON CONFRONTABLE** |
| **NPC** — tous les porteurs sont npc | 21 | **NON CONFRONTABLE** |

⇒ **62 dispatchables, 29 non confrontables.** Taille par item = **1 ability**.

**Les 5 sorties depuis l'inventaire précédent**, toutes de la catégorie HERO-pool (d'où 52 → 47) :

| id | ability | porteur | commit |
|---|---|---|---|
| 1036 | FrenziedFiring | blackObliterator | `d2be96e` (#125) |
| 1116 | RadBombardment | admecDominus | `825f69f` (#128) |
| 1041 | BrazierOfHolyFire | adeptCanoness | `825f69f` (#128) |
| 1097 | Foehammer | spaceRockfist | `86fecad` (#131) |
| 1153 | HammerOfWrath | bloodIntercessor | `86fecad` (#131) |

**La liste nominative des 62 dispatchables et des 29 non confrontables n'est pas recopiée ici** :
elle est intégralement dérivable de `docs/rl/combat-ability-coverage.md` (régénéré dans ce commit),
et la ventilation par porteur est inchangée depuis l'inventaire précédent hors ces 5 lignes. La
**correction de méthode** qui l'accompagne reste valable et mérite d'être répétée :

> ⚠ La catégorie « SUMMON » se dérive de `constants.unitId` **ET** `unitId_2/3/4`. Ne lire que
> `unitId` classe à tort `SlashingDive` (1091, `thousSmnScreamer`) en non confrontable, alors que
> `MasterOfTheTutelaries` (`thousInfernalMaster`, dans le pool) pose le Screamer via `unitId_2`.

> ⚠ `catalog_inject` a fermé le verrou « porteur hors pool » (`case-92`, 10 porteurs confrontés live).
> Toute mention « porteur hors pool ⇒ inconfrontable » antérieure au 2026-07-25 est fausse.

**Fichiers touchés par un item de ce gisement** : `engine/runner/abilities/handler.py` (**collision
systématique**, cf. §7) + `engine/runner/abilities/<faction>.py`. **Pas de module** pour
BlackTemplars / Custodes / EmperorsChildren / AdeptusAstartes → un port de ces factions en CRÉE un
(zéro collision).

---

## 2. Gisement 2 — les actives `[-D]` : la décision CHOISIT, l'exécution NO-OP

**Le gisement à valeur la plus haute** : divergence d'état *invisible* (aucune erreur,
`mutated=false`) en replay / self-play, sur des abilities que l'IA portée choisit réellement.

**Compte re-dérivé : 15 en lineup** (+ 2 npc non confrontables). Source = `kit-coverage.md`
régénéré, dont le critère `D` a été corrigé entre-temps.

> **La méthode de comptage de l'inventaire précédent a été RÉFUTÉE, et c'est important.** Il
> annonçait 20 en comptant `_NONCOMPARABLE_ABILITIES` comme un 4ᵉ registre de décision. `8e8518e`
> a tranché : y figurer signifie seulement que le port **CLASSE** l'ability NonComparable (il
> s'interdit de fabriquer un dégât depuis minDmg/maxDmg) ; son **UTILITÉ de décision** vit dans
> `PLAYBOOKS` et reste à porter. Compter ce registre comme `D` commet l'erreur **symétrique** du
> sous-comptage : déclarer porté ce qui ne l'est pas. L'audit le signale désormais à part
> (« NC classée, utilité NC non portée », 1 occurrence : RadBombardment — **qui a depuis reçu sa
> face combat**, donc l'occurrence a disparu).

Les 15, tous à porteur **HERO du pool** :

| id | ability | porteur | registre décision | symptôme | taille |
|---|---|---|---|---|---|
| 1129 | BloodyFury | worldTerminator | NC + `_SPECIAL` | non mesuré (structurel) | 1 ability (primitive `ChainLeftOverHitsAttackDamage`) |
| 1183 | VexillaMagnifica | custoVexilusPraetor | NC | non mesuré | 1 ability |
| 1121 | ItItches | tyranParasite | NC | non mesuré | 1 ability (multi-étage positionnel) |
| 1039 | RitesOfRestoration | adeptHospitaller | NC | non mesuré | 1 ability |
| 1117 | DefendTheDivineWork | admecManipulus | NC | non mesuré | 1 ability |
| 1050 | HolyDuel | templChampion | NC | non mesuré | 1 ability (3 classes d'effet) |
| 1038 | FoulInfusion | deathPutrifier | NC | non mesuré | 1 ability |
| 1090 | GrapnelLauncher | spaceHound | NC | non mesuré | 1 ability (≥6 primitives) |
| 1020 | HeraldOfTheApocalypse | blackHaarken | `REGISTRY` | non mesuré | 1 ability |
| 1029 | Drachnyen | blackAbaddon | `REGISTRY` | non mesuré | 1 ability |
| 1100 | SorcerousFacade | thousTzaangor | `REGISTRY` | non mesuré ; lire `case-171` (interaction attaque normale) | 1 ability |
| 1177 | LightOfSanguinius | bloodDante | `REGISTRY` | non mesuré | 1 ability |
| 1199 | DoomSiren | emperKakophonist | `REGISTRY` | non mesuré | 1 ability |
| 1137 | MurderousSwing | worldExecutions | `_SPECIAL` | **mesuré côté décision** (`case-108` : ×1,60 + 4 events) — face combat toujours NO-OP | 1 ability |
| 1171 | DakkaDakkaDakka | orksKillaKan | `_SPECIAL` | non mesuré | 1 ability |

**NON CONFRONTABLES** : 1192 `NovaBoost` et 1194 `NovaShield` (`tauBossRiptide`, npc-only).

**Sorties depuis l'inventaire précédent** : 1036 FrenziedFiring (`d2be96e`), 1116 RadBombardment
(`825f69f`), 1153 HammerOfWrath (`86fecad`) — les trois ont reçu leur face COMBAT.

> **Piège de lecture à ne PAS reproduire** : un tag « déjà porté » sans préciser la FACE est un
> faux constat. `port-roadmap.md` §6.3 dit « MurderousSwing 1137 DÉJÀ porté #108 » — le port #108
> est la face DÉCISION seule (`entities/abilities/active_ability.py`) ; la face COMBAT est un NO-OP.

Symboles natifs : `IdunBattleLogic.Entities.Abilities.Active.Loki.<Nom>Ability$$ExecuteBehaviour`
pour tous, sauf `MurderousSwing` et `LightOfSanguinius`
(`IdunBattleLogic.Entities.Abilities.Active.<Nom>Ability$$ExecuteBehaviour`, sans `.Loki`).

---

## 3. Gisement 3 — `TARGETING_OPTIONS` : 53 abilities du registre sur 81 sans masque

**Symptôme chiffré** : `ABILITY_CLASSES` = 81 entrées, **28** portent `TARGETING_OPTIONS`, **53**
n'en ont pas. Le gisement RECULE pour la première fois (75 manquants la veille).

**Conséquence exacte** (lue dans `engine/runner/abilities/targeting.py`) :
`get_invalid_target_reason` et `get_invalid_caster_reason` commencent tous deux par
`options = getattr(ability, "TARGETING_OPTIONS", None)` ; `None` ⇒ **retour 0 immédiat**, aucun
gate. Le port accepte donc des casts que
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` refuserait (ami/ennemi, cible ==
caster, caster ayant bougé). Dégradation **permissive**, donc silencieuse en self-play.

- **Symbole natif** : le masque est le littéral passé par `<X>Ability$$.ctor` à
  `IdunBattle.Core.Services.TargetingOptions$$.ctor` ; cascade consommatrice :
  `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`.
- **Deux formes du piège, les DEUX mesurées** : (1) l'overload **PRESET + flags**
  (`TargetingOptions..ctor(&opts, &preset, <flags>, 0)`) — le littéral visible n'est PAS le masque
  effectif ; (2) les abilities qui **n'appellent AUCUN ctor** et recopient les 0x40 octets d'un
  champ **statique**, le masque effectif étant la constante écrite par
  `IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28`. Les presets ne sont pas
  interchangeables (`statics+0x168` = `0x4002`, `statics+0x68` = `0x4000`) : sur 10 abilities d'un
  même lot, 9 valaient `0x4002` et JakhalStimms `0x4000`. **Lire ability par ability.**
- **Confrontabilité** : chaque ability du registre a déjà un porteur confrontable (elle est portée).
- **Taille** : **1 lot par module** (1 ligne/ability, lecture du ctor décompilé) ; le découpage
  naturel est le module de faction, qui est aussi la frontière de non-collision.
- **Fichiers** : `engine/runner/abilities/<module>.py` (attribut de classe) — **pas** `handler.py`,
  donc collision faible.
- **Depuis `6110d37`, un masque s'écrit en FLAGS NOMMÉS, plus en littéral hexadécimal** : le mirror
  `IntFlag` des 58 bits + 2 composites vit dans `engine/runner/abilities/targeting_rule.py`, et il
  est **GÉNÉRÉ** par `gen_targeting_rule.py` depuis `data/symbols/<build>/frida/enums.tsv` — ne pas
  le transcrire à la main. Ce commit a d'ailleurs corrigé deux paraphrases fausses posées à la main
  (bit 57 `TargetIsCasterOrEnemy`, et bit 51 `TargetIsNotSteppable` documenté **à l'envers**) : un
  masque écrit en hexadécimal laisse passer un bit faux sans trace.

**Ventilation par module — c'est la carte de dispatch** (modules absents = 100 % couverts :
`aeldari`, `darkangels`, `genestealer`, `necrons`, `orks`, `votann`, `worldeaters`) :

| module | avec | sans | ids sans masque |
|---|---|---|---|
| `splash` | 0 | 6 | 1000 GauntletsOfUltramar, 1051 Stikkbomb, 1065 ScythingTalons, 1078 Fragstorm, 1098 PlasmaGrenade, 1105 CrushingClaws |
| `strike` | 0 | 6 | 1014 ArmoriumCherub, 1018 ValkyrieStrike, 1043 ThunderousAssault, 1104 SpiritLeech, 1122 CordClaw, 1163 BlackRage |
| `blacklegion` | 0 | 5 | 1021 Incursion, 1022 BringerOfDespair, 1036 FrenziedFiringCombat, 1147 HadesAutocannons, 1148 DaemonicOrdnance |
| `deathguard` | 0 | 5 | 1037 RevitalizingMalignancy, 1040 SpawnPoxwalkers, 1042 FlailSwing, 1168 EntropyCannons, 1169 PlagueburstMortar |
| `summon` | 0 | 5 | 1007 ScarabHive, 1045 GetEmRuntz, 1047 ScarabSummon, 1096 MasterOfTheTutelaries, 1166 AberrantHypermorph |
| `tau` | 0 | 5 | 1077 EarlyWarningOverride, 1081 FightingRetreat, 1082 InspiredToGreatness, 1160 HeavyRailRifle, 1161 TwinSmartMissileSystem |
| `astramilitarum` | 0 | 4 | 1016 SendInTheNextWave, 1028 SupremeCommander, 1142 MalleusRocketLauncher, 1143 ForwardSpotter |
| `sisterhood` | 1 | 4 | 1025 SkyStrike, 1062 SanctorumMissile, 1187 ThriceBlessedConflagration, 1188 DevastatingRefrain |
| `ultramarines` | 0 | 4 | 1002 CombatRestoratives, 1003 DeathFromAbove, 1004 MortisRound, 1159 MacroPlasmaIncinerator |
| `tyranids` | 0 | 2 | 1112 AlphaWarrior, 1145 SporeMineLauncher |
| `admec` / `bloodangels` / `spacewolves` | 1 / 1 / 1 | 1 / 1 / 1 | 1139 SentinelDirectives · 1230 SavageEchoes · 1089 GreatFrostAxe |
| `imperative` / `mv71` / `quickening` / `stormcaller` | 0 | 1 chacun | 1118 DoctrinaImperatives · 1076 MV71SniperDroneSquadAttack · 1151 TheQuickening · 1113 Stormcaller |

⚠ `1151 TheQuickening` est précisément l'ability citée par la doctrine comme exemple de l'overload
PRESET + flags : ne pas recopier son littéral visible.

---

## 3bis. Gisement 4 — les PASSIFS (207) : le plus gros volume, et le plus invisible

Re-dérivé au commit courant (`audit_passive_ability_coverage.py`) :

```
passifs=207 | enum : TriggeredAbilityType=206, ActiveAbilityType=1
porte=54  zone-grise=11  gap=142
confrontables : gap=55  zone-grise=7
canaux : T=23, O=6, E=35, G=1, X=0, B=3
```

⇒ **55 passifs à porteur confrontable, non portés** (63 la veille — 8 fermés en 24 h par `b8af57a`
DestroyTheWitch/MartialSuperiority, `5c45389` CosmicHorror/SpiritualLeader, `137ef85`
RealityUnbound/TimeFlux-regen, `3848490` LionHelm/FearedInterrogator).

L'angle mort est **structurel** et vaut d'être répété : un passif n'est PAS une active non castable,
c'est une `TriggeredAbilityType` — un objet d'un AUTRE enum. `audit_combat_ability_coverage.py`
(gisement 1) ne peut rien en voir, et l'intersection nom-à-nom actives/passifs est **VIDE**.

⚠ **Homonymie à TROIS faces** à qualifier systématiquement : `EffectType 1291 = HeavyGravCannon`
(le nom CAPTÉ live) · `TriggeredAbilityType 1233 = HeavyGravCannon` (la CONFIG du passif) ·
`TriggeredAbilityType 1291 = SelfRepairMechanism` (**sans rapport**). 27 des 207 passifs sont
homonymes d'un `EffectType` : c'est exactement la population exposée à ce piège.

Détail par passif (canal, verdict, porteur, confrontabilité) : `docs/rl/passive-ability-coverage.md`
— **régénérer** plutôt que fusionner en cas de conflit.

---

## 4. Résidus NOMMÉS — OUVERTS au commit courant

Chacun a été **relu dans le code d'aujourd'hui** ; la référence `fichier:ligne` est la preuve.
Triés symptôme mesuré > symptôme nommé.

### 4.a — Symptôme MESURÉ (chiffres au dossier)

| # | Résidu | Symptôme chiffré | Symbole natif | Porteur / chemin en bataille | Fichiers | Taille |
|---|---|---|---|---|---|---|
| **R1** | **Tuile d'ORIGINE dans les candidats d'ability du port, pas du natif** — `state_bridge.py:318` fait toujours `cand_tiles.append(origin)` | S3 (`C4_02`, `emperNoiseMarine`) : natif `69 tgt=77 to=(3,3)` = **exactement** l'argmax du port une fois l'origine retirée (39.961) ; port rend `69 tgt=79 to=(2,2)` (41.886) | `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` (= `IBattleQuery` slot +0xe ; `GetMovableTilesFor` **exclut** la tuile courante) ; branche `NullPosition` de `ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7` seulement si la liste est vide | tout hero du pool | `engine/ai/state_bridge.py` | **1 sous-système** — touche TOUTE unité qui attaquerait sans bouger ⇒ exige une passe d'agreement complète, pas un smoke |
| **R5** | **`test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` ROUGE** | **RE-REPRODUIT au commit `e972c99`** (2026-07-27, 1 failed / 2 passed) : `res={'moved': (6,5), 'kind':'ability', 'ability': 17, 'target': 79}`, `d_bfs 3->3`, `hp 8536->8536`, `atk(ranged=True, hits=3)` — trace **identique au caractère près** à celle du 2026-07-26. Deux anomalies dans la même trace : le move ne réduit pas la distance BFS, ET 3 coups infligent 0 dégât. `ability: 17` = le NormalAttack ABSTRAIT alors que l'attaque normale est un id CONCRET par unité (`NormalAttackType` @0x28) | pass IA générique + route d'attaque | admecDestroyer / Skitarii Vanguard — **SUMMON**, amené par son summoner du pool | `engine/ai/*` (pass générique), `engine/runner/abilities/base.py` | **1 sous-système** — pré-existant, pas une régression. Aucun marqueur `xfail`/`skip` : le test est nu |
| **N6** | **`test_hailstrike_phase2_live` ROUGE — et plus large que documenté : 2 tests, pas 1** | **REPRODUIT au commit `e972c99`** (2 failed / 2 passed) : (a) `test_hailstrike_attack_trigger_live` — « le trigger 1507 n'a PAS fire offline (`after_hit=[]`) » ; (b) `test_hailstrike_pierce_envelope_live` — « dégât live **2700** hors des bornes du port AVEC le bonus **[1688, 2532]** ⇒ la magnitude du perçage portée est fausse ». Le second est un **symptôme de magnitude chiffré**, pas un simple test rouge | registre `ACTIVE_ABILITY_TRIGGERS` / gates du `CreateTrigger` (a) ; étage perçage (b) | darkaStormSpeeder (**MoW du pool**) / Hailstrike — cf. `case-117` | `engine/runner/abilities/darkangels.py`, `engine/runner/operations/triggers/*`, test associé | **1 ability** (diagnostic d'abord). Probe présente : `probe_123_hailstrike_phase2.py` |
| **R4** | **Resolve slot-8 non matérialisé dans `execute_normal_like`** — `HitDamage.get_damage` court-circuite toujours à `min == max` (`damage_hits.py:49-50`) ; le seul resolve matérialisé (`damage_hits.py:269-270`) est enfermé dans la branche `post_roll is not None` (bounds-mode) | splash Psyker : le live consomme **1 `genrand_int32` de plus que le port par volet splash** — constant, mesuré sur pool=1 et pool=2, absent quand le splash ne fire pas. Avec `spread_pct=0` (tous les call-sites amount-mode, `combat.py:156-158`) → **0 tirage/coup côté port** là où le natif en consomme 1 | `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` appelle `Next(v, v+1)` **sans gate largeur-1** | astraPrimarisPsy / tout Psyker du pool | `engine/runner/operations/damage_hits.py` (branche reduce-then-roll de `_run_hits`), `damage_ops.py::execute_normal_like` | **1 effet** — ⚠ conditionner à la FAMILLE de factory native, pas à la largeur des bornes (le porter inconditionnellement casse Stormcaller 3-hit bit-exact) |
| **R6** | **`execute_normal_like` ET `additional_hits` restent TRONQUANTS** — `damage_ops.py:981-984` et `additional_hits.py:130-133` appellent `apply_all_modifiers(..., def_mods)` **sans** `round_materialize` (re-vérifié au commit courant) | la famille ATTACK d'`execute_ability_attack` a été basculée sur `Round(AwayFromZero)` **sur mesure** (14 casts / 2 régimes d'armure : live == arrondi 14/14, == troncature 12/14, les 2 écarts exactement sur les fractions ≥ .5). Les deux autres vecteurs n'ont **aucune** mesure | `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` : `Fix64.Round(Mul(v, multiplier), AwayFromZero)` **inconditionnel** dès qu'un `Nullable<DamageModifiers>` HasValue | régime discriminant : les DEUX %-list vides **ET** la branche perçage du plancher gagne (armure haute + perçage élevé) | `engine/runner/operations/damage_ops.py`, `engine/runner/operations/additional_hits.py` | **1 effet par vecteur**, mais **chacun exige sa campagne de datapoints** |
| **R7** | **`execute_normal_like` ne threade pas `target_traits`** — `damage_ops.py:948` passe bien `target_id=target_id` (fermé) mais **pas** `target_traits`, qui reste un paramètre distinct de `attacker_modifiers` (`damage_model.py:351-352`) | jumeau du prérequis levé pour `execute_ability_attack`, dont la mesure était **+443 = `extraDmg[50] × 160 %`** de `HeavyGravCannon` (gate `HasTrait(target, 5=Mechanical)`) | `IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` — un SEUL collecteur natif, pas un par famille | aucun porteur de `BeastSlayer`/`MartialKatah`/`CondemnorStake`/`HeavyGravCannon` n'a d'attaque `normal_like` confrontée aujourd'hui | `engine/runner/operations/damage_ops.py` (+ idem `additional_hits`) | **1 effet** |
| **R8** | **`--hp-target` remet `Armor`/`FixedArmor` à 0, et DEUX documentations le taisent** | mesuré : `adeptMorvenn` 2411 → 0, `necroWarden` 2008 → 0. Le code le fait EXPRÈS (`rl_duel.py:349-359`, « PV bas ET armure nulle → kill DÉTERMINISTE ») ; le résidu est documentaire, et il est sur **deux** supports : `runner.md:155` (« force `Health` ET `RemainingHealth` », zéro mention de l'armure) **et** l'aide argparse `rl_duel.py:1970` (même omission) | — (outillage) | — | `.claude/skills/tacticus/references/runner.md`, `scripts/python/rl_duel.py` (help) | **2 lignes de doc** — piège de mesure : tout test qui force les PV supprime SILENCIEUSEMENT l'étage armure, donc tout régime où la branche perçage du plancher mordrait |

### 4.b — Symptôme NOMMÉ (mécanique lue, pas encore chiffrée)

| # | Résidu | Symbole natif | Porteur / chemin en bataille | Fichiers | Taille |
|---|---|---|---|---|---|
| ~~**R9**~~ **FERMÉ** | ~~Magnitude de `Chronometron_ExtraDamage` (1550) — effet POSÉ mais INERTE~~ → **PORTÉ ET VALIDÉ LIVE** (cf. §R9-clos ci-dessous). `attacker_ctx` porte désormais `is_unit` / `team` / `team_by_id` / `traits` sur les DEUX faces ; `BaseEffect.times_applied` (= `EffectComponent+0x6c`) est modélisé ; classe `ChronometronExtraDamageEffect` + trigger de retrait `On(9)` | `IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` (+ `$$CreateRemoveEffectTrigger` = `On(9)`, effet CONSOMMÉ au 1ᵉʳ coup allié) | necroChronomancer — **catalog_inject** (confronté live, `probe_r9_chronometron.py`) | `engine/runner/damage_model.py`, `engine/playbook/prediction/_shared.py`, `engine/entities/effects/{base,factory}.py` + `loki/damage_reduction.py`, `engine/runner/operations/{effects.py,triggers/loki/chronometron.py}` | — (clos) |
| **R12** | **Les 2 derniers consommateurs de `DSLFactory.Revive`, tous deux OUVERTS** — ⚠ `137ef85` (« TimeFlux (regen) ») ne ferme PAS ce résidu : le port lui-même le dit, `dispatch.py:280-286` enregistre `"TimeFlux": [TimeFluxRegenAbility]` avec « le volet GHOST-REVIVE (`TimeFluxReviveAbility` = `GhostReviveAbility` 1186) reste un RESIDU ». `git log -S "GhostRevive"` = **aucun commit**. `FuelledByFury` (1251) : aucune classe, mention en commentaire seule (`dispatch.py:1115`) | `IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` ; ancrage à hooker pour l'émetteur de `On(PendingDeathAdded=3)` : `IdunBattle.MatchState$$AddDeath` ; `IdunBattle.Operations.…$$SetRevivePosition` | ultraTitus, thousTerminator — **HERO pool tous deux** | `engine/runner/operations/triggers/loki/time_flux.py` (+ nouveau `fuelled_by_fury.py`), `triggers/dispatch.py`, `operations/revive.py`, `entities/effects/factory.py` | **2 abilities** (1 par consommateur) |
| **R13** | **`AdaptiveStrategy` (1005, `necroWarden`)** — 1005 en enum seul (`active_ability_type.py:111`), absent d'`ABILITY_CLASSES`. Restent 2 prérequis sur 3 : (1) `RelentlessMarch` 1004 en enum seul (`triggered_ability_type.py:149`), aucune entrée `ABILITY_TRIGGERS`/`TRAIT_TRIGGERS` — sans lui la branche `If(ActorHasTriggeredAbility) TriggerAbility(…)` est un no-op structurel ; (2) les nœuds `TriggerAbility` et `ActorHasTriggeredAbility` **n'existent pas** (0 définition dans `engine/`, inlinés en impératif par `cosmic_horror.py:310` / `sworn_protector.py:266`). Prérequis (3) OVERRIDE-ATTAQUE **CONFIRMÉ LEVÉ** (`stats.py:281`) | `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour` ; `…Loki.RelentlessMarchAbility$$CreateBehaviour` | necroWarden — **HERO pool** | `engine/runner/abilities/behaviours/lifecycle.py` (nœud `TriggerAbility`), `engine/entities/triggers.py`, `triggers/dispatch.py` + module RelentlessMarch, `abilities/necrons.py` + `handler.py` | **1 ability + 1 passif** |
| ~~**R14**~~ | ~~**Face DÉCISION des MoW**~~ — **FERMÉ le 2026-07-27** (`case-r14-mow-decision.md`) | chemin natif dédié = `IdunBattle.AI.Tactics.DefaultMachineTactic` (routé par `IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit` sur `IsMachine`), **pas** `aiPlaybookPredict` | 8 MoW du pool | `engine/ai/tactic.py`, `engine/ai/context.py`, `engine/battle_query.py`, `engine/runner/{components,snapshot}.py`, `engine_validate.py` | — |
| **R15** | **`CalculateCustomUtility` — overlays non portés : le compte réel est 15, pas 16 ni 21.** `REGISTRY` = **7** entrées : 6 posées par `loki_custom.py:283-286` (1014, 1177, 1020, 1029, 1199, **1100**) + `RepairPlaybook` (id 28) posée par `common.py:92` ; plus 1119 `Repair_GalvanicField` porté **hors** `loki_custom`. Sur les 22 overlays par-ability de `case-27`, **7 portés ⇒ 15 non portés**. ⚠ **`case-27-custom-utility.md:139` induit en erreur** : il classe 1100 `SorcerousFacade` « RE RESOLU, **non porté** (routage) », alors que `SorcerousFacadePlaybook` EST défini ET enregistré (`loki_custom.py:243-286`). Ce qui manque n'est pas l'overlay — c'est la **route de ciblage ALLIÉ** (le moteur route 1100 comme attaque d'ENNEMI à cause du `damageProfile`, quand le natif cible un allié Psyker). La ligne doit être re-libellée, sinon elle fait re-porter du code existant | par overlay, cf. `case-27` (formule mirroir par ligne) | mixte ; **4 des 15 sont npc** (1093, 1215, 1216, 1217) et 2 sont des verdicts fermés (1004 terme nul, `ProperKilly` dead-code sans id) ⇒ **9 réellement à débloquer** ; ~~le blocage restant est la face DÉCISION MoW = **R14**~~ **R14 est FERMÉ** (`case-r14-mow-decision.md`) : un caster Machine est routé vers `DefaultMachineTactic` et ses feuilles sont atteintes. Ce qui reste pour un overlay de porteur MoW est le port de la feuille de DÉCISION de son ability — **1187 est la seule des 16 abilities MoW à en avoir une** ; le sweep de `probe_r14_mow_decision.py --sweep` donne, par MoW, l'ability que le natif choisit (= l'ordre de priorité de portage) | `engine/playbook/loki_custom.py`, + correction de `docs/rl/case-27-custom-utility.md` (l.139 et ventilation l.157-160) | **1 sous-système par débloqueur**, puis 1 overlay/ability |
| **R17** | **Ordre intra-groupe de `PerformAIAction(asGroup=1)`** — `summon_ai.py:225` : `uid = valid[0]   # PickNextUnit (utilite natif -> ordre selecteur)`, résidu écrit l.211-214 ; `collect_ai_controlled` l.57 rend `sorted(out)` = ordre d'id. Live observé : les 2 gardes de SupremeCommander agissent dans l'ORDRE INVERSE de leur spawn. Manque la sémantique des 8 ids de `UtilityBucket` (aucun dump d'enum) + le scoreur par-unité derrière le slot 1 | `IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$PickNextUnit` (slot 1 de `operator+0x28`, picker `operator+0x30`) ; `…DefaultGroupOperator$$.ctor` = 8 `IdunBattleLogic.AI.Utilities.UtilityBucket` (ids 0x4a/0x44/0x45/0x4c/0x4b/0x49/0x47/0x48) | astraCreed, orksWarboss — **pool** | `engine/runner/operations/summon_ai.py`, `engine/ai/bucket.py` | **1 sous-système** — sans incidence tant que les unités du groupe sont interchangeables |
| **R19a** | **Mode `AttackRangeType.Both` (3) non modélisé** — `damage_ops.py:37-71` : `hits_channel_is_melee(...)` fait `return is_melee` (l.71) ; la table de vérité native est en commentaire (l.49-53) mais la valeur 3 n'est jamais calculée, l.62-65 le disent (« Le port ne modelise pas `Normal`(3) »). Le port DÉCLARE la nature là où le natif la CALCULE. `services/battle_query.py:26` porte bien `AreUnitsInMelee` mais n'est consommé que par la sélection d'arme (l.85) | `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` = `AreUnitsInMelee(attPos, tgtPos)` pour ce mode | pool | `engine/runner/operations/damage_ops.py`, `engine/services/battle_query.py`, `engine/runner/abilities/behaviours/combat.py` | **1 effet** |
| **R20** | **`SpawnReplica` ré-implémente `PerformAIAttack` à la main** — `behaviours/summon.py:270-277` fait encore `_nearest_enemy` + `AttackDamageOperation.execute`, **sans gate de portée ni dispatch after-hit**, alors que le corps unique est appelé juste au-dessus (`summon.py:162` → `perform_ai_attack_from_current_position`, de-forké par `7f47c29`). Docstring l.241-242 assume encore l'approximation | `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttack` — MÊME `PerformAIAbilityUnitBehaviour` que `…FromCurrentPosition` à un champ près : `+0x78` (budget de déplacement) fourni par l'appelant au lieu de `factory+0xb8 = Direct(0)` | necroSpyder (ScarabSummon 1047) — **HERO pool** | `engine/runner/abilities/behaviours/summon.py` | **1 effet** (rabattre sur le corps unique ; l'amount reste inerte tant qu'aucun étage ne fait bouger un summon avant son attaque) |
| **R24** | **`tests/conftest.py` écrit ses state-files dans `data/`** — `conftest.py:52-53` : `STATE_PREFIX = … ROOT/"data"/"_pytest_duel_state"` ; produits `data/_pytest_duel_state-<pid>-<n>.json`. Vérifié : `git check-ignore` rc=1 (**non ignoré**), et `.gitignore:3` dit explicitement « `data/` A LA RACINE EST VERSIONNE ». Un override existe (`TACTICUS_PYTEST_STATE_PREFIX`) mais le DÉFAUT reste `data/`. Unlinkés au teardown ⇒ invisibles la plupart du temps ; une passe interrompue les laisse dans `git status` | — (outillage) | — | `scripts/python/tests/conftest.py` | **1 ligne** |
| **R25** | **3 constantes de gameplay FIGÉES dans les tests** — (a) `test_damage_crushingclaws_live.py:178` `assert len(off_ph) == main["hits"] == 2` — le fichier n'importe NI `_config_oracle` NI `gameconfig`, le `2` est un littéral ; (b) `test_fragstorm_migration_live.py:167-169` cap `nrOfTargets` en dur (résidu **assumé** en en-tête l.25) ; (c) `test_jakhal_stimms_live.py:288` `exp_loss = round(hp0 * 25 / 100)` (résidu **assumé** l.27). Le module `_config_oracle.py` EXISTE mais **n'expose aucun accesseur générique** `ability(id).constants[<clé>]` — les 3 tests utilisent des helpers `_cfg_hits` locaux | oracle = la CONFIG (`gameconfig.ability(id).constants`) | — | `scripts/python/tests/engine/runner/` (3 fichiers) + `_config_oracle.py` (accesseur générique à ajouter) | **1 effet** (lot de 3 fichiers + 1 accesseur) |
| **R26** | **Rider OVERKILL de `ThrillSeekers`** (face PRÉDICTION) — `services/trait_damage_limits.py:243-245` : `is_overkill(..., allow_flag=0, ...)` en dur ; la signature `compute_prediction_overkill(cur_hp, max_hp, dmg_min, *, suppress=False, p12=0)` (l.230-231) n'a **aucun** paramètre trait/effet, et les 3 appelants ne passent rien. Non-porté explicite : `triggers/loki/thrill_seekers.py:90` | `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` force son `allow_flag` à 1 quand l'attaquant `HasTrait(0x420)` ET `HasEffect(0x59a)` ET (`default_flag` OU le flag de crit) | emper* — **pool** | `engine/services/trait_damage_limits.py`, `engine/runner/operations/damage_hits.py`, `engine/services/damage_prediction.py` | **1 effet** — biais UNILATÉRAL (le port sous-estime l'overkill des porteurs *Thrilled* qui critent, donc `OverkillUnitUtility`) |
| **R27** | **Seuil `should_evaluate` de BlackRage** — `playbook/noncomparable/black_rage.py:77` : `return hp <= hpmax * 0.5`, littéral en dur (commentaire l.76 « ConfigVar 0x26 = 50% … Lucien-only »), aucune lecture indexée par niveau, alors que la RE combat montre un `hpPct` **par niveau** (30 → 50 %) — correct seulement au niveau max | `IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$…` | bloodDeathCompany — **HERO pool** | `engine/playbook/noncomparable/black_rage.py`, `engine/entities/effects/magnitude.py` | **1 effet** — n'affecte pas la garde actuelle (Lucien caste à hp=1) |
| **R28** | **`PickRandomly` — FERMÉ** (2026-07-27, cf. `case-r28-pick-randomly-order.md`). (1) **ordre d'énumération du pool** — RÉEL, **porté et CONFIRMÉ LIVE** sur les deux itérateurs natifs (`IterateAdjacentTiles` = champ brut `boardGraph.neighbours` ; `IterateSurroundingTiles` = triple boucle CUBE) : la victime live suit l'ordre SOURCE, l'ordre id la rate. (2) **Fragstorm tire des HEXES** — RÉEL, porté (`tile_domain=True`, tuiles vides incluses = coup gaspillé) mais **INVALIDABLE LIVE** : le seul porteur de `Fragstorm` (1078) est `templSmnAggressor`, summon spawné par le POWER-UP `PowerUp_SummonSpawn_templSmnAggressor` — aucune unité du pool ne l'invoque, et `templAggressor` (pool) porte une AUTRE ability (`FragstormGrenadeLauncher`, chaîne de coups restants). Mirror-offline gardé par une assertion structurelle sur le pool. (3) **`AddForcedTargetsAndUpdateCandidates`** — **NON PERTINENT** : sa source `GetOnlyTargets(caster)` n'a qu'un écrivain natif (`InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour`, unique XREF de `DSLFactory$$AddForcedAttackTarget`), dont les 23 porteurs (trait `InstinctiveBehaviour` 2021) sont des npc/summons Tyranides SANS active ability ⇒ liste toujours vide, retour immédiat, **0 tirage** | `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` ; `IdunBattle.DSL.APickSelector$$AddForcedTargetsAndUpdateCandidates` ; `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` | BringerOfDespair (`blackTerminator`) + PlasmaCannon (`darkaTerminator`) — **confrontés** ; Fragstorm — **hors pool** | `engine/dsl/base.py`, `engine/entities/pathfinding/board.py`, `engine/entities/selectors/{tiles,units}.py`, `engine/runner/abilities/{behaviours/combat,loki/splash,necrons,darkangels}.py` | **FERMÉ** |
| **R30** | **Substrat MULTI-HEX** (une unité occupant N tuiles) — `components.py:178-185` : `PositionComponent.__slots__ = ("col","row")`, une seule tuile ; **aucune** classe `UnitFootComponent`, aucune liste de pieds dans `state.py`. Corollaire mesuré dans le code : `ai/utilities.py:35` « … (chevauchement small-unit seul). Retour 0.0 jusqu'au cablage du poids + feetCount ». `DutyEternal` 1158 = enum seul, absent d'`ABILITY_CLASSES` | `IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$ExecuteBehaviour` (`RemoveMachine` + `Spawn(ThreeTileUnitSpawnShape)`) | ultraDreadnought (**MoW du pool**) ; probablement aussi `AetherStride` (thousDaemonPrince, catalog_inject) | `engine/runner/components.py`, `state.py`, `snapshot.py`, `utilities/tile.py`, pathfinding/occupance, `engine/ai/utilities.py` | **1 sous-système** — **le plus gros de la liste** |
| **N1** | **Ciblage d'`ArcaneShield` sur un allié NON-Chaos** — `triggers/loki/arcane_shield.py:62` : `prio = 0 if (own_fac == own_fac) else (1 if fac in CHAOS_FACTIONS else 2)` ; le palier `2` retient un allié NON-Chaos alors que le montage de `21494b6` établit l'inverse. `git log 21494b6..HEAD -- arcane_shield.py` = **vide** (le fichier n'a pas bougé depuis que le résidu a été nommé). Le vecteur reste aussi approximé sur `On(4)` au lieu de `On(0x1c)` (l.115-118) | à relire dans `IdunBattleLogic.Entities.Abilities.…ArcaneShieldAbility` | thousSorcerer — **HERO pool** | `engine/runner/operations/triggers/loki/arcane_shield.py` | **1 effet** |
| **N2** | **Famille ATTACK en bounds-mode : cap SCALAIRE là où le natif cape les CELLULES** — `damage_ops.py:796-797` : `execute_ability_attack` passe `_target_limits(..., is_special=2)` **inconditionnellement**, y compris à `is_attack_damage_op=True`. En bounds-mode la branche ATTACK de `_run_hits` (`damage_hits.py:240-249`) applique `roll = _limits_scalar(roll)` = cap SCALAIRE post-tirage ; le cap sur les CELLULES pré-tirage n'existe que sous `limits["is_special"] == 1` (`damage_hits.py:303-316`), atteint uniquement par `execute` et `additional_hits.py:146` | `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` vs `…$$CalculateDamageOperation` (`Math.Max(0, dmg − shieldPart)`) | pool | `engine/runner/operations/damage_ops.py`, `engine/runner/operations/damage_hits.py` | **1 effet** |
| **N5** | **Chaîne `&` derrière un `AddEffect` REFUSÉ : la chaîne se POURSUIT** — `behaviours/effects.py:225-232` : la feuille `AddEffect` émet `placed=(eff is not None)` puis `return OperationResult.ok()` **sans condition**, aucun `stop` ; le combinateur `Seq` (`entities/behaviours.py:30-34`) ne court-circuite que `if r.stop`. Or le gate d'immunité (`operations/effects.py:137-138`) rend `None`, et son propre commentaire (l.133-135) énonce le comportement natif attendu : « pour un vecteur qui chaine (`op_add`/`&`), la suite de la chaine tombe avec (GROUND TRUTH #224 : la branche Chaos entière d'`ExemplarOfHate` est absente sur une cible `TerminatorArmour`) ». **Le port n'implémente pas cette chute** | `IdunBattle.Operations.AddEffectOperation$$Execute` (abandon avant matérialisation) | darkaAsmodai / blackAbaddon — **pool** (le montage #224 existe déjà) | `engine/runner/abilities/behaviours/effects.py`, `engine/runner/operations/effects.py`, `engine/entities/behaviours.py` | **1 effet** |

#### R9-clos — `Chronometron_ExtraDamage` (1550) : d'INERTE à ACTIF, validé live sur les DEUX faces

**Ce qui a été porté** (mirror de `IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`) :

    EffectBonus.ForAddition( OwnerIsTarget & IsUnit(caster@0x160)
                               & AreFriends(caster@0x160, EffectSource(Effect@0x150)),
                             Multiply( If(IsMechanical(caster@0x160), ConfigVar(9 = extraDmg_2),
                                                                      ConfigVar(8 = extraDmg)),
                                       TimesEffectApplied(Effect@0x150) ),
                             AbilityOrEffect(0x4ca = 1226) )

Le KIND est **ForAddition** (additif PLAT) : le corps inline écrit le montant au champ `+0x10` de la
struct `EffectBonus`, le slot qu'écrit `IdunBattle.Entities.Effects.EffectBonus$$ForAddition`
(`param_1[2] = amount`) — distinct de ForPercentIncrease (`+0x08`) / ForSubtraction (`+0x18`).

**`attacker_ctx` est un contexte PARTAGÉ, nommé pour les NŒUDS natifs** (pas pour l'usage qu'en fait
1550) — élargi sur les DEUX faces (`runner/damage_model.py::defender_modifiers` ET
`playbook/prediction/_shared.py`), avec les MÊMES clés :

| clé | nœud natif porté sur `caster@0x160` | source COMBAT | source PRÉDICTION |
|---|---|---|---|
| `is_unit` | `DSLFactory$$IsUnit(caster)` | présence d'un `UnitComponent` | présence dans `scene.vis_by_id` (dv = `EntityType.Unit`-only) |
| `team` | membre GAUCHE d'`AreFriends(caster, …)` | `OwnerComponent.team` | `scene.team(att_id)` |
| `team_by_id` | membre DROIT d'`AreFriends` quand ce n'est PAS l'attaquant (ici `EffectSource(Effect)` = `eff.source`) | walk ECS | `scene.team_by_id` |
| `traits` | `HasTrait(caster, …)`, dont `IsMechanical(caster)` | `StatsComponent.ctx.traits` | traits gameconfig par `visualId` |

⚠ `IsMechanical` porte sur l'**ATTAQUANT**, pas sur la cible (l'énoncé « trait `Mechanical` de la
cible » de la fiche R9 initiale était une imprécision). Et le `3` du 3ᵉ argument de
`DSLFactory$$IsMechanical` n'est **pas** un id de trait : c'est le mode de recherche partagé (le même
`3` que `HasFaction(…, 0x14, 3)`) — la fonction construit
`AmountIsEqualOrGreater(TraitAmount(caster, Mechanical), Value(1))`.

**Compteur d'applications** : `BaseEffect.times_applied` = `EffectComponent+0x6c`.
`IdunBattle.Entities.Components.EffectComponent$$.ctor` l'initialise à **1** (pas 0), et
`IdunBattle.Operations.AddEffectOperation$$UpdateExistingEffect` fait `+0x6c += 1` sur la voie de
RE-pose — voie que le port matérialisait par un simple no-op, qui perdait donc le compteur.
Corollaire documentaire : l'en-tête d'`operations/effects.py` attribuait `Active` à `+0x6c` ; c'est
faux (`Active` = `+0x5c`), corrigé.

**Cycle de vie** : `$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget & IsUnit(caster) &
AreFriends(caster, EffectSource)` → greffe générique de
`BaseEffect$$CreateHandleTriggerAbilities` → `RemoveEffect(<cette instance>)`. C'est une **charge à
usage unique**, consommée au 1ᵉʳ coup d'un allié du Chronomancer (`EFFECT_TRIGGERS[1550]`,
`triggers/loki/chronometron.py`, même mold qu'`InspiredToGreatness_OverrideLevel`).

**MESURE LIVE** (`probe_r9_chronometron.py`, runner isolé MC1_67, positions DRIVÉES, poseur
`necroChronomancer` injecté par `catalog_inject`, level 50 × multiplier 180 %) :

| branche | attaquant | AVANT (effet inerte) | APRÈS (port) | natif | prédiction (`aiPredict` Δ) |
|---|---|---|---|---|---|
| `IsMechanical` VRAI → `extraDmg_2` | `necroDestroyer` | −1197/coup | `[2009, 2203, 2001, 2281, 1934, 2161]` | **identique, 6/6 bit-exact** | Δ = 7182 = 1197 × 6 coups |
| `IsMechanical` FAUX → `extraDmg` | `tauAunShi` | −898/coup | `[2357, 2416, 1989, 1961, 1945]` | **identique, 5/5 bit-exact** | Δ = 4490 = 898 × 5 coups |

`1197 = extraDmg_2[L50]=665 × 1,8` ; `898 = extraDmg[L50]=499 × 1,8`. Le replay-diff **BASELINE**
(avant tout cast) est bit-exact sur les DEUX couples → l'écart post-cast est imputable à
Chronometron seul. 1550 disparaît de la cible après le coup allié, live ET offline.

**Découverte COLLATÉRALE (gap NOUVEAU, orthogonal à R9)** — `FuelledByFury` (passif d'`ultraTitus`,
`ultraTitus` fut le 1ᵉʳ attaquant non-Mechanical essayé) **n'est pas porté** : i2 verbatim « Deals
+{extraDmg} Damage with all attacks **for each time a friendly Character has used an active ability
this battle** ». Le cast de Chronometron incrémente lui-même ce compteur ⇒ +248/coup mesurés
(`FuelledByFury.extraDmg[L50] = 138 × 1,8 = 248,4`), qui s'ajoutent aux 898 de Chronometron. La
BASELINE d'`ultraTitus` était bit-exacte (compteur à 0) : c'est bien un gap de PASSIF, pas de R9.
Second candidat écarté : `darkaCompanion`, dont la BASELINE mismatche déjà (divergence pré-existante
du couple, non diagnostiquée ici).

### 4.c — Résidus d'OUTILLAGE et de HARNAIS (confrontés pour la première fois)

| # | Résidu | Constat au code | Fichiers | Taille |
|---|---|---|---|---|
| **O1** | **Aucune garde AUTOMATISÉE de synchro build ↔ `data/symbols/<HASH>` ↔ binaire chargé dans ghidra-mcp** | La procédure est **purement humaine** (`tacticus-orchestration/SKILL.md:303-319`, `CLAUDE.md:41-51` : 3 étapes manuelles). `ghidra_symbols.py:137-140` (`cmd_build`) ne fait qu'**imprimer** `loaded_build(g)`, aucune comparaison. Rien côté `frida/host` (`admin.ts:54-68` résout le PID sans confronter le hash). Le seul hook de session (`scripts/hooks/session-start.ps1`) ne vérifie aucun hash. ⚠ **Ce qui EST automatisé, mais sur un AUTRE axe** : `il2cpp_provenance.py::assert_matches` (l.109-122, message « DESYNCHRONISATION ») est **fail-closed** et consommé par `preprocess_il2cpp_dump.py:31,48-54` et `GhidraApplyIl2CppSymbols.java:94-136` — mais il cible `data/il2cpp_*.tsv`, **pas** `data/symbols/<HASH>/`, et rien ne l'appelle automatiquement | `scripts/python/ghidra_symbols.py`, `scripts/python/il2cpp_provenance.py`, `scripts/hooks/session-start.ps1` | **1 effet** — étendre `assert_matches` à `data/symbols/<HASH>` et l'accrocher au `SessionStart` |
| **O2** | **Pas de drain à la demande des ai-traces** | `frida/hooks/features/ai-trace/state.ts:127-132` : `emit()` fait un `send({t:"ai_trace", …})` immédiat, **aucun buffer** côté agent. `frida/host/ai-trace-store.ts:62-84` écrit ligne à ligne dans `frida/data/ai-traces/<sessionId>-<iso>.jsonl` (docstring l.18 : « no in-memory aggregation, just write-through »). Routes existantes (`router.ts:788-834`) : `status` / `enable` / `disable` — **aucune route `drain`/`flush`/`consume`/`clear`**, aucun RPC de drain côté hooks. Les 8 consommateurs Python lisent le RÉPERTOIRE. **Finding annexe : `aiTraceStoreStatus` (l.100-114) n'est référencé par AUCUNE route ni aucun module — code mort** | `frida/host/ai-trace-store.ts`, `frida/host/router.ts`, `frida/hooks/features/ai-trace*` | **1 sous-système côté hooks** — ⚠ **exige rebuild + reinject**, donc à programmer quand l'atelier est vide |
| **O3** | **RÉSOLU — `case-o3-tile-effect-dynamics.md`.** L'énoncé d'origine était en partie faux : les timers de tuile ÉTAIENT décrémentés (`EndTurnOperation.execute` balaye TOUTES les clés de `by_unit`, tuiles comprises) et le gate `AreEqual(coverPatch, target)` de `LightCoverEffect` EST porté (A3, `d9d0e6c`). Le vrai trou, MESURÉ : (a) le décrément n'était pas clampé (`RemoveOneTurn` = `if (0 < Duration) Duration--`) et surtout (b) **rien ne RETIRAIT l'instance à 0** — `expired` n'est lu que par `active_effects`, alors que `has_effect` et `collect_effect_triggers` ne filtrent que `consumed` ⇒ un feu de tuile brûlait pour toujours (`(remaining, has_effect)` = `(-4, True)` au 6ᵉ tour). Natif : `EndTurnOperation$$RefreshEffects` itère TOUTES les entités-EFFET (aucune distinction unité/tuile), puis `RefreshEffectsOperation$$RefreshEffect` prend la branche retrait sur `EffectComponent$$ShouldBeRemoved` (`HasTurns && Duration == 0`). **+ transition d'ENTRÉE portée** : `LightCoverAbility` (`On(0x24=UnitPositionChanged_1)`, gate de traits `BigTarget/Vehicle/Mounted` lu au `.cctor`), câblée dans `after_move_triggers` ET `displace_triggers` | `engine/entities/effects_state.py`, `engine/runner/operations/triggers/tiles.py`, `engine/runner/operations/triggers/dispatch.py` | **fait** — reste hors périmètre : spawn/revive sur cover, autres tile-abilities d'entrée, `DespoiledGround` (#85, cf. case §6) |
| **O4** | **Résidus de PLACEMENT laissés par `case-130` SS5** — (a) **RÉSOLU, `case-o4a-maybe-trigger-rng.md`** : le nœud `MaybeTrigger` existait déjà (posé par `case-1203`) mais n'était CÂBLÉ qu'à un seul site ; PileIn restait DÉTERMINISTE (0 tirage) et `LetTheGalaxyBurn` roulait dans le mauvais ORDRE avec la mauvaise primitive. Câblé + branche `!CanUseRandom` (`99 < chance`) portée. Ancrage LIVE bit-exact sur PileIn : **4 datapoints, port 4/4 sur le compte de `genrand_int32` ET le nombre de spawns, port d'avant 0/4** (succès du gate : live 5 / port 5 / avant 4 ; échec : live 1 spawn 0 / port 1 spawn 0 / avant 4 spawn **1** = un grot fantôme) ; (b) **`Swamp -> Thorns_DefenseReduction` (−25) porté en LOCAL** : `spawn.py:277 _PLACEMENT_TERRAIN_EFFECTS` au lieu de `utilities/tile.py:93 TERRAIN_TILE_EFFECTS`, la table partagée alimentant aussi le contexte de DÉGÂT et le scoring de MOUVEMENT ; (c) feuilles `Tile(7)` gatées sur l'unité dans le tri de placement (ctor replié par le linker, aucun scénario mesuré ne les réveille) ; (d) on-appearance `PerformAIAttackFromCurrentPosition` du grot SquigHound : écart **CONSTANT de 4 `genrand_int32`** mesuré sur ce vecteur (MC1_67/777 et C2_37/31337), étranger au placement | `engine/runner/operations/triggers/dispatch.py`, `engine/runner/operations/spawn.py`, `engine/utilities/tile.py`, `engine/runner/damage_model.py` | **1 effet chacun** ; (a) est le plus large (touche tout gate `Maybe`/`chance` du DSL) |
| **O5** | **Résidus RNG du canal de coups d'ability (`case-61`)** — (b) `On(PreAttack=5)` absent du vecteur ability (**fidèle** : le natif l'émet depuis `ALoki_NormalAttackAbility$$ExecuteNormalAttack`) ⇒ sur ce vecteur `LetTheGalaxyBurn` ne s'arme que par `TargetHasTileEffect` ; (c) per-coup non bit-exact contre `templChampion` (même nb de coups, dégât différent — effets `MartialSuperiority`/`RapidAssault_ExtraDamage` de la cible ; le témoin `necroWarden` est bit-exact) ; (d) flag `Moved` absent de la face PRÉDICTION (×1,25 uniforme `HeavyWeapon_ExtraDmg` sur tout caster ranged déjà déplacé — débloqueur = exposer `UnitFlagsComponent`, **rebuild requis**). Plus, **distinct et chiffré** : conso RNG du canal #179 non bit-exacte — sur un cast de `FrenziedFiring`, les coups d'ARME sont bit-exacts (K=0, 2 seeds) mais les 2 coups additionnels diffèrent en valeur (port `[2735, 2553]` vs natif `[2481, 2754]`), désalignant tout ce qui suit la première attaque d'un volet AoE | face prédiction, `engine/runner/operations/additional_hits.py` | **1 effet chacun** — à promouvoir sur miss d'agreement |
| **O6** | **`LetTheGalaxyBurn` — ORDRE de consommation RNG : RÉSOLU (`case-o4a-maybe-trigger-rng.md`)** | Le seuil était déjà **validé** (`probe_84_ltgb_chance.py`, 8 runners, branche A n=73 → **34,2 %**, branche B **23/23**). L'ORDRE l'est désormais aussi : `IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger` évalue gauche puis droite, donc `Maybe` passe **AVANT** `!HasTileStatusEffect` — le port consomme maintenant son tirage **sur les deux branches** (mesuré : 1 tirage tuile nue ET tuile à effet ; le port d'avant en consommait **0** sur la branche bloquée). La **primitive** a été corrigée dans la foulée : `NextBool(chance)` = `next_internal(1,100) <= chance` (borne **99**) et non `next_internal(0,100) < chance` (borne 100) — les deux verdicts divergent sur **90 graines / 199** à `chance=33` (`r % 99` et `r % 100` sont décorrélés), ce n'était donc pas un écart seulement statistique. **Reste non confronté bit-exact LIVE** : le porteur ne l'est pas lui-même (cf. `test_bringer_of_despair_live.py`) | `engine/runner/operations/triggers/loki/let_the_galaxy_burn.py` | **fait** |

### 4.d — Reste en VEILLE (à promouvoir seulement sur miss d'agreement)

Vérifiés présents, sans symptôme actionnable aujourd'hui : résidus MV71 (`case-61bis` §6/§8/§9),
per-player 1180 (`case-31`), `ReachedSummonCap` (`case-38` §4 — branche `IsActive` sans caller
connu), `LordOfTempests` AddIce (`case-35` §4), `LivingMetal` swarm no-wake top-off (`case-203` §5),
les 2 résidus `move` (#17, nature RNG), arc arrière NON dégénéré du push (`case-push-distance` §5 —
sans objet pour un pousseur adjacent), trait `Unstoppable` 1042 (à câbler DANS la tranche
movement-stop #131/B4, sinon registered-but-dead), `#202` face DÉCISION Abraxas non confrontée
oracle, `#5` chantier `DslContext` live-state, chantier archi **DSL-effet** (`dsl-effect-nodes.md` —
migration des `execute_*` impératifs vers des arbres de nœuds ; c'est un chantier, pas un résidu).

### 4.e — HORS PÉRIMÈTRE de cet inventaire

- **En cours de traitement par d'autres agents au moment de la rédaction** (délibérément NON
  inventoriés, pour ne pas fabriquer de doublon de dispatch) : le jet de block `Daemon_ExtraBlock`,
  le canal `OnToxicDamage` (1203), le gate de PORTÉE / `TargetIsInRange`.
  **Le gate de PORTÉE est FERMÉ** (#241, `case-241-range-gate.md`) : `TargetingQuery$$GetRange` est
  porté, les 28 masques du registre portent leur `TargetingRange`, et le cliquet du registre exige
  désormais les deux. Ce qui reste à cet endroit de la cascade : la **ligne de vue**
  (`GetTilesObscuringTerrain`), et `GetValidTargets` (dont dépend `GetCasterNotAddedReason`).
- **Bloqués par une fenêtre d'atelier vide** (exigent rebuild + reinject, donc pas du RE) :
  `StatModificationComponent`, `ChildComponent.ParentId`, `EffectComponent.IsActive`,
  `UnitFlagsComponent` dans `combatSnapshot`, stats résolues des MoW (`EntityType.Machine` dans
  `combatSnapshot.allUnits` et `statModSources.targetUnits`), **plus O2** (drain ai-trace).
- **`[fable]` restants** : arbitrage Comparable `ExcruciatingFrequencies` vs attaque normale ;
  étage d'ARRONDI quand la %-list est vide sur les vecteurs restants (= R6, tag mixte) ; **N4**
  (ci-dessous).

### 4.f — NON CONFRONTABLES

| Item | Ventilation des porteurs | Verdict |
|---|---|---|
| **29 actives NO-OP** (§1) | 21 **npc-only** + 8 **summon-env** (posés par `EnvFactionSummons:<Faction>` / `ATemptingTrap`, qu'aucune unité jouable ne porte) | **NON CONFRONTABLE** — ne pas y envoyer d'agent |
| **1192 NovaBoost / 1194 NovaShield** (§2) | `tauBossRiptide` = **npc** | **NON CONFRONTABLE** |
| **4 overlays de R15** (1093, 1215, 1216, 1217) | tous **npc** | **NON CONFRONTABLE** |
| **`Impervious` (28) / cap boss `0x5d4`** | tous les porteurs sont des **boss npc** | **NON CONFRONTABLE** |
| **N4 — stade natif du refus `TerminatorArmour` / `Pinned`** | blackAbaddon / deathTyphus / blackObliterator = **pool** (donc le COMPORTEMENT est confrontable) — mais le **chemin natif** ne l'est pas : `PinnedEffect` n'override PAS `EntityIsImmuneToEffect`, la base ne teste que le trait `Immune` qu'aucune unité ne porte, et le seul artefact nommant le couple est `IdunBattle.Entities.Effects.Loki.PinnedEffect$$CreateActiveCondition = Not(HasTrait(0x40f))` — or une ActiveCondition désactive, elle n'empêche pas la pose | **CANDIDAT `fable-solver`** — collapse assumé par #224, live-correct sur 4 porteurs, le décompilé ne rend pas le stade. **Ne PAS dispatcher en `[opus]`.** Point d'ancrage pour trancher : hook sur la valeur de retour du slot 40 d'`IEffect` dans `AddEffectOperation$$Execute`, ou sur `BaseUnitComponent$$HasTrait` (arg + résultat) |

---

## 5. PÉRIMÉS — à sortir du backlog / de la roadmap

### 5.1 — Fermés depuis l'inventaire précédent (`fc23f1e` → `e972c99`, 26 commits)

| Résidu | Verdict | Commit qui l'a fermé | Preuve au code |
|---|---|---|---|
| **R14** — face DÉCISION des MoW | **FERMÉ** | `case-r14-mow-decision.md` (2026-07-27) | Le chemin natif dédié est `IdunBattle.AI.Tactics.DefaultMachineTactic` (générateurs d'ability SANS `MovementActionGenerator` ; caster à `UnitPosition$$NullPosition` ; tuiles candidates VIDES → branche `Count == 0` d'`ActiveAbilityActionGenerator.<GenerateActions>d__7`), routé par `AiQuery$$GetUnitTacticForUnit` sur `EntityExtensions$$IsMachine`. Reachability prouvée : `DefaultGroupOperator$$CalculateNextActionForPlayer` ajoute `PlayerComponent+0x78` aux entités du joueur. Porté : `engine.ai.tactic.DefaultMachineTactic`, `engine.ai.context.{machine_row,build_machine}`, routage dans `engine_decide`, + le gate `ActiveAbility$$get_CanCurrentlyBeUsed` (cooldown **et** munitions). `_dv_units`/`_obs_units` gardent leur exclusion — elle était FIDÈLE, pas le bug. Sweep 8/8 MoW, 0 violation ; coïncidence mesurée sur 1187 (`test_thrice_blessed_decision_live.py`, 4 verts) |
| **R16** — stat-mods EAGER présents AU SEED appliqués mais non revertables | **FERMÉ** | *fix(rl): R16 — les stat-mods EAGER du SEED sont attribués par-source, donc revertés* | **Un seul fait natif, deux formes** : `AStatModifierEffect$$ApplyModification` lit `GetStatModification()` (vtable +0x728, ValueTuple assemblé par `AStatModifierEffect$$GetStatModification` depuis les slots `GetStatModificationStat` +0x748 / `GetStatModificationAmount` +0x758) et émet UN `ChangeStat` ; une classe peut OVERRIDER `ApplyModification` et en émettre N (`Loki.ActOfFaithBuffEffect$$ApplyModification` = crit-chance + crit-damage). `AStatModifierEffect$$RevertModification` et `Loki.ActOfFaithBuffEffect$$RevertInternal` rejouent les MÊMES appels en `Position(stat, part 6)` avec LA MÊME `Entity(<effectEntity>)` ⇒ le revert est **inconditionnel**, la source EST l'entité-effet, il n'existe pas de famille « modifie mais ne reverte pas ». Le port avait deux chemins pour ce fait : le canal mono-stat (attribué au seed, revertable) et le canal multi-stat `applied_stat_mods` (magnitude lue sur le ctx du porteur — donc NON calculable au moment où `from_snapshot` attribuait, et invisible du discriminant `effect_stat_mod_key`). Les deux bouts sont fermés : (a) `effects/__init__.py::effect_stat_modifications` = point de vérité UNIQUE des deux formes (l'override PRIME, comme côté natif ⇒ pas de double-compte pour `AnvilShield_FrozenAttackerAdvantage` qui déclare les deux) ; (b) `effect_stat_mod_key` discrimine sur `reverted_stats()` (le prédicat déjà symétrique du natif) ; (c) `unit_context.from_snapshot` seede en DEUX passes — les parts `Initial`/`Current` ne dépendent pas de l'attribution, donc la 2ᵉ passe ré-attribue en rejouant le MÊME `seed_unit_stats` avec le ctx en main. **Mesure avant/après** : `probe_r16_eager_statmod_revert.py` (offline, mono ET multi-stat) ; **garde live** : `tests/engine/runner/test_seeded_eager_statmod_revert_live.py` — `admecMarshall`, FixedArmor natif 2494 → 1608 (−886) au retrait de `ProtectorImperative`, offline 2494 → **2494** avant le fix, 2494 → **1608** après |
| **R23** — `audit_kit_coverage.py` sous-compte la face DÉCISION | **PÉRIMÉ** | `8e8518e` *fix(audit): audit_kit_coverage lit le 3e registre de DECISION* | `audit_kit_coverage.py:116-117` : `"decision": (aid in PLAYBOOKS or aid in CUSTOM_PLAYBOOKS or nm in _SPECIAL_ABILITY_CLASSES)`. Le commit tranche aussi, **contre** l'inventaire précédent, que `_NONCOMPARABLE_ABILITIES` n'est PAS un 4ᵉ registre |
| **R19b** — famille ABILITY : modifiers attaquant non vidés | **PÉRIMÉ** | `86fecad` (#226 Foehammer / HammerOfWrath) | `damage_ops.py:582-583` : `if not is_attack_damage_op: mods = DamageModifiers()` — la struct ATTAQUANT est désormais ZÉROÉE, pas seulement « gates inertes ». Discriminant nommé et mesuré bit-exact : `RapidAssault` (effet 1229, `ForPercentIncrease` SANS gate). ⚠ nuance : `execute_normal_like` ne zéroe PAS (`damage_ops.py:948`) — sans conséquence aujourd'hui, aucun call-site `amount=` + `native_factory="ability"` n'existe |
| **R21** — `UnitFlag.ArrivedAtFinalTile` non posé | **PÉRIMÉ** | `5c45389` (passifs Genestealers) | Le flag EST posé sur le chemin de move : `triggers/dispatch.py:984` (`fl.add(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)`) dans `arrived_at_final_tile_triggers`, appelée en queue d'`after_move_triggers` (l.890), elle-même appelée par `MovementHandler.visit_MoveUnitMessage` (`movement.py:126`). ⚠ l'affirmation « le flag n'est posé que par `FinishUnitTurnOperation` » est **fausse aujourd'hui** — le site de pose a été déplacé dans le dispatcher after-move (choix documenté `dispatch.py:963-968`) |
| **N3** — ordre réduction × bouclier sur `execute_normal_like` | **PÉRIMÉ côté CÂBLAGE** (mesure toujours absente) | `21494b6` (#67b), qui a introduit le paramètre en même temps qu'il nommait le résidu | Thread complet : `damage_ops.py:907` → `_run_hits` (l.1006) → consommé `damage_hits.py:323-330`. Les feuilles le renseignent depuis `native_factory` (`combat.py:163`). **Code câblé = OUI, comportement mesuré = NON** (à `spread_pct=0` et `shield=0` les deux ordres sont indiscernables) |

### 5.2 — Entrées du BACKLOG qui étaient DÉJÀ fausses avant l'inventaire précédent

Ces deux-là sont les plus coûteuses de la liste : elles portent le tag **`[fable]`** au backlog, donc
elles auraient consommé l'agent le plus cher sur un problème déjà résolu.

| Entrée backlog | Verdict | Commit / preuve |
|---|---|---|
| **« Crit-roll NON tiré à cc=0 sur la voie ABILITY multi-hit → desync spread »** (`[fable]`, présenté comme « ROOT CAUSE MESURÉE ») | **PÉRIMÉ — et le diagnostic était FAUX** | `844298e` *fix(rl): cas fable rngcrit-1202 — le « crit-roll fantôme » #220/#205 = resolve slot-8 gaspillé, PAS un crit* (ancêtre de HEAD, vérifié). `damage_hits.py:207-224` porte le verdict RE : « Il n'existe AUCUN chemin consommant un tirage crit à cc=0 — ni par vecteur, ni par éligibilité » ; l'extra tirage est le `GetDamage` brut + le resolve dégénéré. Mesure : `probe_rngcrit_1202`, M3 bit-exact per-hit, 5 seeds × 2 cibles. **Les modèles « crit-roll par coup à cc=0 » sont RÉFUTÉS par la mesure** |
| **« Coups post-mortem / dérive du flux MT »** (`[fable]`) | **PÉRIMÉ — réfuté par lecture du natif** | `case-125-rng-wasted-hits.md:41-43` : `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` est un `while (i < hits)` **plat** — le compteur est incrémenté dans TOUTES les branches, « il n'y a ni `break` ni test de mort de la cible ». Le natif **ET** le port roulent tous leurs coups. La vraie cause du symptôme (#116-d) était le report `GetLeftOverHits`, corrigé et gardé (`test_chain_leftover_hits_live.py`) |
| **« Follow-up fidélité #147 : le reset ActOfFaith mappé sur `On(8)` fire aussi au crit d'attaque NORMALE »** | **PÉRIMÉ** | `94ae6d0` *fix(rl): #151 reset ActOfFaith = On(9)=Attack (ability-only), plus l'after-hit On(8) partagé*, complété par `a50496c` (fix ActOfFaith crit normal). État courant : `dispatch.py:781` « aucun consommateur actif depuis #151 — le reset ActOfFaith a migré sur On(9) ability-only » |
| **« Le VERDICT du `Maybe` de `LetTheGalaxyBurn` diverge natif/port »** (écart de **seuil**) | **REFORMULÉ — l'écart de seuil est RÉFUTÉ** | `probe_84_ltgb_chance.py` (8 runners) : branche A n=73 → **34,2 %** contre 33 % config ; branche B **23/23**. Le résidu subsistant est un **ordre de consommation RNG** dans la conjonction — cf. **O6**, et il ne se dispatche pas de la même façon |

### 5.3 — Entrées déjà sorties par l'inventaire précédent (rappel, ne pas re-dispatcher)

`R2` gate d'immunité (`42de74d`, #224) · `R3` overwatch un-tir (`7c412b8`, #127) · `R10` retrait
`InspiredToGreatness_OverrideLevel` 1180 + `R11` phase-2 `EarlyWarningOverride` (`b6d174c`, #114) ·
`R18` bouclier × limites voie ability (`21494b6`, #67b) · `R22` DoT de tuile `EnvFireTile`
(`ad5692e`) · `R28`/placement (`fc23f1e`, case-130 SS5) · `#PAI-c` consommateurs `PerformAIAction`
(`3f7b9d1`) · FireOfAbsolution volet feu-sur-cible (`ac1144f` + `8b34e7f`) · harnais cast-MoW
hors-plateau (`a9714a4`) · 1169/1148/1142 « BLOQUÉ harnais » (`a9714a4` + `bf61e8b`/`34872ac`/`f4591dd`) ·
« porteur hors pool ⇒ inconfrontable » (`ab98129`) · prérequis OVERRIDE-ATTAQUE de #116-r
(`71dca97` + `d67b6ac`) · `getstuckin_combat_chance` (`886335f`) · prérequis « canal PIERCING
attaquant » de `case-220` §6.17 (`8341bd1` / `169b4b2`).

### 5.4 — CHIFFRES périmés à corriger dans les docs sources

| Document | Ce qu'il dit | Ce qui est vrai au commit courant |
|---|---|---|
| `backlog.md` #217 | « 20 au 2026-07-26, dont 18 à porteur confrontable » | **15 lineup + 2 npc** (§2) |
| `backlog.md` #115 (a) | « les 60 autres abilities du registre » | **53 sur 81** (§3) |
| `backlog.md` #27 / `case-27` | « 16 résidus » | **15**, et `case-27:139` se contredit sur 1100 SorcerousFacade (cf. R15) |
| `backlog.md` #20 / `port-roadmap.md` | « 119 kits, 249 items, 16 abilities portées combat » | **95 kits / 126 items / 80 portées** |
| Ce fichier, version du 2026-07-26 | « 96 NO-OP / 67 dispatchables », « 75 sans masque », « 63 passifs confrontables » | **91 / 62**, **53**, **55** |

**Cadence mesurée sur 24 h** : **4 résidus fermés** (R19b, R21, R23, N3-câblage) + **2 entrées
`[fable]` révélées déjà fausses** + **5 abilities** sorties du gisement 1 + **22 masques de ciblage**
+ **8 passifs**. Un backlog relu à J+1 ment déjà sur ses chiffres ; à J+3 il ment sur ses verdicts.

---

## 6. Ordre de dispatch conseillé (valeur décroissante)

1. **R5 et N6 — deux tests de garde ROUGES, tous deux RE-REPRODUITS ce jour.** N6 est passé devant :
   il porte désormais un **symptôme de magnitude chiffré** (live 2700 vs port [1688, 2532]) et non
   plus un simple « test rouge ». Un test rouge toléré est un oracle perdu.
2. **R1 tuile d'origine** — symptôme mesuré, cause localisée à UNE ligne (`state_bridge.py:318`),
   impact transverse. Exige une passe d'agreement complète, pas un smoke : le prévoir dans la tâche.
3. **Gisement 2 (§2), 15 items** — un agent par ability. Prioriser 1137 MurderousSwing, dont la face
   décision est déjà mesurée : l'oracle existe.
4. **R4 resolve slot-8**, ~~R9 Chronometron~~ (**CLOS**, cf. §R9-clos), **N1**, **N2**, **N5** —
   symptômes mesurés ou cause nommée, taille contenue. ⚠ **ne pas dispatcher R4 et N2 en même temps**
   (`damage_hits.py`).
5. **Gisement 4 (§3bis), 55 passifs confrontables** — le plus gros volume, invisible des deux audits
   historiques. À traiter en parallèle du gisement 1 : il ne touche PAS `handler.py`.
6. **Gisement 3 (§3), 53 masques** — par module, en suivant la carte du §3 ; ou en règle de
   non-régression sur chaque nouveau port. Les gros lots restants : `splash` (6), `strike` (6),
   `blacklegion` (5), `deathguard` (5), `summon` (5), `tau` (5).
7. **Gisement 1 (§1), 47 items restants** (62 − les 15 du gisement 2) — piocher par faction ; les 11
   de la voie `catalog_inject` n'ont plus d'obstacle de harnais.
8. **O1 garde de synchro**, **R24**, **R25**, **R8** — dette d'outillage / de tests, très peu
   coûteuse, et O1 protège toute la chaîne RE.
9. ~~**R14 face décision MoW**~~ **FERMÉ** (`case-r14-mow-decision.md`) — le débloqueur nommé par R15
   est levé ; ce qui reste pour les overlays MoW est le PORT de leur feuille de décision (1187 est la
   seule des 16 abilities MoW à en avoir une). Reste **R30 multi-hex** — sous-système, à isoler.
   (~~O3 dynamique des effets de tuile~~ : **fait**, `case-o3-tile-effect-dynamics.md`.)
10. ~~**O4 (a) `MaybeTrigger`**~~ **FAIT** (`case-o4a-maybe-trigger-rng.md`) — le comptage RNG d'un gate
    `Maybe`/`chance` est désormais confrontable, et O6 est fermé avec. Ce que la mesure a **découvert**
    et laissé ouvert (deux gaps distincts, cf. la case §6) : `load_state` ne seede pas
    `state.turn_counts` (tout état chargé d'un snapshot a `{}` ⇒ PileIn **et** Ambush morts), et
    `OwnerHasFinishedMinTurns` est **PER-UNITÉ** côté natif
    (`IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger` →
    `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(unit)`, champ `+0x5c`), là où le port lit
    un compteur de JOUEUR.

**Ne PAS dispatcher `N4`** en `[opus]` : collapse assumé que le décompilé ne tranche pas — candidat
`fable-solver`, et sans urgence (comportement live-correct sur 4 porteurs).
**Ne PAS dispatcher O2** tant que l'atelier n'est pas vide (rebuild + reinject).

---

## 7. Collisions entre agents concurrents

| Fichier | Qui le touche | Risque |
|---|---|---|
| `engine/runner/abilities/handler.py` | **tout** port d'ability (gisements 1 et 2) | **ÉLEVÉ** — conflit textuel garanti si 2 agents portent en parallèle. Trivial (2 lignes), mais à résoudre par l'auteur au rebase |
| `engine/runner/operations/damage_ops.py` | R4, R6, R7, R9, R19a, N2 | **ÉLEVÉ** — 6 résidus s'y croisent. Ne pas en dispatcher deux ensemble |
| `engine/runner/operations/damage_hits.py` | R4, N2, R26 | **ÉLEVÉ** — sérialiser |
| `engine/ai/state_bridge.py` | R1, R15 | MOYEN — R1 touche `_plans_for_unit`. (R14 est FERMÉ et n'a PAS touché cette fonction : le chemin MoW vit dans `engine/ai/{tactic,context}.py`.) |
| `engine/runner/abilities/behaviours/combat.py` | R19a | MOYEN (R28 fermé) |
| `engine/runner/operations/triggers/dispatch.py` | R12, R13, O4(a), tout vecteur d'event neuf | MOYEN |
| `engine/runner/operations/effects.py`, `engine/entities/effects/factory.py` | N5, R9 (R16 **fermé**) | MOYEN |
| `engine/runner/abilities/<module>.py` | gisement 3 (1 lot par module), 1 port par faction | FAIBLE — deux modules différents ne se croisent pas |
| `engine/entities/effect_type.py` | tout effet neuf | FAIBLE (ajouts en fin de liste) |
| `docs/rl/combat-ability-coverage.md`, `kit-coverage.md`, `passive-ability-coverage.md` | régénérés par les audits | **ne jamais fusionner un conflit** : régénérer (`audit_*.py`) |
