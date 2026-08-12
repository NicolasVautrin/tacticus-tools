"""#978 -- confrontation LIVE des CINQ faces DECISION `NonComparable` Thousand Sons / Eldar.

Ce que ce probe etablit, et dans cet ordre :

  etape 0 (OFFLINE, aucune plateforme) : la STRUCTURE. Base LUE dans `frida/classes.tsv`
          (`NonComparablePlaybook`1` pour les cinq -- leur `.ctor` decompile NOMME
          `ComparablePlaybook<...>`, corps trivial DEDUPLIQUE), reachability LUE dans
          `metadata/active_playbook_builders.tsv` (cinq entrees du dict `active`), inscription au
          registre porte, et les constantes que chaque playbook DECLARE (`MIN_UTILITY`,
          `PRIORITY`) confrontees a `NATIVE_PRIORITY`.

  etape 1 (LIVE) : le MONTAGE UNIQUE. **Un seul runner paie pour les cinq items** : les deux
          porteurs hors pool (`thousDaemonPrince` MoW, `eldarLhykhis`) sont CO-INJECTES par
          `catalog_inject.write_augmented_seed_bc(out, [a, b])` -- deux FACTIONS differentes dans
          le meme seed, meme equipe, meme bataille. Les deux autres (`thousAhriman`,
          `eldarAutarch`) sont deja au pool.

  etape 2 (LIVE) : par item -- (a) REACHABILITY (`abilityTargets` rend des cibles), (b) LE PORT
          PROPOSE via le CHEMIN REEL (`DefaultAiUnitTactic` / `DefaultMachineTactic`, jamais la
          feuille isolee), (c) **CONTRE-EPREUVE**: le MEME appel, playbook RETIRE du registre, ne
          rend PLUS cette action. Une contre-epreuve qui ne MORD pas est un ECHEC du probe, pas un
          succes du port (cran de #957, re-arme par #970).

  etape 3 (LIVE) : ORACLE NATIF `aiStepDryRun` -- ce que le jeu DECIDE, en regard de ce que le
          port propose.

⚠ GEOMETRIE DRIVEE, jamais « bloque par le spawn ». Aux positions de spawn de `MC1_67` les
ennemis sont a 7-8 hexes : `Doombolt` (rayon `range = 2`) et `SwoopingHawk` (vague de 3 tuiles
alignees) rendent alors `no-op certain` -- ce qui est la REPONSE JUSTE du natif, pas un trou. Le
probe DEPLACE donc les unites pour atteindre le regime, et il DIT laquelle des deux situations il
observe.

⚠ COOLDOWN INITIAL. `AetherStride` (`initialCooldownTurns = 1`), `InfernalCannon` et
`EmpyricAmbush` ne sont pas `usable` au tour 1 : `build_machine` / le gate
`AttackQuery$$CanUseAbility` les ecartent, exactement comme #970-r1 l'a mesure pour 1201. Le probe
avance donc d'un round avant de mesurer, et le DIT.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_978_thousandsons_eldar_decision.py --only-scan
    python probe_978_thousandsons_eldar_decision.py --state-file <chemin ABSOLU unique>
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import catalog_inject
from probe_350r3_mow_caster import _ids, _move, _r
from rl_collect_batch import _resolve_session

from engine.entities.active_ability_type import ActiveAbilityType

BOARD = "MC1_67"
RANK = 17
SEED = 777

#: Les deux porteurs ABSENTS du seed BC -> co-injection catalogue (une LISTE, un seul appel).
HORS_POOL = ["thousDaemonPrince", "eldarLhykhis"]
#: Les porteurs deja au pool (`rl_duel build --list-pool`).
AU_POOL = ["thousAhriman", "eldarAutarch"]
#: La MoW du lot -- `--p-mow`, pas `--p-units`.
MOW = "thousDaemonPrince"

#: (ability, porteur, classe portee) -- l'ordre est celui du rapport.
CASES = [
    (int(ActiveAbilityType.Doombolt), "thousAhriman", "DoomboltPlaybook"),
    (int(ActiveAbilityType.Loki_SwoopingHawk), "eldarAutarch", "SwoopingHawkPlaybook"),
    (int(ActiveAbilityType.AetherStride), "thousDaemonPrince", "AetherStridePlaybook"),
    (int(ActiveAbilityType.InfernalCannon), "thousDaemonPrince", "InfernalCannonPlaybook"),
    (int(ActiveAbilityType.EmpyricAmbush), "eldarLhykhis", "EmpyricAmbushPlaybook"),
]

SYMBOLS = Path(__file__).resolve().parents[2] / "data" / "symbols"


# ------------------------------------------------------------------ etape 0 : structure (offline)

def _build_hash() -> str:
    """Le build dont les tables versionnees font foi (le plus recent repertoire de `data/symbols`
    qui porte les deux tables lues ici). Jamais code en dur."""
    cands = [d for d in SYMBOLS.iterdir()
             if (d / "frida" / "classes.tsv").exists()
             and (d / "metadata" / "active_playbook_builders.tsv").exists()]
    if not cands:
        raise RuntimeError("NON MESURE : aucune table de symboles complete sous %s" % SYMBOLS)
    return max(cands, key=lambda d: d.stat().st_mtime).name


def etape0() -> int:
    build = _build_hash()
    print("[978] build = %s" % build)
    ko = 0

    classes = (SYMBOLS / build / "frida" / "classes.tsv").read_text(encoding="utf-8").splitlines()
    parent_of = {}
    for line in classes:
        p = line.split("\t")
        if len(p) >= 3:
            parent_of[p[0]] = p[2]

    builders = (SYMBOLS / build / "metadata" / "active_playbook_builders.tsv"
                ).read_text(encoding="utf-8").splitlines()
    active = {}
    for line in builders:
        p = line.split("\t")
        if len(p) >= 3 and p[0] == "active":
            active[int(p[1])] = p[2]

    from engine.playbook import noncomparable as NC
    from engine.playbook.noncomparable._base import native_priority

    print("\n[978] ETAPE 0 -- structure LUE dans les tables versionnees")
    for aid, porteur, cls in CASES:
        nat = active.get(aid)
        base = parent_of.get(nat or "", "<classe absente>")
        pb = NC.playbook_for(aid)
        ok_base = base == "IdunBattle.AI.Playbook.NonComparablePlaybook`1"
        ok_reach = nat is not None and nat.endswith(cls)
        ok_reg = pb is not None and type(pb).__name__ == cls
        ok_prio = pb is not None and pb.PRIORITY == native_priority(aid)
        st = "OK  " if (ok_base and ok_reach and ok_reg and ok_prio) else "ECHEC"
        print("  %s %-4d %-22s porteur=%-18s base=%s reach=%s registre=%s prio=%s/%s"
              % (st, aid, ActiveAbilityType(aid).name, porteur,
                 "NC" if ok_base else base, "oui" if ok_reach else "NON",
                 "oui" if ok_reg else "NON",
                 pb.PRIORITY if pb else "?", native_priority(aid)))
        if st != "OK  ":
            ko += 1

    # Le couple de tiers du MEME porteur -- la seule interaction inter-items de la tranche.
    a, i = NC.playbook_for(int(ActiveAbilityType.AetherStride)), \
        NC.playbook_for(int(ActiveAbilityType.InfernalCannon))
    if a is not None and i is not None:
        print("\n  couple `thousDaemonPrince` : AetherStride tier %d, InfernalCannon tier %d"
              % (a.PRIORITY, i.PRIORITY))
        if not a.PRIORITY > i.PRIORITY:
            print("  ECHEC : le tier d'AetherStride devrait primer (ordre des generateurs)")
            ko += 1
    print("\n[978] ETAPE 0 : %s" % ("OK" if ko == 0 else "%d ECHEC(S)" % ko))
    return ko


# ------------------------------------------------------------------------- etape 1 : le montage

def _montage(sf: Path, seed_bc: Path, seed: int) -> int:
    sf.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(sf), "--board", BOARD, "--rank", str(RANK),
           "--seed-bc", str(seed_bc), "--no-ai",
           "--p-units", ",".join(AU_POOL + ["eldarLhykhis"]), "--p-mow", MOW]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("build rc=%d\n%s\n%s" % (r.returncode, r.stdout[-2000:],
                                                    r.stderr[-2000:]))
    import json
    return int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"])


def _patch_ammo(seed_bc: Path, ammo: int) -> None:
    """`BC.Player.Players[].MachineOfWarAmmo` -- SANS lui, `AetherStride` est structurellement
    INCASTABLE dans un runner.

    `ammoCost = 1` (constante `munitionsCost` du gameconfig) et le seed BC porte un stock de `0` ;
    `ActiveAbility$$get_CanCurrentlyBeUsed` teste `!AmmoCost.HasValue || HasEnoughAmmo`, donc le
    NATIF LUI-MEME refuse -- et le stock (`PlayerComponent+0x6c`) est pose une fois depuis la BC et
    n'est JAMAIS incremente par une operation native (`docs/rl/case-mow-ammo-gauge.md`). Aucun
    nombre de tours ne leve ce court-circuit : seul le patch de la BC l'ouvre.

    Patch en AMONT du build, sur `BC.Player` -- hors de `BC.Abilities`, donc hors de portee du
    rattrapage `catalog_inject.refresh_ability_configs` qui ecrase les patchs d'ability (#380)."""
    import json
    bc = json.loads(seed_bc.read_text(encoding="utf-8"))
    n = 0
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:
            p["MachineOfWarAmmo"] = int(ammo)
            n += 1
    seed_bc.write_text(json.dumps(bc), encoding="utf-8")
    print("  MachineOfWarAmmo = %d pose sur %d joueur(s)" % (ammo, n))


