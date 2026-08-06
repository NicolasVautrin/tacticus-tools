# #477-r25 — les slots des AUTRES interfaces : un NOM ne désigne pas UN slot, mais un ENSEMBLE

**LIVRÉ.** Build `rnca9r7q6c`, metadata IL2CPP + ghidra-mcp. Aucun runner, aucune injection.

```powershell
python scripts/python/probe_477r25_slots_autres_interfaces.py [--recenser|--mutants|--regenerer]
python -m pytest scripts/python/tests/engine/test_477r25_slots_autres_interfaces_offline.py -q
```

## 1. Le cas nommé, tranché — et par où il fallait le prendre

`case-27` place `GetAdjacentEnemies` au slot `0x7f`, `case-250` au `0x7c`. Dix mois de
recoupements n'avaient pas départagé, et pour une raison qu'aucun des deux camps ne pouvait
voir : **le nom ne désigne pas un slot, il en désigne quatre.**

| nom | slots (metadata `rnca9r7q6c`) | arité |
|---|---|---:|
| `GetAdjacentUnits` | `0x7a`, `0x7b`, **`0x7c`** | 4 |
| `GetAdjacentEnemies` | `0x7d`, `0x7e`, **`0x7f`**, `0x80` | 3 |
| `GetAdjacentFriends` | `0x81`, `0x82`, `0x83`, `0x84` | 2 |
| `GetAdjacentTiles` | `0x4f`, `0x51` | 4 |
| `GetFreeAdjacentTiles` | `0x52`, `0x53` | 1 |

⇒ **`case-27` est JUSTE** (`0x7f` est bien un `GetAdjacentEnemies`) ; **`case-250` est FAUX**
(`0x7c` est un `GetAdjacentUnits` — *amis compris*, et 4 arguments au lieu de 3).

**L'hypothèse laissée ouverte par `#477-r24-r1` — « un décalage global de −1 rendrait `case-250`
juste en cassant `case-433` » — est RÉFUTÉE, pas arbitrée.** Trois lectures indépendantes du
**décompilé du build courant** écrivent le slot LITTÉRALEMENT, et toutes trois concordent avec la
table :

* `IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$GetDynamicInvalidTargetReason`
  — le call-site même de `case-250` — appelle `0x7d` avec **3** arguments (`caster, ownerId, 0`)
  puis `0x81` avec **2** (`caster, ownerId`). La fiche écrivait `0x7c` et `0x80` ;
* `…RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass152_0$$u003CGetAdjacentEnemiesu003Eb__0`
  → `0x7d` ; `…DisplayClass155_0$$…` → `0x80` ; `…DisplayClass102_0$$u003CGetFreeAdjacentTilesu003Eb__0`
  → `0x52` ;
* `case-27` lui-même, qui a résolu ses slots **au runtime** sur ce build (`interfaceOffset` = 4) :
  slot d'interface `2` = `IsMeleeAttack`, `0x4f` = `GetAdjacentTiles`, indices de vtable
  `0x81..0x84` = les quatre `GetAdjacentEnemies`. **3/3 concordants.**

## 2. Pourquoi le désaccord n'était pas arbitrable — et pourquoi il l'est devenu

Ce n'est **pas** que l'un des deux lisait mal. `case-250` et `case-243` ont lu le **build
précédent** (`gqfc5mff6c`), où `IBattleQuery` avait une méthode de moins : le glissement se lit
jusque dans les **noms de classes générées** — les lambdas du décorateur enregistreur y étaient
`DisplayClass151_0..154_0` / `101_0`, elles sont aujourd'hui `152_0..155_0` / `102_0`.

Le décalage n'est **pas uniforme**, et c'est ce qui interdisait de le corriger « au jugé » :
`IsMeleeAttack` (slot 2) n'a pas bougé, `ConvertRoundsToTurns` a pris `+1`, `IsInTeamAuraRange`
`+2`, et `IsTargetInAttackRangeForSummon` a **reculé de 8** (`0xcc` → `0xc4`). Un décalage
constant appliqué à l'aveugle aurait fabriqué de nouvelles fautes.

