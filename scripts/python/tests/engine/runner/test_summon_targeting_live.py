"""#250 -- GARDE des masques de ciblage des CINQ abilities du module `summon`
(`engine/runner/abilities/loki/summon.py`) : 1007 ScarabHive, 1045 GetEmRuntz, 1047 ScarabSummon,
1096 MasterOfTheTutelaries, 1166 AberrantHypermorph.

UN TEST PAR ABILITY (les cinq ont des masques SANS RAPPORT, et deux formes de ctor differentes) :

  id    forme de ctor                                        masque    portee          attackType
  ----  ---------------------------------------------------  --------  --------------  ----------
  1007  FLAGS DIRECTS  ..ctor(&opts,0,&TR30,1,0x4020,...)     0x4020    RANGE_ADJACENT  1
  1045  PRESET COPIE   `TargetingOptions statics+0x280`       0x8004    RANGE_SELF      2
  1047  FLAGS DIRECTS  ..ctor(&opts,1,&TR60,1,0x208000,...)   0x208000  RANGE_SELF      2
  1096  FLAGS DIRECTS  ..ctor(&opts,0,&TR30,1,0x1040,...)     0x1040    RANGE_ADJACENT  2
  1166  FLAGS DIRECTS  ..ctor(&opts,0,&TR30,1,0x1040,...)     0x1040    RANGE_ADJACENT  2

(`TR30`/`TR60` = les `TargetingRange` STATIQUES +0x30/+0x60 ecrits par
`IdunBattle.Core.Services.TargetingRange$$.cctor`.) 1007 et 1047 sont dans le MEME fichier, de la
MEME forme de ctor, et n'ont NI le meme litteral NI le meme `TargetingRange` : chaque ctor est lu.

CE QUE CES TESTS VERROUILLENT, et pourquoi ils ECHOUENT sans les masques : sans
`TARGETING_OPTIONS`, `get_invalid_target_reason` rend 0 des sa premiere ligne (`options is None`
=> aucun gate). Le moteur ACCEPTE alors -- MESURE -- un ScarabHive sur soi-meme ou sur un allie et
sur un ennemi a 4-5 hex, un GetEmRuntz / ScarabSummon sur n'importe qui (ce sont des self-casts de
portee 0), un MasterOfTheTutelaries / AberrantHypermorph sur une tuile OCCUPEE, une tuile a 2 hex
ou une tuile NON MARCHABLE. Tous refuses par
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`.

Le montage (geometrie DRIVEE : caster au contact d'un ennemi, allie au contact, ennemis hors
contact ; pour 1047 le porteur SUMMON est amene en bataille en castant d'abord ScarabHive) et les
cinq lectures du port vivent dans `scripts/python/probe_250_summon_targeting.py` -- le probe MESURE,
ces tests GARDENT, une seule implementation. Lit l'etat LIVE, aucune RVA ni tuile hardcodee,
ASCII only.
"""
from __future__ import annotations

import pytest

import probe_250_summon_targeting as P
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting_rule import TargetingRule as TR

BOARD = "MC1_67"
SEED = "777"

# `regimes` = les codes de refus NATIFS que le montage DOIT produire pour cette ability. Sans eux le
# test ne garderait qu'un demi-masque (un `range` oublie, ou un bit de camp oublie, passerait
# inapercu parce que toutes les lignes rendraient 0).
CAS = {
    P.SCARAB_HIVE:       {"regimes": (int(TR.TargetIsEnemy), int(TR.TargetIsInRange)),
                          "attack_type": 1, "rules": 0x4020},
    P.GETEMRUNTZ:        {"regimes": (int(TR.TargetIsInRange),),
                          "attack_type": 2, "rules": 0x8004},
    P.SCARAB_SUMMON:     {"regimes": (int(TR.TargetIsInRange),),
                          "attack_type": 2, "rules": 0x208000},
    P.MASTER_TUTELARIES: {"regimes": (int(TR.TargetTileIsFree), int(TR.TargetIsInRange),
                                      int(TR.ValidRequest)),
                          "attack_type": 2, "rules": 0x1040},
    P.ABERRANT:          {"regimes": (int(TR.TargetTileIsFree), int(TR.TargetIsInRange),
                                      int(TR.ValidRequest)),
                          "attack_type": 2, "rules": 0x1040},
}


