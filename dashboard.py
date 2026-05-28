# ============================================================
#  ANALIZADOR DE INVERSIONES - v4.2
#  Dashboard rediseñado — limpio, claro, sin solapamientos
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

# ─────────────────────────────────────────────────────────────
#  CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Analizador de Inversiones",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
  /* Fondo general */
  [data-testid="stAppViewContainer"] { background:#0f172a; }
  [data-testid="stSidebar"]          { background:#1e293b; border-right:1px solid #334155; }
  .block-container { padding-top:1.2rem; padding-bottom:2rem; }

  /* Tarjetas de métricas */
  div[data-testid="metric-container"] {
    background:#1e293b;
    border:1px solid #334155;
    border-radius:10px;
    padding:14px 18px;
  }

  /* Texto general */
  h1,h2,h3,h4 { color:#e2e8f0 !important; }
  p, label, .stMarkdown, .stCaption { color:#cbd5e1; }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] {
    background:#1e293b;
    border-radius:10px;
    padding:4px;
    gap:4px;
  }
  .stTabs [data-baseweb="tab"] {
    border-radius:8px;
    color:#94a3b8;
    padding:8px 16px;
  }
  .stTabs [aria-selected="true"] {
    background:#6366f1 !important;
    color:white !important;
  }

  /* Tablas */
  .stDataFrame { border-radius:8px; overflow:hidden; }
  thead tr th { background:#1e3a5f !important; color:#e2e8f0 !important; }

  /* Separador */
  hr { border-color:#334155; }

  /* Expander */
  .stExpander { background:#1e293b; border:1px solid #334155; border-radius:8px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
#  CATÁLOGOS
# ─────────────────────────────────────────────────────────────
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
                "profit","strong","boost","beat","sube","alza","gana","crecimiento","positivo"]
PALABRAS_NEG = ["crash","fall","drop","loss","bear","recession","fear","selloff",
                "decline","weak","risk","tariff","war","crisis","baja","cae","pérdida","negativo"]

TELEGRAM_TOKEN   = "8362312296:AAFr9lR1ad775g8p_OxuSvz9nYMMAitcCFk"
TELEGRAM_CHAT_ID = "5858053994"
COLORES = ["#6366f1","#10b981","#f59e0b","#ef4444","#8b5cf6","#06b6d4","#f43f5e","#84cc16"]

# ─────────────────────────────────────────────────────────────
#  FUNCIONES
# ─────────────────────────────────────────────────────────────
def esc(t):
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def tema_grafica():
    return dict(
        plot_bgcolor="#0f172a",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0", family="Arial"),
        hovermode="x unified",
        margin=dict(t=30, b=40, l=60, r=20),
    )

@st.cache_data(ttl=3600, show_spinner=False)
def descargar(tickers_dict, f_ini, f_fin):
    datos = {}
    for nombre, ticker in tickers_dict.items():
        try:
            df = yf.download(ticker, start=f_ini, end=f_fin, progress=False)
            if not df.empty:
                datos[nombre] = df["Close"].squeeze()
        except: pass
    return pd.DataFrame(datos).dropna(how="all")

@st.cache_data(ttl=1800, show_spinner=False)
def obtener_noticias():
    titulares, scores = [], []
    for nombre, url in FUENTES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                titulo = entry.get("title","")
                if not titulo: continue
                s  = TextBlob(titulo).sentiment.polarity
                tl = titulo.lower()
                s += sum(0.15 for p in PALABRAS_POS if p in tl)
                s -= sum(0.15 for p in PALABRAS_NEG if p in tl)
                s  = max(-1, min(1, s))
                titulares.append((s, titulo, nombre))
                scores.append(s)
        except: pass
    return (float(np.mean(scores)) if scores else 0), sorted(titulares, reverse=True)

def backtest(precio, ma_r, ma_l, capital_ini, sl_pct, trailing):
    mar = precio.rolling(ma_r).mean()
    mal = precio.rolling(ma_l).mean()
    cap = float(capital_ini)
    en_mkt = False
    pc = pmax = 0.0
    ops, hist = [], []
    señal = (mar > mal).astype(int)
    prev  = señal.shift(1)
    for fecha, pa in precio.items():
        pa = float(pa)
        if pd.isna(pa): hist.append(cap); continue
        razon = None
        if en_mkt:
            pmax  = max(pmax, pa) if trailing else pmax
            stop  = (pmax if trailing else pc) * (1 - sl_pct)
            if pa <= stop: razon = "Stop-Loss"
            elif señal.get(fecha,1)==0 and prev.get(fecha,1)==1: razon = "Death Cross"
        if razon and en_mkt:
            g = (pa-pc)/pc*100; cap = cap*(pa/pc)
            ops.append({"tipo":"VENTA","fecha":fecha,"precio":pa,"gan":g,"capital":cap,"razon":razon})
            en_mkt = False
        if not en_mkt and señal.get(fecha,0)==1 and prev.get(fecha,0)==0:
            en_mkt = True; pc = pa; pmax = pa
            ops.append({"tipo":"COMPRA","fecha":fecha,"precio":pa,"capital":cap})
        hist.append(cap*(pa/pc) if en_mkt else cap)
    if en_mkt: cap = cap*(float(precio.iloc[-1])/pc)
    ventas = [o for o in ops if o["tipo"]=="VENTA"]
    total  = len(ventas)
    ganad  = sum(1 for o in ventas if o["gan"]>0)
    wr     = ganad/total*100 if total>0 else 0
    rend   = (cap-capital_ini)/capital_ini*100
    bh     = capital_ini*(float(precio.iloc[-1])/float(precio.iloc[0]))
    rend_bh= (bh-capital_ini)/capital_ini*100
    cs     = pd.Series(hist)
    dd     = ((cs-cs.cummax())/cs.cummax()*100).min()
    return dict(cap=cap,bh=bh,rend=rend,rend_bh=rend_bh,total=total,ganad=ganad,
                wr=wr,dd=dd,ops=ops,hist=hist,mar=mar,mal=mal)

def proyeccion_montecarlo(precio, dias=90, sims=500):
    ret = precio.pct_change().dropna()
    mu, sigma = ret.mean(), ret.std()
    p0 = float(precio.iloc[-1])
    np.random.seed(42)
    resultados = np.zeros((sims, dias))
    for i in range(sims):
        r = np.random.normal(mu, sigma, dias)
        serie = [p0]
        for ri in r: serie.append(serie[-1]*(1+ri))
        resultados[i] = serie[1:]
    fechas = pd.date_range(start=precio.index[-1]+timedelta(days=1), periods=dias, freq="B")
    return fechas, *[np.percentile(resultados,p,axis=0) for p in [10,25,50,75,90]], p0

def enviar_telegram(msg, silencioso=False):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id":TELEGRAM_CHAT_ID,"text":msg,
                  "parse_mode":"HTML","disable_notification":silencioso},
            timeout=10)
        return r.status_code==200
    except: return False

# ─────────────────────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuración")
    st.markdown("---")

    st.markdown("**📅 Período**")
    años_hist = st.slider("Historial (años)", 1, 10, 3)
    años_bt   = st.slider("Backtesting (años)", 1, 10, 5)
    dias_proy = st.slider("Proyección (días)", 30, 180, 90)

    st.markdown("---")
    st.markdown("**💰 Capital inicial**")
    capital_ini = st.number_input("Monto ($)", 1000, 10_000_000, 10_000, step=1000)
    st.caption("Usa pesos MXN o dólares USD según el activo")

    st.markdown("---")
    st.markdown("**🌎 Mercados globales**")
    sel_glob = st.multiselect("Activos", list(ACTIVOS_GLOBALES.keys()),
        default=["S&P 500 (ETF)","Nasdaq (ETF)","Oro (ETF)","Bitcoin"])

    st.markdown("**🇲🇽 Bolsa Mexicana (BMV)**")
    sel_bmv = st.multiselect("Acciones MX", list(ACTIVOS_BMV.keys()),
        default=["América Móvil","FEMSA","Walmart México"])

    st.markdown("---")
    st.markdown("**🔬 Parámetros de estrategia**")
    ma_r  = st.selectbox("Media móvil rápida (días)", [5,10,20,50], index=1)
    ma_l  = st.selectbox("Media móvil lenta (días)",  [20,50,100,200], index=1)
    sl    = st.slider("Stop-loss (%)", 3, 20, 8) / 100
    trail = st.toggle("Trailing stop", value=True)

    todos_lista = sel_glob + sel_bmv
    act_bt = st.selectbox("Activo principal a analizar",
                           todos_lista if todos_lista else ["S&P 500 (ETF)"])
    st.markdown("---")
    btn_tg = st.button("📲 Enviar reporte a Telegram", use_container_width=True, type="primary")

# ─────────────────────────────────────────────────────────────
#  CARGA DE DATOS
# ─────────────────────────────────────────────────────────────
f_ini = (datetime.today()-timedelta(days=365*años_hist)).strftime("%Y-%m-%d")
f_fin = datetime.today().strftime("%Y-%m-%d")
f_bt  = (datetime.today()-timedelta(days=365*años_bt)).strftime("%Y-%m-%d")

todos_activos = {**{k:ACTIVOS_GLOBALES[k] for k in sel_glob},
                 **{k:ACTIVOS_BMV[k]      for k in sel_bmv}}

# ─────────────────────────────────────────────────────────────
#  ENCABEZADO
# ─────────────────────────────────────────────────────────────
c1, c2 = st.columns([4,1])
with c1: st.title("📊 Analizador de Inversiones")
with c2: st.caption(f"v4.2 · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

if not todos_activos:
    st.info("👈 Selecciona activos en el panel izquierdo para comenzar.")
    st.stop()

# ─────────────────────────────────────────────────────────────
#  TABS
# ─────────────────────────────────────────────────────────────
tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs([
    "📈 Rendimiento",
    "🔬 Backtesting",
    "🔮 Proyección",
    "📰 Noticias y Señal",
    "⚡ Estrategias Avanzadas",
    "🧮 Portafolio Óptimo",
])

# ══════════════════════════════════════════════════════════════
#  TAB 1 — RENDIMIENTO
# ══════════════════════════════════════════════════════════════
with tab1:
    with st.spinner("Descargando datos..."):
        precios = descargar(todos_activos, f_ini, f_fin)

    if precios.empty:
        st.error("No se pudieron descargar datos. Verifica tu conexión.")
        st.stop()

    rendimiento = (precios / precios.iloc[0]) * 100
    resumen = []
    for col in precios.columns:
        s = precios[col].dropna()
        if len(s) < 2: continue
        ret = ((s.iloc[-1]-s.iloc[0])/s.iloc[0])*100
        vol = s.pct_change().dropna().std()*(252**0.5)*100
        vf  = capital_ini*(s.iloc[-1]/s.iloc[0])
        resumen.append((col, float(s.iloc[-1]), ret, vol, vf, vf-capital_ini))

    # Métricas
    cols_m = st.columns(min(len(resumen), 5))
    for i,(col,ph,ret,vol,vf,gan) in enumerate(resumen):
        with cols_m[i%5]:
            st.metric(col, f"${ph:,.2f}", f"{ret:+.1f}%",
                      delta_color="normal" if ret>=0 else "inverse")

    st.markdown("---")

    # Gráfica rendimiento
    st.markdown("#### Rendimiento comparativo (%)")
    fig1 = go.Figure()
    for i,col in enumerate(rendimiento.columns):
        s = rendimiento[col].dropna()
        fig1.add_trace(go.Scatter(x=s.index, y=s-100, name=col,
            line=dict(color=COLORES[i%len(COLORES)],width=2.5),
            hovertemplate=f"<b>{col}</b> · %{{x|%d %b %Y}}: <b>%{{y:+.1f}}%</b><extra></extra>"))
    fig1.add_hline(y=0, line_dash="dash", line_color="#475569", opacity=0.5)
    fig1.update_layout(**tema_grafica(), height=380,
        legend=dict(bgcolor="rgba(15,23,42,0.9)",bordercolor="#334155",
                    orientation="h",yanchor="bottom",y=1.02),
        yaxis=dict(title="Rendimiento (%)",gridcolor="#1e3a5f"),
        xaxis=dict(gridcolor="#1e293b"))
    st.plotly_chart(fig1, use_container_width=True)

    # Tabla simulación
    st.markdown("#### Simulación de inversión")
    filas = []
    for col,ph,ret,vol,vf,gan in resumen:
        filas.append({
            "Activo"         : col,
            "Mercado"        : "🇲🇽 BMV" if col in sel_bmv else "🌎 Global",
            "Precio actual"  : f"${ph:,.2f}",
            "Rendimiento"    : f"{ret:+.1f}%",
            "Riesgo anual"   : f"{vol:.1f}%",
            f"${capital_ini:,.0f} invertidos": f"${vf:,.0f}",
            "Ganancia/Pérd." : f"${gan:+,.0f}",
        })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    # BMV separada
    if sel_bmv:
        st.markdown("---")
        st.markdown("#### 🇲🇽 Acciones mexicanas (BMV)")
        p_bmv = precios[[c for c in precios.columns if c in sel_bmv]]
        if not p_bmv.empty:
            r_bmv = (p_bmv/p_bmv.iloc[0])*100
            fig_bmv = go.Figure()
            for i,col in enumerate(r_bmv.columns):
                s = r_bmv[col].dropna()
                fig_bmv.add_trace(go.Scatter(x=s.index,y=s-100,name=col,
                    line=dict(color=COLORES[i%len(COLORES)],width=2.5),
                    hovertemplate=f"<b>{col}</b> · %{{x|%d %b %Y}}: <b>%{{y:+.1f}}%</b><extra></extra>"))
            fig_bmv.add_hline(y=0,line_dash="dash",line_color="#475569",opacity=0.5)
            fig_bmv.update_layout(**tema_grafica(), height=320,
                legend=dict(bgcolor="rgba(15,23,42,0.9)",bordercolor="#334155",
                            orientation="h",yanchor="bottom",y=1.02),
                yaxis=dict(gridcolor="#1e3a5f"),xaxis=dict(gridcolor="#1e293b"))
            st.plotly_chart(fig_bmv, use_container_width=True)

            bmv_ren = [(col,ret) for col,_,ret,_,_,_ in resumen if col in sel_bmv]
            if bmv_ren:
                mejor_mx = max(bmv_ren,key=lambda x:x[1])
                peor_mx  = min(bmv_ren,key=lambda x:x[1])
                c1,c2 = st.columns(2)
                with c1: st.success(f"🏆 Mejor: **{mejor_mx[0]}** → {mejor_mx[1]:+.1f}%")
                with c2: st.error(f"📉 Peor: **{peor_mx[0]}** → {peor_mx[1]:+.1f}%")

# ══════════════════════════════════════════════════════════════
#  TAB 2 — BACKTESTING
# ══════════════════════════════════════════════════════════════
with tab2:
    ticker_bt = todos_activos.get(act_bt)
    if not ticker_bt:
        st.info("Selecciona un activo en el panel izquierdo.")
    else:
        with st.spinner(f"Calculando backtesting de {act_bt}..."):
            df_bt     = yf.download(ticker_bt, start=f_bt, end=f_fin, progress=False)
            precio_bt = df_bt["Close"].squeeze() if not df_bt.empty else pd.Series()

        if precio_bt.empty or len(precio_bt)<ma_l+10:
            st.warning("Datos insuficientes. Reduce la media lenta o amplía el período.")
        else:
            bt = backtest(precio_bt, ma_r, ma_l, capital_ini, sl, trail)
            ventaja = bt["rend"]-bt["rend_bh"]

            st.markdown(f"#### Estrategia MA{ma_r}/MA{ma_l} · {act_bt} · {años_bt} años · Stop-loss {sl*100:.0f}%")
            c1,c2,c3,c4 = st.columns(4)
            with c1: st.metric("Capital (estrategia)", f"${bt['cap']:,.0f}", f"{bt['rend']:+.1f}%")
            with c2: st.metric("Capital (buy & hold)", f"${bt['bh']:,.0f}",  f"{bt['rend_bh']:+.1f}%")
            with c3: st.metric("Tasa de éxito",        f"{bt['wr']:.1f}%",   f"{bt['ganad']}/{bt['total']} ops")
            with c4: st.metric("Máx. caída",           f"{bt['dd']:.1f}%",   delta_color="off")

            if ventaja>0:
                st.success(f"✅ La estrategia superó al Buy & Hold por **${bt['cap']-bt['bh']:,.0f}** ({ventaja:+.1f}%)")
            else:
                st.warning(f"⚠️ Buy & Hold fue mejor por **${bt['bh']-bt['cap']:,.0f}**. En mercados alcistas es lo más común.")

            # Gráfica backtesting
            fig_bt = make_subplots(rows=2,cols=1,shared_xaxes=True,
                subplot_titles=("Precio + medias móviles + señales","Capital: Estrategia vs Buy & Hold"),
                vertical_spacing=0.1, row_heights=[0.55,0.45])

            fig_bt.add_trace(go.Scatter(x=precio_bt.index,y=precio_bt,name="Precio",
                line=dict(color="#94a3b8",width=1.2)),row=1,col=1)
            fig_bt.add_trace(go.Scatter(x=bt["mar"].index,y=bt["mar"],
                name=f"MA{ma_r}d",line=dict(color="#10b981",width=1.8,dash="dot")),row=1,col=1)
            fig_bt.add_trace(go.Scatter(x=bt["mal"].index,y=bt["mal"],
                name=f"MA{ma_l}d",line=dict(color="#ef4444",width=1.8,dash="dash")),row=1,col=1)

            compras = [o for o in bt["ops"] if o["tipo"]=="COMPRA"]
            cruces  = [o for o in bt["ops"] if o["tipo"]=="VENTA" and o.get("razon")=="Death Cross"]
            stops   = [o for o in bt["ops"] if o["tipo"]=="VENTA" and o.get("razon")=="Stop-Loss"]

            if compras:
                fig_bt.add_trace(go.Scatter(x=[o["fecha"] for o in compras],
                    y=[o["precio"] for o in compras],mode="markers",name="🟢 Compra",
                    marker=dict(color="#10b981",size=11,symbol="triangle-up",
                                line=dict(color="white",width=1))),row=1,col=1)
            if cruces:
                fig_bt.add_trace(go.Scatter(x=[o["fecha"] for o in cruces],
                    y=[o["precio"] for o in cruces],mode="markers",name="🔴 Venta",
                    marker=dict(color="#ef4444",size=11,symbol="triangle-down",
                                line=dict(color="white",width=1))),row=1,col=1)
            if stops:
                fig_bt.add_trace(go.Scatter(x=[o["fecha"] for o in stops],
                    y=[o["precio"] for o in stops],mode="markers",name="⚠️ Stop-Loss",
                    marker=dict(color="#f59e0b",size=13,symbol="x",
                                line=dict(color="white",width=2))),row=1,col=1)

            cap_s = pd.Series(bt["hist"],index=precio_bt.index[:len(bt["hist"])])
            bh_s  = (precio_bt/float(precio_bt.iloc[0]))*capital_ini
            fig_bt.add_trace(go.Scatter(x=cap_s.index,y=cap_s,name="Estrategia",
                line=dict(color="#6366f1",width=2.5),
                fill="tozeroy",fillcolor="rgba(99,102,241,0.08)"),row=2,col=1)
            fig_bt.add_trace(go.Scatter(x=bh_s.index,y=bh_s,name="Buy & Hold",
                line=dict(color="#f59e0b",width=2,dash="dot"),
                fill="tozeroy",fillcolor="rgba(245,158,11,0.05)"),row=2,col=1)

            fig_bt.update_layout(**tema_grafica(), height=620,
                legend=dict(bgcolor="rgba(15,23,42,0.9)",bordercolor="#334155",
                            orientation="h",yanchor="bottom",y=1.02))
            fig_bt.update_xaxes(gridcolor="#1e293b")
            fig_bt.update_yaxes(gridcolor="#1e3a5f")
            st.plotly_chart(fig_bt, use_container_width=True)

            with st.expander("📋 Historial de operaciones"):
                filas_ops = []
                for o in bt["ops"]:
                    fs = o["fecha"].strftime("%d/%m/%Y") if hasattr(o["fecha"],"strftime") else str(o["fecha"])[:10]
                    if o["tipo"]=="COMPRA":
                        filas_ops.append({"Fecha":fs,"Tipo":"🟢 COMPRA","Precio":f"${o['precio']:,.2f}",
                                          "Ganancia":"—","Capital":f"${o['capital']:,.0f}","Razón":"Golden Cross"})
                    else:
                        filas_ops.append({"Fecha":fs,"Tipo":"🔴 VENTA","Precio":f"${o['precio']:,.2f}",
                                          "Ganancia":f"{o['gan']:+.1f}%","Capital":f"${o['capital']:,.0f}",
                                          "Razón":o.get("razon","—")})
                st.dataframe(pd.DataFrame(filas_ops), use_container_width=True, hide_index=True)

            with st.expander("❓ ¿Cómo leer esta gráfica?"):
                st.markdown(f"""
**Panel superior:**
- Línea **gris** = precio real del activo
- Línea **verde punteada** = media de los últimos {ma_r} días
- Línea **roja discontinua** = media de los últimos {ma_l} días
- 🟢 **Triángulo verde** = señal de compra (media rápida cruza arriba de la lenta)
- 🔴 **Triángulo rojo** = señal de venta (cruce inverso)
- ⚠️ **X amarilla** = stop-loss activado (precio cayó {sl*100:.0f}% desde el máximo)

**Panel inferior:**
- **Morado** = tu capital siguiendo la estrategia
- **Amarillo** = capital si hubieras comprado y no tocado nada (Buy & Hold)
                """)

# ══════════════════════════════════════════════════════════════
#  TAB 3 — PROYECCIÓN
# ══════════════════════════════════════════════════════════════
with tab3:
    ticker_proy = todos_activos.get(act_bt)
    if ticker_proy:
        with st.spinner("Calculando proyección estadística..."):
            df_p     = yf.download(ticker_proy, start=f_ini, end=f_fin, progress=False)
            precio_p = df_p["Close"].squeeze() if not df_p.empty else pd.Series()
    else:
        precio_p = pd.Series()

    if precio_p.empty:
        st.warning("Sin datos para proyectar.")
    else:
        st.markdown(f"#### 🔮 Proyección estadística · {act_bt} · próximos {dias_proy} días hábiles")
        st.info("**¿Qué es esto?** Se simulan 500 escenarios basados en el comportamiento histórico del activo. No predice el precio exacto — muestra un rango de posibilidades.")

        fechas_fut,p10,p25,p50,p75,p90,p0 = proyeccion_montecarlo(precio_p,dias_proy)

        c1,c2,c3,c4 = st.columns(4)
        with c1: st.metric("Precio actual",          f"${p0:,.2f}")
        with c2: st.metric("Escenario base",         f"${p50[-1]:,.2f}", f"{((p50[-1]-p0)/p0)*100:+.1f}%")
        with c3: st.metric("Optimista (90%)",        f"${p90[-1]:,.2f}", f"{((p90[-1]-p0)/p0)*100:+.1f}%", delta_color="normal")
        with c4: st.metric("Pesimista (10%)",        f"${p10[-1]:,.2f}", f"{((p10[-1]-p0)/p0)*100:+.1f}%", delta_color="inverse")

        fig_p = go.Figure()
        hist_rec = precio_p.iloc[-126:]
        fig_p.add_trace(go.Scatter(x=hist_rec.index,y=hist_rec,name="Historial real",
            line=dict(color="#94a3b8",width=2)))
        fig_p.add_trace(go.Scatter(
            x=list(fechas_fut)+list(fechas_fut[::-1]),
            y=list(p90)+list(p10[::-1]),
            fill="toself",fillcolor="rgba(99,102,241,0.07)",
            line=dict(color="rgba(0,0,0,0)"),name="Rango 10%-90%",hoverinfo="skip"))
        fig_p.add_trace(go.Scatter(
            x=list(fechas_fut)+list(fechas_fut[::-1]),
            y=list(p75)+list(p25[::-1]),
            fill="toself",fillcolor="rgba(99,102,241,0.16)",
            line=dict(color="rgba(0,0,0,0)"),name="Rango 25%-75%",hoverinfo="skip"))
        for vals,nombre,color,dash in [
            (p90,"Optimista (90%)","#10b981","dot"),
            (p50,"Base (mediana)","#6366f1","solid"),
            (p10,"Pesimista (10%)","#ef4444","dot"),
        ]:
            fig_p.add_trace(go.Scatter(x=fechas_fut,y=vals,name=nombre,
                line=dict(color=color,width=2 if "Base" in nombre else 1.5,dash=dash),
                hovertemplate=f"<b>{nombre}</b><br>%{{x|%d %b %Y}}: $%{{y:,.2f}}<extra></extra>"))

        fecha_hoy_str = str(precio_p.index[-1].date())
        fig_p.add_shape(type="line",x0=fecha_hoy_str,x1=fecha_hoy_str,
            y0=0,y1=1,yref="paper",line=dict(color="#475569",width=1.5,dash="dash"))
        fig_p.add_annotation(x=fecha_hoy_str,y=1,yref="paper",text="Hoy",
            showarrow=False,font=dict(color="#94a3b8",size=11),yanchor="bottom")

        fig_p.update_layout(**tema_grafica(), height=460,
            legend=dict(bgcolor="rgba(15,23,42,0.9)",bordercolor="#334155",
                        orientation="h",yanchor="bottom",y=1.02),
            yaxis=dict(title="Precio ($)",gridcolor="#1e3a5f"),
            xaxis=dict(gridcolor="#1e293b"))
        st.plotly_chart(fig_p, use_container_width=True)

        st.markdown("#### Simulación en cada escenario")
        c1,c2,c3 = st.columns(3)
        for col_ui,escenario,pf,dc in [
            (c1,"📉 Pesimista",p10[-1],"inverse"),
            (c2,"⚖️ Base",p50[-1],"off"),
            (c3,"📈 Optimista",p90[-1],"normal"),
        ]:
            vf = capital_ini*(pf/p0)
            with col_ui: st.metric(escenario,f"${vf:,.0f}",f"${vf-capital_ini:+,.0f}",delta_color=dc)

        with st.expander("❓ ¿Cómo leer la proyección?"):
            st.markdown("""
- **Zona oscura (25%-75%):** el precio caerá aquí en ~50% de los escenarios.
- **Zona clara (10%-90%):** el precio caerá aquí en ~80% de los escenarios.
- 🟢 **Optimista:** solo el 10% de escenarios fueron mejores que este.
- 🟣 **Base:** el camino más probable según el historial.
- 🔴 **Pesimista:** solo el 10% de escenarios fueron peores que este.
- ⚠️ Esto NO garantiza nada. Los mercados pueden sorprender.
            """)

# ══════════════════════════════════════════════════════════════
#  TAB 4 — NOTICIAS Y SEÑAL
# ══════════════════════════════════════════════════════════════
with tab4:
    with st.spinner("Analizando noticias..."):
        score_sent, noticias = obtener_noticias()

    pos = sum(1 for s,_,_ in noticias if s>0.05)
    neg = sum(1 for s,_,_ in noticias if s<-0.05)
    neu = len(noticias)-pos-neg

    st.markdown("#### 📰 Sentimiento del mercado — noticias en tiempo real")
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.metric("Score general",f"{score_sent:+.3f}",
                        "🟢 Positivo" if score_sent>0.1 else ("🔴 Negativo" if score_sent<-0.1 else "🟡 Neutro"),
                        delta_color="normal" if score_sent>0.1 else ("inverse" if score_sent<-0.1 else "off"))
    with c2: st.metric("Positivas",str(pos))
    with c3: st.metric("Neutras",str(neu))
    with c4: st.metric("Negativas",str(neg),delta_color="inverse")

    if noticias:
        c_pos,c_neg = st.columns(2)
        with c_pos:
            st.markdown("**📈 Noticias más positivas**")
            for score,titulo,fuente in [x for x in noticias if x[0]>0.05][:5]:
                st.success(f"[{score:+.2f}] {titulo[:85]}")
        with c_neg:
            st.markdown("**📉 Noticias más negativas**")
            for score,titulo,fuente in [x for x in reversed(noticias) if x[0]<-0.05][:5]:
                st.error(f"[{score:+.2f}] {titulo[:85]}")

    st.markdown("---")
    st.markdown("#### 🎯 Señal combinada del día")

    señal_tec = 0
    score_comb = 0.0
    señal_nom = ""
    if ticker_bt and not precio_bt.empty and len(precio_bt)>ma_l+10:
        bt_s = backtest(precio_bt, ma_r, ma_l, capital_ini, sl, trail)
        señal_tec = 1 if bt_s["mar"].iloc[-1]>bt_s["mal"].iloc[-1] else -1
        señal_nom = "COMPRA — MA rápida > MA lenta" if señal_tec==1 else "VENTA — MA rápida < MA lenta"
        score_comb= señal_tec*0.6 + score_sent*0.4

        c1,c2,c3 = st.columns(3)
        with c1: st.metric("Señal técnica","COMPRA 📈" if señal_tec==1 else "VENTA 📉",
                            f"MA{ma_r} vs MA{ma_l}",
                            delta_color="normal" if señal_tec==1 else "inverse")
        with c2: st.metric("Sentimiento noticias",f"{score_sent:+.3f}",
                            "🟢 Favorable" if score_sent>0.1 else ("🔴 Adverso" if score_sent<-0.1 else "🟡 Neutro"))
        with c3: st.metric("Score combinado",f"{score_comb:+.3f}","60% técnico + 40% noticias",delta_color="off")

        st.markdown("")
        if score_comb>0.2:
            st.success("## 🟢 CONDICIONES FAVORABLES\nTendencia positiva con noticias favorables. Momento potencialmente bueno para considerar entrar.")
        elif score_comb<-0.2:
            st.error("## 🔴 CONDICIONES DESFAVORABLES\nSeñal negativa. Considera reducir exposición o esperar un mejor momento.")
        else:
            st.warning("## 🟡 SEÑAL MIXTA — MANTENER\nSin tendencia clara. Evita decisiones impulsivas.")

        st.caption("⚠️ Análisis educativo. No garantiza rendimientos ni constituye consejo financiero.")

    if btn_tg:
        with st.spinner("Enviando a Telegram..."):
            fecha_hoy = datetime.today().strftime("%d/%m/%Y %H:%M")
            alerta    = score_comb < -0.2
            msg1 = f"📊 <b>REPORTE {esc(fecha_hoy)}</b>\n\n<b>Rendimiento {años_hist} años</b>\n"
            for col,ph,ret,vol,vf,gan in resumen:
                msg1 += f"{'📈' if ret>0 else '📉'} {esc(col)}: <b>{ret:+.1f}%</b>\n"
            msg2 = f"💵 <b>Simulación ${capital_ini:,.0f}</b>\n\n"
            for col,ph,ret,vol,vf,gan in resumen:
                msg2 += f"{'🟢' if gan>0 else '🔴'} {esc(col)}: <b>${vf:,.0f}</b> ({gan:+,.0f})\n"
            sent_e = "🟢" if score_sent>0.1 else ("🔴" if score_sent<-0.1 else "🟡")
            dec    = "🟢 FAVORABLES" if score_comb>0.2 else ("🔴 DESFAVORABLES" if score_comb<-0.2 else "🟡 MIXTA")
            msg3   = (f"🎯 <b>SEÑAL DEL DÍA</b>\n\n"
                      f"{'📈' if señal_tec==1 else '📉'} Técnica: {esc(señal_nom)}\n"
                      f"{sent_e} Sentimiento: {score_sent:+.3f}\n"
                      f"Score: <b>{score_comb:+.3f}</b>\n\n"
                      f"<b>{esc(dec)}</b>\n\n⚠️ <i>Solo análisis educativo</i>")
            ok = all([enviar_telegram(msg1),enviar_telegram(msg2),
                      enviar_telegram(msg3,silencioso=not alerta)])
            if ok: st.success("✅ Reporte enviado a Telegram")
            else:  st.error("⚠️ Error al enviar. Revisa tu conexión.")

# ══════════════════════════════════════════════════════════════
#  TAB 5 — ESTRATEGIAS AVANZADAS
# ══════════════════════════════════════════════════════════════
with tab5:
    st.markdown("#### ⚡ Estrategias Avanzadas — RSI y Bandas de Bollinger")
    st.info("Las medias móviles rara vez superan al Buy & Hold en mercados alcistas. RSI y Bollinger detectan mejor los momentos de sobrecompra/sobreventa, especialmente en activos volátiles.")

    c1,c2,c3 = st.columns(3)
    with c1:
        activo_adv  = st.selectbox("Activo",list(todos_activos.keys()),key="adv_act")
        capital_adv = st.number_input("Capital ($)",1000,10_000_000,capital_ini,key="adv_cap")
        años_adv    = st.slider("Años de backtest",1,10,5,key="adv_años")
    with c2:
        estrategia     = st.selectbox("Estrategia",[
            "RSI — Sobrecompra/Sobreventa",
            "Bandas de Bollinger",
            "RSI + Bollinger combinados"])
        rsi_periodo    = st.slider("Período RSI",7,30,14)
        rsi_sobrecompra= st.slider("RSI sobrecompra",60,90,70)
        rsi_sobreventa = st.slider("RSI sobreventa",10,40,30)
    with c3:
        bb_periodo = st.slider("Período Bollinger",10,50,20)
        bb_desv    = st.slider("Desv. estándar BB",1.0,3.0,2.0,step=0.1)

    ticker_adv = todos_activos.get(activo_adv)
    with st.spinner("Calculando..."):
        f_adv  = (datetime.today()-timedelta(days=365*años_adv)).strftime("%Y-%m-%d")
        df_adv = yf.download(ticker_adv,start=f_adv,end=f_fin,progress=False)
        precio_adv = df_adv["Close"].squeeze() if not df_adv.empty else pd.Series()

    if precio_adv.empty:
        st.warning("Sin datos.")
    else:
        delta    = precio_adv.diff()
        ganancia = delta.clip(lower=0).rolling(rsi_periodo).mean()
        perdida  = (-delta.clip(upper=0)).rolling(rsi_periodo).mean()
        rs       = ganancia/perdida
        rsi      = 100-(100/(1+rs))

        bb_media = precio_adv.rolling(bb_periodo).mean()
        bb_std   = precio_adv.rolling(bb_periodo).std()
        bb_sup   = bb_media+bb_desv*bb_std
        bb_inf   = bb_media-bb_desv*bb_std

        capital = float(capital_adv)
        en_mkt  = False
        pc      = 0.0
        ops_adv = []
        hist_adv= []

        for i,(fecha,pa) in enumerate(precio_adv.items()):
            pa = float(pa)
            if pd.isna(pa) or i<bb_periodo: hist_adv.append(capital); continue
            r  = float(rsi.iloc[i])   if not pd.isna(rsi.iloc[i])    else 50
            bs = float(bb_sup.iloc[i]) if not pd.isna(bb_sup.iloc[i]) else pa*1.05
            bi = float(bb_inf.iloc[i]) if not pd.isna(bb_inf.iloc[i]) else pa*0.95

            sc = False; sv = False
            if   estrategia=="RSI — Sobrecompra/Sobreventa":
                sc = r<rsi_sobreventa; sv = r>rsi_sobrecompra
            elif estrategia=="Bandas de Bollinger":
                sc = pa<bi; sv = pa>bs
            else:
                sc = (r<rsi_sobreventa) and (pa<bi)
                sv = (r>rsi_sobrecompra) or (pa>bs)

            if sc and not en_mkt:
                en_mkt=True; pc=pa
                ops_adv.append({"tipo":"COMPRA","fecha":fecha,"precio":pa,"capital":capital})
            elif sv and en_mkt:
                g=((pa-pc)/pc)*100; capital=capital*(pa/pc); en_mkt=False
                ops_adv.append({"tipo":"VENTA","fecha":fecha,"precio":pa,"gan":g,"capital":capital})
            hist_adv.append(capital*(pa/pc) if en_mkt else capital)

        if en_mkt: capital=capital*(float(precio_adv.iloc[-1])/pc)

        ventas_adv  = [o for o in ops_adv if o["tipo"]=="VENTA"]
        total_adv   = len(ventas_adv)
        ganad_adv   = sum(1 for o in ventas_adv if o["gan"]>0)
        wr_adv      = ganad_adv/total_adv*100 if total_adv>0 else 0
        rend_adv    = (capital-capital_adv)/capital_adv*100
        bh_adv      = capital_adv*(float(precio_adv.iloc[-1])/float(precio_adv.iloc[0]))
        rend_bh_adv = (bh_adv-capital_adv)/capital_adv*100
        ventaja_adv = rend_adv-rend_bh_adv

        c1,c2,c3,c4 = st.columns(4)
        with c1: st.metric("Capital (estrategia)",f"${capital:,.0f}",f"{rend_adv:+.1f}%")
        with c2: st.metric("Capital (buy & hold)",f"${bh_adv:,.0f}",f"{rend_bh_adv:+.1f}%")
        with c3: st.metric("Tasa de éxito",f"{wr_adv:.1f}%",f"{ganad_adv}/{total_adv} ops")
        with c4: st.metric("Ventaja vs B&H",f"{ventaja_adv:+.1f}%",
                            "✅ Estrategia ganó" if ventaja_adv>0 else "⚠️ B&H fue mejor",
                            delta_color="normal" if ventaja_adv>0 else "inverse")

        if ventaja_adv>0:
            st.success(f"✅ **{estrategia}** superó al Buy & Hold por **${capital-bh_adv:,.0f}** ({ventaja_adv:+.1f}%)")
        else:
            st.warning(f"⚠️ Buy & Hold fue mejor. Ajusta los parámetros y prueba de nuevo.")

        fig_adv = make_subplots(rows=3,cols=1,shared_xaxes=True,
            subplot_titles=("Precio + Bandas de Bollinger","RSI","Capital: Estrategia vs Buy & Hold"),
            vertical_spacing=0.06,row_heights=[0.45,0.22,0.33])

        fig_adv.add_trace(go.Scatter(x=precio_adv.index,y=precio_adv,name="Precio",
            line=dict(color="#94a3b8",width=1.5)),row=1,col=1)
        fig_adv.add_trace(go.Scatter(x=bb_sup.index,y=bb_sup,name="Banda superior",
            line=dict(color="#6366f1",width=1.2,dash="dot")),row=1,col=1)
        fig_adv.add_trace(go.Scatter(x=bb_inf.index,y=bb_inf,name="Banda inferior",
            line=dict(color="#6366f1",width=1.2,dash="dot"),
            fill="tonexty",fillcolor="rgba(99,102,241,0.06)"),row=1,col=1)
        fig_adv.add_trace(go.Scatter(x=bb_media.index,y=bb_media,name="Media BB",
            line=dict(color="#475569",width=1,dash="dash")),row=1,col=1)

        comp_adv = [o for o in ops_adv if o["tipo"]=="COMPRA"]
        vent_adv = [o for o in ops_adv if o["tipo"]=="VENTA"]
        if comp_adv:
            fig_adv.add_trace(go.Scatter(x=[o["fecha"] for o in comp_adv],
                y=[o["precio"] for o in comp_adv],mode="markers",name="🟢 Compra",
                marker=dict(color="#10b981",size=10,symbol="triangle-up",
                            line=dict(color="white",width=1))),row=1,col=1)
        if vent_adv:
            fig_adv.add_trace(go.Scatter(x=[o["fecha"] for o in vent_adv],
                y=[o["precio"] for o in vent_adv],mode="markers",name="🔴 Venta",
                marker=dict(color="#ef4444",size=10,symbol="triangle-down",
                            line=dict(color="white",width=1))),row=1,col=1)

        fig_adv.add_trace(go.Scatter(x=rsi.index,y=rsi,name="RSI",
            line=dict(color="#f59e0b",width=2)),row=2,col=1)
        fig_adv.add_hrect(y0=rsi_sobrecompra,y1=100,
            fillcolor="rgba(239,68,68,0.10)",line_width=0,row=2,col=1)
        fig_adv.add_hrect(y0=0,y1=rsi_sobreventa,
            fillcolor="rgba(16,185,129,0.10)",line_width=0,row=2,col=1)
        fig_adv.add_hline(y=rsi_sobrecompra,line_color="#ef4444",line_dash="dash",opacity=0.5,row=2,col=1)
        fig_adv.add_hline(y=rsi_sobreventa, line_color="#10b981",line_dash="dash",opacity=0.5,row=2,col=1)

        cap_adv_s = pd.Series(hist_adv,index=precio_adv.index[:len(hist_adv)])
        bh_adv_s  = (precio_adv/float(precio_adv.iloc[0]))*capital_adv
        fig_adv.add_trace(go.Scatter(x=cap_adv_s.index,y=cap_adv_s,name="Estrategia",
            line=dict(color="#6366f1",width=2.5),
            fill="tozeroy",fillcolor="rgba(99,102,241,0.08)"),row=3,col=1)
        fig_adv.add_trace(go.Scatter(x=bh_adv_s.index,y=bh_adv_s,name="Buy & Hold",
            line=dict(color="#f59e0b",width=2,dash="dot"),
            fill="tozeroy",fillcolor="rgba(245,158,11,0.05)"),row=3,col=1)

        fig_adv.update_layout(**tema_grafica(),height=700,
            legend=dict(bgcolor="rgba(15,23,42,0.9)",bordercolor="#334155",
                        orientation="h",yanchor="bottom",y=1.02))
        fig_adv.update_xaxes(gridcolor="#1e293b")
        fig_adv.update_yaxes(gridcolor="#1e3a5f")
        fig_adv.update_yaxes(range=[0,100],row=2,col=1)
        st.plotly_chart(fig_adv, use_container_width=True)

        with st.expander("❓ ¿Cómo leer estas gráficas?"):
            st.markdown(f"""
**Bandas de Bollinger (panel superior):**
Calculadas como la media ± {bb_desv} desviaciones estándar. Cuando el precio toca la **banda inferior** = barato relativamente → posible compra. Banda superior = caro → posible venta.

**RSI (panel central):**
Oscila 0-100. Mide si el activo subió o bajó demasiado rápido.
- **RSI < {rsi_sobreventa}** (zona verde): sobrevendido → posible rebote
- **RSI > {rsi_sobrecompra}** (zona roja): sobrecomprado → posible corrección
            """)

# ══════════════════════════════════════════════════════════════
#  TAB 6 — PORTAFOLIO ÓPTIMO
# ══════════════════════════════════════════════════════════════
with tab6:
    st.markdown("#### 🧮 Portafolio Óptimo — ¿Cuánto poner en cada activo?")

    with st.expander("📖 ¿Qué es esto y para qué sirve?", expanded=True):
        st.markdown("""
Esta sección responde una pregunta clave: si tienes $10,000 (o lo que pongas), 
**¿cuánto poner en Bitcoin, cuánto en S&P 500, cuánto en Oro?**

El modelo de Markowitz (Premio Nobel de Economía) prueba miles de combinaciones y encuentra 
las 3 mejores distribuciones de tu dinero:

| Portafolio | Para quién es | Qué prioriza |
|---|---|---|
| 🏆 **Máximo Sharpe** | La mayoría de inversores | Mejor ganancia por cada peso de riesgo asumido |
| 🛡️ **Mínimo Riesgo** | Inversores conservadores | La menor volatilidad posible, aunque gane menos |
| 🚀 **Máximo Rendimiento** | Inversores agresivos | La mayor ganancia posible, asumiendo más riesgo |
        """)

    activos_mark = [c for c in precios.columns if not precios[c].dropna().empty]

    if len(activos_mark)<2:
        st.warning("Necesitas al menos 2 activos seleccionados en el panel izquierdo.")
    else:
        c1,c2 = st.columns(2)
        with c1: capital_mark = st.number_input("Capital a invertir ($)",1000,10_000_000,capital_ini,key="mk_cap")
        with c2: n_sims = st.slider("Portafolios simulados",500,5000,2000,step=500)

        with st.spinner("Calculando portafolios óptimos..."):
            retornos  = precios[activos_mark].pct_change().dropna()
            n_act     = len(activos_mark)
            np.random.seed(42)
            p_rend,p_vol,p_sharpe,p_pesos = [],[],[],[]

            for _ in range(n_sims):
                w   = np.random.dirichlet(np.ones(n_act))
                r_a = np.sum(retornos.mean()*w)*252
                v_a = np.sqrt(np.dot(w.T,np.dot(retornos.cov()*252,w)))
                sh  = r_a/v_a if v_a>0 else 0
                p_rend.append(r_a*100); p_vol.append(v_a*100)
                p_sharpe.append(sh); p_pesos.append(w)

            p_rend   = np.array(p_rend)
            p_vol    = np.array(p_vol)
            p_sharpe = np.array(p_sharpe)
            p_pesos  = np.array(p_pesos)

            i_sh  = np.argmax(p_sharpe)
            i_mv  = np.argmin(p_vol)
            i_mr  = np.argmax(p_rend)

        # Comparativa de los 3 portafolios
        st.markdown("---")
        st.markdown("#### Los 3 portafolios óptimos")

        c1,c2,c3 = st.columns(3)
        for col_ui,idx,icono,titulo,subtitulo in [
            (c1,i_sh, "🏆","Máximo Sharpe","Mejor balance riesgo/ganancia"),
            (c2,i_mv, "🛡️","Mínimo Riesgo", "Más conservador"),
            (c3,i_mr, "🚀","Máx. Rendimiento","Más agresivo"),
        ]:
            with col_ui:
                st.markdown(f"**{icono} {titulo}**")
                st.caption(subtitulo)
                st.metric("Rendimiento anual esperado",f"{p_rend[idx]:+.1f}%")
                st.metric("Riesgo (volatilidad)",f"{p_vol[idx]:.1f}%")
                st.metric("Ratio Sharpe",f"{p_sharpe[idx]:.2f}",
                           help="Mayor = mejor balance. Por encima de 1.0 se considera bueno.")

        # Distribución de capital — una tabla clara por portafolio
        st.markdown("---")
        st.markdown("#### ¿Cuánto poner en cada activo?")

        tab_sh,tab_mv,tab_mr = st.tabs(["🏆 Máximo Sharpe","🛡️ Mínimo Riesgo","🚀 Máx. Rendimiento"])

        for tab_inner,idx,titulo in [
            (tab_sh,i_sh,"Máximo Sharpe"),
            (tab_mv,i_mv,"Mínimo Riesgo"),
            (tab_mr,i_mr,"Máximo Rendimiento"),
        ]:
            with tab_inner:
                pesos = p_pesos[idx]
                c_izq,c_der = st.columns([3,2])

                with c_izq:
                    st.markdown(f"**Distribución recomendada para ${capital_mark:,.0f}**")
                    filas_mk = []
                    for nombre,peso in sorted(zip(activos_mark,pesos),key=lambda x:-x[1]):
                        if peso>0.005:
                            filas_mk.append({
                                "Activo"  : nombre,
                                "% del capital": f"{peso*100:.1f}%",
                                "Monto ($)": f"${capital_mark*peso:,.0f}",
                                "Barra"    : "█"*int(peso*30)
                            })
                    df_mk = pd.DataFrame(filas_mk)
                    st.dataframe(df_mk, use_container_width=True, hide_index=True)

                    rend_port = p_rend[idx]
                    vol_port  = p_vol[idx]
                    st.markdown(f"""
**Resumen:** Con esta distribución, históricamente habrías obtenido un rendimiento anual de 
**{rend_port:+.1f}%** con una volatilidad de **{vol_port:.1f}%**.
                    """)

                with c_der:
                    pf = [(n,p) for n,p in zip(activos_mark,pesos) if p>0.01]
                    fig_pie = go.Figure(go.Pie(
                        labels=[x[0] for x in pf],
                        values=[x[1] for x in pf],
                        hole=0.5,
                        marker=dict(colors=COLORES[:len(pf)],
                                    line=dict(color="#0f172a",width=2)),
                        textinfo="percent",
                        textfont=dict(size=12,color="#e2e8f0"),
                        hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>"
                    ))
                    fig_pie.add_annotation(text=f"<b>{titulo}</b>",
                        x=0.5,y=0.5,font=dict(size=11,color="#94a3b8"),showarrow=False)
                    fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#e2e8f0"),height=300,
                        margin=dict(t=0,b=0,l=0,r=0),showlegend=True,
                        legend=dict(bgcolor="rgba(0,0,0,0)",font=dict(size=10)))
                    st.plotly_chart(fig_pie, use_container_width=True)

        # Frontera eficiente
        st.markdown("---")
        st.markdown("#### La Frontera Eficiente")
        st.caption("Cada punto es una combinación diferente de tus activos. Los más amarillos son los más eficientes (mejor ratio ganancia/riesgo).")

        fig_ef = go.Figure()
        fig_ef.add_trace(go.Scatter(x=p_vol,y=p_rend,mode="markers",
            marker=dict(color=p_sharpe,colorscale="Viridis",size=4,opacity=0.5,
                        colorbar=dict(title=dict(text="Sharpe",font=dict(color="#e2e8f0")),
                                      thickness=12,tickfont=dict(color="#e2e8f0"))),
            name="Portafolios",hovertemplate="Riesgo: %{x:.1f}%<br>Rendimiento: %{y:.1f}%<extra></extra>"))

        for idx_m,nombre_m,color_m,sym in [
            (i_sh,"🏆 Máximo Sharpe","#f59e0b","star"),
            (i_mv,"🛡️ Mínimo Riesgo","#10b981","diamond"),
            (i_mr,"🚀 Máx. Rendimiento","#ef4444","triangle-up"),
        ]:
            fig_ef.add_trace(go.Scatter(x=[p_vol[idx_m]],y=[p_rend[idx_m]],
                mode="markers+text",name=nombre_m,
                marker=dict(color=color_m,size=16,symbol=sym,line=dict(color="white",width=2)),
                text=[nombre_m.split(" ",1)[1]],textposition="top center",
                textfont=dict(color=color_m,size=10)))

        fig_ef.update_layout(**tema_grafica(),height=440,
            legend=dict(bgcolor="rgba(15,23,42,0.9)",bordercolor="#334155",borderwidth=1),
            xaxis=dict(title="Riesgo — Volatilidad anual (%)",gridcolor="#1e3a5f"),
            yaxis=dict(title="Rendimiento anual esperado (%)",gridcolor="#1e293b"))
        st.plotly_chart(fig_ef, use_container_width=True)