⇒ **La leçon de `#477-r24-r1` se prolonge d'un cran** : là-bas, deux mesures justes accusaient la
GRANDEUR qui les reliait. Ici, deux mesures dont l'une est périmée accusent le **BUILD** qui les
sépare — et aucune relecture du décompilé *courant* ne pouvait innocenter la plus ancienne.

## 3. Ce qui le dérive : la grille `Il2CppTypeDefinition`, pas des ancres de nom

`#477-r24-r1` localisait la table d'une interface par des **ancres de NOM** (intersection des
débuts de table compatibles). Ça marche quand on connaît des noms caractéristiques, et ça
**REFUSE** dès qu'une ancre appartient à une autre interface implémentée par la même classe —
mesuré : `IDamagePrediction` rend `INCOHERENT`, ses ancres ne partagent aucun début.

`il2cpp_metadata.locate_types` désigne la table par le **TYPE** : on trouve l'entrée
`Il2CppTypeDefinition` par la **paire adjacente (`nameIndex`, `namespaceIndex`)** — deux index
relatifs au `string_offset` déjà dérivé — puis on lit `methodStart` et `method_count`. Aucun champ
de header n'est lu (ce build annonce `version = 39`, hors de toute version publique) :

1. **`step`** = PGCD des écarts entre entrées de type (mesuré : **82** octets — non multiple de 4,
   donc aucune taille publiée ne convenait) ;
2. **crible de cardinalité** : le compte lu doit valoir *au moins* ce que Frida attribue au type.
   L'inégalité a un sens précis — `methods.tsv` est indexée par ADRESSE, donc elle **perd** des
   surcharges ; le metadata en a toujours autant ou plus, jamais moins ;
3. **contrôle par les NOMS**, le seul qui tranche : le bloc lu pour chaque ancre doit **contenir**
   tous les noms que Frida lui attribue. Les couples (fieldStart, field_count) et consorts
   satisfont les étapes 1-2 ; seul celui des méthodes passe l'étape 3.

Résultat mesuré : `step = 82`, `methodStart` à `+30`, `method_count` à `+58`, contrôlés sur
**6 classes ancres**.

### Trois voies essayées et écartées, chacune pour une raison mesurée

* **l'ORDRE du dump Frida** — `methods.tsv` est triée par ADRESSE ; l'ordre d'émission ne suit
  l'ordre de déclaration que par accident (**87** méthodes concordantes pour
  `Core.Services.OperationProcessor`, **1** pour `IdunBattle.Core.Services.BattleQuery`). Un
  critère de préfixe ordonné échoue sur 5 classes sur 6 ;
* **la relation `debut(t) + compte(t) == debut(t+1)`** — élégante et **fausse ici** : sur 599
  paires consécutives, **67** la violent, la table des types n'étant pas strictement ordonnée par
  `methodStart` (trois voisines lues à 60723, 60726, 60724). S'en servir aurait demandé un seuil
  arbitraire ;
* **`ctor` ≡ `.ctor`** — le metadata écrit `.ctor`, le nom court dérivé du dump vaut `ctor` : sans
  normalisation, **une seule** ancre suffisait à faire échouer une localisation JUSTE (mesure :
  14 couples candidats, **0** retenu).

### Le contrôle croisé qui rend le tout sûr

Les deux mécanismes ne partagent que le fichier de metadata. Sur
`Core.Services.IOperationProcessor`, ils rendent **exactement la même table** — 150 slots,
`Init` / `SetupGame` / `ActiveAbility`… — alors que chacun se vérifie contre sa **propre** entrée
versionnée. C'est l'étage 5 du cliquet (`test_etage5_les_deux_derivations_rendent_la_MEME_table`).

Et sur `IBattleQuery`, un contrôle **massif et indépendant du metadata** : les **168** lambdas du
décorateur enregistreur ont été décompilées et leur slot extrait — **137 noms, 168 slots,
0 divergence**, soit **168 des 219 slots** attestés par le décompilé (77 %).

## 4. Le recensement — c'est lui qui borne la tranche

