#!/usr/bin/env python
"""oracle — couche MERGE : assemble les 4 sources en une CARTE DÉCISION unifiée.

  decisionView (RPC, dynamique : units/positions/HP/flags + attackPlans rankés
                + dégâts/kill prédits)
  + board.py   (statique : terrain/élévation/hex)
  + gameconfig (statique : kits — Movement, portée d'arme, traits)
  + danger zone GÉOMÉTRIQUE (calculée ici : positions ennemies × Movement ×
                portée, via hexgeo — contourne le dangerZone=0 du RPC car
                GetMovableTilesFor est scopé au tour courant pour les ennemis
                « TurnFinished »).

Sortie = un texte que l'oracle (Claude) lit pour raisonner sur le tour.
Over-approxime la menace (ignore obstacles/occupation/LoS) → conservateur = sûr.
"""
from __future__ import annotations

import string
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import gameconfig  # noqa: E402
from board import Board, _GLYPH  # noqa: E402


def unit_kit(visual_id: str | None) -> dict:
    """Kit mécanique d'une unité (depuis gameconfig) : move, portée, traits."""
    u = gameconfig.unit(visual_id) if visual_id else None
    if not u:
        return {"name": visual_id, "faction": "?", "movement": None,
                "attackRange": 1, "ranged": False, "traits": []}
    weapons = u.get("weapons") or []
    ranges = [w.get("Range") for w in weapons if w.get("Range")]
    return {
        "name": u.get("name"), "faction": u.get("FactionId"),
        "movement": u.get("Movement"),
        "attackRange": max(ranges) if ranges else 1,  # mêlée = 1
        "ranged": bool(ranges), "traits": u.get("traits") or [],
    }


def geometric_danger_zone(bd: Board, enemies: list[dict]) -> tuple[Counter, list]:
    """enemies: [{id, pos:(col,row), movement, attackRange, ranged}]. Renvoie
    (intensity, per) où `intensity[(col,row)]` = NB d'ennemis pouvant frapper la
    tile au prochain tour. Pour chaque ennemi : tiles atteignables (move) puis,
    depuis chacune, tiles à portée — avec **ligne de vue** (LoS) exigée si ranged
    (dist>1). Over-approxime le move (ignore occupation/zones de contrôle) mais
    la LoS retire les cibles derrière un obstacle → signal moins inondé que le
    binaire précédent ; l'intensité donne la gradation (1 = effleuré, N = focus)."""
    intensity: Counter = Counter()
    per = []
    for e in enemies:
        pos = e.get("pos")
        if not pos or pos[0] is None:
            per.append({"id": e.get("id"), "threat": 0})
            continue
        mv = e.get("movement") or 0
        ar = e.get("attackRange") or 1
        ranged = e.get("ranged", ar > 1)
        threat: set = set()
        for r in bd.disk_playable(pos[0], pos[1], mv):
            for t in hexgeo.disk(r[0], r[1], ar):
                if not bd.is_playable(*t):
                    continue
                if ranged and hexgeo.distance(r, t) > 1 and not bd.has_los(r, t):
                    continue
                threat.add(t)
        for t in threat:
            intensity[t] += 1
        per.append({"id": e.get("id"), "threat": len(threat)})
    return intensity, per


def _killmark(t: dict) -> str:
    """K! = kill GARANTI ; K? = kill POSSIBLE (seulement sur un bon roll/crit).
    Base = les seuils de mort EFFECTIFS du moteur (WillBeKill/MightBeKill, post
    floor-Resilient + overkill) — PAS un simple dmg>=hp (qui sur-claimait un K!
    sur un Resilient ; cf. TF04). `↓` = prédiction OPTIMISTE : la cible porte un
    effet de réduction-trigger (TerminatorArmour / *HitReduction / *ReduceDmg…)
    que le moteur NE modélise PAS → dégâts réels plus bas, K! dégradé en K?."""
    mark = "K!" if t.get("killSure") else ("K?" if t.get("kill") else "")
    if t.get("predOptimistic"):
        mark += "↓"
    return mark


