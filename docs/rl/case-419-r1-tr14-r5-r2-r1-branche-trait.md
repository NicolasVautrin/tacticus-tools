# `#419-r1-tr14-r5-r2-r1` — la branche TRAIT du dispatch d'attaque normale

**Critère binaire** : la troisième branche de la cascade de
`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` — le trait `0x7e7` menant à
`1030 Loki_NormalBossAttack` — est-elle portée ? **Oui, depuis cette tranche.** Elle est portée à son
RANG (troisième) et confrontée live sur 8 lignes (2 bras appariés × 4 unités), contre-épreuve
mordante sur la seule ligne PREUVE.

---

## 1. Le décompilé, relu — pas hérité

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, corps entier, dans l'ordre du
flux :

```csharp
// AddNormalAttackAbility(this, entity, config, activeAbilityState, triggeredAbilityState)
// config.Traits = `UnitConfiguration.Traits` (config@+0xd0)
if (config.Traits.Contains(0x0e)) return;                    // Erratic   -- garde -r4
if (config.Traits.Contains(0x15)) return;                    // Harmless  -- garde -r4

var fromPassive = GetCustomNormalAttackTypeFromPassive(this, config);      // config@+0xa8   -- -r1
if (fromPassive.HasValue) { type = fromPassive.Value; state = triggeredAbilityState; }
else {
    var fromActive = GetCustomNormalAttackTypeFromActive(this, config);    // config@+0xa0   -- -r2
    if (fromActive.HasValue) { type = fromActive.Value; state = activeAbilityState; }
    else if (config.Traits.Contains(0x7e7)) {                             // <-- CETTE TRANCHE
        state = activeAbilityState;
        type  = 0x406;
    }
    else {                                                                // repli generique -- -r2-r2
        var list = ListExtensions.FilterNewList(comp@+0x20, <Func statique mis en cache>);
        if (0 < list.Count) return;
        type  = this@+0x20;
        state = new AbilityState(new Level(1, 0), config@+0x74);
    }
}
ActiveAbilityComponent.Add(comp, type, state, null);
```

Trois lectures qui comptent :

* **Le `Contains` est le MÊME appel gshared que la garde `-r4`** :
  `System.Collections.Generic.List<__Il2CppFullySharedGenericType>$$Contains(config@+0xd0, &key,
  <RGCTX>)` avec la **même** donnée de RGCTX que pour `0x0e` et `0x15`. Le substrat est donc
  littéralement le même champ, `UnitConfiguration.Traits` — pas une autre collection de traits.
* **La branche TRAIT n'a PAS le court-circuit `FilterNewList`.** Ce filtre vit dans le `else`
  suivant, pas au-dessus de lui : une unité `Boss` reçoit son `1030` sans que la collection de
  l'`ActiveAbilityComponent` ne soit consultée. C'est ce qui rend le résidu `-r2-r2` indépendant de
  cette tranche.
* **`state = activeAbilityState`**, comme la voie ACTIVE — et non `triggeredAbilityState` comme la
  voie passive. Sans effet sur le port (qui ne modélise que le *type*), noté pour la complétude.

### 1.1 Les deux littéraux, QUALIFIÉS sur le build courant

Lus dans `data/symbols/rnca9r7q6c/frida/enums.tsv` (le build actif — vérifié : dossier de jeu et
table de symboles portent le même hash) :

| littéral | enum | valeur |
|---|---|---|
| `0x7e7` = 2023 | `IdunBattle.Entities.Enum.UnitTrait` | **`Boss`** |
| `0x406` = 1030 | `IdunBattle.Entities.Enum.ActiveAbilityType` | **`Loki_NormalBossAttack`** |

⚠ **Aucun des deux ne s'infère d'un nom, et le gisement le prouve deux fois.** `UnitTrait` porte
AUSSI `Guild_Boss_01` (1045), `BossAdjutant_Old` (1040) et `MachineOfWar` (1049) — trois voisins
lexicaux, trois valeurs différentes. Et l'entier **1030 désigne `BeastSnagga` dans `UnitTrait`** :
c'est exactement le piège « même id, enum différent » du `CLAUDE.md`.

