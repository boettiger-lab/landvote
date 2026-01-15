import os
import re
import datetime

import ibis
from ibis import _
import altair as alt
import minio
import pandas as pd
import streamlit as st
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from variables import *


# -----------------------------
# Data wrangling utils
# -----------------------------

def get_unique_rows(df):
    # collapse multi-county measures to one row per landvote_id
    unique_votes = (
        df
        .group_by("landvote_id")
        .agg(
            **{c: ibis._[c].first() for c in df.schema().names if c not in ("landvote_id", "county", "party")},
            # if spans multiple counties -> set different name for county
            county=ibis.ifelse(ibis._.county.nunique() > 1, "Multiple Counties", ibis._.county.first()),
             # if counties differ in parties -> assign other label to party
            party=ibis.ifelse(ibis._.party.nunique() > 1, "Mixed", ibis._.party.first()),
        )
    )
    return unique_votes


def get_pass_stats(df, min_year, max_year):
    passed_year = (
        df
        .filter((_.year >= min_year) & (_.year <= max_year))
        .filter(_.status.isin(["Pass", "Pass*"]))
        .count()
        .execute()
    )
    total_year = df.filter((_.year >= min_year) & (_.year <= max_year)).count().execute()
    year_passed = round(passed_year / total_year * 100, 2)

    # compute percentage passed over entire dataset
    passed = df.filter(_.status.isin(["Pass", "Pass*"])).count().execute()
    total = df.count().execute()
    overall_passed = round(passed / total * 100, 2)
    return year_passed, overall_passed


def extract_columns(sql_query):
    # Find all substrings inside double quotes
    columns = list(dict.fromkeys(re.findall(r'"(.*?)"', sql_query)))
    return columns


# -----------------------------
# Chart utils
# -----------------------------

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


