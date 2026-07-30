"""#301 (face LIVE) -- le regime « une mort PORTE un killTrigger » est-il ATTEINT en bataille ?

La garde OFFLINE (`test_kill_unit_trigger_channels.py`) etablit **ou** va le `killTrigger` quand il
existe : sur `state.trigger_ability_type` (`AbilityEntities+0x98`), jamais sur
`state.triggering_ability` (`+0x60`, que le memset de
`IdunBattle.Operations.KillUnitOperation$$Execute` laisse VIDE). Elle n'etablit pas qu'un
`killTrigger` EXISTE -- et une garde suspendue en l'air garde peu.

Ce fichier le mesure sur une bataille REELLE. Le seul montage porte qui produise un `killTrigger`
non nul est la chaine `HazeOfCorruption` : les relais y meurent DANS le behaviour de
`HazeOfCorruptionDamageTransferTrigger` (`TRIGGERED_ABILITY_ID = 0x435 = 1077`), donc leur entree de
`IdunBattle.Core.MatchState$$AddDeath` porte 0x435.

MESURE (board et seed de `case-haze-bonded`, seed 777 / PV 1200 / k = 2), trois morts drainees :

    APRES #301 : [(77, None, None), (81, 1077, None), (79, 1077, None)]   (dying, +0x98, +0x60)
    AVANT #301 : [(77, None, None), (81, None, 1077), (79, None, 1077)]

soit l'INVERSION exacte des deux canaux -- et c'est le ROUGE qui donne sa valeur a ce fichier.

⚠ CE QUE CE TEST N'ETABLIT PAS, et il faut le dire : le probe `220` lui-meme reste VERT des DEUX
cotes du fix (memes 14 `genrand`, meme `bonus_fire = 1`, memes PV). La divergence corrigee est
LATENTE : aucun consommateur porte ne lit `+0x60` sur le vecteur mort aujourd'hui, donc aucun
observable de bataille ne bouge. C'est precisement la signature d'une degradation PERMISSIVE -- elle
ne se voit que sur le canal, ce que ce test regarde.
"""
from __future__ import annotations

import pytest

import probe_301_kill_unit_trigger_channels as KUC


@pytest.fixture(scope="module")
def kill_trigger_live_row():
    """Une seule bataille pour tout le module (le montage coute ~2 min)."""
    r = KUC.run_live(seed="777", hp="1200", k=2, verbose=False)
    if not r["deaths"]:
        pytest.skip("montage 220 KO : aucune mort drainee (le probe n'a rien monte)")
    return r


def test_le_regime_est_atteint_une_mort_porte_un_kill_trigger(kill_trigger_live_row):
    """SANS CETTE CLAUSE, tout le reste passerait au vert sur un montage degrade.

    Un montage ou aucune mort ne porte de declencheur verifierait « +0x60 est vide » trivialement
    (il l'est partout) sans jamais exercer le bloc `+0x98..+0xb4`. On EXIGE donc au moins une mort a
    `killTrigger` non nul -- mesure : 2 sur 3 (les deux relais de la chaine 1077)."""
    r = kill_trigger_live_row
    assert r["with_trigger"], (
        "regime NON ATTEINT : aucune des %d morts ne porte de killTrigger ; la garde du canal "
        "+0x98 ne serait pas exercee" % len(r["deaths"]))
    assert all(int(d[1]) == 1077 for d in r["with_trigger"]), (
        "killTrigger attendu = 0x435 (HazeOfCorruption_DamageTransfer) ; vu %s"
        % ([d[1] for d in r["with_trigger"]],))


def test_current_ability_reste_vide_sur_toutes_les_morts(kill_trigger_live_row):
    """LE FAIT NATIF, mesure live : `KillUnitOperation$$Execute` memset son `AbilityEntities` et n'y
    reecrit jamais `+0x60`. Aucune des morts drainees ne doit donc exposer de `CurrentAbility` --
    y compris celles dont le coup fatal est parti d'une triggered qui, elle, avait bien pose `+0x60`
    pendant son behaviour. C'est la moitie du fix que le mode `nowipe` du probe neutralise."""
    r = kill_trigger_live_row
    assert not r["leaked"], (
        "+0x60 NON VIDE sur %d mort(s) %s ; le natif ne publie AUCUN CurrentAbility sur les cinq "
        "evenements de KillUnitOperation" % (len(r["leaked"]), r["leaked"]))


def test_le_montage_220_reste_d_accord_avec_le_natif(kill_trigger_live_row):
    """NON-REGRESSION du COMPORTEMENT : le recablage ne doit rien changer de ce que le port produit.

    Le gate `NOT TriggeringEffectIs(0x435)` de `HazeCorruption_BonusHitAbility` CONSOMME ce canal ;
    s'il etait branche du mauvais cote apres #301, il deviendrait permissif et le port emettrait des
    coups bonus en trop -- exactement l'ecart que `probe_220 --cf` mesure (18 `genrand` / 3 fires au
    lieu de 14 / 1). `rc == 0` couvre les accords PV+vivant et `genrand` port==natif du probe 220."""
    assert kill_trigger_live_row["rc"] == 0, \
        "le montage 220 n'est plus d'accord avec le natif apres le recablage du canal"
