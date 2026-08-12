# #984 — six résidus à RE consignée : ce que la confrontation au build a changé

Lot dont la propriété commune est rare : **la RE est déjà faite et écrite, le port ne l'est pas**.
Le budget qui va normalement dans la lecture est donc allé dans la **vérification** de cette RE et
dans la validation.

Résultat central, et il justifie à lui seul la consigne : **une RE consignée est une mesure datée**.
Sur les deux résidus effectivement travaillés, **les deux énoncés se sont révélés incomplets** — pas
faux dans ce qu'ils affirmaient, faux dans ce qu'ils laissaient conclure. Aucun des six n'était par
ailleurs débloqué par le travail des autres lots (vérifié : `EFFECT_CLASSES` ne contient ni 1545,
1546, 1547, 1209, 1499, 1500, 1518, 1519, 1509 ; `ABILITY_CLASSES` ne contient pas 1215).

## 1. `#967-r1` — « aucun consommateur » était faux, le consommateur a un NOM

`IdunBattle.AI.Playbook.Loki.DeathOnTheWindPlaybook$$GetCustomUnitOrderUtility`, corps confirmé
verbatim : `-(uint)(cVar1 != 0) & 0xffffff9d`, soit `Fix64(vtable[+0x1a8](this, unit) ? -99 : 0)`.

Le résidu concluait « la porter n'aurait aucun consommateur ». **Le consommateur natif existe et se
nomme** : `IdunBattleLogic.AI.Utilities.UnitPicker.UnitOrderUtility$$Priority`. Pour chaque ability
active de l'unité il fait `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)` puis ajoute
`playbook.GetCustomUnitOrderUtility(unit)` à un score de priorité d'ordre d'activation, agrégé avec
des `IdunBattle.AI.Utilities.BaseUtility$$GetUtilityValue` clés par `unitId`, par `abilityType` et
par trait.

**Ce qui manque au port n'est donc pas un lecteur pour une valeur — c'est l'étage `UnitPicker` tout
entier.** La distinction n'est pas cosmétique : « aucun consommateur » se lit comme *du code natif
mort*, alors que ce code est **vivant** et que nous le consommons déjà, côté natif, via
`decisionView.toActivate`.

**Second écart, LU** : ce terme-ci ne se neutralise **pas** par un poids absent du seed. Son
homologue `...Loki.TitanhammerSquadPlaybook$$GetCustomUnitOrderUtility` **multiplie** par un
`GetUtilityValue("<clé>")` absent du seed — donc 0, donc inerte, et c'est ce qui justifiait de le
laisser non porté. Celui de 1213 rend `-99` **en dur**, sans lire aucun poids : il mord toujours.
Les deux résidus se ressemblent et ne se traitent pas pareil.

**Verdict** : le port reste **FIDÈLE par absence d'étage**, pas par inertie du natif. `#967-r1`
**reste ouvert, requalifié** — il se ferme le jour où le port choisit lui-même l'unité active, et
son blocage est `etage`, pas « pas de consommateur ».

## 2. `#967-r3` — le terme aléatoire agit sur DEUX axes ; le port n'en couvrait aucun correctement

`...Loki.HailstrikePlaybook$$GetTargetUtility` confirmé terme à terme :
`Fix64(pierce + rng.Next(0, 10) + bonus)`, `pierce = 100 - DamageProfile.PiercingRatio` de
`FindRangedWeapon ?? FindMeleeWeapon` (slots `IBattleQuery` 179/178), `bonus ∈ {0, 500}`.

### 2.1 L'inclusivité n'est plus « non lue »

Le résidu écrivait « au plus 9 (ou 10 — l'inclusivité de `Next` n'est pas lue) ». Elle est
désormais **lue**, et par deux corps indépendants :
`IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` calcule `range = max - min` puis rend
`min + (g % range)` ; la surcharge d'interface
`...IntBasedMersenneTwister$$IdunBattle.Utils.PRNG.IPseudoRNG.Next` (slot **2** d'`IPseudoRNG`,
`metadata/interface_slots.tsv`, arité 2 — celle que le corps appelle) refait la même arithmétique.
**Borne haute EXCLUE** ⇒ `Next(0, 10)` ∈ **[0, 9]**, dix valeurs équiprobables, **maximum 9**.

### 2.2 Le faux dilemme

