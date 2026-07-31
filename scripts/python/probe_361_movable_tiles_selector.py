"""probe #370 (residu `#361-r2`) -- QUEL maillon de `GetTileToMoveTo` rend vide dans le playbook.

LA QUESTION, BINAIRE
--------------------
`#386` a referme la localisation : les batchs 3/4 de `RammingSpeedPlaybook$$MakeDamagePredictions`
sont absents parce que les deux `ComparablePlaybook<T>$$GenerateAttackPredictions` rendent VIDE,
gate OUVERTE, composition `AdjacentUnits` mesuree VIVANTE 3/3. Reste l'`origin` : l'arbre
`RammingSpeedAbility$$GetTileToMoveTo`, qui rend la bonne tuile dans le contexte de
`RammingSpeedAbility$$GetDynamicInvalidTargetReason` (cast reel, MATCH 2/2) et VIDE dans celui du
playbook. **Lequel de ses maillons ?**

CE QUE LE CAPTEUR OBSERVE (`frida/hooks/features/ai-step/movable-tiles-probe.ts`, flag `tileProbe`)
---------------------------------------------------------------------------------------------------
`IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select` est le SEUL noeud de la chaine
haute dont un retour vide est SILENCIEUX -- partout ailleurs un maillon absent tombe dans le
thrower. Son corps porte trois issues, lues au decompile :

    entity   = unitSelector.<slot 7>(ctx)          ; if (entity == null)   -> List VIDE
    fromTile = unitTileSelector.<slot 0xc>(ctx)    ; if (fromTile == null) -> List VIDE
    return     IBattleQuery.GetMovableTilesInRange(entity, fromTile, ignoreFlags, options)

`entity` et `fromTile` sont des LOCALES : un attach sur `Select` seul ne les voit pas. Le capteur
arme donc AUSSI les deux sous-selecteurs, NOMMES et a corps court, qui les PRODUISENT :

  * `CasterSelector$$Select`     -> `if (ctx+0x08 == 0) return new List(); l.Add(ctx+0x08); return l`
  * `CasterTileSelector$$Select` -> `tiles = ctx+0x48 ?? ToList(ctx+0x40) ?? GetTiles(ctx+0x08)`
    (le SEUL noeud de l'arbre qui CHANGE de branche entre les deux contextes : le gate laisse
    `+0x48` nul, le playbook le renseigne)

LE RETOUR SE LIT EN DEUX FORMES (#374) -- et une seule etait decodee
--------------------------------------------------------------------
Premier tir arme : 4 appels sur chacun des deux bras, `[retour-illisible]` partout
(`classes=['OrderedSet`1' x4]`), alors que le controle positif emettait ses batchs (bras A
4 events == 4 attendus, bras B 5 == 5). Le decodeur ne se trompait pas sur le fond : il ne
savait pas lire ce type. Lu au decompile :

  * les DEUX early-returns rendent la `System.Collections.Generic.List`1` VIDE que le corps
    vient d'allouer ;
  * le retour de `IBattleQuery.GetMovableTilesInRange` est un
    `idun.shared.collections.OrderedSet`1`, qui DERIVE de `List`1` -- `OrderedSet<T>$$.ctor`
    appelle `List<T>$$.ctor` sur le MEME `this` et n'ajoute que son `HashSet` a `+0x28`, et
    `OrderedSet<T>$$get_Item` DELEGUE a `List<T>$$get_Item`. Le stockage ordonne est donc
    celui de la base (`_items`@+0x10, `_size`@+0x18, elements des +0x20), exactement ce que
    `internals.extractTiles` decode deja pour le RPC `aiMovableTiles`.

La CLASSE du retour est donc elle-meme discriminante (`List` = early-return silencieux,
`OrderedSet` = la requete a repondu). Le capteur la publie avec la forme de stockage retenue
et le chemin d'heritage ; `_shape` la rend dans les phrases. Le tri-etat, lui, NE BOUGE PAS :
`[retour-illisible]` reste STRICTEMENT distinct de `[vide]` -- c'est lui qui a evite un faux
« pool vide », et il NOMME desormais la raison de son refus.

DEUX GARDE-FOUS, sans lesquels ce probe mesurerait un artefact de MONTAGE
------------------------------------------------------------------------
  1. **La gate doit etre OUVERTE.** `MakeDamagePredictions` ne construit `GetTileToMoveTo()`
     qu'APRES `Any(selfPreds, p => p.WillBeKill)`. Gate fermee => 0 appel du capteur, et ce zero se
     lirait « l'arbre n'est pas evalue ». Le probe arme donc AUSSI `gateProbe` et REFUSE de
     conclure tant que `willBeKill` n'est pas vrai sur l'event du caster (d'ou `--hp-player`).
  2. **Le caster doit etre A PORTEE.** Le pool est `MovableTilesInRange(..., Direct(0x16))`
     intersecte `CanAddUnit(AdjacentTiles(Target))` : un caster au-dela de la portee rend ce pool
     vide LEGITIMEMENT. Le montage borne la distance (`caster_max_dist`) et le probe la RE-VERIFIE
     sur l'etat drive.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_361_movable_tiles_selector.py
    python probe_361_movable_tiles_selector.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from probe_353r1_ramming_speed_charge_tile import (                          # noqa: E402
    ENEMY2, FILLER_P, GRAFT, VICTIM, _pos, _view)
from probe_361_ramming_speed_explosion_batches import _gate_verdict          # noqa: E402
from montage_361_attack_predictions_selector import (                        # noqa: E402
    ARMS, RAMMING_MOVE_RANGE, build_montage, dispose_montage)

# PV du camp JOUEUR : le 2e batch est un RECUL qui frappe le caster, il faut
# `hpBefore(caster) <= willKillDmg` pour que la gate ouvre. Le probe ne le SUPPOSE pas -- il relit
# le capteur de gate et refuse le bras si elle est restee fermee.
HP_PLAYER = 60

# Les deux sous-selecteurs que `GetTileToMoveTo` passe a `DSLSelectors$$MovableTilesInRange`
# (`factory+0x48` et `factory+0x50`). Le capteur publie les classes EFFECTIVES : le decodeur les
# CONFRONTE a celles-ci et refuse de conclure si la structure differe.
WANT_UNIT_SEL = "CasterSelector"
WANT_TILE_SEL = "CasterTileSelector"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# --------------------------------------------------------------------------------------------
# LE DECODEUR -- tout le verdict est DERIVE des champs du capteur, jamais d'un texte ecrit
# d'avance. Teste 100 % offline par `tests/engine/test_370_tile_probe_tristate_offline.py`.
# --------------------------------------------------------------------------------------------

def _sub_classes(node: dict) -> dict:
    """Retrouve, parmi les champs d'instance publies par le capteur, les classes des deux
    sous-selecteurs -- par leur NOM DE CLASSE, jamais par un offset ni un nom de champ suppose."""
    out = {"unit": None, "tile": None, "unitField": None, "tileField": None}
    for f in (node.get("fields") or []):
        cls = f.get("cls")
        if cls == WANT_UNIT_SEL and out["unit"] is None:
            out["unit"], out["unitField"] = cls, f.get("name")
        elif cls == WANT_TILE_SEL and out["tile"] is None:
            out["tile"], out["tileField"] = cls, f.get("name")
    return out


def _in_window(calls, node: dict) -> list:
    """Les appels d'un sous-selecteur survenus PENDANT cet appel du noeud principal."""
    lo, hi = node.get("seqEnter", -1), node.get("seqLeave", 1 << 30)
    return [c for c in (calls or []) if lo <= c.get("seq", -1) <= hi]


