"""`#419-r1-tr10-r2` -- le canal MULTI-TUILES existe-t-il cote DECISION ?

CRITERE BINAIRE, enonce AVANT la mesure : la `Scene` que construit `playbook.scene.build_predictor`
(le substrat de TOUS les playbooks de la face DECISION) porte-t-elle, pour une MACHINE OF WAR, les
tuiles de son empreinte AUTRES que la MainTile ? Si oui, `playbook.adjacency.iterate_tiles` les lit
et le port calcule le voisinage NATIF. Si non, le port reste sur la MainTile, et le residu est un
trou de SEEDING -- localise, nommable, pas un trou de logique.

Le natif, lui, itere `IdunBattle.Entities.EntityExtensions$$IterateTiles(entity, state)`. C'est LU
dans `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` :

    inner = this.<+0x20 = origin>.Select(entities);        // TOUTES les tuiles du sujet
    foreach (t in inner)
        foreach (n in battleQuery.<+0x50 IterateAdjacentTiles>(t, false, true, true))
            if (!inner.Contains(n)) result.Add(n);         // ring-1 de CHAQUE pied, MOINS l'empreinte

⚠ DEUX CORRECTIONS DE MONTAGE, mesurees a la confrontation du capteur (`#419-r7`) :

  (a) **La MoW n'est PAS dans `decisionView.units`** -- jamais, par construction : le canal `.mows`
      est SEPARE (`projectMowsFull`), et c'est exactement pourquoi `scene.feet_by_id` existe. La
      version d'avant cherchait la MoW dans `units` et sortait en MONTAGE NON INSTALLE sans jamais
      atteindre sa mesure.
  (b) **`GetTiles(<entite Machine>)` rend `[]`, et c'est un FAIT NATIF, pas une panne.**
      `EntityExtensions.<IterateTiles>d__17$$MoveNext` teste TROIS types (pied -> sa tuile ; tuile
      -> elle-meme ; unite -> ses pieds) et sort FAUX pour tout le reste ; `EntityType.Machine`
      n'est aucun des trois. L'empreinte REELLE d'une MoW est l'ensemble de ses `MachinePlatform`,
      publie sous `mows[].platformTiles`. Le probe lit donc les DEUX champs, et dit LEQUEL a
      repondu.

ETAPES -- et l'attestation vient AVANT le verdict :

  1. ATTESTATION du porteur : la MoW est-elle reellement MULTI-TUILES ? Mesuree sur le canal
     publie par le hook (`mows[].platformTiles`, l'ensemble des plateformes de la meme machine).
     Sans elle, << 1 tuile cote decision >> ne prouverait rien : l'entite pourrait etre
     mono-tuile, et le probe rendrait un faux verdict.
  2. MESURE cote DECISION : ce que la `Scene` porte (`feet_by_id`), et ce qu'`adjacency.iterate_tiles`
     en tire.
  3. NON-REGRESSION : sur une UNITE mono-pied, `feet == [MainTile]` et `iterate_tiles` rend
     exactement ce qu'il rendait avant le capteur (`[scene.pos(uid)]`).
  4. VERDICT : canal PRESENT (le port compte le vrai voisinage) ou ABSENT.

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine.playbook import adjacency as adj              # noqa: E402
from engine.playbook import scene as _scene               # noqa: E402


class MontageError(RuntimeError):
    """Le montage n'est pas installe -- on REFUSE de mesurer plutot que de rendre un chiffre."""


