# #485-r1 — vider les barils de ré-export d'`engine/`

**Livré : l'outil et sa preuve, en marche à blanc.** Aucun fichier `engine/**` n'est modifié —
cinq agents y éditaient pendant la tranche. Le sweep se fait dans une fenêtre calme, avec le
découpage proposé en fin de fiche.

## Il n'y a pas 262 problèmes, il y en a UN

Re-dérivé (`probe_485_imports_differes.py`) : **314** imports différés vers `engine.*` dans
`engine/**`, dont **262 PORTEURS**. Leur cause est unique : Python exécute l'`__init__.py` de
**chaque paquet ancêtre** avant d'atteindre une feuille. `import engine.entities.stats` exécute
`engine/entities/__init__.py`, qui tire `effects` → `loki` → … Toucher une feuille traîne un
millier de modules ; le différé est ce qui évite la boucle ainsi créée.

## L'outil

`scripts/python/migrate_485r1_barils_reexport.py` — quatre sous-commandes, **marche à blanc par
défaut**, `--appliquer` explicite.

| commande | ce qu'elle fait |
|---|---|
| `inventaire` | dérive `symbole -> module d'origine` **depuis les barils eux-mêmes** ; classe les barils à registre |
| `reecrire` | `from engine.X import Y` → `from engine.X.enfant import Y` chez les consommateurs |
| `vider` | retire du baril les ré-exports que plus personne ne réclame, ajuste `__all__` |
| `substitutions` | recense les `monkeypatch`/`mock.patch` que le sweep désarmerait (#484) |

`--baril <nom>` restreint le traitement — c'est ce qui permet de **mesurer** l'additivité du
découpage plutôt que d'en avoir un avis.

**L'ordre est contraignant** : `vider` avant `reecrire` casserait tout. Ce n'est pas l'ordre des
sous-commandes qui tient l'invariant, c'est le **refus** de `vider` de retirer un symbole encore
réclamé.

**Réécrire seul ne change RIEN au graphe** — le paquet parent s'exécute quoi qu'on écrive. C'est
`vider` qui allège la cascade.

## Mesuré sur une copie (`git archive HEAD`, arbre complet)

Chiffres **re-joués après rebase sur `origin/master`** (l'arbre témoin bouge : `master` était
passé de 262 à 260 porteurs pendant la tranche).

| | témoin | réécrit + vidé |
|---|---:|---:|
| différés recensés | 307 | 309 |
| **PORTEURS** | **260** | **166** |
| GRATUITS | 47 | 143 |
| modules portant ≥ 1 porteur | 90 | 61 |

**94 porteurs sur 260 (36 %) deviennent gratuits**, et **29 modules sont intégralement libérés**.
Le total monte de 2 parce que la réécriture **éclate** un différé multi-symboles en plusieurs
imports — d'où l'appariement **par module source**, seul stable.

⚠ **Une première mesure rendait 114 (43,5 %) — elle était FAUSSE**, et de 19 porteurs. Elle avait
été prise avec un `TRIGGERED_ABILITY_DELAYED_BEHAVIOURS` vidé (cf. plus bas) : 19 de ces
« libérations » étaient payées par un registre mort. Le gain d'un allègement de cascade et le coût
d'un registre cassé se ressemblent parfaitement dans ce compte — seul l'étage [3] du probe les
sépare.

Réécriture : **2 010 symboles dans 425 fichiers**. Vidange : **283 ré-exports sur 16 barils**
(dont `entities.effects.loki` −166).

## La preuve, et ce qu'elle ne prouve pas

`scripts/python/probe_485r1_liaisons_preservees.py` — trois étages, aucun ne suffit seul.

1. **Syntaxe.** A attrapé **7 fichiers cassés** par la première version de l'outil.
2. **AST hors imports.** L'arbre privé de ses nœuds d'import doit être identique — c'est ce qui
   établit qu'on n'a touché **que** des imports. En régime vidange, `__all__` est retiré lui
   aussi (c'est du code, et le vider le réécrit par construction).
3. **Liaisons**, en process frais, portée large (attributs de module **et** de classe) :
   - réécriture seule : **431 modules, 241 221 attributs, 0 divergence** ;
   - après vidange : **433 modules, 241 628 attributs, 12 678 divergences**, dont **12 593
     déplacements acquittés**, **85 attributs sous-module**, **0 perte réelle**, et
     **2 077 fichiers à AST identique hors imports**. Un acquittement exige les trois :
     disparition (jamais mutation), couple présent dans la table, et **même identité au module
     d'origine**. C'est la 3ᵉ condition qui fait la preuve : « le symbole a disparu du baril » et
     « le symbole est encore joignable » sont deux affirmations distinctes.

**431/431 modules s'importent seuls** dans les deux arbres.

> **Un vert ici ne dit PAS que la banque survit.** Mesure #484 (PR #741) : hisser 624 différés a
> rendu **0 divergence sur 197 017 attributs** — et **28 fichiers de tests rouges**. Hisser ne
> change pas ce que le code *calcule*, ça change **où le nom est lié**. Un `monkeypatch` posé sur
> le module source mord tant que le nom est résolu **à l'appel**, et cesse de mordre une fois le
> nom lié **au chargement**. Les tests n'ont pas mesuré faux : ils ont **cessé de mesurer**.

## La population à risque est énumérée, pas découverte après coup

`migrate_485r1_barils_reexport.py substitutions` : **72 sites** croisent la table.

- **25 `PERD_LA_MORSURE`** — le patch vise le baril **et** un consommateur y résout tardivement.
  Ce sont ceux à traiter **avant** le sweep.
- **45 `GAGNE_LA_MORSURE`** — le patch vise l'enfant ; le consommateur lisait la copie du baril et
  lira désormais l'enfant. Le stub se met à mordre : visible, mais à nommer.
- **2 `COUVERT_PAR_DOUBLE_PATCH`** — le même fichier patche **les deux** bouts (baril *et* module
  d'origine), parce que son auteur ne savait pas lequel mordrait. La morsure survit par le second.

Deux crans évitent de surestimer, et chacun a été **imposé par une mesure** :
la **voie** de consommation (un patch sur un baril qu'aucun consommateur ne résout tardivement ne
peut pas perdre sa morsure — il mord par accès attributaire, intouché), et le **double patch**
ci-dessus, découvert en jouant les tests : `test_389r2_kill_unit_remove_effects_offline.py` était
compté « désarmé en silence » alors qu'il mesure toujours.

**Le correctif est structurel** : un patch doit viser le module qui **consomme**, pas celui qui
**définit** — c'est le consommateur qui porte la liaison. Et le seul contrôle qui voit le
désarmement *silencieux* est la contre-épreuve : empoisonner l'attribut réel et vérifier que le
test **rougit**. Un test qui reste vert quand on casse ce qu'il prétend substituer ne mesure plus.

### Le risque n'est pas théorique — il est joué

Les **9** fichiers de test offline portant un site à risque ont été joués dans les deux arbres et
comparés bilan par bilan :

| | n |
|---|---:|
| rouges **FRANCS** (le test assertionne que son stub a mordu) | **3** |
| désarmements **silencieux** réels | **0** |
| apparents, mais couverts par un double patch | 1 fichier (2 sites) |

Le mécanisme est confirmé, et le test le **documente lui-même** :

```python
# tests/engine/runner/test_448_r1_r1_r2_r1_dsl_after_move_offline.py
"""... paresseux `from .triggers import after_move_triggers` -> attribut du package `triggers`."""
from engine.runner.operations import triggers as T
monkeypatch.setattr(T, "after_move_triggers", fake)
...
assert len(spy) == 1          # -> `assert 0 == 1` apres re-ecriture
```

Le patch vise le **baril** ; la réécriture pointe `triggers.dispatch.move_death` ; le stub ne mord
plus. Le test **rougit franchement** — parce qu'il assertionne que son stub a mordu. C'est la
bonne écriture, et c'est ce qui le rend réparable.

Les 3 rouges : `test_448_r1_r1_r2_r1_dsl_after_move_offline.py` (16 → 3 F / 13 P),
`test_ctx_traits_substrat_ventilation_offline.py` (12 → 1 F / 11 P),
`test_448_r1_stormboyz_port_offline.py` (14 → 3 F / 11 P).

**Ce qui n'est PAS couvert par ce contrôle, et doit l'être avant le sweep** :

- les fichiers `_live.py` portant un site à risque — non joués (100 % offline dans cette tranche) ;
- les **probes** portant un site à risque — on ne les *joue* pas (ce sont des mesures), mais un
  stub désarmé y fausserait silencieusement une future mesure ;
- les 46 `GAGNE_LA_MORSURE` : un stub qui se met à mordre change un résultat sans qu'aucun
  compteur ne le dise ;
- la **banque offline complète** (`probe_457`, dé-obligé mais jouable, 8 shards) : le contrôle
  ci-dessus ne joue que les fichiers portant un site **recensé** — un désarmement par une forme
  de substitution que le recenseur ne lit pas resterait invisible.

## HISSER n'est pas SUPPRIMER — mesuré 376 contre 1

`migrate_485r1_barils_reexport.py gestes` qualifie **377** différés (compte **par alias** ; les
314 de `probe_485` sont comptés **par nœud** — un `from X import a, b` y vaut 1) :

| geste | avant rebase | après rebase |
|---|---:|---:|
| `HISSER` — aucun import top-level ne lie déjà ce nom | 376 | **362** |
| `OMBRAGE_MEME_SOURCE` — nom déjà lié, même source : la ligne se supprime | 1 | **0** |
| `OMBRAGE_AUTRE_SOURCE` — nom déjà lié depuis ailleurs : ni l'un ni l'autre sans lire | 0 | **0** |

⚠ **« La cible est déjà importée » désigne le MODULE, pas chaque NOM.** Qu'un module fasse déjà
`from engine.services.damage import a` en tête n'implique pas que `b`, importé tardivement depuis
le même module, y soit lié — supprimer rend alors `b` introuvable, tandis que **hisser est
toujours correct**. Sur ce dépôt, supprimer au lieu de hisser serait faux dans **362 cas sur 362**.
(#484 s'est fait 23 rouges de sa propre main sur cette exacte confusion.)

## Les barils à REGISTRE — et les deux qu'on croyait tels

Identifiés **mécaniquement** (imports à effet de bord pur + modules qui mutent un objet du moteur
au top-level), jamais en dur. Quatre :

| baril | pourquoi |
|---|---|
| `engine.playbook` | 6 imports pour effet de bord pur + 4 enregistreurs |
| `engine.runner.abilities.loki` | `facade` : `TRIGGERED_ABILITY_DELAYED_BEHAVIOURS[…] = …` |
| `engine.runner.operations.triggers.loki` | `full_throttle` : `TRIGGERED_ABILITY_BEHAVIOURS[…] = …` |
| `engine.utilities` | `move` : `UTILITY_BY_TYPE[UtilityType.UnitMovement] = …` |

⚠ **`engine.entities.effects` et `engine.runner.abilities` n'en sont PAS.** `EFFECT_CLASSES` et
`ABILITY_CLASSES` sont des **littéraux**, écrits dans `entities/effects/factory.py` et
`runner/abilities/handler.py`, qui importent eux-mêmes toutes leurs classes. Court-circuiter leur
baril ne vide rien. L'hypothèse de départ les désignait ; la mesure la corrige.

⚠ Le détecteur a d'abord rendu **17 barils sur 25** — `@dataclass` et `@lru_cache` sont bien « une
racine importée ». Le filtre sur l'origine `engine` n'est pas cosmétique : un détecteur qui exclut
tout n'annule pas le risque, il annule la tranche.

**Forme retenue**, prototypée hors `engine/` (`scripts/python/prototype_485r1_registre_explicite.py`,
6 crans auto-vérifiés) : un `charger_tout()` **découvert** (`pkgutil.iter_modules`, jamais une
liste en dur) appelé à la racine de composition. ⚠ Mais le cran qui compte n'est pas
`charger_tout()` — c'est que **toute lecture avant chargement LÈVE**. Sans lui, l'appelant qui
l'oublie retombe sur le même silence : `.get(clé)` rend `None` et le moteur continue. On aurait
déplacé la faute, pas supprimé sa signature. (Même forme que `probe_313` étape 5.)

## Ce que l'outil ne sait PAS réécrire — partition exhaustive

**1 439 refus**, motifs en `enum` (pas en chaînes libres), un cas non classé sortant en `AUTRE` :

| motif | n | commentaire |
|---|---:|---|
| `SOUS_MODULE` | 898 | `from engine import move` demande le **module**, pas un symbole : déjà à sa forme la plus précise. Rien à réécrire — seule la vidange l'allège. |
| `BARIL_A_REGISTRE` | 440 | les 4 barils ci-dessus, exclus |
| `DEFINI_DANS_LE_BARIL` | 100 | symbole `def`/`class`/assigné dans l'`__init__` (ex. `get_playbook_or_default`) : il n'a pas d'enfant |
| `IMPORT_ETOILE` | 1 | `engine/dsl/nodes.py` → `from ...entities.selectors import *` |
| `AUTRE` | 0 | — |

Motifs prévus et non rencontrés sur ce dépôt : `CONFLIT_DE_NOMS`, `CHAINE_NON_RESOLUE`,
`ORIGINE_HORS_ENGINE`, `IMPORT_CONDITIONNEL`, `COMMENTAIRE_INTERCALE`, `INCONNU_DU_BARIL`.

**Traités, pas refusés** : les **alias** (`from .x import a as b` → `from engine.p.x import a as b`,
value-preserving), les ré-exports **d'un ré-export** (résolus transitivement — **58** origines à
2 maillons sur 846 ; la chaîne **s'arrête** devant un baril à registre), les origines **hors du
sous-arbre** du baril (import absolu produit), et le **commentaire de fin** d'import, réattaché à
la dernière ligne produite.

## La prise principale : « à registre » se propage VERS LE HAUT

Exclure les 4 barils à registre **ne suffit pas**, et c'est l'étage [3] du probe qui l'a montré,
pas une relecture :

```
engine.runner.abilities.behaviours.TRIGGERED_ABILITY_DELAYED_BEHAVIOURS
    {1180: engine.runner.abilities.loki.facade._run_switch}  ->  {}
```

`engine.runner.abilities.loki` était bien exclu du vidage. Mais vider son **parent**
`engine.runner.abilities` retire le `from .loki import (…)` qui était le **seul chemin** chargeant
`loki/__init__.py`, donc `facade`, donc l'enregistrement. Un registre vide, aucune erreur,
**rien qui rougisse** — la panne exacte que l'exclusion devait empêcher, obtenue par un autre
bord.

Correctif : `_cibles_chargeuses_de_registre()` protège les barils à registre **et tous leurs
ancêtres qui sont des barils**. Un import chargeur reste intact même si plus personne ne lui
réclame de symbole : **c'est son exécution qui compte, pas ce qu'il expose**. Effet sur la
vidange : 287 → **283** ré-exports (`runner.abilities` −8 → −4), et le vidage **dit** ce qu'il
garde (`imports GARDES parce qu'ils CHARGENT un registre : engine.runner.abilities.loki`).

## Trois pièges mesurés, que rien n'annonçait

1. **`str.splitlines()` coupe sur le form feed `\f`**, pas `ast`. Un seul `\f` dans un commentaire
   de `engine/runner/abilities/blacklegion.py` décalait de +1 tous les `lineno` suivants →
   **7 fichiers** rendus non parsables, dont un « unterminated string literal » qui n'accusait
   rien de ce qui était en cause. Foyer : `lignes_de()`.
2. **`__all__` ne doit pas compter comme un usage à la vidange** — sinon tout symbole exporté se
   déclare « utilisé » du seul fait d'être exporté, et le baril ne peut **jamais** se vider :
   **8** retirables au lieu de 287. Les deux appelants de `_noms_references` n'ont pas le même
   périmètre, et c'est explicite.
3. **Un `import *` réclame TOUT le baril.** Le refuser côté consommateur ne suffit pas : il faut
   le compter côté **vidange**. Sans ça, vider les 100 ré-exports d'`entities.selectors` fait
   tomber `dsl.Damageable` → **6 modules non chargeables**, dont tout `engine.playbook`. Un
   vidage qui compile parfaitement et casse à l'import.

## Découpage du sweep — **trois** commits, ni un ni seize

1. **Re-cibler les 25 `PERD_LA_MORSURE`** sur le module consommateur, avec contre-épreuve
   (empoisonner la source, vérifier que le test rougit). Aucun autre changement.
2. **Réécriture seule** — 2 010 symboles / 425 fichiers. Empreinte **strictement nulle**
   (0 divergence sur 241 221 attributs), aucun baril modifié.
3. **Vidange** — 283 ré-exports / 16 barils. Empreinte **volontairement** non nulle ; c'est ce
   commit qui libère les 94 porteurs et retire les 85 attributs sous-module.

**Pourquoi cette coupe** : elle sépare le changement à empreinte **nulle** de celui à empreinte
**non nulle**. Les deux régimes de preuve sont différents (`--vidange` du probe), et les fusionner
rendrait le vert du premier inobservable.

**Pourquoi pas baril par baril** : le gain **n'est pas additif** — une cascade traverse plusieurs
`__init__`, donc vider un baril seul laisse la boucle se refermer par un autre. La plupart des 16
commits mesureraient **zéro**, et leur chiffre de gain ne voudrait rien dire. S'y ajoute que
`--baril` existe précisément pour le vérifier, et que 425 fichiers rebasés seize fois contre un
`master` qui avance est un coût sans contrepartie.

**Pourquoi pas un seul commit** : les contrôles 2 et 3 ne se disent pas avec le même verdict.

**Risque de chacun** : (1) faible, chirurgical, mais c'est le seul dont l'oubli est silencieux —
il conditionne les deux autres ; (2) faible, l'empreinte nulle est vérifiable mécaniquement ;
(3) le plus lourd — il change l'API des paquets, et les **91 attributs sous-module** retirés
cassent tout `import <paquet>` suivi de `<paquet>.<enfant>`.

## Résidu

- **#485-r1-r1** — exécuter le sweep (les 3 commits ci-dessus) dans une fenêtre calme, et câbler
  la forme `charger_tout()` sur les 4 barils à registre. Numéro demandé à
  `probe_468 --suggere 485-r1` et annoncé (16 worktrees concurrents).
