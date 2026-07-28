"""R6-b' -- le `Maybe` after-hit d'un trigger `On(8)` est evalue SUR LES COUPS D'UN GROUPE de
coups additionnels (#179/#202-B), avec l'index de coup CONTINU de l'ATTAQUE. Garde LIVE
discriminante sur CET etage seul (l'ordre tirage/reduction est verrouille par
`test_additional_hits_roll_order_live`, la materialisation par
`test_additional_hits_rounding_live`).

RE (decompile = verite, gqfc5mff6c) -- chaine LUE de l'index au tirage :

  * `IdunBattle.Core.OngoingAttack$$.ctor` met `+0x30` (index de coup) et `+0x34` (compteur de
    series) a 0. L'objet est POUSSE **une seule fois par attaque** sur la pile `MatchState+0x60`
    (`IdunBattle.Core.MatchState$$StartAttack`, appelee par
    `IdunBattle.Operations.StartAttackOperation$$Execute`) et depile par
    `IdunBattle.Core.MatchState$$FinishAttack` ;
  * toute sous-operation le RECUPERE par `Peek` : `IdunBattle.Operations.ADamageOperation$$
    GetCurrentAttackOrDefault` -> `IdunBattle.Core.Services.BattleQuery$$GetCurrentAttackOrDefault`
    -> `IdunBattle.Core.MatchState$$GetCurrentAttack` ;
  * `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` relit `currentAttack+0x30` FRAIS a
    chaque tour de boucle et le passe a `ExecuteHit` ;
    `IdunBattle.Operations.ADamageOperation$$UpdateCurrentAttackAfterHit` fait `+0x30 += 1` apres
    CHAQUE coup (`+0x34 += 1` seulement en fin de serie) ;
  * DERNIERE instruction d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (appel
    INCONDITIONNEL, xref) : `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`,
    qui construit `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` avec cet index en
    `Nullable<int>` au champ **+0x110** puis dispatche l'event **`On(8)`** ;
    `IdunBattle.Entities.Formulas.CurrentHitIndexFormula$$Calculate` lit exactement `+0x110` ;
  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger` =
    `On(8) & AmountIsOdd(CurrentHitIndex()) & OwnerIsCaster & !(MinDistance > Direct(2))` ;
    `...GetStuckInAbility$$CreateBehaviour` = `Maybe(AddBonusHitsToCurrentHitGroup(...),
    GetBonusHitChance())` -> 1 `NextBool(chance)`
    (`IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute`) a chaque passage du trigger ;
  * la voie GROUPES (`IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$
    Execute` -> slot 0x3c `Core.Services.OperationProcessor$$AttackDamage` ->
    `IdunBattle.Operations.AttackDamageOperation$$Execute` -> `ExecuteHits`) partage donc le MEME
    `OngoingAttack` : l'index n'y repart PAS de 0.

DEUX MONTAGES A PARITE INVERSEE -- c'est ce qui refute un « +1 tirage » fitte. Le `Maybe` de la
phase d'ARME (coup d'index 1) SPAWNE un coup bonus quand il REUSSIT, ce qui DECALE la parite de
l'index a l'entree du groupe :

  * `orksRuntherd` (GetStuckIn + passif SquigHound, **3** coups d'arme) vs `ultraApothecary` :
    echec du Maybe d'arme -> groupe aux index 3,4 (3 IMPAIR -> 1 tirage ENTRE les deux coups) ;
    succes -> coup bonus (index 3) puis groupe aux index 4,5 (4 PAIR -> AUCUN tirage entre eux) ;
  * MEME porteur vs `templSwordBrother` (trait `Parry` = -1 coup en melee, donc **2** coups
    d'arme) : la conclusion est INVERSEE (echec -> pas de tirage entre les coups du groupe ;
    succes -> un tirage).

Un modele « toujours +1 tirage avant le 2e coup du groupe » passe le premier montage et tombe sur
le second ; le modele qui ne roule RIEN dans les groupes (le port d'avant R6-b') tombe sur les
deux. Le troisieme test est le TEMOIN sans trigger after-hit (`admecRuststalker`), qui doit rester
bit-exact -- il prouve qu'on n'a pas ajoute un tirage PARTOUT.

MONTAGE : regime PERCAGE-DOMINANT (`--armor-target 6000`, fixture `_pierce_floor_regime`), crit et
block neutralises. Le flux live porte APRES le groupe l'attaque du grot spawne par `SquigHound`
(~500 de degat, sans commune mesure avec les ~35 du groupe) : on ancre sur les coups d'ARME
(bit-exacts) et on confronte le groupe evenement par evenement.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _pierce_floor_regime import (drive, replay_orders, _ok,         # noqa: E402
                                  pierce_dominant_regime)            # noqa: F401 (fixture)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
from probe_r6_round_materialize import additional_hits_variant       # noqa: E402
from probe_r6bp_after_hit_maybe_groups import live_hits_of_attacker  # noqa: E402

CARRIER = "orksRuntherd"           # GetStuckIn (Maybe after-hit) + SquigHound (2 coups Physical p1)
TARGET = "ultraApothecary"         # ni BigTarget ni Vehicle -> BeastSlayer inerte ; 3 coups d'arme
PARRY_TARGET = "templSwordBrother"  # trait `Parry` -> -1 coup en melee : 2 coups d'arme (parite INV.)

# Seeds MESUREES discriminantes (`probe_r6bp_after_hit_maybe_groups.py`, 2026-07-28) : le
# contrefactuel « pas de Maybe dans les groupes » y donne un groupe DIFFERENT du port livre.
SQUIG_SEEDS = ["777", "314159", "20202", "4242"]
PARRY_SEEDS = ["777", "12345", "31337"]


def _measure(rpc, regime, seed, target, extra_a_units=None):
    """Monte la bataille, amene `CARRIER` au contact de `target`, joue l'attaque normale LIVE et
    rejoue le MEME coup offline sous le port LIVRE et sous le CONTREFACTUEL (pas de `Maybe` dans
    les groupes). Rend `(live_groupe, shipped, no_maybe, n_arme)` ou skip."""
    r = regime(seed, CARRIER, extra_a_units or target, armor=6000)
    rid, board = r["rid"], r["board"]
    cid, tid, moved = drive(rpc, rid, board, CARRIER, target)
    if cid is None:
        pytest.skip(f"{CARRIER} n'a pas atteint {target} au contact")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng0, dict) and rng0.get("mt")):
        pytest.skip("dumpRng indispo")
    cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
    nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
    if nrm is None:
        pytest.skip("pas d'attaque normale")
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": nrm["id"]}, "captureEvents": True}, 120)
    if not _ok(res):
        pytest.skip(f"attaque live KO: {str(res)[:120]}")
    # FILTRE `Attacker_Id` : ecarte l'attaque du grot spawne par `SquigHound`, qui SUIT le groupe
    # dans le meme flux d'events -> le NOMBRE de coups de l'attaque devient observable, donc la
    # garde peut etre EXACTE EN NOMBRE (un `Maybe` qui reussit PENDANT le groupe y ajoute un coup).
    live, dirty, srcs = live_hits_of_attacker(res, tid, cid)
    if dirty:
        pytest.skip("coup non propre (crit/block/evade)")
    # `additional_hits_variant("roll_then_reduce", None)` IGNORE `bonus_hit_chance`/`hit_index0` :
    # c'est EXACTEMENT le port d'avant R6-b' (bon ordre tirage/reduction, aucun `Maybe` dans les
    # groupes) -> le contrefactuel de CETTE garde.
    off = replay_orders(dv, ob, snap, board, rng0, cid, tid, None, moved, {
        "no_maybe_grp": additional_hits_variant("roll_then_reduce", None)})
    nom, ship, arme = off["no_maybe_grp"], off["shipped"], off["arme"]
    n = len(arme)
    print(f"\n[R6-b'] seed={seed} cible={target} live={live} sources={srcs}")
    print(f"[R6-b'] arme_offline={arme} groupe livre={ship} contrefactuel_sans_Maybe={nom}")
    assert ship, "aucun coup additionnel rejoue offline (le porteur a-t-il l'effet SquigHound ?)"
    assert live[:n] == arme, (
        f"les coups d'ARME divergent (live={live[:n]} off={arme}) : le flux RNG n'est PAS aligne "
        "a l'entree du groupe -- la mesure ne porterait pas sur le `Maybe` after-hit.")
    assert len(live) > n, f"aucun event live apres les {n} coups d'arme : groupe non emis"
    return live[n:], ship, nom, n


def _assert_after_hit_maybe(grp_live, ship, nom, seed, target):
    # (1) RATCHET : le port TEL QU'IL EST LIVRE reproduit le groupe live coup par coup **ET EN
    #     NOMBRE** (un succes du `Maybe` PENDANT le groupe y defere un coup bonus de plus, que le
    #     live marque `Additional_Hit_TriggeredAbility_Source: 1234` = `AbilityOrEffect(0x4d2)`).
    assert ship == grp_live, (
        f"le port LIVRE ne reproduit pas le groupe : shipped={ship} live={grp_live} "
        f"(contrefactuel sans `Maybe` dans les groupes={nom}) -- `execute_additional_hits` "
        "d'`operations/additional_hits.py` roule-t-il encore le `Maybe` after-hit "
        "(`bonus_hit_chance`) avec l'index CONTINU de l'attaque (`hit_index0`) ?")
    # (2) DISCRIMINATION : le modele d'avant R6-b' (aucun `Maybe` dans les groupes) doit ECHOUER
    #     sur ce montage, sinon la garde est AVEUGLE (et la seed n'a rien a prouver).
    assert nom != grp_live, (
        f"seed {seed} / {target} : le contrefactuel SANS `Maybe` dans les groupes reproduit aussi "
        f"le live ({nom}) -- montage NON discriminant, rejouer "
        "`probe_r6bp_after_hit_maybe_groups.py` pour re-selectionner les seeds.")


@pytest.mark.parametrize("seed", SQUIG_SEEDS)
def test_after_hit_maybe_rolls_on_group_hits_live(live_session, rpc, pierce_dominant_regime, seed):
    """Porteur a **3** coups d'arme : la parite de l'index a l'entree du groupe est 3 (impair) si
    le `Maybe` d'arme a echoue, 4 (pair) s'il a reussi (coup bonus)."""
    grp_live, ship, nom, _ = _measure(rpc, pierce_dominant_regime, seed, TARGET)
    _assert_after_hit_maybe(grp_live, ship, nom, seed, TARGET)


@pytest.mark.parametrize("seed", PARRY_SEEDS)
def test_after_hit_maybe_group_parity_inverted_live(live_session, rpc, pierce_dominant_regime,
                                                    seed):
    """MEME porteur, cible `Parry` -> **2** coups d'arme : la parite a l'entree du groupe est
    INVERSEE par rapport au test precedent. Un modele qui « ajoute toujours un tirage avant le 2e
    coup du groupe » passe l'un et tombe sur l'autre."""
    grp_live, ship, nom, n = _measure(rpc, pierce_dominant_regime, seed, PARRY_TARGET)
    assert n in (2, 3), (
        f"le trait `Parry` de {PARRY_TARGET} devait ramener l'attaque a 2 coups d'arme "
        f"(+1 coup bonus GetStuckIn possible) ; mesure = {n} -- montage non conforme.")
    _assert_after_hit_maybe(grp_live, ship, nom, seed, PARRY_TARGET)
