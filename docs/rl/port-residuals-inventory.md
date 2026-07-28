# Inventaire des résidus de portage — confronté au CODE (2026-07-27, passe 3)

> **Pourquoi ce fichier.** `backlog.md` décrit des INTENTIONS horodatées, `port-roadmap.md` un
> découpage figé : ni l'un ni l'autre ne décrit l'état du code. Ce document est le résultat d'une
> **confrontation item par item au commit courant**. Chaque ligne porte un verdict
> **OUVERT / PÉRIMÉ / NON CONFRONTABLE**, et seul OUVERT produit une tâche dispatchable.
>
> **Base de la mesure** : commit `bec119f` (`origin/master`), build `gqfc5mff6c`, session Frida 4
> `running` (démarrée le 2026-07-27 à 17:21 UTC), pool `rl_duel build --list-pool` rank 17 =
> **97 unités + 8 MoW**.
>
> **MÉTHODE DE CETTE PASSE — re-confrontation SCOPÉE PAR LE DIFF, pas relecture intégrale.**
> Base de la passe précédente : `2cef371`. Depuis : **43 commits / 17 merges**. La règle appliquée :
> `git diff --name-only 2cef371..HEAD` donne l'ensemble des fichiers qui ONT PU bouger ; **seules les
> entrées ouvertes dont la colonne « Fichiers » intersecte ce diff ont été relues**. Les autres sont
> inchangées PAR CONSTRUCTION et sont marquées **« hors intersection »** — c'est un verdict, pas un
> oubli. Cette passe est faite pour être **courte et répétable** ; les colonnes « Fichiers » sont ce
> qui la rend possible, et c'est la raison de les tenir à jour.
>
> ⚠ **DÉFAUT DE L'INVENTAIRE, signalé ici parce qu'il coûte à la prochaine passe** : le §4.d
> (« reste en VEILLE », 13 items) **n'a AUCUNE colonne Fichiers**. Il est donc hors de portée du
> scoping par diff, et personne ne peut dire s'il a péri sans le relire en entier. Lui donner un
> ancrage fichier est la dette la moins chère de ce document.
>
> **Ce que cette passe change** : **5 résidus supplémentaires sont FERMÉS** (`R8`, `R24`, `O1` par
> le seul commit `3eee6c0` ; puis `R5` et `R20`, mergés PENDANT la passe), **1 est à REFORMULER**
> (`R30` : le substrat multi-hex EST porté), **3 entrées NEUVES** sont ouvertes avec un symptôme
> mesuré (`N7`, `N8`, `O7`), et le §4.e « bloqués par une fenêtre d'atelier vide » passe de
> **5 items à 1** — quatre d'entre eux étaient déjà livrés le 2026-07-26 (`d9d0008`), donc
> **déjà faux à la passe précédente**.
> Les **10 fermetures** annoncées par la passe précédente (R1, R9, R14, R16, R28, N5, O3, O4a, O6,
> convergence `RULE_*`) ont toutes été **re-vérifiées au code** : aucune n'est fausse (§5.1).
>
> **Ce document n'est PAS auto-généré — mais tous ses comptes le sont.** Pour les re-dériver :
> `python audit_combat_ability_coverage.py`, `python audit_kit_coverage.py` et
> `python audit_passive_ability_coverage.py` depuis `scripts/python/` (le 3ᵉ interroge le pool
> live ; les deux autres sont offline). **Les trois ont été re-joués à `bec119f` : les deux audits
> offline rendent un fichier IDENTIQUE au caractère près** (aucun diff), et l'audit de passifs ne
> bouge que de 2 lignes `GAP-ABSENT` → `GAP-MENTION` sur deux passifs npc-only (`RunsAround`,
> `RunsAway`) plus ses compteurs internes de volume de code. **Aucun compte de gisement n'a bougé
> en 43 commits** — c'est le fait le plus utile de cette passe, et il ne se voit qu'en re-jouant.

---

## 0. Recalage des chiffres — TOUT avait bougé en 24 h, RIEN n'a bougé depuis

> **Re-dérivé à `bec119f` (43 commits plus tard) : la colonne de droite est INCHANGÉE, valeur par
> valeur.** Les deux audits offline rendent un fichier identique au caractère près ; l'audit de
> passifs ne bouge que sur 2 passifs npc-only. Les 43 commits ont fermé des résidus NOMMÉS et livré
> un sous-système (R30), mais **aucun n'a porté d'ability ni de passif** — d'où l'immobilité des
> quatre gisements. Ce n'est donc pas une table à re-mesurer à chaque passe : c'est une table à
> re-JOUER (30 s), et son immobilité est elle-même l'information.

| Chiffre | Inventaire du 2026-07-26 (`fc23f1e`) | RE-DÉRIVÉ au 2026-07-27 (`e972c99`, re-confirmé `bec119f`) | RE-DÉRIVÉ au 2026-07-28 (case-231, `0627635`+2) | Sens |
|---|---|---|---|---|
| actives castables | 171 | **171** | 171 | inchangé |
| `ABILITY_CLASSES` (entrées du registre) | 76 | **83** | **89** | +6 |
| actives portées COMBAT | 75 | **82** | *non re-dérivé* | — |
| actives **NO-OP combat** | 96 | **89** | *non re-dérivé* | — |
| … dont **dispatchables** | 67 | **60** | *non re-dérivé* | — |

> ⚠ Seule la ligne `ABILITY_CLASSES` a été re-dérivée le 2026-07-28 (`len(ABILITY_CLASSES)`, une
> ligne). Les trois suivantes viennent des audits (`audit_combat_ability_coverage.py`) et **n'ont
> pas été re-jouées par ce commit** — les laisser à leur valeur du 27 serait affirmer une
> immobilité non mesurée, d'où le *non re-dérivé*. Écart notable : **83 → 89 en une journée**, dont
> **2** viennent de case-231 et **4** d'autres lots mergés entre-temps.

