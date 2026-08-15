"""`IdunBattle.Operations.KillUnitStep` — mirror d'enum, FEUILLE PURE.

## Pourquoi ce module existe, et pourquoi ICI

L'enum vivait dans `engine/runner/operations/remove_effects.py`, à côté de son consommateur. Or il
a un SECOND consommateur, structurellement en amont : `engine/entities/effects/base.py`, qui doit
nommer la valeur de `BaseEffect.remove_on_kill_step` (#1088). Mesuré en process frais :
`import engine.runner.operations.remove_effects` charge **177** modules `engine.*`, dont
`engine.entities.effects.base` — donc un import direct depuis `base.py` FERMERAIT un cycle, et le
différer aurait été un porteur de plus.

La doctrine (CLAUDE.md, « un import DIFFÉRÉ est un outil à CYCLE, pas un idiome ») ordonne d'abord
de **DÉPLACER le code partagé vers un module que la cascade ne ré-entre pas** — ce que fait ce
fichier : il n'importe **rien** de `engine.*`, donc aucun de ses lecteurs ne peut créer de cycle en
l'important. C'est la voie (1), pas la (3) : l'arête est supprimée, pas contournée.

Il rejoint les autres mirrors d'enum du paquet (`effect_type.py`, `damage_reason.py`,
`heal_type.py`, …). ⚠ Cet emplacement est un CHOIX mesuré, pas une obligation recopiée : ce qui est
prescriptif, c'est qu'un mirror soit une feuille que ses lecteurs peuvent tous atteindre.

ASCII-safe : ce module n'imprime rien.
"""
from __future__ import annotations

from enum import IntEnum


class KillUnitStep(IntEnum):
    """`IdunBattle.Operations.KillUnitStep` — VERBATIM du dump d'enums (`frida/enums.tsv`) :
    `0=PreUnitRemove,1=AfterUnitRemove,2=AfterDeathTrigger`. Domaine RE-VÉRIFIÉ inchangé au passage
    au build `t6dpr4k06g` (aucun renumérotage).

    Les trois valeurs sont les trois call-sites de
    `IdunBattle.Operations.KillUnitOperation$$RemoveEffects` dans
    `IdunBattle.Operations.KillUnitOperation$$Execute` -- cf. `damage.py::_kill_unit_operation`
    pour leur placement exact dans la sequence de mort.

    C'est aussi le domaine du slot 4 de l'interface `IdunBattle.Entities.Effects.IEffect`
    (`get_RemoveOnDeathStep`), que `IdunBattle.Operations.RemoveEffectsOperation$$Execute` compare
    par ÉGALITÉ à `options.step` — la valeur portée par `BaseEffect.remove_on_kill_step` et dérivée
    classe par classe par `probe_1088_remove_on_death_step.py`.

    Les noms sont ceux DU JEU, caractere pour caractere (#427). Le port les avait d'abord ecrits
    en UPPER_SNAKE (`PRE_UNIT_REMOVE`) : `probe_313` n'aurait alors pu le garder qu'en
    `strict=False`, mode qui relache les NOMS pour TOUT le mirror et rend muet le sens
    RENUMEROTE -- le pire des trois (il resout, pointe ailleurs, rien ne proteste). Une
    exception de confort n'est pas payee par le membre qui la demande, elle est payee par les
    autres membres du meme mirror."""
    PreUnitRemove = 0
    AfterUnitRemove = 1
    AfterDeathTrigger = 2