def probe_predates_374(tp) -> bool:
    """Le capteur INJECTE est-il anterieur au correctif #374 (lecture d'`OrderedSet`) ?

    Le correctif vit dans `frida/hooks/*` : il reste INERTE tant que le bundle n'a pas ete
    rebuilde ET reinjecte. Sans ce discriminant, un `[retour-illisible]` post-correctif se
    lirait « le capteur est incoherent » alors qu'il n'est simplement pas charge -- et c'est
    exactement le genre d'ambiguite qui a fait tourner ce residu en rond. Le capteur corrige
    pose TOUJOURS la cle `returnedStorage` (fut-elle nulle) ; celui d'avant ne la connait pas.

    NE conclut RIEN du natif : `True` veut dire « NON CONFRONTE », jamais « pool vide »."""
    nodes = (tp or {}).get("nodes")
    if not nodes:
        return False
    return not any("returnedStorage" in n for n in nodes)


def _shape(node: dict) -> str:
    """La FORME du retour, telle que le capteur l'a lue -- classe effective, stockage retenu,
    chemin d'heritage. Publiee dans les phrases parce que la classe est elle-meme DISCRIMINANTE
    (#374) : `MovableTilesInRangeSelector$$Select` rend la `List` VIDE qu'il vient d'allouer sur
    ses deux early-returns, et un `OrderedSet` (derive de `List`) quand
    `IBattleQuery.GetMovableTilesInRange` a repondu. Purement descriptif : aucun verdict n'en
    est derive -- ce sont les sous-selecteurs qui departagent les trois issues du corps."""
    cls, sto = node.get("returnedClass"), node.get("returnedStorage")
    via, el = node.get("returnedVia"), node.get("returnedElementClass")
    bits = ["classe=%s" % cls]
    if sto:
        bits.append("stockage=%s" % sto)
    if via:
        bits.append("via=%s" % via)
    if el:
        bits.append("element=%s" % el)
    return " ".join(bits)


