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

        df_co0 = df_ur[df_ur['CONTROL_OPERATIVO'] == 0]
        original = round_like_excel(df_co0['ORIGINAL'].sum(), 2)

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
    11101: 'Dietas (Ramos Autónomos)',
    11201: 'Haberes',
    11301: 'Sueldos base',
    11401: 'Retribuciones por adscripción en el extranjero',
    12101: 'Honorarios',
    12201: 'Remuneraciones al personal eventual',
    12202: 'Compensaciones a sustitutos de profesores',
    12301: 'Retribuciones por servicios en período de formación profesional',
    12401: 'Retribución a los representantes de los trabajadores y de los patrones en la Junta Federal de Conciliación y Arbitraje',
    13101: 'Prima quinquenal por años de servicios efectivos prestados',
    13102: 'Acreditación por años de servicio en la docencia y al personal administrativo de las instituciones de educación superior',
    13103: 'Prima de perseverancia por años de servicio activo en el Ejército, Fuerza Aérea y Armada Mexicanos',
    13104: 'Antigüedad',
    13201: 'Primas de vacaciones y dominical',
    13202: 'Aguinaldo o gratificación de fin de año',
    13204: 'Primas de vacaciones y dominical de áreas administrativas (Ramos Autónomos)',
    13301: 'Remuneraciones por horas extraordinarias',
    13401: 'Acreditación por titulación en la docencia',
    13402: 'Acreditación al personal docente por años de estudio de licenciatura',
    13403: 'Compensaciones por servicios especiales',
    13404: 'Compensaciones por servicios eventuales',
    13405: 'Compensaciones de retiro',
    13406: 'Compensaciones de servicios',
    13407: 'Compensaciones adicionales por servicios especiales',
    13408: 'Asignaciones docentes, pedagógicas genéricas y específicas',
    13409: 'Compensación por adquisición de material didáctico',
    13410: 'Compensación por actualización y formación académica',
    13411: 'Compensaciones a médicos residentes',
    13412: 'Gastos contingentes para el personal radicado en el extranjero',
    13413: 'Asignaciones para la conclusión de servicios en la Administración Pública Federal',
    13414: 'Asignaciones conforme al régimen laboral',
    13501: 'Sobrehaberes',
    13601: 'Asignaciones de técnico',
    13602: 'Asignaciones de mando',
    13603: 'Asignaciones por comisión',
    13604: 'Asignaciones de vuelo',
    13605: 'Asignaciones de técnico especial',
    13701: 'Honorarios especiales',
    13801: 'Participaciones por vigilancia en el cumplimiento de las leyes y custodia de valores',
    14101: 'Aportaciones al ISSSTE',
    14102: 'Aportaciones al ISSFAM',
    14103: 'Aportaciones al IMSS',
    14104: 'Aportaciones de seguridad social contractuales',
    14105: 'Aportaciones al seguro de cesantía en edad avanzada y vejez',
    14201: 'Aportaciones al FOVISSSTE',
    14202: 'Aportaciones al INFONAVIT',
    14301: 'Aportaciones al Sistema de Ahorro para el Retiro',
    14302: 'Depósitos para el ahorro solidario',
    14401: 'Cuotas para el seguro de vida del personal civil',
    14402: 'Cuotas para el seguro de vida del personal militar',
    14403: 'Cuotas para el seguro de gastos médicos del personal civil',
    14404: 'Cuotas para el seguro de separación individualizado',
    14405: 'Cuotas para el seguro colectivo de retiro',
    14406: 'Seguro de responsabilidad civil, asistencia legal y otros seguros',
    15101: 'Cuotas para el fondo de ahorro del personal civil',
    15102: 'Cuotas para el fondo de ahorro de generales, almirantes, jefes y oficiales',
    15103: 'Cuotas para el fondo de trabajo del personal del Ejército, Fuerza Aérea y Armada Mexicanos',
    15201: 'Indemnizaciones por accidentes en el trabajo',
    15202: 'Pago de liquidaciones',
    15203: 'Fondo para indemnizaciones (Ramos Autónomos)',
    15301: 'Prestaciones de retiro',
    15302: 'Prestaciones y previsiones de retiro (Ramos Autónomos)',
    15401: 'Prestaciones establecidas por condiciones generales de trabajo o contratos colectivos de trabajo',
    15402: 'Compensación garantizada',
    15403: 'Asignaciones adicionales al sueldo',
    15405: 'Compensación de Apoyo (Ramos Autónomos)',
    15501: 'Apoyos a la capacitación de los servidores públicos',
    15901: 'Otras prestaciones',
    15902: 'Pago extraordinario por riesgo',
    16101: 'Incrementos a las percepciones',
    16102: 'Creación de plazas',
    16103: 'Otras medidas de carácter laboral y económico',
    16104: 'Previsiones para aportaciones al ISSSTE',
    16105: 'Previsiones para aportaciones al FOVISSSTE',
    16106: 'Previsiones para aportaciones al Sistema de Ahorro para el Retiro',
    16107: 'Previsiones para aportaciones al seguro de cesantía en edad avanzada y vejez',
    16108: 'Previsiones para los depósitos al ahorro solidario',
    16109: 'Previsiones por adecuaciones a las estructuras ocupacionales',
    17101: 'Estímulos por productividad y eficiencia',
    17102: 'Estímulos al personal operativo',
    21101: 'Materiales y útiles de oficina',
    21102: 'Material electoral (Ramos Autónomos)',
    21199: 'Materiales de administración, emisión de documentos y artículos oficiales',
    21201: 'Materiales y útiles de impresión y reproducción',
    21301: 'Material estadístico y geográfico',
    21401: 'Materiales y útiles consumibles para el procesamiento en equipos y bienes informáticos',
    21501: 'Material de apoyo informativo',
    21502: 'Material para información en actividades de investigación científica y tecnológica',
    21601: 'Material de limpieza',
    21701: 'Materiales y suministros para planteles educativos',
    21801: 'Materiales para el registro e identificación de bienes y personas',
    22101: 'Productos alimenticios para el Ejército, Fuerza Aérea y Armada Mexicanos',
    22102: 'Productos alimenticios para personas derivado de la prestación de servicios públicos',
    22103: 'Productos alimenticios para el personal que realiza labores en campo',
    22104: 'Productos alimenticios para el personal en las instalaciones',
    22105: 'Productos alimenticios para la población en caso de desastres naturales',
    22106: 'Productos alimenticios para el personal derivado de actividades extraordinarias',
    22199: 'Alimentos y utensilios',
    22201: 'Productos alimenticios para animales',
    22301: 'Utensilios para el servicio de alimentación',
    23101: 'Productos alimenticios, agropecuarios y forestales adquiridos como materia prima',
    23199: 'Materias primas y materiales de producción y comercialización',
    23201: 'Insumos textiles adquiridos como materia prima',
    23301: 'Productos de papel, cartón e impresos adquiridos como materia prima',
    23401: 'Combustibles, lubricantes, aditivos, carbón y sus derivados adquiridos como materia prima',
    23501: 'Productos químicos, farmacéuticos y de laboratorio adquiridos como materia prima',
    23601: 'Productos metálicos y a base de minerales no metálicos adquiridos como materia prima',
    23701: 'Productos de cuero, piel, plástico y hule adquiridos como materia prima',
    23801: 'Mercancías para su comercialización en tiendas del sector público',
    23901: 'Otros productos adquiridos como materia prima',
    23902: 'Petróleo, gas y sus derivados adquiridos como materia prima',
    24101: 'Productos minerales no metálicos',
    24199: 'Materiales y artículos de construcción y de reparación',
    24201: 'Cemento y productos de concreto',
    24301: 'Cal, yeso y productos de yeso',
    24401: 'Madera y productos de madera',
    24501: 'Vidrio y productos de vidrio',
    24601: 'Material eléctrico y electrónico',
    24701: 'Artículos metálicos para la construcción',
    24801: 'Materiales complementarios',
    24901: 'Otros materiales y artículos de construcción y reparación',
    25101: 'Productos químicos básicos',
    25199: 'Productos químicos, farmacéuticos y de laboratorio',
    25201: 'Plaguicidas, abonos y fertilizantes',
    25301: 'Medicinas y productos farmacéuticos',
    25401: 'Materiales, accesorios y suministros médicos',
    25501: 'Materiales, accesorios y suministros de laboratorio',
    25601: 'Fibras sintéticas, hules, plásticos y derivados',
    25901: 'Otros productos químicos',
    26101: 'Combustibles para programas de seguridad pública y nacional',
    26102: 'Combustibles para servicios públicos y operación de programas',
    26103: 'Combustibles para servicios administrativos',
    26104: 'Combustibles asignados a servidores públicos',
    26105: 'Combustibles para maquinaria y equipo de producción',
    26106: 'PIDIREGAS cargos variables',
    26107: 'Combustibles nacionales para plantas productivas',
    26108: 'Combustibles de importación para plantas productivas',
    26199: 'Combustibles, lubricantes y aditivos',
    27101: 'Vestuario y uniformes',
    27199: 'Vestuario, blancos, prendas de protección y artículos deportivos',
    27201: 'Prendas de protección personal',
    27301: 'Artículos deportivos',
    27401: 'Productos textiles',
    27501: 'Blancos y otros productos textiles, excepto prendas de vestir',
    28101: 'Sustancias y materiales explosivos',
    28199: 'Materiales y suministros para seguridad',
    28201: 'Materiales de seguridad pública',
    28301: 'Prendas de protección para seguridad pública y nacional',
    29101: 'Herramientas menores',
    29199: 'Herramientas, refacciones y accesorios menores',
    29201: 'Refacciones y accesorios menores de edificios',
    29301: 'Refacciones y accesorios menores de mobiliario y equipo',
    29401: 'Refacciones y accesorios para equipo de cómputo y telecomunicaciones',
    29501: 'Refacciones y accesorios menores de equipo e instrumental médico',
    29601: 'Refacciones y accesorios menores de equipo de transporte',
    29701: 'Refacciones y accesorios menores de equipo de defensa y seguridad',
    29801: 'Refacciones y accesorios menores de maquinaria y otros equipos',
    29901: 'Refacciones y accesorios menores otros bienes muebles',
    31101: 'Servicio de energía eléctrica',
    31199: 'Servicios básicos',
    31201: 'Servicio de gas',
    31301: 'Servicio de agua',
    31401: 'Servicio telefónico convencional',
    31501: 'Servicio de telefonía celular',
    31601: 'Servicio de radiolocalización',
    31602: 'Servicios de telecomunicaciones',
    31603: 'Servicios de Internet',
    31701: 'Servicios de conducción de señales analógicas y digitales',
    31801: 'Servicio postal',
    31802: 'Servicio telegráfico',
    31901: 'Servicios integrales de telecomunicación',
    31902: 'Contratación de otros servicios',
    31903: 'Servicios generales para planteles educativos',
    31904: 'Servicios integrales de infraestructura de cómputo',
    32101: 'Arrendamiento de terrenos',
    32199: 'Servicios de arrendamiento',
    32201: 'Arrendamiento de edificios y locales',
    32301: 'Arrendamiento de equipo y bienes informáticos',
    32302: 'Arrendamiento de mobiliario',
    32303: 'Arrendamiento de equipo de telecomunicaciones',
    32401: 'Arrendamiento de equipo e instrumental médico y de laboratorio',
    32501: 'Arrendamiento de vehículos para seguridad pública',
    32502: 'Arrendamiento de vehículos para servicios públicos',
    32503: 'Arrendamiento de vehículos para servicios administrativos',
    32504: 'Arrendamiento de vehículos para desastres naturales',
    32505: 'Arrendamiento de vehículos para servidores públicos',
    32601: 'Arrendamiento de maquinaria y equipo',
    32701: 'Patentes, derechos de autor, regalías y otros',
    32901: 'Arrendamiento de sustancias y productos químicos',
    32902: 'PIDIREGAS cargos fijos',
    32903: 'Otros arrendamientos',
    33101: 'Asesorías asociadas a convenios, tratados o acuerdos',
    33102: 'Asesorías por controversias en el marco de los tratados internacionales',
    33103: 'Consultorías para programas o proyectos financiados por organismos internacionales',
    33104: 'Otras asesorías para la operación de programas',
    33105: 'Servicios relacionados con procedimientos jurisdiccionales',
    33106: 'Servicios legales, de contabilidad, auditoría y relacionados',
    33199: 'Servicios profesionales, científicos, técnicos y otros servicios',
    33201: 'Servicios de diseño, arquitectura, ingeniería y actividades relacionadas',
    33301: 'Servicios de desarrollo de aplicaciones informáticas',
    33302: 'Servicios estadísticos y geográficos',
    33303: 'Servicios relacionados con certificación de procesos',
    33304: 'Servicios de mantenimiento de aplicaciones informáticas',
    33401: 'Servicios para capacitación a servidores públicos',
    33501: 'Estudios e investigaciones',
    33601: 'Servicios relacionados con traducciones',
    33602: 'Otros servicios comerciales',
    33603: 'Impresiones de documentos oficiales',
    33604: 'Impresión y elaboración de material informativo',
    33605: 'Información en medios masivos',
    33606: 'Servicios de digitalización',
    33701: 'Gastos de seguridad pública y nacional',
    33702: 'Gastos en actividades de seguridad y logística del Estado Mayor Presidencial',
    33801: 'Servicios de vigilancia',
    33901: 'Subcontratación de servicios con terceros',
    33902: 'Proyectos para prestación de servicios',
    33903: 'Servicios integrales',
    33904: 'Asignaciones derivadas de proyectos de asociación público privada',
    33905: 'Servicios integrales en materia de seguridad pública y nacional',
    33906: 'Asignaciones para cubrir el pago de obligaciones derivadas de títulos de concesión',
    34101: 'Servicios bancarios y financieros',
    34199: 'Servicios financieros, bancarios y comerciales',
    34301: 'Gastos inherentes a la recaudación',
    34401: 'Seguro de responsabilidad patrimonial del Estado',
    34501: 'Seguros de bienes patrimoniales',
    34601: 'Almacenaje, embalaje y envase',
    34701: 'Fletes y maniobras',
    34801: 'Comisiones por ventas',
    34901: 'Otros servicios financieros, bancarios y comerciales',
    35101: 'Mantenimiento y conservación de inmuebles para servicios administrativos',
    35102: 'Mantenimiento y conservación de inmuebles para servicios públicos',
    35199: 'Servicios de instalación, reparación, mantenimiento y conservación',
    35201: 'Mantenimiento y conservación de mobiliario y equipo de administración',
    35301: 'Mantenimiento y conservación de bienes informáticos',
    35401: 'Instalación, reparación y mantenimiento de equipo e instrumental médico',
    35501: 'Mantenimiento y conservación de vehículos',
    35601: 'Reparación y mantenimiento de equipo de defensa y seguridad',
    35701: 'Mantenimiento y conservación de maquinaria y equipo',
    35702: 'Mantenimiento y conservación de plantas e instalaciones productivas',
    35801: 'Servicios de lavandería, limpieza e higiene',
    35901: 'Servicios de jardinería y fumigación',
    36101: 'Difusión de mensajes sobre programas y actividades gubernamentales',
    36199: 'Servicios de comunicación social y publicidad',
    36201: 'Difusión de mensajes comerciales para promover la venta de productos',
    36301: 'Servicios de creatividad, preproducción y producción de publicidad',
    36401: 'Servicios de revelado de fotografías',
    36601: 'Servicio de creación y difusión de contenido a través de Internet',
    36901: 'Servicios relacionados con monitoreo de información en medios masivos',
    37101: 'Pasajes aéreos nacionales para labores en campo y de supervisión',
    37102: 'Pasajes aéreos nacionales asociados a los programas de seguridad pública',
    37103: 'Pasajes aéreos nacionales asociados a desastres naturales',
    37104: 'Pasajes aéreos nacionales para servidores públicos de mando',
    37105: 'Pasajes aéreos internacionales asociados a seguridad pública',
    37106: 'Pasajes aéreos internacionales para servidores públicos',
    37199: 'Servicios de traslado y viáticos',
    37201: 'Pasajes terrestres nacionales para labores en campo',
    37202: 'Pasajes terrestres nacionales asociados a seguridad pública',
    37203: 'Pasajes terrestres nacionales asociados a desastres naturales',
    37204: 'Pasajes terrestres nacionales para servidores públicos de mando',
    37205: 'Pasajes terrestres internacionales asociados a seguridad pública',
    37206: 'Pasajes terrestres internacionales para servidores públicos',
    37207: 'Pasajes terrestres nacionales por medio electrónico',
    37301: 'Pasajes marítimos para labores en campo y de supervisión',
    37302: 'Pasajes marítimos asociados a seguridad pública',
    37303: 'Pasajes marítimos asociados a desastres naturales',
    37304: 'Pasajes marítimos para servidores públicos de mando',
    37501: 'Viáticos nacionales para labores en campo y de supervisión',
    37502: 'Viáticos nacionales asociados a seguridad pública',
    37503: 'Viáticos nacionales asociados a desastres naturales',
    37504: 'Viáticos nacionales para servidores públicos',
    37601: 'Viáticos en el extranjero asociados a seguridad pública',
    37602: 'Viáticos en el extranjero para servidores públicos',
    37701: 'Instalación del personal federal',
    37801: 'Servicios integrales nacionales para servidores públicos',
    37802: 'Servicios integrales en el extranjero para servidores públicos',
    37901: 'Gastos para operativos y trabajos de campo en áreas rurales',
    38101: 'Gastos de ceremonial del titular del Ejecutivo Federal',
    38102: 'Gastos de ceremonial de los titulares de las dependencias',
    38103: 'Gastos inherentes a la investidura presidencial',
    38199: 'Servicios oficiales',
    38201: 'Gastos de orden social',
    38301: 'Congresos y convenciones',
    38401: 'Exposiciones',
    38501: 'Gastos para alimentación de servidores públicos de mando',
    39101: 'Funerales y pagas de defunción',
    39199: 'Otros servicios generales',
    39201: 'Impuestos y derechos de exportación',
    39202: 'Otros impuestos y derechos',
    39301: 'Impuestos y derechos de importación',
    39401: 'Erogaciones por resoluciones por autoridad competente',
    39402: 'Indemnizaciones por expropiación de predios',
    39403: 'Otras asignaciones derivadas de resoluciones de ley',
    39501: 'Penas, multas, accesorios y actualizaciones',
    39601: 'Pérdidas del erario federal',
    39602: 'Otros gastos por responsabilidades',
    39701: 'Erogaciones por pago de utilidades',
    39801: 'Impuesto sobre nóminas',
    39810: 'Otros impuestos sobre nóminas',
    39901: 'Gastos de las Comisiones Internacionales de Límites y Aguas',
    39902: 'Gastos de las oficinas del Servicio Exterior Mexicano',
    39903: 'Asignaciones a los grupos parlamentarios',
    39904: 'Participaciones en órganos de gobierno',
    39905: 'Actividades de coordinación con el Presidente Electo',
    39906: 'Servicios Corporativos prestados por las Entidades Paraestatales',
    39907: 'Servicios prestados entre Organismos de una Entidad Paraestatal',
    39908: 'Erogaciones por cuenta de terceros',
    39909: 'Erogaciones recuperables',
    39910: 'Apertura de Fondo Rotatorio',
    41501: 'Transferencias para cubrir el déficit de operación',
    41601: 'Transferencias a entidades empresariales no financieras',
    43101: 'Subsidios a la producción',
    43201: 'Subsidios a la distribución',
    43301: 'Subsidios para inversión',
    43401: 'Subsidios a la prestación de servicios públicos',
    43501: 'Subsidios para cubrir diferenciales de tasas de interés',
    43601: 'Subsidios para la adquisición de vivienda de interés social',
    43701: 'Subsidios al consumo',
    43801: 'Subsidios a Entidades Federativas y Municipios',
    43901: 'Subsidios para capacitación y becas',
    43902: 'Subsidios a fideicomisos privados y estatales',
    44101: 'Gastos relacionados con actividades culturales, deportivas y de ayuda extraordinaria',
    44102: 'Gastos por servicios de traslado de personas',
    44103: 'Premios, recompensas, pensiones de gracia y pensión recreativa estudiantil',
    44104: 'Premios, estímulos, recompensas, becas y seguros a deportistas',
    44105: 'Apoyo a voluntarios que participan en diversos programas federales',
    44106: 'Compensaciones por servicios de carácter social',
    44199: 'Ayudas sociales',
    44201: 'Otras ayudas para programas de capacitación',
    44401: 'Apoyos a la investigación científica y tecnológica',
    44402: 'Apoyos a la investigación científica en instituciones sin fines de lucro',
    44801: 'Mercancías para su distribución a la población',
    45201: 'Pago de pensiones y jubilaciones',
    45202: 'Pago de pensiones y jubilaciones contractuales',
    45203: 'Transferencias para el pago de pensiones y jubilaciones',
    45901: 'Pago de sumas aseguradas',
    45902: 'Prestaciones económicas distintas de pensiones y jubilaciones',
    46101: 'Aportaciones a fideicomisos públicos',
    46102: 'Aportaciones a mandatos públicos',
    46199: 'Transferencias a fideicomisos, mandatos y otros análogos',
    47101: 'Trasferencias para cuotas y aportaciones de seguridad social',
    47102: 'Transferencias para cuotas y aportaciones a los seguros de retiro',
    48101: 'Donativos a instituciones sin fines de lucro',
    48199: 'Donativos',
    48201: 'Donativos a entidades federativas o municipios',
    48301: 'Donativos a fideicomisos privados',
    48401: 'Donativos a fideicomisos estatales',
    48501: 'Donativos internacionales',
    49199: 'Transferencias al exterior',
    49201: 'Cuotas y aportaciones a organismos internacionales',
    49202: 'Otras aportaciones internacionales',
    51101: 'Mobiliario',
    51199: 'Mobiliario y equipo de administración',
    51201: 'Muebles, excepto de oficina y estantería',
    51301: 'Bienes artísticos y culturales',
    51501: 'Bienes informáticos',
    51901: 'Equipo de administración',
    51902: 'Adjudicaciones, expropiaciones e indemnizaciones de bienes muebles',
    52101: 'Equipos y aparatos audiovisuales',
    52199: 'Mobiliario y equipo educacional y recreativo',
    52201: 'Aparatos deportivos',
    52301: 'Cámaras fotográficas y de video',
    52901: 'Otro mobiliario y equipo educacional y recreativo',
    53101: 'Equipo médico y de laboratorio',
    53199: 'Equipo e instrumental médico y de laboratorio',
    53201: 'Instrumental médico y de laboratorio',
    54101: 'Vehículos y equipo terrestres para seguridad pública',
    54102: 'Vehículos y equipo terrestres para desastres naturales',
    54103: 'Vehículos y equipo terrestres para servicios públicos',
    54104: 'Vehículos y equipo terrestres para servicios administrativos',
    54105: 'Vehículos y equipo terrestres para servidores públicos',
    54199: 'Vehículos y equipo de transporte',
    54201: 'Carrocerías y remolques',
    54301: 'Vehículos y equipo aéreos para seguridad pública',
    54302: 'Vehículos y equipo aéreos para desastres naturales',
    54303: 'Vehículos y equipo aéreos para servicios públicos',
    54401: 'Equipo ferroviario',
    54501: 'Vehículos y equipo marítimo para seguridad pública',
    54502: 'Vehículos y equipo marítimo para servicios públicos',
    54503: 'Construcción de embarcaciones',
    54901: 'Otros equipos de transporte',
    55101: 'Maquinaria y equipo de defensa y seguridad pública',
    55102: 'Equipo de seguridad pública y nacional',
    55199: 'Equipo de defensa y seguridad',
    56101: 'Maquinaria y equipo agropecuario',
    56199: 'Maquinaria, otros equipos y herramientas',
    56201: 'Maquinaria y equipo industrial',
    56301: 'Maquinaria y equipo de construcción',
    56401: 'Sistemas de aire acondicionado, calefacción y de refrigeración',
    56501: 'Equipos y aparatos de comunicaciones y telecomunicaciones',
    56601: 'Maquinaria y equipo eléctrico y electrónico',
    56701: 'Herramientas y máquinas herramienta',
    56901: 'Bienes muebles por arrendamiento financiero',
    56902: 'Otros bienes muebles',
    57101: 'Animales de reproducción',
    57199: 'Activos biológicos',
    57201: 'Porcinos',
    57301: 'Aves',
    57401: 'Ovinos y caprinos',
    57501: 'Peces y acuicultura',
    57601: 'Animales de trabajo',
    57701: 'Animales de custodia y vigilancia',
    57801: 'Árboles y plantas',
    57901: 'Otros activos biológicos',
    58101: 'Terrenos',
    58199: 'Bienes inmuebles',
    58301: 'Edificios y locales',
    58901: 'Adjudicaciones, expropiaciones e indemnizaciones de inmuebles',
    58902: 'Bienes inmuebles en la modalidad de proyectos de infraestructura',
    58903: 'Bienes inmuebles por arrendamiento financiero',
    58904: 'Otros bienes inmuebles',
    59101: 'Software',
    59199: 'Activos intangibles',
    59401: 'Derechos',
    59701: 'Licencias informáticas e intelectuales',
    59901: 'Otros activos intangibles',
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
            # Calcular modificado al PERIODO para partidas
            # usando las columnas mensuales MO{abrev} y RESERVA_{mes}
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

            # Si es cierre de año anterior o diciembre, periodo = anual
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
                partidas_list.append({
                    'Partida': partida,
                    'Denominacion': catalogo_partidas.get(partida, f'Partida {partida}'),
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
