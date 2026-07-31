# case-302 tranche 4 — la POPULATION complete des abilities a cible TUILE

Tranche 4 de `case-302-route-cible-tuile.md` §7. **Une MESURE, pas un port.**

Les tranches 1 a 3 ont porte la route generique tuile et ses deux premiers membres
(`1169 PlagueburstMortar`, `1148 DaemonicOrdnance`). Leur inventaire ne lisait le bit
`TargetingRule.TargetIsTile` que sur les abilities **deja portees** dans `ABILITY_CLASSES` — un
sous-ensemble. Cette tranche lit le bit sur **toute** la population enregistree par le jeu, et dit
pour chacune si sa face DECISION a une route.

**Etat : MESURE LIVREE.** Probe : `scripts/python/probe_302_4_tile_target_population.py`
(`scan` = ghidra-mcp -> `logs/`, `report` = 100 % offline depuis ce brut).
Tables : `docs/rl/case-302-4/tile-target-population.tsv` et `.json` (contrat machine).

⚠ Tous les chiffres de cette fiche sont RE-DERIVABLES par `report`. Les citer de memoire est
exactement ce que la tranche corrige — ils se periment des qu'une ability entre au registre.

---

## 1. Ou vit la population, et pourquoi c'est ELLE le denominateur

`IdunBattle.Core.Services.AbilitiesDatabase$$Init` appelle
`IdunBattle.Core.Services.AbilitiesDatabase$$InitializeActiveAbilities`, qui remplit un
`Dictionary<ActiveAbilityType, Func<AActiveAbility>>` — une entree par ability active, chacune
pointant sur une lambda `...AbilitiesDatabase.u003Cu003Ec$$u003CInitializeActiveAbilitiesu003Eb__27_N`
qui fait exactement `new <X>Ability()`.

Ce dictionnaire n'est pas *un* index parmi d'autres : c'est **le seul**.
`IdunBattle.Core.Services.AbilitiesDatabase$$GetActive(abilityType)` fait
`TryGetValue` dessus et, **en cas d'echec, journalise puis rend `new NoneAbility()`** — lu au
decompile. Une valeur d'`ActiveAbilityType` absente du registre n'a donc aucun comportement propre
dans une bataille.

⇒ Le denominateur pertinent est **le nombre d'entrees de ce registre**, pas le nombre de membres de
l'enum. Les deux comptes sont rendus separement par le probe (`--- DENOMINATEUR ---`), avec les
valeurs d'enum sans entree listees, precisement pour que l'ecart ne se lise pas comme une perte.

### Le mapping `id -> classe`, et pourquoi il est VERIFIE et non suppose

Le decompile de `InitializeActiveAbilities` ne nomme pas les lambdas : il montre, par entree, le
champ de cache `<>c.<>9__27_N` (a `<>c statics + 8 + 8*N`, le slot 0 etant le singleton `<>9`) puis
le `Dictionary.Add` de l'id. La relation `offset <-> N` est donc **affine**, et le report la
**re-derive puis la CONTROLE** : il exige que le nom de la classe construite par `b__27_N` coincide
avec le nom de l'`ActiveAbilityType` de l'entree (`<Nom>Ability`). Sous le seuil de concordance, le
report **refuse de conclure** — un decalage d'un cran renommerait silencieusement tout l'inventaire.

---

## 2. Ou vit le masque, et lequel des deux jeux d'options decide

`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, targetingOptions, abilityAttackType)`
installe **DEUX** structs `TargetingOptions` de 0x40 octets :

| champ | contenu | qui le lit |
|---|---|---|
| `this+0x70` | la struct passee par le ctor de la sous-classe | `AActiveAbility$$GetValidTargets`, `get_TargetingOptions`, `get_IsSelfCasting` |
| `this+0xb0` | le `Nullable<TargetingOptions>` du slot virtuel `GetTargetingOptionsForContinue`, **ou** la meme struct si le Nullable est vide | `get_TargetingOptionsForContinue` / `GetInvalidTargetReasonForContinue` |

`AActiveAbility$$GetValidTargets` ne touche que `this+0x70` (lu en entier au decompile) : **c'est ce
champ, et lui seul, qui decide du DOMAINE de ciblage**. Le second jeu ne concerne que le mode
« continue » d'une ability multi-etapes. Le masque cherche est donc `this+0x70 + 0x28` = `Rules`,
et `TargetIsTile` en est le bit 6 — exactement ce que rend
`IdunBattle.Core.Services.TargetingOptions$$get_IsTileTargeting` (`*(byte*)(this+0x28) >> 6 & 1`).

