# ============================================================
#  ANALIZADOR DE INVERSIONES - v3.1
#  Módulos: Análisis + Backtesting + Riesgo + Sentimiento + Telegram
#  Requisitos: pip install yfinance pandas plotly feedparser textblob requests
# ============================================================

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
#  CONFIGURACIÓN
# ============================================================

ACTIVOS = {
    "S&P 500 (ETF)"  : "SPY",
    "Nasdaq (ETF)"   : "QQQ",
    "México (ETF)"   : "EWW",
    "Oro (ETF)"      : "GLD",
    "Bitcoin"        : "BTC-USD"
}

AÑOS_HISTORIAL    = 3
CAPITAL_INICIAL   = 10_000

ACTIVOS_BACKTEST  = ["SPY", "QQQ", "BTC-USD", "GLD"]
AÑOS_BACKTEST     = 5
COMBOS_MA         = [(10, 30), (20, 50), (50, 200)]
STOP_LOSS_PCT     = 0.08
TRAILING_STOP     = True

# ---- Telegram ----
TELEGRAM_TOKEN   = "8362312296:AAFr9lR1ad775g8p_OxuSvz9nYMMAitcCFk"
TELEGRAM_CHAT_ID = "5858053994"

FUENTES_NOTICIAS = [
    ("Reuters",      "https://feeds.reuters.com/reuters/businessNews"),
    ("Yahoo Finance","https://finance.yahoo.com/news/rssindex"),
    ("Investing.com","https://www.investing.com/rss/news.rss"),
    ("MarketWatch",  "https://feeds.marketwatch.com/marketwatch/topstories"),
]

PALABRAS_POSITIVAS = [
    "surge","rally","gain","rise","growth","record","bull","recovery",
    "profit","strong","boost","up","high","beat","sube","alza","gana",
    "récord","crecimiento","positivo"
]
PALABRAS_NEGATIVAS = [
    "crash","fall","drop","loss","bear","recession","fear","selloff",
    "decline","weak","risk","tariff","war","crisis","baja","cae",
    "pérdida","recesión","inflación","negativo"
]

# ============================================================
#  FUNCIÓN: ENVIAR MENSAJE A TELEGRAM
# ============================================================

def enviar_telegram(mensaje, silencioso=False):
    """Envía un mensaje al bot de Telegram."""
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id"              : TELEGRAM_CHAT_ID,
            "text"                 : mensaje,
            "parse_mode"           : "HTML",
            "disable_notification" : silencioso
        }
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            return True
        else:
            print(f"  ⚠️  Telegram error: {r.text[:100]}")
            return False
    except Exception as e:
        print(f"  ⚠️  No se pudo enviar a Telegram: {e}")
        return False

# ============================================================
#  FUNCIÓN: ANÁLISIS DE NOTICIAS
# ============================================================

def analizar_noticias():
    print("\n📰 ANÁLISIS DE NOTICIAS Y SENTIMIENTO DE MERCADO\n")
    titulares, scores, fuente_list = [], [], []

    for nombre, url in FUENTES_NOTICIAS:
        try:
            feed  = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:5]:
                titulo = entry.get("title", "")
                if not titulo:
                    continue
                blob         = TextBlob(titulo)
                score_tb     = blob.sentiment.polarity
                titulo_lower = titulo.lower()
                bonus  = sum(0.15 for p in PALABRAS_POSITIVAS if p in titulo_lower)
                bonus -= sum(0.15 for p in PALABRAS_NEGATIVAS if p in titulo_lower)
                score_final  = max(-1, min(1, score_tb + bonus))
                titulares.append(titulo)
                scores.append(score_final)
                fuente_list.append(nombre)
                count += 1
            if count > 0:
                print(f"  ✅ {nombre:<22} — {count} titulares")
        except Exception as e:
            print(f"  ⚠️  {nombre:<22} — sin acceso")

    if not scores:
        return 0, []

    score_promedio = np.mean(scores)
    positivas = sum(1 for s in scores if s > 0.05)
    negativas = sum(1 for s in scores if s < -0.05)
    neutras   = len(scores) - positivas - negativas

    if score_promedio > 0.1:
        sentimiento_txt = "🟢 POSITIVO"
    elif score_promedio < -0.1:
        sentimiento_txt = "🔴 NEGATIVO"
    else:
        sentimiento_txt = "🟡 NEUTRO"

    print(f"\n  Score: {score_promedio:+.3f}  |  ✅{positivas}  ➖{neutras}  ❌{negativas}")
    print(f"  Sentimiento general: {sentimiento_txt}")

    titulares_scores = sorted(zip(scores, titulares, fuente_list), reverse=True)
    print(f"\n  Titulares destacados:")
    for score, titulo, _ in titulares_scores[:3]:
        emoji = "📈" if score > 0.05 else ("📉" if score < -0.05 else "➖")
        print(f"  {emoji} [{score:+.2f}] {titulo[:72]}")
    for score, titulo, _ in titulares_scores[-2:]:
        emoji = "📈" if score > 0.05 else ("📉" if score < -0.05 else "➖")
        print(f"  {emoji} [{score:+.2f}] {titulo[:72]}")

    return score_promedio, list(zip(scores, titulares))

