"""Gate 1118 DoctrinaImperatives : branches `count>0` du playbook de Tan Gi'da (case-38).

ORACLE = la leaf NATIVE, lue par le RPC `ncEvaluate` (il invoque
`IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$EvaluateNonComparable` a la position
courante et decode le Bucket rendu). Aucun scalaire fige ici : le cap attendu est interroge sur le
kit (`ability_var("ControlEdict", "maxSummons", niveau PASSIF du caster)`) et le seuil natif est
MESURE, jamais ecrit.

Chaine natif gardee :
  `EvaluateNonComparable` -> (slot itf 0x51) `IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles`
                          -> (slot itf 0xc9) `IdunBattle.Core.Services.BattleQuery$$ReachedSummonCap`
     -> `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(cfg, 0x31=maxSummons, level)`
        <= `IdunBattle.Entities.UnitExtensions$$GetChildrenCount(caster, entities, predicat=null)`

Deux scenarios CRAFTES (doctrine : on fabrique l'etat teste, on ne l'attend pas) :

  * `capbranch_rows` (arene MC1_67, Tan au large) -- Tan garde des tuiles libres adjacentes ->
    la branche exercee est `free>0 -> ReachedSummonCap`. Le balayage passe par chaque valeur de
    `summons_ever` 0..cap : le point de bascule de la leaf native donne le cap NATIF.
  * `capbranch_rows_tight` (C4_09, geometrie serree) -- a 3 Skitarii, Tan n'a PLUS de tuile libre
    adjacente -> la branche exercee est `free==0 -> emission inconditionnelle` (elle emet alors que
    `ReachedSummonCap` est FAUX : c'est ce qui la rend discriminante).

Le scenario (drive + mesure) est REUTILISE depuis `probe_38c_capbranch.run_capbranch_scenario`
(regle DRY : le probe MESURE, le test ASSERE).
"""
from __future__ import annotations

import pytest

import probe_38c_capbranch as P


def _rows(rpc, build_runner, board: str, seed: str = "777"):
    rid = build_runner(seed, extra=[*P.BUILD_EXTRA, "--board", board])["rid"]
    rows = P.run_capbranch_scenario(rid, rpc, log=lambda *a, **k: None)
    if not rows:
        pytest.fail(f"aucun point de mesure sur {board} -- rien n'a ete confronte "
                    f"(ce n'est PAS un skip vert)", pytrace=False)
    return rows


@pytest.fixture(scope="module")
def capbranch_rows(live_session, rpc, build_runner):
    """Arene large : Tan summone jusqu'au cap en gardant `free>0` (branche ReachedSummonCap).

    `--hp-target` rend les ennemis increvables (Tan attaque en boucle -> il summone) ;
    `--dmg-target` rend la frappe adverse letale (phase 2 peut TUER des Skitarii, dont les PV
    viennent du kit ControlEdict et sont donc hors de portee de `--hp-target`/`--hp-player`)."""
    return _rows(rpc, build_runner, "MC1_67")


@pytest.fixture(scope="module")
def capbranch_rows_tight(live_session, rpc, build_runner):
    """Geometrie serree : les Skitarii bouchent les voisins de Tan -> `free==0`."""
    return _rows(rpc, build_runner, "C4_09")


def _cap(rows):
    """Cap attendu = `maxSummons[niveau passif]` du kit ControlEdict (oracle, pas une constante)."""
    return rows[0]["port"]["capValue"]


def _on_cap_branch(rows):
    """Points reellement sur la branche `count>0 & free>0` (celle que garde ce fichier)."""
    return [r for r in rows if r["port"]["hv"] and r["port"]["free"] > 0]


def test_doctrina_gate_agrees_with_native(capbranch_rows):
    """Accord port <-> leaf native sur TOUS les points, + garde ANTI-VACUITE : le discriminant
    doit avoir ete exerce des DEUX cotes du cap (sinon un port qui repondrait toujours `False`
    passerait au vert)."""
    rows = capbranch_rows
    cap = _cap(rows)
    assert cap > 0, f"maxSummons non resoluble (niveau passif={rows[0]['port']['passiveLevel']})"
    branch = _on_cap_branch(rows)
    assert [r for r in branch if r["summons_ever"] < cap], \
        f"aucun point SOUS le cap ({cap}) sur la branche free>0 -- discriminant non exerce"
    assert [r for r in branch if r["summons_ever"] >= cap], \
        f"aucun point AU cap ({cap}) sur la branche free>0 -- discriminant non exerce"
    bad = [(r["label"], r["native_emit"], r["port"]["emit"]) for r in rows if not r["agree"]]
    assert not bad, f"port != leaf native sur {len(bad)} point(s): {bad}"


