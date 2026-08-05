# #462-r4b-r1-r1-r1-r1-b-r1-r1 — `BattleFatigue` : le conjoint `NOT IsObjectOrSteppable(dying)`

**Livré le 2026-08-05.** Résidu ouvert par `case-462-r4b-r1-r1-r1-r1-b-r1-isadjacent-selection-type.md`
(PR #634). `IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger` porte
**six** conjoints ; le port n'en portait que **cinq**.

**Le manquant était CITÉ dans la docstring du module qui ne l'implémentait pas.** C'est la troisième
fois de la campagne qu'une docstring affirme un fait que le code contredit — et ici les **deux faces
du même accident cohabitaient dans un seul fichier** (cf. §6).

## 1. La conjonction, lue conjoint par conjoint

`op_BitwiseAnd` s'applique de gauche à droite, un étage par conjoint. Ordre **exact** du décompilé
(`rnca9r7q6c`) :

| # | conjoint | factory native | sujet |
|---|---|---|---|
| 1 | `OnDeath(1, null)` | `DSLTriggers$$OnDeath` | — |
| 2 | `IsAdjacent(self, dying, 0x2)` | `DSLTriggers$$IsAdjacent` | `+0x30`, `+0x60` |
| 3 | `AreFriends(dying, self, 0, false)` | `DSLTriggers$$AreFriends` | `+0x60`, `+0x30` |
| 4 | `NOT HasEffect(self, 0x437, 0, 6)` | `DSLTriggers$$HasEffect` + `op_LogicalNot` | `+0x30` |
| **5** | **`NOT IsObjectOrSteppable(dying)`** | `DSLTriggers$$IsObjectOrSteppable` + `op_LogicalNot` | **`+0x60`** |
| 6 | `OwnerActive` | conjoint pré-alloué `<factory+0x88>+0x20` | — |

**La position n'est pas décorative, et le sujet encore moins.** Le conjoint 5 porte sur `+0x60` — le
**mourant**, le même sélecteur que le 2ᵉ argument d'`IsAdjacent` et le 1ᵉʳ d'`AreFriends` — et **pas**
sur `+0x30` (self). Un lecteur qui l'aurait attribué à `self` aurait porté l'exact **inverse** : il
aurait empêché un objet de *fuir*, au lieu d'empêcher un objet de *faire fuir*. Les deux lectures
donnent le même nombre de conjoints et la même liste de symboles ; seul l'offset les sépare.

Placé en 5ᵉ, il s'évalue après le gate d'immunité (conjoint 4) : sur une conjonction de prédicats
**purs**, l'ordre ne change aucun verdict — c'est ce qui autorise le port à évaluer `AreFriends` et
`HasEffect` en premier (ils sont impératifs et bon marché). Ce qui est préservé, c'est l'ordre
**relatif des deux nœuds DSL** (`IsAdjacent` avant `IsObjectOrSteppable`).

## 2. La factory est triviale — et c'est ce qui rend le mirror sûr

```
// IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable(this, selector)
left  = new <ctor>(selector, 0x1b, 0);      // HasTrait(selector, 27 = Steppable)
right = new <ctor>(selector, 0x0d, 0);      // HasTrait(selector, 13 = Object)
return IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr(left, right);
```

`<ctor>` est celui que ghidra mislabelle `UnityEngine.Timeline.SupportsChildTracksAttribute$$.ctor`
(**structure** lue, jamais le nom). Le point qui ferme la lecture : c'est le **même ctor, avec la
même signature `(this, unit, traitId, 0)`**, qu'alloue `IdunBattleLogic.Entities.DSLTriggers$$HasTrait`.
Les littéraux `0x1b`/`0x0d` occupent donc exactement la place d'un `traitId`, ce qui exclut toute
autre lecture — et autorise le mirror par le nœud `HasTrait` déjà porté.

⚠ **`Object` = 13, jamais `Decoy` = 1053.** Deux traits distincts de `UnitTrait`. Cette confusion
n'est pas hypothétique : elle est dans l'arbre (§5).

## 3. Le foyer — pourquoi pas un 3ᵉ site

`IsObjectOrSteppable` a **huit** call-sites natifs (xrefs mesurées sur `rnca9r7q6c`) :

| symbole natif | port | état |
|---|---|---|
| `BattleFatigueAbility$$CreateTrigger` | `runner/operations/behaviour.py` | **porté (cette tranche)** |
| `BarbedOvipositorAbility$$CreateTrigger` | `runner/operations/triggers/loki/barbed_ovipositor.py` | porté, fidèle |
| `MasterOfTheTutelaries_SummonAbility$$CreateTrigger` | `runner/operations/triggers/loki/master_of_the_tutelaries.py` | porté, **infidèle** (§5) |
| `CursedOfTheWalkingPoxAbility$$CreateTrigger` | — | non porté |
| `PossessionAbility$$CreateTrigger` | — | non porté |
| `Lakrimae_SummonPoxwalker_Ability$$CreateTrigger` | — | non porté |
| `BounceAbility$$Prioritization` | — | non porté |
| `KillMaimBurnAbility$$GetNextTarget` | — | non porté |

Les deux sites déjà portés étaient des **recopies manuelles**, et elles **divergeaient l'une de
l'autre** — ce qui est la démonstration du besoin : le même prédicat natif rendait deux verdicts
différents selon le module. Le fix passe donc par un foyer nommé,
`engine/entities/triggers.py::is_object_or_steppable`, de la même forme que son frère
`is_mechanical` (une **factory composite** : le natif n'alloue aucun prédicat dédié).

**Cinq call-sites sur huit restent non portés** — autant d'endroits où le même oubli peut se
reproduire, et la raison pour laquelle le foyer existe maintenant plutôt qu'à la 4ᵉ recopie.

## 4. Le chiffrage de l'écart (mesuré, `--step census`)

| trait | porteurs | ventilation |
|---|---|---|
| `BattleFatigue` (1015) | 40 | 28 npc + 12 summons — **0 lineup** |
| `Object` (13) | 28 | 28 npc (tous `LootObj_*`) |
| `Steppable` (27) | 27 | 25 npc + **2 summons** |

Le conjoint 3 (`AreFriends`) est ce qui rend le chiffre non trivial : **un objet de décor
n'appartient à aucune team, donc il était déjà écarté**. Pour lui, le conjoint 5 est redondant. Ce
qui rend l'écart réel, ce sont les Object/Steppable qui arrivent en bataille **sur une team** —
c'est-à-dire les summons : `genesSmnDecoy` et `astarSmnHaywireMine`, face à **12** porteurs
`BattleFatigue` eux aussi summons.

**Le régime est ATTEIGNABLE, et il est naturel.** Le porteur canonique est
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility` — passif de `genesMagus`
(Xybia), **héros présent dans `rl_duel build --list-pool`**, donc sans injection catalogue. La
**même** ability pose un `genesSmnDecoy` (Steppable 27) **et** un `genesSmnNeophyte` (BattleFatigue
1015), tous deux sur la team du caster et adjacents — le Neophyte naissant même **sur la tuile d'un
decoy**, que `AddUnitOperation$$KillSteppableUnits` écrase. Avant ce fix, la mort d'un decoy faisait
**fuir** le Neophyte ; le natif l'ignore.

Ce n'est donc pas un écart « lu, non exerçable » : c'est un écart qu'une composition d'équipe
ordinaire produit toute seule.

## 5. Le second site est infidèle — et la mesure dit exactement en quoi

`master_of_the_tutelaries.py` porte `_STEPPABLE_TRAITS = {"Steppable", "Decoy"}` là où le natif dit
`Steppable | Object`. Mesuré sur le gameconfig :

* `Decoy` **sans** `Steppable` : **0 porteur** → le volet `Decoy` est **inerte**. Le remplacer est
  value-preserving.
* `Object` **sans** `Steppable` : **28 porteurs** (tous npc) → c'est le **trou** : 28 cibles que le
  natif écarte et que ce port laisse passer.

Ce que la mesure ne dit **pas**, et qui décide de la gravité : ces 28 `LootObj_*` peuvent-ils être
`AreEnemies` du porteur *et* recevoir une attaque `Psychic` ? Trancher demande du live. Résidu
`#462-r4b-r1-r1-r1-r1-b-r1-r1-r1` — **le site n'est pas modifié ici** : c'est un changement de
comportement sur une autre ability, qui doit être validé avec ses propres tests.

> **RÉPONDU (2026-08-05) : OUI, et la divergence est CONFRONTÉE.**
> `case-462-r4b-r1-r1-r1-r1-b-r1-r1-r1-mot-object-or-steppable.md`. Un `LootObj_*` s'amène en
> bataille par un montage écrit (augmentation du seed + `Health` forcée + pose via
> `initAndStart.playerUnits`/`PLAYER_ID_AI`, qui contourne le refus de pool) : il arrive **team
> adverse et vivant**, `abilityTargets` le rend **cible légale** de l'attaque normale d'Abraxas, et
> le conjoint de profil ne lit que l'attaque. Deux bras appariés : **0 Screamer** sur le crate,
> **1** sur une vraie unité. Le port infidèle rendait `matches = True` sur ce même état live.
> ⚠ **Le zéro du recensement ci-dessus mesure ce que le seed CONTIENT, pas ce qu'un montage peut
> produire** — s'y arrêter aurait classé un bug réel en « fix cosmétique ».

## 6. Les deux faces de la même panne, dans un seul fichier

`operations/behaviour.py` portait **simultanément** :

* un **code** qui contredisait sa **docstring d'en-tête** — le conjoint 5 y était écrit, jamais
  implémenté (ce résidu) ;
* une **docstring de classe** qui contredisait cette même en-tête — elle annonçait « un ALLIE
  adjacent **(<=2)** » alors que l'en-tête réfutait déjà ce rayon depuis `-b-r1`.

Le fix précédent avait corrigé l'en-tête et le code, **et laissé la docstring de classe**. Les deux
sont corrigés ici. La leçon opérationnelle : **une docstring n'est pas une source** — quand elle
diverge du code, elle a autant de chances d'avoir raison que tort, et c'est le décompilé qui tranche.
Ici elle avait raison sur un point et tort sur l'autre, **dans le même fichier**.

## 7. Validation

* **Garde — `tests/engine/runner/test_battle_fatigue_object_or_steppable_offline.py` (11 tests).**
  C'est le **test** qui garde ; le probe, lui, **mesure**. La distinction est load-bearing : aucune
  passe ne joue un probe, donc la contre-épreuve n'aurait rougi pour personne si elle était restée
  dans `--step guard` seul. Le test **importe** le probe — aucun fork de montage.

  Offline **à dessein** : `matches` est un prédicat **pur**, il se teste sans runner ni tirage. Ce
  qu'on garde ici est la **présence du conjoint**, pas la fuite (qui, elle, passe par le `Maybe`).

  Même géométrie (adjacence 1), même team, même événement : **seuls les traits du mourant changent**
  — c'est ce qui rend un verdict attribuable au conjoint et à rien d'autre.

  | bras | verdict | contre-épreuve (conjoint 5 neutralisé) |
  |---|---|---|
  | mourant normal (contrôle) | `True` | `True` — identique, correct |
  | `Steppable` (27) | `False` | `True` — **diffère** |
  | `Object` (13) | `False` | `True` — **diffère** |
  | `Steppable` + `Object` | `False` | `True` — **diffère** |
  | `Decoy` seul (1053) | `True` | `True` — identique, **et c'est voulu** |

  Le dernier bras **réfute** la recopie `{Steppable, Decoy}` du §5 : le natif ne nomme que 27 et 13.
  Le passer à `False` en « harmonisant » les deux sites serait la faute exacte.

  ⚠ **La contre-épreuve vérifie d'abord que la mutation A MORDU.** Le nœud substitué **compte ses
  consultations**, et le test assertionne `calls > 0` **avant** de lire le verdict. Sans ça, une
  substitution qui ne prend pas (valeur capturée ailleurs qu'à l'attribut de module, conjoint
  antérieur qui court-circuite) rendrait « verdict identique » — qu'un lecteur pressé lirait comme
  *« le conjoint ne change rien »*. Ici **le vert est le résultat suspect, pas le rouge.**

* **Le test a été éprouvé par MUTANTS — 3 posés, 3 détectés** (chaque mutation vérifiée mordante par
  comparaison de hash avant/après, arbre restauré et `git diff` vide ensuite) :

  | mutant | effet | détecté |
  |---|---|---|
  | conjoint 5 retiré (`return True`) | le défaut d'origine | **8 rouges / 11** |
  | sujet `Target()` → `Caster()` | le conjoint porte sur `self` au lieu du mourant | **6 rouges** |
  | foyer `Object` → `Decoy` | exactement la recopie infidèle de MoT (§5) | **5 rouges** |

  Enseignement à garder : le mutant « conjoint retiré » **ne fait pas rougir** le test d'identité du
  foyer (le nœud existe toujours au module, il n'est simplement plus consulté). C'est l'assertion
  `calls > 0` qui l'attrape. Les deux gardes sont complémentaires, pas redondantes.

* **Le conjoint est aussi gardé LIVE ailleurs** —
  `tests/engine/runner/test_barbed_ovipositor_live.py` (sur `master`, non modifié ici) confronte
  **live** `NOT IsObjectOrSteppable(target@0x178)` avec un `genesSmnDecoy` Steppable en bras négatif.
  Le fichier offline ci-dessus garde **le conjoint sur `BattleFatigueAbility`**, que rien ne couvrait.

  ⚠ **RECTIFIÉ (2026-08-05)** : cette puce affirmait que `barbed_ovipositor` « passe par le foyer »,
  donc que ce test live gardait le foyer. **C'est faux** — le module a conservé sa recopie manuelle
  `_OBJECT_OR_STEPPABLE = (UnitTrait.Steppable.name, UnitTrait.Object.name)`, fidèle sur les
  littéraux mais recopie quand même. Ce test live garde donc **la recopie**, pas le foyer. Résidu
  `#462-r4b-r1-r1-r1-r1-b-r1-r1-r3` — et la migration n'y est **pas** cosmétique : le trigger est
  `On(UnitDeath)`, donc la cible est un CADAVRE, et c'est exactement le cas où le substrat de traits
  du contexte DSL (`entity_trait_names`, repli gameconfig, #226) diffère de `ctx.traits` brut.

  | bras | verdict | contre-épreuve (conjoint 5 neutralisé) |
  |---|---|---|
  | mourant normal (contrôle) | `True` | `True` — identique, correct |
  | `Steppable` (27) | `False` | `True` — **diffère** |
  | `Object` (13) | `False` | `True` — **diffère** |
  | `Steppable` + `Object` | `False` | `True` — **diffère** |
  | `Decoy` seul (1053) | `True` | `True` — identique, **et c'est voulu** |

  Le dernier bras est celui qui **réfute** la recopie `{Steppable, Decoy}` du §5 : le natif ne nomme
  que 27 et 13.

* **Non-régression live** — 4 fichiers ciblés, 24 tests, **0 skipped** :
  `test_spiritual_leader_live.py` (5), `test_barbed_ovipositor_live.py` (10),
  `test_cosmic_horror_live.py` (6), `test_decoy_foundation_live.py` (3). Plus
  `test_448_r1_r1_r2_r1_dsl_after_move_offline.py` (16) — il lit le **source** de `behaviour.py` pour
  compter les appels `MoveUnitOperation`, donc toute réécriture du module le concerne.

* **NON COUVERT — le verdict natif du conjoint 5 n'est pas confronté.** Nommé, pas contourné :

  * *Instrument* : il existe (`combatSnapshot.unitFlags` expose les `UnitFlag` natifs en invoquant
    `IdunBattle.Entities.UnitExtensions$$HasFlag` par valeur d'enum), donc `UnitFlag.Fled = 9` — la
    seule trace observable de `FleeOperation` — est **lisible**. Ce n'est pas un trou de capteur.
  * *L'obstacle est le RNG.* Le behaviour est `Repeat(n, If(NOT HasFlag(self,9), Maybe(GetFleeChance,
    self) -> Flee(...)))` : la fuite est un tirage (`GetFleeChance` = `ConditionalAmount(TargetIsOverkilled
    ? const 0x33 : const 0x2a)`). Une non-fuite observée **ne prouve donc rien** — il faut N tirages
    indépendants, et le flag 9 interdit au *même* porteur de re-fuir.
  * *Montage exact à jouer* : `genesMagus` au pool, deux activations pour poser 2 decoys adjacents →
    le Neophyte apparaît → tuer un decoy adjacent au Neophyte → lire `unitFlags` du Neophyte.
    Bras contrôle : même géométrie, mais l'allié qui meurt est une **unité normale**. Il faut
    plusieurs porteurs par événement (anneau) ou plusieurs batailles pour sortir du bruit —
    ~`0.58^N`.
  * *Pourquoi porté quand même* : le décompilé est **net** (conjonction lue verbatim, factory de deux
    `HasTrait` aux littéraux `0x1b`/`0x0d`, ctor identifié par sa structure), donc c'est un mirror 1:1,
    pas une inférence. La doctrine l'autorise explicitement ; ce qu'elle exige est de **dire** que la
    garde est offline. Elle l'est.

## Résidus

* ~~**`#462-r4b-r1-r1-r1-r1-b-r1-r1-r1`**~~ — **LIVRÉ (2026-08-05)**,
  `case-462-r4b-r1-r1-r1-r1-b-r1-r1-r1-mot-object-or-steppable.md`. MoT passe par le foyer ; la
  question ouverte est **répondue OUI** et l'écart **confronté live** (0 vs 1 Screamer sur deux bras
  appariés). Résidu neuf : `#462-r4b-r1-r1-r1-r1-b-r1-r1-r3`.
* **`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3`** — `barbed_ovipositor.py` est la **dernière recopie manuelle**
  du foyer. Fidèle sur les littéraux, donc sans écart de verdict *aujourd'hui* — mais son trigger est
  `On(UnitDeath)`, donc sa cible est un CADAVRE, et c'est précisément le cas où le substrat de traits
  diffère (`entity_trait_names` retombe sur le gameconfig quand le `StatsComponent` manque, #226 ;
  `ctx.traits` brut rend un set VIDE). La migration change donc potentiellement un verdict sur un
  chemin live-confrontable (`test_barbed_ovipositor_live.py`) et exige ses propres bras.
* **`#462-r4b-r1-r1-r1-r1-b-r1-r1-r2`** — les **5 call-sites natifs non portés** d'`IsObjectOrSteppable`
  (§3). Chacun est un gate manquant du même genre, sur une ability différente ; `--step re` les
  réimprime avec leur état, donc l'inventaire se re-dérive au lieu de se citer.
