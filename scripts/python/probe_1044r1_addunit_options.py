"""#1044-r1 -- `AddUnitMessage` peut-il porter le `Nullable<UnitOverrideType>` d'`AddUnitOptions` ?

CE QUE LA FICHE ETABLISSAIT (lu sur `rnca9r7q6c`). `IdunBattle.Operations.AddUnitOperation$$
AddUnitTypeTraits(unit, options, hasParent)` prend le `Nullable<UnitOverrideType>` d'`AddUnitOptions`
et, QUAND IL A UNE VALEUR, elle DECIDE -- court-circuitant le `heroDeDroit`. Les trois valeurs
(`IdunBattle.Operations.UnitOverrideType`) posent chacune UN des trois traits, donc « aucun de
`{Hero, NPC, Summon}` » ne s'obtient QUE par la troisieme branche.

CE QUE LA FICHE LAISSAIT OUVERT, et que ce probe tranche SANS ghidra (metadonnees seules) :
  (a) la disposition exacte d'`AddUnitOptions` ;
  (b) si `AddUnitMessage` -- la voie que `rl_duel --a-place` emprunte deja -- permet de la porter.

⚠ HOMONYMES. Le build porte DEUX `AddUnitOptions` : `IdunBattle.View.Game.AddUnitOptions`
(40 octets) et `IdunBattle.Operations.AddUnitOptions` (112). C'est la SECONDE que lit
`AddUnitTypeTraits` ; viser la premiere donnerait une disposition entierement fausse.

⚠ BOXING. `classFields` rend des offsets BOXES (en-tete d'objet de 16 octets inclus). Un
`ValueType` passe en argument n'a PAS cet en-tete : l'offset de la fiche (`+0x8`) et celui que ce
probe imprime (`24`) designent LE MEME champ. C'est la meme convention que
`reference_il2cpp_methodptr_uninit_class` / `runtime_invoke BOXE les types valeur`.

Usage (depuis `scripts/python`, aucun runner necessaire) :

    python probe_1044r1_addunit_options.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import rl_duel as R

NS_OPS = "IdunBattle.Operations"
NS_MSG = "IdunBattle.Messages"
ENTETE_OBJET = 16          # `boxedSize - fieldsSize` sur toute classe du build


def _champs(sid: int, ns: str, cls: str) -> dict:
    res = R._rpc(sid, "classFields", [ns, cls], timeout=30).get("result") or {}
    if not res.get("ok"):
        raise SystemExit("[1044-r1] classFields(%s, %s) : %s" % (ns, cls, res.get("err")))
    return res


def main(argv=None) -> int:
    sid = R._resolve_session()

    opts = _champs(sid, NS_OPS, "AddUnitOptions")
    msg = _champs(sid, NS_MSG, "AddUnitMessage")

    print("[1044-r1] %s.AddUnitOptions -- boxedSize=%s fieldsSize=%s champs=%s"
          % (NS_OPS, opts.get("boxedSize"), opts.get("fieldsSize"), opts.get("fieldCount")))
    for f in (opts.get("fields") or []):
        brut = int(f.get("offset", 0))
        print("    +0x%-4x (boxe +0x%-4x)  %-46s %s"
              % (brut - ENTETE_OBJET, brut, f.get("name"), f.get("type")))

    print("[1044-r1] %s.AddUnitMessage -- boxedSize=%s champs=%s"
          % (NS_MSG, msg.get("boxedSize"), msg.get("fieldCount")))
    noms_msg = [f.get("name") for f in (msg.get("fields") or [])]
    for f in (msg.get("fields") or []):
        print("    +0x%-4x  %-32s %s" % (int(f.get("offset", 0)), f.get("name"), f.get("type")))

    noms_opts = [f.get("name") for f in (opts.get("fields") or [])]
    partages = [n for n in noms_opts if n in noms_msg]
    manquants = [n for n in noms_opts if n not in noms_msg]

    print("[1044-r1] VERDICT")
    print("    champs d'AddUnitOptions que le MESSAGE transporte : %s" % (partages,))
    print("    champs d'AddUnitOptions ABSENTS du message        : %d -> %s"
          % (len(manquants), manquants))
    porte = "OverrideType" in noms_msg
    print("    `OverrideType` portable par AddUnitMessage ?       : %s" % ("OUI" if porte else "NON"))
    if not porte:
        print("    => la voie `--a-place` / `buildAddUnitMessage` (ctor 4 args : unitId, playerId,")
        print("       col, row) ne PEUT PAS porter UnitOverrideType. La seule signature native qui")
        print("       accepte des AddUnitOptions completes est")
        print("       `Core.Services.OperationProcessor.AddUnit(unitId, unitFeetTileIds, playerId,")
        print("       spawnSource, options)`, qu'aucun RPC du harnais n'expose -- porter l'option")
        print("       exige donc un capteur NEUF cote frida/hooks, c.-a-d. une fenetre de reinject.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
