import os

import altair as alt
import ibis
import leafmap.maplibregl as leafmap
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from ibis import _

from utils import *


st.set_page_config(
    layout="wide",
    page_title="TPL LandVote",
    page_icon=":globe:",
)

"""
# LandVote Prototype

An experimental platform for visualizing data on ballot measures for conservation, based on data from
<https://landvote.org/> curated by the Trust for Public Land.
"""

st.caption(
    "We visualize each voting jurisdiction with green if a conservation measure passed and orange if it failed. "
    "The intensity of green or orange reflects the level of support or opposition, with darker green representing "
    "stronger support for passed measures and darker orange representing lower support for failed measures."
)

"ℹ️ Tip: Use the slider to change the year and hover over shaded areas for measure details."



min_year, max_year = st.slider("Select a range", 1988, 2024, (2020, 2024))

con = ibis.duckdb.connect("duck.db", extensions=["spatial"])
current_tables = con.list_tables()

if "mydata" not in set(current_tables):
    tbl = (
        con.read_parquet(votes_parquet)
        .cast({"geom": "geometry"})
    )
    con.create_table("mydata", tbl)

votes = con.table("mydata")

with st.sidebar:
    color_choice = st.radio("Color by:", ["Measure status", "Political Party"])
    st.divider()

    "Data Layers:"
    party_toggle = st.toggle("Political Parties")
    social_toggle = st.toggle("Social Vulnerability Index")
    justice_toggle = st.toggle("Climate and Economic Justic")


m = leafmap.Map(
    style="positron",
    center=(-100, 40),
    zoom=3,
    use_message_queue=True,
)

if social_toggle:
    m.add_pmtiles(
        sv_pmtiles,
        style=sv_style,
        visible=True,
        opacity=0.3,
        tooltip=True,
    )

if party_toggle:
    m.add_pmtiles(
        party_pmtiles,
        style=party_style(max_year),
        visible=True,
        opacity=0.3,
        tooltip=True,
    )

if justice_toggle:
    m.add_pmtiles(
        justice40,
        style=justice40_style,
        visible=True,
        name="Justice40",
        opacity=0.3,
        tooltip=True,
    )


# compute percentage passed in given year
passed_year = (
    votes
    .filter((_.year>= min_year) & (_.year<= max_year))
    .filter(_.status.isin(["Pass", "Pass*"]))
    .count()
    .execute()
)
total_year = votes.filter((_.year>= min_year) & (_.year<= max_year)).count().execute()
year_passed = round(passed_year / total_year * 100, 2)
f"{year_passed}% Measures Passed between {min_year} and {max_year}"

# compute percentage passed over entire dataset
passed = votes.filter(_.status.isin(["Pass", "Pass*"])).count().execute()
total = votes.count().execute()
overall_passed = round(passed / total * 100, 2)
f"{overall_passed}% Measures Passed from 1988 - 2024 \n"


if color_choice == "Measure status":
    for j, o in zip(
        ["State", "County", "Municipal", "Special District"],
        [0.8, 1, 1, 1],
    ):
        m.add_pmtiles(
            votes_pmtiles,
            style=get_status_style(j,min_year,max_year),
            visible=True,
            opacity=o,
            tooltip=True,
        )

elif color_choice == "Political Party":
    for j, o in zip(
        ["State", "County", "Municipal", "Special District"],
        [0.8, 1, 1, 1],
    ):
        m.add_pmtiles(
            votes_pmtiles,
            style=get_party_landvote_style(j,min_year,max_year),
            visible=True,
            opacity=o,
            tooltip=True,
        )

m.add_layer_control()
m.to_streamlit()

party_df = get_party_df(votes)
st.altair_chart(party_chart(party_df), use_container_width=True)

df_funding = funding_chart(votes)
st.altair_chart(
    create_chart(
        df_funding,
        "cumulative_funding",
        "Billions of Dollars",
        "Cumulative Funding",
        colors["dark_green"],
        chart_type="bar",
    ),
    use_container_width=True,
)

st.divider()
st.caption(
    "***The height of county and city jurisdictions represents the amount of funding proposed by the measure."
)

st.caption(
    "***Political affiliation is determined by the party that received the majority vote in the most recent "
    "presidential election for each jurisdiction. For counties and states, this reflects the majority vote in "
    "that area. For cities, affiliation is based on the party of the county in which the city is located."
)

with open("app/footer.md", "r") as file:
    footer = file.read()

st.markdown(footer)
