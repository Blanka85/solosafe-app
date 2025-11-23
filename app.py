# Force redeploy to use Python 3.11

import streamlit as st
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
from contextlib import contextmanager
from datetime import datetime

# --- Database setup (singleton engine) ---
@st.cache_resource
def get_engine():
    return create_engine("sqlite:///solo_safe.db")

engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# --- Models ---
class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True)
    country = Column(String, index=True, nullable=False)
    city = Column(String, index=True, nullable=False)
    neighborhood = Column(String, index=True, nullable=True)  # None = general city-wide

class SafetyReport(Base):
    __tablename__ = "safety_reports"
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    safety_score = Column(Integer, nullable=False)  # 1–5
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    tags = Column(String)  # comma-separated
    author_initials = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

Base.metadata.create_all(bind=engine)

# --- Proper DB session context manager ---
@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()  # commit on success
    except:
        db.rollback()
        raise
    finally:
        db.close()

# --- Helper ---
def normalize_location(country: str, city: str, neighborhood: str | None):
    country = country.strip().title()
    city = city.strip().title()
    neighborhood = neighborhood.strip() if neighborhood else None
    if neighborhood == "":
        neighborhood = None
    return country, city, neighborhood

def get_or_create_location(db, country: str, city: str, neighborhood: str | None):
    country, city, neighborhood = normalize_location(country, city, neighborhood)
    
    loc = db.query(Location).filter(
        Location.country == country,
        Location.city == city,
        Location.neighborhood.is_(None) if neighborhood is None else Location.neighborhood == neighborhood
    ).first()
    
    if loc:
        return loc
    
    loc = Location(country=country, city=city, neighborhood=neighborhood)
    db.add(loc)
    db.flush()  # get the id without committing yet
    return loc

# --- Streamlit UI ---
st.set_page_config(page_title="SoloSafe", layout="centered")

st.title("🚨 SoloSafe")
st.markdown("**Community-powered safety intel for solo female travelers actually trust**")

tab_search, tab_add = st.tabs(["🔍 Search reports", "➕ Add report"])

# ======= SEARCH TAB =======
with tab_search:
    st.subheader("Search safety reports")
    col1, col2 = st.columns(2)
    with col1:
        country = st.text_input("Country", placeholder="Spain")
    with col2:
        city = st.text_input("City", placeholder="Barcelona")
    neighborhood = st.text_input("Neighborhood (optional)", placeholder="Gothic Quarter, El Raval, etc.")

    tag_filter = st.multiselect(
        "Filter by concern",
        options=["harassment", "pickpocketing", "night_transit", "accommodation",
                 "rideshare", "police_response", "scams", "catcalling", "other"]
    )

    if st.button("Search", type="primary", use_container_width=True):
        if not country or not city:
            st.warning("Please enter at least country and city")
        else:
            country, city, neighborhood = normalize_location(country, city, neighborhood)
            
            with get_db() as db:
                query = db.query(SafetyReport, Location).join(Location).filter(
                    Location.country == country,
                    Location.city == city,
                )
                if neighborhood:
                    query = query.filter(Location.neighborhood == neighborhood)
                else:
                    query = query.filter(Location.neighborhood.is_(None))
                
                if tag_filter:
                    for tag in tag_filter:
                        query = query.filter(SafetyReport.tags.contains(tag))
                
                reports = query.order_by(SafetyReport.created_at.desc()).all()

            if not reports:
                st.info("No reports yet for this location — be the first to help other women! 🚺")
                st.stop()

            for report, loc in reports:
                score_stars = "★" * report.safety_score + "☆" * (5 - report.safety_score)
                st.markdown(f"### {report.title}")
                st.caption(f"{loc.city}, {loc.country}" + (f" – {loc.neighborhood}" if loc.neighborhood else "") + f" · {score_stars} · {report.created_at.strftime('%b %d, %Y')}")
                if report.tags:
                    tags = [t.strip() for t in report.tags.split(",")]
                    st.write(", ".join(f"`{t}`" for t in tags))
                st.write(report.body)
                if report.author_initials:
                    st.caption(f"– {report.author_initials}")
                st.divider()

# ======= ADD REPORT TAB =======
with tab_add:
    st.subheader("Add your experience")
    st.markdown("Your report is anonymous by default. Initials are optional but help build trust.")

    with st.form("add_report", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            country = st.text_input("Country*", placeholder="Spain")
        with col2:
            city = st.text_input("City*", placeholder="Barcelona")
        neighborhood = st.text_input("Neighborhood (optional)", placeholder="Gothic Quarter, Gràcia, etc.")

        safety_score = st.slider("Overall safety feeling", 1, 5, 3, help="1 = felt very unsafe, 5 = felt very safe")
        title = st.text_input("Short title*", placeholder="Felt safe walking alone at night in Gràcia")
        body = st.text_area("What should other women know?*", placeholder="Detailed experience...", height=200)
        tags = st.multiselect("What best describes this experience?", 
                             ["harassment", "pickpocketing", "night_transit", "accommodation",
                              "rideshare", "police_response", "scams", "catcalling", "other"])
        author_initials = st.text_input("Your initials (optional)", placeholder="e.g. M.R.")

        submitted = st.form_submit_button("Submit report", type="primary")

    if submitted:
        if not country or not city or not title or not body:
            st.error("Country, city, title and body are required")
        else:
            country, city, neighborhood = normalize_location(country, city, neighborhood)
            
            with get_db() as db:
                location = get_or_create_location(db, country, city, neighborhood)
                report = SafetyReport(
                    location_id=location.id,
                    safety_score=safety_score,
                    title=title.strip(),
                    body=body.strip(),
                    tags=",".join(tags),
                    author_initials=author_initials.strip() or None
                )
                db.add(report)
            st.success("Thank you — your report is live and helping other women right now ❤️")
            st.balloons()

1
