# #420-r2 / -r3 / -r5 — la quote verbatim du helper de publication : quatre formes à ancrer, et une DÉCIDABILITÉ à fabriquer

**Verdict : quotes `FUN_` ambiguës 16 → 0, ancrées 1 → 23, et `probe_283:on` cesse d'être un
compteur.** Les trois résidus tombent ensemble parce qu'ils partagent une seule question : que
peut-on prouver d'un nombre recopié verbatim d'un décompilé ?

## 1. L'ancre — trois formes manquaient, une seule cause

`_FUN_PUB` n'admettait que `FUN_<addr>(0x4d|0x50, .., <n>)`. Les quatre formes réelles :

| tête | forme | helper natif |
|---|---|---|
| `0x4d` | `(0x4d, <static>, <events>, <n>)` | `FUN_1800280e0` |
| `0x50` | `(0x50, .., <n>, <entities>)` | `FUN_1800280e0` |
| `0x51` | `(0x51, .., <n>, &args)` | **`FUN_1800284a0`** — 8 arguments (#420-r2) |
| `..` | `FUN_<addr>(.., <n>)` — élision **de notre écriture** | (#420-r3) |

**#420-r2 décrivait un obstacle qui n'en est pas un.** « Le littéral y est l'AVANT-dernier
argument » est vrai de la *position* — mais `&args`, comme `entities`, n'est pas un littéral,
donc l'avant-dernier argument **EST** le dernier littéral, et l'extraction existante le capture.
Seul le slot manquait au motif.

**Le slot `0x51` est LU au décompilé** (`rnca9r7q6c`, 2026-08-07) :
`IdunBattle.Operations.FinishUnitTurnOperation$$Execute` publie trois fois
(`FUN_1800284a0(0x51, .., unit, unit, unit, 0x1c|0x28|0x29, &args)`, les deux dernières sous
`UnitFlagsComponent$$Add(3)` et `isTerminated == 0`) ;
`IdunBattle.Operations.ResurrectUnitOperation$$Execute` publie `0x2e` de même.

⚠ **Un slot n'identifie une méthode que DANS son interface.** Le seul `0x51` du dépôt est
`FUN_180003bd0(0x51, itf, service, caster)` = `BattleQuery$$GetFreeAdjacentTiles`, sans rapport.
Il ne porte aucun littéral, donc rien ne s'y ancre — mais c'est une coïncidence heureuse, pas
une garantie. La garantie est ailleurs (§2) : **l'ancre seule n'est jamais un gate**.

Mesure : `0x51` a **0 site** dans `scripts/python` — l'ancre y est préventive. L'élision en a
**2** (`probe_120`, `sworn_protector.py`).

## 2. La décidabilité — la piste écrite en #420 §9 ne tient pas, et sa mesure dit pourquoi

Le résidu proposait « un commentaire de fin de ligne portant le membre, que 4bis garderait
alors ». **Mesuré sur les deux quotes qui en portaient déjà un** : `anvil_shield.py:39` a
**8 caractères** de séparateur (la limite EXACTE de 4bis) et `martial_superiority.py:61` en a
**21** — le padding d'alignement d'un bloc de décompilé recopié bat tout critère de proximité
textuelle. Le critère est donc la **LIGNE**, comme `_historique` — même fichier, même leçon.

**Le voisinage heuristique est mesuré et ÉCARTÉ.** Chercher dans ±3 lignes un membre dont
l'ordinal vaut la valeur de l'ancre rend 11/18 quotes décidables — mais appliqué aux ancres
`On(` du même balayage, il produit **3 « périmées prouvées », 3 FAUSSES** :

| site | ancre | membre apparié | réalité |
|---|---|---|---|
| `probe_462…_haywire_pose.py:124` | `On(0x29)` | `UnitFinishedTurn` | étiquette le `0x28` de la ligne **précédente** |
| `engine/runner/operations/movement.py:14` | `On(0x36)` | `PostUnitKill` | étiquette le `0x35` **voisin** |
| `engine/runner/operations/movement.py:385` | `On(0x36)` | `PostUnitKill` | idem |

C'est le faux positif de voisinage que 4bis avait déjà payé sur la virgule et le slash.
**Un gate ne se fonde pas sur ce qu'un texte porte PRÈS, mais sur ce qu'un auteur a DÉCLARÉ.**

### La forme retenue : `On(<Membre>)` sur la ligne

Membre **nu**, ce qui la distingue de `On(<n> = <Membre>)` (forme que l'étape 4 confronte déjà).
`annotation_de_ligne` rend trois états, dans cet ordre — la monotonie est ce qui interdit un
rouge quand un vert est disponible :

* `ancree` — un `On(<Membre>)` de la ligne a pour ordinal **courant** exactement la valeur ;
* `perimee` — aucun ne l'a, mais l'un a pour ordinal **archivé** exactement la valeur. Même
  critère PROUVÉ que 4bis ⇒ **FAIL** ;
* `nue` — rien, ou un nom qui n'est membre d'`EventTriggerType` sur aucun des deux builds.

**Le gate ne mord QUE là où quelqu'un a déclaré le membre.** C'est ce qui autorise d'élargir
l'ancre (slot `0x51`, slot élidé) sans risquer un faux rouge structurel : une ancre mal posée
gonfle un compteur, elle ne rougit pas.

## 3. Ce que ça arme

Au **prochain** changement de build, `old` devient l'actuel : chaque quote annotée dont
l'ordinal a glissé bascule en `perimee` ⇒ FAIL, **sans qu'une ligne du dépôt ait bougé**. C'est
le gisement exact de #283, et aucun déclencheur sur diff ne peut le voir.

`Rougit = 'compteur'` est retiré de l'entrée `probe_283:on` — une déclaration morte est
elle-même un rouge de `probe_439`, dans les deux directions. `probe_439` re-joué : **PASS**.

## 4. Les 22 quotes annotées — chaque littéral LU au décompilé de `rnca9r7q6c`

| symbole natif | littéraux | garde |
|---|---|---|
| `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` | `0x2a` → `0xb` → `0xc` → `0xe` | par adresse croissante |
| `IdunBattle.Operations.AddEffectOperation$$Execute` | `0x3d` | **aucune** (racine), puis `0x3e`, `0x46` |
| `IdunBattle.Operations.ADamageOperation$$RegisterFinalDamage` | `0x42` | dernière instruction |
| `IdunBattle.Operations.ReviveUnitOperation$$Execute` | `0x2d` | 8 null-checks |
| `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` | `0x3c` / `8` | `if (didBlock != 0)` / inconditionnel |

Au passage, **deux `0x2b` PÉRIMÉS** dans `probe_120_pre_unit_ability_fork.py` (ordinal
`gqfc5mff6c` de `PreUnitAbility`) : le paragraphe se contredisait d'une ligne à l'autre
(« le natif émet `0x2b` … (`FUN_1800280e0(0x4d, .., 0x2a)`) ») et **aucune étape ne le voyait** —
ni ancre `On(`, ni membre au séparateur court.

⚠ La piste `AnvilShieldFrozenAttackerAdvantageAbility` **n'existe pas** dans le binaire : les
symboles réels sont `…Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateBehaviour`
/ `$$CreateTrigger` et `…Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger`,
**trois fabriques DSL sans aucun appel du motif de publication**. `UnitBlocked` part de
`ADamageOperation$$EvaluateAfterHitTriggers`.

## 5. Cliquet

`tests/test_enum_ordinal_ratchet_offline.py` — 7 étages neufs (25 passed, 141 s), dont :

* les DEUX directions du gate (`ancree` / `perimee`), avec **auto-contrôle** que le détecteur
  mord (`old[PreUnitAbility] == 0x2b` assertionné) ;
* le **gisement** : `test_le_depot_ne_porte_AUCUNE_quote_de_publication_INDECIDABLE` — zéro
  quote `FUN_` décalée sans annotation. Une quote neuve non annotée le rouvre ;
* le gate sur l'arbre, avec **assertion de non-vide** (`assert ancrees`) : un gate joué sur un
  ensemble vide passerait pour vert sans rien garder.

## 6. Ce qui n'est PAS couvert

* **Les 144 `On(<n>)` NUS** restent le résidu **#283-r1**. Le gisement s'est ré-ouvert depuis
  #420 (qui l'avait ramené à 0) : c'est la cadence du dépôt, exactement ce que §8 de `case-420`
  annonçait. Le mécanisme d'annotation leur est applicable — la forme `On(<n> = <Membre>)`
  existe déjà et est meilleure (elle entre dans l'étape 4).
* **Les quotes STABLES non annotées** ne sont pas gardées aujourd'hui ; elles le deviendront
  d'elles-mêmes au prochain build (elles passeront « décalées », donc le cliquet du §5 les
  nommera). Choix assumé : annoter les 31 quotes du dépôt aurait demandé la RE des ~9 littéraux
  restants sans rien fermer de plus aujourd'hui.
* **`docs/`** — hors périmètre (`--racine scripts/python`), rangé sous #283-r2.
* **#420-r4** (15 citations « à lire » de l'étape 4) : hors sujet, ce ne sont pas des
  `EventTriggerType`.

## 7. Reproduire

```
python scripts/python/probe_283_enum_ordinal_sweep.py --step on -v
python -m pytest scripts/python/tests/test_enum_ordinal_ratchet_offline.py -q
python scripts/python/probe_439_cliquet_peut_rougir.py
```
