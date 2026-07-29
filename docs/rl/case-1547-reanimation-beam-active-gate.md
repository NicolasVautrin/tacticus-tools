# 1547 `ReanimationBeam_Revive` — le rail TARGETS lit `EffectComponent.IsActive`

Residu nomme de `case-229-effect-triggers-active-inventory.md` (4e des 5 effectTypes en ecart ;
1077 a ete clos par `case-231-haze-transfer-active-gate.md`).

## 0. Question binaire

> Le `matches` du rail TARGETS de l'effectType **1547** teste-t-il, cote PORT, que l'effet source
> est ACTIF (`e.active`) — comme le fait le natif ?

**NON avant cette fiche.** `ReanimationBeamReviveTrigger` heritait `_ReviveEffectCore.matches`
(`engine/runner/operations/triggers/revive_effect.py`), qui gate sur `revive_used_this_turn`
(proxy PAR UNITE) et sur l'arbre `CreateTargetTrigger`, mais **jamais** sur le flag de
l'INSTANCE d'effet. Une instance 1547 seedee INERTE revivait donc, alors que le natif ne
l'evalue meme pas. **Gate pose** (une ligne dans le `matches` de la classe 1547).

## 1. Le gate natif, relu ligne a ligne (pas herite de #229)

`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTrigger` resout la def d'effet
dans l'`EffectsDatabase` par `EffectComponent+0x58` (l'`EffectType`), puis appelle SES DEUX
evaluateurs sur le meme effet :

    EvaluateEffectTriggerEffectAbilities(op, ev, ..., effectDef, ...)   // rail ArraySet
    EvaluateEffectTriggerTargets      (op, ev, effectENTITE, effectCOMPONENT, effectDef, ...)

Le mapping d'arguments est LU au call site : ce que `EvaluateEffectTrigger` recoit en `param_4`
(l'**entite**-effet) devient le `param_3` de `...Targets`, et son `param_3` (le
**`EffectComponent`**) devient le `param_4` de `...Targets`.

### Les DEUX lectures de `+0x5c` — les deux portent sur l'effet SOURCE

