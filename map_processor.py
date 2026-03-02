# ============================================================================
# PROCESADOR DE ARCHIVOS MAP - BASADO EN SCRIPT COLAB ORIGINAL
# ============================================================================

import pandas as pd
import numpy as np
from datetime import date
from config import (
    MONTH_NAMES, round_like_excel, detectar_fecha_archivo,
    get_config_by_year, numero_a_letras_mx, UR_MAP
)


def sum_columns(df, prefix, months_to_use):
    """Suma las columnas de un prefijo para los meses especificados"""
    cols = [f'{prefix}_{month}' for month in months_to_use if f'{prefix}_{month}' in df.columns]
    if not cols:
        return pd.Series([0] * len(df))
    result = df[cols].fillna(0).sum(axis=1)
    return result.apply(lambda x: round_like_excel(x, 2))


def crear_pivot_suma(df, filtro_func):
    """Crea una suma de Original, ModificadoAnualNeto, ModificadoPeriodoNeto, Ejercido"""
    filtered = df[filtro_func(df)]
    if len(filtered) == 0:
        return {
            'Original': 0,
            'ModificadoAnualNeto': 0,
            'ModificadoPeriodoNeto': 0,
            'Ejercido': 0
        }
    return {
        'Original': round_like_excel(filtered['Original'].sum(), 2),
        'ModificadoAnualNeto': round_like_excel(filtered['ModificadoAnualNeto'].sum(), 2),
        'ModificadoPeriodoNeto': round_like_excel(filtered['ModificadoPeriodoNeto'].sum(), 2),
        'Ejercido': round_like_excel(filtered['Ejercido'].sum(), 2)
    }


def calcular_congelado_programa(df, programa):
    """Calcula el congelado anual de un programa específico"""
    df_programa = df[df['Pp'] == programa]
    if len(df_programa) == 0:
        return 0
    return round_like_excel(df_programa['CongeladoAnual'].sum(), 2)


