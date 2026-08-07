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
  existe désormais : il ne manque que la classe et son inscription. ⚠ `1118` et `1189` sont
  **exactement** les deux ids du `HashSet` `ABILITY_COUNTED_ONCE_PER_BATTLE`
  (`…ActiveAbility$$ShouldAbilityOnlyBeCountedOncePerBattleAbility`) — les porter réveillerait le
  facteur `TotalActiveAbilityUsed`, aujourd'hui inerte faute de compteur observable.
* **`#521-r5`** — divergence de SUBSTRAT entre deux registres du même sous-système :
  `PASSIVE_HELPER_ABILITY_TRIGGERS` lit `config_active_abilities` (canal mesuré, tri-état) quand
  `ACTIVE_ABILITY_TRIGGERS` lit encore le seul kit gameconfig — donc aveugle à une active
  **greffée**, qui est le seul chemin de confrontation d'une ability à porteur npc. S'y ajoute que
  `probe_521_talons_of_the_emperor.py` ne lie pas `bind_live_rpc` : ses rejeux tournent en
  `no-transport`, tous canaux mesurés à `None` (ses verdicts restent valides — le repli gameconfig
  rend la même chose pour Atlacoya — mais c'est une fragilité, et elle a coûté une passe ici).
* **`#521-r3`** (ouvert par #521, toujours OUVERT) — `entities/triggers.py::HasTrait` porte encore
  l'idiome `any(...)` que #521-r2 a réfuté sur son voisin `HasFaction`. Ce cas ne le tranche pas :
  les deux `HasTrait` de 1330 reçoivent un sélecteur **mono-unité** (`actor@+0x48`).
* **`#486-r22`** — rien ne DÉCLENCHE la régénération d'un cache de verdict quand du code entre, et
  `origin/master` porte **35 divergences** invisibles du régime normal. Détail et chiffres : §6.

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
