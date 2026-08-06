# #477-r31 — `AttractMechanicals` compte les AMIS, et le port ne comptait RIEN

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp + un runner à la fois. Aucune injection.

```powershell
python scripts/python/probe_477r31_attract_mechanicals_camp.py --offline-only
python scripts/python/probe_477r31_attract_mechanicals_camp.py --board MC1_67 --seed 777 --montage camp
python scripts/python/probe_477r31_attract_mechanicals_camp.py --board MC1_67 --seed 777 --montage agreg
python -m pytest scripts/python/tests/engine/test_477r31_attract_mechanicals_camp_live.py -q
```

## 1. La réponse à la question binaire — et elle est NON

La question posée était « le terme `AttractMechanicals` compte-t-il bien les DEUX CAMPS ? ».
**Non.** Il compte les **AMIS**, self exclu, et il vaut `+10` **au plus une fois** par tuile.

Le port, lui, ne comptait effectivement **rien** : `meta.attract_mechanicals_neighbor` n'était
produit par aucun constructeur de `meta`, donc `AttractMechanicalsUtility.evaluate` rendait `0`
partout — une feuille écrite, enregistrée dans `TILE_LEAVES`, et muette.

## 2. Pourquoi la prémisse était fausse — le camp est un ARGUMENT, pas un nom de slot

`#477-r29` avait conclu « les DEUX CAMPS » à partir du **nom** du slot :
`data/symbols/<build>/metadata/interface_slots.tsv` donne `IBattleQuery` slot `0x7a` =
`GetAdjacentUnits` (arité 4), contre `0x83` = `GetAdjacentFriends` (arité 2) pour
`RadSaturationPlaybook`. Le contraste d'arité est réel ; la conclusion de camp ne l'est pas.

**La signature**, lue dans `data/symbols/<build>/frida/methods.tsv` — jamais dans les noms de
paramètres que ghidra affiche, qui ne sont pas une mesure :

```
IdunBattle.Core.Services.BattleQuery.GetAdjacentUnits
    (from, friendsOf, enemiesOf, ignoreSteppables)        <- les 3 surcharges d'arite 4
```

et le call-site, dans
`IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :

```
units = query.<slot 0x7a>(case.MovementTile, case.Unit, 0, 0);
//                        from               friendsOf  enemiesOf  ignoreSteppables
```

Le foyer terminal `IdunBattle.Core.Services.BattleQuery$$CountOrGetUnitsOnTiles` tranche :

```
u = UnitExtensions.GetUnit(tile, ctx);                     if (u == null) continue;
if (ignoreSteppables && UnitExtensions.IsSteppable(u))                    continue;
if (friendsOf != null && !UnitExtensions.IsFriend(u, friendsOf, ctx))     continue;
if (enemiesOf != null && !UnitExtensions.IsEnemy (u, enemiesOf, ctx))     continue;
add(u);
```

⇒ **`GetAdjacentUnits` nomme l'ensemble AVANT filtrage.** Avec `friendsOf` non nul, il rend les
amis — et `GetAdjacentFriends(from, unit)` n'est lui-même, une fois déroulé, qu'un
`GetUnitsOnTiles(…, friendsOf=<entité JOUEUR de unit>, enemiesOf=null, …)`. Les deux feuilles
interrogent donc **le même ensemble**. C'est exactement la faute que `#477-r29` reprochait à
`case-26` — déduire le camp d'un nom — commise un cran plus bas.

## 3. Le corps, relu ligne à ligne

```
x = Fix64(0);
if (case.Unit == null)                          yield break;              // AUCUN yield
if (!UnitExtensions.HasTrait(case.Unit, 5))     yield return x;           // 5 = Mechanical
units = query.<slot 0x7a = GetAdjacentUnits, arite 4>(case.MovementTile, case.Unit, 0, 0);
if (Enumerable.Any(units, <>c__DisplayClass1_0.<EvaluateMovementInSteps>b__0))
    x += GetUtilityValue("Marshal_AttractMechanicals");
yield return x;
```

prédicat —
`…AttractMechanicalsUtility.u003Cu003Ec__DisplayClass1_0$$u003CEvaluateMovementInStepsu003Eb__0` :

```
return UnitExtensions.HasActiveAbility(f, 0x45e) && f != case.Unit;
```

`0x45e` = 1118 = `ActiveAbilityType.DoctrinaImperatives`. Littéral BC **RÉSOLU**
(`probe_212_bc_key_literals.py --symbol …`) : `+0x33d6cf0` → `'Marshal_AttractMechanicals'`,
`[BC Default.DoctrinaImperatives_AttractMechanicals = 10]`.

