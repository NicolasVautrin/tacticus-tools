"""#605 -- `HellfireShells` (ActiveAbilityType 1080), face COMBAT.

Ce que ces bras GARDENT (et pas seulement ce qu'ils mesurent) :

  * `test_registre_offline`   -- l'entree au registre porte SES DEUX donnees obligatoires
    (`TARGETING_OPTIONS` lu du preset statique `<TargetingOptions statics>+0x140`,
    `ABILITY_ATTACK_TYPE` = 3e argument d'`AActiveAbility$$.ctor`), et le contrat de DISJONCTION
    est verifie PAR LE CODE (1080 retiree de `TARGETING_OPTIONS_UNPORTED` par le meme commit) ;
  * `test_arbre_offline`      -- la FORME de l'arbre : un `If` sur DEUX `AttackWithAttackDamage`
    DISTINCTS, et l'ORDRE des branches (`then` = la branche AUGMENTEE). Une inversion donnerait
    exactement le comportement contraire sur un `BigTarget`, sans aucune erreur ;
  * `test_hits_discriminants_offline` -- le couple `(nrOfHits, extraHit)` du kit SEPARE bien les
    deux branches. Un temoin ou `extraHit == 0` rendrait les deux branches IDENTIQUES et son
    accord ne prouverait RIEN ; ce bras assertionne sa propre discriminance ;
  * `test_degats_bit_exact_live` -- la SEQUENCE de degats coup par coup, natif vs port, MT offline
    cale sur `dumpRng`, sur une cible SANS `BigTarget` puis sur une cible AVEC. C'est le bras qui
    confronte le NOMBRE DE COUPS a l'oracle.

Aucun `pytest.skip` de complaisance : un montage qui ne s'installe pas ECHOUE (#268).

MONTAGE. Le porteur est `ultraNpc4HeavyIntercessor`, le VRAI porteur npc de 1080, amene par le
CHEMIN DE STATS EXPLICITE (`--explicit-stats`, #419-r1-tr12-r2) : il arrive avec SES stats, SES
traits et SES armes -- ce n'est PAS une greffe. Les deux autres porteurs sont
`ultraNpc4HeavyIntercessorSurv` (npc) et le SUMMON `ultraSmnHeavyIntercessor`, invoque par le
passif d'ENVIRONNEMENT `PowerUp_SummonSpawn_ultraSmnHeavyIntercessor` (1536) -- donc sans
invocateur du pool.

⚠ LES PORTEURS NE SONT PAS PLACES PAR `--place`. Mesure du 2026-08-10 : sur un montage par ailleurs
identique, un porteur pose par `--place` n'emettait qu'UN coup la ou le meme porteur laisse a son
SpawnPoint en emettait DEUX (meme config, meme seed, meme distance a la cible, `patch_mordu` verifie
des deux cotes). Ce sont les CIBLES qu'on deplace (`--a-place`) pour amener la configuration --
jamais le porteur.

⚠ ET CETTE MESURE NE SE REPRODUIT PLUS (2026-08-15, build `t6dpr4k06g`, #605-r1).
`probe_605r1_place_vs_spawn.py` joue SIX bras -- spawn, `--place` sur la tuile du cast, `--place`
puis deplacement d'une tuile, la tuile LITTERALE de la fiche (`3,4`), et le roster exact de CE
module avec puis sans `--place` -- et les six rendent **2** coups. Les deux lectures que le residu
laissait ouvertes sont donc eliminees dans ce regime : ni artefact de harnais, ni canal natif
positionnel. Ce qui varie d'un bras a l'autre est la MAGNITUDE (les bras ayant consomme un
deplacement partagent leurs rolls), pas le COMPTE.

La prescription ci-dessus est NEANMOINS conservee : la cause de la mesure du 2026-08-10 reste
inconnue, et rien ne dit qu'elle ne peut pas revenir. Elle n'est simplement plus un fait du build
courant, et elle est desormais VERIFIABLE -- rejouer le probe est ce qui la refonde ou la leve,
pas la relecture de ce paragraphe.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pris LARGE : charger UNE ability tire le registre, le vocabulaire
        # DSL, les Operations, l'IA et le pathfinding -- une liste choisie serait un faux vert.
        # Foyers vraiment load-bearing : `abilities/ultramarines.py` (l'arbre),
        # `handler.py` + `attack_type.py` + `targeting.py` (les registres confrontes),
        # `abilities/behaviours/combat.py` et `operations/damage_ops/ability.py` (la route de
        # degat), `entities/behaviours.py` (`If` LAZY), `entities/triggers.py` (`HasTrait`),
        # `runner/prng.py` (l'ORDRE de consommation).
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1080 HellfireShells` : l'oracle est le jeu "
              "lui-meme (nombre de coups selon le trait `BigTarget` de la CIBLE, montant coup par "
              "coup, ORDRE des tirages). Un changement de build peut donc faire changer ce fichier "
              "d'avis sans qu'une ligne du port bouge.",
}

import json

import pytest

import gameconfig as GC
import stream_events as SE

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.pathfinding.board import Board
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.abilities.ultramarines import (HELLFIRE_SHELLS_ID, HellfireShellsAbility,
                                                  hellfire_shells_hits, hellfire_shells_tree)
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "999"
PORTEUR = "ultraNpc4HeavyIntercessor:33"      # VRAI porteur npc -> `--explicit-stats`
PORTEUR_VIS = "ultraNpc4HeavyIntercessor"
CIBLE_SANS = "ultraTitus"                     # AUCUN trait `BigTarget`
CIBLE_AVEC = "astraBullgryn"                  # traits: Hero, BigTarget
ABILITY = int(ActiveAbilityType.HellfireShells)          # 1080


# ------------------------------------------------------------------ helpers de lecture live

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _vue(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _by_vis(dv, vis):
    return [u for u in _units(dv) if (u.get("visualId") or "") == vis]


def _act(rpc, rid, action, timeout=240):
    return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)


def _montants_natifs(res, cible_id):
    """La SEQUENCE coup par coup du NATIF (tags `Amount` des pas `UnitDamaged` portant
    `Active_Ability_Type == 1080`), resolue PAR NOM de pas -- un ordinal fige designerait le pas
    VOISIN au prochain retrait de membre, sans erreur ni trace. Un TOTAL juste ne prouve rien :
    c'est la SEQUENCE, et surtout sa LONGUEUR, qui mord ici."""
    out = []
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("step") != SE.step_id("UnitDamaged"):
                continue
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if (t.get("Active_Ability_Type") == ABILITY
                    and int(t.get("Target_Id", -1)) == int(cible_id)):
                out.append(int(t["Amount"]))
    return out


