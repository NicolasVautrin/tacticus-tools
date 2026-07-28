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
> n'est PAS `HasMoved`**.
>
> **case-r32 (2026-07-28)** : les consommateurs de ce socle sont RETROFITÉS. Le canal extra-dégât
> gatait ce nœud par le proxy `has_moved`, qui **sur-accorde de +599/coup** sur `astraBullgryn`
> (mesuré, COMBAT *et* PRÉDICTION). Le prédicat vit désormais en un FOYER UNIQUE,
> `engine/battle_query.py::is_charging`, appelé par les deux faces. Le lot concerné est
> `AvalancheOfMuscle` (1025) + `FeederTendrils` (1197) — **pas** `SmashaEad`, dont le décompilé ne
> porte AUCUN nœud `IsCharging` (les fiches antérieures, y compris ce paragraphe, se trompaient).
> `BlackRage_ExtraDamage` (1343) reste ouvert pour une raison SÉPARÉE (entrée `N10`) : **DEUX**
> effets sont recâblés, pas trois.
>
> **case-ischarging-hits (2026-07-28)** : les xrefs sont RE-ÉNUMÉRÉES à la source — **16 CALL** (+2 DATA), pas
> « 12 autres », et **8 canaux** distincts, pas 4. Le tas « déjà porté, gate faux ou absent » est
> **VIDE** : les 11 autres consommateurs ne sont portés sur AUCUN canal. Le canal **COUPS** entre
> par `SagaOfTheWarriorBorn_Owner` (1223, `spaceBlackmane`, **+3 coups en charge**) ; il reste
> `N16` (4 consommateurs confrontables) et `N15` (branche charge de `FeederTendrils_NormalAttack`).
> Deux items sortent en **NON PERTINENTS** (§4.f) : `ObeisanceGenerators` (aucun porteur parmi les
> 669 unités) et `SabreOfSacrifice` (npc + relique).
>
> **case-ischarging-crit-channel (2026-07-28)** : `N14` **FERMÉ**. Le canal CRIT n'était pas
> structurellement aveugle — `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage`
> passe **l'attaquant ET la cible** à `GetCritDamageBonusFromEffects`, qui bâtit lui-même son
> `AbilityEntities` : c'était le PORT qui perdait le contexte. Le canal est instrumenté en UN point
> (`AttackDamageOperation._crit_params`) et la face CRIT de 1223 est portée et validée live.
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

> **Le compte qui fait foi est celui de §2.1**, re-dérivé du CODE par
> `python scripts/python/probe_decision_noop_gap.py` — pas celui de cette ligne ni de `kit-coverage.md`.
> Au 2026-07-28, après le port de `1137` : **10 items réels restants**.

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

### 2.1 — Dérivation autonome et inventaire CLASSÉ (case-decision-noop, 2026-07-28)

> **Re-dérivé du code au commit `60e2e37`**, sans reprendre aucun chiffre de ce document ni du
> backlog. Script de dérivation : `ABILITY_CLASSES` (`engine/runner/abilities/handler.py`) soustrait
> de l'union des **TROIS** registres de décision — `engine.playbook.base.REGISTRY` (Comparable, 7),
> `engine.playbook.noncomparable.PLAYBOOKS` (NonComparable, 35) et
> `engine.entities.abilities.active_ability._SPECIAL_ABILITY_CLASSES` (sous-classes
> `AActiveAbility` à formule de coups/AoE propre, 8 — consommées par le playbook GÉNÉRIQUE).
>
> ```
> exec (ABILITY_CLASSES) = 91 | decision (union des 3 registres) = 45
> DECIDENT sans EXECUTER = 15 -> [28, 1038, 1039, 1050, 1090, 1100, 1117, 1121,
>                                 1129, 1137, 1171, 1177, 1183, 1192, 1194]
> ```
>
> ⚠ **Croiser SEULEMENT `REGISTRY` + `PLAYBOOKS` rend 13 et manque 1137 / 1171** : leur face
> décision vit dans le 3ᵉ registre. C'est l'erreur qu'a commise la première passe de cette
> dérivation ; la table §2 ci-dessus, elle, les avait bien. **Toujours les trois registres.**
>
> **RE-DÉRIVATION du 2026-07-28 (case-decision-noop, après le port de `1137`)** — le script est
> désormais AU DÉPÔT : `python scripts/python/probe_decision_noop_gap.py` (il refait le croisement
> des trois registres et signale ce que deux registres rateraient). Ne PAS décrémenter ce compte à
> la main : le re-dériver.
>
> ```
> exec (ABILITY_CLASSES) = 93 | decision (union des 3 registres) = 49
> DECIDENT sans EXECUTER = 13 -> [28, 1038, 1039, 1050, 1090, 1100, 1117, 1121,
>                                 1129, 1177, 1183, 1192, 1194]
> ```
>
> **10 items réels restants** (13 bruts − `28 Repair` dormant − `1192`/`1194` npc-only).
>
> **Sur les 15 de la dérivation initiale, 12 étaient des items réels et confrontables** :
> * `28 Repair` est un **TAG de playbook générique, pas une ability** — `RepairPlaybook.ability_id =
>   ActiveAbilityType.Repair`, mais **aucune** entrée `abilities` du gameconfig ne s'appelle
>   `Repair` (les repairs concrets ont leur propre id, ex. `NanoscarabRepairProtocols`). Les deux
>   registres sont lookupés par id CONCRET (`REGISTRY.get(ability_id)`) ⇒ le playbook 28 est
>   **dormant par construction**, exactement comme le tag `NormalAttack (17)`. Hors périmètre.
> * `1192 NovaBoost` / `1194 NovaShield` : porteur unique `tauBossRiptide`, **npc**. Non pertinents
>   (pas « bloqués »).

**Écart observable commun à tous** : `AbilityHandler.visit_ActiveAbilityMessage` ne trouve pas la
classe, pose `unported.add(id)`, `last["ported"] = False`, **exécute quand même les flags de tour**
(`On(0xc)` → `AddFlagsAfterAbilityExecution` → `On(0xe)`) et **retourne sans aucune behaviour**.
Le cast est donc ACCEPTÉ (il consomme le tour) et ne mute RIEN. C'est ce qui rend le défaut
invisible : `ok=True`, tour consommé, zéro dégât, zéro effet, zéro erreur.

**Ventilation des porteurs et gate de confrontabilité** (`rl_duel build --list-pool`, rank 17,
97 unités + 8 MoW) — les 12 porteurs `lineup` sont **tous** dans le pool ; **aucun MoW, aucun
summon** dans ce gisement :

| # | id | ability | faction | porteur HERO (pool) | npc | MoW / summon | taille décompilé `ExecuteBehaviour` |
|---|---|---|---|---|---|---|---|
| ~~1~~ | ~~1171~~ | ~~DakkaDakkaDakka~~ | Orks | `orksKillaKan` « Snappawrecka » ✅ | 3 | — | **FERMÉ** (case-decision-noop) |
| ~~2~~ | ~~1137~~ | ~~MurderousSwing~~ | WorldEaters | `worldExecutions` « Tarvakh » ✅ | 1 | — | **FERMÉ** (case-decision-noop) |
| 3 | 1129 | BloodyFury | WorldEaters | `worldTerminator` « Wrask » ✅ | 1 | — | ~864 o + 4 helpers |
| 4 | 1183 | VexillaMagnifica | Custodes | `custoVexilusPraetor` « Aesoth » ✅ | 0 | — | ~1 120 o |
| 5 | 1177 | LightOfSanguinius | BloodAngels | `bloodDante` « Dante » ✅ | 0 | — | ~1 470 o + `GetDamage` |
| 6 | 1050 | HolyDuel | BlackTemplars | `templChampion` « Jaeger » ✅ | 4 | — | ~704 o |
| 7 | 1121 | ItItches | Tyranids | `tyranParasite` ✅ | 6 | — | ~2 060 o + 3 helpers |
| 8 | 1090 | GrapnelLauncher | SpaceWolves | `spaceHound` « Tjark » ✅ | 0 | — | ~1 740 o |
| 9 | 1039 | RitesOfRestoration | Sisterhood | `adeptHospitaller` « Isabella » ✅ | 3 | — | ~976 o + **6 helpers revive** |
| 10 | 1100 | SorcerousFacade | ThousandSons | `thousTzaangor` « Yazaghor » ✅ | 4 | — | ~928 o + `GetTarget` |
| 11 | 1038 | FoulInfusion | DeathGuard | `deathPutrifier` « Pestillian » ✅ | 3 | — | ~880 o |
| 12 | 1117 | DefendTheDivineWork | AdeptusMechanicus | `admecManipulus` « Actus » ✅ | 5 | — | ~752 o + `GetAdjacentFriends` |
| — | 1192 | NovaBoost | Tau | **aucun** | `tauBossRiptide` | — | **NON PERTINENT** |
| — | 1194 | NovaShield | Tau | **aucun** | `tauBossRiptide` | — | **NON PERTINENT** |

> La taille est le delta d'adresse entre `…$$ExecuteBehaviour` et le symbole suivant de la même
> classe — un **proxy** de volume, pas une mesure de difficulté. Les helpers comptent davantage :
> `RitesOfRestoration` est petit en corps mais porte six helpers de revive.

**Écart observable et classement (impact décroissant)** — l'ordre suit le dégât/état NON produit
par cast, pondéré par le caractère INCONDITIONNEL de cet écart :

| # | id | ce que le natif fait, que le port ne fait pas | socle déjà porté ? |
|---|---|---|---|
| 1 | 1171 | **6 coups garantis** (jusqu'à 16) × 1455-1819 Projectile pierce 15 ≈ **9 800 PV non infligés par cast**, sans condition ; puis report des coups gaspillés sur des ennemis tirés ≤3 hex ; **et** le caster ne perd pas ses 15 % de PV **max** ⇒ l'action est *gratuite* offline (double faussage : gain absent **et** coût absent) | oui — `ChainLeftOverHitsAttackDamage` (1006), `SubtractHealthPercent` (1131) |
| ~~2~~ | ~~1137~~ | ~~1 coup Piercing 80 sur **TOUS** les ennemis adjacents (+extraDmg si un seul est touché)~~ | **FERMÉ** — écart MESURÉ avant le port : **7 906 PV non infligés** sur un seul adjacent, **11 662** sur deux |
| 3 | 1129 | 1 coup Chain ≈ 2 800, **+1 coup par attaque reçue dans la bataille** (cap 8) + report des coups gaspillés | oui — `ChainLeftOverHitsAttackDamage` (1006). ⚠ **dépendance** : `TotalTimesAttacked` (compteur de BATAILLE, natif @+0x34) n'est pas entretenu offline — `UnitComponent.times_attacked_this_turn` est remis à 0 à chaque tour (`reset_times_attacked`) et n'est donc PAS le même compteur. Sans lui le port rend le coup de base |
| 4 | 1183 | ≈ 3 640 Physical sur la cible **et** un second ennemi adjacent, `Stunned` 1 round sur les deux, `-66 %` dégâts subis sur le caster 1 round ; cooldown 2 rounds | partiellement — pose d'effet + splash |
| 5 | 1177 | `Infiltrate` self + **CHARGE** vers un hex libre adjacent ≤5 + 5× Melta pierce 75 ≈ 3 800 + debuff -30 % dégâts sur la cible et son ring-1 (doublé contre les alliés ≤50 % PV) | oui — charge (1025/1153), pose d'effet |
| 6 | 1050 | `Taunt` sur un ennemi adjacent + **attaque normale immédiate** + 2 stat-mods conditionnés au Taunt (+582 infligés / −364 subis) + Taunt réciproque **sans expiration** | partiellement — attaque normale libre (1029/1163) |
| 7 | 1121 | `Suppress` + **push 1 hex** de la cible et des ennemis adjacents aux deux + destruction des steppables + **summon d'un Ripper Swarm par hex libéré** (attaque à l'apparition) + le caster peut re-bouger | partiellement — push (1004), spawn (1112/1166) |
| 8 | 1090 | 1× Physical ≈ 2 360 range 3 + **PULL** de la cible d'1 hex vers le caster (franchit l'élévation, pas l'infranchissable) + **le caster occupe l'hex libéré** | non — le pull et le move-into-vacated-hex sont neufs |
| 9 | 1039 | heal 2 183 self + adjacents (non-Mechanical) + **résurrection** de 1 héros Imperial et jusqu'à 2 summons Imperial morts, sur hexes libres adjacents, à 1 819 PV, inactifs ce tour | oui — `ReviveEffect` / `ReviveUnitOperation` (#66) |
| 10 | 1100 | buff psychic mutuel (caster + Psyker allié ciblé, +1× Psychic pierce 100 sur leurs attaques normales) + attaque normale sur l'ennemi le plus proche + **échange de positions** avec le Psyker | partiellement — cf. `case-171` (l'interaction attaque normale est déjà RE côté décision) |
| 11 | 1038 | buff « +1× 2 037 Toxic sur les attaques normales » au caster et à tous les alliés Chaos sous son aura Contagion, 2 rounds + **attaque normale immédiate** sur un ennemi adjacent tiré au hasard | partiellement — pose d'effet d'aura, attaque normale libre |
| 12 | 1117 | repair 4 365 PV sur le caster et tous les alliés adjacents | oui — **clone structurel** de `CombatRestoratives` (1002) et `RevitalizingMalignancy` (1037) |

**PORTÉ ET FERMÉ par ce cas : #1, `1171 DakkaDakkaDakka`.** Face COMBAT dans
`engine/runner/abilities/orks.py` (`DakkaDakkaDakkaAbility`), entrée au registre **avec ses deux
littéraux** (`TARGETING_OPTIONS` = preset `TargetingOptions` statique `+0x140` → `0x4002` +
`RANGE_FROM_CONFIG` + `forceMeleeTarget=True`, le MÊME que 1006/1206 ; `ABILITY_ATTACK_TYPE` = 0
`DirectTargetAttack`, littéral du `AActiveAbility..ctor`). Garde live :
`tests/engine/runner/test_dakka_dakka_dakka_live.py` (4 tests). ROUGE mesuré AVANT le port, sur le
même montage : `ported=False`, `flags={ability_used_flag: True, turn_finished: True}` (le cast est
ACCEPTÉ et consomme le tour) et **cible 500000 → 500000, caster 9037 → 9037** — zéro mutation.

