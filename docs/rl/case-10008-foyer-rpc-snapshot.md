# #10008 — les huit résidus du foyer `rpc-snapshot.ts`, re-mesurés

Tranche du 2026-08-15, build `t6dpr4k06g`, session Frida 93. Huit résidus partageant le foyer
`frida/hooks/features/ai-step/rpc-snapshot.ts`. Volet live :
`scripts/python/probe_10008_canaux_du_foyer.py` (5 volets). Garde hors Frida :
`frida/tools/probe-10008-canaux-du-foyer.ts` (40 contrôles).

## Le résultat qui commande tout le reste

**Six capteurs sur huit étaient déjà EN VOL** au moment du dispatch, armés par une fenêtre
antérieure. La consigne « conçois pour qu'UNE SEULE fenêtre les arme tous » portait donc sur un
état périmé. Mesuré par appel RPC réel sur la session 93, pas par grep du bundle — `frida/dist/`
peut avoir été reconstruit depuis l'injection, il ne prouve rien :

| canal | RPC | en vol ? |
|---|---|---|
| `attacksMadeThisTurn` (`+0x24`) | `actorStats` | oui |
| `attacksReceivedThisTurn` (`+0x38`) | `actorStats` | oui |
| `movement.*` + `nullableLayout` | `actorStats` | oui |
| `rarity` / `rarityLayout` | `combatSnapshot` | oui |
| `tertiary` (+ `tertiaryLevelMeasured`) | `combatSnapshot` | oui |
| `currentOwnerIsEnvironment` | `combatSnapshot` | oui |
| `receiveDamageTypeThisTurn` | `actorStats` | **non — écrit ici** |
| `weapons` | `combatSnapshot` | **non — écrit ici** |

## Verdicts

### `#545-r1` + `#287-r5-r2` — CONFRONTÉS (régime discriminant atteint)

Les deux fiches déclarent le régime discriminant NON ATTEINT : « la marche d'approche a calé sur
la géométrie, les deux côtés rendaient `0/0`, un accord DÉGÉNÉRÉ ». **Deux causes, toutes deux
levées** :

1. la géométrie de spawn se **contourne** par `--place` / `--a-place` : attaquant et cible sur
   deux tuiles adjacentes, l'attaque part sans déplacement ;
2. il faut **DEUX unités** de son côté. Avec une seule, le tour se termine tout seul après le
   cast et `IdunBattle.Operations.StartTurnOperation$$ResetUnit` remet les compteurs à zéro
   *avant* la lecture. Mesuré : un premier montage à une unité rend `0/0` après une attaque qui
   avait pourtant porté 9037 → 4985 PV.

Mesure (`--volet v1`) : NATIF `e77 (made=1, recv=0)`, `e81 (0,1)`, `e79 (0,0)` ; PORT sur état
RECHARGÉ identique ; CONTREFACTUEL sans le canal → `(0,0)` des deux côtés, donc re-divergence.

### `#1039-r1` — CLOS (4ᵉ bras vert, régime non dégénéré)

`unitsNotAlive[].rarity` publie sur une unité ayant **FUI** : entité 103, `unitFlags [9=Fled,
26=Removed]`, `rarity 0`. Les raretés lues valent `{0, 5}` — **discriminant**, ce qui n'était pas
acquis : les gardes posés en cours de bataille par `applyAddUnit` échappent à la normalisation de
`rl_duel build` et gardent leur rareté de **catalogue**, là où le roster initial porte
`targetRarity = 5`. Le bras (2) de `#999-r3`, lui, discrimine par `--unit-stat`, qui ne s'applique
qu'aux unités vivantes.

**Critère recadré, et c'est un choix de méthode** : arrimer le verdict au flag `Fled`, c'est
l'arrimer à un TIRAGE (`BattleFatigue` : 10 % / 40 % en overkill) — le premier passage a rendu
0 enfuie sur seed 777. La question du résidu porte sur le CANAL ; `Fled` en est le cas le plus
dur et reste un **sous-bras**, non bloquant.

