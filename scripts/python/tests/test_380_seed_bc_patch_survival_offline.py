"""#380 -- GARDE du RECENSEUR de patchs de seed BC. OFFLINE, aucune plateforme requise.

CE QUE CETTE GARDE TIENT. #375 a mesure qu'un patch de variable d'ability ecrit dans un seed BC
custom etait ECRASE en silence par `rl_collect_batch._load_seed_bc` (rattrapage #254), et que le
regime discriminant de #369 n'avait donc JAMAIS ete joue : un run VERT qui ne mesurait rien. La
parade #396 est OPT-IN -- elle ne protege que les fixtures qui la demandent. Il fallait donc un
RECENSEUR, et un recenseur dont on n'a jamais vu le rouge ne garantit rien.

Ces tests sont la MORSURE, figee :
  * il ROUGIT sur le cas connu de #369 (patch `LightImUp`, sidecar retire) ;
  * il VERDIT des que le sidecar est en place ;
  * il ROUGIT sur des patchs FABRIQUES pour l'occasion (`Constants`, `BC.Utilities`) ;
  * il ne rend AUCUN faux positif sur le seed BC partage, dont la derive de capture est du
    rattrapage #254 legitime et non un patch ;
  * l'axe ABSENCE (une config volontairement manquante, comblee par le chargeur) est couvert lui
    aussi : signal present sans retenue, eteint avec.

Ils tiennent AUSSI la reparation de `probe_226_seed_bc_ability_configs` : son bras `clone` (dont le
POINT est l'absence de config) repartait du chargeur AVEC la config, donc identique a ses deux bras
temoins -- la mesure « A KO / B OK / C OK » n'etait plus reproductible.

ASCII only (cp1252).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import catalog_inject as CI                                             # noqa: E402
import probe_380_seed_bc_patch_survival as P380                         # noqa: E402


@pytest.fixture(scope="module")
def base_bc():
    return json.loads(Path(CI.SEED_BC).read_text(encoding="utf-8"))


# --- la MORSURE : le recenseur voit-il le cas qui a coute #369 ? ---------------------------------

def test_le_cas_369_rougit_sans_sidecar_et_verdit_avec(tmp_path):
    """Le patch de #369, exactement : `LightImUp` au niveau 50, hors gameconfig.

    Sans sidecar il est reverti a `831` par `_load_seed_bc`, SANS un mot -- c'est la mesure de
    #375. Le recenseur doit le NOMMER, pas le laisser passer.
    """
    p, _rep = CI.write_variable_patched_seed_bc(
        tmp_path / "bc.json", [("LightImUp", 50, {"minDmg": 20000, "maxDmg": 20001})])
    sidecar = CI.pins_path(p)
    saved = sidecar.read_text(encoding="utf-8")
    assert "PassiveAbilities/LightImUp" in saved, "la fixture doit poser son epingle (#396)"

    sidecar.unlink()
    rep = P380.check_seed_bc(p)
    assert [r["key"] for r in rep["overwritten"]] == ["PassiveAbilities/LightImUp"], rep
    with pytest.raises(P380.SeedBcPatchOverwritten):
        P380.assert_survives(p)

    sidecar.write_text(saved, encoding="utf-8")
    rep = P380.check_seed_bc(p)
    assert rep["overwritten"] == [], rep
    P380.assert_survives(p)                       # ne leve pas


def test_un_patch_fabrique_de_constants_rougit(tmp_path, base_bc):
    """Autre cle que #369 : le rattrapage remplace la config ENTIERE, pas seulement Variables."""
    bc = copy.deepcopy(base_bc)
    pa = bc["Abilities"]["PassiveAbilities"]
    victim = next(n for n, c in sorted(pa.items())
                  if (c.get("Constants") or {}) and CI.G.ability(n) is not None)
    key = sorted(pa[victim]["Constants"])[0]
    pa[victim]["Constants"][key] = "424242"
    p = tmp_path / "bc-constants.json"
    p.write_text(json.dumps(bc), encoding="utf-8")

    rep = P380.check_seed_bc(p)
    assert [r["key"] for r in rep["overwritten"]] == ["PassiveAbilities/" + victim], rep
    assert "Constants" in rep["overwritten"][0]["fields"]


def test_un_patch_de_bc_utilities_rougit_et_n_a_AUCUNE_epingle(tmp_path, base_bc):
    """Le 3e catalogue est ecrase EN ENTIER par `refresh_ai_utilities` (`bc["Utilities"] = new`),
    et il n'existe pour lui AUCUN mecanisme d'epinglage. C'est un piege arme : aucune fixture ne
    patche `BC.Utilities` aujourd'hui, la premiere qui le fera mesurera du nominal."""
    bc = copy.deepcopy(base_bc)
    bc["Utilities"] = CI.ai_utilities_from_gameconfig()
    cat = next(c for c, kv in sorted((bc["Utilities"].get("Default") or {}).items())
               if isinstance(kv, dict) and kv)
    k = sorted(bc["Utilities"]["Default"][cat])[0]
    bc["Utilities"]["Default"][cat][k] = int(bc["Utilities"]["Default"][cat][k]) + 777
    p = tmp_path / "bc-utilities.json"
    p.write_text(json.dumps(bc), encoding="utf-8")

    rep = P380.check_seed_bc(p)
    assert rep["utilities"]["state"] == "OVERWRITTEN", rep["utilities"]
    with pytest.raises(P380.SeedBcPatchOverwritten):
        P380.assert_survives(p)


