# #485 — Le recenseur des différés visait le PAQUET quand l'import nomme un MODULE

**Critère binaire.** Le cliquet `probe_485_imports_differes` peut-il demander un hissage qui
**casse** le graphe d'imports ?

Avant ce cas : **oui**, et il le demandait — sur **3 sites**, tous les trois porteurs d'une raison
écrite circonstanciée qui disait vrai et que la mesure contredisait.

## 1. La faute

`_resoudre(mod, node)` rendait, pour un `ImportFrom`, le module nommé par `node.module` — donc le
**PAQUET**. Or Python résout `from PKG import NOM` en deux temps : il charge `PKG`, puis, si `NOM`
désigne un sous-module, il charge **`PKG.NOM`**. La fermeture d'un hissage est celle du module,
pas celle du paquet.

C'est exactement l'écriture que la doctrine **PRESCRIT** — la forme B (`from pkg import module`
+ accès attributaire), celle qui garde la morsure d'un `monkeypatch`. Le faux positif visait donc
les sites les **mieux** écrits, et il s'aggravait à chaque tranche qui appliquait la règle.

**Mesure du 2026-08-18, avant correctif :**

| différé | cible MESURÉE (fausse) | cible RÉELLE | verdict rendu | verdict juste |
|---|---|---|---|---|
| `entities/selectors/pathing.py:50` | `engine.services` | `engine.services.movement_query` | GRATUIT | **PORTEUR** |
| `entities/selectors/pathing.py:111` | `engine.entities` | `engine.entities.triggers` | GRATUIT | **PORTEUR** |
| `entities/selectors/tiles.py:1120` | `engine.services` | `engine.services.movement_query` | GRATUIT | **PORTEUR** |

Contre-épreuve directe, process frais : `import engine.services.movement_query` met
`engine.entities.selectors.pathing` dans `sys.modules`. Hisser aurait refermé la boucle que
`pathing._mq()` documente depuis le 2026-08-11 — la cascade
`movement_query -> runner.components -> ... -> entities.selectors -> pathing -> movement_query`,
qui rendait rouges cinq dicts consommateurs de `probe_313` étape 5.

**Le correctif tient en deux crans**, pas un :

1. `_resoudre` rend `PKG.NOM` quand `PKG/NOM.py` existe sur disque (sur-approximation SÛRE : plus
   de porteurs, donc jamais un hissage qui casse) ;
2. `classer` décide **PAR INSTRUCTION**, jamais cible par cible — un `from PKG import mod, SYMBOLE`
   en charge deux, donc il suffit qu'**une** tire l'appelant pour que la ligne soit porteuse.
   Classer par cible aurait rendu la même ligne moitié gratuite, moitié porteuse.

Effet sur le compte : **58 → 47** gratuits (les 3 faux positifs redevenus porteurs, plus la
re-clé des cibles). Le cache versionné est invalidé par le changement de contexte — coût plein
une fois, ce qui est le comportement voulu.

## 2. Ce que la faute cachait : les raisons écrites étaient PÉRIMÉES, 8 sur 8

En instrumentant les sites, on découvre l'inverse du problème précédent : **des différés classés
GRATUITS à juste titre, mais qui portaient une raison écrite affirmant un cycle**.

Contre-épreuve directe sur 8 couples nommément documentés dans le code — **8 APPELANT_ABSENT sur
8**. Aucun des cycles annoncés n'existe encore :

| site | raison écrite | mesure |
|---|---|---|
| `effects/loki/instinctive_behaviour_condition.py:74` | « `context` importe `runner.components`, qui importe CE module. Hisser fermerait le cycle » | ABSENT |
| `effects/loki/lifewards_condition.py:65` | idem | ABSENT |
| `entities/effects_state.py:392` | « hisser fermerait le cycle `effects_state -> remove_effects -> runner.state -> effects_state` » | ABSENT |
| `runner/operations/attack_prediction.py:75` | « différé PORTEUR : cycle services<->runner » | ABSENT |
| `runner/operations/displace.py:704` | « cycle displace <-> movement (PORTEUR) » | ABSENT |
| `runner/operations/transfer_damage.py:135` | « lazy : rompt le cycle damage <-> transfert » | ABSENT |
| `runner/abilities/loki/ancient_fury.py:320` | « lazy : cycle abilities<->damage » | ABSENT |
| `runner/operations/triggers/loki/battle_focus.py:234` | « différé PORTEUR : triggers <- selectors » | ABSENT |

