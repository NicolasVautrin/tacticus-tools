# #585-r1 — le `selectionType` : le FOYER etait faux, et il existe un etage AMONT

Le residu decrivait « ~100 call-sites portes a relever », **FOYER**
`entities/selectors/{units,tiles,geometry}.py`. Les deux moities de cette phrase sont fausses, et
elles le sont dans des sens opposes : le compte est **sous-estime**, le foyer designe des fichiers
qui ne portent presque aucun des call-sites — mais il existe, dans ces memes fichiers, un etage que
personne n'avait nomme et qui **bloquait** le releve.

## 1. Le compte et le foyer — mesures

Inventaire **AST** (jamais un grep : les docstrings de ce port citent les factories natives a
longueur de ligne), sur les neuf factories a `selectionType` (`Friends`, `Enemies`, `Units`,
`UnitsWithTrait`, `UnitsWithoutTrait`, `NormalUnits`, `MechanicalUnits`, `AllUnits`, `AliveUnits`) :

| ou | call-sites |
|---|---|
| `runner/abilities/**` (dont `loki/`) | **107** |
| `entities/selectors/**` | 11 |
| `runner/operations/triggers/loki/` | 6 |
| `entities/abilities/`, `entities/effects/loki/` | 7 |
| `playbook/prediction/`, `entities/`, `runner/abilities/behaviours/` | 4 |
| **TOTAL** | **135** |

Dont **2** portent deja un `selection_type` explicite (`Friends` de `WarHowl`, un
`UnitsWithoutTrait`). Le releve restant est donc de **133**, pas ~100, et il vit a **79 %** dans
`runner/abilities/**`.

⇒ **Le champ `FOYER` de la ligne de backlog est FAUX**, et c'est ce qui a fait dispatcher ce residu
avec un territoire incapable de le porter. Corrige dans le backlog.

## 2. L'etage AMONT — ce qui BLOQUAIT le releve

Les mirrors de factory de `entities/selectors/**` se divisent en deux : ceux qui allouent un
selecteur (`Friends`, `Enemies`, `Units`, `UnitsWithTrait`, `UnitsWithoutTrait`) et ceux qui
**COMPOSENT** d'autres factories sans rien allouer (`hero_units`, `units_with_traits`,
`non_steppable_units`, `non_steppable_or_object_units`, `NormalUnits`, `composites.adjacent_units`).

