import streamlit as st
import pandas as pd
from datetime import datetime
import sqlite3
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
import requests
import json

# --- Configuración de la Base de Datos SQLite ---
DB_FILE = "gestor_legal.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS casos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, tipo TEXT, 
                  fecha_inicio TEXT, estado TEXT, username TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- Autenticación ---
def check_credentials(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# Estado de la sesión
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None

# --- Configuración de la API Key en secrets ---
# Crea un archivo .streamlit/secrets.toml con: api_key = "TU_CLAVE_AQUI"
API_KEY = st.secrets.get("api_key", None)
if not API_KEY:
    st.error("API Key no configurada. Agrega 'api_key' en .streamlit/secrets.toml")
    st.stop()

# --- Función para llamar a la API de Google Gemini ---
def generate_legal_content(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 8192,
            "responseMimeType": "text/plain"
        }
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    else:
        st.error(f"Error en la API: {response.text}")
        return "Contenido no generado debido a un error."

# --- Interfaz Principal ---
st.title("Gestor Legal GT")
st.markdown("**Herramienta para abogados en Guatemala**")

if not st.session_state.logged_in:
    st.sidebar.header("Iniciar Sesión")
    login_username = st.sidebar.text_input("Usuario")
    login_password = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Iniciar Sesión"):
        if check_credentials(login_username, login_password):
            st.session_state.logged_in = True
            st.session_state.username = login_username
            st.success("¡Inicio de sesión exitoso!")
        else:
            st.error("Credenciales incorrectas")

    st.sidebar.header("Registrarse")
    reg_username = st.sidebar.text_input("Nuevo Usuario")
    reg_password = st.sidebar.text_input("Nueva Contraseña", type="password")
    if st.sidebar.button("Registrarse"):
        if add_user(reg_username, reg_password):
            st.success("Usuario registrado. Inicia sesión.")
        else:
            st.error("El usuario ya existe.")
else:
    st.sidebar.write(f"Bienvenido, {st.session_state.username}")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.experimental_rerun()

    # --- Tabs ---
    tab1, tab2, tab3 = st.tabs(["Gestión de Casos", "Cálculo de Honorarios", "Documentos"])

    with tab1:
        st.header("Gestión de Casos")
        col1, col2 = st.columns(2)
        with col1:
            with st.form(key="nuevo_caso"):
                cliente = st.text_input("Nombre del Cliente")
                tipo_caso = st.selectbox("Tipo de Caso", ["Civil", "Penal", "Laboral", "Mercantil"])
                fecha_inicio = st.date_input("Fecha de Inicio", datetime.today())
                estado = st.selectbox("Estado", ["En Progreso", "Ganado", "Perdido"])
                submit_button = st.form_submit_button(label="Agregar Caso")
                if submit_button:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT INTO casos (cliente, tipo, fecha_inicio, estado, username) VALUES (?, ?, ?, ?, ?)",
                              (cliente, tipo_caso, str(fecha_inicio), estado, st.session_state.username))
                    conn.commit()
                    conn.close()
                    st.success("Caso agregado con éxito")
        with col2:
            st.subheader("Lista de Casos")
            conn = sqlite3.connect(DB_FILE)
            casos_df = pd.read_sql_query(f"SELECT * FROM casos WHERE username='{st.session_state.username}'", conn)
            conn.close()
            st.dataframe(casos_df.drop(columns=["username"]))

    with tab2:
        st.header("Cálculo de Honorarios")
        col1, col2 = st.columns(2)
        with col1:
            horas = st.number_input("Horas trabajadas", min_value=1, value=10)
            tarifa_hora = st.number_input("Tarifa por hora (Q)", min_value=50.0, value=150.0, step=10.0)
        with col2:
            incluir_iva = st.checkbox("Incluir IVA (12%)")
            subtotal = horas * tarifa_hora
            iva = subtotal * 0.12 if incluir_iva else 0
            total = subtotal + iva
            st.write(f"Subtotal: Q{subtotal:.2f}")
            if incluir_iva:
                st.write(f"IVA (12%): Q{iva:.2f}")
            st.write(f"**Total: Q{total:.2f}**")

    with tab3:
        st.header("Generar Documentos")
        doc_type = st.selectbox("Tipo de Documento", ["Recibo de Honorarios", "Contrato Privado", "Demanda Inicial"])

        if doc_type == "Recibo de Honorarios":
            nombre_cliente = st.text_input("Nombre del Cliente")
            monto = st.number_input("Monto (Q)", min_value=0.0)
            if st.button("Generar Recibo"):
                pdf_file = f"recibo_{nombre_cliente}_{datetime.now().strftime('%Y%m%d')}.pdf"
                c = canvas.Canvas(pdf_file, pagesize=letter)
                c.setFont("Helvetica", 12)
                c.drawString(100, 750, "Recibo de Honorarios")
                c.drawString(100, 730, f"Cliente: {nombre_cliente}")
                c.drawString(100, 710, f"Monto: Q{monto:.2f}")
                c.drawString(100, 690, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
                c.save()
                st.success(f"Recibo generado: {pdf_file}")
                with open(pdf_file, "rb") as file:
                    st.download_button("Descargar", file, file_name=pdf_file)

        elif doc_type == "Contrato Privado":
            parte1 = st.text_input("Nombre de la Parte 1 (DPI si aplica)")
            parte2 = st.text_input("Nombre de la Parte 2 (DPI si aplica)")
            objeto = st.text_area("Objeto del Contrato")
            monto_contrato = st.number_input("Monto del Contrato (Q)", min_value=0.0)
            if st.button("Generar Contrato"):
                prompt = f"Redacta un contrato privado conforme a las leyes de Guatemala entre {parte1} y {parte2}, con el objeto: '{objeto}', por un monto de Q{monto_contrato}. Incluye cláusulas estándar como cumplimiento, resolución y jurisdicción en Guatemala."
                contenido = generate_legal_content(prompt)
                pdf_file = f"contrato_{parte1}_{datetime.now().strftime('%Y%m%d')}.pdf"
                c = canvas.Canvas(pdf_file, pagesize=letter)
                c.setFont("Helvetica", 12)
                y = 750
                for line in contenido.split("\n"):
                    c.drawString(100, y, line[:80])  # Limita a 80 caracteres por línea
                    y -= 15
                    if y < 50:
                        c.showPage()
                        y = 750
                c.save()
                st.success(f"Contrato generado: {pdf_file}")
                with open(pdf_file, "rb") as file:
                    st.download_button("Descargar", file, file_name=pdf_file)

        elif doc_type == "Demanda Inicial":
            demandante = st.text_input("Nombre del Demandante (DPI si aplica)")
            demandado = st.text_input("Nombre del Demandado (DPI si aplica)")
            motivo = st.text_area("Motivo de la Demanda")
            pretension = st.text_input("Pretensión (lo que se solicita)")
            if st.button("Generar Demanda"):
                prompt = f"Redacta una demanda inicial conforme al Código Procesal Civil y Mercantil de Guatemala. Demandante: {demandante}, Demandado: {demandado}, Motivo: '{motivo}', Pretensión: '{pretension}'. Incluye estructura formal y referencia a leyes guatemaltecas."
                contenido = generate_legal_content(prompt)
                pdf_file = f"demanda_{demandante}_{datetime.now().strftime('%Y%m%d')}.pdf"
                c = canvas.Canvas(pdf_file, pagesize=letter)
                c.setFont("Helvetica", 12)
                y = 750
                for line in contenido.split("\n"):
                    c.drawString(100, y, line[:80])
                    y -= 15
                    if y < 50:
                        c.showPage()
                        y = 750
                c.save()
                st.success(f"Demanda generada: {pdf_file}")
                with open(pdf_file, "rb") as file:
                    st.download_button("Descargar", file, file_name=pdf_file)

# Instrucciones
st.sidebar.markdown("**Ejecutar:** `streamlit run app.py`")
