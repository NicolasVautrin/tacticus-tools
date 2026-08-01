"""GARDE live de la LIGNE DE VUE (`TargetIsUnobscured`, bit 24) -- #444.

Le probe MESURE (`probe_444_obscured_targeting.py`), ce test GARDE : sur UN montage monte une fois,
il rejoue l'accord entre le gate natif (`abilityReason` ->
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`) et le port
(`engine/runner/abilities/targeting.get_invalid_target_reason`).

LE CRAFT, ET IL EST LE COEUR DU TEST : deux cibles a la MEME distance 2 du caster, l'une derriere un
relief (elevation >= +2), l'autre a decouvert. Un refus qui ne tomberait que sur la plus lointaine
accuserait la PORTEE -- qui PRECEDE la ligne de vue dans la cascade -- et l'erreur serait invisible.

CE QUE LE TEST EXIGE, ET POURQUOI CHAQUE EXIGENCE EST LA :
  * accord natif/port sur toutes les lignes imputables a cette tranche -- le fond ;
  * au moins une ligne ou le natif rend `TargetIsUnobscured` : sans elle la mesure ne distingue pas
    « la regle mord » de « le terrain n'obstrue rien ici » ;
  * cette ligne doit etre une ou le port AVANT rendait `0` (ACCEPTAIT) -- la degradation de cette
    regle est PERMISSIVE, donc un accord sur un cast ACCEPTE ne prouve RIEN ;
  * au moins une ligne ACCEPTEE des deux cotes A LA MEME DISTANCE : c'est l'AXE INVERSE, et il est
    le plus dangereux ici. La regle tourne pour les 103 masques lisibles ; un port trop strict
    casserait des casts legitimes EN MASSE. Le test refuse de passer sans cette contre-mesure ;
  * le DESARMEMENT par `AllowObscuredTarget` (bits 25|26) leve le refus -- CONFRONTE AU NATIF via le
    contraste attaque normale (`0x4002`) vs `HeroicFusillade` 1180 (`0x6004002`) sur la MEME paire ;
  * la valeur de `BC.Targeting.EnableObscuringTerrain` dans la seed versionnee : le port la prend
    pour defaut faute de canal RPC, donc si elle change ce test doit ROUGIR (offline).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import probe_444_obscured_targeting as P
from engine.runner.abilities.targeting_rule import TargetingRule as TR

UNOBSCURED = int(TR.TargetIsUnobscured)
NORMAL_ATTACK = P.NORMAL_ATTACK


@pytest.fixture(scope="module")
def mesure():
    """Rejoue le probe COMPLET et rend ses lignes. Le probe dispose SON runner (jamais ceux des
    autres)."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = P.main([])
    txt = buf.getvalue()
    print(txt[-4000:])
    raw = [ln for ln in txt.splitlines() if ln.startswith("[RAW] ")]
    assert raw, "le probe n'a pas rendu sa ligne [RAW] -- montage rate :\n" + txt[-3000:]
    data = json.loads(raw[-1][len("[RAW] "):])
    data["rc"] = rc
    return data


def _rows(mesure):
    return [r for r in mesure["rows"] if r["nat"] is not None]


def test_le_natif_refuse_pour_ligne_de_vue(mesure):
    """Sans une ligne `0x1000000`, la mesure ne prouve rien : le craft n'aurait realise aucune
    obstruction et l'accord porterait sur des cas ou la regle est muette."""
    refus = [r for r in _rows(mesure) if r["nat"] == UNOBSCURED]
    assert refus, ("aucune ligne ou le natif rend TargetIsUnobscured -- le craft "
                   "(caster %s / cible obscurcie %s) n'a pas realise d'obstruction"
                   % (mesure["craft"]["caster"], mesure["craft"]["blocked"]))


def test_le_port_rend_le_meme_refus(mesure):
    """L'accord sur les lignes REFUSEES pour ligne de vue."""
    for r in [x for x in _rows(mesure) if x["nat"] == UNOBSCURED]:
        assert r["port"] == UNOBSCURED, (
            "caster=u%d cible=u%d d=%d : natif=%s port=%s (tuiles obscurcissantes vues par le "
            "port : %s)" % (r["caster"], r["target"], r["d"], hex(r["nat"]), hex(r["port"]),
                            r["obscuring"]))


def test_la_degradation_fermee_etait_permissive(mesure):
    """Le port AVANT cette tranche (contrefactuel du CHAMP : `AllowObscuredTarget` pose) ACCEPTAIT
    la ligne que le natif refuse. C'est la seule forme de preuve qui vaille pour une regle dont la
    degradation est permissive."""
    refus = [r for r in _rows(mesure) if r["nat"] == UNOBSCURED]
    assert refus, "pas de ligne refusee -- cf. test_le_natif_refuse_pour_ligne_de_vue"
    leve = [r for r in refus if r["port_disarmed"] != UNOBSCURED]
    assert leve, ("aucune ligne refusee ne bascule au desarmement : le refus ne vient donc pas de "
                  "la ligne de vue")


