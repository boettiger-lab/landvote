import ibis
from ibis import _
import altair as alt
from variables import *

def create_chart(df, y_column, ylab, title, color, chart_type="line"):
    # color encoding - color is a list or single value
    color_encoding = (
        alt.Color(
            "party:N",
            scale=alt.Scale(
                domain=["Democrat", "Republican"],
                range=color,
            ),
        )
        if isinstance(color, list)
        else alt.value(color)
    )

    # Set the mark type based on chart_type
    mark = (
        alt.Chart(df).mark_line(strokeWidth=3)
        if chart_type == "line"
        else alt.Chart(df).mark_bar()
    )

    return (
        mark.encode(
            x=alt.X("year:N", title="Year"),
            y=alt.Y(f"{y_column}:Q", title=ylab),
            color=color_encoding,
        )
        .properties(title=title)
    )


# percentage of measures passing, per party
def get_party_df(votes):
    party_df = (
        votes
        .filter(_.party.isin(["Democrat", "Republican"]))
        .group_by(_.year, _.party)
        .aggregate(
            pass_fraction=(
                (_.status.isin(["Pass", "Pass*"]))
                .cast("int")
                .mean()
            )
        )
        .order_by("year")
        .execute()
    )
    return party_df


# cumulative funding over time
def funding_chart(votes):
    return (
        votes
        .filter(_.status.isin(["Pass", "Pass*"]))
        .group_by("year")
        .aggregate(
            total_funding=_.conservation_funds_approved.sum()
        )
        .order_by("year")
        .mutate(
            cumulative_funding=_.total_funding.cumsum() / 1e9
        )
        .to_pandas()
    )


def party_style(year):
    recent_election_year = year - year % 4

    return {
        "layers": [
            {
                "id": "Party",
                "source": "Political Parties",
                "source-layer": "county_political_parties_19882024",
                "type": "fill",
                "filter": [
                    "==",
                    ["get", "year"],
                    str(recent_election_year),
                ],
                "paint": {
                    "fill-color": {
                        "property": "party",
                        "type": "categorical",
                        "stops": [
                            ["Democrat", colors["dem_blue"]],
                            ["Republican", colors["rep_red"]],
                        ],
                    }
                },
            }
        ]
    }


    
# pmtiles style for status
def get_status_style(jurisdiction, min_year, max_year):
    if jurisdiction == "State":
        paint_type = paint_fill
        layer_type = "fill"
    else:
        paint_type = paint_extrusion
        layer_type = "fill-extrusion"

    return {
        "layers": [
            {
                "id": jurisdiction,
                "source": jurisdiction,
                "source-layer": "landvote_party",
                "type": layer_type,
                "filter": [
                    "all",
                    ["<=", "year", str(max_year)],
                    [">=", "year", str(min_year)],
                    ["==", "jurisdiction", jurisdiction],
                ],
                "paint": paint_type,
            }
        ]
    }

# pmtiles style for party
def get_party_landvote_style(jurisdiction, min_year, max_year):
    return {
        "layers": [
            {
                "id": jurisdiction,
                "source": jurisdiction,
                "source-layer": "landvote_party",
                "type": "fill",
                "filter": [
                    "all",
                    ["<=", "year", str(max_year)],
                    [">=", "year", str(min_year)],
                    ["==", "jurisdiction", jurisdiction],
                ],
                "paint": {
                    "fill-color": {
                        "property": "party",
                        "type": "categorical",
                        "stops": [
                            ["Democrat", colors["dem_blue"]],
                            ["Republican", colors["rep_red"]],
                        ],
                    }
                },
            }
        ]
    }


def party_chart(df):
    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("year:O", title="Year"),
            y=alt.Y(
                "pass_fraction:Q",
                title="% of measures passed",
                axis=alt.Axis(format="%"),
            ),
            color=alt.Color(
                "party:N",
                scale=alt.Scale(
                    domain=["Democrat", "Republican"],
                    range=[colors["dem_blue"], colors["rep_red"]],
                ),
                legend=alt.Legend(title="Party"),
            ),
            tooltip=[
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip("party:N", title="Party"),
                alt.Tooltip(
                    "pass_fraction:Q",
                    title="% passed",
                    format=".1%",
                ),
            ],
        )
        .properties(
            title="Percent of Measures Passed per Year by Political Party"
        )
    )

    return chart
