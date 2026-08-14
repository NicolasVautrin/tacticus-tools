"""#999-r3-r1 -- CONFRONTATION LIVE du FOYER de rarete, en REGIME SEPARANT.

CE QUE CE PROBE MESURE, ET POURQUOI IL NE PEUT PAS SE JOUER DANS LE REGIME PAR DEFAUT.
`rl_duel build` impose `targetRarity = 5` : les dix unites rendent `Rarity.Mythic`, donc un port
qui aurait OUBLIE le gate `HasRarity(Caster, Mythic)` serait d'accord avec le natif partout. Un vert
obtenu la est VIDE. Le montage passe donc par `probe_999r3_regime_separant_rarete` (#999-r3), qui
REFUSE de rendre un bras separant qui ne separe pas.

DEUX ETAGES, et le second est celui qui compte :

  1. TRAVERSEE -- les trois cles de rarete que #999-r3-r1 pose (`att_rarity` du canal aura ATTAQUE,
     `tgt_rarity` du canal aura DEFENSE, `rarity` du canal self DEFENSEUR) portent bien, sur un
     etat LIVE, la valeur SEPAREE. Mesuree en INTERCEPTANT le foyer reel (`damage_model`), jamais
     en recopiant sa construction.
  2. DISCRIMINATION -- le gate de `HyperCorrosiveAcid_ExtraDamagePct` (1448) rend un verdict
     DIFFERENT selon la rarete de l'attaquant, TOUT LE RESTE EGAL. C'est pour ca que le bras
     separant vise un HEROS : les deux attaquants compares portent le trait `Hero` et sont tous
     deux allies de la source de l'effet -- seule la rarete change. Sans cette precaution, un
     verdict different s'expliquerait aussi bien par le conjoint `HasTrait(Caster, Hero)`.

CE QUI N'EST **PAS** COUVERT ICI : la MAGNITUDE de 1448 confrontee au natif. Elle exigerait que
l'effet soit REELLEMENT pose en bataille -- donc une Spore Mine (`tyranSmnSporeMine`) amie du
Biovore qui blesse un ennemi -- puis une preview `aiPredict` avec et sans. Le montage est ecrit
dans la case-doc ; il n'a pas ete joue. Un A/B par REJEU de combat ne separerait rien (le tirage
consomme le RNG differemment selon les modificateurs).

Usage :
    python probe_999r3r1_ctx_rarete_live.py [--vis <heros>] [--rarity 3] [--seed 777] [--board MC1_67]

ASCII only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import probe_999r3_regime_separant_rarete as RAR                                # noqa: E402
from engine.entities.rarity import Rarity                                       # noqa: E402
from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                         # noqa: E402
from engine.runner import damage_model as DM                                    # noqa: E402
from engine.runner.components import OwnerComponent, StatsComponent             # noqa: E402

ACID = EffectType.HyperCorrosiveAcid_ExtraDamagePct
PALIERS_EXTRA_DMG_PCT = [10, 13, 16, 20]        # gameconfig `HyperCorrosiveAcid.extraDmgPct`


def _rpc_state(runner_id: int):
    """`State` charge des TROIS canaux live du runner (le meme triple que `RAR.run`)."""
    import rl_collect_batch as B                                                # noqa: PLC0415
    from engine.runner.snapshot import load_state                               # noqa: PLC0415
    sid = B._resolve_session()
    # #1074 -- LE CANAL EST DEMANDE. Ce probe charge un runner monte par `RAR.run` (donc par
    # `rl_duel build`, dont `--equip-mythic` / `--equip-relic` / `--graft-*` ecrivent les trois
    # cles que le port ne lit QUE par `unitAbilityStates`), et il ne peut pas savoir si l'appelant
    # a greffe. Sans transport ambiant, `load_state` ci-dessous rend `source == "no-transport"` :
    # le `UnitContext` arrive prive de ses abilities, et toute lecture qui en depend mesure un
    # NEANT en VERT (#448-r3-r1).
    B.bind_ambient_rpc(sid)

    def rpc(method, body, timeout=90):
        r = B._rpc(sid, method, [body], timeout=timeout)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}

    cs = rpc("combatSnapshot", {"runnerId": runner_id}, 90)
    dv = rpc("decisionView", {"runnerId": runner_id, "maxRank": 1}, 90)
    ob = rpc("observeBattle", {"runnerId": runner_id}, 40)
    return load_state(dv, ob, cs), dv, cs


def _heroes(state):
    """`{uid: (team, rarity)}` des unites VIVANTES portant `UnitTrait.Hero`, rarete MESUREE."""
    out = {}
    for uid, ent in state.entities.items():
        sc = ent.get_component(StatsComponent)
        oc = ent.get_component(OwnerComponent)
        if sc is None or oc is None:
            continue
        traits = DM.target_trait_names(state, uid) or frozenset()
        if UnitTrait.Hero.name not in traits:
            continue
        out[int(uid)] = (oc.team, getattr(sc.ctx, "rarity", None))
    return out


def _ctx_rarity_keys(state, att_id: int, tgt_id: int):
    """Les TROIS cles, captees par INTERCEPTION du foyer reel (forme B : `damage_model` lie ces
    symboles au niveau module, donc remplacer l'attribut du module MORD)."""
    vus = {}

    def _spy(nom, cle_ctx, appel):
        reel = getattr(DM, nom)

        def _f(*a, **kw):
            ctx = a[1] if len(a) > 1 and isinstance(a[1], dict) else kw.get("attacker_ctx")
            if isinstance(ctx, dict) and cle_ctx in ctx:
                vus.setdefault(cle_ctx, ctx[cle_ctx])
            return reel(*a, **kw)

        setattr(DM, nom, _f)
        try:
            appel()
        finally:
            setattr(DM, nom, reel)

    _spy("aura_attack_damage_bonus_from_allies", "att_rarity",
         lambda: DM.attacker_modifiers(state, att_id, None, is_ranged=False, target_id=tgt_id))
    _spy("aura_defense_damage_malus_from_units", "tgt_rarity",
         lambda: DM.defender_modifiers(state, tgt_id, None, is_melee=True, attacker_id=att_id))
    _spy("build_defender_modifiers_from_effects", "rarity",
         lambda: DM.defender_modifiers(state, tgt_id, None, is_melee=True, attacker_id=att_id))
    return vus


def _attacker_ctx(state, att_id: int, tgt_id: int):
    """L'`attacker_ctx` COMPLET que le foyer construit pour le canal self DEFENSEUR."""
    vus = []
    reel = DM.build_defender_modifiers_from_effects

    def _f(*a, **kw):
        vus.append(kw.get("attacker_ctx"))
        return reel(*a, **kw)

    DM.build_defender_modifiers_from_effects = _f
    try:
        DM.defender_modifiers(state, tgt_id, None, is_melee=True, attacker_id=att_id)
    finally:
        DM.build_defender_modifiers_from_effects = reel
    return vus[0] if vus else None


def _acid(source: int, level: int = 1):
    from engine.entities.effects.factory import EffectFactory                   # noqa: PLC0415
    return EffectFactory.create({"name": ACID.name, "effectType": int(ACID),
                                 "source": source, "active": True}, 100, level)


def run(vis: "str | None" = None, rarity: int = int(Rarity.Epic), seed: int = RAR.SEED,
        board: str = RAR.BOARD, verbose: bool = True) -> dict:
    """Monte le bras SEPARANT, mesure, DISPOSE. Leve si le regime n'est pas atteint."""
    res: dict = {"seed": seed, "board": board, "rarityDemandee": rarity}
    bras = None
    try:
        # (a) BRAS DE RECONNAISSANCE : le roster de ce couple (board, seed), pour choisir un HEROS.
        #     `rarity=None` = bras DEGENERE, qui est AUSSI le temoin de #999-r3 (il doit NE PAS
        #     separer -- le probe le refuse sinon).
        if vis is None:
            recon = RAR.run(rarity=None, seed=seed, board=board, keep=True, verbose=verbose)
            try:
                st0, _dv0, _cs0 = _rpc_state(recon["runnerId"])
                heroes0 = _heroes(st0)
                vis_by_id = {int(u["id"]): u.get("visualId")
                             for u in (_dv0.get("units") or []) if u.get("id") is not None}
                cand = sorted({vis_by_id.get(uid) for uid in heroes0} - {None})
                res["herosDuRoster"] = cand
            finally:
                RAR.dispose(recon)
            if not cand:
                raise RuntimeError(
                    "aucun HEROS dans le roster de (%s, seed=%d) : le bras separant ne pourrait "
                    "pas isoler le conjoint de RARETE de celui de TRAIT." % (board, seed))
            vis = cand[0]
        res["vis"] = vis

        # (b) BRAS SEPARANT sur ce heros.
        bras = RAR.run(rarity=rarity, vis=vis, seed=seed, board=board, keep=True, verbose=verbose)
        res["bras"] = {k: bras[k] for k in ("bras", "distinct", "ctxDistinct", "rarityEnum")
                       if k in bras}
        st, dv, _cs = _rpc_state(bras["runnerId"])
        heroes = _heroes(st)
        res["heroes"] = {uid: (t, None if r is None else int(r)) for uid, (t, r) in heroes.items()}

        sep = sorted(uid for uid, (_t, r) in heroes.items() if r == Rarity(rarity))
        myt = sorted(uid for uid, (_t, r) in heroes.items() if r == Rarity.Mythic)
        if not sep or not myt:
            raise RuntimeError(
                "le bras ne separe pas SUR LES HEROS (rarete %s : %s ; Mythic : %s) -- rien n'est "
                "conclu." % (Rarity(rarity).name, sep, myt))
        att_sep, att_myt = sep[0], myt[0]
        # CIBLE : un ennemi de l'attaquant MYTHIC (les deux attaquants doivent frapper la MEME
        # cible pour que seule la rarete change).
        team_myt = heroes[att_myt][0]
        tgt = next((int(uid) for uid, ent in st.entities.items()
                    for oc in (ent.get_component(OwnerComponent),)
                    if oc is not None and oc.team is not None and oc.team != team_myt), None)
        if tgt is None:
            raise RuntimeError("aucune cible ennemie -- montage degenere")
        res["attSepare"], res["attMythic"], res["cible"] = att_sep, att_myt, tgt

        # ETAGE 1 -- TRAVERSEE : les trois cles portent la valeur SEPAREE.
        res["cles_att_separe"] = {k: (None if v is None else int(v))
                                  for k, v in _ctx_rarity_keys(st, att_sep, tgt).items()}
        res["cles_att_mythic"] = {k: (None if v is None else int(v))
                                  for k, v in _ctx_rarity_keys(st, att_myt, tgt).items()}

        # ETAGE 2 -- DISCRIMINATION : le gate de 1448, tout le reste egal.
        ctx_sep = _attacker_ctx(st, att_sep, tgt)
        ctx_myt = _attacker_ctx(st, att_myt, tgt)
        # SOURCE de l'effet = un ALLIE de chaque attaquant (`AreFriends(Caster, EffectSource)`).
        src_sep = next(uid for uid, (t, _r) in heroes.items() if t == heroes[att_sep][0])
        src_myt = next(uid for uid, (t, _r) in heroes.items() if t == team_myt)
        eb_sep = _acid(src_sep).create_effect_damage_malus_for_defense(True, None, ctx_sep)
        eb_myt = _acid(src_myt).create_effect_damage_malus_for_defense(True, None, ctx_myt)
        res["gate1448"] = {
            "attSepare": None if eb_sep is None else (eb_sep.kind, int(eb_sep.value)),
            "attMythic": None if eb_myt is None else (eb_myt.kind, int(eb_myt.value)),
        }
        res["discrimine"] = (eb_sep is None and eb_myt is not None)
        res["heroTraitLesDeux"] = True     # `_heroes` ne rend QUE des porteurs de `Hero`

        if verbose:
            print()
            print("[999-r3-r1] vis separe = %s -> %s ; entites heros = %s"
                  % (vis, Rarity(rarity).name, res["heroes"]))
            print("[999-r3-r1] attaquant SEPARE=%d  MYTHIC=%d  cible=%d"
                  % (att_sep, att_myt, tgt))
            print("[999-r3-r1] cles de ctx (attaquant SEPARE) : %s" % res["cles_att_separe"])
            print("[999-r3-r1] cles de ctx (attaquant MYTHIC) : %s" % res["cles_att_mythic"])
            print("[999-r3-r1] gate 1448 : SEPARE=%s  MYTHIC=%s"
                  % (res["gate1448"]["attSepare"], res["gate1448"]["attMythic"]))
    finally:
        if bras is not None:
            RAR.dispose(bras)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="#999-r3-r1 -- ctx de rarete confronte LIVE")
    ap.add_argument("--vis", default=None, help="visualId du HEROS a separer (defaut : deduit)")
    ap.add_argument("--rarity", type=int, default=int(Rarity.Epic))
    ap.add_argument("--seed", type=int, default=RAR.SEED)
    ap.add_argument("--board", default=RAR.BOARD)
    a = ap.parse_args()
    r = run(vis=a.vis, rarity=a.rarity, seed=a.seed, board=a.board, verbose=True)
    print()
    ok = True
    # Les TROIS cles doivent exister ET porter la rarete de l'unite visee.
    for cle, attendu, bloc in (("att_rarity", a.rarity, "cles_att_separe"),
                               ("rarity", a.rarity, "cles_att_separe"),
                               ("att_rarity", int(Rarity.Mythic), "cles_att_mythic"),
                               ("rarity", int(Rarity.Mythic), "cles_att_mythic")):
        vu = r.get(bloc, {}).get(cle)
        etat = "OK " if vu == attendu else "KO "
        ok = ok and vu == attendu
        print("%s %-16s [%s] = %s (attendu %s)" % (etat, cle, bloc, vu, attendu))
    tgt_r = r.get("cles_att_mythic", {}).get("tgt_rarity")
    print("    tgt_rarity (canal aura DEFENSE) = %s" % tgt_r)
    ok = ok and tgt_r is not None
    print("%s le gate 1448 DISCRIMINE (SEPARE muet, MYTHIC actif) : %s"
          % ("OK " if r.get("discrimine") else "KO ", r.get("discrimine")))
    ok = ok and bool(r.get("discrimine"))
    mag = (r.get("gate1448") or {}).get("attMythic")
    if mag is not None:
        attendu_mag = ("PercentIncrease", PALIERS_EXTRA_DMG_PCT[0])
        print("%s magnitude au palier TERTIAIRE 1 : %s (attendu %s)"
              % ("OK " if tuple(mag) == attendu_mag else "KO ", tuple(mag), attendu_mag))
        ok = ok and tuple(mag) == attendu_mag
    print()
    print("VERDICT: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
