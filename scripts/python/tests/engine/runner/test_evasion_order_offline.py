"""#407-r1 -- l'ESQUIVE precede le BLOCK dans `CalculateDamageOperation` : garde OFFLINE.

RE (decompile = verite, rnca9r7q6c), corps d'`IdunBattle.Core.Services.DamagePrediction$$
CalculateDamageOperation` -- les slots sont ceux d'`IDamageCalculations` (§2 de
`docs/rl/case-407-failed-block-attack-scope.md`) :

    blockChances  = slot 0   CalculateBlockChances(attacker, defender, failedBlockIds)   # 0 RNG
    evasionChance = slot 1   CalculateEvasionChance(attacker, defender)                  # 0 RNG
    shieldPart    = slot 0xc CalculateDamageBlockedByShield(shield, damage)              # 0 RNG
    rest          = Math.Max(0, damage - shieldPart)
    if damageInfo[+0x1E] == 0:               # trait de profil : saute block ET esquive
        if damageInfo[+0x1D] == 0:           # pas de block GARANTI
            ev = slot 3 ApplyRandomEvasion(evasionChance, rest, attacker, defender)
            if !ev.didEvade: bd = slot 2 ApplyRandomBlockDamage(blockChances, rest)
        else: rest = slot 4 ApplyBlockDamage(blockChances, rest)        # AUCUN tirage

=> il n'existe AUCUN drapeau XOR « block vs evasion » : c'est une SEQUENCE, et l'esquive n'ecarte
le block que si elle REUSSIT. L'octet que le port citait comme ce drapeau (`uStack_5b0>>0x28`)
est `damageInfo[+0x1D]`, le block GARANTI -- un mapping FAUX, corrige par #407-r1.

REGIME `evasionChance > 0` : **NON CONFRONTE**. `CalculateEvasionChance` = `GetStat(unit, 0xf)`
(`StatType.EVASION_CHANCE`) et `IdunBattle.Entities.Blueprints$$Unit` attache bien un
`EvasionChanceComponent` a toute unite -- mais rien n'y ecrit jamais (5 voies,
`probe_407r1_evasion_carriers.py`). A `evasion_chance == 0` l'esquive ne consomme AUCUN tirage :
le port livre est donc BIT-EXACT identique a l'ancien sur tout ce que le jeu atteint.

C'est exactement ce que ce fichier verrouille, dans l'ordre des trois assertions de
`test_failed_block_attack_scope_live.py` :
  (1) RATCHET   : a `ev == 0`, le port livre == le modele d'AVANT #407-r1, per-coup ET tirages
                  -> aucune regression possible sur le regime reel ;
  (2) REGIME    : a `ev > 0`, les deux modeles DIVERGENT -- sans quoi la garde serait verte et
                  AVEUGLE (elle passerait meme si l'ordre etait faux) ;
  (3) DISCRIM.  : le contrefactuel `xor` (block plus jamais atteint) doit ECHOUER, y compris a
                  `ev == 0` -- c'est LUI que la garde live peut jouer, faute de porteur d'esquive.
Plus (4) le CABLAGE : la signature ne porte plus le drapeau XOR, et aucun appelant du moteur ne
fournit d'esquive non nulle.

Mesure de reference (`probe_407r1_evasion_order.py`, 6 seeds x 3 regimes, 2026-08-01) :
    ev=0  -> legacy IDENTIQUE 6/6 (18 tirages des deux cotes) | xor diverge 6/6 (12 tirages)
    ev=20 -> legacy diverge 6/6 (30 vs 18 tirages)
    ev=50 -> legacy diverge 6/6 ; xor a les MEMES per-coup que le port mais PAS le meme nombre
             de tirages (28 vs 24) -- d'ou la comparaison sur (per_hit, draws), jamais per_hit seul.

100 % offline : aucun runner, aucun RPC.
"""
from __future__ import annotations

import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python

from probe_407r1_evasion_order import run_window                     # noqa: E402
from engine.services import damage_combat as DC                      # noqa: E402

SEEDS = [12345, 314159, 88, 777, 31337, 2026]
EVASIONS_ON = [20, 50]        # regimes NON CONFRONTES (aucun porteur) mais lisibles offline


def _window(seed, ev, model):
    """(per-coup, tirages consommes) -- la FENETRE, jamais un point : le tirage en trop/en moins
    est consomme APRES le resolve du coup courant, donc c'est le coup SUIVANT qui bouge."""
    w = run_window(seed, ev, model)
    return w["per_hit"], w["draws"]


