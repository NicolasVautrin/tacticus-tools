"""#287-r5 -- BASCULE LIVE de la regle dynamique 1185 `ForwardObservers`, contre l'oracle NATIF.

CE QUE CE PROBE MESURE, ET CE QUI LE DISTINGUE DE `probe_287r4r1_generalisation_live.py`. Ce
dernier confronte des regles dont le substrat est DEJA la sur le plateau (un trait, un camp) : il
compare port et natif cible par cible, une fois. Ici la grandeur lue par le corps natif est un EFFET
qui n'existe pas au montage -- `EffectType.Markerlight` (0x462) -- et que l'ability POSE elle-meme.
Le probe le FABRIQUE donc, et mesure les MEMES couples (caster, cible) AVANT et APRES :

    IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardObserversAbility$$GetDynamicInvalidTargetReason
        if (target != null && EntityExtensions.HasEffect(target, state, 0x462, onlyActive: false))
            return 2;                      // 2 = TargetingRule.TargetMatchesDynamicRule
        return <corps de base>;            // = `return 0`

C'est une bascule au sens fort : le MEME couple change de verdict, et il n'en change que par la
grandeur que le corps natif lit. Un port qui rendrait toujours `0`, ou toujours `2`, echoue -- alors
qu'une mesure en un seul instant ne separerait ni l'un ni l'autre d'un port juste.

LE PORTEUR EST LE VRAI, PAS UN GREFFON. `tauNpc5StealthSuit` est le porteur npc de 1185 ; il entre
en bataille par le CHEMIN DE STATS EXPLICITE (`--explicit-stats`, #419-r1-tr12-r2 :
`UnitProgression$$GetNpcStats`), donc avec SES stats, SES traits et SON arme. La greffe de
`case-92 §5bis` -- qui aurait ete legitime ici, le corps ne lisant ni stats ni traits du caster --
n'est pas necessaire. Le jumeau `tauSmnStealthSuit` (summon) n'a AUCUN invocateur au catalogue
(l'ability `ATemptingTrap` qui le declare n'est portee par personne) : c'est le npc qui est la voie.

LES POSITIONS SONT FORCEES (`--place` / `--a-place`), jamais subies. Aux SpawnPoints de `MC1_67` les
deux camps sont hors de portee et `ForwardObservers` sort « no-op certain » : ce n'est pas une
propriete de l'ability, c'est la geometrie de spawn -- on la DEPLACE.

⚠ DEUX PORTEURS, ET C'EST LA MESURE QUI L'A IMPOSE. `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`
resout l'instance par `IdunBattle.Entities.Components.ActiveAbilityComponent$$GetOrNull(comp, type)`
et rend `GenericBrokenTargetingRule(0x1)` -- `ValidRequest` reutilise comme code de REFUS -- des que
l'ability est absente, en cooldown (`get_CanCurrentlyBeUsed`) ou a `+0x44 == 0`. Ce gate est EN
AMONT de la regle dynamique. Mesure du 2026-08-06 avec un porteur unique : apres son propre cast, le
natif rendait `0x1` sur les DEUX cibles -- l'ability etait consommee, la regle n'etait plus atteinte,
et le port (qui, lui, ne modelise pas ce verrou) rendait `0x2` sur la cible marquee. Le rouge
accusait le PROTOCOLE, pas le port. Le montage porte donc DEUX exemplaires du porteur : l'un CASTE
(il pose l'effet), l'AUTRE OBSERVE (son ability est intacte, donc la cascade descend jusqu'a la
regle). Le verrou d'usage est verifie a part, sur le casteur, plutot que subi.

Usage (session warmee ; le probe monte et DISPOSE son propre runner) :
    python scripts/python/probe_287r5_forward_observers_live.py
    python scripts/python/probe_287r5_forward_observers_live.py --board MC1_67 --keep
ASCII only ; exit 0 = la bascule est reproduite a l'identique, et le desarmement l'efface.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_27_custom_utility_inventory as INV                            # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting import is_invalid_target            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

LOGS = HERE.parents[1] / "logs"
FO = int(ActiveAbilityType.ForwardObservers)          # 1185
PORTEUR = "tauNpc5StealthSuit"
REFUS = int(TR.TargetMatchesDynamicRule)
VERROU_USAGE = int(TR.ValidRequest)                   # 0x1 -- cf. l'entete


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _contexte(rid: int):
    dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    ob = _rpc("observeBattle", {"runnerId": rid}, 40000)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60000)
    bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
    return dec, ob, snap, Board(bg["tiles"], adjacency="evenq")


def mesurer(rid: int, caster_id: int, cibles: list) -> list:
    """[(cible, natif, port, effets_portes)] -- l'etat est RE-CHARGE a chaque appel."""
    dec, ob, snap, board = _contexte(rid)
    state = load_state(dec, ob, snap, board=board)
    ab = P._porteur(FO)
    out = []
    par_id = {u["id"]: u for u in (dec.get("units") or [])}
    for tid in cibles:
        r = _rpc("abilityReason", {"runnerId": rid, "casterId": caster_id,
                                   "abilityType": FO, "targetId": tid}, 60000) or {}
        tr = r.get("targetReason") or {}
        nat = int(tr.get("hex") or "0x0", 16)
        port = int(is_invalid_target(state, int(caster_id), int(tid), ab) or 0)
        eff = [e.get("name") or e.get("type") for e in ((par_id.get(tid) or {}).get("effects") or [])]
        out.append((tid, nat, port, ",".join(str(x) for x in eff)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r5 : bascule live de 1185 ForwardObservers")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--palier", default="5", help="palier npc du porteur (suffixe :<n>)")
    ap.add_argument("--state-file", default="rs_287r5_fo_live.json")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    porteur = "%s:%s" % (PORTEUR, a.palier)
    state_file = LOGS / a.state_file
    # POSITIONS FORCEES cote ADVERSE : aux SpawnPoints de `MC1_67` les deux camps sont hors de
    # portee et `ForwardObservers` sort « no-op certain » -- on mesurerait la geometrie, pas la
    # regle. Avec les deux ennemis en (2,1)/(3,1), le porteur a DEUX cibles legales sans bouger.
    # ⚠ Le porteur, lui, n'est PAS place par `--place` : `_parse_place_specs` coupe l'unitId au
    # PREMIER `:`, donc un id a palier (`tauNpc5StealthSuit:5`, exige par `--explicit-stats`) y
    # part en « col/row non entiers ». Limite de l'outil, hors perimetre de cette tranche --
    # contournee, pas maquillee : le montage n'en a pas besoin.
    _run(["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
          "--explicit-stats", porteur, "--p-units", "%s,%s" % (porteur, porteur),
          "--a-units", "orksWarboss,thousTzaangor",
          "--a-place", "orksWarboss:2,1", "--a-place", "thousTzaangor:3,1",
          "--state-file", str(state_file)])
    if not state_file.exists():
        print("[287r5-fo] PAS MESURE : build KO (state-file absent)")
        return 2
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])

    try:
        dec, _ob, _snap, _board = _contexte(rid)
        units = [u for u in (dec.get("units") or []) if u.get("alive")]
        porteurs = [u for u in units if u.get("visualId") == PORTEUR]
        if len(porteurs) < 2:
            print("[287r5-fo] PAS MESURE : %d exemplaire(s) de %s -- il en faut DEUX (le casteur "
                  "consomme son ability, cf. l'entete)" % (len(porteurs), PORTEUR))
            return 2
        casteur, observateur = porteurs[0], porteurs[1]
        cibles = [u["id"] for u in units if u.get("visualId") != PORTEUR]
        if not cibles:
            print("[287r5-fo] PAS MESURE : aucune cible")
            return 2

        avant = mesurer(rid, observateur["id"], cibles)
        # LE CAST -- il POSE `Markerlight` sur UNE des deux cibles ; l'autre reste temoin.
        marquee = next((t for (t, nat, _p, _e) in avant if nat == 0), None)
        if marquee is None:
            print("[287r5-fo] PAS MESURE : le natif refuse DEJA toutes les cibles avant le cast "
                  "-- rien a faire basculer (verdicts : %s)"
                  % ", ".join("u%s=%s" % (t, hex(n)) for (t, n, _p, _e) in avant))
            return 2
        _run(["act", "ability", "--caster", str(casteur["id"]), "--ability", str(FO),
              "--target", str(marquee), "--state-file", str(state_file)])
        apres = mesurer(rid, observateur["id"], cibles)
        # Le VERROU D'USAGE, mesure SUR LE CASTEUR : c'est lui qui a consomme l'ability. On le
        # constate au lieu de le subir -- c'est ce qui a fait tomber la version a un seul porteur.
        verrou_casteur = mesurer(rid, casteur["id"], [marquee])

        # ATTRIBUTION : les MEMES couples, la regle DESARMEE. Ce qui survit ne vient pas d'elle.
        with P.desarme(FO):
            desarme = mesurer(rid, observateur["id"], cibles)
    finally:
        if not a.keep:
            _run(["dispose", "--state-file", str(state_file)])

    print("[287r5-fo] board=%s seed=%d runner=%d -- %s : casteur u%s, OBSERVATEUR u%s, "
          "cible marquee u%s"
          % (a.board, a.seed, rid, PORTEUR, casteur["id"], observateur["id"], marquee))
    for libelle, res in (("AVANT le cast", avant), ("APRES le cast", apres),
                         ("APRES, regle DESARMEE", desarme)):
        print("  %-22s %s" % (libelle, "  ".join(
            "u%s natif=%-8s port=%-8s [%s]" % (t, hex(n), hex(p), e or "-")
            for (t, n, p, e) in res)))

    av = {t: (n, p) for (t, n, p, _e) in avant}
    ap_ = {t: (n, p) for (t, n, p, _e) in apres}
    de = {t: (n, p) for (t, n, p, _e) in desarme}
    temoins = [t for t in cibles if t != marquee]

    # Le VERROU D'USAGE, CONSTATE sur le casteur -- c'est ce qui rend le second porteur obligatoire.
    vc = verrou_casteur[0][1]
    print("  CASTEUR u%s sur la meme cible u%s : natif=%s -- %s"
          % (casteur["id"], marquee, hex(vc),
             "VERROU D'USAGE (0x1 ValidRequest, ability consommee), la cascade n'atteint PAS la "
             "regle" if vc & VERROU_USAGE else "pas de verrou d'usage"))
    if not (vc & VERROU_USAGE):
        print("     !! ATTENDU : le casteur devrait etre verrouille apres son propre cast. "
              "S'il ne l'est pas, le second porteur n'etait pas necessaire -- le DIRE.")

    bascule_nat = av[marquee][0] == 0 and bool(ap_[marquee][0] & REFUS)
    bascule_port = av[marquee][1] == 0 and bool(ap_[marquee][1] & REFUS)
    reproduit = ap_[marquee][1] == ap_[marquee][0]
    efface = not (de[marquee][1] & REFUS)
    temoin_stable = all(not (ap_[t][1] & REFUS) for t in temoins)

    print("[287r5-fo] BASCULE")
    print("  le NATIF passe de 0 a TargetMatchesDynamicRule sur la cible marquee : %s" % bascule_nat)
    print("  le PORT  passe de 0 a TargetMatchesDynamicRule sur la cible marquee : %s" % bascule_port)
    print("  le port REPRODUIT le masque natif a l'identique (%s == %s)          : %s"
          % (hex(ap_[marquee][1]), hex(ap_[marquee][0]), reproduit))
    print("  cible(s) TEMOIN non marquee(s) : le port ne refuse PAS               : %s (%d cible(s))"
          % (temoin_stable, len(temoins)))
    # SUR-REFUS : le natif ACCEPTE, le port refuse. C'est le bras qui compte pour une regle de
    # ciblage (la degradation d'avant etait permissive dans l'AUTRE sens). On le ventile par
    # ATTRIBUTION : ce qui SURVIT au desarmement vient d'un autre etage du masque et PREEXISTE.
    surrefus = [t for t in cibles if ap_[t][0] == 0 and ap_[t][1] != 0]
    imputables = [t for t in surrefus if de[t][1] == 0]
    preexistants = [t for t in surrefus if de[t][1] != 0]
    print("[287r5-fo] SUR-REFUS (natif accepte, port refuse) : %d" % len(surrefus))
    for t in imputables:
        print("     IMPUTABLE a cette tranche : u%s port=%s -- disparait au desarmement"
              % (t, hex(ap_[t][1])))
    for t in preexistants:
        print("     PREEXISTANT (hors tranche) : u%s port=%s, SURVIT au desarmement -- un AUTRE "
              "etage du masque le pose, pas la regle dynamique" % (t, hex(de[t][1])))
    print("[287r5-fo] ATTRIBUTION -- la regle DESARMEE, la bascule du port S'EFFACE : %s" % efface)
    if not efface:
        print("     !! le refus SURVIT au desarmement : il vient d'un AUTRE etage du masque, "
              "pas de cette regle -- le vert ne serait pas imputable a la tranche")
    print("  effet lu par le corps natif : %s (0x%x)"
          % (EffectType.Markerlight.name, int(EffectType.Markerlight)))

    ok = (bascule_nat and bascule_port and reproduit and efface and temoin_stable
          and not imputables)
    print("[287r5-fo] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
