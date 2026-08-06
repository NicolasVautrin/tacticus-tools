# #477-r34 — la face STREAM du `Group=Damage`

**LIVRÉ.** `#477-r22-r1` avait laissé DEUX familles hors périmètre dans les couples
`Action=PrepareTurn` + `Group=StartTurn`. Cette tranche porte la seconde — `Group=Damage` — et
**seulement elle** : la famille `Group=ResurrectUnit` reste ouverte (`#477-r38`).

Le livrable : `engine/streams/damage_result.py`, `stream_helper.get_damage_tags`,
`engine/streams/apply_damage.py`, plus l'entrée au périmètre de `probe_477r21` /
`probe_477r22` et le cliquet `tests/engine/test_477r34_apply_damage_offline.py`.

## 1. La RE — de `ApplyDamageOperation$$Execute` jusqu'aux trois émissions

Le `Group=Damage` a **un** producteur, et sa face stream tient en trois appels, lus verbatim
dans `IdunBattle.Operations.ApplyDamageOperation$$Execute` :

```
Events.StartGroup(GroupType.Damage /*0x1a*/, <IEntity slot 0>(target),
                  "" /*slot de litteral, index 0*/, default(BEntityId?));
Events.Action(StepType.UnitDamaged /*4*/, <IEntity slot 0>(target),
              StreamHelper.<slot 9>(target, damageResult, numMembersDied, caster, result));
...                                              // ~550 lignes de decompile -- le `corps`
Events.FinishGroup();
```

Le décompilé fait **2 063 lignes** : il n'a pas été lu en entier, et c'est déclaré. Ce qui a été
lu est **la face stream** — les trois sites d'émission et leur ordre — plus le helper de tags.
Tout le reste (statistiques de coup, bouclier, membres, drapeaux, événements post-dégât) est de
l'état ECS et n'écrit rien dans le flux.

**Le `Source=` vide est le MÊME slot de littéral que celui du `Group=StartTurn`** — résolu par
`data/symbols/<build>/metadata/string_literals.tsv` à l'index 0, valeur `""`. La distinction
avec `String.Empty` (la voie de `User_PlaceUnit`) n'est pas observable après `String.Format` :
elle est lue.

### 1.1 `StreamHelper$$GetDamageTags` — quinze clés, trois conditionnelles

La signature vient de `data/symbols/<build>/frida/methods.tsv`, pas d'une déduction :

```
StreamHelper.GetDamageTags(target: IdunBattle.Core.IEntity,
                           damageResult: IdunBattle.Core.Services.DamageAppliedResult,
                           numMembersDied: System.Int32,
                           caster: IdunBattle.Core.IEntity,
                           result: IdunBattle.Core.OperationResult)
  -> Dictionary<IdunBattle.Streams.TagKey, System.Int32>
```

| ce que le natif lit | clé |
|---|---|
| `<composant>.<+0x18>` ×3 et `ShieldComponent$$GetTotalShield` | `UnitStats_RemainingHealth`, `UnitStats_RemainingArmor`, `UnitStats_NumberOfMembers`, `Shields_RemainingAmount` |
| `damageResult.<+0x0e/+0x0c/+0x0d/+0x0f>` | `Attack_DidCrit`, `Attack_DidBlock`, `Attack_DidEvade`, `Attack_WasOverkill` |
| `damageResult.<+0x14> == 0` | `Attack_Is_First_Hit` |
| `numMembersDied` **si > 0** | `UnitStats_NumberOfMembers_Change` |
| `numMembersDied > 0` | `Attack_WasMemberKilled` |
| `<IEntity slot 0>(caster)` **si caster != null** | `Attacker_Id` |
| `<IEntity slot 0>(target)` / `result.<+0x00>` / `damageResult.<+0x00>` | `Target_Id`, `Amount`, `DamageProfileType` |
| cascade sur `damageResult.<+0x40>` | `Active_Ability_Type` / `Passive_Ability_Type` / `Effect_Type` |
| cascade sur `damageResult.<+0x78>` | `Additional_Hit_ActiveAbility_Source` / `..._TriggeredAbility_Source` / `..._Effect_Source` |