`AActiveAbility$$SetConfigValuesInTargetingOptions`, appele avant chaque lecture, ne touche que
`options+0x10` (la portee `Nullable<int>` lue de la config) : **il ne modifie jamais `Rules`**. Le
masque est donc entierement decide au ctor, statiquement.

---

## 3. SIX formes de construction du masque — pas deux, pas quatre

La tranche annoncait deux pieges. Le balayage exhaustif en a fait apparaitre **six formes**, toutes
presentes dans ce build, et le compte de chacune est re-derive par le probe :

| forme | ce que le ctor fait | masque effectif | occurrences / 257 |
|---|---|---|---|
| **litteral** | `TargetingOptions..ctor(this, isSelfCasting, range, forceMeleeTarget, RULES, dynCaster, dynTarget)` | `RULES`, 5e argument | **112** |
| **copie statique** | aucun appel : recopie les 0x40 octets d'un champ statique de `TargetingOptions`, passe la copie a `AActiveAbility$$.ctor` | la constante ecrite par `TargetingOptions$$.cctor` a `<preset>+0x28` | **118** |
| **preset + flags** | `..ctor(this, template, additionalRules)` | `template.Rules \| additionalRules` | **18** |
| **preset seul** | `..ctor(this, template)` — copie PURE, aucun flag ajoute | `template.Rules` | **5** |
| **fabrique** | `TargetingOptions$$Custom{Idun,Loki}NormalAttackOptions` / `$$SelfCastIfEnemyInCustomRangeOptions` remplissent la struct | selon la fabrique (voir §4) | **3** |
| **inline** | la struct est ecrite champ par champ sur la PILE, sans ctor ni preset (`...Loki.ChronometronAbility$$.ctor`) | le qword ecrit a `<base de pile> + 0x28` | **1** |

Le piege central tient toujours : **le litteral visible n'est pas le masque**.
`...Loki.TheQuickeningAbility$$.ctor` combine le preset `TargetingOptions statics+0x200` avec
`0x806000000` — le bit 6 vient du PRESET. Symetriquement,
`...Loki.Loki_NormalAttackAbility$$.ctor` ne passe par aucun ctor : son masque `0x4002` est celui du
preset `+0x00`.

**Les presets ne sont pas interchangeables** — le probe lit les **16** dans
`TargetingOptions$$.cctor` et publie la table (`presets` du JSON) ; elle coincide exactement avec
celle relevee a la main par `case-217` §« Recette du balayage », ce qui est un controle croise
independant. C'est pourquoi la regle est de lire **ability par ability**, jamais de generaliser.

### Deux pieges d'OUTILLAGE, mesures pendant cette tranche

- **Le decompilateur rend un immediat 64 bits comme une REFERENCE.** `...Loki.DeathScreamAbility$$.ctor`
  affiche `RULES = &LAB_180004000`. Lecture des octets : `48 b8 00 40 00 80 01 00 00 00` =
  `mov rax, 0x180004000` puis `mov [rsp+0x20], rax`. Le masque **est** `0x180004000` ; sans cette
  verification l'ability ressortait `not_measurable`.
- **`TargetingRule.TargetIsTile` vaut le MASQUE `0x40`, pas l'index 6.** Le confondre fait
  `(rules >> 64) & 1 == 0` pour tout le monde : un inventaire VIDE qui se lit « rien a signaler ».
  Mesure : le controle croise rendait `0` accord sur tout le registre du port avant correction.

---

## 4. Le compte VENTILE — et ce qui n'a PAS pu etre lu

### 4.1 Denominateur (re-derive, pas cite)

| | valeur |
|---|---|
| membres distincts d'`ActiveAbilityType` dans le dump du jeu | **260** |
| fabriques `b__27_N` | **257** |
| **entrees du registre natif** (le denominateur) | **257** |
| valeurs d'enum SANS entree de registre | **3** — `1079`, `1130`, `9999` : `GetActive` leur rend `NoneAbility` |
| entrees de registre sans valeur d'enum | **0** |
| registre COMBAT du port (`ABILITY_CLASSES`) | **98** — se perime a chaque port ; le probe le relit |

### 4.2 Etat de lecture du masque — TRI-ETAT, jamais un zero

