"""#1016 -- CONFRONTATION LIVE des deux passifs Necrons (`ReanimationProtocols` 1008,
`WhipcoilBody` 1009 / effet 1118).

Le decompile est la verite ; ce probe est la CONFIRMATION. Il repond a deux questions que le
decompile seul ne tranche pas, parce qu'elles portent sur ce que le NATIF fait a l'execution :

  A. `WhipcoilBody` -- l'appariement ability -> effet est-il celui que le corps `return 0x45e` de
     `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WhipcoilBodyAbility$$GetEffectType`
     annonce, et la base `AOwnerEffectTriggeredAbility` POSE-t-elle vraiment l'effet a l'init du
     porteur, sans aucun cast ? On le lit dans `decisionView.effects` d'une unite du pool sur
     laquelle le passif est GREFFE (`case-92` sec.5bis).
     ⚠ La condition de greffe est VERIFIEE au decompile, pas supposee :
     `...WhipcoilBody_ReduceDmgEffect$$CreateEffectDamageMalusForDefense` ne lit NI stat NI trait
     NI arme du porteur -- seulement `ConfigVar(dmgReduction)` de la config du passif et le fait
     que le porteur soit la cible d'un coup de melee.

  B. `ReanimationProtocols` -- le predicat `count > 1` du trigger est-il SATISFAISABLE en bataille
     reelle, et par quel chemin ? Le porteur le moins cher est le SUMMON `necroSmnSwarm`, et
     `ScarabHive` (active de `necroSpyder`, `kind = lineup`, AU POOL) en spawne **DEUX d'un coup**
     -- donc deux unites de MEME `visual_id` et de MEME equipe, ce qui est exactement le regime ou
     le passif mord. Un seul swarm rendrait le predicat FAUX et le montage ne prouverait rien.

## CE QUI A ETE MESURE (2026-08-13, build `rnca9r7q6c`, board MC1_67, seed 777, rank 17)

**A -- CONFRONTE, et il confirme les TROIS lectures du decompile.** Sur un `necroWarden` greffe,
`decisionView` publie :

    {"effectType": 1118, "name": "WhipcoilBody_ReduceDmg", "active": true, "remaining": 0,
     "source": 81, "targetIds": [81], "level": 1, "effectId": 94}

  * `effectType == 1118` => l'appariement `GetEffectType() = 0x45e` est bien celui du corps LU ;
  * `source == targetIds == 81` (le porteur) => `AddEffect(..., source = Owner@+0x30,
    targets = Owner@+0x30)` de la base `AOwnerEffectTriggeredAbility$$CreateBehaviour` ;
  * `remaining == 0` => `turns = <zeroe>` (PERMANENT), et `active == true` SANS aucune condition
    remplie => `CreateActiveCondition = <DSLTriggers+0x40>` est bien la constante VRAIE.
  Le passif greffe n'a demande AUCUN cast : l'effet est la des l'init.
  ⚠ `level: 1` est un fait du MONTAGE (la greffe pose le niveau 1), pas du port -- la magnitude
  live serait donc `dmgReduction[1] = 7`, pas 388. Le scaling par niveau, lui, est garde offline.

**B -- NON CONFRONTE (residu #1016-r1), et la raison est un trou de PILOTAGE, pas un verdict.**
Ce qui est ETABLI : `ScarabHive` (`ActiveAbilityType` 1007, active de `necroSpyder`, AU POOL) vise
un ENNEMI et pose DEUX swarms a cote de lui (i2 : << Summons 2 Scarab Swarms next to the target
>>) -- c'est bien le regime `count > 1` du trigger. Ce qui BLOQUE : le cast n'a pas pu etre joue.
  * mis cote ADVERSAIRE, l'IA native n'a PAS caste `ScarabHive` en 3 tours (elle attaque) ;
  * mis de MON cote, `abilityTargets` rend `targetCount = 0` a la position de spawn, puis
    `targetCount = 1 / fromHereCount = 0` des que l'IA s'approche -- il faut donc BOUGER d'abord ;
  * or `rl_duel act move --to` rend `rc = 0` sans que le summoner quitte `(1,0)`, et
    `play --auto aggressive` ne deplace pas (`spec VIDE -> aucune action`) quand aucune attaque
    n'est a portee.
Le montage a REJOUER est donc : approcher le summoner par un chemin de deplacement qui MORD (le
diagnostic du `move` sans effet est le premier etage a mesurer), puis caster sur l'ennemi, puis
tuer UN swarm (l'autre vivant -> branche VRAIE, ~35 %) et le DERNIER swarm (branche FAUSSE,
0 revive garanti). Le porteur n'est PAS en cause : `necroSmnSwarm` arrive en bataille par son
summoner, qui est au pool.

DISCIPLINE RUNNER : `--state-file` ABSOLU a nom UNIQUE, `--runner` explicite, et on DISPOSE ses
propres runners (jamais ceux des autres). ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
#: SORTIES du run -> `logs/` (gitignore), JAMAIS `data/` (qui ne porte que des ENTREES).
OUT = ROOT / "logs" / "probe_1016"

BOARD = "MC1_67"
SEED = "777"
RANK = "17"
#: Greffon de l'etape A : `necroWarden` est `kind = lineup`, AU POOL, et MECANIQUE -- mais aucune
#: de ces proprietes n'est lue par l'arbre greffe (cf. l'en-tete). Le greffon n'a donc pas a
#: ressembler au vrai porteur ; il doit seulement arriver en bataille.
GRAFT_UNIT = "necroWarden"
GRAFT_ABILITY = "WhipcoilBody"
GRAFT_EFFECT = "WhipcoilBody_ReduceDmg"
#: Etape B : le summoner AU POOL, son active, et le summon porteur du passif.
SUMMONER = "necroSpyder"
SUMMON_ABILITY = "ScarabHive"
SWARM = "necroSmnSwarm"


def _run(args: list, timeout: int = 420) -> tuple:
    p = subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def _decision(state_file: Path) -> dict:
    """`decisionView` du runner decrit par `state_file`.

    ⚠ `rl_duel.py view` n'est PAS une voie de MESURE : il imprime une CARTE ASCII (`_show_card`),
    pas le JSON du RPC. Parser sa sortie rendait un `None` qu'on aurait pu lire comme << l'effet
    n'est pas la >> -- exactement le zero fabrique que la doctrine tri-etat interdit. On appelle
    donc le RPC, et une impossibilite LEVE."""
    from rl_collect_batch import _resolve_session, _rpc
    st = json.loads(state_file.read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    if rid is None:
        raise RuntimeError("state-file sans runnerId : %s" % state_file)
    sid = _resolve_session()
    res = _rpc(sid, "decisionView",
               [{"runnerId": int(rid), "maxRank": 8, "allAbilities": True}],
               timeout=300)
    out = res.get("result")
    if out is None:
        raise RuntimeError("decisionView sans resultat : %s" % json.dumps(res)[:400])
    return out


def _dispose(state_file: Path):
    if state_file.exists():
        _run(["dispose", "--state-file", str(state_file)], timeout=120)


def etape_a(keep: bool) -> dict:
    """A -- GREFFE de `WhipcoilBody` sur une unite du pool, puis lecture de l'effet POSE."""
    import catalog_inject as CI
    OUT.mkdir(parents=True, exist_ok=True)
    seed_bc, reports = CI.write_grafted_seed_bc(
        OUT / ("seed_bc_whipcoil_%d.json" % os.getpid()),
        ["%s:%s" % (GRAFT_UNIT, GRAFT_ABILITY)], kind="passive")
    print("[A] greffe ecrite : %s" % json.dumps(reports[0], sort_keys=True))
    sf = OUT / ("state_1016a_%d.json" % os.getpid())
    rc, out, err = _run(["build", "--seed", SEED, "--rank", RANK, "--board", BOARD,
                         "--seed-bc", str(seed_bc),
                         "--p-units", GRAFT_UNIT, "--a-units", "necroDestroyer,necroOverlord",
                         "--state-file", str(sf)])
    if rc != 0:
        print("[A] BUILD rc=%d\n%s\n%s" % (rc, out[-1500:], err[-800:]))
        return {"ok": False, "etape": "build", "rc": rc}
    view = _decision(sf)
    # `decisionView` publie les effets **PAR UNITE** (`units[].effects`), PAS a la racine -- une
    # lecture a la racine rend `0`, et un zero se lit comme << l'effet n'est pas pose >>. C'est le
    # meme vice que le tri-etat combat : on compte donc AUSSI le total publie, pour qu'un montage
    # muet se distingue d'un effet absent.
    units = [u for u in (view.get("units") or []) if isinstance(u, dict)]
    total = sum(len(u.get("effects") or []) for u in units)
    mine = [(u.get("visualId"), e) for u in units for e in (u.get("effects") or [])
            if str(e.get("name") or "") == GRAFT_EFFECT or int(e.get("effectType") or -1) == 1118]
    res = {"ok": bool(mine), "nb_effets_publies": total, "nb_unites": len(units),
           "effets_1118": [e for _v, e in mine],
           "porteurs": sorted({v for v, _e in mine if v})}
    print("[A] effets 1118 : %d | %d effets publies sur %d unites | porteurs=%s"
          % (len(mine), total, len(units), res["porteurs"]))
    for v, e in mine[:4]:
        print("    %-16s %s" % (v, json.dumps(e, sort_keys=True)[:300]))
    if not mine and total == 0:
        print("    ⚠ AUCUN effet publie sur AUCUNE unite -- montage muet, pas un verdict d'absence")
    if not keep:
        _dispose(sf)
    else:
        print("[A] runner CONSERVE : %s" % sf)
    return res