def _ability_state(a: dict) -> str:
    """État LIVE d'un actif (absent de gameconfig) : prêt / cdN / disabled /
    munitions — pour savoir ce qui est CASTABLE ce tour. Vide pour l'attaque
    normale (toujours dispo). cooldown=None signifie prêt (Nullable sans valeur)."""
    if a.get("kind") != "active":
        return ""
    if a.get("disabled"):
        return " [disabled]"
    parts: list[str] = []
    cd = a.get("cooldown")
    if cd:  # not None and > 0
        parts.append(f"cd{cd}")
    elif a.get("usable") is False:
        parts.append("indispo")
    else:
        parts.append("prêt")
    ammo = a.get("ammoCost")
    if ammo:  # coût en munitions (MoW surtout)
        parts.append(f"munitions{ammo}" + ("" if a.get("hasAmmo", True) else "!MANQUE"))
    return " [" + " ".join(parts) + "]"


def _tgt_key(t: dict):
    if t.get("kind") == "unit":
        return ("u", t.get("targetId"))
    ti = t.get("tile") or {}
    return ("t", ti.get("col"), ti.get("row"))


def _tgt_compact(t: dict) -> str:
    if t.get("kind") == "unit":
        return f"u{t.get('targetId')}"
    ti = t.get("tile") or {}
    return f"({ti.get('col')},{ti.get('row')})"


def _abil_targets_summary(ab: dict | None, fh_ok: bool, cap: int = 6) -> str:
    """Résumé compact des cibles légales d'un actif (abilityTargets) : `now` =
    castable SANS bouger (légalité exacte du cast immédiat) · `+move` = atteignable
    ce tour en bougeant d'abord. '' si pas d'info ; '∅' si aucune cible (no-op
    certain). Comble les abilities NON-attaque (buff/heal/summon/hex) absentes des
    PLANS D'ATTAQUE."""
    if not ab:
        return ""
    here = ab.get("fromHere") or []
    tgts = ab.get("targets") or []
    if not here and not tgts:
        return " →∅(no-op certain)"

    def _fmt(ts: list) -> str:
        s = ",".join(_tgt_compact(t) for t in ts[:cap])
        return s + (f",+{len(ts) - cap}" if len(ts) > cap else "")

    if not fh_ok:  # fromHere indispo → superset seul
        return f" →[{len(tgts)} move incl.]:{_fmt(tgts)}"
    hk = {_tgt_key(t) for t in here}
    move_only = [t for t in tgts if _tgt_key(t) not in hk]
    seg = [f"now[{len(here)}]:{_fmt(here) if here else '∅'}"]
    if move_only:
        seg.append(f"+move[{len(move_only)}]:{_fmt(move_only)}")
    return " →" + " · ".join(seg)


# Effets tactiquement CRITIQUES : sous-chaîne du nom EffectType -> (label,
# hint actionnable). Surfacés en tête de carte pour ne JAMAIS les rater (la
# défaite = mark railgun ignoré). Recon d'un effet : gameconfig.py --effect <nom>.
_CRIT_EFFECTS: list[tuple[str, str, str]] = [
    ("HeavyRailRifle_Pending", "RAILGUN",
     "tir différé sur cette unité → la faire BOUGER ≥3 hex (−30% dmg/hex)"),
    ("ReactivateOverwatch", "OVERWATCH", "réarmé → sa portée = tir gratuit en y entrant"),
    ("Overwatch_AutoAttack", "OVERWATCH", "armé → entrer dans sa portée = tir gratuit"),
    ("FuryOfTheAncients", "HEAL-BLOCK", "ne peut être soigné/revive/repair (2 rounds)"),
    ("Stunned", "STUN", "ne joue pas ce tour (triggers de MORT restent)"),
    ("Taunted", "TAUNT", "forcé de cibler le taunter / mouvement contraint"),
    ("Markerlight", "MARKERLIGHT", "cible l'AoE TwinSmartMissile (Broadside)"),
    ("Incapacitated", "INCAP", "ne joue pas ce tour"),
    ("Infiltrate", "INFILTRATE", "ignore l'overwatch ce tour"),
    ("TeleportStrike_TeleportingIn", "DEEP-STRIKE", "non-ciblable jusqu'à ce qu'elle agisse"),
]


