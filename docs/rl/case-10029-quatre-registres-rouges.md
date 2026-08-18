# #10029 — quatre cliquets de REGISTRE rouges : **une** prémisse expirée sur trois, **un** vrai défaut

Mesuré sur `master` = `8b2a2e35`, build `t6dpr4k06g`, arbre propre. Cinq échecs, quatre fichiers.

| fichier | test | verdict |
|---|---|---|
| `test_1023_omnissiahs_blessing_offline.py` | `test_l_effet_1365_n_a_PAS_de_classe_et_c_est_le_residu_1023r1` | **PRÉMISSE EXPIRÉE** |
| `test_1003_reliques_death_guard_offline.py` | `test_1003_registre_relique` | **PRÉMISSE EXPIRÉE** |
| `test_statmod_captured_channel_offline.py` | `test_no_unclassified_ability_state_rederivation_in_the_registry` | **LE CLIQUET A RAISON** |
| `test_359r5_selector_only_event_order_offline.py` | `..._porte_les_trois_playbooks_a_boucle_unique` + `..._les_deux_familles_sont_NON_VIDES` | **PRÉMISSE EXPIRÉE** (×2, une seule cause) |

Aucun fichier `engine/**` n'a été édité : les quatre registres accusés étaient **justes**, sauf
`POSE_TARGETS` — qui n'est pas dans `engine/` mais dans le probe.

---

## 1. `1365 MachineVengeance` — le cliquet d'ABSENCE a fait son travail, il est RETOURNÉ

Le test affirmait `"MachineVengeance" not in EFFECT_CLASSES` « pour qu'un port futur le fasse rougir
ICI ». #1081 (`1f3b4c9e`) a porté `IdunBattle.Entities.Effects.Loki.MachineVengeanceEffect` ; le
résidu `#1023-r1` est **déjà barré** dans `docs/rl/backlog.md` — c'est le cliquet, seul, qui était
resté en arrière.

Fidélité **re-lue** sur `t6dpr4k06g` avant de retourner l'assertion —
`IdunBattle.Entities.Effects.Loki.MachineVengeanceEffect$$CreateEffectDamageBonusForAttack` :

    EffectBonus.ForPercentIncrease( get_OwnerIsCaster,
                                    Multiply( Get(<config const 7>), EffectLevel(Effect@Sel+0x38) ) )

et `7` est bien un `IdunBattle.Entities.Enum.EffectConfigType` (`frida/enums.tsv` :
`7=MachineVengeanceExtraPct`), **pas** un `AbilityConstantType` — le port l'écrit ainsi et lit
`BC.Effect`, jamais `gameconfig.ability("MachineVengeance")` (qui rend `None`).

**Ce que le cliquet garde maintenant, et que personne d'autre ne garde : le RACCORD.** La classe
prise isolément (+5 %/niveau, la constante depuis `BC.Effect`, le tri-état du niveau, le gate
`get_OwnerIsCaster`) est gardée par `test_1081_foyer_factory_offline.py` ; la redupliquer aurait
fait deux rouges pour une cause. Ce qui n'est gardé qu'ici : la pile que `OmnissiahsBlessing`
DÉPLACE est bien celle que le canal dégât LIT. Si `1365` sortait d'`EFFECT_CLASSES`, les instances
posées redeviendraient des `BaseEffect` **muettes, sans erreur**.

Contre-épreuve jouée (3 mutants, 3 rouges) : hors-registre → rouge ; constante de `BC.Effect` figée
à 20 → rouge (80 lu au lieu de 20×4) ; `_effect_level` constant → rouge sur le bras à 7.

