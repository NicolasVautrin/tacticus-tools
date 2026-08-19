# #477-r15-r4 / -r5 / -r6 — les trois grandeurs que l'émetteur COPIAIT de l'oracle

**Build** `rnca9r7q6c`. RE au décompilé (ghidra-mcp). Code : `frida/hooks/features/ai-step/rpc-snapshot.ts`,
`scripts/python/probe_477r15a_stream_conformance.py`. Probes neufs :
`probe_477r15r4_capteurs_offline.py`, `probe_477r15r5_membres_discrimine.py`. Garde :
`tests/engine/test_477r15_stream_emitter_offline.py`.

## Verdict en une ligne

Les trois entrées de la borne (c) ont un **canal**, et chacun est le **mirror 1:1 de l'accesseur
natif** — pas une approximation choisie pour coïncider. Le code est écrit, bundlé et gardé
offline ; **la confrontation live attend une fenêtre de reinject** (le code vit dans
`frida/hooks/*`).

## 1. Ce que le décompilé dit, et qui n'était écrit nulle part

Trois lectures ont été établies de première main. Les deux premières sont ce qui rend les remèdes
**exacts** au lieu de plausibles.

### `StatComponent$$GetStatPart` : `case 0` **ET** `case 2` rendent `get_CurrentValue`

```
IdunBattle.Entities.Components.StatComponent$$GetStatPart(this, statPart, entityId)
    case 0 (Current) :  -> get_CurrentValue(this)
    case 2 (Maximum) :  -> get_CurrentValue(this)      // le MEME appel
    case 3 (Initial) :  -> *(int*)(this+0x48)
```

Donc `GetStat(unit, StatType.Range, StatPart.Current)` **est** l'appel que fait la ligne du tag
`UnitStats_Range` — `StatComponent$$get_CurrentValue` du composant `Range`. Rien à convertir.

### `FillUpStatComponent$$GetStatPart` : les deux tags des membres y sont **côte à côte**

```
IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart(this, statPart, entityId)
    case 0 (Current) :  -> *(int*)(this+0x18)                    // RemainingValue  = InitAliveMembers (4)
    case 2 (Maximum) :  -> get_CurrentMaximumValue(this)         //                 = MaxMembers      (17)
    case 4 (Missing) :  -> get_CurrentMaximumValue(this) - (this+0x18)
```

C'est la mesure décisive : le canal existant (`StatPart.Current`) était **exactement** le bon pour
`InitAliveMembers` et **exactement** le mauvais pour `MaxMembers`. Ajouter `StatPart.Maximum` ne
choisit pas une valeur « proche » — il appelle la fonction que le tag appelle.

### `ActiveAbility$$.ctor` : l'état NEUF, lu plutôt que supposé

```
IdunBattle.Entities.Components.ActiveAbility$$.ctor(this, activeAbilityType, abilityState, abilityHierarchy)
    this.<CanStillBeUsed +0x28> = 1
    this.<RemainingCooldownTurns +0x2c> = Nullable<int>()      // VIDE -> GetValueOrDefault = 0
    this.<HasEnoughAmmo +0x40> = 1
    // IsDisabled (+0x35) et AmmoCost (+0x38) ne sont PAS ecrits -> zero de l'allocation
```

Le port posait `usable=True / cooldown=None / disabled=False` pour l'entrée d'attaque normale : ces
défauts étaient **justes**, et on le sait maintenant par le ctor, pas par la chance. Ce qui manquait
n'était pas la valeur, c'était la **mesure**.

### L'appariement composant → `StatType` est prouvé par IDENTITÉ DE POINTEUR

`UnitExtensions$$GetStatComponent` `case 2` et la ligne du tag `UnitStats_Range` dans
`UnitExtensions$$GetFullStateUpdateTags(unit)` chargent **le même pointeur de classe** et **le même
`MethodInfo*` de `GetComponent<T>`**. Idem `case 0`/`Attack`, `case 1`/`Movement`, `case 0x10`/
`FixedArmor`. Ce n'est pas déduit du nom — c'est la même paire d'opérandes dans les deux décompilés.

## 2. Les trois capteurs

