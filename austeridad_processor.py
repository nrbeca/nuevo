# ============================================================================
# PROCESADOR DE ARCHIVOS PARA DASHBOARD DE AUSTERIDAD
# ============================================================================

import pandas as pd
import numpy as np
from datetime import date
from config import (
    round_like_excel, PARTIDAS_AUSTERIDAD, DENOMINACIONES_AUSTERIDAD,
    CUENTA_PUBLICA_2025, FUSION_URS_2026, MAPEO_UR_2026_BASE
)


def procesar_cuenta_publica(df):
    if len(df.columns) >= 5:
        df.columns = ['Concatenación', 'ID_UNIDAD', 'Nueva_UR', 'Partida', 'Ejercido_Inflacion']
    df = df[~df['Concatenación'].astype(str).str.contains('Concatenación|Total|general', na=False, case=False)]
    df['Ejercido_Inflacion'] = pd.to_numeric(df['Ejercido_Inflacion'], errors='coerce').fillna(0)
    resultado = {}
    for _, row in df.iterrows():
        concat = str(row['Concatenación']).strip()
        ejercido = row['Ejercido_Inflacion']
        if concat in resultado:
            resultado[concat] = round_like_excel(resultado[concat] + ejercido, 2)
        else:
            resultado[concat] = round_like_excel(ejercido, 2)
    return resultado


def _aplicar_mapeo_ur(id_unidad_str):
    """
    Aplica el mapeo base y las fusiones 2026 a una UR, igual que sicop_processor.
    Convierte UR antiguas (225, 226, 230…) a las nuevas (900, 921, 920…).
    """
    id_str = id_unidad_str
    # Mapeo base (numérico → nuevo código)
    if id_str.isdigit():
        id_int = int(id_str)
        if id_int in MAPEO_UR_2026_BASE:
            id_str = str(MAPEO_UR_2026_BASE[id_int])
    elif id_unidad_str in MAPEO_UR_2026_BASE:
        id_str = str(MAPEO_UR_2026_BASE[id_unidad_str])
    # Fusión 2026
    if id_str in FUSION_URS_2026:
        id_str = FUSION_URS_2026[id_str]
    return id_str


def procesar_sicop_austeridad(df):
    """
    Procesa el archivo SICOP diario para obtener Original, Modificado y Ejercido Real
    para las partidas de austeridad.

    Correcciones:
    - Aplica mapeo y fusiones de URs 2026 (igual que sicop_processor)
    - Ejercido Real = EJERCIDO + DEVENGADO + EJERCIDO_TRAMITE
    - Excluye CONTROL_OPERATIVO entre 60 y 69
    - ORIGINAL solo desde filas con CONTROL_OPERATIVO = 0
    """
    if 'ID_UNIDAD' in df.columns and 'PARTIDA_ESPECIFICA' in df.columns:
        df = df.copy()

        # Construir partida completa
        df['Partida'] = (
            df['CAPITULO'].astype(int) * 10000 +
            df['CONCEPTO'].astype(int) * 1000 +
            df['PARTIDA_GENERICA'].astype(int) * 100 +
            df['PARTIDA_ESPECIFICA'].astype(int)
        )

        # Filtrar solo partidas de austeridad
        df = df[df['Partida'].isin(PARTIDAS_AUSTERIDAD)]

        # Excluir controles operativos 60-69
        df = df[~df['CONTROL_OPERATIVO'].between(60, 69)]

        # Convertir columnas numéricas
        for col in ['ORIGINAL', 'MODIFICADO_AUTORIZADO', 'EJERCIDO', 'DEVENGADO', 'EJERCIDO_TRAMITE']:
            if col not in df.columns:
                df[col] = 0
            else:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Ejercido Real = suma de las tres columnas
        df['_EJERCIDO_REAL'] = df['EJERCIDO'] + df['DEVENGADO'] + df['EJERCIDO_TRAMITE']

        # Aplicar mapeo/fusión de URs 2026
        df['Nueva_UR'] = df['ID_UNIDAD'].astype(str).apply(_aplicar_mapeo_ur)

        # ORIGINAL: solo desde COP = 0
        df_orig = (
            df[df['CONTROL_OPERATIVO'] == 0]
            .assign(Concat=lambda x: x['Nueva_UR'] + x['Partida'].astype(str))
            .groupby('Concat')['ORIGINAL']
            .sum()
            .reset_index()
            .rename(columns={'ORIGINAL': '_ORIGINAL'})
        )

        # Modificado y Ejercido: todos los COP (ya excluidos 60-69)
        df['Concat'] = df['Nueva_UR'] + df['Partida'].astype(str)
        grouped = df.groupby('Concat').agg(
            MODIFICADO=('MODIFICADO_AUTORIZADO', 'sum'),
            EJERCIDO=('_EJERCIDO_REAL', 'sum'),
        ).reset_index()

        # Unir ORIGINAL
        grouped = grouped.merge(df_orig, on='Concat', how='left')
        grouped['_ORIGINAL'] = grouped['_ORIGINAL'].fillna(0)

        resultado = {}
        for _, row in grouped.iterrows():
            concat = str(row['Concat']).strip()
            resultado[concat] = {
                'Original':  round_like_excel(row['_ORIGINAL'], 2),
                'Modificado': round_like_excel(row['MODIFICADO'], 2),
                'Ejercido':  round_like_excel(row['EJERCIDO'], 2),
            }
        return resultado

    else:
        # Formato tabla dinámica (legacy)
        if len(df.columns) >= 4:
            df.columns = ['Concatenación', 'Original', 'Modificado', 'Ejercido_Real']
        df = df[~df['Concatenación'].astype(str).str.contains('Etiqueta|Total|general', na=False, case=False)]
        for col in ['Original', 'Modificado', 'Ejercido_Real']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        resultado = {}
        for _, row in df.iterrows():
            concat = str(row['Concatenación']).strip()
            resultado[concat] = {
                'Original':  round_like_excel(row['Original'], 2),
                'Modificado': round_like_excel(row['Modificado'], 2),
                'Ejercido':  round_like_excel(row['Ejercido_Real'], 2),
            }
        return resultado


