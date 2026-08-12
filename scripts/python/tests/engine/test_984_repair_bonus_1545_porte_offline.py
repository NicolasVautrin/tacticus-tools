"""#984 -- CLIQUET de la refutation du volet 1545 de `#902-r1`.

`#902-r1` affirmait : « `1545 NanoscarabRepairProtocols` : `$$CreateEffectRepairBonus` =
`EffectBonus.ForAddition(OwnerIsTarget, ConfigVar(0x24 = hpToRepair))` -> le +hpToRepair a chaque
reparation recue N'EST PAS PORTE ». **C'est faux, et ce fichier le garde executable.**

Le bonus EST porte -- mais pas la ou le residu le cherchait. Il ne vit pas dans une classe
d'`EFFECT_CLASSES` : il vit dans le foyer UNIQUE
`engine.predict.calculate_repair_modifier_for_prediction`, et c'est un ARBITRAGE EXPLICITE, ecrit
dans `engine/entities/effects/loki/nether_realm_casket.py` :

    « [1456] n'a **pas** de classe d'effet, et c'est un CHOIX : la regle du canal
      `IdunBattle.Entities.Effects.BaseEffect$$RepairBonus` (quels `EffectType` contribuent,
      `add` vs `pct`, et le gate `TriggeringAbilityIs`) vit dans le foyer UNIQUE
      `engine.predict.calculate_repair_modifier_for_prediction`, partage par les DEUX faces --
      c'est l'arbitrage deja pris pour les DEUX autres implementeurs du canal
      (`NanoscarabRepairProtocols` 1545, `VoltagheistField_RepairReduction` 1382), qui n'ont pas
      de classe non plus. En creer une ici dupliquerait la regle : un fork, pas un port. »

⚠ **L'ENJEU N'EST PAS DOCUMENTAIRE.** Repondre au residu en creant une classe d'effet 1545 dans
`EFFECT_CLASSES` ecrirait exactement ce fork : deux regles pour un seul canal natif, qui
divergeraient au premier changement de build. Un residu dont on ne garde pas la refutation se
rouvre -- ce fichier est ce qui l'empeche.

Le cliquet porte sur le COMPORTEMENT (le bonus mord), pas sur l'emplacement du code : si un jour
l'arbitrage change et que 1545 gagne une vraie classe d'effet, ces tests doivent rester VERTS.
"""
from __future__ import annotations

import engine.predict as predict
import engine.runner.operations.repair as repair_ops


#: `EffectType` 1545, tel que `decisionView.units[].effects[].name` le publie.
NANOSCARAB = "NanoscarabRepairProtocols"
#: `EffectType` 1546 -- le nom VOISIN, qui ne doit RIEN contribuer a ce canal (c'est un stat-mod
#: HEALTH, cf. le volet encore ouvert de `#902-r1`). Il garde le matching par nom EXACT.
NANOSCARAB_EXTRA_HP = "NanoscarabRepairProtocols_ExtraHp"


def _eff(name, level=50, source=None):
    return {"name": name, "level": level, "source": source}


def test_le_bonus_de_reparation_de_1545_MORD():
    """Le coeur de la refutation : l'effet porte par la CIBLE augmente la reparation recue."""
    avec = predict.calculate_repair_modifier_for_prediction([_eff(NANOSCARAB)])
    sans = predict.calculate_repair_modifier_for_prediction([])

    assert sans == (0, 1.0), "no-op exact attendu sans effet (`RepairModifier$$Empty`)"
    add, mul = avec
    assert add > 0, (
        "le +hpToRepair de 1545 ne mord PAS -- si ce test rougit, le volet 1545 de #902-r1 "
        "redevient VRAI et le bonus doit etre re-porte (dans le foyer, pas dans une classe)")
    assert mul == 1.0, "1545 est un `ForAddition` : il ne doit toucher QUE `add`, jamais `mult`"


def test_le_matching_est_par_nom_EXACT_et_pas_par_prefixe():
    """Contre-epreuve indispensable : `..._ExtraHp` PREFIXE `NanoscarabRepairProtocols`. Un
    matching par prefixe ferait contribuer 1546 a un canal ou le natif ne le met pas, et le test
    ci-dessus passerait quand meme -- il ne garderait alors plus rien."""
    voisin = predict.calculate_repair_modifier_for_prediction([_eff(NANOSCARAB_EXTRA_HP)])
    assert voisin == (0, 1.0), (
        "1546 contribue au canal RepairBonus alors que son `CreateEffectRepairBonus` n'existe pas "
        "-- matching par prefixe au lieu du nom exact")


def test_les_DEUX_faces_partagent_le_FOYER_et_ne_le_reimplementent_pas():
    """L'argument qui interdit le fork : la face COMBAT ne reecrit pas la regle, elle appelle le
    MEME foyer que la face PREDICTION. C'est verifie par IDENTITE d'objet, pas par un grep : un
    module qui recopierait la regle passerait un test textuel et echouerait celui-ci."""
    assert (repair_ops.calculate_repair_modifier_for_prediction
            is predict.calculate_repair_modifier_for_prediction), (
        "la face COMBAT n'appelle plus le foyer partage -- la regle du canal `BaseEffect$$RepairBonus` "
        "a ete forkee, exactement ce que l'arbitrage de `nether_realm_casket.py` interdit")


def test_le_cumul_de_deux_porteurs_est_SOMME():
    """`IdunBattle.Core.Services.RepairModifier$$Add` : les `add` sont SOMMES. Deux instances de
    1545 sur la meme cible doivent donc doubler l'apport -- garde que la boucle ne fait pas un
    `break` sur le premier effet trouve."""
    un = predict.calculate_repair_modifier_for_prediction([_eff(NANOSCARAB)])[0]
    deux = predict.calculate_repair_modifier_for_prediction([_eff(NANOSCARAB), _eff(NANOSCARAB)])[0]
    assert un > 0, "temoin degenere : le porteur unique n'apporte deja rien"
    assert deux == 2 * un, (
        "les `add` ne se SOMMENT pas (%s puis %s) -- `RepairModifier$$Add` est un fold, pas un "
        "remplacement" % (un, deux))
