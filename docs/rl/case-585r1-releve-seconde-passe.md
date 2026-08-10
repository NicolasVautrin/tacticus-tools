# #585-r1 (2ᵉ passe) — 58 sites de plus, et le contre-exemple devient une RÈGLE

La première passe avait relevé 28 sites et nommé **un** contre-exemple
(`ResurrectionOrbAbility$$GetPossibleResurrectTargets`, littéral `0` = `Any` sur des cibles mortes),
en observant que **27 sites sur 28 valent `3`** — donc que la symétrie est tentante. Cette passe en
a relevé **58** de plus et trouve **deux contre-exemples supplémentaires**. Le rapport reste
écrasant (**3** pour **84**), mais la cause n'est plus une exception : c'est une **règle
mécanique**.

## 1. L'état, re-mesuré

| | avant l'étage | après l'étage `#585-r3` | après cette passe |
|---|---|---|---|
| call-sites sous `runner/abilities/**` | 122 | **195** | 195 |
| dont **MUETS** | 94 | **167** | **109** |
| renseignés | 28 | 28 | **86** |

⚠ Le saut 122 → 195 n'est pas un relevé : c'est l'étage `#585-r3` qui rend **visibles** 73 sites
que le recenseur ne visitait pas (il ne compte que les factories qui *portent* le paramètre). Un
compte de couverture qui ne dit pas ce que son recenseur ne visite pas est un faux vert.

⚠ Le brief annonçait **57 symboles** pour les 94 muets ; le probe en re-dérive **43** sur le même
corpus. Chiffre hérité, non re-mesuré — le rappel « les libellés sont hérités » vaut aussi pour les
comptes.

## 2. Le contre-exemple n'est pas une exception : c'est un PRÉDICAT sur la source

Les trois contre-exemples ont la **même** cause, et elle se lit sans ambiguïté :

```
ResurrectionOrbAbility$$GetPossibleResurrectTargets
    -> Friends(gs, gs@0x48, AllDeadUnits(gs), 0)
UnbreakableDutyAbility$$GetAmountOfDeadImperialUnits
    -> Friends(gs, gs@0x30, AllDeadOrResurrectedUnits(gs), 0)
    -> UnitsWithTraits(gs, ., [0x1a Imperial, 0x10 Hero], 0)
FoehammerAbility$$GetDeadHeroes
    -> UnitsWithTrait(gs, AllDeadOrResurrectedUnits(gs), 0x10, 0)
```

**La source est un ensemble de MORTS.** `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`
teste `IsAlive` pour `OnlyAlive` **comme** pour `OnlyAliveAndTargetable` : un `3` recopié y aurait
**vidé l'ensemble** — donc rendu ces deux comptes nuls en permanence, sans erreur, sans crash, et
avec un champ qui *a l'air renseigné*.

⇒ **Heuristique de tri, à confirmer site par site et jamais à appliquer seule** : source `AllDead*`
⇒ chercher `Any`. Elle prédit les 3/3 rencontrés ; elle ne dispense pas de lire.

`Any` est posé **explicitement** (`int(UnitSelectionType.Any)`) plutôt que laissé à `None`. Les deux
sont observationnellement identiques ; seul le premier dit que le littéral a été **LU**.

## 3. Le littéral implicite : six sites de plus, et un CONTRASTE qui interdit la généralisation

Six call-sites de plus empruntent la variante B d'`$$AdjacentFriends`/`$$AdjacentEnemies` (`3` codé
en dur, invisible du corps) : `CrushingClawsAbility$$ExecuteBehaviour`,
`MightFromBelowAbility$$GetPossibleSpawnTiles`, `FealtyAbility$$GetAdditionalTargets` (**les deux**
primitives), `TalonOfHorusAbility$$GetAdditionalTargets` (**les deux**).

⚠ **Et `RighteousRepugnanceAbility$$GetAdditionalTargets`, la fonction VOISINE de `Fealty` et
`TalonOfHorus` dans le même module natif, emprunte la variante A** — ses deux littéraux, eux, sont
**écrits**. Trois fonctions côte à côte, deux surcharges différentes : c'est la démonstration que le
tri se fait call-site par call-site, jamais par famille.

`CrushingClawsAbility$$ExecuteBehaviour` est le cas mixte : `AdjacentEnemies` en variante **A**
(littéral écrit `3`) **et** `AdjacentFriends` en variante **B** (littéral implicite) dans la même
fonction.

## 4. L'appariement port ↔ natif du recenseur est un INDICE, pas une preuve

Trois symboles cités en docstring du port ne portent **aucun** sélecteur :

