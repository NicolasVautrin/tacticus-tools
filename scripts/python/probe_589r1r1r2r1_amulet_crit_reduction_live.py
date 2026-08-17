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


#: les deux seuls traits que le compteur natif lit -- toute autre valeur serait un bras MUET
#: (le compagnon ne compterait pas, et le probe rendrait un zero qui accuserait le port).
TRAITS_COMPTES = ("Decoy", "Summon")


def _traits_json(spec: str) -> str:
    """`"Summon,Decoy"` -> `"Summon","Decoy"`. REFUSE tout trait hors des deux comptes : un trait
    inerte ferait tomber `n` a zero sans qu'aucune assertion ne designe la cause."""
    noms = [t.strip() for t in str(spec).split(",") if t.strip()]
    if not noms:
        raise SystemExit("--trait : liste vide")
    inconnus = [t for t in noms if t not in TRAITS_COMPTES]
    if inconnus:
        raise SystemExit("--trait : %s hors des traits COMPTES par le natif %s"
                         % (inconnus, list(TRAITS_COMPTES)))
    return ",".join('"%s"' % t for t in noms)


def build(a, tag, level):
    fd, sf = tempfile.mkstemp(prefix="probe_589r1r1r2r1_%s_" % tag, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--p-units", ATTACKER,
            "--a-units", "%s,%s,%s" % (CARRIER, COMPANIONS[0], COMPANIONS[1]),
            "--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
            # `Traits=[...]` REMPLACE la liste d'entite. Une liste a DEUX traits arme le bras
            # UNION de `#589-r1-r1-r2-r1-r2` : le compteur natif est
            # `Count(UnitsWithTrait(.., Summon) op_Addition UnitsWithTrait(.., Decoy))`, et
            # `CombinedSelector$$SelectUnion` est `AddRange(left); AddRange(right)` -- le meme
            # compagnon y figure DEUX FOIS.
            "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[0], _traits_json(a.trait)),
            "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[1], _traits_json(a.trait)),
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


class MontageError(RuntimeError):
    """On REFUSE de rendre un verdict plutot que d'en fabriquer un depuis un montage muet."""


def _pos_de(u) -> tuple:
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def inventaire_traits(h, traits_comptes, dv=None) -> tuple:
    """FOYER UNIQUE de l'inventaire des porteurs de trait, cote NATIF
    (`combatSnapshot.units[].traits`, #233 : les traits REELLEMENT portes en bataille, veto
    compris). Rend `(porteurs, muets)`.

    POURQUOI IL EXISTE. `#589-r1-r1-r2-r1-r8` a mesure que le compteur natif
    (`AmuletOfTheVoidwyrm_CritDamageReductionEffect$$GetAdjacentFriendlySummonsAndDecoysCount`)
    comptait `genesSmnDecoy`, une unite presente au DEPLOIEMENT sur un voisin stocke du porteur --
    jamais le compagnon que le montage croyait mesurer. Un bras qui ne fige que les unites qu'il
    a lui-meme posees peut donc re-mesurer autre chose que ce qu'il annonce, et rendre un accord
    par COMPENSATION.

    La cle d'unite de `combatSnapshot` est `entityId`, PAS `id` : la lire de travers rend un
    inventaire d'anonymes -- exactement le genre de zero qui se lit << rien a signaler >>.

    TRI-ETAT : `traits == None` = capteur MUET pour cette unite -> elle sort dans `muets`, jamais
    dans une liste vide qui se lirait << personne ne porte le trait >>."""
    snap = h.rpc("combatSnapshot", {"runnerId": h.rid}, 60)
    units = (snap.get("units") if isinstance(snap, dict) else None) or []
    dv = dv if dv is not None else h.dview()
    par_id = {u.get("id"): u for u in (dv.get("units") or [])}
    porteurs, muets = [], []
    for u in units:
        eid, tr = u.get("entityId"), u.get("traits")
        if tr is None:
            muets.append(eid)
            continue
        portes = sorted(set(int(t) for t in tr) & set(traits_comptes))
        if portes:
            d = par_id.get(eid) or {}
            porteurs.append({"id": eid, "visualId": d.get("visualId") or u.get("visualId"),
                             "owner": d.get("owner"), "team": d.get("team"),
                             "pos": _pos_de(d), "alive": d.get("alive"),
                             "traits_comptes": portes})
    return porteurs, muets


def pousser_loin(h, ids, loins, quoi):
    """DEPLACE des unites vers des tuiles a hex >= 4 du porteur -- on FORCE la configuration, on ne
    subit pas la geometrie de spawn. Leve `MontageError` si une unite ne peut pas etre eloignee :
    un intrus laisse en place ferait mesurer autre chose que ce que le bras annonce."""
    for uid in ids:
        occ = {_pos_de(u) for u in h.alive()}
        if next((c for c in loins if c not in occ and h.place(uid, c)), None) is None:
            raise MontageError("impossible d'eloigner u%s (%s)" % (uid, quoi))


def _activite(h, carrier_id: int):
    """TRI-ETAT de la `CreateActiveCondition` native, LU sur `decisionView` (`includeInactive`) :
    `True`/`False` = mesure, `None` = l'effet est ABSENT du canal, donc NON MESURE -- jamais rabattu
    sur `False`, ce qui ferait passer un porteur SANS relique pour un compteur nul."""
    dvi = h.rpc("decisionView", {"runnerId": h.rid, "maxRank": 1, "allAbilities": True,
                                 "includeInactive": True}, 90)
    cu = next((u for u in (dvi.get("units") or []) if u.get("id") == carrier_id), None)
    for e in ((cu or {}).get("effects") or []):
        if e.get("name") == EFFECT_NAME:
            return bool(e.get("active"))
    return None


def _stage_geo(h, board, marchables, occupe, carrier, att, comps, verbose):
    """Le bras SUBSTRAT : un compagnon a distance hex 1 du porteur mais ABSENT de sa liste
    d'adjacence CAPTUREE (`boardGraph.neighbours` == `connectivity`, dans les DEUX sens).

    ⚠ CE BRAS A ETE ECRIT A L'ENVERS **DEUX FOIS**, et la seconde correction est celle-ci.
    Sa premiere version attendait que le natif ne compte PAS ce voisin ; une mesure sur `C3_14`
    (porteur `(5,4)`, compagnon `(5,3)`) l'a fait ecrire l'inverse -- « le natif COMPTE ce voisin »
    -- par INFERENCE depuis l'activite de l'effet. `#589-r1-r1-r2-r1-r8` a REFUTE cette inference :
    l'effet etait actif a cause de `genesSmnDecoy`, presente depuis le DEPLOIEMENT sur un voisin
    STOCKE, et le compagnon en `(5,3)` n'a jamais rien ajoute (compteur natif 1 -> 1 quand on le
    pose). C'etait un accord par COMPENSATION -- le port comptait 1 par geometrie, le natif 1 par
    l'intruse.

    LA CHAINE NATIVE NE LAISSE AUCUNE PORTE (relue de bout en bout dans `case-589-r1-r1-r2-r1-r8`
    sec.3) : `AdjacentTilesSelector$$Select` -> `IBattleQuery` slot 80 `IterateAdjacentTiles` ->
    `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` = `foreach id in tile.<+0x30>.<+0x10>`,
    une LISTE STOCKEE, aucune geometrie. **ATTENDU : INACTIF.**

    CE QUE CE BRAS FIGE MAINTENANT, et qui manquait : l'INVENTAIRE des porteurs de trait
    (`inventaire_traits`, cote NATIF) puis leur ELOIGNEMENT, avant toute lecture. `n` n'est plus
    ECRIT, il est DERIVE de l'occupation MESUREE de la liste stockee. Trois refus, aucun n'est un
    accord : capteur de traits muet, aucune paire divergente sur ce board, ou un porteur qu'on ne
    peut pas eloigner."""
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
        # >= 4 tuiles LOIN : il faut de quoi eloigner le SECOND compagnon **et** tous les porteurs
        # de trait que l'inventaire va reveler (il y en avait UN qu'aucune version anterieure ne
        # voyait). Une seule tuile suffisait a l'ancien bras -- c'est cette etroitesse qui laissait
        # l'intruse en place.
        if len(loin) < 4:
            continue
        plan = (anchor, geo, libres_nat, loin)
        break
    if plan is None:
        return None, ("aucune paire (hex-adjacente, NON voisine stockee) libre sur ce board, avec "
                      "au moins 4 tuiles a hex >= 4 pour eloigner les porteurs de trait -- le bras "
                      "GEOMETRIQUE ne discriminerait RIEN ici")
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

    # === INVENTAIRE NATIF DES PORTEURS DE TRAIT, puis ELOIGNEMENT ============================
    # C'est l'etape que ce bras n'avait JAMAIS faite (#589-r1-r1-r2-r1-r8) : il ne figeait que les
    # deux compagnons qu'il avait poses, et une unite du DEPLOIEMENT portant `Decoy` allumait
    # l'effet a leur place. On enumere donc les porteurs REELS, cote natif, et on pousse TOUT le
    # monde sauf le compagnon GEO -- y compris le second compagnon, qui n'a plus de traitement
    # special : il est un porteur comme un autre.
    from engine.entities.traits.unit_trait import UnitTrait
    traits_comptes = (int(UnitTrait.Summon), int(UnitTrait.Decoy))
    porteurs, muets = inventaire_traits(h, traits_comptes)
    if muets:
        return None, ("capteur `combatSnapshot.units[].traits` MUET pour %s -- l'inventaire ne "
                      "peut PAS etre rendu, et un inventaire partiel se lirait comme complet"
                      % (muets,))
    if not any(p["id"] == comps[0]["id"] for p in porteurs):
        return None, ("le compagnon GEO n'est pas dans l'inventaire NATIF des porteurs de %s -- "
                      "le montage `--unit-stat Traits=[...]` n'a pas mordu, le bras serait vide"
                      % (list(TRAITS_COMPTES),))
    a_eloigner = [p["id"] for p in porteurs if p["id"] != comps[0]["id"]]
    try:
        pousser_loin(h, a_eloigner, loins, "porteur de trait etranger au bras GEO")
    except MontageError as e:
        return None, str(e)

    dv = h.dview()
    carrier = h.by_visual(CARRIER, dv)
    att = h.by_visual(ATTACKER, dv)
    cp = carrier.get("pos") or {}
    ancre = (cp.get("col"), cp.get("row"))
    ctile = board.id_at(cp.get("col"), cp.get("row"))
    nat = {board.coord(v) for v in board.neighbours_native(ctile)}
    # === LE REGIME, RE-MESURE APRES DEPLACEMENT (jamais suppose) =============================
    porteurs, muets = inventaire_traits(h, traits_comptes, dv)
    if muets:
        return None, "capteur de traits MUET a la RE-mesure pour %s" % (muets,)
    amis = [p for p in porteurs if p.get("alive") and p.get("team") == carrier.get("team")]
    geo_amis = [p for p in amis
                if p["pos"] not in nat and hexgeo.distance(p["pos"], ancre) == 1]
    # `n` est DERIVE de la liste STOCKEE, pas ecrit : c'est la seule grandeur que le decompile
    # designe (`IterateAdjacentTiles` enumere `tile.<+0x30>.<+0x10>`).
    n_stockes = [p for p in amis if p["pos"] in nat]
    if len(geo_amis) != 1 or geo_amis[0]["id"] != comps[0]["id"]:
        return None, ("regime non atteint : il faut EXACTEMENT un porteur ami a hex 1 HORS liste "
                      "stockee, et que ce soit le compagnon GEO. porteurs amis = %s ; ancre = %s ; "
                      "voisins stockes = %s"
                      % ([(p["visualId"], p["pos"]) for p in amis], ancre, sorted(nat)))
    if n_stockes:
        return None, ("regime non atteint : %s porteur(s) ami(s) sur un voisin STOCKE (%s) -- le "
                      "bras mesurerait leur contribution et non celle du voisin GEOMETRIQUE"
                      % (len(n_stockes), [(p["visualId"], p["pos"]) for p in n_stockes]))
    pos0 = geo_amis[0]["pos"]
    if verbose:
        print("    porteur=%s | GEO=%s (hex 1, stocke=False) | voisins stockes=%s" %
              (ancre, pos0, sorted(nat)))
        print("    porteurs de trait NATIFS : %s"
              % ([(p["visualId"], p["pos"], p["team"],
                   hexgeo.distance(p["pos"], ancre)) for p in porteurs],))
    # === TEMOIN DIFFERENTIEL, et il est INDISPENSABLE ========================================
    # Le regime vise rend `n = 0` : LIVE et OFFLINE s'accordent, les deux contre-epreuves ne
    # mordent pas, et NOCHANNEL est un no-op. Un tel bras serait VERT meme si la relique n'etait
    # pas equipee, si le trait n'etait pas monte, ou si le porteur n'etait pas le bon. On mesure
    # donc TROIS etats sur le MEME runner, en ne deplacant qu'UNE unite :
    #   S1 GEO    (hex 1, HORS liste stockee) -> attendu INACTIF  <- LA question
    #   S2 STOCKE (un voisin de la liste)     -> attendu ACTIF    <- le controle POSITIF
    #   S3 RETOUR (le meme GEO)               -> attendu INACTIF  <- rien ne s'est fige
    # Sans S2, « inactif » ne prouverait rien ; sans S3, « actif en S2 » pourrait etre un etat
    # collant. C'est la forme mesuree par `probe_589r1r1r2r1r8_compteur_natif --bras sequence`.
    s1 = _activite(h, carrier["id"])
    if s1 is None:
        return None, ("l'effet %s est ABSENT du canal (meme `includeInactive`) -- non mesure, "
                      "jamais rabattu sur INACTIF" % EFFECT_NAME)
    occ = {_pos_de(u) for u in h.alive()}
    stocke = next((c for c in nat if c not in occ and board.walkable(board.id_at(c[0], c[1]))
                   and h.place(comps[0]["id"], c)), None)
    if stocke is None:
        return None, ("aucun voisin STOCKE libre pour le CONTROLE POSITIF -- sans lui, un "
                      "« inactif » en position GEO ne prouverait rien")
    s2 = _activite(h, carrier["id"])
    if not h.place(comps[0]["id"], pos0):
        return None, "retour du compagnon GEO en %s refuse -- S3 non mesurable" % (pos0,)
    s3 = _activite(h, carrier["id"])
    if verbose:
        print("    temoin differentiel : S1 GEO=%s  S2 STOCKE %s=%s  S3 RETOUR=%s"
              % (s1, stocke, s2, s3))
    if s2 is not True:
        return None, ("CONTROLE POSITIF MUET : sur un voisin STOCKE (%s) l'effet rend %r au lieu "
                      "d'ACTIF -- le montage est mort (relique, trait, ou porteur), et le bras "
                      "mesurerait un zero qui ne dit rien" % (stocke, s2))
    if s3 is not s1:
        return None, ("l'etat n'est pas REVERSIBLE (S1=%r, S3=%r) -- une lecture s'est figee, on "
                      "ne peut pas attribuer S1 a la position" % (s1, s3))
    actif = bool(s1)
    # ATTENDU : INACTIF. La `CreateActiveCondition` est `AmountIsGreaterThanZero(<le compteur>)`,
    # et le compteur n'enumere que la liste STOCKEE -- que plus aucun porteur ami n'occupe.
    if actif:
        return None, ("REFUTATION : le natif compte un voisin hex-1 ABSENT de la liste stockee, "
                      "alors que l'inventaire montre qu'aucun autre porteur ami n'est adjacent. "
                      "Cela contredirait la chaine relue en sec.3 de case-589-r1-r1-r2-r1-r8 "
                      "(`IterateAdjacentTiles` = `tile.<+0x30>.<+0x10>`). A instruire.")
    dv = h.dview()
    att = h.by_visual(ATTACKER, dv)
    atk_type = h.normal_attack_type(att["id"], dv)
    rec = {"caster": att["id"], "target": carrier["id"], "ability_type": int(atk_type),
           "n": len(n_stockes), "anchor": anchor, "contact": contact, "step_to": None,
           "actif_natif": actif, "geo": pos0, "temoin": {"S1_geo": s1, "S2_stocke": s2,
                                                         "S3_retour": s3, "stocke": stocke},
           "porteurs": [(p["visualId"], p["pos"], hexgeo.distance(p["pos"], ancre))
                        for p in porteurs]}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    if verbose:
        print("    ancre=%s compagnon GEO=%s (hex 1, NON stocke) contact=%s | n derive = %d | "
              "effet actif = %s" % (anchor, pos0, contact, rec["n"], actif))
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


def _etat_passif(state, unit_id: int) -> tuple:
    """La branche de REPLI de `runner/operations/triggers/base.py::triggered_ability_state` :
    `(ctx.passive_ability_level, ctx.ability_variables_multiplier)`. C'est ce que le port lirait si
    le discriminant TERTIAIRE (#357) n'existait pas -- la lecture que le bras `PASSIF` doit refuter.
    Le couple est LU du meme `UnitContext` que le foyer, jamais fabrique."""
    from engine.runner.components import StatsComponent
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        return (None, 100)
    return (getattr(ctx, "passive_ability_level", None),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE de la MEME attaque, RNG neutralise par le dump pris apres le montage.

    `NOCHANNEL` : l'effet retire d'`EFFECT_CLASSES` AVANT `load_state` -- la FACTORY le fait alors
    retomber sur `BaseEffect`, dont `create_effect_crit_damage_bonus_for_attack` rend `None`. C'est
    la vue « d'AVANT ce port ».

    `PASSIF` : la LECTURE FAUSSE « le port lit le slot PASSIF du porteur » -- c'est-a-dire la
    branche de REPLI de `runner/operations/triggers/base.py::triggered_ability_state`
    (`(ctx.passive_ability_level, ctx.ability_variables_multiplier)`, 50 en runner normalise ->
    dernier palier), SUBSTITUEE au callable. C'est la vue « sans le canal #357 ».

    ⚠ CE MUTANT ETAIT DEVENU INERTE, ET LE TEST QUI L'EXERCE ROUGISSAIT SUR `master` (mesure
    2026-08-17 : `test_amulet_voidwyrm_crit_reduction_live.py::test_le_niveau_lu_est_celui_de_la_
    relique_pas_du_passif[1]`, `passif == off == [2739, 2727, 3062, 2767]`, avant comme apres le
    correctif #922-r5). Il RETIRAIT le callable, en supposant que l'effet retomberait sur « le
    niveau des PASSIFS ». Ce n'est plus vrai : depuis la reparation du seeding tertiaire
    (#1005/#1081), `_seed_ability_owner_effects` bake le couple TERTIAIRE sur l'INSTANCE, donc le
    repli d'instance rend DEJA le bon niveau -- les deux voies coincidaient. C'est le patron « un
    changement de harnais perime la premisse d'un test » : ce n'est pas le PORT qui a regresse
    (l'assertion `ability_state[0] == level` passe des deux cotes), c'est le TEMOIN qui avait cesse
    de discriminer. MEME cause et MEME correctif que dans
    `probe_922_intoxicating_elixir_live.py` -- deux fichiers, un seul vice.

    Les deux mutations sont restaurees en `finally`."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.runner.operations import damage as D
    saved = EFFECT_CLASSES.get(EFFECT_NAME)
    orig = D.AttackDamageOperation._crit_board
    try:
        if mutate == "NOCHANNEL":
            EFFECT_CLASSES.pop(EFFECT_NAME, None)
        if mutate == "PASSIF":
            def _slot_passif(state, att_id, tgt_id):
                d = dict(orig(state, att_id, tgt_id))
                d["tertiary_ability_state_of"] = (
                    lambda oid, ability, _st=state: _etat_passif(_st, int(oid)))
                return d
            D.AttackDamageOperation._crit_board = staticmethod(_slot_passif)
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
            # `n` est DERIVE par `_stage_geo` de l'occupation MESUREE de la liste STOCKEE, jamais
            # ecrit. L'ancienne ligne posait `n = 1` sur l'inference « le natif COMPTE le voisin
            # geometrique » que `#589-r1-r1-r2-r1-r8` a REFUTEE : ce 1 venait d'une intruse
            # (`genesSmnDecoy`) que le bras n'inventoriait pas.
            n = int(rec["n"])
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
        if a.geo_only:
            # Ce que le bras a REELLEMENT fige : l'inventaire natif des porteurs et le temoin
            # differentiel. Sans ces deux lignes a l'ecran, un `n = 0` se relirait comme
            # « le montage n'a rien fait ».
            print("        PORTEURS  %s" % (rec.get("porteurs"),))
            print("        TEMOIN    %s" % (rec.get("temoin"),))
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
    ap.add_argument("--trait", default="Decoy",
                    help="le(s) trait(s) pose(s) sur les compagnons, separes par une virgule, "
                         "parmi Decoy / Summon (les DEUX `UnitsWithTrait` natifs). "
                         "`--trait Summon,Decoy` arme le bras UNION (#589-r1-r1-r2-r1-r2) : "
                         "`TargetsSelector$$op_Addition` -> `CombinedSelector` mode 1 -> "
                         "`SelectUnion` = `AddRange; AddRange`, AUCUN dedoublonnage, donc un "
                         "compagnon portant les DEUX compte DEUX FOIS. Attendu : la reduction "
                         "d'un bras `--n 1 --trait Summon,Decoy` doit egaler celle d'un bras "
                         "`--n 2 --trait Decoy`. Le regime n'est pas atteignable par le "
                         "gameconfig (0 unite sur 683 porte les deux traits, re-mesure sur "
                         "`rnca9r7q6c`) mais il l'est PAR LE MONTAGE : le natif ne lit que "
                         "`HasFlag(unit, trait)`, donc `BC.Units[].Traits`, que `--unit-stat` "
                         "ecrit.")
    ap.add_argument("--geo-only", action="store_true",
                    help="BRAS SUBSTRAT : le compagnon est a distance hex 1 du porteur mais ABSENT "
                         "de sa liste d'adjacence STOCKEE. Le natif ne doit PAS le compter "
                         "(`AdjacentTilesSelector` -> `IterateAdjacentTiles` = `tile.<+0x30>."
                         "<+0x10>`, une liste STOCKEE). Le bras INVENTORIE d'abord les porteurs de "
                         "trait cote natif (`combatSnapshot.units[].traits`) et les ELOIGNE tous "
                         "sauf le compagnon GEO : sans cet inventaire il re-mesurait une intruse "
                         "(#589-r1-r1-r2-r1-r8). Un board sans paire divergente, un capteur de "
                         "traits muet ou un porteur qu'on ne peut pas eloigner font REFUSER le "
                         "bras, jamais passer.")
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
