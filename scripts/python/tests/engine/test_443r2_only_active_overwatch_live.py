"""#443-r2 -- le parametre `onlyActive` de `HasEffect` EST discrimine par la mesure.

Le residu disait : « basculer `onlyActive` ne deplace RIEN dans le montage retenu ». La cause n'etait
PAS que le parametre soit mort -- c'etait que le montage n'atteignait pas son regime. Un `HasEffect`
ne peut differer entre `onlyActive` faux et vrai que si l'entite PORTE un effet du type demande dont
`EffectComponent.IsActive @+0x5c` est FAUX (`IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect`
n'a que cette lecture conditionnelle ; `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffect` exige
`+0x5c` INCONDITIONNELLEMENT, il est deja active-only dans les deux regimes).

CE REGIME S'ATTEINT EN UN `endturn`. `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$
CreateHandleTriggerAbilitiesInternal` rend un `Triggered(On(TurnStart_EffectActivation = 0x12) &
IsTurnOf(owner@0x148) -> DeactivateEffect)` : **pendant le tour de son porteur, l'overwatch (1009) est
present et INERTE**.

CE QUE CE TEST GARDE, sur les DEUX regimes :

  1. CONFORMITE -- `pairUtility` natif == port, overwatch ACTIF comme INERTE. Le port est seede par
     le canal `includeInactive` (`runner/snapshot.py::decision_view_seed_body`), le seul qui publie
     l'instance inerte.
  2. DISCRIMINANCE -- le substrat `battle_query.scene_has_effect` mute de `EffectsState.has_effect`
     (mirror d'`onlyActive` FAUX) vers `EffectsState.active_effects` (mirror d'`onlyActive` VRAI) :
     le terme DOIT tomber du poids BC en regime INERTE, et ne DOIT rien deplacer en regime ACTIF.
     Sans ces deux assertions, le test serait incapable d'echouer sur un port qui confond les deux
     substrats -- et c'est exactement l'etat dans lequel la contre-epreuve `CE3` de #443 etait.
  3. CANAL DE SEED -- l'ecart MESURE de la face DECISION (residu `#443-r2-b1`) : seede par le canal
     par DEFAUT, elle ne voit pas l'instance inerte. Le test garde le MECANISME (l'ecart vaut
     EXACTEMENT le poids, jamais autre chose), pas le bug : le jour ou le canal bascule, l'ecart
     passe a zero et l'assertion reste vraie.
  4. LE SECOND CALL-SITE, OFFLINE -- `EarlyWarningOverrideHitReductionPurge.matches` porte le
     litteral OPPOSE (`onlyActive=1`) sur le MEME effectType. Confronte au natif il exigerait un
     kill en overwatch (cf. la case-doc, NON CONFRONTE) ; sa SENSIBILITE au flag, elle, se garde
     offline et sans runner.

Le montage EXIGE les deux regimes : s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268).

Porteurs : `emperNoiseMarine` (trait `SuppressiveFire` 1010 -> triggered 1044), HERO au pool ;
`eldarRanger` (trait `Overwatch` -> effet 1009 sur elle-meme). ASCII only.
Probe jumeau : `scripts/python/probe_443r2_only_active_overwatch.py`.
"""
from __future__ import annotations

import pytest

import probe_443r2_only_active_overwatch as P

EPS = P.EPS


@pytest.fixture(scope="module")
def ow_case(live_session, rpc, build_runner):
    """UN runner, les deux unites placees a distance (le terme natif est NIE au contact), puis les
    DEUX regimes mesures sur le MEME etat : overwatch ACTIF (tour du caster), puis INERTE (tour du
    porteur, apres un `endturn`)."""
    rid = build_runner(P.SEED, ["--board", P.BOARD, "--p-units", P.CASTER,
                                "--a-units", P.TARGET,
                                "--hp-target", "90000", "--hp-player", "90000"])["rid"]
    try:
        case = P._stage(live_session, rpc, rid)
        a = P.measure(rpc, case, "A-actif")
        if not a["ow"]["actif"]:
            pytest.fail(f"montage DEGENERE : regime A sans overwatch ACTIF -- {a['ow']}",
                        pytrace=False)
        r = rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120) or {}
        if not r.get("ok"):
            pytest.fail(f"montage NON INSTALLE : endturn refuse -- {r}", pytrace=False)
        b = P.measure(rpc, case, "B-inactif")
        if not (b["ow"]["present"] and not b["ow"]["actif"]):
            pytest.fail("montage DEGENERE : le regime B n'est pas PRESENT-mais-INACTIF -- "
                        f"{b['ow']}", pytrace=False)
    except P.MontageError as e:
        pytest.fail(f"montage NON INSTALLE : {e}", pytrace=False)
    poids = a["defaut"]["poids"]
    if not poids:
        pytest.fail(f"le BC servi porte {P.KEY}={poids} -- un poids nul ne discrimine rien",
                    pytrace=False)
    return {"rid": rid, "case": case, "A": a, "B": b, "poids": float(poids)}


