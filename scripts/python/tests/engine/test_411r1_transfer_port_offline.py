"""#411-r1 -- GARDE DU PORT de `TransferHit` : la route de block GARANTI et son CABLAGE per-coup.

`test_411_transfer_hit_wiring_offline.py` verrouille les DONNEES de RE (ids d'enum, porteurs, voie
de montage) et pose l'invariant « si 1109/1511 entre au REGISTRE, l'intercepteur doit exposer
`should_transfer` ». Ce fichier-ci garde la chose que l'invariant ne peut pas voir : le PORT lui-meme,
qui passe par l'INTERCEPTEUR per-coup et non par `ABILITY_TRIGGERS` (le bus du port emet `On(6)`/`On(7)`
UNE FOIS PAR ATTAQUE, alors que `DrawFire` se declenche PAR COUP -- exactement la raison pour laquelle
#366-r1 a ouvert ce foyer).

CE QUI EST GARDE, et pourquoi c'est la bonne chose --

  La propriete portee est une propriete de CONSOMMATION, pas de valeur : un coup transfere prend la
  route `IdunBattle.Core.Services.DamageCalculations$$ApplyBlockDamage` (slot 4, arithmetique pur)
  au lieu du couple `ApplyRandomEvasion` (slot 3) + `ApplyRandomBlockDamage` (slot 2). Il consomme
  donc **zero tirage** la ou le chemin ordinaire en consomme un par source de block. Un port qui
  roulerait quand meme desynchroniserait tout le flux RNG de l'attaque A PARTIR DE CE COUP -- sans
  erreur, sans crash : une divergence de valeurs, invisible en self-play.

  Les tests comptent donc les TIRAGES (`call_count` du MT), pas seulement les degats.

Confrontation live du meme port : `probe_411r1_transfer_port.py` (montage de greffe, bras temoin,
ledger de tirages). RE : `docs/rl/case-411-transfer-hit-guaranteed-block.md`.

ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.damage_hits import HitDamage
from engine.services.damage_combat import BlockSource, calculate_damage_operation


# --------------------------------------------------------------- la route elle-meme (slot 4)

def test_route_garantie_ne_consomme_aucun_tirage():
    """`damageInfo[+0x1D] != 0` -> `ApplyBlockDamage(blockChances, currentDamage)`, PAS
    `ApplyRandomBlockDamage`. Le compteur du MT ne doit pas bouger d'un cran."""
    rng = IntBasedMersenneTwister(777)
    n0 = rng.call_count
    d = calculate_damage_operation(1000, block_sources=[BlockSource(chance=50, amount=300,
                                                                    block_id=7)],
                                   guaranteed_block=True, rng=rng)
    assert rng.call_count == n0, "un coup transfere a consomme %d tirage(s)" % (rng.call_count - n0)
    assert d.did_block is True                     # pose EN DUR par le natif
    assert d.health == 700                         # max(0, 1000 - blockChances[0].amount)
    assert not d.failed_block_ids                  # aucune source n'a « echoue » : rien n'a ete tente


def test_route_garantie_prend_la_PREMIERE_source_sans_regarder_sa_chance():
    """Le natif indexe `blockChances[0]` -- il ne filtre NI sur `chance` NI sur `amount`.
    Une source a chance nulle bloque donc quand meme sur un coup transfere."""
    rng = IntBasedMersenneTwister(777)
    d = calculate_damage_operation(1000, block_sources=[BlockSource(chance=0, amount=250,
                                                                    block_id=1),
                                                        BlockSource(chance=99, amount=900,
                                                                    block_id=2)],
                                   guaranteed_block=True, rng=rng)
    assert d.health == 750 and d.did_block is True
    assert rng.call_count == 0


def test_route_garantie_sans_source_laisse_le_degat_et_bloque_quand_meme():
    """`blockChances == null || Count == 0` -> `currentDamage` inchange, mais `didBlock = 1` reste
    pose en dur (c'est ce qui fait compter le coup dans `RegisterBlockMade`)."""
    for sources in (None, []):
        rng = IntBasedMersenneTwister(777)
        d = calculate_damage_operation(1000, block_sources=sources, guaranteed_block=True, rng=rng)
        assert d.health == 1000 and d.did_block is True and rng.call_count == 0


def test_route_garantie_clampe_a_zero():
    """`Math.Max(0, d)` -- une source qui bloque plus que le degat ne rend pas du negatif."""
    d = calculate_damage_operation(100, block_sources=[BlockSource(chance=50, amount=5000)],
                                   guaranteed_block=True, rng=IntBasedMersenneTwister(1))
    assert d.health == 0 and d.did_block is True


def test_route_garantie_prime_sur_la_branche_evasion():
    """Le natif teste `+0x1D` AVANT de choisir evasion/block : `guaranteed_block` doit donc
    l'emporter sur `evasion_branch`, et surtout ne tirer aucune evasion."""
    rng = IntBasedMersenneTwister(777)
    d = calculate_damage_operation(1000, evasion_chance=100, evasion_branch=True,
                                   block_sources=[BlockSource(chance=50, amount=400)],
                                   guaranteed_block=True, rng=rng)
    assert d.did_evade is False and d.did_block is True and d.health == 600
    assert rng.call_count == 0


