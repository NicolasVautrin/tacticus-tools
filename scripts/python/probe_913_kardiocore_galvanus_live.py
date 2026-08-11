#!/usr/bin/env python
"""probe #913 -- MESURE de l'axe ADDITION du canal crit-DEGAT porte par une RELIQUE
(`KardiocoreGalvanus_ExtraCritDmg`, EffectType 0x5aa = 1450).

CRITERE BINAIRE, pose avant toute methode :

    « Le natif AJOUTE-t-il `extraCritDmg[niveau de RELIQUE] x <amis MECANIQUES adjacents au
      porteur>` au degat de CRIT que ce porteur INFLIGE, et le port fait-il pareil ? »

## L'ARTEFACT

`IdunBattle.Entities.Effects.Loki.KardiocoreGalvanus_ExtraCritDmgEffect$$CreateCritDamageBonus`
= `ForAddition(get_OwnerIsCaster, GetExtraCritAmount())`, ou `GetExtraCritAmount` (corps DEDUPLIQUE
avec `MawClawsOfThyrax_ExtraCritDmgEffect$$GetExtraCritAmount`) =
`Multiply(ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet), config@+0x60),
EffectLevel(Effect@DSLSelectors+0x38))`, et le niveau STOCKE que `RefreshEffectsOperation$$
UpdateLevel` y ecrit est `$$GetCalculateLevel` =
`Count(MechanicalUnits(AdjacentFriends(Owner@+0x30, unique: 1, selectionType: 3), 3))`.

Sa `CreateActiveCondition` est `<DSLTriggers+0x70>` = `YesTrigger` -> **TOUJOURS ACTIF**. C'est la
difference de forme avec ses deux voisins (`AmuletOfTheVoidwyrm`, `SupaCyborkBody`), dont la
condition est GEOMETRIQUE : ici l'effet est publie par `decisionView` meme a `n = 0`, donc
l'activite N'EST PAS un observable du compteur -- le seul observable est le DEGAT.

## LE MONTAGE, et pourquoi chaque piece y est

  * `admecRuststalker` est l'un des TROIS porteurs autorises, il est AU POOL, et il porte la
    relique AU SEED (`BC.Units[].TertiaryAbility = 1457`, `TertiaryAbilityLevel = 1`). On passe
    quand meme par `--equip-relic` (etat 2 de la gate relique) : c'est le seul moyen de MAITRISER
    le niveau, donc d'armer le bras `PASSIF`.
  * Le porteur est le **CASTER** (`get_OwnerIsCaster`), donc il est cote `p-units` et c'est LUI qui
    doit criter -> `--crit` (et non `--crit-target`). C'est l'inverse exact des deux
    `ForSubtraction` deja portes.
  * Son arme UNIQUE est melee (`weapons = [{hits: 2, DamageProfile: Energy}]`) : la salve est
    lisible coup par coup, sans arbitrage melee/distance.
  * Les COMPAGNONS portent le trait par `--unit-stat '<vid>:Traits=["Mechanical"]'` : c'est le
    substrat d'ENTITE (`BC.Units[].Traits` -> `BaseUnitComponent`) que `UnitExtensions$$
    IsMechanical` lit (#264). Ecrire la liste ENTIERE les debarrasse au passage de tout trait
    d'invisibilite, qui les ferait tomber du `selectionType = 3 = OnlyAliveAndTargetable`.
  * `n` (le nombre de compagnons ADJACENTS) est le levier : `n = 1` et `n = 2` doivent rendre DEUX
    bonus differents -- c'est ce qui prouve le PRODUIT et interdit de fitter un scalaire.

## LES BRAS

  1. LIVE -- le natif, l'oracle ;
  2. port (etat livre) -- doit egaler le live ;
  3. `NOCHANNEL` -- l'effet retire d'`EFFECT_CLASSES` (retombe sur `BaseEffect`, canal `None`) :
     doit DIVERGER ssi `n > 0`. C'est ce qui interdit l'accord degenere ;
  4. `PASSIF` -- le callable `tertiary_ability_state_of` retire du contexte : le port retombe alors
     sur `ability_level` (le niveau des PASSIFS, 50 en runner normalise -> dernier palier). Doit
     DIVERGER des que `n > 0` et que le niveau demande n'est pas le dernier palier ;
  5. `--trait` -- les TROIS traits d'`IsMechanical` (`Mechanical` 5, `LivingMetal` 1000,
     `Vehicle` 1029) doivent compter PAREIL ; `--trait Hero` est le bras NEGATIF (compagnons
     adjacents mais NON mecaniques -> compteur 0, canal muet) ;
  6. `--ennemi` -- les compagnons mecaniques passent cote ADVERSE : `AdjacentFriends` ne doit pas
     les compter (le natif filtre par `Friends(reference = Owner, ...)`).

Usage :
    python probe_913_kardiocore_galvanus_live.py --n 0,1,2
    python probe_913_kardiocore_galvanus_live.py --n 1 --level 10
    python probe_913_kardiocore_galvanus_live.py --n 2 --trait Vehicle
    python probe_913_kardiocore_galvanus_live.py --n 2 --trait Hero      # bras NEGATIF
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

#: porteur autorise de `KardiocoreGalvanus`, AU POOL, et EQUIPE AU SEED. Arme UNIQUE melee.
CARRIER = "admecRuststalker"
#: les deux porteurs de trait, patches par `--unit-stat`. Cote AMI par defaut.
COMPANIONS = ("admecDominus", "admecManipulus")
#: la CIBLE -- cote adverse, gonflee par `--hp-target` pour survivre a la salve.
TARGET = "tauCrisis"
#: l'ATTAQUANT du bras `--porteur-defenseur` : melee, AU POOL, et surtout NON porteur de la
#: relique (prendre un `admec*` confondrait les deux roles -- deux d'entre eux la portent AU SEED).
ATTACKER_EXT = "blackHaarken"
EFFECT_NAME = "KardiocoreGalvanus_ExtraCritDmg"    # cle EFFECT_CLASSES == nom decisionView
ABILITY_ID = "KardiocoreGalvanus"    # TriggeredAbilityType 0x5b1 = 1457 (la CONFIG)
VAR_KEY = "extraCritDmg"             # AbilityVariableType 0x42 = 66

#: les TROIS traits que `IdunBattle.Entities.UnitExtensions$$IsMechanical` accepte, plus le bras
#: NEGATIF. Tout autre trait ferait un bras MUET dont le zero accuserait le port a tort.
TRAITS_MECANIQUES = ("Mechanical", "LivingMetal", "Vehicle")
TRAITS_ADMIS = TRAITS_MECANIQUES + ("Hero",)


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

    Il n'y a PAS de garde de saturation ici, et c'est une DIFFERENCE de fond avec les deux
    `ForSubtraction` : `CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)`, or la
    somme est POSITIVE -- le clamp bas ne peut pas mordre.

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
    """`"Mechanical"` -> `"Mechanical"`. REFUSE tout trait hors des quatre admis : un trait inerte
    ferait tomber `n` a zero sans qu'aucune assertion ne designe la cause."""
    noms = [t.strip() for t in str(spec).split(",") if t.strip()]
    if not noms:
        raise SystemExit("--trait : liste vide")
    inconnus = [t for t in noms if t not in TRAITS_ADMIS]
    if inconnus:
        raise SystemExit("--trait : %s hors des traits admis %s (les trois d'`IsMechanical` "
                         "plus `Hero`, qui est le bras NEGATIF)" % (inconnus, list(TRAITS_ADMIS)))
    return ",".join('"%s"' % t for t in noms)


