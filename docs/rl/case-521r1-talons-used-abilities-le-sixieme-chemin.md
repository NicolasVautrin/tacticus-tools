# #521-r1 — `1330 TalonsOfTheEmperor_UsedAbilities` : le compteur qui n'avançait pas, et un SIXIÈME chemin de registration

Build `rnca9r7q6c`. Porteur unique : `custoAtlacoya` (Atlacoya, Adeptus Custodes), lineup, pool
rank 17. #521 avait porté la face COMBAT de `1195 TalonsOfTheEmperor` et **lu** le compteur `1420`
depuis la capture ; il ne le faisait pas **avancer**. En simulation pure il restait donc figé à sa
valeur de départ et l'extra damage devenait faux dès le 2ᵉ cast d'ability alliée — **sans erreur,
sans crash**, la même signature que le no-op qu'était 1195 avant #521.

## 1. Le CHEMIN DE MONTAGE : ce n'est pas le dict qu'on croit

Le kit d'Atlacoya rend `activeAbilities = ['TalonsOfTheEmperor']` et
`passiveAbilities = ['DaughterOfTheAbyss']` : **1330 n'y est nulle part**. Les quatre chemins de
registration déjà portés (trait / passiveAbility / activeAbility DÉRIVÉE / relique) ne peuvent donc
pas la monter, et le réflexe — l'inscrire dans `ACTIVE_ABILITY_TRIGGERS` — écrirait 1195 dans un
dict natif **où il n'est pas**.

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility` porte **deux**
dictionnaires distincts, dans deux slots statiques distincts :

| lecteur | slot | valeur | monté par |
|---|---|---|---|
| `…$$GetDerivedTriggeredAbilities` | `<statics>+0x30` | une **List** (`ToList`) | `UnitFactory$$AddDerivedAbilities` |
| `…$$GetPassiveHelperAbility` | `<statics>+0x78` | un **scalaire** `Nullable` | `IdunBattle.Entities.Factories.UnitFactory$$AddActiveAbility` |

`0x4ab = 1195` **n'apparaît qu'une fois** dans tout le `.cctor`, et c'est dans le second.

```
IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities(entity, config, activeState,
                                                                  passiveState, tertiaryState)
    config@+0xa8 (PassiveAbilities) -> TriggeredAbilityComponent.TryAdd(id, passiveState, 2)
    config@+0xb0 (TertiaryAbility)  -> TriggeredAbilityComponent.TryAdd(id, tertiaryState, 3)
    config@+0xa0 (ActiveAbilities)  -> UnitFactory$$AddActiveAbility(aa, activeState, passiveState,
                                                                     actives, triggered, i == 0)

IdunBattle.Entities.Factories.UnitFactory$$AddActiveAbility(...)
    ActiveAbilityComponent.Add(actives, aa, activeState, hierarchy)
    helper = StaticBattleRules.ActiveAbility.GetPassiveHelperAbility(aa)        # Nullable
    if (helper.HasValue)
        TriggeredAbilityComponent.TryAdd(triggered, helper.Value, **passiveState**, 0)