`IterateAdjacentTiles(from, onlyEmptyOrSteppable=false, onlyWalkableTiles=true,
allowTemporary=true)` : liste de voisinage STOCKÉE + porte d'élévation `|delta| < 2` — c'est
`battle_query.is_adjacent`, pas `hexgeo.distance == 1`.

### Ce qui la sépare de `RadSaturationPlaybook`, qui lit le MÊME prédicat

| axe | `RadSaturationPlaybook` (1202) | `AttractMechanicalsUtility` |
|---|---|---|
| gate | aucun | `HasTrait(case.Unit, Mechanical)` |
| self | **INCLUS** (aucun `RemoveAll`) | **EXCLU** (`f != case.Unit`) |
| agrégation | `Count` → `+10 × n` | `Any` → `+10` **une seule fois** |
| clé BC | `RadSaturation_AdjacentMarshals` | `Marshal_AttractMechanicals` |
| camp | les AMIS | **les AMIS** |

Le self est mirroré par la STRUCTURE, pas par une coïncidence : `friend_units` est déjà self-exclu,
et c'est ce qui reproduit l'ensemble FILTRÉ — là où `rad_saturation.py`, dont le corps natif
n'exclut pas, doit rajouter `self_pos` à la main.

## 4. La confrontabilité — le gate est un TRAIT, donc aucune greffe

Contrairement à `RadSaturation` (seul porteur : un SUMMON), cette feuille ne se gate sur aucune
ability. **13 héros du pool sont `Mechanical`** (`adeptMorvenn`, `admecDestroyer`, `admecDominus`,
`admecManipulus`, `admecMarshall`, `admecRuststalker`, `necroDestroyer`, `necroOverlord`,
`necroSpyder`, `necroWarden`, `orksKillaKan`, `orksWarboss`, `tauCrisis`). Le carrier retenu,
`admecDominus`, l'est pour ses traits minimaux (`Hero, Mechanical, Mechanic`) et parce que son
passif `MasterAnnihilator` n'a **aucun** `*Playbook$$.ctor` dans le binaire — donc aucun terme de
tuile concurrent non porté.

## 5. LE CONFOND, payé par une mesure ROUGE — et le résidu qu'il ouvre

Première mesure (`MC1_67`/777) : `X_nat = 30` là où le port met `10`, sur les 3 tuiles du bras
allié — et `0` partout ailleurs, y compris sur le bras ennemi. Le camp était donc déjà tranché,
mais l'accord était faux de `+20`, **exactement sur les tuiles du terme mesuré**.

La ventilation par feuille (ajoutée au probe pour cette raison : un désaccord ne se rend jamais
comme un scalaire) a montré le voisin `admecMarshall` portant `triggered = [1200, 1457, 1201]`
alors que son kit gameconfig n'a que `ControlEdict`. **`1457` = `TriggeredAbilityType.KardiocoreGalvanus`,
la relique équipée AU SEED** (`BC.Units[].TertiaryAbility = 1457`, niveau 1 — cas 1 de la
ventilation des reliques). Son décompilé,
`IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext` :

```
if (case.Unit == null)                          yield return Fix64(0);
if (!UnitExtensions.IsMechanical(case.Unit))    yield break;          // LE MEME GATE
if (query.<slot 0x60>(owner, case.MovementTile))
    yield return GetUtilityValue("KardiocoreGalvanus_AdjacentFriendly");   // BC = 20
```

