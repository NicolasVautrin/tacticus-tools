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
        GetAdjacentEnemies(caster, owner, /*ignoreSteppables*/ false);    [slot-attribution:refute]
VERDICT : ROUGE
```

*(Le `[slot-attribution:refute]` de la dernière ligne est une ANNOTATION, pas une sortie du
probe : depuis `#477-r30`, l'appariement enjambe le saut de ligne, donc ce bloc — qui reproduit
une attribution RÉFUTÉE, coupée en deux par la mise en page — redeviendrait rouge sans lui.)*

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

Les comptes se **re-dérivent** (`probe_477r25_slots_autres_interfaces.py`), ils ne se citent pas —
ils bougent à chaque tranche. Ordre de grandeur au 2026-08-06, **après** l'élargissement `#477-r30` :
~**5 260** lignes sans aucun récepteur d'interface couverte ; ~**200** citant `IOperationProcessor`
(gardées par `#477-r24-r1`) ; **39** MULTI-interfaces dont le couple n'est pas qualifié ; **641**
citant un slot sans lui accoler de nom **même sur trois lignes** ; **7** exemptées au site par
`[slot-attribution:refute]` ; **1** fichier exclu et nommé (le probe lui-même) ; **12** couples dont
le nom n'est à aucun slot de l'interface appariée — **indécidables mécaniquement**, donc listés, ni
verts ni rouges. Le probe imprime **aussi** le rétrécissement (`666 -> 641`), pas seulement l'état :
c'est ce qui distingue une garde d'un inventaire.

## 6bis. `#477-r30` — la FENÊTRE : ce que « slot et nom ADJACENTS » ne pouvait pas voir

**LIVRÉ.** `#477-r25` appariait le couple sur **une ligne**, et le disait (`665 lignes citant un
slot SANS lui accoler de nom`). La première lecture de ce gisement en a sorti une citation
**fausse** — le même slot `0x4c` donné au PUSH et au PULL dans le même paragraphe de
`test_thunderous_assault_push_live.py` — corrigée à la main au merge de `#716`. **Un cliquet dont
la zone aveugle ne rétrécit pas est un inventaire, pas une garde.**

### Le choix de la fenêtre est MESURÉ (`--courbe` le re-dérive)

| W | citations | enjambantes | `sans_couple` | indécidables | désaccords |
|--:|--:|--:|--:|--:|--:|
| **1** (état `#477-r25`) | 161 | 0 | 666 | 5 | 0 |
| **2** | 230 | 59 | 641 | 12 | 0 |
| **3** *(en service)* | 230 | 59 | 641 | 12 | 0 |
| 4 … 8 | 230 | 59 | 641 | 12 | 0 |

Le gain est **intégralement capté à W = 2**, et la courbe est **plate ensuite — jusqu'à W = 12,
pas une citation, pas un indécidable, pas un désaccord de plus**. Ce plateau est un **effet du
cran LIGNE VIDE** : aucun couple du corpus n'enjambe trois lignes *non vides*. `3` est donc pris
comme **marge à coût mesuré nul**. Zone aveugle : **666 → 641** lignes (**−25**), attestations
**161 → 230**.

⚠ **Sans le cran ligne vide, élargir RÉTRÉCISSAIT la couverture** : à ne rendre que les blocs de
taille maximale, `sans_couple` remontait de 642 (W=2) à 645 (W=4) — un bloc plus large voit plus
d'interfaces, bascule en régime multi-interface et **perd** un couple que le bloc étroit voyait.
La récolte est donc une **union sur toutes les tailles de 1 à W**, monotone par construction.

### Quatre crans RETENUS, un REFUSÉ, un de RECONNAISSANCE

1. **l'interface et le régime se jugent sur le SPAN du couple, pas sur le bloc.** Sinon
   « `$$FinishAttack` (slot 0x3b) » <!-- [slot-attribution:refute] --> se voyait attribuer à
   `IMatchState` **parce que la ligne suivante écrit `MatchState+0x60`** ;
