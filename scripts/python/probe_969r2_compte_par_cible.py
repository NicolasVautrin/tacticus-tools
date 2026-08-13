#!/usr/bin/env python
"""#969-r2 -- le COMPTE PAR CIBLE de `DeathFromAbove` (1003), releve DES DEUX COTES.

LA QUESTION, ET POURQUOI ELLE NE SE FITTE PAS
---------------------------------------------
#969 a mesure que le natif caste `1003` sur `u77` la ou le port le caste sur `u114`. L'utilite est
`GetNumPossibleSpawnTilesForTarget(cible)` = `Count(CanAddUnit(AdjacentTiles(cible)))`, un ENTIER
PAR CIBLE. Comparer les deux CHOIX ne dit rien : c'est un argmax, et deux causes distinctes
produisent le meme symptome.

  (a) SUR-COMPTE  -- `_spawn_tiles` rend pour `u114` un nombre PLUS GRAND que le natif (son
                     `occupied` ne connait que `epos`/`fpos`/l'origine).
  (b) ORDRE       -- les comptes sont EGAUX et c'est l'ordre d'enumeration qui departage
                     (`Bucket$$AddAction` remplace sur `>` STRICT : keep-first).
  (c) ENSEMBLE    -- le port et le natif n'enumerent pas les MEMES cibles.

Le discriminant est donc le COMPTE, cible par cible, releve des DEUX cotes -- jamais le choix.

CE QUE CHAQUE COTE PUBLIE
--------------------------
* NATIF -- `ncEvaluate` (`rpc-predict.ts`) invoque le wrapper `Evaluate` du playbook et decode le
  Bucket. Par position il rend `util` (= l'utilite de l'action retenue, donc le compte de la cible
  gagnante), `action.targetLow` (la CIBLE retenue) et `actionCount` (le nombre d'actions du bucket,
  donc le CARDINAL de `GetEligibleTargetsSelectable`). Trois grandeurs, pas une.
* PORT -- `DeathFromAbovePlaybook._spawn_tiles(ctx, pos)` evalue pour CHAQUE cible eligible ; le
  probe imprime la table complete, et pas seulement l'argmax que `generate_candidates` rend.

L'APPARIEMENT est ce qui tranche :

    util_natif  ==  port[cible_natif]   ?   -> le compte du port est JUSTE sur la cible du natif
    port[cible_port] > util_natif       ?   -> (a) SUR-COMPTE : le port croit voir plus de tuiles
    port[cible_port] == util_natif      ?   -> (b) ORDRE : egalite, keep-first diverge
    cardinaux differents                ?   -> (c) ENSEMBLE

REGIME DEGENERE -- REFUSE, PAS RAPPORTE
----------------------------------------
Si le bucket natif ne porte qu'UNE SEULE action, ou si toutes les cibles ont le meme compte, le
montage ne DEPARTAGE rien : (a) et (b) y rendent le meme resultat. Le probe l'ecrit et sort en
`rc 2` (NON CONFRONTE), il ne rend pas un accord qui ne prouve rien.

AMPLITUDE -- DEUX BOARDS AU MOINS
----------------------------------
La geometrie est le sujet meme du residu : un seul board ne borne rien (facteur 9 a 14 mesure sur
d'autres grandeurs). Les fixtures nommees en portent deux, jouees toutes les deux par defaut.

Usage :
    python probe_969r2_compte_par_cible.py                 # les deux boards
    python probe_969r2_compte_par_cible.py --board MC1_67  # un seul
    python probe_969r2_compte_par_cible.py --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

ABILITY_DFA = 1003          # `ActiveAbilityType.DeathFromAbove` -- porteur `ultraInceptorSgt`

# --- FIXTURES NOMMEES (jamais de montage inline) -------------------------------------------------
#
# Le caster est le porteur LU de 1003. Les adversaires sont choisis pour offrir PLUSIEURS cibles a
# des distances differentes : c'est ce qui donne des comptes de tuiles distincts, donc un montage
# NON degenere. Deux boards -- une amplitude ne s'estime pas depuis un seul.
FIXTURES = (
    {"nom": "MC1_67", "board": "MC1_67", "seed": 777, "rank": 17,
     "caster": "ultraInceptorSgt",
     "p_units": "ultraInceptorSgt,ultraTitus",
     "a_units": "necroWarden,necroWarden,astraBullgryn"},
    {"nom": "MC1_39", "board": "MC1_39", "seed": 777, "rank": 17,
     "caster": "ultraInceptorSgt",
     "p_units": "ultraInceptorSgt,ultraTitus",
     "a_units": "necroWarden,necroWarden,astraBullgryn"},
)


def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc          # noqa: E402
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=90):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, fx: dict) -> int:
    """`rl_duel build` -- board CHOISI (runner.md sec.2), state-file ABSOLU dans logs/."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(fx["seed"]),
           "--state-file", str(state_file), "--board", fx["board"], "--rank", str(fx["rank"]),
           "--p-units", fx["p_units"], "--a-units", fx["a_units"], "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _nc_ctx(rpc1, sid, rid, dv, cid):
    """La MEME NCContext que le moteur monte en decision (`engine.ai.context.build`) -- jamais un
    contexte fabrique a la main, qui ne mesurerait que lui-meme."""
    from engine.playbook import scene as scene_mod
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as playbooks

    predictor = scene_mod.build_predictor(rpc1, rid)
    mov = _r(rpc1.__self__ if hasattr(rpc1, "__self__") else None, sid, "aiMovableTiles",
             {"runnerId": rid}, 60) if False else None
    return predictor, playbooks, _ai_ctx, W


