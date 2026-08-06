# #477-r21-r3 — L'ALLOCATION ECS des entités d'EFFET

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **1** (chaude, aucun reinject).
La **règle** d'allocation est portée (`engine/streams/entity_allocator.py`) et confrontée sur
**3 scénarios** : **50 / 78 / 72** identifiants de déploiement dérivés **exacts**, ancre du
déroulé **59 / 87 / 81** **exacte**, et **63/63, 67/67, 22/22** allocations du déroulé
reproduites. **Le verrou n'était pas la règle** — c'est la **séquence de création**, et elle
appartient à **#477-r21-r2**.

```powershell
python scripts/python/probe_477r21r3_allocation_effets.py            # live, 3 scenarios
python scripts/python/probe_477r21r3_allocation_effets.py --auto-test-gardes   # OFFLINE
python -m pytest scripts/python/tests/engine/test_477r21r3_entity_allocator_offline.py -q
```

## 1. La réponse à la question binaire

> **Le port peut-il DÉRIVER l'identifiant ECS de chaque entité d'effet, sans lire aucun id du
> flux ?**

**La RÈGLE, oui — et elle est portée. L'ATTRIBUTION, non**, parce qu'elle exige de connaître
l'ordre des appels à `AddEffectOperation$$Execute`, **dont certains n'écrivent aucune ligne**.
Ce n'est pas une limite de l'allocateur : c'est la **sélection**.

La décomposition en cinq étages est ce qui permet de le dire — un verdict global aurait masqué
le seul étage qui répond non.

## 2. La RE — un compteur, neuf sites, aucun recyclage

`IdunBattle.Entities.Components.MatchComponent$$NextId` est le **SEUL** producteur
d'identifiant du binaire (xrefs Ghidra, liste exhaustive) :

```
NextId()        this.<+0x10> += 1 ; return this.<+0x10>      -- PRE-incrementation
ReturnLastId()  this.<+0x10> -= 1
.ctor()         this.<+0x10> = 1
```

| fonction native | ids | note |
|---|---|---|
| `AddPlayerOperation$$Execute` | 1 / joueur | |
| `AddEnvironmentAbilityOperation$$Execute` | 1 / ability | 2 sites, branches **exclusives** |
| `AddTileOperation$$Execute` / `$$CreateTile` | 1 / tuile | **rollback** si la factory rend null |
| `AddUnitOperation$$Execute` | **1 + 1 par pied** | 2ᵉ site **dans une boucle** |
| `AddMachineOperation$$Execute` | 1 / machine | aucun pied |
| `AddMachineOfWarPlatformOperation$$Execute` | 1 / plateforme | |
| `AddEffectOperation$$Execute` | **1 / effet créé** | **conditionnel** — § 4 |

⚠ **`ReturnLastId` n'a que DEUX sites, tous deux sur le chemin TUILE.** Il n'existe donc
**aucun recyclage** pendant le déroulé : un effet retiré, une unité morte, un summon disparu ne
rendent jamais leur id. C'est ce qui rend la suite **prévisible** dès qu'on connaît l'ordre des
créations — et c'est la contre-épreuve `effet-recycle`.

⚠ **UN EFFET COÛTE EXACTEMENT UN ID.** `Blueprints$$Effect(id)` construit une
`Core.EffectEntity` et lui attache un seul `EffectComponent` : aucune sous-entité, donc aucun
pas variable comme pour l'unité (contre-épreuve `effet-avec-pied`).

L'amorçage est fermé : `Blueprints$$Match(1)` prend le **littéral** 1 et son `.ctor` pose
`+0x10 = 1` ; `InitializeMatchOperation$$Execute` incrémente le champ **directement** (pas via
`NextId`) → 2 ; le premier `NextId` rend **3**, et **l'id 2 n'est jamais attribué**.

## 3. Le résultat, mesuré

