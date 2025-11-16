import requests
import pandas as pd

import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import calendar
import streamlit as st

color_real = "#4BA3F7"
color_interpol = "#F63366"

def generar_menu():
    with st.sidebar:
        st.title('INTERPOWER :orange[e]PowerAPP©')
        st.image('images/banner.png')
        st.caption("Copyright by Jose Vidal :ok_hand:")
        #url_apps = "https://powerappspy-josevidal.streamlit.app/"
        #st.write("Visita mi página de [ePowerAPPs](%s) con un montón de utilidades." % url_apps)
        url_linkedin = "https://www.linkedin.com/posts/josefvidalsierra_epowerapp-interpolados-activity-7382295139412647936-sCHp?utm_source=share&utm_medium=member_desktop&rcm=ACoAAFYBwa4BRZN7ghU77azb6YGy123gZvYnqoE"
        #url_bluesky = "https://bsky.app/profile/poweravenger.bsky.social"
        #st.markdown(f"Deja tus comentarios y propuestas en mi perfil de [Linkedin]({url_linkedin}) - ¡Sígueme en [Bluesky]({url_bluesky})!")
        st.markdown(f"Deja tus comentarios y propuestas en mi perfil de [Linkedin]({url_linkedin})")
        st.subheader("", divider='rainbow')

# Obtenemos curva CUARTO HORARIA para cálculos reales y HORARIA para simulación por interpolación+++++++++++++++++++++++++++++++++++++++++++++++++++++
@st.cache_data(ttl=86400)
def obtener_datos_contador(usuario, password, cups, fecha_inicio, fecha_fin, tipo_curva):

    # URL de autenticación
    url_auth = f'https://api.twinmeter.es/auth?usuario={usuario}&pass={password}'
    # Realizar la solicitud de autenticación
    response_auth = requests.get(url_auth)

    # Autenticación de usuario y password
    if response_auth.status_code == 200:

        # Extraer el token de la respuesta
        token = response_auth.json().get('data', {}).get('token', '')
        if token:
            print('Autenticación exitosa. Token obtenido.')

            # URL del CUPS
            url_cups = f'https://api.twinmeter.es/suministros/?cups={cups}'
            headers = {'token': token}
            response_cups = requests.get(url_cups, headers=headers)

            # Si el CUPS es correcto, obtenemos el id interno del mismo
            if response_cups.status_code == 200:
                cups_data = response_cups.json()
                if 'data' in cups_data and cups_data['data']:
                    cups_id = cups_data['data'].get('cups_id', '')  # Suponiendo que el primer resultado es el correcto
                
                    if cups_id:
                        
                        # Obtener datos cuartohorarios con el cups_id
                        url_datos = (
                            f'https://api.twinmeter.es/medidas?cups_id={cups_id}'
                            f'&fecha_ini={fecha_inicio}&fecha_fin={fecha_fin}'
                            f'&tipo_curva={tipo_curva}'
                        )

                        response_datos = requests.get(url_datos, headers=headers)
                        # pasamos a dataframe
                        if response_datos.status_code == 200:
                            datos = response_datos.json().get('data', [])
                            print('Datos obtenidos correctamente')
                            df_cch_real = pd.DataFrame(datos)
                            df_cch_real = df_cch_real.rename(columns = {'fecha':'datetime'})
                            df_cch_real['datetime'] = pd.to_datetime(df_cch_real['datetime'], format='%d/%m/%Y %H:%M')
                            df_cch_real["datetime"] = df_cch_real["datetime"] - pd.Timedelta(minutes=15)
                            df_cch_real = df_cch_real[["datetime", "hora", "energia"]].copy()
                            df_cch_real = df_cch_real.rename(columns={'energia':'consumo_real'})

                            df_cch_real = df_cch_real.drop_duplicates(subset='datetime', keep='first').sort_values('datetime')
                            df_cch_real.loc[df_cch_real['hora'] == 25, 'hora'] = 3

                            # Resamplear a frecuencia horaria
                            df_ch = df_cch_real.resample("H", on="datetime").agg({
                                "consumo_real": "sum",      # sumar la energía de los 4 cuartos de hora
                                #"ie1q": "sum",
                                #"ce2q": "sum",
                                #"ie3q": "sum",
                                #"ce4q": "sum",
                                #"exportada": "sum",
                                "hora": "first",       # tomar la primera hora (o puedes recalcularla)
                                #"bandera": "first",    # bandera suele repetirse → cogemos la primera
                                #"eventos": "sum"       # sumar eventos si corresponde
                            }).reset_index()
                        else:
                            print('Error al obtener los datos:', response_datos.status_code, response_datos.text)
                    else:
                        print('No se pudo extraer el CUPS ID.')
                else:
                    print('No se encontraron datos para el CUPS proporcionado.')
            else:
                print('Error al obtener CUPS ID:', response_cups.status_code, response_cups.text)
        else:
            print('No se pudo obtener el token de autenticación.')
    else:
        print('Error en la autenticación:', response_auth.status_code, response_auth.text)

    return df_cch_real, df_ch



