import ibis
from ibis import _

import streamlit as st
import altair as alt
import os
import pandas as pd
import matplotlib.pyplot as plt
# from pandasai.llm.openai import OpenAI
# from pandasai import Agent
# from pandasai.responses.streamlit_response import StreamlitResponse
import leafmap.maplibregl as leafmap

st.set_page_config(layout="wide",
                   page_title="TPL LandVote",
                   page_icon=":globe:")

'''
# LandVote Prototype

An experimental platform for visualizing data on ballot measures for conservation, based on data from <https://landvote.org/> curated by the Trust for Public Land. 
'''

st.caption("We visualize each voting jurisdiction with green if a conservation measure passed and orange if it failed. The intensity of green or orange reflects the level of support or opposition, with darker green representing stronger support for passed measures and darker orange representing lower support for failed measures. ")



"ℹ️ Tip: Use the slider to change the year and hover over shaded areas for measure details."



COLORS = {
    "dark_orange": "#ab5601",
    "light_orange": "#f3d3b1",
    "grey": "#d3d3d3",
    "light_green": "#c3dbc3",
    "dark_green": "#417d41",
    "dem_blue": "#1b46c2",
    "rep_red": "#E81B23"
}


## chatbot
# llm = OpenAI(api_token=st.secrets["OPENAI_API_KEY"])
# df1 = pd.read_csv("data.csv")
# agent = Agent([df1], config={"verbose": True, "response_parser": StreamlitResponse, "llm": llm})

year = st.slider("Select a year", 1988, 2024, 2022, 1)

 

votes_pmtiles = "https://huggingface.co/datasets/boettiger-lab/landvote/resolve/main/votes.pmtiles"
votes_parquet = "https://huggingface.co/datasets/boettiger-lab/landvote/resolve/main/votes.parquet"

# get parquet data for charts
con = ibis.duckdb.connect(extensions=["spatial"])
votes = (con
         .read_parquet(votes_parquet)
         .cast({"geometry": "geometry"})
        )

def create_chart(df, y_column, ylab, title, color, chart_type="line"):
    # color encoding - color is a list or single value 
    color_encoding = (
        alt.Color('party:N', scale=alt.Scale(domain=["DEMOCRAT", "REPUBLICAN"], range=color))
        if isinstance(color, list) else alt.value(color)
    )
    
    # Set the mark type based on chart_type
    mark = alt.Chart(df).mark_line(strokeWidth=3) if chart_type == "line" else alt.Chart(df).mark_bar()

    return mark.encode(
        x=alt.X('year:N', title='Year'),
        y=alt.Y(f'{y_column}:Q', title=ylab),
        color=color_encoding  
    ).properties(
        title=title
    )

# percentage of measures passing, per party
def get_passes(votes):
    return (votes
        # .filter(_.year >= 2000)
        .group_by("year", "party")
        .aggregate(total=_.count(), passes=_.Status.isin(["Pass", "Pass*"]).sum())
        .mutate(percent_passed=(_.passes / _.total).round(2),
                color=ibis.case().when(_.party == "DEMOCRAT", COLORS["dem_blue"]).else_(COLORS["rep_red"]).end())
        .to_pandas())


# cumulative funding over time 
def funding_chart(votes):
   return (votes
           # .filter(_.year >= 2000)
          .mutate(amount=_.amount.replace('$', '')
                  .replace(',', '')
                  .cast('float64'))
          .filter(_.Status.isin(["Pass", "Pass*"]))
          .group_by("year")
          .aggregate(total_funding=_.amount.sum())
          .order_by("year")
          .mutate(cumulative_funding=_.total_funding.cumsum()/1e9)
          .to_pandas()
         )
    

#color fill for measure status
paint_fill = {
    "fill-color": [
        "case",
        ["==", ["get", "Status"], "Pass"],
        [
            "interpolate", ["linear"], [
                "to-number", ["slice", ["get", "yes"], 0, -1]  # convert 'yes' string to number
            ],
            50, COLORS["grey"],
            55, COLORS["light_green"],
            100, COLORS["dark_green"] # higher yes % -> darker green
        ],
        ["==", ["get", "Status"], "Fail"],
        [
            "interpolate", ["linear"], [
                "to-number", ["slice", ["get", "yes"], 0, -1]
            ],
            0, COLORS["dark_orange"],
            50, COLORS["light_orange"], # lower yes % -> darker orange
            67, COLORS["grey"] # 67 is max in our data 
        ],
        COLORS["grey"]
    ]
}

