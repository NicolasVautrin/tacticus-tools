"""#1072 -- les QUATRE capteurs de la fenetre : contrat OFFLINE + interrogation LIVE TRI-ETAT.

    python scripts/python/probe_1072_capteurs_de_la_fenetre.py --source     # 100 % offline
    python scripts/python/probe_1072_capteurs_de_la_fenetre.py              # + volets live
    python scripts/python/probe_1072_capteurs_de_la_fenetre.py --volet 982r6

POURQUOI CE PROBE EXISTE. `#1064` a qualifie les 19 residus `BLOCAGE: capteur` contre le bundle
reellement charge : 15 avaient deja leur canal en vol ou etaient caducs, et QUATRE demandaient un
capteur qui n'existait ni dans le bundle ni dans l'arbre. Ces quatre-la sont ECRITS (#1072) mais
ne seront ARMES qu'a la prochaine fenetre de reinject. Ce probe est ce qui rend cette fenetre
RENTABLE : il dit, canal par canal, si le capteur est EN VOL, et -- quand il l'est -- ce qu'il
mesure, en UNE passe.

LA REGLE QUI FAIT TOUT : UN CANAL ABSENT REND `null`, JAMAIS UN ZERO.
Chaque volet distingue trois etats, et les melanger ferait prendre une decision sur un neant :

    PAS EN VOL   le champ est ABSENT de la reponse RPC -> le bundle charge precede #1072
    MESURE       le champ est present et porte une valeur (`0` / `false` compris : ce sont des
                 mesures, cf. `Level` = 0 qui veut dire VERROUILLE)
    NON MESURE   le champ est present et vaut `null` -- le capteur a refuse de lire, et il DIT
                 pourquoi (`tertiaryLayout.errors`, `forceInitError`, ...)

CE QU'IL NE MESURE PAS : la face PORT. Ce probe garde le CANAL, pas ce que le moteur Python en
fait. Et il ne peut RIEN mesurer des capteurs tant que la fenetre n'a pas eu lieu -- c'est
exactement ce qu'il doit alors AFFICHER.

Le pendant hors Frida des LOGIQUES (mutations adversariales) est
`frida/tools/probe-1072-capteurs-fenetre.ts`.

Discipline runner : `--state-file` ABSOLU sous `logs/` du checkout, `--board` EXPLICITE, runner
DISPOSE en sortie sauf `--keep`. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

RACINE = _HERE.parents[1]

BOARD = "MC1_67"
SEED = 777
#: La MoW porteuse d'une MYTHIQUE -- le regime meme que #1036-r8 declare non mesurable.
MOW = "necroReanimator"
MYTHIC = "GuardianConstruct"
NIVEAU = 4

#: Classes d'effet FROIDES du corpus de `probe_916r1_effect_slots.py` (namespaces LUS dans
#: `data/symbols/<build>/frida/classes.tsv`, jamais devines). Le volet #982-r6 prend la premiere
#: que le build declare NON INITIALISEE : c'est le seul regime ou `forceInit` se voit.
CLASSES_FROIDES = [
    ("IdunBattle.Entities.Effects.Loki", "AllIsDustEffect"),
    ("IdunBattle.Entities.Effects.Loki", "AnnihilatorBeam_PendingAttackEffect"),
]

#: Contrat de SOURCE : ce que chaque capteur doit porter dans l'arbre. Motifs EXACTS, pour qu'un
#: renommage silencieux rougisse ici plutot qu'a la fenetre.
CONTRAT_SOURCE = {
    "1036-r8": [
        ("frida/hooks/game/tertiary-ability.ts",
         'TERTIARY_ENUM_FULL_NAME = "IdunBattle.Entities.Enum.TriggeredAbilityType"'),
        ("frida/hooks/game/tertiary-ability.ts", 'LEVEL_TYPE_FULL_NAME = "Idun.Shared.Level"'),
        ("frida/hooks/game/tertiary-ability.ts", "export function resolveTertiaryChannel"),
        ("frida/hooks/features/ai-step/rpc-snapshot.ts", "tertiary: readTertiary(e)"),
        ("frida/hooks/features/ai-step/rpc-snapshot.ts", "tertiaryLayout:"),
        ("frida/hooks/features/ai-step/rpc-snapshot.ts", "tertiaryAbilityEnum:"),
        ("frida/hooks/features/ai-step/rpc-snapshot.ts", "function readConfigTertiary"),
    ],
    "969-r4": [
        ("frida/hooks/features/ai-step/internals.ts", "export function invokeBoolOrNull"),
        ("frida/hooks/features/ai-step/rpc-snapshot.ts",
         "currentOwnerIsEnvironment: wants(\"currentOwnerIsEnv\")"),
        ("frida/hooks/features/ai-step/rpc-snapshot.ts",
         "invokeBoolOrNull(currentOwnerIsEnvMi, [e, statePtr])"),
    ],
    "982-r6": [
        ("frida/hooks/il2cpp/class-init.ts", "export function classInitState"),
        ("frida/hooks/il2cpp/helpers.ts", "export const runtime_class_init"),
        ("frida/hooks/features/introspect.ts", "forceInit?: boolean"),
        ("frida/hooks/features/introspect.ts",
         "classInitState(LIVE_CLASS_INIT_PROBE, klass, args.forceInit === true)"),
        ("frida/hooks/probes/static-field-probe.ts",
         "classInitState(LIVE_CLASS_INIT_PROBE, klass, args.forceInit === true)"),
    ],
    "1009-r3": [
        ("frida/hooks/features/dsl-ctor-trace.ts", "export function classTagOf"),
        ("frida/hooks/features/dsl-ctor-trace.ts", "retCls: classTagOf(readMsgIdentity"),
        ("frida/hooks/features/dsl-ctor-trace.ts", "argCls: (this as any)._ac"),
        ("frida/hooks/features/dsl-ctor-trace.ts", "tagging: { calls, namedRet, args"),
    ],
}

ABSENT = object()      # sentinelle : le champ n'existe pas dans la reponse -> capteur PAS EN VOL


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


def _champ(d, nom):
    """Le champ, ou la sentinelle ABSENT. Ne rabat JAMAIS un manque sur `None` : `None` est un
    etat du capteur (il a refuse de lire), l'absence est un etat du BUNDLE."""
    if not isinstance(d, dict) or nom not in d:
        return ABSENT
    return d[nom]


