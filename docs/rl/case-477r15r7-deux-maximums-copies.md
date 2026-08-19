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

## 6. CE QUI A ÉTÉ MESURÉ — et ce que la prédiction a tenu

### 6.1 La barre du tri-état : les deux probes REFUSENT, ils ne se replient pas

```
probe_477r15a_stream_conformance.py  --boards C1_02
    rc=2  « combatSnapshot ne publie pas `armorMax` de l'unite 49 -- capteur #477-r15-r7 absent »
probe_477r15r7_max_discrimine.py     --tours 1
    rc=2  « combatSnapshot ne publie pas `armorMax` -- capteur #477-r15-r7 absent »
```

Effet de bord **utile** de cette mesure : le probe est allé jusqu'à `armorMax`, donc
`numberOfMembersMax` (r5) et `actives[].state` (r6) **sont dans le bundle chargé**. La fenêtre
précédente a bien eu lieu, et **la moitié santé est confrontable sans en attendre une nouvelle**.

### 6.2 SANTÉ — le canal DISCRIMINE, mesuré

```
probe_477r15r7_max_discrimine.py --sans-armure --tours 12
    SANTE  DISCRIMINE : 13 observation(s)
        tour 1  entite 83  effectif=9015  brut=6023  (delta +2992)
        tour 3  entite 85  effectif=10018 brut=7026  (delta +2992)
    temoins : 29 entites vues avec les deux lectures, dont 10 a valeur non nulle
```

`combatSnapshot.healthMax` **n'est pas un alias** d'`observeBattle.hpMax`. Le `+2992` est
exactement le delta que `engine/ai/context.py` citait de mémoire (`TwistedScience` sur u87) —
re-mesuré ici de première main, sur deux entités.

⚠ **Les écarts commencent au tour 1, pas au tour 0** : au déploiement les deux lectures sont
égales, ce qui **confirme la prédiction** pour le groupe `System_GameSetup`.

### 6.3 Le flux — la prédiction tenue, sur 3 corpus

| corpus | résultat | témoin santé non nulle | témoin armure non nulle |
|---|---|---|---|
| `C1_02` (défaut, 1 unité) | conforme **204/204**, 0 NOUVELLE | 1/1 | **0/1** |
| `MC1_67` (défaut, 1 unité) | conforme **316/316**, 0 NOUVELLE | 1/1 | **0/1** |
| `MC1_67`, 4 kits adverses, `--armor-target 350` | conforme **464/464**, 0 NOUVELLE | 4/4 | **4/4** |

Les deux premières lignes sont mesurées avec l'armure encore copiée (patch **temporaire, non
commité** — le bundle chargé n'a pas le capteur) ; la santé, elle, est **mesurée** dans les trois.

### 6.4 LE TÉMOIN VIDE ÉTAIT RÉEL — et `--armor-target` le lève

Sans montage, `UnitStats_MaxArmor` vaut **0 sur toute unité du corpus** : l'égalité du flux y
compare **deux zéros** et ne teste aucun canal. La cause est mesurée — le `A` des kits
(`unit_map`) est `StatType.FixedArmor` (16), un `StatComponent` ; le pool d'armure
`StatType.Armor` (4) est bien « en pratique absent » des unités régulières.

`rl_duel build --armor-target N` force `Armor` + `FixedArmor` des **a-units**, c'est-à-dire
exactement celles que `SetupGameOperation$$AddPredefinedUnits` pose dans ce groupe. Le probe
l'expose (`--armor-target`), et **le témoin passe de 0/1 à 4/4** — l'accord porte alors sur une
vraie valeur (350). Le probe **imprime son témoin vide** quand le montage n'est pas joué.

### 6.5 Une piste ÉLIMINÉE, et pourquoi elle est retirée du code

`rl_duel build --unit-modifier <unit>:hp:<n>` passe par le point d'entrée natif
`BC.UnitModifiers` → `IdunBattle.Operations.SetupGameOperation$$ApplyModifiers` et produit de
**vrais** `StatModifier` — c'était le candidat pour poser une `Modification(+0x28)` **dès le
déploiement**, donc pour séparer les deux lectures **dans le flux lui-même**. Mesuré :

- le flux reste **conforme 312/312** avec le port d'AVANT la tranche (les deux max copiés) ;
- et la sonde dit pourquoi : `blackTerminator:hp:1000` fait **DISPARAÎTRE l'unité du
  déploiement** (3 unités sans le modificateur, 2 avec). Le levier ne fait pas ce qu'on
  attendait de lui.

L'option a donc été **retirée du probe** : livrer un `--unit-modifier` accompagné d'un
commentaire affirmant qu'il pose une `Modification(+0x28)` aurait écrit une **fausse vérité
invérifiable**. Ce que ce paragraphe garde, c'est la piste et sa réfutation.

