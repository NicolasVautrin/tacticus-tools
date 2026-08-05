"""#462-r4e-o-r1-r1 -- GARDE de la CARDINALITE des events pour un coup DISCARDE.

QUESTION BINAIRE : un coup jete par l'etape 5 d'`IdunBattle.Operations.AttackDamageOperation$$
ExecuteHit` (`if (attackHit.discard != 0) return this;`) emet-il quand meme un evenement
`UnitDamaged` a `Amount` 0 ?

REPONSE LUE (build `rnca9r7q6c`), et c'est une chaine de trois maillons, pas une deduction :

  1. `ExecuteHit` relit `OngoingAttack+0x98` juste apres `On(6)`/`On(7)` et, si le flag `discard`
     du `Nullable<AttackHit>` est pose, fait `return this` sur un `OperationResult` MEMSET A 0 ;
  2. ce `return` PRECEDE la sub-op **0x42** = `IdunBattle.Operations.DealDamageOperation$$Execute`,
     seule sous-operation invoquee par la queue d'`ExecuteHit` ;
  3. `DealDamageOperation$$Execute` invoque le slot **0x43** = `IdunBattle.Core.Services.
     OperationProcessor$$ApplyDamage`, UNIQUE appelant de code d'`IdunBattle.Operations.
     ApplyDamageOperation$$Execute` -- le corps qui emet `UnitDamaged` et son tag `Amount`
     (`IdunBattle.Core.Services.StreamHelper$$GetDamageTags`, TagKey 225).

=> un coup discarde n'emet RIEN. Le port en appendait une entree a 0 : ecart de RAPPORT pur (meme
etat, meme somme), invisible de tout test d'ETAT -- meme signature que #462-r4e-o-r1, autre porte.

CE QUI EST GARDE ICI, et le PIEGE qu'il evite --

  L'assertion naive « tous les coups suivants valent 0 » (`all(h == 0 for h in per_hit[1:])`) est
  VACUEUSEMENT VRAIE des que `per_hit` n'a plus qu'une entree : elle passe AVANT comme APRES le
  correctif. Ce fichier assertionne donc la CARDINALITE (`len(per_hit)`) et sa separation d'avec
  le compte de coups EXECUTES (`hits_executed`, `len(crits)`, `len(rolls)`), qui eux restent
  full-length.

  La CONTRE-EPREUVE substitue le foyer `discarded_hit_emits` (fonction de MODULE, exactement pour
  ca) : le port d'avant revient, et les assertions de cardinalite DOIVENT rougir.

  Le TRANSFERT (#411) est le contre-modele qui interdit de rabattre les deux sur « un coup a 0
  disparait » : il relit le MEME champ au MEME instant (sur `!HasValue`), le natif NE sort PAS, la
  sub-op 0x42 tourne avec `damage = 0` -> l'event EXISTE. Les deux portes sont testees cote a cote.

Confrontation LIVE du meme port : `probe_462_r4e_o_r1_r1_discard_amount.py` (greffe
`HarlequinsPanoply`, events `Amount` du live vs `per_hit` offline).
RE : `docs/rl/case-462-r4e-o-amount-borne-aux-pv.md` section 6.

ASCII only.
"""
from __future__ import annotations

from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.operations import damage_hits as DH
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.damage_hits import HitDamage
from engine.services.damage_combat import BlockSource


class _FakeInterceptor:
    """Contrat minimal attendu par `_run_hits` (meme forme que celui de
    `test_411r1_transfer_port_offline.py`) : on teste le CABLAGE, pas la detection du porteur --
    celle-la est confrontee live par le probe."""

    def __init__(self, discard_at=(), transfer_at=()):
        self.discard_at = set(discard_at)
        self.transfer_at = set(transfer_at)
        self.calls: list = []

    def should_discard(self, hit_index: int) -> bool:
        hit = int(hit_index) in self.discard_at
        self.calls.append(("discard", int(hit_index), hit))
        return hit

    def should_transfer(self, hit_index: int) -> bool:
        hit = int(hit_index) in self.transfer_at
        self.calls.append(("transfer", int(hit_index), hit))
        return hit

    def on_blocked(self, hit_index: int) -> None:
        self.calls.append(("blocked", int(hit_index), True))