def _dit(nom, v):
    if v is ABSENT:
        return "PAS EN VOL (champ `%s` absent de la reponse)" % nom
    if v is None:
        return "NON MESURE (`%s` = null -- le capteur a refuse de lire)" % nom
    return "MESURE   `%s` = %s" % (nom, json.dumps(v, ensure_ascii=True)[:220])


class _Session:
    """Le couple (session, runner) et les RPC, groupes pour que `finally` puisse toujours
    disposer. Meme forme que les probes #1036."""

    def __init__(self, rid):
        import rl_collect_batch as B                                            # noqa: PLC0415
        self._B = B
        self.sid = B._resolve_session()
        self.rid = None if rid is None else int(rid)

    def rpc(self, method, body=None, timeout=90):
        """RPC avec `runnerId` implicite. `body=None` -> appel SANS enveloppe de runner (pour
        les RPC d'introspection, qui n'en prennent pas)."""
        if body is None:
            args = []
        else:
            b = dict(body)
            if self.rid is not None:
                b.setdefault("runnerId", self.rid)
            args = [b]
        return _unwrap(self._B._rpc(self.sid, method, args, timeout=timeout)) or {}

    def rpc_pos(self, method, args, timeout=60):
        """RPC a arguments POSITIONNELS (`resolveVtableSlot` en prend un objet, `dumpEnum` aussi ;
        mais `classFields` prend deux chaines) -- on passe la liste telle quelle."""
        return _unwrap(self._B._rpc(self.sid, method, args, timeout=timeout)) or {}

    def dispose(self):
        if self.rid is None:
            return
        try:
            self._B._rpc(self.sid, "disposeRunner", [{"runnerId": self.rid}], timeout=20)
        except Exception:                    # un teardown qui leve masquerait le verdict
            pass


