#!/usr/bin/env python
"""probe #920 -- MESURE de l'axe ADDITION du canal crit-DEGAT porte par la relique
`MawClawsOfThyrax` (`MawClawsOfThyrax_ExtraCritDmg`, EffectType 0x5b5 = 1461).

CRITERE BINAIRE, pose avant toute methode :

    « Le natif AJOUTE-t-il `extraCritDmg[niveau de RELIQUE] x <unites a trait Summon ADJACENTES au
      porteur, TOUS CAMPS CONFONDUS>` au degat de CRIT que ce porteur INFLIGE, et le port
      fait-il pareil ? »

## L'ARTEFACT

`IdunBattle.Entities.Effects.Loki.MawClawsOfThyrax_ExtraCritDmgEffect$$CreateCritDamageBonus`
= `ForAddition(get_OwnerIsCaster, GetExtraCritAmount())` (cibles de `call` resolues par leur RVA :
`0x18105ef40`, `0x180edbaa0`, `0x181047dc0` -- et NON `0x181048090` = `ForSubtraction`), ou
`GetExtraCritAmount` (corps DEDUPLIQUE avec `KardiocoreGalvanus_ExtraCritDmgEffect`) =
`Multiply(ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet), config@+0x60),
EffectLevel(Effect@DSLSelectors+0x38))`, et le niveau STOCKE que `RefreshEffectsOperation$$
UpdateLevel` y ecrit est `$$GetCalculateLevel` =
`Count(Unique(UnitsWithTrait(AdjacentUnits(Owner@+0x30, unique: 1, sel: 3), 0x2 = Summon, 3)))`.

Sa `CreateActiveCondition` est `AmountIsGreaterThanZero(<vslot +0x5f8>)`, c'est-a-dire le MEME
compteur compare a zero -- l'INVERSE de `KardiocoreGalvanus`, dont la condition est `YesTrigger`.
L'ACTIVITE est donc ICI un observable du compteur, en plus du `level` et du degat.

## CE QUE CE PROBE DOIT DISCRIMINER, et que le voisin `KardiocoreGalvanus` ne discrimine pas

`AdjacentUnits` (`Units(AdjacentTiles(origin), unique, sel) op_Subtraction origin`) ne filtre
AUCUN camp. Un port qui aurait recopie `AmuletOfTheVoidwyrm` (`AdjacentFriends` + Summon/Decoy) ou
`KardiocoreGalvanus` (`AdjacentFriends` + `MechanicalUnits`) passerait TOUS les bras ou les
compagnons sont AMIS, et tomberait uniquement sur `--ennemi`. C'est le bras central de ce probe.

## LE MONTAGE, et pourquoi chaque piece y est

  * `tyranTyrantGuard` est l'un des QUATRE porteurs autorises de `MawClawsOfThyrax`
    (`catalog_inject --list-relics` : `allowedUnits = [tyranTyrantGuard, tyranWingedPrime,
    tyranParasite, genesPatriarch]`), il est AU POOL, et la relique n'est PAS equipee au seed
    (etat 2 de la gate relique) -> `rl_duel build --equip-relic`, qui pose les TROIS ecritures d'un
    bloc (`TertiaryAbility`, `TertiaryAbilityLevel >= 1`, config dans `BC.Abilities.
    PassiveAbilities` -- `MawClawsOfThyrax` est l'une des 29 abilities de relique ABSENTES du seed).
  * Le porteur est le **CASTER** (`get_OwnerIsCaster`), donc il est cote `p-units` et c'est LUI qui
    doit criter -> `--crit` (et non `--crit-target`).
  * Les COMPAGNONS portent le trait par `--unit-stat '<vid>:Traits=["Summon"]'` : c'est le substrat
    d'ENTITE (`BC.Units[].Traits` -> `BaseUnitComponent`) que `UnitsWithTrait` lit (#264), le MEME
    champ qu'un vrai summon renseignerait. Les **59** porteurs natifs de `Summon` au gameconfig
    sont TOUS `kind == summons` et aucun n'est au pool ; leur amener un summoner ne donnerait
    aucun controle sur `n` ni sur le CAMP, qui est justement ce qu'on mesure. Ecrire la liste
    ENTIERE les debarrasse au passage de tout trait d'invisibilite, qui les ferait tomber du
    `selectionType = 3 = OnlyAliveAndTargetable`.
  * `n` (le nombre de compagnons ADJACENTS) est le levier : `n = 1` et `n = 2` doivent rendre DEUX
    bonus differents -- c'est ce qui prouve le PRODUIT et interdit de fitter un scalaire.

## LES BRAS

  1. LIVE -- le natif, l'oracle ;
  2. port (etat livre) -- doit egaler le live ;
  3. `NOCHANNEL` -- l'effet retire d'`EFFECT_CLASSES` (retombe sur `BaseEffect`, canal `None`) :
     doit DIVERGER ssi le canal verse. C'est ce qui interdit l'accord degenere ;
  4. `PASSIF` -- le callable `tertiary_ability_state_of` retire du contexte : le port retombe sur
     `ability_level` (le niveau des PASSIFS, 50 en runner normalise -> dernier palier). Doit
     DIVERGER des que le canal verse et que le niveau demande n'est pas le dernier palier ;
  5. `--ennemi` -- les compagnons Summon passent cote ADVERSE : le compteur doit rester **n**
     (`AdjacentUnits` ne filtre aucun camp). C'est le bras qui separe cet effet de ses deux
     voisins de forme ;
  6. `--trait Hero` -- bras NEGATIF : compagnons adjacents mais SANS `Summon` -> compteur 0, canal
     muet, ET effet publie **INACTIF** (la `CreateActiveCondition` compare le compteur a zero) ;
  7. `--porteur-defenseur` -- le porteur DEFEND, son compteur est PLEIN et le canal doit rester
     MUET (`get_OwnerIsCaster`). Un port qui lirait `get_OwnerIsTarget` passerait tous les autres
     bras et tomberait ICI.

Usage :
    python probe_920_maw_claws_of_thyrax_live.py --n 0,1,2
    python probe_920_maw_claws_of_thyrax_live.py --n 2 --ennemi
    python probe_920_maw_claws_of_thyrax_live.py --n 2 --trait Hero        # bras NEGATIF
    python probe_920_maw_claws_of_thyrax_live.py --n 2 --porteur-defenseur
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

#: porteur autorise de `MawClawsOfThyrax`, AU POOL, relique NON equipee au seed (etat 2).
CARRIER = "tyranTyrantGuard"
#: les deux porteurs de trait, patches par `--unit-stat`. Cote AMI par defaut, ADVERSE sous `--ennemi`.
COMPANIONS = ("genesMagus", "genesPrimus")
#: la CIBLE -- cote adverse, gonflee par `--hp-target` pour survivre a la salve.
TARGET = "tauCrisis"
#: l'ATTAQUANT du bras `--porteur-defenseur` : melee, AU POOL, et NON porteur de cette relique.
ATTACKER_EXT = "blackHaarken"
EFFECT_NAME = "MawClawsOfThyrax_ExtraCritDmg"    # cle EFFECT_CLASSES == nom decisionView
ABILITY_ID = "MawClawsOfThyrax"                  # TriggeredAbilityType 0x5bd = 1469 (la CONFIG)
VAR_KEY = "extraCritDmg"                         # AbilityVariableType 0x42 = 66

#: le SEUL trait que le compteur natif lit, plus le bras NEGATIF. Tout autre trait ferait un bras
#: MUET dont le zero accuserait le port a tort.
TRAIT_COMPTE = "Summon"
TRAITS_ADMIS = (TRAIT_COMPTE, "Hero")


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def paliers_du_gameconfig() -> list:
    """`extraCritDmg` RELU du gameconfig, jamais code en dur -- meme lecture que le port."""
    import gameconfig as GC
    arr = ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get(VAR_KEY)
    if not arr:
        raise SystemExit("%s.variables.%s absent du gameconfig" % (ABILITY_ID, VAR_KEY))
    return [int(x) for x in arr]


def _garde_regime(level: int, paliers: list) -> None:
    """GARDES DE REGIME, jouees AVANT tout montage.

    Pas de garde de SATURATION ici, et c'est une difference de fond avec les trois
    `ForSubtraction` de l'axe : `CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)`,
    or la somme est POSITIVE -- le clamp bas ne peut pas mordre.

      * niveau hors paliers -> `AbilityConfiguration$$TryGetVariableArrayForLevel` CLAMPE au
        dernier, donc le bras « niveau » ne discriminerait plus rien ;
      * niveau == dernier palier -> le bras `PASSIF` ne peut PAS mordre (le repli clampe justement
        au dernier palier), donc sa contre-epreuve serait vide."""
    if not (1 <= level <= len(paliers)):
        raise SystemExit("niveau %d hors des %d paliers de %s : le clamp haut de "
                         "`AbilityConfiguration$$TryGetVariableArrayForLevel` rendrait le bras "
                         "NIVEAU non discriminant" % (level, len(paliers), ABILITY_ID))
    if level == len(paliers):
        print("   [note] niveau == dernier palier : le bras PASSIF ne peut pas mordre "
              "(le repli clampe au dernier palier). Il sera SAUTE.")
    print("   %s.%s[%d] = %d  (paliers %s..%s)" % (ABILITY_ID, VAR_KEY, level, paliers[level - 1],
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


def _traits_json(spec: str) -> str:
    """`"Summon"` -> `"Summon"`. REFUSE tout trait hors des deux admis : un trait inerte ferait
    tomber `n` a zero sans qu'aucune assertion ne designe la cause."""
    noms = [t.strip() for t in str(spec).split(",") if t.strip()]
    if not noms:
        raise SystemExit("--trait : liste vide")
    inconnus = [t for t in noms if t not in TRAITS_ADMIS]
    if inconnus:
        raise SystemExit("--trait : %s hors des traits admis %s (`Summon`, le seul que le compteur "
                         "lit, plus `Hero` qui est le bras NEGATIF)" % (inconnus, list(TRAITS_ADMIS)))
    return ",".join('"%s"' % t for t in noms)


