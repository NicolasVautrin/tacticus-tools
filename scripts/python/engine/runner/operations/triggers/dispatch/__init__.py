"""Dispatch GÉNÉRIQUE de triggers — `IdunBattle.Operations.EvaluateTriggerOperation` : registre
`AbilityAndEffectCache` + vecteurs d'événement.

Chaîne native : `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` → (record message 8) →
`IdunBattle.Operations.EvaluateTriggerOperation$$Execute → `IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal → itère le registre
`AbilityAndEffectCache` → `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityOrEffectTrigger par entrée → (ability-trigger)
`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger + `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger.

**Structure native** (portée 1:1 ici) :
- Le dispatch N'EST PAS scopé à l'attaquant : il itère un **registre GLOBAL** de tous les triggers de la
  bataille (abilities accordées par les traits + effets porteurs de trigger). Le scoping (qui réagit à
  CET événement) est dans la **condition du trigger** de chaque entrée (`matches`).
- Par entrée : gates owner = `IsUnit` & VIVANT (sauf ability fire-on-death) & `!IsTriggersDisabled` ; cap
  `GetTimesTriggeredThisPhase < 0x33` (51/phase).

EVENT-MAPPING RE (#147, verdict agent #150) : `On(NormalAttack=38)` et le vecteur after-hit
`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` (dispatche `AttackHit=8` TOUJOURS + `UnitBlocked=60`
(0x3d) sur la branche `param_6`) sont des events NATIFS DISTINCTS. L'ancien port les conflatait sous une
constante 0x26 → le splash (`IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`, events {6,8,0x3d}, JAMAIS
NormalAttack) re-satisfaisait Psyker `On(NormalAttack)` → chain 51×. Corrigé (#147) : Psyker écoute
`NormalAttack` ; le reset ActOfFaith écoute `Attack=9` (attaque d'ability, #151). Les membres consommés
+ leurs VAs/sémantique sont annotés dans `dsl/event_trigger_type.py`.

Les classes concrètes vivent dans `loki.py` (`Abilities.{Active,Triggered,Damage}.Loki.*`), `tiles.py`
(`Abilities.Tiles.*`) et `effect_triggers.py` (`Entities.Effects.*`) ; le framework dans `base.py`.

SCISSION #169 : ce module est devenu un PACKAGE (meme nom, meme call-site --
`triggers/__init__.py` re-exporte une trentaine de noms depuis `.dispatch`, et 26
fichiers en dependent). Une FACE par sous-module :

  - `registry`   : les 4 registres + le bloc d'imports d'abilities qu'ils entrainent ;
  - `core`       : collecte + `evaluate_trigger_operation` ;
  - `attack`     : vecteurs pre-attaque / per-coup / cloture / degat pris ;
  - `ability`    : vecteurs init / pre-cast / post-cast / cast actif ;
  - `move_death` : vecteurs mouvement, kill, mort, revive, resurrection ;
  - `turn`       : tile-tick, debut et fin de tour.

`OVERKILL_PCT_KEY` et la famille `IsOverkill` ont quitte ce fichier pour
`engine/services/` (notion de DEGAT, pas de dispatch). #178 : le FOYER UNIQUE est
`services/trait_damage_limits.py` (`is_overkill` = surcharge 7-args privee,
`unit_is_overkill` = surcharge d'INSTANCE, celle du chemin COMBAT) ; ils restent
re-exportes ici via `services/damage_prediction.py` : `triggers/__init__.py` les expose.

Les 4 registres sont re-exportes par VALEUR (meme objet dict) : une MUTATION faite par
un consommateur externe porte ; un REBIND ne porterait pas -- aucun site connu n'en fait.
"""
from __future__ import annotations


__all__ = []
