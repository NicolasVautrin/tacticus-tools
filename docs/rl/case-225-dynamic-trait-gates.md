# case-225 -- les gates de trait de la couche DECISION lisent un substrat STATIQUE

**Question posee.** Un `HasTrait` de playbook rend-il le MEME verdict que le natif apres qu'un
`AddTraitOperation` a accorde le trait EN COURS DE BATAILLE ?

**Reponse mesuree.** Avant #225 : NON pour les 33 gates de la couche decision, tous cables sur un
substrat statique par `visualId`. Apres #225 : OUI pour les 10 gates de la famille Tile(7) /
AdjacentUnitPreference (le plus gros cluster, et le seul dont le porteur du trait est atteignable en
runner) ; les 23 autres restent sur le substrat statique -- residus nommes en §5.

Rejouer l'inventaire : `python scripts/python/probe_225_trait_gates.py` (les chiffres ci-dessous
sont sa sortie ; il ECHOUE si sa table de gates rote).

---

## 1. Le chemin d'ECRITURE natif (ce qui peut arriver)

```
IdunBattle.Operations.AddTraitOperation$$AddTrait(this, target, trait, isTemporary)
    comp = IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent(target)
    collection = isTemporary ? comp+0x48 : comp+0x40
    collection.Add(trait)

IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait(comp, trait)
    if ((comp+0x50).Contains(trait)) return false;                 // traits RETIRES
    return (comp+0x40).Contains(trait) || (comp+0x48).Contains(trait);
```

Deux corrections a l'enonce recu :

* un ajout **PERMANENT** (`isTemporary == 0`) ecrit `+0x40`, **la meme collection** que
  `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` seede depuis la BC -- ce n'est donc
  pas « +0x48 seulement » ;
* les traits **RETIRES** (`+0x50`) sont hors de portee : il n'existe **aucun**
  `IdunBattleLogic.Entities.DSLFactory$$RemoveTrait`, et
  `IdunBattle.Operations.RemoveTraitOperation$$Execute` n'a que
  `Core.Services.OperationProcessor$$RemoveTrait` en appelant (slot d'interface, sans appelant
  direct).

Les sites d'ecriture sont **exhaustifs** : les 6 appelants de `IdunBattleLogic.Entities.DSLFactory$$AddTrait`.

| trait | id | site natif | isTemporary | cible | present au gameconfig |
|---|---|---|---|---|---|
| `Stationary` | 0x418 | `DutyEternalAbility$$ExecuteBehaviour`, `AetherStrideAbility$$ExecuteBehaviour`, `ExemplarOfTheKauyonAbility$$ExecuteBehaviour` | 0 | l'unite **SPAWNEE** (`SpawnUnitOptions`) | **0 / 669** |
| `PermaDeath` | 0x41a | `FloatingDeath_InitAbility$$CreateBehaviour` | 0 | l'Actor | 4 / 669 (dont ses 2 porteurs) |
| `AffectedByHealAndRepair` | 0x421 | `SupaCyborkBodyAbility_AddTrait$$CreateBehaviour` | 0 | l'Actor | **0 / 669** |
| data-driven | * | `EnhancementAddTraitAbility$$CreateBehaviour` (`GetEnumConstant(0x7f)`) | **1** | la Target | cf. ci-dessous |

**Ventilation des porteurs** (gate de confrontabilite) :

* `DutyEternal` -> `ultraDreadnought` (**lineup**, MoW) ; `AetherStride` -> `thousDaemonPrince`
  (**lineup**, MoW) ; `ExemplarOfTheKauyon` -> `tauShadowsun` (**lineup**, hero). Les trois sont
  spawnables : `Stationary` est **le seul trait dynamique reellement atteignable dans le harnais**.
* `FloatingDeath` -> `tyranSmnSporeMine` (**summon**, atteignable via son summoner) + npc. L'octroi
  y est **REDONDANT** : le summon porte deja `PermaDeath` a son gameconfig -> cas statique et cas
  dynamique **indiscernables**, aucune mesure possible.
* `SupaCyborkBody` -> **aucune unite en `activeAbilities`/`passiveAbilities`** : c'est une
  **RELIQUE** (`items/R_Defensive_SupaCyborkBody`), presente en `relicAbilities` de 9 ORK **npc**.
  Le precedent N13 (`KardiocoreGalvanus` porte live par `admecMarshall` et absent du kit gameconfig)
  etablit que les reliques SONT en jeu ; la seed BC courante n'en pose pas -> non confronte.
