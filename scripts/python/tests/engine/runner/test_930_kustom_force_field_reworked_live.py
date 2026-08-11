"""#930 -- `KustomForceFieldReworked` (1547, `orksBigMek`), face COMBAT : offline == live.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.KustomForceFieldReworkedAbility$$CreateBehaviour`
pose DEUX `AddDynamicStatModifierEffectToOwner(statType = FixedArmor)` sur le Big Mek ; leurs
`CreateTargetSelector` partagent le noeud de tete `Owner + AdjacentFriends(Owner, unique,
OnlyAliveAndTargetable)` et ne different que par le `op_LogicalNot` de leur filtre
`HasFaction(Subject, UnitFaction.Orks)` -- l'un prend les Orks (`extraArmor_2`), l'autre les
non-Orks (`extraArmor`).

QUATRE discriminants dans un seul runner, dont DEUX negatifs :
  * le PORTEUR lui-meme (Ork)         -> `extraArmor_2` -- le `op_Addition` le RE-AJOUTE a son
                                         propre selecteur, contrairement a LionHelm/IconOfObstinacy
  * ami ORK adjacent                  -> `extraArmor_2`
  * ami NON-Ork adjacent              -> `extraArmor`   (le filtre de faction MORD, et la VALEUR
                                         differe -- c'est le seul canal ou un swap se voit)
  * ami hors ring-1                   -> RIEN (cas NEGATIF)
  * ennemi                            -> RIEN (volet `Friends`, cas NEGATIF)
Et la MOBILITE dans les DEUX sens (`UpdateEffectTargets`) : un allie qui ENTRE dans le ring gagne
sa modification, un allie qui en SORT la perd.

Mesure de reference : `probe_930_kustom_force_field_reworked.py`.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/probe_930_kustom_force_field_reworked.py",
        # Le port et son foyer de selecteur.
        "scripts/python/engine/entities/effects/loki/kustom_force_field.py",
        "scripts/python/engine/entities/effects/aura_selectors.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        # Le driver de l'aura et ses DEUX points de cablage (seed / mouvement) : ce test compare
        # la stat TOTALE a chaque etape, donc l'un ou l'autre le fait diverger.
        "scripts/python/engine/runner/operations/aura_stat_mods.py",
        "scripts/python/engine/runner/operations/movement.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/entities/unit_faction.py",
        "scripts/python/engine/entities/pathfinding/board.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Live : monte un runner a positions FORCEES et confronte la face COMBAT du passif a "
              "son oracle NATIF -- `FixedArmor` total (`combatSnapshot`) a chaque etape ET la "
              "contribution PAR ENTITE-EFFET (`statModSources`), sur cinq entites couvrant les "
              "quatre cases du couple (Ork ?) x (adjacent ?) plus un ennemi. Cinq mutants doivent "
              "mordre. Toute modification du port, du foyer de selecteur, du driver d'aura ou d'un "
              "de ses deux points de cablage peut deplacer l'accord ; `build: True` parce que les "
              "magnitudes viennent du gameconfig du hash courant.",
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

CARRIER = "orksBigMek"           # HERO, au pool rank 17
ALLY_ORK = "orksNob"             # ami ORK      -> 1567
ALLY_OTHER = "ultraApothecary"   # ami NON-Ork  -> 1566
ALLY_FAR = "astraBullgryn"       # ami NON-Ork, hors ring au depart
FOE = "necroWarden"
BUILD = ["--roster", "1", "--p-units", f"{CARRIER},{ALLY_ORK},{ALLY_OTHER},{ALLY_FAR}",
         "--a-units", FOE]

EFFECT_NON_ORKS = "KustomForceFieldReworked"       # EffectType 0x61e = 1566
EFFECT_ORKS = "KustomForceFieldReworked_Orks"      # EffectType 0x61f = 1567
FIXED_ARMOR = 16                                   # StatType.FixedArmor


def _live_armor(rpc, rid):
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    return {int(u["entityId"]): int((u.get("stats") or {}).get("fixedArmor") or 0)
            for u in (snap.get("units") or [])}


def _live_aura_part(rpc, rid):
    """La CONTRIBUTION par entite-effet (`statModSources`) -- ce qui isole l'aura de la base."""
    sm = rpc("statModSources", {"runnerId": rid, "statType": FIXED_ARMOR}, 60)
    out = {}
    for u in sm.get("units") or []:
        fa = (u.get("mods") or {}).get("fixedArmor")
        out[int(u["entityId"])] = 0 if fa is None else int(fa.get("total") or 0)
    return out


