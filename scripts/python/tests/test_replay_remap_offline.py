"""Cliquet HORS LIGNE de `replay_remap` -- sur les chiffres MESURES du 2026-08-24.

Le cas d'espece n'est pas invente : c'est la tentative reelle de boss de guilde ou le
deploiement est sorti en `[MoW] + reverse(unites)` (plateau PRE-REMPLI, donc regime << plateau
plein >>), la ou le replay attend `unites + [MoW]`.

    replay  : orksWarboss 79 | admecDominus 81 | admecRuststalker 83
              admecMarshall 85 | admecManipulus 87 | tyranBiovore 89
    vivant  : tyranBiovore 79 | admecManipulus 80 | admecMarshall 82
              admecRuststalker 84 | admecDominus 86 | orksWarboss 88

ASCII only.
"""
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RACINE / "scripts" / "python"))

import replay_remap as RR  # noqa: E402

REPLAY = {"orksWarboss": 79, "admecDominus": 81, "admecRuststalker": 83,
          "admecMarshall": 85, "admecManipulus": 87, "tyranBiovore": 89}
VIVANT = {"tyranBiovore": 79, "admecManipulus": 80, "admecMarshall": 82,
          "admecRuststalker": 84, "admecDominus": 86, "orksWarboss": 88}
BLOC = set(range(79, 90))          # 79..89 des DEUX cotes -- l'invariant (I)


def test_la_table_apparie_par_UNITE_et_pas_par_position():
    """Le coeur : c'est le NOM de l'unite qui apparie, jamais le rang dans la liste.

    Apparier par position rendrait l'identite (79->79, 81->80...) sur un ordre inverse, donc
    des coups qui frappent une AUTRE unite sans que rien ne refuse."""
    t = RR.table(REPLAY, VIVANT, BLOC, BLOC)
    assert t[79] == 88, "orksWarboss : replay 79 -> vivant 88"
    assert t[81] == 86, "admecDominus"
    assert t[83] == 84, "admecRuststalker"
    assert t[85] == 82, "admecMarshall"
    assert t[87] == 80, "admecManipulus"
    assert t[89] == 79, "tyranBiovore (la MoW, passee en TETE)"


def test_les_PIEDS_suivent_leur_squad():
    """Une unite consomme DEUX entites (squad N, unite N+1). Oublier le pied le laisserait en
    << identite >>, alors qu'il est permute comme son squad."""
    t = RR.table(REPLAY, VIVANT, BLOC, BLOC)
    for squad in (79, 81, 83, 85, 87):
        assert t[squad + 1] == t[squad] + 1, "pied de %d" % squad


def test_un_bloc_qui_ne_COINCIDE_pas_est_un_REFUS():
    """L'invariant (I). Si les blocs n'occupent pas le meme ensemble d'ids, une entite hors
    table ne peut plus etre declaree << identite >> -- tuiles, boss et unites nees en cours de
    partie deviennent indecidables. On refuse, on ne remappe pas << au mieux >>."""
    with pytest.raises(RR.Refus) as e:
        RR.table(REPLAY, VIVANT, BLOC, set(range(80, 91)))
    assert "meme ensemble d'ids" in str(e.value)


def test_une_unite_non_appariee_est_un_REFUS():
    partiel = dict(VIVANT)
    partiel.pop("orksWarboss")
    with pytest.raises(RR.Refus):
        RR.table(REPLAY, partiel, BLOC, BLOC)


def test_hors_du_bloc_reste_IDENTITE_et_dedans_sans_table_est_un_REFUS():
    """Les deux faces de la meme regle, et c'est la seconde qui protege.

    35/44/60/68 sont des TUILES, 77 le boss, 156/206 des unites nees en cours de partie : tous
    HORS bloc, donc identite. Un id DANS le bloc mais sans correspondance ne doit PAS retomber
    en identite par defaut -- ce serait un coup qui frappe a cote, en silence."""
    t = RR.table(REPLAY, VIVANT, BLOC, BLOC)
    refs = {35: [(7, "TargetId")], 77: [(8, "TargetId")], 156: [(20, "TargetId")],
            206: [(41, "TargetId")], 79: [(7, "UnitId")]}
    cl = RR.classer(refs, t, BLOC)
    hors = {x["entite"] for x in cl["identite"]}
    assert hors == {35, 77, 156, 206}
    assert cl["remappe"][79]["vers"] == 88
    assert cl["refus"] == []

    # La face qui protege : un id DANS le bloc, absent de la table.
    cl2 = RR.classer({85: [(9, "CasterId")], 999: [(9, "TargetId")]},
                     {79: 88}, BLOC)
    assert [r["entite"] for r in cl2["refus"]] == [85]
    assert [x["entite"] for x in cl2["identite"]] == [999]