**Deuxième prémisse périmée dans le même fichier, et elle était VERTE.**
`test_NON_MORSURE_MESUREE_le_flag_onlyActive_n_est_pas_separe_par_ce_montage` justifiait sa
non-morsure par « 1365 n'a aucune classe, donc pas d'`ActiveCondition` ». La raison est désormais
**native et plus forte** : le slot `CreateActiveCondition` du bloc de la classe est `return
<DSLTriggers+0x70>` = `YesTrigger` (l'effet est toujours actif), donc `onlyActive` ne peut rien
séparer — ni offline, ni en bataille. Un test dont la prémisse est fausse et l'assertion vraie reste
vert et **enseigne une chose fausse**.

## 2. `Lakrimae` — un id, DEUX classes natives ; le second volet a été porté

`RELIC_ABILITY_TRIGGERS["Lakrimae"]` porte désormais
`[LakrimaeAddContaminationAbility, LakrimaeSummonPoxwalkerAbility]` (#1144, `d3547dfb`). Les deux
classes natives existent dans le build :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Lakrimae_AddContamination_Ability$$CreateTrigger`
et `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Lakrimae_SummonPoxwalker_Ability$$CreateTrigger`
— patron `DaemonfleshPlate`. Le « volet `AddContamination` » de l'en-tête était le **périmètre du
cas**, jamais une affirmation d'unicité.

Le bras figeant `== [une seule classe]` est mis à jour, et **doublé d'un invariant structurel** qui
rend la seconde entrée légitime plutôt que suspecte : même `TRIGGERED_ABILITY_ID` (1541),
`event_id` **distincts** (si les deux écoutaient le même vecteur, l'une serait morte et le registre
mentirait sur sa couverture). Le détail du volet SUMMON reste gardé par
`test_462r4r1_lakrimae_summon_poxwalker_offline.py`.

## 3. `POSE_TARGETS` — le seul vrai défaut, et c'est une RÉCIDIVE de #943

Trois classes de stat-mod entrées au registre sans classification de leur feuille de pose :
`BladeOfTheAncestors_Effect`, `HealingBalms_ExtraCritChance`, `HealingBalms_ExtraCritDamage`.
C'est **le gisement que notre propre cadence de portage alimente**, exactement comme
`TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE` — sauf qu'ici **rien ne l'annonce au commit** : le
cliquet ne mord qu'après le merge, sur `master`. Il a déjà mordu ainsi le 2026-08-10/11 (#943).

Les trois feuilles **relues** sur `t6dpr4k06g`, argument par argument :

* `IdunBattleLogic.Entities.Abilities.Active.Loki.HealingBalms_HealAbility$$ExecuteBehaviour` :
  `AddDynamicStatModifierEffect(targets = Target@Sel+0x60, source = Owner@Sel+0x30, 0x5df,
  statType 10 = CriticalDamage, AbilityStateReference, TurnsFromRounds(ConfigConst(0x5de,
  Owner@+0x30, 0x45)))`, puis le même avec `0x5e0` / statType 9. La **source est explicite**
  ⇒ `EffectComponent.SourceUnit` désigne le POSEUR ⇒ **SRC**, régime de `TwistedScience_ExtraHp`.
* `IdunBattleLogic.Entities.Abilities.Active.Loki.BladeOfTheAncestorsAbility$$CreateBehaviour` :
  `AddEffect(0x5d1, AbilityStateReference, targets = Owner@DSLSelectors+0x30, turns = null)`
  ⇒ porteur == poseur, et le `GetAbilityState(this)` que lit
  `IdunBattle.Entities.Effects.Loki.BladeOfTheAncestorsBuffEffect$$ApplyModification` est l'état
  d'ability du porteur ⇒ **OWNER**. (Ce n'est pas un `AddStat*StatModifierEffect` : l'effet natif
  pose lui-même ses deux `ChangeStat` — la question de `POSE_TARGETS` reste la même.)

Aucune n'est **CROSS** ⇒ aucune bascule sur `captured_stat_mod_amount()` n'est requise.

**Le cliquet pouvait passer VERT à VIDE, et ça n'est pas resté.** `assert not bad` sur un
recensement vide se serait tu exactement quand il aurait dû crier. Le cran ajouté est un
**INVARIANT, pas un seuil** : toute entrée de `POSE_TARGETS` doit s'apparier à une ligne du
recensement. Contre-épreuve : 24 entrées / 43 lignes / **0** orpheline en nominal ; amputer
`EFFECT_CLASSES` d'une seule classe classée en rend **1**.

## 4. `_MAKE_DMG_SELECTOR_ONLY` — le critère était mal NOMMÉ, le registre n'avait pas dérivé

Deux entrées légitimes ajoutées depuis : `1154 TacticalPrecision` (#976, `760b9809`) et
`1170 ExplosivePresents` (#909-r7, `fc8117f2`). Les deux corps **relus** :

* `IdunBattle.AI.Playbook.Loki.ExplosivePresentsPlaybook$$MakeDamagePredictions` : **un seul** appel
  à `GenerateAttackPredictions(caster, casterPosition, target, GetTargets(), VigilanceEternalAbility$$GetDamage, ...)`.
* `IdunBattle.AI.Playbook.Loki.TacticalPrecisionPlaybook$$MakeDamagePredictions` : **un seul** appel
  à `GenerateMultiHitAttackPredictions`, dont le sélecteur dépend de la branche `WillBeCharging`
  (`GetNonChargingAttackTargets()` / `Target@DSLSelectors+0x60`).

Aucun batch `<Target>` séparé dans les deux cas — la boucle vit dans le générique
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateAttackPredictions`,
**relu** lui aussi : il évalue la formule de dégât une fois, `Select`e le sélecteur, puis émet un
`IdunBattle.AI.Playbook.ProbableDamageEvent` **par entité** ; l'argument `target` ne sert qu'à
construire les `AbilityEntities`.

⇒ la forme A a **deux écritures**, observationnellement identiques, et le fichier ne connaissait que
la première : **A1** boucle explicite `GetEntitiesFromSelector` dans le `MakeDamagePredictions`
(1147 — relu, 1148, 1137) ; **A2** délégation du sélecteur à la surcharge plurielle (1154, 1170).
Le test s'appelait « les_trois_playbooks_**a_boucle_unique** » : c'est ce nom-là qui était faux.

**Et le second rouge du même fichier était un DOUBLON périssable.**
`test_les_deux_familles_sont_NON_VIDES` écrivait `len(_MAKE_DMG_SELECTOR_ONLY) == 3` — un cardinal
**nu**, qui ne nommait rien, en doublon du test d'égalité exacte juste au-dessus. Deux rouges pour
une cause, dont un qui n'apprenait rien. Il garde désormais ce qu'il est le seul à garder : la
**non-vacuité** et la **disjonction**, deux propriétés qui ne se périment pas quand le registre
grandit. Le `len(_FORME_B) == 5` **reste** : `_FORME_B` est une constante de ce fichier, et la vider
ferait disparaître les cinq tests paramétrés de la **COLLECTE**, sans rougir (#455-r3).

---

## Ce que cette tranche NE couvre PAS

* **Aucune confrontation live.** Les quatre items sont offline par construction (registres et
  formes de code). Le canal dégât de `1365` n'a pas été observé en bataille ici — `#1023` a son
  fichier live, qui n'a pas été rejoué.
* **`probe_181` / `probe_120_pre_unit_ability_fork --step 0` ne sont pas concernés** : la tranche ne
  fait entrer **aucune** ability dans `ABILITY_CLASSES` (aucun fichier `engine/**` édité). Les deux
  ont été joués pour le dire, pas pour l'espérer — `probe_181` rend `182 / 182 / 0 manquante`,
  `probe_120` rend `registre=182 ; litteral de ctor manquant: aucun`, rc 0 tous les deux.
* **Le gisement `POSE_TARGETS` reste sans garde AU COMMIT.** Il n'a que son cliquet post-merge, qui
  a maintenant mordu deux fois (#943, puis ici). Le pendant existe pour `TARGETING_OPTIONS` et
  `ABILITY_ATTACK_TYPE` sous forme de **règle de dépôt écrite dans `CLAUDE.md`** (« une ability qui
  entre au registre pose X dans le MÊME COMMIT ») ; rien d'équivalent n'existe pour une classe de
  stat-mod. La prose ne stoppe pas un comportement, mais son absence garantit la récidive.
* **`test_1003_registre_relique` et `test_462r4r1_registre_les_deux_classes_du_1541` figent
  maintenant la même liste.** C'est un doublon assumé — contrairement au `== 3` du §4, les deux
  **nomment** les classes et disent la même vérité, donc un rouge y est lisible des deux côtés.