def _port_counts(ctx, playbooks, ability: int) -> "tuple[dict, list]":
    """{cible: compte} pour TOUTES les cibles eligibles du port -- la table complete, pas l'argmax.

    L'enumeration est celle de `generate_candidates` (`_targets.eligible_units` = `fromHere`) : on
    mesure ce que le port VOIT, pas ce qu'on voudrait qu'il voie."""
    from engine.playbook.noncomparable import _targets as T
    pb = playbooks.playbook_for(ability)
    if pb is None:
        return {}, []
    ordre = []
    table = {}
    for tid, pos in T.eligible_units(ctx, ability):
        if pos is None:
            continue
        n = pb._spawn_tiles(ctx, tuple(pos))
        table[int(tid)] = int(n)
        ordre.append(int(tid))
    return table, ordre


def _verdict(natif: dict, table: dict, ordre: list) -> dict:
    """L'appariement de l'en-tete, terme a terme. Rend `hypothese` parmi
    `sur-compte` / `sous-compte` / `ordre` / `ensemble` / `accord`, ou `degenere`."""
    util_n = natif.get("util")
    cible_n = natif.get("cible")
    card_n = natif.get("actionCount")
    if not table:
        return {"hypothese": "degenere", "raison": "le port n'enumere AUCUNE cible eligible"}
    cible_p = max(ordre, key=lambda t: (table[t], -ordre.index(t))) if ordre else None
    # keep-first STRICT : a egalite le PREMIER enumere gagne -> on re-derive comme le port
    best_p, cible_p = None, None
    for t in ordre:
        if best_p is None or table[t] > best_p:
            best_p, cible_p = table[t], t
    out = {"cible_natif": cible_n, "util_natif": util_n, "cardinal_natif": card_n,
           "cible_port": cible_p, "util_port": best_p, "cardinal_port": len(table),
           "table_port": dict(table), "ordre_port": list(ordre)}
    valeurs = sorted(set(table.values()))
    if len(table) < 2 or len(valeurs) < 2:
        out["hypothese"] = "degenere"
        out["raison"] = ("le montage ne DEPARTAGE rien : %d cible(s), %d valeur(s) distincte(s)"
                         % (len(table), len(valeurs)))
        return out
    if card_n is not None and int(card_n) != len(table):
        out["hypothese"] = "ensemble"
        out["raison"] = ("cardinaux DIFFERENTS : natif %s actions, port %d cibles"
                         % (card_n, len(table)))
        return out
    port_sur_cible_native = table.get(int(cible_n)) if cible_n is not None else None
    out["port_sur_cible_native"] = port_sur_cible_native
    if cible_n is not None and cible_p == cible_n:
        out["hypothese"] = "accord"
        out["raison"] = "les deux cotes retiennent la MEME cible"
        return out
    if util_n is None or port_sur_cible_native is None:
        out["hypothese"] = "degenere"
        out["raison"] = "l'oracle natif n'a pas rendu d'utilite exploitable"
        return out
    if best_p > util_n:
        out["hypothese"] = "sur-compte"
        out["raison"] = ("le port compte %d tuiles pour u%s, or le MAX natif vaut %s"
                         % (best_p, cible_p, util_n))
    elif abs(best_p - util_n) < 1e-9:
        out["hypothese"] = "ordre"
        out["raison"] = ("EGALITE a %s : les deux cibles ont le meme compte, seul l'ordre "
                         "d'enumeration departage" % util_n)
    else:
        out["hypothese"] = "sous-compte"
        out["raison"] = ("le port plafonne a %d alors que le natif atteint %s"
                         % (best_p, util_n))
    if abs((port_sur_cible_native or -1) - util_n) > 1e-9:
        out["compte_divergent_sur_cible_native"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default=None, help="ne jouer qu'un board (defaut : les deux)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    fixtures = [f for f in FIXTURES if a.board is None or f["board"] == a.board]
    if not fixtures:
        print("[969-r2] board inconnu : %s" % a.board)
        return 2
    print("[969-r2] TODO -- corps de mesure a cabler (voir --help)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
