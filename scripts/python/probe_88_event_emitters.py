"""probe #88 -- QUI emet `On(<EventTriggerType>)` cote natif ?

Vue par CALL-SITE (une ligne par site) du dispatcher d'evenements de trigger, en regard de
`probe_88_dispatch_scan.py` qui, lui, agrege par evenement. Meme substrat : le thunk de
publication est RE-DERIVE sur le build charge, ses call-sites sont trouves par balayage
d'octets, et l'immediat qui porte l'`eventType` est decode dans la fenetre qui precede
chaque `call`.

But immediat : localiser l'emetteur d'`On(PendingDeathAdded)` (residu A1 de
`docs/rl/case-66-revive-in-place.md` §8.1) et confirmer celui d'`On(PreUnitMove)` (residu A2
§8.2). Sortie ASCII pure.

LA LISTE DE CALL-SITES N'EST PLUS TRANSCRITE (#431)
---------------------------------------------------
Elle l'etait : 55 couples `(nom, VA)` recopies a la main d'un `mcp__ghidra__list_xrefs`
joue sur `gqfc5mff6c`, plus le chemin en dur du binaire de ce build. C'etait le cas le plus
dangereux du lot, et il est MESURE : les 55 VA resolvent 55/55 contre la table `gqfc5mff6c`
et **0/55** contre `rnca9r7q6c` -- chacune tombe dans une fonction d'interface utilisateur
sans le moindre rapport (`idun.ui.UnitDeploymentHud$$...`,
`idun.Idun.Source.UI.ToggleSlider...`). Le decodage d'immediat, lui, aurait continue de
rendre des nombres, et l'en-tete aurait continue d'afficher les BONS noms d'operations :
un tableau entierement faux, d'apparence irreprochable.

La seule reparation qui tienne est donc de SUPPRIMER la transcription, pas de la mettre a
jour -- une liste ecrite a la main se re-perime au build suivant, et rien dans le depot ne
peut le voir (sa source est hors depot).
"""
from __future__ import annotations

import struct

from build_pin import CODE_SECTIONS, BuildPinRefused, load_dll
from probe_88_dispatch_scan import BACK_WINDOW, _decode_event, find_publisher_thunks


def collect_sites(buf, image_base, secs, thunks):
    """[(VA du call, forme, eventType decode)] pour tous les call-sites des thunks."""
    out = []
    for nm, vaddr, _vsize, praw, rawsz in secs:
        if nm not in CODE_SECTIONS:
            continue
        body = buf[praw:praw + rawsz]
        i, n = 0, len(body)
        while True:
            k = body.find(b"\xe8", i)
            if k < 0 or k + 5 > n:
                break
            i = k + 1
            rel = struct.unpack_from("<i", body, k + 1)[0]
            where = thunks.get(image_base + vaddr + (k + 5) + rel)
            if where is None:
                continue
            out.append((image_base + vaddr + k, where,
                        _decode_event(body[max(0, k - BACK_WINDOW):k], where)))
    return out


def main() -> int:
    try:
        buf, image_base, secs, index = load_dll()
        thunks = find_publisher_thunks(buf, image_base, secs, index)
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    from engine.dsl.event_trigger_type import EventTriggerType
    ev_names = {int(m): m.name for m in EventTriggerType}

    print("build=%s  image_base=0x%x  sections=%d" % (index.build, image_base, len(secs)))
    for va, where in sorted(thunks.items()):
        print("  thunk re-derive : %s  (eventType en %s)" % (index.resolve(va)[0], where))
    print("")

    sites = collect_sites(buf, image_base, secs, thunks)
    print("%-70s %-10s %-6s %s" % ("emetteur", "passage", "event", "nom EventTriggerType"))
    print("-" * 118)
    cible, temoin = int(EventTriggerType.PendingDeathAdded), int(EventTriggerType.PreUnitMove)
    hits_cible, hits_temoin = [], []
    for va, where, imm in sorted(sites, key=lambda s: index.resolve(s[0])[0]):
        name = index.resolve(va)[0]
        label = ev_names.get(imm, "?") if imm is not None else "(immediat non decode)"
        print("%-70s %-10s %-6s %s" % (name[:70], where, imm if imm is not None else "-", label))
        if imm == cible:
            hits_cible.append(name)
        if imm == temoin:
            hits_temoin.append(name)
    print("-" * 118)
    print("call-sites : %d" % len(sites))
    print("On(PendingDeathAdded) emetteurs : %s" % (sorted(set(hits_cible)) or "AUCUN"))
    print("On(PreUnitMove)       emetteurs : %s" % (sorted(set(hits_temoin)) or "AUCUN"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
