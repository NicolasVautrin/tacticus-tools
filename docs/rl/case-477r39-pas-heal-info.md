# #477-r39 — la face STREAM du pas `Action=HealInfo`

**LIVRÉ.** `#477-r34` avait laissé DEUX familles hors périmètre dans les couples
`Action=PrepareTurn` + `Group=StartTurn`. Cette tranche porte la première — le pipeline de
SOIN — et **seulement elle** : la famille `Group=ResurrectUnit` / `Ability_CustomGroup` reste
ouverte, et sa RE est écrite ci-dessous (`#477-r38`, § 6).

Le livrable : `engine/streams/heal_unit.py`, l'entrée au périmètre de `probe_477r21` /
`probe_477r22`, le probe de généralisation `probe_477r39_heal_generalisation.py` et le cliquet
`tests/engine/test_477r39_heal_unit_offline.py`.

## 1. Le critère de la tranche, tel que le probe le publie

`python scripts/python/probe_477r22_turn_phase.py` — **rc 0**, quatre scénarios.

| scénario | hors périmètre APRÈS | sans `#477-r34` | sans `#477-r39` |
|---|---:|---:|---:|
| `C1_02`, 2 tours | **0** | 0 | 0 |
| `MC1_67`, 2 tours | **106** | 106 | 106 |
| `MC1_67`, 2v2 | **0** (était 47) | 47 | 47 |
| `MC1_67`, 2v2 sans soin | **0** | 38 | 0 |

**Les 47 lignes du roster 2v2 entrent en entier.** Neuf d'entre elles sont le sous-arbre du
soin ; les **36** autres sont deux `Group=Damage` que `#477-r34` reproduisait déjà et que la
règle du sous-arbre retenait. C'est le levier annoncé, et il est mesuré.

⚠ **LES COLONNES « SANS » MESURENT LA NÉCESSITÉ, PAS L'APPORT — ET NE S'ADDITIONNENT PAS.** Le
bloc de 47 lignes porte DEUX formes neuves : retirer `#477-r34` **ou** `#477-r39` le remet hors
périmètre **en entier**, donc les deux colonnes affichent 47. Chaque tranche est **nécessaire**,
aucune n'est **suffisante** seule. Lire l'une comme « ce que cette tranche rapporte » surestime
— c'est la mesure de `#477-r34` (« nommer un bloc par l'une des formes qu'il porte »),
transposée au compteur lui-même.

⚠ **LE COMPTE « AVANT » EST DÉSORMAIS RE-PARTITIONNÉ, PLUS LISTÉ.** `#477-r34` le calculait en
cherchant les sous-arbres PORTÉS qui contiennent un `Group=Damage` : juste pour cette famille,
faux dès qu'un bloc en porte deux. Le probe retire maintenant les formes de la tranche
(`R21.FORMES_PAR_TRANCHE`) et **re-partitionne** — la question devient exacte : « combien de
lignes seraient hors périmètre si cette forme n'y était pas entrée ? ». Retirer l'`Action=`
suffit : `_formes` juge chaque ligne séparément, donc une action étrangère sort tout son
sous-arbre même si le `Group=` reste porté.

## 2. La RE — `HealUnitOperation$$Execute`, et rien d'autre

La chaîne est courte et sans intermédiaire : **il n'existe AUCUN `StreamHelper$$GetHealTags`**.
Le build porte DIX `IdunBattle.Core.Services.StreamHelper$$Get*Tags` (`AddUnit`,
`ActiveAbilityStateUpdate`, `Damage`, `RefreshEffect`, `ResurrectUnit`, `AddOrUpdateShield`,
`AddScore`, `RemoveShield`, `ReviveUnit`, `UpdateActiveAbilityModification`) — aucune de soin.
Le dictionnaire est construit **INLINE** dans l'opération.