def _effect_crit(name: str | None) -> tuple[str, str] | None:
    if not name:
        return None
    for sub, label, hint in _CRIT_EFFECTS:
        if sub in name:
            return (label, hint)
    return None


def _effect_label(e: dict) -> str:
    """Nom d'effet + tours restants (r0 = permanent/aura, omis)."""
    nm = e.get("name") or f"#{e.get('effectType')}"
    rem = e.get("remaining")
    return nm + (f"(r{rem})" if isinstance(rem, int) and rem > 0 else "")


def build_card(view: dict, bd: Board, abil: dict | None = None,
               round_cap: int | None = None, pov_team: int | None = None,
               turn_no: int | None = None) -> str:
    units = view.get("units") or []
    cur_player = view.get("currentPlayer")
    # abilityTargets (optionnel) : index (unitId, abilityId) -> entrée cibles, pour
    # enrichir MES ACTIFS avec la légalité now/+move (incl. abilities non-attaque).
    abil_idx: dict = {}
    fh_ok = bool(abil and abil.get("fromHereResolved"))
    if abil:
        for au in (abil.get("units") or []):
            for ab in (au.get("abilities") or []):
                abil_idx[(au.get("unitId"), ab.get("abilityId"))] = ab
    # POV stable (TF03) : si `pov_team` fourni (= la team du PLAYER, lue dans le
    # state-file), on labellise MOI/ENNEMI par team ABSOLUE → les labels ne flippent
    # plus quand `currentPlayer` bascule sur l'adversaire (le `ctrl` du jeu est relatif
    # au joueur courant). Sinon fallback historique = ctrl (relatif au currentPlayer).
    if pov_team is not None:
        my_team = pov_team
    else:
        my_team = next((u.get("team") for u in units if u.get("ctrl")), None)

    def _is_mine(u: dict) -> bool:
        return (u.get("team") == pov_team) if pov_team is not None else bool(u.get("ctrl"))

    enemies = [u for u in units if not _is_mine(u) and u.get("alive")]
    mine = [u for u in units if _is_mine(u) and u.get("alive")]

    # Danger zone géométrique (depuis kits gameconfig).
    danger_inputs = []
    for e in enemies:
        pos = e.get("pos") or {}
        k = unit_kit(e.get("visualId"))
        danger_inputs.append({
            "id": e.get("id"),
            "pos": (pos.get("col"), pos.get("row")),
            "movement": k["movement"], "attackRange": k["attackRange"],
            "ranged": k["ranged"],
        })
    intensity, danger_per = geometric_danger_zone(bd, danger_inputs)
    max_int = max(intensity.values(), default=0)

    # MoW (MachinePlatform) — ability-only, ne bougent pas. Rendus comme les
    # units (lettres), distingués dans la légende (clé "casterId" présente).
    mows = [m for m in (view.get("mows") or []) if m.get("alive")]
    my_mows = [m for m in mows if m.get("team") == my_team]
    en_mows = [m for m in mows if m.get("team") != my_team]
    mine_all = mine + my_mows
    enemies_all = enemies + en_mows

    # Lettres : mes units+MoW = A.. (uppercase), ennemis = a.. (lowercase).
    letters: dict = {}
    for i, u in enumerate(mine_all):
        pos = u.get("pos") or {}
        if pos.get("col") is not None and i < 26:
            letters[(pos["col"], pos["row"])] = (string.ascii_uppercase[i], u)
    for i, u in enumerate(enemies_all):
        pos = u.get("pos") or {}
        if pos.get("col") is not None and i < 26:
            letters[(pos["col"], pos["row"])] = (string.ascii_lowercase[i], u)

    # Rendu board avec overlay (units + danger '!').
    lines = ["      " + " ".join(f"{c % 10}" for c in range(bd.width))]
    for row in range(bd.height - 1, -1, -1):
        cells = []
        for col in range(bd.width):
            key = (col, row)
            if key in letters:
                cells.append(letters[key][0])
            elif not bd.is_playable(col, row):
                cells.append(" ")
            elif intensity.get(key):
                cells.append(str(min(intensity[key], 9)))
            else:
                t = bd.tile(col, row)
                tid = (t.get("tileId") or "?") if t else "?"
                cells.append(_GLYPH.get(tid, tid[0].lower()))
        lines.append(f"r{row:2d}   " + " ".join(cells))

    # Légende units (+ MoW : clé "casterId" présente → ability-only).
    leg = []
    for _key, (ch, u) in sorted(letters.items(), key=lambda kv: kv[1][0]):
        tag = "<MOI>" if _is_mine(u) else "ENNEMI"
        if "casterId" in u:  # MoW
            ab = ",".join(str(x.get("id")) for x in (u.get("abilities") or []))
            leg.append(f"  {ch} = MoW u{u.get('casterId')} [{u.get('visualId')}] "
                       f"{tag} HP{u.get('hp')} ability-only abilities:[{ab}]")
            continue
        k = unit_kit(u.get("visualId"))
        rng = f"ranged r{k['attackRange']}" if k["ranged"] else "mêlée"
        leg.append(f"  {ch} = u{u.get('id')} [{u.get('visualId')}] «{k['name']}» "
                   f"{tag} HP{u.get('hp')} move{k['movement']} {rng}")

    # Section MoW : tout ce qu'il faut pour les jouer (ability-only).
    mow_lines: list[str] = []
    if mows:
        mow_lines.append("  MoW (ability-only — jouer : "
                         "act ability --caster <id> --target T --ability <A>) :")
        for m in mows:
            # cibles légales now/+move par ability MoW (abilityTargets indexe les
            # Machine du joueur courant par (casterId, abilityId) ; vide pour l'ENNEMI).
            ab = ", ".join(
                f"{x.get('id')}({x.get('name')}){_ability_state(x)}"
                f"{_abil_targets_summary(abil_idx.get((m.get('casterId'), x.get('id'))), fh_ok)}"
                for x in (m.get("abilities") or [])) or "—"
            side = "MOI" if m.get("team") == my_team else "ENNEMI"
            pos = m.get("pos") or {}
            mow_lines.append(
                f"    u{m.get('casterId')} [{m.get('visualId')}] {side} "
                f"@({pos.get('col')},{pos.get('row')}) HP{m.get('hp')} "
                f"hasAction={m.get('hasAction')} abilities: [{ab}]")

    # Section MES ACTIFS (état live) : par unité contrôlée, ses actifs +
    # castabilité CE tour (prêt/cdN/disabled/munitions). C'est l'info LIVE que
    # gameconfig ne donne PAS (lui n'a que noms+stats statiques) → évite de
    # planifier un actif en cooldown.
    act_lines: list[str] = []
    actives_rows = []
    for u in mine:
        acts = [a for a in (u.get("abilities") or []) if a.get("kind") == "active"]
        if not acts:
            continue
        if abil_idx:  # une ligne par actif AVEC ses cibles légales now/+move.
            for a in acts:
                ti = abil_idx.get((u.get("id"), a.get("id")))
                actives_rows.append(
                    f"    u{u.get('id')} [{u.get('visualId')}] "
                    f"{a.get('name')}({a.get('id')}){_ability_state(a)}"
                    f"{_abil_targets_summary(ti, fh_ok)}")
        else:  # pas d'abilityTargets → format compact d'origine.
            s = ", ".join(f"{a.get('name')}({a.get('id')}){_ability_state(a)}" for a in acts)
            actives_rows.append(f"    u{u.get('id')} [{u.get('visualId')}]: {s}")
    if actives_rows:
        act_lines.append(
            "  MES ACTIFS (état live + cibles légales — now=sans bouger · "
            "+move=après déplacement · ∅=no-op certain) :" if abil_idx
            else "  MES ACTIFS (état live — prêt/cdN/disabled/munitions) :")
        act_lines.extend(actives_rows)

    # Effets actifs par unité (decisionView.effects = liste native du jeu, =
    # icônes de statut in-game). (a) bloc ⚠ CRITIQUES en évidence (railgun / OW /
    # stun / taunt / heal-block / markerlight + hint actionnable — l'anti-défaite) ;
    # (b) liste complète par unité pour la recon (gameconfig.py --effect <nom> ;
    # *_Visual cosmétiques filtrés). mine_all/enemies_all incluent les MoW.
    _crit: list[str] = []
    _eff: list[str] = []
    for u in mine_all + enemies_all:
        uid = u.get("casterId", u.get("id"))
        side = "MOI" if _is_mine(u) else "ENN"
        shown = []
        for e in (u.get("effects") or []):
            nm = e.get("name") or ""
            c = _effect_crit(nm)
            if c:
                _crit.append(f"    ⚠ [{c[0]}] u{uid} [{u.get('visualId')}] "
                             f"({side}) — {c[1]}")
            if "Visual" not in nm:
                shown.append(_effect_label(e))
        if shown:
            _eff.append(f"    u{uid} [{u.get('visualId')}] <{side}>: "
                        + ", ".join(shown))
    # Horloge round-cap (board-level, decisionView.roundCap) — bombardement AoE
    # board-wide qui WIPE LES DEUX camps (no-winner = double-défaite). En TÊTE des
    # critiques : être en avance ne sauve PAS du cap, il faut FERMER avant. cf. H58.
    rc = view.get("roundCap")
    if rc:
        rem = rc.get("remaining")
        nm = rc.get("name") or "EnvEndBombardment"
        if isinstance(rem, int):
            when = "CE TOUR (fire imminent !)" if rem <= 0 else f"dans {rem} tour(s)"
        else:
            when = "imminent"
        _crit.insert(0,
                     f"    ⏱ [ROUND-CAP] {nm} → bombardement AoE board-wide {when} : "
                     f"WIPE LES DEUX camps (no-winner = double-défaite). FERME le combat AVANT.")
    crit_block = (["  ⚠ EFFETS CRITIQUES (ne pas rater) :", *_crit] if _crit else [])
    eff_block = (["  EFFETS ACTIFS (par unité — recon : gameconfig.py --effect <nom>) :",
                  *_eff] if _eff else [])

    # ⏱ Horloge round-cap STATIQUE (cap = nrOfRounds de l'EnvEndBombardment lu dans le
    # BC, =8). On N'AFFICHE PAS de "round courant" live : view.turn
    # (GetAmountOfTurnsStartedByCurrentPlayer) n'est PAS un compteur monotone fiable (il
    # oscille sur les tours passifs ; pas de GetTotalTurnsFinished simple). Le budget
    # actionnable se compte côté player : le Warning/Incoming arme à TotalTurnsFinished ==
    # TurnsFromRounds(nrOfRounds) = ~`cap` tours PAR CAMP, puis le nuke board-wide (wipe
    # les 2 camps, healthPct=20% PV max) ~1 round après. cf. RE EnvEndBombardment.
    _clock_line = ""
    if isinstance(round_cap, int):
        close_by = max(1, round_cap - 2)
        _clock_line = (
            f"  ⏱ HORLOGE round-cap : EnvEndBombardment ACTIF → bombardement final board-wide "
            f"vers le round {round_cap} (≈ tes {round_cap} premiers tours), qui WIPE les 2 "
            f"camps = no-winner = double-défaite. Sois en CLÔTURE cohésive pour ton ~{close_by}ᵉ "
            f"tour ; le ⏱[ROUND-CAP] (effet Incoming) n'arme qu'à 2 tours de la fin = TROP TARD.")

    # En-tête : POV explicite (TF03) + n° de tour FIABLE (TF14, `turn_no` dérivé du
    # state-file action_log) au lieu du compteur per-player oscillant `view.turn`.
    cur_team = {3: 1, 4: 2}.get(cur_player)
    if isinstance(turn_no, int):
        turn_txt = f"mon tour #{turn_no}"
    else:
        turn_txt = f"tour {view.get('turn')} (compteur per-player — NON fiable)"
    pov_warn: list[str] = []
    if pov_team is not None and cur_team is not None and cur_team != pov_team:
        pov_txt = (f"POV joueur {cur_player} (team {cur_team} = ADVERSAIRE) · "
                   f"MON équipe = team {pov_team}")
        pov_warn = ["  ⚠ POV ADVERSAIRE — c'est le tour de l'ADVERSAIRE (team "
                    f"{cur_team}) : les PLANS D'ATTAQUE / MES ACTIFS ci-dessous sont "
                    "les SIENS. Tes units restent labellées MOI (stable) mais tu ne "
                    "joues pas ce tour-ci (attends ton tour)."]
    else:
        pov_txt = f"joueur {cur_player} (team {my_team})"
    out = [
        f"=== CARTE DÉCISION — {turn_txt} · {pov_txt} ===",
        *pov_warn,
        *([_clock_line] if _clock_line else []),
        "\n".join(lines),
        f"  chiffre 1-{max(max_int, 1)} = NB d'ennemis menaçant la tile "
        f"(danger, LoS incluse ; {len(intensity)} tiles, max {max_int}) · "
        f"terrain: . grass ~water #block =bridge s swamp b drybush · "
        f"MAJUSCULE=moi minuscule=ennemi",
        "\n".join(leg),
        *(["\n".join(mow_lines)] if mow_lines else []),
        *(["\n".join(act_lines)] if act_lines else []),
        *(["\n".join(crit_block)] if crit_block else []),
        *(["\n".join(eff_block)] if eff_block else []),
        f"  À ACTIVER (mes units/MoW avec action) : {view.get('toActivate')}",
        "  PLANS D'ATTAQUE (où aller -> dégâts [min-max, K!=kill sûr "
        "K?=kill possible · ↓=préd. OPTIMISTE : cible réduit les dmg (effet "
        "non modélisé) -> réel plus bas]) :",
    ]
    for p in (view.get("attackPlans") or []):
        pos = p.get("pos") or {}
        has_any = any((ev.get("ranked") or []) for ev in (p.get("evals") or []))
        head = (f"    u{p.get('unitId')} [{p.get('visualId')}] "
                f"@({pos.get('col')},{pos.get('row')}):")
        out.append(head if has_any else head + " (aucune attaque à portée)")
        # abilityId -> info (pour labelliser chaque ligne par ability + son état :
        # avec allAbilities il y a plusieurs evals/cible, normal ET actifs).
        ab_by_id = {a.get("id"): a for a in (p.get("abilities") or [])}
        for ev in (p.get("evals") or []):
            ranked = ev.get("ranked") or []
            if not ranked:
                continue
            tl = " > ".join(
                f"({t['col']},{t['row']})" + (
                    f"[{t.get('dmgMin')}-{t.get('dmgMax')}{_killmark(t)}]"
                    if t.get('dmgMax') is not None else "")
                for t in ranked)
            label = ev.get("ability") or "?"
            tag = _ability_state(ab_by_id.get(ev.get("abilityId"), {}))
            out.append(f"      [{label}{tag}] vs u{ev.get('targetId')} "
                       f"[{ev.get('targetVis')}]: {tl}")
    return "\n".join(out)
