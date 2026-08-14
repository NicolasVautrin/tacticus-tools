"""CONFRONTATION LIVE de la face DECISION de `1108 KissOfDeath` (`#940-r3`).

Le port (#940-r2) est garde offline et verifie par 5 mutations, mais aucun TERME NATIF ne lui
avait ete oppose. Ce probe le fait.

    NATIF  `ncPlaybookPredict(via="evaluate")` -> `playbookClass` + `bucketUtil` + `bucket`
    PORT   `PLAYBOOKS[1108].evaluate_non_comparable(origin, cible, NCContext)`

LE MONTAGE -- GREFFE, et sa CONDITION est RE-LUE au decompile
--------------------------------------------------------------
Les deux porteurs de 1108 sont `eldarNpc3Harlequin` (**npc**) et `eldarSmnHarlequin` (**summon**
dont l'unique declarant est `EnvFactionSummons:Aeldari`, spawner d'ENVIRONNEMENT rattache a AUCUNE
unite -> la voie summon est FERMEE). Recours : la **GREFFE** (`case-92` §5bis recours 3), dont la
condition est verifiee ET relue :

  * le playbook est enregistre **PAR ABILITY** (`metadata/active_playbook_builders.tsv` :
    `active 1108 IdunBattle.AI.Playbook.Loki.KissOfDeathPlaybook`), donc c'est l'ability qui
    l'amene, pas l'unite ;
  * `KissOfDeathPlaybook$$EvaluateNonComparable` **ne lit NI stat NI trait du caster** : le caster
    n'entre que par `GetEligibleTargetsEntities(caster, casterPosition.MainTile)` et par
    `GenerateAction(casterPosition, ...)`. Greffer sur une unite du pool ne peut donc pas fausser
    le terme.

`playbookClass` rendu par le RPC est le CONTROLE que la greffe a MORDU : si le natif chargeait le
playbook par defaut, il rendrait autre chose et le probe LEVE.

LES TROIS REGIMES, ET POURQUOI ILS SEPARENT
--------------------------------------------
L'utilite est `|GetChainedUnits(cible, onlyFriends: true)|` -- la composante connexe des AMIS DE LA
CIBLE, **cible comprise** (`adj.Add(tile)` la fait entrer au premier niveau). Le `Bucket` a
`minUtility = 2`. On fait donc varier la TOPOLOGIE DES ADVERSAIRES, en les DEPLACANT (jamais en
subissant la geometrie de spawn) :

    A  cible ISOLEE          -> terme 1  -> SOUS le seuil -> bucket **VIDE**
    C  chaine de 2           -> terme 2  -> JUSTE au seuil -> bucket non vide, util **2**
    B  chaine de 3           -> terme 3  ->                   bucket non vide, util **3**

⚠ **TEMOIN NON DEGENERE, et c'est la condition de validite** : les trois regimes rendent TROIS
issues natives differentes, dont un **refus** (A). Un accord sur un seul regime, ou sur trois
regimes qui rendraient la meme chose, ne prouverait rien -- « accord en regime DEGENERE = zero
preuve ». Le verdict EXIGE que le natif separe.

⚠ **1108 est MELEE** (`attackRangeType` de la config = « Melee »), et `EvaluateNonComparable`
n'interroge que `casterPosition.MainTile` -- **pas** les tuiles de move. Le caster doit donc etre
ADJACENT a sa cible, sinon `GetEligibleTargetsEntities` rend VIDE et les trois regimes s'ecrasent
sur « bucket vide » : l'accord serait DEGENERE et ne dirait rien. Le placement l'assure, et le
probe REFUSE un regime B/C dont la liste de cibles eligibles serait vide.

    python probe_940r2_kiss_of_death_decision.py --state-file <abs> [--board MC1_67] [--seed 777]

Discipline runner : `--state-file` ABSOLU et propre, runners DISPOSES en fin de run. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from engine.entities.active_ability_type import ActiveAbilityType   # noqa: E402

KISS = int(ActiveAbilityType.KissOfDeath)      # 0x454 = 1108
STORM = int(ActiveAbilityType.StormOfWrath)    # 0x3fb = 1019 -- le jumeau au decompile

#: L'unite du pool qui recoit la greffe. AELDARI comme le porteur natif : aucun gate ne lit la
#: faction du caster, mais ca garde le scenario lisible.
GREFFE_SUR = "eldarAutarch"
#: La cle gameconfig de 1108 -- `write_grafted_seed_bc` greffe PAR NOM (le nom discrimine, pas
#: l'ordinal : `TriggeredAbilityType` partage 233 ordinaux avec `ActiveAbilityType`).
ABILITY_NAME = "KissOfDeath"
P_UNITS = "eldarAutarch"
A_UNITS = "necroWarden,necroDestroyer,orksNob"

#: Le caster est colle a `necroWarden` : 1108 est MELEE, donc sans adjacence la liste de cibles
#: eligibles est VIDE et les trois regimes deviennent indiscernables.
CASTER_AT = "eldarAutarch:3,3"
CIBLE_AT = "necroWarden:3,4"

#: On ne DEPLACE que les DEUX autres adversaires : la cible et le caster ne bougent pas d'un
#: regime a l'autre, donc la seule variable est la TAILLE DE LA CHAINE.
MONTAGES = (
    ("A: cible ISOLEE (chaine 1, SOUS le seuil)", ["necroDestroyer:0,6", "orksNob:6,1"], 1.0),
    ("C: chaine de 2 (JUSTE au seuil)", ["necroDestroyer:3,5", "orksNob:6,1"], 2.0),
    ("B: chaine de 3", ["necroDestroyer:3,5", "orksNob:4,4"], 3.0),
)


def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=120):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def greffer(out: Path) -> Path:
    """`case-92` §5bis -- greffe de l'ACTIVE 1108 sur une unite DU POOL, par l'API DEDIEE.

    ⚠ **Une greffe ecrite a la main NE SUFFIT PAS, et le refus est EXPLICITE.** Poser seulement
    `BC.Units[].ActiveAbilities = [1108]` laisse la CONFIG d'ability absente de
    `BC.Abilities.ActiveAbilities` -- c'est le verrou #226 (« system error » au cast). Mesure de la
    1re passe de ce probe : `config 1108 dans la BC : False`, et `rl_duel` a REFUSE le build en
    nommant la cause (`eldarAutarch{ActiveAbilities} INATTENDUE`, garde #254-bc). Le garde a donc
    fait exactement son travail -- il a transforme un montage silencieusement faux en refus lisible.

    `catalog_inject.write_grafted_seed_bc(kind="active")` fait les DEUX ecritures (l'entree d'unite
    ET la config synthetisee depuis le gameconfig), et survit au rechargement (#380). Sortie dans
    `logs/`, jamais dans `data/` (`reject_data_output` le garantit)."""
    import catalog_inject as CI
    p, reports = CI.write_grafted_seed_bc(out, ["%s:%s" % (GREFFE_SUR, ABILITY_NAME)],
                                          kind="active", replace=True)
    CI.declare_graft("active", GREFFE_SUR, "%s (%d)" % (ABILITY_NAME, KISS))
    print("[940r2] greffe ACTIVE %s -> %s : %s" % (ABILITY_NAME, GREFFE_SUR,
                                                   json.dumps(reports, default=str)[:300]))
    return Path(p)


def build(state_file: Path, bc: Path, seed: int, board: str, a_place: list) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--state-file", str(state_file), "--no-ai", "--seed-bc", str(bc),
           "--p-units", P_UNITS, "--a-units", A_UNITS, "--place", CASTER_AT,
           "--a-place", CIBLE_AT]
    for p in a_place:
        cmd += ["--a-place", p]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-2000:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _caster_id(rpc, sid, rid: int):
    dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    # `decisionView.units[]` porte l'id sous `id` (PAS `unitId` -- mesure de la passe 3, qui a
    # rendu « caster introuvable » sur un runner pourtant construit : un champ absent se lit comme
    # une absence d'unite).
    for u in (dv.get("units") or []):
        if u.get("visualId") == GREFFE_SUR:
            return int(u["id"]), dv
    vus = sorted({str(u.get("visualId")) for u in (dv.get("units") or [])})
    raise RuntimeError("caster %s absent de decisionView -- unites vues : %s"
                       % (GREFFE_SUR, ", ".join(vus)))


def oracle_natif(rpc, sid, rid: int, caster_id: int) -> dict:
    """`ncPlaybookPredict(via="evaluate")` -> ce que `Bucket$$ChooseAction` retiendrait.

    ⚠ UN ECHEC RENDU N'EST PAS UNE MESURE : `ok: false` LEVE au lieu de se lire comme un refus."""
    r = _r(rpc, sid, "ncPlaybookPredict",
           {"runnerId": rid, "unitId": caster_id, "abilityType": KISS, "via": "evaluate"}, 300)
    if not r.get("ok"):
        raise RuntimeError("ncPlaybookPredict a ECHOUE (capteur muet, PAS un refus) : %s"
                           % json.dumps(r, default=str)[:400])
    cls = r.get("playbookClass")
    if cls != "KissOfDeathPlaybook":
        raise RuntimeError("le natif a charge %s, pas KissOfDeathPlaybook -- la GREFFE n'a pas "
                           "mordu, donc rien de ce qui suit ne mesure 1108" % cls)
    return {"classe": cls, "util": r.get("bucketUtil"), "actions": r.get("bucketActionCount"),
            "vide": r.get("bucket") == "empty"}


def nc_context(rpc, sid, rid: int, caster_id: int):
    """Le `NCContext` de la face DECISION, monte par la MEME voie que le moteur (#970-r3)."""
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene
    from engine import weights
    dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(rpc, sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: _r(rpc, sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: _r(rpc, sid, m, b, t), rid, dv, mov_by_unit, caster_id,
                      weights.load(), predictor)
    return PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        is_wall_by_pos=getattr(c, "is_wall_by_pos", None) or {},
        is_in_fog_by_pos=getattr(c, "is_in_fog_by_pos", None) or {},
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        current_player=getattr(c, "cur", None),
        machine_of_war_position=c.machine_of_war_position,
        triggered_kits=getattr(c, "live_triggered_kits", None),
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)


def port(rpc, sid, rid: int, caster_id: int) -> dict:
    """Le port, et le PROFIL COMPLET de ses utilites sur les cibles eligibles -- pas seulement
    l'argmax : c'est le profil qui dit si le regime a REELLEMENT ete exerce."""
    from engine.playbook import noncomparable as PB
    from engine.playbook.noncomparable import _targets as NCT
    nc = nc_context(rpc, sid, rid, caster_id)
    pb = PB.PLAYBOOKS[KISS]
    # ⚠ 1108 cible des UNITES, pas des tuiles : `GetEligibleTargetsEntities` rend des entites, et
    # `evaluate_non_comparable(tile, target, ctx)` recoit un ID D'UNITE en `target`. La passe 4 de
    # ce probe lisait `eligible_target_tiles` (le canal des abilities tile-targeted) et rendait
    # `cibles=0` sur les TROIS regimes -- une divergence ENTIEREMENT fabriquee par le probe, alors
    # que le natif, lui, separait deja proprement (refus / 2 / 3). Un canal muet se lit comme une
    # absence de cible : c'est exactement le faux negatif que le verdict doit refuser de conclure.
    cibles = [t[0] if isinstance(t, (tuple, list)) else t
              for t in (NCT.eligible_units(nc, KISS) or [])]
    profil = {}
    for t in cibles:
        u = pb.evaluate_non_comparable(nc.origin, t, nc)
        if u is not None:
            profil[t] = u
    top = max(profil.values()) if profil else None
    admis = [v for v in profil.values() if v >= pb.MIN_UTILITY]
    # Le JUMEAU, evalue sur le MEME contexte : si les deux corps natifs calculent la meme chose,
    # les deux ports doivent le faire aussi -- et un cablage croise se verrait ici.
    jum = PB.PLAYBOOKS[STORM]
    profil_j = {t: jum.evaluate_non_comparable(nc.origin, t, nc) for t in cibles}
    return {"n_cibles": len(cibles), "profil": profil, "top": top,
            "n_admis": len(admis), "vide": not admis,
            "top_jumeau": (max(profil_j.values()) if profil_j else None)}


def mesurer(rpc, sid, rid, libelle, attendu_port) -> dict:
    cid, _dv = _caster_id(rpc, sid, rid)
    nat = oracle_natif(rpc, sid, rid, cid)
    prt = port(rpc, sid, rid, cid)
    print("[940r2] %-44s NATIF vide=%-5s util=%-6s actions=%-3s | PORT cibles=%d top=%-5s admis=%d"
          % (libelle, nat["vide"], nat["util"], nat["actions"],
             prt["n_cibles"], prt["top"], prt["n_admis"]))
    return {"libelle": libelle, "natif": nat, "port": prt, "attendu_port": attendu_port}


def verdict(res: list) -> list:
    """Le verdict, et d'abord la NON-DEGENERESCENCE : sans regimes separes, l'accord ne prouve
    rien. On l'assertionne AVANT de conclure quoi que ce soit sur l'accord."""
    ko = []
    issues = {(r["natif"]["vide"], r["natif"]["util"]) for r in res}
    if len(issues) < len(res):
        ko.append("TEMOIN DEGENERE : le natif rend %d issue(s) distincte(s) pour %d regimes -- "
                  "l'accord ne prouverait rien (issues=%s)" % (len(issues), len(res), sorted(
                      map(str, issues))))
    if not any(r["natif"]["vide"] for r in res):
        ko.append("TEMOIN INCOMPLET : aucun regime ne fait REFUSER le natif ; le seuil "
                  "MIN_UTILITY = 2 n'est donc pas exerce")
    for r in res:
        n, p, att = r["natif"], r["port"], r["attendu_port"]
        if p["n_cibles"] == 0:
            ko.append("%s : AUCUNE cible eligible cote port -- regime NON EXERCE (1108 est melee, "
                      "le caster doit etre adjacent)" % r["libelle"])
            continue
        if p["top"] != att:
            ko.append("%s : PORT top=%s, attendu %s (topologie de chaine non obtenue)"
                      % (r["libelle"], p["top"], att))
        if bool(n["vide"]) != bool(p["vide"]):
            ko.append("%s : NATIF vide=%s mais PORT vide=%s" % (r["libelle"], n["vide"], p["vide"]))
        if not n["vide"] and n["util"] is not None and float(n["util"]) != float(p["top"]):
            ko.append("%s : NATIF util=%s != PORT top=%s" % (r["libelle"], n["util"], p["top"]))
        if p["top_jumeau"] != p["top"]:
            ko.append("%s : le JUMEAU 1019 rend %s la ou 1108 rend %s sur le MEME contexte -- "
                      "les deux corps natifs sont identiques, les ports doivent l'etre"
                      % (r["libelle"], p["top_jumeau"], p["top"]))
    return ko


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()

    resolve, rpc = _rpc_mod()
    sid = resolve()
    sf = Path(a.state_file).resolve()
    bc = greffer(sf.with_name(sf.stem + "_bc.json"))

    res, rids = [], []
    try:
        for libelle, a_place, attendu in MONTAGES:
            sfi = sf.with_name(sf.stem + "_" + libelle[0] + sf.suffix)
            rid = build(sfi, bc, a.seed, a.board, a_place)
            rids.append(rid)
            print("[940r2] runner %d -- %s" % (rid, libelle))
            res.append(mesurer(rpc, sid, rid, libelle, attendu))
    finally:
        for rid in rids:
            try:
                _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception as e:      # noqa: BLE001 -- un dispose rate ne doit pas masquer le verdict
                print("[940r2] dispose du runner %d KO : %s" % (rid, e))

    ko = verdict(res)
    print("")
    if ko:
        for m in ko:
            print("[940r2] KO : %s" % m)
        print("[940r2] VERDICT : DIVERGENCE (%d)" % len(ko))
        return 1
    print("[940r2] VERDICT : ACCORD sur %d regimes SEPARES par le natif (dont un REFUS)" % len(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
