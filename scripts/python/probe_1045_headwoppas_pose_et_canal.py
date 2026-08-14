"""#1045 -- CONFIRMATION LIVE des deux volets, sur un MEME montage.

Ce probe existe parce que les deux volets de #1045 se rejoignent sur un seul fait mesurable :
`HeadwoppasKillchoppa_ExtraDmg` (`EffectType` 0x620 = 1568) est POSE a l'init et INACTIF, donc il
est exactement le temoin dont le canal `decisionView` NU ne dit rien.

CE QU'IL MESURE, et pourquoi c'est le bon temoin :

  (A) LA RE DU VOLET 1. Le decompile `rnca9r7q6c` dit que l'effet naît au niveau **0** --
      `...Triggered.Loki.HeadwoppasKillchoppaAbility$$CreateBehaviour` passe `<DSLFormulas+0x18>`
      en 3e champ des `options`, `DSLFormulas$$.ctor` construit ce slot avec le scalaire `0`
      (`Direct(0)`), `AddEffectOperation$$Execute` l'ecrit dans `EffectComponent+0x68`, et ce champ
      est le NIVEAU (c'est celui qu'`IncreaseEffectLevelOperation$$Execute` incremente). Sa
      `CreateActiveCondition` = `AmountIsGreaterThanZero(EffectLevel)` est donc FAUSSE au
      deploiement. La mesure live doit montrer `active: false`, PAS l'absence de la RE.
      ⚠ Si le natif publiait `active: true`, c'est la lecture `Direct(0)` qui serait fausse -- et
      le verdict `flip: sim` inscrit dans `POSE_VECTOR` tomberait avec elle. Ce probe est donc la
      contre-epreuve de l'attestation, pas son illustration.

  (B) LE VOLET 2. Le meme effet, vu par les DEUX canaux : le canal NU le DROPPE
      (`frida/hooks/game/effects.ts` : `if (info && !info.active && !includeInactive) continue;`),
      la porte `snapshot.decision_view_seed_body` le publie. C'est le regime ou la fixture
      `prediction_confrontation.construire_scene` confrontait une `Scene` AMPUTEE a un oracle natif
      COMPLET -- degradation silencieuse, ni erreur ni ligne manquante.

MONTAGE. `orksWarboss` << Gulgortz >> est AU POOL (`--list-pool`) et c'est le seul porteur `voie:item`
de la relique -- les quatre autres Gulgortz sont npc. La relique n'est PAS equipee au seed : c'est
l'etat 2 des trois etats d'une ability de relique, donc `--equip-relic` (#237), qui ecrit les TROIS
champs dont DEUX echouent en silence (`TertiaryAbility`, la config dans `BC.Abilities.
PassiveAbilities`, et `TertiaryAbilityLevel >= 1`).

Usage :
    python probe_1045_headwoppas_pose_et_canal.py [--board MC1_67] [--seed 777]

rc 0 = les deux volets confirmes ; rc 1 = au moins un controle KO ; rc 2 = NON CONFRONTE (montage
indisponible -- on DIT pourquoi, on ne rend jamais un zero).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

TAG = "probe1045"
#: `TriggeredAbilityType` 0x60d = 1549 -- la relique. Son owner-effect est `EffectType` 0x620 = 1568.
RELIQUE = "HeadwoppasKillchoppa"
PORTEUR = "orksWarboss"
#: adversaire quelconque : ce probe ne fait AUCUNE attaque, il lit l'etat au deploiement.
ADVERSAIRE = "orksNob"


def _effect_ids(dec, uid):
    """Les `effectType` publies pour l'unite `uid`, avec leur flag `active` quand il l'est."""
    out = {}
    for u in (dec.get("units") or []):
        if int(u.get("id", -1)) != int(uid):
            continue
        for e in (u.get("effects") or []):
            t = e.get("effectType", e.get("type"))
            if t is not None:
                out[int(t)] = e.get("active")
    return out


def _unit_id(dec, visual):
    for u in (dec.get("units") or []):
        if u.get("visualId") == visual or u.get("unitId") == visual:
            return int(u["id"])
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#1045 -- pose niveau 0 et canal includeInactive")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--rank", default="17")
    a = ap.parse_args(argv)

    from engine.entities.effect_type import EffectType
    from engine.runner import snapshot as SNAP
    cible = int(EffectType.HeadwoppasKillchoppa_ExtraDmg)

    from probe_r6_round_materialize import _mkrpc
    rpc = _mkrpc()

    sf = ROOT / "logs" / "runners" / ("%s-%s.json" % (TAG, uuid.uuid4().hex[:8]))
    sf.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed), "--state-file", str(sf),
            "--board", a.board, "--roster", "1", "--rank", str(a.rank),
            "--p-units", PORTEUR, "--a-units", ADVERSAIRE,
            "--equip-relic", "%s:%s" % (PORTEUR, RELIQUE)]
    proc = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        print("NON CONFRONTE -- build KO : %s" % ((proc.stderr or proc.stdout or "")[-400:]))
        return 2
    rid = int(json.loads(sf.read_text())["runnerId"])
    print("runner %d ; board %s ; seed %s ; %s porte %s" % (rid, a.board, a.seed, PORTEUR, RELIQUE))

    ko = 0
    try:
        nu = rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 120)
        inact = rpc("decisionView",
                    SNAP.decision_view_seed_body(rid, maxRank=99, allAbilities=True), 120)
        uid = _unit_id(inact, PORTEUR)
        if uid is None:
            print("NON CONFRONTE -- %s absent de la vue (relique non montee ?)" % PORTEUR)
            return 2

        e_nu, e_in = _effect_ids(nu, uid), _effect_ids(inact, uid)
        print("")
        print("effets publies pour %s (id %d) :" % (PORTEUR, uid))
        print("  canal NU             : %s" % sorted(e_nu))
        print("  canal includeInactive: %s" % sorted(e_in))

        # (A) LA RE : l'effet EXISTE cote natif, et il est INACTIF.
        if cible not in e_in:
            print("")
            print("[A] KO : %d ABSENT MEME du canal includeInactive -- la pose d'init lue au "
                  "decompile ne se produit pas (ou la relique n'est pas montee)" % cible)
            ko += 1
        elif e_in.get(cible) is not False:
            print("")
            print("[A] KO : %d publie avec active=%r -- attendu False. La lecture `Direct(0)` du "
                  "3e champ des `options` serait FAUSSE, et le verdict `flip: sim` de POSE_VECTOR "
                  "tomberait avec elle." % (cible, e_in.get(cible)))
            ko += 1
        else:
            print("")
            print("[A] OK : %d est POSE et INACTIF (active=False) -- l'effet naît au niveau 0, "
                  "exactement ce que `<DSLFormulas+0x18> = Direct(0)` fait ecrire dans "
                  "`EffectComponent+0x68`." % cible)

        # (B) LE CANAL : le NU le droppe, la porte le publie.
        if cible in e_nu:
            print("[B] KO : %d publie MEME par le canal NU -- le capteur ne filtre plus les "
                  "inactifs, la porte ne servirait plus a rien" % cible)
            ko += 1
        else:
            print("[B] OK : %d est DROPPE par le canal NU et publie par la porte -- c'est "
                  "l'ecart que `prediction_confrontation` avalait en silence." % cible)

        # (C) LA FIXTURE REPAREE : sans `dec`, elle emprunte la porte, donc sa Scene voit l'inerte.
        import prediction_confrontation as PC
        scene, sctx, dec = PC.construire_scene(rpc, rid)
        if scene is None:
            print("[C] NON CONFRONTE -- Scene non constructible (combatSnapshot KO) ; les volets "
                  "A et B restent mesures.")
        else:
            vu = _effect_ids(dec, uid)
            ok_c = cible in vu
            print("[C] %s : le `dec` capte PAR LA FIXTURE porte %d = %s"
                  % ("OK" if ok_c else "KO", cible, ok_c))
            if not ok_c:
                print("      la fixture est repartie sur le canal NU -- le fix #1045 ne mord pas")
                ko += 1
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
            print("")
            print("runner %d dispose" % rid)
        except Exception as e:                                        # noqa: BLE001
            print("dispose KO (%s) -- runner %d peut survivre" % (type(e).__name__, rid))

    print("")
    print("VERDICT : %s" % ("les deux volets de #1045 sont CONFIRMES live" if not ko
                            else "%d controle(s) KO" % ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