def test_le_seed_bc_partage_ne_rend_aucun_faux_positif():
    """La capture PARTAGEE derive du gameconfig (rattrapage #254) : c'est LEGITIME, pas un patch.

    Un recenseur qui les confondrait rougirait sur tout et ne servirait a rien. C'est le 3e terme
    (`base`) qui les separe.
    """
    rep = P380.check_seed_bc(CI.SEED_BC)
    assert rep["overwritten"] == [], rep["overwritten"]
    assert rep["utilities"]["state"] in ("OK", "STALE"), rep["utilities"]
    assert rep["stale"], "sur ce build la capture DOIT deriver (sinon le 3e terme n'est pas teste)"


# --- l'axe ABSENCE : un patch n'est pas toujours une valeur --------------------------------------

def test_une_absence_deliberee_est_comblee_sans_retenue_et_tenue_avec(tmp_path, base_bc):
    """La 2e boucle du rattrapage POSE toute config qu'une entree `Units` reclame au gameconfig.

    Une fixture dont le bras negatif EST l'absence voit donc ce bras neutralise. `withheld` (#380)
    le nomme ; sans lui, le signal doit au moins etre VISIBLE (`readded` hors ligne de base).
    """
    bc = copy.deepcopy(base_bc)
    pa = bc["Abilities"]["PassiveAbilities"]
    removed = None
    for u in bc["Units"]:
        _act, pas = CI._ability_names(u.get("Id") or "")
        cand = [n for n in pas if n in pa]
        if cand:
            removed = "PassiveAbilities/" + cand[0]
            del pa[cand[0]]
            break
    assert removed, "aucune config retirable -- montage invalide"
    p = tmp_path / "bc-absence.json"
    p.write_text(json.dumps(bc), encoding="utf-8")

    own = [r["key"] for r in P380.check_seed_bc(p)["readded"] if not r["baseline"]]
    assert removed in own, own

    CI.write_pins(p, [], withheld=[removed])
    own = [r["key"] for r in P380.check_seed_bc(p)["readded"] if not r["baseline"]]
    assert removed not in own, own


def test_une_retenue_contradictoire_leve(tmp_path, base_bc):
    """Une retenue qui ne retient rien (la config est presente) est un montage FAUX, pas un no-op.

    Symetrique exact de l'epingle orpheline de #375.
    """
    from rl_collect_batch import _load_seed_bc
    bc = copy.deepcopy(base_bc)
    present = sorted(bc["Abilities"]["PassiveAbilities"])[0]
    p = tmp_path / "bc-contradiction.json"
    p.write_text(json.dumps(bc), encoding="utf-8")
    CI.write_pins(p, [], withheld=["PassiveAbilities/" + present])
    with pytest.raises(RuntimeError, match="CONTRADICTOIRES"):
        _load_seed_bc(str(p))


# --- la REPARATION de probe_226 : ses trois bras redeviennent distincts --------------------------

def test_probe_226_bras_A_arrive_au_runner_SANS_sa_config(tmp_path):
    """Le bras `clone` de #226 mesure l'ABSENCE de config. Avant #380 le chargeur la reposait :
    les trois bras livraient la MEME chose et la discrimination A KO / B OK / C OK avait disparu.

    Le verdict #226 lui-meme reste juste -- mesure le 2026-07-29 a 00h38, rattrapage #254 pose a
    19h17 le meme jour. C'est la REPRODUCTIBILITE qui etait perdue.
    """
    from rl_collect_batch import _load_seed_bc
    import probe_226_seed_bc_ability_configs as P226

    got = {}
    for mode in ("clone", "clone-cfg", "inject"):
        path = P226.build_seed(mode, "bloodTerminator", "bloodDeathCompany", 1230,
                               "380test-" + mode)
        loaded = _load_seed_bc(str(path))
        act = (loaded.get("Abilities") or {}).get("ActiveAbilities") or {}
        got[mode] = "SavageEchoes" in act
    assert got == {"clone": False, "clone-cfg": True, "inject": True}, got


# --- le BALAYAGE : il trouve les producteurs, et il DIT ce qu'il ne voit pas ---------------------

def test_le_balayage_trouve_la_fixture_de_369():
    """Le recenseur statique doit pointer le module qui a produit le cas connu."""
    rows = {r["path"].name: r for r in P380.scan()}
    fx = rows.get("probe_369_playbook_keyspace.py")
    assert fx is not None, sorted(rows)
    assert any(axis == "ABILITIES" for _ln, axis, _d, _i in fx["risky"]), fx["risky"]
    assert P380._verdict(fx) == "A-LIRE", P380._verdict(fx)


def test_le_balayage_ne_confond_pas_un_champ_d_unite_avec_le_2e_catalogue():
    """`u["ActiveAbilities"]` (champ d'une entree `Units`, SURVIT) et
    `bc["Abilities"]["ActiveAbilities"]` (2e catalogue, ECRASE) portent le meme mot.

    Les confondre rendrait un balayage bruyant et inutilisable -- c'est pour cela qu'il lit un AST
    et non un grep. `probe_27_4f_stikkbomb_ab` ne fait que le premier.
    """
    rows = {r["path"].name: r for r in P380.scan()}
    r = rows.get("probe_27_4f_stikkbomb_ab.py")
    assert r is not None, sorted(rows)
    assert r["risky"] == [], r["risky"]
    assert P380._verdict(r) == "SANS-PATCH", P380._verdict(r)
