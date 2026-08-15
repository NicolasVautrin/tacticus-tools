"""`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1` -- les trois DERNIERS `ShouldExecute` a corps propre, et la
CONFRONTATION LIVE des gates que la tranche precedente avait portes sans les jouer.

⚠ La fiche `docs/rl/case-419-r1-tr14-r5-r2-r1-r1-r1-r3-derniers-corps-propres.md` citait un probe
`probe_419r1tr14r5r2r1r1r1r3_gates.py` qui **n'a jamais existe** dans l'arbre. Celui-ci le remplace,
et la citation est corrigee au backlog.

## Ce que ce probe MESURE, etape par etape

**etape 1 (OFFLINE) -- les SLOTS D'INTERFACE, parce que c'est LA ou l'erreur s'est logee.**
Le port de `1147 HadesAutocannons` lisait les ALLIES du caster la ou le natif interroge
`GetAllEnemiesOf`. La cause n'est pas une faute de lecture du pseudo-C : les deux corps de
`IdunBattle.Core.Services.BattleQuery` (`GetAllFriendsOf` / `GetAllEnemiesOf`) sont IDENTIQUES au
sens de la comparaison d'owner pres (`==` contre `!=`), et le decompile n'affiche que
`FUN_180003b70(0x8e, <IBattleQuery>, ...)`. Le seul canal qui tranche est
`data/symbols/<build>/metadata/interface_slots.tsv`. Ce cran fige les CINQ slots que la famille
consomme, pour qu'un renumerotage de build ne repasse pas en silence.

**etape 2 (OFFLINE + LIVE) -- la REACHABILITY de `BloodChalicePlaybook$$ShouldExecute`.**
`ShouldExecute` vit au slot de vtable `+0x328` et n'a qu'UN appelant,
`ComparablePlaybook<T>$$CalculateActionUtility`, qui n'a elle-meme qu'UN appelant
(`list_xrefs` : un seul `UNCONDITIONAL_CALL`), `ComparablePlaybook<T>$$EvaluateInternal`. Une classe
qui OVERRIDE `EvaluateInternal` rend donc son propre `ShouldExecute` INATTEIGNABLE. Le discriminant
se mesure sur deux sources independantes :

  * OFFLINE : `frida/methods.tsv` (l'enumeration IL2CPP `class_get_methods`) ;
  * LIVE : `resolveMethodPtr` a `depth 0`, qui REFAIT l'enumeration dans le processus.

Le TEMOIN obligatoire est `MomentShacklePlaybook` : elle declare `ShouldExecute` et **pas**
`EvaluateInternal`, donc son gate est VIVANT (et il est porte). Sans ce temoin, « BloodChalice
declare `EvaluateInternal` » ne mesurerait que la panne de la table.

**etape 3 (LIVE) -- `1147 HadesAutocannons`, TROIS bras.** C'est la confrontation qui accuse
l'inversion. Montage : greffe de `[1147]` sur `darkaTerminator` (voie `case-92` SS5bis -- le natif
charge le playbook PAR ABILITY, et ce gate ne lit ni stats ni traits du caster, seulement
`GetCurrentOwnerEntityId(caster)`, ce qui est EXACTEMENT la condition qui autorise la greffe),
`Movement=0`, cible a distance 2.

  | bras    | porteur de `UnitTrait.Summon` | gate natif attendu | port AVANT (allies) |
  |---------|-------------------------------|--------------------|---------------------|
  | `none`  | personne                      | REFUSE             | REFUSE              |
  | `ally`  | un ALLIE du caster            | REFUSE             | **ACCEPTE** <- faux |
  | `enemy` | un ENNEMI du caster           | ACCEPTE            | REFUSE      <- faux |

Le bras `ally` est le FALSIFICATEUR : il est le seul ou l'ancien port et le natif divergent dans le
sens PERMISSIF, et le bras `enemy` est celui ou ils divergent dans le sens RESTRICTIF. Un montage a
deux bras (`none` / `enemy`) n'aurait pas suffi -- il aurait ete passe par les DEUX lectures.

**etape 4 (LIVE) -- `1014 ArmoriumCherub`, le gate porte par CETTE tranche.**

    // IdunBattle.AI.Playbook.Loki.ArmoriumCherubPlaybook$$ShouldExecute
    n = <IBattleQuery slot 0x42 = 66 GetValidTargets>(caster, new UnitPosition(casterTile),
                                                      ActiveAbilityType.Loki_NormalAttack).Count;
    if (n < 2) return !CanKillTarget(caster, casterTile, target);
    return true;

⚠ **La branche `n >= 2` est STRUCTURELLEMENT entrelacee avec le concurrent qu'il faut neutraliser** :
`n >= 2` signifie « au moins deux cibles a portee d'ATTAQUE NORMALE », donc l'attaque normale a
forcement un plan, donc son `CalculateCustomUtility = Fix64(1)` peut rafler l'argmax. Les deux bras
LIVE portent donc sur la branche `n < 2` (cible a distance 2 d'un caster melee : `n = 0`), ou le
gate se reduit a `!CanKillTarget` -- et c'est la partie NEUVE. La branche `n >= 2` est gardee
OFFLINE (cran de comportement) et son accord live est exige a SENS UNIQUE.

  | bras     | PV de la cible | `MightBeKill` | gate attendu |
  |----------|----------------|---------------|--------------|
  | `kill`   | 1              | vrai          | REFUSE       |
  | `nokill` | enormes        | faux          | ACCEPTE      |

Usage :
    python scripts/python/probe_419r1tr14r5r2r1r1r1r3r1_gates.py                    # offline
    python scripts/python/probe_419r1tr14r5r2r1r1r1r3r1_gates.py --live \
        --state-file <chemin ABSOLU unique>.json [--only 3]

ASCII only (console cp1252). rc 0 = toutes les etapes jouees s'accordent.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

HOST = "http://127.0.0.1:8765"
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))


class MontageError(RuntimeError):
    """Le montage n'est pas installe -- un bras qui ne mesure pas ce qu'il annonce."""


# --------------------------------------------------------------------------- transport

def _http(path, payload=None, timeout=200):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(HOST + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _sid():
    return (_http("/api/admin/status").get("session") or {}).get("id")


def rpc(method, body=None, timeout=200):
    r = _http("/api/scripts/%s/rpc" % _sid(),
              {"method": method, "args": [body] if body is not None else [],
               "timeout": timeout * 1000}, timeout=timeout + 60)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build_hash() -> str:
    with open(os.path.join(_ROOT, "data", "symbols", "CURRENT"), encoding="utf-8") as fh:
        return fh.read().strip()


# ====================================================================== etape 1 : les SLOTS

#: `(interface, slot, methode, param_count)` -- les cinq slots que la famille consomme, LUS dans
#: `data/symbols/<build>/metadata/interface_slots.tsv`. Le premier est celui qui a fait l'inversion,
#: le second est son VOISIN (`GetAllFriendsOf`), et c'est leur PROXIMITE qui rend le cran utile.
SLOTS = (
    ("IBattleQuery", 0x8e, "GetAllEnemiesOf", 1),      # 142 -- `1147 HadesAutocannons`
    ("IBattleQuery", 0x8d, "GetAllFriendsOf", 1),      # 141 -- le VOISIN qu'on lisait a tort
    ("IBattleQuery", 0x42, "GetValidTargets", 3),      # 66  -- `1014 ArmoriumCherub`
    ("IBattleQuery", 0x83, "GetAdjacentFriends", 2),   # 131 -- `1175 BloodChalice` (code MORT)
    ("IBattleQuery", 0xcd, "WillBeCharging", 3),       # 205 -- `1154 TacticalPrecision`
)


def etape1_slots(verbose: bool = True) -> dict:
    """Les cinq slots d'interface, confrontes a la table du build. AUCUN live."""
    build = _build_hash()
    path = os.path.join(_ROOT, "data", "symbols", build, "metadata", "interface_slots.tsv")
    table: dict = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 4:
                continue
            table[(c[0], int(c[1]))] = (c[2], int(c[3]))
    bad = 0
    if verbose:
        print("[etape 1] interface_slots.tsv build=%s" % build)
    for itf, slot, name, argc in SLOTS:
        got = table.get((itf, slot))
        ok = got == (name, argc)
        if not ok:
            bad += 1
        if verbose:
            print("  %s %s slot 0x%02x = %-20s (%d args) | table: %s"
                  % ("OK " if ok else "BAD", itf, slot, name, argc, got))
    return {"bad": bad, "build": build}


# ====================================================================== etape 2 : REACHABILITY

