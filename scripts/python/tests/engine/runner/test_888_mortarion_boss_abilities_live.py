"""`deathBossMortarion` (GUILD BOSS) -- FACE COMBAT de `1093 MortarionsPlagueWind` et
`1095 ReapingScythe`, confront LIVE. #888.

LES DEUX ARBRES NATIFS, RELUS SUR `rnca9r7q6c` (mirror 1:1, cf. `runner/abilities/deathguard.py`)

    IdunBattleLogic.Entities.Abilities.Active.Loki.MortarionsPlagueWindAbility$$ExecuteBehaviour
        t1  = Cache(<DSLSelectors+0x60> = Target)
        t2  = Cache(Enemies(<+0x48> = Caster, AdjacentUnits(t1, 1, 3), 3))
        t3  = Cache(Unique(Enemies(<+0x48>, AdjacentUnits(t2, 1, 3), 3)) - t1 - t2)
        d_i = If(HasTrait(<+0x60> = Target, 2 = Summon),
                 Multiply(MinMaxDamage{,2,3}Average, <DSLFormulas+0x28> = Direct(2)),
                 MinMaxDamage{,2,3}Average)
        a_i = AttackWithAbilityDamage(Caster, t_i, d_i, Nullable(GetDamageProfile()), GetHits(), ...)
        AtomicGroup(0x5c, Group(a1,Target,0x5d) & Group(a2,Target,0x5e) & Group(a3,Target,0x5f))

    IdunBattleLogic.Entities.Abilities.Active.Loki.ReapingScytheAbility$$ExecuteBehaviour
        targets = <+0x60> op_Addition DSLSelectors$$AdjacentFriends(<+0x60>, unique=1, selType=3)
        Execute( AttackWithAttackDamage(Caster, targets, MinMaxDamage, Nullable(GetDamageProfile()),
                                        GetHits(), AbilityOrEffect(this), <options VIDE>) )

CE QUE CES TESTS DISCRIMINENT, ET CE QU'ILS NE DISCRIMINENT PAS
---------------------------------------------------------------
* **1093 -- les trois bandes ne portent PAS le meme degat, et c'est ce qui rend le test non
  fittable.** Au palier haut du boss (`AbilityLevel 55`, `AbilityVariablesMultiplier 200 %`) les
  trois moyennes valent **3080 / 4448 / 8211** : trois valeurs DISTINCTES, croissantes. Un port qui
  se tromperait de bande, de variable ou d'ordre casserait au moins une egalite. A l'inverse un
  montage a une SEULE cible ne discriminerait rien -- d'ou le bras a 4 cibles reparties sur les
  trois anneaux.
* **1093 -- le degat est DETERMINISTE** (`MinMaxDamageAverage`, pas `RandomAmount`) : l'egalite
  live/offline y est donc INSENSIBLE au flux RNG. C'est une force (aucun confond de tirage) et une
  LIMITE ecrite : ce test ne prouve rien sur la consommation RNG de 1093.
* **1095 -- `AdjacentFriends` est ANCRE SUR LA CIBLE.** Le bras (B) place deux ennemis adjacents a
  la cible : le natif les frappe. Un port qui collapserait la reference d'equipe sur le CASTER (le
  defaut du noeud) ne frapperait QUE la cible -- les allies de Mortarion, il n'y en a aucun. Le bras
  (A) est le contre-cas : cible ISOLEE -> une seule unite frappee. Les deux bras ne rendent pas le
  meme cardinal, donc aucun scalaire ne passe les deux.
* **NON DISCRIMINE, et dit** : le gate `Summon` x2 de 1093 (aucun summon dans le roster adverse
  monte ici) est confronte OFFLINE par le test `test_1093_summon_gate_doubles_offline`, en faisant
  VARIER le seul trait de la cible sur un etat par ailleurs identique. Le confront LIVE de ce gate
  reste OUVERT (il exigerait un summon comme CIBLE PRINCIPALE d'un cast du boss).

MONTAGE
-------
`deathBossMortarion` est `kind = npc` : il entre par `--explicit-stats` + `--p-units` (palier `:4`
= le palier haut, `units.npc[].stats[3]`). Le jeu le publie sous l'id d'entite REMAPPE
`GuildBoss5Boss1DeathMortarion`, que le garde de roster de `rl_duel build` lit comme un deficit ->
`TACTICUS_ALLOW_ROSTER_DEFICIT=1` (pose au niveau MODULE, avant tout build).
Board **`GB_Mortarion_05`** -- SA carte (celle que `battles/campaigns/*/battles[]` associe au boss),
7x10 / 64 tuiles jouables, une rangee de plus que l'arene generique. ⚠ ECART ASSUME avec la vraie
bataille : le boss y est monte cote JOUEUR (`--p-units`) pour etre pilotable, la ou le gameconfig le
place cote ennemi (`TeamWithPlayerIndex 1`) ; aucun volet mesure ici ne lit le camp du caster.

CONFONDS NEUTRALISES AU BUILD : `--hp-target` eleve (armure a 0, cibles qui SURVIVENT), `--crit 0,0`
et `--block-target 0,0` (1095 est famille ATTACK : crit et block y sont actifs et decaleraient le
flux RNG). ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        # PROPRE A CE FICHIER, pris LARGE et non feuille a feuille : le montage passe par le
        # visiteur de message, donc par le registre d'abilities, le vocabulaire DSL (selecteurs,
        # formules, triggers), les feuilles d'attaque, le modele de degat et le PRNG. Une liste
        # choisie serait un faux vert -- elle ne pourrait pas montrer le module qu'elle a oublie.
        # Foyers vraiment load-bearing, pour la relecture humaine :
        # `abilities/deathguard.py` (les deux arbres), `abilities/behaviours/combat.py`
        # (`AttackWithAbilityDamage` / `AttackWithAttackDamage`), `entities/selectors/units.py`
        # (`AdjacentFriends`, `Enemies`, `Sub`, `Unique`), `entities/formulas.py`
        # (`Half`/`Sum`/`Multiply`/`If`), `runner/snapshot.py` (le SEEDING de l'`AbilityState`
        # per-ability, sans lequel le boss repart au niveau 1), et
        # `handler.py` + `attack_type.py` + `targeting.py` (les trois registres).
        "scripts/python/engine/**/*.py",
        # Les modules de la RACINE : la cascade des conftest importe une vingtaine de probes plus
        # `hexgeo` / `engine_validate`, et CE fichier monte son runner par `rl_duel.py`.
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1093 MortarionsPlagueWind` et "
              "`1095 ReapingScythe` : l'oracle est le jeu lui-meme (qui est frappe, par quelle "
              "bande, et pour combien). Un changement de build -- ou de la config d'ability du "
              "boss, ou de sa carte `GB_Mortarion_05` -- peut donc faire changer ce fichier "
              "d'avis sans qu'une ligne du port bouge.",
}

import os
import sys

import pytest

# Le garde de roster de `rl_duel build` compare `deathBossMortarion` (demande) a
# `GuildBoss5Boss1DeathMortarion` (publie) et conclut a un deficit. Pose AVANT tout import de
# fixture, donc avant le premier `subprocess.run` du `build_runner`.
os.environ.setdefault("TACTICUS_ALLOW_ROSTER_DEFICIT", "1")

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _ability_cast_replay import ability_cast_harness   # noqa: E402,F401  (fixture)

import hexgeo                                            # noqa: E402
from engine.runner.runner import Runner                  # noqa: E402
from engine.runner.messages import ActiveAbilityMessage  # noqa: E402
from engine.runner.components import (HealthComponent, PositionComponent,  # noqa: E402
                                      StatsComponent, UnitComponent)
from engine.entities.active_ability_type import ActiveAbilityType    # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait              # noqa: E402

BOSS_VIS = "GuildBoss5Boss1DeathMortarion"     # id d'entite REMAPPE (le roster demande `deathBossMortarion`)
BOSS_UNIT = "deathBossMortarion:4"             # palier 4 = `units.npc[].stats[3]` (AbilityLevel 55)
BOARD = "GB_Mortarion_05"
PLAGUE_WIND = int(ActiveAbilityType.MortarionsPlagueWind)   # 1093
SCYTHE = int(ActiveAbilityType.ReapingScythe)               # 1095
# Roster ADVERSE des bras 1093 : EXACTEMENT les quatre unites que la geometrie a trois anneaux
# consomme (cible + 2 secondaires + 1 tertiaire). Une cinquieme exigerait un `move` de mise a
# l'ecart, donc une activation adverse de plus -- cf. la note du roster de 1095.
ENEMIES = "astraBullgryn,bloodIntercessor,darkaCompanion,eldarRanger"
BUILD = ["--explicit-stats", BOSS_UNIT,
         "--hp-target", "500000", "--crit", "0,0", "--block-target", "0,0"]


# ------------------------------------------------------------------ helpers etat offline

def _boss(h, dv=None):
    return h.by_visual(BOSS_VIS, dv)


def _offline_cast(state, caster, target, ability_type):
    """Rejoue le cast par le VRAI point d'entree (`Runner.apply` -> `AbilityHandler`), donc a travers
    les gates de ciblage et les vecteurs d'operation -- jamais par un appel direct a
    `execute_behaviour`."""
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=caster, target_id=target,
                                      ability_type=int(ability_type)))
    return runner.ability_handler.last or {}


def _per_hit_by_target(last):
    """{targetId: [degat par coup]} depuis le diag `attacks` des deux abilities de ce module."""
    out = {}
    for a in (last.get("attacks") or []):
        out[a["target"]] = ((a.get("attack") or {}).get("per_hit") or [])
    return out


def _upos_of(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _geometry_holds(h, boss_id, want) -> bool:
    """GARDE DE MONTAGE : toutes les unites de `want` sont VIVANTES et sur la tuile demandee, et le
    boss est vivant. Relue sur le `decisionView` COURANT, juste avant le cast.

    Elle a MORDU (#888) : sans elle, une cible tuee ou deplacee entre le placement et le cast faisait
    refuser le cast par le port (`not_alive_and_not_fled`) pendant que le natif l'acceptait --
    un rouge qui accusait le PORT pour une faute de MONTAGE. Un montage qui ne tient pas rend `None`
    (skip NOMME), jamais un faux rouge et jamais un vert silencieux."""
    dv = h.dview()
    # C'EST MON TOUR, et le boss a encore une action. Un `move` consomme une activation ; quand
    # toutes mes unites ont agi le natif termine mon tour TOUT SEUL, et le cast qui suit part alors
    # du mauvais tour -- le natif le refuse EN SILENCE (`ok=True`, aucun degat, signature #111).
    # C'est ce qu'a rendu le bras « cible ISOLEE » avant cette garde : `damage_by_target` VIDE.
    if dv.get("currentPlayer") != h.my_player:
        return False
    live_by = {u["id"]: u for u in h.alive(dv)}
    if boss_id not in live_by:
        return False
    return all(uid in live_by and _upos_of(live_by[uid]) == tuple(c) for uid, c in want.items())


def _roster(state):
    """`{uid: (visualId, alive, hp, pos)}` de l'etat OFFLINE -- le diagnostic qui separe « le port
    refuse le cast » de « l'etat rejoue n'est pas celui qu'on croit »."""
    out = {}
    for uid, e in sorted(state.entities.items()):
        uc = e.get_component(UnitComponent)
        hc = e.get_component(HealthComponent)
        pc = e.get_component(PositionComponent)
        out[uid] = (uc.visual_id if uc is not None else None,
                    uc.alive if uc is not None else None,
                    hc.hp if hc is not None else None,
                    (pc.col, pc.row) if pc is not None else None)
    return out


def _far_tiles(h, anchors, min_d=4):
    """Tuiles marchables a plus de `min_d` de TOUTES les ancres -- ou parquer les non-participants."""
    return [h.board.coord(x) for x in sorted(h.board.by_id)
            if h.board.walkable(x)
            and all(hexgeo.distance(h.board.coord(x), a) > min_d for a in anchors)]


def _place_all(h, pairs):
    return all(h.place(uid, c) for uid, c in pairs)


# ------------------------------------------------------------------ (1093) montage 3 anneaux

def _setup_three_rings(h):
    """Geometrie a TROIS anneaux :
        T  = cible, a distance <= 2 du boss (portee `range = 2` de la config)
        A,B = deux ennemis ADJACENTS a T                       -> vague 2
        D  = un ennemi adjacent a A et a distance 2 de T       -> vague 3
    Rend `(boss_id, T_id, [A_id, B_id], D_id)` ou None si le board ne la porte pas.

    ⚠ ORDRE **INVERSE** de celui que documente `AbilityCastHarness.place`, et c'est MESURE (#888).
    L'ordre canonique (placer, PUIS `reach_my_turn`) existe pour donner au caster un tour NEUF, ce
    qu'exige tout masque portant `CasterHasNotMoved` -- or NI `1093` (0x4002) NI `1095` (0x4000) ne
    le portent. Son cout, lui, mord ici : `reach_my_turn` rend la main a l'IA adverse, qui joue
    ENTRE le placement et le cast et defait la geometrie -- sur ce montage la cible ressortait MORTE
    (`hp = 0`) et le port refusait alors le cast (`not_alive_and_not_fled`) la ou le natif
    l'acceptait, ce qui accusait le PORT pour une faute de MONTAGE. On atteint donc mon tour
    D'ABORD, on place ENSUITE, et on caste dans la foulee."""
    dv = h.dview()
    boss = _boss(h, dv)
    if boss is None:
        return None
    h.my_player = boss.get("owner")
    if h.reach_my_turn() is None:
        return None
    dv = h.dview()
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < 4:
        return None
    ids = [u["id"] for u in h.alive()]
    for t in sorted(h.board.by_id):
        C = h.board.coord(t)                                   # tuile du BOSS
        if not h.board.walkable(t):
            continue
        for T in h.free_neighbours(C, 2, exclude=ids):         # cible a distance EXACTEMENT 2
            ring1 = [c for c in h.free_neighbours(T, 1, exclude=ids) if c != C]
            if len(ring1) < 2:
                continue
            A, B = ring1[0], ring1[1]
            ring2 = [c for c in h.free_neighbours(A, 1, exclude=ids)
                     if hexgeo.distance(c, T) == 2 and c != C and c not in (A, B)]
            if not ring2:
                continue
            D = ring2[0]
            t_id, a_id, b_id, d_id = [e["id"] for e in ens[:4]]
            far = _far_tiles(h, [C, T])
            spare = [e["id"] for e in ens[4:]]
            if len(far) < len(spare):
                continue
            if not _place_all(h, list(zip(spare, far))):
                continue
            if not _place_all(h, [(boss["id"], C), (t_id, T), (a_id, A), (b_id, B), (d_id, D)]):
                continue
            if not _geometry_holds(h, boss["id"], {t_id: T, a_id: A, b_id: B, d_id: D}):
                continue
            return boss["id"], t_id, [a_id, b_id], d_id
    return None


def test_1093_three_waves_live_equals_offline(ability_cast_harness):
    """DISCRIMINANT LIVE : le cast frappe QUATRE unites reparties sur TROIS anneaux, avec TROIS
    degats distincts, et le per-coup OFFLINE == LIVE cible par cible.

    Ce que ce bras casserait s'il etait faux : une erreur de bande (t2 <-> t3), de variable
    (`minDmg_2` <-> `minDmg_3`), d'exclusion (`- t1 - t2` absent -> D compte deux fois), ou de
    formule (`MinMaxDamage` au lieu de son `Average`, qui rendrait un tirage au lieu de la moyenne)."""
    h = ability_cast_harness(p_units=BOSS_UNIT, a_units=ENEMIES, board=BOARD, extra=BUILD)
    geom = _setup_three_rings(h)
    if geom is None:
        pytest.skip("geometrie 3 anneaux non montable sur %s" % BOARD)
    boss, tid, ring1, d_id = geom
    expected = {tid, *ring1, d_id}

    snap = h.snapshot()
    live = h.cast_live(boss, tid, PLAGUE_WIND)
    if not live["ok"]:
        pytest.skip("cast 1093 refuse par le natif: %s" % str(live["raw"])[:200])
    st = h.offline_state(snap)
    last = _offline_cast(st, boss, tid, PLAGUE_WIND)
    assert last.get("ported") is True, "1093 non routee par le handler: %s" % last
    off = _per_hit_by_target(last)
    lv = live["damage_by_target"]

    print("\n[1093] boss=u%d cible=u%d ring1=%s ring2=u%d" % (boss, tid, ring1, d_id))
    print("[1093] live=%s" % {k: v for k, v in sorted(lv.items())})
    print("[1093] off =%s" % {k: v for k, v in sorted(off.items())})
    print("[1093] bandes offline : main=%s secondary=%s tertiary=%s"
          % ([a["target"] for a in last.get("main") or []],
             [a["target"] for a in last.get("secondary") or []],
             [a["target"] for a in last.get("tertiary") or []]))

    # (1) CIBLAGE : les deux cotes frappent EXACTEMENT les quatre unites attendues.
    assert set(lv) == expected, "live frappe %s != attendu %s" % (sorted(lv), sorted(expected))
    assert set(off) == expected, "offline frappe %s != attendu %s" % (sorted(off), sorted(expected))

    # (2) VENTILATION PAR BANDE (diag du port) : elle vient des memos `Cache`, pas d'une geometrie
    #     recalculee -- donc elle EST le mirror des trois `t_i` natifs.
    assert [a["target"] for a in last.get("main") or []] == [tid]
    assert sorted(a["target"] for a in last.get("secondary") or []) == sorted(ring1)
    assert [a["target"] for a in last.get("tertiary") or []] == [d_id]

    # (3) DEGAT per-coup, cible par cible.
    for uid in sorted(expected):
        assert off.get(uid) == lv.get(uid), \
            "u%d : offline %s != live %s" % (uid, off.get(uid), lv.get(uid))

    # (4) LE TEMOIN DISCRIMINE : les trois anneaux ne rendent PAS le meme degat. Sans cette
    #     assertion, un port qui appliquerait la MEME base aux trois bandes passerait (1)-(3).
    d_main, d_sec, d_ter = lv[tid][0], lv[ring1[0]][0], lv[d_id][0]
    print("[1093] degats par anneau : main=%d ring1=%d ring2=%d" % (d_main, d_sec, d_ter))
    assert len({d_main, d_sec, d_ter}) == 3, \
        ("les trois anneaux rendent %s : le montage ne DISCRIMINE PAS les bandes "
         "(un port a base unique y passerait)" % [d_main, d_sec, d_ter])
    assert d_main < d_sec < d_ter, \
        ("degat non croissant par bande %s -- la config 1093 porte minDmg < minDmg_2 < minDmg_3, "
         "l'inverse de 1035" % [d_main, d_sec, d_ter])
    assert lv[ring1[0]][0] == lv[ring1[1]][0], "les deux secondaires doivent partager leur base"

    # (5) NB DE COUPS = `constants.nrOfHits` (oracle config, jamais un litteral ecrit ici).
    import gameconfig as GC
    n_hits = int(((GC.ability("MortarionsPlagueWind") or {}).get("constants") or {})["nrOfHits"])
    for uid, ph in lv.items():
        assert len(ph) == n_hits, "u%d : %d coups live != nrOfHits=%d" % (uid, len(ph), n_hits)


# ------------------------------------------------------------------ (1093) gate Summon, OFFLINE

def test_1093_summon_gate_doubles_offline(ability_cast_harness):
    """`If(HasTrait(<+0x60> = Target, 2 = Summon), Multiply(avg, Direct(2)), avg)` -- confront
    OFFLINE par VARIATION D'ENTREE : le MEME etat, le MEME cast, seul le trait de la CIBLE change.

    Deux crans, et le second est celui qui vaut le detour : le gate porte sur la CIBLE PRINCIPALE,
    donc **les trois bandes** sont doublees, y compris sur des unites qui ne sont pas des summons.
    Un port qui aurait pose le `HasTrait` sur l'unite FRAPPEE ne doublerait que la vague 1."""
    h = ability_cast_harness(p_units=BOSS_UNIT, a_units=ENEMIES, board=BOARD, extra=BUILD)
    geom = _setup_three_rings(h)
    if geom is None:
        pytest.skip("geometrie 3 anneaux non montable sur %s" % BOARD)
    boss, tid, ring1, d_id = geom
    snap = h.snapshot()

    st0 = h.offline_state(snap)
    base = _per_hit_by_target(_offline_cast(st0, boss, tid, PLAGUE_WIND))

    st1 = h.offline_state(snap)
    e = st1.get_entity(tid)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc.ctx, "traits", None) is None:
        pytest.skip("substrat de traits absent sur la cible")
    sc.ctx.traits = list(sc.ctx.traits) + [UnitTrait.Summon.name]
    doubled = _per_hit_by_target(_offline_cast(st1, boss, tid, PLAGUE_WIND))

    print("\n[1093 Summon] base    =%s" % {k: v for k, v in sorted(base.items())})
    print("[1093 Summon] doublee =%s" % {k: v for k, v in sorted(doubled.items())})
    assert set(base) == set(doubled) and base, "le set frappe doit etre identique et non vide"
    for uid in sorted(base):
        b, d = sum(base[uid]), sum(doubled[uid])
        assert d == 2 * b, \
            ("u%d : %d != 2 x %d -- le gate `Summon` porte sur la CIBLE PRINCIPALE, donc les TROIS "
             "bandes doublent (ring1=%s ring2=u%d)" % (uid, d, b, ring1, d_id))


