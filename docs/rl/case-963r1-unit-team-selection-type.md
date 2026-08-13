# #963-r1 — `AreEnemies`/`AreFriends` : le 3ᵉ argument existait, le nœud ne le portait pas

## 1. La question binaire, et sa réponse

**Combien de call-sites natifs passent `UnitTeamSelectionType.ByOriginalTeam` (`1`), et le port
en écarte-t-il qui devraient le lire ?**

| primitive | call-sites | `0` ByCurrentTeam | `1` ByOriginalTeam | INDÉTERMINÉ |
|---|---|---|---|---|
| `IdunBattleLogic.Entities.DSLTriggers$$AreEnemies` | **54** | 52 | **2** | 0 |
| `IdunBattleLogic.Entities.DSLTriggers$$AreFriends` | **79** | 77 | **2** | 0 |

Les **quatre** sites à `ByOriginalTeam`, par leur symbole :

| primitive | site | porté ? |
|---|---|---|
| `AreEnemies` | `…Triggered.Loki.RedRampage_BuffAbility$$CreateTrigger` | **OUI** |
| `AreEnemies` | `…Triggered.Loki.TheArdentBlade_TriggerAbility$$CreateTrigger` | non |
| `AreFriends` | `…Triggered.Loki.Reinforcements_DamageAbility$$CreateTrigger` | non |
| `AreFriends` | `…Triggered.Loki.TheWrathfulDeadAbility_Overkill$$CreateTrigger` | non |

⇒ **l'énoncé du résidu était JUSTE mais INCOMPLET** : il ne citait que `RedRampage`, et il y a
**quatre** sites, dont **un seul est porté**. C'est celui-là, et lui seul, qui était faux —
les 129 autres call-sites passent `0`, pour lesquels le comportement d'avant était déjà correct.

Bonus mesuré au passage, sur le **5ᵉ** argument d'`AreFriends` (`anyEntity`) : **77 × `0`, 2 × `1`**,
les deux dans `…Triggered.Loki.EnvAmbushResurrectAbility` (`$$GetIsAlliedWithCurrentPlayerUnitTrigger`
et `$$GetValidDecoys`). Aucun n'est porté. Ce flag choisit une **classe de trigger différente**
(`AreEntityFriendsAbilityTrigger` au lieu d'`AreFriendsAbilityTrigger`) ; le port ne le modélise pas.

## 2. La chaîne native, relue en entier

```
DSLTriggers.AreEnemies(dsl, sel1, sel2, selectionType)
    -> new AreFriendsAbilityTrigger(sel1, sel2, battleQuery, selectionType)   // champ +0x28
    -> AbilityTrigger.op_LogicalNot(<ce trigger>)                             // AreEnemies == !AreFriends

AreFriendsAbilityTrigger.ShouldTrigger(entities)
    a = <sel@+0x10>.SelectSingle(entities);  if (a == null) return false;
    b = <sel@+0x18>.SelectSingle(entities);  if (b == null) return false;
    return battleQuery.<slot 0x92>(a, b, <+0x28>)

BattleQuery.AreFriends(a, b, selectionType)
    -> UnitExtensions.IsFriend(a, b, selectionType, this.State) :
           if (selectionType == 0)  p = EntityExtensions.GetCurrentPlayer(...)    // ByCurrentTeam
           else if (== 1)           p = EntityExtensions.GetOriginalPlayer(...)   // ByOriginalTeam
           else                     return false;
           teamId = (p == null || p.<+0x20> == null) ? 0 : p.<+0x20>.<+0x24>;
           return teamId(a) == teamId(b);
```

`AreEnemies` **n'alloue pas de classe dédiée** — même trigger, enveloppé dans un `Not`. Les deux
branches ne diffèrent que sur une unité dont le propriétaire courant est surchargé
(`IdunBattle.Operations.ChangeUnitOwnerOperation$$Execute`, effet `1209
AttemptedPossession_Possessed`).

## 3. Ce qui a été porté

* **`entities/unit_team_selection_type.py`** — l'enum EXISTAIT déjà (et était déjà au registre de
  `probe_313`) ; ce qui manquait, c'est le **foyer** `team_for_selection(unit, selection_type)`,
  mirror de la seule bifurcation d'`IsFriend`.
* **`entities/triggers.py`** — `AreEnemies` / `AreFriends` prennent un 3ᵉ argument
  `selection_type`, **défaut `ByCurrentTeam`** (= les 129 sites), et lisent l'équipe par ce foyer.
