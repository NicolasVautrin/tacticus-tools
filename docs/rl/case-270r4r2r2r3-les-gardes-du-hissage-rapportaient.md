# #270-r4-r2-r2-r2 et -r3 — les gardes du hissage RAPPORTAIENT au lieu d'ÉCHOUER

**Livré le 2026-08-06.** Instruments : `probe_270r4r2r2r3_import_ombre.py` (neuf),
`probe_270r4r2_empreinte_valeurs.py` (durci). Cliquet :
`tests/engine/test_270r4r2r2r3_gardes_du_hissage_offline.py` (12 tests, 31 s, 100 % offline).

Deux trous de la **même famille** — un filet qui rapporte sans échouer exige un lecteur humain,
exactement ce qu'une garde est censée supprimer. L'un des deux a laissé passer un **rouge réel sur
`master`**.

## 1. Ce qui a bougé

| | avant | après |
|---|---|---|
| un nom qui DISPARAÎT fait rougir l'empreinte | non (imprimé, `rc 0`) | **oui** (`rc 1`) |
| un module qui ne s'importe PLUS fait rougir l'empreinte | non (clé `!IMPORT!` = un *apparu*) | **oui** |
| un import différé qui OMBRAGE son import module-level rougit | **aucune garde** | **oui**, invariant à 0 |
| échappatoire explicite, comptée, imprimée | — | `--disparition-voulue` / `[import-ombre:voulu]` |
| ombrages sous `engine/` | 0 | **0**, sous cliquet |

## 2. TROU B — l'ombrage, et le « 12 armés sur 14 » qui était FAUX