def _etat(rpc, rid, board):
    dv = _vue(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    ab = rpc("unitAbilityStates", {"runnerId": rid}, 60)
    assert _ok(dv) and _ok(ob) and _ok(snap), "capture live KO -- montage non installe"
    st = load_state(dv, ob, snap, board=board, ability_states=ab)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    assert _ok(s), "dumpRng KO -- MT non calable ; sans lui le degat offline est un faux 0"
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    st.rng = rng
    return dv, st


# ------------------------------------------------------------------------------- OFFLINE

def test_registre_offline():
    """Les DEUX donnees obligatoires du registre, et le contrat de DISJONCTION -- RE-LU DANS LE
    CODE, jamais soustrait d'un compte herite."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert ABILITY_CLASSES.get(ABILITY) is HellfireShellsAbility, \
        "1080 absente d'ABILITY_CLASSES = NO-OP SILENCIEUX : la decision caste, l'execution ignore"

    opts = HellfireShellsAbility.TARGETING_OPTIONS
    assert opts is not None, "sans masque, AUCUN gate n'est applique (degradation permissive)"
    # `<TargetingOptions statics>+0x168` = `<preset +0x140>+0x28` = 0x4002, LU dans le `.cctor`.
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy) == 0x4002
    assert opts.self_cast is False                       # `<preset>+0x00 isSelfCasting = 0`
    assert opts.range is not None and opts.range.use_range_from_config is True   # statics+0x18
    assert int(opts.force_melee_target) == 0             # `<preset>+0x20` = RangedBool.True

    # 3e argument d'`AActiveAbility$$.ctor(this, &opts, 0)` -- TRANSCRIT, pas deduit du profil.
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack

    # DISJONCTION : le masque vivait dans `TARGETING_OPTIONS_UNPORTED` (forme STATIC-COPY) ; il a
    # MIGRE sur la classe avec la face COMBAT. Deux sources = contrat viole.
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED


def test_hits_discriminants_offline():
    """Le couple `(nrOfHits, extraHit)` du kit SEPARE-t-il les deux branches ?

    Ce bras assertionne sa PROPRE discriminance : si `extraHit` valait 0, les deux
    `AttackWithAttackDamage` seraient identiques et l'accord du bras live ne prouverait RIEN sur
    l'ordre des branches ni sur le trigger. Lu du gameconfig, jamais fige."""
    cfg = GC.ability(HELLFIRE_SHELLS_ID) or {}
    base, big = hellfire_shells_hits(cfg)
    consts = (cfg.get("constants") or {})
    assert base == int(consts["nrOfHits"])                    # `GetNumberConstant(0x2f)`
    assert big == base + int(consts["extraHit"])              # `+ GetNumberConstant(0x2b)`
    assert big != base, ("temoin NON DISCRIMINANT : `extraHit` vaut 0, les deux branches du `If` "
                         "rendraient le meme nombre de coups")
    assert base >= 1 and big >= 2


def test_arbre_offline():
    """La FORME de l'arbre : un `If` sur DEUX feuilles d'attaque DISTINCTES, et l'ORDRE des
    branches. Le decompile alloue `local_238` (hits = nrOfHits) PUIS `pvVar8`
    (hits = nrOfHits + extraHit) et appelle `If(cond, pvVar8, local_238)` -- donc `then` est la
    branche AUGMENTEE. Une inversion serait silencieuse et exactement contraire."""
    from engine.entities.behaviours import If as IfBehaviour
    from engine.entities.triggers import HasTrait
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage

    cfg = GC.ability(HELLFIRE_SHELLS_ID) or {}
    base, big = hellfire_shells_hits(cfg)
    profil = (cfg.get("constants") or {}).get("damageProfile")
    arbre = hellfire_shells_tree(base, big, profil)

    assert isinstance(arbre, IfBehaviour)
    assert isinstance(arbre.cond, HasTrait)
    assert int(arbre.cond.trait) == int(UnitTrait.BigTarget) == 0x3f9
    assert type(arbre.cond.unit).__name__ == "Target"         # `Target@DSLSelectors+0x60`

    for branche, attendu in ((arbre.then, big), (arbre.otherwise, base)):
        assert isinstance(branche, AttackWithAttackDamage)
        assert branche.hits_override == attendu
        assert branche.profile == profil                     # `GetDamageProfile(config@0x60)`
        assert branche.is_melee is False                     # `attackRangeType = Ranged`
        assert type(branche.target_sel).__name__ == "Target"
        assert branche.ability_type == ABILITY
    assert arbre.then is not arbre.otherwise, "deux behaviours DISTINCTS, pas un compte partage"


# ---------------------------------------------------------------------------------- LIVE

@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner):
    """Runner `--no-ai` avec DEUX porteurs npc (un cast par cible : 1080 est a usage unique par
    unite -- `UnitStats_ActiveAbility_CanStillBeUsed` passe a 0) et DEUX cibles, l'une SANS le
    trait `BigTarget`, l'autre AVEC.

    Ce sont les CIBLES qu'on place (`--a-place`), pres des SpawnPoints de mon camp : les porteurs
    restent ou le natif les depose (cf. l'avertissement en tete de module). L'armure et le block
    des cibles sont mis a zero pour que CHAQUE coup soit visible -- sinon un coup absorbe ne se
    distingue pas d'un coup absent, et le compte, qui EST l'observable, deviendrait illisible."""
    built = build_runner(SEED, extra=[
        "--board", BOARD, "--no-ai", "--explicit-stats", PORTEUR,
        "--p-units", "%s,%s" % (PORTEUR, PORTEUR),
        "--a-units", "%s,%s" % (CIBLE_SANS, CIBLE_AVEC),
        "--armor-target", "0", "--block-target", "0,0", "--hp-target", "200000",
        "--a-place", "%s:1,2" % CIBLE_SANS, "--a-place", "%s:3,2" % CIBLE_AVEC], keep=True)
    rid = built["rid"]
    dv = _vue(rpc, rid)
    porteurs = _by_vis(dv, PORTEUR_VIS)
    assert len(porteurs) == 2, "porteurs absents -- `--explicit-stats` KO : %r" % (porteurs,)
    sans = _by_vis(dv, CIBLE_SANS)
    avec = _by_vis(dv, CIBLE_AVEC)
    assert sans and avec, "cibles absentes du plateau"
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph KO"
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq"),
            "porteurs": [u["id"] for u in porteurs],
            "sans": sans[0]["id"], "avec": avec[0]["id"]}