| résidu | canal ajouté | mirror de |
|---|---|---|
| `#477-r15-r4` | `COMBAT_STAT_IDS.range = 2` → `combatSnapshot.stats.range` | `StatComponent$$get_CurrentValue` du composant `StatType.Range` |
| `#477-r15-r5` | `combatSnapshot.numberOfMembersMax` (`StatPart.Maximum`) | `FillUpStatComponent$$get_CurrentMaximumValue()` |
| `#477-r15-r6` | `unitAbilityStates.actives[].state` = `readAbilityState(inst)` | les cinq champs que lit `GetFullStateUpdateTags(activeAbility)` |

⚠ **`state` est un SOUS-OBJET, pas un spread**, et c'est fonctionnel : `state.level` /
`state.multiplier` sont `ActiveAbility$$get_AbilityState()` (**l'override prime**) — ce que le natif
écrit dans les tags 24/25 — tandis que `level` / `mult` restent le champ **brut** `_abilityState`.
Les fusionner sous un même nom rendrait indiscernables deux lectures distinctes, et écraserait le
contrat des lecteurs existants de `unitAbilityStates`.

⚠ **Le probe lit désormais `state.level`, pas `level`.** C'était une **septième copie silencieuse** :
le port émettait le champ brut là où le natif émet l'accesseur. Les deux coïncident tant qu'aucun
override n'existe (`overrideRaw` le publie), donc rien ne l'aurait montré.

⚠ **`GetStat` refuse `StatType.Range` sur une Machine of War** — ce `StatType` est dans la liste du
switch qui exige `entity.Type == EntityType.Unit`. Le capteur rend alors `null` = PAS MESURÉ, pas
`0`.

## 3. Ce qui remplace chaque entrée retirée de la borne (c)

Une borne qui rétrécit sans que rien ne soit mesuré est un mensonge. Elle passe de **5** à **3**
entrées, et **une entrée jusqu'ici TUE y entre** :

- retirées : `UnitStats_Range`, `UnitStats_MaxMembers`, les trois tags d'état de l'attaque normale —
  chacune remplacée par le canal du tableau ci-dessus, nommé dans le libellé du rapport ;
- **ajoutée** : `UnitStats_{MaxHealth,MaxArmor}`, lus au champ brut `MaximumValue@0x14`
  (`observeBattle`) là où le natif appelle `get_CurrentMaximumValue()`. La fiche parente le disait en
  prose ; ce n'était **pas** dans la borne. Le capteur `combatSnapshot.healthMax` (`StatPart.Maximum`)
  **existe déjà** et fermerait la moitié de cette entrée ; l'armure n'a **aucun** canal (son composant
  n'est atteignable ni par `GetStatComponent` ni par `GetStat` — aucun `case` ne charge son pointeur
  de classe). Hors périmètre de cette tranche, donc **déclaré**.

## 4. Le piège de `r5` : le régime, pas le canal

**`UnitStats_MaxMembers` et `UnitStats_InitAliveMembers` ne peuvent PAS être séparés par le flux de
`System_GameSetup`.** Au déploiement aucun membre n'est mort et aucune modification n'est posée, donc
`RemainingValue == get_CurrentMaximumValue()`. Ce n'est pas une limite du capteur : c'est une
propriété du régime. Aucun canal ne la lèvera.

Ce qui **est** atteignable, et qui est le cran du dessous : prouver que les deux canaux sont deux
**lectures distinctes**, qui se séparent dès que l'état les sépare. Sans cela,
`numberOfMembersMax` pourrait être un alias et l'accord resterait vert à l'identique.

**Le montage, dérivé du gameconfig** : **17** configurations portent `nrOfMembers > 1`, et **toutes**
sont `summons` ou `npc` — **aucun héros, aucune Machine of War**. La gate de confrontabilité tranche
alors par le summon : on l'amène par son **summoner**, et deux summoners sont **au pool** (vérifié
contre `rl_duel build --list-pool`) :

```
necroSpyder    (Aleph-Null)          --ScarabHive-->  necroSmnSwarm        (5 membres)
tyranParasite  (Parasite of Mortrex) --ItItches---->  tyranSmnRipperSwarm  (5 membres)
```

