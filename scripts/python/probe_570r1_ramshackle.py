"""#570-r1 -- `Ramshackle_DmgReduction` (1090) : le passif du Grot Tank, NATIF vs PORT.

QUESTION BINAIRE, POSEE AVANT LA METHODE. Le Grot Tank encaisse-t-il `-dmgReduction` sur les
attaques a percage FAIBLE, et RIEN sur les autres -- et le port le fait-il pour la meme valeur ?

#570 avait porte l'ability `1057 GrotTank` et NOMME le trou : le summon arrivait avec ses stats,
ses quatre traits et ses deux armes, **sans sa reduction de degat**. L'ecart est PERMISSIF (le
tank encaisse plus qu'il ne devrait) et SILENCIEUX -- « le tank meurt » est un resultat plausible,
donc aucun test ne pouvait le voir.

L'ARTEFACT (mirror dans `engine/entities/effects/loki/ramshackle.py`) :

    ...Ramshackle_DmgReductionEffect$$CreateDamageModifier
        = ForAddition( get_OwnerIsTarget
                         & AmountIsEqualOrGreater(ConfigConst(0x49 = pierceRatio),
                                                  AttackPiercingRatio()),
                       Multiply(ConfigVar(0x12 = dmgReduction), Direct(-1)@DSLFormulas+0x38) )

C'EST UN COUPLE QUI REND LE GATE OBSERVABLE, PAS UN SEUL COUP. Un unique attaquant ne pourrait pas
separer « la reduction s'applique » de « le port se trompe de degat de base » : il faut DEUX
profils de part et d'autre des 30 % de la constante, sur la MEME cible et le MEME etat.
  * `adeptRetributor` -- profil `Physical`, `PiercingRatio` **1**  -> le gate PASSE  (reduction) ;
  * `admecDominus`    -- profil `Power`,    `PiercingRatio` **40** -> le gate REFUSE (rien).
Les deux sont melee et frappent en **1 coup** : le moins d'etages possible entre la formule et le
delta de PV. Le probe IMPRIME les deux profils et leur ratio, relus du gameconfig, jamais en dur.

ETAGES :
  [1] SPAWN       : le tank apparait (non-regression #570) et PORTE l'effet 1090 cote NATIF.
  [2] SEED PORT   : le port, jouant LUI-MEME le cast, pose 1090 sur SON tank -- c'est le volet
                    `_seed_ability_owner_effects` au spawn, que rien d'autre ne couvre (mesure :
                    **0** unite non-`lineup` du gameconfig etait touchee par ce chemin avant).
  [3] PERCAGE BAS : degat NATIF == degat PORT sur `adeptRetributor` (profil a percage 1).
  [4] PERCAGE HAUT: degat NATIF == degat PORT sur `admecDominus` (profil a percage 40), TEMOIN
                    NEGATIF -- si le port appliquait la reduction ici, l'etage [3] seul ne le
                    dirait pas.

Le MT offline est CALE sur le MT live juste avant chaque coup natif (`dumpRng`), donc les deux
degats sont comparables A L'UNITE PRES.

    python probe_570r1_ramshackle.py [--state-file <chemin ABSOLU>] [--board MC1_67] [--seed 777]

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import probe_503r1_overwhelming_wrath_phase2 as P

CASTER = "orksBigMek"
#: Les DEUX attaquants, choisis pour encadrer la constante `pierceRatio` du kit (relue, pas ecrite).
ATT_BAS = "adeptRetributor"     # profil Physical, PiercingRatio 1  -> le gate PASSE
#: TROISIEME profil, et il ne sert PAS a re-verifier le gate : il tranche le PLACEMENT.
#: `Energy` perce a 30 % (le gate passe, de justesse : `30 >= 30`). Si la reduction est
#: PRE-percage, l'ecart port-vs-natif est dilue par le percage et vaut `R x 30 %` ; si elle est
#: POST-percage il vaut `R` tout entier. Sur `Physical` (1 %) les deux hypotheses concurrentes
#: rendaient le MEME nombre (5) -- un regime DEGENERE, ou l'accord ne prouve rien.
ATT_MOYEN = "admecManipulus"    # profil Energy,   PiercingRatio 30 -> le gate PASSE (egalite)
ATT_HAUT = "admecDominus"       # profil Power,    PiercingRatio 40 -> le gate REFUSE
GROT_TANK = 1057                # ActiveAbilityType.GrotTank
RAMSHACKLE = 1090               # EffectType.Ramshackle_DmgReduction
BOARD = "MC1_67"


def _rpc(sid, m, b, t=90):
    return P.rpc(sid, m, b, t)


def _normal_attack_type(dec, uid: int):
    """L'id CONCRET de l'attaque normale de `uid` (`ActiveAbilityComponent.NormalAttackType`),
    PER-UNITE : `applyAction{"kind": "attack"}` n'existe pas, et le `17` synthetique de l'offline
    n'est pas un id natif."""
    for u in (dec.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            for a in (u.get("abilities") or []):
                if a.get("kind") == "normal" and a.get("id") is not None:
                    return int(a["id"])
    return None


def _units(sid, rid) -> dict:
    ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): u for u in (ob.get("units") or [])}