@pytest.mark.parametrize("cle,attendu_plus", [("sans", False), ("avec", True)])
def test_degats_bit_exact_live(env, rpc, cle, attendu_plus):
    """UN cast, et la SEQUENCE de degats coup par coup confrontee au natif.

    Le discriminant PREMIER est la LONGUEUR de la sequence : `nrOfHits` hors `BigTarget`,
    `nrOfHits + extraHit` avec. Le montant coup par coup vient ensuite -- et il ne peut pas etre
    une COMPENSATION, puisqu'un total juste avec un mauvais nombre de coups aurait une sequence
    differente."""
    rid, board = env["rid"], env["board"]
    cible = env[cle]
    # Un porteur par cible : l'ability est a usage unique par unite.
    porteur = env["porteurs"][0 if cle == "sans" else 1]

    cfg = GC.ability(HELLFIRE_SHELLS_ID) or {}
    base, big = hellfire_shells_hits(cfg)
    attendu = big if attendu_plus else base

    dv0, st = _etat(rpc, rid, board)
    # Le trait de la CIBLE est LU sur l'ETAT PORTE par le MEME accesseur que le trigger natif
    # (`UnitExtensions$$HasTrait`, substrat d'entite : `combatSnapshot.units[].traits` quand il
    # existe). Le relire depuis un kit gameconfig fabriquerait un temoin qui ne repond pas a la
    # question que `HasTrait(Target@0x60, 0x3f9)` pose.
    from engine.runner.abilities.attack_query import _has_trait
    a_bigtarget = _has_trait(st, cible, int(UnitTrait.BigTarget))
    assert a_bigtarget is attendu_plus, \
        "montage non conforme : `BigTarget` de %s = %r (attendu %r)" % (cle, a_bigtarget,
                                                                       attendu_plus)
    runner = Runner(st).install_default_handlers(20)

    res = _act(rpc, rid, {"kind": "ability", "casterId": porteur, "targetId": cible,
                          "abilityType": ABILITY})
    a0 = ((res or {}).get("actions") or [{}])[0]
    assert a0.get("ok") and a0.get("mutated"), "le natif REFUSE le cast : %r" % (a0,)
    natif = _montants_natifs(res, cible)

    runner.apply(ActiveAbilityMessage(porteur, cible, ABILITY))
    diag = runner.ability_handler.last or {}
    atk = (diag or {}).get("main_attack") or {}
    port = [int(x) for x in (atk.get("per_hit") or [])]

    assert len(natif) == attendu, \
        "NATIF : %d coup(s) pour une cible %s BigTarget, attendu %d -- %r" % (
            len(natif), "AVEC" if attendu_plus else "SANS", attendu, natif)
    assert len(port) == attendu, \
        "PORT : %d coup(s), attendu %d -- diag=%r" % (len(port), attendu, diag)
    assert port == natif, "sequence coup par coup PORT %r != NATIF %r" % (port, natif)
    assert diag.get("hits") == attendu and diag.get("big_target") is attendu_plus
