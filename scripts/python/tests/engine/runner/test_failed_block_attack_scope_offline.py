"""#407 -- la failed-block list a la portee de l'ATTAQUE, pas de la SERIE de coups.

CE QUE MESURE CE FICHIER (offline, deterministe, aucune session Frida) : le CABLAGE de
`OngoingAttack+0x48` (`FailedBlockIds`), sur les deux etages ou le port pouvait le perdre.

RE (decompile `rnca9r7q6c`, lu, pas suppose) :
  * `IdunBattle.Core.OngoingAttack$$.ctor` cree `+0x48 = new List<int>()` -- NEUVE par attaque,
    exactement comme `+0x40 = 1` (`isCriticalDamageAllowed`) ;
  * `IdunBattle.Operations.ADamageOperation$$GetFailedBlockIds` la rend
    (`HasCurrentAttack() ? GetCurrentAttack().FailedBlockIds : new List<int>()`) ;
  * `IdunBattle.Operations.ADamageOperation$$SetupHitGroup` la seme PAR REFERENCE dans
    `OngoingHitGroup+0x60` ;
  * `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` la passe a chaque coup
    (`options[+0x30] = hitGroup[+0x60]`) et `ADamageOperation$$RegisterBlocks` y AddRange les ids
    echoues (`hitGroup[+0x60].AddRange(result[+0x28])`) ;
  * `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` EXCLUT les sources dont
    l'id y figure (`Contains(failedBlockIds, id)` -> `continue`) -> **0 tirage** pour elles.

Comme `AttackDamageOperation$$Execute` ne construit qu'UN `OngoingHitGroup` (partage par la phase
d'arme, les coups bonus et `ExecuteAdditionalHitsWithoutDamageProfileType`) et que la voie A PROFIL
re-lit la MEME liste de l'`OngoingAttack`, l'exclusion traverse TOUTE l'attaque.

⚠ POLARITE -- ce n'est PAS le gate crit (#440). Le crit a un booleen d'attaque qui TOMBE au premier
coup non-crite (`attack[+0x40] &= hitGroup[+0x3c]`) ; le block n'a AUCUN booleen equivalent, et
l'extinction y est PAR SOURCE et seulement sur ECHEC (une source qui REUSSIT sort de
`ApplyRandomBlockDamage` en `return`, sans `AddFailedBlockId` : elle reste jouable).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]          # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.runner.operations.damage import AttackDamageOperation      # noqa: E402
from engine.runner.operations.damage_hits import HitDamage             # noqa: E402
from engine.services.damage_combat import BlockSource                  # noqa: E402


class _CountingRng:
    """RNG deterministe qui COMPTE les `next_bool` (= les tirages de block d'
    `ApplyRandomBlockDamage`). `next_internal` rend la borne basse : la valeur du coup n'est pas
    la variable ici, la CONSOMMATION l'est."""

    def __init__(self, bool_result: bool = False):
        self.bools = 0
        self._res = bool_result

    def next_internal(self, lo, hi):
        return lo

    def next_bool(self, chance):
        self.bools += 1
        return self._res


_SRC = BlockSource(chance=50, amount=7, block_id=1234)


def _run(failed_block0, hits=1, bool_result=False):
    rng = _CountingRng(bool_result)
    r = AttackDamageOperation._run_hits(
        rng, HitDamage(100, 100), HitDamage(100, 100), 0, False, hits, [_SRC],
        failed_block0=failed_block0)
    return rng.bools, r


def test_une_source_deja_echouee_ne_consomme_AUCUN_tirage():
    """`CalculateBlockChances` la saute (`Contains` -> `continue`) : la liste des chances est vide,
    donc `ApplyRandomBlockDamage` ne roule rien. C'est L'OBSERVABLE qui tranche -- un roll SAUTE ne
    consomme pas de tirage."""
    rolls, r = _run({1234}, hits=3)
    assert rolls == 0, "source exclue : le port a quand meme roule %d fois" % rolls
    assert r["failed_block"] == {1234}, r["failed_block"]


def test_contre_epreuve_sans_l_etat_la_source_roule_a_chaque_coup():
    """CONTRE-EPREUVE du test precedent : sans `failed_block0`, la source est tentee au coup 1,
    ECHOUE, entre dans la liste, et n'est plus tentee ensuite -> 1 seul tirage sur 3 coups. C'est le
    comportement INTRA-serie deja porte (#72) ; ce que #407 ajoute, c'est qu'il SURVIT a la serie."""
    rolls, r = _run(None, hits=3)
    assert rolls == 1, "attendu 1 tirage (echec au coup 1 puis exclusion), vu %d" % rolls
    assert r["failed_block"] == {1234}, r["failed_block"]