def _verifie(aid: int, res: dict):
    cas = CAS[aid]
    rows = res["rows"]

    # 0) garde anti-confusion : au moins une cible ACCEPTEE par le natif -> l'ability n'est pas
    #    court-circuitee par `CanCurrentlyBeUsed` et les refus mesures viennent bien de la cascade.
    assert any(r["nat"] == 0 for r in rows), \
        "aucune cible acceptee par le natif -> les refus ne prouvent rien"

    # 1) accord natif / port APRES sur TOUTES les lignes. C'EST CETTE ASSERTION qui tombe quand
    #    `TARGETING_OPTIONS` disparait : le port rend 0 la ou le natif refuse.
    desaccords = [(r["label"], hex(r["nat"] or 0), hex(r["apres"]))
                  for r in rows if r["nat"] != r["apres"]]
    assert not desaccords, "desaccord natif/port : %s" % desaccords

    # 2) le masque SERT : au moins une ligne ou le natif REFUSE et ou `master` rendait 0.
    assert res["gain"] > 0, ("aucune ligne ou le masque change le verdict -> ce test ne garderait "
                             "rien (il passerait aussi sans `TARGETING_OPTIONS`)")

    # 3) TOUS les regimes de refus attendus sont exerces par le montage.
    vus = {r["nat"] for r in rows}
    manquants = [hex(x) for x in cas["regimes"] if x not in vus]
    assert not manquants, ("regimes de refus non exerces par le montage (le test garderait un demi "
                           "masque) : %s" % manquants)

    # 4) le volet CASTER non porte est INERTE ici -- verifie, pas suppose.
    assert all(c == res["port_caster"] for c in res["caster_nat"]), (
        "casterReason natif != port -> une regle CASTER non portee mord et cree un desaccord : "
        "natif=%s port=%s" % (res["caster_nat"], hex(res["port_caster"])))

    # 5) les DONNEES du registre : le litteral du masque ET l'`AbilityAttackType` du 3e argument de
    #    `AActiveAbility..ctor`. 1007 est le SEUL des cinq a valoir `SummonAndAttackTarget` (1).
    assert int(ABILITY_CLASSES[aid].TARGETING_OPTIONS.rules) == cas["rules"]
    assert int(ABILITY_ATTACK_TYPE[aid]) == cas["attack_type"]


@pytest.mark.parametrize("aid", sorted(CAS))
def test_summon_targeting_mask_matches_native(host, live_session, aid):
    """Le gate de cible porte == `TargetingQuery.GetInvalidTargetReason` natif, et il REFUSE des
    casts que `master` (sans masque) acceptait."""
    res = P.run_one(live_session, aid, SEED, BOARD)
    _verifie(aid, res)


def test_contrefactuel_range_porte_ses_refus(host, live_session):
    """CONTREFACTUEL sur le champ le plus discriminant du lot : les CINQ masques portent un
    `TargetingRange` (RANGE_ADJACENT ou RANGE_SELF), et c'est lui qui refuse le plus de lignes.
    Prive de son `TargetingRange`, le masque doit faux-accepter -- sinon la portee serait
    decorative et l'oublier ne se verrait nulle part.

    Exerce sur AberrantHypermorph (1166) : cast TILE-TARGET `RANGE_ADJACENT`, ou le volet portee
    couvre a lui seul toutes les tuiles a d >= 2 du plateau."""
    res = P.run_one(live_session, P.ABERRANT, SEED, BOARD)
    _verifie(P.ABERRANT, res)
    assert res["cf"]["sansRange"] > 0, (
        "retirer le `TargetingRange` ne change AUCUN verdict -> la portee est decorative")
    assert res["cf"]["sansRules"] > 0, (
        "retirer `rules` ne change AUCUN verdict -> le masque de 1166 serait decoratif")
