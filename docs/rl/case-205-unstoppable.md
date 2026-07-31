# Case #205 — trait **Unstoppable** (mouvement : ne s'arrete pas sur les hex speciaux)

> Trait `Unstoppable` (`UnitTrait` **0x412 = 1042**), porte par ~31 unites (10 lineup). RE
> decompile complet (VAs `gqfc5mff6c`). **Verdict : INVALIDABLE en runner** — trait de MOUVEMENT
> pur dont le fondement (effets de tuile finissant/bloquant le mouvement dans la reachability)
> n'est PAS porte (walk_pathfinder) ET est inerte sur tous les boards runner. Doctrine
> `no-unvalidatable-ability-ports` : documente, **PAS de port speculatif**. Livrable = doc + probe.

## 0. Porteurs (gameconfig, cle `traits`)

31 unites : **10 lineup** (`admecRuststalker`, `astraDreir`, `bloodDeathCompany`, `genesPatriarch`,
`orksNob`, `spaceRockfist`, `spaceStormcaller`, `spaceWulfen`, `worldEightbound`, `worldTerminator`),
17 npc (bosses Ruststalker/Nob/Patriarch/Eightbound/Terminator, DeathRider, Harlequin, ...) + 4 summons
(`astraSmnDeathRider`, `eldarSmnHarlequin`, `genesSmnGenestealer`, ...). Porteurs spawnables valides :
`orksNob` (melee move4), `spaceStormcaller` (ranged move2). Ils EXISTENT et sont spawnables — la
limitation n'est PAS le porteur, c'est la MECANIQUE (invalidable, cf. §3).

Texte i2 (orientation seulement, non-derivant) : « This unit does not have to stop on special hexes
and hex effects that would normally force a unit to end their Movement. »

## 1. RE — decompile = verite (VAs `gqfc5mff6c`)

### 1.1 Unstoppable = un trait d'EXEMPTION de mouvement, pas une ability/effet

Aucune classe `Unstoppable*Ability` (les symboles `UnstoppableMomentum*`/`UnstoppableFerocity*`/
`WarHowl_*_Unstoppable*` sont d'AUTRES kits homonymes, sans rapport). Aucune string « Unstoppable ».
Le trait est un **id d'enum** (`UnitTrait 0x412=1042`, `il2cpp_enums.tsv`), consomme UNIQUEMENT comme
membre de la liste d'exemption ci-dessous. C'est un modificateur du PATHFINDING de marche.

### 1.2 La liste d'exemption partagee — `NotBlockingMovementOfTraits @18155b370`

`StaticBattleRules.Effect.NotBlockingMovementOfTraits(int effectType) @18155b370` (decompile lu) rend,
selon le type d'effet, la liste des traits qui **ne sont PAS bloques/arretes** par cet effet de tuile :

- `effectType == 0` (BlockEnteringUnits), `== 5` (**Fire**), `== 0x11=17` (**Ice**) ->
  `List{ 0, 0x405, 0x412 }` = **{ Mounted(0), Vehicle(0x405=1029), Unstoppable(0x412=1042) }**.
- `effectType == 0x3a=58` -> `List{ 0x1d=29 }` (NightVision — autre famille).
- sinon -> `null`.

=> **Unstoppable (1042) est exempte du blocage/arret de mouvement des effets de tuile 0/5/17**,
au meme titre que Mounted et Vehicle. (Le trait Flying de l'i2 passe par un AUTRE chemin — les
volants prennent le `FlyPathfinder`, cf. §1.4 — d'ou l'i2 « excluding Flying and Unstoppable ».)

### 1.3 Les effets de tuile qui stockent la liste (@+0x488)

Chaque effet de tuile bloquant/finissant le mouvement stocke sa liste d'exemption a l'offset `+0x488` :

- `BlockEnteringUnitsTileEffect.ctor @180f35510` : `ABondEffect(1,0,...)`, puis
  `*(this+0x488) = NotBlockingMovementOfTraits(0)` -> {Mounted, Vehicle, Unstoppable}. (Pose par
  `AddBlockEnteringUnitsEffectBehaviour` @180f930d0 <- `DSLFactory.AddBlockEnteringUnitsEffect @180de6160`
  ; utilise par Thorns/Swamp `ThornsBlockMovementAbility @1811c8d70`, BrokenIce, Ice, Instinctive.)
- `FireEffect.ctor @180f43f40` : `*(this+0x10) = 5` (EffectType Fire), `*(this+0x488) =
  NotBlockingMovementOfTraits(5)` -> {Mounted, Vehicle, Unstoppable}. => **un hex en feu finit le
  mouvement, sauf Mounted/Vehicle/Unstoppable** (= l'i2 « entering a Fire hex ends movement,
  excluding Flying and Unstoppable » ; deja note dans terrain-effects.md §6.2 comme concern MOUVEMENT,
  distinct du gate DEGAT `EnvFireTileAbility.CreateBehaviour @18121e040` qui exclut Steppable/Immune).
- `IceEffect.ctor @180f44bc0` : `*(this+0x488) = NotBlockingMovementOfTraits(0x11)` (terrain-effects.md
  §ICE ligne 143 : « pose NotBlockingMovementOfTraits(0x11) @+0x488 -> blocage de mouvement, exemption
  par trait »).

### 1.4 Consommation dans le pathfinding — le vrai « stop »

- `WalkPathfinder.GetTileBlockingReasons @180f2e9d0` itere les effets de la tuile ; pour chaque effet, il
  teste `effect.exemptTraits(@+0x488).Any(t => movingUnit.HasTrait(t))` (predicat `Func` lie a l'unite
  en mouvement, `UnitExtensions.HasTrait @180ed6ff0`). **Si l'unite a un trait exempt (dont Unstoppable),
  l'effet ne pose AUCUN bit de blocage** pour elle. Sinon il pose un masque de bits (bit 0x1 =
  block-entering, bit 0x2 = movement-ending, bit 0x4 = occupant ennemi).