# -----------------------------
# Mapping / style utils
# -----------------------------

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
def get_party_landvote_style(min_year, max_year):
    return {
        "layers": [
            {
                "id": "party",
                "source": "landvote",
                "source-layer": "landvote_party",
                "type": "fill",
                "filter": [
                    "all",
                    ["<=", "year", str(max_year)],
                    [">=", "year", str(min_year)],
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


def llm_pmtiles_style(ids, paint, pmtiles):
    source_layer_name = re.sub(r"\W+", "", os.path.splitext(os.path.basename(pmtiles))[0]) #stripping hyphens to get layer name
    ids = [str(x) for x in ids]
    style = {
        "version": 8,
        "sources": {
            "tpl": {
                "type": "vector",
                "url": "pmtiles://" + pmtiles,
                "attribution": "TPL",
            },
        },
        "layers": [
            {
                "id": "tpl",
                "source": "tpl",
                "source-layer": source_layer_name,
                "type": "fill",
                "filter": ["in", ["get", "landvote_id"], ["literal", ids]],
                "paint": paint,
            }
        ],
    }
    return style


@st.cache_resource(show_spinner=False)
def get_con(db_path: str = "duck.db"):
    return ibis.duckdb.connect(db_path, extensions=["spatial"])


# -----------------------------
# Chatbot utils
# -----------------------------

class SQLResponse(BaseModel):
    """Defines the structure for SQL response."""
    sql_query: str = Field(description="The SQL query generated by the assistant.")
    explanation: str = Field(description="A detailed explanation of how the SQL query answers the input question.")


@st.cache_data(show_spinner=False)
def _load_template(path: str = "app/system_prompt.txt") -> str:
    with open(path, "r") as f:
        return f.read()


def make_run_sql(votes, llm, con, template_path: str = "app/system_prompt.txt"):
    """
    Returns a run_sql(query, llm_choice) function that:
    - closes over `con` and the chain
    - uses @st.cache_data exactly like your app.py version
    """

    template = _load_template(template_path)

    prompt_tmpl = ChatPromptTemplate.from_messages([
        ("system", template),
        ("human", "{input}")
    ]).partial(dialect="duckdb", landvote=votes.schema())

    # Ensure tools/structured output is not streaming
    llm = llm.bind(streaming=False)

    structured_llm = llm.with_structured_output(SQLResponse)
    few_shot_structured_llm = prompt_tmpl | structured_llm

    @st.cache_data(show_spinner=False)
    def run_sql(query: str, llm_choice: str):
        output = few_shot_structured_llm.invoke({"input": query})
        sql_query = output.sql_query
        explanation = output.explanation

        if not sql_query:
            return pd.DataFrame({"landvote_id": []}), "", explanation

        result = con.sql(sql_query).distinct().execute()

        if result.empty:
            explanation = "This query did not return any results. Please try again with a different query."
            if "geom" in result.columns:
                return result.drop("geom", axis=1), sql_query, explanation
            return result, sql_query, explanation

        return result, sql_query, explanation

    return run_sql


def handle_llm_query(
    prompt: str,
    llm_choice: str,
    run_sql_fn,
    log_queries: bool,
    logger_fn,
    log_file: str = "landvote_query_log.csv",
    log_bucket: str = "shared-tpl",
):
    """
    Runs the LLM->SQL pipeline, renders Streamlit output, logs the query,
    and returns mapping-relevant outputs.
    """

    not_mapping = False
    unique_ids, llm_cols, llm_bounds = [], [], None

    if not prompt:
        return {
            "llm_output": None,
            "sql_query": "",
            "llm_explanation": "",
            "unique_ids": [],
            "llm_cols": [],
            "llm_bounds": None,
            "not_mapping": True,
        }

    st.chat_message("user").write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Invoking query..."):
            llm_output, sql_query, llm_explanation = run_sql_fn(prompt, llm_choice)

            # Log (keep your exact signature)
            logger_fn(
                log_queries,
                prompt,
                sql_query,
                llm_explanation,
                llm_choice,
                log_file,
                log_bucket,
            )

            # No SQL generated
            if sql_query == "":
                st.success(llm_explanation)
                not_mapping = True

            else:
                # SQL generated but no results
                if llm_output is not None and llm_output.empty:
                    st.warning(llm_explanation, icon="⚠️")
                    st.caption("SQL Query:")
                    st.code(sql_query, language="sql")
                    st.stop()

                # Output without mapping columns
                elif llm_output is not None and ("landvote_id" not in llm_output.columns and "geom" not in llm_output.columns):
                    st.write(llm_output)
                    not_mapping = True

                # Always show explanation + SQL in a popover
                with st.popover("Explanation"):
                    st.write(llm_explanation)
                    st.caption("SQL Query:")
                    st.code(sql_query, language="sql")

            # Extract ids, columns, bounds if present
            if llm_output is not None and ("landvote_id" in llm_output.columns) and (not llm_output.empty):
                unique_ids = list(set(llm_output["landvote_id"].tolist()))
                llm_cols = extract_columns(sql_query)
                llm_bounds = llm_output.total_bounds.tolist()
            else:
                unique_ids, llm_cols, llm_bounds = [], [], None
                not_mapping = True

    return {
        "llm_output": llm_output,
        "sql_query": sql_query,
        "llm_explanation": llm_explanation,
        "unique_ids": unique_ids,
        "llm_cols": llm_cols,
        "llm_bounds": llm_bounds,
        "not_mapping": not_mapping,
    }


# -----------------------------
# Logging utils
# -----------------------------

minio_key = os.getenv("MINIO_KEY")
if minio_key is None:
    minio_key = st.secrets["MINIO_KEY"]

minio_secret = os.getenv("MINIO_SECRET")
if minio_secret is None:
    minio_secret = st.secrets["MINIO_SECRET"]


def minio_logger(consent, query, sql_query, llm_explanation, llm_choice, filename="landvote_query_log.csv", bucket="shared-tpl",
                 key=minio_key, secret=minio_secret,
                 endpoint="minio.carlboettiger.info"):
    mc = minio.Minio(endpoint, key, secret)
    mc.fget_object(bucket, filename, filename)
    log = pd.read_csv(filename)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if consent:
        df = pd.DataFrame({"timestamp": [timestamp], "user_query": [query], "llm_sql": [sql_query], "llm_explanation": [llm_explanation], "llm_choice":[llm_choice]})

    # if user opted out, do not store query
    else:
        df = pd.DataFrame({"timestamp": [timestamp], "user_query": ['USER OPTED OUT'], "llm_sql": [''], "llm_explanation": [''], "llm_choice":['']})

    pd.concat([log,df]).to_csv(filename, index=False, header=True)
    mc.fput_object(bucket, filename, filename, content_type="text/csv")
