# #270-r4 — les TROIS rôles de littéraux entiers que le tri n'avait jamais visités

**62 littéraux nommés, 279 scalaires assumés, 1 fausse attribution évitée.** Mirror neuf
`EffectTargetType`. Value-preserving vérifié par empreinte VALEUR (0 divergence sur 155 933 clés).

## 1. Ce qui restait, et pourquoi c'était le cas dur

Les quatre volets précédents disposaient tous d'un discriminant **structurel** : la couverture du
groupe (clé de dict, élément de conteneur) ou le nom de la cible d'affectation. Les trois rôles
d'ici — `argument d'appel` (189), `expression` (103), `comparaison` (49), soit **341 positions** —
sont des positions **isolées** : aucun voisin ne les contraint.

Le seul discriminant est donc, **site par site**, le NOM déjà écrit au site ou le **TYPE DÉCLARÉ**
lu dans `data/symbols/<build>/frida/methods.tsv`.

## 2. Résultat du tri

| | avant | après | après REBASE |
|---|---|---|---|
| candidats (`probe_270r1 --croiser`) | 613 | 549 | **551** |
| `argument d'appel` | 189 | **144** | **144** |
| `comparaison` | 49 | 32 | **33** |
| `expression` | 103 | **103** | **103** |
| `valeur par defaut` (effet de bord, mêmes sites) | 20 | **18** | **18** |

⚠ **Le rebase (23 commits) a apporté +2 candidats — le gisement que notre propre cadence
alimente, mesuré en direct.** Un seul tombe dans les trois rôles de cette tranche, et le tri a été
refait dessus : `runner/snapshot.py` — `" ..." if len(montrees) > 4 else ""`, un seuil d'aperçu
dans un message d'erreur, donc **SCALAIRE**. Comparaison faite par (fichier, valeur, source) et non
par numéro de ligne — `spawn.py` et `snapshot.py` ont grandi, et un diff par ligne aurait rendu
**28 faux « nouveaux »**.

`expression` ne bouge **pas d'un site**, et c'est le résultat : ses 103 positions sont
**intégralement** des `int(x or 100)` de multiplicateur. `100` occupe à lui seul **100** des 279
positions restantes.

**75 membres écrits sur 26 fichiers, 48 membres distincts, 0 membre perdu** (delta AST dérivé,
jamais retranscrit). 75 pour 62 littéraux : les six `SubEffectSpec` de `status.py` dérivent
désormais l'**id ET le nom** du même membre, et six littéraux voisins de magnitude ≤ 3 — hors
périmètre du recenseur mais sur les **mêmes appels** — ont été convertis avec eux.

## 3. Quatre attributions par SIGNATURE LUE, pas par nom

| enum | type déclaré, lu dans `frida/methods.tsv` | sites |
|---|---|---|
| `IdunBattle.Entities.Enum.EffectTargetType` | `DSLTriggers.HasEffect(…, targetType)` + 4 voisins | 4 |
| `IdunBattle.Streams.TagKey` | `DSLBehaviors.Inform(tag, value)` | 5 |
| `IdunBattle.Streams.GroupType` | `DSLBehaviors.Group(…, groupType)` | 3 |
| `IdunBattleLogic.Utils.Hex.Corner` | `BattleQuery.GetTilesInTriangleShape(…, direction)` | 6 |

⚠ **Le port nommait le premier paramètre d'`Inform` `message_type` — c'est FAUX.** Le type déclaré
dit `tag : IdunBattle.Streams.TagKey`. Le nom du port a survécu parce qu'aucun ordinal ne le
contredisait ; seule la signature le corrige.

⚠ `Corner` a **cinq homonymes** dans le build (Unity/SimpleUI) — l'appariement se fait par nom
PLEIN. `EffectTargetType` n'en a **aucun**, et c'est l'exception : le test le **mesure** au lieu de
le supposer, pour qu'un build qui en introduirait un rougisse.

## 4. La fausse attribution évitée — et elle aurait été SILENCIEUSE

