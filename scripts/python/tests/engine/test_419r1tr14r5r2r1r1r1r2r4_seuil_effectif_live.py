"""#419-r1-tr14-r5-r2-r1-r1-r1-r2-r4 -- le seuil de `ShouldExecute` vaut `Fix64(10)`, pas `Fix64(1)`.

La tranche precedente avait lu le seuil dans le `.cctor` de CHAQUE classe derivee (`Fix64(1)` pour
quatre d'entre elles, rien pour les huit autres, donc `Fix64(0)`), et avait mesure un ecart
PERMISSIF qu'elle n'expliquait pas : le natif refusait encore a `u = 5`, tres au-dessus du seuil lu.

Ce fichier garde le fait qui l'explique, et les deux mesures qui le prouvent.

  1. **LE CHAMP A DEUX ECRIVAINS.** `<X>Playbook$$ShouldExecute` lit le PREMIER static de sa classe.
     `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.cctor` y
     ecrit `FixMath.NET.Fix64$$op_Implicit(0xa)` -- le SEUL `Fix64(10)` de la couche playbook -- et
     il ecrit en DERNIER (le `.cctor` derive part au `class_init` de la classe derivee, celui de la
     base part plus tard, avec `ComparablePlaybook<T>..ctor` que le `.ctor` derive appelle ENSUITE).
  2. **LE SEUIL EST ENCADRE, ET L'ENCADREMENT EXCLUT LES DEUX LECTURES PRECEDENTES.** Deux points
     calibres autour de 10 (`u x (maxHP + 2)` invariant a degat constant) : le natif refuse juste
     en dessous, accepte juste au-dessus. Largeur ~3e-4, soit 3e-5 relatif.
  3. **DEUX IDENTITES AUX `.cctor` OPPOSES DONNENT LE MEME SEUIL.** `1150 PlasmaCannon` DECLARE un
     `.cctor` (`Fix64(1)`), `1069 SeekerMissileFrequencyLock` n'en declare AUCUN (donc `Fix64(0)`
     par zero-initialisation). Les deux basculent a 10. C'est ce temoin qui interdit de relire le
     seuil dans le `.cctor` derive -- un montage sur la seule `1150` laisserait « 1 » plausible.
     Le temoin est GREFFE sur le meme caster (`case-92` §5bis) : legitime ici parce que
     `ShouldExecute` ne lit NI stats NI traits du caster.
  4. **LA CAUSE CONCURRENTE EST REFUTEE AU DECOMPILE.** Le predicat que
     `Bucket<...>$$AddAction`/`$$ChooseAction` appliquent est `Bucket<...>$$IsValidAction` =
     `action != null && (!MinUtility.HasValue || action.Utility >= MinUtility.Value)`. Les DEUX
     buckets du chemin `ActiveAbilityActionGenerator` ont un seuil INERTE (ctor sans seuil ->
     `HasValue == false` ; `ComparablePlaybook<T>$$EvaluateInternal` -> `Fix64.MinValue`). Aucun
     filtre au-dessus du playbook ne peut donc refuser sur l'utilite.

⚠ CE QUI N'EST PAS COUVERT, et le probe l'evite exprès : `u` EXACTEMENT egal au seuil. Le natif y
rend `10 + 9.3e-9` (Fix64 Q32.32) la ou le port calcule `10.0` pile (flottant) -- le natif ACCEPTE,
le port REFUSE, pour une raison d'ARITHMETIQUE et non de seuil. Mesure dans la case-doc.

Mesures et RE : `docs/rl/case-419-r1-tr14-r5-r2-r1-r1-r1-r2-r4-seuil-effectif.md`. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr14r5r2r1r1r1r2r4_ecart_permissif.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r1r1r1r2r4_ecart_permissif as R
from engine.playbook.static_threshold_gate import STATIC_UTILITY_THRESHOLD


# ---------------------------------------------------------------- crans OFFLINE

def test_les_quatre_corps_du_bucketsystem_sont_lisibles_en_GHIDRA_pas_en_FRIDA():
    """Le predicat n'etait lisible QUE la : les quatre corps sont `__Il2CppFullySharedGeneric`,
    donc structurellement ABSENTS du dump Frida (le `methodPointer` d'une definition generique est
    un thunk, cf. `docs/rl/case-259-couverture-gshared.md`). Conclure « illisible » de leur absence
    cote Frida aurait ferme la seule voie."""
    res = R.etape1_predicat_offline(verbose=False)
    assert res["bad"] == 0
    assert len(res["rows"]) == 4
    for row in res["rows"]:
        assert row["va"] is not None, row["symbol"]
        assert row["inFrida"] is False, row["symbol"]


def test_le_seul_capteur_live_de_cet_ancrage_est_fige_sur_un_AUTRE_build():
    """`frida/hooks/features/bucket-audit.ts` resout `AddAction`/`ChooseAction`/`IsValidAction` par
    RVA ECRITE EN DUR. Le cran ne juge pas ce choix (le module se documente lui-meme comme
    diagnostic-only) : il MESURE que ces RVA ne sont pas celles du build courant, ce qui est la
    raison pour laquelle le predicat a du etre lu au decompile plutot qu'observe live.

    Il rougit AUSSI si quelqu'un rafraichit les RVA sans le dire -- et c'est voulu : le fait
    change alors, et cette docstring avec lui."""
    res = R.etape1_predicat_offline(verbose=False)
    stale = res["staleAuditRvas"]
    assert len(stale) == 4, stale
    for s in stale:
        assert s["hook"] != s["build"], s


def test_le_seuil_porte_est_DIX():
    assert STATIC_UTILITY_THRESHOLD == 10.0
    assert R.THRESHOLD == STATIC_UTILITY_THRESHOLD
    assert R.FIX64_TEN_RAW == 10 * (1 << 32) == 42949672960


# ---------------------------------------------------------------- crans LIVE

@pytest.fixture(scope="module")
def brackets(tmp_path_factory):
    """Les DEUX encadrements, joues UNE fois pour tout le module (6 runners, un a la fois)."""
    logs = str(tmp_path_factory.mktemp("thr419r2r4"))
    return {"1150": R.etape3_encadrement(logs, verbose=True),
            "1069": R.etape4_temoin_greffe(logs, verbose=True)}


def _check(res, ability):
    assert res["bad"] == 0, res
    rows = res["rows"]
    assert len(rows) == 3, rows
    for r in rows:
        assert r["ability"] == ability, r
        assert r["frozen"], (r["tag"], "la mutation Movement=0 n'a pas mordu")
        assert r["dist"] == 3, r["tag"]
        assert not r["normalPlan"], (r["tag"], "l'attaque normale a un plan")
        assert r["castableHere"], (r["tag"], "l'ability ne porte pas d'ici")
    return res


def test_live_le_seuil_de_1150_encadre_DIX_et_exclut_UN(brackets):
    """`1150 PlasmaCannon` DECLARE un `.cctor` qui ecrit `Fix64(1)`. Si ce `1` etait le seuil, le
    natif accepterait des `u = 1.0001` -- il refuse encore a `u = 9.9997`."""
    res = _check(brackets["1150"], 1150)
    assert res["under"] < STATIC_UTILITY_THRESHOLD < res["over"]
    assert res["over"] - res["under"] < 1e-3, (res["under"], res["over"])
    assert res["under"] > 1.0     # le seuil `Fix64(1)` de la tranche precedente est EXCLU


def test_live_le_temoin_a_cctor_OPPOSE_donne_le_MEME_seuil(brackets):
    """`1069 SeekerMissileFrequencyLock` ne declare AUCUN `.cctor` : la tranche precedente en
    concluait `Fix64(0)`. Elle bascule pourtant au MEME endroit. Deux seuils DECLARES opposes, un
    seul seuil effectif -- c'est ce qui interdit de relire le seuil dans le `.cctor` derive."""
    res = _check(brackets["1069"], 1069)
    assert res["under"] < STATIC_UTILITY_THRESHOLD < res["over"]
    assert res["over"] - res["under"] < 1e-3, (res["under"], res["over"])
    assert res["under"] > 0.0     # le seuil `Fix64(0)` de la tranche precedente est EXCLU
    assert res["rows"][0]["playbook"] == "SeekerMissileFrequencyLockPlaybook"


def test_live_le_port_et_le_natif_s_accordent_sur_les_QUATRE_points(brackets):
    """Ce que la correction de seuil achete : l'accord DANS LES DEUX SENS de part et d'autre du
    seuil, sur les deux identites. C'est le residu `-r4` referme."""
    for key, ability in (("1150", 1150), ("1069", 1069)):
        for r in brackets[key]["rows"]:
            if r["tag"].endswith("_cal"):
                continue
            assert bool(r["native"]) == bool(r["port"]), (key, r["tag"], r["u"], r["msgs"])
