#!/usr/bin/env python3
"""#480 -- MESURE de la surface de capteurs `frida/hooks/` : role, atteignabilite, tri-etat.

POURQUOI
--------
Le flux de replay natif (`Replay$$GetWholeBattleOutputStream`) est deterministe au caractere
pres (#477-r11) : il devient un canal de conformite COMBAT/ETAT unique et auto-descriptif.
La question qui en decoule n'est pas « ce hook marche-t-il » mais « ce hook est-il encore
NECESSAIRE, et si oui QUELLE omission du flux le rend necessaire ».

Ce probe MESURE (il ne GARDE pas, sauf sur deux cliquets explicites, cf. plus bas) :

  1. PERIMETRE      -- fichiers/lignes, y compris `hooks/probes/` qui est VERSIONNE depuis
                       #365 et ENTREE DE BUILD (67 imports statiques depuis `controller.ts`).
                       L'ecarter du decompte, comme le font encore plusieurs case-docs en
                       le disant « gitignore », rend un perimetre FAUX.
  2. ROLES          -- ventilation par table ECRITE (jamais un critere par nom : sur ce depot
                       l'appariement par sous-chaine a deja produit 6 verdicts faux sur 8,
                       cf. case-477r11 5a). Un module non classe fait ROUGIR : il force une
                       decision au lieu de glisser dans un lot par defaut.
  3. ENREGISTREMENT -- qui est effectivement branche dans `controller.ts`.
  4. APPELANTS      -- RPC declares sans aucune mention hors `frida/hooks/`. NB : « sans
                       appelant » n'est PAS « mort » (beaucoup sont des sondes one-shot
                       appelees a la main) -- c'est un axe de tri, pas un verdict.
  5. TRI-ETAT LIVE  -- le gisement le plus rentable : un capteur qui rend un conteneur VIDE
                       sans distinguer « mesure et vide » de « pas mesurable ». Sonde
                       NON DESTRUCTIVE (allowlist de lecteurs purs, `runnerId` inexistant).

TRI-ETAT DU PROBE LUI-MEME : si le host n'est pas joignable, l'etape 5 dit « PAS MESURE ».
Elle ne rend JAMAIS un zero rassurant -- c'est exactement le defaut qu'elle traque.

Ce qu'il NE refait PAS, deleguant a l'outil dedie (ne pas dupliquer un cliquet) :
  - adresses epinglees      -> `probe_475_pinned_addresses.py`
  - tables de noms figees   -> `probe_252_hook_name_tables.py`

Sortie 0 = rien a signaler ; 1 = au moins un cliquet rouge.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "frida" / "hooks"

# --------------------------------------------------------------------------------------
# TABLE DES ROLES -- ECRITE, jamais derivee d'un critere par nom.
#
# Cinq roles, et la ventilation est ce qui rend l'audit exploitable :
#   ETAT    : projette l'etat ECS d'une bataille (le seul role que le flux concurrence)
#   DECISION: playbook / utilite / prediction -- ABSENT du flux par construction
#   MONTAGE : construit ou pilote un runner / une BattleConfiguration
#   INFRA   : plomberie IL2CPP, pump, diagnostic de process, rendu
#   SONDE   : exploration one-shot (dump de champs/methodes), sans consommateur permanent
# --------------------------------------------------------------------------------------
ROLES = {
    # --- ETAT ---
    "features/observe.ts": "ETAT",
    "features/ai-step/rpc-snapshot.ts": "ETAT",
    "features/ai-step/rpc-board.ts": "ETAT",
    "features/replay-output-stream.ts": "ETAT",
    "features/winner-capture.ts": "ETAT",
    "features/effect-immunity-observe.ts": "ETAT",
    "features/modifier-observe.ts": "ETAT",
    "features/unit-visual-resolve.ts": "ETAT",
    "features/unit-asset-map.ts": "ETAT",
    "features/move-options.ts": "ETAT",
    # --- DECISION ---
    "features/ai-step/index.ts": "DECISION",
    "features/ai-step/rpc-predict.ts": "DECISION",
    "features/ai-step/rpc-targeting.ts": "DECISION",
    "features/ai-step/rpc-drive.ts": "DECISION",
    "features/ai-step/playbook-predict.ts": "DECISION",
    "features/ai-step/projection.ts": "DECISION",
    "features/ai-step/movable-tiles-probe.ts": "DECISION",
    "features/ai-step/triggered-predict.ts": "DECISION",
    "features/ai-step/rpc-nc-predict.ts": "DECISION",
    "features/ai-step/internals.ts": "DECISION",
    "features/ai-trace.ts": "DECISION",
    "features/ai-utility-trace.ts": "DECISION",
    "features/bucket-audit.ts": "DECISION",
    "features/dump-composed.ts": "DECISION",
    "features/ability-prefs.ts": "DECISION",
    "features/scorer-damage-trace.ts": "DECISION",
    "features/whatif-trigger.ts": "DECISION",
    "features/compare.ts": "DECISION",
    "features/movement-trace.ts": "DECISION",
    # --- MONTAGE ---
    "features/launch.ts": "MONTAGE",
    "features/battle-config.ts": "MONTAGE",
    "features/campaign-builder.ts": "MONTAGE",
    "features/mow-builder.ts": "MONTAGE",
    "features/normalize-bc.ts": "MONTAGE",
    "features/sim.ts": "MONTAGE",
    "features/sim-engine.ts": "MONTAGE",
    "features/cheat.ts": "MONTAGE",
    "features/mode-source-capture.ts": "MONTAGE",
    "features/config-io.ts": "MONTAGE",
    "features/rl/bridge.ts": "MONTAGE",
    "features/dump-boards.ts": "MONTAGE",
    "features/dump-pvp-boards.ts": "MONTAGE",
    "features/overwatch-fix/index.ts": "MONTAGE",
    # --- INFRA ---
    "features/status.ts": "INFRA",
    "features/amorce-singletons.ts": "INFRA",
    "features/auto-boot.ts": "INFRA",
    "features/ui-nav.ts": "INFRA",
    "features/crash-trap.ts": "INFRA",
    "features/init-trace.ts": "INFRA",
    "features/gc-probe.ts": "INFRA",
    "features/render-budget.ts": "INFRA",
    "features/introspect.ts": "INFRA",
    "features/message-trace.ts": "INFRA",
    "features/dispatch-observe.ts": "INFRA",
    "features/board-trace.ts": "INFRA",
    # --- TRACES DE MECANIQUE (capteurs on-demand sur chemin chaud) ---
    "features/hit-trace.ts": "ETAT",
    "features/effect-bonus-trace.ts": "ETAT",
    "features/triggered-move-trace.ts": "ETAT",
    "features/trigger-trace.ts": "ETAT",
    "features/dsl-trace.ts": "DECISION",
    "features/dsl-ctor-trace.ts": "DECISION",
    # --- SONDE (hooks/probes : introspection one-shot, versionnee depuis #365, renommee #480-r6) ---
    "probes/dump-idun-nav-info.ts": "SONDE",
    "probes/dump-navigation-methods.ts": "SONDE",
    "probes/inspect-cgms.ts": "SONDE",
    "probes/try-to-campaign.ts": "SONDE",
    "probes/test-unity-find.ts": "SONDE",
    "probes/test-scene.ts": "SONDE",
}

# Capteurs LECTEURS PURS : sondables avec un runnerId inexistant sans aucun effet de bord.
# Allowlist ECRITE -- on ne balaie JAMAIS les 300+ RPC en aveugle (`renderBudget` a deja
# tue le process par `SetResolution`, cf. controller.ts).
LECTEURS_PURS = [
    "observeBattle", "combatSnapshot", "tileMeta", "boardGraph", "decisionView",
    "unitAbilityStates", "dumpRng", "replayOutputStream", "abilityTargets",
]

# RPC ECRITS mais dont le deploiement est en attente d'une fenetre de reinject (#477-r12).
# Sondes pour MESURER l'ecart source/session, pas pour les utiliser.
ATTENDUS_NON_DEPLOYES = ["replaySteps", "replayRngEvents"]

RPC_DECL = re.compile(r"ctx\.rpc\.([A-Za-z0-9_]+)\s*=")
MOT = "(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"


def fichiers_ts() -> list[Path]:
    return sorted(p for p in HOOKS.rglob("*.ts") if p.is_file())


def rel(p: Path) -> str:
    return p.relative_to(HOOKS).as_posix()


def lignes(p: Path) -> int:
    return len(p.read_text(encoding="utf-8", errors="replace").splitlines())


def http_json(url: str, payload: dict | None, timeout: float):
    """-> (objet, None) | (None, 'cause nommee'). JAMAIS d'exception, JAMAIS de zero."""
    try:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %d" % e.code
    except urllib.error.URLError as e:
        return None, "injoignable (%s)" % (e.reason,)
    except TimeoutError:
        return None, "delai depasse"
    except OSError as e:
        return None, "erreur systeme (%s)" % (e.__class__.__name__,)
    except ValueError:
        return None, "reponse non-JSON"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="http://127.0.0.1:8765")
    ap.add_argument("--session", default=None,
                    help="id de session Frida ; defaut = celui rendu par /api/admin/status")
    ap.add_argument("--no-live", action="store_true",
                    help="saute l'etape 5 (elle dira PAS MESURE)")
    ap.add_argument("--timeout", type=float, default=20.0)
    args = ap.parse_args()

    rouge = False
    tous = fichiers_ts()
    sondes = [p for p in tous if rel(p).startswith("probes/")]
    hors = [p for p in tous if not rel(p).startswith("probes/")]

    print("=== (1) PERIMETRE ===")
    print("fichiers .ts sous frida/hooks/ : %d  (%d lignes)"
          % (len(tous), sum(lignes(p) for p in tous)))
    print("  hors sondes : %-4d (%d lignes)" % (len(hors), sum(lignes(p) for p in hors)))
    print("  sondes       : %-4d (%d lignes)  -- VERSIONNE depuis #365, ENTREE DE BUILD"
          % (len(sondes), sum(lignes(p) for p in sondes)))
    ctrl = (HOOKS / "controller.ts").read_text(encoding="utf-8")
    n_imports = len(re.findall(r'from "\./probes/', ctrl))
    print("  imports statiques `./probes/` depuis controller.ts : %d" % n_imports)
    print("")

    print("=== (2) LES GROS MODULES (seuil doctrine ~1000 lignes) ===")
    gros = sorted(((lignes(p), rel(p)) for p in hors), reverse=True)
    for n, r in gros[:8]:
        marque = "  <-- au-dessus du seuil" if n >= 1000 else ""
        print("  %5d  %s%s" % (n, r, marque))
    print("  NB : la doctrine dit SCINDER QUAND CA PASSE le seuil, pas pre-scinder.")
    print("       La taille seule n'est pas un defaut -- cf. la fiche pour lesquels FONT MAL.")
    print("")

    print("=== (3) ROLES (table ECRITE ; un module non classe fait ROUGIR) ===")
    modules_reg = [rel(p) for p in tous
                   if re.search(r"export function register\s*\(",
                                p.read_text(encoding="utf-8", errors="replace"))]
    par_role: dict[str, int] = {}
    non_classes = []
    for m in modules_reg:
        r = ROLES.get(m)
        if r is None:
            non_classes.append(m)
        else:
            par_role[r] = par_role.get(r, 0) + 1
    for r in sorted(par_role):
        print("  %-9s %d module(s)" % (r, par_role[r]))
    if non_classes:
        rouge = True
        print("  ROUGE : %d module(s) exportant register() SANS role dans la table :"
              % len(non_classes))
        for m in non_classes:
            print("      %s" % m)
    else:
        print("  tous les modules a register() portent un role.")
    print("")

    print("=== (4) ENREGISTREMENT ET APPELANTS ===")
    bloc = re.search(r"\[\s*status,.*?\]\s*\.forEach", ctrl, re.S)
    corps = bloc.group(0) if bloc else ""
    # une entree COMMENTEE (`/* movementTrace, */`) n'est PAS enregistree
    corps_actif = re.sub(r"/\*.*?\*/", "", corps, flags=re.S)
    corps_actif = re.sub(r"//[^\n]*", "", corps_actif)
    non_enregistres = []
    for m in modules_reg:
        # nom d'import tel qu'il apparait dans controller.ts
        base = re.search(r'import \* as ([A-Za-z0-9_]+) from "\./%s"'
                         % re.escape(m.replace(".ts", ".js")), ctrl)
        if not base:
            continue
        ident = base.group(1)
        if not re.search(MOT.format(re.escape(ident)), corps_actif) \
           and not re.search(MOT.format(re.escape(ident)) + r"\.register", ctrl):
            non_enregistres.append((m, ident))
    if non_enregistres:
        for m, ident in non_enregistres:
            print("  IMPORTE MAIS NON ENREGISTRE : %-34s (%s)" % (m, ident))
    else:
        print("  tous les modules importes sont enregistres.")

    declares: dict[str, str] = {}
    for p in tous:
        for mm in RPC_DECL.finditer(p.read_text(encoding="utf-8", errors="replace")):
            declares.setdefault(mm.group(1), rel(p))
    print("  RPC declares : %d" % len(declares))

    corpus = []
    for d in ("scripts", "frida/host", "frida/public", "tests", "docs", "engine"):
        base = REPO / d
        if not base.is_dir():
            continue
        for ext in ("*.py", "*.ts", "*.js", "*.md", "*.html"):
            corpus.extend(base.rglob(ext))
    # O(n), pas O(n * 321) : on extrait UNE FOIS tous les identifiants du corpus dans un
    # ensemble, au lieu de relancer 321 regex sur 44 Mo (mesure : ~15 min -> quelques
    # secondes). Un probe qu'on ne relancera jamais faute de patience ne garde rien.
    IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    vus: set[str] = set()
    for p in corpus:
        if not p.is_file():
            continue
        vus.update(IDENT.findall(p.read_text(encoding="utf-8", errors="replace")))
    orphelins = sorted(n for n in declares if n not in vus)
    print("  RPC sans AUCUNE mention hors frida/hooks/ : %d / %d"
          % (len(orphelins), len(declares)))
    print("    (axe de TRI, pas un verdict : beaucoup sont des sondes appelees a la main)")
    print("")

    print("=== (5) TRI-ETAT LIVE -- un conteneur vide dit-il POURQUOI il est vide ? ===")
    if args.no_live:
        print("  PAS MESURE (--no-live)")
        print("")
        return 1 if rouge else 0

    st, err = http_json(args.host + "/api/admin/status", None, args.timeout)
    sid = args.session
    if sid is None:
        if st is None:
            print("  PAS MESURE -- host %s : %s" % (args.host, err))
            print("  (ce n'est PAS un zero : l'etape ne conclut rien.)")
            print("")
            return 1 if rouge else 0
        sid = ((st.get("session") or {}).get("id"))
    if sid is None:
        print("  PAS MESURE -- aucune session Frida vivante")
        print("")
        return 1 if rouge else 0

    print("  session %s" % sid)
    url = "%s/api/scripts/%s/rpc" % (args.host, sid)
    FAUX = 999999
    for m in LECTEURS_PURS:
        rep, e = http_json(url, {"method": m, "args": [{"runnerId": FAUX}],
                                 "timeout": 15000}, args.timeout)
        if rep is None:
            print("  %-22s NON DEPLOYE ou en erreur (%s)" % (m, e))
            continue
        res = rep.get("result")
        if not isinstance(res, dict):
            print("  %-22s reponse non-objet" % m)
            continue
        a_erreur = bool(res.get("error") or res.get("err"))
        ok = res.get("ok")
        if a_erreur:
            verdict = "ERREUR NOMMEE (bon)"
        elif ok is False:
            verdict = "ok:false mais SANS cause nommee"
        else:
            verdict = "ZERO RASSURANT (ok=%r, aucune cause)" % (ok,)
            rouge = True
        print("  %-22s %s" % (m, verdict))

    print("")
    print("  -- RPC ecrits, deploiement en attente de fenetre (#477-r12) :")
    for m in ATTENDUS_NON_DEPLOYES:
        rep, e = http_json(url, {"method": m, "args": [{"runnerId": FAUX}],
                                 "timeout": 15000}, args.timeout)
        etat = "ABSENT de la session (%s)" % e if rep is None else "PRESENT -- deploye depuis"
        print("     %-20s %s" % (m, etat))

    print("")
    if rouge:
        print("AU MOINS UN CLIQUET ROUGE -- cf. docs/rl/case-480-audit-hooks-frida.md")
        return 1
    print("RIEN A SIGNALER.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
