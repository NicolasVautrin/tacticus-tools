# case-265 -- `BaseUnitComponent+0x50` (`DisabledTraits`) : AUCUN ecrivain dans le binaire

**Question posee (binaire).** Existe-t-il, dans le binaire du build courant, au moins UN ecrivain de
la collection a l'offset `+0x50` de `IdunBattle.Entities.Components.BaseUnitComponent` -- celle qui
pose le VETO dans `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` ?

**Reponse MESUREE : NON.** Aucun site du binaire n'ajoute quoi que ce soit dans `+0x50`. La
collection est construite VIDE par `IdunBattle.Entities.Components.BaseUnitComponent$$.ctor`,
recopiee (donc toujours vide) par les deux `Copy`, et n'est jamais alimentee.

Consequence directe : **le veto de `HasTrait` est structurellement INERTE**, et
`HasTrait(t) == permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t)` au bit pres, pour
toute la duree d'une bataille. Le port n'a donc **rien a modeliser** pour `+0x50` -- mais il ne
doit pas non plus s'autoriser a *lire* les traits ailleurs qu'a travers un mirror de `HasTrait`
(cf. §6).

Mesure faite sur le build `rnca9r7q6c` (`data/symbols/CURRENT`), 100 % statique (ghidra-mcp),
sans aucune experimentation live.

---

## 1. Le champ, son nom, ses voisins

Le dump Il2CppDumper (`sources_win/IdunBattle/Entities/Components/BaseUnitComponent.cs`) nomme les
trois collections -- le nom **`DisabledTraits`**, pas « removed » :

```
public IOrderedSet<UnitTrait> Traits;            // 0x40   permanents
public IOrderedSet<UnitTrait> TemporaryTraits;   // 0x48   temporaires
public IOrderedSet<UnitTrait> DisabledTraits;    // 0x50   VETO
```

`IdunBattle.Entities.Components.BaseUnitComponent$$.ctor` construit les **trois** avec le meme
`idun.shared.collections.OrderedSetu003C__Il2CppFullySharedGenericTypeu003E$$.ctor` sans argument
et le meme `MethodInfo*` d'instanciation (le `OrderedSet<UnitTrait>` ferme) -- donc trois sets
**vides et distincts**, `+0x50` inclus. Le 4e set (`+0x68`, `Bonus`) est une autre instanciation.

`IdunBattle.Entities.Components.BaseUnitComponent$$Copy` et
`IdunBattle.Entities.Components.UnitComponent$$Copy` recopient les trois par le ctor-copie
(`OrderedSet<T>..ctor(IEnumerable<T>)`, qui delegue a `$$AddRange`) : `+0x50` est preserve, donc
reste vide.

## 2. La methode qui etablit l'exhaustivite (et pourquoi elle CONCLUT)

Le piege a eviter : conclure par l'absence d'un NOM dans les tables. Ici la preuve est
**structurelle**, pas onomastique. Pour qu'un `UnitTrait` entre dans la collection `+0x50`, il faut
appeler un mutateur ADDITIF sur l'objet `OrderedSet<UnitTrait>` qui s'y trouve. En IL2CPP AOT il
n'existe que **trois** formes d'appel, et les trois sont indexables par xref :

| forme | ce qui est reference dans le code | comment on l'enumere |
|---|---|---|
| appel DIRECT au corps full-shared | le `MethodInfo*` de l'instanciation **fermee** `OrderedSet<UnitTrait>::<methode>`, passe en dernier argument | `list_xrefs` sur ce global |
| invoke d'INTERFACE | l'`Il2CppClass*` de l'interface **fermee** sur `UnitTrait` (`FUN_180003b70(<slot>, <ItfClass>, obj, arg)`) | `list_xrefs` sur ce global |
| appel via la vtable resolue a la main | le meme `Il2CppClass*` d'interface (boucle sur `klass+0xb0`) | idem |

Les trois formes passent donc par un **global** (`DAT_...`) propre soit a la methode fermee, soit a
l'interface fermee. Il suffit d'enumerer ces globals puis leurs xrefs pour avoir **tous** les sites
possibles -- aucune deduplication de corps ne peut masquer une xref de donnee.

Les globals concernes se re-derivent en deux lectures (ils sont build-specifiques, et ne portent que
des noms-placeholder `DAT_<adresse>` -- **volontairement laisses en VA**, cf. la regle du CLAUDE.md
sur les placeholders) :

* `IdunBattle.Entities.Components.BaseUnitComponent$$.ctor` donne le `MethodInfo*` du
  **ctor** `OrderedSet<UnitTrait>()` (ici `DAT_183330100`) et
  `...$$Copy` celui du **ctor-copie** (`DAT_183330240`) ;
* `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor` -- le seul
  autre code du binaire qui construit des `OrderedSet<UnitTrait>` -- donne le `MethodInfo*` de
  **`OrderedSet<UnitTrait>::Add`** (`DAT_183330388`) : c'est la piece qui manquait pour fermer la
  question ;
