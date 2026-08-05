# #462-r4b-r1-r1-r1-r1-c-r1 — les effets de TUILE dans la collecte d'effet-triggers

Le résidu ouvert par la tranche `-c` (PR #620) énonçait : « `collect_effect_triggers` est
**structurellement aveugle aux effets de TUILE** : il n'itère que `state.effects.by_unit` ».
La question posée était binaire : **le natif balaie-t-il, lui, les effets de tuile ?**

Ce cas répond aux deux — et la première réponse **corrige la localisation du trou**.

## 1. La prémisse est FAUSSE au niveau du collecteur — `by_unit` contient DÉJÀ les tuiles

`EffectsState.by_unit` est clée par **id d'ENTITÉ**, pas par id d'unité. Le nom ment ; trois
lecteurs du port en dépendent déjà et le disent :

* `engine/runner/operations/triggers/base.py::TileEffectTrigger` — « boardGraph `t.id` = entity id,
  disjoint des ids d'unité → clé `EffectsState.by_unit` valide » ;
* `EffectsState.on_turn_end` §DOMAINE (#102) — `EndTurnOperation$$RefreshEffects` n'itère pas les
  unités mais **toutes** les entités-effet, « il n'y a AUCUNE distinction porteur-unité /
  porteur-tuile dans le tick de durée » ;
* `triggers/tiles.py::dry_bush_fire_spread` — `state.effects.has_effect(tid, ...)` avec `tid` un id
  de TUILE.

`collect_effect_triggers` itère donc bien les effets de tuile et **instancie leur trigger**.

## 2. Le trou réel est un étage plus bas : le gate d'owner de `evaluate_trigger_operation`

```python
if getattr(entry, "owner_is_tile", False) or getattr(entry, "owner_is_global", False):
    pass
else:
    owner = state.get_entity(entry.owner_id)
    if owner is None:
        continue
```

Une tuile n'est **pas** dans `state.entities` → `get_entity` rend `None` → `continue`. Le trigger
collecté est **jeté**, sauf si sa CLASSE déclare `owner_is_tile`. Le critère est donc **statique**
(une propriété de la classe portée) là où la nature du porteur est **dynamique** (une propriété de
l'instance d'effet). Un `EffectTrigger` nu posé sur une tuile est silencieusement écarté.

## 3. Le natif — mesuré, build `rnca9r7q6c`

*(à compléter)*