2. **une LIGNE VIDE est une frontière** — 2 faux positifs ne tenaient qu'à ce franchissement
   (`case-433-…-a-gates-whole-board.md` : `# + slot 10` puis, *après une ligne vide*,
   `AActiveAbility$$GetPossibleTargetTiles`) ;
3. **la forme « nom PUIS slot » ne franchit JAMAIS la ligne.** Dans une énumération verticale le
   nom écrit avant appartient à l'item précédent : c'est le vice du cran VIRGULE de `#477-r25`,
   transposé de la virgule au saut de ligne. Mesure : **3 couples proposés, 3 faux** ;
4. **la CONTINUATION de commentaire** (`#`, `//`, `*`, `>`, `|`, `-`) — `\s*` ne suffit pas. C'est
   ce cran qui a fait apparaître la **jumelle exacte** de la citation motivante, dans `displace.py`
   cette fois ;
5. **REFUSÉ — interdire le `=` dans le remplissage.** Il supprimait le dernier faux positif
   (`ability_caster_gates.py`, deux affectations consécutives), mais au prix de **20 lignes de
   couverture pour 2 faux évités** ; re-mesuré sur l'état final : `sans_couple` **641 → 661**,
   enjambantes **59 → 54**, pour **0** faux évité. Le site a été **reformulé** à la place ;
6. **le qualificatif de slot est INSENSIBLE À LA CASSE.** Le dépôt écrit aussi
   « slot d'INTERFACE » (**4 sites**) — sans ce cran le motif ne reconnaissait même pas le SLOT,
   la ligne partait en `sans_couple` et **aucune fenêtre n'aurait pu la rattraper**.

### 8 citations fausses trouvées, chacune vérifiée au DÉCOMPILÉ

**58 couples enjambants proposés, 49 concordants — les 49 relus un par un, tous de VRAIS
couples** (aucune coïncidence de proximité). Les 9 désaccords se sont ventilés en **8 fautes** et
**1 faux positif de mise en page** :

| site | écrit | mesuré | source |
|---|---|---|---|
| `playbook/noncomparable/_base.py` | slot `0x3f` | **`0x40`** `HasValidTargets` (3 args) | `RecordedSimulationRequestsBattleQuery$$HasValidTargets` |
| `runner/abilities/loki/facade.py` | `0x40` = `CanAttackAnyUnitFromAnyTileWithAnyAbility` | **`0x40` = `HasValidTargets`** ; `CanAttackAny…` est au `0x38` (1 arg) | `…$$CanAttackAnyUnitFromAnyTileWithAnyAbility` (slot `0x38` littéral) |
| `runner/operations/displace.py` (push) | slot `0x4c` = `…180Behind` | **`0x4d`** | table (`0x4c` = `…180Front`, 3 args) |
| `runner/operations/displace.py` (pull) | `0xa6` = `…180Front`, « symbole DISPARU » | **`0x4c`**, et le symbole **existe** | `ghidra/functions.tsv` + metadata |
| `playbook/noncomparable/cord_claw.py` | slot `0x41` | **`0x42`** (`IBattleQuery`, délègue à `AttackQuery`) | `RecordedSimulationRequestsBattleQuery$$GetValidTargets` |
| `runner/abilities/astramilitarum.py` | slot `0x62` | **`0x63`** | `TilesAtDistanceSelector$$Select` (slot `99` littéral) + `…DisplayClass120_0$$…b__0` |
| `playbook/prediction/abilities.py` | slot `0x28` | **`0xb`** d'`IDamagePredictionQuery` | `CachedDamagePredictionQuery$$GetAttackPrediction` + `BattleQuery$$GetAttackPrediction` |
| `tests/…/test_ability_prediction_target_traits_live.py` | slot `0x28` | **`0xb`** | idem |

⚠ **Deux d'entre elles sont des jumelles de fautes DÉJÀ corrigées par `#477-r25`**, restées dans
le PORT parce qu'un saut de ligne les cachait : `facade.py` porte la faute de `case-287`, et
`displace.py` celle du test de `#477-r30`. **Corriger la fiche ne corrige pas le port.**

