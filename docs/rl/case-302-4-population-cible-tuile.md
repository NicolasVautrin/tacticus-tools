# case-302 tranche 4 — la POPULATION complete des abilities a cible TUILE

Tranche 4 de `case-302-route-cible-tuile.md` §7. **Une MESURE, pas un port.**

Les tranches 1 a 3 ont porte la route generique tuile et ses deux premiers membres
(`1169 PlagueburstMortar`, `1148 DaemonicOrdnance`). Leur inventaire ne lisait le bit
`TargetingRule.TargetIsTile` que sur les abilities **deja portees** dans `ABILITY_CLASSES` — un
sous-ensemble. Cette tranche lit le bit sur **toute** la population enregistree par le jeu, et dit
pour chacune si sa face DECISION a une route.

Probe : `scripts/python/probe_302_4_tile_target_population.py` (`scan` puis `report`).
Tables : `docs/rl/case-302-4/tile-target-population.tsv` et `.json`.

---

## 1. Ou vit la population, et pourquoi c'est ELLE le denominateur

`IdunBattle.Core.Services.AbilitiesDatabase$$Init` appelle
`IdunBattle.Core.Services.AbilitiesDatabase$$InitializeActiveAbilities`, qui remplit un
`Dictionary<ActiveAbilityType, Func<AActiveAbility>>` — une entree par ability active, chacune
pointant sur une lambda `...AbilitiesDatabase.u003Cu003Ec$$u003CInitializeActiveAbilitiesu003Eb__27_N`
qui fait exactement `new <X>Ability()`.

Ce dictionnaire n'est pas *un* index parmi d'autres : c'est **le seul**.
`IdunBattle.Core.Services.AbilitiesDatabase$$GetActive(abilityType)` fait
`TryGetValue` dessus et, **en cas d'echec, journalise puis rend `new NoneAbility()`** — lu au
decompile. Une valeur d'`ActiveAbilityType` absente du registre n'a donc aucun comportement propre
dans une bataille.

⇒ Le denominateur pertinent est **le nombre d'entrees de ce registre**, pas le nombre de membres de
l'enum. Les deux comptes sont rendus separement par le probe (`--- DENOMINATEUR ---`), avec les
valeurs d'enum sans entree listees, precisement pour que l'ecart ne se lise pas comme une perte.

### Le mapping `id -> classe`, et pourquoi il est VERIFIE et non suppose

Le decompile de `InitializeActiveAbilities` ne nomme pas les lambdas : il montre, par entree, le
champ de cache `<>c.<>9__27_N` (a `<>c statics + 8 + 8*N`, le slot 0 etant le singleton `<>9`) puis
le `Dictionary.Add` de l'id. La relation `offset <-> N` est donc **affine**, et le report la
**re-derive puis la CONTROLE** : il exige que le nom de la classe construite par `b__27_N` coincide
avec le nom de l'`ActiveAbilityType` de l'entree (`<Nom>Ability`). Sous le seuil de concordance, le
report **refuse de conclure** — un decalage d'un cran renommerait silencieusement tout l'inventaire.

---

## 2. Ou vit le masque, et lequel des deux jeux d'options decide

`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, targetingOptions, abilityAttackType)`
installe **DEUX** structs `TargetingOptions` de 0x40 octets :

| champ | contenu | qui le lit |
|---|---|---|
| `this+0x70` | la struct passee par le ctor de la sous-classe | `AActiveAbility$$GetValidTargets`, `get_TargetingOptions`, `get_IsSelfCasting` |
| `this+0xb0` | le `Nullable<TargetingOptions>` du slot virtuel `GetTargetingOptionsForContinue`, **ou** la meme struct si le Nullable est vide | `get_TargetingOptionsForContinue` / `GetInvalidTargetReasonForContinue` |

