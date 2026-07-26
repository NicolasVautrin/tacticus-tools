"""#119 — face DECISION de `SupremeCommanderPlaybook` (1028) : ACCORD avec l'IA NATIVE.

Ce fichier garde la face **DECIDER** (l'IA choisit-elle de caster 1028 ?). La face **EXECUTER**
(ce que le cast fait) est gardee ailleurs (`runner/test_supreme_commander_live.py`) : tous ses tests
CASTENT l'ability explicitement puis comparent les effets — aucun ne regarde si l'IA aurait choisi
de la caster. C'est ce trou-la que ce fichier ferme.

ORACLE = la decision de l'IA native elle-meme, `CalculateNextActionForUnit` (RPC `aiDryRunAllUnits`,
read-only, `mutated=false` verifie), plus un TOUR REELLEMENT JOUE (`playTurn`) sur le cas nominal.
JAMAIS `aiPredict`/`GetAllPredictions` (preview du seul vecteur Attack — deux bugs compensatoires
#96/#98 sont nes de cette confusion). Aucune valeur figee : chaque assertion confronte le port a une
mesure prise sur le jeu en cours.

Les etats sont CRAFTES (rosters, board, positions pilotees) par
`probe_119_supreme_commander_decision.py` — SOURCE UNIQUE du montage, partagee avec le probe :
  A  Kell allie, Creed PV pleins, ennemis increvables      -> le natif CASTE
  B  meme build, Creed jamais attaque (pas d'enfant)       -> le natif S'ABSTIENT
  C  DEUX Creed, un SEUL Kell (camp adverse)               -> le mien s'abstient, le sien CASTE
  D  Kell allie MAIS ennemi sure-kill a l'attaque normale  -> le natif S'ABSTIENT (gate 1)

C est le point DISCRIMINANT : dans le MEME etat, deux Creed, un seul Kell — une regle naive
« un Kell existe sur le plateau » rendrait la meme reponse pour les deux, le natif non.

ASCII only. Un runner vivant a la fois (dispose des la mesure capturee).
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def sc(live_session):
    """Joue les 4 scenarios (A..D) et rend `{tag: resultat}` — un seul runner vivant a la fois.

    E (frequence de cast a PV REDUITS) est volontairement HORS de la garde : c'est une mesure
    STOCHASTIQUE du tirage natif, pertinente en probe, pas en test."""
    import probe_119_supreme_commander_decision as P
    return P.run_all(live_session, only="A,B,C,D,A2")


def _rec(sc, needle):
    for v in sc.values():
        for r in (v.get("records") or []):
            if needle in r["tag"]:
                return r
    raise AssertionError(f"point de confrontation '{needle}' absent : {list(sc)}")


def _assert_agreement(r):
    assert r["native_cast"] == r["expect_cast"], (
        f"[{r['tag']}] l'ETAT n'est pas celui voulu : le natif "
        f"{'caste' if r['native_cast'] else 'ne caste pas'} 1028 alors que le scenario visait "
        f"l'inverse (natif={r['native']}) -> le montage ne prouve rien, il est a refaire")
    assert r["port_cast"] == r["native_cast"], (
        f"[{r['tag']}] DESACCORD face DECISION : natif={r['native']} port={r['engine']} "
        f"gates={r['gates']}")
    assert r["same_target"], (
        f"[{r['tag']}] meme ability mais CIBLE differente : natif={r['native']} port={r['engine']}")


def test_casts_when_friendly_child_alive(sc):
    """A — Kell (enfant ALLIE de Creed) en jeu, PV pleins, aucun ennemi tuable : le natif caste
    1028 sur LUI-MEME ; le port propose la meme paire (ability, cible)."""
    r = _rec(sc, "A kell-ami")
    assert r["gates"]["gate2_friendly_child"], (
        "gate (2) du port FAUX alors que Kell est en jeu -> `IsFriendlyKell` ne voit pas l'enfant "
        f"(gates={r['gates']}) ; c'etait le bug #119 (lecture d'un `parentId` qu'aucun RPC ne publie)")
    _assert_agreement(r)
    assert r["native"]["target"] == r["uid"], (
        f"1028 est un cast SELF : cible native attendue = le caster, obtenu {r['native']['target']}")


def test_full_hp_draw_is_deterministic(sc):
    """Etage (3) : `chance = 1/2 + hp%(caster)/2` vaut 1 a PV PLEINS -> le tirage natif passe a TOUS
    les coups. C'est ce qui rend le port (deterministe) EXACT dans ce regime."""
    a = sc["A"]
    c, n = a["draws"]
    assert a["hp_frac"] == pytest.approx(1.0), (
        f"Creed n'est pas a PV pleins (hp%={a['hp_frac']}) -> l'etage (3) n'est pas deterministe, "
        f"la garde ne s'applique pas")
    assert c == n, (
        f"{c}/{n} tirages natifs seulement -> a chance=1 le tirage devrait TOUJOURS passer "
        f"(l'etage (3) ou la lecture de PV du RE est fausse)")