def test_le_natif_voit_un_overwatch_INERTE(ow_case):
    """(1a) `onlyActive` faux, CONFIRME PAR MESURE et non par lecture seule : l'oracle natif verse
    le meme terme sur un overwatch ARME et sur un overwatch INERTE."""
    a, b = ow_case["A"], ow_case["B"]
    assert abs(a["native"] - b["native"]) < EPS, (
        "le terme natif ne doit PAS dependre du flag `IsActive` (`onlyActive` est FAUX au "
        f"call-site) : actif={a['native']} inerte={b['native']}")
    assert b["includeInactive"]["leaf"] > 0, (
        "regime DEGENERE : le terme est nul meme en regime ACTIF, rien ne serait discrimine")


def test_le_port_suit_le_natif_dans_les_deux_regimes(ow_case):
    """(1b) CONFORMITE, sur le canal de seed qui publie les instances inertes."""
    for r in (ow_case["A"], ow_case["B"]):
        assert abs(r["includeInactive"]["port"] - r["native"]) < EPS, (
            f"[{r['regime']}] pairUtility port != natif : natif={r['native']} "
            f"port={r['includeInactive']['port']} ecart={r['includeInactive']['port'] - r['native']}")


def test_la_mutation_du_substrat_MORD_sur_un_overwatch_inerte(ow_case):
    """(2) DISCRIMINANCE. Critere = DEPLACEMENT par rapport au port NON MUTE, jamais l'ecart au
    natif. `has_effect` -> `active_effects` = ce que le port ferait si le litteral valait 1."""
    poids = ow_case["poids"]
    b = ow_case["B"]["includeInactive"]
    dep = b["muted_leaf"] - b["leaf"]
    assert abs(dep + poids) < EPS, (
        "[INERTE] basculer le substrat sur `active_effects` DOIT faire perdre exactement le poids "
        f"{poids} : terme={b['leaf']} mute={b['muted_leaf']} deplacement={dep}")


def test_la_mutation_ne_deplace_RIEN_sur_un_overwatch_arme(ow_case):
    """(2bis) Le contre-cas qui prouve que la mutation n'est pas un interrupteur aveugle : sur un
    effet ACTIF, les deux substrats coincident -- c'est POURQUOI `CE3` de #443 etait muette."""
    for canal in ("defaut", "includeInactive"):
        a = ow_case["A"][canal]
        assert abs(a["muted_leaf"] - a["leaf"]) < EPS, (
            f"[ACTIF/{canal}] la mutation ne doit RIEN deplacer : terme={a['leaf']} "
            f"mute={a['muted_leaf']}")


def test_le_canal_de_seed_par_defaut_ne_peut_que_PERDRE_le_poids(ow_case):
    """(3) Residu `#443-r2-b1`. Le canal par DEFAUT droppe les instances inertes, donc la face
    DECISION qui s'en seede ne voit pas ce que le natif voit. Le test garde le MECANISME : l'ecart
    au natif vaut 0 ou EXACTEMENT le poids -- jamais une troisieme valeur. Il reste vrai quand le
    canal bascule (l'ecart passe a 0), et rougirait sur toute autre derive."""
    poids = ow_case["poids"]
    for r in (ow_case["A"], ow_case["B"]):
        ecart = r["defaut"]["port"] - r["native"]
        assert abs(ecart) < EPS or abs(ecart + poids) < EPS, (
            f"[{r['regime']}] l'ecart du canal par defaut doit valoir 0 ou -{poids} : "
            f"natif={r['native']} port={r['defaut']['port']} ecart={ecart}")
    # Et l'ecart n'est PAS symetrique : il n'existe QUE dans le regime inerte.
    assert abs(ow_case["A"]["defaut"]["port"] - ow_case["A"]["native"]) < EPS, (
        "regime ACTIF : le canal par defaut publie l'instance, il ne doit y avoir aucun ecart")