```

Le dict compte **SIX** entrées, transcrites verbatim (nom + ordinal) dans
`PASSIVE_HELPER_ABILITY_TRIGGERS` :

| active (clé) | triggered helper (valeur) | portée ? |
|---|---|---|
| `1032 Catalyst` | `1062 GuildBossRunAway` | non |
| `1070 BreathOfSilence` | `1128 BreathOfSilence_SetStart` | non |
| `1118 DoctrinaImperatives` | `1201 DoctrinaImperatives_SetStart` | non |
| `1148 DaemonicOrdnance` | `1244 DaemonicOrdnance_Crit` | non |
| `1189 CalibaniteGreatsword` | `1316 CalibaniteGreatsword_NormalAttackAdditionalDamage` | non |
| **`1195 TalonsOfTheEmperor`** | **`1330 TalonsOfTheEmperor_UsedAbilities`** | **oui (#521-r1)** |

Deux détails **lus, pas déduits** : l'état d'ability inscrit est le **`passiveAbilityState`** (pas
l'actif) et la hiérarchie vaut **0**. Sans observable ici (le behaviour ne lit aucun `ConfigVar`),
mais c'est le littéral natif. Résidu **#521-r4** pour les cinq autres.

## 2. Les deux arbres, mirror 1:1

Les DEUX corps ont leur symbole propre sur `rnca9r7q6c`. C'est
`…FuelledByFury_ExtraDamageAbility$$CreateTrigger` qui est **ABSENT de la table** — corps
dédupliqué par IL2CPP, propriétaire unique = celui de TalonsOfTheEmperor. #521 avait lu l'inverse
(« le corps de 1330 est dédupliqué avec celui de FuelledByFury ») : la relation est vraie, le sens
de propriété était retourné. Rappel du `CLAUDE.md` : l'absence d'un symbole ne prouve rien.

`…TalonsOfTheEmperor_UsedAbilitiesAbility$$CreateTrigger` (slots `DSLFactory` `this@+0x28` :
`+0x78 Behaviors · +0x80 Formulas · +0x88 Triggers · +0x90 Selectors` ; slots `DSLSelectors` :
`+0x30 Owner · +0x48 Caster`) :

```
On( 0xe = UnitPostAbility, ownerNeedsToBeAlive = 1 )
& AreFriends( Owner@+0x30, actor@+0x48, comparisonType = 0, anyEntity = 0 )
& ( HasTrait(actor@+0x48, 0x10 = Hero) & !HasTrait(actor@+0x48, 0x419 = MachineOfWar) )
& IsActiveAbilityCountedAsUsed( isPreAbilityTrigger = 0 )
```

`…$$CreateBehaviour` :

```
AddEffectOrIncreaseLevel( Behaviors@+0x78, 0x58c = 1420,
                          abilityState = BaseTriggeredAbility.get_AbilityStateReference(this),
                          source = targets = Owner@+0x30,
                          level = Formulas@+0x20, maxLevel = NULL )
```

- `Formulas@+0x20` : `IdunBattleLogic.Entities.DSLFormulas$$.ctor` met en cache cinq nœuds
  constants — `+0x18 = 0`, `+0x20 = 1`, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`. Le slot lu est le
  `1` ⇒ **+1** par déclenchement.
- `maxLevel = NULL` ⇒ **aucun cap** (contraste `TerrifyingCrescendo`, `buffMaxLevel = 6`).
- **Différence de FORME avec FuelledByFury** : là où FuelledByFury écrit
  `If(HasEffect, IncreaseEffectLevel, AddEffect)` à la main, 1330 appelle la **factory composite**
  `IdunBattleLogic.Entities.DSLBehaviors$$AddEffectOrIncreaseLevel` (un `ForeachBehaviour` dont le
  lambda construit ce même `If` par élément). Même arbre, deux écritures ; le port passe par le
  helper `add_effect_or_increase_level`, qui EST le mirror de cette factory (#149 : l'artefact natif
  tranche la forme).

## 3. Ce que la mesure a trouvé

`probe_521r1_talons_used_abilities.py`, board `MC1_67`, armure 2000, crit/block 0.

**`chaine`** — UN build, DEUX captures. Deux captures et pas un rejeu chaîné : le compteur ne dépend
d'aucun tirage et se mesure sans le MT ; le dégât, lui, exige un MT calé. Chaîner mêlerait la
fidélité du compteur à celle des tirages de `MomentShackle`.

| étage | natif | port |
|---|---|---|
| `cap0` | compteur `1420` = 0 | 0 |
| un allié `Hero` (`custoTrajann`) caste `1184 MomentShackle` | **1** | **1** (branche `AddEffect`) |
| le porteur caste `1195` | dégât **3862**, profil `14 Power`, 1 coup | **3862**, coup par coup |
| après ce cast | **2** | **2** (branche `IncreaseEffectLevel`) |
| un tour d'équipe ADVERSE complet | **2** (porteur à 292 569 PV) | — |