`entities/triggers.IsNormalAttack` comparait `ctx.attack_ability_type == 1013`. **`1013` EST un
membre valide d'`ActiveAbilityType` : `PrecisionShot_Attack`.** Le convertir aurait *résolu*, n'aurait
rien cassé, et aurait écrit le mauvais concept — le décompilé nomme ce littéral
`AbilityOrEffect 0x3f5`, argument du `DirectAbilitySelector` de la 2ᵉ branche d'
`IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack` : un marqueur de **KIND**. Le build ne publie
aucun enum `AbilityOrEffect` ; le foyer nommé du dépôt est
`runner/abilities/attack_type.NORMAL_ATTACK_KIND` (= `lord_of_tempests.SMITE_KIND`).

⚠ **La garde qui interdit cette faute a d'abord été SILENCIEUSE SUR ELLE.** L'étage 6 mesurait
(a) que l'ordinal résout des deux côtés, (b) qu'il n'est pas dans `REGULAR_ATTACK_ABILITY_TYPES`,
(c) que le site discrimine. La **contre-épreuve** — réécrire le site en
`int(ActiveAbilityType.PrecisionShot_Attack)` — l'a laissé **VERT** : les trois volets mesurent des
VALEURS, et la valeur est la même. C'est la confusion silencieuse reproduite *à l'intérieur* de la
garde censée l'empêcher. Le cran ajouté (`etage6b`) lit l'**AST du site** et exige le nom.

## 5. Value-preserving

Empreinte de **tout** `engine/` (attributs de module **et** de classe), arbre témoin extrait
**complet** (`git archive HEAD`, `data/` compris), canonicalisation par `int(x)` **récursive**.

```
                            cles communes   divergences   disparues   apparues
avant rebase (HEAD)            155 933            0           0         1 605
APRES REBASE (origin/master)   155 917            0           0         1 622
```

Les clés APPARUES sont **100 %** attribuables à un enum nouvellement importé dans le namespace du
module (251 `TagKey` ×5, 112 `UnitTrait`, 111 `GroupType`, 34 `UnitFlag`, 13 `Corner` ×3, 17
`StatPart` ×2, 10 `EffectTargetType` ×3) — un import ajoute le symbole au module, sans toucher
aucune valeur. **0 clé non attribuable.**

## 6. Contre-épreuves — la garde MORD, et sur le bon étage

**9 mutations / 9 rouges**, chacune sur l'étage visé : ordinal nu revenu (direct **et par alias**),
renumérotage du mirror, mirror retiré du registre, mirror non bijectif, littéral sous cycle changé
de sens, site 1013 mal converti, scalaire assumé muté (valeur **et** forcé en enum).