Le périmètre n'est pas une liste écrite d'avance : on balaie, on apparie le RÉCEPTEUR écrit au
site, et ce qui n'est pas apparié est compté (`--recenser`). **18 interfaces** déclarées,
**7 effectivement citées** avec un couple (slot, nom) :

| interface | attestations | slots |
|---|---:|---:|
| `IBattleQuery` | 112 | 219 |
| `IActiveAbility` | 15 | 30 |
| `IAttackQuery` | 15 | 22 |
| `IDamageCalculations` | 8 | 19 |
| `IMovementQuery` | 4 | 19 |
| `IDamagePredictionQuery` | 2 | 19 |
| `IAmountFormula` | 2 | 5 |

Les onze autres (`IMatchState`, `IEffect`, `IPlaybook`, `IPseudoRNG`, `IStreamDispatcher`,
`IPathfinders`, `ITargetsSelector`, `ITargetingQuery`, `IDamagePrediction`, `IUtilitiesDatabase`,
`IEffectsDatabase`) sont **dérivées et versionnées**, mais **jamais citées avec un nom** : rien à
contredire aujourd'hui, tout à garder demain.

## 5. Le compte — 61 corrections, et ce qui les a rendues sûres

**157 attestations** confrontées, **0 fausse** après correction. Avant : **46** couples faux sur
**24 groupes**, plus **2 arités** contredites. Trajectoire mesurée du probe : `59 → 52 → 46 → 0`.

Les groupes les plus peuplés : `GetFreeAdjacentTiles` `0x51`→`0x52` (**7** sites), `CanBeRepaired`
`0x2e`→`0x2f` (**5**), `GetAdjacentEnemies` `0x7c`→`0x7d` (**3**), `ReachedSummonCap`
`0xc9`→`0xca` (**3**), `GetAdjacentTiles` `0x4e`→`0x4f` (**3**).

**Trois corrections ne sont pas des renumérotations mais des ERREURS DE NOM**, et deux ont une
portée qui dépasse la citation :