def attendu_summon(trait_spec: str) -> bool:
    """Le bras est-il POSITIF (le trait compte) ou NEGATIF ?"""
    return TRAIT_COMPTE in [t.strip() for t in str(trait_spec).split(",") if t.strip()]


def build(a, tag, level):
    fd, sf = tempfile.mkstemp(prefix="probe_920_%s_" % tag, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    comps = '%s,%s' % COMPANIONS
    if a.porteur_defenseur:
        # BRAS `get_OwnerIsCaster` : le porteur DEFEND, ses summons adjacents sont bien la
        # (compteur NON NUL), et le canal doit rester MUET.
        p_units, a_units = ATTACKER_EXT, "%s,%s" % (CARRIER, comps)
    else:
        # Les compagnons sont du COTE du porteur par defaut, et passent en face sous `--ennemi` :
        # c'est le bras qui prouve l'ABSENCE de filtre d'equipe.
        p_units = CARRIER if a.ennemi else "%s,%s" % (CARRIER, comps)
        a_units = TARGET if not a.ennemi else "%s,%s" % (TARGET, comps)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--p-units", p_units, "--a-units", a_units,
            "--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
            "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[0], _traits_json(a.trait)),
            "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[1], _traits_json(a.trait)),
            # Le PORTEUR est reduit a `Hero` : ses autres traits ne changent rien au canal mesure
            # mais brouillent la lecture de la salve. `Summon` lui est DELIBEREMENT refuse -- le
            # natif l'exclut deja par l'`op_Subtraction origin` d'`AdjacentUnits`, et le lui donner
            # ferait porter au bras une question qu'on ne mesure pas ici.
            "--unit-stat", '%s:Traits=["Hero"]' % CARRIER,
            "--hp-target", "900000", "--hp-player", "900000",
            "--no-ai", "--crit", "100,%d" % a.crit_damage, "--block-target", "0,0"]
    if a.porteur_defenseur:
        argv += ["--unit-stat", '%s:Traits=["Hero"]' % ATTACKER_EXT,
                 "--hp-player", "900000"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (tag, (p.stderr or p.stdout or "")[-800:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _pos_de(u) -> tuple:
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def _effet_natif(h, carrier_id: int):
    """`(active, level)` de l'effet, LUS sur `decisionView` (`includeInactive`), ou `None` si
    l'effet est ABSENT du canal (= la relique n'est PAS montee -> montage mort, jamais rabattu).

    DEUX observables NATIFS distincts, et ils sont TOUS DEUX des observables du compteur ici :

      * `active` -- `CreateActiveCondition` = `AmountIsGreaterThanZero(<le compteur>)`, donc
        `active == (compteur > 0)`. C'est l'INVERSE de `KardiocoreGalvanus`, dont la condition est
        `YesTrigger` et dont l'activite ne dit donc rien ;
      * `level` -- le niveau STOCKE dans `EffectComponent+0x68`, que
        `RefreshEffectsOperation$$UpdateLevel` tient EGAL a `$$GetCalculateLevel`. C'est **le
        compteur natif LU DIRECTEMENT**, sans passer par le degat."""
    dvi = h.rpc("decisionView", {"runnerId": h.rid, "maxRank": 1, "allAbilities": True,
                                 "includeInactive": True}, 90)
    cu = next((u for u in (dvi.get("units") or []) if u.get("id") == carrier_id), None)
    for e in ((cu or {}).get("effects") or []):
        if e.get("name") == EFFECT_NAME:
            lvl = e.get("level")
            return bool(e.get("active")), (None if lvl is None else int(lvl))
    return None


def stage(h, n, ennemi=False, verbose=False, porteur_defenseur=False):
    """Monte le regime `n` compagnons ADJACENTS au porteur et rend `(rec, raison)`.

    L'ADJACENCE est celle du NATIF (`board.neighbours_native` = la liste STOCKEE que
    `AdjacentTilesSelector$$Select` enumere via `IterateAdjacentTiles`), JAMAIS
    `hexgeo.distance == 1`.

    ORDRE : cycle de tour D'ABORD, placements ENSUITE -- on veut que les positions LUES au snapshot
    soient celles qu'on a posees. (Et le trait `Summon` accorde aux compagnons les rend
    `PlayAutomaticUnits`-ables au TURN START : placer apres le debut du tour evite qu'un
    turn-start ne les deplace entre la pose et la mesure. Les positions sont RE-MESUREES de toute
    facon, et un ecart fait REFUSER le bras plutot que rendre un verdict.)"""
    import hexgeo
    ancre_vis = CARRIER
    att_vis = ATTACKER_EXT if porteur_defenseur else CARRIER
    def_vis = CARRIER if porteur_defenseur else TARGET

    dv = h.dview()
    att = h.by_visual(att_vis, dv)
    if att is None:
        return None, "attaquant (%s) absent du deploiement" % att_vis
    h.my_player = att.get("owner")
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    dv = h.dview()
    att = h.by_visual(att_vis, dv)
    porteur = h.by_visual(ancre_vis, dv)
    cible = h.by_visual(def_vis, dv)
    if att is None or cible is None or porteur is None:
        return None, "porteur, attaquant ou cible absent du deploiement"
    comps = [h.by_visual(c, dv) for c in COMPANIONS]
    if any(c is None for c in comps):
        return None, "un compagnon est absent du deploiement"

    board = h.board
    marchables = [t for t in sorted(board.by_id) if board.walkable(t)]

    def _occ(exclure=()):
        ex = set(exclure)
        return {_pos_de(u) for u in h.alive() if u.get("id") not in ex}

    def _pose(uid, cands, quoi):
        occ = _occ((uid,))
        for c in cands:
            if c not in occ and h.place(uid, c):
                return c
        return None

    occupe = _occ((porteur["id"],))
    plan = None
    for tid in sorted(marchables, key=lambda t: (-len(board.neighbours_native(t)), t)):
        anchor = board.coord(tid)
        if anchor in occupe:
            continue
        vs = [board.coord(v) for v in board.neighbours_native(tid) if board.walkable(v)]
        if len(vs) < n + 1:
            continue
        loin = [board.coord(t) for t in marchables
                if hexgeo.distance(board.coord(t), anchor) >= 4 and board.coord(t) not in vs]
        if len(loin) < len(COMPANIONS) + 1:
            continue
        plan = (anchor, vs, loin)
        break
    if plan is None:
        return None, "geometrie non realisable (n=%d) : pas d'ancre a %d voisins NATIFS" % (
            n, n + 1)
    anchor, voisins, loin = plan

    # TOUT le monde part LOIN d'abord, ensuite le porteur, ensuite ceux qui reviennent au contact --
    # `place` est un `MoveUnitOperation` NATIF COMPLET, donc un deplacement pres d'un ennemi peut
    # declencher des reactions qui CONSOMMENT l'action qu'on veut mesurer (mesure #913).
    au_contact = att if porteur_defenseur else cible
    for c in comps + [au_contact]:
        if _pose(c["id"], loin, "LOIN") is None:
            return None, "impossible d'eloigner %s" % c.get("visualId")
    if _pose(porteur["id"], [anchor], "ANCRE") is None:
        return None, "placement du porteur refuse (ancre %s)" % (anchor,)
    for i, c in enumerate(comps):
        if i < n and _pose(c["id"], voisins, "ADJACENT") is None:
            return None, "placement du compagnon %s refuse" % c.get("visualId")
    contact = _pose(au_contact["id"], voisins, "CONTACT")
    if contact is None:
        return None, "placement au contact refuse (aucun voisin natif libre)"

    dv = h.dview()
    att = h.by_visual(att_vis, dv)
    if att is not None and not att.get("hasAction"):
        if h.reach_my_turn(force_cycle=True) is None:
            return None, ("l'attaquant a perdu son action pendant le montage et le cycle de tour "
                          "n'a pas pu la lui rendre")

    # --- l'etat MESURE, jamais suppose ------------------------------------------------------------
    dv = h.dview()
    att = h.by_visual(att_vis, dv)
    porteur = h.by_visual(ancre_vis, dv)
    cible = h.by_visual(def_vis, dv)
    ctile = board.id_at(*[(porteur.get("pos") or {}).get(k) for k in ("col", "row")])
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
    # ⚠ TOUT le VOISINAGE, pas seulement les compagnons. Le compteur natif porte sur `AdjacentUnits`
    # -- TOUTE unite adjacente, quel que soit son camp et son role dans le montage. Compter les seuls
    # compagnons FABRIQUE une attente fausse : mesure #920, `genesPrimus` SPAWNE des decoys pendant
    # les cycles de tour du montage, et l'ancre s'est retrouvee entouree d'unites que le montage
    # n'avait pas inventoriees. Le `voisinage` ci-dessous est ce que le probe COMPARE au compteur,
    # et son eligibilite `Summon` est tranchee plus loin sur le substrat d'ENTITE du port.
    rec_voisins = [{"id": u.get("id"), "vis": u.get("visualId"), "pos": _pos_de(u)}
                   for u in h.alive(dv)
                   if u.get("id") != porteur["id"] and _pos_de(u) in voisins_natifs]

    # CONTROLE POSITIF DU MONTAGE : l'effet doit etre PUBLIE (meme inactif). Un `None` ici = la
    # relique n'est pas montee -> tout le bras mesurerait autre chose.
    lu = _effet_natif(h, porteur["id"])
    if lu is None:
        return None, ("l'effet %s est ABSENT du canal (meme `includeInactive`) -- la relique n'est "
                      "PAS montee sur %s, le bras ne mesurerait rien" % (EFFECT_NAME, CARRIER))
    actif, niveau_natif = lu

    atk_type = h.normal_attack_type(att["id"], dv)
    rec = {"caster": att["id"], "target": cible["id"], "ability_type": int(atk_type),
           "porteur": porteur["id"],
           "n": n_mesure, "anchor": anchor, "contact": contact, "step_to": None,
           "actif_natif": bool(actif), "niveau_natif": niveau_natif, "ennemi": bool(ennemi),
           "porteur_defenseur": bool(porteur_defenseur), "voisins": rec_voisins}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    if verbose:
        print("    ancre=%s contact=%s | compagnons adjacents = %d | actif=%s niveau NATIF=%s"
              % (anchor, contact, n_mesure, actif, niveau_natif))
        print("    VOISINAGE NATIF du porteur : %s"
              % [(v["id"], v["vis"], v["pos"]) for v in rec_voisins])
    return rec, None


def strike(h, rec):
    live = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(rec["ability_type"])}}, 60)
    ok, hits = _hits_of(live, rec["caster"], rec["target"])
    if not ok or not hits:
        return None, "attaque live refusee/vide (%s)" % str(live)[:200]
    if not any(u.get("id") == rec["target"] for u in h.alive()):
        return None, "cible MORTE pendant la salve -- flux live tronque"
    return hits, None


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE de la MEME attaque, RNG neutralise par le dump pris apres le montage.

    `NOCHANNEL` : l'effet retire d'`EFFECT_CLASSES` AVANT `load_state` -- la FACTORY le fait alors
    retomber sur `BaseEffect`, dont `create_effect_crit_damage_bonus_for_attack` rend `None`.

    `PASSIF` : le callable `tertiary_ability_state_of` retire du contexte du canal -- le port
    retombe sur `ability_level` (le niveau des PASSIFS). Les deux mutations sont restaurees en
    `finally`."""
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

    Rend, dans l'ordre du natif : le COMPTEUR (`GetCalculateLevel`), l'ACTIVITE (la
    `CreateActiveCondition`, qui est ICI le meme compteur compare a zero), le couple
    `(level, mult)` de `GetAbilityState(effet)`, et le scalaire SIGNE que le canal verse
    (`ForAddition`, donc POSITIF)."""
    from engine.runner.components import adjacent_summons_count, unit_state_for_effects
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.base import triggered_ability_state
    from engine.entities.stats import StatType
    st = h.offline_state(rec)
    aid, tid = int(rec["caster"]), int(rec["target"])
    # `owner_id` = le PORTEUR de l'effet, que la boucle native ECRASE dans `AbilityEntities+0x18` a
    # chaque iteration. Il vaut l'ATTAQUANT partout, SAUF sous `--porteur-defenseur`.
    oid = int(rec.get("porteur", aid))
    out = {"compteur": adjacent_summons_count(st, oid),
           "ability_state": triggered_ability_state(st, oid, ABILITY_ID)}
    # ATTENDU CALCULE A LA MAIN, hors de l'arbre DSL qu'on teste : sur le VOISINAGE NATIF MESURE
    # (`rec["voisins"]`, releve du `decisionView` live), on compte les unites dont le substrat
    # d'ENTITE porte `Summon`. C'est la contre-partie independante du `Count(Unique(UnitsWithTrait(
    # AdjacentUnits(...))))` -- une boucle plate contre un arbre, deux chemins qui doivent
    # coincider. Compter les seuls COMPAGNONS du montage rendait une attente FAUSSE (mesure #920 :
    # des decoys spawnes pendant les cycles de tour entouraient l'ancre).
    from engine.entities.traits.unit_trait import entity_trait_names
    from engine.runner.components import StatsComponent, UnitComponent
    porteurs, n_attendu = [], 0
    for v in (rec.get("voisins") or ()):
        e = st.get_entity(int(v["id"]))
        if e is None:
            continue
        uc, sc = e.get_component(UnitComponent), e.get_component(StatsComponent)
        if uc is None or not uc.alive:
            continue
        noms = entity_trait_names(sc.ctx if sc is not None else None, uc.visual_id)
        if TRAIT_COMPTE in noms:
            n_attendu += 1
            porteurs.append((v["id"], v["vis"]))
    out["voisins_summon"] = porteurs
    out["n_attendu"] = n_attendu
    effs = st.effects.active_effects(oid, unit_state_for_effects(st, oid)) if st.effects else []
    cible = next((e for e in effs if getattr(e, "name", None) == EFFECT_NAME), None)
    out["effet_actif_port"] = cible is not None
    ctx = dict(AttackDamageOperation._crit_board(st, aid, tid))
    ctx.update({"att_id": aid, "tgt_id": tid, "owner_id": oid})
    out["bonus_signe"] = (cible.create_effect_crit_damage_bonus_for_attack(ctx)
                          if cible is not None else None)
    ae = st.get_entity(aid)
    if ae is not None:
        from engine.runner.components import StatsComponent
        sc = ae.get_component(StatsComponent)
        if sc is not None:
            out["crit_damage_base_attaquant"] = sc.ctx.stat(StatType.CRIT_DAMAGE)
            out["crit_chance_base_attaquant"] = sc.ctx.stat(StatType.CRIT_CHANCE)
    return out


