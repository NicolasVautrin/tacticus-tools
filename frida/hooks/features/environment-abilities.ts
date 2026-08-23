// environment-abilities — LE RECEPTACLE `EnvironmentAbilities` ET SON REMPLISSAGE, UN SEUL FOYER.
//
// POURQUOI CE MODULE EXISTE. Deux modules doivent poser un `EnvironmentAbilities` sur une
// configuration de bataille : `guild-war-config` (les buffs de zone) et `sandbox-mode` (la
// pression de fin d'Arene). Leurs SOURCES d'abilities n'ont rien en commun -- des buffs de zone
// d'un cote, une config de saison de l'autre -- mais le RECEPTACLE, lui, est identique : meme
// classe, memes trois membres que le ctor natif ne cree pas, meme facon d'ecrire un
// `EnvironmentAbilityConfiguration` sans passer par son ctor.
//
// Extrait de `guild-war-config.ts` le 2026-08-22, quand `sandbox-mode` a eu besoin des memes
// gestes. Deux copies auraient diverge, et ce sont des ECRITURES en memoire managee : une
// divergence n'y donne pas un resultat different, elle donne un crash.
//
// ⚠ LE CTOR NATIF NE CREE PAS LES MEMBRES. `IdunBattle.Configuration.EnvironmentAbilities..ctor`
// ne prend aucun argument et laisse ses TROIS champs NULS ; c'est l'appelant qui les cree
// (verifie au decompile de la popup GW). D'ou le passage par Newtonsoft, qui connait leurs
// generiques inflates -- introuvables par leur nom.
//
//     +0x10  Abilities               List<EnvironmentAbilityConfiguration>
//     +0x18  EnhancementAbilities    List<EnhancementsEnvironmentAbilityConfiguration>
//     +0x20  AbilitiesConfigurations Dictionary<TriggeredAbilityConfigId, AbilityConfiguration>
//
// ⚠ ET LE DICTIONNAIRE NE SE REMPLIT PAS A LA MAIN. Sa cle est un TYPE VALEUR
// (`TriggeredAbilityConfigId`) : `il2cpp_runtime_invoke` ne distingue pas « pointeur vers la
// valeur » de « valeur BOXEE », le natif DEREFERENCE l'ordinal, et se tromper ne leve pas --
// ca CRASHE le jeu (mesure le 2026-08-21, dump `Tacticus.exe.30620.dmp`). `fusionnerDepuisConfig`
// existe pour ca : elle laisse le NATIF faire l'insertion.

import { findClassAnywhere, findMethodByParamCount, getFieldOffset } from "../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { deserializeFromJson, isDeserializerReady } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { estRefus, refus } from "./lecture-champs.js";
import { Refus } from "./view-command.js";

const NS_CFG = "IdunBattle.Configuration";
const NS_SRC = "IdunBattle.ViewLogic.BattleSource";

/** Un `EnvironmentAbilities` VIDE mais dont les trois membres existent -- enracine.
 *
 *  ⚠ Le JSON n'est pas une commodite : c'est ce qui fait construire les trois generiques
 *  INFLATES par Newtonsoft. `findClassAnywhere` ne les trouverait pas (le nom d'un generique
 *  inflate n'est pas indexe), et un `List`1` nu ne dirait pas son element. */
export function creerReceptacle(): NativePointer | Refus {
    if (!isDeserializerReady()) {
        return refus("`JsonConvert.DeserializeObject` non resolu -- le receptacle "
            + "`EnvironmentAbilities` ne peut pas etre construit (ses trois membres sont des "
            + "generiques INFLATES, introuvables par leur nom)");
    }
    const kEnv = findClassAnywhere(NS_CFG, "EnvironmentAbilities");
    if (!kEnv) return refus("classe `" + NS_CFG + ".EnvironmentAbilities` introuvable");
    let env: NativePointer;
    try {
        env = deserializeFromJson(
            '{"Abilities":[],"EnhancementAbilities":[],"AbilitiesConfigurations":{}}', kEnv);
    } catch (e) {
        return refus("deserialisation d'`EnvironmentAbilities` : " + (e as Error).message);
    }
    if (env.isNull()) return refus("`EnvironmentAbilities` deserialise en NUL");
    gcRoot.add(env);
    return env;
}

/** `env.Abilities += EnvironmentAbilityConfiguration { ConfigId: <type>, Level: <niveau> }`.
 *
 *  ⚠ Les deux structs sont ecrites PAR CHAMP NOMME plutot que par leurs ctors : `Level` n'a
 *  qu'un `val:Int32` et `TriggeredAbilityConfigId` qu'un `AbilityType` + un `VariantId` nul.
 *  Les offsets INTERNES se retranchent de `0x10`, l'en-tete que porte la version BOXEE de la
 *  struct mais pas sa version INLINE. Les offsets sont RESOLUS, jamais ecrits en dur.
 *
 *  ⚠ Un niveau NUL n'arme rien -- c'est ce que fait le natif, pas une commodite. Le retour dit
 *  `false` pour que l'appelant puisse le JOURNALISER au lieu de le deviner. */
