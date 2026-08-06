# #477-r29 — `RadSaturation` compte les ALLIÉS, et le port ne comptait RIEN

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp + un runner. Aucune injection.

```powershell
python scripts/python/probe_477r29_rad_saturation_camp.py --offline-only
python scripts/python/probe_477r29_rad_saturation_camp.py --board MC1_67 --seed 777
python -m pytest scripts/python/tests/engine/test_477r29_rad_saturation_camp_live.py -q
```

## 1. La réponse à la question binaire, et pourquoi elle n'était pas celle attendue

La question posée était « le terme compte-t-il les ALLIÉS ou les DEUX CAMPS ? ». Le port ne
faisait **ni l'un ni l'autre** : `TriggeredAbilityType.RadSaturation` (1202) était **absente de
`TRIGGERED_MOVE_PLAYBOOKS`**, donc `load_playbook(1202)` rendait `None` et le dispatcher
`TriggeredAbilitiesUtility(2)` le sautait. Le terme valait **0 partout** — un GAP, pas une
inversion de camp.

Ce n'est pas un oubli : `case-26` avait **conclu à l'inertie** (« `TriggeredAbilitiesUtility` est
ENREGISTRÉE-MAIS-MORTE dans ce build, NE RIEN PORTER côté décision »). Ce verdict est **réfuté**
par les mesures live de la MÊME feuille faites depuis — `case-36` (30/90 exacts vs L3), `#212`,
`#242`, `#271`, `#456-r1` — et par celle-ci : le natif applique bien le terme, mesuré à **+10**.

## 2. Ce que le décompilé dit, relu ligne à ligne

`IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

```
units = query.<slot 0x83 = GetAdjacentFriends, 2 arguments>(case.MovementTile, case.Unit@+0x10)
n     = System.Linq.Enumerable.Count(units, <>c.<>9__2_0)
w     = <délégué de lookup>("RadSaturation_AdjacentMarshals")
yield Fix64.op_Implicit((int)(w * n))
```

et le prédicat, qui **a un symbole sur ce build** (il n'en avait pas sur `gqfc5mff6c`, d'où le pari
de `case-26`) — `IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.u003Cu003Ec$$u003CCalculateMovementUtilityInStepsInternalu003Eb__2_0` :

```
return IdunBattle.Entities.UnitExtensions$$HasActiveAbility(f, 0x45e);
```

`0x45e` = 1118 = `ActiveAbilityType.DoctrinaImperatives`, l'ACTIVE d'`admecMarshall` (« Tan Gi'da »).
D'où le nom de la clé BC. **Trois faits de `case-26` meurent d'un coup**, et ils allaient tous dans
le même sens (un terme NÉGATIF sur les deux camps) :

| `case-26` disait | le build dit |
|---|---|
| slot `0x82` = `GetAdjacentUnits`, **both teams** | slot `0x83` = `GetAdjacentFriends`, **2 arguments**, ALLIÉS |
| multiplicateur `Utilities.Default.Contaminated.AffectedUnit` = **−25** | `Utilities.Default.TriggeredAbilities.RadSaturation_AdjacentMarshals` = **+10** |
| prédicat « allié non immunisé à `Contaminated` » | `HasActiveAbility(DoctrinaImperatives)` |

Le littéral BC est **résolu**, pas deviné :
`probe_212_bc_key_literals.py --symbol "...RadSaturationPlaybook...MoveNext"` → slot `+0x33b4a50`
→ `'RadSaturation_AdjacentMarshals'`, `[BC Default.TriggeredAbilities = 10]`.

**Face ATTACK** : `…u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext` rend
`Fix64.op_Implicit(0)` inconditionnellement — rien à enregistrer côté attack.

**SELF** : le corps n'écrit **aucun** `RemoveAll(u.Id == case.Unit.Id)`, contrairement au corps
partagé `AdjacentUnitPreference` — et contrairement au prédicat de la feuille voisine (§ 4), qui
écrit `f != case.Unit` explicitement. Le port mirror cette absence (`self_pos` +
`unit_active_abilities`). C'est **inerte par algèbre** sur ce build : aucune unité ne porte à la
fois 1202 et 1118 — le test l'assertionne DANS LES DEUX SENS plutôt que de le taire.

## 3. L'A/B qui sépare les deux camps

Le porteur réel est un SUMMON (`admecSmnVanguard`) — on l'observe, on ne le commande pas. Le passif
est donc **greffé** sur un héros du pool (`catalog_inject.graft_passive_ability`), ce qui est ici
une MESURE : le corps natif ne lit ni stats ni traits du caster.

**La géométrie est PILOTÉE** (`--place` / `--a-place`, #477-r5) : une **cible neutre** au centre,
un Marshal **ALLIÉ** et un Marshal **ENNEMI** à distance 2 d'elle, de part et d'autre, sur une zone
strictement plate (aucune asymétrie de la porte `|dElev| < 2`). Les deux bras vivent donc dans la
**MÊME décision**, sur le **MÊME sweep** — seul le CAMP change.

> ⚠ **Ce qui commande la géométrie, ce sont les HOOKS, pas l'intuition.** Une première disposition
> (les deux Marshals de part et d'autre du carrier) a rendu **6 tuiles hookées, toutes du bras
> ENNEMI** : `scorerTileTermTrace` ne voit que le tier COMPARABLE, c.-à-d. les tuiles d'**ATTAQUE**,
> et celles-ci étaient les voisines du Marshal adverse — donc toutes adjacentes à lui. Un bras vide
> ne réfute rien. C'est la **cible neutre au centre** qui fait des tuiles d'attaque un ensemble
> ventilable par camp.

Mesure `MC1_67` / seed 777, `X = Tile(7) − Elevation − TileEffects` aux hooks EXISTANTS de
`scorer-damage-trace` (armés pour UN dry-run, désarmés en `finally` ; aucune réinjection) :

| tuile | nA | nE | `X_nat` | `X_port` |
|---|--:|--:|--:|--:|
| (3,7) | 1 | 0 | **10** | 10 |
| (3,8) | 1 | 0 | **10** | 10 |
| (4,6) | 0 | 0 | 0 | 0 |
| (4,8) | 0 | 0 | 0 | 0 |
| (5,7) | 0 | 1 | **0** | 0 |
| (5,8) | 0 | 1 | **0** | 0 |
| (6,6) | 0 | 1 | **0** | 0 |
| (6,8) | 0 | 1 | **0** | 0 |

(3,7)/(5,7) et (3,8)/(5,8) sont des **miroirs** : même distance à la cible, même élévation, même
tout — seul le camp du Marshal adjacent diffère. **⇒ le natif compte les ALLIÉS.** `0` désaccord
`X_nat` vs `X_port` sur 8 tuiles.

**GÉNÉRALISATION — second couple board/seed, géométrie CHERCHÉE et non devinée.** `C4_09` / 31337 :
9 tuiles hookées, **10** sur les deux du bras ALLIÉ ((2,1), (3,2)), **0** sur les cinq du bras
ENNEMI, 0 sur les deux témoins, `0` désaccord sur 9. Ce board est plus dur — élévations 20/30/50 et
un effet de tuile à 9 dans le `X_nat` brut — ce qui exerce le retranchement `− Elevation −
TileEffects` au lieu de le laisser à zéro. Sur quatre boards essayés, **deux** admettent la
géométrie exigée (`C1_25` et `C1_02` n'en ont **aucune** : contrainte de terrain, pas un choix).

## 4. Le CONFOND, qui rend la question non rhétorique — et le résidu qu'il ouvre

> ⚠ **CE PARAGRAPHE A ÉTÉ FAUX SUR LE CAMP, ET DE LA MÊME FAÇON QUE `case-26` L'AVAIT ÉTÉ.**
> Il concluait « slot nommé `GetAdjacentUnits` ⇒ les DEUX CAMPS ». **`#477-r31` l'a réfuté** : la
> signature réelle est `GetAdjacentUnits(from, friendsOf, enemiesOf, ignoreSteppables)`, le
> call-site passe `friendsOf = case.Unit`, et `BattleQuery$$CountOrGetUnitsOnTiles` ne garde alors
> que les **AMIS**. Le nom du slot désigne l'ensemble AVANT filtrage : **le camp est un ARGUMENT**.
> Ce qui suit est l'état FINAL. Détail et mesure : `docs/rl/case-477r31-attract-mechanicals-camp.md`.