* `case-26-radsaturation-playbook.md` écrivait « slot `0x82` = `GetAdjacentUnits` (ring-1, **both
  teams**) ». Le décompilé de
  `IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`
  appelle le slot **`0x83`**, qui est **`GetAdjacentFriends`** — donc les **ALLIÉS** du caster, pas
  les deux camps. La fiche le disait à moitié elle-même : son cousin y est nommé
  `OptimizedGait_AdjacentFriends`. **⚠ Ce n'est plus une faute de citation mais une faute de
  SPÉCIFICATION** : un port qui compterait les deux camps serait faux. Résidu **#477-r29**
  (renuméroté de `#477-r27` au merge — collision), **CLOS** : le port ne comptait en fait
  **rien** (1202 absente de `TRIGGERED_MOVE_PLAYBOOKS`), et l'A/B live tranche — `X_nat` = 10 sur
  les tuiles adjacentes à un Marshal ALLIÉ, **0** sur celles adjacentes à un Marshal ENNEMI. Deux
  autres faits de `case-26` sont morts avec : le multiplicateur (`+10`, pas `−25`) et le prédicat
  (`HasActiveAbility(DoctrinaImperatives)`, pas l'immunité à `Contaminated`).
  cf. `docs/rl/case-477r29-radsaturation-camp.md` ;
* trois fiches attribuaient le slot `0x95` d'`IBattleQuery` à `BattleQuery$$GetInRangeAuraAmount`.
  Ce nom n'est dans **aucune** interface : `GetInRangeAuraAmount` est la méthode **interne**
  (4 paramètres, dont `returnFirst`) ; le slot `0x95` est `GetTeamActiveAuraAmount`, qui l'appelle
  avec `returnFirst = false` (lu dans `IdunBattle.Core.Services.BattleQuery$$GetTeamActiveAuraAmount`) ;
* `case-287-sorcerous-facade-combat.md` nommait le slot `0x40`
  `CanAttackAnyUnitFromAnyTileWithAnyAbility` (qui est au `0x38`). C'est `HasValidTargets`, et
  l'arité le confirme : le site passe **3** arguments, `HasValidTargets` en prend 3.

**Quatre citations ACCUSÉES À TORT par le probe, et innocentées avant toute correction** — chacune
a valu un cran, listé au § 6.

## 6. Les gardes, et les six crans qui les rendent lisibles

`probe_477r25_slots_autres_interfaces.py` (mesure) + `test_477r25_slots_autres_interfaces_offline.py`
(cliquet, **49 verts**), cinq étages : RECENSEMENT / DÉRIVATION / CLIQUET sur l'entrée versionnée
`data/symbols/<build>/metadata/interface_slots.tsv` / CITATIONS / ARITÉ.

**La garde a été vue ROUGE, sur une VRAIE faute** — le cas nommé lui-même, remis à sa valeur
d'origine :

```
      1 citation(s) au SLOT/NOM faux
        docs/rl/case-250-tau-targeting.md:313 [IBattleQuery] slot 0x7c : le site nomme
        GetAdjacentEnemies, le metadata dit GetAdjacentUnits ; GetAdjacentEnemies est aux
        slots 0x7d, 0x7e, 0x7f, 0x80 | adjEnemies = battleQuery.<slot 0x7c>
        GetAdjacentEnemies(caster, owner, /*ignoreSteppables*/ false);
VERDICT : ROUGE
```

**Contre-épreuve : 4 mutants, 4 mordent** — `slot-decale` (cliquet 0→190, nom 0→91),
`nom-permute` (0→2 / 0→9), `table-tronquee` (0→110 / 0→38), `arite-fausse` (0→513 / arité 0→37).
`a_mordu` est rendu **séparément** du verdict.

### Les crans, chacun né d'un faux positif MESURÉ

1. **une 4ᵉ forme de couple** — `battleQuery.<slot 0x7c> GetAdjacentEnemies(...)` <!-- [slot-attribution:refute] -->. Les trois formes
   héritées de `#477-r24-r1` attendent un signe égal ou un qualificateur collé au nom : **le cas
   nommé leur était invisible**. Une garde aveugle à ce qu'elle arbitre ne prouve rien ;
2. **en régime MULTI-interface, seules les formes A et D** (attribution portée par un
   qualificateur ou un récepteur collé). « `BattleQuery$$GetNormalAttackPrediction` invoque
   `IDamagePrediction` slot 9 » attribuait sinon le slot de l'une à la méthode de l'autre — 2 faux ;
3. **les RENVOIS** (`que`, `interroge`, `invoque`, `appelle`, `utilise`, `évalue`, `->`, `→`)
   retournent la relation : « le slot `0xe` QUE `BattleQuery$$IsTileInRangeOfAnyAbility` interroge » <!-- [slot-attribution:refute] -->
   désigne le slot APPELÉ — **8 des 49** désaccords étaient de cette forme, tous FAUX ;
4. **la PONCTUATION FORTE** (`:`, `;`) ouvre une proposition : « …`GetAllTilesInAbilityRange`
   surcharge 4 arguments : slot `0x14`, slot `0x13` » énumère les GATES, qui sont des slots
   d'`IActiveAbility` — 2 sites JUSTES ;
5. **la VIRGULE** : le dépôt écrit ses chaînes de gates en ÉNUMÉRATION, et « nom PUIS slot »
   appariait le nom d'un élément au slot du SUIVANT — 2 sites JUSTES ;
6. **`AActiveAbility` est un récepteur d'`IActiveAbility`.** L'omettre ne rendait pas le probe
   muet : il RATTACHAIT ces slots à l'interface voisine citée sur la même ligne — 3 sites JUSTES.

⚠ **Le cran 5 a un COÛT, et il est mesuré** : `engine/runner/operations/displace.py` écrivait
« `GetMinimumTiles180Behind`…, slot d'interface `0x4c` » — une **vraie** faute (`0x4c` est
`…180Front`, prouvé par `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPullOnce`) que la
virgule rend désormais invisible au probe. Elle a été corrigée **à la main**, et elle ne sera plus
gardée. Un cran qui supprime des faux positifs supprime aussi des vrais : le dire est la seule
façon de ne pas prendre le vert pour une couverture.