export function ajouterAbility(
    env: NativePointer, abilityType: number, niveau: number,
): boolean | Refus {
    if (niveau === 0) return false;

    const kEac = findClassAnywhere(NS_CFG, "EnvironmentAbilityConfiguration");
    const kTid = findClassAnywhere("IdunShared", "TriggeredAbilityConfigId");
    if (!kEac) return refus("classe `EnvironmentAbilityConfiguration` introuvable");
    if (!kTid) return refus("classe `TriggeredAbilityConfigId` introuvable");
    const offCfgId = getFieldOffset(kEac, "ConfigId");
    const offLevel = getFieldOffset(kEac, "Level");
    const offType = getFieldOffset(kTid, "AbilityType");
    const offVariant = getFieldOffset(kTid, "VariantId");
    if (offCfgId < 0 || offLevel < 0 || offType < 0 || offVariant < 0) {
        return refus("champ(s) absent(s) sur ce build : "
            + `ConfigId=${offCfgId} Level=${offLevel} AbilityType=${offType} `
            + `VariantId=${offVariant} -- chemin PERIME, pas de repli sur un offset`);
    }

    const liste = membre(env, "Abilities");
    if (estRefus(liste)) return liste;

    const eac = il2cpp_object_new(kEac) as NativePointer;
    if (eac.isNull()) return refus("allocation d'`EnvironmentAbilityConfiguration` a rendu NUL");
    gcRoot.add(eac);
    eac.add(offCfgId + (offType - 0x10)).writeS32(abilityType);
    eac.add(offCfgId + (offVariant - 0x10)).writePointer(ptr(0));
    eac.add(offLevel).writeS32(niveau);

    const l = liste as NativePointer;
    const mAdd = methode(l.readPointer(), "Add", 1);
    if (estRefus(mAdd)) return mAdd;
    try { invokeMethod(mAdd.info, l, [eac]); }
    catch (e) { return refus("`Abilities.Add` a LEVE : " + (e as Error).message); }
    return true;
}

/** Ce qu'une entree d'ENHANCEMENT porte, cote appelant. */
export interface SpecEnhancement {
    /** Nom PLEIN, tel qu'il est CLE du catalogue : `EnhancementAddTrait:Stationary`. */
    ability: string;
    niveau?: number;
    /** `Nullable<PlayerId>` -- `null`/absent laisse le champ nul, comme le ctor natif. */
    playerId?: number | null;
    /** Les `unitId` VISES. C'est ce que `IdunBattleLogic.Entities.DSLTriggers$$IsEnhancementTarget`
     *  confronte -- l'equivalent du `unitAmount` de l'UI d'incursion. */
    cibles?: string[];
    /** Le MULTIPLICATEUR (`IdunBattleLogic.Entities.DSLFormulas$$EnhancementStack`), pas un
     *  compteur decoratif : mesure sur `EnhancementRegeneration`, stack 1 -> +30 % des PV max,
     *  stack 2 -> +60 %. C'est le `stacks` de l'entree d'incursion. */
    stack?: number;
}

/** `env.EnhancementAbilities += EnhancementsEnvironmentAbilityConfiguration { ... }`.
 *
 *  ⚠ LA SECONDE LISTE NE CIBLE PAS COMME LA PREMIERE, et c'est TOUT l'interet. `Abilities` porte
 *  des abilities dont la cible est ECRITE dans leur `CreateTrigger` (`EnvStartProtection` vise
 *  « le camp qui ne joue pas », `EnvAttemptDebuff` vise `IsInTeam(.., TeamId 2)`) -- il n'y a
 *  aucun argument a passer. `EnhancementAbilities`, elle, porte des `Targets` : le ciblage se
 *  fait PAR UNITE NOMMEE. C'est la seule voie mesuree pour viser des unites choisies.
 *
 *  ⚠ ON CONSTRUIT PAR NEWTONSOFT, PAS PAR CHAMPS. `ajouterAbility` ecrit ses deux structs a la
 *  main parce qu'elles sont plates (`AbilityType` + `VariantId`). Ici la forme est un arbre :
 *  `Targets` est une `List<EnhancementTargetConfiguration>` (generique INFLATE, introuvable par
 *  son nom) dont chaque element porte un `UnitConfigId`, et `PlayerId` est un `Nullable<>` dont
 *  la disposition IL2CPP est l'INVERSE de celle de C# (cf. `case-10046` §6bis, ou lire un
 *  `hasValue` au mauvais offset a fabrique un faux positif 5/5). Newtonsoft connait les trois ;
 *  nous, il faudrait les DEVINER. La forme JSON ci-dessous est celle que le jeu SERIALISE, et
 *  elle est validee de bout en bout : posee dans un seed BC, elle rend le trait sur les seules
 *  unites nommees (`docs/rl/case-10046-debuff-d-environnement.md` §3).
 *
 *  ⚠ Un niveau NUL n'arme rien -- meme regle que `ajouterAbility`, et pour la meme raison. */