def _tile_verdict(tp) -> tuple:
    """Traduit le capteur #370 en (etiquette, phrase). TRI-ETAT strict a chaque maillon :
      `None`           -> capteur ABSENT du bundle injecte (reinject en attente) ;
      `nodes is None`  -> capteur DEMANDE mais NON ARME (un maillon n'a pas resolu) ;
      `nodes == []`    -> arme, et le natif n'appelle JAMAIS `MovableTilesInRangeSelector$$Select` ;
      un appel         -> la taille du pool rendu, puis, si elle est nulle, LEQUEL des deux
                          sous-selecteurs est vide -- donc laquelle des trois issues du corps."""
    if tp is None:
        return ("absent", "capteur #370 absent du bundle injecte (reinject en attente)")
    nodes = tp.get("nodes")
    if nodes is None:
        return ("non-arme", "capteur #370 NON ARME : %s" % tp.get("nodesError"))
    if not nodes:
        return ("zero-appel",
                "capteur #370 ARME : `MovableTilesInRangeSelector$$Select` n'est JAMAIS appele "
                "pendant `MakeDamagePredictions` => l'arbre `GetTileToMoveTo` n'est PAS EVALUE, et "
                "la cause est en AMONT du pool (`DSLSelectors$$First` / `$$SortTilesByUtility` / "
                "`TargetsSelector$$op_BitwiseAnd` / `$$AdjacentTiles`)")
    counts = [int(n.get("returnedCount", -1)) for n in nodes]
    if any(c < 0 for c in counts):
        # Cet etat reste DISTINCT de `[vide]`, et c'est tout son interet : c'est lui qui a
        # empeche de lire un « pool vide » la ou le controle positif emettait ses batchs (#374).
        # Il NOMME desormais la raison du refus, faute de quoi un `-1` muet se relirait comme un
        # bug du capteur au lieu d'un type que le decodeur ne connait pas.
        #
        # ... et il dit AUSSI de quel capteur vient ce refus. Le correctif #374 (lecture d'
        # `OrderedSet`) vit dans `frida/hooks/*` : il reste INERTE tant que le bundle injecte
        # n'a pas ete rebuilde. Sans cette distinction, un `[retour-illisible]` post-correctif
        # se lirait « le correctif ne marche pas » alors qu'il n'est simplement pas charge --
        # exactement le genre d'ambiguite qui a fait tourner ce residu en rond. Discriminant :
        # le capteur corrige pose TOUJOURS la cle `returnedStorage` (fut-elle nulle) ; celui
        # d'avant #374 ne la connait pas.
        aged = not any("returnedStorage" in n for n in nodes)
        return ("retour-illisible",
                "capteur #370 ARME (%d appel(s)) mais le retour de "
                "`MovableTilesInRangeSelector$$Select` n'est pas decodable -- c'est une ERREUR de "
                "lecture, pas un pool vide. Formes vues : %s ; raisons : %s%s"
                % (len(nodes), [_shape(n) for n in nodes],
                   [n.get("returnedError") for n in nodes
                    if int(n.get("returnedCount", -1)) < 0],
                   (". Le capteur INJECTE est ANTERIEUR a #374 (il ne publie pas "
                    "`returnedStorage`) : la lecture d'`OrderedSet` est livree mais PAS CHARGEE "
                    "-- fenetre de reinject en attente, rien n'est conclu du natif" if aged
                    else "")))
    if any(c > 0 for c in counts):
        # ⚠ CONDITIONNEL, et #381 dit pourquoi. Le capteur mesure le POOL, pas le DEFICIT : il ne
        # sait pas si des events manquent. Rendre ici « la perte est en AVAL » a fait lire une
        # perte la ou le bras mesure emettait 5 events pour 5 attendus -- une 5e hypothese fausse,
        # nee d'une phrase et non d'une mesure. Le constat du deficit appartient au VERDICT DU RUN
        # (qui compare `n_events` a l'attendu derive) ; le capteur, lui, ne dit que ce qu'il voit.
        return ("pool-non-vide",
                "capteur #370 ARME : `MovableTilesInRangeSelector$$Select` rend %s tuile(s) => le "
                "POOL n'est PAS vide. SI des events manquent a cette etape, la cause est alors en "
                "AVAL (`op_BitwiseAnd CanAddUnit` / `SortTilesByUtility` / `First`) -- mais le "
                "capteur ne mesure PAS le deficit, c'est au verdict du run de le constater. "
                "Tuiles : %s. Formes : %s"
                % (counts, [n.get("returnedTiles") for n in nodes],
                   [_shape(n) for n in nodes]))

    # --- tous les appels rendent un pool VIDE : departager les trois issues du corps
    node = nodes[0]
    subs = _sub_classes(node)
    if subs["unit"] is None or subs["tile"] is None:
        return ("structure-inattendue",
                "capteur #370 ARME, pool VIDE (%d appel(s)), mais les sous-selecteurs ne sont pas "
                "ceux qu'attend `GetTileToMoveTo` (`%s` / `%s`) : champs vus = %s. Le decodeur "
                "REFUSE de conclure -- l'arbre a change, la RE est a refaire"
                % (len(nodes), WANT_UNIT_SEL, WANT_TILE_SEL,
                   [(f.get("name"), f.get("cls")) for f in (node.get("fields") or [])]))
    caster_calls, tile_calls = tp.get("casterCalls"), tp.get("casterTileCalls")
    if caster_calls is None or tile_calls is None:
        return ("sous-maillon-non-arme",
                "capteur #370 ARME sur le noeud (pool VIDE) mais PAS sur les sous-selecteurs : "
                "`%s` / `%s`. Les trois issues du corps restent indiscernables"
                % (tp.get("casterError"), tp.get("casterTileError")))
    unit_win = _in_window(caster_calls, node)
    tile_win = _in_window(tile_calls, node)
    ctx = node.get("ctx") or {}
    if unit_win and all(int(c.get("returnedCount", -1)) == 0 for c in unit_win):
        return ("unit-null",
                "capteur #370 : pool VIDE et `CasterSelector$$Select` rend 0 element (%d appel(s) "
                "dans la fenetre) => `entity == null` dans `MovableTilesInRangeSelector$$Select`, "
                "donc `ctx+0x08` (le caster) est NUL dans le contexte du playbook. Slot lu : %s"
                % (len(unit_win), (ctx.get("caster@0x08") or {}).get("ptr")))
    if tile_win and all(int(c.get("returnedCount", -1)) == 0 for c in tile_win):
        return ("from-tile-null",
                "capteur #370 : pool VIDE, le caster est PRESENT, et `CasterTileSelector$$Select` "
                "rend 0 tuile (%d appel(s) dans la fenetre) => `TargetsSelector$$SelectTile` rend "
                "null, donc `fromTile == null`. Branche : casterPosition@0x48=%s "
                "casterMainTile@0x40=%s caster@0x08=%s"
                % (len(tile_win), (ctx.get("casterPosition@0x48") or {}).get("ptr"),
                   (ctx.get("casterMainTile@0x40") or {}).get("ptr"),
                   (ctx.get("caster@0x08") or {}).get("ptr")))
    if not unit_win or not tile_win:
        return ("fenetre-vide",
                "capteur #370 : pool VIDE, mais AUCUN appel de sous-selecteur n'a ete observe dans "
                "la fenetre du noeud (caster=%d tuile=%d). Les trois issues restent "
                "indiscernables -- la correlation par sequence est a revoir"
                % (len(unit_win), len(tile_win)))
    return ("query-vide",
            "capteur #370 : pool VIDE alors que `CasterSelector$$Select` rend %s element(s) ET "
            "`CasterTileSelector$$Select` rend %s tuile(s) => les deux entrees sont PRESENTES, et "
            "c'est `IBattleQuery.GetMovableTilesInRange(entity, fromTile, ignoreFlags, options)` "
            "qui rend un ensemble VIDE. Forme du retour : %s"
            % ([c.get("returnedCount") for c in unit_win],
               [c.get("returnedCount") for c in tile_win], _shape(node)))