```
IdunBattle.Operations.HealUnitOperation$$Execute(
    caster: IEntity, target: IEntity, amount: Int32,
    scope: IdunBattle.Entities.Enum.HealScope, removeEffects: Boolean,
    abilityOrEffect: Nullable<IdunBattle.Core.AbilityOrEffect>) -> OperationResult

    var tags = new Dictionary<TagKey, int>();
    tags.Add(UnitStats_RemainingHealth /*5*/,            <composant>.<+0x18>);
    tags.Add(UnitStats_RemovedNegativeUnitEffects /*7*/, removedNegativeUnitEffects);
    tags.Add(UnitStats_WasWoundedBeforeHeal /*8*/,       wasWoundedBeforeHeal);
    tags.Add(Amount /*0xe1*/,                            result.<+0x04>);
    tags.Add(Caster_Id /*0xb4*/,          <IEntity slot 0>(caster));
    tags.Add(UnitStats_NumberOfMembers /*100*/,
             IdunBattle.Entities.UnitExtensions$$GetNumberOfMembers(target));
    Events.Action(StepType.HealInfo /*5*/, <IEntity slot 0>(target), tags);
```

Aucune ouverture de groupe : l'action est **NUE**, comme celle d'`InformOperation$$Execute`. Le
`Group=Ability_Power Source=MedicusMinistorum` que le flux montre autour vient de l'étage du
dessus (`EvaluateTriggerOperation$$EvaluateAbilityTrigger`, `engine/streams/evaluate_trigger.py`,
déjà porté).

### 2.1 Quatre lectures qui n'auraient pas été devinables

**(a) LES NOMS GHIDRA DES PARAMÈTRES SONT DÉCALÉS D'UN CRAN, ET LES PRENDRE AU SÉRIEUX INVERSE
LE SOIN.** Le retour est un `ValueType` de 0x40 octets, donc `rcx` porte le pointeur de retour
(sret), `rdx` le vrai `this`, et tout glisse : ce que Ghidra nomme `target` est le **caster**, ce
qu'il nomme `amount` est la **cible**, ce qu'il nomme `abilityOrEffect` est le booléen
`removeEffects`. La signature vraie vient de `data/symbols/<build>/frida/methods.tsv`, et **trois
recoupements internes** la confirment : le `if (<ghidra:abilityOrEffect>)` garde l'appel qui
produit `UnitStats_RemovedNegativeUnitEffects` ; `Tag=Caster_Id` reçoit l'identifiant de
`<ghidra:target>` ; et les **0x1c** octets du paramètre de pile sont recopiés tels quels dans les
deux déclencheurs post-soin, ce qui est exactement la taille d'un `Nullable<AbilityOrEffect>`.

**(b) LES SIX `Add` SONT INCONDITIONNELS, ET LE DISCRIMINANT EST LE CHEMIN DE SORTIE.** Le
décompilé enveloppe les deux derniers `Add` **et l'émission** dans un `if (<caster> != null)` —
exactement la forme du `if (caster != null)` de `StreamHelper$$GetDamageTags` autour
d'`Attacker_Id`. Les deux ne sont **pas** la même chose :

| | forme | ce qui suit le `if` | lecture |
|---|---|---|---|
| `GetDamageTags` | `if (caster != 0) { Add(0xb6, …) }` | `Add(Target_Id)`, `Add(Amount)`, … puis `return tags` | **`if` du source C#** — le port de `#477-r34` a raison |
| `HealUnitOperation$$Execute` | `if (<caster> != 0) { Add(0xb4) … Action(…) }` | **rien** — l'échec tombe sur `FUN_1801f51f0`, marqué « does not return » | **null-check de codegen** autour de `caster.Id` |

Écrire ici la conditionnalité de `GetDamageTags` produirait, sur un caster nul, une
`Action=HealInfo` à quatre tags que le natif n'émet **jamais** : il lève.

**(c) `Amount` EST `result.<+0x04>`, PAS `result.<+0x00>`.** `GetDamageTags` écrit son `Amount`
depuis `*(uint*)result` ; ici le décompilé lit les 32 bits **hauts** du premier qword, c'est-à-dire
le champ que l'opération vient d'incrémenter (`result.<+0x04> += healedAmount`). Deux clés du même
nom, deux champs différents du même `OperationResult`.

**(d) `UnitStats_NumberOfMembers` VIENT D'UN HELPER NOMMÉ, PAS D'UN OFFSET.** Le natif appelle
`IdunBattle.Entities.UnitExtensions$$GetNumberOfMembers(target)`, là où `GetDamageTags` lit
`<composant>.<+0x18>` pour la **même** clé. Deux canaux, une grandeur — le port les reçoit tous
deux résolus (borne (c)).

