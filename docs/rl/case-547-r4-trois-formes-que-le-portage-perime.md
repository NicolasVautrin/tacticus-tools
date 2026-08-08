# #547-r4 — Trois formes qui se périment sur notre cadence de portage, et aucune régression dessous

**Base** : `edfdda38`. `probe_547` rendait **FAIL** — 6 entrées non-VERT au ledger versionné dont
**3 NON DÉCLARÉES** (5 items), plus **2 déclarations PÉRIMÉES**.

## 1. Une seule cause, mesurée

Trois abilities sont entrées dans `ABILITY_CLASSES`, et leur masque a donc MIGRÉ hors de
`TARGETING_OPTIONS_UNPORTED` — les deux tables sont **disjointes par contrat**, c'est le résultat
VOULU du portage :

| id | nom | tranche |
|---|---|---|
| 1121 | `ItItches` | #550 (PR #848) |
| 1050 | `HolyDuel` | #549 (PR #849) |
| 1164 | `MindControl` | #552 (PR #850) |

**Le port réussit, donc le recensement périme.** Le brief n'en nommait que deux : 1164 est arrivée
entre-temps — la cadence continuait pendant le diagnostic.

## 2. Le tri : légitime pour les trois, vérifié avant de toucher au moindre compte

| contrôle | mesure |
|---|---|
| masque migré vs snapshot (`rules`, `self_cast`, `range` aplatie, `force_melee_target`) | **identique champ pour champ** pour 1050, 1121, 1164 |
| `targeting_options_for(ordinal)` | rend la **même valeur** qu'avant migration (c'est pourquoi l'étage 3 du fichier 270, qui l'interroge déjà, restait VERT) |
| entrées ajoutées / permutation dans la table | **0** / **aucune** — la table n'a fait que perdre ces 3 couples |
| `probe_181` | **132/132** masques, 0 manquant |
| `ABILITY_ATTACK_TYPE` | posé pour les 3 |
| `test_targeting_options_sources` (disjonction) | 5 passed |
| les 32 abilities actives du pool | **22** au registre + **10** en table, exactement une source chacune, portée et masque lisibles, **0 anomalie** |
| les 3 classes | portent un vrai `execute_behaviour` (64 / 100 / 114 lignes), pas des coquilles |

**Aucune régression.** Le rouge accusait la forme du recensement, pas le code porté.

## 3. Réparation par la FORME

* **`test_519_comptes_derives_offline`** — BLOC GÉNÉRÉ. Régénéré (`probe_519 --ecrire`),
  `24 → 22`. Il était faux **depuis #849**, qui l'avait régénéré sur une base où #848 n'était pas
  encore mergée : un bloc auto-régénérable reste faux s'il est régénéré sur un arbre partiel.
* **`test_433_r4_r2_r1_r2_ability_range_offline`** — LISTE FIGÉE, raturée à la main par **19**
  tranches (#487 → #521), huit d'entre elles s'y étant croisées. Elle devient
  `POOL_ACTIVE_ABILITIES` (**32**, population STABLE : le pool ne bouge qu'au changement de build)
  et le complément `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` se **DÉRIVE** du registre. La garde passe
  de « toutes dans la table des non-portées » à **`registre XOR unported`** sur les 32.
  Les quatre lecteurs externes (`test_501`, `test_509`, `test_512`, `test_521`) interrogent la
  liste en `not in` : la dérivation les rend vrais **par construction**.
* **`test_270r1_volet2_dict_keys_enum_offline`** — SNAPSHOT amputé à chaque port (44 → 25 en 19
  ratures). Le couple est désormais cherché dans sa **SOURCE EFFECTIVE**
  (`_resolveur_targeting` → `targeting_options_for`), comme le fait déjà l'étage 3 du même fichier.
  Les **109** couples restent verrouillés **APRÈS** migration — l'ancienne forme les rayait, donc
  ne les confrontait plus à rien.
* **`probe_313`** — 4ᵉ symptôme, hors ledger : son cache de verdict était périmé **par les ports
  eux-mêmes** (`holy_duel.py` neuf, `base.py` et `factory.py` modifiés). Remède prescrit par le
  probe : `git add`. `rc 6 → 0`.

## 4. La couverture MONTE — 9 mutants, 9 mordent

| mutant | ancienne forme | nouvelle |
|---|---|---|
| perte réelle (ni dict ni registre) | mord | mord |
| valeur altérée **dans le dict** | mord | mord |
| **valeur altérée sur une ability PORTÉE** (1050) | aveugle (couple rayé) | **mord** |
| **masque à ZÉRO source** (retirée + classe sans masque) | aveugle | **mord** |
| permutation de l'ordre du dict | mord | mord |
| **bit 43 posé sur une portée** | aveugle (22/32 hors périmètre) | **mord** |
| **friendly-only altéré sur 1038** (portée) | aveugle | **mord** |
| double source | mord | mord |
| portée perdue | mord | mord |

Le test « des SIX friendly-only » en retrouve **six** — il n'en balayait plus que cinq, et son nom
était devenu faux sans que rien ne le dise.

## 5. Ce qui n'est PAS fait, et pourquoi

Un **recenseur exhaustif** des assertions que `ABILITY_CLASSES` périme n'est **pas livré** — il
serait, en l'état, une liste blanche de formes, exactement le vice contre lequel il est demandé.
Mesure qui l'établit, sur les **quatre** occurrences connues (les trois ci-dessus + `test_498r4`
du 2026-08-07) : elles se répartissent sur **trois axes**, dont **un seul** est statiquement
décidable.

| axe | exemple | décidable statiquement ? |
|---|---|---|
| CONTENU (collection d'ordinaux littéraux) | `POOL_ABILITIES_WITHOUT_COMBAT_CLASS`, `SNAP_TARGETING_UNPORTED` | **oui** — visite exhaustive des `ast.Constant` entiers, rôle dérivé du nœud parent |
| TAILLE (compte d'une population) | `assert len(sites) == 2` (#498-r4) | **non** — un compte est un entier quelconque ; rien ne dit *quelle* population il compte |
| COMMENTAIRE (bloc généré) | le `24` de `test_519` | **non** — ce n'est ni un littéral exécutable ni un ordinal |

La voie dynamique (simuler un port et rejouer la banque) ne sépare pas les rouges du gisement de
ceux qu'un vrai changement de comportement produit : un stub sans face COMBAT fidèle fabrique des
faux positifs indistinguables. Résidu **#547-r4-r1** ouvert avec cette mesure.

## 6. Ce que la re-mesure a coûté

Le ledger versionné garde le verdict : **réparer un rouge ne suffit pas**, il faut re-mesurer,
sinon `probe_547` reste rouge sur une réparation réussie (arrivé deux fois le 2026-08-08).
⚠ `probe_457` **REFUSE** de se jouer sans `TACTICUS_ALLOW_RATCHETS=1` (rc 99, « rien n'a été
joué ») : un `99` n'est ni un feu vert ni un échec, c'est l'absence de verdict.