# ============================================================
#  FUNCIÓN: BACKTEST
# ============================================================

def backtest(ticker, años, ma_rapida, ma_lenta, capital_ini, stop_loss_pct, trailing):
    fecha_bt  = (datetime.today() - timedelta(days=365 * años)).strftime("%Y-%m-%d")
    fecha_fin = datetime.today().strftime("%Y-%m-%d")
    df        = yf.download(ticker, start=fecha_bt, end=fecha_fin, progress=False)
    if df.empty:
        return None
    precio = df["Close"].squeeze()
    ma_r   = precio.rolling(window=ma_rapida).mean()
    ma_l   = precio.rolling(window=ma_lenta).mean()

    capital, en_mercado  = float(capital_ini), False
    precio_compra        = 0.0
    precio_max           = 0.0
    operaciones          = []
    capital_hist         = []
    señal                = (ma_r > ma_l).astype(int)
    señal_previa         = señal.shift(1)

    for fecha, precio_actual in precio.items():
        precio_actual = float(precio_actual)
        if pd.isna(precio_actual):
            capital_hist.append(capital)
            continue

        razon_salida = None
        if en_mercado:
            if trailing:
                precio_max = max(precio_max, precio_actual)
                stop_nivel = precio_max * (1 - stop_loss_pct)
            else:
                stop_nivel = precio_compra * (1 - stop_loss_pct)
            if precio_actual <= stop_nivel:
                razon_salida = "STOP-LOSS"
            elif señal.get(fecha, 1) == 0 and señal_previa.get(fecha, 1) == 1:
                razon_salida = "DEATH CROSS"

        if razon_salida and en_mercado:
            ganancia_pct = (precio_actual - precio_compra) / precio_compra * 100
            capital      = capital * (precio_actual / precio_compra)
            operaciones.append({
                "tipo": "VENTA", "fecha": fecha, "precio": precio_actual,
                "ganancia_%": ganancia_pct, "capital": capital, "razon": razon_salida
            })
            en_mercado = False

        if not en_mercado and señal.get(fecha, 0) == 1 and señal_previa.get(fecha, 0) == 0:
            en_mercado    = True
            precio_compra = precio_actual
            precio_max    = precio_actual
            operaciones.append({
                "tipo": "COMPRA", "fecha": fecha,
                "precio": precio_actual, "capital": capital
            })

        capital_hist.append(capital * (precio_actual / precio_compra) if en_mercado else capital)

    if en_mercado:
        ultimo  = float(precio.iloc[-1])
        capital = capital * (ultimo / precio_compra)

    ventas     = [o for o in operaciones if o["tipo"] == "VENTA"]
    total_ops  = len(ventas)
    ganadoras  = sum(1 for o in ventas if o["ganancia_%"] > 0)
    win_rate   = (ganadoras / total_ops * 100) if total_ops > 0 else 0
    rend_est   = (capital - capital_ini) / capital_ini * 100
    capital_bh = capital_ini * (float(precio.iloc[-1]) / float(precio.iloc[0]))
    rend_bh    = (capital_bh - capital_ini) / capital_ini * 100
    cap_serie  = pd.Series(capital_hist)
    drawdown   = ((cap_serie - cap_serie.cummax()) / cap_serie.cummax() * 100).min()

    return {
        "ticker": ticker, "ma_rapida": ma_rapida, "ma_lenta": ma_lenta,
        "capital_final": capital, "capital_bh": capital_bh,
        "rend_est": rend_est, "rend_bh": rend_bh,
        "total_ops": total_ops, "ganadoras": ganadoras,
        "win_rate": win_rate, "drawdown": drawdown,
        "operaciones": operaciones, "capital_hist": capital_hist,
        "precios": precio, "ma_r": ma_r, "ma_l": ma_l,
    }