`AActiveAbility$$GetValidTargets` ne touche que `this+0x70` (lu en entier au decompile) : **c'est ce
champ, et lui seul, qui decide du DOMAINE de ciblage**. Le second jeu ne concerne que le mode
« continue » d'une ability multi-etapes. Le masque cherche est donc `this+0x70 + 0x28` = `Rules`,
et `TargetIsTile` en est le bit 6 — exactement ce que rend
`IdunBattle.Core.Services.TargetingOptions$$get_IsTileTargeting` (`*(byte*)(this+0x28) >> 6 & 1`).

`AActiveAbility$$SetConfigValuesInTargetingOptions`, appele avant chaque lecture, ne touche que
`options+0x10` (la portee `Nullable<int>` lue de la config) : **il ne modifie jamais `Rules`**. Le
masque est donc entierement decide au ctor, statiquement.

---

## 3. Les QUATRE formes du ctor — le piege, et il est deja paye dans ce depot

`IdunBattle.Core.Services.TargetingOptions` expose **trois** ctors dans ce build, et une quatrieme
voie existe sans aucun appel :

| forme | signature lue | masque effectif |
|---|---|---|
| **litteral** | `.ctor(this, isSelfCasting, range, forceMeleeTarget, RULES, dynCaster, dynTarget)` | `RULES`, 5e argument |
| **preset + flags** | `.ctor(this, template, additionalRules)` | `template.Rules | additionalRules` |
| **preset seul** | `.ctor(this, template)` | `template.Rules` |
| **copie statique** | aucun appel : le ctor recopie les 0x40 octets d'un champ statique de `TargetingOptions` et passe la copie a `AActiveAbility$$.ctor` | la constante ecrite par `TargetingOptions$$.cctor` a `<preset>+0x28` |

Les deux dernieres colonnes du milieu sont le piege : **le litteral visible n'est pas le masque**.
`...Loki.TheQuickeningAbility$$.ctor` combine le preset `TargetingOptions statics+0x200` avec
`0x806000000` ; le bit 6 y vient du PRESET, pas du litteral. Symetriquement,
`...Loki.Loki_NormalAttackAbility$$.ctor` ne passe par aucun ctor : son masque `0x4002` est celui du
preset `+0x00`.

**Les presets ne sont pas interchangeables** — le probe les lit tous dans `TargetingOptions$$.cctor`
et publie la table (`presets` du JSON). C'est pourquoi la regle est de lire **ability par ability**,
jamais de generaliser « toutes les offensives valent X ».

---

## 4. Ce que le probe ne peut PAS lire — tri-etat, jamais un zero

| etat | ce qu'il dit |
|---|---|
| `measured` | le ctor (ou un ctor de base suivi) expose l'une des quatre formes |
| `not_measurable` | la classe n'expose AUCUNE forme lisible. **Ce n'est pas « masque nul »** : l'ability peut porter le bit sans qu'on le voie |
| `absent` | l'entree du registre n'a pas pu etre reliee a une classe |

Le motif dominant de `not_measurable` est la **deduplication IL2CPP** : un ctor de base trivial est
partage, et Ghidra ne le nomme que pour UN proprietaire — d'ou des chaines qui aboutissent a un
corps nomme sans rapport (mesure :
`...Loki.GenericAddEffectToOwnerAbility$$.ctor` appelle un corps nomme
`Unity_Services_Core_Threading_Internal_UnityThreadUtilsInternal___ctor`). Le probe **suit** la
chaine de ctors de base tant qu'elle est nommee, puis s'arrete et le DIT.

---

## 5. Ce que ce balayage ne repond pas — la question du bit n'est pas celle de la cible

Rappel de `case-302` §1.1, et il vaut pour cette tranche aussi : le bit `TargetIsTile` repond a
**« le DOMAINE de `GetValidTargets` est-il fait de tuiles ? »**, PAS a **« la cible de l'action
est-elle une tuile ? »**. `1197 ExcruciatingFrequencies` cible une tuile **sans** porter le bit (son
aim passe par `TargetTiles@0x190`). Cet inventaire ne la compte donc pas, et c'est correct — mais il
ne faut pas le lire comme « toutes les cibles tuile sont ici ».