- `WalkPathfinder.GetEffectiveDepth @180f2e920` : `if (GetTileBlockingReasons & 2) depth = Min(1, depth)`
  sinon `BasePathfinder.GetEffectiveDepth`. **Bit 0x2 = « l'hex finit le mouvement »** -> la profondeur
  restante est capee (l'unite s'arrete sur/apres cette tuile). Exempte (Unstoppable) -> pas de bit 0x2
  -> pas de cap -> **ne s'arrete pas**.
- `WalkPathfinder.IsValidContinuePathTile @180f2ee30` : `GetTileBlockingReasons == 0` -> une tuile
  block-entering (bit 0x1) ne peut etre ni traversee ni un stop ; exempte -> traversable.
- `BasePathfinder.NodesInNextLevel @180ee28b0` gate l'expansion BFS sur ce predicat par-noeud.
- `MovementQuery.GetPathfinderTypeForUnit @18109a7b0` : selectionne le pathfinder par EFFETS
  (0x40b/0x474/0x4d6/9999) + `IsLikeFlying`, **PAS** par Unstoppable -> une unite Unstoppable prend le
  `WalkPathfinder` normal et n'est exemptee que via la liste d'effet (confirme : pas de pathfinder dedie).

### 1.5 Conclusion RE

**Unstoppable est un trait de MOUVEMENT PUR**, consomme a un SEUL endroit : la liste d'exemption
`NotBlockingMovementOfTraits` des effets de tuile finissant/bloquant le mouvement (Fire=5, Ice=17,
BlockEnteringUnits=0). Aucune face DECISION/PREDICTION ni combat/degat/stat (verifie : le seul id
1042 hardcode cote natif est cette liste ; les autres 1042 du code = enums QUALIFIES differents —
`ActiveAbilityType.FlailSwing`, `TriggeredAbilityType.HailOfLivingAmmunition`, etc.).

## 2. Etat du moteur Python

- `engine/entities/traits/unit_trait.py:107` : `Unstoppable = 1042` **defini, AUCUN consommateur**.
  ⚠ **PERIME depuis (re-derive le 2026-07-31, case-366-r1)** : l'exemption EST portee --
  `services/static_battle_rules.py::_MOVEMENT_EXEMPT_TRAIT_IDS = (0, 0x405, 0x412)` (mirror
  `StaticBattleRules.Effect$$NotBlockingMovementOfTraits`), consommee par
  `entities/pathfinding/tile_blocking.py` et `walk_pathfinder.py`. Le POSEUR dynamique du trait
  existe lui aussi cote natif et est desormais LU : `WarHowl_ExtraDamage_UnstoppableEffect$$
  ApplyInternal`/`RevertInternal` = `AddTrait`/`RemoveTrait(0x412, isTemporary: 1)` -- MESURE live,
  `u81` gagne 1042 dans `combatSnapshot.units[].traits` au cast de `WarHowl`, et le perd a
  l'expiration. Le reste du §3 (mecanique invalidable faute d'hex finissant le mouvement sur les
  boards runner) reste a re-verifier avant d'etre cite.
- `engine/entities/pathfinding/walk_pathfinder.py` : le port du WalkPathfinder ne modelise NI le cap
  `GetEffectiveDepth` (movement-ending, bit 0x2) NI le gate bit 0x1 (block-entering). Son en-tete le
  dit explicitement : « `GetEffectiveDepth` (hazard tile -> Min(1,depth), @180f2e920) non encore
  plombe (pas de tuile-hazard sur board basique) — TODO si une feuille hazard apparait ». Le predicat
  d'arete `is_valid_path_node` ne regarde que `walkable` + `|Delta elev|<=1` + `!ennemi`.
- `docs/rl/terrain-effects.md` #131 / §5 B4 (« Thorns/Swamp/BrokenIce : blocage mouvement
  (pathfinding) ») : famille movement-block **DEFEREE**, verdict explicite « **Ne PAS porter tant
  qu'un board/trigger jouable n'est pas confirme** (impossible a valider live sinon ; static-block
  deja refute) ». Les effets de tuile movement-block sont poses DYNAMIQUEMENT en combat (`AddEffect`
  sur `Tiles(...)`), que le runner ne materialise pas (terrain-effects.md §0).

