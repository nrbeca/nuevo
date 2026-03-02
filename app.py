"""
SADER - Sistema de Reportes Presupuestarios
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
import io

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

# Colores
COLOR_AZUL = '#4472C4'
COLOR_NARANJA = '#ED7D31'
COLOR_VINO = '#9B2247'
COLOR_BEIGE = '#E6D194'
COLOR_GRIS = '#C4BFB6'  # Gris claro para tablas
COLOR_GRIS_EXCEL = '#D9D9D6'  # Gris original para Excel
COLOR_VERDE = '#002F2A'

# Configuracion
st.set_page_config(page_title="SADER - Reportes", page_icon="", layout="wide", initial_sidebar_state="expanded")

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
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #9B2247 0%, #7a1b38 100%); }
    section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] span { color: white !important; }
    section[data-testid="stSidebar"] h3 { color: white !important; }
    .stDownloadButton > button { background: linear-gradient(135deg, #002F2A 0%, #004d40 100%); color: white; border: none; border-radius: 8px; padding: 0.75rem 2rem; font-weight: 600; }
    .stTabs [aria-selected="true"] { background: #9B2247 !important; color: white !important; }
    h1, h2, h3, h4 { color: #9B2247; }
</style>
""", unsafe_allow_html=True)

def format_currency(value):
    if pd.isna(value) or value == 0:
        return "$0.00"
    return f"${value:,.2f}"

def format_currency_millions(value):
    if pd.isna(value) or value == 0:
        return "$0.00 M"
    return f"${value/1_000_000:,.2f} M"

def create_kpi_card(label, value, subtitle="", bg_color=None):
    # Todos los KPIs: fondo blanco, borde vino, texto negro
    return f'<div style="background:white;border-radius:12px;padding:1rem;text-align:center;border:2px solid #9B2247;box-shadow:0 2px 8px rgba(0,0,0,0.08);"><div style="font-size:0.75rem;color:#333;text-transform:uppercase;">{label}</div><div style="font-size:1.3rem;font-weight:700;color:#9B2247;">{value}</div><div style="font-size:0.7rem;color:#666;">{subtitle}</div></div>'

# Sidebar
with st.sidebar:
    st.markdown('<div style="text-align:center;padding:1rem;color:white;font-weight:bold;font-size:1.5rem;">SADER</div>', unsafe_allow_html=True)
    st.markdown("### Tipo de Reporte")
    reporte_tipo = st.radio("Selecciona:", ["MAP - Cuadro de presupuesto", "SICOP - Estado del Ejercicio"], label_visibility="collapsed")

# Header
st.markdown('<div class="main-header"><h1>Sistema de Reportes Presupuestarios</h1><p>Secretaria de Agricultura y Desarrollo Rural</p></div>', unsafe_allow_html=True)

es_map = "MAP" in reporte_tipo

# Upload
col_upload, col_instrucciones = st.columns([2, 1])
with col_upload:
    st.markdown(f"### {'MAP' if es_map else 'SICOP'} - Cargar Archivo")
    uploaded_file = st.file_uploader("Arrastra tu archivo CSV", type=['csv'])