def _effets(dec, uid: int) -> list:
    for u in (dec.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            return list(u.get("effects") or [])
    return []


def _approcher(sid, rid, att_id: int, cible_id: int, nat: int) -> bool:
    """C'EST LE JEU QUI DIT D'OU L'ON PEUT FRAPPER (`castFromTiles`), jamais la distance hex :
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` lit la connectivite BRUTE et porte
    une porte d'ELEVATION. On DEPLACE l'attaquant -- « bloque par la geometrie de spawn » n'est
    pas un resultat."""
    cf = _rpc(sid, "castFromTiles", {"runnerId": rid, "casterId": att_id,
                                     "targetId": cible_id, "abilityType": nat}, 60) or {}
    if cf.get("currentValid"):
        return True
    tiles = [t for t in (cf.get("moveTiles") or []) if t.get("col") is not None]
    if not tiles:
        print("    [approche] u%d : AUCUNE moveTile pour frapper u%d -- castFromTiles=%s"
              % (att_id, cible_id, json.dumps({k: cf.get(k) for k in
                                               ("currentValid", "reason", "error")})))
        return False
    t = tiles[0]
    # `action = {kind:"move", unitId, to}` -- `to` est un OBJET `{col,row}` (rpc-api.md), pas deux
    # champs plats : la forme plate est acceptee sans erreur et NE BOUGE RIEN.
    _rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": att_id,
        "to": {"col": int(t["col"]), "row": int(t["row"])}}}, 90)
    cf = _rpc(sid, "castFromTiles", {"runnerId": rid, "casterId": att_id,
                                     "targetId": cible_id, "abilityType": nat}, 60) or {}
    return bool(cf.get("currentValid"))