Le porteur **compte pour lui-même** : aucun `!AreEqual(Owner, actor)` dans la conjonction native, et
c'est mesuré (0 → 1 → 2). Le dégât lit le compteur d'**AVANT** (1), `On(0xe)` étant le dernier
événement d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`.

**`attaque_normale`** — le témoin négatif. L'attaque normale EST une active côté natif et émet
`On(0xe)` : seul `IsActiveAbilityCountedAsUsed` l'écarte. Compteur 0 → 0 des deux côtés, 3 coups
natifs portés.

### Les contre-épreuves, et pourquoi elles ne sont pas décoratives

Chacune ne mute **qu'une** lecture ; le probe **exige** que celles qui doivent discriminer
discriminent :

| contre-épreuve | effet mesuré |
|---|---|
| `sans_registre` | compteur 0 au lieu de 1 en [A], 1 au lieu de 2 en [B] |
| `increment_2` | 2 au lieu de 1 en [A], 3 au lieu de 2 en [B] |
| `avec_cap` (clamp 1) | 1 au lieu de 2 en [B] — **muet en [A]**, et le probe ne l'y exige pas |
| `sans_gate_compte` | l'attaque normale se met à compter (0 → 1) |
| gates FORGÉS hors-ligne | `matches` FAUX pour un acteur ennemi, sans `Hero`, `MachineOfWar` — avec le cas nominal comme témoin, sans quoi trois refus ne prouveraient rien |

### Deux choses que la mesure a corrigées en cours de route

**(a) Le canal `configActives` était MUET, et le port marchait quand même.** Le registre est lu
contre `UnitContext.config_active_abilities` (`UnitConfiguration.ActiveAbilities` mesurée, canal
`unitAbilityStates.units[].configActives`) avec repli sur le kit gameconfig. Premier jet du probe :
`branche = repli_gameconfig`, `configActives = None` — la branche MESURÉE n'était **jamais**
exercée. Cause : le probe n'appelait pas `snapshot.bind_live_rpc`, donc `_auto_ability_states`
rendait `no-transport` et **tous** les canaux mesurés restaient `None`. Avec le bind :
`branche = mesure`, `configActives = ['TalonsOfTheEmperor']`. Un accord numérique n'aurait jamais
montré ça — c'est un test qui interroge le SUBSTRAT qui l'a montré.
⚠ Le même trou existe dans `probe_521_talons_of_the_emperor.py` (résidu **#521-r5**).

**(b) Un compteur qui TOMBE n'est pas un compteur qui monte à tort.** L'étage [D] a d'abord rendu
`2 -> 0`. Ce n'était ni `AreFriends` mal lu ni un effet qui expire : le porteur était **mort**
pendant le tour adverse et ses effets étaient partis avec lui — un régime **stérile**. Le montage
donne désormais des PV au porteur (ils n'entrent dans aucun étage du dégât de 1195, ce que le
ré-jeu confirme : 3862 avant comme après), et le probe **distingue les trois cas** (mort / monte /
baisse) au lieu de rendre une divergence.

### Ce qui n'est PAS couvert

- **`AreFriends` confronté au NATIF** : l'étage [D] fait jouer un tour d'équipe adverse, mais l'IA
  n'a porté **aucune active non-normale** sur les passes mesurées — le compteur est alors figé par
  `IsActiveAbilityCountedAsUsed`, pas par `AreFriends`. Le probe l'**écrit** (`NON CONFRONTE`) au
  lieu de le compter comme un vert. Le gate forgé hors-ligne, lui, reste inconditionnel.
- **Un cap `>= 2`** serait indiscernable : le montage ne monte qu'à 2. Le `maxLevel = NULL` est
  **lu** au décompilé, pas mesuré au-delà de ce point.
- L'état d'ability inscrit (`passiveAbilityState`) et la hiérarchie `0` : lus, sans observable —
  le behaviour de 1330 ne lit aucun `ConfigVar`.

## 4. La garde, VUE ROUGE

Deux mutations adversariales du SOURCE, chacune rejouée sur le fichier complet :

- **M1** — l'entrée du registre commentée : **7 failed / 6 passed**.
  `1330 doit etre inscrite sous la cle de l'ACTIVE 1195 dans le registre du dict
  GetPassiveHelperAbility` ; `registre vide -> meme compteur : l'INSCRIPTION n'est pas mesuree` ;
  `assert 0 == 1` puis `assert 1 == 2` sur les deux étages.
- **M2** — `IsActiveAbilityCountedAsUsed` court-circuité à `True` : **3 failed / 10 passed**, tous
  dans le témoin négatif (`le PORT a compte une attaque normale que le natif ignore`,
  `assert 1 == 0`). **`chaine` reste VERT sous M2** — c'est exactement ce que le témoin négatif
  existe pour voir, et c'est mesuré, pas supposé.

Restauré : **15 passed**.

## 5. Résidus nommés

* **`#521-r4`** — les **cinq** autres entrées de `GetPassiveHelperAbility` sont
  registered-but-unported : `1032 Catalyst -> 1062 GuildBossRunAway`,
  `1070 BreathOfSilence -> 1128 BreathOfSilence_SetStart`,
  `1118 DoctrinaImperatives -> 1201 DoctrinaImperatives_SetStart`,
  `1148 DaemonicOrdnance -> 1244 DaemonicOrdnance_Crit`,
  `1189 CalibaniteGreatsword -> 1316 CalibaniteGreatsword_NormalAttackAdditionalDamage`. Le rail
  existe désormais : il ne manque que la classe et son inscription. **RECON FAITE (2026-08-07), le
  port reste à faire** — état détaillé au §5bis.
