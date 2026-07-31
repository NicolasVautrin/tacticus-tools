# case-341 — `kit-coverage.md` dérivait : le delta était JUSTE, c'est le FORMAT qui le rendait illisible

**Critère** : le delta de régénération de `docs/rl/kit-coverage.md` (`votanChampion` perd
`ModifiedExoarmour`) est-il juste, ou un bug du générateur ?

**Réponse, mesurée** : **JUSTE**. Les **3** entrées qui bougent s'expliquent toutes par un port
mergé *après* la dernière régénération. Le générateur n'a pas de bug de lecture — mais il avait
deux vrais défauts, corrigés ici : il était **aveugle à 2 voies d'attribution** (43 abilities
invisibles) et son tri par volume produisait **60 lignes de diff pour 3 changements de fond**,
ce qui est la cause mécanique du non-rafraîchissement.

Re-dérivation : `python scripts/python/probe_341_kit_coverage_voies.py` (voies),
`probe_341_regen_churn.py` (churn), `probe_341_dup_table_rows.py` (doublons de tableau).

---

## 1. Le delta — 3 entrées, 3 ports, toutes postérieures

Dernière régénération : `48eee1af` (2026-07-30). Total **115 → 112**.

| entrée | mouvement | voie d'attribution lue par l'audit | port |
|---|---|---|---|
| `votanChampion` / passif `ModifiedExoarmour` | sort des manquants | `ABILITY_INIT_OWNER_EFFECTS` + `EFFECT_CLASSES["ModifiedExoarmour_ExtraDmg"]` | `291b44a9` #322 |
| `necroWarden` / passif `RelentlessMarch` | sort des manquants | `ABILITY_TRIGGERS` + `EFFECT_CLASSES["RelentlessMarch_Effect"]` | `526cb0a9` #328 |
| `admecManipulus` / active `DefendTheDivineWork` (1117) | `[-D] NO-OP` → `[CD] OK` | `ABILITY_CLASSES[1117]` | `8e35a956` #334 |

Aucune information n'était écrite à la main dans ce doc : il est intégralement généré, et
`port-residuals-inventory.md` §7 l'inscrit déjà en « ne jamais fusionner un conflit, régénérer ».
La régénération était donc sans risque — c'est la **lisibilité du delta**, pas le delta, qui
bloquait.

## 2. Le défaut réel n°1 — aveugle à 2 voies d'attribution sur 5

Le précédent #323 s'applique : l'audit lisait `activeAbilities` + `passiveAbilities` + traits, soit
**2 des 5 voies** dérivables du gameconfig. Mesure sur les 127 unités `lineup` :

| voie non lue | abilities | unités `lineup` | portées par un registre |
|---|---:|---:|---:|
| `mythic` (`mythicAbilities`, à débloquer) | 11 | 11 | **0** |
| `item` (`items[*].abilityId` + `allowedUnits`, relique à équiper) | 32 | 65 | **0** |
| `relic` (`relicAbilities`) | **0** | 0 | — |

**43 abilities**, **0 couverte**. Elles sont désormais **lues et imprimées**, dans une section
dédiée **hors du total** : leur nature diffère (une mythique se débloque, une relique s'équipe), et
les fondre dans le compte ferait remonter en tête du classement un héros riche en reliques
équipables dont le kit, lui, est porté. Le total reste **112** — aucun chiffre cité ailleurs ne
bouge. Ce qui change, c'est qu'une couverture partielle **assumée** remplace une couverture
partielle **silencieuse** — le dispositif exact de #323.

## 3. Le défaut réel n°2 — un diff 3× trop gros, et c'est ce qui a tué l'instrument

Sections triées par **volume** : un seul compte qui bouge réordonne des sections entières. Mesuré
en rejouant le même changement de fond dans les deux formats (`probe_341_regen_churn.py`, qui
récupère l'ancien script à `origin/master` et retire les 3 ports des registres) :

| format | lignes de diff pour les MÊMES 3 ports |
|---|---:|
| ancien (sections par volume, lignes par volume) | **60** |
| nouveau (sections par nom, lignes par id) | **20** |

Les 20 lignes restantes sont toutes du fond : 1 pour le total, 6 pour la table de priorisation
(3 factions changent de rang), 3 titres de section, 3 paires de lignes de tableau. La
priorisation par volume n'est pas perdue : elle est devenue une **table de bilan** en tête, 1
ligne par faction. Générateur **idempotent** (2 runs consécutifs, 0 diff).

## 4. Le second constat — la cause du double-compte n'a pas frappé ailleurs

`probe_341_dup_table_rows.py` cherche la signature « deux rebases ont chacun ajouté leur ligne » :
une clé de tableau dupliquée, et un total qui ne tombe pas sur la somme des lignes qui le
précèdent. Sur `port-residuals-inventory.md` (corrigé par `5176603d`), `backlog.md` et
`port-roadmap.md` : **0 doublon**, et le total §4.g (**23**) tombe juste (4 + 15 + 4).

En revanche le balayage a trouvé une entrée **périmée** de la même famille (une PR qui ferme un
résidu sans mettre l'inventaire à jour — le défaut que §4.g dénonce lui-même) : §2.1 ligne 12,
`1117 DefendTheDivineWork`, non barrée alors que #334 l'a portée. Corrigée ici.
`probe_decision_noop_gap.py` re-dérivé le 2026-07-31 : **13** actives « décident sans exécuter »,
et 1117 n'y figure plus.

## 5. Ce qui n'est PAS couvert

* **Les 43 abilities conditionnelles ne sont ni portées ni confrontées** — elles sont désormais
  *visibles*, ce qui est tout ce que cette passe établit.
* **Les 4 voies non dérivables** (`trait`, `liveevent`, `summon`, `tile`) restent hors de portée,
  comme dans `unit_map` (`case-323` §2).
* **Le reste de §2.1 n'a pas été re-confronté** : 3 abilities du gisement `[-D]` courant
  (`1185 ForwardObservers`, `1222 MassDriverAccelerator`, `1227 HeavyWarpFlamer`) n'y figurent
  pas — elles y sont entrées après sa rédaction. Le re-dériver demande une passe, pas un ajustement.
* **Le prédicat de couverture reste une approximation de registres** (convention de nommage des
  effets) : inchangé par cette passe, et toujours à trancher au recon du kit.
