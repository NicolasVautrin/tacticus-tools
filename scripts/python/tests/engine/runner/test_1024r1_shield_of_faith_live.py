"""#1024-r1 -- `ShieldOfFaith` (mythique 1453 d'`adeptExorcist`) : le PORT confronte au NATIF.

L'attaquant ami MYTHIQUE crite -> l'Exorcist lui accorde un bouclier de `shieldPct` % de ses PV MAX,
`unless it already has a shield`. Le natif passe par DEUX temps -- les vecteurs enfilent un
`TriggerAbilityDelayed`, et c'est le re-declenchement en `EventTriggerType.Custom` qui pose. Ce
fichier joue l'attaque LIVE puis la REJOUE au port sur la MEME graine MT, et compare le BOUCLIER.

TROIS BRAS, et les deux derniers sont ce qui rend le premier concluant :

  `positif`     -- mythique L4 (`shieldPct` 50), `--crit 100,700` : bouclier NON NUL des deux cotes.
  `sans_crit`   -- `--crit 0,0` : ZERO des deux cotes. Exerce `WasCrit()`.
  `sans_rarete` -- `--unit-stat <attaquant>:Rarity=4` : ZERO des deux cotes. Exerce
                   `HasRarity(Attacker, idun.meta.Rarity.Mythic = 5)`.

⚠ **LE BRAS DE RARETE EST LE SEUL QUI SORTE DU REGIME DEGENERE.** `rl_duel build` impose
`targetRarity = 5` (`rl_collect_batch._TARGET_RARITY`), donc dans un runner standard TOUTE unite
normalisee est Mythic et le gate `HasRarity` est uniformement VRAI : un port qui l'OUBLIERAIT serait
d'accord avec le natif dans tous les autres bras. `--unit-stat "<vis>:Rarity=N"` est ecrit APRES la
normalisation, et c'est ce qui l'eteint.

⚠ **UN ACCORD SUR ZERO NE PROUVE RIEN SEUL.** Les deux bras negatifs n'ont de sens que parce que le
bras positif est NON NUL, et chacun l'assertionne explicitement plutot que de se contenter du
double zero.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER
        "scripts/python/engine/runner/operations/triggers/loki/shield_of_faith.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/pending.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/dsl/base.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Test LIVE : monte adeptExorcist avec sa mythique ShieldOfFaith, joue l'attaque "
              "normale au natif et la REJOUE au port sur la MEME graine MT, compare le BOUCLIER "
              "pose sur l'attaquant. Trois bras dont deux contre-epreuves (WasCrit, HasRarity).",
}

import pytest  # noqa: E402

from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.entities.rarity import Rarity  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.runner.components import (HealthComponent, ShieldComponent,  # noqa: E402
                                      StatsComponent)
from engine.runner.messages import AttackUnitMessage  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402
from engine.runner.runner import Runner  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402

PORTEUR = "adeptExorcist"          # MoW `lineup` ; `mythicAbilities == ["ShieldOfFaith"]`
ABILITY = "ShieldOfFaith"
SHIELD_OF_FAITH = int(TriggeredAbilityType.ShieldOfFaith)      # 0x5ad = 1453
ATTAQUANT = "adeptRetributor"      # l'ATTAQUANT ami -- c'est LUI qui recoit le bouclier
FIGURANT = "adeptCanoness"
CIBLE = "tyranTyrantGuard"
LOIN = "tyranParasite"
BOARD = "MC1_67"                   # 7x9 tout Grass -> geometrie PILOTEE, jamais subie
NIVEAU = 4                         # `shieldPct[4]` = 50 (paliers [25, 32.5, 40, 50])

#: PV COURANTS de l'attaquant, ECRITS bien SOUS son maximum (~7530 au rank 17).
#:
#: ⚠ **CE N'EST PAS UN DETAIL DE MONTAGE, C'EST CE QUI REND L'ETAGE DE MAGNITUDE MESURABLE.**
#: `StatAmount(Attacker, StatType.Health, StatPart.Maximum)` et son voisin `StatPart.Current`
#: rendent LA MEME VALEUR sur une unite a PV pleins -- MESURE : avec le montage d'origine, muter
#: `MAXIMUM` en `CURRENT` dans le port ne faisait rougir AUCUN des cinq tests. Un accord obtenu la
#: ne prouve rien sur la PART de stat lue. Blesser l'attaquant est le temoin NON NUL qui separe.
HP_BLESSE = 3000

#: Montage COMMUN. Le porteur de la mythique est une MoW : elle n'a pas de tuile, donc pas de
#: `--place`. L'attaquant et la cible, eux, sont poses cote a cote (distance hex 1).
_BASE = ["--rank", "17", "--board", BOARD,
         "--p-units", "%s,%s" % (ATTAQUANT, FIGURANT),
         "--a-units", "%s,%s" % (CIBLE, LOIN),
         "--p-mow", PORTEUR,
         "--place", "%s:3,4" % ATTAQUANT,
         "--a-place", "%s:3,5" % CIBLE,
         "--unit-stat", "%s:RemainingHealth=%d" % (ATTAQUANT, HP_BLESSE)]


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _vivante(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _attaque_normale(u):
    return next((a for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)


def _boucliers_live(snap) -> dict:
    """`combatSnapshot.units[].shields[].amount`, sommes par entite -- le canal du
    `IdunBattle.Entities.Components.ShieldComponent` natif."""
    return {int(u["entityId"]): sum(int(s.get("amount") or 0) for s in (u.get("shields") or []))
            for u in (snap.get("units") or [])}


def _boucliers_port(st) -> dict:
    """`ShieldComponent.get_total_shield()` -- MEME substrat que la feuille `CreateShield`."""
    out = {}
    for eid, e in st.entities.items():
        sc = e.get_component(ShieldComponent)
        out[int(eid)] = int(sc.get_total_shield()) if sc is not None else 0
    return out


def _par_visuel(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _mesure(rpc, build_runner, *, crit: str, rarity_attaquant: int | None,
            avec_mythique: bool = True) -> dict:
    """UN bras : build, capture PRE-coup, attaque LIVE, puis REJEU du port sur la MEME graine."""
    extra = list(_BASE) + ["--crit", crit]
    if avec_mythique:
        extra += ["--equip-mythic", "%s:%s:%d" % (PORTEUR, ABILITY, NIVEAU)]
    if rarity_attaquant is not None:
        extra += ["--unit-stat", "%s:Rarity=%d" % (ATTAQUANT, rarity_attaquant)]
    rid = build_runner("777", extra=extra, board=BOARD)["rid"]

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.fail("boardGraph indisponible -- AUCUNE mesure n'a eu lieu")
    board = Board(bg["tiles"], adjacency="native_sym")

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 300)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    att, cib = _vivante(dv, ATTAQUANT), _vivante(dv, CIBLE)
    if att is None or cib is None:
        pytest.fail("attaquant ou cible absent -- AUCUNE mesure n'a eu lieu")
    norm = _attaque_normale(att)
    if norm is None:
        pytest.fail("pas d'attaque normale sur l'attaquant -- AUCUNE mesure n'a eu lieu")

    # --- ETAT DU PORT, cale sur la MEME graine MT ------------------------------------------
    state = load_state(dv, ob, snap, board=board)
    att_off = _par_visuel(state, ATTAQUANT)
    car_off = _par_visuel(state, PORTEUR)
    if att_off is None:
        pytest.fail("attaquant absent du port -- le seed de l'etat a echoue")
    sh_avant = _boucliers_port(state)
    hp_cur = {}
    for eid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is not None:
            hp_cur[int(eid)] = hc.hp
    if sh_avant.get(int(att["id"]), 0):
        pytest.fail("MONTAGE NON SEPARANT : l'attaquant porte DEJA un bouclier ; "
                    "`AmountIsZero(CurrentShieldAmount(Attacker,3))` fermerait la pose")
    # les deux canaux dont depend le port, LUS et rendus -- une divergence doit pouvoir
    # s'attribuer au CAPTEUR plutot qu'a la mecanique.
    csc = state.get_entity(car_off).get_component(StatsComponent) if car_off is not None else None
    asc = state.get_entity(att_off).get_component(StatsComponent)
    canal = {"tertiary": getattr(getattr(csc, "ctx", None), "tertiary_ability", None),
             "tertiary_level": getattr(getattr(csc, "ctx", None), "tertiary_ability_level", None),
             "rarity_attaquant": getattr(asc.ctx, "rarity", None),
             "rarity_enum": snap.get("rarityEnum")}
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    canal["inscrites"] = sorted(type(x).__name__ for x in collect_triggered_abilities(state)
                                if getattr(x, "owner_id", None) == car_off)

    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("mt")):
        pytest.fail("dumpRng KO -- le replay-diff serait sur un flux desaligne")
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)

    # --- LE NATIF -------------------------------------------------------------------------
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att["id"], "targetId": cib["id"],
        "abilityType": norm["id"]}}, 180)
    a0 = (res.get("actions") or [{}])[0]
    if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
        pytest.fail("attaque live KO : %s" % str(res)[:200])
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 60)

    # --- LE PORT, LE MEME COUP ------------------------------------------------------------
    runner.apply(AttackUnitMessage(int(att["id"]), int(cib["id"])))

    return {"rid": rid, "attaquant": int(att["id"]), "porteur": car_off, "canal": canal,
            "live": _boucliers_live(snap2), "port": _boucliers_port(state),
            "hp_max": {int(u["entityId"]): u.get("healthMax") for u in (snap.get("units") or [])},
            # PV COURANTS **AVANT** le coup -- le temoin qui separe `StatPart.Maximum` de
            # `StatPart.Current` (cf. `HP_BLESSE`). Lus sur le `HealthComponent` du PORT, seede
            # depuis la MEME capture que `hp_max` : le nom du champ courant varie selon le canal
            # (`combatSnapshot` publie `healthMax`, pas d'homologue courant de meme nom), et
            # deviner une clef rendrait `None` -- un tri-etat qui a effectivement mordu ici.
            "hp_cur": hp_cur}


@pytest.fixture(scope="module")
def positif(rpc, build_runner):
    return _mesure(rpc, build_runner, crit="100,700", rarity_attaquant=None)


@pytest.fixture(scope="module")
def sans_crit(rpc, build_runner):
    return _mesure(rpc, build_runner, crit="0,0", rarity_attaquant=None)


@pytest.fixture(scope="module")
def sans_rarete(rpc, build_runner):
    return _mesure(rpc, build_runner, crit="100,700",
                   rarity_attaquant=int(Rarity.Legendary))


# ------------------------------------------------------------------ [1] les canaux d'entree
def test_le_montage_tertiaire_et_le_canal_de_rarete_sont_VIVANTS(positif):
    """Les deux substrats dont le port depend, LUS separement du resultat.

    Un `tertiary=None` serait un defaut de MONTAGE (la mythique n'atteint pas le porteur), un
    `rarity=None` un capteur MUET (#1039) -- deux causes qui ne se corrigent pas au meme endroit.
    Les separer ici evite d'attribuer au port ce qui vient d'en amont."""
    c = positif["canal"]
    assert c["tertiary"] == ABILITY, (
        "la mythique n'atteint pas le porteur cote port : `ctx.tertiary_ability`=%r. "
        "`--equip-mythic` ecrit `BC.Units[].TertiaryAbility` -- si c'est None, c'est le canal "
        "`unitAbilityStates` qui n'a pas parle, pas la mecanique." % (c["tertiary"],))
    assert c["rarity_attaquant"] == int(Rarity.Mythic), (
        "canal de RARETE muet ou inattendu : `ctx.rarity`=%r (attendu %d = Mythic, le "
        "`targetRarity` qu'impose `rl_duel build`). `HasRarity` rend FAUX sur None -- le port ne "
        "poserait rien, et ce serait le CAPTEUR (#1039), pas le port."
        % (c["rarity_attaquant"], int(Rarity.Mythic)))
    assert "ShieldOfFaithAbility" in c["inscrites"], (
        "`ShieldOfFaithAbility` n'est pas INSCRITE sur le porteur : %s. La voie TERTIAIRE passe "
        "par `RELIC_ABILITY_TRIGGERS` -- une entree manquante rend le port muet SANS erreur."
        % (c["inscrites"],))


# ------------------------------------------------------------------ [2] le bras POSITIF
def test_le_port_pose_LE_MEME_bouclier_que_le_natif(positif):
    """LE test. Meme montage, meme coup, meme graine : les boucliers doivent coincider EXACTEMENT.

    Le montant natif est `PercentageOf(StatAmount(Attacker, Health, Maximum), ConfigVar(shieldPct))`
    -- au palier 4, `50 % x hpMax`. On assertionne d'abord le NON-NUL : un double zero serait un
    accord VIDE, et c'est lui qui rendrait les deux contre-epreuves sans valeur."""
    r = positif
    att = r["attaquant"]
    live = r["live"].get(att, 0)
    port = r["port"].get(att, 0)
    assert live > 0, (
        "AUCUN bouclier cote NATIF : le montage est faux (mythique non montee, crit non force, "
        "ou attaquant non ami). Rien n'est conclu du port.")
    assert port == live, (
        "ECART port/natif sur le bouclier de l'attaquant u%s : natif=%s port=%s" % (att, live, port))
    # decomposition par etage : le montant DOIT etre le pourcentage des PV MAX, pas un scalaire
    # qui se trouve coincider.
    hpmax, hpcur = r["hp_max"].get(att), r["hp_cur"].get(att)
    from engine.entities.effects.magnitude import ability_var
    pct = ability_var(ABILITY, "shieldPct", NIVEAU, multiplier_pct=100)
    assert hpmax and pct, "hpMax ou shieldPct illisible -- l'etage de magnitude n'est pas mesure"
    # LE REGIME DISCRIMINANT, assertionne AVANT d'en conclure quoi que ce soit : sans PV entames,
    # `StatPart.Maximum` et `StatPart.Current` coincident et l'egalite ci-dessous ne dirait RIEN de
    # la part de stat lue (mesure : la mutation MAXIMUM->CURRENT passait alors inapercue).
    assert hpcur and hpcur < hpmax, (
        "REGIME DEGENERE : PV courants (%s) non strictement inferieurs au maximum (%s). "
        "`--unit-stat %s:RemainingHealth=%d` n'a pas mordu -- l'etage `StatPart.Maximum` n'est "
        "alors PAS mesure, et ce test passerait pour vert sans separer."
        % (hpcur, hpmax, ATTAQUANT, HP_BLESSE))
    attendu = round(hpmax * pct / 100.0)
    assert abs(live - attendu) <= 1, (
        "le montant natif (%s) ne suit pas `%s %% x hpMAX(%s)` = %s : l'etage de magnitude a "
        "change, le re-lire avant de conclure quoi que ce soit du port. (Le calcul sur les PV "
        "COURANTS donnerait %s -- c'est l'autre `StatPart`.)"
        % (live, pct, hpmax, attendu, round(hpcur * pct / 100.0)))


def test_aucune_AUTRE_entite_ne_recoit_de_bouclier(positif):
    """`CreateShield(Attacker, ...)` vise l'ATTAQUANT et lui seul. Un bouclier ailleurs voudrait
    dire que le port a resolu `Attacker` sur un autre slot (`Owner`, `Target`) -- une faute que le
    total par entite rend visible et qu'un simple `port == live` sur l'attaquant ne verrait pas."""
    r = positif
    for eid in set(r["live"]) | set(r["port"]):
        assert r["port"].get(eid, 0) == r["live"].get(eid, 0), (
            "ECART port/natif sur l'entite u%s : natif=%s port=%s -- le bouclier n'atterrit pas "
            "sur la meme unite des deux cotes." % (eid, r["live"].get(eid), r["port"].get(eid)))


# ------------------------------------------------------------------ [3] les CONTRE-EPREUVES
def test_sans_crit_aucun_bouclier_des_DEUX_cotes(sans_crit, positif):
    """`WasCrit()` exerce. `--crit 0,0` : l'attaque porte mais ne crite pas, et le vecteur
    `On(9 = Attack) & WasCrit()` ne s'ouvre pas. Le bras positif est cite pour que ce zero ne
    puisse pas etre un vert VIDE."""
    assert positif["live"].get(positif["attaquant"], 0) > 0, (
        "le bras POSITIF est nul : ce zero-ci ne prouverait rien (regime degenere)")
    att = sans_crit["attaquant"]
    assert sans_crit["live"].get(att, 0) == 0, (
        "CONTRE-EPREUVE ROUGE : le NATIF pose un bouclier sans crit (%s) -- le gate `WasCrit` "
        "n'est pas ce qu'on a lu." % sans_crit["live"].get(att))
    assert sans_crit["port"].get(att, 0) == 0, (
        "le PORT pose un bouclier sans crit (%s) : son gate `WasCrit` (`ev.is_crit`) ne mord pas."
        % sans_crit["port"].get(att))


def test_attaquant_NON_mythique_aucun_bouclier_des_DEUX_cotes(sans_rarete, positif):
    """`HasRarity(Attacker, idun.meta.Rarity.Mythic = 5)` exerce -- LE SEUL bras qui sorte du
    regime degenere (`rl_duel build` impose `targetRarity = 5`, donc partout ailleurs le gate est
    uniformement VRAI et un port qui l'oublierait serait d'accord).

    Il etablit du meme coup que `--unit-stat <vis>:Rarity=N` n'est pas MUET : la valeur atteint
    `BaseUnitComponent.Rarity` cote natif ET `UnitContext.rarity` cote port."""
    assert positif["live"].get(positif["attaquant"], 0) > 0, (
        "le bras POSITIF est nul : ce zero-ci ne prouverait rien (regime degenere)")
    att = sans_rarete["attaquant"]
    assert sans_rarete["canal"]["rarity_attaquant"] == int(Rarity.Legendary), (
        "le montage de rarete est MUET cote PORT : `ctx.rarity`=%r au lieu de %d. La "
        "contre-epreuve ne separerait alors RIEN -- ce n'est pas un vert."
        % (sans_rarete["canal"]["rarity_attaquant"], int(Rarity.Legendary)))
    assert sans_rarete["live"].get(att, 0) == 0, (
        "CONTRE-EPREUVE ROUGE : le NATIF pose un bouclier a un attaquant Legendary (%s) -- le "
        "gate `HasRarity` n'est pas ce qu'on a lu." % sans_rarete["live"].get(att))
    assert sans_rarete["port"].get(att, 0) == 0, (
        "le PORT pose un bouclier a un attaquant Legendary (%s) : son noeud `HasRarity` ne mord "
        "pas, et le regime par defaut du harnais le cachait." % sans_rarete["port"].get(att))
