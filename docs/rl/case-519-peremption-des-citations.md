# Case #519 — nos livraisons périment nos citations et nos témoins, et rien ne le voyait

**Ce n'est pas un port.** C'est un groupe de résidus qui partagent une cause unique : une tranche
de portage fait ENTRER une ability dans `ABILITY_CLASSES` et SORTIR son entrée de
`TARGETING_OPTIONS_UNPORTED` — donc toute citation ou tout témoin qui pointait vers elle devient
faux. Le 2026-08-07, vingt ports ont été mergés ; **deux** ont rendu `master` rouge.

La question posée était : **ce motif est-il outillable ?** Réponse mesurée : **oui, sur deux axes
sur trois**, et le troisième dit précisément pourquoi il ne l'est pas.

## 1. L'axe TÉMOIN — outillable, cliquet armé à zéro

`probe_519_temoins_de_camp.py` balaie l'AST de `scripts/python/**` et relève toute affirmation de
camp portant un id **littéral** : `<lit> in/not in <table>`, `<table>[<lit>]`, `<table>.get(<lit>)`
et `targeting_options_for(<lit>)` comparés à `None`.

**L'asymétrie fait le tri, et c'est elle qui rend le verdict mécanique** : notre cadence va de
« non portée » vers « portée », jamais l'inverse.

| verdict | forme | sens |
|---|---|---|
| `STABLE` | « x EST au registre / son masque EST lu » | ne peut plus tomber |
| `PERISSABLE` | « x N'EST PAS au registre / son masque n'est PAS lu » | tombera à la tranche qui portera x |
| `PERIME` | l'affirmation est fausse **aujourd'hui** | rouge, ou mensonge silencieux |

Mesure à l'ouverture de la tranche : **18 sites, 2 `PERIME`, 2 `PERISSABLE`, 14 `STABLE`**.
⚠ Ces comptes se **re-dérivent** (`python scripts/python/probe_519_temoins_de_camp.py`), ils ne se
citent pas : après réparation et rebase sur `#512`, le corpus est tombé à **13 sites, 0 `PERIME`**
— les affirmations littérales réparées ayant été remplacées par des dérivations.

Les deux `PERIME` sont les rouges de `master`, tous deux sur le témoin `1091 SlashingDive` porté
par #507 — **et le brief n'en signalait qu'un**. Le second
(`test_433_r4_r2_r1_r2_r2_r1_r1_r1_source_tile_zone_offline.py:243`) a été trouvé par le balayage.

Les deux `PERISSABLE` (`1050 not in ABILITY_CLASSES`, dans deux fichiers) tomberont à la tranche
qui portera `1050`. Ils sont **nommés d'avance**, pas subis.

### La réparation : plus aucun témoin figé

Le témoin de `test_an_unread_mask_never_shrinks` avait déjà été remplacé **trois fois** — `1177`
(#433-r4-r2-r1-r2-r2-r1-r1), `1053` (…-r1), `1091` (#507) — chaque remplacement se déclarant mieux
choisi que le précédent (« non-lecture STRUCTURELLE »). Le troisième est tombé en quelques heures.
**Un id figé du côté « pas encore lu » ne peut pas être bien choisi** : la cadence le vise par
construction.

Le test porte désormais sur la partition **dérivée** d'`ActiveAbilityType` (260 ids →
**110 non lus / 150 lus**), et sur **tous** les non-lus à la fois — ce que le témoin unique n'a
jamais fait. Il assertionne son propre non-vide dans les deux sens, et une contre-épreuve interdit
le régime dégénéré : parmi les 150 lus, **14** rendent une zone vide et **136** non — donc la
fonction discrimine, elle ne rend pas `False` par construction.

## 2. L'axe COMPTEUR — outillable, et la correction du jour était elle-même fausse

Les compteurs d'en-tête de `TARGETING_OPTIONS_UNPORTED` avaient été faux **quatre fois** dans la
journée, chacun corrigé à la main par la tranche qui le croisait et re-cassé par la suivante
(sept tranches, #498 à #504, ont retiré une entrée **chacune**, en parallèle et aveugles les unes
aux autres).

**Et la correction FINALE — celle qui se déclarait « RE-COMPTÉE PAR LE CODE » — était fausse
aussi** : sur l'arbre de `5e876708`, elle annonçait une ventilation par forme de ctor de
`10 / 4 / 0 / 13` là où le code en portait `12 / 6 / 0 / 9`. **Trois nombres faux sur quatre, et
leur SOMME juste** (27 des deux côtés) : le seul contrôle qu'un relecteur pouvait faire de tête
PASSAIT. *Un accord peut être le produit de fautes qui se compensent.*

