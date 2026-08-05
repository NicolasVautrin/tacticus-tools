# #477-r15-r7 — les deux MAXIMUMS que l'émetteur de flux copiait

**Build** `rnca9r7q6c`. RE au décompilé (ghidra-mcp). Code : `frida/hooks/features/ai-step/rpc-snapshot.ts`,
`scripts/python/probe_477r15a_stream_conformance.py`. Probe neuf :
`probe_477r15r7_max_discrimine.py`. Cliquet étendu : `probe_477r15r4_capteurs_offline.py`.
Gardes : `tests/engine/test_477r15_stream_emitter_offline.py`.

## Verdict en une ligne

Les deux entrées ont un **canal**, et l'affirmation qui les bloquait était **fausse** : l'armure
n'est pas hors d'atteinte. La moitié **santé** se ferme **sans écrire un octet de capteur** ;
l'armure demande une fenêtre de reinject. Mais **l'accord ne prouvera rien** sur l'armure — elle
vaut **zéro** sur le corpus, et c'est mesuré, pas redouté.

## 1. Ce que le décompilé dit, et qui contredit la fiche parente

### `GetStatComponent` n'a pas de `case 4` — et cela ne conclut RIEN

La tranche précédente écrivait : « l'armure n'a **aucun** canal (son composant n'est atteignable
ni par `GetStatComponent` ni par `GetStat`) ». La première moitié est vraie, la seconde est
**fausse**, et l'erreur est un raisonnement par héritage : `IdunBattle.Entities.UnitExtensions$$GetStat`
**ne passe pas** par `IdunBattle.Entities.UnitExtensions$$GetStatComponent`.

```
GetStatComponent(unit, statType)      switch ECRIT, cases : 0 1 2 3 7 8 9 10 0xf 0x10 0x11
                                                            0x15 0x16 0x17 0x18 0x19 0x1a
                                      -> AUCUN case 4 (Armor), 5 (Health), 0x14 (NumberOfMembers)

GetStat(actor, statType, statPart, entityId)
    garde   : switch a DEUX listes -- {0,9,10,0xd,0xe,0x11,0x12,0x13,0x16,0x19,0x1a} accepte
              EntityType 1 ou 6 ; {1,2,3,4,5,7,8,0xc,0xf,0x10,0x14,0x15,0x17,0x18} exige 1 (Unit)
    dispatch : JUMPTABLE (28 entrees de 4 octets, RVA), pas un switch ecrit -- ghidra ne la
               recupere pas ("Could not recover jumptable ... Too many branches")
```

