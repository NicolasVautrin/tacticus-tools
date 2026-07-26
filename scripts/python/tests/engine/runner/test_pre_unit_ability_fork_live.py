"""#120 — `On(PreUnitAbility = 0x2b)` part-il de la voie ABILITY comme de la voie NORMALE ?
CONFRONTE AU LIVE.

Le natif n'a qu'UN site d'emission : `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
(`FUN_180026490(0x4d, .., 0x2b)` en tete, avant l'execution) -- et l'attaque NORMALE emprunte cette
MEME operation (elle EST une active ability,
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility`). Le port a DEUX portes
d'operation (`DamageHandler.visit_AttackUnitMessage`, `AbilityHandler.visit_ActiveAbilityMessage`) ;
tant qu'une seule emettait, `SwornProtector` etait MUET face a une ability adverse.

CE QUE CES TESTS PROUVENT (pas « le code est atteint ») -- un ECART D'OBSERVABLE entre DEUX casts sur
le MEME board, le MEME seed, la MEME geometrie, tous deux appliques sur Creed :

  * `test_attack_ability_wakes_sworn_protector_live` : `JakhalStimms` (1131) fait apparaitre Kell ;
  * `test_others_ability_does_not_wake_sworn_protector_live` : `GauntletsOfUltramar` (1000) BLESSE
    Creed et ne fait PAS apparaitre Kell.

L'ecart n'est donc PAS « l'ability fait des degats » mais la CLASSE de l'ability : le 3e argument de
`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` (champ +0x68, lu par
`AActiveAbility$$HasAttackType`) vaut 0 `DirectTargetAttack` pour 1131 et 2 `Others` pour 1000, et
`SwornProtectorAbility$$CreateTrigger` exige `AbilityHasAttackType(@0x130, 0) | ...(@0x130, 1)`.

DISCIPLINE DE MESURE : la cible d'un cast est prise dans `abilityTargets(...).fromHere` (JAMAIS
`targets`) -- un cast REFUSE pour cible illegale rend le meme observable qu'une ability inerte
(`mutated=false`, 2 evenements, groupe 12). Et c'est le CASTER qui approche : faire entrer Creed dans
la portee d'un overwatch declencherait un tir gratuit = une attaque NORMALE, qui reveillerait
SwornProtector par l'autre voie et contaminerait la mesure.

ASCII-only. Skip si pas de session live.
"""
from __future__ import annotations

import pytest

import hexgeo

CREED_VIS = "astraCreed"
KELL_VIS = "astraSmnKell"
BOARD = "MC1_67"
SEED = "4242"
# `JakhalStimms` -- IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$.ctor
# -> `AActiveAbility..ctor(this, &opts, 0)` = AbilityAttackType.DirectTargetAttack
ATTACK_CASTER, ATTACK_ABILITY = "worldJakhal", 1131
# `GauntletsOfUltramar` -- ...GauntletsOfUltramarAbility$$.ctor -> `(.., 2)` = Others
OTHERS_CASTER, OTHERS_ABILITY = "ultraCalgar", 1000


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _by_vis(units, vis):
    return [u for u in units if u.get("visualId") == vis]


class _Drv:
    """Pilotage RPC des DEUX camps (`applyAction` ne verifie pas la propriete)."""

    def __init__(self, rpc, rid):
        self.rpc, self.rid = rpc, rid

    def units(self):
        return (self.rpc("decisionView", {"runnerId": self.rid, "allAbilities": True}, 90)
                or {}).get("units") or []

    def act(self, action, timeout=120):
        return self.rpc("applyAction", {"runnerId": self.rid, "action": action}, timeout) or {}

    def from_here(self, caster, ability):
        """Cibles LEGALES SANS BOUGER pour `ability` -- la seule liste exploitable (cf. en-tete)."""
        tg = self.rpc("abilityTargets",
                      {"runnerId": self.rid, "unitId": caster, "abilityType": ability}, 60) or {}
        for u in tg.get("units") or []:
            if u.get("unitId") == caster:
                for a in u.get("abilities") or []:
                    if int(a.get("abilityId") or -1) == ability:
                        return [t.get("targetId") for t in (a.get("fromHere") or [])]
        return []


