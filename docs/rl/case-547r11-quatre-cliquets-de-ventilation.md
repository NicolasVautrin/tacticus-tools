# #547-r11 — quatre cliquets de ventilation rouges sur `master`, et ce qu'ils gardaient vraiment

`master` (`9e9ab25b`) rendait **quatre** assertions rouges. La question posée à chacune était
binaire : **le cliquet a-t-il raison — un site réel n'est pas déclaré — ou son propre inventaire
est-il faux ?** Réponse mesurée : **deux fois « les deux »**, deux fois « le cliquet a raison ».
Et un **cinquième** rouge, que le cas ne nommait pas, avait la même cause exacte que l'un d'eux.

## Le tableau

| assertion | verdict | ce qui était en cause |
|---|---|---|
| `test_ctx_traits_substrat_ventilation_offline::test_la_table_ventile_exactement_l_inventaire` | **cliquet a raison** | 6 sites `traits` réels non ventilés |
| `test_462_r4b_substrat_mort_appelants_offline::test_la_table_ventile_exactement_l_inventaire` | **cliquet a raison** | 3 appelants `active_effects` réels non ventilés |
| `test_462_r4b_substrat_mort_appelants_offline::test_tout_porteur_fire_on_death_est_trie` | **les deux** | 5 porteurs réels + 1 accusation FAUSSE (tri par TEXTE) |
| `test_camo_seed_inventory_offline::test_every_condition_gated_class_has_a_pose_verdict` | **les deux** | 1 classe sans verdict de pose + inventaire des canaux de seed faux (2 tables sur 6) |
| *(hors cas)* `test_refresh_active_flag_discriminant_offline::test_discriminant_is_the_is_active_override_not_the_case322_flag` | **cliquet a raison** | même classe, autre déclaration manquante |

## Ce qui rouvre ces cliquets — et ce n'est pas une dette à solder

Ce sont des cliquets de **ventilation** : une table doit ventiler *exactement* son inventaire. Comme
`TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE`, **c'est notre propre cadence de portage qui les
rouvre**, un site neuf non déclaré à la fois. La mesure la plus nette de cette tranche le montre :
les **cinq** porteurs `fire_on_death` accusés ont été posés par **#10015, mergée la veille**. Cette
PR a fait le travail juste (elle a mécanisé l'appariement port ↔ natif, 9 → 130 classes
confrontées, et lu chaque valeur dans `metadata/allow_for_dead_owner.tsv`) — et poser la valeur
juste **est** ce qui rouvre la table, puisque le port, lui, n'inscrit toujours pas un
cadavre-au-chargement au registre.

Ce qui les rouvrira encore, nommément :

- une classe qui entre dans `EFFECT_CLASSES` en surchargeant `is_active` sans son verdict de pose
  **et** sans sa ligne d'attestation (les deux, toujours ensemble — c'est ce qui vient de se
  produire) ;
- une valeur `get_AllowForDeadOwner` nouvellement lue et portée en `fire_on_death` ;
- tout site neuf qui lit `traits` ou `active_effects` sur une entité ECS ;
- **un canal de seed neuf** — c'est le vice réparé ici, cf. plus bas.

## Les deux inventaires qui étaient faux

### 1. Une liste de TABLES au lieu des registres (camo)

`probe_366_camo_seed_inventory.scan()` décidait du verdict `COUVERT-SEED` en lisant **deux tables
écrites à la main** (`ABILITY_INIT_OWNER_EFFECTS`, `ABILITY_OWNER_EFFECTS`). Le seed en consomme
davantage : #963-r5 avait ajouté `ABILITY_INIT_OWNER_BOND_EFFECTS` — le canal qui écrit `bonded`,
sans lequel la pose d'init de `Lifewards` restait refusée — et `TRAIT_OWNER_EFFECTS` n'y avait
jamais figuré.

Conséquence mesurée : `Lifewards_BondEffect`, **seedé**, serait sorti `EXPOSE`, c'est-à-dire « le
natif porte l'instance et le port ne la matérialise pas » — un trou annoncé là où il n'y en a pas.
C'est le vice recensé par le CLAUDE.md (« un recenseur ne peut pas rendre zéro sur ce qu'il ne
visite pas »), dans une variante de plus.

