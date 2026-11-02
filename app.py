"""Finestalk - interface Streamlit de constitution de dossiers."""
from __future__ import annotations

import csv
import hmac
import io
import os
import sqlite3
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import streamlit as st

from account_characteristics_ui import render_instagram_page

from finestalk_core import (
    ALLOWED_EXTENSIONS, CATEGORIES, Store, classify, make_pdf, make_zip
)

st.set_page_config(page_title="Finestalk | Dossiers & preuves",
                   page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
.stApp { background: #f6f8fc; }
section[data-testid="stSidebar"] { background: #102a42; }
section[data-testid="stSidebar"] * { color: #f3f7fc; }
section[data-testid="stSidebar"] div[data-baseweb="select"] * { color: #1f2937; }
section[data-testid="stSidebar"] input { color: #1f2937; }
.block-container { padding-top: 1.4rem; max-width: 1360px; }
.finehead { padding: 1.35rem 1.55rem; border-radius: 16px;
  background: linear-gradient(110deg,#102a42,#195d78); color: white;
  margin-bottom: 1.2rem; }
.finehead h1 { margin: 0; font-size: 2.2rem; color: #fff; }
.finehead p { margin: .3rem 0 0; color: #d8edf7; }
[data-testid="stMetric"] { background: white; border: 1px solid #e4eaf2;
  border-radius: 12px; padding: 1.1rem; }
h2,h3 { color: #102a42; }
</style>
""", unsafe_allow_html=True)

def protection():
    password = os.environ.get("FINESTALK_ACCESS_PASSWORD", "")
    try:
        password = password or str(st.secrets.get("FINESTALK_ACCESS_PASSWORD", ""))
    except Exception:
        pass
    if not password:
        st.error("Accès désactivé : aucun mot de passe d'application n'est configuré.")
        st.code('$env:FINESTALK_ACCESS_PASSWORD="choisissez-un-mot-de-passe-long"\n'
                'streamlit run app.py', language="powershell")
        st.caption("Stockage local privé. Ne déployez pas cette application sur un serveur public sans isolation des utilisateurs.")
        st.stop()
    if not st.session_state.get("access_ok", False):
        st.title("Finestalk")
        st.write("Espace privé de conservation des preuves.")
        with st.form("login"):
            entered = st.text_input("Mot de passe d'accès", type="password")
            submitted = st.form_submit_button("Ouvrir l'espace", use_container_width=True)
        if submitted:
            if hmac.compare_digest(entered.encode("utf-8"), password.encode("utf-8")):
                st.session_state["access_ok"] = True
                st.rerun()
            else:
                st.error("Accès refusé.")
        st.stop()

protection()
store = Store(os.environ.get("FINESTALK_DATA_DIR", ".finestalk_data"))

def title(subtitle: str):
    st.markdown('<div class="finehead"><h1>FINESTALK</h1><p>' +
                subtitle + '</p></div>', unsafe_allow_html=True)

# Le stockage est commun à un seul espace privé. Une instance partagée
# entre plusieurs personnes exige une authentification et une isolation par utilisateur.
with st.sidebar:
    st.markdown("## 🛡️ Finestalk")
    st.caption("Espace de travail privé")
    if st.button("Verrouiller la session", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    st.divider()
    cases = store.list_cases()
    if cases:
        choices = {c["id"]: f"{c['title']} · {c['status']}" for c in cases}
        chosen = st.selectbox("Dossier actif", list(choices),
                              format_func=lambda key: choices[key], key="case_selector")
    else:
        chosen = None
        st.info("Créez votre premier dossier.")
    page = st.radio("Navigation", [
        "Inspection Instagram", "Tableau de bord", "Dossiers", "Profils observés", "Nouvel élément",
        "Chronologie", "Import CSV", "Rapports & intégrité", "Aide & confidentialité"
    ])
    st.divider()
    st.caption("Les noms affichés et les pseudonymes ne constituent pas une preuve d'identité.")

title({
    "Inspection Instagram": "Observations publiques, instantanés horodatés et suivi des modifications",
    "Tableau de bord": "Vue synthétique et indicateurs documentaires",
    "Dossiers": "Organisation des signalements et situations",
    "Profils observés": "Comptes, URLs et déclarations publiques",
    "Nouvel élément": "Collecte des messages, captures et pièces",
    "Chronologie": "Historique, transcription et annotations",
    "Import CSV": "Importation contrôlée de messages existants",
    "Rapports & intégrité": "Export complet, inventaire et empreintes",
    "Aide & confidentialité": "Mode d'emploi et précautions",
}[page])

if page == "Inspection Instagram":
    render_instagram_page(store, chosen)

elif page == "Dossiers":
    st.subheader("Créer un dossier")
    with st.form("create_case", clear_on_submit=True):
        title_in = st.text_input("Titre de la situation", placeholder="Ex. messages répétés sur Instagram")
        description = st.text_area("Résumé factuel et contexte", height=135,
                                   placeholder="Dates, plateformes, personnes concernées, sans conclure prématurément.")
        submitted = st.form_submit_button("Créer le dossier", type="primary")
        if submitted:
            try:
                ident = store.create_case(title_in, description)
                st.success("Dossier créé.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.subheader("Dossiers existants")
    if cases:
        st.dataframe(pd.DataFrame(cases)[["title", "status", "created_at", "id"]],
                     use_container_width=True, hide_index=True)
    if chosen:
        st.divider()
        status_choices = ["Ouvert", "En cours de signalement", "Transmis", "Clôturé"]
        current = store.get_case(chosen)
        status = st.selectbox("Statut du dossier", status_choices,
                              index=status_choices.index(current["status"]))
        if st.button("Mettre à jour le statut"):
            store.set_status(chosen, status)
            st.success("Statut enregistré dans le journal.")
            st.rerun()

elif not chosen and page != "Aide & confidentialité":
    st.info("Commencez dans « Dossiers » pour créer une situation à documenter.")

elif page == "Tableau de bord":
    data = store.list_evidence(chosen)
    profiles = store.list_profiles(chosen)
    score, checklist = store.completeness(chosen)
    categories = [cat for item in data for cat in item["categories"]]
    a, b, c, d = st.columns(4)
    a.metric("Éléments conservés", len(data))
    b.metric("Profils consignés", len(profiles))
    c.metric("Pièces jointes", sum(len(store.list_attachments(e["id"])) for e in data))
    d.metric("Complétude documentaire", f"{score}/100")
    st.progress(score / 100)
    st.caption("Ce score représente uniquement les champs et pièces renseignés. Il ne mesure ni la gravité des faits, ni une probabilité d'identification ou de culpabilité.")
    left, right = st.columns([1.4, 1])
    with left:
        st.subheader("Chronologie des éléments")
        dated = []
        for e in data:
            raw = e["occurred_at"]
            try:
                dated.append(pd.to_datetime(raw).date())
            except Exception:
                pass
        if dated:
            series = pd.Series(dated).value_counts().sort_index()
            st.line_chart(pd.DataFrame({"Éléments": series}))
        else:
            st.info("Aucune date de faits exploitable pour le graphique.")
        st.subheader("Signaux lexicaux")
        if categories:
            counts = pd.Series(categories).value_counts()
            st.bar_chart(counts)
        else:
            st.caption("Aucun mot-clé repéré. Cela ne signifie pas qu'il n'y a pas de harcèlement.")
    with right:
        st.subheader("Vérifications du dossier")
        for label, state in checklist.items():
            st.write(("✅" if state["satisfait"] else "○") +
                     f" {label} ({state['points']} points)")
        st.divider()
        st.info("Un message isolé peut être grave. La répétition et le contexte sont importants, mais le tableau de bord ne pose aucun diagnostic juridique.")

elif page == "Profils observés":
    st.subheader("Consigner un compte observé")
    with st.form("create_profile", clear_on_submit=True):
        l, r = st.columns(2)
        with l:
            platform = st.selectbox("Plateforme", ["Instagram", "Facebook", "TikTok",
                          "X", "Snapchat", "Discord", "WhatsApp", "Autre"])
            handle = st.text_input("Pseudonyme exact, sans @")
        with r:
            profile_url = st.text_input("URL publique du profil (si connue)")
            public_name = st.text_input("Nom affiché sur le compte (non vérifié)")
        observations = st.text_area("Observations factuelles",
                 placeholder="Ex. biographie déclarée publiquement, changement visible du pseudonyme…")
        if st.form_submit_button("Enregistrer le profil", type="primary"):
            try:
                store.add_profile(chosen, platform, handle, profile_url, public_name, observations)
                st.success("Profil consigné. Aucune identité civile n'a été inférée.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.subheader("Comptes consignés")
    for p in store.list_profiles(chosen):
        with st.expander(f"{p['platform']} · @{p['handle']}"):
            st.write("Lien :", p["url"] or "Non renseigné")
            st.write("Nom affiché, non vérifié :", p["public_name"] or "Non renseigné")
            st.write("Observations :", p["observations"] or "Aucune")
            st.caption("Plusieurs profils partageant un pseudo ne sont pas nécessairement liés à la même personne.")

elif page == "Nouvel élément":
    st.subheader("Ajouter une observation ou un message")
    st.caption("Conservez les messages exacts, sans correction orthographique. Les captures et exports originaux sont à privilégier.")
    profiles = store.list_profiles(chosen)
    profile_options = {"Aucun profil associé": None}
    profile_options.update({f"{p['platform']} · @{p['handle']}": p["id"] for p in profiles})
    with st.form("add_event", clear_on_submit=True):
        a, b = st.columns(2)
        with a:
            source = st.selectbox("Canal", ["Instagram - message privé", "Instagram - commentaire",
                "Instagram - story", "Instagram - publication", "Facebook", "TikTok",
                "Discord", "WhatsApp", "SMS", "Courriel", "Autre"])
            profile_label = st.selectbox("Compte associé (facultatif)", list(profile_options))
            author_display = st.text_input("Auteur tel qu'affiché dans le message")
            url = st.text_input("Lien direct vers le message, s'il existe")
        with b:
            unknown_date = st.checkbox("Date/heure des faits inconnue", value=False)
            moment_date = st.date_input("Date des faits", value=date.today(),
                                         disabled=unknown_date)
            moment_time = st.time_input("Heure des faits", value=time(12, 0),
                                         disabled=unknown_date)
            tz = st.text_input("Fuseau horaire", value="Europe/Paris",
                               disabled=unknown_date)
        transcript = st.text_area("Transcription fidèle du contenu", height=185,
                        placeholder="Copiez ici les propos exacts, y compris les insultes éventuelles.")
        context = st.text_area("Contexte, témoins et observations", height=100)
        manual = st.multiselect("Catégories à vérifier manuellement", list(CATEGORIES))
        uploads = st.file_uploader("Captures, exports et fichiers originaux (15 max, 25 Mo chacun)",
            accept_multiple_files=True, type=[x.lstrip(".") for x in ALLOWED_EXTENSIONS])
        submitted = st.form_submit_button("Conserver cet élément", type="primary")
        if submitted:
            try:
                if unknown_date:
                    occurred = ""
                else:
                    zone = ZoneInfo(tz.strip())
                    occurred = datetime.combine(moment_date, moment_time, tzinfo=zone).isoformat(timespec="minutes")
                files = [(f.name, f.getvalue(), f.type or "application/octet-stream") for f in uploads]
                event_id = store.add_evidence(
                    chosen, profile_options[profile_label], source, occurred,
                    author_display, url, transcript, context, files, manual)
                st.success(f"Élément archivé : {event_id}")
                st.caption("Les pièces sont copiées et leur SHA-256 est conservé. Cette empreinte ne certifie pas l'authenticité préalable à la collecte.")
            except (ValueError, OSError, ZoneInfoNotFoundError) as exc:
                st.error(str(exc))

elif page == "Chronologie":
    events = store.list_evidence(chosen)
    st.subheader("Rechercher et relire")
    search = st.text_input("Rechercher dans les messages, auteurs, URLs et contextes")
    cat_filter = st.multiselect("Catégories lexicales", list(CATEGORIES))
    show_only_unreviewed = st.checkbox("Éléments non relus seulement")
    def keep(e):
        haystack = " ".join(str(e[k]) for k in ("transcript", "author_display", "url", "context", "source", "profile_handle")).casefold()
        return (search.casefold() in haystack
                and (not cat_filter or any(c in e["categories"] for c in cat_filter))
                and (not show_only_unreviewed or not e["confirmed"]))
    filtered = [e for e in events if keep(e)]
    st.caption(f"{len(filtered)} élément(s) sur {len(events)}")
    if filtered:
        frame = pd.DataFrame([{
            "Date des faits": e["occurred_at"] or "Inconnue",
            "Auteur affiché": e["author_display"] or "Non renseigné",
            "Source": e["source"], "Catégories": ", ".join(e["categories"]),
            "Relu": bool(e["confirmed"]), "Référence": e["id"][:8],
        } for e in filtered])
        st.dataframe(frame, hide_index=True, use_container_width=True)
    for e in filtered[:150]:
        label = f"{e['occurred_at'] or 'Date inconnue'} · {e['source']} · {e['id'][:8]}"
        with st.expander(label):
            st.caption(f"Référence complète : {e['id']}")
            st.write("Auteur déclaré :", e["author_display"] or "Non renseigné")
            st.write("Compte :", e["profile_handle"] or "Non associé")
            st.write("Lien :", e["url"] or "Aucun")
            st.write("Date de conservation :", e["collected_at"])
            st.markdown("**Texte conservé**")
            st.text(e["transcript"] or "(aucune transcription)")
            st.markdown("**Contexte**")
            st.write(e["context"] or "Non renseigné")
            automatic = classify(e["transcript"])
            st.write("Repérages lexicaux :", ", ".join(automatic) or "Aucun")
            st.write("Catégories enregistrées :", ", ".join(e["categories"]) or "Aucune")
            st.caption("Le repérage lexical peut omettre l'ironie, les images, les formulations détournées ou produire des faux positifs.")
            for f in store.list_attachments(e["id"]):
                try:
                    raw = store.attachment_bytes(f)
                    st.download_button(f"Télécharger la pièce : {f['original_name']}",
                        data=raw, file_name=f["original_name"],
                        mime="application/octet-stream", key=f"download_{f['id']}")
                    st.caption("SHA-256 : " + f["sha256"])
                except (OSError, ValueError) as exc:
                    st.error(f"Pièce inaccessible : {exc}")
            for n in store.list_notes(e["id"]):
                st.caption(f"Annotation · {n['created_at']}")
                st.write(n["text"])
            if not e["confirmed"]:
                if st.button("Marquer comme relu", key=f"review_{e['id']}"):
                    store.mark_reviewed(e["id"])
                    st.rerun()
            else:
                st.success("Relu et enregistré dans le journal.")
            with st.form("note_" + e["id"], clear_on_submit=True):
                note = st.text_area("Ajouter une annotation, sans modifier l'original",
                                    key="notetext_" + e["id"])
                if st.form_submit_button("Ajouter l'annotation"):
                    try:
                        store.add_note(e["id"], note)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
    if len(filtered) > 150:
        st.warning("Seuls les 150 premiers éléments filtrés sont affichés. Affinez la recherche.")

elif page == "Import CSV":
    st.subheader("Importer plusieurs transcriptions")
    st.write("Colonnes acceptées : **texte** (obligatoire), **date**, **source**, **auteur**, **url**, **contexte**, **pseudo**.")
    st.caption("Utilisez un export que vous avez le droit de consulter. L'import ne contacte aucune plateforme.")
    up = st.file_uploader("Fichier CSV UTF-8", type=["csv"], key="csvimport")
    if up:
        raw = up.getvalue()
        if len(raw) > 2 * 1024 * 1024:
            st.error("Import limité à 2 Mo.")
        else:
            try:
                decoded = raw.decode("utf-8-sig")
                rows = list(csv.DictReader(io.StringIO(decoded)))
                if "texte" not in (rows[0].keys() if rows else []):
                    st.error("La colonne « texte » est obligatoire.")
                elif len(rows) > 500:
                    st.error("500 lignes maximum par import.")
                else:
                    st.write(f"{len(rows)} ligne(s) détectée(s).")
                    st.dataframe(pd.DataFrame(rows[:10]), hide_index=True, use_container_width=True)
                    st.warning("Vérifiez les dates et les auteurs avant de confirmer. Une ligne importée ne peut pas être supprimée dans l'application.")
                    if st.button("Importer les lignes", type="primary"):
                        profile_lookup = {p["handle"].casefold(): p["id"] for p in store.list_profiles(chosen)}
                        successful = 0
                        errors = []
                        for idx, row in enumerate(rows, 2):
                            try:
                                text_value = (row.get("texte") or "").strip()
                                if not text_value:
                                    raise ValueError("Texte vide")
                                store.add_evidence(
                                    chosen, profile_lookup.get((row.get("pseudo") or "").lstrip("@").casefold()),
                                    row.get("source") or "Import CSV", row.get("date") or "",
                                    row.get("auteur") or "", row.get("url") or "",
                                    text_value, row.get("contexte") or "Import CSV", [])
                                successful += 1
                            except (ValueError, OSError) as exc:
                                errors.append(f"Ligne {idx} : {exc}")
                        st.success(f"{successful} élément(s) importé(s).")
                        if errors:
                            st.warning("Certaines lignes n'ont pas été importées : " + " ; ".join(errors[:12]))
            except UnicodeDecodeError:
                st.error("Le fichier doit être encodé en UTF-8.")
            except csv.Error as exc:
                st.error(f"CSV invalide : {exc}")

elif page == "Rapports & intégrité":
    st.subheader("Vérifier les éléments")
    attachment_status = store.verify_attachments(chosen)
    audit_status = store.verify_audit()
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Pièces vérifiées", len(attachment_status))
        good = sum(r["etat"] == "Intègre" for r in attachment_status)
        st.write(f"{good}/{len(attachment_status)} pièces intègres selon leurs empreintes enregistrées.")
    with col2:
        st.metric("Journal d'audit", "Cohérent" if audit_status["ok"] else "Incohérent")
        st.caption(f"{audit_status['entrees']} entrées contrôlées.")
    if attachment_status:
        st.dataframe(pd.DataFrame(attachment_status), hide_index=True, use_container_width=True)
    if not audit_status["ok"] or any(r["etat"] != "Intègre" for r in attachment_status):
        st.error("Une incohérence a été détectée. Conservez une copie du dossier et vérifiez manuellement.")
    st.divider()
    st.subheader("Rapports et archive du dossier")
    st.write("Le ZIP contient le PDF, un rapport JSON, les fichiers originaux et un manifeste d'empreintes SHA-256.")
    if st.button("Préparer les exports", type="primary"):
        try:
            report = store.build_report(chosen)
            pdf = make_pdf(report)
            archive = make_zip(store, chosen)
            st.session_state["export_for"] = chosen
            st.session_state["export_pdf"] = pdf
            st.session_state["export_zip"] = archive
            st.success("Exports préparés.")
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    if st.session_state.get("export_for") == chosen:
        a, b = st.columns(2)
        with a:
            st.download_button("Télécharger le rapport PDF", st.session_state["export_pdf"],
                               file_name=f"finestalk_{chosen[:8]}.pdf",
                               mime="application/pdf", use_container_width=True)
        with b:
            st.download_button("Télécharger toutes les preuves (ZIP)", st.session_state["export_zip"],
                               file_name=f"finestalk_{chosen[:8]}.zip",
                               mime="application/zip", use_container_width=True)
    st.caption("Le rapport liste ce qui a été conservé et horodaté localement. Un SHA-256 prouve la stabilité après collecte, pas l'authenticité initiale d'une capture.")

elif page == "Aide & confidentialité":
    st.subheader("Ce que fait Finestalk")
    st.markdown("""
- **Dossier chronologique** : conserver messages, publications, URLs, dates des faits et contexte.
- **Pièces originales** : copier captures, fichiers et exports, sans les altérer.
- **Recherche et repérages** : détecter des expressions explicites d'insulte, de menace ou de pression, avec relecture humaine obligatoire.
- **Journal d'audit** : chaîner les opérations par empreinte SHA-256 et détecter certaines modifications.
- **Export autonome** : produire un PDF, un JSON et une archive ZIP des pièces.

**Ce que Finestalk ne fait pas** : pirater un compte, contourner les protections d'une plateforme, identifier une personne à partir d'un pseudonyme, chercher des adresses privées, classer des suspects ou calculer une probabilité de culpabilité. Un nom affiché dans une biographie est une déclaration non vérifiée.

**Protection** : ce déploiement utilise un mot de passe d'accès commun à son espace de stockage. Il n'est pas adapté à une plateforme publique multiutilisateur. Pour un usage individuel, privilégiez une exécution locale, avec chiffrement du disque et sauvegardes privées. Ne chargez pas de pièces confidentielles dans une instance gérée par un tiers.

**En cas de danger immédiat en France** : appelez le 17 ou le 112. Conservez les originaux, signalez les contenus sur la plateforme et faites-vous accompagner, notamment par le 3018 pour le cyberharcèlement.
    """)
    st.info("La détection par mots-clés est volontairement indicative : une phrase violente peut être citée, niée ou employée hors contexte; inversement, beaucoup de violences ne contiennent aucun mot-clé.")