def _build(state_file: str, seed: str, board: str, mow: str, roster: int) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
            "--roster", str(roster), "--state-file", state_file, "--p-mow", mow, "--no-ai"]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError("rl_duel build a echoue (rc=%d) : %s"
                           % (p.returncode, (p.stderr or p.stdout or "")[-900:]))
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _pos(d) -> tuple:
    p = d.get("pos") or {}
    return (p.get("col"), p.get("row"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU, propre")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--mow", default="adeptExorcist", help="MoW du pool (rl_duel build --list-pool)")
    ap.add_argument("--roster", type=int, default=5)
    a = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(a.state_file, a.seed, a.board, a.mow, a.roster)
    print("runner %s | board %s seed %s | MoW visee %s" % (rid, a.board, a.seed, a.mow))
    try:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)
        units = dv.get("units") or []
        mows = dv.get("mows") or []
        print("  decisionView : %d units, %d lignes mows" % (len(units), len(mows)))

        print("")
        print("=== etape 1 -- ATTESTATION : la MoW est-elle multi-tuiles ? ===")
        # ⚠ Le canal `.mows` porte UNE LIGNE PAR PLATEFORME : plusieurs lignes partagent le meme
        # `machineId`. C'est cette redondance qui rendait l'empreinte illisible avant le capteur.
        lignes = [m for m in mows if str(m.get("visualId") or "").lower() == a.mow.lower()]
        if not lignes:
            raise MontageError("montage NON INSTALLE : %s absente du canal `mows` "
                               "(visualIds vus : %s)"
                               % (a.mow, sorted({str(m.get("visualId")) for m in mows})))
        machine_ids = sorted({m.get("machineId") for m in lignes})
        print("  %d ligne(s) `mows` pour %s | machineId(s)=%s"
              % (len(lignes), a.mow, machine_ids))
        for m in lignes:
            print("     platformId=%s machineId=%s pos=%s slot=%s"
                  % (m.get("id"), m.get("machineId"), _pos(m), m.get("slot")))
        m0 = lignes[0]
        feet = m0.get("feet")
        plat = m0.get("platformTiles")
        print("  `feet` (GetTiles sur l'entite Machine) = %r" % (feet,))
        print("  `platformTiles` (l'empreinte REELLE)   = %r" % (plat,))
        canal, empreinte = ("feet", feet) if feet else ("platformTiles", plat)
        if not empreinte:
            raise MontageError(
                "les DEUX canaux sont vides pour %s : feet=%r platformTiles=%r -- la MoW est "
                "probablement HORS PLATEAU (toutes ses lignes ont pos=None). Le capteur n'a rien "
                "publie parce qu'il n'y avait rien a publier : ce n'est PAS un verdict."
                % (a.mow, feet, plat))
        print("  -> canal qui a repondu : `%s`, %d tuile(s)" % (canal, len(empreinte)))
        if len(empreinte) <= 1:
            raise MontageError(
                "le porteur n'est PAS multi-tuiles sur ce montage (%d tuile) -- un << 1 tuile cote "
                "decision >> ne prouverait alors RIEN. Choisir une autre MoW ou un autre board."
                % len(empreinte))

        print("")
        print("=== etape 2 -- ce que la Scene de DECISION porte ===")
        sc = _scene.build_predictor(rpc, rid)
        tbl = getattr(sc, "feet_by_id", None) or {}
        print("  scene.feet_by_id : %d entree(s)" % len(tbl))
        mid = machine_ids[0]
        print("  entree pour machineId=%s : %r" % (mid, tbl.get(int(mid))))
        tiles = adj.iterate_tiles(sc, mid)
        print("  adjacency.iterate_tiles(machineId) -> %r  (cardinal %d)" % (tiles, len(tiles)))
        voisins = adj.adjacent_positions(sc, mid)
        print("  adjacency.adjacent_positions -> %d tuile(s) : %r"
              % (len(voisins), sorted(voisins)))

        print("")
        print("=== etape 3 -- NON-REGRESSION sur une UNITE mono-pied ===")
        # Le capteur ne doit RIEN changer la ou il n'y a qu'un pied : `feet == [MainTile]` et
        # `iterate_tiles` doit rendre EXACTEMENT `[scene.pos(uid)]` -- le comportement d'avant.
        ecarts = 0
        vus = 0
        for u in units:
            uid = u.get("id")
            if uid is None or not u.get("alive"):
                continue
            f = u.get("feet")
            if f is None:
                print("  u%s : `feet` NON MESURE (tri-etat null) -- repli MainTile" % uid)
                continue
            vus += 1
            got = adj.iterate_tiles(sc, uid)
            attendu = [] if sc.pos(uid) is None else [tuple(sc.pos(uid))[:2]]
            if len(f) == 1:
                if got != attendu:
                    ecarts += 1
                    print("  ECART u%s : feet=%r iterate_tiles=%r attendu=%r"
                          % (uid, f, got, attendu))
            else:
                print("  u%s est MULTI-PIED (%d) : feet=%r" % (uid, len(f), f))
        print("  %d unite(s) a canal mesure ; %d ecart(s) sur les mono-pied" % (vus, ecarts))

        print("")
        print("=== etape 4 -- verdict ===")
        if len(tiles) > 1 and ecarts == 0:
            print("CANAL PRESENT : %d tuiles lues cote DECISION (canal `%s`), le voisinage"
                  % (len(tiles), canal))
            print("  multi-tuiles est calcule par le port ; NON-REGRESSION tenue sur les mono-pied.")
            return 0
        if len(tiles) <= 1:
            print("CANAL ABSENT : le port ne connait que la MainTile (%r)." % (tiles,))
            print("  Le mirror EST en place (`engine/playbook/adjacency.py`) ; c'est son ENTREE qui")
            print("  manque. Point d'ancrage : `IdunBattle.Entities.EntityExtensions$$GetTiles`.")
            return 1
        print("REGRESSION : %d ecart(s) sur des unites MONO-PIED -- le capteur change ce qu'il ne"
              % ecarts)
        print("  devait pas changer.")
        return 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as e:
        print("MONTAGE : %s" % e)
        sys.exit(2)