### 2.2 Ce qui est LU et volontairement NON porté

- **Les DEUX gardes qui suppriment l'émission**, toutes deux de vrais `if` (elles rendent le
  `OperationResult` par un `return` normal, ce qui est précisément le critère du (b) ci-dessus) :

  ```
  if (!AttackQuery.<slot 0x11>(caster, target, scope, removeEffects)) return result;
  ...
  if (!wasWounded && healedAmount < 1 && removedNegativeUnitEffects < 1
      && !UnitExtensions.HasFlag(caster, 0x17))                       return result;
  ```

  La seconde est le seul endroit où les trois grandeurs du dictionnaire se relisent **ensemble** :
  un soin qui ne soigne rien, sur une cible intacte, sans effet retiré, n'écrit rien. Résidu
  **#477-r41** ;
- **tout le calcul du soin** : `DamagePredictionQuery.<slot 1>(caster, casterMainTile, target,
  amount, scope)` puis `FillUpStatComponent$$FillUp`, avec la remise à zéro quand
  `EntityExtensions$$HasEffect(target, state, 0x4f, null)` ;
- **l'ORDRE `IsWounded` puis `FillUp`** est lu, pas déduit du nom du tag : le natif appelle
  `HealthComponent$$IsWounded(fill)` **avant** `FillUpStatComponent$$FillUp(fill, …)` ;
- **les mutations ECS** (`ActorStatisticsComponent$$AddRestoreHealthAction`, les compteurs
  `+0xc8` / `+0xd4` / `+0xe4`) : elles n'écrivent rien dans le flux ;
- **les QUATRE appels POST-ÉMISSION** — trois déclencheurs d'`EventTriggerType` (`0x1e` sur la
  cible, `0x2b` puis, si `removeEffects`, `0x2c` sur le caster) et un
  `RefreshEffects(RefreshEffectOptions{3, null})`. Ils peuvent émettre, et ce qu'ils émettent
  apparaît **après** l'action, à la **même profondeur** — l'opération n'ouvrant aucun groupe, le
  port les reçoit comme des sous-arbres frères, jamais comme un corps.

## 3. Ce qui est MESURÉ, et ce qui est COPIÉ

Les six tags sont des **ENTRÉES** lues dans le flux (borne (c)). Ce foyer est **plus copié** que
celui du dégât, et c'est déclaré : le `Group=Damage` offre TROIS canaux pour la même entité
(l'en-tête, l'action, `Tag=Target_Id`), donc deux d'entre eux sont des prédictions ; ici il n'y
en a qu'**UN**, `HealUnitOperation$$Execute` n'écrivant aucun `Tag=Target_Id`. Ce qui reste
MESURÉ :

| | dérivation | confrontée par |
|---|---|---|
| (DH1) | la FORME : une `Action=` **nue**, pas un groupe | `heal_ouvre_groupe` |
| (DH2) | l'ENTITÉ : celle de la CIBLE, quand le `Tag=Caster_Id` de la même action en porte une autre | `heal_entite` |
| (DH3) | l'appariement clé ↔ grandeur des six `Add` | `heal_tag_caster`, `heal_permute_etats`, `heal_permute_valeurs` |

## 4. Les CINQ contre-épreuves — et celle qui a été REFUSÉE d'avance

`heal_entite`, `heal_tag_caster`, `heal_ouvre_groupe`, `heal_permute_etats`,
`heal_permute_valeurs` — **5 / 5 OK** sur leur domaine, `mord` séparé de `rougit`, domaine
**CALCULÉ** (`applicable_heal`) et jamais déclaré après coup.

⚠ **UNE SIXIÈME A ÉTÉ ÉCARTÉE, ET C'EST LE MÊME CRAN QUE LA NEUVIÈME DE `#477-r34`.** La faute
la plus intéressante serait de recopier ici la conditionnalité lue dans `GetDamageTags`
(`if (caster != null) Add(…)`) — c'est exactement la confusion que le (b) écarte. Mais **toutes**
les `Action=HealInfo` du corpus portent un `Tag=Caster_Id`, donc la garde ne retirerait jamais
rien : la mutation serait **INERTE PAR CONSTRUCTION**, et le garde-fou hérité de `#477-r22-r1` la
refuserait. La lecture est portée, gardée offline, et **déclarée NON EXERCÉE**.