# OBTENEMOS CURVA CUARTOHORARIA INTERPOLADA SEGÚN BOE+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def interpolar_cuartohoraria_boe(df_ch):
    """
    Implementación literal del método BOE (Anexo 11).
    Incluye interpolación lineal, normalización, redondeo secuencial
    y todos los casos especiales descritos oficialmente.
    """
    
    df_ch = df_ch.sort_values("datetime").reset_index(drop=True)
    df_ch["consumo_real"] = df_ch["consumo_real"].astype(float)

    x_h = 0.5
    x_prev = -0.5
    x_next = 1.5
    x_q = [0.125, 0.375, 0.625, 0.875]
    registros = []

    for i in range(len(df_ch)):
        E_h = df_ch.loc[i, "consumo_real"]
        dt_h = df_ch.loc[i, "datetime"]

        E_prev = df_ch.loc[i-1, "consumo_real"] if i > 0 else E_h
        E_next = df_ch.loc[i+1, "consumo_real"] if i < len(df_ch)-1 else E_h

        # --- Paso 1: Interpolación lineal ---
        E_qp = []
        for q, x in enumerate(x_q, start=1):
            if q <= 2:
                E_interp = 0.25 * (E_prev + (x - x_prev) * (E_h - E_prev) / (x_h - x_prev))
            else:
                E_interp = 0.25 * (E_h + (x - x_h) * (E_next - E_h) / (x_next - x_h))
            E_qp.append(E_interp)

        # --- Paso 2: Normalización proporcional ---
        sum_Ep = sum(E_qp)
        if sum_Ep == 0:
            E_q = [E_h / 4] * 4
        else:
            E_q = [Ei + Ei / sum_Ep * (E_h - sum_Ep) for Ei in E_qp]

        # --- Paso 3: Redondeo secuencial ---
        E_qr = []
        for q in range(3):
            E_qr.append(np.floor(E_q[q] + 0.5))
        E_qr.append(E_h - sum(E_qr))

        # --- Paso 4: Casos especiales ---
        # Si el último cuarto negativo
        if E_qr[3] < 0:
            E_qr[2] += E_qr[3]
            E_qr[3] = 0
        # Si el último cuarto > E_h
        if E_qr[3] > E_h:
            exceso = E_qr[3] - E_h
            E_qr[2] += exceso
            E_qr[3] = E_h
        # Si el tercero quedó negativo (muy raro)
        if E_qr[2] < 0:
            E_qr[1] += E_qr[2]
            E_qr[2] = 0

        # --- Paso 5: Guardar resultados ---
        for q, mins in enumerate([0, 15, 30, 45]):
            registros.append({
                "datetime": dt_h + pd.Timedelta(minutes=mins),
                "consumo_interpolado": int(E_qr[q]),
                #"energia_float": float(E_q[q])
            })
    
    df_cch_real_interpol = pd.DataFrame(registros)

    #df_cch_real_interpol = df_cch_real_interpol.rename(columns={'energia':'consumo_interpolado'})
    df_cch_real_interpol = df_cch_real_interpol.sort_values("datetime").reset_index(drop=True)

    return df_cch_real_interpol





# DESCARGAMOS SPOT QH++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
@st.cache_data(ttl=86400)
def download_esios_id(id, fecha_ini, fecha_fin, agrupacion, agregacion):
        
        #token = st.secrets['ESIOS_API_KEY']
        token = "496b263791ef0dcaf80b803b47b332a13b01f2c2352e018b624c7a36a0eaffc0"
        cab = dict()
        cab ['x-api-key']= token
        url_id = 'https://api.esios.ree.es/indicators'
        url=f'{url_id}/{id}?geo_ids[]=3&start_date={fecha_ini}T00:00:00&end_date={fecha_fin}T23:59:59&time_trunc={agrupacion}&time_agg={agregacion}'
        print(url)
        datos_origen = requests.get(url, headers=cab).json()
        
        datos=pd.DataFrame(datos_origen['indicator']['values'])
        datos = (datos
            .assign(datetime=lambda vh_: pd #formateamos campo fecha, desde un str con diferencia horaria a un naive
                .to_datetime(vh_['datetime'],utc=True)  # con la fecha local
                .dt
                .tz_convert('Europe/Madrid')
                .dt
                .tz_localize(None)
                ) 
            )
        #dataframe con los valores horarios de las tecnologias
        #lo mezclamos con el spot horario
        df_spot=datos.copy()
        df_spot=df_spot.loc[:,['datetime','value']]
        #df_spot['fecha']=df_spot['datetime'].dt.date
        #df_spot['hora']=df_spot['datetime'].dt.hour
        #df_spot = df_spot.drop(columns='datetime')
        
        #df_spot.set_index('datetime', inplace=True)
        df_spot.reset_index()
        #df_spot['hora']+=1
        #df_spot['fecha'] = pd.to_datetime(df_spot['fecha']).dt.date
        df_spot['value'] = round(pd.to_numeric(df_spot['value'], errors='coerce'),2)
        df_spot = df_spot.rename(columns={'value':'spot'})
         
        return df_spot 




