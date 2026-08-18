"""#1009-r3 -- NOMMER `<A>`, premier conjoint d'`IdunBattleLogic.Entities.DSLTriggers$$IsSpecialActiveAbility`.

CE QUI EST LU AU DECOMPILE (build `t6dpr4k06g`), et qui fixe exactement ce qu'il faut mesurer :

    IsSpecialActiveAbility(this):
        left = new <A>( <DSLSelectors+0x90> , 0 )            # classe = slot metadata DAT_1833a9738
        b    = new <B>( <DSLSelectors+0x90> , 0 )            # classe = slot metadata DAT_1833a95f0
        return AbilityTrigger.op_BitwiseAnd( left, AbilityTrigger.op_LogicalNot(b) )

`<B>` est NOMME parce que TROIS autres fonctions allouent le meme slot (`$$IsActiveAbilityCountedAsUsed`,
`$$IsNormalAttackOrHealOrRepair`, `$$IsTriggeringAbilityNormalAttackOrHealOrRepair`). `<A>`, lui, n'a
qu'UN allocateur -- `list_xrefs` sur `DAT_1833a9738` rend DEUX entrees, toutes deux dans
`IsSpecialActiveAbility` elle-meme --, son `.ctor` trivial est FONDU par l'ICF (le pseudo-C affiche
`UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor`), et le slot est VIDE a froid. Aucune
voie de TABLE ne le nomme.

LA VOIE QUI RESTE : le capteur `dslCtorCasts` (#1072) tague chaque appel par la CLASSE REELLE de son
retour et de ses arguments (`retCls` / `argCls`, via `readMsgIdentity`). `AbilityTrigger$$op_BitwiseAnd`
EST une cible hookee, donc son `argCls[0]` **est** le nom plein de `<A>`.

⚠ **CE QUE CE PROBE A D'ABORD MESURE, ET QUI CONTREDIT LA FICHE DU RESIDU.** Elle disait << le
bloqueur n'est plus le capteur -- reste un MONTAGE, equiper RelicPowerFist et le caster >>. C'est
FAUX, et aucun montage ne l'aurait leve : la PORTE du capteur (`dsl-ctor-trace.enumGates`) ne
s'ouvrait que sur `<Ability>.ExecuteBehaviour`, alors que les DEUX SEULS call-sites de
`IsSpecialActiveAbility` sont `...RelicPowerFistAbility$$CreateBehaviour` et
`...Dw02AdvancedBurstCannonAbility$$CreateTrigger` -- deux abilities DECLENCHEES, qui ne declarent
NI l'une NI l'autre d'`ExecuteBehaviour` (`data/symbols/<build>/frida/methods.tsv` : elles n'ont que
`CreateTrigger` et `CreateBehaviour`). MESURE du 2026-08-18 (session 11, capteur arme puis
desarme) : apres un `rl_duel build` complet, `dslCtorCasts` rend 17 casts dont les abilities sont
TOUTES des actives, et `MAX_CALLS` (4000) est deja SATURE par les casts des autres agents.

⚠ **CE PROBE EXIGE DONC UNE FENETRE DE REINJECT** -- le correctif est dans le bundle
(`frida/hooks/features/dsl-ctor-trace.ts` : `GATE_METHODS` s'ouvre aussi sur `CreateBehaviour` et
`CreateTrigger`, et `dslCtorArm({only})` borne la capture a une ability pour ne pas saturer), mais
un agent ne (re)injecte jamais. Tant que la session tourne sur l'ancien bundle, ce probe REFUSE au
lieu de rendre un resultat vide : il verifie que `dslCtorArm` accepte `only` et le DIT.

    python probe_1009r3_nommer_le_conjoint.py [--porteur darkaAzrael] [--relique RelicPowerFist]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
#: La classe d'ability visee -- `only` du capteur. Sous-chaine du NOM DE CLASSE lu par `readMsgClass`.
CIBLE = "RelicPowerFist"


def rpc(sid, method, args, timeout=120):
    r = _rpc(sid, method, [args], timeout=timeout)
    return r.get("result", r) if isinstance(r, dict) else r


def build(seed: str, board: str, relique: str, porteur: str):
    state = ROOT / "logs" / "runners" / ("st-1009r3-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--state-file", str(state), "--no-ai",
         "--p-units", "%s,ultraCalgar" % porteur, "--a-units", "necroWarden,necroSpyder",
         "--equip-relic", "%s:%s" % (porteur, relique)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO : %s" % (p.stderr or p.stdout or "")[-700:])
        return None
    return json.loads(state.read_text())["runnerId"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--porteur", default="darkaAzrael")
    ap.add_argument("--relique", default="RelicPowerFist")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sid = _resolve_session()

    # --- ETAGE 0 : LE BUNDLE CHARGE PORTE-T-IL LA PORTE ELARGIE ? -----------------------------
    # Sans elle, la mesure serait un VIDE qui se lit comme « le conjoint n'a pas de nom ».
    etat = rpc(sid, "dslCtorCasts", {}, timeout=30)
    if etat.get("armed"):
        print("NON MESURE : le capteur est DEJA arme (par un autre agent ?) -- on ne le desarme")
        print("             PAS sous ses pieds. Reessayer plus tard.")
        return 2
    arm = rpc(sid, "dslCtorArm", {"only": CIBLE}, timeout=60)
    if not arm.get("ok"):
        print("NON MESURE : `dslCtorArm` refuse : %s" % json.dumps(arm)[:300])
        return 2
    print("[0] arme : %s" % json.dumps(arm))
    if arm.get("only") is None:
        rpc(sid, "dslCtorDisarm", {}, timeout=30)
        print("NON MESURE : le bundle CHARGE ignore l'option `only` -- c'est l'ANCIENNE version du")
        print("             capteur, dont la porte ne s'ouvre que sur `ExecuteBehaviour`. Les deux")
        print("             call-sites de `IsSpecialActiveAbility` sont des `CreateBehaviour` /")
        print("             `CreateTrigger` : la porte ne s'ouvrira JAMAIS et le resultat serait un")
        print("             VIDE trompeur. Le correctif est livre dans")
        print("             `frida/hooks/features/dsl-ctor-trace.ts` -- il attend une FENETRE DE")
        print("             REINJECT. Ecrire << NON CONFRONTE -- exige une fenetre de capteur >>.")
        return 2

    rid = None
    try:
        # --- ETAGE 1 : LE MONTAGE -- la relique EQUIPEE, donc l'ability DECLENCHEE MONTEE -------
        # Une triggered ability construit son arbre a l'INIT de l'acteur : le seul fait de batir
        # le runner avec la relique equipee suffit, il n'y a AUCUN cast a jouer.
        rid = build(a.seed, a.board, a.relique, a.porteur)
        if rid is None:
            return 2
        print("[1] runner=%s porteur=%s relique=%s" % (rid, a.porteur, a.relique))

        # --- ETAGE 2 : LIRE LE TAG ---------------------------------------------------------------
        res = rpc(sid, "dslCtorCasts", {}, timeout=60)
        tag = res.get("tagging") or {}
        print("[2] casts=%s tagging=%s" % (res.get("capturedCasts"), json.dumps(tag)))
        if not res.get("capturedCasts"):
            print("NON MESURE : aucune construction de `%s` capturee -- verifier que la relique est")
            print("             REELLEMENT montee (les TROIS ecritures de #237 : `TertiaryAbility`,")
            print("             la config dans `BC.Abilities.PassiveAbilities`, et")
            print("             `TertiaryAbilityLevel >= 1`)." % CIBLE)
            return 2
        if tag.get("calls") and not tag.get("namedArgs"):
            print("NON MESURE : le tag n'a mordu sur AUCUN argument (calls=%s namedArgs=0) -- c'est")
            print("             la signature d'un tag CASSE, pas d'un noeud sans nom." % tag["calls"])
            return 2

        # L'appel qui porte les deux conjoints : `AbilityTrigger.op_BitwiseAnd(left, not(b))`.
        conj = [k for c in (res.get("casts") or []) for k in (c.get("calls") or [])
                if str(k.get("m", "")).endswith("op_BitwiseAnd")]
        print("[2] appels `op_BitwiseAnd` captures : %d" % len(conj))
        for k in conj:
            print("    seq=%s retCls=%s argCls=%s" % (k.get("seq"), k.get("retCls"),
                                                      json.dumps(k.get("argCls"))))
        noms = sorted({t for k in conj for t in (k.get("argCls") or []) if t})
        print("")
        print("CLASSES DES CONJOINTS (candidats pour <A> et <B>) : %s" % (noms or "AUCUNE"))
        print("A CONFRONTER AU DECOMPILE : <B> est la classe qu'allouent AUSSI")
        print("  `IdunBattleLogic.Entities.DSLTriggers$$IsActiveAbilityCountedAsUsed` et")
        print("  `IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttackOrHealOrRepair` ;")
        print("  <A> est l'AUTRE, et c'est LUI le nom que #1009-r3 cherche.")
        return 0
    finally:
        try:
            rpc(sid, "dslCtorDisarm", {}, timeout=30)
            print("[fin] capteur DESARME")
        except Exception as exc:                                        # noqa: BLE001
            print("[fin] disarm KO : %s" % exc)
        if rid and not a.keep:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=30)
                print("[fin] runner %s dispose" % rid)
            except Exception as exc:                                    # noqa: BLE001
                print("[fin] dispose KO : %s" % exc)


if __name__ == "__main__":
    sys.exit(main())