# ============================================================
#  DESCARGA DE DATOS
# ============================================================

fecha_inicio = (datetime.today() - timedelta(days=365 * AÑOS_HISTORIAL)).strftime("%Y-%m-%d")
fecha_fin    = datetime.today().strftime("%Y-%m-%d")

print("\n📥 Descargando datos de mercado...\n")
datos = {}
for nombre, ticker in ACTIVOS.items():
    try:
        df = yf.download(ticker, start=fecha_inicio, end=fecha_fin, progress=False)
        if not df.empty:
            datos[nombre] = df["Close"].squeeze()
            print(f"  ✅ {nombre:20s} ({ticker})")
    except:
        print(f"  ❌ {nombre:20s} — error")

precios     = pd.DataFrame(datos).dropna(how="all")
rendimiento = (precios / precios.iloc[0]) * 100

print("\n📊 RESUMEN DE RENDIMIENTO\n")
print(f"  {'Activo':<22} {'Inicio':>10} {'Hoy':>10} {'Rendimiento':>12} {'Riesgo':>10}")
print("  " + "-" * 68)
resumen_activos = []
for col in precios.columns:
    serie = precios[col].dropna()
    if len(serie) < 2:
        continue
    inicio      = serie.iloc[0]
    hoy         = serie.iloc[-1]
    retorno     = ((hoy - inicio) / inicio) * 100
    volatilidad = serie.pct_change().dropna().std() * (252 ** 0.5) * 100
    print(f"  {col:<22} {inicio:>10.2f} {hoy:>10.2f} {retorno:>+11.1f}% {volatilidad:>8.1f}%")
    resumen_activos.append((col, hoy, retorno, volatilidad))

print(f"\n💰 SIMULACIÓN: ${CAPITAL_INICIAL:,.0f} invertidos hace {AÑOS_HISTORIAL} año(s)\n")
print(f"  {'Activo':<22} {'Valor final':>14} {'Ganancia/Pérdida':>18}")
print("  " + "-" * 56)
sim_activos = []
for col in precios.columns:
    serie = precios[col].dropna()
    if len(serie) < 2:
        continue
    factor      = serie.iloc[-1] / serie.iloc[0]
    valor_final = CAPITAL_INICIAL * factor
    ganancia    = valor_final - CAPITAL_INICIAL
    emoji = "🟢" if ganancia > 0 else "🔴"
    print(f"  {col:<22} ${valor_final:>13,.0f}  {emoji} {ganancia:>+14,.0f}")
    sim_activos.append((col, valor_final, ganancia))

# ============================================================
#  BACKTESTING MÚLTIPLE
# ============================================================

print(f"\n{'='*70}")
print(f"  🔬 BACKTESTING — {len(ACTIVOS_BACKTEST)} activos × {len(COMBOS_MA)} estrategias")
print(f"  Stop-loss: {STOP_LOSS_PCT*100:.0f}%  |  Trailing: {'Sí' if TRAILING_STOP else 'No'}")
print(f"{'='*70}\n")

todos_resultados = []
mejor_resultado  = None