| symbole cité au port | ce que le décompilé dit |
|---|---|
| `FearOfTheUnseenAbility$$ExecuteBehaviour` | **aucun** appel `DSLSelectors$$*` — les nœuds du port viennent d'ailleurs |
| `ExcruciatingFrequenciesAbility$$GetDynamicInvalidTargetReason` | **délègue** à `$$GetAttackTargets`, où vivent les deux littéraux (`Units …, 1, 3` puis `Enemies …, 3`) |
| `HammerOfWrathAbility$$GetAdjacentTargets` | **INTROUVABLE** dans le build `rnca9r7q6c` (`search_symbols_by_name` rend 0) |

Le probe groupe par le symbole cité dans la docstring englobante la plus étroite — c'est ce qui rend
le relevé praticable, mais chaque groupe doit être **confirmé au décompilé** avant d'y poser un
littéral.

## 5. Le SUCRE booléen, re-dérivé (et non hérité)

`list_xrefs` sur les deux surcharges sucrées : **4** fonctions appellent `$$Enemies` booléen
(`PlasmaGrenadeAbility$$ExecuteBehaviour`, `$$GetOtherTargets`,
`PsychicStalk_VisualEffectEffect$$CreateTargetSelector`, `WeakerRearArmourEffect$$CreateTargetSelector`),
**7** appellent `$$Units` booléen (`ArcaneShieldAbility` ×3, `EnvDespoiledGroundTileAbility`,
`EnvFireTileAbility`, `UnstoppableMomentumReworkedAbility$$CanContinue`,
`FragBombAbility$$ExecuteBehaviour`). Conforme à la première passe.

⇒ **Hors de ces 11 fonctions, tout `Enemies(...)`/`Units(...)` visible dans un pseudo-C est la
surcharge explicite.** `FragBombAbility$$ExecuteBehaviour` est au relevé et **n'a pas été traité**
(cf. §7) : ses trois sites exigent de convertir le booléen par
`selection_type_from_only_alive` — `false -> OnlyTargetable`, `true -> OnlyAliveAndTargetable`.

## 6. Deux règles de relevé, ré-appliquées

**(a) Un nœud du port sans équivalent natif ne reçoit RIEN.** Deux `Units(...)` de matérialisation
restent muets et le disent au site : `blacklegion.hades_autocannons_targets` (le natif enchaîne
`Tiles` → `SortByRow`/`SortReverse`/`If`, il n'y a aucun `Units` à cet étage) et
`splash.fragstorm_tree` (le natif passe les tuiles **directement** à `Friends`, dont
`UnitsFromFactionSelector$$Select` résout l'occupant par `SelectUniqueUnits`). Sans conséquence :
le sélecteur qui les enveloppe filtre sa sortie.

**(b) Quand le port COLLAPSE deux étages natifs, le prédicat étant pur, un seul passage suffit** —
et c'est écrit au site. Cas rencontrés : `necrons.harbinger_pool_selector` (le natif écrit
`SurroundingTiles` → `Units` → `Enemies`, le port un seul `SurroundingEnemies`),
`strike.spirit_leech_heal_targets`, `splash` (Crushing Claws / Scything Talons).

## 7. Ce qui n'est PAS traité — résidu `#585-r4`

* **109 call-sites restent MUETS** sous `runner/abilities/**`, sur **46** symboles, dont **42 sites
  à `?`** (docstring englobante ne citant aucun symbole natif — à identifier à la main).
* Les **3 sites de `FragBombAbility$$ExecuteBehaviour`** (`astramilitarum.py`) : la surcharge est le
  **SUCRE** (xref confirmée), donc le littéral se **dérive** du booléen et non se lit — régime
  distinct, non entamé ici.
* Les **6 sites de `runner/operations/triggers/loki/**`** et
  `entities/effects/loki/amulet_of_the_voidwyrm.py` : hors périmètre par consigne.
* **`AdjacentEnemies` du port ne porte pas de `reference`** : la variante B native sépare `unit`
  (référence d'équipe) de `unitTile` (ancre). Aucun call-site relevé n'en a besoin — tous ont
  `unit == caster` — mais un call-site futur où les deux diffèrent exigerait le paramètre, comme
  `AdjacentFriends` l'a déjà.
* **Aucune confrontation LIVE des 58 littéraux eux-mêmes.** Le régime qui les discrimine exige une
  unité `Untargetable` **dans le champ du sélecteur** ; les tests live rejoués ici prouvent la
  **non-régression** (aucune cible perdue sur des boards sans deep strike), pas la morsure. La
  morsure est prouvée OFFLINE, par construction du substrat, sur les sept mirrors.
