"""case-haze-ord -- GARDE du couple ENQUEUE / DRAIN du pipeline de mort.

Critere (binaire) : au regime OVERKILL, le port emet-il le MEME nombre de `genrand_int32` que le
natif ? Mesure de reference AVANT correctif : natif 14, port 12 (`HazeOfCorruption` `k = 2`,
seed 777, board MC1_67, PV cible 1200).

Deux artefacts natifs, l'un ENQUEUE, l'autre DRAINE :

    IdunBattle.Operations.RecordKillOperation$$Execute
        -> UnitFlagsComponent.Add(dying, 0xf)              # PendingDeath
        -> IdunBattle.Core.MatchState$$AddDeath(killer, killed, killTrigger, attackTrigger, range)
        -> On(PendingDeathAdded = 3)
    IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths
        RunPhase(PhaseType.ProcessDeaths /*0xc*/) -> IdunBattle.Operations.KillUnitOperation$$Execute   # On(1)/(2)/(0)/(55)
                         `-> branche `else` de la garde `pendingRevive.HasValue` :
                             Core.Services.OperationProcessor$$ReviveUnit
                             -> IdunBattle.Operations.ReviveUnitOperation$$Execute
        RunPhase(PhaseType.ProcessRemovals /*0xd*/) -> <VerifyRemovedUnits>b__0   # les RETRAITS,
                      PAS le revive (#477-r24 ; cf. `engine/streams/phase_type.py`)

Le port collapsait les deux dans `AttackDamageOperation._fire_death_if_killed`, appelee a CHAQUE
`AttackDamage` : les N feuilles d'un `IdunBattle.Entities.Behaviours.AttackBehaviour` UNIQUE
voyaient la mort de leur cible AU MILIEU de la serie.

S'y ajoute le site (A) d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` :
`HasFlag(target, 8 = Overkilled)` -> `AddLeftoverHit(..., 1, 0)` puis **`return`** -- un coup porte
sur une cible deja overkillee n'emet RIEN (ni `On(0x39 = PreDamageTaken)`, ni `On(0xf)`, ni `On(0x10)`) et
n'applique rien. Le port emettait `On(0x10)`, donc un `Maybe(25)` d'`OnToxicDamageAbility` en trop.
"""
from __future__ import annotations

import pytest

PROBE = "probe_hazeord_death_queue"
# Seeds dont le pick met les DEUX relais en jeu et dont la chaine part au regime overkill.
SEEDS = ["777", "5", "21"]
HP_OVERKILL = 1200          # la cible meurt EN OVERKILL des le 1er coup d'arme (cellule [2087,3131])
# GENERALISATION : le meme montage a trois profondeurs d'overkill. Les regimes DISCRIMINANTS ne sont
# pas ceux ou le relais meurt du 1er report (leftovers = 4) mais ceux ou il meurt EN MILIEU de serie
# -- le port doit alors continuer la serie APRES la mort et le bond suivant lire exactement 3
# leftovers (natif 13 tirages, reports 4 + 3). Un port qui drainerait encore inline en lirait 1.
MATRIX = [(s, hp) for s in SEEDS for hp in (800, 1200, 2000)]


def _row(seed, hp=HP_OVERKILL, k=2):
    import importlib
    P = importlib.import_module(PROBE)
    rpc = P._mkrpc()
    r = P._run(rpc, seed, hp, 0, k)
    assert r is not None, "montage k=%s KO (seed %s hp %s)" % (k, seed, hp)
    return r


# --------------------------------------------------------------------------- OFFLINE (structure)

def test_l_etat_porte_la_file_de_morts_et_son_verrou():
    """`MatchState` tient la file remplie par `AddDeath` ; `VerifyDeaths` la draine. Le port doit
    materialiser les DEUX (la file et la non-reentrance), sinon il n'y a pas d'enqueue du tout."""
    from engine.runner.state import State
    st = State()
    assert st.pending_deaths == []
    assert st.draining_deaths is False


