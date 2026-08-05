# #477-r18 — le périmètre du DÉROULÉ DE BATAILLE dans le flux de replay

**INVENTAIRE, rien de porté.** Build `rnca9r7q6c`, ghidra-mcp sur le binaire installé, session Frida
**9**.

```powershell
python scripts/python/probe_477r18_deroule_perimetre.py --json 477r18-carte.json
python scripts/python/probe_477r18_deroule_perimetre.py --flux-live --board C1_02 --tours 2
```

Volet **statique** : dérive le périmètre du binaire (cache disque sous `logs/477r18-decompile/` —
le premier run décompile ~840 corps, les suivants sont immédiats). Volet **live** : monte un
runner, joue N tours d'IA, ventile le flux natif par groupe racine, le conserve sous
`logs/477r18-flux-<board>.txt`, dispose dans le `finally`. **Les chiffres ci-dessous se
re-dérivent — ne pas les citer.**

## Verdict en une ligne

Le déroulé n'est **pas** un chantier de mécanique — elle est déjà portée. C'est un chantier
d'**ANCRAGE** : les 15 groupes RACINES sont tous ouverts par `IdunBattle.Messages.InputMessageProcessor`,
la seule couche du chemin qui n'existe **nulle part** dans `engine/`. Et la première tranche est
**`User_PlaceUnit`** : **10,1 %** du flux pour **+1 `GroupType`, +0 `StepType`, +0 `TagKey`**.

## 1. Le périmètre, dérivé — trois canaux, aucun énuméré à la main

L'émetteur natif est `IdunBattle.Streams.IStreamListener` (slots **0/1/2** =
`StartGroup`/`FinishGroup`/`Action`). En IL2CPP l'appel passe par un helper
`FUN_*(<slot>, <Il2CppClass* de l'interface>, <this>, <args…>)` : le probe **dérive** ce
`Il2CppClass*` de deux témoins et refuse de continuer s'ils ne concordent pas.

| canal | ce qu'il rend |
|---|---|
| **1** — xrefs du `Il2CppClass*` de `IStreamListener` | **386** sites, **133** fonctions productrices |
| **2** — xrefs de `IdunBattle.Core.AOperation$$get_Events` (indépendant) | **77** fonctions, **toutes** incluses dans le canal 1 ; 56 en plus côté canal 1 |
| **3** — méthodes dont la **signature** déclare le type (lu dans `frida/methods.tsv`) | **32** porteuses de `GroupType` / **20** de `StepType`, **879** sites, **818** littéraux lus |

| enum | atteint par un producteur LU | sans aucun producteur |
|---|---:|---:|
| `GroupType` | **86 / 104** | 18 |
| `StepType` | **59 / 62** | 3 (`None_`, `ExtraAttackDamage`, `LootInfo`) |
| `TagKey` | **131 / 244** | 113 |

**Les `GroupType` que le canal 1 ne voit pas ne sont pas morts — ils sont DÉCLARATIFS.** Ils ne
passent par aucun call-site du flux : une ability les pousse au nœud DSL
`IdunBattleLogic.Entities.DSLBehaviors$$AtomicGroup(groupType, …)`. Témoin lu :
`IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour` passe
`0x4e` = `GroupType.FrenziedFiring`. Le canal 3 en récupère **50** à lui seul (**36 → 86**).

**18 `GroupType` restent sans aucun producteur** sur les trois canaux — candidats dead code, **pas**
une preuve de mort : `None_`, `Ability_Attack`, `Attack`, `DarkDragon`, `AnvilShieldBlock`,
`Drachnyen_AtomicGroup`, `DrachnyenNormalAttack_AtomicGroup`, et onze noms qui n'évoquent aucun kit
Tacticus (`HornOfDespair_*`, `SummonIceElemental_Spawn`, `AirshipStrike_Attack`, `EjectEject`,
`MechRepair`, `RocketBarrage`, `Zinger`, `ZingerAbility`, `VolatileRockets`).

### Trois pièges de mesure, tous trouvés en rougissant

1. **Un nom AMBIGU rend un corps vide, sans erreur.** `InputMessageProcessor$$Visit` a **37**
   surcharges, `DSLBehaviors$$AtomicGroup` **3** : `decompile_function` et `list_xrefs` par nom
   échouent, et la sortie se lit « non décompilable » / « 0 appelant ». Le probe interroge par
   **adresse**, une par surcharge — **39** corps ainsi récupérés, dont les **3** de
   `UnitExtensions$$GetFullStateUpdateTags` qui valaient à elles seules **15** `TagKey`.