def combinar_consumos_spot(df_comp, df_spot):
    df_comp = pd.merge(
        #df_comp[["datetime", "hora", ""]],
        df_comp,
        df_spot[["datetime", "spot"]],
        on="datetime",
        how="left"   # o "left" según lo que necesites
    )

    # opcional: crear la columna coste
    df_comp["coste_real"] = df_comp["consumo_real"] * df_comp["spot"]/1000
    df_comp["coste_interpolado"] = df_comp["consumo_interpolado"] * df_comp["spot"]/1000
    df_comp['dif_consumo'] = df_comp['consumo_interpolado'] - df_comp['consumo_real']

    return df_comp


def comparativa_mensual(df_comp):
    df_comp_diario = (
        df_comp
        .set_index('datetime')
        .resample('D')[['coste_real', 'coste_interpolado']]
        .sum()
        .reset_index()
    )
    df_comp_diario['dif_dia'] = df_comp_diario['coste_interpolado'] - df_comp_diario['coste_real']
    # Añadir columna 'dia_num' como texto desde el principio
    df_comp_diario['dia_num'] = [str(i) for i in range(1, len(df_comp_diario) + 1)]

    # --- Obtener mes y año a partir de la primera fecha válida ---
    fecha_inicio = pd.to_datetime(df_comp_diario.loc[df_comp_diario['datetime'] != 'TOTAL', 'datetime']).iloc[0]
    año = fecha_inicio.year
    mes = fecha_inicio.month
    mes_nombre = fecha_inicio.strftime('%B').capitalize()
    # --- Crear rango completo de días del mes ---
    dias_mes = [str(i) for i in range(1, calendar.monthrange(año, mes)[1] + 1)]  # ['1','2',...,'31']

    # --- Asegurar que dia_num es texto ---
    df_comp_diario['dia_num'] = df_comp_diario['dia_num'].astype(str)

    # --- Mantener solo columnas necesarias ---
    df_comp_diario = df_comp_diario[['dia_num', 'dif_dia']]

    # --- Fusionar con todos los días del mes (rellenando faltantes con NaN) ---
    df_comp_diario = pd.merge(pd.DataFrame({'dia_num': dias_mes}),
                            df_comp_diario,
                            on='dia_num', how='left')

    # --- Añadir fila TOTAL ---
    total = df_comp_diario['dif_dia'].sum(skipna=True)
    df_comp_diario.loc[len(df_comp_diario)] = {'dia_num': 'TOTAL', 'dif_dia': total}

    print('DF EVOLUCION DIARIA DE LAS DIFERENCIAS POR INTERPOLACIÓN')
    print(df_comp_diario)

    return df_comp_diario, mes_nombre



# GRAFICOS--------------------------------------------------------------------------------------------------------------------------------
# GRÁFICA QH COMPARATIVA DE CONSUMOS REAL E INTERPOLADO+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def graficar_consumos(df_comp):

    #color_streamlit = st.get_option("theme.primaryColor")
    

    graf_comp_consumos = go.Figure()

    # 🔹 Barras azules suaves → consumo horario
    #fig.add_trace(go.Bar(
    #    x=df_ch['datetime'],
    #    y=df_ch['energia'],
    #    name='Consumo horario (suma 4 cuartos)',
    #    marker_color='rgba(70, 130, 180, 0.3)',  # azul claro translúcido
    #))

    # 🔴 Línea → consumo interpolado cuartohorario
    graf_comp_consumos.add_trace(go.Scatter(
        x=df_comp['datetime'],
        y=df_comp['consumo_interpolado'],
        mode='lines',
        name='Consumo interpolado',
        line=dict(color=color_interpol, width=2, dash='dot')
    ))
    # 🔵 Línea → consumo real cuartohorario
    graf_comp_consumos.add_trace(go.Scatter(
        x=df_comp['datetime'],
        y=df_comp['consumo_real'],
        mode='lines',
        name='Consumo real',
        line=dict(color=color_real, width=1)
        #line=dict(width=1)
    ))
   

    # --- Layout ---
    graf_comp_consumos.update_layout(
        title="Curvas cuartohorarias (real e interpolada)",
        xaxis=dict(
            title="Fecha y hora",
            showgrid=True,
            rangeslider=dict(
                visible=True,
                bgcolor='rgba(173, 216, 230, 0.5)'  # azul semitransparente
            ),
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1 día", step="day", stepmode="backward"),
                    dict(count=7, label="1 semana", step="day", stepmode="backward"),
                    dict(step="all", label="Todo")
                ]
            )
        ),
        yaxis_title="Consumo (kWh)",
        #width=1400,
        #height=500,
        #barmode='overlay',  # 🔹 superponer barras con líneas
        #plot_bgcolor='rgba(245,245,245,1)',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )

      
    return graf_comp_consumos

