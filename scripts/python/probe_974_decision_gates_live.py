#!/usr/bin/env python
"""#974 -- les DEUX faits que le decompile ne peut PAS trancher pour ce lot, mesures a la VTABLE.

CE QUE CE PROBE MESURE (vue vtable = verite terrain, meme methode que #170 / #350-r3)
  * `pbSlots(<ability>)` -> la CLASSE de playbook que le natif charge, et le nom de chaque slot.
  * `pbGate(slot=1)`     -> `get_IsComparable` : l'ability est-elle Comparable ou NonComparable ?
  * `pbGate(slot=4)`     -> `ShouldEvaluate` : le gate AMONT du generateur.

POURQUOI IL EXISTE -- deux absences qui NE CONCLUENT PAS, et qui n'ont pas la meme nature
  1. **Le gate de tour de `1198 EuphoricStrikes` (residu `#974-r1`).** Le corps
     `GetStat(unit, 0xc = TurnsStarted) > 1` est un COMDAT unique (ghidra l'etiquette
     `AlphaWarriorPlaybook$$ShouldEvaluate`, refcount 7) : son absence sous le nom de la classe
     `EuphoricStrikesPlaybook` ne prouve donc RIEN. Le port pose le defaut PERMISSIF (True
     constant) ; si la mesure rend `0` au PREMIER tour du porteur, il faut brancher
     `_base._turns_started_gate` -- sinon le port proposerait l'ability un tour trop tot.
     ⚠ Contraste avec `ShouldExecute`, ou l'absence CONCLUT : les corps de cette famille-la lisent
     CHACUN le static de LEUR classe, donc ils sont deux a deux distincts, donc non dedupliquables
     et tous nommes.
  2. **La BASE de `1195` et `1198`.** Elle est LUE dans `frida/classes.tsv`
     (`ComparablePlaybook`1` / `NonComparablePlaybook`1`), jamais dans le nom du `.ctor` -- que
     ghidra rend `ComparablePlaybook<...>$$.ctor` pour les DEUX, corps trivial dedupli-que par ICF.
     `get_IsComparable` invoque a la vtable est la seconde source, INDEPENDANTE, qui la recoupe.

CE QU'IL NE PRETEND PAS FAIRE
  Il ne confronte AUCUNE utilite ni aucune prediction de degat : il ne repond qu'a « quelle classe,
  quel regime, quel gate ». La fidelite des valeurs se garde offline (`test_974_*_offline.py`).

TRI-ETAT : 0 = mesure faite et conforme ; 1 = mesure faite et DIVERGENTE ; 2 = PAS MESURE (session
ou runner indisponible) -- jamais rabattu sur un vert.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc    # noqa: E402

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/**/*.py", "scripts/python/probe_974_*.py"),
    "build": True,          # il invoque des SLOTS de vtable : un renumerotage d'interface le perime
    "toujours": False,
    "raison": "Il n'interroge que la vtable des playbooks du lot (classe, get_IsComparable, "
              "ShouldEvaluate) ; seuls la couche playbook et le build peuvent en changer le "
              "verdict.",
}

#: `(abilityType, porteur, regime ATTENDU par le port)`. Le regime est celui que le port a INSCRIT,
#: pas celui qu'on espere : le probe est la pour le CONTREDIRE si le natif dit autre chose.
CIBLES = (
    (1195, "custoAtlacoya", True),    # `ComparablePlaybook`1` (classes.tsv) -> Comparable
    (1198, "emperExultant", False),   # `NonComparablePlaybook`1` (classes.tsv) -> NonComparable
)


def r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _bool_natif(g) -> bool | None:
    """Decode un `System.Boolean` rendu par `pbGate`.

    ⚠ **`retRaw` est une CHAINE HEXADECIMALE** (`ret.toString(16)` cote hook), pas un entier : un
    `bool(g["retRaw"])` rend `True` pour TOUTE reponse, y compris `"0"`. C'est la faute que ce
    probe a commise a son premier tir -- il a annonce une divergence `get_IsComparable` sur
    `1198` qui n'existait pas, et qui aurait fait deplacer un port JUSTE. Le hook publie
    `retLow` = les 8 bits de poids faible, exactement la largeur d'un `bool` C# ; c'est LUI qui
    porte la valeur. Absent -> `None` = PAS MESURE, jamais un `False` fabrique."""
    v = g.get("retLow")
    return None if v is None else bool(int(v) & 0xff)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runner", required=True, type=int)
    ap.add_argument("--unit", required=True, type=int,
                    help="entityId du PORTEUR sur lequel invoquer les slots")
    ap.add_argument("--ability", required=True, type=int)
    args = ap.parse_args(argv)

    try:
        sid = _resolve_session()
    except Exception as exc:                                  # noqa: BLE001
        print("[974] PAS MESURE -- session Frida indisponible : %s" % exc)
        return EX_PAS_MESURE
    if not sid:
        print("[974] PAS MESURE -- aucune session Frida")
        return EX_PAS_MESURE

    attendu = next((c for c in CIBLES if c[0] == args.ability), None)
    if attendu is None:
        print("[974] PAS MESURE -- ability %d hors du lot #974" % args.ability)
        return EX_PAS_MESURE

    sl = r(sid, "pbSlots", {"runnerId": args.runner, "abilityType": args.ability,
                            "maxSlots": 6}, 60)
    klass = sl.get("playbookClass")
    itf = next((i for i in (sl.get("interfaces") or []) if i.get("slots")), None)
    noms = [x.get("name") for x in ((itf or {}).get("slots") or [])]
    if not klass:
        print("[974] PAS MESURE -- `pbSlots` n'a rendu aucune classe (runner %d, ability %d)"
              % (args.runner, args.ability))
        return EX_PAS_MESURE
    print("[974] ability %d : classe = %s" % (args.ability, klass))
    print("[974]   slots 0..%d = %s" % (len(noms) - 1, noms))

    ko = 0
    # -- (1) le REGIME, recoupe par une seconde source independante de `classes.tsv` --
    g1 = r(sid, "pbGate", {"runnerId": args.runner, "unitId": args.unit,
                           "abilityType": args.ability, "itf": "Playbook", "slot": 1,
                           "args": []}, 40)
    if not g1.get("ok"):
        print("[974]   get_IsComparable : PAS MESURE (%s)" % (g1.get("error") or "invocation KO"))
        return EX_PAS_MESURE
    comparable = _bool_natif(g1)
    if comparable is None:
        print("[974]   get_IsComparable : PAS MESURE (`retLow` absent de la reponse)")
        return EX_PAS_MESURE
    print("[974]   get_IsComparable = %s (retRaw=%s hex ; port : %s)"
          % (comparable, g1.get("retRaw"), attendu[2]))
    if comparable != attendu[2]:
        print("[974]   DIVERGENCE : le port a inscrit l'ability du MAUVAIS cote du dispatch")
        ko += 1

    # -- (2) le GATE de tour (`#974-r1` pour 1198) --
    g4 = r(sid, "pbGate", {"runnerId": args.runner, "unitId": args.unit,
                           "abilityType": args.ability, "itf": "Playbook", "slot": 4,
                           "args": []}, 40)
    if not g4.get("ok"):
        print("[974]   ShouldEvaluate  : PAS MESURE (%s)" % (g4.get("error") or "invocation KO"))
        print("[974]   -> le residu #974-r1 reste OUVERT, et le port garde son defaut PERMISSIF")
        return EX_PAS_MESURE if ko == 0 else EX_ROUGE
    evalue = _bool_natif(g4)
    if evalue is None:
        print("[974]   ShouldEvaluate  : PAS MESURE (`retLow` absent de la reponse)")
        return EX_PAS_MESURE
    print("[974]   ShouldEvaluate (slot 4, nom natif = %r) = %s (retRaw=%s hex)"
          % (noms[4] if len(noms) > 4 else "?", evalue, g4.get("retRaw")))
    # -- (3) LE TEMOIN, sans lequel (2) ne prouve RIEN --------------------------------------
    # `ShouldEvaluate = True` est une preuve d'ABSENCE de gate de tour SEULEMENT si, a cet instant,
    # un playbook qui PORTERAIT ce gate rendrait `False` -- c'est-a-dire si `turnsStarted == 1`.
    # Sinon c'est un accord en regime DEGENERE, qui ne vaut rien.
    #
    # ⚠ LE TEMOIN NE PEUT PAS ETRE UNE AUTRE ABILITY. Mesure : `pbGate(slot=4)` sur `1202`, `1112`
    # et `1151` -- les trois porteurs CONNUS du corps folde -- rend `access violation accessing
    # 0xffffffffffffffff` pour les trois, parce qu'aucun de leurs porteurs n'est dans CETTE
    # bataille : leur playbook n'a jamais recu `Init`, donc son `this@+0x20 = state` est nul. Un
    # temoin qui CRASHE ne discrimine rien. Le temoin est donc la STAT ELLE-MEME, lue au meme
    # instant sur le meme porteur (`combatSnapshot`, index de `TurnsStarted` resolu par
    # `statTypes`, jamais code en dur).
    # ⚠ `units[].stats` est indexe par NOM (`attack`, `movement`, `turnsStarted`, ...), PAS par
    # l'ordinal de `StatType` -- verifie sur la reponse (`statTypes.turnsStarted` vaut bien `12`,
    # mais `stats["12"]` rend `None`). Lire par le NOM est de toute facon la regle ; l'ordinal
    # n'est conserve ici que pour ATTESTER que le canal designe la meme stat.
    snap = r(sid, "combatSnapshot", {"runnerId": args.runner}, 60)
    idx = (snap.get("statTypes") or {}).get("turnsStarted")
    unite = next((u for u in (snap.get("units") or []) if u.get("entityId") == args.unit), None)
    ts = (unite.get("stats") or {}).get("turnsStarted") if unite else None
    if ts is not None and idx != 12:
        print("[974]   ATTENTION : `statTypes.turnsStarted` = %r (attendu 12 = StatType.TurnsStarted "
              "dans `frida/enums.tsv`) -- le canal a peut-etre change de sens" % idx)
    if ts is None:
        print("[974]   TEMOIN : PAS MESURE (`turnsStarted` illisible) -> l'absence de gate de tour "
              "n'est PAS etablie (regime peut-etre degenere)")
        return EX_PAS_MESURE if ko == 0 else EX_ROUGE
    print("[974]   TEMOIN : turnsStarted(u%d) = %s" % (args.unit, ts))
    if int(ts) > 1:
        print("[974]   REGIME DEGENERE : `turnsStarted > 1`, donc un playbook PORTEUR du gate "
              "rendrait `True` lui aussi -- le `True` mesure ci-dessus ne prouve RIEN. Rejouer au "
              "PREMIER tour du porteur.")
        ko += 1
    elif evalue is True:
        print("[974]   => le regime DISCRIMINE, et %d n'a AUCUN gate de tour : le defaut permissif "
              "du port est JUSTE." % args.ability)
    else:
        print("[974]   => %d PORTE un gate de tour : brancher `_base._turns_started_gate`."
              % args.ability)
        ko += 1

    print("[974] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return EX_VERT if ko == 0 else EX_ROUGE


if __name__ == "__main__":
    sys.exit(main())
