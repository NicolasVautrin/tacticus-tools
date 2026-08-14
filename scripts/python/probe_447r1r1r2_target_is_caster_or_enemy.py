"""CONFRONTATION LIVE #447-r1-r1-r2 -- le bit 57 `TargetIsCasterOrEnemy`, face DECISION.

LE BIT, VERBATIM du filtre statique (surcharge 7 arguments de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, DERNIERE regle avant le retour
« valide ») :

    if ((rules >> 0x39) & 1) && caster != GetUnit(target)
       && !UnitsCanAttackEachOther(caster, target)  ->  broken(TargetIsCasterOrEnemy)

= « la cible doit etre le CASTER LUI-MEME ou un ennemi attaquable ». C'est un `TargetIsEnemy`
ASSOUPLI par la tolerance du self-cast. Il etait porte mais NON CONFRONTE.

LE PIEGE QUE LA FICHE NOMME, et que ce probe respecte : les DEUX porteurs (`1008` sur
`necroPlasmancer`, `1102` sur `thousAhriman`) arment AUSSI `CasterMatchesDynamicRule`. Une
confrontation qui lirait `targetReason` sans avoir ETABLI `casterReason == 0` mesurerait le gate
CASTER, pas le bit -- le natif rend la raison CASTER telle quelle quand elle est rompue (mesure
#895-r2 : `casterReason` et `targetReason` portent alors le MEME code). L'etage 0 ci-dessous
etablit donc `casterReason == 0` et REFUSE de conclure sinon.

TROIS BRAS, et c'est leur ecart qui prouve que le bit MORD :
  * cible = le CASTER      -> attendu 0        (la tolerance self, c'est ce que le bit ajoute)
  * cible = un ALLIE       -> attendu refus    (0x200000000000000)
  * cible = un ENNEMI      -> attendu 0
Un port qui aurait ecrit `TargetIsEnemy` a la place serait vert sur les bras 2 et 3, et ROUGE sur
le 1er : c'est lui le discriminant.

⚠ CE PROBE N'INJECTE RIEN et ne redemarre rien. Il monte SON runner et le DISPOSE.
ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_895_nova_boss_riptide as P895                              # noqa: E402
from engine.runner.abilities.targeting import (get_invalid_caster_reason,  # noqa: E402
                                               get_invalid_target_reason, targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402

BOARD = "MC1_67"
#: LE PORTEUR EST CHOISI PAR LE POOL, PAS PAR LA FICHE. Les DEUX porteurs du bit sont
#: `necroPlasmancer` (1008) et `thousAhriman` (1102) ; MESURE du 2026-08-14 :
#: `rl_duel build --list-pool` refuse le premier (<< hors pool / non spawnables au rank 17 >>) et
#: accepte le second. Un probe qui aurait garde le premier aurait rendu << non confrontable >> pour
#: une raison de MONTAGE, pas de mecanique.
PORTEUR = "thousAhriman"
ALLIE = "thousSorcerer"
ENNEMI = "orksNob"
ABILITY = 1102                 # ActiveAbilityType porte par `thousAhriman` -- masque 0x200000000000004

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/targeting.py",
                "scripts/python/engine/runner/abilities/necrons.py",
                "scripts/python/probe_895_nova_boss_riptide.py",
                "scripts/python/rl_duel.py",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte la DERNIERE regle du filtre statique au NATIF via un runner live : il "
              "depend du port (`get_invalid_target_reason`), du masque de 1008, du montage et du "
              "build charge, qui EST l'oracle.",
}


def _reason(rep, cle):
    """`abilityReason` publie la raison STRUCTUREE : `{'ruleClass', 'hex', 'reasons'}`. Rend
    `(valeur, noms)` ou `(None, None)` si le canal est muet."""
    brut = rep.get(cle) if isinstance(rep, dict) else None
    if isinstance(brut, dict) and isinstance(brut.get("hex"), str):
        return int(brut["hex"], 16), brut.get("reasons")
    if isinstance(brut, (int, float)):
        return int(brut), None
    return None, None


def main() -> int:
    sid = P895._session()
    path = P895.LOGS / "probe_447r1r1r2.json"
    rid = P895.build(path, ["--seed", "777", "--board", BOARD,
                            "--p-units", "%s,%s" % (PORTEUR, ALLIE), "--a-units", ENNEMI,
                            "--place", "%s:4,4" % PORTEUR, "--place", "%s:4,5" % ALLIE,
                            "--a-place", "%s:5,5" % ENNEMI])
    if rid is None:
        print("[447-r1-r1-r2] BUILD REFUSE -- NON CONFRONTE (ne rien conclure de ce refus).")
        return 2
    rouges, confrontes = 0, 0
    try:
        state, dec, _bg, _board = P895.load(sid, rid)
        par_visual = {}
        for u in (dec.get("units") or []):
            uid = int(u.get("squadId") if u.get("squadId") is not None else u.get("id"))
            par_visual.setdefault(str(u.get("visualId") or ""), []).append((uid, u))
        opts = targeting_options_for(ABILITY)
        print("== #447-r1-r1-r2 : le bit 57 TargetIsCasterOrEnemy ==")
        print("masque de %d = 0x%x | bit 57 pose = %s"
              % (ABILITY, int(opts.rules) if opts else 0,
                 bool(opts and opts.has(TR.TargetIsCasterOrEnemy))))
        cid = alid = eid = None
        for vis, lst in par_visual.items():
            bas = vis.lower()
            if cid is None and "ahriman" in bas:
                cid = lst[0][0]
            elif alid is None and "sorcerer" in bas:
                alid = lst[0][0]
            elif eid is None and ("nob" in bas or "ork" in bas):
                eid = lst[0][0]
        print("caster=%r allie=%r ennemi=%r  (visualIds vus : %r)"
              % (cid, alid, eid, sorted(par_visual)))
        if cid is None:
            print("[447-r1-r1-r2] porteur ABSENT -- NON CONFRONTE.")
            return 2
        # ETAGE 0 -- ETABLIR `casterReason == 0`, sinon on mesure le gate CASTER et pas le bit.
        rep0 = P895.rpc(sid, "abilityReason",
                        {"runnerId": rid, "casterId": cid, "targetId": cid,
                         "abilityType": ABILITY}, 60)
        cr, cn = _reason(rep0, "casterReason")
        print("etage 0 : casterReason natif = %s %r"
              % (("0x%x" % cr) if cr is not None else "NON MESURE", cn))
        if cr is None:
            print("[447-r1-r1-r2] canal muet -- NON CONFRONTE. brut=%r" % (rep0,))
            return 2
        if cr != 0:
            print("[447-r1-r1-r2] le gate CASTER MORD (0x%x) : la zone du bit 57 est INATTEIGNABLE "
                  "dans ce montage -- NON CONFRONTE, et surtout pas 'accord'." % cr)
            return 2
        for tid, libelle, attendu in ((cid, "cible = LE CASTER (tolerance self)", 0),
                                      (alid, "cible = un ALLIE", int(TR.TargetIsCasterOrEnemy)),
                                      (eid, "cible = un ENNEMI", 0)):
            if tid is None:
                print("  %-38s ABSENT du montage -- non confronte" % libelle)
                continue
            rep = P895.rpc(sid, "abilityReason",
                           {"runnerId": rid, "casterId": cid, "targetId": tid,
                            "abilityType": ABILITY}, 60)
            natif, noms = _reason(rep, "targetReason")
            port = get_invalid_target_reason(state, cid, tid, _porteur(ABILITY))
            print("  %-38s natif=%s %r | port=0x%x | attendu=0x%x"
                  % (libelle, ("0x%x" % natif) if natif is not None else "NON MESURE",
                     noms, int(port), attendu))
            if natif is None:
                continue
            confrontes += 1
            if natif != int(port):
                print("     [FAIL] DESACCORD port/natif")
                rouges += 1
            if natif != attendu:
                print("     [NOTE] le NATIF ne rend pas l'attendu de la RE -- c'est la RE qu'il "
                      "faut relire, pas le natif.")
                rouges += 1
    finally:
        P895.rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres
    if confrontes == 0:
        print("  [FAIL] AUCUN bras confronte -- un run muet n'est pas un vert.")
        rouges += 1
    print()
    print("[447-r1-r1-r2] %s -- %d ecart(s)" % ("OK" if rouges == 0 else "FAIL", rouges))
    return 0 if rouges == 0 else 1


def _porteur(aid: int):
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import UnportedAbilityTargeting
    cls = ABILITY_CLASSES.get(int(aid))
    if cls is not None:
        return cls()
    return UnportedAbilityTargeting(int(aid), targeting_options_for(aid))


if __name__ == "__main__":
    raise SystemExit(main())