> ### ~~⚠ TROUVÉ EN CHEMIN : `GetStuckIn` est gaté par un proxy **Chebyshev** là où le natif lit
> une distance **hex**~~ — **FERMÉ** (`case-mindistance-metric.md`)
>
> `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger` =
> `On(8) & IsOdd & OwnerIsCaster & !(MinDistance > 2)`. **Verdict tranché au décompilé** :
> `IdunBattleLogic.Entities.DSLFactory$$MinDistance` construit
> `IdunBattle.Entities.Formulas.MinDistanceFormula`, dont `Calculate` prend le `Min` sur les paires
> de `IdunBattle.Entities.Components.PositionComponent$$Distance` =
> `IdunBattle.Utils.Hex.AxialCoordinate$$ToCubeCoordinate` ×2 puis
> `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` = `Max(|dx|,|dy|,|dz|)` — **distance HEX pure,
> aucun pathfinding**. La glose « pathfinding » venait du natif HOMONYME
> `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` (utilité IA de
> MOUVEMENT), qui, lui, demande bien une route au pathfinding et en lit la longueur.
>
> **Mesure de découverte** (`scripts/python/probe_ddd_1171_getstuckin.py`, trois régimes) :
>
> | dist demandée | caster | cible | hex | cheby | gate porté | gate natif | préfixe commun |
> |---|---|---|---|---|---|---|---|
> | 2 | (1,0) | (0,1) | 2 | 1 | ACTIF (30) | ACTIF | **6 / 6** |
> | 3 | (1,0) | (0,2) | **3** | **2** | **ACTIF (30)** | **INACTIF** | **2 / 6** |
> | 4 | (1,0) | (0,3) | 4 | 3 | INACTIF | INACTIF | (hors portée) |
>
> **Ampleur, re-dérivée** (`probe_min_distance_metric.py --stage offline`) : `hex >= cheby`
> **toujours** (0 violation sur un balayage exhaustif 24×24, écart jusqu'à 12) ⇒ le proxy
> SOUS-ESTIME, donc sur `!(MinDistance > 2)` il **OUVRE ce que le natif FERME** — dégradation
> PERMISSIVE. Ce n'était pas un cas de coin : sur MC1_67, **46,6 %** des paires de tuiles jouables
> ont une distance différente et **5,82 %** font diverger le gate `<= 2`. Les 12 patrons
> discriminants dépendent de la **parité de la colonne de départ** (asymétrie odd-q).
>
> **Ce n'était ni un défaut du port 1171 ni un défaut de la PR #177.** #177
> (`EvaluateAfterHitTriggers` inconditionnel, aucun gate de famille) a **raison** ; elle a seulement
> rendu le défaut OBSERVABLE — avant elle le port ne roulait jamais ce `Maybe` sur une attaque
> d'ability, donc aucun des deux côtés n'en tirait et l'égalité tenait **par compensation**.
>
> **Corrigé sur les DEUX faces** — `entities.traits.combat.min_distance` (`hexgeo.distance`) est
> désormais le mirror unique, consommé par `getstuckin_combat_chance` (COMBAT) et
> `GetStuckInTrait.as_attacker_bonus_hits` (PRÉDICTION). `test_dakka_dakka_dakka_live.py` mesure
> maintenant aux **deux** distances (`GETSTUCKIN_DISTS = (2, 3)`), la 3 étant précisément la bande
> qui divergeait — et elle est DISCRIMINANTE (vue rouge sous mutation).
>
> **Piste « min sur les EMPREINTES » (cf. `are_entities_adjacent` / #R30) : RÉFUTÉE au décompilé
> pour le nœud DSL.** `MinDistanceFormula$$Calculate` fait `GetComponent<PositionComponent>` sur
> chaque élément rendu par les sélecteurs et n'appelle **jamais** `EntityExtensions$$IterateTiles`
> ni `GetTiles` — alors que les deux natifs qui, eux, veulent l'empreinte les appellent
> explicitement (`MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy`,
> `BattleQuery$$AreEntitiesAdjacent` → `MovementUtil$$AreTilesAdjacent(GetTiles(a), GetTiles(b))`).
> Le `Min` porte donc sur le **produit cartésien des deux sélecteurs** : l'empreinte n'entre en jeu
> que si le sélecteur est un sélecteur de TUILES (`CasterTiles@0x170`, cf. `bloodangels.py`), et le
> trigger `GetStuckIn` passe `owner@0x160` / `target@0x178` = des UNITÉS ⇒ **une seule paire**.
> ⚠ Non distingué LIVE (aucun porteur `GetStuckIn` du pool n'est multi-tuile).

> **Résidu nommé, hérité de ce port** : le nœud `If(AreEqual(Cache(First(picked,1)), It@0x180),
> Sum(q, rem), q)` de `$$GetLeftoverHitsPerTargetFormula` distribue le RESTE de la division entière à
> la première cible piquée. `It@0x180` = `ActiveTarget` = **slot 4** de l'`AbilityEntities`
> (`AbilityEntities$$.ctor` : `param_1[4] = param_3`), et NI `AttackBehaviour$$Execute` (qui n'écrit
> que les slots 1 = actor et 2 = target) NI `AttackDamageBehaviour$$ExecuteTarget` (qui évalue le
> nœud de coups contre l'`entities` reçu tel quel) ne le lient — **lu au décompilé**. Le port évalue
> le prédicat tel quel ⇒ toutes les cibles reçoivent `q`, et `rem` (0..cnt−1 coups) n'est pas
> distribué. Écart borné par `cnt − 1` coups, **nul** dès que `numLeft` est divisible par `cnt`
> (dont tout le cas `cnt == 1`). Fermer ce résidu = RE du slot 4 d'un cast top-level.

**PORTÉ ET FERMÉ par ce cas : #2, `1137 MurderousSwing`** (case-decision-noop, 2026-07-28). Face
COMBAT dans `engine/runner/abilities/worldeaters.py` (`MurderousSwingAbility`), entrée au registre
**avec ses deux littéraux** (`TARGETING_OPTIONS` = preset `TargetingOptions` statique `+0x40` →
`Rules = 0x4000 TargetIsEnemy` + `RANGE_ADJACENT` + `forceMeleeTarget = RangedBool.False`, le MÊME
preset que 1131 — relu ability par ability, jamais généralisé ; `ABILITY_ATTACK_TYPE` = 0
`DirectTargetAttack`, littéral du `AActiveAbility..ctor`). Garde live :
`tests/engine/runner/test_murderous_swing_live.py` (5 tests) + fixture nommée
`_adjacent_swing_regime.py`. ROUGE mesuré AVANT le port, sur le même montage :
`ported=False`, `flags={ability_used_flag: True, turn_finished: True}` (cast ACCEPTÉ, tour consommé)
et **cible 500000 → 500000, caster 9537 → 9537** — zéro mutation, alors que le MÊME cast LIVE mutait
(`mutated=True`, 84 événements, 7 906 de dégât).

> **Deux pièges de RE payés sur cet item, et ils se généralisent :**
>
> 1. **`AmountIsGreater` est STRICT, et le ctor MENT.** `IdunBattleLogic.Entities.DSLFactory$$AmountIsGreater`
>    appelle un ctor que ghidra étiquette `IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$.ctor` —
>    **corps trivial DÉDUPLIQUÉ** (les deux classes ont le même ctor à 2 champs). La classe réelle ne se lit que
>    sur le `ShouldTrigger` : `...AmountIsGreaterAbilityTrigger$$ShouldTrigger` rend `b < a` (STRICT),
>    `...AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` rend `b <= a`. Conclure sur le nom du ctor
>    donnait `Count >= 1` = toujours vrai ⇒ un `extraDmg` **jamais appliqué**, l'exact contraire de l'i2
>    et de la mesure `case-108`. C'est le cas d'école de « l'absence/le nom dans les tables ne prouve rien ».
> 2. **Le `Count` est RÉÉVALUÉ PAR CIBLE** (aucun `Cache` natif ; `AttackDamageBehaviour$$ExecuteTarget`
>    évalue le nœud de dégât une fois par cible, alors que le set est matérialisé UNE fois par
>    `AttackBehaviour$$Execute`). Quand des cibles meurent en cours de cast, les suivantes basculent
>    MULTI → SINGLE **dans le même cast**. Mesuré live : trois adjacents à 4 855 PV → deltas
>    `[0, 0, extraDmg]`, 3ᵉ coup **7 846** au lieu de 4 854 ; sous l'hypothèse `Cache` la 3ᵉ cible
>    SURVIVRAIT, or le natif la TUE. C'est la MORT (pas le montant, clampé aux PV) qui tranche.

> **Résidu NOMMÉ, trouvé en chemin et hors périmètre — ✅ FERMÉ (#192)** : `SereneUnifierSenseOfStone`
> (effet 1169, posé par le passif `SereneUnifier` d'`tauAunShi`) était dans l'enum du port sans
> **aucune classe d'effet** → `BaseEffect` nu, aucune contribution. Mesure d'origine : avec Aun'Shi
> dans le camp adverse, le dégât LIVE de 1137 valait **exactement la MOITIÉ** du dégât offline, sur
> les deux cibles à la fois (facteur 2,000 reproductible).
> **Porté** : `SereneUnifierSenseOfStoneEffect` (`engine/entities/effects/loki/damage_reduction.py`),
> mirror 1:1 de `IdunBattle.Entities.Effects.Loki.SereneUnifierSenseOfStoneEffect$$CreateEffectDamageMalusForDefense`
> = `ForPercentDecrease(get_OwnerIsTarget, ConfigVar(0x46 = dmgReductionPct))`, **sans aucun gate**.
> Ce n'était PAS une aura source-side : le behaviour turn-start
> (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour`) fait un
> `AddEffect` sur un **sélecteur**, donc l'effet est MATÉRIALISÉ sur chaque bénéficiaire et emprunte le
> canal DÉFENSEUR standard. Validé sur les DEUX faces (`probe_192_sense_of_stone.py`,
> `tests/engine/runner/test_sense_of_stone_live.py`) : facteur 2,000 → **1,000 bit-exact**.
> **Leçon de banc qui, elle, reste vraie** : `unit_map.py vanilla-target` ne voit que ce qu'une unité
> s'applique à ELLE-MÊME — jamais ce qu'un allié lui donne. Un banc de mesure se qualifie en lisant les
> effets **captés sur les cibles au moment de la mesure**, pas en filtrant le roster.

Les 10 autres restent ouverts et sont dispatchables **sans re-RE** : porteur, gate, symbole natif
(`IdunBattleLogic.Entities.Abilities.Active.Loki.<Nom>Ability$$ExecuteBehaviour`, sauf
`MurderousSwing` et `LightOfSanguinius` qui sont sous
`IdunBattleLogic.Entities.Abilities.Active.<Nom>Ability$$…`), écart observable et socle déjà
disponible sont donnés ci-dessus.

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

**Symptôme chiffré** — ⚠ **à RE-DÉRIVER, jamais à citer** : `python scripts/python/probe_181_targeting_gaps.py`.
Dernière mesure (2026-07-28, après #210) : `ABILITY_CLASSES` = **94** entrées, **55** portent
`TARGETING_OPTIONS`, **39** n'en ont pas (les chiffres ci-dessous datent de #181 : 91 / 51 / 40).
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

> **#243 (2026-07-28) — l'autre moitié du gisement : un masque POSÉ ne sert à rien tant que la
> RÈGLE n'est pas dans la cascade.** Les bits `TargetIsNotAdjacent` (32) et
> `TargetIsNotAdjacentToEnemy` (42) étaient déclarés par 4 masques (1058, 1139, 1153 ; 1145) et
> **ne refusaient jamais rien**. Les deux prédicats sont DÉRIVABLES de l'état que le port possède
> déjà (positions + adjacence + équipes) et sont portés dans le maillon générique
> (`engine/runner/abilities/targeting.py`), pas en special-case :
> `battleQuery.<slot 0x61>(targetTiles, casterTiles)` = `MovementUtil$$AreTilesAdjacent(IList,
> IList)` pour le bit 32 ; `battleQuery.<slot 0x7f>(targetTiles, caster, false)` =
> `BattleQuery$$GetAdjacentEnemies` → `IterateAdjacentTiles(…, false, true, true)` +
> `CountOrGetUnitsOnTiles(enemyOf: joueur du CASTER)` pour le bit 42. Les index de slot sont LUS sur
> les lambdas de `RecordedSimulationRequestsBattleQuery` (`…DisplayClass118_0`/`…154_0`), qui
> ré-appellent l'inner par le même index — c'est la seule lecture qui les donne sans deviner.
>
> **Ce que la mesure a imposé EN PLUS, et c'est la leçon** : porter une règle sans porter celles qui
> la PRÉCÈDENT produit un refus pour la MAUVAISE raison (le natif s'arrête à la PREMIÈRE règle
> rompue). Trois maillons antérieurs ont donc dû entrer avec : `TargetHasFreeAdjacentTile` (bit 5,
> slot 0x51 `GetFreeAdjacentTiles`), `TargetTileIsFree` (bit 12, `TileExtensions$$CanAddUnit(t,
> state, 1, 0, 0)`) et la branche `TargetIsTile` du DÉBUT du filtre (tuile-cible non marchable →
> le natif rend le **littéral 1**, c'est-à-dire `ValidRequest` : cette valeur n'est donc PAS toujours
> « ability indisponible », et un oracle qui l'exclurait du contrat à l'aveugle masquerait un vrai
> désaccord).
>
> **Chiffres** (`probe_243_not_adjacent.py`, MC1_67/777 puis C3_30/31337) : **4 trous permissifs
> fermés** (1153 et 1139 à d=1, 1145 sur une tuile voisine d'un ennemi, 1145 sur une tuile occupée)
> **+ 1 violation de contrat préexistante corrigée** — pour une cible AU CONTACT, Waaagh rendait
> `TargetIsInRange` (sa règle dynamique) là où le natif rend `TargetIsNotAdjacent` ; aucune géométrie
> de test n'amenait un ennemi à d=1 du Warboss, le désaccord était donc latent. Après : **0 refus
> inventé, 0 refus pour la mauvaise raison** sur 18 couples (3 casters × 6 unités) + 3 tuiles, et
> **0/0 sur 88 couples** du second montage (autres porteurs des bits 5 et 12 : 1003, 1009, 1112,
> 1201). Gardes : `tests/engine/runner/test_targeting_adjacency_rules_live.py` (22 tests) + fixture
> `_not_adjacent_stage.py`. Résidu restant du bloc : `CasterHasFreeAdjacentTile` (bit 21) — **aucun
> porteur au registre**, donc rien à valider ; le porter serait spéculatif.

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
| `strike` | 5 | 1014 ArmoriumCherub, 1018 ValkyrieStrike, 1043 ThunderousAssault, 1104 SpiritLeech, 1122 CordClaw (~~1163 BlackRage~~ posé par #210) |
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
| ~~**R32**~~ | ~~gate `IsCharging` du canal extra-dégât~~ — **FERMÉ le 2026-07-28** (`case-r32-ischarging-consumers.md`), **et son diagnostic était FAUX sur deux points**. (1) « le gate n'est porté sur AUCUN des trois » : `AvalancheOfMuscle` 1025 et `FeederTendrils` 1197 le portaient DEPUIS TOUJOURS, par le proxy `has_moved` — le vrai défaut était que ce proxy **SUR-accorde** (cf. `N9`), pas qu'il manque. (2) « offline **+0** » était un artefact de mesure : `probe_avalanche_charge_gate.py` reconstruit l'état par `load_state`, qui ne seede PAS `UnitFlagsComponent` ⇒ `has_moved` FAUX offline ⇒ bonus omis. Dès que le pas est REJOUÉ offline (`MoveUnitMessage`), le régime CHARGE est **bit-exact 4/4 avant même le fix**. L'écart réel n'est donc ni +45 % ni +0 : c'est **+599/coup accordé à tort** dans le seul régime « bouge vers une cible déjà adjacente ». Fusionné dans `N9` | — | `IdunBattle.Core.Services.BattleQuery$$IsCharging` | `astraBullgryn`, `bloodDeathCompany`, Deathleaper | `engine/battle_query.py`, `engine/entities/effects/base.py`, `engine/runner/damage_model.py`, `engine/playbook/{scene.py,prediction/*}` | — |
| ~~**R33**~~ | **NÉ ET FERMÉ le 2026-07-28 (#178)** — ~~**FORK DE PORT : deux `is_overkill` dans `engine/services/`**~~. Le signalement de #169 (commentaire dans `damage_prediction.py`) parlait de « deux mirrors de la MÊME fonction native ». **Le décompilé corrige le cadrage** : il n'y a pas deux fonctions homonymes, il y a **UNE FAMILLE de TROIS surcharges** de `DamagePrediction$$IsOverkill` qui convergent toutes vers le MÊME corps de calcul (la 7-args privée). Le corps 7-args de `trait_damage_limits.py` en était le mirror 1:1 **fidèle** ; le corps 2-args de `damage_prediction.py` était la surcharge d'**INSTANCE** privée de ses gates d'unité (`CanBeOverkilled`, `PreventOverkill`, `allow_flag`, `extraDamage`). **C'est le corps AMPUTÉ que le chemin COMBAT consommait** (`AttackDamageOperation._fire_death_if_killed`) — donc c'est lui qui décidait `UnitFlag.Overkilled (8)` et les `overkill=` des trois vecteurs de mort. Foyer unique = `trait_damage_limits.py` (`is_overkill` = la 7-args, `unit_is_overkill` = l'instance) ; `damage_prediction.py` re-exporte | **MESURÉ LIVE** (`probe_178_overkill_gate.py`, paire de régimes à MÊME attaquant / MÊME dégât / MÊMES PV) : `ultraTitus` (400 PV, porte `FuelledByFury_BlockOverkill` ⇒ `UnitFlag.PreventOverkill`) frappé à **1452** (= 3,6 × PV) **n'est PAS marqué overkill** par le jeu (compteur `TerrifyingCrescendo` du tueur : 0 → **0**), là où `genesPrimus` (400 PV, **même** coup) l'est (0 → **1**). Corps supprimé : « overkill » des DEUX côtés. Corps livré : **2/2 d'accord avec le live** | `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (3 surcharges) ; `…$$CalculateDamageOperation` (inline de l'instance → `didOverkill@+0x13`) ; `IdunBattle.Operations.ApplyDamageOperation$$Execute+0x17d5` ; `IdunBattle.Entities.UnitExtensions$$CanBeOverkilled` ; `IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$ApplyInternal` / `$$RevertInternal` | `ultraTitus` (**HERO du pool**) pour `PreventOverkill` ; `emperNoiseMarine` comme lecteur (`TerrifyingCrescendo` = `HasFlag(target, 8)`) | `engine/services/{trait_damage_limits,damage_prediction}.py`, `engine/runner/components.py`, `engine/runner/operations/damage.py`, `…/triggers/{__init__,dispatch/__init__}.py` | **FERMÉ** — gardes : `tests/engine/runner/test_overkill_gate_live.py` (3 tests, vues ROUGES par 2 mutations distinctes), fixture `overkill_gate_case`. Résidus nommés à sa fermeture : **repris et fermés par `R33-b` ci-dessous** |
| ~~**R33-b**~~ | **NÉ ET FERMÉ le 2026-07-28** — ~~les trois champs du `DealDamageInfo` (`allow_flag`/`default_flag`/`extraDamage`) « ne descendent pas jusqu'au chokepoint de mort »~~. **Le cadrage hérité était le vrai défaut** : c'étaient des PLACEHOLDERS OPAQUES, pas des champs exotiques. La signature native, relue dans `data/symbols/<build>/frida/methods.tsv`, les nomme : `IsOverkill(target, hitDamage, **deniedDamage**, **isCritical**, **isForceOverkill**, targetHealthBeforeAttack, minimumHealth)`. `default_flag` = **`isCritical`** (`@+0x1c`), `allow_flag` = **`isForceOverkill`** (`@+0x2c`), `extraDamage` = **`deniedDamage`** (`@+0x18`, = `previousHitsDeniedDamage`, le `_rogne` de `_run_hits`). Le corps privé **RENVOIE `isCritical`** dans le cas « létal mais SOUS le seuil » ⇒ **tout crit qui tue sans doubler les PV EST un overkill**. Le port passait 0 en dur : dégradation PERMISSIVE, aucun test rouge. Threadés par `AttackDamageOperation._did_overkill`, qui **re-joue la séquence des coups** (le natif appelle `IsOverkill` PAR COUP, et `isCritical`/`deniedDamage` varient d'un coup à l'autre) | **MESURÉ LIVE, 2 montages indépendants.** (A) crescendo `TerrifyingCrescendo`, PV **2178**, plage [2178,3267] (létal, pct ≤ 50 % < seuil 100 %) : **avec crit 0 → 1**, **sans crit 0 → 0**. (B) porte revive `Narthecium` (« unless Overkilled », chance 100), tueur `ultraInceptorSgt` **sans `ThrillSeekers`** — donc attribution à `isCritical` et pas au rider : sans crit la victime est **REVIVE**, avec crit elle **reste morte**. (C) `isForceOverkill` seul (aucun crit) : `FlailSwing` (`deathBlightlord`), dégât réel **20884** sur **16928** PV (pct 23 %) → **pas de revive** live, port d'accord | `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (les 3 surcharges) ; `…$$CalculateDamageOperation` (inline, `DealDamageInfo@+0x18/+0x1c/+0x2c` → `DamageAppliedResult.didCrit@+0x12` / `didOverkill@+0x13` / `isForceOverkill@+0x14`) ; `…$$ApplyTraitDamageLimitsToDamage` ; `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` ; `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` (param `forceOverkill`) ; `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal` (`MinimalHealth@+0x1c`) | `emperNoiseMarine` + `genesPrimus` (montage A) ; `ultraInceptorSgt` + `ultraApothecary` (montage B) ; `deathBlightlord` (montage C) — **tous HEROS du pool** | `engine/services/trait_damage_limits.py`, `engine/runner/operations/damage.py`, `…/damage_hits.py` (+1 liste `denied_before`), `…/damage_ops/{normal,normal_like,ability}.py`, `engine/utilities/damage.py`, `probe_178_overkill_gate.py`, `tests/engine/runner/test_overkill_gate_live.py` | **FERMÉ** — 8 tests, vus ROUGES par **3 mutations distinctes** (sémantique `isCritical`, câblage `hits_result`, sémantique `isForceOverkill`). **Verdicts des gates restants** : `CanBeOverkilled` = **STRUCTURELLEMENT quiescent** au chokepoint de mort (mesure : `unit_map.py find --trait Steppable` = **27 porteurs, tous à HP 0** ; le natif les tue par ÉCRASEMENT, `DamageReason.Steppable = 2`, hors `_fire_death_if_killed`) — **pas un trou de montage** ; `targetMinimumHealth` (8e arg, plancher Hypersensory) = porté, quiescent au chokepoint par construction (un plancher actif empêche les PV d'atteindre 0). **Résidus NEUFS nommés** : `unitComponent@+0x24` (accumulateur adjacent à `MinimalHealth`, ajouté au total d'overkill — nul sans plancher actif) ; ~~`MightBeOverkill` passe `MightCrit@+0xb1` que le port laisse à 0 (face DÉCISION, hors périmètre)~~ → **FERMÉ par `R34`** ; `EffectAdditionalHits.forceOverkill` et le vecteur `additional_hits.py` non threadés (fichier PRIS par un autre agent) |
| ~~**R34**~~ | **NÉ ET FERMÉ le 2026-07-28 (`case-r34-mightbeoverkill-mightcrit.md`)** — le résidu que `R33-b` avait nommé et **délibérément** laissé ouvert : ~~`MightBeOverkill` passe `MightCrit@+0xb1` que le port laisse à 0~~. Face **DÉCISION** (l'autre moitié de `R33-b`, qui a fermé la face COMBAT). `IdunBattle.Core.Services.DamagePredictionResult$$MightBeOverkill` et `…$$WillBeOverkill` appellent la MÊME surcharge privée 8-args et ne diffèrent **que par 2 arguments** : le dégât (raw MAX vs raw MIN/scénario block) et **`isCritical`** — `MightCrit@+0xB1` pour la borne OPTIMISTE, **littéral `0`** pour la GARANTIE (ordre des args re-dérivé au DÉSASSEMBLAGE du site d'appel : le rendu Ghidra du `call` ne suffit pas). Le corps privé RENVOIE `isCritical` sous le seuil ⇒ le port sous-comptait `PossibleOverkill` sur TOUT kill critique dans `[PV, 2 × PV)`. **Canal porté de bout en bout** : producteur `services/damage_prediction.attacker_could_crit` (mirror de `DamageCalculations$$CouldCrit`, évalué DANS `predict_attack_raw` comme le natif l'évalue DANS `PredictAttackRaw`) -> `DamagePredictionResult.might_crit` -> clé `mightCrit` posée par `composite_fields` ET `_fields_from_native_event` -> LUE par `might_be_overkill`. Corrigé au passage : `DamagePredictionResult.add` fusionnait `might_crit` par `or` alors que le natif `Add` **ne fusionne AUCUN** des flags `@+0xB0..0xB3` | **MESURÉ LIVE, 3 étages.** (A) SOURCE : `pred.mightCrit` == `GetStat(9) >= 1 && GetStat(10) > 0` **15/15** sur les 4 cadrans de la conjonction (`100,1` / `100,0` / `0,1` / naturel) ; producteur offline == flag natif **15/15**. (B) UTILITÉ, formule ISOLÉE (les 2 côtés sur les MÊMES prédictions natives, scoreur natif = RPC `pairUtility`), régime létal-sous-le-seuil PV 10836 / bornes `[7218, 10836]` : natif **148.2903** vs port **133.2903** = **exactement `PossibleOverkill` (15.0000)**, et **0** écart sans crit ; après fix 0/0. (C) CLASSEMENT : 2ᵉ porteur `orksRuntherd`, 2 cibles en bandes d'overkill distinctes -> port AVANT choisit **B** (166.56 vs 168.51), natif et port APRÈS choisissent **A** (181.56 vs 168.51) | `…DamagePredictionResult$$MightBeOverkill` / `$$WillBeOverkill` ; `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (privée 8-args) ; `…$$PredictAttackRaw` (écrit `@+0xB0..0xB3` ; `IDamageCalculations` slot 7) ; `IdunBattle.Core.Services.DamageCalculations$$CouldCrit` ; `…DamagePredictionResult$$Add` ; `IdunBattle.AI.Utilities.OverkillUnitUtility` ; `…ComparablePlaybook…$$CalculateUtilityFromPredictions` | `ultraInceptorSgt` (montage utilité), `orksRuntherd` + `tauMarksman` (montage classement), `genesPrimus`/`necroWarden` cibles — **tous HÉROS du pool** | `engine/services/damage_prediction.py`, `engine/playbook/probable_damage_event.py`, `engine/utilities/damage.py`, `engine/playbook/prediction/{normal_attack,abilities}.py`, `engine/playbook/{psyker,fury_of_the_ancients}.py`, `engine_agreement_stages.py`, `probe_r34_overkill_decision.py`, `tests/engine/runner/{conftest,test_overkill_decision_live}.py` | **FERMÉ** — 6 tests, vus **ROUGES par 3 mutations distinctes** (consommateur qui ne lit plus, producteur qui ne pose plus, « harmonisation » de `WillBeOverkill`). **Résidus NEUFS nommés** : `isPreventOverkill@+0xB3` non porté côté DÉCISION (le décodeur d'events **n'expose pas** le champ ⇒ exige un changement de HOOK) ; `runner/operations/damage_utility.py` (sélecteur DSL `SortUnitsByDamageUtility`) ne pose pas la clé — port possible mais **non validable** sans un montage FinalJustice/AncestralFortune en régime létal-sous-le-seuil |
| ~~**R1**~~ | ~~Tuile d'ORIGINE dans les candidats d'ability du port, pas du natif~~ — **FERMÉ, PRÉMISSE RÉFUTÉE** : le slot +0xe est `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` (`OrderedSet` SEEDÉ avec `GetUnitPosition(unit)` puis `UnionWith(movable)`), donc **le natif MET l'origine dans ses candidats, en premier**. Le vrai écart était l'**ORDRE** du sweep (`Bucket$$AddAction` keep-first ⇒ à utilité égale le natif reste sur place) | réfutation live : **10** chunks natifs « caste sans bouger » avec movable NON vide (3 couples). Gain porté : `stay` 1/2 -> 2/2 (`C3_01`/31337, Stormcaller) et 8/9 -> 9/9 (crafté `C4_02`/4242, Njal) ; 0 régression sur 5 couples | `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` -> `IBattleQuery`+0xe ; `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` | tout hero du pool | `engine/ai/{context,state_bridge,action_generators}.py`, `engine/playbook/noncomparable/_base.py` | **LIVRÉ** — cf. `case-r1-origin-action-tile.md` |
| ~~**R1-b**~~ | **FERMÉ 2026-07-28 (`case-r1b-move-tile-sweep-order.md`)** — ~~Ordre RELATIF des tuiles de move dans le sweep de position~~. L'`OrderedSet` porte l'ordre d'**INSERTION** du pathfinder : `[origine] + aiMovableTiles` **à l'identique**. Ce n'est pas un tri. **Et le diagnostic hérité était FAUX sur deux points** : (1) « le natif prend `(4,4)` = 1re rankée » — il ne la prend pas *parce qu'*elle est rankée : `(4,4)` vaut **207.8506** contre **202.8506** pour `(6,4)` côté NATIF, ce n'est **pas un tie** ; le tie 192.851 est un ARTEFACT DU PORT (terme de tuile 30 vs 30 là où le natif fait 45 vs 40). (2) « l'`ExceptWith` de `GetMovablePositionsFor` » — c'est un **`UnionWith`** (même method-info que le `param_8.UnionWith(accumulé)` d'`AnyOrFillMoveableTiles`, dont la cible est un `OrderedSet` VIDE) : le natif AJOUTE les tuiles propres de l'unité, il ne les retire pas. Le port **forkait** (offline `state_bridge` balayait déjà l'ordre natif, seule la voie LIVE suivait `ranked`) — fork refermé | **ORDRE confirmé LIVE** (`probe_r1b_native_sweep_order.py`, hooks `scorerDamageTrace` existants) : la séquence des tuiles caster vues par `ComparablePlaybooku003CTu003E$$CalculateActionUtility` == `action_tiles` **exactement**, sur 2 couples / 21 tuiles / 0 écart (`C4_09`/999 pas 14 `templAncient` ; `C4_09`/31337 pas 22 `admecMarshall`). Coût métrique **assumé** : sweep isolé **102/165 -> 100/165** sur 10 couples (les 2 seuls chunks perdus sont ceux dont le natif prouve qu'ils ne sont PAS des ties : Δ **5.0** et Δ **59.0**) ; harnais complet : `ability` et `stay` INCHANGÉS, `pos` −1 sur le seul `C4_09`/999 | `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` ; `…MovementQuery$$GetMovablePositionsFor` / `$$GetMovablePositionsFromTiles` / `$$GetMovableTilesFor` / `$$AnyOrFillMoveableTiles` ; `IdunBattle.Core.UnitPositionExtensions$$ToUnitPositionList` ; `idun.shared.collections.OrderedSetu003CTu003E$$Add` / `$$UnionWith` / `$$SyncListWithSet` / `$$RemoveExtraEntriesFromList` ; `…ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` ; `…Bucketu003CTu003E$$AddAction` (keep-first) | tout hero du pool | `engine/ai/action_generators.py` (`_sweep_tiles`, `_action_utility`, `_best_attack`) | **LIVRÉ** — gardes : `test_move_tile_sweep_order_live.py` (3 tests × 2 montages, vues ROUGES par mutation « re-imposer l'ordre `ranked` » : 5 failed), montage `_move_tile_sweep_order.py` ; probes `probe_r1b_native_sweep_order.py` + `probe_r1b_move_tile_order.py`. **Résidu NEUF ouvert : `N13`** |
| ~~**N13**~~ | **FERMÉ 2026-07-28 (`case-n13-tile-term-triggered-playbooks.md`)** — ~~le terme de TUILE `Tile(7)` du port est SHORT, par tuile et de façon POSITION-DÉPENDANTE~~. **Le diagnostic hérité visait le mauvais étage** : les **29 enfants** de la `ComposedUtility` (re-énumérés live, `scorerComposedDump`) sont **tous** couverts par `TILE_LEAF_IDS` — aucune feuille ne manque. Le trou est UN ÉTAGE PLUS BAS : (a) la feuille **dispatcher** `TriggeredAbilities(2)` charge un playbook **par ability déclenchée du mover** (`PlaybookDatabase.LoadPlaybook`) et le registre du port n'en avait que **5 sur ~25** ; (b) la feuille `UnitEffectsRanged(12)` était portée mais **dormante** (`meta.neighbor_effect_names` plombée par aucun appelant) ; (c) le kit déclenché venait du seul `gameconfig.passiveAbilities`, qui **ignore traits et RELIQUES** | **RÉSOLU à la tuile près** : le résidu `X = Tile(7) − Elevation − TileEffects` (isolé aux hooks existants, jamais fitté) vaut `5 × amis≤ 2 hex **self compris**` sur `C4_09`/999 pas 14 (**11 tuiles / 11**, AstartesBanner 1106) et `5 × amis ring-1 **self compris** + 10 si le porteur de `PathOfCommand_ExtraDmg` est ≤ 2 hex` sur `C4_09`/31337 pas 22 (**10 tuiles / 10**, KardiocoreGalvanus 1457 + `UnitEffectsRanged`). Les deux ties ARTEFACTS (**192.8506** et **58.7948**) disparaissent | `IdunBattle.AI.Playbook.Loki.AstartesBannerPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` · `IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` · `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` · `IdunBattle.AI.Utilities.UnitEffectsRangedUtility$$GetSourceUnits` | `templAncient`, `admecMarshall` (hero, pool) | `engine/playbook/friends_in_range.py` (neuf), `engine/playbook/adjacent_unit_preference.py`, `engine/battle_query.py`, `engine/utilities/tile.py`, `engine/ai/context.py` | — |
| **N13-b** | **NEUF (2026-07-28, révélé en fermant N13) — le registre `TRIGGERED_MOVE_PLAYBOOKS` reste à **7 concrets sur 84**, et le kit déclenché OFFLINE ignore traits+reliques.** N13 a nommé la cause et fourni l'outillage ; elle se re-manifestera sur tout porteur dont le playbook de mouvement n'est pas encore porté. `state_bridge.py` (la voie qui joue réellement en self-play/RL) n'expose PAS les abilities déclenchées — `live_triggered_ability_ids` n'existe que sur le contexte LIVE | **Gisement chiffré** : `Utilities.Default.TriggeredAbilities` = **107 clés** BC ; **77** corps `*Playbook$$CalculateMovementUtilityInStepsInternal` restent hors registre (compte re-dérivé du binaire : **84** au total). Le symptôme est le MÊME que N13 (tuiles égalisées → tie artefact → arbitrage de position arbitraire) | `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` ; `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` | tout hero portant un des ~18 passifs restants | `engine/playbook/friends_in_range.py`, `engine/playbook/adjacent_unit_preference.py`, `engine/ai/state_bridge.py` | **1 playbook = ~10 lignes** ; la source OFFLINE du kit déclenché = 1 sous-tâche séparée |
| ~~**R5**~~ **FERMÉ 2026-07-27, PENDANT cette passe** (merge `17c2d74`, PR #151 — ma re-reproduction à `bec119f` était donc la DERNIÈRE : 1 failed / 2 passed, trace inchangée depuis 3 jours ; re-joué APRÈS rebase : **3 passed**) | ~~`test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` ROUGE~~ -> **CAUSE RACINE TROUVEE ET PORTEE** (`case-r5-skitarii-turn.md`) : le gate d'expansion `BasePathfinder$$NodesInNextLevel` -> `WalkPathfinder$$IsValidContinuePathTile` (bit 0x1 = effet de tuile `BlockEnteringUnitsTileEffect`) n'etait pas porte -> la flood-fill traversait les Swamp -> la passe IA choisissait une tuile ILLEGALE ((6,5)), a portee du SEUL ennemi 79, d'ou le changement de cible et le `hp 8536->8536` de l'ennemi mesure. Residus ouverts : R5-a (arbitrage de TUILE, axe elevation/menace), R5-b (gate non cable sur 5 autres appelants + `_pathdist_to_enemies`), R5-c (dependance au canal `tiles=tileMeta`), R5-d (bit 0x2 `GetEffectiveDepth`), R5-e (`load_state` ne pose jamais `ai_controlled`) | Oracle natif fabrique (Vanguard REEL invoque live par ControlEdict, joue seul au turn-start) : natif = move (4,7) cible 77 ; le TEST avait raison. Agrement `aiMovableTiles` 5 boards 0 ecart. L'indice `ability: 17` est **REFUTE** comme cause (id concret = 69 `Loki_NormalAttack` pour Marshall ET Vanguard, mais aucun etage de la voie normale offline ne le consomme) | `BasePathfinder$$NodesInNextLevel`, `WalkPathfinder$$IsValidContinuePathTile`, `WalkPathfinder$$GetTileBlockingReasons`, `StaticBattleRules.Effect$$NotBlockingMovementOfTraits` | admecDestroyer / Skitarii Vanguard -- SUMMON | `engine/entities/pathfinding/{walk_pathfinder,tile_blocking,fly_pathfinder}.py`, `engine/services/static_battle_rules.py`, `engine/ai/state_bridge.py` | -- (clos) |
| ~~**N6**~~ **FERMÉ (PR #155, `case-174`)** — MÊME cause que N7 : porteur `darkaStormSpeeder` = **MoW**, `minDmg`/`maxDmg` lus à l'**index 0**. Les 2 tests sont verts après le seul correctif de `snapshot.py` ; le diagnostic « étage perçage / `darkangels.py` » ci-dessous était FAUX | `test_hailstrike_phase2_live` ROUGE, 2 tests pas 1 | **RE-REPRODUIT au commit `bec119f`** (2 failed / 2 passed, chiffres INCHANGÉS malgré les 50 insertions de `darkangels.py` depuis) : (a) `test_hailstrike_attack_trigger_live` — « le trigger 1507 n'a PAS fire offline (`after_hit=[]`) » ; (b) `test_hailstrike_pierce_envelope_live` — « dégât live **2700** hors des bornes du port AVEC le bonus **[1688, 2532]** ⇒ la magnitude du perçage portée est fausse ». Le second est un **symptôme de magnitude chiffré**, pas un simple test rouge | registre `ACTIVE_ABILITY_TRIGGERS` / gates du `CreateTrigger` (a) ; étage perçage (b) | darkaStormSpeeder (**MoW du pool**) / Hailstrike — cf. `case-117` | `engine/runner/abilities/darkangels.py`, `engine/runner/operations/triggers/*`, test associé | **1 ability** (diagnostic d'abord). Probe présente : `probe_123_hailstrike_phase2.py` |
| ~~**N7**~~ **FERMÉ (PR #155, `case-174-mow-level-index.md`)** | **le `StatsComponent` d'une MoW est ÉCRASÉ : toutes ses variables per-niveau sont lues au NIVEAU 0** (`case-162` §4, « PORT-1 »). `load_state` appelle `_load_machines` (l.179) puis `_load_stats_and_effects` (l.182), dont la boucle sur `snapshot["units"]` **ne filtre pas `entityType`** — or `combatSnapshot` **inclut** les lignes `EntityType.Machine` depuis `d9d0008`. Pour la ligne Machine, `unitConfig` vaut `{"error":"visualId introuvable"}` ⇒ le ctx reconstruit n'a **ni niveau ni multiplicateur**, et `snapshot.py:393` pose ce `StatsComponent` niveau-0. `_load_machine_stats` (l.403), qui BÂTIT le bon ctx depuis l'`AbilityState` per-ability, s'exécute APRÈS et porte le gate `if … get_component(StatsComponent) is not None: continue` (l.324) — **il est donc systématiquement sauté** | **MESURÉ à `bec119f`** — `probe_162_mow_ability_level.py --mow orksRukkatrukk --ability SquigMine --var nrOfTiles` : `_machine_ability_state` = **(50, 140)**, `load_state` → `active_ability_level=0, multiplier=100`, `nrOfTiles` **2** au lieu de **4**, verdict imprimé « ECRASEMENT CONFIRME ». Test de garde ROUGE : `test_mow_effect_posers_live.py::test_squig_mine_confront_live` → `cardinal offline 3 != live 5`. `case-162` chiffre 3 autres écarts du même bug (`PlagueburstMortar` nrOfTiles 3 vs 7, `ThriceBlessedConflagration` nrOfRounds 1 vs 5, `EntropyCannons` `off_delta=20` vs `live_delta=1631`) et **4 tests rouges** | `IdunBattle.Operations.AddMachineOperation$$Execute` / `$$InitializeAbilitiesStatus` (le seul canal valable = l'`AbilityState` per-ability) | 8 MoW du pool | `engine/runner/snapshot.py` (`_load_stats_and_effects`) | **1 ligne** — correctif VÉRIFIÉ 4/4 par `case-162` (`continue` sur les lignes `entityType == Machine`), non appliqué car territoire d'un autre agent au moment du cas. ⚠ les effets de MoW doivent CONTINUER d'entrer dans le seed `EffectsState` (ils viennent de `decisionView.mows[].effects`, chemin indépendant) |
| ~~**N8**~~ **FERMÉ 2026-07-28 (`case-n8-owner-has-finished-min-turns.md`)** — le volet (b) est PORTÉ et le volet (a) est **REQUALIFIÉ** : ce n'est pas `turn_counts` qu'il fallait seeder | **(b) porté** : `OwnerHasFinishedMinTurns` est bien PER-UNITÉ, et sur `turnsFinished` — `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger` = `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(Self@0x148) >= amount`, où `GetTurnsFinished` rend `BaseUnitComponent + 0x5c`, écrit par la boucle d'`IdunBattle.Operations.EndTurnOperation$$Execute` sur `PlayerComponent.CurrentlyOwnedUnitIds` AVANT `On(0x17)`. Port : `UnitComponent.turns_finished` + `turnflow._bump_turns_finished`. **(a) requalifié** : `turn_counts` n'a plus AUCUN consommateur dont le comportement dépende de son seed — le seul restant (`EnvAmbushResurrectAbility`, `triggers/genestealer.py`) compare `turn_counts[player] − turn_defeated`, or `turn_defeated` est écrit DEPUIS `turn_counts` ⇒ la DIFFÉRENCE est invariante par décalage. **Le vrai gap de seed est le PER-UNITÉ, et c'est un gap de HOOKS** (cf. R33) | **MESURÉ live, 4 (seed, board)** — `probe_pilein_owner_turns.py` : à l'âge 0 du grot le natif consomme **0** `genrand_int32` (gate FERMÉ alors que le JOUEUR a fini ≥ 2 tours) et à l'âge 1 il en consomme **1** (777/MC1_67, 4242/MC1_44, 555/MC1_63) ou **5** = `Maybe` + 4 `Randomize` avec spawn (31337/MC1_67). Port d'APRÈS : accord **8/8**. Les deux régimes du port d'AVANT divergent en sens opposés — per-JOUEUR : 1 vs 0 à l'âge 0 (sur-tir, grot fantôme 3 fois sur 4) ; snapshot non seedé : 0 vs 1..5 à l'âge 1 (PileIn MORT) | `…UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger` → `UnitExtensions$$GetTurnsFinished` (`+0x5c`) ; `EndTurnOperation$$Execute` (écriture) ; côté joueur `TurnComponent+0x38` = `GetAmountOfTurnsStartedByPlayer` (DEUX compteurs natifs distincts — le port en a maintenant DEUX aussi) | orksRuntherd → `orksNpc1Grot` (PileIn), genestealers (Ambush) — **pool** | `engine/runner/components.py`, `engine/runner/operations/turnflow.py`, `engine/runner/operations/triggers/dispatch/turn.py` | **LIVRÉ** — gardes : `test_pilein_owner_turns_live.py` (+ fixture `_pilein_owner_turns.py`), probe `probe_pilein_owner_turns.py` |
| **N11** | **NEUF (2026-07-28, révélé en fermant N8) — `turnsFinished` PER-UNITÉ n'est exposé par AUCUN RPC** : `load_state` laisse donc `UnitComponent.turns_finished` à **0** pour toute unité chargée d'un snapshot mi-bataille. Sans conséquence quand le port joue la bataille depuis t=0 (c'est le cas NOMINAL, et **tous** les porteurs de PileIn sont des summons créés par le port lui-même, donc leur compteur est exact) ; mais tout replay one-shot chargé mi-bataille doit POSER le compteur à la main | non chiffré (dégradation silencieuse : gate simplement fermé). Les trois consommateurs qui posent la valeur à la main le disent : `probe_o4a_maybe_trigger_rng.py`, `test_maybe_trigger_rng_live.py`, fixture `_pilein_owner_turns.py` | **champ manquant = `BaseUnitComponent + 0x5c`**, lu par `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished`. Ce n'est **pas** un `StatType` (l'enum `StatType` va de 0 à 26 et n'en contient aucun) ⇒ `combatSnapshot`/`GetStat` ne peut pas l'atteindre : il faut le lire **directement sur le composant**, comme `frida/hooks/game/match-state.ts` lit déjà `DefeatedByMeleeAttack`/`DeathReason` (`getFieldOffset(unitComponentClass, …)`), et l'émettre p. ex. en `decisionView.units[].turnsFinished` | tout porteur de `OwnerHasFinishedMinTurns` — `orksNpc1Grot` (PileIn) ; aussi lu par `DutyEternalPlaybook$$GetUseProbability` et `InstrumentsOfVengeancePlaybook$$GetUseProbability` (face DÉCISION, non portée) | `frida/hooks/features/ai-step/projection.ts` ou `rpc-snapshot.ts` (capteur), puis `engine/runner/snapshot.py` (seed) | **1 capteur** — ⚠ exige un rebuild + reinject Frida : à grouper avec un autre besoin de hook. ⚠ `turnsFinished` n'est PAS dérivable de `turnsStarted` : une unité apparue PENDANT le tour de son propriétaire (tout summon) rate le bump de `StartTurn` et garde `turnsFinished = turnsStarted + 1` pour le reste de la bataille |
| ~~**N12**~~ | **NÉ ET FERMÉ le 2026-07-28 (`case-n8b-endturn-order.md`)** — ~~**ORDRE dans `EndTurnOperation.Execute` : le port tiquait les effets AVANT le vecteur `On(0x17 = TurnEnd)`**~~. Le résidu était nommé dans `case-n8` §5 (PR #171) mais **jamais vérifié au décompilé** ; il l'est maintenant, et le constat hérité était **exact**. Deux lectures indépendantes du corps d'`Execute` le donnent : le bloc de l'appel slot 0x51 / littéral `0x17` tombe en **fall-through** sur celui de `RefreshEffects`, et la branche `HasActivePlayer == 0` **saute directement** à `RefreshEffects` en enjambant le vecteur. ⚠ **La justification héritée était FAUSSE** : `RefreshEffects` n'inflige **aucun dégât** (`EffectComponent$$RemoveOneTurn` + 2 events + `RefreshEffectsOperation$$Execute`) — l'écart ne pouvait donc pas « mordre par un DoT qui entame les PV du grot ». Ce qu'il changeait vraiment : **l'état des effets que voient les gates du vecteur** | **AMPLEUR MESURÉE, et elle est NULLE sur les consommateurs du vecteur** — inventaire re-dérivé des registres (`probe_n8b_turnend_consumers.py`, 65 entrées) : les DEUX seuls consommateurs de `On(0x17)` sont `RadSaturationAbility` (gate `NOT HasFlag(owner, Moved)`) et le bespoke `PileIn` (`OwnerHasFinishedMinTurns(2) & Health Cur == Max`) — **aucun des deux ne lit un effet**, et aucun `EFFECT_TRIGGERS` n'écoute `TurnEnd` ⇒ répliques et tirages PRNG **inchangés** (accord live bit-exact préservé : 31337/MC1_67 `0 puis 5`, 4242/MC1_44 `0 puis 1`, identiques à N8). L'écart était **latent**. **Le consommateur qui changeait vraiment est ailleurs** : `land_deep_strike`, dont le gate `has_effect(TeleportStrike_TeleportingIn)` ne voit pas une instance `consumed` — une instance à durée expirant à cette fin de tour annulait l'atterrissage **silencieusement** (passives différées jamais initialisées) | `IdunBattle.Operations.EndTurnOperation$$Execute` (ordre des 5 étapes) ; `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` ; `IdunBattle.Entities.Components.TurnComponent$$HasActivePlayer` ; slot 0x51 = `Core.Services.OperationProcessor$$EvaluateAbilities` ; `Core.Services.OperationProcessor$$RefreshEffects` → `IdunBattle.Operations.RefreshEffectsOperation$$Execute` | orksRuntherd → `orksNpc1Grot` (PileIn), admecSmnVanguard (RadSaturation) — **pool / summon** | `engine/runner/operations/turnflow.py` | **LIVRÉ** — gardes : `tests/engine/runner/test_endturn_order_live.py` (10 tests, **4 vues ROUGES** par mutation adversariale, les 5 autres verts sous mutation = gardes de non-régression) ; probe : `probe_n8b_turnend_consumers.py`. **Résidu nommé ouvert** : l'instant du DRAIN des behaviours (`ExecuteInternal` enfile, `ProcessPendingTriggeredAbilities` draine) relativement à `RefreshEffects` n'est PAS tranché — le port collapse les deux (#201), et aucune garde ne repose dessus |
| **R4** | **VALIDE** (relu à `bec119f`, références EXACTES) — **Resolve slot-8 non matérialisé dans `execute_normal_like`** : `HitDamage.get_damage` court-circuite toujours à `min == max` (`damage_hits.py:49-50`) ; le seul resolve matérialisé (`damage_hits.py:269-270`, `if is_attack_damage_op: rng.next_internal(...)`) est enfermé dans la branche `post_roll is not None` (bounds-mode) | splash Psyker : le live consomme **1 `genrand_int32` de plus que le port par volet splash** — constant, mesuré sur pool=1 et pool=2, absent quand le splash ne fire pas. Avec `spread_pct=0` (tous les call-sites amount-mode, `combat.py:156-158`) → **0 tirage/coup côté port** là où le natif en consomme 1 | `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` appelle `Next(v, v+1)` **sans gate largeur-1** | astraPrimarisPsy / tout Psyker du pool | `engine/runner/operations/damage_hits.py` (branche reduce-then-roll de `_run_hits`), `damage_ops/normal_like.py::execute_normal_like` | **1 effet** — ⚠ conditionner à la FAMILLE de factory native, pas à la largeur des bornes (le porter inconditionnellement casse Stormcaller 3-hit bit-exact) |
| ~~**R6**~~ | **FERMÉ 2026-07-28** — **`execute_normal_like` ET `additional_hits` ARRONDISSENT** (`Fix64.Round(·, AwayFromZero)`), comme les deux autres vecteurs COMBAT. Ce n'était pas trois lois mais UNE : les deux voies natives de coups additionnels (`AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` → `ExecuteHits` ; `ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` → slot 0x3c `Core.Services.OperationProcessor$$AttackDamage` → `AttackDamageOperation$$Execute` → `ExecuteHits`) **et** `execute_normal_like` (mode `amount` d'`AttackWithAttackDamage` + `UseNormalAttackIfAble` on-appearance) retombent sur la MÊME `AttackDamageOperation$$ExecuteHit` que les coups d'arme | **MESURÉ** — `normal_like` (DeathFromAbove/`ultraSmnInceptor`, Bolter p20, cellules [159,239] tronquées vs [160,239] arrondies) : live == arrondi **30/30**, == troncature **0/30**, + TÉMOIN branche-armure 12/12 sur les deux modèles ; `additional_hits` (SquigHound predefined [2660,3988], Physical p1, armure forcée 6000) : live == arrondi **14/14**, == troncature **10/14**, les 4 écarts exactement sur frac ≥ .5 | `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` : `Fix64.Round(Mul(v, multiplier), AwayFromZero)` **inconditionnel** dès qu'un `Nullable<DamageModifiers>` HasValue | le prérequis (b) « branche perçage gagnante » était INATTEIGNABLE sur `Physical` p1 (aucune armure du roster > 2633, et la seule à 3513 est `BigTarget` ⇒ réveille `BeastSlayer` et casse (a)) → **levier NEUF `rl_duel build --armor-target`** | `damage_ops/normal_like.py::_reduced`, `additional_hits.py::reduce_group_damage` (foyer extrait) | **LIVRÉ** — cf. `case-r6-materialisation-normal-like-additional-hits.md`. Gardes : `test_normal_like_bounds_rounding_live.py`, `test_additional_hits_rounding_live.py`, fixture `_pierce_floor_regime.py` |
| ~~**#38**~~ | **PÉRIMÉ 2026-07-28** (`case-38-offbyone-armor-materialization.md`) — l'« off-by-one (+1) valeur-dépendant à armure > 0 sur les DEUX vecteurs » noté HORS SCOPE par `solving-playbook.md` (entrée `rngcrit-1202`, l. 555-558) **ne se reproduit plus**. Le cadrage hérité (« gap de ROUNDING pierce/armure ») était FAUX de deux façons : ce n'était pas l'étage perçage (défaut FLOAT fermé par #30a, de signe OPPOSÉ : `port = natif + 1`) mais la MATÉRIALISATION finale, qui TRONQUAIT au lieu d'ARRONDIR — fermée par **#131** (vecteur normal) puis par la **campagne HeavyGravCannon** (vecteur ability bounds-mode, `_round_mat = True`). ⚠ le playbook n'est PAS amendé ici (auteur exclusif = `fable-solver`) : sa note de résidu reste à corriger | **RE-MESURÉ** sur le montage d'origine (`custoKyrus` 3 coups `Power` pierce 40 vs `necroWarden`, `--armor-target 6000`) : port LIVRÉ **bit-exact 24/24 coups**, 8 casts, les 2 vecteurs, `cc = 0` **et** `cc >= 1` (consommation **9 live == 9 port** sur le cast d'ability à cc=50). `live == ARRONDI` 24/24, `live == TRONCATURE` 5/24 — les 5 coïncidences exactement sur les coups NON discriminants (branche armure, ou frac < .5). **La troncature REPRODUIT le symptôme de la fiche** (`port = live − 1`, cellules tronquées `(803,1205)` -> per-coup `[1112,848,829]` vs live `[1113,849,830]`) ⇒ les chiffres cités étaient ceux du port de l'époque | `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` (slot 0x10 : `Fix64.Round(Mul(v, multiplier), AwayFromZero)`) ; `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing` (le plancher dont la branche PERÇAGE rend l'étage observable) | `custoKyrus` (**HERO du pool**) — attaque normale ET ability 1202 `VigilanceEternal`. Le 3ᵉ point de la même note (« ability multi-coups à `cc >= 1` : aucun porteur spawnable ») est **RÉFUTÉ** : `--crit <cc>,<cd>` pose la crit d'un p-unit au build, donc un seul porteur du pool suffit | — (aucune modification moteur) | **CLOS** — probe : `probe_38_offbyone_armor.py` ; garde : `tests/engine/runner/test_offbyone_armor_38_live.py` (2 tests, vues ROUGES par mutation adversariale des DEUX vecteurs) |
| ~~**R6-b**~~ | **FERMÉ 2026-07-28** — **le canal `additional_hits` résout en ROLL-THEN-REDUCE, 2 tirages/coup** : `ExecuteHit` commence par `IdunBattle.Core.HitDamage$$GetDamage` sur le `HitDamage` de l'`AttackData` — que `AdditionalHitsFromEffects$$GetAdditionalHitsData` bâtit par `HitDamage$$.ctor(min = descripteur.minDmg, max = Nullable(descripteur.maxDmg))`, donc **NON dégénéré** pour un groupe `predefined` ⇒ 1 tirage BRUT (LA valeur) + 1 resolve slot-8 **gaspillé mais consommé** (`RandomlyResolveMinMaxDamage` = `Range(min, max+1)` **sans gate `min == max`**, contraste EXACT avec `GetDamage` qui en a un). Porté par `post_roll=_reduce` + `is_attack_damage_op=True` = la branche déjà mirrorée et validée du vecteur ability bounds-mode de la MÊME famille ATTACK | **DEUX cas discriminants, sur deux AXES** : (a) LARGEUR DU MODULO — `orksRuntherd`/SquigHound, `Physical` p1, armure forcée 6000 : 1ᵉʳ coup reproduit **5/5** par roll-then-reduce, **0/5** par reduce-then-roll (11/11 vs 0/11 sur la campagne d'origine) ; (b) CONSOMMATION — `admecRuststalker`/CordClaw, `DirectDamage` **p100** (réduction = identité ⇒ 1ᵉʳ coup identique dans les deux ordres, seul le resolve gaspillé sépare) : 2ᵉ coup reproduit **7/7** avec resolve, **0/7** sans resolve, **0/7** en reduce-then-roll | `IdunBattle.Core.HitDamage$$GetDamage` ; `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` ; `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData` | `orksRuntherd`, `admecRuststalker`, `thousInfernalMaster` — **pool** | `engine/runner/operations/additional_hits.py` | **LIVRÉ** — cf. `case-r6b-additional-hits-roll-order.md`. Gardes : `test_additional_hits_roll_order_live.py` (les 2 axes) ; probe : `probe_r6b_additional_hits_order.py` |
| ~~**R6-b'**~~ | **FERMÉ 2026-07-28** — **le `Maybe` after-hit d'un trigger `On(8)` EST roulé sur les coups d'un GROUPE additionnel, avec l'index de coup CONTINU de l'ATTAQUE.** L'index n'est pas local à `ExecuteHits` : `OngoingAttack$$.ctor` met `+0x30` à 0, l'objet est poussé **une seule fois par attaque** sur la pile `MatchState+0x60` (`MatchState$$StartAttack` ← `StartAttackOperation$$Execute`) et toute sous-opération le récupère par `Peek` (`ADamageOperation$$GetCurrentAttackOrDefault` → `BattleQuery$$GetCurrentAttackOrDefault` → `MatchState$$GetCurrentAttack`) ⇒ la voie GROUPES (`ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` → slot 0x3c → `AttackDamageOperation$$Execute` → `ExecuteHits`) partage le MÊME compteur. Porté par `bonus_hit_chance` + `hit_index0` THREADÉS depuis la phase d'arme — **un seul site d'évaluation**, pas un second (le fork de port de #110). Question restée ouverte par R6-b, TRANCHÉE : `AddBonusHitsToCurrentHitGroupBehaviour$$Execute` écrit la paire `(AbilityOrEffect, count)` dans la liste `+0xf0` du **CASTER**, que `ADamageOperation$$UpdateHitGroupAfterHit` déverse après CHAQUE coup dans le `hitGroup+0x58` **de la sous-opération courante** — donc un succès PENDANT un groupe défère un coup bonus DANS CE GROUPE (chaque sous-op a son propre `SetupHitGroup`), exécuté par la boucle de fin d'`AttackDamageOperation$$Execute` sur une COPIE de la liste (anti-récursion) | **MESURÉ live** (`probe_r6bp_after_hit_maybe_groups.py`, régime perçage-dominant `--armor-target 6000`, crit/block neutralisés) — (a) `orksRuntherd`/SquigHound vs `ultraApothecary` (**3** coups d'arme) : port **8/8**, contrefactuel « pas de `Maybe` dans les groupes » **2/8**, **6/8** seeds discriminantes ; (b) MÊME porteur vs `templSwordBrother` (trait `Parry` ⇒ **2** coups d'arme, **parité INVERSÉE**) : port **6/6**, contrefactuel **1/6**, **5/6** discriminantes ; (c) TÉMOIN sans trigger after-hit (`admecRuststalker`/CordClaw) : **4/4** bit-exact, les deux modèles IDENTIQUES ⇒ aucun tirage ajouté ailleurs. Les deux régimes de parité apparaissent SEULS dans chaque montage (le `Maybe` d'arme spawne un coup bonus quand il réussit, décalant l'index d'entrée du groupe) : {0 bonus: 5, 1 bonus: 3} en (a), {0: 3, 1: 3} en (b) ⇒ un modèle « toujours +1 tirage » tomberait. **Preuve côté JEU** : les events live portent `Additional_Hit_TriggeredAbility_Source: 1234` = `AbilityOrEffect(0x4d2)`, le littéral exact de `GetStuckInAbility$$CreateBehaviour`, sur un coup émis APRÈS les deux coups `Additional_Hit_Effect_Source: 1292` (SquigHound) et sous le MÊME `Attacker_Id` | `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` (dernière instr. d'`AttackDamageOperation$$ExecuteHit`, appel INCONDITIONNEL) → `AbilityEntities$$.ctor` champ **+0x110** → `IdunBattle.Entities.Formulas.CurrentHitIndexFormula$$Calculate` ; `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger` = `On(8) & AmountIsOdd(CurrentHitIndex()) & OwnerIsCaster & !(MinDistance > Direct(2))` ; `…$$CreateBehaviour` = `Maybe(AddBonusHitsToCurrentHitGroup(…, AbilityOrEffect(0x4d2)), GetBonusHitChance())` ; `IdunBattle.Operations.ADamageOperation$$UpdateCurrentAttackAfterHit` ; `IdunBattle.Core.OngoingAttack$$.ctor` ; `IdunBattle.Core.MatchState$$StartAttack`/`$$GetCurrentAttack`/`$$FinishAttack` | `orksRuntherd` (seul porteur `GetStuckIn` ayant AUSSI un descripteur de coups additionnels), tout porteur `GetStuckIn` du pool par la voie aura — **pool** | `engine/runner/operations/damage_hits.py` (`hit_index0` + `next_hit_index`), `engine/runner/operations/additional_hits.py` (threading), `engine/runner/operations/damage_ops/normal.py` (câblage) | **LIVRÉ** — gardes : `test_additional_hits_after_hit_maybe_live.py` (2 montages à parité inversée, 7 seeds) ; probe : `probe_r6bp_after_hit_maybe_groups.py`. Le résidu « vecteur ABILITY » qu'il laissait ouvert est **FERMÉ par R6-b''** (ligne suivante) |
| ~~**R6-b''**~~ | **FERMÉ 2026-07-28** — **le `Maybe` after-hit d'un trigger `On(8)` EST roulé sur les coups d'une attaque d'ABILITY**, pour les **deux** familles de factory. `ADamageOperation$$EvaluateAfterHitTriggers` (seul émetteur de `On(8)`) a EXACTEMENT TROIS appelants (xref), tous en `UNCONDITIONAL_CALL` et tous en DERNIÈRE instruction de leur `ExecuteHit` : `AttackDamageOperation$$ExecuteHit` (famille ATTACK — **la même fonction** que l'attaque normale), `AbilityDamageOperation$$ExecuteHit` (famille ABILITY) et `MachineDamageOperation$$ExecuteHit` ⇒ **aucun gate de famille**. L'index vient du même `currentAttack+0x30` (`AbilityDamageOperation$$ExecuteHits` le passe en 2ᵉ argument de son `ExecuteHit` et l'incrémente après CHAQUE coup, mirror INLINE d'`UpdateCurrentAttackAfterHit` ; il fait aussi l'`AddRange(hitGroup+0x58, attacker+0xf0)` et `AbilityDamageOperation$$Execute` re-boucle sur une COPIE ⇒ **les coups bonus déférés existent aussi côté ABILITY**). Et il **repart de 0 par CIBLE** : `DSLFactory$$AttackWithAttackDamage` **et** `$$AttackWithAbilityDamage` finissent tous deux par `AttackBehaviour$$.ctor(caster, targets, <behaviour>, options)`, et `AttackBehaviour$$Execute` émet `Core.Services.OperationProcessor$$StartAttack` (slot 0x3a) avant CHAQUE cible / `$$FinishAttack` (0x3b) après ⇒ un `StartAttackOperation$$Execute` (= `new OngoingAttack` + Push sur `MatchState+0x60`) par cible — ce qui reconstruit au passage d'où vient `On(PreAttack = 5)` sur ce vecteur (#84/#61) | **MESURÉ live** (`probe_r6bp2_after_hit_maybe_ability.py`, régime perçage-dominant `--armor-target 6000`, crit/block neutralisés) — (a) `orksKillaKan` (GetStuckIn) caste `DakkaDakkaDakka` (1171, **6 coups** Projectile, famille ATTACK) sur cible ADJACENTE : port **8/8**, contrefactuel `no_maybe` (= le port d'avant) **0/8**, modèle concurrent `parity` (index décalé de 1 : MÊME nombre de tirages, rangs différents) **0/8**, **8/8** discriminantes ; (b) MÊME porteur/ability, cible à **3 hex** ⇒ gate `!(MinDistance > 2)` FERMÉ : port **4/4**, modèle `always` (canal sans gate de distance) **0/4** ; (c) TÉMOIN `admecRuststalker`/CordClaw (registrée, rejeu `ActiveAbilityMessage` complet) : **4/4** bit-exact sur les 3 modèles non forcés, et `always` **échoue** ⇒ le témoin n'est pas aveugle. **Preuve côté JEU** : sur 6 seeds de (a) le 7ᵉ event porte `Additional_Hit_TriggeredAbility_Source: 1234` = `AbilityOrEffect(0x4d2)`, le littéral exact de `GetStuckInAbility$$CreateBehaviour`. Recoupement non cherché : le live de (b) **est** le contrefactuel `no_maybe` de (a), au coup près | `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` (3 xrefs) ; `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits`/`$$ExecuteHit`/`$$Execute` ; `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (slots 0x3a/0x3b) ; `Core.Services.OperationProcessor$$StartAttack` → `IdunBattle.Operations.StartAttackOperation$$Execute` ; `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` / `$$AttackWithAbilityDamage` (les deux → `AttackBehaviour$$.ctor`) ; `…GetStuckInAbility$$CreateTrigger` | **constat RE-DÉRIVÉ, pas hérité** : `GetStuckIn` est porté par **CINQ** héros du pool (`orksBigMek`, `orksKillaKan`, `orksNob`, `orksRuntherd`, `orksWarboss`) et non par le seul `orksRuntherd` ; **un seul** a une ability offensive multi-coups : `orksKillaKan`/`DakkaDakkaDakka` | `engine/runner/operations/damage_ops/ability.py` (câblage `_gsi` sur les deux faces) | **LIVRÉ** — cf. `case-r6bp2-after-hit-maybe-ability-vector.md`. Gardes : `test_ability_after_hit_maybe_live.py` (3 tests, 9 cas, fixture `_ability_after_hit_regime.py`) ; probe : `probe_r6bp2_after_hit_maybe_ability.py`. ⚠ **Résidus NOMMÉS** : (1) le volet famille **ABILITY** (`AttackWithAbilityDamage`) est porté sans gate — conforme au décompilé — mais **non confronté live** (aucun héros `GetStuckIn` n'a d'ability de cette famille) ; (2) le canal #179 (groupes) sur le vecteur ability est câblé mais **non exercé** (`orksKillaKan` n'a aucun effet à coups additionnels) ; (3) `DakkaDakkaDakka` (1171) n'est **pas** au registre `ABILITY_CLASSES` — le rejeu offline appelle `execute_ability_attack` DIRECTEMENT avec les paramètres lus au décompilé |
| ~~**R6-c**~~ | **FERMÉ 2026-07-28** — **bornes COMBAT des groupes `amount`**, sur les **DEUX** formes que le canal recouvre, et sur **DEUX axes** (valeur ET consommation). (1) **Nœuds DISTINCTS** (`CyclicIonBlaster`) : la face combat lit `ConditionalAmount(cond, RandomAmount(Sum(minDmg,extraDmg), Sum(maxDmg,extraDmg)), RandomAmount(minDmg,maxDmg))` là où le port étalait le seul nœud d'affichage (`amount` = `minDmg`) à ±20 %. (2) **Nœud UNIQUE SCALAIRE** (`FoulInfusion` `ConfigVar(0xb)` avec `param_8 = 0` explicite ; `ExplosiveMaladies` `ConfigVar(8)` avec `Create` **inliné**, `param_1[1] == param_1[2]`) : les slots 2 et 3 tapent le même `ConfigAmount` ⇒ cellule **DÉGÉNÉRÉE** `[v,v]`, donc **0 tirage** `GetDamage` — un changement de **CONSOMMATION**, pas seulement de valeur. ⚠ Le blocage hérité (« pas de montage live sur leur porteur ») était faux : les **trois** porteurs sont HERO, directement dans `--list-pool` | **MESURÉ live** — (1) deux montages qui **inversent** la largeur relative (`astraCreed` `cond` faux : ROLL `[599,898]` largeur 299 vs contrefactuel 240 ; `admecMarshall` `Mechanical`, `cond` vrai : ROLL `[1198,1497]` largeur 299 vs contrefactuel 479) ⇒ port **8/8**, contrefactuel **0/8**, 8/8 discriminants, coups d'arme bit-exacts 8/8 ; (2) `ExplosiveMaladies` et `FoulInfusion` : groupe **invariant** (`[1496]` resp. `[1954]`) sur **4 flux RNG différents** alors que les coups d'arme varient (2793/2833/2725/2160), et budget `genrand` natif **3** = port **3** ≠ contrefactuel **4** ⇒ **8/8 sur les deux axes, 0/8 pour le contrefactuel** | `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` (`param_1[1]` = ROLL ; `if (param_8 != 0) param_3 = param_8; param_1[2] = param_3` = DISPLAY avec repli) ; `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits` ; `IdunBattle.Core.HitDamage$$GetDamage` (`if (*param_1 == param_1[1]) return *param_1;`) ; `IdunBattle.Entities.Formulas.ConditionalAmount$$CalculateMin` (délègue à la branche) ; `IdunBattle.Entities.Formulas.RandomAmount$$CalculateMin`/`CalculateMax` ; `IdunBattle.Entities.Formulas.ConfigAmount` | `tauCrisis`, `deathPutrifier` (ExplosiveMaladies + FoulInfusion), `blackObliterator` (témoin, corrigé en #159) — **tous HERO, pool** | `engine/entities/effects/loki/hits.py`, `engine/runner/operations/additional_hits.py` (commentaire du repli) | **LIVRÉ** — cf. `case-r6c-amount-group-bounds.md`. Gardes : `test_additional_hits_scalar_bounds_live.py` (6 tests : 2 branches du `ConditionalAmount` + les 2 descripteurs scalaires sur l'axe conso) ; probe : `probe_r6c_ah_bounds.py`. ⚠ **Résidu NEUF nommé** : la **cellule d'ARME** de `deathPutrifier` en mêlée diverge (live 3219/3529/2923/**2750** vs offline 2333/2649/2505/**3170** — écart de **signe variable** ⇒ bornes de cellule, pas un facteur), alors que le flux reste aligné et que le groupe du même coup est bit-exact (donc armure et %-mods défenseur sont justes) ⇒ suspect en **amont** de la réduction ; ancrage : RPC `statModSources` sur le porteur, trait `ContagionsOfNurgle` premier suspect |
| **R7** | **VALIDE** — **`execute_normal_like` ne threade pas `target_traits`** : `damage_ops/normal_like.py` passe `target_id`/`is_ranged` mais **pas** `target_traits`, que le vecteur ABILITY passe lui (`damage_ops/ability.py`). ⚠ **CORRECTION 2026-07-28 : la mention « idem `additional_hits` » est FAUSSE** — `execute_additional_hits` ne construit PAS de mods, il REÇOIT ceux de `execute`/`execute_ability_attack`, qui threadent tous deux `target_traits` ; le canal #179 est donc DÉJÀ correct sur cet axe | jumeau du prérequis levé pour `execute_ability_attack`, dont la mesure était **+443 = `extraDmg[50] × 160 %`** de `HeavyGravCannon` (gate `HasTrait(target, 5=Mechanical)`) | `IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` — un SEUL collecteur natif, pas un par famille | **VERROU DE CONFRONTABILITÉ RE-VÉRIFIÉ 2026-07-28 : RÉEL.** Les effets gatés `target_traits` sont **5** (`BeastSlayer_ExtraDmg`, `MartialKatah_DmgBonus`, `CondemnorStake_ExtraDmg`, `HeavyGravCannon`, `DestroyTheWitch`). `execute_normal_like` n'a que 2 routes live : (i) splash Psyker — **aucun** `lineup` n'est à la fois `Psyker` et porteur d'un des 5 (intersection VIDE sur les traits gameconfig) ; (ii) on-appearance d'un SUMMON — un summon ne porte que SES PROPRES traits dérivés (ground truth `test_summon_trait_effects_live` : `Diminutive`/`BigTarget` seedés depuis la config du SUMMON, pas du summoner), et aucun summon du pool ne porte l'un des 5. ⇒ **non dispatchable en port live-validé** ; le porter serait spéculatif | `engine/runner/operations/damage_ops/normal_like.py` | **1 effet** — rouvrir dès qu'un porteur d'un des 5 devient Psyker, ou qu'un summon d'un porteur hérite du trait |
| ~~**R8**~~ | ~~`--hp-target` remet `Armor`/`FixedArmor` à 0, et DEUX documentations le taisent~~ — **FERMÉ** par `3eee6c0`, cf. §5.1. Les deux supports le disent désormais, et le commit a AJOUTÉ le troisième que la fiche R8 ne connaissait pas : `--hp-player` a le MÊME effet | — | — | — | — | — |

### 4.b — Symptôme NOMMÉ (mécanique lue, pas encore chiffrée)

| # | Résidu | Symbole natif | Porteur / chemin en bataille | Fichiers | Taille |
|---|---|---|---|---|---|
| ~~**N9**~~ | ~~Le lot extra-dégât `IsCharging` modélisé par `has_moved`~~ — **FERMÉ le 2026-07-28** (`case-r32-ischarging-consumers.md`), avec **deux corrections de fiche**. (a) **`SmashaEad` n'a AUCUN nœud `IsCharging`** : son `CreateEffectDamageBonusForAttack` vaut `ForAddition(get_OwnerIsCaster & IsNormalAttack, ConfigVar(8))` — décompilé relu, xrefs de `DSLFactory$$IsCharging` à l'appui (les SEULS appelants du canal dégât sont `AvalancheOfMuscle` 1025, `FeederTendrils` 1197, `BlackRage` 1343). Le port n'y avait d'ailleurs jamais posé de gate `has_moved` : c'est son TRIGGER qui porte la condition de pas, déjà bakée à la matérialisation. (b) le biais unilatéral est **CHIFFRÉ** : `astraBullgryn` L50 mult 180 %, caster qui bouge vers une cible DÉJÀ adjacente — natif `[3336, 3158, 2479, 2533]`, port-avec-proxy `[3935, 3757, 3078, 3132]` = **+599/coup accordé à tort, sur les 4 coups** ; même écart en PRÉDICTION (natif 9636, proxy 12032). Les deux consommateurs sont rabattus sur `BattleQuery$$IsCharging`, COMBAT et PRÉDICTION, 3 régimes + 4 régimes bit-exacts. Absorbe `R32`. **Reste ouvert, séparé** : `BlackRage_ExtraDamage` (1343) — RE faite, gate disponible, port BLOQUÉ par un défaut du VECTEUR DE POSE (cf. `N10`) | `IdunBattle.Core.Services.BattleQuery$$IsCharging` ; `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` ; `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` (la purge) | astraBullgryn (AvalancheOfMuscle), tyranDeathleaper (FeederTendrils) — **HERO pool** | `engine/battle_query.py`, `engine/entities/effects/base.py` + `loki/extra_damage.py`, `engine/runner/damage_model.py`, `engine/playbook/{scene.py,prediction/_shared.py,prediction/normal_attack.py,prediction/abilities.py}` | — (clos) |
| **N10** | **NEUF (2026-07-28, case-r32)** — **`BlackRage_ExtraDamage` (1343) : le canal est prêt, le NIVEAU ne l'est pas.** Le mirror est lu (`ForAddition(get_OwnerIsCaster & IsCharging & IsNormalAttack, ConfigVar(8 = extraDmg, GetAbilityState, config@+0x60))`) et le gate `IsCharging` existe désormais. Ce qui bloque est AILLEURS : l'`AddEffect(1343, caster)` du `black_rage_tree` pose l'effet **sans propager le niveau d'ability de la source**, donc `ConfigVar(8)` s'indexerait au niveau 1. **MESURÉ** : contribution **18 par coup** (`extraDmg[1] = 10 × 180 %`) au lieu de **997** (`extraDmg[50] = 554 × 180 %`) — A/B live sur le delta de PV de la cible : `off(+charge) − off(−charge) = 52` sur 4 coups, là où le port juste vaudrait ~3 900. Porter le canal dans cet état livrerait une valeur FAUSSE, pas une valeur manquante. Débloqueur = `scale_from_source` du vecteur de pose (déjà utilisé par `Waaagh_ExtraDamage` 1100). ⚠ La fiche antérieure justifiait le non-port par « magnitude négligeable, extraDmg = [10, 12, 14, …] » : **FAUX**, c'était la tête du tableau (`[65] = 728`). Verrou : `test_ischarging_extra_damage_live.py::test_black_rage_effect_level_not_propagated` (il TOMBE le jour où le niveau est propagé — signal « porte le canal »). Écart tiers croisé sur le même vecteur, non lié au canal dégât : le `SetHealth(30 % MaxHealth)` du cast rend **56 871 live vs 60 000 offline** (`hp_max` 189 570 vs 200 000 sur un état rechargé) | `IdunBattle.Entities.Effects.Loki.BlackRage_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` ; `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` | `bloodDeathCompany` <<Lucien>> — **HERO pool** | `engine/runner/abilities/behaviours/effects.py` (`_source_scaling`, le débloqueur), puis `engine/entities/effects/loki/status.py` | **1 effet** (le débloqueur est dans le vecteur de pose, pas dans l'effet) |
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
| ~~**R30**~~ | ~~**Substrat MULTI-HEX**~~ — **FERMÉ le 2026-07-28** (`case-91-duty-eternal.md`, PR #91). La reformulation demandée par la passe précédente est faite, et son unique reste — `DutyEternal` (1158) hors `ABILITY_CLASSES` — est **porté et confronté live** (20 tests live, 6 vues rouges). Ce que le substrat R30 n'avait pas : **aucun PRODUCTEUR**. Le manque était nommable en trois points, tous lus au décompilé : (1) le flag **`SpawnUnitOptions+0x60`**, qui fait basculer `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` de « une unité PAR tuile » à « **UNE** unité sur `GetTileIds(tiles)` » — le SEUL producteur d'empreinte multi-hex du binaire ; (2) le **nœud DSL** `ThreeTileUnitSpawnShape` (R30 avait porté le sélecteur comme *fonction*, pas comme nœud d'arbre) ; (3) **`RemoveMachine`**, qui n'a rien à voir avec le multi-hex. **Deux résidus du `case-R30` §6 sont fermés avec** : le gate `HasTrait(0x418)` de `GetMovablePositionsFor` (il n'était pas porté faute de porteur du trait — `AddTrait(ActiveTarget, 0x418)` en crée un) et l'occupance par pied des nœuds DSL (`CanAddUnit` raisonnait sur `pos`). **Restent ouverts, inchangés** : `HasPowerup` dans `CorrectArea`, centre d'une empreinte à 7 (inexerçable — aucun producteur dans ce build), `MoveUnitOperation` mono-tuile (non confrontable : `Movement = 0`), poids BC `DislikeStartingTiles`. **Deux constats d'OUTILLAGE** en sont sortis, verrouillés par des tests : `abilityReason` rend `reasons: []` sur une cible-TUILE avec caster MACHINE (**aveugle** à la règle dynamique → l'oracle est le cast, `actionConsumed`), et `decisionView.mows` expose `usable: true` sur une MoW RETIRÉE (le projecteur lit `ActiveAbilityComponent`, que `RemoveMachineOperation` ne touche pas) | `…Loki.DutyEternalAbility$$ExecuteBehaviour` ; `SpawnUnitBehaviour$$Execute` (branche `+0x60`) ; `SpawnUnitBehaviour$$GetTileIds` ; `DSLFactory$$RemoveMachine` → `RemoveMachineOperation$$Execute` ; `DSLFactory$$AddTrait` → `AddTraitBehaviour` ; `MovementQuery$$GetMovablePositionsFor` | ultraDreadnought (**MoW du pool**) ; `AetherStride` (thousDaemonPrince, catalog_inject) — **toujours non exercé** | `engine/runner/abilities/{ultramarines,handler,attack_type}.py` · `behaviours/{summon,lifecycle,grants,context}.py` · `entities/selectors/{geometry,tiles}.py` · `runner/{components,operations/spawn}.py` · `services/movement_query.py` | — |
| ~~**R30 (ancien libellé)**~~ | ~~À REFORMULER — le SUBSTRAT est porté et confronté live~~ (`94b7118`, `case-R30-multihex-substrate.md`) : `UnitComponent.feet` (mirror `_feet`, `None` = 1 pied), `get_unit_feet`/`get_feet_count`/`get_main_tile`, occupance par pied dans `state.py`, `movement_query` complet (`is_valid_unit_feet_list`, `get_possible_tile_lists_from_movable_tiles`), `ThreeUnitSpawnTileShapeSelector`, `_load_feet` depuis `observeBattle`, portée sur EMPREINTE. Confronté N=1 et N=3 (18 assertions offline + 7 tests live, garde vue rouge : port sans substrat → distance **2** et refus, natif et port avec substrat → **1** et accord). **Les DEUX corollaires de l'ancien énoncé sont PÉRIMÉS** : `ai/utilities.py` ne dit plus « retour 0.0 jusqu'au câblage du poids + feetCount » — le trou `GetFeetCount` est comblé, seul le POIDS BC reste à 0. **Ce qui RESTE ouvert** : (1) `DutyEternal` 1158 est **toujours** absent d'`ABILITY_CLASSES` (vérifié : `1158 in ABILITY_CLASSES` = `False`) — le substrat est là, l'ability ne l'est pas ; (2) les 5 résidus nommés du `case-R30` §6 — `HasPowerup` dans `CorrectArea`, centre d'une empreinte à 7 (inexerçable, aucun producteur dans ce build), gate `HasTrait(0x418)` de `GetMovablePositionsFor`, `MoveUnitOperation` ne déplace qu'une tuile (non confrontable : le seul multi-hex du build a `Movement = 0`), poids BC `DislikeStartingTiles` non identifié | `…Loki.DutyEternalAbility$$ExecuteBehaviour` (`RemoveMachine` + `Spawn(ThreeTileUnitSpawnShape)`) ; `MovementQuery$$GetMovablePositionsFor` gate `HasTrait(0x418)` ; `TileExtensions$$HasPowerup` | ultraDreadnought (**MoW du pool**) ; `AetherStride` (thousDaemonPrince, catalog_inject) — **non exercé** | `engine/runner/abilities/ultramarines.py` + `handler.py` pour (1) ; `engine/services/{movement_query,spawn_tile_shape}.py` pour (2) | **1 ability** pour (1) — plus le sous-système multi-hex, qui n'est plus « le plus gros de la liste » |
| **R31** | **`PerformAIAttack` avec `moveAmount = null` : l'acteur n'APPROCHE pas** — `abilities/loki/summon.py::perform_ai_ability_unit_behaviour` attaque depuis la tuile COURANTE quel que soit `move_amount`. Le décompilé tranche : `…DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext` appelle `GenerateActionTiles(unit, 1, <d__6+0x34>)` (3ᵉ arg = le `Nullable<int>`, `null` = plage de déplacement NORMALE) puis `if (<d__6+0x30> /* allowMoveAction */) generators.Add(<tactic+0x58>)` = le `MovementActionGenerator`. ⚠ **`d__6` n'instancie qu'UN `ActiveAbilityActionGenerator` sur UNE seule ability** (celle du `Func<IEntity,int>` caché du behaviour), là où `d__5` itère toute la liste `tactic+0x60` : réutiliser `decide_and_apply` tel quel serait un FORK. **DISTINCT du rouge Waaagh** (`case-r21-summon-movement.md`), qui passait par `PerformAIAction`/`d__5` et dont la cause était la stat MOVEMENT non seedée sur un summon spawné offline — ce résidu-ci reste OUVERT | `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttack` ; `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` ; `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` | necroSpyder (ScarabSummon 1047), astraYarrick (ForwardSpotter 1143), + HunterOfSouls / TheArdentBlade_Trigger / AetherStride / CallInReinforcements — **pool** | `engine/runner/abilities/loki/summon.py`, `engine/ai/tactic.py`, `engine/ai/action_generators.py` | **1 sous-système** — manque-à-agir, jamais une attaque illégale |
| ~~**N1**~~ | **`ArcaneShield` — FERMÉ** (`case-n1-arcane-shield-vector.md`). Les deux affirmations de la fiche d'origine étaient FAUSSES et sont réfutées au décompilé : (a) le code cité (`prio = 0 if (own_fac == own_fac) …`, tautologie) n'a jamais existé ; (b) **retenir un allié NON-Chaos est CORRECT** — `SurroundingFriends` ne filtre ni sur la faction ni sur le trait Chaos, qui ne pèse qu'une pénalité de +1. Ce qui était RÉELLEMENT faux : **le vecteur** (`On(4)` au lieu d'`On(0x1c=ArrivedAtFinalTile)` ⇒ aucun bouclier quand Thaumachus finit son tour sans bouger) et **le modèle de classement** — le natif n'a AUCUN palier lexicographique, il trie par le **score ADDITIF** `Sum(3×distance, faction, chaos, owner)` où **la distance (poids 3) domine la faction (poids 1)**. Mesuré : sur 4 configurations, le tri historique se trompait de cible dans **2** (un non-Chaos à d=1 vaut 5, un ThousandSons à d=2 vaut 6) | `…ArcaneShieldAbility$$CreateTrigger` / `$$CreateBehaviour` / `$$Distance` / `$$Faction` / `$$Chaos` / `$$Owner` | thousSorcerer — **HERO pool** | `engine/runner/operations/triggers/loki/arcane_shield.py`, `…/dispatch/{registry,move_death}.py`, `…/turnflow.py` | **FERMÉ** |
| **N2** | **VALIDE** (relu à `bec119f`, puis **RE-ANCRÉ après #169**) — **Famille ATTACK en bounds-mode : cap SCALAIRE là où le natif cape les CELLULES** : `damage_ops/ability.py:368` : `execute_ability_attack` passe `_target_limits(..., is_special=2)` **inconditionnellement**, y compris à `is_attack_damage_op=True` (le seul `is_special=1` est `damage_ops/normal.py:360`). En bounds-mode la branche ATTACK de `_run_hits` (`damage_hits.py:240-249`) applique `roll = _limits_scalar(roll)` = cap SCALAIRE post-tirage ; le cap sur les CELLULES pré-tirage n'existe que sous `limits["is_special"] == 1` (`damage_hits.py:303-316`), atteint uniquement par `execute` et `additional_hits.py:146` | `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` vs `…$$CalculateDamageOperation` (`Math.Max(0, dmg − shieldPart)`) | pool | `engine/runner/operations/damage_ops.py`, `engine/runner/operations/damage_hits.py` | **1 effet** |
| **N16** | **NEUF (2026-07-28, case-ischarging-hits ; renomme de N13 au merge -- N13 etait deja pris par le terme de tuile de R1-b)** — **le canal COUPS n'est porté sur AUCUN de ses consommateurs de CHARGE.** Re-énumération des xrefs d'`IdunBattleLogic.Entities.DSLFactory$$IsCharging` : **16 CALL** (+2 DATA), pas « 12 autres » ; **8 canaux**, pas 4. Après le port de `1223` (`case-ischarging-hits` §6) **puis de `1032` (`case-n16-unstoppable-ferocity`)**, il reste **3 consommateurs confrontables non portés**. **Compte RE-DÉRIVÉ des 16 lignes du tableau `case-ischarging-hits-channel` §2**, et non reporté : 16 CALL − 3 canal DÉGÂT (#1-#3) − 2 `TacticalPrecision` (#4-#5, dont `GetIsChargingTrigger`) − 1 **1223 hits** (#6) − 1 **1223 crit** (#7, porté par `#184`/`N14`) − 1 **1032** (#9) − 2 NON PERTINENTS (#10 `ObeisanceGenerators` sans porteur, #15 `SabreOfSacrifice` npc+relique) − 2 triggers `AggressiveOnslaught` (#13-#14) − 1 `FeederTendrils` (#16, résidu `N15`) = **3** (#8, #11, #12). Chacun une tranche : `RedThirst_ExtraDamageAndHit` **1322** (`ForAddition(OwnerIsCaster & IsCharging(owner,target), ConfigConst(0x4e1, owner, 0x2b = extraHit))` = **+1 coup**) · ~~`UnstoppableFerocity_OwnerEffect` **1032**~~ **PORTÉ ET VALIDÉ LIVE** (`ForAddition(OwnerIsCaster & IsCharging(caster,target), Direct(GetNumberConstant(0x2b = extraHit) = 1))` ; porteur SUMMON `blackSmnBloodletter` amené par l'ACTIVE `Incursion` d'Archimatos — **un summon ne se pilote pas** (auto-activé par l'IA, `applyAction {kind:"ability"}` rend `mutated=False`), la validation passe donc par l'OBSERVATION des `changes` de l'`endturn` ; confrontation **bit-exacte** : CHARGE live 3285 = port 3285 (n=2) vs 1707 sans l'effet, ADJACENT live 1707 = port 1707 (n=1), généralisation `C1_25`/31337 live 6104 = port 6104) · `FragLance` **1475** (`EffectAdditionalHits.Create(OwnerIsCaster & IsNormalAttack & IsCharging, …, GetDamageProfile = Blast, ConfigConst(0x2f))` = une **attaque SÉPARÉE** de 1 coup Blast, pas un bonus de coups) · `BloodChalice_ExtraPiercing` **1369** (`CreateActiveCondition = IsCharging(owner,target)` — nœud UNIQUE ; l'effet lui-même n'existe pas offline, son poseur `BloodChalice` 1175 n'a pas de face COMBAT portée). **Le gate est disponible** (foyer `battle_query.is_charging` + `effects/base.py::is_not_charging`) et le contexte du canal COUPS le porte désormais (clé `is_charging` dans l'`att_hits_ctx`) : ce qui reste est le mirror de chaque effet | `IdunBattle.Entities.Effects.Loki.RedThirst_ExtraDamageAndHitEffect$$CreateEffectHitsBonusForAttack` ; `IdunBattle.Entities.Effects.Loki.UnstoppableFerocityOwnerEffect$$CreateEffectHitsBonusForAttack` ; `IdunBattle.Entities.Effects.Loki.FragLanceEffect$$CreateAdditionalHits` ; `IdunBattle.Entities.Effects.Loki.BloodChalice_ExtraPiercingEffect$$CreateActiveCondition` | 1322 → **SUMMON** `bloodSmnIntercessor` (summoner `bloodIntercessor` — pool) · 1032 → **SUMMON** `blackSmnBloodletter` (summoner `blackPossession` — pool) · 1475 → **SUMMON** `astraSmnDeathRider` (summoner `astraDreir` / `LeadingTheCharge` — pool) · 1369 → **`bloodSanguinary` HERO pool** | `engine/entities/effects/loki/hits.py` + `entities/effects/factory.py` (1322, 1032) ; canal `additional_hits` (1475) ; `engine/runner/abilities/bloodangels.py` (poseur de 1369) | **1 effet par ligne** — 4 tranches |
| ~~**N14**~~ | **FERMÉ 2026-07-28 (`case-ischarging-crit-channel.md`)** — le canal CRIT **n'était pas structurellement aveugle**, et c'est le point qui débloque tout : `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage(this, attaquant, cible, …)` passe **les DEUX entités** à `GetCritDamageBonusFromEffects`, qui construit lui-même son `IdunBattle.Entities.Abilities.AbilityEntities` (caster = owner = l'attaquant, target = la cible) avant d'évaluer le trigger de chaque `EffectBonus` par le slot `IdunBattle.Entities.Effects.BaseEffect$$CritDamageBonus`. `get_OwnerIsCaster`, `IsCharging(owner, target)` et `HasTrait(target, …)` y sont donc TOUS évaluables — le contexte manquait **côté port seulement**. Instrumenté en **UN point** : `AttackDamageOperation._crit_params` (la façade CRIT partagée des 3 vecteurs d'attaque, ce que `build_hits_board` est à l'axe COUPS) bâtit l'`att_ctx` ; les vecteurs ne transmettent que les identités du coup. Face CRIT de 1223 portée (`ConfigVar(0x42 = extraCritDmg)`, **rarity-scaled** contrairement à `extraHits`) et validée live à 3 régimes × 2 boards, avec les deux bornes forcées (`off`/`always`) qui rendent chaque MATCH probant. **Résidu NEUF ouvert par la fermeture : `N17`** (axe DÉFENSEUR du même canal) | `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateCritDamageBonus` ; `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects` / `$$CalculateCriticalDamage` / `$$GetCritDamage` | `spaceBlackmane` <<Ragnar>> — **HERO pool** | `engine/runner/operations/damage.py`, `engine/entities/effects/{base,__init__}.py`, `engine/entities/effects/loki/hits.py` | **LIVRÉ** — gardes : `test_ischarging_saga_crit_live.py` (8 tests), probe `probe_ischarging_saga_crit.py` |
| **N17** | **NEUF (2026-07-28, révélé en fermant `N14`) — l'axe DÉFENSEUR du canal CRIT n'est balayé par personne.** `crit_damage_bonus_from_effects` n'itère que les effets de l'ATTAQUANT, alors que le natif énumère aussi ceux d'autres entités : `IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$CreateCritDamageBonus` = `ForSubtraction(get_OwnerIsTarget, GetCritDmgReductionAmount(), AbilityOrEffect(0x5b8))` vit sur la **CIBLE**. Même famille : `TalismanOfRage_CritDamageReduction`, `NetherRealmCasket_CritDamageReduction`, `SupaCyborkBody_CritDmgReduction`. **NO-OP aujourd'hui** (aucune de ces classes n'est portée, toutes rendent `None`) — donc pas une régression, mais un axe entier absent. Le pendant CHANCE (`GetCritChanceBonusFromEffects` / `create_effect_crit_chance_bonus_for_attack()`) est resté SANS contexte pour la même raison qu'`N14` : aucun consommateur porté à ce jour. Débloqueur : symétrique exact de `N14` — un balayage défenseur au call-site + `att_ctx` sur la face CHANCE | `IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$CreateCritDamageBonus` ; `IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects` | porteurs = **reliques** (`R_*`), même famille que `SabreOfSacrifice` — **confrontabilité à établir** (`rl_duel.py` ne monte aucun équipement) | `engine/runner/operations/damage.py`, `engine/entities/effects/__init__.py` | **1 sous-axe** |
| **N15** | **NEUF (2026-07-28, case-ischarging-hits)** — **branche CHARGE de l'attaque normale de Deathleaper, jamais exécutée offline.** `IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour` est le SEUL consommateur d'`IsCharging` où le prédicat n'est pas un nœud d'arbre : le corps appelle son slot `Evaluate` (`+0x188`) puis, si `charging & WeaponProfile.get_IsMelee(weapon)`, exécute `ExecuteInformWeapon` + `ExecuteAtomic(Heal(owner, owner, ConfigVar(0x20 = hpToHeal)) + AddEffect(0x429 = 1065 Pinned, AbilityStateReference, target@0x178))` + `ExecuteNormalAttack` + `ExecuteTriggerAbilities` ; sinon l'attaque normale nue. Le port ne retient que le SECOND terme (`get_IsMelee`, recopié en gate `is_ranged` de `FeederTendrilsExtraDamageEffect`) : **ni le heal, ni la pose de `Pinned` sur la cible** ne se produisent. Deux opérations observables (PV du caster, effet sur la cible), sur un porteur du pool. `Pinned` (1065) et l'opération de heal sont déjà portés — il manque le VECTEUR | `IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour` ; `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteNormalAttack` | `tyranDeathleaper` — **HERO pool** (+ 6 variantes npc) | `engine/runner/operations/damage_ops/normal.py` (ou un hook d'attaque-normale par-unité), `engine/runner/abilities/` (module tyranides) | **1 ability** |
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

**Découverte COLLATÉRALE (gap NOUVEAU, orthogonal à R9)** — ~~`FuelledByFury` (passif d'`ultraTitus`)
n'est pas porté~~ — **FERMÉ le 2026-07-28 (#1323)**, sur les **DEUX étages**. Le diagnostic d'origine
était juste, et son chiffre aussi : le gap était bien un **ABSENT** (ni classe d'effet pour
`FuelledByFury_ExtraDamage` **1323** dans `entities/effects/factory.py`, ni entrée
`ABILITY_TRIGGERS["FuelledByFury"]`), et `+248/coup` = `round(extraDmg[L50] = 138 × 180 %)` est bien
la magnitude **PAR STACK** à ce rang (l'i2 « +153 » est `extraDmg[L65]` à multiplier 100 %).

- **étage COMPTEUR** —
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateTrigger`
  = `On(0xe = UnitPostAbility) & AreFriends(Owner@0x148, caster@0x160) & HasTrait(caster, 0x10 = Hero)
  & !HasTrait(caster, 0x419 = MachineOfWar) & IsActiveAbilityCountedAsUsed(false)` →
  `$$CreateBehaviour` = `If(HasEffect(Owner, 0x52b), IncreaseEffectLevel(+1, **sans cap**),
  AddEffect(0x52b))`. Le gate `IsActiveAbilityCountedAsUsed` est ce qui écarte l'attaque NORMALE — qui
  émet le MÊME `On(0xe)` — via `DSLFactory$$IsNormalAttack`, déjà porté (foyer unique
  `abilities/attack_type.py::is_normal_attack`), pas re-écrit.
- **étage MAGNITUDE** —
  `IdunBattle.Entities.Effects.Loki.FuelledByFury_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`
  = `ForAddition(get_OwnerIsCaster **seul**, GetCurrentExtraDamage())`, et
  `$$GetCurrentExtraDamage` (refcount 10 — c'est le corps PARTAGÉ dont `TerrifyingCrescendo` hérite)
  = `Multiply(ConfigVar(8 = extraDmg), EffectLevel)`. Aucun gate ranged/mêlée/normale ⇒ i2 « with ALL
  attacks ».
- **MESURÉ LIVE** (`probe_1323_fuelled_by_fury.py`, paire de régimes à MÊME attaquant / MÊME cible /
  élévation ÉGALE pour neutraliser le ×1,5 d'élévation) : compteur `0 → 1 → 2` sur deux actives
  alliées, port == live à chaque pas ; attaque normale de Titus rejouée bit-exacte **4/4 à fury = 0**
  ET **4/4 à fury = 2** ; delta de prédiction native `+1984` = `4 coups × 2 stacks × 248`, à l'unité.
- Gardes : `tests/engine/runner/test_fuelled_by_fury_live.py` (4 tests, fixture nommée
  `_fuelled_by_fury_regime.py`), **vues ROUGES par 3 mutations distinctes** (trigger désenregistré →
  `port=0 live=1` ; effet désenregistré → `−496/coup` ; facteur `EffectLevel` retiré → `−248/coup`).
- **Résidu nommé restant** : le facteur `TimesAbilityUsed(caster, ability) >= 1` du
  `left` d'`IsActiveAbilityCountedAsUsed` n'est pas observable offline (même substrat que
  `entities/formulas.py::TotalActiveAbilityUsed`). Il ne mord que sur les **2** `ActiveAbilityType` du
  HashSet statique `StaticBattleRules.ActiveAbility@+0x58` (`1118 DoctrinaImperatives`,
  `1189 CalibaniteGreatsword`) ; dégradation choisie = « l'ability compte ». Point de câblage unique :
  `triggers/loki/fuelled_by_fury.py::_times_ability_used`.
- **Toujours OUVERT, hors périmètre** : `FuelledByFury_CanRevive` (**1324**) — cf. backlog `#66-r2`.

Second candidat écarté : `darkaCompanion`, dont la BASELINE mismatche déjà (divergence pré-existante
du couple, non diagnostiquée ici).

### 4.c — Résidus d'OUTILLAGE et de HARNAIS (confrontés pour la première fois)

| # | Résidu | Constat au code | Fichiers | Taille |
|---|---|---|---|---|
| ~~**O1**~~ | ~~Aucune garde AUTOMATISÉE de synchro build ↔ `data/symbols/<HASH>` ↔ binaire chargé dans ghidra-mcp~~ — **FERMÉ** par `3eee6c0` : `scripts/python/symbols_sync.py` (neuf, 189 lignes) couvre les TROIS axes (binaire installé ↔ tables versionnées par sha256 ; cohérence interne nom-de-répertoire / `BUILD` / estampilles / en-tête Ghidra ; **ghidra-mcp ↔ tables**), est accroché au `SessionStart` (`session-start.ps1:26`, muet quand tout est synchrone, 1,3 s), et le défaut de `il2cpp_provenance` vise désormais `data/symbols/<HASH>/` au lieu des `data/il2cpp_*.tsv` supprimés. Serveur ghidra éteint = rapporté **NON VÉRIFIÉ**, ni succès ni échec. Vérifié EN ROUGE par son auteur sur 6 désynchronisations injectées. Cf. §5.1 | — | — | — |
| **O2** | **hors intersection** (`frida/host/ai-trace-store.ts`, `frida/host/router.ts`, `frida/hooks/features/ai-trace*` absents du diff — seul `ai-step/internals.ts` a bougé) — **Pas de drain à la demande des ai-traces** | `frida/hooks/features/ai-trace/state.ts:127-132` : `emit()` fait un `send({t:"ai_trace", …})` immédiat, **aucun buffer** côté agent. `frida/host/ai-trace-store.ts:62-84` écrit ligne à ligne dans `frida/data/ai-traces/<sessionId>-<iso>.jsonl` (docstring l.18 : « no in-memory aggregation, just write-through »). Routes existantes (`router.ts:788-834`) : `status` / `enable` / `disable` — **aucune route `drain`/`flush`/`consume`/`clear`**, aucun RPC de drain côté hooks. Les 8 consommateurs Python lisent le RÉPERTOIRE. **Finding annexe : `aiTraceStoreStatus` (l.100-114) n'est référencé par AUCUNE route ni aucun module — code mort** | `frida/host/ai-trace-store.ts`, `frida/host/router.ts`, `frida/hooks/features/ai-trace*` | **1 sous-système côté hooks** — ⚠ **exige rebuild + reinject**, donc à programmer quand l'atelier est vide |
| **O3** | **RÉSOLU — `case-o3-tile-effect-dynamics.md`** | L'énoncé d'origine était en partie faux : les timers de tuile ÉTAIENT décrémentés (`EndTurnOperation.execute` balaye TOUTES les clés de `by_unit`, tuiles comprises) et le gate `AreEqual(coverPatch, target)` de `LightCoverEffect` EST porté (A3, `d9d0e6c`). Le vrai trou, MESURÉ : (a) le décrément n'était pas clampé (`RemoveOneTurn` = `if (0 < Duration) Duration--`) et surtout (b) **rien ne RETIRAIT l'instance à 0** — `expired` n'est lu que par `active_effects`, alors que `has_effect` et `collect_effect_triggers` ne filtrent que `consumed` ⇒ un feu de tuile brûlait pour toujours (`(remaining, has_effect)` = `(-4, True)` au 6ᵉ tour). Natif : `EndTurnOperation$$RefreshEffects` itère TOUTES les entités-EFFET (aucune distinction unité/tuile), puis `RefreshEffectsOperation$$RefreshEffect` prend la branche retrait sur `EffectComponent$$ShouldBeRemoved` (`HasTurns && Duration == 0`). **+ transition d'ENTRÉE portée** : `LightCoverAbility` (`On(0x24=UnitPositionChanged_1)`, gate de traits `BigTarget/Vehicle/Mounted` lu au `.cctor`), câblée dans `after_move_triggers` ET `displace_triggers` | `engine/entities/effects_state.py`, `engine/runner/operations/triggers/tiles.py`, `engine/runner/operations/triggers/dispatch.py` | **fait** — reste hors périmètre : spawn/revive sur cover, autres tile-abilities d'entrée, `DespoiledGround` (#85, cf. case §6) |
| **O4** | **Résidus de PLACEMENT laissés par `case-130` SS5** | (a) **RÉSOLU, `case-o4a-maybe-trigger-rng.md`** : le nœud `MaybeTrigger` existait déjà (posé par `case-1203`) mais n'était CÂBLÉ qu'à un seul site ; PileIn restait DÉTERMINISTE (0 tirage) et `LetTheGalaxyBurn` roulait dans le mauvais ORDRE avec la mauvaise primitive. Câblé + branche `!CanUseRandom` (`99 < chance`) portée. Ancrage LIVE bit-exact sur PileIn : **4 datapoints, port 4/4 sur le compte de `genrand_int32` ET le nombre de spawns, port d'avant 0/4** (succès du gate : live 5 / port 5 / avant 4 ; échec : live 1 spawn 0 / port 1 spawn 0 / avant 4 spawn **1** = un grot fantôme) ; (b) **RÉSOLU, `case-155-swamp-fork-maybetrigger.md`** — le fork `_PLACEMENT_TERRAIN_EFFECTS` vs `TERRAIN_TILE_EFFECTS` reposait sur une **erreur de nature** : la RE des DEUX boucles de `IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` montre que le −25 vient du canal DYNAMIQUE (Loop1 — `ThornsBlockMovementAbility$$CreateBehaviour` = `AddStaticStatModifierEffectToOwner(0xb, …)`, l'effet est posé SUR la tuile) alors que le +9 DryBush vient des abilities HÉBERGÉES (Loop2 — `LightCoverAbility$$CreateBehaviour` pose son effet sur les UNITÉS). Foyer unique dans `utilities/tile.py` (`TERRAIN_HOSTED_ABILITIES` = Loop2 jamais dédupliqué ; `TERRAIN_TILE_OWNED_EFFECTS` = repli Loop1 dédupliqué contre le canal dynamique), 8 call-sites branchés, table de placement supprimée. Mesuré live : régimes hydraté et non hydraté CONVERGENT (même tri, même tuile, = live) ; témoin sans le −25 → le port place sur la Swamp ; (c) feuilles `Tile(7)` gatées sur l'unité dans le tri de placement (ctor replié par le linker, aucun scénario mesuré ne les réveille) ; (d) on-appearance `PerformAIAttackFromCurrentPosition` du grot SquigHound : écart **CONSTANT de 4 `genrand_int32`** mesuré sur ce vecteur (MC1_67/777 et C2_37/31337), étranger au placement | `engine/runner/operations/triggers/dispatch.py`, `engine/runner/operations/spawn.py`, `engine/utilities/tile.py`, `engine/runner/damage_model.py` | **1 effet chacun** ; (a) est le plus large (touche tout gate `Maybe`/`chance` du DSL) |
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
  étage d'ARRONDI quand la %-list est vide sur les vecteurs restants (= R6, tag mixte).
  (~~**N4**~~ **FERMÉ** 2026-07-28 par `[opus]` #208 — cf. §4.f : la question « quel stade natif
  REFUSE » était mal posée, il n'y a pas de refus.)

### 4.f — NON CONFRONTABLES

| Item | Ventilation des porteurs | Verdict |
|---|---|---|
| **29 actives NO-OP** (§1) | 21 **npc-only** + 8 **summon-env** (posés par `EnvFactionSummons:<Faction>` / `ATemptingTrap`, qu'aucune unité jouable ne porte) | **NON CONFRONTABLE** — ne pas y envoyer d'agent |
| **1192 NovaBoost / 1194 NovaShield** (§2) | `tauBossRiptide` = **npc** | **NON CONFRONTABLE** |
| **4 overlays de R15** (1093, 1215, 1216, 1217) | tous **npc** | **NON CONFRONTABLE** |
| **`Impervious` (28) / cap boss `0x5d4`** | tous les porteurs sont des **boss npc** | **NON CONFRONTABLE** |
| **`ObeisanceGenerators` (1121, effet 1128)** — consommateur d'`IsCharging`, face COUPS **DÉFENSEUR** | **AUCUN porteur** : balayage des **669** unités (lineup 123 + npc 481 + summons 65) — zéro `activeAbilities`/`passiveAbilities`, zéro `traits`, zéro `relicAbilities`, zéro item. Le nom n'existe qu'aux **2** emplacements de définition du gameconfig (`/units/abilities/ObeisanceGenerators`, `/units/abilityPowerModifiers/ObeisanceGenerators`) | **NON PERTINENT — donnée enregistrée mais MORTE.** Le canal natif existe (`ForAdditionWithMinimum(OwnerIsTarget & IsCharging(caster, owner) & IsMeleeAttack, ConditionalAmount(HasTrait(caster, 2), −c(0x4b), −c(0x2c)), min 1)`) mais personne ne le porte en bataille. Ne pas y envoyer d'agent (`case-ischarging-hits` §4) |
| **`SabreOfSacrifice` (1478)** — consommateur d'`IsCharging`, face TRIGGER | **npc + relique** : `/units/npc/astraNpcDreir/relicAbilities[0]` et `/items/R_Crit_SabreOfSacrifice/abilityId`. `astraDreir` (le hero du pool) ne la porte **pas**, et `rl_duel.py` ne monte aucun équipement (`relic` : 0 occurrence) | **NON PERTINENT** — hors du domaine confrontable du runner, pas « bloqué » (`case-ischarging-hits` §4) |
| ~~**N4 — stade natif du refus `TerminatorArmour` / `Pinned`**~~ **FERMÉ 2026-07-28 (#208)** | blackAbaddon / deathTyphus / blackObliterator = **pool** | **RÉSOLU, et la QUESTION était mal posée : il n'y a jamais eu de refus.** `AddEffectOperation$$Execute` aboutit, `EntityIsImmuneToEffect` rend `false` — le natif POSE `Pinned` et le laisse INERTE via `PinnedEffect$$CreateActiveCondition`, évaluée par `RefreshEffectsOperation$$ShouldBeActive` (flag `EffectComponent.IsActive @+0x5c`). Le décompilé disait donc juste depuis le début ; c'est l'OBSERVABLE qui trompait, parce que `decisionView` DROPPE par défaut les effets inactifs. **Instrument : `decisionView { includeInactive: true }`, déjà livré par `d9d0008` et jamais utilisé** (`probe_208_pinned_inactive.py`). Fix : collapse défait + `unit_state` des `CreateActiveCondition` à foyer UNIQUE (`runner.components.unit_state_for_effects` / `Scene.unit_state`). Cf. `case-224-effect-immunity-gate.md` §4/§4bis |

### 4.g — COMPTE NET des entrées OUVERTES après cette passe

| Section | Ouvertes | Détail |
|---|---|---|
| §4.a — symptôme MESURÉ | **5** | R4 · R6 · R7 · **N11** (neuf 2026-07-28, capteur `turnsFinished`) · **N13-b** (neuf 2026-07-28, registre `TRIGGERED_MOVE_PLAYBOOKS` à 7/84 + kit déclenché OFFLINE sans traits/reliques — révélé en fermant `N13`) — (~~**R1-b**~~ **FERMÉ** 2026-07-28, `case-r1b-move-tile-sweep-order.md` : l'ordre est `[origine] + aiMovableTiles`, et le « tie » qui le disait régressif était un ARTEFACT du port — remplacé dans le compte par `N13`, le résidu qu'il a révélé, lui-même **FERMÉ** 2026-07-28 (`case-n13-tile-term-triggered-playbooks.md`) et remplacé par `N13-b` ; ~~N7~~, ~~N6~~ **FERMÉS** #174 ; ~~**R32**~~ **FERMÉ** 2026-07-28, absorbé par `N9` ; ~~**R33**~~ fork `is_overkill` **NÉ ET FERMÉ** le 2026-07-28, #178 — il n'a jamais compté comme ouvert ; ~~**R33-b**~~ les 3 champs du `DealDamageInfo` **NÉ ET FERMÉ** le 2026-07-28, `case-r33-overkill-isoverkill-args.md` — il n'a jamais compté comme ouvert non plus ; ~~**N8**~~ **FERMÉ** 2026-07-28, `case-n8-owner-has-finished-min-turns.md` — remplacé dans le compte par `N11`, le résidu qu'il a révélé ; ~~**N12**~~ ordre `On(0x17)` vs `RefreshEffects` **NÉ ET FERMÉ** le 2026-07-28, `case-n8b-endturn-order.md` — il n'a jamais compté comme ouvert) |
| §4.b — symptôme NOMMÉ | **11** | R12 · R13 · R15 · R17 · R19a · R25 · R26 · R27 · N1 · N2 · **N10** (neuf 2026-07-28, niveau non propagé de `BlackRage_ExtraDamage`) — (~~**N9**~~ **FERMÉ**, case-r32 ; ~~**R30**~~ **FERMÉ** 2026-07-28, case-91) |
| §4.b — symptôme NOMMÉ | **15** | R12 · R13 · R15 · R17 · R19a · R25 · R26 · R27 · R30 (reformulé) · N1 · N2 · **N10** (neuf 2026-07-28, niveau non propagé de `BlackRage_ExtraDamage`) · **N16** · **N15** (neufs 2026-07-28, `case-ischarging-hits` — canal COUPS de charge non porté, branche charge de `FeederTendrils_NormalAttack`) · **N17** (neuf 2026-07-28, axe DÉFENSEUR du canal CRIT — révélé en fermant `N14`) — (~~**N9**~~ **FERMÉ**, case-r32 ; ~~**N14**~~ **FERMÉ** 2026-07-28, `case-ischarging-crit-channel.md` : le canal CRIT n'était aveugle que CÔTÉ PORT — remplacé dans le compte par `N17`, le résidu qu'il a révélé) |
| §4.c — outillage / harnais | **4** | O2 · O4 (b, c, d) · O5 · **O7** |
| **Total résidus NOMMÉS** | **21** | dont **6 relus au code cette passe**, **8 hors intersection**, **4 neufs (dont N7 déjà fermé)**, **1 reformulé** |
| §4.d — veille | 13 | **non re-confrontés** (aucune colonne Fichiers, cf. l'encadré du §4.d) |
| §4.f — NON CONFRONTABLES | 4 lots | hors compte : 29 actives npc/summon-env, 1192/1194, 4 overlays R15, `Impervious` (~~**N4**~~ **FERMÉ** 2026-07-28, #208 — il n'y avait pas de refus à expliquer) |

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
   l'**ORDRE** du sweep — porté, +1 `stay` sur 2 couples, 0 régression sur 5. ~~**Reste R1-b**~~ —
   **R1-b est FERMÉ à son tour** (`case-r1b-move-tile-sweep-order.md`) : l'`OrderedSet` porte l'ordre
   d'INSERTION du pathfinder, `[origine] + aiMovableTiles` à l'identique (confirmé LIVE sur le natif,
   2 couples / 21 tuiles / 0 écart), et l'`ExceptWith` de la fiche était un **`UnionWith`**. Le
   « tie 192.851 » qui rendait cet ordre régressif est un **artefact du port** — d'où **`N13`** — lui-même **FERMÉ** le 2026-07-28 (`case-n13-tile-term-triggered-playbooks.md` : le trou n'était pas une feuille manquante mais le REGISTRE de la feuille dispatcher `TriggeredAbilities(2)`), laissant **`N13-b`**.
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
   seule des 16 abilities MoW à en avoir une). ~~**R30 multi-hex**~~ **FERMÉ** (`case-91-duty-eternal.md`,
   2026-07-28) : le substrat (`94b7118`) n'avait **aucun producteur** — le manque était le flag
   `SpawnUnitOptions+0x60`, le nœud DSL `ThreeTileUnitSpawnShape` et `RemoveMachine`. `DutyEternal`
   1158 est au registre, avec ses deux littéraux, et 2 des 5 résidus §6 sont fermés avec.
   (~~O3 dynamique des effets de tuile~~ : **fait**, `case-o3-tile-effect-dynamics.md`.)
10. ~~**O4 (a) `MaybeTrigger`**~~ **FAIT** (`case-o4a-maybe-trigger-rng.md`) — le comptage RNG d'un gate
    `Maybe`/`chance` est désormais confrontable, et O6 est fermé avec. Ce que la mesure avait
    **découvert** et laissé ouvert est désormais une entrée à part entière : **N8** (seed de
    `state.turn_counts` + `OwnerHasFinishedMinTurns` PER-UNITÉ).

~~**Ne PAS dispatcher `N4`**~~ — **N4 est FERMÉ (#208, 2026-07-28)**, et sa leçon vaut au-delà du cas :
le décompilé n'a jamais été en défaut ; c'est l'OBSERVABLE qui l'était. Avant de classer un item
« que le décompilé ne tranche pas », vérifier que le CANAL DE MESURE ne filtre pas la donnée
cherchée (`decisionView` droppe les effets inactifs, `includeInactive: true` les rend).
**Ne PAS dispatcher O2 ni O7** tant que l'atelier n'est pas vide (rebuild + reinject). O7 est le plus
urgent des deux : il **corrompt silencieusement** tout runner portant une MoW, et la parade actuelle
(runner jumeau) est un contournement de test, pas un correctif.

---

## 7. Collisions entre agents concurrents

| Fichier | Qui le touche | Risque |
|---|---|---|
| `engine/runner/abilities/handler.py` | **tout** port d'ability (gisements 1 et 2) | **ÉLEVÉ** — conflit textuel garanti si 2 agents portent en parallèle. Trivial (2 lignes), mais à résoudre par l'auteur au rebase |
| `engine/runner/operations/damage_ops/` (**PACKAGE depuis #169**) | R4 + R6 + R7 (`normal_like.py`), N2 (`ability.py`), R19a (`_channel.py`) — R9 **fermé** | **RETOMBÉ À FAIBLE** — la scission a séparé les 5 résidus en 3 modules disjoints : `normal_like.py` (R4/R6/R7, à sérialiser entre eux), `ability.py` (N2), `_channel.py` (R19a). N2 et R4 peuvent désormais partir **ensemble**, ce que l'inventaire interdisait |
| `engine/runner/snapshot.py` | ~~N7~~ (**FERMÉ**, PR #155), ~~N8~~ (**FERMÉ** 2026-07-28 — le seed manquant n'était pas `turn_counts`), **N11** (seed `turns_finished`, BLOQUÉ tant que le capteur n'existe pas), R30 (`_load_feet`, posé) | **FAIBLE** — N11 reste seul sur ce fichier, et il n'y touche qu'APRÈS l'ajout du capteur Frida |
| `engine/runner/operations/damage_hits.py` | R4, N2, R26 | **ÉLEVÉ** — sérialiser |
| `engine/runner/abilities/behaviours/summon.py` | ~~R20~~ (**FERMÉ**, PR #152) | — |
| `engine/ai/state_bridge.py` | ~~R1~~ (FERMÉ), R15 | FAIBLE — R1 a touché `_plans_for_unit` (ordre) + `build_from_state` (champ `action_tiles`). (R14 est FERMÉ et n'a PAS touché cette fonction : le chemin MoW vit dans `engine/ai/{tactic,context}.py`.) |
| `engine/ai/{context,action_generators}.py`, `engine/playbook/noncomparable/_base.py` | ~~R1~~ (FERMÉ), ~~R1-b~~ (FERMÉ 2026-07-28 — `_sweep_tiles`/`_action_utility`/`_best_attack` re-imbriqués) | FAIBLE — plus aucun résidu ouvert sur ce fichier. ~~`N13`~~ **FERMÉ** 2026-07-28 ; son successeur `N13-b` vit dans `engine/playbook/friends_in_range.py` + `engine/ai/state_bridge.py`. ⚠ N13 a TOUCHÉ `engine/ai/context.py` (méthode `live_triggered_ability_ids`) : conflit possible avec un port MoW |
| `engine/runner/abilities/behaviours/combat.py` | R19a | MOYEN (R28 fermé) |
| `engine/runner/operations/triggers/dispatch/` (**PACKAGE depuis #169**) | R12 (`registry.py` + `move_death.py`), R13 (`registry.py`), ~~N8~~ (`turn.py`, **FERMÉ** 2026-07-28), tout vecteur d'event neuf | **FAIBLE** — même effet que ci-dessus : R12/R13 vivent dans `registry.py`, le gate PileIn dans `turn.py` |
| `engine/runner/operations/turnflow.py` | ~~N8~~ (`_bump_turns_finished`, **FERMÉ** 2026-07-28), ~~N12~~ (ordre `On(0x17)` vs `RefreshEffects`, **NÉ ET FERMÉ** 2026-07-28) | **FAIBLE** — plus aucun résidu ouvert sur ce fichier ; l'ordre des 5 étapes d'`EndTurnOperation$$Execute` y est désormais mirroré 1:1 |
| `engine/runner/operations/effects.py`, `engine/entities/effects/factory.py` | N5, R9 (R16 **fermé**) | MOYEN |
| `engine/runner/abilities/<module>.py` | gisement 3 (1 lot par module), 1 port par faction | FAIBLE — deux modules différents ne se croisent pas |
| `engine/entities/effect_type.py` | tout effet neuf | FAIBLE (ajouts en fin de liste) |
| `docs/rl/combat-ability-coverage.md`, `kit-coverage.md`, `passive-ability-coverage.md` | régénérés par les audits | **ne jamais fusionner un conflit** : régénérer (`audit_*.py`) |