* `EnhancementAddTrait:<X>` : le gameconfig catalogue 4 abilities, et le seul chemin qui les
  INSTANCIE est `liveEvents/idunLiveEventConfigs[]/enhancements/AddTrait_0X` -> **MkXGravis,
  RapidAssault, Resilient, Infiltrate**. La seed BC a `EnhancementsEnvironmentAbilities: []` ->
  **hors du harnais** (residu §5.3).

## 2. Le chemin d'ECRITURE cote PORT existait deja

`engine/runner/abilities/behaviours/grants.py::AddTrait` (mirror du leaf DSL) ecrit
`StatsComponent.ctx.traits`. Le port a donc **deja** un magasin de traits dynamique, et
`engine/services/movement_query.py` (`get_movable_positions_with_feet`) le lit correctement
(`HasTrait(0x418)` -> aucune position de mouvement).

Le defaut n'etait donc **pas** « aucun trait dynamique n'existe offline », mais
**« la couche DECISION lit un AUTRE substrat que la couche COMBAT, pour la meme entite du meme
etat »**.

## 3. L'inventaire (33 gates, 4 accesseurs)

| accesseur | ce qu'il lit | gates | dynamique-capable |
|---|---|---|---|
| `ENTITE` | `UnitContext.traits` (kit seede **+ octrois**) + grande-alliance | **16** (10 a #225, **+6 a #232**) | **oui** |
| `GAMECONFIG` | `GC.unit(<visualId>).traits` en direct | 13 (etait 19) | non -- et **sans** la grande-alliance |
| `CTX` | `UnitContext.traits` seul | 4 | oui pour l'octroi, **non** pour la grande-alliance |
| `VIS-CACHE` | `unit_trait_ids/names(visual_id)`, `lru_cache` par visualId | 0 (etait 2) | non, **par construction** |

Les 6 gates passes en `ENTITE` par **#232** sont ceux de `noncomparable/heals.py` (N1/N4/N5/N6/N7/N8) :
ils testent `AffectedByHealAndRepair`, un trait ACCORDABLE en bataille -- ils sont donc les premiers
gates a la fois `dyn` et cables `ENTITE` (le probe les compte : `dyn ENTITE 0 -> 6`).

Les 10 gates passes en `ENTITE` par #225 :
`CapturePoint(24)`, `PowerUp(26)`, `DespoiledGround(28)` x2, `SummonDislikeDoorOpening(29)`,
`HeroLikeDoorOpening(30)`, `AttractMechanicals`, `MoveTowardsUnit(61/62)` (sujet, via
`ctx["unit_traits"]`), plus `FabricatorClawArray` et `CursedPlagueBell` (voisin, via
`friend_units`/`enemy_units[*]["traits"]`).

**Croisement {trait accordable} x {trait teste par un gate}** : 2 intersections seulement --
`Resilient` (`playbook/prediction/_shared.py`, borne de degat) et `MkXGravis`
(`playbook/prediction/normal_attack.py`, `hit_mult`). Toutes deux sur l'accesseur `GAMECONFIG`, et
toutes deux via un enhancement de **live-event** non instancie dans le harnais -> residu §5.3, pas
un defaut mesurable aujourd'hui.

## 4. Ce que #225 corrige, et pourquoi c'est UNE source

Le foyer est un **fork d'accesseurs**, pas un defaut par gate. La correction pose **une** source :

```python
# engine/entities/traits/unit_trait.py
entity_trait_names(unit_ctx, visual_id) -> frozenset   # mirror complet de BaseUnitComponent$$HasTrait
entity_trait_ids(unit_ctx, visual_id)   -> tuple
```

`unit_ctx is None` -> retombe sur la borne statique `unit_trait_names/ids(visual_id)` (inchangees).
**Non cachee** quand un ctx est fourni : `ctx.traits` est MUTABLE, et deux entites du meme
`visualId` n'ont plus forcement les memes traits des qu'une seule s'en est vu accorder un -- le
`lru_cache` par visualId etait ici un bug latent.

Quatre sites de `engine/utilities/tile.py` la consomment (les deux constructeurs de contexte de
feuille + leurs recs de voisinage) :

* `runner_tile_leaf_ctx(state, ...)` -> `StatsComponent.ctx` de l'entite ;
* `tile_leaf_ctx(ctx)` / `_adjacent_units(ctx, uid)` -> `ctx.scene.ctx(id)`. Sur le chemin OFFLINE
  (`Scene.from_state`) c'est **le meme objet** que `StatsComponent.ctx`, donc l'octroi y est vu ;
  sur le chemin LIVE, `UnitContext.from_snapshot` seede exactement `gameconfig.unit(vis).traits`
  -> **identique au bit pres** a l'ancien comportement.

## 5. Residus nommes (NON couverts)

1. **19 gates `GAMECONFIG` + 4 gates `CTX`** (familles NonComparable, prediction, `scene.py`) restent
   sur un substrat statique ou incomplet. Aucun ne teste aujourd'hui un trait accordable ET
   atteignable ; la migration est donc de la **dette de fork**, pas une divergence mesuree.
   Les 4 `CTX` ont en prime un trou propre : ils omettent le pseudo-trait de **grande-alliance**
   (`Imperial`/`Xenos`/`Chaos`), que `entity_trait_names` ajoute -- latent tant qu'aucun d'eux ne
   teste une alliance.
2. ~~**Gate MANQUANT** : `IsAffectedByHealType` absent des 6 gates de
   `engine/playbook/noncomparable/heals.py`~~ **FERME par #232** (`case-232-heal-type-gate.md`).
   Les 6 gates delèguent desormais au mirror `revive_effect.py::is_affected_by_heal_type` sur le
   substrat d'ENTITE -- ce qui ferme du meme coup deux traits d'`IsMechanical` (`LivingMetal`,
   `Vehicle`) que le module ignorait. Gisement STATIQUE mesure **VIDE** (aucune unite
   `LivingMetal`/`Vehicle` sans `Mechanical`, 0/669 portant 0x421) : la correction est neutre au bit
   pres sans octroi. La voie NATIVE d'octroi (relique `R_Defensive_SupaCyborkBody`) reste
   **non instanciable** -- ses 9 porteurs sont `kind=npc` et aucun canal de `rl_duel build` n'equipe
   d'item ; la validation passe donc par le meme leaf `AddTrait` que §6 ci-dessous.
3. **Chemin LIVE** : aucun RPC ne publie la collection de traits RUNTIME d'une unite
   (`combatSnapshot`/`decisionView`/`observeBattle` n'exposent que le kit gameconfig, cf.
   `frida/hooks/features/ai-step/rpc-snapshot.ts`). Une bataille pilotee LIVE (et non rejouee sur un
   `State`) reste donc aveugle a tout octroi. **Point d'ancrage a hooker** :
   `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent` puis lecture des trois collections
   `+0x40`/`+0x48`/`+0x50`, a exposer dans `combatSnapshot.units[*]`. Non fait ici : cela demande une
   reinjection Frida, proscrite pendant la campagne.
4. **Traits RETIRES (`+0x50`)** : non portes, et sans vecteur natif connu (cf. §1).

## 6. Validation

`scripts/python/tests/engine/test_trait_gates_dynamic_live.py` (4 tests, LIVE) :

* **neutralite** -- sans octroi, `entity_trait_*(ctx, vis) == unit_trait_*(vis)` pour **toutes** les
  unites de la bataille, et le `ctx` reellement servi aux feuilles (`runner_tile_leaf_ctx`) est
  identique a l'ancien, sujet **et** voisins ;
* **discrimination** -- montage exige par le critere (trait **absent du gameconfig**, accorde en
  jeu) : `Summon` (`UnitTrait.Summon` = 2, forme exacte du chemin data-driven
  `EnhancementAddTrait:Summon`) accorde par le leaf porte `AddTrait` a `eldarMauganRa`
  (kit = `HeavyWeapon, Hero, Overwatch, Terrifying`). `ctx["unit_traits"]`
  `(16,34,1001,1003,1006)` -> `(2,16,34,1001,1003,1006)` et la feuille `CapturePointTileUtility`
  bascule **+300 -> -300** (poids BC `heroes_on_capture_points` -> `summons_dislike_capture_points`,
  **changement de signe**). Le substrat statique par `visualId`, lui, ne bouge pas ;
* **face voisin** -- le rec de voisinage porte lui aussi le trait accorde (c'est ce que lisent les
  `FilterAdjacent*` de `AdjacentUnitPreferenceTriggeredAbilityPlaybook`).

Non-regression rejouee : `test_tile_leaf_unit_traits_live.py` + `test_tile_term_unit_gated_playbooks_live.py`
(34 passed), `test_tile_term_triggered_playbooks_live.py` + `test_move_tile_sweep_order_live.py`
(15 passed, 3 skips de montage non discriminant).