#: `(namespace, classe, declare EvaluateInternal ?, declare ShouldExecute ? -- LIVE)`
#:
#: Le verdict `gate vivant` se DERIVE : `ShouldExecute && !EvaluateInternal`. Il n'est PAS une
#: quatrieme donnee -- l'ecrire a part permettrait de le faire mentir.
#:
#: ⚠ **LA COLONNE `ShouldExecute` EST CELLE DE LA MESURE LIVE, ET LES DEUX SOURCES DIVERGENT SUR
#: `CultDemagoguePlaybook`** -- mesure du 2026-08-15 : `frida/methods.tsv` ne la porte PAS,
#: `resolveMethodPtr` la rend a `depth 0`. C'est exactement le faux negatif que le CLAUDE.md decrit
#: (« l'ABSENCE d'une methode dans les tables ne prouve RIEN » : IL2CPP DEDUPLIQUE les corps
#: triviaux, et un `ShouldExecute` non specialise pointe sur le corps de trois octets
#: `mov al,1 ; ret`, dont un seul proprietaire est nomme). L'etape OFFLINE ne peut donc juger que
#: les PRESENCES ; l'etape LIVE juge les deux. Ecrire ici la valeur offline aurait fige le faux
#: negatif comme s'il etait le fait.
REACH = (
    ("IdunBattle.AI.Playbook",      "BloodChalicePlaybook",      True,  True),
    ("IdunBattle.AI.Playbook.Loki", "MomentShacklePlaybook",     False, True),   # TEMOIN
    ("IdunBattle.AI.Playbook.Loki", "CultDemagoguePlaybook",     True,  True),
    ("IdunBattle.AI.Playbook.Loki", "ArmoriumCherubPlaybook",    False, True),
    ("IdunBattle.AI.Playbook.Loki", "TacticalPrecisionPlaybook", False, True),
)


def _methods_by_class(classes: set) -> dict:
    build = _build_hash()
    path = os.path.join(_ROOT, "data", "symbols", build, "frida", "methods.tsv")
    seen: dict = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 3 or c[2] not in classes:
                continue
            # Le nom de methode est ce qui suit `owner + "."` -- PAS un `rsplit(".", 1)`, qui
            # rendrait `cctor` pour `<Classe>..cctor` (meme piege que `probe_..._r2` etape 1).
            seen.setdefault(c[2], set()).add(c[1][len(c[2]) + 1:])
    return seen


def etape2_reachability(verbose: bool = True) -> dict:
    """`ShouldExecute` d'une classe qui OVERRIDE `EvaluateInternal` est INATTEIGNABLE.

    ⚠ Cette etape ne juge que `EvaluateInternal`, et c'est DELIBERE : l'ABSENCE d'une methode dans
    `methods.tsv` ne prouve rien (dedup IL2CPP des corps triviaux), donc un `ShouldExecute` absent
    y est un NON-DIT, pas un fait. La divergence mesuree (`CultDemagoguePlaybook` : absente
    offline, presente live) est IMPRIMEE comme telle -- elle est le TEMOIN que cette prudence n'est
    pas theorique."""
    full = {"%s.%s" % (ns, cls) for ns, cls, _e, _s in REACH}
    seen = _methods_by_class(full)
    bad, ecarts = 0, []
    if verbose:
        print("[etape 2] reachability -- frida/methods.tsv (OFFLINE ; juge `EvaluateInternal` SEUL)")
    for ns, cls, want_ei, want_se_live in REACH:
        names = seen.get("%s.%s" % (ns, cls)) or set()
        ei, se = ("EvaluateInternal" in names), ("ShouldExecute" in names)
        ok = (ei == want_ei)
        if not ok:
            bad += 1
        if se != want_se_live:
            ecarts.append(cls)
        if verbose:
            print("  %s %-28s EvaluateInternal=%-5s | ShouldExecute(offline)=%-5s%s"
                  % ("OK " if ok else "BAD", cls, ei, se,
                     "  <- ABSENT offline, PRESENT live (dedup IL2CPP)" if se != want_se_live
                     else ""))
    if verbose and ecarts:
        print("  ECART offline/live sur %d classe(s) : %s -- l'absence offline n'est pas un fait."
              % (len(ecarts), ", ".join(ecarts)))
    return {"bad": bad, "ecarts_offline_live": ecarts}


def etape2b_reachability_live(verbose: bool = True) -> dict:
    """La MEME question, mais posee au PROCESSUS (`resolveMethodPtr`, `class_get_methods` refait).

    ⚠ Ce cran existe parce que « la methode n'est pas dans la table » ne prouve RIEN par lui-meme
    (dedup IL2CPP des corps triviaux, bases generiques absentes du dump Frida). Le TEMOIN est
    `MomentShacklePlaybook` : elle DOIT rendre `ShouldExecute` a `depth 0` et PAS
    `EvaluateInternal` -- sinon l'absence mesuree n'est que la panne du RPC."""
    targets = []
    for ns, cls, _e, _s in REACH:
        targets.append({"ns": ns, "cls": cls, "method": "EvaluateInternal"})
        targets.append({"ns": ns, "cls": cls, "method": "ShouldExecute"})
    res = rpc("resolveMethodPtr", {"targets": targets, "maxDepth": 6}, 90) or {}
    if not res.get("ok"):
        print("[etape 2b] RPC KO: %s" % json.dumps(res)[:400])
        return {"bad": len(REACH), "measured": False}
    by = {(t.get("ns"), t.get("cls"), t.get("method")): t for t in (res.get("targets") or [])}
    bad = 0
    if verbose:
        print("[etape 2b] reachability -- resolveMethodPtr (LIVE, il2cppBase=%s)"
              % res.get("il2cppBase"))
    for ns, cls, want_ei, want_se in REACH:
        te = by.get((ns, cls, "EvaluateInternal")) or {}
        ts = by.get((ns, cls, "ShouldExecute")) or {}
        if not te.get("ok") or not ts.get("ok"):
            if verbose:
                print("  BAD %-28s classe introuvable : %s"
                      % (cls, te.get("error") or ts.get("error")))
            bad += 1
            continue
        ei = bool(((te.get("levels") or [{}])[0]).get("methods"))
        se = bool(((ts.get("levels") or [{}])[0]).get("methods"))
        ok = (ei == want_ei) and (se == want_se)
        if not ok:
            bad += 1
        if verbose:
            print("  %s %-28s EvaluateInternal@d0=%-5s ShouldExecute@d0=%-5s"
                  % ("OK " if ok else "BAD", cls, ei, se))
    return {"bad": bad, "measured": True}


# ====================================================================== outillage LIVE partage

BOARD = "MC1_67"
#: Caster de TOUS les bras live : `darkaTerminator` est la SEULE forme montable a `Movement = 0`
#: (trait **TeleportStrike** -> placement libre au premier tour, mesure du probe `..._r2` : 58
#: tuiles contre ZERO pour un caster sans Teleport), et son arme est MELEE PURE (`weapons` du
#: gameconfig : un seul profil `Power`, aucune cle `Range`) -- donc portee 1. C'est ce couple qui
#: rend le montage possible : `portee normale (1) < distance (2) <= range de l'ability (2)`.
CASTER = "darkaTerminator"
FOE = "adeptRetributor"
#: Porteur de `UnitTrait.Summon` amene par `--explicit-stats` (voie `case-92` SS4, recours 4) :
#: `genesSmnGenestealer` est declare par UNE seule ability (`MightFromBelow`), donc ses stats de
#: spawn sont NON AMBIGUES -- la moitie des summons du catalogue sont declares par plusieurs.
SUMMON = "genesSmnGenestealer"
DIST = 2


def _duel(*args) -> tuple:
    p = subprocess.run([sys.executable, "rl_duel.py", *args], cwd=_HERE, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _build(state_file: str, argv_tail: list) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--state-file", state_file,
            "--board", BOARD, "--no-ai", *argv_tail]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError("rl_duel build a echoue (rc=%s) : %s"
                           % (p.returncode, (p.stderr or p.stdout or "")[-900:]))
    with open(state_file, encoding="utf-8") as fh:
        return int(json.load(fh)["runnerId"])


def _dispose(rid) -> None:
    try:
        rpc("disposeRunner", {"runnerId": rid}, 60)
    except Exception:
        pass


def _graft_seed_bc(out_path: str, ability_ids, on_unit: str) -> str:
    """`BC.Units[<on_unit>].ActiveAbilities = [...]` dans une COPIE du seed BC (voie `case-92`
    SS5bis). JAMAIS le seed BC partage."""
    from rl_collect_batch import _load_seed_bc
    bc = _load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == on_unit:
            u["ActiveAbilities"] = list(ability_ids)
            n += 1
    if n != 1:
        raise MontageError("greffe impossible : %d entree(s) %r dans BC.Units" % (n, on_unit))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(bc, fh)
    return out_path


def _pos(u):
    p = (u or {}).get("pos") or {}
    return None if p.get("col") is None else (p["col"], p["row"])


def _dv(rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)


