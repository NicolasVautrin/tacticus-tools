#!/usr/bin/env python
"""`#547-r14` -- CONFRONTATION LIVE : le REVIVE natif retire-t-il les effets a `KeepOnRevive = False` ?

## Le discriminant, et pourquoi ce kit-la

`IdunBattle.Operations.ReviveUnitOperation$$Execute` appelle le slot 0x5a INLINE avec
`{step: SANS valeur, +0x08: 1}` -- il retire donc TOUS les effets du ressuscite SAUF ceux a
`IEffect` slot 2 `get_KeepOnRevive = True`. Le DEFAUT de `IdunBattle.Entities.Effects.BaseEffect`
etant `True`, l'observable ne peut venir que d'une classe qui le RENVERSE.

L'active `1211 RitesOfMorkai` de `spaceWolfPriest` (Baldr) est le seul montage du jeu qui pose sur
la MEME unite, du MEME cast :

  * `1502 RitesOfMorkai`               -- un `ReviveEffect` : il POSE la `ReviveData` ;
  * `1529 RitesOfMorkai_ExtraDamage`   -- `get_KeepOnRevive = False` (DERIVE, corps `32 c0 c3`),
                                          sur le sous-ensemble de la zone qui porte deja une forme
                                          de Final Vengeance.

Et `spaceWolfPriest` porte LUI-MEME le trait `FinalJustice` (0x3f6 = 1014), donc il recoit les deux.

⚠ L'i2 le dit deja, et c'est une CORROBORATION INDEPENDANTE de la derivation binaire :
`Abilities/RitesOfMorkai_CurrentLevelDescription` -- << become *Inspired* for {[nrOfRounds]} round
**or until they are revived** >>.

## Ce que la mesure doit separer

`1502` disparait de toute facon apres un revive reussi, mais par une AUTRE voie : son ctor porte
`removeEffect = TRUE` (champ 0x488), donc le 2e volet de son behaviour est un `RemoveEffect`
explicite. Le lire comme une preuve serait une faute. Le SEUL temoin propre est **`1529`**, qui n'a
aucun mecanisme de retrait propre au revive.

⚠ TEMOIN NON DEGENERE OBLIGATOIRE : il faut qu'au moins un effet a `KeepOnRevive = True` SURVIVE au
meme revive, sinon << 1529 est parti >> serait aussi compatible avec << le revive retire tout >>.

Usage (depuis scripts/python, session warmee) :
    python probe_547r14_keep_on_revive_live.py --state-file <ABSOLU> [--board MC1_67] [--keep]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"

#: Baldr -- hors du seed BC capture, donc INJECTE au catalogue (les deux : `Units` + `Abilities`).
CASTER_ID = "spaceWolfPriest"
#: Allies NON-MECANIQUES : `get_HealType` de RitesOfMorkai vaut 0 (Heal), et
#: `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` REFUSE les mecaniques.
#: `ultraTitus` porte AUSSI `FinalJustice` -> second porteur possible de 1529.
P_UNITS = "spaceWolfPriest,ultraTitus,eldarFarseer"
A_UNITS = "orksNob,orksWarboss"
#: Calibrage anti-OVERKILL (`get_ReviveOnOverkill` herite = 0 -> un overkill ANNULE le revive).
#: `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` : pct = (dmg - hpAvant)/hpAvant*100
#: compare a `overkillDmgPctOfHealth` (=100) -> il faut `dmg < 2*hpAvant` au coup letal.
#: PV : le calibrage est PRIS EN TENAILLE, et les deux bornes sont MESUREES.
#:  * trop BAS (3000) -> la victime meurt au PREMIER coup en OVERKILL, ce qui ANNULE le revive
#:    (`get_ReviveOnOverkill` herite = 0) : les orks portent des attaques MULTI-HITS, donc
#:    `--dmg-target 1000` ne borne PAS le total d'une attaque (mesure : ~4800 au premier coup) ;
#:  * trop HAUT (20000) -> il faut 5 tours pour tuer, et l'effet `1502 RitesOfMorkai` EXPIRE avant
#:    (i2 : << become Inspired for {[nrOfRounds]} round >>). Mesure : coup letal dans la fenetre
#:    non-overkill (hp 2226 <= degat 4065 < 2*2226) et POURTANT aucun revive.
#: ⇒ LA FENETRE EST D'UN SEUL COUP. Un seul attaquant tient au contact sur ce board, donc chaque
#: coup supplementaire coute UN TOUR, et l'Inspired ne survit pas au round. Le calibrage vise donc
#: `D/2 < HP <= D` des le PREMIER coup, avec D = 3024 MESURE (crit et block neutralises, cf. les
#: deux drapeaux du build) : 1512 < 2800 <= 3024. 2800 tue a coup sur ET reste hors overkill.
HP_PLAYER = 2800
DMG_TARGET = 1000

ABILITY_RITES_OF_MORKAI = 1211          # ActiveAbilityType.RitesOfMorkai
ET_REVIVE = 1502                        # EffectType.RitesOfMorkai        -- ReviveEffect
ET_EXTRA_DMG = 1529                     # EffectType.RitesOfMorkai_ExtraDamage -- KeepOnRevive=False


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def effets_de(dv: dict, uid: int) -> list:
    for u in (dv.get("units") or []):
        if int(u.get("id")) == int(uid):
            return [int(e.get("effectType")) for e in (u.get("effects") or [])
                    if not e.get("removed")]
    return []


def bfs(board_tiles: dict, src, dst) -> int:
    a, b = board_tiles["byPos"].get(src), board_tiles["byPos"].get(dst)
    if a is None or b is None:
        return 10 ** 6
    seen, q = {a: 0}, deque([a])
    while q:
        t = q.popleft()
        if t == b:
            return seen[t]
        for n in board_tiles["nb"].get(t, ()):
            if n not in seen:
                seen[n] = seen[t] + 1
                q.append(n)
    return 10 ** 6


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    sf = Path(a.state_file).resolve()
    if "data" in sf.parts[:-1] and sf.parts[-2] == "data":
        print("REFUS : le state-file est une SORTIE, il ne va pas sous data/.")
        return 2

    print("== #547-r14 -- le REVIVE retire-t-il les effets a KeepOnRevive=False ?")
    s = sid()
    print("[0] session Frida = %d" % s)

    # --- catalogue augmente (Baldr est hors du seed BC capture) -------------------------------
    import catalog_inject as CI
    seed_bc = sf.with_name(sf.stem + "_seedbc.json")
    CI.write_augmented_seed_bc(str(seed_bc), [CASTER_ID])
    print("[1] seed BC augmente : %s" % seed_bc)

    # ⚠ `--crit-target 0` ET `--block-player 0` sont LOAD-BEARING, et c'est MESURE : la fenetre
    # letale non-overkill d'une arme de degat A est `A/2 < hpAvant <= A`. Elle n'existe donc que si
    # `D_max < 2 * D_min` sur la dispersion des coups. Sans ces deux drapeaux, la MEME attaque a
    # rendu 8772, puis 3010, puis 2650 (ratio 3,3) -- crit et block ouvrent une dispersion qui rend
    # la fenetre STRUCTURELLEMENT VIDE, quel que soit le calibrage des PV.
    extra = ["--seed-bc", str(seed_bc), "--p-units", P_UNITS, "--a-units", A_UNITS,
             "--hp-player", str(HP_PLAYER), "--dmg-target", str(DMG_TARGET),
             # Format "<chance>,<damage>" (cf. `_patch_combat_stat`) : chance NULLE des deux cotes.
             "--crit-target", "0,0", "--block-player", "0,0",
             "--board", a.board, "--no-ai"]
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", a.seed,
           "--state-file", str(sf)] + extra
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print("REFUS : build KO rc=%d\n%s\n%s" % (r.returncode, r.stdout[-1500:], r.stderr[-1500:]))
        return 1
    rid = int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"])
    print("[2] runner %d (board %s)" % (rid, a.board))

    try:
        def dv(inc=False):
            return rpc(s, "decisionView", {"runnerId": rid, "maxRank": 2, "allAbilities": True,
                                           "includeInactive": inc}, 180)

        def act(x):
            return rpc(s, "applyAction", {"runnerId": rid, "action": x}, 120)

        bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        tiles = {"byPos": {}, "nb": {}}
        for t in (bg.get("tiles") or []):
            tiles["byPos"][(t["col"], t["row"])] = t["id"]
            tiles["nb"][t["id"]] = list(t.get("neighbours") or [])

        v0 = dv()
        mine = [u["id"] for u in (v0.get("units") or []) if u.get("ctrl")]
        foes = [u["id"] for u in (v0.get("units") or []) if not u.get("ctrl")]
        vis = {u["id"]: u.get("visualId") for u in (v0.get("units") or [])}
        baldr = next((u for u in mine if vis.get(u) == CASTER_ID), None)
        if baldr is None or not foes:
            print("REFUS : roster natif incomplet (baldr=%s foes=%s)" % (baldr, foes))
            return 1
        print("[3] mine=%s foes=%s  baldr=u%d (%s)" % (mine, foes, baldr, vis.get(baldr)))

        # --- ORDRE LOAD-BEARING : ON RAPPROCHE **AVANT** DE CASTER --------------------------
        # `1502 RitesOfMorkai` est un effet a TIMER tres court (i2 : << Inspired for
        # {[nrOfRounds]} round >>). MESURE : caster d'abord puis marcher fait EXPIRER 1502 ET 1529
        # avant meme le premier coup qui morde -- les cinq autres effets de la victime, eux,
        # restaient. La fenetre utile est donc LE SEUL tour adverse qui suit le cast, et il faut y
        # entrer avec les deux attaquants DEJA au contact.
        pressentie = next((u for u in mine if vis.get(u) == "ultraTitus"), None)
        if pressentie is None:
            print("REFUS : `ultraTitus` (porteur de `FinalJustice`) absent de mon camp.")
            return 1

        def marcher(cible):
            """Bouge les foes vers `cible`. Le set de destinations vient d'`aiMovableTiles` -- on ne
            devine JAMAIS un move (runner.md §4). Les foes deja au contact ne bougent pas."""
            ub = {u["id"]: u for u in (dv().get("units") or [])}
            if cible not in ub:
                return
            vp = ub[cible]["pos"]
            vpos = (vp["col"], vp["row"])
            mov = rpc(s, "aiMovableTiles", {"runnerId": rid}, 60) or {}
            for mu in (mov.get("units") or []):
                fid = mu.get("unitId")
                if fid not in foes:
                    continue
                here = ub.get(fid, {}).get("pos") or {}
                if here and bfs(tiles, (here["col"], here["row"]), vpos) <= 1:
                    continue
                tl = [(t["col"], t["row"]) for t in (mu.get("tiles") or [])
                      if t.get("col") is not None]
                if not tl:
                    continue
                best = min(tl, key=lambda t: bfs(tiles, t, vpos))
                act({"kind": "move", "unitId": fid, "to": {"col": best[0], "row": best[1]}})

        def au_contact(cible):
            ub = {u["id"]: u for u in (dv().get("units") or [])}
            if cible not in ub:
                return []
            vp = ub[cible]["pos"]
            vpos = (vp["col"], vp["row"])
            out = []
            for f in foes:
                p = ub.get(f, {}).get("pos")
                if p and bfs(tiles, (p["col"], p["row"]), vpos) <= 1:
                    out.append(f)
            return out

        def mon_tour():
            return any(u.get("ctrl") and u.get("hasAction")
                       for u in (dv().get("units") or []))

        for _t in range(14):
            if len(au_contact(pressentie)) >= 2:
                break
            if mon_tour():
                act({"kind": "endturn"})
            marcher(pressentie)
            act({"kind": "endturn"})
        contacts = au_contact(pressentie)
        print("[3b] attaquants au contact de u%d (%s) : %s"
              % (pressentie, vis.get(pressentie), contacts))
        if not contacts:
            print("NON CONFRONTE : aucun adverse n'a atteint la victime pressentie.")
            return 3
        # Revenir a MON tour pour caster.
        for _ in range(4):
            if mon_tour():
                break
            act({"kind": "endturn"})

        # --- CAST de 1211 ---------------------------------------------------------------------
        rc = act({"kind": "ability", "casterId": baldr, "targetId": baldr,
                  "abilityType": ABILITY_RITES_OF_MORKAI})
        if not (isinstance(rc, dict) and rc.get("ok")):
            print("REFUS : cast RitesOfMorkai KO : %s" % str(rc)[:400])
            return 1
        v1 = dv()
        porteurs = {u["id"]: effets_de(v1, u["id"]) for u in (v1.get("units") or [])
                    if u.get("ctrl")}
        print("[4] APRES le cast, effets par unite de mon camp :")
        for uid, eff in sorted(porteurs.items()):
            print("      u%-3d %-20s %s" % (uid, vis.get(uid), sorted(eff)))

        # La VICTIME est DERIVEE de la mesure : il lui faut les DEUX effets (le revive ET le
        # temoin a KeepOnRevive=False), plus au moins un AUTRE effet (le temoin non degenere).
        cands = [uid for uid, eff in porteurs.items()
                 if ET_REVIVE in eff and ET_EXTRA_DMG in eff and len(eff) >= 3]
        if not cands:
            print("NON CONFRONTE : aucune unite ne porte a la fois %d, %d et un 3e effet temoin."
                  % (ET_REVIVE, ET_EXTRA_DMG))
            print("  (sans temoin a KeepOnRevive=True, << 1529 est parti >> ne discriminerait pas)")
            return 3
        # On prend le porteur le MIEUX DOTE EN TEMOINS : plus il en porte, moins le verdict
        # << 1529 est parti >> peut se confondre avec << le revive retire tout >>.
        victim = max(cands, key=lambda u: len(porteurs[u]))
        avant = sorted(porteurs[victim])
        temoins_true = [e for e in avant if e not in (ET_REVIVE, ET_EXTRA_DMG)]
        print("[5] VICTIME = u%d (%s)  effets AVANT = %s" % (victim, vis.get(victim), avant))
        print("      temoin(s) attendu(s) SURVIVANT(s) (KeepOnRevive herite = True) : %s"
              % temoins_true)

        # --- la main a l'adversaire ------------------------------------------------------------
        act({"kind": "endturn"})
        print("[6] la main a l'adversaire")

        def etat(uid):
            for u in (dv().get("units") or []):
                if int(u.get("id")) == int(uid):
                    return bool(u.get("alive")), int(u.get("hp") or 0)
            return None, None

        # ---- ANTI-OVERKILL, ADAPTATIF ------------------------------------------------------------
        # `get_ReviveOnOverkill` herite = 0 : un coup letal en OVERKILL ANNULE le revive, et la
        # mesure est perdue. `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` compare
        # `pct = (dmg - hpAvant)/hpAvant*100` a `overkillDmgPctOfHealth` (= 100), donc la fenetre
        # LETALE NON-OVERKILL d'une arme de degat A est :   A/2 < hpAvant <= A.
        #
        # On ne DEVINE donc aucun calibrage : on MESURE le degat reel de chaque couple
        # (attaquant, ability) sur les premiers coups, puis on choisit a chaque tour l'arme qui
        # tombe dans la fenetre. Les degats varient (crit/block/armure) -- d'ou la re-mesure
        # continue plutot qu'une constante.
        mort, revive, hp_revive = False, False, None
        degats: dict = {}                       # (fid, aid) -> derniere perte MESUREE

        def armes(vv):
            """Couples (attaquant, ability) reellement JOUABLES ce tour.

            ⚠ Le filtre `hasAction` est LOAD-BEARING : `attackPlans` continue de lister une unite
            qui a DEJA agi, donc sans lui la boucle rejoue le meme couple indefiniment sur un etat
            qui ne bouge plus (mesure : 23 coups a vide, hp fige a 13025). `decisionView` publie ce
            champ sous le nom `hasAction` -- c'est `UnitExtensions$$HasActionLeft`."""
            actifs = {int(u["id"]) for u in (vv.get("units") or []) if u.get("hasAction")}
            # ⚠ ET AU CONTACT : `attackPlans` liste aussi des attaquants HORS PORTEE, dont le coup
            # part sans mordre. Chaque coup a vide coute un tour, et l'Inspired ne survit pas au
            # round -- c'est ce qui a fait EXPIRER le regime deux fois avant le coup letal.
            proches = set(au_contact(victim))
            out = []
            for p in (vv.get("attackPlans") or []):
                fid = p.get("unitId")
                if fid not in foes or int(fid) not in actifs or int(fid) not in proches:
                    continue
                for ev in (p.get("evals") or []):
                    if ev.get("targetId") == victim and ev.get("abilityId") is not None:
                        out.append((fid, int(ev["abilityId"])))
            return sorted(set(out))

        inefficaces: set = set()
        # (les attaquants sont DEJA au contact : la marche a eu lieu AVANT le cast, cf. [3b])
        for _coup in range(40):
            al, hp = etat(victim)
            if al is None:
                break
            if not al:
                mort = True
                break
            vv = dv()
            dispo = [k for k in armes(vv) if k not in inefficaces]
            if not dispo:
                # Personne ne peut plus frapper ce tour : on rend la main, puis on RAPPROCHE avant
                # de retenter -- un foe hors portee est la cause n1 d'une attaque qui ne mord pas.
                act({"kind": "endturn"})
                act({"kind": "endturn"})
                inefficaces.clear()
                marcher(victim)
                continue
            connus = [(k, degats[k]) for k in dispo if k in degats]
            # (a) une arme MESUREE qui tue SANS overkill -> on la joue, c'est le coup letal.
            letal = [k for (k, d) in connus if d / 2.0 < hp <= d]
            # (b) sinon une arme qui NE TUE PAS -> on descend d'un cran.
            sur = [(d, k) for (k, d) in connus if d < hp]
            if letal:
                fid, aid = letal[0]
                role = "LETAL non-overkill"
            elif sur:
                fid, aid = max(sur)[1]
                role = "descente"
            else:
                inconnues = [k for k in dispo if k not in degats]
                if not inconnues:
                    # Toutes mesurees, aucune ne tient dans la fenetre : on prend la PLUS PETITE
                    # (celle qui a le meilleur ratio) et on le DIT.
                    fid, aid = min(connus, key=lambda kd: kd[1])[0]
                    role = "faute de mieux (overkill possible)"
                else:
                    fid, aid = inconnues[0]
                    role = "calibrage"
            # ⚠ CONTROLE DE VALIDITE DU REGIME, avant chaque coup. `1502` est un effet a TIMER
            # (<< Inspired for {[nrOfRounds]} round >>) : s'il a EXPIRE, la victime mourra sans
            # revive et l'echec n'aura RIEN a voir avec l'overkill. Le dire au lieu de le deviner.
            portes = effets_de(dv(), victim)
            if ET_REVIVE not in portes or ET_EXTRA_DMG not in portes:
                print("NON CONFRONTE : le regime a EXPIRE avant le coup letal -- effets encore")
                print("  portes par u%d : %s (il faut %d ET %d)."
                      % (victim, sorted(portes), ET_REVIVE, ET_EXTRA_DMG))
                print("  Baisser HP_PLAYER pour tuer DANS le round ou l'Inspired est encore actif.")
                return 3
            print("      u%d -> u%d abil=%-5s hp=%-6s %-32s mesures=%s"
                  % (fid, victim, aid, hp, role,
                     {"%d/%d" % k: v for k, v in sorted(degats.items())}))
            res = act({"kind": "ability", "casterId": fid, "targetId": victim,
                       "abilityType": aid})
            d, rv = _scan(res, victim)
            if rv is not None:
                hp_revive = rv
            al2, hp2 = etat(victim)
            if al2 and hp2 is not None and hp is not None and hp2 < hp:
                degats[(fid, aid)] = hp - hp2               # perte REELLE de ce couple
            elif al2 and hp2 == hp:
                # L'attaque N'A PAS MORDU (hors portee, refus de ciblage, plus d'action...). On le
                # RETIENT au lieu de la rejouer : c'est ce qui produisait les boucles a vide.
                inefficaces.add((fid, aid))
                print("        (sans effet -- ok=%s ; couple ecarte pour ce tour)"
                      % (isinstance(res, dict) and res.get("ok")))
            # DISCRIMINANT D'ETAT, independant du scan d'evenements : le revive est INSTANTANE dans
            # la meme cascade, donc une victime qui a subi un coup LETAL et ressort `alive` a ete
            # ressuscitee. Les evenements ne servent que de confirmation -- une passe precedente a
            # rendu << morte mais pas revive >> sur ce seul canal.
            if d and al2:
                revive = True
                print("[7] MORT puis REVIVE natif -- alive=%s hp=%s (events: hp_revive=%s)"
                      % (al2, hp2, hp_revive))
                break
            if not al2:
                mort = True
                print("      u%d MORTE et NON revive (hp=%s, events hp_revive=%s)"
                      % (victim, hp2, hp_revive))
                break

        if not revive:
            print("NON CONFRONTE : la victime n'a pas ete revive en live (morte=%s)." % mort)
            if mort:
                print("  Cause la plus probable : OVERKILL (`get_ReviveOnOverkill` herite = 0).")
                print("  Re-calibrer HP_PLAYER / DMG_TARGET : il faut `dmg < 2*hpAvant` au coup letal.")
            return 3

        v2 = dv(True)
        apres = sorted(effets_de(v2, victim))
        print("[8] effets APRES le revive = %s" % apres)

        # --- VERDICT ---------------------------------------------------------------------------
        ok = True
        if ET_EXTRA_DMG in apres:
            print("  ROUGE : %d (KeepOnRevive=False) a SURVECU au revive." % ET_EXTRA_DMG)
            ok = False
        else:
            print("  OK    : %d (KeepOnRevive=False) a ete RETIRE par le revive." % ET_EXTRA_DMG)
        survivants = [e for e in temoins_true if e in apres]
        if not survivants:
            print("  ROUGE : AUCUN temoin a KeepOnRevive=True n'a survecu -- le regime est")
            print("          DEGENERE (compatible avec << le revive retire tout >>), donc la")
            print("          mesure ci-dessus ne discrimine RIEN.")
            ok = False
        else:
            print("  OK    : temoin(s) a KeepOnRevive=True SURVIVANT(s) : %s" % survivants)

        # --- AGREEMENT EXPLICITE port <-> natif ------------------------------------------------
        # Ce que le PORT aurait garde, derive de ses classes d'effet (pas recopie d'une attente).
        # `1502` est EXCLU de la comparaison, et c'est load-bearing : il part par son PROPRE
        # `RemoveEffect` (2e volet du behaviour, `removeEffect = TRUE` au ctor), donc son sort ne
        # dit RIEN du gate `KeepOnRevive` -- l'inclure ferait passer un desaccord pour un accord.
        try:
            # `EFFECT_CLASSES` est indexe par NOM, pas par ordinal -- on passe donc par le mirror
            # d'enum. (Une premiere version indexait par `int` : elle rendait TOUS les types
            # << sans classe portee >> et fabriquait un faux DESACCORD. Le recenseur etait faux,
            # pas le port : c'est pour ca que la ligne `types sans classe portee` est IMPRIMEE.)
            from engine.entities.effects.factory import EFFECT_CLASSES    # noqa: E402
            from engine.entities.effect_type import EffectType            # noqa: E402
            garde_port, inconnus = [], []
            for et in avant:
                if et == ET_REVIVE:
                    continue
                try:
                    nom = EffectType(int(et)).name
                except ValueError:
                    nom = None
                cls = EFFECT_CLASSES.get(nom) if nom else None
                if cls is None:
                    inconnus.append(et)
                    continue
                if getattr(cls, "keep_on_revive", True):
                    garde_port.append(et)
            attendu = sorted(garde_port + inconnus)   # un type sans classe herite du defaut True
            mesure = sorted(e for e in apres if e != ET_REVIVE)
            print("[9] AGREEMENT port<->natif (hors %d, qui part par sa propre voie) :" % ET_REVIVE)
            print("      port attend %s ; natif rend %s%s"
                  % (attendu, mesure,
                     (" ; types sans classe portee (defaut True) : %s" % inconnus)
                     if inconnus else ""))
            if attendu != mesure:
                print("      ROUGE : DESACCORD port <-> natif.")
                ok = False
            else:
                print("      OK    : accord exact.")
        except Exception as exc:                                          # noqa: BLE001
            print("[9] agreement NON MESURE (resolution des classes portees KO : %s)"
                  % str(exc)[:200])

        print("VERDICT : %s" % ("le natif CONCORDE avec le port de #547-r14" if ok
                                else "DIVERGENCE -- relire le port"))
        return 0 if ok else 1
    finally:
        if not a.keep:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 60)
                print("[9] runner %d dispose" % rid)
            except Exception as exc:                                     # noqa: BLE001
                print("[9] dispose KO : %s" % str(exc)[:200])


def _scan(apply_result, victim):
    """(mort ?, PV du revive) -- meme motif que `test_rites_of_morkai_revive_live` : le revive est
    INSTANTANE dans la MEME cascade (hp_max -> 0 -> hp_max), donc un diff d'etat ne voit RIEN ;
    seuls les EVENEMENTS temoignent."""
    death, rev = False, None
    for act in ((apply_result or {}).get("actions") or []):
        for ev in (act.get("events") or []):
            if ev.get("entity") != victim or ev.get("kind") != "action":
                continue
            try:
                tags = json.loads(ev.get("tags") or "{}")
            except Exception:                                            # noqa: BLE001
                continue
            hp = tags.get("UnitStats_RemainingHealth")
            if hp is None:
                continue
            if tags.get("UnitStats_Transformed") == 1:
                rev = int(hp)
            elif int(hp) == 0 and tags.get("UnitStats_NumberOfMembers") == 0:
                death = True
    return death, rev


if __name__ == "__main__":
    raise SystemExit(main())