def test_la_file_porte_le_declencheur_du_kill():
    """`MatchState$$AddDeath(killer, killed, **killTrigger**, attackTrigger, AttackRangeType)` : le
    declencheur est LU A L'ENQUEUE et rejoue par `KillUnitOperation` dans l'`AbilityEntities+0x138`
    des evenements de mort -- c'est lui que comparent `TriggeringAbilityIs`/`TriggeringEffectIs`.
    Sans cette capture, une mort causee DANS le behaviour d'une triggered-ability (le report 1077)
    serait drainee hors de ce behaviour et perdrait son declencheur."""
    from engine.runner.state import State
    from engine.runner.operations.damage import AttackDamageOperation
    st = State()
    st.triggering_ability = 0x435
    AttackDamageOperation._add_death(st, 7, 3, True)
    assert st.pending_deaths == [(7, 3, True, 0x435, None)]


def test_la_file_porte_l_attack_range_type_de_la_mort():
    """`MatchState$$AddDeath(killer, killed, killTrigger, attackTrigger, **AttackRangeType**)` : le
    CINQUIEME argument (#951-r1). Il devient `KillUnitOptions+0x3c`, dont
    `IdunBattle.Operations.KillUnitOperation$$Execute` derive
    `inMelee = HasValue && GetValueOrDefault() == Melee(1)` -- l'octet qu'il ecrit sur la VICTIME
    (`UnitComponent+0x178`) ET qu'il passe a `RegisterDefeatedUnit` sur le TUEUR.

    Le champ est OPTIONNEL a l'enqueue et `None` par defaut : les voies dont les `KillUnitOptions`
    laissent `+0x3c` a zero (`$$ForSteppable` du crush, `$$ForDefault` de la feuille DSL `Kill`)
    passent un `Nullable` VIDE cote natif aussi."""
    from engine.runner.state import State
    from engine.runner.operations.damage import AttackDamageOperation
    st = State()
    AttackDamageOperation._add_death(st, 7, 3, False, attack_range_type="Melee")
    assert st.pending_deaths == [(7, 3, False, None, "Melee")]
    st2 = State()
    AttackDamageOperation._add_death(st2, 7, 3, False)
    assert st2.pending_deaths == [(7, 3, False, None, None)], (
        "sans mesure, le 5e champ est None -- jamais un 'Melee' fabrique")


def test_le_drain_est_non_reentrant():
    """`VerifyDeaths` traite UNE mort a la fois ; une mort enqueuee PENDANT le drain attend son tour
    de boucle. Appele alors qu'un drain tourne, il ne doit RIEN faire."""
    from engine.runner.state import State
    from engine.runner.operations.damage import AttackDamageOperation
    st = State()
    st.draining_deaths = True
    AttackDamageOperation._add_death(st, 7, 3, False)
    assert AttackDamageOperation._verify_deaths(st) == []
    assert len(st.pending_deaths) == 1, "la mort reste EN FILE, elle n'est ni perdue ni appliquee"


def test_une_mort_causee_pendant_une_mort_est_traitee_APRES_elle(monkeypatch):
    """LE test d'ordonnancement. `KillUnitOperation$$Execute` de A declenche un behaviour qui tue B
    (death-nova, riposte `FinalJustice`, report `HazeOfCorruption`) : le natif ENQUEUE B et ne le
    traite qu'au tour de boucle SUIVANT de `VerifyDeaths`. Le port appliquait la mort de B en
    plein milieu de la sequence de A."""
    from engine.runner.state import State
    from engine.runner.operations.damage import AttackDamageOperation
    st = State()
    trace = []

    def _fake_kill(state, dying_id, killer_id, overkill, attack_range_type=None):
        trace.append(("kill", dying_id))
        if dying_id == 1:                       # la sequence de mort de 1 en TUE un autre
            AttackDamageOperation._add_death(state, 2, 1, False)
            trace.append(("enqueue", 2))
        return []

    monkeypatch.setattr(AttackDamageOperation, "_kill_unit_operation", staticmethod(_fake_kill))
    AttackDamageOperation._add_death(st, 1, 9, False)
    AttackDamageOperation._verify_deaths(st)
    assert trace == [("kill", 1), ("enqueue", 2), ("kill", 2)], (
        "la mort imbriquee doit suivre la sequence en cours, pas s'y inserer -- trace %s" % (trace,))
    assert st.pending_deaths == [], "la file doit etre videe par le drain"


