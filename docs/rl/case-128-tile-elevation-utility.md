# Case #128 — le terme d'ELEVATION de tuile ne domine PAS a tort : il est fidele, la divergence est AILLEURS

**Statut** : RE COMPLETE (decompile + lecture vtable LIVE + confrontation live). **Verdict : le terme
`Elevation(8)` du composite `Tile(7)` est une CONSTANTE — mirror exact, valeur / poids / signe / gate /
position tous verifies. Aucun fix sur ce terme (toute retouche serait du fitting).** L'etage reellement
divergent est l'**ENSEMBLE DE CANDIDATS** de l'action d'ability, pas le bareme de tuile.

Build `gqfc5mff6c`. Probe : `scripts/python/probe_128_tile_elevation_arbitration.py`.
Aucun changement `frida/hooks`, aucun rebuild, aucun reinject.

---

## 1. La question, et la reponse

> Sur l'etat mesure (#124 §7), le moteur choisit-il la MEME action que l'IA native ? Et en amont :
> **le terme d'utilite de TUILE lie a l'elevation est-il porte fidelement ?**

- **Le terme est porte FIDELEMENT** (§2, §3). Il n'est ni mal value, ni mal pondere, ni mal signe.
- **Il n'est meme pas l'agent de la divergence** : sur un etat ou il est le SEUL discriminant, le natif
  paie exactement le meme `+10/niveau` que le port (§4, mesure S3).