# for status, height depends on funding 
paint_extrusion = {
    "fill-extrusion-color": paint_fill["fill-color"],
    "fill-extrusion-height": ["*", ["to-number", ["get", "log_amount"]], 5000]
}



# pmtiles style for status 
def get_style_status(jurisdiction):
    if jurisdiction == "State":
        name = "state"
        label = "States"
        paint_type = paint_fill
        layer_type = "fill"
    elif jurisdiction == "County":
        name = "county"
        label = "Counties"
        paint_type = paint_extrusion
        layer_type = "fill-extrusion"
    else:  # Municipal
        name = "municipal"
        label = "Cities"
        paint_type = paint_extrusion
        layer_type = "fill-extrusion"

    return {
        "layers": [
            {
                "id": label,
                "source": name,
                "source-layer": name,
                "type": layer_type,
                "filter": ["==", ["get", "year"], year],
                "paint": paint_type
            }
        ]
    }


# pmtiles style for party 
def get_style_party(jurisdiction):
    if jurisdiction == "State":
        name = "state"
        label = "States"
    elif jurisdiction == "County":
        name = "county"
        label = "Counties"
    else:  # Municipal
        name = "municipal"
        label = "Cities"

    # Return style dictionary for political party
    return {
        "layers": [
            {
                "id": label, 
                "source": name,
                "source-layer": name,
                "type": "fill",
                "filter": [
                    "==", ["get", "year"], year
                ],
                "paint": {
                    "fill-color": {
                        "property": "party",
                        "type": "categorical",
                        "stops": [
                            ["DEMOCRAT", COLORS["dem_blue"]],
                            ["REPUBLICAN", COLORS["rep_red"]]
                        ]
                    }
                }
            }
        ]
    }



justice40 = "https://data.source.coop/cboettig/justice40/disadvantaged-communities.pmtiles"
justice40_fill = {
        'property': 'Disadvan',
        'type': 'categorical',
        'stops': [
            [0, "rgba(255, 255, 255, 0)"],
            [1, "rgba(0, 0, 139, 1)"]]}
justice40_style = {
    "version": 8,
    "sources": {
        "source1": {
            "type": "vector",
            "url": "pmtiles://" + justice40,
            "attribution": "Justice40"}
    },
    "layers": [{
            "id": "Justice40",
            "source": "source1",
            "source-layer": "DisadvantagedCommunitiesCEJST",
            "type": "fill",
            "paint": {"fill-color": justice40_fill, "fill-opacity": 0.6}}]
}





sv_pmtiles = "https://data.source.coop/cboettig/social-vulnerability/svi2020_us_county.pmtiles"
sv_style =  {
        "layers": [
            {
                "id": "SVI",
                "source": "Social Vulnerability Index",
                "source-layer": "SVI2020_US_county",
                "type": "fill",
                "paint": {
                    "fill-color": 
                        ["interpolate", ["linear"], ["get", "RPL_THEMES"],
                0, "#FFE6EE",
                1, "#850101"] 
                        
                    }
                }
        ]
}

party_pmtiles = "https://huggingface.co/datasets/boettiger-lab/landvote/resolve/main/party_polygons_all.pmtiles"

recent_election_year = year - year%4 
party_style =  {
        "layers": [
            {
                "id": "Party",
                "source": "Political Parties",
                "source-layer": "county",
                "type": "fill",
                "filter": [
                    "==", ["get", "year"], recent_election_year
                ],
                "paint": {
                    "fill-color": {
                        "property": "party",
                        "type": "categorical",
                        "stops": [
                            ["DEMOCRAT", COLORS["dem_blue"]],
                            ["REPUBLICAN", COLORS["rep_red"]]
                        ]
                    }
                }
            }
        ]
    }


with st.sidebar:
    color_choice = st.radio("Color by:", ["Measure Status", "Political Party"])
    st.divider()
    
    "Data Layers:"
    # with st.expander("Social Justice"): 

    social_toggle = st.toggle("Social Vulnerability Index")
    justice_toggle = st.toggle("Climate and Economic Justice")
    party_toggle = st.toggle("Political Parties")

    # st.divider()

    # '''
    # ## Data Assistant (experimental)

    # Ask questions about the LandVote data, like:

    # - What are the top states for approved conservation funds?
    # - Plot the total funds spent in conservation each year.
    # - What city has approved the most funds in a single measure? What was the description of that vote?
    # - Which state has had largest number measures fail? What is that as a fraction of it's total measures?
    # '''
    
    # prompt = st.chat_input("Ask about the data")
    # if prompt:
    #     with st.spinner():
    #         resp = agent.chat(prompt)
    #         if os.path.isfile('exports/charts/temp_chart.png'):
    #             im = plt.imread('exports/charts/temp_chart.png')
    #             st.image(im)
    #             os.remove('exports/charts/temp_chart.png')
    #         st.write(resp)

              
