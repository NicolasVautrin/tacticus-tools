# Case #170 — `get_Priority` est surchargé sur **22** playbooks (et 3 portés avaient un tier faux)

**Verdict : QUIRK PORTÉ.** L'affirmation « aucun playbook n'override `get_Priority` » (#115) est
fausse. 22 des 257 `ActiveAbilityType` ont un tier ≠ 0, toutes NonComparable. Trois d'entre elles
étaient **déjà portées** avec la mauvaise valeur — le défaut n'était donc pas seulement documentaire.

## 1. La table native

`IdunBattle.Entities.Abilities.AbilityPriority` = `1000=First, 100=Early, 0=Normal, -100=Late,
-1000=Last`. `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` range chaque
`ActiveAbilityType` NonComparable dans `dict[playbook.get_Priority()]` — slot **0** de l'interface
`IPlaybook`, dispatché par `FUN_180002560(0, DAT_1831d4f88, playbook)` ; le slot **1**
(`get_IsComparable`) sépare les Comparable, qui vont dans l'`OrderedSet` `special` et **ignorent le
tier**. `GetDefaultActiveAbilityActionGenerators` crée un générateur par tier, dans l'ordre
`[1000, 100, 0, -100, -1000]`, tous évalués **avant** le fallback Comparable, en premier-non-null.

| tier | # | abilities (playbook homonyme) |
|---|---|---|
| **1000** `First` | 9 | BreathOfSilence 1070, EreWeGo 1085, DeathScream 1109, ArmouredMight_Move 1127, TzeentchsFirestorm 1155, ArcScourge 1173, **NovaBoost 1192**, SquigLaunchas 1200, DeathOnTheWind 1213 |
| **100** `Early` | 4 | Catalyst 1032, GunnersKillOnSight 1125, SolarAtomizer 1174, **ThriceBlessedConflagration 1187** |
| **-100** `Late` | 3 | MacroPlasmaIncinerator 1159, SquigMine 1201, InfernalCannon 1209 |
| **-1000** `Last` | 6 | MyWillBeDone 1072, DaGreatWaaagh 1084, LivingBatteringRam 1111, InvocationOfMachineVengeance 1172, **NovaShield 1194**, ReanimationBeam 1223 |
| **0** `Normal` | 235 | tout le reste (défaut hérité) |

En **gras** : les trois portées. La table vit dans le port —
`engine.playbook.noncomparable.NATIVE_PRIORITY` + `native_priority(ability_id)`.

## 2. Pourquoi #115 (et le constat R14) ont conclu faux

Ce n'était pas une lecture erronée mais un **faux négatif de méthode**, et il a DEUX causes
indépendantes qui pointent dans le même sens :

1. **Ghidra ne nomme aucune de ces surcharges.** Leurs corps sont
   `mov eax, <imm32> ; ret` — cinq octets, dédupliqués par IL2CPP entre tous les playbooks de même
   tier. `search_symbols_by_name "get_Priority"` sur `GameAssembly.dll` rend **4 hits, 0 sur un
   Playbook** ; `functions.tsv` n'a pas d'entrée aux VA concernées. C'est exactement ce qu'a vu
   #115, et il en a conclu « le getter vit une fois sur le parent partagé ».
2. **`data/symbols/<build>/frida/methods.tsv` est indexé par RVA, sans doublon** — mesuré :
   **121 502 lignes, 0 RVA répétée**. Un corps partagé n'y a donc qu'**un seul propriétaire**.
   Les 9 playbooks de tier 1000 partagent la ligne de `TzeentchsFirestormPlaybook.get_Priority`,
   les 3 de tier -100 celle de `SquigMinePlaybook`, les 6 de tier -1000 celle de
   `ReanimationBeamPlaybook`. Le tier 100 n'a même aucun représentant sous un nom de playbook.
   D'où les **3** hits vus par R14 pour **22** surcharges réelles.

   Corollaire général, à retenir hors de ce cas : **« X n'a pas de méthode M dans `methods.tsv` »
   ne prouve rien**. C'est vrai de toute méthode au corps trivial (getter constant, `return null`,
   stub). Seule la **vtable** répond.