def _ctx_unit(sid, rid, uid):
    """`AiDecisionContext` d'un caster UNITE -- `engine.ai.context.build`, le chemin du spine."""
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    from engine.runner import snapshot as SNAP
    rpc = lambda m, b, t=60: _r(sid, rid, m, b, t)                              # noqa: E731
    dv = _r(sid, rid, "decisionView",
            SNAP.decision_view_seed_body(int(rid), allAbilities=True, maxRank=8), 180)
    mov = {u.get("id"): u for u in (dv.get("units") or [])}
    return AICTX.build(rpc, rid, dv, mov, int(uid), W.load(),
                       _scene.build_predictor(rpc, rid)), dv


def _ctx_machine(sid, rid, cid, dv):
    """⚠ Le `dv` est PASSE, jamais re-demande : `build_machine` leve si le `cid` n'est pas dans
    `dv.mows`, et un second `decisionView` peut ne plus publier la MoW (elle a agi, ou le tour a
    tourne). Le contexte doit etre bati sur LA MEME observation que celle qui a fourni le `cid`."""
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    rpc = lambda m, b, t=60: _r(sid, rid, m, b, t)                              # noqa: E731
    return AICTX.build_machine(rpc, rid, dv, int(cid), W.load(),
                               _scene.build_predictor(rpc, rid)), dv


