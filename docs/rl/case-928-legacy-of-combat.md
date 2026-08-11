# #928 — `LegacyOfCombat` (1319, `custoBladeChampion` « Kariyan ») : les trois faces, et le vecteur qui manquait

Ferme `#509-r1`. Build `rnca9r7q6c`.

## 1. Combien de faces — le tableau d'audit disait « manque 1 », il y en a QUATRE

| face | artefact natif | verdict |
|---|---|---|
| COMBAT | `...Triggered.Loki.LegacyOfCombatAbility$$CreateTrigger` + `$$CreateBehaviour` | **PORTÉE** (`runner/operations/triggers/loki/legacy_of_combat.py`) |
| DÉCISION — mouvement | `...Loki.LegacyOfCombatPlaybook.<CalculateMovementUtilityInStepsInternal>d__2$$MoveNext` | **PORTÉE** (`playbook/legacy_of_combat.py`) |
| DÉCISION — attaque | `...LegacyOfCombatPlaybook.<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` | **DEAD** — corps entier `yield return Fix64.op_Implicit(0)` |
| DÉCISION — non-owner | *(néant)* | **INEXISTANTE** — la parente est `TriggeredAbilityPlaybook<T>`, pas `AdjacentToOwnerNonOwnerPlaybook<T>` (`frida/classes.tsv`), et `metadata/non_owner_slot4.tsv` ne la porte pas |

Le verdict DEAD est **re-dérivé du binaire** par `test_928_legacy_of_combat_offline.py` (désassemblage
du corps, le seul appel non trivial étant la conversion `Fix64`), pas cité.

## 2. Ce que le natif dit et qu'aucune table ne disait

**Le trigger est sur `On(0xb = UnitAbility)`** — le seul des cinq événements d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
qui soit **INCONDITIONNEL après l'exécution** (séquence lue au désassemblage :
`0x2a` → exécution → **`0xb`** → `if (IsActiveAbility) 0xc` → `AddFlagsAfterAbilityExecution` → `0xe`).
Il fire donc pour l'attaque NORMALE comme pour un cast, sans discriminant de kind — exactement ce
qu'exige « after performing his first attack each turn ». **Le port ne l'émettait pas** (`handler.py`
portait « aucun consommateur porté ») : #928 l'ajoute sur les DEUX voies, comme #120 l'avait fait
pour `0x2a`/`0xe`.

**Le gate est une ÉGALITÉ STRICTE**, `AmountIsEqual(TimesAttackMadeThisTurn(Owner, rangeType: null), <DSLFormulas+0x20> = Direct(1))`,
et c'est lui — sans aucun effet-marqueur — qui borne le passif à une fois par tour : l'attaque
supplémentaire incrémente elle-même le compteur (une fois par cible), donc la 2ᵉ attaque du tour voit
déjà `>= 2`. Un `AmountIsGreaterThanZero` (le voisin de forme) le ferait re-déclencher à chaque
attaque.

**`rangeType = null` ⇒ compteur TOTAL `ActorStatisticsComponent+0x24`**, celui que #508-r1 a déjà
porté. Le résidu **`#508-r2` citait `LegacyOfCombat` comme consommateur potentiel d'une variante
`Ranged`/`Melee` : c'est FAUX**, relu au décompilé — le `Nullable` est vide.

**Le `Randomize` n'est pas décoratif, et le sous-arbre est ÉVALUÉ DEUX FOIS.** La branche BigTarget
vise `First(SortTargetsByDamagePredictionSelector(Randomize(UnitsWithTrait(AdjacentEnemies, BigTarget))), amount = 1)`,
et ce même nœud alimente la condition du `If` **et** la cible de l'attaque, sans `Cache` interposé.
Mesuré : à un Big Target adjacent, 4 coups devraient coûter 8 tirages `genrand_int32` — le natif en
consomme **10**, le port aussi, et le mutant `sans_randomize` **8**.

**Trois surcharges tranchées par l'adresse du `call` puis par le type déclaré** (`frida/methods.tsv`) :
les DEUX `AttackWithAttackDamage` du corps sont des formes **différentes** (`hits: IAmountFormula`
pour le volet 2, `hits: System.Int32` pour le volet 1) ; `AmountIsGreaterThanZero` est la surcharge
`amount: ITargetsSelector` (donc `Count > 0`) ; `AdjacentEnemies` est la variante `(unit, unique, selectionType)`,
pas celle dont le 3ᵉ argument est une entité ; `First` prend un **NOMBRE d'éléments**, pas un index.

## 3. L'arbre porté

```
On(0xb = UnitAbility, ownerNeedsToBeAlive = 1)
  & get_OwnerIsActor
  & NOT CurrentAbilityIs(AbilityOrEffect(<this+0x10> = TriggeredAbility 1319))
  & AmountIsEqual(TimesAttackMadeThisTurn(Owner@+0x30, null), Direct(1))
->
If( AmountIsGreaterThanZero(firstBigTarget),
    AttackWithAttackDamage(Owner, firstBigTarget, minDmg_2/maxDmg_2, Piercing, nrOfHits_2 = 1, 1319),
    AttackWithAttackDamage(Owner, AdjacentEnemies, minDmg/maxDmg, Power, nrOfHits = 3, 1319) )
```