### 1.2 Cinq lectures qui n'auraient pas été devinables

**(a) Le LAYOUT vient du `.ctor`, et il donne `armorDamage` comme paramètre JAMAIS ÉCRIT.**
`IdunBattle.Core.Services.DamageAppliedResult$$.ctor` assigne chaque paramètre à un offset
explicite ; c'est cette fonction, et elle seule, qui attribue `+0x0c`..`+0x0f` aux quatre
booléens, `+0x14` à `hitIndex` et `+0x18` à `isFirstDamagingHit`. Le paramètre `armorDamage`
n'y reçoit aucun offset — il est **lu et non porté**, plutôt que placé à un offset inventé.

**(b) `Attack_Is_First_Hit` sort de `hitIndex == 0`, PAS du champ `isFirstDamagingHit`.** Les
deux existent, à deux offsets voisins. Le getter qui calcule le tag a un corps trivial
(`return *(int*)(this + 0x14) == 0;`) qu'IL2CPP **déduplique** : Ghidra le nomme
`IdunMetaLogic.UserProgress.ProductCost$$get_IsFree`. Prendre ce nom au sérieux ferait lire « le
produit est gratuit ». C'est l'avertissement du CLAUDE.md sur les tables, dans sa forme
**PRÉSENCE trompeuse** — et seul l'offset `+0x14` tranche.

**(c) Le champ s'appelle `TriggeredAbility`, le tag `Passive_Ability_Type`.** Les trois champs
d'`IdunBattle.Core.AbilityOrEffect` sont nommés par leurs setters
(`set_ActiveAbility`/`set_TriggeredAbility`/`set_Effect`, types déclarés
`Nullable<ActiveAbilityType>`/`<TriggeredAbilityType>`/`<EffectType>`) ; les clés qu'ils
produisent ne portent pas les mêmes noms. Un port qui apparierait « `Passive_Ability_Type` → un
type passif » se tromperait de champ **et** d'enum — et la faute serait **silencieuse en
ordinal** (`TriggeredAbilityType` partage 458 ordinaux avec `EffectType`, dont 454 nomment autre
chose).

**(d) Le retour est ANTICIPÉ quand la source du coup est vide, et c'est ASYMÉTRIQUE.** Si
`damageResult.<+0x40>` n'a pas de valeur, la fonction **rend** — le bloc `Additional_Hit_*`
n'est alors jamais évalué, même si `<+0x78>` en a une. Si le `Nullable` a une valeur mais que
ses trois champs sont vides, le natif fait un `goto` qui saute seulement l'`Add` et évalue quand
même le hit additionnel. Les deux chemins diffèrent, et les confondre serait **invisible** sur
tout corpus où la source est toujours présente — c'est le nôtre (72 / 72). Portés tels quels,
déclarés NON EXERCÉS, gardés offline.