def test_doctrina_cap_threshold_matches_kit(capbranch_rows):
    """Le seuil NATIF mesure (1er `summons_ever` ou la leaf emet) == `maxSummons[level]` du kit.
    C'est la confrontation de `GetVariableForLevel(cfg, maxSummons, level)` : un A/B 0-vs-plein
    resterait compatible avec n'importe quel cap 1..N, ce balayage n'est compatible que d'un seul."""
    rows = _on_cap_branch(capbranch_rows)
    cap = _cap(capbranch_rows)
    emitting = sorted(r["summons_ever"] for r in rows if r["native_emit"])
    silent = sorted(r["summons_ever"] for r in rows if not r["native_emit"])
    assert emitting, "la leaf native n'a JAMAIS emis sur la branche free>0 -- cap jamais atteint"
    assert silent, "la leaf native a TOUJOURS emis -- aucun bras sous le cap"
    assert max(silent) < min(emitting), \
        f"seuil natif non monotone: silencieux={silent} emetteurs={emitting}"
    assert min(emitting) == cap, \
        (f"seuil natif mesure={min(emitting)} != maxSummons[level]={cap} "
         f"(GetVariableForLevel vs mirror `_reached_summon_cap`)")


def test_doctrina_cap_counts_dead_summons(capbranch_rows):
    """`GetChildrenCount` lit `ParentComponent.children`, liste APPEND-ONLY (aucun `RemoveChild` ;
    `IdunBattle.Operations.RemoveUnitOperation$$Execute` ne touche que les listes du PlayerComponent)
    -> un Skitarii MORT reste compte. Etat teste : `alive < cap <= ever`. Un modele
    "summons VIVANTS" predirait l'absence d'emission."""
    rows = capbranch_rows
    cap = _cap(rows)
    pts = [r for r in rows if r["summons_alive"] < cap <= r["summons_ever"]
           and r["port"]["hv"] and r["port"]["free"] > 0]
    assert pts, ("aucun point `alive < cap <= ever` sur la branche free>0 -- la destruction de "
                 "summons n'a pas abouti, la semantique append-only de GetChildrenCount n'est "
                 "PAS confrontee (ce n'est PAS un skip vert)")
    for r in pts:
        assert r["native_emit"], \
            (f"{r['label']}: alive={r['summons_alive']} < cap={cap} <= ever={r['summons_ever']} "
             f"et la leaf native N'EMET PAS -> GetChildrenCount ne serait pas append-only")
        assert r["port"]["cap"], \
            (f"{r['label']}: le port ne compte pas les summons MORTS "
             f"(alive={r['summons_alive']}, ever={r['summons_ever']}, cap={cap})")


def test_doctrina_free0_branch_emits_without_cap(capbranch_rows_tight):
    """Branche `count>0 & free==0` : Tan n'a plus AUCUNE tuile libre adjacente -> la leaf native
    emet MEME SI `ReachedSummonCap` est faux. Discriminante : elle refute tout modele ou
    l'emission sur `count>0` passerait uniquement par le cap."""
    rows = capbranch_rows_tight
    cap = _cap(rows)
    pts = [r for r in rows if r["port"]["hv"] and r["port"]["free"] == 0
           and r["summons_ever"] < cap]
    assert pts, ("aucun point `count>0 & free==0 & cap non atteint` -- la branche encerclement "
                 "n'a PAS ete confrontee (ce n'est PAS un skip vert)")
    for r in pts:
        assert r["native_emit"], \
            (f"{r['label']}: free==0 et cap={r['port']['cap']} mais la leaf native N'EMET PAS "
             f"-> la branche `free==0 -> emission inconditionnelle` serait fausse")
        assert r["port"]["emit"], f"{r['label']}: le port n'emet pas sur free==0"
    bad = [(r["label"], r["native_emit"], r["port"]["emit"]) for r in rows if not r["agree"]]
    assert not bad, f"port != leaf native sur {len(bad)} point(s): {bad}"