Donc : **le FONDEMENT dont Unstoppable est l'exemption (effets de tuile finissant/bloquant le
mouvement dans la reachability) n'existe pas offline, et aucun board runner ne le porte.** Porter
l'exemption Unstoppable maintenant = ajouter un `if unit.has_trait("Unstoppable")` a une branche
`if effect ends movement` qui n'existe pas -> **code registered-but-dead** (anti-pattern doctrine).

## 3. Verdict : INVALIDABLE en runner (no-unvalidatable-ability-ports)

Le porteur existe et est spawnable, mais la MECANIQUE est **invalidable** dans le harness runner :

1. **Offline** : `walk_pathfinder` ne modelise aucun movement-ending -> rien a bypasser (l'exemption
   serait inerte).
2. **Runner** : aucun board ne porte d'hex finissant le mouvement (le terrain statique — Swamp,
   DryBush, ... — est walkable et ne tronque pas ; les effets dynamiques ne sont pas materialises).
3. **offline == live EXACT sur board a hex speciaux = PREUVE de non-troncature** (§4) : l'offline
   IGNORE tout movement-ending ; s'il y en avait un live, l'offline aurait des tuiles `extra`.

Porter Unstoppable exigerait d'abord de porter la tranche #131/B4 (materialiser les effets de tuile
Fire/Ice/BlockEnteringUnits sur les tuiles + gate `GetEffectiveDepth`/bit-0x1 dans
`get_reachable_levels`/`get_movable_positions`), elle-meme gatee sur un board/trigger jouable. **C'est
un CANDIDAT de la tranche movement-stop #131/B4, PAS un port de feuille isolee.** Point de branchement
futur (une fois le fondement porte) : dans `walk_pathfinder`, quand un effet movement-ending/block est
present sur une tuile, l'exempter si `moving_unit` a un trait de `NotBlockingMovementOfTraits(effectType)`
= {Mounted(0), Vehicle(1029), Unstoppable(1042)} pour {0,5,17} (mirror @18155b370).

## 4. Preuve live (adversariale) — `probe_205_unstoppable.py`

Board **MC1_67** (DryBush x3 + Swamp x4, tous walkable), porteurs Unstoppable :

```
[205] board special-hex candidates: DryBushx3(walkable=True), Swampx4(walkable=True)
[205] u81 [orksNob] mr=4 native=18 pred=18 extra=[] missing=[]
[205]   hex-speciaux atteints (<=mr): [((1,3),'Swamp',4), ((3,2),'DryBush',3)] ;
        tuiles au-dela du 1er hex special dans le stop-set: 6
[205] u83 [spaceStormcaller] mr=2 native=6 pred=6 extra=[] missing=[]
[205] C: get_movable_positions/get_reachable_levels reference un trait movement ? False
```

- **A. offline == live EXACT** pour chaque porteur (orksNob 18/18, Stormcaller 6/6 ; `extra=[]`,
  `missing=[]`). L'offline (sans movement-ending) reproduit le natif au bit -> le natif NE TRONQUE PAS
  sur Swamp/DryBush -> **aucun hex finissant le mouvement sur ce board**.
- **B. construction** : orksNob atteint le Swamp @(1,3, depth 4) et le DryBush @(3,2, depth 3) ET 6
  tuiles a profondeur > 3 (au-dela du 1er hex special) sont dans le stop-set -> non-troncature confirmee.
- **C. inertness structurelle** : le pathfinder ne reference AUCUN trait movement -> retirer Unstoppable
  du ctx ne change rien offline.
- **Generalisation** : `tests/engine/entities/pathfinding/test_pathfinding_live.py` (3 passed) exige
  `get_movable_positions == aiMovableTiles` EXACT pour TOUTES les unites WALK d'un board live — 100%.
  Si un board runner appliquait un movement-ending, l'offline aurait des tuiles `extra` -> echec. Le
  100% est donc la preuve generale qu'aucun board runner ne tronque le mouvement (rien a bypasser).

## 5. Residus / suite

- **Fondement movement-stop #131/B4 (DEFERE)** : porter la materialisation des effets de tuile Fire(5)/
  Ice(17)/BlockEnteringUnits(0) sur les tuiles + le gate `GetEffectiveDepth`(bit 0x2)/`IsValidContinue
  PathTile`(bit 0x1) dans la reachability. Unstoppable (+ Mounted + Vehicle) = l'EXEMPTION a cabler DANS
  cette tranche (mirror `NotBlockingMovementOfTraits @18155b370`). Validation future : comparer live
  `aiMovableTiles` d'un porteur Unstoppable vs non-porteur sur un board portant un hex finissant le
  mouvement — l'un traverse, l'autre s'arrete. `[opus]` une fois le fondement pose.
- **Aucune face DECISION/PREDICTION** a porter (Unstoppable n'influe que la reachability, elle-meme
  derivee du meme pathfinder cote IA via `state_bridge._move_tiles`).