Le résidu posait le choix « 0 (borne) contre 4,5 (moyenne, un fit) ». **Sur le classement, ce choix
est vide** : le score ne sert qu'à un argmax, et toute constante ajoutée aux N cibles est
l'**identité** sur l'argmax. `0` et `4,5` y désignent exactement le même candidat.

Le tirage étant fait **une fois par cible** (dans `GetTargetUtility`, appelé dans la boucle), c'est
un **bruit indépendant**, pas une constante — et il agit donc sur deux axes distincts :

| axe | effet | réductible ? |
|---|---|---|
| **CLASSEMENT** | renverse deux cibles de même classe de bonus dès que l'écart de perçage est ≤ 9 | **non** — exigerait de mirrorer le flux `IPseudoRNG` |
| **SEUIL** (`MIN_UTILITY = 1`) | décide de l'**existence** de l'action quand `pierce + bonus == 0` | **oui**, par la borne haute LUE |

### 2.3 Le classement : le renversement est le cas COURANT, pas un cas rare

Le résidu minimisait : « il ne départage que deux alliés dont les `PiercingRatio` diffèrent de moins
de 10 ». Vrai, mais **mesuré sur le gameconfig (683 unités), les `PiercingRatio` vivent sur une
grille de pas 5** : `1, 10, 15, 20, 25, 30, 35, 40, 50, 55, 60, 65, 70, 75, 80, 100`. L'écart entre
deux valeurs **voisines** est donc 5 — **sous** le maximum du terme (9). Le régime « moins de 10 »
n'est pas une queue de distribution, c'est le voisinage ordinaire.

Cet axe est **irréductible** : le port ne consomme aucun des tirages de l'IA, donc l'état du
Mersenne Twister diverge dès le premier. C'est une **indétermination** — on la nomme, on ne la
fitte pas.

### 2.4 Le seuil : le port SUPPRIMAIT une action que le natif propose 9 fois sur 10

Quand `pierce + bonus == 0`, le natif émet ssi `rnd >= 1`, soit **9 fois sur 10**. Un port à
`rnd = 0` la supprime **toujours**.

**Le régime est réel et atteignable** — c'est ce qui fait la différence avec une objection
théorique. Il faut une cible qui soit **légale** pour le masque de 1214
(`TargetIsFriendly | TargetIsUnit | TargetIsNotAnObject`) et qui ait `pierce + bonus == 0` :

* les 11 unités `lineup` à `pierce + bonus == 0` sont **toutes des Machines of War** — écartées par
  `TargetIsUnit` (`GetUnit(MoW)` est nul côté natif) ;
* les `LootObj_*` sont écartés par `TargetIsNotAnObject` ;
* restent les **summons sans arme**, et parmi eux **`darkaSmnWatcher`** : faction **DarkAngels** —
  donc allié naturel du `darkaStormSpeeder` — `weapons = []`, traits `['Summon', 'Immune',
  'PermaDeath']`, ni `Object` ni machine. **Il passe le masque.**

### 2.5 Correctif

Partage explicite du terme non porté, dans `engine/playbook/noncomparable/storm_speeder.py` :

* `RNG_TERM = 0.0` — borne **basse**, inchangée, pour le **classement** (jamais une moyenne) ;
* `RNG_TERM_MAX = 9.0` — borne **haute LUE**, pour le seul **franchissement du seuil**.

L'utilité **rapportée** reste celle du score sans bruit : la borne n'entre que dans le test de
seuil. Le natif émet s'il **existe** un tirage qui franchit ⇒ le port émet.

**Verdict** : `#967-r3` **fermé**.

## 3. `#902-r1` — de TROIS classes à UNE

Le résidu demandait de créer **trois** classes d'effet. Deux tombent, et pour des raisons
différentes — c'est le résultat le plus rentable de la tranche, puisqu'il évite un fork.

### 3.1 `1545 NanoscarabRepairProtocols` — déjà porté, et une classe serait un FORK

Le résidu affirmait « le +hpToRepair à chaque réparation reçue n'est pas porté ». **Faux.** Preuve
exécutable : `calculate_repair_modifier_for_prediction([{name: "NanoscarabRepairProtocols",
level: 50}])` rend `(443, 1.0)` contre `(0, 1.0)` à vide.

