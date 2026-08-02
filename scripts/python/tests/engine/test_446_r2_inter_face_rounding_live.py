"""#446-r2 -- GARDE LIVE : les deux faces de modifiers ne partagent pas un arrondi.

Le montage est le controle APPARIE de #446-r1 (`MC1_67`/`41504`, `templAggressor` prive de ses
passifs -> attaque normale generique `69`, AUCUN fold en jeu), armures EGALISEES. Il met cote a
cote deux cibles aux entrees d'etage IDENTIQUES (meme base, meme percage, meme armure, meme compte
de coups, meme facteur `1.5`) qui ne different QUE par la FACE portant ce facteur :

  * `T` = `astraBullgryn`, sur la tuile Thorns de `MC1_67` -> modification de stat DEFENSE `-50`,
    negee par `CalculateModifiersFromStatModifications(negate=1)` -> `x1.5` cote **DEFENSEUR** ;
    et le caster tire d'en BAS (elevation 3 contre 4) donc AUCUN bonus d'elevation ;
  * `A` = `astraOrdnance`, plus bas que le caster -> `x1.5` cote **ATTAQUANT** (elevation), et
    aucune modification de stat.

Le natif rend `434` par coup sur `T` et `433` sur `A` -- MEME percage `288.99999993`. C'est
l'arrondi INCONDITIONNEL de `CalculateBaseDamageWithModifiers` sur la face ATTAQUANT (multiplicateur
NEUTRE) qui materialise `289` avant que le `x1.5` DEFENSEUR ne s'applique.

CE QUE CETTE GARDE VERROUILLE :
  1. le REGIME est bien installe (T porte la modification DEFENSE, A n'en porte pas, et les
     entrees d'etage sont identiques par ailleurs) -- sans ca la mesure ne tranche rien ;
  2. natif == port a l'UNITE sur les DEUX cibles, bornes ET compte de coups ;
  3. les deux cibles ne rendent PAS la meme borne MIN (l'asymetrie est le fait mesure).

ASCII only. Probe jumeau : `scripts/python/probe_446_r2_base_min_residual.py`.
"""
from __future__ import annotations

import pytest

import probe_446_boltstorm_pair_term as P446
import probe_446_r2_base_min_residual as R2

ARMOR = 3513          # armures EGALISEES : la seule difference restante est la FACE du `x1.5`


@pytest.fixture(scope="module")
def r2_case(live_session, rpc, build_runner):
    try:
        rid = build_runner(P446.SEED, R2.build_args(ARMOR))["rid"]
        return R2.stage(live_session, rpc, rid)
    except P446.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def r2_rows(r2_case, rpc):
    tile = tuple(r2_case["layout"]["C"])
    out = {}
    for key in ("T", "A"):
        uid = r2_case["ids"][key]
        nat = R2.native_event(rpc, r2_case["rid"], r2_case["cid"], uid, r2_case["ab"], tile)
        if nat is None:
            pytest.fail(f"aiPlaybookPredict indisponible pour {key}", pytrace=False)
        ev, meta = R2.port_stage(r2_case["ctx"], uid, tile)
        if ev is None:
            pytest.fail(f"le port ne predit rien pour {key}", pytrace=False)
        f = ev.composite_fields()
        sms = rpc("statModSources", {"runnerId": r2_case["rid"], "unitId": uid,
                                     "stats": ["defense"], "minAbs": 0}, 120) or {}
        defense = None
        for u in (sms.get("units") or []):
            if u.get("entityId") == uid:
                defense = ((u.get("mods") or {}).get("defense") or {}).get("total")
        out[key] = {
            "uid": uid, "meta": meta, "defense_mod": defense,
            "nat": (int(nat.get("willKillDmg") or 0), int(nat.get("mightKillDmg") or 0),
                    int(nat.get("appliedHits") or 0)),
            "port": (int(f.get("rawHealthDmgMin") or 0), int(f.get("rawHealthDmgMax") or 0),
                     int(f.get("appliedHits") or 0))}
    return out


def test_regime_installe(r2_rows):
    """(1) Le montage porte-t-il bien les DEUX faces, et rien d'autre ? On refuse la mesure plutot
    que de lire un accord qui ne prouverait rien."""
    t, a = r2_rows["T"], r2_rows["A"]
    assert t["defense_mod"], (
        f"la cible T ne porte AUCUNE modification de stat DEFENSE (total={t['defense_mod']}) : "
        "la face DEFENSEUR n'est pas exercee -- montage NON INSTALLE")
    assert not a["defense_mod"], (
        f"la cible A porte une modification DEFENSE (total={a['defense_mod']}) : les deux cibles "
        "ne sont plus discriminantes")
    assert (t["meta"]["mods"], t["meta"]["mods_def"]) == (None, [1.5]), (
        f"T : faces attendues (ATT=None, DEF=[1.5]), obtenues "
        f"({t['meta']['mods']}, {t['meta']['mods_def']})")
    assert (a["meta"]["mods"], a["meta"]["mods_def"]) == ([1.5], None), (
        f"A : faces attendues (ATT=[1.5], DEF=None), obtenues "
        f"({a['meta']['mods']}, {a['meta']['mods_def']})")
    for k in ("base", "pierce", "armor", "hits"):
        assert t["meta"][k] == a["meta"][k], (
            f"entree d'etage `{k}` differente entre T et A ({t['meta'][k]} vs {a['meta'][k]}) : "
            "les deux cibles ne sont plus appariees")


def test_natif_egale_port_sur_les_deux_faces(r2_rows):
    """(2) L'accord, a l'UNITE, bornes ET coups. Avant #446-r2 : T port `(1299,1950,3)` contre
    natif `(1302,1950,3)`."""
    for key, row in r2_rows.items():
        assert row["port"] == row["nat"], (
            f"[{key}] u{row['uid']} port={row['port']} != natif={row['nat']} "
            f"(faces ATT={row['meta']['mods']} DEF={row['meta']['mods_def']})")


def test_les_deux_faces_ne_rendent_pas_la_meme_borne(r2_rows):
    """(3) L'ASYMETRIE est le fait. Si les deux cibles rendaient la meme borne MIN, c'est que les
    faces ont ete refusionnees -- et (2) passerait quand meme si le natif changeait avec."""
    t_min, a_min = r2_rows["T"]["nat"][0], r2_rows["A"]["nat"][0]
    assert t_min != a_min, (
        f"le NATIF rend la meme borne MIN sur les deux faces ({t_min}) : le regime n'est plus "
        "discriminant, cette garde ne verrouille plus rien")
    assert t_min - a_min == 3, (
        f"ecart natif attendu +3 (3 coups x 1 point), obtenu {t_min - a_min}")
