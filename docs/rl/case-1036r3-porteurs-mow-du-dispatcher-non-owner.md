# #1036-r3 / #433-r4-r3-r1-r1 / #433-r4-r3-r1-r2 — les derniers corps `TriggeredAbilityNonOwnerPlaybook<T>` : ce n'était pas la rareté, c'est l'univers de porteurs

**Verdict** : la famille passe de **23/28** à **27/28** corps portés. Les quatre livrés le sont
**hors registre**, blocage `etage` **mesuré** — leur porteur est une **Machine of War**, que
l'univers de porteurs des trois dispatchers ne voit pas. Le cinquième et dernier
(`SabreOfSacrifice` 1478) a un blocage d'une autre nature. **Les trois fiches disaient faux, sur
trois axes différents.**

Outils : `scripts/python/probe_1036r3_porteurs_non_owner_restants.py` (mesure),
`scripts/python/tests/engine/test_1036r3_faces_non_owner_restantes_offline.py` (14 tests, cliquet).

---

## 1. Les trois prémisses, re-mesurées

| fiche | ce qu'elle disait | mesure |
|---|---|---|
| `#433-r4-r3-r1-r1` | **11** faces MOVE dérivées directes non portées | **4** — sept portées entre-temps (1457/1461/1495 par #477-r33, 1469/1526/1531 par #477-r35, 1064 par #477-r37) et personne n'avait re-compté |
| `#433-r4-r3-r1-r2` | 3 ATTACK + 1 REPAIR **jamais portées** ; « le port n'a pas de foyer pour eux : c'est un **câblage à créer**, pas une entrée à ajouter » | **RÉFUTÉ** — les trois dispatchers (`evaluate` / `evaluate_attack_in_steps` / `evaluate_repair_in_steps`) et les trois registres existent depuis #271-r4 et #271-r7. Restait **1** corps ATTACK, **0** REPAIR |
| `#1036-r3` + bloc de commentaire du registre | gates sur la **RARETÉ**, « aucun canal `rarity` n'existe côté port ; le verrou est un **CAPTEUR MANQUANT** » (⇒ fenêtre de reinject) | **PÉRIMÉ** — `UnitContext.rarity` existe (capteur #1039, consommé #999-r3) et **deux des trois** `*_leaf_ctx` publient `ctx["scene"]`, donc `scene.ctx(uid).rarity` est atteignable depuis la face MOVE |

Le compte de 11 est le même vice que celui déjà corrigé deux fois dans cette famille (25 concrets
annoncés pour 28) : un chiffre écrit une fois, jamais re-dérivé.

## 2. La cause réelle : le porteur est une Machine of War

Les cinq corps sans entrée de registre, et leur porteur (voies dérivées par `unit_map`) :

| corps | id | face | porteur | MoW ? |
|---|---|---|---|---|
| `CabalOfSorcerersPlaybook` | 1496 | MOVE | `thousDaemonPrince`, `thousNpcMowDaemonPrince` | **oui** |
| `WisdomOfTheAncientsPlaybook` | 1451 | MOVE | `ultraDreadnought`, `ultraNpcMoWDreadnought` | **oui** |
| `MastersOfManoeuvreNonOwnerPlaybook` | 1508 | MOVE | `darkaStormSpeeder`, `darkaNpcMowStormSpeeder` | **oui** |
| `ShieldOfFaithNonOwnerPlaybook` | 1453 | ATTACK | `adeptExorcist`, `adeptNpcMoWExorcist` | **oui** |
| `SabreOfSacrificeNonOwnerPlaybook` | 1478 | MOVE | `astraDreir` (relique équipable) | non |

Quatre sur cinq sont des **mythiques de MoW** (voie `mythicAbilities`, invisible de toute autre —
`case-323` §2). Or l'univers de porteurs des dispatchers portés est bâti sur des entités
**positionnées** :

- **face MOVE** — `TriggeredAbilitiesNonOwnerUtility.evaluate` itère `ctx["friend_units"]` +
  `ctx["enemy_units"]`, que les trois `*_leaf_ctx` construisent en exigeant une position
  (`PositionComponent` côté runner, `pos.col is not None` côté `Scene`) ;
- **faces ATTACK / REPAIR** — elles itèrent `Scene.units`, c'est-à-dire `decisionView.units`, d'où
  le natif exclut les Machines par construction (canal `.mows` **séparé**, cf. `Scene.machine_ids`).

Une MoW n'a **aucune tuile** : `AddMachineOperation$$Execute` ne lui donne pas de
`PositionComponent`, et le port non plus (`snapshot._load_machines`). Le natif, lui, itère
`abilityAndEffectCache.<slot 5>()` — **toutes** les `TriggeredAbility` de la bataille. La paire
`(playbook, owner)` n'est donc jamais yieldée côté port.

**Mesuré, pas déduit** (`probe` étape 2, et cliquet) : un état contenant une entité sans
`PositionComponent` rend `univers = [2]` — la Machine (id 9) n'y entre pas.

## 3. Ce qui rend le diagnostic non trivial (et explique trois tranches d'erreur)

**Aucun des quatre corps n'exige la position du porteur.**

- `MastersOfManoeuvreNonOwnerPlaybook` ne lit **même pas** `owner` : sa méthode-usine
  `$$CalculateMovementUtilityInSteps` écrit `case @+0x20, playbook @+0x28` et **laisse `+0x30`**,
  que la state machine réutilise pour son énumérateur ;
- `ShieldOfFaithNonOwnerPlaybook` non plus, pour la même raison structurelle ;
- `CabalOfSorcerersPlaybook` et `WisdomOfTheAncientsPlaybook` ne s'en servent que pour un test
  d'**identité** (`u == owner`) **à l'intérieur** de `GetAdjacentFriends(tile, case.unit)` — branche
  de toute façon inatteignable pour un porteur sans tuile.

Le blocage est donc **au-dessus** des corps. Foyer à réparer : `engine/utilities/tile.py`, jamais
`engine/playbook/non_owner*.py`. C'est ce qui a fait accuser la rareté : on lisait les corps, on y
voyait `Rarity`, et le canal manquait effectivement — à l'époque.

## 4. Rayon de souffle du geste qui débloquerait les quatre

Le geste est l'**élargissement de l'univers de porteurs aux MoW** — pendant exact de ce que
`#999-r3-r1-r1` a fait pour les deux agrégateurs d'aura (`owner_pos = None`, les termes positionnels
se taisent seuls).