# --------------------------------------------------------------------------------------------
# LA MESURE
# --------------------------------------------------------------------------------------------

def _predict(sid, rid, cid, tid):
    """Une invocation avec les DEUX capteurs armes. `gateProbe` n'est pas decoratif : sans lui, un
    « 0 appel » du capteur de tuile serait indiscernable d'une gate restee fermee."""
    return _r(sid, "aiPlaybookPredict",
              {"runnerId": rid, "unitId": cid, "targetId": tid, "abilityType": ARMS["ramming"].ability,
               "gateProbe": True, "tileProbe": True}, 150)


def _port_tile(sid, rid, ids):
    """La tuile que rend le PORT (`ramming_speed_tile_to_move_to`, confronte 2/2 en #353-r1) --
    point de comparaison quand le pool n'est PAS vide. Jamais une source de verdict."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.orks import ramming_speed_tile_to_move_to
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _view(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, snap, board=board)
    t = ramming_speed_tile_to_move_to(state, ids[GRAFT], ids[VICTIM], RAMMING_MOVE_RANGE)
    return (list(t) if t else None), dv, board


def _expected_events(board, dv, tile, caster_id):
    """L'attendu DERIVE de la composition native, jamais un nombre ecrit d'avance :

        batch 1 : la CIBLE                                       -> 1
        batch 2 : le CASTER (recul)                              -> 1
        batch 3 : Friends(Caster, AdjacentUnits(tile, 1, 3), 3)  -> amis adjacents a `tile`
        batch 4 : Enemies(Caster, AdjacentUnits(tile, 1, 3), 3)  -> ennemis adjacents a `tile`

    ⚠ `AdjacentUnits(tile, ...)` = `Units(AdjacentTiles(tile)) - tile` : la soustraction retire
    l'ORIGIN (une TUILE), pas le caster. La CIBLE, elle, est TOUJOURS adjacente a `tile` -- la
    tuile d'arrivee sort de `CanAddUnit(AdjacentTiles(Target))` -- donc elle est comptee DEUX fois
    (batch 1 puis batch 4). C'est une propriete du natif, pas un doublon du probe."""
    from probe_361_ramming_speed_explosion_batches import _neighbourhood
    fr, en = _neighbourhood(board, dv, tuple(tile), caster_id)
    return {"friends": fr, "enemies": en, "n": 2 + len(fr) + len(en)}