Il ne vit simplement pas là où le résidu le cherchait : pas dans `EFFECT_CLASSES`, mais dans le
foyer unique `engine.predict.calculate_repair_modifier_for_prediction`, que la face COMBAT
(`runner/operations/repair.py`) **importe et appelle** — vérifié par identité d'objet, pas par grep.

C'est un **arbitrage explicite**, déjà écrit dans `entities/effects/loki/nether_realm_casket.py` :
les **trois** porteurs natifs du canal `IdunBattle.Entities.Effects.BaseEffect$$RepairBonus` (1545,
1382 `VoltagheistField_RepairReduction`, 1456 `NetherRealmCasket_LivingMetalBonus`) n'ont **aucun**
d'eux de classe d'effet, précisément parce qu'en créer une dupliquerait la règle du canal.

⇒ Répondre au résidu en inscrivant 1545 dans `EFFECT_CLASSES` aurait écrit **deux règles pour un
canal natif unique**, divergentes au premier changement de build. Cliquet posé :
`tests/engine/test_984_repair_bonus_1545_porte_offline.py` (4 tests).

La RE confirme le chemin natif, maillon par maillon :
`RepairCalculations$$CalculateRepairModifierForPrediction` → `IEffect` slot 29 = `RepairBonus`
(`metadata/interface_slots.tsv`) → `BaseEffect$$RepairBonus` → cache alimenté par le virtuel
slot 83 `CreateEffectRepairBonus` → `RepairModifier$$Add`, qui range un `ForAddition` dans
l'accumulateur **additif**. Elle apporte une précision que la case-902 n'avait pas : le 3ᵉ argument
de `EffectBonus$$ForAddition` est `this.SourceAbility`, **pas `null`** (lu au désassemblage, le
registre R9 n'étant pas suivi par le pseudo-C).

### 3.2 `1546 NanoscarabRepairProtocols_ExtraHp` — la classe N'EXISTE PAS

L'ordinal vit dans `enums.tsv`, mais **aucun symbole ne le porte** — ni `frida/methods.tsv`, ni
`ghidra/functions.tsv`. Il est posé par `AddDynamicStatModifierEffect(..., effectType = 0x60a,
statType = 5 Health, ...)` : c'est l'`ADynamicStatModifierEffect` **générique**, pas une classe
propre. Il n'y a **rien à mirrorer**.

Conséquence directe : **le lien avec `#572-r1` disparaît**. Le résidu conditionnait ce volet à la
résorption de `#572-r1` (« inobservable tant que `ctx.stats[5]` ne se propage pas ») ; comme il n'y
a aucune classe à porter, la dépendance n'a jamais eu d'objet.

### 3.3 `1547 ReanimationBeam_Revive` — le seul vrai reste, avec un piège mesuré

Chaîne d'héritage à mirrorer sur **trois** étages, lue dans `classes.tsv` :
`ReanimationBeam_ReviveEffect` → `IdunBattle.Entities.Effects.ReviveEffect` →
`PlayerTurnEffect` → `BaseEffect`.

Le `.ctor` : `ReviveEffect..ctor(turnsEnabled = 2 Both, activationFrequency = 0 Automatic,
sourceAbility = Nullable(AbilityOrEffect(this)), removeEffect = true)`. Le 3ᵉ argument que la
case-902 notait `null` est en réalité un **enum à 0**, et il est **load-bearing** : `Automatic`
vide `PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal`, donc toute la mécanique passe par le
seul couple slot 70 (`CreateTargetTrigger`) / slot 72 (`CreateTargetTriggerBehaviour`). Câbler quoi
que ce soit « par tour » serait une invention.

Déclenchement = **la mort du porteur** :
`OnPreDeath(triggerOnOverkill: false, triggerOnSteppable: false) & CanBeRevived(Target, HealType) &
CreateTargetFilter()`. Comportement = `Maybe(Revive(caster = Owner, targets = Target,
hp = Min(Direct(hp[lvl]), StatAmount(Target, Health, Initial))) & RemoveEffect, Target, 100)`.

⚠ **Le piège, et il est silencieux** : `get_HealType` de la feuille vaut **`1 = Mechanical`** alors
que la base rend **`0 = NonMechanical`**. Le supposer hérité donnerait l'inverse du comportement
réel — et cette valeur n'est lisible **ni dans `methods.tsv`, ni dans Ghidra** (corps
ICF-dédupliqué : `mov eax,1 ; ret`), seulement via le metadata et le bloc `methodPointers`. Le
témoin qui prouve que l'axe discrimine existe :
`TaintedNarthecium_ReviveEffect$$get_ReviveOnOverkill` vaut `true` là où les autres valent `false`.