* **`#521-r5`** — **RÉSOLU (2026-08-07)**, `case-523r2-523r4-521r5-trois-lectures-sans-observable.md`
  §3. Les deux registres lisaient bien deux substrats différents, et c'était un artefact du port :
  `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities` itère
  `List<T>.GetEnumerator(config@+0xa0)`, **le même champ** que celui sur lequel
  `...$$AddConfiguredAbilities` boucle pour `AddActiveAbility` → `GetPassiveHelperAbility`. Les deux
  registres passent désormais par la même lecture tri-état. Volet 2 recensé : **291** rejeux
  `load_state` en régime `auto` sans aucun transport ambiant (sur 550 lecteurs `auto` ; 243 héritent
  de la fixture, 16 lient eux-mêmes) — et `probe_448_r3_r1_r1_greffe_sans_canal.py` **les blanchit
  tous les 291** parce qu'il aplatit son graphe qualifié en noms nus (résidu **`#448-r5`**).
* **`#521-r3`** (ouvert par #521, toujours OUVERT) — `entities/triggers.py::HasTrait` porte encore
  l'idiome `any(...)` que #521-r2 a réfuté sur son voisin `HasFaction`. Ce cas ne le tranche pas :
  les deux `HasTrait` de 1330 reçoivent un sélecteur **mono-unité** (`actor@+0x48`).
* **`#486-r22`** — rien ne DÉCLENCHE la régénération d'un cache de verdict quand du code entre, et
  `origin/master` porte **35 divergences** invisibles du régime normal. Détail et chiffres : §6.

## 5bis. `#521-r4` — la RECON des cinq, et pourquoi le port n'est PAS une formalité (2026-08-07)

Aucune des cinq n'est portée. Ce qui suit est LU (décompilé, ou slot de vtable au runtime quand le
corps est dédupliqué) ; ce qui reste ouvert est nommé.

| helper | porteur de l'ACTIVE | gate | artefact natif |
|---|---|---|---|
| `1062 GuildBossRunAway` ← `1032 Catalyst` | `tyranBossHiveTyrantLeviathan` — **npc SEUL** | greffe à instruire | `On(0x1b = MatchEnd, true)` → `AttackTiles(Owner@+0x30)` |
| `1128 BreathOfSilence_SetStart` ← `1070 BreathOfSilence` | **AUCUN** sur les 5 voies gameconfig | à trancher (trait / summon / tile) | trigger PARTAGÉ (ci-dessous) → `AddEffect(0x464 = 1124 BreathOfSilence_StartPosition, AbilityStateReference, Tiles(Owner@+0x30), null)` |
| `1201 DoctrinaImperatives_SetStart` ← `1118 DoctrinaImperatives` | `admecMarshall` — **DANS LE POOL** | ✅ | trigger PARTAGÉ → `AddDynamicStatModifierEffectToOwner(0x4df = 1247 ProtectorImperative, 0x10 = FixedArmor, 0, …)` |
| `1244 DaemonicOrdnance_Crit` ← `1148 DaemonicOrdnance` | `blackForgefiend` — **MoW spawnable** | ✅ | **CLASSE INTROUVABLE** (cf. plus bas) |
| `1316 CalibaniteGreatsword_NormalAttackAdditionalDamage` ← `1189 CalibaniteGreatsword` | `darkaCompanion` — **DANS LE POOL** | ✅ | `On(0x4a = AttackInAtomicGroup, false) & <DSLTriggers+0x20> & OwnerIsActor & IsNormalAttack & IsMeleeAttack & HasEffect(Owner@+0x30, 0x57d = 1405 CalibaniteGreatswordSweep, 0, 6)` → `Foreach(CalibaniteGreatswordAbility$$GetSweepAdditionalTargets(active), <lambda b__3_0>)` |