⚠ Ces quatre nombres ont **encore** bougé pendant la tranche : le rebase sur `#512` (qui a porté
`1197 ExcruciatingFrequencies`) les a fait passer à `11 / 6 / 0 / 9` pour un dict de **26**. Le
cliquet a rougi au rebase et la régénération l'a refermé — c'est exactement l'office qu'on lui
demande, et la démonstration que ces nombres n'ont pas à être écrits à la main.

`probe_519_comptes_de_table.py` dérive les comptes et les écrit dans un **BLOC GÉNÉRÉ** de
l'en-tête (`--ecrire`) ; `test_519_comptes_derives_offline.py` le confronte à chaque passe. La
forme de chaque entrée vient du marqueur `@FORME` le plus proche au-dessus d'elle — les en-têtes de
section en portent un, et les quatre entrées hors-bloc en portent un chacune. Une entrée sans
marqueur fait rendre **rc 2**, pas un vert : une dérivation qui ne voit pas tout est pire qu'un
compte écrit, parce qu'elle a l'air dérivée.

## 3. L'axe ORDINAL CITÉ — outillable seulement avec le BON discriminant

Deuxième forme du motif, alimentée par le **jeu** et non par notre cadence :
`IdunBattle.Configuration.UtilityType` a reçu **une seule** insertion entre `gqfc5mff6c` et
`rnca9r7q6c` — `AttackTile` en 8 — qui a décalé de +1 les **73** membres suivants.

`#504-r1` signalait **un** fichier. Le balayage en trouve **37 citations** dans `engine/**`.

**Le discriminant est tout l'enjeu.** Un premier balayage « nom d'enum + ordinal » a rendu
**5 faux positifs sur 40** : `Attack(0)` est un `StatType`, `Ranged(2)` un `AttackType`,
`Elevation(2)` un masque `ObscuringType`. **Le NOM ne tranche pas l'enum** — exactement ce que la
doctrine du dépôt dit des ids d'ability, et l'outil venait de commettre la faute qu'il devait
détecter. Le critère retenu ne peut accuser à tort :

> le nom est membre de l'enum sur le build **courant**, ET l'ordinal cité est **exactement** sa
> valeur sur le build **précédent**, ET les deux diffèrent.

C'est une **signature de décalage**, pas une coïncidence de nom. Prix de la rigueur, dit et non tu :
on ne voit que les citations périmées par le **dernier** changement de build.

Contrôle de la réécriture de masse : **empreinte AST hors docstrings, 0 divergence sur 24
fichiers** — seuls commentaires et docstrings ont bougé.

Le code, lui, était juste : il passe par le mirror `engine.utilities.utility_type.UtilityType` et
n'écrit aucun ordinal en dur. Le natif confirme la valeur courante — les deux surcharges de
`IdunBattleLogic.Entities.DSLSelectors$$SortUnitsByDamageUtility` qui construisent la définition
appellent `IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor(this, 0x23)`.

⚠ **Une citation HISTORIQUE ne doit pas passer par un trou.** Le paragraphe qui explique la
correction citait verbatim l'ancienne forme `Damage(34)` — donc le cliquet l'accusait. Plutôt que
d'ouvrir une échappatoire (un trou dans un cliquet vaut moins que pas de cliquet), la citation est
reformulée `Damage = 34`. Les case-docs de `docs/rl/**`, elles, ne sont **pas** dans le corpus :
elles documentent des mesures passées, et les réécrire les falsifierait.

## 4. Ce qui n'est PAS outillé, et pourquoi

- **La PROSE** (docstrings, commentaires, `docs/rl/**`) sur l'axe TÉMOIN : un id cité dans un
  paragraphe n'est confronté à rien. Aucun critère mécanique — résidu ouvert.
- Les ids arrivant par une **variable** : ils suivent la table, donc ils ne périssent pas.
- Les **mutations** de table (`T[x] = …`, `del`, monkeypatch) : ce ne sont pas des affirmations.
- Les citations périmées depuis **plus d'un build** sur l'axe ORDINAL (cf. §3).

## 5. `#488-r1` — le verdict `OnMelta` dead-code NE TIENT PLUS au décompilé

Question posée : le verdict de `case-72`, établi sur `gqfc5mff6c`, tient-il sur `rnca9r7q6c` ?

La racine de ce verdict était : *`OnMeltaDamageAbility` n'override pas `CreateTrigger`, donc
l'ability n'est jamais matérialisée*. **Cette racine est falsifiée sur le build courant.**

