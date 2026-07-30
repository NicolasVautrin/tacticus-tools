"""#120 — `On(PreUnitAbility = 0x2a)` part-il de la voie ABILITY comme de la voie NORMALE ?
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
# GENERALISATION #120bis : ability MONO-CIBLE (`FlailSwing`, 3x Power melee, ctor arg 0), AUTRE board
# et AUTRE seed -> « Creed intact » n'y mesure QUE la re-resolution de cible (aucun volet AoE).
MONO_CASTER, MONO_ABILITY = "deathBlightlord", 1042
MONO_BOARD, MONO_SEED = "C3_26", "31337"


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

    def observed(self):
        """`observeBattle` — la SEULE vue qui publie `hpMax` (`decisionView` ne rend que `hp`)."""
        return (self.rpc("observeBattle", {"runnerId": self.rid}, 40) or {}).get("units") or []

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


def _scenario(rpc, build_runner, caster_vis, ability, board=BOARD, seed=SEED):
    """Monte un runner NEUF (SwornProtector est one-shot par bataille), amene le CASTER au contact de
    Creed sans jamais deplacer Creed, puis caste `ability` sur lui. Rend l'etat avant/apres."""
    rid = build_runner(seed, extra=["--p-units", CREED_VIS,
                                    "--a-units", caster_vis + ",necroWarden",
                                    "--hp-player", "400000", "--hp-target", "400000"],
                       board=board)["rid"]
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
            "after": drv.units(), "observed": drv.observed(),
            "res": (res.get("actions") or [{}])[0]}


@pytest.fixture(scope="module")
def attack_cast(rpc, build_runner):
    return _scenario(rpc, build_runner, ATTACK_CASTER, ATTACK_ABILITY)


@pytest.fixture(scope="module")
def others_cast(rpc, build_runner):
    return _scenario(rpc, build_runner, OTHERS_CASTER, OTHERS_ABILITY)