def test_la_route_ordinaire_est_INCHANGEE():
    """Contre-epreuve : sans le flag, la meme entree DOIT reprendre la chaine aleatoire (et donc
    consommer). Sans ce test, un `guaranteed_block` colle a `True` par megarde passerait tous les
    autres."""
    rng = IntBasedMersenneTwister(777)
    calculate_damage_operation(1000, block_sources=[BlockSource(chance=50, amount=300,
                                                                block_id=7)],
                               guaranteed_block=False, rng=rng)
    assert rng.call_count > 0, "la route ORDINAIRE ne tire plus rien -- le flag fuit"


# ------------------------------------------------------- le CABLAGE per-coup dans `_run_hits`

class _FakeInterceptor:
    """Le contrat minimal que `_run_hits` attend d'un intercepteur, plus un journal.

    `transfer_at` = les index de coup que `should_transfer` accepte. On ne monte PAS de `State` :
    ce qu'on teste ici est le CABLAGE (quelle branche, dans quel ordre, pour quel cout en tirages),
    pas la detection du porteur -- celle-la est confrontee live par `probe_411r1_transfer_port.py`."""

    def __init__(self, transfer_at=(), discard_at=()):
        self.transfer_at = set(transfer_at)
        self.discard_at = set(discard_at)
        self.calls: list = []

    def should_transfer(self, hit_index: int) -> bool:
        hit = int(hit_index) in self.transfer_at
        self.calls.append(("transfer", int(hit_index), hit))
        return hit

    def should_discard(self, hit_index: int) -> bool:
        hit = int(hit_index) in self.discard_at
        self.calls.append(("discard", int(hit_index), hit))
        return hit

    def on_blocked(self, hit_index: int) -> None:
        self.calls.append(("blocked", int(hit_index), True))


def _run(hits: int, icept, block_sources=None, seed: int = 777) -> tuple:
    rng = IntBasedMersenneTwister(seed)
    n0 = rng.call_count
    r = AttackDamageOperation._run_hits(rng, HitDamage(100, 200), HitDamage(100, 200), 0, False,
                                        hits, block_sources, hit_interceptor=icept)
    return r, rng.call_count - n0


def test_les_coups_transferes_sortent_a_zero_et_bloquent():
    """La ventilation per-coup : les index demandes valent 0 et comptent comme blocs."""
    icept = _FakeInterceptor(transfer_at=(1, 3, 5))
    r, _ = _run(6, icept)
    assert [i for i, v in enumerate(r["per_hit"]) if v == 0] == [1, 3, 5]
    assert all(r["per_hit"][i] > 0 for i in (0, 2, 4))
    assert r["did_block"] is True
    assert len(r["crits"]) == 6, "un coup transfere reste COMPTE (l'index avance)"


def test_un_coup_transfere_consomme_son_resolve_mais_AUCUN_block():
    """LE test de consommation. Six coups, trois transferes, une source de block :
      * chemin ordinaire -> 1 resolve + 1 tirage de block par coup ;
      * coup transfere   -> 1 resolve (cellule [0,0], `RandomlyResolveMinMaxDamage` n'a aucun
        gate de largeur -- meme raison que case-221) et RIEN d'autre.
    On compare au MEME montage sans transfert : l'ecart doit valoir exactement les tirages de
    block des trois coups transferes, jamais leur resolve.

    ⚠ La source est a `chance=100` A DESSEIN. A chance partielle, la failed-list de #407 rend le
    compte NON LINEAIRE (une source qui echoue une fois est exclue des coups suivants, donc le
    nombre de tirages depend des resultats) et l'ecart ne serait plus interpretable. A 100 %,
    chaque coup NON transfere tire exactement une fois et reussit -- l'ecart devient une soustraction
    propre."""
    src = [BlockSource(chance=100, amount=10, block_id=1)]
    _, draws_plain = _run(6, _FakeInterceptor(), src)
    _, draws_xfer = _run(6, _FakeInterceptor(transfer_at=(1, 3, 5)), src)
    _, draws_noblock = _run(6, _FakeInterceptor(), None)
    per_resolve = draws_noblock // 6                    # cout d'UN resolve, mesure
    per_block = (draws_plain - draws_noblock) // 6      # cout d'UN tirage de block, mesure
    assert per_resolve > 0 and per_block > 0, (draws_noblock, draws_plain)
    # 6 resolve (les transferes en consomment un AUSSI) + 3 tirages de block seulement.
    attendu = 6 * per_resolve + 3 * per_block
    si_les_transferes_roulaient = 6 * per_resolve + 6 * per_block
    assert draws_xfer == attendu, (
        "coups transferes : %d tirages, attendu %d ; on lirait %d s'ils roulaient leur block"
        % (draws_xfer, attendu, si_les_transferes_roulaient))
    assert attendu != si_les_transferes_roulaient, "regime NON discriminant"