export function ajouterEnhancement(
    env: NativePointer, spec: SpecEnhancement,
): { ok: true; note?: string } | Refus {
    const niveau = spec.niveau ?? 1;
    if (niveau === 0) {
        return refus("`" + spec.ability + "` : niveau 0 -- le natif n'arme rien. On REFUSE plutot "
            + "que de rendre un succes qui n'installe rien");
    }
    if (!isDeserializerReady()) {
        return refus("`JsonConvert.DeserializeObject` non resolu -- une entree d'enhancement ne "
            + "peut pas etre construite (ses `Targets` sont un generique INFLATE)");
    }
    const kEec = findClassAnywhere(NS_CFG, "EnhancementsEnvironmentAbilityConfiguration");
    if (!kEec) {
        return refus("classe `" + NS_CFG + ".EnhancementsEnvironmentAbilityConfiguration` "
            + "introuvable -- chemin PERIME sur ce build");
    }

    const cibles = spec.cibles ?? [];
    const stack = spec.stack ?? 1;
    const charge = {
        ConfigId: spec.ability,
        Level: niveau,
        PlayerId: spec.playerId ?? null,
        Targets: cibles.map((u) => ({
            Target: {
                PureId: u, Rarity: null, Level: null,
                IsBorrowed: false, IsPvpOpponent: false,
            },
            Stack: stack,
        })),
        Stack: stack,
    };

    let eec: NativePointer;
    try { eec = deserializeFromJson(JSON.stringify(charge), kEec); }
    catch (e) {
        return refus("deserialisation de l'enhancement `" + spec.ability + "` : "
            + (e as Error).message);
    }
    if (eec.isNull()) {
        return refus("l'enhancement `" + spec.ability + "` s'est deserialise en NUL");
    }
    gcRoot.add(eec);

    const liste = membre(env, "EnhancementAbilities");
    if (estRefus(liste)) return liste;
    const l = liste as NativePointer;
    const mAdd = methode(l.readPointer(), "Add", 1);
    if (estRefus(mAdd)) return mAdd;
    try { invokeMethod(mAdd.info, l, [eec]); }
    catch (e) {
        return refus("`EnhancementAbilities.Add` a LEVE : " + (e as Error).message);
    }

    // ⚠ AUCUNE CIBLE N'EST UN CAS LEGITIME, MAIS IL SE DIT. `EnhancementRegeneration` choisit sa
    // cible dans son propre arbre (`UnitsFromTeam(.., 1)` filtre par `UnitTrait.Hero`) et ignore
    // `Targets` ; `EnhancementAddTrait`, lui, passe par `IsEnhancementTarget` et ne tirera JAMAIS
    // sans cible nommee. On ne peut pas trancher depuis ici sans lire l'arbre de chaque ability --
    // alors on le DIT, au lieu de refuser a tort ou de laisser croire que c'est arme.
    return cibles.length === 0
        ? { ok: true, note: "AUCUNE cible nommée : légitime pour une ability qui choisit sa cible "
            + "dans son propre arbre (ex. `EnhancementRegeneration`), mais une ability gardée par "
            + "`IsEnhancementTarget` (toute la famille `EnhancementAddTrait`) ne tirera JAMAIS" }
        : { ok: true };
}

/** FUSIONNE une `AbilitiesConfiguration` (config PAR MODE) dans le receptacle, PAR LE NATIF.
 *
 *  C'est `AProgressionGameModeSource$$ApplyEnvironmentAbilities(env, extraAbilitiesConfig)`, et
 *  elle fait LES DEUX moities en un appel, lu au decompile :
 *
 *      Abilities.AddRange( Map(extraAbilitiesConfig.<dict>, <lambda>) )
 *      DictionaryExtensions.AddRange( env.AbilitiesConfigurations, extraAbilitiesConfig.<dict> )
 *
 *  La seconde ligne est celle qu'on ne sait PAS ecrire a la main sans risquer le crash de clé
 *  boxee (cf. l'entete). C'est la raison d'etre de cette fonction.
 *
 *  ⚠ `this` N'EST JAMAIS DEREFERENCE par le corps -- il ne lit que des statiques. On lui passe
 *  donc une instance NUE d'`AProgressionGameModeSource`, allouee pour l'occasion : bien TYPEE
 *  (contrairement a un nul) et inerte (contrairement a une source empruntee, dont on ne saurait
 *  pas si la methode la modifie). Si un build futur se met a lire `this`, il lira des champs
 *  nuls et LEVERA -- un echec bruyant, pas un resultat faux.
 *
 *  ⚠ Un `extraAbilitiesConfig` NUL fait sortir le natif immediatement, sans rien ecrire. On
 *  REFUSE en amont plutot que d'appeler pour rien : « l'appel est passe » se lirait comme
 *  « l'environnement est greffe ». */
