"""#366-r1-effect-targets -- le canal `EffectComponent+0x48` est CABLE cote port, et TRI-ETAT.

CE QUE CE FICHIER GARDE. `IdunBattle.Operations.RefreshEffectsOperation$$AddTargetsToEffect` ->
`IdunBattle.Entities.Components.EffectComponent$$AddTargetId` materialise les CIBLES sur
l'entite-EFFET (`+0x48`) -- c'est la SORTIE native de tout `CreateTargetSelector` d'effet, et le
champ que lit `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffectOfType`.

Le residu le disait bloque par un CAPTEUR MANQUANT. Il ne l'est plus : le capteur est deploye et
verifie live depuis le 2026-08-01 (`frida/hooks/game/effects.ts::readEffectTargetIds`, publie sous
`decisionView.units[].effects[].targetIds`, 36/36 effets porteurs, 0 null / 0 vide). Ce qui
manquait etait le bout PORT : rien ne lisait le champ. `EffectFactory.create` le lit desormais.

LE TRI-ETAT EST L'OBJET DU TEST, pas un detail : `None` = **pas mesure** (capture anterieure au
capteur, ou pose OFFLINE qui ne materialise pas la liste) ; `[]` = mesure faite et VIDE. Les
rabattre l'un sur l'autre ferait lire << aucune cible >> la ou il faut lire << on ne sait pas >> --
la faute exacte que `host_inputs.py` et le capteur lui-meme sont ecrits pour interdire.
"""
from __future__ import annotations

from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import EffectFactory


def _create(**extra):
    captured = {"name": "Pinned", "effectType": 1065, "level": 1, "remaining": 2, "source": 7}
    captured.update(extra)
    return EffectFactory.create(captured)


def test_le_defaut_est_NON_MESURE():
    """Aucune cle `targetIds` (pose OFFLINE, capture anterieure au capteur) -> `None`, jamais `[]`."""
    assert BaseEffect.target_ids is None, "le defaut de CLASSE doit rester `None` (= pas mesure)"
    assert _create().target_ids is None


def test_un_null_du_capteur_reste_NON_MESURE():
    """Le capteur rend explicitement `null` quand il n'a pas pu resoudre le champ. Ce `null` ne doit
    PAS devenir `[]` : `readEffectTargetIds` est deja tri-etat, le port ne l'aplatit pas."""
    assert _create(targetIds=None).target_ids is None


def test_une_liste_VIDE_est_une_MESURE():
    """`[]` = l'entite-effet existe et n'a AUCUNE cible materialisee -- c'est un fait, pas une
    absence de fait. Il doit se distinguer du `None` ci-dessus."""
    eff = _create(targetIds=[])
    assert eff.target_ids == []
    assert eff.target_ids is not None


def test_les_cibles_sont_recopiees_en_ENTIERS():
    """Temoin NON NUL. `EffectComponent+0x48` est une `List<BEntityId>` ; le port en fait des ids
    entiers, la monnaie d'entite de l'`EffectsState`."""
    eff = _create(targetIds=[83, 91])
    assert eff.target_ids == [83, 91]
    assert all(isinstance(t, int) for t in eff.target_ids)


def test_deux_instances_ne_PARTAGENT_pas_leur_liste():
    """L'attribut est de CLASSE (defaut `None`) et l'ecriture est PAR INSTANCE : deux effets seedes
    dans la meme passe ne doivent pas se marcher dessus."""
    a = _create(targetIds=[1])
    b = _create(targetIds=[2, 3])
    c = _create()
    assert (a.target_ids, b.target_ids, c.target_ids) == ([1], [2, 3], None)
