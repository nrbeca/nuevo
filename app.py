"""
SADER - Sistema de Reportes Presupuestarios
Versión con soporte simultáneo MAP/SICOP
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import io
import json
import os
import pickle

from config import (
    MONTH_NAMES_FULL, formatear_fecha, obtener_ultimo_dia_habil, 
    get_config_by_year, UR_NOMBRES, PARTIDAS_AUSTERIDAD, DENOMINACIONES_AUSTERIDAD
)

# Importar PASIVOS si existen (opcional)
try:
    from config import PASIVOS_2026, obtener_pasivos_ur
except ImportError:
    PASIVOS_2026 = {}
    def obtener_pasivos_ur(ur_codigo, usar_2026=True):
        return {'Devengado': 0, 'Pagado': 0, 'Pasivo': 0}
from map_processor import procesar_map
from sicop_processor import procesar_sicop
from excel_map import generar_excel_map
from excel_sicop import generar_excel_sicop
from austeridad_processor import (
    procesar_sicop_austeridad,
    generar_dashboard_austeridad_desde_sicop, obtener_urs_disponibles_sicop
)
from excel_austeridad import generar_excel_austeridad

# ============================================================================
# CONFIGURACIÓN DE PERSISTENCIA
# ============================================================================

DATA_DIR = "data_persistente"
MAP_DATA_FILE = os.path.join(DATA_DIR, "map_data.pkl")
SICOP_DATA_FILE = os.path.join(DATA_DIR, "sicop_data.pkl")
METADATA_FILE = os.path.join(DATA_DIR, "metadata.json")

def asegurar_directorio():
    """Crea el directorio de datos si no existe"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def guardar_datos_map(resultados, filename):
    """Guarda los datos procesados de MAP"""
    asegurar_directorio()
    with open(MAP_DATA_FILE, 'wb') as f:
        pickle.dump(resultados, f)
    actualizar_metadata('map', filename)

def guardar_datos_sicop(resultados, df_original, filename):
    """Guarda los datos procesados de SICOP junto con el DataFrame original"""
    asegurar_directorio()
    data = {
        'resultados': resultados,
        'df_original': df_original
    }
    with open(SICOP_DATA_FILE, 'wb') as f:
        pickle.dump(data, f)
    actualizar_metadata('sicop', filename)

def cargar_datos_map():
    """Carga los datos de MAP si existen"""
    if os.path.exists(MAP_DATA_FILE):
        try:
            with open(MAP_DATA_FILE, 'rb') as f:
                return pickle.load(f)
        except:
            return None
    return None

def cargar_datos_sicop():
    """Carga los datos de SICOP si existen"""
    if os.path.exists(SICOP_DATA_FILE):
        try:
            with open(SICOP_DATA_FILE, 'rb') as f:
                return pickle.load(f)
        except:
            return None
    return None

def actualizar_metadata(tipo, filename):
    """Actualiza los metadatos de última actualización"""
    asegurar_directorio()
    metadata = cargar_metadata()
    metadata[tipo] = {
        'filename': filename,
        'fecha_carga': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'usuario': 'Sistema'
    }
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)

def cargar_metadata():
    """Carga los metadatos de los reportes"""
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

# ============================================================================
# COLORES Y CONFIGURACIÓN DE PÁGINA
# ============================================================================

COLOR_AZUL = '#4472C4'
COLOR_NARANJA = '#ED7D31'
COLOR_VINO = '#9B2247'
COLOR_BEIGE = '#E6D194'
COLOR_GRIS = '#C4BFB6'
COLOR_GRIS_EXCEL = '#D9D9D6'
COLOR_VERDE = '#002F2A'