### 1.2 Ce que la fiche affirmait, et qui est FAUX — mesuré

La fiche de ce résidu annonçait un porteur « MACHINE OF WAR ». **Réfuté.** Le trait `Boss` (2023) a
**six** porteurs sur les 683 kits gameconfig, **tous `npc`**, et ce sont les **boss de guilde** :

```
adeptBossCelestineCE   admecBossBelisarius   darkaBossLion
deathBossMortarion     tauBossRiptide        tyranBossHiveTyrantLeviathan
```

`MachineOfWar` est un **autre** trait (1049), qu'aucun d'eux ne porte. La confusion aurait été
doublement coûteuse : une Machine **n'a structurellement jamais d'attaque normale**
(`IdunBattle.Entities.Factories.MachineFactory$$Build` n'appelle jamais `AddNormalAttackAbility` —
établi et confronté par `-r2`), donc chercher la branche sur une MoW n'aurait rien pu montrer.

---

## 2. L'ORDRE — ce qui n'était pas négociable

La branche TRAIT est **TROISIÈME**, et le natif l'écrit dans sa structure de blocs : le `else if` du
trait est le `else` du test `fromActive.HasValue`, lui-même dans le `else` de `fromPassive.HasValue`.

**Pourquoi c'était le point à établir en premier.** Une branche portée au mauvais rang donne un
résultat *juste* sur les cas isolés (le trait seul) et *faux* dès que deux sources coexistent — et
c'est la forme exacte de l'erreur qui valait **+102 %** sur la voie passive (#557, `templAggressor` :
natif `1299..1950` contre port `2628..3942`). Le montage de cette tranche **fabrique** la coexistence
au lieu de l'espérer : deux des quatre unités portent `Boss` **en plus** d'une source de rang
supérieur.

---

## 3. Ce que la substitution CHANGE — lu, pas supposé