m = leafmap.Map(style="positron", center=(-100, 40), zoom=3, use_message_queue=True)


if social_toggle:
    m.add_pmtiles(sv_pmtiles, style = sv_style ,visible=True, opacity=0.3, tooltip=True)

if party_toggle:
    m.add_pmtiles(party_pmtiles, style = party_style ,visible=True, opacity=0.3, tooltip=True)

if justice_toggle:
    m.add_pmtiles(justice40, style=justice40_style, visible=True, name="Justice40",  opacity=0.3, tooltip=True)



#compute percentage passed in given year 
passed_year = votes.filter(_.year == year).filter(_.Status.isin(["Pass","Pass*"])).count().execute()
total_year= votes.filter(_.year == year).count().execute()
year_passed = round(passed_year/total_year*100,2)
f"{year_passed}% Measures Passed in {year}"  

#compute percentage passed over entire dataset
passed = votes.filter(_.Status.isin(["Pass","Pass*"])).count().execute()
total = votes.count().execute()
overall_passed = round(passed/total*100,2)
f"{overall_passed}% Measures Passed from 1988 - 2024 \n"  



if color_choice == "Measure Status":
    m.add_pmtiles(votes_pmtiles, style=get_style_status("State"), visible=True, opacity=0.8, tooltip=True)
    m.add_pmtiles(votes_pmtiles, style=get_style_status("County"), visible=True, opacity=1.0, tooltip=True)
    m.add_pmtiles(votes_pmtiles, style=get_style_status("Municipal"), visible=True, opacity=1.0, tooltip=True)

elif color_choice == "Political Party":
    m.add_pmtiles(votes_pmtiles, style=get_style_party("State"), visible=True, opacity=0.8, tooltip=True)
    m.add_pmtiles(votes_pmtiles, style=get_style_party("County"), visible=True, opacity=1.0, tooltip=True)
    m.add_pmtiles(votes_pmtiles, style=get_style_party("Municipal"), visible=True, opacity=1.0, tooltip=True)



m.add_layer_control()
m.to_streamlit()


# display charts
df_passes = get_passes(votes)
st.altair_chart(create_chart(df_passes, "percent_passed", "Percent Passed","% of Measures Passed", [COLORS["dem_blue"], COLORS["rep_red"]], chart_type="line"), use_container_width=True)

df_funding = funding_chart(votes)
st.altair_chart(create_chart(df_funding, "cumulative_funding", "Billions of Dollars", "Cumulative Funding", COLORS["dark_green"], chart_type="bar"), use_container_width=True)

st.divider()
footer = st.container()


st.caption("***The height of county and city jurisdictions represents the amount of funding proposed by the measure.")


st.caption("***Political affiliation is determined by the party that received the majority vote in the most recent presidential election for each jurisdiction. For counties and states, this reflects the majority vote in that area. For cities, affiliation is based on the party of the county in which the city is located.")


'''
# Credits
Authors: Cassie Buhler & Carl Boettiger, UC Berkeley License: BSD-2-clause

## Data sources

- TPL LandVote Database by Trust for Public Land. Data: https://tpl.quickbase.com/db/bbqna2qct?a=dbpage&pageID=8. Citation: The Trust for Public Land, LandVote®, 2024, www.landvote.org., License: Public Domain

- Climate and Economic Justice Screening Tool, US Council on Environmental Quality, Justice40, Data: https://beta.source.coop/repositories/cboettig/justice40/description/. License: Public Domain

- CDC 2020 Social Vulnerability Index by US Census Track. Data: https://source.coop/repositories/cboettig/social-vulnerability/description. License: Public Domain

- County Presidential Election Returns 2000-2020 by MIT Election Data and Science Lab. Citation: https://doi.org/10.7910/DVN/VOQCHQ. License: Public Domain.

- U.S. President 1976–2020 by MIT Election Data and Science Lab. Citation: https://doi.org/10.7910/DVN/42MVDX. License: Public Domain.



'''