def _end_turn(sf: str, rid: int) -> None:
    """Termine NOTRE tour, puis attend qu'il nous revienne. L'ORDRE compte (cf. `..._r2`)."""
    _duel("act", "endturn", "--state-file", sf, "--no-ai")
    for _ in range(4):
        if rpc("battleStatus", {"runnerId": rid}, 40).get("currentPlayer") == 3:
            return
        _duel("act", "endturn", "--state-file", sf, "--no-ai")


def _movement_reach(mbu: dict, uid: int, here) -> int:
    import hexgeo
    tiles = [(t.get("col"), t.get("row")) for t in ((mbu.get(uid) or {}).get("tiles") or ())]
    tiles = [t for t in tiles if t[0] is not None]
    return max((hexgeo.distance(t, here) for t in tiles), default=0)


def _deploy_at(sf: str, rid: int, caster_uid: int, anchor_uid: int, want: int,
               rounds: int = 1) -> dict:
    """Place le caster a `want` hex de l'ancre, puis solde le tour.

    Le premier tour est un placement LIBRE (le deploiement ignore `Movement` pour l'unite en cours
    de placement, et `darkaTerminator` porte `TeleportStrike`) ; les tours suivants sont des
    APPROCHES ordinaires -- necessaires des que `want` est plus proche que ce que la zone de
    deploiement permet (mesure : depuis la zone de spawn, la distance MINIMALE a l'adversaire est
    **2** sur `MC1_67`, donc un montage MELEE demande un tour de plus). GEOMETRIE DRIVEE : on ne
    subit jamais le spawn (cf. `feedback_drive_positions_dont_blame_geometry`)."""
    import hexgeo
    for _ in range(max(1, rounds)):
        dv = _dv(rid)
        by = {u.get("id"): u for u in (dv.get("units") or ())}
        here, ap = _pos(by.get(caster_uid)), _pos(by.get(anchor_uid))
        if ap is None:
            break
        if here is not None and hexgeo.distance(here, ap) == want:
            break
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
        tiles = [(t.get("col"), t.get("row"))
                 for t in ((mbu.get(caster_uid) or {}).get("tiles") or ())]
        tiles = [t for t in tiles if t[0] is not None]
        if not tiles:
            _end_turn(sf, rid)
            continue
        best = min(tiles, key=lambda t: abs(hexgeo.distance(t, ap) - want))
        if best == here:
            break
        _duel("act", "move", "--state-file", sf, "--unit", str(caster_uid), "--to", "%d,%d" % best)
        _end_turn(sf, rid)
    _end_turn(sf, rid)
    dv = _dv(rid)
    by = {u.get("id"): u for u in (dv.get("units") or ())}
    here, ap = _pos(by.get(caster_uid)), _pos(by.get(anchor_uid))
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
    return {"dist": (None if (here is None or ap is None) else hexgeo.distance(here, ap)),
            "frozen": (here is not None and _movement_reach(mbu, caster_uid, here) == 0),
            "here": here}


def _place_once(sf: str, rid: int, uid: int, anchor_uid: int, want: int) -> bool:
    """UN placement de `uid` a `want` hex de `anchor_uid`, SANS finir le tour.

    Sert au montage a DEUX placements du meme tour de deploiement : on place le caster, PUIS on
    amene l'adversaire au contact -- ce qui evite les tours d'approche. C'est ce qui rend le bras
    `TurnsStarted` mesurable : chaque tour d'approche INCREMENTE le compteur qu'on veut observer
    sous son seuil (mesure du 1er jet : l'approche a elle seule portait `turnsStarted` a **4**,
    donc au-dessus de la bascule des la premiere mesure)."""
    import hexgeo
    dv = _dv(rid)
    by = {u.get("id"): u for u in (dv.get("units") or ())}
    ap, here = _pos(by.get(anchor_uid)), _pos(by.get(uid))
    if ap is None:
        return False
    if here is not None and hexgeo.distance(here, ap) == want:
        return True
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
    tiles = [(t.get("col"), t.get("row")) for t in ((mbu.get(uid) or {}).get("tiles") or ())]
    tiles = [t for t in tiles if t[0] is not None]
    if not tiles:
        return False
    best = min(tiles, key=lambda t: abs(hexgeo.distance(t, ap) - want))
    rc, _o = _duel("act", "move", "--state-file", sf, "--unit", str(uid), "--to", "%d,%d" % best)
    return rc == 0


def _geometry(rid: int, a: int, b: int) -> dict:
    import hexgeo
    dv = _dv(rid)
    by = {u.get("id"): u for u in (dv.get("units") or ())}
    pa, pb = _pos(by.get(a)), _pos(by.get(b))
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
    return {"dist": None if (pa is None or pb is None) else hexgeo.distance(pa, pb),
            "here": pa, "frozen": pa is not None and _movement_reach(mbu, a, pa) == 0}


def _normal_has_plan(dv, uid: int) -> bool:
    nids = set()
    for u in (dv.get("units") or ()):
        if u.get("id") == uid:
            nids = {a["id"] for a in (u.get("abilities") or ())
                    if a.get("kind") == "normal" and a.get("id") is not None}
    for pl in (dv.get("attackPlans") or ()):
        if pl.get("unitId") != uid:
            continue
        for ev in (pl.get("evals") or ()):
            if ev.get("abilityId") in nids and ev.get("rankCount"):
                return True
    return False


def _ability_castable_here(dv, uid: int, ability: int) -> bool:
    here = None
    for u in (dv.get("units") or ()):
        if u.get("id") == uid:
            here = _pos(u)
    for pl in (dv.get("attackPlans") or ()):
        if pl.get("unitId") != uid:
            continue
        for ev in (pl.get("evals") or ()):
            if ev.get("abilityId") != ability:
                continue
            if any((rk.get("col"), rk.get("row")) == here for rk in (ev.get("ranked") or ())):
                return True
    return False


def _ctx(rid: int, uid: int):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    dv = _dv(rid)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    _rpc = lambda m, b, t=60: rpc(m, dict(b or {}, runnerId=rid), t)             # noqa: E731
    return dv, _ai_ctx.build(_rpc, rid, dv, mbu, uid, W.load(),
                             _scene.build_predictor(_rpc, rid))


def _port_decides(ctx, ability: int, target: int) -> tuple:
    """`(u_gate, action_existe)` -- `u_gate` est l'ARGUMENT EXACT du gate natif
    (`CalculateCustomUtility + CalculateUtilityFromPredictions`), `action_existe` est ce que
    `calculate_action_utility` rend APRES lui (`None` = le `Nullable` VIDE natif)."""
    from engine.playbook import get_playbook_or_default
    pb = get_playbook_or_default(ability)
    evs = pb.make_damage_predictions(ctx, ctx.origin, target, ability)
    if not evs:
        return None, False
    u, _bk = pb.calculate_utility_from_predictions(ctx, ctx.origin, target, ability, evs)
    u += pb.calculate_custom_utility(ctx, ctx.origin, target, ability)
    return u, pb.calculate_action_utility(ctx, ctx.origin, target, ability) is not None


def _native_proposes(rid: int, uid: int, ability: int) -> tuple:
    dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, 300)
    msgs = []
    for u in (dry.get("units") or ()):
        if u.get("unitId") == uid:
            msgs = [(m.get("cls"), m.get("abilityType")) for m in (u.get("proposed") or ())]
    return (any(c == "ActiveAbilityMessage" and a == ability for c, a in msgs), msgs)


@contextlib.contextmanager
def gate_cut(ability: int):
    """COUPE le gate porte pour CETTE ability -- `should_execute` rend `True` quoi qu'il arrive,
    c.-a-d. STRICTEMENT le port sans le gate. On mute la METHODE de l'instance du registre."""
    from engine.playbook import get_playbook_or_default
    from engine.playbook.base import ComparablePlaybook
    pb = get_playbook_or_default(ability)
    cls = type(pb)
    saved = cls.should_execute
    cls.should_execute = ComparablePlaybook.should_execute
    try:
        yield
    finally:
        cls.should_execute = saved