def _measure(sid, m, tag: str) -> dict:
    """UN point de mesure sur l'etat COURANT du runner : tuile du port, attendu DERIVE, events
    natifs attribues, capteur de gate, capteur de tuile."""
    caster, target = m.ids[GRAFT], m.ids[VICTIM]
    tile, dv, board = _port_tile(sid, m.runner, m.ids)
    cp, tp_ = _pos(dv, caster), _pos(dv, target)
    o: dict = {"tag": tag, "port_tile": tile, "caster_pos": cp, "target_pos": tp_,
               "caster_target_dist": (hexgeo.distance(tuple(cp), tuple(tp_))
                                      if cp and tp_ else None),
               # LA variable candidate (#370) : le pool est `MovableTilesInRange(range=5)`, donc
               # une tuile d'arrivee a distance EXACTEMENT 5 n'y entre que si le chemin ne devie
               # pas d'un seul hexagone. C'est la seule difference MESUREE entre le regime ou les
               # batchs sortent (dist 4) et celui ou ils tombent (dist 5).
               "caster_tile_dist": (hexgeo.distance(tuple(cp), tuple(tile))
                                    if cp and tile else None)}
    o["expected"] = _expected_events(board, dv, tile, caster) if tile else None
    nat = _predict(sid, m.runner, caster, target)
    o["playbook"] = nat.get("playbookClass")
    o["native_error"] = nat.get("error")
    evs = nat.get("events") or []
    vis = {int(u["id"]): u.get("visualId") for u in (dv.get("units") or [])}
    o["events"] = [{"targetId": e.get("targetId"), "visualId": vis.get(e.get("targetId")),
                    "healthDmgMax": e.get("healthDmgMax"),
                    "willBeKill": e.get("willBeKill")} for e in evs]
    o["n_events"] = len(evs)
    self_ev = next((e for e in evs if e.get("targetId") == caster), None)
    o["self_will_be_kill"] = (self_ev or {}).get("willBeKill")
    o["gate_kind"], o["gate_phrase"] = _gate_verdict(nat.get("gateProbe"))
    o["tile_probe"] = nat.get("tileProbe")
    o["tile_kind"], o["tile_phrase"] = _tile_verdict(nat.get("tileProbe"))
    # --- discriminance du BRAS, evaluee avant toute lecture du capteur
    d, exp = o["caster_target_dist"], (o["expected"] or {})
    if d is None or d < 2 or d > RAMMING_MOVE_RANGE:
        o["discriminant"] = False
        o["why"] = ("distance caster->cible = %s, hors de [2, %d] : un caster hors portee vide le "
                    "pool POUR UNE RAISON DE MONTAGE" % (d, RAMMING_MOVE_RANGE))
    elif o["self_will_be_kill"] is not True:
        o["discriminant"] = False
        o["why"] = ("gate FERMEE (willBeKill=%s sur l'event du caster) : `GetTileToMoveTo` n'est "
                    "meme pas construite -- baisser --hp-player" % o["self_will_be_kill"])
    elif int(exp.get("n") or 0) <= 2:
        o["discriminant"] = False
        o["why"] = ("le voisinage de la tuile d'arrivee est VIDE (amis=%d ennemis=%d) : les batchs "
                    "3/4 n'auraient rien a emettre"
                    % (len(exp.get("friends") or []), len(exp.get("enemies") or [])))
    else:
        o["discriminant"] = True
        o["why"] = ""
    o["batches_emitted"] = max(0, o["n_events"] - 2)
    o["exact"] = (o["n_events"] == exp.get("n"))
    return o


