#!/usr/bin/env python
"""#1081 (pour `#961-r3`) -- << 1475 n'est PAS dans `decisionView.effects`, ni actif ni inactif >> :
la mesure qui tranche, et le PIEGE D'ENUM que la fiche portait.

CE QUE LA FICHE AFFIRMAIT, ET POURQUOI CE N'ETAIT PAS MESURE
============================================================

`#961-r3` accuse le premier etage : le `decisionView` de la capture ne publierait pour la cible ni
`1475` actif ni `1475` inactif, d'ou deux causes possibles -- (a) l'effet est CONDITIONNEL et
inactif a l'instant de la capture, (b) le capteur ne le publie pas (⇒ fenetre de reinject).

Deux defauts de MESURE, tous deux verifiables sans aucune fenetre :

  1. **Le drapeau n'etait pas demande.** `probe_961_necron_passives.dv()` envoyait
     `{runnerId, maxRank[, allAbilities]}` sans `includeInactive`, dont le defaut est FAUX : le
     canal FILTRE donc les inactifs. L'absence constatee etait celle d'un champ jamais demande --
     elle ne pouvait pas distinguer (a) de (b).

  2. **L'ordinal cherche n'est pas dans l'enum du canal.** `decisionView.effects[]` publie des
     `EffectType`. Or `1475` est un **`TriggeredAbilityType`** (`SupaCyborkBody`, l'ABILITY) ;
     l'EFFET qu'elle pose est `EffectType 1468 = SupaCyborkBody_CritDmgReduction`. Chercher 1475
     dans ce canal ne peut rien rendre, quel que soit le drapeau -- et une absence constatee sur le
     mauvais ordinal ne prouve rien. Les deux membres sont LUS dans
     `data/symbols/<build>/frida/enums.tsv`.

CE QUE CE PROBE MESURE
======================

Un runner minimal portant `orksRuntherd` (porteur de la relique `SupaCyborkBody`, EQUIPEE AU SEED
d'apres `data/seed-bc.json` -- etat 1 des trois etats d'une relique, donc aucun montage), puis
`decisionView` demande DEUX fois, a etat identique : sans `includeInactive`, puis avec. On compte
les instances de **1468** (et, en temoin, de 1475, qui doit rester introuvable des deux cotes).

La table de verite est explicite :

    1468 absent des DEUX vues        -> cause (b) : le capteur ne le publie pas -> FENETRE
    1468 present avec le drapeau      -> cause (a) : pose mais INACTIF a la capture -> aucune fenetre
    1468 present dans les DEUX vues   -> il etait ACTIF : l'enonce d'origine est faux sur les faits

Usage (depuis scripts/python) :
    python probe_1081_supacybork_inactif.py [--seed 777] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import probe_961_necron_passives as P                                      # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402

EX_OK = 0
EX_ROUGE = 1
EX_NON_MESURE = 99

#: `EffectType` 0x5bc = 1468 -- l'EFFET pose par la relique. C'est LUI que publie le canal.
EFFET = int(EffectType.SupaCyborkBody_CritDmgReduction)
#: `TriggeredAbilityType` 1475 -- l'ABILITY. Cherche ici en TEMOIN : il ne doit apparaitre dans
#: AUCUNE des deux vues, puisque ce canal ne publie pas cet enum-la.
ABILITY_ORDINAL = 1475

PORTEUR = "orksRuntherd"


def _effets(view, ordinal):
    """Toutes les instances de `ordinal` publiees par la vue, avec leur drapeau `active`."""
    out = []
    for u in (view.get("units") or []):
        for e in (u.get("effects") or []):
            if int(e.get("effectType") or e.get("type") or -1) == int(ordinal):
                out.append({"unit": u.get("id"), "visual": u.get("visualId"),
                            "active": e.get("active"), "level": e.get("level")})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    a = ap.parse_args(argv)

    from rl_collect_batch import _resolve_session
    try:
        sid = _resolve_session()
    except Exception as exc:
        print("[1081] NON MESURE -- aucune session Frida lisible : %s" % exc)
        return EX_NON_MESURE
    if not sid:
        print("[1081] NON MESURE -- aucune session Frida lisible.")
        return EX_NON_MESURE

    state = P.ROOT / "logs" / "runners" / "_1081_supacybork.json"
    rid = P.build(a.seed, a.board, [PORTEUR], ["orksNob"], state)
    if rid is None:
        print("[1081] NON MESURE -- build KO (voir stderr).")
        return EX_NON_MESURE
    try:
        sans = P.dv(sid, rid)
        avec = P.dv(sid, rid, inactifs=True)

        n_sans, n_avec = _effets(sans, EFFET), _effets(avec, EFFET)
        t_sans, t_avec = _effets(sans, ABILITY_ORDINAL), _effets(avec, ABILITY_ORDINAL)

        print("[1081] porteur %s ; board %s ; seed %d" % (PORTEUR, a.board, a.seed))
        print("   unites publiees : sans=%d avec=%d"
              % (len(sans.get("units") or []), len(avec.get("units") or [])))
        print("   EffectType %d (SupaCyborkBody_CritDmgReduction)" % EFFET)
        print("      sans includeInactive : %d instance(s) %s" % (len(n_sans), n_sans))
        print("      avec includeInactive : %d instance(s) %s" % (len(n_avec), n_avec))
        print("   TEMOIN -- ordinal %d (TriggeredAbilityType, PAS un EffectType)" % ABILITY_ORDINAL)
        print("      sans=%d avec=%d  (doit valoir 0 des deux cotes)" % (len(t_sans), len(t_avec)))

        if t_sans or t_avec:
            print("[1081] ROUGE -- le canal publie l'ordinal 1475 : la separation des deux enums")
            print("        supposee par ce probe est FAUSSE, tout le raisonnement est a refaire.")
            return EX_ROUGE

        print()
        if not n_sans and not n_avec:
            print("[1081] VERDICT -- cause (b) : 1468 absent des DEUX vues. Le drapeau ne le fait")
            print("        pas apparaitre => le capteur ne le publie pas. FENETRE justifiee.")
        elif n_avec and not n_sans:
            print("[1081] VERDICT -- cause (a) : 1468 n'apparait QU'AVEC includeInactive => il est")
            print("        POSE mais INACTIF a la capture. AUCUNE fenetre n'est necessaire ; ce")
            print("        qu'il faut est un montage d'ETAT (amener un ennemi au contact).")
        else:
            print("[1081] VERDICT -- 1468 est publie SANS le drapeau (donc ACTIF a la capture) :")
            print("        l'enonce << ni actif ni inactif >> est faux sur les faits.")
        return EX_OK
    finally:
        if not a.keep:
            P.dispose(sid, rid)


if __name__ == "__main__":
    raise SystemExit(main())
