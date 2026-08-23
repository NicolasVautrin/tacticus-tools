// deployment-draft — RENDRE L'ÉCRAN DE DÉPLOIEMENT NATIF UTILISABLE SUR UNE BATAILLE SANDBOX.
//
// LE FAIT MESURÉ (build `t6dpr4k06g`, décompilé) — LE SANDBOX STUBBE SON ROSTER
// -----------------------------------------------------------------------------
// Les deux corps, côte à côte :
//
//   `IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$GetUnitsForDeploymentHUD`
//       lit la progression (`this+0x20`), construit un `Nullable` depuis `this+0x70`, appelle
//       le slot d'interface `0x15` pour obtenir une liste poolée d'unités, la MAPPE, la rend.
//
//   `IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$GetUnitsForDeploymentHUD`
//       rend un conteneur poolé FRAÎCHEMENT LOUÉ, **sans lire un seul champ de `this`**.
//
// ⇒ L'écran de déploiement s'afficherait, VIDE. Ce n'est pas un défaut de notre montage : la
// source sandbox déclare le contrat et ne fournit rien. C'est le seul étage qui manque.
//
// CE QUI N'EST **PAS** UN BLOQUEUR, et il fallait le vérifier
// ------------------------------------------------------------
// `idun.Idun.Source.IdunBattle.View.Hud.UnitDeployment.UnitDeploymentHudGameModeFactory$$Create`
// ne dispatche PAS sur un enum de mode de jeu : il teste la NON-NULLITÉ de champs successifs de
// l'objet d'options (`+0x50`, `+0x30`, `+0x68`, `+0x60`, `+0x20`, `+0x28`, `+0x58`, `+0x48`,
// `+0x40`) et retombe, tous nuls, sur `UnitDeploymentHudGameModeDefault`. Or
// `SandboxGameModeSource$$GetGameModeSpecificDeploymentHudOptions` construit un
// `idun.ui.GameModeSpecificUnitDeploymentHudOptions` par défaut (il n'écrit que `+0x86 = 0`) —
// tous les champs discriminants restent nuls. **Le sandbox tombe donc sur le HUD générique, et
// il n'y a aucune branche manquante à ajouter.**
//
// LE CONTRAT, ET POURQUOI ON OBSERVE AVANT DE REMPLIR
// ----------------------------------------------------
// La méthode rend `idun.shared.collections.pools.PooledList<System.String>` — une liste d'IDS
// d'unités. Mais `classes.tsv` dit `PooledList\`1  parent=System.ValueType  isValueType=1` :
// c'est un **TYPE VALEUR**, donc le retour est une STRUCT, pas une référence. Sa disposition
// n'est pas lisible statiquement (générique ouvert, taille 0 dans la table).
//
// On ne PARIE donc pas dessus. Le module a deux régimes, et le second refuse tant que le premier
// n'a pas parlé :
//
//   OBSERVER  (défaut)  -- `onLeave` LIT le retour et rapporte ce qu'il voit (valeur brute, et le
//                          nom de classe trouvé derrière si ça pointe sur un objet géré). Écrit
//                          RIEN. C'est « un natif qui écrit s'observe d'abord », appliqué.
//   REMPLIR             -- ajoute nos ids à la liste RENDUE PAR LE STUB. On ne construit aucun
//                          conteneur : celui du stub est déjà du bon type et correctement loué —
//                          il est juste vide. La méthode `Add` est résolue AU RUNTIME sur la
//                          classe RÉELLEMENT observée, jamais sur un offset écrit ici.
//
// TROIS GARDES, toutes tirées de fautes déjà payées dans ce dépôt
// ---------------------------------------------------------------
//   * `Interceptor.attach` + écriture dans le retour, JAMAIS `Interceptor.replace` : un stop de
//     session avec un `replace` actif crashe le jeu (cf. `Ne jamais` du CLAUDE.md).
//   * on n'invoque JAMAIS `GetUnitsForDeploymentHUD` nous-mêmes — ancrer ce qu'on invoque gèle
//     le jeu, et ça a déjà coûté un gel ici (cf. `sandboxModeBcOverride`).
//   * le régime REMPLIR exige `confirmer: true` ET une observation préalable réussie.

import {
    class_get_element_class, class_get_fields, class_get_name, class_instance_size,
    class_is_valuetype, field_get_name, field_get_offset, findMethodByParamClasses,
    field_get_type, findClassAnywhere, findMethod, findMethodByParamCount, getFieldOffset,
    il2cppBase, il2cppSize, s,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { createManagedString, decodeManagedException, il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
// `listeDeTextes` est le foyer unique de la lecture d'une `List<System.String>` native (`_items`
// / `_size` résolus PAR NOM). Il rend `null` quand il n'a PAS SU LIRE — état distinct d'une liste
// vide, et c'est cette distinction que la branche guild war exploite.
import { elementsDeListe, estRefus as estRefusLecture, listeDeTextes } from "./lecture-champs.js";
// ⚠ VOIE FROIDE, ET C'EST DÉLIBÉRÉ. La vue vivante s'obtient par `FindObjectsByType`, À LA
// DEMANDE. La version précédente la publiait depuis le pump (`IdunGameViews$$Update`), donc une
// écriture JS PAR FRAME dans le hot path le plus sensible du dépôt : un coût permanent payé par
// toutes les batailles pour un besoin qui n'existe que le temps d'un RPC.
import { premiereInstance } from "./view-command.js";
// Le prêteur GUILD BOSS. Résolu dans SON module (qui porte le RE de la règle de filtrage),
// pas re-marché ici : `deployment-draft` consomme un roster, il n'a pas à connaître la chaîne
// qui mène à `GuildBossProgression`.
import { rosterPooledGuildBoss, sourceGuildBossForgee } from "./guild-boss-config.js";
import { sourceCampagneForgee } from "./campaign-source-forge.js";
import { sourceGuildWarForgee } from "./guild-war-config.js";
import { sourceOnslaughtForgee } from "./onslaught-source.js";
// Le runner VIVANT, publié par le pump — lecture seule ici.
import { state } from "../game/state.js";
// (!)PLUS AUCUN `buildAddUnitMessage` ICI (2026-08-21). Ce module ne fabrique plus d'ajout
// d'unité : la pose passe TOUJOURS par l'étage FSM (placeholder), et la substitution
// `Remove` + `Add` est supprimée. L'import est donc parti avec ses deux derniers appelants.
//
// ⚠ CE N'EST PAS `AddUnitMessage` QUI ÉTAIT LE PROBLÈME, et il ne faut pas lire ce retrait
// comme une interdiction. Ajouter une unité à un runner VIVANT est une mécanique du jeu :
// les vagues d'onslaught et les renforts de survival le font. Ce qui doublait la mise, c'était
// de l'appliquer PENDANT LA PHASE DE DÉPLOIEMENT, en parallèle des `PlaceholderUnitView` que
// le HUD compte, contre un plafond qui est le sien. Hors déploiement il n'y a aucune seconde
// comptabilité à doubler.
//
// La capacité vit toujours dans `launch.ts` (`buildAddUnitMessage`, 3 sites) et dans
// `battle-config.ts` — c'est là qu'elle a sa place, pas sur le chemin du déploiement.
// Une valeur pré-empruntée doit SURVIVRE jusqu'à sa substitution : sans racine, le GC IL2CPP
// peut la ramasser entre l'emprunt et le `retval.replace`.
import { gcRoot } from "../il2cpp/gc-root.js";
// ⚠ `s()` convertit un `char*` NATIF. Un `System.String` MANAGÉ a sa propre disposition, et
// `readIl2cppString` est le lecteur du dépôt. Mesuré : `stringAt` rendait `null` sur les
// arguments de `TryMarkUnitAsPlaced` — le verdict était bon, le NOM manquait, et un capteur
// qui rend `null` sur ce qu'il est censé identifier ne sert qu'à moitié.
import { readIl2cppString } from "../il2cpp/helpers.js";
import { pinnedAddress } from "../il2cpp/build-pin.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { pompeUiArmer, pompeUiEtat } from "../runtime/main-pump.js";
import {
    getCampaignGameModeSourcePtr, getPvpGameModeSourcePtr, getUnitProgressionPtr,
} from "./campaign-builder.js";
import { Ctx } from "../controller.js";

const NS_SRC = "IdunBattle.ViewLogic.BattleSource";
const METHODE = "GetUnitsForDeploymentHUD";

interface Refus { ok: false; error: string }
function refus(error: string): Refus { return { ok: false, error }; }

// ─────────────────────────────────────────────────────────────────────────────
// LE VERROU : AUCUNE ÉCRITURE SUR UNE BATAILLE QUI N'EST PAS LA NÔTRE
// ─────────────────────────────────────────────────────────────────────────────
//
// ⚠ CE VERROU EXISTE PARCE QU'IL A MANQUÉ, ET QUE ÇA A COÛTÉ UN JETON DE BOSS DE GUILDE.
// Mesuré le 2026-08-20 : `sandbox_boss.py` avait armé `deploymentStartArmer` pour nos montages
// sandbox. Ce relais MÉMORISE une composition et la REJOUE TOUT SEUL à l'apparition d'un écran
// de déploiement -- n'importe lequel. L'utilisateur est entré dans une VRAIE bataille de boss
// de guilde ; l'écran s'est ouvert ; le relais a posé les 5 unités de la référence par la voie
// runner-directe, sous les visuels de SON équipe (Trajann à l'écran sur l'entité `eldarFarseer`).
// Le déploiement était irrécupérable, l'essai perdu.
//
// La faute n'était pas d'avoir mal réparé ensuite : c'est qu'un relais ARMÉ pouvait écrire sur
// une partie officielle sans que personne ne l'ait demandé. Une consigne (« pense à désarmer »)
// n'arrête pas un comportement -- il faut un REFUS EXÉCUTABLE.
//
// LE DISCRIMINANT, et il est déjà employé par `sandbox-mode.ts` : la source de mode ACTIVE,
// `idun.IdunMainView._activeGameSource`, lue PAR NOM. Nos montages portent une
// `SandboxGameModeSource` ; une partie du joueur porte `GuildBossGameModeSource`,
// `CampaignGameModeSource`, `ArenaGameModeSource`...
//
// ⚠ TRI-ÉTAT : « pas su lire » REFUSE aussi. Une source non mesurée n'est pas une source sûre,
// et c'est exactement le travers qui a produit l'incident (on a lu `duJoueur=0` pour « plateau
// vide » alors que la mesure ne portait pas sur ce qu'on croyait).
// (!)LE GARDE `refusHorsSandbox` EST SUPPRIME (2026-08-21), avec sa constante et son
// helper `nomSourceActive`. Il refusait TOUTE ecriture de deploiement des que la source de
// mode active n'etait pas `SandboxGameModeSource`, et s'ouvrait par un `surBatailleReelle`
// passe coup par coup.
//
// IL A ETE ECRIT POUR UN INCIDENT DE LA VOIE COMMIT, ET CELLE-CI N'EXISTE PLUS. Ce qui avait
// coute un jeton de boss de guilde le 2026-08-20, c'est un `AddUnitMessage` applique au
// runner d'une vraie bataille, en parallele des placeholders du HUD. La pose passe desormais
// TOUJOURS par l'etage FSM -- exactement le chemin d'un clic humain, qui produit un
// `PlaceholderUnitView` que le START natif convertit. Reposer ses propres unites dans sa
// propre phase de deploiement n'est pas une ecriture dont il faut se garder.
//
// CE QUI GARDE ENCORE, ET QUI SUFFIT : `refusSiEmpilement`, qui additionne les DEUX
// comptabilites du deploiement et les confronte au plafond que le HUD a lui-meme recu. Il
// porte sur le FAIT (combien d'unites) et non sur l'IDENTITE de la source, donc il ne peut
// pas se tromper de bataille.

// ─────────────────────────────────────────────────────────────────────────────
// LE PLAFOND : ON NE PEUT PLUS EMPILER, EN SANDBOX COMME EN PARTIE RÉELLE
// ─────────────────────────────────────────────────────────────────────────────
//
// ⚠ LA CAUSE STRUCTURELLE DE L'EMPILEMENT, ET ELLE EST DÉJÀ DOCUMENTÉE PLUS BAS DANS CE FICHIER :
// il y a DEUX comptabilités du déploiement -- les `PlaceholderUnitView` que le HUD tient, et les
// unités RÉELLES du runner -- et **aucune ne nourrit l'autre**. Chaque voie de pose ne consultait
// que la sienne, donc rien n'empêchait d'ajouter par l'une ce que l'autre tenait déjà.
//
// Mesuré le 2026-08-20 : le HUD tenait les 5 placeholders de l'équipe du JOUEUR ; notre rejeu a
// appliqué 5 `AddUnitMessage` de plus au runner ; le START a ensuite converti les placeholders
// PAR-DESSUS. Résultat : **10 unités pour un plafond de 5**, et un essai de boss de guilde perdu.
//
// LE CRAN, et il ne dépend d'aucune vigilance : avant toute pose, on ADDITIONNE les deux
// comptabilités et on les confronte au plafond que le HUD a lui-même reçu
// (`UnitDeploymentHud$$Show(units, minUnitsPossible, maxUnitsPossible, options)`).
//
// ⚠ TRI-ÉTAT, ENCORE : un plafond ou une comptabilité qu'on n'a PAS SU LIRE fait REFUSER. Un
// compteur illisible rendu comme un zéro est exactement ce qui autorise l'empilement -- c'est le
// même travers que le `duJoueur=0` lu pour « plateau vide » pendant l'incident.

interface EtatDeploiement {
    reelles: number; nomsReels: Array<string | null>; cases: string[];
    placeholders: number; nomsPlaceholders: Array<string | null>;
    max: number; machines: boolean;
}

/**
 * Les `unitId` que le HUD tient en placeholders.
 *
 * ⚠ SANS EUX, LE CONTRÔLE DE DOUBLON EST AVEUGLE À LA MOITIÉ DU PLATEAU -- et c'est mesuré :
 * la re-pose d'une unité déjà présente n'a été refusée que parce que le PLAFOND était atteint.
 * Un plafond qui rattrape un doublon par accident n'est pas un contrôle de doublon.
 *
 * La taille d'élément est DÉRIVÉE (`class_instance_size` de la classe d'élément moins l'en-tête),
 * jamais recopiée — même exigence que `deploymentPlacees`. Non dérivable ⇒ `null`, qui fait
 * REFUSER en amont, jamais une liste vide qui se lirait « aucun doublon ».
 */
function nomsDesPlaceholders(lst: NativePointer, taille: number): Array<string | null> | null {
    try {
        const kl = lst.readPointer();
        const offItems = getFieldOffset(kl, "_items");
        if (offItems < 0) return null;
        const items = lst.add(offItems).readPointer();
        if (items.isNull()) return null;
        const kElem = class_get_element_class ? class_get_element_class(items.readPointer()) : null;
        if (kElem === null || class_is_valuetype === null || class_instance_size === null) {
            return null;
        }
        const octets = (class_is_valuetype(kElem) as number) !== 0
            ? (class_instance_size(kElem) as number) - 2 * Process.pointerSize
            : Process.pointerSize;
        if (!(octets > 0 && octets <= 512)) return null;
        const base = items.add(4 * Process.pointerSize);
        const out: Array<string | null> = [];
        for (let i = 0; i < Math.min(taille, 32); i++) {
            // Les 8 premiers octets de l'entrée sont le `System.String` de l'`unitId` -- relevé
            // sur les entrées vivantes, pas supposé.
            const sp = base.add(i * octets).readPointer();
            out.push(sp.isNull() ? null : readIl2cppString(sp));
        }
        return out;
    } catch { return null; }
}

/**
 * Les `unitId` des unités RÉELLES, groupés par joueur — SANS AUCUNE INVOCATION.
 *
 * ⛔ POURQUOI UNE SECONDE LECTURE PLUTÔT QUE `unitesDuPlateau()`. Celle-ci invoque deux natifs
 * (`FirstPlayerEntityIdOfHumanOnThisDevice` pour savoir qui est le joueur, `get_LogicalPosition`
 * pour la tuile). Invoquer depuis un callback d'interception GÈLE le jeu -- règle payée deux fois
 * dans ce dépôt. Or le blocage du START doit rendre son verdict DANS un `onLeave`.
 *
 * On se passe donc des deux : on ne demande pas QUI est le joueur humain (on groupe par
 * `<PlayerEntityId>` et on prendra le camp le plus chargé -- un empilement chez l'adversaire
 * serait tout aussi anormal), et on ne lit aucune tuile (le plafond n'en a pas besoin).
 *
 * `getFieldOffset` reste permis : il passe par les API de MÉTADONNÉES d'IL2CPP, pas par
 * `il2cpp_runtime_invoke` — il n'exécute aucun code managé, donc ne peut ni allouer ni prendre
 * le verrou du GC.
 *
 * Rend `null` quand la lecture n'aboutit pas : un `null` fait REFUSER en amont, jamais un zéro.
 */
function unitesReellesParJoueurSansInvoke(): Map<number, string[]> | null {
    try {
        // Même repli que `unitesDuPlateau` : la vue de la pompe quand nos capteurs n'ont pas tiré.
        const vues = vueDeDeploiement();
        if (vues === null || vues.isNull()) return null;
        const k = vues.readPointer();
        const offVues = getFieldOffset(k, "_unitViews");
        if (offVues < 0) return null;
        const dico = vues.add(offVues).readPointer();
        if (dico.isNull()) return null;
        const kd = dico.readPointer();
        const offEntries = getFieldOffset(kd, "_entries");
        const offCount = getFieldOffset(kd, "_count");
        if (offEntries < 0 || offCount < 0) return null;
        const entries = dico.add(offEntries).readPointer();
        const n = dico.add(offCount).readS32();
        if (entries.isNull() || n < 0 || n > 4096) return null;
        if (class_get_element_class === null || class_instance_size === null) return null;
        const kElem = class_get_element_class(entries.readPointer()) as NativePointer;
        const taille = (class_instance_size(kElem) as number) - Process.pointerSize * 2;
        if (!(taille > 0 && taille <= 128)) return null;
        const out = new Map<number, string[]>();
        let offJoueur = -1;
        let offUnitId = -1;
        for (let i = 0; i < n; i++) {
            const uv = entries.add(0x20 + i * taille + taille - Process.pointerSize).readPointer();
            if (uv.isNull()) continue;
            if (offJoueur < 0) {
                offJoueur = getFieldOffset(uv.readPointer(), "<PlayerEntityId>k__BackingField");
                offUnitId = getFieldOffset(uv.readPointer(), "<UnitId>k__BackingField");
                if (offJoueur < 0 || offUnitId < 0) return null;
            }
            const j = uv.add(offJoueur).readS32();
            let nom: string | null = null;
            try { nom = readIl2cppString(uv.add(offUnitId).readPointer()); } catch { nom = null; }
            const l = out.get(j) ?? [];
            if (typeof nom === "string" && nom !== "" && l.indexOf(nom) < 0) l.push(nom);
            out.set(j, l);
        }
        return out;
    } catch { return null; }
}

/** Les DEUX comptabilités + le plafond, ou un `Refus` dès qu'une lecture manque. */
function etatDuDeploiement(): EtatDeploiement | Refus {
    const u = unitesDuPlateau();
    if (!Array.isArray(u)) {
        return refus("plateau NON LISIBLE (" + u + ") -- on ne pose pas à l'aveugle : une "
            + "comptabilité illisible rendue comme un zéro est ce qui autorise l'empilement");
    }
    const miennes = u.filter((x) => x.duJoueur);
    const hud = assurerHud();
    if (hud === null) {
        return refus("aucun `UnitDeploymentHud` -- ni capté à son `Show`, ni rendu par la scène. "
            + "Le plafond de déploiement est donc INCONNU. Ce n'est PAS « pas de plafond ».");
    }
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    if (!k) return refus(`\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE sur ce build`);
    const offMax = getFieldOffset(k, "_maxUnitsPossible");
    const offMow = getFieldOffset(k, "_hasMachinesOfWar");
    const offPl = getFieldOffset(k, "_currentlyPlacedUnits");
    if (offMax < 0 || offPl < 0) {
        return refus(`champs ABSENTS de ce build : _maxUnitsPossible=${offMax} `
            + `_currentlyPlacedUnits=${offPl} -- chemin PÉRIMÉ, pas de repli sur un offset en dur`);
    }
    let placeholders: number;
    let nomsPh: Array<string | null> | null;
    try {
        const lst = hud.add(offPl).readPointer();
        if (lst.isNull()) return refus("`_currentlyPlacedUnits` est NULLE -- comptabilité du HUD "
            + "non mesurable");
        const offSize = getFieldOffset(lst.readPointer(), "_size");
        if (offSize < 0) return refus("`List._size` ABSENT -- comptabilité du HUD non mesurable");
        placeholders = lst.add(offSize).readS32();
        nomsPh = nomsDesPlaceholders(lst, placeholders);
    } catch (e) {
        return refus("`_currentlyPlacedUnits` ILLISIBLE : " + (e as Error).message);
    }
    if (nomsPh === null && placeholders > 0) {
        return refus(`les ${placeholders} placeholder(s) du HUD ne sont pas NOMMABLES -- le `
            + "contrôle de doublon serait aveugle à eux. Une liste illisible n'est pas une liste "
            + "vide.");
    }
    return {
        reelles: miennes.length,
        nomsReels: miennes.map((x) => x.unitId),
        cases: miennes.map((x) => `${x.col},${x.row}`),
        placeholders,
        nomsPlaceholders: nomsPh ?? [],
        max: hud.add(offMax).readS32(),
        machines: offMow >= 0 && hud.add(offMow).readU8() !== 0,
    };
}

/**
 * Le nombre d'unités DISTINCTES déployées, les deux comptabilités confondues.
 *
 * ⚠ NE PAS ADDITIONNER LES DEUX COMPTES -- c'est faux, et mesuré. En voie runner-directe une
 * même unité figurait DANS LES DEUX (la voie commit créait l'unité réelle, et l'entrée du HUD
 * survit) : relevé le 2026-08-20, 5 unités réelles pour 6 entrées de `_currentlyPlacedUnits`,
 * soit une somme de 11 pour un plafond de 6. Le plafond aurait refusé des poses LÉGITIMES.
 * L'invariant porte sur les unités DISTINCTES, donc sur l'UNION par `unitId`.
 */
function unitesDistinctes(e: EtatDeploiement): string[] {
    const vus: string[] = [];
    for (const n of e.nomsReels.concat(e.nomsPlaceholders)) {
        if (typeof n === "string" && n !== "" && vus.indexOf(n) < 0) vus.push(n);
    }
    return vus;
}

/**
 * Rend un `Refus` quand la pose EMPILERAIT, ou `null` quand elle est légitime.
 *
 * `p === null` ⇒ on ne vérifie que le plafond (c'est le cas du START, qui ne pose rien lui-même
 * mais convertit tout ce qui traîne).
 *
 * ⚠ IL N'Y A PAS D'ÉCHAPPATOIRE ICI, ET C'EST DÉLIBÉRÉ. C'est même le SEUL garde qui reste
 * depuis le retrait de `refusHorsSandbox` (2026-08-21), et il tient parce qu'il porte sur le
 * FAIT -- combien d'unités le déploiement totalise -- et non sur l'IDENTITÉ de la source. Il ne
 * peut donc pas se tromper de bataille, ni refuser un geste légitime parce qu'il n'a pas su
 * reconnaître le mode. Aucun empilement n'est légitime : on vide d'abord
 * (`deploymentRetirer` / le clear du rejeu), on ne force pas.
 */
function refusSiEmpilement(p: Pose | null, quoi: string): Refus | null {
    const e = etatDuDeploiement();
    if ("ok" in e) return refus(`REFUS (${quoi}) : ${e.error}`);
    const total = unitesDistinctes(e).length;
    // Le plafond porte sur les unités STANDARD ; une machine de guerre s'y ajoute quand le mode
    // en autorise une. On ne cherche pas à démêler laquelle est laquelle dans les deux listes :
    // la borne haute suffit à interdire l'empilement, et elle ne peut pas refuser à tort une
    // composition légitime.
    const borne = e.max + (e.machines ? 1 : 0);
    if (p !== null) {
        // ⚠ LES DEUX COMPTABILITÉS, pas seulement les unités réelles. Mesuré le 2026-08-20 : avec
        // le seul contrôle sur les réelles, une re-pose n'était refusée que parce que le PLAFOND
        // était atteint -- donc par accident, et donc pas du tout dès qu'il reste une place.
        if (e.nomsReels.indexOf(p.unitId) >= 0) {
            return refus(`REFUS (${quoi}) : \`${p.unitId}\` est DÉJÀ une unité réelle du plateau `
                + "-- la poser une seconde fois la dédoublerait.");
        }
        if (e.nomsPlaceholders.indexOf(p.unitId) >= 0) {
            return refus(`REFUS (${quoi}) : \`${p.unitId}\` est DÉJÀ un placeholder du HUD -- la `
                + "poser créerait le doublon HUD/runner qui a produit les 10 unités du "
                + "2026-08-20.");
        }
        if (e.cases.indexOf(`${p.col},${p.row}`) >= 0) {
            return refus(`REFUS (${quoi}) : la case (${p.col},${p.row}) est DÉJÀ occupée par une `
                + "unité réelle. Une pose sur case occupée échoue EN SILENCE côté natif.");
        }
        if (total >= borne) {
            return refus(`REFUS (${quoi}) : le déploiement est PLEIN -- ${total} unité(s) `
                + `DISTINCTE(S) (${e.reelles} réelle(s), ${e.placeholders} placeholder(s), `
                + `union par unitId), plafond ${borne} (max ${e.max}`
                + `${e.machines ? " + 1 machine" : ""}). Poser de plus EMPILERAIT : c'est ainsi `
                + "qu'un essai de boss de guilde s'est retrouvé à 10 unités pour 5. Vider "
                + "d'abord (`deploymentRetirer`) -- il n'y a pas d'échappatoire à ce refus-ci.");
        }
        return null;
    }
    if (total > borne) {
        return refus(`REFUS (${quoi}) : le plateau porte DÉJÀ ${total} unité(s) DISTINCTE(S) `
            + `(${e.reelles} réelle(s), ${e.placeholders} placeholder(s), union par unitId) pour `
            + `un plafond de ${borne}. Démarrer convertirait les placeholders PAR-DESSUS les `
            + "unités réelles -- exactement le doublement mesuré le 2026-08-20.");
    }
    return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// LE BLOCAGE DU START A ETE SUPPRIME (2026-08-21) -- LE HUD FAIT DEJA CE CONTROLE
// ─────────────────────────────────────────────────────────────────────────────
//
// `deploymentBlocageStart` s'attachait a
// `IdunBattle.View.FSM.VisualBattleQuery$$IsMinUnitAmountToBringToStartBattleReached` et
// reecrivait son retour a `false` sur empilement avere. Il n'AJOUTAIT donc pas un controle :
// il FALSIFIAIT celui du jeu.
//
// (!)IL GARDAIT UNE CAUSE QUI N'EXISTE PLUS. Le 10-pour-5 du 2026-08-20 n'etait pas une
// defaillance du HUD : c'est la voie COMMIT qui appliquait des `AddUnitMessage` DROIT AU
// RUNNER, invisibles de lui. Le HUD comptait ses 5 placeholders et affichait `5/5` en toute
// bonne foi (mesure de l'epoque : bouton a `0/5` avec cinq unites en jeu, et
// `GetPlaceholderUnitViews` ne rendant qu'UN element). Depuis la suppression de cette voie,
// toute pose passe par l'etage FSM, donc par le HUD, donc dans le compte qu'il tient : son
// controle est redevenu exhaustif.
//
// (!)ET LE PLAFOND HAUT EST DEJA GARDE PAR LE HUD, A LA POSE -- mesure du 2026-08-20 qui a
// motive `deploymentPlafondArmer` : en sandbox le HUD recevait `maxUnitsPossible: 0`, et un
// plafond a zero N'AUTORISE AUCUNE POSE. S'il ne gardait pas le max au moment de poser, un
// zero n'aurait rien empeche.
//
// (!)UN DOUBLON QUI RE-IMPLEMENTE LE COMPTAGE SE TROMPE -- et celui-ci s'etait DEJA trompe :
// sa premiere version unionnait nos placeholders avec le camp ENNEMI (3 noms PNJ + 6
// placeholders = 9 pour une borne de 6) et a BLOQUE UN START LEGITIME. Un garde redondant qui
// produit un faux positif ne coute pas zero : il coute le refus de ce que le jeu accepte.
//
// CE QUI RESTE, ET QUI SUFFIT : `refusSiEmpilement`, en amont, a la POSE. Reste un seul chemin
// qui contourne le HUD -- le RPC de substitution d'unite (`RemoveUnitMessage` puis
// `AddUnitMessage` sur le runner vivant), explicite et garde par `confirmer: true`. S'il faut
// le border, ca se fait A SON SITE, pas par un garde global sur le START.

/** Ce que `onLeave` a VU au dernier passage — la seule base sur laquelle REMPLIR est autorisé. */
interface Observation {
    brut: string;            // le retour, en hexa
    pointeur: boolean;       // ressemble-t-il à un pointeur exploitable ?
    classe: string | null;   // nom de classe lu derrière, si lisible
    erreur: string | null;   // ce qui a empêché de lire (jamais un silence)
}

let listener: InvocationListener | null = null;
let observations: Observation[] = [];
let fires = 0;

/** Les ids à injecter. `null` = TRANSPARENT (le hook observe et ne touche à rien). */
let unites: string[] | null = null;
let dernierRemplissage: { ajoutes: number; erreur: string | null } | null = null;

/** Le roster guild war, en CHAÎNES JS. Lu une seule fois, puis re-posé à chaque tir.
 *
 *  ⚠ C'est ce cache qui empêche un objet mis en pool de traverser la frontière : on emprunte
 *  UNE fois pour lire, jamais pour substituer (cf. la branche `guildWar` de la délégation, et
 *  l'exception `BeforeReturnToPoolAttempt` qu'elle a coûtée). Remis à `null` à chaque
 *  (dés)armement du prêteur, pour qu'un remontage relise plutôt que de servir un roster périmé. */
let idsGuildWar: string[] | null = null;

/** Le roster ONSLAUGHT, même forme et pour les mêmes raisons.
 *
 *  ⚠ IL LUI FAUT SA PROPRE CASE, et pas seulement une branche : le cache est ce qui garde
 *  l'emprunt à UN SEUL par montage. Le partager avec la guerre de guilde ferait servir le roster
 *  de l'autre mode après un changement de prêteur -- silencieusement, et avec un roster qui a
 *  l'air parfaitement valide. */
let idsOnslaught: string[] | null = null;

/** Le roster CAMPAGNE, même forme et pour les mêmes raisons — cf. la branche `campagne`. */
let idsCampagne: string[] | null = null;

/** Les ancrages sur les DEUX bornes de `VisualBattleQuery` (cf. `deploymentBornesArmer`). */
const listenerBornes: InvocationListener[] = [];
/** Ce que chaque borne a rendu NATIVEMENT et ce qu'on a substitué. Les deux, toujours : sans le
 *  natif à côté, on ne peut pas dire si la substitution a changé quoi que ce soit. */
const derniersBornes: Record<string,
    { natif: number; substitue: number | null; detail: string }> = {};

/** Le cache du prêteur `nom`, en LECTURE et en ÉCRITURE — un seul foyer pour les deux modes
 *  dont le roster est un `PooledList` à 0 paramètre (`guildWar`, `onslaught`). */
function cacheRoster(nom: Preteur): string[] | null {
    return nom === "onslaught" ? idsOnslaught : idsGuildWar;
}
function poserCacheRoster(nom: Preteur, v: string[] | null): void {
    if (nom === "onslaught") { idsOnslaught = v; } else { idsGuildWar = v; }
}

/**
 * D'un `PooledListElement<T>` aux CHAÎNES qu'il porte. LÈVE si la forme n'est pas celle attendue —
 * un roster illisible doit se DIRE, jamais se rabattre sur une liste vide qui se lirait comme
 * « ce mode n'a pas d'unités ».
 *
 * ⚠ `_object` est résolu PAR SON NOM (`getFieldOffset` remonte la chaîne de parents : le champ est
 * déclaré par `PooledElement\`1`), jamais par un offset écrit ici.
 */
function idsDePooledElement(el: NativePointer): string[] {
    if (el.isNull()) throw new Error("`_listWithStatus` NUL");
    const off = getFieldOffset(el.readPointer(), "_object");
    if (off <= 0) throw new Error("`_object` non résolu sur le wrapper de pool");
    const interne = el.add(off).readPointer();
    if (interne.isNull()) throw new Error("`_object` NUL");
    const ids = listeDeTextes(interne);
    if (ids === null) throw new Error("`List<String>` illisible");
    return ids;
}

/** Lit prudemment le nom de classe derrière un pointeur candidat. Ne lève jamais. */
function classeDerriere(p: NativePointer): { classe: string | null; erreur: string | null } {
    try {
        if (p.isNull()) return { classe: null, erreur: "retour NUL" };
        const klass = p.readPointer();
        if (klass.isNull()) return { classe: null, erreur: "slot de classe NUL" };
        // `il2cpp_class_get_name` rend un `char*`, JAMAIS une chaîne JS -- `s()` est le
        // convertisseur du dépôt. L'oublier rend un `[object Object]` qui se lit comme un nom.
        const nom = s(class_get_name(klass) as NativePointer);
        return { classe: nom || null, erreur: nom ? null : "class_get_name muet" };
    } catch (e) {
        return { classe: null, erreur: "lecture refusée : " + (e as Error).message };
    }
}

/**
 * Ajoute nos ids à la liste rendue par le stub. `Add` résolu au RUNTIME sur la classe vue.
 *
 * ⚠ LE RETOUR EST UN **WRAPPER DE POOL**, PAS LA LISTE — mesuré le 2026-08-17, et c'est le
 * refus de la première version qui l'a établi : `Add` (1 param) est INTROUVABLE sur
 * `PooledListElement\`1`. `classFields` sur la classe VIVANTE donne la forme réelle :
 *
 *     Empty                       PooledListElement`1   (statique)
 *     _object                     List`1                <- LE CONTENEUR, hérité de `PooledElement\`1`
 *     <IsPooled>k__BackingField   Boolean
 *
 * On descend donc d'un cran quand `Add` manque au premier niveau — et le champ est résolu
 * **PAR SON NOM** (`getFieldOffset`, qui remonte la chaîne de parents : `_object` est déclaré
 * par le parent), jamais par un offset écrit ici. La voie empruntée est PUBLIÉE : « ça a marché »
 * ne doit pas cacher « par où ».
 */
function remplir(retour: NativePointer, source?: string[] | null): {
    ajoutes: number; erreur: string | null; voie?: string;
} {
    const { classe, erreur } = classeDerriere(retour);
    if (classe === null) {
        return { ajoutes: 0, erreur: erreur ?? "classe du retour non identifiée" };
    }

    // Niveau 0 : le retour lui-même porte-t-il `Add` ?
    let cible = retour;
    let voie = classe;
    let miAdd = findMethodByParamCount(retour.readPointer(), "Add", 1);

    // Niveau 1 : sinon, descendre dans `_object` (le conteneur du wrapper de pool).
    if (!miAdd) {
        let off: number;
        try {
            off = getFieldOffset(retour.readPointer(), "_object");
        } catch (e) {
            return { ajoutes: 0, erreur: `\`Add\` absent de \`${classe}\` et champ \`_object\` `
                + "non résolu : " + (e as Error).message };
        }
        if (off <= 0) {
            return { ajoutes: 0, erreur: `\`Add\` absent de \`${classe}\`, et \`_object\` n'a pas `
                + "d'offset exploitable -- NE RIEN ÉCRIRE" };
        }
        const interne = retour.add(off).readPointer();
        if (interne.isNull()) {
            return { ajoutes: 0, erreur: `\`${classe}._object\` est NUL -- le wrapper de pool ne `
                + "porte aucune liste ; NE RIEN ÉCRIRE" };
        }
        const nomInterne = classeDerriere(interne).classe;
        miAdd = findMethodByParamCount(interne.readPointer(), "Add", 1);
        if (!miAdd) {
            return { ajoutes: 0, erreur: `\`Add\` (1 param) introuvable sur \`${classe}\` NI sur `
                + `son \`_object\` (\`${nomInterne ?? "?"}\`) -- NE RIEN ÉCRIRE` };
        }
        cible = interne;
        voie = `${classe}._object -> ${nomInterne ?? "?"}`;
    }

    let n = 0;
    for (const id of (source ?? unites) ?? []) {
        try {
            invokeMethod(miAdd.info, cible, [createManagedString(id)]);
            n++;
        } catch (e) {
            return { ajoutes: n, voie, erreur: `\`Add("${id}")\` a levé : ` + (e as Error).message };
        }
    }
    return { ajoutes: n, erreur: null, voie };
}

function armer(): true | Refus {
    if (listener) return true;
    const k = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
    if (!k) return refus(`${NS_SRC}.SandboxGameModeSource INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(k, METHODE, 0);
    if (!mi) return refus(`\`SandboxGameModeSource$$${METHODE}\` INTROUVABLE (0 param)`);
    listener = Interceptor.attach(mi.ptr, {
        onLeave(retval) {
            fires++;
            const p = retval as unknown as NativePointer;
            const { classe, erreur } = classeDerriere(p);
            if (observations.length < 8) {
                observations.push({ brut: p.toString(), pointeur: !p.isNull(), classe, erreur });
            }
            // TRANSPARENT tant qu'aucun id n'est posé : le régime par défaut n'écrit RIEN.
            if (unites && unites.length) dernierRemplissage = remplir(p);
        },
    });
    Interceptor.flush();
    return true;
}

// ============================================================================
// PHASE DE DÉPLOIEMENT (#10020-r1) — forcer une sandbox à passer par l'écran de
// déploiement au lieu de sauter directement en `Running`.
//
// LA CHAÎNE, mesurée le 2026-08-17 (`t6dpr4k06g`), décompilée puis confrontée sur les objets
// VIVANTS (cf. `docs/rl/case-10020-lien-vue-source-sens-unique.md` §7-§8) :
//
//   IdunBattle.View.Game.IdunGameViews$$Enable(this, skipUnitDeployment)
//       si skipUnitDeployment == 0 ET <slot 0x34>(this+0x138 = _visualBattleQuery) :
//              -> IdunBattle.View.FSM.UnitSelectionFsm$$UnitDeployment       (PHASE DE DEPLOIEMENT)
//       sinon  -> IdunBattle.View.FSM.UnitSelectionFsm$$StartMatch           (direct en jeu)
//
//   IdunBattle.View.FSM.VisualBattleQuery$$ShouldShowUnitDeploymentHud  =  relais PUR vers
//       <slot 0x29>(this+0x80 = _gameModeSource : IGameModeSource)
//
// Sur une sandbox les DEUX rendent `false` (invoqués sur les objets vivants), et le corps de
// `SandboxGameModeSource$$ShouldShowUnitDeployment` est un `return 0` **CONSTANT** : aucun réglage
// de BC ni de gameconfig ne le fera basculer. D'où ce hook.
//
// ⛔ POURQUOI ON N'ANCRE PAS LA SOURCE, ET POURQUOI C'EST LE POINT CENTRAL DE CE MODULE
// -------------------------------------------------------------------------------------
// `SandboxGameModeSource$$ShouldShowUnitDeployment` résout au runtime sur un corps que **~745
// `MethodInfo` PARTAGENT** (745 xrefs DATA + 122 appels directs ; Ghidra le nomme d'après une
// classe sans rapport, `Stash.Native.StashNative$$get_IsPurchaseProcessing`). IL2CPP déduplique les
// corps triviaux : `return 0` n'a pas d'identité. S'y attacher basculerait à `true` TOUT ce qui rend
// « faux constant » dans le jeu — sans erreur, sans symptôme qui désigne la cause.
//
// Le dépôt portait déjà « l'absence dans la table ne prouve RIEN » : c'était le versant LECTURE.
// Ici c'est le versant ÉCRITURE, et il ne rate pas une conclusion — il fait un dégât.
//
// ⇒ On ancre le RELAIS, un étage au-dessus : il a un VRAI corps, donc une adresse propre
// (2 xrefs DATA : son `MethodInfo` + son entrée de vtable).
//
// ET LE GARDE EST EXÉCUTABLE, PAS ÉCRIT — une prose n'arrête pas un comportement. `teteTriviale()`
// lit les premiers octets du corps résolu et REFUSE l'attache si un `ret` (0xC3) tombe dans les 8
// premiers : un corps qui rend une constante rette en 1 à 4 octets, un relais réel commence par sa
// garde de cctor et son test de nullité. Le refus PUBLIE les octets, pour qu'on juge sur pièce et
// pas sur un verdict.
//
// RÉGIMES — `forcer` est FAUX par défaut, donc armer n'écrit RIEN.
//   OBSERVER : on lit le `skipUnitDeployment` que le jeu passe à `Enable`, et ce que le relais rend.
//              C'est la seule base sur laquelle on saura si forcer a un sens.
//   FORCER   : `onLeave` remplace le retour du relais par `true`. `Interceptor.attach`, JAMAIS
//              `replace` (un stop de session avec un `replace` actif crashe le jeu).
//
// ⚠ `VisualBattleQuery` sert TOUS les modes, pas seulement la sandbox : forcer sans désarmer ferait
// apparaître une phase de déploiement là où le jeu n'en veut pas. D'où l'armement explicite.

const NS_VBQ = "IdunBattle.View.FSM";
const CLS_VBQ = "VisualBattleQuery";
const METH_VBQ = "ShouldShowUnitDeploymentHud";
const NS_VIEWS = "IdunBattle.View.Game";
const CLS_VIEWS = "IdunGameViews";

/** Octets lus en tête de corps pour le garde de trivialité. */
const OCTETS_TETE = 8;

interface Tete {
    hex: string | null;
    /** Index du premier `ret` (0xC3) dans la tête, ou `null` s'il n'y en a pas. */
    retA: number | null;
    erreur: string | null;
}

/** Lit la tête du corps. Ne lève jamais — un refus de lecture est un refus, pas un silence. */
function lireTete(p: NativePointer): Tete {
    try {
        const buf = p.readByteArray(OCTETS_TETE);
        if (!buf) return { hex: null, retA: null, erreur: "lecture vide" };
        const o = new Uint8Array(buf);
        let retA: number | null = null;
        for (let i = 0; i < o.length; i++) {
            if (o[i] === 0xc3) { retA = i; break; }
        }
        const hex = Array.from(o).map((b) => b.toString(16).padStart(2, "0")).join(" ");
        return { hex, retA, erreur: null };
    } catch (e) {
        return { hex: null, retA: null, erreur: "lecture refusée : " + (e as Error).message };
    }
}

/**
 * Le corps ressemble-t-il à une constante dédupliquée ? Voir l'en-tête.
 *
 * ⚠ UN SAUT N'EST PAS UN CORPS TRIVIAL, ET LES CONFONDRE A COÛTÉ UN CAPTEUR ENTIER, EN SILENCE.
 * `lireTete` cherche un `0xc3` N'IMPORTE OÙ dans les huit premiers octets — il ne décode rien.
 * Sur un THUNK (`e9 <rel32>`), le premier octet du DÉPLACEMENT peut valoir `0xc3` et se lit
 * alors comme un `ret`. Mesuré le 2026-08-19 sur
 * `IdunBattle.View.Game.IdunGameViews$$Enable`, dont la tête est `e9 c3 db a1 ff 48 89 4c` :
 * le garde annonçait « corps TRIVIAL, ret à l'octet 1 », l'ancrage était refusé, `vuesJeu`
 * restait NUL — et la MoW n'était donc jamais reposée au retry, sans qu'aucun message ne
 * nomme la cause.
 *
 * Un corps trivial dédupliqué commence par `b8 <imm32> c3`, `33 c0 c3`, `31 c0 c3` ou `c3` nu :
 * JAMAIS par un saut. Écarter les têtes de saut ne relâche donc rien du garde — ça lui retire
 * un faux positif.
 */
function teteTriviale(t: Tete): boolean {
    if (t.hex === null) return false;
    const premier = parseInt(t.hex.slice(0, 2), 16);
    // `e9` = jmp rel32, `eb` = jmp rel8 : une trampoline, pas une constante.
    if (premier === 0xe9 || premier === 0xeb) return false;
    return t.retA !== null;
}

let relaisListener: InvocationListener | null = null;
let enableListener: InvocationListener | null = null;

/** `false` = OBSERVER (aucune écriture). `true` = le relais rendra `true`. */
let forcerPhase = false;

let relaisFires = 0;
let relaisForces = 0;
/** Ce que le relais a rendu AVANT toute substitution — la mesure, pas notre effet. */
const relaisRetours: number[] = [];
/** Le `skipUnitDeployment` que le jeu passe à `Enable`, tel quel. */
const enableObservations: Array<{ skip: number }> = [];

/** Ce que l'armement a établi sur les deux corps — publié, jamais résumé en booléen. */
let ancrage: {
    relais: { ghidraVA: string; tete: Tete } | null;
    enable: { ghidraVA: string; tete: Tete } | null;
} = { relais: null, enable: null };

function ghidraVA(p: NativePointer): string {
    return ptr("0x180000000").add(p.sub(il2cppBase)).toString();
}

/**
 * UNE PILE ENTRANTE, RENDUE EN ADRESSES GHIDRA — pour NOMMER l'appelant au lieu de le deviner.
 *
 * ⚠ POURQUOI PAS `DebugSymbol.fromAddress`. Mesuré le 2026-08-20 : sur ce binaire il rend
 * l'export le plus proche, donc `mono_type_size` pour absolument tout le code de jeu — un
 * backtrace de 16 frames où 15 portent le même nom faux. Ces frames ne sont pas anonymes, elles
 * sont MAL nommées, ce qui est pire : on lit un nom et on le croit. La conversion vers l'espace
 * Ghidra, elle, est exacte, et `data/symbols/<build>/ghidra/functions.tsv` fait le reste hors
 * ligne (`ghidra_symbols.py whereis`).
 *
 * Les frames HORS de l'image du jeu sont rendues telles quelles, avec leur module : elles sont
 * généralement du runtime ou de l'agent Frida lui-même, et les faire passer par `ghidraVA`
 * fabriquerait une adresse qui ne désigne rien.
 */
function pileGhidra(ctx: CpuContext, max = 20): Array<Record<string, unknown>> {
    const out: Array<Record<string, unknown>> = [];
    let frames: NativePointer[] = [];
    try { frames = Thread.backtrace(ctx, Backtracer.ACCURATE); }
    catch { try { frames = Thread.backtrace(ctx, Backtracer.FUZZY); } catch { return out; } }
    for (const a of frames.slice(0, max)) {
        const delta = a.sub(il2cppBase);
        const dans = delta.compare(ptr(0)) >= 0 && delta.compare(ptr(il2cppSize)) < 0;
        if (dans) { out.push({ ghidraVA: ghidraVA(a) }); continue; }
        let mod: string | null = null;
        try { mod = Process.findModuleByAddress(a)?.name ?? null; } catch { /* best effort */ }
        out.push({ brut: a.toString(), module: mod, horsImage: true });
    }
    return out;
}

/**
 * LA MÊME PILE, EN RÉGIME FROID — aucune API Frida qui touche au processus.
 *
 * ⛔ CE VARIANT EXISTE PARCE QUE L'AUTRE A TUÉ LE JEU. Mesuré le 2026-08-20, minidump à l'appui
 * (`Tacticus.exe.26196.dmp`, 02:09:20) : un `Interceptor.attach` sur `FUN_180201a80` — le fond
 * commun de TOUS les jets IL2CPP — dont le `onEnter` appelait `decodeManagedException` (qui
 * ré-entre dans `il2cpp_class_get_name`) et `Process.findModuleByAddress`. On ré-entre donc dans
 * le runtime PENDANT qu'il déroule une exception. Le jeu est mort au premier tir.
 *
 * Sur un chemin de jet, on ne fait QUE des lectures mémoire et de l'arithmétique. Résoudre les
 * noms est le travail du LECTEUR du RPC, dans un contexte sain — et c'est possible parce qu'un
 * `Il2CppClass*` est permanent, là où l'objet exception, lui, peut avoir été ramassé.
 */
function pileGhidraFroide(ctx: CpuContext, max = 16): string[] {
    const out: string[] = [];
    let frames: NativePointer[] = [];
    try { frames = Thread.backtrace(ctx, Backtracer.FUZZY); } catch { return out; }
    for (const a of frames.slice(0, max)) {
        const delta = a.sub(il2cppBase);
        const dans = delta.compare(ptr(0)) >= 0 && delta.compare(ptr(il2cppSize)) < 0;
        out.push(dans ? ghidraVA(a) : "hors-image:" + a.toString());
    }
    return out;
}

function armerPhase(): true | Refus {
    if (relaisListener) return true;

    const kv = findClassAnywhere(NS_VBQ, CLS_VBQ);
    if (!kv) return refus(`${NS_VBQ}.${CLS_VBQ} INTROUVABLE sur ce build`);
    const mv = findMethodByParamCount(kv, METH_VBQ, 0);
    if (!mv) return refus(`\`${CLS_VBQ}$$${METH_VBQ}\` INTROUVABLE (0 param)`);

    // LE GARDE. Il vaut pour le relais comme pour n'importe quelle cible future : si le corps
    // résolu rend une constante, il est probablement PARTAGÉ, et s'y attacher est un dégât de
    // masse. On refuse en publiant les octets.
    const teteV = lireTete(mv.ptr);
    if (teteV.erreur !== null) {
        return refus(`tête du corps de \`${METH_VBQ}\` ILLISIBLE (${teteV.erreur}) -- `
            + "on ne s'attache pas à un corps qu'on n'a pas pu qualifier");
    }
    if (teteTriviale(teteV)) {
        return refus(`REFUS : \`${CLS_VBQ}$$${METH_VBQ}\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${teteV.retA} ; tête = ${teteV.hex}). IL2CPP déduplique ces corps, `
            + "donc l'adresse est PARTAGÉE par N méthodes et s'y attacher les basculerait TOUTES. "
            + "Ancrer un appelant qui a un vrai corps. Cf. case-10020 §8.");
    }

    const kg = findClassAnywhere(NS_VIEWS, CLS_VIEWS);
    const mg = kg ? findMethodByParamCount(kg, "Enable", 1) : null;
    const teteG = mg ? lireTete(mg.ptr) : null;

    relaisListener = Interceptor.attach(mv.ptr, {
        onLeave(retval) {
            relaisFires++;
            // Le retour est un Boolean IL2CPP : la valeur utile est dans AL, d'où le masque.
            const brut = retval.toInt32() & 0xff;
            if (relaisRetours.length < 32) relaisRetours.push(brut);
            if (forcerPhase && brut === 0) {
                retval.replace(ptr(1));
                relaisForces++;
            }
        },
    });

    // `Enable` reste en OBSERVATION PURE, toujours : c'est lui qui dit si le drapeau
    // `skipUnitDeployment` court-circuite le prédicat, auquel cas forcer le relais ne servirait
    // à rien. Sans cette lecture, un forçage sans effet serait indiscernable d'un forçage raté.
    if (mg && teteG && teteG.erreur === null && !teteTriviale(teteG)) {
        enableListener = Interceptor.attach(mg.ptr, {
            onEnter(args) {
                // L'instance vivante d'`IdunGameViews`, captée au passage : c'est elle qui
                // reposera la MoW au rejeu (`AddPlaceholderMachine`). Coût nul, aucun scan.
                try { if (!args[0].isNull()) vuesJeu = args[0]; } catch { /* avale */ }
                if (enableObservations.length < 32) {
                    enableObservations.push({ skip: args[1].toInt32() & 0xff });
                }
            },
        });
    }

    Interceptor.flush();
    ancrage = {
        relais: { ghidraVA: ghidraVA(mv.ptr), tete: teteV },
        enable: mg && teteG ? { ghidraVA: ghidraVA(mg.ptr), tete: teteG } : null,
    };
    return true;
}

// ============================================================================
// MIRROR DE `GetUnlockedUnitsPooled` (#10020-r1) — LE SECOND STUB, celui qui bloque LA POSE.
//
// LES SIX MÉTHODES DE LA SOURCE ONT **DEUX RÔLES**, et les confondre coûte cher (mesuré) :
//
//   GetUnitsForDeploymentHUD   -> l'AFFICHAGE   (rempli plus haut ; le roster apparaît)
//   GetUnlockedUnitsPooled     -> le MODÈLE     (`UnitDeploymentHud._allUnlockedUnitModels`)
//
// C'est le SECOND que consulte le garde `TryGetValue` de
// `idun.ui.UnitDeploymentHud$$TryMarkUnitAsPlaced`. Sur la sandbox il rend un dictionnaire
// **fraîchement loué** (`DictionaryPooler<K,V>.Get()`, aucun champ de `this` lu), donc vide, donc
// **toute pose est refusée quel que soit l'affichage**. Remplir le premier ne peut pas débloquer
// le second — deux heures de sondage du HUD ne l'auraient pas dit, il fallait lire le corps.
//
// POURQUOI ON N'A PAS RÉIMPLÉMENTÉ LE CORPS CAMPAGNE, ET C'EST UNE MESURE, PAS UN CONFORT
// ----------------------------------------------------------------------------------------
//   `CampaignGameModeSource$$GetUnlockedUnitsPooled(this)` lit `this+0x20` (unitProgression) ET
//   `this+0x70`, puis `<slot 0x15>(Nullable(this+0x70), 1)` suivi d'un `.Map(converter)`.
//   Or `SandboxGameModeSource` fait **0x58 octets** (`classes.tsv`) : il **N'A PAS de `+0x70`**.
//   Rejouer ce corps sur un `this` sandbox lirait HORS DES BORNES de l'objet.
//
// ⇒ On EMPRUNTE le résultat à la source CAMPAGNE VIVANTE, capturée par l'amorce
// (`getCampaignGameModeSourcePtr`). Même compte, même progression, et c'est SA méthode qui
// construit le dictionnaire — on n'en fabrique aucun. Le mirror est un emprunt, pas une copie.
//
// ⚠ CE QUE CET EMPRUNT NE GARANTIT PAS, et il faut le dire : le `+0x70` de la campagne participe
// à la requête (vraisemblablement un type/palier de campagne). Le dictionnaire obtenu est donc
// « les unités débloquées SELON LA CAMPAGNE », pas « selon la sandbox ». Tant qu'aucune mesure ne
// compare les deux, ce module ne prétend pas à l'équivalence — il rend un dictionnaire NON VIDE
// et publie sa provenance.
//
// GARDES — les mêmes que pour la phase, et pour la même raison :
//   * refus si le corps résolu est TRIVIAL (`ret` dans les 8 premiers octets) ⇒ corps dédupliqué,
//     donc adresse PARTAGÉE (cf. les 745 xrefs du §8) ;
//   * refus si aucune source campagne n'est capturée — on ne fabrique pas un dictionnaire vide
//     pour faire joli, on DIT qu'on ne peut pas ;
//   * `Interceptor.attach` + substitution du retour, JAMAIS `replace`.

const CLS_CAMP = "CampaignGameModeSource";
const CLS_SANDBOX = "SandboxGameModeSource";

/**
 * LA TABLE DE DÉLÉGATION — ce que la sandbox n'est pas capable de répondre, et qu'on va lui faire
 * demander à une VRAIE source.
 *
 * Chaque entrée est une méthode d'`IGameModeSource` que la couche déploiement interroge et que
 * `SandboxGameModeSource` STUBBE. `params` est vérifié à la résolution (arité), jamais supposé.
 *
 * ⚠ L'ORDRE N'EST PAS ARBITRAIRE : `GetUnitModel` est celui qui commande la POSE (il décide si le
 * modèle est un `HotseatUnitModel` ou un modèle de compte, donc si `IsUnlocked` passe) ;
 * `GetGameModeSpecificDeploymentHudOptions` est celui qui apporte les RESTRICTIONS (faction,
 * unité obligatoire, objectifs) — sans lui le déploiement reste permissif, ce qui n'est PAS le
 * déploiement du jeu.
 */
/**
 * ⚠ `valeurs` — QUELS PARAMÈTRES SONT DES TYPES VALEUR, et pourquoi ça ne s'improvise pas.
 *
 * `il2cpp_runtime_invoke` attend, pour un type VALEUR, un POINTEUR vers la valeur. Les
 * arguments interceptés, eux, arrivent bruts : un `System.Boolean` `false` est le mot `0`.
 * Le retransmettre tel quel revient à passer `0x0` comme adresse.
 *
 * MESURÉ le 2026-08-17 : `GetUnitModel(unitId, isPvpEnemyUnit)` -- seule entrée de cette table
 * à porter un paramètre -- a levé « access violation accessing 0x0 » sur ses 101 appels, soit
 * exactement l'adresse `false`. Les trois autres n'ont AUCUN paramètre : elles fonctionnaient
 * par chance de forme, pas parce que le transfert était correct.
 */
/** Les méthodes dont le RETOUR est un `System.Int32` — donc un TYPE VALEUR, donc une BOÎTE au
 *  sortir de `runtime_invoke`. Le chemin générique poserait la boîte telle quelle dans `retval`
 *  et le HUD lirait une adresse comme un compte. Elles ont leur branche, qui DÉBALLE (`+0x10`). */
const DELEGUEES_ENTIERES = new Set(["MinUnitsNeededToStartBattle",
                                    "MaxUnitsPossibleToStartBattle",
                                    "AmountOfUnlockedUnits"]);

/** Les méthodes dont le corps SANDBOX est TRIVIAL — donc partagé par déduplication — et qu'on
 *  ancrerait malgré tout, en filtrant sur la classe de `this`.
 *
 *  ⚠ VIDE, ET CE N'EST PAS UNE PRUDENCE : C'EST UNE IMPOSSIBILITÉ MESURÉE.
 *  `SandboxGameModeSource$$AmountOfUnlockedUnits` fait TROIS octets — `33 c0 c3`, soit
 *  `xor eax,eax ; ret`. Frida refuse net : « unable to intercept function at 00007FFC4B7245B0 »
 *  (mesuré le 2026-08-23). Un trampoline inline a besoin de plus de place que ça, et les octets
 *  qui suivent sont le remplissage `cc` d'une AUTRE fonction. Le filtre par classe était donc la
 *  bonne idée pour le mauvais obstacle : ce n'est pas le partage qui bloque, c'est la TAILLE.
 *  Le mécanisme reste câblé (il servira à un corps partagé mais assez long) ; la liste, elle,
 *  reste vide tant qu'aucun cas ne le justifie. */
const DELEGUEES_TRIVIALES_FILTREES = new Set<string>();

const DELEGUEES: Array<{ nom: string; params: number; role: string; valeurs?: boolean[] }> = [
    { nom: "GetUnitModel", params: 2, valeurs: [false, true],
      role: "commande la POSE -- sandbox rend un `HotseatUnitModel`, qui échoue à `IsUnlocked`" },
    { nom: "GetGameModeSpecificDeploymentHudOptions", params: 0,
      role: "apporte les RESTRICTIONS -- sandbox rend des options par défaut, donc AUCUNE règle" },
    { nom: "GetUnitsForDeploymentHUD", params: 0,
      role: "apporte le ROSTER réel -- sandbox rend une liste vide" },
    // LE DERNIER DÉPLOIEMENT UTILISÉ — le jeu le PERSISTE, la sandbox rend un tableau VIDE.
    //
    // `CampaignGameModeSource$$GetBattleLineup(lineupIndex)` fabrique une clé
    // (`<campagne>_<lineupIndex>`), la passe au slot d'interface `0x5e` de `this+0x28` qui rend le
    // lineup SAUVEGARDÉ, puis appelle
    // `LineupHelper$$GetCampaignBattleLineupUsingRequiredUnits(lineupIndex, sauvegardé,
    // déployables, restrictions)`. `SandboxGameModeSource$$GetBattleLineup`, lui, s'écrit en
    // entier : `return <tableau vide>`.
    //
    // ⚠ C'EST LA COMPOSITION, PAS LES CASES. Le type déclaré est `System.String[]` (des `unitId`) :
    // aucune position n'y transite. Les cases restent l'affaire de `deploymentMemoire`, qui les
    // rejoue par l'étage FSM. Les deux sont complémentaires, pas redondants.
    //
    // ⚠ `lineupIndex` est un `System.Int32`, donc un TYPE VALEUR : il doit être RÉ-EMPAQUETÉ
    // (cf. le bloc `valeurs` ci-dessous), sans quoi `0` partirait comme pointeur nul.
    { nom: "GetBattleLineup", params: 1, valeurs: [true],
      role: "le DERNIER DÉPLOIEMENT du joueur sur ce noeud -- sandbox rend un tableau VIDE" },
    { nom: "GetUnlockedUnitsPooled", params: 0,
      role: "dictionnaire des débloqués -- MESURÉ jamais appelé sur ce chemin (cf. §13)" },
    // LES DEUX BORNES DU HUD. Mesuré le 2026-08-23 sur un onslaught Chaos tier 18 : une fois le
    // roster délégué (`allUnitModels` 0 -> 29), `minUnitsPossible` et `maxUnitsPossible`
    // restaient à `0` -- le HUD les lit sur la SANDBOX, qui rend zéro. Avec `min = 0` il n'y a
    // aucun plancher à franchir, et avec `max = 0` aucune place : l'écran a un roster mais reste
    // inutilisable. La source du mode, elle, rend 3 et 5.
    { nom: "MinUnitsNeededToStartBattle", params: 0,
      role: "le PLANCHER de pose -- sandbox rend 0, donc aucune règle de démarrage" },
    { nom: "MaxUnitsPossibleToStartBattle", params: 0,
      role: "le PLAFOND de pose -- sandbox rend 0, donc AUCUNE place déployable" },
    // ⚠ LE TERME QUI ÉCRASE LES DEUX AUTRES, ET QUI N'EST PAS DANS LA FORMULE QU'ON CROYAIT.
    // Le HUD ne demande PAS ses bornes à la source : il les demande à
    // `IdunBattle.View.FSM.VisualBattleQuery`, qui les CALCULE (décompilé, 2026-08-23) --
    //
    //     Max = SPMath.Min( <slot 0x31 de la source>,
    //                       GetSpawnPointCoordinatedForHumanPlayer(this).Count,
    //                       <slot 0x33 de la source> )
    //     Min = SPMath.Min( <slot 0x31>, <même Count>, <slot 0x32> )
    //
    // Déléguer `Min|MaxUnitsPossibleToStartBattle` (les slots 0x32/0x33) ne suffit donc PAS :
    // un `Min` à trois termes est écrasé par le plus petit. Mesuré sur l'onslaught Chaos tier
    // 18 : source déléguée à 3 et 5, points d'apparition du joueur = 3, et le HUD affichait
    // quand même `0/0`. Le terme coupable est le premier.
    { nom: "AmountOfUnlockedUnits", params: 0,
      role: "le 1er terme du `SPMath.Min` de `VisualBattleQuery` -- il ÉCRASE les deux bornes" },
];

interface Delegation {
    nom: string; role: string;
    listener: InvocationListener | null;
    miCampagne: { ptr: NativePointer; info: NativePointer } | null;
    ancrage: { sandbox: string; campagne: string; tete: Tete } | null;
    /** LE PRÊTEUR SUR LEQUEL LA MÉTHODE A ÉTÉ RÉSOLUE — pas celui qui est demandé aujourd'hui.
     *  `null` = jamais armée. Cf. `armerUneDelegation` : sans ce témoin, un ré-armement avec un
     *  AUTRE prêteur laissait la méthode de l'ancien en place, en silence. */
    preteurArme: Preteur | null;
    fires: number; emprunts: number;
    /** Appels qui ont PASSÉ le filtre de classe (corps partagé). Égal à `fires` pour une
     *  méthode à corps propre. L'écart avec `fires` dit combien d'appels ÉTRANGERS traversent
     *  l'ancrage — c'est ce qui rend un filtre trop étroit visible au lieu d'inerte. */
    passesFiltre: number;
    /** Dernier incident RÉEL — jamais avalé, jamais résumé en booléen. */
    dernier: { ok: boolean; detail: string } | null;
}

const delegations: Delegation[] = DELEGUEES.map((d) => ({
    nom: d.nom, role: d.role, listener: null, miCampagne: null, ancrage: null,
    preteurArme: null, fires: 0, emprunts: 0, passesFiltre: 0, dernier: null,
}));

/**
 * QUI PRÊTE À LA DÉLÉGATION — et ce n'est pas toujours la campagne.
 *
 * ⚠ MESURÉ le 2026-08-17, et c'est la cause d'un défaut que l'écran montrait depuis longtemps :
 * l'emplacement Machine of War ne proposait RIEN, ni en guild boss ni en PvP.
 * `SandboxGameModeSource$$GetGameModeSpecificDeploymentHudOptions` s'écrit en entier :
 *
 *     options = new GameModeSpecificUnitDeploymentHudOptions()   // ctor NU
 *     options[0x86] = 0                                          // isOnlineOnly = false
 *     return options
 *
 * Elle ne touche JAMAIS `+0x85 supportsMachinesOfWar`, qui reste donc au zéro de l'allocation.
 * Et elle ne consulte même pas `GameModeExtensions$$SupportsMachinesOfWar`, la règle qui dit
 * quels modes acceptent les MoW. Le défaut est donc dans la SANDBOX, pas dans le mode — d'où
 * son universalité.
 *
 * ⚠ EMPRUNTER À LA CAMPAGNE SUFFIRAIT À RALLUMER LES MoW, ET SERAIT FAUX : le même objet porte
 * les restrictions, la quantité déployable et les objectifs du mode. On prendrait les règles de
 * la campagne pour une bataille de guild boss — exactement le vice déjà payé sur le roster
 * (impérial sur un montage PvP). Le prêteur DOIT être la source du mode monté.
 */
/**
 * ⚠ `guildWar` REND LES DEUX DEFAUTS D'UN SEUL COUP, ET C'EST MESURE (2026-08-19).
 * Sur un montage guild war, l'écran de déploiement montrait un roster VIDE **et** aucun
 * emplacement MoW. Les deux tombent sur la même délégation :
 *
 *   - `GetUnitModel` — la sandbox rend un `HotseatUnitModel`, qui échoue à `IsUnlocked`. La HUD
 *     recevait bien les 98 unités (`dernierRemplissage.ajoutes = 98`, aucune erreur) puis les
 *     rejetait UNE PAR UNE. Le vide était donc EN AVAL du remplissage, pas dedans — et
 *     `deploymentStartArmer` le confirmait par `tailleUnits: 0` au START.
 *   - `GetGameModeSpecificDeploymentHudOptions` — le défaut sandbox décrit ci-dessus.
 *     `GuildWarsGameModeSource$$GetGameModeSpecificDeploymentHudOptionsInternal` est la SEULE
 *     lectrice de `GuildWarBattleData.RarityCap` (+0x44) : c'est elle qui pose le cap de rareté
 *     du mode en même temps que le support MoW.
 *
 * La source vient de `guildWarSourceForger` — donc du MODE MONTÉ, comme cette section l'exige.
 */
/**
 * ⚠ `onslaught` A LE MÊME DÉFAUT, ET SA CLASSE N'EST PAS LÀ OÙ ON LA CHERCHE.
 * Mesuré le 2026-08-23, tier 18 voie Chaos monté par `sandbox_mode.py start --mode waves` :
 * `stage = Setup` (la phase s'ouvre), mais le HUD rend `minUnitsPossible: 0
 * maxUnitsPossible: 0  allUnitModels: 0  allUnlockedUnitModels: 0` et `_units.taille = 0`.
 * Même stub sandbox, même remède : déléguer à la source du mode.
 *
 * ⚠ Et le piège est en amont du câblage : `OnslaughtGameModeSource` ne vit PAS dans
 * `IdunBattle.ViewLogic.BattleSource` — où sont les 23 autres sources de mode — mais sous
 * `idun.Idun.Source.IdunMeta.View.Features.Onslaught.Battle`. Un balayage limité au namespace
 * des autres rend ZÉRO et fait conclure « pas de source onslaught sur ce build ». Conclusion
 * FAUSSE, tirée d'une recherche trop étroite — elle a été faite avant ce commit.
 *
 * La source vient de `onslaughtSourceForger {alliance, tier}` — donc du MODE, et paramétrée par
 * la voie et le palier, qui sont des arguments EN CLAIR de son ctor.
 */
type Preteur = "campagne" | "guildBoss" | "guildWar" | "onslaught";
let preteurDelegation: Preteur = "campagne";

/** La source qui prête, son NAMESPACE et la CLASSE sur lesquels résoudre la méthode déléguée.
 *
 * ⚠ LE NAMESPACE FAIT PARTIE DU PRÊTEUR. Il était supposé valoir `NS_SRC` pour tout le monde —
 * vrai pour trois prêteurs sur quatre, faux pour l'onslaught, et l'échec était SILENCIEUX. */
function sourcePreteuse(): { ptr: NativePointer | null; ns: string; cls: string; nom: Preteur } {
    if (preteurDelegation === "guildBoss") {
        return { ptr: sourceGuildBossForgee(), ns: NS_SRC,
                 cls: "GuildBossGameModeSource", nom: "guildBoss" };
    }
    if (preteurDelegation === "guildWar") {
        return { ptr: sourceGuildWarForgee(), ns: NS_SRC,
                 cls: "GuildWarsGameModeSource", nom: "guildWar" };
    }
    if (preteurDelegation === "onslaught") {
        return { ptr: sourceOnslaughtForgee(),
                 ns: "idun.Idun.Source.IdunMeta.View.Features.Onslaught.Battle",
                 cls: "OnslaughtGameModeSource", nom: "onslaught" };
    }
    // ⚠ LA CAPTÉE D'ABORD, LA FORGÉE ENSUITE -- et le repli n'est pas un confort.
    // La source captée l'est par un ancrage sur le ctor, qui ne tire QU'À LA NAVIGATION : après
    // un reinject, ou sur un nœud monté en sandbox sans passer par l'écran, elle est NULLE. Le
    // prêteur rendait alors `null`, la délégation ne se faisait pas, et l'écran de déploiement
    // affichait un ROSTER VIDE (mesuré le 2026-08-20 sur `elite4` nœud 31) -- BC juste, écran
    // inutilisable. `campaignSourceForger` construit la même classe sans naviguer : on l'accepte
    // exactement comme le prêteur guild boss accepte la sienne.
    const captee = getCampaignGameModeSourcePtr();
    if (captee !== null && !captee.isNull()) {
        return { ptr: captee, ns: NS_SRC, cls: CLS_CAMP, nom: "campagne" };
    }
    return { ptr: sourceCampagneForgee(), ns: NS_SRC, cls: CLS_CAMP, nom: "campagne" };
}

/** Le contexte du prêteur guild boss, retenu pour pouvoir RÉ-EMPRUNTER à l'identique. */
let gbEncounterIndex = 0;
let gbIncludeLocked = false;

/**
 * ⚠ UNE `PooledList` NE SE SUBSTITUE QU'UNE FOIS -- et c'est le RETRY qui l'a révélé.
 *
 * Le pré-emprunt fige UNE valeur, calculée avant le montage, puis la re-pose à chaque appel.
 * Ça tient tant qu'il n'y a qu'un seul `Show`. Mesuré le 2026-08-17 : au RETRY, l'écran revient
 * bien en phase de déploiement mais le roster est VIDE -- le premier `Show` a consommé la
 * liste, qui est retournée au pool, et le second reçoit un pointeur recyclé. Le nom du type le
 * disait déjà.
 *
 * Le prêteur guild boss n'a AUCUN besoin du pré-emprunt : celui-ci n'existe que pour laisser le
 * masque `sansFiltre` agir hors hook (cf. §24), or `GetDeployableUnitsPooled` applique déjà
 * `DisallowedFactions`. On ré-emprunte donc FRAIS à chaque appel.
 */
function rosterFraisGuildBoss(): NativePointer | null {
    const boite = rosterPooledGuildBoss(gbEncounterIndex, gbIncludeLocked);
    if (typeof boite === "object" && boite !== null
        && (boite as { ok?: boolean }).ok === false) return null;
    const b = boite as NativePointer;
    if (b.isNull()) return null;
    gcRoot.add(b);
    try {
        // `PooledList<T>` est un TYPE VALEUR : `runtime_invoke` le boxe, la valeur est à +0x10.
        const deboxe = b.add(0x10).readPointer();
        if (deboxe.isNull()) return null;
        gcRoot.add(deboxe);
        return deboxe;
    } catch { return null; }
}

// ============================================================================
// ROSTER NON FILTRÉ — lever le filtre de NŒUD, sans toucher au nœud.
//
// `CampaignProgression$$GetDeployableUnits(locationIndex: Nullable<Int32>, onlyUnlocked)`
// charge TA collection puis la filtre :
//
//     info = null
//     si locationIndex.HasValue :                       <-- TOUT le filtrage est sous ce test
//         info = (this->_battles[idx], GetStarsOfLocation(idx))
//     unites = this->_unitProgression.GetUnits(flags, null)
//     return CampaignBattleInfo.GetDeployableUnits(info, ..., unites, ...)
//
// Un `Nullable` SANS valeur rend donc la collection non filtrée. Mais
// `CampaignGameModeSource$$GetUnitsForDeploymentHUD` en construit toujours un AVEC valeur
// (depuis `_currentLocationIndex`, un `Int32`) : ce chemin est inatteignable sans intervenir.
//
// ⚠ DEUX RÉGIMES, ET L'OBSERVATION EST LE DÉFAUT. On ne sait pas d'avance si un
// `Nullable<Int32>` (8 octets) arrive PAR VALEUR dans un registre — auquel cas `args[1]` porte
// `valeur | hasValue<<32` — ou PAR POINTEUR. Masquer un POINTEUR le corromprait, et une faute
// native sur le thread principal fige le jeu (deux fois le 2026-08-17). On LIT donc d'abord :
// `74` + `hasValue 1` donnerait `0x10000004a`, une adresse de tas ne ressemble à rien de tel.
//
// ⚠ Et l'effet est BORNÉ À L'APPEL EMPRUNTÉ (`dansEmprunt`) : `GetDeployableUnits` sert aussi
// aux écrans méta, où lever le filtre mentirait à l'interface du jeu.
let sansFiltreArme = false;
let sansFiltreEcrit = false;
let dansEmprunt = false;
let listenerDeployable: InvocationListener | null = null;
// ⚠ COMPTER TOUS LES PASSAGES, PAS SEULEMENT CEUX DE LA FENÊTRE. Un compteur conditionné par
// `dansEmprunt` ne sait pas distinguer « la méthode n'est jamais appelée » (donc la classe
// ancrée est la mauvaise) de « elle est appelée hors fenêtre » (donc c'est ma fenêtre qui est
// fausse). Les deux rendent zéro observation, et ce zéro-là ne désigne rien.
let firesDeployable = 0;
// La valeur PRÉ-EMPRUNTÉE, déjà déboxée, prête à être substituée par la délégation.
let preEmprunt: NativePointer | null = null;
let preEmpruntInfo: Record<string, unknown> | null = null;
const observationsNullable: Array<{
    brut: string; basse: string; haute: string; dansEmprunt: boolean; ecrit: boolean;
}> = [];

function armerSansFiltre(ecrire: boolean): true | Refus {
    sansFiltreArme = true;
    sansFiltreEcrit = ecrire;
    if (listenerDeployable) return true;
    const k = findClassAnywhere("IdunMetaLogic.UserProgress", "CampaignProgression");
    if (!k) return refus("`CampaignProgression` INTROUVABLE sur ce build");
    const mi = findMethodByParamCount(k, "GetDeployableUnits", 2);
    if (!mi) {
        return refus("`CampaignProgression$$GetDeployableUnits` INTROUVABLE (2 paramètres)");
    }
    const tete = lireTete(mi.ptr);
    if (tete.erreur !== null) return refus(`tête ILLISIBLE (${tete.erreur})`);
    if (teteTriviale(tete)) {
        return refus("REFUS : `GetDeployableUnits` résout sur un corps TRIVIAL "
            + `(ret à l'octet ${tete.retA} ; tête = ${tete.hex}) -- adresse probablement `
            + "PARTAGÉE par déduplication IL2CPP. Cf. case-10020 §8.");
    }
    listenerDeployable = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            firesDeployable++;
            const brut = args[1];
            let ecrit = false;
            if (sansFiltreArme && dansEmprunt && sansFiltreEcrit) {
                // ⚠ DISPOSITION **MESURÉE**, ET ELLE EST L'INVERSE DE CELLE QU'ON SUPPOSE.
                // Observation d'un appel NATUREL du jeu : `0x4a00000001` pour
                // `_currentLocationIndex = 74`. Donc 32 bits BAS = `hasValue` (1), 32 bits
                // HAUTS = la valeur (0x4a). Le `Nullable<Int32>` est rangé
                // `{ bool hasValue; int value; }`, pas `{ int value; bool hasValue; }`.
                //
                // Masquer les bits BAS (ce que faisait la version d'avant) aurait gardé
                // `hasValue = 1` et mis l'index à 0 : un AUTRE nœud, pas l'absence de filtre.
                // Ça aurait « marché » en faisant tout autre chose -- et c'est exactement ce
                // que le régime observation-d'abord existe pour attraper.
                args[1] = brut.and(ptr("0xffffffff00000000"));
                ecrit = true;
            }
            if (observationsNullable.length < 24) {
                observationsNullable.push({
                    brut: brut.toString(),
                    basse: brut.and(ptr("0xffffffff")).toString(),
                    haute: brut.shr(32).toString(),
                    dansEmprunt, ecrit,
                });
            }
        },
    });
    Interceptor.flush();
    return true;
}

// ============================================================================
// LE HUD LUI-MÊME — mesurer le REFUS DE POSE plutôt que le déduire.
//
// `idun.ui.UnitDeploymentHud$$Show(units, minUnitsPossible, maxUnitsPossible, options)`
// remplit DEUX dictionnaires : `_allUnitModels` pour tous, et `_allUnlockedUnitModels`
// **seulement si `IUnitModelExtensions$$IsUnlocked(u)`**. C'est le SECOND que
// `TryMarkUnitAsPlaced(unitId, isMachineOfWar)` interroge.
//
// ⇒ « je sélectionne mais je ne pose pas » est exactement la signature d'un premier
// dictionnaire plein et d'un second vide. On ne le DÉDUIT pas : on lit les deux comptes au
// moment du remplissage, et on capture le VERDICT de chaque clic.
//
// OBSERVATION PURE : aucun de ces deux ancrages n'écrit, et on n'invoque ni l'un ni l'autre.
const NS_HUD = "idun.ui";
const CLS_HUD = "UnitDeploymentHud";
let listenerShow: InvocationListener | null = null;
let listenerPose: InvocationListener | null = null;
let listenerBoard: InvocationListener | null = null;
let hudEtat: Record<string, unknown> | null = null;
/** L'instance du HUD, gardée pour pouvoir la relire APRÈS `Show` (l'état bouge à chaque pose). */
let hudInstance: NativePointer | null = null;
/** Comment `hudInstance` a été obtenue — pour qu'un lecteur sache s'il lit la vraie ou un repli. */
let hudSource: "Show" | "scene" | null = null;

/** S'ASSURER qu'on a le HUD, même si `Show` n'a pas tiré.
 *
 * ⚠ MÊME CAUSE QUE `vueDeDeploiement`, MÊME SOIRÉE PERDUE. `hudInstance` n'est écrite QUE dans
 * le `onEnter` de `UnitDeploymentHud$$Show` -- ni `TryMarkUnitAsPlaced` ni aucune pose ne
 * l'écrivent. Sur une bataille dont l'écran de déploiement était DÉJÀ affiché quand on s'arme,
 * `Show` est passé, et le HUD reste introuvable pour toute la durée de la bataille. Mesuré le
 * 2026-08-20 : plafond INCONNU -> toute pose refusée -> START refusé, sur un jeton dépensé.
 *
 * Contrairement à `IdunGameViews`, `UnitDeploymentHud` est un `MonoBehaviour` : la scène peut
 * donc le rendre. On le note (`hudSource`) plutôt que de laisser croire qu'il vient de `Show`.
 *
 * ⚠ TRI-ÉTAT PRÉSERVÉ : si la scène ne le rend pas, on reste à `null` -- ce qui fait REFUSER en
 * amont. Un repli qui échoue ne doit jamais devenir un zéro.
 */
function assurerHud(): NativePointer | null {
    if (hudInstance !== null && !hudInstance.isNull()) return hudInstance;
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    if (!k) return null;
    const r = premiereInstance(k);
    if (!(r instanceof NativePointer) || r.isNull()) return null;
    hudInstance = r;
    hudSource = "scene";
    return hudInstance;
}

/** Les chemins natifs de la bascule héros <-> MoW, ancrés en OBSERVATION PURE.
 *  `EmptyMachineOfWarPlatformTapped` / `EmptySpawnPointTapped` = les clics sur le PLATEAU ;
 *  `HandleOnSwitchTo*Tapped` = les BOUTONS de bascule ; `ShowStandardUnitSelection` =
 *  l'affichage du roster héros, celui qui LÈVE si `_units` est nul. */
// ⚠ LES CINQ APPELANTS DE `PrepareFor...` SONT TOUS LÀ, et c'est la leçon : la première liste
// n'en portait que trois, donc un tir de `PrepareFor...` restait SANS ORIGINE et rendait les
// compteurs mutuellement incompatibles. `PutUnitIntoHand` et `SetCurrentlySelectedUnit` sont les
// deux qui manquaient -- ce sont les chemins de SÉLECTION, pas ceux de la bascule de MODE.
const CHEMINS_BASCULE = [
    "EmptyMachineOfWarPlatformTapped", "EmptySpawnPointTapped",
    "HandleOnSwitchToMachinesOfWarUnitsTapped", "HandleOnSwitchToStandardUnitsTapped",
    "ShowStandardUnitSelection", "PrepareForStandardUnitMachineOfWarSelectionSwitch",
    "PutUnitIntoHand", "SetCurrentlySelectedUnit", "RemoveUnit",
] as const;
const cheminsListeners: Record<string, InvocationListener> = {};
const cheminsEtat: Record<string, unknown> = {};

/**
 * Les chemins dont l'ARGUMENT porte une identité d'unité, et comment le lire.
 *
 * ⚠ POURQUOI L'ARGUMENT, ET PAS SEULEMENT LE COMPTEUR. Symptôme mesuré le 2026-08-19 : une
 * unité ôtée du plateau revient au roster et RESTE sur le plateau. La cause est structurelle —
 * le HUD ne connaît que des `PlaceholderUnitView`, nos unités sont RÉELLES sur le runner, et
 * le seul relais qui atteigne une unité réelle est celui du bouton « tout enlever »
 * (`HandleOnRemoveAllHeroesPressed`, cf. `armerClear`). La dépose unité par unité n'en a aucun.
 *
 * ⚠ RESTE À SAVOIR QUELLE MÉTHODE LA PORTE, ET LES COMPTEURS SEULS NE LE DISENT PAS :
 * `PutUnitIntoHand` a tiré 9 fois pour 4 poses acceptées, donc elle porte AUSSI la prise en
 * main depuis le roster — son nom le dit. Y accrocher un `RemoveUnitMessage` ferait disparaître
 * une unité au simple clic sur le roster. L'identité capturée ici est ce qui tranchera :
 * une dépose nomme l'unité DU PLATEAU, une prise en main nomme celle qu'on saisit.
 */
const CHEMINS_ARG: Record<string, "chaine" | "unitConfigId"> = {
    PutUnitIntoHand: "chaine",
    RemoveUnit: "unitConfigId",
};

/**
 * Ce qu'on peut LIRE d'un `IdunBattle.Configuration.UnitConfigId`.
 *
 * C'est un type VALEUR de 48 octets (`classes.tsv`), donc passé PAR ADRESSE. On ne prétend PAS
 * en connaître la disposition : on rend les six mots, et pour chacun la chaîne IL2CPP qu'il
 * désigne s'il en désigne une. Les trois `.ctor` déclarent `pureId : System.String` en tête, ce
 * qui fait du premier mot le candidat — mais c'est la LECTURE qui le dira, pas ce commentaire.
 *
 * `readIl2cppString` borne la longueur et avale ses propres accès invalides : le passer sur un
 * mot qui n'est pas une chaîne rend `null`, jamais une lecture sauvage.
 */
function lireUnitConfigId(p: NativePointer): Record<string, unknown> {
    if (p.isNull()) return { nul: true };
    const mots: Array<{ i: number; hex: string; chaine: string | null }> = [];
    for (let i = 0; i < 6; i++) {
        try {
            const m = p.add(i * 8).readPointer();
            mots.push({ i, hex: m.toString(), chaine: readIl2cppString(m) });
        } catch { mots.push({ i, hex: "ILLISIBLE", chaine: null }); }
    }
    const porteur = mots.find((m) => m.chaine !== null);
    return { unitId: porteur ? porteur.chaine : null,
             motPorteur: porteur ? porteur.i : null, mots };
}

/**
 * L'ÉTAT VIVANT DE LA BASCULE HÉROS <-> MACHINES OF WAR.
 *
 * ⚠ L'instantané de `Show` NE SUFFIT PAS : ces trois champs bougent à chaque clic sur un point
 * de spawn, longtemps après le dernier `Show`. Symptôme qui l'a exigé (2026-08-19) : cliquer un
 * emplacement MoW bascule bien le roster, cliquer ensuite un spawn héros ne le ramène PAS.
 *
 * Le décompilé nomme les deux causes possibles, et elles sont indiscernables à l'écran :
 *   `UnitDeploymentHud$$EmptySpawnPointTapped` ne fait RIEN si `_isMachinesOfWarSelection` est
 *   déjà faux ; et `ShowStandardUnitSelection` LÈVE si `_units` est nul (le clic paraît alors
 *   sans effet, l'exception étant avalée par la boucle d'évènements Unity).
 *
 * Résolus PAR NOM, et l'offset est CONFRONTÉ à celui du décompilé — un renommage se signale au
 * lieu d'être subi.
 */
function etatBasculeHud(): Record<string, unknown> | null {
    if (hudInstance === null || hudInstance.isNull()) return null;
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    if (!k) return { erreur: `classe \`${NS_HUD}.${CLS_HUD}\` introuvable` };
    const champs: Array<{ nom: string; attendu: number; type: "bool" | "liste" }> = [
        { nom: "_isMachinesOfWarSelection", attendu: 0x221, type: "bool" },
        { nom: "_hasMachinesOfWar", attendu: 0x222, type: "bool" },
        { nom: "_units", attendu: 0x230, type: "liste" },
    ];
    const out: Record<string, unknown> = {};
    for (const c of champs) {
        const off = getFieldOffset(k, c.nom);
        if (off < 0) { out[c.nom] = { absent: true }; continue; }
        try {
            if (c.type === "bool") {
                out[c.nom] = { valeur: hudInstance.add(off).readU8() !== 0,
                               offset: off, attendu: c.attendu, concorde: off === c.attendu };
            } else {
                const l = hudInstance.add(off).readPointer();
                out[c.nom] = { nul: l.isNull(), taille: l.isNull() ? null : l.add(0x18).readS32(),
                               offset: off, attendu: c.attendu, concorde: off === c.attendu };
            }
        } catch (e) { out[c.nom] = { erreur: (e as Error).message }; }
    }
    return out;
}

/**
 * Les deux champs qui expliquent le bouton START.
 *
 * ⚠ MESURÉ : la comptabilité du HUD et la composition RÉELLE de la bataille sont DEUX choses
 * séparées, et en sandbox aucune ne nourrit l'autre. Unités déclarées dans `bc.Units` -> elles
 * apparaissent sur le plateau mais `_currentlyPlacedUnits` reste VIDE, donc START est grisé.
 * Unités posées par le HUD -> START s'active, mais le combat démarre sans unité joueur réelle
 * et se termine aussitôt. `HandleOnStartBattleTapped` relaie les posées à
 * `_callbacksDelegate` (`IDeploymentHudCallbacks`, slot 3) : c'est LÀ que se fait le raccord,
 * et savoir QUI l'implémente est le préalable.
 */
function etatDuBouton(): Record<string, unknown> {
    const hud = assurerHud();
    if (hud === null) {
        return { mesure: false, raison: "aucune instance de HUD -- ni captée à son `Show`, ni "
            + "rendue par la scène" };
    }
    const out: Record<string, unknown> = { mesure: true, hud: hud.toString(),
                                           source: hudSource };
    try {
        const k = hud.readPointer();
        const offCb = getFieldOffset(k, "_callbacksDelegate");
        const offPl = getFieldOffset(k, "_currentlyPlacedUnits");
        if (offCb >= 0) {
            const cb = hud.add(offCb).readPointer();
            out.callbacks = cb.toString();
            out.classeCallbacks = cb.isNull() ? null : classeDerriere(cb).classe;
        } else { out.callbacks = "champ `_callbacksDelegate` ABSENT"; }
        if (offPl >= 0) {
            const lst = hud.add(offPl).readPointer();
            if (lst.isNull()) { out.placees = "liste NULLE"; }
            else {
                const kl = lst.readPointer();
                const offSize = getFieldOffset(kl, "_size");
                out.placees = offSize < 0 ? "champ `_size` ABSENT" : lst.add(offSize).readS32();
            }
        } else { out.placees = "champ `_currentlyPlacedUnits` ABSENT"; }
    } catch (e) { out.erreur = (e as Error).message; }
    return out;
}
const hudPoses: Array<{ unitId: string | null; mow: boolean; accepte: boolean }> = [];
// ⚠ L'ÉTAGE QUI POSE VRAIMENT. `TryMarkUnitAsPlaced` n'est que la comptabilité du roster —
// mesuré : il rend `true` (l'unité se grise) alors que le plateau ne bouge pas.
// `StateMachineActions$$UnitDeployment_PlaceUnitOnBoard` interroge le HUD puis délègue à un
// SECOND étage ; c'est celui-là qu'il faut voir.
const hudBoard: Array<{
    unitId: string | null; col: number; row: number; manuel: boolean; playerId: number;
    retour: number;
}> = [];

/** Compte d'un `Dictionary<K,V>` : `_count - _freeCount`, les deux résolus PAR NOM. */
function compteDict(dico: NativePointer): number | string {
    try {
        if (dico.isNull()) return "NUL";
        const k = dico.readPointer();
        const oc = getFieldOffset(k, "_count");
        const of = getFieldOffset(k, "_freeCount");
        if (oc < 0) return "champ `_count` absent de " + (s(class_get_name(k) as NativePointer));
        const c = dico.add(oc).readS32();
        const f = of < 0 ? 0 : dico.add(of).readS32();
        return c - f;
    } catch (e) { return "ILLISIBLE : " + (e as Error).message; }
}

function armerHud(): true | Refus {
    if (listenerShow && listenerPose) return true;
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    if (!k) return refus(`\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE sur ce build`);
    const miShow = findMethodByParamCount(k, "Show", 4);
    const miPose = findMethodByParamCount(k, "TryMarkUnitAsPlaced", 2);
    if (!miShow) return refus("`UnitDeploymentHud$$Show` INTROUVABLE (4 paramètres)");
    if (!miPose) {
        return refus("`UnitDeploymentHud$$TryMarkUnitAsPlaced` INTROUVABLE (2 paramètres)");
    }
    for (const [nom, mi] of [["Show", miShow], ["TryMarkUnitAsPlaced", miPose]] as const) {
        const t = lireTete(mi.ptr);
        if (t.erreur !== null) return refus(`tête de \`${nom}\` ILLISIBLE (${t.erreur})`);
        if (teteTriviale(t)) {
            return refus(`REFUS : \`${CLS_HUD}$$${nom}\` résout sur un corps TRIVIAL `
                + `(ret à l'octet ${t.retA}) -- adresse probablement PARTAGÉE. Cf. §8.`);
        }
    }
    const offTous = getFieldOffset(k, "_allUnitModels");
    const offDebl = getFieldOffset(k, "_allUnlockedUnitModels");
    const offInput = getFieldOffset(k, "_disabledInput");
    if (offTous < 0 || offDebl < 0) {
        return refus("champ(s) absent(s) de `UnitDeploymentHud` sur ce build : "
            + `_allUnitModels=${offTous} _allUnlockedUnitModels=${offDebl} `
            + "-- chemin PÉRIMÉ, pas de repli sur un offset");
    }
    if (!listenerShow) {
        listenerShow = Interceptor.attach(miShow.ptr, {
            onEnter(args) {
                // `Show` remplit les dictionnaires : on lit APRÈS, pas avant.
                (this as unknown as { hud: NativePointer; mn: number; mx: number }).hud = args[0];
                hudInstance = args[0];
                hudSource = "Show";     // l'autorité : celui que le jeu vient d'afficher
                // ⚠ COMPTER LES ENTRÉES, PAS SEULEMENT LES SORTIES. `Show` VIDE les trois
                // dictionnaires en tête (`ClearWidgets`) et ne les remplit qu'à la fin : un
                // `Show` qui lève entre les deux laisse l'écran avec 0 modèle, et le compteur
                // de SORTIE, lui, ne bouge pas -- on croit alors qu'un seul `Show` a eu lieu et
                // qu'il s'est bien passé. `entrees > sorties` EST la signature de ce cas.
                showEnters++;
                dansShow = true;
                (this as unknown as { mn: number }).mn = args[2].toInt32();
                (this as unknown as { mx: number }).mx = args[3].toInt32();
            },
            onLeave() {
                const self = this as unknown as { hud: NativePointer; mn: number; mx: number };
                dansShow = false;
                try {
                    hudEtat = {
                        hud: self.hud.toString(),
                        minUnitsPossible: self.mn, maxUnitsPossible: self.mx,
                        allUnitModels: compteDict(self.hud.add(offTous).readPointer()),
                        allUnlockedUnitModels: compteDict(self.hud.add(offDebl).readPointer()),
                        // ⚠ LE POINTEUR, PAS SEULEMENT LE COMPTE. Un dictionnaire qui retombe à
                        // zéro peut avoir été VIDÉ (`Clear`) ou REMPLACÉ (le champ réaffecté à
                        // un objet neuf). Les deux se lisent « 0 » et appellent des enquêtes
                        // opposées ; seule l'identité de l'objet les sépare.
                        allUnitModelsPtr: self.hud.add(offTous).readPointer().toString(),
                        allUnlockedUnitModelsPtr: self.hud.add(offDebl).readPointer().toString(),
                        disabledInput: offInput < 0
                            ? null : self.hud.add(offInput).readU8() !== 0,
                    };
                } catch (e) { hudEtat = { erreur: (e as Error).message }; }
                // Le TÉMOIN D'ORDRE du capteur `StartMatch` : compter les affichages du HUD
                // suffit à dire si `StartMatch` a tiré AVANT (donc au montage) ou APRÈS (donc
                // au clic). Pas d'horloge à interpréter, pas de natif invoqué.
                showFires++;
                // ⛔ ON N'INVOQUE RIEN ICI — on ENFILE. Sans ce cran, une BC pré-remplie affiche
                // un START gris : le HUD ne compte que ce que LUI a posé, et `UpdateButtons`
                // n'a aucun appelant après le montage dans ce régime.
                if (syncAuto) planifierSync(6);
                // ⛔ ON N'INVOQUE RIEN ICI NON PLUS : `rejouerMemoire` ENFILE. C'est le retour
                // de la phase de déploiement (retry) qui doit rendre l'équipe déjà composée.
                //
                // ⛔ ET LE JETON EST EXIGÉ, PAS SEULEMENT `memoireAuto`. Ce `Show` tire sur TOUT
                // écran de déploiement -- y compris celui d'une bataille RÉELLE que le joueur
                // vient d'ouvrir lui-même. Mesuré le 2026-08-22 sur un combat officiel contre le
                // boss : la composition d'une sandbox précédente s'y est reposée toute seule.
                // `memoireRejeuArme` n'est posé que par `sandboxModeBcOverride`, donc une
                // bataille qu'on n'a pas montée ne peut plus rien déclencher.
                if (memoireAuto && memoireRejeuArme) {
                    memoireRejeuArme = false;      // USAGE UNIQUE -- consommé avant même de tirer
                    rejouerMemoire();
                } else if (memoireAuto) {
                    memoireDernier = "rejeu REFUSÉ : aucun jeton -- cette bataille n'a pas été "
                        + `montée par la sandbox (mémoire de ${memoireBataille ?? "aucune"})`;
                }
            },
        });
    }
    if (!listenerPose) {
        listenerPose = Interceptor.attach(miPose.ptr, {
            onEnter(args) {
                const self = this as unknown as { uid: string | null; mow: boolean };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.mow = args[2].toInt32() !== 0;
            },
            onLeave(retval) {
                const self = this as unknown as { uid: string | null; mow: boolean };
                if (hudPoses.length < 32) {
                    hudPoses.push({ unitId: self.uid, mow: self.mow,
                                    accepte: (retval.toInt32() & 0xff) !== 0 });
                }
            },
        });
    }
    if (!listenerMoW) {
        // LE PENDANT MoW de `UnitDeployment_PlaceUnitOnBoard`. Même étage, autre signature :
        // pas de colonne/ligne, mais une `MachineOfWarPosition`.
        const kam = findClassAnywhere("IdunBattle.View.FSM", "StateMachineActions");
        const mm = kam
            ? findMethodByParamCount(kam, "UnitDeployment_PlaceMachineOfWarUnitOnBoard", 4)
            : null;
        if (mm && !mm.ptr.isNull()) {
            const tm = lireTete(mm.ptr);
            if (tm.erreur === null && !teteTriviale(tm)) {
                listenerMoW = Interceptor.attach(mm.ptr, {
                    onEnter(args) {
                        try {
                            const uid = readIl2cppString(args[1]);
                            if (uid === null || uid === "") return;
                            // args[2]=isManual, args[3]=playerId, args[4]=position
                            memoireMoW = { unitId: uid, playerId: args[3].toInt32(),
                                           position: args[4].toInt32() };
                        } catch { /* best effort : la mémoire MoW reste ce qu'elle était */ }
                    },
                });
            }
        }
    }
    if (!listenerBoard) {
        const ka = findClassAnywhere("IdunBattle.View.FSM", "StateMachineActions");
        if (!ka) return refus("`IdunBattle.View.FSM.StateMachineActions` INTROUVABLE");
        const mb = findMethodByParamCount(ka, "UnitDeployment_PlaceUnitOnBoard", 5);
        if (!mb) {
            return refus("`StateMachineActions$$UnitDeployment_PlaceUnitOnBoard` INTROUVABLE "
                + "(5 paramètres)");
        }
        const tb = lireTete(mb.ptr);
        if (tb.erreur !== null) return refus(`tête de \`PlaceUnitOnBoard\` ILLISIBLE`);
        if (teteTriviale(tb)) {
            return refus("REFUS : `UnitDeployment_PlaceUnitOnBoard` résout sur un corps "
                + `TRIVIAL (ret à l'octet ${tb.retA}) -- adresse PARTAGÉE. Cf. §8.`);
        }
        listenerBoard = Interceptor.attach(mb.ptr, {
            onEnter(args) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; m: boolean; p: number;
                };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.c = args[2].toInt32();
                self.r = args[3].toInt32();
                self.m = (args[4].toInt32() & 0xff) !== 0;
                self.p = args[5].toInt32();
            },
            onLeave(retval) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; m: boolean; p: number;
                };
                if (hudBoard.length < 32) {
                    hudBoard.push({ unitId: self.uid, col: self.c, row: self.r,
                                    manuel: self.m, playerId: self.p,
                                    retour: retval.toInt32() & 0xff });
                }
                // ⛔ ON N'INVOQUE RIEN ICI — on ENFILE. Sans ce cran, la pose ne produit qu'un
                // `PlaceholderUnitView` que rien ne convertit en sandbox : START démarre une
                // bataille sans unité du joueur, qui se termine aussitôt.
                //
                // ⚠ Le retour n'est PAS un critère : mesuré, `AddPlaceholderUnit` rend `0`
                // AUSSI en succès (sa dernière instruction est une émission d'événement). On
                // enfile donc sur la pose, et c'est la RELECTURE DU PLATEAU qui tranche.
                //
                // (!)LE COMMIT AUTOMATIQUE QUI VIVAIT ICI EST SUPPRIMÉ. Il appliquait un
                // `AddUnitMessage` au runner À CHAQUE POSE, en plus du placeholder que le HUD
                // venait de créer : deux comptabilités pour un seul plafond, et le START
                // convertissait les placeholders PAR-DESSUS les unités réelles.
            },
        });
    }
    // ⚠ LES CHEMINS DE LA BASCULE HÉROS <-> MoW, COMPTÉS -- parce qu'un état AU REPOS ne
    // distingue pas « l'aller-retour a eu lieu » de « rien n'a bougé ». Mesuré le 2026-08-19 :
    // après un clic MoW puis un clic spawn héros, `_isMachinesOfWarSelection` valait `false`,
    // ce qui est AUSSI sa valeur initiale -- la lecture au repos ne prouvait donc rien. On
    // compte les tirs et on relève le drapeau À L'ENTRÉE et À LA SORTIE : c'est la TRANSITION
    // qui est le fait.
    armerChemins(k);
    // ⛔ OBSERVATION PURE sur `ClearWidgets`. On relève les trois comptes AVANT et APRÈS, et
    // l'état des compteurs de `Show` au moment du tir : c'est ce triplet qui NOMME l'appelant
    // sans avoir à lire une pile (`Show` incrémente `showEnters` à l'entrée, donc un tir de
    // `ClearWidgets` avec `showEnters` inchangé depuis le tir précédent vient de l'AUTRE
    // appelant, `IdunMainView$$EndBattleAndGoToMeta`).
    if (!listenerVidange) {
        const mClear = findMethodByParamCount(k, "ClearWidgets", 0);
        if (mClear && !mClear.ptr.isNull()) {
            const offTous2 = getFieldOffset(k, "_allUnitModels");
            const offPl2 = getFieldOffset(k, "_currentlyPlacedUnits");
            const lire = (hud: NativePointer): Record<string, unknown> => {
                const o: Record<string, unknown> = {};
                try { o.allUnitModels = compteDict(hud.add(offTous2).readPointer()); }
                catch { o.allUnitModels = null; }
                try {
                    const l = hud.add(offPl2).readPointer();
                    o.placees = l.isNull() ? null
                        : l.add(getFieldOffset(l.readPointer(), "_size")).readS32();
                } catch { o.placees = null; }
                return o;
            };
            listenerVidange = Interceptor.attach(mClear.ptr, {
                onEnter(args) {
                    const s = this as unknown as { hud: NativePointer; av: unknown; se: number };
                    s.hud = args[0];
                    s.se = showEnters;
                    s.av = offTous2 >= 0 && offPl2 >= 0 ? lire(args[0]) : null;
                },
                onLeave() {
                    const s = this as unknown as { hud: NativePointer; av: unknown; se: number };
                    vidangeFires++;
                    if (vidangeTrace.length < 24) {
                        vidangeTrace.push({
                            n: vidangeFires, avant: s.av,
                            apres: offTous2 >= 0 && offPl2 >= 0 ? lire(s.hud) : null,
                            showEntersAuTir: s.se, showFiresAuTir: showFires,
                            // EXACT, et pas une soustraction de compteurs : `Show` lève ce
                            // drapeau à son entrée et le baisse à sa sortie, sur le MÊME thread.
                            appelant: dansShow ? "UnitDeploymentHud$$Show"
                                : "IdunMainView$$EndBattleAndGoToMeta (seul autre appelant)",
                        });
                    }
                },
            });
        }
    }
    Interceptor.flush();
    return true;
}

/**
 * ANCRER LES CHEMINS DE BASCULE — sorti d'`armerHud` pour être RÉVERSIBLE NOMMÉMENT.
 *
 * ⚠ POURQUOI CE DÉCOUPAGE EXISTE. `deploymentHudArmer {armer:false}` ne détachait que
 * `Show`/`TryMarkUnitAsPlaced`/`AddPlaceholderUnit` : les neuf ancrages ci-dessous SURVIVAIENT à
 * tout désarmement, sans qu'aucun RPC ne puisse les ôter. Or `deploymentMowBasculer` INVOQUE
 * `HandleOnSwitchToMachinesOfWarUnitsTapped`, qui est dans la liste — on ancre donc la méthode
 * qu'on appelle, et le décompilé nomme deux autres ancrés dans sa descendance
 * (`PrepareForStandardUnitMachineOfWarSelectionSwitch`, `ShowStandardUnitSelection`). Tant que le
 * robinet manquait, « l'ancrage est-il la cause ? » n'était pas une question MESURABLE.
 */
function armerChemins(k: NativePointer, seulement?: readonly string[]): string[] {
    const faits: string[] = [];
    for (const nom of CHEMINS_BASCULE) {
        if (seulement !== undefined && !seulement.includes(nom)) continue;
        if (cheminsListeners[nom] !== undefined) continue;
        const mi = findMethod(k, nom);
        if (!mi || mi.ptr.isNull()) { cheminsEtat[nom] = { introuvable: true }; continue; }
        // ⚠ ON PUBLIE LA VA, ET CE N'EST PAS DÉCORATIF. Mesuré le 2026-08-19 : trois compteurs
        // MUTUELLEMENT INCOMPATIBLES (`PrepareFor...` à 1 tir alors que ses DEUX seuls appelants
        // étaient l'un à 0 et l'autre sous une garde fausse). Un ancrage peut tomber sur un corps
        // DÉDUPLIQUÉ ou sur une surcharge voisine ; sans l'adresse, on croit le compteur et on
        // conclut à l'envers. La tête est contrôlée pour la même raison (cf. §8).
        const t = lireTete(mi.ptr);
        cheminsEtat[nom] = { fires: 0, transitions: [], args: [], va: ghidraVA(mi.ptr),
                             teteTriviale: t.erreur === null ? teteTriviale(t) : null,
                             teteErreur: t.erreur };
        const genreArg = CHEMINS_ARG[nom];
        cheminsListeners[nom] = Interceptor.attach(mi.ptr, {
            onEnter(args) {
                const s = this as unknown as {
                    av: boolean | null; hud: NativePointer; arg: unknown;
                };
                s.hud = args[0];
                s.av = lireDrapeauMoW(args[0]);
                // ⛔ LECTURE DE MÉMOIRE SEULEMENT, jamais une invocation. C'est la leçon des
                // deux gels : appeler un natif depuis un callback d'interception fige le jeu.
                s.arg = undefined;
                if (genreArg !== undefined) {
                    try {
                        s.arg = genreArg === "chaine"
                            ? readIl2cppString(args[1])
                            : lireUnitConfigId(args[1]);
                    } catch (e) { s.arg = { erreur: (e as Error).message }; }
                }
            },
            onLeave() {
                const s = this as unknown as {
                    av: boolean | null; hud: NativePointer; arg: unknown;
                };
                const e = cheminsEtat[nom] as {
                    fires: number; transitions: unknown[]; args: unknown[];
                };
                e.fires++;
                if (e.transitions.length < 16) {
                    e.transitions.push({ avant: s.av, apres: lireDrapeauMoW(s.hud) });
                }
                if (s.arg !== undefined && e.args.length < 16) e.args.push(s.arg);
                // LE RELAIS DE DÉPOSE. Il vit ICI et pas sur un ancrage à lui : le chemin est
                // le même que celui qu'on observe, et en poser deux sur une seule méthode ne
                // ferait qu'ajouter un ordre de tir à raisonner.
                if (deposeAuto && nom === "PutUnitIntoHand"
                    && typeof s.arg === "string" && s.arg !== "") {
                    retirerSiSurLePlateau(s.arg);
                }
            },
        });
        faits.push(nom);
    }
    return faits;
}

/** Détacher les chemins de bascule -- tous, ou seulement ceux nommés. Rend les noms ÔTÉS. */
function desarmerChemins(seulement?: readonly string[]): string[] {
    const faits: string[] = [];
    for (const nom of Object.keys(cheminsListeners)) {
        if (seulement !== undefined && !seulement.includes(nom)) continue;
        cheminsListeners[nom].detach();
        delete cheminsListeners[nom];
        faits.push(nom);
    }
    if (faits.length > 0) Interceptor.flush();
    return faits;
}

/** Le drapeau `_isMachinesOfWarSelection` d'une instance de HUD, ou `null` s'il est illisible. */
function lireDrapeauMoW(hud: NativePointer): boolean | null {
    try {
        const k = findClassAnywhere(NS_HUD, CLS_HUD);
        if (!k) return null;
        const off = getFieldOffset(k, "_isMachinesOfWarSelection");
        if (off < 0) return null;
        return hud.add(off).readU8() !== 0;
    } catch { return null; }
}

// ============================================================================
// LE PLAFOND DE POSE — pourquoi « je sélectionne mais je ne pose pas ».
//
// Mesuré sur le HUD vivant : `allUnitModels = 55`, `allUnlockedUnitModels = 49`,
// `disabledInput = false`, mais **`maxUnitsPossible = 0`**. Le verrou n'est donc PAS
// `IsUnlocked` (49 unités sont posables) : le HUD a reçu l'autorisation de poser ZÉRO unité.
//
// `IdunBattle.View.FSM.VisualBattleQuery$$MaxUnitsPossibleToStartBattle` calcule :
//
//     min( source.AmountOfUnlockedUnits(),
//          GetSpawnPointCoordinatedForHumanPlayer(this).Count,
//          source.MaxUnitsPossibleToStartBattle() )
//
// (slots d'interface 0x31 et 0x33, NOMMÉS par `classInterfaceSlots` — lus, pas dérivés.)
//
// Et `SandboxGameModeSource$$AmountOfUnlockedUnits` résout sur un corps `return 0;`
// **DÉDUPLIQUÉ, 1233 xrefs**, que Ghidra nomme `UnityAdsIdentifier$$get_UserId`. D'où
// `min(0, ...) = 0`.
//
// ⛔ ON N'ANCRE PAS CE CORPS. 1233 consommateurs basculeraient — c'est exactement le piège du
// §8. On ancre le RELAIS, qui est un vrai corps, et on remplace SON retour. Même forme que le
// forçage de phase, qui marche par la même raison.
// ⚠ LES DEUX BORNES, PAS SEULEMENT LE PLAFOND. `Show(units, min, max, options)` en reçoit
// DEUX, et `VisualBattleQuery` porte un relais pour chacune
// (`MaxUnitsPossibleToStartBattle`, `MinUnitsNeededToStartBattle`). Ne forcer que le max
// laisserait le HUD sur un intervalle décidé à moitié par la sandbox — et un `min` qui vaut
// autre chose que ce qu'on croit se lirait comme un refus de poser, exactement le symptôme
// qu'on vient de passer une heure à attribuer.
interface Borne {
    methode: string;
    listener: InvocationListener | null;
    impose: number | null;
    fires: number;
    obs: Array<{ rendu: number; impose: number | null }>;
}
const BORNES: Record<"max" | "min", Borne> = {
    max: { methode: "MaxUnitsPossibleToStartBattle",
           listener: null, impose: null, fires: 0, obs: [] },
    min: { methode: "MinUnitsNeededToStartBattle",
           listener: null, impose: null, fires: 0, obs: [] },
};

function armerBorne(b: Borne): true | Refus {
    if (b.listener) return true;
    const k = findClassAnywhere(NS_VBQ, CLS_VBQ);
    if (!k) return refus(`\`${NS_VBQ}.${CLS_VBQ}\` INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(k, b.methode, 0);
    if (!mi) return refus(`\`${CLS_VBQ}$$${b.methode}\` INTROUVABLE (0 paramètre)`);
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`${b.methode}\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus(`REFUS : \`${CLS_VBQ}$$${b.methode}\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${t.retA} ; tête = ${t.hex}) -- adresse PARTAGÉE par `
            + "déduplication. C'est précisément ce qu'on évite en visant le relais plutôt "
            + "que `AmountOfUnlockedUnits`. Cf. §8.");
    }
    b.listener = Interceptor.attach(mi.ptr, {
        onLeave(retval) {
            b.fires++;
            const rendu = retval.toInt32();
            if (b.impose !== null) retval.replace(ptr(b.impose));
            if (b.obs.length < 32) b.obs.push({ rendu, impose: b.impose });
        },
    });
    Interceptor.flush();
    return true;
}

/** Arme UNE délégation. Rend un refus NOMMÉ plutôt qu'un silence. */
function armerUneDelegation(
    d: Delegation, spec: { nom: string; params: number; valeurs?: boolean[] },
): true | Refus {
    // ⚠ DÉJÀ ARMÉE ≠ ARMÉE SUR LE BON PRÊTEUR, ET LES CONFONDRE PRODUIT UNE CONFUSION DE TYPE.
    //
    // Ce test était `if (d.listener) return true;` — un ré-armement demandant un AUTRE prêteur
    // ressortait donc VERT sans rien re-résoudre, et `d.miCampagne` restait la méthode de
    // l'ancien. Mesure du 2026-08-21, montage guild war après trois montages de campagne :
    // `preteurDelegation` valait bien `guildWar` et l'OBJET prêté était la source GW, mais la
    // MÉTHODE invoquée était `CampaignGameModeSource$$GetUnitsForDeploymentHUD` (`+0x511fe0`)
    // au lieu de `GuildWarsGameModeSource$$GetUnitsForDeploymentHUD` (`+0x520300`). On exécutait
    // donc du natif de campagne sur une disposition mémoire de guerre de guilde : le champ de
    // progression lu à l'offset de la campagne tombait sur l'`_onlineFeatureDecider` de l'objet
    // GW, d'où `MethodAccessException: ICampaignProgression.GetDeployableUnits on type
    // OnlineFeatureDecider` — et un écran de déploiement au roster VIDE.
    //
    // C'est exactement ce que `guildWarSourceBc` refuse par ailleurs (« invoquer dessus
    // exécuterait du natif sur une disposition mémoire étrangère ») : ici on le faisait.
    if (d.listener) {
        const voulu = sourcePreteuse().nom;
        if (d.preteurArme === voulu) return true;
        // Le prêteur a changé : on DÉPOSE et on re-résout. Un `detach` ici est sûr — on n'est
        // pas dans l'appel qu'on ancre, on arme.
        d.listener.detach();
        d.listener = null;
        d.miCampagne = null;
        d.ancrage = null;
    }

    const ks = findClassAnywhere(NS_SRC, CLS_SANDBOX);
    if (!ks) return refus(`${NS_SRC}.${CLS_SANDBOX} INTROUVABLE`);
    const ms = findMethodByParamCount(ks, spec.nom, spec.params);
    if (!ms) return refus(`\`${CLS_SANDBOX}$$${spec.nom}\` INTROUVABLE (${spec.params} param)`);

    // MÊME GARDE QUE PARTOUT AILLEURS DANS CE MODULE : un corps trivial est probablement
    // DÉDUPLIQUÉ, donc son adresse est PARTAGÉE, et s'y attacher basculerait N méthodes. Cf. §8.
    const tete = lireTete(ms.ptr);
    if (tete.erreur !== null) {
        return refus(`tête du corps de \`${spec.nom}\` ILLISIBLE (${tete.erreur})`);
    }
    // ⚠ L'EXCEPTION À CETTE GARDE, ET POURQUOI ELLE EST SÛRE.
    // `SandboxGameModeSource$$AmountOfUnlockedUnits` EST un corps trivial : `33 c0 c3`, soit
    // `xor eax,eax ; ret` -- il rend 0, et son adresse est partagée par toutes les méthodes du
    // binaire qui rendent 0. Refuser tout net rendait ce terme INATTEIGNABLE, et il est
    // précisément celui qui écrase les deux bornes du HUD (`SPMath.Min(0, 3, 5) = 0`).
    //
    // Ce qui rend l'ancrage dangereux, ce n'est pas le PARTAGE de l'adresse : c'est de répondre
    // à TOUS ceux qui y passent. On garde donc l'ancrage et on FILTRE SUR LA CLASSE DE `this` --
    // on ne substitue que quand l'appel vient bien d'une `SandboxGameModeSource`, et on laisse
    // le `0` natif à tous les autres. Le compteur `passesFiltre` publie la part réellement
    // substituée : si elle reste à 0 alors que `fires` monte, le filtre est trop étroit et ça
    // se VOIT, au lieu de se lire comme « la délégation ne sert à rien ».
    if (teteTriviale(tete) && !DELEGUEES_TRIVIALES_FILTREES.has(spec.nom)) {
        return refus(`REFUS : \`${CLS_SANDBOX}$$${spec.nom}\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${tete.retA} ; tête = ${tete.hex}) -- adresse probablement PARTAGÉE `
            + "par déduplication IL2CPP. Cf. case-10020 §8.");
    }
    const corpsPartage = teteTriviale(tete);

    // La méthode est résolue sur la classe du PRÊTEUR retenu, pas sur la campagne par défaut.
    //
    // ⚠ ET SUR SON NAMESPACE À LUI. `NS_SRC` était écrit en dur ici : trois prêteurs sur quatre
    // vivent bien dans `IdunBattle.ViewLogic.BattleSource`, mais pas `OnslaughtGameModeSource`
    // (cf. le pavé de `Preteur`). Mesuré le 2026-08-23 : les 4 délégations rendaient
    // `IdunBattle.ViewLogic.BattleSource.OnslaughtGameModeSource INTROUVABLE` — et
    // `deploymentPoolArmer` répondait pourtant `{ok: true, action: "arme"}`, parce que le détail
    // par méthode vit dans `rapport`, que l'appelant ne lit pas forcément. Un armement qui rend
    // `ok` sans rien avoir armé se lit comme un succès : c'est l'écran vide qui l'a démenti.
    const preteur = sourcePreteuse();
    const kc = findClassAnywhere(preteur.ns, preteur.cls);
    if (!kc) return refus(`${preteur.ns}.${preteur.cls} INTROUVABLE`);
    const mc = findMethodByParamCount(kc, spec.nom, spec.params);
    if (!mc) {
        return refus(`\`${preteur.cls}$$${spec.nom}\` INTROUVABLE (${spec.params} param) -- ce `
            + "prêteur ne porte pas cette méthode, donc il n'y a rien à quoi déléguer");
    }
    d.miCampagne = mc;
    d.preteurArme = preteur.nom;

    const nParams = spec.params;
    d.listener = Interceptor.attach(ms.ptr, {
        // Les arguments sont capturés à l'ENTRÉE : au `onLeave` ils ne sont plus lisibles.
        // `args[0]` est le `this` sandbox — on ne le transmet PAS, c'est tout l'objet de la
        // délégation : la vraie source répond avec SON état.
        onEnter(args) {
            // CORPS PARTAGÉ : on n'a le droit de répondre que pour la sandbox. La classe de
            // `this` est le seul discriminant disponible ici — l'adresse, elle, est commune à
            // toutes les méthodes déduplicées.
            (this as unknown as { pourNous: boolean }).pourNous = !corpsPartage || (() => {
                try {
                    const o = args[0];
                    if (o.isNull()) return false;
                    return s(class_get_name(o.readPointer()) as NativePointer) === CLS_SANDBOX;
                } catch { return false; }
            })();
            // Un paramètre de type VALEUR doit être RÉ-EMPAQUETÉ : on alloue et on écrit la
            // valeur, puis on transmet SON ADRESSE. Sans ça, `false` (le mot 0) part comme
            // pointeur nul -- cf. le bloc `valeurs` sur `DELEGUEES`.
            const bruts = nParams >= 1 ? [args[1], args[2]].slice(0, nParams) : [];
            (this as unknown as { argv: NativePointer[] }).argv = bruts.map((a, i) => {
                if (!spec.valeurs || !spec.valeurs[i]) return a;
                const cell = Memory.alloc(8);
                cell.writePointer(a);          // conserve les 8 octets tels quels
                return cell;
            });
        },
        onLeave(retval) {
            d.fires++;
            // Sur un corps partagé, tout ce qui n'est pas la sandbox repart avec sa valeur
            // native. `fires` compte quand même : l'écart `fires - passesFiltre` DIT combien
            // d'appels étrangers traversent, donc si le filtre est au bon endroit.
            if (!(this as unknown as { pourNous: boolean }).pourNous) return;
            d.passesFiltre++;
            const p = sourcePreteuse();
            const src = p.ptr;
            if (src === null || src.isNull()) {
                d.dernier = { ok: false, detail: `aucune source \`${p.cls}\` (prêteur `
                    + `${p.nom}) -- pour la campagne : amorce non joué ou session froide ; pour `
                    + "le guild boss : `guildBossSourceForger` n'a pas été appelé ; pour le "
                    + "guild war : `guildWarSourceForger` n'a pas été appelé. "
                    + "RIEN SUBSTITUÉ." };
                return;
            }
            // PRÉ-EMPRUNT : la valeur a été calculée HORS de tout hook, donc l'ancrage sur
            // `GetDeployableUnits` a pu la voir — et le masque `sansFiltre` a pu agir. Ici on
            // ne fait plus que la poser. C'est la seule forme qui permette de modifier
            // l'appel emprunté (cf. §24 : un `Interceptor` est aveugle aux appels imbriqués).
            // GUILD BOSS : on ré-emprunte FRAIS, jamais la valeur figée -- une `PooledList`
            // consommée par un premier `Show` revient VIDE au retry (cf. `rosterFraisGuildBoss`).
            if (spec.nom === METHODE && p.nom === "guildBoss") {
                const frais = rosterFraisGuildBoss();
                if (frais === null) {
                    d.dernier = { ok: false, detail: "ré-emprunt guild boss ÉCHOUÉ -- rien "
                        + "substitué (mieux vaut le roster natif qu'une liste recyclée)" };
                    return;
                }
                retval.replace(frais);
                d.emprunts++;
                d.dernier = { ok: true, detail: `ré-emprunt FRAIS -> ${frais}` };
                return;
            }
            // GUILD WAR : ON NE SUBSTITUE PLUS LE RETOUR — ON REMPLIT CELUI DU JEU.
            //
            // ⚠ POURQUOI, ET CE QUE LA SUBSTITUTION COÛTAIT. `GetUnitsForDeploymentHUD` rend un
            // `PooledList<System.String>`, TYPE VALEUR d'UN SEUL champ
            // (`_listWithStatus : PooledListElement<T>`, mesuré par `classFields`). La version
            // précédente déboxait le retour de `runtime_invoke` (`+0x10`) et le posait dans
            // `retval` — le roster S'AFFICHAIT (0 -> 125 modèles), donc ça passait pour juste.
            // Ça ne l'était pas : la liste que la source SANDBOX venait de louer
            // (`DictionaryPooler.Get`) n'était jamais rendue, et l'appelant disposait la NÔTRE,
            // louée dans un autre pool par le `ConvertAll` de
            // `GuildWarsGameModeSource$$GetUnitsForDeploymentHUD`. La comptabilité du pool
            // (`PooledElement.IsPooled`) partait de travers, et le `Dispose` de l'appelant levait
            //
            //     MethodAccessException: 'IPoolableObject.BeforeReturnToPoolAttempt'
            //                            on type 'PooledList<System.String>'
            //
            // ⚠ ET CETTE EXCEPTION TUAIT LA BATAILLE EN SILENCE. Capturée le 2026-08-19 dans
            // `IdunBattle.View.Game.IdunGameViews$$Enable+0xf1` (pile :
            // `IdunMainView$$Start` -> `BattleAndEditorFlowController$$LoadBattle` ->
            // `IdunMainView$$StartBattle`), donc AU CHARGEMENT, avant le premier clic.
            // `IdunGameViews$$HandleException` pose alors `_isLogicPausedFromException`, qu'AUCUN
            // `ContinueLogicFromException` ne retire, et `QueueComputerActions` exige ce drapeau à
            // zéro : l'IA adverse n'était plus JAMAIS lancée. Ni popup, ni log (`_errorListeners`
            // est vide). Contre-épreuve : même montage sans cette délégation -> aucune exception,
            // aucun verrou. Sonde : `vueExceptionArmer`. Détail : `docs/rl/case-10038-*.md`.
            //
            // CE QU'ON FAIT À LA PLACE : on emprunte UNE SEULE FOIS pour LIRE les ids (chaînes
            // JS, mises en cache), puis on remplit la liste que le jeu a déjà louée. Plus aucun
            // objet mis en pool ne traverse la frontière, et le cycle de location reste au jeu.
            //
            // ⚠ CETTE BRANCHE SERT DEUX PRÊTEURS, ET C'EST UNE MESURE, PAS UNE COMMODITÉ.
            // `GuildWarsGameModeSource$$GetUnitsForDeploymentHUD` et
            // `OnslaughtGameModeSource$$GetUnitsForDeploymentHUD` ont la MÊME signature (0
            // paramètre) et le MÊME retour (`PooledList<System.String>`, un type valeur). Le
            // traitement est donc identique — mais chacun garde SON cache : partager la case
            // ferait servir le roster de l'autre mode après un changement de prêteur, avec un
            // contenu parfaitement plausible et faux.
            if (spec.nom === METHODE && (p.nom === "guildWar" || p.nom === "onslaught")) {
                const quoi = p.nom === "onslaught" ? "onslaught" : "guild war";
                if (cacheRoster(p.nom) === null) {
                    let b: NativePointer;
                    try { b = invokeMethod(mc.info, src, []) as NativePointer; }
                    catch (e) {
                        d.dernier = { ok: false,
                            detail: `lecture du roster ${quoi} a levé : ` + (e as Error).message };
                        return;
                    }
                    if (b === null || b.isNull()) {
                        d.dernier = { ok: false, detail: `la source ${quoi} a rendu NUL` };
                        return;
                    }
                    gcRoot.add(b);
                    try {
                        // La boîte porte la structure à `+0x10` ; son unique champ est le wrapper
                        // de pool, dont `_object` (résolu PAR NOM) est la `List<String>`.
                        poserCacheRoster(p.nom, idsDePooledElement(b.add(0x10).readPointer()));
                    } catch (e) {
                        d.dernier = { ok: false,
                            detail: `roster ${quoi} illisible : ` + (e as Error).message };
                        return;
                    }
                }
                const ids = cacheRoster(p.nom);
                if (ids === null || ids.length === 0) {
                    // « je n'ai pas su lire » et « c'est vide » se disent, ils ne se rabattent pas
                    // sur un roster natif silencieusement faux.
                    d.dernier = { ok: false, detail: `roster ${quoi} `
                        + (ids === null ? "ILLISIBLE" : "VIDE")
                        + " -- rien écrit, le retour natif est laissé INTACT" };
                    poserCacheRoster(p.nom, null);  // relire au prochain tir, ne pas figer l'échec
                    return;
                }
                const r = remplir(retval, ids);
                d.emprunts++;
                d.dernier = { ok: r.erreur === null,
                    detail: r.erreur === null
                        ? `${quoi} REMPLI ${r.ajoutes}/${ids.length} (${r.voie})`
                        : `remplissage ${quoi} : ${r.erreur}` };
                return;   // ⚠ `retval` INTACT — c'est tout l'objet du correctif.
            }
            // CAMPAGNE : MÊME REMÈDE QUE LE GUILD WAR — on REMPLIT la liste du jeu.
            //
            // ⚠ DEUX DÉFAUTS TOMBAIENT ICI, ET LE PREMIER SUFFISAIT À VIDER L'ÉCRAN.
            // Mesuré le 2026-08-20 sur `elite4` nœud 31 : la délégation TIRAIT et EMPRUNTAIT
            // (`fires=1 emprunts=1`, `dernier.ok` VRAI) et le roster restait VIDE. Sans
            // pré-emprunt, le chemin GÉNÉRIQUE d'en dessous posait dans `retval` le retour BRUT
            // de `runtime_invoke` — or `PooledList<System.String>` est un TYPE VALEUR, donc ce
            // retour est une BOÎTE. Le HUD lisait `_listWithStatus` sur un en-tête d'objet.
            // C'est le prix du chemin générique : il est juste pour un type RÉFÉRENCE (les
            // trois autres déléguées) et faux pour celui-ci, sans que rien ne le signale.
            //
            // Second défaut, celui du PRÉ-EMPRUNT lui-même : une `PooledList` NE SE SUBSTITUE
            // QU'UNE FOIS (cf. `rosterFraisGuildBoss`), et un objet mis en pool qui traverse la
            // frontière fait lever `BeforeReturnToPoolAttempt` au `Dispose` de l'appelant — ce
            // qui TUE la bataille EN SILENCE (cf. la branche `guildWar`). Le remplissage règle
            // les deux d'un coup : rien ne traverse, et la liste remplie est celle du jeu.
            if (spec.nom === METHODE && p.nom === "campagne") {
                if (idsCampagne === null) {
                    // LE PRÉ-EMPRUNT RESTE PRIORITAIRE, MAIS ON LE **LIT** AU LIEU DE LE POSER :
                    // c'est la seule valeur empruntée HORS hook, donc la seule sur laquelle le
                    // masque `sansFiltre` a pu agir (cf. §24 — un `Interceptor` est aveugle aux
                    // appels imbriqués). Le lever de filtre de nœud survit donc au correctif.
                    if (preEmprunt !== null) {
                        try { idsCampagne = idsDePooledElement(preEmprunt); }
                        catch (e) {
                            d.dernier = { ok: false, detail: "pré-emprunt campagne ILLISIBLE : "
                                + (e as Error).message + " -- rien écrit" };
                            return;
                        }
                    } else {
                        let b: NativePointer;
                        try { b = invokeMethod(mc.info, src, []) as NativePointer; }
                        catch (e) {
                            d.dernier = { ok: false, detail: "lecture du roster campagne a levé : "
                                + (e as Error).message };
                            return;
                        }
                        if (b === null || b.isNull()) {
                            d.dernier = { ok: false, detail: "la source campagne a rendu NUL" };
                            return;
                        }
                        gcRoot.add(b);
                        try { idsCampagne = idsDePooledElement(b.add(0x10).readPointer()); }
                        catch (e) {
                            d.dernier = { ok: false, detail: "roster campagne illisible : "
                                + (e as Error).message };
                            return;
                        }
                    }
                }
                if (idsCampagne === null || idsCampagne.length === 0) {
                    d.dernier = { ok: false, detail: "roster campagne "
                        + (idsCampagne === null ? "ILLISIBLE" : "VIDE")
                        + " -- rien écrit, le retour natif est laissé INTACT" };
                    idsCampagne = null;   // relire au prochain tir plutôt que figer un échec
                    return;
                }
                const r = remplir(retval, idsCampagne);
                d.emprunts++;
                d.dernier = { ok: r.erreur === null,
                    detail: r.erreur === null
                        ? `campagne REMPLI ${r.ajoutes}/${idsCampagne.length} (${r.voie})`
                        : `remplissage campagne : ${r.erreur}` };
                return;   // ⚠ `retval` INTACT.
            }
            // LE LINEUP DE LA SOURCE EST UNE SAUVEGARDE — donc PÉRIMÉ dès que le joueur a touché
            // à son déploiement dans cette session.
            //
            // ⚠ MESURÉ le 2026-08-20 : au retry, l'écran revenait à la composition du dernier
            // essai RÉEL, pas à celle qu'on venait de poser. La cause n'est pas la délégation :
            // c'est que le jeu PERSISTE le lineup au démarrage d'une vraie partie
            // (`UnitProgressionData$$SetLineup`), et que la sandbox ne le fait jamais. La clé
            // `<campagne>_<index>` pointe donc toujours sur l'avant-dernier état.
            //
            // ⛔ ET ON N'ÉCRIRA PAS CETTE SAUVEGARDE. `SetLineup` touche les données du COMPTE
            // pour un essai qui n'en est pas un ; c'est exactement le genre d'écriture qui a
            // coûté un jeton. On règle le conflit dans l'autre sens : dès que notre mémoire
            // porte plus frais, on ne substitue RIEN et le tableau VIDE de la sandbox passe.
            // L'écran reste nu une fraction de seconde, puis `rejouerMemoire` y repose la
            // composition ET les cases, par l'étage FSM.
            //
            // ⚠ LA SOURCE RESTE LE FOURNISSEUR AU PREMIER MONTAGE, quand la mémoire est vide --
            // c'est là qu'elle a la seule vérité disponible.
            if (spec.nom === "GetBattleLineup" && memoirePoses.length > 0) {
                d.dernier = { ok: true, detail: "laissé au JEU (tableau vide) -- la mémoire porte "
                    + `${memoirePoses.length} pose(s), plus fraîches que la sauvegarde du compte` };
                return;
            }
            // LES BORNES : un `System.Int32` revient BOXÉ de `runtime_invoke`, et le générique
            // poserait la boîte. On DÉBALLE à `+0x10` et on remplace par la valeur elle-même.
            //
            // ⚠ ET ON VÉRIFIE QUE LE COMPTE EST PLAUSIBLE. Une adresse lue comme un entier donne
            // un nombre ÉNORME ou NÉGATIF ; un plafond absurde ferait un écran encore plus cassé
            // qu'un plafond nul, et sans rien dire. Hors bornes, on ne substitue pas.
            if (DELEGUEES_ENTIERES.has(spec.nom)) {
                let boite: NativePointer;
                try { boite = invokeMethod(mc.info, src, []) as NativePointer; }
                catch (e) {
                    d.dernier = { ok: false,
                        detail: `\`${spec.nom}\` a levé : ` + (e as Error).message };
                    return;
                }
                if (boite === null || boite.isNull()) {
                    d.dernier = { ok: false, detail: `\`${spec.nom}\` a rendu NUL` };
                    return;
                }
                const v = boite.add(0x10).readS32();
                if (v < 0 || v > 64) {
                    d.dernier = { ok: false, detail: `\`${spec.nom}\` = ${v} : hors de toute `
                        + "borne plausible (0..64) -- le déballage est probablement faux, RIEN "
                        + "SUBSTITUÉ plutôt qu'un plafond absurde" };
                    return;
                }
                retval.replace(ptr(v));
                d.emprunts++;
                d.dernier = { ok: true, detail: `${spec.nom} = ${v} (déballé de la boîte)` };
                return;
            }
            // ⚠ LE CHEMIN GÉNÉRIQUE NE DOIT PLUS VOIR `METHODE`. Les quatre prêteurs ont leur
            // branche ; s'il en apparaît un cinquième, il tomberait ici et re-poserait une BOÎTE
            // dans `retval` — le défaut qu'on vient de corriger. On REFUSE plutôt que de le
            // rejouer en silence.
            if (spec.nom === METHODE) {
                d.dernier = { ok: false, detail: `prêteur \`${p.nom}\` sans branche pour `
                    + `\`${METHODE}\` : le retour est un TYPE VALEUR, le chemin générique `
                    + "poserait une BOÎTE. RIEN SUBSTITUÉ." };
                return;
            }
            try {
                const argv = (this as unknown as { argv: NativePointer[] }).argv ?? [];
                // Fenêtre de l'emprunt : c'est la SEULE pendant laquelle `sansFiltre` agit.
                // Hors d'elle, `GetDeployableUnits` sert les écrans méta du jeu.
                dansEmprunt = true;
                let r: NativePointer;
                try { r = invokeMethod(mc.info, src, argv) as NativePointer; }
                finally { dansEmprunt = false; }
                if (r === null || r.isNull()) {
                    d.dernier = { ok: false,
                        detail: "la vraie source a rendu NUL -- rien substitué" };
                    return;
                }
                retval.replace(r);
                d.emprunts++;
                d.dernier = { ok: true, detail: `délégué à ${src} -> ${r}` };
            } catch (e) {
                d.dernier = { ok: false, detail: "la délégation a levé : " + (e as Error).message };
            }
        },
    });
    d.ancrage = { sandbox: ghidraVA(ms.ptr), campagne: ghidraVA(mc.ptr), tete };
    return true;
}

// ============================================================================
// L'ÉTAGE PREFAB — ET LE CHARGEMENT « À LA DEMANDE » EXISTE DÉJÀ DANS LE JEU.
//
// Symptôme : on sélectionne une unité du roster, elle se GRISE (`TryMarkUnitAsPlaced` rend
// `true`), et le plateau ne bouge pas. `IdunGameViews$$AddPlaceholderUnit` sort en `false` sur
// `UnitIdToPrefabDictionary$$Get` -> `NullableRefExtensions$$TryGet` -> `false`.
//
// CE QUE `Get` FAIT VRAIMENT, et c'est le fait qui commande tout ce bloc :
//
//     ref = dico[GetUnitIdForUniverse(unitId)]      // AssetBundleBattleReference
//     si ref.prefab == null :                       // <-- LE CHARGEMENT PARESSEUX
//         ref.prefab = ref.loader.Invoke()          //     EST DÉJÀ LÀ, dans le jeu
//     return NullableRefUnity(ref.prefab)
//
// ⇒ Il n'y a donc RIEN à charger : il y a une ENTRÉE à créer. Le prefab sera tiré par le jeu
// lui-même, au premier `Get`, exactement là où il le tire pour les unités de `bc.Units`. On
// ne déclenche aucun chargement de bundle depuis un thread Frida — ce qui écarte au passage
// le profil de gel qu'on redoutait.
//
// POURQUOI L'ENTRÉE MANQUE. `UnitIdToPrefabDictionary$$Add` n'a qu'UN SEUL appelant :
// `idun.IdunMainView$$StartBattle`, qui itère `BattleConfiguration.Units`. Notre roster est
// EMPRUNTÉ à la campagne et n'est dans aucune BC — il ne pouvait donc pas avoir de prefab.
//
// LA SÉQUENCE NATIVE, mirroir 1:1 de `StartBattle` :
//
//     holder = new <classe porteuse>()                    // { visualConfig, effectPool }
//     holder.effectPool = thor.Game.Board.EffectPool$$GetInstance()
//     IdunUniverse$$TryGetUnitVisualConfig(univers, visualId, &holder.visualConfig)
//     del = new WidgetPoolReuseHelper.CreateWidget<T>(holder, <méthode du holder>)
//     ref = new AssetBundleBattleReference(del)
//     dico.Add(unitId, ref)
//
// ⚠ AUCUNE de ces classes n'est nommée ici, et c'est le cœur du dispositif. Ghidra ne les
// nomme pas non plus : le ctor d'`AssetBundleBattleReference` s'y appelle
// `UnityEngine.EventSystems.BaseEventData$$.ctor` (corps DÉDUPLIQUÉ — son absence de
// `methods.tsv` ne prouvait rien, cf. le CLAUDE.md), et la classe porteuse n'est qu'un `DAT_`.
// On CAPTURE donc un exemplaire VIVANT : `sandboxModeStart` fait tourner `StartBattle`, donc
// `Add` tire pour chaque unité de la BC. Le patron ainsi capturé porte les trois classes, le
// `m_target` du délégué et l'`EffectPool` — sans une seule adresse en dur, et re-capturé à
// chaque montage, donc insensible au changement de build.
//
// ⚠ ON CLONE, ON NE RECONSTRUIT PAS. Copier l'instance capturée puis n'écraser que le champ
// qui change préserve tout ce que le runtime a calculé (l'`invoke_impl` et le `method_code` du
// délégué, notamment) et évite d'invoquer trois ctors dont un prend un `IntPtr`. Le seul piège
// est en face : le `ref` capturé a SON prefab déjà résolu, donc le clone doit REMETTRE CE SLOT
// À NUL — sans quoi chaque unité ajoutée afficherait le modèle de l'unité capturée, et ça se
// verrait comme un bug de jeu, pas comme un bug de patron.
//
// ⚠ Les slots sont résolus PAR LE TYPE du champ (même doctrine que `bucket-decode`), jamais par
// un offset écrit ici, et le diagnostic PUBLIE le nom réellement trouvé pour que la péremption
// se voie.

const NS_PREFAB = "IdunBattle.View.Game";
const CLS_DICO = "UnitIdToPrefabDictionary";
const CLS_VIEWS_PREFAB = "IdunGameViews";

interface Champ { nom: string; off: number; type: string }

/** Champs d'instance d'une classe, avec le NOM DE TYPE — la clé de la résolution par type. */
function champsDe(klass: NativePointer): Champ[] {
    const out: Champ[] = [];
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        let type = "?";
        try {
            const t = field_get_type(f) as NativePointer;
            const k = type_get_class_or_element_class(t) as NativePointer;
            if (!k.isNull()) type = s(class_get_name(k) as NativePointer);
        } catch { /* type illisible : le champ reste listé, avec `?` */ }
        try {
            out.push({ nom: s(field_get_name(f) as NativePointer),
                       off: field_get_offset(f) as number, type });
        } catch { /* champ illisible : on continue plutôt que de tout perdre */ }
    }
    return out;
}

/** Le premier champ dont le type porte `type`. Rend `-1` si absent — jamais un offset deviné. */
function offsetParType(champs: Champ[], type: string): number {
    const c = champs.find((x) => x.type === type);
    return c ? c.off : -1;
}

/** Ce qu'un `Add` VIVANT nous a appris. Tout est capturé, rien n'est écrit en dur. */
interface Patron {
    dico: string;
    refClasse: NativePointer; refClasseNom: string;
    offPrefab: number; nomPrefab: string;
    offLoader: number; nomLoader: string;
    delClasse: NativePointer; delClasseNom: string;
    offTarget: number;
    /** ⚠ LE SLOT QUE `Get` LIT VRAIMENT. Le décompilé invoque le loader par
     *  `invoke_impl(delegue->method_code, &retour, delegue->method)` — donc `method_code`,
     *  PAS `m_target`. Ne réécrire que `m_target` laisse le délégué cloné pointer sur la
     *  fermeture DU PATRON : mesuré, deux unités distinctes se sont affichées avec le modèle du
     *  patron, sans la moindre erreur. Les deux champs sont donc écrits, et relus. */
    offMethodCode: number;
    holderClasse: NativePointer; holderClasseNom: string;
    offConfig: number; nomConfig: string;
    /** TOUS les champs du porteur. Publiés : c'est en choisissant le champ « par élimination »
     *  qu'on a écrit la config dans le mauvais slot, et que deux unités distinctes se sont
     *  affichées avec le modèle du patron. Le slot se choisit désormais par le TYPE RÉEL de la
     *  config, à l'écriture — pas par une devinette à la capture. */
    champsHolder: Champ[];
    /** Le corps que le délégué appelle : c'est LUI qui fabrique le prefab. Lu sur le délégué
     *  capturé (`method_ptr`, champ NOMMÉ de `System.Delegate`), donc jamais une adresse écrite. */
    loaderPtr: NativePointer | null;
    /** ⚠ CE QUE `Delegate..ctor` ATTEND, et ce n'est PAS `method_ptr`. En IL2CPP, `ldftn` rend un
     *  `MethodInfo*` déguisé en `IntPtr` : le second argument du ctor est donc le champ `method`
     *  (+0x28), pas le pointeur de code (+0x10). Lui passer le code construit un délégué dont
     *  l'invocateur part sur une sentinelle — mesuré : « access violation accessing
     *  0xffffffffffffffff ». */
    loaderMethodInfo: NativePointer | null;
    tailleRef: number; tailleDel: number; tailleHolder: number;
    exemplaireRef: NativePointer; exemplaireDel: NativePointer; exemplaireHolder: NativePointer;
    unitIdVu: string | null;
}

let patron: Patron | null = null;
let patronRefus: string | null = null;
let listenerAdd: InvocationListener | null = null;
let addFires = 0;
const prefabCharges: Array<{ unitId: string; ok: boolean; detail: string }> = [];

// ⚠ LES POINTEURS QUE LE JEU UTILISE VRAIMENT — la seule autorité.
//
// Mesuré session 52 : `HasPrefabForUnitId` rend `true` pour `spaceBlackmane` alors que le `Get`
// du jeu rend NUL pour la même unité. Or les deux corps font le MÊME `ContainsKey`, sur le MÊME
// champ, avec la MÊME clé — sur une seule et même instance ils ne PEUVENT pas diverger. Donc ils
// portent sur DEUX objets différents, et c'est ma lecture qui visait le mauvais.
//
// La cause est la voie d'accès : aller CHERCHER la vue (`FindObjectsByType`, ou le dernier `this`
// vu par le pump) rend *une* vue, pas *celle que le déploiement utilise*. On enregistre donc les
// pointeurs tels qu'ils passent dans les appels du jeu, et tout le reste s'y adosse.
const dicosVusParAdd = new Map<string, number>();
/** Les unitIds que `Add` a inscrits — donc ceux dont le prefab EXISTE, sans rien fabriquer. */
const idsAvecPrefab: string[] = [];
let dicoDeGet: NativePointer | null = null;     // le `this` du dernier `Get` -- l'AUTORITÉ
let vuesDePose: NativePointer | null = null;    // le `this` d'`Enable` / `AddPlaceholderUnit`
let listenerVue: InvocationListener | null = null;
const listenersVue: InvocationListener[] = [];

// --- CAPTEUR PUR sur `IdunBattle.Runner.IdunRunner$$StartMatch` -------------------------------
// Deux questions d'un coup, et AUCUNE écriture :
//   QUAND  -- `showsAvant` compte les affichages du HUD de déploiement déjà survenus. Tirer à
//             `showsAvant == 0` = au MONTAGE ; à `showsAvant >= 1` = APRÈS l'écran, donc au clic.
//             Un compteur d'ordre répond mieux qu'une horloge : rien à interpréter.
//   SUR QUI -- `runner` est le `this` de l'appel, comparé au runner publié par le pump. Égaux
//             ⇒ UN SEUL runner (chargé puis démarré). Différents ⇒ il y en a bien deux.
let showFires = 0;
let showEnters = 0;
/** Les tirs de `ClearWidgets` — LE seul vidangeur de `_allUnitModels` et de `_currentlyPlacedUnits`.
 *  Deux appelants au binaire : `UnitDeploymentHud$$Show` (en tête, avant son remplissage) et
 *  `IdunMainView$$EndBattleAndGoToMeta`. Compter les tirs et les confronter aux entrées de `Show`
 *  DÉSIGNE lequel a vidé : un tir sans entrée de `Show` vient de la sortie de bataille. */
let vidangeFires = 0;
const vidangeTrace: Array<Record<string, unknown>> = [];
let listenerVidange: InvocationListener | null = null;
/** L'ancrage sur `Dictionary.Clear`, armé À LA DEMANDE et filtré par pointeur (cf.
 *  `deploymentVidangeArmer`). Les cibles sont relevées à l'armement : ce sont les dictionnaires
 *  VIVANTS du HUD, pas des offsets — si l'un est remplacé par un autre objet, il sort du filtre,
 *  et c'est un RÉSULTAT (le vidage serait alors une RÉAFFECTATION de champ, pas un `Clear`). */
let listenerDictClear: InvocationListener | null = null;
const ciblesVidange: Array<{ nom: string; ptr: NativePointer }> = [];
const dictClearTrace: Array<Record<string, unknown>> = [];
/** L'ancrage sur le lanceur de jet IL2CPP (`deploymentJetArmer`). Global, donc armé/désarmé
 *  autour d'UNE mesure. */
let listenerJet: InvocationListener | null = null;
let jetFires = 0;
const jetTrace: Array<Record<string, unknown>> = [];
/** L'ancrage sur `UnitDeploymentState$$StartBattle` — le point qui coupe l'espace de recherche
 *  en deux (`deploymentStartTracer`). Une entrée SANS sortie est la signature d'une levée dans
 *  ce corps ou dessous ; aucune entrée dit que la levée est en amont. */
let listenerStartBattle: InvocationListener | null = null;
/** L'ancrage sur UnitDeploymentHudButtons\$\$UpdateState -- le compteur que le BOUTON affiche. */
let listenerBoutons: InvocationListener | null = null;
const compteurBoutonTrace: Array<Record<string, unknown>> = [];
/** Les ancrages des quatre etages sous StartBattle (cf. deploymentStartTracer). */
const listenersEtages: InvocationListener[] = [];
const startBattleTrace: Array<Record<string, unknown>> = [];
/** `true` entre l'entrée et la sortie de `Show`. Même thread, donc c'est EXACT — là où une
 *  soustraction de compteurs ne l'est pas (un `Show` qui lève ne sort jamais). */
let dansShow = false;
let listenerRunnerStart: InvocationListener | null = null;
const startMatchTrace: Array<Record<string, unknown>> = [];

function armerRunnerStart(): true | Refus {
    if (listenerRunnerStart) return true;
    const kr = findClassAnywhere("IdunBattle.Runner", "IdunRunner");
    const mi = kr ? findMethodByParamCount(kr, "StartMatch", 0) : null;
    if (!mi) return refus("`IdunBattle.Runner.IdunRunner$$StartMatch` INTROUVABLE (0 paramètre)");
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`StartMatch\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus("REFUS : `IdunRunner$$StartMatch` résout sur un corps TRIVIAL (ret à "
            + `l'octet ${t.retA}) -- adresse PARTAGÉE par déduplication, s'y attacher `
            + "basculerait N méthodes");
    }
    listenerRunnerStart = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            // ⛔ Lecture pure : un `toString()` et des compteurs JS. Aucun natif invoqué.
            if (startMatchTrace.length >= 16) return;
            const vivant = state.liveRunner;
            startMatchTrace.push({
                ordre: startMatchTrace.length + 1,
                showsAvant: showFires,
                quand: showFires === 0 ? "AU MONTAGE (avant tout écran de déploiement)"
                                       : "APRES l'écran de déploiement (donc au clic START)",
                runner: args[0].toString(),
                runnerVivantDuPump: vivant === null ? null : vivant.toString(),
                memeRunner: vivant === null ? null : vivant.equals(args[0]),
            });
        },
    });
    Interceptor.flush();
    return true;
}
/** Ce qu'a donné chaque tentative de capture de la vue. Publié — jamais avalé. */
const captureVue: string[] = [];

/**
 * Le dictionnaire ET la vue que LE JEU utilise pour le déploiement.
 *
 * ⚠ ORDRE DE PRÉFÉRENCE, et il n'est pas cosmétique : on prend d'abord ce qu'on a VU PASSER dans
 * les appels du jeu (`Get`, `AddPlaceholderUnit`), puis seulement à défaut une vue qu'on va
 * chercher. C'est exactement l'erreur qui a produit la contradiction `HasPrefabForUnitId=true` /
 * `Get=NUL` : une vue trouvée n'est pas la vue employée. La SOURCE est publiée à chaque appel,
 * pour qu'un résultat obtenu par le repli ne se lise jamais comme un résultat autoritaire.
 */
function dicoVivant(): { dico: NativePointer; vues: NativePointer; source: string } | Refus {
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    if (!kv) return refus(`\`${NS_PREFAB}.${CLS_VIEWS_PREFAB}\` INTROUVABLE`);
    const off = offsetParType(champsDe(kv), CLS_DICO);
    if (off < 0) {
        return refus(`aucun champ de type \`${CLS_DICO}\` sur \`${CLS_VIEWS_PREFAB}\` -- `
            + "chemin PÉRIMÉ, pas de repli sur un offset");
    }
    // (1) L'AUTORITÉ : la vue sur laquelle le jeu vient d'appeler `AddPlaceholderUnit`.
    if (vuesDePose !== null && !vuesDePose.isNull()) {
        const dico = vuesDePose.add(off).readPointer();
        if (!dico.isNull()) {
            return { dico, vues: vuesDePose, source: "vue OBSERVÉE dans `AddPlaceholderUnit`" };
        }
    }
    // (2) Le dictionnaire vu dans `Get` : autoritaire lui aussi, mais il ne donne pas la vue,
    // donc il ne suffit pas pour `GetUnitVisualConfig`.
    if (dicoDeGet !== null && !dicoDeGet.isNull() && vuesDePose === null) {
        return refus("le dictionnaire du jeu est connu (" + dicoDeGet
            + ") mais AUCUNE vue n'a encore été observée : `GetUnitVisualConfig` a besoin de la "
            + "vue. Tenter une pose d'abord (elle échouera, et elle publiera la vue).");
    }
    // (3) Repli : une vue qu'on va chercher. Peut viser à côté -- on le DIT.
    const trouve = premiereInstance(kv);
    if (!(trouve instanceof NativePointer)) return refus(trouve.error + " (repli)");
    if (trouve.isNull()) return refus("`FindObjectsByType` a rendu un pointeur NUL (repli)");
    const dico = trouve.add(off).readPointer();
    if (dico.isNull()) return refus("le champ dictionnaire est NUL sur la vue trouvée (repli)");
    return { dico, vues: trouve,
             source: "REPLI `FindObjectsByType` -- PAS forcément la vue du déploiement" };
}

/** Arme la CAPTURE du patron sur `Add`. Observation pure : n'écrit rien, ne remplace rien. */
function armerPrefab(): true | Refus {
    if (listenerAdd) return true;
    const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
    if (!kd) return refus(`\`${NS_PREFAB}.${CLS_DICO}\` INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(kd, "Add", 2);
    if (!mi) return refus(`\`${CLS_DICO}$$Add\` INTROUVABLE (2 paramètres)`);
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`Add\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus(`REFUS : \`${CLS_DICO}$$Add\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${t.retA}) -- adresse PARTAGÉE par déduplication. Cf. §8.`);
    }
    // La VUE, captée au montage plutôt qu'à la première pose. Le `this` de ces méthodes EST la
    // vue employée — donc autoritaire, au même titre que celui d'`AddPlaceholderUnit`, mais
    // disponible sans attendre un clic de l'utilisateur.
    //
    // ⚠ DEUX candidates, et le RÉSULTAT DE CHACUNE EST PUBLIÉ. La version précédente n'en tentait
    // qu'une et AVALAIT l'échec : le hook n'a pas tiré, `vuesDePose` est resté nul, et il a fallu
    // un aller-retour avec l'utilisateur pour découvrir que le capteur n'était pas armé. Un
    // capteur qui échoue en silence coûte plus cher que pas de capteur du tout.
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    if (!listenerVue && kv) {
        // ⚠ DEUX CORRECTIFS ICI, ET LE SECOND EST CELUI QUI COMPTE.
        //
        // (1) L'affectation était CONDITIONNELLE (`if (vuesDePose === null)`) : un verrou. Une
        //     fois posée, elle ne suivait plus jamais.
        // (2) L'armement s'ARRÊTAIT AU PREMIER trouvé — `Continue` — qui ne tire PAS d'une
        //     bataille à l'autre. Corriger (1) seul ne changeait donc RIEN : mesuré, second
        //     montage encore à `total=0` avec le pointeur figé pendant 12 s.
        //
        // On en arme donc PLUSIEURS. `Initialize` tire à chaque mise en place de plateau ;
        // `AddUnit` est l'autorité absolue, puisque l'objet qui la reçoit EST celui qui porte
        // les vues qu'on compte ensuite.
        //
        // ⚠ Le symptôme était MUET et TROMPEUR : `0 unité` se lit « plateau vide » alors que
        // l'écran montrait les unités. C'est l'observation de l'utilisateur qui a tranché,
        // pas mes chiffres.
        for (const [nom, np] of
             [["Initialize", 2], ["AddUnit", 7], ["Continue", 0], ["Enable", 1]] as const) {
            const mv = findMethodByParamCount(kv, nom, np);
            if (!mv) { captureVue.push(`${nom}(${np}) : INTROUVABLE`); continue; }
            const tv = lireTete(mv.ptr);
            if (tv.erreur !== null) { captureVue.push(`${nom} : tête ILLISIBLE`); continue; }
            if (teteTriviale(tv)) { captureVue.push(`${nom} : corps TRIVIAL, refusé`); continue; }
            listenersVue.push(Interceptor.attach(mv.ptr, {
                onEnter(args) { if (!args[0].isNull()) vuesDePose = args[0]; },
            }));
            captureVue.push(`${nom} : ARMÉ`);
        }
        listenerVue = listenersVue.length > 0 ? listenersVue[0] : null;
        if (listenersVue.length === 0) captureVue.push("AUCUN capteur de vue armé -- `vuesDePose` "
            + "ne suivra PAS les changements de bataille");
    }
    listenerAdd = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            addFires++;
            // QUEL dictionnaire a été rempli, et combien de fois chacun. C'est ce comptage qui
            // distingue « 68 prefabs chargés » de « 68 prefabs chargés AILLEURS ».
            const cle = args[0].toString();
            dicosVusParAdd.set(cle, (dicosVusParAdd.get(cle) ?? 0) + 1);
            // LES IDS QUI ONT UN PREFAB, par construction : ce sont ceux que le jeu vient de
            // charger. C'est la bonne source pour le roster -- inutile d'en fabriquer d'autres.
            try {
                const nom = readIl2cppString(args[1]);
                if (nom !== null && nom !== "" && idsAvecPrefab.indexOf(nom) < 0) {
                    idsAvecPrefab.push(nom);
                }
            } catch { /* best effort */ }
            if (patron !== null) return;          // un seul patron suffit
            try { patronRefus = capturerPatron(args[0], args[1], args[2]); }
            catch (e) { patronRefus = "capture levée : " + (e as Error).message; }
        },
    });
    Interceptor.flush();
    return true;
}

/**
 * Booléen rendu par `invokeMethod`. **À N'OUBLIER SOUS AUCUN PRÉTEXTE.**
 *
 * `il2cpp_runtime_invoke` BOXE les retours de type valeur : le pointeur rendu désigne une boîte
 * managée, et le `Boolean` vit à `+0x10`. Lire `retour.toInt32()` lit les 32 bits BAS DU
 * POINTEUR — quasi jamais nuls — donc rend **`true` inconditionnellement**.
 *
 * Ce n'est pas une précaution théorique : c'est exactement la faute qui a fait répondre
 * `HasPrefabForUnitId = true` sur des unités ABSENTES du dictionnaire, réfuter à tort la bonne
 * cause, et faire dire à `deploymentPrefabCharger` « déjà présent -- rien fait » alors qu'il
 * n'avait rien créé. Un capteur qui ne peut rendre que `true` ne mesure rien.
 */
function boolBoxe(p: NativePointer): boolean {
    if (p.isNull()) return false;
    return p.add(0x10).readU8() !== 0;
}

/** Taille d'instance. `il2cpp_class_instance_size` peut manquer de l'export : on LÈVE avec le
 *  nom plutôt que de cloner sur une taille devinée — un clone tronqué laisserait des champs à
 *  zéro sans la moindre erreur. */
function taille(klass: NativePointer): number {
    if (class_instance_size === null) {
        throw new Error("`il2cpp_class_instance_size` absent de ce build : clonage IMPOSSIBLE");
    }
    return class_instance_size(klass) as number;
}

/** Décortique un `Add` réel. Rend `null` si le patron est complet, sinon la RAISON du refus. */
function capturerPatron(dico: NativePointer, unitId: NativePointer,
                        ref: NativePointer): string | null {
    if (ref.isNull()) return "la référence passée à `Add` est NULLE";
    const kRef = ref.readPointer();
    const nomRef = s(class_get_name(kRef) as NativePointer);
    const champsRef = champsDe(kRef);
    // Le prefab est le champ `GameObject` ; le loader est le SEUL autre champ référence.
    const offPrefab = offsetParType(champsRef, "GameObject");
    if (offPrefab < 0) {
        return `aucun champ de type \`GameObject\` sur \`${nomRef}\` -- champs vus : `
            + champsRef.map((c) => `${c.nom}:${c.type}`).join(", ");
    }
    const cLoader = champsRef.find((c) => c.off !== offPrefab && c.type !== "?");
    if (!cLoader) return `aucun champ loader identifiable sur \`${nomRef}\``;
    const del = ref.add(cLoader.off).readPointer();
    if (del.isNull()) return "le champ loader est NUL sur l'exemplaire capturé";
    const kDel = del.readPointer();
    const nomDel = s(class_get_name(kDel) as NativePointer);
    // `m_target` est un champ NOMMÉ de `System.Delegate` : on le résout par son nom, pas par
    // la disposition supposée d'`Il2CppDelegate`.
    const offTarget = getFieldOffset(kDel, "m_target");
    if (offTarget < 0) return `\`m_target\` absent de \`${nomDel}\``;
    const holder = del.add(offTarget).readPointer();
    if (holder.isNull()) return "le `m_target` du délégué capturé est NUL";
    const kHolder = holder.readPointer();
    const nomHolder = s(class_get_name(kHolder) as NativePointer);
    const champsHolder = champsDe(kHolder);
    // La config visuelle est ce que `TryGetUnitVisualConfig` écrit ; on la repère par le champ
    // dont le type n'est PAS le pool d'effets.
    const cConfig = champsHolder.find((c) => c.type.indexOf("EffectPool") < 0 && c.type !== "?");
    if (!cConfig) {
        return `aucun champ de config visuelle sur \`${nomHolder}\` -- champs vus : `
            + champsHolder.map((c) => `${c.nom}:${c.type}`).join(", ");
    }
    patron = {
        dico: dico.toString(),
        refClasse: kRef, refClasseNom: nomRef,
        offPrefab, nomPrefab: champsRef.find((c) => c.off === offPrefab)?.nom ?? "?",
        offLoader: cLoader.off, nomLoader: cLoader.nom,
        delClasse: kDel, delClasseNom: nomDel, offTarget,
        offMethodCode: getFieldOffset(kDel, "method_code"),
        holderClasse: kHolder, holderClasseNom: nomHolder,
        offConfig: cConfig.off, nomConfig: cConfig.nom, champsHolder,
        loaderPtr: (() => {
            const o = getFieldOffset(kDel, "method_ptr");
            if (o < 0) return null;
            const p = del.add(o).readPointer();
            return p.isNull() ? null : p;
        })(),
        loaderMethodInfo: (() => {
            const o = getFieldOffset(kDel, "method");
            if (o < 0) return null;
            const p = del.add(o).readPointer();
            return p.isNull() ? null : p;
        })(),
        tailleRef: taille(kRef), tailleDel: taille(kDel), tailleHolder: taille(kHolder),
        exemplaireRef: ref, exemplaireDel: del, exemplaireHolder: holder,
        unitIdVu: (() => { try { return readIl2cppString(unitId); } catch { return null; } })(),
    };
    // Le patron sert de gabarit BIEN APRÈS le `Add` qui l'a fourni : sans racine, le GC peut
    // ramasser les trois exemplaires entre la capture et la première fabrication.
    gcRoot.add(ref); gcRoot.add(del); gcRoot.add(holder);
    return null;
}

/** Clone une instance managée : même classe, mêmes octets, en-tête neuf. */
function cloner(source: NativePointer, klass: NativePointer, taille: number): NativePointer {
    const copie = il2cpp_object_new(klass) as NativePointer;
    if (copie.isNull()) throw new Error("`il2cpp_object_new` a rendu NUL");
    // L'en-tête (klass + monitor, 2 pointeurs) vient de l'allocation ; on ne copie QUE le corps.
    const debut = Process.pointerSize * 2;
    Memory.copy(copie.add(debut), source.add(debut), Math.max(0, taille - debut));
    return copie;
}

/**
 * Les ids du roster, lus dans la liste PRÉ-EMPRUNTÉE à la campagne.
 *
 * ⚠ POURQUOI C'EST NÉCESSAIRE, ET PAS UN CONFORT. Charger « les unités qu'on croit utiles »
 * fait porter à l'utilisateur la traduction portrait -> identifiant : il a cliqué
 * `admecMarshall` en pensant désigner un héros de la liste que j'avais chargée, et l'essai n'a
 * rien mesuré du tout. Un écran est utilisable quand TOUT ce qu'il montre est posable.
 *
 * La liste est un `PooledListElement\`1` : on descend dans `_object` (le `List\`1` réel), puis on
 * lit `_size` et `_items` PAR LEUR NOM. Aucun offset écrit ici.
 */
function listeDuRoster(): string[] | Refus {
    if (preEmprunt === null || preEmprunt.isNull()) {
        return refus("aucun pré-emprunt en main -- jouer `deploymentPoolPreEmprunt` d'abord");
    }
    try {
        const kWrap = preEmprunt.readPointer();
        let liste = preEmprunt;
        const offObj = getFieldOffset(kWrap, "_object");
        if (offObj > 0) {
            const interne = preEmprunt.add(offObj).readPointer();
            if (interne.isNull()) return refus("`_object` du wrapper de pool est NUL");
            liste = interne;
        }
        const kListe = liste.readPointer();
        const offItems = getFieldOffset(kListe, "_items");
        const offSize = getFieldOffset(kListe, "_size");
        if (offItems < 0 || offSize < 0) {
            return refus(`\`_items\`/\`_size\` absents de \`${s(class_get_name(kListe) as
                NativePointer)}\` -- chemin PÉRIMÉ`);
        }
        const n = liste.add(offSize).readS32();
        const items = liste.add(offItems).readPointer();
        if (items.isNull()) return refus("`_items` est NUL");
        if (n < 0 || n > 4096) return refus(`taille invraisemblable (${n}) -- on ne lit RIEN`);
        const out: string[] = [];
        // ⚠ LES ÉLÉMENTS NE SONT PAS FORCÉMENT DES CHAÎNES. `GetUnitsForDeploymentHUD` MAPPE la
        // liste : ses éléments sont des MODÈLES d'unité. `readIl2cppString` dessus ne rend rien,
        // et la première version rendait donc une liste VIDE -- que l'appelant a rapportée comme
        // « `tout` non demandé ». Un vide silencieux vaut pire qu'une erreur.
        let classeElement: string | null = null;
        let offId = -1;
        for (let i = 0; i < n; i++) {
            // Tableau managé : longueur à +0x18, premier élément à +0x20.
            const el = items.add(0x20 + i * Process.pointerSize).readPointer();
            if (el.isNull()) continue;
            const ke = el.readPointer();
            if (classeElement === null) {
                classeElement = s(class_get_name(ke) as NativePointer);
                if (classeElement !== "String") {
                    // L'id se trouve sur le modèle : champ String nommé, résolu PAR SON NOM.
                    for (const nom of ["unitId", "UnitId", "id", "Id",
                                       "<UnitId>k__BackingField", "<unitId>k__BackingField"]) {
                        const o = getFieldOffset(ke, nom);
                        if (o >= 0) { offId = o; break; }
                    }
                    if (offId < 0) {
                        return refus(`les éléments sont des \`${classeElement}\`, et aucun champ `
                            + "d'id n'y est reconnu -- champs : "
                            + champsDe(ke).map((c) => `${c.nom}:${c.type}`).join(", "));
                    }
                }
            }
            const v = classeElement === "String"
                ? readIl2cppString(el)
                : readIl2cppString(el.add(offId).readPointer());
            if (v !== null && v !== "") out.push(v);
        }
        if (out.length === 0) {
            return refus(`liste lue (taille ${n}, éléments \`${classeElement ?? "?"}\`) mais AUCUN `
                + "id extrait -- on refuse plutôt que de rendre un vide qui se lirait comme "
                + "« rien à charger »");
        }
        return out;
    } catch (e) { return refus("lecture du roster levée : " + (e as Error).message); }
}

/**
 * Fabrique l'entrée manquante d'UNE unité, sur le patron capturé. Rend le détail — jamais un
 * booléen nu : chaque refus doit se lire.
 *
 * ⚠ N'appelle AUCUN chargement d'asset. Elle pose un triplet PARESSEUX (`_prefab` à nul) ;
 * c'est le corps natif de `Get` qui invoquera le loader ensuite, exactement comme il le fait
 * pour les unités de la BC. Le coût reste donc proportionnel à ce qui est RÉELLEMENT posé.
 */
function fabriquerEntree(
    p: Patron, dico: NativePointer, vues: NativePointer, id: string,
    mHas: MethodRefLike, mAdd: MethodRefLike, mCfg: MethodRefLike,
): { ok: boolean; detail: string; ref?: NativePointer } {
    try {
        const sid = createManagedString(id);
        // `Add` LÈVE sur clé dupliquée : on ne tente que ce qui manque vraiment.
        if (boolBoxe(invokeMethod(mHas.info, dico, [sid]))) {
            return { ok: true, detail: "déjà présent -- rien fait" };
        }
        // Lecture pure (`UnitConfigMap.TryGetValue`), aucun asset touché.
        const cfg = invokeMethod(mCfg.info, vues, [sid]);
        if (cfg.isNull()) {
            return { ok: false, detail: "`GetUnitVisualConfig` rend NUL -- pas de config visuelle "
                + "dans l'univers chargé ; on n'invente rien" };
        }
        // LE SLOT SE CHOISIT PAR LE TYPE RÉEL DE `cfg`, pas par élimination. Mesuré : le choix
        // « le premier champ qui n'est pas l'EffectPool » visait un autre membre de la fermeture,
        // la config du patron restait en place, et DEUX unités s'affichaient avec SON modèle.
        const nomCfg = s(class_get_name(cfg.readPointer()) as NativePointer);
        const cible = p.champsHolder.find((c) => c.type === nomCfg);
        if (!cible) {
            return { ok: false, detail: `aucun champ de type \`${nomCfg}\` sur `
                + `\`${p.holderClasseNom}\` -- champs : `
                + p.champsHolder.map((c) => `${c.nom}:${c.type}`).join(", ")
                + " ; on n'écrit RIEN plutôt qu'à côté" };
        }
        if (p.loaderMethodInfo === null) {
            return { ok: false, detail: "`method` (le `MethodInfo*`) du délégué capturé "
                + "ILLISIBLE -- on ne construit pas de délégué sans lui" };
        }
        const ctorDel = findMethodByParamCount(p.delClasse, ".ctor", 2);
        if (!ctorDel) {
            return { ok: false, detail: `\`${p.delClasseNom}..ctor\` (2 paramètres) INTROUVABLE` };
        }
        const holder = cloner(p.exemplaireHolder, p.holderClasse, p.tailleHolder);
        holder.add(cible.off).writePointer(cfg);
        // RELECTURE : une écriture non vérifiée est ce qui a produit deux modèles identiques
        // sans la moindre erreur.
        if (!holder.add(cible.off).readPointer().equals(cfg)) {
            return { ok: false, detail: `écriture NON CONFIRMÉE dans \`${cible.nom}\`` };
        }
        // ⚠ ON CONSTRUIT LE DÉLÉGUÉ, ON NE LE CLONE PAS — et les deux tentatives précédentes
        // établissent pourquoi. `method_code` (+0x40), que `Get` passe à l'invocateur, n'est pas
        // la CIBLE mais un pointeur de CODE, vers un trampoline où la cible est déjà scellée :
        //   * ne réécrire que `m_target` -> pas de crash, mais le trampoline appelle toujours la
        //     fermeture du PATRON (mesuré : deux unités affichées avec SON modèle) ;
        //   * écrire le porteur dans `method_code` -> l'invocateur saute sur des données
        //     (mesuré : « access violation accessing 0x... » levée par `Get`).
        // Un délégué ne se re-cible donc pas par écriture de champ. `StartBattle` l'instancie par
        // `.ctor(cible, pointeur_de_méthode)` — on fait pareil, et le runtime bâtit le trampoline.
        const del = il2cpp_object_new(p.delClasse) as NativePointer;
        if (del.isNull()) return { ok: false, detail: "`il2cpp_object_new` (délégué) a rendu NUL" };
        // Un `IntPtr` est un TYPE VALEUR : `runtime_invoke` en attend l'ADRESSE, pas la valeur.
        const boiteFn = Memory.alloc(Process.pointerSize);
        boiteFn.writePointer(p.loaderMethodInfo);
        invokeMethod(ctorDel.info, del, [holder, boiteFn]);
        const cibleRelue = del.add(p.offTarget).readPointer();
        if (!cibleRelue.equals(holder)) {
            return { ok: false, detail: `délégué construit mais \`m_target\` vaut ${cibleRelue} `
                + `au lieu de ${holder} -- on n'inscrit RIEN` };
        }
        const ref = cloner(p.exemplaireRef, p.refClasse, p.tailleRef);
        // ⚠ LE SLOT QUI DOIT REPARTIR À NUL : le patron a son prefab déjà résolu ; le laisser
        // afficherait le modèle de l'unité capturée.
        ref.add(p.offPrefab).writePointer(ptr(0));
        ref.add(p.offLoader).writePointer(del);
        gcRoot.add(holder); gcRoot.add(del); gcRoot.add(ref);
        invokeMethod(mAdd.info, dico, [sid, ref]);
        return { ok: true, ref, detail: `entrée créée -- config ${nomCfg} @ \`${cible.nom}\`` };
    } catch (e) { return { ok: false, detail: "LEVÉ : " + (e as Error).message }; }
}

/** Ce dont `fabriquerEntree` a besoin d'une méthode : son `MethodInfo*`. */
interface MethodRefLike { info: NativePointer }

function etatPrefab(): Record<string, unknown> {
    return {
        arme: listenerAdd !== null,
        addFires,
        patron: patron === null ? null : {
            reference: patron.refClasseNom,
            champPrefab: `${patron.nomPrefab}@+0x${patron.offPrefab.toString(16)}`,
            champLoader: `${patron.nomLoader}@+0x${patron.offLoader.toString(16)}`,
            delegue: patron.delClasseNom,
            porteur: patron.holderClasseNom,
            champConfig: `${patron.nomConfig}@+0x${patron.offConfig.toString(16)}`,
            champsDuPorteur: patron.champsHolder.map((c) => `${c.nom}:${c.type}`),
            unitIdVu: patron.unitIdVu,
        },
        // LE COMPTAGE QUI TRANCHE : si `Add` a rempli un dictionnaire et que `Get` en lit un
        // AUTRE, « N prefabs chargés » ne dit rien sur ce que le déploiement voit.
        dicosRemplisParAdd: Array.from(dicosVusParAdd, ([p, n]) => ({ dico: p, adds: n })),
        dicoLuParGet: dicoDeGet === null ? null : dicoDeGet.toString(),
        idsAvecPrefab,
        vueDePose: vuesDePose === null ? null : vuesDePose.toString(),
        captureVue,
        dicoDuPatron: patron === null ? null : patron.dico,
        // TRI-ÉTAT : `null` = aucun refus ENREGISTRÉ, ce qui n'est pas « tout va bien » tant
        // qu'`addFires` vaut 0.
        refusDeCapture: patronRefus,
        charges: prefabCharges.slice(-24),
    };
}

// ============================================================================
// POURQUOI LA POSE ÉCHOUE — ET LA PREMIÈRE CAUSE ÉCRITE ICI ÉTAIT FAUSSE.
//
// Mesuré sur la session 50, sur les DEUX unités réellement refusées
// (`spaceBlackmane`, `admecRuststalker`) : `HasPrefabForUnitId` rend **true** pour chacune.
// Le montage `useAccountUnits` charge **68** prefabs (compté sur `Add`, hook armé APRÈS le
// amorce, donc tous les fires viennent de NOTRE montage). ⇒ **La cause « prefab manquant »
// est RÉFUTÉE** ; elle avait été déduite du décompilé sans jamais être mesurée.
//
// L'étage supérieur est tranché, lui aussi par mesure. `StateMachineActions` porte
// `_hud : IIdunGameHud` en `+0x48` et `_views : IIdunGameViews` en `+0x18` (`classFields`), donc :
//
//     UnitDeployment_PlaceUnitOnBoard(unitId, col, row, isManual, playerId) :
//         si _hud != null et <garde> :
//             si !_hud.<slot 0x11>(unitId) : return false      <- c'est `TryMarkUnitAsPlaced`,
//                                                                 MESURÉ à `true` (le grisement)
//         return _views.AddPlaceholderUnit(unitId, col, row, isManual, playerId)
//
// ⇒ On entre donc BIEN dans `AddPlaceholderUnit`, et c'est LUI qui rend `false`. Il lui reste
// exactement trois sorties, et ce bloc les départage AU LIEU d'en élire une :
//
//   (A) `UnitIdToPrefabDictionary$$Get` -> `TryGet` faux        -- déjà réfutée, on la RE-MESURE
//                                                                  au runtime plutôt que de s'en
//                                                                  remettre à `HasPrefabForUnitId`
//   (B) `IdunBoardView$$GetLogicalTileAt(col, row)` rend NUL    -- la tuile cliquée n'existe pas
//   (C) `_placeholderUnitViews` contient déjà `unitId`          -- unité déjà posée
//
// ⚠ Aucun de ces trois hooks n'écrit quoi que ce soit. On observe, on nomme, ET ENSUITE on
// décide — c'est le régime qui a déjà rattrapé deux fausses causes dans ce dossier.

const NS_BOARD = "idun";
const CLS_BOARD = "IdunBoardView";
let listenerAdd2: InvocationListener | null = null;
let listenerTuile: InvocationListener | null = null;
let listenerGet: InvocationListener | null = null;
const poseTrace: Array<Record<string, unknown>> = [];
const tuileTrace: Array<{ col: number; row: number; trouvee: boolean }> = [];
const getTrace: Array<{
    unitId: string | null; rendu: string; nul: boolean; dico: string;
    loaderAppele: number; lecture: string;
}> = [];
let listenerLoader: InvocationListener | null = null;
let listenerCle: InvocationListener | null = null;
let listenerDemande: InvocationListener | null = null;
/** Le régime À LA DEMANDE. Faux par défaut : il ÉCRIT dans le dictionnaire du jeu. */
let aLaDemande = false;
let demandesFaites = 0;
const demandeTrace: Array<{ unitId: string | null; detail: string }> = [];
let loaderFires = 0;
const loaderTrace: Array<{ rendu: string; nul: boolean }> = [];
const cleTrace: Array<{ entree: string | null; sortie: string | null }> = [];

function armerPoseDiag(): true | Refus {
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    if (!kv) return refus(`\`${CLS_VIEWS_PREFAB}\` INTROUVABLE`);
    const mAdd = findMethodByParamCount(kv, "AddPlaceholderUnit", 5);
    if (!mAdd) return refus("`IdunGameViews$$AddPlaceholderUnit` INTROUVABLE (5 paramètres)");
    const kb = findClassAnywhere(NS_BOARD, CLS_BOARD);
    if (!kb) return refus(`\`${NS_BOARD}.${CLS_BOARD}\` INTROUVABLE`);
    const mTuile = findMethodByParamCount(kb, "GetLogicalTileAt", 2);
    if (!mTuile) return refus("`IdunBoardView$$GetLogicalTileAt` INTROUVABLE (2 paramètres)");
    const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
    if (!kd) return refus(`\`${CLS_DICO}\` INTROUVABLE`);
    const mGet = findMethodByParamCount(kd, "Get", 1);
    if (!mGet) return refus("`UnitIdToPrefabDictionary$$Get` INTROUVABLE (1 paramètre)");
    for (const [nom, mi] of
        [["AddPlaceholderUnit", mAdd], ["GetLogicalTileAt", mTuile], ["Get", mGet]] as const) {
        const t = lireTete(mi.ptr);
        if (t.erreur !== null) return refus(`tête de \`${nom}\` ILLISIBLE (${t.erreur})`);
        if (teteTriviale(t)) {
            return refus(`REFUS : \`${nom}\` résout sur un corps TRIVIAL (ret à l'octet `
                + `${t.retA}) -- adresse PARTAGÉE par déduplication. Cf. §8.`);
        }
    }
    if (!listenerAdd2) {
        listenerAdd2 = Interceptor.attach(mAdd.ptr, {
            onEnter(args) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; vues: NativePointer;
                    tAvant: number; gAvant: number;
                };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.c = args[2].toInt32();
                self.r = args[3].toInt32();
                self.vues = args[0];
                vuesDePose = args[0];      // l'AUTORITÉ sur « quelle vue déploie »
                // Les deux compteurs encadrent l'appel : ils disent quels sous-étages ont été
                // TRAVERSÉS, donc où la sortie s'est produite. Un `false` sans delta de tuile
                // désigne (A) ou (C) ; avec delta et tuile non trouvée, c'est (B).
                self.tAvant = tuileTrace.length;
                self.gAvant = getTrace.length;
            },
            onLeave(retval) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; vues: NativePointer;
                    tAvant: number; gAvant: number;
                };
                if (poseTrace.length >= 32) return;
                const rendu = (retval.toInt32() & 0xff) !== 0;
                let dejaPosee: boolean | string = "non lu";
                let nbPosees: number | string = "non lu";
                try {
                    const kv2 = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
                    const off = kv2 ? getFieldOffset(kv2, "_placeholderUnitViews") : -1;
                    if (off >= 0) {
                        const dico = self.vues.add(off).readPointer();
                        nbPosees = compteDict(dico);
                    } else { nbPosees = "champ `_placeholderUnitViews` ABSENT"; }
                } catch (e) { nbPosees = "ILLISIBLE : " + (e as Error).message; }
                const tuiles = tuileTrace.slice(self.tAvant);
                const gets = getTrace.slice(self.gAvant);
                if (gets.length > 0) dejaPosee = false;   // on a dépassé le test (C)
                poseTrace.push({
                    unitId: self.uid, col: self.c, row: self.r, rendu,
                    // Le VERDICT est dérivé des étages traversés, jamais deviné.
                    etage: rendu ? "POSÉE"
                        : gets.length === 0 ? "(A?) sorti AVANT `Get` -- prefab ou garde amont"
                        : gets.some((g) => g.nul) ? "(A) `Get` a rendu NUL"
                        : tuiles.length === 0 ? "(C) sorti APRÈS `Get`, SANS chercher de tuile "
                            + "-- `_placeholderUnitViews` contient déjà cet unitId"
                        : tuiles.some((t) => !t.trouvee) ? "(B) `GetLogicalTileAt` a rendu NUL"
                        : "sorti APRÈS une tuile TROUVÉE -- aucune des trois causes connues",
                    getsVus: gets, tuilesVues: tuiles, placeholders: nbPosees, dejaPosee,
                });
            },
        });
    }
    if (!listenerTuile) {
        listenerTuile = Interceptor.attach(mTuile.ptr, {
            onEnter(args) {
                const self = this as unknown as { c: number; r: number };
                self.c = args[1].toInt32();
                self.r = args[2].toInt32();
            },
            onLeave(retval) {
                const self = this as unknown as { c: number; r: number };
                if (tuileTrace.length < 64) {
                    tuileTrace.push({ col: self.c, row: self.r, trouvee: !retval.isNull() });
                }
            },
        });
    }
    // LE LOADER. S'il tire pendant un `Get` qui rend nul, l'entrée EXISTE et c'est la fabrication
    // du prefab qui échoue. S'il ne tire pas, `Get` est sorti par « clé absente » -- donc la clé
    // qu'il calcule DIFFÈRE de celle de `HasPrefabForUnitId`, seule autre explication possible.
    if (!listenerLoader && patron !== null && patron.loaderPtr !== null) {
        listenerLoader = Interceptor.attach(patron.loaderPtr, {
            onLeave(retval) {
                loaderFires++;
                if (loaderTrace.length < 32) {
                    loaderTrace.push({ rendu: retval.toString(), nul: retval.isNull() });
                }
            },
        });
    }
    // LA CLÉ. Les deux appels de `GetUnitIdForUniverse` dans `Get` passent par des blocs d'init
    // distincts : si leurs sorties diffèrent, la contradiction s'explique sans mystère.
    if (!listenerCle) {
        const kn = findClassAnywhere("idun.shared", "UnitNamingConventions")
            ?? findClassAnywhere("shared", "UnitNamingConventions");
        const mn = kn ? findMethodByParamCount(kn, "GetUnitIdForUniverse", 1) : null;
        if (mn) {
            listenerCle = Interceptor.attach(mn.ptr, {
                onEnter(args) {
                    const self = this as unknown as { e: string | null };
                    self.e = null;
                    try { self.e = readIl2cppString(args[0]); } catch { /* best effort */ }
                },
                onLeave(retval) {
                    const self = this as unknown as { e: string | null };
                    if (cleTrace.length >= 48) return;
                    let sortie: string | null = null;
                    try { sortie = readIl2cppString(retval); } catch { /* best effort */ }
                    cleTrace.push({ entree: self.e, sortie });
                },
            });
        }
    }
    // ============================================================================
    // LE CHARGEMENT À LA DEMANDE, DANS SA FORME DÉFINITIVE.
    //
    // On ancre `Get` et, si la clé MANQUE, on fabrique l'entrée DANS LE `onEnter` — puis on
    // laisse le corps natif s'exécuter normalement : il trouve alors la clé et déclenche son
    // propre chargement paresseux. Aucun `replace`, aucun retour fabriqué, et c'est le JEU qui
    // charge, au moment où il l'aurait fait.
    //
    // ⚠ POURQUOI PAS UN PRÉCHARGEMENT DU ROSTER. Créer les 55 entrées d'avance « pour tester »
    // valide un mécanisme qui n'est PAS celui qu'on livre : le régime d'épreuve doit être le
    // régime réel, sinon le vert ne prouve rien. Une entrée par unité RÉELLEMENT posée.
    //
    // ⚠ Les appels faits ici (`HasPrefabForUnitId`, `GetUnitVisualConfig`, `Add`) ne seront PAS
    // vus par nos propres ancrages : un `Interceptor` ne ré-observe pas un appel émis depuis un
    // autre callback sur le même thread. `addFires` ne bougera donc pas — ce n'est pas une panne.
    if (!listenerDemande) {
        const kdd = findClassAnywhere(NS_PREFAB, CLS_DICO);
        const kvv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
        const mHas = kdd ? findMethodByParamCount(kdd, "HasPrefabForUnitId", 1) : null;
        const mAddD = kdd ? findMethodByParamCount(kdd, "Add", 2) : null;
        const mCfg = kvv ? findMethodByParamCount(kvv, "GetUnitVisualConfig", 1) : null;
        if (!mHas || !mAddD || !mCfg) {
            return refus("chargement à la demande IMPOSSIBLE : "
                + `HasPrefabForUnitId=${mHas !== null} Add=${mAddD !== null} `
                + `GetUnitVisualConfig=${mCfg !== null}`);
        }
        listenerDemande = Interceptor.attach(mGet.ptr, {
            onEnter(args) {
                if (!aLaDemande || patron === null) return;
                const vues = vuesDePose;
                if (vues === null || vues.isNull()) {
                    if (demandeTrace.length < 32) {
                        demandeTrace.push({ unitId: null,
                            detail: "aucune vue captée -- rien tenté" });
                    }
                    return;
                }
                let id: string | null = null;
                try { id = readIl2cppString(args[1]); } catch { /* best effort */ }
                if (id === null || id === "") return;
                const r = fabriquerEntree(patron, args[0], vues, id, mHas, mAddD, mCfg);
                if (r.detail === "déjà présent -- rien fait") return;   // le cas courant
                demandesFaites++;
                if (demandeTrace.length < 32) demandeTrace.push({ unitId: id, detail: r.detail });
            },
        });
    }
    if (!listenerGet) {
        listenerGet = Interceptor.attach(mGet.ptr, {
            onEnter(args) {
                const self = this as unknown as {
                    uid: string | null; dico: NativePointer; lAvant: number;
                };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.dico = args[0];
                self.lAvant = loaderFires;
                dicoDeGet = args[0];       // l'AUTORITÉ sur « quel dictionnaire est lu »
            },
            onLeave(retval) {
                const self = this as unknown as {
                    uid: string | null; dico: NativePointer; lAvant: number;
                };
                if (getTrace.length < 64) {
                    const dl = loaderFires - self.lAvant;
                    getTrace.push({
                        unitId: self.uid, rendu: retval.toString(), nul: retval.isNull(),
                        dico: self.dico.toString(), loaderAppele: dl,
                        // LE VERDICT, dérivé -- pas choisi.
                        lecture: !retval.isNull() ? "prefab rendu"
                            : dl > 0 ? "le loader A TIRÉ et n'a rien produit -- entrée présente, "
                                + "fabrication du prefab EN ÉCHEC"
                            // ⚠ CE VERDICT ACCUSAIT UN DÉCALAGE DE CLÉ QUI N'EXISTE PAS. Il
                            // disait « sa clé DIFFÈRE de celle de `HasPrefabForUnitId` », ce qui
                            // envoie chercher une normalisation divergente -- et fait perdre du
                            // temps. Décompilé le 2026-08-23 :
                            // `IdunBattle.View.Game.UnitIdToPrefabDictionary$$Get` ET `$$Add`
                            // passent tous DEUX par
                            // `idun.shared.UnitNamingConventions$$GetUnitIdForUniverse`. La clé
                            // est donc la MÊME des deux côtés. Ce que dit vraiment ce cas, c'est
                            // que l'entrée n'a JAMAIS été ajoutée -- et `Get` ne charge rien à la
                            // demande : le loader vit DANS l'entrée (`+0x18`), pas sur le
                            // dictionnaire ; clé absente = `return 0` + une ligne de log.
                            : "le loader N'A PAS tiré -- clé ABSENTE du dictionnaire. `Add` n'a "
                                + "jamais été appelé pour cet unitId, et `Get` ne charge RIEN à "
                                + "la demande (le loader est par ENTRÉE). La clé n'est pas en "
                                + "cause : `Get` et `Add` normalisent par le même "
                                + "`UnitNamingConventions$$GetUnitIdForUniverse`.",
                    });
                }
            },
        });
    }
    Interceptor.flush();
    return true;
}

// ============================================================================
// LE BOUTON START — pourquoi il reste GRIS quand les unités sont PRÉ-POSITIONNÉES.
//
// `idun.ui.UnitDeploymentHud$$UpdateButtons` compte les unités de `_currentlyPlacedUnits`
// (+0x1b8) et relaie à `idun.ui.UnitDeploymentHudButtons$$UpdateState(gameMode, count, mowCount,
// min, max)`, dont le corps décide :
//
//     count <  min  ->  Animator.SetInteger(<etat>, 0)   // BOUTON DÉSACTIVÉ
//     count >= max  ->  ... SetInteger(<etat>, 2)        // plein
//     sinon         ->  ... SetInteger(<etat>, 1)        // actif
//
// ⚠ MESURÉ : la comptabilité du HUD et la composition RÉELLE de la bataille sont DEUX choses
// SÉPARÉES, et en sandbox aucune ne nourrit l'autre. Déclarer les unités dans `bc.Units` les
// fait bien APPARAÎTRE sur le plateau, mais `_currentlyPlacedUnits` reste VIDE — donc
// `count = 0 < min` et le bouton est gris. Symétriquement, les poser par le HUD active le
// bouton mais ne crée que des `PlaceholderUnitView`.
//
// On force donc le COMPTE que le relais reçoit, pas la liste : c'est le même patron que le
// forçage de phase et celui des bornes, tous deux éprouvés. Défaut = le `min` que le relais
// reçoit lui-même, pour rendre le bouton ACTIF sans le déclarer PLEIN.

const NS_BOUTONS = "idun.ui";
const CLS_BOUTONS = "UnitDeploymentHudButtons";
let listenerBouton: InvocationListener | null = null;
let boutonImpose: number | null = null;
let boutonFires = 0;
/** Le compte dérivé du plateau, calculé HORS hook puis mis en cache. `null` = jamais calculé —
 *  ce qui n'est PAS zéro : le relais laisse alors passer ce que le HUD croit. */
let compteCache: number | null = null;
let compteCacheDetail: Record<string, number | string> | null = null;
/** L'entité du joueur humain, retenue au dernier parcours — publiée pour rendre un appariement
 *  raté LISIBLE (un compte à zéro ne dit pas s'il n'y a pas d'unité ou si l'appariement ment). */
let dernierIdJoueurHumain: number | null = null;
/** Les couples `PlayerId/PlayerEntityId` observés — deux numérotations distinctes, et c'est la
 *  PREMIÈRE qu'attend `AddUnitMessage`. */
let derniersCouples: string | null = null;
const boutonObs: Array<{
    recu: number; impose: number; min: number; max: number;
    source: string; plateau: Record<string, number | string>;
}> = [];

/**
 * L'ORDRE QUE LE START PARCOURT — lu à la source, pas déduit.
 *
 * ⚠ CE N'EST PAS `UnitDeploymentHud._currentlyPlacedUnits`, ET LES CONFONDRE M'A FAIT ÉCRIRE
 * DEUX RÈGLES CONTRADICTOIRES. Le corps de `idun.IdunMainView$$AddUnitsFromPlaceholdersAndRunner
 * StartMatch` s'écrit :
 *
 *     vues = IdunGameViews$$GetPlaceholderUnitViews(this->_gameViews)
 *     pour chaque vue, EN AVANT (GetEnumerator + MoveNext) :
 *         si !vue.IsMachineOfWar : Apply(AddUnitMessage{ UnitId, PlayerId, [tuile] })
 *         sinon                  : Apply(AddMachineMessage{ UnitId, PlayerId })
 *     runner.StartMatch()
 *
 * L'allocation des entités suit donc CETTE liste, dans CET ordre, sans inversion. Le HUD tient
 * une comptabilité PARALLÈLE qui ne commande rien -- mesuré : les deux collections sortent dans
 * un ordre différent selon le régime (pré-remplissage vs clear+repose), ce qui rendait toute
 * règle bâtie sur le HUD vraie une fois sur deux.
 *
 * ⚠ LES CHAMPS SONT RÉSOLUS PAR LEUR NOM, jamais par les offsets lus au décompilé -- ceux-ci
 * n'ont servi qu'à CONFIRMER l'appariement (`<UnitId>`=0x18, `<PlayerId>`=0x58,
 * `<CoordinatePosition>`=0x5c, `<IsMachineOfWar>`=0x70 sur ce build).
 */
function ordreDeConversion(): unknown {
    const v = vueDeLaMoW();
    if ("ok" in v) return { erreur: "aucune `IdunGameViews` joignable -- " + v.error };
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    const mi = kv ? findMethodByParamCount(kv, "GetPlaceholderUnitViews", 0) : null;
    if (!mi) return { erreur: "`IdunGameViews$$GetPlaceholderUnitViews` INTROUVABLE (0 paramètre)" };
    let lst: NativePointer;
    try { lst = invokeMethod(mi.info, v.vues, []) as NativePointer; }
    catch (e) { return { erreur: "LEVÉ : " + (e as Error).message }; }
    if (lst === null || lst.isNull()) return { erreur: "la liste des vues est NULLE" };
    const els = elementsDeListe(lst);
    if (estRefusLecture(els)) return { erreur: "liste ILLISIBLE : " + JSON.stringify(els) };
    const out: Array<Record<string, unknown>> = [];
    for (const el of els) {
        if (el.isNull()) { out.push({ erreur: "vue NULLE" }); continue; }
        try {
            const k = el.readPointer();
            const oId = getFieldOffset(k, "<UnitId>k__BackingField");
            const oPl = getFieldOffset(k, "<PlayerId>k__BackingField");
            const oCo = getFieldOffset(k, "<CoordinatePosition>k__BackingField");
            const oMo = getFieldOffset(k, "<IsMachineOfWar>k__BackingField");
            if (oId < 0 || oPl < 0 || oCo < 0) {
                out.push({ erreur: `champs ABSENTS (UnitId=${oId} PlayerId=${oPl} `
                    + `CoordinatePosition=${oCo}) -- chemin PÉRIMÉ` });
                continue;
            }
            out.push({
                unitId: readIl2cppString(el.add(oId).readPointer()),
                playerId: el.add(oPl).readS32(),
                col: el.add(oCo).readS32(), row: el.add(oCo).add(4).readS32(),
                mow: oMo >= 0 ? el.add(oMo).readU8() !== 0 : null,
            });
        } catch (e) { out.push({ erreur: "vue ILLISIBLE : " + (e as Error).message }); }
    }
    return out;
}

/** Taille d'un `List\`1`, champ `_size` résolu PAR SON NOM. */
function tailleListe(lst: NativePointer): number | string {
    try {
        if (lst.isNull()) return "NULLE";
        const o = getFieldOffset(lst.readPointer(), "_size");
        return o < 0 ? "champ `_size` ABSENT" : lst.add(o).readS32();
    } catch (e) { return "ILLISIBLE : " + (e as Error).message; }
}

/**
 * LE COMPTE DÉRIVÉ DU PLATEAU — les trois candidats, tous publiés.
 *
 * Forcer une CONSTANTE dans le relais du bouton ne contourne pas seulement la comptabilité
 * fausse du HUD : ça supprime la contrainte « assez d'unités posées ». En dérivant le compte des
 * unités RÉELLEMENT présentes, la contrainte est de nouveau ÉVALUÉE — c'est la comptabilité du
 * HUD qui est fausse (il ignore ce qui vient de `bc.Units`), pas la borne.
 *
 * Les trois sont rendus ensemble parce qu'un seul chiffre ne se vérifie pas : sur un montage à
 * 5 unités joueur et 3 adverses, seul le bon candidat vaut 5.
 */
function compterSurLePlateau(): Record<string, number | string> {
    const out: Record<string, number | string> = {};
    const vues = vuesDePose;
    if (vues === null || vues.isNull()) {
        return { erreur: "aucune `IdunGameViews` observée -- rien n'est compté" };
    }
    // LE COMPTE JUSTE : les vues d'unité dont le joueur EST le joueur humain.
    // ⚠ `_humanPlayerEntityIds` compte les JOUEURS (mesuré : 1) et `_unitViews` compte LES DEUX
    // CAMPS (mesuré : 8 pour 5+3). Ni l'un ni l'autre ne repond a la question ; c'est en les
    // publiant tous les deux qu'on l'a vu, plutot qu'en en elisant un.
    const ids = idsDesUnitesDuJoueur();
    out.unitesDuJoueurHumain = Array.isArray(ids) ? ids.length : ids;
    if (Array.isArray(ids)) out.idsSurLePlateau = ids.join(",");
    if (dernierIdJoueurHumain !== null) out.idJoueurHumain = dernierIdJoueurHumain;
    if (derniersCouples !== null) out.couplesPlayerIdSurEntityId = derniersCouples;
    try {
        const k = vues.readPointer();
        for (const [cle, champ, genre] of [
            ["unitesDuJoueur", "_humanPlayerEntityIds", "liste"],
            ["toutesLesVues", "_unitViews", "dico"],
            ["placeholders", "_placeholderUnitViews", "dico"],
        ] as const) {
            const o = getFieldOffset(k, champ);
            if (o < 0) { out[cle] = `champ \`${champ}\` ABSENT`; continue; }
            const p = vues.add(o).readPointer();
            out[cle] = genre === "liste" ? tailleListe(p) : compteDict(p);
        }
    } catch (e) { out.erreur = (e as Error).message; }
    return out;
}

/** Une unité RÉELLE du plateau, telle que sa vue la déclare. */
interface UniteDuPlateau {
    unitId: string | null;
    /** `AUnitView.<Id>` — l'entité DE L'UNITÉ. C'est ce qu'attend `RemoveUnitMessage`. */
    entityId: number;
    /** `AUnitView.<PlayerId>` — ce qu'attend `AddUnitMessage`. */
    playerId: number | null;
    /** `AUnitView.<PlayerEntityId>` — l'entité DU JOUEUR, ce qui apparie l'unité à son camp. */
    playerEntityId: number;
    /** `AUnitView$$get_LogicalPosition` — la tuile RÉELLEMENT occupée. `null` = non lue.
     *  ⚠ Sans elle on ne peut pas dire si une pose échoue par la TUILE ou par le CATALOGUE :
     *  mesuré, `ultraApothecary` (dans la BC ET dans le lineup) n'apparaît pas en (0,0), tandis
     *  qu'`admecMarshall` (hors BC native) apparaît en (4,1) et (4,2). */
    col: number | null;
    row: number | null;
    duJoueur: boolean;
}

/**
 * L'inventaire des unités RÉELLEMENT présentes sur le plateau, une entrée par vue.
 *
 * ⚠ LE JOUEUR SE DEMANDE PAR `FirstPlayerEntityIdOfHumanOnThisDevice`, PAS PAR
 * `get_CurrentPlayerEntityId` : le second désigne le joueur DU TOUR COURANT, et pendant le
 * déploiement il ne désigne pas le propriétaire de l'appareil. Mesuré : le premier apparie 5
 * unités sur 8, le second en appariait **0**.
 *
 * ⚠ TROIS NUMÉROTATIONS COEXISTENT sur une vue, et les confondre ne lève RIEN — on les publie
 * donc toutes les trois plutôt que d'en élire une (c'est ainsi qu'on a vu que le `playerId 11`
 * de l'écran était JUSTE, après l'avoir soupçonné à tort).
 */
/** L'`IdunGameViews` du déploiement — captée par nos hooks, SINON celle que la pompe draine.
 *
 * ⚠ LE REPLI N'EST PAS UN CONFORT, C'EST LA CAUSE D'UNE SOIRÉE PERDUE (2026-08-20). Nos capteurs
 * (`Initialize`/`AddUnit`/`Continue`/`Enable`) ne tirent qu'à la CRÉATION de la bataille. En
 * sandbox on monte soi-même, hooks déjà en place, donc ils tirent toujours -- et le défaut est
 * resté invisible. Sur une bataille RÉELLE créée avant l'armement, ils ne tirent JAMAIS :
 * `vuesDePose` reste nul pour toute la durée de cette bataille, et TOUT ce qui suit devient
 * aveugle (plateau illisible, poses refusées, START refusé).
 *
 * Or la pompe, elle, tient cette vue depuis toujours : elle lit `IdunGameViews._runner` à chaque
 * frame, donc son `this` EST l'objet qu'on cherche -- même classe, même instance.
 *
 * ⛔ `premiereInstance` NE MARCHE PAS ICI : `IdunGameViews` n'est pas un `UnityEngine.Object`,
 * `FindObjectsByType` rend NULL même en pleine bataille. Mesuré. Le repli (3) de `dicoVivant`
 * repose sur cette voie et ne peut donc pas sauver ce cas-là.
 */
function vueDeDeploiement(): NativePointer | null {
    if (vuesDePose !== null && !vuesDePose.isNull()) return vuesDePose;
    const p = state.gameViews;
    return p !== null && !p.isNull() ? p : null;
}

function unitesDuPlateau(): UniteDuPlateau[] | string {
    const vues = vueDeDeploiement();
    if (vues === null || vues.isNull()) {
        return "aucune `IdunGameViews` -- ni captée par nos hooks, ni vue par la pompe";
    }
    return (() => {
        try {
            const k = vues.readPointer();
            // ⚠ `get_CurrentPlayerEntityId` designe le joueur DU TOUR COURANT, pas le proprietaire
            // de l'appareil : pendant le deploiement il peut ne designer personne de pertinent.
            // `FirstPlayerEntityIdOfHumanOnThisDevice` est la question qu'on pose vraiment.
            const mAll = findMethodByParamCount(k, "GetAllUnitViews", 0);
            const mHum = findMethodByParamCount(k, "FirstPlayerEntityIdOfHumanOnThisDevice", 0)
                ?? findMethodByParamCount(k, "get_CurrentPlayerEntityId", 0);
            if (!mAll || !mHum) return "`GetAllUnitViews`/joueur humain INTROUVABLES";
            // ⚠ `BEntityId` est un TYPE VALEUR : `runtime_invoke` le BOXE, la valeur est a +0x10.
            const boite = invokeMethod(mHum.info, vues, null);
            if (boite.isNull()) return "joueur humain NUL";
            const idCourant = boite.add(0x10).readS32();
            dernierIdJoueurHumain = idCourant;
            // ⚠ `GetAllUnitViews` rend une `ValueCollection` (mesuré), pas une `List` : elle n'a
            // ni `_items` ni `_size`. On parcourt donc les ENTRÉES du dictionnaire, avec la
            // taille d'élément DÉRIVÉE de la classe du tableau -- jamais supposée.
            const offVues = getFieldOffset(k, "_unitViews");
            if (offVues < 0) return "champ `_unitViews` ABSENT";
            const dico = vues.add(offVues).readPointer();
            if (dico.isNull()) return "`_unitViews` est NUL";
            const kd = dico.readPointer();
            const offEntries = getFieldOffset(kd, "_entries");
            const offCount = getFieldOffset(kd, "_count");
            if (offEntries < 0 || offCount < 0) return "`_entries`/`_count` absents du dictionnaire";
            const entries = dico.add(offEntries).readPointer();
            const nEntries = dico.add(offCount).readS32();
            if (entries.isNull()) return "`_entries` est NUL";
            if (nEntries < 0 || nEntries > 4096) return `_count invraisemblable (${nEntries})`;
            if (class_get_element_class === null || class_instance_size === null) {
                return "`class_get_element_class`/`class_instance_size` absents -- taille "
                    + "d'element NON DERIVABLE, on ne devine pas";
            }
            const kElem = class_get_element_class(entries.readPointer()) as NativePointer;
            // Type valeur : `instance_size` inclut l'en-tete d'objet (2 pointeurs).
            const tailleElem = (class_instance_size(kElem) as number) - Process.pointerSize * 2;
            if (tailleElem <= 0 || tailleElem > 128) {
                return `taille d'element derivee invraisemblable (${tailleElem})`;
            }
            const trouves: UniteDuPlateau[] = [];
            let offJoueur = -1;
            let offUnitId = -1;
            let offPlayerId = -1;
            let offId = -1;
            // `undefined` = pas encore cherché ; `null` = cherché et ABSENT. Les distinguer évite
            // de relancer la résolution à chaque vue.
            let mPos: ReturnType<typeof findMethodByParamCount> | undefined;
            let lus = 0;
            const vus: number[] = [];
            const couples: string[] = [];
            for (let i = 0; i < nEntries; i++) {
                // `{ hashCode, next, cle, valeur }` : la valeur est une REFERENCE, donc en fin
                // d'entree apres alignement.
                const uv = entries.add(0x20 + i * tailleElem + tailleElem - Process.pointerSize)
                    .readPointer();
                if (uv.isNull()) continue;
                if (offJoueur < 0) {
                    offJoueur = getFieldOffset(uv.readPointer(),
                                               "<PlayerEntityId>k__BackingField");
                    offPlayerId = getFieldOffset(uv.readPointer(), "<PlayerId>k__BackingField");
                    offUnitId = getFieldOffset(uv.readPointer(), "<UnitId>k__BackingField");
                    // `AUnitView.<Id>` : l'entité de l'UNITÉ, distincte des deux ids de JOUEUR
                    // lus juste au-dessus. Sans elle, aucun retrait n'est adressable.
                    offId = getFieldOffset(uv.readPointer(), "<Id>k__BackingField");
                    if (offJoueur < 0) return "champ `<PlayerEntityId>k__BackingField` ABSENT";
                    if (offUnitId < 0) return "champ `<UnitId>k__BackingField` ABSENT";
                    if (offId < 0) return "champ `<Id>k__BackingField` ABSENT";
                }
                lus++;
                const idVue = uv.add(offJoueur).readS32();
                // Les ids OBSERVES sont publies : un compte a zero ne dit pas s'il n'y a pas
                // d'unite du joueur ou si c'est l'appariement qui est faux.
                if (vus.indexOf(idVue) < 0 && vus.length < 12) vus.push(idVue);
                // ⚠ `PlayerId` et `PlayerEntityId` sont DEUX numerotations distinctes. Celle
                // qu'attend `AddUnitMessage` est `PlayerId` -- la lire sur une unite REELLE est
                // le seul moyen de ne pas la deviner.
                if (offPlayerId >= 0 && couples.length < 12) {
                    const c = `${uv.add(offPlayerId).readS32()}/${idVue}`;
                    if (couples.indexOf(c) < 0) couples.push(c);
                }
                // On enregistre les DEUX camps : c'est le seul moyen de dire « 0 unité du joueur
                // sur 8 vues lues » plutôt qu'un zéro muet qui ne distingue pas le plateau vide
                // de l'appariement faux.
                let nom: string | null = null;
                try { nom = readIl2cppString(uv.add(offUnitId).readPointer()); } catch { nom = null; }
                // La TUILE. `get_LogicalPosition` rend un `AxialCoordinate` — un TYPE VALEUR,
                // donc `runtime_invoke` le BOXE : `Column` est à +0x10, `Row` à +0x14. Lire le
                // pointeur lui-même rendrait n'importe quoi (même piège que `boolBoxe`).
                let col: number | null = null;
                let row: number | null = null;
                try {
                    if (mPos === undefined) {
                        mPos = findMethodByParamCount(uv.readPointer(), "get_LogicalPosition", 0);
                    }
                    if (mPos) {
                        const boite = invokeMethod(mPos.info, uv, null);
                        if (!boite.isNull()) {
                            col = boite.add(0x10).readS32();
                            row = boite.add(0x14).readS32();
                        }
                    }
                } catch { col = null; row = null; }
                trouves.push({
                    unitId: nom === "" ? null : nom,
                    entityId: uv.add(offId).readS32(),
                    playerId: offPlayerId >= 0 ? uv.add(offPlayerId).readS32() : null,
                    playerEntityId: idVue,
                    col, row,
                    duJoueur: idVue === idCourant,
                });
            }
            // Le parcours se CONTROLE : si on n'a pas lu autant de vues que le dictionnaire en
            // annonce, la disposition supposee est fausse et le compte ne vaut RIEN.
            derniersCouples = couples.join(" ");
            const attendu = compteDict(dico);
            if (typeof attendu === "number" && lus !== attendu) {
                return `parcours INCOHERENT : ${lus} vues lues pour ${attendu} annoncees `
                    + `(taille d'element ${tailleElem}) -- on ne rend RIEN plutot qu'un faux`;
            }
            return trouves;
        } catch (e) { return "LEVÉ : " + (e as Error).message; }
    })();
}

/** Les `unitId` des unités du JOUEUR HUMAIN sur le plateau — la vue « noms » de l'inventaire.
 *  UN SEUL parcours existe (`unitesDuPlateau`), avec UN SEUL contrôle de cohérence : deux
 *  lecteurs indépendants du même dictionnaire finiraient par diverger en silence. */
function idsDesUnitesDuJoueur(): string[] | string {
    const u = unitesDuPlateau();
    if (!Array.isArray(u)) return u;
    return u.filter((x) => x.duJoueur && x.unitId !== null).map((x) => x.unitId as string);
}

// ---------------------------------------------------------------------------------------------
// LE RETRAIT — le symétrique exact de la pose.
//
// Le déploiement natif ne sait ôter que des `PlaceholderUnitView` : quand les unités viennent de
// `bc.Units`, le runner les a créées AU MONTAGE, elles sont RÉELLES, et le clear du HUD n'a
// aucune prise sur elles. Il vide sa liste (donc grise START) et laisse le plateau intact.
//
// Le chemin qui les ôte pour de vrai est le même que pour la pose : un message d'entrée appliqué
// au runner VIVANT. `IdunBattle.Messages.InputMessageProcessor$$Visit` en a une surcharge dédiée.
// ---------------------------------------------------------------------------------------------

const NS_MESSAGES = "IdunBattle.Messages";

/**
 * Le message que le jeu emploie lui-même pour ôter une unité — construit, jamais deviné.
 *
 * `RemoveUnitMessage` porte UN SEUL champ (`UnitId : BEntityId`), et
 * `IdunBattle.Messages.InputMessageProcessor$$Visit` ne lit que celui-là (4 octets) avant de
 * résoudre l'entité et d'appeler `IdunBattle.Operations.RemoveUnitOperation$$Execute` avec
 * `removeEffects: true, keepActive: false` — les deux littéraux sont dans le décompilé.
 *
 * ⚠ AUCUN `.ctor` n'est invoqué, et c'est un choix MESURÉ, pas une facilité : la classe n'en
 * publie pas dans `frida/methods.tsv` — ce qui ne prouve rien (IL2CPP déduplique les corps
 * triviaux) — mais son unique champ est un entier et le lecteur natif ne lit que lui. L'écrire
 * EST donc la construction complète.
 *
 * ⚠ L'offset est DÉRIVÉ par `getFieldOffset`, jamais le `+0x10` qu'on a mesuré : un offset
 * recopié devient faux au prochain build, en silence.
 *
 * ⚠ Rendu PINNÉ, comme `buildAddUnitMessage` : l'appelant DOIT `gcRoot.remove(msg)` après
 * l'`Apply`, sinon la racine GC s'accumule à chaque retrait.
 */
function buildRemoveUnitMessage(entityId: number): NativePointer {
    const k = findClassAnywhere(NS_MESSAGES, "RemoveUnitMessage");
    if (!k) throw new Error("`IdunBattle.Messages.RemoveUnitMessage` INTROUVABLE sur ce build");
    const off = getFieldOffset(k, "UnitId");
    if (off < 0) throw new Error("champ `UnitId` ABSENT de `RemoveUnitMessage` -- chemin PÉRIMÉ");
    const msg = il2cpp_object_new(k) as NativePointer;
    if (msg.isNull()) throw new Error("`il2cpp_object_new(RemoveUnitMessage)` a rendu NUL");
    gcRoot.add(msg);
    msg.add(off).writeS32(entityId);
    return msg;
}

/** Applique un `RemoveUnitMessage` par cible. `cibles === null` ⇒ toutes les unités du joueur.
 *  ⚠ À APPELER DEPUIS LA FILE DU THREAD PRINCIPAL, jamais d'un callback d'interception. */
function retirerDuRunner(cibles: number[] | null): Record<string, unknown> | Refus {
    const avant = unitesDuPlateau();
    if (!Array.isArray(avant)) return refus("plateau non lisible : " + avant);
    const ids = cibles ?? avant.filter((u) => u.duJoueur).map((u) => u.entityId);
    if (ids.length === 0) {
        // ⚠ Un zéro DÉSIGNE SON SUSPECT. Ce refus a déjà menti une fois : le plateau portait
        // bien ses unités, c'est `vuesDePose` qui pointait sur la vue d'une bataille morte.
        return refus("aucune unité du joueur sur le plateau -- rien à retirer. Vue interrogée : "
            + `${vuesDePose === null ? "AUCUNE" : vuesDePose.toString()}, ${avant.length} vue(s) `
            + "lue(s) tous camps confondus. Si la bataille est bien montée, c'est cette "
            + "vue-là qui est PÉRIMÉE, pas le plateau qui est vide.");
    }
    const runner = state.liveRunner;
    if (runner === null || runner.isNull()) {
        return refus("aucun runner vivant publié par le pump -- `state.liveRunner` est NUL, "
            + "ce qui n'est PAS « zéro unité »");
    }
    const kr = findClassAnywhere("IdunBattle.Runner", "IdunRunner");
    const mApply = kr ? findMethodByParamCount(kr, "Apply", 1) : null;
    if (!mApply) return refus("`IdunBattle.Runner.IdunRunner$$Apply` INTROUVABLE");
    const nomDe = new Map<number, string | null>(avant.map((u) => [u.entityId, u.unitId]));
    const faits: Array<{ entityId: number; unitId: string | null;
                         ok: boolean; detail: string }> = [];
    for (const id of ids) {
        let msg: NativePointer | null = null;
        try {
            msg = buildRemoveUnitMessage(id);
            invokeMethod(mApply.info, runner, [msg]);
            faits.push({ entityId: id, unitId: nomDe.get(id) ?? null, ok: true,
                         detail: "`Apply` passé" });
        } catch (e) {
            faits.push({ entityId: id, unitId: nomDe.get(id) ?? null, ok: false,
                         detail: "LEVÉ : " + (e as Error).message });
        } finally {
            if (msg !== null) { try { gcRoot.remove(msg); } catch { /* best effort */ } }
        }
    }
    // ⚠ ON NE TOUCHE PAS À LA MÉMOIRE ICI, ET C'EST UN CHOIX. Tenir `memoirePoses` à jour geste
    // par geste, c'est maintenir un DOUBLE du plateau : deux états qui doivent rester égaux,
    // donc qui divergent. La mémoire se prend en UNE FOIS, au START, sur le plateau RÉEL
    // (`instantanerAuStart`) -- ce qui rend cette synchronisation-ci inutile ET plus sûre.
    // ⚠ READ-AFTER-WRITE. Une observation prise AVANT la mutation ne dit rien de ce qu'elle a
    // fait, et « `Apply` n'a pas levé » n'est PAS « l'unité a disparu » : mesuré sur
    // `AddUnitMessage`, l'appel passe sans erreur et rien n'apparaît quand la configuration
    // manque à la BC. On relit donc, et on publie les deux comptes.
    const apres = unitesDuPlateau();
    return {
        // ⚠ `ok` DIT ICI << les appels sont partis >>, PAS << les unités sont parties >>, et cette
        // nuance a coûté cher : le 2026-08-20, ce RPC a rendu `ok: true` sur ses 5 cibles alors
        // que les 5 entités étaient TOUJOURS VIVANTES ; le START a ensuite empilé par-dessus,
        // 10 unités pour 5. La note le disait déjà -- une note ne suffit pas quand le champ
        // qu'on lit d'abord affirme le contraire. Le VERDICT est produit par `deploymentRetirer`,
        // qui attend l'effet et REND `ok: false` si une cible survit.
        ok: true, faits, verifie: false,
        cibles: ids,
        retirees: faits.filter((f) => f.ok).length, visees: ids.length,
        surPlateauAvant: avant.filter((u) => u.duJoueur).length,
        surPlateauApres: Array.isArray(apres)
            ? apres.filter((u) => u.duJoueur).length : apres,
        note: "`ok` = les `Apply` sont partis. Le retrait de la VUE passe par le flux de bataille "
            + "(`IdunBattle.View.BattleStream.StepHandlers.RemoveUnitStepHandler`) et traîne "
            + "d'une frame ou deux : `surPlateauApres` est un INSTANTANÉ, pas un verdict.",
    };
}

/** Rejoue `f` après `n` images de pump. ⛔ On repasse par la FILE, on ne dort jamais. */
function apresImages<T>(n: number, f: () => T): Promise<T> {
    if (n <= 0) return queueOnMainThread(f) as Promise<T>;
    return (queueOnMainThread(() => null) as Promise<null>)
        .then(() => apresImages(n - 1, f));
}

/** Déclare au HUD les unités DÉJÀ présentes sur le plateau, puis provoque le rafraîchissement
 *  du bouton. C'est ce qui rend START actif quand les unités viennent de `bc.Units` : le HUD ne
 *  compte que ce que LUI a posé, or sur une BC pré-remplie il n'a rien posé.
 *  ⚠ À APPELER DEPUIS LA FILE DU THREAD PRINCIPAL. */
function marquerLesUnitesDuPlateau(): Record<string, unknown> | Refus {
    const ids = idsDesUnitesDuJoueur();
    if (!Array.isArray(ids)) return refus("plateau non lisible : " + ids);
    if (ids.length === 0) return refus("aucune unité du joueur sur le plateau");
    if (hudInstance === null || hudInstance.isNull()) {
        return refus("aucune instance de HUD captée");
    }
    const c = classeDerriere(hudInstance);
    if (c.classe !== CLS_HUD) {
        return refus(`le pointeur de HUD ne porte plus \`${CLS_HUD}\` mais `
            + `\`${c.classe ?? c.erreur}\` -- PÉRIMÉ`);
    }
    const kh = findClassAnywhere(NS_HUD, CLS_HUD);
    const mMark = kh ? findMethodByParamCount(kh, "TryMarkUnitAsPlaced", 2) : null;
    const mUp = kh ? findMethodByParamCount(kh, "UpdateButtons", 0) : null;
    if (!mMark) return refus("`TryMarkUnitAsPlaced` INTROUVABLE (2 paramètres)");
    const faits: Array<{ unitId: string; accepte: boolean | string }> = [];
    const faux = Memory.alloc(1); faux.writeU8(0);   // `isMachineOfWar: false`
    for (const id of ids) {
        try {
            const r = invokeMethod(mMark.info, hudInstance, [createManagedString(id), faux]);
            // ⚠ retour BOXÉ : le booléen est à +0x10, pas dans le pointeur.
            faits.push({ unitId: id, accepte: boolBoxe(r) });
        } catch (e) {
            faits.push({ unitId: id, accepte: "LEVÉ : " + (e as Error).message });
        }
    }
    if (mUp) { try { invokeMethod(mUp.info, hudInstance, null); } catch { /* best effort */ } }
    const b = etatDuBouton();
    return { ok: true, faits, marquees: faits.filter((f) => f.accepte === true).length,
             placeesApres: typeof b.placees !== "undefined" ? b.placees : "non relu" };
}

let listenerClear: InvocationListener | null = null;
let clearAuto = false;
let clearFires = 0;
let clearDernier: unknown = null;

/** Relais sur le clear natif. Il LAISSE le corps natif faire son travail (vider
 *  `_currentlyPlacedUnits`, ôter les placeholders) et ENFILE le retrait des unités RÉELLES. */
function armerClear(): true | Refus {
    if (listenerClear) return true;
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    const mi = k ? findMethodByParamCount(k, "HandleOnRemoveAllHeroesPressed", 0) : null;
    if (!mi) {
        return refus("`UnitDeploymentHud$$HandleOnRemoveAllHeroesPressed` INTROUVABLE "
            + "(0 paramètre)");
    }
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête du clear ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus("REFUS : `UnitDeploymentHud$$HandleOnRemoveAllHeroesPressed` résout sur un "
            + `corps TRIVIAL (ret à l'octet ${t.retA}) -- adresse probablement PARTAGÉE`);
    }
    listenerClear = Interceptor.attach(mi.ptr, {
        onLeave() {
            clearFires++;
            if (!clearAuto) return;
            // ⛔ CE CALLBACK N'INVOQUE RIEN, ET C'EST LA LEÇON DE DEUX GELS. Il ne fait
            // qu'ENFILER : la file est drainée par le pump, sur le thread principal, hors de
            // toute interception. Invoquer ici gèle le jeu.
            queueOnMainThread(() => retirerDuRunner(null)).then(
                (r) => { clearDernier = r; },
                (e) => { clearDernier = { ok: false, error: String(e) }; });
        },
    });
    return true;
}

let deposeAuto = false;
let deposeDernier: unknown = null;
const deposeTrace: unknown[] = [];

/**
 * LA DÉPOSE UNITÉ PAR UNITÉ — le pendant du relais de CLEAR, sur un seul héros.
 *
 * ⚠ LE CHEMIN A ÉTÉ MESURÉ, PAS DEVINÉ, et la première hypothèse était FAUSSE.
 * `UnitDeploymentHud$$RemoveUnit(unitConfigId)` porte le nom qu'il faut et ne tire JAMAIS
 * (0 tir sur un cycle complet pose + dépose, ancrage contrôlé : VA `0x180e2f220`, tête non
 * triviale). C'est `PutUnitIntoHand(unitId)` qui porte les DEUX gestes — mesuré 2 tirs pour
 * 1 pose acceptée, avec le MÊME argument (`worldKharn`) les deux fois.
 *
 * ⇒ L'ARGUMENT NE DISCRIMINE PAS. Ce qui discrimine est l'ÉTAT DU PLATEAU : si l'unité nommée
 * y est déjà, le tir est une DÉPOSE (elle revient en main) ; sinon c'est une SAISIE depuis le
 * roster, et il n'y a rien à retirer. Le no-op est donc le comportement CORRECT dans un cas
 * sur deux — il est tracé pour qu'on ne le confonde pas avec un raté.
 *
 * ⛔ ON N'INVOQUE RIEN DEPUIS LE CALLBACK : on ENFILE. La décision elle-même (relire le
 * plateau, résoudre l'entité) se prend sur la file du thread principal, hors de toute
 * interception — c'est la leçon des deux gels, et c'est exactement ce que fait `armerClear`.
 * Le plateau lu en différé reste valable : tout le défaut est que le natif ne le touche pas.
 */
function retirerSiSurLePlateau(unitId: string): void {
    queueOnMainThread(() => {
        const u = unitesDuPlateau();
        if (!Array.isArray(u)) {
            return { ok: false, unitId, error: "plateau non lisible : " + String(u) };
        }
        const cible = u.find((x) => x.duJoueur && x.unitId === unitId);
        if (!cible) {
            return { ok: true, unitId, action: "aucune",
                     raison: "pas sur le plateau -- c'est une SAISIE, pas une dépose" };
        }
        return { ok: true, unitId, action: "retire", entityId: cible.entityId,
                 retrait: retirerDuRunner([cible.entityId]) };
    }).then(
        (r) => { deposeDernier = r; if (deposeTrace.length < 16) deposeTrace.push(r); },
        (e) => { deposeDernier = { ok: false, unitId, error: String(e) }; });
}

let syncAuto = false;
let syncDernier: unknown = null;

/** Enfile la synchronisation HUD, avec un nombre BORNÉ de reprises : quand `Show` tire, le
 *  plateau peut n'être pas encore peuplé, et un unique essai rendrait « 0 marquée » sans que
 *  rien soit en défaut. */
function planifierSync(reste: number): void {
    queueOnMainThread(() => marquerLesUnitesDuPlateau()).then((r) => {
        syncDernier = r;
        const n = (r as { marquees?: number }).marquees ?? 0;
        if (n === 0 && reste > 0) planifierSync(reste - 1);
    }, (e) => { syncDernier = { ok: false, error: String(e) }; });
}

// ---------------------------------------------------------------------------------------------
// COMMITTER À LA POSE — ÉTAGE OBSOLÈTE, GARDÉ POUR COMPARAISON. Ne pas l'armer par défaut.
//
// ⛔ SA PRÉMISSE EST RÉFUTÉE, PAR LA MESURE (2026-08-20). Elle disait :
//
//     « La pose native ne crée qu'un `PlaceholderUnitView`. Ce qui le convertit en unité RÉELLE
//       est `IGameModeSource.HandleStartMatch`, que `SandboxGameModeSource` N'IMPLÉMENTE PAS :
//       la bataille démarre alors sans aucune unité du joueur et se termine AUSSITÔT. »
//
// CONTRE-ÉPREUVE, sur `Campaign4_31` monté en sandbox avec les QUATRE relais d'écriture ÉTEINTS
// (`deploymentMemoire`, `deploymentClearArmer`, `deploymentDeposeArmer`, ce commit-ci) : cinq
// unités posées À LA MAIN, START pressé À LA MAIN. La bataille A DÉMARRÉ avec les cinq unités,
// s'est jouée et a été GAGNÉE (`stage -> Finished`, `winner` = l'entité du joueur, 19 pas).
// Le replay porte `5 AddUnitMessage` sous `Group=User_PlaceUnit`, AVANT le `StartBattleMessage`,
// et AUCUN `RemoveUnitMessage` : c'est le JEU qui les émet, pas nous. 0 exception, 0 faute de
// pompe. Et le retry se comporte de même : plateau réinitialisé, roster re-servi, mêmes entités.
//
// ⚠ CE QUI N'EST PAS ÉTABLI : la CAUSE de l'observation d'origine. Elle date d'avant `980214ab`,
// où les deux pompes CONFISQUAIENT les exceptions managées du jeu (`exceptions: "steal"`) --
// or `AGameModeSource$$HandleStartMatch` LÈVE si `this+0x60` est nul, et une levée confisquée
// posait `_isLogicPausedFromException` sans popup ni log. C'est une hypothèse cohérente, pas une
// mesure : personne n'a rejoué l'ancien régime sous l'ancienne pompe, et personne ne le fera.
// Ce qui est mort, c'est la CONCLUSION -- pas la raison pour laquelle on y avait cru.
//
// ⛔ ET LA RAISON DÉCISIVE N'EST PAS LÀ : LA VOIE DES PLACEHOLDERS EST LA SEULE QUI PUISSE
// PRODUIRE UN REPLAY BIT-EXACT AVEC CELUI DU JEU.
//
// Le livrable de #10040 est une comparaison AU CARACTÈRE des flux de sortie, pas une bataille
// qui « ressemble ». Or le message de déploiement n'est pas un détail de mise en scène : il
// ENTRE dans le flux enregistré. Selon la voie, il n'a pas le même émetteur :
//
//   commit       -- c'est NOUS qui fabriquons et appliquons l'`AddUnitMessage`, à la POSE,
//                   un par un, dans NOTRE ordre ;
//   placeholders -- c'est le JEU qui les émet, au START, depuis ses `PlaceholderUnitView`.
//
// Une partie officielle passe forcément par la seconde. Un replay capturé par la première ne
// peut donc pas coïncider avec la référence : mêmes unités, mêmes cases, et pourtant un flux
// qui diffère par l'émetteur, l'ordre et le groupement. On ne compare plus le MOTEUR, on
// compare notre harnais à lui-même.
//
// ⚠ ET C'EST UNE RAISON DE CONCEPTION, PAS UNE MESURE : personne n'a diffé au caractère un
// replay << commit >> contre un replay << placeholders >> de la même bataille. Ce qui EST
// mesuré, c'est que les deux voies écrivent des messages différents -- le reste suit.
//
// ⚠ ET CET ÉTAGE COÛTAIT. Le HUD tient des `PlaceholderUnitView`, le commit crée des unités
// RÉELLES, le START convertit les premières PAR-DESSUS les secondes : DEUX comptabilités pour un
// seul plafond -- 10 unités pour 5, sur un jeton de boss de guilde perdu le 2026-08-20. Le
// rappel de déploiement au retry passe désormais par `poserUnHerosParFsm` -- la SEULE voie
// depuis le 2026-08-21 --, qui produit un placeholder que le START natif convertit
// avec les autres -- une seule comptabilité, celle du jeu.
//
// Ce qui reste VRAI, et qui est une LECTURE, pas une observation :
// `CampaignGameModeSource$$HandleStartMatch` appelle `TempBattleData$$GenerateNewBattleId` puis
// le slot d'interface `0x1a` de `this+0x20` -- c'est le chemin qui CONSOMME un jeton sur le
// compte réel. On ne le porte pas. Son absence côté sandbox reste PROTECTRICE.
//
// ⛔ ET ON NE PORTE PAS L'IMPLÉMENTATION DE RÉFÉRENCE. `CampaignGameModeSource$$HandleStartMatch`
// appelle `GenerateNewBattleId` puis émet l'événement de chargement : c'est le chemin qui
// CONSOMME UN JETON sur le compte réel. Son absence côté sandbox est PROTECTRICE.
//
// (Motif historique de cet étage : convertir soi-même À LA POSE plutôt qu'au START, le START
// étant un callback d'interception où invoquer des natifs a gelé le jeu deux fois. La contrainte
// sur le callback reste vraie -- c'est la nécessité de convertir qui ne l'est plus.)
// ---------------------------------------------------------------------------------------------

// (!)LA VOIE COMMIT EST SUPPRIMÉE (2026-08-21), pas éteinte par défaut. Elle appliquait un
// `AddUnitMessage` au runner à la pose, en parallèle du `PlaceholderUnitView` du HUD, et le START
// natif convertissait les placeholders PAR-DESSUS : deux comptabilités pour un seul plafond,
// **10 unités pour 5** et un jeton de boss de guilde perdu le 2026-08-20.
//
// Ce qui l'a condamnée n'est pas ce coût, c'est que son EXISTENCE rendait le clear CONDITIONNEL
// (cf. `rejouerMemoire`) : sur la campagne réelle du 2026-08-21 le drapeau n'était pas armé, le
// clear a été sauté, et quatre rejeux ont laissé le plateau strictement inchangé sans une seule
// erreur. Une voie qu'on n'emprunte plus mais qui reste dans le code continue de brancher les
// autres.
//
// Parties avec elle : `committerUnePose`, `poseCommitAuto`, le commit automatique posé dans
// `onLeave` d'`AddPlaceholderUnit`, et les RPC `deploymentCommit` / `deploymentPoseCommitArmer`.
/** Le compte d'unités RÉELLES du joueur, ou `null` si le plateau n'est pas lisible.
 *  ⚠ `null` = PAS MESURÉ, jamais à lire comme un zéro. */
function compteJoueur(): number | null {
    const u = unitesDuPlateau();
    return Array.isArray(u) ? u.filter((x) => x.duJoueur).length : null;
}

interface Pose { unitId: string; playerId: number; col: number; row: number }

/** Deuxième temps : le plateau a-t-il VRAIMENT grossi ? Tant que non, on repasse — l'ajout
 *  transite par le flux de bataille et ne se voit pas dans la frame de l'`Apply` (mesuré sur le
 *  retrait : instantané à 5, réel à 4 une seconde plus tard). */
function verifierPuisNettoyer(p: Pose, avant: number | null, reste: number): void {
    queueOnMainThread((): Record<string, unknown> => {
        const apres = compteJoueur();
        if (avant !== null && apres !== null && apres > avant) {
            // L'unité est RÉELLE : le placeholder ferait doublon à l'écran.
            const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
            const mRem = kv ? findMethodByParamCount(kv, "RemovePlaceholderUnit", 1) : null;
            let ote: boolean | string = "`IdunGameViews$$RemovePlaceholderUnit` INTROUVABLE";
            if (mRem && vuesDePose !== null && !vuesDePose.isNull()) {
                try {
                    invokeMethod(mRem.info, vuesDePose, [createManagedString(p.unitId)]);
                    ote = true;
                } catch (e) { ote = "LEVÉ : " + (e as Error).message; }
            }
            return { ok: true, unitId: p.unitId, avant, apres, placeholderOte: ote };
        }
        if (reste > 0) return { attendre: true };
        return { ok: false, unitId: p.unitId, avant, apres,
                 error: "`Apply` est passé mais AUCUNE unité n'est apparue. Le runner ne "
                     + "construit que ce dont la CONFIGURATION est dans la BC -- mesuré : "
                     + "`spaceBlackmane` (hors BC) passe sans erreur et rien n'apparaît, "
                     + "`ultraInceptorSgt` (dans la BC) crée l'unité. Il faut enrichir la BC "
                     + "(`catalog_inject` / `--p-units`), donc un remontage.",
                 placeholderOte: "LAISSÉ EN PLACE -- c'est la seule trace visible de ta pose" };
    }).then((r) => {
        if ((r as { attendre?: boolean }).attendre === true) {
            verifierPuisNettoyer(p, avant, reste - 1);
            return;
        }
        tracerPose(r);
    }, (e) => tracerPose({ ok: false, unitId: p.unitId, error: String(e) }));
}

/** Premier temps : appliquer l'`AddUnitMessage` — le MÊME message que le harnais RL emploie. */
// ============================================================================
// MÉMOIRE DE DÉPLOIEMENT — pour que le RETRY reparte avec l'équipe déjà composée.
//
// Le retry ramène la phase de déploiement, mais le plateau revient VIDE : la bataille est
// reconstruite depuis la BC, qui ne porte aucun `PredefinedUnits` côté joueur. Recomposer cinq
// unités à chaque essai rend le mode inutilisable pour ce à quoi il sert -- réessayer une
// composition contre un boss.
//
// On mémorise donc les poses APPLIQUÉES, et on les rejoue quand la phase revient.
//
// ⚠ LE REJEU EST GARDÉ PAR L'ÉTAT DU PLATEAU, pas par un drapeau : on ne rejoue QUE si le camp
// du joueur est vide. Sans ce cran, un `Show` qui tire alors que les unités sont déjà là
// doublerait la mise -- et une pose sur une case occupée échoue en silence (mesuré le
// 2026-08-17 : `ultraApothecary` sur la case de `ultraTigurius`).
const memoirePoses: Pose[] = [];
let memoireAuto = false;
let memoireRejeux = 0;
let memoireDernier: string | null = null;

/**
 * ⚠ LA MACHINE OF WAR A SON PROPRE CHEMIN, ET IL NE CROISE JAMAIS CELUI DES UNITÉS.
 *
 * Mesuré le 2026-08-17 : `tyranBiovore` sort de `TryMarkUnitAsPlaced` avec `mow=true` et
 * `accepte=true`, mais n'apparaît NI dans la mémoire NI dans `deploymentPlateau`. Deux causes
 * distinctes, toutes deux structurelles :
 *
 *   * la pose passe par `AddPlaceholderMachine(unitId, isManual, playerId, position)` -- une
 *     MoW n'a ni colonne ni ligne, elle a une `MachineOfWarPosition` et sa plateforme. Notre
 *     ancrage ne visait que `AddPlaceholderUnit` ;
 *   * `deploymentPlateau` énumère des `AUnitView` ; une MoW est une `MachineView`. Son absence
 *     de l'inventaire ne prouvait donc PAS son absence de l'écran.
 *
 * ⛔ ON ANCRE l'étage FSM (`UnitDeployment_PlaceMachineOfWarUnitOnBoard`, qui porte la
 * `position`) ET ON INVOQUE l'étage vues (`AddPlaceholderMachine`). Deux classes, deux
 * méthodes : la règle « ne jamais ancrer ce qu'on invoque » est tenue.
 */
interface PoseMoW { unitId: string; playerId: number; position: number }
let memoireMoW: PoseMoW | null = null;      // une seule MoW par bataille
/** OÙ la MoW s'intercale dans la séquence de pose. `null` = en DERNIER, le comportement
 *  historique -- c'est le défaut, donc rien ne change pour un appelant qui l'ignore.
 *
 *  (!)POURQUOI CET INDEX EXISTE. La MoW était posée APRÈS les unités, toujours, parce qu'elle
 *  passe par un autre chemin (`rejouerLaMoW` vs `poserUnHerosParFsm`). Conséquence MESURÉE le
 *  2026-08-21 : l'ordre de conversion obtenu ne peut mettre la machine qu'aux EXTRÉMITÉS --
 *  dernière sur plateau vierge (`U + [M]`), première sur plateau plein, où la liste libre se
 *  comporte en pile (`reverse(U + [M])` = `[M] + reverse(U)`). Aucune permutation des unités ne
 *  l'en déloge : elle n'est pas dans la partie permutée.
 *
 *  Or un replay où le joueur a posé la MoW AU MILIEU enregistre exactement ça -- et il devient
 *  alors irreproductible. Ce n'était pas visible tant que tous nos replays venaient de notre
 *  propre chaîne, qui la posait en dernier ; la capture automatique de fin de bataille en
 *  produit désormais d'autres. Le gisement est né de cette ouverture, pas d'un défaut du jeu. */
let memoireMoWIndex: number | null = null;

/* ⛔ LA MÉMOIRE APPARTIENT À UNE BATAILLE, ET SON REJEU EST UN JETON À USAGE UNIQUE.
 *
 * Ces deux variables existent parce que `memoireAuto` seul est un booléen GLOBAL : une fois armé,
 * le `Show` du HUD de déploiement appelle `rejouerMemoire()` à CHAQUE écran, sans savoir de quelle
 * bataille la mémoire vient ni qui a monté celle qui s'ouvre. Deux dégâts mesurés le 2026-08-22,
 * rapportés par l'écran :
 *
 *   1. SANDBOX SUIVANTE — montage de `campaign1` nœud 22 juste après avoir joué le nœud 19 :
 *      l'écran s'ouvre avec les cinq poses du nœud 19 rejouées sur `C1_05`, qui n'a pas la même
 *      géométrie. Et le rejeu VIDE LE PLATEAU d'abord, donc il écrase aussi le dernier
 *      déploiement que le jeu propose lui-même par `GetBattleLineup` -- la seule lineup
 *      pré-posée légitime.
 *   2. BATAILLE RÉELLE — le même artefact sur un combat officiel contre le boss. Là c'est notre
 *      hook qui écrit dans la partie du joueur, et c'est la faute grave : un relais laissé armé
 *      qui pose tout seul est exactement ce qui fait perdre un jeton.
 *
 * `memoireBataille` retient le `BC.Id` de la bataille à qui la mémoire appartient ;
 * `memoireRejeuArme` est un JETON posé par le montage sandbox et CONSOMMÉ au premier rejeu. Une
 * bataille qu'on n'a pas montée ne pose aucun jeton, donc elle ne peut pas déclencher de rejeu --
 * quel que soit l'état de `memoireAuto`.
 *
 * (!)LE JETON EST LE CRAN QUI TIENT, PAS L'IDENTIFIANT. Comparer le `BC.Id` ne suffirait pas :
 * après un montage sandbox, `memoireBataille` reste renseigné, et une bataille RÉELLE lancée
 * ensuite retomberait dans le même piège. C'est l'usage unique qui ferme le cas 2. */
let memoireBataille: string | null = null;
let memoireRejeuArme = false;

let vuesJeu: NativePointer | null = null;   // l'`IdunGameViews` vivante, captée au passage
let listenerMoW: InvocationListener | null = null;

/** Le montage sandbox DÉCLARE la bataille qu'il monte. Vide la mémoire si c'en est une autre,
 *  et pose le jeton de rejeu. Appelé par `sandboxModeBcOverride` -- le seul point du code qui
 *  sache qu'une bataille est LA NÔTRE. */
export function memoireBatailleMontee(bcId: string | null): Record<string, unknown> {
    const change = bcId !== memoireBataille;
    const avant = memoirePoses.length;
    if (change) {
        memoirePoses.length = 0;
        memoireMoW = null;
        memoireMoWIndex = null;
        memoireDernier = `mémoire VIDÉE : montage de ${bcId ?? "?"}, `
            + `la mémoire appartenait à ${memoireBataille ?? "aucune bataille"} `
            + `(${avant} pose(s) jetée(s))`;
    }
    memoireBataille = bcId;
    memoireRejeuArme = true;
    return { bataille: bcId, changeDeBataille: change, posesJetees: change ? avant : 0,
             rejeuArme: true };
}

/** REPOSER le jeton -- appelé depuis l'ancrage de `SandboxGameModeSource$$LoadBattle`.
 *
 *  (!)C'EST LE RETRY QUI EXIGE ÇA, ET LE PREMIER CORRECTIF LE CASSAIT. Un jeton posé une seule
 *  fois au montage est consommé par l'écran de déploiement initial ; au RETRY, le jeu rouvre la
 *  phase de déploiement de la MÊME bataille sans repasser par le RPC de montage, donc plus aucun
 *  jeton -- et la composition était perdue, ce qui est précisément ce que la mémoire existe pour
 *  éviter. Rapporté par l'écran le 2026-08-22.
 *
 *  `SandboxGameModeSource$$LoadBattle` est le bon point parce qu'il tire à CHAQUE chargement de
 *  la bataille sandbox, retry compris, et qu'une bataille RÉELLE n'y passe jamais : elle a sa
 *  propre `GameModeSource`. Le jeton reste donc refusé là où il doit l'être. */
export function memoireRejeuAutoriser(): void {
    memoireRejeuArme = true;
}

/**
 * OUBLIER TOUS LES POINTEURS CAPTÉS SUR LA BATAILLE PRÉCÉDENTE.
 *
 * ⛔ CE MODULE MET EN CACHE CINQ POINTEURS D'OBJETS VIVANTS, ET RIEN NE LES INVALIDAIT. Ils sont
 * captés au vol dans les appels du jeu — c'est justement ce qui fait leur valeur (cf. l'en-tête
 * de `dicoVivant` : « aller CHERCHER la vue rend *une* vue, pas *celle que le déploiement
 * utilise* »). Mais l'objet meurt avec sa bataille, et le pointeur, lui, restait.
 *
 * ⚠ MESURÉ, ET LE MOTIF EST NET : le PREMIER montage d'une session passe, le SECOND tue le jeu
 * pendant la pose. Trois crashs le 2026-08-21 (`.50856` 16:42, `.29408` 16:5x, plus celui de
 * 16:27). Signature au journal : sur un plateau qu'on vient de monter, `deploymentEtat` rend un
 * `ordreConversion` NON VIDE — il décrit la bataille morte, lue à travers un pointeur périmé.
 *
 * ⚠ ET NE PAS LES TRAITER UN PAR UN. J'ai d'abord nullifié le seul `vuesJeu`, en inversant au
 * passage la préférence de `vueDeLaMoW` vers `dicoVivant()` — dont la tête est `vuesDePose`,
 * périmée de la MÊME façon. Le crash est revenu à l'identique : le défaut avait été DÉPLACÉ, pas
 * réparé. Une liste de suspects ne peut pas montrer celui qu'elle a oublié ; on remet donc à nul
 * TOUT pointeur d'objet du module, et on l'appelle depuis le seul verbe que l'appelant joue avant
 * chaque montage.
 *
 * Aucune perte : chacun est re-rempli par son propre ancrage dès que la nouvelle bataille appelle
 * la méthode correspondante. Ce qui disparaît, c'est uniquement ce qui ne devait plus servir.
 */
function oublierLesPointeursDeLaBatailleMorte(): string[] {
    const vides: string[] = [];
    if (preEmprunt !== null) { preEmprunt = null; preEmpruntInfo = null; vides.push("preEmprunt"); }
    if (hudInstance !== null) { hudInstance = null; vides.push("hudInstance"); }
    if (dicoDeGet !== null) { dicoDeGet = null; vides.push("dicoDeGet"); }
    if (vuesDePose !== null) { vuesDePose = null; vides.push("vuesDePose"); }
    if (vuesJeu !== null) { vuesJeu = null; vides.push("vuesJeu"); }
    return vides;
}

/** Retient une pose, dédupliquée par unité (la dernière position gagne). */
function memoriser(p: Pose): void {
    const i = memoirePoses.findIndex((x) => x.unitId === p.unitId);
    if (i >= 0) memoirePoses[i] = p; else memoirePoses.push(p);
}

/**
 * L'INSTANTANÉ DE LA MÉMOIRE, PRIS UNE SEULE FOIS : À L'APPUI SUR START.
 *
 * ⚠ POURQUOI PAS UNE SYNCHRONISATION À CHAQUE GESTE. Tenir la mémoire à jour pose par pose et
 * retrait par retrait, c'est maintenir un DOUBLE du plateau : deux états qui doivent rester
 * égaux, donc qui finissent par diverger — et la divergence est SILENCIEUSE, elle ne se voit
 * qu'au retry suivant, sous la forme d'une unité qu'on croyait retirée et qui revient. Le
 * plateau est la vérité, et il est LISIBLE. On le recopie donc une fois, au moment où la
 * composition est arrêtée.
 *
 * ⛔ ENFILÉ. `unitesDuPlateau` invoque des natifs, et un natif invoqué depuis un callback
 * d'interception a déjà FIGÉ le jeu (cf. le callback de `armerBouton`).
 *
 * ⚠ LA MoW N'EST PAS DANS CET INSTANTANÉ, ET C'EST STRUCTUREL : `unitesDuPlateau` énumère des
 * `AUnitView`, une MoW est une `MachineView`. `memoireMoW` reste donc alimentée par SON capteur
 * (`UnitDeployment_PlaceMachineOfWarUnitOnBoard`), qui la voit au clic. Écraser `memoireMoW`
 * ici la perdrait à chaque START.
 */
function instantanerAuStart(): void {
    queueOnMainThread(() => unitesDuPlateau()).then((u) => {
        if (!Array.isArray(u)) {
            memoireDernier = "instantané au START ANNULÉ -- plateau non lisible : " + String(u);
            return;
        }
        const miennes = (u as UniteDuPlateau[]).filter(
            (x) => x.duJoueur && x.unitId !== null && x.col !== null && x.row !== null);
        if (miennes.length === 0) {
            // ⚠ ON NE VIDE JAMAIS SUR UN ZÉRO. Un plateau lu vide au moment du START est bien
            // plus probablement une lecture prématurée qu'une équipe vide — et écraser la
            // mémoire par ce zéro perdrait exactement la composition que le retry doit rendre.
            // Un zéro qui EFFACE est le pire des deux résultats possibles.
            memoireDernier = "instantané au START IGNORÉ -- 0 unité du joueur lue ; la mémoire "
                + `précédente est CONSERVÉE (${memoirePoses.length} pose(s))`;
            return;
        }
        memoirePoses.length = 0;
        for (const x of miennes) {
            memoirePoses.push({ unitId: x.unitId as string, playerId: x.playerId ?? 11,
                                col: x.col as number, row: x.row as number });
        }
        memoireDernier = `instantané au START : ${memoirePoses.length} pose(s) prises sur le `
            + "plateau RÉEL"
            + (memoireMoW ? ` + MoW ${memoireMoW.unitId} (capteur propre)` : " (aucune MoW)");
    }, (e) => { memoireDernier = "instantané au START LEVÉ : " + String(e); });
}

/**
 * Rejoue la mémoire si le camp du joueur est VIDE.
 *
 * ⛔ Appelé depuis la FILE du thread principal, jamais depuis un callback d'interception.
 */
function rejouerMemoire(): void {
    if (memoirePoses.length === 0 && memoireMoW === null) return;
    queueOnMainThread(() => compteJoueur()).then((n) => {
        const nb = n as number | null;
        if (nb === null) { memoireDernier = "plateau non lisible -- rejeu ANNULÉ"; return; }
        if (nb > 0) {
            memoireDernier = `plateau déjà peuplé (${nb}) -- rejeu ANNULÉ (pas de doublon)`;
            return;
        }
        memoireRejeux++;
        memoireDernier = `rejeu de ${memoirePoses.length} pose(s)`
            + (memoireMoW ? ` + MoW ${memoireMoW.unitId}` : " (aucune MoW mémorisée)");
        // ⚠ UN REJEU PASSE PAR UN CLEAR, TOUJOURS -- cf. `viderLePlateauParFsm`. L'écran arrive
        // pré-rempli par le lineup sauvegardé du jeu, et reposer par-dessus fait refuser chaque
        // unité : le rejeu ne corrigerait RIEN et les cases resteraient celles du jeu.
        //
        // (!)CE « TOUJOURS » N'EN ÉTAIT PAS UN, ET ÇA S'EST VU SUR UNE BATAILLE RÉELLE. Le clear
        // était conditionné à `poseParFsm`, un drapeau que l'appelant devait penser à armer. Sur
        // la campagne réelle du 2026-08-21 il ne l'était pas : le clear a été sauté, les cinq
        // reposes sont tombées sur un plateau déjà plein, et `deploymentEtat` a continué de
        // publier l'arrangement du JEU -- 4 rejeux, 0 changement, aucun message d'erreur. Le
        // journal disait même « plateau VIDÉ avant rejeu », parce que cette ligne s'écrit sans
        // condition. Depuis la suppression de la voie commit, il n'y a plus de drapeau : la pose
        // est TOUJOURS un placeholder, donc le clear est TOUJOURS joué.
        viderLePlateauParFsm().then((r) => {
            const rr = r as { ok?: boolean; error?: string };
            if (rr.ok !== true) {
                // Poser sans avoir vidé produirait un déploiement MÉLANGÉ, donc faux en silence.
                memoireDernier = `rejeu ANNULÉ -- clear ÉCHOUÉ : ${rr.error}`;
                return;
            }
            memoireDernier = (memoireDernier ?? "") + " | plateau VIDÉ avant rejeu";
            // ⚠ LA MoW S'INTERCALE, ELLE N'EST PLUS FORCÉMENT DERNIÈRE. `memoireMoWIndex` dit
            // combien d'unités la précèdent ; `null` (le défaut) la remet en fin de séquence,
            // donc un appelant qui l'ignore obtient exactement le comportement d'avant.
            const idxMoW = memoireMoW === null ? -1
                : (memoireMoWIndex === null ? memoirePoses.length
                    : Math.max(0, Math.min(memoirePoses.length, memoireMoWIndex)));
            for (let i = 0; i < memoirePoses.length; i++) {
                if (i === idxMoW) rejouerLaMoW(memoireMoW as PoseMoW);
                poserUnHerosParFsm(memoirePoses[i]);
            }
            if (idxMoW >= memoirePoses.length) rejouerLaMoW(memoireMoW as PoseMoW);
        }, (e) => { memoireDernier = "rejeu ANNULÉ -- clear levé : " + String(e); });
    }, (e) => { memoireDernier = "rejeu ÉCHOUÉ : " + String(e); });
}

/**
 * L'`IdunGameViews` sur laquelle reposer la MoW — par ORDRE D'AUTORITÉ, jamais par une source
 * unique.
 *
 * ⚠ C'EST LA CAUSE MESURÉE DU « LA MoW N'EST PAS RÉCUPÉRÉE AU RETRY » (2026-08-19).
 * `vuesJeu` n'est rempli que par le hook `IdunGameViews$$Enable` d'`armerPhase`, et ce hook
 * était REFUSÉ par le faux positif du garde de trivialité (cf. `teteTriviale`). Pendant ce
 * temps, le MÊME fichier tenait une vue VIVANTE dans `vuesDePose` — captée par
 * `AddPlaceholderUnit`, armée sans encombre. Relevé en séance : `deploymentMemoire` publiait
 * `vuesJeu: null` et `dernier: "... | MoW: aucune IdunGameViews captée"` alors que
 * `deploymentPrefabStatus` publiait `vueDePose: 0x1c716011000` et `Enable : ARMÉ`.
 * Le rejeu lisait la variable VIDE des deux. Deux sources pour une même chose, et on
 * interrogeait la mauvaise.
 *
 * ⇒ On passe par l'échelle `dicoVivant()` que le reste du fichier emploie déjà, et on PUBLIE la
 * source : une MoW reposée par le repli `FindObjectsByType` ne doit pas se lire comme une MoW
 * reposée sur la vue observée.
 *
 * ⇒ `dicoVivant()` D'ABORD, `vuesJeu` en dernier recours. Sa tête est `vuesDePose`, captée sur
 * l'`AddPlaceholderUnit` de la pose EN COURS — strictement plus fraîche que `Enable`, dont on a
 * mesuré (2026-08-21, `sonde_vue_perimee`) qu'il tire PENDANT LE DÉMONTAGE :
 *     AVANT montage    vuesJeu=None
 *     APRÈS montage    vuesJeu=None          <- `Enable` n'a pas encore tiré
 *     APRÈS retraite   vuesJeu=0x270feb0c900 <- il est rempli PAR LA SORTIE
 *
 * ⚠ CET ORDRE NE SUFFIT PAS, ET C'EST MESURÉ : l'inverser SEUL n'a rien réparé — le jeu est mort
 * au montage suivant exactement comme avant, parce que `vuesDePose` est périmée de la MÊME façon.
 * La réparation est `oublierLesPointeursDeLaBatailleMorte()`, qui les remet TOUS à nul avant
 * chaque montage. Ce qu'on gagne ici est plus modeste et reste vrai : à fraîcheur égale, la vue
 * de la pose en cours est la bonne, et la source publiée dit toujours laquelle a servi.
 */
function vueDeLaMoW(): { vues: NativePointer; source: string } | Refus {
    const d = dicoVivant();
    if (!("ok" in d)) return { vues: d.vues, source: d.source };
    if (vuesJeu !== null && !vuesJeu.isNull()) {
        return { vues: vuesJeu,
                 source: "DERNIER RECOURS `IdunGameViews$$Enable` -- l'échelle vivante a refusé ("
                     + d.error + "). Ce pointeur peut dater d'une bataille PRÉCÉDENTE." };
    }
    return d;
}

/**
 * Re-pose la MoW par `IdunGameViews$$AddPlaceholderMachine`.
 *
 * ⛔ ENFILÉ, jamais appelé depuis un callback d'interception.
 * ⚠ On ne rend pas la MoW RÉELLE ici : on la remet à sa plateforme, comme le ferait le clic.
 * Le passage au réel est le travail du START, comme pour les unités pré-positionnées.
 */
function rejouerLaMoW(m: PoseMoW): void {
    queueOnMainThread((): Record<string, unknown> => {
        const v = vueDeLaMoW();
        if ("ok" in v) {
            return { ok: false, error: "aucune `IdunGameViews` joignable -- " + v.error };
        }
        // ⚠ ON PASSE PAR L'ÉTAGE FSM, PAS PAR LA VUE — et c'est mesuré.
        //
        // `IdunGameViews$$AddPlaceholderMachine` ne pose qu'un PLACEHOLDER DE VUE. Le commit du
        // déploiement (`UnitDeploymentHud$$HandleOnStartBattleTapped`) ne le trouve alors PAS
        // là où il le cherche et CRASHE en « system error » — mesuré le 2026-08-19 : START
        // lève avec la MoW reposée par la vue, et PASSE sans elle, toutes gardes identiques
        // (`+0x22c`=0, source et callbacks non nuls, 5 unités posées).
        //
        // Le clic humain, lui, passe par `StateMachineActions$$UnitDeployment_PlaceMachineOfWarUnitOnBoard`
        // — le pendant MoW de `UnitDeployment_PlaceUnitOnBoard`, et c'est exactement ce que
        // notre propre capteur ancre pour REMPLIR `memoireMoW`. On invoque donc la même chose
        // qu'on observe : le porteur est `IdunGameViews._stateMachineActions`.
        const kam = findClassAnywhere("IdunBattle.View.FSM", "StateMachineActions");
        const mi = kam
            ? findMethodByParamCount(kam, "UnitDeployment_PlaceMachineOfWarUnitOnBoard", 4)
            : null;
        if (!mi) {
            return { ok: false,
                     error: "`UnitDeployment_PlaceMachineOfWarUnitOnBoard` INTROUVABLE "
                         + "(4 paramètres)" };
        }
        let actions: NativePointer;
        try {
            const off = getFieldOffset(v.vues.readPointer(), "_stateMachineActions");
            if (off < 0) return { ok: false, error: "`_stateMachineActions` ABSENT de ce build" };
            actions = v.vues.add(off).readPointer();
        } catch (e) { return { ok: false, error: "`_stateMachineActions` ILLISIBLE : " + (e as Error).message }; }
        if (actions.isNull()) {
            return { ok: false, error: "`_stateMachineActions` NUL -- la phase de déploiement "
                + "n'est pas montée. Ce n'est PAS « pas de MoW »." };
        }
        try {
            // `isManual`, `playerId` et `position` sont des types VALEUR : on transmet
            // l'ADRESSE de la valeur, jamais la valeur elle-même.
            const manuel = Memory.alloc(1); manuel.writeU8(1);
            const pid = Memory.alloc(4); pid.writeS32(m.playerId);
            const pos = Memory.alloc(4); pos.writeS32(m.position);
            invokeMethod(mi.info, actions, [createManagedString(m.unitId), manuel, pid, pos]);
            return { ok: true, unitId: m.unitId, actions: actions.toString(),
                     vue: v.vues.toString(), source: v.source, voie: "étage FSM" };
        } catch (e) { return { ok: false, error: "LEVÉ : " + (e as Error).message }; }
    }).then((r) => {
        const rr = r as { ok?: boolean; error?: string; source?: string };
        // ⚠ ON PUBLIE AUSSI LE SUCCÈS. La version d'avant ne consignait que l'échec : une MoW
        // reposée et une MoW jamais tentée rendaient exactement la même trace.
        memoireDernier = (memoireDernier ?? "")
            + (rr.ok === true ? ` | MoW REPOSÉE (${rr.source})` : ` | MoW: ${rr.error}`);
    }, (e) => { memoireDernier = (memoireDernier ?? "") + ` | MoW levée: ${String(e)}`; });
}

/** Poser les HÉROS par l'étage FSM, comme la MoW. C'est désormais LA voie, il n'y en a plus
 *  d'autre -- le drapeau qui les départageait est parti avec la voie commit. */
const poseFsmTrace: Array<Record<string, unknown>> = [];

function tracerPose(r: unknown): void {
    if (poseFsmTrace.length < 32) poseFsmTrace.push(r as Record<string, unknown>);
}

/**
 * POSER UN HÉROS PAR L'ÉTAGE FSM — le pendant exact de `rejouerLaMoW`.
 *
 * ⚠ CE QUE FAISAIT LA VOIE SUPPRIMÉE, ET POURQUOI ÇA NE SUFFISAIT PAS. Elle fabriquait un
 * `AddUnitMessage` et l'appliquait DIRECTEMENT au runner : l'unité apparaissait sur le plateau,
 * mais elle passait À CÔTÉ DU HUD. Mesuré le 2026-08-20 : le bouton START affiche **0/5** alors
 * que cinq unités sont en jeu, et `IdunGameViews$$GetPlaceholderUnitViews` ne rend qu'UN élément
 * -- la MoW, seule posée par l'étage FSM. Les héros n'ont jamais été des placeholders.
 *
 * ⚠ ET LE 5/1 QU'ON AVAIT MESURÉ ÉTAIT LE NÔTRE. `UnitDeploymentHudButtons$$UpdateState` rendait
 * `standardUnitsCount = 5`, ce qui a fait conclure « le HUD compte bien notre déploiement ». Mais
 * `deploymentBoutonArmer` RÉÉCRIT ce compte (son propre commentaire le dit) : on lisait notre
 * écriture. L'écran, lui, disait 0/5 depuis le début.
 *
 * Conséquence en chaîne : `AddUnitsFromPlaceholdersAndRunnerStartMatch` ne convertit qu'un seul
 * placeholder au lieu de six, et le groupe de flux de la MoW part seul. Le replay de référence,
 * lui, vient d'une sandbox où TOUT avait été posé au HUD -- six placeholders convertis d'un coup.
 *
 * On invoque donc pour les héros la méthode que le clic humain invoque :
 * `StateMachineActions$$UnitDeployment_PlaceUnitOnBoard(unitId, column, row, isManual, playerId)`.
 */
function poserUnHerosParFsm(p: Pose): void {
    memoriser(p);
    queueOnMainThread((): Record<string, unknown> => {
        const bloque = refusSiEmpilement(p, "UnitDeployment_PlaceUnitOnBoard");
        if (bloque) return { ok: false, unitId: p.unitId, error: bloque.error };
        const v = vueDeLaMoW();
        if ("ok" in v) {
            return { ok: false, unitId: p.unitId,
                     error: "aucune `IdunGameViews` joignable -- " + v.error };
        }
        const kam = findClassAnywhere("IdunBattle.View.FSM", "StateMachineActions");
        const mi = kam ? findMethodByParamCount(kam, "UnitDeployment_PlaceUnitOnBoard", 5) : null;
        if (!mi) {
            return { ok: false, unitId: p.unitId,
                     error: "`UnitDeployment_PlaceUnitOnBoard` INTROUVABLE (5 paramètres)" };
        }
        let actions: NativePointer;
        try {
            const off = getFieldOffset(v.vues.readPointer(), "_stateMachineActions");
            if (off < 0) return { ok: false, unitId: p.unitId,
                                  error: "`_stateMachineActions` ABSENT de ce build" };
            actions = v.vues.add(off).readPointer();
        } catch (e) {
            return { ok: false, unitId: p.unitId,
                     error: "`_stateMachineActions` ILLISIBLE : " + (e as Error).message };
        }
        if (actions.isNull()) {
            return { ok: false, unitId: p.unitId,
                     error: "`_stateMachineActions` NUL -- la phase de déploiement n'est pas "
                         + "montée. Ce n'est PAS « pas de héros »." };
        }
        try {
            // `column`, `row`, `isManual` et `playerId` sont des types VALEUR : on transmet
            // l'ADRESSE de la valeur, jamais la valeur elle-même. Même règle que pour la MoW.
            const col = Memory.alloc(4); col.writeS32(p.col);
            const row = Memory.alloc(4); row.writeS32(p.row);
            const manuel = Memory.alloc(1); manuel.writeU8(1);
            const pid = Memory.alloc(4); pid.writeS32(p.playerId);
            invokeMethod(mi.info, actions,
                         [createManagedString(p.unitId), col, row, manuel, pid]);
        } catch (e) {
            return { ok: false, unitId: p.unitId, error: "LEVÉ : " + (e as Error).message };
        }
        return { ok: true, unitId: p.unitId, voie: "FSM" };
    }).then((r) => {
        if (poseFsmTrace.length < 32) poseFsmTrace.push(r as Record<string, unknown>);
    }, (e) => {
        if (poseFsmTrace.length < 32) {
            poseFsmTrace.push({ ok: false, unitId: p.unitId, error: String(e) });
        }
    });
}

/**
 * VIDER LE PLATEAU PAR L'ÉTAGE FSM — le préalable OBLIGÉ de tout rejeu de déploiement.
 *
 * ⚠ UN REJEU QUI NE VIDE PAS EMPILE. Mesuré le 2026-08-20 : l'écran arrive DÉJÀ pré-rempli --
 * `GetBattleLineup` rend le lineup que le jeu a sauvegardé, et le HUD pose les cinq unités à
 * SES cases. Reposer par-dessus fait refuser chaque unité (« déjà un placeholder »), donc le
 * rejeu ne corrige RIEN et les cases restent celles du jeu, pas celles du replay. Pour un test
 * de déterminisme, une case fausse suffit à tout invalider.
 *
 * ⛔ CE N'EST **PAS** `UnitDeployment_RemoveAllUnitsFromBoard`, ET C'EST MESURÉ.
 * Son corps énumère le service `this+0x18` par le slot d'interface `0x22` et retire par le slot
 * `0x1f` -- ce sont les unités RÉELLEMENT DÉPLOYÉES. En phase de déploiement il y en a ZÉRO :
 * la boucle tourne à vide, l'appel rend `ok`, et le HUD garde ses cinq placeholders. Mesuré le
 * 2026-08-20 -- les cinq poses suivantes ont été refusées (« déjà un placeholder ») et le roster
 * continuait d'afficher tout comme placé. Un `ok` de cet appel-là ne prouve RIEN.
 *
 * LE RACCOURCI EST LE BOUTON LUI-MÊME : `UnitDeploymentHud$$HandleOnRemoveAllHeroesPressed()`
 * (0 paramètre), que `armerClear` ANCRE DÉJÀ -- on invoque donc exactement ce qu'on observe,
 * plutôt que de reconstituer un retrait unité par unité.
 *
 * ⚠ SI `deploymentClearArmer` EST ARMÉ, cet appel déclenche AUSSI notre relais, donc un
 * `retirerDuRunner(null)`. En régime placeholders il est éteint, et c'est ce qui rend l'appel
 * inoffensif -- pas une propriété du bouton.
 *
 * ⚠ ET ON RELIT. Le retrait transite par le flux de bataille : il ne se voit pas dans la frame de
 * l'appel (même décalage que la pose, mesuré « instantané à 5, réel à 4 une seconde plus tard »).
 * Rendre `ok` sans avoir vu le compte tomber, c'est exactement le mensonge qu'on vient de payer.
 *
 * ⛔ ENFILÉ, comme la pose : invoquer un natif depuis un callback d'interception fige le jeu.
 */
function viderLePlateauParFsm(): Promise<Record<string, unknown>> {
    return queueOnMainThread((): Record<string, unknown> => {
        const e = etatDuDeploiement();
        if ("ok" in e) {
            return { ok: false, error: "état du déploiement NON LISIBLE (" + e.error
                + ") -- ce n'est PAS « plateau déjà vide »" };
        }
        if (e.placeholders === 0) return { ok: true, otes: 0, voie: "rien à vider" };
        const hud = assurerHud();
        if (hud === null) {
            return { ok: false, error: "aucun `UnitDeploymentHud` -- ni capté à son `Show`, ni "
                + "rendu par la scène. Le clear est INJOUABLE, ce n'est pas « déjà vide »." };
        }
        const k = findClassAnywhere(NS_HUD, CLS_HUD);
        const mi = k ? findMethodByParamCount(k, "HandleOnRemoveAllHeroesPressed", 0) : null;
        if (!mi) {
            return { ok: false, error: "`UnitDeploymentHud$$HandleOnRemoveAllHeroesPressed` "
                + "INTROUVABLE (0 paramètre)" };
        }
        try {
            invokeMethod(mi.info, hud, []);
        } catch (err) { return { ok: false, error: "LEVÉ : " + (err as Error).message }; }
        return { ok: true, avant: e.placeholders, voie: "bouton CLEAR du HUD" };
    }).then((r) => {
        const rr = r as { ok?: boolean };
        if (rr.ok !== true) return r as Record<string, unknown>;
        // LA RELECTURE, et c'est elle qui fait foi -- pas l'appel.
        return queueOnMainThread(() => {
            const e2 = etatDuDeploiement();
            if ("ok" in e2) {
                return { ok: false, error: "après retrait, état NON LISIBLE : " + e2.error };
            }
            if (e2.placeholders !== 0) {
                return { ok: false, error: `${e2.placeholders} placeholder(s) SUBSISTENT après `
                    + "retrait -- le clear n'a pas mordu" };
            }
            return { ...(r as Record<string, unknown>), verifie: true };
        }) as Promise<Record<string, unknown>>;
    });
}

/** Images de pump laissées passer entre un retrait et la pose qui prend sa place. */
const DELAI_REMPLACEMENT = 6;

/**
 * Enfile une pose APRÈS `reste` images de pump.
 *
 * ⛔ On repasse par la FILE à chaque image, on ne dort pas : une attente bloquante dans la file
 * du thread principal FIGE le jeu. Même idiome que `verifierPuisNettoyer`.
 *
 * ⚠ POURQUOI ATTENDRE. Le retrait ne prend effet qu'au passage du flux de bataille
 * (`IdunBattle.View.BattleStream.StepHandlers.RemoveUnitStepHandler`) : une pose émise dans la
 * même image tombe sur une case ENCORE OCCUPÉE, et une pose sur case occupée échoue EN SILENCE
 * (mesuré le 2026-08-17 : `ultraApothecary` sur la case de `ultraTigurius`).
 */
function poserApresDelai(p: Pose, reste: number): void {
    if (reste <= 0) { poserUnHerosParFsm(p); return; }
    queueOnMainThread(() => ({ attendre: true })).then(
        () => poserApresDelai(p, reste - 1),
        (e) => tracerPose({ ok: false, unitId: p.unitId, error: String(e) }));
}

function armerBouton(): true | Refus {
    if (listenerBouton) return true;
    const k = findClassAnywhere(NS_BOUTONS, CLS_BOUTONS);
    if (!k) return refus(`\`${NS_BOUTONS}.${CLS_BOUTONS}\` INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(k, "UpdateState", 5);
    if (!mi) return refus(`\`${CLS_BOUTONS}$$UpdateState\` INTROUVABLE (5 paramètres)`);
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`UpdateState\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus(`REFUS : \`${CLS_BOUTONS}$$UpdateState\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${t.retA}) -- adresse PARTAGÉE. Cf. §8.`);
    }
    listenerBouton = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            boutonFires++;
            const recu = args[2].toInt32();
            const mn = args[4].toInt32();
            const mx = args[5].toInt32();
            // ⛔ CE CALLBACK N'INVOQUE RIEN, ET C'EST LA LEÇON D'UN GEL.
            // La version précédente appelait `compterSurLePlateau()` ICI : elle invoquait donc
            // deux natifs et parcourait un dictionnaire DEPUIS UN CALLBACK D'INTERCEPTION, sur le
            // thread de rendu, à CHAQUE rafraîchissement du bouton. C'est le motif que le dépôt
            // interdit (« ne jamais invoquer un natif depuis un hook »), et le jeu s'est figé.
            // Le compte est désormais calculé HORS hook (`deploymentBoutonArmer {rafraichir}`)
            // et seulement LU ici.
            const surPlateau = compteCache;
            const plateau: Record<string, number | string> = compteCacheDetail
                ?? { cache: "jamais calculé -- appeler `rafraichir: true`" };
            // Ordre : consigne explicite > compte dérivé du plateau > ce que le HUD croit.
            // ⚠ On ne descend JAMAIS sous `recu` : le HUD sait ce qu'il a posé lui-même, et une
            // dérivation ratée ne doit pas RETIRER des unités qu'il a comptées.
            const derive = surPlateau !== null ? Math.max(recu, surPlateau) : recu;
            const impose = boutonImpose !== null ? boutonImpose : derive;
            if (impose !== recu) args[2] = ptr(impose);
            if (boutonObs.length < 32) {
                boutonObs.push({ recu, impose, min: mn, max: mx,
                                 source: boutonImpose !== null ? "consigne"
                                     : surPlateau !== null ? "plateau" : "HUD (non dérivé)",
                                 plateau });
            }
        },
    });
    Interceptor.flush();
    return true;
}

// ============================================================================
// LE DÉMARRAGE — le capteur qui tranche entre « composer par l'écran » et « inventer ».
//
// `UnitDeploymentHud$$HandleOnStartBattleTapped` relaie les unités posées à
// `_callbacksDelegate` (`UnitDeploymentState`, mesuré) dont le slot 3 est :
//
//     UnitDeploymentState$$StartBattle(units) :
//         ok = source.<slot 0x31>(units.<champ +0x18>)
//         si ok  : source.<slot 0x59>(units, &resultat)
//                  si echec : <slot 0x1d>(1)        <- CHEMIN D'ECHEC
//         sinon  : fabrique un objet de repli
//         this.<slot 0x69>(resultat)                <- demarrage reel
//
// ⚠ DEUX SLOTS PORTÉS PAR LA SOURCE DE MODE DE JEU — exactement l'endroit où la sandbox nous a
// déjà stubbés deux fois (`GetUnitsForDeploymentHUD` rendait un conteneur vide,
// `AmountOfUnlockedUnits` un `return 0` dédupliqué). Savoir si elle les implémente décide du
// design : si oui, on compose entièrement par l'écran (clear et start natifs, cohérents) ; si
// non, il faut écrire la conversion placeholder -> unité réelle, et ce chemin-là n'a AUCUN
// précédent dans le binaire.
//
// ⛔ Le callback ne fait que des LECTURES DE MÉMOIRE : pas une invocation. C'est la leçon des
// deux gels de ce soir. La résolution des noms se fait après coup, par RPC.

const NS_ETAT = "IdunBattle.View.FSM.UnitDeployment";
const CLS_ETAT = "UnitDeploymentState";
let listenerStart: InvocationListener | null = null;
const startTrace: Array<Record<string, unknown>> = [];

function armerStart(): true | Refus {
    if (listenerStart) return true;
    const k = findClassAnywhere(NS_ETAT, CLS_ETAT);
    if (!k) return refus(`\`${NS_ETAT}.${CLS_ETAT}\` INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(k, "StartBattle", 1);
    if (!mi) return refus(`\`${CLS_ETAT}$$StartBattle\` INTROUVABLE (1 paramètre)`);
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`StartBattle\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus(`REFUS : \`${CLS_ETAT}$$StartBattle\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${t.retA}) -- adresse PARTAGÉE. Cf. §8.`);
    }
    // Les offsets viennent du décompilé et sont des positions de CHAMP, pas des adresses :
    // `this+0x28` = la source interrogée, `this+0x18` = le relais de démarrage.
    listenerStart = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            const self = this as unknown as { e: Record<string, unknown> };
            self.e = {};
            try {
                const ceci = args[0];
                const units = args[1];
                self.e.units = units.toString();
                self.e.unitsNul = units.isNull();
                if (!units.isNull()) {
                    self.e.classeUnits = classeDerriere(units).classe;
                    self.e.tailleUnits = tailleListe(units);
                }
                const src = ceci.add(0x28).readPointer();
                self.e.source = src.toString();
                self.e.classeSource = src.isNull() ? null : classeDerriere(src).classe;
                const relais = ceci.add(0x18).readPointer();
                self.e.classeRelais = relais.isNull() ? null : classeDerriere(relais).classe;
            } catch (e) { self.e.erreur = (e as Error).message; }
        },
        onLeave(retval) {
            const self = this as unknown as { e: Record<string, unknown> };
            self.e.retour = retval.toInt32() & 0xff;
            // ⚠ `1` est le retour du CHEMIN D'ECHEC (`<slot 0x1d>(1)` puis `return true`) :
            // un « true » ici ne veut donc PAS dire que la bataille a démarré.
            self.e.lecture = (self.e.retour === 1)
                ? "retour 1 -- c'est la valeur du CHEMIN D'ECHEC du décompilé, pas un succès"
                : "retour 0 -- passé par le démarrage réel (slot 0x69)";
            if (startTrace.length < 16) startTrace.push(self.e);
            // ⛔ ON ENFILE, ON N'INVOQUE RIEN ICI. C'est LE point de prise de la mémoire : la
            // composition ne bougera plus, et le plateau la porte en entier.
            if (memoireAuto) instantanerAuStart();
        },
    });
    Interceptor.flush();
    return true;
}

function etatPool(): Record<string, unknown> {
    const src = getCampaignGameModeSourcePtr();
    const p = sourcePreteuse();
    return {
        // ⚠ LE PRÊTEUR DEMANDÉ, ET LE PRÊTEUR RÉELLEMENT ARMÉ -- publier le premier seul serait
        // pire que rien. Mesure du 2026-08-21 : `preteurDelegation` disait `guildWar` alors que
        // les quatre délégations restaient armées sur la CAMPAGNE (cf. `armerUneDelegation`), et
        // ce statut n'exposait NI l'un NI l'autre. Il ne publiait que `sourceCampagne`, qu'on lit
        // alors naturellement comme « le prêteur » -- ça m'a fait diagnostiquer à côté deux fois.
        preteur: p.nom,
        preteurPtr: p.ptr && !p.ptr.isNull() ? p.ptr.toString() : null,
        // TRI-ÉTAT : `null` = pas de source capturée, ce qui n'est PAS « rien à déléguer ».
        // (!)CE N'EST PAS LE PRÊTEUR -- c'est la source de campagne captée par l'amorce, qui ne
        // sert que si `preteur === "campagne"`.
        sourceCampagne: src && !src.isNull() ? src.toString() : null,
        // LE ROSTER EMPRUNTÉ, EN CLAIR. Il était lu, mis en cache et versé dans la liste du jeu
        // sans jamais être publié : impossible de savoir CE QUE le HUD a reçu, ni de s'en servir
        // ailleurs (ex. peupler `BC.Units` pour que ces unités aient un prefab). `null` = pas
        // encore emprunté, ce qui n'est PAS « roster vide ».
        rosterEmprunte: cacheRoster(p.nom),
        delegations: delegations.map((d) => ({
            nom: d.nom, role: d.role, arme: d.listener !== null,
            // `null` = jamais armée. Un écart avec `preteur` ci-dessus signale une résolution
            // PÉRIMÉE -- c'est le symptôme qui n'avait aucun capteur.
            preteurArme: d.preteurArme,
            fires: d.fires, emprunts: d.emprunts, passesFiltre: d.passesFiltre,
            dernier: d.dernier, ancrage: d.ancrage,
        })),
    };
}

function etatPhase(): Record<string, unknown> {
    return {
        arme: relaisListener !== null,
        enableArme: enableListener !== null,
        forcer: forcerPhase,
        relaisFires, relaisForces,
        relaisRetours, enableObservations,
        ancrage,
    };
}

export function register(ctx: Ctx): void {
    /** OBSERVER / DÉSARMER. `{ armer: true }` pose le hook en régime transparent. */
    ctx.rpc.deploymentDraftArmer = (body?: { armer?: boolean }): Promise<unknown> | unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, arme: listener !== null, fires,
                     unitesPosees: unites ? unites.length : null, observations,
                     dernierRemplissage,
                     note: "passer { armer: true } pour observer, { armer: false } pour retirer" };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (listener) { listener.detach(); Interceptor.flush(); listener = null; }
                unites = null;
                return { ok: true, arme: false, action: "retire", fires };
            }
            const r = armer();
            if (r !== true) return r;
            return { ok: true, arme: true, fires, observations,
                     ancrage: `IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$${METHODE}`,
                     note: "régime OBSERVER -- rien n'est écrit tant que `deploymentDraftUnites` "
                         + "n'a pas posé d'ids" };
        });
    };

    /** REMPLIR. Exige une observation préalable QUI A IDENTIFIÉ la classe du retour. */
    ctx.rpc.deploymentDraftUnites = (body?: {
        unites?: string[] | null; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        if (!body || body.unites === undefined) {
            return { ok: true, lecture: true, unitesPosees: unites, fires,
                     observations, dernierRemplissage };
        }
        return queueOnMainThread(() => {
            if (body.unites === null) {
                unites = null;
                return { ok: true, action: "retire", note: "hook redevenu TRANSPARENT" };
            }
            if (!Array.isArray(body.unites) || body.unites.some((u) => typeof u !== "string")) {
                return refus("`unites` doit être un tableau de chaînes (ids d'unité), ou null");
            }
            if (listener === null) {
                return refus("hook NON ARMÉ -- jouer `deploymentDraftArmer { armer: true }` "
                    + "d'abord, puis ouvrir l'écran de déploiement pour OBSERVER");
            }
            // Le cran qui rend ce module honnête : on ne remplit pas un conteneur qu'on n'a
            // jamais vu. Une observation qui n'a identifié AUCUNE classe = on refuse, en le
            // disant, plutôt que d'écrire dans un pointeur supposé.
            const vue = observations.find((o) => o.classe !== null);
            if (!vue) {
                return refus("AUCUNE observation n'a identifié la classe du retour ("
                    + `${observations.length} passage(s), ${fires} fire(s)). \`PooledList\` est un `
                    + "TYPE VALEUR : sa disposition doit être MESURÉE avant qu'on y écrive. "
                    + "Ouvrir l'écran de déploiement d'une sandbox, relire `deploymentDraftArmer`.");
            }
            if (body.confirmer !== true) {
                return refus("`confirmer: true` exigé : au prochain affichage de l'écran de "
                    + `déploiement, ce hook ÉCRIRA dans le conteneur rendu (\`${vue.classe}\`).`);
            }
            unites = body.unites.slice();
            return { ok: true, unitesPosees: unites.length, classeVue: vue.classe,
                     note: "posé -- l'écriture aura lieu au PROCHAIN appel de "
                         + `\`SandboxGameModeSource$$${METHODE}\`` };
        });
    };

    /** ÉTAT du hook de phase de déploiement. Lecture pure. */
    ctx.rpc.deploymentPhaseStatus = (): unknown => ({ ok: true, lecture: true, ...etatPhase() });

    /** Débloque le bouton START quand les unités sont PRÉ-POSITIONNÉES (venues de `bc.Units`,
     *  donc invisibles de `_currentlyPlacedUnits`). Force le COMPTE reçu par le relais. */
    /**
     * DÉCLARE AU HUD les unités DÉJÀ SUR LE PLATEAU, par SA PROPRE méthode.
     *
     * ⚠ POURQUOI FORCER LE COMPTE NE SUFFIT PAS. `deploymentBoutonArmer` réécrit l'argument que
     * `UpdateState` reçoit : ça change l'APPARENCE du bouton, rien d'autre. Le chemin de
     * démarrage, lui, relit `_currentlyPlacedUnits` — mesuré : START s'allume puis répond
     * « il faut positionner une unité », parce que la liste est toujours vide.
     *
     * On n'écrit donc PAS dans cette liste : on appelle `TryMarkUnitAsPlaced`, la méthode que le
     * jeu emploie lui-même à chaque pose, une fois par unité du joueur présente sur le plateau.
     * La comptabilité du HUD rejoint la réalité au lieu d'être maquillée.
     *
     * ⚠ `TryMarkUnitAsPlaced` est ANCRÉ par `deploymentHudArmer` : on l'invoque depuis la file du
     * thread principal, jamais depuis un callback — c'est cette distinction qui a gelé le jeu.
     */
    /**
     * LE COMMIT DE DÉPLOIEMENT : rejoue les poses de l'écran en `AddUnitMessage` sur le runner
     * VIVANT. Les placeholders deviennent des unités RÉELLES, à leur place, sans remontage.
     *
     * ⚠ POURQUOI CE CHEMIN, ET PAS CELUI DU JEU. Dans TOUS les chemins natifs (pose manuelle
     * comme `DeployBattleLineup`), le déploiement ne manipule que des `PlaceholderUnitView` ; la
     * conversion en unités réelles est faite par `IGameModeSource.HandleStartMatch`. Or
     * `SandboxGameModeSource` **ne l'implémente pas** (mesuré : absent de la table, retombe sur
     * `AGameModeSource`), d'où la sortie immédiate -- le combat démarrait sans unité joueur.
     *
     * ⛔ ET ON NE PORTE PAS L'IMPLÉMENTATION DE RÉFÉRENCE. `CampaignGameModeSource$$HandleStartMatch`
     * appelle `GenerateNewBattleId` puis émet l'événement de chargement : c'est le chemin qui
     * CONSOMME UN JETON sur le compte réel. L'absence côté sandbox est donc PROTECTRICE, et la
     * copier ferait payer chaque essai de draft.
     *
     * La voie retenue est celle que le harnais RL emploie déjà : `AddUnitMessage` appliqué au
     * runner (`launch.ts` : « apply AddUnitMessages for each player placement, then StartMatch »).
     * `SpawnSource = Deployment (5)` par défaut, écrit au champ +0x28 comme `applyAddUnitSrc`.
     */
    /**
     * LA MÉMOIRE DE DÉPLOIEMENT — pour que le RETRY reparte avec l'équipe déjà composée.
     *
     * Armée, elle retient chaque pose appliquée et la rejoue quand la phase de déploiement
     * revient (le `Show` du HUD). `{ oublier: true }` la vide ; sans corps, elle se lit.
     *
     * ⚠ Le rejeu ne part QUE si le camp du joueur est vide -- c'est l'état du plateau qui
     * garde, pas un drapeau. Un `Show` sur un plateau déjà peuplé ne doit rien doubler.
     */
    ctx.rpc.deploymentMemoire = (body?: {
        armer?: boolean; oublier?: boolean; rejouer?: boolean; confirmer?: boolean;
        poser?: { poses?: Array<{ unitId: string; playerId: number; col: number; row: number }>;
                  mow?: { unitId: string; playerId: number; position: number } | null };
    }): unknown => {
        const etat = () => ({
            arme: memoireAuto, poses: memoirePoses.map((p) => ({
                unitId: p.unitId, playerId: p.playerId, col: p.col, row: p.row,
            })),
            // La MoW est SÉPARÉE, parce que son chemin natif l'est : elle n'a ni colonne ni
            // ligne. La publier à part évite de la croire absente quand on lit `poses`.
            mow: memoireMoW,
            // `null` = en dernier. Publié parce que c'est ce qui décide la POSITION de la machine
            // dans l'ordre de conversion, et qu'un appelant qui le croit sans le lire se trompe.
            mowIndex: memoireMoWIndex,
            vuesJeu: vuesJeu === null ? null : vuesJeu.toString(),
            // ⚠ SANS CE CAPTEUR, L'INSTANTANÉ NE SE PREND JAMAIS. Le publier évite de lire
            // `arme: true` comme « la mémoire se remplira » alors qu'elle restera vide.
            capteurStartArme: listenerStart !== null,
            rejeux: memoireRejeux, dernier: memoireDernier,
            // À QUI la mémoire appartient, et si un rejeu est ENCORE autorisé. Sans ces deux-là,
            // « armé » se lit comme « va rejouer » alors que le jeton peut être consommé.
            bataille: memoireBataille, rejeuArme: memoireRejeuArme,
        });
        if (body?.oublier === true) {
            memoirePoses.length = 0; memoireMoW = null; memoireMoWIndex = null;
            memoireBataille = null; memoireRejeuArme = false;
            // ⚠ LES POINTEURS DE LA BATAILLE PRÉCÉDENTE PARTENT AVEC LA MÉMOIRE, et c'est ici que
            // ça doit se faire : ce verbe est ce que l'appelant joue AVANT chaque montage
            // (`sandbox_gw.py` : « memoire de pose VIDEE avant montage »). Cf.
            // `oublierLesPointeursDeLaBatailleMorte` pour ce que ça a coûté.
            const vides = oublierLesPointeursDeLaBatailleMorte();
            memoireDernier = vides.length === 0
                ? "mémoire vidée (aucun pointeur en cache)"
                : `mémoire vidée | pointeurs oubliés : ${vides.join(", ")}`;
            return { ok: true, action: "oubliee", pointeursOublies: vides, ...etat() };
        }
        // POSER une mémoire venue du DEHORS.
        //
        // ⚠ CE QUI SURVIT À QUOI, MESURÉ le 2026-08-17 -- et je l'avais écrit à l'envers.
        // La mémoire vit dans des variables de CE script : elle survit donc parfaitement à un
        // REMONTAGE (retraite + forge + BC + `sandboxModeStart`), et c'est vérifié
        // (`rejeux` 2 -> 3, les cinq unités reposées aux mêmes cases, MoW comprise).
        // Ce qu'elle NE survit PAS, c'est un REINJECT : recharger le bundle repart de zéro.
        // D'où cette entrée -- l'appelant relit avant, repose après, et rien n'est perdu.
        if (body?.poser !== undefined) {
            memoirePoses.length = 0;
            for (const p of body.poser.poses ?? []) {
                if (typeof p?.unitId === "string" && p.unitId !== "") memoriser(p as Pose);
            }
            memoireMoW = body.poser.mow ?? null;
            // `mowIndex` ABSENT != `mowIndex: 0`. Un appelant qui ne connaît pas ce champ doit
            // retrouver le comportement d'avant (MoW en dernier), pas la poser en tête.
            const mi = (body.poser as { mowIndex?: unknown }).mowIndex;
            memoireMoWIndex = typeof mi === "number" && isFinite(mi) ? Math.trunc(mi) : null;
            memoireDernier = `mémoire POSÉE depuis l'extérieur : ${memoirePoses.length} pose(s)`
                + (memoireMoW ? ` + MoW ${memoireMoW.unitId}` : " (aucune MoW)")
                + (memoireMoWIndex === null ? "" : ` (MoW intercalée en ${memoireMoWIndex})`);
            return { ok: true, action: "posee", ...etat() };
        }
        if (body?.rejouer === true) {
            if (body.confirmer !== true) {
                // (!)CE MESSAGE ANNONÇAIT DES `AddUnitMessage` -- FAUX depuis la suppression de
                // la voie commit. `rejouerMemoire` VIDE le plateau puis repose par l'étage FSM,
                // donc en placeholders. Un avertissement périmé invente un risque disparu et
                // décrédibilise ceux qui restent : ce rejeu MUTE bien l'écran, et c'est pour ÇA
                // qu'il exige `confirmer`.
                return refus("`confirmer: true` exigé : le rejeu VIDE le plateau puis repose "
                    + "les unités mémorisées par l'étage FSM -- il modifie l'écran de "
                    + "déploiement en cours");
            }
            rejouerMemoire();
            return { ok: true, action: "rejeu ENFILÉ", ...etat() };
        }
        if (body?.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` : la composition est PRISE EN UNE FOIS à l'appui sur "
                         + "START (instantané du plateau réel), puis REJOUÉE au retour de la "
                         + "phase de déploiement (retry). Le rejeu ne part que si le camp du "
                         + "joueur est VIDE." };
        }
        memoireAuto = body.armer === true;
        // ⚠ L'INSTANTANÉ SE PREND AU START : sans le capteur de START, la mémoire ne se remplit
        // JAMAIS et le retry reviendrait à vide -- en silence. On l'arme donc ici, et on DIT si
        // l'armement a échoué plutôt que de rendre un `arme: true` qui ne tiendrait rien.
        let start: true | Refus | "non demandé" = "non demandé";
        if (memoireAuto) start = armerStart();
        return { ok: true, action: memoireAuto ? "arme" : "retire", ...etat(),
                 capteurStart: start === true ? "ARMÉ"
                     : (start === "non demandé" ? start : "REFUSÉ : " + start.error) };
    };

    // (!)`deploymentCommit` EST SUPPRIME (2026-08-21). Il appliquait en un coup les
    // `AddUnitMessage` de tout un plateau au runner VIVANT -- la voie commit, sous sa forme
    // explicite. Elle est partie entiere : la pose passe TOUJOURS par l'etage FSM, donc par
    // un `PlaceholderUnitView` que le START natif convertit avec les autres.

    /** Capteur PUR sur `UnitDeploymentState$$StartBattle` — le relais du bouton START. */
    ctx.rpc.deploymentStartArmer = (body?: { armer?: boolean }): unknown => {
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, arme: listenerStart !== null,
                     passages: startTrace.slice(-8) };
        }
        if (body.armer === false) {
            if (listenerStart) { try { listenerStart.detach(); } catch { /* best effort */ } }
            listenerStart = null;
            return { ok: true, arme: false };
        }
        const r = armerStart();
        if (r !== true) return r;
        return { ok: true, arme: true,
                 note: "appuyer sur START, puis relire ce RPC sans argument" };
    };

    /**
     * VIDANGER LA POMPE DANS LE TICK DE L'UI plutôt que dans celui de la vue de bataille.
     *
     * Le HUD n'a pas d'`Update` : il est piloté par `UnityEngine.EventSystems.EventSystem$$Update`.
     * Nos travaux, eux, partaient de `IdunGameViews$$Update` -- en pleine frame de la vue de
     * bataille -- et tout appel manipulant des widgets y LÈVE. Ce RPC déplace le point de
     * vidange ; il est EXCLUSIF (cf. `runtime/main-pump.ts`).
     */
    ctx.rpc.pompeUiArmer = (body?: { armer?: boolean }): unknown => {
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...pompeUiEtat() };
        }
        return pompeUiArmer(body.armer === true);
    };

    /**
     * BASCULER LE HUD EN SÉLECTION « MACHINES OF WAR » — ou en revenir.
     *
     * `idun.ui.UnitDeploymentHud$$HandleOnSwitchToMachinesOfWarUnitsTapped()` (aucun paramètre
     * managé) : c'est l'onglet que le joueur tape avant de choisir sa machine.
     *
     * ⚠ CE RPC EXISTE POUR UNE MESURE, PAS SUR UNE CERTITUDE. Le START lève parce que son
     * prédicat (`<HandleOnStartBattleTapped>b__150_0`) cherche CHAQUE unité posée dans
     * `_allUnitModels` (`+0x240`, `Dictionary`, 102 entrées mesurées) et LÈVE SANS GARDE quand
     * la clé manque -- ce qui est le cas de la MoW. Reste à établir ce qui l'y met : le
     * basculement lui-même ne touche QUE `_unitModels` (`+0x238`, vidé par
     * `PrepareForStandardUnitMachineOfWarSelectionSwitch`) au décompilé. On rend donc le compte
     * du dictionnaire AVANT et APRÈS, et c'est la mesure qui tranchera.
     *
     * ⛔ ÉCRITURE : détruit des widgets, réinitialise les filtres, ré-affiche la collection.
     */
    ctx.rpc.deploymentMowBasculer = (body?: { confirmer?: boolean; retour?: boolean }):
        Promise<unknown> | unknown => {
        if (body?.confirmer !== true) {
            return refus("ECRITURE -- exige `confirmer: true`. Ce RPC rejoue l'onglet "
                + "« Machines of War » du HUD (widgets détruits, filtres réinitialisés).");
        }
        const methode = body?.retour === true
            ? "HandleOnSwitchToStandardUnitsTapped"
            : "HandleOnSwitchToMachinesOfWarUnitsTapped";
        return queueOnMainThread((): Record<string, unknown> => {
            if (hudInstance === null || hudInstance.isNull()) {
                return { ok: false, error: "aucun `UnitDeploymentHud` capturé -- il ne s'attrape "
                    + "qu'à son `Show`, donc à l'AFFICHAGE de la phase de déploiement." };
            }
            const k = findClassAnywhere(NS_HUD, CLS_HUD);
            const mi = k ? findMethodByParamCount(k, methode, 0) : null;
            if (!mi) return { ok: false, error: `\`${methode}\` INTROUVABLE (0 paramètre)` };
            // ⚠ VÉRIFIER LE CORPS RÉSOLU. IL2CPP déduplique les corps triviaux : `findMethod`
            // peut rendre une adresse PARTAGÉE, et on invoquerait alors autre chose sans que
            // rien ne le dise. On publie l'adresse Ghidra et la tête, comme le fait déjà
            // l'armement du relais de START -- au lecteur de confronter au décompilé.
            const va = ghidraVA(mi.ptr);
            const tete = lireTete(mi.ptr);
            const compte = (): number | null => {
                try {
                    const d = hudInstance!.add(0x240).readPointer();
                    if (d.isNull()) return null;
                    const off = getFieldOffset(d.readPointer(), "_count");
                    return off < 0 ? null : d.add(off).readS32();
                } catch { return null; }
            };
            const avant = compte();
            try { invokeMethod(mi.info, hudInstance, []); }
            catch (e) {
                return { ok: false, methode, ghidraVA: va, tete, allUnitModelsAvant: avant,
                         error: "LEVÉ : " + (e as Error).message };
            }
            return { ok: true, methode, ghidraVA: va, tete,
                     allUnitModelsAvant: avant, allUnitModelsApres: compte(),
                     selectionMoW: (() => {
                         try { return hudInstance!.add(0x221).readU8() !== 0; } catch { return null; }
                     })() };
        });
    };

    /**
     * APPUYER SUR START — `idun.ui.UnitDeploymentHud$$HandleOnStartBattleTapped(success)`.
     *
     * ⚠ POURQUOI CE POINT-LA, ET PAS `UnitDeploymentState$$StartBattle`. Ce dernier prend la
     * LISTE des unités posées, que le HUD construit lui-même : la fabriquer à la main, c'est
     * inventer ce que l'écran sait produire. Le handler du bouton, lui, filtre
     * (`_placedUnits.FindAll(predicate)`), mappe, puis relaie au slot 3 de son
     * `_callbacksDelegate` — donc UNE invocation reproduit exactement le clic.
     *
     * ⚠ C'EST CE PASSAGE QUI CRÉE LA MoW. Mesuré le 2026-08-19 : après un START joué à la main,
     * les pas produits sont `AddMachineMessage` (2 271 car.) puis `StartBattleMessage`
     * (11 980 car.) — les DEUX valeurs de la référence, au caractère. Le placeholder de vue ne
     * suffit pas, `applyAddMachine` crashe : le START est la seule voie juste.
     *
     * ⛔ ÉCRITURE. Les trois gardes du décompilé sont LUES ET RENDUES avant l'appel — un refus
     * silencieux du natif se lirait sinon comme « ça n'a rien fait, réessaie ».
     */
    /**
     * LES ENTRÉES DE `_currentlyPlacedUnits`, ET LE PRÉDICAT DE START ÉPROUVÉ SUR CHACUNE.
     *
     * ⚠ POURQUOI ENTRÉE PAR ENTRÉE, ET PAS UN VERDICT GLOBAL. `HandleOnStartBattleTapped` fait
     * `_currentlyPlacedUnits.FindAll(<HandleOnStartBattleTapped>b__150_0)` : UNE entrée qui lève
     * fait tomber tout le START, et le message natif ne dit PAS laquelle. Tant qu'on ne les
     * éprouve pas une par une, « ça lève » ne désigne personne — c'est exactement ce qui a fait
     * accuser tour à tour le prefab, la munition, le placeholder, le contexte de vidange.
     *
     * Le prédicat est un LECTEUR : il cherche la clé de l'entrée dans `_allUnitModels` et rend
     * `!IsMachineOfWar` (slot 0x37) -- donc `FindAll` EXCLUT les machines. Aucune écriture.
     *
     * ⚠ La taille d'élément est DÉRIVÉE (`class_instance_size` de la classe d'élément moins
     * l'en-tête d'objet), jamais recopiée du décompilé : elle est PUBLIÉE pour être confrontée
     * aux 32 octets que `b__150_0` copie, pas pour être crue.
     */
    ctx.rpc.deploymentPlacees = (body?: {
        tronquer?: number; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const tronquer = typeof body?.tronquer === "number" ? body.tronquer : null;
        if (tronquer !== null && body?.confirmer !== true) {
            return refus("ECRITURE -- `tronquer` exige `confirmer: true`. Il RÉÉCRIT le `_size` "
                + "de `_currentlyPlacedUnits` : les éléments au-delà deviennent invisibles du "
                + "HUD sans être détruits.");
        }
        return queueOnMainThread((): Record<string, unknown> => {
            if (hudInstance === null || hudInstance.isNull()) {
                return { ok: false, error: "aucun `UnitDeploymentHud` capturé" };
            }
            const k = findClassAnywhere(NS_HUD, CLS_HUD);
            if (!k) return { ok: false, error: `\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE` };
            const offPl = getFieldOffset(k, "_currentlyPlacedUnits");
            if (offPl < 0) return { ok: false, error: "champ `_currentlyPlacedUnits` ABSENT" };
            const lst = hudInstance.add(offPl).readPointer();
            if (lst.isNull()) return { ok: false, error: "`_currentlyPlacedUnits` est NULLE" };
            const kl = lst.readPointer();
            const offItems = getFieldOffset(kl, "_items");
            const offSize = getFieldOffset(kl, "_size");
            if (offItems < 0 || offSize < 0) {
                return { ok: false, error: `champs de \`List\` absents : _items=${offItems} `
                    + `_size=${offSize}` };
            }
            const taille = lst.add(offSize).readS32();
            if (tronquer !== null) {
                if (tronquer < 0 || tronquer > taille) {
                    return { ok: false, error: `\`tronquer\` HORS BORNES : ${tronquer} pour une `
                        + `liste de ${taille}` };
                }
                lst.add(offSize).writeS32(tronquer);
                return { ok: true, action: "tronque", avant: taille,
                         apres: lst.add(offSize).readS32() };
            }
            const items = lst.add(offItems).readPointer();
            if (items.isNull()) return { ok: false, error: "`_items` est NUL", taille };
            // Taille d'élément DÉRIVÉE de la classe d'élément du tableau, jamais supposée.
            // ⚠ Les trois helpers sont résolus PARESSEUSEMENT et peuvent valoir `null` sur un
            // build où l'export manque : on le DIT (`octetsParEntree: null`) au lieu de retomber
            // sur les 32 du décompilé, qui feraient lire des entrées décalées en silence.
            const kArr = items.readPointer();
            const kElem = class_get_element_class ? class_get_element_class(kArr) : null;
            const estVal = kElem !== null && class_is_valuetype !== null
                ? (class_is_valuetype(kElem) as number) !== 0 : null;
            let octets: number | null = null;
            if (estVal === true && class_instance_size !== null) {
                octets = (class_instance_size(kElem as NativePointer) as number)
                    - 2 * Process.pointerSize;
            } else if (estVal === false) { octets = Process.pointerSize; }
            if (octets === null || octets <= 0 || octets > 512) {
                return { ok: false, taille, octetsParEntree: octets, elementValeur: estVal,
                         error: "taille d'élément NON DÉRIVABLE -- pas de repli sur une "
                             + "constante, la lecture serait décalée sans le dire" };
            }
            const maxLength = items.add(3 * Process.pointerSize).readS32();
            const base = items.add(4 * Process.pointerSize);
            // Le prédicat, résolu PAR NOM. C'est un lecteur -- il ne mute rien.
            const mPred = findMethod(k, "<HandleOnStartBattleTapped>b__150_0");
            const entrees: Array<Record<string, unknown>> = [];
            for (let i = 0; i < Math.min(taille, 32); i++) {
                const p = base.add(i * octets);
                const e: Record<string, unknown> = { i, adresse: p.toString() };
                try {
                    const u8 = new Uint8Array(p.readByteArray(octets) as ArrayBuffer);
                    e.hex = Array.from(u8).map((b) => b.toString(16).padStart(2, "0")).join(" ");
                    e.nul = Array.from(u8).every((b) => b === 0);
                } catch (err) { e.hex = "ILLISIBLE : " + (err as Error).message; }
                if (mPred) {
                    try {
                        const r = invokeMethod(mPred.info, hudInstance!, [p]);
                        // Retour `bool` BOXÉ : la valeur vit à +0x10, pas sur le pointeur.
                        e.predicat = r !== null && !r.isNull()
                            ? (r.add(0x10).readU8() !== 0) : null;
                    } catch (err) { e.predicat = "LEVÉ : " + (err as Error).message; }
                } else { e.predicat = "`b__150_0` INTROUVABLE"; }
                entrees.push(e);
            }
            return { ok: true, taille, maxLength, octetsParEntree: octets,
                     elementValeur: estVal, predicatResolu: mPred !== null,
                     predicatVA: mPred ? ghidraVA(mPred.ptr) : null, entrees,
                     note: "`predicat: false` = machine of war (EXCLUE du relais, c'est normal) ; "
                         + "`predicat: LEVÉ` = clé ABSENTE d'`_allUnitModels` -- CELLE-LÀ fait "
                         + "tomber tout le START." };
        });
    };

    ctx.rpc.deploymentStartInvoquer = (body?: {
        confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        if (body?.confirmer !== true) {
            return refus("ECRITURE -- exige `confirmer: true`. Ce RPC APPUIE SUR START : il "
                + "commit le déploiement (MoW comprise) et DÉMARRE la bataille.");
        }
        return queueOnMainThread((): Record<string, unknown> => {
            const bloque = refusSiEmpilement(null, "HandleOnStartBattleTapped");
            if (bloque) return { ok: false, error: bloque.error };
            if (hudInstance === null || hudInstance.isNull()) {
                return { ok: false, error: "aucun `UnitDeploymentHud` capturé -- le HUD ne "
                    + "s'attrape qu'à son `Show`, donc à l'AFFICHAGE de la phase de "
                    + "déploiement. Ce n'est PAS « zéro unité »." };
            }
            const k = findClassAnywhere(NS_HUD, CLS_HUD);
            const mi = k ? findMethodByParamCount(k, "HandleOnStartBattleTapped", 1) : null;
            if (!mi) {
                return { ok: false,
                         error: "`HandleOnStartBattleTapped` INTROUVABLE (1 paramètre)" };
            }
            // Les gardes, dans l'ordre du décompilé. Offsets de CHAMP, lus avant d'écrire.
            const gardes: Record<string, unknown> = {};
            try {
                gardes.bloque_0x22c = hudInstance.add(0x22c).readU8();
                gardes.source_0x1a8 = hudInstance.add(0x1a8).readPointer().toString();
                gardes.callbacks_0x1b0 = hudInstance.add(0x1b0).readPointer().toString();
                const l = hudInstance.add(0x1b8).readPointer();
                gardes.posees_0x1b8 = l.isNull() ? null : tailleListe(l);
            } catch (e) { gardes.erreur = (e as Error).message; }
            if (gardes.bloque_0x22c !== 0) {
                return { ok: false, gardes,
                         error: "le HUD REFUSE (`+0x22c` non nul) -- START est déjà consommé "
                             + "ou verrouillé ; l'appeler ne ferait rien." };
            }
            if (gardes.callbacks_0x1b0 === "0x0" || gardes.source_0x1a8 === "0x0") {
                return { ok: false, gardes,
                         error: "relais ou source NULS -- le natif LÈVE sur ce chemin." };
            }
            try {
                // `success` est un booléen : type VALEUR, donc on transmet son ADRESSE.
                const vrai = Memory.alloc(1); vrai.writeU8(1);
                invokeMethod(mi.info, hudInstance, [vrai]);
            } catch (e) {
                return { ok: false, gardes, error: "LEVÉ : " + (e as Error).message };
            }
            return { ok: true, gardes, hud: hudInstance.toString(),
                     note: "l'appel est passé -- ça ne dit RIEN du démarrage. Le vérifier par "
                         + "`replaySteps` (on attend `AddMachineMessage` puis "
                         + "`StartBattleMessage`) et par `battleStatus.stageName == Running`." };
        });
    };

    ctx.rpc.deploymentBoutonMarquer = (body?: { confirmer?: boolean }):
        Promise<unknown> | unknown => {
        if (body?.confirmer !== true) {
            return refus("`confirmer: true` exigé : ce RPC APPELLE `TryMarkUnitAsPlaced` sur le "
                + "HUD vivant, une fois par unité du joueur présente sur le plateau");
        }
        return queueOnMainThread(() => marquerLesUnitesDuPlateau());
    };

    /** L'inventaire du plateau, les DEUX camps — lecture pure, aucune écriture. */
    ctx.rpc.deploymentPlateau = (): Promise<unknown> | unknown =>
        queueOnMainThread(() => {
            const u = unitesDuPlateau();
            if (!Array.isArray(u)) return refus("plateau non lisible : " + u);
            return { ok: true, lecture: true, unites: u,
                     duJoueur: u.filter((x) => x.duJoueur).length, total: u.length };
        });

    /** LE CLEAR QUI ÔTE POUR DE VRAI. Applique un `RemoveUnitMessage` par unité au runner
     *  VIVANT — le seul chemin qui atteigne une unité RÉELLE, celle que le clear natif ne sait
     *  pas voir parce qu'il ne connaît que les `PlaceholderUnitView`. */
    ctx.rpc.deploymentRetirer = (body?: {
        confirmer?: boolean; entityIds?: number[];
    }): Promise<unknown> | unknown => {
        if (body?.confirmer !== true) {
            return queueOnMainThread(() => {
                const u = unitesDuPlateau();
                if (!Array.isArray(u)) return refus("plateau non lisible : " + u);
                const cibles = body?.entityIds ?? u.filter((x) => x.duJoueur)
                    .map((x) => x.entityId);
                return { ok: true, lecture: true, aRetirer: cibles,
                         unites: u.filter((x) => cibles.indexOf(x.entityId) >= 0),
                         note: "`confirmer: true` exigé : ce RPC APPLIQUE des "
                             + "`RemoveUnitMessage` au runner VIVANT -- il modifie la bataille "
                             + "en cours" };
            });
        }
        // ⚠ ON ATTEND L'EFFET, ET LE VERDICT EN DÉPEND. `Apply` qui passe n'est pas « l'unité est
        // partie » -- mesuré le 2026-08-20, 5 `Apply` verts pour 5 entités TOUJOURS VIVANTES.
        // ~90 images de pump, soit environ une seconde à 60 images/s (même délai que
        // `verifierPuisNettoyer`).
        return (queueOnMainThread(
            () => retirerDuRunner(body.entityIds ?? null)) as
                Promise<Record<string, unknown>>)
            .then((r) => {
                if (r.ok !== true) return r;
                const cibles = (r.cibles as number[]) ?? [];
                return apresImages(90, (): Record<string, unknown> => {
                    const u = unitesDuPlateau();
                    if (!Array.isArray(u)) {
                        return { ...r, verifie: false, ok: false,
                                 verdict: "plateau NON RELISIBLE (" + u + ") -- le retrait n'est "
                                     + "ni confirmé ni infirmé. On ne le compte pas comme fait." };
                    }
                    const restants = u.filter((x) => cibles.indexOf(x.entityId) >= 0);
                    if (restants.length > 0) {
                        return { ...r, verifie: true, ok: false,
                                 survivantes: restants.map((x) => ({ entityId: x.entityId,
                                                                     unitId: x.unitId })),
                                 verdict: `RETRAIT INCOMPLET : ${restants.length} cible(s) sur `
                                     + `${cibles.length} sont TOUJOURS sur le plateau après 90 `
                                     + "images. Ne rien poser par-dessus : c'est exactement ce "
                                     + "qui a produit 10 unités pour 5 le 2026-08-20." };
                    }
                    return { ...r, verifie: true, ok: true,
                             verdict: `les ${cibles.length} cible(s) ont bien QUITTÉ le plateau` };
                });
            });
    };

    // (!)`deploymentRemplacer` EST SUPPRIME (2026-08-21) -- LE SEUL CHEMIN QUI CONTOURNAIT
    // ENCORE LE HUD. Il echangeait une unite sans passer par le clear, en deux verbes appliques
    // au runner VIVANT : `RemoveUnitMessage` sur la cible, puis `AddUnitMessage` de la
    // remplacante sur la case liberee.
    //
    // C'est la MEME forme que la voie commit supprimee la veille : une ecriture qui entre dans
    // le plateau SANS que le HUD la voie, donc une seconde comptabilite. Le HUD garde son
    // plafond a la POSE et ne compte que ses `PlaceholderUnitView` ; ce qui arrive par
    // `AddUnitMessage` lui reste invisible. Tant que ce chemin existait, le controle natif
    // n'etait pas exhaustif -- et c'est justement parce qu'il redevient exhaustif que
    // `deploymentBlocageStart` a pu partir (cf. le pave plus haut). Les deux devaient tomber
    // ensemble : garder l'un sans l'autre aurait laisse le trou ouvert ET le garde retire.
    //
    // Pour echanger une unite : la deposer par l'ecran (etage FSM) et reposer -- le chemin du
    // clic humain, celui que le HUD compte.

    /** Relais sur le bouton CLEAR de l'écran. Armé, un appui ôte AUSSI les unités réelles. */
    ctx.rpc.deploymentClearArmer = (body?: {
        armer?: boolean; confirmer?: boolean;
    }): unknown => {
        const etat = () => ({ arme: listenerClear !== null, actif: clearAuto,
                              fires: clearFires, dernier: clearDernier });
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` + `confirmer: true` : le clair de l'écran APPLIQUERA "
                         + "des `RemoveUnitMessage` sur la bataille en cours" };
        }
        if (body.armer === false) {
            if (listenerClear) { try { listenerClear.detach(); } catch { /* best effort */ } }
            listenerClear = null; clearAuto = false;
            return { ok: true, ...etat() };
        }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        const r = armerClear();
        if (r !== true) return r;
        clearAuto = true;
        return { ok: true, ...etat() };
    };

    /**
     * Relais sur la DÉPOSE unité par unité — le pendant de `deploymentClearArmer`, qui ne
     * couvre que le bouton « tout enlever ». Armé, ôter une unité du plateau ôte AUSSI
     * l'unité RÉELLE du runner. Cf. `retirerSiSurLePlateau` pour le chemin, mesuré.
     */
    ctx.rpc.deploymentDeposeArmer = (body?: {
        armer?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const etat = () => ({
            actif: deposeAuto,
            ancre: cheminsListeners["PutUnitIntoHand"] !== undefined,
            chemin: cheminsEtat["PutUnitIntoHand"] ?? null,
            dernier: deposeDernier, trace: deposeTrace,
        });
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` + `confirmer: true` : ôter une unité du plateau "
                         + "APPLIQUERA un `RemoveUnitMessage` sur la bataille en cours. Le "
                         + "chemin est `PutUnitIntoHand`, qui porte AUSSI la saisie depuis le "
                         + "roster -- c'est la présence sur le plateau qui les sépare." };
        }
        if (body.armer === false) { deposeAuto = false; return { ok: true, ...etat() }; }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        // ⚠ L'ANCRAGE VIT DANS `armerHud`, comme pour `deploymentSyncArmer` : sans lui, rien
        // ne tirera et l'armement rendrait un `actif: true` qui ne tient RIEN.
        const r = armerHud();
        if (r !== true) return r;
        deposeAuto = true;
        return { ok: true, ...etat() };
    };

    /** CAPTEUR PUR sur `IdunBattle.Runner.IdunRunner$$StartMatch` — n'écrit RIEN.
     *  À armer AVANT le montage : c'est tout l'intérêt de savoir s'il tire à ce moment-là. */
    ctx.rpc.deploymentRunnerStartArmer = (body?: { armer?: boolean }): unknown => {
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, arme: listenerRunnerStart !== null,
                     showsDuHud: showFires, passages: startMatchTrace };
        }
        if (body.armer === false) {
            if (listenerRunnerStart) {
                try { listenerRunnerStart.detach(); } catch { /* best effort */ }
            }
            listenerRunnerStart = null;
            return { ok: true, arme: false };
        }
        const r = armerRunnerStart();
        if (r !== true) return r;
        return { ok: true, arme: true,
                 note: "monter la bataille, drafter, appuyer START, puis relire sans argument" };
    };

    /** Fait de chaque pose une unité RÉELLE, immédiatement : `AddUnitMessage` sur le runner
     *  vivant, puis retrait du placeholder devenu doublon. C'est ce qui rend START opérant —
     *  sans lui la bataille démarre vide et se termine aussitôt. */
    /**
     * LA VOIE DE POSE DES HÉROS — runner direct (défaut) ou étage FSM.
     *
     * `armer: true` fait passer `deploymentMemoire {rejouer}` par
     * `StateMachineActions$$UnitDeployment_PlaceUnitOnBoard`, la méthode que le CLIC HUMAIN
     * invoque. Les héros deviennent alors des PLACEHOLDERS comptés par le HUD, au lieu d'unités
     * réelles invisibles de lui (START à 0/5, un seul placeholder dans la boucle du START).
     */
    /**
     * POSER LA MoW SEULE, À L'INSTANT CHOISI — sans passer par le rejeu de mémoire.
     *
     * ⚠ POURQUOI CE RPC EXISTE. `deploymentMemoire {rejouer}` pose les héros PUIS la MoW dans la
     * MÊME vague : les six appels sont enfilés d'affilée sur le thread principal. Le joueur, lui,
     * clique la machine plusieurs secondes après ses héros. Mesuré le 2026-08-20 : la pose
     * humaine DÉMARRE la bataille (`stageName = Running`) avec des arguments IDENTIQUES aux
     * nôtres (`blackForgefiend`, `playerId 11`, `position 2`, relevés par notre propre capteur
     * sur le clic). Ce n'est donc pas QUOI on passe -- reste QUAND.
     *
     * Et le rejeu de mémoire ne peut pas servir à l'éprouver : il REFUSE quand le plateau est
     * déjà peuplé (garde anti-doublon), ce qui est justement le cas après les héros.
     */
    ctx.rpc.deploymentMoWPoser = (body?: {
        unitId?: string; playerId?: number; position?: number; confirmer?: boolean;
    }): unknown => {
        if (body?.confirmer !== true) {
            return refus("ECRITURE -- exige `confirmer: true`. Ce RPC invoque l'étage FSM de "
                + "pose de Machine of War (`UnitDeployment_PlaceMachineOfWarUnitOnBoard`).");
        }
        if (typeof body.unitId !== "string" || body.unitId === "") {
            return refus("`unitId` exigé -- ce RPC ne devine aucune machine.");
        }
        if (typeof body.playerId !== "number" || typeof body.position !== "number") {
            return refus("`playerId` et `position` exigés (entiers) -- ils ne se devinent pas, "
                + "et un `position` faux pose la machine sur une AUTRE plateforme.");
        }
        rejouerLaMoW({ unitId: body.unitId, playerId: body.playerId, position: body.position },
                     );
        return { ok: true, enfile: true, unitId: body.unitId, playerId: body.playerId,
                 position: body.position,
                 note: "ENFILÉ sur le thread principal -- vérifier l'EFFET par "
                     + "`deploymentBoutonArmer` (placees) ou `observeBattle`, jamais ce retour." };
    };

    /** LA TRACE DES POSES — lecture pure. Il n'y a plus de voie à choisir, donc plus rien à
     *  armer : `deploymentPoseFsmArmer` et `deploymentPoseCommitArmer` sont SUPPRIMÉS avec la
     *  voie commit. Ce RPC ne garde que ce qu'ils publiaient d'utile, les derniers résultats. */
    ctx.rpc.deploymentPoseTrace = (): unknown =>
        ({ ok: true, lecture: true, faits: poseFsmTrace.slice(-8),
           note: "les poses passent TOUJOURS par l'étage FSM (placeholder) -- la voie "
               + "`AddUnitMessage` au runner est supprimée depuis le 2026-08-21." });

    /** Rend START vivant SANS geste manuel sur une BC pré-remplie : à chaque `Show`, les unités
     *  déjà présentes sont déclarées au HUD et le bouton est rafraîchi. */
    ctx.rpc.deploymentSyncArmer = (body?: {
        armer?: boolean; confirmer?: boolean; maintenant?: boolean;
    }): Promise<unknown> | unknown => {
        if (body?.maintenant === true) {
            return queueOnMainThread(() => marquerLesUnitesDuPlateau());
        }
        const etat = () => ({ actif: syncAuto, dernier: syncDernier });
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` + `confirmer: true` : chaque `Show` déclarera au HUD "
                         + "les unités déjà sur le plateau (invoque `TryMarkUnitAsPlaced`)" };
        }
        if (body.armer === false) { syncAuto = false; return { ok: true, ...etat() }; }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        // Le relais vit dans `Show`, qui est ancré par `armerHud` : sans lui, rien ne tirera.
        const r = armerHud();
        if (r !== true) return r;
        syncAuto = true;
        return { ok: true, ...etat() };
    };

    ctx.rpc.deploymentBoutonArmer = (body?: {
        armer?: boolean; compte?: number; confirmer?: boolean; rafraichir?: boolean;
    }): Promise<unknown> | unknown => {
        // Le calcul se fait ICI, sur la file du thread principal — JAMAIS dans le callback.
        if (body?.rafraichir === true) {
            return queueOnMainThread(() => {
                const d = compterSurLePlateau();
                compteCacheDetail = d;
                compteCache = typeof d.unitesDuJoueurHumain === "number"
                    ? d.unitesDuJoueurHumain : null;
                const sortie: Record<string, unknown> = { ok: true, compteCache, detail: d };
                // ⚠ SANS CE SECOND TEMPS, LE CACHE NE SERT À RIEN SUR DES UNITÉS PRÉ-POSITIONNÉES.
                // `UpdateButtons` n'a que cinq appelants (`Show`, `TryMarkUnitAsPlaced`,
                // `PutUnitIntoHand`, `RemoveUnit`, `HandleOnRemoveAllHeroesPressed`) : quand les
                // unités viennent de `bc.Units`, AUCUN ne se produit après le montage. Le bouton
                // reste donc figé sur l'état calculé à `Show`, où le cache n'existait pas encore.
                // On provoque donc le rafraîchissement.
                //
                // ⚠ On invoque `UpdateButtons`, qui n'est PAS ancré ; c'est `UpdateState`, qu'il
                // appelle, qui l'est. Et l'appel part de la FILE DU THREAD PRINCIPAL, pas d'un
                // callback d'interception — c'est cette distinction-là, et non l'ancrage, qui a
                // gelé le jeu deux fois ce soir.
                if (hudInstance === null || hudInstance.isNull()) {
                    sortie.rafraichi = false;
                    sortie.raison = "aucune instance de HUD captée (`Show` n'a pas tiré)";
                    return sortie;
                }
                const c = classeDerriere(hudInstance);
                if (c.classe !== CLS_HUD) {
                    sortie.rafraichi = false;
                    sortie.raison = `le pointeur de HUD ne porte plus \`${CLS_HUD}\` mais `
                        + `\`${c.classe ?? c.erreur}\` -- PÉRIMÉ, on n'invoque rien dessus`;
                    return sortie;
                }
                const kh = findClassAnywhere(NS_HUD, CLS_HUD);
                const mUp = kh ? findMethodByParamCount(kh, "UpdateButtons", 0) : null;
                if (!mUp) {
                    sortie.rafraichi = false;
                    sortie.raison = "`UnitDeploymentHud$$UpdateButtons` INTROUVABLE (0 paramètre)";
                    return sortie;
                }
                const avant = boutonFires;
                try { invokeMethod(mUp.info, hudInstance, null); }
                catch (e) {
                    sortie.rafraichi = false;
                    sortie.raison = "`UpdateButtons` a levé : " + (e as Error).message;
                    return sortie;
                }
                // Le TÉMOIN : le relais a-t-il vraiment re-tiré ? Sans lui, « rafraîchi » ne
                // dirait que « l'appel est passé », ce qui ne prouve rien.
                sortie.rafraichi = boutonFires > avant;
                sortie.relaisTirs = boutonFires - avant;
                sortie.dernier = boutonObs.length > 0 ? boutonObs[boutonObs.length - 1] : null;
                return sortie;
            });
        }
        const etat = () => ({
            arme: listenerBouton !== null, impose: boutonImpose, fires: boutonFires,
            obs: boutonObs.slice(-8), bouton: etatDuBouton(),
        });
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` + `confirmer: true` : ce relais RÉÉCRIT le compte "
                         + "d'unités posées que le HUD utilise pour activer START" };
        }
        if (body.armer === false) {
            if (listenerBouton) { try { listenerBouton.detach(); } catch { /* best effort */ } }
            listenerBouton = null; boutonImpose = null;
            return { ok: true, arme: false };
        }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        if (body.compte !== undefined) boutonImpose = body.compte;
        const r = armerBouton();
        if (r !== true) return r;
        return { ok: true, ...etat() };
    };

    /** Arme la CAPTURE du patron sur `UnitIdToPrefabDictionary$$Add`. Observation PURE.
     *  À armer AVANT `sandboxModeStart` : c'est `StartBattle` qui fait tirer `Add`. */
    ctx.rpc.deploymentPrefabArmer = (body?: { armer?: boolean }): unknown => {
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etatPrefab(),
                     note: "lecture seule -- `armer: true` pose la capture (elle n'écrit rien)" };
        }
        if (body.armer === false) {
            if (listenerAdd) { try { listenerAdd.detach(); } catch { /* best effort */ } }
            listenerAdd = null;
            return { ok: true, arme: false };
        }
        const r = armerPrefab();
        if (r !== true) return r;
        return { ok: true, ...etatPrefab() };
    };

    /** Départage les trois sorties d'échec d'`AddPlaceholderUnit`. Observation PURE. */
    ctx.rpc.deploymentPoseDiag = (body?: {
        armer?: boolean; aLaDemande?: boolean; confirmer?: boolean;
    }): unknown => {
        // Le régime À LA DEMANDE se règle ici : il ÉCRIT dans le dictionnaire du jeu, donc il
        // exige `confirmer`, et son état est publié à chaque lecture.
        if (body?.aLaDemande !== undefined) {
            if (body.aLaDemande === true && body.confirmer !== true) {
                return refus("`confirmer: true` exigé : le régime à la demande ÉCRIT dans le "
                    + "dictionnaire de prefabs du jeu, sur défaut de clé");
            }
            aLaDemande = body.aLaDemande;
        }
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true,
                     arme: listenerAdd2 !== null && listenerTuile !== null,
                     poses: poseTrace.slice(-12),
                     tuiles: tuileTrace.slice(-16), gets: getTrace.slice(-16),
                     // TRI-ÉTAT : `loaderArme: false` veut dire NON MESURÉ, pas « n'a pas tiré ».
                     loaderArme: listenerLoader !== null, loaderFires,
                     loaderRetours: loaderTrace.slice(-12),
                     aLaDemande, demandesFaites, demandes: demandeTrace.slice(-12),
                     clesArme: listenerCle !== null, cles: cleTrace.slice(-16) };
        }
        if (body.armer === false) {
            for (const l of [listenerAdd2, listenerTuile, listenerGet]) {
                if (l) { try { l.detach(); } catch { /* best effort */ } }
            }
            listenerAdd2 = null; listenerTuile = null; listenerGet = null;
            return { ok: true, arme: false };
        }
        const r = armerPoseDiag();
        if (r !== true) return r;
        return { ok: true, arme: true,
                 note: "poser une unité, puis relire ce RPC sans argument" };
    };

    /**
     * POURQUOI `Get` REND NUL ALORS QUE LA CLÉ EST LÀ. Lectures pures, aucune écriture.
     *
     * Mesuré session 53, MÊME dictionnaire et MÊME instant : `HasPrefabForUnitId` rend `true`
     * pour `spaceBlackmane` quand le `Get` du jeu rend `0x0`. `ContainsKey` étant donc vrai,
     * `Get` ne sort PAS par la branche « clé absente » — la seule autre issue à `0x0` est que
     * le loader rende un prefab NUL. Or `StartBattle` teste `IdunAssets$$IsAssetBundleAvailable`,
     * ÉCRIT UN AVERTISSEMENT, **et ajoute l'entrée quand même** : une entrée présente ne promet
     * donc rien sur la disponibilité de l'asset.
     *
     * Ce RPC lit, pour chaque unité : la config visuelle, sa référence d'asset (champ résolu PAR
     * TYPE), et la réponse de `IsAssetBundleAvailable`. Il n'invoque AUCUN chargement.
     */
    ctx.rpc.deploymentPrefabInspecter = (body?: { ids?: string[] }):
        Promise<unknown> | unknown => {
        const ids = body?.ids ?? [];
        if (ids.length === 0) return refus("`ids` exigé");
        return queueOnMainThread(() => {
            const d = dicoVivant();
            if ("ok" in d) return d;
            const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
            if (!kv) return refus(`\`${CLS_VIEWS_PREFAB}\` INTROUVABLE`);
            const mCfg = findMethodByParamCount(kv, "GetUnitVisualConfig", 1);
            if (!mCfg) return refus("`GetUnitVisualConfig` INTROUVABLE (1 paramètre)");
            const kAssets = findClassAnywhere("Idun.Source.Scripts", "IdunAssets")
                ?? findClassAnywhere("idun.Idun.Source.Scripts", "IdunAssets");
            const mDispo = kAssets
                ? findMethodByParamCount(kAssets, "IsAssetBundleAvailable", 1) : null;
            const out: Array<Record<string, unknown>> = [];
            for (const id of ids) {
                const ligne: Record<string, unknown> = { unitId: id };
                try {
                    const cfg = invokeMethod(mCfg.info, d.vues, [createManagedString(id)]);
                    ligne.config = cfg.toString();
                    if (cfg.isNull()) { ligne.verdict = "config visuelle NULLE"; out.push(ligne);
                                        continue; }
                    const kc = cfg.readPointer();
                    ligne.classeConfig = s(class_get_name(kc) as NativePointer);
                    const champs = champsDe(kc);
                    ligne.champs = champs.map((c) => `${c.nom}:${c.type}`);
                    const cRef = champs.find((c) => c.type.indexOf("AssetReference") >= 0);
                    if (!cRef) {
                        ligne.verdict = "aucun champ `AssetReference*` -- chemin PÉRIMÉ";
                        out.push(ligne); continue;
                    }
                    const aref = cfg.add(cRef.off).readPointer();
                    ligne.assetRef = `${cRef.nom}@+0x${cRef.off.toString(16)} = ${aref}`;
                    if (mDispo === null) {
                        ligne.verdict = "`IdunAssets$$IsAssetBundleAvailable` INTROUVABLE "
                            + "-- NON MESURÉ (ce n'est pas un `false`)";
                    } else if (aref.isNull()) {
                        ligne.verdict = "référence d'asset NULLE";
                    } else {
                        const dispo = boolBoxe(invokeMethod(mDispo.info, null, [aref]));
                        ligne.bundleDisponible = dispo;
                        ligne.verdict = dispo
                            ? "bundle DISPONIBLE -- la cause est ailleurs"
                            : "bundle INDISPONIBLE -- le loader ne peut RIEN produire, `Get` "
                                + "rendra nul quoi qu'on écrive dans le dictionnaire";
                    }
                } catch (e) { ligne.verdict = "LEVÉ : " + (e as Error).message; }
                out.push(ligne);
            }
            return { ok: true, dico: d.dico.toString(), source: d.source, unites: out };
        });
    };

    /**
     * L'ÉPREUVE CONTRÔLÉE : fabriquer l'entrée d'UNE unité, puis appeler `Get` NOUS-MÊMES et
     * DÉCODER ce qui en sort — retour, ou exception managée avec sa classe et son message.
     *
     * Pourquoi elle existe : `listenerDemande` a vu **5** appels de `Get` là où `listenerGet`
     * n'en a enregistré que **3**, et les deux manquants sont exactement les unités posées. Or
     * `listenerGet` écrit dans son `onLeave` — un `onLeave` qui ne tire pas signifie que l'appel
     * N'EST PAS REVENU. `Get` lève donc dans notre entrée fabriquée, silencieusement : rien sur
     * le plateau, aucune trace de pose, aucune erreur à l'écran. Seul un appel encadré peut lire
     * ce message.
     *
     * ⛔ ON DÉPOSE LES ANCRAGES SUR `Get` PENDANT L'APPEL. Ancrer la méthode qu'on invoque est
     * le motif qui gèle le jeu (`retreatInvoke` applique déjà cette précaution). Ils sont
     * ré-armés ensuite.
     */
    ctx.rpc.deploymentPrefabEprouver = (body?: { id?: string; confirmer?: boolean }):
        Promise<unknown> | unknown => {
        const id = body?.id;
        if (!id) return refus("`id` exigé (une seule unité)");
        if (body?.confirmer !== true) {
            return refus("`confirmer: true` exigé : cette épreuve ÉCRIT une entrée puis INVOQUE "
                + "`Get`, donc elle peut déclencher un chargement d'asset");
        }
        if (patron === null) return refus("aucun PATRON capturé -- monter une bataille d'abord");
        return queueOnMainThread(() => {
            const p = patron;
            if (p === null) return refus("patron perdu");
            const d = dicoVivant();
            if ("ok" in d) return d;
            const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
            const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
            if (!kd || !kv) return refus("classes INTROUVABLES");
            const mHas = findMethodByParamCount(kd, "HasPrefabForUnitId", 1);
            const mAdd = findMethodByParamCount(kd, "Add", 2);
            const mCfg = findMethodByParamCount(kv, "GetUnitVisualConfig", 1);
            const mGet = findMethodByParamCount(kd, "Get", 1);
            if (!mHas || !mAdd || !mCfg || !mGet) return refus("méthodes INTROUVABLES");

            const fab = fabriquerEntree(p, d.dico, d.vues, id, mHas, mAdd, mCfg);
            const sortie: Record<string, unknown> = { unitId: id, fabrication: fab.detail };

            // ⛔ dépose des ancrages sur `Get` -- on invoque ce qu'on ancrait.
            const gardeDemande = aLaDemande;
            aLaDemande = false;
            for (const l of [listenerDemande, listenerGet]) {
                if (l) { try { l.detach(); } catch { /* best effort */ } }
            }
            listenerDemande = null; listenerGet = null;
            Interceptor.flush();
            try {
                const r = invokeMethod(mGet.info, d.dico, [createManagedString(id)]);
                sortie.getRetour = r.toString();
                sortie.getNul = r.isNull();
                sortie.verdict = r.isNull()
                    ? "`Get` rend NUL sans lever -- l'entrée est là mais ne produit pas de prefab"
                    : "`Get` a RENDU quelque chose -- le prefab existe";
            } catch (e) {
                // C'EST LE MESSAGE QU'ON CHERCHAIT : `invokeMethod` décode la classe, le message
                // et la pile de l'exception managée.
                sortie.verdict = "`Get` a LEVÉ";
                sortie.exception = (e as Error).message;
            }
            // L'état de l'entrée APRÈS l'appel : le loader a-t-il rempli `_prefab` ?
            if (fab.ref !== undefined) {
                try {
                    const pr = fab.ref.add(p.offPrefab).readPointer();
                    sortie.prefabApres = pr.toString();
                    sortie.prefabRempli = !pr.isNull();
                } catch (e) { sortie.prefabApres = "ILLISIBLE : " + (e as Error).message; }
            }
            aLaDemande = gardeDemande;
            const re = armerPoseDiag();
            sortie.ancragesReArmes = re === true ? true : (re as Refus).error;
            return { ok: true, ...sortie };
        });
    };

    /** Diagnostic PUR : le patron, et pour chaque id demandé si le jeu a déjà son prefab.
     *  `HasPrefabForUnitId` est une lecture (`ContainsKey`), elle n'écrit rien. */
    ctx.rpc.deploymentPrefabStatus = (body?: { ids?: string[] }): Promise<unknown> | unknown => {
        const ids = body?.ids ?? [];
        if (ids.length === 0) return { ok: true, lecture: true, ...etatPrefab() };
        return queueOnMainThread(() => {
            const d = dicoVivant();
            if ("ok" in d) return d;
            const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
            if (!kd) return refus(`\`${CLS_DICO}\` INTROUVABLE`);
            const mh = findMethodByParamCount(kd, "HasPrefabForUnitId", 1);
            if (!mh) return refus("`HasPrefabForUnitId` INTROUVABLE (1 paramètre)");
            const vus: Array<{ unitId: string; aSonPrefab: boolean | string }> = [];
            for (const id of ids) {
                try {
                    const r = invokeMethod(mh.info, d.dico, [createManagedString(id)]);
                    vus.push({ unitId: id, aSonPrefab: boolBoxe(r) });
                } catch (e) { vus.push({ unitId: id, aSonPrefab: "LEVÉ : " + (e as Error).message }); }
            }
            return { ok: true, dico: d.dico.toString(), vus, ...etatPrefab() };
        });
    };

    /** LE CHARGEMENT À LA DEMANDE. Fabrique l'entrée manquante pour chaque id, sur le patron
     *  capturé. N'appelle AUCUN chargement d'asset : c'est le jeu qui tirera le prefab à son
     *  premier `Get`, comme il le fait pour les unités de la BC. */
    ctx.rpc.deploymentPrefabCharger = (body?: {
        ids?: string[]; confirmer?: boolean; tout?: boolean;
    }):
        Promise<unknown> | unknown => {
        let ids = body?.ids ?? [];
        if (!body || body.confirmer === undefined) {
            return { ok: true, lecture: true, ...etatPrefab(),
                     note: "`confirmer: true` exigé, plus `ids` OU `tout: true` : ce RPC ÉCRIT "
                         + "dans le dictionnaire de prefabs de la vue vivante" };
        }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        // `tout` = tout ce que le HUD affiche. C'est le seul régime qui rende l'écran
        // réellement utilisable : l'utilisateur clique un portrait, pas un identifiant.
        if (body.tout === true) {
            const r = listeDuRoster();
            if (!Array.isArray(r)) return r;
            ids = r;
        }
        if (ids.length === 0) return refus("`ids` vide et `tout` non demandé : rien à faire");
        if (patron === null) {
            return refus("aucun PATRON capturé -- armer `deploymentPrefabArmer` AVANT le montage, "
                + `puis remonter la bataille (addFires=${addFires}, refus=${patronRefus})`);
        }
        return queueOnMainThread(() => {
            const p = patron;
            if (p === null) return refus("patron perdu entre-temps");
            const d = dicoVivant();
            if ("ok" in d) return d;
            const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
            const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
            if (!kd || !kv) return refus("classes du dictionnaire/vue INTROUVABLES");
            const mHas = findMethodByParamCount(kd, "HasPrefabForUnitId", 1);
            const mAdd = findMethodByParamCount(kd, "Add", 2);
            const mCfg = findMethodByParamCount(kv, "GetUnitVisualConfig", 1);
            if (!mHas || !mAdd) return refus("`HasPrefabForUnitId`/`Add` INTROUVABLES");
            if (!mCfg) return refus("`IdunGameViews$$GetUnitVisualConfig` INTROUVABLE (1 param)");
            const faits: Array<{ unitId: string; ok: boolean; detail: string }> = [];
            for (const id of ids) {
                let detail = "";
                let ok = false;
                try {
                    const sid = createManagedString(id);
                    // `Add` LÈVE sur clé dupliquée : on ne tente que ce qui manque vraiment.
                    if (boolBoxe(invokeMethod(mHas.info, d.dico, [sid]))) {
                        detail = "déjà présent -- rien fait";
                        ok = true;
                    } else {
                        // Lecture pure (`UnitConfigMap.TryGetValue`), aucun asset touché.
                        const cfg = invokeMethod(mCfg.info, d.vues, [sid]);
                        if (cfg.isNull()) {
                            detail = "`GetUnitVisualConfig` rend NUL -- cette unité n'a pas de "
                                + "config visuelle dans l'univers chargé ; on n'invente rien";
                        } else {
                            // LE SLOT SE CHOISIT PAR LE TYPE RÉEL DE `cfg`, pas par élimination.
                            // Mesuré : le choix « le premier champ qui n'est pas l'EffectPool »
                            // visait un autre membre de la fermeture ; la config du patron restait
                            // en place et DEUX unités distinctes s'affichaient avec SON modèle.
                            const nomCfg = s(class_get_name(cfg.readPointer()) as NativePointer);
                            const cible = p.champsHolder.find((c) => c.type === nomCfg);
                            if (!cible) {
                                detail = `aucun champ de type \`${nomCfg}\` sur `
                                    + `\`${p.holderClasseNom}\` -- champs : `
                                    + p.champsHolder.map((c) => `${c.nom}:${c.type}`).join(", ")
                                    + " ; on n'écrit RIEN plutôt qu'à côté";
                                faits.push({ unitId: id, ok: false, detail });
                                continue;
                            }
                            const holder = cloner(p.exemplaireHolder, p.holderClasse,
                                                  p.tailleHolder);
                            holder.add(cible.off).writePointer(cfg);
                            // RELECTURE : une écriture non vérifiée est ce qui a produit deux
                            // modèles identiques sans la moindre erreur.
                            const relu = holder.add(cible.off).readPointer();
                            if (!relu.equals(cfg)) {
                                detail = `écriture NON CONFIRMÉE dans \`${cible.nom}\` `
                                    + `(relu ${relu}, attendu ${cfg})`;
                                faits.push({ unitId: id, ok: false, detail });
                                continue;
                            }
                            const del = cloner(p.exemplaireDel, p.delClasse, p.tailleDel);
                            del.add(p.offTarget).writePointer(holder);
                            // `method_code` est le slot que `Get` passe à l'invocateur.
                            if (p.offMethodCode < 0) {
                                detail = "`method_code` ABSENT de `" + p.delClasseNom
                                    + "` : le délégué cloné appellerait la fermeture du PATRON. "
                                    + "On refuse plutôt que d'afficher un modèle d'emprunt.";
                                faits.push({ unitId: id, ok: false, detail });
                                continue;
                            }
                            del.add(p.offMethodCode).writePointer(holder);
                            const reluCode = del.add(p.offMethodCode).readPointer();
                            if (!reluCode.equals(holder)) {
                                detail = `\`method_code\` NON CONFIRMÉ (relu ${reluCode})`;
                                faits.push({ unitId: id, ok: false, detail });
                                continue;
                            }
                            const ref = cloner(p.exemplaireRef, p.refClasse, p.tailleRef);
                            // ⚠ LE SLOT QUI DOIT REPARTIR À NUL : le patron a son prefab déjà
                            // résolu ; le laisser afficherait le modèle de l'unité capturée.
                            ref.add(p.offPrefab).writePointer(ptr(0));
                            ref.add(p.offLoader).writePointer(del);
                            gcRoot.add(holder); gcRoot.add(del); gcRoot.add(ref);
                            invokeMethod(mAdd.info, d.dico, [sid, ref]);
                            detail = `entrée créée -- config ${nomCfg} @ \`${cible.nom}\``
                                + `+0x${cible.off.toString(16)} = ${cfg} (relue OK)`;
                            ok = true;
                        }
                    }
                } catch (e) { detail = "LEVÉ : " + (e as Error).message; }
                faits.push({ unitId: id, ok, detail });
                if (prefabCharges.length < 128) prefabCharges.push({ unitId: id, ok, detail });
            }
            return { ok: true, faits, poses: faits.filter((f) => f.ok).length,
                     total: ids.length };
        });
    };

    /**
     * L'ÉTAT DU DÉPLOIEMENT, ORDRE COMPRIS — lecture pure, et le seul observable AVANT le START.
     *
     * ⚠ POURQUOI IL EXISTE. Le replay adresse ses coups PAR ENTITÉ, et l'entité n'est attribuée
     * qu'au START : mesuré le 2026-08-20, en phase de déploiement `observeBattle` ne voit que les
     * unités ADVERSES -- les nôtres sont des `PlaceholderUnitView`, sans entité. Tout contrôle
     * d'appariement arrivait donc APRÈS le START, c'est-à-dire après le coût d'entrée.
     *
     * Ce que le HUD tient, lui, est lisible tout de suite : `_currentlyPlacedUnits`, DANS SON
     * ORDRE. C'est cet ordre que le START parcourt pour convertir. L'exposer, c'est se donner
     * l'unique chance de refuser AVANT de dépenser.
     *
     * ⚠ CE QUE ÇA NE PROUVE PAS ENCORE. Que l'allocation se DÉDUISE de cet ordre reste une
     * corrélation à deux mesures (poses en ordre du replay -> allocation inverse ; poses en ordre
     * inverse -> allocation du replay), sans mécanisme lu au décompilé. On PUBLIE donc l'ordre,
     * on n'en tire aucune loi ici : c'est l'appelant qui confronte, et le cran d'après-START
     * (`controler_appariement`) reste le juge.
     */
    ctx.rpc.deploymentEtat = (): Promise<unknown> | unknown => queueOnMainThread(() => {
        const e = etatDuDeploiement();
        const base = "ok" in e ? { hudRefus: e.error }
            : { placeholders: e.placeholders, ordreHud: e.nomsPlaceholders,
                reelles: e.reelles, nomsReels: e.nomsReels, cases: e.cases,
                max: e.max, machines: e.machines };
        return { ok: true, lecture: true, ...base, ordreConversion: ordreDeConversion(),
                 note: "`ordreConversion` est la liste que le START PARCOURT ; `ordreHud` est une "
                     + "AUTRE collection, qui ne commande rien. Les entités n'existent qu'APRÈS "
                     + "le START, dans l'ordre d'`ordreConversion`." };
    });

    /** ÉTAT du mirror de `GetUnlockedUnitsPooled`. Lecture pure. */
    ctx.rpc.deploymentPoolStatus = (): unknown => ({ ok: true, lecture: true, ...etatPool() });

    /**
     * LE PLAFOND DE POSE — observe, et sur demande IMPOSE.
     *
     *   { armer: true }                                  -> observe ce que le relais rend
     *   { armer: true, valeur: N, confirmer: true }       -> impose N
     *
     * ⚠ On agit sur le RELAIS `VisualBattleQuery`, jamais sur
     * `SandboxGameModeSource$$AmountOfUnlockedUnits` : ce dernier résout sur un `return 0;`
     * DÉDUPLIQUÉ à 1233 xrefs. L'ancrer basculerait un millier de prédicats sans rapport.
     */
    ctx.rpc.deploymentPlafondArmer = (body?: {
        armer?: boolean; max?: number; min?: number; confirmer?: boolean;
    }): unknown => {
        const etat = () => ({
            max: { arme: BORNES.max.listener !== null, impose: BORNES.max.impose,
                   fires: BORNES.max.fires, observations: BORNES.max.obs },
            min: { arme: BORNES.min.listener !== null, impose: BORNES.min.impose,
                   fires: BORNES.min.fires, observations: BORNES.min.obs },
        });
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat() };
        }
        if (body.armer === false) {
            for (const b of [BORNES.max, BORNES.min]) {
                if (b.listener) b.listener.detach();
                b.listener = null; b.impose = null;
            }
            Interceptor.flush();
            return { ok: true, action: "retire", ...etat() };
        }
        if ((body.max !== undefined || body.min !== undefined) && body.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé pour IMPOSER une borne : on "
                + "écrit dans la décision de `VisualBattleQuery`, que TOUS les modes de jeu "
                + "partagent. Observer d'abord (`{ armer: true }`)." };
        }
        // On arme les DEUX relais même si une seule valeur est imposée : observer la borne
        // qu'on ne force pas est ce qui dit si elle valait déjà ce qu'on croit.
        for (const b of [BORNES.max, BORNES.min]) {
            const r = armerBorne(b);
            if (r !== true) return r;
        }
        if (body.max !== undefined) BORNES.max.impose = body.max | 0;
        if (body.min !== undefined) BORNES.min.impose = body.min | 0;
        return { ok: true, ...etat() };
    };

    /**
     * LE HUD — les DEUX dictionnaires, et le VERDICT de chaque clic. Observation pure.
     *
     * `{ armer: true }` ancre `Show` (lit les comptes après remplissage) et
     * `TryMarkUnitAsPlaced` (capture unitId + retour). Sans corps : lecture.
     */
    ctx.rpc.deploymentHudArmer = (body?: { armer?: boolean }): unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true,
                     arme: listenerShow !== null && listenerPose !== null,
                     etat: hudEtat, bascule: etatBasculeHud(), chemins: cheminsEtat,
                     poses: hudPoses, plateau: hudBoard,
                     shows: { entrees: showEnters, sorties: showFires,
                              leveEnCours: showEnters > showFires },
                     clears: { fires: vidangeFires, trace: vidangeTrace } };
        }
        if (body.armer === false) {
            if (listenerShow) { listenerShow.detach(); listenerShow = null; }
            if (listenerPose) { listenerPose.detach(); listenerPose = null; }
            if (listenerBoard) { listenerBoard.detach(); listenerBoard = null; }
            if (listenerVidange) { listenerVidange.detach(); listenerVidange = null; }
            Interceptor.flush();
            return { ok: true, arme: false, action: "retire" };
        }
        const r = armerHud();
        if (r !== true) return r;
        return { ok: true, arme: true, etat: hudEtat, poses: hudPoses, plateau: hudBoard,
                 note: "`Show` publie les deux comptes ; `TryMarkUnitAsPlaced` publie le "
                     + "verdict de chaque clic. Un premier dictionnaire plein et un second "
                     + "vide EST la signature de « je sélectionne mais je ne pose pas »." };
    };

    /**
     * LE COMPTEUR DU BOUTON — celui de l'ÉCRAN, pas celui qu'on avait choisi de lire.
     *
     * ⚠ POURQUOI CE RPC EXISTE. On lisait `_currentlyPlacedUnits._size` et on y voyait 6, pendant
     * que le bouton START affichait **0/5** à l'écran. Les deux comptabilités sont distinctes, et
     * c'est l'ÉCRAN qui dit la vérité sur ce que le HUD croit avoir. Le décompilé le confirme :
     *
     *     UpdateButtons(this):
     *         standard = ListExtensions.Count(_currentlyPlacedUnits, <prédicat A>)
     *         machines = ListExtensions.Count(_currentlyPlacedUnits, <prédicat B>)
     *         UnitDeploymentHudButtons.UpdateState(boutons, gameMode,
     *                                              standard, machines,
     *                                              _minUnitsPossible, _maxUnitsPossible)
     *
     * Donc la liste est la MÊME (6 entrées) mais elle est comptée À TRAVERS UN PRÉDICAT, et
     * `UpdateState` affiche `MaxUnitAmountNotReached(standard, max)` -- le « X/5 ». Un `0`
     * signifie que le prédicat rejette les six.
     *
     * On n'a pas besoin de nommer les deux lambdas (elles ne portent pas de symbole `b__` sur ce
     * build) : `UpdateState` REÇOIT les quatre entiers en arguments. On les lit là, à la source.
     */
    ctx.rpc.deploymentCompteurBouton = (body?: {
        armer?: boolean; vider?: boolean;
    }): unknown => {
        if (body?.vider === true) compteurBoutonTrace.length = 0;
        const etat = () => ({ arme: listenerBoutons !== null,
                              tirs: compteurBoutonTrace.length, trace: compteurBoutonTrace });
        if (!body || body.armer === undefined) return { ok: true, lecture: true, ...etat() };
        if (body.armer === false) {
            if (listenerBoutons) { listenerBoutons.detach(); listenerBoutons = null; }
            Interceptor.flush();
            return { ok: true, action: "detache", ...etat() };
        }
        if (listenerBoutons) return { ok: true, action: "deja arme", ...etat() };
        const kB = findClassAnywhere("idun.ui", "UnitDeploymentHudButtons");
        if (!kB) return refus("`idun.ui.UnitDeploymentHudButtons` INTROUVABLE");
        const mB = findMethodByParamCount(kB, "UpdateState", 5);
        if (!mB) return refus("`UnitDeploymentHudButtons$$UpdateState` INTROUVABLE (5 paramètres)");
        const tB = lireTete(mB.ptr);
        if (tB.erreur === null && teteTriviale(tB)) {
            return refus("REFUS : `UpdateState` résout sur un corps TRIVIAL -- adresse PARTAGÉE.");
        }
        listenerBoutons = Interceptor.attach(mB.ptr, {
            onEnter(args) {
                if (compteurBoutonTrace.length >= 24) return;
                // args[0] = this, args[1] = gameMode, puis les QUATRE entiers.
                compteurBoutonTrace.push({
                    standardUnitsCount: args[2].toInt32(),
                    machineOfWarUnitsCount: args[3].toInt32(),
                    minUnitsPossible: args[4].toInt32(),
                    maxUnitsPossible: args[5].toInt32(),
                    // Le compte BRUT de la liste, au même instant : c'est l'écart entre les deux
                    // qui est le fait (`brut` 6 contre `standardUnitsCount` 0 = le prédicat
                    // rejette tout).
                    listeBrute: (() => {
                        try {
                            if (hudInstance === null || hudInstance.isNull()) return null;
                            const l = hudInstance.add(0x1b8).readPointer();
                            return l.isNull() ? null : l.add(0x18).readS32();
                        } catch { return null; }
                    })(),
                });
            },
        });
        Interceptor.flush();
        return { ok: true, action: "attache", ghidraVA: ghidraVA(mB.ptr), tete: tB, ...etat() };
    };

    /**
     * COUPER L'ESPACE DE RECHERCHE EN DEUX : `StartBattle` est-il ATTEINT, et REVIENT-IL ?
     *
     * ⚠ C'EST UNE MESURE, PAS UNE HYPOTHÈSE. `HandleOnStartBattleTapped` fait trois choses après
     * ses gardes : `FindAll` (le prédicat -- MESURÉ bon, 6/6), `ListExtensions.Map`, puis le
     * relais au slot 3 du `_callbacksDelegate`, qui est
     * `IdunBattle.View.FSM.UnitDeployment.UnitDeploymentState$$StartBattle`. Ancrer CE point
     * tranche entre les deux moitiés sans rien supposer :
     *
     *   entrée 0            -> la levée est AVANT, donc dans `Map` ou dans le dispatch d'interface ;
     *   entrée 1, sortie 0  -> la levée est DANS `StartBattle` ou dessous ;
     *   entrée 1, sortie 1  -> `StartBattle` a rendu, la levée est APRÈS.
     *
     * On relève aussi ses trois champs et la TAILLE de la liste reçue : le décompilé montre que
     * `units == null`, `_visualBattleQuery == null` et `_actions == null` sont ses trois sorties
     * « ne revient pas », et que la taille est passée telle quelle au slot 0x31.
     *
     * Résolu PAR NOM, corps contrôlé (`tete`) : pas d'adresse épinglée ici, il y a un `MethodInfo`.
     */
    ctx.rpc.deploymentStartTracer = (body?: {
        armer?: boolean; vider?: boolean;
    }): unknown => {
        if (body?.vider === true) { startBattleTrace.length = 0; }
        // La résolution des noms de classe se fait ICI, hors de tout callback : un
        // `Il2CppClass*` est PERMANENT, donc le nommer plus tard est sûr -- là où l'objet
        // message, lui, peut avoir été ramassé entre-temps.
        const etat = () => ({
            arme: listenerStartBattle !== null, tirs: startBattleTrace.length,
            trace: startBattleTrace.map((e) => {
                const nom = (k: unknown): string | null => {
                    if (typeof k !== "string" || k === "0x0") return null;
                    try { return s(class_get_name(ptr(k)) as NativePointer); }
                    catch { return null; }
                };
                if (e.msgKlass === undefined && e.selfKlass === undefined) return e;
                return { ...e, msgClasse: nom(e.msgKlass), handler: nom(e.selfKlass) };
            }),
        });
        if (!body || body.armer === undefined) return { ok: true, lecture: true, ...etat() };
        if (body.armer === false) {
            if (listenerStartBattle) { listenerStartBattle.detach(); listenerStartBattle = null; }
            for (const l of listenersEtages) l.detach();
            listenersEtages.length = 0;
            Interceptor.flush();
            return { ok: true, action: "detache", ...etat() };
        }
        if (listenerStartBattle) return { ok: true, action: "deja arme", ...etat() };
        const kS = findClassAnywhere("IdunBattle.View.FSM.UnitDeployment", "UnitDeploymentState");
        if (!kS) return refus("`UnitDeploymentState` INTROUVABLE sur ce build");
        const mS = findMethodByParamCount(kS, "StartBattle", 1);
        if (!mS) return refus("`UnitDeploymentState$$StartBattle` INTROUVABLE (1 paramètre)");
        const t = lireTete(mS.ptr);
        if (t.erreur === null && teteTriviale(t)) {
            return refus("REFUS : `StartBattle` résout sur un corps TRIVIAL "
                + `(ret à l'octet ${t.retA}) -- adresse PARTAGÉE.`);
        }
        // LES QUATRE ÉTAGES SOUS `StartBattle`, NOMMÉS PAR LEURS SLOTS D'INTERFACE (lus par
        // `classInterfaceSlots`, jamais devinés) :
        //
        //   StartBattle(units)
        //     +- VisualBattleQuery$$IsMinUnitAmountToBringToStartBattleReached(count)   slot 0x31
        //     +- VisualBattleQuery$$HasGameModeReasonNotToStartMatch(units, out raison) slot 0x59
        //          +- [aucune raison] UnitSelectionFsm$$StartMatch(true)                slot 0x1d
        //          +- [une raison]    StateMachineActions$$HandleReasonNotToStartMatch  slot 0x69
        //
        // Le même critère qu'au-dessus s'applique à chacun : ENTRÉE SANS SORTIE = c'est lui.
        for (const c of [
            ["IdunBattle.View.FSM", "VisualBattleQuery",
             "IsMinUnitAmountToBringToStartBattleReached", 1],
            ["IdunBattle.View.FSM", "VisualBattleQuery", "HasGameModeReasonNotToStartMatch", 2],
            ["IdunBattle.View.FSM", "UnitSelectionFsm", "StartMatch", 1],
            ["IdunBattle.View.FSM", "StateMachineActions", "HandleReasonNotToStartMatch", 1],
            // ⚠ L'ÉTAGE SOUS `StartMatch`, pour encadrer `ChangeState<T>` SANS l'ancrer.
            // `ChangeState` est un corps gshared : `findMethod` sur la définition générique
            // rendrait le THUNK, donc un ancrage qui se déclare posé et ne tire jamais (#259-b).
            // `QueueHideEverything` (slot 0x3e d'`IStateMachineActions`, NOMMÉ par
            // `classInterfaceSlots`) est appelé dans les DERNIÈRES lignes de `ChangeState` :
            // s'il tire, la levée est après lui ; s'il ne tire pas, elle est avant -- dans la
            // fabrique d'état ou dans la sortie de l'état courant.
            ["IdunBattle.View.FSM", "StateMachineActions", "QueueHideEverything", 0],
            // LE DERNIER CRAN. Après `ChangeState`, `UnitSelectionFsm$$StartMatch` teste
            // `etat+0x10` et, s'il est non nul, relaie au slot 0x50 d'`IStateMachineActions` --
            // NOMMÉ `StateMachineActions$$StartMatch`, le vrai démarrage. S'il tire, la levée
            // est DEDANS ; s'il ne tire pas, c'est que `etat+0x10` est nul et que la levée est
            // la sortie « ne revient pas » de `UnitSelectionFsm$$StartMatch` lui-même.
            ["IdunBattle.View.FSM", "StateMachineActions", "StartMatch", 0],
            // ET LE BOUT DE LA CHAÎNE. `StateMachineActions$$StartMatch` relaie au slot 0
            // d'`IStartMatchHandler` sur `_startMatchHandler`, qui est l'`IdunMainView` --
            // lequel relaie au slot 0x11 d'`IGameModeSource` sur son `_activeGameSource`, NOMMÉ
            // `HandleStartMatch` et porté, en sandbox, par `SandboxGameModeSource`.
            //
            // ⚠ `HandleStartMatch` N'EXISTE PAS dans `functions.tsv` pour cette classe, et ça ne
            // prouve RIEN : IL2CPP déduplique les corps triviaux, un corps partagé n'a qu'UN
            // propriétaire dans la table. Le contrôle `teteTriviale` ci-dessous tranche pour de
            // vrai -- et s'il refuse, LE REFUS EST LE RÉSULTAT : la sandbox n'implémente pas ce
            // point, exactement comme `AmountOfUnlockedUnits` résout sur un `return 0` partagé.
            ["idun", "IdunMainView", "StartMatch", 0],
            ["IdunBattle.ViewLogic.BattleSource", "SandboxGameModeSource", "HandleStartMatch", 1],
            // `HandleStartMatch` ne fait qu'INVOQUER le `ContinueStartMatchDelegate` fabriqué
            // par `IdunMainView$$StartMatch` -- son corps est d'ailleurs DÉDUPLIQUÉ (Ghidra le
            // nomme `TestSceneBattleModeSource$$HandleStartMatch`). Le travail réel est ici, et
            // les six champs qu'il exige non nuls sont TOUS mesurés non nuls : la levée est donc
            // dans un de ses APPELS, pas dans une de ses gardes.
            ["idun", "IdunMainView", "ContinueStartMatch", 0],
            // Le premier suspect, et son nom dit pourquoi : notre MoW EST un placeholder.
            ["idun", "IdunMainView", "AddUnitsFromPlaceholdersAndRunnerStartMatch", 0],
            // Le second : `CLAUDE.md` documente que `SandboxGameModeSource$$AmountOfUnlockedUnits`
            // résout sur un `return 0` DÉDUPLIQUÉ, d'où un plafond nul en sandbox -- et ce calcul
            // lit aussi `GetSpawnPointCoordinatedForHumanPlayer(...).Count`.
            ["IdunBattle.View.FSM", "VisualBattleQuery", "MaxUnitsPossibleToStartBattle", 0],
            // LE CORPS DE `AddUnitsFromPlaceholdersAndRunnerStartMatch`, coupé en deux.
            //
            //   placeholders = IdunGameViews.GetPlaceholderUnitViews(...)
            //   foreach (ph) { message = (ph+0x70 == 0) ? AddUnit : AddMachine ;
            //                  IdunRunner.Apply(runner, message) }
            //   IdunRunner.StartMatch(runner)
            //
            // `GetPlaceholderUnitViews` dit COMBIEN d'entrées entrent dans la boucle ;
            // `IdunRunner$$StartMatch` dit si la boucle est allée AU BOUT. Une entrée dans la
            // première et pas dans la seconde localise la levée DANS la boucle, donc sur un
            // placeholder précis -- et c'est exactement là que notre MoW vit.
            ["IdunBattle.View.Game", "IdunGameViews", "GetPlaceholderUnitViews", 0],
            ["IdunBattle.Runner", "IdunRunner", "StartMatch", 0],
            // LES DEUX SEULS APPELS DU CORPS DE BOUCLE. Tous ses gardes sont mesurés passants
            // (le placeholder porte `UnitId` non nul, `PlayerId` 11, `IsMachineOfWar` 1 ; le
            // `_logger` est non nul), donc la levée est dans l'un des deux.
            ["Idun.Source.Util.Logging", "IdunLogger", "AddBreadcrumb", 3],
            ["IdunBattle.Runner", "IdunRunner", "Apply", 1],
            // LE MOTEUR, SOUS `Apply`. Le message est visité (`Accept`) puis relayé à
            // `OperationProcessor$$AddMachine`, qui exécute `AddMachineOperation`.
            //
            // ⚠ `GetPlatform` a DEUX régimes qu'il ne faut pas confondre : rendre `0` est traité
            // PROPREMENT par `Execute` (il journalise et rend `0`, aucun jet) ; mais `GetPlatform`
            // LUI-MÊME lève si l'état ne rend aucune entité de type 7 -- les plateformes de
            // Machine of War. Une entrée sans sortie SUR LUI dit donc « pas de plateforme du
            // tout », ce qui n'est pas la même panne que « pas de plateforme à cette position ».
            ["IdunBattle.Messages", "AddMachineMessage", "Accept", 1],
            ["IdunBattle.Operations", "AddMachineOperation", "Execute", 3],
            ["IdunBattle.Operations", "AddMachineOperation", "GetPlatform", 1],
            ["IdunBattle.Operations", "AddMachineOperation", "InitializeAbilitiesStatus", 2],
            // L'ARBRE DE GROUPES DU FLUX -- le vrai fond.
            //
            // `StreamDispatcher$$FinishGroup` ne leve pas lui-meme : il fait `ForEach` sur ses
            // DEUX abonnes (`StreamCache` et `MessageGenerator`, LUS sur l'instance vivante).
            // Et `MessageGenerator$$FinishGroup` DEPILE : il leve si la pile ne rend rien.
            // Mesure post-mortem : `_messageStack._size == 0`.
            //
            // ⚠ `StartGroup` EMPILE INCONDITIONNELLEMENT (au decompile). Une pile vide au
            // `FinishGroup` n'est donc pas « un push rate » -- c'est un DESEQUILIBRE : plus de
            // `FinishGroup` que de `StartGroup`. Compter les deux le montre ; les lire au repos
            // ne le montrerait pas.
            ["IdunBattle.ViewLogic.BattleStream", "MessageGenerator", "StartGroup", 4],
            ["IdunBattle.ViewLogic.BattleStream", "MessageGenerator", "FinishGroup", 0],
            // LE BOUT. Quand la pile se vide (groupe RACINE), `FinishGroup` PUBLIE le groupe
            // entier : slot 0 d'`IMessageProcessor` sur `_messageProcessor`, NOMMÉ
            // `MessageExecutionQueue$$Enqueue`. C'est la file dont on sait qu'elle reste à
            // `_currentlyProcessingMessage = 1` POUR TOUJOURS après l'incident -- on lit donc ce
            // drapeau À L'ENTRÉE, seule façon de distinguer la CAUSE de la CONSÉQUENCE.
            ["IdunBattle.ViewLogic.BattleStream", "MessageExecutionQueue", "Enqueue", 1],
            // ⚠ `Enqueue` TRAITE EN LIGNE : mesuré `enTraitement=false`, `enFile=0` à son entrée,
            // et pourtant il ne revient pas. La file n'était donc pas engorgée -- c'est le
            // TRAITEMENT du groupe qui lève, et le `_currentlyProcessingMessage = 1` qu'on
            // observe ensuite (le blocage qui tue l'IA) en est la CONSÉQUENCE, pas la cause.
            // Sous lui : les gestionnaires de VUE du pas `AddMachine`.
            ["IdunBattle.View.BattleStream.StepHandlers", "AddMachineGroupHandler",
             "ExecuteStepInternal", 1],
            // ⚠ LES COMPTES DE PARAMÈTRES SONT LUS AU DÉCOMPILÉ, pas devinés : les trois
            // premiers essais ont rendu `INTROUVABLE`, et un `INTROUVABLE` silencieux se lirait
            // « cet étage n'a pas tiré » -- l'inverse du fait. `ExecuteInternal` ne prend RIEN,
            // `AddMachine` en prend CINQ (unitEntityId, playerEntityId, teamId, onFinished,
            // out machineView).
            ["IdunBattle.View.BattleStream.StepHandlers", "AddMachineStepHandler",
             "ExecuteInternal", 0],
            ["IdunBattle.View.Game", "IdunGameViews", "AddMachine", 5],
            ["IdunBattle.View.Game", "IdunGameViews", "GetUnitConfig", 1],
            // Le maillon que le décompilé désigne : la plateforme côté VUE, cherchée PAR TEAM.
            // Une sandbox qui n'a pas monté ce visuel-là rendrait `0` -- ce qui est traité
            // proprement -- ou ferait tomber la cascade qui suit, qui n'a AUCUNE garde.
            ["idun", "IdunBoardView", "GetMachinePlatform", 1],
            ["IdunBattle.View.Game", "IdunGameViews", "GetNewPooledUnitView", 4],
            // ⚠ `Enqueue` DÉLÈGUE À `ProcessNextMessage`, QUI SE RAPPELLE LUI-MÊME. Le décompilé
            // montre qu'il lève quand la FABRIQUE ne rend AUCUN gestionnaire pour le type du
            // message dépilé (`if (handler != 0) { ...; return } THROW`). Or les gestionnaires
            // MoW ont bien tourné : le message fautif est donc un AUTRE, plus loin dans la file.
            // Compter entrées/sorties donne la profondeur de récursion et l'itération qui casse.
            ["IdunBattle.ViewLogic.BattleStream", "MessageExecutionQueue", "ProcessNextMessage", 0],
            ["IdunBattle.ViewLogic.BattleStream", "MessageExecutionQueue",
             "OnMessageFinishedProcessing", 0],
            // LE SQUELETTE DU GESTIONNAIRE DE GROUPE. `Execute` -> `ExecuteInternal` ->
            // `StartMessageExecutionLoop`, qui parcourt les enfants du groupe et, quand il n'y
            // en a plus, appelle `Finish` -- lequel rappelle la file. Trois gardes y lèvent :
            // le GroupMessage nul, l'enfant nul, et le `onFinished` nul dans `Finish`.
            ["IdunBattle.View.BattleStream.GroupHandlers", "AGroupHandlerBase", "Execute", 3],
            ["IdunBattle.View.BattleStream.GroupHandlers", "AGroupHandlerBase", "Finish", 0],
            ["IdunBattle.View.BattleStream.GroupHandlers", "GenericGroupHandlerBase",
             "ExecuteInternal", 0],
            ["IdunBattle.View.BattleStream.GroupHandlers", "GenericGroupHandlerBase",
             "StartMessageExecutionLoop", 0],
            ["IdunBattle.View.BattleStream.GroupHandlers", "GenericGroupHandlerBase",
             "PullAndExecuteNextMessage", 0],
            ["IdunBattle.View.BattleStream.StepHandlers", "AStepHandlerBase", "Execute", 3],
            // LE PARSEUR DE TYPE D'ABILITY, ET SON FOND.
            //
            // `ParseAbilityType` remet ses trois `Nullable` à zéro, puis tente TROIS
            // `Enum.TryParse` sur `Group.Source` -- `ActiveAbilityType`, `TriggeredAbilityType`,
            // `EffectType` -- et rend sans rien poser si les trois échouent.
            //
            // ⚠ MAIS `IdunMeta.Utils.Extensions.Enum$$TryParse<T>` NE FAIT PAS DE `TryParse` :
            // son corps appelle `System.Enum.Parse`, qui LÈVE quand le nom n'est pas un membre.
            // Le décompilé seul ne peut pas trancher (IL2CPP compile les `catch` en EH C++,
            // invisibles dans le flux linéaire) -- c'est la MESURE qui tranche.
            //
            // ⚠ `Enum$$Parse` prend DEUX paramètres, pas trois : le `0` final du décompilé est
            // le `MethodInfo*` qu'IL2CPP ajoute à CHAQUE appel. Le compter comme un argument rend
            // l'ancrage INTROUVABLE, et un étage non ancré se lit ensuite « n'a pas tiré » --
            // exactement l'inverse du fait. Mesuré : à 3 il ne tire jamais.
            ["IdunBattle.View.BattleStream.GroupHandlers", "Ability_Power_GroupHandler",
             "ParseAbilityType", 0],
            ["IdunBattle.View.BattleStream.GroupHandlers", "Ability_Power_GroupHandler",
             "OnInitialized", 0],
            // Témoin de branche : appelé UNIQUEMENT si le `TryParse<TriggeredAbilityType>` a
            // réussi, et son corps est de l'arithmétique pure (aucun jet possible).
            ["IdunBattle.View.AbilityConfigs", "StaticAbilityVisualRules",
             "CorrectAbilityIdForVisualsAndIcon", 1],
            // ⛔ `["System", "Enum", "Parse", 2]` A ÉTÉ RETIRÉ, ET IL NE DOIT PAS REVENIR.
            //
            // Mesuré le 2026-08-20 : l'ancrer fait TOMBER LE JEU à l'injection. `System.Enum.Parse`
            // est appelé en permanence par tout le binaire (chargement de config, sérialisation,
            // vues) -- y poser un trampoline est exactement le « broad-hook sur méthode hot » que
            // le `CLAUDE.md` proscrit, et le cap de 600 entrées ne protège pas : le coût est le
            // trampoline, pas le callback.
            //
            // Ce qu'il aurait prouvé est de toute façon DÉJÀ ÉTABLI par quatre mesures
            // convergentes (cf. le commentaire ci-dessus) : `ParseAbilityType` entre avec son
            // groupe et sa source et ne revient pas, son seul jet explicite est exclu, le témoin
            // de la 2ᵉ branche ne tire jamais, et un échec des trois `TryParse` rendrait
            // normalement. Pour l'observer directement il faudrait ancrer le corps gshared
            // `IdunMeta.Utils.Extensions.Enum$$TryParse<T>` -- lui aussi partagé, donc au même
            // prix. Le gain ne vaut pas une chute du jeu.
        ] as const) {
            const kc = findClassAnywhere(c[0], c[1]);
            const mc = kc ? findMethodByParamCount(kc, c[2], c[3]) : null;
            if (!mc || mc.ptr.isNull()) {
                startBattleTrace.push({ evt: "etage INTROUVABLE", etage: `${c[1]}$$${c[2]}`,
                                        params: c[3] });
                continue;
            }
            const tc = lireTete(mc.ptr);
            if (tc.erreur === null && teteTriviale(tc)) {
                // Un corps TRIVIAL est PARTAGÉ : s'y attacher ferait tirer le compteur pour
                // toute autre méthode dédupliquée sur le même corps. On le DIT et on saute.
                startBattleTrace.push({ evt: "etage TRIVIAL (corps partagé, non ancré)",
                                        etage: `${c[1]}$$${c[2]}`, tete: tc });
                continue;
            }
            listenersEtages.push(Interceptor.attach(mc.ptr, {
                onEnter(args) {
                    const s2 = this as unknown as { n: number };
                    s2.n = startBattleTrace.length;
                    if (startBattleTrace.length >= 600) return;
                    const e: Record<string, unknown> = {
                        evt: "entree", etage: `${c[1]}$$${c[2]}`, ghidraVA: ghidraVA(mc.ptr) };
                    // ⚠ LA PILE DE GROUPES, LUE À L'ENTRÉE — c'est ce qui sépare les deux causes
                    // possibles de la levée de `FinishGroup`, indiscernables au repos :
                    //   pile = 0 à l'entrée  -> `Stack.Pop` sur une pile VIDE, donc DÉSÉQUILIBRE ;
                    //   pile >= 1            -> le Pop réussit et c'est le groupe dépilé qui est
                    //                           incomplet (`+0x48`, sa liste d'enfants, nulle).
                    // La lecture post-mortem rend `_size == 0` dans LES DEUX cas.
                    if (c[1] === "MessageGenerator") {
                        try {
                            const pile = args[0].add(0x18).readPointer();
                            e.pile = pile.isNull() ? null : pile.add(0x18).readS32();
                        } catch (err) { e.pile = "ILLISIBLE : " + (err as Error).message; }
                    }
                    // ⚠ LE TYPE DU MESSAGE, sur les deux `Execute` de handler. C'est LA réponse
                    // à « quel message est mal routé » : le gestionnaire de GROUPE lève quand
                    // `message.AsGroup()` rend null, donc quand le message n'est PAS un groupe.
                    // On garde le POINTEUR DE CLASSE (permanent) et on le nomme À LA LECTURE --
                    // pas d'appel IL2CPP depuis un callback qui peut se trouver sur un chemin
                    // de jet.
                    if (c[2] === "Execute" && c[3] === 3) {
                        try {
                            const m = args[1];
                            e.msg = m.toString();
                            e.msgKlass = m.isNull() ? null : m.readPointer().toString();
                            // ⚠ ET LA CLASSE CONCRÈTE DU HANDLER. `ExecuteInternal` est VIRTUEL
                            // (slot 0x1e8) : ancrer celle de `GenericGroupHandlerBase` ne voit
                            // PAS un handler qui la surcharge. Sans ce nom, « Execute ouvert
                            // sans ExecuteInternal ouvert » se lit « il a levé avant » -- alors
                            // qu'il a simplement appelé une AUTRE implémentation, non ancrée.
                            e.selfKlass = args[0].isNull()
                                ? null : args[0].readPointer().toString();
                            // L'INSTANCE elle-même : la pile reste bloquée sur elle, donc elle
                            // survit à la levée et ses champs se lisent APRÈS coup
                            // (`objetChamps`). C'est ce qui permet de nommer LE champ nul.
                            e.self = args[0].toString();
                        } catch (err) { e.msg = "ILLISIBLE : " + (err as Error).message; }
                    }
                    // ⚠ LE `Group` DU HANDLER, LU À L'ENTRÉE. `ParseAbilityType` n'a qu'UN chemin
                    // de jet explicite : `Group == null`. Le relever à la SORTIE ne dit rien --
                    // quand il lève, la sortie n'existe pas, et le champ garde sa valeur par
                    // défaut, qu'on lirait à tort comme « nul MESURÉ ».
                    if (c[1] === "Ability_Power_GroupHandler") {
                        try {
                            const g = args[0].add(0x30).readPointer();
                            e.groupNul = g.isNull();
                            e.source = g.isNull()
                                ? null : readIl2cppString(g.add(0x38).readPointer());
                        } catch (err) { e.groupNul = "ILLISIBLE : " + (err as Error).message; }
                    }
                    if (c[1] === "MessageExecutionQueue") {
                        try {
                            const kq = args[0].readPointer();
                            const off = getFieldOffset(kq, "_currentlyProcessingMessage");
                            e.enTraitement = off < 0 ? null : args[0].add(off).readU8() !== 0;
                            const offM = getFieldOffset(kq, "_messages");
                            if (offM >= 0) {
                                const q = args[0].add(offM).readPointer();
                                e.enFile = q.isNull()
                                    ? null : q.add(getFieldOffset(q.readPointer(), "_size")).readS32();
                            }
                        } catch (err) { e.enTraitement = "ILLISIBLE : " + (err as Error).message; }
                    }
                    startBattleTrace.push(e);
                },
                onLeave(rv) {
                    const s2 = this as unknown as { n: number };
                    const e2 = startBattleTrace[s2.n];
                    if (!e2) return;
                    e2.sortie = true;
                    e2.retour = rv.toInt32() & 0xff;
                    // ⚠ ET LE POINTEUR ENTIER, pas seulement son octet de poids faible. Un
                    // `bool` se lit sur l'octet, mais un getter qui rend une LISTE se perdrait
                    // entièrement -- or c'est précisément ce qu'il faut inspecter ici : la liste
                    // de placeholders sur laquelle la boucle lève. On la garde pour la lire
                    // PLUS TARD, hors de tout callback (`objetChamps` déréférence les `List`).
                    e2.retourPtr = rv.toString();
                },
            }));
        }
        // ⚠ LE VISITEUR, VISÉ PAR LE TYPE DE SON PARAMÈTRE — pas par un compte.
        // `IdunBattle.Messages.InputMessageProcessor` porte des DIZAINES de surcharges de `Visit`
        // à un paramètre : `findMethodByParamCount` en rendrait une au hasard, et l'ancrage
        // serait muet ou pire, faux. `findMethodByParamClasses` est le foyer du dépôt pour ça.
        //
        // C'est le point qui compte : `AddMachineOperation$$Execute` SORT (la machine est créée),
        // et c'est `AddMachineMessage$$Accept` qui ne revient pas. La levée est donc dans ce
        // `Visit`, APRÈS l'opération.
        {
            const kProc = findClassAnywhere("IdunBattle.Messages", "InputMessageProcessor");
            const mV = kProc
                ? findMethodByParamClasses(kProc, "Visit", ["AddMachineMessage"]) : null;
            if (!mV || mV.ptr.isNull()) {
                startBattleTrace.push({ evt: "etage INTROUVABLE",
                                        etage: "InputMessageProcessor$$Visit(AddMachineMessage)" });
            } else {
                const tv = lireTete(mV.ptr);
                listenersEtages.push(Interceptor.attach(mV.ptr, {
                    onEnter() {
                        const s3 = this as unknown as { n: number };
                        s3.n = startBattleTrace.length;
                        if (startBattleTrace.length < 600) {
                            startBattleTrace.push({
                                evt: "entree", ghidraVA: ghidraVA(mV.ptr), tete: tv,
                                etage: "InputMessageProcessor$$Visit(AddMachineMessage)" });
                        }
                    },
                    onLeave(rv) {
                        const s3 = this as unknown as { n: number };
                        const e3 = startBattleTrace[s3.n];
                        if (e3) { e3.sortie = true; e3.retour = rv.toInt32() & 0xff; }
                    },
                }));
            }
        }
        listenerStartBattle = Interceptor.attach(mS.ptr, {
            onEnter(args) {
                const self = this as unknown as { n: number };
                const e: Record<string, unknown> = { evt: "entree",
                                                    etage: "UnitDeploymentState$$StartBattle" };
                try {
                    const st = args[0];
                    const lst = args[1];
                    for (const [nom, off] of [["_stateChanger", 0x10], ["_actions", 0x18],
                                              ["_visualBattleQuery", 0x28]] as const) {
                        const p = st.add(off).readPointer();
                        e[nom] = p.isNull() ? null : p.toString();
                    }
                    e.unitsNul = lst.isNull();
                    e.unitsTaille = lst.isNull() ? null : lst.add(0x18).readS32();
                } catch (err) { e.erreur = (err as Error).message; }
                self.n = startBattleTrace.length;
                if (startBattleTrace.length < 600) startBattleTrace.push(e);
            },
            onLeave(retval) {
                const self = this as unknown as { n: number };
                const e = startBattleTrace[self.n];
                if (e) { e.sortie = true; e.retour = retval.toInt32() & 0xff; }
            },
        });
        Interceptor.flush();
        return { ok: true, action: "attache", ghidraVA: ghidraVA(mS.ptr), tete: t, ...etat() };
    };

    /**
     * S'ANCRER SUR LE LANCEUR DE JET LUI-MÊME — le SITE, pas le symptôme.
     *
     * ⚠ POURQUOI CELUI-LÀ. Toutes les sorties « WARNING: Subroutine does not return » du
     * décompilé de cette famille (`HandleOnStartBattleTapped`, `UnitDeploymentState$$StartBattle`,
     * `Show`, `b__150_0`…) appellent `FUN_1801f5460`, qui appelle son helper puis `int 3` et ne
     * revient jamais : c'est le lanceur de `NullReferenceException` généré par IL2CPP. Son
     * ENTRÉE est donc l'instant exact du jet, et la frame 0 de sa pile est l'adresse de retour
     * DANS la fonction fautive.
     *
     * Ce que ça remplace : le « system error » de Frida (aucun message), le backtrace SEH (16
     * frames toutes nommées `mono_type_size`), et le backtrace d'`invoke_native_error` (qui est
     * la pile de NOTRE agent, pas celle du jeu). Trois étages qui arrivent trop tard ou qui
     * nomment faux.
     *
     * ⚠ ADRESSE ÉPINGLÉE, ET C'EST LE SEUL RÉGIME OÙ C'EST LÉGITIME : `FUN_1801f5460` est un
     * placeholder, il n'a AUCUN `MethodInfo`, donc rien à résoudre au runtime. Elle passe par
     * `pinnedAddress`, qui confronte le build DÉCLARÉ au build CHARGÉ et rend `null` en le
     * disant — jamais un attachement en aveugle.
     *
     * ⛔ IL TIRE POUR TOUT LE JEU. À armer le temps d'une mesure, à désarmer juste après.
     */
    ctx.rpc.deploymentJetArmer = (body?: {
        armer?: boolean; confirmer?: boolean; vider?: boolean;
    }): unknown => {
        if (body?.vider === true) { jetTrace.length = 0; jetFires = 0; }
        // LA RÉSOLUTION DES NOMS SE FAIT ICI, hors du chemin de jet : un `Il2CppClass*` est
        // permanent, donc le nommer plus tard est sûr -- et c'est la seule façon de le faire
        // sans ré-entrer dans le runtime pendant qu'il déroule une exception.
        const etat = () => ({
            arme: listenerJet !== null, tirs: jetFires,
            trace: jetTrace.map((e) => {
                const k = e.klass;
                let nom: string | null = null;
                if (typeof k === "string" && k !== "0x0") {
                    try { nom = s(class_get_name(ptr(k)) as NativePointer); }
                    catch { nom = null; }
                }
                return { ...e, classeException: nom };
            }),
        });
        if (!body || body.armer === undefined) return { ok: true, lecture: true, ...etat() };
        if (body.armer === false) {
            if (listenerJet) { listenerJet.detach(); listenerJet = null; }
            Interceptor.flush();
            return { ok: true, action: "detache", ...etat() };
        }
        if (body.confirmer !== true) {
            return refus("ANCRAGE GLOBAL -- exige `confirmer: true`. `FUN_1801f5460` est le "
                + "lanceur de NullReferenceException de TOUT le binaire : il tire pour chaque "
                + "jet du jeu, pas seulement les nôtres. À désarmer dès la mesure prise.");
        }
        if (listenerJet) return { ok: true, action: "deja arme", ...etat() };
        // ⛔⛔ NE PAS RÉARMER. DEUX MORTS DU JEU, MESURÉES, POUR CETTE SEULE CIBLE.
        //
        // 2026-08-20, minidumps `Tacticus.exe.26196.dmp` (02:09:20) et le suivant : ancrer
        // `FUN_180201a80` tue le processus au premier tir. La première fois, l'explication
        // paraissait suffisante — le `onEnter` appelait `decodeManagedException`, donc on
        // RÉ-ENTRAIT dans IL2CPP pendant qu'il déroulait une exception. On a donc refait la sonde
        // en régime FROID : lectures mémoire seules, `Thread.backtrace` FUZZY, résolution des
        // noms déportée dans le lecteur du RPC. Le jeu est mort EXACTEMENT PAREIL.
        //
        // Ce que la seconde mort établit et que la première ne disait pas : ce n'est pas le
        // CONTENU du callback, c'est le TRAMPOLINE. `Interceptor.attach` réécrit le prologue en
        // `e9 <rel32>` ; sur une fonction que le runtime traverse en plein déroulement de pile,
        // ça détruit l'invariant d'unwind (le déroulement cherche des tables associées au code
        // ORIGINAL). Aucune version « plus prudente » du callback ne peut rattraper ça.
        //
        // ⇒ L'observation du site de jet ne se fait PAS par ancrage du raiser. Les voies qui
        // restent, et qui n'ont PAS tué le jeu : `deploymentStartTracer` (ancrage de méthodes de
        // JEU nommées, entrée sans sortie = c'est celle-là), et le gestionnaire SEH déjà installé
        // par `crash-trap`, qui observe SANS réécrire de prologue.
        if (true as boolean) {
            return refus("REFUS DÉFINITIF -- cet ancrage a tué le jeu DEUX fois (minidumps du "
                + "2026-08-20). La cause n'est pas le callback mais le trampoline posé sur le "
                + "chemin de déroulement d'exception. Utiliser `deploymentStartTracer` "
                + "(méthodes de jeu nommées, entrée sans sortie) ou le gestionnaire SEH de "
                + "`crash-trap`, qui n'écrivent aucun prologue.");
        }
        const p = pinnedAddress({
            va: 0x180201a80, build: "t6dpr4k06g", symbol: "FUN_180201a80", kind: "code",
            what: "LE FOND COMMUN de tous les jets IL2CPP de ce binaire, et il reçoit "
                + "L'OBJET EXCEPTION en premier argument -- donc un seul ancrage rend à la "
                + "fois la classe/le message de l'exception ET le site du jet par sa pile",
            how: "partir d'une sortie « Subroutine does not return » d'une méthode connue, "
                + "descendre la chaîne de helpers (`FUN_1801f5460` -> `FUN_180201bc0` -> "
                + "`FUN_180201ba0`, `FUN_1801f5450` -> `FUN_180201b80`, `FUN_1801f5420`) : "
                + "les trois convergent sur la fonction qui prend l'exception en param_1",
        });
        if (p === null) {
            return { ok: false, error: "adresse ÉPINGLÉE REFUSÉE (build différent ou non "
                + "mesurable) -- aucun attachement. Cf. `pinnedAddressRefusals`." };
        }
        const t = lireTete(p);
        listenerJet = Interceptor.attach(p, {
            onEnter(args) {
                jetFires++;
                if (jetTrace.length >= 24) return;
                // ⛔ LECTURES MÉMOIRE SEULEMENT — aucune ré-entrée dans IL2CPP. La version qui
                // décodait l'exception ici a TUÉ LE JEU au premier tir (cf. `pileGhidraFroide`).
                // On garde le pointeur de CLASSE, qui est permanent, et le lecteur du RPC le
                // nommera dans un contexte sain.
                let klass: string | null = null;
                try { klass = args[0].readPointer().toString(); } catch { /* laissé null */ }
                jetTrace.push({ n: jetFires, exception: args[0].toString(), klass,
                                pile: pileGhidraFroide(this.context, 16) });
            },
        });
        Interceptor.flush();
        return { ok: true, action: "attache", ghidraVA: ghidraVA(p), tete: t, ...etat() };
    };

    /**
     * SE BRANCHER SUR LE VIDANGEUR, ET LIRE LA PILE ENTRANTE.
     *
     * ⚠ C'EST LA RÉPONSE À « L'ERREUR ARRIVE TROP TARD ». Le « system error » du START est un
     * SYMPTÔME : quand il tombe, la cause a déjà eu lieu, et son backtrace SEH ne nomme que des
     * `mono_type_size`. Ce qu'on sait en revanche, c'est QUOI a bougé : les trois dictionnaires
     * du HUD passent de 102 à 0. On s'ancre donc sur le geste lui-même — `Dictionary.Clear` — et
     * on relève la pile AU MOMENT du vidage. L'appelant est alors LU, pas déduit.
     *
     * ⚠ RÉSOLU SUR L'INSTANCE INFLATÉE, jamais sur la définition générique : `findMethod` sur
     * une définition rend le THUNK d'invocation, pas le corps gshared — un ancrage qui se
     * déclare posé et ne tire jamais (#259-b). On part donc de la classe du dictionnaire VIVANT.
     *
     * ⚠ ET IL EST FILTRÉ PAR POINTEUR, PREMIÈRE INSTRUCTION. Ce corps est partagé par toutes les
     * instanciations de même forme : sans filtre, c'est un broad-hook sur du hot path, exactement
     * ce que le `CLAUDE.md` proscrit. On compare `args[0]` aux trois dictionnaires du HUD et on
     * sort. Il s'arme et se désarme À LA DEMANDE — pas au montage.
     */
    ctx.rpc.deploymentVidangeArmer = (body?: {
        armer?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const etat = () => ({
            arme: listenerDictClear !== null, cibles: ciblesVidange.map((c) => c.nom),
            tirs: dictClearTrace.length, trace: dictClearTrace,
        });
        if (!body || body.armer === undefined) return { ok: true, lecture: true, ...etat() };
        if (body.armer === false) {
            if (listenerDictClear) { listenerDictClear.detach(); listenerDictClear = null; }
            ciblesVidange.length = 0;
            Interceptor.flush();
            return { ok: true, action: "detache", ...etat() };
        }
        if (body.confirmer !== true) {
            return refus("ANCRAGE SUR UN CORPS PARTAGÉ -- exige `confirmer: true`. "
                + "`Dictionary.Clear` est un corps gshared appelé par tout le jeu ; le filtre "
                + "par pointeur est la première instruction, mais le trampoline, lui, est payé "
                + "par TOUS les appelants. À désarmer dès la mesure prise.");
        }
        return queueOnMainThread((): Record<string, unknown> => {
            if (hudInstance === null || hudInstance.isNull()) {
                return { ok: false, error: "aucun `UnitDeploymentHud` capturé" };
            }
            const k = findClassAnywhere(NS_HUD, CLS_HUD);
            if (!k) return { ok: false, error: `\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE` };
            if (listenerDictClear) return { ok: true, action: "deja arme", ...etat() };
            ciblesVidange.length = 0;
            for (const nom of ["_unitModels", "_allUnitModels", "_allUnlockedUnitModels"]) {
                const off = getFieldOffset(k, nom);
                if (off < 0) continue;
                try {
                    const d = hudInstance.add(off).readPointer();
                    if (!d.isNull()) ciblesVidange.push({ nom, ptr: d });
                } catch { /* champ illisible : on le DIT par son absence de la liste */ }
            }
            if (ciblesVidange.length === 0) {
                return { ok: false, error: "aucun des trois dictionnaires n'est lisible -- rien "
                    + "à filtrer, et un ancrage SANS filtre est refusé" };
            }
            const kDict = ciblesVidange[0].ptr.readPointer();
            const mClear = findMethod(kDict, "Clear");
            if (!mClear || mClear.ptr.isNull()) {
                return { ok: false, error: "`Clear` INTROUVABLE sur la classe du dictionnaire "
                    + "VIVANT (instance inflatée)" };
            }
            const t = lireTete(mClear.ptr);
            listenerDictClear = Interceptor.attach(mClear.ptr, {
                onEnter(args) {
                    // FILTRE D'ABORD. Tout le reste est derrière cette comparaison.
                    const self = args[0];
                    let nom: string | null = null;
                    for (const c of ciblesVidange) {
                        if (c.ptr.equals(self)) { nom = c.nom; break; }
                    }
                    if (nom === null) return;
                    if (dictClearTrace.length >= 16) return;
                    let avant: string | number | null = null;
                    try { avant = compteDict(self); } catch { /* laisse null */ }
                    dictClearTrace.push({
                        champ: nom, dictionnaire: self.toString(), comptaAvant: avant,
                        dansShow, showEnters, showFires,
                        pile: pileGhidra(this.context, 24),
                    });
                },
            });
            Interceptor.flush();
            return { ok: true, action: "attache", clearVA: ghidraVA(mClear.ptr), tete: t,
                     classeDict: s(class_get_name(kDict) as NativePointer), ...etat() };
        });
    };

    /**
     * LE ROBINET DES NEUF ANCRAGES DE BASCULE — ce qui rend « est-ce NOUS ? » MESURABLE.
     *
     * ⚠ CE RPC EXISTE PARCE QU'UNE OBSERVATION PURE N'ÉTAIT PAS ÔTABLE. `deploymentHudArmer
     * {armer:false}` ne détache que `Show`, `TryMarkUnitAsPlaced` et `AddPlaceholderUnit` ; les
     * neuf `CHEMINS_BASCULE` restaient en place pour la vie de la session. Or nous INVOQUONS
     * `HandleOnSwitchToMachinesOfWarUnitsTapped`, qui en fait partie — et le décompilé en nomme
     * deux autres dans sa descendance. La règle « ne jamais ancrer la méthode qu'on invoque »
     * était donc violée sans qu'aucun geste ne permette de le vérifier.
     *
     * Lecture seule sans `armer`. `seulement: [...]` restreint aux noms donnés — c'est la forme
     * du contrôle : ôter les TROIS de la chaîne d'appel, retenter, et garder les six autres
     * armés pour que la mesure ne perde pas ses témoins.
     */
    ctx.rpc.deploymentCheminsArmer = (body?: {
        armer?: boolean; seulement?: string[];
    }): unknown => {
        const inventaire = (): Record<string, unknown> => {
            const out: Record<string, unknown> = {};
            for (const nom of CHEMINS_BASCULE) {
                out[nom] = { ancre: cheminsListeners[nom] !== undefined,
                             etat: cheminsEtat[nom] ?? null };
            }
            return out;
        };
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, connus: CHEMINS_BASCULE.slice(),
                     ancres: Object.keys(cheminsListeners), chemins: inventaire() };
        }
        const seulement = Array.isArray(body.seulement) && body.seulement.length > 0
            ? body.seulement : undefined;
        if (seulement !== undefined) {
            const inconnus = seulement.filter((n) => !CHEMINS_BASCULE.includes(
                n as typeof CHEMINS_BASCULE[number]));
            if (inconnus.length > 0) {
                return refus(`noms HORS de \`CHEMINS_BASCULE\` : ${inconnus.join(", ")} -- `
                    + `les neuf connus sont ${CHEMINS_BASCULE.join(", ")}`);
            }
        }
        if (body.armer === false) {
            const otes = desarmerChemins(seulement);
            return { ok: true, action: "detache", otes,
                     restentAncres: Object.keys(cheminsListeners), chemins: inventaire() };
        }
        const k = findClassAnywhere(NS_HUD, CLS_HUD);
        if (!k) return refus(`\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE sur ce build`);
        const poses = armerChemins(k, seulement);
        Interceptor.flush();
        return { ok: true, action: "attache", poses,
                 ancres: Object.keys(cheminsListeners), chemins: inventaire() };
    };

    /**
     * EMPRUNT ISOLÉ — invoque la méthode campagne HORS de tout callback d'interception.
     *
     * ⚠ C'EST UN DISCRIMINANT, PAS UNE COMMODITÉ. Mesuré : l'ancrage sur
     * `CampaignProgression$$GetDeployableUnits` attrape les appels NATURELS du jeu (2 fires
     * pendant une navigation de campagne, `dansEmprunt: false`) mais JAMAIS ceux de nos
     * emprunts. Deux lectures restent :
     *
     *   (a) le corps emprunté ne s'exécute pas -- `invokeMethod` rendrait un pointeur sans
     *       rien faire, et toutes nos substitutions seraient des illusions ;
     *   (b) il s'exécute, mais un appel déclenché DEPUIS un callback d'interception n'est pas
     *       re-observé par l'`Interceptor` sur le même thread.
     *
     * Ce RPC tranche : il fait le MÊME appel, depuis la file du thread principal, sans être
     * dans aucun hook. Si le compteur bouge, c'est (b) — nos emprunts marchent, c'est notre
     * OBSERVATION qui est aveugle. S'il ne bouge pas, c'est (a), et c'est bien plus grave.
     *
     * ⚠ La règle « ne jamais ancrer la méthode qu'on invoque » est RESPECTÉE : on invoque
     * `GetUnitsForDeploymentHUD`, on ancre `GetDeployableUnits`. Deux méthodes distinctes.
     * Et c'est un appel que le JEU fait lui-même — pas un natif jamais observé.
     */
    /**
     * PRÉ-EMPRUNT — calcule la valeur empruntée HORS de tout hook, la déboxe, la garde.
     *
     * C'est la forme imposée par le §24 : pendant la délégation, l'`Interceptor` est aveugle,
     * donc `sansFiltre` ne peut pas y agir. En pré-empruntant ici, l'appel est visible, le
     * masque s'applique, et il ne reste au `onLeave` de la délégation qu'un `retval.replace`.
     *
     * ⚠ DEUX CRANS QUE LA VERSION NAÏVE N'AVAIT PAS :
     *
     *   1. **DÉBOXAGE.** `il2cpp_runtime_invoke` BOXE les types valeur, et
     *      `PooledList<System.String>` en est un (`classes.tsv` : `isValueType=1`). Rendre la
     *      BOÎTE là où l'appelant attend la valeur lui fait lire l'en-tête d'objet comme si
     *      c'était le conteneur. La valeur utile est à `+0x10`. Les deux classes sont
     *      PUBLIÉES : c'est le seul moyen de voir qu'on a bien déboxé, plutôt que de
     *      supposer.
     *   2. **RACINE GC.** Entre l'emprunt et la substitution il peut s'écouler un montage
     *      entier. Sans `gcRoot`, la valeur est ramassable.
     */
    /**
     * INITIALISER UNE SOURCE DE MODE SANS RIEN DÉPENSER — en lui CÂBLANT ses dépendances.
     *
     * LE FAIT MESURÉ (décompilé, build `t6dpr4k06g`). Les deux méthodes de roster de
     * `PvpGameModeSource` ont la MÊME et UNIQUE garde :
     *
     *     if (this->_unitProgression != null) { ... }   // sinon : levée
     *
     *   `GetUnitsForDeploymentHUD` -> slot d'interface 0xe3 sur `_unitProgression`
     *   `GetUnlockedUnitsPooled`   -> slot d'interface 0xc  sur `_unitProgression`
     *
     * Puis, dans les deux cas, `ShortLivedPool$$GetListConverted`. Il n'y a AUCUNE donnée de
     * match dans ce chemin : ni adversaire, ni `_currentEncounter`, ni `_currentBattle`.
     *
     * ⇒ Une source « vide » ne l'est pas faute de combat : elle l'est faute de CÂBLAGE. Le
     * service manquant est celui que l'amorce capte déjà (`IdunNavigation._unitProgression`),
     * donc l'écrire ne fabrique rien — on branche l'instance que le jeu emploie partout.
     *
     * ⚠ C'EST UNE ÉCRITURE SUR UN OBJET VIVANT, donc `confirmer: true`, et on RELIT après.
     * Sans corps : lecture pure, on dit ce qui est branché et ce qui manque.
     *
     * ⚠ On n'écrit JAMAIS par-dessus un champ déjà rempli : si le jeu a câblé lui-même, il n'y
     * a rien à faire, et écraser reviendrait à parier que notre instance vaut la sienne.
     */
    ctx.rpc.modeSourceCabler = (body?: {
        mode?: "pvp" | "campagne"; confirmer?: boolean;
    }): Promise<unknown> | unknown => queueOnMainThread(() => {
        const mode = body?.mode ?? "pvp";
        const nomClasse = mode === "pvp" ? "PvpGameModeSource" : "CampaignGameModeSource";
        const src = mode === "pvp" ? getPvpGameModeSourcePtr() : getCampaignGameModeSourcePtr();
        if (!src || src.isNull()) {
            return refus(`aucune \`${nomClasse}\` captée -- \`discoverSources\` la trouve si le `
                + "jeu en a une vivante en mémoire");
        }
        const k = findClassAnywhere(NS_SRC, nomClasse);
        if (!k) return refus(`\`${nomClasse}\` INTROUVABLE sur ce build`);
        // PAR NOM. `getFieldOffset` rend -1 sur un nom absent, et -1 est *truthy* : tester `< 0`.
        const off = getFieldOffset(k, "_unitProgression");
        if (off < 0) {
            return refus(`champ \`_unitProgression\` ABSENT de \`${nomClasse}\` sur ce build `
                + "-- chemin PÉRIMÉ, pas de repli sur un offset");
        }
        const avant = src.add(off).readPointer();
        const prog = getUnitProgressionPtr();
        const etat = {
            mode, instance: src.toString(), champ: `_unitProgression@+0x${off.toString(16)}`,
            avant: avant.isNull() ? null : avant.toString(),
            progressionCaptee: prog === null || prog.isNull() ? null : prog.toString(),
        };
        if (!avant.isNull()) {
            return { ok: true, ...etat, action: "RIEN",
                     note: "déjà câblé par le jeu -- on n'écrase pas ce qu'on n'a pas posé" };
        }
        if (prog === null || prog.isNull()) {
            return refus("aucune `IUnitProgression` captée -- l'amorce ne l'a pas posée. "
                + "Sans elle on n'a rien à câbler, et on n'en fabrique pas.");
        }
        if (body?.confirmer !== true) {
            return { ok: true, lecture: true, ...etat, action: "AUCUNE",
                     note: "`confirmer: true` exigé : ce RPC ÉCRIT un champ d'une source de mode "
                         + "VIVANTE. Il ne dépense rien -- il branche un service déjà capté." };
        }
        src.add(off).writePointer(prog);
        // RELECTURE : une écriture non vérifiée est ce qui a produit, ailleurs dans ce module,
        // deux unités affichant le même modèle sans la moindre erreur.
        const apres = src.add(off).readPointer();
        return { ok: true, ...etat, action: "CABLE",
                 apres: apres.isNull() ? null : apres.toString(),
                 confirme: apres.equals(prog) };
    });

    /**
     * ⚠ `source` — LE PRÊTEUR EST CELUI DU MODE, ET C'EST UNE RÈGLE, PAS UNE OPTION.
     *
     * Le roster affiché doit venir de la source du mode qu'on monte, sinon on importe les
     * PERMISSIONS d'un autre mode. Mesuré le 2026-08-17 : emprunté à la campagne sur un
     * montage PvP, l'écran n'offrait que les Impériaux — parce que
     * `CampaignGameModeSource$$GetUnitsForDeploymentHUD` rend
     * `_campaignProgression.GetDeployableUnits(locationIndex, onlyUnlocked: false)`, soit la
     * liste déployable de CETTE campagne.
     *
     * `PvpGameModeSource$$GetUnitsForDeploymentHUD` est, lui, une LECTURE PURE d'un champ déjà
     * rempli (`this+0x88`, converti en liste poolée) — vérifié au décompilé : aucun appel
     * serveur, aucun matchmaking.
     *
     * ⚠ Le défaut reste `campagne` et la source RETENUE est publiée : un choix implicite entre
     * deux prêteurs se lirait comme « ça marche » alors qu'on offrirait le mauvais roster.
     */
    ctx.rpc.deploymentPoolPreEmprunt = (body?: {
        confirmer?: boolean; oublier?: boolean; source?: "campagne" | "pvp" | "guildBoss";
        encounterIndex?: number; includeLocked?: boolean;
    }): Promise<unknown> | unknown => {
        if (body?.oublier === true) {
            preEmprunt = null; preEmpruntInfo = null;
            return { ok: true, action: "oublie" };
        }
        if (!body || body.confirmer === undefined) {
            return { ok: true, lecture: true, pret: preEmprunt !== null, info: preEmpruntInfo,
                     sources: {
                         campagne: getCampaignGameModeSourcePtr()?.toString() ?? null,
                         pvp: getPvpGameModeSourcePtr()?.toString() ?? null,
                         guildBoss: "via la PROGRESSION, pas une GameModeSource",
                     },
                     note: "`source: \"pvp\"` emprunte le roster à la source PvP -- c'est ce "
                         + "qu'il faut pour un montage PvP ; la campagne n'offrirait que sa "
                         + "propre liste déployable. `source: \"guildBoss\"` passe par "
                         + "`GuildBossProgression$$GetDeployableUnitsPooled`, qui APPLIQUE "
                         + "`DisallowedFactions` -- le filtre du mode, pas une liste brute." };
        }
        if (body.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé : ce RPC INVOQUE la méthode de "
                + "la source de mode vivante." };
        }
        const quelle = body.source ?? "campagne";

        // GUILD BOSS — le prêteur n'est PAS une `GameModeSource` mais la PROGRESSION.
        //
        // ⚠ Ce n'est pas un contournement faute d'instance : au décompilé,
        // `GuildBossGameModeSource$$IsUnitDeployable` ne fait que DÉLÉGUER à la progression
        // (slot d'interface `0x36`, avec son index d'encounter). La règle vit donc là, et
        // `GetDeployableUnitsPooled` APPLIQUE déjà `DisallowedFactions` -- ce qu'on emprunte
        // est le roster FILTRÉ par le mode, pas une liste brute qu'il faudrait re-filtrer.
        if (quelle === "guildBoss") {
            const idx = body.encounterIndex ?? 0;
            const incl = body.includeLocked === true;
            // Retenu pour que le RÉ-EMPRUNT de la délégation reparte du MÊME contexte : un
            // roster frais qui viserait un autre encounter serait pire qu'une liste vide.
            gbEncounterIndex = idx;
            gbIncludeLocked = incl;
            return queueOnMainThread(() => {
                const boite = rosterPooledGuildBoss(idx, incl);
                if (typeof boite === "object" && boite !== null
                    && (boite as { ok?: boolean }).ok === false) {
                    return { ok: false, source: quelle, ...(boite as object) };
                }
                const b = boite as NativePointer;
                gcRoot.add(b);
                const cBoite = classeDerriere(b);
                let deboxe: NativePointer;
                try { deboxe = b.add(0x10).readPointer(); }
                catch (e) {
                    return { ok: false, source: quelle,
                             error: "déboxage impossible : " + (e as Error).message };
                }
                if (deboxe.isNull()) {
                    return { ok: false, source: quelle,
                             error: "déboxage -> NUL : on ne substitue RIEN plutôt que de poser "
                                 + "un pointeur douteux",
                             boite: b.toString(), classeBoite: cBoite.classe };
                }
                gcRoot.add(deboxe);
                const cDeboxe = classeDerriere(deboxe);
                preEmprunt = deboxe;
                preEmpruntInfo = {
                    source: quelle, instance: "progression", encounterIndex: idx,
                    includeLocked: incl,
                    boite: b.toString(), classeBoite: cBoite.classe, erreurBoite: cBoite.erreur,
                    deboxe: deboxe.toString(), classeDeboxee: cDeboxe.classe,
                    erreurDeboxee: cDeboxe.erreur,
                    // Le témoin de `GetDeployableUnits` ne vaut QUE pour la campagne : ni la
                    // source PvP ni la progression guild boss ne passent par elle.
                    deltaGetDeployableUnits: null,
                    masqueArme: sansFiltreArme && sansFiltreEcrit,
                };
                return { ok: true, ...preEmpruntInfo };
            });
        }

        return queueOnMainThread(() => {
            const pvp = quelle === "pvp";
            const nomClasse = pvp ? "PvpGameModeSource" : "CampaignGameModeSource";
            const src = pvp ? getPvpGameModeSourcePtr() : getCampaignGameModeSourcePtr();
            if (!src || src.isNull()) {
                return { ok: false, source: quelle,
                         error: `aucune \`${nomClasse}\` captée -- pour le PvP, `
                             + "`discoverSources` la trouve si le jeu en a une vivante" };
            }
            const kc = findClassAnywhere(NS_SRC, nomClasse);
            if (!kc) return { ok: false, source: quelle,
                              error: `\`${nomClasse}\` INTROUVABLE` };
            const mc = findMethodByParamCount(kc, METHODE, 0);
            if (!mc) return { ok: false, source: quelle,
                              error: `\`${nomClasse}$$${METHODE}\` INTROUVABLE (0 paramètre)` };
            const avant = firesDeployable;
            let boite: NativePointer;
            // Même fenêtre que la délégation, mais ICI elle est observable : c'est tout
            // l'intérêt du pré-emprunt.
            dansEmprunt = true;
            try { boite = invokeMethod(mc.info, src, null); }
            catch (e) {
                dansEmprunt = false;
                return { ok: false, error: "l'emprunt a levé : " + (e as Error).message };
            }
            dansEmprunt = false;
            if (boite.isNull()) return { ok: false, error: "l'emprunt a rendu NUL" };
            gcRoot.add(boite);
            const cBoite = classeDerriere(boite);
            let deboxe: NativePointer | null = null;
            let cDeboxe: { classe: string | null; erreur: string | null } =
                { classe: null, erreur: "non lu" };
            try {
                deboxe = boite.add(0x10).readPointer();
                cDeboxe = classeDerriere(deboxe);
            } catch (e) { cDeboxe = { classe: null, erreur: (e as Error).message }; }
            if (deboxe === null || deboxe.isNull()) {
                return { ok: false, error: "déboxage -> NUL : la valeur à +0x10 est vide, on ne "
                    + "substitue RIEN plutôt que de poser un pointeur douteux",
                         boite: boite.toString(), classeBoite: cBoite.classe };
            }
            gcRoot.add(deboxe);
            preEmprunt = deboxe;
            preEmpruntInfo = {
                // QUI a prêté. Sans ce champ, un roster impérial sur un montage PvP est
                // indiscernable d'un roster correct -- c'est exactement ce qui s'est produit.
                source: quelle, instance: src.toString(),
                boite: boite.toString(), classeBoite: cBoite.classe, erreurBoite: cBoite.erreur,
                deboxe: deboxe.toString(), classeDeboxee: cDeboxe.classe,
                erreurDeboxee: cDeboxe.erreur,
                // Le témoin que l'appel a VRAIMENT traversé `GetDeployableUnits`, et que le
                // masque a pu agir : sans lui, « ok » ne dirait rien.
                // ⚠ Ce témoin ne vaut QUE pour le prêteur campagne : la source PvP ne passe
                // pas par `GetDeployableUnits`, donc un delta nul y est NORMAL, pas un échec.
                deltaGetDeployableUnits: pvp ? null : firesDeployable - avant,
                masqueArme: sansFiltreArme && sansFiltreEcrit,
            };
            return { ok: true, ...preEmpruntInfo };
        });
    };

    ctx.rpc.deploymentPoolEmprunterUneFois = (body?: { confirmer?: boolean }):
        Promise<unknown> | unknown => {
        if (body?.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé : ce RPC INVOQUE une méthode "
                + "native sur la source campagne vivante. C'est une mesure, pas un lecteur." };
        }
        return queueOnMainThread(() => {
            const src = getCampaignGameModeSourcePtr();
            if (!src || src.isNull()) {
                return { ok: false, error: "aucune `CampaignGameModeSource` captée" };
            }
            const kc = findClassAnywhere(NS_SRC, "CampaignGameModeSource");
            if (!kc) return { ok: false, error: "`CampaignGameModeSource` INTROUVABLE" };
            const mc = findMethodByParamCount(kc, METHODE, 0);
            if (!mc) return { ok: false, error: `\`${METHODE}\` INTROUVABLE (0 paramètre)` };
            const avant = firesDeployable;
            let r: NativePointer | null = null;
            let erreur: string | null = null;
            // Cet emprunt-ci est HORS hook, donc l'ancrage le VOIT : c'est le seul endroit où
            // `sansFiltre` peut réellement agir. On ouvre donc la même fenêtre que la
            // délégation -- sans quoi le masque resterait inerte ici aussi.
            dansEmprunt = true;
            try { r = invokeMethod(mc.info, src, null); }
            catch (e) { erreur = (e as Error).message; }
            finally { dansEmprunt = false; }
            return {
                ok: erreur === null,
                erreur,
                retour: r === null || r.isNull() ? null : r.toString(),
                // LE chiffre : combien de fois `GetDeployableUnits` a été vu PENDANT cet appel.
                firesAvant: avant, firesApres: firesDeployable,
                delta: firesDeployable - avant,
                lecture: firesDeployable > avant
                    ? "(b) le corps S'EXÉCUTE -- c'est notre observation depuis un hook qui est "
                      + "aveugle aux appels imbriqués"
                    : "(a) le corps NE s'exécute PAS -- toutes nos substitutions sont des "
                      + "illusions, à re-mesurer avant d'en tirer quoi que ce soit",
            };
        });
    };

    /**
     * LÈVE LE FILTRE DE NŒUD sur le roster emprunté — deux régimes, observation par défaut.
     *
     *   { armer: true }                          -> OBSERVE `args[1]` sans rien écrire
     *   { armer: true, ecrire: true, confirmer: true } -> efface `hasValue`
     *
     * L'observation est le défaut parce qu'on ne sait pas d'avance si le `Nullable<Int32>`
     * arrive par VALEUR (registre) ou par POINTEUR : masquer un pointeur le corromprait, et
     * une faute native sur le thread principal fige le jeu. Lire d'abord coûte un aller-retour.
     */
    ctx.rpc.deploymentPoolSansFiltre = (body?: {
        armer?: boolean; ecrire?: boolean; confirmer?: boolean;
    }): unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, arme: sansFiltreArme, ecrit: sansFiltreEcrit, fires: firesDeployable,
                     observations: observationsNullable,
                     note: "`{ armer: true }` observe ; `{ armer: true, ecrire: true, "
                         + "confirmer: true }` écrit. Lire les observations AVANT d'écrire : "
                         + "un `Nullable<Int32>` par valeur donne `basse`=index et `haute`=1." };
        }
        if (body.armer === false) {
            sansFiltreArme = false; sansFiltreEcrit = false;
            return { ok: true, arme: false, action: "desarme" };
        }
        if (body.ecrire === true && body.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé pour ÉCRIRE : on modifie un "
                + "argument natif en vol. Observer d'abord (`{ armer: true }`)." };
        }
        const r = armerSansFiltre(body.ecrire === true);
        if (r !== true) return r;
        return { ok: true, arme: true, ecrit: sansFiltreEcrit,
                 observations: observationsNullable };
    };

    /**
     * LE PRÊTEUR, LU ET POSITIONNÉ — sans bataille, sans `StartMatch`, sans swap.
     *
     * Sans corps : LECTURE PURE. Avec `{ locationIndex, confirmer: true }` : écrit le seul
     * entier dont dépende le roster.
     *
     * ⚠ POURQUOI CET ENTIER SUFFIT, ET POURQUOI CE N'EST PAS LA MÊME CHOSE QUE POSITIONNER
     * UNE SOURCE. Le décompilé de `CampaignGameModeSource$$GetUnitsForDeploymentHUD` ne lit
     * QUE deux champs :
     *
     *     _campaignProgression.GetDeployableUnits(
     *         locationIndex: Nullable<Int32>(this->_currentLocationIndex),
     *         onlyUnlocked : false)
     *
     * Ni `_currentMatch`, ni `_currentCampaignId`, ni la progression de compte. La crainte
     * écrite plus haut (« un DTO déjà résolu deviendrait périmé ») vaut pour `LoadBattle`,
     * PAS pour le roster : il n'y a aucun DTO dans ce chemin. Et l'identité de la campagne
     * est portée par l'INSTANCE de `_campaignProgression` (`get_CampaignType` est son premier
     * slot d'interface), donc elle ne se règle pas ici.
     *
     * ⚠ `_currentLocationIndex` est restauré par personne : ce qu'on écrit reste écrit. On le
     * publie donc AVANT et APRÈS, pour que l'appelant puisse le remettre.
     */
    ctx.rpc.deploymentPoolPreteur = (body?: {
        locationIndex?: number; confirmer?: boolean; classe?: boolean;
    }): Promise<unknown> | unknown => queueOnMainThread(() => {
        const src = getCampaignGameModeSourcePtr();
        if (!src || src.isNull()) {
            return { ok: false, error: "aucune `CampaignGameModeSource` captée -- l'amorce ne "
                + "l'a pas posée, ou la session a été réinjectée depuis" };
        }
        const kSrc = findClassAnywhere("IdunBattle.ViewLogic.BattleSource",
                                       "CampaignGameModeSource");
        if (!kSrc) return { ok: false, error: "classe `CampaignGameModeSource` introuvable" };
        // PAR NOM, jamais par les +0x68/+0x70 mesurés : `getFieldOffset` rend -1 sur un nom
        // absent, et -1 est *truthy* -- tester `< 0`, jamais `||`.
        const offId = getFieldOffset(kSrc, "_currentCampaignId");
        const offIdx = getFieldOffset(kSrc, "_currentLocationIndex");
        const offProg = getFieldOffset(kSrc, "_campaignProgression");
        if (offId < 0 || offIdx < 0 || offProg < 0) {
            return { ok: false, error: "champ(s) absent(s) de `CampaignGameModeSource` sur ce "
                + `build : _currentCampaignId=${offId} _currentLocationIndex=${offIdx} `
                + `_campaignProgression=${offProg} -- chemin PÉRIMÉ, pas de repli sur un offset` };
        }

        const lire = (): Record<string, unknown> => {
            const idx = src.add(offIdx).readS32();
            // ⛔ ON NE DÉRÉFÉRENCE RIEN DE CE QUE CES CHAMPS CONTIENNENT. Deux gels du jeu
            // le 2026-08-17 (sessions 35 et 36, `Responding=False`, delta CPU nul,
            // `__loadingStep = 12`) : la première version lisait la CLASSE de
            // `_campaignProgression` et le CONTENU de `_currentCampaignId`. `isNull()` ne
            // protège que du zéro -- un pointeur STALE le passe, et `class_get_name` /
            // la lecture d'un `System.String` partent alors dans le vide, sur le thread
            // principal, où un `try/catch` JS n'attrape pas une faute native.
            //
            // Ce lecteur ne rend donc que des SCALAIRES et des ADRESSES, sans jamais suivre
            // un pointeur. C'est assez pour le diagnostic visé (`_currentLocationIndex`), et
            // c'est le seul régime qui ne puisse pas figer.
            const progBrut = src.add(offProg).readPointer();
            const idBrut = src.add(offId).readPointer();
            // ⛔ CE LECTEUR N'INVOQUE RIEN, ET C'EST UNE CICATRICE, PAS UN PRINCIPE.
            //
            // La première version appelait `CampaignProgression$$IsDeploymentUnlocked(idx)`
            // « pour avoir un tri-état » distinguant « mauvais index » de « index bon, roster
            // vide ». Mesuré le 2026-08-17 (session 35) : l'appel n'est JAMAIS revenu, et le
            // jeu a GELÉ -- `Responding=False`, delta CPU 0,03 s sur 8 s,
            // `thor.Loader.__loadingStep = 12`. Relance manuelle exigée.
            //
            // Le natif n'avait jamais été OBSERVÉ : on ne savait pas ce qu'il touche, s'il
            // charge quoi que ce soit, ni s'il est appelable hors de son contexte d'écran.
            // Une commodité de diagnostic ne justifie pas d'invoquer à l'aveugle sur le
            // thread principal. Si ce tri-état est voulu, il se prend par un `Interceptor`
            // sur l'appel que le JEU fait lui-même -- jamais en le provoquant.
            // ⚠ OPT-IN, ET C'EST UNE HISTOIRE D'ACCUSATION PUIS D'ACQUITTEMENT. Ce
            // déréférencement a été RETIRÉ le 2026-08-17 comme cause présumée de deux gels du
            // jeu. Il a ensuite été DISCULPÉ : un troisième gel, même signature
            // (`__loadingStep = 12`), s'est produit sur un inject NU, sans qu'aucun RPC ne soit
            // appelé -- les trois appartiennent au cycle inject (résidu #10021).
            // Il revient donc, mais sur demande explicite : suivre un pointeur de champ reste
            // le geste le plus risqué de ce module, et rien ne prouve qu'il soit TOUJOURS sain.
            let classeProgression: string | null = null;
            if (body?.classe === true && !progBrut.isNull()) {
                try {
                    classeProgression = s(class_get_name(progBrut.readPointer()) as NativePointer);
                } catch (e) { classeProgression = "ILLISIBLE : " + (e as Error).message; }
            }
            return {
                source: src.toString(), locationIndex: idx,
                campaignProgression: progBrut.isNull() ? null : progBrut.toString(),
                classeProgression,
                currentCampaignIdPtr: idBrut.isNull() ? null : idBrut.toString(),
                note: "SCALAIRES ET ADRESSES SEULEMENT -- aucun pointeur n'est suivi, aucun "
                    + "natif invoqué (deux gels du jeu le 2026-08-17). Le NOM de la campagne "
                    + "et la CLASSE de la progression exigeraient de déréférencer : les "
                    + "prendre en OBSERVANT un appel du jeu, jamais en le provoquant.",
            };
        };

        const avant = lire();
        if (body?.locationIndex === undefined) {
            return { ok: true, lecture: true, ...avant,
                     note: "passer { locationIndex, confirmer: true } pour positionner le "
                         + "prêteur. Rien d'autre n'est écrit, et rien ne le restaure." };
        }
        if (body.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé : on écrit dans une source "
                + "VIVANTE du jeu, et personne ne la restaure.", ...avant };
        }
        src.add(offIdx).writeS32(body.locationIndex | 0);
        return { ok: true, action: "positionne", avant, apres: lire() };
    });

    /**
     * LES DEUX BORNES DU HUD, MIRÉES LÀ OÙ ELLES SONT CALCULÉES.
     *
     * ⚠ LE HUD NE DEMANDE PAS SES BORNES À LA SOURCE — il les demande à `VisualBattleQuery`, qui
     * les CALCULE. Décompilé le 2026-08-23 :
     *
     *     IdunBattle.View.FSM.VisualBattleQuery$$MaxUnitsPossibleToStartBattle
     *         = idun.shared.SPMath$$Min( <slot 0x31 de la source>,
     *                                    GetSpawnPointCoordinatedForHumanPlayer(this).Count,
     *                                    <slot 0x33 de la source> )
     *     ...$$MinUnitsNeededToStartBattle : idem, avec <slot 0x32> en 3e terme.
     *
     * puis `idun.Ui.IdunGameHud$$UnitDeployment_ShowHud` passe les deux à
     * `idun.ui.UnitDeploymentHud$$Show(units, min, max, options)`.
     *
     * ⇒ DÉLÉGUER `Min|MaxUnitsPossibleToStartBattle` NE SUFFIT PAS, et c'est le piège : un `Min`
     * à trois termes est écrasé par le plus petit. Mesuré sur l'onslaught Chaos tier 18 — source
     * déléguée à 3 et 5, points d'apparition du joueur = 3 — le HUD affichait quand même `0/0`.
     * Le terme coupable est le PREMIER : `SandboxGameModeSource$$AmountOfUnlockedUnits` rend 0.
     *
     * ⚠ ET IL EST INANCRABLE. Son corps fait TROIS octets (`33 c0 c3` = `xor eax,eax ; ret`) :
     * Frida répond « unable to intercept function ». Ce n'est pas le partage par déduplication
     * qui bloque — c'est la TAILLE. On ne peut donc pas corriger le terme ; on mire la FORMULE.
     *
     * Ce qu'on fait ici : on rejoue `SPMath.Min` des trois MÊMES termes, en lisant les deux qui
     * viennent de la source sur le PRÊTEUR (la vraie source du mode) au lieu du stub. Le terme
     * des points d'apparition, lui, est relu du natif — on ne le devine pas.
     */
    ctx.rpc.deploymentBornesArmer = (body?: {
        armer?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const etat = () => ({
            arme: listenerBornes.length > 0,
            derniers: derniersBornes,
        });
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "{ armer: true, confirmer: true } pour mirer `SPMath.Min` avec les "
                         + "termes du PRÊTEUR. `deploymentPoolArmer {source}` doit avoir été "
                         + "joué d'abord : c'est lui qui désigne la source à interroger." };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                for (const l of listenerBornes) l.detach();
                listenerBornes.length = 0;
                Interceptor.flush();
                return { ok: true, action: "retire", ...etat() };
            }
            if (body.confirmer !== true) {
                return refus("`confirmer: true` exigé : on SUBSTITUE le retour de deux méthodes "
                    + "de `VisualBattleQuery`, que TOUS les modes partagent.");
            }
            if (listenerBornes.length > 0) return { ok: true, action: "deja arme", ...etat() };

            const kQ = findClassAnywhere("IdunBattle.View.FSM", "VisualBattleQuery");
            if (!kQ) return refus("`IdunBattle.View.FSM.VisualBattleQuery` INTROUVABLE");
            const miSpawn = findMethodByParamCount(kQ, "GetSpawnPointCoordinatedForHumanPlayer", 0);
            if (!miSpawn) {
                return refus("`VisualBattleQuery$$GetSpawnPointCoordinatedForHumanPlayer(0)` "
                    + "INTROUVABLE -- sans ce terme on ne peut pas rejouer le `Min` sans le "
                    + "DEVINER, et on ne devine pas");
            }
            const rapport: Array<{ nom: string; ok: boolean; detail: string | null }> = [];
            for (const [nom, surSource] of [
                ["MinUnitsNeededToStartBattle", "MinUnitsNeededToStartBattle"],
                ["MaxUnitsPossibleToStartBattle", "MaxUnitsPossibleToStartBattle"],
            ] as Array<[string, string]>) {
                const mq = findMethodByParamCount(kQ, nom, 0);
                if (!mq) {
                    rapport.push({ nom, ok: false,
                                   detail: `\`VisualBattleQuery$$${nom}(0)\` INTROUVABLE` });
                    continue;
                }
                const t = lireTete(mq.ptr);
                if (t.erreur === null && teteTriviale(t)) {
                    rapport.push({ nom, ok: false,
                                   detail: `corps TRIVIAL (${t.hex}) -- adresse PARTAGÉE` });
                    continue;
                }
                listenerBornes.push(Interceptor.attach(mq.ptr, {
                    onEnter(args) {
                        (this as unknown as { q: NativePointer }).q = args[0];
                    },
                    onLeave(retval) {
                        const q = (this as unknown as { q: NativePointer }).q;
                        const natif = retval.toInt32();
                        const p = sourcePreteuse();
                        if (p.ptr === null || p.ptr.isNull()) {
                            derniersBornes[nom] = { natif, substitue: null,
                                detail: `aucune source \`${p.cls}\` (prêteur ${p.nom})` };
                            return;
                        }
                        try {
                            const klass = p.ptr.readPointer();
                            // ⚠ CHAQUE `Int32` revient BOXÉ : la valeur est à `+0x10`.
                            const entier = (m: string): number | null => {
                                const mi = findMethodByParamCount(klass, m, 0);
                                if (!mi) return null;
                                const b = invokeMethod(mi.info, p.ptr as NativePointer, []);
                                return b.isNull() ? null : b.add(0x10).readS32();
                            };
                            const debloquees = entier("AmountOfUnlockedUnits");
                            const borne = entier(surSource);
                            // Le terme des points d'apparition se RELIT du natif -- c'est une
                            // propriété du PLATEAU, pas de la source : l'emprunter serait faux.
                            const liste = invokeMethod(miSpawn.info, q, []);
                            const places = liste.isNull() ? null : liste.add(0x18).readS32();
                            if (debloquees === null || borne === null || places === null) {
                                derniersBornes[nom] = { natif, substitue: null,
                                    detail: `terme NON MESURÉ (debloquees=${debloquees} `
                                        + `borne=${borne} places=${places}) -- RIEN SUBSTITUÉ` };
                                return;
                            }
                            const v = Math.min(debloquees, places, borne);
                            if (v < 0 || v > 64) {
                                derniersBornes[nom] = { natif, substitue: null,
                                    detail: `résultat ${v} hors borne plausible -- RIEN SUBSTITUÉ` };
                                return;
                            }
                            retval.replace(ptr(v));
                            derniersBornes[nom] = { natif, substitue: v,
                                detail: `Min(debloquees=${debloquees}, places=${places}, `
                                    + `${surSource}=${borne}) = ${v}` };
                        } catch (e) {
                            derniersBornes[nom] = { natif, substitue: null,
                                detail: "a levé : " + (e as Error).message };
                        }
                    },
                }));
                rapport.push({ nom, ok: true, detail: null });
            }
            Interceptor.flush();
            const reussies = rapport.filter((x) => x.ok).length;
            if (reussies === 0) {
                return refus("AUCUNE borne ancrée -- "
                    + rapport.map((x) => `${x.nom} : ${x.detail}`).join(" | "));
            }
            return { ok: true, action: "arme", ancrees: reussies, rapport, ...etat() };
        });
    };

    /**
     * LA SANDBOX EN **WRAPPER** D'UNE VRAIE SOURCE — on ne patche plus stub par stub, on DÉLÈGUE.
     *
     *   { armer: true, confirmer: true }            -> délègue TOUTE la table
     *   { armer: true, confirmer: true, only: [...] } -> délègue seulement ces méthodes
     *   { armer: false }                            -> retire tout
     *
     * `confirmer` est exigé : chaque délégation SUBSTITUE un retour dès l'armement, il n'y a pas
     * de régime transparent (contrairement à la phase). L'observer d'abord n'apprendrait rien —
     * le décompilé dit déjà ce que la sandbox rend.
     *
     * ⚠ CE QUE CE WRAPPER EST, ET CE QU'IL N'EST PAS — mesuré, pas supposé.
     * `CampaignGameModeSource` ne STOCKE pas les règles d'un nœud : elle porte son IDENTITÉ
     * (`_currentCampaignId` `+0x68`, `_currentLocationIndex` `+0x70`) et RÉSOUT sa config
     * (`_currentMatch : CampaignConfigDto` `+0x78`). C'est un RÉSOLVEUR lié à une sélection
     * courante. Déléguer lui importe donc **les règles du nœud où elle pointe** — celui que le
     * amorce a ouvert — et **pas** des règles « génériques » ni celles d'un nœud choisi.
     * Dire « la sandbox devient fidèle » serait faux : elle IMPERSONNE UN NŒUD PARTICULIER.
     * Choisir ce nœud voudrait dire écrire `_currentCampaignId`/`_currentLocationIndex` et
     * re-résoudre `_currentMatch` — NON MESURÉ, et un DTO déjà résolu deviendrait périmé.
     */
    ctx.rpc.deploymentPoolArmer = (body?: {
        armer?: boolean; confirmer?: boolean; only?: string[]; source?: Preteur;
    }): Promise<unknown> | unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, ...etatPool(), preteur: preteurDelegation,
                     note: "{ armer: true, confirmer: true } pour déléguer ; `only` restreint la "
                         + "liste ; `source: \"guildBoss\"` emprunte à la source du MODE plutôt "
                         + "qu'à la campagne -- indispensable pour "
                         + "`GetGameModeSpecificDeploymentHudOptions`, qui porte "
                         + "`supportsMachinesOfWar` ET les restrictions du mode." };
        }
        // Le prêteur est fixé AVANT l'armement : `armerUneDelegation` résout la méthode sur SA
        // classe, donc en changer après coup laisserait des ancrages incohérents.
        if (body.source !== undefined) preteurDelegation = body.source;
        // Les rosters empruntés sont relus au prochain tir : un remontage change de source forgée,
        // et servir le cache d'une bataille précédente donnerait un roster PÉRIMÉ sans le dire.
        idsGuildWar = null;
        idsOnslaught = null;
        idsCampagne = null;
        return queueOnMainThread(() => {
            if (body.armer === false) {
                for (const d of delegations) {
                    if (d.listener) { d.listener.detach(); d.listener = null; }
                    // Le témoin de prêteur suit le listener : le garder après un désarmement
                    // ferait croire à un ré-armement inutile au prochain tour.
                    d.preteurArme = null; d.miCampagne = null; d.ancrage = null;
                }
                Interceptor.flush();
                return { ok: true, action: "retire", ...etatPool() };
            }
            if (body.confirmer !== true) {
                return refus("`confirmer: true` exigé : chaque délégation SUBSTITUE le retour dès "
                    + "l'armement. Et le wrapper fait répondre la sandbox comme LE NŒUD DE CAMPAGNE "
                    + "où pointe la source capturée -- pas comme une source générique.");
            }
            // ⚠ LA GARDE PORTE SUR LE PRÊTEUR RETENU, PAS SUR LA CAMPAGNE. Elle testait
            // `getCampaignGameModeSourcePtr()` quel que soit `source` — un reste de l'époque où
            // la campagne était le seul prêteur. Mesuré le 2026-08-19 : un montage guild boss
            // ENTIÈREMENT gréé (source forgée, BC de la source, override posé) était refusé au
            // motif « rejouer l'amorce », alors qu'`armerUneDelegation` résout sur
            // `sourcePreteuse()` et n'aurait pas lu la campagne une seule fois. Une garde qui
            // accuse une dépendance dont le chemin ne se sert pas fait réparer la mauvaise cause.
            const p = sourcePreteuse();
            if (p.ptr === null || p.ptr.isNull()) {
                return refus(`aucune source \`${p.cls}\` (prêteur ${p.nom}) -- on ne délègue PAS `
                    + "à rien. Campagne : l'amorce ne l'a pas prise (session froide, ou la "
                    + "navigation auto est éteinte) ; guild boss : `guildBossSourceForger "
                    + "{confirmer:true}` n'a pas été appelé ; guild war : "
                    + "`guildWarSourceForger` n'a pas été appelé ; onslaught : "
                    + "`onslaughtSourceForger {alliance, tier, confirmer:true}` n'a pas été "
                    + "appelé.");
            }
            if (body.only !== undefined) {
                const connus = DELEGUEES.map((x) => x.nom);
                const inconnus = body.only.filter((n) => !connus.includes(n));
                if (inconnus.length) {
                    return refus(`méthode(s) hors table : ${inconnus.join(", ")}. Table = `
                        + connus.join(", "));
                }
            }
            const rapport: Array<{ nom: string; ok: boolean; detail: string | null }> = [];
            for (let i = 0; i < delegations.length; i++) {
                const spec = DELEGUEES[i];
                if (body.only && !body.only.includes(spec.nom)) continue;
                const r = armerUneDelegation(delegations[i], spec);
                rapport.push(r === true
                    ? { nom: spec.nom, ok: true, detail: null }
                    : { nom: spec.nom, ok: false, detail: r.error });
            }
            Interceptor.flush();
            // ⚠ UN ARMEMENT QUI N'ARME RIEN N'EST PAS UN SUCCÈS. Ce retour valait `ok: true,
            // action: "arme"` quel que soit le contenu de `rapport` : le détail par méthode y
            // était bien écrit, mais un appelant qui ne le lit pas -- et il n'y a aucune raison
            // de le lire quand `ok` est vrai -- monte sa bataille en croyant l'écran gréé.
            // Mesuré le 2026-08-23 : 4 délégations sur 4 en échec (mauvais namespace du prêteur),
            // `ok: true` rendu, et c'est l'ÉCRAN VIDE qui a fini par le démentir -- après un
            // montage, un armement de relais et un patch d'environnement posés pour rien.
            const reussies = rapport.filter((x) => x.ok).length;
            if (rapport.length > 0 && reussies === 0) {
                return refus(`AUCUNE délégation armée (${rapport.length} tentée(s), prêteur `
                    + `\`${p.nom}\`) -- l'écran resterait VIDE. Détail : `
                    + rapport.map((x) => `${x.nom} : ${x.detail}`).join(" | "));
            }
            return { ok: true, action: "arme", armees: reussies, tentees: rapport.length,
                     rapport, ...etatPool() };
        });
    };

    /**
     * ARMER / FORCER / DÉSARMER la phase de déploiement.
     *
     *   { armer: true }                      -> OBSERVER : pose les deux ancrages, n'écrit RIEN
     *   { forcer: true, confirmer: true }    -> le relais rendra `true` au prochain `Enable`
     *   { forcer: false }                    -> redevient transparent, ancrages en place
     *   { armer: false }                     -> retire tout
     *
     * `confirmer: true` est exigé pour FORCER, parce que c'est le seul geste qui écrit — et il
     * écrit dans la décision d'un objet (`VisualBattleQuery`) que TOUS les modes partagent.
     */
    ctx.rpc.deploymentPhaseArmer = (body?: {
        armer?: boolean; forcer?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        if (!body || (body.armer === undefined && body.forcer === undefined)) {
            return { ok: true, lecture: true, ...etatPhase(),
                     note: "{ armer: true } pour OBSERVER ; puis { forcer: true, confirmer: true }" };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (relaisListener) { relaisListener.detach(); relaisListener = null; }
                if (enableListener) { enableListener.detach(); enableListener = null; }
                Interceptor.flush();
                forcerPhase = false;
                return { ok: true, action: "retire", ...etatPhase() };
            }
            if (body.armer === true) {
                const r = armerPhase();
                if (r !== true) return r;
            }
            if (body.forcer !== undefined) {
                if (relaisListener === null) {
                    return refus("hook NON ARMÉ -- jouer `{ armer: true }` d'abord. Forcer sans "
                        + "avoir observé ne dirait pas si le drapeau `skipUnitDeployment` "
                        + "court-circuite déjà le prédicat.");
                }
                if (body.forcer === true && body.confirmer !== true) {
                    return refus("`confirmer: true` exigé : forcer écrit dans la décision de "
                        + "`VisualBattleQuery`, que TOUS les modes de jeu partagent -- une phase "
                        + "de déploiement apparaîtrait là où le jeu n'en veut pas.");
                }
                forcerPhase = body.forcer === true;
            }
            return { ok: true, action: body.armer === true ? "arme" : "regime", ...etatPhase() };
        });
    };
}