export function fusionnerDepuisConfig(
    env: NativePointer, extraAbilitiesConfig: NativePointer,
): true | Refus {
    if (extraAbilitiesConfig.isNull()) {
        return refus("`extraAbilitiesConfig` est NUL -- le natif sortirait sans rien ecrire, et "
            + "l'appel se lirait a tort comme un environnement greffe");
    }
    const kSrc = findClassAnywhere(NS_SRC, "AProgressionGameModeSource");
    if (!kSrc) return refus("classe `AProgressionGameModeSource` introuvable");
    const mApply = methode(kSrc, "ApplyEnvironmentAbilities", 2);
    if (estRefus(mApply)) return mApply;

    const inerte = il2cpp_object_new(kSrc) as NativePointer;
    if (inerte.isNull()) {
        return refus("allocation d'une `AProgressionGameModeSource` nue a rendu NUL -- on ne se "
            + "replie PAS sur un `this` nul : le corps est cense l'ignorer, mais le lui passer "
            + "quand meme est une supposition de plus");
    }
    gcRoot.add(inerte);
    try {
        invokeMethod(mApply.info, inerte, [env, extraAbilitiesConfig]);
    } catch (e) {
        return refus("`ApplyEnvironmentAbilities` a LEVE : " + (e as Error).message);
    }
    return true;
}

/** CE QUI EST REELLEMENT INSTALLE -- pour qu'un environnement greffe soit une MESURE.
 *
 *  ⚠ « configure » n'est PAS « installe », et c'est le piege mesure le 2026-08-22 : un grep de
 *  la BC trouve `EnvEndBombardment` TROIS fois (sa config d'ability, son poids IA) alors que la
 *  liste des installees est VIDE. Compter les membres est la seule lecture qui tranche. */
export function resume(env: NativePointer): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const nom of ["Abilities", "EnhancementAbilities"]) {
        const l = membre(env, nom);
        // TRI-ETAT : `null` = PAS LU (membre absent ou illisible), jamais rendu comme un `0`.
        out[nom] = estRefus(l) ? null : tailleDeListe(l as NativePointer);
    }
    const d = membre(env, "AbilitiesConfigurations");
    out.AbilitiesConfigurations = estRefus(d) ? null : tailleDeDictionnaire(d as NativePointer);
    return out;
}

// --- interne ----------------------------------------------------------------------------

/** Un membre du receptacle, par son NOM -- jamais par un offset ecrit en dur. */
function membre(env: NativePointer, nom: string): NativePointer | Refus {
    const kEnv = findClassAnywhere(NS_CFG, "EnvironmentAbilities");
    if (!kEnv) return refus("classe `EnvironmentAbilities` introuvable");
    const off = getFieldOffset(kEnv, nom);
    if (off < 0) return refus("`EnvironmentAbilities." + nom + "` ABSENT sur ce build -- PERIME");
    const p = env.add(off).readPointer();
    if (p.isNull()) {
        return refus("`EnvironmentAbilities." + nom + "` est NUL -- le receptacle n'a pas ete "
            + "cree par `creerReceptacle` (le ctor natif laisse ses trois membres nuls)");
    }
    return p;
}

/** `List<T>._size`, resolu par nom avec repli sur la disposition standard (`+0x18`). */
function tailleDeListe(l: NativePointer): number | null {
    try {
        const off = getFieldOffset(l.readPointer(), "_size");
        return l.add(off < 0 ? 0x18 : off).readS32();
    } catch { return null; }
}

/** `Dictionary<K,V>._count`. `null` = PAS LU. */
function tailleDeDictionnaire(d: NativePointer): number | null {
    try {
        const off = getFieldOffset(d.readPointer(), "_count");
        return off < 0 ? null : d.add(off).readS32();
    } catch { return null; }
}

/** `findMethodByParamCount` mais qui REFUSE par un message NOMME plutot que par un `null`.
 *  Un `null` remonte sans dire QUELLE methode manquait, et le site d'appel le reecrit a chaque
 *  fois -- c'est exactement le genre de garde qu'on veut en un seul endroit. */
function methode(
    klass: NativePointer, nom: string, n: number,
): { info: NativePointer } | Refus {
    const m = findMethodByParamCount(klass, nom, n);
    if (!m) {
        return refus("`" + nom + "(" + n + " parametre(s))` INTROUVABLE sur cette classe "
            + "-- chemin PERIME");
    }
    return m;
}