# GRAFICO DEL SPOT QH+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def graficar_spot(df_spot):
    fig_spot = px.bar(df_spot, x='datetime', y='spot',
        title = 'Precio del SPOT (€)',
        #color_discrete_sequence=['green'])
        color = 'spot',
        color_continuous_scale='Greens'
    )

    fig_spot.update_layout(
        xaxis=dict(
            title='Fecha-Hora (cada 15 minutos)',
            showgrid=True,
            dtick=24 * 60 * 60 * 1000,
            rangeslider=dict(
                visible=True,
                bgcolor='rgba(173, 216, 230, 0.5)',  # azul semitransparente
            ),
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1 día", step="day", stepmode="backward"),
                    dict(count=7, label="1 semana", step="day", stepmode="backward"),
                    dict(step="all", label="Todo")
                ]
            )
        ),
        yaxis=dict(
            title='Spot (€)',
            showgrid=True
        ),
    )
    
    
     

    return fig_spot

# GRAFICO COMPARATIVO DE COSTES QH REAL VS INTERPOLADO+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def graficar_costes(df_comp):
    fig_comp_costes = px.bar(
        df_comp.melt(
            id_vars="datetime", 
            value_vars=["coste_real","coste_interpolado"],
            var_name="tipo", value_name="energia"
        ),
        x="datetime", y="energia", color="tipo",
        barmode="group",
        title=f'Comparación COSTE (€) cuartohorario interpolado vs real',
        color_discrete_map={
            "coste_real": color_real,
            "coste_interpolado": color_interpol
        }
    )

    fig_comp_costes.update_layout(
        xaxis=dict(
            title='Fecha-Hora (cada 15 minutos)',
            showgrid=True,
            rangeslider=dict(
                visible=True,
                bgcolor='rgba(173, 216, 230, 0.5)',  # azul semitransparente
            ),
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1 día", step="day", stepmode="backward"),
                    dict(count=7, label="1 semana", step="day", stepmode="backward"),
                    dict(step="all", label="Todo")
                ]
            )
        ),
        yaxis=dict(
            title='Coste (€)',
            showgrid=True
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        legend_title_text=''
    )

    return fig_comp_costes





# GRAFICO EVOLUCIÓN MENSUAL DE LA COMPARATIVA COSTE REAL VS INTERPOLADO

def graficar_evol_coste(df_comp_diario, mes_nombre):

    category_order = list(df_comp_diario["dia_num"])  # ['1','2',...,'31','TOTAL']

    # Colores más suaves para las barras intermedias
    verde_suave = "rgba(46, 125, 50, 0.4)"   # verde apagado
    rojo_suave = "rgba(198, 40, 40, 0.4)"    # rojo apagado

    # --- Definir medidas ---
    measures = ['relative'] * (len(df_comp_diario) - 1) + ['total']

    # Determinar color del total según signo
    color_total = "rgba(198, 40, 40, 1)" if df_comp_diario['dif_dia'].iloc[-1] > 0 else "rgba(46, 125, 50, 1)"
    fig_waterfall = go.Figure(go.Waterfall(
        name="Diferencia diaria (€)",
        orientation="v",
        measure=measures,
        x=df_comp_diario['dia_num'],
        y=df_comp_diario['dif_dia'].fillna(0),
        text=df_comp_diario['dif_dia'].apply(lambda x: f"{x:.2f}" if pd.notna(x) and x != 0 else ""),  # 🔹 sin NaN
        
        textposition="outside",
        decreasing={"marker": {"color": verde_suave}},  # verde apagado
        increasing={"marker": {"color": rojo_suave}},   # rojo apagado
        totals={"marker": {"color": color_total}},      # total color intenso
        connector={"line": {"color": "rgb(90,90,90)"}},
    ))

    fig_waterfall.update_layout(
        title=f"Evolución del coste mensual por interpolación de la curva horaria vs real cuarto horaria - {mes_nombre} de 2025",
        xaxis_title="Día",
        yaxis_title="Diferencia diaria (€)",
        #width=1200,
        #height=500,
        showlegend=False
    )

    # --- Forzar orden correcto del eje X y mantener 'TOTAL' visible ---
    fig_waterfall.update_xaxes(
        type='category',
        categoryorder='array',
        categoryarray=category_order
    )

    return fig_waterfall


