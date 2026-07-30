"""GARDE de `stream_events` -- decodable depuis un CHECKOUT SEUL, et fail-loud sinon (#254b-a).

CE QUE CES TESTS PROTEGENT
--------------------------
`stream_events` traduit les ordinaux `StepType`/`GroupType` des events StreamDispatcher
(`IdunBattle.Streams.StreamDispatcher$$Action(StepType, BEntityId, Dictionary<TagKey,int>)`).
Il lisait pour cela `frida/data/meta/<version>/enums.json`, artefact ecrit par le HOST a
l'inject -- et `frida/data/` est GITIGNORE. Dans un worktree frais la table etait donc VIDE,
et le tout premier `python rl_duel.py act ...` levait `KeyError: StepType.UnitDamaged`
APRES que le RPC `applyAction` ait applique l'action (mesure live du 2026-07-30).

Deux proprietes distinctes, et il faut les deux :

 1. **la source est VERSIONNEE** -- `data/symbols/<CURRENT>/frida/enums.tsv`, donc presente
    dans tout checkout. C'est l'invariant « un worktree frais est RUNNABLE par son seul
    checkout » (CLAUDE.md, invariant 3) applique a CE chemin. Aucun test ne le tenait : le
    `__main__` du module detectait la panne mais n'etait joue par personne.
 2. **une panne est RENDUE, pas deguisee** -- table absente => message qui NOMME le fichier
    et la commande qui le regenere ; membre disparu => message DIFFERENT. Un `KeyError` nu
    sur un membre d'enum envoie chercher une renumerotation de build pour un fichier
    manquant : c'est exactement ce qui a coute du temps.
 3. **le decodage n'annule jamais une action APPLIQUEE** -- `_print_apply` rend sa panne au
    lieu de la lever, sinon l'appelant lit « erreur » sur une action qui a eu lieu, la
    rejoue, et la joue DEUX FOIS.

AUCUN ordinal n'est fige ici : figer `UnitDamaged == 4` re-armerait le piege que ce module
vient de desamorcer (la MAJ `rnca9r7q6c` a retire `RestoreArmorInfo`, decalant tout ce qui
suit de -1). On assert des ALLERS-RETOURS et des RELATIONS, jamais une valeur.

Offline pur : aucun runner, aucune session Frida.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "python"))

import stream_events as SE  # noqa: E402


# ------------------------------------------------------- 1. la source est VERSIONNEE

def test_la_source_des_ordinaux_vit_sous_data_symbols():
    """Pas sous `frida/data/` (gitignore), donc pas absente d'un worktree frais."""
    p = SE.source_path()
    assert p.is_file(), "table d'enums absente du checkout : %s" % p
    assert p.is_relative_to(REPO / "data" / "symbols"), \
        "la source doit etre la table VERSIONNEE, pas un artefact host : %s" % p


def test_la_source_des_ordinaux_n_est_PAS_gitignoree():
    """LA propriete qui manquait. `git check-ignore` rend 0 quand le chemin est ignore --
    c'est ce qui rendait la table vide dans tout worktree d'agent."""
    p = SE.source_path()
    r = subprocess.run(["git", "check-ignore", "-q", str(p)], cwd=str(REPO))
    assert r.returncode != 0, (
        "%s est GITIGNORE -> absent d'un worktree frais. Une source d'ordinaux doit etre "
        "versionnee." % p)


# ------------------------------------------------- 2. aller-retour, jamais un ordinal fige

@pytest.mark.parametrize("nom", ["UnitDamaged", "RemoveUnit", "ReceiveEffect",
                                 "ChangePosition", "ChangeStats", "LoseEffect"])
def test_aller_retour_nom_ordinal(nom):
    i = SE.step_id(nom)
    assert SE.step_name(i) == nom


def test_step_name_rend_un_NOM_et_pas_un_repli_Step_N():
    """Regression : la map etait interrogee A L'ENVERS (`{NOM: ordinal}` lu par ordinal),
    donc `step_name` rendait TOUJOURS `Step#N`. Panne muette -- le repli avait exactement
    la forme d'un ordinal inconnu."""
    assert not SE.step_name(SE.step_id("UnitDamaged")).startswith("Step#")
    assert SE.group_name(0) != "Group#0"        # GroupType.None existe sur tout build


def test_un_ordinal_reellement_inconnu_se_replie_lui():
    """Le repli reste LEGITIME pour un ordinal hors table (event d'un build plus recent)."""
    inconnu = max(SE._step_map()) + 1000
    assert SE.step_name(inconnu) == "Step#%d" % inconnu


# ------------------------------------------ 3. analyze() classe par NOM, pas par ordinal fige

def _ev(step, **tags):
    return {"kind": "action", "step": step, "entity": 1, "tags": dict(tags)}


def test_analyze_classe_damage_deaths_effects_par_NOM():
    cascade = [
        {"kind": "group", "group": SE._group_par_nom()["User_UseAbility"], "entity": 1},
        _ev(SE.step_id("UnitDamaged"), Attacker_Id=10, Target_Id=20, Amount=99),
        _ev(SE.step_id("RemoveUnit")),
        _ev(SE.step_id("ReceiveEffect"), Effect_Id=1234),
        {"kind": "finish"},
    ]
    an = SE.analyze(cascade, [10])
    assert [d["amount"] for d in an["dealt"]] == [99]
    assert an["deaths"] == [1]
    assert an["effects"] == [1234]