# ------------------------------------------------------------------ (1095) deux bras de cardinal

def _setup_scythe(h, n_adjacent_to_target):
    """Boss sur C, cible T ADJACENTE a C, et `n_adjacent_to_target` autres ennemis sur des voisins
    de T. Rend `(boss_id, T_id, [ids adjacents], [ids ecartes])` ou None.

    MEME ordre inverse et MEME garde que `_setup_three_rings` -- cf. sa docstring."""
    dv = h.dview()
    boss = _boss(h, dv)
    if boss is None:
        return None
    h.my_player = boss.get("owner")
    if h.reach_my_turn() is None:
        return None
    dv = h.dview()
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < n_adjacent_to_target + 1:
        return None
    ids = [u["id"] for u in h.alive()]
    for t in sorted(h.board.by_id):
        C = h.board.coord(t)
        if not h.board.walkable(t):
            continue
        for T in h.free_neighbours(C, 1, exclude=ids):
            slots = [c for c in h.free_neighbours(T, 1, exclude=ids) if c != C]
            if len(slots) < n_adjacent_to_target:
                continue
            t_id = ens[0]["id"]
            adj = [e["id"] for e in ens[1:1 + n_adjacent_to_target]]
            spare = [e["id"] for e in ens[1 + n_adjacent_to_target:]]
            far = _far_tiles(h, [C, T])
            if len(far) < len(spare):
                continue
            if not _place_all(h, list(zip(spare, far))):
                continue
            if not _place_all(h, [(boss["id"], C), (t_id, T)]):
                continue
            if not _place_all(h, list(zip(adj, slots[:n_adjacent_to_target]))):
                continue
            if not _geometry_holds(h, boss["id"],
                                   {t_id: T, **dict(zip(adj, slots[:n_adjacent_to_target]))}):
                continue
            return boss["id"], t_id, adj, spare
    return None