* **`runner/abilities/behaviours/context.py`** — le dict d'unité publie **`originalTeam`**, dérivé
  d'`OwnerComponent.overridden_from` (le couple `(team, player)` d'origine, `None` hors possession).
* **`runner/operations/triggers/loki/red_rampage.py`** — la constante `TEAM_SELECTION`, **déjà
  déclarée mais jamais consommée**, est enfin passée au nœud.

## 4. Trois pièges rencontrés, chacun mesuré

**(a) `list_xrefs` est INCOMPLET.** Sur `AreFriends` il rend **39** sites ; l'image en porte **79**.
Un recensement qui s'y arrête ne peut pas montrer le site qu'il a oublié — et c'était exactement le
mode de panne que ce résidu demandait d'éviter. Sur `AreEnemies`, en revanche, la table était
**complète** (54/54) : l'incomplétude ne se généralise pas non plus.

**(b) Le pseudo-C REPLIE les registres.** Le décompilateur rend volontiers `0` là où l'argument vient
d'un registre mis à zéro plus haut — **8 sites** d'`AreFriends` alimentent leur 5ᵉ argument depuis un
registre (`sil`, `r12b`, `r13b`, `r15b`, `bl`). Le littéral affiché y est une **déduction du
décompilateur**, pas l'octet. Le probe remonte donc à la **définition** du registre dans la même
fonction, et rend `INDETERMINE` plutôt qu'une valeur devinée.

**(c) Le balayage doit viser la bonne SECTION.** Ancré sur `.text`, il rend **0 call-site** — un
recensement VIDE qui se lit comme « aucun site ne passe `1` ». Les 60 Mo de corps IL2CPP vivent dans
une section nommée **`il2cpp`**. Le probe dérive donc les sections de code par « contient-elle des
débuts de fonction de `functions.tsv` ? », jamais par un nom écrit en dur.

**(d) La paire de sélecteurs NE PRÉDIT PAS le drapeau.** Les deux sites `AreEnemies` à `1` comparent
`(DSLSelectors+0x30, +0x60)` — mais `BarbedOvipositor` et `CosmicHorror_OnKill` comparent la **même**
paire avec `0`. Aucune inférence depuis la forme de l'appel.

## 5. Comment re-dériver

```powershell
python scripts/python/probe_963r1_team_selection_callsites.py [--detail]
```

Balayage **exhaustif** du binaire (capstone, ancré sur `functions.tsv`), **sans ghidra-mcp** — qui
était HS pendant toute cette tranche. ~40 s. Trois mesures indépendantes (ce probe + deux agents
décodant les octets séparément) concordent site pour site.

Le cliquet est `tests/engine/test_963r1_unit_team_selection_offline.py` (étage 1 = le recensement
figé, `build: True`).

## 6. Validation adversariale

| mutation | garde attendue | observé |
|---|---|---|
| dé-câbler `TEAM_SELECTION` de l'arbre `RedRampage` | ROUGE | `AssertionError: AVANT #963-r1 ce terme rendait False : le +1 Movement etait REFUSE a tort` + `assert 0 == 1` sur `selection_type` |
| le substrat ne publie plus l'équipe d'origine (`overridden_from` ignoré) | ROUGE | `AssertionError: regime DEGENERE : la victime doit avoir une equipe courante != de son origine` — `assert 1 != 1` |

La fixture `etat_possede` **JOUE** l'owner-swap (`ChangeUnitOwnerOperation.execute`) au lieu
d'écrire le couple à la main : un montage qui poserait `originalTeam` directement testerait le test.
Elle assertionne **son propre non-vide** (`team != originalTeam`) — sans quoi les deux hypothèses
rendraient le même résultat et le fichier ne conclurait rien.

## 7. Résidu ouvert

| # | quoi |
|---|---|
| `#963-r4` | `AreFriendsAbilityTrigger$$ShouldTrigger` résout chaque opérande par **`SelectSingle`** et rend FAUX si l'un est nul ; le port garde son `any` sur le produit des deux listes, et rend FAUX des deux côtés là où `AreEnemies` (= `Not(AreFriends)`) rendrait **VRAI**. Autre axe que le paramètre d'équipe |

Non couvert et **nommé** : le 4ᵉ argument `anyEntity` d'`AreFriends` (2 sites natifs, aucun porté) ;
et la confrontation **LIVE** du régime `MindControl × RedRampage` — le montage exige `1101
AttemptedPossession` **et** un porteur `RedRampage` **et** que le porteur achève la victime possédée.
Le régime est établi offline sur un état produit par l'Operation native mirrorée, pas en bataille.