@pytest.mark.parametrize("seed", SEEDS)
def test_1_ratchet_le_port_livre_est_bit_exact_a_evasion_nulle(seed):
    """(1) A `evasion_chance == 0` -- le SEUL regime que le jeu atteint -- l'ordre porte par
    #407-r1 ne change RIEN : `ApplyRandomEvasion` sort sans toucher au PRNG (`if evasion_chance
    > 0` est son unique porte) et rend le degat inchange. Le port livre doit donc reproduire le
    modele d'AVANT, per-coup ET nombre de tirages.

    C'est le cliquet de NON-REGRESSION : s'il tombe, c'est que l'esquive s'est mise a consommer
    ou a modifier quelque chose alors qu'aucune unite ne la porte."""
    assert _window(seed, 0, "shipped") == _window(seed, 0, "legacy"), (
        f"seed {seed} : a evasion_chance=0 le port livre DIVERGE du modele d'avant #407-r1 "
        f"(livre={_window(seed, 0, 'shipped')} legacy={_window(seed, 0, 'legacy')}) -- "
        "`apply_random_evasion` consomme-t-elle un tirage a chance nulle ?")


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("ev", EVASIONS_ON)
def test_2_le_regime_distingue_bien_les_deux_modeles(seed, ev):
    """(2) Sans cette assertion, (1) et (3) pourraient etre vertes ET AVEUGLES : il faut montrer
    qu'un regime EXISTE ou l'ordre porte se voit. Des `evasion_chance > 0`, le modele d'avant
    (qui n'evalue jamais l'esquive) doit diverger du port livre.

    Ce regime n'est PAS atteignable en jeu (aucun porteur de `StatType 15`, cf.
    `probe_407r1_evasion_carriers.py`) -- il est ici pour prouver que la correction porte sur
    quelque chose de reel, pas pour pretendre l'avoir confrontee live."""
    ship, leg = _window(seed, ev, "shipped"), _window(seed, ev, "legacy")
    assert ship != leg, (
        f"seed {seed} ev={ev} : les deux modeles donnent {ship} -- le montage ne discrimine plus "
        "l'ORDRE (les bornes/sources de block de `probe_407r1_evasion_order` ont-elles change ?)")


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("ev", [0] + EVASIONS_ON)
def test_3_le_contrefactuel_xor_echoue(seed, ev):
    """(3) DISCRIMINATION. `block_runs_after_evasion` rendu toujours `False` = le block n'est
    PLUS JAMAIS atteint apres l'etage esquive. C'est la faute que la garde LIVE sait attraper,
    parce qu'elle mord MEME a `evasion_chance == 0` (le regime reel).

    Si cette assertion devient verte, c'est que le chainage `esquive -> block` a disparu du port
    ou que la source de block ne roule plus."""
    ship, xor = _window(seed, ev, "shipped"), _window(seed, ev, "xor")
    assert ship != xor, (
        f"seed {seed} ev={ev} : le contrefactuel XOR reproduit le port livre ({ship}) -- la garde "
        "est AVEUGLE : `block_runs_after_evasion` est-elle encore le point de passage du block ?")


def test_4_cablage_plus_de_drapeau_xor_et_aucune_evasion_fournie():
    """(4) CABLAGE. Le drapeau `evasion_branch` a disparu de la signature (il portait un mapping
    natif FAUX), `evasion_chance` reste exposee, et AUCUN appelant du moteur ne la fournit --
    coherent avec « aucun porteur ». Le jour ou un porteur apparait, c'est cette assertion qui
    doit tomber et forcer le cablage explicite."""
    sig = inspect.signature(DC.calculate_damage_operation)
    assert "evasion_branch" not in sig.parameters, (
        "`evasion_branch` est revenu dans la signature : il n'existe AUCUN drapeau XOR natif "
        "(`uStack_5b0>>0x28` = `damageInfo[+0x1D]`, le block GARANTI -- pas un selecteur).")
    assert "evasion_chance" in sig.parameters, (
        "`evasion_chance` a disparu : c'est le slot 1 `CalculateEvasionChance` du natif.")
    assert sig.parameters["evasion_chance"].default == 0, (
        "le defaut de `evasion_chance` doit rester 0 (aucune unite ne porte `StatType 15`).")

    # Balayage des APPELS par AST (et pas par regex : `evasion_chance == 0` d'une docstring ou
    # d'une garde ressemble a un argument nomme et produirait un faux positif).
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[3] / "engine"
    appels, fournis = 0, []
    for p in root.rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name != "calculate_damage_operation":
                continue
            appels += 1
            for kw in node.keywords:
                if kw.arg != "evasion_chance":
                    continue
                if not (isinstance(kw.value, ast.Constant) and kw.value.value == 0):
                    fournis.append((str(p.relative_to(root)), ast.dump(kw.value)[:60]))
    assert appels >= 2, (
        f"seulement {appels} appel(s) de `calculate_damage_operation` trouve(s) dans engine/ : le "
        "balayage de cablage ne porte plus (les appelants attendus sont "
        "`runner/operations/damage_hits.py` et `runner/operations/displace.py`).")
    assert not fournis, (
        f"un appelant du moteur fournit une esquive non nulle : {fournis} -- un porteur de "
        "`StatType 15` est-il apparu ? Alors le regime devient CONFRONTABLE et la garde LIVE "
        "de #407-r1 doit etre rejouee sur ce porteur (cf. docs/rl/case-407-r1-evasion-order.md).")


@pytest.mark.parametrize("seed", SEEDS)
def test_5_une_esquive_reussie_court_circuite_la_chaine_block(seed):
    """L'ORDRE lui-meme, dans sa consequence observable : quand l'esquive REUSSIT, le natif fait
    `return` avant le slot 2 -> la chaine de block ne roule PAS pour ce coup (aucun tirage, aucune
    source ajoutee a la failed-list) et le degat du coup est 0.

    Mesure au grain du COUP : on force une esquive certaine (chance 99, la borne haute de
    `next_bool`) et on verifie qu'aucune source n'a echoue -- ce qui serait impossible si le block
    avait tourne derriere l'esquive."""
    w = run_window(seed, 99, "shipped")
    assert w["did_evade"], f"seed {seed} : chance 99 n'a produit aucune esquive"
    assert all(v == 0 for v in w["per_hit"]), (
        f"seed {seed} : une esquive certaine laisse passer du degat ({w['per_hit']})")
    assert not w["did_block"] and not w["failed"], (
        f"seed {seed} : la chaine de block a tourne DERRIERE une esquive reussie "
        f"(did_block={w['did_block']} failed={w['failed']}) -- le natif fait `return` avant le "
        "slot 2 `ApplyRandomBlockDamage`.")
