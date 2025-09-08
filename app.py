#!/usr/bin/env python3
# app.py – Dash UI for AutoNav
# --------------------------------------------------------------------
import atexit
import os, signal, sys, time
from queue import Empty

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output, State, no_update
import plotly.graph_objects as go
from controller import Controller
import json

with open("assets/region_network.json") as f:
    REGION_MAP = json.load(f)["regions"]

REG_POS = {k: v["position"][:2] for k, v in REGION_MAP.items()}
EDGES = [(k, n) for k, v in REGION_MAP.items() for n in v["neighbors"]]

ctl = Controller()  # global instance
AGENTS_DIR = "agents"
os.makedirs(AGENTS_DIR, exist_ok=True)


# --------------------------------------------------------------------
def status_style(state: str):
    cmap = {'off': '#dc3545', 'initializing': '#ffc107',
            'ok': '#28a745', 'running': '#28a745', 'error': '#dc3545'}
    return {'backgroundColor': cmap.get(state, 'grey'), 'color': 'white'}


# Dash ----------------------------------------------------------------
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
server = app.server

# Layout --------------------------------------------------------------
app.layout = dbc.Container([
    dcc.Store(id='hist-store',
              data={'ts': [], 'throttle': [], 'steer': [], 'conf': []}),
    dcc.Store(id='tts-ts', data=0),  # NEW — track last mp3 timestamp
    html.Audio(id='tts-player', src='', autoPlay=True),  # NEW — hidden player

    dbc.Tabs([
        dbc.Tab(dcc.Graph(id='action-plot',
                          style={"height": "300px"},
                          figure=go.Figure().update_layout(template="plotly_dark"),
                          config={'displayModeBar': False}),
                label="Action"),

        dbc.Tab(dcc.Graph(id='map-plot',
                          style={"height": "300px"},
                          figure=go.Figure().update_layout(template="plotly_dark"),
                          config={'displayModeBar': False}),
                label="Map"),
    ]),

    dbc.InputGroup([
        dbc.InputGroupText("Stopping Region:"),
        dbc.Select(
            id="dest-drop",
            options=[{"label": "None", "value": ""}] +
                    [{"label": f"r_{i:02d}", "value": f"r_{i:02d}"} for i in range(49)],
            value=""
        ),
    ], className="mb-3 w-100"),

    dbc.InputGroup([
        dbc.Select(id="agent-drop",
                   options=[{"label": f, "value": os.path.join(AGENTS_DIR, f)}
                            for f in os.listdir(AGENTS_DIR)],
                   value=os.path.join(AGENTS_DIR, "hobbs_v10_recip.pt")),
        dbc.Button("Run", id="run-btn", color="primary"),
    ], className="my-3 w-100"),

    dbc.Button("E-STOP", id="estop-btn", color="danger",
               size="lg", className="w-100 mb-3"),

    dcc.Interval(id="tick", interval=500, n_intervals=0),

    html.Script("""
      const audio = document.getElementById('tts-player');
      audio.play().catch(() => {
        document.addEventListener('click', () => {
          audio.play().catch(console.error);
        }, { once: true });
      });
    """)

], fluid=True, className="p-4")


# --------------------------------------------------------------------
@app.callback(Output("dest-drop", "value"),
              Input("dest-drop", "value"))
def update_stop_region(val):
    ctl.set_stop_region(val or None)
    return val


# --------------------------------------------------------------------
@app.callback(Output('run-btn', 'color'),
              Input('run-btn', 'n_clicks'),
              State('agent-drop', 'value'),
              prevent_initial_call=True)
def start_inference(_, model_path):
    if not model_path:
        return no_update
    try:
        ctl.start_inference(model_path)
        return "success"
    except Exception as e:
        print("START ERROR:", e, file=sys.stderr)
        return "danger"


# --------------------------------------------------------------------
@app.callback(Output('estop-btn', 'n_clicks'),
              Input('estop-btn', 'n_clicks'),
              prevent_initial_call=True)
def estop(_):
    ctl.stop_inference()
    return 0


# --------------------------------------------------------------------
@app.callback(Output('action-plot', 'figure'),
              Output('hist-store', 'data'),
              Input('tick', 'n_intervals'),
              State('hist-store', 'data'),
              State('dest-drop', 'value'))
