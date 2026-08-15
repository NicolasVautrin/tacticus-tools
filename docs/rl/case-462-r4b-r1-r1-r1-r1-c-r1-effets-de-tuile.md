# #462-r4b-r1-r1-r1-r1-c-r1 — les effets de TUILE dans la collecte d'effet-triggers

Le résidu ouvert par la tranche `-c` (PR #620) énonçait : « `collect_effect_triggers` est
**structurellement aveugle aux effets de TUILE** : il n'itère que `state.effects.by_unit` ».
La question posée était binaire : **le natif balaie-t-il, lui, les effets de tuile ?**

Réponse : **oui, et sans le moindre gate**. Mais la mesure a d'abord **déplacé l'accusation** — le
collecteur voit déjà les tuiles ; c'est le **gate d'owner** du dispatch qui les jetait.

> **ÉTAT FINAL de cette fiche** : `-c-r1` (2026-08-05) n'a tiré de cette RE que le cas TUILE, en
> gardant deux gates que le natif n'a pas. **`-c-r3` (2026-08-05, §7) les lève** : sur la face EFFET
> le port ne gate plus rien. Les §2 et §4 décrivent l'état intermédiaire et le disent.

## 1. La prémisse est FAUSSE au niveau du collecteur — `by_unit` contient DÉJÀ les tuiles

`EffectsState.by_unit` est clée par **id d'ENTITÉ**, pas par id d'unité. Le nom ment, et quatre
lecteurs du port en dépendent déjà en le disant :

* `triggers/base.py::TileEffectTrigger` — « boardGraph `t.id` = entity id, disjoint des ids d'unité
  → clé `EffectsState.by_unit` valide » ;
* `EffectsState.on_turn_end` §DOMAINE (#102) — `IdunBattle.Operations.EndTurnOperation$$RefreshEffects`
  n'itère pas les unités mais **toutes** les entités-effet : « aucune distinction porteur-unité /
  porteur-tuile dans le tick de durée » ;
* `snapshot.py::_load_tile_effects` — « la glace de LordOfTempests vit dans `by_unit[tile_id]` […]
  il n'y a pas deux modèles d'effet de tuile, il y en a un seul, alimenté par deux bouts » ;
* `triggers/tiles.py::dry_bush_fire_spread` — `state.effects.has_effect(tid, …)` avec `tid` de tuile.

**Mesuré** (`probe_462_r4b_r1_r1_r1_r1_c_r1_tile_effect_triggers.py --step collecte`) : sur un
`State` portant un effet du registre sur une entité-tuile, `collect_effect_triggers` rend **1
trigger**, `owner_id` = l'id de tuile. Le collecteur n'a jamais été aveugle.

## 2. Le trou réel est un étage plus bas : le gate d'owner de `evaluate_trigger_operation`

*(code d'AVANT `-c-r1`, conservé parce que c'est lui qui porte le vice ; l'état final est au §7.3)*

```python
if getattr(entry, "owner_is_tile", False) or getattr(entry, "owner_is_global", False):
    pass
else:
    owner = state.get_entity(entry.owner_id)
    if owner is None:
        continue                      # <- une TUILE tombait ICI
```

Une tuile n'est pas dans `state.entities` → `get_entity` rend `None` → `continue`. Le trigger
collecté était **jeté avant `matches`** (`--step gate` : **0** appel), sauf si sa **CLASSE**
déclarait `owner_is_tile`.

**Le vice est là** : le critère est **statique** (une propriété de la classe portée) alors que la
nature du porteur est **dynamique** (une propriété de l'instance d'effet). Une classe qui sert
plusieurs `effect_type` ne peut pas la déclarer — et il en existe déjà une :
`BondRemoveOnBondedEntityDeath`, dont l'artefact natif est la **BASE** `ABondEffect`, donc **une**
classe pour toute la famille (1077 et 1218 aujourd'hui ; 1113, 1308, 1402, 1022 dans la table).

## 3. Le natif — mesuré, build `rnca9r7q6c`

**Le registre est indexé par ENTITÉ-EFFET, jamais par porteur.**
`IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache$$AddEntity` teste si l'entité est une
entité-effet et appelle `$$AddEffect(this, entity, entity+0x20)` — la nature du **porteur** n'y
apparaît nulle part. `IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal` itère ce
registre et appelle `$$EvaluateAbilityOrEffectTrigger` par entrée.

**Sur la face EFFET, il n'existe AUCUN gate d'owner.** Dans la branche effet de
`$$EvaluateAbilityOrEffectTrigger`, le porteur est résolu par `EffectComponent+0x14`, puis :

```
owner  = <query>.GetEntity(effectComponent+0x14)
uVar1  = UnityEngine.U2D.IK.Solver2D$$DoValidate(owner, 0)      // corps DEDUPLIQUE = `return 1`
if (!uVar1) return;                                             // donc JAMAIS pris
... EvaluateEffectTriggerEffectAbilities(this, trigger, onlyNonAtomic, owner, effect, ...)
```

`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetEffectTrigger` a **exactement** la même
entrée. Le nom ghidra `UnityEngine.U2D.IK.Solver2D$$DoValidate` est celui du propriétaire
**arbitraire** d'un corps partagé (`return 1`) — même piège de déduplication qu'au §2 de la fiche
mère, et il se lève de la même façon : par l'**adresse** du corps.
`$$EvaluateEffectTriggerEffectAbilities` se contente ensuite d'écrire `owner` dans
l'`AbilityEntities` avant `ShouldTrigger`/`Execute` : aucun test non plus.

**Sur la face ABILITY, le gate existe mais est conditionné à `IsUnit`.**
`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` :

```
if (!ability.get_AllowForDeadOwner()) {                    // ITriggeredAbility slot 8
    if (EntityExtensions$$IsUnit(owner) && !UnitExtensions$$IsAlive(owner)) return false;
}
if (EntityExtensions$$IsUnit(owner) && UnitExtensions$$IsTriggersDisabled(owner)) return false;
```

⚠ **`IsAtomic` était un FAUX NOM (#10015)** — cette fiche l'écrivait, et il désigne en réalité une
AUTRE propriété (`ITriggerable` slot 0 = `get_AllowInAtomicMode`), lue par la MÊME fonction quelques
instructions plus bas sous `IMatchState` slot 22 = `get_InAtomicMode`. Le raisonnement de cette
section ne change pas d'un iota ; le nom, si. Détail : `docs/rl/case-10015-allow-for-dead-owner.md`.

Les deux gates sont **sous** `IsUnit`. Un porteur qui n'est pas une unité — une tuile — les traverse.

⇒ **La réponse à la question binaire : le natif ne distingue pas.** Le port avait donc bien un trou,
et le seul discriminant natif à mirrorer est `EntityExtensions$$IsUnit`.

## 4. Ce qui est porté — et ce que `-c-r3` en a fait

**État `-c-r1`** : `dispatch/core.py::_owner_is_tile_entity(state, owner_id)`, mirror d'`IsUnit` par
la négative — un porteur absent de `state.entities` mais présent dans `state.board.by_id` est une
entité-tuile, donc aucun gate ; l'ENTITÉ l'emporte ; sans board, `False`.

**État FINAL (`-c-r3`, §7)** : ce prédicat est **SUPPRIMÉ**. Il conditionnait un gate qui n'existe
plus — la face EFFET n'en applique aucun. La bifurcation est désormais
`dispatch/core.py::_owner_gate_applies(entry)`, qui décide **laquelle des deux fonctions natives**
`evaluate_trigger_operation` mirrore : `CanGetAbilityTrigger` (gates sous `IsUnit`) ou
`CanGetEffectTrigger` (aucun gate).

`owner_is_tile` **reste** sur `TileEffectTrigger` : il documente l'intention et porte les helpers
`_tile_coord`/`_unit_on_tile`. Il n'est plus lu par le dispatch.

## 5. Le trou est RÉEL et LATENT — et le dire fait partie du livrable

Croisement **dérivé du registre** (`--step registre`) : `EFFECT_TRIGGERS` = **31 `effect_type`** pour
**69 classes**, dont **15** `TileEffectTrigger` et **54** nues. Les cinq familles d'effet de tuile
qui ont des triggers — `Fire` 5, `TimeFlux`/`Echoes` ghost 1186/1284, `Contaminated` 1244,
`DespoiledGround` 1476 — déclarent **toutes** `TileEffectTrigger`.

Croisement **mesuré live** (7e test, board `MC1_67`) : les `effect_type` réellement portés par des
tuiles sont `[0, 11, 1297]` ; les `effect_type` du registre à classes exclusivement nues sont **26** ;
**intersection vide**.

⇒ **Aucun porteur NATUREL aujourd'hui.** Les quatre effets de bond posés sur des tuiles n'inscrivent
aucun trigger : 1113 et 1022 ont `get_RemoveOnBondedEntityDeath` **faux** ; 1308 et 1402 sont **hors
table** (bondé = MoW inatteignable, §7.4 de la fiche mère). C'est exactement ce qui a masqué le trou
**trois fois** : à chaque rencontre, une autre raison de non-portage suffisait à expliquer le silence.

## 6. Validation — la garde mord sur un porteur RÉEL, faute d'un porteur naturel

`test_462_r4b_r1_r1_r1_r1_c_r1_tile_owner_gate_live.py` — **7 verts**.

Le bras qui MORD prend l'effet de tuile le plus observable du jeu, sur un board et des unités réels
tirés du harnais : le `FireEffect` (5) et son DoT de 20 % des PV max. Trois mesures sur le **même
état** :

| bras | montage | attendu | mesuré |
|---|---|---|---|
| A | `FireTileDoT` intact | DoT > 0 (le montage brûle) | **352** |
| B | attribut de classe `owner_is_tile` **RETIRÉ** | DoT > 0 (la CLASSE ne décide plus) | **352** |
| C | B + attribution neutralisée | DoT **nul** | **0** |

B est l'invariant : **avant le correctif il rendait 0**. C attribue le passage de B au correctif et
à lui seul — sans lui, B pourrait tenir pour n'importe quelle autre raison.
⚠ **C a changé d'instrument en `-c-r3`** : il neutralisait `_owner_is_tile_entity` (le prédicat qui
RECONNAISSAIT la tuile) ; ce prédicat n'existe plus, et C force désormais `_owner_gate_applies` à
`True` — l'entrée est alors traitée comme une face ABILITY, où un porteur absent de `state.entities`
est écarté. Même chiffre, même rôle, autre accusé.

Contre-épreuves sur l'arbre, toutes MORDANTES, arbre restauré :

| mutation | rouges |
|---|---|
| C1 — prédicat de nature RETIRÉ du gate | **2** (mécanisme + le porteur réel, DoT 352 → 0) |
| C2 — gate SUPPRIMÉ (`or True`) au lieu d'être conditionné | **3** (portée, non-régression `alive`, attribution) |

Les autres bras : le collecteur voit les tuiles (contrôle positif, réfute la prémisse) ; un owner
**ni unité ni tuile** reste écarté (le gate est conditionné, pas supprimé) ; un porteur **unité
morte** reste écarté (le surplus §7 n'est pas élargi par accident) ; les ids d'unité et de tuile
sont **disjoints** (10 entités / 63 tuiles, chevauchement vide) — invariant que
`TileEffectTrigger` affirmait sans que rien ne le vérifie.

⚠ **Retirer `owner_is_tile` est un montage, pas un porteur.** Il n'existe aujourd'hui aucun effet du
jeu qui franchisse ce trou (§5) ; le dire est la seule façon honnête de rendre la garde. Le 6e test
garde cet **énoncé** : il rougira le jour où un `effect_type` porté par une tuile sera servi par une
classe nue — signal qu'un porteur naturel est apparu, pas régression.

**Non-régression : 64 verts** — `test_462_r4b_r1_r1_r1_r1_bond_removal_live` (4),
`test_tile_effect_dynamics_live` (5), `test_rad_saturation_live` (5),
`test_load_state_inactive_effects_live` (10), `test_haze_of_corruption_transfer_live` (9),
`test_master_tutelaries_active_gate_live` (5), `test_462_r4b_r1_r1_r1_neuroparasite_pose_live` (7),
`test_462_r4b_r1_r1_r1_r1_bond_removal_offline` + `test_trigger_ability_channels` (19).

## 7. `#462-r4b-r1-r1-r1-r1-c-r3` — les deux gates de surplus sont LEVÉS (2026-08-05)

Le résidu ouvert ici disait : sur la face EFFET, le natif n'applique **aucun** gate d'owner, pas même
« l'owner existe » ; le port en garde deux (porteur **MORT**, porteur **INTROUVABLE**). C'est vrai,
c'est re-vérifié, et les deux sont levés.

### 7.1 La RE, re-dérivée (build `rnca9r7q6c`)

Le corps partagé est lu **par ses octets**, pas par son nom :
`UnityEngine.U2D.IK.Solver2D$$DoValidate` = `b0 01 c3` = `mov al,1 ; ret`, **772 propriétaires** dans
la table. Il ne lit même pas son argument. `CanGetEffectTrigger(this, owner, effect, onlyNonAtomic)`
commence par lui, et la branche EFFET d'`EvaluateAbilityOrEffectTrigger` aussi ; ni l'une ni l'autre
n'appelle `IsUnit` ou `IsAlive`. En aval, `EvaluateEffectTriggerEffectAbilities` écrit `owner` **tel
quel** dans l'`AbilityEntities` (champ `+0x30` de sa frame) puis appelle `ShouldTrigger`/`Execute` —
aucun test supplémentaire.
`EntityExtensions$$IsUnit(null)` rend **faux** (lu : `if (entity == 0) return 0`), donc même la face
ABILITY ne gaterait pas un porteur absent.

### 7.2 Les trois questions, mesurées

**(1) Le natif évalue-t-il le trigger d'un effet dont le porteur est mort ? absent ?** — Oui aux
deux : il n'y a aucun gate à traverser. Le seul frein est que le porteur mort **n'a plus d'effets** :
`KillUnitOperation$$Execute` appelle ses **trois** `RemoveEffects(killed, step)` (littéraux 0, 1, 2).
⚠ Et ces trois appels ne sont gatés par **aucun** champ de `KillUnitOperationOptions` : les quatre
seuls tests sur `options` portent sur `+0x00`, `+0x44`, `+0x45`, `+0x46` et gatent `IsSteppable`,
`RecordDeathReason`, le flag `Overkilled` et une émission analytics — rien d'autre.

**(2) La fenêtre, et ce qui s'y passe.** Mesurée sur le pipeline de mort du port
(`probe_462_r4b_r1_r1_r1_r1_c_r3_gates_owner_effet.py --step fenetre`, et le bras live homonyme) : le
mourant est `alive=False` avec ses effets **non consommés** sur **EXACTEMENT trois** événements —
`On(3 = PendingDeathAdded)`, `On(1 = PreUnitDeath)`, `On(2 = PreUnitDeath_2)`. Dès `On(0 = UnitDeath)`
le premier `RemoveEffects(PreUnitRemove)` a tourné et `collect_effect_triggers` ne rend plus rien.
C'est la seule fenêtre où le gate `alive` mordait, et il y jetait **3 évaluations sur 3**.

**(3) Quels `effect_type` changent réellement ?** — **AUCUN, aujourd'hui**, et c'est la réponse
utile. Croisement dérivé du registre (`--step registre`, **re-dérivé après le rebase sur #629**, qui
a fait passer `EFFECT_TRIGGERS` de 31/69 à **32 `effect_type` / 71 classes** — 15 Tile, **56** nues,
**27** `effect_type` à classes exclusivement nues, **52** classes nues sans `fire_on_death`) : sur
les 56 classes NUES, les seules qui écoutent un événement de la fenêtre ont pour owner le **TUEUR**
(`EarlyWarningOverrideReactivateOverwatch`, `On(1)`), le **REVIVEUR** (`ReanimationBeamReviveTrigger`,
`On(1)`) ou le **porteur du bond** (`BondRemoveOnBondedEntityDeath`, `On(2)`/`On(0x25)`) — toutes
VIVANTES. Les deux classes entrées par #629 ne changent pas ce verdict : `BondRemoveOnRangeExceeded`
écoute `On(29 = UnitPositionChanged_2)`, hors fenêtre, et `BondRemoveOnBondedEntityDeath` sur
l'`effect_type` 27 a le même owner (le porteur du bond). Les **deux** classes dont l'owner EST le mourant, `PhoenixGemReviveAbility` (1451) et
`RitesOfMorkaiReviveTrigger` (1502), déclarent `fire_on_death` : l'échappatoire ad hoc qui compensait
exactement ce surplus. **La corrélation `fire_on_death == (owner est le mourant)` tient sur tout le
lot.** La levée rend donc cet attribut **INERTE sur la face EFFET** — elle retire une béquille, elle
ne change aucun observable.
Pour le gate « porteur introuvable », mesure live : **10 clés** de `by_unit` portant un effet,
**0 orpheline** — toute clé est une entité ou une tuile. Régime **vide**.

### 7.3 Ce qui est porté

`_owner_is_tile_entity` **disparaît** (plus aucun lecteur). `_owner_gate_applies(entry)` le remplace
et exprime la bifurcation native :

```python
if _owner_gate_applies(entry):          # face ABILITY -> CanGetAbilityTrigger
    owner = state.get_entity(entry.owner_id)
    if owner is None:
        continue                        # SURPLUS NOMMÉ (7.4), régime inatteignable
    uc = owner.get_component(UnitComponent)
    if uc is not None and not uc.alive and not getattr(entry, "fire_on_death", False):
        continue
# face EFFET (`EffectTrigger`) et abilities GLOBALES : AUCUN gate
```

### 7.4 Résidus ouverts par cette levée

* ~~**`#462-r4b-r1-r1-r1-r1-c-r3-r1`**~~ — **RÉSOLU (2026-08-05)**, cf.
  **`case-462-r4b-r1-r1-r1-r1-c-r3-r1-crush-steppable.md`**. Le RETRAIT est porté
  (`movement.py::_kill_steppable_remove_effects`, les trois `RemoveEffects` + la garde HEAL, via le
  foyer `remove_effects.py` de #389-r2), donc ce régime — le seul où la levée pouvait faire firer un
  trigger que le natif n'a plus — est fermé **du bon côté** : l'effet n'existe plus. Chiffres du
  résidu **confirmés par re-mesure** (27 kits `Steppable`, 20 `Immune`, **0** inscrit à un registre
  d'ability-trigger porté). L'ÉMISSION des cinq événements, elle, **n'est pas** portée : blast
  radius **mesuré à 27 classes** du registre, dont plusieurs portées par le MOVER (donc atteignables
  dès le premier decoy écrasé) — résidu `#462-r4b-r1-r1-r1-r1-c-r3-r1-r1`, gardé par
  `test_les_quatre_evenements_de_mort_restent_non_emis`.
* ~~**`#462-r4b-r1-r1-r1-r1-c-r3-r2`**~~ — **TRANCHÉ (2026-08-15) : ON GARDE, et le `BLOCAGE:
  porteur` de sa fiche était FAUX.** La divergence est confirmée au décompilé : le corps
  d'`IdunBattle.Entities.EntityExtensions$$IsUnit` ouvre sur `if (entity == 0) return 0`, donc
  `CanGetAbilityTrigger` saute ses deux gates et rend VRAI avec `owner = null`. Rien ne manque comme
  unité confrontable ; le régime est inatteignable par la **construction du modèle d'état du port**,
  et c'est désormais MESURÉ en quatre constats falsifiables : (a) aucun site d'`engine/**` ne retire
  d'entrée de `state.entities` (0 occurrence de `entities.pop` / `del …entities[` / `entities.clear()`
  / réaffectation) ; (b) `collect_triggered_abilities` n'instancie qu'en itérant `state.entities` ;
  (c) les deux classes de `GLOBAL_TRIGGERS` déclarent bien `owner_is_global = True` — sans quoi
  `state.get_entity(None)` tomberait ici et les tuerait **en silence** ; (d) `TileEffectTrigger`
  DÉRIVE d'`EffectTrigger`, donc `_owner_gate_applies` rend faux pour elle. Les quatre constats sont
  écrits **au site**, avec leur critère. Le `continue` reste l'instrument des contre-épreuves C.
* ~~**`#462-r4b-r1-r1-r1-r1-c-r3-r3`**~~ — **VÉRIFIÉ DES DEUX CÔTÉS (2026-08-15), et l'énumération
  de cette fiche était PÉRIMÉE.** *Inertie* : structurelle — `_owner_gate_applies` est le **seul**
  lecteur de `fire_on_death` de tout `engine/**` et rend faux pour tout `EffectTrigger`,
  `TileEffectTrigger` comprise. *Load-bearing* : le même montage sur un `TriggeredAbility` doit
  mordre, et mord. Les deux sont prouvés par **MORSURE** (l'attribut est remplacé par une property
  qui LÈVE, puis un dispatch est rejoué) et non par lecture — `probe_10015_allow_for_dead_owner.py
  --inertie`, deux bras : sans le second, le premier serait vert par vacuité.
  ⚠ **Le régime de lecture est étroit** : l'attribut n'est lu que si l'owner est PRÉSENT, porte un
  `UnitComponent` et n'est PAS vivant — un owner absent tombe sur le `continue` de `-r3-r2` **avant**
  toute lecture, si bien qu'un montage naïf ne mord pas et se lirait comme une preuve d'inertie.
  ⚠ **Et la liste de 4 classes ci-dessus est fausse** : re-dérivée, la face EFFET en compte **6** —
  `ArmourOfShriekingSoulsResurrectOnRemoved` et `FinalVengeanceUnitEffectTrigger` s'y sont ajoutées
  sans que la citation bouge. Le cliquet **dérive** l'ensemble (`getattr` sur `EFFECT_TRIGGERS`).
  ⚠ Enfin, sur `TriggeredAbility` l'attribut mirrore `ITriggeredAbility` slot 8 =
  `get_AllowForDeadOwner`, **pas** un `IsAtomic` (#10015). Attribut non retiré : il documente
  `OwnerIsTarget`.

### 7.5 Validation

`test_462_r4b_r1_r1_r1_r1_c_r3_owner_gates_effet_live.py` — **8 verts** (board `C3_01`, roster
`ultraTitus,bloodIntercessor,eldarFarseer` vs `worldKharn,orksNob,orksWarboss`, DIFFÉRENTS de ceux de
`-c-r1`).

Le bras qui MORD prend un porteur RÉEL dont l'owner est le mourant — `RitesOfMorkaiReviveTrigger`
(1502) — et un observable RÉEL (l'unité revit) :

| bras | montage | attendu | mesuré |
|---|---|---|---|
| A | `fire_on_death` intact | revive (contrôle positif) | revive |
| B | attribut **RETIRÉ** de la classe | revive (la face EFFET ne gate plus) | revive |
| C | B + `_owner_gate_applies` forcé à `True` | **aucun** revive (attribution) | aucun |

B est l'invariant : **avant `-c-r3` il ne revivait pas**. ⚠ Retirer `fire_on_death` est un
**MONTAGE**, pas un porteur naturel — et le dire est la seule façon honnête de rendre la garde (§7.2
(3) : les deux seules classes concernées le déclarent déjà).

Les sept autres bras : la fenêtre rend bien `[On(3), On(1), On(2)]` et **rien** sur `On(0)`/`On(54)`
(contre-épreuve : face ABILITY forcée ⇒ 0 passage) ; un porteur introuvable atteint `matches` sur la
face EFFET et **pas** sur la face ABILITY ; la face ABILITY gate **toujours** un porteur mort et
**seul** `fire_on_death` l'en dispense ; les trois mesures de gisement (0 clé orpheline sur 10 ;
**2 unités mortes réelles, 17 effets non consommés, 0 sur un mort** ; 27 kits `Steppable`, 0 adossé
au registre) ; l'inventaire des 4 `fire_on_death`.

⚠ **DEUX rouges PRÉEXISTANTS trouvés en jouant le cliquet offline complet** (`probe_457`, **2056
tests**), tous deux venus des tranches PRÉCÉDENTES de cette même famille :

1. `tests/test_enum_ordinal_ratchet_offline.py` (cliquet #283) — littéraux `2` en contexte
   `EventTriggerType` dans les fichiers de `-c-r1` (**5 sites**, mergés par la PR #625). Un ordinal en
   dur en contexte enum, refusé **même quand il est juste**. **CORRIGÉ ICI** : les 11 sites de la
   famille (5 hérités + 6 de cette tranche) passent par `EVENT_SONDE = int(EventTriggerType.PreUnitDeath_2)` ;
   le cliquet rend **18 verts**. La valeur est indifférente — ce qui est mesuré est le gate, pas
   l'événement — mais elle doit désigner un MEMBRE.
2. `tests/engine/runner/test_421_effect_active_gate_offline.py::test_the_probe_rail_covers_the_whole_registry`
   — `BondRemoveOnRangeExceeded`, la classe entrée au registre par la PR **#629**, n'est pas déclarée
   dans `probe_229_effect_triggers_active.RAIL`. **NON CORRIGÉ ICI** : une entrée de `RAIL` encode un
   verdict de RE (`kind` + symbole natif du rail) que cette tranche n'a pas rendu, et le fabriquer
   serait exactement ce que le cliquet existe pour empêcher. Résidu `#462-r4b-r1-r1-r1-r1-b-r2`,
   **depuis RÉSOLU** (`case-462-r4b-r1-r1-r1-r1-retrait-bond.md` §9) : la dérivation probable est
   **confirmée par lecture** — rail `ARRAYSET`, symbole
   `IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal`, les trois
   `Triggered()` alimentant le même `ArraySet` dans le même corps (`Add` à `+0x214` / `+0x436` /
   `+0x5b0`).

### 7.6 Matrice de mutants — et ce qu'elle a trouvé de MANQUANT

| mutant | ce qu'il casse | rouges |
|---|---|---|
| M1 — `_owner_gate_applies` rend `not owner_is_global` (face EFFET re-gatée = état pré-`-c-r1`) | la levée | **7** |
| M2 — `_owner_gate_applies` rend `False` (gate supprimé **PARTOUT**) | la PORTÉE | **1** |
| M3 — `fire_on_death` ignoré sur la face ABILITY | le mirror d'`IsAtomic` | **1** |
| M4 — la face ABILITY n'écarte plus un porteur introuvable | l'attribution | **2** |

⚠ **M2 a d'abord rendu 14 verts sur 14**, et c'est la mesure la plus utile du lot : **tous** les bras
d'attribution de cette famille **SUBSTITUENT** `_owner_gate_applies` (`monkeypatch` → `lambda: True`),
donc ils sont par construction **aveugles à sa disparition** — le piège « vacuously vrai » par une
porte que personne n'avait ouverte. Le bras
`test_le_gate_alive_de_la_face_ABILITY_mord_toujours` a été **ajouté pour ça** : il inscrit un
ability-trigger par la voie RÉELLE (`TRAIT_TRIGGERS` + un trait posé sur une unité du live) et ne
touche à aucun prédicat. C'est lui, et lui seul, qui attrape M2 et M3.
M4 confirme en creux le résidu `-r3-r2` : le refus d'un porteur introuvable sur la face ABILITY est
**l'instrument** des contre-épreuves C — le lever coûterait cette attributabilité.

Deux bras de `test_462_r4b_r1_r1_r1_r1_c_r1_tile_owner_gate_live.py` **changent d'assertion** — c'est
voulu, ils fixaient le comportement d'avant : `test_un_owner_introuvable_passe_desormais_sur_la_face_effet`
(inversé) et `test_le_gate_d_owner_reste_entier_sur_la_face_ABILITY` (l'ancien 4ᵉ test, qui gardait le
surplus `alive` ; il garde désormais que la levée **ne déborde pas** sur l'autre face). Le contrôle du
probe `-c-r1 --step gate` est inversé pour la même raison.

**Non-régression : 208 verts sur 26 fichiers** (24 live + 2 offline), plus **70** re-joués APRÈS le
rebase sur `origin/master` (#629 mergée entre-temps) et le cliquet offline complet `probe_457`
(**2024 tests**) — `test_462_r4b_r1_r1_r1_r1_c_r1_tile_owner_gate_live` + `bond_removal_live` (11),
`death_queue_ordering_live` (22), les trois `overwatch_*` (18), `tile_effect_dynamics_live` +
`load_state_inactive_effects_live` (15), `rites_of_morkai_revive_live` (13),
`haze_of_corruption_transfer_live` + `haze_bonded_chain_live` (27), `rad_saturation_live` +
`master_tutelaries_active_gate_live` (10), `neuroparasite_pose_live` + `bond_removal_offline` +
`trigger_ability_channels` (26), `revive_cancels_death_events_live` + `death_nova_live` (8),
`ghost_revive_live` + `echoes_from_the_warp_revive_live` (11), les trois narthecium/fuelled (24),
`425_tile_effect_channel_live` + `load_state_tile_effects_live` + `swamp_tile_effect_foyer_live` (19),
`overwatch_active_ability_gate_live` + `overwatch_single_shot_per_activation_live` (4).

## 8. Non couvert, et nommé

* **La face ABILITY sur porteur-tuile n'est pas exercée** : `collect_triggered_abilities` itère
  `state.entities`, donc aucun `TriggeredAbility` ne peut aujourd'hui avoir une tuile pour owner —
  alors que `CanGetAbilityTrigger` le permet côté natif (`IsUnit` faux ⇒ pas de gate). Les
  ability-triggers **de tuile** existent (`triggers/tiles.py`) mais sont appelés par des vecteurs
  dédiés, hors registre. Le correctif les couvrirait si le registre les portait un jour.
* **Les gates `simulation` / `onlyNonAtomic`** de `CanGet*Trigger` (les deux `FUN_180002590` sur
  `DAT_183365e08` / `DAT_183387e30`) ne sont portés dans aucun sens — ils l'étaient déjà avant.
* **`UnitExtensions$$IsTriggersDisabled`** (2ᵉ gate de `CanGetAbilityTrigger`) n'est toujours pas
  porté — antérieur à cette tranche, inchangé par elle.
* **La fenêtre du DESPAWN** (`RemoveUnitOperation$$Execute` : `alive=False` + `On(0x25 = UnitRemoved)`
  **avant** l'étape 14 qui consomme les effets) est ouverte par la même levée, mais **non exercée
  par un bras dédié** : le seul écouteur d'`On(0x25)` est `BondRemoveOnBondedEntityDeath`, dont
  l'owner est le porteur du bond et dont le behaviour retire un effet du retiré — sans observable.