Sa question de sûreté n'est pas « est-ce lisible ? » mais « **les corps déjà portés se taisent-ils
sur un porteur sans position ?** ». Mesure : **1 sur 19**.

- `NornCrownNonOwnerPlaybook` verse (10.0) — et c'est **correct** : c'est le seul corps de la
  famille dont la méthode-usine n'écrit pas `owner` (il ne pèse que le voisinage du mover) ;
- son rayon **réel** est nul : aucune MoW ne porte 1495, relique de `tyranNeurothrope`.

Les 18 autres lisent `owner["pos"]` et rendent 0 quand il manque. Le geste est donc **borné au
dispatcher** : il ne redistribue aucun terme existant.

## 5. Les quatre corps livrés — ce que le décompilé dit

Clés BC **résolues** par `probe_212_bc_key_literals.py` sur le symbole du `MoveNext`, puis
confrontées au gameconfig vivant (double confirmation).

### `CabalOfSorcerersPlaybook` (1496) — clé `CabalOfSorcerers_AffectUnits` = 20

```c
if (case.unit == null) yield break;
var buc = case.unit.GetComponent<BaseUnitComponent>();
if (buc.Rarity != 5) yield break;                      // Rarity.Mythic
if (!buc.HasTrait(0x3ea)) yield break;                  // UnitTrait.Psyker
foreach (u in Query.<slot 0x83 = GetAdjacentFriends>(case.MovementTile, case.unit)) {
    if (u == case.unit) continue;
    var b = u.GetComponent<BaseUnitComponent>();
    if (b.Rarity == 5 && b.HasTrait(0x10) && b.HasTrait(0x3ea)) yield return <clé>;
    if (u == owner)                                     yield return <clé>;
}
```

Le second membre est un **OU**, pas une seconde passe : le natif ne teste `u == owner` que quand le
triple prédicat a échoué, et les deux branches yieldent la même valeur. Le terme vaut 20 ou 0,
jamais 40.

