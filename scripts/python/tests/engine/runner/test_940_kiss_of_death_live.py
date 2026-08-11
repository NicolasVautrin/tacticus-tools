"""#940 -- GARDE LIVE de `KissOfDeath` (1108) : le port confronte au NATIF, sur UN runner.

Le probe `probe_940_kiss_of_death_live.py` MESURE (six etages, banc de mutants, decomposition du
degat) ; ce fichier GARDE les trois verdicts qu'un port faux ne peut pas produire par hasard, et il
les garde sur UN SEUL montage pour ne pas payer six builds :

  * les CIBLES de la chaine -- `{T, M1, M2}` : `M2` n'est adjacent qu'a `M1`, jamais a la cible
    designee, donc il n'est atteignable que si le `jumpTargetSelector` recoit la LISTE COMPLETE des
    cibles deja piquees ; et `W`, adjacent a `M2`, ne doit PAS etre frappe (`maxAdjacentTargets`
    borne les SAUTS, pas le total) ;
  * la TUILE d'atterrissage -- adjacente a la DERNIERE victime, pas a la cible designee. C'est le
    verdict qui exige que `unitsAttackedThisTurn` MUTE pendant l'arbre qui le relit ;
  * le DEGAT applique, cible par cible -- rng CALE des deux cotes (`dumpRng`), donc egalite
    BIT-EXACTE attendue.

Le montage (board, placement, geometrie) et les helpers RPC viennent du probe, importe comme
BIBLIOTHEQUE : une seule definition du montage, donc aucun risque de le voir diverger entre la
mesure et la garde.

ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/probe_940_kiss_of_death_live.py",
        "scripts/python/engine/runner/abilities/aeldari.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/behaviours/chain.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/selectors/**",
        "scripts/python/engine/dsl/**",
        "data/seed-bc.json", "data/boards/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE du port de 1108 au natif (cibles de chaine, tuile "
              "d'atterrissage, degat bit-exact). Depend du code du port ET du build charge -- le "
              "natif est l'oracle des trois verdicts.",
}

import pytest                                                                    # noqa: E402

import probe_940_kiss_of_death_live as P                                         # noqa: E402


@pytest.fixture(scope="module")
def montage(tmp_path_factory):
    """Un SEUL runner pour les trois verdicts : build, placement force, etat PRE-CAST charge,
    execution du port, puis cast NATIF. Le port tourne sur un `State` Python INDEPENDANT du
    runner -- l'executer ne touche pas le live, donc les deux mesures partent du meme etat."""
    from engine.runner.components import HealthComponent
    sid = P._session()
    sp = tmp_path_factory.mktemp("kod940") / "st_940_kiss_of_death_test.json"
    rid = P.build(sp)
    try:
        _, dec = P.load(sid, rid)
        ids = P._ids(dec)
        assert all(v is not None for v in ids.values()), "roster incomplet : %r" % (ids,)
        for role, (c, r) in P.PLACEMENT:
            P._cli(sp, ["act", "move", "--unit", str(ids[role]), "--to", "%d,%d" % (c, r)])
        state, dec = P.load(sid, rid)
        for role, want in P.TILES.items():                 # le montage vaut ce que vaut sa geometrie
            assert P._pos_of(state, ids[role]) == want, "placement %s" % (role,)

        def _hp(st):
            out = {}
            for role in ("T", "M1", "M2", "W"):
                e = st.get_entity(ids[role])
                hc = e.get_component(HealthComponent) if e is not None else None
                out[role] = int(hc.hp) if hc is not None and hc.hp is not None else None
            return out
        hp0 = _hp(state)
        from engine.runner.abilities.handler import ABILITY_CLASSES
        cls = ABILITY_CLASSES[P.KISS_OF_DEATH]
        out = cls().execute_behaviour(state, ids["H"], ids["T"])
        hp1 = _hp(state)
        port = {
            "targets": sorted(int(t) for t in (out or {}).get("targets", []) if t is not None),
            "tile": P._pos_of(state, ids["H"]),
            "damage": {k: hp0[k] - hp1[k] for k in hp0
                       if hp0[k] is not None and hp1[k] is not None and hp0[k] != hp1[k]},
        }
        legal = P.native_targets(sid, rid, ids["H"], P.KISS_OF_DEATH)
        res = P.rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ids["H"], "targetId": ids["T"],
            "abilityType": P.KISS_OF_DEATH}}, 120)
        flat = P.native_events(res)
        hits = [n for n in flat if n["tags"].get("Target_Id") is not None
                and n["tags"].get("Amount") is not None]
        role_of = {v: k for k, v in ids.items()}
        st2, _ = P.load(sid, rid)
        nat = {
            "targets": sorted({int(n["tags"]["Target_Id"]) for n in hits}),
            "tile": P._pos_of(st2, ids["H"]),
            "damage": {role_of[int(n["tags"]["Target_Id"])]: int(n["tags"]["Amount"])
                       for n in hits},
            "profiles": sorted({int(n["tags"]["DamageProfileType"]) for n in hits
                                if n["tags"].get("DamageProfileType") is not None}),
            "abilities": sorted({int(n["tags"]["Active_Ability_Type"]) for n in hits
                                 if n["tags"].get("Active_Ability_Type") is not None}),
            "legal": legal,
        }
        yield {"ids": ids, "port": port, "nat": nat, "role_of": role_of}
    finally:
        P._cli(sp, ["dispose"])