@pytest.fixture(scope="module")
def mono_target_cast(rpc, build_runner):
    """GENERALISATION (#120bis) : MEME verdict, mais ability MONO-CIBLE et AUTRE board/seed.
    `JakhalStimms` porte un volet AoE (`AdjacentUnits(caster) & AdjacentFriends(target)`) qui peut
    atteindre Creed depuis sa NOUVELLE tuile : « Creed a-t-il encaisse ? » y depend de la geometrie.
    `FlailSwing` (1042, `deathBlightlord`) est 3x Power melee MONO-CIBLE -> l'ABILITY ne peut rien
    eclabousser.

    Le CASTER, lui, en est capable : `deathBlightlord` porte `HazeOfCorruption`, qui bonde
    `Damageable(AdjacentEnemies(Self@0x148) & AdjacentFriends(Target@0x178))` (effet 0x435 = 1077,
    `HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`) et lui reporte, a la mort de la cible,
    les `LeftOverDamage` enregistrees par `IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit`
    (case-207/209). Creed, apres le switch, est TOUJOURS `AdjacentFriends(Kell)` -- il ne sort du pool
    que parce qu'il n'est PAS adjacent au caster. C'est ce que produit
    `SwornProtectorAbility$$GetSpawnTile` (Kell apparait du cote OPPOSE a l'attaquant), et le test
    l'ASSERTE desormais au lieu de le supposer : sans cette garde, « Creed intact » confondrait deux
    canaux. MESURE : `d(caster, creed) == 2` sur 3/3 montages live."""
    return _scenario(rpc, build_runner, MONO_CASTER, MONO_ABILITY, board=MONO_BOARD, seed=MONO_SEED)


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

    C'est l'ORACLE de la RE-RESOLUTION DE CIBLE : ce n'est pas le `SwitchPosition` qui epargne Creed
    (il ne fait que le deplacer) mais l'etage que `ActiveAbilityOperation$$ExecuteInternal` enchaine
    JUSTE APRES le vecteur -- `GetUnit(First(AbilityEntities@+0x38))` puis re-entree
    `ExecuteForReplacedTarget` -> `Execute` sur l'occupant courant de la tuile visee. Porte en
    #120bis sur les DEUX voies (`engine/runner/operations/active_ability.py`) ; le port rejoue ce
    verdict dans `probe_120bis_execute_for_replaced_target.py`."""
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


def test_mono_target_cast_hits_kell_not_creed_live(mono_target_cast):
    """GENERALISATION du verdict de re-resolution, SANS confond AoE et sur un AUTRE board/seed :
    `FlailSwing` (mono-cible) sur Creed -> Kell apparait, echange, encaisse (PV < max) et Creed
    ressort a PV STRICTEMENT inchanges. C'est le critere binaire du port cote LIVE : « qui encaisse
    apres le switch ». Le port rejoue exactement ce couple dans
    `probe_120bis_execute_for_replaced_target.py` (etape 2)."""
    assert mono_target_cast["res"].get("mutated"), (
        "cast non applique (mutated=false) -> cible illegale, mesure non concluante")
    creed_id = mono_target_cast["creed"]
    before = [u for u in mono_target_cast["before"] if u["id"] == creed_id][0]
    after = [u for u in mono_target_cast["after"] if u["id"] == creed_id][0]
    kell = _by_vis(mono_target_cast["after"], KELL_VIS)
    assert kell, "Kell n'est PAS apparu -> le scenario ne mesure pas la re-resolution"
    assert _pos(after) != _pos(before), "Creed n'a pas bouge -> pas de SwitchPosition"
    # GARDE DE MESURE (cf. la docstring de la fixture) : hors du pool `AdjacentEnemies(Self)`, donc
    # hors du canal de report `HazeOfCorruption`. Si cette distance tombait a 1, « Creed intact »
    # cesserait de mesurer la re-resolution -- il faudrait alors la mesurer par montant, comme le
    # fait l'etape 9 de `probe_120bis_execute_for_replaced_target.py`.
    caster_after = [u for u in mono_target_cast["after"]
                    if u["id"] == mono_target_cast["caster"]][0]
    assert hexgeo.distance(_pos(caster_after), _pos(after)) > 1, (
        "Creed (%s) est ADJACENT au caster (%s) -> il est relais `HazeOfCorruption` et le verdict "
        "« Creed intact » confond deux canaux" % (_pos(after), _pos(caster_after)))
    assert after.get("hp") == before.get("hp"), (
        "Creed a encaisse un cast MONO-CIBLE (hp %s -> %s) : les degats ne sont pas partis sur Kell"
        % (before.get("hp"), after.get("hp")))
    # `hpMax` n'existe que dans `observeBattle` (cf. `_Drv.observed`) : c'est LUI qui donne le
    # « Kell a encaisse » sans avoir a connaitre les PV d'un Kell frais.
    # `decisionView.id` == `observeBattle.squadId` (meme entite de squad ; `entityId` y est un AUTRE
    # champ). C'est aussi `observeBattle` qui porte `isDead` (decisionView garde les cadavres).
    kid = kell[0]["id"]
    ko = [u for u in mono_target_cast["observed"] if u.get("squadId") == kid]
    assert ko, "Kell absent d'observeBattle (squadId=%s)" % kid
    k = ko[0]
    assert k.get("hpMax"), "hpMax non publie -> l'assertion « Kell a encaisse » n'est pas montable"
    assert k.get("isDead") or k["hp"] < k["hpMax"], (
        "Kell n'a rien encaisse (hp=%s / max=%s, isDead=%s) -> le coup est parti ailleurs"
        % (k.get("hp"), k.get("hpMax"), k.get("isDead")))


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


def test_port_reproduces_replaced_target_offline():
    """#120bis — le PORT rejoue le verdict « Creed INTACT, c'est Kell qui encaisse » mesure live par
    les DEUX tests de switch ci-dessus (voie CAST) et par
    `test_sworn_protector_kell_live::test_sworn_protector_switches_position_live` (voie NORMALE),
    ET les contre-cas qui prouvent que la re-resolution n'est pas inconditionnelle.

    ECHOUE sur master (`ExecuteForReplacedTarget` non porte : Creed encaissait sur les deux voies).
    Le probe couvre : voie normale avec switch / voie cast MONO-CIBLE avec switch / Creed taunte
    (`CanSwitchPosition` faux -> spawn SANS switch, la cible d'origine encaisse, sur les 2 voies) /
    cible sans SwornProtector (2 voies) / ability `Others` / cible morte (`Count(targetTiles) > 0`
    protege les casts sur cadavre) / structure de la re-entree (`On(0x2b)` re-emis, flags de tour
    poses une seule fois) / 2e coup pris en charge par `SwornProtector_Protect`."""
    import importlib
    probe = importlib.import_module("probe_120bis_execute_for_replaced_target")
    assert probe.main() == 0
