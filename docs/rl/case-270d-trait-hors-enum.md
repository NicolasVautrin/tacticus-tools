# case-270-d — un NOM DE TRAIT hors enum rend le BC entier indeserialisable

`astarLysander` ne se deployait pas (`[error] initAndStart: system error`), et avec lui
`1231 TitanhammerSquad` etait declaree « confrontable par aucun montage ». Ni le roster, ni
l'injection, ni la seed (bissection #270, 2026-07-30 : les trois autres porteurs montent SEULS,
celui-ci echoue SEUL).

## 1. La cause, nommee

`IdunBattle.Configuration.UnitConfiguration.Traits` est **type**
`List<IdunBattle.Entities.Enum.UnitTrait>`. Deux maillons l'etablissent :

| Maillon | Ce qu'il montre |
|---|---|
| `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` | recopie `UnitProperties+0x18` dans `UnitConfiguration+0xd0` (et y pose une `List` neuve du meme type si la source est nulle) |
| `IdunMetaLogic.UserProgress.Model.UnitPropertiesExtensions$$GetPlayerFacingTraits` | lit ce **meme** `UnitProperties+0x18` (le display-class recopie `param_1+0x18` en `+0x28`, passe a `idun.shared.extensions.ListExtensions$$FilterNewList`) et sa signature rend `System.Collections.Generic.List<IdunBattle.Entities.Enum.UnitTrait>` |

Un nom hors enum n'est donc pas « un trait que le natif ignorerait » : il est **inexprimable** dans
ce champ. Chemin de la levee, a la relecture du BC :

```
initAndStart  step=deserialize BC          (frida/hooks/features/launch.ts)
  -> Newtonsoft.Json.Converters.StringEnumConverter$$ReadJson      (token String)
  -> Newtonsoft.Json.Utilities.EnumUtils$$ParseEnum
  -> $$MatchName / $$FindIndexByName rendent un Nullable VIDE
  -> Newtonsoft.Json.Utilities.StringUtils$$FormatWith + System.ArgumentException -> THROW
```

Exception managee sous `invokeMethod` => Frida rend « system error ». La faute emporte **tout le
BC**, pas seulement le porteur — d'ou la signature de la bissection.

## 2. Ce qui l'a declenchee : le gameconfig est LIVRE EN AVANCE sur le binaire

`astarLysander` porte `Subfaction: ImperialFists`. Sur `rnca9r7q6c`, `UnitTrait` (105 membres)
s'arrete a **quatre** sous-factions : `DeathKorpsKrieg` 9000, `FarsightEnclaves` 9001,
`SistersSilence` 9002, `BloodRavens` 9003. `catalog_inject._traits` place la sous-faction dans
`Traits` — mirror mesure sur les 175 entrees capturees (`custoAtlacoya` -> `['Imperial',
'SistersSilence', 'Hero', ...]`).

Les quatre porteurs de #270 ont tous un `releaseStatus` **futur** ; seul le plus lointain apporte
une sous-faction que le binaire ne connait pas encore :

| Porteur | Sortie | Subfaction | Deploiement |
|---|---|---|---|
| `eldarLhykhis` | 2026-08-06 | — | OK |
| `thousSekhetar` | 2026-08-06 | — | OK |
| **`astarLysander`** | **2026-08-26** | **`ImperialFists`** | **system error** |
| `votanChampion` | 2026-09-06 | — | OK |

## 3. Combien d'autres unites portent la meme signature — **une seule**

Balayage des **669** unites du gameconfig (`lineup` + `npc` + `summons`) : `astarLysander` est la
**seule** dont la synthese sortirait du vocabulaire de `UnitTrait`. Sur les 175 entrees capturees du
seed BC : **0** trait hors enum. Le cas est donc ISOLE aujourd'hui — mais le gisement n'est pas
epuise, il est **alimente par le jeu** : chaque livraison de contenu en avance peut en apporter un
autre, et le symptome (« initAndStart: system error ») ne nomme jamais le coupable. D'ou une garde,
pas un constat.

