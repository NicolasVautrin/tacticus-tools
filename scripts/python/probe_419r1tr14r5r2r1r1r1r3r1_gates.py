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


def _deploy_at(sf: str, rid: int, caster_uid: int, anchor_uid: int, want: int) -> dict:
    """Place le caster a `want` hex de l'ancre PENDANT LE DEPLOIEMENT, puis solde le tour.

    Le placement est SEQUENTIEL (une unite a la main a la fois) et le deploiement du premier tour
    ignore `Movement` pour l'unite en cours de placement -- ce sont les deux faits mesures par le
    montage jumeau (`probe_..._r2::_deploy`)."""
    import hexgeo
    for _ in range(6):
        dv = _dv(rid)
        by = {u.get("id"): u for u in (dv.get("units") or ())}
        ap = _pos(by.get(anchor_uid))
        if ap is None:
            break
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
        tiles = [(t.get("col"), t.get("row")) for t in ((mbu.get(caster_uid) or {}).get("tiles") or ())]
        tiles = [t for t in tiles if t[0] is not None]
        if not tiles:
            break
        best = min(tiles, key=lambda t: abs(hexgeo.distance(t, ap) - want))
        rc, _o = _duel("act", "move", "--state-file", sf, "--unit", str(caster_uid),
                       "--to", "%d,%d" % best)
        if rc == 0:
            break
    _end_turn(sf, rid)
    dv = _dv(rid)
    by = {u.get("id"): u for u in (dv.get("units") or ())}
    here, ap = _pos(by.get(caster_uid)), _pos(by.get(anchor_uid))
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
    return {"dist": (None if (here is None or ap is None) else hexgeo.distance(here, ap)),
            "frozen": (here is not None and _movement_reach(mbu, caster_uid, here) == 0),
            "here": here}


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
    if args.live and (run("3") or run("4")):
        if not args.state_file:
            print("--live exige --state-file (chemin ABSOLU)")
            return 2
        logs = os.path.dirname(os.path.abspath(args.state_file))
        os.makedirs(logs, exist_ok=True)
        if run("3"):
            out["etape3"] = etape3_live_1147(logs)
            total += out["etape3"]["bad"]
            print("")
        if run("4"):
            out["etape4"] = etape4_live_1014(logs)
            total += out["etape4"]["bad"]
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
