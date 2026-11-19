from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, ctx


# One row = one order-product line. Order ID is absent: do not count orders.
BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DATA_PATH = BASE_DIR / "data" / "superstore_orders.csv"
if not DATA_PATH.exists():  # notebook is one folder above the standalone project
    DATA_PATH = BASE_DIR / "superstore_app" / "data" / "superstore_orders.csv"
df = pd.read_csv(DATA_PATH, parse_dates=["Order Date"])
required = ["Row ID", "Order Date", "Region", "Category", "Sales", "Profit"]
assert df[required].notna().all().all(), "Missing classroom data values"
assert df["Row ID"].is_unique, "Expected one unique Row ID per order line"
assert len(df) == 51290, "Use the supplied, unchanged classroom CSV"
df = df.assign(Year=df["Order Date"].dt.year)  # original CSV is never modified
REGIONS = sorted(df["Region"].unique())
YEARS = sorted(int(y) for y in df["Year"].unique())
CATEGORIES = sorted(df["Category"].unique())

CHART_FONT = dict(family="Times, serif", size=14)

def empty_figure(title):
    fig = go.Figure()
    fig.add_annotation(text="No matching rows. Choose a region/category.", showarrow=False)
    fig.update_layout(title=title, template="plotly_white", font=CHART_FONT)
    return fig


ASSETS_DIR = DATA_PATH.parent.parent / "assets"
app = Dash(__name__, assets_folder=str(ASSETS_DIR))
server = app.server  # deployment target for gunicorn app:server
app.title = "Superstore Explorer"


# TODO: choose a business question, title, colors, and layout for your audience.
app.layout = html.Main([
    html.H1("Superstore Explorer"),
    html.P("Question: How do category sales and profits and monthly trends vary by region and year?"),
    html.Div([
        html.Div([
            html.Label("Regions (clear all = no rows)", htmlFor="regions"),
            dcc.Dropdown(id="regions", options=REGIONS, value=REGIONS,
                         multi=True, closeOnSelect=False),
        ], className="control"),
        html.Div([
            html.Label("Year", htmlFor="year"),
            dcc.Slider(id="year", min=min(YEARS), max=max(YEARS), step=1,
                       marks={y: str(y) for y in YEARS}, value=max(YEARS),
                       updatemode="mouseup"),
        ], className="control"),
    ], className="controls"),
    html.Button("Reset category selection", id="reset", n_clicks=0),
    html.P("Click a category bar to filter the monthly charts and summary. "
           "Changing a control also resets the category selection."),
    html.Div(id="summary", className="summary", role="status"),
    # Sales row
    html.Div([
        html.Div([
            dcc.Graph(id="category-bar"),
            html.Div([
                html.Label("Sort bars by", htmlFor="sort"),
                dcc.RadioItems(id="sort",
                               options=[{"label": "Alphabetical", "value": "alpha"},
                                        {"label": "High → Low", "value": "desc"},
                                        {"label": "Low → High", "value": "asc"}],
                               value="alpha", inline=True),
            ], className="control", style={"borderRadius": "0"}),
        ]),
        dcc.Graph(id="monthly-line"),
    ], className="charts"),
    # Profit row
    html.Div([
        dcc.Graph(id="profit-bar"),
        dcc.Graph(id="profit-line"),
    ], className="charts"),
    # Region comparison row
    html.Div([
        dcc.Graph(id="region-sales-bar"),
        dcc.Graph(id="region-profit-bar"),
    ], className="charts"),
    html.Footer("Global Superstore | 2011–2014 | one row = one order line"),
], className="page")


# A control supplies a value. pandas performs the actual filtering.
def filter_rows(regions, year):
    mask = df["Region"].isin(regions or []) & df["Year"].eq(year)
    return df.loc[mask].copy()

def make_bar(dff, metric, sort, year):
    if dff.empty:
        return empty_figure(f"{metric} by category")
    totals = dff.groupby("Category", as_index=False)[metric].sum()
    if sort == "desc":
        totals = totals.sort_values(metric, ascending=False)
    elif sort == "asc":
        totals = totals.sort_values(metric, ascending=True)
    else:
        totals = totals.sort_values("Category")
    return px.bar(totals, x="Category", y=metric, template="plotly_white",
                  title=f"{metric} by category — {year}",
                  color="Category",
                  color_discrete_map={
                      "Furniture": "#2463a6",
                      "Office Supplies": "#2ca02c",
                      "Technology": "#ff7f0e",
                  }).update_layout(font=CHART_FONT)

@app.callback(Output("category-bar", "figure"), Output("profit-bar", "figure"),
              Input("regions", "value"), Input("year", "value"),
              Input("sort", "value"))
def update_bars(regions, year, sort):
    dff = filter_rows(regions, year)
    return make_bar(dff, "Sales", sort, year), make_bar(dff, "Profit", sort, year)

@app.callback(Output("monthly-line", "figure"), Output("profit-line", "figure"),
              Output("summary", "children"),
              Input("regions", "value"), Input("year", "value"),
              Input("category-bar", "clickData"), Input("reset", "n_clicks"))
def update_lines(regions, year, click_data, reset_clicks):
    dff = filter_rows(regions, year)
    category = None
    if ctx.triggered_id == "category-bar" and click_data:
        category = click_data["points"][0]["x"]
        dff = dff.loc[dff["Category"].eq(category)]
    scope = category or "All categories"
    summary = (f"Detail: {scope} | Year: {year} | Sales: ${dff['Sales'].sum():,.0f} | "
               f"Profit: ${dff['Profit'].sum():,.0f} | Order lines: {len(dff):,}")
    if dff.empty:
        return empty_figure("Monthly Sales"), empty_figure("Monthly Profit"), summary
    monthly = dff.groupby(pd.Grouper(key="Order Date", freq="MS"))[["Sales", "Profit"]].sum().reset_index()
    sales_fig = px.line(monthly, x="Order Date", y="Sales", markers=True,
                        title=f"Monthly Sales — {scope}", template="plotly_white",
                        color_discrete_sequence=["green"])
    sales_fig.update_layout(font=CHART_FONT)
    profit_fig = px.line(monthly, x="Order Date", y="Profit", markers=True,
                         title=f"Monthly Profit — {scope}", template="plotly_white",
                         color_discrete_sequence=["green"])
    profit_fig.update_layout(font=CHART_FONT)
    return sales_fig, profit_fig, summary


@app.callback(Output("region-sales-bar", "figure"), Output("region-profit-bar", "figure"),
              Input("regions", "value"), Input("year", "value"))
def update_region_bars(regions, year):
    dff = filter_rows(regions, year)
    if dff.empty:
        return empty_figure("Sales by Region & Category"), empty_figure("Profit by Region & Category")
    totals = dff.groupby(["Region", "Category"], as_index=False)[["Sales", "Profit"]].sum()
    sales_fig = px.bar(totals, x="Category", y="Sales", color="Region", barmode="group",
                       template="plotly_white", title=f"Sales by Region & Category — {year}")
    sales_fig.update_layout(font=CHART_FONT)
    profit_fig = px.bar(totals, x="Category", y="Profit", color="Region", barmode="group",
                        template="plotly_white", title=f"Profit by Region & Category — {year}")
    profit_fig.update_layout(font=CHART_FONT)
    return sales_fig, profit_fig


@app.callback(Output("sort", "value"),
              Input("reset", "n_clicks"),
              prevent_initial_call=True)
def reset_controls(_):
    return "alpha"


if __name__ == "__main__":
    app.run(debug=False, port=8050)
