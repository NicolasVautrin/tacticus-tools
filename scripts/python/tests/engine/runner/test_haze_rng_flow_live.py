"""case-#221 -- GARDE du FLUX RNG du report de degat `HazeOfCorruption`.

Critere : le port consomme-t-il le MEME nombre de `genrand_int32` que le natif, aux MEMES points ?
Un ecart de flux est INVISIBLE sur le degat (case-209 etait deja bit-exact 6/6) mais desynchronise
tout ce qui tire APRES dans le meme tour -- d'ou cette garde separee.

Les regimes LIVE font varier UN etage a la fois, ce qui est ce qui a permis d'ATTRIBUER les tirages
au lieu de les deviner :

  * PV 8000        -> la cible SURVIT : ni coup bonus ni transfert (temoin bas, 4 tirages) ;
  * PV 6000        -> mort au 3e coup, 2 transferts (8) ;
  * PV 5000        -> mort au 2e coup, 3 transferts (9)  -> isole le cout PAR TRANSFERT ;
  * PV 6000 k = 0  -> aucun relais, donc aucun bond ni transfert (5) -> isole le cout du coup BONUS.

Le TEMOIN independant du compte est la pose de `Contaminated` (1244) par le `Maybe(25)` d'
`OnToxicDamageAbility` : on resout le rang candidat du flux en `NextBool[1,99]` et on confronte a
`tileMeta`. C'est lui qui etablit que le natif emet `On(DamageDealt = 0x10)` sur un coup qui tombe
sur un CADAVRE (`Amount 0`), et que la tuile posee est celle de la CIBLE, pas celle du relais.

OFFLINE : les invariants de structure que les quatre correctifs reposent.
"""
from __future__ import annotations

import pytest

PROBE = "probe_221_haze_rng_flow"


def _row(hp, seed="777", k=1):
    import importlib
    P = importlib.import_module(PROBE)
    rpc = P._mkrpc()

    class _A:
        armor, stacks = 0, 0
    a = _A()
    a.k = k
    r = P._run(rpc, seed, hp, a)
    assert r is not None, "montage KO (seed %s hp %s k %s)" % (seed, hp, k)
    return r


# --------------------------------------------------------------------------- OFFLINE (structure)

def test_on_damage_dealt_n_est_pas_gate_par_l_applique():
    """`ApplyDamageOperation$$Execute` : `On(0x10)` est sous `local_7e8 == 0` SEUL -- aucun terme
    `0 < local_7dc`. Le port doit donc gater sur le degat SANTE **DEMANDE**, pas sur l'applique.
    Ce test lit le SOURCE du chokepoint : un retour au gate `applied > 0` le casse."""
    import inspect
    from engine.runner.operations.damage import AttackDamageOperation
    src = inspect.getsource(AttackDamageOperation._apply_damage_pipeline)
    # la DERNIERE ligne `if ...:` qui precede l'appel = le gate effectif.
    head = src.split("damage_dealt_triggers(state,")[0].split("\n")
    gate = [ln.strip() for ln in head if ln.strip().startswith("if ") and ln.rstrip().endswith(":")]
    assert gate, "aucun gate lu devant `damage_dealt_triggers`"
    assert "total" in gate[-1] and "applied" not in gate[-1], (
        "le gate de `damage_dealt_triggers` doit porter sur le degat DEMANDE (`total`), "
        "pas sur l'applique -- gate lu : %r" % gate[-1])


def test_le_resolve_de_montant_n_a_pas_de_gate_largeur_1():
    """Mirror du slot 8 `DamagePrediction$$RandomlyResolveMinMaxDamage` : `Next(v, v+1)` consomme un
    tirage MEME sur une cellule degeneree. `HitDamage$$GetDamage`, lui, court-circuite -- et reste le
    bon appel pour la famille ABILITY (`AbilityDamageOperation$$ExecuteHits` l'appelle directement).
    On exerce les DEUX familles sur la MEME cellule degeneree, en comptant le MT."""
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.damage_hits import HitDamage

    n = [0]

    class _Counting(IntBasedMersenneTwister):
        """`call_count` compte les APPELS de haut niveau ; ici on veut les `genrand_int32`, la seule
        unite qui dit si le MT a avance."""
        __slots__ = ()

        def genrand_int32(self):
            n[0] += 1
            return IntBasedMersenneTwister.genrand_int32(self)

    def _n(is_attack):
        rng = _Counting()
        rng.init_genrand(777)
        n[0] = 0
        AttackDamageOperation._run_hits(rng, HitDamage(1397, 1397), HitDamage(1397, 1397),
                                        0, False, 1, None, is_attack_damage_op=is_attack)
        return n[0]

    assert _n(True) == 1, "famille ATTACK : le resolve slot-8 doit consommer 1 tirage"
    assert _n(False) == 0, "famille ABILITY : `HitDamage$$GetDamage` court-circuite -> 0 tirage"


