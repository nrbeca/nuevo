"""
SADER - Sistema de Reportes Presupuestarios
Versión con persistencia de datos y soporte simultáneo MAP/SICOP
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

# CSS
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

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.markdown('<div style="text-align:center;padding:1rem;color:white;font-weight:bold;font-size:1.5rem;"> SADER</div>', unsafe_allow_html=True)
    
    st.markdown("### Navegación")
    pagina = st.radio(
        "Selecciona vista:",
        [" Inicio", " Cargar Reportes", " Ver MAP", " Ver SICOP"],
        label_visibility="collapsed"
    )
    
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
                <li><strong>Ver MAP:</strong> Cuadro de presupuesto y Dashboard</li>
                <li><strong>Ver SICOP:</strong> Estado del ejercicio y Austeridad</li>
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
                df_map = pd.read_csv(uploaded_map, encoding='latin-1', low_memory=False)
                filename_map = uploaded_map.name
                
                with st.spinner("Procesando MAP..."):
                    resultados_map = procesar_map(df_map, filename_map)
                    guardar_datos_map(resultados_map, filename_map)
                
                st.success(f" MAP cargado: **{filename_map}** ({len(df_map):,} registros)")
                st.info("Los datos están disponibles para todos los usuarios.")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error procesando MAP: {str(e)}")
    
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
                df_sicop = pd.read_csv(uploaded_sicop, encoding='latin-1', low_memory=False)
                filename_sicop = uploaded_sicop.name
                
                with st.spinner("Procesando SICOP..."):
                    resultados_sicop = procesar_sicop(df_sicop, filename_sicop)
                    guardar_datos_sicop(resultados_sicop, df_sicop, filename_sicop)
                
                st.success(f" SICOP cargado: **{filename_sicop}** ({len(df_sicop):,} registros)")
                st.info("Los datos están disponibles para todos los usuarios.")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error procesando SICOP: {str(e)}")

# ============================================================================
# PÁGINA: VER MAP
# ============================================================================

elif pagina == " Ver MAP":
    resultados = cargar_datos_map()
    
    if resultados is None:
        st.warning(" No hay datos de MAP cargados. Ve a 'Cargar Reportes' para subir un archivo.")
        st.stop()
    
    metadata = resultados['metadata']
    config = metadata['config']
    
    # Info del reporte
    col_info1, col_info2, col_info3 = st.columns(3)
    with col_info1:
        st.metric("Fecha Archivo", formatear_fecha(metadata['fecha_archivo']))
    with col_info2:
        st.metric("Mes", MONTH_NAMES_FULL[metadata['mes'] - 1])
    with col_info3:
        st.metric("Config", "2026" if config['usar_2026'] else "2025")
    
    st.markdown("---")
    st.markdown("### Resumen Presupuestario MAP")
    
    totales = resultados['totales']
    
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
    
    # Tabs MAP
    tab1, tab2, tab3 = st.tabs([" Resumen General", " Dashboard Presupuesto", " Gráficas"])
    
    with tab1:
        categorias = resultados['categorias']
        cat_data = []
        for cat_key, cat_name in [('servicios_personales', 'Servicios Personales'), ('gasto_corriente', 'Gasto Corriente'), ('subsidios', 'Subsidios'), ('otros_programas', 'Otros')]:
            if cat_key in categorias:
                d = categorias[cat_key]
                disp = d['ModificadoPeriodoNeto'] - d['Ejercido']
                pct = d['Ejercido'] / d['ModificadoPeriodoNeto'] * 100 if d['ModificadoPeriodoNeto'] > 0 else 0
                cat_data.append({'Categoria': cat_name, 'Original': d['Original'], 'Mod. Anual': d['ModificadoAnualNeto'], 'Mod. Periodo': d['ModificadoPeriodoNeto'], 'Ejercido': d['Ejercido'], 'Disponible': disp, '% Avance': pct})
        df_cat = pd.DataFrame(cat_data)
        st.dataframe(df_cat.style.format({'Original': '${:,.2f}', 'Mod. Anual': '${:,.2f}', 'Mod. Periodo': '${:,.2f}', 'Ejercido': '${:,.2f}', 'Disponible': '${:,.2f}', '% Avance': '{:.2f}%'}), use_container_width=True, hide_index=True)
    
    with tab2:
        resultados_ur = resultados.get('resultados_por_ur', {})
        if not resultados_ur:
            st.warning("No hay datos por UR disponibles")
        else:
            urs_disponibles = sorted(resultados_ur.keys())
            denominaciones = config.get('denominaciones', {})
            urs_con_nombre = [f"{ur} - {denominaciones.get(ur, ur)[:40]}" for ur in urs_disponibles]
            
            ur_seleccionada = st.selectbox("Selecciona una Unidad Responsable:", options=urs_con_nombre, index=0, key="ur_map")
            ur_codigo = ur_seleccionada.split(" - ")[0]
            datos_ur = resultados_ur[ur_codigo]
            
            hoy = date.today()
            meses_esp = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            fecha_titulo = f"{hoy.day} de {meses_esp[hoy.month - 1]} de {hoy.year}"
            st.markdown(f"### Estado del ejercicio del 1 de enero al {fecha_titulo}")
            st.markdown(f"**{ur_codigo}.- {denominaciones.get(ur_codigo, ur_codigo)}**")
            
            # KPIs Fila 1
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(create_kpi_card("Original", format_currency(datos_ur['Original'])), unsafe_allow_html=True)
            with c2:
                st.markdown(create_kpi_card("Modificado Anual", format_currency(datos_ur['Modificado_anual']), "", COLOR_VINO), unsafe_allow_html=True)
            with c3:
                st.markdown(create_kpi_card("Modificado Periodo", format_currency(datos_ur['Modificado_periodo']), "", COLOR_BEIGE), unsafe_allow_html=True)
            with c4:
                st.markdown(create_kpi_card("Ejercido", format_currency(datos_ur['Ejercido']), "", COLOR_NARANJA), unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # KPIs Fila 2
            c5, c6, c7, c8 = st.columns(4)
            with c5:
                st.markdown(create_kpi_card("Disponible Anual", format_currency(datos_ur['Disponible_anual']), "", COLOR_AZUL), unsafe_allow_html=True)
            with c6:
                st.markdown(create_kpi_card("Disponible Periodo", format_currency(datos_ur['Disponible_periodo']), "", COLOR_AZUL), unsafe_allow_html=True)
            with c7:
                cong_a = datos_ur.get('Congelado_anual', 0)
                st.markdown(create_kpi_card("Congelado Anual", format_currency(cong_a) if cong_a else "-", "", COLOR_GRIS), unsafe_allow_html=True)
            with c8:
                cong_p = datos_ur.get('Congelado_periodo', 0)
                st.markdown(create_kpi_card("Congelado Periodo", format_currency(cong_p) if cong_p else "-", "", COLOR_GRIS), unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Layout: Graficas + Pasivos | Tablas
            col_izq, col_der = st.columns([1, 1])
            
            with col_izq:
                cg1, cg2 = st.columns(2)
                pct_anual = datos_ur['Pct_avance_anual'] * 100
                pct_periodo = datos_ur['Pct_avance_periodo'] * 100
                
                with cg1:
                    st.markdown("**Avance ejercicio anual**")
                    fig1 = go.Figure(go.Pie(values=[datos_ur['Ejercido'], max(0, datos_ur['Disponible_anual'])], labels=['Ejercido', 'Disponible'], hole=0.6, marker_colors=[COLOR_NARANJA, COLOR_AZUL], textinfo='none'))
                    fig1.add_annotation(text=f"{pct_anual:.2f}%", x=0.5, y=0.5, font_size=18, font_color=COLOR_VINO, showarrow=False)
                    fig1.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=10, b=30, l=10, r=10), height=200)
                    st.plotly_chart(fig1, use_container_width=True, key="fig_map_anual")
                
                with cg2:
                    st.markdown("**Avance ejercicio periodo**")
                    fig2 = go.Figure(go.Pie(values=[datos_ur['Ejercido'], max(0, datos_ur['Disponible_periodo'])], labels=['Ejercido', 'Disponible'], hole=0.6, marker_colors=[COLOR_NARANJA, COLOR_AZUL], textinfo='none'))
                    fig2.add_annotation(text=f"{pct_periodo:.2f}%", x=0.5, y=0.5, font_size=18, font_color=COLOR_VINO, showarrow=False)
                    fig2.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=10, b=30, l=10, r=10), height=200)
                    st.plotly_chart(fig2, use_container_width=True, key="fig_map_periodo")
                
                st.markdown("#### Pasivos con cargo al presupuesto")
                cp1, cp2 = st.columns(2)
                with cp1:
                    st.markdown('<div style="border:1px solid #ddd;border-radius:8px;padding:1rem;text-align:center;"><div style="font-size:0.8rem;color:#666;">Pasivos reportados a la SHCP</div><div style="font-size:1.2rem;font-weight:bold;"></div></div>', unsafe_allow_html=True)
                with cp2:
                    st.markdown('<div style="border:1px solid #ddd;border-radius:8px;padding:1rem;text-align:center;"><div style="font-size:0.8rem;color:#666;">Pasivos pagados en COP 10</div><div style="font-size:1.2rem;font-weight:bold;"></div></div>', unsafe_allow_html=True)
                
                st.markdown("**Avance de pago de pasivos**")
                fig3 = go.Figure(go.Pie(values=[1], labels=['Sin pasivos'], hole=0.6, marker_colors=['#e0e0e0'], textinfo='none'))
                fig3.add_annotation(text="-", x=0.5, y=0.5, font_size=16, font_color=COLOR_VINO, showarrow=False)
                fig3.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=10, b=30, l=10, r=10), height=180)
                st.plotly_chart(fig3, use_container_width=True, key="fig_map_pasivos")
            
            with col_der:
                st.markdown("#### Estado del ejercicio por capítulo de gasto")
                caps_ur = resultados.get('capitulos_por_ur', {}).get(ur_codigo, {})
                
                cap_data = []
                tot_o, tot_ma, tot_mp, tot_e = 0, 0, 0, 0
                for cap_num, cap_name in [('2', 'Materiales y suministros'), ('3', 'Servicios generales'), ('4', 'Transferencias')]:
                    c = caps_ur.get(cap_num, {})
                    o, ma, mp, e = c.get('Original', 0), c.get('Modificado_anual', 0), c.get('Modificado_periodo', 0), c.get('Ejercido', 0)
                    d = mp - e
                    p = e / mp * 100 if mp > 0 else 0
                    tot_o += o; tot_ma += ma; tot_mp += mp; tot_e += e
                    cap_data.append({'Capitulo': f'{cap_num}000', 'Denominacion': cap_name, 'Original': o, 'Mod. Anual': ma, 'Mod. Periodo': mp, 'Ejercido': e, 'Disponible': d, '% Avance': p})
                
                tot_d = tot_mp - tot_e
                tot_p = tot_e / tot_mp * 100 if tot_mp > 0 else 0
                cap_data.insert(0, {'Capitulo': 'Total', 'Denominacion': '', 'Original': tot_o, 'Mod. Anual': tot_ma, 'Mod. Periodo': tot_mp, 'Ejercido': tot_e, 'Disponible': tot_d, '% Avance': tot_p})
                
                df_cap_table = pd.DataFrame(cap_data)
                st.dataframe(df_cap_table.style.format({
                    'Original': '${:,.2f}', 'Mod. Anual': '${:,.2f}', 'Mod. Periodo': '${:,.2f}', 
                    'Ejercido': '${:,.2f}', 'Disponible': '${:,.2f}', '% Avance': '{:.2f}%'
                }), use_container_width=True, hide_index=True)
                
                st.markdown("#### Cinco partidas con el mayor monto de disponible al periodo")
                partidas_ur = resultados.get('partidas_por_ur', {}).get(ur_codigo, [])
                if partidas_ur:
                    from config import obtener_denominacion_partida
                    total_disp = datos_ur['Disponible_periodo']
                    part_data = []
                    for p in partidas_ur[:5]:
                        pct_r = p['Disponible'] / total_disp * 100 if total_disp > 0 else 0
                        denom_partida = obtener_denominacion_partida(p['Partida'])
                        part_data.append({'Partida': p['Partida'], 'Denominación': denom_partida, 'Disponible': p['Disponible'], '% del Total': pct_r})
                    df_part = pd.DataFrame(part_data)
                    st.dataframe(df_part.style.format({'Disponible': '${:,.2f}', '% del Total': '{:.2f}%'}), use_container_width=True, hide_index=True)
                else:
                    st.info("No hay partidas con disponible")
    
    with tab3:
        cg1, cg2 = st.columns(2)
        with cg1:
            fig_pie = px.pie(df_cat, values='Mod. Periodo', names='Categoria', color_discrete_sequence=[COLOR_VINO, COLOR_BEIGE, COLOR_GRIS, COLOR_VERDE])
            st.plotly_chart(fig_pie, use_container_width=True, key="pie_map_cat")
        with cg2:
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(name='Ejercido', x=df_cat['Categoria'], y=df_cat['Ejercido'], marker_color=COLOR_NARANJA))
            fig_bar.add_trace(go.Bar(name='Disponible', x=df_cat['Categoria'], y=df_cat['Disponible'], marker_color=COLOR_AZUL))
            fig_bar.update_layout(barmode='stack', xaxis_tickangle=-45)
            st.plotly_chart(fig_bar, use_container_width=True, key="bar_map_cat")
    
    # Botón de descarga
    st.markdown("---")
    excel_bytes = generar_excel_map(resultados)
    filename_excel = f'Cuadro_Presupuesto_{date.today().strftime("%d%b%Y").upper()}.xlsx'
    st.download_button(
        label=" Descargar Excel MAP",
        data=excel_bytes,
        file_name=filename_excel,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
    
    metadata = resultados['metadata']
    config = metadata['config']
    
    # Info del reporte
    col_info1, col_info2, col_info3 = st.columns(3)
    with col_info1:
        st.metric("Fecha Archivo", formatear_fecha(metadata['fecha_archivo']))
    with col_info2:
        st.metric("Mes", MONTH_NAMES_FULL[metadata['mes'] - 1])
    with col_info3:
        st.metric("Config", "2026" if config['usar_2026'] else "2025")
    
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
    
    tab1, tab2, tab3 = st.tabs([" Por Sección", " Dashboard Austeridad", " Gráficas"])
    
    with tab1:
        subtotales = resultados['subtotales']
        seccion_data = []
        for sk, sn in [('sector_central', 'Sector Central'), ('oficinas', 'Oficinas'), ('organos_desconcentrados', 'Órganos Desconcentrados'), ('entidades_paraestatales', 'Entidades Paraestatales')]:
            if sk in subtotales:
                d = subtotales[sk]
                p = d['Pct_avance_periodo'] * 100 if d.get('Pct_avance_periodo') else 0
                seccion_data.append({'Seccion': sn, 'Original': d['Original'], 'Mod. Anual': d['Modificado_anual'], 'Mod. Periodo': d['Modificado_periodo'], 'Ejercido': d['Ejercido_acumulado'], 'Disponible': d['Disponible_periodo'], '% Avance': p})
        df_sec = pd.DataFrame(seccion_data)
        st.dataframe(df_sec.style.format({'Original': '${:,.2f}', 'Mod. Anual': '${:,.2f}', 'Mod. Periodo': '${:,.2f}', 'Ejercido': '${:,.2f}', 'Disponible': '${:,.2f}', '% Avance': '{:.2f}%'}), use_container_width=True, hide_index=True)
    
    with tab2:
        st.markdown("### Dashboard Austeridad")
        
        # Procesar datos de austeridad desde el DataFrame original
        datos_sicop_aust = procesar_sicop_austeridad(df_original)
        urs_disponibles = obtener_urs_disponibles_sicop(datos_sicop_aust)
        
        # Selector de UR
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
        
        # KPIs resumen
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
        
        st.dataframe(
            df_display.style.format({
                f'Ejercido {año_anterior}': '${:,.2f}',
                'Original': '${:,.2f}',
                'Modificado': '${:,.2f}',
                'Ejercido Real': '${:,.2f}',
                'Avance Anual': lambda x: format_avance(x)
            }),
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
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_austeridad"
        )
        st.caption("El Excel incluye fórmulas para Nota y Avance Anual")
    
    with tab3:
        cg1, cg2 = st.columns(2)
        with cg1:
            fig_pie = px.pie(df_sec, values='Mod. Periodo', names='Seccion', color_discrete_sequence=[COLOR_VINO, COLOR_BEIGE, COLOR_GRIS, COLOR_VERDE])
            st.plotly_chart(fig_pie, use_container_width=True, key="pie_sicop")
        with cg2:
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(name='Ejercido', x=df_sec['Seccion'], y=df_sec['Ejercido'], marker_color=COLOR_NARANJA))
            fig_bar.add_trace(go.Bar(name='Disponible', x=df_sec['Seccion'], y=df_sec['Disponible'], marker_color=COLOR_AZUL))
            fig_bar.update_layout(barmode='stack', xaxis_tickangle=-45)
            st.plotly_chart(fig_bar, use_container_width=True, key="bar_sicop")
    
    # Botón de descarga SICOP
    st.markdown("---")
    excel_bytes = generar_excel_sicop(resultados)
    filename_excel = f'Estado_Ejercicio_SICOP_{date.today().strftime("%d%b%Y").upper()}.xlsx'
    st.download_button(
        label=" Descargar Excel SICOP",
        data=excel_bytes,
        file_name=filename_excel,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown('<div style="text-align:center;color:#888;font-size:0.8rem;">SADER - Sistema de Reportes Presupuestarios | Los datos se mantienen hasta que se cargue un nuevo archivo</div>', unsafe_allow_html=True)