3. Les classes de base génériques (`Playbook<T>`, `NonComparablePlaybook<T>`,
   `ComparablePlaybook<T>`) sont **absentes de `methods.tsv`** (aucune méthode d'instanciation
   générique n'y figure) : on ne peut donc pas non plus y lire le getter *hérité*. Les deux bouts
   de la chaîne sont invisibles offline.

Un détail qui a renforcé l'erreur : #115 avait attribué le `mov eax,0x3E8` trouvé à
`idun.tests.TestLegendaryEventProgression$$GetLiveEventState+0x40` et l'avait déclaré « stale /
mal-attribué », puis **supprimé** les valeurs 1000/-1000 de NovaBoost/NovaShield. Ces valeurs
étaient justes ; c'est l'*attribution* du corps dédupliqué qui était fortuite.

## 3. La mesure (#170)

`scripts/python/probe_170_playbook_priority.py` — trois voies indépendantes qui doivent concorder :

* **vtable (ground truth)** : `pbGate {itf:"Playbook", slot:0, args:[]}` **invoque** le slot 0 sur
  le playbook réellement chargé (`LoadPlaybook(db, ability)`), quelle que soit la classe qui
  l'implémente. Sweep sur **toutes les valeurs de l'enum** lues dans
  `data/symbols/<build>/frida/enums.tsv` — 257 valeurs, pas une plage arbitraire : c'est ce que le
  natif lui-même itère (`Enum.GetValues<ActiveAbilityType>()` dans `InitAbilityTypeLists`). Au-delà
  de 1230 l'enum ne contient que `Test*` 9001..9018 et `STRIPPED`.
* **résolution par nom** : `abilityPreferences` (la voie qui avait produit la carte de
  `playbook/architecture.md`). **0 divergence sur 257.**
* **octets du binaire**, pour les trois surcharges dont `methods.tsv` expose la RVA :

  | playbook | octets | décodage |
  |---|---|---|
  | `TzeentchsFirestormPlaybook.get_Priority` | `b8 e8 03 00 00 c3` | `mov eax,0x3E8` → **1000** |
  | `SquigMinePlaybook.get_Priority` | `b8 9c ff ff ff c3` | `mov eax,0xFFFFFF9C` → **-100** |
  | `ReanimationBeamPlaybook.get_Priority` | `b8 18 fc ff ff c3` | `mov eax,0xFFFFFC18` → **-1000** |

`get_IsComparable` (slot 1) vaut **False pour les 22** — lu sur **AL** (`retLow`), pas sur RAX : un
getter `bool` ne met que l'octet bas, le reste de RAX est un résidu (mesuré : un pointeur). Contrôles
positifs : 69 (attaque normale) et 18 (Heal) → `True`.

**Exhaustivité** : elle porte sur les 257 valeurs de l'enum et sur la valeur EFFECTIVE du slot
invoqué, pas sur une recherche de symboles. Ce qu'elle ne couvre pas : un playbook dont le tier
dépendrait de l'état (aucun des 257 corps mesurés n'est conditionnel ici — mais le
`get_Priority` de `DefenderOfTheGreaterGood_ExtraHitsEffect`, lui, l'est :
`xor edx,edx / mov eax,0x64 / cmp byte [rcx+0x480],dl / cmovne eax,edx`. C'est un **effet**, pas un
playbook, et il n'entre pas dans `InitAbilityTypeLists` — mais il montre que la forme conditionnelle
existe dans ce binaire).

## 4. Ce qui est corrigé côté port