Deux mutations ont d'abord échoué et **les deux ont appris quelque chose** :
- la mutation « 1013 mal converti » passait VERTE → l'étage 6 ne gardait pas le site (§4) ;
- la mutation « scalaire forcé en enum » rendait `rc != 0` **sans aucun `FAILED`** : elle cassait la
  **collecte** (cycle d'import). Une mutation invalide, pas une garde qui mord — d'où le témoin
  déplacé sur une feuille sans cycle.

⚠ **Portée mesurée des `SCALAIRES_ASSUMES`** : les deux entrées lues par `.get(clé, défaut)`
(`ELEVATION_BONUS_PCT`, `CONTAMINATED_ARMOR_REDUCTION_PCT`) gardent la valeur **effective** du
gameconfig — muter leur défaut les laisse **vertes**, la clé existant au gameconfig. Ce n'est pas un
trou, c'est ce qu'elles peuvent garder ; le dire vaut mieux que de laisser croire le contraire.

## 7. Le cliquet de forme résout désormais les ALIAS D'IMPORT

Le cliquet de #270-r1-r1-r3 comparait `n.value.id` à la liste des noms d'enum. Un site écrit
`_SP.MISSING` (`from …stats import StatPart as _SP`) lui était donc **invisible** : son compte se
serait tu sur un retour à l'ordinal nu. Même forme de trou que celui du recenseur, un cran plus
bas. `test_270r4` lit les alias, et un étage dédié (`etage2b`) mesure que la résolution **mord**
sur le seul fichier concerné.

## 8. Ce qui reste en littéral — et c'est un RÉSULTAT

Rendu **exécutable** par le dernier bloc du test. Les 279 positions restantes :

| famille | n | pourquoi |
|---|---|---|
| `100` (pourcentage, multiplicateur, dénominateur `Fraction`) | 100 | quantité |
| timeouts RPC (`40`/`60`/`90`) | ~30 | quantité |
| sentinelles de distance (`99`, `0x7FFFFFFF`) | ~8 | borne, pas un membre |
| valeurs par défaut de constante gameconfig (`50`, `30`, `25`, `15`, `75`, `5`) | ~15 | la VALEUR, pas l'index |
| état du Mersenne Twister (`5489`, `0x80000000`) | 3 | quantité |
| comptes de pieds (`feet_count == 7`), de tours, de membres | ~12 | quantité |
| indices (`raw[10]`, `ev[4]`, `range(64)`) | ~8 | position |
| **slot de vtable** (`slot == 4` = `AAmountFormula$$CalculateAverage`) | 1 | offset relatif — la doctrine l'exclut explicitement |
| **borne d'enum** (`direction > 5`) | 1 | borne le domaine de `Corner`, ne DÉSIGNE pas `SouthEast` |
| assertions de garde d'ordinal (`utilities/move.py`) | 3 | c'est le cliquet lui-même |
| `et == 0x3a` (`EffectType.Darkness`) | 1 | **cycle d'import mesuré** — cf. §9 |

## 9. Les sites que l'architecture d'imports bloque — MESURÉ, pas supposé

Trois sites ont exigé un contournement. Chaque cycle a été **vu échouer** (import module-level posé,
module importé seul dans un process frais, erreur lue, arbre restauré).

| site | enum visé | chaîne exacte | issue |
|---|---|---|---|
| `services/static_battle_rules.py` — `et == 0x3a` | `EffectType` | `static_battle_rules` → `entities/__init__` → `effects_state` → `effects/__init__` → `effects/factory` → `effects/loki/__init__` → `effects/loki/hits` → **`services.static_battle_rules`** | **NON converti** — garde déportée au test (étage 5) |
| `dsl/base.py` — `stat_type == 5` | `StatType` | `dsl/base` → `entities/__init__` → `effects_state` → `effects/__init__` → `effects/factory` → `effects/loki/__init__` → `effects/loki/ability_modifications` → `entities/selectors/__init__` → `selectors/_shared` → **`dsl.base`** | converti par **import différé** |
| `entities/triggers.py` — `== 1013` | `NORMAL_ATTACK_KIND` | `entities/triggers` → `runner/abilities/__init__` → `runner/abilities/loki/__init__` → `runner/abilities/loki/summon` → **`entities.triggers`** | converti par **import différé** |

**Témoin de contrôle** : `services/trait_damage_limits.py → entities.effect_type`, même couche,
même profondeur → **VERT**. `engine/services/` n'est donc pas bloqué *en soi* ; seul
`static_battle_rules` l'est, parce qu'il est **lu en retour** par `effects/loki/hits.py`.

### La cause n'est PAS l'emplacement du mirror — c'est l'`__init__.py` du paquet parent

Contre-épreuve : les trois `__init__.py` en cause neutralisés, **les trois imports passent**.

```
                                       aretes  plus grosse SCC
REEL (differees comprises)              2921       284  (69,6 %)
MODULE-LEVEL seul (differees RETIREES)  2372         7  ( 1,7 %)
SANS les aretes d'un __init__.py        2184         1  ( 0,2 %)   <- plus AUCUN cycle
```

Deux lectures, toutes deux load-bearing :

1. **La SCC de 284 modules est un artefact des imports DIFFÉRÉS comptés comme arêtes.** Le graphe
   qui gouverne réellement le chargement (module-level seul) a une plus grosse SCC de **7 modules**,
   pas 284. `engine/` n'est pas un monolithe : il est *déclaré* comme tel par ses `__init__.py`.
2. **Les 24 `__init__.py` ré-exportateurs sont la cause ENTIÈRE des cycles réels.** Leurs arêtes
   retirées, il ne reste **aucune** SCC > 1.

Les deux SCC module-level, et le paquet est membre des deux :
```
6 : engine.services + damage_calculations, damage_modifiers, damage_prediction,
                      min_max_damage, static_battle_rules
7 : engine.playbook + common, daemonic_ordnance, loki_custom,
                      normal_attack_kill_gate, plagueburst_mortar, static_threshold_gate
```

Les cinq plus gros ré-exportateurs : `entities/effects/loki` (166 noms), `entities/selectors` (100),
`runner/operations/triggers/loki` (76), `runner/abilities/loki` (69),
`runner/operations/triggers` (68).

**Ce qu'il aurait fallu** : ni déplacer les mirrors, ni un import différé — un `__init__.py` qui
n'exécute pas son paquet. Un mirror d'enum est déjà une **feuille** ; ce que Python exécute avant
d'y arriver, c'est l'`__init__.py` du paquet parent. Résidu ouvert : **`#270-r4-r1`**.

### Combien, par cause

| cause | n |
|---|---|
| candidats des 3 rôles | **341** |
| convertis | **62** (dont **2** qui n'ont pu l'être que par import différé) |
| non convertis — vrais SCALAIRES | **278** |
| non convertis — **architecture d'imports** | **1** (`et == 0x3a`) |
| non convertis — ambiguïté d'enum irréductible | **0** |

L'architecture pèse donc **1 site sur 341** en blocage dur, et **2 de plus** en contournement. Elle
n'est pas le goulot de *cette* tranche — mais les trois sites concernés sont ceux qui portent la
sémantique la plus dense (`Darkness`, `StatType.HEALTH`, le KIND d'attaque normale), et le
contournement par import différé est une dette qui se paie au prochain lecteur.

## 10. Validation

**Tout ce qui suit a été RE-JOUÉ après le rebase (23 commits) — les chiffres sont ceux d'après.**

- `probe_313` → rc 0, **26** mirrors sous garde (25 + `EffectTargetType`), 0 introuvable, 0 morte,
  0 dette.
- Suite **offline complète** de `tests/engine` : **1757 passed, 3 skipped** (1730 avant rebase ;
  skips documentés, témoins non discriminants — aucun skip de montage).
- **12 fichiers live ciblés**, 3 vagues de 4 : `test_effect_stun` (1), `test_taunt_targeting` (7),
  `test_plague_wind` (2), `test_hammer_of_wrath` (1), `test_tile_leaf_unit_traits` (4),
  `test_daemonic_ordnance_decision` (18), `test_366_r1_stormboyz_strike` (8),
  `test_thrice_blessed_decision` (4), `test_summon_spawn` (3), `test_harlequins_panoply` (10),
  `test_hailstrike_phase2` (4), `test_thebetrayer_turnstart` (1) — **63 passed, 0 failed**.
  **Huit d'entre eux re-joués après rebase** (les plus sensibles : stun, taunt, plague wind, tile
  leaves, daemonic ordnance, stormboyz, harlequins, hammer of wrath) — **51 passed, 0 failed**.
- `test_270r4_role_enum_offline.py` : **17** tests, 9/9 contre-épreuves de mutation rouges sur le
  bon étage.

**NON couvert** : aucun test live ne traverse `EffectTargetType` (les deux `HasEffect`/`HasAnyEffect`
convertis passent par `ctx.has_effect`, dont aucun consommateur porté ne lit le `sourceFlags`) —
la garde y est offline seulement. Et les cinq `Inform`/trois `Group` sont des **no-op côté état**
(mirror structurel) : leur conversion est value-preserving par construction, aucun test ne peut la
distinguer d'un ordinal nu.
