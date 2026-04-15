# ============================================================================
# PROCESADOR DE ARCHIVOS PARA DASHBOARD DE AUSTERIDAD
# ============================================================================
# 
# Fuentes de datos (del archivo Tablero.xlsx):
# - Tabla Cuenta Pública: Ejercido año anterior (con inflación)
#   Concatenación: Partida + UR (ej: "21101100")
# - Tabla SICOP: Original, Modificado, Ejercido Real del año actual
#   Concatenación: UR + Partida (ej: "10021101")
#
# ============================================================================

import pandas as pd
import numpy as np
from datetime import date
from config import (
    round_like_excel, PARTIDAS_AUSTERIDAD, DENOMINACIONES_AUSTERIDAD,
    CUENTA_PUBLICA_2025
)


def procesar_cuenta_publica(df):
    """
    Procesa la Tabla de Cuenta Pública para obtener el ejercido del año anterior.
    
    La tabla tiene la estructura (después de header):
    - Concatenación: Partida + ID_UNIDAD (ej: "21101100")
    - ID_UNIDAD: Unidad responsable original
    - Nueva_UR: Nueva clave de UR (mapeo)
    - Partida: Partida presupuestaria (5 dígitos)
    - Suma de Ejercido con inflación: Monto ejercido con factor de inflación
    
    Para buscar: CONCATENAR(Partida, UR) → ej: "21101100"
    
    Returns:
        dict: {concatenacion: ejercido} donde concatenacion = "PartidaUR"
    """
    # Normalizar nombres de columnas
    if len(df.columns) >= 5:
        df.columns = ['Concatenación', 'ID_UNIDAD', 'Nueva_UR', 'Partida', 'Ejercido_Inflacion']
    
    # Eliminar filas de encabezado o totales
    df = df[~df['Concatenación'].astype(str).str.contains('Concatenación|Total|general', na=False, case=False)]
    
    # Convertir tipos
    df['Ejercido_Inflacion'] = pd.to_numeric(df['Ejercido_Inflacion'], errors='coerce').fillna(0)
    
    # Crear diccionario con concatenación Partida+UR como clave
    # La concatenación ya viene en el formato correcto (PartidaUR)
    resultado = {}
    for _, row in df.iterrows():
        concat = str(row['Concatenación']).strip()
        ejercido = row['Ejercido_Inflacion']
        # Acumular si hay duplicados
        if concat in resultado:
            resultado[concat] = round_like_excel(resultado[concat] + ejercido, 2)
        else:
            resultado[concat] = round_like_excel(ejercido, 2)
    
    return resultado


def procesar_sicop_austeridad(df):
    """
    Procesa el archivo SICOP diario (CSV crudo) para obtener Original, Modificado y Ejercido Real
    para las partidas de austeridad.
    
    El archivo SICOP tiene columnas como:
    - ID_UNIDAD: Unidad responsable
    - PARTIDA_ESPECIFICA: Partida presupuestaria (5 dígitos)
    - ORIGINAL: Presupuesto original
    - MODIFICADO_AUTORIZADO: Modificado anual bruto
    - EJERCIDO: Ejercido real
    
    La concatenación para búsqueda es: UR + Partida (ej: "10021101")
    
    Returns:
        dict: {concatenacion: {'Original': x, 'Modificado': y, 'Ejercido': z}}
              donde concatenacion = "URPartida"
    """
    # Verificar si es el archivo SICOP crudo o una tabla dinámica
    if 'ID_UNIDAD' in df.columns and 'PARTIDA_ESPECIFICA' in df.columns:
        # Es el archivo SICOP crudo
        # Construir partida completa
        df = df.copy()
        
        # Crear partida completa de 5 dígitos
        df['Partida'] = (
            df['CAPITULO'].astype(int) * 10000 +
            df['CONCEPTO'].astype(int) * 1000 +
            df['PARTIDA_GENERICA'].astype(int) * 100 +
            df['PARTIDA_ESPECIFICA'].astype(int)
        )
        
        # Filtrar solo partidas de austeridad
        df = df[df['Partida'].isin(PARTIDAS_AUSTERIDAD)]
        
        # Convertir columnas numéricas
        for col in ['ORIGINAL', 'MODIFICADO_AUTORIZADO', 'EJERCIDO']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Agrupar por UR + Partida
        df['Concatenacion'] = df['ID_UNIDAD'].astype(str) + df['Partida'].astype(str)
        
        # Sumar por concatenación
        grouped = df.groupby('Concatenacion').agg({
            'ORIGINAL': 'sum',
            'MODIFICADO_AUTORIZADO': 'sum',
            'EJERCIDO': 'sum'
        }).reset_index()
        
        # Crear diccionario de resultados
        resultado = {}
        for _, row in grouped.iterrows():
            concat = str(row['Concatenacion']).strip()
            resultado[concat] = {
                'Original': round_like_excel(row['ORIGINAL'], 2),
                'Modificado': round_like_excel(row['MODIFICADO_AUTORIZADO'], 2),
                'Ejercido': round_like_excel(row['EJERCIDO'], 2),
            }
        
        return resultado
    
    else:
        # Asumir que es una tabla dinámica (formato anterior)
        # Normalizar nombres de columnas
        if len(df.columns) >= 4:
            df.columns = ['Concatenación', 'Original', 'Modificado', 'Ejercido_Real']
        
        # Eliminar filas de encabezado o totales
        df = df[~df['Concatenación'].astype(str).str.contains('Etiqueta|Total|general', na=False, case=False)]
        
        # Convertir tipos
        df['Original'] = pd.to_numeric(df['Original'], errors='coerce').fillna(0)
        df['Modificado'] = pd.to_numeric(df['Modificado'], errors='coerce').fillna(0)
        df['Ejercido_Real'] = pd.to_numeric(df['Ejercido_Real'], errors='coerce').fillna(0)
        
        # Crear diccionario con concatenación UR+Partida como clave
        resultado = {}
        for _, row in df.iterrows():
            concat = str(row['Concatenación']).strip()
            resultado[concat] = {
                'Original': round_like_excel(row['Original'], 2),
                'Modificado': round_like_excel(row['Modificado'], 2),
                'Ejercido': round_like_excel(row['Ejercido_Real'], 2),
            }
        
        return resultado