**Le `CreateTrigger` PARTAGÉ des deux `_SetStart`** — leurs corps sont ABSENTS de la table (l'absence
ne prouve rien) ; résolus par slot de vtable (`resolveMethodPtr`), `BreathOfSilence_SetStartAbility`
et `DoctrinaImperatives_SetStart` pointent **la MÊME adresse**, dont le propriétaire ghidra est
`IdunBattleLogic.Entities.Abilities.Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`
(nom ARBITRAIRE). Son corps rend `<DSLTriggers+0x30>`, que
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` construit :

```
this+0x30 = On(0x21 = AbilityInit, ownerNeedsToBeAlive = 0) & <this+0x70> & get_OwnerIsActor
this+0x38 = On(0x41,               ownerNeedsToBeAlive = 0) & <this+0x70> & get_OwnerIsActor
this+0x28 = <le `IsTurnOf(Owner)` de case-366-r1 §2>
```

`<DSLTriggers+0x70>` reste **non identifié** (posé hors d'`InitializeShared`) : c'est le dernier
verrou de lecture de ces deux ports.

**Le PIÈGE ANNONCÉ est RÉFUTÉ** : porter `1201` / `1316` ne réveille PAS `TotalActiveAbilityUsed`.
Ce facteur est lu par `is_active_ability_counted_as_used` quand l'ability **DÉCLENCHANTE** vaut 1118
ou 1189 — ce qui dépend des casts en bataille, pas de l'inscription du helper. Et le `CreateTrigger`
de `1316`, lu en entier ci-dessus, n'en contient aucun ; celui de `1201` est le trigger partagé, qui
n'en contient pas non plus.

**Ce qui reste ouvert, par ability** :
* `1244` — la classe n'existe sous AUCUN des noms essayés (`DaemonicOrdnance_Crit[Ability]` dans
  `Abilities.{Active,Triggered,Damage}.Loki`, `IdunBattle.Entities.Abilities.Triggered.Loki`) ; la
  seule voisine trouvée est `...Active.Loki.DaemonicOrdnance_RemoveCritChance`. À trancher par
  énumération des classes du namespace (RPC), pas par recherche de nom.
* `1070 BreathOfSilence` — `unit_map find --ability` rend **0 unité** sur les 5 voies dérivables du
  gameconfig ; un zéro de cet outil n'est pas une preuve de mort (#323). Les 4 voies non couvertes
  (trait / live-event / summon / tuile) restent à balayer.
* `1032 Catalyst` — porteur npc SEUL. La greffe est envisageable (`case-92` §5bis) puisque
  `GuildBossRunAwayAbility$$CreateTrigger` ne lit ni stat ni trait du caster, mais le vecteur
  `On(MatchEnd)` demande un montage qui atteigne la fin de match.
* `1201` et `1316` sont les deux CONFRONTABLES immédiats (porteurs dans le pool). `1201` est de très
  loin le moins cher : un seul nœud, et son effet `1247 ProtectorImperative` est **déjà porté**
  (`entities/effects/loki/imperative.py`). `1316` est une tranche complète (sélecteur de cibles de
  balayage + behaviour d'attaque additionnelle).

## 6. Le cache du cliquet — un signalement que j'ai d'abord rendu FAUX

Ce cas ajoute un consommateur à `probe_313_enum_mirror_bijection.py`, dont le **contexte de cache
EST le sha du fichier probe** : le modifier invalide donc **tout** le cache versionné, par
construction. J'ai d'abord refusé de le régénérer, sur ce constat :

> « le cache se réécrit de 330 lignes à **chaque run**, donc le commiter ne sert à rien »

**C'est faux, et la façon dont c'était faux vaut d'être écrite** : j'avais mesuré *un* diff après
*un* run, sans jamais vérifier la stabilité — exactement le raisonnement qu'un probe existe pour
interdire. Ce que la re-mesure rend :

| question | mesure |
|---|---|
| la régénération est-elle stable ? | **IDEMPOTENTE** — trois runs consécutifs, sha256 identique |
| quelle est l'ampleur réelle du diff ? | **75 lignes** (43+/32−). Les « 330 » comparaient à un `master` vieux de 15 commits |
| `origin/master` PUR, mode espion | **`rc=3`, 35 divergences** (1 519 sur disque / 1 527 recalculées) — **rouge PRÉEXISTANT** |
| mon arbre, avant régénération | `rc=3` — le contexte a changé, tout le cache est invalidé |
| mon arbre, après régénération | **`rc=0`, 0 divergence, 1 530/1 530** |
| le cache régénéré porte-t-il du code d'un autre agent ? | **non** — `worktree` : 0 occurrence, `.claude` : 0 ; ventilation 1 290 `scripts/` + 239 `engine/` + 1 `lib` (le vice de #434, vérifié absent) |

La livraison **améliore** donc l'état : 35 divergences → 0. Et le régime **normal** rend `rc=0` des
deux côtés — une entrée périmée est recalculée, jamais rougie, ce qui est précisément pourquoi la
dérive s'accumule sans que personne ne la voie. Résidu **`#486-r22`**.