Le **même** prédicat `HasActiveAbility(0x45e)` est lu par une **autre** feuille du même composite,
`IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`
(`UtilityType.DoctrinaImperatives_AttractMechanicals`) — et celle-là interroge le slot **`0x7a` =
`GetAdjacentUnits`, QUATRE arguments** :

```
if (!HasTrait(case.Unit, 5 /* Mechanical */))            yield Fix64(0);
units = query.<slot 0x7a = GetAdjacentUnits>(case.MovementTile, case.Unit, false, false);
//                                            from         friendsOf  enemiesOf  ignoreSteppables
if (Enumerable.Any(units, u => HasActiveAbility(u, 0x45e) && u != case.Unit))
    x += GetUtilityValue("Marshal_AttractMechanicals");   // 10, et UNE seule fois (`Any`)
```

Les deux feuilles interrogent donc le **MÊME ensemble** — les amis adjacents à la tuile candidate ;
`GetAdjacentFriends(from, unit)` n'est lui-même qu'un `GetUnitsOnTiles(…, friendsOf=<entité JOUEUR
de unit>, enemiesOf=null, …)`. Ce qui les sépare est ailleurs, et vaut d'être lu :

| axe | `RadSaturationPlaybook` (1202) | `AttractMechanicalsUtility` |
|---|---|---|
| gate | aucun | `HasTrait(case.Unit, Mechanical)` |
| self | **INCLUS** (aucun `RemoveAll`) | **EXCLU** (`f != case.Unit`) |
| agrégation | `Count` → `+10 × n` | `Any` → `+10` au plus une fois |
| camp | les AMIS | **les AMIS aussi** |

**Ce qui reste vrai de ce paragraphe** : la spécification de `case-26` ne décrit **aucune** des deux
feuilles telle quelle — elle a mélangé le prédicat de l'une, un slot mal attribué et un poids d'une
troisième mécanique. Et le CONFOND opérationnel, lui, est réel :

* le greffon de l'A/B est choisi **NON Mechanical** (l'étape 0 du probe le REFUSE sinon) — sans quoi
  `X_nat` porterait DEUX `+10` sur les mêmes tuiles et la mesure ne trancherait rien ;
* cette feuille était **INERTE côté port** (`meta.attract_mechanicals_neighbor` produit par aucun
  des trois `*_tile_leaf_ctx`). Elle est **PORTÉE et CONFRONTÉE depuis #477-r31**, sur le substrat
  `{friend,enemy}_units[].active` que cette tranche-ci ajoute — aucun RPC neuf, contrairement à ce
  qu'annonçait l'en-tête de `tile.py`.

⚠ Et le montage de CE cas cachait un second confond, que seul un carrier **Mechanical** réveille :
`admecMarshall` porte au seed la relique `KardiocoreGalvanus`, dont la face NON-OWNER pose `+20` sur
ses tuiles adjacentes sous le gate `IsMechanical(case.Unit)`. Il n'a rien changé ici (`orksNob`
n'est pas Mechanical) — mais « mon montage est vert » ne dit rien du montage voisin.

## 5. Le cousin `OptimizedGait_AdjacentFriends` — ne partage PAS le défaut

`case-26` le nommait « partage slot 0x82 ». C'est un `IdunBattle.AI.Utilities.OptimizedGait_AdjacentFriendsUtility`
(`UtilityType` 60), **pas un playbook**, et il n'a qu'une face ATTACK :

```
if (!UnitExtensions.IsMechanical(case.Unit))   yield Fix64(0);
units = query.<slot 0x83 = GetAdjacentFriends, 2 arguments>(case.Unit.MainTile, case.Unit);
foreach (u in units)
    if (HasTriggeredAbility(u, 0x4b5 /* 1205 OptimizedGait */))
        x += GetUtilityValue("OptimizedGait_AdjacentFriends");
```