| étage | `C1_02` | `MC1_67` | 2v2 crafté |
|---|---:|---:|---:|
| (A1) identifiants du **déploiement** dérivés, sans en lire aucun | **50 EXACT** | **78 EXACT** | **72 EXACT** |
| (A2) **ancre** du déroulé (prévue = observée) | **59** | **87** | **81** |
| (A3) créations **muettes** dans l'intervalle | 2 | 4 | 5 |
| (A6) leur **nature** (`dumpEntityComponents`) | `Effect` ×2 | `Effect` ×4 | `Effect` ×5 |
| (A4) **inversions** apparition vs allocation — flux entier / bloc 1 | 4 / **0** | 3 / **0** | 0 / **0** |
| (A5) allocateur par **ordre d'apparition** | 7 / 61 | 7 / 63 | 4 / 17 |
| (A5) allocateur par **ordre de création** | **63 / 63** | **67 / 67** | **22 / 22** |

**Les deux lignes (A5) sont le résultat.** La seconde établit que la règle est **SUFFISANTE** :
dès que la suite des créations lui est donnée, l'allocateur rend **tous** les identifiants, y
compris ceux des unités placées et des summons. La première chiffre ce que vaudrait un émetteur
alimenté par le seul ordre du flux — **7 / 7 / 4**, soit un décrochage dès le premier effet muet.

