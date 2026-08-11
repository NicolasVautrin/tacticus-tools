#!/usr/bin/env python
"""probe #910 -- MESURE des DEUX canaux de la relique `RelicBoltPistol`
(`EffectType` 0x5b1 = 1457 `RelicBoltPistol_ExtraPierce` et 0x5b2 = 1458
`RelicBoltPistol_ExtraCritDamage`).

CRITERE BINAIRE, pose avant toute methode :

    « Le natif ajoute-t-il `extraPierceRatio[niveau de RELIQUE]` au ratio de percage des attaques
      MELEE de son porteur et `extraCritDmg[niveau]` a son degat de crit en RANGED, chacun DOUBLE
      quand la cible porte `Xenos` ou `Chaos` -- et le port fait-il pareil ? »

## L'ARTEFACT

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicBoltPistolAbility$$CreateBehaviour` pose les
DEUX effets sur l'Owner (`AddEffect(0x5b1) & AddEffect(0x5b2)`, `options` zeroe donc PERMANENTS), et
les deux canaux ont le MEME corps a la variable et a la nature du coup pres ::

    ForAddition( get_OwnerIsCaster & <IsMeleeAttack | IsRangedAttack>,
                 If( HasTrait(Target@+0x60, 0x3ee Xenos) | HasTrait(Target@+0x60, 0x7ea Chaos),
                     Multiply(ConfigVar(<0x3f | 0x42>), <DSLFormulas+0x28> = Direct(2)),
                     ConfigVar(<0x3f | 0x42>) ) )

## LE MONTAGE, et pourquoi chaque piece y est

  * `darkaHellblaster` (Sarquael) est l'un des SEPT porteurs autorises (`items.R_Crit_
    RelicBoltPistol.allowedUnits`), il est AU POOL (etat 2 de la gate relique -> `--equip-relic`),
    et il est le SEUL des cinq porteurs du pool a porter DEUX armes : `Physical` (melee) et
    `Plasma` r3 (ranged). UN porteur exerce donc les DEUX canaux, par la seule DISTANCE.
  * Le trait de la cible est le levier, et il est ECRIT : `--unit-stat '<vid>:Traits=[...]'` ecrit
    `BC.Units[].Traits`, le substrat d'ENTITE que `BaseUnitComponent$$HasTrait` lit (#264). Les
    pseudo-traits `Xenos`/`Chaos` ne sont dans AUCUN `traits` gameconfig (mesure : 0 unite sur les
    trois groupes) -- les poser par le BC est la SEULE voie qui les rende variables.
  * `--armor-target` : sans armure, le ratio de percage n'a AUCUN observable (tout le degat passe
    deja). Le bras PERCAGE serait alors un accord DEGENERE.
  * `--crit 100,<cd>` : tous les coups critent (aucun tirage), et `cd` est assez grand pour que
    `Math.Max(0, GetStat(10) + somme)` de `CalculateCriticalDamage` ne sature pas.
  * Traits et passifs des deux unites REDUITS (`Traits=["Hero"]`, `PassiveAbilities=[]`) : Sarquael
    porte `HeavyWeapon` (+% degat ranged non-bouge), `Overwatch` et `GrimRetribution`, la cible
    porte `BigTarget` et `AvalancheOfMuscle` -- quatre canaux valides AILLEURS, qui ne feraient ici
    que brouiller la salve qu'on lit coup par coup.

## LES BRAS

  1. LIVE -- le natif, l'oracle ;
  2. port (etat livre) -- doit egaler le live ;
  3. `NOCHANNEL` -- les deux effets retires d'`EFFECT_CLASSES` (retombee sur `BaseEffect`, canal
     `None`) : doit DIVERGER dans les deux canaux. C'est ce qui interdit l'accord degenere ;
  4. `NODOUBLE` -- `<DSLFormulas+0x28>` ramene a `Direct(1)` : doit DIVERGER **ssi** la cible porte
     `Xenos` ou `Chaos`. C'est ce qui prouve que le `If` est une MAGNITUDE et pas un gate ;
  5. `PASSIF` -- le callable `tertiary_ability_state_of` retire des DEUX contextes : le port
     retombe sur le niveau des PASSIFS (50 en runner normalise -> dernier palier). Doit DIVERGER
     des que le niveau de relique demande n'est pas le dernier ;
  6. `KIT_TRAITS` (canal PERCAGE seul) -- `target_traits` relu du KIT gameconfig, comme AVANT #910 :
     doit DIVERGER ssi la cible porte `Xenos`/`Chaos`, puisque ces traits n'y sont pour personne ;
  7. `CROISE` -- le gate de NATURE inverse dans les deux classes : doit DIVERGER dans les deux
     canaux (il prouve que `IsMeleeAttack` / `IsRangedAttack` mordent, et qu'un coup ne verse pas
     dans les deux canaux a la fois).

Usage :
    python probe_910_relic_bolt_pistol_live.py
    python probe_910_relic_bolt_pistol_live.py --traits Hero,Xenos,Chaos --level 3
    python probe_910_relic_bolt_pistol_live.py --traits Xenos --canaux PIERCE --verbose
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

CARRIER = "darkaHellblaster"      # porteur autorise de RelicBoltPistol, AU POOL, melee + ranged r3
TARGET = "astraBullgryn"          # cible ; ses traits sont ECRITS par --unit-stat
#: SECOND porteur autorise, AU POOL (`items.R_Crit_RelicBoltPistol.allowedUnits`). Il sert le bras
#: SPECTATEUR : il EQUIPE la relique et n'attaque PAS, pendant que `CARRIER` -- prive de relique --
#: frappe. C'est le seul montage qui exerce `get_OwnerIsCaster`, et il ne mord QUE sur le canal
#: crit-DEGAT : l'agregateur du PERCAGE ne visite que les effets de l'ATTAQUANT (le gate y est
#: satisfait structurellement), tandis que `crit_damage_bonus_from_effects` balaye TOUT LE BOARD
#: (`board_effect_carriers`, #589-r1-r1) -- un porteur SPECTATEUR y est donc bel et bien VISITE.
SPECTATOR = "ultraTitus"
ABILITY_ID = "RelicBoltPistol"    # TriggeredAbilityType 0x5bb = 1467 (la CONFIG)
EFFECT_PIERCE = "RelicBoltPistol_ExtraPierce"           # EffectType 0x5b1 = 1457
EFFECT_CRIT = "RelicBoltPistol_ExtraCritDamage"         # EffectType 0x5b2 = 1458
VAR_PIERCE = "extraPierceRatio"   # AbilityVariableType 0x3f = 63
VAR_CRIT = "extraCritDmg"         # AbilityVariableType 0x42 = 66

#: distance hex du caster a la cible, par canal. C'est ce qui choisit l'ARME
#: (`BattleQuery$$GetAttackWeaponForDefaultNormalAttack`) donc la NATURE du coup.
DIST = {"PIERCE": 1, "CRIT": 3}
#: les DEUX seuls traits que le `If` natif lit. Tout autre valeur est un TEMOIN NEUTRE.
TRAITS_DOUBLANTS = ("Xenos", "Chaos")


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def paliers(var_key: str) -> list:
    """Les paliers RELUS du gameconfig, jamais codes en dur -- meme lecture que le port."""
    import gameconfig as GC
    arr = ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get(var_key)
    if not arr:
        raise SystemExit("%s.variables.%s absent du gameconfig" % (ABILITY_ID, var_key))
    return [int(x) for x in arr]


def garde_regime(level: int, p_pierce: list, p_crit: list, crit_damage: int, armor: int) -> None:
    """GARDES DE REGIME, jouees AVANT tout montage. Chacune ferme une porte de vert-qui-ne-mesure-rien.

      * niveau hors paliers -> `AbilityConfiguration$$TryGetVariableArrayForLevel` CLAMPE au dernier,
        donc les bras `PASSIF` et `NODOUBLE` ne discrimineraient plus rien ;
      * percage effectif deja >= 100 SANS le bonus -> le `Min(100, .)` de
        `GetAttackPiercingDamageRatio` SATURE : port et natif rendraient le meme degat, accord
        DEGENERE. `Physical.PiercingRatio` = 1, donc large marge, mais on le DIT plutot que de le
        supposer ;
      * armure nulle -> le percage n'a AUCUN observable (tout le degat passe deja) ;
      * `crit_damage` a 0 -> `CouldCrit` (`GetStat(9) > 0 && GetStat(10) > 0`) serait FAUX et le
        canal CRIT MUET. (Le regime de crit du canal PERCAGE est force a `0,0` par `build` : le
        crit y rendrait le percage inobservable -- cf. sa docstring.)
    """
    if not (1 <= level <= len(p_pierce)) or not (1 <= level <= len(p_crit)):
        raise SystemExit("niveau %d hors des paliers (%d/%d) : le clamp haut de "
                         "`TryGetVariableArrayForLevel` rendrait les bras NIVEAU non discriminants"
                         % (level, len(p_pierce), len(p_crit)))
    import gameconfig as GC
    base = int((GC.damage_profile("Physical") or {}).get("PiercingRatio") or 0)
    if base + 2 * p_pierce[level - 1] >= 100:
        raise SystemExit("SATURATION du percage : %d + 2 x %d >= 100, le `Min(100, .)` de "
                         "`GetAttackPiercingDamageRatio` confondrait les modeles"
                         % (base, p_pierce[level - 1]))
    if armor <= 0:
        raise SystemExit("--armor-target %d : sans armure le ratio de percage n'a AUCUN observable"
                         % armor)
    if crit_damage <= 0:
        raise SystemExit("--crit-damage %d : `CouldCrit` = GetStat(9) > 0 && GetStat(10) > 0 serait "
                         "FAUX, le canal CRIT serait MUET" % crit_damage)
    if level == len(p_pierce):
        print("   [note] niveau == dernier palier : le bras PASSIF ne peut pas mordre "
              "(le repli clampe justement au dernier palier). Il sera SAUTE.")
    print("   %s[%d] : %s = %d ; %s = %d   (profil Physical.PiercingRatio = %d)"
          % (ABILITY_ID, level, VAR_PIERCE, p_pierce[level - 1], VAR_CRIT, p_crit[level - 1], base))


#: armure par DEFAUT -- cf. `--armor` pour la mesure qui l'etablit.
ARMOR = 6000
#: CritDamage des p-units pour le canal CRIT.
CRIT_DAMAGE = 2000


def flags_spectateur(trait: str, level: int,
                     armor: int = ARMOR, crit_damage: int = CRIT_DAMAGE) -> list:
    """BRAS SPECTATEUR : la relique est sur `SPECTATOR`, et c'est `CARRIER` -- SANS relique -- qui
    frappe. `get_OwnerIsCaster` doit alors FERMER le canal crit-DEGAT, alors meme que l'agregateur
    VISITE le porteur (balayage board-wide). Sans ce gate, un porteur spectateur bufferait un tiers.

    A jouer avec `--p-units CARRIER,SPECTATOR` (le probe s'en charge)."""
    return [
        "--equip-relic", "%s:%s:%d" % (SPECTATOR, ABILITY_ID, level),
        "--unit-stat", '%s:Traits=["%s"]' % (TARGET, trait),
        "--unit-stat", '%s:PassiveAbilities=[]' % TARGET,
        "--unit-stat", '%s:Traits=["Hero"]' % CARRIER,
        "--unit-stat", '%s:PassiveAbilities=[]' % CARRIER,
        "--unit-stat", '%s:Traits=["Hero"]' % SPECTATOR,
        "--unit-stat", '%s:PassiveAbilities=[]' % SPECTATOR,
        "--armor-target", str(armor),
        "--hp-target", "900000", "--hp-player", "900000", "--no-ai",
        "--crit", "100,%d" % crit_damage, "--block-target", "0,0"]


def flags_de_build(trait: str, canal: str, level: int,
                   armor: int = ARMOR, crit_damage: int = CRIT_DAMAGE) -> list:
    """FOYER UNIQUE des flags de montage, partage par le probe et par son cliquet
    (`tests/engine/runner/test_910_relic_bolt_pistol_live.py`) : un montage DUPLIQUE derive de son
    original sans que rien ne le signale.

    ⚠ LE CRIT EST UN PARAMETRE DE REGIME, PAS UN REGLAGE DE CONFORT, et c'est une MESURE qui l'a
    impose : avec `--crit 100,2000`, le canal PERCAGE devient DEGENERE. Un coup CRITIQUE ne traverse
    pas l'armure de la meme facon (`MkXGravis` : « Does not apply to Crits »), donc le ratio de
    percage n'a plus AUCUN observable -- mesure du premier montage : `bonus_pierce = 12` cote port,
    et pourtant `NOCHANNEL` NE MORD PAS (live == port == 4196 dans les deux vues). Un accord y
    aurait ete vide de sens. D'ou :

      * canal PERCAGE -> `--crit 0,0`   (aucun crit : l'armure, donc le percage, mordent) ;
      * canal CRIT    -> `--crit 100,<cd>` (tous les coups critent : aucun tirage a compenser)."""
    return [
        "--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
        # Le LEVIER : `Traits=[...]` REMPLACE la liste d'entite (`BC.Units[].Traits`), le MEME
        # champ que la couche meta remplit avec le pseudo-trait de grande-alliance.
        "--unit-stat", '%s:Traits=["%s"]' % (TARGET, trait),
        "--unit-stat", '%s:PassiveAbilities=[]' % TARGET,
        # Sarquael reduit a `Hero` : `HeavyWeapon` (+% degat ranged non-bouge), `Overwatch` et
        # `FinalJustice` sont trois canaux qui brouilleraient la salve sans rien apporter ici.
        "--unit-stat", '%s:Traits=["Hero"]' % CARRIER,
        "--unit-stat", '%s:PassiveAbilities=[]' % CARRIER,
        "--armor-target", str(armor),
        "--hp-target", "900000", "--hp-player", "900000", "--no-ai",
        "--crit", ("0,0" if canal == "PIERCE" else "100,%d" % crit_damage),
        "--block-target", "0,0"]


def build(a, trait: str, canal: str, level: int, spectateur: bool = False):
    """Un runner par couple (TRAIT de cible, CANAL) -- les deux sont des parametres de BUILD.

    `spectateur=True` : la relique part sur `SPECTATOR` et `CARRIER` frappe SANS elle."""
    fd, sf = tempfile.mkstemp(prefix="probe_910_%s_%s_l%d_" % (trait, canal, level), suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    p_units = "%s,%s" % (CARRIER, SPECTATOR) if spectateur else CARRIER
    flags = (flags_spectateur(trait, level, armor=a.armor, crit_damage=a.crit_damage) if spectateur
             else flags_de_build(trait, canal, level, armor=a.armor, crit_damage=a.crit_damage))
    argv = ([sys.executable, "rl_duel.py", "build",
             "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
             "--p-units", p_units, "--a-units", TARGET] + flags)
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s/%s] build KO : %s" % (trait, canal, (p.stderr or p.stdout or "")[-900:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


class MontageError(RuntimeError):
    """On REFUSE de rendre un verdict plutot que d'en fabriquer un depuis un montage muet."""


def _pos(u) -> tuple:
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


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


def traits_natifs(h, uid: int) -> "set | None":
    """Les traits REELLEMENT portes en bataille, cote NATIF (`combatSnapshot.units[].traits`, #233).

    TRI-ETAT : `None` = capteur MUET pour cette unite -- jamais un ensemble vide, qui se lirait
    « elle ne porte rien » et ferait passer un montage rate pour une mesure."""
    from engine.entities.traits.unit_trait import UnitTrait
    snap = h.rpc("combatSnapshot", {"runnerId": h.rid}, 60)
    for u in ((snap.get("units") if isinstance(snap, dict) else None) or []):
        if u.get("entityId") == uid:
            tr = u.get("traits")
            if tr is None:
                return None
            noms = set()
            for t in tr:
                try:
                    noms.add(UnitTrait(int(t)).name)
                except ValueError:
                    pass
            return noms
    return None


def stage(h, canal: str, verbose=False, porteur: str = CARRIER):
    """Place le caster a la DISTANCE du canal, verifie que les DEUX effets sont bien montes et que
    le trait ecrit est bien porte cote natif, puis fige l'etat.

    `porteur` = l'unite qui EQUIPE la relique. Elle vaut `CARRIER` (= l'attaquant) dans le regime
    nominal, et `SPECTATOR` dans le bras qui exerce `get_OwnerIsCaster`.

    On DEPLACE les unites pour obtenir la configuration voulue -- jamais « bloque par la geometrie
    de spawn »."""
    import hexgeo
    # ⚠ `my_player` doit etre celui du CASTER, et il ne se devine pas : `reach_my_turn` le derive
    # sinon de la PREMIERE unite vivante du `decisionView`, qui est ici la CIBLE (owner adverse).
    # Symptome mesure : le tour amene est celui du camp adverse, l'attaque part quand meme, rend
    # `ok: true` et ne mute RIEN (`mutated: false, changes: []`) -- un REFUS SILENCIEUX.
    dv0 = h.dview()
    c0 = h.by_visual(CARRIER, dv0)
    if c0 is None:
        raise MontageError("attaquant absent du decisionView")
    h.my_player = c0.get("owner")
    dv = h.reach_my_turn(force_cycle=True)
    if dv is None:
        raise MontageError("le tour de l'attaquant est inatteignable")
    carrier = h.by_visual(CARRIER, dv)
    target = h.by_visual(TARGET, dv)
    if carrier is None or target is None:
        raise MontageError("caster ou cible absent du decisionView")
    equipe = h.by_visual(porteur, dv)
    if equipe is None:
        raise MontageError("porteur de relique (%s) absent du decisionView" % porteur)

    # --- les DEUX effets de la relique doivent etre MONTES, cote natif. Sans cette garde, un
    # `--equip-relic` silencieusement rate (les trois ecritures de #237, dont DEUX echouent sans
    # bruit) ferait mesurer une unite SANS relique et rendrait un accord vide de sens.
    noms = {e.get("name") for e in (equipe.get("effects") or [])}
    manquants = [n for n in (EFFECT_PIERCE, EFFECT_CRIT) if n not in noms]
    if manquants:
        raise MontageError("relique NON montee sur %s : %s absent(s) de decisionView.effects "
                           "(presents : %s)" % (porteur, manquants, sorted(noms)))
    if porteur != CARRIER:
        # CONTROLE NEGATIF du bras SPECTATEUR : l'ATTAQUANT ne doit porter AUCUN des deux effets,
        # sinon le gate qu'on croit exercer serait satisfait par le porteur lui-meme.
        an = {e.get("name") for e in (carrier.get("effects") or [])}
        intrus = [n for n in (EFFECT_PIERCE, EFFECT_CRIT) if n in an]
        if intrus:
            raise MontageError("l'ATTAQUANT porte %s -- le bras SPECTATEUR ne mesurerait rien"
                               % intrus)

    # --- le TRAIT ecrit doit etre porte cote natif (tri-etat : capteur muet => REFUS).
    tn = traits_natifs(h, target["id"])
    if tn is None:
        raise MontageError("capteur de traits MUET sur la cible -- le levier du `If` n'est pas mesure")

    # --- placement a la distance du canal. Le caster BOUGE, la cible reste : deplacer le caster est
    # ce qui change l'ARME choisie (`GetAttackWeaponForDefaultNormalAttack`).
    # ⚠ MELEE : le natif teste l'ADJACENCE par la liste STOCKEE de la tuile
    # (`AreEntitiesAdjacent` -> `TileQuery$$IterateAdjacentTiles` = `tile.<+0x30>.<+0x10>`), PAS par
    # la geometrie hex -- mesure #589-r1-r1-r2-r1-r8. Une tuile a `hexgeo.distance == 1` mais ABSENTE
    # de la liste stockee fait partir l'attaque SANS RIEN MUTER (`mutated: false, changes: []`),
    # c'est-a-dire un REFUS SILENCIEUX. Les candidats melee viennent donc des voisins STOCKES.
    d = DIST[canal]
    tpos = _pos(target)
    occ = {_pos(u) for u in h.alive() if u.get("id") != carrier["id"]}
    if d == 1:
        ttid = h.board.id_at(tpos[0], tpos[1])
        if ttid is None:
            raise MontageError("tuile de la cible introuvable dans le boardGraph")
        cands = [h.board.coord(v) for v in h.board.neighbours_native(ttid)
                 if h.board.walkable(v) and h.board.coord(v) not in occ]
    else:
        cands = h.free_tiles(tpos, d, exclude=(carrier["id"],))
    if not cands:
        raise MontageError("aucune tuile marchable libre a hex %d de la cible sur ce board "
                           "(melee : voisins STOCKES)" % d)
    if not any(h.place(carrier["id"], c) for c in cands):
        raise MontageError("placement du caster a hex %d refuse sur toutes les tuiles" % d)

    # --- un `place` est un `MoveUnitOperation` NATIF : il pose `Moved` et peut CHARGER. On repasse
    # donc par un cycle complet, qui purge les deux (`FinishUnitTurnOperation$$Execute`).
    dv = h.reach_my_turn(force_cycle=True)
    if dv is None:
        raise MontageError("mon tour inatteignable apres placement")
    carrier = h.by_visual(CARRIER, dv)
    target = h.by_visual(TARGET, dv)
    if carrier is None or target is None:
        raise MontageError("caster ou cible disparu apres placement")
    dist = hexgeo.distance(_pos(carrier), _pos(target))
    if dist != d:
        raise MontageError("distance %d != %d attendue apres placement" % (dist, d))

    at = h.normal_attack_type(carrier["id"], dv)
    if at is None:
        raise MontageError("attaque normale introuvable sur le porteur")
    rec = {"caster": carrier["id"], "target": target["id"], "ability_type": at,
           "step_to": None, "snapshot": h.snapshot(), "canal": canal,
           "traits_natifs_cible": sorted(tn), "dist": dist,
           "porteur": porteur, "porteur_id": equipe["id"]}
    if verbose:
        print("    canal=%s dist=%d caster=u%s@%s cible=u%s@%s traits natifs cible=%s"
              % (canal, dist, carrier["id"], _pos(carrier), target["id"], _pos(target), sorted(tn)))
    return rec


def strike(h, rec):
    live = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(rec["ability_type"])}}, 60)
    ok, hits = _hits_of(live, rec["caster"], rec["target"])
    if not ok or not hits:
        return None, "attaque live refusee/vide (%s)" % str(live)[:220]
    if not any(u.get("id") == rec["target"] for u in h.alive()):
        return None, "cible MORTE pendant la salve -- flux live tronque"
    return hits, None


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE de la MEME attaque, RNG neutralise par le dump pris au montage.

    Chaque mutation est une CONTRE-EPREUVE, et toutes sont restaurees en `finally`."""
    from engine.entities.effects import factory as F
    from engine.entities.effects.loki import relic_bolt_pistol as RBP
    from engine.runner.operations import damage as D
    from engine.runner import abilities as _A
    from engine.runner.abilities import base as AB

    saved = {n: F.EFFECT_CLASSES.get(n) for n in (EFFECT_PIERCE, EFFECT_CRIT)}
    orig_board = D.AttackDamageOperation._crit_board
    orig_double = RBP._DOUBLE
    orig_oic = RBP._owner_is_caster
    orig_pbonus = AB.ability_pierce_effect_bonus
    orig_pierce_m = RBP.RelicBoltPistolExtraPierceEffect.create_effect_piercing_bonus_for_attack
    orig_crit_m = RBP.RelicBoltPistolExtraCritDamageEffect.create_effect_crit_damage_bonus_for_attack
    try:
        if mutate == "NOCHANNEL":
            for n in (EFFECT_PIERCE, EFFECT_CRIT):
                F.EFFECT_CLASSES.pop(n, None)
        elif mutate == "NODOUBLE":
            # `<DSLFormulas+0x28>` ramene a `Direct(1)` : la branche VRAIE du `If` devient l'identite.
            RBP._DOUBLE = 1
        elif mutate == "PASSIF":
            # Le canal CRIT pose son callable dans `_crit_board`, le canal PERCAGE dans
            # `ability_pierce_effect_bonus` : les DEUX doivent etre prives pour que le bras morde.
            def _crit_sans_tertiaire(state, att_id, tgt_id):
                d = dict(orig_board(state, att_id, tgt_id))
                d.pop(RBP.CTX_ABILITY_STATE_OF, None)
                return d
            D.AttackDamageOperation._crit_board = staticmethod(_crit_sans_tertiaire)

            def _pbonus_sans_tertiaire(state, caster_id, target_id, ability_type, **kw):
                from engine.entities import effects as E
                vrai = E.piercing_bonus_from_effects

                def _filtre(effects, ctx=None):
                    c = dict(ctx or {})
                    c.pop(RBP.CTX_ABILITY_STATE_OF, None)
                    return vrai(effects, c)
                E.piercing_bonus_from_effects = _filtre
                AB.piercing_bonus_from_effects = _filtre
                try:
                    return orig_pbonus(state, caster_id, target_id, ability_type, **kw)
                finally:
                    E.piercing_bonus_from_effects = vrai
                    AB.piercing_bonus_from_effects = vrai
            AB.ability_pierce_effect_bonus = _pbonus_sans_tertiaire
            _A.base.ability_pierce_effect_bonus = _pbonus_sans_tertiaire
        elif mutate == "KIT_TRAITS":
            # La vue d'AVANT #910 : `target_traits` relu du KIT gameconfig, ou `Xenos`/`Chaos` ne
            # sont POUR PERSONNE. Le doublement du canal PERCAGE doit alors disparaitre.
            import gameconfig as GC
            from engine.runner.components import UnitComponent

            def _pbonus_kit(state, caster_id, target_id, ability_type, **kw):
                from engine.entities import effects as E
                vrai = E.piercing_bonus_from_effects
                kit = None
                if target_id is not None:
                    te = state.get_entity(target_id)
                    tuc = te.get_component(UnitComponent) if te is not None else None
                    if tuc is not None:
                        kit = frozenset((GC.unit(tuc.visual_id) or {}).get("traits") or ())

                def _filtre(effects, ctx=None):
                    c = dict(ctx or {})
                    c["target_traits"] = kit
                    return vrai(effects, c)
                E.piercing_bonus_from_effects = _filtre
                AB.piercing_bonus_from_effects = _filtre
                try:
                    return orig_pbonus(state, caster_id, target_id, ability_type, **kw)
                finally:
                    E.piercing_bonus_from_effects = vrai
                    AB.piercing_bonus_from_effects = vrai
            AB.ability_pierce_effect_bonus = _pbonus_kit
            _A.base.ability_pierce_effect_bonus = _pbonus_kit
        elif mutate == "OWNERISCASTER_OFF":
            # `get_OwnerIsCaster` neutralise (toujours VRAI). Sur le bras SPECTATEUR il doit MORDRE :
            # c'est la preuve que l'agregateur crit-DEGAT VISITE bel et bien le porteur spectateur
            # (balayage board-wide) et que SEUL ce gate ferme le canal. Sur le regime nominal
            # (porteur == attaquant) il ne peut RIEN changer -- controle negatif gratuit.
            RBP._owner_is_caster = lambda ctx: True
        elif mutate == "CROISE":
            # Gate de NATURE inverse dans les deux classes : le canal PERCAGE ne verserait plus
            # qu'en RANGED, le canal CRIT qu'en MELEE.
            def _pierce_croise(self, ctx=None):
                c = dict(ctx or {})
                if c.get("is_ranged") is None:
                    return None
                c["is_ranged"] = not c["is_ranged"]
                return orig_pierce_m(self, c)

            def _crit_croise(self, att_ctx=None):
                c = dict(att_ctx or {})
                if c.get("is_ranged") is None:
                    return None
                c["is_ranged"] = not c["is_ranged"]
                return orig_crit_m(self, c)
            RBP.RelicBoltPistolExtraPierceEffect.create_effect_piercing_bonus_for_attack = _pierce_croise
            RBP.RelicBoltPistolExtraCritDamageEffect.create_effect_crit_damage_bonus_for_attack = _crit_croise
        return h.replay_offline(rec)["per_hit"]
    finally:
        for n, cls in saved.items():
            if cls is not None:
                F.EFFECT_CLASSES[n] = cls
        D.AttackDamageOperation._crit_board = orig_board
        RBP._DOUBLE = orig_double
        RBP._owner_is_caster = orig_oic
        AB.ability_pierce_effect_bonus = orig_pbonus
        _A.base.ability_pierce_effect_bonus = orig_pbonus
        RBP.RelicBoltPistolExtraPierceEffect.create_effect_piercing_bonus_for_attack = orig_pierce_m
        RBP.RelicBoltPistolExtraCritDamageEffect.create_effect_crit_damage_bonus_for_attack = orig_crit_m


def etages(h, rec) -> dict:
    """DECOMPOSITION PAR ETAGE du port, sur l'etat OFFLINE reconstruit -- jamais un scalaire fitte.

    Rend, dans l'ordre du natif : les traits d'ENTITE de la cible, le couple `(level, mult)` de
    `GetAbilityState(effect)`, la valeur de `ConfigVar(<var>)`, et les DEUX scalaires que les canaux
    versent. C'est ce qui permet de dire QUEL etage bouge quand le degat diverge."""
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.traits.unit_trait import entity_trait_names
    from engine.runner.components import StatsComponent, UnitComponent, unit_state_for_effects
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.base import triggered_ability_state
    st = h.offline_state(rec)
    aid, tid = int(rec["caster"]), int(rec["target"])
    te = st.get_entity(tid)
    tuc = te.get_component(UnitComponent) if te is not None else None
    tsc = te.get_component(StatsComponent) if te is not None else None
    traits = entity_trait_names(tsc.ctx if tsc is not None else None,
                                tuc.visual_id if tuc is not None else None)
    lvl, mult = triggered_ability_state(st, aid, ABILITY_ID)
    out = {"traits_entite_cible": sorted(traits or ()), "ability_state": (lvl, mult),
           "config_var_pierce": ability_var(ABILITY_ID, VAR_PIERCE, lvl, multiplier_pct=mult),
           "config_var_crit": ability_var(ABILITY_ID, VAR_CRIT, lvl, multiplier_pct=mult)}
    effs = st.effects.active_effects(aid, unit_state_for_effects(st, aid)) if st.effects else []
    out["effets_porteur_port"] = sorted({getattr(e, "name", None) for e in effs} - {None})
    is_ranged = rec["canal"] == "CRIT"
    ep = next((e for e in effs if getattr(e, "name", None) == EFFECT_PIERCE), None)
    ec = next((e for e in effs if getattr(e, "name", None) == EFFECT_CRIT), None)
    ctx = dict(AttackDamageOperation._crit_board(st, aid, tid))
    ctx.update({"att_id": aid, "tgt_id": tid, "owner_id": aid, "is_ranged": is_ranged})
    out["bonus_crit"] = (ec.create_effect_crit_damage_bonus_for_attack(ctx) if ec is not None else None)
    pctx = {"owner_id": aid, "att_id": aid, "target_traits": traits, "is_ranged": is_ranged,
            RBP_CTX: (lambda oid, ab: triggered_ability_state(st, int(oid), ab))}
    out["bonus_pierce"] = (ep.create_effect_piercing_bonus_for_attack(pctx) if ep is not None else None)
    return out