Note : la signature n'est pas « un passif a `constants: null` » (§4) mais **« un nom de gameconfig
hors de l'enum natif correspondant »**. Les enums voisins sont deja couverts autrement :
`active_ability_id` / `triggered_ability_id` **levent** sur un nom inconnu, `ability_variable_id`
aussi. `Traits` etait le seul champ enum recopie VERBATIM sans confrontation.

## 4. La piste #254 est REFUTEE

La piste soumise etait : « `IconOfObstinacy` a `constants: null` au gameconfig, et le motif #254 est
un `GetStringConstant` leve a la construction du trigger d'un passif, au deploiement ». Le
`constants` absent est reel ; la levee, non. Aucune classe du kit ne lit de constante a la
construction :

| Fonction native | Ce qu'elle utilise |
|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger` | `DSLTriggers$$On(0x28)`, `DSLSelectors$$AdjacentFriends`, `DSLSelectors$$UnitsWithTrait(0x40f)`, `DSLTriggers$$Contains`, `DSLFormulas$$TimesAttackMadeThisTurn`, `DSLTriggers$$AmountIsZero` |
| `...IconOfObstinacy_AddArmourBuffAbility$$CreateBehaviour` | `DSLFormulas$$TurnsFromRounds(1)`, `DSLBehaviors$$AddDynamicStatModifierEffect(0x628)` |
| `...IconOfObstinacy_AddDamageBuffAbility$$CreateBehaviour` | `DSLBehaviors$$AddEffect(0x627)` |
| `...AIconOfObstinacyAbility$$GetAffectedUnits` | `DSLSelectors$$AdjacentFriends` + `UnitsWithTrait(0x40f)` |

**Zero** appel a `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` /
`$$GetNumberConstant`. La seule lecture de constante du kit est
`IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$GetCurrentlyAffectedFriends`
-> `GetNumberConstant(0x16)` = `AbilityConstantType.range`, et le gameconfig la **porte**
(`TitanhammerSquad.constants.range = "2"`). Les deux constantes declarees (`range`,
`initialCooldownTurns`) et les cinq variables du kit (`hpToHeal`, `blockDmg`, `extraDmg`,
`extraArmor`, `chance`) sont toutes des membres valides de `AbilityConstantType` /
`AbilityVariableType`.

## 4bis. Ce que le filtre COUTE : rien, et c'est mesure

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor` construit un
`OrderedSet<UnitTrait>` qu'il stocke a `statics+0x18` et qui contient **exactement quatre** valeurs,
ecrites en dur : `9000`, `0x2329`, `0x232a`, `0x232b` — soit les quatre sous-factions de l'enum, ni
plus ni moins. L'ensemble des traits de sous-faction que ce binaire sait manipuler est donc **ferme
et code en dur** ; il n'y a aucune case pour `ImperialFists`, ni dans l'enum, ni dans cette table de
regles. Retirer ce nom ne prive le natif d'aucune branche : il n'en a aucune a offrir.

Le jour ou le binaire rattrapera le gameconfig, `dropped_traits` deviendra vide de lui-meme, le
filtre cessera de mordre, et le probe A/B le dira explicitement (`why` = « plus rien a contraster »)
au lieu de rendre un vert par vacuite.

## 5. Le correctif

`catalog_inject._traits` ne produit plus que des membres de `UnitTrait` **du build courant**, et ce
qui est ecarte se lit (`dropped_traits`, report `--show`) — jamais en silence. Ce n'est pas une
rustine : le champ etant type, une valeur hors enum n'a aucun sens observable — **aucun code natif
de ce build ne peut tester un membre que son propre enum ne contient pas**. Et le filtre ne touche
pas la cohorte reelle : sur les 175 entrees capturees, `_traits_raw` produit 0 nom hors enum, donc
`catalog_inject --validate` est inchange.

