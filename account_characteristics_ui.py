"""Page Streamlit : relevé fidèle des caractéristiques affichées d'un compte.

Seuls les éléments observés par l'utilisateur sont conservés.
Aucune recherche d'adresse privée, de téléphone ou d'identité civile.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from account_characteristics import (
    CATEGORIES, FIELD_LABELS, format_public_snapshot, normalize_snapshot,
)
from account_characteristics_store import CharacteristicsStore
from profile_review import ProfileLog, normalize_instagram


def render_instagram_page(store, case_id: str | None) -> None:
    st.subheader("Relevé des informations publiques du compte")
    st.write(
        "Ce module permet de conserver les **caractéristiques qu'un compte affiche "
        "lui-même** : nom de profil, présentation, catégorie, statut, lien externe "
        "déclaré et statistiques visibles. Les informations saisies sont des "
        "observations documentaires, et non une preuve de l'identité de son titulaire."
    )
    st.info(
        "Les coordonnées privées, les adresses personnelles et les rapprochements "
        "automatiques destinés à identifier quelqu'un ne font pas partie de cette recherche. "
        "Utilisez les messages et canaux de signalement de la plateforme pour le contact."
    )
    if not case_id:
        st.warning("Créez un dossier dans « Dossiers » avant d'ajouter une observation.")
        return

    review = ProfileLog(store)
    attributes_store = CharacteristicsStore(store)

    with st.form("public_characteristics_form", clear_on_submit=True):
        st.markdown("#### 1. Profil observé")
        left, right = st.columns(2)
        with left:
            raw_handle = st.text_input(
                "Pseudonyme ou URL Instagram *",
                placeholder="@exemple ou https://www.instagram.com/exemple/")
            display_name = st.text_input(
                "Nom exactement affiché sur ce profil",
                help="Ne pas transformer un nom affiché en identité civile supposée.")
            category = st.text_input(
                "Catégorie affichée sur le compte",
                placeholder="Ex. artiste, commerce, créateur")
        with right:
            visibility = st.selectbox("Visibilité", CATEGORIES["visibility"])
            account_kind = st.selectbox("Type de compte", CATEGORIES["account_kind"])
            verified = st.selectbox(
                "Badge visible sur le compte", CATEGORIES["verified_badge"])
        biography = st.text_area(
            "Biographie publique, fidèlement retranscrite", height=135, max_chars=1500,
            placeholder="Texte affiché dans la biographie du profil, sans interprétation.")

        st.markdown("#### 2. Liens déclarés et activité visible")
        left, right = st.columns(2)
        with left:
            website = st.text_input(
                "Site ou page publique affichée directement sur le profil",
                placeholder="https://exemple.org/",
                help="Le lien sera archivé tel qu'observé, sans visite automatique de ce site.")
            direct_messages = st.selectbox(
                "Messagerie du compte", CATEGORIES["direct_messages"])
        with right:
            posts = st.text_input("Publications (nombre entier exact)", placeholder="Ex. 125")
            followers = st.text_input("Abonnés (nombre entier exact)", placeholder="Ex. 12 345")
            following = st.text_input("Abonnements (nombre entier exact)", placeholder="Ex. 253")
        st.caption("Si Instagram affiche un nombre abrégé (par exemple « 12,3 k »), laissez le compteur vide plutôt que d'inventer une valeur exacte.")

        st.markdown("#### 3. Provenance et intégrité")
        a, b = st.columns(2)
        with a:
            observed_date = st.date_input("Date de consultation", value=date.today())
        with b:
            observed_time = st.time_input(
                "Heure de consultation",
                value=datetime.now().time().replace(second=0, microsecond=0))
        source_description = st.text_area(
            "Comment l'observation a-t-elle été réalisée ?",
            placeholder="Ex. consultation directe du profil Instagram, capture complète non modifiée.",
            max_chars=1000)
        context = st.text_area(
            "Observations supplémentaires sur l'état du compte",
            placeholder="Uniquement des faits visibles et pertinents pour le dossier.",
            max_chars=3000)
        captures = st.file_uploader(
            "Captures originales du profil (images ou PDF)",
            type=["png", "jpg", "jpeg", "webp", "pdf"],
            accept_multiple_files=True,
            help="La copie conserve les octets originaux et enregistre une empreinte SHA-256.")
        reviewed = st.checkbox(
            "Je certifie avoir relevé ces informations à partir du profil ou de pièces "
            "consultées légitimement, sans déduire l'identité réelle du titulaire.")
        submitted = st.form_submit_button(
            "Enregistrer l'instantané du compte", type="primary", use_container_width=True)
        if submitted:
            if not reviewed:
                st.error("La confirmation de provenance est nécessaire.")
            else:
                try:
                    snapshot = normalize_snapshot({
                        "biography": biography,
                        "category": category,
                        "visibility": visibility,
                        "account_kind": account_kind,
                        "verified_badge": verified,
                        "public_website": website,
                        "direct_messages": direct_messages,
                        "posts": posts,
                        "followers": followers,
                        "following": following,
                        "source_description": source_description,
                    })
                    username, canonical = normalize_instagram(raw_handle)
                    files = [(f.name, f.getvalue(), f.type or "application/octet-stream")
                             for f in captures]
                    moment = datetime.combine(
                        observed_date, observed_time,
                        tzinfo=ZoneInfo("Europe/Paris")).isoformat(timespec="minutes")
                    recorded_context = (
                        "Caractéristiques publiques déclarées (relevé utilisateur) :\n"
                        + (format_public_snapshot(snapshot) or "Aucune caractéristique précisée")
                        + "\n\nContexte :\n" + context
                    )
                    observation_id = review.add(
                        case_id, username, display_name, moment, recorded_context, files)
                    attributes_store.record(case_id, observation_id, snapshot)
                    st.success("Fiche et pièces consignées, avec horodatage et empreintes.")
                    st.rerun()
                except (ValueError, OSError) as exc:
                    st.error(str(exc))

    st.divider()
    st.subheader("Historique des comptes enregistrés")
    observations = review.list(case_id)
    if not observations:
        st.caption("Aucune observation enregistrée dans ce dossier.")
        return
    snapshots = attributes_store.for_case(case_id)
    accounts = sorted({item["handle"] for item in observations}, key=str.casefold)
    selected = st.selectbox("Pseudonyme", accounts, key="observed_instagram_account")
    handle, canonical = normalize_instagram(selected)
    st.link_button("Consulter le profil Instagram", canonical)
    history = review.timeline(case_id, handle)
    enriched = [{**row, "attributes": snapshots.get(row["id"], {})} for row in history]
    screenshot_count = sum(
        len(store.list_attachments(row["evidence_id"])) for row in history)
    names = {row["display_name"] for row in history if row["display_name"]}
    a, b, c = st.columns(3)
    a.metric("Observations datées", len(history))
    b.metric("Noms affichés relevés", len(names))
    c.metric("Pièces associées", screenshot_count)
    st.caption("Des changements de nom ou d'apparence du compte ne révèlent pas son identité civile.")

    changes = attributes_store.timeline_changes(enriched)
    if changes:
        st.markdown("#### Évolutions constatées entre observations")
        st.dataframe(pd.DataFrame(changes), hide_index=True, use_container_width=True)
    else:
        st.caption("Aucun changement documenté entre deux relevés renseignés.")

    series = []
    for row in enriched:
        s = row["attributes"]
        if any(s.get(col) is not None for col in ("posts", "followers", "following")):
            series.append({
                "Date": row["observed_at"],
                "Publications": s.get("posts"),
                "Abonnés": s.get("followers"),
                "Abonnements": s.get("following"),
            })
    if series:
        st.markdown("#### Compteurs publics enregistrés")
        st.dataframe(pd.DataFrame(series), hide_index=True, use_container_width=True)

    st.markdown("#### Observations conservées")
    for row in reversed(enriched):
        title = row["observed_at"] + " · " + (row["display_name"] or "Nom non relevé")
        with st.expander(title):
            st.write("Nom affiché (non vérifié) :", row["display_name"] or "Non relevé")
            attrs = row["attributes"]
            if attrs:
                for field, label in FIELD_LABELS.items():
                    val = attrs.get(field)
                    if val not in (None, "", "Non déterminé"):
                        st.write("**" + label + "** :", str(val))
            else:
                st.caption("Observation ancienne, sans fiche structurée.")
            st.text(row["context"] or "")
            st.caption("Référence de preuve : " + row["evidence_id"])
            st.caption("Les captures et empreintes SHA-256 restent dans « Chronologie » "
                       "et les archives exportées.")