Cette question n'est pas rhétorique : `-r2` avait trouvé que sa propre substitution (`1126
RogalDorn_NormalAttack`) ne déplaçait **aucun** chiffre. Ici, la lecture donne un résultat
**différent**, et il faut le dire.

### 3.1 L'ABILITY — un seul différentiel, le preset de ciblage

`IdunBattleLogic.Entities.Abilities.Active.Loki.Loki_NormalBossAttackAbility$$.ctor` et
`IdunBattleLogic.Entities.Abilities.Active.Loki.Loki_NormalAttackAbility$$.ctor` sont
structurellement **identiques** : même classe de statics, recopie de 0x40 octets de `TargetingOptions`,
puis `IdunBattle.Entities.Abilities.ADeprecatedActiveAbility$$.ctor(this, &opts, 0)`. Un seul écart :
le **preset** lu — `statics+0x00` pour la générique, `statics+0x80` pour la boss. Deux presets
distincts, donc potentiellement deux masques de ciblage. **Non lu ici** (le port ne fait pas passer
l'attaque normale par `TARGETING_OPTIONS`) → résidu `-r2-r1-r2`.

`Loki_NormalBossAttackAbility` n'a **que** son `.ctor` dans les tables — ni `PredictAttack`, ni
`ExecuteBehaviour`, ni `FindAttackWeapon` propres.
⚠ Cette absence ne **prouve** rien à elle seule (corps triviaux dédupliqués, cf. `CLAUDE.md`) ; ce
qui la corrobore est que `Loki_NormalAttackAbility` n'en a pas non plus — les deux héritent du même
socle.

### 3.2 LE PLAYBOOK — un différentiel RÉEL, et c'est `ShouldExecute`

| membre | `Loki_NormalAttackPlaybook` (69) | `Loki_NormalBossAttackPlaybook` (1030) |
|---|---|---|
| base | `ALoki_NormalAttackPlaybook<T>` → `ComparablePlaybook<T>(0x45)` | `ComparablePlaybook<T>(0x406)` **directement** |
| `CalculateCustomUtility` | `Fix64.FromInt(1)` | `Fix64.FromInt(1)` — **identique** |
| `MakeDamagePredictions` | slot `0x22` du service, un `ProbableDamageEvent`, liste de 1 | **même forme** |
| `ShouldExecute` | `!HasTriggeredAbility(target, 0x48) && utility > 0` | `utility > 0` — **PAS de gate** |

`IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$ShouldExecute`,
lu verbatim :

```csharp
if (UnitExtensions.HasTriggeredAbility(target, 0x48)) return false;   // 0x48 = 72 = Explosive
return attackHealUtility > Fix64(0);
```

contre `IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$ShouldExecute` :

```csharp
return attackHealUtility > Fix64(0);
```

`0x48` = 72 = **`Explosive`** dans `IdunBattle.Entities.Enum.TriggeredAbilityType`. Sémantiquement :
l'IA refuse d'attaquer au corps une cible qui **explose**… sauf si elle est un boss.
**Aucune des deux formes n'est portée** (le port n'a pas de `should_execute` sur
`ComparablePlaybook`) → résidu `-r2-r1-r1`, ouvert et chiffré en §7.

⚠ **Conséquence honnête sur la portée de CETTE tranche** : parce que le gate n'est porté ni dans un
sens ni dans l'autre, le port de la branche TRAIT **ne déplace aujourd'hui aucun chiffre de décision**.
Ce qu'il déplace — et ce que la mesure du §5 confronte — c'est l'**identité de l'attaque normale**,
c'est-à-dire le champ que la fabrique écrit. Même statut que `-r2`, dit ici pour que personne n'aille
chercher un écart qui n'existe pas encore.

---

## 4. Confrontabilité — montage ÉCRIT, comme `-r4`

Zéro porteur du trait dans le pool (les six sont `npc`). **Ce n'est pas « non confrontable »** : le
substrat `BC.Units[].Traits` est écrit, et c'est exactement ce que le volet `traits` de `-r4` a fait
pour `Erratic`/`Harmless` (eux aussi à zéro porteur).

Trois précautions, toutes issues des tranches précédentes :

1. **Le trait est AJOUTÉ à la liste d'origine, jamais substitué à elle** (`_traits_for`) —
   remplacer retirerait `Hero`/l'alliance et ferait varier autre chose que la seule variable étudiée.
2. **`P380.assert_survives`** sur chaque seed écrit : `buildNormalizedBC` ne doit pas réécrire ce
   qu'on vient de poser.
3. **Le canal est un SUR-ENSEMBLE** (§5.1), donc il est contrôlé avant d'être utilisé.

---

## 5. La mesure — 8 lignes, 2 bras APPARIÉS

Board `MC1_67`, seed `9292901`, mêmes quatre unités, même roster, même seed dans les deux bras :
**seuls les `BC.Units[].Traits` diffèrent**. Le natif est lu sur
`decisionView.units[].abilities` `kind == "normal"` (= `ActiveAbilityComponent.NormalAttackType@0x28`) ;
le port est interrogé sur les **canaux de production** (`UnitContext.traits` /
`.passive_abilities` / `.active_abilities` seedés par `scene.build_predictor`, lus par
`entity_trait_names`).

`probe_419r1tr14r5r2r1_trait_normal_attack.py --volet trait`, **8/8 conformes** :

| bras | rôle | unité | `PassiveAbilities` | `ActiveAbilities` | `Boss` mesuré | natif | port |
|---|---|---|---|---|---|---|---|
| `boss` | **preuve** | `astraBullgryn` | `[]` | (origine) | oui | **`Loki_NormalBossAttack`** | idem |
| `boss` | ordre-pas | `orksNob` | `[1090 Boltstorm]` | (origine) | oui | `Boltstorm_NormalAttack` | idem |
| `boss` | ordre-act | `eldarRanger` | `[]` | `[1124 PoundThemToDust]` | oui | `RogalDorn_NormalAttack` | idem |
| `boss` | témoin | `necroWarden` | `[]` | (origine) | **non** | `Loki_NormalAttack` | idem |
| `ctrl` | **preuve** | `astraBullgryn` | `[]` | (origine) | non | **`Loki_NormalAttack`** | idem |
| `ctrl` | ordre-pas | `orksNob` | `[1090 Boltstorm]` | (origine) | non | `Boltstorm_NormalAttack` | idem |
| `ctrl` | ordre-act | `eldarRanger` | `[]` | `[1124 PoundThemToDust]` | non | `RogalDorn_NormalAttack` | idem |
| `ctrl` | témoin | `necroWarden` | `[]` | (origine) | non | `Loki_NormalAttack` | idem |

**Ce que chaque ligne établit :**

* **`boss`/preuve vs `ctrl`/preuve** — la MÊME unité, à un seul trait près, passe de
  `Loki_NormalAttack` à `Loki_NormalBossAttack`. C'est le discriminant énoncé avant la mesure : un
  port qui retomberait sur l'attaque générique répondrait `69` là où le natif dit `1030`.
* **`boss`/ordre-pas et `boss`/ordre-act** — le trait COEXISTE avec une source gagnante, et le natif
  rend celle de la source, **pas** `1030`. C'est la seule paire de lignes qui lit l'ORDRE. Elles ne
  prouvent rien seules (les deux modèles y coïncident quand le rang est juste) : elles **bornent**.
  Leurs contrôles appariés dans `ctrl` rendent la même valeur → ajouter `Boss` n'a rien changé, ce
  qui est précisément l'assertion.
* **témoin** — une unité qui ne reçoit le trait dans **aucun** bras. Sans elle, un montage mort
  rendrait des `69` partout dans `ctrl` et se lirait comme « la branche trait ne substitue pas ».

### 5.1 Le canal, contrôlé AVANT d'être utilisé

`combatSnapshot.units[].traits` est l'ensemble **effectif** que rend
`IdunBattle.Entities.UnitExtensions$$HasTrait` — un **sur-ensemble** de `UnitConfiguration.Traits`
(il inclut les traits accordés en bataille par `IdunBattle.Operations.AddTraitOperation$$AddTrait`).
Il n'est donc sûr que si `Boss` n'y entre **que** par `BC.Units[].Traits`.
`--volet canal`, **8/8 conformes** : `Boss` mesuré exactement sur les trois unités du bras `boss` qui
devaient le recevoir, absent des cinq autres lignes. Extrait :

```
[boss][preuve   ] astraBullgryn  traits=['BigTarget','Boss','Hero','Imperial']  contient Boss : True  (attendu True)
[ctrl][preuve   ] astraBullgryn  traits=['BigTarget','Hero','Imperial']         contient Boss : False (attendu False)
[boss][temoin   ] necroWarden    traits=['Hero','LivingMetal','Mechanical','Xenos'] contient Boss : False (attendu False)
```

Ce contrôle est **aussi** un cran du test live (`test_le_port_reproduit_le_natif_sur_les_huit_lignes`) :
un `Boss` venu d'ailleurs produirait un faux positif, un `Boss` non installé un faux négatif
silencieux.

### 5.2 La contre-épreuve MORD, et seulement là

Branche TRAIT coupée (littéral rendu impossible = strictement le port d'avant cette tranche) :

```
[boss][preuve   ] -> Loki_NormalAttack        MORD
[boss][ordre-pas] -> Boltstorm_NormalAttack   inerte
[boss][ordre-act] -> RogalDorn_NormalAttack   inerte
[boss][temoin   ] -> Loki_NormalAttack        inerte
[ctrl][*        ] -> (les quatre)             inerte
```

Une seule ligne bouge, et c'est la PREUVE. L'inertie des sept autres est la **réciproque** : un port
qui déborderait (trait décidant là où une voie de rang supérieur doit gagner) les ferait bouger.

---

## 6. Le port

`scripts/python/engine/services/custom_normal_attack.py` :

* `NORMAL_BOSS_ATTACK_TRAIT = "Boss"` / `NORMAL_BOSS_ATTACK = "Loki_NormalBossAttack"` — deux
  **constantes**, pas une table : le natif n'appelle ici aucun `GetCustomNormalAttack`, il teste un
  littéral et pose un littéral. Le mirror doit avoir la même forme.
* `custom_normal_attack_from_trait(traits)` — appartenance simple. L'**ordre de la liste n'a aucun
  rôle** ici, contraste voulu avec les deux voies précédentes où « le PREMIER gagnant s'impose » EST
  la sémantique.
* `custom_normal_attack(..., traits=None)` — la branche en **troisième** position, atteinte seulement
  quand les deux voies ont rendu `None`. Tri-état par voie conservé : `None` = canal muet → repli
  `unit_trait_names(visual_id)` (délégué au foyer unique `engine.entities.traits.unit_trait`, jamais
  re-dérivé) ; une liste (fût-elle vide) = mesure.
* `substitutes_normal_attack(..., traits=None)` — threadé. ⚠ **Cette branche ne peut, seule, jamais
  changer la réponse de ce prédicat** (`Loki_NormalBossAttack` n'est la valeur d'aucune entrée de la
  table passive) ; elle est passée quand même pour que le prédicat interroge la cascade **entière** —
  une invariance de TABLE, pas de FOYER.

Les trois postes d'appel reçoivent la liste mesurée, via `entity_trait_names` :
`engine/playbook/prediction/normal_attack.py`, `engine/runner/abilities/loki/mv71.py`,
`engine/runner/operations/damage.py`. Même argument qu'en `-r2` : une face qui ne connaîtrait
qu'une **partie** de la cascade est exactement ce que les deux tranches précédentes ont fermé.

---

## 7. Résidus NOMMÉS

* **`#419-r1-tr14-r5-r2-r1-r1` — le gate `ShouldExecute` de l'attaque normale n'est porté d'AUCUN
  côté.** `ALoki_NormalAttackPlaybook<T>$$ShouldExecute` refuse l'action quand la CIBLE porte
  `HasTriggeredAbility(target, 0x48)` = `72 Explosive` ; `Loki_NormalBossAttackPlaybook$$ShouldExecute`
  ne l'a pas. Le port n'a pas de `should_execute` sur `ComparablePlaybook` → dégradation
  **permissive** (il propose une attaque normale que le natif refuse), exactement la signature de
  bug qui reste invisible en self-play. C'est le **seul** différentiel de décision entre `69` et
  `1030`, donc ce résidu est ce qui donnerait un effet observable à la présente tranche.
  **Confrontable** : `Explosive` (72) a un unique porteur, `LootObj_ExplOilDrum` (npc, **absent du
  seed BC**), mais le passif est greffable — `catalog_inject.graft_passive_ability` écrit les deux
  côtés requis (`BC.Units[].PassiveAbilities` **et** `BC.Abilities.PassiveAbilities['Explosive']`,
  absente du seed : vérifié, 194 entrées, pas celle-là). Bras discriminant : un attaquant face à une
  cible `Explosive` — le natif n'émet aucune action d'attaque normale sur elle ; le même attaquant
  avec `Traits += [Boss]` doit en émettre une. ⚠ Rayon de souffle : le gate porte sur **toutes** les
  attaques normales, pas seulement le cas boss.