#: importe tardivement pour ne pas figer le module a l'import du probe
from engine.entities.effects.loki.relic_bolt_pistol import CTX_ABILITY_STATE_OF as RBP_CTX  # noqa: E402


def run_case(a, rpc, Board, Harness, trait: str, canal: str, level: int,
             p_pierce: list, p_crit: list, spectateur: bool = False) -> int:
    rid, sf = build(a, trait, canal, level, spectateur=spectateur)
    tag = "%s/%s%s" % (trait, canal, "/SPECTATEUR" if spectateur else "")
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        double = trait in TRAITS_DOUBLANTS
        try:
            rec = stage(h, canal, a.verbose, porteur=(SPECTATOR if spectateur else CARRIER))
        except MontageError as e:
            print("[%s] REFUS : %s" % (tag, e))
            return 2
        live, why = strike(h, rec)
        if live is None:
            print("[%s] REFUS : %s" % (tag, why))
            return 2
        off = replay(h, rec)
        k = len(live)
        accord = (off[:k] == live)
        rc = 0 if accord else 1

        if spectateur:
            # Le porteur n'est PAS l'attaquant : le canal doit etre MUET. `NOCHANNEL` ne peut donc
            # RIEN changer, et c'est `OWNERISCASTER_OFF` -- le gate neutralise -- qui doit mordre.
            bras = [("NOCHANNEL", False), ("OWNERISCASTER_OFF", True)]
        else:
            bras = [("NOCHANNEL", True),
                    ("NODOUBLE", double),
                    ("PASSIF", level != len(p_pierce)),
                    ("CROISE", True),
                    # Controle NEGATIF gratuit : porteur == attaquant, le gate est deja VRAI.
                    ("OWNERISCASTER_OFF", False)]
            if canal == "PIERCE":
                bras.append(("KIT_TRAITS", double))
        lignes = []
        for nom, attendu in bras:
            mut = replay(h, rec, mutate=nom)
            mord = (mut[:k] != off[:k])
            if mord != attendu:
                rc |= 1
            lignes.append("%s mord=%s (attendu %s)  %s -> %s%s"
                          % (nom, mord, attendu, off[:3], mut[:3],
                             "" if mord == attendu else "  <<< ECART"))
        v = (p_pierce if canal == "PIERCE" else p_crit)[level - 1]
        print("[%s] accord=%s | %s attendu = %s | live=%s port=%s"
              % (tag, accord, VAR_PIERCE if canal == "PIERCE" else VAR_CRIT,
                 "0 (porteur != attaquant)" if spectateur
                 else "%d%s" % (v * (2 if double else 1), " (x2)" if double else ""),
                 live[:6], off[:6]))
        for l in lignes:
            print("        %s" % l)
        if a.verbose:
            print("        ETAGES %s" % (etages(h, rec),))
        return rc
    finally:
        from engine.runner.snapshot import clear_ability_states_cache
        clear_ability_states_cache("build#%s" % rid)
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--level", type=int, default=3, help="niveau de la RELIQUE (1..10)")
    ap.add_argument("--traits", default="Hero,Xenos,Chaos",
                    help="traits ECRITS sur la cible, un runner par trait. `Hero` = TEMOIN NEUTRE "
                         "(branche FAUSSE du `If`), `Xenos`/`Chaos` = branche VRAIE (x2).")
    ap.add_argument("--canaux", default="PIERCE,CRIT",
                    help="canaux a mesurer : PIERCE (melee, dist 1) et/ou CRIT (ranged, dist 3)")
    ap.add_argument("--armor", type=int, default=ARMOR,
                    help="armure de la cible. Elle doit ABSORBER TOUTE la part non percee, sinon le "
                         "ratio de percage n'a AUCUN observable : `total = base x p + max(0, base x "
                         "(1-p) - armure)` vaut `base - armure` INDEPENDAMMENT de `p` tant que "
                         "`base x (1-p) > armure`. MESURE sur ce montage (base = 4200) : armure "
                         "200/800/3000 -> degat 4000/3400/1200, IDENTIQUE avec et sans le canal ; "
                         "armure 6000 -> 42 (sans) contre 693 (avec).")
    ap.add_argument("--crit-damage", type=int, default=CRIT_DAMAGE, help="CritDamage des p-units")
    ap.add_argument("--spectateur", action="store_true",
                    help="BRAS `get_OwnerIsCaster` : la relique est sur `%s` (qui n'attaque PAS) et "
                         "`%s` frappe SANS elle. Le canal crit-DEGAT balaye TOUT le board, donc le "
                         "porteur EST visite -- seul le gate le ferme. Le mutant "
                         "`OWNERISCASTER_OFF` doit alors MORDRE." % (SPECTATOR, CARRIER))
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    a.canaux = [c.strip() for c in a.canaux.split(",") if c.strip()]
    inconnus = [c for c in a.canaux if c not in DIST]
    if inconnus:
        raise SystemExit("--canaux : %s hors de %s" % (inconnus, list(DIST)))

    p_pierce, p_crit = paliers(VAR_PIERCE), paliers(VAR_CRIT)
    print("== #910 RelicBoltPistol -- porteur %s, cible %s" % (CARRIER, TARGET))
    garde_regime(a.level, p_pierce, p_crit, a.crit_damage, a.armor)

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    # ⚠ CANAL RELIQUE. `load_state` tire `unitAbilityStates` elle-meme, mais SEULEMENT si un
    # transport AMBIANT est lie (`snapshot.bind_live_rpc`, #357/#363). Sans lui,
    # `UnitContext.tertiary_ability` reste `None` et `triggered_ability_state` retombe sur le couple
    # PASSIF -- le niveau lu serait 50 (dernier palier) au lieu de celui qu'on a EQUIPE.
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)
    rc = 0
    for trait in [t.strip() for t in a.traits.split(",") if t.strip()]:
        for canal in a.canaux:
            rc |= run_case(a, rpc, Board, ChargeRegimeHarness, trait, canal, a.level,
                           p_pierce, p_crit, spectateur=a.spectateur)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
