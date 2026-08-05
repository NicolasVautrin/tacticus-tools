#!/usr/bin/env python
"""probe #589-r1-r1-r2-r1 -- MESURE de l'axe REDUCTION du canal crit-DEGAT
(`AmuletOfTheVoidwyrm_CritDamageReduction`, EffectType 0x5b4 = 1460).

CRITERE BINAIRE, pose avant toute methode :

    « Le natif retranche-t-il `critDmgReduction[niveau de RELIQUE] x <summons/decoys allies
      adjacents au porteur>` du degat de CRIT recu par ce porteur, et le port fait-il pareil ? »

## L'ARTEFACT

`IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$
CreateCritDamageBonus` = `ForSubtraction(get_OwnerIsTarget, GetCritDmgReductionAmount())`, ou
`GetCritDmgReductionAmount` = `Multiply(ConfigVar(0x97 = critDmgReduction),
GetAdjacentFriendlySummonsAndDecoysCount())` et le compteur est l'arbre
`Count(UnitsWithTrait(AdjacentFriends(Owner), 0x2 = Summon) + UnitsWithTrait(AdjacentFriends(Owner),
0x41d = Decoy))`. Sa `CreateActiveCondition` est `AmountIsGreaterThanZero(<le MEME compteur>)`.

## LE MONTAGE, et pourquoi chaque piece y est

  * `genesKelermorph` est l'un des TROIS porteurs autorises d'`AmuletOfTheVoidwyrm`
    (`catalog_inject --list-relics`), et il est AU POOL -- donc etat 2 de la gate relique :
    `rl_duel build --equip-relic`, qui pose les TROIS ecritures d'un bloc (`TertiaryAbility`,
    `TertiaryAbilityLevel >= 1`, config dans `BC.Abilities.PassiveAbilities`).
  * Le porteur est la **CIBLE** (`get_OwnerIsTarget`), donc il est cote `a-units` et c'est
    l'attaquant qui doit criter -> `--crit` (p-units) et non `--crit-target`.
  * `--crit 100,2000` : TOUS les coups critent, donc aucun tirage ; et `2000` laisse la marge
    necessaire pour que `Math.Max(0, GetStat(10) + somme)` de `CalculateCriticalDamage` NE SATURE
    PAS a 0 -- une saturation ferait s'accorder deux modeles differents (regime DEGENERE).
  * Les COMPAGNONS portent le trait par `--unit-stat '<vid>:Traits=["Decoy"]'` : c'est le substrat
    d'ENTITE (`BC.Units[].Traits` -> `BaseUnitComponent`) que `UnitsWithTrait` lit (#264), le MEME
    champ qu'un vrai summon renseignerait. Les vrais summons ne sont PAS spawnables par `--a-units`
    (hors pool), et leur amener un summoner ne donnerait aucun controle sur `n`.
  * `n` (le nombre de compagnons ADJACENTS) est le levier : `n = 0` doit rendre l'effet INACTIF,
    `n = 1` et `n = 2` doivent rendre DEUX reductions differentes -- c'est ce qui prouve le PRODUIT
    et interdit de fitter un scalaire.

## LES BRAS

  1. LIVE -- le natif, l'oracle ;
  2. port (etat livre) -- doit egaler le live ;
  3. `NOCHANNEL` -- l'effet retire d'`EFFECT_CLASSES` (retombe sur `BaseEffect`, canal `None`) :
     doit DIVERGER ssi `n > 0`. C'est ce qui interdit l'accord degenere ;
  4. `PASSIF` -- le callable `tertiary_ability_state_of` retire du contexte : le port retombe alors
     sur `ability_level` (le niveau des PASSIFS, 50 en runner normalise -> dernier palier). Doit
     DIVERGER des que le niveau de relique demande n'est pas le dernier palier. C'est ce qui prouve
     que le canal TERTIAIRE mord.

Usage :
    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 0,1,2
    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 1 --level 10
    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 1 --trait Summon --board C1_74
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

CARRIER = "genesKelermorph"          # porteur autorise d'AmuletOfTheVoidwyrm, AU POOL
COMPANIONS = ("genesMagus", "genesPrimus")   # les deux porteurs de trait, patches par --unit-stat
ATTACKER = "blackHaarken"            # melee, plusieurs coups -- la salve est lisible coup par coup
EFFECT_NAME = "AmuletOfTheVoidwyrm_CritDamageReduction"   # cle EFFECT_CLASSES == nom decisionView
ABILITY_ID = "AmuletOfTheVoidwyrm"   # TriggeredAbilityType 0x5b8 = 1464 (la CONFIG)
VAR_KEY = "critDmgReduction"         # AbilityVariableType 0x97 = 151


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def paliers_du_gameconfig() -> list:
    """`critDmgReduction` RELU du gameconfig, jamais code en dur -- meme lecture que le port."""
    import gameconfig as GC
    arr = ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get(VAR_KEY)
    if not arr:
        raise SystemExit("%s.variables.%s absent du gameconfig" % (ABILITY_ID, VAR_KEY))
    return [int(x) for x in arr]


def _garde_regime(level: int, paliers: list, n_max: int, crit_dmg: int) -> None:
    """GARDES DE REGIME, jouees AVANT tout montage. Chacune ferme une porte de vert-qui-ne-mesure-rien.

      * niveau hors paliers -> `TryGetVariableArrayForLevel` CLAMPE au dernier, donc le bras
        « niveau » ne discriminerait plus rien ;
      * `GetStat(10) + somme <= 0` -> `Math.Max(0, .)` SATURE : port et natif rendraient tous deux
        le meme degat non-critique, accord DEGENERE (deux modeles algebriquement confondus sur le
        point mesure) ;
      * niveau == dernier palier -> le bras `PASSIF` ne peut PAS mordre (le repli clampe justement
        au dernier palier), donc sa contre-epreuve serait vide."""
    if not (1 <= level <= len(paliers)):
        raise SystemExit("niveau %d hors des %d paliers de %s : le clamp haut de "
                         "`AbilityConfiguration$$TryGetVariableArrayForLevel` rendrait le bras "
                         "NIVEAU non discriminant" % (level, len(paliers), ABILITY_ID))
    v = paliers[level - 1]
    if crit_dmg - v * n_max <= 0:
        raise SystemExit("SATURATION : critDamage=%d - %d x %d <= 0, `Math.Max(0, .)` de "
                         "CalculateCriticalDamage confondrait les modeles (regime DEGENERE). "
                         "Augmenter --crit-damage." % (crit_dmg, v, n_max))
    if level == len(paliers):
        print("   [note] niveau == dernier palier : le bras PASSIF ne peut pas mordre "
              "(le repli clampe au dernier palier). Il sera SAUTE.")
    print("   %s.%s[%d] = %d  (paliers %s..%s)" % (ABILITY_ID, VAR_KEY, level, v,
                                                   paliers[0], paliers[-1]))


def _hits_of(res, caster, target) -> tuple:
    """Degats PAR COUP : les `tags` des events d'`applyAction`, cle `Amount`, filtres sur la paire."""
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    out = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Attacker_Id") == caster and td.get("Target_Id") == target:
            out.append(int(td["Amount"]))
    return bool(a0.get("ok")), out