## 5. La GÉNÉRALISATION — `probe_477r39_heal_generalisation.py`

⚠ **UN VERT OBTENU SUR LE SEUL CORPUS HÉRITÉ NE DIRAIT PRESQUE RIEN, ET C'EST CE QUI A IMPOSÉ CE
PROBE.** Sur les quatre scénarios de `probe_477r22`, **un seul** porte une `Action=HealInfo`, et
il n'en porte que **DEUX** — même ability, même cible, même valeur d'`Amount`. Trois angles morts
en découlaient : les autres porteurs du trait `Healer` (quatre au pool), l'**auto-soin** (le
régime où `heal_entite` devient hors domaine, donc celui où un port qui aurait interverti les deux
entités resterait VERT), et les deux clés d'état, à **une seule valeur** sur ce corpus
(`RemovedNegativeUnitEffects` = 0, `WasWoundedBeforeHeal` = 1).

Le probe monte cinq rosters — les quatre soigneurs du pool en 2v2, plus un **1v1 dérivé** où la
seule cible possible du soin EST le soigneur — applique le **même** foyer, et publie la
ventilation des RÉGIMES. Le board reste `MC1_67` pour une raison lue : c'est son effet de tuile
(`EnvDespoiledGroundTileDamage`) qui blesse au début du tour, donc qui ouvre la garde amont.

Un régime qu'aucun roster n'atteint est **publié** comme non exercé ; un corpus qui n'atteindrait
**aucun** soin fait ROUGIR — c'est le signe que le montage ne tient plus, pas que le port serait
faux.

### 5.1 Le résultat, et ce qu'il a coûté de le rendre non trivial

⚠ **LE NOMBRE DE TOURS EST UNE VARIABLE DE LA MESURE, ET IL A DÛ ÊTRE MESURÉ.** À **deux** tours,
les cinq rosters ne rendent que **2** actions, toutes du **même** producteur : les trois autres
soigneurs n'en produisent **aucune**, parce que leur ability de soin est **ACTIVE**
(`RevitalizingMalignancy`, `BloodChalice`, `AberrantHypermorph`, `RitesOfRestoration`) et que
l'IA ne l'avait pas encore castée — seul `MedicusMinistorum` est un **passif** qui se déclenche
tout seul. Le corpus restait donc à **un** producteur, et le probe l'a dit au lieu de rendre un
vert : `ATTENTION : un SEUL producteur enveloppant sur tout le corpus`.

À **quatre** tours, `SanguinaryPriest` (le passif de `bloodSanguinary`) entre à son tour :

| roster | tours | `Action=HealInfo` | producteur |
|---|---:|---:|---|
| `hospitaller-2v2` | 4 | **2 / 2** | `MedicusMinistorum` |
| `sanguinary-2v2` | 4 | **1 / 1** | `SanguinaryPriest` |
| `rotbone-2v2` | 4 | 0 | — |
| `biophagus-2v2` | 3 | 0 | — |

**3 / 3 reproduites à l'égalité brute, sur DEUX producteurs distincts**, et les cinq
contre-épreuves mordent et rougissent sur chacune. Le défaut du probe est passé à 4 pour cette
raison-là.

**Quatre régimes restent NON EXERCÉS**, et le probe les nomme : `auto-soin`,
`cible NON blessée`, `effets retirés > 0`, `membres > 1`. Le premier a été **cherché** (le 1v1
`adeptHospitaller`) et n'est pas venu : ce montage ne produit aucun soin du tout, ce qui suggère
que `MedicusMinistorum` ne cible pas son propre porteur — mais cela reste une **hypothèse**, la
RE de son arbre de ciblage n'ayant pas été faite. Le second est structurellement rare (§ 7).

## 6. `#477-r38` — la RE est écrite, le port ne l'est PAS, et la tranche est TOUT-OU-RIEN