`probe_477r15r5_membres_discrimine.py` les met des deux côtés, laisse `aiPlayByUnit` jouer les deux
camps, et relit `courant` vs `maximum` à chaque tour. **Verdict à trois états** : `NON DISCRIMINÉ` est
un résultat rendu avec ses témoins (combien d'entités multi-membres vues, sur combien de tours), pas
un vert.

## 5. Le recoupement qui peut ROUGIR sans que le flux bouge

`decisionView` n'alimente plus le port — il devient un **recoupement**. Les deux canaux appellent la
même `readAbilityState`, donc il ne teste **pas** la lecture des champs ; il teste que les deux
chemins de **récupération d'instance** désignent les mêmes objets : `ActiveAbilityComponent$$GetActives`
d'un côté, le walk manuel de `Abilities@0x20` de l'autre. Si ce walk décalait d'un élément, le
recoupement rougirait alors que le flux resterait égal tant que les valeurs se ressemblent. Un écart
est donc un **ROUGE à part entière** (`rc=1`), et le compte d'actives **recoupées** est imprimé — un
zéro d'écarts sur zéro recoupée ne prouve rien, et le probe le dit.

## 6. PRÉDICTION, écrite AVANT la fenêtre

**Prédiction : `C1_02` reste 204/204 et `MC1_67` 316/316, avec 0 divergence nouvelle**, et le
raisonnement est décomposé par grandeur — pas une intuition globale.

| grandeur | pourquoi le flux ne doit pas bouger | ce qui la falsifierait |
|---|---|---|
| `UnitStats_Range` | le flux natif **porte déjà `0`** (le port émettait `0` et 204/204 étaient égales) ; le composant `Range` **existe** sur ces unités — sinon la cascade de gardes de `GetFullStateUpdateTags` serait tombée sur son thunk de levée au lieu d'émettre le tag. Donc `get_CurrentValue` **rend 0**, et `GetStat(.., Current)` est le même appel | `stats.range` non nul, ou `null` (⇒ `MesureImpossible`, pas une divergence) |
| `UnitStats_MaxMembers` | `RemainingValue == MaximumValue` au déploiement, modification et override nuls | `numberOfMembersMax != numberOfMembers` sur une unité du corpus — **ce serait une découverte**, et le tag l'aurait porté depuis toujours |
| les trois tags d'attaque normale | le ctor écrit `CanStillBeUsed=1`, un `Nullable` **vide** en cooldown, `IsDisabled` non écrit ; et le fragment natif figé porte bien `1 / 0 / 0` sur `Id:69` | un de ces trois champs déjà muté au déploiement — impossible sans opération intercalée |
| `state.level` / `state.multiplier` | `OverrideAbilityState` est vide au déploiement (`overrideRaw` le publie) | un override non vide ⇒ le port émettrait enfin la bonne valeur, et **le flux natif la portait déjà** |

**Une divergence serait un VRAI désaccord** jusqu'ici masqué par la copie — c'est le résultat
recherché, pas un échec. Le seul régime où le probe rend `2` (MESURE IMPOSSIBLE) est celui où le
bundle chargé est antérieur à la fenêtre : il le **nomme** au lieu de retomber sur un défaut.

## 7. Ce que la validation a trouvé, et qui n'était pas prévu

- **Deux bras de contre-épreuve n'avaient pas mordu** (`(?m)^…$` contre des CRLF) et rendaient un
  **VERT** sur un cliquet qu'ils étaient censés falsifier. Repassés en vérifiant la morsure : **5
  mutations, 5 détectées** (clé retirée, ordinal faux, canal retiré, `partBufMax` faux, `state`
  retiré), arbre restauré.
- **Le sélecteur de build maison rendait une ARCHIVE** (`gqfc5mff6c`) et comparait le hook à un enum
  périmé. Remplacé par le foyer unique `symbols_layout.current_build()`.
- **Un motif de non-régression rougissait sur sa propre explication** (`#477-r15-r4)` matchait le
  commentaire qui dit *pourquoi* la borne a rétréci). Un motif doit désigner l'**artefact**, jamais sa
  mention.
- **Trois caractères non-ASCII** dans le `print` de « montage incohérent » du probe live : il aurait
  levé `UnicodeEncodeError` sur la console cp1252 **au seul moment où il a quelque chose à dire**. Le
  `.replace` en place n'en couvrait qu'un sur trois.

## Résidus

- **#477-r15-r4/r5/r6 — NON CONFRONTÉS EN LIVE : fenêtre de reinject requise.** Le code est écrit,
  bundlé (`frida-compile` rc=0, **0** erreur TS sur `features/ai-step`) et gardé offline. La liste
  exécutable de la fenêtre est en §8 ci-dessous.
- **`UnitStats_{MaxHealth,MaxArmor}`** — entrés en borne (c) (cf. §3). `healthMax` existe déjà,
  l'armure n'a aucun canal. Non numérotés : à ouvrir via `probe_468_collision_numeros.py --suggere 477`
  si l'orchestrateur veut les traiter.
- **`UnitStats_TriggeredAbility_{AmmoCost,EnoughAmmo}`** — inchangé : `AmmoCost` est nul sur toute
  unité régulière ; les munitions ne mordent que sur les Machines of War, hors de ce groupe.

## 7bis. Le rayon de souffle de `COMBAT_STAT_IDS`, et pourquoi il ne se voit pas avant la fenêtre

`COMBAT_STAT_IDS` n'est pas seulement la table de `combatSnapshot` : elle est publiée sous
`statTypes`, et `engine/entities/stats.py::seed_unit_stats` **itère cette table** pour seeder un
`StatComponent` par entrée. Ajouter `range` ajoute donc un composant `StatType.RANGE` (initial `0`)
à chaque `UnitContext` reconstruit d'une capture live.

Mesuré, pas supposé : `_stat_min(2)` rend `0`, `STAT_CLAMP_MAX.get(2)` rend `None` (aucune levée) ;
et **aucun code d'`engine/` ne lit `StatType.RANGE`** — les seuls lecteurs de la famille visent
`StatType.EXTRA_RANGE` (24), qui était déjà dans la table. Le composant ajouté est donc **inerte**.

⚠ **Mais cet effet n'apparaît qu'APRÈS le rechargement du bundle** : tant que le RPC ne publie pas
`range`, `stats.get("range")` est `None` et `seed_unit_stats` fait `continue`. Aucun test joué avant
la fenêtre ne peut donc l'exercer — d'où le test de garde par dépendance en §8.

## 8. Ce qu'il faut jouer dans la fenêtre

```powershell
# 0. AVANT le reinject -- doit deja etre VERT (aucune session requise)
python scripts/python/probe_477r15r4_capteurs_offline.py
#    attendu : rc=0, 20 cles comparees, temoin 6/6 sur la contre-epreuve

# 1. reinject + amorce (orchestrateur)   ... puis :

# 2. LA mesure : les trois grandeurs cessent d'etre copiees
python scripts/python/probe_477r15a_stream_conformance.py
#    attendu : C1_02 204/204, MC1_67 316/316, 0 NOUVELLE, borne (c) = 3 entrees,
#              "RECOUPEMENT ... 0 ecart(s) sur N active(s) recoupee(s)" avec N > 0,
#              "REGIME MEMBRES ... k/k unite(s) ou courant == maximum"
#    rc=2 + "capteur #477-r15-r5/r6 absent" => le bundle n'a pas ete recharge

# 3. generalisation (4 kits adverses, board different) -- doit rester a 0 NOUVELLE
python scripts/python/probe_477r15a_stream_conformance.py --boards MC1_67 `
    --p-units astraBullgryn,ultraInceptorSgt `
    --a-units adeptRetributor,admecDestroyer,astraOrdnance,blackTerminator

# 4. sortie du regime degenere de r5 (verdict a 3 etats ; NON DISCRIMINE est un resultat)
python scripts/python/probe_477r15r5_membres_discrimine.py --tours 12
#    rc=0 DISCRIMINE / rc=3 NON DISCRIMINE (avec temoins) / rc=2 capteur absent

# 5. NON-REGRESSION par dependance : `COMBAT_STAT_IDS` alimente AUSSI `seed_unit_stats`, donc
#    l'ajout de `range` fait apparaitre un StatComponent de plus dans tout `UnitContext`
#    reconstruit d'une capture live. Inerte a la lecture (aucun lecteur de `StatType.RANGE`),
#    mais INEXERCABLE avant le rechargement du bundle -- c'est ici qu'on le voit.
python -m pytest tests/engine/test_damage_roll_live.py tests/engine/test_runner_attack_live.py -q

# 6. garde offline (rejouable a tout moment, aucune session requise)
python -m pytest tests/engine/test_477r15_stream_emitter_offline.py -q     # 46 passed
```