def test_940_ciblage_le_natif_n_accepte_que_la_cible_adjacente(montage):
    """`<TargetingOptions statics>+0x68` = `TargetIsEnemy` SEUL, `range` = `RANGE_ADJACENT` :
    l'oracle est le natif lui-meme (`abilityTargets.fromHere`)."""
    ids, nat = montage["ids"], montage["nat"]
    assert nat["legal"] == [ids["T"]], \
        "le natif n'accepte QUE la cible adjacente ; obtenu %r" % (nat["legal"],)


def test_940_cibles_de_la_chaine(montage):
    """{T, M1, M2} des DEUX cotes. `M2` prouve que le saut part de TOUTES les cibles piquees ;
    `W`, absent, prouve que `maxAdjacentTargets = 2` borne les SAUTS."""
    ids, port, nat, role_of = (montage["ids"], montage["port"], montage["nat"],
                               montage["role_of"])
    attendu = sorted([ids["T"], ids["M1"], ids["M2"]])
    assert nat["targets"] == attendu, \
        "NATIF : attendu {T,M1,M2}, obtenu %r" % ([role_of.get(i, i) for i in nat["targets"]],)
    assert ids["W"] not in nat["targets"], "W frappe -> la borne `maxTargets` ne mord pas"
    assert port["targets"] == nat["targets"], \
        "PORT %r != NATIF %r" % ([role_of.get(i, i) for i in port["targets"]],
                                 [role_of.get(i, i) for i in nat["targets"]])


def test_940_atterrissage_adjacent_a_la_derniere_victime(montage):
    """« reappears in a hex adjacent to the last target hit » : la derniere victime est `M2`, par
    construction du montage. Un port qui lirait la liste d'AVANT la chaine atterrirait a cote de la
    CIBLE (mesure du 2026-08-11 : (2,3) au lieu de (2,4))."""
    import hexgeo
    port, nat = montage["port"], montage["nat"]
    voisins = set(hexgeo.neighbors(*P.TILES["M2"]))
    assert nat["tile"] in voisins, \
        "NATIF : %r n'est pas adjacente a la derniere victime %r" % (nat["tile"], P.TILES["M2"])
    assert port["tile"] == nat["tile"], "PORT %r != NATIF %r" % (port["tile"], nat["tile"])


def test_940_degat_bit_exact_et_profil(montage):
    """Rng CALE des deux cotes -> egalite BIT-EXACTE, cible par cible. Le profil (`DirectDamage`)
    et l'id d'ability threade sont LUS de la config, pas deduits de l'arbre."""
    port, nat = montage["port"], montage["nat"]
    assert nat["profiles"] == [P.DIRECT_DAMAGE], "profil natif %r" % (nat["profiles"],)
    assert nat["abilities"] == [P.KISS_OF_DEATH], "ability id natif %r" % (nat["abilities"],)
    assert nat["damage"], "le natif n'a inflige aucun degat -- montage degenere"
    assert port["damage"] == nat["damage"], \
        "degat PORT %r != NATIF %r" % (port["damage"], nat["damage"])
