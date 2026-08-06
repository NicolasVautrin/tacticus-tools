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

Equiper ouvre ce canal par la voie NATIVE, et non en reecrivant le scalaire apres coup comme
`--crit` / `--block-*`.

CE QUE #419-r6 A DEPLACE DANS CE FICHIER, ET POURQUOI CE N'EST PAS COSMETIQUE
-----------------------------------------------------------------------------
Quand ce fichier a ete ecrit, equiper etait un OPT-IN (`--bis-items`) et le defaut laissait le
canal ferme. #419-r6 a bascule ce defaut : desormais **tout runner** part equipe, et
`--bis-items` n'est plus qu'un no-op explicite. Le volet 2 disait alors « le MEME montage SANS
le drapeau doit avoir le canal FERME » -- il a donc ROUGI, exactement comme son propre message
d'echec l'avait prevu (« soit une autre voie equipe desormais les unites [...], ce fichier ne
garde plus rien et doit etre reecrit »).

Ce que le fichier garde a donc CHANGE D'OBJET, et c'est le bon : ce n'est plus « le drapeau
ouvre le canal », c'est **« le DEFAUT ouvre le canal »** -- l'invariant que #419-r6 livre. Le
bras temoin devient `--no-bis-items`, le seul chemin qui restitue encore le regime degenere.

LES DEUX VOLETS RESTENT INDISSOCIABLES
---------------------------------------
Le volet 1 seul ne prouverait rien : si le canal etait ouvert pour une raison exterieure, il
passerait au vert sans que l'equipement y soit pour quoi que ce soit. Le volet 2 exige donc que
le MEME montage, avec `--no-bis-items`, ait le canal FERME. C'est lui qui rend le premier
discriminant -- et c'est exactement le cran qui manquait a tout le harnais pendant que le canal
etait muet partout.
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
    """Bras MESURE : le montage NU, sans aucun drapeau -- c'est le DEFAUT qui doit equiper."""
    return _canaux(rpc, build_runner("777", extra=_BUILD)["rid"])


@pytest.fixture(scope="module")
def canaux_sans(rpc, build_runner):
    """Bras TEMOIN : `--no-bis-items`, le seul chemin qui restitue encore le regime degenere."""
    return _canaux(rpc, build_runner("777", extra=_BUILD + ["--no-bis-items"])["rid"])


@pytest.fixture(scope="module")
def canaux_drapeau(rpc, build_runner):
    """Bras RETRO-COMPAT : `--bis-items` est un no-op depuis #419-r6, il doit le rester."""
    return _canaux(rpc, build_runner("777", extra=_BUILD + ["--bis-items"])["rid"])


def test_419r5_le_defaut_ouvre_le_canal_crit(canaux_avec):
    """VOLET 1 -- SANS aucun drapeau, `CouldCrit` est VRAI au natif (#419-r6 : le defaut equipe)."""
    crit = [u for u in canaux_avec if u["could_crit"]]
    assert crit, (
        "canal CRIT FERME sur un runner par DEFAUT : "
        + "; ".join(f"e{u['id']} cc={u['cc']} cd={u['cd']}" for u in canaux_avec)
        + " -- `CouldCrit` = GetStat(9) > 0 && GetStat(10) > 0 est une CONJONCTION, "
          "donc un seul conjoint nul suffit a rendre le crit impossible (#419-r5). "
          "`_EQUIP_ITEMS_PAR_DEFAUT` a-t-il ete remis a False, ou TACTICUS_BIS_ITEMS=0 "
          "traine-t-il dans l'environnement ?")


def test_419r5_le_defaut_ouvre_le_canal_block(canaux_avec):
    """VOLET 1 bis -- meme chose pour `CouldBlock`, l'autre canal porte par les items."""
    block = [u for u in canaux_avec if u["could_block"]]
    assert block, (
        "canal BLOCK FERME sur un runner par DEFAUT : "
        + "; ".join(f"e{u['id']} bc={u['bc']} bd={u['bd']}" for u in canaux_avec))


def test_419r5_le_temoin_no_bis_items_ferme_le_canal(canaux_sans, canaux_avec):
    """VOLET 2 -- ANTI-TAUTOLOGIE : avec `--no-bis-items`, le canal doit etre FERME.

    Sans ce volet, le volet 1 passerait au vert meme si le canal etait ouvert pour une raison
    etrangere a l'equipement -- et le fichier entier cesserait de garder quoi que ce soit,
    silencieusement. C'est la forme meme du defaut #419-r5 : un vert qui ne discrimine rien.

    Ce volet garde AUSSI le temoin lui-meme : si `--no-bis-items` cessait de fermer le canal,
    toutes les mesures << regime d'avant >> de #419-r6 deviendraient inverifiables.
    """
    ouverts = [u for u in canaux_sans if u["could_crit"] or u["could_block"]]
    assert not ouverts, (
        "le canal est OUVERT alors que --no-bis-items demande de n'equiper personne : "
        + "; ".join(f"e{u['id']} cc={u['cc']} cd={u['cd']} bc={u['bc']} bd={u['bd']}"
                    for u in ouverts)
        + " -- le TEMOIN du regime d'avant #419-r5 ne restitue plus ce regime, donc plus "
          "aucune mesure de causalite de #419-r6 n'est reproductible")
    # Et le montage doit bien DISCRIMINER : meme porteur, meme board, meme seed.
    assert any(u["could_crit"] for u in canaux_avec), (
        "les deux bras rendent le canal ferme -- le montage ne discrimine RIEN, "
        "le vert du volet 2 ne prouverait rien")


def test_419r5_le_drapeau_bis_items_reste_un_noop(canaux_drapeau, canaux_avec):
    """VOLET 3 (#419-r6) -- `--bis-items` demande ce qui est desormais le DEFAUT.

    Il doit donc rendre EXACTEMENT le meme etat que le montage nu, et surtout ne pas ECHOUER :
    des appelants le posent encore, et un drapeau devenu erreur casserait leur montage sans que
    rien ne le dise.
    """
    nu = {u["id"]: (u["cc"], u["cd"], u["bc"], u["bd"]) for u in canaux_avec}
    dr = {u["id"]: (u["cc"], u["cd"], u["bc"], u["bd"]) for u in canaux_drapeau}
    assert dr == nu, (
        "`--bis-items` ne rend PAS le meme etat que le defaut -- il devrait etre un no-op "
        f"depuis #419-r6 : nu={nu} drapeau={dr}")