for ticker in ACTIVOS_BACKTEST:
    print(f"  📊 {ticker}")
    for (ma_r_val, ma_l_val) in COMBOS_MA:
        r = backtest(ticker, AÑOS_BACKTEST, ma_r_val, ma_l_val,
                     CAPITAL_INICIAL, STOP_LOSS_PCT, TRAILING_STOP)
        if r is None:
            continue
        todos_resultados.append(r)
        ventaja = r["rend_est"] - r["rend_bh"]
        emoji   = "✅" if ventaja > 0 else "⚠️ "
        print(f"    MA{ma_r_val:>3}/{ma_l_val:<4} "
              f"Est: {r['rend_est']:>+6.1f}%  B&H: {r['rend_bh']:>+6.1f}%  "
              f"Ventaja: {ventaja:>+6.1f}%  WR: {r['win_rate']:>5.1f}%  "
              f"DD: {r['drawdown']:>+5.1f}%  {emoji}")
    print()

todos_resultados.sort(key=lambda x: x["rend_est"], reverse=True)
mejor_resultado = todos_resultados[0]
print(f"  🥇 Mejor: {mejor_resultado['ticker']} "
      f"MA{mejor_resultado['ma_rapida']}/{mejor_resultado['ma_lenta']} "
      f"→ {mejor_resultado['rend_est']:+.1f}%")

# ============================================================
#  NOTICIAS Y SENTIMIENTO
# ============================================================

score_sentimiento, noticias = analizar_noticias()

# ============================================================
#  SEÑAL FINAL COMBINADA
# ============================================================

print(f"\n{'='*60}")
print(f"  🎯 SEÑAL FINAL COMBINADA")
print(f"{'='*60}\n")

ma_r_serie    = mejor_resultado["ma_r"]
ma_l_serie    = mejor_resultado["ma_l"]
señal_tecnica = 1 if ma_r_serie.iloc[-1] > ma_l_serie.iloc[-1] else -1
señal_nombre  = "COMPRA (MA rápida > MA lenta)" if señal_tecnica == 1 else "VENTA (MA rápida < MA lenta)"
score_comb    = señal_tecnica * 0.6 + score_sentimiento * 0.4

if score_comb > 0.2:
    decision = "🟢 CONDICIONES FAVORABLES — COMPRAR"
    detalle  = "Tendencia técnica positiva con noticias favorables"
    alerta   = False
elif score_comb < -0.2:
    decision = "🔴 CONDICIONES DESFAVORABLES — PRECAUCIÓN"
    detalle  = "Señal negativa — considera reducir exposición"
    alerta   = True
else:
    decision = "🟡 SEÑAL MIXTA — MANTENER"
    detalle  = "Sin tendencia clara, evita movimientos bruscos"
    alerta   = False

print(f"  Señal técnica:   {'📈' if señal_tecnica==1 else '📉'} {señal_nombre}")
print(f"  Sentimiento:     {score_sentimiento:+.3f}")
print(f"  Score combinado: {score_comb:+.3f}")
print(f"\n  ╔══════════════════════════════════════════════╗")
print(f"  ║  {decision:<44}║")
print(f"  ║  {detalle:<44}║")
print(f"  ╚══════════════════════════════════════════════╝")
print(f"\n  ⚠️  Análisis educativo, no consejo financiero.\n")

# ============================================================
#  ENVÍO A TELEGRAM
# ============================================================

print("📲 Enviando reporte a Telegram...\n")

fecha_hoy = datetime.today().strftime("%d/%m/%Y %H:%M")

# Mensaje 1 — Encabezado
msg1 = (
    f"📊 <b>REPORTE DE INVERSIONES</b>\n"
    f"🗓 {fecha_hoy}\n"
    f"{'─'*30}\n\n"
    f"<b>💰 Rendimiento {AÑOS_HISTORIAL} años</b>\n"
)
for col, hoy_precio, retorno, vol in resumen_activos:
    emoji = "📈" if retorno > 0 else "📉"
    msg1 += f"{emoji} {col}: <b>{retorno:+.1f}%</b> (riesgo {vol:.1f}%)\n"

if enviar_telegram(msg1):
    print("  ✅ Mensaje 1/3 enviado — Rendimiento")

# Mensaje 2 — Simulación y mejor estrategia
msg2 = (
    f"💵 <b>SIMULACIÓN ${CAPITAL_INICIAL:,.0f} → {AÑOS_HISTORIAL} años</b>\n"
    f"{'─'*30}\n"
)
for col, valor_final, ganancia in sim_activos:
    emoji = "🟢" if ganancia > 0 else "🔴"
    msg2 += f"{emoji} {col}: <b>${valor_final:,.0f}</b> ({ganancia:+,.0f})\n"