st.set_page_config(
    page_title="SADER - Reportes", 
    page_icon="", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# ============================================================================
# AUTENTICACIÓN - CONTRASEÑA
# ============================================================================

def verificar_contraseña():
    """Verifica que el usuario ingrese la contraseña correcta"""
    
    # Si ya está autenticado, retornar True
    if st.session_state.get('autenticado', False):
        return True
    
    # Mostrar formulario de login
    st.markdown("""
    <style>
        .login-container {
            max-width: 400px;
            margin: 100px auto;
            padding: 2rem;
            background: white;
            border-radius: 15px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            border: 2px solid #9B2247;
        }
        .login-header {
            text-align: center;
            color: #9B2247;
            margin-bottom: 2rem;
        }
        .login-header h1 {
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }
        .login-header p {
            color: #666;
            font-size: 0.9rem;
        }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
        <div class="login-header">
            <h1>🌾 SADER</h1>
            <p>Sistema de Reportes Presupuestarios</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            password = st.text_input("Contraseña", type="password", placeholder="Ingresa la contraseña")
            submit = st.form_submit_button("Ingresar", use_container_width=True)
            
            if submit:
                if password == "SADER 2025":
                    st.session_state['autenticado'] = True
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta. Intenta de nuevo.")
        
        st.markdown("""
        <div style="text-align: center; margin-top: 2rem; color: #999; font-size: 0.8rem;">
            Secretaría de Agricultura y Desarrollo Rural
        </div>
        """, unsafe_allow_html=True)
    
    return False

# Verificar autenticación antes de continuar
if not verificar_contraseña():
    st.stop()

# ============================================================================
# CSS (solo se carga si está autenticado)
# ============================================================================

st.markdown("""
<style>
    .stApp { background-color: #FFFFFF; }
    .main-header { background: linear-gradient(135deg, #9B2247 0%, #7a1b38 100%); color: white; padding: 1.5rem; border-radius: 10px; margin-bottom: 2rem; text-align: center; }
    .main-header h1 { margin: 0; font-size: 2rem; color: white; }
    .main-header p { margin: 0.5rem 0 0 0; color: white; opacity: 0.9; }
    .kpi-card { background: white; border-radius: 12px; padding: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 2px solid #9B2247; }
    .instrucciones-box { background: #f8f8f8; border: 1px solid #E6D194; border-radius: 10px; padding: 1.5rem; }
    .instrucciones-box h4 { color: #9B2247; margin-top: 0; }
    .status-box { background: #e8f5e9; border: 1px solid #4caf50; border-radius: 8px; padding: 1rem; margin: 0.5rem 0; }
    .status-box-warning { background: #fff3e0; border: 1px solid #ff9800; border-radius: 8px; padding: 1rem; margin: 0.5rem 0; }
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #9B2247 0%, #7a1b38 100%); }
    section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] span { color: white !important; }
    section[data-testid="stSidebar"] h3 { color: white !important; }
    .stDownloadButton > button { background: linear-gradient(135deg, #002F2A 0%, #004d40 100%); color: white; border: none; border-radius: 8px; padding: 0.75rem 2rem; font-weight: 600; }
    .stTabs [aria-selected="true"] { background: #9B2247 !important; color: white !important; }
    h1, h2, h3, h4 { color: #9B2247; }
    .data-status { font-size: 0.85rem; padding: 0.5rem; border-radius: 5px; margin: 0.5rem 0; }
    .data-loaded { background: #e8f5e9; color: #2e7d32; }
    .data-empty { background: #fff3e0; color: #ef6c00; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def format_currency(value):
    if pd.isna(value) or value == 0:
        return "$0.00"
    return f"${value:,.2f}"

def format_currency_millions(value):
    if pd.isna(value) or value == 0:
        return "$0.00 M"
    return f"${value/1_000_000:,.2f} M"

def create_kpi_card(label, value, subtitle="", bg_color=None):
    return f'<div style="background:white;border-radius:12px;padding:1rem;text-align:center;border:2px solid #9B2247;box-shadow:0 2px 8px rgba(0,0,0,0.08);"><div style="font-size:0.75rem;color:#333;text-transform:uppercase;">{label}</div><div style="font-size:1.3rem;font-weight:700;color:#9B2247;">{value}</div><div style="font-size:0.7rem;color:#666;">{subtitle}</div></div>'

def mostrar_estado_datos():
    """Muestra el estado actual de los datos cargados"""
    metadata = cargar_metadata()
    
    col1, col2 = st.columns(2)
    
    with col1:
        if 'map' in metadata:
            st.markdown(f"""
            <div class="data-status data-loaded">
                 <strong>MAP cargado:</strong> {metadata['map']['filename']}<br>
                <small>Actualizado: {metadata['map']['fecha_carga']}</small>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="data-status data-empty">
                 <strong>MAP:</strong> Sin datos cargados
            </div>
            """, unsafe_allow_html=True)
    
    with col2:
        if 'sicop' in metadata:
            st.markdown(f"""
            <div class="data-status data-loaded">
                 <strong>SICOP cargado:</strong> {metadata['sicop']['filename']}<br>
                <small>Actualizado: {metadata['sicop']['fecha_carga']}</small>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="data-status data-empty">
                 <strong>SICOP:</strong> Sin datos cargados
            </div>
            """, unsafe_allow_html=True)

def calcular_pasivos_cop_desde_sicop(df_original, ur_codigo, config):
    """
    Calcula los pasivos pagados en COP desde el DataFrame de SICOP.
    
    Dos escenarios separados:
    - FF 6 + COP 0 (Fuente Financiamiento 6 y Control Operativo 0) -> COP 00
    - FF 1 + COP 10 (Fuente Financiamiento 1 y Control Operativo 10) -> COP 10
    
    Returns:
        dict con PagoCOP_00 (FF6+COP0) y PagoCOP_10 (FF1+COP10)
    """
    if df_original is None or df_original.empty:
        return {'PagoCOP_00': 0, 'PagoCOP_10': 0}
    
    # Buscar la columna de fuente de financiamiento
    ff_col = None
    for col_name in ['FUENTE_FINANCIAMIENTO', 'FF', 'FUENTE_FIN', 'FTE_FIN']:
        if col_name in df_original.columns:
            ff_col = col_name
            break
    
    if ff_col is None:
        return {'PagoCOP_00': 0, 'PagoCOP_10': 0}
    
    # Verificar columnas requeridas
    if 'CONTROL_OPERATIVO' not in df_original.columns or 'EJERCIDO' not in df_original.columns:
        return {'PagoCOP_00': 0, 'PagoCOP_10': 0}
    
    # Mapear UR
    if 'ID_UNIDAD' not in df_original.columns:
        return {'PagoCOP_00': 0, 'PagoCOP_10': 0}
    
    df = df_original.copy()
    df['ID_UNIDAD'] = df['ID_UNIDAD'].astype(str)
    
    # Crear lista de URs que corresponden a la UR seleccionada
    mapeo_ur = config.get('mapeo_ur', {})
    fusion_urs = config.get('fusion_urs', {})
    
    urs_a_buscar = [ur_codigo, str(ur_codigo)]
    
    # Agregar URs que mapean a esta
    for ur_orig, ur_dest in mapeo_ur.items():
        if str(ur_dest) == str(ur_codigo):
            urs_a_buscar.append(str(ur_orig))
    
    # Agregar URs fusionadas
    for ur_orig, ur_dest in fusion_urs.items():
        if str(ur_dest) == str(ur_codigo):
            urs_a_buscar.append(str(ur_orig))
    
    # Filtrar por URs
    df_ur = df[df['ID_UNIDAD'].isin(urs_a_buscar)].copy()
    
    if df_ur.empty:
        return {'PagoCOP_00': 0, 'PagoCOP_10': 0}
    
    # Asegurar tipos numéricos
    df_ur[ff_col] = pd.to_numeric(df_ur[ff_col], errors='coerce').fillna(0).astype(int)
    df_ur['CONTROL_OPERATIVO'] = pd.to_numeric(df_ur['CONTROL_OPERATIVO'], errors='coerce').fillna(0).astype(int)
    df_ur['EJERCIDO'] = pd.to_numeric(df_ur['EJERCIDO'], errors='coerce').fillna(0)
    
    # Escenario 1: FF=6 y COP=0 -> COP 00
    condicion_cop00 = (df_ur[ff_col] == 6) & (df_ur['CONTROL_OPERATIVO'] == 0)
    pago_cop_00 = df_ur[condicion_cop00]['EJERCIDO'].sum()
    
    # Escenario 2: FF=1 y COP=10 -> COP 10
    condicion_cop10 = (df_ur[ff_col] == 1) & (df_ur['CONTROL_OPERATIVO'] == 10)
    pago_cop_10 = df_ur[condicion_cop10]['EJERCIDO'].sum()
    
    return {
        'PagoCOP_00': round(pago_cop_00, 2),
        'PagoCOP_10': round(pago_cop_10, 2)
    }

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.markdown('<div style="text-align:center;padding:1rem;color:white;font-weight:bold;font-size:1.5rem;"> SADER</div>', unsafe_allow_html=True)
    
    st.markdown("### Navegación")
    
    # Opciones del menú
    opciones_menu = [" Inicio", " Cargar Reportes", " Ver MAP", " Ver SICOP"]
    
    pagina = st.radio(
        "Selecciona vista:",
        opciones_menu,
        label_visibility="collapsed"
    )
    
    # Mostrar subtítulo solo para MAP y SICOP
    if pagina == " Ver MAP":
        st.caption("*Cuadro de Presupuesto*")
    elif pagina == " Ver SICOP":
        st.caption("*Estado del Ejercicio, Dashboard Presupuesto y Austeridad*")
    
    st.markdown("---")
    st.markdown("### Estado de Datos")
    
    metadata = cargar_metadata()
    
    if 'map' in metadata:
        st.success(f" MAP: {metadata['map']['filename'][:20]}...")
    else:
        st.warning(" MAP: Sin datos")
    
    if 'sicop' in metadata:
        st.success(f" SICOP: {metadata['sicop']['filename'][:20]}...")
    else:
        st.warning(" SICOP: Sin datos")
    
    # Botón de cerrar sesión
    st.markdown("---")
    if st.button(" Cerrar sesión", use_container_width=True):
        st.session_state['autenticado'] = False
        st.rerun()

# ============================================================================
# HEADER
# ============================================================================

st.markdown('<div class="main-header"><h1>Sistema de Reportes Presupuestarios</h1><p>Secretaría de Agricultura y Desarrollo Rural</p></div>', unsafe_allow_html=True)

# ============================================================================
# PÁGINA: INICIO
# ============================================================================

if pagina == " Inicio":
    st.markdown("### Bienvenido al Sistema de Reportes")
    
    mostrar_estado_datos()
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="instrucciones-box">
            <h4> Cargar Reportes</h4>
            <p>Sube archivos CSV de MAP o SICOP. Los datos quedarán disponibles para todos los usuarios hasta que se cargue un nuevo archivo.</p>
            <ul>
                <li>Los reportes se guardan automáticamente</li>
                <li>Puedes tener MAP y SICOP cargados al mismo tiempo</li>
                <li>Al subir un nuevo archivo, reemplaza el anterior</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="instrucciones-box">
            <h4> Ver Reportes</h4>
            <p>Navega entre los reportes cargados sin perder información.</p>
            <ul>
                <li><strong>Ver MAP:</strong> Cuadro de presupuesto</li>
                <li><strong>Ver SICOP:</strong> Estado del ejercicio, Dashboard de Presupuesto y Austeridad</li>
                <li>Descarga Excel desde cualquier vista</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# ============================================================================
# PÁGINA: CARGAR REPORTES
# ============================================================================

elif pagina == " Cargar Reportes":
    st.markdown("### Cargar Nuevos Reportes")
    
    mostrar_estado_datos()
    
    st.markdown("---")
    
    col_map, col_sicop = st.columns(2)
    
    # Columna MAP
    with col_map:
        st.markdown("####  Cargar MAP")
        uploaded_map = st.file_uploader(
            "Archivo CSV de MAP",
            type=['csv'],
            key="upload_map",
            help="Sube el archivo CSV del reporte MAP"
        )
        
        if uploaded_map is not None:
            try:
                df_map = pd.read_csv(uploaded_map, encoding='latin-1')
                
                with st.spinner("Procesando MAP..."):
                    resultados_map = procesar_map(df_map, uploaded_map.name)
                    guardar_datos_map(resultados_map, uploaded_map.name)
                
                st.success(f" MAP procesado correctamente: {len(df_map):,} registros")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error al procesar MAP: {str(e)}")
    
    # Columna SICOP
    with col_sicop:
        st.markdown("####  Cargar SICOP")
        uploaded_sicop = st.file_uploader(
            "Archivo CSV de SICOP",
            type=['csv'],
            key="upload_sicop",
            help="Sube el archivo CSV del reporte SICOP"
        )
        
        if uploaded_sicop is not None:
            try:
                df_sicop = pd.read_csv(uploaded_sicop, encoding='latin-1')
                
                with st.spinner("Procesando SICOP..."):
                    resultados_sicop = procesar_sicop(df_sicop, uploaded_sicop.name)
                    guardar_datos_sicop(resultados_sicop, df_sicop, uploaded_sicop.name)
                
                st.success(f" SICOP procesado correctamente: {len(df_sicop):,} registros")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error al procesar SICOP: {str(e)}")

# ============================================================================
# PÁGINA: VER MAP
# ============================================================================

elif pagina == " Ver MAP":
    resultados = cargar_datos_map()
    
    if resultados is None:
        st.warning(" No hay datos de MAP cargados. Ve a 'Cargar Reportes' para subir un archivo.")
        st.stop()
    
    metadata_map = resultados['metadata']
    config = metadata_map['config']
    totales = resultados['totales']
    
    # Botón de descarga
    col_titulo, col_descarga = st.columns([3, 1])
    with col_titulo:
        st.markdown("### Reporte MAP - Cuadro de Presupuesto")
    with col_descarga:
        excel_bytes = generar_excel_map(resultados)
        fecha_str = date.today().strftime("%d%b%Y").upper()
        st.download_button(
            label=" Descargar Excel",
            data=excel_bytes,
            file_name=f'Cuadro_Presupuesto_{fecha_str}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    st.markdown("---")
    st.markdown("### Resumen General Ramo 08")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(create_kpi_card("PEF Original", format_currency_millions(totales['Original'])), unsafe_allow_html=True)
    with col2:
        st.markdown(create_kpi_card("Modificado Anual", format_currency_millions(totales['ModificadoAnualNeto']), "", COLOR_VINO), unsafe_allow_html=True)
    with col3:
        st.markdown(create_kpi_card("Mod. Periodo", format_currency_millions(totales['ModificadoPeriodoNeto']), "", COLOR_BEIGE), unsafe_allow_html=True)
    with col4:
        st.markdown(create_kpi_card("Ejercido", format_currency_millions(totales['Ejercido']), "", COLOR_NARANJA), unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Tab único: Cuadro de Presupuesto
    st.markdown("#### Cuadro de Presupuesto")
    
    # Construir tabla completa como en el Excel
    cuadro_data = []
    categorias = resultados['categorias']
    programas = resultados.get('programas', {})
    programas_especificos = config.get('programas_especificos', [])
    programas_nombres = config.get('programas_nombres', {})
    nombres_especiales = config.get('nombres_especiales', {})
    
    # Fila Totales
    cuadro_data.append({
        'Concepto': 'Totales:',
        'Original': totales['Original'],
        'Mod. Anual': totales['ModificadoAnualNeto'],
        'Mod. Periodo': totales['ModificadoPeriodoNeto'],
        'Ejercido': totales['Ejercido'],
        'Disponible': totales['ModificadoPeriodoNeto'] - totales['Ejercido'],
        '% Avance': totales['Ejercido'] / totales['ModificadoPeriodoNeto'] * 100 if totales['ModificadoPeriodoNeto'] > 0 else 0,
        '_tipo': 'total'
    })
    
    # Servicios personales
    cat_sp = categorias.get('servicios_personales', {'Original': 0, 'ModificadoAnualNeto': 0, 'ModificadoPeriodoNeto': 0, 'Ejercido': 0})
    cuadro_data.append({
        'Concepto': 'Servicios personales',
        'Original': cat_sp['Original'],
        'Mod. Anual': cat_sp['ModificadoAnualNeto'],
        'Mod. Periodo': cat_sp['ModificadoPeriodoNeto'],
        'Ejercido': cat_sp['Ejercido'],
        'Disponible': cat_sp['ModificadoPeriodoNeto'] - cat_sp['Ejercido'],
        '% Avance': cat_sp['Ejercido'] / cat_sp['ModificadoPeriodoNeto'] * 100 if cat_sp['ModificadoPeriodoNeto'] > 0 else 0,
        '_tipo': 'subtotal'
    })
    
    # Gasto corriente
    cat_gc = categorias.get('gasto_corriente', {'Original': 0, 'ModificadoAnualNeto': 0, 'ModificadoPeriodoNeto': 0, 'Ejercido': 0})
    cuadro_data.append({
        'Concepto': 'Gasto corriente 1/',
        'Original': cat_gc['Original'],
        'Mod. Anual': cat_gc['ModificadoAnualNeto'],
        'Mod. Periodo': cat_gc['ModificadoPeriodoNeto'],
        'Ejercido': cat_gc['Ejercido'],
        'Disponible': cat_gc['ModificadoPeriodoNeto'] - cat_gc['Ejercido'],
        '% Avance': cat_gc['Ejercido'] / cat_gc['ModificadoPeriodoNeto'] * 100 if cat_gc['ModificadoPeriodoNeto'] > 0 else 0,
        '_tipo': 'subtotal'
    })
    
    # Subtotal subsidios
    subtotal_subs = {
        'Original': sum(programas.get(p, {}).get('Original', 0) for p in programas_especificos),
        'ModificadoAnualNeto': sum(programas.get(p, {}).get('ModificadoAnualNeto', 0) for p in programas_especificos),
        'ModificadoPeriodoNeto': sum(programas.get(p, {}).get('ModificadoPeriodoNeto', 0) for p in programas_especificos),
        'Ejercido': sum(programas.get(p, {}).get('Ejercido', 0) for p in programas_especificos),
    }
    cuadro_data.append({
        'Concepto': 'Subsidios y Gastos asociados 2/',
        'Original': subtotal_subs['Original'],
        'Mod. Anual': subtotal_subs['ModificadoAnualNeto'],
        'Mod. Periodo': subtotal_subs['ModificadoPeriodoNeto'],
        'Ejercido': subtotal_subs['Ejercido'],
        'Disponible': subtotal_subs['ModificadoPeriodoNeto'] - subtotal_subs['Ejercido'],
        '% Avance': subtotal_subs['Ejercido'] / subtotal_subs['ModificadoPeriodoNeto'] * 100 if subtotal_subs['ModificadoPeriodoNeto'] > 0 else 0,
        '_tipo': 'subtotal'
    })
    
    # Programas específicos
    for prog in programas_especificos:
        if prog in programas:
            nombre = nombres_especiales.get(prog, programas_nombres.get(prog, prog))
            d = programas[prog]
            cuadro_data.append({
                'Concepto': nombre,
                'Original': d.get('Original', 0),
                'Mod. Anual': d.get('ModificadoAnualNeto', 0),
                'Mod. Periodo': d.get('ModificadoPeriodoNeto', 0),
                'Ejercido': d.get('Ejercido', 0),
                'Disponible': d.get('ModificadoPeriodoNeto', 0) - d.get('Ejercido', 0),
                '% Avance': d.get('Ejercido', 0) / d.get('ModificadoPeriodoNeto', 1) * 100 if d.get('ModificadoPeriodoNeto', 0) > 0 else 0,
                '_tipo': 'programa'
            })
    
    # Otros programas
    cat_otros = categorias.get('otros_programas', {'Original': 0, 'ModificadoAnualNeto': 0, 'ModificadoPeriodoNeto': 0, 'Ejercido': 0})
    cuadro_data.append({
        'Concepto': 'Otros programas de subsidios y Gastos asociados 6/',
        'Original': cat_otros['Original'],
        'Mod. Anual': cat_otros['ModificadoAnualNeto'],
        'Mod. Periodo': cat_otros['ModificadoPeriodoNeto'],
        'Ejercido': cat_otros['Ejercido'],
        'Disponible': cat_otros['ModificadoPeriodoNeto'] - cat_otros['Ejercido'],
        '% Avance': cat_otros['Ejercido'] / cat_otros['ModificadoPeriodoNeto'] * 100 if cat_otros['ModificadoPeriodoNeto'] > 0 else 0,
        '_tipo': 'programa'
    })
    
    # Bienes muebles
    cat_bm = categorias.get('bienes_muebles', {'Original': 0, 'ModificadoAnualNeto': 0, 'ModificadoPeriodoNeto': 0, 'Ejercido': 0})
    cuadro_data.append({
        'Concepto': 'Bienes muebles, inmuebles e intangibles',
        'Original': cat_bm['Original'],
        'Mod. Anual': cat_bm['ModificadoAnualNeto'],
        'Mod. Periodo': cat_bm['ModificadoPeriodoNeto'],
        'Ejercido': cat_bm['Ejercido'],
        'Disponible': cat_bm['ModificadoPeriodoNeto'] - cat_bm['Ejercido'],
        '% Avance': cat_bm['Ejercido'] / cat_bm['ModificadoPeriodoNeto'] * 100 if cat_bm['ModificadoPeriodoNeto'] > 0 else 0,
        '_tipo': 'subtotal'
    })
    
    df_cuadro = pd.DataFrame(cuadro_data)
    
    # Guardar tipos para aplicar estilos
    tipos = df_cuadro['_tipo'].tolist()
    
    # Quitar columna auxiliar para mostrar
    df_mostrar = df_cuadro.drop(columns=['_tipo'])
    
    # Función para estilo de filas basada en índice
    def estilo_cuadro_map(row):
        idx = row.name
        tipo = tipos[idx] if idx < len(tipos) else ''
        if tipo == 'total':
            return ['background-color: #E6D194; font-weight: bold'] * len(row)
        elif tipo == 'subtotal':
            return ['background-color: #D9D9D6'] * len(row)
        return [''] * len(row)
    
    st.dataframe(
        df_mostrar.style.format({
            'Original': '${:,.2f}',
            'Mod. Anual': '${:,.2f}',
            'Mod. Periodo': '${:,.2f}',
            'Ejercido': '${:,.2f}',
            'Disponible': '${:,.2f}',
            '% Avance': '{:.2f}%'
        }).apply(estilo_cuadro_map, axis=1),
        use_container_width=True,
        hide_index=True,
        height=450
    )

# ============================================================================
# PÁGINA: VER SICOP
# ============================================================================

elif pagina == " Ver SICOP":
    datos_sicop = cargar_datos_sicop()
    
    if datos_sicop is None:
        st.warning(" No hay datos de SICOP cargados. Ve a 'Cargar Reportes' para subir un archivo.")
        st.stop()
    
    resultados = datos_sicop['resultados']
    df_original = datos_sicop['df_original']
    
    metadata_sicop = resultados['metadata']
    config = metadata_sicop['config']
    
    # Botón de descarga
    col_titulo, col_descarga = st.columns([3, 1])
    with col_titulo:
        st.markdown("### Reporte SICOP - Estado del Ejercicio")
    with col_descarga:
        excel_bytes = generar_excel_sicop(resultados)
        fecha_str = date.today().strftime("%d%b%Y").upper()
        st.download_button(
            label=" Descargar Excel",
            data=excel_bytes,
            file_name=f'Estado_Ejercicio_{fecha_str}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    st.markdown("---")
    st.markdown("### Resumen por Unidad Responsable SICOP")
    
    totales = resultados['totales']
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(create_kpi_card("Original", format_currency_millions(totales['Original'])), unsafe_allow_html=True)
    with col2:
        st.markdown(create_kpi_card("Modificado Anual", format_currency_millions(totales['Modificado_anual']), "", COLOR_VINO), unsafe_allow_html=True)
    with col3:
        st.markdown(create_kpi_card("Ejercido", format_currency_millions(totales['Ejercido_acumulado']), "", COLOR_NARANJA), unsafe_allow_html=True)
    with col4:
        pct = totales['Pct_avance_periodo'] * 100 if totales['Pct_avance_periodo'] else 0
        st.markdown(create_kpi_card("Avance Periodo", f"{pct:.2f}%", "", COLOR_AZUL), unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 3 Pestañas: Estado del Ejercicio, Dashboard Presupuesto, Dashboard Austeridad
    tab1, tab2, tab3 = st.tabs([" Estado del Ejercicio", " Dashboard Presupuesto", " Dashboard Austeridad"])
    
    # ========================================================================
    # TAB 1: Estado del Ejercicio
    # ========================================================================
    with tab1:
        st.markdown("#### Estado del Ejercicio por Unidad Responsable")
        
        resumen_df = resultados.get('resumen', pd.DataFrame())
        subtotales = resultados.get('subtotales', {})
        denominaciones = config.get('denominaciones', {})
        
        secciones_config = [
            ('sector_central', 'Sector Central', config.get('sector_central', [])),
            ('oficinas', 'Oficinas de Representación en las Entidades Federativas', config.get('oficinas', [])),
            ('organos_desconcentrados', 'Órganos Desconcentrados', config.get('organos_desconcentrados', [])),
            ('entidades_paraestatales', 'Entidades Paraestatales', config.get('entidades_paraestatales', []))
        ]
        
        ejercicio_data = []
        
        # Fila Totales
        ejercicio_data.append({
            'UR': '',
            'Denominación': 'Total general:',
            'Original': totales['Original'],
            'Mod. Anual': totales['Modificado_anual'],
            'Mod. Periodo': totales['Modificado_periodo'],
            'Ejercido': totales['Ejercido_acumulado'],
            'Disp. Anual': totales['Modificado_anual'] - totales['Ejercido_acumulado'],
            'Disp. Periodo': totales['Disponible_periodo'],
            '% Av. Anual': (totales['Ejercido_acumulado'] / totales['Modificado_anual'] * 100) if totales['Modificado_anual'] > 0 else 0,
            '% Av. Periodo': (totales['Pct_avance_periodo'] * 100) if totales.get('Pct_avance_periodo') else 0,
            '_tipo': 'total'
        })
        
        # Por cada sección
        for seccion_key, seccion_nombre, urs_lista in secciones_config:
            if seccion_key in subtotales:
                st_data = subtotales[seccion_key]
                ejercicio_data.append({
                    'UR': '',
                    'Denominación': seccion_nombre,
                    'Original': st_data['Original'],
                    'Mod. Anual': st_data['Modificado_anual'],
                    'Mod. Periodo': st_data['Modificado_periodo'],
                    'Ejercido': st_data['Ejercido_acumulado'],
                    'Disp. Anual': st_data['Modificado_anual'] - st_data['Ejercido_acumulado'],
                    'Disp. Periodo': st_data['Disponible_periodo'],
                    '% Av. Anual': (st_data['Ejercido_acumulado'] / st_data['Modificado_anual'] * 100) if st_data['Modificado_anual'] > 0 else 0,
                    '% Av. Periodo': (st_data['Pct_avance_periodo'] * 100) if st_data.get('Pct_avance_periodo') else 0,
                    '_tipo': 'subtotal'
                })
            
            contador_ur = 0
            for ur in urs_lista:
                ur_rows = resumen_df[resumen_df['UR'] == ur] if not resumen_df.empty else pd.DataFrame()
                if not ur_rows.empty:
                    ur_data = ur_rows.iloc[0]
                    ejercicio_data.append({
                        'UR': ur,
                        'Denominación': denominaciones.get(ur, ur),
                        'Original': ur_data.get('Original', 0),
                        'Mod. Anual': ur_data.get('Modificado_anual', 0),
                        'Mod. Periodo': ur_data.get('Modificado_periodo', 0),
                        'Ejercido': ur_data.get('Ejercido_acumulado', 0),
                        'Disp. Anual': ur_data.get('Disponible_anual', 0),
                        'Disp. Periodo': ur_data.get('Disponible_periodo', 0),
                        '% Av. Anual': (ur_data.get('Pct_avance_anual', 0) * 100) if ur_data.get('Pct_avance_anual') else 0,
                        '% Av. Periodo': (ur_data.get('Pct_avance_periodo', 0) * 100) if ur_data.get('Pct_avance_periodo') else 0,
                        '_tipo': 'ur_gris' if contador_ur % 2 == 1 else 'ur'
                    })
                    contador_ur += 1
        
        df_ejercicio = pd.DataFrame(ejercicio_data)
        tipos_sicop = df_ejercicio['_tipo'].tolist()
        df_mostrar = df_ejercicio.drop(columns=['_tipo'])
        
        def estilo_estado_ejercicio(row):
            idx = row.name
            tipo = tipos_sicop[idx] if idx < len(tipos_sicop) else ''
            if tipo == 'total':
                return ['background-color: #E6D194; font-weight: bold'] * len(row)
            elif tipo == 'subtotal':
                return ['background-color: #002F2A; color: white; font-weight: bold'] * len(row)
            elif tipo == 'ur_gris':
                return ['background-color: #D9D9D6'] * len(row)
            return [''] * len(row)
        
        st.dataframe(
            df_mostrar.style.format({
                'Original': '${:,.2f}',
                'Mod. Anual': '${:,.2f}',
                'Mod. Periodo': '${:,.2f}',
                'Ejercido': '${:,.2f}',
                'Disp. Anual': '${:,.2f}',
                'Disp. Periodo': '${:,.2f}',
                '% Av. Anual': '{:.2f}%',
                '% Av. Periodo': '{:.2f}%'
            }).apply(estilo_estado_ejercicio, axis=1),
            use_container_width=True,
            hide_index=True,
            height=800
        )
    
    # ========================================================================
    # TAB 2: Dashboard Presupuesto (MOVIDO DE MAP)
    # ========================================================================
    with tab2:
        st.markdown("### Dashboard de Presupuesto por UR")
        
        # Obtener datos por UR del SICOP
        capitulos_por_ur = resultados.get('capitulos_por_ur', {})
        partidas_por_ur = resultados.get('partidas_por_ur', {})
        
        # Selector de UR
        urs_disponibles = sorted([ur for ur in config.get('sector_central', []) + 
                                   config.get('oficinas', []) + 
                                   config.get('organos_desconcentrados', []) + 
                                   config.get('entidades_paraestatales', [])])
        denominaciones = config.get('denominaciones', {})
        urs_con_nombre = [f"{ur} - {denominaciones.get(ur, ur)[:40]}" for ur in urs_disponibles]
        
        ur_seleccionada = st.selectbox("Selecciona una Unidad Responsable:", options=urs_con_nombre, index=0, key="ur_dash_ppto")
        ur_codigo = ur_seleccionada.split(" - ")[0]
        
        # Buscar datos de la UR en resumen
        ur_rows = resumen_df[resumen_df['UR'] == ur_codigo] if not resumen_df.empty else pd.DataFrame()
        
        if ur_rows.empty:
            st.warning(f"No hay datos disponibles para la UR {ur_codigo}")
        else:
            ur_data = ur_rows.iloc[0]
            
            hoy = date.today()
            meses_esp = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            fecha_titulo = f"{hoy.day} de {meses_esp[hoy.month - 1]} de {hoy.year}"
            st.markdown(f"### Estado del ejercicio del 1 de enero al {fecha_titulo}")
            st.markdown(f"**{ur_codigo}.- {denominaciones.get(ur_codigo, ur_codigo)}**")
            
            # KPIs Fila 1
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(create_kpi_card("Original", format_currency(ur_data.get('Original', 0))), unsafe_allow_html=True)
            with c2:
                st.markdown(create_kpi_card("Modificado Anual", format_currency(ur_data.get('Modificado_anual', 0)), "", COLOR_VINO), unsafe_allow_html=True)
            with c3:
                st.markdown(create_kpi_card("Modificado Periodo", format_currency(ur_data.get('Modificado_periodo', 0)), "", COLOR_BEIGE), unsafe_allow_html=True)
            with c4:
                st.markdown(create_kpi_card("Ejercido", format_currency(ur_data.get('Ejercido_acumulado', 0)), "", COLOR_NARANJA), unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # KPIs Fila 2
            c5, c6, c7, c8 = st.columns(4)
            with c5:
                st.markdown(create_kpi_card("Disponible Anual", format_currency(ur_data.get('Disponible_anual', 0)), "", COLOR_AZUL), unsafe_allow_html=True)
            with c6:
                st.markdown(create_kpi_card("Disponible Periodo", format_currency(ur_data.get('Disponible_periodo', 0)), "", COLOR_AZUL), unsafe_allow_html=True)
            with c7:
                pct_anual = ur_data.get('Pct_avance_anual', 0) * 100 if ur_data.get('Pct_avance_anual') else 0
                st.markdown(create_kpi_card("% Avance Anual", f"{pct_anual:.2f}%", "", COLOR_GRIS), unsafe_allow_html=True)
            with c8:
                pct_periodo = ur_data.get('Pct_avance_periodo', 0) * 100 if ur_data.get('Pct_avance_periodo') else 0
                st.markdown(create_kpi_card("% Avance Periodo", f"{pct_periodo:.2f}%", "", COLOR_GRIS), unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Layout: Graficas + Pasivos | Tablas
            col_izq, col_der = st.columns([1, 1])
            
            with col_izq:
                cg1, cg2 = st.columns(2)
                
                ejercido = ur_data.get('Ejercido_acumulado', 0)
                disp_anual = ur_data.get('Disponible_anual', 0)
                disp_periodo = ur_data.get('Disponible_periodo', 0)
                pct_anual = ur_data.get('Pct_avance_anual', 0) * 100 if ur_data.get('Pct_avance_anual') else 0
                pct_periodo = ur_data.get('Pct_avance_periodo', 0) * 100 if ur_data.get('Pct_avance_periodo') else 0
                
                with cg1:
                    st.markdown("**Avance ejercicio anual**")
                    fig1 = go.Figure(go.Pie(values=[ejercido, max(0, disp_anual)], labels=['Ejercido', 'Disponible'], hole=0.6, marker_colors=[COLOR_NARANJA, COLOR_AZUL], textinfo='none'))
                    fig1.add_annotation(text=f"{pct_anual:.2f}%", x=0.5, y=0.5, font_size=18, font_color=COLOR_VINO, showarrow=False)
                    fig1.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=10, b=30, l=10, r=10), height=200)
                    st.plotly_chart(fig1, use_container_width=True, key="fig_sicop_anual")
                
                with cg2:
                    st.markdown("**Avance ejercicio periodo**")
                    fig2 = go.Figure(go.Pie(values=[ejercido, max(0, disp_periodo)], labels=['Ejercido', 'Disponible'], hole=0.6, marker_colors=[COLOR_NARANJA, COLOR_AZUL], textinfo='none'))
                    fig2.add_annotation(text=f"{pct_periodo:.2f}%", x=0.5, y=0.5, font_size=18, font_color=COLOR_VINO, showarrow=False)
                    fig2.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=10, b=30, l=10, r=10), height=200)
                    st.plotly_chart(fig2, use_container_width=True, key="fig_sicop_periodo")
                
                st.markdown("#### Pasivos con cargo al presupuesto")
                
                # Obtener datos de pasivos
                pasivos_ur = obtener_pasivos_ur(ur_codigo, usar_2026=config.get('usar_2026', True))
                pasivos_shcp = pasivos_ur.get('Pasivo', 0)
                
                # Calcular pasivos pagados en COP desde SICOP (separados)
                pasivos_cop = calcular_pasivos_cop_desde_sicop(df_original, ur_codigo, config)
                pago_cop_00 = pasivos_cop.get('PagoCOP_00', 0)
                pago_cop_10 = pasivos_cop.get('PagoCOP_10', 0)
                
                # Cuadro 1: Pasivos reportados a SHCP
                st.markdown(f'<div style="border:1px solid #ddd;border-radius:8px;padding:1rem;text-align:center;margin-bottom:0.5rem;"><div style="font-size:0.8rem;color:#666;">Pasivos reportados a la SHCP</div><div style="font-size:1.2rem;font-weight:bold;color:#9B2247;">{format_currency(pasivos_shcp)}</div></div>', unsafe_allow_html=True)
                
                # Cuadros 2 y 3: Pasivos pagados en COP 00 y COP 10
                cp1, cp2 = st.columns(2)
                with cp1:
                    st.markdown(f'<div style="border:1px solid #ddd;border-radius:8px;padding:1rem;text-align:center;"><div style="font-size:0.8rem;color:#666;">Pasivos pagados en COP 00</div><div style="font-size:1.1rem;font-weight:bold;color:#002F2A;">{format_currency(pago_cop_00)}</div><div style="font-size:0.65rem;color:#999;">(FF=6, COP=0)</div></div>', unsafe_allow_html=True)
                with cp2:
                    st.markdown(f'<div style="border:1px solid #ddd;border-radius:8px;padding:1rem;text-align:center;"><div style="font-size:0.8rem;color:#666;">Pasivos pagados en COP 10</div><div style="font-size:1.1rem;font-weight:bold;color:#002F2A;">{format_currency(pago_cop_10)}</div><div style="font-size:0.65rem;color:#999;">(FF=1, COP=10)</div></div>', unsafe_allow_html=True)
                
                st.markdown("**Avance de pago de pasivos**")
                
                # Total pagado = COP 00 + COP 10
                pago_cop_total = pago_cop_00 + pago_cop_10
                
                if pasivos_shcp > 0 and pago_cop_total > 0:
                    pct_pagado = min(pago_cop_total / pasivos_shcp, 1)
                    pct_por_pagar = 1 - pct_pagado
                    
                    fig3 = go.Figure(go.Pie(values=[pct_pagado, pct_por_pagar], labels=['Pagado', 'Por pagar'], hole=0.6, marker_colors=[COLOR_NARANJA, COLOR_AZUL], textinfo='none'))
                    fig3.add_annotation(text=f"{pct_pagado*100:.2f}%", x=0.5, y=0.5, font_size=18, font_color=COLOR_VINO, showarrow=False)
                elif pasivos_shcp > 0:
                    fig3 = go.Figure(go.Pie(values=[0, 1], labels=['Pagado', 'Por pagar'], hole=0.6, marker_colors=[COLOR_NARANJA, COLOR_AZUL], textinfo='none'))
                    fig3.add_annotation(text="0.00%", x=0.5, y=0.5, font_size=18, font_color=COLOR_VINO, showarrow=False)
                else:
                    fig3 = go.Figure(go.Pie(values=[1], labels=['Sin pasivos'], hole=0.6, marker_colors=['#e0e0e0'], textinfo='none'))
                    fig3.add_annotation(text="N/A", x=0.5, y=0.5, font_size=14, font_color='#999', showarrow=False)
                
                fig3.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=10, b=30, l=10, r=10), height=180)
                st.plotly_chart(fig3, use_container_width=True, key="fig_sicop_pasivos")
            
            with col_der:
                st.markdown("#### Ejercido por Capítulo")
                
                # Datos por capítulo
                caps_ur = capitulos_por_ur.get(ur_codigo, {})
                
                if caps_ur:
                    cap_data = []
                    for cap, cap_vals in caps_ur.items():
                        cap_nombre = {
                            '2': 'Cap. 2000 - Materiales',
                            '3': 'Cap. 3000 - Servicios',
                            '4': 'Cap. 4000 - Subsidios'
                        }.get(cap, f'Cap. {cap}000')
                        cap_data.append({
                            'Capítulo': cap_nombre,
                            'Original': cap_vals.get('Original', 0),
                            'Modificado': cap_vals.get('Modificado_periodo', cap_vals.get('Modificado_anual', 0)),
                            'Ejercido': cap_vals.get('Ejercido', 0)
                        })
                    
                    if cap_data:
                        df_caps = pd.DataFrame(cap_data)
                        st.dataframe(
                            df_caps.style.format({
                                'Original': '${:,.2f}',
                                'Modificado': '${:,.2f}',
                                'Ejercido': '${:,.2f}'
                            }),
                            use_container_width=True,
                            hide_index=True
                        )
                else:
                    st.info("No hay datos por capítulo disponibles")
                
                st.markdown("#### Top Partidas con Mayor Disponible")
                
                partidas_ur = partidas_por_ur.get(ur_codigo, [])
                
                if partidas_ur:
                    df_partidas = pd.DataFrame(partidas_ur)
                    st.dataframe(
                        df_partidas.style.format({
                            'Disponible': '${:,.2f}'
                        }),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No hay datos de partidas disponibles")
    
    # ========================================================================
    # TAB 3: Dashboard Austeridad
    # ========================================================================
    with tab3:
        st.markdown("### Dashboard Austeridad")
        
        datos_sicop_aust = procesar_sicop_austeridad(df_original)
        urs_disponibles = obtener_urs_disponibles_sicop(datos_sicop_aust)
        
        opciones_ur_aust = []
        for ur in urs_disponibles:
            nombre = UR_NOMBRES.get(ur, '')
            if nombre:
                opciones_ur_aust.append(f"{ur} - {nombre}")
            else:
                opciones_ur_aust.append(ur)
        
        ur_seleccionada = st.selectbox("Selecciona UR:", opciones_ur_aust, key="ur_austeridad")
        
        ur_codigo = ur_seleccionada.split(" - ")[0] if " - " in ur_seleccionada else ur_seleccionada
        ur_nombre = UR_NOMBRES.get(ur_codigo, ur_codigo)
        
        datos_dashboard = generar_dashboard_austeridad_desde_sicop(datos_sicop_aust, ur_codigo)
        
        año_actual = date.today().year
        año_anterior = año_actual - 1
        
        ultimo_habil = obtener_ultimo_dia_habil(date.today())
        mes_nombre = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"][ultimo_habil.month-1]
        
        st.markdown(f"#### Estado del ejercicio del 1 de enero al {ultimo_habil.day} de {mes_nombre} de {año_actual}")
        st.markdown(f"**{ur_codigo}.- {ur_nombre}**")
        
        total_ejercido_ant = sum(d['Ejercido_Anterior'] for d in datos_dashboard)
        total_original = sum(d['Original'] for d in datos_dashboard)
        total_modificado = sum(d['Modificado'] for d in datos_dashboard)
        total_ejercido = sum(d['Ejercido_Real'] for d in datos_dashboard)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(create_kpi_card(f"Ejercido {año_anterior}", format_currency_millions(total_ejercido_ant)), unsafe_allow_html=True)
        with col2:
            st.markdown(create_kpi_card("Original", format_currency_millions(total_original)), unsafe_allow_html=True)
        with col3:
            st.markdown(create_kpi_card("Modificado", format_currency_millions(total_modificado)), unsafe_allow_html=True)
        with col4:
            st.markdown(create_kpi_card("Ejercido Real", format_currency_millions(total_ejercido)), unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Partidas sujetas a Austeridad Republicana")
        
        df_display = pd.DataFrame(datos_dashboard)
        df_display = df_display.rename(columns={
            'Partida': 'Partida',
            'Denominacion': 'Denominación',
            'Ejercido_Anterior': f'Ejercido {año_anterior}',
            'Original': 'Original',
            'Modificado': 'Modificado',
            'Ejercido_Real': 'Ejercido Real',
            'Nota': 'Nota',
            'Avance_Anual': 'Avance Anual'
        })
        
        if 'Solicitud_Pago' in df_display.columns:
            df_display = df_display.drop(columns=['Solicitud_Pago'])
        
        def format_avance(val):
            if val is None or val == '':
                return ''
            if isinstance(val, str):
                return val
            return f"{val:.2%}"
        
        def color_nota(val):
            if pd.isna(val) or val == '':
                return ''
            if 'Solicitar dictamen' in str(val):
                return 'background-color: #FFB6C1'
            elif 'Monto ejercido real mayor' in str(val):
                return 'background-color: #FFD699'
            return ''
        
        styled_df = df_display.style.format({
            f'Ejercido {año_anterior}': '${:,.2f}',
            'Original': '${:,.2f}',
            'Modificado': '${:,.2f}',
            'Ejercido Real': '${:,.2f}',
            'Avance Anual': lambda x: format_avance(x)
        })
        
        try:
            styled_df = styled_df.map(color_nota, subset=['Nota'])
        except AttributeError:
            styled_df = styled_df.applymap(color_nota, subset=['Nota'])
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            height=500
        )
        
        # Botón de descarga Excel Austeridad
        excel_aust_bytes = generar_excel_austeridad(
            datos_dashboard, 
            ur_codigo, 
            ur_nombre,
            año_anterior=año_anterior,
            año_actual=año_actual
        )
        filename_aust = f'Dashboard_Austeridad_{ur_codigo}_{date.today().strftime("%d%b%Y").upper()}.xlsx'
        
        st.download_button(
            label=" Descargar Excel Austeridad",
            data=excel_aust_bytes,
            file_name=filename_aust,
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            key="download_excel_austeridad"
        )