#: GEOMETRIE DRIVEE -- placement des ENNEMIS (jamais des casters : deplacer un caster armerait la
#: regle `CasterHasNotMoved` d'`ActiveAbilityOperation$$IsInvalidTarget` et confondrait un refus de
#: ciblage avec un port muet). Les positions sont DERIVEES, pas choisies a vue :
#:   * `thousAhriman` spawn en (1,0) -> `hexgeo.disk((1,0), range = 2)` contient (0,1) et (2,0) ;
#:     `Doombolt` doit donc compter **2**.
#:   * `eldarAutarch` spawn en (0,0) -> `battle_query.get_tiles_behind((0,0), (0,1), 3)` rend
#:     EXACTEMENT [(0,1), (0,2), (0,3)] ; trois ennemis dessus font `n = 3`, donc `util = n - 1 = 2`.
#:   * `darkaTerminator` est ecarte au loin : il porte DEEP-STRIKE (non ciblable tant qu'il n'a pas
#:     agi), et le laisser dans le rayon melangerait « non ciblable » et « non compte ».
PLACEMENT = {
    "custoVexilusPraetor": (0, 1),      # rayon Doombolt ET tete de vague SwoopingHawk
    "orksBigMek": (0, 2),               # vague SwoopingHawk, HORS du rayon Doombolt
    "emperNoiseMarine": (0, 3),         # vague SwoopingHawk, HORS du rayon Doombolt
    "templAncient": (2, 0),             # rayon Doombolt
    "darkaTerminator": (5, 8),          # ECARTE (DEEP-STRIKE)
}
#: Ce que la geometrie ci-dessus IMPOSE aux deux formules -- ecrit AVANT la mesure, jamais releve
#: apres coup. Un port qui rendrait autre chose sur cette configuration est FAUX.
ATTENDU = {int(ActiveAbilityType.Doombolt): 2.0,
           int(ActiveAbilityType.Loki_SwoopingHawk): 2.0}