def update_plot(_, hist, stop_region):
    inf = ctl.get_status().get('inference', {})
    vpr = ctl.get_status().get('vpr', {})

    now = time.time()
    throttle_clipped = max(0.0, inf.get('throttle', 0))
    steer_norm = (inf.get('steering', 0) + 1.0) / 2.0

    top_regions = vpr.get('top_regions', [])
    pred_conf = next((c for r, c in top_regions if r == stop_region), 0.0)

    hist['ts'].append(now)
    hist['throttle'].append(throttle_clipped)
    hist['steer'].append(steer_norm)
    hist['conf'].append(pred_conf)

    while hist['ts'] and now - hist['ts'][0] > 5:
        for k in hist:
            hist[k].pop(0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist['ts'], y=hist['throttle'],
                             name='Throttle', line=dict(color='cyan')))
    fig.add_trace(go.Scatter(x=hist['ts'], y=hist['steer'],
                             name='Steering', line=dict(color='magenta')))
    fig.add_trace(go.Scatter(x=hist['ts'], y=hist['conf'],
                             name='Confidence', line=dict(color='yellow', dash='dot')))

    fig.update_layout(template="plotly_dark",
                      yaxis=dict(visible=False),
                      xaxis=dict(visible=False),
                      margin=dict(l=0, r=0, t=0, b=0),
                      legend=dict(orientation="h", yanchor="bottom",
                                  xanchor="center", x=0.5),
                      dragmode=False)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig, hist


# --------------------------------------------------------------------
@app.callback(Output("map-plot", "figure"),
              Input("tick", "n_intervals"))
def update_map(_):
    vpr = ctl.get_status().get("vpr", {})
    top_regions = vpr.get("top_regions", [])

    top_dict = {r: c for r, c in top_regions}
    max_conf = max(top_dict.values(), default=1.0)

    x_e, y_e = [], []
    for a, b in EDGES:
        xa, ya = REG_POS[a]
        xb, yb = REG_POS[b]
        x_e += [xa, xb, None]
        y_e += [ya, yb, None]

    edge_trace = go.Scatter(x=x_e, y=y_e, mode="lines",
                            line=dict(color="#555", width=1),
                            hoverinfo="none")

    xs, ys, hover, size, color, text = [], [], [], [], [], []
    for r, (x, y) in REG_POS.items():
        xs.append(x)
        ys.append(y)
        hover.append(r)
        if r in top_dict:
            ratio = top_dict[r] / max_conf if max_conf else 0.0
            alpha = 0.2 + 0.8 * ratio
            dot_size = 12 + 10 * ratio
            color.append(f"rgba(255,0,255,{alpha:.2f})")
            size.append(dot_size)
            text.append(f"{top_dict[r]:.2f}")
        else:
            color.append("rgba(150,150,150,0.4)")
            size.append(8)
            text.append("")

    node_trace = go.Scatter(x=xs, y=ys,
                            mode="markers+text",
                            hovertext=hover,
                            hoverinfo="text",
                            text=text,
                            textposition="top center",
                            marker=dict(size=size, color=color, line=dict(width=0)))

    fig = go.Figure([edge_trace, node_trace])
    fig.update_layout(template="plotly_dark",
                      xaxis=dict(visible=False),
                      yaxis=dict(visible=False, scaleanchor="x", scaleratio=1),
                      margin=dict(l=20, r=20, t=20, b=20),
                      showlegend=False,
                      dragmode=False,
                      title="")
    return fig


# --------------------------------------------------------------------
@app.callback(Output("tts-player", "src"),
              Output("tts-ts", "data"),
              Input("tick", "n_intervals"),
              State("tts-ts", "data"))
def update_tts(_, last_ts):
    rec = ctl.get_status().get("recognizer", {})
    ts = rec.get("ts", 0)
    if ts and ts != last_ts:
        return rec.get("mp3", ""), ts
    return no_update, last_ts


# graceful exit -------------------------------------------------------
def _shutdown():
    print("Shutdown hook triggered — cleaning up.")
    ctl.shutdown_all()


atexit.register(_shutdown)

# --------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="autonav.local", port=8050, debug=False)
