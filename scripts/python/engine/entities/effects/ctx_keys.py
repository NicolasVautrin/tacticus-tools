"""FOYER UNIQUE des chaines de cle du contexte de degat (`att_ctx` / ctx d'aura / ctx de defense).

Ce module est une FEUILLE : il n'importe RIEN de `engine.*`, donc l'importer depuis
n'importe quel module d'effet ne peut fermer aucun cycle. Il ne contient que des chaines.

POURQUOI il existe (#1042-r5, mesure du 2026-08-14). La chaine
`"tertiary_ability_state_of"` etait declaree **14 fois dans 13 modules**, chaque
declaration se presentant comme << le >> foyer. Le defaut a ete trouve en resolvant le
merge #1055 x #1056 : les deux tranches posaient cette meme cle dans le MEME literal de
dict de `runner/damage_model.defender_modifiers`, chacune via SA constante -- une cle
DUPLIQUEE, que Python resout en silence en gardant la derniere. Ni #1055 ni #1056 ne
pouvait le voir seule : le defaut n'EXISTE que dans l'union des deux.

Tant que N constantes portent la meme chaine, une tranche qui renomme l'une croit
deplacer le foyer et n'en deplace qu'une fraction : les N-1 autres continuent de poser
l'ancienne chaine, sans erreur et sans que rien ne rougisse.

CRAN : `scripts/python/probe_1042r5_cles_ctx_dupliquees.py` rougit des qu'une chaine de
cle de ctx est declaree dans plus d'un module. Une cle NEUVE partagee par plusieurs
modules entre ICI, pas dans le module qui la lit en premier.
"""
from __future__ import annotations

# `GetAbilityState(effect)` (#357) -- callable `(owner_id, ability_name) -> (level, mult)`.
# Le couple (niveau, multiplicateur) sous lequel l'ability est MONTEE sur le porteur :
# TERTIAIRE pour une relique EQUIPEE, ce qui n'est PAS l'etat de ses passifs (mesure
# #1005 : `level = 1, mult = 100` contre `level = 50, mult = 180`). Foyer de lecture :
# `entities/effects/base.py::relic_ability_state`.
CTX_TERTIARY_ABILITY_STATE_OF = "tertiary_ability_state_of"

# #884-r2 / #1003-r1 -- les DEUX scalaires que lit `...OrbsOfDecayAbility$$GetTriggerForAttack`
# sur son `Subject`, quand ce meme predicat est re-evalue depuis le canal #179
# (`OrbsOfDecay_AdditionalHitsEffect$$CreateAdditionalHits`, ou le sujet est la CIBLE de l'attaque
# -- le « on ... the target's hex » de l'i2, par opposition au « adjacent to » du volet ABILITY).
# Posees par `runner/operations/additional_hits.py`, lues par `entities/effects/loki/hits.py` :
# DEUX modules, donc la chaine entre ICI et pas chez son lecteur (cran `probe_1042r5`).
# TRI-ETAT : `None` = NON MESURE -> le gate se FERME (cf. `orbs_of_decay_armor_gate`), jamais un
# 0 rabattu, qui ferait passer une cible sans armure pour une cible non reduite.
#: `StatAmount(Subject@+0x68, 0x10 = FixedArmor, statPart 3 = Initial, null, 0)`
CTX_TGT_FIXED_ARMOR_INITIAL = "tgt_fixed_armor_initial"
#: `StatNegativeModification(Subject@+0x68, 0x10 = FixedArmor)` -- SOMME des valeurs ABSOLUES des
#: seules contributions NEGATIVES (un `-40` compense par un `+40` rend `40`, pas `0`).
CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD = "tgt_fixed_armor_negative_mod"
