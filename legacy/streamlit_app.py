import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core

st.set_page_config(
    page_title="Egypt Crop Yield Analytics",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Palette: near-black surfaces, gold as the primary accent, emerald for growth,
# violet for risk. Defined once so the charts and the CSS cannot drift apart.
INK, TEXT, MUTED = "#0B0F14", "#E8EDF2", "#8D98A5"
GOLD, GREEN, PURPLE, RED, GREY = "#D4AF37", "#1F9D6B", "#7C5CD6", "#D9614C", "#6B7885"

MODEL_COLORS = {"Actual": TEXT, "Naive (last year)": GREY,
                "Linear Regression": GOLD, "Random Forest": GREEN}

st.markdown(
    f"""
    <style>
    .block-container {{padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1240px;}}
    h1, h2, h3 {{color: {TEXT}; font-weight: 600; letter-spacing: -0.015em;}}
    h2 {{font-size: 1.32rem;}}
    h3 {{font-size: 1.06rem;}}
    [data-testid="stSidebar"] {{background: linear-gradient(180deg, #0B0F14 0%, #070A0D 100%);
                                border-right: 1px solid #1B222A;}}
    [data-testid="stSidebar"] * {{color: {MUTED} !important;}}
    [data-testid="stSidebar"] h3 {{color: {TEXT} !important; font-size: 1rem;
                                   letter-spacing: .01em;}}
    [data-testid="stSidebar"] hr {{border-color: #1B222A;}}
    [data-testid="stSidebar"] [role="radiogroup"] label {{
        border-radius: 8px; padding: .3rem .5rem;
        transition: background .15s ease, color .15s ease;}}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {{
        background: rgba(212,175,55,0.10);}}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover * {{color: {TEXT} !important;}}
    .hero {{position: relative; overflow: hidden; border: 1px solid #232A33;
            border-radius: 14px; padding: 1.9rem 2.1rem; margin-bottom: 1.5rem;
            background:
              radial-gradient(90% 170% at 100% 0%, rgba(212,175,55,0.18) 0%, rgba(212,175,55,0) 55%),
              radial-gradient(70% 150% at 0% 110%, rgba(124,92,214,0.18) 0%, rgba(124,92,214,0) 62%),
              linear-gradient(180deg, #11161C 0%, #0A0E12 100%);
            box-shadow: 0 18px 40px rgba(0,0,0,0.45);}}
    .hero::after {{content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 2px;
                   background: linear-gradient(90deg, {GOLD} 0%, {GREEN} 48%, {PURPLE} 100%);
                   opacity: .85;}}
    .hero h1 {{color: #FFFFFF; margin: 0; font-size: 1.9rem; letter-spacing: -0.025em;}}
    .hero p {{color: #9FAEBC; margin: .5rem 0 0 0; font-size: .97rem; max-width: 62ch;}}
    .badges {{margin-top: 1.05rem; display: flex; gap: .5rem; flex-wrap: wrap;}}
    .badge {{background: rgba(255,255,255,0.05); border: 1px solid #2A323C; color: #D8DEE5;
             font-size: .7rem; letter-spacing: .09em; text-transform: uppercase;
             padding: .24rem .62rem; border-radius: 999px;}}
    .badge.gold {{border-color: rgba(212,175,55,.45); color: #E7C765;}}
    .kpi {{background: linear-gradient(180deg, #12171D 0%, #0E1319 100%);
           border: 1px solid #232A33; border-left: 3px solid {GOLD}; border-radius: 10px;
           padding: 1rem 1.15rem;
           transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;}}
    .kpi:hover {{transform: translateY(-2px); border-color: #2F3A46;
                 box-shadow: 0 12px 24px rgba(0,0,0,0.45);}}
    .kpi.green {{border-left-color: {GREEN};}}
    .kpi.purple {{border-left-color: {PURPLE};}}
    .kpi .l {{font-size: .68rem; text-transform: uppercase; letter-spacing: .1em; color: {MUTED};}}
    .kpi .v {{font-size: 1.58rem; font-weight: 650; color: #FFFFFF; margin-top: .22rem;
              line-height: 1.15;}}
    .kpi .s {{font-size: .75rem; color: #7E8A97; margin-top: .12rem;}}
    .note {{background: linear-gradient(180deg, rgba(212,175,55,0.07), rgba(212,175,55,0.03));
            border: 1px solid rgba(212,175,55,0.22); border-left: 3px solid {GOLD};
            padding: .85rem 1.05rem; border-radius: 8px; color: #C6CFD8;
            font-size: .9rem; margin: .7rem 0 1.1rem 0; line-height: 1.6;}}
    [data-testid="stDataFrame"] {{border: 1px solid #232A33; border-radius: 10px;}}
    #MainMenu, footer {{visibility: hidden;}}
    </style>
    """,
    unsafe_allow_html=True,
)


def kpi(label, value, sub="", tone=""):
    return (f'<div class="kpi {tone}"><div class="l">{label}</div>'
            f'<div class="v">{value}</div><div class="s">{sub}</div></div>')


def style(fig, h=420, title=None):
    fig.update_layout(
        height=h, title=title, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", color="#C8CFD6", size=12),
        margin=dict(l=10, r=10, t=54 if title else 20, b=10),
        legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11)),
        hoverlabel=dict(bgcolor="#12171D", bordercolor="#2A323C",
                        font=dict(color="#E8EDF2")),
    )
    if title:
        fig.update_layout(
            title=dict(text=title, x=0, xanchor="left",
                       font=dict(color="#F2F4F6", size=15,
                                 family="Inter, Segoe UI, sans-serif")))
    fig.update_xaxes(showgrid=False, linecolor="#242C35", zeroline=False,
                     tickfont=dict(color="#8D98A5", size=11))
    fig.update_yaxes(gridcolor="#1B222A", zeroline=False,
                     tickfont=dict(color="#8D98A5", size=11))
    return fig