def calcular_nota(ejercido_anterior, ejercido_real, modificado, solicitud_pago=0):
    C, E, F, G = ejercido_anterior, modificado, ejercido_real, solicitud_pago
    if F > C and C > 0:
        return "Monto ejercido real mayor al presupuesto ejercido en 2025."
    if C == 0 and E > 0:
        return "Solicitar dictamen antes de ejercer recursos en esta partida."
    if C == 0 and F > 0:
        return "Monto ejercido real mayor al presupuesto ejercido en 2025."
    if (F + G) > C and C > 0:
        return "Solicitar dictamen antes de ejercer recursos en esta partida."
    if C == 0 and E == 0 and F == 0:
        return None
    if E > C and F < C:
        return "Solicitar dictamen antes de sobrepasar el monto ejercido en 2025."
    return "Sin observaciones."


def calcular_avance_anual(ejercido_anterior, ejercido_real, solicitud_pago=0):
    C, F, G = ejercido_anterior, ejercido_real, solicitud_pago
    if C == 0 and (F > 0 or G > 0):
        return "Incremento en presupuesto"
    if C == 0:
        return None
    return round_like_excel((F + G) / C, 6)


def generar_dashboard_austeridad(datos_cp, datos_sicop, ur_filtro):
    if datos_cp is None:
        datos_cp = CUENTA_PUBLICA_2025
    resultado = []
    for partida in PARTIDAS_AUSTERIDAD:
        concat_cp    = f"{partida}{ur_filtro}"
        concat_sicop = f"{ur_filtro}{partida}"
        ejercido_anterior = datos_cp.get(concat_cp, 0)
        sicop_data   = datos_sicop.get(concat_sicop, {'Original': 0, 'Modificado': 0, 'Ejercido': 0})
        original      = sicop_data['Original']
        modificado    = sicop_data['Modificado']
        ejercido_real = sicop_data['Ejercido']
        solicitud_pago = 0
        nota   = calcular_nota(ejercido_anterior, ejercido_real, modificado, solicitud_pago)
        avance = calcular_avance_anual(ejercido_anterior, ejercido_real, solicitud_pago)
        resultado.append({
            'Partida':           partida,
            'Denominacion':      DENOMINACIONES_AUSTERIDAD.get(partida, ''),
            'Ejercido_Anterior': ejercido_anterior,
            'Original':          original,
            'Modificado':        modificado,
            'Ejercido_Real':     ejercido_real,
            'Solicitud_Pago':    solicitud_pago,
            'Nota':              nota,
            'Avance_Anual':      avance,
        })
    return resultado


def generar_dashboard_austeridad_desde_sicop(datos_sicop, ur_filtro):
    return generar_dashboard_austeridad(None, datos_sicop, ur_filtro)


def obtener_urs_disponibles_cp(datos_cp):
    urs = set()
    for concat in datos_cp.keys():
        if len(concat) > 5:
            urs.add(concat[5:])
    urs_num   = sorted([ur for ur in urs if ur.isdigit()], key=lambda x: int(x))
    urs_alpha = sorted([ur for ur in urs if not ur.isdigit()])
    return urs_num + urs_alpha


def obtener_urs_disponibles_sicop(datos_sicop):
    urs = set()
    for concat in datos_sicop.keys():
        if len(concat) > 5:
            urs.add(concat[:-5])
    urs_num   = sorted([ur for ur in urs if ur.isdigit()], key=lambda x: int(x))
    urs_alpha = sorted([ur for ur in urs if not ur.isdigit()])
    return urs_num + urs_alpha


def obtener_urs_disponibles(datos_cp, datos_sicop):
    urs = set(obtener_urs_disponibles_cp(datos_cp)).union(
          set(obtener_urs_disponibles_sicop(datos_sicop)))
    urs_num   = sorted([ur for ur in urs if ur.isdigit()], key=lambda x: int(x))
    urs_alpha = sorted([ur for ur in urs if not ur.isdigit()])
    return urs_num + urs_alpha