def procesar_map(df, filename):
    """Procesa un archivo MAP y genera el resumen presupuestario"""
    
    # Detectar fecha del archivo
    fecha_archivo, mes_archivo, año_archivo = detectar_fecha_archivo(filename)
    
    # Obtener configuración según el año
    config = get_config_by_year(año_archivo)
    
    # Meses
    month_names = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC']
    months_up_to_current = month_names[:mes_archivo]
    
    # Obtener configuración de programas
    PROGRAMAS_ESPECIFICOS = config['programas_especificos']
    FUSION_PROGRAMAS = config.get('fusion_programas', {})
    
    # =========================================================================
    # CALCULAR COLUMNAS (igual que Colab)
    # =========================================================================
    
    # Calcular Nueva UR
    df['NuevaUR'] = df['UNIDAD'].apply(
        lambda x: 811 if x == 'G00' else UR_MAP.get(int(x) if str(x).isdigit() else 0, int(x) if str(x).isdigit() else 0)
    )
    
    # Calcular Pp (Programa Presupuestario) = IDEN_PROY + PROYECTO.zfill(3)
    df['Pp_Original'] = df['IDEN_PROY'].astype(str) + df['PROYECTO'].astype(str).str.zfill(3)
    
    # Aplicar fusión de programas (B004 -> B006 para 2026)
    def mapear_programa(pp):
        if pp in FUSION_PROGRAMAS:
            return FUSION_PROGRAMAS[pp]
        return pp
    
    df['Pp'] = df['Pp_Original'].apply(mapear_programa)
    
    # Calcular Capítulo = (PARTIDA // 10000) * 1000
    df['PARTIDA'] = pd.to_numeric(df['PARTIDA'], errors='coerce').fillna(0).astype(int)
    df['Capitulo'] = (df['PARTIDA'] // 10000) * 1000
    
    # Redondear valores base
    for prefix in ['ORI', 'AMP', 'RED', 'MOD', 'CONG', 'DESCONG', 'EJE']:
        for month in month_names:
            col = f'{prefix}_{month}'
            if col in df.columns:
                df[col] = df[col].fillna(0).apply(lambda x: round_like_excel(x, 2))
    
    # =========================================================================
    # CALCULAR TOTALES (igual que Colab)
    # =========================================================================
    
    año_actual = date.today().year
    es_cierre_año_anterior = (mes_archivo in [1, 2]) and (año_archivo < año_actual)
    
    # Original
    df['Original'] = sum_columns(df, 'ORI', month_names)
    df['OriginalPeriodo'] = sum_columns(df, 'ORI', months_up_to_current)
    
    # Modificado Anual Bruto
    df['ModificadoAnualBruto'] = sum_columns(df, 'MOD', month_names)
    
    # Modificado Periodo Bruto
    if es_cierre_año_anterior:
        df['ModificadoPeriodoBruto'] = sum_columns(df, 'MOD', month_names)
    else:
        df['ModificadoPeriodoBruto'] = sum_columns(df, 'MOD', months_up_to_current)
    
    # Congelados = CONG - DESCONG
    cong_anual = sum_columns(df, 'CONG', month_names)
    descong_anual = sum_columns(df, 'DESCONG', month_names)
    
    if es_cierre_año_anterior:
        cong_periodo = sum_columns(df, 'CONG', month_names)
        descong_periodo = sum_columns(df, 'DESCONG', month_names)
    else:
        cong_periodo = sum_columns(df, 'CONG', months_up_to_current)
        descong_periodo = sum_columns(df, 'DESCONG', months_up_to_current)
    
    df['CongeladoAnual'] = (cong_anual - descong_anual).apply(lambda x: round_like_excel(x, 2))
    df['CongeladoPeriodo'] = (cong_periodo - descong_periodo).apply(lambda x: round_like_excel(x, 2))
    
    # Modificado Neto = MOD - Congelado
    mod_anual_sum = sum_columns(df, 'MOD', month_names)
    df['ModificadoAnualNeto'] = (mod_anual_sum - df['CongeladoAnual']).apply(lambda x: round_like_excel(x, 2))
    
    if es_cierre_año_anterior:
        df['ModificadoPeriodoNeto'] = df['ModificadoAnualNeto'].copy()
    else:
        mod_periodo_sum = sum_columns(df, 'MOD', months_up_to_current)
        df['ModificadoPeriodoNeto'] = (mod_periodo_sum - df['CongeladoPeriodo']).apply(lambda x: round_like_excel(x, 2))
    
    # Ejercido
    df['Ejercido'] = sum_columns(df, 'EJE', month_names)
    
    # Disponibles
    df['DisponibleAnualNeto'] = (df['ModificadoAnualNeto'] - df['Ejercido']).apply(lambda x: round_like_excel(x, 2))
    df['DisponiblePeriodoNeto'] = (df['ModificadoPeriodoNeto'] - df['Ejercido']).apply(lambda x: round_like_excel(x, 2))
    
    # =========================================================================
    # CONGELADOS POR PROGRAMA (para notas del Excel)
    # =========================================================================
    
    programas_con_congelados = ['S263', 'S293', 'S304']
    congelados_valores = {}
    congelados_textos = {}
    
    for prog in programas_con_congelados:
        valor = calcular_congelado_programa(df, prog)
        congelados_valores[prog] = valor
        congelados_textos[prog] = numero_a_letras_mx(valor)
    
    # =========================================================================
    # CREAR TABLAS DINÁMICAS (igual que Colab)
    # =========================================================================
    
    # Capítulo 1000 (Servicios Personales) - EXCLUYENDO programas específicos
    pivot_cap1000 = crear_pivot_suma(
        df,
        lambda d: (d['Capitulo'] == 1000) & (~d['Pp'].isin(PROGRAMAS_ESPECIFICOS))
    )
    
    # Capítulos 2000 + 3000 (Gasto Corriente) - EXCLUYENDO programas específicos
    pivot_cap2000_3000 = crear_pivot_suma(
        df,
        lambda d: (d['Capitulo'].isin([2000, 3000])) & (~d['Pp'].isin(PROGRAMAS_ESPECIFICOS))
    )
    
    # Programas Específicos (cada uno incluye TODOS sus capítulos)
    pivot_programas = {}
    for prog in PROGRAMAS_ESPECIFICOS:
        pivot_programas[prog] = crear_pivot_suma(df, lambda d, p=prog: d['Pp'] == p)
    
    # Capítulo 4000 (Otros programas) - EXCLUYENDO programas específicos
    pivot_cap4000 = crear_pivot_suma(
        df,
        lambda d: (d['Capitulo'] == 4000) & (~d['Pp'].isin(PROGRAMAS_ESPECIFICOS))
    )
    
    # Capítulos 5000 + 7000 (Bienes Muebles) - EXCLUYENDO programas específicos
    pivot_cap5000_7000 = crear_pivot_suma(
        df,
        lambda d: (d['Capitulo'].isin([5000, 7000])) & (~d['Pp'].isin(PROGRAMAS_ESPECIFICOS))
    )
    
    # =========================================================================
    # CALCULAR SUBTOTALES Y TOTALES
    # =========================================================================
    
    # Subtotal subsidios = suma de todos los programas específicos
    subtotal_subsidios = {
        'Original': sum(pivot_programas[p]['Original'] for p in PROGRAMAS_ESPECIFICOS),
        'ModificadoAnualNeto': sum(pivot_programas[p]['ModificadoAnualNeto'] for p in PROGRAMAS_ESPECIFICOS),
        'ModificadoPeriodoNeto': sum(pivot_programas[p]['ModificadoPeriodoNeto'] for p in PROGRAMAS_ESPECIFICOS),
        'Ejercido': sum(pivot_programas[p]['Ejercido'] for p in PROGRAMAS_ESPECIFICOS),
    }
    
    # Totales = suma de todas las categorías
    totales = {
        'Original': (pivot_cap1000['Original'] + pivot_cap2000_3000['Original'] +
                     subtotal_subsidios['Original'] +
                     pivot_cap4000['Original'] + pivot_cap5000_7000['Original']),
        'ModificadoAnualNeto': (pivot_cap1000['ModificadoAnualNeto'] + pivot_cap2000_3000['ModificadoAnualNeto'] +
                                subtotal_subsidios['ModificadoAnualNeto'] +
                                pivot_cap4000['ModificadoAnualNeto'] + pivot_cap5000_7000['ModificadoAnualNeto']),
        'ModificadoPeriodoNeto': (pivot_cap1000['ModificadoPeriodoNeto'] + pivot_cap2000_3000['ModificadoPeriodoNeto'] +
                                  subtotal_subsidios['ModificadoPeriodoNeto'] +
                                  pivot_cap4000['ModificadoPeriodoNeto'] + pivot_cap5000_7000['ModificadoPeriodoNeto']),
        'Ejercido': (pivot_cap1000['Ejercido'] + pivot_cap2000_3000['Ejercido'] +
                     subtotal_subsidios['Ejercido'] +
                     pivot_cap4000['Ejercido'] + pivot_cap5000_7000['Ejercido']),
    }
    
    # Categorías para compatibilidad con la app
    categorias = {
        'servicios_personales': pivot_cap1000,
        'gasto_corriente': pivot_cap2000_3000,
        'subsidios': subtotal_subsidios,
        'otros_programas': pivot_cap4000,
        'bienes_muebles': pivot_cap5000_7000,
    }
    
    # =========================================================================
    # CALCULOS POR UR PARA DASHBOARD PRESUPUESTO
    # =========================================================================
    
    # Filtros para dashboard: excluir Cap 1000 y partidas 39801/39810
    PARTIDAS_EXCLUIR = [39801, 39810]
    df_dashboard = df[(df['Capitulo'] != 1000) & (~df['PARTIDA'].isin(PARTIDAS_EXCLUIR))].copy()
    
    resultados_por_ur = {}
    capitulos_por_ur = {}
    partidas_por_ur = {}
    
    for ur in df['UNIDAD'].unique():
        ur_str = str(ur).strip()
        
        # Datos filtrados para dashboard
        df_ur = df_dashboard[df_dashboard['UNIDAD'].astype(str).str.strip() == ur_str]
        
        if len(df_ur) == 0:
            continue
        
        # KPIs principales
        original = round_like_excel(df_ur['Original'].sum(), 2)
        mod_anual = round_like_excel(df_ur['ModificadoAnualNeto'].sum(), 2)
        mod_periodo = round_like_excel(df_ur['ModificadoPeriodoNeto'].sum(), 2)
        ejercido = round_like_excel(df_ur['Ejercido'].sum(), 2)
        cong_anual = round_like_excel(df_ur['CongeladoAnual'].sum(), 2)
        cong_periodo = round_like_excel(df_ur['CongeladoPeriodo'].sum(), 2)
        
        disp_anual = round_like_excel(mod_anual - ejercido, 2)
        disp_periodo = round_like_excel(mod_periodo - ejercido, 2)
        
        resultados_por_ur[ur_str] = {
            'Original': original,
            'Modificado_anual': mod_anual,
            'Modificado_periodo': mod_periodo,
            'Ejercido': ejercido,
            'Disponible_anual': disp_anual,
            'Disponible_periodo': disp_periodo,
            'Congelado_anual': cong_anual,
            'Congelado_periodo': cong_periodo,
            'Pct_avance_anual': ejercido / mod_anual if mod_anual > 0 else 0,
            'Pct_avance_periodo': ejercido / mod_periodo if mod_periodo > 0 else 0,
        }
        
        # Por capítulo (2000, 3000, 4000)
        caps = {}
        for cap in [2000, 3000, 4000]:
            df_cap = df_ur[df_ur['Capitulo'] == cap]
            caps[str(cap // 1000)] = {
                'Original': round_like_excel(df_cap['Original'].sum(), 2),
                'Modificado_anual': round_like_excel(df_cap['ModificadoAnualNeto'].sum(), 2),
                'Modificado_periodo': round_like_excel(df_cap['ModificadoPeriodoNeto'].sum(), 2),
                'Ejercido': round_like_excel(df_cap['Ejercido'].sum(), 2),
            }
        capitulos_por_ur[ur_str] = caps
        
        # Top partidas con mayor disponible
        df_part = df_ur.groupby(['PARTIDA', 'Pp']).agg({
            'Original': 'sum',
            'ModificadoAnualNeto': 'sum',
            'ModificadoPeriodoNeto': 'sum',
            'Ejercido': 'sum'
        }).reset_index()
        df_part['Disponible'] = df_part['ModificadoPeriodoNeto'] - df_part['Ejercido']
        df_part = df_part[df_part['Disponible'] > 0].sort_values('Disponible', ascending=False).head(5)
        
        partidas_list = []
        for _, row in df_part.iterrows():
            partidas_list.append({
                'Partida': int(row['PARTIDA']),
                'Programa': row['Pp'],
                'Denom_Programa': config['programas_nombres'].get(row['Pp'], ''),
                'Disponible': round_like_excel(row['Disponible'], 2),
            })
        partidas_por_ur[ur_str] = partidas_list
    
    # =========================================================================
    # RETORNAR RESULTADOS
    # =========================================================================
    
    return {
        'congelados': {
            'valores': congelados_valores,
            'textos': congelados_textos,
        },
        'totales': totales,
        'categorias': categorias,
        'programas': pivot_programas,
        'resultados_por_ur': resultados_por_ur,
        'capitulos_por_ur': capitulos_por_ur,
        'partidas_por_ur': partidas_por_ur,
        'metadata': {
            'fecha_archivo': fecha_archivo,
            'mes': mes_archivo,
            'año': año_archivo,
            'registros': len(df),
            'config': config,
            'es_cierre_año_anterior': es_cierre_año_anterior,
        },
        'df_procesado': df,
    }