def etape_b(keep: bool) -> dict:
    """B -- `ScarabHive` spawne-t-il DEUX `necroSmnSwarm` de la MEME equipe (predicat `count > 1`) ?"""
    OUT.mkdir(parents=True, exist_ok=True)
    sf = OUT / ("state_1016b_%d.json" % os.getpid())
    # ⚠ MESURE (2026-08-13) : mis cote ADVERSAIRE, l'IA native n'a PAS caste `ScarabHive` en trois
    # tours -- elle a prefere attaquer. On commande donc le SUMMONER (ce qui est licite : c'est une
    # ACTIVE d'une unite du pool), et on OBSERVE ses summons. Ce n'est pas commander un summon
    # (#291) : le summon, lui, reste hors de `toActivate`.
    rc, out, err = _run(["build", "--seed", SEED, "--rank", RANK, "--board", BOARD,
                         "--p-units", SUMMONER, "--a-units", "necroWarden,necroDestroyer",
                         "--state-file", str(sf)])
    if rc != 0:
        print("[B] BUILD rc=%d\n%s\n%s" % (rc, out[-1500:], err[-800:]))
        return {"ok": False, "etape": "build", "rc": rc}
    v0 = _decision(sf)
    av = [u for u in (v0.get("units") or []) if str(u.get("visualId") or "") == SWARM]
    #: `ActiveAbilityType` de `ScarabHive`, RESOLU (jamais un litteral en dur) -- `--ability` de
    #: `rl_duel` attend l'ORDINAL, pas le nom.
    import catalog_inject as CI
    aid = CI.active_ability_id(SUMMON_ABILITY)
    # ⚠ MESURE : `abilityTargets` rend `targetCount = 0` a la position de SPAWN -- l'i2 dit
    # << Summons 2 Scarab Swarms next to the TARGET, whom they immediately attack >>, donc cette
    # active vise un ENNEMI et il faut etre a portee. On DEPLACE le summoner (doctrine : jamais
    # << bloque par la geometrie de spawn >>) en jouant des tours agressifs jusqu'a ce que le cast
    # soit legal, puis on OBSERVE les summons apparaitre.
    n = 0
    for tour in range(1, 9):
        rc, out, err = _run(["play", "--auto", "aggressive", "--state-file", str(sf)])
        rc2, _o2, _e2 = _run(["aiturn", "--state-file", str(sf)])
        us = _decision(sf).get("units") or []
        n = len([u for u in us if str(u.get("visualId") or "") == SWARM])
        vivants = [u.get("visualId") for u in us if u.get("alive") is not False]
        print("[B] tour %d : play rc=%d aiturn rc=%d -> %d %s | vivants=%s"
              % (tour, rc, rc2, n, SWARM, vivants))
        if n >= 2 or not [u for u in us if str(u.get("visualId") or "") == SUMMONER
                          and u.get("alive") is not False]:
            break
    v1 = _decision(sf)
    swarms = [u for u in (v1.get("units") or []) if str(u.get("visualId") or "") == SWARM]
    teams = sorted({u.get("team") for u in swarms})
    res = {"ok": len(swarms) >= 2 and len(teams) == 1,
           "swarms_avant": len(av), "swarms_apres": len(swarms), "equipes": teams,
           "hp": [(u.get("id"), u.get("hp"), u.get("maxHp") or u.get("hpMax")) for u in swarms]}
    print("[B] %s : %d avant -> %d apres, equipes=%s" % (SWARM, len(av), len(swarms), teams))
    for u in swarms:
        print("    id=%s team=%s hp=%s/%s" % (u.get("id"), u.get("team"), u.get("hp"),
                                              u.get("maxHp") or u.get("hpMax")))
    if not keep:
        _dispose(sf)
    else:
        print("[B] runner CONSERVE : %s" % sf)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--etape", choices=["a", "b", "ab"], default="ab")
    ap.add_argument("--keep", action="store_true", help="ne PAS disposer le runner (debug)")
    a = ap.parse_args(argv)
    out = {}
    if "a" in a.etape:
        out["A_whipcoil_greffe"] = etape_a(a.keep)
    if "b" in a.etape:
        out["B_scarabhive_deux_swarms"] = etape_b(a.keep)
    print("\n=== BILAN #1016 ===")
    for k, v in out.items():
        print("  %-28s ok=%s" % (k, v.get("ok")))
    return 0 if all(v.get("ok") for v in out.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
