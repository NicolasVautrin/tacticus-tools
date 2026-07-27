"""Vecteurs d'attaque (les 4 `execute*`) extraits d'`operations/damage.py` (scission du module
>1000 lignes, tache #60 -- deplacement VERBATIM, zero changement de comportement).

`_DamageOpsMixin` (mixin de `AttackDamageOperation`) porte :
  - `execute` : attaque normale (`IdunBattle.Operations.AttackDamageOperation$$Execute`) ;
  - `execute_ability_attack` : ability `AttackWithAttackDamage`/`AttackWithAbilityDamage` ;
  - `execute_normal_like` : node `StatAmount`/`PercentageOf` (splash Psyker...) ;
  - `execute_direct` : degat `Direct(...)` (DoT de tuile).

Les helpers `_*` (crit/block/limits/pipeline) et `_run_hits` restent portes par
`AttackDamageOperation` ; chaque `execute*` les atteint via un import LAZY
`from .damage import AttackDamageOperation` (meme convention que `additional_hits`/`displace`/
`summon_ai` -- rompt le cycle `damage` <-> `damage_ops`, `AttackDamageOperation` n'existant
qu'apres l'import de ce mixin comme classe de base).

SCISSION #169 : ce module est devenu un PACKAGE (meme nom, meme call-site
`from .damage_ops import _DamageOpsMixin`). Un vecteur par sous-module :

  - `_channel`     : `hits_channel_is_melee` + `_normal_attack_kind` ;
  - `normal`       : `execute` (attaque normale) ;
  - `ability`      : `execute_ability_attack` ;
  - `normal_like`  : `execute_normal_like` + `execute_direct`.

ATTENTION PATCH-POINTS : un test/probe qui remplace un attribut de MODULE
(`apply_all_modifiers`, `hits_channel_is_melee`) doit viser le SOUS-MODULE qui le
consomme (`damage_ops.normal.apply_all_modifiers`, `damage_ops.ability....`). Ecrire
sur le namespace de CE `__init__` ne change RIEN a ce que resolvent les vecteurs : le
patch devient un NO-OP SILENCIEUX (le test reste vert en ne mesurant plus rien)."""
from __future__ import annotations

from ._channel import hits_channel_is_melee, _normal_attack_kind
from .normal import _Normal
from .ability import _AbilityAttack
from .normal_like import _NormalLike


class _DamageOpsMixin(_Normal, _AbilityAttack, _NormalLike):
    """Mixin des vecteurs d'attaque de `AttackDamageOperation`. Sans etat (staticmethods) ;
    herite tel quel. Chaque methode lazy-importe `AttackDamageOperation` pour ses
    helpers/`_run_hits`."""
    __slots__ = ()


__all__ = ["_DamageOpsMixin", "hits_channel_is_melee", "_normal_attack_kind",
           "_Normal", "_AbilityAttack", "_NormalLike"]
