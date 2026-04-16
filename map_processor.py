# ============================================================================
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
        return {'Original': 0, 'ModificadoAnualNeto': 0, 'ModificadoPeriodoNeto': 0, 'Ejercido': 0}
    return {
        'Original':              round_like_excel(filtered['Original'].sum(), 2),
        'ModificadoAnualNeto':   round_like_excel(filtered['ModificadoAnualNeto'].sum(), 2),
        'ModificadoPeriodoNeto': round_like_excel(filtered['ModificadoPeriodoNeto'].sum(), 2),
        'Ejercido':              round_like_excel(filtered['Ejercido'].sum(), 2),
    }


def calcular_congelado_programa(df, programa):
    """Calcula el congelado anual de un programa específico"""
    df_programa = df[df['Pp'] == programa]
    if len(df_programa) == 0:
        return 0
    return round_like_excel(df_programa['CongeladoAnual'].sum(), 2)


def calcular_congelado_periodo_programa(df, programa):
    """Calcula el congelado al periodo de un programa específico"""
    df_programa = df[df['Pp'] == programa]
    if len(df_programa) == 0:
        return 0
    return round_like_excel(df_programa['CongeladoPeriodo'].sum(), 2)


def calcular_congelado_bienes_muebles(df, programas_especificos):
    """
    Calcula el congelado anual y al periodo de Bienes Muebles (caps 5000 y 7000),
    excluyendo los programas específicos (igual que el pivot_cap5000_7000).
    Retorna (congelado_anual, congelado_periodo).
    """
    df_bm = df[
        df['Capitulo'].isin([5000, 7000]) &
        (~df['Pp'].isin(programas_especificos))
    ]
    if df_bm.empty:
        return 0, 0
    anual   = round_like_excel(df_bm['CongeladoAnual'].sum(), 2)
    periodo = round_like_excel(df_bm['CongeladoPeriodo'].sum(), 2)
    return anual, periodo