**NON PORTÉ ici** : c'est un port à trois étages d'héritage plus un canal `Revive`, hors du budget
restant de cette tranche. Le résidu passe à `BLOCAGE: aucun`, et son périmètre est divisé par trois.

## 4. `#590-r3` — le blocage était PÉRIMÉ, et c'est une citation du port qui le portait

L'arbre du résidu est **confirmé**, et son énoncé **complété** sur quatre points lus :
`On(0x32 = UnitAdded)` passe par `BaseEffect$$On`, donc `ownerNeedsToBeAlive: false` ; les deux
`Parent` sont `root: false` (le **summoner immédiat**, via `UnitExtensions$$GetParent` et
`ParentComponent+0x10` — pas l'équipe, pas le propriétaire) ; la surcharge d'`AddBondEffect` prend
**six** arguments (l'énoncé en donnait trois — `abilityState = AbilityStateFromEffect(Effect)` et
`source = BondedEntityFromEffect(Effect)` manquaient), tranchée par `list_xrefs` et non par la
forme, sa jumelle ayant la **même arité** ; et `0x4b9` est tranché par le **type déclaré** du
paramètre — `EffectType`, sachant que 1209 nomme `InfernalCannon` dans `ActiveAbilityType` et
`PoundThemToDust_Attack` dans `TriggeredAbilityType`.

**Mais le résultat qui compte est ailleurs.** Le résidu portait `BLOCAGE: etage`, et la docstring de
`engine/entities/effects/loki/possession.py` affirmait que « le port n'a pas de canal
`CreateHandleTriggerAbilities` sur les effets de bond ; le vecteur `On(UnitAdded)` existe côté
triggers mais aucun effet porté ne s'y abonne ». **Les trois étages déclarés manquants existent
tous les trois** au commit courant :

| étage déclaré manquant | état réel |
|---|---|
| canal `CreateHandleTriggerAbilities` | `EFFECT_TRIGGERS` (`triggers/dispatch/registry.py`) + `collect_effect_triggers` (`.../dispatch/core.py`), portant **déjà** des entrées issues d'un `CreateHandleTriggerAbilitiesInternal` (1009 `RangedAutoAttackEffect`, `PhoenixGem_CanReviveEffect`) |
| mirror de la base `ABondEffect` | **existe** — `triggers/bond_removal.py` porte ses trois triggers de retrait |
| abonné à `On(UnitAdded)` | vecteur **vivant** — `on_unit_added` (`operations/spawn.py`) a déjà `GhostRemoveOnUnitAdded`, `ContagionsOfNurgle_AddEffectToNewUnit`, … |

Le travail restant est **deux entrées de registre**, pas un étage à ouvrir. C'est exactement le
piège du lot : *une citation périmée dans le code avait fait classer le résidu comme bloqué*, et le
dispatch l'aurait écarté tant qu'aucune fenêtre n'était prévue. La docstring est corrigée dans le
même commit, et la ligne de backlog passe à `BLOCAGE: aucun`.

**Écart que l'énoncé ne nommait pas** : `1209` est absent de `EFFECT_TRIGGERS` **et** de
`bond_removal.py` — il manque donc aussi les **trois triggers de retrait de bond hérités** de la
base, pas seulement la propagation.

**Pourquoi je ne le porte PAS ici** — deux points restent **non prouvés**, et porter à l'aveugle
écrirait une hypothèse en dur :

1. `<DSLSelectors+0x40>` = `Actor` est une **hypothèse étayée**, pas une lecture. `DSLSelectors`
   expose ses sélecteurs partagés en **champs**, et aucun dump de champs n'existe sous
   `data/symbols/<build>/` (`classes.tsv` ne porte que nom/taille/parent). L'argument sémantique
   est fort (si c'était `Caster`, `AreEqual(Parent(Caster), Owner)` rendrait l'arbre absurde) mais
   il reste un argument.
2. Les **valeurs** des trois getters d'`ABondEffect` (`+0x748`/`+0x728`/`+0x738`) **pour cet
   effet** sont inconnues (corps dédupliqués, absents de `methods.tsv`), donc lesquels des trois
   retraits s'arment réellement sur 1209 reste à établir avant de l'inscrire.

Le capteur `validTargetsFrom` mis en ligne pendant la tranche ne lève aucun des deux.

## 5. Ce qui n'est PAS couvert, et pourquoi

* **`#967-r3`, axe CLASSEMENT** : non couvert, et il ne l'est pas par ce correctif. Fermer
  exigerait de mirrorer le flux `IPseudoRNG` de l'IA — même classe de problème que les
  `GetUseProbability` conditionnels. L'indétermination est désormais **écrite** au lieu d'être
  masquée par un `0`.
* **Confrontation LIVE du tirage** : NON CONFRONTÉ — fenêtre DRAIN pendant toute la tranche
  (`GET /api/admin/drain` → `enabled: true`, `liveRunners: null`, aucune session Frida vivante).
  Le point d'ancrage qui la rendrait mesurable est nommé au §5.
* **`#966-r4`** : NON PORTÉ — **collision de foyer**. Le canal à ouvrir
  (`aura_attack_damage_bonus_from_allies` / `create_aura_attack_damage_bonus_for_ally`, dont le
  `ctx` ne porte pas l'adjacence à la CIBLE) vit dans `engine/entities/effects/base.py` et
  `engine/entities/effects/loki/extra_damage_aura.py` — **les deux réservés à d'autres lots en
  vol**. Le porter ici déplacerait une collision au lieu de l'éviter. Le second étage manquant
  (`DSLBehaviors$$UseNormalAttackIfAble`, cité 12 fois, jamais porté comme feuille) reste ouvert.
* **`#889-r6`** : NON PORTÉ — ampleur **confirmée au décompilé**, la prémisse tient. Le recensement
  des symboles rend, pour la seule face COMBAT :
  `...InstrumentsOfVengeanceAbility$$GetEffectBehavior`,
  `...InstrumentsOfVengeance_AttackAbility$$AttackLine`, `$$AttackTileBehavior`,
  `...InstrumentsOfVengeance_PendingAttackEffect$$GetAttackingUnitSelector` et son `.ctor`,
  `...InstrumentsOfVengeance_LocationTargetEffect$$.ctor` — soit **deux classes d'effet neuves** en
  plus des six nœuds DSL déjà nommés par le résidu. C'est une tranche à soi seule.

## 6. Validation

* `tests/engine/playbook/test_967_mow_decision_faces_offline.py` : **19 → 22**, tous verts.
  Les trois tests neufs sont construits pour ne pas être décoratifs :
  * la **prémisse** du régime est **dérivée du gameconfig**, pas postulée — si plus aucun summon ne
    tombe dans `pierce + bonus == 0`, le test **rougit** et le seuil doit être ré-arbitré ;
  * **contre-épreuve interne** : borne remise à 0 ⇒ l'action disparaît (sans elle, le test passerait
    aussi bien sur un port qui ne franchit jamais rien) ;
  * **garde de portée** : `MIN_UTILITY > 9` doit continuer de REFUSER — la borne haute ne devient
    pas un passe-partout.
* `probe_967_morsure.py` : **11 mutations sur 11 mordent** après le changement, témoin non muté
  vert, restauration vérifiée. Le correctif n'a désarmé aucune garde existante.
* `probe_181_targeting_gaps.py` : 165 abilities, **0 manquante**. `probe_909_decision_actives_kit.py`
  vert.

## 7. Le capteur qui manque, nommé

Rien dans cette tranche n'était bloqué par un capteur. Le seul qui aurait de la valeur — et qui
dépasse ce lot — est une trace de l'**utilité playbook par cible**, au point d'ancrage
`IdunBattle.AI.Playbook.Loki.HailstrikePlaybook$$GetTargetUtility` (retour `Fix64`, argument
`target`). Il mesurerait le tirage réel et confirmerait live le `[0, 9]` établi ici.

⚠ **C'est un chemin CHAUD** — appelé dans la boucle de cibles, pour chaque unité et chaque tour. Un
hook permanent y tombe sous l'interdit « broad-hooks sur méthodes hot » ; il exige un armement **à
la demande**, façon `modifier-observe`. C'est sa propre tranche, pas un passager clandestin d'une
fenêtre de reinject.

Sa portée dépasserait largement `#967` : c'est le **seul canal qui donnerait l'utilité native par
cible**, là où aujourd'hui on n'observe que l'action retenue. Toutes les faces DÉCISION en
bénéficieraient.
