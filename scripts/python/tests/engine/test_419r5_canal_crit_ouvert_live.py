"""#419-r5 -- GARDE du canal CRIT/BLOCK.

Ce que ce fichier tient, et pourquoi il existe
----------------------------------------------
Les 4 stats `CritChance` / `CritDamage` / `BlockChance` / `BlockDamage` ne vivent QUE dans les
items equipes (gameconfig : `adeptMorvenn` porte `stats = {Health, Damage, FixedArmor}` et
`itemSlots = ["I_Crit", "I_Block", "I_Booster_Block"]`). `buildNormalizedBC` ECRASE les stats
du seed BC par la sortie de
`IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor` ; appelee sans items,
celle-ci rend 0 sur ces 4 stats. Resultat mesure au rank 17 : `could_crit` valait **0 sur 106**
unites normalisees.

Comme `IdunBattle.Core.Services.DamageCalculations$$CouldCrit` est
`GetStat(9) > 0 && GetStat(10) > 0` -- une CONJONCTION -- le crit etait alors impossible cote
NATIF comme cote PORT. `RollCritical` et le gate << never crit >> etaient structurellement
inertes, et tout accord natif-port sur ces chemins etait un accord en REGIME DEGENERE : les
deux cotes rendaient zero. Idem pour `$$CouldBlock`.

`rl_duel build --bis-items` ouvre ce canal par la voie NATIVE (equiper), et non en reecrivant
le scalaire apres coup comme `--crit` / `--block-*`.

LES DEUX VOLETS SONT INDISSOCIABLES
------------------------------------
Le volet 1 seul ne prouverait rien : si le canal etait ouvert pour une raison exterieure, il
passerait au vert sans que `--bis-items` y soit pour quoi que ce soit. Le volet 2 exige donc
que le MEME montage, SANS le drapeau, ait le canal FERME. C'est lui qui rend le premier
discriminant -- et c'est exactement le cran qui manquait a tout le harnais pendant que le
canal etait muet partout.
"""
from __future__ import annotations

import pytest

# Le montage : un porteur dont les slots sont CRIT + BLOCK (`adeptMorvenn` :
# ["I_Crit", "I_Block", "I_Booster_Block"]), donc les deux canaux d'un coup.
_PORTEUR = "adeptMorvenn"
_ADVERSE = "tauCrisis"
_BOARD = "MC1_67"
_BUILD = ["--p-units", _PORTEUR, "--a-units", _ADVERSE, "--board", _BOARD]


def _canaux(rpc, rid: int) -> list[dict]:
    """`(could_crit, could_block)` par unite, lus au NATIF via `combatSnapshot`.

    On lit le natif, pas le port : ce qui est garde ici est que l'ETAT MONTE porte les stats,
    en amont de toute question de fidelite du port.
    """
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    assert snap.get("ok"), f"combatSnapshot KO : {str(snap)[:200]}"
    out = []
    for u in snap.get("units") or []:
        st = u.get("stats") or {}
        cc, cd = st.get("critChance") or 0, st.get("critDamage") or 0
        bc, bd = st.get("blockChance") or 0, st.get("blockDamage") or 0
        out.append({"id": u.get("entityId"),
                    "cc": cc, "cd": cd, "bc": bc, "bd": bd,
                    "could_crit": cc > 0 and cd > 0,
                    "could_block": bc > 0 and bd > 0})
    assert out, "combatSnapshot n'a rendu AUCUNE unite -- montage casse, pas un verdict"
    return out


@pytest.fixture(scope="module")
def canaux_avec(rpc, build_runner):
    return _canaux(rpc, build_runner("777", extra=_BUILD + ["--bis-items"])["rid"])


@pytest.fixture(scope="module")
def canaux_sans(rpc, build_runner):
    return _canaux(rpc, build_runner("777", extra=_BUILD)["rid"])


def test_419r5_bis_items_ouvre_le_canal_crit(canaux_avec):
    """VOLET 1 -- avec `--bis-items`, `CouldCrit` est VRAI au natif."""
    crit = [u for u in canaux_avec if u["could_crit"]]
    assert crit, (
        "canal CRIT FERME malgre --bis-items : "
        + "; ".join(f"e{u['id']} cc={u['cc']} cd={u['cd']}" for u in canaux_avec)
        + " -- `CouldCrit` = GetStat(9) > 0 && GetStat(10) > 0 est une CONJONCTION, "
          "donc un seul conjoint nul suffit a rendre le crit impossible (#419-r5)")


def test_419r5_bis_items_ouvre_le_canal_block(canaux_avec):
    """VOLET 1 bis -- meme chose pour `CouldBlock`, l'autre canal porte par les items."""
    block = [u for u in canaux_avec if u["could_block"]]
    assert block, (
        "canal BLOCK FERME malgre --bis-items : "
        + "; ".join(f"e{u['id']} bc={u['bc']} bd={u['bd']}" for u in canaux_avec))


def test_419r5_sans_le_drapeau_le_canal_est_ferme(canaux_sans, canaux_avec):
    """VOLET 2 -- ANTI-TAUTOLOGIE : sans le drapeau, le canal doit etre FERME.

    Sans ce volet, le volet 1 passerait au vert meme si le canal etait ouvert pour une raison
    etrangere a `--bis-items` -- et le fichier entier cesserait de garder quoi que ce soit,
    silencieusement. C'est la forme meme du defaut #419-r5 : un vert qui ne discrimine rien.
    """
    ouverts = [u for u in canaux_sans if u["could_crit"] or u["could_block"]]
    assert not ouverts, (
        "le canal est OUVERT alors qu'aucun item n'est equipe : "
        + "; ".join(f"e{u['id']} cc={u['cc']} cd={u['cd']} bc={u['bc']} bd={u['bd']}"
                    for u in ouverts)
        + " -- soit une autre voie equipe desormais les unites (tant mieux, mais ce fichier "
          "ne garde plus rien et doit etre reecrit), soit le montage a change")
    # Et le montage doit bien DISCRIMINER : meme porteur, meme board, meme seed.
    assert any(u["could_crit"] for u in canaux_avec), (
        "les deux bras rendent le canal ferme -- le montage ne discrimine RIEN, "
        "le vert du volet 2 ne prouverait rien")