**NON PORTÉ, mesuré.** Les 106 lignes de `MC1_67` sont **UN SEUL sous-arbre**, et il porte
**23 formes étrangères** — 6 structurelles (`Group=Ability_CustomGroup`, `Group=ResurrectUnit`,
`Action=Resurrect`, `Action=DirectlyKillUnit`, `Action=RemoveUnit`,
`Action=RemoveUnitFromTiles`) et **17 `Tag=`**.

⚠ **PORTER UNE PARTIE NE LIBÈRE RIEN, ET C'EST MESURÉ, PAS DÉDUIT.** En ajoutant au périmètre
chaque famille séparément puis les trois ensemble, le hors-périmètre reste **106 / 106 / 106 /
106**. Il n'y a donc pas de sous-tranche qui rapporte : `#477-r38` se livre en entier ou pas du
tout. C'est la différence avec `#477-r39`, dont neuf lignes en libéraient quarante-sept.

La chaîne est **fermée de bout en bout**, chaque maillon étant une fonction nommée :

```
IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$CreateBehaviour
    Foreach(SortByFormula(GetUnitsEligibleForResurrect(), ConditionalAmount(HasTrait(0x10), …)),
        If(AmountIsGreaterThanZero(decoys) & AmountIsGreaterThanZero(eligibles),
           DSLBehaviors.Group(                                 <- LE NOEUD DSL, pas une Operation
               DSLBehaviors.Resurrect(targets, PickRandomly(decoys, 1, …), StatAmount(…), 2,
                                      Nullable(AbilityType), true),
               <selecteur d'entite>, GroupType.Ability_CustomGroup /*0x31*/)))

IdunBattle.Entities.Behaviours.GroupBehaviour$$Execute            <- `Group=Ability_CustomGroup`
    groupEntity = <selecteur this+0x68>.Select(entities);
    Events.StartGroup(this.<+0x60> /*groupType*/,
                      groupEntity != null ? <IEntity slot 0>(groupEntity) : 0,
                      "" /*meme slot de litteral, index 0*/, null);
    if (this.<+0x50> != null) <abilityBehaviour>.Execute(entities, ...);
    Events.FinishGroup();

IdunBattle.Entities.Behaviours.ResurrectBehaviour$$Execute        <- n'ouvre AUCUN groupe
    for (i in 0 .. Min(units.Count, tiles.Count))
        processor.<slot 0x64>(units[i], healType, tiles[i], health, abilityType, options);

IdunBattle.Operations.ResurrectUnitOperation$$Execute             <- `Group=ResurrectUnit`
    ... gardes (IsDefeated, slot 0x31 d'IBattleQuery, TilesAreOccupied, TilesAreWalkable,
        GetFeetCount == tiles.Count, slot 0xa5) ...
    Events.StartGroup(GroupType.ResurrectUnit /*0x29*/, <IEntity slot 0>(unit),
                      String.Empty, default(BEntityId?));
    $$KillSteppableUnits(unit, tilesUnits)                        <- les 4 actions sur l'occupant
        foreach (steppable in steppableUnits)
            processor.<slot 0x60>(killer, steppable.Entity,
                                  KillUnitOperationOptions{2, ..., 0x10100000000});
    $$SendStreamEvents(unit, tiles, abilityType)                  <- les 4 emissions du corps
        tags = StreamHelper.<slot 1>(unit, tiles, abilityType);   // GetResurrectUnitTags
        Events.Action(StepType.Resurrect /*0x24*/,  <IEntity slot 0>(unit), tags);
        Events.Action(StepType.ChangeStats /*0xc*/, <IEntity slot 0>(unit),
                      UnitExtensions.GetFullStateUpdateTags(unit));
        var d = new Dictionary<TagKey,int>();
        d.Add(UnitStats_ActionsAvailable /*0x6f*/,
              UnitExtensions.HasFlag(unit, UnitFlag.NoActionAvailable /*4*/) ^ 1);
        Events.Action(StepType.ChangeStats /*0xc*/, <IEntity slot 0>(unit), d);
        foreach (a in <composant A>.<+0x20>)                       // les ACTIVE
            Events.Action(StepType.ChangeAbility /*0xd*/, <IEntity slot 0>(unit),
                          UnitExtensions.GetFullStateUpdateTags(a));
        foreach (t in <composant B>.<+0x18>)                       // les TRIGGERED
            Events.Action(StepType.ChangeAbility /*0xd*/, <IEntity slot 0>(unit),
                          UnitExtensions.GetFullStateUpdateTags(t, ...));
    ... mutations ECS ...
    Events.FinishGroup();

IdunBattle.Core.Services.StreamHelper$$GetResurrectUnitTags(unit, tiles, abilityType)
    tags.Add(Unit_Owner_Id /*0x77*/,  EntityExtensions.GetOriginalOwnerEntityId(unit));
    tags.Add(Unit_IsSummoned /*0x86*/, UnitExtensions.GetParent(unit, state, null) != null);
    tags.Add(Unit_Foot_Tile_Id_1 /*0x79*/, <IEntity slot 0>(tiles[0]));
    tags.Add(UnitStats_NumberOfMembers /*100*/, <composant>.<+0x18>);
    if (abilityType.HasValue) {
        if (abilityType.Value.ActiveAbility.HasValue)
            tags.Add(Active_Ability_Type  /*0xce*/, ...);
        if (abilityType.Value.TriggeredAbility.HasValue)
            tags.Add(Passive_Ability_Type /*0xcf*/, ...);
    }

IdunBattle.Operations.RemoveUnitOperation$$Execute(unit, removeEffects, keepActive)
    tags.Add(Unit_IsDying /*0x88*/,       UnitExtensions.HasFlag(unit, 6));
    tags.Add(Unit_WasOverkilled /*0x89*/, UnitExtensions.HasFlag(unit, 8));
    Events.Action(StepType.RemoveUnit /*0xb*/, <IEntity slot 0>(unit), tags);

IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute(unit, removeTileFromUnit)
    tags.Add(Clear_Unit_Tiles /*0x85*/, removeTileFromUnit);      // UN SEUL `Add`
    Events.Action(StepType.RemoveUnitFromTiles /*0x1b*/, <IEntity slot 0>(unit), tags);
```