## 5bis. La mesure LIVE (2026-07-31, session 1 puis 2, apres amorce)

`probe_270d_lysander_deploy.py` — deux builds, meme roster, meme board, meme seed, meme seed BC ;
seule difference : `ImperialFists` present ou non dans `BC.Units[astarLysander].Traits`.

```
Traits produits  : ['Imperial','Hero','TeleportStrike','TerminatorArmour','Resilient','CrushingStrike']
Traits ECARTES   : ['ImperialFists']
A  trait REMIS     : build KO   verbatim : [error] initAndStart: system error
B  tel que produit : build OK   abilities du porteur : [69, 1231]   toActivate : [85]
```

Rejoue sur un SECOND couple (seed 31337, board `C1_74`) : meme resultat.

**Contre-epreuve croisee** (`--cross votanChampion`) — le meme nom pose sur une unite qui monte
DEJA :

```
CROSS votanChampion   intact: build OK | + ImperialFists : build KO
                      verbatim : [error] initAndStart: system error
```

C'est cette moitie qui ATTRIBUE : la faute est le **trait**, pas le porteur.

**`1231 TitanhammerSquad` est confrontable, pas seulement « deploye »** : le porteur (id 85, pos
(1,0), 11044 PV) est **la seule unite de `toActivate`**, `abilityTargets(1231)` repond `ok`, et
l'ability arrive avec `cooldown = 1` — ce qui corrobore au passage la lecture de
`AbilityConstantType.initialCooldownTurns` (`TitanhammerSquad.constants.initialCooldownTurns = "1"`).

Le probe #270 d'origine, rejoue avec les **quatre** porteurs injectes ensemble, passe desormais sur
les quatre lignes (`1222`, `1227`, `1231`, `1232` : natif=True / port=True / sans-l-entree=False) —
c'est la couverture qui lui manquait.

## 6. Ce qui est garde

| Fichier | Nature | Session |
|---|---|---|
| `scripts/python/tests/engine/test_270d_catalog_traits_enum.py` | vocabulaire sur les 669 unites + partition `_traits` / `dropped_traits` + non-regression des 175 capturees (3 tests) | non |
| `scripts/python/tests/engine/runner/test_270d_lysander_deploy_live.py` | le trait remis casse le build ; le porteur se deploie, expose `1231`, entre dans `toActivate` ; la faute est attribuee au TRAIT (contre-epreuve croisee) ; le kit de combat survit au filtre (5 tests) | oui |
| `scripts/python/probe_270d_lysander_deploy.py` | le montage A/B a UN SEUL BIT d'ecart + `--cross` (fixtures `lysander_deploy_case`, `trait_hors_enum_cross_case`) | oui |

Rouge de la garde offline **avant** le correctif, verbatim :

```
AssertionError: ces entrees porteraient un nom hors IdunBattle.Entities.Enum.UnitTrait ->
le BC ENTIER devient indeserialisable (initAndStart: system error) :
{'astarLysander': ['ImperialFists']}
```

## 7. Ce qui n'est PAS couvert

- **Le port de `1231 TitanhammerSquad` n'est pas fait** : ce cas rend le porteur confrontable, il
  n'ecrit aucune mecanique. L'ability reste hors `ABILITY_CLASSES`.
- **Le champ `Subfaction`** de `UnitConfiguration` garde `"ImperialFists"` : c'est une
  `System.String` (signatures `idun.shared.utils.IdunLocalization.Units$$SubfactionName(subfaction:
  System.String)`, `...$$SubfactionNameTerm(subfactionId: System.String)`), pas un enum — elle ne
  peut donc pas lever. Non modifie.
- **Les autres blocs du seed BC** (`Utilities`, `Effect`, `Board`) n'ont pas ete balayes pour la
  meme classe de faute : seul `Units[].Traits` l'a ete.