Il appelle donc **le même slot `0x83`** que `RadSaturation` — les ALLIÉS, conformément à son nom.
La citation `0x82` était la numérotation du build précédent ; `0x82` et `0x83` sont **tous deux**
des `GetAdjacentFriends` d'arité 2, si bien que la conclusion de camp y était juste par accident.

**Non porté, et il n'y a rien à porter aujourd'hui** : son poids
`Utilities.Default.OptimizedGait_AdjacentFriends.OptimizedGait_AdjacentFriends` vaut **0** dans la
capture ET au gameconfig VIVANT. Le porter rendrait `0` partout — un port invalidable, que la
doctrine interdit. Condition de réouverture, explicite : **que ce poids devienne non nul**
(le contrôle est celui de `#271`, où une clé à 0 dans la capture valait 10 au gameconfig).

## 6. Ce qui est livré

* `engine/playbook/rad_saturation.py` — `RadSaturationPlaybook`, famille « corps propre » (comme
  `friends_in_range.py`), enregistré dans `TRIGGERED_MOVE_PLAYBOOKS` ;
* `engine/entities/active_abilities.py` — foyer `kit_active_ability_ids` /
  `entity_active_ability_ids` (tri-état, pendant exact d'`entity_triggered_ability_ids`). Il vit
  **hors** d'`active_ability_type.py` parce que le générateur de ce mirror réécrit le fichier
  ENTIER (`regen_active_ability_tables.py` fait `MIRROR.write_text`, là où `regen_enum_mirrors.py`
  ne remplace que le bloc de membres) : une fonction posée là-bas disparaîtrait sans erreur.
  `services/ability_range._active_ability_ids` y délègue, pour ne pas forker le substrat ;
* `engine/utilities/tile.py` — clés `{friend,enemy}_units[].active` et `unit_active_abilities`,
  dans les **TROIS** producteurs de `ctx` (`tile_leaf_ctx`, `runner_tile_leaf_ctx`,
  `scene_tile_leaf_ctx`) ;
* `probe_477r29_rad_saturation_camp.py` (mesure) + `test_477r29_rad_saturation_camp_live.py`
  (garde, 9 verts).

## 7. Contre-épreuve — `a_mordu` rendu SÉPARÉMENT du verdict

Sept modèles confrontés à la MÊME mesure, sur les deux couples board/seed :

| modèle | `MC1_67`/777 | `C4_09`/31337 | a_mordu |
|---|--:|--:|---|
| `PORT (allies)` | 0 / 8 | 0 / 9 | — (c'est le verdict) |
| `DEUX-CAMPS` (la spec de `case-26`) | 4 / 8 | 5 / 9 | OUI |
| `ENNEMIS` (camp inverse) | 6 / 8 | 7 / 9 | OUI |
| `SANS-PREDICAT` | 1 / 8 | 3 / 9 | OUI |
| `POIDS -25` (le multiplicateur de `case-26`) | 2 / 8 | 2 / 9 | OUI |
| `ABSENT (avant)` = l'état du port avant cette tranche | **2 / 8** | **2 / 9** | OUI |
| `SELF-EXCLU` | 0 / 8 | 0 / 9 | NON — **inerte PAR ALGÈBRE**, assertionné dans les deux sens |

La ligne `ABSENT (avant)` **chiffre le bug corrigé** : 2 tuiles par montage, de 10 exactement.

Et la garde a été vue ROUGE sur une VRAIE mutation du port : en faisant compter les deux camps à
`calculate_movement_utility_in_steps`, `test_le_natif_suit_le_modele_ALLIES` tombe avec 4 tuiles en
désaccord ; en retirant 1202 du registre, six gardes tombent (dont celle qui NOMME l'absence).

## Résidus

- ~~**#477-r31**~~ — **FERMÉ** (`docs/rl/case-477r31-attract-mechanicals-camp.md`).
  `AttractMechanicalsUtility` est portée et confrontée live. Le résidu était écrit « une unité **de
  n'importe quel camp** » : c'est cette phrase-là qui était fausse, pas l'inertie qu'elle signalait.
- **Le poids du cousin `OptimizedGait_AdjacentFriends` est nul** (capture ET gameconfig vivant).
  Pas de résidu ouvert : porter un terme identiquement nul serait spéculatif. La condition de
  réouverture est écrite au § 5.
