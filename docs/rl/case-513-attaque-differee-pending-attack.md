# #513 — `APendingAttackEffect` : le foyer des attaques DIFFÉRÉES, et la phase 2 de `1069`

Build `rnca9r7q6c`. Résidu `#491-r1`. Le patron 2-PHASES — une ability ACTIVE pose un effet de bond,
et le DÉGÂT appartient à une ability TRIGGERED que cet effet déclenche au tour suivant — a **un seul
foyer natif**, `IdunBattle.Entities.Effects.APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal`,
partagé par **20** classes d'effet.

## 1. Le recensement — DÉRIVÉ, et livré avant tout port

`probe_513_pending_attack_family.py` (offline, `rc 0`). Fermeture **transitive** de la colonne
PARENT de `data/symbols/<build>/frida/classes.tsv` : **20 dérivées**, toutes à profondeur 1.
Chaîne : `APendingAttackEffect` ← `ABondEffect` ← `BaseEffect`.

| état | n | abilities |
|---|---|---|
| phase 1 PORTÉE, phase 2 à porter | **6** | 1018 `ValkyrieStrike`, 1069 `SeekerMissileFrequencyLock`, 1141 `OverwhelmingWrath`, 1142 `MalleusRocketLauncher`, 1160 `HeavyRailRifle`, 1188 `DevastatingRefrain` |
| phase 1 NON portée | **11** | 1071 `AnnihilatorBeam`, 1075 `TargetingProtocols`, 1083 `NeedsMoreDakka`, 1085 `EreWeGo`, 1094 `TheLantern`, 1124 `PoundThemToDust`, 1134/1135 `TheWailingDoom{Sweeps,Strikes}`, 1174 `SolarAtomizer`, 1215 `InstrumentsOfVengeance`, 1217 `TheLionsWrath` |
| phase 1 NON ÉTABLIE | **3** | `GazeOfMagnusEffect` (aucun `ActiveAbilityType` de ce radical) ; `OwnerPendingAttackEffect` et `TheWrathOfKhaineUnleashed_PendingAttackEffect` (leur `GetTriggeredAbilityType` n'est **pas une constante**) |

**Cette tranche livre la phase 2 de `1069`, une sur six.** Les cinq autres restent des résidus
nommés (§7) : leur `CreateBehaviour` n'est pas lu, et le foyer refuse une inscription sans phase 2
dispatchable (§4).

### Deux pièges de table, tous deux MORDUS

* **`GetAttackingUnitSelector` n'apparaît que DEUX fois** dans les 154 176 lignes de
  `ghidra/functions.tsv` (`ValkyrieStrikeEffect` et `InstrumentsOfVengeance_PendingAttackEffect`),
  alors que les 20 classes le surchargent. Le corps `{ return BondedEntitySelector(this); }` compile
  en un `jmp` — IL2CPP le **déduplique**, la table n'en publie qu'UN propriétaire ARBITRAIRE, et le
  nom de ce propriétaire ne dit RIEN de l'appelant. Conclure « ValkyrieStrike est la seule à
  surcharger » aurait été faux 18 fois.
* **Les deux classes de 1160 octets.** `OwnerPendingAttackEffect` et
  `TheWrathOfKhaineUnleashed_PendingAttackEffect` pèsent 1160 quand les 18 autres pèsent 1152 : elles
  portent un champ de 8 octets de plus, à l'offset `+0x480`. Le seul corps que ghidra publie
  (`return *(uint *)(this + 0x480)`, attribué à `TheWrathOfKhaine…`) lit **exactement ce champ** —
  les deux le déclarent, ghidra n'en nomme qu'une. Leur `TriggeredAbilityType` est donc **dynamique**,
  écrit au ctor : aucune valeur ne peut être écrite dans une table offline pour elles.

Le probe **assertionne sa propre couverture** : la table écrite doit couvrir EXACTEMENT la fermeture
dérivée, et chaque valeur doit NOMMER un membre de `TriggeredAbilityType`. Une classe neuve au
prochain build fait donc rougir plutôt que de disparaître en silence.

## 2. Le foyer, mirror 1:1

`APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` AJOUTE un `Triggered()` à l'`ArraySet`
que rend `ABondEffect$$CreateHandleTriggerAbilitiesInternal` (les trois retraits de bond, portés par
`triggers/bond_removal.py`) :

```
Triggered(
    On(0x15 = EventTriggerType.TurnStart_DelayedAttacks)
    & IsTurnOf( <klass+0x758>() ),                       # GetAttackingUnitSelector
    DSLBehaviors.TriggerAbility(
        entity = <klass+0x758>(), abilityType = <klass+0x768>(),   # GetTriggeredAbilityType
        actor  = <klass+0x758>(), caster = <klass+0x758>(),
        target = Owner@DSLSelectors+0x30,                # le PORTEUR de l'effet
        unitFeetTiles = null, selectionType = <pile>, ignoreUnitHavingAbility = <pile> )
    & DSLBehaviors.RemoveEffect( Effect@DSLSelectors+0x38 ) )
```

`APendingAttackEffect$$GetAttackTrigger` et `$$GetAttackBehaviour` exposent séparément les deux
morceaux, que le corps ci-dessus **inline** : trois lectures concordantes.

**L'ATTAQUANT EST L'ENTITÉ BONDÉE, ET C'EST MESURÉ, PAS DÉDUIT.** Sur 1069, l'effet `1123` est posé
SUR LA CIBLE et bondé AU CASTER : les deux candidats (`Owner` = le porteur, `BondedEntity` = le
caster) appartiennent à des **JOUEURS DIFFÉRENTS**, donc `IsTurnOf` les sépare d'un tour entier — il
suffit de regarder QUAND les PV tombent. Board `MC1_67`, seed 777, deux `endturn` **NUS** (aucune
unité n'agit entre les bornes) :

| pas | PV cible | `dumpRng` | effets |
|---|---|---|---|
| cast | 12049 | `(0, 624)` | 1136 sur le caster, 1122+1123 sur la cible |
| `endturn` #1 → tour ENNEMI | 12049 | `(0, 624)` | intacts (Markerlight 3 → 2) |
| `endturn` #2 → tour DU CASTER | **8625** (−3424) | `(4, 2)` | **1123 et 1136 RETIRÉS** |

⚠ **Le premier jet laissait l'IA jouer le tour ennemi** entre les deux bornes : le delta de PV
n'était attribuable à rien (l'IA tuait même le caster). Deux `endturn` nus, et le pas devient
mono-causal.

## 3. La phase 2 de `1069`, mirror 1:1

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SeekerMissileFrequencyLock_AttackAbility$$CreateBehaviour` :

```
hits      = AbilityConfiguration.GetNumberConstant( config@+0x20, 0x2f = nrOfHits )
<BaseTriggeredAbility.MinMaxDamage(this, abilityState)>        # appelée, RÉSULTAT NON UTILISÉ
effectSel = DSLSelectors.EffectFromOwner( Target@DSLSelectors+0x60, 0x463 = 1123 )
stateSel  = DSLSelectors.AbilityStateFromEffect( effectSel )
amount    = DSLFormulas.RandomAmount( ConfigVar(0xc minDmg, stateSel, config), ConfigVar(0xd maxDmg, …) )
profile   = BaseTriggeredAbility.GetDamageProfileOrDefault( this, 0x13 )
attack    = DSLBehaviors.AttackWithAbilityDamage( Caster@+0x48, Target@+0x60, amount,
                                                  Nullable(profile), hits, AbilityOrEffect(this), 2 )
remove    = DSLBehaviors.RemoveEffect( Caster@+0x48, (int?)0x470 = 1136, null )
```

* `MinMaxDamage` est **appelée et son résultat n'est consommé par aucun registre** au site d'appel.
  Elle construirait `RandomAmount` sur l'`abilityState` de l'ability DÉCLENCHÉE ; le montant
  réellement passé est l'autre, bâti sur l'état **figé dans l'effet 1123**. Elle ne consomme aucun
  tirage (les deux constructeurs rendent un NŒUD), donc ne pas la porter est bit-exact — **la porter
  tirerait deux fois**.
* `GetDamageProfileOrDefault(0x13)` = `config.GetDamageProfile() ?? 0x13` (corps LU). Le kit porte
  `damageProfile = HeavyRound`, donc le défaut n'est jamais atteint : l'écrire en dur serait un fit.
* **Le kit est PARTAGÉ par les deux phases.** `SeekerMissileFrequencyLock_Attack` n'a AUCUNE entrée
  gameconfig propre (une seule clé `SeekerMissileFrequencyLock`), et `this@+0x20` est pourtant non
  nul au runtime : c'est la MÊME `AbilityConfiguration` que l'active. Le site natif de cette
  attribution n'est pas RE'd (résidu #513-r3) ; ce que la mesure établit, c'est que `nrOfHits`,
  `damageProfile`, `minDmg` et `maxDmg` sont consommés **là**, pas au cast.

## 4. `is_melee=None` — l'écart valait exactement ×1,15, et le montage le portait

Premier jet : port **4307**, natif **3424**. Décomposition par étage (le port publie `base_min`,
`pierce`, `armor`, `did_block`, `rolls`, `per_hit`) :

```
base 8344   pierce 55   armor 2460   ->  6767 avant block  ->  4307        (port, is_melee=False)
                                          5884 avant block  ->  3424       (natif)
6767 / 5884 = 1.150
```

**Le `+15 %` est le `MarkerlightDmgBonusPct`, et la cible le porte à cause du MÊME cast.** Son bonus
est gaté `IsRangedAttack`. Écrire `is_melee=False` — ce que le kit `attackRangeType = "Ranged"`
invite à faire — l'ARME côté défenseur.

La lecture tranche dans le même sens : les **quatre** surcharges de
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` prennent
`(caster, target, amount, damageProfile, hits, abilityOrEffect, [options,] selectionType)` et la
chaîne de délégation ne fabrique qu'un couple `(damageProfile, hits)` : **aucune ne porte de bit
melee/ranged**. Le nœud ne transporte donc aucune nature de coup, ce que le port notait déjà pour le
DoT de tuile (`is_melee=None` ⇒ `IsMeleeAttack` ET `IsRangedAttack` tous deux FAUX). Le kit déclare
la portée de l'ABILITY (elle sert au ciblage) ; il ne déclare pas la nature du COUP sur ce vecteur.

Après correction : **3424 des deux côtés, 4 tirages des deux côtés.**

## 5. Le kit déclenché du caster était AMPUTÉ — et le gate était muet à un champ près

Le nœud `TriggerAbility` porte le gate `GetAbilityState` de
`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` : l'unité déclenchée
doit PORTER l'ability. Il refusait l'attaquant, et le missile ne partait pas.

Cause : `entity_triggered_ability_ids` retombait sur le kit **gameconfig**
(`triggered_ability_ids(visualId)`) parce que le canal MESURÉ (`unitAbilityStates`) n'était pas lié.
Mesure des deux :

```
gameconfig  tauMarksman -> [1119]
NATIF       TriggeredAbilityComponent -> [1119, 1127, 1131]     (`unitAbilityStates`, row entityId)
```

Les deux manquantes sont les abilities **DÉRIVÉES** de ses actives
(`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`, un dictionnaire peuplé au runtime,
donc **invisible du gameconfig**). La parade est celle que le dépôt a déjà : lier le transport
ambiant (`snapshot.bind_live_rpc`), ce que le harnais de tests fait et que le probe fait désormais.

⚠ **Le diagnostic n'a été possible que parce que le nœud PUBLIE `notCarrying`.** Sans ce champ, le
symptôme aurait été « `dispatched: True`, zéro dégât » — un vert qui ment.

## 6. Ce qui est porté

| Fichier | Contenu |
|---|---|
| `engine/runner/operations/triggers/pending_attack.py` | **NEUF** — le foyer : `PENDING_ATTACK_EFFECTS`, `pending_attack_tree`, `PendingAttackOnAttackersTurn`, `pending_attack_registry_entries` |
| `engine/runner/operations/triggers/dispatch/turn.py` | `delayed_attack_triggers` — le vecteur `On(0x15)`, le SEUL des cinq events de `StartTurnOperation` qui restait « rôle à mapper » |
| `engine/runner/operations/turnflow.py` | câblage du vecteur, **entre `0x14` et `0x16`** (ordre du décompilé) |
| `engine/runner/operations/triggers/dispatch/registry.py` | inscription dérivée dans `EFFECT_TRIGGERS` |
| `engine/runner/abilities/behaviours/lifecycle.py` | contrat de `TRIGGERED_ABILITY_BEHAVIOURS` élargi à `(state, owner_id, entities, ectx)` |
| `engine/runner/operations/triggers/loki/full_throttle.py` | mise à jour de la seule autre entrée du registre (résidu #513-r5) |
| `engine/runner/abilities/tau.py` | phase 2 (arbre + entrée de registre) ; `scale_from_source=True` sur la pose de `1123` |
| `probe_513_pending_attack_family.py` | le RECENSEMENT (offline) |
| `probe_513_seeker_phase2.py` | la MESURE (5 étages) |
| `probe_513_generalisation.py` | les 3 contre-épreuves |
| `tests/engine/runner/test_513_pending_attack_live.py` | la GARDE (8 tests) |

**Le critère d'inscription est la PHASE 2, pas l'appartenance à la famille.** Un effet inscrit sans
phase 2 dispatchable serait **effacé** par le `RemoveEffect(Effect)` du même `Triggered()` sans que
rien ne frappe — un verrouillage qui disparaît en silence, **pire** que le marqueur inerte d'avant.
`test_la_phase2_de_1069_est_inscrite` garde les deux inscriptions ENSEMBLE.

## 7. Validation

`probe_513_seeker_phase2.py` — **PROBE OK**, 5 étages, aucun dégénéré :

| étage | résultat |
|---|---|
| [1] cast | port == natif, `{caster:{1136}, cible:{1122,1123}}` — non-régression #491 |
| [2] tour ENNEMI | **témoin négatif** : 0 déclenché, 0 PV, 1123 encore là, des deux côtés |
| [3] tour DU CASTER | dégât **3424 = 3424** |
| [4] effets retirés | `1123` (foyer commun) ET `1136` (arbre de phase 2), des deux côtés |
| [5] tirages | **4 = 4**, MT calé sur `dumpRng` |

`probe_513_generalisation.py` — **PROBE OK**, 3 contre-épreuves :

* **G1** autre board (`C1_02`) → dégât **4022 = 4022**, 4 tirages = 4 (témoin NON NUL et
  **DIFFÉRENT** de celui de la mesure principale : l'accord n'est pas un artefact de scénario).
* **G2** **DEUX porteurs, DEUX cibles**, deux `1123` vivants au même `On(0x15)` → le port fire
  **2 fois**, attaquants et porteurs correctement appariés, dégâts **{4022, 5902} = {4022, 5902}**,
  **8 tirages = 8**. Un port qui ne firerait qu'une fois, ou qui intervertirait les deux attaquants,
  tombe ici — et l'ORDRE des deux tirs est contraint par l'égalité des deux valeurs.
  ⚠ Le montage a dû **borner sur `currentPlayer`** : après le 2ᵉ cast le jeu **auto-endturn** (toutes
  mes unités ont agi), donc un `endturn` en aveugle rendait mon tour — et faisait partir les deux
  missiles — AVANT la mesure de référence.
* **G3** attaquant déplacé à **distance 6** (portée de l'ACTIVE = 5) → le missile part quand même.
  Le `Triggered()` n'a que `On(0x15) & IsTurnOf(...)` : ni distance, ni ligne de vue. **OFFLINE PUR**
  (le natif ne peut pas être mis dans ce régime sans un tour d'IA) — résidu #513-r6.

`tests/engine/runner/test_513_pending_attack_live.py` — **8 passed**.
`tests/engine/runner/test_seeker_missile_frequency_lock_live.py` (#491) — **6 passed**.

**La banque impactée** : `test_448_r1_stormboyz_port_live` + `test_448_r1_r1_full_throttle_offline`
(**19 passed**), `test_living_metal_repair_live` + `test_287r1_no_action_available_offline`
(**27 passed**). Cliquets : `probe_181_targeting_gaps` (**121/121**, 0 manquante),
`probe_313_enum_mirror_bijection` (34 mirrors, 0 dette), `probe_365`, `probe_273 --only-scan`,
`probe_433_r1_identity_shortcircuit`, `probe_468_collision_numeros` — tous `rc 0`.
`audit_combat_ability_coverage.py` régénéré : **aucun diff** (1069 y reste `DAMAGE(HeavyRound)`,
c'est exactement l'angle mort #491-r2, encore ouvert).

**Un rouge PROUVÉ ANTÉRIEUR** (rejoué sur `origin/master` NU, HEAD détaché `a0d41a1c`, message
identique) : `test_endturn_order_live.py::test_deep_strike_landing_is_not_cancelled_by_the_tick`.
Il est OFFLINE et porte sur `EndTurnOperation`, pas sur le début de tour.

**Un rouge QUE J'AI CAUSÉ, trouvé par ma propre passe adversariale** :
`test_448_r1_stormboyz_port_live::test_L6_le_gate_GetAbilityState_a_ses_DEUX_bras` →
`TypeError: execute_full_throttle() takes 2 positional arguments but 4 were given`. Le commentaire
de `TRIGGERED_ABILITY_BEHAVIOURS` annonçait « VIDE par défaut » — il ne l'est pas : `full_throttle.py`
y inscrit `1134` à l'import depuis #448-r1. **Lire un dict au repos ne dit pas qui le peuple** ;
c'est la banque qui l'a dit. Le commentaire est corrigé au même endroit.

## 8. Ce qui n'est PAS couvert

* Les **cinq autres** phases 2 dont la phase 1 est portée (§7 résidus). Leur `CreateBehaviour` n'est
  pas lu ; le foyer les accueille sans modification (une ligne de table + un arbre + une entrée de
  `TRIGGERED_ABILITY_BEHAVIOURS`).
* Le **second `Triggered()`** de `SeekerMissileFrequencyLockTargetEffect` (résidu #513-r1) :
  `On(0xc = UnitActiveAbility) & TriggeringAbilityIs(<self>) & AreEqual(Caster@+0x48, Owner@+0x30)`
  → `GetRemoveEffectBehaviour()`. Il n'entre pas dans le régime mesuré (aucune ability active n'est
  castée entre le cast et le tir).
* Le régime **npc** des quatre porteurs npc de 1069, et le cas où l'attaquant MEURT entre le cast et
  le tir (le gate d'owner de la face EFFET est `mov al,1 ; ret`, donc le natif ne gate rien — mais ce
  n'est pas confronté ici).
* L'ordre du `op_BitwiseAnd` de la phase 2 : le décompilé ÉVALUE l'attaque d'abord et passe le
  retrait en PREMIER argument. Le port place l'attaque d'abord ; l'ordre est sans conséquence
  mesurable (1136 est un `BaseEffect` inerte, aucune stat-mod, aucun tirage). Résidu #513-r4.

## Résidus

* **#513-r1** — le 2ᵉ `Triggered()` de `SeekerMissileFrequencyLockTargetEffect` (retrait du
  verrouillage sur un NOUVEAU cast actif) n'est pas porté ; celui de
  `SeekerMissileFrequencyLock_AimingEffect` non plus (#491 l'avait déjà lu).
* **#513-r2** — le DÉFAUT `0x13` de `GetDamageProfileOrDefault` n'est pas modélisé : le kit fournit
  toujours son `damageProfile`, donc la branche est inatteignable ici. L'écrire serait un fit.
* **#513-r3** — le site natif qui attache l'`AbilityConfiguration` de l'ACTIVE à la TRIGGERED n'est
  pas RE'd. Le port lit la même entrée gameconfig, ce que la mesure valide, mais le mécanisme
  d'attribution reste une boîte noire (il vaut pour toute la famille).
* **#513-r4** — l'ordre du `op_BitwiseAnd` de la phase 2 (attaque/retrait) n'est pas tranché ; sans
  conséquence mesurable sur ce porteur.
* **#513-r5** — `execute_full_throttle` IGNORE les `entities`/`ectx` que le contrat du registre lui
  passe désormais, et rebâtit les siens (comportement strictement d'avant). Sur
  `...StormboyzStrike_MissAbility`, le sélecteur `caster` du nœud n'est pas forcément l'unité
  déclenchée : basculer changerait la sémantique de FullThrottle.
* **#513-r6** — G3 (attaquant hors portée au moment du tir) est **OFFLINE PUR** : mettre le natif
  dans ce régime demande un tour d'IA qui déplace l'attaquant, ce que le montage à `endturn` nus
  exclut par construction.