msg2 += (
    f"\n🥇 <b>Mejor estrategia backtest</b>\n"
    f"Activo: {mejor_resultado['ticker']}  "
    f"MA{mejor_resultado['ma_rapida']}/{mejor_resultado['ma_lenta']}\n"
    f"Rendimiento: <b>{mejor_resultado['rend_est']:+.1f}%</b>  "
    f"vs B&H: {mejor_resultado['rend_bh']:+.1f}%\n"
    f"Win rate: {mejor_resultado['win_rate']:.1f}%  "
    f"Drawdown: {mejor_resultado['drawdown']:+.1f}%"
)

if enviar_telegram(msg2):
    print("  ✅ Mensaje 2/3 enviado — Simulación y backtest")

# Mensaje 3 — Señal final (con notificación sonora si es alerta)
sent_emoji = "🟢" if score_sentimiento > 0.1 else ("🔴" if score_sentimiento < -0.1 else "🟡")
msg3 = (
    f"🎯 <b>SEÑAL FINAL DEL DÍA</b>\n"
    f"{'─'*30}\n"
    f"Técnica: {'📈' if señal_tecnica==1 else '📉'} {señal_nombre}\n"
    f"Sentimiento noticias: {sent_emoji} {score_sentimiento:+.3f}\n"
    f"Score combinado: <b>{score_comb:+.3f}</b>\n\n"
    f"<b>{decision}</b>\n"
    f"<i>{detalle}</i>\n\n"
)

# Añadir titulares más negativos si hay alerta
if alerta and noticias:
    noticias_ord = sorted(noticias, key=lambda x: x[0])
    msg3 += "📰 <b>Noticias preocupantes:</b>\n"
    for score, titulo in noticias_ord[:3]:
        if score < -0.05:
            msg3 += f"• {titulo[:70]}\n"

msg3 += "\n⚠️ <i>Solo análisis educativo, no consejo financiero</i>"

if enviar_telegram(msg3, silencioso=not alerta):
    estado = "🔔 con notificación sonora" if alerta else "🔕 silencioso"
    print(f"  ✅ Mensaje 3/3 enviado — Señal final ({estado})")

print("\n✅ Reporte completo enviado a Telegram\n")

# ============================================================
#  GRÁFICA
# ============================================================

mejor = mejor_resultado
precio_mejor  = mejor["precios"]
capital_serie = pd.Series(
    mejor["capital_hist"],
    index=precio_mejor.index[:len(mejor["capital_hist"])]
)
bh_serie = (precio_mejor / float(precio_mejor.iloc[0])) * CAPITAL_INICIAL

COLORES = ["#6366f1","#10b981","#f59e0b","#ef4444","#8b5cf6","#06b6d4"]

fig = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,
    subplot_titles=(
        f"Rendimiento comparativo — últimos {AÑOS_HISTORIAL} años (%)",
        f"Mejor estrategia: {mejor['ticker']} MA{mejor['ma_rapida']}/{mejor['ma_lenta']} + Stop-Loss {STOP_LOSS_PCT*100:.0f}%",
        "Evolución del capital: Estrategia vs Buy & Hold"
    ),
    vertical_spacing=0.1,
    row_heights=[0.30, 0.38, 0.32]
)

# Panel 1 — Rendimiento
for i, col in enumerate(rendimiento.columns):
    serie = rendimiento[col].dropna()
    fig.add_trace(go.Scatter(
        x=serie.index, y=serie - 100, name=col,
        line=dict(color=COLORES[i % len(COLORES)], width=2),
        hovertemplate=f"<b>{col}</b><br>%{{x|%d %b %Y}}: %{{y:.1f}}%<extra></extra>"
    ), row=1, col=1)
fig.add_hline(y=0, line_dash="dash", line_color="#475569", opacity=0.6, row=1, col=1)