| etat | compte | ce qu'il dit |
|---|---|---|
| `measured` | **255** | le ctor (ou un ctor de base suivi) expose l'une des six formes |
| `measured_partial` | **2** | base lue, `extraRules` ILLISIBLE -> le masque est un **MINORANT** |
| `not_measurable` | **0** | — |
| `absent` | **0** | — |

Les **2** partielles sont `12 NobleCharge` (fabrique `CustomIdunNormalAttackOptions`, base `0x4000`)
et `1076 MV71SniperDroneSquadAttack` (fabrique `CustomLokiNormalAttackOptions`, base `0x4002`). Ces
deux fabriques font `Rules = <preset> | extraRules`, et `extraRules` transite par un registre que le
decompile de l'APPELANT n'expose pas. Le bit 6 est absent de leur base :
**leur appartenance a la population est INDETERMINEE**, pas negative. Les lever demande de lire
l'assembleur de l'appelant (le registre charge avant le `call`), ou un `abilityTargets` live.

> La 3e fabrique, `SelfCastIfEnemyInCustomRangeOptions`, ecrit `Rules = 0x4000` en dur : son unique
> appelant (`1000 GauntletsOfUltramar`) est donc `measured`, pas partiel.

Le motif qui produisait la majorite des `not_measurable` au premier passage etait la
**deduplication IL2CPP** et un filtre de nom trop etroit de ma part — deux causes, distinguees :

- `...Loki.GenericAddEffectToOwnerAbility$$.ctor` appelle un corps nomme
  `Unity_Services_Core_Threading_Internal_UnityThreadUtilsInternal___ctor` (dedup) — le probe suit
  la chaine de ctors de base tant qu'elle est NOMMEE ;
- la base de `...Loki.SwoopingHawkAbility` s'appelle `DiveAttackAbilityBase` : exiger le suffixe
  `Ability` la rendait invisible, et ses deux heritieres (`1064`, `1091`) ressortaient
  `not_measurable` alors que leur masque est lisible **un cran plus haut**. Meme cause pour les
  deux entrees `absent` : `...Active.TestTargetAndAdjacentAttack` et `...Active.TestTileAttack` ne
  portent pas « Ability » dans leur nom de classe.

---

---

## 5. LE LIVRABLE — les 41 abilities a domaine TUILE, et leur route de DECISION

**41** des 257 entrees du registre portent `TargetIsTile`. Le detail par ability (masque, forme,
porteurs, route) est dans `docs/rl/case-302-4/tile-target-population.tsv` — la table fait foi ; ce
qui suit en est la synthese.

| | compte |
|---|---|
| portant `TargetIsTile` | **41** |
| dont la route emet une **cible tuile** (`ctx.tile_id_by_pos`) | **9** depuis #343 — 1092, 1096, 1121, 1148, 1151, 1166, 1169, 1194, 1197 |
| dont une route existe mais n'emet PAS de cible tuile | **0** (etait 2 — 1166, 1194 ; cf. §5.2) |
| **sans AUCUNE route de decision** | **32** |
| au registre COMBAT du port (`ABILITY_CLASSES`) | **19** — exactement les 19 de `case-302` §4 |
| **hors** registre COMBAT | **22** |

> Le recoupement des 19 est la validation la plus forte de ce balayage : l'inventaire manuel du
> §4 de `case-302` (relu ability par ability par les tranches qui les ont fait entrer) et ce
> balayage automatique donnent **la meme liste**, sans exception.

### 5.1 Les 32 sans route, ventilees par PORTEUR

