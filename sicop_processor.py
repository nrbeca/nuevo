# ============================================================================
# PROCESADOR DE ARCHIVOS SICOP
# ============================================================================

import pandas as pd
import numpy as np
from datetime import date
from config import (
    MONTH_NAMES, round_like_excel, detectar_fecha_archivo,
    get_config_by_year, numero_a_letras_mx, PARTIDAS_ESPECIFICAS
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
        'comprometido': [f'CO{abrev}' for abrev, _ in meses_usar],
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

    df['Partida'] = df.apply(
       lambda r: int(
           str(int(r['CAPITULO'])) + str(int(r['CONCEPTO'])) +
           str(int(r['PARTIDA_GENERICA'])) + f"{int(r['PARTIDA_ESPECIFICA']):02d}"
       ), axis=1
    )

    for col in ['EJERCIDO', 'DEVENGADO', 'EJERCIDO_TRAMITE', 'COMPROMETIDO']:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    cols_comprometido_mes = [f'CO{abrev}' for abrev, _ in
        [('EN', ''), ('FE', ''), ('MR', ''), ('AB', ''), ('MY', ''), ('JN', ''),
         ('JL', ''), ('AG', ''), ('SE', ''), ('OC', ''), ('NO', ''), ('DI', '')]]
    for col in cols_comprometido_mes:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['EJERCIDO_REAL'] = df['EJERCIDO'] + df['DEVENGADO'] + df['EJERCIDO_TRAMITE']

    urs_validas = (config['sector_central'] + config['oficinas'] +
                   config['organos_desconcentrados'] + config['entidades_paraestatales'])

    df_para_congelados = df.copy()
    df_para_cop_62_67 = df.copy()

    urs_validas_str = [str(ur) for ur in urs_validas]
    df = df[df['Nueva UR'].isin(urs_validas_str)].copy()
    df = df[~df['Partida'].isin([39801])].copy()
    df = df[~df['CAPITULO'].isin([1])].copy()
    df = df[~df['CONTROL_OPERATIVO'].between(60, 69)].copy()

    resultados_ur = {}

    for ur in urs_validas:
        df_ur = df[df['Nueva UR'].astype(str) == ur].copy()

        if len(df_ur) == 0:
            resultados_ur[ur] = {
                'Original': 0, 'Modificado_anual': 0, 'Modificado_periodo': 0,
                'Comprometido_anual': 0, 'Comprometido_periodo': 0,
                'Ejercido': 0, 'Devengado': 0, 'Ejercido_tramite': 0,
            }
            continue

        df_ur['Modificado_neto'] = df_ur['MODIFICADO_AUTORIZADO'] - df_ur['RESERVAS']

        df_co0 = df_ur[df_ur['CONTROL_OPERATIVO'] == 0]
        original = round_like_excel(df_co0['ORIGINAL'].sum(), 2)

        df_modificado = df_ur
        modificado_anual = round_like_excel(df_modificado['Modificado_neto'].sum(), 2)

        comprometido_anual = round_like_excel(df_ur['COMPROMETIDO'].sum(), 2) if 'COMPROMETIDO' in df_ur.columns else 0

        if es_cierre_año_anterior or mes_archivo == 12:
            modificado_periodo = modificado_anual
            comprometido_periodo = comprometido_anual
        else:
            cols_a_usar = obtener_columnas_hasta_mes(mes_archivo)
            cols_mod = [col for col in cols_a_usar['modificaciones'] if col in df_modificado.columns]
            cols_res = [col for col in cols_a_usar['reservas'] if col in df_modificado.columns]
            mod_bruto = df_modificado[cols_mod].sum(axis=1).sum() if cols_mod else 0
            cong_periodo = df_modificado[cols_res].sum(axis=1).sum() if cols_res else 0
            modificado_periodo = round_like_excel(mod_bruto - cong_periodo, 2)

            cols_com = [col for col in cols_a_usar['comprometido'] if col in df_ur.columns]
            comprometido_periodo = round_like_excel(df_ur[cols_com].sum(axis=1).sum(), 2) if cols_com else 0

        ejercido = round_like_excel(df_ur['EJERCIDO_REAL'].sum(), 2)
        ejercido_solo = round_like_excel(df_ur['EJERCIDO'].sum(), 2)
        devengado = round_like_excel(df_ur['DEVENGADO'].sum(), 2)
        ejercido_tramite = round_like_excel(df_ur['EJERCIDO_TRAMITE'].sum(), 2)

        resultados_ur[ur] = {
            'Original': original,
            'Modificado_anual': modificado_anual,
            'Modificado_periodo': modificado_periodo,
            'Comprometido_anual': comprometido_anual,
            'Comprometido_periodo': comprometido_periodo,
            'Ejercido_acumulado': ejercido,
            'Ejercido': ejercido_solo,
            'Devengado': devengado,
            'Ejercido_tramite': ejercido_tramite,
        }

    resumen = pd.DataFrame.from_dict(resultados_ur, orient='index').reset_index()
    resumen = resumen.rename(columns={'index': 'UR'})

    # Total anual/periodo (columnas auxiliares, no se muestran): (c+f+g+h) y (e+f+g+h)
    resumen['Total_anual'] = (
        resumen['Comprometido_anual'] + resumen['Ejercido'] + resumen['Devengado'] + resumen['Ejercido_tramite']
    )
    resumen['Total_periodo'] = (
        resumen['Comprometido_periodo'] + resumen['Ejercido'] + resumen['Devengado'] + resumen['Ejercido_tramite']
    )

    resumen['Disponible_anual'] = resumen.apply(
        lambda row: round_like_excel(row['Modificado_anual'] - row['Total_anual'], 2), axis=1
    )
    resumen['Disponible_periodo'] = resumen.apply(
        lambda row: round_like_excel(row['Modificado_periodo'] - row['Total_periodo'], 2), axis=1
    )
    resumen['Pct_avance_anual'] = resumen.apply(
        lambda row: row['Total_anual'] / row['Modificado_anual'] if row['Modificado_anual'] != 0 else 0, axis=1
    )
    resumen['Pct_avance_periodo'] = resumen.apply(
        lambda row: row['Total_periodo'] / row['Modificado_periodo'] if row['Modificado_periodo'] != 0 else 0, axis=1
    )

    def calcular_subtotal(urs_lista):
        df_seccion = resumen[resumen['UR'].isin(urs_lista)]
        subtotal = {
            'Original': df_seccion['Original'].sum(),
            'Modificado_anual': df_seccion['Modificado_anual'].sum(),
            'Modificado_periodo': df_seccion['Modificado_periodo'].sum(),
            'Comprometido_anual': df_seccion['Comprometido_anual'].sum(),
            'Comprometido_periodo': df_seccion['Comprometido_periodo'].sum(),
            'Ejercido_acumulado': df_seccion['Ejercido_acumulado'].sum(),
            'Ejercido': df_seccion['Ejercido'].sum(),
            'Devengado': df_seccion['Devengado'].sum(),
            'Ejercido_tramite': df_seccion['Ejercido_tramite'].sum(),
            'Total_anual': df_seccion['Total_anual'].sum(),
            'Total_periodo': df_seccion['Total_periodo'].sum(),
            'Disponible_anual': df_seccion['Disponible_anual'].sum(),
            'Disponible_periodo': df_seccion['Disponible_periodo'].sum(),
        }
        subtotal['Pct_avance_anual'] = subtotal['Total_anual'] / subtotal['Modificado_anual'] if subtotal['Modificado_anual'] != 0 else 0
        subtotal['Pct_avance_periodo'] = subtotal['Total_periodo'] / subtotal['Modificado_periodo'] if subtotal['Modificado_periodo'] != 0 else 0
        return subtotal

    subtotal_sc = calcular_subtotal(config['sector_central'])
    subtotal_of = calcular_subtotal(config['oficinas'])
    subtotal_od = calcular_subtotal(config['organos_desconcentrados'])
    subtotal_ep = calcular_subtotal(config['entidades_paraestatales'])

    def _sumar_llave(llave):
        return subtotal_sc[llave] + subtotal_of[llave] + subtotal_od[llave] + subtotal_ep[llave]

    total_general = {
        'Original': _sumar_llave('Original'),
        'Modificado_anual': _sumar_llave('Modificado_anual'),
        'Modificado_periodo': _sumar_llave('Modificado_periodo'),
        'Comprometido_anual': _sumar_llave('Comprometido_anual'),
        'Comprometido_periodo': _sumar_llave('Comprometido_periodo'),
        'Ejercido_acumulado': _sumar_llave('Ejercido_acumulado'),
        'Ejercido': _sumar_llave('Ejercido'),
        'Devengado': _sumar_llave('Devengado'),
        'Ejercido_tramite': _sumar_llave('Ejercido_tramite'),
        'Total_anual': _sumar_llave('Total_anual'),
        'Total_periodo': _sumar_llave('Total_periodo'),
        'Disponible_anual': _sumar_llave('Disponible_anual'),
        'Disponible_periodo': _sumar_llave('Disponible_periodo'),
    }
    total_general['Pct_avance_anual'] = total_general['Total_anual'] / total_general['Modificado_anual'] if total_general['Modificado_anual'] != 0 else 0
    total_general['Pct_avance_periodo'] = total_general['Total_periodo'] / total_general['Modificado_periodo'] if total_general['Modificado_periodo'] != 0 else 0

    # Congelados
    df_para_congelados = df_para_congelados[df_para_congelados['Nueva UR'].astype(str).isin(urs_validas)]
    df_para_congelados = df_para_congelados[~df_para_congelados['Partida'].isin([39801])]
    df_para_congelados = df_para_congelados[~df_para_congelados['CAPITULO'].isin([1])]

    congelado_anual = calcular_congelado_anual(df_para_congelados)
    congelado_periodo = calcular_congelado_periodo(df_para_congelados, mes_archivo)

    # =========================================================================
    # CALCULOS POR UR PARA DASHBOARD PRESUPUESTO
    # Usa PARTIDAS_ESPECIFICAS de config.py (catálogo completo con cientos
    # de partidas) en lugar del catálogo local reducido anterior.
    # =========================================================================

    catalogo_programas = config.get('programas_nombres', {})

    capitulos_por_ur = {}
    partidas_por_ur = {}

    for ur in urs_validas:
        df_ur = df[df['Nueva UR'] == ur]

        if df_ur.empty:
            capitulos_por_ur[ur] = {}
            partidas_por_ur[ur] = []
            continue

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
            cols_periodo = obtener_columnas_hasta_mes(mes_archivo)
            cols_mod_p = [c for c in cols_periodo['modificaciones'] if c in df_ur_filtered.columns]
            cols_res_p = [c for c in cols_periodo['reservas']        if c in df_ur_filtered.columns]

            df_urt = df_ur_filtered.copy()
            if cols_mod_p:
                df_urt['_mod_periodo'] = df_urt[cols_mod_p].sum(axis=1)
            else:
                df_urt['_mod_periodo'] = df_urt['MODIFICADO_AUTORIZADO'] - df_urt['RESERVAS']
            if cols_res_p:
                df_urt['_res_periodo'] = df_urt[cols_res_p].sum(axis=1)
            else:
                df_urt['_res_periodo'] = df_urt['RESERVAS']

            if es_cierre_año_anterior or mes_archivo == 12:
                df_urt['_mod_neto_periodo'] = df_urt['MODIFICADO_AUTORIZADO'] - df_urt['RESERVAS']
            else:
                df_urt['_mod_neto_periodo'] = df_urt['_mod_periodo'] - df_urt['_res_periodo']

            df_partidas = df_urt.groupby(['Partida', 'PROGRAMA_PRESUPUESTARIO']).agg(
                ORIGINAL=('ORIGINAL', 'sum'),
                MODIFICADO_AUTORIZADO=('MODIFICADO_AUTORIZADO', 'sum'),
                RESERVAS=('RESERVAS', 'sum'),
                EJERCIDO_REAL=('EJERCIDO_REAL', 'sum'),
                Modificado_periodo=('_mod_neto_periodo', 'sum'),
            ).reset_index()

            df_partidas['Modificado_anual'] = df_partidas['MODIFICADO_AUTORIZADO'] - df_partidas['RESERVAS']
            df_partidas['Disponible_periodo'] = df_partidas['Modificado_periodo'] - df_partidas['EJERCIDO_REAL']
            df_partidas = df_partidas[df_partidas['Disponible_periodo'] > 0].sort_values('Disponible_periodo', ascending=False).head(5)

            partidas_list = []
            for _, row in df_partidas.iterrows():
                partida = int(row['Partida'])
                programa = row['PROGRAMA_PRESUPUESTARIO']
                # ── CORRECCIÓN: usar PARTIDAS_ESPECIFICAS (catálogo completo) ──
                denominacion = PARTIDAS_ESPECIFICAS.get(partida, f'Partida {partida}')
                partidas_list.append({
                    'Partida': partida,
                    'Denominacion': denominacion,
                    'Programa': programa,
                    'Denom_Programa': catalogo_programas.get(programa, programa),
                    'Original': round_like_excel(row['ORIGINAL'], 2),
                    'Modificado': round_like_excel(row['Modificado_periodo'], 2),
                    'Ejercido': round_like_excel(row['EJERCIDO_REAL'], 2),
                    'Disponible': round_like_excel(row['Disponible_periodo'], 2),
                })

            partidas_por_ur[ur] = partidas_list
        else:
            partidas_por_ur[ur] = []

    # =========================================================================
    # COP 62 y 67 — usa MODIFICADO_AUTORIZADO (igual que la nota en app.py)
    # =========================================================================
    df_cop = df_para_cop_62_67[df_para_cop_62_67['Nueva UR'].astype(str).isin(urs_validas)]
    df_cop = df_cop[~df_cop['Partida'].isin([39801])]
    df_cop = df_cop[~df_cop['CAPITULO'].isin([1])]

    if 'MODIFICADO_AUTORIZADO' in df_cop.columns:
        df_cop['MODIFICADO_AUTORIZADO'] = pd.to_numeric(df_cop['MODIFICADO_AUTORIZADO'], errors='coerce').fillna(0)

        df_cop62 = df_cop[df_cop['CONTROL_OPERATIVO'] == 62]
        monto_cop62 = round_like_excel(df_cop62['MODIFICADO_AUTORIZADO'].sum(), 2)
        urs_cop62 = sorted(df_cop62['Nueva UR'].unique().tolist()) if not df_cop62.empty else []

        df_cop67 = df_cop[df_cop['CONTROL_OPERATIVO'] == 67]
        monto_cop67 = round_like_excel(df_cop67['MODIFICADO_AUTORIZADO'].sum(), 2)
        urs_cop67 = sorted(df_cop67['Nueva UR'].unique().tolist()) if not df_cop67.empty else []
    else:
        monto_cop62, urs_cop62 = 0, []
        monto_cop67, urs_cop67 = 0, []

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