def _off_armor(state):
    from engine.entities.stats import StatType
    from engine.runner.components import StatsComponent
    out = {}
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None or sc.ctx is None:
            continue
        out[int(uid)] = int(sc.ctx.stat(StatType.FIXED_ARMOR))
    return out


def _off_aura_part(state):
    """La contribution PORT de la seule famille AURA (cle `("aura_statmod", ...)` de
    `runner/operations/aura_stat_mods.aura_stat_mod_key`) -- le pendant EXACT de
    `statModSources.bySource` cote natif.

    ⚠ Ce canal existe parce que le TOTAL ne suffit pas : mesure, retirer le porteur de son propre
    selecteur laisse le total INCHANGE au seed (la part reste dans le residu opaque
    `CAPTURED_SOURCE`, que `attribute_aura_stat_modifiers` n'a alors rien a re-attribuer). Le
    mutant << op_Addition perdu >> passait 4/4 tant que ce test ne lisait que le total et la
    mesure NATIVE."""
    from engine.entities.stats import StatType
    from engine.runner.components import StatsComponent
    out = {}
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        stats = getattr(getattr(sc, "ctx", None), "stats", None)
        if stats is None:
            continue
        comp = stats.components.get(int(StatType.FIXED_ARMOR))
        per_source = getattr(getattr(comp, "modification", None), "per_source", {}) or {}
        out[int(uid)] = int(sum(v for k, v in per_source.items()
                                if isinstance(k, tuple) and k and k[0] == "aura_statmod"))
    return out


@pytest.fixture(scope="module")
def kff(rpc, build_runner):
    """Monte le runner, charge l'etat offline, puis rejoue DEUX deplacements EN LIVE ET OFFLINE :
    un allie ENTRE dans le ring-1, un autre en SORT."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import MoveUnitMessage

    rid = build_runner("777", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    ids, pos = {}, {}
    for u in dv.get("units") or []:
        if u.get("alive"):
            ids[u.get("visualId")] = u["id"]
            p = u.get("pos") or {}
            pos[u["id"]] = (p.get("col"), p.get("row"))
    if not all(k in ids for k in (CARRIER, ALLY_ORK, ALLY_OTHER, ALLY_FAR)):
        pytest.skip(f"unite absente du build ({sorted(ids)})")
    carrier_effects = {e.get("name") for u in (dv.get("units") or [])
                       if u.get("id") == ids[CARRIER] for e in (u.get("effects") or [])}
    state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    runner = Runner(state).install_default_handlers(20)
    steps = []

    def snap_step(label):
        steps.append((label, _live_armor(rpc, rid), _off_armor(state),
                      _live_aura_part(rpc, rid), _off_aura_part(state)))

    def move(uid, col, row):
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 40)
        runner.apply(MoveUnitMessage(uid, (col, row)))
        pos[uid] = (col, row)

    snap_step("seed")
    bm = pos[ids[CARRIER]]
    move(ids[ALLY_FAR], int(bm[0]) + 1, int(bm[1]))          # ENTRE dans le ring-1
    snap_step("far_in")
    move(ids[ALLY_OTHER], int(bm[0]), int(bm[1]) + 3)        # SORT du ring-1
    snap_step("other_out")
    return {"ids": ids, "pos": pos, "steps": steps, "carrier_effects": carrier_effects,
            "carrier_pos": bm}


def test_le_porteur_porte_les_DEUX_effets(kff):
    """Le trigger HERITE (`On(AbilityInit) & OwnerIsActor`) pose les deux INCONDITIONNELLEMENT :
    ils sont donc dans `decisionView.effects` d'un runner FRAIS, sans qu'aucune action n'ait eu
    lieu. C'est ce qui etablit que le canal de port est `ABILITY_INIT_OWNER_EFFECTS`."""
    assert {EFFECT_NON_ORKS, EFFECT_ORKS} <= kff["carrier_effects"], kff["carrier_effects"]


def test_armure_offline_equals_live_at_every_step(kff):
    """A CHAQUE etape (seed, entree dans le ring, sortie du ring), `FixedArmor` offline == live sur
    les CINQ entites -- l'aura est materialisee ET revertee comme le natif."""
    for label, live, off, _lp, _op in kff["steps"]:
        for vid, uid in kff["ids"].items():
            assert live.get(uid) == off.get(uid), (
                f"[{label}] u{uid} ({vid}) : FixedArmor offline {off.get(uid)} != live "
                f"{live.get(uid)} (aura KustomForceFieldReworked mal materialisee / mal revertee)")