> **case-231 (2026-07-28)** : +2 entrées = `1154 TacticalPrecision` (`ultraTitus`) et
> `1184 MomentShackle` (`custoTrajann`), toutes deux **avec** `TARGETING_OPTIONS` **et**
> `ABILITY_ATTACK_TYPE`. Ce qu'elles apportent au-delà de deux abilities, ce sont **deux primitives
> partagées** : le prédicat `IsCharging` (`BattleQuery$$IsCharging` = adjacence **ET**
> `UnitComponent.ChargedUnitIds@+0x190`, alimenté par `MoveUnitOperation$$UpdateCharging`, vidé par
> `FinishUnitTurnOperation$$Execute`) et le flag `force_crit` (octet **+5** du
> `Nullable<AttackOptions>`, le même struct dont l'octet +4 porte `force_overkill`). ⚠ **`IsCharging`
> n'est PAS `HasMoved`** — le lot d'effets `SmashaEad`/`AvalancheOfMuscle`/`FeederTendrils`
> (`entities/effects/loki/extra_damage.py`) modélise toujours ce nœud par `has_moved` : approximation
> **plus large**, antérieure, **non touchée** ici → résidu à rabattre (cf. §4.b, entrée `N9`).
| … dont **non pertinents** (npc + summon-env) | 29 | **29** | inchangé |
| actives **`[-D]`** (décision portée, combat NO-OP) | 20 (méthode réfutée) | **15 lineup + 2 npc** | **−3** |
| kits lineup | 123 | **123** | inchangé |
| kits lineup **COMPLETS** | 22 | **28** | +6 |
| kits **avec du travail** | 101 | **95** | −6 |
| items manquants (kit-coverage) | 139 | **126** | −13 |
| registre **sans `TARGETING_OPTIONS`** | 75 sur 76 | **40 sur 91** (après #181) | **−35 — la tendance s'INVERSE** |
| registre **sans `ABILITY_ATTACK_TYPE`** | 3 (constaté le 2026-07-27 au matin) | **0 sur 83** | **fermé** |
| passifs **portés** | 46 | **54** | +8 |
| passifs **gap** | 150 | **142** | −8 |
| passifs gap **confrontables** | 63 | **55** | −8 |
| overlays `CalculateCustomUtility` **non portés** | 16 | **15** | −1 (correction de comptage, cf. R15) |

**Les deux gisements « que notre propre cadence aggrave » ne l'aggravent plus.** `TARGETING_OPTIONS`
a reculé de 35 en deux jours (`89518da` 10 DarkAngels/Aeldari/WorldEaters, `ff66741` 13
Necrons/Orks/Votann/GenestealerCults, **`#181` 13 Ultramarines/Sisterhood/Tyranids/SpaceWolves/
AdMec/BloodAngels**, plus les masques posés en même temps que chaque nouveau port).
`ABILITY_ATTACK_TYPE` est à **zéro manquant** : la garde `probe_120` étape 0 passe au commit courant.

> **Re-dérivé au 2026-07-28, APRÈS #181** (`probe_181_targeting_gaps.py`, une commande) :
> `ABILITY_CLASSES` = **91**, sans `TARGETING_OPTIONS` = **40**, sans `ABILITY_ATTACK_TYPE` = **0**
> (`probe_120` étape 0 : « littéral de ctor manquant: aucun »). Les entrées neuves portent toutes
> leurs deux littéraux — c'est désormais le **cliquet**
> `tests/engine/runner/test_ability_registry_ratchet.py` qui l'impose, plus la seule discipline, et
> il a MORDU pour de vrai sur #181 (les 13 masques ont fait échouer le test tant qu'ils n'étaient pas
> sortis de la liste d'exemption). Le gisement `[-D]` passe de **15 à 14** en lineup (1199 en sort).
> *(Mesure intermédiaire du matin, conservée pour la tendance : 89 entrées / 53 sans masque.)*
La règle de non-régression du `CLAUDE.md` a donc pris — c'est le seul endroit de ce document où la
tendance s'est retournée, et il vaut de le noter avant que quiconque recopie « 60 restantes ».

---

## 1. Gisement 1 — les 89 actives NO-OP en combat

> Re-dérivé le 2026-07-28 (`audit_combat_ability_coverage.py`) : **171** actives castables, **82**
> portées, **89** NO-OP (91 la veille — `1017 FragBomb` et `1026 BasiliskBarrage` sont sorties du
> gisement). Ventilation NO-OP : DAMAGE **56**, EFFECT/BUFF 21, SUMMON 7, REPAIR 3, HEAL 2. La
> ventilation par confrontabilité ci-dessous date de la passe précédente et se re-dérive au besoin.

`AbilityHandler.visit_ActiveAbilityMessage` route tout `ActiveAbilityType` absent de
`ABILITY_CLASSES` vers un **NO-OP silencieux** (`ported:False`, 0 dégât, 0 effet, aucune erreur).

**Ventilation par confrontabilité** (gate HERO / MoW / SUMMON / NPC) :

| Verdict | N | Dispatchable ? |
|---|---|---|
| **HERO** — porteur lineup DANS le pool rank 17 | 45 | oui |
| **MoW** — porteur MoW du pool (harnais débloqué, `a9714a4`) | 2 | oui |
| **SUMMON** — porteur summon amené par un summoner du pool | 2 | oui |
| **HERO (catalog_inject)** — lineup absent du seed BC, injectable (`ab98129`) | 11 | oui |
| **SUMMON-ENV** — summon d'environnement, aucun summoner joueur | 8 | **NON CONFRONTABLE** |
| **NPC** — tous les porteurs sont npc | 21 | **NON CONFRONTABLE** |

⇒ **60 dispatchables, 29 non confrontables.** Taille par item = **1 ability**.

**Les 7 sorties depuis l'inventaire précédent**, toutes de la catégorie HERO-pool (d'où 52 → 45) :

| id | ability | porteur | commit |
|---|---|---|---|
| 1036 | FrenziedFiring | blackObliterator | `d2be96e` (#125) |
| 1116 | RadBombardment | admecDominus | `825f69f` (#128) |
| 1041 | BrazierOfHolyFire | adeptCanoness | `825f69f` (#128) |
| 1097 | Foehammer | spaceRockfist | `86fecad` (#131) |
| 1153 | HammerOfWrath | bloodIntercessor | `86fecad` (#131) |
| 1035 | PlagueWind | deathTyphus | `case-psychic-aoe` (#152) |
| 1102 | Doombolt | thousAhriman | `case-psychic-aoe` (#152) |

Les DEUX dernières entrent **avec** leur `TARGETING_OPTIONS` et leur `ABILITY_ATTACK_TYPE` (masques
LUS dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` : preset `statics+0x180` → `0x4002`
pour 1035, preset `statics+0x3c0` → `0x200000000000004` pour 1102) : le gisement
« sans `TARGETING_OPTIONS` » ne remonte donc pas de leur fait (il était à **53** à ce moment-là ;
**40** depuis #181 — cf. §3).

**La liste nominative des 60 dispatchables et des 29 non confrontables n'est pas recopiée ici** :
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

**Compte re-dérivé : 13 en lineup** (+ 2 npc non confrontables). Source = `kit-coverage.md`
régénéré, dont le critère `D` a été corrigé entre-temps.

> **−2 le 2026-07-28** (`case-bl-1029-1020`) : `1020 HeraldOfTheApocalypse` et `1029 Drachnyen`
> sont PORTÉES et confrontées live. Leur symptôme, qui était « non mesuré », l'est désormais —
> c'était bien le pire cas du gisement : Herald **8450 + 7713 PV non infligés sur DEUX unités**,
> Drachnyen PV du caster **non SETÉS** (10038 au lieu de 6480) + attaque normale jamais
> dispatchée. Les deux étaient des NO-OP complets, pas des casts dégradés.

> **La méthode de comptage de l'inventaire précédent a été RÉFUTÉE, et c'est important.** Il
> annonçait 20 en comptant `_NONCOMPARABLE_ABILITIES` comme un 4ᵉ registre de décision. `8e8518e`
> a tranché : y figurer signifie seulement que le port **CLASSE** l'ability NonComparable (il
> s'interdit de fabriquer un dégât depuis minDmg/maxDmg) ; son **UTILITÉ de décision** vit dans
> `PLAYBOOKS` et reste à porter. Compter ce registre comme `D` commet l'erreur **symétrique** du
> sous-comptage : déclarer porté ce qui ne l'est pas. L'audit le signale désormais à part
> (« NC classée, utilité NC non portée », 1 occurrence : RadBombardment — **qui a depuis reçu sa
> face combat**, donc l'occurrence a disparu).

Les 13 restants, tous à porteur **HERO du pool** (les 2 fermés restent listés, barrés, pour que le
sens de la marche se lise) :

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
| ~~1020~~ | ~~HeraldOfTheApocalypse~~ | blackHaarken | `REGISTRY` | **FERMÉ** (`case-bl-1029-1020`) — mesuré avant port : 8450 + 7713 PV non infligés sur 2 unités | — |
| ~~1029~~ | ~~Drachnyen~~ | blackAbaddon | `REGISTRY` | **FERMÉ** (`case-bl-1029-1020`) — mesuré avant port : SetHealth muet (10038 au lieu de 6480) + attaque normale non dispatchée | — |
| 1100 | SorcerousFacade | thousTzaangor | `REGISTRY` | non mesuré ; lire `case-171` (interaction attaque normale) | 1 ability |
| 1177 | LightOfSanguinius | bloodDante | `REGISTRY` | non mesuré | 1 ability |
| 1137 | MurderousSwing | worldExecutions | `_SPECIAL` | **mesuré côté décision** (`case-108` : ×1,60 + 4 events) — face combat toujours NO-OP | 1 ability |
| 1171 | DakkaDakkaDakka | orksKillaKan | `_SPECIAL` | non mesuré | 1 ability |

**NON CONFRONTABLES** : 1192 `NovaBoost` et 1194 `NovaShield` (`tauBossRiptide`, npc-only).

**Sorties depuis l'inventaire précédent** : 1036 FrenziedFiring (`d2be96e`), 1116 RadBombardment
(`825f69f`), 1153 HammerOfWrath (`86fecad`) — les trois ont reçu leur face COMBAT. **Depuis le
2026-07-28 : 1199 `DoomSiren` (`emperKakophonist`) sort de ce gisement** — face COMBAT portée
(`engine/runner/abilities/emperorschildren.py`), validée live (`test_doom_siren_live.py`, 4 tests).
Le compte du gisement passe donc de **15 à 14** en lineup. Dans le même lot, **1115
`FearOfTheUnseen` (`tyranDeathleaper`)** quitte les NO-OP combat (elle n'était pas dans cette table :
son registre de décision est vide) — `engine/runner/abilities/tyranids.py`, validée live
(`test_fear_of_the_unseen_live.py`).

> **Piège de lecture à ne PAS reproduire** : un tag « déjà porté » sans préciser la FACE est un
> faux constat. `port-roadmap.md` §6.3 dit « MurderousSwing 1137 DÉJÀ porté #108 » — le port #108
> est la face DÉCISION seule (`entities/abilities/active_ability.py`) ; la face COMBAT est un NO-OP.

Symboles natifs : `IdunBattleLogic.Entities.Abilities.Active.Loki.<Nom>Ability$$ExecuteBehaviour`
pour tous, sauf `MurderousSwing` et `LightOfSanguinius`
(`IdunBattleLogic.Entities.Abilities.Active.<Nom>Ability$$ExecuteBehaviour`, sans `.Loki`).

---

## 3. Gisement 3 — `TARGETING_OPTIONS` : 40 abilities du registre sur 91 sans masque

**Symptôme chiffré** (re-dérivé du code après #181, `probe_181_targeting_gaps.py`) :
`ABILITY_CLASSES` = **91** entrées, **51** portent `TARGETING_OPTIONS`, **40** n'en ont pas.
Le gisement RECULE franchement (75 manquants le 2026-07-26, 53 le 2026-07-28 au matin, **40**
après #181) et **ne monte plus** : les entrées neuves arrivent AVEC leur masque, le cliquet
(`tests/engine/runner/test_ability_registry_ratchet.py`) les rejetant sans.

> **#181 (2026-07-28)** : **13 masques** posés d'un coup — `ultramarines` (1002, 1003, 1004, 1159),
> `sisterhood` (1025, 1062, 1187, 1188), `tyranids` (1112, 1145), `spacewolves` (1089),
> `admec` (1139), `bloodangels` (1230). Ces six modules passent à **100 % couverts**. Les deux
> formes du ctor sont représentées (flags directs ×9, preset statique ×4 : `TO+0x80` pour 1004,
> `TO+0x140` pour 1062, `TO+0x40` pour 1089 et 1230), et **aucun masque du lot n'est déductible d'un
> autre** — `SporeMineLauncher` (1145, `0x40046001042`) est `SquigMine` (1201, `0x46001042`) **plus**
> le bit 42 `TargetIsNotAdjacentToEnemy`, et 1003 impose l'adjacence là où son porteur a une arme r3.
> Garde live : `tests/engine/runner/test_ability_target_gate_lot181_live.py` (26 tests) confronte
> chaque masque à `abilityReason` **et** mesure le ROUGE AVANT (sans masque, le port acceptait).

> **case-231 (2026-07-28)** : les deux masques du lot viennent d'un **preset statique** — leur
> `.ctor` n'appelle AUCUN `TargetingOptions$$.ctor`, il recopie 0x40 octets. Le masque effectif est
> la constante écrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28` :
> `statics+0x40` = `TargetIsEnemy` (1154), `statics+0x280` =
> `CasterIsPossibleTarget | CasterMatchesDynamicRule` (1184). C'est la **2ᵉ forme du piège**
> documentée ci-dessous, et elle se lit — le `cctor` porte aussi le `TargetingRange` (`RANGE_ADJACENT`
> / `RANGE_SELF`) et le `isSelfCasting`. Détail : `docs/rl/case-231-ischarging-forcecrit.md` §5.

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

**Ventilation par module — c'est la carte de dispatch** (re-dérivée après #181 ;
modules absents = **100 % couverts** : `admec`, `aeldari`, `bloodangels`, `darkangels`,
`genestealer`, `necrons`, `orks`, `sisterhood`, `spacewolves`, `tyranids`, `ultramarines`,
`votann`, `worldeaters`) :

| module | sans | ids sans masque |
|---|---|---|
| `splash` | 6 | 1000 GauntletsOfUltramar, 1051 Stikkbomb, 1065 ScythingTalons, 1078 Fragstorm, 1098 PlasmaGrenade, 1105 CrushingClaws |
| `strike` | 6 | 1014 ArmoriumCherub, 1018 ValkyrieStrike, 1043 ThunderousAssault, 1104 SpiritLeech, 1122 CordClaw, 1163 BlackRage |
| `blacklegion` | 5 | 1021 Incursion, 1022 BringerOfDespair, 1036 FrenziedFiringCombat, 1147 HadesAutocannons, 1148 DaemonicOrdnance |
| `deathguard` | 5 | 1037 RevitalizingMalignancy, 1040 SpawnPoxwalkers, 1042 FlailSwing, 1168 EntropyCannons, 1169 PlagueburstMortar |
| `summon` | 5 | 1007 ScarabHive, 1045 GetEmRuntz, 1047 ScarabSummon, 1096 MasterOfTheTutelaries, 1166 AberrantHypermorph |
| `tau` | 5 | 1077 EarlyWarningOverride, 1081 FightingRetreat, 1082 InspiredToGreatness, 1160 HeavyRailRifle, 1161 TwinSmartMissileSystem |
| `astramilitarum` | 4 | 1016 SendInTheNextWave, 1028 SupremeCommander, 1142 MalleusRocketLauncher, 1143 ForwardSpotter |
| `imperative` / `mv71` / `quickening` / `stormcaller` | 1 chacun | 1118 DoctrinaImperatives · 1076 MV71SniperDroneSquadAttack · 1151 TheQuickening · 1113 Stormcaller |

> Les modules de **faction** sont désormais tous couverts. Ce qui reste est concentré dans les
> modules de **PATRON partagé** (`splash`, `strike`, `summon` = 17 des 40) plus `blacklegion`,
> `deathguard`, `tau` et `astramilitarum`. Un lot par module reste le bon découpage : ces
> modules-là sont les plus exposés à la collision entre agents, à dispatcher un seul à la fois.

⚠ `1151 TheQuickening` est précisément l'ability citée par la doctrine comme exemple de l'overload
PRESET + flags : ne pas recopier son littéral visible.

---

## 3bis. Gisement 4 — les PASSIFS (207) : le plus gros volume, et le plus invisible

Re-dérivé au commit courant (`audit_passive_ability_coverage.py`) :

```
passifs=207 | enum : TriggeredAbilityType=206, ActiveAbilityType=1
porte=55  zone-grise=11  gap=141
confrontables : gap=54  zone-grise=7
canaux : T=24, O=6, E=35, G=1, X=0, B=3
```

⇒ **54 passifs à porteur confrontable, non portés** (63 l'avant-veille, 55 la veille — 9 fermés par
`b8af57a` DestroyTheWitch/MartialSuperiority, `5c45389` CosmicHorror/SpiritualLeader, `137ef85`
RealityUnbound/TimeFlux-regen, `3848490` LionHelm/FearedInterrogator, et **BarbedOvipositor**
(`tyranParasite`, canal **T**) — summon-on-kill confronté live sur ses DEUX faces : Ripper Swarm sur
la tuile du mort à **6282 PV** == `WithStatsFromConfig` (L50 ×180 %), et **0 summon** sur une victime
`Mechanical`. La cadence de fermeture de ce gisement est donc de l'ordre de 4-5/jour.

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

> Colonne implicite de cette passe : **VALIDE** = relu au code (références `fichier:ligne`
> corrigées quand elles avaient dérivé) ; **hors intersection** = la colonne Fichiers n'intersecte
> pas `git diff 2cef371..HEAD`, donc inchangé par construction.
>
> ⚠ **RE-ANCRAGE #169** : la scission VERBATIM de `operations/damage_ops.py` (1086 l.) et de
> `operations/triggers/dispatch.py` (1290 l.) en PACKAGES a atterri pendant le dernier rebase de
> cette passe. **Ces deux fichiers n'existent plus** — toute référence `damage_ops.py:NNN` /
> `dispatch.py:NNN` d'un document antérieur est morte. Les entrées OUVERTES (R4, R6, R7, R12,
> R19a, N2, N8, O4) sont ré-ancrées ici sur les nouveaux modules. Les références des sections **§5
> (PÉRIMÉS)** sont laissées telles quelles : elles décrivent l'état du code AU MOMENT de la
> fermeture, ce sont des traces historiques, pas des ancrages à suivre.

| # | Résidu | Symptôme chiffré | Symbole natif | Porteur / chemin en bataille | Fichiers | Taille |
|---|---|---|---|---|---|---|
| **R32** | **NEUF (2026-07-28)** — **le gate `IsCharging` n'est porté sur AUCUN des trois effets qui le portent** (`AvalancheOfMuscle_ExtraDamage` 1025, `BlackRage_ExtraDamage` 1343, `FeederTendrils_ExtraDamage` 1197). Le canal modifier du port est ÉVALUÉ EAGER : il ne sait pas exprimer « l'unité est entrée au contact ce tour », donc le bonus est simplement absent. Les deux fiches existantes le rangeaient en « magnitude négligeable » — **ce n'est plus vrai** : mesuré ici à **+45 %** du coup | **MESURÉ** (`probe_avalanche_charge_gate.py`, `astraBullgryn` passif niv. 50 / multiplicateur 180 % ⇒ `extraDmg = 599`) : caster ayant BOUGÉ ce tour → live **+599 par coup** sur les ennemis ADJACENTS au caster (ni sur l'allié adjacent, ni sur les ennemis à distance 2), offline **+0**. Sans charge : **bit-exact 4/4** (attaque normale) et **18/18** (FragBomb). Se reproduit à l'identique sur l'ATTAQUE NORMALE du porteur ⇒ résidu du PASSIF, indépendant du vecteur d'ability | `IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack` (`ForAddition(OwnerIsCaster & IsCharging, ConfigVar(8))`) ; jumeaux `…BlackRage_ExtraDamageEffect$$…` et `…FeederTendrils_ExtraDamageEffect$$…` | `astraBullgryn` (**HERO du pool**), `bloodDeathCompany`, Deathleaper | `engine/entities/effects/loki/status.py`, `engine/entities/effects/factory.py`, contexte d'attaque per-coup (`attacker_modifiers`) | **1 sous-système** — le débloqueur est COMMUN aux trois effets : threader « entré au contact ce tour » dans le ctx d'attaque |
| ~~**R1**~~ | ~~Tuile d'ORIGINE dans les candidats d'ability du port, pas du natif~~ — **FERMÉ, PRÉMISSE RÉFUTÉE** : le slot +0xe est `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` (`OrderedSet` SEEDÉ avec `GetUnitPosition(unit)` puis `UnionWith(movable)`), donc **le natif MET l'origine dans ses candidats, en premier**. Le vrai écart était l'**ORDRE** du sweep (`Bucket$$AddAction` keep-first ⇒ à utilité égale le natif reste sur place) | réfutation live : **10** chunks natifs « caste sans bouger » avec movable NON vide (3 couples). Gain porté : `stay` 1/2 -> 2/2 (`C3_01`/31337, Stormcaller) et 8/9 -> 9/9 (crafté `C4_02`/4242, Njal) ; 0 régression sur 5 couples | `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` -> `IBattleQuery`+0xe ; `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` | tout hero du pool | `engine/ai/{context,state_bridge,action_generators}.py`, `engine/playbook/noncomparable/_base.py` | **LIVRÉ** — cf. `case-r1-origin-action-tile.md` |
| **R1-b** | **Ordre RELATIF des tuiles de move dans le sweep de position** — non porté | tie 192.851 entre deux tuiles de move (`C4_09`/999 pas 14) : le natif prend `(4,4)` = 1re **rankée** ; imposer l'ordre `aiMovableTiles` fait **régresser** pos 15/20 -> 14/20 | `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles` (slot 4 d'`IMovementQuery`) + l'`ExceptWith` de `$$GetMovablePositionsFor` — quel ordre l'`OrderedSet` porte-t-il ? | tout hero du pool | `engine/ai/action_generators.py` (`_best_attack`) | **1 sous-système** — symptôme chiffré au dossier, RE ciblée d'une seule fonction |
| ~~**R5**~~ **FERMÉ 2026-07-27, PENDANT cette passe** (merge `17c2d74`, PR #151 — ma re-reproduction à `bec119f` était donc la DERNIÈRE : 1 failed / 2 passed, trace inchangée depuis 3 jours ; re-joué APRÈS rebase : **3 passed**) | ~~`test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` ROUGE~~ -> **CAUSE RACINE TROUVEE ET PORTEE** (`case-r5-skitarii-turn.md`) : le gate d'expansion `BasePathfinder$$NodesInNextLevel` -> `WalkPathfinder$$IsValidContinuePathTile` (bit 0x1 = effet de tuile `BlockEnteringUnitsTileEffect`) n'etait pas porte -> la flood-fill traversait les Swamp -> la passe IA choisissait une tuile ILLEGALE ((6,5)), a portee du SEUL ennemi 79, d'ou le changement de cible et le `hp 8536->8536` de l'ennemi mesure. Residus ouverts : R5-a (arbitrage de TUILE, axe elevation/menace), R5-b (gate non cable sur 5 autres appelants + `_pathdist_to_enemies`), R5-c (dependance au canal `tiles=tileMeta`), R5-d (bit 0x2 `GetEffectiveDepth`), R5-e (`load_state` ne pose jamais `ai_controlled`) | Oracle natif fabrique (Vanguard REEL invoque live par ControlEdict, joue seul au turn-start) : natif = move (4,7) cible 77 ; le TEST avait raison. Agrement `aiMovableTiles` 5 boards 0 ecart. L'indice `ability: 17` est **REFUTE** comme cause (id concret = 69 `Loki_NormalAttack` pour Marshall ET Vanguard, mais aucun etage de la voie normale offline ne le consomme) | `BasePathfinder$$NodesInNextLevel`, `WalkPathfinder$$IsValidContinuePathTile`, `WalkPathfinder$$GetTileBlockingReasons`, `StaticBattleRules.Effect$$NotBlockingMovementOfTraits` | admecDestroyer / Skitarii Vanguard -- SUMMON | `engine/entities/pathfinding/{walk_pathfinder,tile_blocking,fly_pathfinder}.py`, `engine/services/static_battle_rules.py`, `engine/ai/state_bridge.py` | -- (clos) |
| ~~**N6**~~ **FERMÉ (PR #155, `case-174`)** — MÊME cause que N7 : porteur `darkaStormSpeeder` = **MoW**, `minDmg`/`maxDmg` lus à l'**index 0**. Les 2 tests sont verts après le seul correctif de `snapshot.py` ; le diagnostic « étage perçage / `darkangels.py` » ci-dessous était FAUX | `test_hailstrike_phase2_live` ROUGE, 2 tests pas 1 | **RE-REPRODUIT au commit `bec119f`** (2 failed / 2 passed, chiffres INCHANGÉS malgré les 50 insertions de `darkangels.py` depuis) : (a) `test_hailstrike_attack_trigger_live` — « le trigger 1507 n'a PAS fire offline (`after_hit=[]`) » ; (b) `test_hailstrike_pierce_envelope_live` — « dégât live **2700** hors des bornes du port AVEC le bonus **[1688, 2532]** ⇒ la magnitude du perçage portée est fausse ». Le second est un **symptôme de magnitude chiffré**, pas un simple test rouge | registre `ACTIVE_ABILITY_TRIGGERS` / gates du `CreateTrigger` (a) ; étage perçage (b) | darkaStormSpeeder (**MoW du pool**) / Hailstrike — cf. `case-117` | `engine/runner/abilities/darkangels.py`, `engine/runner/operations/triggers/*`, test associé | **1 ability** (diagnostic d'abord). Probe présente : `probe_123_hailstrike_phase2.py` |
| ~~**N7**~~ **FERMÉ (PR #155, `case-174-mow-level-index.md`)** | **le `StatsComponent` d'une MoW est ÉCRASÉ : toutes ses variables per-niveau sont lues au NIVEAU 0** (`case-162` §4, « PORT-1 »). `load_state` appelle `_load_machines` (l.179) puis `_load_stats_and_effects` (l.182), dont la boucle sur `snapshot["units"]` **ne filtre pas `entityType`** — or `combatSnapshot` **inclut** les lignes `EntityType.Machine` depuis `d9d0008`. Pour la ligne Machine, `unitConfig` vaut `{"error":"visualId introuvable"}` ⇒ le ctx reconstruit n'a **ni niveau ni multiplicateur**, et `snapshot.py:393` pose ce `StatsComponent` niveau-0. `_load_machine_stats` (l.403), qui BÂTIT le bon ctx depuis l'`AbilityState` per-ability, s'exécute APRÈS et porte le gate `if … get_component(StatsComponent) is not None: continue` (l.324) — **il est donc systématiquement sauté** | **MESURÉ à `bec119f`** — `probe_162_mow_ability_level.py --mow orksRukkatrukk --ability SquigMine --var nrOfTiles` : `_machine_ability_state` = **(50, 140)**, `load_state` → `active_ability_level=0, multiplier=100`, `nrOfTiles` **2** au lieu de **4**, verdict imprimé « ECRASEMENT CONFIRME ». Test de garde ROUGE : `test_mow_effect_posers_live.py::test_squig_mine_confront_live` → `cardinal offline 3 != live 5`. `case-162` chiffre 3 autres écarts du même bug (`PlagueburstMortar` nrOfTiles 3 vs 7, `ThriceBlessedConflagration` nrOfRounds 1 vs 5, `EntropyCannons` `off_delta=20` vs `live_delta=1631`) et **4 tests rouges** | `IdunBattle.Operations.AddMachineOperation$$Execute` / `$$InitializeAbilitiesStatus` (le seul canal valable = l'`AbilityState` per-ability) | 8 MoW du pool | `engine/runner/snapshot.py` (`_load_stats_and_effects`) | **1 ligne** — correctif VÉRIFIÉ 4/4 par `case-162` (`continue` sur les lignes `entityType == Machine`), non appliqué car territoire d'un autre agent au moment du cas. ⚠ les effets de MoW doivent CONTINUER d'entrer dans le seed `EffectsState` (ils viennent de `decisionView.mows[].effects`, chemin indépendant) |
| **N8** | **NEUF — deux gaps découverts PAR la mesure d'O4a, laissés ouverts** : (a) **`load_state` ne seede pas `state.turn_counts`** — `State.turn_counts` (`state.py:99`) part à `{}` et n'est écrit que par `StartTurnOperation` (`turnflow.py:194`), donc **tout état chargé d'un snapshot a `{}`** ⇒ le gate `OwnerHasFinishedMinTurns(2)` de PileIn (`triggers/dispatch/turn.py:62` + `:106`, **RE-ANCRÉ après #169**) et celui d'Ambush sont MORTS offline ; (b) **`OwnerHasFinishedMinTurns` est PER-UNITÉ côté natif** — `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger` lit `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(unit)` (champ `+0x5c`), là où le port lit un compteur de **JOUEUR** (`state.turn_counts[player]`) | non chiffré isolément (les deux gates sont muets offline, donc l'écart ne se voit pas en agreement — c'est la signature « dégradation silencieuse ») ; la mesure d'O4a qui les a révélés est bit-exacte sur PileIn (4 datapoints, port 4/4) | `…UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger` → `UnitExtensions$$GetTurnsFinished` (`+0x5c`) ; côté joueur `TurnComponent+0x38` = `GetAmountOfTurnsStartedByCurrentPlayer` (DEUX compteurs natifs distincts, le port n'en a qu'un) | orksMekboyz (PileIn), genestealers (Ambush) — **pool** | `engine/runner/snapshot.py` (seed), `engine/runner/state.py`, `engine/runner/components.py`, `engine/runner/operations/triggers/dispatch.py` | **1 effet** — (a) et (b) se portent ensemble (le seed doit alimenter le compteur PER-UNITÉ, pas le compteur joueur) |
| **R4** | **VALIDE** (relu à `bec119f`, références EXACTES) — **Resolve slot-8 non matérialisé dans `execute_normal_like`** : `HitDamage.get_damage` court-circuite toujours à `min == max` (`damage_hits.py:49-50`) ; le seul resolve matérialisé (`damage_hits.py:269-270`, `if is_attack_damage_op: rng.next_internal(...)`) est enfermé dans la branche `post_roll is not None` (bounds-mode) | splash Psyker : le live consomme **1 `genrand_int32` de plus que le port par volet splash** — constant, mesuré sur pool=1 et pool=2, absent quand le splash ne fire pas. Avec `spread_pct=0` (tous les call-sites amount-mode, `combat.py:156-158`) → **0 tirage/coup côté port** là où le natif en consomme 1 | `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` appelle `Next(v, v+1)` **sans gate largeur-1** | astraPrimarisPsy / tout Psyker du pool | `engine/runner/operations/damage_hits.py` (branche reduce-then-roll de `_run_hits`), `damage_ops/normal_like.py::execute_normal_like` | **1 effet** — ⚠ conditionner à la FAMILLE de factory native, pas à la largeur des bornes (le porter inconditionnellement casse Stormcaller 3-hit bit-exact) |
| ~~**R6**~~ | **FERMÉ 2026-07-28** — **`execute_normal_like` ET `additional_hits` ARRONDISSENT** (`Fix64.Round(·, AwayFromZero)`), comme les deux autres vecteurs COMBAT. Ce n'était pas trois lois mais UNE : les deux voies natives de coups additionnels (`AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` → `ExecuteHits` ; `ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` → slot 0x3c `Core.Services.OperationProcessor$$AttackDamage` → `AttackDamageOperation$$Execute` → `ExecuteHits`) **et** `execute_normal_like` (mode `amount` d'`AttackWithAttackDamage` + `UseNormalAttackIfAble` on-appearance) retombent sur la MÊME `AttackDamageOperation$$ExecuteHit` que les coups d'arme | **MESURÉ** — `normal_like` (DeathFromAbove/`ultraSmnInceptor`, Bolter p20, cellules [159,239] tronquées vs [160,239] arrondies) : live == arrondi **30/30**, == troncature **0/30**, + TÉMOIN branche-armure 12/12 sur les deux modèles ; `additional_hits` (SquigHound predefined [2660,3988], Physical p1, armure forcée 6000) : live == arrondi **14/14**, == troncature **10/14**, les 4 écarts exactement sur frac ≥ .5 | `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` : `Fix64.Round(Mul(v, multiplier), AwayFromZero)` **inconditionnel** dès qu'un `Nullable<DamageModifiers>` HasValue | le prérequis (b) « branche perçage gagnante » était INATTEIGNABLE sur `Physical` p1 (aucune armure du roster > 2633, et la seule à 3513 est `BigTarget` ⇒ réveille `BeastSlayer` et casse (a)) → **levier NEUF `rl_duel build --armor-target`** | `damage_ops/normal_like.py::_reduced`, `additional_hits.py::reduce_group_damage` (foyer extrait) | **LIVRÉ** — cf. `case-r6-materialisation-normal-like-additional-hits.md`. Gardes : `test_normal_like_bounds_rounding_live.py`, `test_additional_hits_rounding_live.py`, fixture `_pierce_floor_regime.py` |
| ~~**R6-b**~~ | **FERMÉ 2026-07-28** — **le canal `additional_hits` résout en ROLL-THEN-REDUCE, 2 tirages/coup** : `ExecuteHit` commence par `IdunBattle.Core.HitDamage$$GetDamage` sur le `HitDamage` de l'`AttackData` — que `AdditionalHitsFromEffects$$GetAdditionalHitsData` bâtit par `HitDamage$$.ctor(min = descripteur.minDmg, max = Nullable(descripteur.maxDmg))`, donc **NON dégénéré** pour un groupe `predefined` ⇒ 1 tirage BRUT (LA valeur) + 1 resolve slot-8 **gaspillé mais consommé** (`RandomlyResolveMinMaxDamage` = `Range(min, max+1)` **sans gate `min == max`**, contraste EXACT avec `GetDamage` qui en a un). Porté par `post_roll=_reduce` + `is_attack_damage_op=True` = la branche déjà mirrorée et validée du vecteur ability bounds-mode de la MÊME famille ATTACK | **DEUX cas discriminants, sur deux AXES** : (a) LARGEUR DU MODULO — `orksRuntherd`/SquigHound, `Physical` p1, armure forcée 6000 : 1ᵉʳ coup reproduit **5/5** par roll-then-reduce, **0/5** par reduce-then-roll (11/11 vs 0/11 sur la campagne d'origine) ; (b) CONSOMMATION — `admecRuststalker`/CordClaw, `DirectDamage` **p100** (réduction = identité ⇒ 1ᵉʳ coup identique dans les deux ordres, seul le resolve gaspillé sépare) : 2ᵉ coup reproduit **7/7** avec resolve, **0/7** sans resolve, **0/7** en reduce-then-roll | `IdunBattle.Core.HitDamage$$GetDamage` ; `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` ; `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData` | `orksRuntherd`, `admecRuststalker`, `thousInfernalMaster` — **pool** | `engine/runner/operations/additional_hits.py` | **LIVRÉ** — cf. `case-r6b-additional-hits-roll-order.md`. Gardes : `test_additional_hits_roll_order_live.py` (les 2 axes) ; probe : `probe_r6b_additional_hits_order.py` |
| **R6-b'** | **NEUF, isolé PAR la mesure R6-b — RÉSOLU AU DÉCOMPILÉ, port non fait** : le `Maybe` de `GetStuckIn` n'est pas roulé sur les coups d'un GROUPE additionnel, et l'index du port repart à 0 à chaque `_run_hits`. Or `CurrentHitIndex` est le compteur de coups de l'**ATTAQUE**, **CONTINU** à travers les sous-opérations : `CurrentHitIndexFormula$$Calculate` lit `AbilityEntities+0x110`, alimenté par `EvaluateAfterHitTriggers(param_5)` = `param_3` d'`ExecuteHit` = `*(currentAttack+0x30)`, que `UpdateCurrentAttackAfterHit` incrémente après CHAQUE coup — et `ExecuteAdditionalHitsWithoutDamageProfileType` passe le MÊME `currentAttack` à `ExecuteHits` | `orksRuntherd` : 2ᵉ coup du groupe reproduit **3/5** seulement. Le modèle « **1 tirage de plus avant le 2ᵉ coup SSI le nombre de coups d'arme émis est IMPAIR** » le reproduit **5/5**, avec **3 seeds strictement discriminantes** (777 et 314159 imposent k=1 — 3 coups d'arme ; 31337 impose k=0 — 4 coups d'arme). Sur un porteur SANS `GetStuckIn` (`admecRuststalker`), les 2 coups sont bit-exacts **7/7** ⇒ attribution nette | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger` = `On(8) & AmountIsOdd(CurrentHitIndex()) & OwnerIsCaster & !AmountIsGreater(MinDistance(caster,target), Direct(2))` ; `IdunBattleLogic.Entities.DSLFactory$$AddBonusHitsToCurrentHitGroup` ; `IdunBattle.Operations.ADamageOperation$$UpdateCurrentAttackAfterHit` | `orksNob`, `orksRuntherd`, tout porteur de `GetStuckIn` — **pool** | `engine/runner/operations/damage_hits.py` (offset d'index de `_run_hits`), `engine/runner/operations/additional_hits.py` (threader `bonus_hit_chance`) | **1 effet** — reste à trancher au décompilé : ce que `AddBonusHitsToCurrentHitGroup` ajoute quand le hit-group courant EST un groupe additionnel. Probe LIVRÉ : `probe_r6b_additional_hits_order.py --case squig --extra-rolls N` |
| **R6-c** | **NEUF, mesuré au passage** — **bornes COMBAT des groupes `amount`** : la face combat native tire dans `RandomAmount(minDmg, maxDmg)` alors que le port applique `amount ± 20 %` sur le seul nœud d'affichage (`amount` = `minDmg`). Résidu déjà NOMMÉ dans la docstring de `CyclicIonBlasterAdditionalHitsEffect` (« face COMBAT non confrontée »), désormais **CHIFFRÉ** | `tauCrisis`/`CyclicIonBlaster`, `Particle` p35, armure 6000 : coups d'ARME bit-exacts (`[153,211,163,144,200,174]`), mais groupe live `[267,277,243]` vs port `[235,235,208]`/`[236,236,209]` — **au-dessus de la borne haute du port** (cellules ≤ 252) | `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` (field[1] = nœud de ROLL, field[2] = Average d'AFFICHAGE) | `tauCrisis`, `deathPutrifier` (ExplosiveMaladies/FoulInfusion), `blackObliterator` (FleshmetalGuns) | `engine/entities/effects/loki/hits.py` | **1 effet** — patron de correction DÉJÀ en place : `InfernalPactsAdditionalHitsEffect` expose `amount` **ET** `min`/`max` (bi-canal) |
| **R7** | **VALIDE** — **`execute_normal_like` ne threade pas `target_traits`** : `damage_ops/normal_like.py` passe `target_id`/`is_ranged` mais **pas** `target_traits`, que le vecteur ABILITY passe lui (`damage_ops/ability.py`). ⚠ **CORRECTION 2026-07-28 : la mention « idem `additional_hits` » est FAUSSE** — `execute_additional_hits` ne construit PAS de mods, il REÇOIT ceux de `execute`/`execute_ability_attack`, qui threadent tous deux `target_traits` ; le canal #179 est donc DÉJÀ correct sur cet axe | jumeau du prérequis levé pour `execute_ability_attack`, dont la mesure était **+443 = `extraDmg[50] × 160 %`** de `HeavyGravCannon` (gate `HasTrait(target, 5=Mechanical)`) | `IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` — un SEUL collecteur natif, pas un par famille | **VERROU DE CONFRONTABILITÉ RE-VÉRIFIÉ 2026-07-28 : RÉEL.** Les effets gatés `target_traits` sont **5** (`BeastSlayer_ExtraDmg`, `MartialKatah_DmgBonus`, `CondemnorStake_ExtraDmg`, `HeavyGravCannon`, `DestroyTheWitch`). `execute_normal_like` n'a que 2 routes live : (i) splash Psyker — **aucun** `lineup` n'est à la fois `Psyker` et porteur d'un des 5 (intersection VIDE sur les traits gameconfig) ; (ii) on-appearance d'un SUMMON — un summon ne porte que SES PROPRES traits dérivés (ground truth `test_summon_trait_effects_live` : `Diminutive`/`BigTarget` seedés depuis la config du SUMMON, pas du summoner), et aucun summon du pool ne porte l'un des 5. ⇒ **non dispatchable en port live-validé** ; le porter serait spéculatif | `engine/runner/operations/damage_ops/normal_like.py` | **1 effet** — rouvrir dès qu'un porteur d'un des 5 devient Psyker, ou qu'un summon d'un porteur hérite du trait |
| ~~**R8**~~ | ~~`--hp-target` remet `Armor`/`FixedArmor` à 0, et DEUX documentations le taisent~~ — **FERMÉ** par `3eee6c0`, cf. §5.1. Les deux supports le disent désormais, et le commit a AJOUTÉ le troisième que la fiche R8 ne connaissait pas : `--hp-player` a le MÊME effet | — | — | — | — | — |

### 4.b — Symptôme NOMMÉ (mécanique lue, pas encore chiffrée)

| # | Résidu | Symbole natif | Porteur / chemin en bataille | Fichiers | Taille |
|---|---|---|---|---|---|
| **N9** | **NEUF (2026-07-28, case-231)** — **Le lot extra-dégât `IsCharging` modélisé par `has_moved`** : `entities/effects/loki/extra_damage.py` gate `SmashaEad` / `FeederTendrils` / `AvalancheOfMuscle` sur `has_moved` (« l'unité s'est-elle déplacée »). Le prédicat natif est **strictement plus étroit** : `AreEntitiesAdjacent(caster, target) && ChargedUnitIds@+0x190.Contains(target.Id)`, où la liste ne retient que les unités devenues **NOUVELLEMENT adjacentes** pendant le pas. Une unité qui bouge sans arriver au contact, ou qui était **déjà adjacente avant son pas**, n'a PAS chargé — le port accorde donc le bonus dans des cas où le natif ne l'accorde pas. Le vrai nœud est désormais porté (`entities/triggers.py::IsCharging` + `components.update_charging`, confronté live par `test_case231_charge_forcecrit_live.py` sur un scénario où les deux modèles DIVERGENT) : il reste à y rabattre les trois effets. Biais **UNILATÉRAL** (le port sur-accorde) | `IdunBattle.Core.Services.BattleQuery$$IsCharging` ; `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` ; `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` (la purge) | orksNob (SmashaEad), astraBullgryn (AvalancheOfMuscle), tyranDeathleaper (FeederTendrils) — **HERO pool tous trois** | `engine/entities/effects/loki/extra_damage.py`, `engine/entities/effects/loki/status.py` (l.527-535, la note qui annonçait ce branchement) | **1 effet** (3 classes, un seul gate) |
| ~~**R9**~~ **FERMÉ** | ~~Magnitude de `Chronometron_ExtraDamage` (1550) — effet POSÉ mais INERTE~~ → **PORTÉ ET VALIDÉ LIVE** (cf. §R9-clos ci-dessous). `attacker_ctx` porte désormais `is_unit` / `team` / `team_by_id` / `traits` sur les DEUX faces ; `BaseEffect.times_applied` (= `EffectComponent+0x6c`) est modélisé ; classe `ChronometronExtraDamageEffect` + trigger de retrait `On(9)` | `IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` (+ `$$CreateRemoveEffectTrigger` = `On(9)`, effet CONSOMMÉ au 1ᵉʳ coup allié) | necroChronomancer — **catalog_inject** (confronté live, `probe_r9_chronometron.py`) | `engine/runner/damage_model.py`, `engine/playbook/prediction/_shared.py`, `engine/entities/effects/{base,factory}.py` + `loki/damage_reduction.py`, `engine/runner/operations/{effects.py,triggers/loki/chronometron.py}` | — (clos) |
| **R12** | **VALIDE** (relu à `bec119f`, puis **RE-ANCRÉ après #169** — `triggers/dispatch.py` est devenu un PACKAGE) — **Les 2 derniers consommateurs de `DSLFactory.Revive`, tous deux OUVERTS** : `triggers/dispatch/registry.py:261` enregistre toujours `"TimeFlux": [TimeFluxRegenAbility]` seul, avec le résidu GHOST-REVIVE écrit juste au-dessus ; `git log -S "GhostRevive"` ne rend toujours **aucun commit de port**. `FuelledByFury` (1251) : aucune classe, mention en commentaire seule (`triggers/dispatch/move_death.py:265`). ⚠ **RAPPEL utile** : la face DÉGÂT de `FuelledByFury` est un gap SÉPARÉ, chiffré par la mesure de R9 (+248/coup sur `ultraTitus`, `extraDmg[L50]=138 × 1,8`) — deux facettes du même passif, deux tranches | `IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` ; ancrage à hooker pour l'émetteur de `On(PendingDeathAdded=3)` : `IdunBattle.MatchState$$AddDeath` ; `IdunBattle.Operations.…$$SetRevivePosition` | ultraTitus, thousTerminator — **HERO pool tous deux** | `engine/runner/operations/triggers/loki/time_flux.py` (+ nouveau `fuelled_by_fury.py`), `triggers/dispatch.py`, `operations/revive.py`, `entities/effects/factory.py` | **2 abilities** (1 par consommateur) |
| **R13** | **VALIDE** (relu à `bec119f`, références EXACTES : `1005 in ABILITY_CLASSES` = `False`, aucune classe `TriggerAbility`/`ActorHasTriggeredAbility` dans `engine/`) — **`AdaptiveStrategy` (1005, `necroWarden`)** : 1005 en enum seul (`active_ability_type.py:111`), absent d'`ABILITY_CLASSES`. Restent 2 prérequis sur 3 : (1) `RelentlessMarch` 1004 en enum seul (`triggered_ability_type.py:149`), aucune entrée `ABILITY_TRIGGERS`/`TRAIT_TRIGGERS` — sans lui la branche `If(ActorHasTriggeredAbility) TriggerAbility(…)` est un no-op structurel ; (2) les nœuds `TriggerAbility` et `ActorHasTriggeredAbility` **n'existent pas** (0 définition dans `engine/`, inlinés en impératif par `cosmic_horror.py:310` / `sworn_protector.py:266`). Prérequis (3) OVERRIDE-ATTAQUE **CONFIRMÉ LEVÉ** (`stats.py:281`) | `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$ExecuteBehaviour` ; `…Loki.RelentlessMarchAbility$$CreateBehaviour` | necroWarden — **HERO pool** | `engine/runner/abilities/behaviours/lifecycle.py` (nœud `TriggerAbility`), `engine/entities/triggers.py`, `triggers/dispatch.py` + module RelentlessMarch, `abilities/necrons.py` + `handler.py` | **1 ability + 1 passif** |
| ~~**R14**~~ | ~~**Face DÉCISION des MoW**~~ — **FERMÉ le 2026-07-27** (`case-r14-mow-decision.md`) | chemin natif dédié = `IdunBattle.AI.Tactics.DefaultMachineTactic` (routé par `IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit` sur `IsMachine`), **pas** `aiPlaybookPredict` | 8 MoW du pool | `engine/ai/tactic.py`, `engine/ai/context.py`, `engine/battle_query.py`, `engine/runner/{components,snapshot}.py`, `engine_validate.py` | — |
| **R15** | **hors intersection** (`engine/playbook/loki_custom.py` et `docs/rl/case-27-custom-utility.md` sont absents de `git diff 2cef371..HEAD` ⇒ inchangé par construction) — **`CalculateCustomUtility` — overlays non portés : le compte réel est 15, pas 16 ni 21.** `REGISTRY` = **7** entrées : 6 posées par `loki_custom.py:283-286` (1014, 1177, 1020, 1029, 1199, **1100**) + `RepairPlaybook` (id 28) posée par `common.py:92` ; plus 1119 `Repair_GalvanicField` porté **hors** `loki_custom`. Sur les 22 overlays par-ability de `case-27`, **7 portés ⇒ 15 non portés**. ⚠ **`case-27-custom-utility.md:139` induit en erreur** : il classe 1100 `SorcerousFacade` « RE RESOLU, **non porté** (routage) », alors que `SorcerousFacadePlaybook` EST défini ET enregistré (`loki_custom.py:243-286`). Ce qui manque n'est pas l'overlay — c'est la **route de ciblage ALLIÉ** (le moteur route 1100 comme attaque d'ENNEMI à cause du `damageProfile`, quand le natif cible un allié Psyker). La ligne doit être re-libellée, sinon elle fait re-porter du code existant | par overlay, cf. `case-27` (formule mirroir par ligne) | mixte ; **4 des 15 sont npc** (1093, 1215, 1216, 1217) et 2 sont des verdicts fermés (1004 terme nul, `ProperKilly` dead-code sans id) ⇒ **9 réellement à débloquer** ; ~~le blocage restant est la face DÉCISION MoW = **R14**~~ **R14 est FERMÉ** (`case-r14-mow-decision.md`) : un caster Machine est routé vers `DefaultMachineTactic` et ses feuilles sont atteintes. Ce qui reste pour un overlay de porteur MoW est le port de la feuille de DÉCISION de son ability — **1187 est la seule des 16 abilities MoW à en avoir une** ; le sweep de `probe_r14_mow_decision.py --sweep` donne, par MoW, l'ability que le natif choisit (= l'ordre de priorité de portage) | `engine/playbook/loki_custom.py`, + correction de `docs/rl/case-27-custom-utility.md` (l.139 et ventilation l.157-160) | **1 sous-système par débloqueur**, puis 1 overlay/ability |
| **R17** | **hors intersection** (`summon_ai.py`, `engine/ai/bucket.py` absents du diff) — **Ordre intra-groupe de `PerformAIAction(asGroup=1)`** — `summon_ai.py:225` : `uid = valid[0]   # PickNextUnit (utilite natif -> ordre selecteur)`, résidu écrit l.211-214 ; `collect_ai_controlled` l.57 rend `sorted(out)` = ordre d'id. Live observé : les 2 gardes de SupremeCommander agissent dans l'ORDRE INVERSE de leur spawn. Manque la sémantique des 8 ids de `UtilityBucket` (aucun dump d'enum) + le scoreur par-unité derrière le slot 1 | `IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$PickNextUnit` (slot 1 de `operator+0x28`, picker `operator+0x30`) ; `…DefaultGroupOperator$$.ctor` = 8 `IdunBattleLogic.AI.Utilities.UtilityBucket` (ids 0x4a/0x44/0x45/0x4c/0x4b/0x49/0x47/0x48) | astraCreed, orksWarboss — **pool** | `engine/runner/operations/summon_ai.py`, `engine/ai/bucket.py` | **1 sous-système** — sans incidence tant que les unités du groupe sont interchangeables |
| **R19a** | **VALIDE** (relu à `bec119f`, puis **RE-ANCRÉ après #169** — la fonction a migré dans `damage_ops/_channel.py`) — **Mode `AttackRangeType.Both` (3) non modélisé** : `damage_ops/_channel.py:15-49` : `hits_channel_is_melee(...)` fait `return is_melee` (l.49) ; la table de vérité native est en commentaire mais la valeur 3 n'est jamais calculée, le corps le dit (« Le port ne modelise pas `Normal`(3) »). Le port DÉCLARE la nature là où le natif la CALCULE. `services/battle_query.py:26` porte bien `AreUnitsInMelee` mais n'est consommé que par la sélection d'arme (l.85) | `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` = `AreUnitsInMelee(attPos, tgtPos)` pour ce mode | pool | `engine/runner/operations/damage_ops.py`, `engine/services/battle_query.py`, `engine/runner/abilities/behaviours/combat.py` | **1 effet** |
| ~~**R20**~~ | **FERMÉ 2026-07-27, PENDANT cette passe** (merge `fd1031e`, PR #152 — `fdc45c0` de-fork + `027ed84` ForwardSpotter 1143 routé sur le MAUVAIS constructeur + `0378ce3` état final). `summon.py:275-276` porte désormais le « AVANT » du fork au passé. ⚠ **la PR n'a PAS mis cet inventaire à jour** : l'entrée serait restée « ouverte » sans cette passe — c'est le mode de défaillance que le §5.5 décrit, appliqué à ce fichier-ci. Énoncé d'origine conservé pour trace : ~~**`SpawnReplica` ré-implémente `PerformAIAttack` à la main**~~ — `behaviours/summon.py:270-277` fait encore `_nearest_enemy` + `AttackDamageOperation.execute`, **sans gate de portée ni dispatch after-hit**, alors que le corps unique est appelé juste au-dessus (`summon.py:162` → `perform_ai_attack_from_current_position`, de-forké par `7f47c29`). Docstring l.241-242 assume encore l'approximation | `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttack` — MÊME `PerformAIAbilityUnitBehaviour` que `…FromCurrentPosition` à un champ près : `+0x78` (budget de déplacement) fourni par l'appelant au lieu de `factory+0xb8 = Direct(0)` | necroSpyder (ScarabSummon 1047) — **HERO pool** | `engine/runner/abilities/behaviours/summon.py` | **1 effet** (rabattre sur le corps unique ; l'amount reste inerte tant qu'aucun étage ne fait bouger un summon avant son attaque) |
| ~~**R24**~~ | ~~`tests/conftest.py` écrit ses state-files dans `data/`~~ — **FERMÉ** par `3eee6c0` : `conftest.py:58-59` pose désormais `STATE_PREFIX = ROOT / "logs" / "_pytest_duel_state"`, avec le `mkdir(parents=True)` qui va avec. L'override `TACTICUS_PYTEST_STATE_PREFIX` est conservé. Cf. §5.1 | — | — | — | — |
| **R25** | **VALIDE** (relu à `bec119f` ; lignes corrigées pour (b) : `167-169` → **`194-203`**, en-tête `l.25` → **`l.32`**) — **3 constantes de gameplay FIGÉES dans les tests** : (a) `test_damage_crushingclaws_live.py:178` `assert len(off_ph) == main["hits"] == 2` — le fichier n'importe NI `_config_oracle` NI `gameconfig`, le `2` est un littéral ; (b) `test_fragstorm_migration_live.py:194-203` cap `nrOfTargets` en dur (`min(#cands, 4)`, résidu **assumé** en en-tête l.32) — le fichier a pourtant été retouché par R28 sans que le cap bouge ; (c) `test_jakhal_stimms_live.py:288` `exp_loss = round(hp0 * 25 / 100)`. `_config_oracle.py` expose 6 accesseurs (`damage_profile_pierce`, `ability_damage_profile`, `assert_ability_damage_profile`, `trait_variable`, `global_constant`, `ability_variable_levels`) mais **toujours aucun `ability(<nom>).constants[<clé>]` générique** | oracle = la CONFIG (`gameconfig.ability(id).constants`) | — | `scripts/python/tests/engine/runner/` (3 fichiers) + `_config_oracle.py` (accesseur générique à ajouter) | **1 effet** (lot de 3 fichiers + 1 accesseur) |
| **R26** | **hors intersection** (`trait_damage_limits.py`, `damage_hits.py`, `damage_prediction.py` absents du diff) — **Rider OVERKILL de `ThrillSeekers`** (face PRÉDICTION) — `services/trait_damage_limits.py:243-245` : `is_overkill(..., allow_flag=0, ...)` en dur ; la signature `compute_prediction_overkill(cur_hp, max_hp, dmg_min, *, suppress=False, p12=0)` (l.230-231) n'a **aucun** paramètre trait/effet, et les 3 appelants ne passent rien. Non-porté explicite : `triggers/loki/thrill_seekers.py:90` | `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` force son `allow_flag` à 1 quand l'attaquant `HasTrait(0x420)` ET `HasEffect(0x59a)` ET (`default_flag` OU le flag de crit) | emper* — **pool** | `engine/services/trait_damage_limits.py`, `engine/runner/operations/damage_hits.py`, `engine/services/damage_prediction.py` | **1 effet** — biais UNILATÉRAL (le port sous-estime l'overkill des porteurs *Thrilled* qui critent, donc `OverkillUnitUtility`) |
| **R27** | **VALIDE** (relu à `bec119f`, référence EXACTE — le fichier a bougé pour #170 `get_Priority` sans que le seuil change) — **Seuil `should_evaluate` de BlackRage** : `playbook/noncomparable/black_rage.py:77` : `return hp <= hpmax * 0.5`, littéral en dur (commentaire l.76 « ConfigVar 0x26 = 50% … Lucien-only »), aucune lecture indexée par niveau, alors que la RE combat montre un `hpPct` **par niveau** (30 → 50 %) — correct seulement au niveau max | `IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$…` | bloodDeathCompany — **HERO pool** | `engine/playbook/noncomparable/black_rage.py`, `engine/entities/effects/magnitude.py` | **1 effet** — n'affecte pas la garde actuelle (Lucien caste à hp=1) |
| **R28** | **`PickRandomly` — FERMÉ** (2026-07-27, cf. `case-r28-pick-randomly-order.md`). (1) **ordre d'énumération du pool** — RÉEL, **porté et CONFIRMÉ LIVE** sur les deux itérateurs natifs (`IterateAdjacentTiles` = champ brut `boardGraph.neighbours` ; `IterateSurroundingTiles` = triple boucle CUBE) : la victime live suit l'ordre SOURCE, l'ordre id la rate. (2) **Fragstorm tire des HEXES** — RÉEL, porté (`tile_domain=True`, tuiles vides incluses = coup gaspillé) mais **INVALIDABLE LIVE** : le seul porteur de `Fragstorm` (1078) est `templSmnAggressor`, summon spawné par le POWER-UP `PowerUp_SummonSpawn_templSmnAggressor` — aucune unité du pool ne l'invoque, et `templAggressor` (pool) porte une AUTRE ability (`FragstormGrenadeLauncher`, chaîne de coups restants). Mirror-offline gardé par une assertion structurelle sur le pool. (3) **`AddForcedTargetsAndUpdateCandidates`** — **NON PERTINENT** : sa source `GetOnlyTargets(caster)` n'a qu'un écrivain natif (`InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour`, unique XREF de `DSLFactory$$AddForcedAttackTarget`), dont les 23 porteurs (trait `InstinctiveBehaviour` 2021) sont des npc/summons Tyranides SANS active ability ⇒ liste toujours vide, retour immédiat, **0 tirage** | `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` ; `IdunBattle.DSL.APickSelector$$AddForcedTargetsAndUpdateCandidates` ; `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` | BringerOfDespair (`blackTerminator`) + PlasmaCannon (`darkaTerminator`) — **confrontés** ; Fragstorm — **hors pool** | `engine/dsl/base.py`, `engine/entities/pathfinding/board.py`, `engine/entities/selectors/{tiles,units}.py`, `engine/runner/abilities/{behaviours/combat,loki/splash,necrons,darkangels}.py` | **FERMÉ** |
| **R30** | **À REFORMULER — le SUBSTRAT est porté et confronté live** (`94b7118`, `case-R30-multihex-substrate.md`) : `UnitComponent.feet` (mirror `_feet`, `None` = 1 pied), `get_unit_feet`/`get_feet_count`/`get_main_tile`, occupance par pied dans `state.py`, `movement_query` complet (`is_valid_unit_feet_list`, `get_possible_tile_lists_from_movable_tiles`), `ThreeUnitSpawnTileShapeSelector`, `_load_feet` depuis `observeBattle`, portée sur EMPREINTE. Confronté N=1 et N=3 (18 assertions offline + 7 tests live, garde vue rouge : port sans substrat → distance **2** et refus, natif et port avec substrat → **1** et accord). **Les DEUX corollaires de l'ancien énoncé sont PÉRIMÉS** : `ai/utilities.py` ne dit plus « retour 0.0 jusqu'au câblage du poids + feetCount » — le trou `GetFeetCount` est comblé, seul le POIDS BC reste à 0. **Ce qui RESTE ouvert** : (1) `DutyEternal` 1158 est **toujours** absent d'`ABILITY_CLASSES` (vérifié : `1158 in ABILITY_CLASSES` = `False`) — le substrat est là, l'ability ne l'est pas ; (2) les 5 résidus nommés du `case-R30` §6 — `HasPowerup` dans `CorrectArea`, centre d'une empreinte à 7 (inexerçable, aucun producteur dans ce build), gate `HasTrait(0x418)` de `GetMovablePositionsFor`, `MoveUnitOperation` ne déplace qu'une tuile (non confrontable : le seul multi-hex du build a `Movement = 0`), poids BC `DislikeStartingTiles` non identifié | `…Loki.DutyEternalAbility$$ExecuteBehaviour` (`RemoveMachine` + `Spawn(ThreeTileUnitSpawnShape)`) ; `MovementQuery$$GetMovablePositionsFor` gate `HasTrait(0x418)` ; `TileExtensions$$HasPowerup` | ultraDreadnought (**MoW du pool**) ; `AetherStride` (thousDaemonPrince, catalog_inject) — **non exercé** | `engine/runner/abilities/ultramarines.py` + `handler.py` pour (1) ; `engine/services/{movement_query,spawn_tile_shape}.py` pour (2) | **1 ability** pour (1) — plus le sous-système multi-hex, qui n'est plus « le plus gros de la liste » |
| **R31** | **`PerformAIAttack` avec `moveAmount = null` : l'acteur n'APPROCHE pas** — `abilities/loki/summon.py::perform_ai_ability_unit_behaviour` attaque depuis la tuile COURANTE quel que soit `move_amount`. Le décompilé tranche : `…DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext` appelle `GenerateActionTiles(unit, 1, <d__6+0x34>)` (3ᵉ arg = le `Nullable<int>`, `null` = plage de déplacement NORMALE) puis `if (<d__6+0x30> /* allowMoveAction */) generators.Add(<tactic+0x58>)` = le `MovementActionGenerator`. ⚠ **`d__6` n'instancie qu'UN `ActiveAbilityActionGenerator` sur UNE seule ability** (celle du `Func<IEntity,int>` caché du behaviour), là où `d__5` itère toute la liste `tactic+0x60` : réutiliser `decide_and_apply` tel quel serait un FORK. **DISTINCT du rouge Waaagh** (`case-r21-summon-movement.md`), qui passait par `PerformAIAction`/`d__5` et dont la cause était la stat MOVEMENT non seedée sur un summon spawné offline — ce résidu-ci reste OUVERT | `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttack` ; `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` ; `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` | necroSpyder (ScarabSummon 1047), astraYarrick (ForwardSpotter 1143), + HunterOfSouls / TheArdentBlade_Trigger / AetherStride / CallInReinforcements — **pool** | `engine/runner/abilities/loki/summon.py`, `engine/ai/tactic.py`, `engine/ai/action_generators.py` | **1 sous-système** — manque-à-agir, jamais une attaque illégale |
| ~~**N1**~~ | **`ArcaneShield` — FERMÉ** (`case-n1-arcane-shield-vector.md`). Les deux affirmations de la fiche d'origine étaient FAUSSES et sont réfutées au décompilé : (a) le code cité (`prio = 0 if (own_fac == own_fac) …`, tautologie) n'a jamais existé ; (b) **retenir un allié NON-Chaos est CORRECT** — `SurroundingFriends` ne filtre ni sur la faction ni sur le trait Chaos, qui ne pèse qu'une pénalité de +1. Ce qui était RÉELLEMENT faux : **le vecteur** (`On(4)` au lieu d'`On(0x1c=ArrivedAtFinalTile)` ⇒ aucun bouclier quand Thaumachus finit son tour sans bouger) et **le modèle de classement** — le natif n'a AUCUN palier lexicographique, il trie par le **score ADDITIF** `Sum(3×distance, faction, chaos, owner)` où **la distance (poids 3) domine la faction (poids 1)**. Mesuré : sur 4 configurations, le tri historique se trompait de cible dans **2** (un non-Chaos à d=1 vaut 5, un ThousandSons à d=2 vaut 6) | `…ArcaneShieldAbility$$CreateTrigger` / `$$CreateBehaviour` / `$$Distance` / `$$Faction` / `$$Chaos` / `$$Owner` | thousSorcerer — **HERO pool** | `engine/runner/operations/triggers/loki/arcane_shield.py`, `…/dispatch/{registry,move_death}.py`, `…/turnflow.py` | **FERMÉ** |
| **N2** | **VALIDE** (relu à `bec119f`, puis **RE-ANCRÉ après #169**) — **Famille ATTACK en bounds-mode : cap SCALAIRE là où le natif cape les CELLULES** : `damage_ops/ability.py:368` : `execute_ability_attack` passe `_target_limits(..., is_special=2)` **inconditionnellement**, y compris à `is_attack_damage_op=True` (le seul `is_special=1` est `damage_ops/normal.py:360`). En bounds-mode la branche ATTACK de `_run_hits` (`damage_hits.py:240-249`) applique `roll = _limits_scalar(roll)` = cap SCALAIRE post-tirage ; le cap sur les CELLULES pré-tirage n'existe que sous `limits["is_special"] == 1` (`damage_hits.py:303-316`), atteint uniquement par `execute` et `additional_hits.py:146` | `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` vs `…$$CalculateDamageOperation` (`Math.Max(0, dmg − shieldPart)`) | pool | `engine/runner/operations/damage_ops.py`, `engine/runner/operations/damage_hits.py` | **1 effet** |
| ~~**N5**~~ **RÉFUTÉ** | ~~Chaîne `&` derrière un `AddEffect` REFUSÉ : la chaîne se POURSUIT~~ → **le port était CONFORME ; c'est la DOC qui était fausse** (`case-n5-chain-after-refused-addeffect.md`). `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` zéro-initialise son `OperationResult` et **ne le réécrit jamais** — la valeur rendue par l'opération (l'entité-effet, `0` sur *chacun* de ses gates **et** sur la voie `UpdateExistingEffect`) est appelée via le slot 0x10 du processeur et JETÉE ; `IdunBattle.DSL.CombinedBehaviour$$Execute` ne court-circuite que sur le byte @+0x20, qu'aucune de ces voies ne pose. L'abandon s'arrête à l'OPÉRATION (ni l'itération du sélecteur-cible ni le combinateur). Le « GROUND TRUTH #224 » était un **CONFOND** (aucun DarkAngels à portée) : avec le camp joueur déployé au contact, `Pinned` est refusé ET l'override + l'attaque libre s'exécutent (10038 → 7442 HP). Le commentaire fautif d'`operations/effects.py` est corrigé, une garde live (4 tests, vue ROUGE par mutation) verrouille les deux sens | `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` ; `IdunBattle.DSL.CombinedBehaviour$$Execute` ; `IdunBattle.Core.OperationResult$$Combine` | darkaAsmodai / blackAbaddon — **pool** | `engine/runner/abilities/behaviours/effects.py`, `engine/runner/operations/effects.py`, `engine/entities/behaviours.py` | **RÉFUTÉ** |

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
| ~~**O1**~~ | ~~Aucune garde AUTOMATISÉE de synchro build ↔ `data/symbols/<HASH>` ↔ binaire chargé dans ghidra-mcp~~ — **FERMÉ** par `3eee6c0` : `scripts/python/symbols_sync.py` (neuf, 189 lignes) couvre les TROIS axes (binaire installé ↔ tables versionnées par sha256 ; cohérence interne nom-de-répertoire / `BUILD` / estampilles / en-tête Ghidra ; **ghidra-mcp ↔ tables**), est accroché au `SessionStart` (`session-start.ps1:26`, muet quand tout est synchrone, 1,3 s), et le défaut de `il2cpp_provenance` vise désormais `data/symbols/<HASH>/` au lieu des `data/il2cpp_*.tsv` supprimés. Serveur ghidra éteint = rapporté **NON VÉRIFIÉ**, ni succès ni échec. Vérifié EN ROUGE par son auteur sur 6 désynchronisations injectées. Cf. §5.1 | — | — | — |
| **O2** | **hors intersection** (`frida/host/ai-trace-store.ts`, `frida/host/router.ts`, `frida/hooks/features/ai-trace*` absents du diff — seul `ai-step/internals.ts` a bougé) — **Pas de drain à la demande des ai-traces** | `frida/hooks/features/ai-trace/state.ts:127-132` : `emit()` fait un `send({t:"ai_trace", …})` immédiat, **aucun buffer** côté agent. `frida/host/ai-trace-store.ts:62-84` écrit ligne à ligne dans `frida/data/ai-traces/<sessionId>-<iso>.jsonl` (docstring l.18 : « no in-memory aggregation, just write-through »). Routes existantes (`router.ts:788-834`) : `status` / `enable` / `disable` — **aucune route `drain`/`flush`/`consume`/`clear`**, aucun RPC de drain côté hooks. Les 8 consommateurs Python lisent le RÉPERTOIRE. **Finding annexe : `aiTraceStoreStatus` (l.100-114) n'est référencé par AUCUNE route ni aucun module — code mort** | `frida/host/ai-trace-store.ts`, `frida/host/router.ts`, `frida/hooks/features/ai-trace*` | **1 sous-système côté hooks** — ⚠ **exige rebuild + reinject**, donc à programmer quand l'atelier est vide |
| **O3** | **RÉSOLU — `case-o3-tile-effect-dynamics.md`** | L'énoncé d'origine était en partie faux : les timers de tuile ÉTAIENT décrémentés (`EndTurnOperation.execute` balaye TOUTES les clés de `by_unit`, tuiles comprises) et le gate `AreEqual(coverPatch, target)` de `LightCoverEffect` EST porté (A3, `d9d0e6c`). Le vrai trou, MESURÉ : (a) le décrément n'était pas clampé (`RemoveOneTurn` = `if (0 < Duration) Duration--`) et surtout (b) **rien ne RETIRAIT l'instance à 0** — `expired` n'est lu que par `active_effects`, alors que `has_effect` et `collect_effect_triggers` ne filtrent que `consumed` ⇒ un feu de tuile brûlait pour toujours (`(remaining, has_effect)` = `(-4, True)` au 6ᵉ tour). Natif : `EndTurnOperation$$RefreshEffects` itère TOUTES les entités-EFFET (aucune distinction unité/tuile), puis `RefreshEffectsOperation$$RefreshEffect` prend la branche retrait sur `EffectComponent$$ShouldBeRemoved` (`HasTurns && Duration == 0`). **+ transition d'ENTRÉE portée** : `LightCoverAbility` (`On(0x24=UnitPositionChanged_1)`, gate de traits `BigTarget/Vehicle/Mounted` lu au `.cctor`), câblée dans `after_move_triggers` ET `displace_triggers` | `engine/entities/effects_state.py`, `engine/runner/operations/triggers/tiles.py`, `engine/runner/operations/triggers/dispatch.py` | **fait** — reste hors périmètre : spawn/revive sur cover, autres tile-abilities d'entrée, `DespoiledGround` (#85, cf. case §6) |
| **O4** | **Résidus de PLACEMENT laissés par `case-130` SS5** | (a) **RÉSOLU, `case-o4a-maybe-trigger-rng.md`** : le nœud `MaybeTrigger` existait déjà (posé par `case-1203`) mais n'était CÂBLÉ qu'à un seul site ; PileIn restait DÉTERMINISTE (0 tirage) et `LetTheGalaxyBurn` roulait dans le mauvais ORDRE avec la mauvaise primitive. Câblé + branche `!CanUseRandom` (`99 < chance`) portée. Ancrage LIVE bit-exact sur PileIn : **4 datapoints, port 4/4 sur le compte de `genrand_int32` ET le nombre de spawns, port d'avant 0/4** (succès du gate : live 5 / port 5 / avant 4 ; échec : live 1 spawn 0 / port 1 spawn 0 / avant 4 spawn **1** = un grot fantôme) ; (b) **VALIDE** (ligne corrigée `277` → **`274`**) — **`Swamp -> Thorns_DefenseReduction` (−25) porté en LOCAL** : `spawn.py:274-276 _PLACEMENT_TERRAIN_EFFECTS` (consommé l.339) au lieu de `utilities/tile.py:93 TERRAIN_TILE_EFFECTS`, la table partagée alimentant aussi le contexte de DÉGÂT et le scoring de MOUVEMENT ; (c) feuilles `Tile(7)` gatées sur l'unité dans le tri de placement (ctor replié par le linker, aucun scénario mesuré ne les réveille) ; (d) on-appearance `PerformAIAttackFromCurrentPosition` du grot SquigHound : écart **CONSTANT de 4 `genrand_int32`** mesuré sur ce vecteur (MC1_67/777 et C2_37/31337), étranger au placement | `engine/runner/operations/triggers/dispatch.py`, `engine/runner/operations/spawn.py`, `engine/utilities/tile.py`, `engine/runner/damage_model.py` | **1 effet chacun** ; (a) est le plus large (touche tout gate `Maybe`/`chance` du DSL) |
| **O5** | **Résidus RNG du canal de coups d'ability (`case-61`)** | (b) `On(PreAttack=5)` absent du vecteur ability (**fidèle** : le natif l'émet depuis `ALoki_NormalAttackAbility$$ExecuteNormalAttack`) ⇒ sur ce vecteur `LetTheGalaxyBurn` ne s'arme que par `TargetHasTileEffect` ; (c) per-coup non bit-exact contre `templChampion` (même nb de coups, dégât différent — effets `MartialSuperiority`/`RapidAssault_ExtraDamage` de la cible ; le témoin `necroWarden` est bit-exact) ; (d) **VALIDE** — flag `Moved` absent de la face PRÉDICTION (×1,25 uniforme `HeavyWeapon_ExtraDmg` sur tout caster ranged déjà déplacé). Re-vérifié à `bec119f` : `has_moved` n'existe QUE côté combat (`entities/effects/base.py:181-183`, `effects/__init__.py:107`) ; `playbook/prediction/_shared.py` — qui a pourtant été élargi par R9 — n'en porte toujours aucune trace. Débloqueur = exposer `UnitFlagsComponent`, **rebuild requis** (le SEUL des 5 items de §4.e qui le soit encore). Plus, **distinct et chiffré** : conso RNG du canal #179 non bit-exacte — sur un cast de `FrenziedFiring`, les coups d'ARME sont bit-exacts (K=0, 2 seeds) mais les 2 coups additionnels diffèrent en valeur (port `[2735, 2553]` vs natif `[2481, 2754]`), désalignant tout ce qui suit la première attaque d'un volet AoE | face prédiction, `engine/runner/operations/additional_hits.py` | **1 effet chacun** — à promouvoir sur miss d'agreement |
| **O7** | **NEUF — le RPC `combatSnapshot` CORROMPT tout runner qui contient une entité `EntityType.Machine`** (`case-162` §2, « HARNAIS-1 ») | Après un `combatSnapshot` sur un runner où une MoW est déployée, **toute pose d'effet ultérieure est un NO-OP silencieux** — sur ce runner, définitivement (survit aux fins de tour). `applyAction` rend `ok=true`, l'action est consommée, et **le dégât passe normalement** (`ThunderousAssault` : 6180 PV avec ET sans corruption) : seuls les events de pose d'effet disparaissent (15 events → 7). Ce n'est pas propre aux MoW : le cast d'une UNITÉ est frappé pareil dès qu'une Machine est sur le plateau. Contre-épreuves : `decisionView`+`abilityTargets`, `observeBattle`, `boardGraph`, `tileMeta`, `dumpRng`, `statModSources` (qui exerce pourtant `GetStat` sur les Machines) et `aiPlaybookPredict` caster-MoW ne corrompent PAS ; le même runner **sans** MoW + `combatSnapshot` ne corrompt pas. **Coût mesuré : 13 tests rouges** dans deux suites (`test_mow_effect_posers_live`, `test_mow_groups_bcd_live`), imputés à tort au moteur avant le diagnostic ; parade en place = snapshot pris sur un **runner JUMEAU** rejoué puis disposé (`_twin_snapshot`), donc les suites mesurent de nouveau, mais l'outil reste cassé. La sortie silencieuse côté natif se lit dans `IdunBattle.Operations.AddEffectOperation$$Execute` : un appel d'interface au slot `+0x28` de la définition d'effet rend un booléen qui fait `return 0` sans rien poser ni logger. Suspects côté hook (les seuls invokes que `combatSnapshot` est SEUL à faire sur une entité Machine) : `UnitExtensions$$GetUnitPosition(machine)` puis `CachedDamagePredictionQuery$$GetNormalAttackPrediction` (`readNormalAttack` — qui ne rapporte RIEN sur une MoW hors-plateau, la ligne rend déjà `{"error":"aucune cible atteignable au deploiement"}`), et `UnitExtensions$$GetStat` aux parts 0/2/3 | `frida/hooks/features/ai-step/rpc-snapshot.ts` | **1 sous-système côté hooks** — ⚠ **exige un hook de diagnostic donc rebuild + reinject** : à programmer quand l'atelier est vide, comme O2. Piste à essayer EN PREMIER : ne pas appeler `readNormalAttack` pour les entités `Machine`, puis re-jouer les deux suites SANS le jumeau |
| **O6** | **`LetTheGalaxyBurn` — ORDRE de consommation RNG : RÉSOLU (`case-o4a-maybe-trigger-rng.md`)** | Le seuil était déjà **validé** (`probe_84_ltgb_chance.py`, 8 runners, branche A n=73 → **34,2 %**, branche B **23/23**). L'ORDRE l'est désormais aussi : `IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger` évalue gauche puis droite, donc `Maybe` passe **AVANT** `!HasTileStatusEffect` — le port consomme maintenant son tirage **sur les deux branches** (mesuré : 1 tirage tuile nue ET tuile à effet ; le port d'avant en consommait **0** sur la branche bloquée). La **primitive** a été corrigée dans la foulée : `NextBool(chance)` = `next_internal(1,100) <= chance` (borne **99**) et non `next_internal(0,100) < chance` (borne 100) — les deux verdicts divergent sur **90 graines / 199** à `chance=33` (`r % 99` et `r % 100` sont décorrélés), ce n'était donc pas un écart seulement statistique. **Reste non confronté bit-exact LIVE** : le porteur ne l'est pas lui-même (cf. `test_bringer_of_despair_live.py`) | `engine/runner/operations/triggers/loki/let_the_galaxy_burn.py` | **fait** |

### 4.d — Reste en VEILLE (à promouvoir seulement sur miss d'agreement)

> ⚠ **NON RE-CONFRONTÉ à cette passe, et c'est un DÉFAUT de la section, pas un choix** : aucune de
> ces 13 lignes ne porte de colonne « Fichiers », donc aucune ne peut être scopée par
> `git diff 2cef371..HEAD`. Les re-lire toutes coûterait plus cher que tout le reste de la passe
> réunie, et les ignorer laisse un angle mort — c'est exactement la forme de dette que ce document
> est censé supprimer ailleurs. **Action la moins chère** : à la prochaine promotion d'une de ces
> lignes vers §4.a/§4.b, lui poser son ancrage `fichier:ligne` au passage.

Vérifiés présents (à la passe précédente), sans symptôme actionnable aujourd'hui : résidus MV71 (`case-61bis` §6/§8/§9),
per-player 1180 (`case-31`), `ReachedSummonCap` (`case-38` §4 — branche `IsActive` sans caller
connu), `LordOfTempests` AddIce (`case-35` §4), `LivingMetal` swarm no-wake top-off (`case-203` §5),
les 2 résidus `move` (#17, nature RNG), arc arrière NON dégénéré du push (`case-push-distance` §5 —
sans objet pour un pousseur adjacent), trait `Unstoppable` 1042 (à câbler DANS la tranche
movement-stop #131/B4, sinon registered-but-dead), `#202` face DÉCISION Abraxas non confrontée
oracle, `#5` chantier `DslContext` live-state, chantier archi **DSL-effet** (`dsl-effect-nodes.md` —
migration des `execute_*` impératifs vers des arbres de nœuds ; c'est un chantier, pas un résidu).

### 4.e — HORS PÉRIMÈTRE de cet inventaire

- ~~**En cours de traitement par d'autres agents au moment de la rédaction**~~ — **les TROIS sont
  livrés** : le jet de block `Daemon_ExtraBlock` (`fda9142`, `case-221-daemon-extrablock-rng.md` ;
  `DaemonExtraBlockEffect` enregistré `effects/factory.py:299` + seed du trait 0x3fb l.572-574) ; le
  canal `OnToxicDamage` (1203) (`175f006` ; `TriggeredAbilityType.OnToxicDamageAbility = 1203`,
  émetteur `damage_ops/ability.py:430`, `triggers/dispatch/attack.py:207-218`) — **re-confronté depuis**
  au décompilé et au live : port conforme à `OnToxicDamageAbility$$CreateTrigger`/`$$CreateBehaviour`,
  résidu de GRANULARITÉ tranché (« série » = les coups sur UNE cible, cf. `case-1203` §5.1) et 2ᵉ porteur
  RANGED confronté (`case-1203` §5.2) ; le gate de PORTÉE (#241,
  `case-241-range-gate.md`). Ce qui reste à cet endroit de la cascade : la **ligne de vue**
  (`GetTilesObscuringTerrain`), et `GetValidTargets` (dont dépend `GetCasterNotAddedReason`).
- **Bloqués par une fenêtre d'atelier vide** (exigent rebuild + reinject, donc pas du RE) :
  **`UnitFlagsComponent` dans `combatSnapshot`** (seul survivant de la liste — vérifié : aucune
  occurrence dans `frida/hooks/**`), **plus O2** (drain ai-trace) et **O7** (corruption
  `combatSnapshot` × Machine).

  > ⚠ **Les QUATRE autres items de cette liste étaient DÉJÀ FAUX à la passe précédente.**
  > `d9d0008` (*#128 lot ATELIER VIDE*, **2026-07-26**, donc antérieur à `2cef371`) a livré :
  > `EffectComponent.IsActive` + option `includeInactive` (`rpc-decision.ts:50-53`),
  > le `StatModifierComponent` de l'entité-effet champ par champ (`frida/hooks/game/effects.ts:52-108`),
  > `ChildComponent.ParentId` dans `projectUnitsFull` (`projection.ts:289-306`), et
  > **`combatSnapshot.allUnits` + `statModSources.targetUnits` élargis à `EntityType.Machine`**
  > (`rpc-snapshot.ts:131` et `:367`, plus le champ `entityType` dans les deux charges utiles).
  > Cette dernière entrée est la plus coûteuse des quatre : sa version PÉRIMÉE est écrite en dur
  > dans le code et dans deux case-docs (cf. §5.5), et c'est **exactement elle qui a masqué N7**
  > — `_load_stats_and_effects` boucle sans filtrer `entityType` parce que la doc jurait que
  > `combatSnapshot` n'émettait que des `Unit`.
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

### 4.g — COMPTE NET des entrées OUVERTES après cette passe

| Section | Ouvertes | Détail |
|---|---|---|
| §4.a — symptôme MESURÉ | **6** | R1-b · R4 · R6 · R7 · **N8** · **R32** (neuf 2026-07-28, gate `IsCharging`) — (~~N7~~ et ~~N6~~ **FERMÉS**, #174) |
| §4.b — symptôme NOMMÉ | **11** | R12 · R13 · R15 · R17 · R19a · R25 · R26 · R27 · R30 (reformulé) · N1 · N2 |
| §4.c — outillage / harnais | **4** | O2 · O4 (b, c, d) · O5 · **O7** |
| **Total résidus NOMMÉS** | **21** | dont **6 relus au code cette passe**, **8 hors intersection**, **4 neufs (dont N7 déjà fermé)**, **1 reformulé** |
| §4.d — veille | 13 | **non re-confrontés** (aucune colonne Fichiers, cf. l'encadré du §4.d) |
| §4.f — NON CONFRONTABLES | 4 lots | hors compte : 29 actives npc/summon-env, 1192/1194, 4 overlays R15, `Impervious`, plus **N4** (candidat `fable-solver`) |

Gisements (re-dérivés du code au 2026-07-28, après #181) : **89** actives NO-OP au
total, **60** dispatchables (dont **15** en `[-D]`), **40** masques de ciblage manquants sur **91**
entrées de registre, **55** passifs à porteur confrontable.

> ⚠ Seule la ligne « masques de ciblage » a été re-dérivée par #181
> (`probe_181_targeting_gaps.py`) ; les trois autres viennent des audits antérieurs et **n'ont pas
> été re-jouées** — les re-dériver avant de s'en servir pour dispatcher.

**Mouvement de cette passe** : 27 ouvertes avant → **22** après. −5 fermetures (`R8`, `R24`, `O1` par
`3eee6c0` ; puis **`R5`** et **`R20`**, mergées PENDANT la passe — cf. l'encadré ci-dessous),
+3 entrées neuves (`N7`, `N8`, `O7`), 1 reformulation (`R30`). Les trois neuves ne sont pas des
régressions : ce sont des résidus qui **existaient et n'étaient pas inventoriés**, deux d'entre eux
parce qu'une affirmation périmée les masquait (§5.5).

> **`N7` ET `N6` ont été fermés PENDANT la vie de cette passe** (PR #155,
> `case-174-mow-level-index.md`) — d'où **20** au tableau ci-dessus.
>
> Le rayon d'action mesuré par ce cas est **bien plus large** que ce que l'entrée N7 annonçait :
> **14 tests** passent de rouge à vert, pas 4 — dont **5** dans `test_mow_targeting_predicate_live`
> et **2** dans `test_hailstrike_phase2_live`. Et `test_mow_caster_is_loaded_offline` **assertait
> déjà** le niveau (`sc.ctx.active_ability_level == ab["level"]`) : il était rouge sur `master`
> depuis `d9d0008` sans que personne ne l'ait vu.
>
> **`N6` était la MÊME cause, sous un autre nom.** L'entrée le suspectait à l'« étage perçage » et
> pointait `engine/runner/abilities/darkangels.py` ; en réalité son porteur est `darkaStormSpeeder`,
> une **MoW**, et ses bornes `[1688, 2532]` étaient calculées avec `minDmg`/`maxDmg` lus à
> l'**index 0**. Les deux tests sont verts après le seul correctif de `snapshot.py`, sans une ligne
> touchée dans `darkangels.py`. C'est le troisième « écart de magnitude inexpliqué » que ce bug
> unique produisait, après `EntropyCannons` (`off_delta=20` vs `live_delta=1631`, la « mesure B » de
> `case-162`) et les `nrOfTiles`/`nrOfRounds` — chacun inventorié séparément, avec un sous-système
> suspect différent. **Leçon : un écart de magnitude sur un porteur MoW doit faire suspecter le
> NIVEAU LU avant l'étage de calcul.**
>
> Enfin, le correctif n'est pas tout à fait « 1 ligne » : le `continue` seul aurait fait retomber les
> stats résolues de la MoW à 0 **et** perdu son `visual_id`/`traits` — `_load_machine_stats` consomme
> désormais la ligne Machine.

> **`R5` et `R20` ont été fermés PENDANT la rédaction de cette passe** (PR #151 et #152, mergées
> entre `bec119f` et le rebase). Deux conséquences, l'une méthodologique et l'autre à retenir :
> (a) ma re-reproduction de R5 à `bec119f` (1 failed / 2 passed, trace inchangée depuis 3 jours)
> était **juste au moment de la mesure** et **périmée deux heures plus tard** — le rebase avant PR
> n'est pas une formalité, c'est ce qui a évité de livrer un verdict faux ; re-joué après rebase :
> **3 passed** ; (b) **ni PR #151 ni PR #152 n'a mis CET inventaire à jour**, alors que les deux
> fermaient une de ses entrées nominatives. Un document qui n'est corrigé que par ses passes de
> re-confrontation ment structurellement entre deux passes — l'ajout d'une ligne d'inventaire dans
> la PR qui ferme un résidu coûte 30 secondes et supprime ce mensonge.

---

## 5. PÉRIMÉS — à sortir du backlog / de la roadmap

### 5.0 — Fermés PENDANT cette passe (`2cef371` → `fd1031e`, 49 commits / 19 merges)

| Résidu | Verdict | Commit | Preuve au code (relue à `bec119f`) |
|---|---|---|---|
| **R5** — `test_skitarii_played_by_generic_ai_pass` ROUGE | **FERMÉ** | `17c2d74` (PR #151) | Fermé APRÈS ma re-reproduction à `bec119f`, pendant la rédaction. Cause racine : le gate d'expansion `BasePathfinder$$NodesInNextLevel` → `WalkPathfinder$$IsValidContinuePathTile` (bit 0x1, `BlockEnteringUnitsTileEffect`) n'était pas porté ⇒ la flood-fill traversait les marécages et la passe IA choisissait une tuile ILLÉGALE. `case-r5-skitarii-turn.md`. Test re-joué APRÈS rebase : **3 passed**. 5 résidus fils ouverts (R5-a…R5-e) |
| **R20** — `SpawnReplica` ré-implémentait `PerformAIAttack` | **FERMÉ** | `fd1031e` (PR #152) | `fdc45c0` (de-fork vers le corps unique `PerformAIAbilityUnitBehaviour`), `027ed84` (**ForwardSpotter 1143 était routé sur le MAUVAIS constructeur** — trouvé en de-forkant), `0378ce3` (état final). `summon.py:275-276` porte le fork au passé. ⚠ **la PR n'a pas mis cet inventaire à jour** |
| **O1** — aucune garde AUTOMATISÉE de synchro build ↔ symboles ↔ ghidra-mcp | **FERMÉ** | `3eee6c0` | `scripts/python/symbols_sync.py` existe (189 l.) ; `scripts/hooks/session-start.ps1:26` l'invoque à CHAQUE `SessionStart` (`--quiet --ghidra-timeout 6`) et n'imprime que s'il proteste. Trois axes couverts, dont **ghidra-mcp ↔ tables** (le seul qui attrape « le serveur sert l'ANCIEN projet pendant que les tables sont du NOUVEAU »). Serveur éteint = **NON VÉRIFIÉ**, distinct d'un succès. Le défaut de `il2cpp_provenance` vise désormais `data/symbols/<HASH>/` — il visait des `data/il2cpp_*.tsv` SUPPRIMÉS, donc l'outil « fail-closed » était inerte et échouait sur « artefact absent », ce qui se lit comme une faute de chemin |
| **R8** — `--hp-target` remet l'armure à 0, tu par la doc | **FERMÉ** | `3eee6c0` | `runner.md:155` porte maintenant « **et met `Armor`/`FixedArmor` à 0** » + le piège de mesure chiffré (`adeptMorvenn` 2411 → 0, `necroWarden` 2008 → 0) ; `rl_duel.py:1970-1972` et `:1974-1975` le disent dans l'aide argparse. Le commit a trouvé un **troisième** support que la fiche R8 ignorait : `--hp-player` a le MÊME effet, également tu |
| **R24** — state-files pytest dans `data/` (VERSIONNÉ) | **FERMÉ** | `3eee6c0` | `tests/conftest.py:58-59` : `STATE_PREFIX = ROOT / "logs" / "_pytest_duel_state"` (+ `mkdir(parents=True)` l.60). L'override `TACTICUS_PYTEST_STATE_PREFIX` reste, le DÉFAUT a changé de camp |

**O1 / R8 / R24 par le MÊME commit** — une passe transverse de garde-fous « qui se revendiquaient
sans exister ». C'est le profil de tâche le moins cher de tout l'inventaire (§6 item 8) et il a
rendu 3 fermetures d'un coup. **R5 et R20** ont été mergés PENDANT cette passe, entre la mesure et
le rebase (cf. l'encadré du §4.g).

### 5.0bis — Les 10 fermetures de la passe précédente, RE-VÉRIFIÉES au code

Aucune n'est fausse. Preuve minimale relue à `bec119f` :

| Fermeture | Preuve au code |
|---|---|
| **R1** (prémisse réfutée + ordre de sweep porté) | `case-r1-origin-action-tile.md` ; `engine/ai/context.py::action_tiles_for` existe, `_sweep_origin_first` est devenu l'identité. ⚠ un vestige de la prémisse RÉFUTÉE survit ailleurs — cf. §5.5 |
| **R9** (Chronometron 1550) | `engine/entities/effects/loki/damage_reduction.py:88` `class ChronometronExtraDamageEffect` ; `effects/base.py:113` `times_applied: int = 1` ; `triggers/loki/chronometron.py` (`On(9)`, retrait de l'instance) |
| **R14** (face DÉCISION des MoW) | `engine/ai/tactic.py:57` `class DefaultMachineTactic`, docstring citant `AiQuery$$GetUnitTacticForUnit` → `EntityExtensions$$IsMachine` |
| **R16** (stat-mods EAGER du seed revertés) | `effects/__init__.py:558` `def effect_stat_modifications` (« point de verite UNIQUE des deux formes ») ; `unit_context.py:193` seed en DEUX passes |
| **R28** (`PickRandomly`, ordre SOURCE) | `engine/dsl/base.py:234-247` (triple boucle CUBE d'`IterateSurroundingTiles`, et **pourquoi** l'ordre compte : `ElementAt(idx)`) ; `selectors/units.py:566,581` |
| **N5** (chaîne `&` après un `AddEffect` refusé) | `operations/effects.py:144-149` : « L'ABANDON S'ARRÊTE À CETTE OPÉRATION — il ne remonte NI à l'itération du sélecteur-cible NI [au combinateur] » ; garde live `test_chain_after_refused_addeffect_live.py` (15 ko) |
| **O3** (dynamique des effets de tuile) | `entities/effects_state.py:97-133` : décrément CLAMPÉ (`RemoveOneTurn`) **et** retrait à 0 (`ShouldBeRemoved`) |
| **O4(a)** (`MaybeTrigger`) | `triggers/loki/let_the_galaxy_burn.py:102` `from …entities.triggers import MaybeTrigger`, câblé dans l'arbre l.29 |
| **O6** (ordre RNG de `LetTheGalaxyBurn`) | même fichier, l.85-91 : `Maybe` AVANT `!HasTileStatusEffect`, primitive `NextBool(chance)` = `next_internal(1,100) <= chance` (borne **99**) |
| **convergence `RULE_*`** | `abilities/targeting.py:163` `from .targeting_rule import TargetingRule as TR` — et **plus aucune** constante `RULE_*` locale. Gardé par 3 tests d'AST dans `test_ability_registry_ratchet.py` (déclaration hors module généré, littéral brut dans `options.has(...)`, dérive du module généré vs dump). **La justification « le dump il2cpp tronque l'enum à 32 bits » a disparu du fichier** — c'était l'une des affirmations périmées signalées |

**Garde re-jouée** : `python -m pytest tests/engine/runner/test_ability_registry_ratchet.py` → **8 passed**
(offline pur, 18 s). Elle confirme d'un coup `ABILITY_ATTACK_TYPE` = **81/81**, `TARGETING_OPTIONS` =
**28/81** avec les **53** exemptés nommés, `TargetingRange` sur les 28, et la source unique de ciblage.

### 5.1 — Fermés à l'inventaire précédent (`fc23f1e` → `e972c99`, 26 commits)

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
| `backlog.md` #217 (note) | « ⚠ `audit_kit_coverage.py` SOUS-COMPTE ce gisement (2 registres de décision lus sur 3) » | **FAUX** — corrigé par `8e8518e` (= R23, §5.1). L'audit lit les 3 registres |
| `backlog.md:140` et `:645`, `case-118-seeded-statmod-revert.md:185` | « stat-mods EAGER (`applied_stat_mods`) présents AU SEED : appliqués mais **non revertables** » | **FAUX** — R16 fermé (§5.1). `case-thrillseekers.md:205` le dit déjà (« ~~non revertable~~ **FERMÉ** »), les trois autres supports non |
| `CLAUDE.md`, §« Entrer au registre SANS son masque de ciblage » | « `ABILITY_CLASSES` = **76** entrées, **1 seule** (`WaaaghAbility`, 1058) porte son masque. Le compte est passé de 60 à **75** manquants » | **81 entrées, 28 avec masque, 53 manquants** — et la tendance s'est INVERSÉE. Le paragraphe qui suit (« le SEUL gisement que notre propre cadence aggrave ») n'est plus vrai non plus depuis le cliquet `test_ability_registry_ratchet.py` |

**Cadence mesurée sur 24 h** : **4 résidus fermés** (R19b, R21, R23, N3-câblage) + **2 entrées
`[fable]` révélées déjà fausses** + **5 abilities** sorties du gisement 1 + **22 masques de ciblage**
+ **8 passifs**. Un backlog relu à J+1 ment déjà sur ses chiffres ; à J+3 il ment sur ses verdicts.

> **Ajout PR #155 (#174)** — les affirmations périmées de `snapshot.py::_load_machine_stats`,
> `_machine_ability_state`, `blacklegion.py`, `case-mow-offboard-cast.md` §8 et
> `case-mow-targeting-predicates.md` sont **corrigées à la source**. Deux enseignements de plus :
> - **une attribution fausse se propage aussi vite qu'une affirmation fausse.** Le commentaire du
>   hook dit « Machine INCLUSE (**#93**) » ; #93 est la tâche *SpiritLeech*, le filtre vient de
>   `d9d0008` (#128). `case-162` a recopié « #93 », puis la 1ʳᵉ rédaction de `case-174` aussi —
>   corrigé au rebase, sur arbitrage du conflit avec cette passe-ci. Trancher par
>   `git log -S "EntityType.Machine" -- frida/hooks/features/ai-step/rpc-snapshot.ts`, jamais par le
>   numéro écrit dans un commentaire.
> - **un diagnostic inventorié est une hypothèse, pas un fait** : N6 pointait l'« étage perçage » et
>   `darkangels.py` ; la cause était le niveau de la MoW. Un écart de magnitude sur un porteur MoW
>   doit faire suspecter le **niveau lu** avant l'étage de calcul.

### 5.5 — AFFIRMATIONS périmées écrites EN DUR (code et docs) — la classe de défaut la plus chère

Ces phrases ne cassent aucun test. Elles sont **lues, crues, et propagées** — et chacune a survécu à
plusieurs relectures du fichier qui la porte. Elles sont listées ici pour être corrigées **à la source**,
pas seulement contredites ici.

| Support | Ce qu'il affirme | Ce qui est vrai | Coût déjà payé |
|---|---|---|---|
| `engine/runner/snapshot.py::_load_machine_stats` (docstring, l.302-314) | « `combatSnapshot` n'expose QUE `EntityType.Unit` (son `allUnits` filtre `ty === EntityType.Unit`), donc **aucune stat RÉSOLUE de MoW n'est lisible par RPC** » + « RÉSIDU DOCUMENTÉ : … tant que `combatSnapshot`/`statModSources` filtrent `EntityType.Unit` (changement `frida/hooks` requis) » | `rpc-snapshot.ts:131` = `if (ty !== EntityType.Unit && ty !== EntityType.Machine) return;` et `:367` `isCombatant = isUnit \|\| ty === EntityType.Machine`. **Les deux RPC émettent les Machines depuis `d9d0008` (2026-07-26).** Le changement `frida/hooks` réclamé EST fait | **N7** — c'est cette phrase qui explique que `_load_stats_and_effects` boucle sans filtrer `entityType`. La phrase a simplement DÉMÉNAGÉ (`case-162` l'avait pointée sur `_load_machines`) au lieu d'être corrigée |
| `docs/rl/case-mow-offboard-cast.md:55` et **:188-195** | « combatSnapshot ids = […] ← `EntityType.Unit` only » ; « **Spec du changement `frida/hooks` requis** (non fait ici : rebuild+reinject interdits) : élargir le filtre de `rpc-snapshot.ts` à `EntityType.Machine` … et idem pour les `targetUnits` de `statModSources` » | idem — la spec est **implémentée**, mot pour mot, depuis `d9d0008` | fait porter un résidu FANTÔME au §4.e pendant deux passes d'inventaire |
| `docs/rl/case-172-mow-abilities-conditional.md:104` | « **combatSnapshot reste `EntityType.Unit`-only** → stats résolues de MoW non captables » | idem | idem |
| `engine/ai/utilities.py:57-58` (docstring `DislikeStartingTilesUtility`, écrite le 2026-07-03) | « couple au trou#6 R1 : **origine évaluée en dernier côté natif** » | **R1 a réfuté exactement cela** (`284ca69`) : le slot `IBattleQuery+0xe` est `BattleQuery$$GetCurrentAndMovablePositionsFor`, dont l'`OrderedSet` est SEEDÉ avec la position courante ⇒ **l'origine est PREMIÈRE**. 10 contre-exemples live | non chiffré ; le raisonnement de tie-breaker construit dessus est à re-dériver |
| `docs/rl/case-128-tile-elevation-utility.md:21-23` (le RÉSUMÉ du document) | « Le port sur-génère des candidats : il score l'action depuis la tuile d'ORIGINE du caster, **que l'énumération native ne contient pas** » | **le §5 du MÊME document porte déjà l'encadré « SECTION RÉFUTÉE »** — le résumé de tête, lui, n'a pas été mis à jour. Un lecteur qui s'arrête au TL;DR emporte la prémisse morte | c'est la prémisse qui a produit R1, dispatché sur une cause fausse |
| `CLAUDE.md` §masque de ciblage | 76 / 1 / 60→75 (cf. §5.4) | 81 / 28 / 53 | un brief dérivé du CLAUDE.md annoncerait « 75 masques à poser » |

**Le motif commun** : une phrase VRAIE le jour où elle est écrite, dans un fichier que personne ne
relit en entier, et qui devient FAUSSE par un commit qui touche un AUTRE fichier. Aucune des six
n'aurait été trouvée par un test. La seule parade qui a fonctionné ici est de les **confronter à
leur source** (le `.ts` du hook, le décompilé, le `git log -S`) au lieu de les croire.

---

## 6. Ordre de dispatch conseillé (valeur décroissante)

0. ~~**N7**~~ — **FERMÉ (PR #155, `case-174`)**. Rayon d'action réel : **14 tests** rouge→vert, pas 4.
1. ~~**N6 — le dernier test de garde ROUGE**~~ — **FERMÉ par le MÊME correctif (PR #155)**, sans une
   ligne touchée dans `darkangels.py`. Le diagnostic inventorié était faux : le symptôme chiffré
   (live 2700 vs port [1688, 2532]) n'était pas un défaut de l'**étage perçage**, c'était le porteur
   `darkaStormSpeeder` — une **MoW** — dont `minDmg`/`maxDmg` étaient lus à l'**index 0**. (~~R5~~,
   son jumeau, a été **FERMÉ pendant cette passe** — PR #151 : cause racine = le gate d'expansion
   `BlockEnteringUnits` non porté, la flood-fill traversait les marécages. Le test avait raison, et
   l'indice `ability: 17` était une fausse piste.)
2. ~~**R1 tuile d'origine**~~ — **FERMÉ, prémisse RÉFUTÉE** (`case-r1-origin-action-tile.md`). La
   cause n'était PAS `state_bridge.py:318` (l'origine EST candidate côté natif : slot `IBattleQuery`+0xe
   = `BattleQuery$$GetCurrentAndMovablePositionsFor`, `OrderedSet` seedé avec la position courante) mais
   l'**ORDRE** du sweep — porté, +1 `stay` sur 2 couples, 0 régression sur 5. **Reste R1-b** : l'ordre
   RELATIF des tuiles de move (`GetMovablePositionsFromTiles` + `ExceptWith`), dont l'imposition est
   MESURÉE régressive (`C4_09`/999 pos 15/20 -> 14/20) — symptôme chiffré disponible.
3. **Gisement 2 (§2), 15 items** — un agent par ability. Prioriser 1137 MurderousSwing, dont la face
   décision est déjà mesurée : l'oracle existe.
4. **R4 resolve slot-8**, ~~R9 Chronometron~~ (**CLOS**, cf. §R9-clos), ~~N1 ArcaneShield~~ (**CLOS**,
   cf. `case-n1-arcane-shield-vector.md`), **N2**, ~~N5~~ (**RÉFUTÉ**) — symptômes mesurés ou cause
   nommée, taille contenue. ⚠ **ne pas dispatcher R4 et N2 en même temps** : la scission #169 les a
   séparés dans `damage_ops/` (`normal_like.py` vs `ability.py`) mais ils **partagent toujours
   `damage_hits.py`**, qui n'a pas été scindé.
5. **Gisement 4 (§3bis), 55 passifs confrontables** — le plus gros volume, invisible des deux audits
   historiques. À traiter en parallèle du gisement 1 : il ne touche PAS `handler.py`.
6. **Gisement 3 (§3), 53 masques** — par module, en suivant la carte du §3 ; ou en règle de
   non-régression sur chaque nouveau port. Les gros lots restants : `splash` (6), `strike` (6),
   `blacklegion` (5), `deathguard` (5), `summon` (5), `tau` (5).
7. **Gisement 1 (§1), 47 items restants** (62 − les 15 du gisement 2) — piocher par faction ; les 11
   de la voie `catalog_inject` n'ont plus d'obstacle de harnais.
8. ~~**O1 garde de synchro**, **R24**, **R8**~~ **FERMÉS** en un seul commit (`3eee6c0`, §5.0) — la
   confirmation que cette catégorie « dette d'outillage » est la moins chère du document : 3
   fermetures pour une passe. **Reste `R25`** (3 constantes de gameplay figées + 1 accesseur
   générique à ajouter à `_config_oracle.py`), et **N8** (seed `turn_counts` + compteur PER-UNITÉ).
9. ~~**R14 face décision MoW**~~ **FERMÉ** (`case-r14-mow-decision.md`) — le débloqueur nommé par R15
   est levé ; ce qui reste pour les overlays MoW est le PORT de leur feuille de décision (1187 est la
   seule des 16 abilities MoW à en avoir une). ~~**R30 multi-hex**~~ : le SUBSTRAT est **porté et
   confronté live** (`94b7118`) ; il ne reste que `DutyEternal` 1158 à faire entrer au registre
   (1 ability) et 5 résidus nommés dont 3 sont inexerçables dans ce build.
   (~~O3 dynamique des effets de tuile~~ : **fait**, `case-o3-tile-effect-dynamics.md`.)
10. ~~**O4 (a) `MaybeTrigger`**~~ **FAIT** (`case-o4a-maybe-trigger-rng.md`) — le comptage RNG d'un gate
    `Maybe`/`chance` est désormais confrontable, et O6 est fermé avec. Ce que la mesure avait
    **découvert** et laissé ouvert est désormais une entrée à part entière : **N8** (seed de
    `state.turn_counts` + `OwnerHasFinishedMinTurns` PER-UNITÉ).

**Ne PAS dispatcher `N4`** en `[opus]` : collapse assumé que le décompilé ne tranche pas — candidat
`fable-solver`, et sans urgence (comportement live-correct sur 4 porteurs).
**Ne PAS dispatcher O2 ni O7** tant que l'atelier n'est pas vide (rebuild + reinject). O7 est le plus
urgent des deux : il **corrompt silencieusement** tout runner portant une MoW, et la parade actuelle
(runner jumeau) est un contournement de test, pas un correctif.

---

## 7. Collisions entre agents concurrents

| Fichier | Qui le touche | Risque |
|---|---|---|
| `engine/runner/abilities/handler.py` | **tout** port d'ability (gisements 1 et 2) | **ÉLEVÉ** — conflit textuel garanti si 2 agents portent en parallèle. Trivial (2 lignes), mais à résoudre par l'auteur au rebase |
| `engine/runner/operations/damage_ops/` (**PACKAGE depuis #169**) | R4 + R6 + R7 (`normal_like.py`), N2 (`ability.py`), R19a (`_channel.py`) — R9 **fermé** | **RETOMBÉ À FAIBLE** — la scission a séparé les 5 résidus en 3 modules disjoints : `normal_like.py` (R4/R6/R7, à sérialiser entre eux), `ability.py` (N2), `_channel.py` (R19a). N2 et R4 peuvent désormais partir **ensemble**, ce que l'inventaire interdisait |
| `engine/runner/snapshot.py` | ~~N7~~ (**FERMÉ**, PR #155), **N8** (seed `turn_counts`), R30 (`_load_feet`, posé) | **FAIBLE** — N8 reste seul sur ce fichier. ⚠ #155 a modifié `_load_stats_and_effects` ET `_load_machine_stats` : re-baser avant de porter N8 |
| `engine/runner/operations/damage_hits.py` | R4, N2, R26 | **ÉLEVÉ** — sérialiser |
| `engine/runner/abilities/behaviours/summon.py` | ~~R20~~ (**FERMÉ**, PR #152) | — |
| `engine/ai/state_bridge.py` | ~~R1~~ (FERMÉ), R15 | FAIBLE — R1 a touché `_plans_for_unit` (ordre) + `build_from_state` (champ `action_tiles`). (R14 est FERMÉ et n'a PAS touché cette fonction : le chemin MoW vit dans `engine/ai/{tactic,context}.py`.) |
| `engine/ai/{context,action_generators}.py`, `engine/playbook/noncomparable/_base.py` | ~~R1~~ (FERMÉ), R1-b | MOYEN — R1-b re-touchera le sweep de position de `_best_attack` |
| `engine/runner/abilities/behaviours/combat.py` | R19a | MOYEN (R28 fermé) |
| `engine/runner/operations/triggers/dispatch/` (**PACKAGE depuis #169**) | R12 (`registry.py` + `move_death.py`), R13 (`registry.py`), N8 (`turn.py`), tout vecteur d'event neuf | **FAIBLE** — même effet que ci-dessus : R12/R13 et N8 ne se croisent plus |
| `engine/runner/operations/effects.py`, `engine/entities/effects/factory.py` | N5, R9 (R16 **fermé**) | MOYEN |
| `engine/runner/abilities/<module>.py` | gisement 3 (1 lot par module), 1 port par faction | FAIBLE — deux modules différents ne se croisent pas |
| `engine/entities/effect_type.py` | tout effet neuf | FAIBLE (ajouts en fin de liste) |
| `docs/rl/combat-ability-coverage.md`, `kit-coverage.md`, `passive-ability-coverage.md` | régénérés par les audits | **ne jamais fusionner un conflit** : régénérer (`audit_*.py`) |