def build(a, tag, level):
    fd, sf = tempfile.mkstemp(prefix="probe_589r1r1r2r1_%s_" % tag, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--p-units", ATTACKER,
            "--a-units", "%s,%s,%s" % (CARRIER, COMPANIONS[0], COMPANIONS[1]),
            "--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
            "--unit-stat", '%s:Traits=["%s"]' % (COMPANIONS[0], a.trait),
            "--unit-stat", '%s:Traits=["%s"]' % (COMPANIONS[1], a.trait),
            # ⚠ `Ambush` (UnitTrait 1052) RETIRE du porteur : les TROIS porteurs autorises
            # d'`AmuletOfTheVoidwyrm` le portent, et une unite en embuscade n'est pas CIBLABLE --
            # l'attaque part alors sans erreur et ne mute RIEN (mesure : `mutated: false`,
            # `changes: []`). Le trait n'a aucun rapport avec le canal mesure.
            "--unit-stat", '%s:Traits=["Hero"]' % CARRIER,
            # L'ATTAQUANT est reduit a `Hero` pour la MEME raison de LISIBILITE : `LetTheGalaxyBurn`
            # ajoute des coups dont le compte depend de la cible (`LetTheGalaxyBurnEffect$$
            # CreateAdditionalHits`) et `Terrifying` pose un effet defensif -- deux canaux valides
            # AILLEURS, qui ne feraient ici que brouiller la salve qu'on lit coup par coup.
            "--unit-stat", '%s:Traits=["Hero"]' % ATTACKER,
            "--hp-target", "900000", "--hp-player", "900000",
            "--no-ai", "--crit", "100,%d" % a.crit_damage, "--block-target", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (tag, (p.stderr or p.stdout or "")[-800:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _stage_geo(h, board, marchables, occupe, carrier, att, comps, verbose):
    """Le bras SUBSTRAT : un compagnon a distance hex 1 du porteur mais ABSENT de sa liste
    d'adjacence CAPTUREE (`boardGraph.neighbours` == `connectivity`, dans les DEUX sens).

    ⚠ CE BRAS A ETE ECRIT A L'ENVERS, et la mesure l'a retourne. Il attendait d'abord que le natif
    ne compte PAS ce voisin (substrat `IterateAdjacentTiles`, celui de `BattleQuery$$GetAdjacentUnits`
    et d'`IsCharging`). MESURE sur `C3_14`, porteur en `(5,4)`, compagnon en `(5,3)` -- meme
    elevation 4, donc la porte `|dElev| < 2` ne joue pas, et l'arete manque des deux cotes de la
    capture : le natif COMPTE ce voisin. C'est le meme fait que le depot avait deja mesure sur
    l'AUTRE consommateur du meme sous-arbre (`Units(AdjacentTiles(...))` du splash de FragBomb,
    cf. `runner/operations/triggers/base.py::_adjacent_damageable_enemies`), et il est ici recoupe
    par un canal INDEPENDANT (l'activite d'un effet, pas un splash).

    Le bras mesure donc « le natif compte un voisin GEOMETRIQUE que la capture ne liste pas, et le
    port aussi » -- `_within` filtre par `hexgeo.distance <= radius` et ne se sert de
    `board.neighbours_native` que pour l'ORDRE. Il REFUSE si le board n'offre aucune paire
    divergente : il ne rend jamais un vert qui ne mesure rien."""
    import hexgeo
    plan = None
    for tid in sorted(marchables, key=lambda t: (-len(board.neighbours_native(t)), t)):
        anchor = board.coord(tid)
        if anchor in occupe:
            continue
        nat = {board.coord(v) for v in board.neighbours_native(tid)}
        geo = [board.coord(t) for t in marchables
               if hexgeo.distance(board.coord(t), anchor) == 1
               and board.coord(t) not in nat and board.coord(t) not in occupe]
        libres_nat = [c for c in nat if c not in occupe
                      and board.walkable(board.id_at(c[0], c[1]))]
        if not geo or not libres_nat:
            continue
        loin = [board.coord(t) for t in marchables
                if board.coord(t) not in occupe
                and hexgeo.distance(board.coord(t), anchor) >= 4]
        if not loin:
            continue
        plan = (anchor, geo, libres_nat, loin)
        break
    if plan is None:
        return None, ("aucune paire (hex-adjacente, NON voisine stockee) libre sur ce board -- "
                      "le bras GEOMETRIQUE ne discriminerait RIEN ici")
    anchor, geos, contacts, loins = plan

    def _pose(uid, cands, quoi):
        """Un `place` peut echouer sur une tuile pourtant libre AU MOMENT DU CALCUL (une unite y a
        ete posee entre-temps) : on essaie les candidats dans l'ordre plutot que d'abandonner sur
        le premier -- c'est du montage, pas de la mesure."""
        for c in cands:
            if h.place(uid, c):
                return c
        return None

    # ORDRE : porteur, puis ATTAQUANT (le contact natif est la ressource la plus rare), puis les
    # deux compagnons. A chaque etape les candidats sont re-filtres sur l'occupation REELLE.
    if not h.place(carrier["id"], anchor):
        return None, "placement du porteur refuse"

    def _occ():
        return {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                for u in h.alive()}

    o = _occ()
    contact = _pose(att["id"], [c for c in contacts if c not in o], "CONTACT")
    if contact is None:
        return None, "placement de l'attaquant refuse"
    o = _occ()
    geo_pos = _pose(comps[0]["id"], [c for c in geos if c not in o], "GEO")
    if geo_pos is None:
        return None, "placement du compagnon GEOMETRIQUE refuse"
    o = _occ()
    if _pose(comps[1]["id"], [c for c in loins if c not in o], "LOIN") is None:
        return None, "placement du second compagnon refuse"

    dv = h.dview()
    carrier = h.by_visual(CARRIER, dv)
    att = h.by_visual(ATTACKER, dv)
    cp = carrier.get("pos") or {}
    ctile = board.id_at(cp.get("col"), cp.get("row"))
    nat = {board.coord(v) for v in board.neighbours_native(ctile)}
    u0 = h.by_visual(COMPANIONS[0], dv)
    p0 = (u0 or {}).get("pos") or {}
    pos0 = (p0.get("col"), p0.get("row"))
    if hexgeo.distance(pos0, (cp["col"], cp["row"])) != 1 or pos0 in nat:
        return None, ("le compagnon n'est pas dans le regime voulu (hex-adjacent ET non stocke) : "
                      "pos=%s nat=%s" % (pos0, sorted(nat)))
    # GARDE DE MONTAGE : le SECOND compagnon doit etre HORS de tout voisinage du porteur, sinon
    # c'est LUI qui allumerait l'effet et le bras n'accuserait pas ce qu'il croit.
    u1 = h.by_visual(COMPANIONS[1], dv)
    p1 = (u1 or {}).get("pos") or {}
    pos1 = (p1.get("col"), p1.get("row"))
    if hexgeo.distance(pos1, (cp["col"], cp["row"])) <= 1 or pos1 in nat:
        return None, ("le SECOND compagnon est proche du porteur (%s) -- le bras ne discrimine "
                      "rien" % (pos1,))
    if verbose:
        print("    porteur=%s | GEO=%s (hex %d, stocke=%s) | LOIN=%s (hex %d) | voisins stockes=%s"
              % ((cp["col"], cp["row"]), pos0,
                 hexgeo.distance(pos0, (cp["col"], cp["row"])), pos0 in nat, pos1,
                 hexgeo.distance(pos1, (cp["col"], cp["row"])), sorted(nat)))
    dvi = h.rpc("decisionView", {"runnerId": h.rid, "maxRank": 1, "allAbilities": True,
                                 "includeInactive": True}, 90)
    cu = next((u for u in (dvi.get("units") or []) if u.get("id") == carrier["id"]), None)
    effs = {e.get("name"): e.get("active") for e in ((cu or {}).get("effects") or [])}
    actif = bool(effs.get(EFFECT_NAME))
    if not actif:
        return None, ("REFUTATION : le natif ne compte PAS ce voisin hex non capture -- le "
                      "substrat d'`AdjacentTilesSelector` serait la liste STOCKEE, ce qui "
                      "contredirait la mesure de `_adjacent_damageable_enemies`. A instruire.")
    atk_type = h.normal_attack_type(att["id"], dv)
    rec = {"caster": att["id"], "target": carrier["id"], "ability_type": int(atk_type),
           "n": 1, "anchor": anchor, "contact": contact, "step_to": None,
           "actif_natif": actif, "geo": pos0}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    if verbose:
        print("    ancre=%s compagnon GEO=%s (hex 1, NON stocke) contact=%s | effet actif = %s"
              % (anchor, pos0, contact, actif))
    return rec, None


def stage(h, n, verbose=False, geo_only=False):
    """Monte le regime `n` compagnons ADJACENTS et rend `(rec, raison)`.

    L'ADJACENCE est celle du NATIF (`board.neighbours_native` = la liste STOCKEE que
    `AdjacentTilesSelector$$Select` enumere via `IterateAdjacentTiles`), JAMAIS `hexgeo.distance
    == 1` : sur un board a `Bridge` les deux different, et c'est le substrat stocke qui fait foi.

    ORDRE : cycle de tour D'ABORD (les compagnons portent un trait qui peut declencher
    `PlayAutomaticUnits`), placements ENSUITE -- on veut que les positions LUES au snapshot soient
    celles qu'on a posees."""
    import hexgeo
    # ⚠ `my_player` AVANT `reach_my_turn` : sans lui le harnais le devine
    # (`alive(dv)[0].owner`) et peut s'arreter sur le tour de l'AUTRE camp -- l'attaque part alors
    # hors tour et rend `mutated: false` SANS erreur (mesure : `abilityTargets.playerId` = 4 alors
    # que l'attaquant appartient au joueur 3).
    dv = h.dview()
    att = h.by_visual(ATTACKER, dv)
    if att is None:
        return None, "attaquant absent du deploiement"
    h.my_player = att.get("owner")
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    dv = h.dview()
    att = h.by_visual(ATTACKER, dv)
    carrier = h.by_visual(CARRIER, dv)
    if att is None or carrier is None:
        return None, "attaquant ou porteur absent du deploiement"
    comps = [h.by_visual(c, dv) for c in COMPANIONS]
    if any(c is None for c in comps):
        return None, "un compagnon est absent du deploiement"

    # --- choix de l'ancre : il faut n voisins NATIFS pour les compagnons + 1 pour l'attaquant -----
    board = h.board
    occupe = set()
    for u in h.alive(dv):
        p = u.get("pos") or {}
        if p.get("col") is not None:
            occupe.add((p["col"], p["row"]))
    pilotees = {carrier["id"], att["id"]} | {c["id"] for c in comps}
    for u in h.alive(dv):
        if u.get("id") in pilotees:
            p = u.get("pos") or {}
            occupe.discard((p.get("col"), p.get("row")))     # elles vont liberer leur case
    marchables = [t for t in sorted(board.by_id) if board.walkable(t)]

    def _nat_voisins(tid):
        out = []
        for v in board.neighbours_native(tid):
            c = board.coord(v)
            if board.walkable(v) and c not in occupe:
                out.append(c)
        return out

    if geo_only:
        # BRAS SUBSTRAT (cf. `_stage_geo` : il a ete ECRIT A L'ENVERS et la mesure l'a retourne).
        return _stage_geo(h, board, marchables, occupe, carrier, att, comps, verbose)

    plan = None
    # ancres d'abord les MIEUX ENTOUREES (au sens NATIF) : une tuile de coin n'a que 2 voisins
    # stockes et ne peut porter ni les compagnons ni le contact.
    for tid in sorted(marchables, key=lambda t: (-len(board.neighbours_native(t)), t)):
        anchor = board.coord(tid)
        if anchor in occupe:
            continue
        vs = _nat_voisins(tid)
        if len(vs) < n + 1:
            continue
        loin = [board.coord(t) for t in marchables
                if board.coord(t) not in occupe
                and hexgeo.distance(board.coord(t), anchor) >= 4
                and board.coord(t) not in vs]
        if len(loin) < (len(COMPANIONS) - n):
            continue
        plan = (anchor, vs[:n], vs[n], loin)
        break
    if plan is None:
        return None, "geometrie non realisable (n=%d) : pas d'ancre a %d voisins NATIFS libres" % (
            n, n + 1)
    anchor, proches, contact, loin = plan

    if not h.place(carrier["id"], anchor):
        return None, "placement du porteur refuse"
    for i, c in enumerate(comps):
        dest = proches[i] if i < n else loin[i - n]
        if not h.place(c["id"], dest):
            return None, "placement du compagnon %s refuse" % c.get("visualId")
    if not h.place(att["id"], contact):
        return None, "placement de l'attaquant refuse"

    # --- l'etat MESURE, jamais suppose ------------------------------------------------------------
    dv = h.dview()
    carrier = h.by_visual(CARRIER, dv)
    att = h.by_visual(ATTACKER, dv)
    ctile = board.id_at(*[(carrier.get("pos") or {}).get(k) for k in ("col", "row")])
    voisins_natifs = {board.coord(v) for v in board.neighbours_native(ctile)}
    n_mesure = 0
    for c in COMPANIONS:
        u = h.by_visual(c, dv)
        p = (u or {}).get("pos") or {}
        if (p.get("col"), p.get("row")) in voisins_natifs:
            n_mesure += 1
    if n_mesure != n:
        return None, "n MESURE = %d != %d voulu (les compagnons ne sont pas ou on croit)" % (
            n_mesure, n)

    dvi = h.rpc("decisionView", {"runnerId": h.rid, "maxRank": 1, "allAbilities": True,
                                 "includeInactive": True}, 90)
    cu = next((u for u in (dvi.get("units") or []) if u.get("id") == carrier["id"]), None)
    effs = {e.get("name"): e.get("active") for e in ((cu or {}).get("effects") or [])}
    actif = effs.get(EFFECT_NAME)
    # `CreateActiveCondition` = `AmountIsGreaterThanZero(<le compteur>)` : c'est un OBSERVABLE
    # NATIF de l'etage COMPTEUR, independant du degat.
    if bool(actif) != (n > 0):
        return None, ("CreateActiveCondition natif = %s pour n=%d (attendu %s) -- effets: %s"
                      % (actif, n, n > 0, sorted(effs)))

    atk_type = h.normal_attack_type(att["id"], dv)
    rec = {"caster": att["id"], "target": carrier["id"], "ability_type": int(atk_type),
           "n": n_mesure, "anchor": anchor, "contact": contact, "step_to": None,
           "actif_natif": bool(actif)}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    if verbose:
        print("    ancre=%s contact=%s | n natif mesure = %d | effet actif = %s"
              % (anchor, contact, n_mesure, actif))
    return rec, None


def strike(h, rec):
    live = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(rec["ability_type"])}}, 60)
    ok, hits = _hits_of(live, rec["caster"], rec["target"])
    if not ok or not hits:
        return None, "attaque live refusee/vide (%s)" % str(live)[:200]
    if not any(u.get("id") == rec["target"] for u in h.alive()):
        return None, "porteur MORT pendant la salve -- flux live tronque"
    return hits, None


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE de la MEME attaque, RNG neutralise par le dump pris apres le montage.

    `NOCHANNEL` : l'effet retire d'`EFFECT_CLASSES` AVANT `load_state` -- la FACTORY le fait alors
    retomber sur `BaseEffect`, dont `create_effect_crit_damage_bonus_for_attack` rend `None`. C'est
    la vue « d'AVANT ce port ».

    `PASSIF` : le callable `tertiary_ability_state_of` retire du contexte du canal -- le port
    retombe sur `ability_level` (le niveau des PASSIFS). C'est la vue « sans le canal #357 ».
    Les deux mutations sont restaurees en `finally`."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.runner.operations import damage as D
    saved = EFFECT_CLASSES.get(EFFECT_NAME)
    orig = D.AttackDamageOperation._crit_board
    try:
        if mutate == "NOCHANNEL":
            EFFECT_CLASSES.pop(EFFECT_NAME, None)
        if mutate == "PASSIF":
            def _sans_tertiaire(state, att_id, tgt_id):
                d = dict(orig(state, att_id, tgt_id))
                d.pop("tertiary_ability_state_of", None)
                return d
            D.AttackDamageOperation._crit_board = staticmethod(_sans_tertiaire)
        return h.replay_offline(rec)["per_hit"]
    finally:
        if saved is not None:
            EFFECT_CLASSES[EFFECT_NAME] = saved
        D.AttackDamageOperation._crit_board = orig


