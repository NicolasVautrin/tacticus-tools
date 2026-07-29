"""GARDE #263 -- un `applyAction` MAL CONSTRUIT ne doit JAMAIS ressembler a une mesure.

CE QUE CETTE GARDE EMPECHE DE REVENIR. Le 2026-07-29, `applyOneAction` rendait `ok:false`
dans une enveloppe par ailleurs NORMALE (`changes:[]`, `events:[]`, `eventCount:0`) quand
l'action ne pouvait pas etre construite. Aucun des ~250 montages Python ne lit `ok` : une
action JAMAIS EMISE se lisait comme « une action qui n'a rien fait », donc comme un RESULTAT.
Deux agents independants y ont perdu leurs mesures le meme jour (13 attaques pour l'un ; un
« l'ennemi n'inflige aucun degat » pour l'autre, alors que l'ennemi n'attaquait pas).

La reparation est cote HOOKS : `applyOneAction` LEVE desormais sur un echec de construction.
Cette garde tient la ligne -- si quelqu'un la re-adoucit en retour silencieux « pour la
robustesse », ces tests rougissent.

CE QUI EST TESTE EST LA FORME DU REFUS, pas le refus lui-meme : l'enveloppe rendue ne doit
PAS porter de cle `actions` (c'est elle qui rendait le refus indistinguable d'une mesure).

PAS DE KIND `attack`, et c'est la decision, pas un oubli : l'attaque normale EST une ability
dont l'`ActiveAbilityType` est PER-UNIT (`NormalAttackType`). Un kind dedie ferait deux facons
d'exprimer la meme chose et masquerait quelle ability a reellement tire.

NOTE SUR LE CANAL : le `_http` de `rl_collect_batch` (donc la fixture `rpc`) RATTRAPE
l'HTTPError et rend le corps `{"error": ...}`. Les ~250 probes, eux, utilisent `urlopen` nu
et prennent l'exception en pleine face. Les deux voies sont bruyantes ; celle qu'on teste ici
est la plus PERMISSIVE des deux -- si elle est propre, l'autre l'est a fortiori.

ASCII only. Le runner est construit par le corps du test -> dispose a la fin de CE test.
"""
from __future__ import annotations

import pytest


def _apply(rpc, rid, action):
    return rpc("applyAction", {"runnerId": rid, "action": action}, 60)


@pytest.fixture(scope="module")
def rid(build_runner):
    return build_runner("777")["rid"]


@pytest.mark.parametrize("action,attendu", [
    ({"kind": "attack", "casterId": 1, "targetId": 2}, "kind inconnu"),
    ({"kind": "ability", "targetId": 2}, "casterId"),
    ({"kind": "move"}, "unitId"),
])
def test_action_mal_construite_ne_rend_pas_d_enveloppe(rpc, rid, action, attendu):
    """Le refus ne doit porter AUCUNE cle `actions` : c'est elle qui le faisait
    passer pour une mesure. Et le message doit nommer ce qui manque."""
    res = _apply(rpc, rid, action)
    assert isinstance(res, dict), "reponse inattendue: %r" % (res,)
    assert "actions" not in res, (
        "REGRESSION #263 : le refus rend une enveloppe de MESURE (cle `actions`) -- "
        "un montage qui lit events/changes y verra « rien ne s'est passe ». Recu: %r"
        % (res,))
    msg = str(res.get("error") or "")
    assert msg, "refus SANS message -- indiagnostiquable. Recu: %r" % (res,)
    assert attendu in msg, "message peu clair (%r attendu dans %r)" % (attendu, msg)


def test_le_refus_de_attack_enseigne_le_chemin_propre(rpc, rid):
    """Refuser ne suffit pas : les deux agents de #263 ont ecrit `attack` parce que
    c'est le mot naturel. Le message doit dire par ou passer."""
    msg = str(_apply(rpc, rid, {"kind": "attack"}).get("error") or "")
    assert "ability" in msg and "NormalAttackType" in msg, (
        "le refus de `attack` doit renvoyer vers ability + NormalAttackType "
        "(type PER-UNIT). Recu: %r" % (msg,))


def test_une_action_bien_formee_passe_toujours(rpc, rid):
    """La levee ne doit pas manger le cas normal : `endturn` reste applicable et rend
    une enveloppe de MESURE complete."""
    res = _apply(rpc, rid, {"kind": "endturn"})
    assert isinstance(res, dict) and "actions" in res, (
        "un `endturn` bien forme doit rendre une enveloppe de mesure. Recu: %r" % (res,))
    assert res.get("ok") is True, "endturn refuse: %r" % (res,)
