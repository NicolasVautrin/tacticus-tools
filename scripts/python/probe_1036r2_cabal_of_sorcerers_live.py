"""#1036-r2 -- CONFRONTATION LIVE de `CabalOfSorcerers_ExtraDamagePct` (1494), en REGIME SEPARANT.

CE QUE CE PROBE MESURE. L'aura 1494 est posee A L'INIT sur la MoW `thousDaemonPrince`, et son
`$$CreateTargetSelector` retient, quand le porteur est une MACHINE (branche `F` du
`ConditionalSelector(IsMachine(Owner), ...)`), les allies **Mythic + Psyker + Hero** qui ont
eux-memes un tel allie **ADJACENT**. Le probe DEPLACE les unites pour fabriquer cette adjacence --
il ne subit pas la geometrie de spawn -- puis compare les quatre conjoints, chacun avec son
TEMOIN NON NUL :

  1. le filtre `F` (`AmountIsGreaterThanZero(ValidCharacter(AdjacentFriends(It)))`) -- le MEME
     psyker, AVANT et APRES le rapprochement. Le port doit passer de `None` a `PercentIncrease` ;
  2. `CurrentAttackDamageProfileIs(DamageProfileType.Psychic = 0xd)` -- le MEME instant, le MEME
     attaquant, un profil de degat NON Psychic : rien ne doit etre accorde ;
  3. `UnitsWithTraits([Psyker, Hero])` -- un allie adjacent NON Psyker : le gate se ferme, alors
     que la geometrie, elle, est identique ;
  4. `UnitsWithRarity(..., Rarity.Mythic = 5)` -- le bras SEPARANT. ⚠ Le regime par defaut du
     harnais est DEGENERE (`rl_duel build` impose `targetRarity = 5`) : un port qui aurait OUBLIE ce
     gate y serait d'accord avec le natif partout. On en sort par `--unit-stat "<vis>:Rarity=3"`.

CE QUI N'EST **PAS** COUVERT, et c'est MESURE (residu `#1036-r8`, `BLOCAGE: capteur`) : la
MAGNITUDE face au natif. Sur un runner LIVE, aucun canal ne publie l'`AbilityState` d'une mythique
de MoW -- `combatSnapshot.units[].unitConfig` rend `{"error": "visualId introuvable"}` pour toute
Machine et `abilityStates` ne liste que ses ACTIVES. Le probe FOURNIT donc un niveau pour
neutraliser la magnitude et mesurer ce qu'il PEUT mesurer : le GATE.

Discipline runner : `--state-file` ABSOLU sous `logs/`, `--board` EXPLICITE, runners DISPOSES en
sortie sauf `--keep`. ASCII only (cp1252).

Usage :
    python probe_1036r2_cabal_of_sorcerers_live.py
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
from engine.entities.damage_profile_type import DamageProfileType               # noqa: E402
from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.entities.rarity import Rarity                                       # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                         # noqa: E402
from engine.runner import damage_model as DM                                    # noqa: E402

BOARD = "MC1_67"
SEED = 777
MOW = "thousDaemonPrince"
MYTHIC = "CabalOfSorcerers"
AURA = EffectType.CabalOfSorcerers_ExtraDamagePct
#: DEUX psykers `lineup` (donc porteurs de `UnitTrait.Hero`) + un NON psyker qui sert de temoin de
#: l'etage `UnitsWithTraits` : la geometrie sera la meme, seul le trait changera.
PSYKERS = ("eldarFarseer", "genesMagus")
NON_PSYKER = "ultraTitus"
NIVEAU = 4
RARETE_SEPARANTE = int(Rarity.Epic)
#: cf. `probe_1036r1_guardian_construct_live.py` : le niveau n'est PAS mesurable live sur une MoW
#: (residu `#1036-r8`). Le fournir isole le GATE ; la magnitude reste NON CONFRONTEE.
NIVEAU_FOURNI_POUR_LE_GATE = 4


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


class _Session:
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
        except Exception:
            pass


def _build(rarity_vis: "str | None", seed: int, board: str, niveau: int, verbose: bool) -> _Session:
    nom = "degenere" if rarity_vis is None else ("separant_%s" % rarity_vis)
    sf = Path(__file__).resolve().parents[2] / "logs" / ("probe1036r2_%s.json" % nom)
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = ["build", "--seed", str(int(seed)), "--board", str(board), "--p-mow", MOW,
            "--equip-mythic", "%s:%s:%d" % (MOW, MYTHIC, int(niveau)),
            "--p-units", ",".join(PSYKERS + (NON_PSYKER,))]
    if rarity_vis:
        argv += ["--unit-stat", "%s:Rarity=%d" % (rarity_vis, RARETE_SEPARANTE)]
    argv += ["--state-file", str(sf)]
    if verbose:
        print("[1036-r2] build %s" % " ".join(argv))
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


def _port(state, att_id: int, tgt_id: int, profil: str):
    """Ce que le PORT accorde a `att_id`, par INTERCEPTION du foyer REEL (forme B). Le niveau
    d'ability est FOURNI (cf. `NIVEAU_FOURNI_POUR_LE_GATE`) : on mesure le GATE, pas la magnitude."""
    vus = []
    reel = DM.aura_attack_damage_bonus_from_allies

    def _spy(carriers, ctx):
        ctx = dict(ctx)
        ctx["tertiary_ability_state_of"] = lambda _u, _a: (NIVEAU_FOURNI_POUR_LE_GATE, 100)
        out = reel(carriers, ctx)
        vus.append({"porteurs": [c[0] for c in (carriers or [])],
                    "att_rarity": ctx.get("att_rarity"),
                    "att_traits": sorted(ctx.get("att_traits") or []),
                    "damage_profile": ctx.get("damage_profile"),
                    "owner_is_machine": ctx.get("owner_is_machine"),
                    "voisins_valides": ctx.get("cabal_valid_adjacent_to_attacker"),
                    "bonus": [(b.kind, b.value) for b in out]})
        return out

    DM.aura_attack_damage_bonus_from_allies = _spy
    try:
        DM.attacker_modifiers(state, att_id, None, is_ranged=False, target_id=tgt_id,
                              damage_profile=profil)
    finally:
        DM.aura_attack_damage_bonus_from_allies = reel
    return vus[0] if vus else None