⚠ **L'ancre 59 n'est pas celle du premier EFFET, et c'est voulu.** Un flux réel déploie
**5** unités dans `System_GameSetup` puis **5** par `User_PlaceUnit` (#477-r18-r5) : la première
entité d'après le déploiement prédéfini est donc une unité, pas un effet. Le port dérive
l'ancre du **déroulé**, et les unités placées consomment ensuite `1 + pieds` chacune.

## 4. Ce qui manque, NOMMÉ

Le flux **n'écrit rien** à la création d'un effet : `AddEffectOperation$$Execute` n'émet aucune
`Action`. Ce qu'on y voit est le `Group=Effect_Refresh` que `RefreshEffectsOperation` produit
**ensuite** — et seulement **si** `eventActions.Count > 0` (#477-r21). D'où deux écarts, tous
deux mesurés :

1. **des créations entières sont TUES** — 2 / 4 / 5 entités par scénario. `dumpEntityComponents`
   les rend toutes de type `IdunBattle.Entities.Enum.EntityType.Effect`, et **vivantes à la fin
   du déroulé** : ce ne sont pas des entités détruites ;
2. **l'ordre d'apparition n'est pas l'ordre d'allocation** — 4 / 3 / 0 inversions sur le flux
   entier. Un effet d'aura est créé au `MatchInit` et n'ouvre son premier groupe qu'au moment où
   une cible entre dans son rayon.

⚠ **Dans le BLOC 1 de `System_StartMatch`, il y a 0 inversion sur 3/3** (39 / 41 / 12
apparitions). L'ordre y est croissant — mais **avec des trous**, donc le rang d'apparition ne
suffit toujours pas.

**La condition d'allocation est LUE**, et c'est elle qui relie ce résidu à la sélection.
`AddEffectOperation$$Execute` sort **avant toute allocation** sur quatre chemins :

```
owner == null                                        -> log, retour null
<config d'effet>.<slot 0x28>(owner)                  -> retour null
owner.IsUnit() && UnitExtensions$$HasFlag(owner, 6)  -> log, retour ; 6 = UnitFlag.Dead
UpdateExistingEffect(...) == true                    -> l'effet EXISTANT est mis a jour
```

`AddEffectOperation$$UpdateExistingEffect` commence par
`StaticBattleRules.Effect$$IsUpdatable(effectType)` — un balayage d'une table statique dont le
défaut est `effectType != 0x472` — puis parcourt les effets **déjà portés** par la cible en
cherchant le même `EffectType` (`effectComponent.<+0x58>`), la même parenté
(`effectComponent.<+0x70>`) et une configuration dont le slot 5 est faux. **Trouvé ⇒ aucune
entité créée.** Toutes ces conditions vivent dans l'**état ECS** : c'est **#477-r21-r2**.

⚠ **`UpdateExistingEffect` est un SECOND producteur de `Group=Effect_Refresh`**, distinct de
`RefreshEffectsOperation$$GenerateEventGroup` : elle ouvre le groupe (`0x16`) avec
`Enum.ToString(effectComponent.<+0x58>)`, puis émet un `ReceiveEffect` à dictionnaire **vide**,
un `Action` porteur du seul `Effect_RemainingTurns` (`0xa5`), un autre du seul
`Effect_CurrentLevel` (`0xa7`), et ferme. Lu, **non porté** — hors du périmètre de cette tranche.

## 5. Ce que la tranche change pour #477-r21

La borne (c) de `probe_477r21` portait **quatre** entrées, dont « les IDENTIFIANTS D'ENTITÉ
ECS ». Cette entrée ne disparaît pas — elle **fusionne** avec la première : c'est désormais la
**même** donnée manquante, la sélection. Le probe le dit explicitement plutôt que de laisser
croire à deux verrous indépendants.

⚠ **`Effect_Refresh` AUTONOMES reste 0 / 0 / 0, et ce zéro est MESURÉ.** #477-r19 avait annoncé
`System_StartMatch` comme débloqueur ; #477-r20 l'a réfuté par la mesure. Cette tranche ne
réintroduit pas l'inférence dans l'autre sens : elle était **nécessaire, pas suffisante**, et le
chiffre publié par `probe_477r21` est celui que ce probe mesure, jamais celui qu'on déduirait de
cette livraison.

## 6. Les contre-épreuves — 6 mordent et rougissent, 1 est déclarée NON EXERCÉE

`post-increment`, `sans-initialize`, `une-plateforme`, `unite-sans-pieds`, `effet-avec-pied`,
`effet-recycle` : **6 / 6 sur 3 / 3 scénarios**, `a_morde` publié **séparément** du verdict.

⚠ **`unite-pas-fixe` (« une unité coûte 2 ») ne peut PAS mordre sur nos corpus** : toutes les
unités y sont mono-pied, donc `1 + pieds` et `2` y sont la même valeur. Le probe ne la retire pas
en silence et ne la compte pas verte : il la marque **NON EXERCÉE** et **dit pourquoi**. Le jour
où un porteur multi-pieds entre au corpus, elle redevient un cran — c'est **#477-r16-r2**.
L'auto-test offline l'exerce, lui, sur un roster fabriqué `9 mono-pied + 1 bi-pied`.

**Vue rouge avant le fix**, par mutation adversariale du port :

- `next_id` en **post-incrément** → **11 tests rouges**, dont
  `` compteur : `.ctor`=1, `InitializeMatch`, 1er `NextId` -> 2 ROUGE `` et
  `` temoin #477-r16 (regle, 10 unites) : (1re tuile, 1re unite, id suivant) = (11, 48, 69) ROUGE, attendu (12, 49, 69) `` ;
- `add_effect` consommant **deux** ids → **3 tests rouges**, dont
  `` (A5) discrimine : APPARITION=1/4 (autonome=False), CREATION=0/5 (suffisant=False) ROUGE ``.

⚠ **L'ANCRE SEULE NE DISCRIMINE PAS LE POST-INCRÉMENT** : le mutant consomme le même nombre
d'incréments, donc `last_id + 1` ne bouge pas. Ce sont les identifiants **individuels** qui le
font tomber — raison pour laquelle (A1) confronte chaque famille et pas seulement l'offset.

## 7. Ce qui n'est PAS couvert

- **La séquence de création** → **#477-r21-r2** (§ 4).
- **La boucle multi-pieds** d'`AddUnitOperation` : lue, **jamais exercée** — aucun porteur
  multi-tuiles dans les montages joués → **#477-r16-r2**.
- **`AddMachineOperation`** : porté (`add_machine`), **non confronté** — aucune Machine of War
  dans les trois scénarios.
- **Le rollback tuile** : porté et testé offline, **jamais observé en live** (aucune factory ne
  rend null sur nos boards).
- **`UpdateExistingEffect` comme producteur de flux** (§ 4) : lu, non porté.
- **La nature des créations muettes au-delà du type** : `dumpEntityComponents` donne
  `EntityType.Effect`, pas l'`EffectType` ni le porteur. Le point d'ancrage natif qui le dirait
  est un hook sur `AddEffectOperation$$Execute` — **aucun reinject n'a été fait**, donc il reste
  à poser.
