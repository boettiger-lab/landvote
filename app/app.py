import os
import openai
import altair as alt
import leafmap.maplibregl as leafmap
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from utils import *
import ibis
from ibis import _

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

if "landvote" not in set(current_tables):
    tbl = (
        con.read_parquet(votes_parquet)
        .cast({"geom": "geometry"})
    )
    tbl = get_unique_rows(tbl)  # drop multi-county measures with non-unanimous party labels
    con.create_table("landvote", tbl)
    
votes = con.table("landvote")

with st.sidebar:
    color_choice = st.radio("Color by:", ["Measure status", "Political Party"])
    st.divider()

    "Data Layers:"
    party_toggle = st.toggle("Political Parties")
    social_toggle = st.toggle("Social Vulnerability Index")
    justice_toggle = st.toggle("Climate and Economic Justic")

##### Chatbot stuff 
chatbot_container = st.container()
with chatbot_container:
    llm_left_col, llm_right_col = st.columns([5,1], vertical_alignment = "bottom")
    with llm_left_col:
        with st.popover("💬 Example Queries"):
            '''
            Mapping queries: 
            - Show me Republican-voting counties where conservation measures passed
            - Show measures that failed narrowly (between 45% and 50% yes)
            - Show me conservation measures that approved over $500 million
            '''

            '''
            Exploratory data queries:
            - Which year had the most conservation funds approved?
            - Which state approved the largest total conservation funding?
            - How many measures passed by jurisdiction type?
            - Which counties voted on conservation measures most frequently?
            - What is the median funding amount for passed measures?
            - How often do bond measures pass compared to other finance mechanisms?
            '''
            
            st.info('If the map appears blank, queried data may be too small to see at the default zoom level. Check the table below the map, as query results will also be displayed there.', icon="ℹ️")
    
    with llm_right_col:
        llm_choice = st.selectbox("Select LLM:", llm_options, key = "llm", help = "Select which model to use.")   
        llm = llm_options[llm_choice]
        
run_sql = make_run_sql(votes, llm, con)

with chatbot_container:
    with llm_left_col:
        example_query = "👋 Input query here"
        prompt = st.chat_input(example_query, key="chain", max_chars=300)
    _,log_query_col, _ = st.columns([.001, 5,1], vertical_alignment = "top")
    with log_query_col:
        log_queries = st.checkbox("Save query", value = True, help = "Saving your queries helps improve this tool and guide conservation efforts. Your data is stored in a private location. For more details, see 'Why save your queries?' at the bottom of this page.")
        
# new container for output so it doesn't mess with the alignment of llm options 
with st.container():
    if prompt:
        result = handle_llm_query(
            prompt=prompt,
            llm_choice=llm_choice,
            run_sql_fn=run_sql,            # your cached function: run_sql(prompt, llm_choice)
            log_queries=log_queries,
            logger_fn=minio_logger,
            log_file="landvote_query_log.csv",
            log_bucket="shared-tpl",
        )

        llm_output = result["llm_output"]
        sql_query = result["sql_query"]
        llm_explanation = result["llm_explanation"]
        unique_ids = result["unique_ids"]
        llm_cols = result["llm_cols"]
        llm_bounds = result["llm_bounds"]
        not_mapping = result["not_mapping"]

##### end of chatbot code 


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


# define PMTiles style dict (if we didn't already do so using the chatbot)
if 'llm_output' in locals():
    if not_mapping == False:
        # filter to ids from result 
        style = llm_pmtiles_style(unique_ids, paint_fill, votes_pmtiles)
        m.add_pmtiles(
            votes_pmtiles,
            style=style,
            visible=True,
            opacity=1.0,
            tooltip=True,
            name="LLM Query Results",
        )
    
        # Zoom to result bounds if present
        if "llm_bounds" in locals() and llm_bounds:
            m.fit_bounds(llm_bounds)
        m.to_streamlit()
        with st.expander("🔍 View/download data"): # adding data table  
            if ('geom' in llm_output.columns) and (not llm_output.empty):
                llm_output = llm_output.drop('geom',axis = 1)
            st.dataframe(llm_output, use_container_width = True)

else: # if we didn't use chatbot 
        
    # compute percentage passed in given year
    year_passed, overall_passed=get_pass_stats(votes, min_year, max_year)
    f"{year_passed}% Measures Passed between {min_year} and {max_year}"
    f"{overall_passed}% Measures Passed from 1988 - 2024 \n"

    if color_choice == "Measure status":
        # 4 styles / 4 layers (jurisdiction-specific)
        for j, o in zip(
            ["State", "County", "Municipal", "Special District"],
            [0.8, 1, 1, 1],
        ):
            m.add_pmtiles(
                votes_pmtiles,
                style=get_status_style(j, min_year, max_year),
                visible=True,
                opacity=o,
                tooltip=True,
                name=j,  # shows as separate toggles in layer control
            )
        m.to_streamlit()


    elif color_choice == "Political Party":
        # 1 style / 1 layer
        style = get_party_landvote_style(min_year, max_year)

        m.add_pmtiles(
            votes_pmtiles,
            style=style,
            visible=True,
            opacity=1.0,
            tooltip=True,
            name="Political Party",
        )

        m.to_streamlit()

    with st.expander("🔍 View/download data"): # adding data table  
        group_cols = ['landvote_id','year','state','county','municipal','jurisdiction']
        gdf_grouped = (votes.head(100).execute().groupby(group_cols)
            .agg({col: ('sum' if col in ['total_funds_at_stake','total_funds_approved',
                'conservation_funds_at_stake','conservation_funds_approved'] else 'first') 
                  for col in votes.columns if col not in group_cols})).reset_index()
        cols = ['landvote_id','year','state','county','municipal','jurisdiction',
                'status', 'percent_yes', 'percent_no', 'date',
                'total_funds_at_stake','total_funds_approved',
                'conservation_funds_at_stake','conservation_funds_approved',
                'finance_mechanism', 'other_comment','purpose',
                'description', 'notes', 'voted_acq_measure', 'party']

        st.dataframe(gdf_grouped[cols], use_container_width = True)  

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