@st.cache_data(show_spinner="Loading data")
def get_data():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "FAOSTAT_Egypt_Agriculture_Raw.csv")
    raw = core.load_raw(path)
    data = core.clean(raw)
    yt = core.build_yield_table(data)
    return raw, data, yt


@st.cache_data(show_spinner="Training models")
def get_models(_yt):
    res, test = core.train_forecasters(_yt)
    summ, rtest, imp = core.train_risk(_yt)
    return res, test, summ, rtest, imp


raw, data, yt = get_data()
results, ftest, risk_sum, risk_test, importance = get_models(yt)
items = sorted(yt["Item"].unique())

with st.sidebar:
    st.markdown("### Egypt Crop Yield Analytics")
    st.caption("FAOSTAT, crops and livestock products, 1990 to 2024")
    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["Overview", "Data Explorer", "Yield Forecast", "Decline Risk", "Model Evaluation"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption(f"Training period: up to {core.SPLIT_YEAR}\n\n"
               f"Test period: {core.SPLIT_YEAR + 1} to {int(yt['Year'].max())}")

st.markdown(
    f"""
    <div class="hero">
      <h1>Egypt Crop Yield Analytics</h1>
      <p>Thirty-five years of FAOSTAT records, read as a next-year yield forecast
         and a year-on-year decline screen for {data['Item'].nunique()} crops.</p>
      <div class="badges">
        <span class="badge gold">1990&ndash;2024</span>
        <span class="badge">{len(data):,} records</span>
        <span class="badge">{data['Item'].nunique()} crops</span>
        <span class="badge">strict 2015 time split</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------- Overview
if page == "Overview":
    c = st.columns(4)
    c[0].markdown(kpi("Records", f"{len(raw):,}", "rows in the raw file"), unsafe_allow_html=True)
    c[1].markdown(kpi("Crops", data["Item"].nunique(), "distinct items"), unsafe_allow_html=True)
    c[2].markdown(kpi("Years", f"{int(data['Year'].min())} to {int(data['Year'].max())}",
                      "annual series"), unsafe_allow_html=True)
    best = results.sort_values("MAPE (%)").iloc[0]
    c[3].markdown(kpi("Best MAPE", f"{best['MAPE (%)']:.2f}%", best["Model"]), unsafe_allow_html=True)

    st.markdown("")
    l, r = st.columns([1.2, 1])
    with l:
        st.subheader("Approach")
        st.markdown(
            """
            **1. Forecasting.** Predict next-year yield (kg/ha) for each crop from its own
            last two years, the three-year moving average, the calendar year and the crop identity.
            Linear Regression and Random Forest are compared with a naive baseline that repeats
            last year's yield.

            **2. Risk screening.** A logistic regression estimates the probability that a crop's
            yield falls by more than 10 percent versus the previous year, using recent growth
            and the gap between last year and its three-year average.

            **3. Validation.** A strict time split is used: models are fitted on data up to
            2015 and judged on 2016 to 2024, so no future information reaches the training set.
            """
        )
    with r:
        st.subheader("Records by measurement")
        cnt = data["Element"].value_counts()
        fig = go.Figure(go.Bar(x=cnt.index, y=cnt.values,
                               marker_color=[GOLD, GREEN, PURPLE]))
        st.plotly_chart(style(fig, 300), width="stretch")

    st.markdown(
        '<div class="note">Key finding: the naive baseline has the lowest MAPE and MAE. '
        "The machine learning models add very little over repeating last year's yield, "
        "which should be stated openly when presenting the results.</div>",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------- Data Explorer
elif page == "Data Explorer":
    st.subheader("Historical series")
    a, b = st.columns([2, 1])
    sel = a.multiselect("Crops", items, default=["Wheat", "Rice", "Maize (corn)"]
                        if {"Wheat", "Rice", "Maize (corn)"} <= set(items) else items[:3])
    elem = b.selectbox("Measurement", ["Yield", "Production", "Area harvested"])
    sub = data[(data["Element"] == elem) & (data["Item"].isin(sel))]
    unit = {"Yield": "kg/ha", "Production": "tonnes", "Area harvested": "ha"}[elem]
    fig = go.Figure()
    palette = [GOLD, GREEN, PURPLE, "#4EA8DE", RED, MUTED]
    for i, it in enumerate(sel):
        s = sub[sub["Item"] == it].sort_values("Year")
        fig.add_trace(go.Scatter(x=s["Year"], y=s["Value"], name=it, mode="lines+markers",
                                 line=dict(color=palette[i % len(palette)], width=2.4),
                                 marker=dict(size=5)))
    fig.update_yaxes(title=unit)
    st.plotly_chart(style(fig, 450), width="stretch")

    l, r = st.columns(2)
    with l:
        st.subheader("Data quality")
        miss = int(raw["Value"].isna().sum())
        st.markdown(f"Missing values: **{miss}** ({miss / len(raw) * 100:.2f}% of rows), removed before modelling. "
                    f"Duplicates after cleaning: **{int(data.duplicated().sum())}**.")
        fl = raw["Flag"].map(core.FLAG_LABELS).value_counts()
        fig = go.Figure(go.Bar(x=fl.values, y=fl.index, orientation="h", marker_color=GREEN))
        st.plotly_chart(style(fig, 280, "Source of values (FAOSTAT flags)"), width="stretch")
    with r:
        st.subheader("Top crops by mean yield")
        top = (yt.groupby("Item")["Value"].mean().sort_values().tail(10))
        fig = go.Figure(go.Bar(x=top.values, y=[t[:32] for t in top.index], orientation="h",
                               marker_color=GOLD))
        fig.update_xaxes(title="kg/ha")
        st.plotly_chart(style(fig, 360), width="stretch")

    with st.expander("View filtered data"):
        st.dataframe(sub.sort_values(["Item", "Year"]), width="stretch", hide_index=True)

# -------------------------------------------------------------- Yield Forecast
elif page == "Yield Forecast":
    st.subheader("Crop yield forecast")
    default = items.index("Wheat") if "Wheat" in items else 0
    item = st.selectbox("Select a crop", items, index=default)
    hist = yt[yt["Item"] == item].sort_values("Year")
    tst = ftest[ftest["Item"] == item].sort_values("Year")
    nxt = core.forecast_next(yt, item)

    if nxt is None:
        st.info(
            f"{item} has fewer than four annual observations, so there is not enough "
            "history to fit a forecast. The observed series is shown below."
        )
        fig = go.Figure(
            go.Scatter(x=hist["Year"], y=hist["Value"], name="Actual", mode="lines+markers",
                       line=dict(color=TEXT, width=2.6), marker=dict(size=5))
        )
        fig.update_yaxes(title="kg/ha")
        st.plotly_chart(style(fig, 460), width="stretch")
    else:
        c = st.columns(4)
        c[0].markdown(kpi("Latest yield", f"{hist['Value'].iloc[-1]:,.0f}",
                          f"kg/ha, {int(hist['Year'].iloc[-1])}", tone="green"),
                      unsafe_allow_html=True)
        c[1].markdown(kpi(f"Naive {nxt['year']}", f"{nxt['Naive (last year)']:,.0f}", "kg/ha",
                          tone="green"), unsafe_allow_html=True)
        c[2].markdown(kpi(f"Linear {nxt['year']}", f"{nxt['Linear Regression']:,.0f}", "kg/ha",
                          tone="green"), unsafe_allow_html=True)
        c[3].markdown(kpi(f"Random Forest {nxt['year']}", f"{nxt['Random Forest']:,.0f}", "kg/ha",
                          tone="green"), unsafe_allow_html=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist["Year"], y=hist["Value"], name="Actual", mode="lines+markers",
                                 line=dict(color=TEXT, width=2.6), marker=dict(size=5)))
        for m in ["Naive (last year)", "Linear Regression", "Random Forest"]:
            if len(tst):
                fig.add_trace(go.Scatter(x=tst["Year"], y=tst[m], name=m, mode="lines",
                                         line=dict(color=MODEL_COLORS[m], width=2, dash="dot")))
            fig.add_trace(go.Scatter(x=[hist["Year"].iloc[-1], nxt["year"]],
                                     y=[hist["Value"].iloc[-1], nxt[m]], showlegend=False,
                                     mode="lines+markers", line=dict(color=MODEL_COLORS[m], width=1.5),
                                     marker=dict(size=[0, 9])))
        fig.add_vline(x=core.SPLIT_YEAR + 0.5, line_dash="dash", line_color="#39434F",
                      annotation_text="Train / test split", annotation_position="top left",
                      annotation_font_color=MUTED)
        fig.update_yaxes(title="kg/ha")
        st.plotly_chart(style(fig, 460), width="stretch")

        if len(tst):
            rows = []
            for m in ["Naive (last year)", "Linear Regression", "Random Forest"]:
                e = (tst[m] - tst["Value"]).abs()
                rows.append({"Model": m, "MAE (kg/ha)": e.mean(),
                             "MAPE (%)": (e / tst["Value"]).mean() * 100})
            st.markdown("**Test-period accuracy for this crop**")
            st.dataframe(pd.DataFrame(rows).round(2), width="stretch", hide_index=True)
        else:
            st.info("This crop has no observations in the test period.")
        st.markdown('<div class="note">Forecasts for the coming year are produced by models refitted '
                    "on the full history. They are indicative only and should be read next to the "
                    "naive baseline.</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- Decline Risk
elif page == "Decline Risk":
    st.subheader("Probability of a yield decline above 10 percent")
    c = st.columns(4)
    c[0].markdown(kpi("AUC", f"{risk_sum['auc']:.3f}", "0.5 means no skill",
                      tone="purple"), unsafe_allow_html=True)
    c[1].markdown(kpi("Base rate", f"{risk_sum['base_rate']:.1f}%", "drops in the test period",
                      tone="purple"), unsafe_allow_html=True)
    c[2].markdown(kpi("Riskiest 10%", f"{risk_sum['top10_rate']:.1f}%", "actual drop rate",
                      tone="purple"), unsafe_allow_html=True)
    c[3].markdown(kpi("Lift", f"{risk_sum['top10_rate'] / risk_sum['base_rate']:.1f}x",
                      "versus random selection", tone="purple"), unsafe_allow_html=True)

    st.markdown('<div class="note">Discrimination is weak (AUC close to 0.6). The model is useful '
                "as a coarse screening aid, not as a reliable early-warning system.</div>",
                unsafe_allow_html=True)

    l, r = st.columns(2)
    with l:
        st.markdown("**Feature importance (mean absolute SHAP)**")
        fig = go.Figure(go.Bar(x=importance["Mean |SHAP|"], y=importance["Feature"],
                               orientation="h", marker_color=PURPLE))
        st.plotly_chart(style(fig, 300), width="stretch")
        st.caption("ch1: last year's change. ch2: change the year before. "
                   "gap: last year versus its three-year average. For a linear model these values "
                   "equal coefficient times the deviation from the training mean.")
    with r:
        st.markdown("**Risk score distribution**")
        fig = go.Figure()
        for lab, col, flag in [("No drop", GREEN, 0), ("Drop above 10%", RED, 1)]:
            fig.add_trace(go.Histogram(x=risk_test.loc[risk_test["drop"] == flag, "risk"] * 100,
                                       name=lab, marker_color=col, opacity=0.7, nbinsx=25))
        fig.update_layout(barmode="overlay")
        fig.update_xaxes(title="Predicted probability (%)")
        st.plotly_chart(style(fig, 300), width="stretch")

    st.markdown("**Next-year risk ranking (model refitted on full history)**")
    thr = st.slider("Show crops above probability (%)", 0.0, 15.0, 0.0, 0.5)
    ranking = core.score_next_year(yt)
    ranking = ranking[ranking["Drop probability (%)"] >= thr].rename(
        columns={"ch1": "Last change", "gap": "Gap vs 3y avg"})
    st.dataframe(
        ranking.style.format({"Latest yield": "{:,.0f}", "Last change": "{:+.1%}",
                              "Gap vs 3y avg": "{:+.1%}", "Drop probability (%)": "{:.1f}"}),
        use_container_width=True, hide_index=True, height=380)

# ------------------------------------------------------------ Model Evaluation
else:
    st.subheader("Out-of-sample performance")
    st.caption(f"Trained on years up to {core.SPLIT_YEAR}; evaluated on "
               f"{core.SPLIT_YEAR + 1} to {int(yt['Year'].max())} ({len(ftest)} crop-year observations).")
    st.dataframe(results.round(3), width="stretch", hide_index=True)

    l, r = st.columns(2)
    with l:
        fig = go.Figure(go.Bar(x=results["Model"], y=results["MAPE (%)"],
                               marker_color=[GREY, GOLD, GREEN],
                               text=results["MAPE (%)"].round(2), textposition="outside"))
        fig.update_yaxes(title="MAPE (%)")
        st.plotly_chart(style(fig, 360, "Mean absolute percentage error"), width="stretch")
    with r:
        fig = go.Figure(go.Bar(x=results["Model"], y=results["MAE (kg/ha)"],
                               marker_color=[GREY, GOLD, GREEN],
                               text=results["MAE (kg/ha)"].round(0), textposition="outside"))
        fig.update_yaxes(title="kg/ha")
        st.plotly_chart(style(fig, 360, "Mean absolute error"), width="stretch")

    st.markdown("**Predicted versus actual (Random Forest)**")
    mx = float(max(ftest["Value"].max(), ftest["Random Forest"].max()))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ftest["Value"], y=ftest["Random Forest"], mode="markers",
                             marker=dict(color=GREEN, size=6, opacity=0.55), name="Observations",
                             text=ftest["Item"] + ", " + ftest["Year"].astype(str)))
    fig.add_trace(go.Scatter(x=[0, mx], y=[0, mx], mode="lines", name="Perfect prediction",
                             line=dict(color=TEXT, dash="dash")))
    fig.update_xaxes(title="Actual (kg/ha)")
    fig.update_yaxes(title="Predicted (kg/ha)")
    st.plotly_chart(style(fig, 440), width="stretch")

    st.markdown('<div class="note">R2 is computed on all crops pooled together. Because yields range from '
                "about 700 to over 100,000 kg/ha across crops, the pooled R2 is high mostly because "
                "the models know which crop is which. MAPE and MAE against the naive baseline are "
                "the fairer comparison.</div>", unsafe_allow_html=True)

st.markdown("---")
st.caption(
    "Data: FAOSTAT, Crops and livestock products (QCL), Egypt, 1990 to 2024. "
    f"{len(data):,} cleaned records across {data['Item'].nunique()} crops. "
    "Built with Streamlit, scikit-learn and Plotly."
)
