# case-10025 — cinq rouges de `master`, une seule forme : le recenseur ne visite pas ce qu'il croit

`#10025`. Cinq cliquets rouges sur `609c8a53`, tous de la famille « UN RECENSEUR NE PEUT PAS RENDRE
ZÉRO SUR CE QU'IL NE VISITE PAS ». Chacun a été **tranché par une mesure**, jamais par l'hypothèse
la plus probable : deux des cinq n'étaient pas des inventaires faux, et **un accusait juste**.

| item | verdict | ce qui l'établit |
|---|---|---|
| `#421-r2` `test_421_effect_active_gate_offline` | **le cliquet a RAISON** | 6 classes au registre sans rail ; l'une, rail TARGETS confirmé au décompilé, **sans son gate** |
| `#287-r5-r3` `test_287r5_dynamic_target_rules_offline` | **prémisse EXPIRÉE** | dette `19 → 0` ; les 15 ids d'`ETAGE_BLOQUANT` rendent tous `surcharge` |
| `#462-r4b-r1-r1-r2` `test_462_..._defender_additive_carriers_offline` | **inventaire FAUX** | les 2 accusés rendent `for_addition(False, 0)` — magnitude littéralement nulle |
| `#498-r4-r2` `test_498r4_face_decision_is_displaceable_offline` | **inventaire FAUX** | le corps a été déplacé par `#977` dans un **second** foyer, invisible au recenseur |
| `#566-r1-r2` `test_566r1_sure_kill_gate_offline` | **prémisse EXPIRÉE** | `graviton_rifle` est un 4ᵉ lecteur réel (AST), **déjà nommé** dans la fiche |

## 1. `#421-r2` — le seul qui accusait juste, et il a trouvé un bug

`probe_229.RAIL` est saisi à la main ; il ne peut rien dire d'une classe absente. Six l'étaient.
Rail de chacune **confirmé dans la table du build `t6dpr4k06g`** :

