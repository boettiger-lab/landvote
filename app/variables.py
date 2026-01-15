votes_pmtiles = "https://minio.carlboettiger.info/public-tpl/landvote/landvote_party.pmtiles"
votes_parquet = "https://minio.carlboettiger.info/public-tpl/landvote/landvote_party.parquet"

colors = {
    "dark_orange": "#ab5601",
    "light_orange": "#f3d3b1",
    "grey": "#d3d3d3",
    "light_green": "#c3dbc3",
    "dark_green": "#417d41",
    "dem_blue": "#1b46c2",
    "rep_red": "#E81B23",
}

# color fill for measure status
paint_fill = {
    "fill-color": [
        "case",
        ["==", ["get", "status"], "Pass"],
        [
            "interpolate",
            ["linear"],
            [
                "to-number",
                ["slice", ["get", "percent_yes"], 0, -1],  # convert 'yes' string to number
            ],
            50,
            colors["grey"],
            55,
            colors["light_green"],
            100,
            colors["dark_green"],  # higher yes % -> darker green
        ],
        ["==", ["get", "status"], "Fail"],
        [
            "interpolate",
            ["linear"],
            [
                "to-number",
                ["slice", ["get", "percent_yes"], 0, -1],
            ],
            0,
            colors["dark_orange"],
            50,
            colors["light_orange"],  # lower yes % -> darker orange
            67,
            colors["grey"],  # 67 is max in our data
        ],
        colors["grey"],
    ]
}

# for status, height depends on funding
paint_extrusion = {
    "fill-extrusion-color": paint_fill["fill-color"],
    "fill-extrusion-height": [
        "*",
        [
            "ln",
            ["+", 1, ["to-number", ["get", "conservation_funds_approved"]]],
        ],
        1,
    ],
}

justice40 = "https://data.source.coop/cboettig/justice40/disadvantaged-communities.pmtiles"

justice40_fill = {
    "property": "Disadvan",
    "type": "categorical",
    "stops": [
        [0, "rgba(255, 255, 255, 0)"],
        [1, "rgba(0, 0, 139, 1)"],
    ],
}

justice40_style = {
    "version": 8,
    "sources": {
        "source1": {
            "type": "vector",
            "url": "pmtiles://" + justice40,
            "attribution": "Justice40",
        }
    },
    "layers": [
        {
            "id": "Justice40",
            "source": "source1",
            "source-layer": "DisadvantagedCommunitiesCEJST",
            "type": "fill",
            "paint": {
                "fill-color": justice40_fill,
                "fill-opacity": 0.6,
            },
        }
    ],
}

sv_pmtiles = "https://data.source.coop/cboettig/social-vulnerability/svi2020_us_county.pmtiles"

sv_style = {
    "layers": [
        {
            "id": "SVI",
            "source": "Social Vulnerability Index",
            "source-layer": "SVI2020_US_county",
            "type": "fill",
            "paint": {
                "fill-color": [
                    "interpolate",
                    ["linear"],
                    ["get", "RPL_THEMES"],
                    0,
                    "#FFE6EE",
                    1,
                    "#850101",
                ]
            },
        }
    ]
}

party_pmtiles = (
    "https://minio.carlboettiger.info/public-election/"
    "county/county_political_parties_1988-2024.pmtiles"
)


from langchain_openai import ChatOpenAI
import streamlit as st
from langchain_openai.chat_models.base import BaseChatOpenAI

## dockerized streamlit app wants to read from os.getenv(), otherwise use st.secrets
import os
api_key = os.getenv("NRP_API_KEY")
if api_key is None:
    api_key = st.secrets["NRP_API_KEY"]

openrouter_api = os.getenv("OPENROUTER_API_KEY")
if openrouter_api is None:
    openrouter_api = st.secrets["OPENROUTER_API_KEY"]

openrouter_endpoint="https://openrouter.ai/api/v1"
nrp_endpoint="https://ellm.nrp-nautilus.io/v1"

# don't use a provider that collects data
data_policy = {
    "provider": {
        "data_collection": "deny"
    }
}

llm_options = {
    "devstral-2512": ChatOpenAI(
        model="mistralai/devstral-2512:free",
        api_key=openrouter_api,
        base_url=openrouter_endpoint,
        temperature=0,
        extra_body=data_policy
    ),

    "trinity-mini": ChatOpenAI(
        model="arcee-ai/trinity-mini:free",
        api_key=openrouter_api,
        base_url=openrouter_endpoint,
        temperature=0,
        extra_body=data_policy
    ),

    "nemotron-nano-9b-v2": ChatOpenAI(
        model="nvidia/nemotron-nano-9b-v2:free",
        api_key=openrouter_api,
        base_url=openrouter_endpoint,
        temperature=0,
        extra_body=data_policy
    ),
    
    "gemma-3-27b-it": ChatOpenAI(
        model="gemma3",
        api_key=api_key,
        base_url=nrp_endpoint,
        temperature=0
    ),

}