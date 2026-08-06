"""GARDE #419-r1-tr14-r4 -- la face COMBAT de `HeavyBoltPistol` (1083) : le COUP DE PISTOLET.

Confronte l'EXECUTION (degats appliques, ventilation par coup) du port au natif, sur les TROIS
crans mesures par `probe_419r1tr14r4_heavy_bolt_pistol_bonus_attack.py`. Ce n'est PAS le terme du
playbook : decider != executer, et la face DECISION (#419-r1-tr14, -r1) ne dit rien de ce qui part.

Les trois crans, et ce que chacun tranche :

| cran | hote (arme) | distance | TERME natif attendu |
|---|---|---|---|
| `npc_adj`   | `templNpc1Initiate:33` (`Chain`, melee) -- le porteur REEL | contact | **+299 PV** |
| `graft_adj` | `tauMarksman` (`Piercing` 3, portee) -- 1083 greffe      | contact | **+299 PV** |
| `graft_far` | idem                                                     | 2 hex   | **+0 PV** |

Le zero de `graft_far` n'est PAS un regime degenere : le MEME montage rend `+299` au contact
(`graft_adj`). C'est ce couple qui etablit que la gate est la branche `Normal(3)` de
`BattleQuery$$IsMeleeAttack` (adjacence), ni `Melee(1)` ni `None(0)`.

⚠ Les mutants sont gardes CRAN PAR CRAN, avec leur cause : `profile_weapon` est ALGEBRIQUEMENT
INERTE sur le porteur reel (`Chain` et `Bolter` partagent `PiercingRatio = 20`) et ne MORD que sur
la greffe (`Piercing`, 80) ; `no_gate` est inerte partout ou la gate est deja vraie et ne MORD qu'a
2 hex. Les exiger mordants partout ferait rougir la garde pour une cause etrangere ; les taire
laisserait sans garde deux lectures load-bearing. L'equivalence `Chain == Bolter` est elle-meme
ASSERTEE : si elle cesse, `profile_weapon` doit redevenir mordant sur le npc.
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(_HERE))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_419r1tr14_heavy_bolt_pistol as P                        # noqa: E402
import probe_419r1tr14r1_heavy_bolt_pistol_real_carriers as R1       # noqa: E402
import probe_419r1tr14r4_heavy_bolt_pistol_bonus_attack as R4        # noqa: E402

#: Le TERME attendu, en PV sur la cible. Il n'est PAS un scalaire fitte : il se DECOMPOSE --
#: `(level 50, multiplier 180)` mesures sur l'entite -> `ability_var(HeavyBoltPistol, dmg) = 1496`,
#: puis percage `Bolter` 20 % -> 299. C'est pourquoi il vaut la MEME chose sur les deux hotes, dont
#: les armes different.
TERME = 299

#: Ce que chaque contre-epreuve doit faire, CRAN PAR CRAN (cf. l'en-tete pour les deux inerties
#: expliquees). `True` = doit MORDRE, `False` = doit rester INERTE.
ATTENDU = {
    "npc_adj":   {"no_gate": False, "gate_off": True, "no_dispatch": True,
                  "profile_weapon": False, "amount_half": True, "hits_two": True},
    "graft_adj": {"no_gate": False, "gate_off": True, "no_dispatch": True,
                  "profile_weapon": True, "amount_half": True, "hits_two": True},
    "graft_far": {"no_gate": True, "gate_off": False, "no_dispatch": False,
                  "profile_weapon": False, "amount_half": False, "hits_two": False},
}

CRANS = (("npc_adj", "npc", "A", TERME),
         ("graft_adj", "graft", "A", TERME),
         ("graft_far", "graft", "B", 0))


def _rpc_and_session():
    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    return sid, rpc


def _logs_dir() -> str:
    d = os.path.join(os.path.dirname(os.path.dirname(_PY)), "logs")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture(scope="module")
def crans():
    """Monte les TROIS crans, une paire de runners par cran, et rend leurs mesures.

    Les runners sont disposes des que le cran est mesure : au plus DEUX vivants a la fois (le
    plafond de 4 est PARTAGE avec les autres agents)."""
    sid, rpc = _rpc_and_session()
    logs, out = _logs_dir(), {}
    for name, montage, spot, _want in CRANS:
        sf_g = os.path.join(logs, f"test_hbp_r4_{name}_{os.getpid()}_g.json")
        sf_b = os.path.join(logs, f"test_hbp_r4_{name}_{os.getpid()}_b.json")
        if montage == "npc":
            args_g, args_b = R1.build_args("npc", "graft"), R1.build_args("npc", "base")
            host = R1.CARRIERS["npc"]["visual"]
        else:
            args_g, args_b = P.build_args(logs, "graft"), P.build_args(logs, "base")
            host = P.HOST
        rid_g = R1._build(sf_g, args_g)
        rid_b = R1._build(sf_b, args_b)
        try:
            if montage == "npc":
                graft = R1.stage(sid, rpc, rid_g, "npc", None, True)
                base = R1.stage(sid, rpc, rid_b, "npc", graft["layout"], False)
            else:
                graft = P.stage(sid, rpc, rid_g, None, True)
                base = P.stage(sid, rpc, rid_b, graft["layout"], False)
            rg = R4.measure_arm(sid, rpc, graft, spot, True)
            rb = R4.measure_arm(sid, rpc, base, spot, False)
            out[name] = {
                "host": host, "spot": spot,
                "terme_natif": rg["natif"]["degat_cible"] - rb["natif"]["degat_cible"],
                "terme_port": rg["port"]["degat_cible"] - rb["port"]["degat_cible"],
                "natif_g": rg["natif"], "port_g": rg["port"],
                "natif_b": rb["natif"], "port_b": rb["port"],
                "muts": {m["mutant"]: m for m in
                         R4.run_mutants(rg["bundle"], rg["port"]["degat_cible"], host)},
                "profils": R4.profile_equivalence(host)}
        finally:
            R1._dispose(sf_g)
            R1._dispose(sf_b)
    return out


@pytest.mark.parametrize("name,_montage,_spot,want", CRANS)
def test_terme_natif_est_celui_attendu(crans, name, _montage, _spot, want):
    """ETAGE 1 -- ce que le NATIF fait. La garde arbitre d'abord le natif, jamais le port : si le
    terme natif change, c'est le REGIME qui a bouge et tout le reste est a re-instruire."""
    c = crans[name]
    assert c["terme_natif"] == want, (
        f"[{name}] le TERME NATIF vaut {c['terme_natif']:+d} PV au lieu de {want:+d} -- le regime "
        f"mesure a change (hote {c['host']}, spot {c['spot']}) ; coups natifs "
        f"graft={c['natif_g']['hits']} base={c['natif_b']['hits']}")


