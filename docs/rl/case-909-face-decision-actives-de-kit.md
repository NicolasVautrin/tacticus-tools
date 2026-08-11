# #909 — La face DÉCISION des actives de kit : le quatrième canal, et une ventilation qui ne ventile rien

**Build** `rnca9r7q6c` · **mesuré** le 2026-08-11 sur `f84c7c2f` · **outil**
`scripts/python/probe_909_decision_actives_kit.py` · **cliquet**
`scripts/python/tests/engine/test_909_decision_actives_offline.py` · **table**
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv`

Tous les chiffres ci-dessous se **re-dérivent** (`python probe_909_decision_actives_kit.py`).
Ne pas les citer : les re-jouer.

## 1. Le chiffre

Sur les **138** actives distinctes des unités `kind == lineup`, **62** n'ont leur face DÉCISION
portée par **aucun** des trois registres (`playbook.noncomparable.PLAYBOOKS`,
`playbook.base.REGISTRY`, `active_ability._SPECIAL_ABILITY_CLASSES`) ; **76** l'ont.

`audit_kit_coverage.py` calculait déjà ce booléen mais ne le **comptait** pas : son total
`missing` ne retient que la face COMBAT. Cet axe n'avait donc jamais été chiffré pour lui-même.

## 2. La frontière : `PlaybookDatabase` porte QUATRE dicts, pas un

C'est la **structure** qui sépare les populations, pas une convention de nommage. Relu au
décompilé des cinq entrées de `IdunBattle.AI.PlaybookDatabase` :

| champ | entrée native | clé | entrées | inventorié par |
|---|---|---|---:|---|
| `+0x68` | `PlaybookDatabase$$LoadPlaybook(ability, fallbackToDefault)` | `ActiveAbilityType` | **233** | **#909 (ici)** |
| `+0x88` | `PlaybookDatabase$$LoadPlaybook(ability)` | `TriggeredAbilityType` | 109 | #419 |
| `+0x98` | `PlaybookDatabase$$LoadPlaybookNonOwner(ability)` | `TriggeredAbilityType` | 28 | #433-r4-r3, #477-r33/r35/r37 |
| `+0xa8` | `PlaybookDatabase$$LoadPlaybook(specificBehaviour)` | `UnitSpecificBehaviourType` | 4 | **aucun** (`#909-r4`) |

`+0x80` porte en plus un delegate **unique** — le builder de
`IdunBattle.AI.Playbook.Common.DefaultActiveAbilityPlaybook`, servi par
`$$LoadDefaultActiveAbilityPlaybook` quand `+0x68` n'a pas la clé et que `fallbackToDefault`
est vrai. Les cinq entrées ont le même squelette : cache, sinon dict de builders, sinon `0`.

Les inventaires livrés vivent **tous** sur `+0x88` et `+0x98`, donc sur `TriggeredAbilityType`.
`case-419` §1 nomme explicitement le canal des actives pour dire qu'il ne l'inventorie **pas** ;
c'est cette frontière que #909 franchit.

**Témoin croisé** : `+0x98` rend **28** entrées — exactement les 28 concrets non-owner comptés
par #477-r33 et #477-r37 via une voie entièrement indépendante (filtre par PARENT dans
`frida/classes.tsv`). Deux lectures indépendantes qui concordent ; l'étage 5 du cliquet garde
cette concordance.

## 3. La ventilation demandée est DÉGÉNÉRÉE — et c'est le résultat

La question posée était : parmi les 62, lesquelles ont un playbook natif (travail réel) et
lesquelles n'en ont aucun (rien à faire) ? Réponse mesurée : **62 et 0**.

Ce `62 / 0` **ne ventile rien**. Le prédicat est **constant** sur la population : **138 des 138**
actives de kit `lineup` sont des clés de `+0x68`. Publier « 62 / 0 » se lirait comme une
ventilation informative alors que c'est une tautologie — un accord obtenu en régime dégénéré ne
prouve rien. Le probe l'imprime explicitement, et l'étage 7 du cliquet tombera le jour où le
régime changera (des actives de kit hors `+0x68`), en demandant la réécriture de cette fiche.

## 4. Le discriminant réel : la SUBSTANCE, un cran plus bas

Même mouvement que `case-419`, qui avait dû descendre au corps des méthodes (seuil de trivialité
à 0x80 octets). Ici, deux crans successifs :

**(a) la classe construite.** Sur les 233 clés actives, **une seule** — `1015 PrecisionShot`, hors
kit `lineup` — est appariée au playbook **par défaut**. Les **62** ont donc toutes une classe
**propre**, et aucune n'est un « rien à faire » déguisé.

**(b) les méthodes qu'elle porte.** Dérivées du binaire, **jamais** d'une liste blanche — une
première version filtrait sur des noms présumés (`CalculateCustomUtility`, `GetUseProbability`, …)
et **ratait `EvaluateNonComparable`, le nom le plus fréquent du gisement**. C'est le vice que le
CLAUDE.md nomme : une liste blanche ne peut pas montrer ce qu'elle a oublié.