def test_les_leftovers_de_montant_nul_sont_conserves():
    """`AddLeftoverHit` n'a AUCUN gate de montant (seul gate lu : l'octet `hitInfo+0x15`). Une entree
    de 0 -- le coup fatal qui tombe PILE sur les PV restants -- doit donc etre poussee : la filtrer
    coutait un `AttackDamage` (donc un resolve) et decalait le rang des transferts suivants."""
    from engine.runner.state import State
    from engine.runner.operations.left_over_damage import _append, left_over_damages
    st = State()
    e = st.add_entity()
    _append(st, e.id, 0, "Power")
    _append(st, e.id, 1397, "Toxic")
    assert [d["amount"] for d in left_over_damages(st, e.id)] == [0, 1397]


def test_une_seule_serie_pour_les_n_feuilles_du_transfert():
    """Les N `AttackDamage` vivent sous UN `AttackBehaviour` -> `IsFirstHitInSeries()` n'est vrai qu'a
    la premiere. Le port instancie une feuille par transfert : le drapeau doit donc etre PORTE par la
    feuille (sinon un transfert Toxic re-declenche le `Maybe` d'`OnToxicDamageAbility`)."""
    import inspect
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.operations.triggers.loki import haze_of_corruption as H
    assert "is_first_hit" in AttackWithAttackDamage.__slots__
    assert AttackWithAttackDamage(None, "x", "Power").is_first_hit is True, "defaut = serie entiere"
    src = inspect.getsource(H.HazeOfCorruptionDamageTransferTrigger.execute_behaviour)
    assert "is_first_hit=(i == 0)" in src, "le transfert doit numeroter ses feuilles"


# --------------------------------------------------------------------------- LIVE

@pytest.mark.parametrize("hp,k", [(8000, 1), (6000, 1), (5000, 1), (6000, 0)])
def test_le_port_consomme_autant_de_tirages_que_le_natif(hp, k):
    r = _row(hp, "777", k)
    assert r["n_off"] == r["n_native"], (
        "flux RNG : port %s tirages != natif %s (hp %s, k %s)" % (r["n_off"], r["n_native"], hp, k))


def test_l_echelle_attribue_les_tirages_a_leur_etage():
    """Le compte seul ne prouve rien s'il ne BOUGE pas : trois regimes doivent rendre trois comptes
    DISTINCTS et croissants, chacun expliquant un etage (le coup bonus, puis un transfert de plus)."""
    survie, mort3, mort2 = _row(8000), _row(6000), _row(5000)
    assert survie["n_native"] == survie["n_off"] < mort3["n_native"] == mort3["n_off"]
    assert mort3["n_native"] < mort2["n_native"] == mort2["n_off"]
    # un transfert de plus (PV 5000 : 3 entrees au lieu de 2) = EXACTEMENT un tirage de plus.
    assert mort2["n_native"] - mort3["n_native"] == 1


def test_la_contamination_tombe_sur_la_tuile_de_la_cible_comme_en_live():
    """TEMOIN independant du compte. Seed 88 : le rang du `Maybe` passe sous 25 -> le natif contamine
    la tuile de la CIBLE (le coup bonus tape le cadavre). Le port doit poser la MEME tuile -- avant
    correctif il posait celle du RELAIS, parce qu'il attribuait le `Maybe` a un transfert."""
    r = _row(6000, "88")
    assert r["tgt_tile"] in r["tiles1"] and r["tgt_tile"] not in r["tiles0"], \
        "le natif doit contaminer la tuile de la cible sur ce montage (temoin non concluant)"
    posed = [p["target"] for p in r["off_tiles"]]
    assert posed == [r["tgt_tile"]], \
        "port : Contaminated pose sur %s, natif sur la tuile de la cible %s" % (posed, r["tgt_tile"])