def test_la_file_ne_double_pas_une_meme_mort():
    """Gate `UnitFlagsComponent.Has(dying, 6)` de `RecordKillOperation$$Execute` : une unite deja
    enregistree ne repasse pas. Entre l'enqueue et le drain, la cible reste JOIGNABLE."""
    from engine.runner.state import State
    from engine.runner.operations.damage import AttackDamageOperation
    st = State()
    AttackDamageOperation._add_death(st, 7, 3, False)
    AttackDamageOperation._add_death(st, 7, 4, True)
    assert st.pending_deaths == [(7, 3, False, None, None)]


def test_un_coup_sur_une_cible_deja_overkillee_n_applique_ni_n_emet_rien():
    """SITE (A) d'`ApplyDamageOperation$$Execute` : `HasFlag(target, 8)` -> `AddLeftoverHit` puis
    `return`. La `LeftOverDamage` est poussee (base nominale), mais AUCUN PV n'est mute et AUCUN
    des trois evenements (`0x3a` / `0xf` / `0x10`) ne part."""
    from engine.runner.state import State
    from engine.runner.components import (HealthComponent, UnitComponent, UnitFlagsComponent)
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.left_over_damage import left_over_damages
    st = State()
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id="astraBullgryn", alive=False))
    hc = e.add_component(HealthComponent(hp=0, hp_max=1200))
    fl = e.add_component(UnitFlagsComponent())
    fl.add(UnitFlagsComponent.OVERKILLED)
    fired = []
    import engine.runner.operations.triggers.dispatch.attack as _D
    _orig = _D.damage_dealt_triggers
    try:
        _D.damage_dealt_triggers = lambda *a, **k: fired.append(a) or []
        out = AttackDamageOperation._apply_damage_pipeline(
            st, e.id, None, e, hc, 2609, "Toxic",
            hits_result={"per_hit_health": [2609], "base_nominal": 2609}, is_first_hit=True)
    finally:
        _D.damage_dealt_triggers = _orig
    assert out is None
    assert hc.hp == 0
    assert fired == [], "aucun `On(DamageDealt = 0x10)` ne doit partir sur une cible overkillee"
    assert [d["amount"] for d in left_over_damages(st, e.id)] == [2609], \
        "la `LeftOverDamage` (base nominale) est poussee AVANT le `return` du site (A)"


def test_un_revive_efface_l_overkill_donc_la_cible_redevient_frappable():
    """LA precondition du gate ci-dessus. `IdunBattle.Operations.ReviveUnitOperation$$Execute` fait
    `Remove(0xf)`, **`Remove(8)`** et `Add(0x14)` (decompile relu) : sans ce retrait, la garde du
    site (A) rendrait toute unite RESSUSCITEE apres overkill (`TaintedNarthecium` = ReviveOnOverkill)
    definitivement INVULNERABLE -- un trou permissif silencieux, exactement le profil de degradation
    qu'on chasse."""
    from engine.runner.state import State
    from engine.runner.components import (HealthComponent, UnitComponent, UnitFlagsComponent)
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.revive import ReviveUnitOperation
    st = State()
    e = st.add_entity()
    uc = e.add_component(UnitComponent(visual_id="astraBullgryn", alive=False))
    hc = e.add_component(HealthComponent(hp=0, hp_max=1200))
    fl = e.add_component(UnitFlagsComponent())
    fl.add(UnitFlagsComponent.OVERKILLED)
    uc.pending_revive = {"amount": 1200}
    assert ReviveUnitOperation.execute(st, e.id) is not None
    assert not fl.has(UnitFlagsComponent.OVERKILLED), "`Remove(8)` doit avoir efface l'overkill"
    AttackDamageOperation._apply_damage_pipeline(st, e.id, None, e, hc, 300, "Power")
    assert hc.hp == 900, "la cible ressuscitee doit REDEVENIR frappable (PV lus : %s)" % (hc.hp,)


# --------------------------------------------------------------------------- LIVE

