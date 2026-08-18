"""#589-r1-r1-r2-r1-r3 / #910-r1 (axe CRIT) -- LA PREVISION N'A AUCUN CANAL CRIT D'EFFET, et
c'est un RESULTAT, pas un trou.

## Comment la refutation a ete etablie -- et pourquoi la methode compte

L'enonce disait << la face PREDICTION ignore les canaux CRIT >>, sous-entendu : elle DEVRAIT les
lire. La re-mesure dit l'inverse. Mais **un grep de NOMS sur un decompile ne peut pas refuter un
appel dispatche par INTERFACE** : il ne le voit pas. On enumere donc les DISPATCHES.

`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` (2778 lignes, build charge)
n'invoque que **TROIS** slots d'`IDamageCalculations` :

    0  CalculateBlockChances
    7  CouldCrit
    12 CalculateDamageBlockedByShield

(noms LUS dans `data/symbols/<build>/metadata/interface_slots.tsv`.) Les deux slots CRIT du meme
contrat -- `5 ApplyCritDamage` et `6 RollCritical` -- n'y sont PAS. Et aucun appel DIRECT nomme
`CalculateCriticalDamage` / `GetCritChanceBonusFromEffects` / `GetCritDamageBonusFromEffects` n'y
figure : un appel intra-classe sort par son NOM dans le pseudo-C, et `GetBaseDamageFix64` comme
`IsAttackMaxOutDamage` y sont bien visibles -- donc l'absence est LISIBLE sur cet axe-la.

Le SEUL canal crit que la prevision ecrit est `MightCrit@+0xB1` = `CouldCrit(attacker)`, dont le
corps est `GetStat(9 = CritChance) >= 1 && GetStat(10 = CritDamage) > 0` -- des stats **NUES**.

## Ce que ce cliquet garde

Il ne re-fait pas la RE : il fige le CONTRAT du port, c'est-a-dire l'ensemble des canaux que la
prevision accepte. Un correctif qui << fermerait le residu >> en branchant
`crit_chance_bonus_from_effects` / `crit_damage_bonus_from_effects` ici ferait mordre le canal
PLUS LARGE que le jeu -- et ce fichier rougirait.

CONTRE-EPREUVE (jouee) : ajouter un parametre de canal crit d'effet a `attacker_could_crit` fait
rougir l'etage 2 ; faire lire a `attacker_could_crit` autre chose que les deux stats nues fait
rougir l'etage 1.

ASCII only.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.services import damage_prediction as DP        # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/services/damage_prediction.py",
        "scripts/python/engine/services/damage_combat.py",
        "scripts/python/tests/engine/test_589r3_prediction_sans_canaux_crit_offline.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("Le fichier lit deux SOURCES Python (`attacker_could_crit` et `_crit_params`) et "
               "evalue un predicat a deux stats : ni binaire ni `data/symbols/**`, d'ou "
               "`build: False`. Les trois chemins sont les deux FACES confrontees plus le "
               "fichier lui-meme -- `damage_combat.py` parce que le seuil `could_crit` y vit. "
               "Elargir le contrat de la face PREDICTION (etage 2) ou retirer les canaux de la "
               "face EXECUTION (etage 3) sont les deux seules facons de faire basculer ce "
               "verdict, et les deux passent par ces chemins."),
}


class _Ctx:
    """Le contrat que `attacker_could_crit` lit : DEUX stats, et rien d'autre."""

    def __init__(self, cc, cd):
        self.crit_chance, self.crit_damage = cc, cd


# --------------------------------------------------------------------------------------------
# Etage 1 -- `MightCrit` = les DEUX stats NUES, et le seuil est celui du natif.
# --------------------------------------------------------------------------------------------

def test_might_crit_lit_les_deux_stats_nues():
    """`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` :
    `GetStat(9 = CritChance) >= 1 && GetStat(10 = CritDamage) > 0`."""
    assert DP.attacker_could_crit(_Ctx(31, 2706)) is True
    assert DP.attacker_could_crit(_Ctx(0, 2706)) is False, "seuil `CritChance >= 1`"
    assert DP.attacker_could_crit(_Ctx(31, 0)) is False, "seuil `CritDamage > 0`"
    # TEMOIN NON VIDE : sans porteur, le predicat doit pouvoir etre VRAI -- sinon les deux
    # assertions negatives ci-dessus passeraient sur une fonction constante a False.
    assert DP.attacker_could_crit(_Ctx(1, 1)) is True
    assert DP.attacker_could_crit(None) is False, "aucun contexte -> False, jamais permissif"


# --------------------------------------------------------------------------------------------
# Etage 2 -- LE CONTRAT : aucun canal crit d'EFFET n'entre dans la prevision.
# --------------------------------------------------------------------------------------------

def test_la_prevision_n_expose_aucun_canal_crit_d_effet():
    """Les deux foyers `crit_chance_bonus_from_effects` / `crit_damage_bonus_from_effects` vivent
    cote EXECUTION (`runner/operations/damage.py::AttackDamageOperation._crit_params`). Les
    brancher ICI ferait diverger la prevision du jeu."""
    params = list(inspect.signature(DP.attacker_could_crit).parameters)
    assert params == ["attacker_ctx"], (
        "`attacker_could_crit` a gagne un canal : %s. `PredictAttackRaw` n'invoque QUE les slots "
        "0/7/12 d'`IDamageCalculations` -- ni `5 ApplyCritDamage` ni `6 RollCritical`. Relire le "
        "decompile avant d'elargir ce contrat (#589-r1-r1-r2-r1-r3)." % params)
    src = inspect.getsource(DP.attacker_could_crit)
    for interdit in ("crit_chance_bonus_from_effects", "crit_damage_bonus_from_effects",
                     "GetCritChanceBonusFromEffects", "GetCritDamageBonusFromEffects"):
        assert interdit not in src.split('"""')[-1], \
            "canal d'EFFET branche dans le corps de la prevision : %s" % interdit


# --------------------------------------------------------------------------------------------
# Etage 3 -- le canal EXISTE bel et bien cote EXECUTION (contre-temoin : le residu n'est pas
#            << personne ne porte ces bonus >>, c'est << la prevision ne les lit pas, et le natif
#            non plus >>).
# --------------------------------------------------------------------------------------------

def test_les_deux_canaux_existent_bien_cote_execution():
    from engine.runner.operations import damage as D
    assert hasattr(D.AttackDamageOperation, "_crit_params"), \
        "le pendant EXECUTION a disparu : ce fichier ne compare plus rien"
    src = inspect.getsource(D.AttackDamageOperation._crit_params)
    assert "crit_damage_bonus_from_effects" in src and "crit_chance_bonus_from_effects" in src, \
        ("les canaux crit d'effet ne sont plus lus par `_crit_params` -- l'asymetrie que ce "
         "fichier documente n'existerait plus, et son etage 2 deviendrait vacant")