def test_le_canal_de_PRODUCTION_separe_le_substrat_STRUCTURE_de_la_liste_BRUTE(ow_case, rpc):
    """(5) #443-r2-b1, sur un payload LIVE et en regime INERTE -- la seule forme de la garde qui ne
    peut PAS etre satisfaite par un dict synthetique.

    Depuis #443-r2-b1 la face DECISION capte par `decision_view_seed_body` (la porte du canal
    `includeInactive`, PARTAGEE avec le seed COMBAT). Ce que ce canal ajoute doit atterrir dans
    EXACTEMENT un endroit :

      * `scene.eff_state` (STRUCTURE, porteur du flag par instance) -> `has_effect` VOIT l'inerte,
        et c'est ce qui referme les 35 points ;
      * PAS dans `ctx.units[].effects` (la liste BRUTE), dont les lecteurs n'ont aucun flag a
        consulter : eux doivent rester INDEPENDANTS DU CANAL.

    Les deux moities sont assertees : sans la premiere le fix n'existe pas, sans la seconde il
    deplace des verdicts que personne n'a demandes."""
    case, tgt = ow_case["case"], ow_case["case"]["tgt"]
    ctx = P._ctx_for(rpc, case["rid"], case["cid"], seed_inactive=True)

    eff = getattr(getattr(ctx, "scene", None), "eff_state", None)
    assert eff is not None, "la Scene du contexte n'a pas d'EffectsState -- rien n'est mesurable"
    assert eff.has_effect(int(tgt), effect_type=P.OVERWATCH), (
        "le canal de PRODUCTION doit publier l'instance 1009 INERTE dans le substrat STRUCTURE : "
        "c'est la seule voie par laquelle un mirror d'`onlyActive = 0` la voit")
    actifs = [int(e.effect_type or -1) for e in eff.active_effects(int(tgt), {})]
    assert P.OVERWATCH not in actifs, (
        "l'instance INERTE ne doit contribuer a AUCUN nombre : `active_effects` doit la filtrer "
        f"(obtenu {actifs})")

    ligne = next((u for u in (ctx.units or []) if u.get("id") == tgt), None)
    assert ligne is not None, f"la cible u{tgt} est absente de `ctx.units`"
    bruts = [(e.get("effectType"), e.get("active")) for e in (ligne.get("effects") or [])]
    assert all(a is not False for _t, a in bruts), (
        "la liste BRUTE de `ctx.units` doit rester ACTIF-ONLY (projection "
        f"`snapshot.active_only_rows`) -- obtenu {bruts}")
    assert P.OVERWATCH not in [t for t, _a in bruts], (
        "l'instance 1009 INERTE a fuite dans la liste BRUTE : tout lecteur qui y mirroire un "
        "predicat ACTIVE-ONLY change de verdict EN SILENCE")


def test_le_call_site_onlyActive_VRAI_est_sensible_au_flag():
    """(4) `EarlyWarningOverrideHitReductionPurge.matches` -- l'autre call-site FLAG, litteral
    OPPOSE (`NOT HasEffect(Owner@0x148, 0x3f1, onlyActive=1, targetType=Both)`). 100 % OFFLINE :
    le meme etat, au seul flag `IsActive` de l'instance 1009 pres, doit donner des verdicts
    OPPOSES. Un port qui aurait lu `has_effect` ici serait INSENSIBLE -- et muet."""
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects_state import EffectsState
    from engine.runner.operations.triggers.loki.reactivate_overwatch import (
        EarlyWarningOverrideHitReductionPurge, EWO_HIT_REDUCTION, OVERWATCH_AUTO_ATTACK)
    from engine.runner.state import State
    from engine.runner.operations.triggers.base import TriggerEvent

    def _state(ow_actif: bool) -> State:
        st = State()
        eff = EffectsState()
        # L'effet a RETIRER : sans lui le natif no-ope aussi (gate << rien a retirer >>).
        eff.by_unit[1] = [
            BaseEffect(name="EarlyWarningOverride_HitReduction", effect_type=EWO_HIT_REDUCTION),
            BaseEffect(name="Overwatch_AutoAttack", effect_type=OVERWATCH_AUTO_ATTACK,
                       active=ow_actif),
        ]
        st.effects = eff
        return st

    trig = EarlyWarningOverrideHitReductionPurge.__new__(EarlyWarningOverrideHitReductionPurge)
    trig.owner_id = 1
    ev = TriggerEvent(event_id=int(trig.event_id), actor_id=1, target_id=1,
                      ranged=False, profile=None)
    verdicts = {actif: trig.matches(_state(actif), ev) for actif in (True, False)}
    assert verdicts == {True: False, False: True}, (
        "`NOT HasEffect(Owner, 1009, onlyActive=1)` doit rendre des verdicts OPPOSES selon le seul "
        f"flag `IsActive` de l'instance 1009 -- obtenu {verdicts}")