⚠ Le nom natif est `CabalOfSorcerersPlaybook` ; le dépôt traînait la coquille `CabalOfSorcers`
(sans le second `e`) dans son commentaire de registre — corrigée.

### `WisdomOfTheAncientsPlaybook` (1451) — clé `WisdomOfTheAncients_AffectUnits` = 20

Jumeau du précédent à **deux gates près**, et c'est la seule différence : **aucun `Psyker`**, ni sur
le mover ni sur le voisin (prédicat = `Mythic && Hero`). Transposer l'un depuis l'autre aurait
ajouté deux filtres que le natif n'a pas — dégradation restrictive silencieuse. Le cliquet la rend
observable : le même montage sans aucun `Psyker` verse ici et rend 0 chez `CabalOfSorcerers`.

### `MastersOfManoeuvreNonOwnerPlaybook` (1508) — clé `MastersOfManoeuvre_AdjacentFriendlyMythicDA` = 25

```c
if (case.unit == null)                        { yield return Fix64.Zero; yield break; }
if (!UnitExtensions.HasRarity(case.unit, 5))  { yield return Fix64.Zero; yield break; }
foreach (u in Query.<slot 0x84 = GetAdjacentFriends(case.Position, case.unit)>) {
    if (u == case.unit)                     continue;
    if (!UnitExtensions.HasFaction(u, 0xa)) continue;   // UnitFaction.DarkAngels
    if (!UnitExtensions.HasRarity(u, 5))    continue;   // Rarity.Mythic
    yield return <clé>;
}
```

Le gate de rareté passe par la fonction **nommée** `UnitExtensions$$HasRarity`, là où les deux
jumeaux inlinent la lecture du composant. `HasRarity` porte un gate de plus (`<EntityType> == 1`),
noté au port plutôt que gommé. Le `0xa` est confirmé indépendamment par le **nom de la clé**
(`…_AdjacentFriendlyMythicDA`).

### `ShieldOfFaithNonOwnerPlaybook` (1453, face ATTACK) — clé `ShieldOfFaith_LikesEnemiesOnFire` = 10

```c
var caster = case.Caster;
if (caster.TryGetComponent<BaseUnitComponent>(out var buc) && buc.Rarity != 5) yield break;
if (AnyTileHasEffectOfUnit(case.Target, EffectType.Fire)) yield return <clé>;
```

Deux lectures fines :

- **si `TryGetComponent` échoue, le corps CONTINUE** — la comparaison est gardée par le succès de la
  résolution, pas l'inverse. Le port mirrore ce tri-état (`rarity is None` ⇒ on ne coupe pas), et le
  cliquet l'exerce ;
- `AnyTileHasEffectOfUnit` → `HasEffect(t, state, type, onlyActive: false)` =
  `IsOwnerOfEffect(...) || IsTargetOfEffect(...)`. La première branche itère
  `EffectsOwnedComponent.<+0x10>` sans filtre d'activité : c'est exactement
  `Scene.tile_effects_owned_by_pos` (servi avec `only_active=False`). La seconde
  (`IsTargetOfEffect`) **n'a aucun canal côté port** — écart restrictif nommé, commun à tout le
  port des effets de tuile.

`EffectType(5) = Fire` — type déclaré lu dans `frida/methods.tsv`, confirmé par le nom de la clé.

## 6. Pourquoi HORS registre, et le cran qui l'y maintient

Inscrire ces quatre classes ferait du code que le dispatcher **n'itère jamais** — patron #419. Le
précédent est explicite dans le module : `RedemptionOfTheRisenNonOwnerPlaybook`, portée depuis
#477-r33 et volontairement hors registre (0 porteur).

⚠ **`probe_419` ne voit pas ce cas-là**, et c'est mesuré : il rend `PORTE+NON CABLE = 0` sur les
trois axes, parce que « porté » y signifie « **au registre** » et « câblé » « **a un porteur** ».
Nos quatre classes ONT des porteurs : si on les inscrivait, il les classerait `porte+cable` et ne
signalerait rien. Le niveau où ça casse (le dispatcher ne voit pas les MoW) lui est structurellement
invisible — d'où le cliquet dédié.

