import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
from io import BytesIO
import os # Importar el módulo os para acceder a variables de entorno
import json # Importar el módulo json para parsear el JSON

# --- CONFIGURACIÓN ---
SHEET_NAME = "AirQualityDatabase"
SPREADSHEET_ID = "1QNorefNN63r4MYMNhEKs126J3hadVVmkWzMiDFAv5a0"

# --- CAMBIO IMPORTANTE AQUÍ: OBTENER CREDENCIALES DE VARIABLE DE ENTORNO ---
# Lee el token de Telegram desde una variable de entorno para mayor seguridad
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_POR_DEFECTO_AQUI_SI_NO_ESTA_EN_ENV")
# Lee el contenido JSON de la variable de entorno
GOOGLE_CREDENTIALS_JSON_STR = os.getenv("GOOGLE_CREDENTIALS_JSON")

if GOOGLE_CREDENTIALS_JSON_STR is None:
    raise ValueError("La variable de entorno GOOGLE_CREDENTIALS_JSON no está configurada. Asegúrate de añadir el contenido de tu key.json a Render.")

try:
    # Parsea el string JSON a un diccionario de Python
    GOOGLE_CREDENTIALS = json.loads(GOOGLE_CREDENTIALS_JSON_STR)
except json.JSONDecodeError:
    raise ValueError("Error al decodificar la variable de entorno GOOGLE_CREDENTIALS_JSON. Asegúrate de que el valor sea un JSON válido.")

# --- CONEXIÓN GOOGLE SHEETS ---
scope = ["[https://spreadsheets.google.com/feeds](https://spreadsheets.google.com/feeds)", "[https://www.googleapis.com/auth/drive](https://www.googleapis.com/auth/drive)"]
# Usa from_json_keyfile_dict en lugar de from_json_keyfile_name
creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDENTIALS, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

def get_dataframe():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.columns = df.columns.str.strip()
    # Convertir 'Fecha y Hora' a datetime, errores se vuelven NaT
    df['Fecha y Hora'] = pd.to_datetime(df['Fecha y Hora'], errors='coerce')
    # Convertir columnas relevantes a numéricas, errores a NaN
    for col in ['Temperatura (°C)', 'Humedad (%)', 'Gas (ADC)']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    # Filtrar filas sin fecha o sin datos numéricos válidos
    return df.dropna(subset=['Fecha y Hora', 'Temperatura (°C)', 'Humedad (%)', 'Gas (ADC)'])

# --- COMANDOS TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 AirQualityBot \n"
        "\n"
        "✅ Bienvenido\n"
        "\n"
        "💻 Comandos disponibles:\n"
        "\n"
        "/actual – Última lectura\n"
        "/promedio YYYY-MM-DD – Promedios del día\n"
        "/maximo YYYY-MM-DD – Valores máximos\n"
        "/minimo YYYY-MM-DD – Valores mínimos\n"
        "/grafico YYYY-MM-DD – Gráfico estadístico del día"
    )

async def actual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = get_dataframe()
    if df.empty:
        await update.message.reply_text("No hay datos disponibles.")
        return
    ultima = df.iloc[-1]
    msg = (f"📍 Última lectura:\n"
           f"🌡️ Temp: {ultima['Temperatura (°C)']} °C\n"
           f"💧 Humedad: {ultima['Humedad (%)']} %\n"
           f"🫧 Gas: {ultima['Gas (ADC)']} ADC\n"
           f"🕒 {ultima['Fecha y Hora']}")
    await update.message.reply_text(msg)

async def promedio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await responder_por_fecha(update, context, modo="promedio")

async def maximo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await responder_por_fecha(update, context, modo="maximo")

async def minimo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await responder_por_fecha(update, context, modo="minimo")

# --- FUNCIÓN GENERAL PARA PROMEDIO, MÁXIMO Y MÍNIMO ---