def _placer(sid, rid, ids) -> dict:
    """Applique `PLACEMENT` et rend les positions REELLEMENT atteintes (jamais celles demandees :
    un `move` refuse laisserait croire au regime alors qu'on mesure autre chose)."""
    for vid, (c, r) in PLACEMENT.items():
        if vid in ids:
            _move(sid, rid, ids[vid], c, r)
    dv = _r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 8}, 180)
    return {u.get("visualId"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
            for u in (dv.get("units") or []) if u.get("alive")}


def _decide(ctx, machine: bool) -> dict | None:
    """Le CHEMIN REEL, jamais la feuille isolee : c'est lui qui dit si la feuille est ATTEINTE."""
    from engine.ai import tactic as T
    tac = T.DefaultMachineTactic() if machine else T.DefaultAiUnitTactic()
    return tac.calculate_next_action(ctx)


def _sans_playbook(aid: int):
    """Contexte de CONTRE-EPREUVE : le playbook `aid` RETIRE du registre.

    Rend `(retire, restaurer)` -- l'appelant DOIT verifier que le retrait a MORDU (l'action
    disparait), sinon la contre-epreuve ne prouve rien. Sept mutations muettes en une journee
    (dont un garde refute par sa propre contre-epreuve) : on JOUE la mutation, on VOIT le rouge,
    on RESTAURE, on re-verifie le vert."""
    from engine.playbook import noncomparable as NC
    pb = NC.PLAYBOOKS.pop(aid, None)

    def restaurer():
        if pb is not None:
            NC.PLAYBOOKS[aid] = pb
    return pb, restaurer


def etape2(sid, rid, ids, dv) -> int:
    ko = 0
    print("\n[978] ETAPE 2 -- reachability / port / contre-epreuve, item par item")
    # ⚠ La cle d'une ligne `.mows` est `casterId` (== l'entite `EntityType.Machine`), PAS `id` :
    # c'est celle que `engine.ai.context.machine_row` interroge, et `build_machine` LEVE sinon.
    mow_row = next((m for m in (dv.get("mows") or []) if m.get("visualId") == MOW), None)
    for aid, porteur, cls in CASES:
        machine = (porteur == MOW)
        cid = (mow_row or {}).get("casterId") if machine else ids.get(porteur)
        nom = ActiveAbilityType(aid).name
        if cid is None:
            print("  %-4d %-22s NON CONFRONTE -- porteur %s absent du deploiement"
                  % (aid, nom, porteur))
            ko += 1
            continue
        at = _r(sid, rid, "abilityTargets", {"unitId": int(cid), "abilityType": int(aid)}, 120)
        n_from = 0
        usable = None
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == aid:
                    n_from += len(a.get("fromHere") or [])
                    usable = a.get("usable")
        ctx, _ = (_ctx_machine(sid, rid, cid, dv) if machine else _ctx_unit(sid, rid, cid))
        act = _decide(ctx, machine)
        propose = bool(act and act.get("kind") == "ability" and act.get("ability") == aid)
        # CONTRE-EPREUVE : sans le playbook, la MEME question doit changer de reponse.
        _, restaurer = _sans_playbook(aid)
        try:
            act_sans = _decide(ctx, machine)
        finally:
            restaurer()
        act_re = _decide(ctx, machine)          # le VERT est re-verifie apres restauration
        # ⚠ MORDANT = « la DECISION CHANGE », PAS « l'ability disparait ». Trois des cinq abilities
        # de la tranche sont AUSSI des attaques : amputer leur playbook NonComparable les fait
        # retomber sur le fallback `ComparableAbilityGenerator`, qui les repropose -- avec une
        # AUTRE cible, une AUTRE position et une AUTRE utilite. Exiger la disparition declarerait
        # « non mordante » une mutation qui mord franchement (mesure : 1102 passe de
        # `{77, to None, 2.0}` a `{79, to (1,3), 78.2}`). Le predicat porte donc sur l'ACTION
        # ENTIERE.
        mord = propose and (act_sans != act)
        print("  %-4d %-22s caster=%s fromHere=%d usable=%s" % (aid, nom, cid, n_from, usable))
        print("       port    : %s" % (act,))
        print("       ampute  : %s" % (act_sans,))
        print("       restaure: %s" % ("IDENTIQUE" if act_re == act else "DIVERGENT %s" % (act_re,)))
        if not propose:
            # Distinguer « regime non atteint » de « port muet » : le premier n'est PAS un echec.
            if aid == int(ActiveAbilityType.AetherStride):
                # VETO booleen : un refus ici est compatible avec le natif (le predicat PSYKER
                # peut etre faux partout). C'est l'etape 2b qui le CONFRONTE, en forcant la
                # branche positive -- un refus non force ne prouve rien.
                print("       -> VETO (utilite 0 partout) -- confronte par l'ETAPE 2b")
            elif n_from == 0 or usable is False:
                print("       -> NON CONFRONTE (regime non atteint : fromHere=%d usable=%s)"
                      % (n_from, usable))
            else:
                print("       -> ECHEC : cibles eligibles mais le port ne propose pas 1%d" % aid)
                ko += 1
        elif not mord:
            print("       -> ECHEC : la CONTRE-EPREUVE NE MORD PAS (un autre chemin proposait deja)")
            ko += 1
        else:
            att = ATTENDU.get(aid)
            if att is not None and act.get("util") != att:
                print("       -> ECHEC : utilite %s, la geometrie DRIVEE en impose %s"
                      % (act.get("util"), att))
                ko += 1
            else:
                print("       -> OK : propose, contre-epreuve MORD, util=%s%s"
                      % (act.get("util"),
                         " (= l'attendu de la geometrie)" if att is not None else ""))
        if act_re != act:
            print("       -> ECHEC : la restauration ne rend pas le verdict initial")
            ko += 1
    return ko


def etape2b(sid, rid, ids, dv) -> int:
    """1208 -- FORCER la branche POSITIVE du veto, au lieu de se contenter du refus.

    Dans la configuration de l'etape 2, `AetherStridePlaybook` rend `[]` : mesure par etage --
    **38/38 aires NON VIDES**, predicat SUMMON-EN-PORTEE **23/38**, predicat PSYKER **0/38**. Le
    veto est donc JUSTE (l'unique allie psyker, `thousAhriman`, est en (1,0) et ses trois voisins
    sont OCCUPES, donc aucune empreinte valide ne le touche), mais un refus ne CONFRONTE rien : il
    est compatible avec une feuille inerte comme avec un mirror exact.

    Cette phase DEPLACE donc le psyker jusqu'a rendre le predicat vrai, et la destination est
    CALCULEE, pas choisie a vue : on cherche `(ancre eligible, tuile de son aire, voisin LIBRE de
    cette tuile)` et on y envoie `thousAhriman`. Deplacer un ALLIE du caster est sans effet de
    bord ici -- le caster de 1208 est la MoW, pas lui."""
    from engine import battle_query as bq
    import engine.playbook.noncomparable._targets as TGT
    import engine.playbook.noncomparable.daemon_prince as DP
    from engine.playbook import noncomparable as NC

    aid = int(ActiveAbilityType.AetherStride)
    mow_row = next((m for m in (dv.get("mows") or []) if m.get("visualId") == MOW), None)
    if mow_row is None or "thousAhriman" not in ids:
        print("\n[978] ETAPE 2b -- NON CONFRONTE : MoW ou psyker absent")
        return 1
    cid = mow_row["casterId"]
    ctx, _ = _ctx_machine(sid, rid, cid, dv)
    pb = DP.AetherStridePlaybook()
    occup = set(p for p in (ctx.epos or []) if p) | set(p for p in (ctx.fpos or []) if p)
    neigh = bq.neigh_map(ctx) or {}
    cible = None
    for tid, pos, _k in TGT.eligible_any(ctx, aid):
        if pos is None:
            continue
        for t in pb._area(ctx, pos):
            for v in (neigh.get(t) or []):
                if v not in occup and v not in pb._area(ctx, pos):
                    cible = (pos, t, v)
                    break
            if cible:
                break
        if cible:
            break
    if cible is None:
        print("\n[978] ETAPE 2b -- NON CONFRONTE : aucune tuile libre adjacente a une aire")
        return 1
    ancre, tuile, dest = cible
    print("\n[978] ETAPE 2b -- 1208 : brancher le predicat PSYKER")
    print("  ancre %s -> aire touchee %s -> psyker envoye en %s" % (ancre, tuile, dest))
    _move(sid, rid, ids["thousAhriman"], dest[0], dest[1])
    _, dv2 = _ids(sid, rid)
    ctx2, _ = _ctx_machine(sid, rid, cid, dv2)
    pos_ahri = next((((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                     for u in (dv2.get("units") or []) if u.get("id") == ids["thousAhriman"]), None)
    print("  position ATTEINTE du psyker : %s (demandee %s)" % (pos_ahri, dest))
    n_a = sum(1 for tid, p, _k in TGT.eligible_any(ctx2, aid)
              if p is not None and pb._has_adjacent_friendly_psyker(ctx2, pb._area(ctx2, p)))
    print("  predicat PSYKER : %d cible(s) le satisfont maintenant (0 avant)" % n_a)
    act = _decide(ctx2, True)
    _, restaurer = _sans_playbook(aid)
    try:
        act_sans = _decide(ctx2, True)
    finally:
        restaurer()
    print("  port    : %s" % (act,))
    print("  ampute  : %s" % (act_sans,))
    if n_a == 0:
        print("  -> NON CONFRONTE : le deplacement n'a pas branche le predicat")
        return 1
    if not (act and act.get("kind") == "ability" and act.get("ability") == aid):
        print("  -> ECHEC : predicat branche mais 1208 n'est pas proposee")
        return 1
    if act.get("util") != pb.BOTH_PREDICATES_UTILITY:
        print("  -> ECHEC : utilite %s, le corps natif n'emet que %s"
              % (act.get("util"), pb.BOTH_PREDICATES_UTILITY))
        return 1
    if act_sans == act:
        print("  -> ECHEC : la contre-epreuve NE MORD PAS")
        return 1
    print("  -> OK : 1208 proposee (util=%s), et elle PRIME sur 1209 (tier 0 > tier -100) ; "
          "contre-epreuve MORD" % act.get("util"))
    _ = NC
    return 0


def etape3(sid, rid) -> None:
    print("\n[978] ETAPE 3 -- ORACLE NATIF (`aiStepDryRun`)")
    out = _r(sid, rid, "aiStepDryRun", {}, 180)
    msgs = out.get("messages") or out.get("inputMessages") or out
    print("  %s" % (msgs,))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-scan", action="store_true")
    ap.add_argument("--state-file")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--rounds", type=int, default=3,
                    help="rounds a avancer avant de mesurer (`initialCooldownTurns = 1` sur "
                         "1208/1209/1232 : `cooldown` du canal EST `RemainingCooldownTurns`, "
                         "et `can_currently_be_used` le refuse tant qu'il vaut >= 1)")
    ap.add_argument("--ammo", type=int, default=9,
                    help="`BC.Player.Players[].MachineOfWarAmmo` (0 au seed -> 1208 incastable)")
    a = ap.parse_args()

    ko = etape0()
    if a.only_scan:
        return 0 if ko == 0 else 1
    if not a.state_file:
        print("[978] --state-file ABSOLU requis hors --only-scan")
        return 2

    sf = Path(a.state_file)
    seed_bc = sf.with_name(sf.stem + "_seedbc.json")
    catalog_inject.write_augmented_seed_bc(seed_bc, HORS_POOL)
    _patch_ammo(seed_bc, a.ammo)
    print("\n[978] ETAPE 1 -- montage UNIQUE (co-injection %s)" % HORS_POOL)
    rid = _montage(sf, seed_bc, a.seed)
    sid = _resolve_session()
    ids, dv = _ids(sid, rid)
    print("  runner=%s board=%s ids=%s" % (rid, BOARD, ids))

    # Le round d'avance leve les `initialCooldownTurns = 1` (1208/1209/1232) -- meme cause que
    # #970-r1 sur 1201. Le PLACEMENT vient APRES : sinon le tour adverse redeplacerait tout.
    # ⚠ LES DEUX NOMS SONT EXACTS, ET LES DEUX FAUTES SONT SILENCIEUSES. `applyAction` attend
    # `kind: "endturn"` (minuscules -- `"endTurn"` rend `{}` sans erreur) et le tour adverse passe
    # par `autoPlayRunner` (`CheatRunAIMessage`), pas par un `aiTurn` qui n'existe pas. Mesure du
    # 1er jet : `turn` restait FIGE a 3 sur 6 rounds demandes, et le probe declarait alors
    # « regime non atteint » -- une mutation NON MORDANTE prise pour une mesure. D'ou le controle
    # ci-dessous, qui EXIGE que `turn` ait avance.
    # ⚠ ON NE FAIT PAS JOUER L'IA ADVERSE : `autoPlayRunner` la lache sur mes trois heros et la
    # bataille se termine (`stage Finished`) avant la mesure -- mesure du 2e jet, 3 rounds
    # suffisaient. Un `endturn` par CAMP fait avancer le compteur de tour sans qu'aucune unite
    # n'agisse : c'est tout ce dont le cooldown a besoin, et ca preserve la configuration placee.
    # ⚠ LE TEMOIN EST LE COOLDOWN, PAS `turn`. Premier jet : on lisait `dv.turn`, qui reste a `3`
    # de part et d'autre alors que les trois abilities passent bel et bien de `cooldown 1` a `0` --
    # un capteur qui accuse « FIGE » quand la mutation a MORDU ferait corriger la mauvaise cause.
    # On mesure donc EXACTEMENT la grandeur que ce bloc doit changer (meme regle que #467-r6 : une
    # panne, ou une absence de panne, doit porter son nom).
    def _cds() -> dict:
        d = _r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 1}, 180)
        out = {}
        for m in (d.get("mows") or []):
            for ab in (m.get("abilities") or []):
                out[ab.get("id")] = ab.get("cooldown")
        for u in (d.get("units") or []):
            for ab in (u.get("abilities") or []):
                if ab.get("id") in (int(ActiveAbilityType.EmpyricAmbush),):
                    out[ab["id"]] = ab.get("cooldown")
        return out

    c0 = _cds()
    for _ in range(a.rounds):
        _r(sid, rid, "applyAction", {"action": {"kind": "endturn"}})     # mon camp
        _r(sid, rid, "applyAction", {"action": {"kind": "endturn"}})     # camp adverse
    c1 = _cds()
    bouge = [k for k in c0 if c0.get(k) != c1.get(k)]
    print("  rounds : cooldowns %s -> %s (%s)"
          % (c0, c1, "RETOMBES sur %s" % bouge if bouge else
             "INCHANGES -- l'avancement n'a PAS mordu"))
    pos = _placer(sid, rid, ids)
    print("  positions ATTEINTES apres placement : %s" % pos)
    ids, dv = _ids(sid, rid)

    ko += etape2(sid, rid, ids, dv)
    etape3(sid, rid)
    # 2b APRES l'oracle : elle DEPLACE le psyker, donc elle change l'etat mesure par l'etape 2.
    ko += etape2b(sid, rid, ids, dv)
    print("\n[978] BILAN : %s" % ("OK" if ko == 0 else "%d ECHEC(S)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