**Même gate, même camp, mêmes tuiles.** Inséparable du terme mesuré. Le montage déséquipe donc la
relique (`catalog_inject.unequip_relic`, écrit ici — pendant exact d'`equip_relic`) : `X_nat` tombe
de 30 à 10 sur les mêmes 3 tuiles, ce qui **confirme la RE du confond par la mesure**, au poids
exact.

⚠ **Le confond DORMAIT sous `probe_477r29`** : son carrier (`orksNob`) n'est pas Mechanical, donc le
gate coupait. Un montage vert ne dit rien du montage voisin. Corollaire utile : le choix « greffon
NON Mechanical » de `#477-r29` est devenu le **contrôle du gate** de cette feuille-ci — mesuré, en
retirant le gate `Mechanical`, `probe_477r29` passe au rouge (−10 par tuile).

> **Résidu #477-r33 — FERMÉ par #477-r33.** `1457 KardiocoreGalvanus` est portée, inscrite au
> registre et confrontée live sur cette géométrie même (montage `kardio`, la relique n'y est plus
> retirée : le confond y est devenu le mesurande). Deux autres l'ont été avec elle
> (`1461 BookOfFate`, `1495 NornCrown`) ; il reste **8** faces MOVE non portées, résidu **#477-r35**.
>
> ⚠ **Le compte annoncé ici — « 13 des 25 » — était FAUX de trois façons**, re-mesuré par
> `probe_477r33_non_owner_registry_gaps.py --offline-only` : `25` est un compte par NOM (le filtre
> correct est le PARENT : **28** concrets, **24 MOVE / 3 ATTACK / 1 REPAIR**) ; la liste des « 13 »
> comptait trois faces **ATTACK** (`1453`, `1500`, `1523`), oubliait deux concrets sans suffixe
> (`1496 CabalOfSorcerers`, `1451 WisdomOfTheAncients`) et incluait `1522 RedemptionOfTheRisen`,
> déjà écrite et volontairement hors registre.
>
> ⚠ Et **`orksRuntherd` ne porte PAS `MastersOfManoeuvre`** : sa relique du seed est
> `1475 SupaCyborkBody`, qui n'a **aucun** playbook non-owner — donc **zéro** confond. Sur les
> quatre reliques que le seed équipe sans qu'on l'ait demandé, **une seule** armait un terme non
> porté : `KardiocoreGalvanus`, sur `admecMarshall` **et** `admecRuststalker`. Détail :
> `docs/rl/case-477r33-non-owner-manquants.md`.

## 6. L'A/B — DEUX montages, parce qu'un seul ne sépare pas tout

* **`camp`** — géométrie de `probe_477r29` (cible neutre au centre, un Marshal ALLIÉ et un Marshal
  ENNEMI à distance 2 en miroir, zone strictement plate). Les deux bras vivent dans la MÊME
  décision, sur le MÊME sweep : seul le CAMP change. Il porte **en plus un ami NEUTRE**
  (`orksNob`, sans `DoctrinaImperatives`) placé près des tuiles témoins — sans lui, « amis porteurs
  du prédicat » et « amis » coïncident, et le mutant `SANS-PREDICAT` ne mord pas (mesuré : 0 → 3).
* **`agreg`** — DEUX Marshals ALLIÉS, une tuile candidate adjacente aux DEUX. Seul montage qui
  sépare `Any` (+10) de `Count` (+20). Le second porteur est obtenu par
  `graft_active_ability(replace=False)`, faute d'un second porteur de `DoctrinaImperatives` au
  gameconfig.

Les géométries sont **CHERCHÉES**, pas devinées (triplet à élévation CONSTANTE tel que les voisines
de la cible se ventilent en groupes miroir) ; celle de `C4_09` est retrouvée à l'identique par ce
chercheur et par `probe_477r29`.

> ⚠ **Ce qui commande la géométrie, ce sont les HOOKS** : `scorerTileTermTrace` ne voit que le tier
> COMPARABLE (les tuiles d'ATTAQUE). Un montage dont les deux bras ne sont pas OBSERVÉS À ÉGALITÉ
> ne sépare rien — mesure payée par `#477-r29` (6 tuiles hookées, toutes du même bras).

`X = Tile(7) − Elevation − TileEffects`, hooks EXISTANTS de `scorer-damage-trace` armés pour UN
dry-run et désarmés en `finally` ; aucune réinjection.

`camp` / `MC1_67` / 777 :

| tuile | nA | nE | `X_nat` | `X_port` |
|---|--:|--:|--:|--:|
| (2,6) | 1 | 0 | **10** | 10 |
| (3,7) | 1 | 0 | **10** | 10 |
| (3,8) | 1 | 0 | **10** | 10 |
| (5,7) | 0 | 1 | **0** | 0 |
| (5,8) | 0 | 1 | **0** | 0 |
| (6,6) | 0 | 1 | **0** | 0 |
| (3,6) (4,5) (4,6) (5,6) (6,5) | 0 | 0 | 0 | 0 |

(3,7)/(5,7) et (3,8)/(5,8) sont des **miroirs** — même distance à la cible, même élévation, seul le
camp du Marshal adjacent diffère. **⇒ le natif compte les AMIS.**

`agreg` / `MC1_67` / 777 — la ligne qui tranche l'agrégation :

| tuile | nA | `X_nat` | `X_port` | lecture |
|---|--:|--:|--:|---|
| (4,7) | **2** | **10** | 10 | `Any` : deux Marshals amis, un seul `+10` |
| (3,6) (3,7) | 1 | 10 | 10 | |
| 5 autres | 0 | 0 | 0 | |

## 7. Contre-épreuve — `a_mordu` rendu SÉPARÉMENT du verdict

Sept modèles confrontés à la MÊME mesure, sur les deux montages × deux couples board/seed. La liste
des mutants exigés est **dérivée du montage**, pas recopiée : `camp` ne peut pas séparer
`Any`/`Count`, `agreg` ne peut pas séparer le camp — et le probe **le dit** au lieu de le taire.

| modèle | `camp` MC1_67/777 | `camp` C4_09/31337 | `agreg` MC1_67/777 | `agreg` C4_09/31337 |
|---|--:|--:|--:|--:|
| `PORT (amis)` | 0 / 11 | 0 / 12 | 0 / 8 | 0 / 8 |
| `DEUX-CAMPS` (la lecture de #477-r29 §4) | **3** | **4** | 0 (non séparé) | 0 (non séparé) |
| `ENNEMIS` | 6 | 7 | 3 | 3 |
| `SANS-PREDICAT` | 3 | 2 | 0 (non séparé) | 0 (non séparé) |
| `COUNT (× n)` | 0 (non séparé) | 0 (non séparé) | **1** | **1** |
| `SELF-INCLUS` | 0 | 0 | 0 | 0 |
| `ABSENT (avant)` = l'état du port avant cette tranche | **3** | **3** | **3** | **3** |

`SELF-INCLUS` est **inerte PAR ALGÈBRE** (le carrier ne porte pas `DoctrinaImperatives`) : déclaré,
et **assertionné dans les deux sens** — aucune ligne n'a `self = 1`, donc le mutant ne DOIT pas
mordre. Le volet est quand même **EXERCÉ** offline (`test_le_gate_est_un_TRAIT_et_le_predicat_une_ACTIVE`,
branche `self_seul`), là où l'algèbre ne l'étouffe pas.

La ligne `ABSENT (avant)` **chiffre le bug corrigé** : 3 tuiles de 10 par montage, sur les quatre.

### La garde a été vue ROUGE sur trois VRAIES mutations du port

| mutation | ce qui tombe |
|---|---|
| compter aussi `enemy_units` | 4 tests (`…modele_AMIS` et `…mutants_attendus…` sur les deux `camp`) |
| ne plus produire `meta.attract_mechanicals_neighbor` (= l'état d'avant) | **9** tests, sur les 4 cas + l'étage offline |
| retirer le gate `HasTrait(Mechanical)` | l'étage offline **et** `probe_477r29` (−10/tuile) |

La troisième est la plus instructive : la garde live de CE cas reste verte (son carrier est
Mechanical), et c'est le montage du cas VOISIN qui l'attrape. Une garde ne couvre pas ce que son
propre montage rend indifférent.

## 8. Ce qui est livré

* `engine/utilities/tile.py` — `_attract_mechanicals_neighbor` + sa dérivation dans
  `apply_tile_attributes` (foyer unique du `meta` par tuile) ; `WEIGHT_CATEGORY`/`WEIGHT_KEY` sur la
  classe, pour que probe et garde citent ce que le code évalue ; docstrings de la feuille et
  en-tête du module corrigés ;
* `catalog_inject.unequip_relic` — le pendant d'`equip_relic`, écrit parce qu'un montage doit
  pouvoir **retirer** une relique que le seed impose ;
* `probe_477r31_attract_mechanicals_camp.py` (mesure, 2 montages, ventilation par feuille) +
  `test_477r31_attract_mechanicals_camp_live.py` (garde, 27 verts : 4 étages offline × 1 +
  6 étages live × 4 cas − les offline non paramétrés).

## 9. Ce qui n'est PAS couvert

* **Le `ignoreSteppables = false`** du call-site n'est pas exercé : aucun occupant steppable n'est
  adjacent aux tuiles candidates des deux montages. Le port ne filtre rien (fidèle au littéral),
  mais rien ne le contredirait s'il filtrait.
* **La branche `case.Unit == null`** (call-site SUMMON, `is_spawning`) : le natif n'y fait AUCUN
  yield ; le port rend 0 par absence de `unit_traits`. Même valeur, chemins différents, non
  confronté.
* **Le terme sur le VRAI porteur** (`admecSmnVanguard`, Mechanical **et** porteur de 1202) : il
  cumule `AttractMechanicals` et `RadSaturation` sur les mêmes tuiles. Les deux termes sont portés
  et confrontés SÉPARÉMENT ; leur somme sur un summon observé ne l'est pas.
* **Le résidu #477-r33** : RE faite pour `1457` dans CE cas, aucun port — **fermé par #477-r33**.

## Résidus

- ~~**#477-r33**~~ — **FERMÉ** (§ 5). `1457 KardiocoreGalvanus`, `1461 BookOfFate` et
  `1495 NornCrown` sont portées, inscrites au registre et confrontées live — `1457` sur CETTE
  géométrie même, la relique n'y étant plus retirée. Le compte annoncé au § 5 était faux de trois
  façons, et `orksRuntherd` ne porte pas `MastersOfManoeuvre` : détail et recensement re-dérivé
  dans `docs/rl/case-477r33-non-owner-manquants.md`. Il reste **8** faces MOVE non portées, aucune
  armée sans montage → résidu **#477-r35**.