**La ventilation utile**, dérivée de la méthode portée, par registre visé :

| registre visé | n | signature native |
|---|---:|---|
| `playbook.noncomparable.PLAYBOOKS` | **47** | `EvaluateNonComparable` surchargée |
| `_SPECIAL_ABILITY_CLASSES` (prédiction) | **12** | `MakeDamagePredictions` surchargée |
| `playbook.REGISTRY` (comparable, terme custom) | **3** | ni l'une ni l'autre, méthodes propres |
| indéterminé | **0** | — |

Somme = 62, partition exhaustive, **0 indéterminé** (étage 6 du cliquet). `methodes propres` est
une **borne inférieure** : IL2CPP déduplique les corps triviaux, donc une absence dans
`ghidra/functions.tsv` ne prouve aucune non-surcharge.

## 4bis. Ce qui était déjà suivi : **6 sur 62**

Critère : la **classe** de playbook (`<X>Playbook`) citée dans `docs/rl/backlog.md` — jamais le
**nom** de l'ability, qui y figure pour 50 des 62 au titre de leur face **COMBAT**, autre axe.

Six seulement : `1005 AdaptiveStrategy`, `1017 FragBomb`, `1049 CrusadeOfWrath`,
`1160 HeavyRailRifle`, `1211 RitesOfMorkai`, `1106 WarHowl`. Deux d'entre elles ont un résidu
individuel formé (`#893-r1`, `#906-r1`), ouverts par les tranches qui avaient porté la face
COMBAT de la même ability et avaient constaté la face DÉCISION manquante **au passage**.

**56 des 62 n'avaient donc aucun résidu de face décision ouvert** — le gisement était entamé au
détail, ability par ability, sans que personne n'en connaisse la taille.

## 5. Contrôles inverses — l'inventaire doit aussi se retourner

- actives **portées** sans playbook natif (port fantôme) : **0** ;
- actives **portées** appariées au playbook par défaut (port de vide) : **0** ;
- clés natives absentes du mirror `ACTIVE_ABILITY_TYPE` : **0**.

Ces trois zéros sont les invariants 1 à 3 du cliquet. Ils gardent le gisement que **notre propre
cadence alimente** — inscrire une ability à un registre de décision sans playbook natif
correspondant ne lève rien, ne casse aucun test, et fait croire la face couverte : même signature
de dégradation que `TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE`.

## 6. Comment la table native est lue (et pourquoi elle refuse plutôt que de deviner)

`InitializePlaybookBuilders` fait **64 688 octets** (le décompilateur y expire) : elle est
**désassemblée**. Trois gardes, toutes exécutables :

- **couverture** — le désassemblage linéaire doit couvrir l'octet final ; une désynchronisation
  ferait sous-compter en silence, donc elle **REFUSE** (mesure : 0 trou, 0 octet restant) ;
- **trampolines dérivés** — `Dictionary.Add` est appelée soit directement, soit par un trampoline
  qui prend la clé dans `edx`. Les trampolines ne sont pas en dur : ils sont **découverts** en
  cherchant, parmi les cibles de `call`, celles dont le corps appelle `Add`. Les rater aurait
  perdu **280 des 374** entrées ;
- **appariement tranché, jamais supposé** — le slot du cache `<>9__31_N` ne donne pas directement
  l'index de lambda. Le décalage est choisi par **concordance de noms** (`<Ability>` ↔
  `<Ability>Playbook`) parmi cinq candidats : `+1` rend **221/233**, les autres **0 à 2**. Le
  probe refuse si aucun candidat ne domine.

Aucune adresse en dur : tout se résout par **symbole** dans `data/symbols/<build>/ghidra/functions.tsv`.
La table produite déclare son build et le lecteur **REFUSE** une table d'un autre build.

## 7. Ce que cette mesure NE couvre PAS (imprimé à chaque exécution)

- **556 unités écartées** (`npc` 491, `summons` 65) — seul `kind == lineup` est visité ;
- les **voies conditionnelles** : `mythicAbilities` et la relique `items[*].abilityId` ne passent
  pas par `activeAbilities` (cf. `case-323`), donc une active de relique est invisible ici ;
- les dicts `+0x88` (109), `+0x98` (28), `+0xa8` (4) : **recensés et comptés**, non confrontés au
  port — les deux premiers ont leurs inventaires, le troisième n'en a aucun (`#909-r4`) ;
- la **fidélité** des 76 faces portées : ce probe atteste leur **existence**, jamais leur justesse ;
- le régime SPAWN et toute confrontation **live** : la tranche est intégralement offline.

## 8. Résidus ouverts

`#909-r1` (les 12 `MakeDamagePredictions`), `#909-r2` (les 3 comparables à terme custom),
`#909-r3` (les 47 non-comparables, à découper), `#909-r4` (le dict `+0xa8`, jamais inventorié),
`#909-r5` (l'audit de kit ne compte pas la face décision dans son total). Voir
`docs/rl/backlog.md`.