| build | `OnMeltaDamageAbility$$CreateBehaviour` | `OnMeltaDamageAbility$$CreateTrigger` |
|---|---|---|
| `gqfc5mff6c` | présent | **ABSENT** de `ghidra/functions.tsv` |
| `rnca9r7q6c` | présent | **PRÉSENT**, corps `return DSLTriggers.On(0x19 MatchInit, true)` |

`CreateBehaviour` est inchangé : `AddEffect(0x511 = 1297 Melta_ExtraDmg, source =
AbilityStateReference(caster), target = First(...))`. La chaîne est donc **complète** au décompilé,
et le gate Melta/Vehicle vit là où il a toujours vécu —
`IdunBattle.Entities.Effects.Loki.Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
(`DamageProfileHasTrait(OnMelta) && HasTrait(target, Vehicle)`). Un trigger `MatchInit` sans gate
de profil est **cohérent** avec ce découpage, là où `OnFire`/`OnToxic` gatent au trigger
(`On(0x10 DamageDealt) & DamageProfileHasTrait(...)`) parce que leurs effets, eux, sont
inconditionnels.

**PORT NON FAIT — arrêt demandé, et je m'y tiens** : un trait de dégât touche le pipeline partagé
par toutes les attaques. Deux réserves à lever d'abord, toutes deux mesurées :

1. **Le corps est probablement DÉDUPLIQUÉ.** L'adresse porte **8** xrefs DATA entrantes (contre
   **2** pour `OnFireDamageAbility$$CreateTrigger` et `OnToxicDamageAbility$$CreateTrigger`) et vit
   loin du bloc de code de la classe. `return On(MatchInit, true)` est un corps d'une ligne que
   ~7 autres méthodes partagent. Le label atteste qu'`OnMelta` **est** un propriétaire, mais la
   table n'en nomme qu'un — il faut la confirmation par le **slot de vtable de l'instance**
   (RPC `resolveMethodPtr`, la voie exacte par laquelle #507 a tranché `SlashingDive`).
2. **Contre-observation LIVE, sur le build courant** : runner `1196` (board `MC1_67`, seed 777,
   `tauShadowsun` vs `admecDestroyer`+`orksNob`, unités placées). Au début de match, les effets de
   `tauShadowsun` sont `DefenderOfTheGreaterGood_ExtraDmg`, `…_ExtraHits`,
   `Camouflage_HitReduction`, `Infiltrate` — **pas de `Melta_ExtraDmg`**. C'est le canal qu'avait
   utilisé `case-72`, et il dit toujours non. Deux lectures possibles, non départagées :
   `First(...)` rendrait un ensemble **vide** au `MatchInit` (l'ability serait alors morte pour une
   raison **différente** de celle de `case-72`), ou l'effet est posé mais invisible de
   `decisionView.effects` (aveugle aux auras).

**Montage exact pour reprendre** : (a) `resolveMethodPtr` sur le slot `CreateTrigger` d'une
instance d'`OnMeltaDamageAbility` — c'est le seul geste qui tranche la réserve 1 ; (b) si vivant,
mesurer natif vs port sur `tauShadowsun` → `admecDestroyer` (Vehicle) **et** `orksNob`
(non-Vehicle) en attaque **normale nue**, le second servant de témoin bit-exact. Rappel de la
mesure #488 : natif `[4497, 5349]` vs port `[3162, 2678]` sur le Vehicle, rapports **1,42** et
**2,00** — pas un facteur constant, donc pas un simple `×1,5` sur la bande.

## Résidus ouverts

- **`#519-r1`** — l'axe PROSE du motif TÉMOIN n'est pas outillé (cf. §4). Un id d'ability cité dans
  un paragraphe pour dire « pas encore portée » n'est confronté à rien.
- **`#488-r1` reste OUVERT**, mais son énoncé change : ce n'est plus « le verdict est peut-être
  périmé » — il l'est au décompilé — c'est « le chemin est-il VIVANT, et si oui pourquoi l'effet ne
  se voit-il pas ». Cf. §5.

## Symboles cités

- `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnMeltaDamageAbility$$CreateTrigger` /
  `$$CreateBehaviour` ; jumeaux `OnFireDamageAbility$$CreateTrigger`,
  `OnToxicDamageAbility$$CreateTrigger`.
- `IdunBattle.Entities.Effects.Loki.Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`.
- `IdunBattleLogic.Entities.DSLSelectors$$SortUnitsByDamageUtility` (4 surcharges) ;
  `IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor`.
- `IdunBattle.Core.Services.TargetingOptions$$.ctor` (3 surcharges) et `$$.cctor`.