Face DÉCISION mouvement : `10 × |ennemis adjacents à la tuile candidate|`, clé BC
`LegacyOfCombat_LikesAdjacentEnemies` (résolue au littéral de `global-metadata.dat`, valeur 10 dans
la capture **et** dans le gameconfig vivant). Corps **propre** (`GetAdjacentEnemies` slot 127,
ancre TUILE + argument UNITÉ) : aucun filtre, aucun cap, et — contrairement à la famille
`friends_in_range` — aucune inclusion de self, le natif demandant les ennemis de `case.Unit`.

## 4. Ce que ce port ferme, et ce qu'il périme

`MartialInspiration_ExtraDamage` (1408) porte
`ForPercentIncrease(OwnerIsCaster & (CurrentAbilityIs(1191) | CurrentAbilityIs(1319)), …)`. La 2ᵉ
branche était **structurellement inatteignable** côté port. Les deux feuilles passent désormais
`ability_type = 1319`, et le mutant `sans_ability_type` mord dans les deux branches et les deux
régimes de compteur.

⚠ **Une prémisse de test est PÉRIMÉE par ce port**, et elle a dû être recalibrée :
`probe_509` / `test_509_martial_inspiration_live.py` gardaient `tirages_port == 2 × <coups de 1191>`,
l'écart avec le natif étant *le port manquant*. Mesure (`MC1_67`/50901, régime nominal, compteurs 0
et 3) : **AVANT port 6 / natif 18 ; APRÈS 18 / 18**. Le critère est devenu l'ÉGALITÉ, plus un témoin
`len(sp) < coups_tous` qui rougirait si 1319 cessait de jouer.

## 5. Mesures (`probe_928_legacy_of_combat.py`)

| étape | régime | résultat |
|---|---|---|
| 5 | 2 ennemis adjacents, aucun BigTarget | delta PV **bit-exact** port = natif (`{warden: 8992, overlord: 2774}` puis `{12588, 3901}`), tirages **18/18**, 6 coups sur 2 cibles ; **6 mutants sur 6 mordent**, dans les DEUX régimes de compteur |
| 6 | `astraBullgryn` (BigTarget) adjacent | delta PV **bit-exact** (`15896` puis `22242`), tirages **10/10** (dont 2 de `Randomize`), 1 seul coup Piercing ; **6 mutants sur 6 mordent** |
| 7 | terme de tuile, `MC1_67`/777 | `X_nat == X_port` sur **7 tuiles sur 7**, terme prenant **3 valeurs distinctes** (10/20/30) |
| 8 | contre-épreuve registre neutralisé | le terme du port devient plat à zéro : plus aucun pas discriminant, alors que le natif vaut 10/20/30 sur ces mêmes tuiles |
| 9 | **voie ATTAQUE NORMALE** (l'autre porte de `On(0xb)`) | delta PV **bit-exact** sur 3 casts, tirages **15/15** ; supplément `ref - sans_trigger` = `{warden: 2200, overlord: 1993}` puis `{1711, 1594}`, `{1744, 1590}` — DEUX cibles touchées, et le total reste bit-égal au natif, donc le passif joue **UNE SEULE FOIS** (une double émission le doublerait) |

⚠ **Le port a DEUX portes d'opération là où le natif n'a qu'un site** (#120) : une émission manquante
ou doublée d'un côté ne se verrait sur **aucun** montage de l'autre. L'étape 9 est donc un axe à part
entière, pas une variante de confort. Un seul mutant y est inerte, avec sa **cause mesurée** :
`else_sans_ability_type` n'a d'observable qu'à travers le gate `CurrentAbilityIs(1319)` de l'effet
1408, que seul un cast de `1191` pose — il mord sur l'autre voie, à compteur > 0.

Mutants joués (chacun retire UNE lecture, sur la MÊME capture et le MÊME état MT), **choisis par
branche** — muter la branche non prise serait un vert par pauvreté du mutant :
`sans_trigger`, `{else,then}_profil_volet{2,1}`, `{else,then}_hits_volet{2,1}`,
`{else,then}_bornes_volet{2,1}`, `{else,then}_sans_ability_type`, `sans_filtre_bigtarget`,
`sans_randomize`.

## 6. Résidus nommés

* **`selectionType = 2`** (9ᵉ argument d'`AttackWithAttackDamage`) : aucun étage de
  `UnitSelectionType` n'est matérialisé sur cette feuille — résidu **partagé** par tous ses call-sites.
* **`options`** (8ᵉ argument) : struct zéroée au call-site (5 qwords à 0, lus à l'assembleur) → ni
  `isForceOverkill`, ni `forceCrit`, ni `skipHitsModifiers` ; c'est le défaut de la feuille portée.
* **Double évaluation du sous-arbre `firstBigTarget` à N ≥ 2 Big Targets** : NON CONFRONTÉE — aucun
  montage de cette tranche n'a mis deux porteurs de `BigTarget` adjacents à Kariyan. À N = 1 le
  tirage existe (mesuré) mais son résultat est forcé.
* **Adjacence sans porte d'élévation** sur les sélecteurs du behaviour (`hexgeo`/`_within`), comme
  toute la famille (#271). La face DÉCISION, elle, passe par `battle_query.is_adjacent`, qui la porte.
* Le gate `NOT CurrentAbilityIs(1319)` est **structurellement toujours vrai** sur les émetteurs
  portés (les deux voies de `0xb` renseignent un `ActiveAbilityType`) : porté parce qu'ÉCRIT, testé
  pour qu'il ne soit pas supprimé en le croyant mort.