def calcular_nota(ejercido_anterior, ejercido_real, modificado, solicitud_pago=0):
    """
    Calcula la nota/observación para una partida.
    
    Lógica de Excel:
    =SI(Y(F>C),"Monto ejercido real mayor al presupuesto ejercido en 2024.",
      SI(Y(C=0,E>0),"Solicitar dictamen antes de ejercer recursos en esta partida.",
        SI(Y(C=0,F>0),"Monto ejercido real mayor al presupuesto ejercido en 2024.",
          SI(Y(F+G>C),"Solicitar dictamen antes de ejercer recursos en esta partida.",
            SI(Y(C+E+F=0),"",
              SI(Y(E>C,F<C),"Solicitar dictamen antes de sobrepasar el monto ejercido en 2024.",
                "Sin observaciones."))))))
    
    Donde:
    C = Ejercido año anterior (2024)
    E = Modificado
    F = Ejercido Real
    G = Solicitud de pago
    
    Returns:
        str o None
    """
    C = ejercido_anterior
    E = modificado
    F = ejercido_real
    G = solicitud_pago
    
    # Condición 1: F > C → Monto ejercido real mayor al presupuesto ejercido en 2024
    if F > C and C > 0:
        return "Monto ejercido real mayor al presupuesto ejercido en 2024."
    
    # Condición 2: C = 0 y E > 0 → Solicitar dictamen antes de ejercer
    if C == 0 and E > 0:
        return "Solicitar dictamen antes de ejercer recursos en esta partida."
    
    # Condición 3: C = 0 y F > 0 → Monto ejercido real mayor
    if C == 0 and F > 0:
        return "Monto ejercido real mayor al presupuesto ejercido en 2024."
    
    # Condición 4: F + G > C → Solicitar dictamen antes de ejercer
    if (F + G) > C and C > 0:
        return "Solicitar dictamen antes de ejercer recursos en esta partida."
    
    # Condición 5: C + E + F = 0 → vacío
    if C == 0 and E == 0 and F == 0:
        return None
    
    # Condición 6: E > C y F < C → Solicitar dictamen antes de sobrepasar
    if E > C and F < C:
        return "Solicitar dictamen antes de sobrepasar el monto ejercido en 2024."
    
    # Default: Sin observaciones
    return "Sin observaciones."


def calcular_avance_anual(ejercido_anterior, ejercido_real, solicitud_pago=0):
    """
    Calcula el porcentaje de avance anual.
    
    Fórmula Excel:
    =SI(Y(C=0,(F>0)+G),"Incremento en presupuesto",(SI.ERROR(((F+G)/C),"")))
    
    Donde:
    C = Ejercido año anterior
    F = Ejercido Real
    G = Solicitud de pago
    
    Returns:
        float, str o None
    """
    C = ejercido_anterior
    F = ejercido_real
    G = solicitud_pago
    
    # Si C = 0 y (F > 0 o G > 0) → "Incremento en presupuesto"
    if C == 0 and (F > 0 or G > 0):
        return "Incremento en presupuesto"
    
    # Si C = 0 → vacío
    if C == 0:
        return None
    
    # Calcular porcentaje
    return round_like_excel((F + G) / C, 6)


