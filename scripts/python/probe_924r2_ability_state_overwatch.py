"""#924-r2 -- QUEL `AbilityState` le natif donne-t-il a `ConfigVar(extraDmg)` d'`InescapableDeath` ?

CE QUE CE PROBE FERME. #924-r2 mesure un ecart entre le bonus de degat d'overwatch applique par le
natif (`+617,3` par coup) et celui que produirait le port (`+898,0` par coup, EXACTEMENT). L'ecart
etait attribue a un ETAGE ; cette attribution est REFUTEE (#1084 : le decompile place l'additif au
meme endroit que le port, et la mesure d'origine etait prise en regime DEGENERE -- a armure nulle,
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
est l'IDENTITE, donc les deux positions rendent le meme nombre).

Reste la MAGNITUDE. Et elle a un candidat CHIFFRE, pas une piste vague :

    gameconfig `InescapableDeath.extraDmg[level 50]` = 499
    499 x multiplicateur 180 %                       = 898   <- EXACTEMENT l'ecart du port
    499 x multiplicateur 100 %                       = 499
    499 x multiplicateur 120 %                       = 599

Le port lit donc `level = 50, mult = 180`. Le natif, lui, applique `+617,3` -- une MOYENNE sur six
tirages, dont l'incertitude (ecart-type d'environ 45 sur la difference de deux moyennes de six
coups d'etendue ~220) place `499` et `599` DANS l'intervalle et `898` a plus de six sigmas.

⚠ C'est un ARGUMENT, pas une mesure : un ecart de moyennes ne peut pas designer un couple
(niveau, multiplicateur). CE PROBE MESURE LE COUPLE, en lisant le canal `unitAbilityStates` --
le MEME canal qui a etabli, pour #1005, qu'une relique EQUIPEE tourne a `level = 1, mult = 100`
quand ses passifs sont a `level = 50, mult = 180`. Si `InescapableDeath` tourne a un couple autre
que `(50, 180)`, la cause est LOCALISEE et le residu se ferme sur une correction de magnitude.

RESULTAT MESURE (2026-08-14, board `MC1_67` / seed 777, runner dedie, `necroDestroyer` entite 79) :

    entite 79   level=50   mult=180   -> extraDmg = 898

⇒ **LA PISTE `AbilityState` EST REFUTEE.** Le natif donne a `InescapableDeath` EXACTEMENT le couple
que le port lit, et donc exactement la meme valeur de variable : `898`. Ni l'etage d'injection
(refute par #1084), ni la magnitude de la variable ne peuvent expliquer l'ecart.

CE QU'IL RESTE, ET LA MESURE QUI MANQUE. Le natif DISPOSE de 898 et n'ajoute pourtant que `+617,3`
par coup : le 898 subit donc, cote natif, une transformation multiplicative d'environ `0,687` que
le bras du port ne lui applique pas. Le candidat est le PERCAGE :
`…StaticBattleRules.Damage$$GetDamageWithPiercing` rend `max(0, d - armure, d x p/100)`, un facteur
`p/100` des que le percage DOMINE -- et `628,7 / 906 = 0,694` est exactement la signature d'un
`p = 70` en regime pierced. Or #924 affirme << armure 0 des deux cotes >>, ce qui rendrait cette
fonction IDENTIQUE et interdirait tout facteur. **C'est cette affirmation-la qu'il faut
re-mesurer**, et c'est la mesure qui manque :

    rejouer le montage d'overwatch d'Imospekh en instrumentant les ETAGES des deux cotes --
    `pierce` effectif, `armure` effective de la cible, bornes brutes, %-mods -- au lieu de comparer
    deux MOYENNES de six tirages. Si le regime est `pierced`, l'additif natif vaut `898 x p/100`
    (~629 pour p=70, compatible avec 617,3 a l'incertitude pres) et c'est alors l'ecart PORT de
    << 898,0 EXACTEMENT >> qui est anormal : il signifierait que le bras mutant du port ne traverse
    pas le meme chemin de percage que son bras nominal.

Sortie ASCII stricte (cp1252). Un runner, dispose en sortie.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ABILITY = "InescapableDeath"
#: `InescapableDeathEffect$$.ctor` = `AReactivateOverwatchEffect..ctor(this, 0x3ed)` -- l'ability
#: dont l'effet lit la config, donc celle dont `unitAbilityStates` porte le couple (niveau, mult).
ABILITY_ID = 0x3ed          # 1005
VAR = "extraDmg"
#: le porteur du passif -- `necroDestroyer` (Imospekh).
PORTEUR = "necroDestroyer"
#: l'ecart PORT mesure par #924 : `5388 / 6 coups`.
ECART_PORT = 898.0
#: l'ecart NATIF mesure par #924 : `1246,0 - 628,7`.
ECART_NATIF = 617.3


class MontageError(RuntimeError):
    pass


def build(state_file: str, board: str, seed: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            "--board", board, "--p-units", PORTEUR, "--a-units", "astraBullgryn"]
    p = subprocess.run(argv, capture_output=True, text=True)
    if p.returncode != 0:
        raise MontageError("rl_duel build a echoue (rc=%s) : %s" % (p.returncode, p.stderr[-800:]))
    import json
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--runner", type=int, default=None)
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = args.runner or build(args.state_file, args.board, args.seed)
    print("[924-r2] runner %s | board %s seed %s | porteur %s" % (rid, args.board, args.seed, PORTEUR))
    try:
        res = rpc("unitAbilityStates", {"runnerId": rid}, 120) or {}
        # ⚠ `raw[0]` est un ORDINAL, pas un nom -- mesure du 2026-08-14 : le canal rend
        # `[abilityId, .., .., .., level, mult]`. Filtrer par NOM y rend un faux << non mesure >>.
        trouve = []
        for u in res.get("units") or []:
            for t in (u.get("triggered") or []) + (u.get("active") or []) + (u.get("passive") or []):
                raw = t.get("raw") or []
                if raw and int(raw[0]) == ABILITY_ID:
                    trouve.append({"entityId": u.get("entityId"),
                                   "level": raw[4] if len(raw) > 4 else None,
                                   "mult": raw[5] if len(raw) > 5 else None,
                                   "raw": raw})
        if not trouve:
            print("[924-r2] NON MESURE : aucune entree `%s` dans `unitAbilityStates`." % ABILITY)
            print("           Ce n'est PAS un zero : le canal n'a pas repondu pour cette ability.")
            print("           Entrees vues (echantillon) :")
            for u in (res.get("units") or [])[:2]:
                for k in ("triggered", "active", "passive"):
                    for t in (u.get(k) or [])[:4]:
                        print("             %-9s %s" % (k, (t.get("raw") or [t])[:6]))
            return 3

        from engine.entities.effects.magnitude import ability_var
        print("[924-r2] ETAT MESURE de `%s` :" % ABILITY)
        for row in trouve:
            lv, mu = row["level"], row["mult"]
            val = ability_var(ABILITY, VAR, lv, multiplier_pct=mu) if lv is not None else None
            print("    entite %-4s level=%-4s mult=%-5s -> %s = %s"
                  % (row["entityId"], lv, mu, VAR, val))
            if val is not None:
                print("        ecart PORT  attendu %s -> %s" % (ECART_PORT, "CONCORDE" if abs(val - ECART_PORT) < 1 else "DIVERGE"))
                print("        ecart NATIF mesure  %s -> %s" % (ECART_NATIF, "COMPATIBLE" if abs(val - ECART_NATIF) < 120 else "INCOMPATIBLE"))
        return 0
    finally:
        if args.runner is None:
            try:
                _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
                print("[924-r2] runner %s dispose" % rid)
            except Exception as exc:                      # pragma: no cover - nettoyage best effort
                print("[924-r2] dispose ECHOUE : %s" % exc)


if __name__ == "__main__":
    sys.exit(main())