@pytest.mark.parametrize("seed", SEEDS)
def test_le_regime_overkill_est_bit_exact(seed):
    """Le montage de reference : `deathBlightlord` (C) frappe `astraBullgryn` (T) a 1200 PV. T meurt
    EN OVERKILL des le 1er coup -> les 3 autres coups (2 d'arme + le bonus Toxic) partent en site (A)
    et laissent 4 `LeftOverDamage`. Le relais 1 encaisse ces 4 reports et meurt ; ses 4 leftovers
    partent a leur tour vers le relais 2. Natif = 2 + 3 + 1 + 4 + 4 = 14 tirages."""
    r = _row(seed)
    assert len(r["relays"]) == 2, "montage k=2 attendu, relais lus : %s" % (r["relays"],)
    off = r["off"]
    assert off["n"] == r["n_native"], (
        "flux RNG : port %s tirages != natif %s (seed %s)" % (off["n"], r["n_native"], seed))
    port = {e["id"]: e for e in off["entities"]}
    for uid in [r["tid"]] + r["relays"]:
        live = sum(m for (t, m, _e, _a, _p) in r["dmg"] if t == uid)
        got = int(r["hp"]) - int(port[uid]["hp"] or 0)
        assert live == got, "degat sur %s : live %s != port %s (seed %s)" % (uid, live, got, seed)


@pytest.mark.parametrize("seed", SEEDS)
def test_le_second_bond_lit_une_liste_de_leftovers_COMPLETE(seed):
    """La CAUSE, en une assertion : quand le bond du 2e relais est consomme, la
    `List<LeftOverDamage>` du 1er relais doit porter les QUATRE reports qu'il vient d'encaisser --
    pas seulement celui qui l'a tue. C'est ce que garantit le drain differe."""
    r = _row(seed)
    reads = r["off"]["reads"]
    assert len(reads) == 2, "les DEUX bonds doivent etre consommes -- lu : %s" % (reads,)
    assert len(reads[0]["leftover"]) == 4, (
        "1er bond : les 4 leftovers de la cible initiale -- lu %s" % (reads[0]["leftover"],))
    assert len(reads[1]["leftover"]) == 4, (
        "2e bond : la liste du relais 1 doit etre COMPLETE (drain differe) -- lu %s"
        % (reads[1]["leftover"],))
    assert [f["draws"] for f in r["off"]["fires"]] == [4, 4], (
        "chaque report = 4 feuilles `AttackDamage`, donc 4 tirages -- lu %s"
        % ([f["draws"] for f in r["off"]["fires"]],))


@pytest.mark.parametrize("seed,hp", MATRIX)
def test_la_profondeur_d_overkill_ne_deplace_rien(seed, hp):
    """GENERALISATION. Meme geometrie, trois PV cible -> trois profondeurs d'overkill et donc trois
    rangs de mort du 1er relais dans SA serie de reports. Mesure : 9/9 bit-exacts (RNG natif ==
    port ET degat par unite), dont 4 montages a **13** tirages ou le relais meurt en MILIEU de
    serie -- le regime que le drain inline ne pouvait pas produire."""
    r = _row(seed, hp)
    off = r["off"]
    assert off["n"] == r["n_native"], (
        "flux RNG : port %s != natif %s (seed %s hp %s)" % (off["n"], r["n_native"], seed, hp))
    port = {e["id"]: e for e in off["entities"]}
    for uid in [r["tid"]] + r["relays"]:
        live = sum(m for (t, m, _e, _a, _p) in r["dmg"] if t == uid)
        got = int(hp) - int(port[uid]["hp"] or 0)
        assert live == got, ("degat sur %s : live %s != port %s (seed %s hp %s)"
                             % (uid, live, got, seed, hp))
    # La serie du 1er report doit etre COMPLETE : autant de feuilles que de leftovers lus, et le
    # 2e bond doit lire la liste que le relais a REELLEMENT accumulee (pas la seule entree letale).
    reads, fires = off["reads"], off["fires"]
    assert len(reads) == 2 and len(fires) == 2
    assert fires[0]["draws"] == len(reads[0]["leftover"])
    assert fires[1]["draws"] == len(reads[1]["leftover"])
    assert len(reads[1]["leftover"]) >= 3, (
        "le 2e bond doit lire une liste COMPLETE (>= 3), pas la seule entree letale -- lu %s"
        % (reads[1]["leftover"],))