**(e) Les deux `Nullable<AbilityOrEffect>` appartiennent à `DamageSource`, pas à
`DamageAppliedResult`.** Le recoupement est arithmétique : le `.ctor` copie `source` à `+0x28`,
et `IdunBattle.Operations.DamageSource$$get_IsFromAnyAbility` lit `this + 0x18` — or
`0x28 + 0x18 = 0x40`, l'offset exact que `GetDamageTags` teste. Le second, `0x28 + 0x50 = 0x78`,
tombe de même, et `0x50 + 0x1c` (la taille d'un `Nullable<AbilityOrEffect>`) referme les `0x6c`
de `DamageSource`. Deux fonctions indépendantes, un seul layout.

## 2. Le résultat, mesuré

`python scripts/python/probe_477r22_turn_phase.py` — **rc 0**, quatre scénarios.

| | `C1_02` | `MC1_67` | 2v2 | 2v2 sans soin | **total** |
|---|---:|---:|---:|---:|---:|
| couples reproduits | 5/5 | 5/5 | 5/5 | 5/5 | **20 / 20** |
| `Group=Damage` reproduits (tout le flux) | 19/19 | 18/18 | 12/12 | 12/12 | **61 / 61** |
| lignes de `Group=Damage` | 367 | 345 | 218 | 218 | **1 148** |

**Le foyer est confronté sur TOUT le flux, pas sur les seuls couples**, exactement comme
`#477-r22-r1` l'a fait pour le slot `0x76` : le `Group=StartTurn` n'en porte qu'un, et seulement
sur certains montages. Les `Group=Damage` du flux sortent aussi de `User_UseAbility` (le gros du
volume) et de `System_ProcessDeaths`.

### 2.1 Le compte AVANT / APRÈS, par scénario

| scénario | hors périmètre AVANT | entrées | APRÈS | ce qui retient le reste |
|---|---:|---:|---:|---|
| `C1_02`, 2 tours | 0 | 0 | **0** | — |
| `MC1_67`, 2 tours | 106 | 0 | **106** | `Group=ResurrectUnit` / `Ability_CustomGroup` (`#477-r38`) |
| `MC1_67`, 2v2 | 47 | 0 | **47** | `Action=HealInfo` (`#477-r39`) — **9 lignes** qui en retiennent **36** de `Group=Damage` |
| `MC1_67`, 2v2 **sans soin** | 38 | **38** | **0** | — |

⚠ **NOMMER UN BLOC PAR L'UNE DES FORMES QU'IL PORTE SURESTIME CE QUE PORTER CETTE FORME
RAPPORTE.** `case-477r22` § 7.6 attribue les 47 lignes du roster 2v2 à `Group=Damage` ; la
ventilation les décompose en **36** lignes de `Group=Damage` (que cette tranche reproduit
désormais à l'égalité brute) et **11** d'un `Group=Ability_Power` + `Action=HealInfo`. La règle
« un sous-arbre part hors périmètre EN ENTIER » — qui est juste — fait que porter la famille
`Damage` ne fait **rien** entrer de ce bloc-là. Le probe publie désormais, pour chaque bloc
restant, **quelles formes le retiennent**.

### 2.2 Le quatrième scénario est CRAFTÉ, pas choisi

Aucun des trois scénarios hérités ne fait entrer de `Group=Damage` dans un couple : `C1_02` et
`MC1_67` à deux tours n'en portent pas à cet endroit (un dégât de début de tour vient d'un effet
de TUILE, qui exige qu'une unité s'y soit posée), et le roster 2v2 en porte deux que le
`HealInfo` retient. Le roster livré est celui du 2v2 avec **`adeptHospitaller` →
`adeptCanoness`** : même board, même seed, mêmes deux cibles (entités 81 et 83, mêmes
`Attacker_Id` 21 et 12, mêmes `Amount` 565 et 798) — le dégât de tuile est **préservé**, le soin
**disparaît**, et les 38 lignes entrent.

⚠ **Un scénario LONG a été essayé et ÉCARTÉ** : `C1_02` à six tours porte bien 36 lignes de
`Group=Damage` dans un couple, mais leur sous-arbre est retenu par un
`Group=Ability_Power Source=TerminatorArmour_Visual` — un nom qui vit dans `EffectType`, pas
dans `TriggeredAbilityType` (`#477-r40`). Gain zéro, pour six tours de jeu.

## 3. Ce qui est MESURÉ, et ce qui est COPIÉ

Les quinze tags sont des **ENTRÉES** lues dans le flux (borne (c)), comme les identifiants
d'entité l'étaient chez le parent. Ce que le port **DÉRIVE** :

| | dérivation | `C1_02` | `MC1_67` | 2v2 | 2v2 sans soin |
|---|---|---:|---:|---:|---:|
| (DD1) | l'ENTITÉ : le probe ne donne que `Tag=Target_Id`, le port produit **trois** occurrences | 19/19 | 18/18 | 12/12 | 12/12 |
| (DD2) | `Attack_WasMemberKilled` dérivé de la **PRÉSENCE** de `UnitStats_NumberOfMembers_Change` | 19/19 | 18/18 | 12/12 | 12/12 |
| (DD3) | la conditionnalité de `UnitStats_NumberOfMembers_Change` | (`damage_change_inconditionnel`) |
| (DD4) | l'appariement champ → clé des deux cascades | **COPIÉ** — cf. § 4 |

**(DD1) est la dérivation centrale.** Le natif appelle deux fois l'accesseur d'identifiant
d'`IdunBattle.Core.IEntity` sur le même `target` ; le port fait suivre un seul paramètre, pris
du **tag**, et produit l'en-tête du groupe et l'entité de l'action. Une divergence des trois
canaux ferait rougir le diff — **0 sur 61**.

**(DD2) n'est jamais copié** : le booléen est reconstruit depuis la présence d'un *autre* tag.
Exercé : **5** groupes avec mort (2 sur `C1_02`, 2 sur `MC1_67`, 1 sur `C1_02`-6t hors corpus),
**56** sans.

`hit_index` est **posé au minimum qui reproduit**, comme les deux prédicats de mobilité de
`#477-r22-r1` : le flux ne publie pas l'indice du coup, seulement le booléen. Ce qui reste
mesuré de ce champ est la **forme du test**, que `damage_premier_hit` confronte.

## 4. Les HUIT contre-épreuves — et celle qui a été RETIRÉE

`damage_entite_groupe`, `damage_ordre_action`, `damage_source_groupe`, `damage_voie_source`,
`damage_voie_additionnelle`, `damage_change_inconditionnel`, `damage_premier_hit`,
`damage_membre_tue` — **8 / 8 OK**, jouées sur chaque `Group=Damage` de leur domaine, `mord`
séparé de `rougit`, domaine **CALCULÉ** (`applicable_damage`) et jamais déclaré après coup.

⚠ **UNE NEUVIÈME A ÉTÉ ÉCRITE PUIS RETIRÉE, ET C'EST UNE MESURE QUI L'A IMPOSÉ.** La faute la
plus naturelle sur `Attack_WasMemberKilled` serait d'y écrire le **compte** au lieu du booléen.
Or `UnitStats_NumberOfMembers_Change` vaut **1** dans ses 5 occurrences du corpus, et rien
d'autre : `1` et `True` s'écrivent tous deux `1`, donc la mutation serait **INERTE PAR
CONSTRUCTION sur 61 / 61**. Le garde-fou hérité de `#477-r22-r1` l'aurait refusée. Elle est
remplacée par `damage_membre_tue`, qui **inverse** le booléen et mord partout.

⚠ **LE VERT DU SCÉNARIO SAIN NE PROUVE PAS L'APPARIEMENT DES CASCADES, ET C'EST MESURÉ.**
Permuter `Passive_Ability_Type` ↔ `Effect_Type` dans la table du port laisse le bout-en-bout
**VERT** : le parseur du probe reconstruit l'`AbilityOrEffect` avec **la même table**, donc la
faute se compense. C'est exactement pourquoi `damage_voie_source` permute la table du **PORT
seul** — et elle rougit 9 / 9 sur son domaine. Le cliquet offline fige en plus la table
elle-même.

## 5. Le REFUS a changé de porte — la partition juge aussi la SOURCE

Le symbole d'une forme ne suffit pas à dire qu'elle est portée. `_formes` ne lit que le
`Group=` / `Action=` / `Tag=` ; le `Source=`, lui, est une chaîne que l'émetteur natif tire d'un
enum, et le port ne sait la reproduire que si son mirror porte le membre.

**Mesuré le 2026-08-06** : sur `C1_02` à six tours, un
`Group=Ability_Power Source=TerminatorArmour_Visual` a fait **LEVER** l'émission au milieu de la
mesure — le probe rend `2` et ne publie plus rien. `formes_etrangeres` juge désormais **deux
axes**, tous deux dérivés du port : la forme, et la résolubilité du `Source=`. Le sous-arbre part
hors périmètre, **énuméré**, et la mesure continue. Le cran du dessous est conservé : l'émission
lève toujours si un appelant court-circuite la partition — les deux sont gardés par
`test_477r21_activation_tree_offline.py`.

## 6. Ce qui n'est PAS couvert

- **La DÉCISION qu'un coup produise un `Group=Damage`** : elle vit dans le pipeline de dégât
  amont (`ADamageOperation$$ExecuteHit` et ses dérivés `AttackDamageOperation` /
  `AbilityDamageOperation`), qui n'est pas une face stream. L'appelant appelle — ou n'appelle pas ;
- **tout le calcul du dégât** : `DamageAppliedResult` est une entrée, comme les quatre valeurs
  d'état ECS (`remaining_health`, `remaining_armor`, `total_shield`, `number_of_members`) ;
- **les AUTRES groupes du pipeline** : `GroupType.MachineDamage` (28), `DamageChain` (29),
  `TileDamage` (27), qui sortent d'opérations distinctes — `MachineDamageOperation$$ExecuteHit`
  a son propre helper (`GetMachineHitTags`) ;
- **la branche `caster == null`** d'`Attacker_Id` : 72 / 72 des `Group=Damage` observés portent
  un attaquant. Portée, gardée offline, **NON EXERCÉE** live ;
- **le retour anticipé sur source vide** (§ 1.2 (d)) : même statut ;
- **deux voies sur six** des cascades : `Additional_Hit_ActiveAbility_Source` n'apparaît nulle
  part dans le corpus, et `Additional_Hit_TriggeredAbility_Source` seulement sur `C1_02` à six
  tours (1 occurrence), hors du corpus livré. Publiées en ATTENTION par le probe ;
- **`Attack_DidCrit` / `DidBlock` / `DidEvade`** valent `0` sur les 61 groupes : le régime à une
  seule valeur ne sépare pas les trois clés par l'égalité brute — seule la contre-épreuve les
  sépare (le test offline les exerce une à une).

## Résidus

- **#477-r38** — **la famille `Group=ResurrectUnit` / `Ability_CustomGroup`**, l'autre moitié de
  `#477-r34` : **106 lignes** sur `MC1_67` à deux tours, avec `Action=Resurrect`,
  `Action=DirectlyKillUnit`, `Action=RemoveUnit`, `Action=RemoveUnitFromTiles`. Elle sort du
  pipeline de RÉSURRECTION, qui a sa propre tranche. Le probe publie désormais la liste
  **complète** des formes qui la retiennent (23 formes, dont 20 `Tag=`).
- **#477-r39** — **`Action=HealInfo`, le pipeline de SOIN.** Neuf lignes qui en retiennent
  quarante-sept sur le roster 2v2 (`Group=Ability_Power Source=MedicusMinistorum` →
  `Action=HealInfo` + `Tag=Caster_Id` / `UnitStats_WasWoundedBeforeHeal` /
  `UnitStats_RemovedNegativeUnitEffects` / `UnitStats_RemainingHealth` /
  `UnitStats_NumberOfMembers` / `Amount`). **36** des 47 lignes sont déjà reproduites par le
  foyer de `#477-r34` : c'est la règle du sous-arbre qui les retient, pas le port.
- **#477-r40** — **le `Group=Ability_Power` dont le `Source=` est un `EffectType`.**
  `evaluate_trigger.py` porte `EvaluateTriggerOperation$$EvaluateAbilityTrigger`, qui écrit
  `((TriggeredAbilityType)order).ToString()`. Or `EvaluateTriggerOperation$$ExecuteInternal`
  appelle `EvaluateAbilityOrEffectTrigger` — le nom dit « **Ability OR Effect** » —, et le flux
  montre `Source=TerminatorArmour_Visual` / `TerminatorArmour_ReduceDmg`, deux membres
  d'`EffectType`. La seconde branche n'est pas portée. Elle retient **36 lignes** sur `C1_02` à
  six tours, déjà reproduites par le foyer de `#477-r34`.