| fichier | correction |
|---|---|
| `engine/playbook/noncomparable/_base.py` | **table `NATIVE_PRIORITY` (22) + `native_priority(id)`** = le point d'extension, avec la note anti-régression sur la déduplication |
| `engine/playbook/noncomparable/nova_boost.py` | `PRIORITY` 0 → **1000** |
| `engine/playbook/noncomparable/thrice_blessed_conflagration.py` | `PRIORITY` 0 → **100** |
| `engine/playbook/noncomparable/nova_shield.py` | `PRIORITY` 0 → **-1000** |
| `engine/ai/tactic.py`, `engine/ai/action_generators.py`, `engine/ai/utilities.py`, `engine/playbook/base.py`, `noncomparable/__init__.py` | l'affirmation générale « aucun override » remplacée par la table + la raison du faux négatif |
| 22 docstrings de feuilles (`heals.py`, `stormcaller.py`, …) | `PRIORITY=0 (#115)` → `PRIORITY=0 (défaut `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170)` — la **valeur** était juste, la **justification** était fausse |

L'affirmation n'était **pas** dans `CLAUDE.md` — vérifié : `git log -S "get_Priority" -- CLAUDE.md`
est vide et le fichier (includes compris) ne contient aucune occurrence. Le constat R14 se trompait
de porteur ; aucune correction n'y était nécessaire.

## 5. Le point d'extension était **déclaratif** — il ne l'est plus

`NonComparablePlaybook.PRIORITY` et les 5 générateurs `NC(1000..-1000)` de `DefaultAiUnitTactic`
existaient déjà. Mais avec **35 playbooks portés tous à 0**, un seul tier était peuplé : le filtrage
`pb.PRIORITY != priority` de `choose_action` n'avait **jamais été exercé**. Un filtre cassé (ou
supprimé) serait passé totalement inaperçu — ni erreur, ni test rouge.

`tests/engine/test_nc_priority_tiers_offline.py` l'exerce avec des playbooks **stub** (le stub ne
vit que dans le test) dont le tier HAUT porte l'utilité la PLUS FAIBLE — le seul couple qui rend le
tier observable :

* `choose_action(priority=P)` ne voit que le tier `P` ; un tier vide rend `None` (le tactic descend),
  jamais un repli sur un autre tier ;
* le tactic renvoie l'ability de tier 100 (utilité **1**) plutôt que celle de tier 0 (utilité **999**) ;
* contre-épreuves : sans le tier haut, c'est le tier 0 qui sort ; sans lui, le tier -1000 ;
* la table et la conformité `PLAYBOOKS[id].PRIORITY == NATIVE_PRIORITY[id]`.

**Vu ROUGE avant d'être vert**, sur deux mutants distincts : (a) `PRIORITY` de 1187 remis à 0 →
1 échec ; (b) filtre `pb.PRIORITY != priority` neutralisé → 2 échecs (dont le test d'ordre).

## 6. Validation

| quoi | résultat |
|---|---|
| `probe_170_playbook_priority.py` (live, 257 abilities) | **ROUGE** avant fix — `1192 port=0/natif=1000`, `1194 port=0/natif=-1000`, `1187 port=0/natif=100` ; **VERT** après (`35 playbooks portés, PRIORITY conforme au natif pour tous`) |
| `tests/engine/test_nc_priority_tiers_offline.py` | 5 passed ; rouge sur 2 mutants |
| `tests/engine/test_thrice_blessed_decision_live.py` (la seule des 3 confrontable) | 4 passed |
| `tests/engine/runner/test_skitarii_turn_live.py` (garde par dépendance : exerce `DefaultAiUnitTactic` via `summon_ai`) | 1 failed — **échec PRÉEXISTANT**, reproduit à l'identique sur `1930824` (worktree jetable, même message `BFS 3->3`, même action `ability 17 target 79`). Déjà nommé comme rouge connu dans `case-r14-mow-decision.md` §5, résidu 3 |

**Ce qui n'est PAS couvert** :

* **NovaBoost 1192 / NovaShield 1194 restent inconfrontables** : leur unique porteur est
  `tauBossRiptide`, `kind = npc`. Leur tier est établi par mesure vtable + `abilityPreferences`,
  jamais par un agrément de décision.
* **Le tier n'est pas encore *observable* côté port sur un vrai porteur.** Il faudrait une unité
  portant **deux** NonComparable PORTÉES de tiers différents ; il n'en existe aucune aujourd'hui.
  Le cas le plus proche est `adeptExorcist` (MoW), qui porte `ThriceBlessedConflagration` 1187
  (tier **100**) **et** `DevastatingRefrain` 1188 — NonComparable de tier **0** (mesuré). Dès que
  1188 sera porté, ce couple devient le scénario d'agrément naturel du tier : à cible disponible
  pour les deux, le natif doit émettre **1187** quelle que soit l'utilité de 1188.
* Les **19 autres** abilities de la table ne sont pas portées : leur valeur est disponible dans
  `NATIVE_PRIORITY`, elle n'est pas exercée.