def _run(hits: int, icept, block_sources=None, seed: int = 777) -> tuple:
    rng = IntBasedMersenneTwister(seed)
    n0 = rng.call_count
    r = AttackDamageOperation._run_hits(rng, HitDamage(100, 200), HitDamage(100, 200), 0, False,
                                        hits, block_sources, hit_interceptor=icept)
    return r, rng.call_count - n0


# ------------------------------------------------------- 1. le natif : AUCUN event pour un discard

def test_un_coup_discarde_n_emet_AUCUN_event():
    """Le cas du passif : le coup 0 porte, les cinq suivants sont jetes. `per_hit` = les events
    EMIS -> UNE seule entree, pas six."""
    r, _ = _run(6, _FakeInterceptor(discard_at=(1, 2, 3, 4, 5)))
    assert len(r["per_hit"]) == 1, (
        "un coup discarde a laisse une entree dans per_hit : %s" % (r["per_hit"],))
    assert r["per_hit"][0] > 0, r["per_hit"]
    assert r["hits_executed"] == 6, (
        "le coup discarde reste EXECUTE (l'index avance) : %s" % (r["hits_executed"],))


def test_les_compteurs_de_COUPS_restent_full_length():
    """La separation qui donne son sens au correctif : `per_hit` compte les EVENTS,
    `crits`/`rolls`/`per_hit_health`/`hits_executed` comptent les COUPS. Un port qui aurait
    tronque la liste apres coup (la rustine explicitement refusee par la tranche precedente)
    ferait tomber ces quatre-la avec."""
    r, _ = _run(6, _FakeInterceptor(discard_at=(1, 2, 3, 4, 5)))
    assert len(r["crits"]) == 6, r["crits"]
    assert len(r["rolls"]) == 6, r["rolls"]
    assert len(r["per_hit_health"]) == 6, r["per_hit_health"]
    assert r["hits_executed"] == 6
    assert r["per_hit_health"][1:] == [0] * 5, r["per_hit_health"]


def test_la_position_des_discards_ne_change_pas_la_regle():
    """Le regime ou la coupure n'est PAS un suffixe : seuls les index 1 et 4 sont jetes. `per_hit`
    doit valoir 4 entrees, toutes > 0 -- une troncature en queue rendrait 5 ou 6."""
    r, _ = _run(6, _FakeInterceptor(discard_at=(1, 4)))
    assert len(r["per_hit"]) == 4, r["per_hit"]
    assert all(v > 0 for v in r["per_hit"]), r["per_hit"]
    assert r["hits_executed"] == 6


# ------------------------------------------------------- 2. le CONTRE-MODELE : le transfert (#411)

def test_un_coup_TRANSFERE_emet_bien_son_event_a_zero():
    """La porte JUMELLE, au MEME point d'`ExecuteHit`, mais sur `!HasValue` : le natif NE SORT PAS,
    la sub-op 0x42 tourne avec `damage = 0` -> `ApplyDamage` -> l'event EXISTE, a `Amount` 0.
    Sans ce test, « supprimer les entrees a 0 » passerait pour une regle generale : elle est FAUSSE.
    """
    r, _ = _run(6, _FakeInterceptor(transfer_at=(1, 3, 5)))
    assert len(r["per_hit"]) == 6, r["per_hit"]
    assert [i for i, v in enumerate(r["per_hit"]) if v == 0] == [1, 3, 5], r["per_hit"]


