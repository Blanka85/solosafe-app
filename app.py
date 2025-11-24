###############################################
# SoloSafe (Upgraded MVP)
# Single-file Streamlit App with Dashboard, Analytics, Examples
###############################################

import streamlit as st
import altair as alt
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, ForeignKey,
    DateTime, func, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from contextlib import contextmanager
from datetime import datetime
import math

# =========================================================
# DATABASE SETUP
# =========================================================
@st.cache_resource
def get_engine():
    return create_engine("sqlite:///solo_safe.db")

engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# ------------------ MODELS ------------------
class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True)
    country = Column(String, index=True, nullable=False)
    city = Column(String, index=True, nullable=False)
    neighborhood = Column(String, index=True)

    reports = relationship("SafetyReport", back_populates="location")

Index("idx_country_city", Location.country, Location.city)


class SafetyReport(Base):
    __tablename__ = "safety_reports"
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id"))
    safety_score = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    tags = Column(String)
    author_initials = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    location = relationship("Location", back_populates="reports")

Index("idx_report_location", SafetyReport.location_id)

Base.metadata.create_all(bind=engine)


# ------------------ SESSION MANAGER ------------------
@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except:
        db.rollback()
        raise
    finally:
        db.close()


# =========================================================
# HELPERS
# =========================================================
def normalize_location(country, city, neighborhood):
    country = country.strip().title()
    city = city.strip().title()
    if neighborhood:
        neighborhood = neighborhood.strip().title()
        if neighborhood == "":
            neighborhood = None
    return country, city, neighborhood


def get_or_create_location(db, country, city, neighborhood):
    country, city, neighborhood = normalize_location(country, city, neighborhood)

    query = db.query(Location).filter(
        Location.country == country,
        Location.city == city,
    )

    if neighborhood:
        query = query.filter(Location.neighborhood.ilike(f"%{neighborhood}%"))
    else:
        query = query.filter(Location.neighborhood.is_(None))

    loc = query.first()
    if loc:
        return loc

    # Create new
    loc = Location(country=country, city=city, neighborhood=neighborhood)
    db.add(loc)
    db.flush()
    return loc


# =========================================================
# SEED EXAMPLE REPORTS (first run only)
# =========================================================
def seed_example_reports():
    with get_db() as db:
        if db.query(SafetyReport).count() > 0:
            return

        examples = [
            {
                "country": "Spain", "city": "Barcelona", "neighborhood": "El Raval",
                "score": 2,
                "title": "Felt uneasy walking at night",
                "body": "Lots of catcalling around 10–11pm. Stick to main streets.",
                "tags": "harassment,night_transit",
                "initials": "K.A."
            },
            {
                "country": "Japan", "city": "Tokyo", "neighborhood": "Shinjuku",
                "score": 5,
                "title": "Extremely safe even late at night",
                "body": "Walked home alone at 1am, zero issues. Very well lit.",
                "tags": "night_transit,other",
                "initials": "S.M."
            },
            {
                "country": "Mexico", "city": "Mexico City", "neighborhood": "Condesa",
                "score": 4,
                "title": "Generally safe but watch for scams",
                "body": "Felt fine walking daytime. Some taxi scams reported.",
                "tags": "scams,other",
                "initials": "L.T."
            }
        ]

        for e in examples:
            loc = get_or_create_location(db, e["country"], e["city"], e["neighborhood"])
            db.add(SafetyReport(
                location_id=loc.id,
                safety_score=e["score"],
                title=e["title"],
                body=e["body"],
                tags=e["tags"],
                author_initials=e["initials"],
            ))
    print("Seeded example reports.")


seed_example_reports()


# =========================================================
# UI CONFIG
# =========================================================
st.set_page_config(page_title="SoloSafe", layout="wide")
st.title("🚨 SoloSafe — Community Safety for Solo Women Travelers")


###############################################
# DASHBOARD TAB — SUMMARY + ANALYTICS
###############################################
tab_dashboard, tab_search, tab_add = st.tabs(["📊 Dashboard", "🔍 Search", "➕ Add Report"])


# =========================================================
# DASHBOARD TAB
# =========================================================
with tab_dashboard:
    st.subheader("Global Safety Overview")

    with get_db() as db:
        reports = db.query(SafetyReport).join(Location).all()

        if reports:
            avg_score = sum(r.safety_score for r in reports) / len(reports)
            st.metric("Global Avg Safety Score", f"{avg_score:.2f} / 5")

            # ---- TAG FREQUENCY ----
            tag_counts = {}
            for r in reports:
                if r.tags:
                    for t in r.tags.split(","):
                        t = t.strip()
                        tag_counts[t] = tag_counts.get(t, 0) + 1

            if tag_counts:
                st.write("### Most Common Safety Concerns")
                tag_chart = alt.Chart(
                    {"values": [{"tag": k, "count": v} for k, v in tag_counts.items()]}
                ).mark_bar().encode(
                    x="tag:N",
                    y="count:Q",
                    color="tag:N"
                )
                st.altair_chart(tag_chart, use_container_width=True)

            # ---- WORST LOCATIONS ----
            st.write("### Highest Risk Locations (Lowest Avg Scores)")
            loc_scores = {}
            for r in reports:
                loc = f"{r.location.city}, {r.location.country}"
                loc_scores.setdefault(loc, []).append(r.safety_score)

            sorted_risk = sorted(
                [(loc, sum(scores)/len(scores)) for loc, scores in loc_scores.items()],
                key=lambda x: x[1]
            )[:5]

            st.table({"Location": [x[0] for x in sorted_risk],
                      "Avg Score": [round(x[1], 2) for x in sorted_risk]})
        else:
            st.info("No reports available yet.")


###############################################
# SEARCH TAB
###############################################
with tab_search:
    st.subheader("Search Safety Reports")

    col1, col2 = st.columns(2)
    country = col1.text_input("Country", placeholder="Spain")
    city = col2.text_input("City", placeholder="Barcelona")
    neighborhood = st.text_input("Neighborhood (optional)", placeholder="Gothic Quarter")

    tags_filter = st.multiselect(
        "Filter by concerns:",
        ["harassment", "pickpocketing", "night_transit", "accommodation",
         "rideshare", "police_response", "scams", "catcalling", "other"]
    )

    page = st.number_input("Page", min_value=1, value=1)

    if st.button("Search", type="primary"):
        if not country or not city:
            st.warning("Country and city are required.")
        else:
            with get_db() as db:
                query = db.query(SafetyReport).join(Location).filter(
                    Location.country.ilike(f"%{country.strip().title()}%"),


1
