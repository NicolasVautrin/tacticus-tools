"""`#419-r1-tr10-r2` -- le canal MULTI-TUILES existe-t-il cote DECISION ?

CRITERE BINAIRE, enonce AVANT la mesure : la `Scene` du pas courant (`build_predictor` +
`step_context`, le substrat de TOUS les playbooks de la face DECISION) porte-t-elle, pour une
entite MULTI-TUILES, les tuiles de son empreinte AUTRES que la MainTile ? Si oui,
`playbook.adjacency.iterate_tiles` les lit et le port calcule le voisinage NATIF. Si non, le port
reste sur la MainTile, et le residu est un trou de SEEDING -- localise, nommable, pas un trou de
logique.

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
from engine.playbook.scene import Scene                   # noqa: E402


def _scene_du_pas(rpc, rid: int, dv: dict):
    """La `Scene` du PAS COURANT, pas les tables statiques.

    ⚠ `build_predictor` seul ne suffit PAS, et c'est la faute que la premiere ecriture de ce probe
    a commise : il rend les tables COLD (`combatSnapshot` : degat d'arme, stats, boucliers) et
    **aucun** `feet_by_id`. L'empreinte est DYNAMIQUE -- elle vit dans `step_context(predictor,
    dv)`, refrappe a chaque pas -- exactement la raison pour laquelle le capteur a ete pose sur
    `decisionView` et non sur `combatSnapshot` (case-doc §2.2). Mesure : `scene.feet_by_id` rendait
    `0 entree` alors que `decisionView.units[].feet` en publiait bien trois."""
    predictor = _scene.build_predictor(rpc, rid)
    if predictor is None:
        raise MontageError("`build_predictor` rend None (combatSnapshot KO) -- pas de scene")
    sctx = _scene.step_context(predictor, dv)
    return Scene.from_predictor_sctx(predictor, sctx)


class MontageError(RuntimeError):
    """Le montage n'est pas installe -- on REFUSE de mesurer plutot que de rendre un chiffre."""


#: `#419-r7` -- le porteur MULTI-TUILES qui EXISTE et qu'on peut amener en bataille.
#: `ultraDreadnought` (MoW du pool) caste `DutyEternal` et fait apparaitre `ultraSmnDreadnought`
#: SUR TROIS HEXES (mesure de `case-mow-offboard-cast.md` §1, table du sweep des 8 MoW).
#: C'est une `EntityType.Unit`, donc `EntityExtensions$$GetTiles` la reconnait et rend ses PIEDS --
#: contrairement a l'`EntityType.Machine`, qu'`IterateTiles` ne teste pas et pour qui `feet` vaut
#: `[]` LEGITIMEMENT.
MOW_SUMMONER = "ultraDreadnought"
ABILITY_DUTY_ETERNAL = 1158
SUMMON_MULTI_HEX = "ultraSmnDreadnought"


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


class _ScenePos:
    """La MEME scene, mais PRIVEE du canal `feet_by_id` -- c'est-a-dire le port d'AVANT le capteur.

    Sert de REPERE : l'ecart entre le voisinage calcule avec et sans ce canal est la valeur
    ajoutee du capteur, chiffree. On ne recopie pas la logique d'`adjacency` pour l'obtenir --
    on lui retire son entree, ce qui est exactement la degradation qu'elle documente."""

    def __init__(self, sc):
        self._sc = sc
        self.feet_by_id: dict = {}

    def __getattr__(self, nom):
        # ⚠ `units` DOIT etre servi vide : les dicts d'unite portent eux aussi une cle `feet`, que
        # `iterate_tiles` lit en second recours. Les laisser passer ferait mesurer le canal qu'on
        # croit avoir retire -- un repere qui ne repere rien.
        if nom == "units":
            return ()
        return getattr(self._sc, nom)


def _non_regression(units, sc, adj) -> int:
    """Sur une unite MONO-PIED, le capteur ne doit RIEN changer : `feet == [MainTile]` et
    `iterate_tiles` doit rendre EXACTEMENT `[scene.pos(uid)]`, le comportement d'avant. Rend le
    nombre d'ECARTS."""
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
        p = sc.pos(uid)
        attendu = [] if p is None else [(p[0], p[1])]
        if len(f) == 1:
            if got != attendu:
                ecarts += 1
                print("  ECART u%s : feet=%r iterate_tiles=%r attendu=%r" % (uid, f, got, attendu))
        else:
            print("  u%s est MULTI-PIED (%d) : feet=%r" % (uid, len(f), f))
    print("  %d unite(s) a canal mesure ; %d ecart(s) sur les mono-pied" % (vus, ecarts))
    return ecarts