⚠ **Aucun code exécutable n'a bougé** : `probe_477r30_empreinte_ast.py` compare les AST
**docstrings retirées** — 10 fichiers Python, **8 identiques**, 2 divergents **déclarés**
(l'instrument et son cliquet). Il **REFUSE** de mesurer si le témoin n'est pas un ancêtre de
`HEAD` : contre `origin/master` non rebasé, il rendait **17 « non déclarés »** qui étaient tous le
travail des autres.

### Le mutant qui garde la FENÊTRE, et pourquoi les quatre autres n'y suffisaient pas

`enjambants-decales` permute le nom des slots que **seuls** des couples enjambants citent. Les
quatre mutants hérités mordent dans les deux régimes : **aucun d'eux ne dirait qu'on a perdu la
fenêtre**. Premier jet **rejeté par son propre test** — il visait tous les slots enjambants, dont
certains cités aussi sur une ligne, et mordait donc **aussi à `fenetre=1`** (63 désaccords).

## 6ter. `#477-r32` — l'étage qui manquait n'était pas la FENÊTRE, c'était le NOM SEUL

**LIVRÉ.** La fenêtre a été portée telle quelle de `probe_477r25` à
`probe_477r24r1_slots_interface.py` (le cliquet d'`IOperationProcessor`, resté au régime « slot et
nom ADJACENTS », qui écartait **166** lignes du même patron).

### La courbe, re-dérivée sur CE corpus (`--courbe`)

| W | citations | enjambantes | nom seul | `sans_couple` | désaccords | arités fausses |
|--:|--:|--:|--:|--:|--:|--:|
| **1** (régime précédent) | 60 | 0 | 9 | 181 | 0 | 0 |
| **2** | 81 | **17** | 10 | 173 | 0 | 0 |
| **3** *(en service)* | 81 | 17 | 10 | 173 | 0 | 0 |
| 4 … 8 | 81 | 17 | 10 | 173 | 0 | 0 |

Même forme que la courbe de `#477-r30` : **gain intégralement capté à W = 2, plat ensuite**. `3`
est pris comme marge à coût mesuré nul.

⚠ **Le corpus contient la tranche elle-même — et il bouge aussi sous les MERGES des autres.**
Cette fiche, le backlog et le fichier de test en font partie (seul le *probe* est exclu de son
propre balayage) ; et chaque PR fusionnée pendant la tranche en ajoute. Mesuré, **à régime
constant** : **45 → 51** attestations sous nos seules écritures, puis **51 → 60** au rebase sur
`#477-r22-r1` — qui, lui, RÉSOUT le slot `0x21`, et dont les citations neuves passent toutes le
cliquet. Les chiffres se **re-dérivent** (`--courbe`, `--ventiler`), ils ne se citent pas.
Corollaire pratique : les exemples écrits dans le test et dans les fiches doivent être des couples
**VRAIS** — un exemple faux ferait rougir le cliquet sur son propre artefact, et c'est à cela que
sert le marqueur `[slot-attribution:refute]` (3 sites).

### Un cran hérité peut COÛTER une citation juste — la non-régression le dit, pas la relecture

Porter la fenêtre, c'est aussi porter les **dix renvois** que `#477-r25` exclut du remplissage. Ils
ont été mesurés **sur l'autre corpus**. Confrontation directe : la version de `master` et la
version livrée jouées **sur le même arbre**, à `fenetre = 1` des deux côtés — le seul régime où la
comparaison ait un sens. Résultat : **1 citation JUSTE perdue**, et le cran fautif isolé en
retirant les renvois **un par un** :

| renvoi retiré de la forme « slot PUIS nom » | couples neufs | justes | faux |
|---|--:|--:|--:|
| les 8 autres (`que`, `qu'`, `interrog`, `invoq`, `appel`, `utilis`, `evalu`, `slot`) | 0 | 0 | 0 |
| `->` | 0 | 0 | 0 |
| **`→`** | **1** | **1** | 0 |

**La flèche n'est un renvoi que dans le sens « nom PUIS slot »**, où elle marque un *enchaînement*
(« `…$$ReachedSummonCap` -> slot 0x52 » désigne ce que la méthode APPELLE). Dans le sens
« slot PUIS nom » elle marque une **résolution** — « slot 0x3b → `OperationProcessor$$FinishAttack` »
—, c'est-à-dire exactement l'attribution cherchée. Les **deux** flèches sont donc retirées de la
forme C **par leur cause** : garder l'ASCII et lâcher l'unicode parce que seul l'unicode rapporte
serait un *fit* sur le corpus, pas un cran.

⚠ Un cran importé d'un corpus voisin doit être **re-mesuré**, pas recopié — et c'est une
comparaison mécanique (ancienne version vs nouvelle, même arbre) qui l'a montré, pas une
relecture. La seule autre perte est du **matériel de test** (une liste Python
`["…slot 0x65 =", "", "…MoveUnit`"]` dont la virgule est écartée) : elle ne cite rien.

### La réponse à la question binaire : **0** citation fausse sur l'axe (slot, nom)

Les **16** couples enjambants sont **tous justes**, relus un par un contre
`data/symbols/rnca9r7q6c/metadata/ioperationprocessor_slots.tsv`. Contrairement à `#477-r30`
(8 fautes sur 59), **le corpus d'`IOperationProcessor` était sain sur cet axe** — et ce n'est pas
une conclusion par absence : chacun des crans conservateurs a été **relâché séparément** pour voir
ce qu'il cachait.

| relâchement | couples neufs | dont douteux | verdict |
|---|--:|--:|---|
| la parenthèse fermante ne bloque plus le remplissage | 6 | 4 | **artefacts** : `slot 0x3a` saute la fermeture et attrape le `FinishAttack` de la proposition suivante — le faux positif que ce cran a été créé pour bloquer |
| forme « récepteur COLLÉ au slot, puis le nom » (la forme D de `#477-r25`) | 6 | 4 | **artefacts** : `processor.<slot 0x55>` en fin de ligne + `L1997` (une étiquette) au début de la suivante |
| le nom COLLÉ au numéro (`slot 0x3c AttackDamage`) | 2 | **0** | **2 couples justes**, aucun faux positif |
| forme A tolérant un appel avant le `=` (`processor.<slot 0x12>(); // -> …`) | 4 | 1 | 3 justes, 1 artefact (`// DeactivateEffect -> REVERT`) |

**Aucun des 8 douteux n'est une faute du dépôt** : tous sont fabriqués par le relâchement
lui-même. Les deux crans qui gagneraient sans bruit (nom collé au numéro, forme A après appel)
sont laissés au résidu — ils relèvent des FORMES, pas de la fenêtre.

### La faute était sur un axe que le probe ne visitait PAS

`components.py` écrivait « le slot `ApplyStatModifiers` de l'`OperationProcessor` » <!-- [slot-attribution:refute] -->
— un slot désigné par son **nom seul**, sans numéro. Ce nom n'est à **aucun** des 150 slots.

Chaîne LUE au décompilé, sur les **trois** call-sites que la fiche cite elle-même —
`IdunBattle.Operations.ReviveUnitOperation$$SetHealth`,
`IdunBattle.Operations.SetupGameOperation$$ApplyModifiers` et
`IdunBattle.Operations.TransformActorToConfigIdOperation$$UpdateStats` : **tous les trois** invoquent
le **slot 0x66** de l'`IOperationProcessor`, c'est-à-dire
`Core.Services.OperationProcessor$$TransformUnit(entity, statModifiers, isHidden)` (3 arguments,
exacts) → `IdunBattle.Operations.TransformUnitOperation$$Execute` →
`IdunBattle.Entities.UnitExtensions$$ApplyStatModifiers`, **deux niveaux plus bas**. Contrôle
croisé gratuit : le même corps invoque aussi le slot `0x2f` avec `{5, 0}`, que la table donne pour
`RefreshEffects` — l'interface visée est bien la bonne.

⚠ **La correction est REFORMULÉE pour rester confrontable** (« slot 0x66 = `TransformUnit` »)
plutôt que rangée dans l'angle mort. Écrire « slot `TransformUnit` (0x66) » aurait été *juste* et
**invisible des deux étages** : le numéro ne suit pas le mot `slot`, et la tournure « de l'… » est
rompue par la parenthèse. Corriger une citation sans la rendre **vérifiable** ne ferme rien.

⚠ **Le discriminant de l'étage 5 est la tournure « de l'<récepteur> », pas le mot en capitale.**
Un motif qui se contente de `slot <Mot>` récolte la prose — « slot **SANS** ARGUMENT », « que ce
slot **SOIT** `FinishUnitTurn` », « slots **AUTRES** que » : mesure, **5 faux positifs pour
7 citations réelles**. La tournure les dissout toutes sans en perdre une.

### Deux crans de RECONNAISSANCE, mesurés sur ce corpus

1. **le RÉCEPTEUR a le droit de s'écrire entre `slot` et le numéro** — « slot `IOperationProcessor`
   0x21 », « slot processor 0x76 », « le slot 0x23 de `Core.Services.OperationProcessor` ». Sans ce
   cran le motif ne reconnaissait même pas le **SLOT** : la ligne partait en `sans_couple` et
   **aucune fenêtre** n'aurait pu la rattraper. C'est la forme exacte du gisement « slot
   d'INTERFACE » de `#477-r30`, sur un autre qualificatif ;
2. **un nom suivi d'un POINT PUIS D'UNE LETTRE est un segment de chemin, pas une méthode.** Le
   qualificateur étant optionnel en forme A, le moteur y renonce et attrape la **tête du
   namespace** : `slot 0x46 -> `IdunBattle.Operations.DiscardHitOperation`` rendait le nom
   `IdunBattle`. **4 sites**, tous artefacts — et tous rangés là où une vraie citation fausse doit
   sortir. Avec le cran, `fenetre=1` redevient **exactement** le régime précédent.

Une **coupure** propre à ce corpus a aussi dû être ouverte : `Core.Services.OperationProcessor$$`
finit la ligne et le nom ouvre la suivante (`turnflow.py`, `runner.py`). C'est une position de
rupture **différente** de celle mesurée par `#477-r30` (qui tombait entre le signe égal et le
qualificateur), donc son propre cran et son propre test.

### Le mutant qui garde la fenêtre NE PEUT PAS porter sur la table ici

`enjambants-decales` de `#477-r30` permute le nom des slots que **seuls** des couples enjambants
citent. **Ce mutant est inconstructible sur ce corpus, et c'est une mesure** : les 16 couples
enjambants tiennent sur **8** slots (`0x06`, `0x21`, `0x3c`, `0x43`, `0x51`, `0x71`, `0x76`,
`0x77`), et **les 8 sont aussi cités sur une seule ligne ailleurs** — toute mutation de la TABLE
mordrait donc dans les deux régimes, exactement comme les quatre mutants hérités.

La mutation porte donc sur la **CITATION** : « un couple à cheval se voit attribuer le nom du slot
VOISIN ». C'est précisément la faute que l'élargissement existe pour trouver, elle n'a **aucun
porteur** à `fenetre = 1`, et le module **REFUSE** (`contre-épreuve IMPOSSIBLE`) plutôt que de
rendre une mutation vide. Mesuré : **16** désaccords en fenêtre, refus à `fenetre=1`.
⚠ Le voisin choisi doit porter un **nom différent** — l'interface a des surcharges à des slots
adjacents (`0x2e`/`0x2f` = `RefreshEffects`, `0x34`/`0x35` = `ComputerAction`), et prendre le
voisin immédiat rendrait une mutation **nulle** qui passerait pour appliquée.

### L'empreinte AST : le seul fichier de PORT touché est resté IDENTIQUE

`engine/runner/components.py` est le **seul** fichier du moteur que la tranche modifie, et
l'empreinte le rend **AST-identique** : la correction de citation n'a **emporté aucun code
exécutable**. Les deux autres divergents (l'instrument et son cliquet) sont **déclarés**.

⚠ **La déclaration est une ENTRÉE, pas une constante de l'instrument** — et c'est `#477-r30-r2`,
fusionné *pendant* cette tranche, qui l'a imposé : la table figée dans le module accusait la
branche suivante de fautes qui étaient les siennes. Cette tranche a **adopté** ce mécanisme (sa
propre correction du même défaut, écrite en parallèle, a été **abandonnée au rebase** — la
version fusionnée est meilleure : elle rend le tri-état `PAS MESURÉ / ROUGE / VERT` au lieu de se
contenter d'imprimer les déclarations périmées). La déclaration de la tranche vit dans
`scripts/python/declaration_477r32_empreinte_ast.tsv`.

### Un étage absent du tuple rendu par `jouer` est un étage SANS contre-épreuve

L'étage 5 est entré ainsi : les cinq mutants continuaient de « mordre » sur les autres colonnes, et
la garde passait pour complète. `test_etage3_chaque_etage_a_son_mutant` exige désormais que
**chacune** des 4 colonnes de `jouer` soit bougée par au moins un mutant — c'est ce qui l'a montré.
Sa dérivation est **simulée depuis l'entrée versionnée** pour que la colonne « écart
dérivation/versionné » reste observable **sans le jeu installé** ; la passer à `None` la fige à 0 et
le test se lirait « aucun mutant ne garde l'étage 2 » alors que tous le gardent.

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
- **Les ~5 260 lignes sans récepteur reconnu** restent hors garde. Le recensement (`--recenser`) les
  ventile par récepteur ; aucune ne porte de couple (slot, nom) appariable sans lire le site.
- ~~**#477-r32**~~ → **CLOS le 2026-08-06.** La fenêtre est portée à
  `probe_477r24r1_slots_interface.py` (§ 6ter). Sur `IOperationProcessor` : **17** couples
  enjambants, zone aveugle **181 → 173**, et **0 citation fausse** sur l'axe (slot, nom) —
  vérifié en relâchant chacun des crans un par un, les 8 douteux qui en sortent étant **tous**
  des artefacts du relâchement. La faute trouvée était sur un **autre axe** : le slot cité par son
  **nom seul**. cf. § 6ter.
  Le volet *(a)* — échantillonner les ~640 lignes de `probe_477r25` — reste ouvert sous
  **#477-r36** ci-dessous.
- **#477-r36 — ce qui reste hors couverture, VENTILÉ PAR CAUSE, sur les DEUX cliquets.** Le compte
  seul est un inventaire ; sa cause en fait une tâche. Sur `IOperationProcessor` (**173** lignes,
  mesurées ; `--ventiler`, et la somme des trois VAUT le total — c'est une partition
  assertionnée, pas une liste blanche de motifs) :
  * **44** ne portent **aucun numéro** — elles nomment le slot en prose (« un slot de
    l'`OperationProcessor` qui pose des modificateurs de stat ») ou le désignent par une tournure
    que l'étage 5 ne reconnaît pas (« prennent le slot `MoveUnit` (4 arguments…) », sans « de
    l'… ») ;
  * **79** portent un numéro et **aucun nom de méthode dans la fenêtre** — rien à contredire ;
  * **50** portent un numéro **et** un nom de l'interface dans la fenêtre, mais un cran
    conservateur les écarte. C'est **là** que se trouve le gisement restant, et il est **borné** :
    les quatre relâchements mesurés en § 6ter n'y sortent que **18** couples, dont **10 justes**
    (dont **1 déjà récupéré** par le cran flèche) et
    **8 artefacts**. Deux crans gagneraient sans bruit mesuré (**nom collé au numéro** : 2 couples,
    0 artefact ; **forme A tolérant un appel avant le `=`** : 3 justes pour 1 artefact) — ce sont
    des axes de FORME, pas de fenêtre, et ils n'ont pas été appliqués dans cette tranche.
  Sur les autres interfaces, les ~640 lignes de `probe_477r25` restent non ventilées : la courbe y
  est plate et elles n'ont **pas** de nom appariable ; les échantillonner reste le volet ouvert.
- **Le mot `slot` lui-même reste sensible à la casse** (seul son qualificatif ne l'est plus). Une
  ligne commençant par « Slot 0x12 = … » ne serait pas vue. Non mesuré comme gisement.
