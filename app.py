"""Finestalk : recherche unique de métadonnées de profils Instagram publics."""
from __future__ import annotations

import hmac
import os
import time

import streamlit as st

from instagram_lookup import lookup_public_profile
from profile_review import normalize_instagram


st.set_page_config(
    page_title="Finestalk — Instagram",
    page_icon="🔎",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
:root {color-scheme:dark;}
.stApp {
    color:#eaf0fa;
    background:
      radial-gradient(ellipse 90% 48% at 50% -12%, rgba(49,92,161,.32), transparent 74%),
      linear-gradient(155deg,#080f20 0%,#0c1426 58%,#0c172a 100%);
}
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"],[data-testid="stSidebar"],
[data-testid="collapsedControl"] {display:none!important;}
.block-container {max-width:820px; padding-top:8vh; padding-bottom:5rem;}
.ft-head {text-align:center; margin:0 auto 2.45rem;}
.ft-emblem {
    display:inline-flex;align-items:center;justify-content:center;
    font-size:24px;color:#d7e9ff;letter-spacing:.05em;
    background:linear-gradient(135deg,#224a77,#172c53);
    height:58px;width:58px;border:1px solid #3e5c82;
    border-radius:19px;box-shadow:0 12px 40px #02071565;
    margin-bottom:1.1rem;
}
.ft-name {font-size:clamp(2.8rem,6vw,4.15rem);font-weight:750;
  letter-spacing:-.075em;color:#f6f9ff;line-height:1.13;margin:.15rem 0;}
.ft-kicker{font-size:.73rem;letter-spacing:.23em;text-transform:uppercase;
  font-weight:700;color:#8cb6e1;margin-top:.6rem;}
.ft-sub{font-size:1.03rem;color:#a4b6ce;line-height:1.75;
  margin:1.1rem auto 0;max-width:560px;}
div[data-testid="stTextInput"] input {
    color:#f7fbff!important;
    background:#16243b!important;
    border:1px solid #3d5470!important;
    border-radius:17px!important;
    height:64px!important;
    font-size:1.08rem!important;
    padding:0 22px!important;
    box-shadow:0 8px 40px #02071535;
}
div[data-testid="stTextInput"] input:focus {
    border-color:#72b2ef!important;
    box-shadow:0 0 0 3px #568dd12e!important;
}
div[data-testid="stTextInput"] input::placeholder{color:#8497ae!important;}
div[data-testid="stForm"] {
    border:1px solid #344961!important; border-radius:18px!important;
    padding:1.25rem!important;background:#142139!important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div {
    background:rgba(18,32,54,.87)!important;
    border:1px solid #344b69!important;border-radius:18px!important;
}
.stMarkdown p, .stCaption, [data-testid="stCaptionContainer"] {
    color:#afc0d6;
}
[data-testid="stHeading"] h2,[data-testid="stHeading"] h3 {color:#f5f8ff;}
hr {border-color:#354862!important;}
.ft-caption {text-align:center;color:#879cb5;font-size:.77rem;
  line-height:1.6;margin-top:1rem;}
.ft-source {font-size:.76rem;color:#92a8c2;text-transform:uppercase;
  letter-spacing:.1em;font-weight:700;margin-bottom:.25rem;}
.ft-value {font-size:1.3rem;color:#f8fbff;font-weight:640;margin-bottom:.4rem;}
.ft-muted {font-size:.85rem;color:#a9bad0;line-height:1.7;}
a {color:#9ecbfa!important;}
@media(max-width:680px){
  .block-container{padding-top:3.7rem;}
  .ft-name{font-size:2.75rem;}
  .ft-sub{font-size:.94rem;}
}
</style>
""", unsafe_allow_html=True)


def configured_password() -> str:
    try:
        secret = str(st.secrets.get("FINESTALK_ACCESS_PASSWORD", ""))
    except (FileNotFoundError, KeyError):
        secret = ""
    return secret or os.environ.get("FINESTALK_ACCESS_PASSWORD", "")


def hero() -> None:
    st.markdown("""
    <div class="ft-head">
      <div class="ft-emblem">F.</div>
      <div class="ft-kicker">Analyse de profils publics</div>
      <div class="ft-name">Finestalk</div>
      <div class="ft-sub">
        Un pseudonyme Instagram. Une lecture claire des informations
        publiquement affichées par le compte.
      </div>
    </div>
    """, unsafe_allow_html=True)


hero()
password = configured_password()
if not password:
    st.error("L'accès n'est pas configuré. Ajoutez FINESTALK_ACCESS_PASSWORD dans les secrets de Streamlit.")
    st.stop()

if not st.session_state.get("finestalk_authenticated", False):
    with st.form("finestalk_login"):
        entered = st.text_input("Mot de passe", type="password", placeholder="Accès privé")
        sent = st.form_submit_button("Accéder à Finestalk", use_container_width=True)
    if sent:
        if hmac.compare_digest(entered.encode("utf-8"), password.encode("utf-8")):
            st.session_state["finestalk_authenticated"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()

query = st.text_input(
    "Rechercher un compte Instagram",
    placeholder="@pseudonyme ou https://instagram.com/pseudonyme",
    label_visibility="collapsed",
    key="profile_query",
)
st.markdown("""
<div class="ft-caption">
Appuyez sur Entrée pour lancer la consultation publique.
Aucune connexion Instagram requise.
</div>
""", unsafe_allow_html=True)

if not query.strip():
    st.stop()

try:
    username, canonical = normalize_instagram(query)
except ValueError as error:
    st.error(str(error))
    st.stop()

# Limite les requêtes involontaires aux reruns Streamlit.
now = time.monotonic()
cached = st.session_state.get("_profile_result")
cached_at = st.session_state.get("_profile_result_at", 0)
if (cached is not None and cached.username.casefold() == username.casefold()
        and now - cached_at < 120):
    result = cached
else:
    with st.spinner("Consultation du profil public…"):
        result = lookup_public_profile(username)
    st.session_state["_profile_result"] = result
    st.session_state["_profile_result_at"] = now

st.divider()
with st.container(border=True):
    st.markdown('<div class="ft-source">Profil Instagram consulté</div>', unsafe_allow_html=True)
    st.subheader("@" + result.username)
    st.caption("Consulté le " + result.checked_at.replace("T", " ") + " UTC")

    if result.status == "metadonnees_publiques":
        st.success("Métadonnées publiques disponibles")
    elif result.status == "metadonnees_partielles":
        st.info("Quelques métadonnées publiques disponibles")
    else:
        st.warning(result.message)

    if result.display_name:
        st.markdown("**Nom affiché sur le profil**")
        st.write(result.display_name)
        st.caption("Nom déclaré par le compte ; il ne prouve pas l'identité civile de son titulaire.")

    if result.public_description:
        st.markdown("**Description publique de la page**")
        st.write(result.public_description)
        st.caption("Texte fourni par les métadonnées Instagram, pas nécessairement une biographie.")

    if result.page_title and result.status in ("metadonnees_publiques", "metadonnees_partielles"):
        with st.expander("Titre public de la page"):
            st.text(result.page_title)

    if result.status not in ("metadonnees_publiques", "metadonnees_partielles"):
        st.caption("Instagram peut exiger une connexion ou limiter l'accès automatisé. "
                   "L'absence de résultat ne permet pas de conclure que le compte n'existe pas.")

    st.link_button("Voir le profil sur Instagram", canonical, use_container_width=True)

st.markdown("""
<div class="ft-caption">
Finestalk n'attribue pas une identité réelle à un pseudonyme.
Aucun rapprochement nominatif, historique ni donnée privée n'est collecté dans cette version.
</div>
""", unsafe_allow_html=True)
