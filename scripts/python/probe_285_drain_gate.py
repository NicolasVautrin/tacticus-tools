"""#285 -- Le mode DRAIN refuse la CREATION de runner, et le refus ARRIVE JUSQU'A L'AGENT.

Ce probe mesure les DEUX moities de l'exigence, parce qu'un gate qui bloque sans que
personne ne lise pourquoi est pire que pas de gate du tout :

  A. LE GATE BLOQUE     -- `initAndStart` (et les 4 autres methodes creatrices) sont
                           refusees pendant le drain, et re-autorisees a la levee.
  B. LE MESSAGE REMONTE -- le texte du refus est retrouve, VERBATIM, au bout de la
                           chaine, la ou un agent le lit vraiment : la sortie de
                           `rl_duel.py build`.

Et la contrainte qui borne tout le dispositif :

  C. LES RUNNERS EN PLACE RESTENT PILOTES -- `battleStatus`, `decisionView`,
     `observeBattle` et `disposeRunner` passent PENDANT le drain. Le drain suspend la
     CREATION, il ne gele pas le harnais. `disposeRunner` en particulier DOIT passer :
     c'est la dispose des agents qui fait tomber le compte a zero, donc sans elle le
     drain ne convergerait jamais et n'ouvrirait aucune fenetre.

POURQUOI CE PROBE EXISTE (la panne qu'il previent, deja vecue -- #263).
`applyAction` rendait `ok:false` SANS message : deux agents y ont perdu des mesures
independamment, chacun croyant a un bug de son montage. Un refus muet ne se debug pas,
il se subit. La chaine du message a SIX maillons, et chacun peut l'avaler en silence :

    frida/host/drain.ts   DRAIN_MARKER + DrainRefusedError
      -> router.ts        sendRpcError -> 503 + { error: <message> }
      -> _http            parse le corps de la HTTPError et le REND (ne leve PAS)
      -> _rpc             rend le dict tel quel
      -> rl_duel.cmd_build lit `init_resp["error"]` et l'imprime sur stderr
      -> tests/conftest.py retrouve la sous-chaine -> ATTEND, puis ECHOUE ROUGE

Le maillon le plus fragile n'est pas le code, c'est la CONSTANTE PARTAGEE : `DRAIN_MARKER`
cote TypeScript et `_DRAIN_MARKER` cote conftest sont deux litteraux qu'aucun compilateur
ne relie. Les desynchroniser ne casse rien de visible -- ca rend juste au skip vert, en
silence. C'est exactement ce que l'etape B verrouille.

COUVERTURE DE L'ATTENTE, MESUREE le 2026-07-30 (et non estimee).
`rl_collect_batch._rpc` porte l'attente ; qui en herite, par construction :

    [A]   9  appellent `_rpc` PARTAGE directement (dont `R._rpc` / `host._rpc`)
    [B] 315  lancent `rl_duel.py build` en SOUS-PROCESSUS -- le sous-processus
             bloque sur SON `_rpc`, donc l'attente remonte sans une ligne de code
    [C]   4  NON couverts : `diag_normalize`, `diag_state_degradation`,
             `diag_summoner_crash` (chacun redefinit son `_rpc` local) et
             `diag_init_err` (urllib brut -- VOULU : son role est de capturer le
             corps HTTP tel quel).
    -> 331 / 334 consommateurs.

Les 4 exclus VOIENT quand meme le refus (ils impriment la reponse), ils ne font
que ne pas attendre. Ce sont des outils de diagnostic lances a la main, pas le
harnais des agents -- echouer vite y est meme preferable. A noter au passage :
`diag_normalize.py` lit `.get('err')` la ou le host rend `error`, un avalage
PRE-EXISTANT sans rapport avec le drain.

USAGE
    python scripts/python/probe_285_drain_gate.py

PREREQUIS : host lance, session Frida vivante et WARM. Le probe construit son propre
runner temoin et le dispose en sortie, y compris sur echec (le `finally` leve le drain
AVANT de disposer -- sinon un drain laisse arme apres un plantage bloquerait tous les
agents suivants sans que personne ne sache pourquoi).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc, HOST  # noqa: E402

# Doit rester EGAL a `DRAIN_MARKER` (frida/host/drain.ts) et `_DRAIN_MARKER`
# (scripts/python/tests/conftest.py). C'est le contrat inter-langages du dispositif.
DRAIN_MARKER = "runner creation paused"

# Les 5 methodes refusees, cf. l'en-tete de frida/host/drain.ts. Re-derivation :
#   grep -n "registerRunner(" frida/hooks   puis remonter au `ctx.rpc.<nom>`.
EXPECTED_CREATION_METHODS = {
    "buildPatchedRunner", "initAndStart", "initRunner",
    "loadFromSavedBundle", "simBuildPreview",
}

_failures: list[str] = []
_checks = 0


def check(label: str, ok: bool, detail: str = "") -> bool:
    global _checks
    _checks += 1
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        _failures.append(f"{label} -- {detail}")
    return ok


def http(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict, dict]:
    """Appel HTTP RENDANT le code et les en-tetes -- `_http` de rl_collect_batch les
    ecrase (il ne rend que le corps). Or le 503 et `Retry-After` FONT PARTIE du
    contrat : ils disent « temporaire, reessaie » la ou un 500 dirait « casse »."""
    url = HOST + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else {}), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"_raw": raw[:400]}
        return e.code, parsed, dict(e.headers)


def set_drain(enabled: bool, **kw) -> dict:
    code, body, _ = http("/api/admin/drain", "POST", {"enabled": enabled, **kw})
    if code != 200:
        raise RuntimeError(f"POST /api/admin/drain -> HTTP {code}: {json.dumps(body)[:300]}")
    return body


def build_via_rl_duel(state: Path, wait: bool = True) -> tuple[bool, str]:
    """LA voie que prennent les agents. On mesure ce qu'ILS voient, pas ce que le
    host croit avoir envoye -- c'est toute la difference entre « le gate marche »
    et « le gate est utilisable ».

    `wait=False` pose `TACTICUS_DRAIN_WAIT_S=0`, ce qui DESARME l'attente que
    `rl_collect_batch._rpc` applique desormais a tout refus de drain. Sans ce
    levier, mesurer le refus couterait les 300 s d'attente nominale -- on veut ici
    LIRE le message, pas eprouver la patience. C'est aussi la demonstration que
    l'attente est pilotable par variable d'environnement, donc desactivable par un
    agent qui prefere echouer vite."""
    state.unlink(missing_ok=True)
    env = dict(__import__("os").environ)
    if not wait:
        env["TACTICUS_DRAIN_WAIT_S"] = "0"
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337",
         "--board", "MC1_67", "--state-file", str(state)],
        cwd=str(PYDIR), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env)
    return state.exists(), (p.stderr or "") + (p.stdout or "")


def main() -> int:
    sid = _resolve_session()
    state = Path(tempfile.gettempdir()) / f"probe285_{__import__('os').getpid()}.json"
    rid = None
    print(f"[285] session={sid}")

    try:
        # -- 0. Etat initial : drain leve, et la liste des methodes est bien celle
        #       derivee du code (une divergence ici = gate qui fuit ou qui mord trop).
        print("\n[0] etat initial")
        code, st, _ = http("/api/admin/drain")
        check("GET /api/admin/drain repond 200", code == 200, f"HTTP {code}")
        check("drain initialement leve", st.get("enabled") is False,
              f"enabled={st.get('enabled')}")
        got = set(st.get("creationMethods") or [])
        check("liste des methodes creatrices conforme au code",
              got == EXPECTED_CREATION_METHODS,
              f"attendu={sorted(EXPECTED_CREATION_METHODS)} obtenu={sorted(got)}")

        # -- 1. Reference AVANT drain : un build passe. Sans ce temoin, un refus
        #       observe en 2. pourrait venir d'un harnais deja casse.
        print("\n[1] reference : build AVANT drain")
        built, out = build_via_rl_duel(state)
        if not check("build reussi hors drain", built, out[-200:]):
            return 1
        rid = json.loads(state.read_text())["runnerId"]
        print(f"      runner temoin = {rid}")

        # -- 2. Drain arme : la CREATION est refusee, avec le bon code et le bon texte.
        print("\n[2] drain ARME : la creation est refusee")
        set_drain(True, retryAfterSec=60, resetCounters=True)

        code, body, headers = http(
            f"/api/scripts/{sid}/rpc", "POST",
            {"method": "initAndStart", "args": [{"configJson": "{}"}], "timeout": 20000})
        err = str(body.get("error") or "")
        check("initAndStart -> HTTP 503 (temporaire, pas 500)", code == 503, f"HTTP {code}")
        check("en-tete Retry-After present", "Retry-After" in headers,
              f"headers={sorted(headers)}")
        check("le corps porte le marqueur", DRAIN_MARKER in err, f"error={err[:160]}")
        check("le message est ASCII (cp1252-safe)", err.isascii(),
              "un non-ASCII ferait crasher le print du lecteur")
        print(f"      message : {err[:150]}")

        # -- 3. LA MESURE QUI COMPTE : ce que voit un agent au bout de la chaine.
        print("\n[3] le refus arrive-t-il jusqu'a l'agent ?")
        built, out = build_via_rl_duel(state, wait=False)
        check("rl_duel build ne cree PAS de runner", not built,
              "un state-file ecrit pendant le drain = gate contourne")
        check("le marqueur est dans la sortie de rl_duel", DRAIN_MARKER in out,
              f"sortie={out[-200:]}")

        # -- 3bis. L'ATTENTE elle-meme, cote client : `_rpc` doit ANNONCER qu'il
        #    patiente. Une attente muette se lit comme un harnais fige -- c'est le
        #    meme defaut que le refus muet, deplace d'un cran.
        print("\n[3bis] l'attente est-elle annoncee ?")
        env = dict(__import__("os").environ)
        env["TACTICUS_DRAIN_WAIT_S"] = "2"
        env["TACTICUS_DRAIN_POLL_S"] = "1"
        p = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from rl_collect_batch import _resolve_session, _rpc; "
             "r = _rpc(_resolve_session(), 'initAndStart', "
             "[{'configJson': '{}'}], timeout=10); "
             "print('ERR:' + str(r.get('error'))[:80])"],
            cwd=str(PYDIR), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env)
        combined = (p.stderr or "") + (p.stdout or "")
        check("_rpc annonce l'attente sur stderr", "[drain]" in (p.stderr or ""),
              f"stderr={(p.stderr or '')[-200:]}")
        check("_rpc rend quand meme l'erreur a l'appelant", DRAIN_MARKER in combined,
              "l'attente doit DIFFERER le refus, jamais le masquer")

        # -- 4. La contrainte : les runners EN PLACE restent pilotables et observables.
        print("\n[4] les runners en place restent pilotes")
        for method, args in (("battleStatus", [{"runnerId": rid}]),
                             ("decisionView", [{"runnerId": rid}]),
                             ("observeBattle", [{"runnerId": rid}]),
                             ("listRunners", [])):
            r = _rpc(sid, method, args, timeout=60)
            check(f"{method} passe pendant le drain", "error" not in r,
                  str(r.get("error"))[:160])

        # -- 5. Le compteur de refus : l'instrument qui distingue « aucun agent n'a
        #       essaye » de « le gate a ete contourne ». Sans lui, les deux se lisent
        #       pareil -- un calme plat.
        print("\n[5] instrumentation")
        _, st, _ = http("/api/admin/drain")
        n = st.get("refusedTotal") or 0
        check("les refus sont comptes", n >= 2, f"refusedTotal={n} (attendu >= 2)")
        check("le refus est impute a initAndStart",
              (st.get("refusedByMethod") or {}).get("initAndStart", 0) >= 2,
              json.dumps(st.get("refusedByMethod")))

        # -- 6. Le drain CONVERGE : dispose passe, donc le compte peut tomber a zero.
        print("\n[6] convergence : disposeRunner passe pendant le drain")
        r = _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        if check("disposeRunner passe pendant le drain", "error" not in r,
                 str(r.get("error"))[:160]):
            rid = None

        # La JAUGE de convergence doit dire la VERITE, sinon le drain n'ouvre
        # aucune fenetre : on attendrait un zero qui n'arrive jamais. Mesure du
        # 2026-07-30 : juste apres cette dispose, le registre HOST annoncait 2
        # quand celui des hooks etait vide -- d'ou la lecture cote hooks.
        _, st, _ = http("/api/admin/drain")
        hooks = _rpc(sid, "listRunners", [], timeout=15).get("result")
        n_hooks = len(hooks) if isinstance(hooks, list) else None
        check("liveRunners est MESURE (pas null par defaut)",
              st.get("liveRunners") is not None,
              f"liveRunnersError={st.get('liveRunnersError')}")
        check("liveRunners lit le registre des HOOKS",
              st.get("liveRunners") == n_hooks and st.get("liveRunnersSource") == "hooks",
              f"drain={st.get('liveRunners')} hooks={n_hooks} "
              f"source={st.get('liveRunnersSource')}")
        print(f"      jauge={st.get('liveRunners')} (hooks) "
              f"| cache host={st.get('hostRegistryRunners')} <- derive attendue")

        # -- 7. Levee : le harnais redevient normal. Un drain qui ne se leve pas
        #       proprement serait un piege pose pour tous les agents suivants.
        print("\n[7] levee du drain")
        st = set_drain(False)
        check("drain leve", st.get("enabled") is False, f"enabled={st.get('enabled')}")
        built, out = build_via_rl_duel(state)
        if check("build a nouveau possible apres la levee", built, out[-200:]):
            rid = json.loads(state.read_text())["runnerId"]

    finally:
        # Ordre IMPERATIF : lever le drain AVANT de disposer. Un drain reste arme
        # apres un plantage bloquerait silencieusement tous les agents suivants,
        # et le symptome (« mes builds echouent ») ne pointerait pas vers ce probe.
        try:
            set_drain(False)
        except Exception as e:
            print(f"[285] ATTENTION : levee du drain KO ({e}) -- "
                  f"lever a la main : POST /api/admin/drain {{'enabled': false}}")
        if rid is not None:
            try:
                _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            except Exception:
                pass
        state.unlink(missing_ok=True)

    print(f"\n[285] {_checks - len(_failures)}/{_checks} verifications OK")
    if _failures:
        print("[285] VERDICT : ECHEC")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("[285] VERDICT : le gate bloque la creation, le message arrive a l'agent, "
          "et les runners en place restent pilotes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
