#!/usr/bin/env python
"""Cliquet #254b-b -- AUCUN ordinal `StepType`/`GroupType` en dur dans le depot.

POURQUOI UN CLIQUET, ET PAS SEULEMENT UNE CORRECTION
----------------------------------------------------
Un ordinal fige ne casse pas : il designe un AUTRE pas. La MAJ `gqfc5mff6c` -> `rnca9r7q6c` a
retire `StepType.RestoreArmorInfo` (7) et decale de -1 tout ce qui suit. Cinq filtres de
`probe_202c_tutelaries.py` visaient `AddUnit`/`ChangeStats`/`ChangeAbility`/`ReceiveEffect`/`Info` :
ils lisaient depuis la MAJ `AddMachine`/`ChangeAbility`/`FinishMatch`/`LoseEffect`/`TerritoryCapture`.
Ni erreur, ni trace. Le meme decalage frappait `probe_217_blackrage`, `probe_217_thequickening`,
`rl_collect_batch` (colonne `step_name` de la base RL) et la table de labels du frontend.

Ce fichier verifie DEUX choses, et la seconde n'est pas decorative :

1. le depot est PROPRE (aucun litteral) -- c'est le cliquet ;
2. le DETECTEUR mord vraiment sur les motifs connus. Un cliquet qui ne detecte rien passerait
   au vert sur un depot pourri. Les trois motifs testes sont ceux qui existaient REELLEMENT :
   acces direct, alias de variable, et le couple « constante-tuple + champ de dict » par lequel
   `rl_collect_batch.py` comparait `fr["code"]` a des ordinaux de `GroupType`.

Offline pur : aucun runner, aucune session Frida. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "python"))

import probe_274_step_ordinals_sweep as SW  # noqa: E402
import stream_events as SE  # noqa: E402


def _hits(src: str) -> list:
    tree = ast.parse(src)
    al = SW._Aliases()
    al.visit(tree)
    al.visit(tree)
    sw = SW._Sweep(al)
    sw.visit(tree)
    return sw.hits


# --------------------------------------------------- 1. le cliquet : le depot est propre

def test_aucun_ordinal_step_ou_group_en_dur_dans_le_code_vivant():
    fails, _infos, _prev = SW.sweep_py(verbose=False)
    assert not fails, (
        "ordinal(aux) StepType/GroupType en dur -- remplacer par stream_events.step_id/group_id :\n"
        + "\n".join("  %s:%d  %s %s -> %s" % r for r in fails))


def test_la_table_de_labels_du_frontend_suit_le_build_courant():
    """`frida/public/src/battle-log.js` indexe ses labels PAR ORDINAL : un membre retire la
    decale entierement, et le journal de bataille affiche alors le nom du pas VOISIN."""
    bad = SW.sweep_js()
    assert not bad, ("table de labels frontend desynchronisee de enums.tsv :\n"
                     + "\n".join("  " + m for (m,) in bad))


# --------------------------------- 2. le detecteur mord (sinon le cliquet ne prouve rien)

def test_detecte_l_acces_direct():
    """Le motif de `probe_202c_tutelaries` : `ev.get("step") == 16`."""
    h = _hits('if ev.get("step") == 16 and t: pass\n')
    assert h and h[0][1] == "step" and h[0][2] == [16]


def test_detecte_l_alias_de_variable():
    """Le motif de `probe_217_blackrage` : `st = ev.get("step")` puis `st == 13`."""
    h = _hits('st = ev.get("step")\nif st == 13: pass\n')
    assert h and h[0][1] == "step" and h[0][2] == [13]


def test_detecte_le_in_sur_un_tuple_litteral():
    """Le motif de `probe_217_thequickening` : `step in (16, 18)`."""
    h = _hits('step = ev["step"]\nif step in (16, 18): pass\n')
    assert h and h[0][1] == "step" and h[0][2] == [16, 18]


def test_detecte_la_constante_tuple_derriere_un_champ_de_dict():
    """LE motif qu'il a fallu trouver a la main dans `rl_collect_batch.py` : le code de groupe
    est range dans un dict (`{"code": gcode}`), puis compare a une constante-tuple nommee
    (`fr["code"] in _ACTOR`). Ni l'un ni l'autre n'est un litteral visible sur la ligne."""
    src = ('_ACTOR = (11, 12, 13)\n'
           'gcode = ev.get("group")\n'
           'gstack.append({"code": gcode, "entity": 1})\n'
           'for fr in gstack:\n'
           '    if fr["code"] in _ACTOR: pass\n')
    h = _hits(src)
    assert h and h[0][1] == "group" and h[0][2] == [11, 12, 13]


# --------------------------------------------- 3. le resolveur par nom leve, il ne se replie pas

def test_group_id_leve_sur_un_membre_inexistant():
    """Pendant de `step_id` : un membre disparu doit CASSER, jamais rendre un ordinal qui
    appartient desormais a un autre groupe."""
    try:
        SE.group_id("GroupeQuiNExistePas")
    except KeyError as e:
        assert "GroupType.GroupeQuiNExistePas" in str(e)
    else:
        raise AssertionError("group_id aurait du lever sur un membre inexistant")


def test_group_id_est_l_inverse_exact_de_group_name():
    for nom in ("User_UseAbility", "Effect_Refresh", "NormalAttack_AtomicDamage",
                "Ability_Attack", "EffectAdditionalHits"):
        assert SE.group_name(SE.group_id(nom)) == nom