def test_la_reecriture_ne_touche_QUE_les_champs_d_entite():
    """`ActiveAbilityType`, `PlayerId`, `SpawnSource`, les positions : des entiers qui ne
    designent AUCUNE entite. Les remapper serait une corruption silencieuse."""
    import json
    d = {"Messages": [{"Message": {"MessageJson": json.dumps({
        "Name": "ActiveAbilityMessage", "CasterId": 79, "TargetId": 77,
        "ActiveAbilityType": 79, "PlayerId": 11, "SkipFlags": False})}}]}
    neuf = RR.reecrire(d, {79: 88, 77: 12345})
    c = json.loads(neuf["Messages"][0]["Message"]["MessageJson"])
    assert c["CasterId"] == 88, "champ d'entite -> remappe"
    assert c["TargetId"] == 12345
    assert c["ActiveAbilityType"] == 79, "MEME VALEUR que le caster, mais ce n'est pas une entite"
    assert c["PlayerId"] == 11
    assert c["SkipFlags"] is False


def test_AddUnitMessage_porte_un_UnitId_CHAINE_qui_ne_doit_pas_bouger():
    """Le meme NOM de champ porte deux natures : entier (entite) dans un coup de combat,
    CHAINE (id de catalogue) dans une pose. Le filtre est le TYPE, pas le nom."""
    import json
    d = {"Messages": [{"Message": {"MessageJson": json.dumps({
        "Name": "AddUnitMessage", "UnitId": "orksWarboss", "PlayerId": 11})}}]}
    neuf = RR.reecrire(d, {79: 88})
    c = json.loads(neuf["Messages"][0]["Message"]["MessageJson"])
    assert c["UnitId"] == "orksWarboss"


def test_la_reecriture_ne_touche_PAS_l_OutputStream():
    """Le flux reste la reference ATTENDUE. Le reecrire ferait passer la confrontation par
    construction, et elle ne mesurerait plus rien."""
    import json
    d = {"Messages": [{"Message": {"MessageJson": json.dumps(
        {"Name": "MoveUnitMessage", "UnitId": 79})}, "OutputStream": "Entity=79 intact"}]}
    neuf = RR.reecrire(d, {79: 88})
    assert neuf["Messages"][0]["OutputStream"] == "Entity=79 intact"


def test_sur_le_replay_REEL_tout_est_classe_et_rien_n_est_refuse():
    """Le bout en bout, sur le fichier mesure -- s'il est encore la.

    Il vit sous `data/replays/_captures/`, qui n'est pas versionne : le test se SAUTE en le
    DISANT plutot que de rendre un vert sur rien."""
    import json
    f = RACINE / "data" / "replays" / "_captures" / "GuildBoss-29710292-f609810.json"
    if not f.exists():
        pytest.skip("capture absente (non versionnee) : %s" % f.name)
    d = json.loads(f.read_text(encoding="utf-8"))

    rep = RR.entites_du_replay(d)
    assert rep == REPLAY, "l'appariement se LIT dans le flux"
    bloc = RR.bloc_de_deploiement(d)
    assert bloc == BLOC, "bloc 79..89, PIEDS compris"

    refs = RR.ids_references(d)
    assert set(refs) >= {79, 81, 83, 85, 87, 89, 77, 156, 206}, "les ids adresses par les coups"
    t = RR.table(rep, VIVANT, bloc, BLOC)
    assert len(t) == 11, "la TABLE couvre 6 unites + 5 pieds"

    cl = RR.classer(refs, t, bloc)
    assert cl["refus"] == [], "aucun id indecidable"
    # `classer` ne rend que les ids REFERENCES : les coups adressent des SQUADS, jamais des
    # pieds, donc les 5 pieds de la table n'y apparaissent pas. La propagation aux pieds est
    # defensive -- elle ne sert que si un replay venait a en adresser un.
    assert sorted(cl["remappe"]) == [79, 81, 83, 85, 87, 89]
    assert {e: i["vers"] for e, i in cl["remappe"].items()} == {
        79: 88, 81: 86, 83: 84, 85: 82, 87: 80, 89: 79}
