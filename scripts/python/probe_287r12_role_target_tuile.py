"""probe #287-r12 -- ce que les CINQ abilities TILE-TARGET portees font de leur `Target()`.

Le fait mesure (backlog `#287-r12`) : `entities_from_state` materialise un CASTER minimal quand
`caster_id` designe une tuile, mais rend `None` sur le role `target`. Cinq abilities TILE-TARGET
portees passent leur `target_id` a ce foyer : `1017` FragBomb, `1018` ValkyrieStrike, `1026`
BasiliskBarrage, `1148` DaemonicOrdnance, `1169` PlagueburstMortar.

CE QUE CE PROBE ETABLIT, ET POURQUOI IL FAUT LE MESURER AVANT D'ELARGIR LE FOYER
-------------------------------------------------------------------------------
« Les cinq lisent un `Target()` nul » n'est vrai que si le `target_id` qu'elles recoivent designe
une TUILE. Or le port a DEUX regimes d'appel, et ils coexistent :

  * regime U -- `target_id` = id d'UNITE : c'est ce que passent tous les tests live actuels
    (`_ringed_cast.cast_and_confront` envoie `targetId: <unite>` a `applyAction`, et le NATIF
    l'accepte parce qu'il transforme lui-meme la cible, cf. ci-dessous) ;
  * regime T -- `target_id` = id de TUILE : c'est ce que produit la face DECISION portee
    (`probe_302_tile_target_route`, `probe_343_tile_target_emission` : le RPC `abilityTargets`
    rend `kind: "tile"` et l'action porte le `tileEntityId`).

Le probe joue les DEUX sur le MEME substrat et le MEME MT, et imprime, par ability :
  [1] combien de fois l'arbre EVALUE le noeud `Target()`, et combien de ces evaluations rendent
      `None` (etage dynamique -- un recensement statique ne dit pas si le noeud est ATTEINT) ;
  [2] le diagnostic complet des deux regimes, et s'il DIVERGE.

LE SENS NATIF (lu, pas suppose) -- `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
resout `finalTarget = IActiveAbility.GetActualTarget(ability, caster, target)` (slot 16) ->
`IdunBattle.Entities.Abilities.AActiveAbility$$GetActualTarget` -> slot `ITargetingQuery` 6 =
`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`, dont le corps est :

    if (!options.isSelfCasting) {
        if (options.rules & 0x40)   return EntityExtensions.GetMainTile(target, state);   // TargetIsTile
        if (options.rules & (1<<44)) ... GetUnit / GetMachine                             // TargetIsMachine
        if (options.rules & (1<<46)) ... GetUnit puis GetMachine                          // TargetIsActor
        return UnitExtensions.GetUnit(target, state);
    }
    return caster;

et c'est CE `finalTarget` qui part en 5e argument de
`IdunBattle.Operations.ActiveAbilityOperation$$GetAbilityEntities`, lequel ecrit
`AbilityEntities+0x10 = finalTarget` (offset LU dans `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`,
32 arguments : `+0x00 actor · +0x08 caster · +0x10 target · +0x18 owner · +0x20 activeTarget ·
+0x30 targetTile · +0x38 targetTiles · +0x40 casterTile · +0x48 casterTiles`).

=> Pour une ability portant `TargetIsTile`, le role `target` du natif est TOUJOURS l'ENTITE-TUILE :
   ni `None`, ni l'unite occupante. Les deux regimes du port divergent donc du natif dans des sens
   OPPOSES (regime U = l'unite, regime T = `None`), et c'est ce que ce probe rend visible.

Usage (depuis scripts/python, ASCII only, 100 % OFFLINE -- aucun runner, aucune session Frida) :
    python probe_287r12_role_target_tuile.py
    python probe_287r12_role_target_tuile.py --ability 1017
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                          # noqa: E402
import engine.entities.selectors.accessors as ACC                      # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType      # noqa: E402
from engine.entities.pathfinding.board import Board                    # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES            # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                 # noqa: E402
from engine.runner.snapshot import load_state                          # noqa: E402

COLS = ROWS = 9
SEED_MT = 20260807

FRAG_BOMB = int(ActiveAbilityType.FragBomb)                     # 1017
VALKYRIE = int(ActiveAbilityType.ValkyrieStrike)                # 1018
BASILISK = int(ActiveAbilityType.BasiliskBarrage)               # 1026
DAEMONIC = int(ActiveAbilityType.DaemonicOrdnance)              # 1148
PLAGUEBURST = int(ActiveAbilityType.PlagueburstMortar)          # 1169

#: `visualId` du PORTEUR de chaque ability (recon kit -- sert au seed de traits/stats du substrat).
PORTEURS = {
    FRAG_BOMB: "astraBullgryn",
    VALKYRIE: "astraSmnVoxcaster",
    BASILISK: "astraOrdnance",
    DAEMONIC: "blackForgefiend",
    PLAGUEBURST: "deathCrawler",
}

U_CASTER, U_CIBLE, U_ADJ1, U_ADJ2, U_ALLIE = 9001, 9002, 9003, 9004, 9005
POS_CASTER = (4, 1)
POS_CIBLE = (4, 4)


def _tid(col: int, row: int) -> int:
    """Id de tuile du board SYNTHETIQUE. Volontairement >= 1 et < 1000, donc DISJOINT des ids
    d'unite (9001+) : le probe doit pouvoir distinguer les deux espaces, ce que le port ne fait
    pas (residu nomme dans `operations/active_ability.py`)."""
    return col * 100 + row + 1


def _board() -> Board:
    tuiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tuiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                           "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


def _substrat(unites, board):
    """`State` runner minimal. `unites` = (id, visualId, team, (col,row))."""
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
         "pos": {"col": p[0], "row": p[1]}, "effects": []}
        for (uid, vid, team, p) in unites]}
    ob = {"units": [{"squadId": u["id"], "hp": 200000, "hpMax": 200000} for u in dv["units"]]}
    snap = {"units": [{"entityId": uid, "traits": []} for (uid, _v, _t, _p) in unites]}
    st = load_state(dv, ob, snap, board=board)
    rng = IntBasedMersenneTwister()
    rng.init_genrand(SEED_MT)
    st.rng = rng
    return st


def _montage(ability: int, board):
    """Substrat FRAIS pour `ability` : caster + cible ENNEMIE au centre + deux ennemis et un allie
    sur des tuiles ADJACENTES a la cible (le voisinage NATIF, pas un voisinage suppose)."""
    voisins = [board.coord(t) for t in board.neighbours_native(_tid(*POS_CIBLE))]
    assert len(voisins) >= 3, "la tuile centrale doit avoir au moins 3 voisins"
    unites = [(U_CASTER, PORTEURS[ability], 1, POS_CASTER),
              (U_CIBLE, "necroWarden", 2, POS_CIBLE),
              (U_ADJ1, "necroDestroyer", 2, voisins[0]),
              (U_ADJ2, "orksNob", 2, voisins[1]),
              (U_ALLIE, "astraCreed", 1, voisins[2])]
    return _substrat(unites, board)


def _mesure(ability: int, target_id: int, board):
    """Joue `execute_behaviour(state, caster, target_id)` sur un substrat FRAIS, en comptant les
    evaluations du noeud `Target()` et leurs retours NULS.

    L'instrumentation patche `Target.select` sur la CLASSE : tous les modules importent le NOM de
    classe, donc la resolution de methode passe par elle -- forme qui MORD (contraste avec un
    `from ... import <fonction>` deja lie)."""
    st = _montage(ability, board)
    vus = []
    orig = ACC.Target.select

    def _spy(self, ctx):
        v = orig(self, ctx)
        vus.append(v)
        return v

    ACC.Target.select = _spy
    try:
        out = ABILITY_CLASSES[ability]().execute_behaviour(st, U_CASTER, target_id)
    finally:
        ACC.Target.select = orig
    return {
        "out": out,
        "evaluations": len(vus),
        "nuls": sum(1 for v in vus if v is None),
        "effets": _effets(st),
    }


def _effets(st) -> list:
    """Empreinte ORDONNEE des effets poses (porteur, type) -- le canal par lequel un `Target()` nul
    se voit sans passer par le diagnostic de retour."""
    if st.effects is None:
        return []
    out = []
    for uid, effs in sorted(st.effects.by_unit.items()):
        for e in effs:
            out.append((int(uid), int(e.effect_type)))
    return sorted(out)


def _norm(out):
    """Diagnostic canonique : on jette la cle `target` (elle porte l'ARGUMENT, qui differe par
    construction entre les deux regimes) pour ne comparer que ce que l'ability a FAIT."""
    if out is None:
        return None
    return {k: v for k, v in sorted(out.items()) if k != "target"}


