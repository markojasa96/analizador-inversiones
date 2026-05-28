# ============================================================
#  ANALIZADOR DE INVERSIONES - v4.1
#  Dashboard en español, proyección estadística, UI mejorada
#  Ejecutar: python -m streamlit run dashboard.py
# ============================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import feedparser
from textblob import TextBlob
import requests
import warnings
warnings.filterwarnings("ignore")

# ============================================================
#  PÁGINA
# ============================================================

st.set_page_config(
    page_title="Analizador de Inversiones",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background:#0f172a; }
  [data-testid="stSidebar"]          { background:#1e293b; }
  [data-testid="stSidebarContent"]   { background:#1e293b; }
  .block-container { padding-top:1.5rem; }
  div[data-testid="metric-container"] {
      background:#1e293b; border-radius:10px;
      padding:14px 18px; border:1px solid #334155;
  }
  .stDataFrame { background:#1e293b; }
  h1,h2,h3 { color:#e2e8f0 !important; }
  p, label, .stMarkdown { color:#cbd5e1; }
  .stExpander { background:#1e293b; border:1px solid #334155; border-radius:8px; }
  .stAlert { border-radius:8px; }
  .tag {
      display:inline-block; padding:3px 10px; border-radius:12px;
      font-size:12px; font-weight:600; margin:2px;
  }
  .tag-green  { background:#064e3b; color:#10b981; border:1px solid #10b981; }
  .tag-red    { background:#450a0a; color:#ef4444; border:1px solid #ef4444; }
  .tag-yellow { background:#422006; color:#f59e0b; border:1px solid #f59e0b; }
</style>
""", unsafe_allow_html=True)

# ============================================================
#  CATÁLOGOS
# ============================================================

ACTIVOS_GLOBALES = {
    "S&P 500 (ETF)"  : "SPY",
    "Nasdaq (ETF)"   : "QQQ",
    "México (ETF)"   : "EWW",
    "Oro (ETF)"      : "GLD",
    "Bitcoin"        : "BTC-USD",
    "Ethereum"       : "ETH-USD",
    "Bonos EE.UU."   : "TLT",
    "Sector Tecno."  : "XLK",
    "Sector Energía" : "XLE",
    "Índice Dólar"   : "UUP",
}

ACTIVOS_BMV = {
    "América Móvil"  : "AMXL.MX",
    "FEMSA"          : "FEMSAUBD.MX",
    "Walmart México" : "WALMEX.MX",
    "CEMEX"          : "CEMEXCPO.MX",
    "Grupo Carso"    : "GCARSOA1.MX",
    "Bimbo"          : "BIMBOA.MX",
    "Banorte"        : "GFNORTEO.MX",
    "Televisa"       : "TLEVISACPO.MX",
    "Grupo México"   : "GMEXICOB.MX",
    "Liverpool"      : "LIVEPOLC-1.MX",
}

FUENTES = [
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Investing.com", "https://www.investing.com/rss/news.rss"),
    ("MarketWatch",   "https://feeds.marketwatch.com/marketwatch/topstories"),
]

PALABRAS_POS = ["surge","rally","gain","rise","growth","record","bull","recovery",
                "profit","strong","boost","beat","sube","alza","gana","récord",
                "crecimiento","positivo","up","high"]
PALABRAS_NEG = ["crash","fall","drop","loss","bear","recession","fear","selloff",
                "decline","weak","risk","tariff","war","crisis","baja","cae",
                "pérdida","recesión","inflación","negativo","down","low"]

TELEGRAM_TOKEN   = "8362312296:AAFr9lR1ad775g8p_OxuSvz9nYMMAitcCFk"
TELEGRAM_CHAT_ID = "5858053994"
COLORES = ["#6366f1","#10b981","#f59e0b","#ef4444","#8b5cf6","#06b6d4","#f43f5e","#84cc16"]

# ============================================================
#  FUNCIONES
# ============================================================

def esc(t):
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

@st.cache_data(ttl=3600, show_spinner=False)
def descargar(tickers_dict, f_ini, f_fin):
    datos = {}
    for nombre, ticker in tickers_dict.items():
        try:
            df = yf.download(ticker, start=f_ini, end=f_fin, progress=False)
            if not df.empty:
                datos[nombre] = df["Close"].squeeze()
        except:
            pass
    return pd.DataFrame(datos).dropna(how="all")

@st.cache_data(ttl=1800, show_spinner=False)
def obtener_noticias():
    titulares, scores = [], []
    for nombre, url in FUENTES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                titulo = entry.get("title","")
                if not titulo:
                    continue
                s  = TextBlob(titulo).sentiment.polarity
                tl = titulo.lower()
                s += sum(0.15 for p in PALABRAS_POS if p in tl)
                s -= sum(0.15 for p in PALABRAS_NEG if p in tl)
                s  = max(-1, min(1, s))
                titulares.append((s, titulo, nombre))
                scores.append(s)
        except:
            pass
    return (float(np.mean(scores)) if scores else 0), sorted(titulares, reverse=True)

def backtest(precio, ma_r, ma_l, capital_ini, sl_pct, trailing):
    mar    = precio.rolling(ma_r).mean()
    mal    = precio.rolling(ma_l).mean()
    cap    = float(capital_ini)
    en_mkt = False
    pc     = pmax = 0.0
    ops    = []
    hist   = []
    señal  = (mar > mal).astype(int)
    prev   = señal.shift(1)

    for fecha, pa in precio.items():
        pa = float(pa)
        if pd.isna(pa):
            hist.append(cap); continue
        razon = None
        if en_mkt:
            pmax  = max(pmax, pa) if trailing else pmax
            stop  = (pmax if trailing else pc) * (1 - sl_pct)
            if pa <= stop:
                razon = "Stop-Loss"
            elif señal.get(fecha,1)==0 and prev.get(fecha,1)==1:
                razon = "Death Cross"
        if razon and en_mkt:
            g   = (pa - pc) / pc * 100
            cap = cap * (pa / pc)
            ops.append({"tipo":"VENTA","fecha":fecha,"precio":pa,"gan":g,"capital":cap,"razon":razon})
            en_mkt = False
        if not en_mkt and señal.get(fecha,0)==1 and prev.get(fecha,0)==0:
            en_mkt = True; pc = pa; pmax = pa
            ops.append({"tipo":"COMPRA","fecha":fecha,"precio":pa,"capital":cap})
        hist.append(cap*(pa/pc) if en_mkt else cap)

    if en_mkt:
        cap = cap * (float(precio.iloc[-1]) / pc)
    ventas = [o for o in ops if o["tipo"]=="VENTA"]
    total  = len(ventas)
    ganad  = sum(1 for o in ventas if o["gan"]>0)
    wr     = ganad/total*100 if total>0 else 0
    rend   = (cap - capital_ini) / capital_ini * 100
    bh_cap = capital_ini * (float(precio.iloc[-1]) / float(precio.iloc[0]))
    rend_bh= (bh_cap - capital_ini) / capital_ini * 100
    cs     = pd.Series(hist)
    dd     = ((cs - cs.cummax()) / cs.cummax() * 100).min()
    return dict(cap=cap, bh=bh_cap, rend=rend, rend_bh=rend_bh,
                total=total, ganad=ganad, wr=wr, dd=dd,
                ops=ops, hist=hist, mar=mar, mal=mal)

def proyeccion_montecarlo(precio, dias=90, simulaciones=500):
    """Proyección estadística usando simulación de Monte Carlo."""
    retornos   = precio.pct_change().dropna()
    mu         = retornos.mean()
    sigma      = retornos.std()
    precio_hoy = float(precio.iloc[-1])
    np.random.seed(42)
    resultados = np.zeros((simulaciones, dias))
    for i in range(simulaciones):
        r = np.random.normal(mu, sigma, dias)
        precios_sim = [precio_hoy]
        for ret in r:
            precios_sim.append(precios_sim[-1] * (1 + ret))
        resultados[i] = precios_sim[1:]

    p10  = np.percentile(resultados, 10, axis=0)
    p25  = np.percentile(resultados, 25, axis=0)
    p50  = np.percentile(resultados, 50, axis=0)
    p75  = np.percentile(resultados, 75, axis=0)
    p90  = np.percentile(resultados, 90, axis=0)

    fechas_fut = pd.date_range(
        start=precio.index[-1] + timedelta(days=1),
        periods=dias, freq="B"
    )
    return fechas_fut, p10, p25, p50, p75, p90, precio_hoy

def enviar_telegram(msg, silencioso=False):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id":TELEGRAM_CHAT_ID,"text":msg,
                  "parse_mode":"HTML","disable_notification":silencioso},
            timeout=10
        )
        return r.status_code == 200
    except:
        return False

# ============================================================
#  SIDEBAR
# ============================================================

with st.sidebar:
    st.image("https://img.icons8.com/fluency/48/combo-chart.png", width=40)
    st.title("Configuración")
    st.markdown("---")

    st.markdown("**📅 Período de análisis**")
    años_hist = st.slider("Historial (años)", 1, 10, 3, key="ah")
    años_bt   = st.slider("Backtesting (años)", 1, 10, 5, key="abt")
    dias_proy = st.slider("Proyección (días hábiles)", 30, 180, 90, key="dp")

    st.markdown("---")
    st.markdown("**💰 Capital de simulación**")
    capital_ini = st.number_input("Capital ($)", 1000, 10_000_000, 10_000, step=1000)
    st.caption("Puedes usar pesos o dólares según el activo")

    st.markdown("---")
    st.markdown("**🌎 Mercados globales**")
    sel_glob = st.multiselect("Activos", list(ACTIVOS_GLOBALES.keys()),
                               default=["S&P 500 (ETF)","Nasdaq (ETF)","Oro (ETF)","Bitcoin"])

    st.markdown("**🇲🇽 Bolsa Mexicana (BMV)**")
    sel_bmv = st.multiselect("Acciones MX", list(ACTIVOS_BMV.keys()),
                              default=["América Móvil","FEMSA","Walmart México"])

    st.markdown("---")
    st.markdown("**🔬 Backtesting**")
    ma_r  = st.selectbox("Media rápida", [5,10,20,50], index=1)
    ma_l  = st.selectbox("Media lenta",  [20,50,100,200], index=1)
    sl    = st.slider("Stop-loss (%)", 3, 20, 8) / 100
    trail = st.toggle("Trailing stop", value=True)

    todos = sel_glob + sel_bmv
    act_bt = st.selectbox("Activo para analizar", todos if todos else ["S&P 500 (ETF)"])

    st.markdown("---")
    btn_tg = st.button("📲 Enviar a Telegram", use_container_width=True, type="primary")

# ============================================================
#  CARGA DE DATOS
# ============================================================

f_ini = (datetime.today() - timedelta(days=365*años_hist)).strftime("%Y-%m-%d")
f_fin = datetime.today().strftime("%Y-%m-%d")
f_bt  = (datetime.today() - timedelta(days=365*años_bt)).strftime("%Y-%m-%d")

todos_activos = {**{k:ACTIVOS_GLOBALES[k] for k in sel_glob},
                 **{k:ACTIVOS_BMV[k]      for k in sel_bmv}}

# ============================================================
#  ENCABEZADO
# ============================================================

col_t1, col_t2 = st.columns([3,1])
with col_t1:
    st.title("📊 Analizador de Inversiones")
with col_t2:
    st.markdown(f"<p style='text-align:right;color:#64748b;margin-top:18px'>"
                f"v4.1 · {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>",
                unsafe_allow_html=True)

if not todos_activos:
    st.info("👈 Selecciona activos en el panel izquierdo para comenzar.")
    st.stop()

# ============================================================
#  TABS PRINCIPALES
# ============================================================

tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Rendimiento",
    "🔬 Backtesting",
    "🔮 Proyección",
    "📰 Noticias y Señal"
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 1 — RENDIMIENTO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab1:
    with st.spinner("Descargando datos de mercado..."):
        precios = descargar(todos_activos, f_ini, f_fin)

    if precios.empty:
        st.error("No se pudieron descargar datos. Verifica tu conexión.")
        st.stop()

    rendimiento = (precios / precios.iloc[0]) * 100

    # Métricas rápidas
    resumen = []
    cols_met = st.columns(min(len(precios.columns), 5))
    for i, col in enumerate(precios.columns):
        serie = precios[col].dropna()
        if len(serie) < 2: continue
        ret = ((serie.iloc[-1] - serie.iloc[0]) / serie.iloc[0]) * 100
        vol = serie.pct_change().dropna().std() * (252**0.5) * 100
        vf  = capital_ini * (serie.iloc[-1] / serie.iloc[0])
        gan = vf - capital_ini
        resumen.append((col, float(serie.iloc[-1]), ret, vol, vf, gan))
        with cols_met[i % 5]:
            st.metric(col, f"${serie.iloc[-1]:,.2f}",
                      delta=f"{ret:+.1f}%",
                      delta_color="normal" if ret >= 0 else "inverse")

    st.markdown("---")

    # Gráfica comparativa
    st.markdown("#### Rendimiento comparativo (%)")
    fig1 = go.Figure()
    for i, col in enumerate(rendimiento.columns):
        s = rendimiento[col].dropna()
        fig1.add_trace(go.Scatter(
            x=s.index, y=s-100, name=col,
            line=dict(color=COLORES[i%len(COLORES)], width=2.5),
            hovertemplate=f"<b>{col}</b><br>%{{x|%d %b %Y}}: %{{y:+.1f}}%<extra></extra>"
        ))
    fig1.add_hrect(y0=-100, y1=0, fillcolor="rgba(239,68,68,0.04)", line_width=0)
    fig1.add_hline(y=0, line_dash="dash", line_color="#475569", opacity=0.6)
    fig1.update_layout(
        plot_bgcolor="#0f172a", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0", family="Arial"),
        hovermode="x unified", height=380,
        legend=dict(bgcolor="rgba(15,23,42,0.9)", bordercolor="#334155", borderwidth=1, orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=10,b=40,l=55,r=20),
        yaxis=dict(title="Rendimiento (%)", gridcolor="#1e3a5f"),
        xaxis=dict(gridcolor="#1e293b")
    )
    st.plotly_chart(fig1, use_container_width=True)

    # Tabla resumen
    st.markdown("#### Simulación de inversión")
    filas = []
    for col, ph, ret, vol, vf, gan in resumen:
        mercado = "🇲🇽 BMV" if col in sel_bmv else "🌎 Global"
        filas.append({
            "Mercado"      : mercado,
            "Activo"       : col,
            "Precio actual": f"${ph:,.2f}",
            "Rendimiento"  : f"{ret:+.1f}%",
            "Riesgo (vol)" : f"{vol:.1f}%",
            f"${capital_ini:,.0f} → hoy": f"${vf:,.0f}",
            "Ganancia/Pérd": f"${gan:+,.0f}",
        })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    # Sección BMV separada
    if sel_bmv:
        st.markdown("---")
        st.markdown("#### 🇲🇽 Acciones de la Bolsa Mexicana (BMV)")
        p_bmv = precios[[c for c in precios.columns if c in sel_bmv]]
        if not p_bmv.empty:
            r_bmv = (p_bmv / p_bmv.iloc[0]) * 100
            fig_bmv = go.Figure()
            for i, col in enumerate(r_bmv.columns):
                s = r_bmv[col].dropna()
                fig_bmv.add_trace(go.Scatter(
                    x=s.index, y=s-100, name=col,
                    line=dict(color=COLORES[i%len(COLORES)], width=2.5),
                    hovertemplate=f"<b>{col}</b><br>%{{x|%d %b %Y}}: %{{y:+.1f}}%<extra></extra>"
                ))
            fig_bmv.add_hline(y=0, line_dash="dash", line_color="#475569", opacity=0.5)
            fig_bmv.update_layout(
                plot_bgcolor="#0f172a", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"), hovermode="x unified", height=320,
                legend=dict(bgcolor="rgba(15,23,42,0.9)", bordercolor="#334155", borderwidth=1, orientation="h", yanchor="bottom", y=1.02),
                margin=dict(t=10,b=40,l=55,r=20),
                yaxis=dict(gridcolor="#1e3a5f"), xaxis=dict(gridcolor="#1e293b")
            )
            st.plotly_chart(fig_bmv, use_container_width=True)

            c1, c2 = st.columns(2)
            bmv_ren = [(col,ret) for col,_,ret,_,_,_ in resumen if col in sel_bmv]
            if bmv_ren:
                mejor_mx = max(bmv_ren, key=lambda x: x[1])
                peor_mx  = min(bmv_ren, key=lambda x: x[1])
                with c1:
                    st.success(f"🏆 Mejor: **{mejor_mx[0]}** → {mejor_mx[1]:+.1f}%")
                with c2:
                    st.error(f"📉 Peor: **{peor_mx[0]}** → {peor_mx[1]:+.1f}%")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 2 — BACKTESTING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab2:
    ticker_bt = todos_activos.get(act_bt)
    if not ticker_bt:
        st.info("Selecciona un activo en el panel izquierdo.")
        st.stop()

    with st.spinner(f"Calculando backtesting de {act_bt}..."):
        df_bt = yf.download(ticker_bt, start=f_bt, end=f_fin, progress=False)
        precio_bt = df_bt["Close"].squeeze() if not df_bt.empty else pd.Series()

    if precio_bt.empty or len(precio_bt) < ma_l + 10:
        st.warning(f"Datos insuficientes. Reduce la media lenta o amplía el período.")
    else:
        bt = backtest(precio_bt, ma_r, ma_l, capital_ini, sl, trail)

        st.markdown(f"#### Estrategia MA{ma_r}/MA{ma_l} en {act_bt} — {años_bt} años · Stop-loss {sl*100:.0f}%")

        c1,c2,c3,c4 = st.columns(4)
        ventaja = bt["rend"] - bt["rend_bh"]
        with c1: st.metric("Capital final (estrategia)", f"${bt['cap']:,.0f}", f"{bt['rend']:+.1f}%")
        with c2: st.metric("Capital Buy & Hold",         f"${bt['bh']:,.0f}",  f"{bt['rend_bh']:+.1f}%")
        with c3: st.metric("Tasa de éxito",              f"{bt['wr']:.1f}%",   f"{bt['ganad']}/{bt['total']} operaciones")
        with c4: st.metric("Máx. caída (drawdown)",      f"{bt['dd']:.1f}%",   "Con trailing stop" if trail else "Stop fijo", delta_color="off")

        if ventaja > 0:
            st.success(f"✅ La estrategia superó al Buy & Hold por **${bt['cap']-bt['bh']:,.0f}** ({ventaja:+.1f}%)")
        else:
            st.warning(f"⚠️ Buy & Hold fue mejor por **${bt['bh']-bt['cap']:,.0f}** ({abs(ventaja):.1f}%) — esto es común en mercados alcistas prolongados.")

        # Gráfica backtesting
        fig_bt = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            subplot_titles=(
                f"Precio de {act_bt} con medias móviles y señales de entrada/salida",
                "Evolución del capital: Estrategia vs Buy & Hold"
            ),
            vertical_spacing=0.1, row_heights=[0.55,0.45]
        )

        fig_bt.add_trace(go.Scatter(x=precio_bt.index, y=precio_bt,
            name="Precio", line=dict(color="#94a3b8",width=1.2)), row=1,col=1)
        fig_bt.add_trace(go.Scatter(x=bt["mar"].index, y=bt["mar"],
            name=f"MA{ma_r} días", line=dict(color="#10b981",width=1.8,dash="dot")), row=1,col=1)
        fig_bt.add_trace(go.Scatter(x=bt["mal"].index, y=bt["mal"],
            name=f"MA{ma_l} días", line=dict(color="#ef4444",width=1.8,dash="dash")), row=1,col=1)

        compras = [o for o in bt["ops"] if o["tipo"]=="COMPRA"]
        ventas_c= [o for o in bt["ops"] if o["tipo"]=="VENTA" and o.get("razon")=="Death Cross"]
        stops   = [o for o in bt["ops"] if o["tipo"]=="VENTA" and o.get("razon")=="Stop-Loss"]

        if compras:
            fig_bt.add_trace(go.Scatter(
                x=[o["fecha"] for o in compras], y=[o["precio"] for o in compras],
                mode="markers", name="🟢 Compra",
                marker=dict(color="#10b981",size=11,symbol="triangle-up",line=dict(color="white",width=1))
            ), row=1,col=1)
        if ventas_c:
            fig_bt.add_trace(go.Scatter(
                x=[o["fecha"] for o in ventas_c], y=[o["precio"] for o in ventas_c],
                mode="markers", name="🔴 Venta (cruce)",
                marker=dict(color="#ef4444",size=11,symbol="triangle-down",line=dict(color="white",width=1))
            ), row=1,col=1)
        if stops:
            fig_bt.add_trace(go.Scatter(
                x=[o["fecha"] for o in stops], y=[o["precio"] for o in stops],
                mode="markers", name="⚠️ Stop-Loss",
                marker=dict(color="#f59e0b",size=13,symbol="x",line=dict(color="white",width=2))
            ), row=1,col=1)

        cap_s = pd.Series(bt["hist"], index=precio_bt.index[:len(bt["hist"])])
        bh_s  = (precio_bt / float(precio_bt.iloc[0])) * capital_ini

        fig_bt.add_trace(go.Scatter(x=cap_s.index, y=cap_s, name="Estrategia",
            line=dict(color="#6366f1",width=2.5),
            fill="tozeroy", fillcolor="rgba(99,102,241,0.08)"), row=2,col=1)
        fig_bt.add_trace(go.Scatter(x=bh_s.index, y=bh_s, name="Buy & Hold",
            line=dict(color="#f59e0b",width=2,dash="dot"),
            fill="tozeroy", fillcolor="rgba(245,158,11,0.05)"), row=2,col=1)

        fig_bt.update_layout(
            plot_bgcolor="#0f172a", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e2e8f0",family="Arial"), hovermode="x unified",
            legend=dict(bgcolor="rgba(15,23,42,0.9)",bordercolor="#334155",borderwidth=1,orientation="h",yanchor="bottom",y=1.02),
            height=620, margin=dict(t=40,b=40,l=60,r=20)
        )
        fig_bt.update_xaxes(gridcolor="#1e293b")
        fig_bt.update_yaxes(gridcolor="#1e3a5f")
        st.plotly_chart(fig_bt, use_container_width=True)

        # Tabla de operaciones
        with st.expander(f"📋 Historial de operaciones ({bt['total']} ventas)"):
            filas_ops = []
            for o in bt["ops"]:
                fs = o["fecha"].strftime("%d/%m/%Y") if hasattr(o["fecha"],"strftime") else str(o["fecha"])[:10]
                if o["tipo"]=="COMPRA":
                    filas_ops.append({"Fecha":fs,"Tipo":"🟢 COMPRA","Precio":f"${o['precio']:,.2f}","Ganancia":"—","Capital acum.":f"${o['capital']:,.0f}","Razón":"Golden Cross"})
                else:
                    filas_ops.append({"Fecha":fs,"Tipo":"🔴 VENTA","Precio":f"${o['precio']:,.2f}","Ganancia":f"{o['gan']:+.1f}%","Capital acum.":f"${o['capital']:,.0f}","Razón":o.get("razon","—")})
            st.dataframe(pd.DataFrame(filas_ops), use_container_width=True, hide_index=True)

        with st.expander("❓ ¿Cómo leer estas gráficas?"):
            st.markdown("""
**Panel superior — Precio + Medias Móviles:**
- La línea **gris** es el precio real del activo día a día.
- La línea **verde punteada** es la media móvil rápida (promedio de los últimos N días).
- La línea **roja discontinua** es la media móvil lenta.
- 🟢 **Triángulo verde (compra):** el programa "compra" cuando la media rápida cruza *arriba* de la lenta — señal de tendencia alcista.
- 🔴 **Triángulo rojo (venta):** venta cuando la media rápida cruza *abajo* — señal de tendencia bajista.
- ⚠️ **X amarilla (stop-loss):** venta de emergencia porque el precio cayó más del límite configurado.

**Panel inferior — Capital acumulado:**
- **Línea morada:** cómo creció (o cayó) tu capital siguiendo la estrategia.
- **Línea amarilla punteada:** cómo hubiera quedado si hubieras comprado y no tocado nada (Buy & Hold).
- Si la morada queda arriba, la estrategia ganó. Si queda abajo, fue mejor no hacer nada.
            """)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 3 — PROYECCIÓN ESTADÍSTICA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab3:
    ticker_proy = todos_activos.get(act_bt)

    with st.spinner("Calculando proyección estadística..."):
        if ticker_proy:
            df_p = yf.download(ticker_proy, start=f_ini, end=f_fin, progress=False)
            precio_p = df_p["Close"].squeeze() if not df_p.empty else pd.Series()
        else:
            precio_p = pd.Series()

    if precio_p.empty:
        st.warning("Sin datos para proyectar.")
    else:
        st.markdown(f"#### 🔮 Proyección estadística — {act_bt} — próximos {dias_proy} días hábiles")

        st.info("""
**¿Qué es esto?** Esta proyección usa **Simulación de Monte Carlo**: corre 500 escenarios posibles 
basados en el comportamiento histórico del activo (su rendimiento promedio y su volatilidad). 
**No predice el precio exacto** — muestra un rango de posibilidades con distintos niveles de probabilidad.
        """)

        fechas_fut, p10, p25, p50, p75, p90, precio_hoy = proyeccion_montecarlo(precio_p, dias_proy)

        # Métricas de proyección
        ret_esperado = ((p50[-1] - precio_hoy) / precio_hoy) * 100
        ret_optimista= ((p90[-1] - precio_hoy) / precio_hoy) * 100
        ret_pesimista= ((p10[-1] - precio_hoy) / precio_hoy) * 100

        c1,c2,c3,c4 = st.columns(4)
        with c1: st.metric("Precio actual",    f"${precio_hoy:,.2f}")
        with c2: st.metric("Escenario base",   f"${p50[-1]:,.2f}",  f"{ret_esperado:+.1f}%")
        with c3: st.metric("Escenario optimista (90%)", f"${p90[-1]:,.2f}", f"{ret_optimista:+.1f}%", delta_color="normal")
        with c4: st.metric("Escenario pesimista (10%)", f"${p10[-1]:,.2f}", f"{ret_pesimista:+.1f}%", delta_color="inverse")

        # Gráfica de proyección
        fig_proy = go.Figure()

        # Historial reciente (últimos 6 meses)
        hist_reciente = precio_p.iloc[-126:]
        fig_proy.add_trace(go.Scatter(
            x=hist_reciente.index, y=hist_reciente,
            name="Historial real", line=dict(color="#94a3b8",width=2),
            hovertemplate="%{x|%d %b %Y}: $%{y:,.2f}<extra>Historial</extra>"
        ))

        # Punto de hoy
        fig_proy.add_trace(go.Scatter(
            x=[precio_p.index[-1]], y=[precio_hoy],
            mode="markers", name="Hoy",
            marker=dict(color="white",size=10,symbol="circle",line=dict(color="#6366f1",width=3))
        ))

        # Banda 10-90% (zona exterior)
        fig_proy.add_trace(go.Scatter(
            x=list(fechas_fut)+list(fechas_fut[::-1]),
            y=list(p90)+list(p10[::-1]),
            fill="toself", fillcolor="rgba(99,102,241,0.08)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Rango 10%-90%", hoverinfo="skip"
        ))

        # Banda 25-75% (zona interior)
        fig_proy.add_trace(go.Scatter(
            x=list(fechas_fut)+list(fechas_fut[::-1]),
            y=list(p75)+list(p25[::-1]),
            fill="toself", fillcolor="rgba(99,102,241,0.18)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Rango 25%-75%", hoverinfo="skip"
        ))

        # Líneas de percentiles
        for vals, nombre, color, dash in [
            (p90, "Optimista (90%)",  "#10b981", "dot"),
            (p75, "Alto (75%)",       "#84cc16", "dot"),
            (p50, "Base (mediana)",   "#6366f1", "solid"),
            (p25, "Bajo (25%)",       "#f59e0b", "dot"),
            (p10, "Pesimista (10%)", "#ef4444", "dot"),
        ]:
            fig_proy.add_trace(go.Scatter(
                x=fechas_fut, y=vals, name=nombre,
                line=dict(color=color, width=1.8 if nombre!="Base (mediana)" else 2.5, dash=dash),
                hovertemplate=f"<b>{nombre}</b><br>%{{x|%d %b %Y}}: $%{{y:,.2f}}<extra></extra>"
            ))

        # Línea vertical "hoy"
        fig_proy.add_vline(
            x=precio_p.index[-1], line_dash="dash",
            line_color="#475569", opacity=0.7,
            annotation_text="Hoy", annotation_position="top"
        )

        fig_proy.update_layout(
            plot_bgcolor="#0f172a", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e2e8f0",family="Arial"),
            hovermode="x unified", height=480,
            legend=dict(bgcolor="rgba(15,23,42,0.9)",bordercolor="#334155",borderwidth=1,orientation="h",yanchor="bottom",y=1.02),
            margin=dict(t=20,b=40,l=65,r=20),
            yaxis=dict(title="Precio ($)", gridcolor="#1e3a5f"),
            xaxis=dict(gridcolor="#1e293b")
        )
        st.plotly_chart(fig_proy, use_container_width=True)

        # Simulación de inversión con proyección
        st.markdown("#### 💰 Simulación de tu inversión en los escenarios")
        c1,c2,c3 = st.columns(3)
        for col_ui, escenario, precio_final, color in [
            (c1, "📉 Pesimista", p10[-1],  "inverse"),
            (c2, "⚖️ Base",      p50[-1],  "off"),
            (c3, "📈 Optimista", p90[-1],  "normal"),
        ]:
            vf  = capital_ini * (precio_final / precio_hoy)
            gan = vf - capital_ini
            with col_ui:
                st.metric(escenario, f"${vf:,.0f}", f"${gan:+,.0f}", delta_color=color)

        with st.expander("❓ ¿Cómo leer la proyección?"):
            st.markdown("""
**Las bandas de color** representan rangos de probabilidad:
- **Zona oscura interior (25%-75%):** aquí caerá el precio con ~50% de probabilidad.
- **Zona clara exterior (10%-90%):** aquí caerá el precio con ~80% de probabilidad.

**Las líneas de colores:**
- 🟢 **Optimista (90%):** solo el 10% de los escenarios fueron mejores que este.
- 🟣 **Base (mediana):** el escenario más probable según el comportamiento histórico.
- 🔴 **Pesimista (10%):** solo el 10% de los escenarios fueron peores que este.

**Importante:** esto NO es una predicción. Es una extrapolación estadística del pasado. 
Los mercados pueden comportarse de formas inesperadas que ningún modelo predice.
            """)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 4 — NOTICIAS Y SEÑAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab4:
    with st.spinner("Analizando noticias en tiempo real..."):
        score_sent, noticias = obtener_noticias()

    st.markdown("#### 📰 Sentimiento del mercado — noticias en tiempo real")

    pos = sum(1 for s,_,_ in noticias if s > 0.05)
    neg = sum(1 for s,_,_ in noticias if s < -0.05)
    neu = len(noticias) - pos - neg

    c1,c2,c3,c4 = st.columns(4)
    color_sent = "normal" if score_sent > 0.1 else ("inverse" if score_sent < -0.1 else "off")
    with c1: st.metric("Score de sentimiento", f"{score_sent:+.3f}", "🟢 Positivo" if score_sent>0.1 else ("🔴 Negativo" if score_sent<-0.1 else "🟡 Neutro"), delta_color=color_sent)
    with c2: st.metric("Noticias positivas", pos)
    with c3: st.metric("Noticias neutras",   neu)
    with c4: st.metric("Noticias negativas", neg, delta_color="inverse")

    # Gráfica barras sentimiento
    if noticias:
        scores_list = [s for s,_,_ in noticias]
        titulos_cortos = [t[:40]+"…" for _,t,_ in noticias]
        colores_bar = ["#10b981" if s>0.05 else ("#ef4444" if s<-0.05 else "#f59e0b") for s in scores_list]
        fig_sent = go.Figure(go.Bar(
            x=scores_list, y=titulos_cortos, orientation="h",
            marker_color=colores_bar, opacity=0.85,
            hovertemplate="Score: %{x:+.2f}<extra></extra>"
        ))
        fig_sent.add_vline(x=0, line_color="#475569", line_dash="dash", opacity=0.7)
        fig_sent.update_layout(
            plot_bgcolor="#0f172a", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e2e8f0",size=11), height=max(250, len(noticias)*28),
            margin=dict(t=10,b=30,l=10,r=20),
            xaxis=dict(title="Score de sentimiento", gridcolor="#1e3a5f"),
            yaxis=dict(gridcolor="#1e293b", autorange="reversed")
        )
        st.plotly_chart(fig_sent, use_container_width=True)

    # ---- SEÑAL FINAL ----
    st.markdown("---")
    st.markdown("#### 🎯 Señal combinada del día")

    if ticker_bt and not precio_bt.empty and len(precio_bt) > ma_l + 10:
        bt_señal   = backtest(precio_bt, ma_r, ma_l, capital_ini, sl, trail)
        señal_tec  = 1 if bt_señal["mar"].iloc[-1] > bt_señal["mal"].iloc[-1] else -1
        señal_nom  = "COMPRA — MA rápida > MA lenta" if señal_tec==1 else "VENTA — MA rápida < MA lenta"
        score_comb = señal_tec * 0.6 + score_sent * 0.4

        c1,c2,c3 = st.columns(3)
        with c1: st.metric("Señal técnica", "COMPRA 📈" if señal_tec==1 else "VENTA 📉",
                            delta=f"MA{ma_r} vs MA{ma_l}",
                            delta_color="normal" if señal_tec==1 else "inverse")
        with c2: st.metric("Sentimiento", f"{score_sent:+.3f}",
                            "🟢 Favorable" if score_sent>0.1 else ("🔴 Adverso" if score_sent<-0.1 else "🟡 Neutro"))
        with c3: st.metric("Score final", f"{score_comb:+.3f}", "60% técnico + 40% noticias", delta_color="off")

        st.markdown("")
        if score_comb > 0.2:
            st.success("## 🟢 CONDICIONES FAVORABLES\nLa señal técnica y el sentimiento apuntan en la misma dirección positiva. Momento potencialmente favorable para considerar entrar.")
        elif score_comb < -0.2:
            st.error("## 🔴 CONDICIONES DESFAVORABLES\nSeñal técnica negativa y/o noticias adversas. Considera reducir exposición o esperar mejor momento.")
        else:
            st.warning("## 🟡 SEÑAL MIXTA — MANTENER\nNo hay tendencia clara. Evita tomar decisiones impulsivas.")

        st.caption("⚠️ Este sistema es una herramienta educativa de análisis. No garantiza rendimientos ni constituye consejo financiero profesional.")

    # ---- BOTÓN TELEGRAM ----
    if btn_tg:
        with st.spinner("Enviando reporte a Telegram..."):
            fecha_hoy = datetime.today().strftime("%d/%m/%Y %H:%M")
            alerta    = score_comb < -0.2 if ticker_bt else False

            msg1 = f"📊 <b>REPORTE {esc(fecha_hoy)}</b>\n\n<b>Rendimiento {años_hist} años</b>\n"
            for col,ph,ret,vol,vf,gan in resumen:
                msg1 += f"{'📈' if ret>0 else '📉'} {esc(col)}: <b>{ret:+.1f}%</b>\n"

            msg2 = f"💵 <b>Simulación ${capital_ini:,.0f}</b>\n\n"
            for col,ph,ret,vol,vf,gan in resumen:
                msg2 += f"{'🟢' if gan>0 else '🔴'} {esc(col)}: <b>${vf:,.0f}</b> ({gan:+,.0f})\n"

            sent_e = "🟢" if score_sent>0.1 else ("🔴" if score_sent<-0.1 else "🟡")
            dec    = ("🟢 FAVORABLES" if score_comb>0.2 else ("🔴 DESFAVORABLES" if score_comb<-0.2 else "🟡 MIXTA"))
            tec_e  = "📈" if señal_tec==1 else "📉"
            msg3   = (f"🎯 <b>SEÑAL DEL DÍA</b>\n\n"
                      f"{tec_e} Técnica: {esc(señal_nom)}\n"
                      f"{sent_e} Sentimiento: {score_sent:+.3f}\n"
                      f"Score: <b>{score_comb:+.3f}</b>\n\n"
                      f"<b>{esc(dec)}</b>\n\n"
                      f"⚠️ <i>Solo análisis educativo</i>")

            ok = all([enviar_telegram(msg1), enviar_telegram(msg2),
                      enviar_telegram(msg3, silencioso=not alerta)])
            if ok:
                st.success("✅ Reporte enviado a Telegram")
            else:
                st.error("⚠️ Error al enviar. Revisa tu conexión.")