La cause est notre propre réparation : la **vidange des barils** (#485-r1-r1) a supprimé les arêtes
de retour. Personne n'est allé relire les raisons qui les invoquaient.

**Conséquence de méthode.** L'étage 3 du probe compte les porteurs « sans raison **écrite** » et
traite l'absence comme le défaut. La mesure dit le contraire : une raison écrite **présente** est
au moins aussi trompeuse qu'une absente, parce qu'elle **survit à la disparition de son objet** et
qu'elle **décourage la vérification**. C'est pourquoi #485 ajoute `--porteurs`, qui **dérive** la
raison de la mesure au lieu de la recopier au site. Recopier 187 raisons dans des fichiers partagés
serait par ailleurs le sweep de masse que la doctrine interdit — et il faudrait le refaire à chaque
vidange.

## 3. Le sweep

**43 des 47** différés gratuits hissés, tous en **FORME B**, sur 37 fichiers.

Le contrôle `migrate_485r1_barils_reexport.py morsure` (joué AVANT tout hissage, base des gratuits
mesurée à frais sur l'arbre courant) nomme **4** `HISSAGE_DESARMERAIT`, dont **3 dans le
périmètre** — pour ceux-là la forme B n'est pas une préférence, c'est ce qui garde le patch :

| symbole | site | substitué par |
|---|---|---|
| `effects.factory.get_owner_bond_effects_added_on_ability_init` | `operations/spawn.py:956` | `test_963r5_bond_a_l_init_offline` |
| `runner.abilities.base.ability_pierce_effect_bonus` | `abilities/behaviours/combat.py:907` | `probe_910_relic_bolt_pistol_live` |
| `runner.operations.movement._kill_steppable_kill_unit` | `operations/displace.py:704` | `probe_448r1r1r3`, `probe_462_...` |

Le 4e (`abilities.targeting.targeting_options_for` @ `playbook/nonattack.py:214`) est un des trois
imports **optionnels sous `try/except`** de la base attestée : il ne bouge pas.

`probe_477r35_import_isole` rejoué après **chaque** lot : **721 modules, 0 en échec**. La mesure
lot par lot n'est pas de la prudence décorative — le tri est individuel (une instruction à la
fois) alors que l'**ENSEMBLE** peut refermer une boucle qu'aucun hissage isolé ne fermait ; un
premier lot historique avait cassé l'import de 405 modules sur 409.

## 4. Résidu #485-r5 — 4 sites laissés, par BORNAGE d'orchestration

Ils ne sont ni difficiles ni douteux : ils tombent dans des chemins réservés à d'autres agents en
vol au moment de la tranche. Le cliquet reste donc **ROUGE** sur eux, **volontairement** — les
inscrire à la base attestée serait affaiblir un cliquet pour un motif d'orchestration, et la base
ne doit que **décroître**.

| site | classe | cible |
|---|---|---|
| `playbook/prediction/abilities.py:454` | CYCLE (déjà écrit en forme B au site) | `engine.runner.abilities.custodes` |
| `services/movement_query.py:489` | CYCLE | `engine.entities.effects.base` |
| `services/movement_query.py:490` | CYCLE + REDONDANCE | `engine.runner.components` |
| `services/movement_query.py:491` | CYCLE | `engine.services.range_bonus` |

## 5. Ce que la tranche NE couvre PAS

- Les **187 porteurs sans raison écrite** restent sans raison écrite. `--porteurs` rend la mesure,
  il ne l'inscrit pas au site.
- Le critère REDONDANCE reste importé de `probe_270r4r2r2_tri_differes.gratuits`, dont la
  résolution de cible rend l'**union** `[pkg, pkg.alias, ...]` — donc il n'avait **pas** le vice
  corrigé ici, et n'a pas été touché.
- La forme B n'a été **posée** que sur les sites hissés. Les liaisons de forme A préexistantes des
  préambules ne sont pas converties : les toucher changerait la morsure de call-sites que la
  tranche n'a pas mesurés.