@pytest.mark.parametrize("name,_montage,_spot,_want", CRANS)
def test_port_accorde_le_terme_au_natif(crans, name, _montage, _spot, _want):
    """ETAGE 2 -- le PORT rend le meme terme que le natif. C'est la tranche."""
    c = crans[name]
    assert c["terme_port"] == c["terme_natif"], (
        f"[{name}] TERME porte {c['terme_port']:+d} != TERME natif {c['terme_natif']:+d} "
        f"(ecart {c['terme_port'] - c['terme_natif']:+d} PV) -- la face COMBAT de HeavyBoltPistol "
        f"ne reproduit pas l'execution native")


@pytest.mark.parametrize("name,_montage,_spot,_want", CRANS)
def test_ventilation_par_coup(crans, name, _montage, _spot, _want):
    """ETAGE 3 -- COMMENT. Le delta de PV dit COMBIEN ; la ventilation dit si le coup de pistolet
    est un coup SEPARE (natif : un coup de plus, `Active_Ability_Type = None`, la signature d'un
    `AttackDamageBehaviour` sans ability ACTIVE) ou un montant fondu dans les coups d'arme."""
    c = crans[name]
    n_nat = len(c["natif_g"]["hits"])
    n_port = len(c["port_g"]["coups_arme"]) + len(c["port_g"]["coups_bonus"])
    assert n_nat == n_port, (
        f"[{name}] le natif emet {n_nat} coups {c['natif_g']['hits']} et le port en joue {n_port} "
        f"(arme {c['port_g']['coups_arme']} + bonus {c['port_g']['coups_bonus']}) -- meme total de "
        f"degats, la ventilation differe")
    bonus = c["port_g"]["coups_bonus"]
    if c["terme_natif"]:
        assert bonus == [c["terme_natif"]], (
            f"[{name}] le coup BONUS porte doit valoir exactement le terme natif "
            f"{c['terme_natif']} PV, il vaut {bonus}")
        assert c["natif_g"]["kinds"][-1] is None, (
            f"[{name}] le DERNIER coup natif doit porter `Active_Ability_Type = None` (la signature "
            f"d'un `AttackDamageBehaviour` dont l'`AbilityOrEffect` est une TRIGGERED), il porte "
            f"{c['natif_g']['kinds'][-1]}")
    else:
        assert bonus == [], f"[{name}] aucun coup bonus attendu, le port en joue {bonus}"


@pytest.mark.parametrize("name,_montage,_spot,_want", CRANS)
def test_contre_epreuves(crans, name, _montage, _spot, _want):
    """Les SIX contre-epreuves, CRAN PAR CRAN. Le critere est le DEPLACEMENT par rapport au port
    non mute, jamais l'ecart au natif (piege #441/#446).

    Les inerties attendues sont gardees A L'ENVERS (on EXIGE qu'elles restent inertes) : si l'une
    se met a mordre, le montage a change de regime et la borne doit etre re-instruite."""
    c = crans[name]
    bad = []
    for m, doit_mordre in ATTENDU[name].items():
        got = c["muts"][m]
        if got["erreur"]:
            bad.append(f"{m}: ERREUR {got['erreur']}")
        elif bool(got["a_mordu"]) != bool(doit_mordre):
            bad.append(f"{m}: a_mordu={got['a_mordu']} (attendu {doit_mordre}), "
                       f"deplacement={got['shift']:+d}")
    assert not bad, f"[{name}] contre-epreuves en desaccord : {bad}"


def test_equivalence_de_profil_du_porteur_reel(crans):
    """La CAUSE de l'inertie de `profile_weapon` sur le npc, ASSERTEE et non supposee.

    Si `Chain` cesse de partager son `PiercingRatio` avec `Bolter`, ce mutant redevient
    discriminant sur le porteur reel et `ATTENDU["npc_adj"]["profile_weapon"]` doit passer a `True`
    -- cette ligne est ce qui le fera savoir."""
    pe = crans["npc_adj"]["profils"]
    assert pe["equivalent"], (
        f"`Chain` ({pe['weapon_piercing']}) et `Bolter` ({pe['ability_piercing']}) ne partagent "
        f"PLUS leur PiercingRatio : `profile_weapon` redevient discriminant sur le porteur reel")
    pg = crans["graft_adj"]["profils"]
    assert not pg["equivalent"], (
        f"la GREFFE a perdu son pouvoir discriminant sur l'axe PROFIL : arme {pg['weapon']} "
        f"({pg['weapon_piercing']}) == ability {pg['ability']} ({pg['ability_piercing']}) -- plus "
        f"aucun montage ne garde la lecture << le profil vient de l'ABILITY >>")