⚠ **`RemoveUnitFromTilesOperation$$Execute` A DEUX SURCHARGES**, et le build les distingue par
leur premier paramètre (`units` vs `unit`). Celle ci-dessus est celle qui **émet** ; le flux la
montre **deux fois** sur la même entité, avec la même valeur — l'appelant l'appelle deux fois, ce
n'est pas une boucle de l'opération.

**Cinq lectures déjà acquises**, qui font gagner du temps à qui reprendra :

1. **LES DEUX GROUPES ONT DEUX PRODUCTEURS DIFFÉRENTS, ET AUCUN N'EST CELUI QU'ON SUPPOSERAIT.**
   `Group=Ability_CustomGroup` sort d'un **nœud DSL** (`DSLBehaviors$$Group`, exécuté par
   `GroupBehaviour$$Execute`) dont le `groupType` est un **argument de l'arbre** — le littéral
   `0x31` est lisible dans `EnvAmbushResurrectAbility$$CreateBehaviour`. `Group=ResurrectUnit`,
   lui, est ouvert par l'**Operation** (`ResurrectUnitOperation$$Execute`), et
   `ResurrectBehaviour$$Execute` — le nœud DSL du dessus — n'ouvre **rien du tout**. Supposer
   « un groupe = un behaviour » aurait fait chercher le second au mauvais étage.
2. **LE `Source=` DU `Group=ResurrectUnit` PASSE PAR `String.Empty`, PAS PAR LE SLOT DE
   LITTÉRAL** qu'utilisent `Group=StartTurn` et `Group=Damage`. Les deux voies rendent la même
   chaîne vide et ne sont **pas** distinguables après `String.Format` : c'est une lecture, pas
   une mesure — et c'est le cinquième `Source=` vide de ce dossier.
3. **`GetResurrectUnitTags` N'A PAS DE CASCADE.** Ses deux tests de source sont **indépendants**
   (deux `if`, pas un `else if`) et il n'y a **pas** de branche `Effect` — l'inverse exact de
   `GetDamageTags`, dont les deux cascades s'arrêtent au premier champ non vide. Le flux confirme :
   `Action=Resurrect` y porte `Tag=Passive_Ability_Type:1271` seul.