* **`#419-r1-tr14-r5-r2-r1-r2` — les deux presets de `TargetingOptions` ne sont pas départagés.**
  `Loki_NormalAttackAbility$$.ctor` recopie `statics+0x00`, `Loki_NormalBossAttackAbility$$.ctor`
  recopie `statics+0x80` — deux presets **distincts** de la même classe. Les masques effectifs n'ont
  pas été lus. Premier geste : la `.cctor` de la classe de statics, comme pour le piège « preset
  statique » du `CLAUDE.md` (mesuré en PR #126 : `0x4002` contre `0x4000` sur un même lot).
* **`#419-r1-tr14-r5-r2-r2` reste ouvert** (garde `FilterNewList` du repli générique) — **inchangé
  par cette tranche, et la lecture du §1 le confirme** : le filtre vit dans le `else` qui SUIT la
  branche TRAIT, jamais au-dessus d'elle.
* **`#419-r1-tr14-r5-r3` reste ouvert** (branche TERTIAIRE de la voie passive) — sans équivalent ici.
* **Le repli kit des traits reste une BORNE.** `custom_normal_attack(traits=None)` retombe sur
  `unit_trait_names(visual_id)`, et `BC.Units[].Traits` n'est PAS le `traits` du gameconfig (#264 :
  sur les 175 unités du seed, 5 en ont MOINS, 48 en ont PLUS). Aucun des six porteurs de `Boss`
  n'étant dans le seed, l'axe est inerte aujourd'hui — à rouvrir si un porteur y entre.