def _build(verbose):
    """Monte le runner qui porte la MoW a MYTHIQUE de niveau 4 -- le regime EXACT de #1036-r8."""
    import rl_duel as R                                                         # noqa: PLC0415
    sf = RACINE / "logs" / "probe1072_capteurs.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--p-mow", MOW,
            "--equip-mythic", "%s:%s:%d" % (MOW, MYTHIC, NIVEAU),
            "--state-file", str(sf)]
    if verbose:
        print("[1072] build %s" % " ".join(argv))
    if R.main(argv) != 0:
        raise RuntimeError("build ECHOUE : %s" % " ".join(argv))
    rid = json.loads(sf.read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        raise RuntimeError("build sans runnerId : %s" % sf)
    return _Session(rid)


# --- VOLET 0 : le contrat de SOURCE (100 % offline) ---------------------------------------

def volet_source():
    print("=== VOLET 0 : contrat de SOURCE (offline) ===")
    echecs = 0
    for residu in sorted(CONTRAT_SOURCE):
        manquants = []
        for rel, motif in CONTRAT_SOURCE[residu]:
            p = RACINE / rel
            if not p.exists():
                manquants.append("%s : FICHIER ABSENT" % rel)
                continue
            if motif not in p.read_text(encoding="utf-8"):
                manquants.append("%s : motif absent -> %s" % (rel, motif))
        n = len(CONTRAT_SOURCE[residu])
        print("  #%-8s %d/%d motif(s) presents" % (residu, n - len(manquants), n))
        for m in manquants:
            print("      MANQUE %s" % m)
        echecs += len(manquants)
    print("  => %s" % ("contrat de source COMPLET" if echecs == 0
                       else "%d motif(s) manquant(s)" % echecs))
    print("")
    return echecs


# --- VOLET #1036-r8 : l'ability tertiaire d'une MACHINE OF WAR -----------------------------

def volet_1036r8(s):
    print("=== VOLET #1036-r8 : `combatSnapshot.units[].tertiary` (MoW %s, mythique niveau %d) ==="
          % (MOW, NIVEAU))
    cs = s.rpc("combatSnapshot", {})
    if not cs.get("ok"):
        print("  combatSnapshot KO : %s" % cs.get("error"))
        return 1
    layout = _champ(cs, "tertiaryLayout")
    print("  %s" % _dit("tertiaryLayout", layout))
    print("  %s" % _dit("tertiaryAbilityEnum", _champ(cs, "tertiaryAbilityEnum")))
    print("  %s" % _dit("tertiaryLevelMeasured", _champ(cs, "tertiaryLevelMeasured")))
    print("  %s" % _dit("tertiaryAbilityMeasured", _champ(cs, "tertiaryAbilityMeasured")))
    if layout is ABSENT:
        print("  VERDICT : CAPTEUR PAS EN VOL. Rien n'est conclu du contenu de `units[]` --")
        print("            un `tertiary` absent n'est PAS `aucune ability tertiaire`.")
        print("")
        return 0
    # Le capteur EST en vol : on mesure. La MoW est l'unite dont l'`entityType` vaut Machine (6).
    mows = [u for u in (cs.get("units") or []) if u.get("entityType") == 6]
    print("  %d Machine(s) dans le snapshot" % len(mows))
    echecs = 0
    for u in mows:
        t = _champ(u, "tertiary")
        print("    entity %-5s %s" % (u.get("entityId"), _dit("tertiary", t)))
        if t is ABSENT or t is None:
            print("      -> la jointure entite->configuration n'a rien rendu pour cette Machine")
            echecs += 1
            continue
        niveau = t.get("level")
        if niveau is None:
            print("      -> NON MESURE : `level` = null (le canal a refuse). Regarder"
                  " `tertiaryLayout.errors`.")
            echecs += 1
        elif int(niveau) == NIVEAU:
            print("      -> ATTENDU CONFIRME : level = %d, le niveau ECRIT dans la BC par"
                  " `--equip-mythic`" % NIVEAU)
        elif int(niveau) == 0:
            print("      -> level = 0 = VERROUILLE. C'est une MESURE, pas une panne : cette"
                  " Machine ne porte AUCUNE mythique. Verifier le montage.")
            echecs += 1
        else:
            print("      -> ECART : level = %s, attendu %d" % (niveau, NIVEAU))
            echecs += 1
    # Le TEMOIN : les unites NON-Machine passent par les DEUX voies. Un desaccord se verrait.
    for u in (cs.get("units") or [])[:3]:
        if u.get("entityType") == 6:
            continue
        t = u.get("tertiary")
        uc = u.get("unitConfig") or {}
        if isinstance(t, dict) and isinstance(uc, dict) and "error" not in uc:
            a = t.get("multiplier")
            b = uc.get("tertiaryAbilityVariablesMultiplier")
            print("    temoin entity %-5s multiplicateur : voie #1072 = %s / voie"
                  " `unitConfig` = %s  %s"
                  % (u.get("entityId"), a, b, "OK" if a == b else "DIVERGE"))
            if a != b:
                echecs += 1
    print("")
    return echecs


# --- VOLET #969-r4 : `CurrentOwnerIsEnvironment` par unite ---------------------------------

def volet_969r4(s):
    print("=== VOLET #969-r4 : `combatSnapshot.units[].currentOwnerIsEnvironment` ===")
    cs = s.rpc("combatSnapshot", {})
    if not cs.get("ok"):
        print("  combatSnapshot KO : %s" % cs.get("error"))
        return 1
    units = cs.get("units") or []
    if not units:
        print("  aucune unite dans le snapshot -- rien a mesurer")
        return 1
    presents = [u for u in units if "currentOwnerIsEnvironment" in u]
    if not presents:
        print("  %s" % _dit("currentOwnerIsEnvironment", ABSENT))
        print("  VERDICT : CAPTEUR PAS EN VOL. Ne PAS lire cette absence comme `aucune unite")
        print("            Environment` -- c'est exactement le rabattement que le tri-etat")
        print("            interdit.")
        print("")
        return 0
    vrais = [u for u in presents if u.get("currentOwnerIsEnvironment") is True]
    faux = [u for u in presents if u.get("currentOwnerIsEnvironment") is False]
    nuls = [u for u in presents if u.get("currentOwnerIsEnvironment") is None]
    print("  %d unite(s) : %d True / %d False / %d NON MESURE"
          % (len(presents), len(vrais), len(faux), len(nuls)))
    if nuls:
        print("  %d unite(s) en NON MESURE -- `currentOwnerIsEnvMi` irresolu, ou l'invocation"
              " a leve" % len(nuls))
        print("")
        return 1
    if not vrais:
        print("  PORTEUR MANQUANT (attendu) : aucune unite Environment sur ce montage, donc le")
        print("  canal ne DISCRIMINE rien ici. Le capteur est en vol et repond ; la")
        print("  CONFRONTATION de `GetEligibleTargetsSelectable` reste bloquee par le PORTEUR,")
        print("  exactement comme #1064 l'a etabli. Ce n'est pas un echec de ce probe.")
    else:
        print("  %d unite(s) Environment : le regime SEPARANT existe sur ce montage --"
              " confronter `eligible_targets` du port au natif" % len(vrais))
    print("")
    return 0


# --- VOLET #982-r6 : `forceInit` sur `resolveVtableSlot` -----------------------------------

def volet_982r6(s):
    print("=== VOLET #982-r6 : `resolveVtableSlot({forceInit})` sur une classe FROIDE ===")
    echecs = 0
    for ns, cls in CLASSES_FROIDES:
        avant = s.rpc_pos("resolveVtableSlot",
                          [{"ns": ns, "cls": cls, "start": 0x100, "end": 0x400}])
        if not isinstance(avant, dict) or not avant.get("ok"):
            print("  %s.%s : RPC KO (%s)" % (ns, cls, (avant or {}).get("error")))
            echecs += 1
            continue
        init = _champ(avant, "initializedBefore")
        print("  %s.%s" % (ns, cls))
        print("    %s" % _dit("initializedBefore", init))
        print("    %s" % _dit("nonNullSlots", _champ(avant, "nonNullSlots")))
        if init is ABSENT:
            print("    VERDICT : CAPTEUR PAS EN VOL (le RPC repond, mais sans l'etat")
            print("              d'initialisation ni `forceInit`). Un balayage de vtable sur")
            print("              ce bundle ne peut PAS distinguer `aucun override` de")
            print("              `classe jamais reveillee` -- le trou de #982-r6 est entier.")
            print("")
            return 0
        if init is True:
            print("    classe DEJA chaude -- elle ne peut pas montrer l'effet de `forceInit`,"
                  " on passe a la suivante")
            continue
        # Le seul regime ou le drapeau se voit : froide AVANT, chaude APRES.
        apres = s.rpc_pos("resolveVtableSlot",
                          [{"ns": ns, "cls": cls, "start": 0x100, "end": 0x400,
                            "forceInit": True}])
        print("    apres forceInit : %s" % _dit("forcedInit", _champ(apres, "forcedInit")))
        print("                      %s" % _dit("initialized", _champ(apres, "initialized")))
        print("                      %s" % _dit("nonNullSlots", _champ(apres, "nonNullSlots")))
        err = _champ(apres, "forceInitError")
        if err not in (ABSENT, None):
            print("    FORCAGE EN ECHEC, et il le DIT : %s" % err)
            echecs += 1
            continue
        a = avant.get("nonNullSlots")
        b = apres.get("nonNullSlots")
        if isinstance(a, int) and isinstance(b, int) and b > a:
            print("    ATTENDU CONFIRME : %d -> %d slots nommes. Les 221 classes `NON MESUREE`"
                  " de `probe_916r1_effect_slots.py` deviennent mesurables." % (a, b))
        else:
            print("    ECART : nonNullSlots %s -> %s (aucun gain) -- `forceInit` n'a pas"
                  " reveille la classe" % (a, b))
            echecs += 1
        print("")
        return echecs
    print("    aucune classe FROIDE parmi les candidates : le regime discriminant n'existe pas")
    print("    sur cette session (elles ont toutes ete initialisees). Relancer sur une session")
    print("    fraiche, ou elargir CLASSES_FROIDES depuis les `NON MESUREE` de probe_916r1.")
    print("")
    return echecs


# --- VOLET #1009-r3 : le tag de classe des noeuds DSL --------------------------------------

def volet_1009r3(s, armer):
    print("=== VOLET #1009-r3 : `dslCtorCasts` tague `ret`/`args` ===")
    lu = s.rpc("dslCtorCasts", {})
    tag = _champ(lu, "tagging")
    print("  %s" % _dit("tagging", tag))
    if tag is ABSENT:
        print("  VERDICT : CAPTEUR PAS EN VOL. `dslCtorCasts` repond, mais ses appels ne")
        print("            portent que des POINTEURS : `<A>`, premier conjoint de")
        print("            `DSLTriggers$$IsSpecialActiveAbility`, reste sans nom.")
        print("")
        return 0
    if not armer:
        print("  Le canal EST en vol. Pour le MESURER il faut des casts : relancer avec")
        print("  `--armer` (arme le traceur, joue un tour d'IA, lit, desarme).")
        print("")
        return 0
    import rl_duel as R                                                         # noqa: PLC0415
    sf = RACINE / "logs" / "probe1072_capteurs.json"
    arm = s.rpc("dslCtorArm", {})
    print("  arm -> %s" % json.dumps(arm, ensure_ascii=True)[:200])
    try:
        R.main(["aiturn", "--state-file", str(sf)])
    finally:
        lu = s.rpc("dslCtorCasts", {})
        s.rpc("dslCtorDisarm", {})
    tag = lu.get("tagging") or {}
    print("  casts captures : %s" % lu.get("capturedCasts"))
    print("  tagging : %s" % json.dumps(tag, ensure_ascii=True))
    if not tag.get("calls"):
        print("  AUCUN APPEL capture -- le tour d'IA n'a construit aucun arbre DSL. Rien n'est")
        print("  conclu du tag : relancer sur un montage qui CASTE (cf. le montage nomme dans")
        print("  le rapport #1072).")
        print("")
        return 0
    if not tag.get("namedRet"):
        print("  ROUGE : %d appel(s) captures et ZERO `retCls` nomme -- le tag est CASSE."
              % tag["calls"])
        print("")
        return 1
    noms = {}
    for c in (lu.get("casts") or []):
        for k in (c.get("calls") or []):
            for n in ([k.get("retCls")] + list(k.get("argCls") or [])):
                if n:
                    noms[n] = noms.get(n, 0) + 1
    print("  %d nom(s) DISTINCT(S) vus ; les 12 plus frequents :" % len(noms))
    for n, c in sorted(noms.items(), key=lambda kv: -kv[1])[:12]:
        print("    %5d  %s" % (c, n))
    print("  Pour #1009-r3 : chercher les DEUX conjoints d'un `op_BitwiseAnd` dans un cast de")
    print("  `RelicPowerFist` -- `<A>` y sortira nomme.")
    print("")
    return 0


# --- CONTRE-EPREUVE : un probe qui rend `PAS EN VOL` partout doit le PROUVER ---------------
#
# Tant que la fenetre n'a pas eu lieu, les quatre volets rendent `PAS EN VOL` -- et un probe
# incapable de lire quoi que ce soit rendrait EXACTEMENT la meme chose. L'accord est donc en
# regime DEGENERE, et il ne prouve rien. Cette contre-epreuve fabrique les reponses qu'un bundle
# ARME rendrait, et exige que les volets (a) les LISENT et (b) ROUGISSENT quand la valeur est
# fausse. Elle est deterministe et 100 % offline : aucune session, aucun runner.

class _FauxSession:
    """Une session qui rend des reponses SCRIPTEES. Meme surface que `_Session`."""

    def __init__(self, table):
        self._t = table
        self.rid = 1

    def rpc(self, method, body=None, timeout=90):
        v = self._t.get(method)
        return v(body) if callable(v) else (v or {})

    def rpc_pos(self, method, args, timeout=60):
        v = self._t.get(method)
        return v(args) if callable(v) else (v or {})

    def dispose(self):
        pass


def _cs_arme(level, owner_env, mult_a=120, mult_b=120):
    """Ce que `combatSnapshot` rend une fois #1036-r8 et #969-r4 armes."""
    return {
        "ok": True,
        "tertiaryLayout": {"channelResolved": True, "abilityReadable": True, "errors": [],
                           "drift": [], "bcUnits": 175, "bcUnitsWithTertiary": 4},
        "tertiaryAbilityEnum": "IdunBattle.Entities.Enum.TriggeredAbilityType",
        "tertiaryLevelMeasured": True, "tertiaryAbilityMeasured": True,
        "units": [
            {"entityId": 87, "entityType": 6,
             "tertiary": {"configId": MOW, "abilityHasValue": True, "ability": 1548,
                          "abilityRaw": [1, 1548], "level": level, "multiplier": mult_a},
             "currentOwnerIsEnvironment": owner_env},
            {"entityId": 89, "entityType": 1,
             "tertiary": {"configId": "custoVexilusPraetor", "abilityHasValue": False,
                          "ability": None, "abilityRaw": [0, 0], "level": 0,
                          "multiplier": mult_a},
             "unitConfig": {"tertiaryAbilityVariablesMultiplier": mult_b},
             "currentOwnerIsEnvironment": False},
        ],
    }


def volet_contre_epreuve():
    print("=== CONTRE-EPREUVE : les volets LISENT-ILS un capteur arme ? (offline) ===")
    echecs = 0

    def attend(label, veut_zero, fn):
        nonlocal echecs
        import io                                                               # noqa: PLC0415
        import contextlib                                                       # noqa: PLC0415
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = fn()
        ok = (got == 0) if veut_zero else (got > 0)
        print("  %s %-58s -> %d echec(s)" % ("OK   " if ok else "ROUGE", label, got))
        if not ok:
            echecs += 1
            for ligne in buf.getvalue().splitlines():
                print("        | %s" % ligne)

    # (a) capteur ARME et JUSTE : le niveau vaut celui que `--equip-mythic` a ecrit.
    s = _FauxSession({"combatSnapshot": _cs_arme(NIVEAU, False)})
    attend("#1036-r8 arme, level = %d (attendu)" % NIVEAU, True, lambda: volet_1036r8(s))

    # (b) capteur ARME mais MENTEUR : `level = 0`. C'est une MESURE (verrouille), donc le volet
    #     ne doit PAS l'avaler comme un succes -- le montage demandait 4.
    s = _FauxSession({"combatSnapshot": _cs_arme(0, False)})
    attend("#1036-r8 arme, level = 0 (verrouille) -> doit ROUGIR", False,
           lambda: volet_1036r8(s))

    # (c) capteur ARME mais MUET : `level = null`. NON MESURE, jamais confondu avec 0.
    s = _FauxSession({"combatSnapshot": _cs_arme(None, False)})
    attend("#1036-r8 arme, level = null (non mesure) -> doit ROUGIR", False,
           lambda: volet_1036r8(s))

    # (d) le TEMOIN des deux voies : un multiplicateur qui DIVERGE doit rougir.
    s = _FauxSession({"combatSnapshot": _cs_arme(NIVEAU, False, mult_a=120, mult_b=180)})
    attend("#1036-r8 temoin : multiplicateur qui DIVERGE -> doit ROUGIR", False,
           lambda: volet_1036r8(s))

    # (e) #969-r4 arme, aucune unite Environment : PORTEUR MANQUANT, pas un echec.
    s = _FauxSession({"combatSnapshot": _cs_arme(NIVEAU, False)})
    attend("#969-r4 arme, 0 Environment -> porteur manquant, PAS un echec", True,
           lambda: volet_969r4(s))

    # (f) #969-r4 arme mais MUET (`null`) : le capteur n'a pas lu -> rouge.
    s = _FauxSession({"combatSnapshot": _cs_arme(NIVEAU, None)})
    attend("#969-r4 arme, valeur null -> doit ROUGIR", False, lambda: volet_969r4(s))

    # (g) #982-r6 arme : froide -> forcee, les slots nommes AUGMENTENT.
    def vt(args):
        a = args[0] if args else {}
        if a.get("forceInit"):
            return {"ok": True, "initializedBefore": False, "initialized": True,
                    "forcedInit": True, "forceInitError": None, "nonNullSlots": 61}
        return {"ok": True, "initializedBefore": False, "initialized": False,
                "forcedInit": False, "forceInitError": None, "nonNullSlots": 0}
    attend("#982-r6 arme, 0 -> 61 slots nommes", True,
           lambda: volet_982r6(_FauxSession({"resolveVtableSlot": vt})))

    # (h) #982-r6 arme mais SANS GAIN : le forcage n'a rien reveille -> rouge.
    def vt0(args):
        a = args[0] if args else {}
        return {"ok": True, "initializedBefore": False,
                "initialized": bool(a.get("forceInit")), "forcedInit": bool(a.get("forceInit")),
                "forceInitError": None, "nonNullSlots": 0}
    attend("#982-r6 arme, aucun gain -> doit ROUGIR", False,
           lambda: volet_982r6(_FauxSession({"resolveVtableSlot": vt0})))

    # (i) #982-r6 arme, forcage IMPOSSIBLE et NOMME -> rouge, avec la cause.
    def vtx(args):
        a = args[0] if args else {}
        return {"ok": True, "initializedBefore": False, "initialized": False,
                "forcedInit": False, "nonNullSlots": 0,
                "forceInitError": "`il2cpp_runtime_class_init` n'est pas exporte"}
    attend("#982-r6 arme, forcage impossible -> doit ROUGIR", False,
           lambda: volet_982r6(_FauxSession({"resolveVtableSlot": vtx})))

    # (j) #1009-r3 arme : le contrat est la, sans `--armer` on ne mesure pas -> pas un echec.
    s = _FauxSession({"dslCtorCasts": {"ok": True, "armed": False, "capturedCasts": 0,
                                       "tagging": {"calls": 0, "namedRet": 0, "args": 0,
                                                   "namedArgs": 0}, "casts": []}})
    attend("#1009-r3 arme, lecture pure -> pas un echec", True,
           lambda: volet_1009r3(s, False))

    print("  => %s" % ("les volets LISENT un capteur arme ET rougissent sur une valeur fausse"
                       if echecs == 0 else "%d comportement(s) faux" % echecs))
    print("")
    return echecs


def main():
    ap = argparse.ArgumentParser(description="#1072 -- contrat + interrogation des 4 capteurs")
    ap.add_argument("--source", action="store_true",
                    help="volet 0 seul (100 %% offline, aucun runner)")
    ap.add_argument("--volet", default=None,
                    choices=["1036r8", "969r4", "982r6", "1009r3"],
                    help="ne jouer qu'un volet live")
    ap.add_argument("--armer", action="store_true",
                    help="#1009-r3 : armer le traceur DSL, jouer un tour d'IA, lire, desarmer")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    echecs = volet_source()
    echecs += volet_contre_epreuve()
    if a.source:
        print("PORTEE : volets OFFLINE seuls (contrat + contre-epreuve). Les canaux ne sont PAS")
        print("         interroges -- rien n'est conclu de leur presence en vol.")
        print("\nBILAN : %s" % ("OK" if echecs == 0 else "%d ECHEC(S)" % echecs))
        return 0 if echecs == 0 else 1

    # `resolveVtableSlot` ne prend PAS de runner : le volet #982-r6 se joue sans en monter un.
    sans_runner = a.volet == "982r6"
    s = None
    try:
        s = _Session(None) if sans_runner else _build(a.verbose)
        if a.volet in (None, "1036r8"):
            echecs += volet_1036r8(s)
        if a.volet in (None, "969r4"):
            echecs += volet_969r4(s)
        if a.volet in (None, "982r6"):
            echecs += volet_982r6(s)
        if a.volet in (None, "1009r3"):
            echecs += volet_1009r3(s, a.armer)
    finally:
        if s is not None and not a.keep:
            s.dispose()

    print("PORTEE : ce probe garde les CANAUX, pas ce que le moteur Python en fait.")
    print("NON COUVERT : la face PORT de chacun des quatre residus, et -- tant que la fenetre")
    print("         n'a pas eu lieu -- toute mesure, puisque les capteurs ne sont pas armes.")
    print("\nBILAN : %s" % ("OK" if echecs == 0 else "%d ECHEC(S)" % echecs))
    return 0 if echecs == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
