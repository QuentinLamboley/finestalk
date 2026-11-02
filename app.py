"""Finestalk : recherche unique de métadonnées de profils Instagram publics."""
from __future__ import annotations

import hmac
import os
import time

import streamlit as st

from public_presence import check_public_presence, search_links
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
        Un pseudonyme. Des présences publiques vérifiées sur plusieurs
        plateformes, avec des liens vers leurs sources.
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
Appuyez sur Entrée pour vérifier la présence publique de ce pseudonyme.
Un pseudo identique ne signifie pas une même personne.
</div>
""", unsafe_allow_html=True)

if not query.strip():
    st.stop()

try:
    username, canonical = normalize_instagram(query)
except ValueError as error:
    st.error(str(error))
    st.stop()

# Conserve uniquement des résultats publics de présence en mémoire de session.
now = time.monotonic()
cached = st.session_state.get("_presence_report")
cached_at = st.session_state.get("_presence_at", 0.0)
if cached is not None and st.session_state.get("_presence_handle") == username.casefold() and now - cached_at < 180:
    results = cached
else:
    with st.spinner("Vérification de la présence publique sur cinq plateformes…"):
        results = check_public_presence(username)
    st.session_state["_presence_handle"] = username.casefold()
    st.session_state["_presence_report"] = results
    st.session_state["_presence_at"] = now

present = [r for r in results if r.state == "found"]
missing = [r for r in results if r.state == "absent"]
unknown = [r for r in results if r.state in ("unknown", "unsupported")]

st.divider()
st.markdown('<div class="ft-source">Recherche de présence publique</div>', unsafe_allow_html=True)
st.subheader("@" + username)
st.caption("Plateformes vérifiées via leurs interfaces publiques · "
           "Aucune recherche de données personnelles")

a, b, c = st.columns(3)
a.metric("Comptes trouvés", len(present))
b.metric("Sans fiche publique", len(missing))
c.metric("Non vérifiables", len(unknown))

if present:
    st.success(str(len(present)) + " compte(s) avec ce pseudonyme exact confirmé(s) par une API publique.")
else:
    st.info("Aucune présence n'a été confirmée par les interfaces interrogées. "
            "Cela ne signifie pas que ce pseudonyme n'est utilisé nulle part.")

for item in results:
    with st.container(border=True):
        left, right = st.columns([3, 1])
        with left:
            st.markdown("**" + item.platform + "**")
            if item.state == "found":
                st.caption("● Pseudonyme exact retrouvé · Compte public")
            elif item.state == "absent":
                st.caption("○ Aucune fiche publique trouvée")
            elif item.state == "unsupported":
                st.caption("— Format du pseudo non compatible")
            else:
                st.caption("◌ Vérification indisponible")
            st.write(item.description)
        with right:
            if item.state == "found":
                st.link_button("Voir le compte", item.profile_url, use_container_width=True)
            elif item.profile_url and item.state != "unsupported":
                st.link_button("Vérifier", item.profile_url, use_container_width=True)
        with st.expander("Source de la vérification"):
            st.code(item.source_url or "Aucune requête possible", language=None)
            st.caption("Réponse HTTP : " + str(item.http_status or "non disponible"))
            st.caption("Consultation : " + item.checked_at)

st.markdown("#### Explorer les résultats publics indexés")
st.caption("Ces liens ouvrent des recherches exactes dans des moteurs externes. "
           "Les résultats ne sont pas récupérés ni interprétés automatiquement.")
engines = search_links(username)
cols = st.columns(3)
for col, (engine, url) in zip(cols, engines.items()):
    with col:
        st.link_button(engine, url, use_container_width=True)

st.link_button("Ouvrir le profil Instagram", canonical, use_container_width=True)
st.markdown("""
<div class="ft-caption">
La présence du même pseudonyme sur deux plateformes ne prouve pas que
les comptes sont contrôlés par la même personne. Aucun nom civil,
coordonnée privée ou score d'identité n'est déduit.
</div>
""", unsafe_allow_html=True)