@pytest.mark.parametrize("n_adj,roster,label", [
    # ⚠ LE ROSTER EST DIMENSIONNE POUR LE BRAS, et ce n'est pas cosmetique (#888). Chaque `place`
    # d'une unite ADVERSE consomme SON activation ; mettre 4 unites a l'ecart pour monter une cible
    # ISOLEE faisait basculer le tour avant le cast, et le natif le refusait alors EN SILENCE
    # (`ok=True`, `damage_by_target` VIDE, signature #111) -- le bras se skippait au lieu de mesurer.
    # Un roster a la taille exacte du bras supprime tout deplacement de mise a l'ecart.
    (0, "astraBullgryn", "cible ISOLEE"),
    (2, "astraBullgryn,bloodIntercessor,darkaCompanion", "cible + 2 voisins"),
])
def test_1095_live_equals_offline(ability_cast_harness, n_adj, roster, label):
    """DISCRIMINANT LIVE de `1095` : le cast frappe `1 + n_adj` unites (les ALLIES DE LA CIBLE qui
    lui sont adjacents, donc les ennemis du boss autour d'elle) et le per-coup OFFLINE == LIVE.

    Les deux bras ne rendent pas le meme cardinal -> aucun scalaire fitte ne les passe tous les deux.
    Le bras `n_adj = 2` est celui qui refute le collapse `reference = caster` : Mortarion n'a AUCUN
    allie, donc un port collapse ne frapperait que la cible dans les DEUX bras."""
    h = ability_cast_harness(p_units=BOSS_UNIT, a_units=roster, board=BOARD, extra=BUILD)
    geom = _setup_scythe(h, n_adj)
    if geom is None:
        pytest.skip("geometrie %s non montable sur %s" % (label, BOARD))
    boss, tid, adj, spare = geom
    expected = {tid, *adj}

    snap = h.snapshot()
    live = h.cast_live(boss, tid, SCYTHE)
    if not live["ok"]:
        pytest.skip("cast 1095 refuse par le natif: %s" % str(live["raw"])[:200])
    st = h.offline_state(snap)
    print("\n[1095 %s] etat OFFLINE pre-cast : %s" % (label, _roster(st)))
    last = _offline_cast(st, boss, tid, SCYTHE)
    assert last.get("ported") is True, \
        "1095 non routee par le handler: %s | roster offline %s" % (last, _roster(st))
    off = _per_hit_by_target(last)
    lv = live["damage_by_target"]

    print("\n[1095 %s] boss=u%d cible=u%d voisins-cible=%s ecartes=%s"
          % (label, boss, tid, adj, spare))
    print("[1095 %s] live=%s" % (label, {k: v for k, v in sorted(lv.items())}))
    print("[1095 %s] off =%s" % (label, {k: v for k, v in sorted(off.items())}))

    # ⚠ UN LIVE VIDE N'EST PAS UN VERT, et ce n'est pas non plus un « port faux » : c'est la
    # signature #111 (le natif REFUSE le cast en silence -- `ok=True`, `mutated` absent, aucun
    # degat -- quand il part du mauvais tour). On la NOMME au lieu de la laisser se deguiser en
    # divergence de ciblage.
    assert lv, ("le natif n'a emis AUCUN degat attribue a 1095 alors que le port en emet %s : "
                "cast refuse en silence (mauvais tour / gate de ciblage). raw=%s"
                % (sorted(off), str(live["raw"])[:300]))
    assert set(lv) == expected, "live frappe %s != attendu %s" % (sorted(lv), sorted(expected))
    assert set(off) == expected, "offline frappe %s != attendu %s" % (sorted(off), sorted(expected))
    assert len(lv) == 1 + n_adj, "cardinal frappe %d != %d" % (len(lv), 1 + n_adj)

    # NB DE COUPS. `constants.nrOfHits` (= 7) est le compte AVANT les reducteurs PAR CIBLE : la
    # mesure du 2026-08-11 montre `darkaCompanion` a **6** coups la ou les deux autres en prennent 7
    # -- elle porte `Parry_ReduceHits`, un `EffectHitsBonusForAttack` NEGATIF, et le port le
    # reproduit exactement. On asserte donc (a) l'egalite live/offline du COMPTE par cible, qui est
    # le vrai critere, et (b) que le PLAFOND observe est bien `nrOfHits` -- une cible non reductrice
    # doit recevoir le compte plein. Figer `== nrOfHits` partout serait un faux rouge sur le natif.
    import gameconfig as GC
    n_hits = int(((GC.ability("ReapingScythe") or {}).get("constants") or {})["nrOfHits"])
    assert max(len(ph) for ph in lv.values()) == n_hits, \
        "aucune cible ne recoit les %d coups de nrOfHits : %s" % (n_hits, {k: len(v) for k, v in lv.items()})
    for uid in sorted(expected):
        assert len(off.get(uid) or []) == len(lv.get(uid) or []), \
            "u%d : %d coups offline != %d live (reducteur de coups mal porte ?)" \
            % (uid, len(off.get(uid) or []), len(lv.get(uid) or []))
        assert off.get(uid) == lv.get(uid), \
            "u%d : offline %s != live %s" % (uid, off.get(uid), lv.get(uid))