def run_case(a, rpc, Board, Harness, n, level, paliers) -> int:
    rid, sf = build(a, "n%d_l%d" % (n, level), level)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage(h, n, ennemi=a.ennemi, verbose=a.verbose,
                         porteur_defenseur=a.porteur_defenseur)
        if rec is None:
            print("[n=%d lvl=%d] REFUS : %s" % (n, level, why))
            return 2
        live, why = strike(h, rec)
        if live is None:
            print("[n=%d lvl=%d] REFUS : %s" % (n, level, why))
            return 2
        off = replay(h, rec)
        k = len(live)
        accord = (off[:k] == live)
        et = etages(h, rec)

        # `n_effectif` = le compte que le NATIF doit voir autour du PORTEUR, CALCULE A LA MAIN sur
        # le voisinage MESURE (cf. `etages`), jamais deduit du nombre de compagnons demande.
        # ⚠ `a.ennemi` N'ENTRE PAS dans ce calcul, et c'est le coeur du probe : `AdjacentUnits` ne
        # filtre aucun camp -- l'attente est donc la MEME que les compagnons soient amis ou non.
        n_effectif = et["n_attendu"]
        # GARDE DE DISCRIMINATION : sur un bras POSITIF, une attente NULLE ferait passer pour un
        # accord ce qui n'est qu'un canal muet des deux cotes (regime DEGENERE). On REFUSE plutot
        # que de rendre un vert vide.
        if attendu_summon(a.trait) and n > 0 and n_effectif == 0:
            print("[n=%d lvl=%d] REFUS : bras POSITIF mais AUCUN voisin `%s` mesure -- le montage "
                  "n'a rien pose d'eligible, un accord y serait DEGENERE (voisinage : %s)"
                  % (n, level, TRAIT_COMPTE, [(v["id"], v["vis"]) for v in rec["voisins"]]))
            return 2
        if not attendu_summon(a.trait) and n_effectif != 0:
            print("[n=%d lvl=%d] REFUS : bras NEGATIF mais %d voisin(s) `%s` mesure(s) (%s) -- le "
                  "montage n'est pas celui qu'on croit"
                  % (n, level, n_effectif, TRAIT_COMPTE, et["voisins_summon"]))
            return 2
        # `verse` = ce que le canal doit REELLEMENT ajouter : `ForAddition(get_OwnerIsCaster, ...)`
        # ne verse RIEN quand le porteur n'est pas l'attaquant, quel que soit son compteur.
        verse = 0 if a.porteur_defenseur else n_effectif

        mut = replay(h, rec, mutate="NOCHANNEL")
        mord = (mut[:k] != off[:k])
        attendu = (verse > 0)

        passif_attendu = (verse > 0) and (level != len(paliers))
        mut2 = replay(h, rec, mutate="PASSIF")
        mord2 = (mut2[:k] != off[:k])

        rc = 0
        # ⚠ LE BRAS `--porteur-defenseur` NE JUGE PAS LE DEGAT, et c'est une ATTRIBUTION MESUREE,
        # pas une exemption de confort. Sur le montage `blackHaarken` -> `tyranTyrantGuard`, le port
        # rend `+1` par coup PAR RAPPORT AU LIVE -- et il le rend AUSSI quand on ramene
        # `scripts/python/engine` a `origin/master`, c'est-a-dire quand CE PORT N'EXISTE PAS
        # (`DELTA [1, 1, 1, 1]` des deux cotes, meme salve `[2420, 2554, 2385, 1745]`). Le canal
        # MawClaws y est de toute facon MUET (`bonus_signe is None`, et `NOCHANNEL` rend le MEME
        # offline). Ce que ce bras confronte est donc l'ETAGE TRIGGER (`get_OwnerIsCaster` avec un
        # compteur PLEIN), pas la salve. Residu #920-r1.
        if not accord and not a.porteur_defenseur:
            rc |= 1
        if mord != attendu:
            rc |= 1
        if mord2 != passif_attendu:
            rc |= 1
        v = paliers[level - 1]
        print("[n=%d lvl=%d trait=%s ennemi=%s def=%s] verse attendu = %d x %d = %d"
              % (n, level, a.trait, a.ennemi, a.porteur_defenseur, v, verse, v * verse))
        print("        VOISINS `%s` MESURES : %s" % (TRAIT_COMPTE, et["voisins_summon"]))
        # ETAGE COMPTEUR, confronte SANS passer par le degat -- MAIS seulement quand l'effet est
        # ACTIF. ⚠ MESURE #920 : sur un effet INACTIF le `level` publie est PERIME -- releve
        # `level = 1` avec `active = false` et un voisinage VIDE, parce que
        # `RefreshEffectsOperation$$UpdateLevel` n'est atteint que par le chemin qui rafraichit un
        # effet ACTIF. Le comparer la accuserait le port pour un champ que le natif n'a pas remis a
        # jour. Quand l'effet est actif, il EST le compteur natif et vaut confrontation.
        if rec["actif_natif"] and rec["niveau_natif"] != n_effectif:
            print("        !! COMPTEUR NATIF (decisionView.effects[].level) = %s, attendu %d"
                  % (rec["niveau_natif"], n_effectif))
            rc |= 1
        if not rec["actif_natif"]:
            print("        [note] effet INACTIF -> `level` natif (%s) NON confronte : "
                  "`UpdateLevel` ne repasse pas dessus (PERIME)." % (rec["niveau_natif"],))
        if et["compteur"] != n_effectif:
            print("        !! COMPTEUR du port = %s, attendu %d" % (et["compteur"], n_effectif))
            rc |= 1
        # ETAGE CONDITION D'ACTIVITE -- observable PROPRE a cet effet (son voisin 1450 est
        # `YesTrigger`, donc toujours actif). `active == (compteur > 0)` des DEUX cotes.
        actif_attendu = (n_effectif > 0)
        if rec["actif_natif"] != actif_attendu:
            print("        !! ACTIVITE NATIVE = %s, attendue %s (CreateActiveCondition = "
                  "AmountIsGreaterThanZero(<compteur>))" % (rec["actif_natif"], actif_attendu))
            rc |= 1
        if et["effet_actif_port"] != actif_attendu:
            print("        !! ACTIVITE du port = %s, attendue %s"
                  % (et["effet_actif_port"], actif_attendu))
            rc |= 1
        # ETAGE TRIGGER, isole du compteur : sous `--porteur-defenseur` le compteur est PLEIN et le
        # bonus doit pourtant etre `None`.
        bonus_attendu = (v * verse) if verse else None
        if et["bonus_signe"] != bonus_attendu:
            print("        !! BONUS du port = %s, attendu %s" % (et["bonus_signe"], bonus_attendu))
            rc |= 1
        print("        COMPTEUR  natif=%s port=%s (attendu %d) | ACTIF natif=%s port=%s (attendu %s)"
              % (rec["niveau_natif"], et["compteur"], n_effectif, rec["actif_natif"],
                 et["effet_actif_port"], actif_attendu))
        print("        BONUS     port=%s (attendu %s)" % (et["bonus_signe"], bonus_attendu))
        if a.verbose:
            print("        ETAGES port %s" % (et,))
            print("        VOISINAGE %s" % [(x["id"], x["vis"], x["pos"]) for x in rec["voisins"]])
        print("        LIVE      %s" % (live[:6],))
        print("        OFFLINE   %s  accord=%s%s"
              % (off[:k][:6], accord,
                 "  [NON JUGE -- divergence PRE-EXISTANTE, cf. #920-r1 ; delta=%s]"
                 % ([o - l for o, l in zip(off[:k], live)][:6],) if a.porteur_defenseur else ""))
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
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--crit-damage", type=int, default=2000,
                    help="CritDamage des p-units. Pas de garde de saturation : le terme est "
                         "ADDITIF, donc le `Math.Max(0, .)` de CalculateCriticalDamage ne peut pas "
                         "mordre. La valeur sert seulement a rendre la salve lisible.")
    ap.add_argument("--n", default="0,1,2", help="nombre de compagnons ADJACENTS (un runner par n)")
    ap.add_argument("--level", type=int, default=3, help="niveau de la RELIQUE (1..10)")
    ap.add_argument("--trait", default=TRAIT_COMPTE,
                    help="le(s) trait(s) pose(s) sur les compagnons. `Summon` (0x2) est le SEUL "
                         "que `UnitsWithTrait` lit ici ; `Hero` est le bras NEGATIF (compagnons "
                         "adjacents mais sans le trait -> compteur 0, canal MUET, et effet publie "
                         "INACTIF puisque la `CreateActiveCondition` compare ce compteur a zero).")
    ap.add_argument("--porteur-defenseur", action="store_true",
                    help="BRAS TRIGGER : le porteur DEFEND au lieu d'attaquer (un `%s` externe "
                         "crite sur lui), ses summons restant ADJACENTS. "
                         "`ForAddition(get_OwnerIsCaster, ...)` = `AreEqual(Owner@+0x30, "
                         "Caster@+0x48)` ne doit RIEN verser -- alors que le compteur, lui, reste "
                         "PLEIN. TEMOIN NON NUL : un port qui lirait `get_OwnerIsTarget` "
                         "passerait TOUS les autres bras." % ATTACKER_EXT)
    ap.add_argument("--ennemi", action="store_true",
                    help="BRAS EQUIPE, et c'est le COEUR de ce probe : les compagnons Summon "
                         "passent cote ADVERSE. `AdjacentUnits` = `Units(AdjacentTiles(origin), "
                         "unique, sel) op_Subtraction origin` ne filtre AUCUN camp -> le compteur "
                         "doit RESTER n. C'est l'inverse exact du meme bras chez "
                         "`KardiocoreGalvanus`/`AmuletOfTheVoidwyrm`, dont l'etage est un "
                         "`AdjacentFriends`.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    paliers = paliers_du_gameconfig()
    ns = [int(x) for x in str(a.n).split(",") if x.strip()]
    print("== #920 MawClawsOfThyrax_ExtraCritDmg -- trait=%s ennemi=%s def=%s"
          % (a.trait, a.ennemi, a.porteur_defenseur))
    _garde_regime(a.level, paliers)
    _traits_json(a.trait)          # refus PRECOCE d'un trait inerte

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    # ⚠ CANAL RELIQUE. `load_state` tire `unitAbilityStates` elle-meme, mais SEULEMENT si un
    # transport AMBIANT est lie (`snapshot.bind_live_rpc`, #357/#363). Sans lui,
    # `UnitContext.tertiary_ability` reste `None` et `triggered_ability_state` retombe sur le
    # couple PASSIF, donc `extraCritDmg` au dernier palier -- et le bras PASSIF ne mordrait plus.
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)
    rc = 0
    for n in ns:
        rc |= run_case(a, rpc, Board, ChargeRegimeHarness, n, a.level, paliers)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