### `#347-r3` — CONFIRMÉ, et la fiche est *doublement* dépassée

Le correctif est en vol et MORD : `decode: "ok"`, tuiles décodées. Surtout, la disposition
mesurée est `{hasValueOff: 0, valueOff: 8}` — **ni** `{T value; bool hasValue}` (l'hypothèse que
le capteur supposait, `hasValue` à `off + 8`), **ni** `{hasValue @+0, value @+4}` (celle que
`game/match-state.ts` avait relevée sur `MachinePlatformComponent`, et que la fiche propose comme
la bonne). L'offset de `value` suit l'**alignement de `T`**. Un choix « à l'œil » entre les deux
hypothèses aurait donc été faux **dans les deux cas** : la dérivation par métadonnées n'est pas
la voie prudente, c'est la seule.

Le mécanisme de l'accident se vérifie sur le brut publié : `[1, 0, 679530336, 352]`. L'ancienne
lecture prenait l'octet de poids faible du mot 2 (= 224), non nul dès que la liste existe — le
drapeau « marchait » par coïncidence, exactement comme la fiche l'annonçait.

### `#1036-r8` — PRÉMISSE RÉFUTÉE

La fiche conclut `UnitContext.tertiary_ability = None`, `tertiary_ability_level = 0` pour toute
Machine, et en tire que « toute magnitude d'aura de MoW est structurellement nulle côté port ».
Mesure sur le montage même que la fiche prescrit (`--p-mow necroReanimator --equip-mythic
necroReanimator:GuardianConstruct:4`) : le niveau arrive **par deux voies indépendantes**.

* `unitAbilityStates` — canal **préexistant**, non spécifique aux Machines : entrée `triggered`
  avec `raw[10] == 3` (hiérarchie tertiaire) et `level = 4`. C'est ce que
  `snapshot._load_tertiary_abilities` consomme déjà, et le port rend
  `tertiary_ability = 'GuardianConstruct'`, `level = 4` sur un état rechargé.
* `combatSnapshot.units[].tertiary` (capteur #1072) — `{ability: 1530, level: 4, multiplier: 100}`
  sur l'entité 77, `entityType 6`.

Accord **non dégénéré** (`4`, pas `0`). Le mur n'existe plus. Gardé par `--volet v4`.

### `#969-r4` — PORTÉ, et le blocage `porteur` RÉFUTÉ pour le terme qui mord

**Deux corrections de RE** (relu sur `t6dpr4k06g`) :

1. le `ListExtensions.Remove` n'est **pas** dans
   `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` (3 surcharges) mais dans
   `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` (4 surcharges), que la
   première appelle. Le nom du lambda le disait déjà
   (`...BasePlaybook$$u003CGetEligibleTargetsEntitiesu003Eb__58_0`). L'effet est le même, la
   citation ne l'était pas ;
2. `IdunBattle.Entities.UnitExtensions$$IsIrrelevantObject` se lit
   `HasTrait(Steppable=27) || (GetStat(Attack=0) < 1 && HasTrait(Object=13))` — le seuil est
   `< 1`, **pas** `== 0`.

`BasePlaybook$$ShouldEvaluateTarget` et
`IdunBattle.Entities.EntityExtensions$$CurrentOwnerIsEnvironment` sont conformes à la fiche.

**Porteur** — `unit_map find --trait Steppable` rend les power-ups, `--trait Object` les
`LootObj_*`. Aucun n'est au seed BC (175 unités), donc `applyAddUnit` y échoue **en silence** ;
ils entrent par `catalog_inject.write_augmented_seed_bc` puis `applyAddUnit`. Mesuré (runner 112,
MC1_67) : `LootObj_Strongbox_Imp` (traits `13,28`, `stats.attack = 0`) figure dans
`abilityTargets(77).fromHere` **à côté** d'`orksKillaKan` — le port le retenait, le natif le
retire. La dégradation permissive est reproduite.

Le second terme (`CurrentOwnerIsEnvironment`) reste **sans porteur** : `False` partout
(`PlayerType` Human/AI). Il est porté et mesuré ; son régime discriminant reste à atteindre.

⚠ **Piège trouvé en écrivant la garde** : `IsUnit` et « porte un `BaseUnitComponent` » sont deux
drapeaux **distincts**. Une Machine of War n'est pas forcément `IsUnit` mais en porte un (son
`MachineComponent` en dérive). Un port écrivant `if not is_unit: return True` aurait rendu le
filtre **inerte sur les MoW**.