def attendu_mecanique(trait_spec: str) -> bool:
    """Le bras est-il POSITIF (au moins un trait d'`IsMechanical`) ou NEGATIF ?"""
    noms = [t.strip() for t in str(trait_spec).split(",") if t.strip()]
    return any(t in TRAITS_MECANIQUES for t in noms)


def build(a, tag, level):
    fd, sf = tempfile.mkstemp(prefix="probe_913_%s_" % tag, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    comps = '%s,%s' % COMPANIONS
    if a.porteur_defenseur:
        # BRAS `get_OwnerIsCaster` : le porteur DEFEND, ses amis mecaniques sont bien la (compteur
        # NON NUL), et le canal doit rester MUET. C'est ce qui separe cet effet de ses deux jumeaux
        # `get_OwnerIsTarget` -- un port qui confondrait les deux slots passerait TOUS les autres
        # bras et tomberait sur celui-ci.
        p_units, a_units = ATTACKER_EXT, "%s,%s" % (CARRIER, comps)
    else:
        # les compagnons sont du COTE du porteur par defaut (`AdjacentFriends`), et passent en face
        # sous `--ennemi` : c'est le bras qui prouve le filtre d'EQUIPE.
        p_units = CARRIER if a.ennemi else "%s,%s" % (CARRIER, comps)
        a_units = TARGET if not a.ennemi else "%s,%s" % (TARGET, comps)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--p-units", p_units, "--a-units", a_units,
            "--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
            "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[0], _traits_json(a.trait)),
            "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[1], _traits_json(a.trait)),
            # Le PORTEUR est reduit a `Hero` + `Mechanical` : `Camouflage` / `Infiltrate` /
            # `Unstoppable` ne changent rien au canal mesure mais brouillent la lecture de la salve.
            # `Mechanical` est CONSERVE bien qu'inutile au compteur (`AdjacentFriends` EXCLUT le
            # porteur, `op_Subtraction unit`) : le retirer changerait l'unite sans raison lue.
            "--unit-stat", '%s:Traits=["Hero","Mechanical"]' % CARRIER,
            "--hp-target", "900000", "--hp-player", "900000",
            "--no-ai", "--crit", "100,%d" % a.crit_damage, "--block-target", "0,0"]
    if a.porteur_defenseur:
        # L'attaquant EXTERNE est reduit a `Hero` pour la LISIBILITE : `LetTheGalaxyBurn` ajoute
        # des coups dont le compte depend de la cible et `Terrifying` pose un effet defensif --
        # deux canaux valides AILLEURS, qui ne feraient ici que brouiller la salve.
        argv += ["--unit-stat", '%s:Traits=["Hero"]' % ATTACKER_EXT,
                 # le porteur DEFEND : c'est lui qui doit encaisser sans mourir.
                 "--hp-player", "900000"]
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