⚠ **Ce que cela laisse ouvert** : séparer les deux lectures **dans le groupe `System_GameSetup`**
reste non atteint. Ce n'est pas une limite du canal — c'est une propriété du **régime**, la même
que pour les membres (#477-r15-r5) : le déploiement précède toute opération, donc
`Modification(+0x28)` y est nul par construction. La discrimination se mesure **en cours de
bataille**, et elle l'est (§6.2) pour la santé.

### 6.6 Ce que les cliquets ont prouvé sur EUX-MÊMES

- `probe_477r15r4_capteurs_offline.py` : **5 mutations réelles, 5 détectées**, arbre restauré —
  `armor` retiré de `STAT_IDS_MAX_SEUL` ; ordinal `armor: 5` ; `armor` ajouté à
  `COMBAT_STAT_IDS` ; copie `hpMax` revenue ; canal `armorMax` cessant d'être consommé.
- `tests/engine/test_477r15_stream_emitter_offline.py` : **2 mutations, 2 détectées**
  (`MaxArmor` figé à 0 ; `MaxHealth` copiant `init_remaining_health` — le vice réparé).
- Le bras **`MOTIFS_REQUIS_LIVE`** est neuf et comble un trou de forme : un motif *interdit*
  prouve que la copie a **disparu**, jamais qu'un **canal la remplace**. Le port pourrait cesser
  de lire `hpMax` sans lire `healthMax` pour autant.

### 6.7 Non-régression

Périmètre réel du changement : **aucun fichier `engine/**` du moteur** n'est touché (seulement
`tests/engine/`). Le rayon de souffle qui inquiétait #477-r15-r4 — `COMBAT_STAT_IDS` publiée sous
`statTypes`, itérée par `seed_unit_stats` — est **structurellement évité** ici par la table
séparée. `test_getstat_live.py` (le lecteur de `statTypes`) + la garde offline : **50 passed**.

## Résidus

- **#477-r15-r7 — NON CONFRONTÉ EN LIVE côté ARMURE : fenêtre de reinject requise.** Le code est
  écrit, bundlé (`frida-compile` rc=0) et gardé offline. Liste exécutable en §7.
- **La moitié SANTÉ ne demande aucune fenêtre** et est livrée telle quelle.
- **`entity_type` posé en dur** par le probe (cf. §3) : `combatSnapshot.entityType` le mesurerait.
  Non numéroté — à ouvrir via `probe_468_collision_numeros.py --suggere 477` si l'orchestrateur
  veut le traiter.
- **Aucun vecteur connu ne modifie le MAX d'ARMURE** : `--armor-target` écrit le champ brut, donc
  il lève le témoin vide mais **ne discrimine pas** ; `--unit-modifier` ne dispatche pas `armor`
  (§5, §6.5). Le canal reste le mirror 1:1 de l'accesseur natif — c'est établi au décompilé par
  identité de pointeur (§1) — mais **sa discrimination live n'est pas atteinte**, et le probe le
  rend en `NON DISCRIMINE` avec ses témoins, jamais en vert.

## 7. Ce qu'il faut jouer dans la fenêtre

```powershell
# 0. AVANT le reinject -- doit deja etre VERT (aucune session requise)
python scripts/python/probe_477r15r4_capteurs_offline.py
#    attendu : rc=0, 21 cles comparees, 9/9 copies attrapees sur temoin, 10 TagKey compares
python -m pytest tests/engine/test_477r15_stream_emitter_offline.py -q     # 49 passed

# 1. reinject + amorce (orchestrateur)   ... puis :

# 2. LA mesure : le dernier tag cesse d'etre copie
python scripts/python/probe_477r15a_stream_conformance.py
#    attendu : C1_02 204/204, MC1_67 316/316, 0 NOUVELLE, borne (c) = 2 entrees,
#              "REGIME MAXIMUMS ... sante 1/1, armure 1/1"
#              "valeurs NON NULLES : sante 1/1, armure 0/1" + le "! TEMOIN VIDE" sur l'armure
#    rc=2 + "capteur #477-r15-r7 absent" => le bundle n'a pas ete recharge

# 3. LE MONTAGE QUI LEVE LE TEMOIN VIDE -- sans lui l'accord sur `MaxArmor` compare deux zeros
python scripts/python/probe_477r15a_stream_conformance.py --boards MC1_67 --armor-target 350 `
    --p-units astraBullgryn,ultraInceptorSgt `
    --a-units adeptRetributor,admecDestroyer,astraOrdnance,blackTerminator
#    attendu : conforme 464/464, 0 NOUVELLE, "valeurs NON NULLES : sante 4/4, armure 4/4",
#              AUCUN "! TEMOIN VIDE"
#    (mesure de reference prise AVANT la fenetre, armure encore copiee : 464/464. Si le chiffre
#     change apres le rechargement, l'ecart accuse le capteur `armorMax`.)

# 4. discrimination des DEUX maximums (verdict a 3 etats PAR GRANDEUR)
python scripts/python/probe_477r15r7_max_discrimine.py --tours 12
#    attendu : SANTE DISCRIMINE (deja mesure AVANT la fenetre : 13 obs, delta +2992)
#              ARMURE NON DISCRIMINE -- corpus incapable (armure nulle). C'est un RESULTAT.
#    rc=3 est donc l'attendu ; rc=0 signifierait qu'un vecteur d'armure existe -> le NOMMER.

# 5. NON-REGRESSION : le lecteur de `statTypes`, que la table SEPAREE doit laisser intact
python -m pytest tests/engine/test_getstat_live.py -q        # reference AVANT fenetre : vert
```