def test_axe_inverse_les_casts_legitimes_passent(mesure):
    """L'AXE INVERSE. La regle tourne pour les 103 masques lisibles : un port trop strict serait une
    regression bien plus large que le trou qu'il ferme. On exige une cible ACCEPTEE des deux cotes
    A LA MEME DISTANCE que la cible refusee."""
    rows = _rows(mesure)
    refus = [r for r in rows if r["nat"] == UNOBSCURED]
    assert refus, "pas de ligne refusee -- cf. test_le_natif_refuse_pour_ligne_de_vue"
    d = refus[0]["d"]
    temoins = [r for r in rows
               if r["nat"] == 0 and r["d"] == d and r["ability"] == refus[0]["ability"]
               and not r["ally"]]
    assert temoins, ("aucune cible ACCEPTEE a la meme distance (%d) que la cible refusee : la "
                     "mesure ne separe pas la ligne de vue de la PORTEE" % d)
    for r in temoins:
        assert r["port"] == 0, (
            "cast LEGITIME refuse par le port : caster=u%d cible=u%d d=%d natif=0x0 port=%s "
            "tuiles=%s" % (r["caster"], r["target"], r["d"], hex(r["port"]), r["obscuring"]))


def test_le_natif_desarme_selon_le_masque(mesure):
    """Le DESARMEMENT confronte au NATIF (et pas seulement au port) : sur la MEME paire
    (caster, cible), l'attaque normale (`0x4002`) refuse pour ligne de vue et `HeroicFusillade`
    (1180, `0x6004002`, qui pose les bits 25 ET 26) accepte. Seule la permission change."""
    by_pair = {}
    for r in _rows(mesure):
        by_pair.setdefault((r["caster"], r["target"]), {})[r["ability"]] = r
    contraste = [v for v in by_pair.values()
                 if len(v) > 1 and any(x["nat"] == UNOBSCURED for x in v.values())
                 and any(x["nat"] == 0 for x in v.values())]
    assert contraste, ("aucune paire ou le natif rend TargetIsUnobscured pour un masque et 0 pour "
                       "un autre -- le desarmement n'est pas confronte")
    for v in contraste:
        for aid, r in v.items():
            assert r["port"] == r["nat"], (
                "desaccord sur le contraste de masques : ability=%d caster=u%d cible=u%d "
                "natif=%s port=%s" % (aid, r["caster"], r["target"], hex(r["nat"]), hex(r["port"])))


def test_aucun_desaccord_imputable_a_cette_tranche(mesure):
    """Tout desaccord dont l'un des deux cotes vaut `TargetIsUnobscured` est de CETTE tranche. Les
    autres sont anterieurs (regle dynamique de 1180 non portee, `TargetingRange` de 1202 non lu) --
    ils sont nommes dans la case-doc, pas masques.

    ⚠ Le critere ne peut PAS etre « le contrefactuel du champ fait disparaitre le desaccord » :
    neutraliser la regle dans le port rend `port == port_disarmed`, et le desaccord se classerait
    « preexistant ». Mesure de contre-epreuve : avec la regle neutralisee ce test restait VERT."""
    mine = [r for r in _rows(mesure)
            if r["nat"] != r["port"]
            and (UNOBSCURED in (r["nat"], r["port"]) or r["nat"] == r["port_disarmed"])]
    assert not mine, "\n".join(
        "caster=u%d ability=%d cible=u%d d=%d natif=%s port=%s port(desarme)=%s"
        % (r["caster"], r["ability"], r["target"], r["d"], hex(r["nat"]), hex(r["port"]),
           hex(r["port_disarmed"])) for r in mine)


def test_le_probe_rend_pass(mesure):
    assert mesure["rc"] == 0, "le probe a rendu rc=%s" % mesure["rc"]


def test_la_seed_versionnee_active_bien_l_obscurcissement():
    """OFFLINE. `TargetingQuery$$GetTilesObscuringTerrain` gate sur
    `IdunBattle.Configuration.TargetingConfiguration.EnableObscuringTerrain` (`config+0x10`), et
    AUCUN RPC ne le publie -- ce n'est ni un etat dynamique ni un composant d'entite, c'est un champ
    de la BattleConfiguration. Le port prend donc pour defaut la valeur LUE dans la seed versionnee,
    dont partent tous les runners `rl_duel build`. Si elle changeait, le defaut deviendrait une
    invention : ce test est ce qui l'empeche de le devenir en silence."""
    root = Path(__file__).resolve().parents[5]        # tests/engine/runner -> scripts/python -> racine
    bc = json.loads((root / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    val = (bc.get("Targeting") or {}).get("EnableObscuringTerrain")
    assert val is True, (
        "data/seed-bc.json Targeting.EnableObscuringTerrain = %r : le defaut `True` de "
        "`State.enable_obscuring_terrain` n'est plus la valeur de la seed -- il faut cabler le "
        "canal (`load_state(targeting_config=...)`) au lieu de s'appuyer sur ce defaut" % (val,))
