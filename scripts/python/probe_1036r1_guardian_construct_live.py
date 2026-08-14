"""#1036-r1 -- CONFRONTATION LIVE de `GuardianConstruct_ExtraDamagePct` (1548), en REGIME SEPARANT.

CE QUE CE PROBE MESURE, ET POURQUOI IL LUI FAUT UN CAST.
L'aura 1548 est posee A L'INIT sur la MoW `necroReanimator`, mais son `$$CreateTargetSelector` ne
retient un allie QUE s'il porte un `NanoscarabRepairProtocols` (0x609 = 1545) -- l'effet que la MoW
pose elle-meme en CASTANT son active 1224. Au tour 0, PERSONNE ne le porte : l'aura est presente et
n'accorde rien. Le probe fabrique donc la matiere qu'il mesure -- il CASTE, puis compare.

TROIS DISCRIMINANTS, chacun avec son TEMOIN NON NUL (un accord obtenu sans temoin ne prouve rien) :

  1. `EntitiesWithAnyEffect(..., [NanoscarabRepairProtocols], Both)` -- le MEME allie, AVANT et
     APRES le cast. Le natif (`aiPredict`, preview `GetAllPredictions`) doit MONTER, et le port
     doit passer de `None` a `PercentIncrease`.
  2. `Friends(Owner, AllUnits)` + le meme selecteur -- un allie NON repare, dans le MEME bras et au
     MEME instant : ni le natif ni le port ne doivent rien lui accorder.
  3. `UnitsWithRarity(..., Rarity.Mythic = 5)` -- le bras SEPARANT. ⚠ Le regime par defaut du
     harnais est DEGENERE : `rl_duel build` impose `targetRarity = 5` a toute unite normalisee, donc
     ce gate y est uniformement VRAI et un port qui l'aurait OUBLIE serait d'accord avec le natif
     partout. On en sort par `--unit-stat "<vis>:Rarity=3"` (ecrit APRES la normalisation), et le
     bras separant doit faire TOMBER le bonus -- natif comme port -- tout le reste egal.

L'oracle est le NATIF (`aiPredict`), jamais une constante attendue en dur : le probe compare des
DELTAS de preview, et le port est confronte au meme instant sur le meme etat.

Discipline runner : `--state-file` ABSOLU sous `logs/` du checkout, `--board` EXPLICITE, runners
DISPOSES en sortie sauf `--keep`. ASCII only (cp1252).

Usage :
    python probe_1036r1_guardian_construct_live.py
    python probe_1036r1_guardian_construct_live.py --niveau 4 --keep
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import rl_duel as R                                                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType               # noqa: E402
from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.entities.rarity import Rarity                                       # noqa: E402
from engine.runner import damage_model as DM                                    # noqa: E402

BOARD = "MC1_67"
SEED = 777
MOW = "necroReanimator"
MYTHIC = "GuardianConstruct"
#: `EffectType` 0x60c = 1548 -- l'owner-effect que `GuardianConstructAbility` pose a l'init.
AURA = EffectType.GuardianConstruct_ExtraDamagePct
#: `ActiveAbilityType` 1224 -- l'active de la MoW qui pose `NanoscarabRepairProtocols` (1545) sur sa
#: CIBLE (`AddEffect(0x609, source = Owner, targets = Target@<DSLSelectors+0x60>)`, LU au decompile).
REPAIR_ABILITY = ActiveAbilityType.NanoscarabRepairProtocols
REPAIR_EFFECT = EffectType.NanoscarabRepairProtocols
#: Palier de la mythique (1..4) -- `extraDmgPct = [10, 13, 16, 20]`, dans
#: `variablesAffectedByRarityBonus`. `TertiaryAbilityLevel >= 1` est un VERROU du montage (case-237).
NIVEAU = 4
RARETE_SEPARANTE = int(Rarity.Epic)      # 3, distinct du `Mythic` (5) que le harnais impose


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


class _Session:
    """Le couple (session, runner) et les RPC, groupes pour que `finally` puisse toujours disposer."""

    def __init__(self, rid: int):
        import rl_collect_batch as B                                            # noqa: PLC0415
        self._B = B
        self.sid = B._resolve_session()
        self.rid = int(rid)

    def rpc(self, method, body=None, timeout=90):
        b = dict(body or {})
        b.setdefault("runnerId", self.rid)
        return _unwrap(self._B._rpc(self.sid, method, [b], timeout=timeout)) or {}

    def dispose(self):
        try:
            self._B._rpc(self.sid, "disposeRunner", [{"runnerId": self.rid}], timeout=20)
        except Exception:                    # un teardown qui leve masquerait le verdict
            pass


def _build(rarity_vis: "str | None", rarity: int, niveau: int, seed: int, board: str,
           verbose: bool) -> _Session:
    """Monte UN bras. `rarity_vis` non nul -> bras SEPARANT (le VisualId vise descend a `rarity`).

    ⚠ MEME VOIE DE BUILD que les probes #999-r3 : la CLI par `R.main(argv)`, jamais un `Namespace`
    fabrique a la main -- un jeu de defauts recopie se perime des qu'une option est ajoutee."""
    nom = "degenere" if rarity_vis is None else ("separant_%s_%d" % (rarity_vis, rarity))
    sf = Path(__file__).resolve().parents[2] / "logs" / ("probe1036r1_%s.json" % nom)
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = ["build", "--seed", str(int(seed)), "--board", str(board), "--p-mow", MOW,
            "--equip-mythic", "%s:%s:%d" % (MOW, MYTHIC, int(niveau))]
    if rarity_vis:
        argv += ["--unit-stat", "%s:Rarity=%d" % (rarity_vis, int(rarity))]
    argv += ["--state-file", str(sf)]
    if verbose:
        print("[1036-r1] build %s" % " ".join(argv))
    if R.main(argv) != 0:
        raise RuntimeError("build ECHOUE (bras=%s) : %s" % (nom, " ".join(argv)))
    rid = json.loads(sf.read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        raise RuntimeError("build sans runnerId (bras=%s) : %s" % (nom, sf))
    return _Session(rid)


def _state(s: _Session):
    from engine.runner.snapshot import load_state                               # noqa: PLC0415
    dv = s.rpc("decisionView", {"includeInactive": True})
    cs = s.rpc("combatSnapshot", {})
    ob = s.rpc("observeBattle", {}, 40)
    return load_state(dv, ob, cs), dv, cs


#: Niveau d'ability FOURNI au bras de mesure du GATE. ⚠ Il n'est PAS mesure : sur un runner LIVE,
#: aucun canal ne publie l'`AbilityState` d'une mythique de MoW (`unitConfig` est en erreur pour
#: toute Machine, `abilityStates` ne liste que ses ACTIVES) -- residu `#1036-r8`, `BLOCAGE: capteur`.
#: Le fournir NEUTRALISE la magnitude pour que le probe mesure ce qu'il PEUT mesurer : le GATE.
#: La magnitude, elle, reste NON CONFRONTEE, et c'est ecrit tel quel dans le verdict.
NIVEAU_FOURNI_POUR_LE_GATE = 4


def _port_bonus(state, att_id: int, tgt_id: int, niveau_fourni: "int | None" = None):
    """Ce que le PORT accorde a `att_id` par le canal AURA ATTAQUE, capte par INTERCEPTION du foyer
    REEL (forme B : `damage_model` lie ce symbole au niveau module, donc remplacer l'attribut du
    module MORD). On ne RECOPIE pas la boucle : un mirror mesurerait le code du probe.

    `niveau_fourni` substitue le SEUL canal muet (`tertiary_ability_state_of`) -- les gates, eux,
    restent evalues sur les valeurs LIVE du ctx (`att_rarity`, `att_effect_names`, porteurs)."""
    vus = []
    reel = DM.aura_attack_damage_bonus_from_allies

    def _spy(carriers, ctx):
        if niveau_fourni is not None:
            ctx = dict(ctx)
            ctx["tertiary_ability_state_of"] = lambda _uid, _ab: (int(niveau_fourni), 100)
        out = reel(carriers, ctx)
        vus.append({"porteurs": [c[0] for c in (carriers or [])],
                    "att_rarity": ctx.get("att_rarity"),
                    "att_effect_names": sorted(ctx.get("att_effect_names") or []),
                    "bonus": [(b.kind, b.value) for b in out]})
        return out

    DM.aura_attack_damage_bonus_from_allies = _spy
    try:
        DM.attacker_modifiers(state, att_id, None, is_ranged=False, target_id=tgt_id)
    finally:
        DM.aura_attack_damage_bonus_from_allies = reel
    return vus[0] if vus else None


def _predict(s: _Session, att_id: int, tgt_id: int, tuile=None):
    """Preview NATIVE du degat (`aiPredict` -> `GetAllPredictions`), depuis la TUILE CANDIDATE.

    ⚠ Le natif rend `pred: null` + `err: "get_Item: system error"` quand la cible n'est pas a
    portee depuis la tuile evaluee -- ce n'est pas une panne, c'est << aucune attaque possible >>.
    On passe donc `col`/`row` explicitement (le probe DEPLACE l'evaluation plutot que de subir la
    geometrie de spawn), et on rend le dict tel quel : c'est l'appelant qui juge."""
    body = {"unitId": int(att_id), "targetId": int(tgt_id)}
    if tuile is not None:
        body["col"], body["row"] = int(tuile[0]), int(tuile[1])
    r = s.rpc("aiPredict", body, 60)
    return {"pred": r.get("pred"), "err": r.get("err"), "tuile": tuile}


def _degat(p) -> "tuple | None":
    """`(min, max)` d'une preview native, ou `None` si le natif n'a rien predit."""
    d = (p or {}).get("pred")
    if not isinstance(d, dict):
        return None
    for cmin, cmax in (("healthDamageMin", "healthDamageMax"), ("damageMin", "damageMax"),
                       ("min", "max")):
        if cmin in d:
            return (d.get(cmin), d.get(cmax))
    return tuple(sorted(v for v in d.values() if isinstance(v, (int, float)))[-2:]) or None


def _tuiles_de_tir(s: _Session, att_id: int, tgt_id: int, dv) -> list:
    """Tuiles LIBRES depuis lesquelles le natif predit reellement un degat sur `tgt_id`.

    On ne se plaint PAS de la geometrie de spawn : on ENUMERE les voisins de la cible (canal
    `boardGraph`) et on garde ceux ou la preview repond. Sans cela, `aiPredict` rendrait
    `pred: null` au spawn et le probe conclurait << pas de bonus >> pour une raison de PORTEE."""
    g = s.rpc("boardGraph", {}, 60)
    tuiles = g.get("tiles") or []
    par_id = {t.get("id"): t for t in tuiles}
    occupees = {(u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or [])
                if u.get("alive") and u.get("pos")}
    cible = next((u for u in (dv.get("units") or []) if u["id"] == tgt_id), None)
    if cible is None or not cible.get("pos"):
        return []
    tc = next((t for t in tuiles
               if t.get("col") == cible["pos"]["col"] and t.get("row") == cible["pos"]["row"]), None)
    if tc is None:
        return []
    out = []
    for nid in (tc.get("neighbours") or tc.get("neighbors") or []):
        t = par_id.get(nid)
        if t is None or (t.get("col"), t.get("row")) in occupees:
            continue
        out.append((t["col"], t["row"]))
    return out


def _lignes(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")]


def _cibles_legales(s: _Session, caster_id: int) -> set:
    """Ids que le NATIF accepte pour `NanoscarabRepairProtocols` (`abilityTargets` -> `targets`,
    move inclus). C'est l'oracle du ciblage : on ne devine pas quelle unite est reparable."""
    r = s.rpc("abilityTargets", {"unitId": int(caster_id),
                                 "abilityType": int(REPAIR_ABILITY)}, 90)
    out = set()
    # ⚠ DEUX pieges de forme, tous deux mesures : les listes vivent sous
    # `units[].abilities[].{targets,fromHere}` (rien a la RACINE), et la cle d'une cible UNITE est
    # `targetId`, PAS `id`. Chacun des deux, seul, rend un ensemble VIDE -- qui se confondrait avec
    # << aucune cible legale >>, c.-a-d. avec un montage impossible.
    for u in (r.get("units") or []):
        if int(u.get("unitId", -1)) != int(caster_id):
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId", -1)) != int(REPAIR_ABILITY):
                continue
            for cle in ("targets", "fromHere"):
                for t in (ab.get(cle) or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        out.add(int(t["targetId"]))
    return out


def _mesure_bras(s: _Session, rarity_vis: "str | None", verbose: bool) -> dict:
    f: dict = {"runnerId": s.rid, "rarity_vis": rarity_vis}
    dv = s.rpc("decisionView", {"allAbilities": True, "includeInactive": True})
    mow = next((m for m in (dv.get("mows") or []) if m.get("visualId") == MOW), None)
    if mow is None:
        raise RuntimeError("la MoW %r n'est pas dans decisionView.mows : %r"
                           % (MOW, [m.get("visualId") for m in (dv.get("mows") or [])]))
    mid, team = int(mow["casterId"]), mow.get("team")
    f["mow_id"] = mid
    f["mow_effets"] = [e.get("name") for e in (mow.get("effects") or []) if e.get("name")]
    f["aura_publiee"] = AURA.name in f["mow_effets"]
    if not f["aura_publiee"]:
        raise RuntimeError("montage DEGENERE : la MoW ne porte pas %r (publie : %r)"
                           % (AURA.name, f["mow_effets"]))

    allies = [u for u in _lignes(dv) if u.get("team") == team]
    ennemis = [u for u in _lignes(dv) if u.get("team") != team]
    if len(allies) < 2 or not ennemis:
        raise RuntimeError("montage DEGENERE : %d allie(s), %d ennemi(s) vivants"
                           % (len(allies), len(ennemis)))
    # La CIBLE de la reparation est celle que le NATIF accepte (`abilityTargets`), jamais un allie
    # choisi au hasard : `NanoscarabRepairProtocols` a son propre masque de ciblage, et le premier
    # allie de la liste n'y est pas forcement (mesure : 1 seule cible legale sur 5 allies).
    legales = _cibles_legales(s, mid)
    f["cibles_legales"] = sorted(legales)
    candidats = [u for u in allies if u["id"] in legales]
    if not candidats:
        raise RuntimeError("aucune cible legale de %s parmi les allies : legales=%r allies=%r"
                           % (REPAIR_ABILITY.name, sorted(legales), [u["id"] for u in allies]))
    if rarity_vis:
        cible = next((u for u in candidats if u.get("visualId") == rarity_vis), None)
        if cible is None:
            raise RuntimeError("le VisualId separant %r n'est plus une cible legale : %r"
                               % (rarity_vis, [(u["id"], u.get("visualId")) for u in candidats]))
    else:
        cible = candidats[0]
    temoin = next((u for u in allies if u["id"] != cible["id"]), None)
    ennemi = ennemis[0]
    f["repare_id"], f["repare_vis"] = cible["id"], cible.get("visualId")
    f["temoin_id"], f["temoin_vis"] = temoin["id"], temoin.get("visualId")
    f["ennemi_id"] = ennemi["id"]

    # --- AVANT le cast : personne ne porte 1545, l'aura ne doit rien accorder -----------------
    from engine.runner.components import StatsComponent                         # noqa: PLC0415
    st, _dv, _cs = _state(s)
    _sc = st.get_entity(cible["id"]).get_component(StatsComponent)
    _r = getattr(getattr(_sc, "ctx", None), "rarity", None)
    f["rarete_reparee_avant"] = None if _r is None else int(_r)
    # La TUILE DE TIR est choisie une fois pour toutes : le MEME point d'evaluation servira avant
    # et apres le cast, sinon la comparaison melangerait la geometrie et le bonus.
    f["tuile"] = None
    f["tuiles_candidates"] = _tuiles_de_tir(s, cible["id"], ennemi["id"], dv)
    for t in f["tuiles_candidates"]:
        p = _predict(s, cible["id"], ennemi["id"], t)
        if _degat(p) is not None:
            f["tuile"], f["pred_avant"] = t, p
            break
    else:
        f["pred_avant"] = _predict(s, cible["id"], ennemi["id"])
    f["port_avant"] = _port_bonus(st, cible["id"], ennemi["id"], NIVEAU_FOURNI_POUR_LE_GATE)

    # --- le CAST : la MoW repare la cible ------------------------------------------------------
    for _ in range(12):
        r = s.rpc("applyAction", {"action": {"kind": "ability", "casterId": mid,
                                             "abilityType": int(REPAIR_ABILITY),
                                             "targetId": int(cible["id"])}}, 90)
        dv2 = s.rpc("decisionView", {"includeInactive": True})
        ligne = next((u for u in (dv2.get("units") or []) if u["id"] == cible["id"]), {})
        noms = [e.get("name") for e in (ligne.get("effects") or []) if e.get("name")]
        if REPAIR_EFFECT.name in noms:
            f["cast_ok"], f["effets_repare"] = True, noms
            break
        f["dernier_applyAction"] = json.dumps(r)[:200]
        s.rpc("applyAction", {"action": {"kind": "endturn"}}, 90)
    else:
        raise RuntimeError("le cast de %s n'a jamais pose %s sur l'allie %s (dernier retour : %s)"
                           % (REPAIR_ABILITY.name, REPAIR_EFFECT.name, cible["id"],
                              f.get("dernier_applyAction")))

    # --- APRES le cast : le MEME allie, et un TEMOIN non repare --------------------------------
    st2, dv3, _cs2 = _state(s)
    f["pred_apres"] = _predict(s, cible["id"], ennemi["id"], f["tuile"])
    f["port_apres"] = _port_bonus(st2, cible["id"], ennemi["id"], NIVEAU_FOURNI_POUR_LE_GATE)
    f["pred_temoin"] = _predict(s, temoin["id"], ennemi["id"], f["tuile"])
    f["port_temoin"] = _port_bonus(st2, temoin["id"], ennemi["id"], NIVEAU_FOURNI_POUR_LE_GATE)
    f["temoin_effets"] = [e.get("name") for e in
                          (next((u for u in (dv3.get("units") or []) if u["id"] == temoin["id"]),
                                {}).get("effects") or []) if e.get("name")]
    if verbose:
        print(json.dumps(f, indent=1, default=str))
    return f


def _bonus_pct(mesure) -> "int | None":
    """Le `PercentIncrease` que le port a verse, ou `None` s'il n'a rien verse."""
    if not mesure:
        return None
    for kind, val in (mesure.get("bonus") or []):
        if kind == "PercentIncrease":
            return int(val)
    return None


def run(niveau: int = NIVEAU, seed: int = SEED, board: str = BOARD, keep: bool = False,
        verbose: bool = True) -> dict:
    res: dict = {"niveau": niveau, "seed": seed, "board": board}
    s1 = _build(None, RARETE_SEPARANTE, niveau, seed, board, verbose)
    try:
        res["degenere"] = _mesure_bras(s1, None, verbose=False)
    finally:
        if not keep:
            s1.dispose()
    vis = res["degenere"].get("repare_vis")
    s2 = _build(vis, RARETE_SEPARANTE, niveau, seed, board, verbose)
    try:
        res["separant"] = _mesure_bras(s2, vis, verbose=False)
    finally:
        if not keep:
            s2.dispose()
    if verbose:
        _print(res)
    return res


def _print(res: dict) -> None:
    d, sep = res["degenere"], res["separant"]
    print("=== #1036-r1 LIVE : %s / %s (palier %d) ===" % (MOW, MYTHIC, res["niveau"]))
    for nom, f in (("BRAS DEGENERE (tout Mythic)", d), ("BRAS SEPARANT (%s -> Epic)"
                                                        % sep.get("rarity_vis"), sep)):
        print("-- %s" % nom)
        print("   MoW %s, aura publiee            : %s" % (f["mow_id"], f["aura_publiee"]))
        print("   allie REPARE                    : %s (%s), rarete mesuree = %s"
              % (f["repare_id"], f["repare_vis"], f.get("rarete_reparee_avant")))
        print("   tuile de tir evaluee            : %s" % (f.get("tuile"),))
        print("   natif degat AVANT / APRES       : %s -> %s"
              % (_degat(f["pred_avant"]), _degat(f["pred_apres"])))
        print("   port  bonus AVANT / APRES       : %s -> %s"
              % (_bonus_pct(f["port_avant"]), _bonus_pct(f["port_apres"])))
        print("   temoin NON repare %s (%s)       : natif %s, port %s"
              % (f["temoin_id"], f["temoin_vis"], _degat(f["pred_temoin"]),
                 _bonus_pct(f["port_temoin"])))
        print("   effets de l'allie repare        : %s" % (f.get("effets_repare"),))
        print("   ctx d'aura vu par le port APRES : %s" % (f.get("port_apres"),))
        print("   err natif AVANT / APRES         : %s / %s"
              % ((f.get("pred_avant") or {}).get("err"), (f.get("pred_apres") or {}).get("err")))
        print("   tuiles de tir candidates        : %s" % (f.get("tuiles_candidates"),))


def verdict(res: dict) -> bool:
    d, sep = res.get("degenere") or {}, res.get("separant") or {}
    return bool(
        _bonus_pct(d.get("port_avant")) is None            # gate EntitiesWithAnyEffect : ferme
        and _bonus_pct(d.get("port_apres")) is not None    # ... et ouvert apres le cast
        and _bonus_pct(d.get("port_temoin")) is None       # ... et ferme pour le NON repare
        and _bonus_pct(sep.get("port_apres")) is None      # gate UnitsWithRarity : ferme en Epic
        and sep.get("rarete_reparee_avant") == RARETE_SEPARANTE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--niveau", type=int, default=NIVEAU)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true", help="ne PAS disposer les runners")
    a = ap.parse_args()
    res = run(niveau=a.niveau, seed=a.seed, board=a.board, keep=a.keep, verbose=True)
    print()
    if verdict(res):
        print("VERDICT: les TROIS gates discriminent LIVE (effet repair, temoin, rarete separante).")
        return 0
    print("VERDICT: un gate ne discrimine PAS -- re-lire la ventilation ci-dessus.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