def joue(ability: int) -> int:
    board = _board()
    tuile_cible = _tid(*POS_CIBLE)
    u = _mesure(ability, U_CIBLE, board)
    t = _mesure(ability, tuile_cible, board)
    nom = ActiveAbilityType(ability).name
    print(f"\n=== {ability} {nom} ({PORTEURS[ability]}) ===")
    print(f"  regime U (target_id = unite {U_CIBLE}) : Target() evalue {u['evaluations']}x, "
          f"dont {u['nuls']} NUL")
    print(f"  regime T (target_id = tuile {tuile_cible}) : Target() evalue {t['evaluations']}x, "
          f"dont {t['nuls']} NUL")
    same = _norm(u["out"]) == _norm(t["out"]) and u["effets"] == t["effets"]
    print(f"  DIAGNOSTICS IDENTIQUES : {'OUI' if same else 'NON'}")
    if not same:
        print(f"    U out    = {_norm(u['out'])}")
        print(f"    T out    = {_norm(t['out'])}")
        print(f"    U effets = {u['effets']}")
        print(f"    T effets = {t['effets']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", type=int, default=None)
    ns = ap.parse_args()
    cibles = [ns.ability] if ns.ability else [FRAG_BOMB, VALKYRIE, BASILISK, DAEMONIC, PLAGUEBURST]
    for a in cibles:
        joue(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