def _cablage(state, cible_id: int, profil: "str | None") -> list:
    """Ce que les instances d'effet du PORT portees par la cible rendent SUR CE PROFIL.

    C'est l'etage de CABLAGE, distinct de la magnitude : il separe « l'effet n'est pas la »
    (registre, seed, factory) de « l'effet est la et rend le mauvais montant »."""
    from engine.runner.components import StatsComponent
    e = state.get_entity(int(cible_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    out = [{"CTX": {k: getattr(ctx, k, "<absent>") for k in
                    ("passive_ability_level", "ability_level", "active_ability_level",
                     "ability_variables_multiplier")}}]
    if state.effects is None:
        return out
    for e in (state.effects.by_unit.get(int(cible_id)) or []):
        try:
            b = e.create_effect_damage_malus_for_defense(damage_profile=profil)
        except Exception as ex:                             # pragma: no cover (diagnostic)
            b = "ERREUR %r" % (ex,)
        out.append({"classe": type(e).__name__, "type": e.effect_type,
                    "ability_level": e.ability_level, "level": e.level,
                    "mult": e.ability_variables_multiplier,
                    "bonus": (None if b is None else str(b))})
    return out


def _coup(sid, rid, att_id: int, cible_id: int, profil: "str | None") -> dict:
    """UN coup de `att_id` sur `cible_id`, joue par le PORT (sur MT cale) PUIS par le NATIF."""
    from engine.runner.operations.damage import AttackDamageOperation

    dec = P.decision(sid, rid)
    nat = _normal_attack_type(dec, att_id)
    if nat is None:
        return {"erreur": "aucune attaque normale pour u%d" % att_id}
    if not _approcher(sid, rid, att_id, cible_id, nat):
        return {"erreur": "u%d ne peut pas atteindre u%d" % (att_id, cible_id)}

    # PORT : l'etat AVANT le coup natif, MT cale sur le MT live.
    state, _ = P.load(sid, rid)
    P.seed_offline_rng(state, P.rng_dump(sid, rid))
    # ETAGE DE CABLAGE : l'instance d'effet du PORT existe-t-elle, et que rend SON canal ? Sans
    # cette lecture, « port != natif » ne distingue pas « mauvaise magnitude » de « l'effet n'est
    # pas la » -- et c'est exactement la question qui s'est posee ici.
    inst = _cablage(state, int(cible_id), profil)
    hp_off_avant = P.hp_off(state)
    r = AttackDamageOperation.execute(state, int(att_id), int(cible_id)) or {}
    hp_off_apres = P.hp_off(state)
    port = int(hp_off_avant.get(cible_id, 0)) - int(hp_off_apres.get(cible_id, 0))

    # NATIF : le MEME coup.
    hp_live_avant = P.hp_live(sid, rid)
    act = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(att_id), "abilityType": int(nat),
        "targetId": int(cible_id)}}, 90) or {}
    hp_live_apres = P.hp_live(sid, rid)
    natif = int(hp_live_avant.get(cible_id, 0)) - int(hp_live_apres.get(cible_id, 0))
    return {"port": port, "natif": natif, "nat": nat, "cablage": inst,
            "erreur_cast": (act.get("actions") or [{}])[0].get("error"),
            "etages": {k: r.get(k) for k in ("total", "rolls", "crits", "armor", "pierce",
                                             "profile", "did_block", "per_hit")}}