@contextlib.contextmanager
def gate_inverted_1147():
    """CONTRE-EPREUVE dediee au bras `ally` : le gate de `1147` remis a la lecture FAUSSE
    (les ALLIES au lieu des ennemis), c.-a-d. le port d'AVANT ce correctif. Sans elle, l'accord
    natif/port des trois bras ne dirait pas que l'inversion etait OBSERVABLE."""
    from engine.playbook.should_execute_gates import HadesAutocannonsPlaybook as H
    from engine.playbook.prediction._shared import _entity_traits

    def _ancien(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return True
        team = sc.team(getattr(ctx, "uid", None))
        if team is None:
            return True
        want = self.REQUIRED_ENEMY_TRAIT.name
        for u in (sc.units or ()):
            uid = u.get("id")
            if uid is None or u.get("team") != team:      # <- ALLIES : la lecture FAUSSE
                continue
            if want in _entity_traits(sc, uid):
                return True
        return False

    saved = H.should_execute
    H.should_execute = _ancien
    try:
        yield
    finally:
        H.should_execute = saved


# ====================================================================== etape 3 : 1147, trois bras

A1147 = 1147
#: Second porteur de `UnitTrait.Summon`, du COTE ALLIE -- il faut deux visualId DISTINCTS pour que
#: la table `visualId -> id` de `decisionView` reste injective. `thousSmnScreamer` est declare par
#: une seule ability (`MasterOfTheTutelaries`), donc ses stats de spawn sont non ambigues.
SUMMON_ALLY = "thousSmnScreamer"

# ⚠ **CE QUE LA MESURE A IMPOSE AU MONTAGE, ET QUI CHANGE LE VERDICT.**
#
# Le premier jet montait trois bras (`none` / `ally` / `enemy`) et attendait que le natif REFUSE
# dans les deux premiers. Il a rendu, sur les deux, `castHere = False` et `abilityTargets` a ZERO --
# et le RPC `abilityReason` a NOMME la cause :
#
#     targetReason = { ruleClass: "GenericBrokenTargetingRule",
#                      hex: "0x0000000000002000", reasons: ["TargetIsSummon"] }
#
# Le masque de `HadesAutocannonsAbility` porte `TargetIsSummon` (bit 13), et ce bit est LE MEME
# predicat que le gate : `HasTrait(target, UnitTrait.Summon)` (cf.
# `engine/runner/abilities/targeting.py`, bloc TRAITS). **Donc, sur la route du natif, le gate est
# une TAUTOLOGIE** : `CalculateActionUtility` n'est appelee que pour un couple (caster, target) que
# `GetEligibleTargetsSelectable` a laisse passer, donc pour une cible qui EST un summon ENNEMI,
# donc la boucle de `ShouldExecute` en trouve un et rend `true`. Le natif ne peut PAS refuser ici.
#
# Consequence sur ce que la tranche corrige, et elle est plus forte que prevu : l'ancienne lecture
# (les ALLIES) etait une degradation **RESTRICTIVE**, pas permissive -- le port REFUSAIT un cast
# que le natif fait, des que le camp du caster n'avait pas de summon a lui. C'est ce que le bras
# `enemy` mesure, et c'est le seul bras qui puisse mesurer quoi que ce soit.
#
#   | bras    | summon ENNEMI | summon ALLIE | cibles legales | natif | port corrige | port ANCIEN |
#   |---------|---------------|--------------|----------------|-------|--------------|-------------|
#   | `enemy` | oui           | non          | >= 1           | OUI   | OUI          | **NON**     |
#   | `both`  | oui           | oui          | >= 1           | OUI   | OUI          | oui         |
#   | `none`  | non           | non          | **0**          | non   | non          | non         |
#
# Le bras `both` est le TEMOIN de coincidence : il montre que l'ancien port ne « marchait » que
# quand un allie portait par hasard le trait. Le bras `none` mesure la NON-DISCRIMINATION (aucune
# cible legale -> le gate n'est jamais atteint), c.-a-d. la tautologie elle-meme.


def _legal_targets(rid: int, uid: int, ability: int) -> list:
    """Les cibles LEGALES `fromHere` (le natif applique deja le masque et la regle dynamique)."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": uid, "allAbilities": True}, 120) or {}
    out = []
    for u in (at.get("units") or ()):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or ()):
            if a.get("abilityId") != ability:
                continue
            for t in (a.get("fromHere") or ()):
                tid = t.get("targetId")
                if t.get("kind") == "unit" and tid is not None:
                    out.append(int(tid))
    return out


#: `(bras, summon du camp ADVERSE, summon du camp du CASTER)`
ARMS_1147 = (("enemy", SUMMON, None), ("both", SUMMON, SUMMON_ALLY), ("none", None, None))


def _summon_sides(rid: int, cid: int) -> dict:
    """`{"enemy": [uids], "ally": [uids]}` -- les porteurs de `UnitTrait.Summon`, classes par camp
    RELATIVEMENT au caster.

    ⚠ La resolution se fait par le TRAIT MESURE, pas par le `visualId` demande : `--p-units
    thousSmnScreamer` fait apparaitre `thousNpc2Screamer` sur le plateau (mesure du 2026-08-15 --
    la normalisation substitue le jumeau npc). Un montage qui apparie par le nom demande accuse
    alors une absence qui n'en est pas une, et un montage qui l'IGNORE mesurerait un bras dont il
    ignore la composition."""
    from engine.playbook.prediction._shared import _entity_traits
    _dv2, ctx = _ctx(rid, cid)
    sc, team = ctx.scene, ctx.scene.team(cid)
    out = {"enemy": [], "ally": []}
    for u in (sc.units or ()):
        uid = u.get("id")
        if uid is None or uid == cid:
            continue
        if "Summon" in _entity_traits(sc, uid):
            out["ally" if sc.team(uid) == team else "enemy"].append(int(uid))
    return out


def _stage_1147(logs: str, tag: str, enemy_smn, ally_smn, seed_bc: str) -> dict:
    sf = os.path.join(logs, "tr14r5r2r1r1r1r3r1_1147_%s.json" % tag)
    p_units = [CASTER] + ([ally_smn] if ally_smn else [])
    a_units = [FOE] + ([enemy_smn] if enemy_smn else [])
    tail = ["--seed", "4242", "--seed-bc", seed_bc,
            "--p-units", ",".join(p_units), "--a-units", ",".join(a_units),
            "--unit-stat", "%s:Movement=0" % CASTER]
    for s in (enemy_smn, ally_smn):
        if s:
            tail += ["--explicit-stats", s]
    rid = _build(sf, tail)
    dv = _dv(rid)
    ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
    for want in (CASTER, FOE):
        if ids.get(want) is None:
            _dispose(rid)
            raise MontageError("montage 1147/%s : %r absent (units=%s)" % (tag, want, sorted(ids)))
    sides = _summon_sides(rid, ids[CASTER])
    # L'ANCRE du placement est le summon ENNEMI quand il existe (c'est la SEULE cible legale de
    # 1147) ; a defaut le `FOE`, et le bras mesure alors zero cible -- ce qui EST son objet.
    anchor = sides["enemy"][0] if sides["enemy"] else ids[FOE]
    geo = _deploy_at(sf, rid, ids[CASTER], anchor, DIST)
    return {"tag": tag, "rid": rid, "sf": sf, "ids": ids, "anchor": anchor, "sides": sides, **geo}


def _measure_1147(case: dict) -> dict:
    dv, ctx = _ctx(case["rid"], case["ids"][CASTER])
    cid = case["ids"][CASTER]
    legal = _legal_targets(case["rid"], cid, A1147)
    tid = legal[0] if legal else case["anchor"]
    u, port = _port_decides(ctx, A1147, tid)
    with gate_cut(A1147):
        _u2, cut = _port_decides(ctx, A1147, tid)
    with gate_inverted_1147():
        _u3, old = _port_decides(ctx, A1147, tid)
    nat, msgs = _native_proposes(case["rid"], cid, A1147)
    return {"arm": case["tag"], "dist": case["dist"], "frozen": case["frozen"],
            "normal_plan": _normal_has_plan(dv, cid), "legal": len(legal), "target": tid,
            "n_enemy_smn": len(case["sides"]["enemy"]), "n_ally_smn": len(case["sides"]["ally"]),
            "u": u, "native": nat, "port": port,
            "port_gate_cut": cut, "port_ancien": old, "msgs": msgs}


def etape3_live_1147(logs: str, verbose: bool = True) -> dict:
    seed_bc = _graft_seed_bc(os.path.join(logs, "bc_1147_graft.json"), [A1147], CASTER)
    rows, bad = [], 0
    for tag, esmn, asmn in ARMS_1147:
        case = _stage_1147(logs, tag, esmn, asmn, seed_bc)
        try:
            rows.append(_measure_1147(case))
        finally:
            _dispose(case["rid"])
    if verbose:
        print("[etape 3] 1147 HadesAutocannons -- greffee sur %s, board %s, Movement=0, dist=%d"
              % (CASTER, BOARD, DIST))
        for r in rows:
            print("  [%-5s] smnEnnemis=%d smnAllies=%d legal=%-3d dist=%-4s frozen=%-5s "
                  "normalPlan=%-5s u=%-9s natif=%-5s port=%-5s ancien=%-5s"
                  % (r["arm"], r["n_enemy_smn"], r["n_ally_smn"], r["legal"], r["dist"],
                     r["frozen"], r["normal_plan"],
                     "None" if r["u"] is None else round(r["u"], 3),
                     r["native"], r["port"], r["port_ancien"]))

    #: `(bras, nb de summons ENNEMIS attendu, nb de summons ALLIES attendu)` -- le montage est
    #: verifie sur la MESURE des traits, pas sur les ids demandes a `--p-units`.
    want_sides = {"enemy": (1, 0), "both": (1, 1), "none": (0, 0)}
    by = {r["arm"]: r for r in rows}
    for r in rows:
        # MONTAGE -- trois conditions communes.
        if (not r["frozen"]) or r["dist"] != DIST or r["normal_plan"]:
            print("  BAD MONTAGE [%s] frozen=%s dist=%s normalPlan=%s"
                  % (r["arm"], r["frozen"], r["dist"], r["normal_plan"]))
            bad += 1
            continue
        if (r["n_enemy_smn"], r["n_ally_smn"]) != want_sides[r["arm"]]:
            print("  BAD MONTAGE [%s] summons (ennemis, allies) = %s (attendu %s)"
                  % (r["arm"], (r["n_enemy_smn"], r["n_ally_smn"]), want_sides[r["arm"]]))
            bad += 1
            continue
        # REGIME : `enemy`/`both` DOIVENT avoir une cible legale, `none` DOIT n'en avoir aucune --
        # c'est la mesure de la TAUTOLOGIE (le gate n'est atteint que la ou il ne peut qu'accepter).
        if (r["legal"] > 0) != (r["arm"] in ("enemy", "both")):
            print("  BAD REGIME [%s] cibles legales=%d" % (r["arm"], r["legal"]))
            bad += 1
            continue
        if r["arm"] == "none":
            # Aucune cible legale : ni le natif ni le port ne peuvent proposer. Le bras ne mesure
            # PAS le gate, et c'est ce qu'il est la pour etablir.
            if r["native"] or r["port"]:
                print("  VIOLE none : natif=%s port=%s alors qu'AUCUNE cible n'est legale"
                      % (r["native"], r["port"]))
                bad += 1
            continue
        # CRITERE A : accord natif/port, et les DEUX doivent ACCEPTER.
        if not (r["native"] and r["port"]):
            print("  VIOLE A [%s] natif=%s port=%s msgs=%s"
                  % (r["arm"], r["native"], r["port"], r["msgs"]))
            bad += 1
        # CRITERE B : le gate porte est INERTE ici -- le couper ne change rien. C'est la forme
        # executable de « le gate est une tautologie sur la route du natif ».
        if r["port_gate_cut"] != r["port"]:
            print("  VIOLE B [%s] le gate MORD (gate_cut=%s port=%s) alors que la seule cible "
                  "legale est un summon ennemi" % (r["arm"], r["port_gate_cut"], r["port"]))
            bad += 1
    # CRITERE C -- L'INVERSION ETAIT OBSERVABLE, ET DANS LE SENS RESTRICTIF. Le port d'AVANT
    # REFUSE le bras `enemy` (aucun allie porteur) et ACCEPTE le bras `both` (un allie porteur par
    # coincidence). Sans ce cran, l'accord des deux bras se lirait « le gate n'a jamais rien
    # change » -- alors qu'il changeait le verdict d'une action que le natif emet.
    if {"enemy", "both"} <= set(by):
        if by["enemy"]["port_ancien"] is not False:
            print("  VIOLE C : le port ANCIEN n'a pas refuse le bras `enemy` (ancien=%s) -- "
                  "la contre-epreuve est INERTE" % by["enemy"]["port_ancien"])
            bad += 1
        if by["both"]["port_ancien"] is not True:
            print("  VIOLE C : le port ANCIEN n'a pas accepte le bras `both` (ancien=%s)"
                  % by["both"]["port_ancien"])
            bad += 1
    return {"bad": bad, "rows": rows}


# ====================================================================== etape 4 : 1014, deux bras

A1014 = 1014
#: PV de la cible dans le bras `nokill`. Choisi tres au-dessus du degat maximal de `1014` pour que
#: `MightBeKill` soit FAUX ; la valeur effective de `kill` est ensuite MESUREE, pas supposee.
HP_NOKILL = 4_000_000


def _stage_1014(logs: str, tag: str, seed_bc: str, hp: int) -> dict:
    sf = os.path.join(logs, "tr14r5r2r1r1r1r3r1_1014_%s.json" % tag)
    rid = _build(sf, ["--seed", "4242", "--seed-bc", seed_bc,
                      "--p-units", CASTER, "--a-units", FOE,
                      "--unit-stat", "%s:Movement=0" % CASTER,
                      "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (FOE, hp, hp)])
    dv = _dv(rid)
    ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
    if ids.get(CASTER) is None or ids.get(FOE) is None:
        _dispose(rid)
        raise MontageError("montage 1014/%s : units=%s" % (tag, sorted(ids)))
    geo = _deploy_at(sf, rid, ids[CASTER], ids[FOE], DIST)
    return {"tag": tag, "rid": rid, "sf": sf, "ids": ids, "hp": hp, **geo}


def _measure_1014(case: dict) -> dict:
    from engine.playbook import get_playbook_or_default
    from engine.playbook.noncomparable import _base as _nc_base
    dv, ctx = _ctx(case["rid"], case["ids"][CASTER])
    cid, fid = case["ids"][CASTER], case["ids"][FOE]
    pb = get_playbook_or_default(A1014)
    n = _nc_base.count_eligible_normal_attack_targets(ctx, cid, ctx.origin, ctx.epos)
    can_kill = pb._can_kill_target(ctx, ctx.origin, fid, A1014)
    u, port = _port_decides(ctx, A1014, fid)
    with gate_cut(A1014):
        _u2, cut = _port_decides(ctx, A1014, fid)
    nat, msgs = _native_proposes(case["rid"], cid, A1014)
    return {"arm": case["tag"], "hp": case["hp"], "dist": case["dist"], "frozen": case["frozen"],
            "normal_plan": _normal_has_plan(dv, cid),
            "castable_here": _ability_castable_here(dv, cid, A1014),
            "n_targets": n, "can_kill": can_kill, "u": u,
            "native": nat, "port": port, "port_gate_cut": cut, "msgs": msgs}


def etape4_live_1014(logs: str, verbose: bool = True) -> dict:
    seed_bc = _graft_seed_bc(os.path.join(logs, "bc_1014_graft.json"), [A1014], CASTER)
    rows, bad = [], 0
    for tag, hp in (("kill", 1), ("nokill", HP_NOKILL)):
        case = _stage_1014(logs, tag, seed_bc, hp)
        try:
            rows.append(_measure_1014(case))
        finally:
            _dispose(case["rid"])
    if verbose:
        print("[etape 4] 1014 ArmoriumCherub -- greffee sur %s, board %s, Movement=0, dist=%d"
              % (CASTER, BOARD, DIST))
        for r in rows:
            print("  [%-6s] hp=%-9d n=%-4s canKill=%-5s dist=%-4s frozen=%-5s normalPlan=%-5s "
                  "castHere=%-5s u=%-9s natif=%-5s port=%-5s"
                  % (r["arm"], r["hp"], r["n_targets"], r["can_kill"], r["dist"], r["frozen"],
                     r["normal_plan"], r["castable_here"],
                     "None" if r["u"] is None else round(r["u"], 3), r["native"], r["port"]))
    want = {"kill": False, "nokill": True}
    for r in rows:
        if (not r["frozen"]) or r["dist"] != DIST or r["normal_plan"] or not r["castable_here"]:
            print("  BAD MONTAGE [%s] frozen=%s dist=%s normalPlan=%s castHere=%s"
                  % (r["arm"], r["frozen"], r["dist"], r["normal_plan"], r["castable_here"]))
            bad += 1
            continue
        # REGIME : la branche exercee DOIT etre `n < 2` (le caster est melee, la cible a 2 hex), et
        # `MightBeKill` doit valoir ce que le bras annonce -- sinon le bras ne discrimine rien.
        if r["n_targets"] is None or r["n_targets"] >= 2:
            print("  BAD REGIME [%s] n=%s : la branche `n < 2` n'est pas celle exercee"
                  % (r["arm"], r["n_targets"]))
            bad += 1
            continue
        if bool(r["can_kill"]) != (r["arm"] == "kill"):
            print("  BAD REGIME [%s] canKill=%s (attendu %s)"
                  % (r["arm"], r["can_kill"], r["arm"] == "kill"))
            bad += 1
            continue
        if bool(r["port"]) != want[r["arm"]]:
            print("  VIOLE B [%s] port=%s (attendu %s)" % (r["arm"], r["port"], want[r["arm"]]))
            bad += 1
        if bool(r["native"]) != bool(r["port"]):
            print("  VIOLE A [%s] natif=%s port=%s msgs=%s"
                  % (r["arm"], r["native"], r["port"], r["msgs"]))
            bad += 1
        if (r["port_gate_cut"] != r["port"]) != (not r["port"]):
            print("  VIOLE C [%s] gate_cut=%s port=%s" % (r["arm"], r["port_gate_cut"], r["port"]))
            bad += 1
    return {"bad": bad, "rows": rows}


# ============================================ etape 5 : 1010 StormOfFlensingBlades (tuile de cast)

A1010 = 1010

# `IdunBattle.AI.Playbook.Loki.StormOfFlensingBladesPlaybook$$ShouldExecute` :
#
#     return casterTile == EntityExtensions.GetMainTile(caster, this.<+0x20 = state>);
#
# ⚠ **CE QUE CETTE ETAPE A MESURE N'EST PAS CE QU'ELLE CHERCHAIT, ET C'EST LE RESULTAT.**
# Le montage visait la bascule du gate « je ne me deplace pas pour lancer ». Il a rendu, sur les
# DEUX bras, `okAvecGate = okSansGate = 0` : le port ne produit AUCUNE prediction pour `1010`,
# donc `calculate_action_utility` rend `None` a la garde `if not events` -- **AVANT** le gate. Le
# gate de `1010` est donc **INERTE dans le port**, et la contre-epreuve qui devait le falsifier est
# elle-meme muette.
#
# La cause est LUE, pas supposee. `IdunBattle.AI.Playbook.Loki.StormOfFlensingBladesPlaybook$$
# MakeDamagePredictions` existe et n'est PAS portee :
#
#     pred = battleQuery.<slot d'interface 0x22 = 34 -- la prediction d'ABILITY>(
#                caster, target, casterPosition);
#     ev = new ProbableDamageEvent(target, pred, default, default);
#     if (ev.<DamagePredictionResult @+0x8>.get_WillBeKill())
#         return new ProbableDamageEvent[0];                 // liste VIDE si le kill est SUR
#     return new ProbableDamageEvent[2] { ev, ev };           // sinon l'event DEUX FOIS
#
# Deux quirks qu'aucun chemin generique ne reproduit : la liste VIDE sur SURE-kill (donc
# `attackHealUtility = custom` seul) et le DOUBLE COMPTAGE de l'unique event. Le port, lui, passe
# par la prediction generique, qui ne sait rien faire d'une ability dont le gameconfig ne porte
# AUCUNE constante (`StormOfFlensingBlades.constants` est `null` : ni `damageProfile`, ni
# `nrOfHits`, ni `range`) -- d'ou la liste vide.
#
# Cette etape GARDE donc le constat, avec son temoin : le natif, lui, PROPOSE bien `1010`
# (`aiDryRunAllUnits` -> `ActiveAbilityMessage(1010)` sur le bras `here`). L'ecart port/natif est
# RESTRICTIF et il precede le gate. Residu : le port de `$$MakeDamagePredictions`.
STORM_RANGE = 1          # `StormOfFlensingBlades.constants` n'a AUCUNE cle `range` -> melee.


def _ranked_tiles(dv, uid: int, ability: int) -> list:
    for pl in (dv.get("attackPlans") or ()):
        if pl.get("unitId") != uid:
            continue
        for ev in (pl.get("evals") or ()):
            if ev.get("abilityId") == ability:
                return [(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or ())
                        if rk.get("col") is not None]
    return []


def _stage_1010(logs: str, tag: str, seed_bc: str, want: int) -> dict:
    sf = os.path.join(logs, "tr14r5r2r1r1r1r3r1_1010_%s.json" % tag)
    rid = _build(sf, ["--seed", "4242", "--seed-bc", seed_bc,
                      "--p-units", CASTER, "--a-units", FOE])
    dv = _dv(rid)
    ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
    if ids.get(CASTER) is None or ids.get(FOE) is None:
        _dispose(rid)
        raise MontageError("montage 1010/%s : units=%s" % (tag, sorted(ids)))
    # 4 rounds : la zone de deploiement de `MC1_67` ne descend pas sous 2 hex de l'adversaire, donc
    # le bras `here` (MELEE) exige une APPROCHE, pas seulement un placement.
    geo = _deploy_at(sf, rid, ids[CASTER], ids[FOE], want, rounds=4)
    return {"tag": tag, "rid": rid, "sf": sf, "ids": ids, "want": want, **geo}


def _measure_1010(case: dict) -> dict:
    from engine.playbook import get_playbook_or_default
    dv, ctx = _ctx(case["rid"], case["ids"][CASTER])
    cid, fid = case["ids"][CASTER], case["ids"][FOE]
    pb = get_playbook_or_default(A1010)
    tiles = _ranked_tiles(dv, cid, A1010) or [ctx.origin]
    ok_gate = [t for t in tiles
               if pb.calculate_action_utility(ctx, t, fid, A1010) is not None]
    with gate_cut(A1010):
        ok_cut = [t for t in tiles
                  if pb.calculate_action_utility(ctx, t, fid, A1010) is not None]
    nat, msgs = _native_proposes(case["rid"], cid, A1010)
    return {"arm": case["tag"], "dist": case["dist"], "want": case["want"],
            "origin": ctx.origin, "n_ranked": len(tiles),
            "legal_here": len(_legal_targets(case["rid"], cid, A1010)),
            "ok_gate": [tuple(t) for t in ok_gate], "n_ok_gate": len(ok_gate),
            "n_ok_cut": len(ok_cut), "native": nat, "msgs": msgs}


def etape5_live_1010(logs: str, verbose: bool = True) -> dict:
    seed_bc = _graft_seed_bc(os.path.join(logs, "bc_1010_graft.json"), [A1010], CASTER)
    rows, bad = [], 0
    for tag, want in (("here", STORM_RANGE), ("away", 3)):
        case = _stage_1010(logs, tag, seed_bc, want)
        try:
            rows.append(_measure_1010(case))
        finally:
            _dispose(case["rid"])
    if verbose:
        print("[etape 5] 1010 StormOfFlensingBlades -- greffee sur %s, board %s (Movement INTACT)"
              % (CASTER, BOARD))
        for r in rows:
            print("  [%-4s] dist=%-4s (voulu %d) origine=%-8s ranked=%-3d legalHere=%-3d "
                  "okAvecGate=%-3d okSansGate=%-3d natif=%s"
                  % (r["arm"], r["dist"], r["want"], r["origin"], r["n_ranked"], r["legal_here"],
                     r["n_ok_gate"], r["n_ok_cut"], r["native"]))
    by = {r["arm"]: r for r in rows}
    for r in rows:
        if r["dist"] != r["want"]:
            print("  BAD MONTAGE [%s] dist=%s (voulu %d)" % (r["arm"], r["dist"], r["want"]))
            bad += 1
            continue
        # CRITERE 1 -- LE GATE EST INERTE DANS LE PORT, et la contre-epreuve le PROUVE : couper le
        # gate ne change RIEN, donc ce n'est pas lui qui bloque. Si un jour la prediction de `1010`
        # est portee, `n_ok_cut` deviendra non nul et cette ligne rougira : le cran est un
        # DECLENCHEUR, pas un constat fige.
        if r["n_ok_gate"] != 0 or r["n_ok_cut"] != 0:
            print("  CHANGEMENT [%s] le port produit desormais des candidats pour 1010 "
                  "(avecGate=%d sansGate=%d) : la prediction a ete portee, ce bras doit etre "
                  "REECRIT en confrontation de gate" % (r["arm"], r["n_ok_gate"], r["n_ok_cut"]))
            bad += 1
    if {"here", "away"} <= set(by):
        # CRITERE 2 -- L'ECART EST RESTRICTIF, et il PRECEDE le gate : depuis l'origine, le natif
        # PROPOSE `1010` (temoin), le port n'a aucun candidat. Sans ce temoin, « le port ne propose
        # rien » se lirait comme « il n'y avait rien a proposer ».
        if not by["here"]["native"]:
            print("  TEMOIN ABSENT [here] le natif ne propose PAS 1010 a dist %d (legalHere=%d, "
                  "msgs=%s) -- l'ecart mesure n'est alors pas etabli"
                  % (by["here"]["dist"], by["here"]["legal_here"], by["here"]["msgs"]))
            bad += 1
        if by["here"]["legal_here"] < 1:
            print("  TEMOIN ABSENT [here] aucune cible legale depuis l'origine")
            bad += 1
        # Le bras `away` est le controle : hors de portee, le natif ne propose rien non plus.
        if by["away"]["native"] or by["away"]["legal_here"] != 0:
            print("  VIOLE [away] natif=%s legalHere=%d alors que la cible est hors de portee"
                  % (by["away"]["native"], by["away"]["legal_here"]))
            bad += 1
    return {"bad": bad, "rows": rows}


# ================================================ etape 6 : 1095 ReapingScythe (TurnsStarted > 2)

A1095 = 1095

# `IdunBattle.AI.Playbook.Loki.ReapingScythePlaybook$$ShouldExecute` :
#
#     if (!(attackHealUtility > Fix64(0))) return false;
#     return UnitExtensions.GetStat(caster, StatType.TurnsStarted, Current, 0) > 2;
#
# Le discriminant est le TEMPS, donc les deux bras vivent sur UN SEUL runner et partagent
# EXACTEMENT la meme geometrie : seul `turnsStarted` change. C'est le montage le moins confondable
# du probe -- aucun autre parametre ne bouge entre les deux mesures.
#
# ⚠ **La greffe est legitime ICI, et il faut le dire** : le gate lit une stat du CASTER
# (`TurnsStarted`), ce que la recette de `case-92` SS5bis interdit en general. Mais `TurnsStarted`
# est un COMPTEUR DE BATAILLE, pas une valeur de kit : il vaut la meme chose pour n'importe quel
# porteur au meme tour. La greffe n'importe donc AUCUNE valeur du vrai porteur
# (`deathBossMortarion`, npc) dans ce que le gate lit.
MAX_CYCLES = 6


def etape6_live_1095(logs: str, verbose: bool = True) -> dict:
    from engine.playbook import get_playbook_or_default
    seed_bc = _graft_seed_bc(os.path.join(logs, "bc_1095_graft.json"), [A1095], CASTER)
    sf = os.path.join(logs, "tr14r5r2r1r1r1r3r1_1095.json")
    # ⚠ PAS de `Movement = 0` ici, et c'est une CONTRAINTE MESUREE : `ReapingScythe` n'a aucune
    # cle `range` a sa config (donc MELEE), et la zone de deploiement de `MC1_67` ne descend pas
    # sous 2 hex de l'adversaire -- il FAUT une approche. Le concurrent (l'attaque normale) est
    # alors present, mais il est CONSTANT d'un cycle a l'autre : le discriminant de ce bras est le
    # TEMPS, pas la geometrie, et les deux mesures partagent le meme etat a `turnsStarted` pres.
    rid = _build(sf, ["--seed", "4242", "--seed-bc", seed_bc,
                      "--p-units", CASTER, "--a-units", FOE])
    rows, bad = [], 0
    try:
        dv = _dv(rid)
        ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
        if ids.get(CASTER) is None or ids.get(FOE) is None:
            raise MontageError("montage 1095 : units=%s" % sorted(ids))
        cid, fid = ids[CASTER], ids[FOE]
        # MELEE (aucune cle `range` a la config). DEUX placements dans le MEME tour de deploiement :
        # le caster d'abord, puis l'ADVERSAIRE au contact -- une approche coute un tour, et un tour
        # incremente exactement le compteur qu'on veut observer SOUS son seuil.
        _place_once(sf, rid, cid, fid, 2)
        _place_once(sf, rid, fid, cid, 1)
        _end_turn(sf, rid)
        geo = _geometry(rid, cid, fid)
        pb = get_playbook_or_default(A1095)
        for k in range(MAX_CYCLES):
            dvk, ctx = _ctx(rid, cid)
            ts = ctx.scene.turns_started(cid)
            u, port = _port_decides(ctx, A1095, fid)
            with gate_cut(A1095):
                _u2, cut = _port_decides(ctx, A1095, fid)
            nat, msgs = _native_proposes(rid, cid, A1095)
            rows.append({"cycle": k, "turns_started": ts, "u": u, "native": nat, "port": port,
                         "port_gate_cut": cut, "dist": geo["dist"],
                         "legal": len(_legal_targets(rid, cid, A1095)), "msgs": msgs})
            _end_turn(sf, rid)
    finally:
        _dispose(rid)
    if verbose:
        print("[etape 6] 1095 ReapingScythe -- greffee sur %s, board %s, Movement=0, MELEE (dist 1)"
              % (CASTER, BOARD))
        for r in rows:
            print("  [cycle %d] turnsStarted=%-5s legal=%-3d u=%-9s natif=%-5s port=%-5s "
                  "sansGate=%-5s" % (r["cycle"], r["turns_started"], r["legal"],
                                     "None" if r["u"] is None else round(r["u"], 3),
                                     r["native"], r["port"], r["port_gate_cut"]))
    # REGIME : il faut AU MOINS un cycle de chaque cote de la bascule, sinon rien n'est mesure.
    sous = [r for r in rows if r["turns_started"] is not None and r["turns_started"] <= 2]
    sur = [r for r in rows if r["turns_started"] is not None and r["turns_started"] > 2]
    if not sous or not sur:
        print("  BAD REGIME : la bascule `TurnsStarted > 2` n'est pas franchie "
              "(sous=%d, sur=%d, valeurs=%s)"
              % (len(sous), len(sur), [r["turns_started"] for r in rows]))
        return {"bad": 1, "rows": rows}
    for r in rows:
        if r["legal"] < 1:
            print("  BAD MONTAGE [cycle %d] aucune cible legale" % r["cycle"])
            bad += 1
            continue
        # CRITERE B : le gate porte bascule EXACTEMENT au seuil natif (`> 2`, STRICT).
        want = bool(r["turns_started"] is not None and r["turns_started"] > 2 and (r["u"] or 0) > 0)
        if bool(r["port"]) != want:
            print("  VIOLE B [cycle %d] ts=%s u=%s port=%s (attendu %s)"
                  % (r["cycle"], r["turns_started"], r["u"], r["port"], want))
            bad += 1
        # CRITERE A -- **UNILATERAL, ET C'EST UNE CONTRAINTE DE MONTAGE, PAS UN RELACHEMENT.**
        # `ReapingScythe` est MELEE : la cible est a UN hex, donc l'ATTAQUE NORMALE a toujours un
        # plan et son `CalculateCustomUtility = Fix64(1)` peut rafler l'argmax. `aiDryRunAllUnits`
        # rend l'action GAGNANTE, pas « l'ability est proposable » -- un natif qui ne propose pas
        # 1095 a donc DEUX causes possibles au-dessus du seuil. Ce qui reste exigible dans les deux
        # sens : **le port ne refuse JAMAIS ce que le natif choisit**. Sous le seuil, en revanche,
        # le natif ne PEUT pas le proposer, et c'est ce que la ligne suivante garde.
        if r["native"] and not r["port"]:
            print("  VIOLE A [cycle %d] le natif propose 1095 et le port REFUSE (ts=%s) msgs=%s"
                  % (r["cycle"], r["turns_started"], r["msgs"]))
            bad += 1
        if (r["turns_started"] is not None and r["turns_started"] <= 2) and r["native"]:
            print("  VIOLE A' [cycle %d] le natif propose 1095 a ts=%s (<= 2) : le gate ne mord "
                  "pas cote natif -- msgs=%s" % (r["cycle"], r["turns_started"], r["msgs"]))
            bad += 1
        if (r["port_gate_cut"] != r["port"]) != (not r["port"]):
            print("  VIOLE C [cycle %d] gate_cut=%s port=%s"
                  % (r["cycle"], r["port_gate_cut"], r["port"]))
            bad += 1
    nat_ok = [r for r in rows if r["native"]]
    if not nat_ok:
        print("  NOTE : le natif n'a propose 1095 sur AUCUN cycle -- l'attaque normale (custom "
              "+1, cible a 1 hex) rafle l'argmax. Le bras garde alors la bascule du PORT et le "
              "refus natif SOUS le seuil ; il ne prouve pas le cast natif AU-DESSUS.")
    return {"bad": bad, "rows": rows, "native_ever": bool(nat_ok)}


# ======================================= etape 7 : la clause BOSS du soin generique (`18 Heal`)

A18 = 18
NORMAL_BOSS_ATTACK = 1030          # `ActiveAbilityType.Loki_NormalBossAttack`

# `IdunBattle.AI.Playbook.Common.HealPlaybook$$ShouldExecute` :
#
#     if (!(attackHealUtility > Fix64(0))) return false;
#     if (!UnitExtensions.IsBoss(caster))  return true;
#     return caster != target;                      // un BOSS ne se soigne pas LUI-MEME
#
# Le port emploie un PROXY : le trait `Boss` (`UnitTrait` 0x7e7 = 2023), parce que le natif ne lit
# PAS un trait -- `UnitExtensions$$IsBoss` resout un composant et rend l'octet `<composant>+0x88`,
# qu'AUCUN canal ne publie. **CE BRAS EXISTE POUR MESURER SI LE PROXY TIENT**, et son resultat est
# informatif dans les deux sens :
#
#   * le TEMOIN DE LECTURE est l'attaque normale : `UnitFactory$$AddNormalAttackAbility` fait
#     `else if (config.Traits.Contains(0x7e7)) type = 0x406;` -- si le trait greffe est LU, le natif
#     publie `1030 Loki_NormalBossAttack` a la place de `69`. C'est le seul canal qui separe
#     « le trait n'a pas ete pose » de « le trait est pose mais `IsBoss` lit ailleurs » ;
#   * si le natif AUTORISE malgre tout le self-heal alors que le trait est lu, le proxy est FAUX
#     sur cet axe, et c'est un resultat -- pas un echec du port a masquer.
#
# Le caster est SEUL de son camp et BLESSE : le self-heal est alors le seul soin possible, donc
# l'absence d'`ActiveAbilityMessage(18)` sur lui-meme n'a qu'une cause.
HEALER_CASTER = "ultraTigurius"        # `Hero` + `Psyker` au kit ; la greffe `Healer` -> 18 est la
                                       # voie ETABLIE par #1015-r1 (aucune config d'ability requise)
HEAL_TRAITS = '["Hero","Psyker","Healer"]'
HEAL_TRAITS_BOSS = '["Hero","Psyker","Healer","Boss"]'
HEALER_HP, HEALER_HP_LEFT = 20000, 200


def _native_msgs(rid: int, uid: int) -> list:
    dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, 300)
    for u in (dry.get("units") or ()):
        if u.get("unitId") == uid:
            return [{"cls": m.get("cls"), "ab": m.get("abilityType"),
                     "target": m.get("targetId")} for m in (u.get("proposed") or ())]
    return []


def etape7_live_boss(logs: str, verbose: bool = True) -> dict:
    from engine.playbook.common import HEAL_PLAYBOOK
    from engine.playbook.prediction._shared import _entity_traits
    rows, bad = [], 0
    for tag, traits in (("nonboss", HEAL_TRAITS), ("boss", HEAL_TRAITS_BOSS)):
        sf = os.path.join(logs, "tr14r5r2r1r1r1r3r1_boss_%s.json" % tag)
        rid = _build(sf, ["--seed", "4242",
                          "--p-units", HEALER_CASTER, "--a-units", FOE,
                          "--unit-stat", "%s:Traits=%s" % (HEALER_CASTER, traits),
                          "--unit-stat", "%s:Health=%d,RemainingHealth=%d"
                          % (HEALER_CASTER, HEALER_HP, HEALER_HP_LEFT)])
        try:
            dv = _dv(rid)
            ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
            cid = ids.get(HEALER_CASTER)
            if cid is None:
                raise MontageError("montage BOSS/%s : caster absent (units=%s)" % (tag, sorted(ids)))
            row_u = next(u for u in (dv.get("units") or ()) if u.get("id") == cid)
            abs_ = [(a.get("id"), a.get("kind")) for a in (row_u.get("abilities") or ())]
            normal_ids = [i for i, k in abs_ if k == "normal"]
            _dv2, ctx = _ctx(rid, cid)
            sc = ctx.scene
            traits_mes = sorted(_entity_traits(sc, cid))
            hp, hpmax = sc.hp(cid), sc.hpmax(cid)
            port_self = HEAL_PLAYBOOK.should_execute(ctx, None, cid, A18, 30.0)
            port_other = HEAL_PLAYBOOK.should_execute(ctx, None, cid + 10_000, A18, 30.0)
            msgs = _native_msgs(rid, cid)
            nat_self = any(m["cls"] == "ActiveAbilityMessage" and m["ab"] == A18
                           and m["target"] == cid for m in msgs)
            rows.append({"arm": tag, "abilities": abs_, "normal_ids": normal_ids,
                         "boss_normal": NORMAL_BOSS_ATTACK in normal_ids,
                         "traits": traits_mes, "has_18": A18 in [i for i, _k in abs_],
                         "hp": hp, "hpmax": hpmax,
                         "port_self": port_self, "port_other": port_other,
                         "native_self_heal": nat_self, "msgs": msgs})
        finally:
            _dispose(rid)
    if verbose:
        print("[etape 7] clause BOSS du soin generique (18) -- caster %s, board %s"
              % (HEALER_CASTER, BOARD))
        for r in rows:
            print("  [%-7s] traits=%s" % (r["arm"], r["traits"]))
            print("            a18=%-5s normalIds=%-10s attaqueNormaleBOSS=%-5s hp=%s/%s"
                  % (r["has_18"], r["normal_ids"], r["boss_normal"], r["hp"], r["hpmax"]))
            print("            port(self)=%-5s port(autre)=%-5s natif(selfHeal)=%-5s msgs=%s"
                  % (r["port_self"], r["port_other"], r["native_self_heal"], r["msgs"]))
    by = {r["arm"]: r for r in rows}
    for r in rows:
        if not r["has_18"]:
            print("  BAD MONTAGE [%s] la greffe `Healer` n'a pas donne 18" % r["arm"])
            bad += 1
            continue
        if r["hp"] is None or r["hpmax"] is None or r["hp"] >= r["hpmax"]:
            print("  BAD MONTAGE [%s] caster NON BLESSE (%s/%s) : le soin n'a aucune utilite"
                  % (r["arm"], r["hp"], r["hpmax"]))
            bad += 1
            continue
        # Le port doit TOUJOURS accepter le soin d'un TIERS -- la clause ne porte que sur le self.
        if r["port_other"] is not True:
            print("  VIOLE [%s] le port refuse le soin d'un TIERS (port_other=%s)"
                  % (r["arm"], r["port_other"]))
            bad += 1
    if {"boss", "nonboss"} <= set(by):
        # TEMOIN DE LECTURE : le trait greffe DOIT avoir bascule l'attaque normale sur 1030.
        if by["boss"]["boss_normal"] is not True or by["nonboss"]["boss_normal"] is not False:
            print("  BAD MONTAGE : le trait `Boss` n'a pas ete LU par le natif "
                  "(attaque normale boss : boss=%s nonboss=%s) -- le bras ne mesure pas `IsBoss`"
                  % (by["boss"]["boss_normal"], by["nonboss"]["boss_normal"]))
            bad += 1
        else:
            # ⚠ **CE QUE CE BRAS A ETABLI** : le natif SELF-HEAL sur les DEUX bras, alors que le
            # trait `Boss` a bel et bien ete LU (l'attaque normale bascule sur `1030`). Donc
            # `UnitExtensions$$IsBoss` NE LIT PAS ce trait, et le proxy de la tranche precedente
            # faisait REFUSER au port un cast que le natif emet -- degradation RESTRICTIVE.
            # Le port rend desormais `_is_boss = None` (PAS MESURE) et degrade la clause en VRAI :
            # l'accord doit donc etre PLEIN sur les deux bras.
            if not by["boss"]["native_self_heal"] or not by["nonboss"]["native_self_heal"]:
                print("  TEMOIN ABSENT : le natif ne self-heal pas (boss=%s nonboss=%s) -- "
                      "le bras ne mesure alors rien sur `IsBoss` ; msgs=%s / %s"
                      % (by["boss"]["native_self_heal"], by["nonboss"]["native_self_heal"],
                         by["boss"]["msgs"], by["nonboss"]["msgs"]))
                bad += 1
            for r in rows:
                if bool(r["port_self"]) != bool(r["native_self_heal"]):
                    print("  VIOLE ACCORD [%s] port(self)=%s natif(selfHeal)=%s -- le trait `Boss` "
                          "N'EST PAS le substrat de `UnitExtensions$$IsBoss`, un port qui s'en sert "
                          "prononce un refus que le natif ne prononce pas"
                          % (r["arm"], r["port_self"], r["native_self_heal"]))
                    bad += 1
            # Et le SUBSTRAT lui-meme est garde : `_is_boss` doit rester TRI-ETAT `None`. Un
            # `True`/`False` y reintroduirait le refus infonde.
            from engine.playbook.common import HealPlaybook as _HP
            if _HP._is_boss(None, 1) is not None:
                print("  VIOLE SUBSTRAT : `HealPlaybook._is_boss` ne rend plus `None` (PAS MESURE) "
                      "-- cf. la mesure de ce bras")
                bad += 1
    return {"bad": bad, "rows": rows}


# ====================================================================== main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="joue aussi les etapes LIVE")
    ap.add_argument("--state-file", default=None, help="prefixe ABSOLU des state-files (--live)")
    ap.add_argument("--only", default=None, help="n'executer que ces etapes (ex. '1,2' ou '3')")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    only = None if not args.only else {s.strip() for s in args.only.split(",")}

    def run(tag):
        return only is None or tag in only

    out, total = {}, 0
    if run("1"):
        out["etape1"] = etape1_slots()
        total += out["etape1"]["bad"]
        print("")
    if run("2"):
        out["etape2"] = etape2_reachability()
        total += out["etape2"]["bad"]
        print("")
    if args.live and run("2b"):
        out["etape2b"] = etape2b_reachability_live()
        total += out["etape2b"]["bad"]
        print("")
    live_etapes = (("3", etape3_live_1147), ("4", etape4_live_1014),
                   ("5", etape5_live_1010), ("6", etape6_live_1095),
                   ("7", etape7_live_boss))
    if args.live and any(run(t) for t, _f in live_etapes):
        if not args.state_file:
            print("--live exige --state-file (chemin ABSOLU)")
            return 2
        logs = os.path.dirname(os.path.abspath(args.state_file))
        os.makedirs(logs, exist_ok=True)
        for tag, fn in live_etapes:
            if not run(tag):
                continue
            out["etape%s" % tag] = fn(logs)
            total += out["etape%s" % tag]["bad"]
            print("")
    print("VERDICT: %s (%s)"
          % ("PASS" if total == 0 else "FAIL",
             ", ".join("%s=%d BAD" % (k, v["bad"]) for k, v in out.items())))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