La gate de confrontabilite du depot exige de dire QUI porte. Ventilation depuis le gameconfig
(5 voies d'attribution, `unit_map`) :

| porteurs | compte | ids |
|---|---|---|
| au moins un `lineup` | **18** | 1017, 1026, 1057, 1087, 1112, 1116, 1142, 1145, 1152, 1158, 1159, 1188, 1201, 1208, 1209, 1213, 1219, 1231 |
| `summons` (+ npc) | **2** | 1011, 1018 |
| `npc` seulement | **3** | 1094, 1174, 1193 |
| AUCUN porteur | **9** | 1083, 1085, 1134, 1135, 9009, 9012, 9016, 9017, 9018 |

⚠ **Cette colonne n'est PAS une gate de spawnabilite.** Le `kind` du gameconfig ment sur ce point :
la gate HERO/MoW est la presence dans `rl_duel.py build --list-pool`, et une absence du pool se
leve par injection catalogue (`case-92` §6). Un porteur `summons` s'amene par son summoner. Un item
dont tous les porteurs sont `npc` n'est pas « bloque », il est **NON PERTINENT**. Les **9 sans
porteur** sont pour l'essentiel des abilities de test (`Test*`, ids 90xx) et quatre ids Ork/Eldar
sans unite dans le catalogue courant.

### 5.2 Les 2 routes qui n'emettaient PAS de cible tuile — RESOLU (#343)

`1166 AberrantHypermorph` et `1194 NovaShield` rendaient `{"target": None, ...}`. **Le natif emet
TOUJOURS une cible tuile** (`element+0x10` du selector, passe a
`IdunBattle.AI.ActionGenerators.UnitAction$$.ctor`) : c'etaient deux BUGS, et la degradation ne
perdait pas seulement la cible — sans cible ni deplacement, l'action retombait sur
`FinishUnitTurnMessage`, donc le moteur ne castait PAS l'ability. Corrige + confronte live (2 bras
par item, accord sur ability + cible tuile + position). Detail :
**`docs/rl/case-343-cible-tuile-emise.md`**. Le compte du tableau ci-dessus passe donc a **9**
routes emettant une cible tuile, **0** route muette.

### 5.3 Ce que la mesure a corrige au passage — un masque FAUX au registre

Le controle croise « masque decompile vs `TARGETING_OPTIONS` du port » a rendu **98 accords, 0
desaccord** (re-joue apres rebase : la 98e ability entree entre-temps concorde elle aussi) — mais
seulement APRES correction de `1029 Drachnyen`, qui portait `TargetIsNotAnObject` (`0x200000000`)
en trop.

Le commentaire du port attribuait a `...Loki.DrachnyenAbility$$.ctor` un
`TargetingOptions..ctor(&out, &preset, 0x200000000, 0)` — l'overload PRESET + flags. **Ce n'est pas
la surcharge appelee** : les xrefs ENTRANTES des trois surcharges tranchent sans ambiguite — le ctor
de Drachnyen figure parmi les appelants de la surcharge **2 arguments** (copie pure) et **pas** parmi
ceux de la surcharge 3 arguments. Masque effectif : `0x4000` = `TargetIsEnemy` seul.

Le bit retire n'etant pas porte (`TargetIsNotAnObject` n'est pas implementee), **aucun verdict de
ciblage ne change** : `probe_249` passe de 4 a 3 porteurs pour cette regle et de 6 a 5 abilities
touchees, `probe_181` reste a 98/98 masques poses. La correction retire une fausse verite, elle ne
deplace pas un comportement.

---

## 6. Ce que ce balayage ne repond pas — la question du bit n'est pas celle de la cible

Le bit `TargetIsTile` repond a **« le DOMAINE de `GetValidTargets` est-il fait de tuiles ? »**, PAS
a **« la cible de l'action est-elle une tuile ? »**. Les deux questions ne coincident pas, et la
seconde n'a pas d'inventaire : elle n'est pas derivable d'un masque. Cet inventaire ne doit donc pas
se lire « toutes les cibles tuile sont ici ».

### ⚠ Rectificatif MESURE : `1197 ExcruciatingFrequencies` PORTE le bit

`case-302` §1.1 et §4 affirmaient l'inverse — « 1197 cible une TUILE **sans** porter le bit », et
donc « elle n'apparait pas dans le balayage, et c'est correct ». **C'est faux sur le build courant.**
`...Loki.ExcruciatingFrequenciesAbility$$.ctor` passe le litteral `rules = 0x20000000042`, dont le
bit 6 est pose ; l'ability figure bien parmi les 41.

La vraie cause de son absence de l'ancien inventaire est mecanique : **1197 n'est pas dans
`ABILITY_CLASSES`**, et l'ancien balayage ne lisait le bit QUE sur ce registre. L'inference « donc
elle ne porte pas le bit » n'avait jamais ete mesuree — c'est exactement le mode de defaillance que
cette tranche corrige : un axe non balaye qui se lit comme un resultat negatif.

Ce que la fiche disait de JUSTE, et qui reste : le ciblage EFFECTIF de 1197 passe par
`TargetTiles@0x190` (l'aim d'une ligne), d'ou sa route BESPOKE
(`engine/playbook/excruciating_frequencies.py`, qui balaie positions x aims) plutot que la route
generique. Porter le bit et enumerer son domaine par le bit sont deux choses distinctes.