---

## 8. Ce qui n'est PAS couvert

* **Aucun écart de DÉGÂT n'a été cherché**, et c'est délibéré : §3 établit par lecture que le seul
  différentiel `69` ↔ `1030` est `ShouldExecute`, non porté. Chercher un écart de prédiction serait
  chercher ce que la RE dit absent.
* **Le trait accordé EN BATAILLE.** Le natif lit `UnitConfiguration.Traits` **à la fabrique** ; le
  port lit l'ensemble effectif (sur-ensemble). Les deux coïncident au tour 1, ce que le montage
  garantit. Un `Boss` accordé en cours de bataille ne changerait PAS l'attaque normale côté natif
  (la fabrique a déjà tourné) et la changerait côté port. Aucun `AddTrait` de `Boss` n'a été trouvé,
  mais l'absence n'a pas été prouvée exhaustivement.
* **Les six porteurs npc n'ont pas été confrontés eux-mêmes** — aucun n'est dans le seed BC, et le
  montage écrit rend la mesure indépendante d'eux.
* **Un seul board (`MC1_67`) et un seul seed.** Le dispatch de la fabrique ne lit ni terrain ni RNG ;
  la généralisation par board n'a pas été jouée.

---

## 9. Tests rejoués

| fichier | verdict |
|---|---|
| `test_419r1tr14r5r2r1_trait_normal_attack_live.py` (neuf) | **6 passed** |
| `test_419r1tr14r5_normal_attack_dispatch_live.py` | 6 passed |
| `test_419r1tr14r5_r1r4_normal_attack_table_live.py` | 9 passed |
| `test_419r1tr14r5r2_active_normal_attack_live.py` | 6 passed |
| `test_446_r1_boltstorm_followup_live.py` | 5 passed |
| `test_446_r3_repugnance_followup_live.py` | 5 passed |
| `test_419r1tr9_r4_r1_r2_normal_attack_gate_live.py` | 6 passed |
| `test_normal_attack_bonus_decision_live.py` | 8 passed |

**51 verts, 0 rouge.** Les sept fichiers de non-régression sont ceux qui consomment la cascade :
les trois tranches précédentes du dispatch, les deux molds de follow-up qui appellent `carries()`,
la gate `is_normal_attack` et le bonus d'action de l'attaque normale.

---

## 10. Livré

* `scripts/python/engine/services/custom_normal_attack.py` — les deux littéraux, la branche, son
  rang dans la cascade, le repli kit délégué.
* `scripts/python/engine/playbook/prediction/normal_attack.py`,
  `scripts/python/engine/runner/abilities/loki/mv71.py`,
  `scripts/python/engine/runner/operations/damage.py` — la liste de traits threadée jusqu'au prédicat.
* `scripts/python/probe_419r1tr14r5r2r1_trait_normal_attack.py` — deux volets (`canal`, `trait`),
  contre-épreuve.
* `scripts/python/tests/engine/test_419r1tr14r5r2r1_trait_normal_attack_live.py` — 6 gardes.
