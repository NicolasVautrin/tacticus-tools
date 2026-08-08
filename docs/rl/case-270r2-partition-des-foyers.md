# #270-r2 — le registre `CONSOMMATEURS` était une liste ÉCRITE ; **4 registres réels y manquaient**

**Statut** : RÉSOLU. Le résidu parlait d'« un huitième dict ajouté demain ». Au premier passage de
la partition, **quatre registres réels** manquaient **déjà** — et l'un d'eux portait **deux clés que
rien ne vérifiait**.

## 1. Le vice, et pourquoi ce n'était pas une découverte qu'il fallait

L'étape 1 de `probe_313` **découvre** toute `IntEnum` sous `engine/`. L'étape 5, elle, ne gardait
que les dicts inscrits à la main : exactement le mode de défaillance que l'étape 1 existe pour
fermer, réintroduit un cran plus bas.

La fiche parente (`case-270c` §7) avait raison sur le point dur : **« un dict dont les clés désignent
un enum » n'est pas décidable par AST** — une table de constantes et un registre d'abilities ont la
même forme. Généraliser l'étape 1 à l'étape 5 était donc impossible.

La réponse n'est pas la découverte, c'est la **PARTITION**. Dans les modules qui hébergent **déjà**
un registre inscrit — les **foyers**, dérivés de `CONSOMMATEURS`, jamais écrits — tout dict de
niveau module est soit **INSCRIT**, soit **ÉCARTÉ AVEC SA RAISON**. Rien ne peut y être muet. Même
patron que le recenseur de `#270-r1`, qui a cessé d'énumérer des rôles pour les **dériver**, l'inconnu
sortant sous `autre (<Nœud>)`.

Corollaire : inscrire un registre dans un module **neuf** met aussitôt **tout ce module** sous
partition. C'est ce qui empêche le vice de se déplacer d'un cran de plus.

## 2. Ce que la partition a trouvé, au premier passage

**12 dicts** de niveau module sur **2 foyers**. Quatre n'étaient pas inscrits, tous dans
`engine/entities/effects/factory.py`, tous lus par `.get(<nom>, [])` — **la même dégradation muette**
que l'étape 5 garde :

| registre | clé | voie native |
|---|---|---|
| `TRAIT_OWNER_EFFECTS` | `UnitTrait` | owner-effect posé par le trait à l'init |
| `TRAIT_DERIVED_ABILITIES` | `UnitTrait` | `AddTraitOperation$$AddDerivedAbilities` |
| `ABILITY_INIT_OWNER_EFFECTS` | ability | `<Ability>.CreateBehaviour` → `AddEffect(owner)` |
| `ABILITY_OWNER_EFFECTS` | ability | `StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility` |

`GLOBAL_TRIGGERS` est une **liste**, pas un dict indexé par clé : la partition ne la voit pas, et
c'est correct — le critère porte sur la lecture PAR CLÉ.

## 3. Deux enums, et c'est LU — pas déduit de la voie

`spawn.py::_seed_ability_owner_effects` boucle sur `activeAbilities + passiveAbilities`. Les clés des
deux registres d'ability vivent donc dans **deux** enums, et le `CLAUDE.md` le dit : la **voie** ne
dit pas l'enum — `ShroudPsalm` en `passiveAbilities` est un `ActiveAbilityType`, `Maugetar` en
`activeAbilities` un `TriggeredAbilityType`. `Consommateur.cls` accepte désormais un **tuple** ;
forcer un enum unique aurait fabriqué des `EGAREES` sur des clés justes.

## 4. Le résultat neuf — un TROISIÈME espace de noms, que personne n'avait modélisé

Inscrits tels quels, les deux registres d'ability ont rendu **2 clés cassées** :

```
EGAREE      ShadowInTheWarp     ce nom vit dans : UnitTrait
INTROUVABLE DiminutiveAbility   dans AUCUN enum du build
```

**Ce ne sont pas des fautes.** Ce sont les **abilities DÉRIVÉES d'un trait** — le natif les crée par
`IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` →
`StaticBattleRules.Trait$$GetTriggeredAbility`, et le **port les nomme lui-même**, dans les *valeurs*
de `TRAIT_DERIVED_ABILITIES`. Ce nom n'est pas celui du membre d'enum : `DiminutiveAbility` vient de
la CLASSE native (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DiminutiveAbility`),
`ShadowInTheWarp` du TRAIT. Un troisième espace de noms, **interne au port**, légitime et dérivable.

Les compter `INTROUVABLES` aurait **accusé deux entrées justes** ; ne rien vérifier aurait laissé
passer une chaîne rompue. La bonne mesure est celle **du cran du dessous** :

> **toute valeur de `TRAIT_DERIVED_ABILITIES` doit être CONSOMMÉE** — clé d'`ABILITY_INIT_OWNER_EFFECTS`,
> clé d'`ABILITY_OWNER_EFFECTS`, ou membre d'enum du build.

Sinon le trait dérive une ability que **rien ne matérialise** : `.get(nom, [])` rend `[]`, aucun
owner-effect n'est posé, et le porteur perd sa réduction **en silence**. Mesuré : **5** abilities
dérivées, **0 orpheline**.

## 5. Le cliquet

`tests/engine/test_270r2_partition_foyers_offline.py` — **5 passed**, 100 % offline :

1. `MUETS == 0` — invariant, jamais un seuil ;
2. **la partition MORD** — on désinscrit un consommateur et son dict doit redevenir muet ; c'est
   littéralement l'état de `master` avant cette tranche, où quatre dicts y étaient ;
3. les foyers sont **dérivés** de `CONSOMMATEURS`, pas écrits ;
4. les deux registres d'ability déclarent **les deux** enums ;
5. **0 orpheline** dans la chaîne trait → ability dérivée → owner-effect, et l'espace de noms dérivé
   est assertionné **non vide** (un ensemble vide passerait pour vert).

`probe_313` complet : **35 mirrors en bijection**, 12/12 registres inscrits, 0 muet, 0 orpheline.

## 6. Ce qui n'est PAS couvert

* **La partition ne voit que les FOYERS.** Un registre indexé par un membre d'enum vivant dans un
  module qui n'héberge aucun registre inscrit reste invisible. C'est le prix du critère décidable :
  la partition ne prétend pas trouver les registres, elle interdit qu'un foyer en cache un.
* **Les registres par VALEUR** restent gardés faiblement (454/458 ordinaux partagés
  `Triggered`/`Effect` nomment autre chose) — inchangé, et dit dans le code.
* **Aucun contrôle live** : la tranche est entièrement statique.
* **`HORS_PERIMETRE` est vide** aujourd'hui — donc le mécanisme d'écart motivé n'a jamais été
  exercé sur un cas réel.

## 7. Reproduction

```
python scripts/python/probe_313_enum_mirror_bijection.py
python -m pytest scripts/python/tests/engine/test_270r2_partition_foyers_offline.py -q
```
