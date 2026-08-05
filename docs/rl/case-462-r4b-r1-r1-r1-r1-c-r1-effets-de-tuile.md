# #462-r4b-r1-r1-r1-r1-c-r1 — les effets de TUILE dans la collecte d'effet-triggers

Le résidu ouvert par la tranche `-c` (PR #620) énonçait : « `collect_effect_triggers` est
**structurellement aveugle aux effets de TUILE** : il n'itère que `state.effects.by_unit` ».
La question posée était binaire : **le natif balaie-t-il, lui, les effets de tuile ?**

Réponse : **oui, et sans le moindre gate**. Mais la mesure a d'abord **déplacé l'accusation** — le
collecteur voit déjà les tuiles ; c'est le **gate d'owner** du dispatch qui les jetait.

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
if (!IsAtomic(ability)) {
    if (EntityExtensions$$IsUnit(owner) && !UnitExtensions$$IsAlive(owner)) return false;
}
if (EntityExtensions$$IsUnit(owner) && UnitExtensions$$IsTriggersDisabled(owner)) return false;
```

Les deux gates sont **sous** `IsUnit`. Un porteur qui n'est pas une unité — une tuile — les traverse.

⇒ **La réponse à la question binaire : le natif ne distingue pas.** Le port avait donc bien un trou,
et le seul discriminant natif à mirrorer est `EntityExtensions$$IsUnit`.

## 4. Ce qui est porté

`dispatch/core.py::_owner_is_tile_entity(state, owner_id)` — mirror d'`IsUnit` **par la négative** :
un porteur absent de `state.entities` mais présent dans `state.board.by_id` est une entité-tuile,
donc aucun gate. **L'ENTITÉ L'EMPORTE** : le prédicat n'est consulté que si `get_entity` n'a rien
rendu, si bien qu'un id qui serait à la fois unité et tuile resterait gaté comme une unité.
Sans board (State nu), `False` — le comportement d'avant.

`owner_is_tile` **reste** sur `TileEffectTrigger` : il documente l'intention et porte les helpers
`_tile_coord`/`_unit_on_tile`. Il n'est simplement plus le SEUL chemin.

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
| B | attribut de classe `owner_is_tile` **RETIRÉ** | DoT > 0 (le gate lit la NATURE) | **352** |
| C | B + `_owner_is_tile_entity` neutralisé | DoT **nul** (attribution) | **0** |

B est l'invariant : **avant le correctif il rendait 0**. C attribue le passage de B au nouveau
prédicat et à lui seul — sans lui, B pourrait tenir pour n'importe quelle autre raison.

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

## 7. Résidu nommé — `#462-r4b-r1-r1-r1-r1-c-r3`

La RE du §3 établit **plus** que ce qui est porté : sur la face EFFET, le natif n'applique **aucun**
gate d'owner, pas même « l'owner existe ». Le port en garde deux, qui sont donc un **SURPLUS** :

* un effet porté par une unité **MORTE** ne déclenche plus ses triggers (`uc.alive`), là où le natif
  les évaluerait ;
* un effet dont le porteur est **introuvable** est écarté, là où le natif passerait `owner = null`.

Les deux sont **hors périmètre de cette tranche** et volontairement non touchés : les lever change le
comportement de **26** `effect_type` à classes nues, et exige sa propre confrontation (le régime
« effet sur unité morte » est court côté natif — `IdunBattle.Operations.KillUnitOperation$$RemoveEffects`
détruit les entités-effet de la victime — mais il n'est pas vide, et c'est précisément ce qu'il
faudrait mesurer). Le 4e test du fichier **fixe** le comportement actuel, pour qu'un élargissement
soit un choix et pas un effet de bord.

## 8. Non couvert, et nommé

* **La face ABILITY sur porteur-tuile n'est pas exercée** : `collect_triggered_abilities` itère
  `state.entities`, donc aucun `TriggeredAbility` ne peut aujourd'hui avoir une tuile pour owner —
  alors que `CanGetAbilityTrigger` le permet côté natif (`IsUnit` faux ⇒ pas de gate). Les
  ability-triggers **de tuile** existent (`triggers/tiles.py`) mais sont appelés par des vecteurs
  dédiés, hors registre. Le correctif les couvrirait si le registre les portait un jour.
* **Les gates `simulation` / `onlyNonAtomic`** de `CanGet*Trigger` (les deux `FUN_180002590` sur
  `DAT_183365e08` / `DAT_183387e30`) ne sont portés dans aucun sens — ils l'étaient déjà avant.