def test_le_transfert_est_teste_AVANT_le_discard():
    """COLLISION `discard` x `transfer` sur un MEME coup : `On(6)` pose `discard = 1` dans le
    Nullable, `On(7)` EFFACE le Nullable, et la relecture teste `HasValue` d'abord -- elle voit
    donc `!HasValue`. Le TRANSFERT gagne. Un coup discard sort sur un `OperationResult` memset a
    0 (aucune entree dans `per_hit`), un coup transfere y laisse un 0 : les deux sont
    distinguables."""
    icept = _FakeInterceptor(transfer_at=(1,), discard_at=(1,))
    r, _ = _run(2, icept)
    assert len(r["per_hit"]) == 2 and r["per_hit"][1] == 0, r["per_hit"]
    assert ("discard", 1, True) not in icept.calls, "le discard a gagne la collision"
    assert ("transfer", 1, True) in icept.calls


def test_sans_transfert_le_chemin_est_STRICTEMENT_inchange():
    """Retro-compatibilite : un intercepteur qui ne transfere jamais doit rendre exactement ce
    que rendait le port d'avant -- memes degats, MEME nombre de tirages."""
    src = [BlockSource(chance=50, amount=10, block_id=1)]
    r1, d1 = _run(6, _FakeInterceptor(), src)
    r2, d2 = _run(6, None, src)
    assert r1["per_hit"] == r2["per_hit"] and d1 == d2
    assert all(v > 0 for v in r1["per_hit"])


def test_un_coup_transfere_eteint_le_crit_du_reste_de_lattaque():
    """`crit_allowed` = `OngoingHitGroup+0x3c`. Le coup transfere rejoint le meme label que le
    chemin « n'a PAS crite » -> l'extinction a lieu, comme pour un coup non-crite ordinaire.

    ⚠ C'est bien l'extinction qui compte, PAS le `msg[+0x29] = 1` que pose la meme branche : la
    struct d'options est passee PAR VALEUR (`ExecuteHits` la recharge avant chaque coup) et
    l'ecriture arrive APRES le gate crit. Cf. la fiche §6.3, qui refute l'affirmation inverse."""
    r, _ = _run(2, _FakeInterceptor(transfer_at=(1,)))
    assert r["crit_allowed"] is False


# ------------------------------------------------------------------ le porteur et ses gates

def test_le_gate_de_parite_est_evalue_AVANT_toute_recherche_de_porteur():
    """`AmountIsOdd(CurrentHitIndex)` (0-based). Sur un index PAIR, `DrawFireTransfer.transfer`
    doit sortir SANS toucher au `State` -- c'est ce qui rend l'anti-recursion gratuite : la
    sous-attaque repart a l'index 0, donc elle ne peut pas retransferer."""
    from engine.runner.operations.triggers.loki.draw_fire import DrawFireTransfer
    t = DrawFireTransfer(None, 1, 2)               # `state=None` : toute lecture leverait
    assert t.transfer(0) is False
    assert t.transfer(2) is False
    assert t.transfer(4) is False
    assert t.events == []


def test_sans_state_un_index_impair_ne_leve_pas_et_ne_transfere_pas():
    """`find_transfer_carrier` rend `None` sur un montage incomplet : pas de transfert, pas
    d'exception -- la degradation est SILENCIEUSE cote effet, JAMAIS cote erreur."""
    from engine.runner.operations.triggers.loki.draw_fire import (DrawFireTransfer,
                                                                  find_transfer_carrier)
    assert find_transfer_carrier(None, 1, 2) is None
    assert DrawFireTransfer(None, None, None).transfer(1) is False


def test_lintercepteur_expose_bien_la_route():
    """Le contrat que `test_411_transfer_hit_wiring_offline.py` exige du jour ou 1109/1511 entre
    au registre -- et que le port satisfait DES MAINTENANT, par la voie intercepteur."""
    from engine.runner.operations.triggers.loki.harlequins_panoply import (
        HarlequinsPanoplyHitInterceptor)
    assert hasattr(HarlequinsPanoplyHitInterceptor, "should_transfer")


def test_le_levier_skip_hit_count_query_existe_et_est_no_op_par_defaut():
    """`AttackDamageOptions[+0x28]` porte comme parametre de `AttackDamageOperation.execute`.
    Defaut `False` = strictement no-op : aucun chemin existant ne change."""
    import inspect
    sig = inspect.signature(AttackDamageOperation.execute)
    p = sig.parameters.get("skip_hit_count_query")
    assert p is not None and p.default is False


@pytest.mark.parametrize("ability_id,expected", [(1109, "DrawFire"),
                                                 (1511, "PrimarchOfTheFirstLegion")])
def test_les_deux_ids_restent_ceux_de_la_RE(ability_id, expected):
    """Rappel local des deux seuls proprietaires de `DSLBehaviors$$TransferHit`. `1511` n'est
    PAS porte (son `transferTarget` passe par un `Randomize` qui consomme du RNG et dont l'ordre
    du pool n'est pas lu) : ce test garde l'id, pas un port."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert int(getattr(TriggeredAbilityType, expected)) == ability_id