def test_la_contribution_PAR_EFFET_offline_equals_live(kff):
    """Le cran DU DESSOUS : la stat TOTALE peut concorder alors que le port n'ATTRIBUE rien (la
    part dort dans le residu opaque `CAPTURED_SOURCE`). On confronte donc la contribution de la
    famille AURA elle-meme, entite par entite, a `statModSources.bySource` du natif.

    Mesure : sans ce test, le mutant << le porteur n'est plus dans son propre selecteur >> passait
    4/4 -- et c'est precisement le quirk que cette tranche etablit."""
    for label, _live, _off, live_part, off_part in kff["steps"]:
        for vid, uid in kff["ids"].items():
            assert off_part.get(uid, 0) == live_part.get(uid, 0), (
                f"[{label}] u{uid} ({vid}) : contribution AURA offline {off_part.get(uid)} != "
                f"live {live_part.get(uid)} (le port n'attribue pas la meme part que le natif)")


def test_les_quatre_discriminants_du_selecteur(kff):
    """Valeurs EXACTES par entite-effet (`statModSources`), jamais un `> 0` :

      * le PORTEUR se buffe lui-meme, a la valeur ORK (c'est le `op_Addition` du selecteur) ;
      * l'ami ORK adjacent a la MEME valeur ;
      * l'ami NON-Ork adjacent a l'AUTRE (le filtre de faction mord, et il mord SUR LA VALEUR) ;
      * l'ami hors ring et l'ennemi n'ont RIEN.
    """
    ids = kff["ids"]
    seed = {lbl: part for lbl, _l, _o, part, _op in kff["steps"]}["seed"]
    amt_ork = seed[ids[CARRIER]]
    amt_other = seed[ids[ALLY_OTHER]]
    assert amt_ork > 0, "le PORTEUR ne se buffe pas -- le `op_Addition(Owner, ...)` est perdu"
    assert amt_other > 0, "l'ami NON-Ork adjacent n'a rien -- l'effet 1566 ne fire pas"
    assert amt_ork != amt_other, (
        f"les deux effets rendent la MEME valeur ({amt_ork}) : le montage ne peut pas distinguer "
        "`extraArmor` d'`extraArmor_2`")
    assert seed[ids[ALLY_ORK]] == amt_ork, (
        f"ami ORK adjacent a {seed[ids[ALLY_ORK]]} au lieu de {amt_ork} -- le filtre de faction "
        "designe le mauvais effet")
    assert seed[ids[ALLY_FAR]] == 0, (
        f"ami hors ring-1 buffe ({seed[ids[ALLY_FAR]]}) -- `AdjacentFriends` ne borne pas")
    assert seed[ids[FOE]] == 0, (
        f"ENNEMI buffe ({seed[ids[FOE]]}) -- le volet `Friends` du selecteur ne mord pas")


def test_la_mobilite_est_suivie_dans_les_DEUX_sens(kff):
    """`UpdateEffectTargets` : l'allie NON-Ork qui ENTRE dans le ring-1 recoit exactement la
    valeur non-Ork ; celui qui en SORT retombe a 0. Les deux sens comptent -- un port qui
    appliquerait sans jamais reverter passerait la moitie de ce test."""
    ids = kff["ids"]
    parts = {lbl: part for lbl, _l, _o, part, _op in kff["steps"]}
    seed, far_in, other_out = parts["seed"], parts["far_in"], parts["other_out"]
    non_ork = seed[ids[ALLY_OTHER]]
    assert far_in[ids[ALLY_FAR]] == non_ork, (
        f"allie entre dans le ring : {far_in[ids[ALLY_FAR]]} au lieu de {non_ork}")
    assert other_out[ids[ALLY_OTHER]] == 0, (
        f"allie sorti du ring garde {other_out[ids[ALLY_OTHER]]} -- pas de `RevertModification`")
    # le PORTEUR n'a pas bouge : sa contribution est INCHANGEE aux trois etapes (temoin de stabilite).
    assert (seed[ids[CARRIER]] == far_in[ids[CARRIER]] == other_out[ids[CARRIER]]
            == seed[ids[CARRIER]]) and seed[ids[CARRIER]] > 0