Elles ne different PAS par leur sujet (c'est le meme effet, celui qui porte le trigger) mais par
la FRAICHEUR du composant lu et par ce qu'elles commandent :

| # | emplacement | expression | ce qu'elle commande |
|---|---|---|---|
| 1 | avant la boucle | `if (*(char *)(param_4 + 0x5c) != '\0')` sur le `EffectComponent` **transmis par l'appelant** | early-out : `if (IsActive) { if (Targets@+0x50 == null) NRE ; if (Targets.Count == 0) return ; }` |
| 2 | **dans** la boucle PAR CIBLE | `lVar20 = GetComponent<EffectComponent>(param_3 /* entite-effet */) ; if (*(char *)(lVar20 + 0x5c) != '\0')` | **LE gate** : conditionne `ShouldTrigger` (slot 0x13 de la def) puis `Execute` (slots 0x15/0x14) |

Deux consequences que le port doit respecter :

- **La lecture #2 est le gate semantique.** Un effet INERTE entre bien dans la boucle sur ses
  cibles (la lecture #1 ne saute rien quand le flag est a 0) mais n'evalue **jamais** son
  trigger : ni `ShouldTrigger`, ni le behaviour. Cote port, l'endroit fidele est donc le
  `matches`, **avant** l'arbre — pas le collecteur.
- **Le composant est RE-CHARGE depuis l'entite a chaque cible.** Une desactivation survenue en
  cours de drain stoppe les cibles suivantes. Le pump collapse du port
  (`triggers/dispatch/core.py::evaluate_trigger_operation`) re-appelle `matches` par item : il
  rend cette re-lecture sans machinerie supplementaire.

### Le gate ne vaut QUE pour ce rail

`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities` n'accede
**jamais** a `+0x5c`. C'est necessaire : c'est ce rail qui porte les `ActivateEffect` capables de
RALLUMER un effet eteint. Gater `collect_effect_triggers` (voie 2 de `case-229` §4) eteindrait
les 17 triggers de ce rail. La garde `test_le_gate_ne_vaut_que_pour_le_rail_targets`
(`test_haze_of_corruption_transfer_live.py`, posee par #231) verrouille deja ce refus ;
cette fiche ne la duplique pas.

## 2. 1547 est bien du rail TARGETS — et son arbre ne porte AUCUN noeud d'activite

`IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger` (decompile) :

    OnPreDeath(entities@0x48, get_ReviveOnOverkill@vtable+0x738, 0, 0)
      & CanBeRevived(target@0x178, get_HealType@vtable+0x748)
      & CreateTargetFilter@vtable+0x758

`IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter` (decompile) :

    AreFriends(self@0x148, target@0x178)
      & HasTrait(target@0x178, 5 = Mechanical)
      & HasEffect(target@0x178, 0x609 = 1545 NanoscarabRepairProtocols, onlyActive = 0, 6 = Both)

Deux faits importants :

- L'arbre est un `CreateTargetTrigger` pur -> rail TARGETS -> **gate `IsActive` obligatoire**.
- Aucun noeud `IsEffectActive` / `HasEffect(..., onlyActive = 1)` n'y figure. Le port n'a donc
  PAS deja le gate « par l'arbre » (contrairement a `GhostRemoveOnSourceDeathInactive` ou
  `EarlyWarningOverrideHitReductionPurge`, cf. `ARRAYSET_READS_BY_TREE` du probe 229). En
  particulier, le `HasEffect` du filtre porte sur l'effet **1545 de la CIBLE** avec
  `onlyActive = 0` : il ne dit rien de l'activite de 1547, et le port a raison de n'y tester que
  `not e.consumed`.

## 3. Ce qu'est 1547, et qui le porte

- `EffectType.ReanimationBeam_Revive = 1547`, pose par l'active **1223 `ReanimationBeam`** de
  `necroReanimator` (`IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$.ctor`,
  `removeEffect = TRUE` -> one-shot DEFINITIF).
- Porteur : `necroReanimator` — trait `MachineOfWar`, kit `[ReanimationBeam,
  NanoscarabRepairProtocols]`. Variante NPC : `necroNpcMoWReanimator`.

**Confrontabilite : NON.** `python scripts/python/rl_duel.py build --list-pool` (rank 17) rend
97 unites regulieres + **8 MoW** (`adeptExorcist, astraOrdnanceBattery, blackForgefiend,
deathCrawler, orksRukkatrukk, tauBroadside, tyranBiovore, ultraDreadnought`) :
`necroReanimator` n'y est ni comme hero ni comme MoW, et ce n'est pas un summon. Son
`kind = lineup` de gameconfig est le piege documente (il MENT) ; le pool est la seule porte.

-> Validation par le harnais deja en place pour #79 : etat **capture LIVE** (board, stats,
traits reels via `load_state` sur un runner monte) + effet 1547 **injecte** dans `state.effects`
(`tests/engine/runner/test_revive_retrofit_offline_live.py`). C'est exactement ce que ferait la
pose native, et c'est le seul chemin qui met 1547 sur un plateau.

## 4. Le fix

`engine/runner/operations/triggers/loki/reanimation_beam.py` — override de `matches` sur la
SEULE classe 1547, qui lit le flag de l'instance puis delegue a `_ReviveEffectCore.matches` :

    if not self._instance_flag_is_set(state):
        return False
    return super().matches(state, ev)

Placement volontaire **sur la classe**, pas sur `ReviveEffectTrigger` (la base du rail EFFET) :
`RitesOfMorkaiReviveTrigger` (1502) partage cette base et fait l'objet d'une fiche distincte,
traitee EN PARALLELE — poser le gate dans la base aurait resolu les deux d'un coup et melange les
perimetres. Le solveur de 1502 a fait le MEME choix symetrique
(`case-229-1502-rites-of-morkai-active-gate.md`), et c'est ce qui a permis aux deux de lander sans
se marcher dessus. Les deux fiches concordent aussi, **independamment**, sur la desambiguisation
des deux lectures de `+0x5c` (§1). Le jour ou l'on voudra factoriser, remonter le gate dans
`ReviveEffectTrigger.matches` est une refactorisation mecanique.

`_instance_flag_is_set` mirroire `_ranged_auto_attack_flag_is_set` (1009, le seul gate deja
porte) : instance introuvable -> **True** (degradation PERMISSIVE, on ne fabrique pas un refus).
Le cas est inatteignable en production — `collect_effect_triggers` n'instancie ce trigger QUE
depuis une instance 1547 non consommee de `state.effects.by_unit[owner]`.

## 5. Rayon de souffle d'un `includeInactive` global au seed

`case-229` §3 rangeait 1547 dans « OUI, dans le rayon de souffle » par **deduction** (« porteur
unite => canal unite »), et #231 a REFUTE cette meme deduction pour 1077 par mesure. Pour 1547
la mesure est **impossible** : le porteur n'est pas montable, donc aucun etat live ne peut
contenir une instance 1547 a lire dans `readEffectsByUnit`. La ligne reste donc une HYPOTHESE,
et cette fiche ne la promeut pas.

Ce qui EST etabli, et suffit a justifier le gate :

- le mecanisme de seed inerte existe et est cable — `EffectFactory.create`
  (`engine/entities/effects/factory.py`) lit la cle `active` de l'entree captee et la reporte
  sur `BaseEffect.active` ; sans cle -> `True` ;
- `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` eteint **n'importe quel** effet
  (`ShouldBeActive` faux -> `DeactivateEffect` -> `+0x5c = 0`), ce n'est pas reserve aux effets a
  `CreateActiveCondition` propre. « On ne l'a jamais vu inactif » ne prouve donc rien
  (`case-229` §1).

## 6. Validation

### 6.1 Garde de non-regression (cliquet)

`tests/engine/runner/test_revive_retrofit_offline_live.py::test_beam_inactive_effect_does_not_revive`
(meme fixture `env` : runner monte, board `MC1_67`, seed 31337, capture live). Montage nominal
oppose a lui-meme, la SEULE difference etant le flag :

- face POSITIVE (`active = True`) -> la cible revit (temoin) ;
- face NEGATIVE (`active = False`) -> la cible reste morte, ET l'effet 1547 n'est PAS `consumed` ;
- entre les deux, `collect_effect_triggers` DOIT quand meme instancier le trigger : c'est ce qui
  PROUVE que le refus vient du `matches` du rail TARGETS et non d'un filtre pose au mauvais etage
  (le rail `ArraySet` n'a AUCUN gate natif -- l'y poser eteindrait les `ActivateEffect`).

**Contre-epreuve** (moteur restaure a `HEAD`, pre-fix — `git checkout HEAD -- reanimation_beam.py`) :

    tests/.../test_revive_retrofit_offline_live.py   1 failed, 10 passed
        -> AssertionError: revive par une instance 1547 INERTE (gate IsActive absent)
    probe_229_effect_triggers_active.py              RESULT: FAIL
        -> gaps 5 ; nouveaux : ['ReanimationBeamReviveTrigger']

**Apres restauration du fix** : `11 passed` ; `probe_229` -> `RESULT: OK`, gaps **4**
(`1186 GhostEffectRevive`, `1197`, `1201`, `1502` — 1502 reste bien en ecart, la preuve que le
gate n'a PAS debordé sur la base partagee).

### 6.2 Generalisation crafte — `probe_1547_reanimation_beam_active_gate.py`

La garde tue par l'helper `_kill` (hp=0 + `after_death_triggers`). Le probe generalise sur les
trois axes qu'elle ne couvre pas : **chemin de mort REEL** (attaque portee par
`Runner.apply(AttackUnitMessage)` -> `AttackDamageOperation` -> enqueue `MatchState.AddDeath` ->
drain `VerifyDeaths` -> `KillUnitOperation` -> `after_death_triggers`), **geometrie** (porteur du
beam DEPLACE loin de la victime — le filtre natif n'a aucun noeud d'adjacence) et **board /
roster / seed**. Trois faces par cellule : sans 1547 / 1547 actif / 1547 inerte. Les PV de la
victime sont cales EXACTEMENT sur le degat mesure a vide, pour que la mort soit letale mais
**non overkill** (`get_ReviveOnOverkill = 0` est l'AUTRE gate du meme trigger : on l'ecarte pour
n'observer que le flag — le probe le verifie et le signale si l'overkill survient).

| board | seed | roster (allies / ennemi) | dist beam-victime | sans 1547 | 1547 ACTIF | 1547 INERTE |
|---|---|---|---|---|---|---|
| MC1_67 | 777 | ultraTitus, bloodIntercessor / worldKharn | 11 hex | mort | **REVIVE** (hp 4986) | mort |
| C3_01 | 4242 | spaceRockfist, tauMarksman / necroDestroyer | 9 hex | mort | **REVIVE** (hp 4986) | mort |
| PVP_desert_01 | 31337 | templChampion, adeptRetributor / orksNob | 11 hex | mort | **REVIVE** (hp 4986) | mort |

`RESULT: OK`, **3 / 3 cellules concluantes**, 0 overkill. Dans les trois, l'effet 1547 est
`consumed = True` sur la face ACTIVE (le `RemoveEffect` du 2e volet, one-shot) et
`consumed = False` sur la face INERTE — le natif ne consomme rien de ce qu'il n'evalue pas.

### 6.3 Non-regression LIVE

| fichier | resultat |
|---|---|
| `test_revive_retrofit_offline_live.py` (5 beam + 5 PhoenixGem + la garde) | 11 / 11 |
| `test_rites_of_morkai_revive_live.py`, `test_narthecium_revive_live.py`, `test_tainted_narthecium_revive_live.py`, `test_overkill_gate_live.py` (la famille qui PARTAGE `_ReviveEffectCore`) | 32 / 32 |
| `test_haze_of_corruption_transfer_live.py` (dont la garde de rail #231), `test_revive_cancels_death_events_live.py` | 12 / 12 |
| `test_ghost_revive_live.py`, `test_fuelled_by_fury_revive_live.py`, `test_death_queue_ordering_live.py` | 32 / 32 |

**87 tests live verts**, plus `probe_229` OK.

## 7. Ce qui n'est PAS couvert

- **Aucune observation d'une instance 1547 REELLE** (porteur non spawnable) : le gate est valide
  sur une instance injectee, pas sur une pose native. C'est la meme limite que celle sous
  laquelle tout le port ReanimationBeam a ete accepte en #79.
- **Le cas MULTI-INSTANCES.** `_instance_flag_is_set` agrege par `any(e.active for e in insts)`,
  comme `_ranged_auto_attack_flag_is_set` (1009). Le natif, lui, raisonne PAR ENTITE-EFFET (une
  inscription de trigger par instance). L'agregation n'est observable que si un porteur cumulait
  DEUX instances 1547 d'activites differentes ; `AddEffectOperation` no-ope sur un meme-type deja
  present, donc il y en a 0 ou 1. Non teste, et volontairement aligne sur le precedent 1009
  plutot que devine.
- **L'interaction gate x OVERKILL.** Le probe ECARTE l'overkill (PV cales sur le degat) pour
  isoler le flag. Le comportement d'une instance INERTE sur une mort par overkill n'est pas
  mesure : les deux gates refusent, l'ordre entre eux est donc inobservable.
- **La ligne « rayon de souffle » de `case-229` §3 pour 1547** reste une hypothese non mesurable
  (cf. §5).
- **L'ecart restant** — `1186 GhostEffectRevive` (rail TARGETS, porteur TUILE, donc hors du canal
  `readEffectsByUnit`) : hors perimetre, fiche distincte. Tous les autres ont ete clos le meme
  jour, par des taches independantes : `1077` et `1201` (`case-231-...`, meme rail et meme
  remede), `1197` (`case-231-master-tutelaries`, rail `ApplyInternal`/`RevertInternal` — le
  remede n'y est PAS celui-ci), `1502` (`case-229-1502-rites-of-morkai-active-gate.md`, le jumeau
  de celui-ci).
- **La face DECISION** (prediction / playbook) de 1547 : non balayee.