with col_instrucciones:
    st.markdown('<div class="instrucciones-box"><h4>Instrucciones</h4><ol><li>Selecciona el tipo de reporte</li><li>Sube el archivo CSV</li><li>Revisa los resultados</li><li>Descarga el Excel</li></ol></div>', unsafe_allow_html=True)

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file, encoding='latin-1', low_memory=False)
        filename = uploaded_file.name
        st.success(f"Archivo: **{filename}** ({len(df):,} registros)")
        
        with st.spinner("Procesando..."):
            if es_map:
                resultados = procesar_map(df, filename)
            else:
                resultados = procesar_sicop(df, filename)
        
        metadata = resultados['metadata']
        config = metadata['config']
        
        col_info1, col_info2, col_info3 = st.columns(3)
        with col_info1:
            st.metric("Fecha", formatear_fecha(metadata['fecha_archivo']))
        with col_info2:
            st.metric("Mes", MONTH_NAMES_FULL[metadata['mes'] - 1])
        with col_info3:
            st.metric("Config", "2026" if config['usar_2026'] else "2025")
        
        st.markdown("---")
        
        # ====================================================================
        # MAP
        # ====================================================================
        if es_map:
            st.markdown("### Resumen Presupuestario")
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
            tab1, tab2, tab3 = st.tabs(["Resumen General", "Dashboard Presupuesto", "Graficas"])
            
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
            
            # ================================================================
            # TAB 2: DASHBOARD PRESUPUESTO (desde MAP)
            # ================================================================
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
                    
                    # Título con fecha
                    from datetime import date
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
                        # Graficas de avance
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
                        
                        # Seccion Pasivos
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
                        # Tabla por capitulo
                        st.markdown("#### Estado del ejercicio por capitulo de gasto")
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
                        
                        df_cap = pd.DataFrame(cap_data)
                        st.dataframe(df_cap.style.format({
                            'Original': '${:,.2f}', 'Mod. Anual': '${:,.2f}', 'Mod. Periodo': '${:,.2f}', 
                            'Ejercido': '${:,.2f}', 'Disponible': '${:,.2f}', '% Avance': '{:.2f}%'
                        }), use_container_width=True, hide_index=True)
                        
                        # Top 5 partidas
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
        
        # ====================================================================
        # SICOP
        # ====================================================================
        else:
            st.markdown("### Resumen por Unidad Responsable")
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
            
            tab1, tab2, tab3 = st.tabs(["Por Seccion", "Dashboard Austeridad", "Graficas"])
            
            with tab1:
                subtotales = resultados['subtotales']
                seccion_data = []
                for sk, sn in [('sector_central', 'Sector Central'), ('oficinas', 'Oficinas'), ('organos_desconcentrados', 'Organos Desconcentrados'), ('entidades_paraestatales', 'Entidades Paraestatales')]:
                    if sk in subtotales:
                        d = subtotales[sk]
                        p = d['Pct_avance_periodo'] * 100 if d.get('Pct_avance_periodo') else 0
                        seccion_data.append({'Seccion': sn, 'Original': d['Original'], 'Mod. Anual': d['Modificado_anual'], 'Mod. Periodo': d['Modificado_periodo'], 'Ejercido': d['Ejercido_acumulado'], 'Disponible': d['Disponible_periodo'], '% Avance': p})
                df_sec = pd.DataFrame(seccion_data)
                st.dataframe(df_sec.style.format({'Original': '${:,.2f}', 'Mod. Anual': '${:,.2f}', 'Mod. Periodo': '${:,.2f}', 'Ejercido': '${:,.2f}', 'Disponible': '${:,.2f}', '% Avance': '{:.2f}%'}), use_container_width=True, hide_index=True)
            
            with tab2:
                # Dashboard Austeridad
                st.markdown("### Dashboard Austeridad")
                
                # Procesar datos de austeridad desde el mismo archivo SICOP
                datos_sicop_aust = procesar_sicop_austeridad(df)
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
                
                # Extraer código de UR
                ur_codigo = ur_seleccionada.split(" - ")[0] if " - " in ur_seleccionada else ur_seleccionada
                ur_nombre = UR_NOMBRES.get(ur_codigo, ur_codigo)
                
                # Generar dashboard usando datos precargados de Cuenta Pública
                datos_dashboard = generar_dashboard_austeridad_desde_sicop(datos_sicop_aust, ur_codigo)
                
                # Determinar años
                año_actual = date.today().year
                año_anterior = año_actual - 1
                
                # Mostrar título
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
                
                # Tabla de datos
                st.markdown("#### Partidas sujetas a Austeridad Republicana")
                
                # Convertir a DataFrame para mostrar
                df_display = pd.DataFrame(datos_dashboard)
                
                # Renombrar columnas para display
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
                
                # Eliminar columna Solicitud_Pago del display
                if 'Solicitud_Pago' in df_display.columns:
                    df_display = df_display.drop(columns=['Solicitud_Pago'])
                
                # Formatear avance anual
                def format_avance(val):
                    if val is None or val == '':
                        return ''
                    if isinstance(val, str):
                        return val
                    return f"{val:.2%}"
                
                # Mostrar tabla
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
                    label="Descargar Excel Austeridad",
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
        
        # Descarga
        st.markdown("---")
        if es_map:
            excel_bytes = generar_excel_map(resultados)
            filename_excel = f'Cuadro_Presupuesto_{date.today().strftime("%d%b%Y").upper()}.xlsx'
        else:
            excel_bytes = generar_excel_sicop(resultados)
            filename_excel = f'Estado_Ejercicio_SICOP_{date.today().strftime("%d%b%Y").upper()}.xlsx'
        
        st.download_button(label="Descargar Excel", data=excel_bytes, file_name=filename_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.exception(e)

else:
    st.markdown('<div style="border:2px dashed #E6D194;border-radius:12px;padding:2rem;text-align:center;"><h3>Sube tu archivo CSV</h3><p style="color:#666;">Arrastra y suelta o haz clic en el boton de arriba</p></div>', unsafe_allow_html=True)

st.markdown("---")
st.markdown('<div style="text-align:center;color:#888;font-size:0.8rem;">SADER - Sistema de Reportes Presupuestarios</div>', unsafe_allow_html=True)
