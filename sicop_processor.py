# ============================================================================
# PROCESADOR DE ARCHIVOS SICOP
# ============================================================================

import pandas as pd
import numpy as np
from datetime import date
from config import (
    MONTH_NAMES, round_like_excel, detectar_fecha_archivo,
    get_config_by_year, numero_a_letras_mx
)


def obtener_columnas_hasta_mes(mes_numero):
    todos_los_meses = [
        ('EN', 'ENE'), ('FE', 'FEB'), ('MR', 'MZO'), ('AB', 'ABR'),
        ('MY', 'MAY'), ('JN', 'JUN'), ('JL', 'JUL'), ('AG', 'AGO'),
        ('SE', 'SEP'), ('OC', 'OCT'), ('NO', 'NOV'), ('DI', 'DIC')
    ]
    meses_usar = todos_los_meses[:mes_numero]
    return {
        'modificaciones': [f'MO{abrev}' for abrev, _ in meses_usar],
        'reservas': [f'RESERVA_{completo}' for _, completo in meses_usar],
    }


def calcular_congelado_anual(df):
    todos_meses = ['ENE', 'FEB', 'MZO', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC']
    cols = [f'RESERVA_{mes}' for mes in todos_meses if f'RESERVA_{mes}' in df.columns]
    if cols:
        return round_like_excel(df[cols].sum(axis=1).sum(), 2)
    return 0


def calcular_congelado_periodo(df, mes_numero):
    cols_a_usar = obtener_columnas_hasta_mes(mes_numero)
    cols = [col for col in cols_a_usar['reservas'] if col in df.columns]
    if cols:
        return round_like_excel(df[cols].sum(axis=1).sum(), 2)
    return 0


def mapear_ur(id_unidad, config):
    id_str = str(id_unidad)
    mapeo_base = config['mapeo_ur']
    fusion_urs = config.get('fusion_urs', {})
    if id_unidad in mapeo_base:
        id_str = str(mapeo_base[id_unidad])
    elif id_str.isdigit() and int(id_str) in mapeo_base:
        id_str = str(mapeo_base[int(id_str)])
    if config['usar_2026'] and id_str in fusion_urs:
        return fusion_urs[id_str]
    return id_str


def get_co_filter_for_ur(ur, config, for_original=False):
    """
    Para ORIGINAL: siempre CO == 0
    Para MODIFICADO y EJERCIDO: todos los COPs excepto los que empiezan en 6
    (62, 67, 68 son operaciones de traspaso que no deben sumarse al ejercicio)
    """
    if for_original:
        return [0]
    return [0, 10, 40, 50, 51]


def procesar_sicop(df, filename):
    fecha_archivo, mes_archivo, año_archivo = detectar_fecha_archivo(filename)
    config = get_config_by_year(año_archivo)

    año_actual = date.today().year
    es_cierre_año_anterior = (mes_archivo in [1, 2]) and (año_archivo < año_actual)

    df['ID_UNIDAD'] = df['ID_UNIDAD'].astype(str)
    df['Nueva UR'] = df['ID_UNIDAD'].apply(lambda x: mapear_ur(x, config))
    df['Nueva UR'] = df['Nueva UR'].astype(str)

    # CORRECTO — equivalente a CONCATENAR(J,K,L,TEXTO(M,"0#"))
    df['Partida'] = df.apply(
       lambda r: int(
           str(int(r['CAPITULO'])) + str(int(r['CONCEPTO'])) +
           str(int(r['PARTIDA_GENERICA'])) + f"{int(r['PARTIDA_ESPECIFICA']):02d}"
       ), axis=1
    )

    for col in ['EJERCIDO', 'DEVENGADO', 'EJERCIDO_TRAMITE']:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = df[col].fillna(0)

    df['EJERCIDO_REAL'] = df['EJERCIDO'] + df['DEVENGADO'] + df['EJERCIDO_TRAMITE']

    urs_validas = (config['sector_central'] + config['oficinas'] +
                   config['organos_desconcentrados'] + config['entidades_paraestatales'])

    df_para_congelados = df.copy()
    df_para_cop_62_67 = df.copy()

    urs_validas_str = [str(ur) for ur in urs_validas]
    df = df[df['Nueva UR'].isin(urs_validas_str)].copy()
    df = df[~df['Partida'].isin([39801])].copy()
    df = df[~df['CAPITULO'].isin([1])].copy()
    # Excluir COPs que empiezan en 6 (62, 67, 68...)
    df = df[~df['CONTROL_OPERATIVO'].between(60, 69)].copy()

    resultados_ur = {}

    for ur in urs_validas:
        df_ur = df[df['Nueva UR'].astype(str) == ur].copy()

        if len(df_ur) == 0:
            resultados_ur[ur] = {
                'Original': 0, 'Modificado_anual': 0, 'Modificado_periodo': 0, 'Ejercido': 0
            }
            continue

        df_ur['Modificado_neto'] = df_ur['MODIFICADO_AUTORIZADO'] - df_ur['RESERVAS']

        # ORIGINAL: CO=0
        df_co0 = df_ur[df_ur['CONTROL_OPERATIVO'] == 0]
        original = round_like_excel(df_co0['ORIGINAL'].sum(), 2)

        # MODIFICADO y EJERCIDO: todos los COPs válidos (ya filtrados en df)
        df_modificado = df_ur
        modificado_anual = round_like_excel(df_modificado['Modificado_neto'].sum(), 2)

        if es_cierre_año_anterior or mes_archivo == 12:
            modificado_periodo = modificado_anual
        else:
            cols_a_usar = obtener_columnas_hasta_mes(mes_archivo)
            cols_mod = [col for col in cols_a_usar['modificaciones'] if col in df_modificado.columns]
            cols_res = [col for col in cols_a_usar['reservas'] if col in df_modificado.columns]
            mod_bruto = df_modificado[cols_mod].sum(axis=1).sum() if cols_mod else 0
            cong_periodo = df_modificado[cols_res].sum(axis=1).sum() if cols_res else 0
            modificado_periodo = round_like_excel(mod_bruto - cong_periodo, 2)

        ejercido = round_like_excel(df_ur['EJERCIDO_REAL'].sum(), 2)

        resultados_ur[ur] = {
            'Original': original,
            'Modificado_anual': modificado_anual,
            'Modificado_periodo': modificado_periodo,
            'Ejercido': ejercido
        }

    resumen = pd.DataFrame.from_dict(resultados_ur, orient='index').reset_index()
    resumen.columns = ['UR', 'Original', 'Modificado_anual', 'Modificado_periodo', 'Ejercido_acumulado']

    resumen['Disponible_anual'] = resumen.apply(
        lambda row: round_like_excel(row['Modificado_anual'] - row['Ejercido_acumulado'], 2), axis=1
    )
    resumen['Disponible_periodo'] = resumen.apply(
        lambda row: round_like_excel(row['Modificado_periodo'] - row['Ejercido_acumulado'], 2), axis=1
    )
    resumen['Pct_avance_anual'] = resumen.apply(
        lambda row: row['Ejercido_acumulado'] / row['Modificado_anual'] if row['Modificado_anual'] != 0 else 0, axis=1
    )
    resumen['Pct_avance_periodo'] = resumen.apply(
        lambda row: row['Ejercido_acumulado'] / row['Modificado_periodo'] if row['Modificado_periodo'] != 0 else 0, axis=1
    )

    def calcular_subtotal(urs_lista):
        df_seccion = resumen[resumen['UR'].isin(urs_lista)]
        subtotal = {
            'Original': df_seccion['Original'].sum(),
            'Modificado_anual': df_seccion['Modificado_anual'].sum(),
            'Modificado_periodo': df_seccion['Modificado_periodo'].sum(),
            'Ejercido_acumulado': df_seccion['Ejercido_acumulado'].sum(),
            'Disponible_anual': df_seccion['Disponible_anual'].sum(),
            'Disponible_periodo': df_seccion['Disponible_periodo'].sum(),
        }
        subtotal['Pct_avance_anual'] = subtotal['Ejercido_acumulado'] / subtotal['Modificado_anual'] if subtotal['Modificado_anual'] != 0 else 0
        subtotal['Pct_avance_periodo'] = subtotal['Ejercido_acumulado'] / subtotal['Modificado_periodo'] if subtotal['Modificado_periodo'] != 0 else 0
        return subtotal

    subtotal_sc = calcular_subtotal(config['sector_central'])
    subtotal_of = calcular_subtotal(config['oficinas'])
    subtotal_od = calcular_subtotal(config['organos_desconcentrados'])
    subtotal_ep = calcular_subtotal(config['entidades_paraestatales'])

    total_general = {
        'Original': subtotal_sc['Original'] + subtotal_of['Original'] + subtotal_od['Original'] + subtotal_ep['Original'],
        'Modificado_anual': subtotal_sc['Modificado_anual'] + subtotal_of['Modificado_anual'] + subtotal_od['Modificado_anual'] + subtotal_ep['Modificado_anual'],
        'Modificado_periodo': subtotal_sc['Modificado_periodo'] + subtotal_of['Modificado_periodo'] + subtotal_od['Modificado_periodo'] + subtotal_ep['Modificado_periodo'],
        'Ejercido_acumulado': subtotal_sc['Ejercido_acumulado'] + subtotal_of['Ejercido_acumulado'] + subtotal_od['Ejercido_acumulado'] + subtotal_ep['Ejercido_acumulado'],
        'Disponible_anual': subtotal_sc['Disponible_anual'] + subtotal_of['Disponible_anual'] + subtotal_od['Disponible_anual'] + subtotal_ep['Disponible_anual'],
        'Disponible_periodo': subtotal_sc['Disponible_periodo'] + subtotal_of['Disponible_periodo'] + subtotal_od['Disponible_periodo'] + subtotal_ep['Disponible_periodo'],
    }
    total_general['Pct_avance_anual'] = total_general['Ejercido_acumulado'] / total_general['Modificado_anual'] if total_general['Modificado_anual'] != 0 else 0
    total_general['Pct_avance_periodo'] = total_general['Ejercido_acumulado'] / total_general['Modificado_periodo'] if total_general['Modificado_periodo'] != 0 else 0

    # Congelados
    df_para_congelados = df_para_congelados[df_para_congelados['Nueva UR'].astype(str).isin(urs_validas)]
    df_para_congelados = df_para_congelados[~df_para_congelados['Partida'].isin([39801])]
    df_para_congelados = df_para_congelados[~df_para_congelados['CAPITULO'].isin([1])]

    congelado_anual = calcular_congelado_anual(df_para_congelados)
    congelado_periodo = calcular_congelado_periodo(df_para_congelados, mes_archivo)

    # =========================================================================
    # CALCULOS POR UR PARA DASHBOARD PRESUPUESTO
    # =========================================================================

    catalogo_partidas = {
        21101: 'Materiales y Útiles de Oficina',
        21401: 'Materiales y Útiles Consumibles para el Procesamiento en Equipos y Bienes Informáticos',
        21501: 'Material de Apoyo Informativo',
        22102: 'Productos Alimenticios para Personas Derivado de la Prestación de Servicios Públicos',
        22103: 'Productos Alimenticios para el Personal que Realiza Labores en Campo o de Supervisión',
        22104: 'Productos Alimenticios para el Personal en las Instalaciones de las Dependencias y Entidades',
        22106: 'Productos Alimenticios para el Personal Derivado de Actividades Extraordinarias',
        22301: 'Utensilios para el Servicio de Alimentación',
        26102: 'Combustibles, Lubricantes y Aditivos para Vehículos Destinados a Servicios Públicos',
        26103: 'Combustibles, Lubricantes y Aditivos para Vehículos Destinados a Servicios Administrativos',
        26104: 'Combustibles, Lubricantes y Aditivos para Vehículos Asignados a Servidores Públicos',
        26105: 'Combustibles, Lubricantes y Aditivos para Maquinaria y Equipo de Producción',
        31701: 'Servicios de Conducción de Señales Analógicas y Digitales',
        33104: 'Otras Asesorías para la Operación de Programas',
        33302: 'Servicios Estadísticos y Geográficos',
        33401: 'Servicios para Capacitación a Servidores Públicos',
        33602: 'Otros Servicios Comerciales',
        33801: 'Servicios de Vigilancia',
        33901: 'Subcontratación de Servicios con Terceros',
        35101: 'Mantenimiento y Conservación de Inmuebles para la Prestación de Servicios Administrativos',
        35201: 'Mantenimiento y Conservación de Mobiliario y Equipo de Administración',
        35801: 'Servicios de Lavandería, Limpieza e Higiene',
        35901: 'Servicios de Jardinería y Fumigación',
        37101: 'Pasajes Aéreos Nacionales para Labores en Campo y de Supervisión',
        37104: 'Pasajes Aéreos Nacionales para Servidores Públicos de Mando',
        37106: 'Pasajes Aéreos Internacionales para Servidores Públicos',
        37201: 'Pasajes Terrestres Nacionales para Labores en Campo y de Supervisión',
        37204: 'Pasajes Terrestres Nacionales para Servidores Públicos de Mando',
        37206: 'Pasajes Terrestres Internacionales para Servidores Públicos',
        37501: 'Viáticos Nacionales para Labores en Campo y de Supervisión',
        37504: 'Viáticos Nacionales para Servidores Públicos en el Desempeño de Funciones Oficiales',
        37602: 'Viáticos en el Extranjero para Servidores Públicos',
        37901: 'Cuotas para Congresos, Convenciones, Exposiciones, Seminarios y Similares',
        38301: 'Congresos y Convenciones',
        38401: 'Exposiciones',
        38501: 'Gastos de Representación',
    }

    catalogo_programas = config.get('programas_nombres', {})

    capitulos_por_ur = {}
    partidas_por_ur = {}

    for ur in urs_validas:
        df_ur = df[df['Nueva UR'] == ur]

        if df_ur.empty:
            capitulos_por_ur[ur] = {}
            partidas_por_ur[ur] = []
            continue

        # df ya tiene excluidos los COP 6x, no necesitamos filtrar de nuevo
        df_ur_filtered = df_ur

        caps_ur = {}
        for cap in [2, 3, 4]:
            df_cap = df_ur_filtered[df_ur_filtered['CAPITULO'] == cap]

            if df_cap.empty:
                caps_ur[str(cap)] = {
                    'Original': 0,
                    'Modificado_anual': 0,
                    'Modificado_periodo': 0,
                    'Ejercido': 0,
                    'Disponible_periodo': 0,
                }
                continue

            # Original: solo CO=0
            df_cap_orig = df_ur[df_ur['CAPITULO'] == cap]
            df_cap_orig = df_cap_orig[df_cap_orig['CONTROL_OPERATIVO'] == 0]
            original = round_like_excel(df_cap_orig['ORIGINAL'].sum(), 2)

            mod_anual = round_like_excel(df_cap['MODIFICADO_AUTORIZADO'].sum() - df_cap['RESERVAS'].sum(), 2)

            if es_cierre_año_anterior or mes_archivo == 12:
                mod_periodo = mod_anual
            else:
                cols_a_usar = obtener_columnas_hasta_mes(mes_archivo)
                cols_mod = [col for col in cols_a_usar['modificaciones'] if col in df_cap.columns]
                cols_res = [col for col in cols_a_usar['reservas'] if col in df_cap.columns]
                mod_bruto = df_cap[cols_mod].sum(axis=1).sum() if cols_mod else 0
                cong_periodo = df_cap[cols_res].sum(axis=1).sum() if cols_res else 0
                mod_periodo = round_like_excel(mod_bruto - cong_periodo, 2)

            ejercido = round_like_excel(df_cap['EJERCIDO_REAL'].sum(), 2)

            caps_ur[str(cap)] = {
                'Original': original,
                'Modificado_anual': mod_anual,
                'Modificado_periodo': mod_periodo,
                'Ejercido': ejercido,
                'Disponible_periodo': round_like_excel(mod_periodo - ejercido, 2),
            }

        capitulos_por_ur[ur] = caps_ur

        if not df_ur_filtered.empty:
            df_partidas = df_ur_filtered.groupby(['Partida', 'PROGRAMA_PRESUPUESTARIO']).agg({
                'ORIGINAL': 'sum',
                'MODIFICADO_AUTORIZADO': 'sum',
                'RESERVAS': 'sum',
                'EJERCIDO_REAL': 'sum',
            }).reset_index()

            df_partidas['Modificado_neto'] = df_partidas['MODIFICADO_AUTORIZADO'] - df_partidas['RESERVAS']
            df_partidas['Disponible'] = df_partidas['Modificado_neto'] - df_partidas['EJERCIDO_REAL']
            df_partidas = df_partidas[df_partidas['Disponible'] > 0].sort_values('Disponible', ascending=False).head(5)

            partidas_list = []
            for _, row in df_partidas.iterrows():
                partida = int(row['Partida'])
                programa = row['PROGRAMA_PRESUPUESTARIO']
                partidas_list.append({
                    'Partida': partida,
                    'Denominacion': catalogo_partidas.get(partida, f'Partida {partida}'),
                    'Programa': programa,
                    'Denom_Programa': catalogo_programas.get(programa, programa),
                    'Original': round_like_excel(row['ORIGINAL'], 2),
                    'Modificado': round_like_excel(row['Modificado_neto'], 2),
                    'Ejercido': round_like_excel(row['EJERCIDO_REAL'], 2),
                    'Disponible': round_like_excel(row['Disponible'], 2),
                })

            partidas_por_ur[ur] = partidas_list
        else:
            partidas_por_ur[ur] = []

    # =========================================================================
    # COP 62, 67, 68 para la nota
    # =========================================================================
    df_cop = df_para_cop_62_67[df_para_cop_62_67['Nueva UR'].astype(str).isin(urs_validas)]
    df_cop = df_cop[~df_cop['Partida'].isin([39801])]
    df_cop = df_cop[~df_cop['CAPITULO'].isin([1])]

    df_cop62 = df_cop[df_cop['CONTROL_OPERATIVO'] == 62]
    monto_cop62 = round_like_excel(df_cop62['EJERCIDO_REAL'].sum(), 2)
    urs_cop62 = df_cop62['Nueva UR'].unique().tolist()

    df_cop67 = df_cop[df_cop['CONTROL_OPERATIVO'] == 67]
    monto_cop67 = round_like_excel(df_cop67['EJERCIDO_REAL'].sum(), 2)
    urs_cop67 = df_cop67['Nueva UR'].unique().tolist()

    return {
        'resumen': resumen,
        'subtotales': {
            'sector_central': subtotal_sc,
            'oficinas': subtotal_of,
            'organos_desconcentrados': subtotal_od,
            'entidades_paraestatales': subtotal_ep,
        },
        'congelados': {
            'anual': congelado_anual,
            'periodo': congelado_periodo,
            'texto_anual': numero_a_letras_mx(congelado_anual),
            'texto_periodo': numero_a_letras_mx(congelado_periodo),
        },
        'cop_excluidos': {
            'cop_62': {'monto': monto_cop62, 'urs': urs_cop62, 'texto': numero_a_letras_mx(monto_cop62) if monto_cop62 > 0 else ''},
            'cop_67': {'monto': monto_cop67, 'urs': urs_cop67, 'texto': numero_a_letras_mx(monto_cop67) if monto_cop67 > 0 else ''},
        },
        'totales': total_general,
        'capitulos_por_ur': capitulos_por_ur,
        'partidas_por_ur': partidas_por_ur,
        'metadata': {
            'fecha_archivo': fecha_archivo,
            'mes': mes_archivo,
            'año': año_archivo,
            'registros': len(df),
            'es_cierre': es_cierre_año_anterior,
            'config': config,
        },
        'df_procesado': df,
    }