`test_1036r3_faces_non_owner_restantes_offline.py` garde les deux sens :

1. la classe **doit exister** (sinon la RE est reperdue et le prochain lecteur ré-accusera la
   rareté), avec son `ABILITY_ID`, sa `FACE` et son `SLOT_4` confrontés au TSV versionné ;
2. elle **ne doit pas** être au registre ;
3. `test_une_entite_SANS_position_n_entre_PAS_dans_l_univers_de_porteurs_du_dispatcher` **rougit le
   jour où l'étage tombe** — c'est le signal de relire ces résidus et de câbler.

## 7. Le cinquième : `SabreOfSacrifice` (1478), NON PORTÉ

Porteur `astraDreir` — unité **normale**, relique équipable (état 2, `--equip-relic`). Son blocage
n'est donc pas celui des quatre autres, et élargir l'univers du dispatcher ne le débloquera pas.

```c
if (case.unit == null)                       yield return Fix64.Zero;
if (case.StaysOnTile(State))                 yield return Fix64.Zero;
if (!Query.<slot 0x60 = AreEntitiesAdjacent>(case.MovementTile, owner)) yield return Fix64.Zero;
if (!<arbre>.ShouldTrigger(<ctx 0x128, owner @+0x18>))                  yield return Fix64.Zero;
yield return GetUtilityValue("SabreOfSacrifice_LikesFriendlyDreir");    // 35
```

avec `SabreOfSacrificeAbility$$IsAffectedSummon(u)` =
`AreEqual(Parent(u), Owner) & IsUnitWithVisualId(u, GetStringConstant(unitId))`, et
`abilities.SabreOfSacrifice.constants.unitId == "astraNpc5DeathRider"`.

Deux manques **mesurés** — et **aucun n'est celui que la fiche annonçait** :

- le **`visualId` du MOVER** n'est publié par aucun des trois `*_leaf_ctx` (il ne l'est qu'à travers
  `scene.vis_by_id`) ;
- l'évaluateur DSL ne se branche pas sur le dict `tile_leaf_ctx`, et le gate **est** un arbre DSL
  (#149) : le porter en impératif serait recâbler à la main ce qui doit émerger des nœuds.

⚠ **`UtilityMovementCase$$StaysOnTile`, que la fiche citait comme canal manquant, EST disponible** :
son corps entier est `GetMainTile(case.unit, state) == case.Position.MainTile`, c'est-à-dire
`tile == ctx["self_pos"]`, et les trois `*_leaf_ctx` publient `self_pos`. Cette moitié de la fiche
est périmée.

## 8. Résidus

- **`#1036-r9`** (numéro **alloué et réservé** par `probe_468 --suggere 1036`) — élargir l'univers
  de porteurs des trois dispatchers aux Machines of War, puis câbler les quatre corps livrés ici.
  **FOYER:** `engine/utilities/tile.py` — **BLOCAGE:** `aucun`. Rayon de souffle **mesuré** :
  1 corps sur 19 (§4), rayon réel nul.
- **`#433-r4-r3-r1-r1`** se réduit à `SabreOfSacrifice` (§7) — **BLOCAGE:** `etage`.
- **`#1024-r7`** : `ShieldOfFaith` est désormais **portée**, il ne reste que son inscription au
  registre, qui dépend de `#1036-r9`.

## 9. Ce qui n'est PAS couvert

- **Aucune confrontation live.** Les quatre corps sont hors registre, donc aucun dispatcher ne les
  joue : il n'existe aujourd'hui **aucun montage** qui les fasse mordre côté port. La confrontation
  appartient à la tranche qui fera le geste de `#1036-r9`. Les corps sont exercés **offline**,
  gate par gate, sur un ctx crafté (14 tests, 8 mutations → 8 rouges).
- **Le `<slot 4>` des quatre** est LU dans l'entrée versionnée (`declare=0 valeur=0`), pas re-mesuré
  au runtime dans cette tranche.
- **La branche `IsTargetOfEffect`** de `ShieldOfFaith` (§5) reste sans canal.
- **`GetTiles(target)`** rend toutes les tuiles de la cible ; le port n'interroge que sa main tile
  — écart pour une cible multi-tuiles seulement.