**Le remède n'est pas d'allonger la liste** (elle re-vieillirait au canal suivant) mais de la
**dériver du consommateur**. `canaux_de_seed()` parse `runner/operations/spawn.py` — le foyer unique
des `_seed_*_owner_effects` — en trois crans mécaniques :

1. tout nom importé de `entities/effects/factory.py`, **imports différés compris** (le canal BOND
   est importé *dans* une fonction : un balayage des seuls imports de tête l'aurait raté) ;
2. accesseur → table par l'AST du `return <TABLE>.get(...)`, jamais par le nom ;
3. aplatissement des valeurs, filtré par appartenance à `EFFECT_CLASSES`.

Mesure : **2 → 6** canaux visités, `COUVERT-SEED` 18 → 19, `INCONNU` 1 → 0. Le probe **imprime ce
qu'il filtre** : trois tables d'indirection sortent avec leurs noms écartés
(`TRAIT_DERIVED_ABILITIES` porte des noms d'*ability*, `ABILITY_INIT_OWNER_FLAGS` des *entiers*).
Le filtre est **exact**, et c'est mesuré : l'intersection `TRAIT_DERIVED_ABILITIES` ×
`EFFECT_CLASSES` est **vide** (0 sur 8).

⚠ **Cette dérivation pouvait rendre VIDE en silence**, et aucune assertion existante ne l'aurait vu :
un `seeded` vide fait basculer tout le gisement de `COUVERT-SEED` vers `EXPOSE`, alors que le
cliquet de `POSE_VECTOR` ne regarde que `unknown`. D'où un test qui **assertionne son propre
non-vide** (≥ 2 tables, ≥ 10 noms, canal BOND présent) sans figer la liste — ce serait la liste
blanche qu'on vient de retirer. Contre-épreuve jouée : restreindre le balayage aux imports de tête
fait tomber le canal BOND et **rougit** ce test, pendant que celui de `POSE_VECTOR` reste vert.

### 2. Un tri par TEXTE là où la question porte sur des VALEURS (`fire_on_death`)

Le tri comparait `ast.unparse(event_id)` à des libellés `"EventTriggerType.UnitDeath"`. Un site qui
écrit une **constante de module** — `event_id = _ON_UNIT_DEATH`, la forme majoritaire — n'en
contient aucun. `RelicOfLostCadiaSummonUnitAbility` écoute `UnitDeath(0)`, donc **sa propre mort**,
et sortait « NON TRIÉ ».

Le probe résout désormais la valeur sur la classe (`_events_de` — il importe déjà le module pour
résoudre la face, donc lire l'attribut ne coûte rien) et compare à des **membres d'enum**, ce que
« un ENTIER qui DÉSIGNE quelque chose passe par un ENUM » demandait déjà. Le prédicat est un
`all()`, pas un `any()` : un porteur qui écoute la mort **et** autre chose peut encore tirer par le
second vecteur (`LordOfTempests` = `[9, 38]`).

⚠ **Le cliquet principal ne garde pas cette réparation** : il est vert dans les *deux* régimes dès
que le porteur mal trié entre au registre. D'où un second test qui fige le fait mesuré — il existe
un porteur dont le texte ne contient aucun libellé alors que sa valeur en est une — et qui
assertionne son propre non-vide. Le test principal accuse en outre le **résolveur** séparément :
sous mutation (`_events_de` rendant `None`), il dit « c'est le résolveur qui est cassé, pas le
registre », au lieu de rendre 24 porteurs faussement non triés.

## Le seul régime divergent qui ne soit pas vide

Sur les 24 porteurs `fire_on_death`, **23** ont un régime divergent vide — l'événement est leur
propre mort, ou la face est EFFET (aucun gate d'owner natif), ou `matches` exige que le porteur soit
l'**acteur**, et un cadavre-au-chargement n'agit jamais.

**`LifewardsAbility` est l'exception**, et c'est structurel : son porteur n'est ni l'acteur ni la
cible. `AreEqual(Target@<DSLSelectors+0x60>, Parent(Owner@+0x30))` fait de la victime **Celestine**
et du porteur la **Geminae** ; et le second conjoint est écrit exprès pour qu'une Geminae **morte**
portant encore `1240` absorbe le coup. Le régime est atteignable sur un cadavre-au-chargement, et
c'est mesuré : `decisionView.units[]` conserve les morts **avec leurs effets**, `combatSnapshot` ne
les énumère pas — l'entité porte donc `1240` **sans** `StatsComponent`, et
`collect_triggered_abilities` la saute. Observable : **Celestine encaisse des dégâts que le natif
lui épargne**. Résidu **#547-r12**.

## Un verdict qui déclare une dette ne s'écrit pas par commodité

Le site `close_combat_weakness.py::_owner_active_effect_names` a d'abord été ventilé `ATTEIGNABLE`
— au sens littéral de la définition : le sujet peut être un cadavre, rien ne l'écarte. Le cliquet
**voisin** `test_aucun_verdict_ATTEIGNABLE_ne_reste_sans_gate` a rougi, et il avait raison : dans
cette table, `ATTEIGNABLE` **déclare une dette de fidélité**. Or il n'y en a pas —
`collect_effect_triggers` balaie `by_unit` sans gate de vivacité, ce qui est **fidèle** (le rail
natif `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities` ne lit
jamais `EffectComponent+0x5c`), et `_owner_gate_applies` est faux sur la face EFFET **des deux
côtés** : le natif atteint la même lecture. Inventer un gate aurait *divergé* du natif.

Le verdict juste est `INERTE-AVAL`, et la définition des deux verdicts est désormais **écrite en
tête de table** pour que le prochain n'ait pas à refaire le détour. Le cliquet, lui, n'a pas été
touché.

## Les fiches périmées, et ce que ça coûte

La fiche `#547-r6` nommait pour le volet (1) **trois** sites (`resurrect.py::tiles_are_occupied`,
`traits.py::_traits_of`, `traits.py::execute`). **Aucun** n'est le rouge courant : les deux
`traits.py` sont ventilés depuis #585, et six *autres* sites étaient arrivés. C'est la **deuxième**
fois que cette fiche est trouvée à moitié périmée — la première ayant montré que son volet (3)
rougit sur une assertion différente de celle qu'elle cite. Diagnostiquer d'après une fiche plutôt
que d'après le rouge courant fait chercher au mauvais endroit ; la fiche donne la **famille**, le
rouge donne le **site**.

## Ce qui n'est PAS couvert

- **Aucune confrontation live** : les cinq assertions sont offline par construction (prédicats purs
  et lectures de source). Le seul fait qui appellerait du live est `#547-r12`, et son montage est à
  **fabriquer** (une capture où la Geminae est déjà morte en portant `1240`), pas à attendre.
- Les volets **(3)** et **(4)** de `#547-r6` restent **rouges** sur `master`, re-mesurés à
  `8d3fe895` : `test_366_r1_bcpatch_port_blindspot_offline` sur `test_la_couverture_reste_nommee`
  (confirmant la re-mesure du 2026-08-15, pas l'énoncé d'origine), et
  `test_480r8_rpc_joignable_offline` sur **24** RPC sans canal nominatif — contre 12 à la fiche,
  soit un doublement, dont 15 joignables par le seul message de commit et 4 non exposés de
  `movement-trace.ts`. Ce dernier vit sous `frida/hooks/**` : hors périmètre d'un agent, qui ne
  réinjecte pas.
- Le tri des 23 régimes vides repose sur « un cadavre-au-chargement n'agit jamais ». C'est établi
  par deux mesures (`verify_unit_turn_ended` rend `reason: dead` avant tout `_can_act` ; aucun
  `KillUnitOperation` du run ne le concerne, donc aucune attaque post-mortem `FinalJustice`), mais
  **aucun test ne l'exerce** : c'est une lecture de code, pas un contrefactuel joué.