⚠ **Le probe ne voit un fichier qu'une fois SUIVI — et la garde s'est retournée contre son propre
auteur.** Le périmètre est dérivé d'un `git ls-files` : tant que la case-doc et le test n'étaient
pas indexés, leurs **exemples de syntaxe** (qui reproduisent volontairement l'attribution réfutée)
étaient invisibles. Au premier re-jeu **après le commit**, la garde est passée à **4 citations
fausses**, toutes dans les deux fichiers de cette tranche. Ce n'est pas un défaut : c'est
exactement à quoi sert le marqueur `[slot-attribution:refute]` — elles le portent désormais, et
l'exemption est **comptée** (1 → 5). Le corollaire vaut pour toute tranche suivante : **jouer le
probe avant `git add` ne prouve rien sur ce qu'on vient d'écrire.**

### Ce que les gardes ÉCARTENT, compté et imprimé

**5 114** lignes sans aucun récepteur d'interface couverte ; **200** citant `IOperationProcessor`
(gardées par `#477-r24-r1`) ; **37** MULTI-interfaces dont le couple n'est pas qualifié ; **633**
citant un slot sans lui accoler de nom ; **1** exemptée au site par `[slot-attribution:refute]` ;
**1** fichier exclu et nommé (le probe lui-même) ; **4** couples dont le nom n'est à aucun slot de
l'interface appariée — **indécidables mécaniquement**, donc listés, ni verts ni rouges (vérifiés à
la main : les 4 sont JUSTES, le nom capté étant tronqué par un retour à la ligne ou un `:`).

## 7. Un apport hors périmètre, non appliqué

`docs/rl/backlog.md` porte le résidu **`#443-r2-b1-r2` : « slot `0x13` de
`AttackQuery$$CanUseAbility` non résolu »**. La table le résout : `0x13` est le slot
d'`IActiveAbility$$IsDisabled` (1 argument) — le premier des gates que `case-433` décrit, et
`CanUseAbility` n'est pas une méthode d'interface (elle vit dans la classe `AttackQuery` seule).
La ligne n'a **pas** été modifiée : elle appartient à un autre résidu.

## Résidus

- ~~**#477-r27**~~ → **#477-r29 (renuméroté au merge), CLOS le 2026-08-06.** Le port ne comptait ni
  les alliés ni les deux camps : **il ne comptait rien** (1202 absente de
  `TRIGGERED_MOVE_PLAYBOOKS`, sur la foi d'un verdict « AI-inerte » de `case-26` que les mesures
  live de la même feuille réfutent). Porté, puis confronté par un A/B où **seul le CAMP change**
  (cible neutre au centre, un Marshal allié et un Marshal ennemi à distance 2, de part et d'autre) :
  `X_nat` = 10 / 10 sur le bras ALLIÉ, **0** sur les quatre tuiles du bras ENNEMI, 0 désaccord sur
  8 tuiles. Le modèle « deux camps » diverge sur 4 tuiles, celui d'AVANT la tranche sur 2.
  **⚠ La leçon dépasse la fiche** : le modèle « deux camps » EXISTE dans le même build, sur le même
  prédicat — `AttractMechanicalsUtility` appelle le slot `0x7a` = `GetAdjacentUnits` (4 arguments).
  `case-26` décrivait en fait CETTE feuille-là. Elle reste inerte côté port : résidu **#477-r31**.
  cf. `docs/rl/case-477r29-radsaturation-camp.md`.
- **Les slots des interfaces DÉRIVÉES mais jamais citées** (11 sur 18) ne sont gardés que par le
  cliquet, pas par des citations. Un renumérotage les ferait rougir ; une attribution fausse écrite
  demain sur `IEffect` ou `IPlaybook` serait, elle, immédiatement gardée — c'est le seul sens dans
  lequel la couverture est acquise.
- **Les 5 114 lignes sans récepteur reconnu** restent hors garde. Le recensement (`--recenser`) les
  ventile par récepteur ; aucune ne porte de couple (slot, nom) appariable sans lire le site.