# La geometrie de `#386` sec.1, LITTERALE (`case-361` sec.1, re-mesuree le 2026-07-31 :
# `probe_361_ramming_speed_explosion_batches` la retrouve et y lit 2 events pour 5 attendus).
# Elle est FIGEE et non re-scannee : `_scan_geometry` trie par distance aux positions COURANTES,
# donc relance depuis un autre etat il rend une AUTRE geometrie -- mesure du 1er jet de ce probe,
# qui a ainsi obtenu 5 events la ou #386 en lit 2. Une geometrie de reference se REPRODUIT, elle
# ne se re-derive pas.
GEO_386 = {"target": (4, 7), "ally": (4, 6), "enemy2": (5, 8), "caster": (1, 4)}


def _redrive(sid, m, geo: dict) -> dict:
    """Repose une geometrie LITTERALE sur le MEME runner. Rejouer les deux geometries sur le meme
    build est ce qui rend leur ecart ATTRIBUABLE a la geometrie, et a rien d'autre (meme seed,
    meme rank, memes unites, meme session)."""
    from probe_353r1_ramming_speed_charge_tile import drive_to
    wanted = {m.ids[VICTIM]: geo["target"], m.ids[ENEMY2]: geo["enemy2"],
              m.ids[FILLER_P]: geo["ally"]}
    drive_to(sid, m.runner, wanted)          # le voisinage d'abord (cf. montage_361)
    wanted[m.ids[GRAFT]] = geo["caster"]
    if not drive_to(sid, m.runner, wanted):
        return {"error": "drive KO vers %s" % json.dumps({k: list(v) for k, v in geo.items()})}
    return {"geometry": {k: list(v) for k, v in geo.items()}}