Cote natif, **les deux familles prennent le `selectionType` et le propagent**. Cote port, **aucune
ne le portait**, hormis `Friends` et `UnitsWithoutTrait` (poses par #585). Consequence : un appelant
qui connaissait son litteral **ne pouvait pas le faire descendre**. Le releve des 133 etait bloque
avant d'avoir commence, et rien ne le disait.

Signatures NATIVES relues sur `rnca9r7q6c`, une par une (jamais par symetrie) :

| mirror du port | natif | ce qui manquait |
|---|---|---|
| `Enemies` | `DSLSelectors$$Enemies(this, of, entities, selectionType)` | parametre ABSENT |
| `Units` | `DSLSelectors$$Units(this, entities, unique, selectionType)` | parametre ABSENT |
| `UnitsWithTrait` | `DSLSelectors$$UnitsWithTrait(this, entities, trait, selectionType)` | parametre ABSENT |
| `NormalUnits` | `DSLSelectors$$NormalUnits(this, entities, selectionType)` | propage a son `Units` interne |
| `hero_units` | `DSLSelectors$$HeroUnits(source, mask)` — `mask` EST le selectionType | avale |
| `units_with_traits` | `DSLSelectors$$UnitsWithTraits(entities, traits, selectionType)` | avale |
| `non_steppable_units` | `DSLSelectors$$NonSteppableUnits(source, selectionType)` | avale |
| `non_steppable_or_object_units` | `DSLSelectors$$NonSteppableOrObjectUnits(source, selectionType)` | avale |
| `composites.adjacent_units` | `DSLSelectors$$AdjacentUnits(this, origin, unique, selectionType)` | avale |

**`UnitsWithoutRangedWeapons` reste SANS parametre**, et c'est un resultat : son natif a l'arite 2 et
`UnitsWithoutWeaponsSelector$$Select` pose `1` en dur. Y ajouter le parametre inviterait a passer le
litteral de l'appelant, qui n'appartient pas a ce noeud — la docstring du port le disait deja.

Defaut `None` partout = **comportement HISTORIQUE strictement inchange**. Verifie mecaniquement :
aucun call-site du depot ne passe d'argument positionnel a l'arite elargie (balayage AST, 7 sites
au-dessus de l'arite historique, les 7 introduits par ce commit).

## 3. La surcharge BOOLEENNE est un SUCRE — et elle ne rend JAMAIS `Any`

Decouverte de cette tranche, **confirmee deux fois independamment** (lecture directe, puis relecture
par xrefs entrantes d'un second lecteur). Les factories `Enemies` et `Units` ont **deux surcharges de
meme arite**, indiscernables dans le pseudo-C — meme identifiant affiche. La seconde n'est pas un
autre axe :

```
DSLSelectors$$Enemies(this, of, entities, onlyAlive)
    -> DSLSelectors$$Enemies(this, of, entities, (onlyAlive & 0xff) + 2)
DSLSelectors$$Units(this, entities, unique, onlyAlive)
    -> UnitsOnTilesSelector..ctor(..., unique, (onlyAlive & 0xff) + 2)
```

Soit `false -> 2` (`OnlyTargetable`) et `true -> 3` (`OnlyAliveAndTargetable`).

**Deux consequences pour les 133 restants** :

1. **Un call-site qui emprunte la surcharge booleenne filtre AU MINIMUM `UnitFlag.Untargetable`.**
   Il n'existe aucun chemin par lequel elle rende `Any` ou `OnlyAlive`. Le `None` du port y est donc
   strictement plus permissif que le **plancher** natif — c'est exactement l'ecart mesure par #585
   (`spaceRockfist` en deep strike, retenu par tous les autres filtres, que le natif ne buffe pas).
2. **Un `bool` litteral se DERIVE sans arbitrage** entre quatre valeurs. Le releve y gagne un
   regime entier.

⚠ **Et un piege** : le mapping n'est pas l'identite. Lire `Enemies(..., 0)` dans le decompile ne dit
pas `Any` tant qu'on n'a pas tranche la surcharge — si c'est celle a `onlyAlive`, `0` vaut `2`. La
seule voie sure est la **xref entrante**, jamais la lecture du pseudo-C seul. Meme piege latent sur
`DSLSelectors$$First`.

Foyer du sucre : `engine/entities/unit_selection_type.selection_type_from_only_alive`.

## 4. Defaut trouve en passant — une factory definie DEUX FOIS

`non_steppable_or_object_units` etait definie **deux fois** dans `entities/selectors/units.py`
(corps identiques, docstrings differentes). La seconde ecrasait la premiere a l'import : la version
qui portait l'avertissement sur l'ambiguite de l'ordinal `0xd` (`UnitTrait.Object` **vs**
`DamageProfileType.Psychic`, que `HellfyreMissileRackAbility$$ExecuteBehaviour` utilise TOUS LES DEUX
dans la meme expression) vivait dans du **code mort**. Un lecteur qui parcourt le fichier de haut en
bas ne pouvait pas le voir. Les deux sont fusionnees.

## 5. Ce qui n'est PAS couvert

* **Les 133 litteraux de call-site restent a relever**, et chacun doit etre RE-LU : recopier `3`
  partout ecrirait un masque faux. Le residu `#585-r1` reste OUVERT, avec son foyer corrige.
* **`AdjacentFriends` / `AdjacentEnemies`** (classes de `units.py`) : leur docstring cite deja la
  surcharge 4-args native `AdjacentFriends(factory, X, p3, p4)` =
  `Friends(reference = X, Units(AdjacentTiles(X), p3, p4) - X, p4)`, donc elles avalent le litteral
  **deux fois** (au `Units` et au `Friends`). Non traitees ici : elles passent par `_within`, pas par
  la composition, donc le plombage y est un changement de STRUCTURE et pas d'arite — a faire avec la
  mesure qui l'exige.
* **Le flag `unique` de `Units` / `AdjacentUnits`** reste hors parametre : residu `#433-r3-r1a-r1`,
  distinct et prealable.
* **Aucune confrontation LIVE** dans cette tranche : le defaut `None` rend le changement
  observationnellement NUL par construction. Confronter exigerait de renseigner un litteral a un
  call-site, donc d'entrer dans `runner/abilities/**` — territoire d'un autre agent sur cette vague.