⚠ **PIÈGE DE MÉTHODE, nommé parce qu'il m'a fait rendre un chiffre faux** : un arbre témoin extrait
par `git archive` n'est **pas un dépôt git**, donc l'étape qui itère le Python *suivi* n'y voit
**rien**. Elle a rendu « 1 294 divergences sur `master` » ; la re-mesure dans un vrai
`git worktree --detach` rend **35**. C'est le pendant exact de la règle du `CLAUDE.md` (« l'arbre
TÉMOIN doit voir les mêmes ENTRÉES que l'arbre mesuré ») — pour un balayage indexé par git, ces
entrées incluent **l'index git lui-même**.

## 7. Ce qui garde

* `scripts/python/tests/engine/runner/test_521r1_talons_used_abilities_live.py` — 15 tests : le
  registre (bon dict natif, et **absence** des trois autres registres — une double inscription
  incrémenterait de +2 et ressemblerait à un compteur qui monte), les cinq littéraux, l'identité de
  la constante `1420` écrite ici et lue par `custodes.py`, la forme DSL de l'arbre (`Foreach` d'un
  `If`, pas un collapse impératif), le SUBSTRAT et la CARDINALITÉ, les deux étages du compteur, le
  dégât coup par coup, les contre-épreuves, les gates forgés, le tour adverse, et le témoin négatif.
* `scripts/python/probe_521r1_talons_used_abilities.py` — la MESURE (montage + critères), foyer
  unique appelé par le test.

## 8. Ce que cette tranche a laissé ROUGE, et que la suite offline complète a trouvé (2026-08-07)

Deux rouges de `master` sortis du **même** fichier — `probe_521r1_talons_used_abilities.py` — en
rejouant la suite offline entière (16 failed / 3314 passed ; le cliquet a été retiré du pipeline de
PR le 2026-08-05, donc plus personne ne la jouait). Aucun des deux n'était attribué à un lot : ils
n'appartenaient à la tranche de personne, exactement le mode d'invisibilité que `#457` décrit.

* **`test_host_inputs_offline::test_probe_273_passe`** — le state-file par défaut était
  `PYDIR / "logs"` = `scripts/python/logs`. Les deux emplacements sont gitignorés (`.gitignore`
  → `logs/` matche à tout niveau), mais `probe_273 --only-scan` étape 0 classe SORTIE sur le
  **premier segment** du chemin relatif au dépôt : `scripts/…` n'en est pas un. Écart mesuré :
  **71** probes écrivent `parents[1] / "logs"`, **1 seul** faisait autrement — et le probe FRÈRE
  de cette même tranche (`probe_521_talons_of_the_emperor.py:635`) faisait déjà juste.
* **`test_enum_ordinal_ratchet_offline`** — `TriggerEvent(event_id=14, …)` en contexte
  `EventTriggerType`. Le commentaire de la ligne au-dessus **nommait déjà** l'event
  (`On(0xe = UnitPostAbility)`) : l'ordinal étant juste, la faute était structurellement invisible.

⚠ **Reste, NON traité et hors périmètre du correctif** : `MOMENT_SHACKLE = 1184` (l. 70) porte le
même patron sur l'axe `ActiveAbilityType`, avec son nom en commentaire de fin de ligne. **Aucun
cliquet ne le relève** — l'étape 2 de `probe_283` vise les *kwargs* en contexte enum, pas les
*affectations de module*. C'est un trou de garde, pas un oubli de cette tranche.