def run(seed: int = 37000, level: int = 8, mult: int = None, verbose: bool = True) -> dict:
    sid = _resolve_session()
    arm = ARMS["ramming"]
    out: dict = {"seed": seed, "level": level, "mult": mult, "ability": arm.ability,
                 "selector": arm.selector, "hp_player": HP_PLAYER,
                 "move_range": RAMMING_MOVE_RANGE}
    m = None
    try:
        m = build_montage(sid, arm, seed=seed, level=level, hp_player=HP_PLAYER,
                          caster_max_dist=RAMMING_MOVE_RANGE, mult=mult)
        out["runner"] = m.runner
        out["geometry"] = {k: list(v) for k, v in (m.geometry or {}).items()}
        if m.errors:
            out["error"] = "; ".join(m.errors)
            return out
        # --- bras A : la geometrie du montage. C'est le CONTROLE POSITIF -- le natif Y EMET les
        #     batchs 3/4 (mesure #370), donc le capteur doit y voir un pool NON VIDE.
        out["arm_montage"] = _measure(sid, m, "montage")
        # --- bras B : la geometrie de #386 sec.1, ou le natif rend 2 events. C'est le bras que le
        #     capteur doit TRANCHER.
        rd = _redrive(sid, m, GEO_386)
        out["geometry_386"] = rd.get("geometry")
        if rd.get("error"):
            out["arm_386"] = {"error": rd["error"]}
        else:
            out["arm_386"] = _measure(sid, m, "386")
    finally:
        if m is not None:
            dispose_montage(sid, m)

    a, b = out.get("arm_montage") or {}, out.get("arm_386") or {}
    # --- VERDICT DERIVE DES CHAMPS (jamais un recit ecrit d'avance)
    if out.get("error"):
        out["ok"] = False
        out["verdict"] = "MONTAGE KO : %s" % out["error"]
    elif not a.get("discriminant"):
        out["ok"] = False
        out["verdict"] = "BRAS A (controle positif) NON DISCRIMINANT : %s" % a.get("why")
    elif b.get("error"):
        out["ok"] = False
        out["verdict"] = "BRAS B (reference #386) NON MONTE : %s" % b["error"]
    elif not b.get("discriminant"):
        out["ok"] = False
        out["verdict"] = "BRAS B (reference #386) NON DISCRIMINANT : %s" % b.get("why")
    elif a.get("batches_emitted", 0) == 0:
        out["ok"] = False
        out["verdict"] = ("CONTROLE POSITIF PERDU : le bras A n'emet plus les batchs 3/4 (%d "
                          "events pour %d attendus). Le montage a derive -- rien n'est conclu."
                          % (a.get("n_events"), (a.get("expected") or {}).get("n")))
    elif a["tile_kind"] in ("absent", "non-arme") or probe_predates_374(a.get("tile_probe")):
        # ⚠ Trois situations, un SEUL verdict : capteur absent du bundle, capteur non arme, ou
        # capteur ARME mais ANTERIEUR au correctif #374. Les trois disent la meme chose -- le
        # harnais n'est pas en etat de repondre -- et aucune n'autorise a conclure du natif.
        # La derniere est la plus traitre : le capteur FIRE, ses appels se comptent, et sans le
        # discriminant `returnedStorage` on l'accuserait d'etre « incoherent ».
        out["ok"] = False
        out["verdict"] = (
            "NON CONFRONTE : %s. Les DEUX bras sont PRETS et DISCRIMINANTS, et ils ENCADRENT la "
            "question : bras A (%s) emet %d events == %d attendus (les batchs 3/4 SORTENT), bras B "
            "(%s, geometrie de #386) en rend %d pour %d attendus. Il ne manque que la fenetre de "
            "reinject pour dire QUEL maillon rend vide dans B."
            % (a["tile_phrase"], a.get("caster_pos"), a.get("n_events"),
               (a.get("expected") or {}).get("n"), b.get("caster_pos"), b.get("n_events"),
               (b.get("expected") or {}).get("n")))
    elif a["tile_kind"] != "pool-non-vide":
        out["ok"] = False
        out["verdict"] = ("CAPTEUR INCOHERENT AVEC LE CONTROLE POSITIF : le bras A emet %d events "
                          "(batchs 3/4 presents) mais le capteur y dit [%s] -- %s"
                          % (a.get("n_events"), a["tile_kind"], a["tile_phrase"]))
    elif b["tile_kind"] in ("retour-illisible", "structure-inattendue",
                            "sous-maillon-non-arme", "fenetre-vide"):
        out["ok"] = False
        out["verdict"] = "CAPTEUR NON CONCLUANT SUR LE BRAS B : %s" % b["tile_phrase"]
    elif b.get("batches_emitted", 0) > 0:
        # ⚠ LA GARDE QUE CE PROBE N'AVAIT PAS, et qui lui a fait rendre `ok=True` + « MAILLON
        # TRANCHE ... la perte est en AVAL » sur un bras qui emettait 5 events pour 5 attendus :
        # il n'y avait RIEN a trancher. Le bras B est cense reproduire le regime DEFICITAIRE ;
        # s'il ne le reproduit pas, le capteur ne mesure que le regime ou tout marche, et aucune
        # lecture de son pool ne dit quoi que ce soit d'une perte.
        # Cause etablie depuis (#381) : le deficit ne tient pas a la geometrie mais au TOUR --
        # `montage_361` et `probe_361` ne laissent pas la meme parite d'`endturn`, donc le caster
        # n'a pas la main dans les deux. Le regime deficitaire se monte par `probe_381`
        # (balayage de tours) ou par `probe_361_ramming_speed_explosion_batches`.
        out["ok"] = False
        out["verdict"] = (
            "REGIME DEFICITAIRE NON REPRODUIT : le bras B emet %d events pour %d attendus "
            "(batchs 3/4 PRESENTS, exact=%s) -- il n'y a AUCUNE perte a expliquer sur ce bras, "
            "donc son pool [%s] ne tranche rien. Le pool n'est lisible comme cause que sur un "
            "bras ou des events MANQUENT : cf. `probe_381_movable_tiles_query_gate.py` (balayage "
            "de tours, geometrie figee)."
            % (b.get("n_events"), (b.get("expected") or {}).get("n"), b.get("exact"),
               b["tile_kind"]))
    else:
        out["ok"] = True
        out["verdict"] = ("MAILLON TRANCHE [%s] : %s (controle positif A : %s)"
                          % (b["tile_kind"], b["tile_phrase"], a["tile_kind"]))

    if verbose:
        print("[370] runner=%s ability=%s niveau=%s" % (out.get("runner"), arm.ability, level))
        for key, geo in (("A/montage", out.get("geometry")),
                         ("B/386", out.get("geometry_386"))):
            print("[370] geometrie %s = %s" % (key, json.dumps(geo)))
        for key, o in (("A/montage", a), ("B/386", b)):
            if o.get("error"):
                print("[370] bras %s : ERREUR %s" % (key, o["error"]))
                continue
            exp = o.get("expected") or {}
            print("[370] bras %s caster=%s cible=%s d(c,cible)=%s d(c,tuile)=%s tuile_port=%s "
                  "discriminant=%s %s"
                  % (key, o.get("caster_pos"), o.get("target_pos"), o.get("caster_target_dist"),
                     o.get("caster_tile_dist"), o.get("port_tile"), o.get("discriminant"),
                     o.get("why")))
            print("        events=%s attendu=%s (2 + amis=%s + ennemis=%s) exact=%s erreur=%s"
                  % (o.get("n_events"), exp.get("n"),
                     [x["visualId"] for x in (exp.get("friends") or [])],
                     [x["visualId"] for x in (exp.get("enemies") or [])],
                     o.get("exact"), o.get("native_error")))
            for e in o.get("events") or []:
                print("        %s" % json.dumps(e, sort_keys=True))
            print("        gate  [%s] : %s" % (o.get("gate_kind"), o.get("gate_phrase")))
            print("        tuile [%s] : %s" % (o.get("tile_kind"), o.get("tile_phrase")))
        print("[370] %s" % out.get("verdict"))
        print("[370] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=37000)
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--mult", type=int, default=None,
                    help="AbilityVariablesMultiplierPercentage du greffon "
                         "(absent = valeur du seed ; `probe_361` force 100)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, level=a.level, mult=a.mult, verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