- ~~**Le port sur-genere des candidats**~~ — **REFUTE** (R1, `case-r1-origin-action-tile.md`). Le natif
  MET la tuile d'ORIGINE dans ses candidats, et elle y est la PREMIERE : le slot `IBattleQuery`+0xe est
  `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`, dont l'`OrderedSet` est SEEDE
  avec `GetUnitPosition(unit)` avant `UnionWith(movable)`. 10 contre-exemples live. La coincidence
  numerique du §5 (« argmax sans l'origine = action native ») reste vraie, son MECANISME est faux — et le
  retrait de l'origine aurait ete un FORK, pas un fix. Ce qui a ete porte a la place est l'ORDRE du sweep
  (origine EN TETE). Detail et encadre : §5.
- **Residu non ferme** : la divergence S3 reste OUVERTE, et son explication du §5 ne tient plus (l'ecart
  est de 1.925, donc ce n'est pas un tie que l'ordre trancherait). Piste nommee au §7 (le x1.25
  positionnel du degat predit depuis l'ORIGINE) et reprise dans `case-r1-origin-action-tile.md` §5. Sur
  l'etat S1 (1197 disponible), l'ecart subsiste egalement — candidat `fable-solver` (§6).

## 2. Le terme, lu au decompile (chaine complete)

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
somme, dans cet ordre (RE ligne a ligne) :

```
u  = vtable+0x338  CalculateCustomUtility(unit, position, target, ability, ...)   # NormalAttack : +1
u += CalculateUtilityFromPredictions(...)                                          # Sigma damage/heal/effet/repair
if !ShouldExecute(unit, mainTile, target, u): return null                           # vtable+0x328
u += vtable+0x348  CalculateCasterPositionUtility(...)                              # base = Fix64(0)
u += UtilitiesDatabase[0x36 = WireweaveNet_FirstAttack].EvaluateAttack(UtilityAttackCase)
u += CalculateUtilityFromTilePrediction(...)                                        # <-- LE TERME DE TUILE
return Nullable(u)
```

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromTilePrediction` :

```
if (vtable+0x318)():            return Fix64(0)     # get_IgnoreTileUtility
pos = (vtable+0x398)(unit, position, target)        # MakeFinalTilePrediction
if pos.MainTile == null:        return Fix64(0)
case = new UtilityMovementCase(unit, pos, 0, Nullable<AbilityType>(this+0x10), 0, 0)
return Fix64(0) + playbookUtilities[7 = Tile].EvaluateMovement(case)
```

**Les trois inconnues de cette fonction sont maintenant TRANCHEES, par lecture d'octets et de vtable
runtime (RPC `resolveVtableSlot`, klass live des playbooks concernes) :**

| slot | methode (nom lu runtime) | pointeur (identique pour `Loki_NormalAttackPlaybook`, `ExcruciatingFrequenciesPlaybook`, `HealPlaybook`) | octets | semantique |
|---|---|---|---|---|
| +0x318 | `get_IgnoreTileUtility` | `0x1802b15a0` (partage avec `get_CanHandleNullCasterTile` — repli ICF) | `32 c0 c3` = `xor al,al ; ret` | **FALSE** -> le terme de tuile s'applique TOUJOURS |
| +0x398 | `MakeFinalTilePrediction` | `0x1803088d0` | `49 8b c0 c3` = `mov rax,r8 ; ret` | **identite** sur le 3e argument -> la tuile evaluee = la tuile candidate du caster |
| +0x348 | `CalculateCasterPositionUtility` | `0x1814077f0` (base) | — | `Fix64(0)` |

Aucun playbook du jeu n'override `get_IgnoreTileUtility` (aucun symbole `*$$get_IgnoreTileUtility` dans
la table, et les 3 klass lues live pointent sur le meme stub).

### Le composite `Tile(7)` : membership lue au decompile (plus une supposition)

`IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility(db, utilityType, profil)` resout un
`utilityType` en composite via une **carte de composition** `db+0x58` (`Dictionary<UtilityType,
UtilityType[]>`) : `list = map[utilityType]` -> `Map(list, GetUtility)` -> 1 element = l'utilite seule,
`> 1` = `new ComposedUtility(list)`. Sinon `db+0x60` = fabrique de feuille (config `GetUtilityConfig`).

`IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities` remplit cette carte :

| cle | taille du tableau | signification |
|---|---|---|
| **7 (`Tile`)** | **0x1d = 29** | le composite porte par `engine/utilities/tile.py::TILE_LEAF_IDS` (29 feuilles, dont `Elevation(8)`) |
| 0x22 (34 `Damage`) | 0xd = 13 | les 13 feuilles Damage |
| 0x2e (46) | 3 | — |
| 0 | 2 = `[7, 1]` | |
| 0x20 (32) | 2 = `[7, 0x21]` | |
| 6 (`UnitMovement`) | 2 = `[7, 0x10 = MinDistanceToClosestEnemy]` | le sweep MOVE = Tile(7) + MinDist |
| 5 (`UnitMovementFromTemporary`) | 2 = `[6, 0x11]` | |

`IdunBattle.AI.Playbook.BasePlaybook$$Init` pose `playbook+0x40 = param_8` — c'est **la MEME
`UtilitiesDatabase`** que celle du sweep de mouvement, pas un profil par playbook. Il n'existe d'ailleurs
que **deux** profils dans la BC (`Utilities.Default` et `Utilities.MovementSuggestion`, ce dernier
reduit a `{RangedAdjacentEnemy: {HasAdjacentEnemy: -50}}` — **aucun Elevation**).

### La feuille elle-meme

`IdunBattle.AI.Utilities.ElevationUtility.u003CEvaluateMovementInStepsu003Ed__8$$MoveNext` :

```
if (!this.loaded) { LoadRelevantTileElevations(); this.loaded = true; }   # this+0x68, one-shot
tile = case.Position.MainTile ;  elev = TileComponent(tile)+0x18 -> this+0x6c
u  = GetUtilityValue("Multiplier") * elev
if (elev == this+0x60 /*max board*/) u += GetUtilityValue("HighestElevation")
if (elev == this+0x64 /*min board*/) u += GetUtilityValue("LowestElevation")
```

BC `Utilities.Default.Elevation = {Multiplier: 10, HighestElevation: 10, LowestElevation: -5}`.
`IdunBattle.AI.Utilities.ElevationUtility$$LoadRelevantTileElevations` enumere **tout le board**
(max seed 0 @this+0x60, min seed 10 @this+0x64).

**`engine/utilities/tile.py::ElevationUtility.evaluate` est le mirror 1:1 de ce corps**, alimente par
`engine/playbook/base.py::tile_utility` (meta = `elevation` + `elevation_max`/`elevation_min` sur
`ctx.elev_by_pos` COMPLET = tileMeta board). Rien a corriger.

## 3. Confrontation live — l'etage DEGAT est bit-exact, donc hors de cause

Etat d'ancrage (mirror de #124 §7) : board `C4_02`, caster `emperNoiseMarine` (u81) en (2,2) elev 3,
ennemis `eldarRanger` (u77) en (4,3) elev 1 et `astraBullgryn` (u79) en (5,4) elev 1, `--hp-target 90000`
(regime volontairement « degat faible » : les utilites de degat valent 5-11, le terme de tuile 10-30 —
c'est l'etat ou le terme de tuile est le plus discriminant possible).

Pour **chaque** (ability, cible, tuile) de `decisionView.attackPlans`, la prediction du port est
**identique au chiffre natif** :

| ability | cible | tuile | natif (dmgMin,dmgMax) | moteur |
|---|---|---|---|---|
| 69 | 79 | (2,2) e3 | (5448, 8166) | (5448, 8166) |
| 69 | 79 | (3,3)/(3,4)/(3,5) e3 | (4356, 6534) | (4356, 6534) |
| 69 | 77 | e2 x9 | (3630, 5445) | (3630, 5445) |
| 1197 | 77 | (4,2) e2 | (5744, 8615) | (5744, 8615) |

18/18 lignes exactes. **L'etage DEGAT n'est pas la divergence** — il n'y a donc rien a « fitter » du cote
utilite de degat non plus.

## 4. La mesure S3 — le terme d'elevation ARBITRE, et il arbitre comme le natif

Le probleme des etats a ability speciale : deux termes bougent a la fois. **S3 isole le terme** en
CONSOMMANT la speciale : on joue reellement l'action native (`applyAction` move+ability), on passe deux
tours, on repose l'etat a l'identique — `ExcruciatingFrequencies` est alors en cooldown et il ne reste que
l'attaque NORMALE. Le choix de TUILE du natif devient une mesure directe du terme `Tile(7)`.

| | ability | cible | tuile | `u` degat | `Tile(7)` | custom | total |
|---|---|---|---|---|---|---|---|
| **natif S3** | **69** | **77** | **(3,3) e3** | 8.961 | 30 | 1 | **39.961** |
| moteur S3 | 69 | 79 | (2,2) e3 (= ORIGINE) | 10.886 | 30 | 1 | 41.886 |
| (concurrents e2, degat NATIF IDENTIQUE) | 69 | 77 | (3,2)/(4,1)/(3,1)/(5,2)/(5,1)/(4,0) e2 | 8.961 | 20 | 1 | 29.961 |

**Deux enseignements, tous deux positifs pour le port :**

1. **Le natif paie l'elevation.** A degat natif STRICTEMENT identique (5625, 7440) depuis (3,3) e3 et
   depuis six tuiles e2, il choisit la tuile e3. Un moteur sans terme d'elevation (ou avec un terme
   rabote) ne reproduirait pas ce choix. **Le `+10/niveau` est donc bien dans l'utilite d'ACTION native,
   exactement comme le port l'applique.** Le raboter pour faire gagner 1197 aurait casse CE cas.
2. **L'ordre des cibles du port est bon a 0.25 pres.** Depuis (3,3) le natif prend 77 (`u=8.961`) et pas
   79 (`u=8.710`) : le port classe ces deux candidats dans le MEME ordre, avec une marge de 0.25 sur ~40.

## 5. ~~L'etage reellement divergent : la TUILE D'ORIGINE est dans les candidats du port, pas dans ceux du natif~~ — **SECTION REFUTEE**

> ⚠ **CETTE SECTION EST FAUSSE dans son MECANISME** (verdict R1, `case-r1-origin-action-tile.md`).
> Le slot `IBattleQuery`+0xe n'est PAS `GetMovableTilesFor` mais
> `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`, dont l'`OrderedSet` est
> SEEDE avec `GetUnitPosition(unit)` avant `UnionWith(movable)` : **le natif MET l'origine dans ses
> candidats, en premier**. Refutation live : 10 chunks natifs « caste sans bouger » avec un movable
> NON vide (3 couples board/seed). La coincidence numerique du §5 (« argmax sans l'origine = action
> native ») reste vraie ; son explication ne l'est pas, et l'ecart S3 n'est PAS un tie (1.925), donc
> l'ordre de sweep ne l'explique pas davantage. **La divergence S3 reste OUVERTE** — piste nommee au
> §7 de ce document et reprise dans `case-r1-origin-action-tile.md` §5 (le x1.25 positionnel du degat
> depuis l'ORIGINE). Le texte d'origine est conserve ci-dessous comme trace de la mesure.

Sur S3 le natif descend a `39.961` alors que la tuile d'ORIGINE (2,2) offre au port `41.886` — et (2,2)
n'est pas moins bonne en tuile (e3, `Tile(7)=30`) ni en degat (elle est la MEILLEURE : natif
(8436, 11160) contre (5625, 7440)). Le natif la refuse.

Chaine native (RE) :

- `IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext` calcule
  `tiles = IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles(unit, ...)` puis appelle
  `ActiveAbilityActionGenerator.GenerateActions(unit, position, tiles, ...)`.
- `GenerateActionTiles` = `IBattleQuery.slot+0xe(unit, ...)` (les tuiles de MOUVEMENT) puis, pour chaque
  ability de l'unite, un hook de playbook qui peut AJOUTER des tuiles (`PlaybookDatabase.LoadPlaybook`
  -> slot 1 sur la liste).
- `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`
  boucle EXCLUSIVEMENT sur cette liste ; la tuile courante n'est evaluee que par la branche
  **`if (count(tiles) == 0) { if (playbook.CanHandleNullCasterTile) Evaluate(unit, NullPosition) }`**,
  c'est-a-dire seulement quand l'unite n'a plus AUCUNE tuile de mouvement.
- Cote outillage, notre propre hook le dit noir sur blanc :
  `frida/hooks/features/ai-step/internals.ts` — « `GetMovableTilesFor` exclut la tile d'origine ; on
  l'ajoute au set candidat pour que "rester sur place et attaquer" soit rankee ». `attackPlans.ranked`
  contient donc l'origine **par construction de l'outil**, et `engine/ai/action_generators.py::
  _best_attack` la consomme telle quelle (aucun filtre `movable`).
- Mesure : `aiMovableTiles u81` = 20 tuiles, **origine incluse = False**.

**Chiffre du verdict (S3)** : `argmax` du port en retirant le seul candidat « tuile d'origine » =
`ab=69 tgt=77 to=(3,3) u=39.961` = **exactement l'action native** (ability + cible + tuile).

⚠ **NON PORTE ici, deliberement** — et c'est ce qui a evite une regression : la tranche dediee (R1) a
etabli au decompile que le retrait de l'origine aurait ete un FORK, pas un fix (cf. l'encadre en tete
de section). Ce qui a ete porte a la place, c'est l'ORDRE (origine EN TETE du sweep) :
`case-r1-origin-action-tile.md`.

## 6. Residu NON ferme (candidat `fable-solver`)

Etat S1 (identique a S3 mais **1197 disponible**) :

| | ability | cible | tuile | total port |
|---|---|---|---|---|
| natif | **1197** | tuile 50 = (4,2) | to=(4,1) e2 | 27.977 |
| moteur | 69 | 79 | (2,2) e3 (origine) | 38.563 |
| moteur, sans l'origine | 69 | 79 | (3,3) e3 | 37.050 |

Le retrait de l'origine (§5) **ne suffit pas** : il reste `69@(3,3) = 6.050 + 30 + 1 = 37.05` contre
`1197@(4,1) = 7.977 + 20 = 27.977`. Pour que le natif prefere 1197 il faudrait `u(1197) > 17.05`, soit
~2.1x notre valeur — alors que le rapport `u/degat` du port est verifie exact sur 1197 comme sur 69
(§3), et que l'ordre des cibles de 69 est confirme a 0.25 pres (§4).

Hypotheses ECARTEES par la mesure ou le decompile (ne pas y revenir) :

| hypothese | refutation |
|---|---|
| terme d'elevation absent / rabote cote natif | S3 : le natif choisit la tuile e3 a degat egal (§4) ; et `get_IgnoreTileUtility` = `xor al,al` |
| `MakeFinalTilePrediction` renverrait la tuile de la CIBLE | octets `49 8b c0 c3` = identite sur la position (§2) |
| composite Tile(7) different pour le playbook d'attaque | `BasePlaybook.Init` : `playbook+0x40` = LA base d'utilites partagee ; carte de composition cle 7 = 29 feuilles (§2) |
| profil de poids par playbook | la BC n'a que `Default` et `MovementSuggestion` ; ce dernier n'a pas d'Elevation |
| tier / priorite d'ability (speciale avant normale) | `GetDefaultActiveAbilityActionGenerators` = `[NC(1000),NC(100),NC(0),NC(-100),NC(-1000), Comparable(special)]` : **un seul** generateur Comparable, et son `<GenerateActions>d__7` cree **UN SEUL `Bucket` AVANT la boucle d'abilities** et n'appelle `ChooseAction` qu'apres l'avoir epuisee -> argmax INTER-ability par utilite, pas premier-legal (corrige la pseudo-code de `docs/rl/playbook/architecture.md` §2.3quater) |
| gate d'elevation sur l'ELIGIBILITE de cible (`|Delta elev| >= 2` interdirait d'attaquer d'en haut) | filtre qui « colle » numeriquement sur S1 mais **REFUTE** : S3 montre le natif attaquant depuis (3,3) e3 une cible en e1 (dElev=2) ; et `abilityTargets.fromHere` (= `AttackQuery.GetValidTargets` natif, legalite exacte du cast immediat) rend 79 valide depuis (2,2) e3. **C'etait un sur-ajustement — non porte.** |
| prediction de degat sur/sous-estimee | 18/18 lignes bit-exactes vs natif (§3) |
| `MakeEffectPredictions` de 1197 (Suppressed) apporterait l'utilite manquante | vtable +0x378 de `ExcruciatingFrequenciesPlaybook` = le stub de base `0x18140a930` (liste vide) — pas d'override |

Points d'ancrage a lire pour la suite (nommes, non lus faute de perimetre) :
`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$Merge` /
`$$ChooseAction` (arbre `SortedList<Key, sous-Bucket>` + admission `FUN_18004cc80(bucket, action)`
appelee dans `ComparablePlaybook.EvaluateInternal` AVANT l'argmax) — c'est le seul etage de la chaine
qui n'a pas ete lu ligne a ligne, et le seul ou une preference structurelle (hors utilite) pourrait
encore vivre.

## 7. Ce qui n'est PAS couvert

- La correction §5 (tuile d'origine) : **diagnostic REFUTE** par la tranche R1
  (`case-r1-origin-action-tile.md`) ; ce qui a ete porte est l'ORDRE de sweep, pas un retrait.
- Le residu §6 : non ferme.
- Le regime de mesure est volontairement extreme (`--hp-target 90000`) pour maximiser le poids relatif du
  terme de tuile. En HP realistes les utilites de degat (~200-500) ecrasent le terme (10-50) et l'ecart
  observe ici ne se manifeste pas — c'est pourquoi il n'apparait pas dans l'agreement courant.
- Le `x1.25` systematique du degat natif depuis la tuile d'ORIGINE (ex. (5448,8166) contre (4356,6534)
  pour la meme paire) est reproduit exactement par le port ; sa cause (modificateur positionnel) n'a pas
  ete investiguee — hors perimetre, et sans effet sur les verdicts ci-dessus.

## 8. Reproduire

```
python probe_128_tile_elevation_arbitration.py            # C4_02, emperNoiseMarine vs eldarRanger+astraBullgryn
python probe_128_tile_elevation_arbitration.py --p-units emperNoiseMarine,eldarRanger   # + temoin sans 1197
```

La probe imprime, PAR ETAGE : les candidats 1197 (`u` / `Tile(7)@P` separes), les candidats d'attaque
(`u` / `Tile(7)` / `custom` / degat NATIF vs MOTEUR), la ventilation de `Tile(7)` par FEUILLE, et
l'argmax du port sous variantes d'ensemble-candidat (tel quel / sans l'origine / `dElev < 2`) — c'est
cette derniere ligne qui a permis de trancher entre les hypotheses du §6.