def generar_dashboard_austeridad(datos_cp, datos_sicop, ur_filtro):
    """
    Genera los datos para el Dashboard de Austeridad de una UR específica.
    
    Args:
        datos_cp: Resultado de procesar_cuenta_publica() - dict {PartidaUR: ejercido}
                  O None para usar CUENTA_PUBLICA_2025 precargado
        datos_sicop: Resultado de procesar_sicop_austeridad() - dict {URPartida: {Original, Modificado, Ejercido}}
        ur_filtro: UR a filtrar (ej: '100')
    
    Returns:
        list: Lista de dicts con los datos de cada partida
    """
    # Usar datos precargados si no se proporcionan
    if datos_cp is None:
        datos_cp = CUENTA_PUBLICA_2025
    
    resultado = []
    
    for partida in PARTIDAS_AUSTERIDAD:
        # Concatenaciones para búsqueda
        # Cuenta Pública: Partida + UR (ej: "21101100")
        concat_cp = f"{partida}{ur_filtro}"
        # SICOP: UR + Partida (ej: "10021101")
        concat_sicop = f"{ur_filtro}{partida}"
        
        # Ejercido año anterior (Cuenta Pública)
        ejercido_anterior = datos_cp.get(concat_cp, 0)
        
        # Año actual (SICOP)
        sicop_data = datos_sicop.get(concat_sicop, {'Original': 0, 'Modificado': 0, 'Ejercido': 0})
        original = sicop_data['Original']
        modificado = sicop_data['Modificado']
        ejercido_real = sicop_data['Ejercido']
        
        # Solicitud de pago (se deja en 0, es input manual)
        solicitud_pago = 0
        
        # Calcular nota y avance
        nota = calcular_nota(ejercido_anterior, ejercido_real, modificado, solicitud_pago)
        avance = calcular_avance_anual(ejercido_anterior, ejercido_real, solicitud_pago)
        
        resultado.append({
            'Partida': partida,
            'Denominacion': DENOMINACIONES_AUSTERIDAD.get(partida, ''),
            'Ejercido_Anterior': ejercido_anterior,
            'Original': original,
            'Modificado': modificado,
            'Ejercido_Real': ejercido_real,
            'Solicitud_Pago': solicitud_pago,
            'Nota': nota,
            'Avance_Anual': avance,
        })
    
    return resultado


def generar_dashboard_austeridad_desde_sicop(datos_sicop, ur_filtro):
    """
    Genera el Dashboard de Austeridad usando solo datos del SICOP diario
    y los datos precargados de Cuenta Pública 2025.
    
    Args:
        datos_sicop: Resultado de procesar_sicop_austeridad() - dict {URPartida: {Original, Modificado, Ejercido}}
        ur_filtro: UR a filtrar (ej: '100')
    
    Returns:
        list: Lista de dicts con los datos de cada partida
    """
    return generar_dashboard_austeridad(None, datos_sicop, ur_filtro)


def obtener_urs_disponibles_cp(datos_cp):
    """
    Obtiene la lista de URs disponibles en Cuenta Pública.
    
    La concatenación es PartidaUR, así que extraemos los últimos 3 caracteres
    para URs de 3 dígitos o lo que reste después de la partida de 5 dígitos.
    
    Returns:
        list: Lista de URs únicas ordenadas
    """
    urs = set()
    for concat in datos_cp.keys():
        # La partida es de 5 dígitos, el resto es la UR
        if len(concat) > 5:
            ur = concat[5:]  # Todo después de los 5 dígitos de partida
            urs.add(ur)
    
    # Separar numéricas de alfanuméricas
    urs_num = sorted([ur for ur in urs if ur.isdigit()], key=lambda x: int(x))
    urs_alpha = sorted([ur for ur in urs if not ur.isdigit()])
    
    return urs_num + urs_alpha


def obtener_urs_disponibles_sicop(datos_sicop):
    """
    Obtiene la lista de URs disponibles en SICOP.
    
    La concatenación es URPartida, así que extraemos todo menos los últimos 5 dígitos.
    
    Returns:
        list: Lista de URs únicas ordenadas
    """
    urs = set()
    for concat in datos_sicop.keys():
        # La partida es de 5 dígitos al final
        if len(concat) > 5:
            ur = concat[:-5]  # Todo antes de los últimos 5 dígitos
            urs.add(ur)
    
    # Separar numéricas de alfanuméricas
    urs_num = sorted([ur for ur in urs if ur.isdigit()], key=lambda x: int(x))
    urs_alpha = sorted([ur for ur in urs if not ur.isdigit()])
    
    return urs_num + urs_alpha


def obtener_urs_disponibles(datos_cp, datos_sicop):
    """
    Obtiene la lista de URs disponibles en ambas fuentes (intersección).
    
    Returns:
        list: Lista de URs ordenadas que existen en ambas fuentes
    """
    urs_cp = set(obtener_urs_disponibles_cp(datos_cp))
    urs_sicop = set(obtener_urs_disponibles_sicop(datos_sicop))
    
    # Usar unión para mostrar todas las URs disponibles
    urs = urs_cp.union(urs_sicop)
    
    # Separar numéricas de alfanuméricas
    urs_num = sorted([ur for ur in urs if ur.isdigit()], key=lambda x: int(x))
    urs_alpha = sorted([ur for ur in urs if not ur.isdigit()])
    
    return urs_num + urs_alpha
