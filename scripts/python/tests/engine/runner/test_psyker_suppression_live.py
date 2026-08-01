"""case-418-r1 -- GARDE du noeud `IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget`, sur le
call-site `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$
IsPsykerAttackSuppressed`.

Le splash << Smite >> du trait Psyker est SUPPRIME quand le psyker figure dans la liste
`EffectComponent.Targets @+0x48` d'une entite-effet `1191
HuntersBeyondDeathPsykerSuppression`. Cette liste est maintenue par
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` depuis
`...HuntersBeyondDeathPsykerSuppressionEffect$$CreateTargetSelector` =
`UnitsWithoutTrait(UnitsWithTrait(SurroundingEnemies(Owner, unitTile, range = 2, unique, sel = 3),
Psyker), Immune)` -- l'instance elle-meme est POSEE SUR SON PORTEUR
(`HuntersBeyondDeathAbility$$CreateBehaviour` = `AddEffect(0x4a7, ref, Owner, Owner, ...)`).

Ce que ces gardes ROUGISSENT :

  * lire `EffectsState.has_effect(psyker, 1191)` au lieu de la liste de cibles (l'etat AVANT
    case-418-r1) -- structurellement toujours faux, donc splash JAMAIS supprime ;
  * porter `SurroundingUnits` au lieu de `SurroundingEnemies` (volet `ally_carrier`) ;
  * sur-fermer le gate (volet `free`, ou le splash DOIT firer).

Le montage vit dans `probe_418_r1_is_effect_target.py`. Un montage qui n'aboutit pas ASSERTE
(jamais un skip vert).
"""
from __future__ import annotations

import pytest

import probe_418_r1_is_effect_target as P


@pytest.fixture(scope="module")
def psyker_suppression_case(live_session):
    """Fabrique : `psyker_suppression_case(<variant>)` -> {label: mesure}. Un build par variante,
    dispose a la sortie ; portee MODULE (les assertions du fichier se partagent la mesure)."""
    cache: dict = {}

    def _case(variant: str = "core") -> dict:
        if variant not in cache:
            import rl_collect_batch as R

            def _unwrap(x):
                return x.get("result") if isinstance(x, dict) and "result" in x else x

            sid = R._resolve_session()

            def rpc(method, body=None, timeout=120):
                return _unwrap(R._rpc(sid, method, [body] if body is not None else [],
                                      timeout=timeout))

            try:
                res = P.run(rpc, P.SEED, P.BOARD, keep=False, variant=variant)
            except RuntimeError as exc:                  # montage non installe -> ROUGE
                pytest.fail("montage 418-r1 NON INSTALLE (variant=%s) : %s" % (variant, exc),
                            pytrace=False)
            cache[variant] = {m["label"]: m for m in res["measures"]}
        return cache[variant]
    return _case


def _m(case, variant, label):
    ms = case(variant)
    m = ms.get(label)
    assert m is not None, "mesure '%s' absente du volet %s (mesures=%s)" % (label, variant,
                                                                           sorted(ms))
    assert not m.get("error"), "montage KO sur '%s' : %s" % (label, m.get("error"))
    assert m.get("cast_ok"), "le tir LIVE a echoue sur '%s'" % label
    assert not m.get("dirty"), "coup non propre (crit/block/evade) sur '%s' -- hors axe" % label
    assert m.get("live_primary"), "aucun degat primaire LIVE sur '%s'" % label
    assert m.get("port_ranged") is True and m.get("port_profile") == "Psychic", (
        "le vecteur porte n'est pas l'attaque RANGED Psychic sur '%s' (ranged=%s profile=%s)"
        % (label, m.get("port_ranged"), m.get("port_profile")))
    return m


def test_carrier_owns_the_effect_not_the_psyker(psyker_suppression_case):
    """L'instance `1191` est portee par le SUPPRESSEUR, jamais par le psyker : c'est ce qui rend
    `has_effect(psyker, 1191)` structurellement faux, et donc le gate d'avant #418-r1 inoperant."""
    m = _m(psyker_suppression_case, "core", "same_turn")
    assert m["suppressor_carries_1191"] is True, (
        "le porteur de HuntersBeyondDeath doit OWNER l'effet 1191 (EffectsOwnedComponent)")
    assert m["psyker_carries_1191"] is False, (
        "le psyker ne porte PAS 1191 -- s'il le portait, `has_effect` suffirait et le noeud "
        "`IsEffectTarget` serait un synonyme de `HasEffect`")
    assert "Psyker" in m["psyker_traits"], "le caster doit porter le trait Psyker"


def test_splash_fires_when_no_suppressor_in_range(psyker_suppression_case):
    """TEMOIN : psyker a d = 3 du suppresseur -> hors du disque `range = 2` -> le splash FIRE, et le
    port le reproduit bit-exact. Sans ce volet, << pas de splash >> ne prouverait rien."""
    m = _m(psyker_suppression_case, "core", "free")
    assert m["dist_suppressor"] is not None and m["dist_suppressor"] > 2, (
        "montage : le suppresseur doit etre HORS du disque range=2 (d=%s)" % m["dist_suppressor"])
    assert m["live_splash_fired"], "le splash Psyker doit firer LIVE hors de portee du suppresseur"
    assert m["port_splash_fired"], "le port doit firer le splash hors de portee du suppresseur"
    live = m["live_splash"]
    port = {str(s["target"]): s["per_hit"] for s in m["port_splash"]}
    assert {str(k): v for k, v in live.items()} == port, (
        "splash live %s != port %s" % (live, port))


@pytest.mark.parametrize("label", ["same_turn", "after_turn"])
def test_splash_suppressed_inside_the_aura(psyker_suppression_case, label):
    """Psyker a d = 2 d'un porteur ENNEMI de `HuntersBeyondDeath` -> il est dans la liste de cibles
    de `1191` -> le splash se TAIT, live ET port.

    `same_turn` = deplacement PUIS tir dans le MEME tour ; `after_turn` = meme position apres un
    cycle complet. Les deux mesurent le MEME resultat : la liste native n'est PAS en retard d'un
    refresh (regime discriminant << materialise vs re-derive >>, case-418-r1 §3)."""
    m = _m(psyker_suppression_case, "core", label)
    assert m["dist_suppressor"] == 2, (
        "montage : le psyker doit etre a d = 2 du suppresseur (d=%s)" % m["dist_suppressor"])
    assert not m["live_splash_fired"], (
        "le natif SUPPRIME le splash ici -- mesure live %s" % (m["live_splash"],))
    assert not m["port_splash_fired"], (
        "le port doit se taire comme le natif -- il a splashe %s" % (m["port_splash"],))


def test_friendly_carrier_does_not_suppress(psyker_suppression_case):
    """Le porteur du passif est un AMI du psyker, a d = 2 : `SurroundingEnemies` ne le cible PAS ->
    le splash FIRE. Ce volet ROUGIT si le port avait ecrit `SurroundingUnits`."""
    m = _m(psyker_suppression_case, "ally", "ally_carrier")
    assert m["dist_suppressor"] is not None and m["dist_suppressor"] <= 2, (
        "montage : le porteur AMI doit etre dans le disque range=2 (d=%s)" % m["dist_suppressor"])
    assert m["live_splash_fired"], (
        "un porteur AMI ne supprime pas le splash (selecteur `SurroundingEnemies`)")
    assert m["port_splash_fired"], "le port ne doit pas fermer sur un porteur AMI"
    live = m["live_splash"]
    port = {str(s["target"]): s["per_hit"] for s in m["port_splash"]}
    assert {str(k): v for k, v in live.items()} == port, (
        "splash live %s != port %s" % (live, port))