### `#487-r2` et `#419-r1-tr14-r5-r2-r1-r2-r1-r2` — CAPTEURS ÉCRITS, en attente d'armement

Ce sont les deux seuls qui exigent encore une fenêtre. **Deux prémisses de fiche corrigées**,
toutes deux mesurées au RPC `classFields` (lecture pure) :

* `ActorStatisticsComponent+0x80` n'est **pas** un scalaire `receivedDamageThisTurn` : c'est un
  `Dictionary<DamageProfileType, int>` nommé **`ReceiveDamageTypeThisTurn`** — un compte
  d'instances par profil, jamais une somme de dégâts. Un `fieldOffsetOr(asClass,
  "ReceivedDamageThisTurn", 0x80)` se serait **replié en silence** sur le littéral décompilé ; un
  `readS32` aurait publié les 4 octets bas d'un **pointeur**, c'est-à-dire un entier énorme, non
  nul et parfaitement plausible pour « des dégâts ont été reçus ». Le port, lui, portait la bonne
  forme depuis #202.
* `WeaponsComponent` expose **`<Weapons>k__BackingField`** (backing field d'auto-property) :
  chercher `"Weapons"` ne résout rien. Structure lue :
  `WeaponProfile{DamageProfileType@+0x10, DamageProfile@+0x18, Hits@+0x20,
  Range@+0x24 (Nullable<Int32>)}`, et
  `IdunShared.Battle.WeaponProfile$$get_IsMelee` = `!Range.HasValue || Range.Value < 2`.
  Une arme de portée **1 est MELEE** — aucune arme du gameconfig n'a `Range == 1`, donc une faute
  de seuil serait **invisible en live**.

## Le cran de garde que cette tranche ajoute

**La définition OUVERTE d'un générique ne porte aucun layout, et une garde `< 0` ne le voit pas.**
Mesuré session 93 : `classFields("System.Collections.Generic", "Dictionary\`2")` rend
`boxedSize: 0` et ses **dix** champs à l'offset 0 ; idem `System.Nullable\`1`. Résoudre depuis un
nom de classe générique donnerait donc `_entries@0` et `_count@0` — deux offsets qui ne sont pas
négatifs. Les deux modules dérivent le layout de l'**instance inflatée** (obtenue du type du
champ) et refusent explicitement la disposition ouverte par une garde de **plage** (offsets
`>= 0x10` et **distincts**).

Contre-épreuve : garde retirée → le harnais rougit avec `errors: []`, c'est-à-dire un canal
**résolu à l'offset 0**.

## Ce qui n'est PAS couvert

* Les deux canaux neufs ne sont **pas confrontés en live** — il faut la fenêtre. `--volet v3`
  rend `PAS EN VOL` / `ok: null` et distingue « absent » (rien à conclure) de « présent et
  faux ».
* `CurrentOwnerIsEnvironment` n'a **aucun porteur** : le terme est porté et mesuré, jamais
  exercé.
* Le port ne **change pas de substrat** pour les armes : `engine/services/battle_query.py::
  has_ranged_weapon` continue de lire le gameconfig. Le canal ECS est livré pour **mesurer**
  l'écart (`--volet v3` le confronte profil par profil) ; le changer avant de l'avoir mesuré
  serait spéculatif.
* Une surcharge du slot virtuel `0x248` (`ShouldEvaluateTarget`) par un playbook particulier n'a
  pas été balayée — l'absence dans les tables ne prouve rien (dedup ICF).