def _spawner_le_summon(rpc, rid: int) -> "dict | None":
    """Fait apparaitre `ultraSmnDreadnought` (3 hexes) en castant `DutyEternal` depuis la MoW.

    Rend le dict d'unite du summon (tel que `decisionView.units` le porte), ou leve `MontageError`.
    Le cast se fait `casterId = machineId` : `abilityTargets` scanne les casters
    `EntityType.Machine` en plus des `EntityType.Unit`, et `applyAction {kind:"ability"}` execute
    la cascade native complete (`case-mow-offboard-cast.md` §1)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 180)
    m = next((x for x in (dv.get("mows") or [])
              if str(x.get("visualId") or "").lower() == MOW_SUMMONER.lower()), None)
    if m is None:
        raise MontageError("montage NON INSTALLE : %s absent de `decisionView.mows` (vus : %s)"
                           % (MOW_SUMMONER, sorted({str(x.get("visualId"))
                                                    for x in (dv.get("mows") or [])})))
    caster = m["casterId"]
    avant = {u.get("id") for u in (dv.get("units") or [])}
    at = rpc("abilityTargets",
             {"runnerId": rid, "unitId": caster, "abilityType": ABILITY_DUTY_ETERNAL}, 120) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
    print("  caster MoW u%s slot=%s | %d cible(s) legale(s) pour %d"
          % (caster, m.get("slot"), len(tgts), ABILITY_DUTY_ETERNAL))
    if not tgts:
        raise MontageError("aucune cible legale pour `DutyEternal` -- le summon ne peut pas "
                           "apparaitre, donc AUCUN porteur multi-tuiles n'entre en jeu")
    pick = next((t for t in tgts if t.get("kind") == "tile"), None) or tgts[0]
    action = {"kind": "ability", "casterId": caster, "abilityType": ABILITY_DUTY_ETERNAL}
    if pick.get("kind") == "unit":
        action["targetId"] = pick["targetId"]
    else:
        action["to"] = {"col": pick["tile"]["col"], "row": pick["tile"]["row"]}
    res = rpc("applyAction", {"runnerId": rid, "action": action}, 150) or {}
    act = (res.get("actions") or [{}])[0]
    if not act.get("ok") or act.get("error"):
        raise MontageError("le cast a echoue : %s" % (act.get("error") or act))
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 180)
    neufs = [u for u in (dv2.get("units") or []) if u.get("id") not in avant]
    print("  cast OK | %d unite(s) NEUVE(S) : %s"
          % (len(neufs), [(u.get("id"), u.get("visualId")) for u in neufs]))
    smn = next((u for u in neufs
                if str(u.get("visualId") or "").lower() == SUMMON_MULTI_HEX.lower()), None)
    if smn is None:
        raise MontageError("le cast n'a fait apparaitre aucun `%s` -- le porteur multi-tuiles "
                           "n'est pas en jeu, il n'y a rien a mesurer" % SUMMON_MULTI_HEX)
    return {"summon": smn, "dv": dv2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU, propre")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--mow", default="adeptExorcist", help="MoW du pool (rl_duel build --list-pool)")
    ap.add_argument("--roster", type=int, default=5)
    ap.add_argument("--summon", action="store_true",
                    help="MONTAGE QUI PORTE LE CRITERE : au lieu de viser une MoW (qui reste "
                         "HORS PLATEAU et dont `GetTiles` rend [] legitimement), spawner "
                         "`ultraSmnDreadnought` (3 hexes) via `DutyEternal` d'`ultraDreadnought` "
                         "et lire son `units[].feet`")
    a = ap.parse_args()
    if a.summon:
        a.mow = MOW_SUMMONER

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

        if a.summon:
            print("")
            print("=== etape 1 -- ATTESTATION : spawn d'un porteur MULTI-HEX ===")
            r = _spawner_le_summon(rpc, rid)
            smn, units = r["summon"], (r["dv"].get("units") or [])
            uid = smn.get("id")
            feet = smn.get("feet")
            print("  summon u%s %s pos=%s" % (uid, smn.get("visualId"), _pos(smn)))
            print("  `feet` (GetTiles sur l'entite Unit) = %r" % (feet,))
            if feet is None:
                raise MontageError("`feet` est NULL (tri-etat : capteur MUET) -- la methode n'a "
                                   "pas ete resolue, ou l'invocation a leve. Ce n'est PAS "
                                   "<< aucune tuile >>, c'est << pas mesure >>.")
            if len(feet) <= 1:
                raise MontageError(
                    "le summon n'a que %d tuile(s) : ce montage ne porte AUCUN porteur "
                    "multi-tuiles, donc il ne peut RIEN conclure sur le canal." % len(feet))
            print("  -> porteur MULTI-TUILES atteste : %d tuiles" % len(feet))
            print("")
            print("=== etape 2 -- ce que la Scene de DECISION porte ===")
            sc = _scene_du_pas(rpc, rid, r["dv"])
            tbl = getattr(sc, "feet_by_id", None) or {}
            print("  scene.feet_by_id : %d entree(s)" % len(tbl))
            print("  entree pour u%s : %r" % (uid, tbl.get(int(uid))))
            tiles = adj.iterate_tiles(sc, uid)
            print("  adjacency.iterate_tiles(u%s) -> %r  (cardinal %d)" % (uid, tiles, len(tiles)))
            voisins = adj.adjacent_positions(sc, uid)
            print("  adjacency.adjacent_positions -> %d tuile(s) : %r"
                  % (len(voisins), sorted(voisins)))
            # Le voisinage d'UNE seule tuile, c'est-a-dire le port d'AVANT le capteur. L'ecart
            # entre les deux EST la valeur ajoutee du canal, chiffree.
            mono = adj.adjacent_positions(_ScenePos(sc), uid)
            print("  (repere) voisinage si on ne lisait que la MainTile : %d tuile(s)" % len(mono))
            ecarts = _non_regression(units, sc, adj)
            print("")
            print("=== etape 4 -- verdict ===")
            if len(tiles) == len(feet) and len(tiles) > 1 and ecarts == 0:
                print("CANAL PRESENT : %d tuiles publiees ET lues (contre 1 avant le capteur) ;"
                      % len(tiles))
                print("  le voisinage passe de %d a %d tuiles. NON-REGRESSION tenue sur les"
                      % (len(mono), len(voisins)))
                print("  unites mono-pied (0 ecart).")
                return 0
            print("ECHEC : feet=%d iterate_tiles=%d ecarts_mono_pied=%d"
                  % (len(feet), len(tiles), ecarts))
            return 1

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
        sc = _scene_du_pas(rpc, rid, dv)
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
        ecarts = _non_regression(units, sc, adj)

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