def _scenario(rpc, build_runner, caster_vis, ability):
    """Monte un runner NEUF (SwornProtector est one-shot par bataille), amene le CASTER au contact de
    Creed sans jamais deplacer Creed, puis caste `ability` sur lui. Rend l'etat avant/apres."""
    rid = build_runner(SEED, extra=["--p-units", CREED_VIS,
                                    "--a-units", caster_vis + ",necroWarden",
                                    "--hp-player", "400000", "--hp-target", "400000"],
                       board=BOARD)["rid"]
    drv = _Drv(rpc, rid)
    us = drv.units()
    creed = (_by_vis(us, CREED_VIS) or [{}])[0].get("id")
    caster = (_by_vis(us, caster_vis) or [{}])[0].get("id")
    if creed is None or caster is None:
        pytest.skip("roster live incomplet")
    drv.act({"kind": "endturn"})                       # la main passe au camp du caster
    tiles = [(c, r) for c in range(0, 7) for r in range(0, 9)]
    for _ in range(10):
        us = drv.units()
        cp = _pos([u for u in us if u["id"] == creed][0])
        sp = _pos([u for u in us if u["id"] == caster][0])
        if _by_vis(us, KELL_VIS):
            pytest.skip("Kell apparu avant le cast -> scenario contamine")
        if creed in drv.from_here(caster, ability):
            break
        for t in sorted([t for t in tiles if 0 < hexgeo.distance(t, sp) <= 3],
                        key=lambda t: hexgeo.distance(t, cp)):
            drv.act({"kind": "move", "unitId": caster, "to": {"col": t[0], "row": t[1]}})
            if _pos([u for u in drv.units() if u["id"] == caster][0]) != sp:
                break
        else:
            pytest.skip("caster bloque")
    else:
        pytest.skip("cible jamais legale sans bouger")
    before = drv.units()
    res = drv.act({"kind": "ability", "casterId": caster, "targetId": creed,
                   "abilityType": ability})
    return {"drv": drv, "creed": creed, "caster": caster, "before": before,
            "after": drv.units(), "res": (res.get("actions") or [{}])[0]}


@pytest.fixture(scope="module")
def attack_cast(rpc, build_runner):
    return _scenario(rpc, build_runner, ATTACK_CASTER, ATTACK_ABILITY)


@pytest.fixture(scope="module")
def others_cast(rpc, build_runner):
    return _scenario(rpc, build_runner, OTHERS_CASTER, OTHERS_ABILITY)


def test_attack_ability_wakes_sworn_protector_live(attack_cast):
    """ORACLE du de-fork : un cast d'ability CLASSEE ATTAQUE (`JakhalStimms`, ctor arg 0) sur Creed
    fait apparaitre Kell -- donc le natif emet bien `On(0x2b)` sur la voie ABILITY, pas seulement sur
    la voie d'attaque normale."""
    assert attack_cast["res"].get("mutated"), (
        "cast non applique (mutated=false) -> cible illegale, mesure non concluante")
    kell = _by_vis(attack_cast["after"], KELL_VIS)
    assert kell, "Kell n'est PAS apparu sur un cast d'ability offensive ciblant Creed"


def test_attack_ability_switches_creed_live(attack_cast):
    """`SwornProtector_Protect` : Kell prend la place de Creed AVANT que l'ability ne resolve, donc
    Creed ressort de l'ability a PV PLEINS alors qu'il en etait la cible.

    Ce test mesure le LIVE. Le port, lui, ne reproduit PAS encore le second membre (Creed intact) :
    il lui manque la RE-RESOLUTION DE CIBLE que `ActiveAbilityOperation$$ExecuteInternal` enchaine
    apres le vecteur (`ExecuteForReplacedTarget`) -- residu NOMME, symetrique sur les deux voies et
    anterieur a #120, decrit en tete de `triggers/loki/sworn_protector.py` et mesure par
    `probe_120_pre_unit_ability_fork.py`."""
    creed_id = attack_cast["creed"]
    before = [u for u in attack_cast["before"] if u["id"] == creed_id][0]
    after = [u for u in attack_cast["after"] if u["id"] == creed_id][0]
    kell = _by_vis(attack_cast["after"], KELL_VIS)
    if not kell:
        pytest.skip("pas de Kell (couvert par le test precedent)")
    assert _pos(after) != _pos(before), "Creed n'a pas bouge -> pas de SwitchPosition"
    assert after.get("hp") == before.get("hp"), (
        "Creed a encaisse (hp %s -> %s) alors que Kell devait prendre le coup"
        % (before.get("hp"), after.get("hp")))


def test_others_ability_does_not_wake_sworn_protector_live(others_cast):
    """CONTRE-CAS DISCRIMINANT : `GauntletsOfUltramar` (ctor arg 2 = `Others`) BLESSE Creed et ne
    reveille PAS SwornProtector. Ce n'est donc pas « faire des degats » qui compte mais
    `AbilityHasAttackType(@0x130, 0) | ...(@0x130, 1)` -- sans ce gate, le de-fork de #120 ferait
    apparaitre Kell ici aussi."""
    assert others_cast["res"].get("mutated"), (
        "cast non applique -> le contre-cas ne prouve rien")
    creed_id = others_cast["creed"]
    hp0 = [u for u in others_cast["before"] if u["id"] == creed_id][0].get("hp")
    hp1 = [u for u in others_cast["after"] if u["id"] == creed_id][0].get("hp")
    assert hp1 < hp0, f"Creed n'a pas ete blesse ({hp0} -> {hp1}) -> contre-cas non discriminant"
    assert not _by_vis(others_cast["after"], KELL_VIS), (
        "Kell est apparu sur une ability classee Others -> AbilityHasAttackType n'est pas porte")


def test_port_reproduces_both_verdicts_offline():
    """Le PORT rejoue les DEUX verdicts live (attaque -> Kell ; `Others` -> degats mais pas de Kell),
    plus le gate `IsNormalAttack` d'AnvilShield et la non-regression de la voie normale.
    ECHOUE sur master : le vecteur n'y part pas de `AbilityHandler.visit_ActiveAbilityMessage`."""
    import importlib
    probe = importlib.import_module("probe_120_pre_unit_ability_fork")
    assert probe.main() == 0