def etages(h, rec) -> dict:
    """DECOMPOSITION PAR ETAGE du port, sur l'etat OFFLINE reconstruit -- jamais un scalaire fitte.

    Rend, dans l'ordre du natif : le COMPTEUR (`GetAdjacentFriendlySummonsAndDecoysCount`), le
    couple `(level, mult)` de `GetAbilityState(effect)`, la valeur de `ConfigVar(0x97)`, et le
    scalaire SIGNE que le canal verse (`ForSubtraction`). C'est ce qui permet de dire QUEL etage
    bouge quand le degat diverge."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.runner.components import (adjacent_friendly_summons_and_decoys_count,
                                          unit_state_for_effects)
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.base import triggered_ability_state
    from engine.entities.stats import StatType
    st = h.offline_state(rec)
    oid, aid = int(rec["target"]), int(rec["caster"])
    out = {"compteur": adjacent_friendly_summons_and_decoys_count(st, oid),
           "ability_state": triggered_ability_state(st, oid, ABILITY_ID)}
    effs = st.effects.active_effects(oid, unit_state_for_effects(st, oid)) if st.effects else []
    cible = next((e for e in effs if getattr(e, "name", None) == EFFECT_NAME), None)
    out["effet_actif_port"] = cible is not None
    ctx = dict(AttackDamageOperation._crit_board(st, aid, oid))
    ctx.update({"att_id": aid, "tgt_id": oid, "owner_id": oid})
    out["bonus_signe"] = (cible.create_effect_crit_damage_bonus_for_attack(ctx)
                          if cible is not None else None)
    tsc = st.get_entity(oid)
    out["crit_damage_base_cible"] = None
    ae = st.get_entity(aid)
    if ae is not None:
        from engine.runner.components import StatsComponent
        sc = ae.get_component(StatsComponent)
        if sc is not None:
            out["crit_damage_base_attaquant"] = sc.ctx.stat(StatType.CRIT_DAMAGE)
            out["crit_chance_base_attaquant"] = sc.ctx.stat(StatType.CRIT_CHANCE)
    _ = tsc, EFFECT_CLASSES
    return out


def run_case(a, rpc, Board, Harness, n, level, paliers) -> int:
    rid, sf = build(a, "n%d_l%d" % (n, level), level)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage(h, n, a.verbose, geo_only=a.geo_only)
        if rec is None:
            print("[n=%d lvl=%d] REFUS : %s" % (n, level, why))
            return 2
        if a.geo_only:
            n = 1                       # MESURE : le natif COMPTE le voisin geometrique (cf. _stage_geo)
        live, why = strike(h, rec)
        if live is None:
            print("[n=%d lvl=%d] REFUS : %s" % (n, level, why))
            return 2
        off = replay(h, rec)
        k = len(live)
        accord = (off[:k] == live)

        # CONTRE-EPREUVE 1 : sans le canal, le rejeu doit CHANGER ssi n > 0.
        mut = replay(h, rec, mutate="NOCHANNEL")
        mord = (mut[:k] != off[:k])
        attendu = (n > 0)

        # CONTRE-EPREUVE 2 : sans le canal TERTIAIRE, le port lit le niveau PASSIF (-> dernier
        # palier). Ne peut mordre que si n > 0 ET que le niveau demande n'est pas le dernier.
        passif_attendu = (n > 0) and (level != len(paliers))
        mut2 = replay(h, rec, mutate="PASSIF")
        mord2 = (mut2[:k] != off[:k])

        rc = 0
        if not accord:
            rc |= 1
        if mord != attendu:
            rc |= 1
        if mord2 != passif_attendu:
            rc |= 1
        v = paliers[level - 1]
        print("[n=%d lvl=%d] reduction attendue = %d x %d = %d | actif_natif=%s"
              % (n, level, v, n, v * n, rec["actif_natif"]))
        if a.verbose:
            print("        ETAGES port %s" % (etages(h, rec),))
        print("        LIVE      %s" % (live[:6],))
        print("        OFFLINE   %s  accord=%s" % (off[:k][:6], accord))
        print("        NOCHANNEL %s  mord=%s (attendu %s)" % (mut[:k][:6], mord, attendu))
        print("        PASSIF    %s  mord=%s (attendu %s)" % (mut2[:k][:6], mord2, passif_attendu))
        return rc
    finally:
        # Le cache `unitAbilityStates` est indexe par LABEL de runner, et un id dispose peut etre
        # recycle par un build ulterieur -> purge obligatoire, sinon le run suivant lirait la
        # relique du precedent.
        from engine.runner.snapshot import clear_ability_states_cache
        clear_ability_states_cache("build#%s" % rid)
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--crit-damage", type=int, default=2000,
                    help="CritDamage des p-units. Assez GRAND pour que Math.Max(0, .) de "
                         "CalculateCriticalDamage ne sature pas (sinon regime DEGENERE).")
    ap.add_argument("--n", default="0,1,2", help="nombre de compagnons ADJACENTS (un runner par n)")
    ap.add_argument("--level", type=int, default=3, help="niveau de la RELIQUE (1..10)")
    ap.add_argument("--trait", default="Decoy", choices=("Decoy", "Summon"),
                    help="le trait pose sur les compagnons : les DEUX `UnitsWithTrait` natifs")
    ap.add_argument("--geo-only", action="store_true",
                    help="BRAS GEOMETRIQUE : le compagnon est a distance hex 1 du porteur mais "
                         "ABSENT de sa liste d'adjacence STOCKEE. Le natif ne doit PAS le compter "
                         "(`AdjacentTilesSelector` enumere `IterateAdjacentTiles`). Un board sans "
                         "paire divergente fait REFUSER le bras, jamais passer.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    paliers = paliers_du_gameconfig()
    ns = [int(x) for x in a.n.split(",") if x.strip()]
    print("== #589-r1-r1-r2-r1 AmuletOfTheVoidwyrm_CritDamageReduction -- trait=%s" % a.trait)
    _garde_regime(a.level, paliers, max(ns) if ns else 1, a.crit_damage)

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    # ⚠ CANAL RELIQUE. `load_state` tire `unitAbilityStates` elle-meme, mais SEULEMENT si un
    # transport AMBIANT est lie (`snapshot.bind_live_rpc`, #357/#363) -- la fixture `rpc` des tests
    # le pose, un probe doit le faire. Sans lui, `UnitContext.tertiary_ability` reste `None` et
    # `triggered_ability_state` retombe sur le couple PASSIF : MESURE (avant correctif du probe),
    # `ability_state = (50, 180)` au lieu de `(3, 100)`, donc `critDmgReduction` lu au dernier
    # palier (579) au lieu de celui du niveau demande (432). Le tri-etat du port a fait son
    # travail -- c'est le HARNAIS qui ne fournissait pas le canal.
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)
    rc = 0
    for n in ns:
        rc |= run_case(a, rpc, Board, ChargeRegimeHarness, n, a.level, paliers)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