* les `Il2CppClass*` d'interfaces fermees sur `UnitTrait` apparaissent dans
  `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` (`DAT_1833681e0`, slots 4 =
  `Contains` / 6 = `Remove`), `IdunBattle.Operations.AddTraitOperation$$AddTrait`
  (`DAT_1833aec78`, slot 0 = `Add`) et
  `IdunBattle.Operations.AddUnitOperation$$RemoveTraitsThatAreNotInheritedWhenCloned`
  (`DAT_1833935e8`, acces indexe).

## 3. Le releve : tous les sites, et l'offset qu'ils visent

**Mutateurs ADDITIFS de `OrderedSet<UnitTrait>` (les seuls qui peuvent rendre `+0x50` non vide) :**

| voie | sites (exhaustif) | offset ecrit |
|---|---|---|
| `Add` DIRECT (`MethodInfo` `OrderedSet<UnitTrait>::Add`) | `StaticBattleRules.Trait$$.cctor` **et lui seul** (24 sites) | tables STATIQUES de la classe, aucun composant |
| `Add` par interface (`ICollection<UnitTrait>`, slot 0) | `IdunBattle.Operations.AddTraitOperation$$Execute`, `...$$AddTrait`, `IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits` (les 2 surcharges), `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent`, + `idun.tests.AbilityAnimationTest$$AddTraitToUnit` et `idun.tests.ability_adaptive_strategy_test.u003CRunAbilityTestInternalu003Ed__2$$MoveNext` (harnais de test, hors jeu) | **`+0x40` / `+0x48` uniquement** |
| `OrderedSetu003C...u003E$$AddRange` | 40 appelants, **aucun** sur des `UnitTrait` de composant (tuiles, `ValidTargets`, selecteurs, configs de test) ; l'unique appelant « generique » est le ctor-copie lui-meme | -- |
| `OrderedSetu003C...u003E$$UnionWith` | 2 appelants : `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` / `...$$GetCurrentAndMovableTilesOf` (positions/tuiles) | -- |
| `OrderedSetu003C...u003E$$Insert` | appele **uniquement** par `OrderedSetu003C...u003E$$set_Item` | -- |
| `OrderedSetu003C...u003E$$set_Item`, `...$$System.Collections.Generic.ICollectionu003CTu003E.Add` | **aucun appelant de code** (uniquement des refs de vtable / tables d'interface) | -- |
| ctor `OrderedSet<UnitTrait>()` | `BaseUnitComponent$$.ctor` (3x) + `StaticBattleRules.Trait$$.cctor` | cree VIDE |
| ctor-copie `OrderedSet<UnitTrait>(IEnumerable)` | `BaseUnitComponent$$Copy` + `UnitComponent$$Copy` **et eux seuls** | copie a l'identique |

**Les operations metier de trait, relues integralement -- aucune ne mentionne `+0x50` :**

```
AddTraitOperation$$Execute / $$AddTrait
    comp = UnitExtensions$$GetBaseUnitComponent(target)
    (isTemporary ? comp+0x48 : comp+0x40).Add(trait)          // jamais +0x50

RemoveTraitOperation$$Execute / $$RemoveTrait
    comp = GetComponent<UnitComponent>(target)
    (isTemporary ? comp+0x48 : comp+0x40).Remove(trait)       // DESTRUCTIF sur les additifs
                                                             // JAMAIS additif sur un ensemble de veto

AddUnitOperation$$AddUnitTypeTraits (les 2 surcharges)        // +0x40 seulement
AddUnitOperation$$RemoveTraitsThatAreNotInheritedWhenCloned   // lit +0x40, delegue a RemoveTrait
UnitFactory$$InitBaseComponent                                // seede +0x40 depuis la config
```

## 4. Correction d'une justification anterieure (`case-225` §1)

`case-225-dynamic-trait-gates.md` rangeait `+0x50` en « hors de portee » en s'appuyant, entre
autres, sur le fait que `IdunBattle.Operations.RemoveTraitOperation$$Execute` n'a
« que `Core.Services.OperationProcessor$$RemoveTrait` en appelant (slot d'interface, sans appelant
direct) ». **La conclusion tenait, la justification etait fragile** : la voie `RemoveTrait` est
reellement empruntee EN JEU, chaine complete lue au decompile --

```
AddUnitOperation$$Execute  |  AddUnitOperation$$AddMiscTraits
    -> AddUnitOperation$$RemoveTraitsThatAreNotInheritedWhenCloned
        -> (slot d'interface IOperationProcessor)
            -> Core.Services.OperationProcessor$$RemoveTrait
                -> IdunBattle.Operations.RemoveTraitOperation$$Execute
```

-- elle s'execute donc a chaque clonage/ajout d'unite. Ce qui rend `+0x50` inerte n'est PAS que
`RemoveTrait` serait inaccessible : c'est que `RemoveTrait` **retire de `+0x40`/`+0x48`** au lieu
d'ajouter a `+0x50`. Le retrait de trait est **destructif sur les ensembles additifs**, jamais
additif sur un ensemble de veto. `DisabledTraits` est un troisieme mecanisme, cable dans `HasTrait`
mais que **rien n'alimente**.

## 5. Gate de confrontabilite

Sans objet : il n'y a aucun chemin natif a emprunter, donc aucun porteur (hero / MoW / summon) a
chercher. La question « quel porteur spawnable declenche l'ecriture de `+0x50` » n'a pas de reponse
parce que la question n'a pas d'objet -- et c'est le resultat, pas un blocage de harnais.

## 6. Ce que ca change pour le port, et ce que ca ne change PAS

* **Rien a porter** pour le veto. Un `HasTrait` offline qui ignore `DisabledTraits` est exact.
* **Ce qui reste vrai et non couvert** : le veto est inerte, mais les DEUX autres collections, elles,
  bougent (`AddTraitOperation` ecrit `+0x40`/`+0x48`, `RemoveTraitOperation` en retire). Le seul
  canal juste cote snapshot reste donc celui qui passe par un mirror de
  `IdunBattle.Entities.UnitExtensions$$HasTrait` (lequel delegue a
  `BaseUnitComponent$$HasTrait`) -- pas une lecture directe du kit gameconfig par `visualId`. Le
  residu `case-225` §5.1 (23 gates de decision encore sur un substrat statique) et `case-225` §5.3
  (aucun RPC ne publie les traits RUNTIME) **restent ouverts** : ils portent sur `+0x40`/`+0x48`,
  que cette fiche ne referme pas.
* Corollaire pour le point d'ancrage propose en `case-225` §5.3 : un futur hook n'a besoin
  d'exposer que `+0x40` et `+0x48`. Publier `+0x50` serait du bruit constant a vide.

## 7. Ce qui rouvrirait la question (limites assumees)

1. **Changement de build.** Tout ce releve est un ensemble de xrefs du binaire `rnca9r7q6c`. Une
   mise a jour du jeu peut introduire un ecrivain ; la mesure est a rejouer (§8), pas a heriter.
2. **Aliasing de champ.** La preuve porte sur les MUTATIONS de la collection. Une reassignation
   `compA.DisabledTraits = <une autre collection deja peuplee>` n'apparaitrait dans aucune xref de
   mutateur. Elle est cependant tres contrainte : les seules `OrderedSet<UnitTrait>` du binaire sont
   celles des composants (creees vides) et les tables statiques de `StaticBattleRules.Trait`, dont
   les 4 lecteurs de globals (`BaseUnitComponent$$.ctor`, `...$$Copy`, `UnitComponent$$Copy`,
   `StaticBattleRules.Trait$$.cctor`) ont ete lus ligne a ligne -- aucun n'ecrit `+0x50` avec autre
   chose qu'un set neuf ou une copie.
3. **Reflexion / deserialisation.** Le composant n'est pas deserialise depuis la BC : il est
   construit par `UnitFactory$$InitBaseComponent` a partir de la `UnitConfiguration`, qui n'alimente
   que `+0x40`. La seed BC du depot (`data/seed-bc.json`) ne contient d'ailleurs aucune occurrence
   de `DisabledTraits`.

## 8. Rejouer la mesure (procedure, ghidra-mcp, binaire `/GameAssembly.dll`)

1. `decompile_function` sur `IdunBattle.Entities.Components.BaseUnitComponent$$.ctor` -> relever le
   `MethodInfo*` (dernier argument du `OrderedSet<>$$.ctor`) et confirmer que les trois champs
   `+0x40/+0x48/+0x50` recoivent un set NEUF.
2. `list_xrefs` sur ce `MethodInfo*` -> doit ne rendre que `BaseUnitComponent$$.ctor` et
   `StaticBattleRules.Trait$$.cctor`.
3. `decompile_function` sur `StaticBattleRules.Trait$$.cctor` -> relever le `MethodInfo*` passe aux
   `OrderedSetu003C...u003E$$Add` : c'est celui de `OrderedSet<UnitTrait>::Add`.
4. `list_xrefs` sur ce `MethodInfo*` -> **si un appelant autre que la cctor apparait, la mesure est
   perimee**.
5. `list_xrefs` sur les `Il2CppClass*` d'interfaces relevees dans
   `BaseUnitComponent$$HasTrait` / `AddTraitOperation$$AddTrait` /
   `AddUnitOperation$$RemoveTraitsThatAreNotInheritedWhenCloned`, puis lire l'offset vise par chaque
   appelant du modele (les appelants `idun.Game.Board.AUnitView$$*` / `*Visuals` / `idun.Ui.*` sont
   la VUE et travaillent sur leurs propres listes).
6. `list_xrefs` sur `OrderedSetu003C...u003E$$AddRange`, `$$UnionWith`, `$$Insert`, `$$set_Item`,
   `$$System.Collections.Generic.ICollectionu003CTu003E.Add`.
