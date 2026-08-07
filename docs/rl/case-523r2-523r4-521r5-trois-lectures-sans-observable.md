# #523-r2 / #523-r4 / #521-r5 — trois lectures natives qu'AUCUN observable ne trahissait

Build `rnca9r7q6c` (= `data/symbols/CURRENT`, = le jeu chargé). Les trois résidus ont la **même
signature** : le port diverge du natif, et **aucun montage porté ne change de verdict**. C'est
pourquoi ils ont survécu, et c'est ce qui dicte la forme de la garde — offline, sur la feuille, pas
sur le bout de la chaîne.

## 1. `#523-r2` — `AddPersistentDataBehavior$$Execute` ACCUMULE

La docstring du port affirmait « `PersistData` **ÉCRASE**, il n'empile pas ». Vrai de la
**primitive**, faux du **behaviour** : le corps RELIT puis ADDITIONNE. Lu à l'assembleur autour de
`IdunBattle.Entities.Triggers.AddPersistentDataBehavior$$Execute+0x5a7` :

```
+0x591  lea   r9, [rbp+0x1f0]            ; slot `out` du TryGet
+0x5a7  call  <PersistentDataComponent$$TryGetPersistData<T>>
+0x62e  call  <Nullable<T>$$GetValueOrDefault>
+0x65b  mov   eax, dword ptr [rbp+0x1f0] ; eax = l'ancien
+0x668  add   dword ptr [rbp+0x1e8], eax ; <<< valeur_formule += ancien
+0x684  call  <PersistentDataComponent$$PersistData<T>>
```

`[rbp+0x1e8]` est le résultat de la formule VALEUR (c'est le `r9` passé ensuite à `PersistData`).
Le jumeau `IdunBattle.Entities.Behaviours.SetPersistentDataBehavior$$Execute` n'appelle **ni**
`TryGetPersistData` **ni** d'`add` : il passe directement la formule à `PersistData<T>`. La séquence
d'appels EST donc bien le discriminant, et son sens était **retourné**.

`default(T)` sur clé absente vaut `0` :
`PersistentDataComponent$$TryGetPersistData<T>` memset son `out` et n'appelle
`System.Nullable<T>$$.ctor` **que** sur succès ; le behaviour lit ensuite `GetValueOrDefault()`.
L'`add` est un `dword` ⇒ arithmétique `Int32`, ce que corrobore la formule valeur (même surcharge
`Calculate` que la `dataKey` int que le natif passe à `System.Int32$$ToString`).

**Pourquoi rien ne divergeait** — vérifié sur les trois vecteurs d'écriture de l'unique consommateur
porté (`HaywireMineAbility`), pas supposé : la clé est retirée par `HaywireMine_ResetAbility` sur
`On(0x28 = UnitFinishedTurn)`, qui précède TOUJOURS le `On(0x29)`
(`FinishUnitTurnOperation$$Execute` publie 0x28 puis 0x29). Aucun chemin n'écrit deux fois sans
`Clear` intercalé — `On(4)` prend une branche EXCLUSIVE du `If`, `On(0x29)` est gaté par
`AmountIsZero` (donc ancien = 0), et la branche `Custom` n'est atteinte que si le `If` d'origine
avait pris `TriggerAbilityDelayed`, donc SANS avoir écrit. Et même un `2` fabriqué ne changerait
rien : le seul LECTEUR est `AmountIsZero`, faux pour 1 comme pour 2.

⚠ **La distinction n'est pas cosmétique** : sous `AddPersistentData`, l'arbre
`Sum(GetPersistentData, Direct(1))` de `1546 HeavyWarpFlamer_AttackTracking` rendrait
`ancien + (ancien + 1)` — un facteur 2 sur le compteur. C'est la NON-accumulation de
`SetPersistentData` qui l'empêche, et elle est assertée.

## 2. `#523-r4` — `DSLSelectors$$Attacker` est CONDITIONNEL, et il est PARTAGÉ

```
If( AreEqual(<DSLSelectors+0x98>,
             DirectAbilitySelector(AbilityOrEffect(0x434 = MV71SniperDroneSquadAttack))),
    ParentSelector(Caster@+0x48),
    Caster@+0x48 )
```