def test_discard_et_transfert_dans_la_MEME_serie():
    """Regime mixte : coup 1 transfere (event a 0), coups 2-3 discardes (aucun event). 6 coups
    executes, 4 events -- dont exactement UN a 0."""
    r, _ = _run(6, _FakeInterceptor(transfer_at=(1,), discard_at=(2, 3)))
    assert r["hits_executed"] == 6
    assert len(r["per_hit"]) == 4, r["per_hit"]
    assert r["per_hit"].count(0) == 1, r["per_hit"]


# ------------------------------------------------------- 3. non-regression : sans discard, RIEN ne bouge

def test_sans_discard_le_chemin_est_STRICTEMENT_inchange():
    """Un intercepteur qui ne jette jamais doit rendre exactement ce que rendait le port d'avant --
    memes valeurs, MEME nombre de tirages, meme cardinalite."""
    src = [BlockSource(chance=50, amount=10, block_id=1)]
    r1, d1 = _run(6, _FakeInterceptor(), src)
    r2, d2 = _run(6, None, src)
    assert r1["per_hit"] == r2["per_hit"] and d1 == d2
    assert len(r1["per_hit"]) == 6 and all(v > 0 for v in r1["per_hit"])


def test_un_coup_discarde_ne_consomme_pas_les_tirages_de_l_aval():
    """Garde de CONSOMMATION (le correctif ne doit pas la deplacer) : le discard sort AVANT le
    slot 4/8 et la sub-op 0x42, donc un coup jete ne roule ni son resolve ni ses blocks. L'ecart
    avec le bras temoin vaut exactement les tirages des cinq coups jetes."""
    src = [BlockSource(chance=100, amount=10, block_id=1)]
    _, d_plain = _run(6, _FakeInterceptor(), src)
    _, d_disc = _run(6, _FakeInterceptor(discard_at=(1, 2, 3, 4, 5)), src)
    assert d_disc < d_plain, (d_disc, d_plain)
    assert d_disc == d_plain // 6, (
        "un coup discarde a consomme des tirages d'aval : %d pour 1 coup porte, temoin %d"
        % (d_disc, d_plain))


# ------------------------------------------------------- 4. CONTRE-EPREUVE : le foyer, mute

def test_contre_epreuve_le_foyer_mute_restaure_le_port_d_avant():
    """VERT est le resultat SUSPECT sur une contre-epreuve : on verifie d'abord que la mutation a
    MORDU (le foyer rend bien True), puis que la cardinalite REGRESSE a l'identique du port
    d'avant #462-r4e-o-r1-r1 -- six entrees dont cinq a 0, meme somme, meme etat.

    Le foyer substitue est `discarded_hit_emits` DU MODULE (`_run_hits` le resout par nom au
    moment de l'appel) : si un jour quelqu'un l'inline, ce test rougit -- et c'est voulu."""
    ref, _ = _run(6, _FakeInterceptor(discard_at=(1, 2, 3, 4, 5)))
    assert len(ref["per_hit"]) == 1                       # etat de reference (correctif en place)

    original = DH.discarded_hit_emits
    try:
        DH.discarded_hit_emits = lambda: True
        assert DH.discarded_hit_emits() is True, "la mutation n'a pas mordu"
        mut, _ = _run(6, _FakeInterceptor(discard_at=(1, 2, 3, 4, 5)))
    finally:
        DH.discarded_hit_emits = original
    assert DH.discarded_hit_emits() is False, "le foyer n'a pas ete restaure"

    assert len(mut["per_hit"]) == 6, (
        "la mutation n'a pas produit l'ancien ecart : %s" % (mut["per_hit"],))
    assert mut["per_hit"][1:] == [0] * 5, mut["per_hit"]
    # C'est CA qui rendait l'ecart invisible : meme somme, meme total, meme etat.
    assert sum(mut["per_hit"]) == sum(ref["per_hit"])
    assert mut["total"] == ref["total"]
    assert mut["hits_executed"] == ref["hits_executed"] == 6