def procesar_map(df, filename):
    """Procesa un archivo MAP y genera el resumen presupuestario"""

    fecha_archivo, mes_archivo, año_archivo = detectar_fecha_archivo(filename)
    config = get_config_by_year(año_archivo)

    month_names = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC']
    months_up_to_current = month_names[:mes_archivo]

    PROGRAMAS_ESPECIFICOS = config['programas_especificos']
    FUSION_PROGRAMAS = config.get('fusion_programas', {})

    # ── Calcular columnas ────────────────────────────────────────────────────
    df['NuevaUR'] = df['UNIDAD'].apply(
        lambda x: 811 if x == 'G00' else UR_MAP.get(int(x) if str(x).isdigit() else 0, int(x) if str(x).isdigit() else 0)
    )
    df['Pp_Original'] = df['IDEN_PROY'].astype(str) + df['PROYECTO'].astype(str).str.zfill(3)

    def mapear_programa(pp):
        return FUSION_PROGRAMAS.get(pp, pp)

    df['Pp'] = df['Pp_Original'].apply(mapear_programa)

    df['PARTIDA'] = pd.to_numeric(df['PARTIDA'], errors='coerce').fillna(0).astype(int)
    df['Capitulo'] = (df['PARTIDA'] // 10000) * 1000

    for prefix in ['ORI', 'AMP', 'RED', 'MOD', 'CONG', 'DESCONG', 'EJE']:
        for month in month_names:
            col = f'{prefix}_{month}'
            if col in df.columns:
                df[col] = df[col].fillna(0).apply(lambda x: round_like_excel(x, 2))

    # ── Calcular totales ─────────────────────────────────────────────────────
    año_actual = date.today().year
    es_cierre_año_anterior = (mes_archivo in [1, 2]) and (año_archivo < año_actual)

    df['Original']          = sum_columns(df, 'ORI', month_names)
    df['OriginalPeriodo']   = sum_columns(df, 'ORI', months_up_to_current)
    df['ModificadoAnualBruto']   = sum_columns(df, 'MOD', month_names)

    if es_cierre_año_anterior:
        df['ModificadoPeriodoBruto'] = sum_columns(df, 'MOD', month_names)
    else:
        df['ModificadoPeriodoBruto'] = sum_columns(df, 'MOD', months_up_to_current)

    cong_anual   = sum_columns(df, 'CONG', month_names)
    descong_anual = sum_columns(df, 'DESCONG', month_names)

    if es_cierre_año_anterior:
        cong_periodo   = sum_columns(df, 'CONG', month_names)
        descong_periodo = sum_columns(df, 'DESCONG', month_names)
    else:
        cong_periodo   = sum_columns(df, 'CONG', months_up_to_current)
        descong_periodo = sum_columns(df, 'DESCONG', months_up_to_current)

    df['CongeladoAnual']   = (cong_anual - descong_anual).apply(lambda x: round_like_excel(x, 2))
    df['CongeladoPeriodo'] = (cong_periodo - descong_periodo).apply(lambda x: round_like_excel(x, 2))

    mod_anual_sum = sum_columns(df, 'MOD', month_names)
    df['ModificadoAnualNeto'] = (mod_anual_sum - df['CongeladoAnual']).apply(lambda x: round_like_excel(x, 2))

    if es_cierre_año_anterior:
        df['ModificadoPeriodoNeto'] = df['ModificadoAnualNeto'].copy()
    else:
        mod_periodo_sum = sum_columns(df, 'MOD', months_up_to_current)
        df['ModificadoPeriodoNeto'] = (mod_periodo_sum - df['CongeladoPeriodo']).apply(lambda x: round_like_excel(x, 2))

    df['Ejercido']            = sum_columns(df, 'EJE', month_names)
    df['DisponibleAnualNeto'] = (df['ModificadoAnualNeto']   - df['Ejercido']).apply(lambda x: round_like_excel(x, 2))
    df['DisponiblePeriodoNeto'] = (df['ModificadoPeriodoNeto'] - df['Ejercido']).apply(lambda x: round_like_excel(x, 2))

    # ── Congelados por programa (para notas del Excel) ───────────────────────
    programas_con_congelados = ['S263', 'S293', 'S304']
    congelados_valores  = {}
    congelados_textos   = {}
    congelados_valores_periodo = {}
    congelados_textos_periodo  = {}

    for prog in programas_con_congelados:
        valor_anual   = calcular_congelado_programa(df, prog)
        valor_periodo = calcular_congelado_periodo_programa(df, prog)
        congelados_valores[prog]          = valor_anual
        congelados_textos[prog]           = numero_a_letras_mx(valor_anual)
        congelados_valores_periodo[prog]  = valor_periodo
        congelados_textos_periodo[prog]   = numero_a_letras_mx(valor_periodo)

    # ── Congelados de Bienes Muebles (cap 5000+7000) ─────────────────────────
    bm_cong_anual, bm_cong_periodo = calcular_congelado_bienes_muebles(df, PROGRAMAS_ESPECIFICOS)

    # ── Tablas dinámicas ─────────────────────────────────────────────────────
    pivot_cap1000 = crear_pivot_suma(
        df, lambda d: (d['Capitulo'] == 1000) & (~d['Pp'].isin(PROGRAMAS_ESPECIFICOS))
    )
    pivot_cap2000_3000 = crear_pivot_suma(
        df, lambda d: (d['Capitulo'].isin([2000, 3000])) & (~d['Pp'].isin(PROGRAMAS_ESPECIFICOS))
    )

    pivot_programas = {}
    for prog in PROGRAMAS_ESPECIFICOS:
        pivot_programas[prog] = crear_pivot_suma(df, lambda d, p=prog: d['Pp'] == p)

    pivot_cap4000 = crear_pivot_suma(
        df, lambda d: (d['Capitulo'] == 4000) & (~d['Pp'].isin(PROGRAMAS_ESPECIFICOS))
    )
    pivot_cap5000_7000 = crear_pivot_suma(
        df, lambda d: (d['Capitulo'].isin([5000, 7000])) & (~d['Pp'].isin(PROGRAMAS_ESPECIFICOS))
    )

    # ── Subtotales y totales ─────────────────────────────────────────────────
    subtotal_subsidios = {
        'Original':              sum(pivot_programas[p]['Original']              for p in PROGRAMAS_ESPECIFICOS),
        'ModificadoAnualNeto':   sum(pivot_programas[p]['ModificadoAnualNeto']   for p in PROGRAMAS_ESPECIFICOS),
        'ModificadoPeriodoNeto': sum(pivot_programas[p]['ModificadoPeriodoNeto'] for p in PROGRAMAS_ESPECIFICOS),
        'Ejercido':              sum(pivot_programas[p]['Ejercido']              for p in PROGRAMAS_ESPECIFICOS),
    }

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

    categorias = {
        'servicios_personales': pivot_cap1000,
        'gasto_corriente':      pivot_cap2000_3000,
        'subsidios':            subtotal_subsidios,
        'otros_programas':      pivot_cap4000,
        'bienes_muebles':       pivot_cap5000_7000,
    }

    # ── Cálculos por UR para Dashboard Presupuesto ───────────────────────────
    PARTIDAS_EXCLUIR = [39801, 39810]
    df_dashboard = df[(df['Capitulo'] != 1000) & (~df['PARTIDA'].isin(PARTIDAS_EXCLUIR))].copy()

    resultados_por_ur = {}
    capitulos_por_ur  = {}
    partidas_por_ur   = {}

    for ur in df['UNIDAD'].unique():
        ur_str = str(ur).strip()
        df_ur  = df_dashboard[df_dashboard['UNIDAD'].astype(str).str.strip() == ur_str]
        if len(df_ur) == 0:
            continue

        original    = round_like_excel(df_ur['Original'].sum(), 2)
        mod_anual   = round_like_excel(df_ur['ModificadoAnualNeto'].sum(), 2)
        mod_periodo = round_like_excel(df_ur['ModificadoPeriodoNeto'].sum(), 2)
        ejercido    = round_like_excel(df_ur['Ejercido'].sum(), 2)
        cong_anual_ur  = round_like_excel(df_ur['CongeladoAnual'].sum(), 2)
        cong_periodo_ur = round_like_excel(df_ur['CongeladoPeriodo'].sum(), 2)

        disp_anual   = round_like_excel(mod_anual   - ejercido, 2)
        disp_periodo = round_like_excel(mod_periodo - ejercido, 2)

        resultados_por_ur[ur_str] = {
            'Original': original, 'Modificado_anual': mod_anual,
            'Modificado_periodo': mod_periodo, 'Ejercido': ejercido,
            'Disponible_anual': disp_anual, 'Disponible_periodo': disp_periodo,
            'Congelado_anual': cong_anual_ur, 'Congelado_periodo': cong_periodo_ur,
            'Pct_avance_anual':   ejercido / mod_anual   if mod_anual   > 0 else 0,
            'Pct_avance_periodo': ejercido / mod_periodo if mod_periodo > 0 else 0,
        }

        caps = {}
        for cap in [2000, 3000, 4000]:
            df_cap = df_ur[df_ur['Capitulo'] == cap]
            caps[str(cap // 1000)] = {
                'Original':          round_like_excel(df_cap['Original'].sum(), 2),
                'Modificado_anual':  round_like_excel(df_cap['ModificadoAnualNeto'].sum(), 2),
                'Modificado_periodo': round_like_excel(df_cap['ModificadoPeriodoNeto'].sum(), 2),
                'Ejercido':          round_like_excel(df_cap['Ejercido'].sum(), 2),
            }
        capitulos_por_ur[ur_str] = caps

        df_part = df_ur.groupby(['PARTIDA', 'Pp']).agg({
            'Original': 'sum', 'ModificadoAnualNeto': 'sum',
            'ModificadoPeriodoNeto': 'sum', 'Ejercido': 'sum'
        }).reset_index()
        df_part['Disponible'] = df_part['ModificadoPeriodoNeto'] - df_part['Ejercido']
        df_part = df_part[df_part['Disponible'] > 0].sort_values('Disponible', ascending=False).head(5)

        partidas_list = []
        for _, row in df_part.iterrows():
            partidas_list.append({
                'Partida':       int(row['PARTIDA']),
                'Programa':      row['Pp'],
                'Denom_Programa': config['programas_nombres'].get(row['Pp'], ''),
                'Disponible':    round_like_excel(row['Disponible'], 2),
            })
        partidas_por_ur[ur_str] = partidas_list

    # ── Return ───────────────────────────────────────────────────────────────
    return {
        'congelados': {
            'valores':          congelados_valores,
            'textos':           congelados_textos,
            'valores_periodo':  congelados_valores_periodo,
            'textos_periodo':   congelados_textos_periodo,
            # Bienes muebles
            'bm_anual':         bm_cong_anual,
            'bm_anual_texto':   numero_a_letras_mx(bm_cong_anual)   if bm_cong_anual   > 0 else '',
            'bm_periodo':       bm_cong_periodo,
            'bm_periodo_texto': numero_a_letras_mx(bm_cong_periodo) if bm_cong_periodo > 0 else '',
        },
        'totales':    totales,
        'categorias': categorias,
        'programas':  pivot_programas,
        'resultados_por_ur': resultados_por_ur,
        'capitulos_por_ur':  capitulos_por_ur,
        'partidas_por_ur':   partidas_por_ur,
        'metadata': {
            'fecha_archivo':          fecha_archivo,
            'mes':                    mes_archivo,
            'año':                    año_archivo,
            'registros':              len(df),
            'config':                 config,
            'es_cierre_año_anterior': es_cierre_año_anterior,
        },
        'df_procesado': df,
    }