def mesurer(sid: int, state_name: str, board: str = BOARD, seed: str = "777") -> dict:
    import gameconfig as GC
    state_path = P.LOGS / ("%s.json" % state_name)
    rid = P.build(state_path, [
        "--seed", seed, "--board", board,
        "--p-units", CASTER,
        "--a-units", "%s,%s,%s" % (ATT_BAS, ATT_MOYEN, ATT_HAUT),
        "--place", "%s:2,3" % CASTER,
        "--a-place", "%s:1,3" % ATT_BAS, "--a-place", "%s:3,3" % ATT_MOYEN,
        "--a-place", "%s:1,2" % ATT_HAUT])
    out: dict = {"rid": rid, "profils": {}}
    for uid in (ATT_BAS, ATT_MOYEN, ATT_HAUT):
        w = ((GC.unit(uid) or {}).get("weapons") or [{}])[0]
        prof = w.get("DamageProfile")
        out["profils"][uid] = {"profil": prof,
                               "pierce": (GC.damage_profile(prof) or {}).get("PiercingRatio"),
                               "hits": w.get("hits")}
    out["pierce_ratio_kit"] = GC.ability("Ramshackle", ).get("constants", {}).get("pierceRatio")
    try:
        P.bind_transport(sid)
        dec0 = P.decision(sid, rid)
        mek = P.find(dec0, CASTER)
        if mek is None:
            raise AssertionError("SCENARIO NON MONTE : %s absent du decisionView" % CASTER)
        mek_id = int(mek["id"])
        at = _rpc(sid, "abilityTargets",
                  {"runnerId": rid, "unitId": mek_id, "abilityType": GROT_TANK}) or {}
        row = next((u for u in (at.get("units") or []) if u.get("unitId") == mek_id), None)
        ab = next((a for a in ((row or {}).get("abilities") or [])
                   if int(a.get("abilityId", -1)) == GROT_TANK), {})
        tuiles = [t.get("targetId") for t in (ab.get("fromHere") or [])]
        if not tuiles:
            raise AssertionError("SCENARIO NON MONTE : aucune tuile de spawn SUR PLACE pour 1057")

        # ---- [2] LE PORT joue le cast sur SON etat : son tank porte-t-il 1090 ? --------------
        state, _ = P.load(sid, rid)
        P.seed_offline_rng(state, P.rng_dump(sid, rid))
        avant_off = set(state.entities)
        from engine.runner.operations.summon_ai import _apply_active_ability
        _apply_active_ability(state, mek_id, int(tuiles[0]), GROT_TANK)
        neufs = [e for e in state.entities if e not in avant_off]
        out["port_spawn"] = neufs
        out["port_effets_du_tank"] = (
            [int(e.effect_type) for e in (state.effects.by_unit.get(neufs[0]) or [])]
            if neufs and state.effects is not None else [])

        # ---- [1] LE NATIF joue le MEME cast ---------------------------------------------------
        avant = set(_units(sid, rid))
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": mek_id, "abilityType": GROT_TANK,
            "targetId": int(tuiles[0])}})
        apres = _units(sid, rid)
        tank = [u for u in apres if u not in avant]
        if not tank:
            raise AssertionError("SCENARIO NON MONTE : aucun summon apparu")
        tank_id = int(tank[0])
        dec1 = P.decision(sid, rid)
        out["tank"] = {"id": tank_id, "visualId": apres[tank_id].get("visualId"),
                       "hp": apres[tank_id].get("hp")}
        out["effets_natifs_du_tank"] = _effets(dec1, tank_id)

        # ---- tour ADVERSE : les deux attaquants frappent le tank ------------------------------
        # ⚠ ON NE SUPPOSE PAS QUE C'EST DEJA LEUR TOUR : `toActivate` le DIT, et on passe le tour
        # jusqu'a ce qu'ils y soient. Un `endturn` de trop rendrait la main au joueur et ferait
        # lire « ne peut pas atteindre » la ou la cause est « ce n'est pas son tour » -- exactement
        # le genre de non-mesure qui se lit comme un resultat.
        dec2, tours = P.decision(sid, rid), 0
        while tours < 4:
            act_ids = {int(x) for x in (dec2.get("toActivate") or []) if x is not None}
            if any(int((P.find(dec2, v) or {}).get("id", -1)) in act_ids
                   for v in (ATT_BAS, ATT_MOYEN, ATT_HAUT)):
                break
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
            dec2 = P.decision(sid, rid)
            tours += 1
        out["endturns"] = tours
        out["to_activate"] = list(dec2.get("toActivate") or [])
        for cle, vid in (("bas", ATT_BAS), ("moyen", ATT_MOYEN), ("haut", ATT_HAUT)):
            u = P.find(dec2, vid)
            if u is None:
                out[cle] = {"erreur": "%s absent du decisionView adverse" % vid}
                continue
            out[cle] = _coup(sid, rid, int(u["id"]), tank_id,
                             (out["profils"].get(vid) or {}).get("profil"))
        return out
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais les autres
        except Exception as e:                                  # pragma: no cover
            print("[warn] disposeRunner a echoue : %s" % e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    sid = P._session()
    nom = Path(a.state_file).stem if a.state_file else "probe_570r1_ramshackle"
    m = mesurer(sid, nom, board=a.board, seed=a.seed)
    rc = 0

    print("[570-r1] constante `pierceRatio` du kit Ramshackle : %s" % m["pierce_ratio_kit"])
    print("[570-r1] profils des deux attaquants : %s" % json.dumps(m["profils"]))

    print("\n[1] SPAWN -- le tank apparait et PORTE 1090 cote natif")
    print("    tank = %s" % json.dumps(m.get("tank")))
    natifs = [int(e.get("effectType")) for e in (m.get("effets_natifs_du_tank") or [])]
    print("    effets natifs : %s" % json.dumps(
        [{"t": e.get("effectType"), "n": e.get("name"), "lvl": e.get("level"),
          "act": e.get("active")} for e in (m.get("effets_natifs_du_tank") or [])]))
    if RAMSHACKLE not in natifs:
        print("    ECHEC : le natif ne publie PAS 1090 sur le tank -- rien n'est comparable")
        rc = 1

    print("    endturns joues avant le tour adverse : %s ; toActivate = %s"
          % (m.get("endturns"), m.get("to_activate")))

    print("\n[2] SEED PORT -- le port pose 1090 sur SON propre tank (spawn)")
    print("    entites neuves : %s ; effets : %s"
          % (m.get("port_spawn"), m.get("port_effets_du_tank")))
    if RAMSHACKLE not in (m.get("port_effets_du_tank") or []):
        print("    ECHEC : le tank du PORT n'a pas 1090 -- `_seed_ability_owner_effects` au spawn")
        rc = 1

    for etage, cle, attendu in (
            ("[3] PERCAGE BAS  (1 %) ", "bas", "la reduction MORD"),
            ("[3b] PERCAGE MOYEN (30 %)", "moyen",
             "elle MORD (egalite) -- et l'ecart DIT le PLACEMENT : `R x 30 %` = PRE-percage, "
             "`R` entier = POST-percage"),
            ("[4] PERCAGE HAUT (40 %)", "haut", "TEMOIN NEGATIF : elle ne mord pas")):
        d = m.get(cle) or {}
        print("\n%s -- %s" % (etage, attendu))
        if d.get("erreur"):
            print("    NON MESURE : %s" % d["erreur"])
            rc = 1
            continue
        print("    port %-8s natif %-8s  %s" % (d["port"], d["natif"],
                                                "OK" if d["port"] == d["natif"]
                                                else "ECART %d" % (d["port"] - d["natif"])))
        print("    etages port : %s" % json.dumps(d.get("etages"), ensure_ascii=True))
        print("    cablage (instances d'effet du PORT sur la cible) :")
        for row in (d.get("cablage") or []):
            print("      %s" % json.dumps(row, ensure_ascii=True))
        ram = next((r for r in (d.get("cablage") or [])
                    if r.get("type") == RAMSHACKLE), None)
        if d.get("erreur_cast"):
            print("    ECHEC : le coup natif a rendu une erreur : %s" % d["erreur_cast"])
            rc = 1
        elif d["natif"] <= 0:
            print("    ECHEC : degat natif NUL -- regime DEGENERE, l'accord ne prouverait rien")
            rc = 1
        elif cle == "haut":
            # TEMOIN NEGATIF : c'est le SEUL etage de magnitude qui soit CONCLUANT aujourd'hui,
            # parce que la valeur attendue y est ZERO -- elle ne depend donc pas du niveau seede.
            if ram is not None and ram.get("bonus") is not None:
                print("    ECHEC : le gate a LAISSE PASSER la reduction sur un profil a percage "
                      "SUPERIEUR a la constante")
                rc = 1
            elif d["port"] != d["natif"]:
                rc = 1
        else:
            # ETAGES POSITIFS : le CABLAGE est verifiable, la MAGNITUDE non (cf. l'en-tete du
            # mirror). On ne rend donc PAS un ECHEC sur l'ecart -- on le NOMME.
            if ram is None or ram.get("bonus") is None:
                print("    ECHEC : le canal du port ne rend RIEN sur un profil qui PASSE le gate")
                rc = 1
            elif d["port"] != d["natif"]:
                print("    NON CONFRONTE (magnitude) : ecart %d. Le port lit `dmgReduction` au "
                      "niveau %s / mult %s -- l'entite NPC fraichement spawnee arrive avec "
                      "`passive_ability_level = 0`. Trou de SUBSTRAT (le meme que l'etage E3 de "
                      "#570), pas de RE." % (d["port"] - d["natif"],
                                             ram.get("ability_level"), ram.get("mult")))
    print("\nVERDICT : %s" % ("OK" if rc == 0 else "ECHEC"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
