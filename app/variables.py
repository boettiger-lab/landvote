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