Les **trois** « fill-up » y sont donc bien couverts. C'est la même voie que `healthMax` (#45b') et
`numberOfMembersMax` (#477-r15-r5) empruntent **déjà** — leur existence aurait dû suffire à
réfuter l'affirmation.

### L'appariement composant → tag, prouvé par IDENTITÉ DE POINTEUR

Chaque entrée de la jumptable fait `mov r8,[rip+X]` (le `Il2CppClass*` de `T`) puis
`mov rcx,[rip+Y]` (le `MethodInfo*` de `GetComponent<T>`) avant d'appeler le `GetStatPart` du
composant. Les deux opérandes sont **les mêmes** que dans la ligne du tag correspondant de
`IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags(unit)` :

| `StatType` | classe de `T` | `MethodInfo*` | `GetStatPart` appelé | tag |
|---|---|---|---|---|
| `Health` (5) | `DAT_18332dbb8` | `DAT_1833c0830` | `FillUpStatComponent` | `UnitStats_MaxHealth` (9) |
| `Armor` (4) | `DAT_1833e3690` | `DAT_1833be6e0` | `FillUpStatComponent` | `UnitStats_MaxArmor` (13) |
| `NumberOfMembers` (0x14) | `DAT_183335c00` | `DAT_1833c0fe0` | `FillUpStatComponent` | `UnitStats_MaxMembers` (17) |
| `Range` (2) | `DAT_183377838` | `DAT_1833c1648` | `StatComponent` | `UnitStats_Range` (31) |

(Les `DAT_*` sont des slots de données du binaire, cités ici parce qu'ils sont l'**objet même**
de la preuve : c'est leur ÉGALITÉ entre deux décompilés qui apparie, pas un nom.)

### Ce que `get_CurrentMaximumValue()` calcule, relu

```
IdunBattle.Entities.Components.FillUpStatComponent$$get_CurrentMaximumValue(this)
    ov = ValueOverride$$GetOverrideValueWithModification(this+0x38, this.Modification@0x28)
    if (ov.HasValue) return ov.Value
    return MaximumValue(+0x14)
           + Math.Min(IntMax - Initial(+0x10),
                      Math.Max(-Initial(+0x10), Modification(+0x28)))
```

et le `GetStatPart` du même composant :

```
IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart(this, statPart, entityId)
    case 0 (Current)  : *(int*)(this+0x18)                          // RemainingValue BRUT
    case 2 (Maximum)  : get_CurrentMaximumValue(this)
    case 3 (Initial)  : *(int*)(this+0x10)
    case 4 (Missing)  : get_CurrentMaximumValue(this) - (this+0x18)
    case 7 (Override) : ValueOverride$$get_OverrideValue(this+0x38) ?? *(int*)(this+0x14)
```

⚠ **Le champ brut `MaximumValue@0x14` a lui aussi son `StatPart`** — c'est le `case 7`, dans sa
branche sans override. Ce que le port lisait n'était donc pas « une approximation » : c'était une
**troisième lecture**, celle d'`observeBattle` (`frida/hooks/game/match-state.ts::projectSquadStats`,
`comp.add(COMP_FIELD.hpMax).readS32()`).

## 2. Les deux canaux

| grandeur | canal | capteur neuf ? |
|---|---|---|
| `UnitStats_MaxHealth` (9) | `combatSnapshot.healthMax` = `GetStat(unit, StatType.Health, StatPart.Maximum)` | **non** — il existait depuis #45b'. Il suffisait de cesser de copier. |
| `UnitStats_MaxArmor` (13) | `combatSnapshot.armorMax` = `GetStat(unit, StatType.Armor, StatPart.Maximum)` | **oui** (#477-r15-r7) |

⚠ **`armor` vit dans `STAT_IDS_MAX_SEUL`, PAS dans `COMBAT_STAT_IDS`, et c'est fonctionnel.**
Cette dernière est publiée telle quelle sous `statTypes`, et `engine/entities/stats.py::seed_unit_stats`
l'**itère** pour matérialiser un `StatComponent` par entrée dans tout `UnitContext` reconstruit
d'une capture live. Or `StatType.Armor` est un `FillUpStatComponent`, pas un `StatComponent` : l'y
ajouter matérialiserait un composant de la **mauvaise famille**, et ne casserait **aucun test**.
Le cliquet garde les deux fautes (absente / du mauvais côté).

## 3. Ce qui remplace l'entrée retirée de la borne (c)

Elle passe de **3** à **2** entrées, et les deux remplaçants sont nommés dans le libellé même du
rapport : `MaxHealth` ← `combatSnapshot.healthMax`, `MaxArmor` ← `combatSnapshot.armorMax`.

**Rien n'entre en remplacement**, et c'est un résultat : après cette tranche, **aucune grandeur du
groupe `System_GameSetup` n'est plus prise du flux natif**. Les deux entrées restantes ne sont pas
des copies — `Tile_IsTerritory` est un tag qu'aucun board du corpus n'émet, `TriggeredAbility_
{AmmoCost,EnoughAmmo}` un tag qu'aucune unité du régime ne porte.

⚠ **Une hypothèse subsiste, et elle n'est pas une copie** : `entity_type` est posé à
`EntityType.Unit` **en dur** par le probe là où le natif lit `entity.Type`. Ce n'est pas pris du
flux (c'est une propriété du montage : les Machines of War passent par `AddMachineOperation`, hors
de ce groupe), et le flux la **confronte** — mais `combatSnapshot.entityType` existe et la
mesurerait. **Hors périmètre de cette tranche, donc DÉCLARÉ** (résidu ci-dessous).

## 4. PRÉDICTION, écrite AVANT la mesure

**Prédiction : `C1_02` reste 204/204 et `MC1_67` 316/316, 0 divergence nouvelle**, décomposée par
grandeur.

| grandeur | pourquoi le flux ne doit pas bouger | ce qui la falsifierait |
|---|---|---|
| `UnitStats_MaxHealth` | `get_CurrentMaximumValue()` = `MaximumValue@0x14` tant que `Modification@0x28` et l'override `+0x38` sont nuls — et rien n'est intercalé au déploiement | `healthMax != hpMax` sur une unité du corpus. **Ce serait une découverte**, et le flux natif portait déjà la bonne valeur : le port aurait alors DIVERGÉ avant ce commit, pas après |
| `UnitStats_MaxArmor` | même raison, **et plus fortement** : `max_armor` vaut **0** sur `thousTzaangor` (lu dans `ETAT_49`, corpus figé du test offline). Deux zéros | `armorMax` non nul ⇒ le corpus exerce enfin le tag ; `armorMax` à `null` ⇒ `MesureImpossible` (capteur absent), **pas** une divergence |
| témoin `max_armure_non_nuls` | **prédit à 0 sur les deux boards** — les unités régulières ne portent pas d'armure « fill-up » | un compte non nul : l'accord aurait alors une valeur, et cette ligne serait à réécrire |
| discrimination SANTÉ (`probe_477r15r7`) | **atteignable, non garantie** : `TwistedScience` doit être joué par l'IA. Verdict à 3 états | — (les trois états sont des résultats) |
| discrimination ARMURE | **prédit NON DISCRIMINÉ, corpus incapable** (armure nulle) | un écart ⇒ un vecteur de modification du max d'armure existe, et il faudra le nommer |

**Une divergence serait un VRAI désaccord** jusqu'ici masqué par la copie — c'est le résultat
recherché, pas un échec. Le seul régime où le probe rend `2` (MESURE IMPOSSIBLE) est celui où le
bundle chargé est antérieur à la fenêtre : il **nomme** alors le capteur absent.

## 5. Ce que la recherche du vecteur ARMURE a éliminé — et ce qui reste ouvert

Sortir du régime dégénéré exige `Modification@0x28 != 0` ou un override sur le composant
d'ARMURE. Pour la santé le vecteur est **nommé par son propre texte de kit** :
`TwistedScience` (`genesBiophagus`, **au pool**) — « *Affected units immediately gain 2183 Health
and **their maximum Health increases by the same amount*** », et l'écart avait déjà été mesuré
(`hpMax` 11044 vs `healthMax` 14036 sur u87, cité par `engine/ai/context.py`).

Pour l'armure, **aucun vecteur trouvé**. Ce qui a été éliminé, et ce qui reste ouvert, est imprimé
par `probe_477r15r7_max_discrimine.py` à chaque run (`PORTEE DE LA RECHERCHE`) :

- les **558** `statType` du gameconfig sont les **upgrades de méta-jeu** (`hp`/`dmg`/`fixedArmor`) —
  ce canal ne conclut **rien** sur les stat-modifiers de combat ;
- **aucun** site du port n'émet de `ChangeStat` sur `StatType.ARMOR` (4) ; les effets nommés
  `*_ExtraArmor` visent tous `StatType.FIXED_ARMOR` (16), qui est un `StatComponent` ;
- **RESTE OUVERT** : le port ne couvre qu'une partie des abilities natives — un `CreateBehaviour`
  non porté peut appeler `FillUpStatComponent$$ModifyMax`/`OverrideMax` sur l'armure sans que rien
  du dépôt ne le montre.

## Résidus

- **#477-r15-r7 — NON CONFRONTÉ EN LIVE côté ARMURE : fenêtre de reinject requise.** Le code est
  écrit, bundlé (`frida-compile` rc=0) et gardé offline. Liste exécutable en §7.
- **La moitié SANTÉ ne demande aucune fenêtre** et est livrée telle quelle.
- **`entity_type` posé en dur** par le probe (cf. §3) : `combatSnapshot.entityType` le mesurerait.
  Non numéroté — à ouvrir via `probe_468_collision_numeros.py --suggere 477` si l'orchestrateur
  veut le traiter.