def test_une_source_qui_REUSSIT_reste_jouable():
    """POLARITE INVERSE du gate crit : `ApplyRandomBlockDamage` sort en `return` au 1er succes,
    AVANT `BlockDamageInfo$$AddFailedBlockId` -> la source n'entre pas dans la liste et est
    re-tentee au coup suivant (1 tirage par coup)."""
    rolls, r = _run(None, hits=3, bool_result=True)
    assert rolls == 3, "une source qui reussit doit rester jouable : %d tirages sur 3 coups" % rolls
    assert r["failed_block"] == set(), r["failed_block"]


def test_l_etat_sort_de_la_serie_et_y_rentre():
    """Le contrat de threading : ce que `_run_hits` REND est ce qu'il ACCEPTE. Sans lui, l'appelant
    (`execute_additional_hits`) ne pourrait pas propager `OngoingAttack+0x48` d'une sous-operation a
    la suivante."""
    _, r1 = _run(None, hits=1)
    rolls2, r2 = _run(r1["failed_block"], hits=2)
    assert rolls2 == 0, "l'etat de sortie n'a pas ferme la source : %d tirages" % rolls2
    assert r2["failed_block"] == r1["failed_block"]


def test_execute_additional_hits_CHAINE_l_etat_de_groupe_en_groupe():
    """Etage 2 : `execute_additional_hits` doit ACCEPTER `failed_block0`, le passer a `_run_hits`,
    RE-INJECTER la sortie dans le groupe suivant, et le RENDRE. Sans ce chainage, une source
    exclue par la phase d'arme etait re-tiree a CHAQUE groupe (tirages en trop)."""
    from engine.runner.operations import additional_hits as AH

    seen = []

    def _rh(rng, hit_nc, hit_cr, *a, **kw):
        seen.append(set(kw.get("failed_block0") or ()))
        out = set(kw.get("failed_block0") or ())
        out.add(100 + len(seen))          # chaque groupe ajoute SON id d'echec
        return {"total": 0, "per_hit": [], "per_hit_health": [], "rolls": [], "crits": [],
                "shield_dmg": 0, "armor_dmg": 0, "did_crit": False, "did_block": False,
                "did_evade": False, "next_hit_index": 0, "crit_allowed": True,
                "failed_block": out}

    class _Thc:
        hp = 1000

    class _State:
        """`State` minimal : `execute_additional_hits` n'y touche que par `unit_prevents_overkill`
        (qui lit une entite) et par `state.rng`."""
        rng = _CountingRng()

        @staticmethod
        def get_entity(_uid):
            return None

    import gameconfig as GC
    orig_rh, orig_dp = AttackDamageOperation._run_hits, GC.damage_profile
    orig = {k: getattr(AttackDamageOperation, k)
            for k in ("_apply_max_out", "_target_limits", "_deplete_shield",
                      "_apply_damage_pipeline")}
    GC.damage_profile = lambda _p: {}
    AttackDamageOperation._run_hits = staticmethod(_rh)
    AttackDamageOperation._apply_max_out = staticmethod(lambda st, aid, nc, cr: (nc, cr))
    AttackDamageOperation._target_limits = staticmethod(lambda *a, **k: None)
    AttackDamageOperation._deplete_shield = staticmethod(lambda *a, **k: None)
    AttackDamageOperation._apply_damage_pipeline = staticmethod(lambda *a, **k: False)
    try:
        out = AH.execute_additional_hits(
            _State(), 1, 2, object(), _Thc(),
            [{"profile": "Physical", "count": 1, "min": 10, "max": 10},
             {"profile": "Physical", "count": 1, "min": 10, "max": 10}],
            None, None, 0, 100, None, None, failed_block0={9})
    finally:
        GC.damage_profile = orig_dp
        AttackDamageOperation._run_hits = staticmethod(orig_rh)
        for k, v in orig.items():
            setattr(AttackDamageOperation, k, staticmethod(v))

    assert seen[0] == {9}, "le groupe 1 n'a pas recu l'etat d'entree : %s" % (seen[0],)
    assert seen[1] == {9, 101}, "le groupe 2 n'a pas recu la sortie du groupe 1 : %s" % (seen[1],)
    assert out["failed_block"] == {9, 101, 102}, out["failed_block"]


if __name__ == "__main__":                    # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