def _effet_natif(h, carrier_id: int):
    """`(active, level)` de l'effet, LUS sur `decisionView` (`includeInactive`), ou `None` si
    l'effet est ABSENT du canal (= la relique n'est PAS montee -> montage mort, jamais rabattu).

    DEUX observables NATIFS distincts, et le second est le plus precieux :

      * `active` -- ATTENDU `True` en TOUTE circonstance (`CreateActiveCondition` =
        `<DSLTriggers+0x70>` = `YesTrigger`). Ce n'est donc PAS un observable du compteur, juste le
        controle positif du montage. C'est l'inverse d'`AmuletOfTheVoidwyrm`, dont l'activite EST
        le compteur compare a zero ;
      * `level` -- le niveau STOCKE dans `EffectComponent+0x68`, que
        `IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel` tient EGAL a
        `$$GetCalculateLevel`. C'est donc **le compteur natif LU DIRECTEMENT**, sans passer par le
        degat : l'etage COMPTEUR devient confrontable a lui seul, independamment de la magnitude.
        Mesure de decouverte : `admecRuststalker` deploye en (1,0) avec deux amis mecaniques en
        (0,0) et (1,1) publie `level: 2`."""
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
    `AdjacentTilesSelector$$Select` enumere via `IterateAdjacentTiles`), JAMAIS `hexgeo.distance
    == 1` : sur un board a `Bridge` les deux different, et c'est le substrat stocke qui fait foi
    (#589-r1-r1-r2-r1-r8).

    ORDRE : cycle de tour D'ABORD, placements ENSUITE -- on veut que les positions LUES au snapshot
    soient celles qu'on a posees."""
    import hexgeo
    # DEUX ROLES, confondus par DEFAUT et SEPARES sous `--porteur-defenseur` :
    #   * `ancre_vis` = le PORTEUR de la relique -- c'est AUTOUR de lui qu'on compte les amis
    #     mecaniques (`AdjacentFriends(Owner)`), donc c'est lui qu'on ancre ;
    #   * `att_vis`   = l'ATTAQUANT, celui qui crite. Il doit etre au CONTACT du defenseur.
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
        """Occupation REELLE, relue a chaque etape. La version precedente pre-soustrayait les
        unites « qui vont liberer leur case » : elle proposait alors comme ancre une tuile ENCORE
        occupee, et le `place` echouait sans que rien ne designe la cause (mesure : REFUS
        « placement du porteur refuse » sur les trois valeurs de `n`)."""
        ex = set(exclure)
        return {_pos_de(u) for u in h.alive() if u.get("id") not in ex}

    def _pose(uid, cands, quoi):
        """Un `place` peut echouer sur une tuile pourtant libre AU MOMENT DU CALCUL (une unite y a
        ete posee entre-temps) : on essaie les candidats dans l'ordre plutot que d'abandonner sur
        le premier -- c'est du montage, pas de la mesure."""
        occ = _occ((uid,))
        for c in cands:
            if c not in occ and h.place(uid, c):
                return c
        return None

    # L'ancre du PORTEUR : il lui faut `n + 1` voisins NATIFS -- `n` pour les compagnons, un pour
    # l'autre camp (les deux armes en jeu sont melee, donc contact). L'occupation est celle du
    # MOMENT : les unites a deplacer libereront leur case ensuite, et `_pose` re-filtre a chaque
    # etape.
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

    # ORDRE -- et il a ete CORRIGE par une mesure, pas choisi. Version precedente : n'eloigner que
    # les compagnons SURNUMERAIRES, puis poser le porteur. Le bras `--ennemi` y REFUSAIT
    # systematiquement (`applyAction` rendait `mutated: false, changes: []` sans erreur), parce que
    # `place` est un `MoveUnitOperation` NATIF COMPLET : le passif `OptimizedGait` du porteur
    # declenche une attaque d'opportunite quand il se deplace pres d'un ennemi, ce qui CONSOMME son
    # action avant la salve qu'on veut mesurer. Les autres bras y echappaient par hasard (leurs
    # compagnons sont AMIS et la cible spawne loin) -- c'est exactement le genre d'accord
    # accidentel qu'on ne veut pas laisser porter un verdict.
    #
    # Donc : TOUT le monde part LOIN d'abord, ensuite le porteur, ensuite seulement ceux qui
    # doivent revenir au contact.
    # `mobiles` = tout le monde SAUF le porteur (qui va sur l'ancre). Sous `--porteur-defenseur`
    # c'est l'ATTAQUANT qui vient au contact ; sinon c'est la CIBLE.
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

    # --- RECUPERER l'action du porteur si le MONTAGE l'a consommee --------------------------------
    # `place` est un `MoveUnitOperation` natif COMPLET : amener une unite ADVERSE au contact du
    # porteur declenche ses reactions (le passif `OptimizedGait` de `admecRuststalker` attaque au
    # mouvement), et le porteur se retrouve sans action -- l'`applyAction` suivant rend alors
    # `mutated: false, changes: []`, SANS erreur. C'est ce qui faisait REFUSER le bras `--ennemi`
    # alors que son montage etait bon (son compteur natif, lui, etait deja lisible et valait 0).
    # Un cycle de tour complet le lui rend ; les positions sont RE-MESUREES juste apres, jamais
    # supposees.
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

    # CONTROLE POSITIF DU MONTAGE : l'effet DOIT etre publie et ACTIF a tout `n` (`YesTrigger`).
    # Un `None` ici = la relique n'est pas montee -> tout le bras mesurerait autre chose.
    lu = _effet_natif(h, porteur["id"])
    if lu is None:
        return None, ("l'effet %s est ABSENT du canal (meme `includeInactive`) -- la relique n'est "
                      "PAS montee sur %s, le bras ne mesurerait rien" % (EFFECT_NAME, CARRIER))
    actif, niveau_natif = lu
    if actif is not True:
        return None, ("l'effet %s est publie INACTIF : la `CreateActiveCondition` native est "
                      "`<DSLTriggers+0x70>` = YesTrigger, donc CONSTANTE VRAIE. A instruire -- "
                      "c'est une REFUTATION de la RE, pas un montage rate." % EFFECT_NAME)

    atk_type = h.normal_attack_type(att["id"], dv)
    rec = {"caster": att["id"], "target": cible["id"], "ability_type": int(atk_type),
           # `porteur` != `caster` SOUS `--porteur-defenseur` seulement : c'est l'id sur lequel les
           # etages du port sont evalues (`owner_id` du canal), et il vaut le caster partout ailleurs.
           "porteur": porteur["id"],
           "n": n_mesure, "anchor": anchor, "contact": contact, "step_to": None,
           "actif_natif": bool(actif), "niveau_natif": niveau_natif, "ennemi": bool(ennemi),
           "porteur_defenseur": bool(porteur_defenseur)}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    if verbose:
        print("    ancre=%s contact=%s | compagnons adjacents = %d | actif=%s niveau NATIF=%s"
              % (anchor, contact, n_mesure, actif, niveau_natif))
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

    Rend, dans l'ordre du natif : le COMPTEUR (`GetCalculateLevel`), le couple `(level, mult)` de
    `GetAbilityState(effet)`, et le scalaire SIGNE que le canal verse (`ForAddition`, donc
    POSITIF). C'est ce qui permet de dire QUEL etage bouge quand le degat diverge."""
    from engine.runner.components import (adjacent_mechanical_friends_count,
                                          unit_state_for_effects)
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.base import triggered_ability_state
    from engine.entities.stats import StatType
    st = h.offline_state(rec)
    aid, tid = int(rec["caster"]), int(rec["target"])
    # `owner_id` = le PORTEUR de l'effet, que la boucle native ECRASE dans `AbilityEntities+0x18` a
    # chaque iteration. Il vaut l'ATTAQUANT partout, SAUF sous `--porteur-defenseur` ou il vaut la
    # cible -- et c'est precisement le regime ou `get_OwnerIsCaster` doit rendre FAUX.
    oid = int(rec.get("porteur", aid))
    out = {"compteur": adjacent_mechanical_friends_count(st, oid),
           "ability_state": triggered_ability_state(st, oid, ABILITY_ID)}
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

        # `n_effectif` = le compte que le NATIF doit voir autour du PORTEUR. Les compagnons sont
        # poses adjacents dans tous les bras ; ce qui varie est leur ELIGIBILITE (trait mecanique,
        # meme equipe). Sous `--porteur-defenseur` le compteur reste NON NUL -- c'est justement le
        # TEMOIN qui rend le bras probant : le canal doit se taire malgre un compteur plein.
        n_effectif = n if (attendu_mecanique(a.trait) and not a.ennemi) else 0
        # `verse` = ce que le canal doit REELLEMENT ajouter : `ForAddition(get_OwnerIsCaster, ...)`
        # ne verse RIEN quand le porteur n'est pas l'attaquant, quel que soit son compteur.
        verse = 0 if a.porteur_defenseur else n_effectif

        # CONTRE-EPREUVE 1 : sans le canal, le rejeu doit CHANGER ssi le canal verse.
        mut = replay(h, rec, mutate="NOCHANNEL")
        mord = (mut[:k] != off[:k])
        attendu = (verse > 0)

        # CONTRE-EPREUVE 2 : sans le canal TERTIAIRE, le port lit le niveau PASSIF (-> dernier
        # palier). Ne peut mordre que si le canal verse ET que le niveau demande n'est pas le dernier.
        passif_attendu = (verse > 0) and (level != len(paliers))
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
        print("[n=%d lvl=%d trait=%s ennemi=%s def=%s] verse attendu = %d x %d = %d | actif=%s"
              % (n, level, a.trait, a.ennemi, a.porteur_defenseur, v, verse, v * verse,
                 rec["actif_natif"]))
        et = etages(h, rec)
        # ETAGE COMPTEUR, confronte SANS passer par le degat : le niveau STOCKE que le natif publie
        # (`EffectComponent+0x68`, tenu egal a `GetCalculateLevel` par `RefreshEffectsOperation$$
        # UpdateLevel`) contre celui que le port recalcule.
        if rec["niveau_natif"] != n_effectif:
            print("        !! COMPTEUR NATIF (decisionView.effects[].level) = %s, attendu %d"
                  % (rec["niveau_natif"], n_effectif))
            rc |= 1
        if et["compteur"] != n_effectif:
            print("        !! COMPTEUR du port = %s, attendu %d" % (et["compteur"], n_effectif))
            rc |= 1
        # ETAGE TRIGGER, isole du compteur : sous `--porteur-defenseur` le compteur est PLEIN et le
        # bonus doit pourtant etre `None`. Un port qui lirait `get_OwnerIsTarget` passerait tous les
        # autres bras et tomberait ICI.
        bonus_attendu = (v * verse) if verse else None
        if et["bonus_signe"] != bonus_attendu:
            print("        !! BONUS du port = %s, attendu %s" % (et["bonus_signe"], bonus_attendu))
            rc |= 1
        print("        COMPTEUR  natif=%s port=%s (attendu %d) | BONUS port=%s (attendu %s)"
              % (rec["niveau_natif"], et["compteur"], n_effectif, et["bonus_signe"], bonus_attendu))
        if a.verbose:
            print("        ETAGES port %s" % (et,))
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
                    help="CritDamage des p-units. Pas de garde de saturation ici : le terme est "
                         "ADDITIF, donc le `Math.Max(0, .)` de CalculateCriticalDamage ne peut pas "
                         "mordre. La valeur sert seulement a rendre la salve lisible.")
    ap.add_argument("--n", default="0,1,2", help="nombre de compagnons ADJACENTS (un runner par n)")
    ap.add_argument("--level", type=int, default=3, help="niveau de la RELIQUE (1..10)")
    ap.add_argument("--trait", default="Mechanical",
                    help="le(s) trait(s) pose(s) sur les compagnons, parmi les TROIS que "
                         "`IdunBattle.Entities.UnitExtensions$$IsMechanical` accepte "
                         "(`Mechanical` 5, `LivingMetal` 1000, `Vehicle` 1029) -- ils doivent tous "
                         "compter PAREIL. `Hero` est le bras NEGATIF : compagnons adjacents mais "
                         "NON mecaniques -> `MechanicalUnitsSelector$$Select` les ecarte, compteur "
                         "0, canal muet.")
    ap.add_argument("--porteur-defenseur", action="store_true",
                    help="BRAS TRIGGER : le porteur DEFEND au lieu d'attaquer (un `%s` externe "
                         "crite sur lui), ses amis mecaniques restant ADJACENTS. "
                         "`ForAddition(get_OwnerIsCaster, ...)` = `AreEqual(Owner@+0x30, "
                         "Caster@+0x48)` ne doit RIEN verser -- alors que le compteur, lui, reste "
                         "PLEIN. C'est le TEMOIN NON NUL qui separe cet effet de ses deux jumeaux "
                         "`get_OwnerIsTarget` (`AmuletOfTheVoidwyrm`, `SupaCyborkBody`) : un port "
                         "qui confondrait les deux slots passerait TOUS les autres bras."
                         % ATTACKER_EXT)
    ap.add_argument("--ennemi", action="store_true",
                    help="BRAS EQUIPE : les compagnons mecaniques passent cote ADVERSE. "
                         "`AdjacentFriends` = `Friends(reference = Owner, Units(AdjacentTiles) - "
                         "Owner)` ne doit PAS les compter -> compteur 0, canal muet.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    paliers = paliers_du_gameconfig()
    ns = [int(x) for x in a.n.split(",") if x.strip()]
    print("== #913 KardiocoreGalvanus_ExtraCritDmg -- trait=%s ennemi=%s" % (a.trait, a.ennemi))
    _garde_regime(a.level, paliers)

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    # ⚠ CANAL RELIQUE. `load_state` tire `unitAbilityStates` elle-meme, mais SEULEMENT si un
    # transport AMBIANT est lie (`snapshot.bind_live_rpc`, #357/#363) -- la fixture `rpc` des tests
    # le pose, un probe doit le faire. Sans lui, `UnitContext.tertiary_ability` reste `None` et
    # `triggered_ability_state` retombe sur le couple PASSIF, donc `extraCritDmg` au dernier palier.
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)
    rc = 0
    for n in ns:
        rc |= run_case(a, rpc, Board, ChargeRegimeHarness, n, a.level, paliers)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