def test_analyze_ne_compte_PAS_les_pas_VOISINS_des_ordinaux_historiques():
    """LE defaut de #254b-a : `analyze` testait `step == 12` (« RemoveUnit ») et `step == 16`
    (« ReceiveEffect »). Sur `rnca9r7q6c` ces deux ordinaux designent `ChangeStats` et
    `LoseEffect`. Un `ChangeStats` ne doit produire NI mort NI effet -- sinon on est
    retombe sur une lecture par ordinal."""
    assert SE.step_id("ChangeStats") != SE.step_id("RemoveUnit")
    assert SE.step_id("LoseEffect") != SE.step_id("ReceiveEffect")
    an = SE.analyze([_ev(SE.step_id("ChangeStats")),
                     _ev(SE.step_id("LoseEffect"), Effect_Id=7)], [])
    assert an["deaths"] == []
    assert an["effects"] == []


def test_analyze_distingue_manuel_et_auto_par_le_groupe():
    """`auto` = hors activation commandee. Le discriminant est le NOM du groupe englobant
    (`User_*`), pas un ordinal."""
    dmg = _ev(SE.step_id("UnitDamaged"), Attacker_Id=10, Target_Id=20, Amount=5)
    sous_user = [{"kind": "group", "group": SE._group_par_nom()["User_UseAbility"],
                  "entity": 1}, dmg, {"kind": "finish"}]
    sous_startturn = [{"kind": "group", "group": SE._group_par_nom()["System_StartTurn"],
                       "entity": 1}, dmg, {"kind": "finish"}]
    assert SE.analyze(sous_user, [10])["dealt"][0]["auto"] is False
    assert SE.analyze(sous_startturn, [10])["dealt"][0]["auto"] is True


# --------------------------------------- 4. la panne est RENDUE : fichier + commande nommes

def _vide_les_caches():
    for f in (SE.source_path, SE._par_nom, SE._step_par_nom, SE._group_par_nom,
              SE._step_map, SE._group_map, SE.step_id):
        f.cache_clear()


def test_table_absente_NOMME_le_fichier_ET_la_commande(monkeypatch, tmp_path):
    """Le message qui a coute du temps disait `KeyError: StepType.UnitDamaged absent de
    enums.json` : il accusait une renumerotation alors qu'un FICHIER manquait."""
    fantome = tmp_path / "nulle-part" / "frida" / "enums.tsv"
    _vide_les_caches()
    monkeypatch.setattr(SE, "source_path", lambda: fantome)
    try:
        with pytest.raises(SE.EnumTableUnavailable) as exc:
            SE.step_id("UnitDamaged")
        msg = str(exc.value)
        assert fantome.as_posix() in msg, "le message doit NOMMER le fichier absent"
        assert "preprocess_il2cpp_dump.py" in msg, "le message doit donner la regeneration"
        assert "symbols_sync.py" in msg, "le message doit donner la garde de synchro"
    finally:
        monkeypatch.undo()
        _vide_les_caches()


def test_membre_disparu_leve_AUTRE_CHOSE_qu_une_table_absente():
    """Deux causes, deux messages. `RestoreArmorInfo` a ete RETIRE par `rnca9r7q6c` : sa
    disparition doit lever un KeyError qui pointe la table, pas un EnumTableUnavailable."""
    with pytest.raises(KeyError) as exc:
        SE.step_id("RestoreArmorInfo")
    assert not isinstance(exc.value, SE.EnumTableUnavailable)
    # `str(KeyError)` = `repr(args[0])` -> les antislashs d'un chemin Windows y sont
    # DOUBLES et le message devient illisible : le module rend donc le chemin en POSIX.
    assert SE.source_path().as_posix() in exc.value.args[0]


# ------------------------- 5. un decodage en panne n'annule pas une action DEJA APPLIQUEE

def test_print_apply_rend_sa_panne_au_lieu_de_la_lever(monkeypatch, capsys):
    """`applyAction` a DEJA mute le runner quand `_print_apply` s'execute. Une exception
    ici remontait jusqu'a `cmd_act`, court-circuitant l'append `action_log` + `_save_state` :
    l'appelant lisait « erreur » sur une action APPLIQUEE et la rejouait."""
    import rl_probe_step  # noqa: E402  (tire rl_collect_batch -- import paresseux volontaire)

    def _explose(*_a, **_k):
        raise SE.EnumTableUnavailable("table absente (simulee)")

    monkeypatch.setattr(SE, "analyze", _explose)
    res = {"ok": True, "actions": [{"kind": "move", "ok": True, "mutated": True,
                                    "eventCount": 1,
                                    "changes": [{"squadId": 42, "moved": True,
                                                 "from": {"col": 1, "row": 1},
                                                 "to": {"col": 2, "row": 1}}],
                                    "events": [_ev(0)]}]}
    echec = rl_probe_step._print_apply("MOVE u42", res, [42])
    assert echec, "la panne de decodage doit etre RENDUE a l'appelant"
    out = capsys.readouterr().out
    assert "u42" in out, "le diff d'etat (preuve que l'action a porte) doit rester imprime"
    assert "DEJA ETE APPLIQUEE" in out, "l'appelant doit etre averti de ne pas rejouer"