* `BattleFocusEffectTrigger` → `IdunBattle.Entities.Effects.Loki.BattleFocusEffect$$CreateTargetTrigger` — **TARGETS** ;
* les deux `CallRipperSwarms*` → `...CallRipperSwarms_PendingSummonEffect$$CreateHandleTriggerAbilitiesInternal` ;
* les deux `FiringPosition*` → `IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal`
  (la sous-classe n'override pas ce corps — établi par le **comptage** de son bloc `methodPointers`,
  jamais par l'absence dans une table indexée par adresse) ;
* `LifewardsProtectingRemove` → `IdunBattle.Entities.Effects.Loki.LifewardsProtectingEffect$$CreateRemoveEffectTrigger`.

**Le bug.** Corps relu : `On(0xb, alive:1) & AbilityHasAttackType(..., 0) & (get_OwnerIsTarget |
get_OwnerIsCaster) & (NOT IsMoving & CanMove)` — un vrai trigger de cible, donc
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` teste
`EffectComponent.IsActive @+0x5c` avant `ShouldTrigger`. Le port ne le lisait pas. Gate posé
(`_battle_focus_flag_is_set`), dégradation **permissive** sur instance absente — même direction et
même raison écrite que `effect_triggers._ranged_auto_attack_flag_is_set`.

⚠ **Portée honnête : le gate est FIDÈLE mais INERTE aujourd'hui.** `_active_condition_is_ported`
rend `False` pour 1199, donc aucun chemin porté n'écrit `active = False` sur cette instance. Il ne
change aucun comportement observable en l'état ; il aligne le port sur le rail et ne pourra plus
être oublié. **Non confronté live.**

## 2. `#287-r5-r3` — le cliquet rougissait sur sa propre résorption

La dernière ligne était `assert res["dette"]` : elle exigeait que la **DETTE** reste non vide. Or la
dette est exactement ce que les tranches `#287-*` éteignent. *Asserter le non-vide : oui sur le
TÉMOIN, jamais sur le GISEMENT.*

Mesure : `dette 19 → 0`, 85 ids visités, 60 symboles natifs lus, 53 évaluables, 32 en corps de base.
`ETAGE_BLOQUANT` est **vidée**, pour la raison que le commentaire de `DeathOnTheWind` (`#287-r11`)
avait déjà écrite — une entrée d'étage pour une règle *portée* n'est jamais imprimée, donc c'est une
déclaration muette et fausse.

**Ce que ce vide coûte est remplacé** : `fantomes` boucle sur cette table et devient vacant. Il
gardait « `ghidra/functions.tsv` répond encore aux noms qu'on lui demande » — désormais tenu par le
**non-effondrement** (planchers symboles/population). Le cliquet actif devient `orphelins`.

## 3. `#462-r4b-r1-r1-r2` — l'inventaire ne lisait pas la magnitude

`for_addition(owner_is_caster: bool, value: int)` : le recenseur ne regardait que le **premier**
argument. Les deux accusés rendent `for_addition(False, 0)` — un `EffectBonus` à formules nulles
dont l'unique rôle est de porter la gate du bloc `IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense`
où `IgnoreArmor()` est évalué. Un montant nul ne peut pas être « au mauvais étage » : le placement
pré-perçage est l'identité dessus.

Ventilation mesurée, séparation nette, aucun cas mixte : **5 producteurs** (magnitude = expression)
= les 5 attestés ; **2 porteurs de gate** (littéral 0) = les 2 accusés.

L'exclusion est **re-mesurée en exécutant** : gate ouverte, face défenseur, magnitude nulle, **et
pénétration d'armure non nulle**. Ce quatrième point est le vrai critère — le montant existe, il vit
sur l'axe ARMURE. Un effet nul sur les deux axes serait un effet mort, et le test le dit.

⚠ Le risque n'était pas théorique : les deux docstrings de mirror **interdisent** de supprimer ces
appels comme « inutiles, ils valent zéro » (cela désarmerait la pénétration). Un cliquet qui les
accuse pousse à ce geste.

## 4. `#498-r4-r2` — un seul foyer connu, alors que `#977` en avait créé un second

`delegue` valait `FOYER_CALL in appels`, avec le foyer RUNNER **écrit en constante**. `#977` a
déplacé le corps de `loki_custom.MortisRoundPlaybook._is_displaceable` dans
`playbook/displace_utility.py::is_displaceable`. La délégation vers ce second foyer était invisible :
le site, parfaitement porté, sortait `NON-PORTE`.

C'est le vice qu'`_alias_traits_global` avait **déjà** corrigé un cran plus bas, sur l'axe des
constantes : **le recenseur récompense la duplication**. L'axe des APPELS avait gardé le défaut que
l'axe des NOMS avait perdu.

⚠ **Et le remède pouvait être pire que le mal.** L'ancien `delegue` créditait les **cinq** conditions
d'office — juste tant que l'unique cible était le foyer RUNNER, qui les porte toutes. Généralisé tel
quel, il aurait rendu `manque = []` pour le délégant alors que `displace_utility::is_displaceable`
n'en porte que **trois**. Un délégant hérite désormais de ce que sa cible porte : **le manque
traverse**, et un test le fige, avec sa garde de non-vacuité (le délégataire doit manquer quelque
chose, sinon l'égalité ne distingue plus l'héritage fidèle du crédit d'office).

Résolution d'un appel : **d'abord dans le même fichier**, sinon globalement — sans cette priorité,
l'homonymie `_is_displaceable` (quatre définitions) ferait hériter `momentum::_suppress_or_stun`
d'un manque qui n'est pas le sien. Recensement : miroirs DECISION 3 → 6, RUNNER 7 → 8, « cités mais
non portés » 6 → 3 ; cliquet RUNNER inchangé (0 copie, 0 incomplet).

## 5. `#566-r1-r2` — trois xrefs natives ne font pas trois modules Python

La docstring du fichier **nommait déjà** `GravitonRiflePlaybook$$ShouldEvaluate` en tête des trois
xrefs entrantes de `IdunBattle.AI.Playbook.BasePlaybook$$EnemyWillBeKilledWithNormalAttack` ; seule
l'assertion, écrite avant le port (`#975`), ne l'avait pas. La cause du glissement est que le corps
COMDAT `VexillaMagnificaPlaybook$$ShouldEvaluate` est **partagé** par `HammerOfWrath` : les trois
xrefs se portent en **quatre** modules. L'effectif Python n'est contraint par rien de stable.

Le compte figé est remplacé par un critère : non-rétrécissement · **adossement natif** (tout lecteur
cite `EnemyWillBeKilledWithNormalAttack`) · non-confusion avec `will_normal_attack_kill` (l'autre
corps natif, par cible) · non-vacuité. Les trois crans mordent sur trois lignes **distinctes**.

⚠ Le durcissement AST (le recenseur lisait la source par `re.search`) **ne change aucun verdict
aujourd'hui** : mesuré, regex et AST coïncident (0 module crédité par la seule prose). Il ferme la
porte, il ne répare pas le rouge — c'est dit pour que personne ne le lise comme la cause.

## 6. Contre-épreuves — 9 mutants, 9 rouges

| mutant | attendu | mesuré |
|---|---|---|
| gate `BattleFocus` retiré | `probe_229` + 2 tests | 1 gap TARGETS, 2 fichiers rouges |
| entrée RAIL retirée | `probe_421` + test | 1 trou de recensement |
| délégué crédité des 5 conditions d'office | test `#498-r4-r2` | **2** tests rouges |
| `for_addition(False, 0)` → `(False, 5)` | ré-accusé | 2 tests rouges |
| pénétration d'armure forcée à 0 | cran (4) | rouge |
| `supreme_commander` n'appelle plus le foyer | non-rétrécissement | rouge |
| `graviton_rifle` ne cite plus le symbole | adossement | rouge |
| un lecteur lit AUSSI l'autre foyer | non-confusion | rouge |
| `SUFFIXE` renommé (régime inter-build) | plancher `#287-r5-r3` | probe FAUTES + test rouge |

## 7. Ce qui n'est PAS couvert

* **Le gate `BattleFocus` n'est pas confronté live**, et il est structurellement **inerte**
  aujourd'hui (§1) — aucun montage ne peut le rendre discriminant tant qu'aucun chemin porté ne
  désactive l'instance 1199. Le verdict repose sur le décompilé et sur trois régimes synthétiques.
* **Le `RAIL` reste saisi à la main.** Un croisement avec le symbole cité au site a été **mesuré**
  (101/104) puis **écarté** : les 3 exceptions sont des écritures *correctes* (un module cite
  l'arbre produit, ou la classe native sans le nom de la méthode), donc le cran punirait une bonne
  pratique. `probe_421` reste exhaustif par construction (registre ↔ RAIL) ; c'est lui qui garde.
* **`ETAGE_BLOQUANT` vide rend `fantomes` vacant** — c'est écrit au site, et le non-effondrement le
  couvre. Le cran redevient armé dès qu'une entrée y revient.
* **Rouge PRÉEXISTANT, hors périmètre, non porté** : `tests/test_337_dsl_triggers_attestation_offline.py`
  (`IsInTeam`, `IsPartialAttackAbility`, `IsSpawnTile` non tranchées) — vérifié rouge sur un arbre
  témoin détaché à `609c8a53`, **avant** cette tranche.