- le littéral `0x434` est à l'assembleur (`IdunBattleLogic.Entities.DSLSelectors$$Attacker+0x38` :
  `mov edx,0x434`), invisible du décompilé — ghidra perd le registre dans
  `IdunBattle.Core.AbilityOrEffect$$op_Implicit` ;
- la nature conditionnelle du nœud rendu vient des XREFS de son `.ctor`, corps DÉDUPLIQUÉ : le nom
  ghidra `IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$.ctor` est celui d'un
  propriétaire ARBITRAIRE, l'ordre `(services, condition, then, else)` est celui du site d'appel ;
- la surcharge d'`AreEqual` retenue (celle appelée ici) reçoit en second opérande un
  `AbilityTypeSelector` ⇒ la comparaison porte sur des **ability-types**, jamais sur des entités.

**RECENSEMENT — les XREFS sont exhaustives : QUATRE consommateurs natifs, 5 sites d'appel :**

| consommateur natif | porté ? |
|---|---|
| `IdunBattle.Entities.Effects.Loki.HeadwoppasKillchoppaEffect$$CreateHandleTriggerAbilitiesInternal` | non |
| `IdunBattle.Entities.Effects.Loki.LifeStealEffect$$CreateTargetTrigger` | non |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ShieldOfFaithAbility$$CreateTrigger` **et** `$$CreateBehaviour` | non |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyWarpFlamer_AttackTrackingAbility$$CreateTrigger` (×2) | **oui** (#523-r1) |

Le rayon de souffle du résidu vaut donc aujourd'hui **exactement un module**. C'est ce qui justifie
un **FOYER** (`engine/runner/operations/triggers/base.py::attacker_of`) plutôt qu'un collapse
recopié : les trois autres l'hériteront au lieu de le refaire.

**Le seul point non épinglé, et il est nommé** : `<DSLSelectors+0x98>` est l'un des TROIS sélecteurs
sans argument que `IdunBattleLogic.Entities.DSLSelectors$$.ctor` met en cache en `+0x88/+0x90/+0x98`
(ctor commun dédupliqué ⇒ classes non nommables hors ligne ; `$$InitializeShared` ne remplit que
`+0x18..+0x80`). Deux seuls `AbilityTypeSelector` parameterless existent :
`CurrentAbilitySelector` (dont le `$$Select` lit `AbilityEntities+0x60`) et
`TriggeringAbilitySelector` (`+0x98` de l'`AbilityEntities`). Le second est écrit **après** le
behaviour d'une triggered et ne couvre que `On(0xd)` (case-292) — il serait NUL sur `On(9 = Attack)`
où `Attacker` est consommé. Le port lit donc `ev.ability_type`, son canal pour `+0x60`.

**NON CONFRONTÉ live, et c'est mesuré.** Sur le seul consommateur porté, `Attacker` n'entre que dans
`NOT AreEqual(Attacker, Owner)` et `AreFriends(Attacker, Owner)` : un drone et son parent sont dans
la MÊME équipe (`AreFriends` ne discrimine pas), et `AreEqual` ne différerait que si l'owner de 1546
ÉTAIT le parent du drone — il faudrait greffer le passif `MV71SniperDroneSquad` (porté par
`tauMarksman`, lineup) sur `thousSekhetar` **et** que l'attaque du drone porte un profil `Psychic`,
qu'exige le conjoint `CurrentAttackDamageProfilesContain(0xd)`. La branche est **inerte** ici. La
branche `else` est byte-identique au comportement d'avant ⇒ aucun montage live ne peut régresser.

⚠ **La garde a trouvé une VRAIE faute au premier jeu** : le foyer était importé en **forme A**
(`from ..base import attacker_of`), donc `monkeypatch`/substitution **NE MORDAIT PAS** — le test
qui prouve que le module CONSOMME le foyer serait passé vert sur un module qui l'ignore. Passé en
forme B (CLAUDE.md, les 28 fichiers rouges de #484).

## 3. `#521-r5` — les deux registres d'ACTIVE lisent le MÊME champ natif

`IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities(entity, config, activeAbilityState,
triggeredAbilityState)` ouvre sur
`System.Collections.Generic.List<T>$$GetEnumerator(config@+0xa0)` puis, par élément :

```
config@+0xa0 (ActiveAbilities)  -> StaticBattleRules.ActiveAbility$$HasDerivedTriggeredAbilities
                                -> ...$$GetDerivedTriggeredAbilities -> TriggeredAbilityComponent$$TryAdd
                                -> ...$$HasDerivedActiveAbilities / GetDerivedActiveAbilities -> ActiveAbilityComponent$$Add
config@+0xa8 (PassiveAbilities) -> StaticBattleRules.TriggeredAbility$$GetDerived{Triggered,Active}Abilities
config@+0xd0 (Traits)           -> StaticBattleRules.Trait$$GetTriggeredAbility / $$GetActiveAbility
```

`config@+0xa0` est **le même champ** que celui sur lequel `UnitFactory$$AddConfiguredAbilities`
boucle pour appeler `AddActiveAbility` → `GetPassiveHelperAbility` (#521-r1 §1). Faire lire deux
substrats DIFFÉRENTS aux deux registres était donc un artefact du port, pas une nuance du natif :
`ACTIVE_ABILITY_TRIGGERS` sur le seul kit gameconfig était **aveugle à une active greffée** — le
seul chemin de confrontation d'une ability à porteur npc. Les deux passent désormais par la même
lecture tri-état (`UnitContext.config_active_abilities`, canal `unitAbilityStates[].configActives`,
repli gameconfig sur `None`, aucune inscription sur `[]`).

**Deux chemins de plus, LUS ici et NON portés** (hors périmètre, nommés parce qu'ils sortent du même
décompilé) : la voie `config@+0xa8` → `StaticBattleRules.TriggeredAbility$$GetDerived*Abilities`
(une triggered dérivée d'un PASSIF) et `StaticBattleRules.Trait$$GetActiveAbility` (un trait qui
accorde une ACTIVE). Le port couvre `Trait$$GetTriggeredAbility` (`TRAIT_TRIGGERS`), pas les deux
autres.

### Volet 2 — les rejeux sans transport ambiant : **291**, et le recenseur existant les blanchit tous

Mesure (corpus `scripts/python/**`, 2 250 fichiers), critère = « le fichier porte un site
`load_state(...)` en régime `auto` (donc il DÉPEND de l'ambiant) et n'atteint ni le foyer de liaison
ni la fixture qui le lie » :

| | |
|---|---|
| lecteurs de `load_state` en régime `auto` | **550** |
| ambiant HÉRITÉ (`tests/`, fixture `live_session`) | 243 |
| ambiant LIÉ par le fichier | 16 |
| **SANS aucun ambiant** | **291** |

⚠ **Et `probe_448_r3_r1_r1_greffe_sans_canal.py` en rend `0`** — il **APLATIT** son graphe qualifié
en **noms nus** (`lieurs = {n for _m, n in reach_bind}`, 117 nœuds `(module, fn)` → 70 noms) avant
d'intersecter. Tout fichier portant un `main`, un `run` ou une `mesure` est donc déclaré « lie
l'ambiant », quel que soit son module : **291/291 blanchis à tort**, dont
`probe_521_talons_of_the_emperor.py`, celui-là même que #521-r5 accuse. Sa docstring dit
« CRITERE DERIVE, pas une liste de noms » — c'en est une, seulement plus grosse. Résidu **`#448-r5`**
(ouvert ici).

Le critère retenu pour la mesure ci-dessus est l'**UNION** de deux lectures, parce que chacune a
l'angle mort de l'autre : le graphe **qualifié** rate les liaisons faites au niveau MODULE et les
appels attributaires (`snapshot_module.bind_live_rpc(...)` de `probe_287r8`, `probe_513`) ; le nom
terminal du **foyer** rate les wrappers. L'union ne peut que BLANCHIR ⇒ elle borne les 291 **par le
haut**, ce qui est le sens sur lequel on ne veut pas se tromper.

## 4. Ce qui garde

`scripts/python/tests/engine/runner/test_523r2r4_521r5_persistent_data_attacker_substrat_offline.py`
(12, offline pur) : l'accumulation (1→2→3) et le `default = 0` d'`AddPersistentData` ; la
NON-accumulation de `SetPersistentData` ; l'invariance de l'observable `HaywireMine` (deux poses
sans `Clear`, puis `Clear` + repose) ; le littéral 1076 **écrit au site** (`probe_313` compare le
mirror au build, pas la valeur écrite) ; les trois branches d'`attacker_of` (else / MV71 / parent
absent) ; la consommation du FOYER par le seul port concerné (substitution en forme B) ; et le
substrat commun des deux registres dans les **deux** régimes — dont celui qui discrimine, la GREFFE
(kit gameconfig muet, canal mesuré parlant), plus le tri-état `[]` ≠ `None`.

**VUE ROUGE** — trois mutations du SOURCE, chacune appliquée puis révoquée, sur le fichier complet :

| mutation | rouges | ce qui tombe |
|---|---|---|
| l'accumulation retirée (`cumul = int(val)`) | **2/12** | `…ACCUMULE_au_lieu_d_ecraser` (`[1,1,1] != [1,2,3]`) et `…haywire_mine_ne_change_PAS_d_observable` |
| la branche MV71 désarmée (retour au collapse) | **2/12** | `…branche_MV71_rend_le_PARENT` et `…parent_absent_rend_un_ensemble_VIDE` |
| `ACTIVE_ABILITY_TRIGGERS` re-filtré sur le seul kit gameconfig | **1/12** | `…meme_substrat[True]` **seul** — le régime `[False]` reste VERT, et c'est exactement ce qu'il existe pour montrer : sans la GREFFE, les deux lectures coïncident |

Restauré : **12 passed**.

Non-régression LIVE rejouée (4 fichiers, **33 tests, 0 rouge**, avant ET après rebase) :
`test_523r1_heavy_warp_flamer_tracking_live.py` (8), `test_462_r4b_..._haywire_pose_live.py` (5),
`test_521r1_talons_used_abilities_live.py` (15), `test_589r1r1r1r1_empyric_ambush_reset_live.py` (5)
— les deux derniers exercent les deux registres dont le substrat a changé.

Les deux `DECLENCHEUR` de la famille #523 ont perdu leur glob indiscriminant `scripts/python/*.py`
(il retenait ces fichiers à chaque édition d'un des ~500 probes de la racine, dont **aucun** n'est
dans leur fermeture) ; `probe_486r15` : **PASS**, 69 déclarations dont 66 confrontées.

## 5. Résidus

* **`#448-r5`** — *le recenseur de canal aplatit son graphe qualifié en noms nus*. Cf. §3 volet 2 :
  291 faux blanchis sur 291. Réparer `binds_ambient` (comparer des `(module, fn)`, pas des noms) et
  lui donner l'union avec le nom terminal du foyer, puis décider quoi faire des 291 — le sous-lot
  qui compte est celui des rejeux qui **greffent**, déjà couvert (`0 site amputé sur 37 suspects`).
* **`#521-r4`** — reste OUVERT, cf. `case-521r1-...md` §5 (état d'avancement re-mesuré ici).
* **`#523-r3`** — inchangé.
* Deux slots de cache non nommés : `<DSLSelectors+0x98>` (§2) et `<DSLTriggers+0x70>` (conjoint du
  `CreateTrigger` partagé des `_SetStart`, cf. `case-521r1-...md` §5). Ni l'un ni l'autre n'est
  nommable hors ligne (ctor dédupliqué) ; les deux se trancheraient par la même voie que celle
  employée ici — le slot de vtable au runtime (`resolveMethodPtr`).

## Fichiers

* feuille : `scripts/python/engine/runner/abilities/behaviours/persistent_data.py`
* foyer sélecteur : `scripts/python/engine/runner/operations/triggers/base.py` (`attacker_of`)
* consommateur : `scripts/python/engine/runner/operations/triggers/loki/heavy_warp_flamer.py`
* substrat : `scripts/python/engine/runner/operations/triggers/dispatch/core.py`
* garde : `scripts/python/tests/engine/runner/test_523r2r4_521r5_persistent_data_attacker_substrat_offline.py`