En Python, un `import` dans un corps de fonction rend le nom **local à TOUTE la fonction**
(`STORE_FAST`), pas à partir de sa ligne. Le hissage `492c722f` (#270-r4-r2-r2) a **ajouté**
l'import module-level sans **retirer** le différé, qui vivait sous `if self.value is not None:` :
la branche `else` lisait une locale non liée.

```
UnboundLocalError: cannot access local variable 'StatType' where it is not associated with a value
engine/entities/effects/loki/status.py  (fn `applied_stat_mods`)
```

Re-mesuré ici sur l'arbre extrait de `492c722f`
(`probe_270r4r2r2r3_import_ombre.py --historique 492c722f`) :

| | n |
|---|---|
| sites d'ombrage | **14** / 10 fichiers |
| dont **imbriqués** dans un `if`/`try` | 12 |
| dont **ARMÉS** (une lecture n'est couverte par AUCUN binder qui la domine) | **1** |

⚠ **Le « 12 armés » du rapport de #477-r24 comptait les CONDITIONNELS, pas les armés.** Les deux
critères ne coïncident pas, et l'écart est mesurable :

- `state_bridge:427` est sous un `if`, mais la **seule** lecture de `targeting_options_for` vit
  **dans la même branche, après** l'import → aucun chemin ne lit de locale non liée ;
- `components:2388` et `:2393` sont **deux** imports du même nom dans **deux** branches, chacune
  lisant `EffectType` après **son** import → une dominance calculée par-import seul les déclare
  armés à tort ; une dominance calculée sur **l'union des binders du nom** ne le fait pas.

Le seul site réellement armé est `status.py:241 StatType` — **exactement celui qui a crashé**.
Le critère qui rend ce 1 est écrit dans le probe : *une lecture est couverte dès qu'**un** binder
du nom la domine structurellement* (même liste d'instructions, l'import **directement** dedans,
et **avant**).

### Pourquoi la garde rougit quand même sur les 14

**Le critère de la garde est la REDONDANCE, pas l'armement.** Trois raisons, et la mesure
ci-dessus est la première :

1. la distinction ARMÉ/inoffensif est **fragile par nature** — trois des 14 changent de camp selon
   qu'on regarde l'import seul ou l'union des binders. Une garde dont le critère est approximatif
   se dégrade en silence ;
2. un site inoffensif est à **une édition** d'être armé (déplacer une instruction, ajouter une
   branche) — et c'est précisément l'étage qui manquait ;
3. la redondance n'apporte **rien** : le module est déjà chargé, le nom déjà résolu.

L'armement reste **DÉRIVÉ et IMPRIMÉ**, en **trois** sévérités et pas deux — parce que
« armé / pas armé » ne sait pas dire *je ne sais pas* :

| sévérité | critère |
|---|---|
| `ARME` | une lecture n'est couverte par aucun binder qui la domine → `UnboundLocalError` |
| `INDETERMINE` | la seule lecture non couverte vit dans une portée **imbriquée** : au runtime elle passe par une cellule de fermeture, et l'ordre d'**appel** n'est pas structurel |
| `REDONDANT` | toutes les lectures sont couvertes |

### Cinq régimes que le détecteur ne confond pas (témoins négatifs, tous mesurés)

Un détecteur qui rendrait **tout** serait vert sur les seuls mutants. Sept sources synthétiques
couvrent chacune une raison **distincte** de ne pas rougir, et aucune ne rougit :

- le module-level est sous `if TYPE_CHECKING:` → il n'existe **pas** au runtime, le différé est
  **nécessaire** ;
- l'import vit dans un **corps de classe** → `LOAD_NAME` retombe sur le global, aucun ombrage ;
- la fonction déclare `global X` → l'import écrit le **global**, il ne crée aucune locale ;
- l'import vit dans une `def` **imbriquée** → il ombrage la portée interne, pas la porteuse ;
- alias distinct / noms différents.

Et deux régimes que le détecteur attrape et qu'un critère naïf raterait :
`import a.b` lie **`a`** (donc ombrage `import a.c` du module) ; un `if TYPE_CHECKING:` **dans la
fonction** n'est jamais exécuté mais rend quand même le nom **local**.

## 3. TROU A — l'empreinte voyait et se taisait

`probe_270r4r2_empreinte_valeurs` imprimait `NOMS disparus = 1` et rendait `rc 0` : son verdict
ne dépendait **que** des divergences de VALEUR (`return 1` sur `val` seul). Quatre catégories
existent désormais, et **trois** sont des régressions :

| catégorie | verdict | pourquoi |
|---|---|---|
| VALEUR | **ÉCHEC** | déjà couvert |
| DISPARU non déclaré | **ÉCHEC** | signature d'un hissage cassé |
| IMPORT cassé | **ÉCHEC** | la clé `!IMPORT!<mod>` **apparaissait**, et un apparu ne comptait pas — une régression d'import était structurellement invisible |
| APPARU | liste | c'est ce que **produit** un hissage réussi ; le fermer ferait rougir la tranche qui a hissé 625 imports |

L'échappatoire est `--disparition-voulue <nom>` (répétable), **comptée, imprimée** — et
**périmable** : une déclaration qui ne correspond à **aucune** disparition réelle fait échouer elle
aussi. Une porte laissée ouverte après usage est le mode de défaillance suivant.

## 4. Les deux gardes VUES ROUGES sur la faute HISTORIQUE, pas sur un mutant

Les deux fautes ont été **ré-introduites dans les vrais fichiers**, mesurées, puis l'arbre restauré
(`git diff` vide vérifié).

**TROU A** — retrait de `from ..entities.pathfinding.fly_pathfinder import is_like_flying`
(module-level) dans `engine/services/movement_query.py`, le nom restant appelé ligne 384 :

```
probe_270r4r2_import_en_premier --tous  ->  OK : 412/412 modules s'importent EN PREMIER   (rc 0)
probe_270r4r2_empreinte_valeurs --comparer <temoin>
  ECHEC : 1 NOM(S) DISPARU(S) non declare(s) -- signature d'un hissage CASSE
          (import SUPPRIME au lieu d'etre DEPLACE).
  - engine.services.movement_query.is_like_flying  (valeur au temoin : '<callable>')   (rc 1)
```

La garde offline reste **verte** — le module *s'importe*, le nom ne manque qu'à l'**appel**. C'est
exactement le régime que l'empreinte devait couvrir et ne couvrait pas.

**TROU B** — remise du `from ...stats import StatType` dans la branche d'`applied_stat_mods` :

```
probe_270r4r2r2_tri_differes --gratuits            ->  INVARIANT : 0 differe(s) GRATUIT(s)  (rc 0)
probe_270r4r2_empreinte_valeurs --comparer <temoin> ->  0 nom disparu, 0 import casse       (rc 0)
probe_270r4r2r2r3_import_ombre
  ECHEC  ecarts = 1 (dont 1 ARMES, 0 INDETERMINES)
    ARME  engine.entities.effects.loki.status:241  StatType  (fn `applied_stat_mods`,
          module-level ligne 21, sous If)  lecture NON couverte par un binder du nom      (rc 1)
```

Et la faute est **réelle**, pas stylistique — vérifié au runtime sur le module muté :

```
StatType est une LOCALE de applied_stat_mods : True
LEVE -> UnboundLocalError: cannot access local variable 'StatType' where it is not associated with a value
```

Contre-épreuve **reproductible sans muter quoi que ce soit** :

```powershell
python probe_270r4r2r2r3_import_ombre.py --historique 492c722f   # 14 sites, 1 ARME, rc 1
python probe_270r4r2r2r3_import_ombre.py --historique d450c362   # 0, rc 0
```

Une révision inatteignable rend **rc 2** en le disant — une mesure impossible n'est pas un zéro.

## 5. Ce qui n'est PAS gardé, et qui est DIT à chaque run

Le probe imprime sa portée **inconditionnellement**, sans qu'on la lui demande :

- **hors périmètre** — le reste de `scripts/python/**` : **15** ombrages mesurés (**0 ARMÉ**,
  2 `INDETERMINE`, 13 `REDONDANT`), dans `tests/conftest.py` (4), `test_350_prediction_average_
  forms_offline` (3), `unit_map.py`, `probe_192`, `probe_326`, `probe_446_r2`,
  `probe_brazier_radbombardment`, `test_ability_target_gate_live`, `test_389_ramming_speed`,
  `test_433_r4_r2_r1_r2`. **Résidu #270-r4-r2-r2-r3-r1** — ces fichiers appartiennent à d'autres
  tranches ; le cliquet les tient par un **plafond** (15), nommé comme tel, pour que le gisement ne
  **grossisse** pas ;
- **hors portée par construction** — les corps de **classe** (`LOAD_NAME` retombe sur le global,
  aucun ombrage possible : 0 mesuré), `from x import *` (le nom lié n'est pas dérivable
  statiquement : 0 mesuré), et les liaisons module-level **non-import** (`X = ...`, `def`, `class`)
  que `--elargi` **mesure** — **0 sous `engine/`**.

## 6. Deux pièges rencontrés, tous deux mesurés

**Un `ast.walk` par instruction est quadratique.** Le balayage complet de `scripts/python`
(1 969 fichiers) coûtait **33,9 s** : chaque instruction re-parcourait le corps de chaque bloc une
fois par ancêtre. En s'arrêtant aux sous-instructions et en **fusionnant** les trois traversées
(lectures directes / portées imbriquées / walrus) en une seule : `engine/` seul passe de 10,6 s à
**2,4 s**. C'est pour ça que l'étage « hors périmètre » est **opt-in** (`--portee`) — mais sa
**déclaration**, elle, ne l'est pas.

**Une déclaration d'échappatoire doit porter un MOTIF.** Un marqueur nu (`[import-ombre:voulu]`
sans texte) est refusé par le probe **et** par le cliquet : une échappatoire sans raison est une
porte ouverte, et le plafond (3) la garde visible.

## 7. Résidus

- **#270-r4-r2-r2-r3-r1** — les **15** ombrages hors `engine/`. Aucun n'est ARMÉ aujourd'hui ;
  ils sont sous plafond, pas sous invariant. Les résorber demande d'éditer des fichiers d'autres
  tranches (`tests/conftest.py` en particulier).