async def responder_por_fecha(update, context, modo="promedio"):
    if len(context.args) != 1:
        await update.message.reply_text(f"Uso: /{modo} YYYY-MM-DD")
        return

    fecha_str = context.args[0]
    try:
        fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("Formato inválido. Usa: YYYY-MM-DD")
        return

    try:
        df = get_dataframe()
        df['fecha'] = df['Fecha y Hora'].dt.date
        filtrado = df[df['fecha'] == fecha_dt]

        if filtrado.empty:
            await update.message.reply_text(f"No hay datos registrados para {fecha_dt}.")
            return

        if modo == "promedio":
            t = filtrado['Temperatura (°C)'].mean()
            h = filtrado['Humedad (%)'].mean()
            g = filtrado['Gas (ADC)'].mean()
            txt = f"📊 Promedios del {fecha_dt}:"
        elif modo == "maximo":
            t = filtrado['Temperatura (°C)'].max()
            h = filtrado['Humedad (%)'].max()
            g = filtrado['Gas (ADC)'].max()
            txt = f"📈 Máximos del {fecha_dt}:"
        elif modo == "minimo":
            t = filtrado['Temperatura (°C)'].min()
            h = filtrado['Humedad (%)'].min()
            g = filtrado['Gas (ADC)'].min()
            txt = f"📉 Mínimos del {fecha_dt}:"
        else:
            await update.message.reply_text("Modo de análisis no reconocido.")
            return

        t_str = f"{t:.2f} °C" if pd.notna(t) else "sin datos"
        h_str = f"{h:.2f} %" if pd.notna(h) else "sin datos"
        try:
            g_str = f"{g:.2f} ADC" if pd.notna(g) else "sin datos"
        except Exception:
            g_str = "sin datos"

        msg = f"{txt}\n🌡️ Temp: {t_str}\n💧 Humedad: {h_str}\n🫧 Gas: {g_str}"
        await update.message.reply_text(msg)

    except Exception as e:
        print(f"🛑 Error en comando '/{modo}':", e)
        await update.message.reply_text("Ocurrió un error interno procesando los datos.")

# --- NUEVO: FUNCIÓN PARA GRAFICAR ---

async def grafico(update, context):
    if len(context.args) != 1:
        await update.message.reply_text("Uso: /grafico YYYY-MM-DD")
        return

    fecha_str = context.args[0]
    try:
        fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("Formato inválido. Usa: YYYY-MM-DD")
        return

    df = get_dataframe()
    df['fecha'] = df['Fecha y Hora'].dt.date
    filtrado = df[df['fecha'] == fecha_dt]

    if filtrado.empty:
        await update.message.reply_text(f"No hay datos para {fecha_dt}.")
        return

    stats = {
        'Temperatura (°C)': {
            'min': filtrado['Temperatura (°C)'].min(),
            'prom': filtrado['Temperatura (°C)'].mean(),
            'max': filtrado['Temperatura (°C)'].max()
        },
        'Humedad (%)': {
            'min': filtrado['Humedad (%)'].min(),
            'prom': filtrado['Humedad (%)'].mean(),
            'max': filtrado['Humedad (%)'].max()
        },
        'Gas (ADC)': {
            'min': filtrado['Gas (ADC)'].min(),
            'prom': filtrado['Gas (ADC)'].mean(),
            'max': filtrado['Gas (ADC)'].max()
        }
    }

    categorias = list(stats.keys())
    minimos = [stats[c]['min'] for c in categorias]
    promedios = [stats[c]['prom'] for c in categorias]
    maximos = [stats[c]['max'] for c in categorias]

    x = range(len(categorias))
    width = 0.25

    fig, ax = plt.subplots(figsize=(8,5))
    ax.bar([p - width for p in x], minimos, width=width, label='Mínimo', color='skyblue')
    ax.bar(x, promedios, width=width, label='Promedio', color='lightgreen')
    ax.bar([p + width for p in x], maximos, width=width, label='Máximo', color='salmon')

    ax.set_xticks(x)
    ax.set_xticklabels(categorias)
    ax.set_ylabel('Valores')
    ax.set_title(f'Estadísticas del {fecha_dt}')
    ax.legend()
    plt.grid()
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.message.reply_photo(photo=buf)

# --- MAIN ---

def main():
    # El TELEGRAM_TOKEN ahora se obtiene de la variable de entorno al inicio del script.
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("actual", actual))
    app.add_handler(CommandHandler("promedio", promedio))
    app.add_handler(CommandHandler("maximo", maximo))
    app.add_handler(CommandHandler("minimo", minimo))
    app.add_handler(CommandHandler("grafico", grafico))  # Nuevo handler para gráficos

    print("✅ Bot en ejecución.")
    app.run_polling()

if __name__ == "__main__":
    main()
