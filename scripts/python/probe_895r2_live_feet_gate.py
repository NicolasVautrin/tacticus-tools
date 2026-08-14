"""CONFRONTATION LIVE #895-r2 -- les trois filtres de `GetFeetCount` du volet CASTER.

CE QU'IL MESURE, et pourquoi CE bras : la fiche du residu declarait la regle non confrontable
faute d'un caster a SEPT pieds (<< le boss arrive MONO-HEX >>). Elle lisait le montage a l'envers.
Le bras qui MORD est le NEGATIF : un caster mono-hex portant `1193 NovaCharge` (masque
`CasterHas7Tiles`) doit se voir REFUSER le cast par
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` --
`if ((rules >> 0x25 & 1) && feet != 7) return broken(0x2000000000)`. Avant #895-r2 le port rendait
`0` : degradation PERMISSIVE, exactement ce que ce probe met en evidence.

LE CANAL est `abilityReason.casterReason` : il PUBLIE le verdict du volet caster natif, sans
dependre d'une cible. `abilityTargets.fromHere` sert de second temoin (le natif rend
`ValidTargets.Empty` des que le caster est refuse -- cf. `TargetingQuery$$GetValidTargets`), ce qui
confronte AUSSI #447-r4.

⚠ CE PROBE N'INJECTE RIEN et ne redemarre rien. Il monte SON runner et le DISPOSE.
ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_895_nova_boss_riptide as P895                              # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES             # noqa: E402
from engine.runner.abilities.targeting import get_invalid_caster_reason  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402
from engine.runner.components import get_unit_feet                      # noqa: E402

NOVA_CHARGE = 1193             # ActiveAbilityType.NovaCharge -- masque `CasterHas7Tiles`
NOVA_SHIELD = 1194             # temoin : MEME porteur, masque SANS aucun `CasterHasNTiles`

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/targeting.py",
                "scripts/python/engine/runner/abilities/tau.py",
                "scripts/python/engine/runner/components.py",
                "scripts/python/probe_895_nova_boss_riptide.py",
                "scripts/python/rl_duel.py",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le volet CASTER du port au NATIF via un runner live : il depend du "
              "port (`get_invalid_caster_reason`), du masque de 1193 (`tau.py`), du substrat "
              "d'empreinte (`components.get_unit_feet`), du montage (`probe_895` resout le boss "
              "npc) ET du build charge, qui EST l'oracle.",
}


def main() -> int:
    sid = P895._session()
    path = P895.LOGS / "probe_895r2_feet.json"
    # MEME montage que `probe_895.measure_shield` : les adversaires sont AU POOL (`ultraTitus` n'y
    # est pas au rank courant -- le build le refuse, et c'est le garde de roster qui parle).
    rid = P895.build(path, ["--seed", "777", "--board", P895.BOARD,
                            "--explicit-stats", P895.BOSS, "--p-units", P895.BOSS,
                            "--a-units", "tauCrisis,orksNob",
                            "--place", "%s:3,4" % P895.BOSS,
                            "--a-place", "tauCrisis:1,6", "--a-place", "orksNob:3,7"])
    if rid is None:
        print("[895-r2] BUILD REFUSE -- NON CONFRONTE (ne rien conclure de ce refus).")
        return 2
    rouges = 0
    try:
        state, dec, _bg, _board = P895.load(sid, rid)
        boss = None
        for u in (dec.get("units") or []):
            if str(u.get("visualId") or "") == P895.BOSS_VISUAL:
                boss = u
                break
        if boss is None:
            print("[895-r2] boss ABSENT de la vue decision -- NON CONFRONTE.")
            return 2
        uid = int(boss.get("squadId") if boss.get("squadId") is not None else boss.get("id"))
        feet_live = list(boss.get("feet") or [])
        feet_port = get_unit_feet(state, uid)
        print("== #895-r2 : le volet CASTER, live vs port ==")
        print("boss uid=%d  |  feet LIVE = %d  |  feet PORT = %d"
              % (uid, len(feet_live), len(feet_port)))
        if len(feet_live) != len(feet_port):
            print("[FAIL] le SUBSTRAT diverge avant tout gate : %r vs %r" % (feet_live, feet_port))
            rouges += 1
        confrontes = 0
        for aid, libelle in ((NOVA_CHARGE, "1193 NovaCharge (CasterHas7Tiles)"),
                             (NOVA_SHIELD, "1194 NovaShield (TEMOIN, aucun CasterHasNTiles)")):
            # ⚠ LE PARAMETRE EST `casterId`, PAS `unitId` -- contrat LU dans
            # `.claude/skills/tacticus/references/rpc-api.md`. Avec le mauvais nom le RPC rend une
            # reponse SANS `casterReason`, et un probe qui traite ce `None` comme
            # « non confronte » rend un VERT qui ne mesure rien : c'est pourquoi le compteur
            # `confrontes` ci-dessous fait rougir un run entierement muet.
            rep = P895.rpc(sid, "abilityReason",
                           {"runnerId": rid, "casterId": uid, "targetId": uid,
                            "abilityType": aid}, 60)
            brut = rep.get("casterReason") if isinstance(rep, dict) else None
            # `abilityReason` publie la raison STRUCTUREE (flags `TargetingRule` en NOMS) : le canal
            # rend un dict, pas un entier. On extrait la valeur numerique par le champ qui la porte,
            # et on DIT lequel plutot que de deviner.
            # FORME REELLE, LUE sur la reponse : `{'ruleClass': ..., 'hex': '0x00000020...',
            # 'reasons': ['CasterHas7Tiles']}`. Le champ numerique est `hex` (une CHAINE), et
            # `reasons` porte les NOMS de bits -- c'est ce second champ qui rend la confrontation
            # lisible, donc on le RESTITUE.
            natif, noms = None, None
            if isinstance(brut, dict):
                if isinstance(brut.get("hex"), str):
                    natif = int(brut["hex"], 16)
                noms = brut.get("reasons")
            elif isinstance(brut, (int, float)):
                natif = int(brut)
            cls = ABILITY_CLASSES.get(aid)
            port = get_invalid_caster_reason(state, uid, cls()) if cls else None
            print("  %-46s natif casterReason=%s %r | port=%s"
                  % (libelle, ("0x%x" % int(natif)) if natif is not None else "NON MESURE",
                     noms, ("0x%x" % int(port)) if port is not None else "NON PORTE"))
            if natif is None:
                print("     [NOTE] canal muet -- reponse brute : %r" % (rep,))
                continue
            confrontes += 1
            if int(natif) != int(port or 0):
                print("     [FAIL] DESACCORD port/natif")
                rouges += 1
        if confrontes == 0:
            print("  [FAIL] AUCUNE ability confrontee -- un run entierement muet n'est pas un vert.")
            rouges += 1
        # SECOND TEMOIN, et il confronte #447-r4 : un caster refuse rend `ValidTargets.Empty`.
        at = P895.rpc(sid, "abilityTargets",
                      {"runnerId": rid, "unitId": uid, "abilityType": NOVA_CHARGE}, 60)
        fromhere = (at or {}).get("fromHere") if isinstance(at, dict) else None
        print("  abilityTargets(1193).fromHere = %r" % (fromhere,))
        if isinstance(fromhere, list) and len(feet_live) != 7 and fromhere:
            print("     [FAIL] le natif devrait rendre ValidTargets.Empty sur un caster refuse")
            rouges += 1
    finally:
        P895.rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres
    print()
    print("[895-r2] %s -- %d ecart(s)" % ("OK" if rouges == 0 else "FAIL", rouges))
    return 0 if rouges == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