# Panel 2 — Precio + MAs + señales
fig.add_trace(go.Scatter(
    x=precio_mejor.index, y=precio_mejor,
    name=f"Precio {mejor['ticker']}", line=dict(color="#94a3b8", width=1.2)
), row=2, col=1)
fig.add_trace(go.Scatter(
    x=mejor["ma_r"].index, y=mejor["ma_r"],
    name=f"MA{mejor['ma_rapida']}d", line=dict(color="#10b981", width=1.5, dash="dot")
), row=2, col=1)
fig.add_trace(go.Scatter(
    x=mejor["ma_l"].index, y=mejor["ma_l"],
    name=f"MA{mejor['ma_lenta']}d", line=dict(color="#ef4444", width=1.5, dash="dash")
), row=2, col=1)

compras = [o for o in mejor["operaciones"] if o["tipo"] == "COMPRA"]
ventas  = [o for o in mejor["operaciones"] if o["tipo"] == "VENTA"]
stops   = [o for o in ventas if o.get("razon") == "STOP-LOSS"]
death   = [o for o in ventas if o.get("razon") == "DEATH CROSS"]

if compras:
    fig.add_trace(go.Scatter(
        x=[o["fecha"] for o in compras], y=[o["precio"] for o in compras],
        mode="markers", name="🟢 Compra",
        marker=dict(color="#10b981", size=11, symbol="triangle-up",
                    line=dict(color="white", width=1))
    ), row=2, col=1)
if death:
    fig.add_trace(go.Scatter(
        x=[o["fecha"] for o in death], y=[o["precio"] for o in death],
        mode="markers", name="🔴 Venta (cruce)",
        marker=dict(color="#ef4444", size=11, symbol="triangle-down",
                    line=dict(color="white", width=1))
    ), row=2, col=1)
if stops:
    fig.add_trace(go.Scatter(
        x=[o["fecha"] for o in stops], y=[o["precio"] for o in stops],
        mode="markers", name="⚠️ Stop-Loss",
        marker=dict(color="#f59e0b", size=13, symbol="x",
                    line=dict(color="white", width=2))
    ), row=2, col=1)

# Panel 3 — Capital
fig.add_trace(go.Scatter(
    x=capital_serie.index, y=capital_serie,
    name="Estrategia", line=dict(color="#6366f1", width=2.5),
    fill="tozeroy", fillcolor="rgba(99,102,241,0.10)"
), row=3, col=1)
fig.add_trace(go.Scatter(
    x=bh_serie.index, y=bh_serie,
    name="Buy & Hold", line=dict(color="#f59e0b", width=2, dash="dot"),
    fill="tozeroy", fillcolor="rgba(245,158,11,0.06)"
), row=3, col=1)

# Anotación de señal
color_señal = "#10b981" if score_comb > 0.2 else ("#ef4444" if score_comb < -0.2 else "#f59e0b")
fig.add_annotation(
    text=f"Señal hoy: {decision}  |  Score: {score_comb:+.2f}  |  Sentimiento: {score_sentimiento:+.2f}",
    xref="paper", yref="paper", x=0.5, y=1.03,
    showarrow=False,
    font=dict(size=12, color=color_señal),
    bgcolor="rgba(15,23,42,0.85)",
    bordercolor=color_señal, borderwidth=1.5, borderpad=6
)

fig.update_layout(
    title=dict(
        text="📊 Analizador de Inversiones v3.1 — Backtest + Riesgo + Sentimiento + Telegram",
        font=dict(size=17, color="#e2e8f0"), x=0.5
    ),
    plot_bgcolor="#0f172a", paper_bgcolor="#1e293b",
    font=dict(color="#e2e8f0", family="Arial, sans-serif"),
    hovermode="x unified",
    legend=dict(
        bgcolor="rgba(15,23,42,0.8)", bordercolor="#334155",
        borderwidth=1, font=dict(size=11)
    ),
    height=880,
    margin=dict(t=100, b=50, l=65, r=40)
)
fig.update_xaxes(gridcolor="#1e293b", showgrid=True, zeroline=False)
fig.update_yaxes(gridcolor="#1e3a5f", showgrid=True, zeroline=False)

fig.write_html("reporte_inversiones.html", auto_open=True)
print("✅ Gráfica guardada y abierta en tu navegador\n")