def _pct(m) -> "int | None":
    for kind, val in ((m or {}).get("bonus") or []):
        if kind == "PercentIncrease":
            return int(val)
    return None


def _lignes(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")]


def _pos(u):
    return (u["pos"]["col"], u["pos"]["row"])


def _rapproche(s: _Session, mobile: int, ancre_pos, verbose: bool) -> bool:
    """DEPLACE `mobile` sur une tuile ADJACENTE a `ancre_pos` -- on FORCE la configuration au lieu
    de se plaindre de la geometrie de spawn. Rend True si l'adjacence est atteinte."""
    import hexgeo                                                               # noqa: PLC0415
    g = s.rpc("boardGraph", {}, 60)
    dv = s.rpc("decisionView", {})
    occ = {_pos(u) for u in _lignes(dv)}
    cands = sorted(((t["col"], t["row"]) for t in (g.get("tiles") or [])
                    if t.get("walkable") and (t["col"], t["row"]) not in occ),
                   key=lambda p: hexgeo.distance(p, ancre_pos))
    for (c, r) in cands[:10]:
        s.rpc("applyAction", {"action": {"kind": "move", "unitId": int(mobile),
                                         "to": {"col": c, "row": r}}}, 90)
        dv2 = s.rpc("decisionView", {})
        u = next((x for x in _lignes(dv2) if x["id"] == mobile), None)
        if u is not None and hexgeo.distance(_pos(u), ancre_pos) == 1:
            if verbose:
                print("[1036-r2] u%d deplace en (%d,%d), adjacent a %s" % (mobile, c, r, ancre_pos))
            return True
    return False


def _mesure(s: _Session, rarity_vis: "str | None", verbose: bool) -> dict:
    f: dict = {"runnerId": s.rid, "rarity_vis": rarity_vis}
    dv = s.rpc("decisionView", {"includeInactive": True, "allAbilities": True})
    mow = next((m for m in (dv.get("mows") or []) if m.get("visualId") == MOW), None)
    if mow is None:
        raise RuntimeError("MoW %r absente de decisionView.mows : %r"
                           % (MOW, [m.get("visualId") for m in (dv.get("mows") or [])]))
    f["mow_id"], team = int(mow["casterId"]), mow.get("team")
    f["mow_effets"] = [e.get("name") for e in (mow.get("effects") or []) if e.get("name")]
    if AURA.name not in f["mow_effets"]:
        raise RuntimeError("montage DEGENERE : la MoW ne porte pas %r (publie %r)"
                           % (AURA.name, f["mow_effets"]))
    allies = [u for u in _lignes(dv) if u.get("team") == team]
    ennemis = [u for u in _lignes(dv) if u.get("team") != team]
    psy = [u for u in allies if u.get("visualId") in PSYKERS]
    autre = next((u for u in allies if u.get("visualId") == NON_PSYKER), None)
    if len(psy) < 2 or autre is None or not ennemis:
        raise RuntimeError("montage DEGENERE : psykers=%r, non-psyker=%r, ennemis=%d"
                           % ([u.get("visualId") for u in psy],
                              autre and autre.get("visualId"), len(ennemis)))
    att, voisin, ennemi = psy[0], psy[1], ennemis[0]
    f["att_id"], f["att_vis"] = att["id"], att.get("visualId")
    f["voisin_id"], f["voisin_vis"] = voisin["id"], voisin.get("visualId")
    f["ennemi_id"] = ennemi["id"]

    # --- AVANT rapprochement : les deux psykers sont loin -> le filtre `F` doit se taire --------
    st, _dv, _cs = _state(s)
    f["avant"] = _port(st, att["id"], ennemi["id"], DamageProfileType.Psychic.name)

    # --- on FABRIQUE l'adjacence ---------------------------------------------------------------
    f["rapproche"] = _rapproche(s, voisin["id"], _pos(att), verbose)
    st2, dv2, _cs2 = _state(s)
    f["apres"] = _port(st2, att["id"], ennemi["id"], DamageProfileType.Psychic.name)
    # --- meme instant, meme geometrie : le PROFIL change ---------------------------------------
    f["profil_non_psychic"] = _port(st2, att["id"], ennemi["id"], "Physical")
    # --- meme instant, meme geometrie : un attaquant NON psyker ---------------------------------
    f["non_psyker"] = _port(st2, autre["id"], ennemi["id"], DamageProfileType.Psychic.name)
    f["non_psyker_traits"] = sorted(DM.target_trait_names(st2, autre["id"]) or ())
    return f


def run(seed: int = SEED, board: str = BOARD, niveau: int = NIVEAU, keep: bool = False,
        verbose: bool = True) -> dict:
    res: dict = {"seed": seed, "board": board, "niveau": niveau}
    s1 = _build(None, seed, board, niveau, verbose)
    try:
        res["degenere"] = _mesure(s1, None, verbose)
    finally:
        if not keep:
            s1.dispose()
    vis = res["degenere"]["att_vis"]
    s2 = _build(vis, seed, board, niveau, verbose)
    try:
        res["separant"] = _mesure(s2, vis, verbose)
    finally:
        if not keep:
            s2.dispose()
    if verbose:
        _print(res)
    return res


def _print(res: dict) -> None:
    print("=== #1036-r2 LIVE : %s / %s (palier %d) ===" % (MOW, MYTHIC, res["niveau"]))
    for nom, f in (("BRAS DEGENERE (tout Mythic)", res["degenere"]),
                   ("BRAS SEPARANT (%s -> Epic)" % res["separant"].get("rarity_vis"),
                    res["separant"])):
        print("-- %s" % nom)
        print("   MoW %s, aura publiee           : %s"
              % (f["mow_id"], AURA.name in f["mow_effets"]))
        print("   attaquant psyker               : u%s (%s)" % (f["att_id"], f["att_vis"]))
        print("   adjacence FABRIQUEE            : %s (u%s %s)"
              % (f["rapproche"], f["voisin_id"], f["voisin_vis"]))
        print("   port AVANT / APRES             : %s -> %s"
              % (_pct(f["avant"]), _pct(f["apres"])))
        print("   ... profil non Psychic         : %s" % _pct(f["profil_non_psychic"]))
        print("   ... attaquant NON psyker       : %s (traits %s)"
              % (_pct(f["non_psyker"]), f["non_psyker_traits"][:6]))
        print("   ctx APRES                      : %s" % (f["apres"],))


def verdict(res: dict) -> bool:
    d, sep = res.get("degenere") or {}, res.get("separant") or {}
    return bool(
        d.get("rapproche")                                  # le montage a bien FABRIQUE l'adjacence
        and _pct(d.get("avant")) is None                    # filtre F : ferme sans voisin qualifie
        and _pct(d.get("apres")) is not None                # ... ouvert des que l'adjacence existe
        and _pct(d.get("profil_non_psychic")) is None       # CurrentAttackDamageProfileIs(Psychic)
        and _pct(d.get("non_psyker")) is None               # UnitsWithTraits([Psyker, Hero])
        and _pct(sep.get("apres")) is None                  # UnitsWithRarity(..., Mythic)
        and (sep.get("apres") or {}).get("att_rarity") == Rarity.Epic)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--niveau", type=int, default=NIVEAU)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    res = run(seed=a.seed, board=a.board, niveau=a.niveau, keep=a.keep, verbose=True)
    print()
    if verdict(res):
        print("VERDICT: les QUATRE gates de 1494 discriminent LIVE (voisinage, profil, traits,")
        print("         rarete separante). La MAGNITUDE reste NON CONFRONTEE (#1036-r8).")
        return 0
    print("VERDICT: un gate ne discrimine PAS -- re-lire la ventilation ci-dessus.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