4. **`UnitStats_ActionsAvailable` est ici l'INVERSE d'un drapeau**, écrit `HasFlag(unit,
   UnitFlag.NoActionAvailable) ^ 1` — le **même** recoupement que celui de `#477-r22-r1` (« la
   VALEUR est l'INVERSE du sens du drapeau »), obtenu par une deuxième fonction indépendante.
   ⚠ Mais la ligne est ici **dans un sous-arbre**, pas à la profondeur du groupe : la règle
   structurelle `_marque` de `probe_477r22` ne la voit pas, et c'est pourquoi
   `Tag=UnitStats_ActionsAvailable` figure parmi les 17 formes étrangères.
5. **Les trois `GetFullStateUpdateTags` sont DÉJÀ PORTÉS** (`engine/streams/unit_extensions.py` :
   `get_full_state_update_tags`, `_for_active`, `_for_triggered`). Le flux le confirme ligne à
   ligne : un `ChangeStats` à 16 tags, puis trois `ChangeAbility` d'ability active et deux de
   triggered — exactement les deux boucles du décompilé.

**Ce qui reste à lire** : `KillUnitOperation$$Execute` seul — l'`Action=DirectlyKillUnit` et son
`Tag=Unit_WasOverkilled`. Tout le reste de la chaîne est lu ci-dessus.

**Ce qu'il faudra ÉCRIRE** : `engine/streams/group_behaviour.py` (le producteur générique de
groupes DSL, qui couvre les deux `Group=`), `engine/streams/resurrect_unit.py`
(`GetResurrectUnitTags` + `SendStreamEvents`), les trois opérations de `KillSteppableUnits`, et
l'extension du périmètre aux **17 `Tag=`** — dont la plupart sont déjà produits par
`unit_extensions.get_full_state_update_tags`, mais ne sont pas encore **déclarés** dans
`_formes_portees` (qui ne connaît, pour l'axe `ChangeStats`, que les clés de
`_tags_de_transformation()`).

## 7. Ce qui n'est PAS couvert

- **La DÉCISION qu'un soin produise une `Action=HealInfo`** : elle vit dans les deux gardes de
  § 2.2, qui ne sont pas une face stream. L'appelant appelle — ou n'appelle pas (`#477-r41`) ;
- **tout le calcul du soin** : les six valeurs sont des entrées ;
- **la branche `caster == null`** : portée (les six `Add` inconditionnels), **NON EXERCÉE** live,
  gardée offline ;
- **le régime `WasWoundedBeforeHeal = 0`** est structurellement rare, et la RE dit pourquoi : la
  garde de § 2.2 exige `wasWounded || healedAmount > 0 || removedNegative > 0 ||
  HasFlag(caster, 0x17)`, et une cible non blessée rend `FillUp` nul. Il n'apparaît donc qu'avec
  un retrait d'effet ou le drapeau `0x17`. Le probe de généralisation le publie ;
- **les AUTRES pas du même vocabulaire** : `StepType.RepairInfo` (6) — le pendant machine — et
  `StepType.LootInfo` (26) sortent d'opérations distinctes et restent HORS, ÉNUMÉRÉS ;
- **`#477-r38`** (§ 6) et **`#477-r40`** (le `Group=Ability_Power` dont le `Source=` est un
  `EffectType`) restent ouverts.

## Résidus

- **#477-r41** — **les DEUX gardes d'émission de `HealUnitOperation$$Execute`.** Lues et citées
  au § 2.2 ; aucune n'est une face stream (elles vivent dans l'ÉTAT ECS et dans `AttackQuery`),
  et aucune n'est atteinte par nos montages — tous nos soins passent. Même forme que
  `#477-r22-r2`.
- **#477-r38** — **la famille `Group=ResurrectUnit` / `Ability_CustomGroup`**, 106 lignes sur
  `MC1_67` à deux tours. RE écrite au § 6, périmètre chiffré (23 formes, dont 17 `Tag=`), et
  **TOUT-OU-RIEN mesuré** : aucune sous-tranche ne libère la moindre ligne.