def test_played_turn_actually_summons(sc):
    """ORACLE FORT : on rend REELLEMENT la main a l'IA (`playTurn`) et des unites APPARAISSENT —
    la decision observee n'est pas un artefact du dry-run non applique."""
    spawned = sc["A"]["played_turn_spawned"]
    assert spawned, ("le tour natif joue n'a fait apparaitre aucune unite -> 1028 n'a pas ete "
                     "reellement caste")


def test_abstains_without_any_child(sc):
    """B — CONTRE-CAS du gate (2) : meme build, meme geometrie, Creed jamais attaque donc AUCUN
    enfant : le natif s'abstient (il attaque), le port aussi."""
    r = _rec(sc, "B sans-enfant")
    assert not r["gates"]["gate2_friendly_child"]
    _assert_agreement(r)


def test_child_of_the_other_team_does_not_count(sc):
    """C — DISCRIMINANT du filtre `UnitExtensions.IsFriend` : un SEUL Kell sur le plateau, dans le
    camp ADVERSE. Le Creed adverse caste, le mien non — dans le MEME etat."""
    kell_teams = sc["C"]["kell_teams"]
    assert kell_teams and all(t != 1 for t in kell_teams), (
        f"le montage exige un Kell UNIQUEMENT dans le camp adverse, teams={kell_teams}")
    mine = _rec(sc, "C mon-creed")
    theirs = _rec(sc, "C creed-adverse")
    assert not mine["gates"]["gate2_friendly_child"], (
        "gate (2) VRAI pour MON Creed alors que le seul Kell est adverse -> le filtre d'equipe "
        f"ne s'applique pas (gates={mine['gates']})")
    assert theirs["gates"]["gate2_friendly_child"]
    _assert_agreement(mine)
    _assert_agreement(theirs)


def test_agreement_generalises_to_another_board_and_seed(sc):
    """GENERALISATION : le meme accord sur un AUTRE couple (board, seed). Le board fixe la
    geometrie de spawn de Kell (`GetSpawnTile` = voisin LIBRE de la cible) et les positions ;
    l'accord de la face DECISION, lui, ne doit pas en dependre."""
    a2 = sc["A2"]
    assert (a2["board"], a2["seed"]) != (sc["A"]["board"], sc["A"]["seed"]), (
        "A et A2 doivent differer par le couple (board, seed), sinon ce n'est pas une "
        "generalisation")
    r = _rec(sc, "A2 kell-ami")
    assert r["gates"]["gate2_friendly_child"]
    _assert_agreement(r)
    c, n = a2["draws"]
    assert c == n, f"{c}/{n} tirages natifs a PV pleins sur {a2['board']}"


def test_abstains_when_normal_attack_already_kills(sc):
    """D — gate (1) `EnemyWillBeKilledWithNormalAttack` : Kell en jeu et PV pleins (gates 2 et 3
    VRAIS), mais un ennemi meurt a coup sur de l'attaque normale -> le natif l'attaque au lieu de
    caster. Seuls les PV ennemis changent vs A : c'est bien ce gate qui bascule la decision."""
    r = _rec(sc, "D sure-kill")
    assert sc["D"]["sure_kill"], "aucun sure-kill dans le plan natif -> gate (1) non exerce"
    assert r["gates"]["gate1_enemy_sure_kill"] and r["gates"]["gate2_friendly_child"], (
        f"le montage exige gate1 VRAI *et* gate2 VRAI, gates={r['gates']}")
    _assert_agreement(r)