2. **Ghidra caste les littéraux** (`(void *)0x4e`) autant qu'il les écrit nus. Sans décapsulage, le
   canal 3 rendait **657 sites et 0 littéral** — un zéro produit par le parseur, pas par le binaire.
3. **L'appel d'interface a DEUX formes.** Quand Ghidra sort la résolution de slot de l'appel
   (`p = FUN_…(this, <DAT>, <slot>); (*(code *)*p)(this, 0x37, …)`), le motif du canal 1 ne mord
   plus : `AddOrUpdateShield` et `RemoveShield` — **tous deux observés dans le flux live** —
   sortaient « sans producteur ».

**Ce que la mesure ne voit toujours pas**, imprimé à chaque run : les arguments portés par une
variable (propagés d'**un** cran, pas plus), les porteurs sans symbole Ghidra.

## 1bis. La contre-épreuve — le statique ne se juge pas lui-même

Tout ce que le flux natif **émet** doit avoir été **atteint** par le balayage. Sur les deux flux
témoins : `GroupType` **0** manquant, `StepType` **0**, `TagKey` **9** — les tags de
**modification** de stat (`UnitStats_*_Modification[_Change|_Entity]`), `Attack_Weapon_IsMelee`,
`Attack_Weapon_DamageProfile`, `Custom_Data`. C'est ce contrôle qui a trouvé les pièges 1 et 3
ci-dessus ; les 9 restants sont le résidu `#477-r18-r4`.

## 2. La structure : un groupe RACINE = un message d'entrée

Les 15 `System_*` / `User_*` sont ouverts par les lambdas de
`IdunBattle.Messages.InputMessageProcessor$$Visit` — **15 sur 15** ont leur producteur lu. Tout le
reste (`StartTurn`, `EndTurn`, `Damage`, `Effect_Refresh`, `Ability_Power`…) est ouvert par des
**Operations**.

Séquence mesurée d'une transition de tour, dans l'ordre :

```
User_EndTurn -> EndTurn -> Action=PrepareTurn (HORS groupe) -> StartTurn
```

⚠ **Une `Action=` existe à profondeur 0**, hors de tout groupe : `PrepareTurn` après chaque
`EndTurn`, `ChangeStats` après chaque `User_MoveUnit`. **29** lignes du flux témoin sont dans ce cas.

## 3. Le poids MESURÉ, et le classement qui en découle

`C1_02`, seed 777, 2 tours d'IA : **2 777** lignes, **116 459** octets, reproductible à l'octet.
Le déploiement déjà porté en représente **423** (15,2 %). « NOUVEAU » = ce que le groupe ajoute
au vocabulaire **déjà exercé par le déploiement**. **Deux boards** — un seul ne prouverait rien :
sur `MC1_67` (63 tuiles), le déploiement passe à **535** lignes sur **2 931**, mais
`User_PlaceUnit` reste à **281** lignes et **+1 / +0 / +0**.

| groupe racine | occ | lignes | NOUVEAU G/S/T | mécanique portée ? |
|---|---:|---:|---|---|
| `User_UseAbility` | 5 | 564 | +6 / +6 / +31 | oui (`active_ability.py`, `damage.py`) |
| `System_StartMatch` | 1 | 477 | +4 / +8 / +18 | partiel |
| `System_GameSetup` | 1 | 423 | — | **FAIT** |
| `User_MoveUnit` | 10 | 303 | +3 / +6 / +12 | oui (`movement.py`) |
| **`User_PlaceUnit`** | **5** | **281** | **+1 / +0 / +0** | **oui — c'est le MÊME `AddUnit` que le setup** |
| `StartTurn` | 4 | 274 | +3 / +6 / +7 | oui (`turnflow.py`) |
| `EndTurn` | 4 | 180 | +3 / +7 / +10 | oui (`turnflow.py`) |
| `System_ProcessDeaths` | 3 | 133 | +5 / +7 / +30 | oui (`damage.py`, `remove_unit.py`) |
| `Ability_Power` | 1 | 51 | +2 / +3 / +3 | oui (`effect_triggers.py`) |
| `User_EndTurn` | 2 | 50 | +2 / +2 / +2 | oui (`turnflow.py`) |
| `Effect_Refresh` | 1 | 6 | +1 / +2 / +1 | oui (`refresh_effects.py`) |
| `System_ProcessRemovals` | 3 | 6 | +1 / +0 / +0 | groupe **VIDE** |

**Le classement demandé** : la mécanique de **tous** les groupes du déroulé est déjà dans
`engine/` — sur les **133** producteurs natifs, **50** sont cités par leur symbole exact,
**19** par leur classe. Les **64** absents se ventilent en `IdunBattle.Operations` (**45**,
essentiellement hors combat : drafting, score, portes, territoire, réinforcements),
`InputMessageProcessor` (**10**, l'ancrage), `RefreshEffectsOperation` (**5** lambdas internes),
et 4 divers. Il n'y a **aucun** groupe du déroulé dont l'opération native serait à porter de zéro.

⚠ `Effect_Refresh` est le motif **transversal** : il apparaît imbriqué dans presque tous les
groupes racines. Le porter tôt paie partout.

## 4. `Source=` — tranché par le PRODUCTEUR, ni par le nom ni par le groupe

Sur le flux témoin : **68** valeurs distinctes, **67** non vides (le déploiement seul n'en montrait
que 8). **Toutes** tombent dans un mirror déjà présent — il n'y a **aucune** source orpheline.

| groupe | sources distinctes | ce que le producteur LIT |
|---|---:|---|
| `Effect_Refresh` | 39 | `EffectComponent.EffectType` **@0x58** — `IdunBattle.Operations.RefreshEffectsOperation$$GenerateEventGroup`, puis `System.Enum$$ToString` |
| `Ability_Power` | 31 | **TROIS producteurs, trois types** (ci-dessous) |
| `User_UseAbility` | 3 | l'`ActiveAbilityType` du cast |

⚠ **Le nom ne discrimine pas** : **12** des 31 sources d'`Ability_Power` sont des membres valides
de **plusieurs** enums à la fois (`Ambush`, `BigTarget`, `TeleportStrike`, `TerminatorArmour`…).
⚠ **Le groupe non plus** : `Ability_Power` est ouvert par **trois** producteurs distincts, et
chacun boxe un type différent —
`EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` lit `EffectComponent@0x58` (`EffectType`,
même `Il2CppClass*` que `RefreshEffectsOperation`), tandis que
`TriggerTriggeredAbilityOperation$$TriggerAbility` et
`EvaluateTriggerOperation$$EvaluateAbilityTrigger` boxent un **autre** `Il2CppClass*`, alimenté par
des porteurs nommés `abilityName` / `sortedTriggeredAbility` (`TriggeredAbilityType`).

⇒ **L'unité d'attribution est le SITE, pas le groupe.** Les mirrors existent tous
(`engine/entities/effect_type.py`, `active_ability_type.py`, `triggered_ability_type.py`) et
`format_enum_value` fait déjà le rendu : **`Source=` n'est un mur pour aucun groupe du déroulé** —
le travail est de lire, site par site, le champ que le producteur boxe.

## 5. Le flux ne nomme pas le kit — non bloquant pour COMPARER

`#477-r17` reste vrai : aucun `visualId`. Mais l'`Entity=` est un discriminant **exact** et le
port l'apparie déjà (`observeBattle.units[].squadId`, mesuré 5/5 par `#477-r15`). Conséquence
réelle : ça ne gêne pas l'**égalité**, seulement la **lecture d'un rapport de divergence**. La
parade est côté rapporteur (joindre l'appariement `Entity= -> unitId` déjà disponible), pas côté
émetteur.

## 6. La PREMIÈRE TRANCHE — `User_PlaceUnit`, et son critère écrit à l'avance

**Pourquoi elle** : son contenu est un `Group=AddUnit` **strictement identique** à celui que le
port émet déjà dans `System_GameSetup` (tranches A + D). Le seul manque est l'**enveloppe**.
Mesuré : **281 lignes** (10,1 % du flux) pour **+1 `GroupType`** et **aucun** `StepType` ni `TagKey`
nouveau. C'est le meilleur rapport lignes-gagnées / vocabulaire-neuf du tableau, d'un facteur
**deux** sur son suivant.

Forme exacte, lue au flux :

```
Group=User_PlaceUnit Entity=NO_ENTITY Source= InitialTarget=
    Group=AddUnit Entity=59 Source= InitialTarget=
        Action=AddUnit Entity=59            (6 tags, dont Unit_SpawnSource:5)
        Action=ChangeStats Entity=59        (16 tags)
        Action=ChangeAbility Entity=59      (x4)
    Finish_Group
Finish_Group
```

**Critère de réussite, écrit AVANT** :

1. sur `C1_02` **et** `MC1_67` (tailles différentes), les **5** groupes racines `User_PlaceUnit`
   sont reproduits à l'**égalité BRUTE** ligne à ligne ; registre de divergences **VIDE** ;
2. la borne (a) republiée montre `GroupType` **2 → 3 / 104**, `StepType` **6 / 62** et `TagKey`
   **36 / 244** **inchangés** — si l'un des deux derniers bouge, c'est que la tranche a débordé ;
3. contre-épreuve, chaque mutation devant **rougir** : enveloppe supprimée ; `Entity=` du groupe
   racine ≠ `NO_ENTITY` ; `Unit_SpawnSource` faux ; ordre des cinq unités inversé ;
4. ce qui n'est **PAS** couvert est nommé : la valeur de `Unit_SpawnSource` hors du montage
   `rl_duel build`, et le fait qu'un `User_PlaceUnit` de partie réelle puisse contenir autre chose
   qu'un `AddUnit`.

**Crans suivants, dans l'ordre du tableau** : `System_ProcessRemovals` (groupe vide, +1 `GroupType`,
prouve l'ancrage temporel sans aucune donnée), puis `Effect_Refresh` (motif transversal, +1/+2/+1),
puis `User_EndTurn` (+2/+2/+2), qui l'englobe.

## Résidus

- **#477-r18-r1** — **le troisième `Il2CppClass*` boxé par `EvaluateTriggerOperation$$EvaluateAbilityTrigger`
  n'est pas nommé.** Cette fonction fait **trois** `Enum.ToString` sur **deux** types différents ; le
  second n'a été rattaché à aucun mirror. Condition de retournement : nommer ce `Il2CppClass*` (par
  un autre site qui l'initialise et appelle une méthode de la classe), puis vérifier que les sources
  qu'il produit sont bien celles du flux.
- **#477-r18-r2** — **`GroupType.Ability_CustomGroup` et `Ability_AtomicGroup` ne sont ouverts par
  aucun producteur nommable** : `IdunBattle.Operations.AtomicGroupOperation$$Execute` les reçoit en
  **paramètre**, et son unique appelant `Core.Services.OperationProcessor$$CreateAtomicGroup` le
  reçoit lui aussi — la propagation d'un cran s'arrête là. Condition de retournement : remonter le
  deuxième cran (les appelants de `CreateAtomicGroup`, atteignables seulement par le
  `Il2CppClass*` de son interface) et vérifier que les littéraux trouvés sont ceux du flux.
- **#477-r18-r3** — **18 `GroupType` sans aucun producteur, sur trois canaux.** Onze d'entre eux ne
  correspondent à aucun kit Tacticus (`HornOfDespair_*`, `Zinger`, `MechRepair`, `EjectEject`,
  `RocketBarrage`, `VolatileRockets`, `SummonIceElemental_Spawn`, `AirshipStrike_Attack`) : dead
  code hérité, **probable et non démontré**. Condition de retournement : chercher chacun comme
  immédiat dans le code machine (pas dans le pseudo-C), et pour les quatre génériques
  (`Ability_Attack`, `Attack`, `DarkDragon`, `AnvilShieldBlock`) établir s'ils passent par un champ
  écrit ailleurs qu'à un call-site.
- **#477-r18-r4** — **9 `TagKey` ÉMIS par le flux mais non atteints par le balayage** : les tags de
  modification de stat (`UnitStats_{FixedArmor,Movement}_Modification[_Change|_Entity]`),
  `Attack_Weapon_IsMelee`, `Attack_Weapon_DamageProfile`, `Custom_Data`. Leur producteur n'est ni
  dans les 133, ni dans les 11 fabriques balayées. Condition de retournement : partir du flux
  (`Action=` qui les porte), remonter à l'opération, et vérifier que l'étape [8] du probe retombe
  à zéro.
